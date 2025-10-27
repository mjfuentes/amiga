"""
Intelligent log analyzer - Local pattern matching without Claude API calls
Identifies issues and anomalies in bot logs for proactive monitoring
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class IssueLevel(Enum):
    """Severity levels for detected issues"""

    INFO = "info"  # Informational findings (no action needed)
    WARNING = "warning"  # Potential issues (may need attention)
    CRITICAL = "critical"  # Errors/failures (should investigate)


class IssueType(Enum):
    """Categories of issues we detect"""

    ERROR_PATTERN = "error_pattern"  # Repeated errors
    HIGH_LATENCY = "high_latency"  # Response time issues
    RATE_LIMIT = "rate_limit"  # Rate limit hits
    AUTHENTICATION = "authentication"  # Auth failures
    ORCHESTRATOR_FAILURE = "orchestrator_failure"  # Orchestrator returning empty
    RESOURCE_USAGE = "resource_usage"  # High resource consumption
    PERFORMANCE = "performance"  # General performance issues
    PATTERN_ANOMALY = "pattern_anomaly"  # Unusual patterns
    RECOMMENDATION = "recommendation"  # Suggested improvements


@dataclass
class LogIssue:
    """Represents a detected issue or finding"""

    issue_type: IssueType
    level: IssueLevel
    title: str
    description: str
    evidence: list[str]  # Log lines that support this finding
    timestamp: datetime
    suggested_action: str | None = None
    requires_user_confirmation: bool = False

    def to_dict(self) -> dict:
        return {
            "type": self.issue_type.value,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence[:3],  # Limit evidence shown to user
            "timestamp": self.timestamp.isoformat(),
            "suggested_action": self.suggested_action,
            "requires_confirmation": self.requires_user_confirmation,
        }


class LocalLogAnalyzer:
    """Analyze logs locally without making API calls"""

    def __init__(self, log_path: str) -> None:
        self.log_path = Path(log_path)
        self.issues: list[LogIssue] = []

        # Error patterns to detect (local parsing only)
        self.error_patterns = [
            (r"ERROR", "Error logged"),
            (r"Exception", "Exception occurred"),
            (r"Traceback", "Traceback found"),
            (r"failed", "Failure detected"),
            (r"timeout", "Timeout occurred"),
            (r"Connection.*refused", "Connection refused"),
            (r"Unauthorized", "Unauthorized access"),
        ]

        # Warning patterns
        self.warning_patterns = [
            (r"WARNING", "Warning logged"),
            (r"Deprecated", "Deprecated usage"),
            (r"MaxRetry", "Retry limit hit"),
        ]

    def analyze(self, hours: int = 1) -> list[LogIssue]:
        """
        Analyze logs from the last N hours
        Returns list of issues found (local analysis only)
        """
        if not self.log_path.exists():
            return []

        # Read log file
        try:
            with open(self.log_path) as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading log: {e}")
            return []

        self.issues = []
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Parse and filter logs
        recent_logs = self._parse_logs(lines, cutoff_time)

        if not recent_logs:
            return []

        # Run local analysis patterns
        self._analyze_error_patterns(recent_logs)
        self._analyze_orchestrator_issues(recent_logs)
        self._analyze_latency_patterns(recent_logs)
        self._analyze_rate_limits(recent_logs)
        self._analyze_performance_anomalies(recent_logs)
        self._analyze_recommendations(recent_logs)

        # Sort by severity (critical first)
        severity_order = {IssueLevel.CRITICAL: 0, IssueLevel.WARNING: 1, IssueLevel.INFO: 2}
        self.issues.sort(key=lambda x: severity_order.get(x.level, 99))

        return self.issues

    def _parse_logs(self, lines: list[str], cutoff_time: datetime) -> list[tuple[datetime, str]]:
        """Parse log lines and filter by time"""
        parsed = []

        for line in lines:
            try:
                # Expected format: "2025-10-16 20:41:56,025 - __main__ - INFO - message"
                match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
                if match:
                    ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff_time:
                        parsed.append((ts, line.strip()))
            except (ValueError, AttributeError):
                # Skip malformed log lines
                continue

        return parsed

    def _analyze_error_patterns(self, logs: list[tuple[datetime, str]]) -> None:
        """Detect repeated errors and exceptions"""
        error_logs = []
        error_types: dict[str, int] = {}

        for ts, line in logs:
            for pattern, desc in self.error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    error_logs.append((ts, line))
                    error_types[desc] = error_types.get(desc, 0) + 1
                    break

        if not error_logs:
            return

        # Check for error spikes
        error_count = len(error_logs)
        if error_count > 10:  # More than 10 errors in period
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.ERROR_PATTERN,
                    level=IssueLevel.CRITICAL,
                    title="High error rate detected",
                    description=f"Detected {error_count} errors in the last period. This indicates potential issues with bot stability.",
                    evidence=[log[1] for log in error_logs[:5]],
                    timestamp=datetime.now(),
                    suggested_action="Review error logs to identify root cause. May need to restart bot or fix specific issues.",
                    requires_user_confirmation=True,
                )
            )
        elif error_count > 5:
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.ERROR_PATTERN,
                    level=IssueLevel.WARNING,
                    title="Moderate error rate",
                    description=f"Found {error_count} errors. Review for patterns.",
                    evidence=[log[1] for log in error_logs[:3]],
                    timestamp=datetime.now(),
                    suggested_action="Monitor logs for recurring issues",
                )
            )

    def _analyze_orchestrator_issues(self, logs: list[tuple[datetime, str]]) -> None:
        """Detect orchestrator failures and empty responses"""
        orchestrator_warnings = []
        empty_responses = []

        for ts, line in logs:
            if "Orchestrator returned empty" in line:
                empty_responses.append((ts, line))
            if "orchestrator" in line.lower() and ("error" in line.lower() or "failed" in line.lower()):
                orchestrator_warnings.append((ts, line))

        if empty_responses:
            empty_count = len(empty_responses)
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.ORCHESTRATOR_FAILURE,
                    level=IssueLevel.WARNING if empty_count < 5 else IssueLevel.CRITICAL,
                    title=f"Orchestrator returning empty responses ({empty_count}x)",
                    description="The orchestrator is returning empty responses, causing fallback to direct Claude responses. This increases API costs and reduces functionality.",
                    evidence=[log[1] for log in empty_responses[:5]],
                    timestamp=datetime.now(),
                    suggested_action="Check orchestrator.py for issues. Verify Claude CLI is responding correctly.",
                    requires_user_confirmation=True,
                )
            )

    def _analyze_latency_patterns(self, logs: list[tuple[datetime, str]]) -> None:
        """Detect high latency patterns"""
        # Look for POST requests with timing information
        timings = []

        for ts, line in logs:
            # Parse HTTP request lines for timing
            # Format: "HTTP Request: POST ... took 3.5s"
            match = re.search(r"HTTP.*?(\d+\.\d+)s", line)
            if match:
                latency = float(match.group(1))
                timings.append((ts, latency))

        if not timings:
            return

        # Analyze latency distribution
        latencies = [t[1] for t in timings]
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        slow_requests = [t for t in timings if t[1] > 5.0]  # > 5 seconds

        if max_latency > 10.0:
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.HIGH_LATENCY,
                    level=IssueLevel.WARNING,
                    title="High latency detected",
                    description=f"Max latency: {max_latency:.1f}s. Average: {avg_latency:.1f}s. {len(slow_requests)} slow requests (>5s).",
                    evidence=[f"Request took {t[1]:.1f}s" for t in slow_requests[:3]],
                    timestamp=datetime.now(),
                    suggested_action="Check network conditions and Claude API status. Consider implementing request caching.",
                )
            )

    def _analyze_rate_limits(self, logs: list[tuple[datetime, str]]) -> None:
        """Detect rate limit issues"""
        rate_limit_hits = []
        cooldown_mentions = []

        for ts, line in logs:
            if "429" in line or "rate limit" in line.lower():
                rate_limit_hits.append((ts, line))
            if "cooldown" in line.lower():
                cooldown_mentions.append((ts, line))

        if rate_limit_hits or cooldown_mentions:
            issue_count = len(rate_limit_hits) + len(cooldown_mentions)
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.RATE_LIMIT,
                    level=IssueLevel.WARNING,
                    title=f"Rate limit issues detected ({issue_count}x)",
                    description="Rate limiting is being triggered. This may be due to high request volume or configuration issues.",
                    evidence=[log[1] for log in (rate_limit_hits + cooldown_mentions)[:3]],
                    timestamp=datetime.now(),
                    suggested_action="Review rate limiting configuration. Consider increasing limits or implementing request queuing.",
                    requires_user_confirmation=True,
                )
            )

    def _analyze_performance_anomalies(self, logs: list[tuple[datetime, str]]) -> None:
        """Detect performance anomalies"""
        # Look for repeated timeouts
        timeout_count = sum(1 for _, line in logs if "timeout" in line.lower())

        if timeout_count > 3:
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.PERFORMANCE,
                    level=IssueLevel.WARNING,
                    title=f"Repeated timeouts ({timeout_count}x)",
                    description="Multiple timeout events detected. This may indicate network issues or service unavailability.",
                    evidence=[line[1] for ts, line in logs if "timeout" in line.lower()][:3],
                    timestamp=datetime.now(),
                    suggested_action="Check network connectivity and external service availability.",
                )
            )

        # Look for session cleanup activity
        cleanup_count = sum(1 for _, line in logs if "cleanup" in line.lower() and "removed" in line.lower())
        if cleanup_count > 2:
            self.issues.append(
                LogIssue(
                    issue_type=IssueType.PATTERN_ANOMALY,
                    level=IssueLevel.INFO,
                    title="Session cleanup activity",
                    description=f"Detected {cleanup_count} session cleanup operations. This is normal if users have long idle sessions.",
                    evidence=[line[1] for ts, line in logs if "cleanup" in line.lower()][:2],
                    timestamp=datetime.now(),
                )
            )

    def _analyze_recommendations(self, logs: list[tuple[datetime, str]]) -> list[LogIssue]:
        """Generate improvement recommendations"""
        recommendations: list[LogIssue] = []

        # Check if logs have httpx noise (noisy logging)
        httpx_lines = [log_line for _, log_line in logs if "httpx" in log_line.lower()]
        if len(httpx_lines) > len(logs) * 0.5:  # More than 50% are httpx logs
            recommendations.append(
                LogIssue(
                    issue_type=IssueType.RECOMMENDATION,
                    level=IssueLevel.INFO,
                    title="High verbosity in HTTP logs",
                    description="HTTP library (httpx) is generating many log entries. Consider reducing verbosity for cleaner logs.",
                    evidence=httpx_lines[:2],
                    timestamp=datetime.now(),
                    suggested_action="Set logging.getLogger('httpx').setLevel(logging.ERROR) to reduce noise.",
                )
            )

        # Check for Telegram deprecation warnings
        deprecation_count = sum(1 for _, line in logs if "deprecat" in line.lower())
        if deprecation_count > 0:
            recommendations.append(
                LogIssue(
                    issue_type=IssueType.RECOMMENDATION,
                    level=IssueLevel.INFO,
                    title="Deprecation warnings found",
                    description=f"Found {deprecation_count} deprecation warnings. Update dependencies to stay current.",
                    evidence=[line for ts, line in logs if "deprecat" in line.lower()][:2],
                    timestamp=datetime.now(),
                    suggested_action="Run 'pip list --outdated' and update packages.",
                )
            )

        self.issues.extend(recommendations)
        return recommendations

    def get_critical_issues(self) -> list[LogIssue]:
        """Get only critical issues"""
        return [i for i in self.issues if i.level == IssueLevel.CRITICAL]

    def get_warnings(self) -> list[LogIssue]:
        """Get warning-level issues"""
        return [i for i in self.issues if i.level == IssueLevel.WARNING]

    def get_summary(self) -> dict:
        """Get summary of findings"""
        return {
            "total_issues": len(self.issues),
            "critical": len(self.get_critical_issues()),
            "warnings": len(self.get_warnings()),
            "issues": [i.to_dict() for i in self.issues],
        }
