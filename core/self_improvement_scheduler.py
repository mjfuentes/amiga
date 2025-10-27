"""
Self-Improvement Agent Scheduler
Runs hourly to analyze errors and improve agent prompts automatically
"""

import asyncio
import logging
from datetime import datetime

from tasks.manager import TaskManager
from tasks.pool import AgentPool, TaskPriority

logger = logging.getLogger(__name__)


class SelfImprovementScheduler:
    """Schedules periodic self-improvement analysis"""

    def __init__(self, task_manager: TaskManager, agent_pool: AgentPool, interval_seconds: int = 3600):
        """
        Initialize scheduler

        Args:
            task_manager: TaskManager instance for creating tasks
            agent_pool: AgentPool instance for task execution
            interval_seconds: How often to run (default: 3600 = 1 hour)
        """
        self.task_manager = task_manager
        self.agent_pool = agent_pool
        self.interval_seconds = interval_seconds
        self._task = None
        self._running = False

    async def start(self):
        """Start the scheduler"""
        if self._running:
            logger.warning("Self-improvement scheduler already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Self-improvement scheduler started (runs every {self.interval_seconds / 3600:.1f} hours)"
        )

    async def stop(self):
        """Stop the scheduler"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Self-improvement scheduler stopped")

    async def _run_loop(self):
        """Main loop - runs every interval"""
        try:
            while self._running:
                # Wait for the interval
                await asyncio.sleep(self.interval_seconds)

                if not self._running:
                    break

                # Run the analysis
                await self._run_analysis()

        except asyncio.CancelledError:
            logger.info("Self-improvement scheduler task cancelled")
        except Exception as e:
            logger.error(f"Self-improvement scheduler error: {e}", exc_info=True)

    async def _run_analysis(self):
        """Run a single self-improvement analysis"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"Starting scheduled self-improvement analysis at {timestamp}")

            # Create a task for the self-improvement agent
            # Uses a system user_id (0) to indicate automated task
            task = await self.task_manager.create_task(
                user_id=0,  # System user
                description="Automated self-improvement analysis",
                workspace="/Users/matifuentes/Workspace/agentlab",
                model="opus",  # Self-improvement agent uses Opus for analysis
                agent_type="orchestrator",  # Will delegate to self-improvement-agent
                context="Scheduled hourly analysis: Analyze errors from the last 7 days. "
                "Query the database for failed tasks and tool usage errors. "
                "Focus on top 3 patterns and update agent prompts accordingly.",
            )

            logger.info(f"Created self-improvement task {task.task_id}")

            # Submit to agent pool with LOW priority (don't block user tasks)
            # The task will invoke self-improvement-agent via orchestrator
            await self.agent_pool.submit(
                self._execute_self_improvement_task,
                task,
                priority=TaskPriority.LOW,
            )

            logger.info(f"Submitted self-improvement task {task.task_id} to agent pool")

        except Exception as e:
            logger.error(f"Failed to run self-improvement analysis: {e}", exc_info=True)

    async def _execute_self_improvement_task(self, task):
        """Execute the self-improvement task via orchestrator"""
        from claude.code_cli import ClaudeSessionPool
        from pathlib import Path

        try:
            logger.info(f"Executing self-improvement task {task.task_id}")

            # Update task status
            await self.task_manager.update_task(task.task_id, status="running")

            # Create session pool for execution
            session_pool = ClaudeSessionPool(max_sessions=1)

            # Define callbacks
            def pid_callback(pid):
                asyncio.create_task(self.task_manager.update_task(task.task_id, pid=pid))

            def progress_callback(status, elapsed):
                asyncio.create_task(
                    self.task_manager.log_activity(task.task_id, f"{status} (elapsed: {elapsed}s)")
                )

            # Build prompt for orchestrator to invoke self-improvement-agent
            prompt = (
                "Use Task tool with subagent_type='self-improvement-agent' and "
                "prompt='Analyze errors from the last 7 days. "
                "Query the database for failed tasks and tool usage errors. "
                "Focus on top 3 patterns and update agent prompts accordingly.'"
            )

            # Execute via session pool
            success, response, pid, workflow = await session_pool.execute_task(
                task_id=task.task_id,
                description=task.description,
                workspace=Path(task.workspace),
                bot_repo_path="/Users/matifuentes/Workspace/agentlab",
                model="opus",
                context=prompt,
                pid_callback=pid_callback,
                progress_callback=progress_callback,
            )

            # Update task with result
            if success:
                await self.task_manager.update_task(
                    task.task_id,
                    status="completed",
                    result=response[:1000],  # Truncate long responses
                    workflow=workflow,
                )
                logger.info(f"Self-improvement task {task.task_id} completed successfully")
            else:
                await self.task_manager.update_task(
                    task.task_id,
                    status="failed",
                    error=response[:500],
                    workflow=workflow,
                )
                logger.error(f"Self-improvement task {task.task_id} failed: {response[:200]}")

        except Exception as e:
            logger.error(f"Error executing self-improvement task {task.task_id}: {e}", exc_info=True)
            await self.task_manager.update_task(task.task_id, status="failed", error=str(e))

    async def run_now(self):
        """Manually trigger an analysis now (for testing)"""
        logger.info("Manually triggering self-improvement analysis")
        await self._run_analysis()

