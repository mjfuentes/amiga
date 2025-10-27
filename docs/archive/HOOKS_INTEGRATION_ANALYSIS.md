# Claude Code Hooks Integration Analysis
## Task #3126492d Findings & Implementation Strategy

**Generated:** 2025-10-17
**Based on:** claude-code-hooks-multi-agent-observability repository analysis

---

## Executive Summary

Task #3126492d investigated the **claude-code-hooks-multi-agent-observability** repository and identified comprehensive patterns for implementing Claude Code hooks. This document synthesizes those findings with the agentlab Telegram bot's architecture to propose practical integration strategies.

### Key Opportunities Identified

1. **Task Lifecycle Observability** - Track all background task executions
2. **Validation & Safety** - Prevent dangerous operations in bot code
3. **Cost Tracking Enhancement** - Real-time monitoring of Claude API usage
4. **Multi-Agent Coordination** - Monitor concurrent task execution
5. **User Notifications** - Proactive alerts for task completion/failures

---

## 1. Architecture Patterns from Task #3126492d

### 1.1 Event Flow Architecture

```
Claude Agent → Hook Script → HTTP POST → Backend Server → WebSocket → UI/Notifications
     ↓
  Validation
     ↓
  Logging
     ↓
  Exit Code (0/2/other)
```

**Key Insight:** Hooks should **always succeed** (exit 0) unless blocking is intentional (exit 2).

### 1.2 Hook Types & Events

The reference implementation supports:

| Event Type | When Triggered | Use Case |
|------------|---------------|----------|
| **PreToolUse** | Before tool execution | Validation, dangerous command blocking |
| **PostToolUse** | After tool execution | Success tracking, metrics |
| **UserPromptSubmit** | User sends message | Context injection, logging |
| **Notification** | Claude sends notification | Alerting, monitoring |
| **Stop/SubagentStop** | Task completion | Cleanup, final reporting |
| **PreCompact** | Before context compaction | State preservation |
| **SessionStart/End** | Session lifecycle | Setup, teardown, analytics |

### 1.3 Configuration Structure

From `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "command": ["python3", ".claude/hooks/pre_tool_use.py"],
        "description": "Validate and block dangerous commands",
        "matcher": {
          "tool": "Bash"
        }
      },
      {
        "command": ["python3", ".claude/hooks/send_event.py",
                    "--source-app", "claude-code",
                    "--event-type", "pre_tool_use"],
        "description": "Log tool usage to observability system"
      }
    ],
    "PostToolUse": [...],
    "UserPromptSubmit": [...],
    "Stop": [...]
  }
}
```

**Pattern:** Multiple hooks per event, sequential execution, universal sender script.

### 1.4 Best Practices Identified

1. **Always use absolute paths** or `$CLAUDE_PROJECT_DIR` environment variable
2. **Dual-purpose hooks**: Validation + observability in single event
3. **Fail silently**: Never break Claude Code workflow
4. **Session isolation**: Log events per session for organization
5. **Modular design**: Reusable utilities (LLM, TTS, constants)
6. **Graceful degradation**: Optional features fail silently
7. **Real-time feedback**: WebSocket for instant updates

---

## 2. Current Bot Architecture Analysis

### 2.1 Relevant Components

**File:** `telegram_bot/claude_interactive.py:186-286`

```python
class ClaudeSessionPool:
    """Pool of Claude sessions for concurrent task execution"""

    async def execute_task(
        self, task_id, description, workspace,
        bot_repo_path, model, pid_callback
    ):
        # Starts: `claude chat --model sonnet --permission-mode bypassPermissions`
        # Sends: User request with context
        # Returns: (success, result, pid)
```

**Current Flow:**
1. User sends message → Telegram bot
2. Bot routes to `execute_code_task()` → `telegram_bot/main.py:427`
3. Task created → `TaskManager` → `data/tasks.json`
4. `ClaudeSessionPool.execute_task()` spawns `claude chat` process
5. Process completes → Result sent to user

**Gaps:**
- ✗ No observability into what tools Claude uses
- ✗ No validation of dangerous operations
- ✗ No real-time progress updates
- ✗ No session-level logging beyond high-level task status
- ✗ Limited context about why tasks fail

