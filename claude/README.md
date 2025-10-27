# Claude

## Purpose
Claude AI integration layer providing direct API client for question answering and CLI subprocess management for coding tasks.

## Components

### api_client.py
Claude API client for question answering and routing decisions.
- `ClaudeAPIClient`: Anthropic Messages API wrapper
- Input sanitization and prompt injection detection
- Context building (history, tasks, logs, repos)
- Background task format parsing (`BACKGROUND_TASK|description|message`)
- Cost tracking and token usage monitoring
- Streaming response support
- XML-safe content escaping

### code_cli.py
Claude Code CLI subprocess management for coding tasks.
- `ClaudeSessionPool`: manages concurrent Claude Code sessions
- Session isolation and cleanup
- Process lifecycle management (spawn, monitor, kill)
- Tool usage tracking via hooks integration
- Timeout handling (default: 5 minutes)
- Session UUID correlation for log analysis
- Fire-and-forget execution for background tasks

## Usage Examples

### Claude API Client
```python
from claude.api_client import ClaudeAPIClient

client = ClaudeAPIClient()

# Simple query
response = await client.query(
    user_query="What is recursion?",
    conversation_history=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How can I help?"}
    ],
    current_workspace="/Users/user/Workspace/project"
)

# Response types:
# 1. Direct answer: "Recursion is a programming technique..."
# 2. Background task: "BACKGROUND_TASK|Explain recursion with code|Let me show you."

# Parse background task response
if response.startswith("BACKGROUND_TASK|"):
    parts = response.split("|")
    task_description = parts[1]  # "Explain recursion with code"
    user_message = parts[2]      # "Let me show you."
```

### Input Sanitization
```python
from claude.api_client import sanitize_xml_content, detect_prompt_injection

# Sanitize user input before API call
safe_input = sanitize_xml_content(user_input)
# Escapes HTML entities, removes XML tags, strips dangerous patterns

# Detect prompt injection attempts
is_malicious, reason = detect_prompt_injection(user_input)
if is_malicious:
    print(f"Blocked: {reason}")
    # e.g., "Instruction override attempt"
```

### Claude Code CLI Session Pool
```python
from claude.code_cli import ClaudeSessionPool

# Initialize pool
pool = ClaudeSessionPool(max_concurrent=3, usage_tracker=tracker)

# Execute task
result = await pool.execute_task(
    task_id="abc123",
    task_description="Fix authentication bug",
    workspace="/Users/user/Workspace/project",
    agent_type="code_agent",
    model="sonnet",
    timeout=300  # 5 minutes
)

# Result format:
# {
#     "success": True,
#     "output": "Fixed authentication bug in auth.py:42",
#     "error": None,
#     "session_uuid": "550e8400-e29b-41d4-a716-446655440000"
# }

# Get pool status
status = pool.get_status()
# {
#     "active_sessions": 2,
#     "max_concurrent": 3,
#     "available_slots": 1
# }

# Graceful shutdown
await pool.shutdown()
```

### Cost Tracking
```python
from claude.api_client import ClaudeAPIClient

client = ClaudeAPIClient()

# Query with cost tracking
response = await client.query(user_query="Hello")

# Get token usage from last request
usage = client.get_last_usage()
# {
#     "input_tokens": 120,
#     "output_tokens": 45,
#     "cache_creation_tokens": 0,
#     "cache_read_tokens": 80,
#     "total_cost": 0.0023  # USD
# }

# Get session total
total_cost = client.get_session_cost()
# 0.156  # USD (cumulative for session)
```

## Dependencies

### Internal
- `core/config.py` - Configuration paths and environment variables
- `tasks/tracker.py` - Tool usage tracking for session correlation
- `tasks/database.py` - Database backend for cost/usage storage
- `utils/git.py` - Git operations for workspace validation

### External
- `anthropic` - Official Anthropic Python SDK
- `asyncio` - Async subprocess management
- `subprocess` - Process spawning for Claude Code CLI
- `json` - Response parsing and context serialization

## Architecture

### API Client Flow
```
User Query
    ↓
sanitize_xml_content() + detect_prompt_injection()
    ↓
Build context (history, tasks, logs, repos)
    ↓
Anthropic Messages API (Haiku 4.5 for routing)
    ↓
Parse response format:
    ↓
    ├→ Direct answer → return to user
    └→ BACKGROUND_TASK → create task + spawn agent
```

