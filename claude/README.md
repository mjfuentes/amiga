# Claude

## Purpose

Claude AI integration layer — provides the native Agent SDK client for task execution, Python hook callbacks for observability and git safety, an agent definition loader, and a lightweight API client for question answering and routing.

## Components

### sdk_client.py

Primary Claude integration using `claude_agent_sdk.query()` directly. Replaces the legacy subprocess-based `code_cli.py`.

**Constants** (effort and budget defaults per task type):
```python
ORCHESTRATOR_EFFORT = "low"       # Haiku — cheap routing
ORCHESTRATOR_MAX_BUDGET = 0.50   # $0.50 cap per orchestration call
TASK_EFFORT = "high"             # Sonnet — full implementation reasoning
TASK_MAX_BUDGET = 5.0            # $5.00 cap per task
DEBUG_EFFORT = "max"             # Opus — maximum reasoning for deep debugging
DEBUG_MAX_BUDGET = 10.0          # $10.00 cap for debugging sessions
```

**ClaudeSDKSession** — single session wrapper:
- `execute_task(task_id, prompt, effort, max_budget_usd, use_worktree)` — runs async `query()` and streams messages
- `_build_options()` — builds `ClaudeAgentOptions` with effort, budget, worktree flag, and hooks
- `_find_project_root()` — resolves worktree symlinks so `PROJECT_ROOT` points at the real repo
- `cancel()` — signals cancellation via `asyncio.Event`

**ClaudeSDKPool** — concurrent session management:
- Semaphore-based concurrency (`max_concurrent=3`)
- `execute_task()` — acquires semaphore, creates session, returns `(success, result, session_id)`
- `cancel_task(task_id)` / `cancel_all()` — cancels running sessions by ID or all at once

**invoke_orchestrator_sdk()** — lightweight orchestrator invocation:
- Discovers repositories under `WORKSPACE_PATH`
- Builds prompt with task context and available repos
- Returns a routing decision in `BACKGROUND_TASK` format

**Message handling inside `query()` loop**:
- `ResultMessage` — final result; records cost, duration, and session ID to tracker
- `AssistantMessage` — per-turn content; fires optional `progress_callback`
- `SystemMessage` — session init and state; logs active tool count

### sdk_hooks.py

Python SDK callbacks replacing shell script hooks. Passed to `ClaudeAgentOptions(hooks=...)` by `sdk_client.py`.

**Safety guarantee**: Every callback is wrapped in `try/except`. An unhandled exception in a hook callback causes the SDK transport to emit `"Error in hook callback"` and terminate the stream — so no hook error is ever allowed to propagate.

**Hook types**:

| Hook | Trigger | What it does |
|------|---------|-------------|
| `PreToolUse` | Before any tool call | Records tool start in tracker; blocks dangerous git commands |
| `PostToolUse` | After any tool call | Records tool completion with success status |
| `Stop` | Session end | Records `session_ended` status change in tracker |

**Blocked git patterns** (`BLOCKED_GIT_PATTERNS`):
```python
("--no-verify", "Pre-commit hooks must not be skipped")
("push --force", "Force push is not allowed")
("push -f ",     "Force push is not allowed")
("reset --hard", "Hard reset is not allowed without confirmation")
```
Blocks are only checked on the `Bash` tool. Returning `{"decision": "block", "reason": "..."}` tells the SDK to refuse the tool call.

**`_safe_get(hook_input, key)`**: Handles `None` hook_input (SDK passes `None` when `request_data.get("input")` returns `None`). Calling `.get()` on `None` would crash the callback.

**`build_hooks(tracker, task_id)`**: Factory function — returns the full hooks dict for `ClaudeAgentOptions`:
```python
{
    "PreToolUse":  [HookMatcher(matcher=None, hooks=[pre_hook])],
    "PostToolUse": [HookMatcher(matcher=None, hooks=[post_hook])],
    "Stop":        [HookMatcher(matcher=None, hooks=[stop_hook])],
}
```
`matcher=None` means "match all tools" (the SDK default). Empty string `""` is not used because it may not match tool names correctly.

### agent_loader.py

Parses `.claude/agents/*.md` files into `AgentDefinition` instances for the Claude Agent SDK.

