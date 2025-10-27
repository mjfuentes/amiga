"""
Tests for Claude interactive session with session UUID extraction
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude.code_cli import ClaudeInteractiveSession


class TestSessionUUIDExtraction:
    """Tests for extracting Claude's actual session UUID"""

    @pytest.mark.skip(reason="UUID extraction changed from stdout to logs/sessions/ directory with -p flag")
    @pytest.mark.asyncio
    async def test_extract_session_uuid_success(self):
        """Test successful extraction of session UUID from stdout"""
        # Create session
        session = ClaudeInteractiveSession(workspace=Path("/tmp/test"), model="sonnet")

        # Mock process with stdout containing UUID
        mock_process = MagicMock()
        mock_stdout = AsyncMock()
        mock_stdout.read = AsyncMock(
            return_value=b"Starting session with ID: 1d2d4146-3f9f-444b-b37f-85abc6386a70\nReady..."
        )
        mock_process.stdout = mock_stdout
        session.process = mock_process

        # Extract UUID
        result = await session._extract_claude_session_id()

        # Verify
        assert result == "1d2d4146-3f9f-444b-b37f-85abc6386a70"

    @pytest.mark.asyncio
    async def test_extract_session_uuid_no_match(self):
        """Test extraction fails when no UUID in output"""
        session = ClaudeInteractiveSession(workspace=Path("/tmp/test"), model="sonnet")

        # Mock process with stdout containing no UUID
        mock_process = MagicMock()
        mock_stdout = AsyncMock()
        mock_stdout.read = AsyncMock(return_value=b"Starting session...\nReady...")
        mock_process.stdout = mock_stdout
        session.process = mock_process

        # Extract UUID
        result = await session._extract_claude_session_id()

        # Verify returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_session_uuid_timeout(self):
        """Test extraction handles timeout gracefully"""
        session = ClaudeInteractiveSession(workspace=Path("/tmp/test"), model="sonnet")

        # Mock process with stdout that times out
        mock_process = MagicMock()
        mock_stdout = AsyncMock()

        async def slow_read(n):
            await asyncio.sleep(10)  # Longer than 3s timeout
            return b""

        mock_stdout.read = slow_read
        mock_process.stdout = mock_stdout
        session.process = mock_process

        # Extract UUID (should timeout)
        result = await session._extract_claude_session_id()

        # Verify returns None on timeout
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_session_uuid_no_process(self):
        """Test extraction when process not started"""
        session = ClaudeInteractiveSession(workspace=Path("/tmp/test"), model="sonnet")
        session.process = None

        # Extract UUID
        result = await session._extract_claude_session_id()

        # Verify returns None
        assert result is None


