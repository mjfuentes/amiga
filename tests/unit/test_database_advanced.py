#!/usr/bin/env python3
"""
Advanced tests for tasks/database.py module
Tests cover missing methods, edge cases, and integration scenarios
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from tasks.database import Database


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing"""
    db_path = tmp_path / "test_agentlab.db"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def sample_task(temp_db):
    """Create a sample task for testing"""

    async def _create():
        task_data = await temp_db.create_task(
            task_id="test_task_123",
            user_id=12345,
            description="Test task description",
            workspace="/tmp/workspace",
            model="sonnet",
            agent_type="code_agent",
        )
        return task_data

    return asyncio.run(_create())


class TestTaskPhaseOperations:
    """Test suite for task phase tracking operations"""

    def test_update_task_phase_success(self, temp_db, sample_task):
        """Test successful task phase update"""

        async def _test():
            result = await temp_db.update_task_phase("test_task_123", "code_agent", 1)
            assert result is True

            # Verify phase was updated
            task = temp_db.get_task("test_task_123")
            assert task["current_phase"] == "code_agent"
            assert task["phase_number"] == 1

        asyncio.run(_test())

    def test_update_task_phase_multiple_phases(self, temp_db, sample_task):
        """Test updating phase multiple times"""

        async def _test():
            # Phase 1
            await temp_db.update_task_phase("test_task_123", "research_agent", 1)
            task = temp_db.get_task("test_task_123")
            assert task["phase_number"] == 1

            # Phase 2
            await temp_db.update_task_phase("test_task_123", "code_agent", 2)
            task = temp_db.get_task("test_task_123")
            assert task["current_phase"] == "code_agent"
            assert task["phase_number"] == 2

            # Phase 3
            await temp_db.update_task_phase("test_task_123", "git-merge", 3)
            task = temp_db.get_task("test_task_123")
            assert task["current_phase"] == "git-merge"
            assert task["phase_number"] == 3

        asyncio.run(_test())

    def test_update_task_phase_nonexistent_task(self, temp_db):
        """Test updating phase of nonexistent task"""

        async def _test():
            result = await temp_db.update_task_phase("nonexistent_task", "code_agent", 1)
            assert result is False

        asyncio.run(_test())

    def test_update_task_phase_zero_phase(self, temp_db, sample_task):
        """Test updating phase with zero phase number"""

        async def _test():
            result = await temp_db.update_task_phase("test_task_123", "code_agent", 0)
            assert result is True

            task = temp_db.get_task("test_task_123")
            assert task["phase_number"] == 0

        asyncio.run(_test())


class TestActivityLogOperations:
    """Test suite for activity log operations"""

    def test_add_activity_basic(self, temp_db, sample_task):
        """Test adding activity to task log"""

        async def _test():
            result = await temp_db.add_activity("test_task_123", "Task started")
            assert result is True

            task = temp_db.get_task("test_task_123")
            assert len(task["activity_log"]) == 1
            assert task["activity_log"][0]["message"] == "Task started"
            assert "timestamp" in task["activity_log"][0]

        asyncio.run(_test())

    def test_add_activity_multiple_entries(self, temp_db, sample_task):
        """Test adding multiple activity entries"""

        async def _test():
            await temp_db.add_activity("test_task_123", "Task started")
            await temp_db.add_activity("test_task_123", "Processing files")
            await temp_db.add_activity("test_task_123", "Task completed", output_lines=50)

            task = temp_db.get_task("test_task_123")
            assert len(task["activity_log"]) == 3
            assert task["activity_log"][0]["message"] == "Task started"
            assert task["activity_log"][1]["message"] == "Processing files"
            assert task["activity_log"][2]["message"] == "Task completed"
            assert task["activity_log"][2]["output_lines"] == 50

        asyncio.run(_test())

    def test_add_activity_with_output_lines(self, temp_db, sample_task):
        """Test adding activity with output line count"""

        async def _test():
            result = await temp_db.add_activity("test_task_123", "Generated output", output_lines=100)
            assert result is True

            task = temp_db.get_task("test_task_123")
            assert task["activity_log"][0]["output_lines"] == 100

        asyncio.run(_test())

    def test_add_activity_nonexistent_task(self, temp_db):
        """Test adding activity to nonexistent task"""

        async def _test():
            result = await temp_db.add_activity("nonexistent_task", "Should fail")
            assert result is False

        asyncio.run(_test())

    def test_activity_log_chronological_order(self, temp_db, sample_task):
        """Test that activity log maintains chronological order"""

        async def _test():
            await temp_db.add_activity("test_task_123", "First")
            await asyncio.sleep(0.01)  # Ensure different timestamps
            await temp_db.add_activity("test_task_123", "Second")
            await asyncio.sleep(0.01)
            await temp_db.add_activity("test_task_123", "Third")

            task = temp_db.get_task("test_task_123")
            log = task["activity_log"]

            # Check chronological order
            timestamp_1 = datetime.fromisoformat(log[0]["timestamp"])
            timestamp_2 = datetime.fromisoformat(log[1]["timestamp"])
            timestamp_3 = datetime.fromisoformat(log[2]["timestamp"])

            assert timestamp_1 <= timestamp_2 <= timestamp_3

        asyncio.run(_test())


