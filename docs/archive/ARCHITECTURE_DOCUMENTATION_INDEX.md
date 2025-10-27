# Architecture Documentation Index

Complete analysis of the AMIGA (Autonomous Modular Interactive Graphical Agent) Telegram bot architecture with guidance for replicating in a web chat interface.

---

## Quick Navigation

### For Quick Understanding
Start here: **ARCHITECTURE_EXPLORATION_SUMMARY.md** (5 min read)
- Architecture at a glance
- Key numbers and metrics
- Design patterns explained
- Implementation roadmap

### For Deep Technical Understanding
Read: **TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md** (30 min read)
- Complete message flow breakdown
- Component architecture (all 6 systems)
- Data flow details
- Security architecture
- Real-world examples

### For Web Chat Implementation
Read: **WEB_CHAT_REPLICATION_GUIDE.md** (20 min read)
- Message flow comparison (Telegram vs Web)
- 6 components to implement
- Web-specific considerations
- Full Flask sample code
- Replication checklist

---

## Document Overview

### ARCHITECTURE_EXPLORATION_SUMMARY.md (11 KB, 396 lines)
**Purpose**: Executive summary and orientation guide

**Sections**:
1. Documents overview (what was created and why)
2. Architecture at a glance (message pipeline, components)
3. Key numbers (latency, cost, limits)
4. Design patterns (6 main patterns explained)
5. Message flow examples (3 real scenarios)
6. Security measures (5 security layers)
7. Database schema (3 data stores)
8. Web chat roadmap (4 phases)
9. Key takeaways (6 insights)
10. Files to reference (with links)
11. Conclusion (reusability insight)

**Best for**: Getting oriented, understanding what's reusable

---

### TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md (26 KB, 936 lines)
**Purpose**: Comprehensive technical analysis of the entire bot architecture

**Sections**:
1. Executive summary
2. Message flow (high-level to detailed breakdown)
3. Component architecture (6 major systems):
   - Message processing pipeline (main.py, message_queue.py, session.py)
   - Routing engine (claude_api.py - Haiku)
   - Task execution pipeline (tasks.py, agent_pool.py)
   - Code execution (claude_interactive.py)
   - Response formatting (formatter.py)
   - Monitoring & observability
4. Data flow architecture (3 major data stores)
5. Key design patterns (6 patterns with problems/solutions)
6. Security architecture (5 security layers)
7. Message response formatting
8. Claude Code CLI integration
9. Comparison: API vs CLI routes
10. Real-world message examples (4 examples)
11. Monitoring & observability
12. Key files reference table
13. Conclusion: why this architecture works

**Best for**: Understanding how everything works together, design decisions

---

### WEB_CHAT_REPLICATION_GUIDE.md (19 KB, 723 lines)
**Purpose**: Practical implementation guide for building a web chat interface

**Sections**:
1. Message flow comparison (Telegram vs Web)
2. Core components to implement (6 components):
   - API endpoint (POST /api/chat)
   - WebSocket for real-time updates
   - Message queue (reuse as-is)
   - Session management (reuse as-is)
   - Routing engine (reuse as-is)
   - Task execution (reuse with WebSocket adapter)
3. Web-specific considerations (6 topics)
4. Database and persistence (share with Telegram bot)
5. Full architecture diagram
6. Migration path (4 phases)
7. Key implementation files table
8. Full Flask application structure (sample code)
9. Replication checklist

**Best for**: Actually building the web chat, code examples

---

## Key Insights

### 1. Reusability
**90% of bot logic is reusable** across Telegram and web:
- Message queue: Reuse as-is
- Session management: Reuse as-is
- Routing (ask_claude): Reuse as-is
- Task execution: Reuse as-is
- Database layer: Reuse as-is

Only need to write:
- Flask HTTP handlers (10% new code)
- WebSocket adapters (10% new code)

### 2. Shared Database
Both Telegram bot and web chat can access same database:
- `data/agentlab.db` - Tasks
- `data/sessions.json` - Conversation history
- `data/cost_tracking.json` - API costs

