# Architecture Exploration Summary

Date: October 21, 2025
Focus: Understanding Telegram bot architecture for web chat replication

---

## Documents Created

### 1. TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md (26 KB)
Comprehensive deep-dive into the bot's design and implementation.

**Contents**:
- Executive summary of dual-model routing
- Detailed message flow from user input to response
- Component architecture (6 major sections):
  1. Message processing pipeline (main.py, message_queue.py, session.py)
  2. Routing engine (claude_api.py - Haiku)
  3. Task execution pipeline (tasks.py, agent_pool.py)
  4. Code execution (claude_interactive.py)
- Data flow architecture (sessions, tasks, costs)
- 6 key design patterns explained
- Security architecture
- Message response formatting
- Claude Code CLI integration
- Real-world message examples
- Monitoring & observability
- Key files reference table
- Conclusion: why this architecture works

**Audience**: Engineers wanting to understand the system deeply

**Key Insights**:
- Dual-model routing saves 10x on costs (80% via cheap Haiku)
- Per-user message queues prevent race conditions
- Bounded worker pool (max 3) prevents resource exhaustion
- Task-specific git branches enable safe parallel execution
- Session history limited to 10 messages for token efficiency

---

### 2. WEB_CHAT_REPLICATION_GUIDE.md (19 KB)
Practical guide for replicating the bot in a web interface.

**Contents**:
- Message flow comparison (Telegram vs Web)
- 6 core components to implement:
  1. API endpoint (POST /api/chat)
  2. WebSocket for real-time updates
  3. Message queue (reuse as-is)
  4. Session management (reuse as-is)
  5. Routing engine (reuse as-is)
  6. Task execution (reuse with WebSocket instead of Telegram)
- Web-specific considerations:
  - Authentication (JWT/session tokens)
  - Streaming responses (SSE or WebSocket)
  - Conversation UI (React/Vue example)
  - Background task display
  - File uploads
- Database and persistence (share with Telegram bot)
- Architecture diagram
- 4-phase migration path
- Key implementation files table
- Full Flask application structure (sample code)
- Replication checklist

**Audience**: Engineers building the web interface

**Key Insights**:
- Reuse ALL core modules from bot (message_queue, session, routing, tasks)
- Just add Flask frontend and WebSocket layer
- Share same database (agentlab.db, sessions.json)
- Users see same history in both Telegram and web
- Can run both Telegram bot and web chat simultaneously

---

## Architecture at a Glance

### Message Processing Pipeline
```
User Input
    ↓
Authorization + Rate Limiting
    ↓
Per-User Message Queue (sequential processing)
    ↓
Routing Decision (ask_claude via Haiku)
    ├─ 80%: DIRECT ANSWER (fast, cheap)
    └─ 20%: BACKGROUND_TASK (code work)
    ↓
Either:
  a) Send response immediately (Haiku path)
  b) Create task, queue to agent pool (Sonnet path)
    ↓
Response sent to user
```

### Core Components

| Component | Role | Can Reuse? |
|-----------|------|-----------|
| `message_queue.py` | Per-user sequential processing | YES - as-is |
| `session.py` | Conversation history | YES - as-is |
| `claude_api.py` | Haiku routing (ask_claude) | YES - as-is |
| `claude_interactive.py` | Sonnet code execution | YES - as-is |
| `agent_pool.py` | Bounded worker pool (max 3) | YES - as-is |
| `tasks.py` | Task management & lifecycle | YES - as-is |
| `database.py` | SQLite persistence | YES - as-is |
| `formatter.py` | Response formatting | ADAPT - Telegram → HTML |
| `main.py` | Telegram handlers | NEW - create web_handlers.py |

### Key Numbers

- **Message latency (Haiku)**: 1-2 seconds
- **Code task latency (Sonnet)**: 30-120 seconds
- **Cost per question**: ~$0.0001
- **Cost per code task**: ~$0.01-0.50
- **Rate limits**: 30 req/min, 500 req/hour per user
- **Bounded pool size**: 3 concurrent agents
- **Session history sent to Claude**: Last 10 messages
- **Message truncation**: 2000 chars per message

