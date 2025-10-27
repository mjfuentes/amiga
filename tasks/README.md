# Tasks

## Purpose
Background task management system providing task tracking, lifecycle management, execution pool, analytics, usage tracking, and workflow enforcement.

## Components

### manager.py
Task lifecycle management and background task coordination.
- `Task` dataclass: task metadata, status, results
- `TaskManager`: task CRUD operations, status updates, cleanup
- Task branch creation/merging for isolated work
- Process lifecycle tracking (PID monitoring)
- Activity log management (JSON array of events)
- SQLite persistence via `database.py`

### database.py
Centralized SQLite backend for persistent storage.
- Database initialization and schema migrations
- Tasks table: background task tracking
- Tool usage table: Claude Code tool invocations
- Agent status table: status change tracking
- Files table: file access analytics
- Games table: game state persistence
- User management: web UI authentication
- Async-safe write locking
- WAL mode for concurrency

### pool.py
Bounded worker pool for concurrent task execution.
- `AgentPool`: async task queue with max concurrency
- `TaskPriority`: priority levels (HIGH/NORMAL/LOW)
- Priority queue implementation
- Worker lifecycle management
- Task cancellation support
- Graceful shutdown handling

### tracker.py
Tool usage tracking and analytics for Claude Code agents.
- `ToolUsageTracker`: records tool invocations to database
- Error categorization (file_not_found, permission_denied, etc.)
- Duration tracking
- Token usage metrics
- Screenshot path recording
- Session UUID correlation

### analytics.py
Database analytics queries and reporting.
- `AnalyticsDB`: high-level query interface
- Tool usage statistics by agent/workflow
- Error rate analysis
- Cost tracking and projections
- Task success/failure rates
- File access patterns

### enforcer.py
Workflow validation and git commit enforcement.
- Pre-task checks (uncommitted changes detection)
- Post-task validation (verify commits made)
- Git dirty state blocking
- Enforcement rules per agent type
- Warning/blocking modes

## Usage Examples

### Task Management
```python
from tasks.manager import TaskManager

task_manager = TaskManager(data_dir="data")

# Create background task
task = await task_manager.create_task(
    user_id=12345,
    description="Fix authentication bug",
    model="sonnet",
    workspace="/Users/user/Workspace/project",
    agent_type="code_agent",
    workflow="smart-fix"
)

# Update task status
await task_manager.update_task_status(
    task_id=task.task_id,
    status="running",
    pid=12345
)

# Add activity log entry
await task_manager.add_activity(
    task_id=task.task_id,
    message="Starting bug investigation"
)

# Complete task
await task_manager.complete_task(
    task_id=task.task_id,
    result="Fixed authentication bug in auth.py:42"
)

# Get user's active tasks
active_tasks = await task_manager.get_user_tasks(
    user_id=12345,
    status="running"
)
```

### Agent Pool
```python
from tasks.pool import AgentPool, TaskPriority

pool = AgentPool(max_agents=3)

# Submit high-priority task
result = await pool.submit(
    execute_task,
    task_id="abc123",
    description="Critical bug fix",
    priority=TaskPriority.HIGH
)

# Check pool status
status = pool.get_status()
# {
#     "total_workers": 3,
#     "active_workers": 2,
#     "queued_tasks": 5,
#     "queue_size": 10
# }

# Graceful shutdown
await pool.shutdown()
```

### Tool Usage Tracking
```python
from tasks.tracker import ToolUsageTracker

tracker = ToolUsageTracker(data_dir="data")

# Record tool usage
tracker.record_tool_usage(
    task_id="abc123",
    tool_name="Read",
    duration_ms=150.5,
    success=True,
    parameters={"file_path": "/path/to/file.py"}
)

# Record error
tracker.record_tool_usage(
    task_id="abc123",
    tool_name="Write",
    duration_ms=50.0,
    success=False,
    error="Permission denied",
    parameters={"file_path": "/etc/passwd"}
)

# Get tool statistics
stats = tracker.get_tool_stats(hours=24)
# {
#     "Read": {"count": 150, "success_rate": 0.98},
#     "Write": {"count": 45, "success_rate": 0.95},
#     ...
# }
```

### Analytics Queries
```python
from tasks.analytics import AnalyticsDB

analytics = AnalyticsDB()

# Get tool usage by workflow
stats = analytics.get_tool_usage_by_workflow("code-task")
# [
#     {"tool_name": "Read", "count": 120, "avg_duration": 145.2},
#     {"tool_name": "Edit", "count": 45, "avg_duration": 230.5},
#     ...
# ]

# Get error rates
errors = analytics.get_error_rates(days=7)
# {
#     "file_not_found": 12,
#     "permission_denied": 3,
#     "timeout": 5,
#     ...
# }

# Cost tracking
costs = analytics.get_daily_costs(days=30)
# [
#     {"date": "2025-10-22", "cost": 5.23, "tasks": 15},
#     {"date": "2025-10-23", "cost": 3.45, "tasks": 8},
#     ...
# ]
```

