"""
Bounded agent pool for background task execution.

Prevents blocking by managing a fixed number of concurrent agents,
queuing excess tasks for processing when agents become available.

Supports priority-based task execution with four priority levels:
URGENT (0), HIGH (1), NORMAL (2), LOW (3)
"""

import asyncio
import logging
from collections.abc import Callable
from enum import IntEnum
from typing import Any

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)

# Sentinel object to signal agent shutdown
_SENTINEL = object()


class TaskPriority(IntEnum):
    """
    Task priority levels for the agent pool.

    Lower numeric values = higher priority.
    Tasks are processed in priority order, with URGENT tasks first.
    """

    URGENT = 0  # User-facing errors, critical failures
    HIGH = 1  # User requests, interactive tasks
    NORMAL = 2  # Background tasks, routine operations (default)
    LOW = 3  # Maintenance, cleanup, analytics


class AgentPool:
    """
    Bounded agent pool for async task execution.

    Maintains a fixed number of agent coroutines that process tasks
    from a queue, ensuring concurrent work doesn't overwhelm the system.
    Uses poison pill pattern (SENTINEL) for graceful shutdown.
    """

    def __init__(self, max_agents: int = 3):
        """
        Initialize the agent pool.

        Args:
            max_agents: Maximum number of concurrent agents (default 3)
        """
        self.max_agents = max_agents
        self.task_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.agents: list[asyncio.Task] = []
        self.active_tasks = 0
        self._lock = asyncio.Lock()
        self._started = False
        self._task_counter = 0  # For FIFO ordering within same priority

    async def start(self) -> None:
        """Start the agent pool by spawning agent coroutines."""
        if self._started:
            logger.warning("Agent pool already started")
            return

        self._started = True
        logger.info(f"Starting agent pool with {self.max_agents} agents")

        # Spawn agent tasks
        for i in range(self.max_agents):
            agent_task = asyncio.create_task(self._agent(i))
            self.agents.append(agent_task)

    async def stop(self) -> None:
        """Stop the agent pool gracefully."""
        if not self._started:
            logger.warning("Agent pool not started")
            return

        logger.info("Stopping agent pool...")

        # Send sentinel values to signal agents to stop
        # Use max priority and counter to ensure sentinels are processed
        for i in range(self.max_agents):
            # Format: (priority, counter, sentinel) - matches task tuple structure
            # Use negative counter to ensure sentinels are processed first
            await self.task_queue.put((TaskPriority.URGENT, -(i + 1), _SENTINEL))

        # Wait for all agents to finish
        try:
            await asyncio.gather(*self.agents)
            logger.info("Agent pool stopped successfully")
        except asyncio.CancelledError:
            logger.warning("Agent pool tasks cancelled")
            pass

        self.agents.clear()
        self._started = False

    async def submit(
        self, task_func: Callable, *args: Any, priority: TaskPriority = TaskPriority.NORMAL, **kwargs: Any
    ) -> None:
        """
        Submit a task for execution in the agent pool.

        Non-blocking - returns immediately after queueing the task.

        Args:
            task_func: Async callable to execute
            *args: Positional arguments for task_func
            priority: Task priority level (default: NORMAL)
            **kwargs: Keyword arguments for task_func
        """
        if not self._started:
            raise RuntimeError("Agent pool not started")

        # Use counter for FIFO ordering within same priority
        async with self._lock:
            counter = self._task_counter
            self._task_counter += 1

        # Priority queue format: (priority, counter, (task_func, args, kwargs))
        # Lower priority number = processed first
        # Counter ensures FIFO for same priority
        await self.task_queue.put((priority, counter, (task_func, args, kwargs)))

        logger.debug(
            f"Task {task_func.__name__} submitted to agent pool "
            f"(priority: {priority.name}, queue size: {self.task_queue.qsize()})"
        )

    async def _agent(self, agent_id: int) -> None:
        """
        Main agent loop - processes tasks from queue.

        Args:
            agent_id: Unique identifier for this agent
        """
        logger.info(f"Agent {agent_id} started")

        try:
            while True:
                try:
                    # Get next task from queue (priority-ordered)
                    item = await self.task_queue.get()

                    # Unpack priority queue item
                    priority, counter, task_data = item

                    # Check for shutdown signal
                    if task_data is _SENTINEL:
                        logger.info(f"Agent {agent_id} received shutdown signal")
                        break

                    # Unpack task data: (task_func, args, kwargs)
                    task_func, args, kwargs = task_data

                    # Execute task
                    try:
                        async with self._lock:
                            self.active_tasks += 1

                        logger.debug(
                            f"Agent {agent_id} executing {task_func.__name__} "
                            f"(priority: {TaskPriority(priority).name}, active: {self.active_tasks})"
                        )

                        # Run the task
                        await task_func(*args, **kwargs)

                        logger.debug(f"Agent {agent_id} completed {task_func.__name__}")

                    except Exception as e:
                        logger.error(f"Agent {agent_id} error executing {task_func.__name__}: {e}", exc_info=True)
                    finally:
                        async with self._lock:
                            self.active_tasks -= 1

                    # Mark task as done
                    self.task_queue.task_done()

                except Exception as e:
                    logger.error(f"Agent {agent_id} unexpected error: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info(f"Agent {agent_id} cancelled")
            raise
        finally:
            logger.info(f"Agent {agent_id} stopped")

    @property
    def active_agent_count(self) -> int:
        """Get count of currently active tasks being processed."""
        return self.active_tasks

    @property
    def queue_size(self) -> int:
        """Get number of tasks waiting in queue."""
        return self.task_queue.qsize()

    def get_status(self) -> dict:
        """Get pool status for monitoring."""
        return {
            "max_agents": self.max_agents,
            "started": self._started,
            "active_tasks": self.active_tasks,
            "queued_tasks": self.queue_size,
            "total_agents": len(self.agents),
        }
