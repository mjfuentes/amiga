# Main entry point for the Telegram bot
#!/usr/bin/env python3
"""
Telegram Bot for Claude Code Orchestrator
Phase 5: Voice message support with Whisper transcription
"""

import asyncio
import atexit
import logging
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from claude.api_client import ask_claude
from claude.code_cli import ClaudeSessionPool
from core.config import RESTART_STATE_FILE_STR
from core.config_validator import check_and_warn
from core.database_manager import get_database, close_database
from core.orchestrator import discover_repositories
from core.session import ClaudeCodeSession, SessionManager
from dotenv import load_dotenv
from messaging.formatter import format_telegram_response
from messaging.queue import MessageQueueManager
from messaging.rate_limiter import RateLimiter
from tasks.analytics import AnalyticsDB
from tasks.manager import Task, TaskManager
from tasks.pool import AgentPool, TaskPriority
from tasks.tracker import ToolUsageTracker
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from utils.git import get_git_tracker
from utils.log_monitor import LogMonitorManager, MonitoringConfig
from utils.logging_setup import configure_root_logger
from core.self_improvement_scheduler import SelfImprovementScheduler

# Import scripts
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from log_claude_escalation import LogClaudeEscalation, UserConfirmationManager

# Check if whisper is available
try:
    import whisper

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = [int(uid) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid]
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "claude")
WORKSPACE_PATH = os.getenv("WORKSPACE_PATH", os.getcwd())
BOT_REPOSITORY = os.getenv("BOT_REPOSITORY", os.getcwd())

# Setup logging (BEFORE any log calls to avoid duplicate handlers)
# NOTE: No console handler when running under launchd - it captures stdout/stderr automatically
configure_root_logger(
    handlers=[logging.FileHandler("logs/bot.log")],
    force=True,
)
from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)

# Reduce HTTP/Telegram noise in logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Log whisper availability after logging is configured
if not WHISPER_AVAILABLE:
    logger.warning("Whisper not installed. Voice transcription will be limited.")


