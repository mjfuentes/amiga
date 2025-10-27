# Monitoring

## Purpose
Real-time monitoring infrastructure providing web dashboard, metrics aggregation, hook data parsing, and command handling for task management and analytics.

## Components

### server.py
Flask-based web server with SSE and WebSocket support.
- Flask app with Jinja2 templates
- Server-Sent Events (SSE) for real-time metrics streaming
- WebSocket support for web chat interface
- REST API endpoints for task management
- User authentication with JWT
- CORS configuration for frontend integration
- Static file serving for React dashboard

### metrics.py
Real-time metrics aggregation from multiple data sources.
- `MetricsAggregator`: combines task, tool usage, and hook data
- Active task monitoring
- Error tracking and categorization
- Cost calculations (24h, daily, monthly)
- Tool usage statistics by agent/workflow
- Performance metrics (tool duration, success rates)

### hooks_reader.py
Claude Code hook data parser and session log reader.
- `HooksReader`: parses hook JSONL files
- Session discovery (logs/sessions/<uuid>/)
- Pre-tool-use and post-tool-use log parsing
- Session summary aggregation
- Tool invocation correlation
- Multi-directory support (workspace + bot logs)

### commands.py
Command handler for task management operations.
- `CommandHandler`: executes task-related commands
- Task lifecycle commands (start, stop, restart)
- Status queries and filtering
- Bulk operations (stop all, clear failed)
- Command validation and error handling

## Usage Examples

### Web Server
```python
from monitoring.server import app, socketio

# Run server (production)
socketio.run(app, host="0.0.0.0", port=3000)

# Run with Flask dev server (development)
app.run(debug=True, port=3000)

# Server provides:
# - http://localhost:3000/ - Dashboard (SSE-based metrics)
# - http://localhost:3000/chat - React chat UI
# - http://localhost:3000/api/metrics - REST API
# - ws://localhost:3000/socket.io - WebSocket for chat
```

### Metrics Aggregation
```python
from monitoring.metrics import MetricsAggregator

aggregator = MetricsAggregator(task_manager, tool_tracker, hooks_reader)

# Get real-time metrics snapshot
metrics = aggregator.get_metrics()
# {
#     "active_tasks": 3,
#     "completed_tasks_24h": 45,
#     "failed_tasks_24h": 2,
#     "tool_usage_24h": {
#         "Read": 120,
#         "Write": 45,
#         "Edit": 30
#     },
#     "cost_24h": 5.23,
#     "top_errors": [
#         {"error": "file_not_found", "count": 5},
#         {"error": "permission_denied", "count": 2}
#     ]
# }

# Get task details
task_details = aggregator.get_task_details(task_id="abc123")
# {
#     "task_id": "abc123",
#     "status": "running",
#     "tool_usage": [...],
#     "duration_ms": 15230,
#     "progress": "45%"
# }
```

### Hooks Reader
```python
from monitoring.hooks_reader import HooksReader

reader = HooksReader(
    sessions_dir="logs/sessions",
    additional_dirs=["workspace/logs/sessions"]
)

# Get all sessions
sessions = reader.get_all_sessions()
# [
#     {
#         "session_uuid": "550e8400-...",
#         "tool_count": 15,
#         "duration_ms": 45230,
#         "status": "completed"
#     },
#     ...
# ]

# Get session details
session = reader.get_session_details("550e8400-...")
# {
#     "tools": [
#         {
#             "tool_name": "Read",
#             "timestamp": "2025-10-22T10:30:45",
#             "duration_ms": 150,
#             "success": True,
#             "parameters": {"file_path": "/path/to/file.py"}
#         },
#         ...
#     ],
#     "summary": {...}
# }

# Parse pre-tool-use logs
tools = reader.parse_pre_tool_use("logs/sessions/abc123/pre_tool_use.jsonl")
# List of tool invocation records
```

### Command Handler
```python
from monitoring.commands import CommandHandler

handler = CommandHandler(task_manager)

# Execute command
result = await handler.handle_command("/tasks:status")
# {
#     "success": True,
#     "message": "3 active tasks, 45 completed, 2 failed",
#     "data": [...]
# }

# Stop task
result = await handler.handle_command("/tasks:stop abc123")
# {
#     "success": True,
#     "message": "Task abc123 stopped"
# }

# Stop all tasks
result = await handler.handle_command("/tasks:stopall")
# {
#     "success": True,
#     "message": "Stopped 3 tasks"
# }
```

## Dependencies

### Internal
- `tasks/manager.py` - Task lifecycle management
- `tasks/tracker.py` - Tool usage tracking
- `tasks/database.py` - Database queries
- `core/session.py` - Session management for web chat
- `claude/code_cli.py` - CLI session pool for web chat execution

