# Telegram Bot - Session Context Retention & Conversation History Implementation

## Executive Summary

The Telegram bot implements persistent session management with JSON file storage and in-memory caching. Session context is maintained per user with conversation history stored locally. The system prioritizes token efficiency through aggressive context truncation and selective message history limits.

---

## 1. Conversation History Storage

### 1.1 Primary Storage Mechanism

**File-Based Storage**: `/Users/matifuentes/Workspace/agentlab/data/sessions.json`

- **Format**: JSON with user_id as keys
- **Structure**: Each session contains:
  - `user_id`: Unique Telegram user identifier (int)
  - `created_at`: ISO timestamp when session started
  - `last_activity`: ISO timestamp of last interaction
  - `history`: List of Message objects
  - `current_workspace`: Current working directory context

### 1.2 Message Structure

Each message in history contains:
```json
{
  "role": "user" | "assistant",
  "content": "Message text",
  "timestamp": "ISO format timestamp"
}
```

### 1.3 Session File Example

Location: `/Users/matifuentes/Workspace/agentlab/data/sessions.json`

The file contains active sessions with full conversation history. Example from actual deployment:
- Session for user 521930094 contains 26 messages dating from Oct 16-20, 2025
- Messages span conversation about UI dashboard improvements, task creation, and feature requests
- Full message content preserved (not truncated in storage)

---

## 2. Session Context Implementation

### 2.1 Core Components

**SessionManager Class** (`telegram_bot/session.py`)
- Manages all user sessions
- In-memory dictionary: `sessions: dict[int, Session]`
- Persistence via JSON file serialization
- Methods for session lifecycle management

**Key Operations**:

```python
class SessionManager:
    def __init__(self, data_dir: str = "data"):
        # Creates data directory, loads existing sessions
        
    def get_or_create_session(self, user_id: int) -> Session:
        # Gets existing session or creates new one
        
    def add_message(self, user_id: int, role: str, content: str):
        # Appends message to history
        
    def get_history(self, user_id: int, limit: int | None = None) -> list[Message]:
        # Retrieves conversation history with optional limit
        
    def clear_session(self, user_id: int):
        # Clears history (triggered by /start command)
        
    def get_session_stats(self, user_id: int) -> dict:
        # Returns metadata: message count, timestamps, workspace
        
    def set_workspace(self, user_id: int, workspace: str):
        # Sets current working repository context
```

### 2.2 Session Lifecycle

1. **Creation**: `/start` command or first message from user
2. **Active Use**: Messages added to history on each interaction
3. **Context Retention**: Full history persisted to disk after each message
4. **Clearing**: `/clear` command or automatic timeout
5. **Deletion**: Manual `/delete` or session cleanup

### 2.3 Initialization & Loading

**Startup Process** (main.py, line 75):
```python
session_manager = SessionManager()  # Loads from data/sessions.json
```

**Automatic Persistence**: After each message added
```python
def add_message(self, user_id: int, role: str, content: str):
    session = self.get_or_create_session(user_id)
    message = Message(role=role, content=content, timestamp=datetime.now().isoformat())
    session.history.append(message)
    session.last_activity = message.timestamp
    self._save_sessions()  # Persist to disk
```

---

## 3. History Limits & Configurations

### 3.1 Session-Level Limits

**Maximum Messages Per Session**: UNLIMITED (configured as persistent)
- Historical comment: "now a no-op since sessions don't timeout"
- Sessions persist indefinitely until explicitly cleared

**Recent Conversation Context Passed to APIs**:
- Last 2 messages only (claude_api.py, line 201)
- Truncated to 500 characters per message (claude_api.py, line 206)

### 3.2 API Call Context Optimization

**claude_api.py** - Token Efficiency Strategy:

| Component | Limit | Rationale |
|-----------|-------|-----------|
| Conversation History | Last 2 messages | Token efficiency for API calls |
| Message Truncation | 500 chars max | Prevent huge context bloat |
| Active Tasks Included | Max 3 tasks | Avoid overwhelming context |
| Repositories List | Omitted | Saves ~100 tokens |
| Log Lines | Last 50 lines | Reduce token usage vs. 200 lines |