# PID file lock management
class PIDFileLock:
    """
    Manages a PID file to ensure only one bot instance runs at a time.

    Uses file locking to prevent race conditions and properly detects stale PID files.
    """

    def __init__(self, pid_file_path: str = "data/bot.pid"):
        """
        Initialize PID file lock.

        Args:
            pid_file_path: Path to the PID file
        """
        self.pid_file = Path(pid_file_path)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.locked = False

    def acquire(self) -> bool:
        """
        Acquire the PID file lock.

        Returns:
            True if lock acquired successfully, False if another instance is running

        Raises:
            SystemExit: If another instance is detected
        """
        # Check if PID file exists
        if self.pid_file.exists():
            try:
                # Read existing PID
                with open(self.pid_file) as f:
                    existing_pid = int(f.read().strip())

                # Check if process is still running
                if self._is_process_running(existing_pid):
                    logger.error(
                        f"Another bot instance is already running (PID: {existing_pid}, exc_info=True). "
                        "Only one instance can run at a time."
                    )
                    logger.error(
                        "To stop the existing instance:\n"
                        f"  kill {existing_pid}\n"
                        "Or use the /restart command from Telegram."
                    , exc_info=True)
                    return False
                else:
                    # Stale PID file - process is dead
                    logger.warning(f"Found stale PID file (PID {existing_pid} not running). Removing...")
                    self.pid_file.unlink()
            except (OSError, ValueError) as e:
                logger.warning(f"Error reading PID file: {e}. Removing...")
                self.pid_file.unlink()

        # Write our PID
        current_pid = os.getpid()
        try:
            with open(self.pid_file, "w") as f:
                f.write(str(current_pid))
            self.locked = True
            logger.info(f"PID file lock acquired (PID: {current_pid})")

            # Register cleanup on exit
            atexit.register(self.release)

            # Register signal handlers for graceful shutdown
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

            return True
        except OSError as e:
            logger.error(f"Failed to write PID file: {e}", exc_info=True)
            return False

    def release(self):
        """Release the PID file lock."""
        if self.locked and self.pid_file.exists():
            try:
                # Verify it's our PID before removing
                with open(self.pid_file) as f:
                    pid = int(f.read().strip())

                if pid == os.getpid():
                    self.pid_file.unlink()
                    logger.info("PID file lock released")
                    self.locked = False
                else:
                    logger.warning(f"PID file contains different PID ({pid}), not removing")
            except (OSError, ValueError) as e:
                logger.warning(f"Error releasing PID file: {e}")

    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process with given PID is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        try:
            # Send signal 0 to check if process exists (doesn't actually send a signal)
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _signal_handler(self, signum, frame):
        """
        Handle termination signals gracefully.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} signal, shutting down gracefully...")
        self.release()
        sys.exit(0)


# Global PID lock instance
pid_lock = PIDFileLock()

# Global managers
db = get_database()  # Shared singleton database instance
analytics_db = AnalyticsDB(db)  # Analytics database for message tracking
session_manager = SessionManager()
claude_client = ClaudeCodeSession(CLAUDE_CLI_PATH, WORKSPACE_PATH, session_manager)
task_manager = TaskManager(db=db)
tool_usage_tracker = ToolUsageTracker(db=db)  # Track tool usage and agent status
claude_pool = ClaudeSessionPool(usage_tracker=tool_usage_tracker)  # No default workspace - uses task.workspace
rate_limiter = RateLimiter()  # Rate limiting
queue_manager = MessageQueueManager()  # Message queue per user
agent_pool = AgentPool(max_agents=3)  # Bounded agent pool for background tasks

# Log monitoring system
log_monitor_config = MonitoringConfig(
    log_path="logs/bot.log",
    check_interval_seconds=300,  # Check every 5 minutes
    analysis_window_hours=1,  # Analyze last hour
    notify_on_critical=True,
    notify_on_warning=False,  # Only notify on critical initially
    max_notifications_per_check=3,
)
log_monitor_manager = LogMonitorManager(log_monitor_config)
log_escalation = LogClaudeEscalation(BOT_REPOSITORY)
user_confirmations = UserConfirmationManager()


# Register tool usage tracking hooks
def log_tool_start(task_id: str, tool_name: str, parameters: dict):
    """Hook: Log when a tool starts"""
    logger.debug(f"Tool started: {tool_name} (task: {task_id})")


def log_tool_complete(task_id: str, tool_name: str, duration_ms: float, success: bool, error: str | None):
    """Hook: Log when a tool completes"""
    status = "✓" if success else "✗"
    logger.info(f"{status} {tool_name} ({duration_ms:.0f}ms, task: {task_id})")


def log_status_change(task_id: str, status: str, message: str | None):
    """Hook: Log agent status changes"""
    msg = f" - {message}" if message else ""
    logger.info(f"Task {task_id}: {status}{msg}")


# Register hooks with tracker
tool_usage_tracker.register_tool_start_hook(log_tool_start)
tool_usage_tracker.register_tool_complete_hook(log_tool_complete)
tool_usage_tracker.register_status_change_hook(log_status_change)


def resolve_git_workspace(current_workspace: str | None, workspace_path: str, bot_repo: str) -> Path | None:
    """
    Resolve workspace to a valid git repository

    Priority:
    1. current_workspace if set and is git repo
    2. bot_repo (agentlab) if no workspace set
    3. None if no valid git repo found

    Args:
        current_workspace: User's selected workspace (may be None or non-git)
        workspace_path: Default workspace parent directory
        bot_repo: Path to the bot's own repository

    Returns:
        Path to valid git repository, or None if none found
    """
    candidates = []

    if current_workspace:
        candidates.append(Path(current_workspace))

    # Default to bot repo for bot-related tasks
    candidates.append(Path(bot_repo))

    # Never default to parent WORKSPACE_PATH unless it's actually a git repo
    workspace_parent = Path(workspace_path)
    if (workspace_parent / ".git").exists():
        candidates.append(workspace_parent)

    for candidate in candidates:
        if candidate.exists() and (candidate / ".git").exists():
            logger.debug(f"Resolved git workspace: {candidate}")
            return candidate

    logger.warning(f"No valid git repository found. Candidates checked: {[str(c) for c in candidates]}")
    return None


async def send_formatted_response(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, response: str, workspace_path: str | None = None
):
    """
    Send a formatted response to the user, either as text chunks or as a document attachment
    if the response is too long.

    Args:
        context: Telegram context
        user_id: User ID to send to
        response: Raw response text
        workspace_path: Optional workspace path for context
    """
    formatted_result = format_telegram_response(response, workspace_path=workspace_path)

    # Check if result is a tuple (document mode) or list (normal chunks)
    if isinstance(formatted_result, tuple):
        # Document mode: send summary + attached file
        summary, document_path = formatted_result
        await context.bot.send_message(chat_id=user_id, text=summary, parse_mode="HTML")

        # Send the markdown document
        try:
            with open(document_path, "rb") as doc:
                await context.bot.send_document(chat_id=user_id, document=doc, filename="response.md")
        finally:
            # Clean up temporary file
            Path(document_path).unlink(missing_ok=True)
    else:
        # Normal mode: send chunks
        for chunk in formatted_result:
            await context.bot.send_message(chat_id=user_id, text=chunk, parse_mode="HTML")


# Async wrapper functions for delegating writes to worker pool
async def _async_add_session_message(user_id: int, role: str, content: str):
    """Async wrapper for session write - queued to worker pool"""
    session_manager.add_message(user_id, role, content)
    logger.debug(f"Queued session write: user {user_id}, role {role}")


async def recover_interrupted_tasks(app: Application) -> None:
    """
    Recover tasks interrupted by bot restart.
    Notifies users about interrupted tasks and offers retry option.
    """
    # Get all stopped tasks that were interrupted by restart
    interrupted_tasks = db.get_interrupted_tasks()

    if not interrupted_tasks:
        logger.info("No interrupted tasks found")
        return

    # Group tasks by user
    tasks_by_user: dict[int, list[dict]] = {}
    for task_dict in interrupted_tasks:
        user_id = task_dict["user_id"]
        if user_id not in tasks_by_user:
            tasks_by_user[user_id] = []
        tasks_by_user[user_id].append(task_dict)

    logger.info(f"Found {len(interrupted_tasks)} interrupted tasks across {len(tasks_by_user)} users")

    # Notify each user
    for user_id, tasks in tasks_by_user.items():
        try:
            # Build notification message
            task_count = len(tasks)
            notification = "⚠️ Bot Restart Detected\n\n"
            notification += f"Found {task_count} task{'s' if task_count > 1 else ''} interrupted by restart:\n\n"

            # List interrupted tasks (max 5 to avoid message length issues)
            for task_dict in tasks[:5]:
                task_id = task_dict["task_id"]
                description = task_dict["description"]
                # Truncate long descriptions
                desc_preview = description[:60] + "..." if len(description) > 60 else description
                notification += f"• #{task_id}: {desc_preview}\n"

            if task_count > 5:
                notification += f"\n...and {task_count - 5} more\n"

            notification += "\nUse /retry to restart these tasks, or /status to view details."

            # Create inline keyboard for quick retry
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Retry All", callback_data="retry_all_interrupted"),
                    InlineKeyboardButton("📊 View Status", callback_data="view_status"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send notification
            await app.bot.send_message(chat_id=user_id, text=notification, reply_markup=reply_markup)
            logger.info(f"Notified user {user_id} about {task_count} interrupted tasks")

        except Exception as e:
            logger.error(f"Failed to notify user {user_id} about interrupted tasks: {e}", exc_info=True)


async def check_authorization(update: Update) -> bool:
    """Check if user is authorized"""
    user_id = update.effective_user.id

    if not ALLOWED_USERS or user_id not in ALLOWED_USERS:
        await update.message.reply_text("Unauthorized. Please contact the bot owner.")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return False

    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - priority command that executes immediately"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Clear conversation history on /start (executes immediately, bypassing queue)
    session_manager.clear_session(user_id)
    logger.info(f"Priority /start: Cleared session for user {user_id}")

    # Get recent changes
    try:
        result = subprocess.run(["git", "log", "--oneline", "-3"], cwd=BOT_REPOSITORY, capture_output=True, text=True)
        recent_changes = result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        recent_changes = None

    welcome_message = "<b>Started fresh</b>\n\n"

    if recent_changes:
        welcome_message += "<b>Recent updates:</b>\n"
        for line in recent_changes.split("\n")[:2]:  # Show last 2 commits
            # Format: hash message -> • message
            parts = line.split(" ", 1)
            if len(parts) == 2:
                welcome_message += f"• {parts[1]}\n"
        welcome_message += "\n"

    welcome_message += "Send me a message to get started!"

    await update.message.reply_text(welcome_message, parse_mode="HTML")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - show active tasks and errors in compact format"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Clean up stale pending tasks (older than 1 hour) to prevent clutter
    task_manager.cleanup_stale_pending_tasks(max_age_hours=1)

    # Clean up old failed tasks (older than 24 hours) to prevent clutter
    task_manager.clear_old_failed_tasks(user_id, older_than_hours=24)

    # Get active tasks only
    active_tasks = task_manager.get_active_tasks(user_id)

    # Get recent failed tasks (last 1 hour only, exclude repetitive failures)
    from datetime import datetime, timedelta

    recent_tasks = task_manager.get_user_tasks(user_id, limit=50)
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)

    failed_tasks = []
    seen_errors = set()
    for task in recent_tasks:
        if task.status != "failed":
            continue

        # Only show failures from last hour
        try:
            task_time = datetime.fromisoformat(task.created_at)
            if task_time < one_hour_ago:
                continue
        except ValueError:
            # Skip tasks with invalid timestamp format
            continue

        # Skip repetitive "Find todos" failures
        if "Find todos" in task.description:
            continue

        # Skip if we've seen this exact error before
        error_key = (task.description[:50], task.error[:100] if task.error else "")
        if error_key in seen_errors:
            continue

        seen_errors.add(error_key)
        failed_tasks.append(task)

        if len(failed_tasks) >= 3:
            break

    # Build compact status message (plain text - formatter will convert to HTML)
    message_parts = ["Status\n"]

    # Active Tasks - only show if there are any
    if active_tasks:
        message_parts.append(f"Active Tasks ({len(active_tasks)})")
        for task in active_tasks[:5]:  # Show up to 5 active tasks
            status_icon = "🔄" if task.status == "pending" else "▶️"
            message_parts.append(f"{status_icon} #{task.task_id} {task.description[:50]}")

            # Show latest activity if available
            latest_activity = task.get_latest_activity(limit=1)
            if latest_activity:
                activity = latest_activity[0]
                # Parse timestamp to show relative time
                from datetime import datetime

                try:
                    activity_time = datetime.fromisoformat(activity["timestamp"])
                    now = datetime.now()
                    elapsed = (now - activity_time).total_seconds()

                    if elapsed < 60:
                        time_str = f"{int(elapsed)}s ago"
                    elif elapsed < 3600:
                        time_str = f"{int(elapsed / 60)}m ago"
                    else:
                        time_str = f"{int(elapsed / 3600)}h ago"

                    message_parts.append(f"   └─ {activity['message'][:60]} ({time_str})")
                except Exception:
                    message_parts.append(f"   └─ {activity['message'][:60]}")

        message_parts.append("")

    # Failed tasks - only show if there are any
    if failed_tasks:
        message_parts.append(f"\nRecent Errors ({len(failed_tasks)})")
        for task in failed_tasks:
            error_preview = task.error[:60] if task.error else "Unknown error"
            message_parts.append(f"❌ #{task.task_id} {error_preview}")

    # Recently completed tasks with viewable results
    completed_tasks = [t for t in recent_tasks if t.status == "completed" and t.result and t not in active_tasks]
    if completed_tasks:
        message_parts.append(f"\n\nRecent Completions ({min(len(completed_tasks), 3)})")
        for task in completed_tasks[:3]:  # Show up to 3
            message_parts.append(f"✅ #{task.task_id} {task.description[:50]}")

    # If nothing to show
    if not active_tasks and not failed_tasks and not completed_tasks:
        message_parts.append("\n✓ No active tasks or errors")

    # Format and send using HTML formatter (handles entities properly)
    message = "\n".join(message_parts)

    # Add inline keyboard buttons for quick access to completed task results
    keyboard = []
    if completed_tasks:
        # Add buttons for viewing completed tasks (up to 3)
        for task in completed_tasks[:3]:
            button_text = f"📄 View #{task.task_id}"
            callback_data = f"view:{task.task_id}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    # Send with inline keyboard if available
    if reply_markup:
        formatted_message = format_telegram_response(message)
        if isinstance(formatted_message, list):
            # Send first chunk with keyboard, rest without
            await context.bot.send_message(
                chat_id=user_id, text=formatted_message[0], parse_mode="HTML", reply_markup=reply_markup
            )
            for chunk in formatted_message[1:]:
                await context.bot.send_message(chat_id=user_id, text=chunk, parse_mode="HTML")
        else:
            # Single message with keyboard
            await context.bot.send_message(
                chat_id=user_id,
                text=formatted_message[0] if isinstance(formatted_message, list) else formatted_message,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
    else:
        # No keyboard, use normal send
        await send_formatted_response(context, user_id, message)


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /view command - display task result as markdown document"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Check if task ID was provided
    if not context.args or len(context.args) == 0:
        # No task ID provided - show recent completed tasks
        recent_tasks = task_manager.get_user_tasks(user_id, limit=20)
        completed_tasks = [t for t in recent_tasks if t.status in ("completed", "failed") and (t.result or t.error)]

        if not completed_tasks:
            message = "No completed tasks with results.\n\nUse /view <task_id> to view a specific task result."
            await send_formatted_response(context, user_id, message)
            return

        message = "Recent Completed Tasks\n\n"
        for task in completed_tasks[:10]:  # Show up to 10
            status_icon = "✅" if task.status == "completed" else "❌"
            message += f"{status_icon} #{task.task_id} - {task.description[:50]}\n"

        message += "\n\nUse /view <task_id> to view result\nExample: /view " + completed_tasks[0].task_id
        await send_formatted_response(context, user_id, message)
        return

    # Task ID was provided
    task_id = context.args[0].lstrip("#")  # Remove # if present

    # Get task
    task = task_manager.get_task(task_id)
    if not task:
        message = f"Task #{task_id} not found."
        await send_formatted_response(context, user_id, message)
        return

    # Check ownership
    if task.user_id != user_id:
        await update.message.reply_text("You don't have permission to view this task.")
        return

    # Check if task has a result
    if not task.result and not task.error:
        message = f"Task #{task_id} has no result yet.\nStatus: {task.status}"
        await send_formatted_response(context, user_id, message)
        return

    # Create markdown document with task result
    if task.status == "completed" and task.result:
        content = f"# Task Result: {task.description}\n\n"
        content += f"**Task ID:** {task.task_id}\n"
        content += f"**Status:** {task.status}\n"
        content += f"**Model:** {task.model}\n"
        content += f"**Completed:** {task.updated_at}\n\n"
        content += "---\n\n"
        content += task.result
        filename = f"task_{task_id}_result.md"
        summary = f"✅ Task #{task_id} Result\n\n{task.description[:100]}\n\n📄 Full result attached..."
    else:
        # Failed task
        content = f"# Task Error: {task.description}\n\n"
        content += f"**Task ID:** {task.task_id}\n"
        content += f"**Status:** {task.status}\n"
        content += f"**Model:** {task.model}\n"
        content += f"**Failed:** {task.updated_at}\n\n"
        content += "---\n\n"
        content += f"## Error\n\n{task.error or 'Unknown error'}"
        filename = f"task_{task_id}_error.md"
        summary = f"❌ Task #{task_id} Error\n\n{task.description[:100]}\n\n📄 Error details attached..."

    # Create temporary file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix=f"task_{task_id}_") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    # Send summary message
    await send_formatted_response(context, user_id, summary)

    # Send document
    try:
        with open(tmp_path, "rb") as doc:
            await context.bot.send_document(chat_id=user_id, document=doc, filename=filename)
    finally:
        # Clean up temporary file
        Path(tmp_path).unlink(missing_ok=True)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboard buttons"""
    query = update.callback_query
    await query.answer()  # Acknowledge the button press

    user_id = query.from_user.id

    # Check authorization
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        await query.edit_message_text("You are not authorized to use this bot.")
        return

    # Parse callback data
    data = query.data

    # Handle retry all interrupted tasks
    if data == "retry_all_interrupted":
        await query.edit_message_text("🔄 Retrying interrupted tasks...")

        # Get all stopped tasks for this user that were interrupted
        cursor = db.conn.cursor()
        cursor.execute(
            """
            SELECT task_id, description, workspace, model, agent_type, context
            FROM tasks
            WHERE user_id = ? AND status = 'stopped'
            AND (error = 'Task stopped due to bot restart' OR error = 'Task stopped during bot shutdown')
            ORDER BY created_at ASC
        """,
            (user_id,),
        )
        interrupted_tasks = cursor.fetchall()

        if not interrupted_tasks:
            await context.bot.send_message(chat_id=user_id, text="No interrupted tasks found to retry.")
            return

        # Create new tasks for each interrupted task
        retry_count = 0
        for task_row in interrupted_tasks:
            old_task_id, description, workspace, model, agent_type, task_context = task_row

            try:
                new_task = await task_manager.create_task(
                    user_id=user_id,
                    description=description,
                    workspace=workspace,
                    model=model,
                    agent_type=agent_type,
                    context=task_context,
                )

                # Submit to agent pool
                await agent_pool.submit(
                    execute_code_task,
                    task=new_task,
                    update=query,
                    context=context,
                    priority=TaskPriority.NORMAL,
                )

                retry_count += 1
                logger.info(f"Retried interrupted task {old_task_id} as new task {new_task.task_id}")

            except Exception as e:
                logger.error(f"Failed to retry interrupted task {old_task_id}: {e}", exc_info=True)

        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Restarted {retry_count} task{'s' if retry_count != 1 else ''}.\n\nUse /status to monitor progress.",
        )
        return

    # Handle view status button
    elif data == "view_status":
        # Redirect to status command - we need to create a fake Update object
        # Since show_task_status expects Update with message, we'll send status directly
        await query.answer()

        # Get active tasks
        active_tasks = task_manager.get_active_tasks(user_id)

        # Get recent completed/failed tasks
        recent_tasks = task_manager.get_user_tasks(user_id, limit=5)
        completed = [t for t in recent_tasks if t.status == "completed"][:3]
        failed = [t for t in recent_tasks if t.status == "failed"][:3]

        # Build status message
        message_parts = ["📊 Task Status\n"]

        # Active tasks
        if active_tasks:
            message_parts.append(f"\n⚙️ Active Tasks ({len(active_tasks)}):")
            for task in active_tasks:
                status_icon = "⏳" if task.status == "pending" else "▶️"
                message_parts.append(f"{status_icon} #{task.task_id} - {task.description[:50]}...")
        else:
            message_parts.append("\n✅ No active tasks")

        # Recent completed
        if completed:
            message_parts.append(f"\n\n✅ Recent Completed ({len(completed)}):")
            for task in completed:
                message_parts.append(f"• #{task.task_id} - {task.description[:40]}...")

        # Recent failed
        if failed:
            message_parts.append(f"\n\n❌ Recent Failed ({len(failed)}):")
            for task in failed:
                message_parts.append(f"• #{task.task_id} - {task.description[:40]}...")

        message_parts.append("\n\n💡 Use /status for full details")

        # Send as new message
        message = "\n".join(message_parts)
        formatted_chunks = format_telegram_response(message, max_length=4000)
        for chunk in formatted_chunks:
            await context.bot.send_message(chat_id=user_id, text=chunk, parse_mode="HTML")

        return

    # Handle view specific task
    elif data.startswith("view:"):
        task_id = data.split(":", 1)[1]

        # Get task
        task = task_manager.get_task(task_id)
        if not task:
            await query.edit_message_text(f"Task #{task_id} not found.")
            return

        # Check ownership
        if task.user_id != user_id:
            await query.edit_message_text("You don't have permission to view this task.")
            return

        # Check if task has a result
        if not task.result and not task.error:
            await query.edit_message_text(f"Task #{task_id} has no result yet.\nStatus: {task.status}")
            return

        # Create markdown document with task result
        if task.status == "completed" and task.result:
            content = f"# Task Result: {task.description}\n\n"
            content += f"**Task ID:** {task.task_id}\n"
            content += f"**Status:** {task.status}\n"
            content += f"**Model:** {task.model}\n"
            content += f"**Completed:** {task.updated_at}\n\n"
            content += "---\n\n"
            content += task.result
            filename = f"task_{task_id}_result.md"
            summary = f"✅ Task #{task_id} Result\n\n{task.description[:100]}\n\n📄 Full result attached..."
        else:
            # Failed task
            content = f"# Task Error: {task.description}\n\n"
            content += f"**Task ID:** {task.task_id}\n"
            content += f"**Status:** {task.status}\n"
            content += f"**Model:** {task.model}\n"
            content += f"**Failed:** {task.updated_at}\n\n"
            content += "---\n\n"
            content += f"## Error\n\n{task.error or 'Unknown error'}"
            filename = f"task_{task_id}_error.md"
            summary = f"❌ Task #{task_id} Error\n\n{task.description[:100]}\n\n📄 Error details attached..."

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix=f"task_{task_id}_") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Send document
        try:
            formatted_summary = format_telegram_response(summary)
            summary_text = formatted_summary[0] if isinstance(formatted_summary, list) else formatted_summary

            # Send as new message (not editing the status message)
            await context.bot.send_message(chat_id=user_id, text=summary_text, parse_mode="HTML")

            with open(tmp_path, "rb") as doc:
                await context.bot.send_document(chat_id=user_id, document=doc, filename=filename)
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)


