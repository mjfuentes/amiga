# Core

## Purpose
Core bot infrastructure providing entry point, configuration, session management, task orchestration, and intelligent routing between Claude API and Claude Code CLI.

## Components

### main.py
Telegram bot entry point with command handlers, message processing, and lifecycle management.
- Bot initialization and startup
- Command handlers (`/start`, `/clear`, `/status`, `/restart`, etc.)
- Message routing to Claude API or orchestrator
- Voice message transcription via Whisper
- User permission enforcement
- Bot restart and state recovery

### config.py
Centralized configuration management for file paths and directory structures.
- Project root and data directory paths
- Database configuration (`DATABASE_PATH`)
- Log file locations
- Environment variable overrides
- Path resolution helpers for CWD-relative access

### session.py
User session management with persistent conversation history.
- `Session` dataclass: conversation history, workspace tracking
- `SessionManager`: session CRUD operations, history limits
- `ClaudeCodeSession`: Context-aware Claude Code CLI client (deprecated)
- Per-user session isolation
- JSON persistence to `data/sessions.json`

### orchestrator.py
Orchestrator agent invocation for user query routing and task coordination.
- Repository discovery and validation
- Git dirty state checking
- Orchestrator agent invocation via Claude Code CLI
- Context building (history, workspace, active tasks)
- Background task format parsing (`BACKGROUND_TASK|description|message`)
- Fire-and-forget subprocess execution

### routing.py
Intelligent workflow routing using Claude API.
- `WorkflowRouter`: Claude Haiku-based workflow selection
- Available workflows: `code-task`, `smart-fix`, `improve-agent`
- Decision criteria for workflow selection
- API-driven routing (deterministic, cost-optimized)

## Usage Examples

### Configuration
```python
from core.config import DATABASE_PATH, DATA_DIR, LOGS_DIR

# Use configured paths
db_path = DATABASE_PATH  # Respects AGENTLAB_DB_PATH env var
data_files = DATA_DIR / "sessions.json"
```

### Session Management
```python
from core.session import SessionManager

session_manager = SessionManager(data_dir="data")

# Add message to user's history
session_manager.add_message(user_id=12345, role="user", content="Hello")
session_manager.add_message(user_id=12345, role="assistant", content="Hi there!")

# Get conversation history
history = session_manager.get_history(user_id=12345, limit=5)

# Set workspace context
session_manager.set_workspace(user_id=12345, workspace="/path/to/repo")

# Clear session
session_manager.clear_session(user_id=12345)
```

### Orchestrator Invocation
```python
from core.orchestrator import invoke_orchestrator

# Invoke orchestrator for user query
response = await invoke_orchestrator(
    user_query="Fix bug in main.py",
    input_method="text",
    conversation_history=[{"role": "user", "content": "Previous message"}],
    current_workspace="/Users/user/Workspace/project",
    bot_repository="/Users/user/Workspace/agentlab",
    workspace_path="/Users/user/Workspace",
    task_manager=task_manager,  # Optional: for active task context
    image_path=None,  # Optional: uploaded image
    session_id="uuid"  # Optional: for tracking
)

# Response format:
# - Direct answer (questions/chat): "The function does X and Y."
# - Background task: "BACKGROUND_TASK|Fix bug in main.py|Fixing the bug."
```

### Workflow Routing
```python
from core.routing import get_workflow_router

router = get_workflow_router()

# Route task to appropriate workflow
workflow_cmd = router.route_task("Fix authentication error")
# Returns: "/workflows:smart-fix"

workflow_cmd = router.route_task("Add user profile page")
# Returns: "/workflows:code-task"
```

## Dependencies

### Internal
- `tasks/manager.py` - Task tracking and lifecycle management
- `tasks/database.py` - SQLite backend for persistent storage
- `claude/code_cli.py` - Claude Code CLI subprocess management
- `messaging/formatter.py` - Telegram message formatting
- `utils/git.py` - Git repository operations and dirty state tracking

### External
- `python-telegram-bot` - Telegram Bot API client
- `anthropic` - Claude API client for routing
- `openai` - Whisper transcription for voice messages
- `asyncio` - Async/await for concurrent operations
- `dotenv` - Environment variable loading

## Architecture

### Message Flow
```
Telegram User
    ↓
main.py (command/message handler)
    ↓
orchestrator.py (invokes orchestrator agent via Claude Code CLI)
    ↓
    ├→ Direct response (questions/chat)
    │    └→ formatter.py → Telegram User
    └→ BACKGROUND_TASK format (coding tasks)
         └→ tasks/manager.py (background execution)
              └→ claude/code_cli.py (spawns code_agent)
```

### Session Flow
```
User Message → SessionManager.add_message()
    ↓
conversation_history stored in memory + data/sessions.json
    ↓
orchestrator receives last 3 messages as context
    ↓
response added to history → SessionManager.add_message()
```

### Configuration Hierarchy
```
Environment Variables (AGENTLAB_DB_PATH, AGENTLAB_DATA_DIR)
    ↓
config.py (defaults: data/agentlab.db, data/)
    ↓
All modules import from config.py (single source of truth)
```

## Cross-References

- **Database Schema**: See [docs/API.md](../docs/API.md#database-layer) for complete schema documentation
- **Task Management**: See [tasks/README.md](../tasks/README.md) for task lifecycle details
- **Claude Integration**: See [claude/README.md](../claude/README.md) for API/CLI usage patterns
- **Testing**: See [tests/README.md](../tests/README.md) for core module tests

## Key Patterns

### Fire-and-Forget Orchestrator
The orchestrator uses `start_new_session=True` to detach subprocess from parent, allowing the bot to remain responsive while Claude Code executes.

### Background Task Format
Orchestrator responses follow a strict format for task delegation:
```
BACKGROUND_TASK|<description>|<user_message>
```
Example: `BACKGROUND_TASK|Fix bug in auth.py|Fixing the authentication bug.`

### Voice Input Permissiveness
System prompts instruct agents to be permissive with voice transcription errors (e.g., "group therapy" → "groovetherapy").

### Cost Optimization
- Orchestrator uses Haiku 4.5 for routing (10x cheaper than Sonnet)
- Conversation history limited to last 3 messages
- Background tasks spawn Sonnet 4.5 agents for coding work

## Notes

- All file paths use `Path` objects internally, converted to strings for backward compatibility
- Session history never times out (removed in phase 2)
- Orchestrator runs from `bot_repository` to load agent configs from `.claude/agents/`
- Background tasks spawn from target workspace for proper file operations