**Code Reference** (claude_api.py):
```python
# Optimize context: Sanitize and truncate conversation history
safe_history = []
for msg in conversation_history[-2:]:  # Last 2 messages only
    safe_msg = {}
    for key, value in msg.items():
        if isinstance(value, str):
            # Truncate very long messages to save tokens
            truncated = value[:500] if len(value) > 500 else value
            safe_msg[key] = sanitize_xml_content(truncated)
        else:
            safe_msg[key] = value
    safe_history.append(safe_msg)

# Optimize context: Only include essential task info
safe_tasks = []
for task in active_tasks[:3]:  # Max 3 recent tasks
    safe_task = {
        "id": task.get("id", ""),
        "status": task.get("status", ""),
        # Omit description to save tokens unless critical
    }
    safe_tasks.append(safe_task)
```

### 3.3 Context Window Settings

**ClaudeCodeSession** (session.py, line 201):
```python
def _format_conversation_context(self, user_id: int) -> str:
    """Format conversation history as context for Claude"""
    history = self.session_manager.get_history(user_id, limit=10)  # Last 10 messages
```

**Orchestrator Context** (orchestrator.py, line 96):
```python
context = {
    "conversation_history": conversation_history[-3:],  # Last 3 messages (reduced context)
    # ...
}
```

**Summary of Context Windows**:
- Full session storage: Unlimited
- Claude API context: Last 2 messages
- Orchestrator context: Last 3 messages  
- ClaudeCodeSession context: Last 10 messages

### 3.4 Environment Configuration

**File**: `.env` or `.env.example`

```bash
# Session Settings
SESSION_TIMEOUT_MINUTES=60  # No longer enforced - sessions don't timeout
```

Note: Timeout setting exists but is not actively enforced. The `cleanup_stale_sessions()` method is now a no-op (session.py, line 152-153).

---

## 4. Message Storage Mechanisms

### 4.1 Write Flow

**User Message → Storage**:
1. User sends message via Telegram
2. `main.py` receives update via handler (e.g., `handle_message()`)
3. Message queued for processing (MessageQueueManager)
4. Handler retrieves session: `session = session_manager.get_session(user_id)`
5. Convert stored messages to dict format:
   ```python
   history = [{"role": msg.role, "content": msg.content} for msg in session.history] if session else []
   ```
6. History passed to `ask_claude()` API function
7. After receiving response, message added to session:
   ```python
   session_manager.add_message(user_id, "user", message_text)
   session_manager.add_message(user_id, "assistant", response_text)
   ```

### 4.2 Storage Persistence

**Automatic Saving** (session.py, line 82-91):
```python
def _save_sessions(self):
    """Save sessions to disk"""
    try:
        data = {str(user_id): session.to_dict() for user_id, session in self.sessions.items()}
        with open(self.sessions_file, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving sessions: {e}")
```

- Triggered after: Each message addition, session clear, workspace change
- Format: Pretty-printed JSON for readability
- Location: `data/sessions.json`
- Encoding: UTF-8

### 4.3 Load on Startup

**Initialization** (session.py, line 65-80):
```python
def _load_sessions(self):
    """Load sessions from disk"""
    if not self.sessions_file.exists():
        return
    try:
        with open(self.sessions_file) as f:
            data = json.load(f)
            for user_id_str, session_data in data.items():
                user_id = int(user_id_str)
                session = Session.from_dict(session_data)
                self.sessions[user_id] = session
        logger.info(f"Loaded {len(self.sessions)} sessions from disk")
    except Exception as e:
        logger.error(f"Error loading sessions: {e}")
```

- Runs during `SessionManager.__init__()`
- Deserializes JSON to Session/Message objects
- Loaded sessions kept in memory

---

## 5. Context Management Architecture

### 5.1 Context Flow Diagram

```
User Message (Telegram)
    ↓
Message Queue (per-user serialization)
    ↓
retrieve full session from SessionManager
    ↓
extract last 2 messages + truncate to 500 chars each
    ↓
sanitize for XML injection safety
    ↓
build system prompt with context
    ↓
call claude_api.ask_claude()
    ↓
add response to session history
    ↓
persist to data/sessions.json
```