async def retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /retry command - retry failed tasks"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Check if task ID was provided
    if context.args and len(context.args) > 0:
        # Retry specific task
        task_id = context.args[0].lstrip("#")  # Remove # if present

        # Check if task exists and belongs to user
        task = task_manager.get_task(task_id)
        if not task:
            message = f"Task #{task_id} not found."
            await send_formatted_response(context, user_id, message)
            return

        if task.user_id != user_id:
            await update.message.reply_text("You don't have permission to retry this task.")
            return

        if task.status != "failed":
            message = f"Task #{task_id} is not failed (status: {task.status})."
            await send_formatted_response(context, user_id, message)
            return

        # Retry the task
        new_task = task_manager.retry_task(task_id)
        if new_task:
            # Submit task to worker pool (HIGH priority - user retry request)
            await agent_pool.submit(execute_code_task, new_task, update, context, priority=TaskPriority.HIGH)

            message = f"Task Retry Started #{new_task.task_id}\n\n"
            message += f"Retrying: {task.description}\n"
            message += f"Original: #{task_id}\n"
            message += f"Previous error: {task.error[:80] if task.error else 'Unknown'}"

            await send_formatted_response(context, user_id, message)
        else:
            await update.message.reply_text("Failed to retry task. Please try again.")

    else:
        # Show list of failed tasks
        failed_tasks = task_manager.get_failed_tasks(user_id, limit=10)

        if not failed_tasks:
            await update.message.reply_text("No failed tasks to retry! 🎉")
            return

        message = "Failed Tasks\n\n"
        message += f"Found {len(failed_tasks)} failed task(s):\n\n"

        for task in failed_tasks[:5]:  # Show up to 5
            error_preview = task.error[:60] if task.error else "Unknown error"
            message += f"❌ #{task.task_id} - {task.description[:50]}\n"
            message += f"   Error: {error_preview}\n\n"

        if len(failed_tasks) > 5:
            message += f"... and {len(failed_tasks) - 5} more\n\n"

        message += "\nUse /retry <task_id> to retry a specific task\n"
        message += "Example: /retry " + failed_tasks[0].task_id

        await send_formatted_response(context, user_id, message)


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command - stop a running task"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Check if task ID was provided
    if not context.args or len(context.args) == 0:
        # No task ID provided - show usage
        active_tasks = task_manager.get_active_tasks(user_id)

        if not active_tasks:
            await update.message.reply_text("No active tasks to stop.")
            return

        message = "Active Tasks\n\n"
        message += "Use /stop <task_id> to stop a specific task\n\n"

        for task in active_tasks[:5]:  # Show up to 5 active tasks
            status_icon = "🔄" if task.status == "pending" else "▶️"
            message += f"{status_icon} #{task.task_id} - {task.description[:50]}\n"

        if len(active_tasks) > 5:
            message += f"\n... and {len(active_tasks) - 5} more"

        message += f"\n\nExample: /stop {active_tasks[0].task_id}"

        await send_formatted_response(context, user_id, message)
        return

    # Stop specific task
    task_id = context.args[0].lstrip("#")  # Remove # if present

    # Check if task exists and belongs to user
    task = task_manager.get_task(task_id)
    if not task:
        message = f"Task #{task_id} not found."
        await send_formatted_response(context, user_id, message)
        return

    if task.user_id != user_id:
        await update.message.reply_text("You don't have permission to stop this task.")
        return

    # Stop the task
    success, message = await task_manager.stop_task(task_id)

    if success:
        message = f"Task Stopped #{task_id}\n\n{task.description}\n\nYou can retry it later with /retry {task_id}"

    await send_formatted_response(context, user_id, message)


