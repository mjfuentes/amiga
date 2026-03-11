"""
Claude Agent SDK client - replaces subprocess-based Claude Code integration.

Uses claude_code_sdk.query() instead of spawning `claude -p` as a subprocess.
Provides ClaudeSDKSession, ClaudeSDKPool, and invoke_orchestrator_sdk as
drop-in replacements for ClaudeInteractiveSession, ClaudeSessionPool,
and invoke_orchestrator respectively.
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from claude.api_client import detect_prompt_injection, sanitize_xml_content
from core.exceptions import AMIGAError
from tasks.tracker import ToolUsageTracker
from utils.git import get_git_tracker

logger = logging.getLogger(__name__)

# Effort and cost defaults per task type
ORCHESTRATOR_EFFORT = "low"
ORCHESTRATOR_MAX_BUDGET = 0.50  # Routing should be cheap (haiku)
TASK_EFFORT = "high"  # Implementation tasks need full reasoning
TASK_MAX_BUDGET = 5.0  # Cap per individual task
DEBUG_EFFORT = "max"  # Deep debugging gets maximum reasoning
DEBUG_MAX_BUDGET = 10.0  # Debugging can be expensive


def discover_repositories(base_path: str) -> list[str]:
    """Discover git repositories in workspace."""
    repos: list[str] = []
    base = Path(base_path)

    try:
        for item in base.iterdir():
            if item.is_dir():
                if (item / ".git").exists():
                    repos.append(str(item))
                try:
                    for subitem in item.iterdir():
                        if subitem.is_dir() and (subitem / ".git").exists():
                            repos.append(str(subitem))
                except (PermissionError, OSError):
                    pass
    except Exception as e:
        logger.warning(f"Error discovering repositories: {e}")

    return repos


class ClaudeSDKSession:
    """SDK-based Claude session replacing subprocess spawning."""

    def __init__(
        self,
        workspace: Path,
        model: str = "sonnet",
        usage_tracker: ToolUsageTracker | None = None,
    ):
        self.workspace = workspace
        self.model = model
        self.usage_tracker = usage_tracker
        self._cancel_event: asyncio.Event = asyncio.Event()

    def _find_project_root(self) -> Path:
        """Find the main project root, resolving worktree symlinks.

        When running in a git worktree, .git is a file pointing to the
        main repo. This follows that reference to find the actual root.
        """
        git_path = self.workspace / ".git"

        if git_path.exists() and git_path.is_file():
            git_content = git_path.read_text().strip()
            if git_content.startswith("gitdir:"):
                gitdir_path = Path(git_content.split("gitdir:")[1].strip())
                # .git/worktrees/<name> -> .git/worktrees -> .git -> repo root
                return gitdir_path.parent.parent.parent

        return self.workspace

    def _build_options(
        self,
        task_id: str,
        effort: str = "high",
        max_budget_usd: float | None = None,
        use_worktree: bool = True,
    ) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for a task execution."""
        project_root = self._find_project_root()

        env_vars = {
            "TASK_ID": task_id,
            "PROJECT_ROOT": str(project_root),
        }

        extra_args: dict[str, str | None] = {}
        if effort:
            extra_args["effort"] = effort
        if max_budget_usd is not None:
            extra_args["max-budget-usd"] = str(max_budget_usd)
        if use_worktree:
            extra_args["worktree"] = None  # Flag-only, no value

        return ClaudeAgentOptions(
            model=self.model,
            permission_mode="bypassPermissions",
            allowed_tools=["Task", "TodoWrite", "Read", "Glob", "Grep", "Bash"],
            cwd=str(self.workspace),
            env=env_vars,
            max_turns=200,
            extra_args=extra_args,
        )

    async def execute_task(
        self,
        task_id: str,
        prompt: str,
        progress_callback: Callable[[str, int], None] | None = None,
        effort: str = "high",
        max_budget_usd: float | None = None,
        use_worktree: bool = True,
    ) -> tuple[bool, str, str | None]:
        """Execute task via SDK query().

        Returns:
            (success, result_text, session_id)
        """
        if not self.usage_tracker:
            logger.warning(
                f"Task {task_id}: usage_tracker is None - session data will NOT be tracked"
            )

        if self.usage_tracker:
            self.usage_tracker.record_status_change(
                task_id, "started", "Starting Claude SDK session"
            )

        options = self._build_options(task_id, effort, max_budget_usd, use_worktree)
        self._cancel_event.clear()

        logger.info(f"Task {task_id}: Starting SDK query (model={self.model}, workspace={self.workspace})")
        logger.info(f"Task {task_id}: Prompt preview: {prompt[:100]}...")

        session_id: str | None = None
        result_text: str = ""
        is_error: bool = False
        turn_count: int = 0

        try:
            async for message in query(prompt=prompt, options=options):
                if self._cancel_event.is_set():
                    logger.info(f"Task {task_id}: Cancelled by user")
                    break

                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    is_error = message.is_error
                    result_text = message.result or ""

                    logger.info(
                        f"Task {task_id}: Completed in {message.duration_ms}ms "
                        f"(turns={message.num_turns}, cost=${message.total_cost_usd or 0:.4f}, "
                        f"error={is_error})"
                    )

                    await self._record_completion(
                        task_id, session_id, message, is_error
                    )

                elif isinstance(message, AssistantMessage):
                    turn_count += 1
                    self._log_assistant_message(task_id, message, turn_count)

                    if progress_callback:
                        progress_callback(
                            f"Processing... turn {turn_count}", turn_count
                        )

                elif isinstance(message, SystemMessage):
                    self._log_system_message(task_id, message)

            success = not is_error and bool(result_text)

            if not result_text:
                result_text = "No output produced by Claude SDK"
                success = False

            return success, result_text, session_id

        except ClaudeSDKError as e:
            error_msg = f"Claude SDK error: {e}"
            logger.error(f"Task {task_id}: {error_msg}", exc_info=True)
            await self._record_failure(task_id, error_msg)
            return False, error_msg, session_id

        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Task {task_id}: {error_msg}", exc_info=True)
            await self._record_failure(task_id, error_msg)
            return False, error_msg, session_id

    async def _record_completion(
        self,
        task_id: str,
        session_id: str | None,
        result: ResultMessage,
        is_error: bool,
    ) -> None:
        """Record task completion in usage tracker."""
        if not self.usage_tracker:
            return

        status = "failed" if is_error else "completed"
        detail = f"duration={result.duration_ms}ms, cost=${result.total_cost_usd or 0:.4f}"

        self.usage_tracker.record_status_change(task_id, status, detail)

        if session_id:
            await self.usage_tracker.db.update_task(
                task_id=task_id,
                session_uuid=session_id,
                status=status,
            )

    async def _record_failure(self, task_id: str, error_msg: str) -> None:
        """Record task failure in usage tracker."""
        if not self.usage_tracker:
            return

        self.usage_tracker.record_status_change(task_id, "failed", error_msg)
        await self.usage_tracker.db.update_task(
            task_id=task_id, status="failed", error=error_msg
        )

    def _log_assistant_message(
        self, task_id: str, message: AssistantMessage, turn: int
    ) -> None:
        """Log assistant message content at appropriate levels."""
        for block in message.content:
            if isinstance(block, TextBlock):
                preview = block.text[:120].replace("\n", " ")
                logger.debug(f"Task {task_id} turn {turn}: {preview}...")
            elif isinstance(block, ToolUseBlock):
                logger.info(f"Task {task_id} turn {turn}: tool={block.name}")

    def _log_system_message(self, task_id: str, message: SystemMessage) -> None:
        """Log system message data."""
        subtype = message.subtype
        if subtype == "init":
            tools = message.data.get("tools", [])
            logger.info(
                f"Task {task_id}: Session initialized with {len(tools)} tools"
            )
        else:
            logger.debug(f"Task {task_id}: System message subtype={subtype}")

    async def cancel(self) -> None:
        """Cancel running query via event signal."""
        self._cancel_event.set()
        logger.info("Cancel signal sent to SDK session")


