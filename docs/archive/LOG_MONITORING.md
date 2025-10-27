# Intelligent Log Monitoring System

## Overview

The bot now has a **smart background log monitoring system** that automatically analyzes logs, detects issues, and escalates to Claude for intelligent analysis when needed.

### How It Works

```
Bot Running
    ↓
Every 5 minutes (configurable)
    ↓
LOCAL LOG ANALYSIS (no API calls)
├─ Parse logs from last hour
├─ Detect error patterns
├─ Identify rate limits
├─ Find orchestrator issues
└─ Detect performance anomalies
    ↓
Issue Found?
├─ No → Continue monitoring
└─ Yes → NOTIFY USER & Check if escalation needed
         ├─ Is it recurring/complex? → Send to Claude
         └─ Is it informational? → Just log it
    ↓
Claude Analysis (if escalated)
├─ Deep dive into root causes
├─ Suggest fixes
└─ Create approval requests
    ↓
User Confirmation
├─ Review Claude analysis
├─ Approve fixes with /approve ID
└─ Reject with /reject ID
```

## Key Features

### 1. **Local Pattern Matching (Zero API Cost)**
- Analyzes logs WITHOUT calling Claude
- Pattern matching for:
  - Errors and exceptions
  - Timeout events
  - Rate limit hits
  - Orchestrator empty responses
  - Performance anomalies
  - Session management issues

### 2. **Smart Escalation to Claude**
- Only escalates when:
  - Issues are recurring (detected 3+ times)
  - Errors are critical and need code understanding
  - Performance issues are complex
- Caches Claude responses to avoid duplicate calls
- Respects 30-minute escalation throttle

### 3. **User Notifications**
- 🔍 Alerts sent only to bot owner (first ALLOWED_USER)
- Shows evidence from logs
- Includes suggested actions
- Creates approval requests for fixes
- Never blocks bot operations

### 4. **Asynchronous & Background**
- Runs every 5 minutes (configurable)
- Non-blocking - doesn't impact bot responsiveness
- Can be stopped/started without restart
- Continues running even if user not active

## Configuration

In `telegram_bot/main.py`:

```python
log_monitor_config = MonitoringConfig(
    log_path="logs/bot.log",              # Where to read logs
    check_interval_seconds=300,           # Check every 5 minutes
    analysis_window_hours=1,              # Analyze last 1 hour
    notify_on_critical=True,              # Send alerts for critical issues
    notify_on_warning=False,              # Can enable later for warnings
    max_notifications_per_check=3         # Limit spam
)
```

### Adjust Settings

**More frequent monitoring** (check every 2 minutes):
```python
check_interval_seconds=120
```

**Include warnings** (not just critical issues):
```python
notify_on_warning=True
```

**Analyze longer history** (last 3 hours):
```python
analysis_window_hours=3
```

## Issue Types Detected

| Type | Level | What Triggers | Example |
|------|-------|---------------|---------|
| **ERROR_PATTERN** | CRITICAL | 10+ errors | Exception in orchestrator |
| **ORCHESTRATOR_FAILURE** | WARNING | Empty responses | Fallback triggered |
| **HIGH_LATENCY** | WARNING | Requests > 10s | Network delays |
| **RATE_LIMIT** | WARNING | 429 errors | Limit exceeded |
| **PERFORMANCE** | WARNING | Repeated timeouts | Service unavailable |
| **PATTERN_ANOMALY** | INFO | Unusual patterns | High cleanup activity |
| **RECOMMENDATION** | INFO | Improvement ideas | Reduce log verbosity |

## User Commands

### View Monitoring Status
```
/logs - Show current log monitoring status
/logs check - Manually trigger log analysis
/logs enable - Start monitoring
/logs disable - Stop monitoring
```

### Handle Issue Approvals
```
/approve <confirmation_id> - Apply suggested fix
/reject <confirmation_id> - Reject fix, add reason
/logs history - View action history
```

## Module Architecture

### `log_analyzer.py` - Local Pattern Matching
- **Purpose**: Analyze logs without API calls
- **Key Classes**:
  - `LocalLogAnalyzer`: Main analyzer
  - `LogIssue`: Represents detected issue
  - `IssueLevel`: CRITICAL, WARNING, INFO
  - `IssueType`: Categories of issues
- **Methods**:
  - `analyze(hours)`: Run analysis on last N hours
  - `get_critical_issues()`: Filter by severity
  - `get_summary()`: Get findings summary

### `log_monitor.py` - Background Task Management
- **Purpose**: Run monitoring periodically in background
- **Key Classes**:
  - `LogMonitorTask`: Individual monitor instance
  - `LogMonitorManager`: Lifecycle management
  - `MonitoringConfig`: Configuration dataclass
- **Methods**:
  - `start(callback)`: Begin monitoring
  - `stop()`: Stop monitoring
  - `manual_check()`: Trigger analysis now

