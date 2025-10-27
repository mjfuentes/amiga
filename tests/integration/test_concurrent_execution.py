"""
Integration test for concurrent task execution

Tests that multiple tasks can run simultaneously without interference:
- Multiple tasks execute in parallel
- No file conflicts between tasks
- Each task maintains isolated state
- Database operations remain consistent
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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
def isolated_workspaces(tmp_path):
    """Create multiple isolated workspace directories"""
    workspaces = []

    for i in range(3):
        workspace = tmp_path / f"workspace_{i}"
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
        (workspace / "README.md").write_text(f"# Workspace {i}")
        subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=workspace,
            capture_output=True,
            check=True
        )

        workspaces.append(workspace)

    yield workspaces


@pytest.mark.integration
@pytest.mark.asyncio
async def test_three_tasks_run_concurrently(isolated_db, isolated_workspaces):
    """
    Test that 3 tasks can execute concurrently without interference

    Each task:
    1. Creates a unique file
    2. Writes unique content
    3. Commits changes
    4. Completes successfully

    Verifies:
    - All tasks complete without errors
    - Each task's output is isolated
    - No file conflicts occur
    """
    task_manager = TaskManager(isolated_db)

    user_id = 123456
    tasks = []

    # Create 3 tasks in different workspaces
    for i, workspace in enumerate(isolated_workspaces):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Task {i + 1}: Create module_{i}.py",
            model="claude-sonnet-4.5",
            workspace=str(workspace),
            agent_type="code_agent"
        )
        tasks.append((task, workspace))

    # Define async task executor
    async def execute_task(task, workspace):
        """Simulate concurrent task execution"""
        task_id = task.task_id
        task_num = tasks.index((task, workspace))

        # Start execution
        await task_manager.update_task(task_id, status="running", pid=os.getpid() + task_num)

        # Simulate work with small delay
        await asyncio.sleep(0.1)

        # Create unique file
        file_path = workspace / f"module_{task_num}.py"
        file_path.write_text(f"""
def task_{task_num}_function():
    return "Result from task {task_num}"
