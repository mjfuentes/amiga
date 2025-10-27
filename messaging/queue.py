"""
Message queue system for sequential message processing per user
Ensures messages are processed in order, one at a time per user
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """Represents a queued message"""

    user_id: int
    update: Any  # Telegram Update object
    context: Any  # Telegram Context object
    handler: Callable  # Handler function (handle_message, handle_document, etc)
    queued_at: datetime
    handler_name: str = "unknown"  # For logging
    priority: int = 0  # 0 = normal, 1+ = higher priority (higher number = higher priority)

    async def execute(self) -> None:
        """Execute the handler for this message"""
        try:
            await self.handler(self.update, self.context)
        except Exception as e:
            logger.error(
                f"Error executing handler {self.handler_name} for user {self.user_id}: {e}",
                exc_info=True,
                extra={"user_id": self.user_id, "handler": self.handler_name}
            )


class UserMessageQueue:
    """Queue for a single user's messages"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.queue: asyncio.Queue[QueuedMessage] = asyncio.Queue()
        self.priority_queue: list[QueuedMessage] = []  # Messages waiting for priority
        self.processing = False
        self.current_message: QueuedMessage | None = None
        self.messages_processed = 0
        self.processor_task: asyncio.Task | None = None

    async def enqueue(self, message: QueuedMessage) -> None:
        """Add a message to the queue, prioritizing high-priority messages"""
        if message.priority > 0:
            # High priority message - add to priority list and trigger immediate processing
            self.priority_queue.append(message)
            self.priority_queue.sort(key=lambda m: m.priority, reverse=True)
            logger.info(
                f"User {self.user_id}: Priority message queued: {message.handler_name} (priority={message.priority})"
            )
        else:
            # Normal priority message
            await self.queue.put(message)
            logger.debug(f"User {self.user_id}: Message queued ({self.queue.qsize()} in queue)")

        # Start processor if not already running
        if not self.processing:
            await self.start_processor()

    async def start_processor(self) -> None:
        """Start processing messages from queue"""
        if self.processing:
            return

        self.processing = True
        logger.debug(f"User {self.user_id}: Queue processor started")

        # Create and track processor task
        self.processor_task = asyncio.create_task(self._process_queue())

    async def _process_queue(self) -> None:
        """Process queued messages sequentially, prioritizing high-priority messages"""
        try:
            while True:
                try:
                    # Check for priority messages first
                    if self.priority_queue:
                        self.current_message = self.priority_queue.pop(0)
                        wait_time = (datetime.now() - self.current_message.queued_at).total_seconds()
                        logger.info(
                            f"User {self.user_id}: Processing PRIORITY {self.current_message.handler_name} "
                            f"(waited {wait_time:.1f}s, priority={self.current_message.priority})"
                        )
                    else:
                        # Wait for next normal priority message
                        self.current_message = await self.queue.get()

                        wait_time = (datetime.now() - self.current_message.queued_at).total_seconds()
                        logger.info(
                            f"User {self.user_id}: Processing {self.current_message.handler_name} "
                            f"(waited {wait_time:.1f}s, {self.queue.qsize()} remaining)"
                        )

                    # Execute handler
                    await self.current_message.execute()
                    self.messages_processed += 1

                    logger.debug(f"User {self.user_id}: Completed message " f"({self.messages_processed} total)")

                except asyncio.CancelledError:
                    # Processor cancelled - stop
                    logger.debug(f"User {self.user_id}: Processor cancelled")
                    break

        except asyncio.CancelledError:
            logger.debug(f"User {self.user_id}: Queue processor cancelled")
        finally:
            self.processing = False
            self.current_message = None
            logger.debug(f"User {self.user_id}: Queue processor stopped")

    async def stop(self) -> None:
        """Stop the processor"""
        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass

    def get_status(self) -> dict:
        """Get queue status"""
        return {
            "user_id": self.user_id,
            "processing": self.processing,
            "queue_size": self.queue.qsize(),
            "messages_processed": self.messages_processed,
            "current_message": self.current_message.handler_name if self.current_message else None,
        }


class MessageQueueManager:
    """Manages message queues for all users"""

    def __init__(self):
        self.user_queues: dict[int, UserMessageQueue] = {}
        self._lock = asyncio.Lock()

    async def enqueue_message(
        self,
        user_id: int,
        update: Any,
        context: Any,
        handler: Callable,
        handler_name: str = "unknown",
        priority: int = 0,
    ) -> None:
        """Queue a message for a user

        Args:
            user_id: The user ID
            update: Telegram Update object
            context: Telegram Context object
            handler: Handler function to execute
            handler_name: Name of handler for logging
            priority: Message priority (0=normal, higher=priority commands like restart/start/clear)
        """
        async with self._lock:
            # Create queue for user if doesn't exist
            if user_id not in self.user_queues:
                self.user_queues[user_id] = UserMessageQueue(user_id)
                logger.debug(f"Created queue for user {user_id}")

        # Queue the message
        message = QueuedMessage(
            user_id=user_id,
            update=update,
            context=context,
            handler=handler,
            queued_at=datetime.now(),
            handler_name=handler_name,
            priority=priority,
        )

        await self.user_queues[user_id].enqueue(message)

    async def cleanup_user(self, user_id: int) -> None:
        """Stop and remove queue for a user"""
        if user_id in self.user_queues:
            await self.user_queues[user_id].stop()
            del self.user_queues[user_id]
            logger.debug(f"Cleaned up queue for user {user_id}")

    async def cleanup_all(self) -> None:
        """Stop and remove all queues"""
        for user_id in list(self.user_queues.keys()):
            await self.cleanup_user(user_id)
        logger.info("All message queues cleaned up")

    def get_status(self) -> dict:
        """Get status of all queues"""
        return {
            "active_users": len(self.user_queues),
            "queues": {str(uid): q.get_status() for uid, q in self.user_queues.items()},
        }

    async def get_user_status(self, user_id: int) -> dict | None:
        """Get status for specific user"""
        if user_id in self.user_queues:
            return self.user_queues[user_id].get_status()
        return None