**Public API**:
```python
parse_agent_file(file_path: Path) -> tuple[str, AgentDefinition] | None
load_agents(agents_dir: Path) -> dict[str, AgentDefinition]
load_project_agents(project_root: Path | None = None) -> dict[str, AgentDefinition]
```

**File format** (YAML frontmatter + markdown body):
```yaml
---
name: code_agent
description: Implements Python and backend features
tools: Read,Glob,Grep,Bash,Edit,Write
model: sonnet
---
You are a backend implementation specialist...
```
- `name` and `description` are **required**; files missing either are skipped with a warning.
- `model` maps to `"inherit"`, `"sonnet"`, `"opus"`, or `"haiku"` via keyword matching.
- `tools` is parsed as a comma-separated list.
- The markdown body after the closing `---` becomes the agent system prompt.
- `CHANGELOG.md` is explicitly skipped (`_SKIP_FILES`).
- No `pyyaml` dependency — frontmatter is parsed with a regex + flat key-value loop.

**`load_project_agents(project_root)`**: Convenience wrapper that loads from `<project_root>/.claude/agents/`. Returns an empty dict if the directory does not exist.

### api_client.py

Lightweight Claude API client for question answering and routing decisions. Uses Haiku for fast, cheap responses.

- `ClaudeAPIClient`: Anthropic Messages API wrapper
- Input sanitization and prompt injection detection
- Context building (history, tasks, logs, repos)
- Background task format parsing (`BACKGROUND_TASK|description|message`)
- Cost tracking and token usage monitoring
- Streaming response support
- XML-safe content escaping

### code_cli.py

**Legacy** subprocess-based Claude Code CLI wrapper. Replaced by `sdk_client.py` for all new task execution. Retained for reference and backward compatibility.

- `ClaudeSessionPool` — manages concurrent `claude -p` subprocess sessions
- Process lifecycle management (spawn, monitor, kill)
- Fire-and-forget execution for background tasks

## Usage Examples

### SDK Session (primary path)

```python
from claude.sdk_client import ClaudeSDKSession, TASK_EFFORT, TASK_MAX_BUDGET
from pathlib import Path

session = ClaudeSDKSession(
    workspace=Path("/Users/user/Workspace/project"),
    model="sonnet",
    usage_tracker=tracker,
)

success, result, session_id = await session.execute_task(
    task_id="abc123",
    prompt="Fix the authentication bug in auth.py",
    effort=TASK_EFFORT,
    max_budget_usd=TASK_MAX_BUDGET,
    use_worktree=True,
)
# Returns: (True, "Fixed auth bug on line 42...", "session-uuid-...")
```

### SDK Pool (concurrent tasks)

```python
from claude.sdk_client import ClaudeSDKPool

pool = ClaudeSDKPool(max_concurrent=3, usage_tracker=tracker)

success, result, session_id = await pool.execute_task(
    task_id="abc123",
    task_description="Implement dark mode toggle",
    workspace=Path("/Users/user/Workspace/project"),
    model="sonnet",
    effort="high",
    max_budget_usd=5.0,
)

# Cancel a specific task
await pool.cancel_task("abc123")

# Cancel all active tasks
await pool.cancel_all()
```

### Building hooks

```python
from claude.sdk_hooks import build_hooks
from tasks.tracker import ToolUsageTracker

tracker = ToolUsageTracker(db)
hooks = build_hooks(tracker, task_id="abc123")
# Pass to ClaudeAgentOptions(hooks=hooks)
```

### Loading agent definitions

```python
from claude.agent_loader import load_project_agents
from pathlib import Path

agents = load_project_agents(Path("/Users/user/Workspace/project"))
# {"code_agent": AgentDefinition(...), "orchestrator": AgentDefinition(...), ...}

# Or load from an explicit directory
from claude.agent_loader import load_agents
agents = load_agents(Path(".claude/agents"))
```

### Claude API Client (routing/Q&A)

```python
from claude.api_client import ClaudeAPIClient

client = ClaudeAPIClient()

response = await client.query(
    user_query="What is the current task status?",
    conversation_history=[...],
    current_workspace="/Users/user/Workspace/project",
)

# Response types:
# 1. Direct answer:   "There are 3 active tasks..."
# 2. Background task: "BACKGROUND_TASK|Fix auth bug|Working on it..."
```