### 2.2 Existing Infrastructure

**Strengths:**
- ✓ Task tracking (`telegram_bot/tasks.py`)
- ✓ Cost tracking (`telegram_bot/cost_tracker.py`)
- ✓ Rate limiting (`telegram_bot/rate_limiter.py`)
- ✓ Log monitoring (`telegram_bot/log_monitor.py`)
- ✓ Worker pool for concurrency (`telegram_bot/worker_pool.py`)
- ✓ Message queue per user (`telegram_bot/message_queue.py`)

**Integration Points:**
- Task lifecycle hooks can integrate with `TaskManager`
- Tool usage can enhance `CostTracker` with real token counts
- Session logs can feed into `LogMonitor`

---

## 3. Proposed Integration Strategy

### 3.1 Phase 1: Foundation (2-3 hours)

**Goal:** Basic hook infrastructure with validation & logging

#### 3.1.1 Directory Structure

```
agentlab/
├── .claude/
│   ├── settings.json          # Hook configuration
│   ├── hooks/
│   │   ├── utils/
│   │   │   ├── __init__.py
│   │   │   ├── constants.py   # Session log paths
│   │   │   └── telegram.py    # Bot notification helpers
│   │   ├── pre_tool_use.py    # Validation hook
│   │   ├── post_tool_use.py   # Logging hook
│   │   └── task_lifecycle.py  # Stop/SessionEnd hook
│   └── agents/                # (existing)
├── telegram_bot/
│   ├── hooks_manager.py       # NEW: Hook event coordinator
│   └── ... (existing files)
└── logs/
    └── sessions/              # NEW: Per-session hook logs
        └── <task_id>/
            ├── pre_tool_use.json
            ├── post_tool_use.json
            └── summary.json
```

#### 3.1.2 Hook Scripts

**`.claude/hooks/pre_tool_use.py`** (Validation)

```python
#!/usr/bin/env python3
"""Validate tool usage before execution"""
import json
import re
import sys
from pathlib import Path

def main():
    # Read event from stdin
    event = json.load(sys.stdin)

    tool_name = event.get("tool_name")
    parameters = event.get("parameters", {})

    # Block dangerous Bash commands
    if tool_name == "Bash":
        command = parameters.get("command", "")

        dangerous_patterns = [
            r"rm\s+-rf\s+/",           # Root deletion
            r"rm\s+-rf\s+\*",          # Wildcard deletion
            r"mkfs\.",                 # Format filesystem
            r"dd\s+if=.*of=/dev",      # Direct disk write
            r":(){ :|:& };:",          # Fork bomb
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, command):
                print(f"BLOCKED: Dangerous command pattern detected: {pattern}",
                      file=sys.stderr)
                sys.exit(2)  # Block with error

    # Prevent editing .env files (credentials)
    if tool_name in ["Edit", "Write"]:
        file_path = parameters.get("file_path", "")
        if ".env" in file_path and not file_path.endswith(".env.example"):
            print(f"BLOCKED: Cannot modify .env files", file=sys.stderr)
            sys.exit(2)

    # Allow - log to session directory
    task_id = event.get("session_id", "unknown")
    log_dir = Path(f"logs/sessions/{task_id}")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "pre_tool_use.json"
    logs = []
    if log_file.exists():
        with open(log_file) as f:
            logs = json.load(f)

    logs.append({
        "tool": tool_name,
        "parameters": parameters,
        "timestamp": event.get("timestamp"),
        "status": "allowed"
    })

    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

    # Success - allow execution
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**`.claude/hooks/post_tool_use.py`** (Logging)

```python
#!/usr/bin/env python3
"""Log tool usage after execution"""
import json
import sys
from pathlib import Path

def main():
    event = json.load(sys.stdin)

    tool_name = event.get("tool_name")
    result = event.get("result", {})
    success = result.get("success", False)

    # Log to session directory
    task_id = event.get("session_id", "unknown")
    log_dir = Path(f"logs/sessions/{task_id}")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "post_tool_use.json"
    logs = []
    if log_file.exists():
        with open(log_file) as f:
            logs = json.load(f)

    logs.append({
        "tool": tool_name,
        "success": success,
        "timestamp": event.get("timestamp"),
        "output_length": len(str(result.get("output", "")))
    })

    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

    # Always succeed (non-blocking)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**`.claude/hooks/task_lifecycle.py`** (Task completion)

