"""
Task tracking system for background operations
Phase 3-4: Orchestrator & worker task management
Now using SQLite for better performance and querying
Enhanced with task-specific branch isolation
"""

import logging
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from tasks.database import Database

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


def is_process_alive(pid: int) -> bool:
    """Check if process with given PID is still running"""
    if pid is None:
        return False

    try:
        # Send signal 0 - checks if process exists without killing it
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def create_task_branch(task_id: str, workspace: Path) -> tuple[bool, str]:
    """
    Create and checkout a branch for this task

    Returns: (success, branch_name or error_message)
    """
    try:
        branch_name = f"task/{task_id[:8]}"

        # Check if we're in a git repo
        result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True, cwd=str(workspace))
        if result.returncode != 0:
            logger.warning(f"Not a git repo: {workspace}")
            return False, "not_a_git_repo"

        # Check for uncommitted changes
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(workspace))

        if result.stdout.strip():
            # Stash any existing changes with a message
            logger.info(f"Stashing uncommitted changes in {workspace}")
            subprocess.run(
                ["git", "stash", "push", "-m", f"Auto-stash before task {task_id}"],
                capture_output=True,
                cwd=str(workspace),
            )

        # Create and checkout task branch from current HEAD
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name], capture_output=True, text=True, cwd=str(workspace)
        )

        if result.returncode != 0:
            # Branch might already exist, try to checkout
            result = subprocess.run(
                ["git", "checkout", branch_name], capture_output=True, text=True, cwd=str(workspace)
            )
            if result.returncode != 0:
                logger.error(f"Failed to create/checkout branch {branch_name}: {result.stderr}", exc_info=True)
                return False, result.stderr

        logger.info(f"Created/checked out task branch: {branch_name} in {workspace}")
        return True, branch_name

    except Exception as e:
        logger.error(f"Error creating task branch: {e}", exc_info=True)
        return False, str(e)


def merge_task_branch(task_id: str, workspace: Path, target_branch: str = "main") -> tuple[bool, str]:
    """
    Merge task branch back to target branch (usually main)

    CRITICAL: Fails if uncommitted changes exist - agents MUST commit their work

    Returns: (success, message)
    """
    try:
        branch_name = f"task/{task_id[:8]}"

        # Check for uncommitted changes - STRICT ENFORCEMENT
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(workspace))

        if result.stdout.strip():
            # FAIL - agent violated commit policy
            files_changed = result.stdout.strip().split("\n")
            logger.error(
                f"Task {task_id[:8]} FAILED COMMIT POLICY: {len(files_changed, exc_info=True)} uncommitted files in {branch_name}"
            )
            logger.error(f"Uncommitted changes:\n{result.stdout}", exc_info=True)
            return False, f"Agent left {len(files_changed)} files uncommitted - violates commit policy"

        # Switch to target branch
        result = subprocess.run(["git", "checkout", target_branch], capture_output=True, text=True, cwd=str(workspace))

        if result.returncode != 0:
            logger.error(f"Failed to checkout {target_branch}: {result.stderr}", exc_info=True)
            return False, f"Failed to checkout {target_branch}"

        # Merge task branch with no-ff to preserve task history
        result = subprocess.run(
            ["git", "merge", "--no-ff", branch_name, "-m", f"Merge task {task_id[:8]}"],
            capture_output=True,
            text=True,
            cwd=str(workspace),
        )

        if result.returncode == 0:
            # Delete task branch
            subprocess.run(["git", "branch", "-d", branch_name], capture_output=True, cwd=str(workspace))
            logger.info(f"Merged and deleted task branch: {branch_name}")
            return True, f"Merged to {target_branch}"
        else:
            # Merge conflict - abort merge
            subprocess.run(["git", "merge", "--abort"], capture_output=True, cwd=str(workspace))
            logger.error(f"Merge conflict for {branch_name}: {result.stderr}", exc_info=True)
            return False, f"Merge conflict: {result.stderr}"

    except Exception as e:
        logger.error(f"Error merging task branch: {e}", exc_info=True)
        return False, str(e)