### External
- `flask` - Web framework
- `flask-socketio` - WebSocket support
- `flask-cors` - CORS middleware
- `eventlet` - Async server (monkey-patched)
- `jwt` - JWT authentication
- `bcrypt` - Password hashing

## Architecture

### Dashboard Flow (SSE-based)
```
Browser → http://localhost:3000/
    ↓
server.py renders dashboard.html
    ↓
JavaScript connects to /api/metrics (SSE)
    ↓
metrics.py aggregates data every 2 seconds
    ↓
Server sends SSE events with JSON payload
    ↓
Browser updates UI (active tasks, errors, costs)
```

### Chat Flow (WebSocket-based)
```
Browser → http://localhost:3000/chat
    ↓
React app loads from static/chat/
    ↓
WebSocket connection to /socket.io
    ↓
User sends message → emit('chat_message')
    ↓
server.py handles message:
    ↓
    ├→ claude/code_cli.py executes task
    └→ emit('chat_response') back to user
```

### Hook Data Flow
```
Claude Code CLI executes
    ↓
Hooks write to logs/sessions/<session_uuid>/
    ↓
hooks_reader.py discovers sessions
    ↓
Parse pre_tool_use.jsonl + post_tool_use.jsonl
    ↓
Correlate with database.tool_usage (by session_uuid)
    ↓
metrics.py aggregates for dashboard
```

## Cross-References

- **Task Management**: See [tasks/README.md](../tasks/README.md) for task lifecycle and database schema
- **Hook System**: See `.claude/hooks/` for hook implementation details
- **Web Chat**: See `dashboard/README.md` for React frontend architecture
- **API Documentation**: See [docs/API.md](../docs/API.md) for REST API endpoint details

## Key Patterns

### Server-Sent Events (SSE)
Dashboard uses SSE for real-time updates:
- One-way server → client communication
- Automatic reconnection on disconnect
- Lower overhead than WebSocket for read-only data

### Change Detection
Metrics aggregator only sends updates when data changes:
```python
if current_metrics != last_metrics:
    yield f"data: {json.dumps(current_metrics)}\n\n"
    last_metrics = current_metrics
```

### Multi-Directory Hook Discovery
Hooks reader scans multiple directories for sessions:
- `logs/sessions/` - Bot task sessions
- `workspace/logs/sessions/` - User workspace sessions
- Unified view of all Claude Code activity

### JWT Authentication
Web chat uses JWT for stateless auth:
- Login → generate JWT token
- Token stored in browser localStorage
- Token validated on each WebSocket message

### Async Event Loop Sharing
Server runs eventlet with monkey-patching:
```python
import eventlet
eventlet.monkey_patch()
```
Allows Flask to run async operations without blocking.

## REST API Endpoints

### Metrics
- `GET /api/metrics` - SSE stream of real-time metrics
- `GET /api/tasks` - List all tasks
- `GET /api/tasks/<task_id>` - Get task details
- `GET /api/tool_usage/<task_id>` - Get tool usage for task

### Task Management
- `POST /api/tasks/stop/<task_id>` - Stop task
- `POST /api/tasks/restart/<task_id>` - Restart task
- `DELETE /api/tasks/<task_id>` - Delete task

### Web Chat
- `POST /api/auth/login` - Login and get JWT token
- `POST /api/auth/register` - Register new user (disabled in prod)
- `WebSocket /socket.io` - Chat message exchange

## Performance Considerations

### Metrics Caching
Metrics aggregator caches data for 2 seconds to reduce database load:
```python
@lru_cache(maxsize=1)
def get_metrics_cached():
    return aggregator.get_metrics()
```

### Selective SSE Updates
Only send SSE events when metrics change (reduces bandwidth):
```python
if current_snapshot != last_snapshot:
    send_sse_event(current_snapshot)
```

### Hook File Parsing
Hook files parsed on-demand (not continuously):
- Triggered by dashboard refresh
- Cached in memory for 30 seconds
- Only parse recent sessions (last 24 hours)

### Database Query Optimization
Use indices for fast queries:
- `idx_tasks_user_status` - User's active tasks
- `idx_tool_timestamp` - Recent tool usage
- `idx_tool_task` - Task's tool usage

## WebSocket Events

### Client → Server
- `chat_message` - User sends message
- `disconnect` - User leaves chat

### Server → Client
- `chat_response` - Bot response
- `chat_error` - Error occurred
- `task_update` - Background task status change

## Notes

- Server runs on port 3000 (configurable)
- SSE connection timeout: 30 seconds
- WebSocket ping interval: 25 seconds
- Metrics update interval: 2 seconds
- Hook session TTL: 24 hours (older sessions ignored)
- CORS enabled for localhost:3000 and localhost:3001 (dev/prod)
- Static files cached for 0 seconds in dev (instant reload)
- JWT secret must be set in production (`JWT_SECRET_KEY` env var)
- Eventlet required for WebSocket support (gevent incompatible)
