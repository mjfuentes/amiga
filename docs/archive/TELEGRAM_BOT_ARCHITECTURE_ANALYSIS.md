# Telegram Bot Architecture Analysis

## Executive Summary

The AMIGA (Autonomous Modular Interactive Graphical Agent) is a sophisticated Telegram bot that intelligently routes user requests between two Claude models:

1. **Claude API (Haiku 4.5)** - Fast, cheap Q&A routing via REST API
2. **Claude Code CLI (Sonnet 4.5)** - Full-featured code execution with file/git access

The architecture implements several key patterns:
- **Dual-model routing** for cost optimization
- **Per-user message queuing** for sequential processing
- **Background task execution** with bounded worker pool
- **Persistent sessions** with conversation history
- **Real-time monitoring** dashboard with SSE
- **Prompt injection protection** and security hardening

---

## Message Flow: From User Input to Response

### High-Level Flow

```
User sends message to Telegram
    ↓
Telegram webhook → main.py handler
    ↓
Authorization check
    ↓
Rate limiting check
    ↓
Message queued to user's message queue
    ↓
Queue processor picks up message
    ↓
Parallel Path 1 (FAST - Most Messages):
    Claude API (Haiku) routes the request
    ├─ DIRECT ANSWER → Send to user
    ├─ BACKGROUND_TASK → Create task, queue to agent pool
    └─ Both paths complete in <2 seconds
    ↓
Parallel Path 2 (BACKGROUND - Complex Tasks):
    Agent pool executes code task
    ├─ Creates task branch in git
    ├─ Runs orchestrator agent via Claude Code CLI
    ├─ Orchestrator delegates to sub-agents if needed
    ├─ Saves result to database
    └─ Notifies user when complete
```

### Detailed Message Flow with Components

```
TELEGRAM MESSAGE RECEIVED
├─ Handle /commands (priority, bypass queue)
│  ├─ /start → Clear session, send welcome
│  ├─ /clear → Clear history immediately
│  ├─ /status → Show task status
│  ├─ /restart → Graceful shutdown with restart
│  └─ [Other commands]
│
└─ Handle regular messages (queued)
   │
   ├─ 1. AUTHORIZATION
   │  └─ Check user ID against ALLOWED_USERS whitelist
   │
   ├─ 2. RATE LIMITING
   │  ├─ 30 requests/minute per user
   │  └─ 500 requests/hour per user
   │
   ├─ 3. COST CHECKING
   │  ├─ Daily limit (DAILY_COST_LIMIT env var)
   │  └─ Monthly limit (MONTHLY_COST_LIMIT env var)
   │
   ├─ 4. QUEUEING
   │  └─ Add to user's MessageQueue (per-user, sequential)
   │
   ├─ 5. ACKNOWLEDGMENT
   │  └─ Send "Thinking" message (deleted when response arrives)
   │
   └─ 6. ASYNC PROCESSING (handle_message → process_message_async)
      │
      ├─ ROUTING DECISION (ask_claude)
      │  │
      │  ├─ Option A: DIRECT ANSWER (most messages)
      │  │  ├─ Get session history (last 10 messages)
      │  │  ├─ Build context XML
      │  │  ├─ Call Claude Haiku API
      │  │  ├─ Response routing rules:
      │  │  │  ├─ Questions → Direct response
      │  │  │  ├─ Logs → Grep logs, summarize
      │  │  │  ├─ Chat → Conversational response
      │  │  │  └─ Code work → BACKGROUND_TASK format
      │  │  └─ Return (response_text, None, usage_info)
      │  │
      │  └─ Option B: BACKGROUND_TASK (code operations)
      │     └─ Return (user_message, task_info, usage_info)
      │        where task_info = {description, user_message, context}
      │
      ├─ CREATE TASK (if background_task_info not None)
      │  ├─ Resolve workspace to git repository
      │  ├─ Create Task record in database
      │  │  └─ Fields: task_id, user_id, description, context, workspace, model
      │  ├─ Submit to agent_pool with HIGH priority
      │  └─ Return immediate user message (e.g., "Task #abc123 started")
      │
      ├─ QUEUE SESSION WRITES (non-blocking)
      │  ├─ Queue user message to history
      │  └─ Queue assistant response to history
      │
      ├─ QUEUE COST TRACKING (non-blocking)
      │  ├─ Record input/output tokens
      │  └─ Update daily/monthly costs
      │
      └─ SEND RESPONSE
         ├─ If short: Send as HTML message
         └─ If long: Send summary + markdown attachment
```