```python
#!/usr/bin/env python3
"""Handle task lifecycle events"""
import json
import sys
from pathlib import Path

def main():
    event = json.load(sys.stdin)
    event_type = event.get("event_type")
    task_id = event.get("session_id", "unknown")

    if event_type == "Stop":
        # Generate summary of tool usage
        log_dir = Path(f"logs/sessions/{task_id}")

        pre_tools = []
        post_tools = []

        if (log_dir / "pre_tool_use.json").exists():
            with open(log_dir / "pre_tool_use.json") as f:
                pre_tools = json.load(f)

        if (log_dir / "post_tool_use.json").exists():
            with open(log_dir / "post_tool_use.json") as f:
                post_tools = json.load(f)

        summary = {
            "task_id": task_id,
            "total_tools_used": len(post_tools),
            "tools_by_type": {},
            "blocked_operations": len([t for t in pre_tools if t.get("status") == "blocked"]),
            "failed_tools": len([t for t in post_tools if not t.get("success", True)])
        }

        for tool in post_tools:
            tool_name = tool.get("tool")
            summary["tools_by_type"][tool_name] = summary["tools_by_type"].get(tool_name, 0) + 1

        with open(log_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        print(f"Task {task_id} completed: {summary['total_tools_used']} tools used")

    sys.exit(0)

if __name__ == "__main__":
    main()
```

#### 3.1.3 Configuration

**`.claude/settings.json`**

```json
{
  "permissions": {
    "allow": ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)", "Glob(*)", "Grep(*)"],
    "deny": [],
    "ask": []
  },
  "outputStyle": "concise",
  "hooks": {
    "PreToolUse": [
      {
        "command": ["python3", "$CLAUDE_PROJECT_DIR/.claude/hooks/pre_tool_use.py"],
        "description": "Validate and block dangerous operations"
      }
    ],
    "PostToolUse": [
      {
        "command": ["python3", "$CLAUDE_PROJECT_DIR/.claude/hooks/post_tool_use.py"],
        "description": "Log tool usage for analytics"
      }
    ],
    "Stop": [
      {
        "command": ["python3", "$CLAUDE_PROJECT_DIR/.claude/hooks/task_lifecycle.py"],
        "description": "Generate task completion summary"
      }
    ]
  }
}
```

#### 3.1.4 Bot Integration

**`telegram_bot/hooks_manager.py`** (NEW)

```python
"""Hook event coordinator for Telegram bot"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class HooksManager:
    """Manages hook logs and provides analytics"""

    def __init__(self, sessions_dir: str = "logs/sessions"):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def get_task_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get tool usage summary for a task"""
        summary_file = self.sessions_dir / task_id / "summary.json"

        if not summary_file.exists():
            return None

        try:
            with open(summary_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading task summary {task_id}: {e}")
            return None

    def get_tool_usage_history(self, task_id: str) -> Dict[str, Any]:
        """Get detailed tool usage history"""
        task_dir = self.sessions_dir / task_id

        if not task_dir.exists():
            return {"error": "Task not found"}

        history = {
            "task_id": task_id,
            "pre_tool_use": [],
            "post_tool_use": [],
            "summary": None
        }

        try:
            if (task_dir / "pre_tool_use.json").exists():
                with open(task_dir / "pre_tool_use.json") as f:
                    history["pre_tool_use"] = json.load(f)

            if (task_dir / "post_tool_use.json").exists():
                with open(task_dir / "post_tool_use.json") as f:
                    history["post_tool_use"] = json.load(f)

            if (task_dir / "summary.json").exists():
                with open(task_dir / "summary.json") as f:
                    history["summary"] = json.load(f)
        except Exception as e:
            logger.error(f"Error reading tool history {task_id}: {e}")

        return history

    def format_summary_for_user(self, task_id: str) -> str:
        """Format task summary for Telegram display"""
        summary = self.get_task_summary(task_id)

        if not summary:
            return "No detailed logs available"

        tools_used = summary.get("total_tools_used", 0)
        failed = summary.get("failed_tools", 0)
        blocked = summary.get("blocked_operations", 0)

        msg = f"*Task Analytics*\n\n"
        msg += f"• Tools executed: {tools_used}\n"

        if blocked > 0:
            msg += f"• Blocked operations: {blocked}\n"

        if failed > 0:
            msg += f"• Failed operations: {failed}\n"

        tools_by_type = summary.get("tools_by_type", {})
        if tools_by_type:
            msg += f"\n*Tool Breakdown:*\n"
            for tool, count in sorted(tools_by_type.items(), key=lambda x: -x[1])[:5]:
                msg += f"• {tool}: {count}\n"

        return msg
```