class ClaudeSDKPool:
    """Pool of SDK sessions for concurrent task execution."""

    def __init__(
        self,
        max_concurrent: int = 3,
        usage_tracker: ToolUsageTracker | None = None,
    ):
        self.max_concurrent = max_concurrent
        self.usage_tracker = usage_tracker
        self._active_sessions: dict[str, ClaudeSDKSession] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_task(
        self,
        task_id: str,
        description: str,
        workspace: Path,
        model: str = "sonnet",
        context: str | None = None,
        pid_callback: Callable[[int], None] | None = None,
        progress_callback: Callable[[str, int], None] | None = None,
        effort: str = "high",
        max_budget_usd: float | None = None,
        use_worktree: bool = True,
    ) -> tuple[bool, str, str | None, str | None]:
        """Execute a task using session pool.

        Returns:
            (success, result, session_id, workflow_name)
        """
        workflow_name = "orchestrator"

        async with self._semaphore:
            session = ClaudeSDKSession(
                workspace=workspace,
                model=model,
                usage_tracker=self.usage_tracker,
            )
            self._active_sessions[task_id] = session

            try:
                prompt = self._build_prompt(description, context)

                # pid_callback kept for API compat; SDK doesn't expose PID
                if pid_callback:
                    logger.debug(
                        f"Task {task_id}: pid_callback provided but SDK has no PID"
                    )

                if self.usage_tracker:
                    await self.usage_tracker.record_workflow_assignment(
                        task_id, workflow_name
                    )

                success, result, session_id = await session.execute_task(
                    task_id=task_id,
                    prompt=prompt,
                    progress_callback=progress_callback,
                    effort=effort,
                    max_budget_usd=max_budget_usd,
                    use_worktree=use_worktree,
                )

                await self._finalize_task(
                    task_id, success, result, session_id
                )

                return success, result, session_id, workflow_name

            except Exception as e:
                error_msg = f"Task execution error: {e}"
                logger.error(f"Task {task_id}: {error_msg}", exc_info=True)
                await self._record_pool_failure(task_id, error_msg)
                return False, error_msg, None, workflow_name

            finally:
                self._active_sessions.pop(task_id, None)

    def _build_prompt(self, description: str, context: str | None) -> str:
        """Build prompt from description and optional context."""
        parts: list[str] = []
        if context:
            parts.append(context)
        parts.append(description)
        return "\n\n".join(parts)

    async def _finalize_task(
        self,
        task_id: str,
        success: bool,
        result: str,
        session_id: str | None,
    ) -> None:
        """Update task status in DB after completion."""
        if not self.usage_tracker:
            return

        if success:
            await self.usage_tracker.db.update_task(
                task_id, status="completed", result=result[:500]
            )
        elif len(result.strip()) < 10:
            error_msg = f"Minimal output ({len(result)} chars): {result[:100]}"
            logger.warning(f"Task {task_id}: {error_msg}")
            await self.usage_tracker.db.update_task(
                task_id, status="failed", error=error_msg
            )

    async def _record_pool_failure(
        self, task_id: str, error_msg: str
    ) -> None:
        """Record pool-level failure in tracker and DB."""
        if not self.usage_tracker:
            return

        self.usage_tracker.record_status_change(task_id, "failed", error_msg)
        await self.usage_tracker.db.update_task(
            task_id, status="failed", error=error_msg
        )

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task by task_id.

        Returns:
            True if session was found and cancelled, False otherwise.
        """
        session = self._active_sessions.get(task_id)
        if not session:
            logger.warning(f"Task {task_id} not found in active sessions")
            return False

        await session.cancel()

        if self.usage_tracker:
            self.usage_tracker.record_status_change(
                task_id, "stopped", "Task stopped by user"
            )
            await self.usage_tracker.db.update_task(
                task_id, status="stopped", error="Stopped by user request"
            )

        logger.info(f"Task {task_id} cancelled by user request")
        return True

    async def cancel_all(self) -> None:
        """Cancel all active sessions."""
        for task_id, session in list(self._active_sessions.items()):
            await session.cancel()
            logger.info(f"Cancelled task {task_id}")
        self._active_sessions.clear()


def _build_orchestrator_prompt(
    user_query: str,
    input_method: str,
    conversation_history: list[dict],
    current_workspace: str | None,
    bot_repository: str,
    workspace_path: str,
    available_repos: list[str],
    active_tasks_info: list[dict],
    image_path: str | None = None,
) -> str:
    """Build the orchestrator prompt. Identical to invoke_orchestrator's prompt."""
    context = {
        "user_query": user_query,
        "input_method": input_method,
        "conversation_history": conversation_history[-3:],
        "current_workspace": current_workspace or workspace_path,
        "available_repositories": available_repos,
        "bot_repository": bot_repository,
        "active_tasks": active_tasks_info,
    }

    if image_path:
        context["image_path"] = image_path

    return f"""CONTEXT:
{json.dumps(context, indent=2)}

USER CONTEXT:
- Name: Matias Fuentes
- You are their personal engineering assistant
- Available projects: cloudmate, Latinamerica2026, permanent_residence, groovetherapy, mjfuentes.github.io, agentlab
- Use this project knowledge in conversations - reference their work and interests

YOUR ROLE:
You are the routing orchestrator. For user queries:
1. Answer directly if it's a question, chat, or knowledge request
2. Use BACKGROUND_TASK format for ANY coding work (file ops, code changes, git commands, edits, features, etc.)

ROUTING DECISION:
- QUESTIONS/CHAT: "what does X do?", "explain Y", "show me..." -> Answer directly with 2-3 sentences
- LOG CHECKING: "check logs", "show logs", "?" -> Use Grep with ERROR|WARNING pattern, summarize issues
- ANY CODING: "fix bug", "add feature", "edit file", "commit", "modify prompt", etc. -> Use BACKGROUND_TASK format

LOG CHECKING PROTOCOL (CRITICAL):
When user says "check logs", "show logs", or "?":
- NEVER use Read tool on logs/bot.log
- ALWAYS use Grep with pattern: ERROR|WARNING|CRITICAL|Exception|Traceback
- path: logs/bot.log, output_mode: content, -C: 2
- Summarize errors found (or "Logs clean" if none)
- Keep response brief: 3-4 sentences

BACKGROUND_TASK FORMAT (EXACT):
For ANY coding work, return this EXACT format (pipe-delimited, single line):
```
BACKGROUND_TASK|<task_description>|<user_message>
```

Examples:
- User: "fix bug in main.py" -> `BACKGROUND_TASK|Fix bug in main.py|Fixing the bug.`
- User: "modify the orchestrator prompt" -> `BACKGROUND_TASK|Modify orchestrator prompt|Updating the prompt.`
- User: "add feature X" -> `BACKGROUND_TASK|Add feature X|Adding feature X.`

CRITICAL RULES:
- NEVER use Task tool for coding work
- NEVER attempt Write/Edit/Bash commands yourself
- ONLY use Read, Glob, Grep for analysis
- ONLY return BACKGROUND_TASK format string for ANY coding/modifications
- For questions: Answer directly (2-3 sentences)

RESPONSE REQUIREMENTS:
- For questions/chat: Direct, conversational answer (2-3 sentences)
- For ANY coding: Return BACKGROUND_TASK format immediately
- Keep it brief: Mobile users, max 3 sentences when possible
- Use active voice: "Fixing X" not "X will be fixed"

Remember:
- input_method="{input_method}" ({'be permissive with voice errors' if input_method == 'voice' else 'exact text input'})
- When user references "you"/"your code"/"the bot": {bot_repository}
- Current workspace: {current_workspace or workspace_path}
- This bot is deeply personal - tailor responses to Matias' interests
{'- IMAGE ATTACHED: View at: ' + image_path if image_path else ''}

User query: {user_query}"""