async def stopall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stopall command - stop all active tasks"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Get active tasks
    active_tasks = task_manager.get_active_tasks(user_id)

    if not active_tasks:
        await update.message.reply_text("No active tasks to stop.")
        return

    # Stop all active tasks
    stopped_count, failed_count, failed_task_ids = await task_manager.stop_all_tasks(user_id)

    # Build response message
    message = f"Stopped {stopped_count} task(s)"

    if failed_count > 0:
        message += f"\n\nFailed to stop {failed_count} task(s):"
        for task_id in failed_task_ids:
            message += f"\n• #{task_id}"

    if stopped_count > 0:
        message += "\n\nYou can retry stopped tasks with /retry"

    await send_formatted_response(context, user_id, message)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command - priority command that executes immediately"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id

    # Check if user wants to clear errors specifically
    if context.args and len(context.args) > 0 and context.args[0].lower() == "errors":
        # Clear all failed tasks immediately
        all_failed = task_manager.get_failed_tasks(user_id, limit=1000)
        cleared_count = 0
        for task in all_failed:
            if task_manager.db.delete_task(task.task_id):
                cleared_count += 1

        if cleared_count > 0:
            logger.info(f"Manually cleared {cleared_count} failed tasks for user {user_id}")
            await update.message.reply_text(f"Cleared {cleared_count} failed task(s) from history.")
        else:
            await update.message.reply_text("No failed tasks to clear!")
        return

    # Clear the session immediately (bypasses queue)
    session_manager.clear_session(user_id)
    logger.info(f"Priority /clear: Cleared session for user {user_id}")

    # Broadcast clear event to web chat clients
    try:
        from monitoring.server import socketio
        socketio.emit("clear_chat", {"user_id": str(user_id)}, room=str(user_id))
        logger.debug(f"Broadcasted clear_chat event for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to broadcast clear_chat event: {e}")

    await update.message.reply_text("Conversation cleared! Starting fresh.")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart command - gracefully restart the bot"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    logger.info(f"Restart requested by user {user_id}")

    # Send acknowledgment and wait for it to complete
    restart_msg = None
    try:
        restart_msg = await update.message.reply_text("🔄 Restarting...")
        logger.info(f"Sent restart message to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send restart acknowledgment: {e}", exc_info=True)
        # Don't restart if we can't even send the message
        await update.message.reply_text("Failed to initiate restart. Please try again.")
        return

    # Save restart state immediately (synchronously)
    import json
    import time

    restart_state = {
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": restart_msg.message_id if restart_msg else None,
        "timestamp": time.time(),  # Use Unix timestamp, not event loop time
    }

    # Use centralized config path for restart state
    restart_state_path = Path(RESTART_STATE_FILE_STR)
    restart_state_path.parent.mkdir(exist_ok=True)
    with open(restart_state_path, "w") as f:
        json.dump(restart_state, f)

    logger.info(f"Saved restart state for user {user_id}")

    # Schedule exit after ensuring message is sent
    async def delayed_exit():
        # Give more time for the message to be fully delivered
        await asyncio.sleep(1.0)
        logger.info("Exiting for restart...")
        import os

        # Restart monitoring server via launchd
        try:
            logger.info("Restarting monitoring server...")
            subprocess.run(
                ["launchctl", "kickstart", "-k", "gui/501/com.agentlab.monitoring"], capture_output=True, timeout=5
            )
            logger.info("Monitoring server restart initiated")
        except Exception as e:
            logger.error(f"Failed to restart monitoring server: {e}", exc_info=True)

        # Flush logs before exit
        for handler in logging.root.handlers:
            handler.flush()

        # Exit with non-zero code to trigger launchd restart of bot
        os._exit(42)  # Exit code 42 = intentional restart (launchd auto-restarts on non-zero)

    asyncio.create_task(delayed_exit())




def is_priority_command(message_text: str) -> bool:
    """
    Check if message is a priority command that should bypass the queue.
    Priority commands: /restart, /start, /clear

    These need immediate execution even if bot is processing something.
    """
    if not message_text:
        return False

    text_lower = message_text.lower().strip()
    priority_commands = ["/restart", "restart", "/start", "start", "/clear", "clear"]

    return any(text_lower == cmd or text_lower.startswith(cmd + " ") for cmd in priority_commands)


def extract_workspace_from_message(message: str) -> tuple[str | None, str]:
    """
    Extract workspace path from message if specified
    Returns: (workspace_path, cleaned_message)

    Supports patterns like:
    - "in /path/to/repo, do X"
    - "in ~/projects/myapp do X"
    - "for repository /path/repo, do X"
    """
    import re

    # Pattern: "in <path>, <rest>" or "in <path> <rest>"
    pattern1 = r"^in\s+([~/\w\-/.]+)[,\s]+(.+)$"
    match = re.match(pattern1, message, re.IGNORECASE)
    if match:
        workspace = os.path.expanduser(match.group(1).strip())
        cleaned = match.group(2).strip()
        return workspace, cleaned

    # Pattern: "for repository <path>, <rest>"
    pattern2 = r"^for\s+(?:repository|repo|project)\s+([~/\w\-/.]+)[,\s]+(.+)$"
    match = re.match(pattern2, message, re.IGNORECASE)
    if match:
        workspace = os.path.expanduser(match.group(1).strip())
        cleaned = match.group(2).strip()
        return workspace, cleaned

    return None, message


def detect_task_type(message: str) -> str:
    """
    Detect if message requires code execution or just chat
    Returns: 'code_task', 'chat', 'status_query'
    """
    message_lower = message.lower()

    # Code task keywords
    code_keywords = [
        "modify",
        "change",
        "update",
        "fix",
        "refactor",
        "add",
        "create",
        "build",
        "implement",
        "write code",
        "edit",
        "commit",
        "git",
        "file",
        "repository",
        "repo",
    ]

    # Status query keywords
    status_keywords = ["status", "progress", "tasks", "running"]

    # Check for status queries
    if any(kw in message_lower for kw in status_keywords):
        return "status_query"

    # Check for code tasks
    if any(kw in message_lower for kw in code_keywords):
        return "code_task"

    return "chat"


def _create_pid_callback(task_id: str):
    """
    Create a PID callback for task execution.

    Args:
        task_id: Task ID for tracking

    Returns:
        Callback function that saves PID when process starts
    """

    def save_pid_immediately(pid: int):
        """Called by claude_pool as soon as process starts"""
        asyncio.create_task(task_manager.update_task(task_id, pid=pid))
        logger.info(f"Task {task_id} process started with PID {pid}")

    return save_pid_immediately


def _create_progress_callback(task_id: str):
    """
    Create a progress callback for task execution.

    Args:
        task_id: Task ID for tracking

    Returns:
        Callback function that logs progress updates
    """

    def send_progress_update(status_message: str, elapsed_seconds: int):
        """Called periodically with progress updates"""
        # Extract output line count if present in message
        output_lines = None
        if "output lines" in status_message:
            import re

            match = re.search(r"(\d+) output lines", status_message)
            if match:
                output_lines = int(match.group(1))

        # Log to task manager (stored for status queries and dashboard)
        asyncio.create_task(task_manager.log_activity(task_id, status_message, output_lines, save=True))

    return send_progress_update


async def _handle_task_result(task: "Task", success: bool, result: str, workflow: str | None) -> tuple[str, str]:
    """
    Update task status and prepare notification messages.

    Args:
        task: Task object
        success: Whether task succeeded
        result: Task result or error message
        workflow: Workflow name (if applicable)

    Returns:
        Tuple of (notification message, full response for attachment)
    """
    if success:
        await task_manager.update_task(task.task_id, status="completed", result=result, workflow=workflow)
        logger.info(f"Task {task.task_id} completed successfully")

        notification = f"Task Complete #{task.task_id}\n\n{task.description}\n\n📄 Full response attached..."
        full_response = f"{task.description}\n\n{result}"
    else:
        await task_manager.update_task(task.task_id, status="failed", error=result, workflow=workflow)
        logger.error(f"Task {task.task_id} failed: {result}", exc_info=True)

        notification = f"Task Failed #{task.task_id}\n\n{task.description}\n\n📄 Error details attached..."
        full_response = f"{task.description}\n\n{result}"

    return notification, full_response


