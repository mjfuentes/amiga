"""
Metrics aggregation system for bot monitoring
Collects and aggregates data from all tracking systems
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from monitoring.hooks_reader import HooksReader
from tasks.manager import TaskManager
from tasks.tracker import ToolUsageTracker

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    """Snapshot of bot metrics at a point in time"""

    timestamp: str
    task_statistics: dict[str, Any]
    tool_usage: dict[str, Any]
    system_health: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


class MetricsAggregator:
    """Aggregates metrics from all tracking systems"""

    def __init__(
        self,
        task_manager: TaskManager,
        tool_usage_tracker: ToolUsageTracker,
        hooks_reader: HooksReader | None = None,
    ) -> None:
        self.task_manager = task_manager
        self.tool_usage_tracker = tool_usage_tracker
        self.hooks_reader = hooks_reader

        logger.info("MetricsAggregator initialized")

    def get_task_statistics(self) -> dict[str, Any]:
        """Get task execution statistics"""
        # Use database statistics method
        stats = self.task_manager.db.get_task_statistics()

        # Get recent tasks for detailed view
        cursor = self.task_manager.db.conn.cursor()
        cutoff_time = (datetime.now() - timedelta(hours=24)).isoformat()
        cursor.execute(
            """
            SELECT task_id, user_id, description, status, created_at, model
            FROM tasks
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT 20
        """,
            (cutoff_time,),
        )

        recent_tasks = []
        for row in cursor.fetchall():
            recent_tasks.append(
                {
                    "task_id": row[0],
                    "user_id": row[1],
                    "description": row[2][:100],
                    "status": row[3],
                    "created_at": row[4],
                    "model": row[5],
                }
            )

        return {
            "total_tasks": stats["total"],
            "by_status": stats["by_status"],
            "success_rate": stats["success_rate"],
            "recent_24h": {
                "total": stats["recent_24h"],
                "completed": stats["by_status"].get("completed", 0),
                "failed": stats["by_status"].get("failed", 0),
                "tasks": recent_tasks,
            },
        }

    def get_tool_usage_metrics(self, hours: int = 24) -> dict[str, Any]:
        """Get tool usage statistics from Claude Code hooks"""
        # Use hooks data if available
        if self.hooks_reader:
            hooks_stats = self.hooks_reader.get_aggregate_statistics(hours=hours)

            # Convert to expected format
            tools_breakdown = hooks_stats["tools_by_type"]
            most_used = sorted(
                [
                    {
                        "tool": k,
                        "count": v,
                        "success_rate": 1.0,  # Hooks don't track success rate per tool
                        "avg_duration_ms": 0.0,
                    }
                    for k, v in tools_breakdown.items()
                ],
                key=lambda x: x["count"],
                reverse=True,
            )[:10]

            status_summary = self.tool_usage_tracker.get_agent_status_summary()

            return {
                "time_window_hours": hours,
                "total_tool_calls": hooks_stats["total_tool_calls"],
                "tools_breakdown": tools_breakdown,
                "most_used_tools": most_used,
                "agent_status": status_summary,
            }

        # Fallback to old tracker (mostly empty)
        tool_stats = self.tool_usage_tracker.get_tool_statistics(hours=hours)
        status_summary = self.tool_usage_tracker.get_agent_status_summary()

        tools_by_usage = sorted(
            tool_stats.get("tools", {}).items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )

        most_used_tools = [
            {
                "tool": tool,
                "count": stats["count"],
                "success_rate": stats.get("success_rate", 0.0),
                "avg_duration_ms": stats.get("avg_duration_ms", 0.0),
            }
            for tool, stats in tools_by_usage[:10]
        ]

        return {
            "time_window_hours": hours,
            "total_tool_calls": tool_stats.get("total_calls", 0),
            "tools_breakdown": tool_stats.get("tools", {}),
            "most_used_tools": most_used_tools,
            "agent_status": status_summary,
        }

    def get_system_health(self) -> dict[str, Any]:
        """Get system health metrics"""
        # Check data file sizes (now includes database)
        # Get data directory from task_manager's database path
        db_path = Path(self.task_manager.db.db_path)
        data_dir = db_path.parent
        file_sizes = {}

        if data_dir.exists():
            # Include JSON files (if any remain for backwards compat)
            for file in data_dir.glob("*.json"):
                size_mb = file.stat().st_size / (1024 * 1024)
                file_sizes[file.name] = round(size_mb, 2)

            # Include database file
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024 * 1024)
                file_sizes[db_path.name] = round(size_mb, 2)

        # Active tasks count from database (bot tasks + active CLI sessions)
        cursor = self.task_manager.db.conn.cursor()

        # Count bot tasks (pending/running)
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('pending', 'running')")
        bot_tasks_count = cursor.fetchone()[0]

        # Count active CLI sessions (tool usage in last 5 minutes, not in tasks table)
        cutoff_cli = (datetime.now() - timedelta(minutes=5)).isoformat()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT tool_usage.task_id)
            FROM tool_usage
            LEFT JOIN tasks ON tool_usage.task_id = tasks.task_id
            WHERE tool_usage.timestamp >= ? AND tasks.task_id IS NULL
        """,
            (cutoff_cli,),
        )
        cli_sessions_count = cursor.fetchone()[0]

        active_tasks_count = bot_tasks_count + cli_sessions_count

        # Recent errors from database
        cutoff_time = (datetime.now() - timedelta(hours=24)).isoformat()
        cursor.execute(
            """
            SELECT task_id, created_at, error
            FROM tasks
            WHERE status = 'failed' AND error IS NOT NULL AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 10
        """,
            (cutoff_time,),
        )

        recent_errors = []
        for row in cursor.fetchall():
            recent_errors.append(
                {
                    "task_id": row[0],
                    "timestamp": row[1],
                    "error": row[2][:200] if row[2] else "",  # Truncate long errors
                }
            )

        return {
            "data_file_sizes_mb": file_sizes,
            "active_tasks_count": active_tasks_count,
            "recent_errors_24h": len(recent_errors),
            "recent_errors": recent_errors,
            "timestamp": datetime.now().isoformat(),
        }

    def get_complete_snapshot(self, hours: int = 24) -> MetricsSnapshot:
        """Get complete metrics snapshot"""
        return MetricsSnapshot(
            timestamp=datetime.now().isoformat(),
            task_statistics=self.get_task_statistics(),
            tool_usage=self.get_tool_usage_metrics(hours=hours),
            system_health=self.get_system_health(),
        )

    def get_hook_usage_summary(self) -> dict[str, Any]:
        """Get summary of registered hooks and their activity"""
        return {
            "tool_start_hooks": len(self.tool_usage_tracker.tool_start_hooks),
            "tool_complete_hooks": len(self.tool_usage_tracker.tool_complete_hooks),
            "status_change_hooks": len(self.tool_usage_tracker.status_change_hooks),
            "hooks_registered": (
                len(self.tool_usage_tracker.tool_start_hooks)
                + len(self.tool_usage_tracker.tool_complete_hooks)
                + len(self.tool_usage_tracker.status_change_hooks)
            ),
        }

    def get_time_series_data(self, hours: int = 24, interval_minutes: int = 60) -> dict[str, Any]:
        """
        Get time-series data for charting

        Args:
            hours: Time window in hours
            interval_minutes: Data point interval in minutes
        """
        cutoff_time = datetime.now().replace(tzinfo=None) - timedelta(hours=hours)
        interval_delta = timedelta(minutes=interval_minutes)

        # Initialize time buckets
        buckets: list[dict[str, Any]] = []
        current_time = cutoff_time
        while current_time <= datetime.now():
            buckets.append(
                {
                    "timestamp": current_time.isoformat(),
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "tool_calls": 0,
                }
            )
            current_time += interval_delta

        # Add task data from database
        cursor = self.task_manager.db.conn.cursor()
        cursor.execute(
            """
            SELECT created_at, status
            FROM tasks
            WHERE created_at >= ?
        """,
            (cutoff_time.isoformat(),),
        )

        for row in cursor.fetchall():
            task_time = datetime.fromisoformat(row[0]).replace(tzinfo=None)
            status = row[1]
            bucket_index = int((task_time - cutoff_time).total_seconds() / (interval_minutes * 60))
            if 0 <= bucket_index < len(buckets):
                if status == "completed":
                    buckets[bucket_index]["tasks_completed"] += 1
                elif status == "failed":
                    buckets[bucket_index]["tasks_failed"] += 1

        # Add tool usage data from database
        cursor.execute(
            """
            SELECT timestamp
            FROM tool_usage
            WHERE timestamp >= ?
        """,
            (cutoff_time.isoformat(),),
        )

        for row in cursor.fetchall():
            record_time = datetime.fromisoformat(row[0]).replace(tzinfo=None)
            bucket_index = int((record_time - cutoff_time).total_seconds() / (interval_minutes * 60))
            if 0 <= bucket_index < len(buckets):
                buckets[bucket_index]["tool_calls"] += 1

        return {
            "time_window_hours": hours,
            "interval_minutes": interval_minutes,
            "data_points": buckets,
        }
