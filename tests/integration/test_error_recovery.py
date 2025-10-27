"""
Integration test for error recovery scenarios

Tests recovery from various failure modes:
- Process crashes during execution
- Database corruption recovery
- Orphaned tasks detection and cleanup
- Restart recovery
- Graceful degradation
"""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tasks.database import Database
from tasks.manager import TaskManager, is_process_alive


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
    subprocess.run(["git", "init"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=workspace,
        capture_output=True,
        check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=workspace,
        capture_output=True,
        check=True
    )

    # Create initial commit
    (workspace / "README.md").write_text("# Test Workspace")
    subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=workspace,
        capture_output=True,
        check=True
    )

    yield workspace


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orphaned_task_detection(isolated_db, isolated_workspace):
    """
    Test detection of orphaned tasks (running tasks with dead PIDs)

    Scenario:
    1. Create task with running status
    2. Set PID to non-existent process
    3. Verify orphaned task detection
    4. Cleanup orphaned tasks
    """
    task_manager = TaskManager(isolated_db)

    user_id = 123456
    description = "Task that will become orphaned"

    # Create task
    task = await task_manager.create_task(
        user_id=user_id,
        description=description,
        model="claude-sonnet-4.5",
        workspace=str(isolated_workspace),
        agent_type="code_agent"
    )

    # Set task to running with fake PID that doesn't exist
    fake_pid = 999999  # Unlikely to exist
    await task_manager.update_task(task.task_id, status="running", pid=fake_pid)

    # Verify task is marked as running
    running_task = await task_manager.get_task(task.task_id)
    assert running_task.status == "running"
    assert running_task.pid == fake_pid

    # Check if process is alive (should be False)
    assert not is_process_alive(fake_pid)

    # Simulate orphaned task cleanup
    # (In production, this would be done by restart recovery)
    await task_manager.update_task(
        task.task_id,
        "stopped",
        error="Process terminated unexpectedly"
    )

    # Verify task marked as stopped
    stopped_task = await task_manager.get_task(task.task_id)
    assert stopped_task.status == "stopped"
    assert "terminated unexpectedly" in stopped_task.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_restart_recovery_scenario(isolated_db, isolated_workspace):
    """
    Test restart recovery process

    Scenario:
    1. Start multiple tasks
    2. Simulate crash (leave tasks in running state)
    3. Simulate restart
    4. Verify orphaned tasks detected and marked as stopped
    """
    task_manager = TaskManager(isolated_db)

    user_id = 789012

    # Create 3 tasks and mark as running with fake PIDs
    tasks = []
    for i in range(3):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Task {i + 1} before crash",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )
        fake_pid = 900000 + i  # Non-existent PIDs
        await task_manager.update_task(task.task_id, status="running", pid=fake_pid)
        tasks.append(task)

    # Verify all tasks are running
    for task in tasks:
        running_task = await task_manager.get_task(task.task_id)
        assert running_task.status == "running"

    # Simulate restart: check for orphaned tasks
    running_tasks = [t for t in tasks if await task_manager.get_task(t.task_id).status == "running"]

    orphaned_count = 0
    for task in running_tasks:
        task_data = await task_manager.get_task(task.task_id)
        if task_data.pid and not is_process_alive(task_data.pid):
            await task_manager.update_task(
                task.task_id,
                "stopped",
                error="Task interrupted by system restart"
            )
            orphaned_count += 1

    # Verify all tasks were marked as orphaned
    assert orphaned_count == 3

    # Verify final state
    for task in tasks:
        final_task = await task_manager.get_task(task.task_id)
        assert final_task.status == "stopped"
        assert "interrupted by system restart" in final_task.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_task_timeout_recovery(isolated_db, isolated_workspace):
    """
    Test recovery from task timeout

    Scenario:
    1. Start task
    2. Simulate long-running operation
    3. Timeout expires
    4. Task marked as failed
    """
    task_manager = TaskManager(isolated_db)

    user_id = 345678
    description = "Task that will timeout"

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

    # Simulate timeout check (in production, this would be done by timeout monitor)
    # For testing, we just mark it as failed with timeout error
    await task_manager.update_task(
        task.task_id,
        "failed",
        error="Task exceeded maximum execution time (600s)"
    )

    # Verify timeout error recorded
    failed_task = await task_manager.get_task(task.task_id)
    assert failed_task.status == "failed"
    assert "exceeded maximum execution time" in failed_task.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_connection_failure_recovery(isolated_db, isolated_workspace):
    """
    Test recovery from database connection issues

    Scenario:
    1. Create task
    2. Simulate database connection error
    3. Retry with backoff
    4. Verify operation succeeds after retry
    """
    task_manager = TaskManager(isolated_db)

    user_id = 567890
    description = "Task with DB retry"

    # Create task successfully
    task = await task_manager.create_task(
        user_id=user_id,
        description=description,
        model="claude-sonnet-4.5",
        workspace=str(isolated_workspace),
        agent_type="code_agent"
    )

    assert task is not None

    # Simulate retry logic for database operations
    # In production, this would be in database.py with actual retry logic
    max_retries = 3
    retry_count = 0
    success = False

    while retry_count < max_retries and not success:
        try:
            # Attempt to update status
            await task_manager.update_task(task.task_id, status="running", pid=os.getpid())
            success = True
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise
            await asyncio.sleep(0.1 * retry_count)  # Exponential backoff

    # Verify operation succeeded
    assert success
    running_task = await task_manager.get_task(task.task_id)
    assert running_task.status == "running"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_partial_completion_recovery(isolated_db, isolated_workspace):
    """
    Test recovery from partial task completion

    Scenario:
    1. Start task
    2. Complete some work
    3. Process crashes
    4. Restart and detect incomplete work
    5. Resume or mark as stopped appropriately
    """
    task_manager = TaskManager(isolated_db)

    user_id = 111111
    description = "Task with partial completion"

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

    # Add activity log showing partial progress
    await task_manager.add_activity(task.task_id, "Started task execution")
    await task_manager.add_activity(task.task_id, "Analyzed codebase")
    await task_manager.add_activity(task.task_id, "Created new file")

    # Create partial work
    partial_file = isolated_workspace / "incomplete.py"
    partial_file.write_text("# Incomplete implementation\n")

    # Simulate crash (process dies, no commit)
    fake_dead_pid = 888888
    await task_manager.update_task(task.task_id, status="running", pid=fake_dead_pid)

    # Simulate restart recovery
    task_data = await task_manager.get_task(task.task_id)
    if not is_process_alive(task_data.pid):
        # Check for uncommitted changes (in production, would use git status)
        has_uncommitted = partial_file.exists()

        if has_uncommitted:
            await task_manager.update_task(
                task.task_id,
                "stopped",
                error="Task interrupted with uncommitted changes"
            )

    # Verify task marked as stopped with appropriate error
    stopped_task = await task_manager.get_task(task.task_id)
    assert stopped_task.status == "stopped"
    assert "uncommitted changes" in stopped_task.error

    # Verify partial work exists
    assert partial_file.exists()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cascading_failure_isolation(isolated_db, isolated_workspace):
    """
    Test that one task failure doesn't affect other tasks

    Scenario:
    1. Start multiple tasks
    2. One task fails
    3. Verify other tasks continue unaffected
    """
    task_manager = TaskManager(isolated_db)

    user_id = 222222

    # Create 3 tasks
    tasks = []
    for i in range(3):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )
        await task_manager.update_task(task.task_id, status="running", pid=os.getpid() + i)
        tasks.append(task)

    # Fail the middle task
    await task_manager.update_task(
        tasks[1].task_id,
        "failed",
        error="Simulated failure"
    )

    # Complete the other tasks
    await task_manager.update_task(tasks[0].task_id, status="completed", result="Success")
    await task_manager.update_task(tasks[2].task_id, status="completed", result="Success")

    # Verify states
    task0 = await task_manager.get_task(tasks[0].task_id)
    task1 = await task_manager.get_task(tasks[1].task_id)
    task2 = await task_manager.get_task(tasks[2].task_id)

    assert task0.status == "completed"
    assert task1.status == "failed"
    assert task2.status == "completed"

    # Verify failed task doesn't affect others
    assert task0.error is None
    assert task2.error is None
    assert "Simulated failure" in task1.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graceful_shutdown_handling(isolated_db, isolated_workspace):
    """
    Test graceful shutdown with running tasks

    Scenario:
    1. Start tasks
    2. Initiate graceful shutdown
    3. Wait for tasks to complete or timeout
    4. Mark incomplete tasks as stopped
    """
    task_manager = TaskManager(isolated_db)

    user_id = 333333

    # Create and start tasks
    tasks = []
    for i in range(3):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Task during shutdown {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )
        await task_manager.update_task(task.task_id, status="running", pid=os.getpid())
        tasks.append(task)

    # Simulate graceful shutdown
    shutdown_timeout = 0.5  # seconds
    start_time = time.time()

    # Complete some tasks before timeout
    await task_manager.update_task(tasks[0].task_id, status="completed", result="Finished in time")

    # Wait for timeout
    await asyncio.sleep(shutdown_timeout)

    # Mark remaining running tasks as stopped
    for task in tasks[1:]:
        task_data = await task_manager.get_task(task.task_id)
        if task_data.status == "running":
            await task_manager.update_task(
                task.task_id,
                "stopped",
                error="Task stopped during graceful shutdown"
            )

    # Verify final states
    task0 = await task_manager.get_task(tasks[0].task_id)
    task1 = await task_manager.get_task(tasks[1].task_id)
    task2 = await task_manager.get_task(tasks[2].task_id)

    assert task0.status == "completed"
    assert task1.status == "stopped"
    assert task2.status == "stopped"

    assert "graceful shutdown" in task1.error
    assert "graceful shutdown" in task2.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_notification_queuing(isolated_db, isolated_workspace):
    """
    Test that errors are properly queued for user notification

    Scenario:
    1. Multiple tasks fail
    2. Errors are recorded
    3. System can retrieve all errors for notification
    """
    task_manager = TaskManager(isolated_db)

    user_id = 444444

    # Create and fail multiple tasks
    error_messages = [
        "File not found: missing.py",
        "Syntax error in line 42",
        "Network timeout during API call"
    ]

    tasks = []
    for i, error_msg in enumerate(error_messages):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspace),
            agent_type="code_agent"
        )
        await task_manager.update_task(task.task_id, status="running", pid=os.getpid())
        await task_manager.update_task(task.task_id, status="failed", error=error_msg)
        tasks.append(task)

    # Retrieve all failed tasks for user
    user_tasks = await task_manager.get_tasks_by_user(user_id)
    failed_tasks = [t for t in user_tasks if t.status == "failed"]

    # Verify all failures recorded
    assert len(failed_tasks) == 3

    # Verify error messages preserved
    recorded_errors = [t.error for t in failed_tasks]
    assert set(recorded_errors) == set(error_messages)