class TestInterruptedTaskOperations:
    """Test suite for interrupted task operations"""

    def test_get_interrupted_tasks_empty(self, temp_db):
        """Test getting interrupted tasks when none exist"""
        tasks = temp_db.get_interrupted_tasks()
        assert tasks == []

    def test_get_interrupted_tasks_with_restart(self, temp_db):
        """Test getting tasks interrupted by restart"""

        async def _test():
            # Create task and mark as stopped due to restart
            await temp_db.create_task(
                task_id="task_1",
                user_id=12345,
                description="Task 1",
                workspace="/tmp/workspace",
            )
            await temp_db.update_task(
                task_id="task_1", status="stopped", error="Task stopped due to bot restart"
            )

            interrupted = temp_db.get_interrupted_tasks()
            assert len(interrupted) == 1
            assert interrupted[0]["task_id"] == "task_1"
            assert interrupted[0]["error"] == "Task stopped due to bot restart"

        asyncio.run(_test())

    def test_get_interrupted_tasks_with_shutdown(self, temp_db):
        """Test getting tasks interrupted by shutdown"""

        async def _test():
            await temp_db.create_task(
                task_id="task_2",
                user_id=12345,
                description="Task 2",
                workspace="/tmp/workspace",
            )
            await temp_db.update_task(
                task_id="task_2", status="stopped", error="Task stopped during bot shutdown"
            )

            interrupted = temp_db.get_interrupted_tasks()
            assert len(interrupted) == 1
            assert "shutdown" in interrupted[0]["error"]

        asyncio.run(_test())

    def test_get_interrupted_tasks_grouped_by_user(self, temp_db):
        """Test that interrupted tasks are ordered by user and time"""

        async def _test():
            # Create multiple interrupted tasks
            await temp_db.create_task("task_1", 100, "Task 1", "/tmp/workspace")
            await temp_db.update_task("task_1", status="stopped", error="Task stopped due to bot restart")

            await temp_db.create_task("task_2", 200, "Task 2", "/tmp/workspace")
            await temp_db.update_task("task_2", status="stopped", error="Task stopped due to bot restart")

            interrupted = temp_db.get_interrupted_tasks()
            assert len(interrupted) == 2

            # Verify grouping (sorted by user_id, then created_at DESC)
            user_ids = [task["user_id"] for task in interrupted]
            assert user_ids == sorted(user_ids)

        asyncio.run(_test())

    def test_interrupted_tasks_excludes_normal_stopped(self, temp_db):
        """Test that normal stopped tasks are not included"""

        async def _test():
            await temp_db.create_task("task_normal", 12345, "Normal task", "/tmp/workspace")
            await temp_db.update_task("task_normal", status="stopped", error="User cancelled")

            interrupted = temp_db.get_interrupted_tasks()
            assert len(interrupted) == 0

        asyncio.run(_test())


class TestMarkRunningAsStopped:
    """Test suite for mark_all_running_as_stopped operations"""

    def test_mark_running_as_stopped_empty(self, temp_db):
        """Test marking when no running tasks exist"""
        count = temp_db.mark_all_running_as_stopped()
        assert count == 0

    def test_mark_running_as_stopped_single_task(self, temp_db):
        """Test marking single running task as stopped"""

        async def _test():
            await temp_db.create_task("task_1", 12345, "Running task", "/tmp/workspace")
            await temp_db.update_task("task_1", status="running")

            count = temp_db.mark_all_running_as_stopped()
            assert count == 1

            # Verify task status changed
            task = temp_db.get_task("task_1")
            assert task["status"] == "stopped"
            assert "shutdown" in task["error"]

        asyncio.run(_test())

    def test_mark_running_as_stopped_multiple_tasks(self, temp_db):
        """Test marking multiple running tasks as stopped"""

        async def _test():
            await temp_db.create_task("task_1", 12345, "Task 1", "/tmp/workspace")
            await temp_db.create_task("task_2", 12345, "Task 2", "/tmp/workspace")
            await temp_db.create_task("task_3", 12345, "Task 3", "/tmp/workspace")

            await temp_db.update_task("task_1", status="running")
            await temp_db.update_task("task_2", status="running")
            await temp_db.update_task("task_3", status="running")

            count = temp_db.mark_all_running_as_stopped()
            assert count == 3

            # Verify all tasks marked as stopped
            for task_id in ["task_1", "task_2", "task_3"]:
                task = temp_db.get_task(task_id)
                assert task["status"] == "stopped"

        asyncio.run(_test())

    def test_mark_running_excludes_other_statuses(self, temp_db):
        """Test that only running tasks are marked"""

        async def _test():
            await temp_db.create_task("task_pending", 12345, "Pending", "/tmp/workspace")
            await temp_db.create_task("task_running", 12345, "Running", "/tmp/workspace")
            await temp_db.create_task("task_completed", 12345, "Completed", "/tmp/workspace")

            await temp_db.update_task("task_pending", status="pending")
            await temp_db.update_task("task_running", status="running")
            await temp_db.update_task("task_completed", status="completed")

            count = temp_db.mark_all_running_as_stopped()
            assert count == 1

            # Verify other statuses unchanged
            assert temp_db.get_task("task_pending")["status"] == "pending"
            assert temp_db.get_task("task_running")["status"] == "stopped"
            assert temp_db.get_task("task_completed")["status"] == "completed"

        asyncio.run(_test())

    def test_mark_running_adds_activity_log(self, temp_db):
        """Test that activity log entry is added when marking stopped"""

        async def _test():
            await temp_db.create_task("task_1", 12345, "Task", "/tmp/workspace")
            await temp_db.update_task("task_1", status="running")

            temp_db.mark_all_running_as_stopped()

            task = temp_db.get_task("task_1")
            assert len(task["activity_log"]) == 1
            assert "shutdown" in task["activity_log"][0]["message"]

        asyncio.run(_test())