---

## Component Architecture

### 1. Message Processing Pipeline

#### `main.py` - Entry Point & Command Handlers
**Role**: Telegram bot initialization, handler registration, command dispatch

**Key Functions**:
- `start_command()` - Clear session, show welcome
- `handle_message()` - Queue text messages
- `_handle_message_impl()` - Actual message processing (called from queue)
- `process_message_async()` - Background processing (calls ask_claude)
- `execute_code_task()` - Background task execution (agent pool worker)

**Handler Registration**:
```python
app.add_handler(CommandHandler("start", start_command))
app.add_handler(CommandHandler("clear", clear_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
```

**Priority vs Normal Messages**:
- Priority: `/start`, `/clear`, `/restart` (bypass queue, execute immediately)
- Normal: Text messages (queued per-user)

#### `message_queue.py` - Per-User Sequential Processing
**Role**: Ensure one message processes at a time per user (prevents race conditions)

**Architecture**:
```
MessageQueueManager
├─ user_queues: dict[user_id] → UserMessageQueue
│
UserMessageQueue (one per user)
├─ queue: asyncio.Queue (normal priority messages)
├─ priority_queue: list (high priority)
├─ processor_task: asyncio.Task (background worker)
└─ Methods:
   ├─ enqueue(): Add message to queue
   ├─ start_processor(): Start background worker
   └─ _process_queue(): Main loop that executes handlers one at a time
```

**Flow**:
1. `handle_message()` calls `queue_manager.enqueue_message()`
2. Message added to queue
3. Processor wakes up and executes `_handle_message_impl()`
4. Next message waits until current one completes
5. Ensures sequential processing per user

**Why needed**: 
- Telegram delivers messages fast
- Prevents concurrent API calls per user
- Ensures session history consistency
- Handles rate limits gracefully

#### `session.py` - Conversation History
**Role**: Store and retrieve user conversation history persistently

**Data Structure**:
```python
Session
├─ user_id: int
├─ created_at: str (ISO timestamp)
├─ last_activity: str (ISO timestamp)
├─ history: list[Message]
│  └─ Message: role (user/assistant), content, timestamp
└─ current_workspace: str (current git repo for tasks)

SessionManager
├─ data_dir: Path (data/)
├─ sessions_file: data/sessions.json (persistent storage)
├─ sessions: dict[user_id] → Session (in-memory cache)
└─ Methods:
   ├─ get_or_create_session()
   ├─ add_message()
   ├─ get_history(limit=10)
   ├─ clear_session()
   └─ set_workspace()
```

**Storage Format** (`data/sessions.json`):
```json
{
  "12345": {
    "user_id": 12345,
    "created_at": "2025-01-01T10:00:00",
    "last_activity": "2025-01-01T10:05:00",
    "history": [
      {
        "role": "user",
        "content": "What is Python?",
        "timestamp": "2025-01-01T10:00:00"
      },
      {
        "role": "assistant",
        "content": "Python is a programming language...",
        "timestamp": "2025-01-01T10:00:01"
      }
    ],
    "current_workspace": "/Users/matifuentes/Workspace/agentlab"
  }
}
```

**History Optimization**:
- Only last 10 messages sent to Claude API (save tokens)
- Messages truncated to 2000 chars (save tokens)
- Updated on every message (not batch)

### 2. Routing Engine

#### `claude_api.py` - Question Routing via Haiku
**Role**: Fast, cheap routing decision using Claude API

