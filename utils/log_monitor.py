"""
Background log monitoring system
Periodically analyzes logs and notifies user of issues
Runs asynchronously without blocking bot operations
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from utils.log_analyzer import IssueLevel, IssueType, LocalLogAnalyzer, LogIssue

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


@dataclass
class MonitoringConfig:
    """Configuration for log monitoring"""

    log_path: str
    check_interval_seconds: int = 300  # Check every 5 minutes
    analysis_window_hours: int = 1  # Analyze last 1 hour of logs
    notify_on_critical: bool = True
    notify_on_warning: bool = True
    max_notifications_per_check: int = 3  # Don't spam with too many issues
    escalation_threshold: int = 3  # Issues to escalate to Claude after this many local detections


class LogMonitorTask:
    """Background task for monitoring logs"""

    def __init__(self, config: MonitoringConfig) -> None:
        self.config = config
        self.analyzer = LocalLogAnalyzer(config.log_path)
        self.running = False
        self.last_check_time: datetime | None = None
        self.detection_history: dict[str, int] = {}  # Track recurring issues
        self.issue_cache: list[LogIssue] = []  # Cache for Claude escalation

    async def start(self, notification_callback: Callable) -> None:
        """
        Start monitoring in background
        notification_callback: async function(issue, should_ask_for_confirmation)
        """
        self.running = True
        self.notification_callback = notification_callback
        logger.info(f"Log monitor started (checking every {self.config.check_interval_seconds}s)")

        try:
            while self.running:
                await self._check_and_notify()
                await asyncio.sleep(self.config.check_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Log monitor stopped")
            self.running = False
        except Exception as e:
            logger.error(f"Log monitor error: {e}", exc_info=True)
            self.running = False

    async def stop(self) -> None:
        """Stop monitoring"""
        self.running = False
        logger.info("Stopping log monitor")

    async def _check_and_notify(self) -> None:
        """Check logs and notify user of issues"""
        try:
            # Analyze logs (local, no API calls)
            issues = self.analyzer.analyze(hours=self.config.analysis_window_hours)

            if not issues:
                return

            # Filter by notification settings
            issues_to_notify = []

            for issue in issues:
                # Track recurring issues
                issue_key = f"{issue.issue_type.value}:{issue.title}"
                self.detection_history[issue_key] = self.detection_history.get(issue_key, 0) + 1

                # Skip if not configured to notify
                if issue.level == IssueLevel.CRITICAL and not self.config.notify_on_critical:
                    continue
                if issue.level == IssueLevel.WARNING and not self.config.notify_on_warning:
                    continue
                if issue.level == IssueLevel.INFO:
                    continue  # Never auto-notify on INFO level

                issues_to_notify.append(issue)

            # Limit notifications
            issues_to_notify = issues_to_notify[: self.config.max_notifications_per_check]

            # Notify user about each issue
            for issue in issues_to_notify:
                should_escalate = self._should_escalate_to_claude(issue)
                await self.notification_callback(issue, should_escalate)

            self.last_check_time = datetime.now()

        except Exception as e:
            logger.error(f"Error in log check: {e}", exc_info=True)

    def _should_escalate_to_claude(self, issue: LogIssue) -> bool:
        """
        Determine if issue should be escalated to Claude for deeper analysis
        Returns True if:
        - Issue has been detected repeatedly
        - Issue is critical and complex
        - Issue requires understanding code context
        """
        issue_key = f"{issue.issue_type.value}:{issue.title}"
        occurrence_count = self.detection_history.get(issue_key, 1)

        # Escalate if:
        # 1. Recurring issue (detected 3+ times)
        if occurrence_count >= self.config.escalation_threshold:
            logger.info(f"Escalating recurring issue to Claude: {issue.title}")
            return True

        # 2. Critical orchestrator/performance issues
        if issue.issue_type in [IssueType.ORCHESTRATOR_FAILURE, IssueType.PERFORMANCE]:
            return True

        # 3. Critical errors (may need code changes)
        if issue.level == IssueLevel.CRITICAL and issue.issue_type == IssueType.ERROR_PATTERN:
            return True

        return False

    def get_cached_issues(self) -> list[LogIssue]:
        """Get cached issues for later Claude analysis"""
        return self.issue_cache

    def add_to_escalation_queue(self, issue: LogIssue) -> None:
        """Add issue to escalation queue for Claude analysis"""
        self.issue_cache.append(issue)

    def clear_escalation_queue(self) -> None:
        """Clear cached issues after Claude has analyzed them"""
        self.issue_cache = []

    def get_stats(self) -> dict:
        """Get monitoring statistics"""
        return {
            "running": self.running,
            "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            "issues_detected": len(self.detection_history),
            "recurring_issues": {k: v for k, v in self.detection_history.items() if v > 1},
            "escalation_queue_size": len(self.issue_cache),
        }


class LogMonitorManager:
    """Manages the background log monitoring task"""

    def __init__(self, config: MonitoringConfig) -> None:
        self.config = config
        self.monitor = LogMonitorTask(config)
        self.monitor_task: asyncio.Task | None = None
        self.notification_callback: Callable | None = None

    async def start(self, notification_callback: Callable) -> None:
        """Start monitoring"""
        if self.monitor_task and not self.monitor_task.done():
            logger.warning("Log monitor already running")
            return

        self.notification_callback = notification_callback
        self.monitor_task = asyncio.create_task(self.monitor.start(notification_callback))
        logger.info("Log monitor manager started")

    async def stop(self) -> None:
        """Stop monitoring"""
        await self.monitor.stop()
        if self.monitor_task:
            await self.monitor_task

    def is_running(self) -> bool:
        """Check if monitor is running"""
        return self.monitor.running

    async def manual_check(self) -> dict:
        """Manually trigger a check (useful for testing)"""
        await self.monitor._check_and_notify()
        return self.monitor.analyzer.get_summary()

    def get_stats(self) -> dict:
        """Get current monitoring stats"""
        return self.monitor.get_stats()

    def get_escalation_queue(self) -> list[LogIssue]:
        """Get issues queued for Claude analysis"""
        return self.monitor.get_cached_issues()

    def clear_escalation_queue(self) -> None:
        """Clear escalation queue"""
        self.monitor.clear_escalation_queue()