**Update `telegram_bot/main.py:427-490`** (execute_code_task)

```python
# Add at top
from hooks_manager import HooksManager
hooks_manager = HooksManager()

# In execute_code_task, after task completion (line ~458):
if success:
    task_manager.update_task(task.task_id, status="completed", result=result)
    logger.info(f"Task {task.task_id} completed successfully")

    # Get hook analytics
    analytics = hooks_manager.format_summary_for_user(task.task_id)

    # Notify user with analytics
    notification = (
        f"*Task Complete* (#{task.task_id})\n\n"
        f"{task.description}\n\n"
        f"**Result:**\n{result}\n\n"
        f"{analytics}"  # ADD THIS
    )
```

### 3.2 Phase 2: Real-Time Observability (3-4 hours)

**Goal:** WebSocket server for live task monitoring

#### 3.2.1 Backend Server

Similar to reference implementation, create a lightweight server:

```
telegram_bot/
├── observability/
│   ├── __init__.py
│   ├── server.py       # WebSocket + HTTP server
│   ├── db.py           # SQLite event storage
│   └── client.html     # Dashboard UI
```

**Key Features:**
- HTTP POST endpoint for hook events
- WebSocket broadcast for real-time updates
- SQLite storage for historical queries
- Dashboard showing:
  - Active tasks
  - Tool usage in real-time
  - Error rates
  - Cost per task

**Integration:**
- Update hook scripts to POST events to local server
- Bot can query server for analytics
- Users can access dashboard via browser

### 3.3 Phase 3: Advanced Features (Optional, 4-5 hours)

#### 3.3.1 Context Injection

Use `UserPromptSubmit` hook to inject context:

```python
# .claude/hooks/user_prompt_submit.py
def main():
    event = json.load(sys.stdin)

    # Read recent task failures from TaskManager
    recent_failures = get_recent_failures()

    if recent_failures:
        context = "\nNOTE: Recent task failures:\n"
        for task in recent_failures:
            context += f"- {task['description']}: {task['error']}\n"

        # Output to stdout (added to context)
        print(context)

    sys.exit(0)
```

#### 3.3.2 Cost Tracking Enhancement

Track actual tokens used (from PostToolUse) vs estimates:

```python
# In post_tool_use.py
if tool_name == "Claude":
    actual_tokens = result.get("tokens_used")
    # Send to CostTracker for refinement
```

#### 3.3.3 Proactive Notifications

Send Telegram alerts when:
- Task uses more than X tools (potential runaway)
- Dangerous operation blocked
- Error rate exceeds threshold

---

## 4. Implementation Roadmap

### Week 1: Foundation
- [ ] Day 1-2: Create hook scripts (pre_tool_use, post_tool_use, task_lifecycle)
- [ ] Day 3: Integrate HooksManager with TaskManager
- [ ] Day 4: Update /status command to show hook analytics
- [ ] Day 5: Testing & documentation

### Week 2: Observability (Optional)
- [ ] Day 1-2: Build WebSocket server
- [ ] Day 3: Create dashboard UI
- [ ] Day 4-5: Integration & testing

### Week 3: Polish (Optional)
- [ ] Advanced features (context injection, proactive alerts)
- [ ] Performance optimization
- [ ] User documentation

---

## 5. Expected Benefits

### Immediate (Phase 1)
1. **Safety**: Prevent accidental destructive operations
2. **Visibility**: Understand what Claude does during tasks
3. **Debugging**: Identify why tasks fail
4. **Analytics**: Track tool usage patterns

