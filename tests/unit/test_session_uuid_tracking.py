"""
Regression tests for session_uuid tracking in monitoring server

Tests that ClaudeSessionPool receives usage_tracker and that session_uuid
is properly set in the database for tool usage correlation.

This prevents the bug where missing usage_tracker caused session_uuid to remain
NULL, breaking tool usage correlation in the dashboard.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSessionUuidTracking:
    """Test suite for session_uuid tracking in ClaudeSessionPool"""

    def test_claude_pool_receives_usage_tracker(self):
        """Test that ClaudeSessionPool is initialized with usage_tracker in monitoring_server"""
        # Read the monitoring/server.py source code to verify the initialization
        monitoring_server_path = Path(__file__).parent.parent / "monitoring" / "server.py"
        source = monitoring_server_path.read_text()

        # Check that ClaudeSessionPool initialization includes usage_tracker parameter
        # Look for the pattern: ClaudeSessionPool(... usage_tracker=tool_usage_tracker)
        import re

        # Find ClaudeSessionPool initialization
        claude_pool_pattern = r"claude_pool\s*=\s*ClaudeSessionPool\([^)]*\)"
        matches = re.findall(claude_pool_pattern, source, re.MULTILINE | re.DOTALL)

        assert len(matches) > 0, "Could not find ClaudeSessionPool initialization in monitoring_server.py"

        initialization = matches[0]
        assert (
            "usage_tracker" in initialization
        ), f"usage_tracker parameter is missing from ClaudeSessionPool initialization: {initialization}"
        assert (
            "tool_usage_tracker" in initialization
        ), f"usage_tracker should be set to tool_usage_tracker: {initialization}"

    @pytest.mark.asyncio
    async def test_session_start_updates_session_uuid(self):
        """Test that ClaudeInteractiveSession.start() updates session_uuid in database"""
        from claude.code_cli import ClaudeInteractiveSession
        from tasks.tracker import ToolUsageTracker

        # Create mocks
        mock_db = AsyncMock()
        mock_usage_tracker = MagicMock(spec=ToolUsageTracker)
        mock_usage_tracker.db = mock_db
        mock_usage_tracker.record_status_change = MagicMock()

        # Create session with usage_tracker
        workspace = Path("/tmp/test_workspace")
        session = ClaudeInteractiveSession(workspace=workspace, usage_tracker=mock_usage_tracker)

        # Mock subprocess creation
        with patch("claude.code_cli.asyncio.create_subprocess_exec") as mock_exec:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_exec.return_value = mock_process

            # Start session
            task_id = "test_task_123"
            result = await session.start(task_id)

            assert result is True, "Session start should succeed"

            # Verify update_task was called with session_uuid
            mock_db.update_task.assert_called_once()
            call_args = mock_db.update_task.call_args

            assert call_args is not None, "update_task should have been called"
            assert "task_id" in call_args[1], "task_id parameter is missing"
            assert call_args[1]["task_id"] == task_id, f"task_id should be {task_id}"
            assert "session_uuid" in call_args[1], "session_uuid parameter is missing"
            assert call_args[1]["session_uuid"] is not None, "session_uuid should not be None"
            assert "pid" in call_args[1], "pid parameter is missing"
            assert call_args[1]["pid"] == 12345, "pid should match process PID"

            # Verify session_uuid format (should be a valid UUID)
            session_uuid = call_args[1]["session_uuid"]
            import uuid

            try:
                uuid.UUID(session_uuid)
            except ValueError:
                pytest.fail(f"session_uuid is not a valid UUID: {session_uuid}")

    @pytest.mark.asyncio
    async def test_session_warns_when_usage_tracker_missing(self):
        """Test that ClaudeInteractiveSession warns when usage_tracker is None"""
        from claude.code_cli import ClaudeInteractiveSession

        # Create session WITHOUT usage_tracker
        workspace = Path("/tmp/test_workspace")
        session = ClaudeInteractiveSession(workspace=workspace, usage_tracker=None)

        # Mock subprocess creation
        with (
            patch("claude.code_cli.asyncio.create_subprocess_exec") as mock_exec,
            patch("claude.code_cli.logger") as mock_logger,
        ):
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_exec.return_value = mock_process

            # Start session
            task_id = "test_task_456"
            result = await session.start(task_id)

            assert result is True, "Session should start even without usage_tracker"

            # Verify warning was logged
            warning_calls = list(mock_logger.warning.call_args_list)
            assert len(warning_calls) > 0, "Should have logged a warning"

            warning_message = str(warning_calls[0])
            assert "usage_tracker is None" in warning_message, "Warning should mention missing usage_tracker"
            assert "session_uuid will NOT be tracked" in warning_message, "Warning should explain the impact"

    @pytest.mark.asyncio
    async def test_session_pool_passes_usage_tracker_to_sessions(self):
        """Test that ClaudeSessionPool passes usage_tracker to created sessions"""
        from claude.code_cli import ClaudeSessionPool
        from tasks.tracker import ToolUsageTracker

        # Create mock usage_tracker
        mock_usage_tracker = MagicMock(spec=ToolUsageTracker)
        mock_usage_tracker.db = AsyncMock()
        mock_usage_tracker.record_status_change = MagicMock()
        mock_usage_tracker.record_workflow_assignment = AsyncMock()

        # Create pool with usage_tracker
        pool = ClaudeSessionPool(max_concurrent=3, usage_tracker=mock_usage_tracker)

        # Mock ClaudeInteractiveSession to capture initialization
        with (
            patch("claude.code_cli.ClaudeInteractiveSession") as mock_session_class,
            patch("claude.code_cli.get_workflow_router") as mock_router,
        ):
            mock_session_instance = AsyncMock()
            mock_session_instance.start = AsyncMock(return_value=True)
            mock_session_instance.send_message_with_streaming = AsyncMock(return_value="Task completed")
            mock_session_instance.terminate = AsyncMock()
            mock_session_instance.process = MagicMock()
            mock_session_instance.process.pid = 12345
            mock_session_class.return_value = mock_session_instance

            mock_router_instance = MagicMock()
            mock_router_instance.route_task = MagicMock(return_value="/workflows:code-task")
            mock_router.return_value = mock_router_instance

            # Execute task
            task_id = "test_task_789"
            workspace = Path("/tmp/test_workspace")
            success, result, pid, workflow = await pool.execute_task(
                task_id=task_id, description="Test task", workspace=workspace
            )

            # Verify ClaudeInteractiveSession was created with usage_tracker
            mock_session_class.assert_called_once()
            call_kwargs = mock_session_class.call_args[1]
            assert "usage_tracker" in call_kwargs, "usage_tracker parameter is missing"
            assert call_kwargs["usage_tracker"] == mock_usage_tracker, "usage_tracker should be passed to session"

    @pytest.mark.asyncio
    async def test_defensive_logging_confirms_session_uuid_set(self):
        """Test that defensive logging confirms session_uuid is set successfully"""
        from claude.code_cli import ClaudeInteractiveSession
        from tasks.tracker import ToolUsageTracker

        # Create mocks
        mock_db = AsyncMock()
        mock_usage_tracker = MagicMock(spec=ToolUsageTracker)
        mock_usage_tracker.db = mock_db
        mock_usage_tracker.record_status_change = MagicMock()

        # Create session
        workspace = Path("/tmp/test_workspace")
        session = ClaudeInteractiveSession(workspace=workspace, usage_tracker=mock_usage_tracker)

        # Mock subprocess creation
        with (
            patch("claude.code_cli.asyncio.create_subprocess_exec") as mock_exec,
            patch("claude.code_cli.logger") as mock_logger,
        ):
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_exec.return_value = mock_process

            # Start session
            task_id = "test_task_999"
            result = await session.start(task_id)

            assert result is True, "Session start should succeed"

            # Verify confirmation logging
            info_calls = list(mock_logger.info.call_args_list)
            confirmation_logs = [call for call in info_calls if "Successfully set session_uuid" in str(call)]

            assert len(confirmation_logs) > 0, "Should have logged session_uuid confirmation"
            confirmation_message = str(confirmation_logs[0])
            assert "for tool usage correlation" in confirmation_message, "Should mention purpose"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
