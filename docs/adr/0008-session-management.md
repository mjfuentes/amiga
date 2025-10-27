# 8. Session Management

Date: 2025-01-15

## Status

Accepted

## Context

Users have conversations with the bot that need context preservation:

1. **Conversation continuity**: User references previous messages ("change that", "fix the bug you mentioned")
2. **Multi-turn interactions**: Complex tasks require back-and-forth
3. **State tracking**: Remember user's current workspace/repository
4. **Persistence**: Sessions should survive bot restarts
5. **Memory limits**: Can't keep unlimited history (token costs)
6. **User isolation**: Each user has independent conversation

**Without session management:**
- Agent has no context from previous messages
- User must repeat information every time
- Can't reference previous work
- Poor user experience

**Challenges:**
- Balance history length vs token costs
- Persist sessions across restarts
- Clean up old/inactive sessions
- Support multiple concurrent users

## Decision

Implement **in-memory session management with JSON persistence**.

**Architecture** (`core/session.py`):

```python
@dataclass
class Message:
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str

@dataclass
class Session:
    user_id: int
    created_at: str
    last_activity: str
    history: list[Message]
    current_workspace: str | None

class SessionManager:
    def __init__(self):
        self.sessions: dict[int, Session] = {}  # In-memory
        self.sessions_file = Path("data/sessions.json")
        self._load_sessions()  # Load from disk on startup
```

**Key features:**
1. **In-memory storage**: Fast access, no database queries
2. **Disk persistence**: JSON file for restart recovery
3. **Per-user isolation**: Separate session per Telegram user
4. **Message history**: Stores user and assistant messages
5. **Workspace tracking**: Remembers user's current repository
6. **No timeout**: Sessions persist indefinitely (user must clear explicitly)

**History management:**
- Messages stored in order with timestamps
- Claude API gets last 2 messages (500 chars each) for context
- User can view full history or clear with `/clear` command
- History truncated in API calls to manage token costs

**Session lifecycle:**
```
1. User sends first message → Session created
2. Messages added to history on each interaction
3. Last activity timestamp updated
4. Session persisted to disk after each message
5. Session survives bot restarts (loaded from disk)
6. User calls /clear → History cleared (session kept)
7. Session persists until manual deletion
```

## Consequences

### Positive

- **Fast access**: In-memory lookups (no database queries)
- **Conversation context**: Agent remembers previous messages
- **Restart survival**: Sessions restored from JSON on startup
- **Simple model**: Straightforward dataclass-based design
- **No timeout complexity**: Sessions don't expire unexpectedly
- **Workspace memory**: Remembers user's working repository
- **User control**: `/clear` command to reset when needed

### Negative

- **Memory usage**: All sessions kept in memory (acceptable for single-user)
- **Lost on crashes**: In-memory state lost if JSON save fails
- **No automatic cleanup**: Old sessions never deleted (could grow unbounded)
- **File I/O on every message**: Save to disk after each message (acceptable overhead)
- **Single file risk**: Corruption loses all sessions (mitigated by backups)
- **No distributed support**: Can't share sessions across bot instances

## Alternatives Considered

1. **Database-Only Sessions**
   - Rejected: Slower than in-memory (database query per access)
   - Would require session table in SQLite
   - No significant benefit for our use case

2. **Redis for Session Storage**
   - Rejected: External dependency (Redis server)
   - Overkill for single-machine deployment
   - Would enable distributed sessions (not needed)

3. **Session Timeout**
   - Previous approach: Auto-cleanup after 60 minutes
   - Changed: Sessions persist indefinitely
   - Rationale: Better UX, user controls cleanup with `/clear`

4. **No Persistence (Memory Only)**
   - Rejected: Sessions lost on restart
   - Poor user experience
   - Defeats purpose of session management

5. **Separate File Per Session**
   - Rejected: Too many files to manage
   - Slower to load on startup
   - Single JSON file is simpler

6. **Database + In-Memory Cache**
   - Considered: SQLite for persistence, cache for speed
   - Rejected: Added complexity not justified
   - Current approach is simple and fast enough

## Session Data Structure

**In-memory:**
```python
sessions = {
    123456: Session(
        user_id=123456,
        created_at="2025-01-15T10:00:00Z",
        last_activity="2025-01-15T10:30:00Z",
        history=[
            Message(role="user", content="Hello", timestamp="..."),
            Message(role="assistant", content="Hi!", timestamp="..."),
        ],
        current_workspace="/Users/name/Workspace/myproject"
    )
}
```

**On disk** (`data/sessions.json`):
```json
{
  "123456": {
    "user_id": 123456,
    "created_at": "2025-01-15T10:00:00Z",
    "last_activity": "2025-01-15T10:30:00Z",
    "history": [
      {
        "role": "user",
        "content": "Hello",
        "timestamp": "2025-01-15T10:00:00Z"
      }
    ],
    "current_workspace": "/Users/name/Workspace/myproject"
  }
}
```

## Context Truncation

**For Claude API calls** (`claude/api_client.py`):
- Last 2 messages only (not full history)
- Each message truncated to 500 chars
- Reduces token costs while preserving recent context

**Example:**
```python
# Full history: 50 messages
# API context: Last 2 messages, 500 chars each
context = [
    {"role": "user", "content": history[-2].content[:500]},
    {"role": "assistant", "content": history[-1].content[:500]}
]
```

## References

- Implementation: `core/session.py:53-191`
- Session class: `core/session.py:28-50`
- Message class: `core/session.py:18-25`
- Persistence file: `data/sessions.json`
- Usage in API: `claude/api_client.py` (context building)
- User commands: `/clear` in `core/main.py`
- Timeout removal: Commit 2025-01-10 (session timeout disabled)
