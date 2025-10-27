"""
Task monitoring and automatic cleanup for stuck/stale tasks

Provides:
- Timeout detection for long-running tasks
- Automatic cleanup for stale tasks (no updates, dead process)
- Background monitoring loop
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

from tasks.database import Database
from tasks.manager import is_process_alive

logger = logging.getLogger(__name__)


class TaskMonitor:
    """
    Monitors running tasks and cleans up stuck/stale tasks

    Features:
    - Detects tasks with dead PIDs
    - Detects tasks without updates for >timeout period
    - Automatic status updates to 'failed' with clear error messages
    """

    def __init__(
        self,
        database: Database,
        check_interval_seconds: int = 60,
        task_timeout_minutes: int = 30,
    ):
        """
        Args:
            database: Database instance for task queries/updates
            check_interval_seconds: How often to check for stuck tasks (default: 60s)
            task_timeout_minutes: Max time without updates before marking failed (default: 30min)
        """
        self.db = database
        self.check_interval = check_interval_seconds
        self.task_timeout = timedelta(minutes=task_timeout_minutes)
        self._running = False
        self._task = None

    async def start(self):
        """Start background monitoring loop"""
        if self._running:
            logger.warning("Task monitor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"Task monitor started: check_interval={self.check_interval}s, "
            f"timeout={self.task_timeout.total_seconds()/60:.0f}min"
        )

    async def stop(self):
        """Stop background monitoring loop"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task monitor stopped")

    async def _monitor_loop(self):
        """Background loop that checks for stuck tasks"""
        while self._running:
            try:
                await self._check_stuck_tasks()
            except Exception as e:
                logger.error(f"Error in task monitor loop: {e}", exc_info=True)

            # Wait for next check
            await asyncio.sleep(self.check_interval)

    async def _check_stuck_tasks(self):
        """Check all running tasks for stuck/stale conditions"""
        try:
            # Query running tasks
            running_tasks = self.db.get_tasks_by_status("running")

            if not running_tasks:
                return

            now = datetime.now()
            stuck_count = 0

            for task in running_tasks:
                task_id = task["task_id"]
                pid = task.get("pid")
                updated_at_str = task["updated_at"]

                # Parse updated_at timestamp
                try:
                    updated_at = datetime.fromisoformat(updated_at_str)
                except (ValueError, TypeError):
                    logger.warning(f"Task {task_id}: Invalid updated_at timestamp: {updated_at_str}")
                    continue

                # Check 1: Dead process
                if pid and not is_process_alive(pid):
                    error_msg = f"Process {pid} no longer running (dead/killed)"
                    logger.warning(f"Task {task_id}: {error_msg}")
                    await self._mark_task_failed(task_id, error_msg, "dead_process")
                    stuck_count += 1
                    continue

                # Check 2: No updates for >timeout period
                time_since_update = now - updated_at
                if time_since_update > self.task_timeout:
                    error_msg = f"No updates for {time_since_update.total_seconds()/60:.1f}min (timeout: {self.task_timeout.total_seconds()/60:.0f}min)"
                    logger.warning(f"Task {task_id}: {error_msg}")

                    # Kill process if still running
                    if pid and is_process_alive(pid):
                        try:
                            import os
                            import signal
                            os.kill(pid, signal.SIGTERM)
                            logger.info(f"Task {task_id}: Sent SIGTERM to PID {pid}")
                            await asyncio.sleep(2)  # Give it time to terminate

                            # Force kill if still alive
                            if is_process_alive(pid):
                                os.kill(pid, signal.SIGKILL)
                                logger.info(f"Task {task_id}: Sent SIGKILL to PID {pid}")
                        except Exception as e:
                            logger.error(f"Task {task_id}: Failed to kill PID {pid}: {e}")

                    await self._mark_task_failed(task_id, error_msg, "timeout")
                    stuck_count += 1

            if stuck_count > 0:
                logger.info(f"Cleaned up {stuck_count} stuck tasks")

        except Exception as e:
            logger.error(f"Error checking stuck tasks: {e}", exc_info=True)

    async def _mark_task_failed(self, task_id: str, error_msg: str, reason: str):
        """Mark task as failed with clear error message"""
        try:
            await self.db.update_task(
                task_id=task_id,
                status="failed",
                error=f"[{reason}] {error_msg}"
            )
            logger.info(f"Task {task_id}: Marked as failed ({reason})")
        except Exception as e:
            logger.error(f"Task {task_id}: Failed to update status: {e}", exc_info=True)

    async def check_task_health(self, task_id: str) -> dict:
        """
        Check health of specific task (on-demand check)

        Returns:
            {
                "status": "healthy" | "dead_process" | "timeout" | "unknown",
                "message": str,
                "pid_alive": bool | None,
                "time_since_update_seconds": float | None
            }
        """
        try:
            task = self.db.get_task(task_id)
            if not task:
                return {"status": "unknown", "message": "Task not found"}

            pid = task.get("pid")
            status = task["status"]
            updated_at_str = task["updated_at"]

            # Only check running tasks
            if status != "running":
                return {"status": "not_running", "message": f"Task status: {status}"}

            # Check PID
            pid_alive = is_process_alive(pid) if pid else None

            # Check update time
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                time_since_update = datetime.now() - updated_at
                time_since_update_seconds = time_since_update.total_seconds()
            except (ValueError, TypeError):
                time_since_update_seconds = None

            # Determine health
            if pid and not pid_alive:
                return {
                    "status": "dead_process",
                    "message": f"Process {pid} is dead",
                    "pid_alive": False,
                    "time_since_update_seconds": time_since_update_seconds
                }

            if time_since_update_seconds and time_since_update_seconds > self.task_timeout.total_seconds():
                return {
                    "status": "timeout",
                    "message": f"No updates for {time_since_update_seconds/60:.1f}min",
                    "pid_alive": pid_alive,
                    "time_since_update_seconds": time_since_update_seconds
                }

            return {
                "status": "healthy",
                "message": "Task is running normally",
                "pid_alive": pid_alive,
                "time_since_update_seconds": time_since_update_seconds
            }

        except Exception as e:
            logger.error(f"Error checking task health: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
