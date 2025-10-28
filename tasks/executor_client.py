"""
Client for communicating with task executor service.

Provides async interface for monitoring server to submit tasks
to the independent task executor process.
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/amiga-task-executor.sock"


class TaskExecutorClient:
    """Client for task executor service"""

    async def submit_task(
        self,
        task_id,
        description,
        workspace,
        user_id,
        priority="NORMAL",
        model="sonnet",
        context=None,
        bot_repo_path=None,
    ):
        """Submit task to executor service"""
        message = {
            "action": "submit_task",
            "task_id": task_id,
            "description": description,
            "workspace": workspace,
            "user_id": user_id,
            "priority": priority,
            "model": model,
            "context": context,
            "bot_repo_path": bot_repo_path,
        }

        return await self._send_message(message)

    async def health_check(self):
        """Check executor service health"""
        message = {"action": "health"}
        return await self._send_message(message)

    async def get_task_status(self, task_id):
        """Get task status"""
        message = {"action": "get_status", "task_id": task_id}
        return await self._send_message(message)

    async def _send_message(self, message):
        """Send message to task executor via Unix socket"""
        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)

            # Send message
            writer.write(json.dumps(message).encode())
            await writer.drain()

            # Read response
            data = await reader.read(4096)
            response = json.loads(data.decode())

            writer.close()
            await writer.wait_closed()

            return response

        except FileNotFoundError:
            logger.error(f"Task executor not running (socket not found: {SOCKET_PATH})")
            return {"error": "Task executor not running"}
        except Exception as e:
            logger.error(f"Error communicating with task executor: {e}", exc_info=True)
            return {"error": str(e)}