**Key Function**: `ask_claude()`

**Input**:
```python
user_query: str
input_method: str  # "voice" or "text"
conversation_history: list[dict]  # Last 10 messages
current_workspace: str | None
bot_repository: str
workspace_path: str
available_repositories: list[str]
active_tasks: list[dict]  # Last 3 pending/running tasks
image_path: str | None  # For image analysis
```

**Output**:
```python
(
  response_text: str,                    # Direct answer
  background_task_info: dict | None,     # Task info if background work needed
  usage_info: dict | None                # Token counts from API
)
```

**Decision Logic** (in system prompt):

| Input | Output | Example |
|-------|--------|---------|
| Question | Direct answer (2-3 sentences) | "What is Python?" → "Python is a..." |
| Chat | Conversational response | "Thanks!" → "You're welcome!" |
| Log check | Grep logs, summarize | "Check logs" → Parse ERROR/WARNING lines |
| Code work | BACKGROUND_TASK format | "Fix bug in main.py" → `BACKGROUND_TASK\|...\|...` |

**Security**:
```python
# 1. Prompt injection detection
detect_prompt_injection(user_query)  # Catch "ignore instructions" attempts

# 2. Input sanitization
sanitize_xml_content(text)  # HTML escape + remove dangerous patterns

# 3. File path validation
validate_file_path(image_path, base_path)  # Prevent directory traversal

# 4. Token reduction (cost optimization)
history[-10:]  # Last 10 messages only
tasks[:3]  # Max 3 active tasks
logs[-50:]  # Last 50 lines
```

**Cost**: ~$0.0001 per request (Haiku is very cheap)

### 3. Task Execution Pipeline

#### `tasks.py` - Task Management
**Role**: Create, track, and persist background tasks

**Task Lifecycle**:
```
Task Created
├─ user_id, description, workspace, model
├─ status = "pending"
├─ Saved to database (data/agentlab.db)
│
Task Queued
├─ Added to agent_pool queue
├─ Assigned priority (HIGH for user requests)
│
Task Execution (when agent available)
├─ Create task branch: task/{task_id[:8]}
├─ Run Claude Code CLI (orchestrator agent)
├─ Periodically log progress
├─ status = "running"
│
Task Complete
├─ Merge task branch to main
├─ Save result
├─ status = "completed"
├─ Notify user
│
[OR]
│
Task Failed
├─ Save error message
├─ status = "failed"
├─ Keep branch for debugging
├─ Notify user
```

**Task Data Structure**:
```python
Task
├─ task_id: str (UUID)
├─ user_id: int
├─ description: str (what to do)
├─ context: str | None (original user message + conversation context)
├─ status: str (pending, running, completed, failed, stopped)
├─ workspace: str (repository path)
├─ model: str (sonnet, opus)
├─ agent_type: str (orchestrator, code_agent, etc.)
├─ workflow: str | None (workflow used: code-task, research-task, etc.)
├─ created_at: str (ISO timestamp)
├─ updated_at: str (ISO timestamp)
├─ pid: int | None (process ID if running)
├─ result: str | None (output if completed)
├─ error: str | None (error if failed)
└─ activity_log: list[dict] (progress updates with timestamps)
```

**Database**: `data/agentlab.db` (SQLite3)
- Persistent storage
- Efficient querying
- Used by monitoring dashboard

**Methods**:
```python
create_task(user_id, description, workspace, model, context)
update_task(task_id, status, result, error, pid, workflow)
get_task(task_id)
get_user_tasks(user_id, limit=50)
get_active_tasks(user_id)
get_failed_tasks(user_id, limit=10)
```

#### `agent_pool.py` - Bounded Worker Pool
**Role**: Manage concurrent background task execution (max 3 agents)

