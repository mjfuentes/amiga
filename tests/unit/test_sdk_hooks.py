"""Tests for claude/sdk_hooks.py - SDK hook callbacks for AMIGA."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from claude.sdk_hooks import (
    BLOCKED_GIT_PATTERNS,
    _check_blocked_git_command,
    _safe_get,
    build_hooks,
    create_post_tool_hook,
    create_pre_tool_hook,
    create_stop_hook,
)


def _make_context() -> dict:
    """Create a minimal HookContext dict."""
    return {"signal": None}


class TestCheckBlockedGitCommand:
    """Tests for _check_blocked_git_command helper."""

    def test_allows_normal_command(self):
        result = _check_blocked_git_command("ls -la")
        assert result is None

    def test_allows_normal_git_command(self):
        result = _check_blocked_git_command("git status")
        assert result is None

    def test_allows_git_commit(self):
        result = _check_blocked_git_command("git commit -m 'fix bug'")
        assert result is None

    def test_allows_git_push(self):
        result = _check_blocked_git_command("git push origin main")
        assert result is None

    def test_blocks_no_verify(self):
        result = _check_blocked_git_command("git commit --no-verify -m 'skip hooks'")
        assert result is not None
        assert result["decision"] == "block"
        assert "skip" in result["reason"].lower() or "hook" in result["reason"].lower()

    def test_blocks_force_push(self):
        result = _check_blocked_git_command("git push --force origin main")
        assert result is not None
        assert result["decision"] == "block"

    def test_blocks_push_f_flag(self):
        result = _check_blocked_git_command("git push -f origin main")
        assert result is not None
        assert result["decision"] == "block"

    def test_blocks_hard_reset(self):
        result = _check_blocked_git_command("git reset --hard HEAD~1")
        assert result is not None
        assert result["decision"] == "block"

    def test_no_git_keyword_skips_check(self):
        # Even if pattern is present, no "git" means no block
        result = _check_blocked_git_command("echo --no-verify")
        assert result is None


class TestPreToolHook:
    """Tests for create_pre_tool_hook."""

    @pytest.mark.asyncio
    async def test_allows_read_tool(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/tmp/test.py"}},
            "use-1",
            _make_context(),
        )
        assert result == {} or "decision" not in result

    @pytest.mark.asyncio
    async def test_allows_write_tool(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": "/tmp/test.py", "content": "x"}},
            "use-2",
            _make_context(),
        )
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_allows_safe_bash(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "python3 -m pytest"}},
            "use-3",
            _make_context(),
        )
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_allows_safe_git_bash(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "git log --oneline -5"}},
            "use-4",
            _make_context(),
        )
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_blocks_no_verify_in_bash(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m 'bad'"}},
            "use-5",
            _make_context(),
        )
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_blocks_force_push_in_bash(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}},
            "use-6",
            _make_context(),
        )
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_blocks_hard_reset_in_bash(self):
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}},
            "use-7",
            _make_context(),
        )
        assert result["decision"] == "block"

    @pytest.mark.asyncio
    async def test_does_not_check_non_bash_tools(self):
        """Even if tool_input contains git patterns, non-Bash tools are not checked."""
        hook = create_pre_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Write", "tool_input": {"command": "git push --force"}},
            "use-8",
            _make_context(),
        )
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_records_tool_start_with_tracker(self):
        tracker = MagicMock()
        tracker.record_tool_start = MagicMock()

        hook = create_pre_tool_hook(tracker, "task-002")
        await hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
            "use-9",
            _make_context(),
        )
        tracker.record_tool_start.assert_called_once_with(
            "task-002", "Read", {"file_path": "/tmp/x"}
        )

    @pytest.mark.asyncio
    async def test_works_without_tracker(self):
        hook = create_pre_tool_hook(None, "task-003")
        result = await hook(
            {"tool_name": "Grep", "tool_input": {"pattern": "TODO"}},
            "use-10",
            _make_context(),
        )
        assert "decision" not in result


class TestPostToolHook:
    """Tests for create_post_tool_hook."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict(self):
        hook = create_post_tool_hook(None, "task-001")
        result = await hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
            "use-1",
            _make_context(),
        )
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_records_tool_complete_with_tracker(self):
        tracker = MagicMock()
        tracker.record_tool_complete = MagicMock()

        hook = create_post_tool_hook(tracker, "task-004")
        await hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "use-11",
            _make_context(),
        )
        tracker.record_tool_complete.assert_called_once_with(
            task_id="task-004",
            tool_name="Bash",
            duration_ms=0.0,
            success=True,
            parameters={"command": "ls"},
        )

    @pytest.mark.asyncio
    async def test_works_without_tracker(self):
        hook = create_post_tool_hook(None, "task-005")
        result = await hook(
            {"tool_name": "Edit", "tool_input": {}},
            "use-12",
            _make_context(),
        )
        assert "decision" not in result