### Workflow Enforcement
```python
from tasks.enforcer import WorkflowEnforcer

enforcer = WorkflowEnforcer(git_tracker=git_tracker)

# Pre-task check
allowed, message = enforcer.check_pre_task(
    workspace="/Users/user/Workspace/project",
    agent_type="code_agent"
)

if not allowed:
    print(f"Blocked: {message}")
    # "Uncommitted changes in /Users/user/Workspace/project"

# Post-task validation
passed, message = enforcer.validate_post_task(
    task_id="abc123",
    workspace="/Users/user/Workspace/project",
    agent_type="code_agent"
)

if not passed:
    print(f"Warning: {message}")
    # "Agent made file changes without committing"
```

## Dependencies

### Internal
- `core/config.py` - Configuration paths and environment variables
- `utils/git.py` - Git operations and dirty state tracking
- `utils/worktree.py` - Git worktree management
- `monitoring/hooks_reader.py` - Hook data parsing for tool usage

### External
- `sqlite3` - SQLite database backend
- `asyncio` - Async task execution and queue management
- `dataclasses` - Data structure definitions
- `bcrypt` - Password hashing for user management
- `jwt` - JWT token generation for web UI auth

## Architecture

### Task Lifecycle
```
Create Task (pending)
    ↓
Submit to AgentPool (queued)
    ↓
Worker Picks Up (running)
    ↓ (writes to database throughout execution)
Tool Usage Tracked → database.tool_usage
Activity Logs → task.activity_log (JSON array)
    ↓
Task Completes (completed/failed/stopped)
    ↓
Result/Error Stored → task.result/task.error
    ↓
Post-Task Validation (enforcer checks commits)
```

### Database Schema
```
tasks (primary tracking)
    ↓ (linked by task_id)
tool_usage (tool invocations)
agent_status (status changes)
    ↓ (analytics layer)
Query patterns: by user, by status, by workflow, by time range
```

### Agent Pool Flow
```
Priority Queue (HIGH → NORMAL → LOW)
    ↓
Worker Pool (max_agents=3)
    ↓
Worker 1: Task A (running)
Worker 2: Task B (running)
Worker 3: Available
    ↓
Queued Tasks: [Task C (HIGH), Task D (NORMAL), Task E (LOW)]
    ↓
Worker 3 picks Task C (highest priority)
```

## Cross-References

- **Database Schema**: See [docs/API.md](../docs/API.md#database-layer) for complete schema and query patterns
- **Manager Classes**: See [docs/API.md](../docs/API.md#manager-classes-overview) for TaskManager, ToolUsageTracker, AnalyticsDB details
- **Git Operations**: See [utils/README.md](../utils/README.md) for git workflow and worktree management
- **Testing**: See [tests/README.md](../tests/README.md) for task system tests

## Key Patterns

### Task Isolation with Branches
Each task creates a branch (`task/<task_id>`) for isolated work:
1. Create branch from current HEAD
2. Agent makes changes and commits
3. Merge back to main on completion
4. Clean up branch

### Async-Safe Database Access
All writes use `async with self._write_lock` to prevent race conditions:
```python
async with self._write_lock:
    self.conn.execute("UPDATE tasks SET status = ?", (status,))
    self.conn.commit()
```

### Tool Usage Correlation
Tool usage records link to tasks via `task_id` and sessions via `session_uuid` for cross-referencing tool invocations with task outcomes.

### Priority Queue
Agent pool uses priority-based task scheduling:
- HIGH: Critical bugs, user-requested tasks
- NORMAL: Background tasks, refactoring
- LOW: Cleanup, optimization

### Workflow Enforcement
Enforcer blocks tasks if workspace has uncommitted changes, enforcing agent commit policy.

## Performance Considerations

### Database Indices
- `idx_tasks_user_status` - Fast user task lookups
- `idx_tool_timestamp` - Fast tool usage queries
- `idx_tool_task` - Fast task→tools correlation

### WAL Mode
Write-Ahead Logging allows concurrent reads during writes, improving dashboard responsiveness.

### Connection Pooling
Single `Database` instance shared across modules, avoiding connection overhead.

## Notes

- Task IDs are 6-char UUID prefixes (e.g., "abc123")
- Session UUIDs are full UUIDs for log directory correlation
- Activity logs stored as JSON array in single TEXT column
- Tool usage parameters stored as JSON blob for flexibility
- Error categories standardized: `file_not_found`, `permission_denied`, `timeout`, `command_failed`, `syntax_error`
- Games table separate from tasks for future game state persistence