**Architecture**:
```
AgentPool (max_agents=3)
├─ agents: list[asyncio.Task] (3 concurrent workers)
├─ task_queue: asyncio.PriorityQueue
│  └─ Format: (priority, counter, (task_func, args, kwargs))
└─ Methods:
   ├─ start() - Spawn agent tasks
   ├─ submit(task_func, *args, priority, **kwargs) - Queue work
   ├─ stop() - Graceful shutdown
   └─ _agent(agent_id) - Main loop per agent
```

**Priority Levels**:
```python
class TaskPriority(IntEnum):
    URGENT = 0   # Critical failures
    HIGH = 1     # User requests, interactive
    NORMAL = 2   # Background work (default)
    LOW = 3      # Maintenance, cleanup
```

**Flow**:
1. `submit(execute_code_task, task, priority=HIGH)` queued
2. Agent becomes available, dequeues from priority queue
3. Executes `await execute_code_task(task, update, context)`
4. Task completes, agent returns to queue
5. Next task dequeued

**Why bounded**:
- Prevents resource exhaustion (no unlimited threads)
- Claude Code CLI is heavyweight (high CPU/memory)
- Max 3 concurrent tasks reasonable compromise
- Queue remains responsive during spikes

### 4. Code Execution

#### `claude_interactive.py` - Claude Code CLI Integration
**Role**: Execute code tasks with full tool access (Read, Write, Edit, Bash, Glob, Grep)

**Key Class**: `ClaudeSessionPool`

**Methods**:
```python
execute_task(
    task_id: str,
    description: str,
    workspace: Path,
    bot_repo_path: str,
    model: str,
    context: str,
    pid_callback: Callable,      # Called when process starts
    progress_callback: Callable  # Called with status updates
) → (success, result, pid, workflow)
```

**Execution Flow**:

```
1. BUILD PROMPT
   ├─ Task context (bot code structure)
   ├─ User description
   ├─ Workspace path
   ├─ Conversation history
   └─ Workflow constraints

2. INVOKE CLAUDE CODE
   cmd = ["claude", "chat", "--model", "sonnet", "--permission-mode", "bypassPermissions"]
   Process started in workspace (can access files)

3. SEND PROMPT
   stdin → Full task prompt
   
4. MONITOR EXECUTION
   ├─ Poll stdout/stderr
   ├─ Track process PID
   ├─ Log tool usage
   ├─ Call progress_callback() periodically
   └─ Max timeout 300 seconds (5 minutes)

5. COLLECT RESULT
   stdout → Full response text
   
6. CLEANUP
   ├─ Terminate process if timeout
   ├─ Cleanup worktree if needed
   └─ Save result to database
```

**Workflow Enforcement**:
```
Claude Code can use SLASH COMMANDS:
├─ /git-merge - Handles git merge at end of task
├─ /code-task - Standard code implementation flow
├─ /ui-task - UI/UX development flow
├─ /research-task - Research & analysis flow
└─ etc.
```

**Security**:
- `--permission-mode bypassPermissions` - Auto-approve file operations
- Runs in subprocess (isolated)
- Process PID tracked for cleanup
- Prompt injection prevention (sanitized input)
- Task context validation

---

## Data Flow Architecture

### Session Data
```
User interaction
    ↓
Message added to Session.history
    ↓
Written to data/sessions.json
    ↓
Persisted across bot restarts
    ↓
Queried when rendering conversation context
```

### Task Data
```
Task created
    ↓
Inserted into data/agentlab.db
    ↓
Referenced in subsequent queries
    ↓
Updated as task progresses
    ↓
Results stored when complete
    ↓
Retrieved for /status, /view commands
    ↓
Dashboard queries for monitoring
```

### Cost Tracking
```
API request made
    ↓
Token counts recorded (input + output)
    ↓
Stored in data/cost_tracking.json
    ↓
Daily/monthly totals calculated
    ↓
Checked against DAILY_COST_LIMIT, MONTHLY_COST_LIMIT
    ↓
Displayed in /usage command
```

---

## Key Design Patterns

### 1. Dual-Model Routing
**Problem**: Claude API and Claude Code CLI have different strengths
- API: Fast, cheap, stateless, great for Q&A
- CLI: Full tool access, stateful, expensive, great for coding