---

## Design Patterns Explained

### 1. Dual-Model Routing
Route 80% of work to cheap Haiku (questions, routing) and 20% to powerful Sonnet (code).
Result: 10x cost reduction compared to routing all to Sonnet.

### 2. Per-User Message Queuing
One queue per user ensures sequential processing, preventing race conditions in session state.
Result: Reliable, consistent state management.

### 3. Bounded Worker Pool
Fixed number of agents (3) with queueing prevents resource exhaustion.
Result: System stays responsive even under load.

### 4. Task-Specific Git Branching
Each task gets isolated branch (task/abc12345), enabling safe parallel execution.
Result: Multiple tasks can run simultaneously without interfering with each other.

### 5. Session Persistence with History Limits
Cache full history persistently, but only send last 10 messages to Claude API.
Result: Save 90% of tokens while maintaining full context.

### 6. Real-Time Monitoring with SSE
Server pushes updates to dashboard instead of polling.
Result: Responsive UI, minimal bandwidth.

---

## Message Flow Examples

### Example 1: Question (Direct Answer Path)
```
User: "What is Python?"
    ↓ ask_claude (Haiku)
    ↓ Routes as DIRECT_ANSWER
    ↓ "Python is a programming language..."
    ↓ Response sent to user
Timeline: 1-2 seconds
Cost: ~$0.0001
```

### Example 2: Code Task (Background Task Path)
```
User: "Fix the bug in main.py"
    ↓ ask_claude (Haiku)
    ↓ Routes as BACKGROUND_TASK
    ↓ Create task, queue to agent pool
    ↓ Agent becomes available
    ↓ Execute via Claude Code CLI (Sonnet)
    ↓ Read files, analyze, fix, test, commit
    ↓ User notified: "Task #abc123 completed"
    ↓ Results saved and displayed
Timeline: 30-120 seconds
Cost: ~$0.10-0.50
```

### Example 3: Log Analysis
```
User: "Check logs"
    ↓ ask_claude (Haiku)
    ↓ Routes as LOG_CHECKING
    ↓ Grep logs for ERROR|WARNING|CRITICAL
    ↓ Summarize issues (or "Logs clean")
    ↓ Response sent
Timeline: 1-2 seconds
Cost: ~$0.0001
```

---

## Security Measures

1. **Input Validation**
   - Detect prompt injection attempts
   - Sanitize XML special characters
   - Validate file paths (prevent traversal)

2. **Authorization**
   - User whitelist (ALLOWED_USERS env var)
   - Check on every request

3. **Rate Limiting**
   - 30 requests/minute per user
   - 500 requests/hour per user
   - Cooldown period if exceeded

4. **Cost Limits**
   - Track daily spending
   - Track monthly spending
   - Block requests if limit exceeded

5. **Secret Protection**
   - Pre-commit hooks prevent API key commits
   - No hardcoded secrets in code

---

## Database Schema

### Tasks (data/agentlab.db)
```
task_id (UUID)
user_id (int)
description (str)
status (pending, running, completed, failed, stopped)
workspace (str)
model (sonnet, opus)
agent_type (orchestrator, code_agent, etc.)
workflow (code-task, ui-task, research-task, etc.)
created_at (ISO timestamp)
updated_at (ISO timestamp)
pid (int, if running)
result (str, if completed)
error (str, if failed)
activity_log (list of progress updates)
```

### Sessions (data/sessions.json)
```json
{
  "user_id": {
    "user_id": int,
    "created_at": ISO timestamp,
    "last_activity": ISO timestamp,
    "history": [
      {
        "role": "user|assistant",
        "content": str,
        "timestamp": ISO timestamp
      }
    ],
    "current_workspace": str (optional)
  }
}
```