def cleanup_task_branch(task_id: str, workspace: Path, force: bool = False) -> bool:
    """
    Cleanup task branch (for failed/stopped tasks)

    Args:
        force: If True, force delete unmerged branch

    Returns: success
    """
    try:
        branch_name = f"task/{task_id[:8]}"

        # Switch to main first
        subprocess.run(["git", "checkout", "main"], capture_output=True, cwd=str(workspace))

        # Delete branch
        delete_flag = "-D" if force else "-d"
        result = subprocess.run(
            ["git", "branch", delete_flag, branch_name], capture_output=True, text=True, cwd=str(workspace)
        )

        if result.returncode == 0:
            logger.info(f"Cleaned up task branch: {branch_name}")
            return True
        else:
            logger.warning(f"Failed to cleanup branch {branch_name}: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error cleaning up task branch: {e}", exc_info=True)
        return False


@dataclass
class Task:
    """Background task"""

    task_id: str
    user_id: int
    description: str
    status: str  # 'pending', 'running', 'completed', 'failed', 'stopped'
    created_at: str
    updated_at: str
    model: str  # 'haiku', 'sonnet'
    workspace: str  # Repository/workspace path
    agent_type: str = "code_agent"  # 'code_agent', 'frontend_agent', 'research_agent', etc.
    workflow: str | None = None  # Workflow used (e.g., 'code-task', 'ui-task', 'research-task')
    context: str | None = None  # Context summary from Claude API (user's original message, conversation context)
    current_phase: str | None = None  # Current subagent/phase (e.g., 'code_agent', 'git-merge')
    phase_number: int = 0  # Sequential phase counter (increments with each Task tool call)
    last_agent_type: str | None = None  # Most recent delegated agent (for persistence)
    result: str | None = None
    error: str | None = None
    pid: int | None = None  # Process ID for running tasks
    activity_log: list[dict] | None = None  # Activity/progress log with timestamps

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        # Ensure activity_log exists (for backwards compatibility)
        if "activity_log" not in data:
            data["activity_log"] = []
        # Ensure agent_type exists (for backwards compatibility with old tasks)
        if "agent_type" not in data:
            data["agent_type"] = "code_agent"
        # Ensure context exists (for backwards compatibility with old tasks)
        if "context" not in data:
            data["context"] = None
        # Ensure phase tracking fields exist (for backwards compatibility)
        if "current_phase" not in data:
            data["current_phase"] = None
        if "phase_number" not in data:
            data["phase_number"] = 0
        # Ensure last_agent_type exists (for backwards compatibility)
        if "last_agent_type" not in data:
            data["last_agent_type"] = None
        return cls(**data)

    def add_activity(self, message: str, output_lines: int | None = None):
        """Add activity entry to log"""
        if self.activity_log is None:
            self.activity_log = []

        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
        }
        if output_lines is not None:
            entry["output_lines"] = output_lines

        self.activity_log.append(entry)

    def get_latest_activity(self, limit: int = 5) -> list[dict]:
        """Get latest activity entries"""
        if not self.activity_log:
            return []
        return self.activity_log[-limit:]


