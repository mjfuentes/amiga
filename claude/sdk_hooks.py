"""
SDK hook callbacks for AMIGA.

Replaces shell script hooks with Python callbacks that write
directly to the SQLite database via ToolUsageTracker.
"""

import logging
import time
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


def _check_blocked_git_command(command: str) -> SyncHookJSONOutput | None:
    """Check if a command contains a blocked git pattern.

    Returns a block response if the command should be blocked, None otherwise.
    """
    if "git" not in command:
        return None

    for pattern, reason in BLOCKED_GIT_PATTERNS:
        if pattern in command:
            logger.warning(f"Blocked git command: {reason} (pattern={pattern!r})")
            return SyncHookJSONOutput(decision="block", reason=reason)

    return None


def create_pre_tool_hook(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> HookCallbackType:
    """Create a PreToolUse hook callback.

    Logs tool invocations and blocks dangerous git operations.
    """

    async def pre_tool_callback(
        hook_input: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> SyncHookJSONOutput:
        tool_name = hook_input.get("tool_name", "unknown")
        tool_input = hook_input.get("tool_input", {})

        logger.debug(f"Task {task_id}: PreToolUse tool={tool_name}")

        # Record tool start in tracker
        if tracker:
            params = dict(tool_input) if tool_input else {}
            tracker.record_tool_start(task_id, tool_name, params)

        # Only check Bash tool commands for dangerous git patterns
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            block_result = _check_blocked_git_command(command)
            if block_result is not None:
                return block_result

        return SyncHookJSONOutput()

    return pre_tool_callback


def create_post_tool_hook(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> HookCallbackType:
    """Create a PostToolUse hook callback.

    Records tool completion to the tracker with duration info.
    """

    async def post_tool_callback(
        hook_input: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> SyncHookJSONOutput:
        tool_name = hook_input.get("tool_name", "unknown")
        tool_input = hook_input.get("tool_input", {})

        logger.debug(f"Task {task_id}: PostToolUse tool={tool_name}")

        if tracker:
            params = dict(tool_input) if tool_input else {}
            # Duration is not directly available in the hook input;
            # record with zero and let the tracker handle timing externally.
            tracker.record_tool_complete(
                task_id=task_id,
                tool_name=tool_name,
                duration_ms=0.0,
                success=True,
                parameters=params,
            )

        return SyncHookJSONOutput()

    return post_tool_callback


def create_stop_hook(
    tracker: ToolUsageTracker | None,
    task_id: str,
) -> HookCallbackType:
    """Create a Stop hook callback.

    Logs session completion for the task.
    """

    async def stop_callback(
        hook_input: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> SyncHookJSONOutput:
        logger.info(f"Task {task_id}: Session ending (Stop hook)")

        if tracker:
            tracker.record_status_change(
                task_id, "session_ended", "Claude session completed"
            )

        return SyncHookJSONOutput()

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
    """
    pre_hook = create_pre_tool_hook(tracker, task_id)
    post_hook = create_post_tool_hook(tracker, task_id)
    stop_hook = create_stop_hook(tracker, task_id)

    return {
        "PreToolUse": [HookMatcher(matcher="", hooks=[pre_hook])],
        "PostToolUse": [HookMatcher(matcher="", hooks=[post_hook])],
        "Stop": [HookMatcher(hooks=[stop_hook])],
    }
