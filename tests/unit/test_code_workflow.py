"""
Test code-task workflow script
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


import pytest
from tasks.database import Database
from tasks.manager import TaskManager


@pytest.mark.asyncio
async def test_create_test_task():
    """Test that we can create a test task for code workflow"""

    # Initialize
    db = Database()
    task_manager = TaskManager(db=db)

    # Create test task
    task = await task_manager.create_task(
        user_id=999999999,  # Test user
        description="Test code workflow task creation",
        workspace="/tmp/test",
        model="sonnet",
        agent_type="code_agent",
        workflow="code-task",
        context="Test context",
    )

    # Verify task created
    assert task is not None
    assert task.task_id is not None
    assert task.status == "pending"
    assert task.workflow == "code-task"
    assert task.agent_type == "code_agent"
    assert task.model == "sonnet"

    # Verify task can be retrieved
    retrieved = task_manager.get_task(task.task_id)
    assert retrieved is not None
    assert retrieved.task_id == task.task_id
    assert retrieved.description == "Test code workflow task creation"

    # Verify activity logging works
    await task_manager.log_activity(task.task_id, "Test activity entry")

    # Re-fetch and check activity
    updated = task_manager.get_task(task.task_id)
    assert updated.activity_log is not None
    assert len(updated.activity_log) > 0


@pytest.mark.asyncio
async def test_workflow_task_attributes():
    """Test that workflow-created tasks have correct attributes"""

    db = Database()
    task_manager = TaskManager(db=db)

    # Create task with workflow
    task = await task_manager.create_task(
        user_id=999999999, description="Workflow attribute test", workspace="/tmp/test", workflow="code-task"
    )

    # Verify workflow-specific attributes
    assert task.workflow == "code-task"
    assert task.context is None  # Optional field
    assert task.agent_type == "code_agent"  # Default for code tasks

    # Test with context
    task_with_context = await task_manager.create_task(
        user_id=999999999,
        description="Context test",
        workspace="/tmp/test",
        workflow="code-task",
        context="This is the context from routing",
    )

    assert task_with_context.context == "This is the context from routing"
