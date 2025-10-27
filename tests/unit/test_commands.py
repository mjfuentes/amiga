"""
Tests for web chat command handling.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, Mock
from monitoring.commands import CommandHandler
from tasks.manager import Task


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = Mock()
    manager.get_active_tasks = Mock(return_value=[])
    manager.get_user_tasks = Mock(return_value=[])
    manager.get_task = Mock(return_value=None)
    manager.stop_task = AsyncMock(return_value=(True, "Task stopped"))
    return manager


@pytest.fixture
def command_handler(mock_task_manager):
    """Create a command handler instance."""
    return CommandHandler(mock_task_manager)


@pytest.mark.asyncio
async def test_handle_stop_no_args(command_handler, mock_task_manager):
    """Test /stop command without task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.description = "Test task"
    
    mock_task_manager.get_active_tasks.return_value = [mock_task]
    
    result = await command_handler.handle_command("/stop", "12345")
    
    assert result["success"] is True
    assert "Active Tasks" in result["message"]
    assert "#abc123" in result["message"]
    assert "Usage:" in result["message"]


@pytest.mark.asyncio
async def test_handle_stop_with_task_id(command_handler, mock_task_manager):
    """Test /stop command with task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.user_id = 12345
    mock_task.status = "running"
    mock_task.description = "Test task"
    
    mock_task_manager.get_task.return_value = mock_task
    mock_task_manager.stop_task.return_value = (True, "Stopped")
    
    result = await command_handler.handle_command("/stop abc123", "12345")
    
    assert result["success"] is True
    assert "Task Stopped" in result["message"]
    assert "#abc123" in result["message"]
    mock_task_manager.stop_task.assert_called_once_with("abc123")


@pytest.mark.asyncio
async def test_handle_stop_task_not_found(command_handler, mock_task_manager):
    """Test /stop command with nonexistent task ID."""
    mock_task_manager.get_task.return_value = None
    
    result = await command_handler.handle_command("/stop xyz789", "12345")
    
    assert result["success"] is False
    assert "not found" in result["message"]


@pytest.mark.asyncio
async def test_handle_stop_wrong_user(command_handler, mock_task_manager):
    """Test /stop command on another user's task."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.user_id = 99999  # Different user
    
    mock_task_manager.get_task.return_value = mock_task
    
    result = await command_handler.handle_command("/stop abc123", "12345")
    
    assert result["success"] is False
    assert "permission" in result["message"].lower()


@pytest.mark.asyncio
async def test_handle_stopall(command_handler, mock_task_manager):
    """Test /stopall command."""
    mock_task1 = Mock(spec=Task)
    mock_task1.task_id = "abc123"
    mock_task2 = Mock(spec=Task)
    mock_task2.task_id = "def456"
    
    mock_task_manager.get_active_tasks.return_value = [mock_task1, mock_task2]
    mock_task_manager.stop_task.return_value = (True, "Stopped")
    
    result = await command_handler.handle_command("/stopall", "12345")
    
    assert result["success"] is True
    assert "Stopped 2 task(s)" in result["message"]
    assert mock_task_manager.stop_task.call_count == 2


@pytest.mark.asyncio
async def test_handle_retry_no_args(command_handler, mock_task_manager):
    """Test /retry command without task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.description = "Failed task"
    mock_task.error = "Some error occurred"
    
    mock_task_manager.get_user_tasks.return_value = [mock_task]
    
    result = await command_handler.handle_command("/retry", "12345")
    
    assert result["success"] is True
    assert "Failed Tasks" in result["message"]
    assert "#abc123" in result["message"]


@pytest.mark.asyncio
async def test_handle_retry_with_task_id(command_handler, mock_task_manager):
    """Test /retry command with task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.user_id = 12345
    mock_task.status = "failed"
    
    mock_task_manager.get_task.return_value = mock_task
    
    result = await command_handler.handle_command("/retry abc123", "12345")
    
    assert result["success"] is True
    assert "Retrying task" in result["message"]
    assert result["data"]["action"] == "retry"
    assert result["data"]["task"] == mock_task


@pytest.mark.asyncio
async def test_handle_view_no_args(command_handler, mock_task_manager):
    """Test /view command without task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.description = "Completed task"
    
    mock_task_manager.get_user_tasks.return_value = [mock_task]
    
    result = await command_handler.handle_command("/view", "12345")
    
    assert result["success"] is True
    assert "Recent Completed Tasks" in result["message"]
    assert "#abc123" in result["message"]


@pytest.mark.asyncio
async def test_handle_view_with_task_id(command_handler, mock_task_manager):
    """Test /view command with task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.user_id = 12345
    mock_task.description = "Completed task"
    mock_task.result = "Task completed successfully"
    
    mock_task_manager.get_task.return_value = mock_task
    
    result = await command_handler.handle_command("/view abc123", "12345")
    
    assert result["success"] is True
    assert "Task #abc123 Result" in result["message"]
    assert "Task completed successfully" in result["message"]
    assert result["data"]["result"] == mock_task.result


@pytest.mark.asyncio
async def test_handle_unknown_command(command_handler):
    """Test handling of unknown command."""
    result = await command_handler.handle_command("/unknown", "12345")
    
    assert result["success"] is False
    assert "Unknown command" in result["message"]


@pytest.mark.asyncio
async def test_handle_stop_with_hash_prefix(command_handler, mock_task_manager):
    """Test /stop command with # prefix in task ID."""
    mock_task = Mock(spec=Task)
    mock_task.task_id = "abc123"
    mock_task.user_id = 12345
    mock_task.status = "running"
    mock_task.description = "Test task"
    
    mock_task_manager.get_task.return_value = mock_task
    mock_task_manager.stop_task.return_value = (True, "Stopped")
    
    result = await command_handler.handle_command("/stop #abc123", "12345")
    
    assert result["success"] is True
    # Should strip # and find task
    mock_task_manager.get_task.assert_called_once_with("abc123")
