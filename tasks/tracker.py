"""
Tool usage tracking system with hooks for monitoring Claude agent activity
Tracks tool calls, execution times, success rates, and agent status
Now using SQLite for better performance and querying
"""

import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tasks.database import Database

from core.exceptions import AMIGAError

logger = logging.getLogger(__name__)


@dataclass
class ToolUsageRecord:
    """Record of a single tool usage event"""

    timestamp: str
    task_id: str
    tool_name: str
    duration_ms: float | None = None  # Execution time in milliseconds
    success: bool | None = None
    error: str | None = None
    parameters: dict | None = None  # Sanitized parameters (no sensitive data)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ToolUsageRecord":
        return cls(**data)


@dataclass
class AgentStatusRecord:
    """Record of agent status changes"""

    timestamp: str
    task_id: str
    status: str  # 'started', 'tool_call', 'completed', 'failed'
    message: str | None = None
    metadata: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentStatusRecord":
        return cls(**data)


class ToolUsageTracker:
    """Track tool usage and agent activity with hooks using SQLite"""

    def __init__(self, db: Database = None, data_dir: str = "data"):
        """
        Initialize ToolUsageTracker.

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

        # Hooks - callbacks that get called on events
        self.tool_start_hooks: list[Callable[[str, str, dict], None]] = []
        self.tool_complete_hooks: list[Callable[[str, str, float, bool, str | None, dict | None, str | None], None]] = (
            []
        )
        self.status_change_hooks: list[Callable[[str, str, str | None], None]] = []

        # Get record counts for logging
        stats = self.db.get_database_stats()
        logger.info(
            f"ToolUsageTracker initialized with {stats['tool_usage_records']} tool records "
            f"and {stats['agent_status_records']} status records"
        )

    # Hook management
    def register_tool_start_hook(self, callback: Callable[[str, str, dict], None]):
        """
        Register a hook that gets called when a tool usage starts

        Args:
            callback: Function with signature (task_id, tool_name, parameters) -> None
        """
        self.tool_start_hooks.append(callback)
        logger.info(f"Registered tool start hook: {callback.__name__}")

    def register_tool_complete_hook(
        self, callback: Callable[[str, str, float, bool, str | None, dict | None, str | None], None]
    ):
        """
        Register a hook that gets called when a tool usage completes

        Args:
            callback: Function with signature (task_id, tool_name, duration_ms, success, error, parameters, output) -> None
        """
        self.tool_complete_hooks.append(callback)
        logger.info(f"Registered tool complete hook: {callback.__name__}")

    def register_status_change_hook(self, callback: Callable[[str, str, str | None], None]):
        """
        Register a hook that gets called when agent status changes

        Args:
            callback: Function with signature (task_id, status, message) -> None
        """
        self.status_change_hooks.append(callback)
        logger.info(f"Registered status change hook: {callback.__name__}")

    # Tool usage tracking
    def record_tool_start(self, task_id: str, tool_name: str, parameters: dict | None = None) -> str:
        """
        Record the start of a tool usage

        Args:
            task_id: Task ID
            tool_name: Name of the tool being used
            parameters: Tool parameters (will be sanitized)

        Returns:
            Record ID for tracking this usage
        """
        # Sanitize parameters - remove sensitive data
        sanitized_params = self._sanitize_parameters(parameters) if parameters else None

        # Call hooks
        for hook in self.tool_start_hooks:
            try:
                hook(task_id, tool_name, sanitized_params or {})
            except Exception as e:
                logger.error(f"Error in tool start hook {hook.__name__}: {e}", exc_info=True)

        logger.debug(f"Recorded tool start: {task_id} - {tool_name}")

        # Return dummy record ID for compatibility
        return "0"

    def record_tool_complete(
        self,
        task_id: str,
        tool_name: str,
        duration_ms: float,
        success: bool = True,
        error: str | None = None,
        parameters: dict | None = None,
    ):
        """
        Record the completion of a tool usage

        Args:
            task_id: Task ID
            tool_name: Name of the tool used
            duration_ms: Execution time in milliseconds
            success: Whether the tool completed successfully
            error: Error message if tool failed
            parameters: Tool parameters (will be sanitized)
        """
        # Sanitize parameters
        sanitized_params = self._sanitize_parameters(parameters) if parameters else None

        # Categorize error if present
        error_category = self._categorize_error(error) if error and not success else None

        # Record in database
        self.db.record_tool_usage(
            task_id=task_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success,
            error=error,
            parameters=sanitized_params,
            error_category=error_category,
        )

        # Record file access if file_path is present in parameters
        if success and sanitized_params and "file_path" in sanitized_params:
            file_path = sanitized_params["file_path"]
            operation = self._map_tool_to_operation(tool_name)
            if operation:
                # Use asyncio to run the async method
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                try:
                    if loop.is_running():
                        # If loop is already running, create a task
                        asyncio.create_task(self.db.record_file_access(file_path, task_id, operation))
                    else:
                        # If no loop is running, run it synchronously
                        loop.run_until_complete(self.db.record_file_access(file_path, task_id, operation))
                except Exception as e:
                    logger.error(f"Error recording file access for {file_path}: {e}", exc_info=True)

        # Call hooks - pass parameters and a brief output summary
        # For output, we pass error if failed, otherwise None (full output not tracked here)
        output_preview = error if not success else None
        for hook in self.tool_complete_hooks:
            try:
                hook(task_id, tool_name, duration_ms, success, error, sanitized_params, output_preview)
            except Exception as e:
                logger.error(f"Error in tool complete hook {hook.__name__}: {e}", exc_info=True)

        status = "success" if success else "failed"
        logger.info(f"Recorded tool completion: {task_id} - {tool_name} ({duration_ms:.2f}ms, {status})")

    # Agent status tracking
    def record_status_change(self, task_id: str, status: str, message: str | None = None, metadata: dict | None = None):
        """
        Record a change in agent status

        Args:
            task_id: Task ID
            status: New status ('started', 'tool_call', 'completed', 'failed')
            message: Optional message describing the status change
            metadata: Optional metadata dictionary
        """
        # Record in database
        self.db.record_agent_status(
            task_id=task_id,
            status=status,
            message=message,
            metadata=metadata,
        )

        # Call hooks
        for hook in self.status_change_hooks:
            try:
                hook(task_id, status, message)
            except Exception as e:
                logger.error(f"Error in status change hook {hook.__name__}: {e}", exc_info=True)

        logger.info(f"Recorded status change: {task_id} - {status} {f'({message})' if message else ''}")

    async def record_workflow_assignment(self, task_id: str, workflow_name: str):
        """
        Record workflow assignment for a task

        Args:
            task_id: Task ID
            workflow_name: Name of the workflow (e.g., 'code-task', 'smart-fix')
        """
        await self.db.update_task(task_id, workflow=workflow_name)
        logger.info(f"Recorded workflow assignment: {task_id} - {workflow_name}")

    # Statistics and reporting
    def get_tool_statistics(self, task_id: str | None = None, hours: int = 24) -> dict[str, Any]:
        """
        Get tool usage statistics

        Args:
            task_id: Optional task ID to filter by
            hours: Time window in hours (default: 24)

        Returns:
            Dictionary with statistics
        """
        return self.db.get_tool_statistics(task_id, hours)

    def get_agent_status_summary(self, task_id: str | None = None) -> dict[str, Any]:
        """
        Get summary of agent status changes

        Args:
            task_id: Optional task ID to filter by

        Returns:
            Dictionary with status summary
        """
        return self.db.get_agent_status_summary(task_id)

    def get_task_timeline(self, task_id: str) -> list[dict]:
        """
        Get complete timeline of events for a task

        Args:
            task_id: Task ID

        Returns:
            List of events sorted by timestamp
        """
        return self.db.get_task_timeline(task_id)

    def _sanitize_parameters(self, parameters: dict) -> dict:
        """
        Sanitize parameters to remove sensitive data

        Args:
            parameters: Raw parameters

        Returns:
            Sanitized parameters
        """
        sanitized = {}

        # List of keys to exclude
        sensitive_keys = {"token", "password", "secret", "api_key", "auth", "credential"}

        for key, value in parameters.items():
            # Skip sensitive keys
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "<redacted>"
            # Truncate long strings
            elif isinstance(value, str) and len(value) > 200:
                sanitized[key] = value[:200] + "..."
            else:
                sanitized[key] = value

        return sanitized

    def _categorize_error(self, error: str) -> str:
        """
        Categorize error based on error message patterns

        Args:
            error: Error message

        Returns:
            Error category string
        """
        if not error:
            return "unknown_error"

        error_lower = error.lower()

        # Permission errors
        if any(
            pattern in error_lower for pattern in ["permission denied", "access denied", "forbidden", "not permitted"]
        ):
            return "permission_error"

        # File not found errors
        if any(
            pattern in error_lower for pattern in ["no such file", "file not found", "cannot find", "does not exist"]
        ):
            return "file_not_found"

        # Timeout errors
        if any(pattern in error_lower for pattern in ["timed out", "timeout", "deadline exceeded"]):
            return "timeout"

        # Syntax errors
        if any(
            pattern in error_lower for pattern in ["syntax error", "invalid syntax", "parsing error", "parse error"]
        ):
            return "syntax_error"

        # Network errors
        if any(
            pattern in error_lower
            for pattern in ["connection", "network", "refused", "unreachable", "dns", "socket", "ssl", "tls"]
        ):
            return "network_error"

        # Git errors
        if any(
            pattern in error_lower
            for pattern in ["git error", "merge conflict", "rebase", "detached head", "not a git"]
        ):
            return "git_error"

        # Validation errors
        if any(pattern in error_lower for pattern in ["validation", "invalid", "malformed", "bad request"]):
            return "validation_error"

        # Resource errors
        if any(
            pattern in error_lower
            for pattern in ["out of memory", "disk full", "quota", "too many", "resource", "limit exceeded"]
        ):
            return "resource_error"

        # Command not found
        if any(pattern in error_lower for pattern in ["command not found", "not recognized", "no such command"]):
            return "command_not_found"

        # Generic error fallback
        return "unknown_error"

    def _map_tool_to_operation(self, tool_name: str) -> str | None:
        """
        Map tool name to file operation type

        Args:
            tool_name: Name of the tool

        Returns:
            Operation type ('read', 'write', 'edit') or None if not a file tool
        """
        tool_lower = tool_name.lower()

        if tool_lower == "read":
            return "read"
        elif tool_lower == "write":
            return "write"
        elif tool_lower == "edit":
            return "edit"
        else:
            return None


class ToolUsageContext:
    """Context manager for tracking tool usage with automatic timing"""

    def __init__(self, tracker: ToolUsageTracker, task_id: str, tool_name: str, parameters: dict | None = None):
        self.tracker = tracker
        self.task_id = task_id
        self.tool_name = tool_name
        self.parameters = parameters
        self.start_time: float | None = None
        self.record_id: str | None = None

    def __enter__(self):
        """Start tracking tool usage"""
        self.start_time = time.time()
        self.record_id = self.tracker.record_tool_start(self.task_id, self.tool_name, self.parameters)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Complete tracking tool usage"""
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            success = exc_type is None
            error = str(exc_val) if exc_val else None

            self.tracker.record_tool_complete(self.task_id, self.tool_name, duration_ms, success, error)

        return False  # Don't suppress exceptions
