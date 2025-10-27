"""
Orchestrator agent integration for Telegram bot

Proper separation of concerns:
- Orchestrator: Handles routing, user responses, simple queries via Task tool
- code_agent: Spawned by orchestrator for all file operations and code changes
"""

import asyncio
import json
import logging
from pathlib import Path

from utils.git import get_git_tracker

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


def discover_repositories(base_path: str) -> list[str]:
    """Discover git repositories in workspace"""
    repos = []
    base = Path(base_path)

    try:
        # Look for .git directories up to 2 levels deep
        for item in base.iterdir():
            if item.is_dir():
                if (item / ".git").exists():
                    repos.append(str(item))
                # Check one level deeper
                try:
                    for subitem in item.iterdir():
                        if subitem.is_dir() and (subitem / ".git").exists():
                            repos.append(str(subitem))
                except (PermissionError, OSError):
                    pass  # Skip directories we can't read
    except Exception as e:
        logger.warning(f"Error discovering repositories: {e}")

    return repos


async def invoke_orchestrator(
    user_query: str,
    input_method: str,  # "voice" or "text"
    conversation_history: list[dict],
    current_workspace: str | None,
    bot_repository: str,
    workspace_path: str,
    task_manager=None,  # TaskManager instance for background task creation
    image_path: str | None = None,  # Path to uploaded image
    session_id: str | None = None,  # Session ID for tracking
) -> str | None:
    """
    Invoke orchestrator agent via Claude Code (fire-and-forget pattern).

    IMPORTANT: This function returns IMMEDIATELY (<100ms) without waiting for
    Claude Code execution. The orchestrator subprocess runs detached from the
    parent process, allowing the bot to remain responsive.

    Returns:
        User-facing message string, or None on error
    """

    # Discover available repositories
    available_repos = discover_repositories(workspace_path)

    # Check for uncommitted changes blocking work
    git_tracker = get_git_tracker()

    # Determine target repo from query or current workspace
    target_repo = current_workspace or workspace_path

    # Check if blocked by dirty repos
    blocking_msg = git_tracker.get_blocking_message(target_repo)
    if blocking_msg:
        logger.info("Blocking work due to dirty repos")
        return blocking_msg

    # Get active tasks info if task_manager provided
    active_tasks_info = []
    if task_manager:
        # Get user's active tasks (pending or running)
        # For now, get all active tasks - orchestrator will filter by context
        all_tasks = task_manager.tasks.values()
        active_tasks_info = [
            {"task_id": t.task_id, "description": t.description, "status": t.status, "workspace": t.workspace}
            for t in all_tasks
            if t.status in ["pending", "running"]
        ]

    # Build context for orchestrator
    context = {
        "user_query": user_query,
        "input_method": input_method,
        "conversation_history": conversation_history[-3:],  # Last 3 messages (reduced context)
        "current_workspace": current_workspace or workspace_path,
        "available_repositories": available_repos,
        "bot_repository": bot_repository,
        "active_tasks": active_tasks_info,
    }

    # Add image path if provided
    if image_path:
        context["image_path"] = image_path

    # Format prompt - orchestrator now handles routing and spawns code_agent for coding tasks
    prompt = f"""CONTEXT:
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
- QUESTIONS/CHAT: "what does X do?", "explain Y", "show me..." → Answer directly with 2-3 sentences
- LOG CHECKING: "check logs", "show logs", "?" → Use Grep with ERROR|WARNING pattern, summarize issues
- ANY CODING: "fix bug", "add feature", "edit file", "commit", "modify prompt", etc. → Use BACKGROUND_TASK format

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
- User: "fix bug in main.py" → `BACKGROUND_TASK|Fix bug in main.py|Fixing the bug.`
- User: "modify the orchestrator prompt" → `BACKGROUND_TASK|Modify orchestrator prompt|Updating the prompt.`
- User: "add feature X" → `BACKGROUND_TASK|Add feature X|Adding feature X.`

CRITICAL RULES:
- ❌ NEVER use Task tool for coding work
- ❌ NEVER attempt Write/Edit/Bash commands yourself
- ✅ ONLY use Read, Glob, Grep for analysis
- ✅ ONLY return BACKGROUND_TASK format string for ANY coding/modifications
- ✅ For questions: Answer directly (2-3 sentences)

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

    try:
        logger.info(f"Invoking orchestrator agent for: {user_query[:60]}...")

        # Invoke Claude Code (loads agents from .claude/agents/ automatically)
        cmd = [
            "claude",
            "chat",
            "--model",
            "haiku",  # Fast responses for chat/routing (background tasks use Sonnet)
            "--permission-mode",
            "bypassPermissions",  # Auto-approve write operations
        ]

        logger.debug(f"Command: {' '.join(cmd)}")
        logger.debug(f"Working directory: {bot_repository}")

        # Run from bot_repository to load orchestrator agent config from .claude/agents/
        # Orchestrator can still access other repos using absolute paths via Glob/Grep/Read tools

        # Set environment variables for hooks
        import os

        env = os.environ.copy()
        env["CLAUDE_AGENT_NAME"] = "orchestrator"
        if session_id:
            env["SESSION_ID"] = session_id

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=bot_repository,  # Run from bot repo to load .claude/agents/orchestrator.md
            env=env,  # Pass env vars for hook tracking
            start_new_session=True,  # Detach from parent process (fire-and-forget)
        )

        try:
            # Send prompt and wait for response (fast with Haiku: 1-2s)
            if process.stdin:
                process.stdin.write(f"{prompt}\n".encode())
                await process.stdin.drain()
                process.stdin.close()

            logger.info("Waiting for orchestrator response...")

            # Wait for orchestrator response
            stdout, stderr = await process.communicate()

            output = stdout.decode().strip()

            if stderr:
                error_msg = stderr.decode().strip()
                if error_msg and not error_msg.startswith("Loading"):
                    logger.warning(f"Orchestrator stderr: {error_msg}")

            if not output:
                logger.error("Empty output from orchestrator", exc_info=True)
                return None

            logger.info(f"Orchestrator response: {output[:100]}...")
            return output
        except Exception as e:
            logger.error(f"Error starting orchestrator process: {e}", exc_info=True)
            if process:
                try:
                    process.kill()
                    await process.wait()
                except (ProcessLookupError, OSError):
                    # Process already terminated
                    pass
            return None

    except Exception as e:
        logger.error(f"Error invoking orchestrator: {e}", exc_info=True)
        return None
