# Session Context - Quick Reference

## Key Files

| File | Purpose | Key Method |
|------|---------|-----------|
| `telegram_bot/session.py` | Session storage & management | `SessionManager` class |
| `telegram_bot/message_queue.py` | Per-user message serialization | `MessageQueueManager` |
| `telegram_bot/claude_api.py` | API integration with context | `ask_claude()` |
| `telegram_bot/main.py` | Bot entry point | Session initialization at line 75 |
| `data/sessions.json` | Persistent storage | User ID -> Session mapping |

## Critical Limits

```
Local Storage (sessions.json):
  └─ UNLIMITED messages per user (persistent)

API Context (ask_claude):
  ├─ Last 2 messages only
  ├─ Truncated to 500 chars each
  ├─ Max 3 active tasks
  └─ ~2048 max response tokens

Orchestrator Context:
  ├─ Last 3 messages
  └─ Reduced for routing

ClaudeCodeSession Context:
  └─ Last 10 messages
```

## How to Increase Context

To include more history for API calls, modify `claude_api.py` line 201:

```python
# Current: Last 2 messages only
for msg in conversation_history[-2:]:  # CHANGE THIS NUMBER

# To get more context (e.g., last 5):
for msg in conversation_history[-5:]:
```

## How to Adjust Message Truncation

Modify `claude_api.py` line 206:

```python
# Current: 500 chars max
truncated = value[:500] if len(value) > 500 else value

# To allow longer messages (e.g., 1000 chars):
truncated = value[:1000] if len(value) > 1000 else value
```

## Session Lifecycle Commands

```bash
/start      # Clear session history + reset context
/clear      # Clear conversation history
/status     # Show session info
/usage      # Show API usage for session

# No command to view current message count
# Check data/sessions.json for full details
```

## Environment Variables (Not Enforced)

```bash
SESSION_TIMEOUT_MINUTES=60  # Ignored - sessions don't timeout
DAILY_COST_LIMIT=100        # Cost ceiling for API calls
MONTHLY_COST_LIMIT=1000     # Monthly cost limit
```

## Message Flow

```
User Message
    ↓
MessageQueueManager (per-user queue)
    ↓
SessionManager.get_session()
    ↓
Extract last 2 messages (claude_api.py:201)
    ↓
Truncate to 500 chars (claude_api.py:206)
    ↓
Sanitize for XML (claude_api.py)
    ↓
ask_claude() API call
    ↓
SessionManager.add_message() x2 (user + assistant)
    ↓
_save_sessions() → data/sessions.json
```

## Storage Details

**Location**: `/Users/matifuentes/Workspace/agentlab/data/sessions.json`

**Format**: 
```json
{
  "USER_ID_INT": {
    "user_id": INT,
    "created_at": "ISO timestamp",
    "last_activity": "ISO timestamp",
    "history": [
      {
        "role": "user" | "assistant",
        "content": "text",
        "timestamp": "ISO timestamp"
      }
    ],
    "current_workspace": "string | null"
  }
}
```

**Size**: Grows with each message. Full deployment example: 26 messages = ~15KB

## Debug Commands

```python
# Get session in Python
from telegram_bot.session import SessionManager
sm = SessionManager()
session = sm.get_session(USER_ID)
print(f"Messages: {len(session.history)}")

# Get stats
stats = sm.get_session_stats(USER_ID)
print(stats)

# Clear session
sm.clear_session(USER_ID)
```

## Known Issues

1. **Context too small**: Only 2 messages sent to API despite storing full history
   - User complaint: "bot sessions losses context too quickly"
   - Solution: Increase `conversation_history[-2:]` to `[-5:]` or more

2. **Session timeout ignored**: `SESSION_TIMEOUT_MINUTES` has no effect
   - Sessions persist indefinitely unless manually cleared
   - No automatic cleanup

3. **No session pagination**: Full history in memory might cause memory issues
   - No archival mechanism for old sessions
   - Risk of bloat over time

## Cost Notes

Each API call:
- Input: ~1200-1550 tokens (system prompt + 2 messages)
- Output: Up to 2048 tokens
- Model: Claude Haiku 4.5
- Cost: ~$0.008 per call (rough estimate)

## Related Files

- Cost tracking: `data/cost_tracking.json`
- Database: `data/agentlab.db` (SQLite - not used for history)
- Tasks: `data/tasks.json` (backup)
- Logs: `logs/bot.log`

---

**Last Updated**: October 20, 2025
