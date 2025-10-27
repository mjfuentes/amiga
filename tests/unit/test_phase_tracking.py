"""
Tests for task phase tracking functionality.

Tests the new phase tracking columns (current_phase, phase_number) in the tasks table
and the update_task_phase() method.
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import tempfile
from datetime import datetime

import pytest

from tasks.database import Database


@pytest.fixture
def db():
    """Create temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    database = Database(db_path)
    yield database
    database.close()

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestPhaseTracking:
    """Test phase tracking functionality"""

    @pytest.mark.asyncio
    async def test_create_task_with_phase_defaults(self, db):
        """Test that new tasks have default phase values"""
        task = await db.create_task(
            task_id="test_task_1",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
            model="sonnet",
            agent_type="code_agent",
        )

        assert task["task_id"] == "test_task_1"
        assert task["current_phase"] is None
        assert task["phase_number"] == 0

    @pytest.mark.asyncio
    async def test_update_task_phase(self, db):
        """Test updating task phase information"""
        # Create task
        await db.create_task(
            task_id="test_task_2",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
        )

        # Update phase
        success = await db.update_task_phase("test_task_2", "code_agent", 1)
        assert success is True

        # Verify update
        task = db.get_task("test_task_2")
        assert task["current_phase"] == "code_agent"
        assert task["phase_number"] == 1

    @pytest.mark.asyncio
    async def test_update_task_phase_progression(self, db):
        """Test phase progression through multiple subagents"""
        # Create task
        await db.create_task(
            task_id="test_task_3",
            user_id=12345,
            description="Test task with workflow",
            workspace="/tmp/test",
        )

        # Simulate workflow: code_agent -> git-merge -> task-completion-validator
        phases = [
            ("code_agent", 1),
            ("git-merge", 2),
            ("task-completion-validator", 3),
        ]

        for subagent, phase_num in phases:
            await db.update_task_phase("test_task_3", subagent, phase_num)

            task = db.get_task("test_task_3")
            assert task["current_phase"] == subagent
            assert task["phase_number"] == phase_num

    @pytest.mark.asyncio
    async def test_update_task_phase_nonexistent_task(self, db):
        """Test updating phase for nonexistent task"""
        success = await db.update_task_phase("nonexistent_task", "code_agent", 1)
        assert success is False

    @pytest.mark.asyncio
    async def test_phase_tracking_with_task_update(self, db):
        """Test that phase tracking works alongside other task updates"""
        # Create task
        await db.create_task(
            task_id="test_task_4",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
        )

        # Update phase
        await db.update_task_phase("test_task_4", "code_agent", 1)

        # Update status
        await db.update_task("test_task_4", status="running")

        # Verify both updates persist
        task = db.get_task("test_task_4")
        assert task["current_phase"] == "code_agent"
        assert task["phase_number"] == 1
        assert task["status"] == "running"

    @pytest.mark.asyncio
    async def test_phase_tracking_updates_timestamp(self, db):
        """Test that phase updates also update the updated_at timestamp"""
        # Create task
        await db.create_task(
            task_id="test_task_5",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
        )

        original_task = db.get_task("test_task_5")
        original_updated_at = original_task["updated_at"]

        # Wait a moment to ensure timestamp difference
        await asyncio.sleep(0.1)

        # Update phase
        await db.update_task_phase("test_task_5", "code_agent", 1)

        # Verify timestamp was updated
        updated_task = db.get_task("test_task_5")
        assert updated_task["updated_at"] > original_updated_at

    def test_get_task_includes_phase_fields(self, db):
        """Test that get_task returns phase fields in the result"""
        # Create task synchronously using asyncio.run
        asyncio.run(
            db.create_task(
                task_id="test_task_6",
                user_id=12345,
                description="Test task",
                workspace="/tmp/test",
            )
        )

        # Update phase
        asyncio.run(db.update_task_phase("test_task_6", "frontend_agent", 2))

        # Get task and verify phase fields are present
        task = db.get_task("test_task_6")
        assert "current_phase" in task
        assert "phase_number" in task
        assert task["current_phase"] == "frontend_agent"
        assert task["phase_number"] == 2

    def test_get_user_tasks_includes_phase_fields(self, db):
        """Test that get_user_tasks returns phase fields"""
        # Create multiple tasks with different phases
        asyncio.run(
            db.create_task(
                task_id="test_task_7",
                user_id=12345,
                description="Task 1",
                workspace="/tmp/test",
            )
        )
        asyncio.run(db.update_task_phase("test_task_7", "code_agent", 1))

        asyncio.run(
            db.create_task(
                task_id="test_task_8",
                user_id=12345,
                description="Task 2",
                workspace="/tmp/test",
            )
        )
        asyncio.run(db.update_task_phase("test_task_8", "git-merge", 2))

        # Get user tasks
        tasks = db.get_user_tasks(12345, limit=10)

        assert len(tasks) == 2
        for task in tasks:
            assert "current_phase" in task
            assert "phase_number" in task

        # Verify specific values (most recent first)
        assert tasks[0]["task_id"] == "test_task_8"
        assert tasks[0]["current_phase"] == "git-merge"
        assert tasks[0]["phase_number"] == 2

        assert tasks[1]["task_id"] == "test_task_7"
        assert tasks[1]["current_phase"] == "code_agent"
        assert tasks[1]["phase_number"] == 1

    @pytest.mark.asyncio
    async def test_phase_tracking_with_special_characters(self, db):
        """Test phase tracking handles subagent names with special characters"""
        await db.create_task(
            task_id="test_task_9",
            user_id=12345,
            description="Test task",
            workspace="/tmp/test",
        )

        # Test with subagent names that have hyphens, underscores, etc.
        special_subagents = [
            "task-completion-validator",
            "claude-md-compliance-checker",
            "code-quality-pragmatist",
        ]

        for i, subagent in enumerate(special_subagents, start=1):
            await db.update_task_phase("test_task_9", subagent, i)
            task = db.get_task("test_task_9")
            assert task["current_phase"] == subagent
            assert task["phase_number"] == i