## Dependencies

### Internal
- `core/config.py` — configuration paths and environment variables
- `tasks/tracker.py` — tool usage tracking and session correlation
- `tasks/database.py` — database backend for cost/usage storage
- `utils/git.py` — git operations for workspace validation

### External
- `claude_agent_sdk` — Claude Agent SDK (`query`, `ClaudeAgentOptions`, `AgentDefinition`, hooks)
- `anthropic` — Anthropic Messages API (used by `api_client.py`)
- `asyncio` — async execution and cancellation

## Architecture

### SDK Session Flow

```
Task submitted (task_id, prompt, effort, budget)
    ↓
ClaudeSDKPool.execute_task() — acquire semaphore
    ↓
ClaudeSDKSession._build_options()
    ├── effort=high / max_budget_usd=5.0
    ├── --worktree flag (SDK creates git worktree)
    └── hooks = {PreToolUse, PostToolUse, Stop}
    ↓
claude_agent_sdk.query(prompt, options)
    ↓
SDK creates git worktree → routes to orchestrator agent
    ↓
loop (tool calls):
    ├── PreToolUse hook  → check blocked git patterns → record_tool_start()
    ├── Tool executes    (Read / Grep / Bash / Edit / Write)
    └── PostToolUse hook → record_tool_complete()
    ↓
Stop hook → record_status_change("session_ended")
    ↓
ResultMessage → record cost + session_id → update task status
    ↓
Release semaphore → return (success, result, session_id)
```

### Agent Loader Flow

```
.claude/agents/*.md
    ↓
_FRONTMATTER_PATTERN regex → split frontmatter + body
    ↓
_parse_frontmatter() → {name, description, model, tools}
    ↓
_parse_model() → "sonnet" | "opus" | "haiku" | "inherit"
_parse_tools() → ["Read", "Grep", "Bash", ...]
    ↓
AgentDefinition(description, prompt, tools, model)
    ↓
dict[str, AgentDefinition]   (keyed by agent name)
```

### Auth Flow (auth/middleware.py)

```
POST /api/auth/login
    ↓
init_auth_middleware(SECRET_KEY, session_manager)  ← called at server startup
    ↓
AuthMiddleware.generate_tokens(user_id)
    ├── JWT access token  (15-min expiry, HS256)
    └── session_manager.create_session() → refresh_token + session_id
    ↓
Response: {access_token, refresh_token, user}
    ↓
Subsequent requests: verify_access_token(token)
    ├── Decode JWT
    ├── Check session validity in SQLite
    └── Update session activity timestamp
```

## Security

### Git Safety (SDK Hooks)
Dangerous operations blocked at the `PreToolUse` hook level — before the Bash tool executes. Pattern list in `BLOCKED_GIT_PATTERNS`. Returning `{"decision": "block"}` prevents the tool call entirely.

### Prompt Injection Prevention (api_client.py)
- XML tag filtering and HTML entity escaping
- Instruction override detection
- Role manipulation blocking

### Environment Variable Isolation
Each SDK session receives only:
- `TASK_ID` — for hook correlation
- `PROJECT_ROOT` — resolved repo root (follows worktree symlink)

## Cost Optimization

| Tier | Model | Effort | Budget Cap | Use case |
|------|-------|--------|-----------|----------|
| Orchestrator | Haiku | `low` | $0.50 | Routing, delegation |
| Task | Sonnet | `high` | $5.00 | Implementation, coding |
| Debug | Opus | `max` | $10.00 | Deep debugging, root cause |

Effort and budget are set per-session in `ClaudeAgentOptions.extra_args` and enforced by the SDK.

## Cross-References

- **API Documentation**: See [docs/API.md](../docs/API.md) for REST endpoint details
- **Task Management**: See [tasks/README.md](../tasks/README.md) for background task lifecycle
- **Architecture**: See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) for system-wide design
- **Testing**: See [tests/README.md](../tests/README.md) for test coverage details
- **Agent Definitions**: See [../.claude/agents/](../.claude/agents/) for agent markdown files
