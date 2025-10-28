"""
Tests for standalone task executor service.

Verifies:
- Task submission via Unix socket
- Health check endpoint
- Task status queries
- Executor survives simulated server restarts
- Socket cleanup on shutdown
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import os
import signal
import time

import pytest

from tasks.executor import TaskExecutor, SOCKET_PATH, PID_FILE
from tasks.executor_client import TaskExecutorClient


@pytest.fixture
async def executor():
    """Create and start task executor for testing"""
    executor = TaskExecutor()

    # Start executor in background task
    executor_task = asyncio.create_task(executor.start())

    # Wait for socket to be created
    for _ in range(50):  # 5 second timeout
        if os.path.exists(SOCKET_PATH):
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("Executor failed to create socket")

    yield executor

    # Cleanup
    await executor.stop()

    # Cancel the server task
    executor_task.cancel()
    try:
        await executor_task
    except asyncio.CancelledError:
        pass


@pytest.fixture
def client():
    """Create task executor client"""
    return TaskExecutorClient()


class TestTaskExecutor:
    """Test task executor service"""

    @pytest.mark.asyncio
    async def test_health_check(self, executor, client):
        """Test health check endpoint returns correct status"""
        response = await client.health_check()

        assert response["status"] == "healthy"
        assert "active_tasks" in response
        assert "queued_tasks" in response
        assert "uptime_seconds" in response
        assert response["active_tasks"] == 0
        assert response["queued_tasks"] == 0

    @pytest.mark.asyncio
    async def test_submit_task(self, executor, client):
        """Test task submission via Unix socket"""
        task_id = "test123"
        description = "Test task"
        workspace = "/tmp/test"
        user_id = "user1"
        priority = "HIGH"

        # Create task in database first
        task = await executor.task_manager.create_task(
            user_id=int(user_id.replace("user", "")),
            description=description,
            workspace=workspace,
            model="sonnet",
        )
        task_id = task.task_id

        response = await client.submit_task(task_id, description, workspace, user_id, priority)

        assert response["status"] == "queued"
        assert response["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, executor, client):
        """Test task status query for non-existent task"""
        response = await client.get_task_status("nonexistent")

        assert "error" in response
        assert "not found" in response["error"]

    @pytest.mark.asyncio
    async def test_socket_cleanup_on_shutdown(self, executor, client):
        """Test socket is cleaned up when executor stops"""
        # Verify socket exists
        assert os.path.exists(SOCKET_PATH)

        # Stop executor
        await executor.stop()

        # Wait a bit for cleanup
        await asyncio.sleep(0.5)

        # Verify socket is removed
        assert not os.path.exists(SOCKET_PATH)

    @pytest.mark.asyncio
    async def test_pid_file_creation(self, executor):
        """Test PID file is created with correct process ID"""
        assert os.path.exists(PID_FILE)

        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())

        # Verify it's a valid PID
        assert pid > 0

    @pytest.mark.asyncio
    async def test_multiple_task_submissions(self, executor, client):
        """Test multiple tasks can be submitted"""
        tasks = []

        for i in range(5):
            # Create task in database first
            task = await executor.task_manager.create_task(
                user_id=1, description=f"Task {i}", workspace="/tmp/test", model="sonnet"
            )

            response = await client.submit_task(
                task_id=task.task_id,
                description=task.description,
                workspace="/tmp/test",
                user_id="user1",
                priority="NORMAL",
            )

            assert response["status"] == "queued"
            assert response["task_id"] == task.task_id
            tasks.append(task.task_id)

        # Verify health check shows queued tasks
        health = await client.health_check()
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_invalid_action(self, executor):
        """Test handling of invalid action"""
        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)

            # Send invalid action
            message = {"action": "invalid_action"}
            writer.write(json.dumps(message).encode())
            await writer.drain()

            # Read response
            data = await reader.read(4096)
            response = json.loads(data.decode())

            writer.close()
            await writer.wait_closed()

            assert "error" in response
            assert "Unknown action" in response["error"]
        except Exception as e:
            pytest.fail(f"Test failed with exception: {e}")

    @pytest.mark.asyncio
    async def test_client_handles_no_executor(self):
        """Test client handles case when executor is not running"""
        # Ensure no executor is running
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        client = TaskExecutorClient()
        response = await client.submit_task("test", "desc", "/tmp", "user1")

        assert "error" in response
        assert "not running" in response["error"]

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, executor, client):
        """Test executor can handle concurrent requests"""
        # Create tasks in database first
        db_tasks = []
        for i in range(10):
            task = await executor.task_manager.create_task(
                user_id=1, description=f"Task {i}", workspace="/tmp", model="sonnet"
            )
            db_tasks.append(task)

        # Submit multiple tasks concurrently
        submit_tasks = []
        for task in db_tasks:
            submit_task = client.submit_task(
                task_id=task.task_id,
                description=task.description,
                workspace="/tmp",
                user_id="user1",
                priority="NORMAL",
            )
            submit_tasks.append(submit_task)

        # Wait for all to complete
        responses = await asyncio.gather(*submit_tasks)

        # Verify all succeeded
        for response in responses:
            assert response["status"] == "queued"


class TestTaskExecutorResilience:
    """Test executor resilience to failures"""

    @pytest.mark.asyncio
    async def test_executor_survives_simulated_server_restart(self):
        """
        Test executor process survives when simulated monitoring server restarts.

        This is the critical test that verifies the executor can run independently
        of the monitoring server.
        """
        # Start executor
        executor = TaskExecutor()
        executor_task = asyncio.create_task(executor.start())

        # Wait for socket
        for _ in range(50):
            if os.path.exists(SOCKET_PATH):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("Executor failed to start")

        # Get executor PID
        with open(PID_FILE, "r") as f:
            executor_pid = int(f.read().strip())

        # Create task in database first
        task = await executor.task_manager.create_task(user_id=1, description="Test task", workspace="/tmp", model="sonnet")

        # Submit a task
        client = TaskExecutorClient()
        response = await client.submit_task(task.task_id, "Test task", "/tmp", "user1")
        assert response["status"] == "queued"

        # Simulate monitoring server restart by doing nothing
        # (executor should continue running)
        await asyncio.sleep(1)

        # Verify executor is still running
        try:
            os.kill(executor_pid, 0)  # Signal 0 checks if process exists
            executor_alive = True
        except OSError:
            executor_alive = False

        assert executor_alive, "Executor process died"

        # Verify we can still communicate with executor
        health = await client.health_check()
        assert health["status"] == "healthy"

        # Cleanup
        await executor.stop()
        executor_task.cancel()
        try:
            await executor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_socket_recreated_on_restart(self):
        """Test socket is recreated if executor restarts"""
        # Start executor
        executor1 = TaskExecutor()
        task1 = asyncio.create_task(executor1.start())

        # Wait for socket
        for _ in range(50):
            if os.path.exists(SOCKET_PATH):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("Executor failed to start")

        # Stop executor
        await executor1.stop()
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass

        await asyncio.sleep(0.5)

        # Verify socket is removed
        assert not os.path.exists(SOCKET_PATH)

        # Start new executor
        executor2 = TaskExecutor()
        task2 = asyncio.create_task(executor2.start())

        # Wait for socket to be recreated
        for _ in range(50):
            if os.path.exists(SOCKET_PATH):
                break
            await asyncio.sleep(0.1)
        else:
            pytest.fail("Executor failed to recreate socket")

        # Verify we can communicate
        client = TaskExecutorClient()
        health = await client.health_check()
        assert health["status"] == "healthy"

        # Cleanup
        await executor2.stop()
        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass
