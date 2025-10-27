# Telegram Bot + Claude Code Orchestrator - Implementation Plan

## Project Overview
Build a Telegram bot that provides conversational access to Claude Code orchestrator, with intelligent routing between direct responses and background task delegation.

## Architecture

```
Telegram App (Phone)
    ↓
Telegram Bot API
    ↓
Bot Server (Python)
    ↓ maintains persistent session
Claude Code CLI (orchestrator agent)
    ↓ spawns when needed
Background Worker Agents (via Task tool)
```

## Model Selection Strategy

### Intelligent Model Routing

**Claude Haiku 4.5 (Default - Fast & Cheap):**
- Quick questions
- Conversations
- Status checks
- Simple lookups
- General Q&A
- Orchestration and routing
- **Cost**: ~$0.80 per 1M input tokens, ~$4 per 1M output tokens (estimated)

**Claude Sonnet 4.5 (For complex work only):**
- Code generation
- Architecture decisions
- Multi-file refactoring
- Complex reasoning tasks
- **Cost**: $3 per 1M input tokens, $15 per 1M output tokens

**Note:** No Opus - too expensive for this use case!

### Model Fallback Strategy

```python
def select_model(task_type, complexity):
    # Try Haiku 4.5 first (if available)
    if task_type in ['chat', 'question', 'status', 'orchestrate']:
        return 'haiku-4.5'

    # Use Sonnet only for code/complex tasks
    if task_type in ['code', 'architecture', 'refactor']:
        return 'sonnet-4.5'

    # Default to Haiku
    return 'haiku-4.5'
```

### Agent Configuration

```markdown
# ~/.claude/agents/orchestrator.md
---
name: orchestrator
model: haiku-4.5
---
You are the main orchestrator. Decide when to delegate vs respond directly.
Use Haiku 4.5 (yourself) for simple queries and conversations.
Spawn Sonnet 4.5 workers ONLY for complex code generation tasks.

# ~/.claude/agents/code-builder.md
---
name: code-builder
model: sonnet-4.5
---
Build production-quality code with tests.
Only invoked for actual code generation tasks.

# ~/.claude/agents/quick-responder.md
---
name: quick-responder
model: haiku-4.5
---
Answer questions quickly and concisely.
```

## Implementation Phases

### Phase 1: Basic Telegram Bot (Week 1)
**Goal:** Chat with Claude Code via Telegram

**Tasks:**
- [ ] Set up Telegram bot (BotFather)
- [ ] Install python-telegram-bot library
- [ ] Create bot server with message handler
- [ ] Connect to Claude Code CLI
- [ ] Test basic message exchange

**Deliverables:**
- Working Telegram bot
- Messages forwarded to Claude Code
- Responses returned to Telegram

**Time**: 1-2 days

---

### Phase 2: Persistent Sessions (Week 1)
**Goal:** Maintain conversation context

**Tasks:**
- [ ] Implement session management (user_id → claude_session)
- [ ] Store conversation history per user
- [ ] Handle session timeout/cleanup
- [ ] Add session restart command

**Session Storage:**
```python
sessions = {
    'user_123': {
        'claude_process': subprocess.Popen(...),
        'history': [],
        'created_at': datetime,
        'last_activity': datetime
    }
}
```

**Deliverables:**
- Persistent conversations
- Context awareness
- Session management

**Time**: 2-3 days

---

### Phase 3: Orchestrator Agent (Week 2)
**Goal:** Intelligent task routing

**Tasks:**
- [x] Create orchestrator subagent definition
- [x] Configure model routing logic
- [x] Implement task tracking system
- [x] Add status monitoring
- [x] Build notification system

**Task Tracking:**
```python
# tasks.json
{
    "task_id": "uuid",
    "user_id": "telegram_user_id",
    "description": "Build REST API",
    "status": "in_progress",
    "agent": "code-builder",
    "model": "sonnet-4.5",
    "created_at": "2025-10-16T10:00:00",
    "estimated_tokens": 50000,
    "actual_tokens": 25000
}
```

**Deliverables:**
- Smart routing (Haiku vs Sonnet)
- Background task spawning
- Status tracking

**Time**: 4-5 days

---

### Phase 4: Worker Agents (Week 2-3)
**Goal:** Specialized background workers

**Tasks:**
- [x] Create code-builder agent (Sonnet 4.5)
- [x] Create quick-responder agent (Haiku 4.5)
- [x] Create research agent (Haiku 4.5)
- [x] Create test-writer agent (Sonnet 4.5)
- [x] Implement artifact storage system
- [x] Add task completion notifications

**Agent Types:**

| Agent | Model | Use Case | Est. Tokens/Task |
|-------|-------|----------|------------------|
| orchestrator | Haiku 4.5 | Routing & chat | 5K |
| quick-responder | Haiku 4.5 | Q&A | 2K |
| code-builder | Sonnet 4.5 | Build features | 50K |
| test-writer | Sonnet 4.5 | Write tests | 20K |
| research | Haiku 4.5 | Web search | 10K |

**Deliverables:**
- 5 specialized agents
- Task delegation
- Completion notifications

**Time**: 5-6 days

---

### Phase 5: Voice Support (Week 3)
**Goal:** Voice message input

**Tasks:**
- [x] Handle Telegram voice messages
- [x] Integrate speech-to-text (OpenAI Whisper)
- [x] Test voice input accuracy
- [ ] Add voice response option (optional)

**Note:** Telegram automatically transcribes voice messages!

**Deliverables:**
- Voice message support
- Auto-transcription

**Time**: 1 day

---

### Phase 6: Enhanced UX (Week 3-4)
**Goal:** Better conversation experience

**Tasks:**
- [ ] Add rich formatting (markdown, code blocks)
- [ ] Implement typing indicator
- [ ] Add file upload/download
- [ ] Create status dashboard messages
- [ ] Add command shortcuts

**Commands:**
```
/status - Show all running tasks
/logs <id> - View task logs
/kill <id> - Cancel task
/agents - List available agents
/clear - Reset conversation
/cost - Show usage costs
```

**Message Formatting:**
```
🤖 *Task Created*
📝 Build REST API
⚙️ Agent: code-builder (Sonnet 4.5)
⏱️ Estimated: 15-20 min
💰 Est. cost: $0.75

✅ *Task Complete* (#42)
📦 3 files created
🧪 15 tests passing
💰 Actual cost: $0.68
📎 api.py
📎 tests.py
📎 README.md
```

**Deliverables:**
- Rich message formatting
- Status updates
- File sharing
- Commands

**Time**: 3-4 days

---

### Phase 7: Production Hardening (Week 4)
**Goal:** Reliable, secure operation

**Tasks:**
- [ ] Add error handling and retries
- [ ] Implement rate limiting
- [ ] Add authentication (whitelist user IDs)
- [ ] Set up logging and monitoring
- [ ] Add cost tracking and limits
- [ ] Create backup/restore for sessions
- [ ] Add health checks

**Security:**
```python
ALLOWED_USERS = [
    123456789,  # Your Telegram user ID
    # Add trusted users
]

async def handle_message(update, context):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("Unauthorized")
        return
```

**Cost Controls:**
```python
USER_DAILY_LIMIT = 100  # $100/day
USER_MONTHLY_LIMIT = 1000  # $1000/month

def check_budget(user_id, estimated_cost):
    usage = get_user_usage(user_id)
    if usage.daily + estimated_cost > USER_DAILY_LIMIT:
        raise BudgetExceeded("Daily limit reached")
```

**Deliverables:**
- Error handling
- Security
- Monitoring
- Cost controls

**Time**: 3-4 days

---

## Technical Stack

### Dependencies
```json
{
  "python-telegram-bot": "^20.7",
  "anthropic": "^0.39.0",
  "python-dotenv": "^1.0.0",
  "aiofiles": "^23.2.1",
  "pydantic": "^2.5.0",
  "rich": "^13.7.0"
}
```

### Project Structure
```
agentlab/
├── telegram_bot/
│   ├── main.py              # Bot entry point
│   ├── handlers.py          # Message handlers
│   ├── session.py           # Session management
│   ├── claude_client.py     # Claude Code CLI wrapper
│   ├── tasks.py             # Task tracking
│   └── formatters.py        # Message formatting
├── .claude/
│   └── agents/
│       ├── orchestrator.md
│       ├── code-builder.md
│       ├── quick-responder.md
│       ├── test-writer.md
│       └── research.md
├── data/
│   ├── sessions.json        # Active sessions
│   ├── tasks.json           # Task history
│   └── usage.json           # Cost tracking
├── logs/
│   └── bot.log
├── .env
├── requirements.txt
└── README.md
```

## Cost Estimation

### Usage Scenarios

#### Scenario 1: Light Use (Personal)
**Daily usage:**
- 20 quick questions (Haiku 4.5, 2K tokens each)
- 5 conversations (Haiku 4.5, 10K tokens each)
- 2 coding tasks (Sonnet 4.5, 50K tokens each)

**Monthly costs with Haiku 4.5:**
```
Quick questions (Haiku 4.5):
  20/day × 30 days × 2K tokens = 1.2M tokens
  Input: 1.2M × $0.80/1M = $0.96
  Output: 1.2M × $4/1M = $4.80

Conversations (Haiku 4.5):
  5/day × 30 days × 10K tokens = 1.5M tokens
  Input: 1.5M × $0.80/1M = $1.20
  Output: 1.5M × $4/1M = $6.00

Coding tasks (Sonnet 4.5):
  2/day × 30 days × 50K tokens = 3M tokens
  Input: 3M × $3/1M = $9.00
  Output: 3M × $15/1M = $45.00

Orchestrator overhead (Haiku 4.5):
  27/day × 30 days × 5K tokens = 4M tokens
  Input: 4M × $0.80/1M = $3.20
  Output: 4M × $4/1M = $16.00

MONTHLY TOTAL: ~$86
```

**Much cheaper with Haiku 4.5!**

---

#### Scenario 2: Moderate Use (Daily Driver)
**Daily usage:**
- 50 quick questions (Haiku 4.5)
- 10 conversations (Haiku 4.5)
- 5 coding tasks (Sonnet 4.5)
- 3 research tasks (Haiku 4.5)

**Monthly costs:**
```
Quick questions (Haiku 4.5): $14.40
Conversations (Haiku 4.5): $14.40
Coding tasks (Sonnet 4.5): $135
Research (Haiku 4.5): $8.64
Orchestrator (Haiku 4.5): $11.52

MONTHLY TOTAL: ~$184
```

---

#### Scenario 3: Heavy Use (Professional)
**Daily usage:**
- 100 quick questions
- 20 conversations
- 10 coding tasks
- 5 research tasks

**Monthly costs:**
```
Quick questions (Haiku 4.5): $28.80
Conversations (Haiku 4.5): $28.80
Coding tasks (Sonnet 4.5): $270
Research (Haiku 4.5): $14.40
Orchestrator (Haiku 4.5): $23.04

MONTHLY TOTAL: ~$365
```

---

### Cost Optimization Strategies

1. **Use Haiku 4.5 by default** (90%+ of queries)
2. **Sonnet only for code generation** (not conversations)
3. **Cache common responses** (reduce repeated queries)
4. **Prompt compression** (minimize token usage)
5. **Set daily limits** (prevent runaway costs)
6. **No Opus ever** (not cost-effective)

**Realistic monthly cost for typical use: $86-184**

---

## Success Criteria

### MVP (End of Phase 4) ✅ COMPLETE
- [x] Telegram bot operational
- [x] Persistent chat sessions (session.py)
- [x] Sonnet 4.5 orchestration (orchestrator.py:151)
- [x] Background task spawning (orchestrator.py:195-202)
- [x] Task status tracking (tasks.py)
- [x] Task completion notifications

### Full Release (End of Phase 7) - IN PROGRESS
- [x] Voice message support (OpenAI Whisper)
- [x] Rich formatting (HTML via formatter.py)
- [ ] File upload/download
- [x] Command shortcuts (/restart, /status, /clear)
- [x] Security (ALLOWED_USERS whitelist)
- [ ] Cost tracking and limits
- [x] Error handling (try/catch in main.py)
- [ ] Production monitoring

---

### Phase 8: Investigation → Plan → Build Workflow (Week 5)
**Goal:** Research-first approach with user approval

**Tasks:**
- [ ] Add research agent workflow
- [ ] Implement plan document generation
- [ ] Add approval gate (wait for "implement")
- [ ] Create automatic folder structure
- [ ] Add project templates

**Workflow:**
```
1. User: "Build X"
2. Agent spawns research task
3. Agent creates PLAN.md with:
   - Architecture decisions
   - File structure
   - Phases breakdown
   - Cost/time estimates
4. Agent waits for approval
5. User: "implement" or "modify plan first"
6. Agent creates new folder: workspace/project-name/
7. Agent spawns builder agents
8. Agent tracks progress
```

**Orchestrator Enhancement:**
```markdown
# Orchestrator knows these patterns:

Investigation keywords: "research", "investigate", "explore", "analyze"
→ Spawn research agent, create plan, wait for approval

Implementation keywords: "implement", "build", "create", "start"
→ Check if plan exists, create folder, spawn builders

Planning keywords: "plan", "design", "architect"
→ Create detailed PLAN.md only
```

**Features:**
- Full workspace access (uses Glob/Grep/Read efficiently)
- New projects → separate folders
- Doesn't load entire workspace into context
- Plan review before execution
- Clear file structure preview

**Deliverables:**
- Research agent (Haiku 4.5)
- Plan generator
- Approval workflow
- Automatic project scaffolding
- Progress tracking

**Time**: 3-4 days

---

## Future Enhancements

### Phase 9: Advanced Features
- [ ] Multi-user support (team usage)
- [ ] Shared task queue
- [ ] Task templates ("build CRUD API")
- [ ] Agent learning from feedback
- [ ] Integration with GitHub (PR creation)
- [ ] Calendar integration (schedule tasks)
- [ ] Web dashboard (optional)

### Phase 10: Multi-Platform
- [ ] Discord bot (same backend)
- [ ] Slack bot
- [ ] WhatsApp (if official API improves)
- [ ] Web interface

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| High costs | High | Use Haiku 4.5 default, Sonnet only for code, no Opus ever |
| Bot downtime | Medium | Auto-restart, health checks |
| Claude Code crashes | Medium | Session recovery, error handling |
| Unauthorized access | High | User whitelist, rate limiting |
| Token limit exceeded | Medium | Context window management |
| Network issues | Low | Retry logic, queue messages |

## Timeline

**Total: 4 weeks**

- **Week 1**: Phases 1-2 (Basic bot + sessions)
- **Week 2**: Phases 3-4 (Orchestrator + workers)
- **Week 3**: Phases 5-6 (Voice + UX)
- **Week 4**: Phase 7 (Production hardening)

**MVP Ready**: End of Week 2
**Production Ready**: End of Week 4

## Getting Started

### Prerequisites
1. Telegram account
2. Claude Code CLI installed
3. Anthropic API key
4. Python 3.11+

### Quick Start

```bash
# 1. Create Telegram bot
# Talk to @BotFather on Telegram
# Get bot token

# 2. Set up environment
cd agentlab
python -m venv venv
source venv/bin/activate
pip install python-telegram-bot anthropic python-dotenv

# 3. Configure
echo "TELEGRAM_BOT_TOKEN=your_token_here" > .env
echo "ANTHROPIC_API_KEY=your_key_here" >> .env

# 4. Create agents
mkdir -p ~/.claude/agents
# Add agent configs

# 5. Run bot
python telegram_bot/main.py
```

### Testing

```bash
# Send message to bot
# Should get response from Claude Code

# Test voice
# Send voice message
# Should transcribe and respond

# Test task spawning
# "Build a REST API"
# Should create background task
```

## Cost Monitoring

### Daily Summary
```python
def send_daily_summary(user_id):
    usage = get_user_usage(user_id, today)

    message = f"""
📊 *Daily Summary*
💬 Messages: {usage.messages}
🤖 Haiku 4.5 calls: {usage.haiku_calls}
⚙️ Sonnet 4.5 calls: {usage.sonnet_calls}
💰 Cost: ${usage.total_cost:.2f}
📈 MTD: ${usage.month_to_date:.2f}

Model breakdown:
└─ Haiku: {usage.haiku_percentage:.0f}%
└─ Sonnet: {usage.sonnet_percentage:.0f}%
    """

    send_message(user_id, message)
```

## Next Steps

1. ✅ Review and approve plan
2. Create Telegram bot with BotFather
3. Set up development environment
4. Begin Phase 1 implementation
5. Test with single user
6. Iterate and improve
7. Add cost controls before heavy use

---

**Estimated Total Cost:**
- Development time: 4 weeks
- Monthly operating cost: **$86-184** (typical use with Haiku 4.5)
- One-time setup: Free (Telegram bot is free)

**Cost Breakdown:**
- Light use: **~$86/month**
- Moderate use: **~$184/month**
- Heavy use: **~$365/month**

**Why so cheap?** Haiku 4.5 handles 90% of interactions at 1/4 the cost of Sonnet!

**ROI:**
Unlimited access to Claude Code from anywhere via phone. Worth it! 🚀