### Cost Tracking (data/cost_tracking.json)
```json
{
  "user_id": {
    "daily_cost": float,
    "monthly_cost": float,
    "total_cost": float,
    "model_breakdown": {
      "haiku": {
        "requests": int,
        "input_tokens": int,
        "output_tokens": int,
        "cost": float
      },
      "sonnet": { ... }
    }
  }
}
```

---

## Web Chat Implementation Roadmap

### Phase 1: Minimal (Week 1)
- [x] Understand architecture
- [ ] Create Flask app with /api/chat endpoint
- [ ] Connect to same message_queue
- [ ] Reuse session.py for history
- [ ] Call ask_claude for routing
- [ ] Stream response via WebSocket
- [ ] Basic React UI

**Result**: Users can chat, get Haiku responses, see history

### Phase 2: Full Task Support (Week 2)
- [ ] Reuse agent_pool for task execution
- [ ] Create tasks in shared database
- [ ] Stream task progress via WebSocket
- [ ] Display task status in UI
- [ ] Handle failed tasks

**Result**: Users can request code tasks, see them execute in real-time

### Phase 3: Integration (Week 3)
- [ ] Share database with Telegram bot
- [ ] Users see same history in both platforms
- [ ] Task status visible in both Telegram and web
- [ ] Cost tracking unified

**Result**: Multi-platform experience, consistent state

### Phase 4: Polish (Week 4)
- [ ] File uploads (images, documents)
- [ ] Code syntax highlighting
- [ ] Better error messages
- [ ] Performance optimization
- [ ] Mobile responsive design

**Result**: Production-ready web chat

---

## Key Takeaways for Web Implementation

1. **Architecture is Framework-Agnostic**
   - Core modules don't care about Telegram vs HTTP
   - Just need adapter layer (Flask, WebSocket)

2. **Reuse Existing Code**
   - 90% of bot logic is reusable
   - Don't rewrite message_queue, routing, task execution
   - Just add web frontend

3. **Share Database**
   - Users can switch platforms seamlessly
   - Same task history, same costs, same sessions
   - Single source of truth

4. **Real-Time Critical**
   - WebSocket or SSE for live updates
   - Users need to see task progress, not wait
   - Server-Sent Events better for one-way streaming

5. **Async Everything**
   - Telegram handlers are async
   - Agent pool is async
   - Message queue is async
   - Web handlers must also be async (use aiohttp or Flask async)

6. **Cost Optimization Preserved**
   - Haiku routing still applies (1-2s, cheap)
   - Sonnet for code tasks (slow, powerful)
   - Same token reduction strategies work
   - Cost limits still enforced

---

## Files to Reference

**Comprehensive Analysis**:
- `/Users/matifuentes/Workspace/agentlab/TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md`

**Implementation Guide**:
- `/Users/matifuentes/Workspace/agentlab/WEB_CHAT_REPLICATION_GUIDE.md`

**Source Code**:
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py` - Telegram handlers
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/message_queue.py` - Queueing
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/session.py` - History
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/claude_api.py` - Routing
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/tasks.py` - Task management
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/agent_pool.py` - Worker pool
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/claude_interactive.py` - Code execution
- `/Users/matifuentes/Workspace/agentlab/README.md` - Project overview
- `/Users/matifuentes/Workspace/agentlab/CLAUDE.md` - Development conventions

---

## Conclusion

The Telegram bot architecture is elegant and reusable. The core insight is **separation of concerns**:

1. **Routing layer** (ask_claude) - Framework independent
2. **Task management** (agent_pool, tasks) - Framework independent
3. **Session state** (session.py, message_queue.py) - Framework independent
4. **Frontend** (Telegram handlers vs Flask/React) - Framework dependent

To build the web chat:
1. Reuse layers 1-3 as-is (90% of code)
2. Create Flask/React frontend (10% new code)
3. Share database (zero changes to core modules)

**Estimated effort**: 1-2 weeks for Phase 1-2, with existing architecture doing 90% of the work.