class TestStopHook:
    """Tests for create_stop_hook."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict(self):
        hook = create_stop_hook(None, "task-001")
        result = await hook(
            {"hook_event_name": "Stop", "stop_hook_active": True},
            None,
            _make_context(),
        )
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_records_status_with_tracker(self):
        tracker = MagicMock()
        tracker.record_status_change = MagicMock()

        hook = create_stop_hook(tracker, "task-006")
        await hook(
            {"hook_event_name": "Stop", "stop_hook_active": True},
            None,
            _make_context(),
        )
        tracker.record_status_change.assert_called_once_with(
            "task-006", "session_ended", "Claude session completed"
        )

    @pytest.mark.asyncio
    async def test_works_without_tracker(self):
        hook = create_stop_hook(None, "task-007")
        result = await hook(
            {"hook_event_name": "Stop", "stop_hook_active": False},
            None,
            _make_context(),
        )
        assert "decision" not in result


class TestBuildHooks:
    """Tests for build_hooks."""

    def test_returns_correct_keys(self):
        hooks = build_hooks(None, "task-001")
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "Stop" in hooks

    def test_returns_hook_matchers(self):
        from claude_agent_sdk import HookMatcher

        hooks = build_hooks(None, "task-001")

        for key in ("PreToolUse", "PostToolUse", "Stop"):
            matchers = hooks[key]
            assert isinstance(matchers, list)
            assert len(matchers) == 1
            assert isinstance(matchers[0], HookMatcher)

    def test_all_matchers_use_none_for_match_all(self):
        hooks = build_hooks(None, "task-001")
        # All matchers use None (SDK default) to match all tools
        assert hooks["PreToolUse"][0].matcher is None
        assert hooks["PostToolUse"][0].matcher is None
        assert hooks["Stop"][0].matcher is None

    def test_each_matcher_has_one_hook(self):
        hooks = build_hooks(None, "task-001")
        for key in ("PreToolUse", "PostToolUse", "Stop"):
            assert len(hooks[key][0].hooks) == 1

    def test_hooks_are_callable(self):
        hooks = build_hooks(None, "task-001")
        for key in ("PreToolUse", "PostToolUse", "Stop"):
            assert callable(hooks[key][0].hooks[0])

    def test_passes_tracker_to_hooks(self):
        tracker = MagicMock()
        hooks = build_hooks(tracker, "task-002")
        # Verify hooks were created (they're closures over tracker)
        assert len(hooks) == 3


class TestBlockedGitPatterns:
    """Tests for the BLOCKED_GIT_PATTERNS constant."""

    def test_patterns_are_tuples(self):
        for item in BLOCKED_GIT_PATTERNS:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_all_patterns_have_reasons(self):
        for pattern, reason in BLOCKED_GIT_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(reason, str)
            assert len(reason) > 0


class TestSafeGet:
    """Tests for the _safe_get helper."""

    def test_returns_value_from_dict(self):
        assert _safe_get({"key": "val"}, "key") == "val"

    def test_returns_default_for_missing_key(self):
        assert _safe_get({"a": 1}, "b", "default") == "default"

    def test_returns_default_for_none_input(self):
        assert _safe_get(None, "key", "fallback") == "fallback"

    def test_returns_none_default_when_not_specified(self):
        assert _safe_get(None, "key") is None

    def test_returns_default_for_non_dict_input(self):
        assert _safe_get(42, "key", "fallback") == "fallback"

    def test_returns_default_for_string_input(self):
        assert _safe_get("not a dict", "key", "fallback") == "fallback"


class TestHookDefensiveBehavior:
    """Tests that hooks never raise exceptions, even when tracker crashes."""

    @pytest.mark.asyncio
    async def test_pre_hook_survives_tracker_exception(self):
        tracker = MagicMock()
        tracker.record_tool_start = MagicMock(
            side_effect=RuntimeError("DB connection lost")
        )
        hook = create_pre_tool_hook(tracker, "task-err")
        result = await hook(
            {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
            "use-1",
            _make_context(),
        )
        # Must return a valid dict, never raise
        assert isinstance(result, dict)
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_post_hook_survives_tracker_exception(self):
        tracker = MagicMock()
        tracker.record_tool_complete = MagicMock(
            side_effect=RuntimeError("DB write failed")
        )
        hook = create_post_tool_hook(tracker, "task-err")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "use-2",
            _make_context(),
        )
        assert isinstance(result, dict)
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_stop_hook_survives_tracker_exception(self):
        tracker = MagicMock()
        tracker.record_status_change = MagicMock(
            side_effect=RuntimeError("DB error")
        )
        hook = create_stop_hook(tracker, "task-err")
        result = await hook(
            {"hook_event_name": "Stop", "stop_hook_active": True},
            None,
            _make_context(),
        )
        assert isinstance(result, dict)
        assert "decision" not in result

    @pytest.mark.asyncio
    async def test_pre_hook_handles_none_hook_input(self):
        hook = create_pre_tool_hook(None, "task-nil")
        result = await hook(None, None, _make_context())
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_post_hook_handles_none_hook_input(self):
        hook = create_post_tool_hook(None, "task-nil")
        result = await hook(None, None, _make_context())
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_pre_hook_handles_none_tool_input(self):
        hook = create_pre_tool_hook(None, "task-nil2")
        result = await hook(
            {"tool_name": "Bash", "tool_input": None},
            "use-3",
            _make_context(),
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_pre_hook_returns_plain_dict(self):
        """Hook must return a plain dict, not a TypedDict subclass that
        might serialize differently."""
        hook = create_pre_tool_hook(None, "task-plain")
        result = await hook(
            {"tool_name": "Read", "tool_input": {}},
            "use-4",
            _make_context(),
        )
        assert result == {}
        assert type(result) is dict

    @pytest.mark.asyncio
    async def test_block_result_is_plain_dict(self):
        """Block responses must also be plain dicts."""
        hook = create_pre_tool_hook(None, "task-block")
        result = await hook(
            {"tool_name": "Bash", "tool_input": {"command": "git push --force origin"}},
            "use-5",
            _make_context(),
        )
        assert result["decision"] == "block"
        assert type(result) is dict
