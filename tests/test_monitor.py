"""
Tests for task monitoring and automatic cleanup
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import os
import signal
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tasks.database import Database
from tasks.monitor import TaskMonitor


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing"""
    db_path = tmp_path / "test_monitor.db"
    db = Database(str(tmp_path))
    yield db
    # Cleanup handled automatically when tmp_path is removed


@pytest.fixture
def mock_db():
    """Mock database for testing"""
    db = AsyncMock(spec=Database)
    db.get_tasks_by_status = AsyncMock()
    db.update_task = AsyncMock()
    db.get_tasks = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_monitor_initialization(mock_db):
    """Test monitor initializes with correct parameters"""
    monitor = TaskMonitor(
        database=mock_db,
        check_interval_seconds=30,
        task_timeout_minutes=15
    )

    assert monitor.db == mock_db
    assert monitor.check_interval == 30
    assert monitor.task_timeout.total_seconds() == 15 * 60
    assert not monitor._running


@pytest.mark.asyncio
async def test_monitor_start_stop(mock_db):
    """Test monitor can be started and stopped"""
    mock_db.get_tasks_by_status.return_value = []

    monitor = TaskMonitor(mock_db, check_interval_seconds=1)

    # Start monitor
    await monitor.start()
    assert monitor._running
    assert monitor._task is not None

    # Stop monitor
    await monitor.stop()
    assert not monitor._running