### Medium-Term (Phase 2)
1. **Real-time monitoring**: Watch tasks as they execute
2. **Historical analysis**: Query past task behavior
3. **Cost optimization**: Identify expensive operations
4. **User confidence**: Show users exactly what's happening

### Long-Term (Phase 3)
1. **Predictive alerts**: Warn before issues occur
2. **Auto-optimization**: Learn from patterns
3. **Multi-agent coordination**: Prevent conflicts
4. **Compliance**: Audit trail for all operations

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Hook scripts fail | Task blocked | Ensure all hooks exit 0 on error |
| Performance overhead | Slower tasks | Use async I/O, minimal processing |
| Log storage growth | Disk space | Implement rotation/cleanup |
| Complexity creep | Hard to maintain | Start minimal, add incrementally |

---

## 7. Success Metrics

After Phase 1 implementation:
- [ ] 100% of background tasks have hook logs
- [ ] Zero unintended dangerous operations
- [ ] Task failure root cause identified in <2 minutes
- [ ] Users see tool usage summary in completion notifications

After Phase 2 implementation:
- [ ] Real-time dashboard shows live task execution
- [ ] Historical queries answer "what did Claude do?" in <1 second
- [ ] Cost tracking accuracy improves by 20%+

---

## 8. Next Steps

### Immediate Actions
1. **Review this document** with team/stakeholders
2. **Create feature branch**: `git checkout -b feature/hooks-integration`
3. **Start with Phase 1, Day 1**: Implement basic hook scripts
4. **Test with single task**: Verify logs are created
5. **Iterate**: Add features incrementally

### Decision Points
- **Go/No-Go on Phase 2**: After Phase 1 evaluation (2 weeks)
- **Dashboard design review**: Before building UI
- **User beta testing**: Small group before full rollout

---

## Appendix A: Reference Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Telegram Bot                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ User Message │───▶│ TaskManager  │───▶│ ClaudePool   │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                   │              │
└───────────────────────────────────────────────────┼──────────────┘
                                                    ▼
                                          ┌─────────────────┐
                                          │  claude chat    │
                                          │  (subprocess)   │
                                          └────────┬────────┘
                                                   │
                   ┌───────────────────────────────┼───────────────────────┐
                   │                    Claude Code Hooks                  │
                   │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
                   │  │ PreToolUse   │  │ PostToolUse  │  │ Stop/End    │ │
                   │  │ (validate)   │  │ (log)        │  │ (summarize) │ │
                   │  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
                   └─────────┼──────────────────┼──────────────────┼────────┘
                             ▼                  ▼                  ▼
                   ┌─────────────────────────────────────────────────────┐
                   │         logs/sessions/<task_id>/                    │
                   │  • pre_tool_use.json                                │
                   │  • post_tool_use.json                               │
                   │  • summary.json                                     │
                   └─────────────────┬───────────────────────────────────┘
                                     ▼
                   ┌─────────────────────────────────────────────────────┐
                   │              HooksManager                            │
                   │  • Read session logs                                 │
                   │  • Generate analytics                                │
                   │  • Format for Telegram                               │
                   └─────────────────┬───────────────────────────────────┘
                                     ▼
                   ┌─────────────────────────────────────────────────────┐
                   │         Telegram Notification                        │
                   │  "Task Complete                                      │
                   │   • Tools used: 12                                   │
                   │   • Bash: 5, Edit: 4, Read: 3"                      │
                   └─────────────────────────────────────────────────────┘
```

---

## Appendix B: Example Session Log

**`logs/sessions/abc123de/summary.json`**

```json
{
  "task_id": "abc123de",
  "total_tools_used": 12,
  "tools_by_type": {
    "Read": 3,
    "Edit": 4,
    "Bash": 5
  },
  "blocked_operations": 0,
  "failed_tools": 1,
  "duration_seconds": 45.3,
  "timestamp_start": "2025-10-17T12:30:00Z",
  "timestamp_end": "2025-10-17T12:30:45Z"
}
```

---

**Document Status:** Draft v1.0
**Author:** Claude (via task #af059d14)
**Review:** Pending