### `log_claude_escalation.py` - Claude Integration & Confirmations
- **Purpose**: Escalate complex issues to Claude, manage user approvals
- **Key Classes**:
  - `LogClaudeEscalation`: Send issues to Claude
  - `UserConfirmationManager`: Track approval requests
- **Methods**:
  - `analyze_issues_with_claude()`: Get Claude analysis
  - `create_confirmation_request()`: Create approval
  - `confirm_action()`: User approves fix
  - `get_action_history()`: View all user decisions

## Example Workflow

### Scenario: Orchestrator Returning Empty Responses

1. **5-minute mark**: Log monitor runs
2. **Local Analysis**: Finds 5 "Orchestrator returned empty" lines
3. **Decision**: Critical issue (>3 occurrences) → Escalate to Claude
4. **Notification Sent**:
   ```
   🔍 Log Monitor Alert [CRITICAL]

   *Orchestrator returning empty responses (5x)*

   The orchestrator is returning empty responses, causing fallback...

   📋 Evidence:
     `2025-10-16 20:54:17 - __main__ - WARNING - Orchestrator returned empty response`
     `2025-10-16 20:54:23 - __main__ - WARNING - Orchestrator returned empty response`

   🤖 Escalating to Claude for deeper analysis...

   *Claude Analysis*:
   Root cause likely in orchestrator.py line 45. The invoke_orchestrator
   function returns None when response is empty. Suggested fix: add
   validation before returning...

   ✅ Type `/approve conf_123` to apply suggested fixes
   ❌ Type `/reject conf_123` if you prefer not to apply
   ```

5. **User Response**:
   - Reviews Claude analysis
   - Types: `/approve conf_123`
   - System logs the decision for future reference

6. **Follow-up**: Next check at 5 minutes later monitors if issue persists

### Notification Style

Notifications are concise and action-focused:
- Issue title & evidence (no fluff)
- Claude analysis (if escalated)
- Direct action links: `/approve ID` or `/reject ID`
- No "system is production ready" or verbose status messages

## Performance Impact

### Memory
- Minimal: Only keeps last hour of logs in memory during check
- Clears analysis after each cycle
- Cached Claude responses expire after 1 hour

### API Usage
- **Zero calls** during local analysis (most checks)
- **~1-2 calls/hour** for escalated issues (smart throttling)
- Compared to bot's typical usage: **negligible**

### CPU
- Analysis runs every 5 minutes for ~1 second
- Non-blocking async task
- No impact on message handling

## Troubleshooting

### Monitor Not Starting
Check logs for initialization errors:
```
grep "log monitor" logs/bot.log
```

### Too Many Notifications
Adjust config:
```python
notify_on_warning=False          # Disable warning-level alerts
max_notifications_per_check=1    # Show only most critical
```

### Claude Escalation Not Working
Verify:
1. Claude CLI is working: `claude -p "test"`
2. CLAUDE_CLI_PATH env var is set
3. Check logs for escalation errors

### Issues Not Detected
Increase analysis window:
```python
analysis_window_hours=3  # Look at more history
```

Or check if log file path is correct:
```
ls -la logs/bot.log
```

## Future Enhancements

Potential improvements (tracked separately):
- [ ] Pattern learning - AI detects new issue types over time
- [ ] Trend analysis - Identify degradation patterns
- [ ] Auto-fixes - Apply suggested fixes automatically after approval
- [ ] Metrics dashboard - Show health trends
- [ ] Alert channels - Send to Slack/Discord
- [ ] Custom patterns - User-defined detection rules

## API Reference

### Create Custom Analyzer
```python
from telegram_bot.log_analyzer import LocalLogAnalyzer

analyzer = LocalLogAnalyzer("path/to/log")
issues = analyzer.analyze(hours=2)

for issue in issues:
    print(f"{issue.level}: {issue.title}")
    print(f"Evidence: {issue.evidence[0]}")
```

### Start Monitoring Programmatically
```python
from telegram_bot.log_monitor import LogMonitorManager, MonitoringConfig

config = MonitoringConfig(log_path="logs/bot.log", check_interval_seconds=300)
manager = LogMonitorManager(config)

async def on_issue_found(issue, should_escalate):
    print(f"Issue found: {issue.title}")
    print(f"Escalate to Claude: {should_escalate}")

await manager.start(on_issue_found)

# Later...
await manager.stop()
```

### Get Monitoring Stats
```python
stats = manager.get_stats()
print(f"Monitor running: {stats['running']}")
print(f"Issues detected: {stats['issues_detected']}")
print(f"Recurring issues: {stats['recurring_issues']}")
```

---

**Last Updated**: 2025-10-17
**Status**: ✅ Production Ready
**Memory Impact**: <5MB
**API Cost**: Minimal (mostly local analysis)