async def _send_task_result_document(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, task_id: str, content: str, success: bool
):
    """
    Send task result as a markdown document attachment.

    Args:
        context: Telegram context
        user_id: User ID to send document to
        task_id: Task ID for filename
        content: Document content
        success: Whether task succeeded (affects filename)
    """
    filename = f"task_{task_id}_{'result' if success else 'error'}.md"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, prefix=f"task_{task_id}_") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as doc:
            await context.bot.send_document(chat_id=user_id, document=doc, filename=filename)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def execute_code_task(task: "Task", update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute a code task in the background with full tool access"""
    user_id = update.effective_user.id

    try:
        # Update task status
        await task_manager.update_task(task.task_id, status="running")
        logger.info(f"Starting task execution: {task.task_id} in {task.workspace}")

        workspace_path = Path(task.workspace)

        # Execute using Claude session pool - always routes via workflow slash commands
        success, result, pid, workflow = await claude_pool.execute_task(
            task_id=task.task_id,
            description=task.description,
            workspace=Path(task.workspace),
            bot_repo_path=BOT_REPOSITORY,
            model=task.model,
            context=task.context,
            pid_callback=_create_pid_callback(task.task_id),
            progress_callback=_create_progress_callback(task.task_id),
        )

        # Update task and prepare notification
        notification, full_response = await _handle_task_result(task, success, result, workflow)

        # Send minimal inline notification
        await send_formatted_response(context, user_id, notification)

        # Send full result as markdown document attachment
        await _send_task_result_document(context, user_id, task.task_id, full_response, success)

    except Exception as e:
        logger.error(f"Task execution error for {task.task_id}: {e}", exc_info=True)
        await task_manager.update_task(task.task_id, status="failed", error=str(e))

        # Cleanup failed task branch (if workspace_path is defined)
        if "workspace_path" in locals():
            from tasks import cleanup_task_branch

            cleanup_task_branch(task.task_id, workspace_path, force=False)
            logger.info(f"Task {task.task_id} exception, branch preserved for debugging")

        # Prepare error notification
        notification = f"Task Failed #{task.task_id}\n\n{task.description}\n\n📄 Error details attached..."
        full_response = f"{task.description}\n\nUnexpected error: {str(e)}"

        # Send minimal inline notification
        await send_formatted_response(context, user_id, notification)

        # Send error details as markdown document attachment
        await _send_task_result_document(context, user_id, task.task_id, full_response, success=False)


async def show_task_status(user_id: int, update: Update):
    """Show user's task status"""
    # Get active tasks
    active_tasks = task_manager.get_active_tasks(user_id)

    # Get recent completed/failed tasks
    recent_tasks = task_manager.get_user_tasks(user_id, limit=5)
    completed = [t for t in recent_tasks if t.status == "completed"][:3]
    failed = [t for t in recent_tasks if t.status == "failed"][:3]

    # Build status message (plain text - formatter will convert to HTML)
    message_parts = ["Task Status\n"]

    # Active tasks
    if active_tasks:
        message_parts.append(f"\nActive Tasks ({len(active_tasks)}):")
        for task in active_tasks:
            status_icon = "[P]" if task.status == "pending" else "[R]"
            message_parts.append(f"{status_icon} #{task.task_id} - {task.description[:50]}...")
    else:
        message_parts.append("\nNo active tasks")

    # Recent completed
    if completed:
        message_parts.append(f"\n\nRecent Completed ({len(completed)}):")
        for task in completed:
            message_parts.append(f"• #{task.task_id} - {task.description[:40]}...")

    # Recent failed
    if failed:
        message_parts.append(f"\n\nRecent Failed ({len(failed)}):")
        for task in failed:
            message_parts.append(f"• #{task.task_id} - {task.description[:40]}...")

    message_parts.append("\n\nUse task ID to see details")

    # Format and send using HTML formatter
    message = "\n".join(message_parts)
    formatted_chunks = format_telegram_response(message, max_length=4000)
    for chunk in formatted_chunks:
        await update.message.reply_text(chunk, parse_mode="HTML")


async def process_message_async(
    user_id: int,
    message_text: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ack_message_id: int | None = None,
):
    """Process message asynchronously in background"""
    try:
        # Get conversation history
        session = session_manager.get_session(user_id)
        history = [{"role": msg.role, "content": msg.content} for msg in session.history] if session else []

        # Get workspace and discover repositories
        current_workspace = session_manager.get_workspace(user_id)
        available_repos = discover_repositories(WORKSPACE_PATH)

        # Check for uncommitted changes blocking work
        git_tracker = get_git_tracker()
        target_repo = current_workspace or WORKSPACE_PATH
        blocking_msg = git_tracker.get_blocking_message(target_repo)

        if blocking_msg:
            response = blocking_msg
            background_task_info = None
        else:
            # Get active tasks info from database
            cursor = task_manager.db.conn.cursor()
            cursor.execute(
                """
                SELECT task_id, description, status, workspace
                FROM tasks
                WHERE status IN ('pending', 'running')
            """
            )
            active_tasks_info = [
                {"task_id": row[0], "description": row[1], "status": row[2], "workspace": row[3]}
                for row in cursor.fetchall()
            ]

            # Ask Claude via API (fast, no file tools needed for routing)
            response, background_task_info, usage_info = await ask_claude(
                user_query=message_text,
                input_method="text",
                conversation_history=history,
                current_workspace=current_workspace,
                bot_repository=BOT_REPOSITORY,
                workspace_path=WORKSPACE_PATH,
                available_repositories=available_repos,
                active_tasks=active_tasks_info,
            )

            # Log user message to analytics database
            analytics_db.log_message(
                user_id=user_id,
                role="user",
                content=message_text,
                input_method="text",
            )

            # Log assistant response to analytics database (if we got usage info)
            if usage_info:
                analytics_db.log_message(
                    user_id=user_id,
                    role="assistant",
                    content=response,
                    tokens_input=usage_info.get("input_tokens"),
                    tokens_output=usage_info.get("output_tokens"),
                    model="claude-haiku-4-5",
                    input_method="text",
                )

        # Delete acknowledgment message if it exists
        if ack_message_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=ack_message_id)
            except Exception as e:
                logger.debug(f"Could not delete acknowledgment message: {e}")

        if not response:
            # Fallback to direct Claude response
            logger.warning("Claude API returned empty response, using fallback")
            response = await claude_client.send_message(user_id, message_text)
            background_task_info = None

        # Check if background task should be created
        if background_task_info:
            task_desc = background_task_info["description"]
            user_message = background_task_info["user_message"]
            task_context = background_task_info.get("context")  # Context summary from Claude API

            # Create background task - ALWAYS use orchestrator (it delegates to sub-agents)
            # Resolve workspace to valid git repository
            workspace = resolve_git_workspace(current_workspace, WORKSPACE_PATH, BOT_REPOSITORY)
            if workspace is None:
                await update.message.reply_text(
                    "⚠️ Cannot create task: No git repository available.\n\n"
                    "Tasks require branch isolation. Use /workspace to set a git repository."
                )
                return

            task = await task_manager.create_task(
                user_id=user_id,
                description=task_desc,
                workspace=str(workspace),
                model="sonnet",
                agent_type="orchestrator",  # Workflow slash commands orchestrate directly
                context=task_context,
            )

            # Submit task to agent pool (non-blocking, HIGH priority - user request)
            logger.info(f"Submitted orchestrator task {task.task_id} to agent pool")
            await agent_pool.submit(execute_code_task, task, update, context, priority=TaskPriority.HIGH)

            # Send user-facing message
            response = f"Task #{task.task_id} started.\n\n{user_message}"

        # Queue session writes to agent pool (non-blocking, LOW priority - not urgent)
        await agent_pool.submit(_async_add_session_message, user_id, "user", message_text, priority=TaskPriority.LOW)
        await agent_pool.submit(_async_add_session_message, user_id, "assistant", response, priority=TaskPriority.LOW)

        # Format and send response to user (uses helper that handles document attachment)
        await send_formatted_response(context, user_id, response, workspace_path=session_manager.get_workspace(user_id))

    except Exception as e:
        logger.error(f"Error in async message processing for user {user_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=user_id, text="An error occurred while processing your message. Please try again."
        )