**Solution**: Route at message time
- 80%+ messages → Claude API (Haiku, <2s, cheap)
- 20%- messages → Claude Code CLI (Sonnet, >5s, expensive)

**Result**: 10x cost reduction, better UX

### 2. Per-User Message Queuing
**Problem**: Multiple messages arrive simultaneously, race conditions in state
- Two messages try to update session history
- Two messages create tasks simultaneously
- State gets corrupted

**Solution**: One queue per user, processes messages sequentially
- Message 1 processed fully (session updated, cost tracked)
- Message 2 waits for Message 1 to finish
- No race conditions, consistent state

### 3. Bounded Worker Pool
**Problem**: Background tasks can pile up, overwhelming system
- 100 tasks queued, 100 Claude processes running
- System crashes from resource exhaustion

**Solution**: Max 3 concurrent agents, rest queue
- Tasks queue quickly (non-blocking)
- Only 3 processes run at once
- Fair FIFO within same priority

### 4. Task-Specific Git Branching
**Problem**: Multiple tasks running in same repo could interfere
- Task 1 makes changes
- Task 2 makes conflicting changes
- Repo gets corrupted

**Solution**: Each task gets isolated branch
- Task 1 → `task/abc12345` branch
- Task 2 → `task/def67890` branch
- Parallel execution safe
- Branches merged when complete (or preserved if failed for debugging)

### 5. Session Persistence with History Limits
**Problem**: Conversation grows unbounded, tokens waste away
- 1000 messages in history
- Each API call includes all 1000 messages
- Massive token waste, slow queries

**Solution**: Only send last 10 messages to Claude
- Cache full history in sessions.json
- Truncate to 10 messages for context
- Save 90%+ of tokens on queries

### 6. Real-Time Monitoring with Server-Sent Events (SSE)
**Problem**: Dashboard polling for updates wastes resources
- Request every 1 second: 86,400 requests/day
- Lots of HTTP overhead

**Solution**: Server-Sent Events (streaming)
- Server pushes updates to dashboard
- Dashboard receives updates in real-time
- Minimal bandwidth, responsive UI

---

## Security Architecture

### Input Validation
```python
# 1. Prompt Injection Detection
detect_prompt_injection(user_query)
├─ Detect "ignore instructions"
├─ Detect "system:"
├─ Detect "[INST]" markers
└─ Detect excessive XML tags

# 2. Input Sanitization
sanitize_xml_content(text)
├─ HTML escape special characters
├─ Remove dangerous patterns
└─ Safe for inclusion in XML prompts

# 3. File Path Validation
validate_file_path(path, base_path)
├─ Prevent directory traversal (..)
├─ Restrict to base directory
└─ Validate paths exist and accessible

# 4. Task Description Validation
validate_task_description(description)
├─ Check length (<5000 chars)
├─ Detect injection attempts
└─ Ensure valid format
```

### Authorization
```python
# User Whitelist
ALLOWED_USERS = [int(uid) for uid in os.getenv("ALLOWED_USERS", "").split(",")]

# Check on every message
if user_id not in ALLOWED_USERS:
    return "Unauthorized"
```

### Rate Limiting
```python
RateLimiter
├─ 30 requests per minute per user
├─ 500 requests per hour per user
├─ Cooldown period if exceeded
└─ Checked before processing each message
```

### Cost Limits
```python
CostTracker
├─ Track daily spending
├─ Track monthly spending
├─ Check against DAILY_COST_LIMIT
├─ Check against MONTHLY_COST_LIMIT
└─ Block requests if exceeded
```

### Secret Protection
```
Pre-commit hooks prevent:
├─ API keys in code
├─ Secrets in commits
├─ Large files
└─ Sensitive patterns
```

---

## Message Response Formatting

### `formatter.py` - Telegram HTML Formatting
**Role**: Convert plain text responses to rich HTML for Telegram

