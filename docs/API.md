# AMIGA API Documentation

> Comprehensive reference for internal APIs, managers, database layer, and data flows

**Last Updated**: 2025-10-22
**Audience**: Developers, QA agents, debugging workflows

---

## Table of Contents

1. [Database Layer](#database-layer)
2. [Manager Classes Overview](#manager-classes-overview)
3. [Manager Classes Detail](#manager-classes-detail)
4. [Key Data Flows](#key-data-flows)
5. [API Examples](#api-examples)

---

## Database Layer

### Database Class (`database.py`)

Centralized SQLite backend for all persistent storage. Replaces previous JSON file-based storage.

**Location**: `telegram_bot/database.py`
**Schema Version**: 10 (auto-migrated)
**Storage**: `data/agentlab.db` (configurable via `config.DATABASE_PATH`)

#### Initialization

```python
# Recommended: Use centralized config
from database import Database
db = Database()  # Uses config.DATABASE_PATH

# Legacy: Explicit path (backward compatibility)
db = Database(db_path="data/agentlab.db")
```

**Configuration** (`database.py:25-56`):
- Auto-creates database file and parent directories
- Enables WAL mode for better concurrency
- Enables foreign keys
- Row factory returns dict-like objects (access by column name)
- Write lock for async safety (`_write_lock`)

#### Database Schema

##### Tasks Table (`database.py:95-114`)

Primary table for background task tracking.

```sql
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,           -- 6-char UUID prefix
    user_id INTEGER NOT NULL,            -- Telegram user ID
    description TEXT NOT NULL,           -- Task description
    status TEXT NOT NULL,                -- pending/running/completed/failed/stopped
    created_at TEXT NOT NULL,            -- ISO 8601 timestamp
    updated_at TEXT NOT NULL,            -- ISO 8601 timestamp
    model TEXT NOT NULL,                 -- haiku/sonnet/opus
    workspace TEXT NOT NULL,             -- Repository path
    agent_type TEXT NOT NULL DEFAULT 'code_agent',  -- code_agent/frontend_agent/research_agent
    session_uuid TEXT,                   -- UUID for logs/sessions/<uuid>/
    result TEXT,                         -- Task result on completion
    error TEXT,                          -- Error message on failure
    pid INTEGER,                         -- Claude Code process ID
    activity_log TEXT,                   -- JSON array of activity entries
    workflow TEXT,                       -- Workflow used (e.g., 'code-task')
    context TEXT                         -- Context summary from Claude API
);

-- Indices for performance
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status, created_at DESC);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX idx_tasks_status ON tasks(status);
```

##### Tool Usage Table (`database.py:119-130`)

Records every tool invocation by Claude Code agents.

```sql
CREATE TABLE tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,             -- ISO 8601 timestamp
    task_id TEXT NOT NULL,               -- Links to tasks.task_id
    tool_name TEXT NOT NULL,             -- Read/Write/Edit/Bash/Grep/Glob
    duration_ms REAL,                    -- Execution time
    success BOOLEAN,                     -- True/False/NULL
    error TEXT,                          -- Error message if failed
    error_category TEXT,                 -- Categorized error type
    parameters TEXT,                     -- JSON blob of tool params
    screenshot_path TEXT,                -- Path to screenshot if captured
    input_tokens INTEGER,                -- Token usage metrics
    output_tokens INTEGER,
    cache_creation_tokens INTEGER,
    cache_read_tokens INTEGER
);

-- Indices for performance
CREATE INDEX idx_tool_timestamp ON tool_usage(timestamp DESC);
CREATE INDEX idx_tool_task ON tool_usage(task_id);
CREATE INDEX idx_tool_name ON tool_usage(tool_name);
```

##### Agent Status Table (`database.py:134-144`)

Status change tracking for agent lifecycle monitoring.

```sql
CREATE TABLE agent_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,             -- ISO 8601 timestamp
    task_id TEXT NOT NULL,               -- Links to tasks.task_id
    status TEXT NOT NULL,                -- Status identifier
    message TEXT,                        -- Human-readable message
    metadata TEXT                        -- JSON blob with extra data
);

-- Indices for performance
CREATE INDEX idx_status_timestamp ON agent_status(timestamp DESC);
CREATE INDEX idx_status_task ON agent_status(task_id);
```

##### Files Table (`database.py:314-327`)

File access tracking for codebase analytics.

```sql
CREATE TABLE files (
    file_path TEXT PRIMARY KEY,          -- Absolute path
    first_seen TEXT NOT NULL,            -- ISO 8601 timestamp
    last_accessed TEXT NOT NULL,         -- ISO 8601 timestamp
    access_count INTEGER NOT NULL DEFAULT 0,
    task_ids TEXT,                       -- JSON array of task_ids
    operations TEXT,                     -- JSON object: {read: N, write: N, edit: N}
    file_size INTEGER,                   -- Bytes
    file_hash TEXT                       -- SHA256 or similar
);

-- Indices for performance
CREATE INDEX idx_files_last_accessed ON files(last_accessed DESC);
CREATE INDEX idx_files_access_count ON files(access_count DESC);
```

##### Games Table (`database.py:211-223`)

Game state persistence for Pacman and future games.

```sql
CREATE TABLE games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,            -- Telegram user ID
    game_type TEXT NOT NULL,             -- 'pacman'
    status TEXT NOT NULL,                -- active/completed
    score INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,            -- ISO 8601 timestamp
    updated_at TEXT NOT NULL,            -- ISO 8601 timestamp
    state_data TEXT                      -- JSON blob with game state
);

-- Indices for performance
CREATE INDEX idx_games_user_status ON games(user_id, status, updated_at DESC);
CREATE INDEX idx_games_user_type ON games(user_id, game_type);
```

##### Users Table (`database.py:350-361`)

Web chat authentication (future feature).

```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,            -- UUID
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,         -- bcrypt hash
    created_at TEXT NOT NULL,            -- ISO 8601 timestamp
    is_admin BOOLEAN NOT NULL DEFAULT 0
);

-- Indices for performance
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

#### Task Operations

##### Create Task (`database.py:421-463`)

```python
async def create_task(
    self,
    task_id: str,
    user_id: int,
    description: str,
    workspace: str,
    model: str = "sonnet",
    agent_type: str = "code_agent",
    workflow: str | None = None,
    context: str | None = None,
) -> dict:
    """Create a new task"""
```

**Returns**: Task dictionary with all fields including empty `activity_log: []`

**Example**:
```python
task = await db.create_task(
    task_id="abc123",
    user_id=123456,
    description="Fix bug in main.py",
    workspace="/Users/user/project",
    model="sonnet",
    agent_type="code_agent",
    workflow="code-task"
)
# Returns: {'task_id': 'abc123', 'status': 'pending', ...}
```

##### Get Task (`database.py:465-474`)

```python
def get_task(self, task_id: str) -> dict | None:
    """Get task by ID"""
```

**Example**:
```python
task = db.get_task("abc123")
if task:
    print(f"Status: {task['status']}")
```

##### Update Task (`database.py:476-523`)

```python
async def update_task(
    self,
    task_id: str,
    status: str | None = None,
    result: str | None = None,
    error: str | None = None,
    pid: int | None = None,
    workflow: str | None = None,
    session_uuid: str | None = None,
) -> bool:
    """Update task fields"""
```

**Example**:
```python
await db.update_task("abc123", status="running", pid=12345)
```

##### Add Activity (`database.py:525-557`)

```python
async def add_activity(
    self, task_id: str, message: str, output_lines: int | None = None
) -> bool:
    """Add activity entry to task log"""
```

**Example**:
```python
await db.add_activity("abc123", "Started code generation", output_lines=50)
```

##### Query Tasks (`database.py:559-641`)

```python
def get_user_tasks(self, user_id: int, status: str | None = None, limit: int = 10) -> list[dict]:
    """Get tasks for a user"""

def get_active_tasks(self, user_id: int) -> list[dict]:
    """Get active (pending/running) tasks for user"""

def get_failed_tasks(self, user_id: int, limit: int = 10) -> list[dict]:
    """Get failed tasks for a user"""

def get_stopped_tasks(self, user_id: int | None = None, limit: int = 100) -> list[dict]:
    """Get stopped tasks, optionally filtered by user"""

def get_interrupted_tasks(self) -> list[dict]:
    """Get tasks interrupted by bot restart or shutdown"""
```

**Example**:
```python
# Get all active tasks
active = db.get_active_tasks(user_id=123456)

# Get recent failed tasks
failed = db.get_failed_tasks(user_id=123456, limit=5)

# Get tasks interrupted by restart
interrupted = db.get_interrupted_tasks()
```

##### Cleanup Operations (`database.py:669-766`)

```python
def delete_task(self, task_id: str) -> bool:
    """Delete a task"""

def clear_old_failed_tasks(self, user_id: int, older_than_hours: int = 24) -> int:
    """Clear old failed tasks for a user"""

def cleanup_stale_pending_tasks(self, max_age_hours: int = 1) -> int:
    """Mark stale pending tasks as failed"""

def mark_all_running_as_stopped(self) -> int:
    """Mark all running tasks as stopped during shutdown"""
```

**Example**:
```python
# Mark all running tasks as stopped during shutdown
stopped_count = db.mark_all_running_as_stopped()
print(f"Marked {stopped_count} tasks as stopped")
```

##### Statistics (`database.py:768-801`)

```python
def get_task_statistics(self) -> dict:
    """Get task statistics"""
```

**Returns**:
```python
{
    "total": 150,
    "by_status": {"completed": 120, "failed": 20, "running": 5, "pending": 5},
    "recent_24h": 30,
    "success_rate": 85.7  # percentage
}
```

#### Tool Usage Operations

##### Record Tool Usage (`database.py:805-846`)

```python
def record_tool_usage(
    self,
    task_id: str,
    tool_name: str,
    duration_ms: float | None = None,
    success: bool | None = None,
    error: str | None = None,
    parameters: dict | None = None,
    error_category: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
    cache_read_tokens: int | None = None,
):
    """Record tool usage with optional token tracking"""
```

**Example**:
```python
db.record_tool_usage(
    task_id="abc123",
    tool_name="Read",
    duration_ms=123.45,
    success=True,
    parameters={"file_path": "/path/to/file.py"},
    input_tokens=1000,
    output_tokens=500
)
```

##### Query Tool Usage (`database.py:848-924`)

```python
def get_tool_statistics(self, task_id: str | None = None, hours: int = 24) -> dict[str, Any]:
    """Get tool usage statistics"""
```

**Returns**:
```python
{
    "total_calls": 150,
    "time_window_hours": 24,
    "tools": {
        "Read": {
            "count": 50,
            "successes": 48,
            "failures": 2,
            "total_duration_ms": 5000.0,
            "min_duration_ms": 10.0,
            "max_duration_ms": 500.0,
            "avg_duration_ms": 100.0,
            "success_rate": 0.96
        },
        # ... other tools
    }
}
```

##### Task Timeline (`database.py:926-977`)

```python
def get_task_timeline(self, task_id: str) -> list[dict]:
    """Get complete timeline of events for a task"""
```

**Returns**: Combined list of tool usage and status changes, sorted by timestamp.

**Example**:
```python
timeline = db.get_task_timeline("abc123")
for event in timeline:
    if event["type"] == "tool_usage":
        print(f"{event['timestamp']}: {event['tool_name']} - {event['success']}")
    elif event["type"] == "status_change":
        print(f"{event['timestamp']}: Status → {event['status']}")
```

##### Tool Usage by Session (`database.py:979-1012`)

```python
def get_tool_usage_by_session(self, session_id: str) -> list[dict]:
    """Get tool usage records for a specific session/task"""
```

**Example**:
```python
usage = db.get_tool_usage_by_session("abc123")
for record in usage:
    print(f"{record['tool']}: {record['duration']}ms")
```

#### File Indexing Operations

##### Record File Access (`database.py:1127-1201`)

```python
async def record_file_access(
    self,
    file_path: str,
    task_id: str,
    operation: str,  # 'read', 'write', 'edit'
    file_size: int | None = None,
    file_hash: str | None = None
):
    """Record file access in the files index"""
```

**Example**:
```python
await db.record_file_access(
    file_path="/path/to/file.py",
    task_id="abc123",
    operation="read",
    file_size=1234
)
```

##### Query File Info (`database.py:1203-1303`)

```python
def get_file_info(self, file_path: str) -> dict | None:
    """Get file metadata from index"""

def get_frequently_accessed_files(self, limit: int = 50) -> list[dict]:
    """Get most frequently accessed files"""

def get_task_files(self, task_id: str) -> list[dict]:
    """Get all files accessed by a task"""
```

**Example**:
```python
# Get info for specific file
info = db.get_file_info("/path/to/main.py")
print(f"Accessed {info['access_count']} times by {len(info['task_ids'])} tasks")

# Get most accessed files
top_files = db.get_frequently_accessed_files(limit=10)
```

#### User Management Operations

##### User CRUD (`database.py:1376-1582`)

```python
def create_user(self, user_id: str, username: str, email: str, password_hash: str, is_admin: bool = False) -> bool:
    """Create a new user"""

def get_user_by_username(self, username: str) -> dict | None:
    """Get user by username"""

def get_user_by_id(self, user_id: str) -> dict | None:
    """Get user by user_id"""

def get_user_by_email(self, email: str) -> dict | None:
    """Get user by email"""

def update_user(self, user_id: str, **kwargs) -> bool:
    """Update user fields"""

def delete_user(self, user_id: str) -> bool:
    """Delete a user"""

def get_all_users(self, limit: int = 100) -> list[dict]:
    """Get all users"""
```

#### Utility Methods

##### Database Statistics (`database.py:1606-1637`)

```python
def get_database_stats(self) -> dict:
    """Get database statistics"""
```

**Returns**:
```python
{
    "tasks": 150,
    "tool_usage_records": 5000,
    "agent_status_records": 300,
    "database_size_bytes": 5242880,
    "database_size_kb": 5120.0
}
```

##### Maintenance (`database.py:1634-1642`)

```python
def vacuum(self):
    """Vacuum database to reclaim space"""

def close(self):
    """Close database connection"""
```

---

## Manager Classes Overview

| Manager | Purpose | Shared State | Location |
|---------|---------|--------------|----------|
| **SessionManager** | User conversation history | `sessions: dict[int, Session]` | `session.py:51` |
| **TaskManager** | Background task tracking | `db: Database` | `tasks.py:227` |
| **MessageQueueManager** | Per-user message serialization | `user_queues: dict[int, UserMessageQueue]` | `message_queue.py:138` |
| **AgentPool** | Bounded worker pool | `task_queue: PriorityQueue`, `agents: list[Task]` | `agent_pool.py:37` |
| **ClaudeSessionPool** | Claude Code session pooling | `active_sessions: dict[str, ClaudeInteractiveSession]` | `claude_interactive.py:474` |
| **GameManager** | Game state management | `active_games: dict[int, PacmanGame]`, `db: Database` | `game_manager.py:13` |
| **LogMonitorManager** | Background log monitoring | `monitor: LogMonitorTask` | `log_monitor.py:157` |
| **UserConfirmationManager** | User confirmation tracking | `pending_confirmations: dict[str, dict]` | `log_claude_escalation.py:169` |
| **WorktreeManager** | Git worktree management (DEPRECATED) | `active_worktrees: dict[str, Path]` | `worktree_manager.py:60` |

**Shared Database Instance**: Most managers share a single `Database` instance passed during initialization to avoid connection overhead and ensure data consistency.

---

## Manager Classes Detail

### SessionManager (`session.py:51`)

Manages user conversation history with persistent storage.

#### Initialization

```python
def __init__(self, data_dir: str = "data"):
    """Initialize SessionManager with persistent storage"""
```

**State**:
- `sessions: dict[int, Session]` - In-memory session cache
- `sessions_file: Path` - Persistent storage (`data/sessions.json`)

**Lifecycle**:
1. Load existing sessions from disk on startup
2. Auto-save to disk on every modification
3. No timeout - sessions persist indefinitely

#### Session Data Structure

```python
@dataclass
class Session:
    user_id: int
    created_at: str              # ISO 8601
    last_activity: str           # ISO 8601
    history: list[Message]       # Conversation messages
    current_workspace: str | None  # Active repository
```

```python
@dataclass
class Message:
    role: str                    # 'user' or 'assistant'
    content: str
    timestamp: str               # ISO 8601
```

#### API Methods

##### Get or Create Session (`session.py:97`)

```python
def get_or_create_session(self, user_id: int) -> Session:
    """Get existing session or create new one"""
```

**Behavior**:
- Returns existing session if found
- Creates new session if not found
- Updates `last_activity` timestamp
- Auto-saves to disk

**Example**:
```python
session = session_manager.get_or_create_session(user_id=123456)
print(f"Session has {len(session.history)} messages")
```

##### Add Message (`session.py:115`)

```python
def add_message(self, user_id: int, role: str, content: str):
    """Add message to session history"""
```

**Example**:
```python
session_manager.add_message(123456, "user", "Hello, Claude!")
session_manager.add_message(123456, "assistant", "Hello! How can I help?")
```

##### Get History (`session.py:127`)

```python
def get_history(self, user_id: int, limit: int | None = None) -> list[Message]:
    """Get conversation history for user"""
```

**Example**:
```python
# Get last 5 messages
recent = session_manager.get_history(123456, limit=5)
for msg in recent:
    print(f"{msg.role}: {msg.content[:50]}")
```

##### Clear Session (`session.py:135`)

```python
def clear_session(self, user_id: int):
    """Clear session history"""
```

**Behavior**:
- Clears `history` list
- Preserves session metadata
- Updates `last_activity`

##### Workspace Management (`session.py:178-188`)

```python
def set_workspace(self, user_id: int, workspace: str):
    """Set current workspace for user session"""

def get_workspace(self, user_id: int) -> str | None:
    """Get current workspace for user session"""
```

**Example**:
```python
session_manager.set_workspace(123456, "/Users/user/project")
workspace = session_manager.get_workspace(123456)
```

##### Statistics (`session.py:156`)

```python
def get_session_stats(self, user_id: int) -> dict:
    """Get statistics about a session"""
```

**Returns**:
```python
{
    "exists": True,
    "message_count": 42,
    "created_at": "2025-01-15T10:30:00",
    "last_activity": "2025-01-15T14:30:00",
    "user_messages": 21,
    "assistant_messages": 21,
    "current_workspace": "/Users/user/project"
}
```

---

### TaskManager (`tasks.py:227`)

Manages background task lifecycle using SQLite backend.

#### Initialization

```python
def __init__(self, db: Database = None, data_dir: str = "data"):
    """Initialize TaskManager with shared Database"""
```

**Recommended Usage**:
```python
db = Database()  # Centralized instance
task_manager = TaskManager(db=db)
```

#### Task Data Structure

```python
@dataclass
class Task:
    task_id: str                 # 6-char UUID prefix
    user_id: int
    description: str
    status: str                  # pending/running/completed/failed/stopped
    created_at: str              # ISO 8601
    updated_at: str              # ISO 8601
    model: str                   # haiku/sonnet/opus
    workspace: str               # Repository path
    agent_type: str = "code_agent"  # Agent type
    workflow: str | None = None  # Workflow name
    context: str | None = None   # Context from Claude API
    result: str | None = None
    error: str | None = None
    pid: int | None = None       # Claude Code process ID
    activity_log: list[dict] | None = None  # Activity entries
```

#### API Methods

##### Create Task (`tasks.py:294`)

```python
async def create_task(
    self,
    user_id: int,
    description: str,
    workspace: str,
    model: str = "sonnet",
    agent_type: str = "code_agent",
    workflow: str | None = None,
    context: str | None = None,
) -> Task:
    """Create a new task"""
```

**Example**:
```python
task = await task_manager.create_task(
    user_id=123456,
    description="Fix bug in main.py",
    workspace="/Users/user/project",
    model="sonnet",
    agent_type="code_agent",
    workflow="code-task"
)
print(f"Created task {task.task_id}")
```

##### Update Task (`tasks.py:322`)

```python
async def update_task(
    self,
    task_id: str,
    status: str | None = None,
    result: str | None = None,
    error: str | None = None,
    pid: int | None = None,
    workflow: str | None = None,
):
    """Update task status"""
```

##### Log Activity (`tasks.py:347`)

```python
async def log_activity(
    self, task_id: str, message: str, output_lines: int | None = None, save: bool = True
):
    """Log activity for a task"""
```

##### Query Tasks (`tasks.py:357-442`)

```python
def get_task(self, task_id: str) -> Task | None:
    """Get task by ID"""

def get_user_tasks(self, user_id: int, status: str | None = None, limit: int = 10) -> list[Task]:
    """Get tasks for a user"""

def get_active_tasks(self, user_id: int) -> list[Task]:
    """Get active (pending/running) tasks for user"""

def get_failed_tasks(self, user_id: int, limit: int = 10) -> list[Task]:
    """Get failed tasks for a user"""

def get_stopped_tasks(self, user_id: int | None = None, limit: int = 100) -> list[Task]:
    """Get stopped tasks, optionally filtered by user"""
```

##### Task Control (`tasks.py:458-552`)

```python
async def stop_task(self, task_id: str) -> tuple[bool, str]:
    """Stop a running task by killing its process"""

async def stop_all_tasks(self, user_id: int) -> tuple[int, int, list[str]]:
    """Stop all active tasks for a user"""

def retry_task(self, task_id: str) -> Task | None:
    """Retry a failed or stopped task by creating a new task"""
```

**Example**:
```python
# Stop a task
success, message = await task_manager.stop_task("abc123")
print(message)

# Stop all user tasks
stopped, failed, failed_ids = await task_manager.stop_all_tasks(123456)
print(f"Stopped {stopped} tasks, {failed} failed")
```

##### Cleanup (`tasks.py:404-456`)

```python
def clear_old_failed_tasks(self, user_id: int, older_than_hours: int = 24) -> int:
    """Clear old failed tasks for a user"""

def cleanup_stale_pending_tasks(self, max_age_hours: int = 1) -> int:
    """Clean up stale pending tasks"""

def mark_all_running_as_stopped(self) -> int:
    """Mark all running tasks as stopped during shutdown"""
```

##### Startup Recovery (`tasks.py:253`)

```python
async def check_running_tasks(self):
    """Check running tasks on startup - mark as stopped if process died"""
```

**Behavior**:
- Queries all tasks with `status='running'`
- Checks if process is alive using `os.kill(pid, 0)`
- Marks dead processes as `stopped`
- Adds activity log entries for tracking

**Must call manually from async context**:
```python
task_manager = TaskManager(db=db)
await task_manager.check_running_tasks()
```

---

### MessageQueueManager (`message_queue.py:138`)

Ensures sequential message processing per user to prevent race conditions.

#### Initialization

```python
def __init__(self):
    """Initialize message queue manager"""
```

**State**:
- `user_queues: dict[int, UserMessageQueue]` - Per-user queues
- `_lock: asyncio.Lock` - Thread-safe queue creation

#### Queue Architecture

```
User 123 → UserMessageQueue → [Msg1, Msg2, Msg3] → Process sequentially
User 456 → UserMessageQueue → [Msg4, Msg5]        → Process sequentially
                                ↓
                        Parallel execution across users
```

#### API Methods

##### Enqueue Message (`message_queue.py:145`)

```python
async def enqueue_message(
    self,
    user_id: int,
    update: Any,               # Telegram Update
    context: Any,              # Telegram Context
    handler: Callable,         # Handler function
    handler_name: str = "unknown",
    priority: int = 0,         # 0=normal, 1+=priority
) -> None:
    """Queue a message for a user"""
```

**Priority Levels**:
- `0`: Normal messages (text, voice, documents)
- `1+`: Priority commands (`/restart`, `/start`, `/clear`)

**Example**:
```python
# Normal message
await message_queue.enqueue_message(
    user_id=123456,
    update=update,
    context=context,
    handler=handle_message,
    handler_name="handle_message",
    priority=0
)

# Priority command
await message_queue.enqueue_message(
    user_id=123456,
    update=update,
    context=context,
    handler=handle_restart,
    handler_name="restart",
    priority=1
)
```

##### Status (`message_queue.py:196-207`)

```python
def get_status(self) -> dict:
    """Get status of all queues"""

async def get_user_status(self, user_id: int) -> dict | None:
    """Get status for specific user"""
```

**Returns**:
```python
{
    "active_users": 3,
    "queues": {
        "123456": {
            "user_id": 123456,
            "processing": True,
            "queue_size": 2,
            "messages_processed": 15,
            "current_message": "handle_message"
        }
    }
}
```

##### Cleanup (`message_queue.py:183-194`)

```python
async def cleanup_user(self, user_id: int) -> None:
    """Stop and remove queue for a user"""

async def cleanup_all(self) -> None:
    """Stop and remove all queues"""
```

---

### AgentPool (`agent_pool.py:37`)

Bounded worker pool for background task execution with priority support.

#### Initialization

```python
def __init__(self, max_agents: int = 3):
    """Initialize agent pool"""
```

**Configuration**:
- Default: 3 concurrent agents
- Priority queue with 4 levels (URGENT/HIGH/NORMAL/LOW)
- FIFO ordering within same priority

#### Priority Levels

```python
class TaskPriority(IntEnum):
    URGENT = 0    # User-facing errors, critical failures
    HIGH = 1      # User requests, interactive tasks
    NORMAL = 2    # Background tasks, routine operations (default)
    LOW = 3       # Maintenance, cleanup, analytics
```

#### API Methods

##### Lifecycle (`agent_pool.py:61-96`)

```python
async def start(self) -> None:
    """Start the agent pool by spawning agent coroutines"""

async def stop(self) -> None:
    """Stop the agent pool gracefully"""
```

**Example**:
```python
pool = AgentPool(max_agents=3)
await pool.start()

# ... use pool ...

await pool.stop()  # Graceful shutdown
```

##### Submit Task (`agent_pool.py:98`)

```python
async def submit(
    self,
    task_func: Callable,
    *args: Any,
    priority: TaskPriority = TaskPriority.NORMAL,
    **kwargs: Any
) -> None:
    """Submit a task for execution"""
```

**Non-blocking**: Returns immediately after queueing.

**Example**:
```python
from agent_pool import TaskPriority

# Submit normal priority task
await pool.submit(
    execute_task,
    task_id="abc123",
    description="Fix bug",
    priority=TaskPriority.NORMAL
)

# Submit urgent task (jumps queue)
await pool.submit(
    handle_critical_error,
    error_id="err123",
    priority=TaskPriority.URGENT
)
```

##### Status (`agent_pool.py:187-205`)

```python
@property
def active_agent_count(self) -> int:
    """Get count of currently active tasks"""

@property
def queue_size(self) -> int:
    """Get number of tasks waiting in queue"""

def get_status(self) -> dict:
    """Get pool status for monitoring"""
```

**Returns**:
```python
{
    "max_agents": 3,
    "started": True,
    "active_tasks": 2,
    "queued_tasks": 5,
    "total_agents": 3
}
```

---

### ClaudeSessionPool (`claude_interactive.py:474`)

Pool of Claude Code sessions for concurrent task execution.

#### Initialization

```python
def __init__(
    self,
    max_concurrent: int = 3,
    enforce_workflow: bool = True,
    usage_tracker: ToolUsageTracker | None = None,
):
    """Initialize session pool"""
```

**State**:
- `active_sessions: dict[str, ClaudeInteractiveSession]` - Task ID → Session mapping
- `usage_tracker: ToolUsageTracker` - Optional tool usage tracking

#### API Methods

##### Execute Task (`claude_interactive.py:494`)

```python
async def execute_task(
    self,
    task_id: str,
    description: str,
    workspace: Path,
    bot_repo_path: str | None = None,
    model: str = "sonnet",
    context: str | None = None,
    pid_callback: Callable[[int], None] | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> tuple[bool, str, int | None, str | None]:
    """Execute a task using session pool"""
```

**Returns**: `(success, result, pid, workflow)`

**Behavior**:
1. Waits if at max capacity (simple polling, 1s interval)
2. Creates Claude session with workflow enforcement disabled (workflows orchestrate)
3. Starts session and gets PID
4. Calls `pid_callback(pid)` immediately when process starts
5. Uses workflow router to select appropriate workflow
6. Adds context from Claude API to task description
7. Invokes workflow slash command (e.g., `/workflows:code-task`)
8. Streams output and calls `progress_callback(status, elapsed)` periodically
9. Returns result and workflow used

**Example**:
```python
def on_pid(pid: int):
    print(f"Process started: {pid}")

def on_progress(status: str, elapsed: int):
    print(f"{elapsed}s: {status}")

success, result, pid, workflow = await session_pool.execute_task(
    task_id="abc123",
    description="Fix bug in main.py",
    workspace=Path("/Users/user/project"),
    model="sonnet",
    context="User reported crash on startup",
    pid_callback=on_pid,
    progress_callback=on_progress
)

print(f"Task completed: {success}, workflow: {workflow}")
```

---

### GameManager (`game_manager.py:13`)

Manages active game sessions with database persistence.

#### Initialization

```python
def __init__(self, db: Database):
    """Initialize game manager with shared Database"""
```

**State**:
- `active_games: dict[int, PacmanGame]` - User ID → Game instance
- `db: Database` - Shared database for persistence

**Lifecycle**:
- Loads active games from database on startup
- Auto-saves game state on updates

#### API Methods

##### Start Game (`game_manager.py:48`)

```python
def start_game(self, user_id: int, game_type: str = "pacman") -> PacmanGame:
    """Start a new game for user"""
```

**Example**:
```python
game = game_manager.start_game(user_id=123456)
print(f"Game started at level {game.state.level}")
```

##### Get Active Game (`game_manager.py:79`)

```python
def get_active_game(self, user_id: int) -> PacmanGame | None:
    """Get active game for user"""

def has_active_game(self, user_id: int) -> bool:
    """Check if user has an active game"""
```

##### Update Game (`game_manager.py:101`)

```python
def update_game(self, user_id: int):
    """Update game state in database"""
```

**Call after game state changes** (movement, scoring, etc.)

##### End Game (`game_manager.py:113`)

```python
def end_game(self, user_id: int) -> dict[str, Any] | None:
    """End active game for user"""
```

**Returns**:
```python
{
    "score": 1234,
    "level": 5,
    "game_type": "pacman"
}
```

##### Statistics (`game_manager.py:182-214`)

```python
def get_user_stats(self, user_id: int) -> dict[str, Any]:
    """Get game statistics for user"""

def get_leaderboard(self, limit: int = 10) -> list:
    """Get top scores leaderboard"""
```

---

### LogMonitorManager (`log_monitor.py:157`)

Background log monitoring with error detection and escalation.

#### Initialization

```python
def __init__(self, config: MonitoringConfig):
    """Initialize log monitor manager"""
```

**MonitoringConfig**:
```python
@dataclass
class MonitoringConfig:
    log_file: str = "logs/bot.log"
    check_interval: int = 300        # 5 minutes
    error_threshold: int = 5         # Errors before notification
    warning_threshold: int = 10      # Warnings before notification
    escalation_threshold: int = 3    # Critical errors before Claude escalation
```

#### API Methods

##### Lifecycle (`log_monitor.py:166-180`)

```python
async def start(self, notification_callback: Callable):
    """Start monitoring"""

async def stop(self):
    """Stop monitoring"""

def is_running(self) -> bool:
    """Check if monitor is running"""
```

**Example**:
```python
async def notify_user(message: str):
    await bot.send_message(chat_id=123456, text=message)

config = MonitoringConfig(check_interval=300)
monitor = LogMonitorManager(config)
await monitor.start(notification_callback=notify_user)
```

##### Manual Operations (`log_monitor.py:186-201`)

```python
async def manual_check(self) -> dict:
    """Manually trigger a check"""

def get_stats(self) -> dict:
    """Get current monitoring stats"""

def get_escalation_queue(self) -> list[LogIssue]:
    """Get issues queued for Claude analysis"""

def clear_escalation_queue(self):
    """Clear escalation queue"""
```

---

### UserConfirmationManager (`log_claude_escalation.py:169`)

Tracks user confirmations for suggested fixes from Claude analysis.

#### Initialization

```python
def __init__(self):
    """Initialize confirmation manager"""
```

**State**:
- `pending_confirmations: dict[str, dict]` - Confirmation ID → Request
- `confirmed_actions: list[dict]` - History of confirmed actions
- `rejected_actions: list[dict]` - History of rejected actions

#### API Methods

##### Create Confirmation (`log_claude_escalation.py:177`)

```python
def create_confirmation_request(
    self, issue: LogIssue, suggested_action: str, confidence: float = 0.8
) -> str:
    """Create a confirmation request for a suggested fix"""
```

**Returns**: Confirmation ID (format: `{issue_type}_{timestamp}`)

##### User Actions (`log_claude_escalation.py:195-225`)

```python
def confirm_action(self, confirmation_id: str, user_notes: str | None = None) -> bool:
    """User confirms to apply the suggested fix"""

def reject_action(self, confirmation_id: str, reason: str | None = None) -> bool:
    """User rejects the suggested fix"""
```

##### Query (`log_claude_escalation.py:227-243`)

```python
def get_pending_confirmations(self) -> list[dict]:
    """Get all pending confirmation requests"""

def get_confirmation_status(self, confirmation_id: str) -> dict | None:
    """Get status of a specific confirmation"""

def get_action_history(self) -> dict:
    """Get history of user actions"""
```

**Returns**:
```python
{
    "confirmed": [...],  # List of confirmed actions
    "rejected": [...],   # List of rejected actions
    "pending": [...]     # List of pending confirmations
}
```

---

### WorktreeManager (`worktree_manager.py:60`) - DEPRECATED

**STATUS**: Deprecated as of 2025-10-22. Worktree management now handled explicitly by `git-worktree` agent within workflows.

**Original Purpose**: Managed git worktrees for concurrent task execution in isolated branches.

**Why Deprecated**:
- Workflows now explicitly control worktree lifecycle via `git-worktree` agent
- Provides better visibility and control over branch management
- Prevents automatic cleanup that could lose debugging context

**Migration**: Use `git-worktree` agent commands in workflows:
- `/git-worktree create-worktree` - Create isolated worktree
- `/git-merge` - Merge branch to main
- `/git-worktree cleanup-worktree` - Manual cleanup (only when requested)

---

## Key Data Flows

### Message Routing Flow

User message → Telegram bot → flow branches:

#### 1. Text/Voice Message

```
User sends message
    ↓
MessageQueueManager.enqueue_message()
    ↓ (serialized per user)
handle_message()
    ↓
ask_claude() [Claude API - Haiku]
    ↓ (routing decision)
    ├─→ DIRECT RESPONSE (question/chat)
    │   └─→ Send to user
    └─→ BACKGROUND_TASK format (coding work)
        ↓
        parse task_description & user_message
        ↓
        TaskManager.create_task()
        ↓
        AgentPool.submit(execute_task, priority=HIGH)
        ↓ (queued, returns immediately)
        Send "user_message" to user
```

#### 2. Background Task Execution

```
AgentPool agent picks up task
    ↓
execute_background_task()
    ↓
TaskManager.update_task(status="running", pid=...)
    ↓
ClaudeSessionPool.execute_task()
    ├─→ Workflow Router selects workflow
    ├─→ Create ClaudeInteractiveSession
    ├─→ Start Claude Code process
    ├─→ Call pid_callback(pid)
    └─→ Invoke workflow slash command (e.g., /workflows:code-task)
        ↓
        Workflow executes (may spawn sub-agents)
        ↓ (streams output)
        Call progress_callback(status, elapsed)
        ↓
        Return result
    ↓
TaskManager.update_task(status="completed", result=...)
    ↓
Send result to user
```

### Tool Usage Tracking Flow

```
Claude Code session starts
    ↓
Pre-tool-use hook fires
    ↓
~/.claude/hooks/pre-tool-use
    ↓
Log to logs/sessions/{session_uuid}/pre_tool_use.jsonl
    ↓
Tool executes (Read/Write/Edit/Bash/Grep/Glob)
    ↓
Post-tool-use hook fires
    ↓
~/.claude/hooks/post-tool-use
    ↓
Call record_tool_usage.py
    ↓
Database.record_tool_usage()
    ├─→ Insert into tool_usage table
    │   └─→ tool_name, duration_ms, success, error, parameters, tokens
    └─→ Optional: Database.record_file_access() for Read/Write/Edit
        └─→ Update files table for codebase analytics
    ↓
Log to logs/sessions/{session_uuid}/post_tool_use.jsonl
```

### Session End Flow

```
Claude Code session ends
    ↓
Session-end hook fires
    ↓
~/.claude/hooks/session-end
    ↓
Aggregate session data
    ├─→ Read pre_tool_use.jsonl
    ├─→ Read post_tool_use.jsonl
    └─→ Generate summary.json
        ├─→ Total tools used
        ├─→ Success rate
        ├─→ Duration
        └─→ Token usage
    ↓
Write to logs/sessions/{session_uuid}/summary.json
```

### Error Detection & Escalation Flow

```
LogMonitorManager runs every 5 minutes
    ↓
LogAnalyzer.analyze_logs()
    ├─→ Read logs/bot.log (last N lines)
    ├─→ Parse ERROR, WARNING, CRITICAL patterns
    └─→ Categorize issues (DatabaseError, APIError, etc.)
    ↓
Check thresholds
    ├─→ error_count > error_threshold
    └─→ critical_count > escalation_threshold
    ↓
notification_callback(summary_message)
    ↓
Send to user via Telegram
    ↓
If critical_count > escalation_threshold:
    LogClaudeEscalation.analyze_and_suggest()
        ↓
        Claude API analyzes logs + issue
        ↓
        Returns suggested fix
        ↓
        UserConfirmationManager.create_confirmation_request()
        ↓
        Send confirmation request to user
        ↓
        User confirms/rejects via callback
```

### Shutdown & Recovery Flow

```
Bot shutdown signal (SIGTERM/SIGINT)
    ↓
graceful_shutdown()
    ├─→ TaskManager.mark_all_running_as_stopped()
    │   └─→ Update tasks: status='stopped', error='Task stopped during bot shutdown'
    ├─→ MessageQueueManager.cleanup_all()
    ├─→ AgentPool.stop()
    ├─→ LogMonitorManager.stop()
    └─→ Database.close()
    ↓
PIDFileLock.release()
    └─→ Remove data/bot.pid
    ↓
Exit
```

```
Bot startup
    ↓
PIDFileLock.acquire()
    ├─→ Check for existing PID
    └─→ Write new PID
    ↓
Initialize managers (shared Database instance)
    ├─→ Database()
    ├─→ TaskManager(db)
    ├─→ SessionManager()
    ├─→ MessageQueueManager()
    ├─→ AgentPool()
    └─→ GameManager(db)
    ↓
TaskManager.check_running_tasks()
    ├─→ Query tasks with status='running'
    ├─→ Check if PID still alive (os.kill(pid, 0))
    └─→ Mark dead tasks as 'stopped'
    ↓
Database.get_interrupted_tasks()
    ├─→ Query tasks with error='Task stopped during bot shutdown'
    └─→ Group by user_id
    ↓
Send recovery notification to each user
    └─→ "I restarted and found N interrupted tasks. Use /retry to resume them."
```

---

## API Examples

### Example 1: Create and Track Background Task

```python
from database import Database
from tasks import TaskManager
from agent_pool import AgentPool, TaskPriority
from claude_interactive import ClaudeSessionPool

# Initialize shared instances
db = Database()
task_manager = TaskManager(db=db)
agent_pool = AgentPool(max_agents=3)
session_pool = ClaudeSessionPool(max_concurrent=3)

# Start agent pool
await agent_pool.start()

# Create task
task = await task_manager.create_task(
    user_id=123456,
    description="Fix critical bug in auth.py",
    workspace="/Users/user/project",
    model="sonnet",
    agent_type="code_agent",
    workflow="code-task",
    context="User reported 500 error on login"
)

print(f"Created task {task.task_id}")

# Submit to agent pool
async def execute_task():
    # Update status to running
    await task_manager.update_task(task.task_id, status="running")

    # Execute via session pool
    success, result, pid, workflow = await session_pool.execute_task(
        task_id=task.task_id,
        description=task.description,
        workspace=Path(task.workspace),
        model=task.model,
        context=task.context,
        pid_callback=lambda p: task_manager.update_task(task.task_id, pid=p),
        progress_callback=lambda s, e: task_manager.log_activity(task.task_id, s)
    )

    # Update final status
    if success:
        await task_manager.update_task(task.task_id, status="completed", result=result, workflow=workflow)
    else:
        await task_manager.update_task(task.task_id, status="failed", error=result)

await agent_pool.submit(execute_task, priority=TaskPriority.HIGH)

# Query task status
task = task_manager.get_task(task.task_id)
print(f"Status: {task.status}")
```

### Example 2: Query Tool Usage Statistics

```python
from database import Database

db = Database()

# Get tool stats for last 24 hours
stats = db.get_tool_statistics(hours=24)
print(f"Total tool calls: {stats['total_calls']}")

for tool_name, tool_stats in stats['tools'].items():
    print(f"\n{tool_name}:")
    print(f"  Calls: {tool_stats['count']}")
    print(f"  Success rate: {tool_stats['success_rate']:.1%}")
    print(f"  Avg duration: {tool_stats['avg_duration_ms']:.1f}ms")

# Get tool usage for specific task
task_stats = db.get_tool_statistics(task_id="abc123")
print(f"\nTask abc123 used {task_stats['total_calls']} tools")

# Get complete timeline
timeline = db.get_task_timeline("abc123")
for event in timeline:
    if event['type'] == 'tool_usage':
        status = "✓" if event['success'] else "✗"
        print(f"{event['timestamp']}: {status} {event['tool_name']}")
```

### Example 3: Session Management

```python
from session import SessionManager

session_manager = SessionManager(data_dir="data")

# Add conversation
session_manager.add_message(123456, "user", "How do I fix this bug?")
session_manager.add_message(123456, "assistant", "Let me analyze the code...")

# Get recent history
history = session_manager.get_history(123456, limit=5)
for msg in history:
    print(f"{msg.role}: {msg.content[:60]}")

# Get stats
stats = session_manager.get_session_stats(123456)
print(f"Session has {stats['message_count']} messages")
print(f"Last activity: {stats['last_activity']}")

# Clear when requested
session_manager.clear_session(123456)
```

### Example 4: Message Queue Priority

```python
from message_queue import MessageQueueManager

queue_manager = MessageQueueManager()

# Enqueue normal message
await queue_manager.enqueue_message(
    user_id=123456,
    update=update,
    context=context,
    handler=handle_message,
    handler_name="message",
    priority=0
)

# Enqueue urgent restart command (jumps queue)
await queue_manager.enqueue_message(
    user_id=123456,
    update=restart_update,
    context=context,
    handler=handle_restart,
    handler_name="restart",
    priority=1
)

# Check status
status = await queue_manager.get_user_status(123456)
print(f"Queue size: {status['queue_size']}")
print(f"Processing: {status['current_message']}")
```

### Example 5: File Access Analytics

```python
from database import Database

db = Database()

# Record file access
await db.record_file_access(
    file_path="/Users/user/project/main.py",
    task_id="abc123",
    operation="edit",
    file_size=5432
)

# Get most accessed files
top_files = db.get_frequently_accessed_files(limit=10)
for file in top_files:
    print(f"{file['file_path']}: {file['access_count']} accesses")
    print(f"  Operations: {file['operations']}")
    print(f"  Tasks: {len(file['task_ids'])}")

# Get files for specific task
task_files = db.get_task_files("abc123")
print(f"\nTask abc123 accessed {len(task_files)} files")
```

### Example 6: Error Detection and Escalation

```python
from log_monitor import LogMonitorManager, MonitoringConfig
from log_claude_escalation import LogClaudeEscalation, UserConfirmationManager

# Configure monitoring
config = MonitoringConfig(
    log_file="logs/bot.log",
    check_interval=300,  # 5 minutes
    error_threshold=5,
    escalation_threshold=3
)

# Initialize managers
monitor = LogMonitorManager(config)
escalation = LogClaudeEscalation()
confirmations = UserConfirmationManager()

# Define notification callback
async def on_issue_detected(message: str):
    await bot.send_message(chat_id=owner_id, text=message)

# Start monitoring
await monitor.start(notification_callback=on_issue_detected)

# Check for critical issues requiring escalation
if len(monitor.get_escalation_queue()) > 0:
    issues = monitor.get_escalation_queue()

    for issue in issues:
        # Get Claude's analysis
        suggested_fix = await escalation.analyze_and_suggest(issue)

        # Create confirmation request
        confirmation_id = confirmations.create_confirmation_request(
            issue, suggested_fix, confidence=0.85
        )

        # Send to user
        await bot.send_message(
            chat_id=owner_id,
            text=f"Issue detected: {issue.message}\n\nSuggested fix:\n{suggested_fix}\n\nConfirm: /confirm_{confirmation_id}"
        )

# User confirms
if confirmations.confirm_action(confirmation_id, user_notes="Looks good"):
    # Apply fix
    print("Applying fix...")
```

### Example 7: Shutdown and Recovery

```python
import signal
from database import Database
from tasks import TaskManager

db = Database()
task_manager = TaskManager(db=db)

# Register shutdown handler
def shutdown_handler(signum, frame):
    print("Shutting down gracefully...")

    # Mark all running tasks as stopped
    stopped_count = task_manager.mark_all_running_as_stopped()
    print(f"Marked {stopped_count} tasks as stopped")

    # Close database
    db.close()

    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# On startup: Check for interrupted tasks
await task_manager.check_running_tasks()

# Notify users about interrupted tasks
interrupted = db.get_interrupted_tasks()
if interrupted:
    by_user = {}
    for task in interrupted:
        user_id = task['user_id']
        if user_id not in by_user:
            by_user[user_id] = []
        by_user[user_id].append(task)

    for user_id, tasks in by_user.items():
        message = f"I restarted and found {len(tasks)} interrupted tasks:\n\n"
        for task in tasks[:3]:  # Show first 3
            message += f"- {task['description'][:60]}\n"
        message += f"\nUse /retry to resume them."

        await bot.send_message(chat_id=user_id, text=message)
```

---

## Database Query Cookbook

### Common SQLite Queries

```bash
# Get task by ID
sqlite3 data/agentlab.db "SELECT * FROM tasks WHERE task_id = 'abc123';"

# Get active tasks
sqlite3 data/agentlab.db "SELECT task_id, description, status FROM tasks WHERE status IN ('pending', 'running');"

# Count tasks by status
sqlite3 data/agentlab.db "SELECT status, COUNT(*) as count FROM tasks GROUP BY status;"

# Get recent errors
sqlite3 data/agentlab.db "SELECT task_id, error, updated_at FROM tasks WHERE error IS NOT NULL ORDER BY updated_at DESC LIMIT 10;"

# Get tool usage for task
sqlite3 data/agentlab.db "SELECT tool_name, duration_ms, success FROM tool_usage WHERE task_id = 'abc123' ORDER BY timestamp;"

# Get tool failure rate
sqlite3 data/agentlab.db "SELECT tool_name, COUNT(*) as total, SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures FROM tool_usage GROUP BY tool_name;"

# Get session UUID for task (for log correlation)
sqlite3 data/agentlab.db "SELECT session_uuid FROM tasks WHERE task_id = 'abc123';"

# Find hung tasks (running but not updated in >1 hour)
sqlite3 data/agentlab.db "SELECT task_id, description, updated_at FROM tasks WHERE status = 'running' AND julianday('now') - julianday(updated_at) > 0.042;"

# Get top accessed files
sqlite3 data/agentlab.db "SELECT file_path, access_count FROM files ORDER BY access_count DESC LIMIT 10;"
```

---

## Utilities API

### GitTracker (`utils/git.py:13`)

Tracks repositories with uncommitted changes to prevent simultaneous operations on dirty repos.

#### Initialization

```python
def __init__(self, data_file: str = "data/git_tracker.json"):
    """Initialize GitTracker with persistent storage"""
```

**State**:
- `dirty_repos: dict[str, str]` - Mapping of repo path → last operation
- `data_file: str` - Persistent storage location

**Lifecycle**:
- Loads dirty repos from disk on startup
- Auto-saves to disk on every modification
- Uses `git status --porcelain` to verify actual repo state

#### API Methods

##### check_repo_status (`utils/git.py:41`)

```python
def check_repo_status(self, repo_path: str) -> tuple[bool, str]:
    """
    Check if repo has uncommitted changes

    Returns:
        (has_changes, status_message)
    """
```

**Example**:
```python
tracker = GitTracker()
has_changes, status = tracker.check_repo_status("/Users/user/project")
if has_changes:
    print(f"Repository is dirty: {status}")
else:
    print("Repository is clean")
```

**Returns**:
- `(True, "3 files changed (2 staged) (1 unstaged)")` - Has uncommitted changes
- `(False, "Clean")` - Clean working directory
- `(False, "Not a git repository")` - Not a git repo
- `(False, "Error: ...")` - Check failed

##### mark_dirty (`utils/git.py:77`)

```python
def mark_dirty(self, repo_path: str, operation: str = "modified") -> bool:
    """Mark repo as having uncommitted changes"""
```

**Behavior**:
- Verifies repo actually has changes using `check_repo_status()`
- Only marks dirty if changes exist
- Auto-removes from dirty list if repo is clean
- Saves state to disk immediately

**Example**:
```python
tracker = GitTracker()
if tracker.mark_dirty("/Users/user/project", "code_agent modified files"):
    print("Repository marked as dirty")
else:
    print("Repository is already clean")
```

##### mark_clean (`utils/git.py:96`)

```python
def mark_clean(self, repo_path: str):
    """Mark repo as clean (changes committed)"""
```

**Example**:
```python
# After committing changes
tracker.mark_clean("/Users/user/project")
```

##### Get Status (`utils/git.py`)

```python
def get_dirty_repos(self) -> dict[str, str]:
    """Get all repos with uncommitted changes"""

def is_dirty(self, repo_path: str) -> bool:
    """Check if a specific repo is marked dirty"""
```

**Example**:
```python
dirty = tracker.get_dirty_repos()
for repo, operation in dirty.items():
    print(f"{repo}: {operation}")

if tracker.is_dirty("/Users/user/project"):
    print("Cannot work on this repo - uncommitted changes")
```

**Usage Pattern**:
```python
# Before starting work on a repo
tracker = get_git_tracker()  # Singleton instance
if tracker.is_dirty(workspace):
    raise Exception("Repository has uncommitted changes. Commit first.")

# Do work...

# After making changes
tracker.mark_dirty(workspace, "code_agent modified files")

# After committing
tracker.mark_clean(workspace)
```

---

### LogMonitorManager (`utils/log_monitor.py:31`)

Background task for monitoring logs and detecting issues proactively.

#### Initialization

```python
def __init__(self, config: MonitoringConfig):
    """Initialize log monitor with configuration"""
```

**MonitoringConfig** (`utils/log_monitor.py:19`):
```python
@dataclass
class MonitoringConfig:
    log_path: str
    check_interval_seconds: int = 300  # Check every 5 minutes
    analysis_window_hours: int = 1  # Analyze last 1 hour
    notify_on_critical: bool = True
    notify_on_warning: bool = True
    max_notifications_per_check: int = 3
    escalation_threshold: int = 3  # Escalate after N detections
```

**State**:
- `analyzer: LocalLogAnalyzer` - Log analysis engine
- `running: bool` - Monitor status
- `detection_history: dict[str, int]` - Track recurring issues
- `issue_cache: list[LogIssue]` - Issues for Claude escalation

#### API Methods

##### Lifecycle (`utils/log_monitor.py:42-65`)

```python
async def start(self, notification_callback: Callable):
    """
    Start monitoring in background
    notification_callback: async function(issue, should_escalate)
    """

async def stop(self):
    """Stop monitoring gracefully"""
```

**Example**:
```python
async def on_issue(issue: LogIssue, should_escalate: bool):
    message = f"Issue detected: {issue.title}\n{issue.description}"
    await bot.send_message(chat_id=owner_id, text=message)

    if should_escalate:
        # Escalate to Claude for analysis
        pass

config = MonitoringConfig(
    log_path="logs/bot.log",
    check_interval_seconds=300,
    notify_on_critical=True
)

monitor = LogMonitorTask(config)
await monitor.start(notification_callback=on_issue)

# Later: stop monitoring
await monitor.stop()
```

##### Manual Check (`utils/log_monitor.py:67`)

```python
async def _check_and_notify(self):
    """Check logs and notify user of issues (internal)"""
```

**Behavior**:
- Analyzes logs using `LocalLogAnalyzer`
- Filters by notification settings
- Tracks recurring issues
- Limits notifications to avoid spam
- Determines if escalation to Claude needed

**Escalation Logic**:
```python
def _should_escalate_to_claude(self, issue: LogIssue) -> bool:
    """Determine if issue should be escalated to Claude"""
    issue_key = f"{issue.issue_type.value}:{issue.title}"
    count = self.detection_history.get(issue_key, 0)
    return count >= self.config.escalation_threshold
```

---

### LocalLogAnalyzer (`utils/log_analyzer.py:61`)

Local pattern-based log analysis without making API calls.

#### Initialization

```python
def __init__(self, log_path: str):
    """Initialize analyzer with log file path"""
```

**Built-in Patterns**:
- Error patterns: `ERROR`, `Exception`, `Traceback`, `failed`, `timeout`, `Connection refused`, `Unauthorized`
- Warning patterns: `WARNING`, `Deprecated`, `MaxRetry`

#### Data Structures

**IssueLevel** (`utils/log_analyzer.py:13`):
```python
class IssueLevel(Enum):
    INFO = "info"        # Informational findings
    WARNING = "warning"  # Potential issues
    CRITICAL = "critical"  # Errors/failures
```

**IssueType** (`utils/log_analyzer.py:21`):
```python
class IssueType(Enum):
    ERROR_PATTERN = "error_pattern"
    HIGH_LATENCY = "high_latency"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    ORCHESTRATOR_FAILURE = "orchestrator_failure"
    RESOURCE_USAGE = "resource_usage"
    PERFORMANCE = "performance"
    PATTERN_ANOMALY = "pattern_anomaly"
    RECOMMENDATION = "recommendation"
```

**LogIssue** (`utils/log_analyzer.py:35`):
```python
@dataclass
class LogIssue:
    issue_type: IssueType
    level: IssueLevel
    title: str
    description: str
    evidence: list[str]  # Log lines supporting finding
    timestamp: datetime
    suggested_action: str | None = None
    requires_user_confirmation: bool = False
```

#### API Methods

##### analyze (`utils/log_analyzer.py:86`)

```python
def analyze(self, hours: int = 1) -> list[LogIssue]:
    """
    Analyze logs from the last N hours
    Returns list of issues found (local analysis only)
    """
```

**Example**:
```python
analyzer = LocalLogAnalyzer("logs/bot.log")
issues = analyzer.analyze(hours=1)

for issue in issues:
    print(f"[{issue.level.value.upper()}] {issue.title}")
    print(f"  {issue.description}")
    print(f"  Evidence: {len(issue.evidence)} log entries")
    if issue.suggested_action:
        print(f"  Suggested: {issue.suggested_action}")
```

**Returns**:
```python
[
    LogIssue(
        issue_type=IssueType.ERROR_PATTERN,
        level=IssueLevel.CRITICAL,
        title="Multiple errors detected",
        description="Found 5 ERROR entries in last hour",
        evidence=["ERROR: Failed to connect", "ERROR: Timeout", ...],
        timestamp=datetime.now(),
        suggested_action="Check network connectivity"
    ),
    # ... more issues
]
```

---

### Helper Functions (`utils/helpers.py`)

**Status**: Trivial utility functions for demonstration purposes.

These are simple mathematical and string manipulation functions demonstrating the bot's utility module structure. Not critical to core functionality.

```python
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together"""

def multiply_numbers(a: int, b: int) -> int:
    """Multiply two numbers together"""

def reverse_string(text: str) -> str:
    """Reverse a string"""
```

---

## Messaging API

### ResponseFormatter (`messaging/formatter.py:10`)

Formats agent responses for better Telegram display using HTML formatting.

#### Initialization

```python
def __init__(self, workspace_path: str | None = None):
    """Initialize formatter with optional workspace path"""
```

**State**:
- `workspace_path: str | None` - Used for highlighting repo-relative paths

#### API Methods

##### format_response (`messaging/formatter.py:16`)

```python
def format_response(self, text: str) -> str:
    """
    Apply HTML formatting to response text

    Enhancements:
    - Escape HTML entities for safety
    - Highlight file paths with <code>
    - Highlight repository names with <b>
    - Format code blocks with <pre>
    - Format lists properly
    """
```

**Example**:
```python
formatter = ResponseFormatter(workspace_path="/Users/user/project")

# Plain text input
text = """
I fixed the bug in main.py:42.

Changes:
- Updated auth logic
- Added error handling

Code:
```python
def login(user):
    return True
```
"""

# Formatted for Telegram HTML
formatted = formatter.format_response(text)
# Result includes <code>main.py:42</code>, <pre>...</pre> for code blocks
```

**Formatting Applied**:
1. Strip markdown syntax (`**bold**` → plain text)
2. Extract code blocks (`` `code` `` and `` ```blocks``` ``)
3. Escape HTML entities (`<`, `>`, `&`)
4. Highlight file paths (`main.py:42` → `<code>main.py:42</code>`)
5. Highlight repository names (`agentlab` → `<b>agentlab</b>`)
6. Format lists with proper indentation
7. Restore code blocks with `<pre>` and `<code>` tags

---

### MessageQueueManager (`messaging/queue.py:138`)

Ensures sequential message processing per user to prevent race conditions.

#### Initialization

```python
def __init__(self):
    """Initialize message queue manager"""
```

**State**:
- `user_queues: dict[int, UserMessageQueue]` - Per-user queues
- `_lock: asyncio.Lock` - Thread-safe queue creation

#### Queue Architecture

```
User 123 → UserMessageQueue → [Msg1, Msg2, Msg3] → Process sequentially
User 456 → UserMessageQueue → [Msg4, Msg5]        → Process sequentially
                                ↓
                        Parallel execution across users
```

**Priority Support**:
- `0`: Normal messages (text, voice, documents)
- `1+`: Priority commands (`/restart`, `/start`, `/clear`)

#### API Methods

##### enqueue_message (`messaging/queue.py:145`)

```python
async def enqueue_message(
    self,
    user_id: int,
    update: Any,               # Telegram Update
    context: Any,              # Telegram Context
    handler: Callable,         # Handler function
    handler_name: str = "unknown",
    priority: int = 0,         # 0=normal, 1+=priority
) -> None:
    """Queue a message for a user"""
```

**Example**:
```python
queue_manager = MessageQueueManager()

# Normal message
await queue_manager.enqueue_message(
    user_id=123456,
    update=update,
    context=context,
    handler=handle_message,
    handler_name="handle_message",
    priority=0
)

# Priority command (jumps queue)
await queue_manager.enqueue_message(
    user_id=123456,
    update=restart_update,
    context=context,
    handler=handle_restart,
    handler_name="restart",
    priority=1
)
```

##### Status Queries (`messaging/queue.py:196-207`)

```python
def get_status(self) -> dict:
    """Get status of all queues"""

async def get_user_status(self, user_id: int) -> dict | None:
    """Get status for specific user"""
```

**Returns**:
```python
{
    "active_users": 3,
    "queues": {
        "123456": {
            "user_id": 123456,
            "processing": True,
            "queue_size": 2,
            "messages_processed": 15,
            "current_message": "handle_message"
        }
    }
}
```

##### Cleanup (`messaging/queue.py:183-194`)

```python
async def cleanup_user(self, user_id: int) -> None:
    """Stop and remove queue for a user"""

async def cleanup_all(self) -> None:
    """Stop and remove all queues"""
```

---

### UserMessageQueue (`messaging/queue.py:36`)

Queue for a single user's messages with priority support.

#### Initialization

```python
def __init__(self, user_id: int):
    """Initialize queue for a user"""
```

**State**:
- `queue: asyncio.Queue[QueuedMessage]` - Normal priority messages
- `priority_queue: list[QueuedMessage]` - High priority messages
- `processing: bool` - Queue processor status
- `current_message: QueuedMessage | None` - Currently processing message
- `messages_processed: int` - Total messages processed

#### Processing Logic (`messaging/queue.py:77`)

```python
async def _process_queue(self) -> None:
    """Process queued messages sequentially, prioritizing high-priority"""
```

**Behavior**:
1. Check `priority_queue` first (sorted by priority)
2. Process priority message if available
3. Otherwise, wait for normal message from `queue`
4. Execute handler
5. Mark done and continue

**Example**:
```python
# Internal usage - managed by MessageQueueManager
queue = UserMessageQueue(user_id=123456)
await queue.enqueue(QueuedMessage(..., priority=0))
await queue.enqueue(QueuedMessage(..., priority=1))  # Processes first
```

---

### RateLimiter (`messaging/rate_limiter.py:25`)

Rate limiter with per-user tracking and cooldown system.

#### Initialization

```python
def __init__(self):
    """Initialize rate limiter"""
```

**RateLimitConfig** (`messaging/rate_limiter.py:16`):
```python
@dataclass
class RateLimitConfig:
    requests_per_minute: int = 10
    requests_per_hour: int = 100
    burst_size: int = 3  # Allow small bursts
    cooldown_seconds: int = 60  # Cooldown after hitting limit
```

**State**:
- `user_requests: dict[int, deque]` - Per-user request timestamps
- `user_cooldowns: dict[int, datetime]` - Cooldown end times
- `config: RateLimitConfig` - Rate limit configuration

#### API Methods

##### check_rate_limit (`messaging/rate_limiter.py:60`)

```python
def check_rate_limit(self, user_id: int) -> tuple[bool, str | None]:
    """
    Check if user can make a request
    Returns: (allowed, error_message)
    """
```

**Example**:
```python
limiter = RateLimiter()

allowed, error = limiter.check_rate_limit(user_id=123456)
if not allowed:
    await update.message.reply_text(error)
    return

# Process request
limiter.record_request(user_id=123456)
```

**Returns**:
- `(True, None)` - Request allowed
- `(False, "Rate limit exceeded. Please wait 60s...")` - Per-minute limit hit
- `(False, "Too many requests. Limit: 100/hour...")` - Per-hour limit hit
- `(False, "Too many requests in short time...")` - Burst limit hit

##### record_request (`messaging/rate_limiter.py`)

```python
def record_request(self, user_id: int):
    """Record a request for rate limiting"""
```

**Example**:
```python
limiter = RateLimiter()

# Check before processing
allowed, error = limiter.check_rate_limit(user_id)
if not allowed:
    return error

# Process request...

# Record after successful processing
limiter.record_request(user_id)
```

##### Reset Methods

```python
def reset_user(self, user_id: int):
    """Reset rate limit state for a user"""

def get_user_stats(self, user_id: int) -> dict:
    """Get rate limit stats for a user"""
```

---

## Monitoring API

### MetricsAggregator (`monitoring/metrics.py:32`)

Aggregates metrics from all tracking systems for dashboard display.

#### Initialization

```python
def __init__(
    self,
    task_manager: TaskManager,
    tool_usage_tracker: ToolUsageTracker,
    hooks_reader: HooksReader | None = None,
):
    """Initialize metrics aggregator with tracking systems"""
```

**State**:
- `task_manager: TaskManager` - Task tracking
- `tool_usage_tracker: ToolUsageTracker` - Tool usage tracking
- `hooks_reader: HooksReader` - Hook log reader (optional)

#### API Methods

##### get_task_statistics (`monitoring/metrics.py:47`)

```python
def get_task_statistics(self) -> dict[str, Any]:
    """Get task execution statistics"""
```

**Returns**:
```python
{
    "total_tasks": 150,
    "by_status": {
        "completed": 120,
        "failed": 20,
        "running": 5,
        "pending": 5
    },
    "success_rate": 85.7,
    "recent_24h": {
        "total": 30,
        "completed": 25,
        "failed": 5,
        "tasks": [
            {
                "task_id": "abc123",
                "user_id": 123456,
                "description": "Fix bug in main.py",
                "status": "completed",
                "created_at": "2025-01-15T10:00:00",
                "model": "sonnet"
            },
            # ... more tasks
        ]
    }
}
```

##### get_tool_usage_metrics (`monitoring/metrics.py:91`)

```python
def get_tool_usage_metrics(self, hours: int = 24) -> dict[str, Any]:
    """Get tool usage statistics from Claude Code hooks"""
```

**Returns**:
```python
{
    "time_window_hours": 24,
    "total_tool_calls": 5000,
    "tools_breakdown": {
        "Read": 2000,
        "Write": 500,
        "Edit": 1000,
        "Bash": 800,
        "Grep": 500,
        "Glob": 200
    },
    "most_used_tools": [
        {
            "tool": "Read",
            "count": 2000,
            "success_rate": 0.98,
            "avg_duration_ms": 50.5
        },
        # ... top 10 tools
    ],
    "agent_status": {
        "active_sessions": 3,
        "recent_errors": 5
    }
}
```

##### get_snapshot (`monitoring/metrics.py`)

```python
def get_snapshot(self) -> MetricsSnapshot:
    """Get complete metrics snapshot for dashboard"""
```

**Example**:
```python
aggregator = MetricsAggregator(
    task_manager=task_manager,
    tool_usage_tracker=tracker,
    hooks_reader=hooks_reader
)

# Get full snapshot
snapshot = aggregator.get_snapshot()
print(f"Tasks: {snapshot.task_statistics['total_tasks']}")
print(f"Tool calls: {snapshot.tool_usage['total_tool_calls']}")

# Individual metrics
task_stats = aggregator.get_task_statistics()
tool_stats = aggregator.get_tool_usage_metrics(hours=24)
```

---

### HooksReader (`monitoring/hooks_reader.py:29`)

Reads and aggregates Claude Code hook logs from session directories.

#### Initialization

```python
def __init__(
    self,
    sessions_dir: str = "logs/sessions",
    additional_dirs: list[str] | None = None
):
    """Initialize hooks reader with session directories"""
```

**State**:
- `sessions_dir: Path` - Primary session logs directory
- `additional_dirs: list[Path]` - Additional directories to search

**Session Structure**:
```
logs/sessions/
├── {session_uuid_1}/
│   ├── pre_tool_use.jsonl    # Tool invocations
│   ├── post_tool_use.jsonl   # Tool results
│   └── summary.json          # Session summary
├── {session_uuid_2}/
│   └── ...
```

#### Data Structures

**HookSessionSummary** (`monitoring/hooks_reader.py:17`):
```python
@dataclass
class HookSessionSummary:
    session_id: str
    total_tools: int
    tools_by_type: dict[str, int]
    blocked_operations: int
    tools_with_errors: int
    timestamps: list[str]
```

#### API Methods

##### get_all_sessions (`monitoring/hooks_reader.py:38`)

```python
def get_all_sessions(self) -> list[str]:
    """Get list of all session IDs from all configured directories"""
```

##### read_session_summary (`monitoring/hooks_reader.py:68`)

```python
def read_session_summary(self, session_id: str) -> HookSessionSummary | None:
    """Read summary for a specific session"""
```

**Example**:
```python
reader = HooksReader(
    sessions_dir="logs/sessions",
    additional_dirs=["logs/archive/sessions"]
)

# Get all sessions
sessions = reader.get_all_sessions()
print(f"Found {len(sessions)} sessions")

# Read specific session
summary = reader.read_session_summary("abc123-session-uuid")
if summary:
    print(f"Tools used: {summary.total_tools}")
    print(f"By type: {summary.tools_by_type}")
    print(f"Errors: {summary.tools_with_errors}")
```

##### read_session_pre_tools (`monitoring/hooks_reader.py:94`)

```python
def read_session_pre_tools(self, session_id: str) -> list[dict]:
    """Read pre-tool logs for a session"""
```

**Returns**: List of tool invocation records from `pre_tool_use.jsonl`

##### get_aggregate_statistics (`monitoring/hooks_reader.py`)

```python
def get_aggregate_statistics(self, hours: int = 24) -> dict:
    """Get aggregate statistics across all sessions"""
```

**Returns**:
```python
{
    "total_sessions": 50,
    "total_tool_calls": 5000,
    "tools_by_type": {
        "Read": 2000,
        "Write": 500,
        # ...
    },
    "blocked_operations": 10,
    "tools_with_errors": 25
}
```

---

### CommandHandler (`monitoring/commands.py:10`)

Handles bot commands for web chat interface.

#### Initialization

```python
def __init__(self, task_manager: TaskManager):
    """Initialize command handler with task manager"""
```

#### API Methods

##### handle_command (`monitoring/commands.py:16`)

```python
async def handle_command(self, command: str, user_id: str) -> dict:
    """
    Route command to appropriate handler

    Returns:
        dict with keys:
            - success: bool
            - message: str (response message)
            - data: dict (optional additional data)
    """
```

**Supported Commands**:
- `/status` - Get task status report
- `/stop <task_id>` - Stop specific task
- `/stopall` - Stop all active tasks
- `/retry <task_id>` - Retry failed task
- `/view <task_id>` - View task details

**Example**:
```python
handler = CommandHandler(task_manager)

# Handle status command
result = await handler.handle_command("/status", user_id="123456")
print(result["message"])  # Formatted status report

# Handle stop command
result = await handler.handle_command("/stop abc123", user_id="123456")
if result["success"]:
    print(f"Task stopped: {result['message']}")
```

**Return Format**:
```python
{
    "success": True,
    "message": "Task abc123 stopped successfully",
    "data": {  # Optional
        "task_id": "abc123",
        "status": "stopped"
    }
}
```

---

## Task Enforcement API

### WorkflowEnforcer (`tasks/enforcer.py:13`)

Enforces testing and commit requirements for code changes.

#### Initialization

```python
def __init__(self, workspace: Path):
    """Initialize workflow enforcer for workspace"""
```

**State**:
- `workspace: Path` - Repository path
- `pre_commit_installed: bool` - Pre-commit availability

#### API Methods

##### get_changed_files (`tasks/enforcer.py:46`)

```python
def get_changed_files(self) -> list[str]:
    """Get list of modified/untracked Python files"""
```

**Returns**: List of `.py` files that are modified or untracked

**Example**:
```python
enforcer = WorkflowEnforcer(workspace=Path("/Users/user/project"))
changed = enforcer.get_changed_files()
print(f"Modified Python files: {changed}")
```

##### has_uncommitted_changes (`tasks/enforcer.py:71`)

```python
def has_uncommitted_changes(self) -> bool:
    """Check if there are uncommitted changes"""
```

##### run_tests (`tasks/enforcer.py:82`)

```python
def run_tests(self) -> tuple[bool, str]:
    """Run tests if they exist"""
```

**Behavior**:
- Searches for test directories (`tests/`, `test/`)
- Searches for test files (`test_*.py`, `*_test.py`)
- Runs `pytest` if tests found
- Returns `(True, "No tests found")` if no tests

**Returns**:
- `(True, "All tests passed (15 passed)")` - Tests passed
- `(False, "Tests failed: 2 failed, 13 passed")` - Tests failed
- `(True, "No tests found - skipping")` - No tests

**Example**:
```python
enforcer = WorkflowEnforcer(workspace)
success, message = enforcer.run_tests()
if not success:
    print(f"Test failure: {message}")
```

##### run_pre_commit (`tasks/enforcer.py`)

```python
def run_pre_commit(self) -> tuple[bool, str]:
    """Run pre-commit hooks on changed files"""
```

**Example**:
```python
enforcer = WorkflowEnforcer(workspace)
success, message = enforcer.run_pre_commit()
if not success:
    print(f"Pre-commit failed: {message}")
```

##### enforce_workflow (`tasks/enforcer.py`)

```python
def enforce_workflow(self) -> tuple[bool, list[str]]:
    """
    Enforce complete workflow:
    1. Check for uncommitted changes
    2. Run tests if they exist
    3. Run pre-commit hooks

    Returns: (success, messages)
    """
```

**Example**:
```python
enforcer = WorkflowEnforcer(workspace)
success, messages = enforcer.enforce_workflow()

if not success:
    print("Workflow enforcement failed:")
    for msg in messages:
        print(f"  - {msg}")
else:
    print("Workflow checks passed!")
```

---

### AnalyticsDB (`tasks/analytics.py:15`)

Analytics database wrapper for message and conversation tracking.

#### Initialization

```python
def __init__(self, db: Database):
    """Initialize analytics DB wrapper with existing Database"""
```

**Schema**:
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,            -- 'user' or 'assistant'
    content TEXT NOT NULL,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cache_creation_tokens INTEGER,
    cache_read_tokens INTEGER,
    conversation_id TEXT,
    input_method TEXT,             -- 'text', 'voice', 'image'
    has_image BOOLEAN DEFAULT 0,
    model TEXT
);
```

#### API Methods

##### log_message (`tasks/analytics.py:81`)

```python
def log_message(
    self,
    user_id: int,
    role: str,
    content: str,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    cache_creation_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    conversation_id: str | None = None,
    input_method: str = "text",
    has_image: bool = False,
    model: str | None = None,
) -> int:
    """
    Log a message to the analytics database

    Returns: Message ID
    """
```

**Example**:
```python
analytics = AnalyticsDB(db)

# Log user message
analytics.log_message(
    user_id=123456,
    role="user",
    content="Fix bug in main.py",
    conversation_id="conv-abc123",
    input_method="text"
)

# Log assistant response with token usage
analytics.log_message(
    user_id=123456,
    role="assistant",
    content="I'll fix that for you...",
    tokens_input=1000,
    tokens_output=500,
    cache_read_tokens=2000,
    conversation_id="conv-abc123",
    model="sonnet"
)
```

##### Query Methods

```python
def get_user_messages(
    self, user_id: int, limit: int = 100
) -> list[dict]:
    """Get recent messages for a user"""

def get_conversation(
    self, conversation_id: str
) -> list[dict]:
    """Get all messages in a conversation"""

def get_token_usage_summary(
    self, user_id: int | None = None, days: int = 30
) -> dict:
    """Get token usage summary"""
```

**Example**:
```python
# Get recent messages
messages = analytics.get_user_messages(user_id=123456, limit=50)
for msg in messages:
    print(f"{msg['role']}: {msg['content'][:50]}")

# Get conversation
conversation = analytics.get_conversation("conv-abc123")
print(f"Conversation has {len(conversation)} messages")

# Token usage summary
usage = analytics.get_token_usage_summary(user_id=123456, days=7)
print(f"Last 7 days:")
print(f"  Input tokens: {usage['total_input_tokens']}")
print(f"  Output tokens: {usage['total_output_tokens']}")
print(f"  Cache reads: {usage['total_cache_read_tokens']}")
```

---

## Cross-Reference: Related APIs

### Task Management Flow
1. **TaskManager** (`tasks/manager.py`) - Create and track tasks
2. **AgentPool** (`agent_pool.py`) - Execute tasks in worker pool
3. **ClaudeSessionPool** (`claude_interactive.py`) - Run Claude Code sessions
4. **WorkflowEnforcer** (`tasks/enforcer.py`) - Enforce testing/commit workflow
5. **ToolUsageTracker** (`tasks/tracker.py`) - Track tool usage
6. **Database** (`tasks/database.py`) - Persist all data

### Message Processing Flow
1. **MessageQueueManager** (`messaging/queue.py`) - Queue messages per user
2. **RateLimiter** (`messaging/rate_limiter.py`) - Check rate limits
3. **ResponseFormatter** (`messaging/formatter.py`) - Format responses
4. **SessionManager** (`session.py`) - Track conversation history

### Monitoring Flow
1. **LogMonitorManager** (`utils/log_monitor.py`) - Monitor logs
2. **LocalLogAnalyzer** (`utils/log_analyzer.py`) - Analyze log patterns
3. **MetricsAggregator** (`monitoring/metrics.py`) - Aggregate metrics
4. **HooksReader** (`monitoring/hooks_reader.py`) - Read hook logs
5. **AnalyticsDB** (`tasks/analytics.py`) - Track conversations

### Git Operations Flow
1. **GitTracker** (`utils/git.py`) - Track dirty repos
2. **WorkflowEnforcer** (`tasks/enforcer.py`) - Enforce commit workflow
3. **WorktreeManager** (`utils/worktree.py`) - DEPRECATED - Use git-worktree agent

---

**End of API Documentation**

For workflow examples and agent architecture, see:
- `docs/archive/AGENT_ARCHITECTURE.md` - Agent system design
- `.claude/agents/` - Agent configurations
- `CLAUDE.md` - Repository conventions and patterns