async def _handle_message_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Implementation of message handling (called from queue)"""
    user_id = update.effective_user.id
    message_text = update.message.text

    logger.info(f"User {user_id} (text): {message_text}")

    # Check rate limits
    allowed, error_msg = rate_limiter.check_rate_limit(user_id)
    if not allowed:
        await update.message.reply_text(error_msg)
        return

    # Record rate limit request
    rate_limiter.record_request(user_id)

    # Send acknowledgment message
    ack_message = await update.message.reply_text("Thinking")
    ack_message_id = ack_message.message_id

    # Launch background task for orchestrator processing (no await)
    # This allows the function to return immediately while work happens async
    asyncio.create_task(process_message_async(user_id, message_text, update, context, ack_message_id))

    logger.info(f"Queued async processing for user {user_id}: {message_text[:60]}...")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queue text messages for sequential processing, with priority for commands"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id
    message_text = update.message.text or ""

    # Check if this is a priority command (should not normally happen since
    # CommandHandler catches /start, /clear, etc., but good defensive check)
    if is_priority_command(message_text):
        logger.info(f"Priority text command detected: {message_text[:50]}")
        # Queue with high priority
        await queue_manager.enqueue_message(
            user_id=user_id,
            update=update,
            context=context,
            handler=_handle_message_impl,
            handler_name="priority_text_command",
            priority=10,
        )
    else:
        # Queue with normal priority (no acknowledgment - orchestrator responds fast with Haiku)
        await queue_manager.enqueue_message(
            user_id=user_id,
            update=update,
            context=context,
            handler=_handle_message_impl,
            handler_name="text_message",
            priority=0,
        )


def transcribe_audio(file_path: str) -> str | None:
    """Transcribe audio file using Whisper (sync function)"""
    if not WHISPER_AVAILABLE:
        return None

    try:
        # Load model (tiny for speed, can upgrade to base/small/medium)
        model = whisper.load_model("tiny")

        # Transcribe
        result = model.transcribe(file_path)
        return result["text"].strip()
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}", exc_info=True)
        return None


async def process_document_async(
    user_id: int, message_text: str, tmp_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Process document asynchronously in background"""
    try:
        # Get conversation history
        session = session_manager.get_session(user_id)
        history = [{"role": msg.role, "content": msg.content} for msg in session.history] if session else []

        # Get workspace and repos
        current_workspace = session_manager.get_workspace(user_id)
        available_repos = discover_repositories(WORKSPACE_PATH)

        # Check git
        git_tracker = get_git_tracker()
        target_repo = current_workspace or WORKSPACE_PATH
        blocking_msg = git_tracker.get_blocking_message(target_repo)

        if blocking_msg:
            response = blocking_msg
            background_task_info = None
        else:
            # Get active tasks from database
            cursor = task_manager.db.conn.cursor()
            cursor.execute(
                """
                SELECT task_id, description, status, workspace
                FROM tasks
                WHERE status IN ('pending', 'running')
            """
            )
            active_tasks_info = [
                {"task_id": row[0], "description": row[1], "status": row[2], "workspace": row[3]}
                for row in cursor.fetchall()
            ]

            # Ask Claude API
            response, background_task_info, usage_info = await ask_claude(
                user_query=message_text,
                input_method="text",
                conversation_history=history,
                current_workspace=current_workspace,
                bot_repository=BOT_REPOSITORY,
                workspace_path=WORKSPACE_PATH,
                available_repositories=available_repos,
                active_tasks=active_tasks_info,
            )

            # Log user message to analytics database
            analytics_db.log_message(
                user_id=user_id,
                role="user",
                content=message_text,
                input_method="text",
            )

            # Log assistant response to analytics database (if we got usage info)
            if usage_info:
                analytics_db.log_message(
                    user_id=user_id,
                    role="assistant",
                    content=response,
                    tokens_input=usage_info.get("input_tokens"),
                    tokens_output=usage_info.get("output_tokens"),
                    model="claude-haiku-4-5",
                    input_method="text",
                )

        if not response:
            logger.warning("Claude API returned empty response (document), using fallback")
            response = await claude_client.send_message(user_id, message_text)
            background_task_info = None

        # Check if background task should be created
        if background_task_info:
            task_desc = background_task_info["description"]
            user_message = background_task_info["user_message"]
            task_context = background_task_info.get("context")  # Context summary from Claude API

            # Resolve workspace to valid git repository
            workspace = resolve_git_workspace(current_workspace, WORKSPACE_PATH, BOT_REPOSITORY)
            if workspace is None:
                await update.message.reply_text(
                    "⚠️ Cannot create task: No git repository available.\n\n"
                    "Tasks require branch isolation. Use /workspace to set a git repository."
                )
                return

            task = await task_manager.create_task(
                user_id=user_id,
                description=task_desc,
                workspace=str(workspace),
                model="sonnet",
                agent_type="orchestrator",  # Workflow slash commands orchestrate directly
                context=task_context,
            )
            logger.info(f"Submitted orchestrator task {task.task_id} to worker pool (document)")
            await agent_pool.submit(execute_code_task, task, update, context, priority=TaskPriority.HIGH)
            response = f"Task #{task.task_id} started.\n\n{user_message}"

        # Queue session writes to agent pool (non-blocking, LOW priority - not urgent)
        await agent_pool.submit(_async_add_session_message, user_id, "user", message_text, priority=TaskPriority.LOW)
        await agent_pool.submit(_async_add_session_message, user_id, "assistant", response, priority=TaskPriority.LOW)

        # Format and send response to user (uses helper that handles document attachment)
        await send_formatted_response(context, user_id, response, workspace_path=session_manager.get_workspace(user_id))

    except Exception as e:
        logger.error(f"Error in async document processing for user {user_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=user_id, text="An error occurred while processing your document. Please try again."
        )
    finally:
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)


async def _handle_document_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Implementation of document handling (called from queue)"""
    user_id = update.effective_user.id
    document = update.message.document
    caption = update.message.caption or ""

    logger.info(f"User {user_id} sent document: {document.file_name} ({document.mime_type})")

    # Check file size (limit to 20MB for safety)
    if document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("File too large. Maximum size is 20MB.")
        return

    # Show typing indicator
    await update.message.chat.send_action("typing")

    try:
        # Download file
        file = await context.bot.get_file(document.file_id)

        # Create temp file with original extension
        file_ext = Path(document.file_name).suffix or ".txt"
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
            tmp_path = tmp.name

        # Download to temp file
        await file.download_to_drive(tmp_path)
        logger.info(f"Downloaded document to {tmp_path}")

        # Read file content (text-based files only)
        try:
            with open(tmp_path, encoding="utf-8") as f:
                file_content = f.read()
        except UnicodeDecodeError:
            # Binary file (PDF, images, etc.) - just provide path
            file_content = f"[Binary file: {document.file_name}]"
            logger.info(f"Binary file detected: {document.file_name}")

        # Build message with file context
        if caption:
            message_text = f"{caption}\n\n[Attached file: {document.file_name}]\n{file_content[:2000]}"
        else:
            message_text = f"I've uploaded a file: {document.file_name}\n\n{file_content[:2000]}"

        if len(file_content) > 2000:
            message_text += f"\n\n... (file truncated, total {len(file_content)} chars)"

        logger.info(f"User {user_id} (document): {message_text[:100]}...")

        # Launch background task for processing (no await)
        asyncio.create_task(process_document_async(user_id, message_text, tmp_path, update, context))

        logger.info(f"Queued async processing for document from user {user_id}")

    except Exception as e:
        logger.error(f"Document download/prep error: {e}", exc_info=True)
        await update.message.reply_text("Error downloading file. Please try again.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queue document uploads for sequential processing"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id
    await queue_manager.enqueue_message(
        user_id=user_id, update=update, context=context, handler=_handle_document_impl, handler_name="document"
    )


async def process_photo_async(
    user_id: int, message_text: str, tmp_path: str, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Process photo asynchronously in background"""
    try:
        # Get conversation history
        session = session_manager.get_session(user_id)
        history = [{"role": msg.role, "content": msg.content} for msg in session.history] if session else []

        # Get workspace and repos
        current_workspace = session_manager.get_workspace(user_id)
        available_repos = discover_repositories(WORKSPACE_PATH)

        # Check git
        git_tracker = get_git_tracker()
        target_repo = current_workspace or WORKSPACE_PATH
        blocking_msg = git_tracker.get_blocking_message(target_repo)

        if blocking_msg:
            response = blocking_msg
            background_task_info = None
        else:
            # Get active tasks from database
            cursor = task_manager.db.conn.cursor()
            cursor.execute(
                """
                SELECT task_id, description, status, workspace
                FROM tasks
                WHERE status IN ('pending', 'running')
            """
            )
            active_tasks_info = [
                {"task_id": row[0], "description": row[1], "status": row[2], "workspace": row[3]}
                for row in cursor.fetchall()
            ]

            # Ask Claude API with image
            response, background_task_info, usage_info = await ask_claude(
                user_query=message_text,
                input_method="text",
                conversation_history=history,
                current_workspace=current_workspace,
                bot_repository=BOT_REPOSITORY,
                workspace_path=WORKSPACE_PATH,
                available_repositories=available_repos,
                active_tasks=active_tasks_info,
                image_path=tmp_path,  # Pass image file path
            )

            # Log user message to analytics database
            analytics_db.log_message(
                user_id=user_id,
                role="user",
                content=message_text,
                input_method="text",
                has_image=True,
            )

            # Log assistant response to analytics database (if we got usage info)
            if usage_info:
                analytics_db.log_message(
                    user_id=user_id,
                    role="assistant",
                    content=response,
                    tokens_input=usage_info.get("input_tokens"),
                    tokens_output=usage_info.get("output_tokens"),
                    model="claude-haiku-4-5",
                    input_method="text",
                    has_image=True,
                )

        if not response:
            logger.warning("Claude API returned empty response (photo), using fallback")
            response = await claude_client.send_message(user_id, message_text)
            background_task_info = None

        # Check if background task should be created
        if background_task_info:
            task_desc = background_task_info["description"]
            user_message = background_task_info["user_message"]
            task_context = background_task_info.get("context")  # Context summary from Claude API

            # Resolve workspace to valid git repository
            workspace = resolve_git_workspace(current_workspace, WORKSPACE_PATH, BOT_REPOSITORY)
            if workspace is None:
                await update.message.reply_text(
                    "⚠️ Cannot create task: No git repository available.\n\n"
                    "Tasks require branch isolation. Use /workspace to set a git repository."
                )
                return

            task = await task_manager.create_task(
                user_id=user_id,
                description=task_desc,
                workspace=str(workspace),
                model="sonnet",
                agent_type="orchestrator",  # Workflow slash commands orchestrate directly
                context=task_context,
            )
            logger.info(f"Submitted orchestrator task {task.task_id} to worker pool (photo)")
            await agent_pool.submit(execute_code_task, task, update, context, priority=TaskPriority.HIGH)
            response = f"Task #{task.task_id} started.\n\n{user_message}"

        # Queue session writes to agent pool (non-blocking, LOW priority - not urgent)
        await agent_pool.submit(_async_add_session_message, user_id, "user", message_text, priority=TaskPriority.LOW)
        await agent_pool.submit(_async_add_session_message, user_id, "assistant", response, priority=TaskPriority.LOW)

        # Format and send response to user (uses helper that handles document attachment)
        await send_formatted_response(context, user_id, response, workspace_path=session_manager.get_workspace(user_id))

    except Exception as e:
        logger.error(f"Error in async photo processing for user {user_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=user_id, text="An error occurred while processing your image. Please try again."
        )
    finally:
        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)


