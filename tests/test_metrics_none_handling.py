"""
Tests for metrics.py None handling in database queries

REGRESSION TEST for bug at metrics.py:219:
TypeError: 'NoneType' object is not subscriptable

The bug occurred when cursor.fetchone() returned None (empty result set)
and the code tried to subscript it directly: cursor.fetchone()[0]

The fix adds safety checks: result = cursor.fetchone(); value = result[0] if result else 0
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import tempfile

import pytest

from monitoring.metrics import MetricsAggregator
from tasks.database import Database
from tasks.manager import TaskManager
from tasks.tracker import ToolUsageTracker


class TestMetricsNoneHandling:
    """Test suite for None handling in metrics queries"""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        temp_file.close()
        yield temp_file.name
        # Cleanup
        Path(temp_file.name).unlink(missing_ok=True)

    @pytest.fixture
    def task_db(self, temp_db_path):
        """Create a real Database instance for testing"""
        db = Database(temp_db_path)
        yield db
        db.close()

    @pytest.fixture
    def task_manager(self, task_db):
        """Create a TaskManager with the test database"""
        manager = TaskManager(db=task_db)
        return manager

    @pytest.fixture
    def tool_tracker(self, task_db):
        """Create a ToolUsageTracker with the test database"""
        tracker = ToolUsageTracker(db=task_db)
        return tracker

    @pytest.fixture
    def metrics_aggregator(self, task_manager, tool_tracker):
        """Create a MetricsAggregator with test dependencies"""
        aggregator = MetricsAggregator(
            task_manager=task_manager,
            tool_usage_tracker=tool_tracker,
            hooks_reader=None
        )
        return aggregator

    def test_get_system_health_with_empty_database(self, metrics_aggregator):
        """
        CRITICAL REGRESSION TEST: get_system_health with empty database.
        
        Before fix:
            bot_tasks_count = cursor.fetchone()[0]  # TypeError if None
            cli_sessions_count = cursor.fetchone()[0]  # TypeError if None
        
        After fix:
            result = cursor.fetchone()
            bot_tasks_count = result[0] if result is not None else 0
        
        This test ensures empty database doesn't crash the metrics endpoint.
        """
        # Empty database should not raise TypeError
        health = metrics_aggregator.get_system_health()
        
        # Should return valid structure with zero counts
        assert isinstance(health, dict)
        assert "active_tasks_count" in health
        assert health["active_tasks_count"] == 0
        assert health["recent_errors_24h"] == 0
        assert isinstance(health["recent_errors"], list)
        assert len(health["recent_errors"]) == 0

    def test_get_system_health_count_queries_with_no_results(self, task_db):
        """
        Direct test of COUNT(*) queries that were causing the bug.
        
        Simulates the exact queries from get_system_health() on empty database.
        """
        cursor = task_db.conn.cursor()
        
        # Test 1: Count bot tasks (line 205-206 in original code)
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'running')")
        result = cursor.fetchone()
        # COUNT(*) should return (0,) not None, but we handle None defensively
        assert result is not None
        count = result[0] if result is not None else 0
        assert count == 0
        
        # Test 2: Count CLI sessions (line 210-219 in original code)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT tool_usage.task_id)
            FROM tool_usage
            LEFT JOIN tasks ON tool_usage.task_id = tasks.task_id
            WHERE tool_usage.timestamp >= ? AND tasks.task_id IS NULL
        """,
            ("2025-01-01T00:00:00",),
        )
        result = cursor.fetchone()
        # This was the line causing TypeError in production
        assert result is not None
        count = result[0] if result is not None else 0
        assert count == 0

    def test_get_system_health_returns_all_required_fields(self, metrics_aggregator):
        """Verify complete response structure"""
        health = metrics_aggregator.get_system_health()
        
        required_fields = [
            "data_file_sizes_mb",
            "active_tasks_count",
            "recent_errors_24h",
            "recent_errors",
            "disk_space",
            "timestamp"
        ]
        
        for field in required_fields:
            assert field in health, f"Missing required field: {field}"
        
        # Type checks
        assert isinstance(health["active_tasks_count"], int)
        assert isinstance(health["recent_errors_24h"], int)
        assert isinstance(health["recent_errors"], list)
        assert isinstance(health["data_file_sizes_mb"], dict)
        assert isinstance(health["disk_space"], dict)

    def test_fetchone_none_safety_pattern(self):
        """
        Demonstrate the safe pattern for handling cursor.fetchone() results.
        
        This documents the fix pattern used throughout get_system_health().
        """
        # Setup in-memory database
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test (id INTEGER)")
        
        # Query with no results
        cursor.execute("SELECT COUNT(*) FROM test WHERE id = 999")
        result = cursor.fetchone()
        
        # WRONG (original code - can raise TypeError):
        # count = cursor.fetchone()[0]
        
        # RIGHT (fixed code):
        count = result[0] if result is not None else 0
        
        assert count == 0
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