**Processing Pipeline**:
```
Plain text response
    ↓
Extract code blocks (preserve formatting)
    ↓
HTML escape special characters
    ↓
Restore code blocks with <pre> tags
    ↓
Format file paths with <code> tags
    ↓
Format repository names with <b> tags
    ↓
Format lists with proper indentation
    ↓
Split into 4096-char chunks (Telegram limit)
    ↓
Send each chunk as separate message
```

**Example**:
```
Input:
"Fix the bug in /Users/matifuentes/Workspace/agentlab/main.py
```python
def hello():
    print('Hello')
```"

Output HTML:
"Fix the bug in <code>/Users/matifuentes/Workspace/agentlab/main.py</code>
<pre>def hello():
    print('Hello')</pre>"
```

### Long Response Handling
**Problem**: Telegram message limit is 4096 characters

**Solution**: Multi-mode sending
```
If response < 4096 chars:
    └─ Send as single message

If response >= 4096 chars:
    └─ Send as markdown document attachment
       ├─ Summary message (inline)
       └─ Full response (attached file)
```

**Example**:
- Task completes with 50KB output
- User gets: "Task Complete #abc123 ... (attached file)"
- Document: task_abc123_result.md (full output)

---

## Integration with Claude Code CLI

### Orchestrator Pattern
```
User message "Fix bug in main.py"
    ↓
Haiku (ask_claude) routes to BACKGROUND_TASK
    ↓
Task created, queued to agent pool
    ↓
Agent executes via orchestrator agent
    ↓
Orchestrator via Claude Code CLI:
    ├─ Reads code files (Glob, Read, Grep)
    ├─ Analyzes problem
    ├─ Implements fix (Write, Edit)
    ├─ Runs tests (Bash)
    ├─ Commits changes (Bash git)
    └─ Returns summary
    ↓
Result stored in database
    ↓
User notified
```

### Agent Delegation
Orchestrator can invoke sub-agents:
```
orchestrator.md (Sonnet)
├─ Routes and coordinates
├─ May delegate to code_agent for implementations
├─ May delegate to frontend_agent for UI work
├─ May delegate to research_agent for analysis
└─ Returns task completion summary
```

---

## Comparison: API vs CLI Routes

| Aspect | Claude API (Haiku) | Claude Code CLI (Sonnet) |
|--------|-------------------|------------------------|
| **Model** | Haiku 4.5 | Sonnet 4.5 |
| **Speed** | 1-2 seconds | 5-60 seconds |
| **Cost** | ~$0.0001 per req | ~$0.01-1.00 per req |
| **Tool Access** | None (REST API) | Full: Read, Write, Edit, Bash, Grep, Glob |
| **File Access** | No | Yes (code execution) |
| **Git Integration** | No | Yes (can commit) |
| **Use Cases** | Questions, chat, routing | Code changes, refactoring, features |
| **Response Type** | Direct text | Can create/modify files |
| **Token Limit** | 4096 output | Unlimited (can stream) |
| **Session State** | None | Stateful (task branches, sessions) |

---

## Real-World Message Examples

### Example 1: Simple Question (Direct Answer)
```
User: "What is the difference between Python lists and tuples?"

Flow:
1. Haiku routes as DIRECT ANSWER (knowledge question)
2. Returns explanation
3. Added to session history
4. User sees response in 1-2 seconds

Cost: ~$0.0001
```

### Example 2: Code Task
```
User: "Fix the bug in main.py where tasks aren't being queued properly"

Flow:
1. Haiku routes as BACKGROUND_TASK
2. Task created: "Fix task queueing bug in main.py"
3. Added to agent pool (HIGH priority)
4. Agent becomes available
5. Orchestrator reads main.py, analyzes bug
6. Writes fix, runs tests
7. Commits changes to task branch
8. Merges to main
9. User notified: "Task #abc123 completed"
10. Full output saved to markdown document

Cost: ~$0.10-0.50
Timeline: 30-120 seconds
```