class TestToolUsageUpdateMethod:
    """Test suite for update_tool_usage method"""

    def test_update_tool_usage_success(self, temp_db):
        """Test updating existing tool usage record"""
        # Create in-progress tool usage
        temp_db.record_tool_usage(
            task_id="task_1", tool_name="Read", duration_ms=None, success=None, parameters={"file": "test.py"}
        )

        # Update with completion data
        result = temp_db.update_tool_usage(
            task_id="task_1",
            tool_name="Read",
            success=True,
            input_tokens=100,
            output_tokens=50,
        )

        assert result is True

    def test_update_tool_usage_no_record(self, temp_db):
        """Test updating non-existent tool usage record"""
        result = temp_db.update_tool_usage(
            task_id="nonexistent", tool_name="Read", success=True
        )
        assert result is False

    def test_update_tool_usage_with_error(self, temp_db):
        """Test updating with error information"""
        temp_db.record_tool_usage(
            task_id="task_2", tool_name="Bash", duration_ms=None, success=None
        )

        result = temp_db.update_tool_usage(
            task_id="task_2",
            tool_name="Bash",
            success=False,
            error="Command failed",
            error_category="execution_error",
        )

        assert result is True

    def test_update_tool_usage_with_tokens(self, temp_db):
        """Test updating with token usage data"""
        temp_db.record_tool_usage(
            task_id="task_3", tool_name="Task", duration_ms=None, success=None
        )

        result = temp_db.update_tool_usage(
            task_id="task_3",
            tool_name="Task",
            success=True,
            input_tokens=500,
            output_tokens=200,
            cache_creation_tokens=100,
            cache_read_tokens=300,
        )

        assert result is True


class TestDatabaseEdgeCases:
    """Test suite for edge cases and error handling"""

    def test_create_task_with_all_fields(self, temp_db):
        """Test creating task with all optional fields"""

        async def _test():
            task = await temp_db.create_task(
                task_id="full_task",
                user_id=12345,
                description="Full task",
                workspace="/workspace",
                model="opus",
                agent_type="research_agent",
                workflow="research_workflow",
                context="Additional context",
            )

            assert task["task_id"] == "full_task"
            assert task["model"] == "opus"
            assert task["agent_type"] == "research_agent"
            assert task["workflow"] == "research_workflow"
            assert task["context"] == "Additional context"

        asyncio.run(_test())

    def test_update_task_no_changes(self, temp_db, sample_task):
        """Test updating task with no actual changes"""

        async def _test():
            result = await temp_db.update_task("test_task_123")
            assert result is False  # No updates provided

        asyncio.run(_test())

    def test_cleanup_stale_pending_tasks(self, temp_db):
        """Test cleanup of stale pending tasks"""

        async def _test():
            # Create old pending task
            await temp_db.create_task("old_task", 12345, "Old task", "/workspace")

            # Manually set old timestamp
            cursor = temp_db.conn.cursor()
            old_time = (datetime.now() - timedelta(hours=2)).isoformat()
            cursor.execute(
                "UPDATE tasks SET created_at = ?, status = 'pending' WHERE task_id = ?",
                (old_time, "old_task"),
            )
            temp_db.conn.commit()

            # Cleanup stale tasks
            count = temp_db.cleanup_stale_pending_tasks(max_age_hours=1)
            assert count == 1

            # Verify task marked as failed
            task = temp_db.get_task("old_task")
            assert task["status"] == "failed"
            assert "pending for more than" in task["error"]

        asyncio.run(_test())

    def test_get_task_statistics_empty_db(self, temp_db):
        """Test statistics on empty database"""
        stats = temp_db.get_task_statistics()
        assert stats["total"] == 0
        assert stats["by_status"] == {}
        assert stats["recent_24h"] == 0
        assert stats["success_rate"] == 0

    def test_vacuum_database(self, temp_db):
        """Test database vacuum operation"""
        # Should not raise exception
        temp_db.vacuum()

    def test_database_context_manager(self, tmp_path):
        """Test database as context manager"""
        db_path = tmp_path / "context_test.db"

        with Database(db_path) as db:
            assert db.conn is not None
            stats = db.get_database_stats()
            assert "tasks" in stats

        # Connection should be closed after context