### 5.2 Per-User Isolation

**Message Queue Manager** (`message_queue.py`):
- Each user has dedicated `UserMessageQueue`
- Messages from same user processed sequentially
- Prevents race conditions in history updates
- Enforces per-user rate limiting

**Session Manager**:
- Independent session dictionary per user_id
- No shared history between users
- Workspace context stored per user

### 5.3 Context Window Behavior

**Current Session Lost Issue** (from conversation history):
```
User: "bot sessions losses context too quickly lets keep more conversation history in context"
Assistant: "Task #3378aa started. Expanding session memory to keep more conversation history in context."
```

This indicates the system currently limits context too aggressively:
- Only 2 messages sent to API despite storing full history
- Users want more conversation continuity
- System preserves all history locally but uses minimal context

---

## 6. Token Limit Settings

### 6.1 API Call Token Limits

**Claude API Calls** (claude_api.py, line 418):
```python
response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=2048,  # Hard limit on response length
    system=system_prompt,
    messages=messages
)
```

**Model-Specific Limits**:
- Model: Claude Haiku 4.5
- Max output tokens: 2048
- Model input window: ~100,000 tokens (Haiku standard)

### 6.2 Context Token Budget

**Approximate Token Allocation**:
- System prompt: ~800-1000 tokens
- Last 2 messages: ~50-200 tokens (heavily truncated)
- Active tasks (max 3): ~100-150 tokens
- Current context info: ~200 tokens
- **Total context per call: ~1200-1550 tokens**
- **Response budget: 2048 tokens**

### 6.3 Cost Optimization Features

From CLAUDE.md:
> "Token minimization in claude_api.py:
> - Conversation history: Last 2 messages only, truncate to 500 chars
> - Active tasks: Max 3 tasks, omit descriptions
> - Logs: Last 50 lines only (not 200)
> - Don't include `available_repositories` list (~100 tokens saved)"

**Cost Per Session**:
- Tracked in `data/cost_tracking.json`
- Per-model costs (Haiku vs. Sonnet)
- Daily/monthly cost ceilings enforced

---

## 7. Where These Limits Are Configured

### 7.1 Hard-Coded Limits

| Parameter | Location | Value | Purpose |
|-----------|----------|-------|---------|
| History for API | claude_api.py:201 | Last 2 messages | Token efficiency |
| Message truncation | claude_api.py:206 | 500 characters | Cap message size |
| Active tasks | claude_api.py:214 | Max 3 tasks | Reduce context bloat |
| ClaudeCodeSession context | session.py:201 | Last 10 messages | Local session use |
| Orchestrator context | orchestrator.py:96 | Last 3 messages | Routing decision context |
| Max response tokens | claude_api.py:418 | 2048 | API response cap |
| Log lines | claude_api.py:394 | Last 50 lines | Log truncation |

### 7.2 Environment-Based Configuration

**File**: `.env` (from `.env.example`)

```bash
SESSION_TIMEOUT_MINUTES=60  # Not enforced - sessions persistent
DAILY_COST_LIMIT=100         # Stop API calls if exceeded
MONTHLY_COST_LIMIT=1000      # Stop API calls if exceeded
```

### 7.3 Database Configuration

**SQLite Database** (`telegram_bot/database.py`):
- Tasks table with activity logs
- Tool usage tracking
- Agent status history
- Games state
- No direct history storage (using sessions.json instead)

---

## 8. Architecture Summary

### 8.1 Two-Tier History System

**Tier 1: Full Local Storage (Persistent)**
- Location: `data/sessions.json`
- Content: Complete conversation history per user
- Retention: Indefinite until manual clear
- Access: On-demand, in-memory after load

**Tier 2: API Context (Transient)**
- Content: Last 2 messages, truncated
- Purpose: API efficiency
- Lifetime: Single API call
- Token budget: ~400-500 tokens

### 8.2 Session Lifecycle