Users see same history and tasks in both platforms.

### 3. Architecture Patterns
Six core patterns that enable this reusability:

1. **Dual-Model Routing**: 80% questions (cheap Haiku) + 20% code (powerful Sonnet)
2. **Per-User Queuing**: Sequential processing prevents race conditions
3. **Bounded Worker Pool**: Max 3 concurrent agents prevent resource exhaustion
4. **Task Branching**: Each task gets isolated git branch for safe parallelism
5. **History Limits**: Cache full history, send last 10 messages to Claude
6. **Real-Time Monitoring**: Server-Sent Events for responsive dashboards

### 4. Cost Optimization
Original design saves **10x on API costs**:
- 80% of queries via cheap Haiku (~$0.0001 each)
- 20% of queries via powerful Sonnet (~$0.01-1.00 each)
- Same optimization applies to web chat

### 5. Security Architecture
Five layers of protection:
1. Input validation (prompt injection detection, sanitization)
2. Authorization (user whitelist)
3. Rate limiting (30/min, 500/hour)
4. Cost limits (daily/monthly caps)
5. Secret protection (pre-commit hooks)

---

## Message Flow: The Essence

```
User Input
    ↓
Authorization + Rate Limiting
    ↓
Per-User Message Queue (one at a time)
    ↓
ask_claude() routes via Haiku
    ├─ 80%: DIRECT_ANSWER (1-2 sec, cheap)
    └─ 20%: BACKGROUND_TASK (30-120 sec, powerful)
    ↓
Either:
  A) Send response immediately
  B) Create task → Queue to agent pool → Execute via Sonnet
    ↓
Response sent to user
```

---

## Implementation Checklist

### Phase 1: Minimal Web Chat (Week 1)
- [ ] Read ARCHITECTURE_EXPLORATION_SUMMARY.md
- [ ] Read WEB_CHAT_REPLICATION_GUIDE.md Section 1-2
- [ ] Create Flask app with `/api/chat` endpoint
- [ ] Connect to shared `message_queue.py`
- [ ] Connect to shared `session.py`
- [ ] Call `ask_claude()` for routing
- [ ] Add WebSocket for real-time response
- [ ] Build basic React chat UI
- [ ] Test with Haiku queries

**Result**: Users can chat, see history, get Q&A responses

### Phase 2: Full Task Support (Week 2)
- [ ] Read WEB_CHAT_REPLICATION_GUIDE.md Section 3
- [ ] Connect to shared `agent_pool.py`
- [ ] Connect to shared `tasks.py` and `database.py`
- [ ] Handle BACKGROUND_TASK responses
- [ ] Create tasks in shared database
- [ ] Queue to agent pool with HIGH priority
- [ ] Stream task progress via WebSocket
- [ ] Display task status in UI

**Result**: Users can request code tasks, see real-time execution

### Phase 3: Database Integration (Week 3)
- [ ] Verify both Telegram bot and web app use same DB files
- [ ] Test task visibility in both platforms
- [ ] Test history visibility in both platforms
- [ ] Verify cost tracking unified
- [ ] Test user can switch platforms mid-conversation

**Result**: Seamless multi-platform experience

### Phase 4: Polish (Week 4)
- [ ] Read TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md for security details
- [ ] Add file upload support
- [ ] Add code syntax highlighting
- [ ] Add better error messages
- [ ] Optimize performance
- [ ] Mobile responsive design
- [ ] Run monitoring dashboard

**Result**: Production-ready web chat

---

## File References