### Example 3: Log Analysis
```
User: "Check logs"

Flow:
1. Haiku routes as LOG CHECKING
2. Greps logs/bot.log for ERROR|WARNING|CRITICAL|Exception|Traceback
3. Summarizes issues (or "Logs clean")
4. Returns 3-4 sentences

Cost: ~$0.0001
Timeline: 1-2 seconds
```

### Example 4: Voice Input (with Whisper Transcription)
```
User: Sends voice note "Add a new command called slash get status"

Flow:
1. Download audio file
2. Whisper transcribes: "Add a new command called slash get status"
3. Route as BACKGROUND_TASK (code work)
4. Same as Example 2...

Cost: Transcription (free locally) + Sonnet task
Timeline: 2-3 seconds (transcription) + 30-60 seconds (task)
```

---

## Monitoring & Observability

### Logging Strategy
```
DEBUG: Detailed flow, tool calls, state changes
INFO: User actions, task lifecycle, API calls
WARNING: Recoverable issues, rate limits, retries
ERROR: Failures, exceptions, blocked operations

File: logs/bot.log (rotated automatically)
Queried by: /status command, dashboard, log analysis
```

### Dashboard (monitoring_server.py)
Real-time web dashboard at http://localhost:3000 shows:
```
Running Tasks
├─ Task ID, description, status
├─ Click to view tool usage live
└─ Progress timeline

Recent Errors
├─ Task ID, error message
├─ Timestamp
└─ Link to full error

24h API Costs
├─ Per model (Haiku, Sonnet)
├─ Daily total
└─ Progress toward limit

Tool Usage Stats
├─ Read/Write/Edit/Bash/Grep/Glob counts
├─ Most used tools
└─ Error rates per tool
```

**Technology**: Flask + SSE (Server-Sent Events)
- Server pushes updates to browser
- Real-time without polling
- Dashboard reads from hooks data and database

### Hook System
Claude Code CLI Hooks (in ~/.claude/hooks/):
```
pre-tool-use.sh → Logs before tool execution
post-tool-use.sh → Logs results/errors after execution
session-end.sh → Aggregates session summary

Output:
├─ JSONL logs (raw data)
├─ JSON databases (parsed data)
└─ Read by Python: hooks_reader.py
```

---

## Key Files Reference

| File | Responsibility |
|------|-----------------|
| `main.py` | Entry point, handlers, routing logic |
| `message_queue.py` | Per-user sequential message processing |
| `session.py` | Conversation history management |
| `claude_api.py` | Haiku routing via Anthropic API |
| `claude_interactive.py` | Sonnet execution via Claude Code CLI |
| `tasks.py` | Task creation, tracking, lifecycle |
| `agent_pool.py` | Bounded worker pool (max 3 concurrent) |
| `database.py` | SQLite persistence (tasks, metrics) |
| `formatter.py` | Telegram HTML formatting |
| `cost_tracker.py` | API usage tracking and limits |
| `rate_limiter.py` | Rate limiting (30/min, 500/hour) |
| `monitoring_server.py` | Flask web dashboard with SSE |
| `metrics_aggregator.py` | Real-time metrics from hooks |
| `orchestrator.py` | Orchestrator agent invocation |

---

## Conclusion: Why This Architecture Works

1. **Cost Optimization**: 80% of work handled by cheap Haiku → 10x savings
2. **Responsiveness**: Messages queued, Haiku responds in <2s, user sees immediate feedback
3. **Scalability**: Bounded worker pool prevents resource exhaustion
4. **Reliability**: Task branches ensure parallel work doesn't interfere
5. **Debuggability**: Comprehensive logging and persistent task history
6. **Security**: Multi-layer validation, rate limiting, cost limits
7. **UX**: Real-time dashboard, progress tracking, detailed results

The architecture prioritizes:
- **Isolation**: Per-user queues, task branches, bounded pools
- **Efficiency**: History limits, token reduction, multi-model routing
- **Resilience**: Persistent storage, task retries, graceful degradation
- **Observability**: Logging, dashboard, metrics, hooks

