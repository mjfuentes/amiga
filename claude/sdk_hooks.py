"""
SDK hook callbacks for AMIGA.

Replaces shell script hooks with Python callbacks that write
directly to the SQLite database via ToolUsageTracker.

IMPORTANT: All hook callbacks are wrapped in try/except to prevent
exceptions from crashing the SDK transport layer. An unhandled exception
in a hook callback causes the Claude Code subprocess to emit
"Error in hook callback" and terminate the stream.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from claude_agent_sdk import (
    HookContext,
    HookMatcher,
    PostToolUseHookInput,
    PreToolUseHookInput,
    StopHookInput,
)
from claude_agent_sdk.types import SyncHookJSONOutput

from tasks.tracker import ToolUsageTracker

logger = logging.getLogger(__name__)

# Git patterns that should be blocked in Bash tool commands.
# Each tuple is (pattern_to_match, human-readable reason).
BLOCKED_GIT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("--no-verify", "Pre-commit hooks must not be skipped"),
    ("push --force", "Force push is not allowed"),
    ("push -f ", "Force push is not allowed"),
    ("reset --hard", "Hard reset is not allowed without confirmation"),
)


HookInput = PreToolUseHookInput | PostToolUseHookInput | StopHookInput
HookCallbackType = Callable[
    [HookInput, str | None, HookContext],
    Awaitable[SyncHookJSONOutput],
]


def _safe_get(hook_input: Any, key: str, default: Any = None) -> Any:
    """Safely extract a value from hook_input, handling None inputs.

    The SDK may pass None as hook_input if request_data.get("input")
    returns None.  Calling .get() on None would raise AttributeError
    and crash the hook callback.
    """
    if hook_input is None:
        return default
    try:
        return hook_input.get(key, default)
    except AttributeError:
        return default


def _check_blocked_git_command(command: str) -> dict[str, str] | None:
    """Check if a command contains a blocked git pattern.

    Returns a block response dict if the command should be blocked,
    None otherwise.
    """
    if "git" not in command:
        return None

    for pattern, reason in BLOCKED_GIT_PATTERNS:
        if pattern in command:
            logger.warning(f"Blocked git command: {reason} (pattern={pattern!r})")
            return {"decision": "block", "reason": reason}

    return None


def create_pre_tool_hook(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> HookCallbackType:
    """Create a PreToolUse hook callback.

    Logs tool invocations and blocks dangerous git operations.
    All tracker calls are wrapped in try/except so they never crash
    the hook callback.
    """

    async def pre_tool_callback(
        hook_input: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> SyncHookJSONOutput:
        try:
            tool_name = _safe_get(hook_input, "tool_name", "unknown")
            tool_input = _safe_get(hook_input, "tool_input", {})

            logger.debug(f"Task {task_id}: PreToolUse tool={tool_name}")

            # Record tool start in tracker (never let this crash the hook)
            if tracker:
                try:
                    params = dict(tool_input) if tool_input else {}
                    tracker.record_tool_start(task_id, tool_name, params)
                except Exception as tracker_err:
                    logger.warning(
                        f"Task {task_id}: Failed to record tool start: {tracker_err}"
                    )

            # Only check Bash tool commands for dangerous git patterns
            if tool_name == "Bash":
                command = _safe_get(tool_input, "command", "")
                if command:
                    block_result = _check_blocked_git_command(command)
                    if block_result is not None:
                        return block_result

            return {}
        except Exception as exc:
            logger.error(f"Task {task_id}: Pre-tool hook error: {exc}")
            return {}

    return pre_tool_callback


def create_post_tool_hook(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> HookCallbackType:
    """Create a PostToolUse hook callback.

    Records tool completion to the tracker with duration info.
    All tracker calls are wrapped in try/except so they never crash
    the hook callback.
    """

    async def post_tool_callback(
        hook_input: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> SyncHookJSONOutput:
        try:
            tool_name = _safe_get(hook_input, "tool_name", "unknown")
            tool_input = _safe_get(hook_input, "tool_input", {})

            logger.debug(f"Task {task_id}: PostToolUse tool={tool_name}")

            if tracker:
                try:
                    params = dict(tool_input) if tool_input else {}
                    tracker.record_tool_complete(
                        task_id=task_id,
                        tool_name=tool_name,
                        duration_ms=0.0,
                        success=True,
                        parameters=params,
                    )
                except Exception as tracker_err:
                    logger.warning(
                        f"Task {task_id}: Failed to record tool complete: {tracker_err}"
                    )

            return {}
        except Exception as exc:
            logger.error(f"Task {task_id}: Post-tool hook error: {exc}")
            return {}

    return post_tool_callback


def create_stop_hook(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> HookCallbackType:
    """Create a Stop hook callback.

    Logs session completion for the task.
    All tracker calls are wrapped in try/except so they never crash
    the hook callback.
    """

    async def stop_callback(
        hook_input: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> SyncHookJSONOutput:
        try:
            logger.info(f"Task {task_id}: Session ending (Stop hook)")

            if tracker:
                try:
                    tracker.record_status_change(
                        task_id, "session_ended", "Claude session completed"
                    )
                except Exception as tracker_err:
                    logger.warning(
                        f"Task {task_id}: Failed to record status change: {tracker_err}"
                    )

            return {}
        except Exception as exc:
            logger.error(f"Task {task_id}: Stop hook error: {exc}")
            return {}

    return stop_callback


def build_hooks(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> dict[str, list[HookMatcher]]:
    """Build the full hooks dict for ClaudeAgentOptions.

    Args:
        tracker: Optional ToolUsageTracker for recording tool usage.
        task_id: The task ID for this session.

    Returns:
        Dictionary mapping hook event names to lists of HookMatchers,
        ready to pass to ClaudeAgentOptions(hooks=...).

    Notes:
        - matcher=None means "match all tools" (SDK default).
        - Using None instead of "" avoids potential matching issues
          where empty string might not match tool names as expected.
    """
    pre_hook = create_pre_tool_hook(tracker, task_id)
    post_hook = create_post_tool_hook(tracker, task_id)
    stop_hook = create_stop_hook(tracker, task_id)

    return {
        "PreToolUse": [HookMatcher(matcher=None, hooks=[pre_hook])],
        "PostToolUse": [HookMatcher(matcher=None, hooks=[post_hook])],
        "Stop": [HookMatcher(matcher=None, hooks=[stop_hook])],
    }
