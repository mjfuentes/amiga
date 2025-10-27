"""
Command handlers for web chat interface.
Centralizes logic for handling bot commands like /status, /stop, /retry, etc.
"""

from datetime import datetime, timedelta
from tasks.manager import TaskManager


class CommandHandler:
    """Handles bot commands for web chat interface."""

    def __init__(self, task_manager: TaskManager) -> None:
        self.task_manager = task_manager

    async def handle_command(self, command: str, user_id: str) -> dict:
        """
        Route command to appropriate handler.
        
        Returns:
            dict with keys:
                - success: bool
                - message: str (response message)
                - data: dict (optional additional data)
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/status": self._handle_status,
            "/stop": self._handle_stop,
            "/stopall": self._handle_stopall,
            "/retry": self._handle_retry,
            "/view": self._handle_view,
        }

        handler = handlers.get(cmd)
        if not handler:
            return {
                "success": False,
                "message": f"Unknown command: {cmd}. Type /help for available commands.",
            }

        return await handler(user_id, args)

    async def _handle_status(self, user_id: str, args: str) -> dict:
        """Handle /status command."""
        # Clean up stale tasks
        self.task_manager.cleanup_stale_pending_tasks(max_age_hours=1)
        self.task_manager.clear_old_failed_tasks(int(user_id), older_than_hours=24)

        # Get active tasks
        active_tasks = self.task_manager.get_active_tasks(int(user_id))

        # Get recent completed/failed tasks
        recent_tasks = self.task_manager.get_user_tasks(int(user_id), limit=10)
        completed = [t for t in recent_tasks if t.status == "completed"][:5]
        failed = [t for t in recent_tasks if t.status == "failed"][:5]

        message = "**Status Report**\n\n"

        if active_tasks:
            message += f"**Active Tasks ({len(active_tasks)}):**\n"
            for task in active_tasks:
                elapsed = datetime.now() - datetime.fromisoformat(task.created_at)
                elapsed_str = f"{int(elapsed.total_seconds() / 60)}m" if elapsed.total_seconds() > 60 else f"{int(elapsed.total_seconds())}s"
                status_emoji = "🔄" if task.status == "running" else "⏳"
                message += f"{status_emoji} `#{task.task_id}` - {task.description[:60]}... ({elapsed_str})\n"
            message += "\n"
        else:
            message += "No active tasks\n\n"

        if completed:
            message += f"**Recent Completed ({len(completed)}):**\n"
            for task in completed:
                message += f"✅ `#{task.task_id}` - {task.description[:60]}...\n"
            message += "\n"

        if failed:
            message += f"**Recent Failed ({len(failed)}):**\n"
            for task in failed:
                error_msg = task.error[:50] if task.error else "Unknown error"
                message += f"❌ `#{task.task_id}` - {task.description[:60]}...\n   Error: {error_msg}...\n"
            message += "\n"

        if not active_tasks and not completed and not failed:
            message += "No recent activity\n"

        return {"success": True, "message": message, "data": {"active": len(active_tasks)}}

    async def _handle_stop(self, user_id: str, args: str) -> dict:
        """Handle /stop <task_id> command."""
        if not args:
            active_tasks = self.task_manager.get_active_tasks(int(user_id))
            if not active_tasks:
                return {"success": False, "message": "No active tasks to stop."}
            
            message = "**Active Tasks:**\n\n"
            for task in active_tasks:
                message += f"• `#{task.task_id}` - {task.description[:60]}...\n"
            message += f"\n**Usage:** `/stop <task_id>`\n**Example:** `/stop {active_tasks[0].task_id}`"
            return {"success": True, "message": message}

        task_id = args.strip().lstrip("#")
        task = self.task_manager.get_task(task_id)

        if task is None:
            return {"success": False, "message": f"Task #{task_id} not found."}

        if task.user_id != int(user_id):
            return {"success": False, "message": "You don't have permission to stop this task."}

        if task.status not in ["pending", "running"]:
            return {"success": False, "message": f"Task #{task_id} is not active (status: {task.status})."}

        success, msg = await self.task_manager.stop_task(task_id)
        
        if success:
            message = f"**Task Stopped:** `#{task_id}`\n\n{task.description}\n\nYou can retry it with `/retry {task_id}`"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": msg}

    async def _handle_stopall(self, user_id: str, args: str) -> dict:
        """Handle /stopall command."""
        active_tasks = self.task_manager.get_active_tasks(int(user_id))

        if not active_tasks:
            return {"success": False, "message": "No active tasks to stop."}

        stopped = []
        failed = []

        for task in active_tasks:
            success, msg = await self.task_manager.stop_task(task.task_id)
            if success:
                stopped.append(task.task_id)
            else:
                failed.append((task.task_id, msg))

        message = f"**Stopped {len(stopped)} task(s)**\n\n"
        
        if stopped:
            message += "**Stopped:**\n"
            for tid in stopped:
                message += f"• `#{tid}`\n"
            message += "\n"

        if failed:
            message += "**Failed to stop:**\n"
            for tid, err in failed:
                message += f"• `#{tid}` - {err[:50]}...\n"

        return {"success": True, "message": message}

    async def _handle_retry(self, user_id: str, args: str) -> dict:
        """Handle /retry <task_id> command."""
        if not args:
            failed_tasks = self.task_manager.get_user_tasks(int(user_id), status="failed", limit=10)
            if not failed_tasks:
                return {"success": False, "message": "No failed tasks to retry."}

            message = "**Failed Tasks:**\n\n"
            for task in failed_tasks[:5]:
                error_msg = task.error[:50] if task.error else "Unknown error"
                message += f"• `#{task.task_id}` - {task.description[:60]}...\n  Error: {error_msg}...\n"
            
            if len(failed_tasks) > 5:
                message += f"\n... and {len(failed_tasks) - 5} more\n"
            
            message += f"\n**Usage:** `/retry <task_id>`\n**Example:** `/retry {failed_tasks[0].task_id}`"
            return {"success": True, "message": message}

        task_id = args.strip().lstrip("#")
        task = self.task_manager.get_task(task_id)

        if task is None:
            return {"success": False, "message": f"Task #{task_id} not found."}

        if task.user_id != int(user_id):
            return {"success": False, "message": "You don't have permission to retry this task."}

        if task.status not in ["failed", "stopped"]:
            return {"success": False, "message": f"Task #{task_id} cannot be retried (status: {task.status})."}

        # Return data to trigger retry in the WebSocket handler
        return {
            "success": True,
            "message": f"Retrying task #{task_id}...",
            "data": {"action": "retry", "task": task},
        }

    async def _handle_view(self, user_id: str, args: str) -> dict:
        """Handle /view <task_id> command."""
        if not args:
            recent_tasks = self.task_manager.get_user_tasks(int(user_id), status="completed", limit=10)
            if not recent_tasks:
                return {"success": False, "message": "No completed tasks to view."}

            message = "**Recent Completed Tasks:**\n\n"
            for task in recent_tasks[:5]:
                message += f"• `#{task.task_id}` - {task.description[:60]}...\n"
            
            message += f"\n**Usage:** `/view <task_id>`\n**Example:** `/view {recent_tasks[0].task_id}`"
            return {"success": True, "message": message}

        task_id = args.strip().lstrip("#")
        task = self.task_manager.get_task(task_id)

        if task is None:
            return {"success": False, "message": f"Task #{task_id} not found."}

        if task.user_id != int(user_id):
            return {"success": False, "message": "You don't have permission to view this task."}

        if not task.result:
            if task.status == "completed":
                return {"success": False, "message": f"Task #{task_id} completed but has no result."}
            else:
                return {"success": False, "message": f"Task #{task_id} is not completed yet (status: {task.status})."}

        # Return task result
        message = f"**Task #{task_id} Result:**\n\n{task.description}\n\n---\n\n{task.result}"
        return {"success": True, "message": message, "data": {"task_id": task_id, "result": task.result}}