class TestStdinConfiguration:
    """Tests for stdin configuration in subprocess creation"""

    @pytest.mark.asyncio
    async def test_start_configures_stdin_devnull(self):
        """Test that start() creates subprocess with stdin=DEVNULL for -p mode"""
        workspace = Path("/tmp/test")
        session = ClaudeInteractiveSession(workspace=workspace, model="sonnet")

        # Mock usage tracker
        mock_tracker = MagicMock()
        mock_tracker.record_status_change = MagicMock()
        mock_tracker.db = MagicMock()
        mock_tracker.db.update_task = AsyncMock()
        session.usage_tracker = mock_tracker

        # Mock process creation to verify stdin parameter
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_exec.return_value = mock_process

            # Mock UUID extraction to avoid filesystem dependency
            with patch.object(session, "_extract_claude_session_id", return_value="test-uuid"):
                # Start session with prompt (uses -p mode)
                await session.start(task_id="test123", prompt="test prompt")

                # Verify subprocess was created with stdin=DEVNULL for -p mode
                mock_exec.assert_called_once()
                call_kwargs = mock_exec.call_args[1]
                assert "stdin" in call_kwargs
                assert call_kwargs["stdin"] == asyncio.subprocess.DEVNULL
                assert call_kwargs["stdout"] == asyncio.subprocess.PIPE
                assert call_kwargs["stderr"] == asyncio.subprocess.PIPE

    @pytest.mark.asyncio
    async def test_slash_command_converted_to_plain_text(self):
        """Test that slash commands are converted to plain text instructions for -p mode"""
        workspace = Path("/tmp/test")
        session = ClaudeInteractiveSession(workspace=workspace, model="sonnet")

        # Mock usage tracker
        mock_tracker = MagicMock()
        mock_tracker.record_status_change = MagicMock()
        mock_tracker.db = MagicMock()
        mock_tracker.db.update_task = AsyncMock()
        session.usage_tracker = mock_tracker

        # Mock process creation
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_exec.return_value = mock_process

            # Mock UUID extraction
            with patch.object(session, "_extract_claude_session_id", return_value="test-uuid"):
                # Start session with slash command prompt
                test_prompt = "/workflows:code-task Fix bug in auth.py"
                await session.start(task_id="test123", prompt=test_prompt)

                # Verify slash command was converted to plain text instruction
                mock_exec.assert_called_once()
                cmd_args = mock_exec.call_args[0]

                # Last argument should be the converted instruction
                assert len(cmd_args) > 0
                last_arg = cmd_args[-1]
                assert "Use the code-task workflow to complete this task:" in last_arg
                assert "Fix bug in auth.py" in last_arg
                assert "/workflows:" not in last_arg  # Slash command removed

    @pytest.mark.asyncio
    async def test_plain_prompt_passed_unchanged(self):
        """Test that non-slash-command prompts are passed as-is"""
        workspace = Path("/tmp/test")
        session = ClaudeInteractiveSession(workspace=workspace, model="sonnet")

        # Mock usage tracker
        mock_tracker = MagicMock()
        mock_tracker.record_status_change = MagicMock()
        mock_tracker.db = MagicMock()
        mock_tracker.db.update_task = AsyncMock()
        session.usage_tracker = mock_tracker

        # Mock process creation
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_process.stdout = AsyncMock()
            mock_process.stderr = AsyncMock()
            mock_exec.return_value = mock_process

            # Mock UUID extraction
            with patch.object(session, "_extract_claude_session_id", return_value="test-uuid"):
                # Start session with regular prompt
                test_prompt = "Fix bug in auth.py"
                await session.start(task_id="test123", prompt=test_prompt)

                # Verify prompt was passed unchanged
                mock_exec.assert_called_once()
                cmd_args = mock_exec.call_args[0]

                # Last argument should be the original prompt
                assert len(cmd_args) > 0
                last_arg = cmd_args[-1]
                assert last_arg == test_prompt


class TestSessionUUIDCorrelation:
    """Tests for session UUID database correlation"""

    @pytest.mark.asyncio
    async def test_start_uses_actual_uuid(self):
        """Test that start() uses extracted UUID for database update"""
        workspace = Path("/tmp/test")
        session = ClaudeInteractiveSession(workspace=workspace, model="sonnet")

        # Mock usage tracker
        mock_tracker = MagicMock()
        mock_tracker.record_status_change = MagicMock()
        mock_tracker.db = MagicMock()
        mock_tracker.db.update_task = AsyncMock()
        session.usage_tracker = mock_tracker

        # Mock process creation
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_process.stdout = AsyncMock()

            # Mock stdout to return UUID
            mock_process.stdout.read = AsyncMock(return_value=b"Session: a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d\n")

            mock_exec.return_value = mock_process

            # Mock _extract_claude_session_id to return specific UUID
            with patch.object(
                session, "_extract_claude_session_id", return_value="a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
            ):
                # Start session
                await session.start(task_id="test123")

                # Verify update_task called with actual UUID
                mock_tracker.db.update_task.assert_called_once()
                call_kwargs = mock_tracker.db.update_task.call_args[1]
                assert call_kwargs["task_id"] == "test123"
                assert call_kwargs["session_uuid"] == "a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
                assert call_kwargs["pid"] == 12345

    @pytest.mark.asyncio
    async def test_start_fallback_on_extraction_failure(self):
        """Test that start() uses fallback UUID when extraction fails"""
        workspace = Path("/tmp/test")
        session = ClaudeInteractiveSession(workspace=workspace, model="sonnet")

        # Mock usage tracker
        mock_tracker = MagicMock()
        mock_tracker.record_status_change = MagicMock()
        mock_tracker.db = MagicMock()
        mock_tracker.db.update_task = AsyncMock()
        session.usage_tracker = mock_tracker

        # Mock process creation
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_process.stdout = AsyncMock()
            mock_exec.return_value = mock_process

            # Mock _extract_claude_session_id to return None (extraction failed)
            with patch.object(session, "_extract_claude_session_id", return_value=None):
                # Start session
                await session.start(task_id="test123")

                # Verify update_task called with fallback UUID (deterministic from task_id)
                mock_tracker.db.update_task.assert_called_once()
                call_kwargs = mock_tracker.db.update_task.call_args[1]
                assert call_kwargs["task_id"] == "test123"
                # Fallback UUID is deterministic UUID5 from task_id
                assert call_kwargs["session_uuid"] is not None
                assert len(call_kwargs["session_uuid"]) == 36  # Valid UUID format


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