async def _handle_photo_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Implementation of photo handling (called from queue)"""
    user_id = update.effective_user.id
    photo = update.message.photo[-1]  # Get highest resolution
    caption = update.message.caption or ""

    logger.info(f"User {user_id} sent photo")

    # Show typing indicator
    await update.message.chat.send_action("typing")

    try:
        # Download photo
        file = await context.bot.get_file(photo.file_id)

        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        # Download to temp file
        await file.download_to_drive(tmp_path)
        logger.info(f"Downloaded photo to {tmp_path}")

        # Build message with photo context
        if caption:
            message_text = f"{caption}\n\n[Attached image: photo.jpg]"
        else:
            message_text = "I've uploaded an image. Can you analyze it?"

        logger.info(f"User {user_id} (photo): {message_text}")

        # Launch background task for processing (no await)
        asyncio.create_task(process_photo_async(user_id, message_text, tmp_path, update, context))

        logger.info(f"Queued async processing for photo from user {user_id}")

    except Exception as e:
        logger.error(f"Photo download/prep error: {e}", exc_info=True)
        await update.message.reply_text("Error downloading image. Please try again.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queue photo uploads for sequential processing"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id
    await queue_manager.enqueue_message(
        user_id=user_id, update=update, context=context, handler=_handle_photo_impl, handler_name="photo"
    )


async def process_voice_async(
    user_id: int,
    transcription: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ack_message_id: int | None = None,
):
    """Process voice message asynchronously in background"""
    try:
        # Get conversation history
        session = session_manager.get_session(user_id)
        history = [{"role": msg.role, "content": msg.content} for msg in session.history] if session else []

        # Get workspace and discover repositories
        current_workspace = session_manager.get_workspace(user_id)
        available_repos = discover_repositories(WORKSPACE_PATH)

        # Check for uncommitted changes
        git_tracker = get_git_tracker()
        target_repo = current_workspace or WORKSPACE_PATH
        blocking_msg = git_tracker.get_blocking_message(target_repo)

        if blocking_msg:
            response = blocking_msg
            background_task_info = None
        else:
            # Get active tasks from database
            cursor = task_manager.db.conn.cursor()
            cursor.execute(
                """
                SELECT task_id, description, status, workspace
                FROM tasks
                WHERE status IN ('pending', 'running')
            """
            )
            active_tasks_info = [
                {"task_id": row[0], "description": row[1], "status": row[2], "workspace": row[3]}
                for row in cursor.fetchall()
            ]

            # Ask Claude via API with VOICE input (be permissive with errors)
            response, background_task_info, usage_info = await ask_claude(
                user_query=transcription,
                input_method="voice",  # Important: tells Claude to be permissive with voice transcription errors
                conversation_history=history,
                current_workspace=current_workspace,
                bot_repository=BOT_REPOSITORY,
                workspace_path=WORKSPACE_PATH,
                available_repositories=available_repos,
                active_tasks=active_tasks_info,
            )

            # Log user message to analytics database
            analytics_db.log_message(
                user_id=user_id,
                role="user",
                content=transcription,
                input_method="voice",
            )

            # Log assistant response to analytics database (if we got usage info)
            if usage_info:
                analytics_db.log_message(
                    user_id=user_id,
                    role="assistant",
                    content=response,
                    tokens_input=usage_info.get("input_tokens"),
                    tokens_output=usage_info.get("output_tokens"),
                    model="claude-haiku-4-5",
                    input_method="voice",
                )

        # Delete acknowledgment message if it exists
        if ack_message_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=ack_message_id)
            except Exception as e:
                logger.debug(f"Could not delete acknowledgment message: {e}")

        if not response:
            logger.warning("Claude API returned empty response (voice), using fallback")
            response = await claude_client.send_message(user_id, transcription)
            background_task_info = None

        # Check if background task should be created
        if background_task_info:
            task_desc = background_task_info["description"]
            user_message = background_task_info["user_message"]
            task_context = background_task_info.get("context")  # Context summary from Claude API

            # Resolve workspace to valid git repository
            workspace = resolve_git_workspace(current_workspace, WORKSPACE_PATH, BOT_REPOSITORY)
            if workspace is None:
                await update.message.reply_text(
                    "⚠️ Cannot create task: No git repository available.\n\n"
                    "Tasks require branch isolation. Use /workspace to set a git repository."
                )
                return

            task = await task_manager.create_task(
                user_id=user_id,
                description=task_desc,
                workspace=str(workspace),
                model="sonnet",
                agent_type="orchestrator",  # Workflow slash commands orchestrate directly
                context=task_context,
            )
            logger.info(f"Submitted orchestrator task {task.task_id} to worker pool (voice)")
            await agent_pool.submit(execute_code_task, task, update, context, priority=TaskPriority.HIGH)
            response = f"Task #{task.task_id} started.\n\n{user_message}"

        # Queue session writes to agent pool (non-blocking, LOW priority - not urgent)
        await agent_pool.submit(_async_add_session_message, user_id, "user", transcription, priority=TaskPriority.LOW)
        await agent_pool.submit(_async_add_session_message, user_id, "assistant", response, priority=TaskPriority.LOW)

        # Format and send response to user (uses helper that handles document attachment)
        await send_formatted_response(context, user_id, response, workspace_path=session_manager.get_workspace(user_id))

    except Exception as e:
        logger.error(f"Error in async voice processing for user {user_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=user_id, text="An error occurred while processing your voice message. Please try again."
        )


async def _handle_voice_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Implementation of voice handling (called from queue)"""
    user_id = update.effective_user.id
    voice_message = update.message.voice

    logger.info(f"User {user_id} sent voice message (duration: {voice_message.duration}s)")

    # Show typing indicator
    await update.message.chat.send_action("typing")

    try:
        # Download voice file
        voice_file = await context.bot.get_file(voice_message.file_id)

        # Create temp file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        # Download to temp file
        await voice_file.download_to_drive(tmp_path)
        logger.info(f"Downloaded voice file to {tmp_path}")

        # Transcribe (run in thread to avoid blocking)
        loop = asyncio.get_event_loop()
        transcription = await loop.run_in_executor(None, transcribe_audio, tmp_path)

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        if not transcription:
            await update.message.reply_text("Transcription failed. Please try again or send text.")
            return

        logger.info(f"User {user_id} (voice): {transcription}")

        # Send acknowledgment message
        ack_message = await update.message.reply_text("Thinking")
        ack_message_id = ack_message.message_id

        # Launch background task for processing (no await)
        asyncio.create_task(process_voice_async(user_id, transcription, update, context, ack_message_id))

        logger.info(f"Queued async processing for voice from user {user_id}")

    except Exception as e:
        logger.error(f"Voice download/transcription error: {e}", exc_info=True)
        await update.message.reply_text("Error processing voice message. Please try again.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queue voice messages for sequential processing"""
    if not await check_authorization(update):
        return

    user_id = update.effective_user.id
    await queue_manager.enqueue_message(
        user_id=user_id, update=update, context=context, handler=_handle_voice_impl, handler_name="voice"
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors with special handling for instance conflicts"""
    error_msg = str(context.error)

    # Check for the specific getUpdates conflict error
    if "Conflict: terminated by other getUpdates request" in error_msg:
        logger.error(
            "INSTANCE CONFLICT: Multiple bot instances detected! "
            "Another instance is polling for updates. "
            f"This instance (PID: {os.getpid()}, exc_info=True) will stop receiving updates. "
            "Please ensure only one bot instance is running."
        )
        logger.error(
            "To fix this issue:\n"
            "1. Check for other running instances: ps aux | grep 'telegram_bot/main.py'\n"
            "2. Stop duplicate instances: kill <PID>\n"
            "3. Use /restart command instead of starting new instances"
        , exc_info=True)
    else:
        logger.error(f"Update {update} caused error {context.error}", exc_info=True)

    if update and update.message:
        await update.message.reply_text("An error occurred. Please try again.")


async def cleanup_task(context: ContextTypes.DEFAULT_TYPE):
    """Periodic task to cleanup stale sessions and tasks"""
    # Clean up stale sessions
    session_count = session_manager.cleanup_stale_sessions()
    if session_count > 0:
        logger.info(f"Cleanup task: removed {session_count} stale sessions")

    # Clean up stale pending tasks (older than 1 hour)
    task_count = task_manager.cleanup_stale_pending_tasks(max_age_hours=1)
    if task_count > 0:
        logger.info(f"Cleanup task: marked {task_count} stale pending tasks as failed")


async def log_issue_notification(issue, should_escalate: bool):
    """
    Notification callback for log monitoring
    Called when bot detects issues in logs
    """
    if not ALLOWED_USERS:
        return

    # Only notify the first allowed user (usually the owner)
    user_id = ALLOWED_USERS[0]

    try:
        # Build notification message (plain text - formatter will handle HTML conversion)
        title = issue.title
        severity = issue.level.value.upper()
        description = issue.description

        message = f"🔍 Log Monitor Alert [{severity}]\n\n"
        message += f"{title}\n"
        message += f"{description}\n\n"

        if issue.evidence:
            message += "Evidence:\n"
            for evidence_line in issue.evidence[:2]:
                # Truncate long evidence lines
                if len(evidence_line) > 100:
                    evidence_line = evidence_line[:97] + "..."
                message += f"  {evidence_line}\n"

        message += "\n"

        if should_escalate:
            # Queue escalation to Claude
            log_escalation.add_to_escalation_queue(issue)

            # Perform Claude analysis asynchronously
            analysis_result = await log_escalation.analyze_issues_with_claude([issue], logs_context=None)

            if analysis_result.get("analysis"):
                analysis_msg = f"\nClaude Analysis:\n{analysis_result['analysis'][:500]}"
                if len(analysis_result["analysis"]) > 500:
                    analysis_msg += "\n\n... (truncated)"

                message += analysis_msg

                # Create confirmation request if fixes are suggested
                if analysis_result.get("suggested_fixes"):
                    conf_id = user_confirmations.create_confirmation_request(
                        issue=issue, suggested_action="\n".join(analysis_result["suggested_fixes"][:2]), confidence=0.85
                    )
                    message += f"\n\n✅ /approve {conf_id} to apply\n"
                    message += f"❌ /reject {conf_id} to skip\n"

        # Get bot instance from application (requires global reference)
        from telegram import Bot

        bot = Bot(token=TELEGRAM_BOT_TOKEN)

        # Format response using the formatter (handles HTML entities properly)
        formatted_chunks = format_telegram_response(message, max_length=4000)

        # Send formatted chunks
        for chunk in formatted_chunks:
            await bot.send_message(chat_id=user_id, text=chunk, parse_mode="HTML")

        logger.info(f"Sent log alert to user {user_id}: {issue.title}")

    except Exception as e:
        logger.error(f"Error sending log notification: {e}", exc_info=True)


def main():
    """Start the bot"""
    # Clear console on startup
    os.system("clear" if os.name != "nt" else "cls")  # nosec B605

    # Check production configuration and warn about insecure defaults
    check_and_warn()

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment!", exc_info=True)
        return

    if not ALLOWED_USERS:
        logger.warning("No ALLOWED_USERS set - bot is open to everyone!")

    # Acquire PID lock to prevent multiple instances
    if not pid_lock.acquire():
        logger.error("Failed to acquire PID lock. Exiting.", exc_info=True)
        sys.exit(1)

    logger.info("Starting Telegram bot...")

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Set bot commands (updates Telegram menu)
    async def post_init(app: Application):
        logger.info("Initializing bot (post_init)...")

        await app.bot.set_my_commands(
            [
                BotCommand("start", "Start fresh (clears history)"),
                BotCommand("status", "Active tasks & errors"),
                BotCommand("view", "View task result as markdown"),
                BotCommand("retry", "Retry failed tasks"),
                BotCommand("stop", "Stop a running task"),
                BotCommand("stopall", "Stop all active tasks"),
                BotCommand("clear", "Clear conversation"),
                BotCommand("restart", "Restart the bot"),
            ]
        )
        logger.info("Bot commands registered")

    application.post_init = post_init

    # Cleanup and shutdown handler
    async def shutdown(app: Application):
        logger.info("Shutting down...")

        # Mark all in-progress tasks as stopped before shutdown
        logger.info("Marking in-progress tasks as stopped...")
        stopped_count = task_manager.mark_all_running_as_stopped()
        logger.info(f"Marked {stopped_count} tasks as stopped")

        logger.info("Stopping self-improvement scheduler...")
        await self_improvement_scheduler.stop()
        logger.info("Self-improvement scheduler stopped")

        logger.info("Stopping worker pool...")
        await agent_pool.stop()
        logger.info("Worker pool stopped")

        logger.info("Cleaning up message queues...")
        await queue_manager.cleanup_all()

        # Log monitor is disabled, skip stopping
        # logger.info("Stopping log monitor...")
        # await log_monitor_manager.stop()

        # Close database connection
        logger.info("Closing database connection...")
        close_database()

        # Release PID lock
        logger.info("Releasing PID lock...")
        pid_lock.release()

        logger.info("Shutdown complete")

    application.post_stop = shutdown

    # Start log monitoring after app is initialized
    # DISABLED: Log monitoring alerts are disabled
    # async def start_log_monitor(app: Application):
    #     logger.info("Starting background log monitoring...")
    #     await log_monitor_manager.start(log_issue_notification)

    # Initialize self-improvement scheduler (runs every hour)
    self_improvement_scheduler = SelfImprovementScheduler(
        task_manager=task_manager,
        agent_pool=agent_pool,
        interval_seconds=3600  # 1 hour
    )

    # Hook to start worker pool and log monitor after post_init
    original_post_init = application.post_init

    async def new_post_init(app: Application):
        if original_post_init:
            await original_post_init(app)

        # Start worker pool FIRST - before any operations that might need it
        logger.info("Starting background worker pool...")
        await agent_pool.start()
        logger.info(f"Agent pool started with {agent_pool.max_agents} agents")
        
        # Start self-improvement scheduler
        logger.info("Starting self-improvement scheduler...")
        await self_improvement_scheduler.start()
        logger.info("Self-improvement scheduler started (runs every hour)")

        # Check running tasks on startup - mark as stopped if process died
        logger.info("Checking running tasks from previous session...")
        await task_manager.check_running_tasks()

        # Recover interrupted tasks - notify users and offer retry
        logger.info("Checking for interrupted tasks from previous session...")
        await recover_interrupted_tasks(app)

        # Check for restart state and notify user
        import json
        from pathlib import Path

        # Use centralized config path for restart state
        restart_state_path = Path(RESTART_STATE_FILE_STR)
        if restart_state_path.exists():
            try:
                logger.info("Found restart state file, processing...")
                with open(restart_state_path) as f:
                    restart_state = json.load(f)

                user_id = restart_state.get("user_id")
                chat_id = restart_state.get("chat_id")
                message_id = restart_state.get("message_id")
                timestamp = restart_state.get("timestamp")

                # Validate restart state - if invalid, skip restart notification but continue initialization
                if not user_id or not chat_id:
                    logger.warning("Invalid restart state: missing user_id or chat_id, skipping restart notification")
                    restart_state_path.unlink()
                elif timestamp:
                    import time

                    age = time.time() - timestamp
                    if age > 300:  # 5 minutes
                        logger.warning(f"Restart state too old ({age:.0f}s), discarding, skipping restart notification")
                        restart_state_path.unlink()
                    else:
                        # Valid restart state - process it
                        try:
                            # Clear the user's session
                            session_manager.clear_session(user_id)
                            logger.info(f"Cleared session for user {user_id} after restart")

                            # Update or send completion message
                            if message_id:
                                # Try to update the "Restarting..." message
                                try:
                                    await app.bot.edit_message_text(
                                        chat_id=chat_id, message_id=message_id, text="✅ Ready! Fresh start."
                                    )
                                    logger.info(f"Updated restart message for user {user_id}")
                                except Exception as edit_error:
                                    # If edit fails (message too old, etc), send new message
                                    logger.warning(f"Failed to edit restart message: {edit_error}, sending new message")
                                    await app.bot.send_message(chat_id=chat_id, text="✅ Ready! Fresh start.")
                            else:
                                # Send new message if we don't have a message_id
                                await app.bot.send_message(chat_id=chat_id, text="✅ Ready! Fresh start.")
                            logger.info(f"Sent restart completion to user {user_id}")
                        except Exception as e:
                            logger.error(f"Failed to process restart notification: {e}", exc_info=True)

                        # Clean up restart state file
                        restart_state_path.unlink()
                        logger.info("Restart sequence completed successfully")
                else:
                    # No timestamp, process as valid for backwards compatibility
                    try:
                        session_manager.clear_session(user_id)
                        logger.info(f"Cleared session for user {user_id} after restart")

                        if message_id:
                            try:
                                await app.bot.edit_message_text(
                                    chat_id=chat_id, message_id=message_id, text="✅ Ready! Fresh start."
                                )
                            except Exception:
                                await app.bot.send_message(chat_id=chat_id, text="✅ Ready! Fresh start.")
                        else:
                            await app.bot.send_message(chat_id=chat_id, text="✅ Ready! Fresh start.")
                        logger.info(f"Sent restart completion to user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to process restart notification: {e}", exc_info=True)

                    restart_state_path.unlink()
                    logger.info("Restart sequence completed")

            except Exception as e:
                logger.error(f"Error processing restart state: {e}", exc_info=True)
                # Clean up even if there was an error
                try:
                    if restart_state_path.exists():
                        restart_state_path.unlink()
                        logger.info("Cleaned up restart state file after error")
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up restart state file: {cleanup_error}", exc_info=True)

        # Clean up old pending tasks (stuck from previous bot issues)
        logger.info("Checking for orphaned pending tasks...")
        from datetime import datetime, timedelta

        now = datetime.now()
        cutoff = now - timedelta(minutes=5)  # Pending > 5 minutes is stuck
        cleaned = 0

        # Get pending tasks from database
        cursor = task_manager.db.conn.cursor()
        cursor.execute("SELECT task_id, created_at FROM tasks WHERE status = 'pending'")
        for row in cursor.fetchall():
            task_id, created_at = row
            created_time = datetime.fromisoformat(created_at)
            if created_time < cutoff:
                # Task stuck in pending - mark as failed
                await task_manager.update_task(
                    task_id,
                    status="failed",
                    error="Task stuck in pending state - never submitted to worker pool",
                )
                cleaned += 1
                logger.warning(f"Cleaned stuck pending task {task_id} (created {created_at})")

        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} orphaned pending tasks")
        else:
            logger.info("No orphaned pending tasks found")

        # Auto-retry disabled - it creates pending tasks that never get submitted to worker pool
        # Users can manually retry via /retry command
        logger.info("Auto-retry of stopped tasks is disabled")
        stopped_tasks = task_manager.get_stopped_tasks()
        if stopped_tasks:
            logger.info(f"Found {len(stopped_tasks)} stopped tasks - use /retry to retry them manually")
        else:
            logger.info("No stopped tasks found")

        # Start log monitoring - DISABLED
        # await start_log_monitor(app)
        logger.info("Log monitoring alerts are disabled")

    application.post_init = new_post_init

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("view", view_command))
    application.add_handler(CommandHandler("retry", retry_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("stopall", stopall_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("restart", restart_command))

    # Handle callback queries (inline keyboard buttons)
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Handle messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Error handler
    application.add_error_handler(error_handler)

    # Schedule cleanup task (every 30 minutes)
    job_queue = application.job_queue
    job_queue.run_repeating(cleanup_task, interval=1800, first=1800)
    logger.info("Scheduled cleanup task (every 30 minutes)")

    # Start bot
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