```
Initialization:
  └─ Load data/sessions.json → in-memory SessionManager

Message Handling:
  ├─ Get session (or create)
  ├─ Retrieve full history from memory
  ├─ Extract last 2 messages for API
  ├─ Call claude_api.ask_claude()
  ├─ Add user + assistant messages to history
  └─ Persist to data/sessions.json

Cleanup:
  ├─ /clear command → clear_session()
  ├─ /start command → clear_session()
  └─ Manual deletion → delete_session()
```

### 8.3 Message Processing Queue

**per-user serialization** via `MessageQueueManager`:
- Ensures messages processed sequentially per user
- Prevents concurrent history updates
- Maintains order of conversation

---

## 9. Key Limitations & Observations

### 9.1 Current Limitations

1. **Context Loss for Extended Conversations**
   - Only 2 messages sent to API despite storing full history
   - User complaint: "bot sessions losses context too quickly"
   - Full history available locally but underutilized

2. **Timeout Configuration Not Active**
   - `SESSION_TIMEOUT_MINUTES=60` in `.env` is ignored
   - Comment: "now a no-op since sessions don't timeout"
   - Sessions persist indefinitely

3. **No Automatic Cleanup**
   - `cleanup_stale_sessions()` returns 0 (no-op)
   - Must manually clear with `/clear` or `/start`
   - Risk of memory bloat over time

4. **Token Budget Conservative**
   - 2-message limit very aggressive
   - Could support 5-10 messages within same token budget
   - Prioritizes API cost over conversation continuity

### 9.2 Design Strengths

1. **Persistent Storage**
   - Full conversation history preserved
   - Survives bot restarts
   - Human-readable JSON format

2. **Per-User Isolation**
   - No cross-user context leakage
   - Independent session management
   - Per-user rate limiting

3. **Security**
   - XML sanitization before API calls
   - Prompt injection detection
   - File path validation

4. **Flexibility**
   - In-memory caching of sessions
   - Configurable context windows per component
   - Extensible message format

---

## 10. Future Improvements (Identified)

From conversation history, user requests:
1. Increase context history to reduce context loss
2. Simplify logging output
3. Add WebSocket support for live dashboard
4. Maintain more conversation history in API context

---

## Appendix: Configuration Reference

### Complete Environment Variables

```bash
# Session Management
SESSION_TIMEOUT_MINUTES=60  # Not enforced (no-op)

# Cost Control
DAILY_COST_LIMIT=100
MONTHLY_COST_LIMIT=1000

# API Keys
ANTHROPIC_API_KEY=<key>
ANTHROPIC_ADMIN_API_KEY=<key>

# Bot Configuration
TELEGRAM_BOT_TOKEN=<token>
ALLOWED_USERS=<user_ids>
CLAUDE_CLI_PATH=claude
WORKSPACE_PATH=/Users/matifuentes/Workspace
LOG_LEVEL=INFO
```

### File Structure

```
data/
├── sessions.json          # Persistent user sessions + history
├── cost_tracking.json     # API usage costs
├── usage.json            # Usage statistics
├── agentlab.db          # SQLite database (tasks, tools, games)
└── tasks.json           # Backup task data

telegram_bot/
├── session.py           # SessionManager, Session, Message classes
├── message_queue.py     # Per-user message serialization
├── claude_api.py        # API integration with context management
├── orchestrator.py      # Orchestrator with context window config
├── main.py              # Bot entry point, session initialization
└── database.py          # SQLite backend (optional, not for history)
```

### Session Storage Example

```json
{
  "521930094": {
    "user_id": 521930094,
    "created_at": "2025-10-16T21:02:38.779264",
    "last_activity": "2025-10-20T15:17:18.806760",
    "history": [
      {
        "role": "user",
        "content": "message text",
        "timestamp": "2025-10-20T14:58:45.279398"
      },
      {
        "role": "assistant",
        "content": "response text",
        "timestamp": "2025-10-20T14:58:45.280508"
      }
    ],
    "current_workspace": null
  }
}
```

---

**Document Generated**: October 20, 2025
**Codebase**: AMIGA Telegram Bot
**Status**: Current as of latest deployment