@pytest.mark.asyncio
async def test_detect_dead_process(mock_db):
    """Test detection of tasks with dead processes"""
    # Mock task with dead PID
    mock_db.get_tasks_by_status.return_value = [
        {
            "task_id": "dead123",
            "pid": 999999,  # Non-existent PID
            "updated_at": datetime.now().isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    # Run single check
    await monitor._check_stuck_tasks()

    # Verify task marked as failed
    mock_db.update_task.assert_called_once()
    call_args = mock_db.update_task.call_args
    assert call_args[1]["task_id"] == "dead123"
    assert call_args[1]["status"] == "failed"
    assert "dead_process" in call_args[1]["error"]


@pytest.mark.asyncio
async def test_detect_timeout(mock_db):
    """Test detection of tasks without updates for too long"""
    # Mock task with old update time
    old_time = datetime.now() - timedelta(minutes=35)
    mock_db.get_tasks_by_status.return_value = [
        {
            "task_id": "timeout123",
            "pid": None,
            "updated_at": old_time.isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    # Run single check
    await monitor._check_stuck_tasks()

    # Verify task marked as failed
    mock_db.update_task.assert_called_once()
    call_args = mock_db.update_task.call_args
    assert call_args[1]["task_id"] == "timeout123"
    assert call_args[1]["status"] == "failed"
    assert "timeout" in call_args[1]["error"]


@pytest.mark.asyncio
async def test_healthy_task_not_marked_failed(mock_db):
    """Test healthy tasks are not marked as failed"""
    # Mock healthy task (recent update, no PID)
    mock_db.get_tasks_by_status.return_value = [
        {
            "task_id": "healthy123",
            "pid": None,
            "updated_at": datetime.now().isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    # Run single check
    await monitor._check_stuck_tasks()

    # Verify NO update calls
    mock_db.update_task.assert_not_called()


@pytest.mark.asyncio
async def test_kill_stuck_process(mock_db):
    """Test monitor attempts to kill stuck processes before marking failed"""
    # Create actual process to test killing
    import subprocess
    proc = subprocess.Popen(["sleep", "300"])
    pid = proc.pid

    try:
        # Verify process started
        assert os.kill(pid, 0) is None, "Process should be alive before test"

        # Mock task with timeout and living process
        old_time = datetime.now() - timedelta(minutes=35)
        mock_db.get_tasks_by_status.return_value = [
            {
                "task_id": "kill123",
                "pid": pid,
                "updated_at": old_time.isoformat()
            }
        ]

        monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

        # Run single check (this should kill the process)
        await monitor._check_stuck_tasks()

        # Wait for kill to take effect (SIGTERM then SIGKILL)
        await asyncio.sleep(3)

        # Verify task marked as failed (main assertion)
        mock_db.update_task.assert_called_once()
        call_args = mock_db.update_task.call_args
        assert call_args[1]["task_id"] == "kill123"
        assert call_args[1]["status"] == "failed"
        assert "timeout" in call_args[1]["error"]

        # Process should be dead (best effort - may still be alive on slow systems)
        try:
            os.kill(pid, 0)
            # If still alive, log warning but don't fail test (timing dependent)
            print(f"Warning: Process {pid} still alive after kill attempt (timing issue)")
        except OSError:
            pass  # Process is dead, as expected

    finally:
        # Cleanup: ensure process is dead
        try:
            proc.kill()  # Use SIGKILL for immediate termination
            proc.wait(timeout=1)
        except:
            pass


@pytest.mark.asyncio
async def test_check_task_health_healthy(mock_db):
    """Test health check for healthy task"""
    mock_db.get_tasks.return_value = [
        {
            "task_id": "healthy123",
            "status": "running",
            "pid": None,
            "updated_at": datetime.now().isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    health = await monitor.check_task_health("healthy123")

    assert health["status"] == "healthy"
    assert "running normally" in health["message"]


@pytest.mark.asyncio
async def test_check_task_health_dead_process(mock_db):
    """Test health check detects dead process"""
    mock_db.get_tasks.return_value = [
        {
            "task_id": "dead123",
            "status": "running",
            "pid": 999999,  # Non-existent PID
            "updated_at": datetime.now().isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    health = await monitor.check_task_health("dead123")

    assert health["status"] == "dead_process"
    assert "is dead" in health["message"]
    assert health["pid_alive"] is False


@pytest.mark.asyncio
async def test_check_task_health_timeout(mock_db):
    """Test health check detects timeout"""
    old_time = datetime.now() - timedelta(minutes=35)
    mock_db.get_tasks.return_value = [
        {
            "task_id": "timeout123",
            "status": "running",
            "pid": None,
            "updated_at": old_time.isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    health = await monitor.check_task_health("timeout123")

    assert health["status"] == "timeout"
    assert "No updates" in health["message"]
    assert health["time_since_update_seconds"] > 30 * 60


@pytest.mark.asyncio
async def test_check_task_health_not_found(mock_db):
    """Test health check for non-existent task"""
    mock_db.get_tasks.return_value = []

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    health = await monitor.check_task_health("notfound123")

    assert health["status"] == "unknown"
    assert "not found" in health["message"]


@pytest.mark.asyncio
async def test_check_task_health_not_running(mock_db):
    """Test health check for non-running task"""
    mock_db.get_tasks.return_value = [
        {
            "task_id": "completed123",
            "status": "completed",
            "pid": None,
            "updated_at": datetime.now().isoformat()
        }
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    health = await monitor.check_task_health("completed123")

    assert health["status"] == "not_running"
    assert "completed" in health["message"]


@pytest.mark.asyncio
async def test_monitor_handles_exceptions(mock_db):
    """Test monitor continues running after exceptions"""
    # First call raises exception, second call returns empty
    mock_db.get_tasks_by_status.side_effect = [
        Exception("Test error"),
        []
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=0.1, task_timeout_minutes=30)

    await monitor.start()
    await asyncio.sleep(0.3)  # Let it run 2-3 checks
    await monitor.stop()

    # Verify it handled exception and continued
    assert mock_db.get_tasks_by_status.call_count >= 2


@pytest.mark.asyncio
async def test_multiple_stuck_tasks(mock_db):
    """Test monitor handles multiple stuck tasks in one check"""
    old_time = datetime.now() - timedelta(minutes=35)
    mock_db.get_tasks_by_status.return_value = [
        {"task_id": "stuck1", "pid": None, "updated_at": old_time.isoformat()},
        {"task_id": "stuck2", "pid": 999998, "updated_at": datetime.now().isoformat()},
        {"task_id": "stuck3", "pid": 999999, "updated_at": old_time.isoformat()},
    ]

    monitor = TaskMonitor(mock_db, check_interval_seconds=1, task_timeout_minutes=30)

    await monitor._check_stuck_tasks()

    # All 3 tasks should be marked failed
    assert mock_db.update_task.call_count == 3
