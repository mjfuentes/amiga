"""Tests for claude/sdk_hooks.py hook callbacks."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from claude.sdk_hooks import (
    build_hooks,
    create_notification_hook,
    create_post_tool_failure_hook,
    create_post_tool_hook,
    create_pre_tool_hook,
    create_stop_hook,
    create_subagent_start_hook,
    create_subagent_stop_hook,
    _safe_get,
)


@pytest.fixture
def mock_tracker():
    """Create a mock ToolUsageTracker."""
    tracker = MagicMock()
    tracker.record_tool_start = MagicMock()
    tracker.record_tool_complete = MagicMock()
    tracker.record_status_change = MagicMock()
    return tracker


@pytest.fixture
def hook_context():
    """Create a minimal HookContext."""
    return {"signal": None}


TASK_ID = "test-task-123"


class TestSafeGet:
    def test_normal_dict(self):
        assert _safe_get({"key": "value"}, "key") == "value"

    def test_missing_key(self):
        assert _safe_get({"key": "value"}, "missing", "default") == "default"

    def test_none_input(self):
        assert _safe_get(None, "key", "default") == "default"

    def test_non_dict_input(self):
        assert _safe_get(42, "key", "default") == "default"


class TestSubagentStartHook:
    @pytest.mark.asyncio
    async def test_logs_subagent_start(self, mock_tracker, hook_context):
        callback = create_subagent_start_hook(mock_tracker, TASK_ID)
        hook_input = {
            "agent_type": "code_agent",
            "agent_id": "agent-001",
            "session_id": "sess-1",
            "transcript_path": "/tmp/transcript",
            "cwd": "/tmp",
            "hook_event_name": "SubagentStart",
        }

        result = await callback(hook_input, None, hook_context)

        assert result == {}
        mock_tracker.record_tool_start.assert_called_once_with(
            TASK_ID,
            "SubagentStart:code_agent",
            {"agent_type": "code_agent", "agent_id": "agent-001"},
        )

    @pytest.mark.asyncio
    async def test_handles_missing_fields(self, mock_tracker, hook_context):
        callback = create_subagent_start_hook(mock_tracker, TASK_ID)
        result = await callback({}, None, hook_context)

        assert result == {}
        mock_tracker.record_tool_start.assert_called_once_with(
            TASK_ID,
            "SubagentStart:unknown",
            {"agent_type": "unknown", "agent_id": "unknown"},
        )

    @pytest.mark.asyncio
    async def test_handles_none_input(self, mock_tracker, hook_context):
        callback = create_subagent_start_hook(mock_tracker, TASK_ID)
        result = await callback(None, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_tracker_error(self, mock_tracker, hook_context):
        mock_tracker.record_tool_start.side_effect = RuntimeError("db error")
        callback = create_subagent_start_hook(mock_tracker, TASK_ID)

        result = await callback({"agent_type": "x", "agent_id": "y"}, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_tracker(self, hook_context):
        callback = create_subagent_start_hook(None, TASK_ID)
        result = await callback({"agent_type": "x", "agent_id": "y"}, None, hook_context)
        assert result == {}


class TestSubagentStopHook:
    @pytest.mark.asyncio
    async def test_logs_subagent_stop(self, mock_tracker, hook_context):
        callback = create_subagent_stop_hook(mock_tracker, TASK_ID)
        hook_input = {
            "agent_type": "code_agent",
            "agent_id": "agent-001",
            "last_assistant_message": "Done implementing feature.",
            "session_id": "sess-1",
            "transcript_path": "/tmp/transcript",
            "cwd": "/tmp",
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_transcript_path": "/tmp/agent_transcript",
        }

        result = await callback(hook_input, None, hook_context)

        assert result == {}
        mock_tracker.record_tool_complete.assert_called_once_with(
            task_id=TASK_ID,
            tool_name="SubagentStop:code_agent",
            duration_ms=0.0,
            success=True,
            error=None,
            parameters={
                "agent_type": "code_agent",
                "agent_id": "agent-001",
                "last_assistant_message": "Done implementing feature.",
                "agent_transcript_path": "/tmp/agent_transcript",
            },
        )

    @pytest.mark.asyncio
    async def test_records_failure_on_error(self, mock_tracker, hook_context):
        callback = create_subagent_stop_hook(mock_tracker, TASK_ID)
        hook_input = {
            "agent_type": "code_agent",
            "agent_id": "agent-003",
            "last_assistant_message": "Failed to complete.",
            "error": "Agent exceeded token limit",
        }

        result = await callback(hook_input, None, hook_context)

        assert result == {}
        mock_tracker.record_tool_complete.assert_called_once_with(
            task_id=TASK_ID,
            tool_name="SubagentStop:code_agent",
            duration_ms=0.0,
            success=False,
            error="Agent exceeded token limit",
            parameters={
                "agent_type": "code_agent",
                "agent_id": "agent-003",
                "last_assistant_message": "Failed to complete.",
            },
        )

    @pytest.mark.asyncio
    async def test_truncates_long_message(self, mock_tracker, hook_context):
        callback = create_subagent_stop_hook(mock_tracker, TASK_ID)
        long_message = "x" * 1000
        hook_input = {
            "agent_type": "research",
            "agent_id": "agent-002",
            "last_assistant_message": long_message,
        }

        await callback(hook_input, None, hook_context)

        call_args = mock_tracker.record_tool_complete.call_args
        stored_msg = call_args[1]["parameters"]["last_assistant_message"]
        assert len(stored_msg) == 500

    @pytest.mark.asyncio
    async def test_handles_none_input(self, mock_tracker, hook_context):
        callback = create_subagent_stop_hook(mock_tracker, TASK_ID)
        result = await callback(None, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_tracker_error(self, mock_tracker, hook_context):
        mock_tracker.record_tool_complete.side_effect = RuntimeError("db error")
        callback = create_subagent_stop_hook(mock_tracker, TASK_ID)

        result = await callback({"agent_type": "x", "agent_id": "y"}, None, hook_context)
        assert result == {}


class TestPostToolFailureHook:
    @pytest.mark.asyncio
    async def test_records_failure(self, mock_tracker, hook_context):
        callback = create_post_tool_failure_hook(mock_tracker, TASK_ID)
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls /nonexistent"},
            "error": "No such file or directory",
            "tool_use_id": "tu-001",
            "session_id": "sess-1",
            "transcript_path": "/tmp/transcript",
            "cwd": "/tmp",
            "hook_event_name": "PostToolUseFailure",
        }

        result = await callback(hook_input, "tu-001", hook_context)

        assert result == {}
        mock_tracker.record_tool_complete.assert_called_once_with(
            task_id=TASK_ID,
            tool_name="Bash",
            duration_ms=0.0,
            success=False,
            error="No such file or directory",
            parameters={"command": "ls /nonexistent"},
        )

    @pytest.mark.asyncio
    async def test_handles_missing_fields(self, mock_tracker, hook_context):
        callback = create_post_tool_failure_hook(mock_tracker, TASK_ID)
        result = await callback({}, None, hook_context)

        assert result == {}
        mock_tracker.record_tool_complete.assert_called_once_with(
            task_id=TASK_ID,
            tool_name="unknown",
            duration_ms=0.0,
            success=False,
            error="unknown error",
            parameters={},
        )

    @pytest.mark.asyncio
    async def test_handles_none_input(self, mock_tracker, hook_context):
        callback = create_post_tool_failure_hook(mock_tracker, TASK_ID)
        result = await callback(None, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_tracker_error(self, mock_tracker, hook_context):
        mock_tracker.record_tool_complete.side_effect = RuntimeError("db error")
        callback = create_post_tool_failure_hook(mock_tracker, TASK_ID)

        result = await callback({"tool_name": "Read", "error": "fail"}, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_tracker(self, hook_context):
        callback = create_post_tool_failure_hook(None, TASK_ID)
        result = await callback({"tool_name": "Read", "error": "fail"}, None, hook_context)
        assert result == {}


class TestNotificationHook:
    @pytest.mark.asyncio
    async def test_logs_notification(self, hook_context):
        callback = create_notification_hook(None, TASK_ID)
        hook_input = {
            "message": "Task is 50% complete",
            "session_id": "sess-1",
            "transcript_path": "/tmp/transcript",
            "cwd": "/tmp",
            "hook_event_name": "Notification",
            "notification_type": "progress",
        }

        result = await callback(hook_input, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_records_notification_with_type(self, mock_tracker, hook_context):
        callback = create_notification_hook(mock_tracker, TASK_ID)
        hook_input = {
            "message": "Subagent spawned",
            "notification_type": "progress",
        }

        result = await callback(hook_input, None, hook_context)

        assert result == {}
        mock_tracker.record_tool_complete.assert_called_once_with(
            task_id=TASK_ID,
            tool_name="Notification:progress",
            duration_ms=0.0,
            success=True,
            parameters={"message": "Subagent spawned", "notification_type": "progress"},
        )

    @pytest.mark.asyncio
    async def test_notification_type_defaults_to_unknown(self, mock_tracker, hook_context):
        callback = create_notification_hook(mock_tracker, TASK_ID)
        hook_input = {"message": "Something happened"}

        result = await callback(hook_input, None, hook_context)

        assert result == {}
        call_args = mock_tracker.record_tool_complete.call_args
        assert call_args[1]["tool_name"] == "Notification:unknown"
        assert call_args[1]["parameters"]["notification_type"] == "unknown"

    @pytest.mark.asyncio
    async def test_handles_missing_message(self, hook_context):
        callback = create_notification_hook(None, TASK_ID)
        result = await callback({}, None, hook_context)
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_none_input(self, hook_context):
        callback = create_notification_hook(None, TASK_ID)
        result = await callback(None, None, hook_context)
        assert result == {}


    @pytest.mark.asyncio
    async def test_omits_transcript_path_when_absent(self, mock_tracker, hook_context):
        callback = create_subagent_stop_hook(mock_tracker, TASK_ID)
        hook_input = {
            "agent_type": "code_agent",
            "agent_id": "agent-005",
            "last_assistant_message": "Done.",
        }

        await callback(hook_input, None, hook_context)

        call_args = mock_tracker.record_tool_complete.call_args
        assert "agent_transcript_path" not in call_args[1]["parameters"]


class TestPreToolHookAgentFields:
    @pytest.mark.asyncio
    async def test_passes_agent_fields_to_tracker(self, mock_tracker, hook_context):
        callback = create_pre_tool_hook(mock_tracker, TASK_ID)
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "agent_id": "agent-010",
            "agent_type": "code_agent",
        }

        result = await callback(hook_input, "tu-100", hook_context)

        assert result == {}
        call_args = mock_tracker.record_tool_start.call_args
        params = call_args[0][2]
        assert params["agent_id"] == "agent-010"
        assert params["agent_type"] == "code_agent"
        assert params["tool_use_id"] == "tu-100"

    @pytest.mark.asyncio
    async def test_omits_none_agent_fields(self, mock_tracker, hook_context):
        callback = create_pre_tool_hook(mock_tracker, TASK_ID)
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
        }

        await callback(hook_input, None, hook_context)

        call_args = mock_tracker.record_tool_start.call_args
        params = call_args[0][2]
        assert "agent_id" not in params
        assert "agent_type" not in params
        assert "tool_use_id" not in params


class TestPostToolHookAgentFields:
    @pytest.mark.asyncio
    async def test_passes_agent_fields_to_tracker(self, mock_tracker, hook_context):
        callback = create_post_tool_hook(mock_tracker, TASK_ID)
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/out.py"},
            "agent_id": "agent-020",
            "agent_type": "frontend_agent",
        }

        result = await callback(hook_input, "tu-200", hook_context)

        assert result == {}
        call_args = mock_tracker.record_tool_complete.call_args
        params = call_args[1]["parameters"]
        assert params["agent_id"] == "agent-020"
        assert params["agent_type"] == "frontend_agent"
        assert params["tool_use_id"] == "tu-200"

    @pytest.mark.asyncio
    async def test_omits_none_agent_fields(self, mock_tracker, hook_context):
        callback = create_post_tool_hook(mock_tracker, TASK_ID)
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/out.py"},
        }

        await callback(hook_input, None, hook_context)

        call_args = mock_tracker.record_tool_complete.call_args
        params = call_args[1]["parameters"]
        assert "agent_id" not in params
        assert "agent_type" not in params
        assert "tool_use_id" not in params


class TestBuildHooks:
    def test_returns_all_hook_events(self, mock_tracker):
        hooks = build_hooks(mock_tracker, TASK_ID)

        expected_events = {
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "Stop",
            "SubagentStart",
            "SubagentStop",
            "Notification",
        }
        assert set(hooks.keys()) == expected_events

    def test_each_event_has_hook_matcher(self, mock_tracker):
        hooks = build_hooks(mock_tracker, TASK_ID)

        for event_name, matchers in hooks.items():
            assert len(matchers) == 1, f"{event_name} should have exactly 1 matcher"
            matcher = matchers[0]
            assert matcher.matcher is None, f"{event_name} matcher should be None (match all)"
            assert len(matcher.hooks) == 1, f"{event_name} should have exactly 1 hook callback"

    def test_works_with_no_tracker(self):
        hooks = build_hooks(None, TASK_ID)
        assert len(hooks) == 7

    @pytest.mark.asyncio
    async def test_all_callbacks_are_callable(self, mock_tracker, hook_context):
        hooks = build_hooks(mock_tracker, TASK_ID)

        for event_name, matchers in hooks.items():
            callback = matchers[0].hooks[0]
            result = await callback({}, None, hook_context)
            assert result == {} or isinstance(result, dict), (
                f"{event_name} callback should return dict"
            )