async def invoke_orchestrator_sdk(
    user_query: str,
    input_method: str,
    conversation_history: list[dict],
    current_workspace: str | None,
    bot_repository: str,
    workspace_path: str,
    task_manager: Any = None,
    image_path: str | None = None,
    session_id: str | None = None,
) -> str | None:
    """SDK-based orchestrator invocation.

    Returns:
        User-facing message string, or None on error.
    """
    available_repos = discover_repositories(workspace_path)

    git_tracker = get_git_tracker()
    target_repo = current_workspace or workspace_path
    blocking_msg = git_tracker.get_blocking_message(target_repo)
    if blocking_msg:
        logger.info("Blocking work due to dirty repos")
        return blocking_msg

    active_tasks_info = _collect_active_tasks(task_manager)

    prompt = _build_orchestrator_prompt(
        user_query=user_query,
        input_method=input_method,
        conversation_history=conversation_history,
        current_workspace=current_workspace,
        bot_repository=bot_repository,
        workspace_path=workspace_path,
        available_repos=available_repos,
        active_tasks_info=active_tasks_info,
        image_path=image_path,
    )

    env_vars: dict[str, str] = {"CLAUDE_AGENT_NAME": "orchestrator"}
    if session_id:
        env_vars["SESSION_ID"] = session_id

    options = ClaudeAgentOptions(
        model="haiku",
        permission_mode="bypassPermissions",
        cwd=bot_repository,
        env=env_vars,
        max_turns=5,
        extra_args={"effort": ORCHESTRATOR_EFFORT, "max-budget-usd": str(ORCHESTRATOR_MAX_BUDGET)},
    )

    try:
        logger.info(f"Invoking SDK orchestrator for: {user_query[:60]}...")

        result_text = await _collect_query_result(prompt, options)

        if not result_text:
            logger.error("Empty output from SDK orchestrator")
            return None

        logger.info(f"SDK orchestrator response: {result_text[:100]}...")
        return result_text

    except ClaudeSDKError as e:
        logger.error(f"SDK error invoking orchestrator: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error invoking SDK orchestrator: {e}", exc_info=True)
        return None


def _collect_active_tasks(task_manager: Any) -> list[dict]:
    """Extract active task info from task manager."""
    if not task_manager:
        return []

    try:
        all_tasks = task_manager.tasks.values()
        return [
            {
                "task_id": t.task_id,
                "description": t.description,
                "status": t.status,
                "workspace": t.workspace,
            }
            for t in all_tasks
            if t.status in ["pending", "running"]
        ]
    except Exception as e:
        logger.warning(f"Error collecting active tasks: {e}")
        return []


async def _collect_query_result(
    prompt: str, options: ClaudeAgentOptions
) -> str | None:
    """Run SDK query and collect the final result text."""
    result_text: str | None = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result_text = message.result
            if message.is_error:
                logger.warning(
                    f"Orchestrator query returned error: {result_text}"
                )
        elif isinstance(message, AssistantMessage):
            # Extract text from assistant messages as fallback
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    # Keep last non-empty text as potential result
                    result_text = block.text.strip()

    return result_text
