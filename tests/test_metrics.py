"""
Tests for monitoring/metrics.py module
Focuses on defensive null checks for empty database queries
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import sqlite3
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from monitoring.metrics import MetricsAggregator
from monitoring.hooks_reader import HooksReader
from tasks.manager import TaskManager
from tasks.tracker import ToolUsageTracker
from tasks.database import Database


@pytest.fixture
def empty_db():
    """Create an empty database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    db = Database(db_path)
    yield db
    
    # Cleanup
    db.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def metrics_aggregator(empty_db):
    """Create MetricsAggregator with empty database"""
    task_manager = TaskManager(empty_db)
    tool_tracker = ToolUsageTracker(empty_db)
    
    return MetricsAggregator(
        task_manager=task_manager,
        tool_usage_tracker=tool_tracker,
        hooks_reader=None
    )


class TestGetSystemHealthEmptyDatabase:
    """Test get_system_health() with empty database (regression test for tuple index error)"""
    
    def test_empty_database_no_tasks(self, metrics_aggregator):
        """Should return 0 for active tasks when database is empty"""
        health = metrics_aggregator.get_system_health()
        
        assert health["active_tasks_count"] == 0
        assert isinstance(health["active_tasks_count"], int)
    
    def test_empty_database_no_cli_sessions(self, metrics_aggregator):
        """Should return 0 for CLI sessions when tool_usage table is empty"""
        health = metrics_aggregator.get_system_health()
        
        # This should not crash even with empty tool_usage table
        assert health["active_tasks_count"] == 0
    
    def test_empty_database_recent_errors(self, metrics_aggregator):
        """Should return empty list for recent errors"""
        health = metrics_aggregator.get_system_health()
        
        assert health["recent_errors_24h"] == 0
        assert health["recent_errors"] == []
    
    def test_empty_database_full_health_check(self, metrics_aggregator):
        """Complete health check should not crash on empty database"""
        health = metrics_aggregator.get_system_health()
        
        # Verify all expected keys exist
        assert "data_file_sizes_mb" in health
        assert "active_tasks_count" in health
        assert "recent_errors_24h" in health
        assert "recent_errors" in health
        assert "disk_space" in health
        assert "timestamp" in health
        
        # Verify types
        assert isinstance(health["active_tasks_count"], int)
        assert isinstance(health["recent_errors_24h"], int)
        assert isinstance(health["recent_errors"], list)


class TestGetSystemHealthWithData:
    """Test get_system_health() with realistic data"""
    
    @pytest.mark.asyncio
    async def test_with_running_tasks(self, metrics_aggregator):
        """Should count running tasks correctly"""
        # Add a running task directly via SQL (simpler than async)
        cursor = metrics_aggregator.task_manager.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (task_id, user_id, description, status, created_at, updated_at, model, workspace, agent_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test-task-1",
                12345,
                "Test task",
                "running",
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                "claude-sonnet-4.5",
                "/test",
                "code_agent"
            )
        )
        metrics_aggregator.task_manager.db.conn.commit()
        
        health = metrics_aggregator.get_system_health()
        assert health["active_tasks_count"] >= 1
    
    @pytest.mark.asyncio
    async def test_with_failed_task_errors(self, metrics_aggregator):
        """Should include recent errors from failed tasks"""
        # Add a failed task directly via SQL
        cursor = metrics_aggregator.task_manager.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (task_id, user_id, description, status, created_at, updated_at, model, workspace, agent_type, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test-task-failed",
                12345,
                "Failed task",
                "failed",
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                "claude-sonnet-4.5",
                "/test",
                "code_agent",
                "Test error message"
            )
        )
        metrics_aggregator.task_manager.db.conn.commit()
        
        health = metrics_aggregator.get_system_health()
        assert health["recent_errors_24h"] >= 1
        assert len(health["recent_errors"]) >= 1
        assert health["recent_errors"][0]["task_id"] == "test-task-failed"
        assert "Test error message" in health["recent_errors"][0]["error"]
    
    def test_with_cli_sessions(self, metrics_aggregator):
        """Should count active CLI sessions from tool_usage"""
        # Add tool usage for a CLI session (not in tasks table)
        cursor = metrics_aggregator.task_manager.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tool_usage (timestamp, task_id, tool_name, success)
            VALUES (?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                "cli-session-123",
                "Bash",
                None  # NULL success indicates pre-tool hook (ongoing)
            )
        )
        metrics_aggregator.task_manager.db.conn.commit()
        
        health = metrics_aggregator.get_system_health()
        # Should count CLI session as active
        assert health["active_tasks_count"] >= 1


class TestGetTaskStatisticsEmptyDatabase:
    """Test get_task_statistics() with empty database"""
    
    def test_empty_database_statistics(self, metrics_aggregator):
        """Should handle empty task statistics gracefully"""
        stats = metrics_aggregator.get_task_statistics()
        
        assert stats["total_tasks"] == 0
        assert stats["by_status"] == {}
        assert stats["success_rate"] == 0.0
        assert stats["recent_24h"]["total"] == 0
        assert stats["recent_24h"]["tasks"] == []


class TestGetToolUsageMetricsEmptyDatabase:
    """Test get_tool_usage_metrics() with empty database"""
    
    def test_empty_database_tool_usage(self, metrics_aggregator):
        """Should handle empty tool usage gracefully"""
        metrics = metrics_aggregator.get_tool_usage_metrics(hours=24)
        
        assert metrics["time_window_hours"] == 24
        assert metrics["total_tool_calls"] == 0
        assert metrics["most_used_tools"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