### CLI Session Pool Flow
```
Task submitted to pool
    ↓
Check available slots (max_concurrent=3)
    ↓ (if available)
Spawn subprocess: claude chat --model sonnet
    ↓
Set environment vars (CLAUDE_AGENT_NAME, SESSION_ID)
    ↓
Hooks record tool usage → database.tool_usage
    ↓
Wait for completion (timeout: 5 min)
    ↓
Collect output + session_uuid
    ↓
Return result to task manager
```

### Session UUID Correlation
```
ClaudeSessionPool.execute_task()
    ↓
Generate session_uuid (full UUID)
    ↓
Set SESSION_ID env var for hooks
    ↓
Hooks write to logs/sessions/<session_uuid>/
    ↓
Tool usage records include session_uuid
    ↓
Analytics can correlate: task → session → tool usage
```

## Cross-References

- **API Documentation**: See [docs/API.md](../docs/API.md) for cost tracking and token usage details
- **Task Management**: See [tasks/README.md](../tasks/README.md) for background task execution
- **Hook System**: See [monitoring/README.md](../monitoring/README.md) for tool usage tracking
- **Testing**: See [tests/README.md](../tests/README.md) for API client tests

## Key Patterns

### Background Task Format
Strict format for task delegation:
```
BACKGROUND_TASK|<description>|<user_message>
```
- `description`: Internal task context (what needs doing)
- `user_message`: Immediate feedback to user

Example:
```
BACKGROUND_TASK|Fix authentication bug in auth.py|Fixing the authentication issue.
```

### Input Sanitization Pipeline
1. HTML entity escape (`<` → `&lt;`, etc.)
2. Remove dangerous XML patterns (`</role>`, `[INST]`, etc.)
3. Check for prompt injection attempts
4. Log and block if malicious

### Cost Optimization
API client minimizes token usage:
- History: Last 2 messages only, 500 chars each
- Logs: Last 50 lines only
- Tasks: Max 3 active tasks, no descriptions
- Repos: Omit full list (saves ~100 tokens)

### Fire-and-Forget Execution
CLI sessions detach from parent process:
```python
process = await asyncio.create_subprocess_exec(
    *cmd,
    start_new_session=True  # Detach from parent
)
```
Allows bot to remain responsive during long-running tasks.

### Session Isolation
Each task gets dedicated Claude Code session:
- Independent working directory
- Isolated environment variables
- Separate log files
- No cross-task state leakage

## Model Selection

### Haiku 4.5 (API Client)
- Use case: Question answering, routing decisions
- Speed: 1-2 seconds
- Cost: ~$0.001 per request
- Context: 8K tokens

### Sonnet 4.5 (CLI Sessions)
- Use case: Coding tasks, file operations
- Speed: 5-60 seconds
- Cost: ~$0.01-0.10 per task
- Context: 200K tokens

### Opus 4.5 (Reserved)
- Use case: Research, deep debugging (research_agent, ultrathink-debugger)
- Speed: 30-300 seconds
- Cost: ~$0.50-5.00 per task
- Context: 200K tokens

## Security

### Prompt Injection Prevention
- XML tag filtering
- Instruction override detection
- Role manipulation blocking
- Excessive content length limits

### Safe XML Escaping
All user input escaped before embedding in prompts:
```python
safe_input = html.escape(text, quote=True)
```

### Environment Variable Isolation
Each session gets clean environment with only necessary vars:
- `ANTHROPIC_API_KEY`
- `CLAUDE_AGENT_NAME`
- `SESSION_ID`

## Performance Considerations

### Connection Pooling
API client reuses `anthropic.Anthropic()` instance, avoiding handshake overhead.

### Streaming Responses
API client supports streaming for real-time feedback (not yet implemented in bot).

### Timeout Handling
CLI sessions timeout after 5 minutes (configurable):
- Prevents hung processes
- Logs timeout errors
- Cleans up zombie processes

### Concurrent Session Limits
Pool limits concurrent sessions (default: 3):
- Prevents resource exhaustion
- Rate limit compliance
- Predictable performance

## Notes

- API client uses Messages API (not legacy Completions API)
- CLI sessions run from target workspace for correct file paths
- Session UUIDs are full UUIDs (not shortened like task IDs)
- Background task format parsing is lenient (strips markdown code blocks)
- Cost tracking includes prompt caching (cache_read_tokens)
- Hooks automatically enabled if `.claude/hooks/` directory exists
- Process cleanup uses `SIGTERM` first, then `SIGKILL` if unresponsive