""")

        # Commit changes
        import subprocess
        subprocess.run(["git", "add", "."], cwd=workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"Add module_{task_num}.py"],
            cwd=workspace,
            capture_output=True
        )

        # Mark as completed
        await task_manager.update_task(
            task_id,
            "completed",
            result=f"Created module_{task_num}.py"
        )

        return task_id

    # Execute all tasks concurrently
    task_ids = await asyncio.gather(*[execute_task(task, workspace) for task, workspace in tasks])

    # Verify all tasks completed successfully
    for task_id in task_ids:
        completed_task = await task_manager.get_task(task_id)
        assert completed_task.status == "completed"
        assert completed_task.error is None

    # Verify each workspace has its unique file
    for i, workspace in enumerate(isolated_workspaces):
        file_path = workspace / f"module_{i}.py"
        assert file_path.exists()
        content = file_path.read_text()
        assert f"task_{i}_function" in content
        assert f"Result from task {i}" in content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_database_writes(isolated_db, isolated_workspaces):
    """
    Test that concurrent database writes don't cause conflicts

    Simulates multiple tasks updating status simultaneously.
    """
    task_manager = TaskManager(isolated_db)

    user_id = 789012
    tasks = []

    # Create 5 tasks
    for i in range(5):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Concurrent task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspaces[0]),
            agent_type="code_agent"
        )
        tasks.append(task)

    # Define async status updater
    async def update_task_status(task, status_sequence):
        """Update task through status sequence"""
        for status in status_sequence:
            await task_manager.update_task(task.task_id, status, pid=os.getpid())
            await asyncio.sleep(0.05)  # Small delay between updates

    # Run concurrent updates
    status_sequence = ["running", "completed"]
    await asyncio.gather(*[update_task_status(task, status_sequence) for task in tasks])

    # Verify all tasks reached completed state
    for task in tasks:
        final_task = await task_manager.get_task(task.task_id)
        assert final_task.status == "completed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_activity_logging(isolated_db, isolated_workspaces):
    """
    Test that concurrent activity log updates work correctly

    Each task adds multiple log entries concurrently.
    """
    task_manager = TaskManager(isolated_db)

    user_id = 345678
    tasks = []

    # Create 3 tasks
    for i in range(3):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Task with logging {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspaces[0]),
            agent_type="code_agent"
        )
        await task_manager.update_task(task.task_id, status="running", pid=os.getpid())
        tasks.append(task)

    # Define async log writer
    async def write_logs(task, num_logs):
        """Write multiple log entries"""
        for j in range(num_logs):
            await task_manager.add_activity(
                task.task_id,
                f"Task {tasks.index(task)}: Activity {j + 1}"
            )
            await asyncio.sleep(0.02)

    # Write logs concurrently
    await asyncio.gather(*[write_logs(task, 5) for task in tasks])

    # Complete tasks
    for task in tasks:
        await task_manager.update_task(task.task_id, status="completed")

    # Verify each task has correct number of log entries
    import json
    for task in tasks:
        final_task = await task_manager.get_task(task.task_id)
        log_entries = json.loads(final_task.activity_log)
        assert len(log_entries) == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_task_queries(isolated_db, isolated_workspaces):
    """
    Test that concurrent task queries work correctly

    Simulates multiple users querying tasks simultaneously.
    """
    task_manager = TaskManager(isolated_db)

    # Create tasks for 3 different users
    user_ids = [111111, 222222, 333333]
    user_tasks = {user_id: [] for user_id in user_ids}

    for user_id in user_ids:
        for i in range(3):
            task = await task_manager.create_task(
                user_id=user_id,
                description=f"User {user_id} task {i + 1}",
                model="claude-sonnet-4.5",
                workspace=str(isolated_workspaces[0]),
                agent_type="code_agent"
            )
            user_tasks[user_id].append(task.task_id)

    # Define async query function
    async def query_user_tasks(user_id):
        """Query tasks for a user"""
        await asyncio.sleep(0.01)  # Small delay
        tasks = await task_manager.get_tasks_by_user(user_id)
        return user_id, tasks

    # Query all users concurrently
    results = await asyncio.gather(*[query_user_tasks(user_id) for user_id in user_ids])

    # Verify each user got their correct tasks
    for user_id, tasks in results:
        assert len(tasks) == 3
        assert all(t.user_id == user_id for t in tasks)
        task_ids = [t.task_id for t in tasks]
        assert set(task_ids) == set(user_tasks[user_id])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mixed_success_and_failure(isolated_db, isolated_workspaces):
    """
    Test concurrent execution with mix of successful and failed tasks

    Verifies that:
    - Failed tasks don't affect successful ones
    - Each task's final state is correct
    - No cross-contamination of errors
    """
    task_manager = TaskManager(isolated_db)

    user_id = 567890
    tasks = []

    # Create 6 tasks
    for i in range(6):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Mixed outcome task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspaces[0]),
            agent_type="code_agent"
        )
        tasks.append(task)

    # Define async executor with conditional failure
    async def execute_with_outcome(task, should_fail):
        """Execute task with predetermined outcome"""
        task_id = task.task_id

        # Start execution
        await task_manager.update_task(task_id, status="running", pid=os.getpid())

        await asyncio.sleep(0.1)

        if should_fail:
            # Fail task
            await task_manager.update_task(
                task_id,
                "failed",
                error=f"Task {tasks.index(task)} failed intentionally"
            )
        else:
            # Complete task
            await task_manager.update_task(
                task_id,
                "completed",
                result=f"Task {tasks.index(task)} completed successfully"
            )

        return task_id, not should_fail

    # Execute with alternating success/failure
    outcomes = [i % 2 == 0 for i in range(6)]  # Even indices succeed, odd fail
    results = await asyncio.gather(*[
        execute_with_outcome(task, should_fail)
        for task, should_fail in zip(tasks, [not o for o in outcomes])
    ])

    # Verify outcomes
    for task_id, should_succeed in results:
        final_task = await task_manager.get_task(task_id)
        if should_succeed:
            assert final_task.status == "completed"
            assert final_task.error is None
            assert "completed successfully" in final_task.result
        else:
            assert final_task.status == "failed"
            assert final_task.result is None
            assert "failed intentionally" in final_task.error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_high_concurrency_stress(isolated_db, isolated_workspaces):
    """
    Stress test with high number of concurrent tasks

    Creates and executes 20 tasks concurrently to test system under load.
    """
    task_manager = TaskManager(isolated_db)

    user_id = 999999
    num_tasks = 20
    tasks = []

    # Create many tasks
    for i in range(num_tasks):
        task = await task_manager.create_task(
            user_id=user_id,
            description=f"Stress test task {i + 1}",
            model="claude-sonnet-4.5",
            workspace=str(isolated_workspaces[i % 3]),  # Distribute across workspaces
            agent_type="code_agent"
        )
        tasks.append(task)

    # Define async executor
    async def execute_stress_task(task):
        """Execute task with minimal work"""
        await task_manager.update_task(task.task_id, status="running", pid=os.getpid())
        await asyncio.sleep(0.05)
        await task_manager.update_task(task.task_id, status="completed", result="OK")
        return task.task_id

    # Execute all tasks concurrently
    start_time = time.time()
    task_ids = await asyncio.gather(*[execute_stress_task(task) for task in tasks])
    elapsed = time.time() - start_time

    # Verify all completed
    for task_id in task_ids:
        final_task = await task_manager.get_task(task_id)
        assert final_task.status == "completed"

    # Verify reasonable execution time (should be < 2 seconds for 20 tasks)
    assert elapsed < 2.0, f"High concurrency test took too long: {elapsed:.2f}s"
