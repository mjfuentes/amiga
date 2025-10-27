"""
Integration test for complete task lifecycle

Tests the full flow from user message to task completion:
1. User sends message
2. Router creates task
3. AgentPool picks up task
4. ClaudeSessionPool executes
5. Task completed
6. User notified
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tasks.database import Database
from tasks.manager import TaskManager


@pytest.fixture
def isolated_db(tmp_path):
    """Create isolated database for testing"""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def isolated_workspace(tmp_path):
    """Create isolated workspace directory"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=workspace, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, capture_output=True)

    # Create initial commit
    (workspace / "README.md").write_text("# Test Workspace")
    subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace, capture_output=True)

    yield workspace


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_task_lifecycle(isolated_db, isolated_workspace):
    """
    Test complete task lifecycle from creation to completion

    Flow:
    1. Create task
    2. Submit to executor (mocked)
    3. Update status to running
    4. Update status to completed
    5. Verify final state
    """
    # Initialize task manager
    task_manager = TaskManager(isolated_db)

    user_id = 123456
    description = "Add hello world function to utils.py"

    # Step 1: Create task
    task = await task_manager.create_task(
        user_id=user_id,
        description=description,
        model="claude-sonnet-4.5",
        workspace=str(isolated_workspace),
        agent_type="code_agent"
    )

    assert task is not None
    assert task.task_id is not None
    assert task.status == "pending"
    assert task.user_id == user_id
    assert task.description == description

    # Step 2: Simulate task pickup by agent pool
    await task_manager.update_task(task.task_id, status="running", pid=os.getpid())

    # Verify running state
    running_task = await task_manager.get_task(task.task_id)
    assert running_task.status == "running"
    assert running_task.pid == os.getpid()

    # Step 3: Simulate task execution (create file)
    utils_file = isolated_workspace / "utils.py"
    utils_file.write_text("""
def hello_world():
    return "Hello, World!"
""")

    # Commit the change
    import subprocess
    subprocess.run(["git", "add", "."], cwd=isolated_workspace, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add hello world function"],
        cwd=isolated_workspace,
        capture_output=True
    )

    # Step 4: Mark task as completed
    result = "Added hello_world() function to utils.py"
    await task_manager.update_task(task.task_id, status="completed", result=result)

    # Step 5: Verify final state
    completed_task = await task_manager.get_task(task.task_id)
    assert completed_task.status == "completed"
    assert completed_task.result == result
    assert completed_task.error is None

    # Verify file was created
    assert utils_file.exists()
    content = utils_file.read_text()
    assert "hello_world" in content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_lifecycle_with_error(isolated_db, isolated_workspace):
    """
    Test task lifecycle when execution fails

    Flow:
    1. Create task
    2. Update to running
    3. Simulate error
    4. Update to failed with error message
    5. Verify error state
    """
    task_manager = TaskManager(isolated_db)

    user_id = 789012
    description = "Invalid task that will fail"

    # Create task
    task = await task_manager.create_task(
        user_id=user_id,
        description=description,
        model="claude-sonnet-4.5",
        workspace=str(isolated_workspace),
        agent_type="code_agent"
    )

    # Start execution
    await task_manager.update_task(task.task_id, status="running", pid=os.getpid())

    # Simulate error
    error_message = "File not found: nonexistent.py"
    await task_manager.update_task(task.task_id, status="failed", error=error_message)

    # Verify error state
    failed_task = await task_manager.get_task(task.task_id)
    assert failed_task.status == "failed"
    assert failed_task.error == error_message
    assert failed_task.result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_tasks_sequential(isolated_db, isolated_workspace):
    """
    Test multiple tasks executed sequentially

    Verifies that tasks can be created and completed one after another
    without interference.
    """
    task_manager = TaskManager(isolated_db)

    user_id = 345678
    tasks_completed = []

    # Create and execute 3 tasks sequentially
    for i in range(3):
        description = f"Task {i + 1}: Create file_{i}.txt"

        # Create task
        task = await task_manager.create_task(
            user_id=user_id,
            description=description,
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )

        # Execute
        await task_manager.update_task(task.task_id, status="running", pid=os.getpid())

        # Create file
        file_path = isolated_workspace / f"file_{i}.txt"
        file_path.write_text(f"Content from task {i + 1}")

        # Complete
        await task_manager.update_task(
            task.task_id,
            "completed",
            result=f"Created file_{i}.txt"
        )

        tasks_completed.append(task.task_id)

    # Verify all tasks completed
    for task_id in tasks_completed:
        task = await task_manager.get_task(task_id)
        assert task.status == "completed"

    # Verify all files created
    for i in range(3):
        file_path = isolated_workspace / f"file_{i}.txt"
        assert file_path.exists()
        assert file_path.read_text() == f"Content from task {i + 1}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_with_activity_log(isolated_db, isolated_workspace):
    """
    Test task with activity log updates

    Verifies that activity log entries are properly recorded during execution.
    """
    task_manager = TaskManager(isolated_db)

    user_id = 567890
    description = "Task with detailed activity logging"

    # Create task
    task = await task_manager.create_task(
        user_id=user_id,
        description=description,
        model="claude-sonnet-4.5",
        workspace=str(isolated_workspace),
        agent_type="code_agent"
    )

    # Start execution
    await task_manager.update_task(task.task_id, status="running", pid=os.getpid())

    # Add activity log entries
    activities = [
        "Started analysis of codebase",
        "Reading existing files",
        "Creating new module",
        "Running tests",
        "Committing changes"
    ]

    for activity in activities:
        await task_manager.add_activity(task.task_id, activity)

    # Complete task
    await task_manager.update_task(
        task.task_id,
        "completed",
        result="Task completed successfully"
    )

    # Verify activity log
    completed_task = await task_manager.get_task(task.task_id)
    assert completed_task.activity_log is not None

    import json
    log_entries = json.loads(completed_task.activity_log)
    assert len(log_entries) == len(activities)

    for i, activity in enumerate(activities):
        assert log_entries[i]["message"] == activity


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_query_by_user(isolated_db, isolated_workspace):
    """
    Test querying tasks by user ID

    Verifies that tasks can be filtered by user.
    """
    task_manager = TaskManager(isolated_db)

    # Create tasks for different users
    user1_id = 111111
    user2_id = 222222

    user1_tasks = []
    user2_tasks = []

    # Create 2 tasks for user1
    for i in range(2):
        task = await task_manager.create_task(
            user_id=user1_id,
            description=f"User1 task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )
        user1_tasks.append(task.task_id)

    # Create 3 tasks for user2
    for i in range(3):
        task = await task_manager.create_task(
            user_id=user2_id,
            description=f"User2 task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )
        user2_tasks.append(task.task_id)

    # Query user1's tasks
    user1_results = await task_manager.get_tasks_by_user(user1_id)
    assert len(user1_results) == 2
    assert all(t.user_id == user1_id for t in user1_results)

    # Query user2's tasks
    user2_results = await task_manager.get_tasks_by_user(user2_id)
    assert len(user2_results) == 3
    assert all(t.user_id == user2_id for t in user2_results)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_cancellation(isolated_db, isolated_workspace):
    """
    Test task cancellation/stopping

    Verifies that a running task can be stopped and marked as stopped.
    """
    task_manager = TaskManager(isolated_db)

    user_id = 999999
    description = "Long-running task that will be stopped"

    # Create task
    task = await task_manager.create_task(
        user_id=user_id,
        description=description,
        model="claude-sonnet-4.5",
        workspace=str(isolated_workspace),
        agent_type="code_agent"
    )

    # Start execution
    await task_manager.update_task(task.task_id, status="running", pid=os.getpid())

    # Verify running
    running_task = await task_manager.get_task(task.task_id)
    assert running_task.status == "running"

    # Stop task
    await task_manager.update_task(task.task_id, status="stopped")

    # Verify stopped
    stopped_task = await task_manager.get_task(task.task_id)
    assert stopped_task.status == "stopped"