### Source Code (Telegram Bot)
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py` - Entry point, handlers
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/message_queue.py` - Per-user queueing
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/session.py` - Conversation history
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/claude_api.py` - Routing (Haiku)
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/tasks.py` - Task management
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/agent_pool.py` - Worker pool
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/claude_interactive.py` - Code execution
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/database.py` - SQLite persistence
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/formatter.py` - Response formatting

### Configuration Files
- `/Users/matifuentes/Workspace/agentlab/README.md` - Project overview
- `/Users/matifuentes/Workspace/agentlab/CLAUDE.md` - Development conventions
- `/Users/matifuentes/Workspace/agentlab/.env.example` - Environment setup

### Documentation (This Analysis)
- `/Users/matifuentes/Workspace/agentlab/ARCHITECTURE_EXPLORATION_SUMMARY.md` - You are here
- `/Users/matifuentes/Workspace/agentlab/TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md` - Deep dive
- `/Users/matifuentes/Workspace/agentlab/WEB_CHAT_REPLICATION_GUIDE.md` - Implementation guide
- `/Users/matifuentes/Workspace/agentlab/ARCHITECTURE_DOCUMENTATION_INDEX.md` - This file

---

## Quick Reference: Component Reusability

| Component | Module | Reusable? | Changes |
|-----------|--------|-----------|---------|
| Message queueing | `message_queue.py` | YES | None |
| Session history | `session.py` | YES | None |
| Routing logic | `claude_api.py` | YES | None |
| Code execution | `claude_interactive.py` | YES | None |
| Worker pool | `agent_pool.py` | YES | None |
| Task management | `tasks.py` | YES | None |
| Persistence | `database.py` | YES | None |
| Response formatting | `formatter.py` | PARTIAL | Adapt Telegram → HTML |
| Handlers | `main.py` | NO | Create `web_handlers.py` |

---

## Performance Metrics

### Response Times
- Question (Haiku): 1-2 seconds
- Code task (Sonnet): 30-120 seconds
- Log analysis: 1-2 seconds

### Costs
- Question: ~$0.0001
- Small code task: ~$0.01-0.05
- Large code task: ~$0.10-0.50

### Limits (Per User)
- Rate: 30 requests/minute, 500/hour
- Worker pool: 3 concurrent tasks
- Session history sent to Claude: Last 10 messages
- Message truncation: 2000 chars each

---

## Troubleshooting Guide

### Common Issues

**"Messages processing slowly"**
- Check `message_queue.py` processor logs
- Verify rate limits not being hit
- Check if agent pool is saturated (max 3 agents)

**"Session history not persisting"**
- Verify `data/sessions.json` exists
- Check disk permissions on `data/` directory
- Restart bot (reload from disk)

**"Costs higher than expected"**
- Check if routing to Sonnet too often (should be 80/20)
- Verify history truncation working (last 10 messages)
- Review large code tasks in logs

**"WebSocket disconnections"**
- Increase WebSocket timeout
- Add reconnection logic in frontend
- Check for server-side errors in logs

---

## Next Steps

1. **Understand the Architecture** (30 min)
   - Read ARCHITECTURE_EXPLORATION_SUMMARY.md
   - Review the diagrams in TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md

2. **Review the Code** (1 hour)
   - Skim main.py to understand flow
   - Look at message_queue.py structure
   - Check session.py data format

3. **Plan Implementation** (30 min)
   - Read WEB_CHAT_REPLICATION_GUIDE.md
   - Create implementation plan
   - Estimate effort

4. **Start Building** (Week 1)
   - Create Flask app
   - Connect to shared message_queue
   - Add WebSocket layer
   - Build basic React UI

5. **Extend Functionality** (Week 2+)
   - Add task execution
   - Integrate shared database
   - Add advanced features

---

## Summary

You now have three comprehensive documents explaining:

1. **ARCHITECTURE_EXPLORATION_SUMMARY.md** - The big picture in 5 minutes
2. **TELEGRAM_BOT_ARCHITECTURE_ANALYSIS.md** - Deep technical details
3. **WEB_CHAT_REPLICATION_GUIDE.md** - Step-by-step implementation

The key insight: **The Telegram bot architecture is 90% reusable for a web chat interface.** You're not reimplementing the bot - you're adding a new frontend to the same backend.

Start with the summary, then dive into the guide when ready to build.

