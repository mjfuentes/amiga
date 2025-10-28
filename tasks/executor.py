"""
Standalone task executor service - runs independently from monitoring server.

Prevents task termination when monitoring server restarts/deploys.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks.pool import AgentPool, TaskPriority
from tasks.manager import TaskManager
from tasks.tracker import ToolUsageTracker
from claude.code_cli import ClaudeSessionPool

logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/amiga-task-executor.sock"
PID_FILE = "/tmp/amiga-task-executor.pid"


class TaskExecutor:
    """Standalone task executor service"""

    def __init__(self):
        self.agent_pool = AgentPool(max_agents=3)
        self.task_manager = TaskManager()
        self.usage_tracker = ToolUsageTracker()
        self.claude_pool = ClaudeSessionPool(max_concurrent=3, usage_tracker=self.usage_tracker)
        self.server = None
        self.start_time = time.time()
        self._running = False
        self._task_callbacks = {}  # Store callbacks for task notifications

    async def start(self):
        """Start task executor service"""
        logger.info("Starting task executor service...")

        # Start agent pool
        await self.agent_pool.start()

        # Remove old socket if exists
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        # Start Unix socket server
        self.server = await asyncio.start_unix_server(self.handle_client, path=SOCKET_PATH)

        # Write PID file
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

        self._running = True
        logger.info(f"Task executor listening on {SOCKET_PATH}")

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        async with self.server:
            await self.server.serve_forever()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self.stop())

    async def stop(self):
        """Stop task executor service"""
        logger.info("Stopping task executor service...")
        self._running = False

        # Stop agent pool
        await self.agent_pool.stop()

        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # Cleanup
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        if os.path.exists(PID_FILE):
            os.unlink(PID_FILE)

        logger.info("Task executor stopped")

    async def handle_client(self, reader, writer):
        """Handle client connections"""
        try:
            data = await reader.read(4096)
            message = json.loads(data.decode())

            action = message.get("action")
            response = {}

            if action == "submit_task":
                response = await self.submit_task(message)
            elif action == "health":
                response = self.get_health()
            elif action == "get_status":
                response = await self.get_task_status(message.get("task_id"))
            else:
                response = {"error": f"Unknown action: {action}"}

            writer.write(json.dumps(response).encode())
            await writer.drain()

        except Exception as e:
            logger.error(f"Error handling client: {e}", exc_info=True)
            error_response = {"error": str(e)}
            writer.write(json.dumps(error_response).encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def submit_task(self, message):
        """Submit task to agent pool for execution"""
        task_id = message["task_id"]
        description = message["description"]
        workspace = message["workspace"]
        user_id = message["user_id"]
        priority_str = message.get("priority", "NORMAL")
        model = message.get("model", "sonnet")
        context = message.get("context")
        bot_repo_path = message.get("bot_repo_path")

        # Convert priority string to enum
        priority = TaskPriority[priority_str]

        # Get task from database
        task = self.task_manager.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found in database")
            return {"error": f"Task {task_id} not found"}

        # Submit task to agent pool for execution
        await self.agent_pool.submit(
            self._execute_task,
            task=task,
            user_id=user_id,
            model=model,
            context=context,
            bot_repo_path=bot_repo_path,
            priority=priority,
        )

        logger.info(f"Task {task_id} queued for execution (priority: {priority.name})")

        return {"status": "queued", "task_id": task_id}

    async def _execute_task(
        self, task, user_id: str, model: str = "sonnet", context: str | None = None, bot_repo_path: str | None = None
    ):
        """
        Execute a task using Claude session pool.

        This is the core execution logic that runs in the agent pool worker.
        """
        try:
            # Update task status
            await self.task_manager.update_task(task.task_id, status="running")
            logger.info(f"Starting task execution: {task.task_id} in {task.workspace}")

            workspace_path = Path(task.workspace)

            # Define PID callback to save PID immediately when process starts
            def save_pid_immediately(pid: int):
                """Called by claude_pool as soon as process starts"""
                asyncio.create_task(self.task_manager.update_task(task.task_id, pid=pid))
                logger.info(f"Task {task.task_id} process started with PID {pid}")

            # Define progress callback to log activity
            def send_progress_update(status_message: str, elapsed_seconds: int):
                """Called periodically with progress updates"""
                # Extract output line count if present
                output_lines = None
                if "output lines" in status_message:
                    import re

                    match = re.search(r"(\d+) output lines", status_message)
                    if match:
                        output_lines = int(match.group(1))

                # Log to task manager
                asyncio.create_task(self.task_manager.log_activity(task.task_id, status_message, output_lines, save=True))

            # Execute using Claude session pool
            success, result, pid, workflow = await self.claude_pool.execute_task(
                task_id=task.task_id,
                description=task.description,
                workspace=workspace_path,
                bot_repo_path=bot_repo_path,
                model=model,
                context=context,
                pid_callback=save_pid_immediately,
                progress_callback=send_progress_update,
            )

            # Update task with result
            if success:
                await self.task_manager.update_task(task.task_id, status="completed", result=result, workflow=workflow)
                logger.info(f"Task {task.task_id} completed successfully")
            else:
                await self.task_manager.update_task(task.task_id, status="failed", error=result, workflow=workflow)
                logger.error(f"Task {task.task_id} failed: {result}")

        except Exception as e:
            logger.error(f"Task execution error for {task.task_id}: {e}", exc_info=True)
            await self.task_manager.update_task(task.task_id, status="failed", error=str(e))

    def get_health(self):
        """Get service health status"""
        return {
            "status": "healthy",
            "active_tasks": self.agent_pool.active_tasks,
            "queued_tasks": self.agent_pool.queue_size,
            "uptime_seconds": int(time.time() - self.start_time),
        }

    async def get_task_status(self, task_id):
        """Get task status from task manager"""
        task = self.task_manager.get_task(task_id)
        if task:
            return {"status": task.status, "task_id": task.task_id, "started_at": task.created_at}
        else:
            return {"error": f"Task {task_id} not found"}


async def main():
    """Main entry point"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    executor = TaskExecutor()
    try:
        await executor.start()
    except KeyboardInterrupt:
        await executor.stop()


if __name__ == "__main__":
    asyncio.run(main())