class TaskManager:
    """Manages background tasks using SQLite"""

    def __init__(self, db: Database = None, data_dir: str = "data"):
        """
        Initialize TaskManager.

        Args:
            db: Shared Database instance (recommended). If None, creates new instance.
            data_dir: Deprecated. Ignored when using centralized config.
        """
        self.data_dir = Path(data_dir)  # Kept for backward compatibility
        self.data_dir.mkdir(exist_ok=True)

        # Use provided database or get singleton instance
        if db is not None:
            self.db = db
        else:
            from core.database_manager import get_database
            self.db = get_database()  # Get singleton instance

        # Get task count for logging
        stats = self.db.get_database_stats()
        logger.info(f"TaskManager initialized with {stats['tasks']} tasks")

        # Note: Call check_running_tasks() manually from async context after initialization

    async def check_running_tasks(self):
        """
        Check running tasks on startup - mark as stopped if process died.
        Adds informative activity log entries for recovery tracking.
        """
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT task_id, pid, description FROM tasks WHERE status = 'running'")
        running_tasks = cursor.fetchall()

        if not running_tasks:
            logger.info("No running tasks found from previous session")
            return

        stopped_count = 0
        survived_count = 0

        for row in running_tasks:
            task_id, pid, description = row
            if pid and is_process_alive(pid):
                # Task survived restart! Process still running
                logger.info(f"Task {task_id} (PID {pid}) still running after restart")
                await self.db.add_activity(task_id, f"Task survived bot restart - process {pid} still running")
                survived_count += 1
            else:
                # Process died (or no PID tracked) - mark as stopped
                await self.db.update_task(task_id, status="stopped", error="Task stopped due to bot restart")
                await self.db.add_activity(
                    task_id, f"Task interrupted by bot restart - process {'died' if pid else 'not tracked'}"
                )
                logger.warning(f"Marked stopped task {task_id}: {description[:60]}")
                stopped_count += 1

        logger.info(f"Startup task check complete: {stopped_count} stopped, {survived_count} survived")

    def reload_tasks(self):
        """
        Reload tasks - no-op for SQLite backend since queries are always fresh.
        Kept for API compatibility.
        """
        logger.debug("reload_tasks() called - no-op for SQLite backend")

    async def create_task(
        self,
        user_id: int,
        description: str,
        workspace: str,
        model: str = "sonnet",
        agent_type: str = "code_agent",
        workflow: str | None = None,
        context: str | None = None,
    ) -> Task:
        """Create a new task"""
        task_id = str(uuid.uuid4())[:6]

        # Create in database
        task_dict = await self.db.create_task(
            task_id=task_id,
            user_id=user_id,
            description=description,
            workspace=workspace,
            model=model,
            agent_type=agent_type,
            workflow=workflow,
            context=context,
        )

        logger.info(f"Created {agent_type} task {task_id} for user {user_id} in {workspace}: {description}")
        return Task.from_dict(task_dict)

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        result: str | None = None,
        error: str | None = None,
        pid: int | None = None,
        workflow: str | None = None,
    ):
        """Update task status"""
        success = await self.db.update_task(
            task_id=task_id,
            status=status,
            result=result,
            error=error,
            pid=pid,
            workflow=workflow,
        )

        if not success:
            logger.error(f"Task {task_id} not found", exc_info=True)
            return

        logger.info(f"Updated task {task_id}: status={status}, pid={pid}")

    async def log_activity(self, task_id: str, message: str, output_lines: int | None = None, save: bool = True):
        """Log activity for a task"""
        success = await self.db.add_activity(task_id, message, output_lines)

        if not success:
            logger.error(f"Task {task_id} not found", exc_info=True)
            return

        logger.debug(f"Task {task_id} activity: {message}")

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID"""
        task_dict = self.db.get_task(task_id)
        return Task.from_dict(task_dict) if task_dict else None

    def get_user_tasks(self, user_id: int, status: str | None = None, limit: int = 10) -> list[Task]:
        """Get tasks for a user"""
        task_dicts = self.db.get_user_tasks(user_id, status, limit)
        return [Task.from_dict(t) for t in task_dicts]

    def get_active_tasks(self, user_id: int) -> list[Task]:
        """Get active (pending/running) tasks for user"""
        task_dicts = self.db.get_active_tasks(user_id)
        return [Task.from_dict(t) for t in task_dicts]

    def retry_task(self, task_id: str) -> Task | None:
        """
        Retry a failed or stopped task by creating a new task with the same parameters.
        Returns the new task if successful, None if task not found or not retryable.
        """
        original_task = self.get_task(task_id)

        if not original_task:
            logger.error(f"Task {task_id} not found", exc_info=True)
            return None

        if original_task.status not in ["failed", "stopped"]:
            logger.warning(f"Task {task_id} is not retryable (status: {original_task.status})")
            return None

        # Create new task with same parameters
        new_task = self.create_task(
            user_id=original_task.user_id,
            description=original_task.description,
            workspace=original_task.workspace,
            model=original_task.model,
            agent_type=original_task.agent_type,
        )

        logger.info(f"Created retry task {new_task.task_id} for {original_task.status} task {task_id}")
        return new_task

    def get_failed_tasks(self, user_id: int, limit: int = 10) -> list[Task]:
        """Get failed tasks for a user"""
        task_dicts = self.db.get_failed_tasks(user_id, limit)
        return [Task.from_dict(t) for t in task_dicts]

    def clear_old_failed_tasks(self, user_id: int, older_than_hours: int = 24):
        """
        Clear old failed tasks for a user to prevent clutter in status display.
        Only removes tasks older than the specified hours.

        Args:
            user_id: User ID to clear tasks for
            older_than_hours: Only clear tasks older than this many hours (default: 24)

        Returns:
            Number of tasks cleared
        """
        cleared_count = self.db.clear_old_failed_tasks(user_id, older_than_hours)
        return cleared_count

    def mark_all_running_as_stopped(self):
        """
        Mark all running tasks as stopped during shutdown.
        This preserves task state so they can be retried on restart.

        Returns:
            Number of tasks marked as stopped
        """
        stopped_count = self.db.mark_all_running_as_stopped()
        return stopped_count

    def get_stopped_tasks(self, user_id: int | None = None, limit: int = 100) -> list[Task]:
        """
        Get stopped tasks, optionally filtered by user.

        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of tasks to return

        Returns:
            List of stopped tasks
        """
        task_dicts = self.db.get_stopped_tasks(user_id, limit)
        return [Task.from_dict(t) for t in task_dicts]

    def cleanup_stale_pending_tasks(self, max_age_hours: int = 1) -> int:
        """
        Clean up stale pending tasks that have been waiting too long.
        Marks them as failed to prevent cluttering the active tasks list.

        Args:
            max_age_hours: Maximum age in hours before a pending task is considered stale

        Returns:
            Number of tasks cleaned up
        """
        cleaned_count = self.db.cleanup_stale_pending_tasks(max_age_hours)
        return cleaned_count

    def cleanup_all_pending_tasks(self, user_id: int | None = None) -> int:
        """
        Clean up all pending tasks by marking them as stopped.
        Useful for clearing the queue when tasks shouldn't run.
        
        Args:
            user_id: Optional user ID to filter tasks (None = all users)
            
        Returns:
            Number of tasks cleaned up
        """
        cleaned_count = self.db.cleanup_all_pending_tasks(user_id)
        
        if cleaned_count > 0:
            user_msg = f"for user {user_id}" if user_id else "across all users"
            logger.info(f"Cleaned up {cleaned_count} pending tasks {user_msg}")
        
        return cleaned_count

    async def stop_task(self, task_id: str) -> tuple[bool, str]:
        """
        Stop a running task by killing its process.

        Args:
            task_id: Task ID to stop

        Returns:
            (success, message) tuple
        """
        task = self.get_task(task_id)

        if not task:
            return False, f"Task #{task_id} not found."

        if task.status not in ["pending", "running"]:
            return False, f"Task #{task_id} is not running (status: {task.status})."

        # Try to kill the process if we have a PID
        if task.pid and is_process_alive(task.pid):
            try:
                os.kill(task.pid, 9)  # SIGKILL - forcefully terminate
                logger.info(f"Killed process {task.pid} for task {task_id}")
            except OSError as e:
                logger.error(f"Failed to kill process {task.pid}: {e}", exc_info=True)
                return False, f"Failed to stop task #{task_id}: {e}"

        # Update task status
        await self.db.update_task(task_id, status="stopped", error="Task stopped by user")

        logger.info(f"Stopped task {task_id} (was {task.status})")
        return True, f"Task #{task_id} stopped successfully."

    def retry_all_stopped_tasks(self) -> list[Task]:
        """
        Retry all stopped tasks on startup.
        Creates new tasks for all stopped tasks across all users.

        Returns:
            List of new tasks created
        """
        stopped_tasks = self.get_stopped_tasks()
        new_tasks = []

        for stopped_task in stopped_tasks:
            # Skip repetitive/test tasks that shouldn't be auto-retried
            if any(skip_pattern in stopped_task.description for skip_pattern in ["Find todos", "test", "Test"]):
                logger.info(f"Skipping auto-retry of task {stopped_task.task_id}: {stopped_task.description[:50]}")
                continue

            new_task = self.create_task(
                user_id=stopped_task.user_id,
                description=stopped_task.description,
                workspace=stopped_task.workspace,
                model=stopped_task.model,
                agent_type=stopped_task.agent_type,
            )
            new_tasks.append(new_task)
            logger.info(f"Auto-retrying stopped task {stopped_task.task_id} as {new_task.task_id}")

        if new_tasks:
            logger.info(f"Auto-retried {len(new_tasks)} stopped tasks on startup")

        return new_tasks

    async def stop_all_tasks(self, user_id: int) -> tuple[int, int, list[str]]:
        """
        Stop all active tasks for a user.

        Args:
            user_id: User ID whose tasks to stop

        Returns:
            (stopped_count, failed_count, failed_task_ids) tuple
        """
        active_tasks = self.get_active_tasks(user_id)

        if not active_tasks:
            return 0, 0, []

        stopped_count = 0
        failed_count = 0
        failed_task_ids = []

        for task in active_tasks:
            success, message = await self.stop_task(task.task_id)
            if success:
                stopped_count += 1
            else:
                failed_count += 1
                failed_task_ids.append(task.task_id)

        logger.info(f"Stopped {stopped_count}/{len(active_tasks)} tasks for user {user_id}")

        return stopped_count, failed_count, failed_task_ids
