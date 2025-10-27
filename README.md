# AMIGA: Autonomous Modular Interactive Graphical Agent

<p align="center">
  <img src="static/img/logo.png" alt="AMIGA Logo" width="500"/>
</p>

<p align="center">
  <strong>Interactive agent system for repository automation</strong><br/>
  Focus on intent, not code
</p>

<p align="center">
  <img src="https://img.shields.io/badge/coverage-70%25-yellow?style=flat-square" alt="Coverage Badge"/>
  <img src="https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square" alt="Tests Badge"/>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square" alt="Python Badge"/>
</p>

## What This Is

AMIGA is an interactive tool for controlling repositories through natural language. You describe what you want, and specialized agents handle the implementation. The focus is on user experience and intent extraction, not code editing.

**Core Philosophy**: Users shouldn't think about code. The system handles implementation through comprehensive monitoring, error handling, and self-improvement capabilities.

## Why This Exists

Current tools (Cursor, Claude Code) focus on code - editing files, writing functions, managing implementations. AMIGA takes a different approach: focus on what the user wants to achieve, and make the code implicit.

**The goal**: Advance software development by prioritizing user intent over technical details. Better monitoring, better error handling, better automation - so users never need to think about implementation.

## Key Capabilities

- **16 Specialized Agents**: Orchestration, implementation, QA validation, debugging, self-improvement
- **Web Chat Interface**: `http://localhost:3000/chat` - rich interactions without code focus
- **Real-time Monitoring**: Live task tracking, tool usage metrics, error analysis, cost analytics
- **Self-Improvement**: Analyzes failures from SQLite database, updates agent behavior autonomously
- **Phase-Aware Execution**: Visual progression through Explore → Plan → Code → Commit
- **Database Persistence**: SQLite tracking of tasks, tool usage, sessions, error patterns
- **Comprehensive Testing**: 41 test modules (9,843 lines) ensuring reliability
- **Production Ready**: 589 commits, battle-tested workflows, stable deployment

## Interface

### Web Chat (Primary)
**URL**: `http://localhost:3000/chat`

Modern React + TypeScript interface:
- Real-time messaging with WebSocket
- Syntax highlighting for technical output
- Session persistence
- Mobile responsive
- No external dependencies

### Monitoring Dashboard
**URL**: `http://localhost:3000`

Real-time system metrics:
- Running tasks with live tool usage
- Session history with sorting
- Error tracking and categorization
- API cost breakdown by model
- Database metrics and analytics

### Telegram Bot (Deprecated)
Early interface implementation. Still functional but no longer primary focus. Use web chat for better UX.

## Quick Start

### Prerequisites
- Python 3.12+
- [Claude Code CLI](https://docs.claude.com/claude-code)
- Anthropic API key ([get one](https://console.anthropic.com/))
- jq (JSON processor): `brew install jq`
- Node.js 18+ (for frontend development)

### Installation

```bash
# Clone and setup
git clone <repo_url>
cd amiga
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pre-commit install

# Configure
cp .env.example .env
# Edit .env with your API key and workspace path

# Deploy and run
./deploy.sh chat  # Builds frontend, starts all services

# Access interfaces
# Chat: http://localhost:3000/chat
# Monitoring: http://localhost:3000
```

### Environment Config

```bash
# Required
ANTHROPIC_API_KEY=your_api_key
WORKSPACE_PATH=/path/to/your/repos

# Optional (Telegram - deprecated)
TELEGRAM_BOT_TOKEN=your_bot_token
ALLOWED_USERS=your_telegram_user_id

# Cost controls
DAILY_COST_LIMIT=100              # Stop at $100/day
MONTHLY_COST_LIMIT=1000           # Stop at $1000/month

# System
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
SESSION_TIMEOUT_MINUTES=60        # Clear inactive sessions
```

## Architecture

### Agent System

**16 Specialized Agents** coordinated by orchestrator:

#### Core Workflow
- **orchestrator**: Task coordination and delegation
- **code_agent**: Backend implementation (Python, Sonnet 4.5)
- **frontend_agent**: UI/UX with Playwright testing (Sonnet 4.5)
- **research_agent**: Deep analysis and proposals (Opus 4.5)

#### Quality Assurance
- **Jenny**: Spec verification
- **karen**: Reality checks on completion claims
- **task-completion-validator**: End-to-end functional testing
- **ui-comprehensive-tester**: UI testing with Playwright MCP
- **code-quality-pragmatist**: Over-engineering detection
- **claude-md-compliance-checker**: Project standards enforcement

#### System Operations
- **ultrathink-debugger**: Deep debugging (Opus 4.5 - use sparingly)
- **debug-agent**: Task diagnostics and git state checks
- **self-improvement-agent**: Analyzes error patterns, updates agent prompts
- **git-worktree**: Isolated workspace creation
- **git-merge**: Branch merging after completion
- **Explore**: Fast codebase exploration

### Task Execution

Background tasks run in isolated git worktrees:

**Phases**:
1. **Explore**: Context loading and codebase research
2. **Plan**: Analysis, design, trade-off evaluation
3. **Code**: Implementation with self-checks
4. **Commit**: Verification, testing, git operations

**Monitoring**: Real-time phase tracking, tool usage, and error handling visible in dashboard.

### Self-Improvement

The system learns from failures:
- **Error tracking**: SQLite database stores tool usage, failures, error categories
- **Pattern analysis**: self-improvement-agent queries database for recurring issues
- **Autonomous updates**: Agent prompts updated based on real failure patterns
- **Code fixes**: Tasks created for systemic code issues

Manual trigger: "analyze recent errors and improve"

### Model Selection

- **Haiku 4.5**: Fast routing decisions (Q&A, deprecated Telegram bot)
- **Sonnet 4.5**: Standard coding tasks (code_agent, frontend_agent)
- **Opus 4.5**: Complex research and deep debugging (research_agent, ultrathink-debugger)

Cost-aware: More capable models used only when needed.

## Monitoring & Debugging

### Database

**Location**: `data/agentlab.db`

**Tables**:
- `tasks`: Task status, lifecycle, errors
- `tool_usage`: Per-tool metrics, failures, error categories
- `sessions`: Conversation history

**Quick Queries**:
```bash
# Running tasks
sqlite3 data/agentlab.db "SELECT task_id, status, description FROM tasks WHERE status = 'running';"

# Tool usage
sqlite3 data/agentlab.db "SELECT tool_name, COUNT(*) FROM tool_usage GROUP BY tool_name;"

# Recent errors
sqlite3 data/agentlab.db "SELECT task_id, error FROM tasks WHERE error IS NOT NULL LIMIT 10;"
```

See `CLAUDE.md` for comprehensive database schema and query patterns.

### Logs

**Location**: `logs/`

**Files**:
- `logs/bot.log` - Main application log (auto-rotated)
- `logs/monitoring.log` - Web dashboard log
- `logs/sessions/<session_uuid>/` - Per-session Claude Code logs

**Common Commands**:
```bash
# Check for errors
tail -100 logs/bot.log | grep ERROR

# Monitor real-time
tail -f logs/bot.log

# Find specific issues
grep -i "timeout\|exception\|failed" logs/bot.log | tail -50
```

### Troubleshooting

| Issue | Fix |
|-------|-----|
| **Services not running** | `./deploy.sh chat` |
| **Frontend not updating** | `./deploy.sh chat` + hard refresh (Cmd+Shift+R) |
| **Task stuck** | Check dashboard or query database |
| **High costs** | `cat data/cost_tracking.json \| jq` |

## Project Structure

```
amiga/
├── core/                        # Core system functionality
│   ├── main.py                  # Entry point
│   ├── routing.py               # Message routing (deprecated)
│   ├── session.py               # Session management
│   └── orchestrator.py          # Task orchestration
├── claude/                      # Claude AI integration
│   ├── api_client.py            # Claude API (Haiku - routing)
│   └── code_cli.py              # Claude Code CLI (Sonnet/Opus - tasks)
├── monitoring/                  # Dashboard & metrics
│   ├── server.py                # Flask + SSE server
│   ├── metrics.py               # Real-time metrics
│   └── dashboard/               # React chat UI (TypeScript)
│       ├── src/                 # Source files
│       └── build/               # Production build
├── tasks/                       # Task management
│   ├── manager.py               # Background task tracking
│   ├── pool.py                  # Worker pool
│   ├── database.py              # SQLite operations
│   ├── analytics.py             # Usage tracking
│   ├── tracker.py               # Tool usage tracking
│   └── enforcer.py              # Workflow enforcement
├── utils/                       # Shared utilities
│   ├── git.py                   # Git operations
│   ├── log_monitor.py           # Log monitoring
│   ├── log_analyzer.py          # Log analysis
│   └── worktree.py              # Worktree management
├── tests/                       # Test suite (41 modules, 9,843 lines)
├── .claude/                     # Claude Code configuration
│   ├── agents/                  # 16 agent definitions
│   ├── hooks/                   # Tool usage tracking
│   └── settings.local.json      # Permissions
├── data/                        # Runtime state
│   └── agentlab.db              # SQLite database
├── logs/                        # Application logs
├── static/                      # Static assets
│   └── chat/                    # Deployed chat frontend
└── templates/                   # Jinja templates
```

## Cost Estimates

### Typical Usage
- 10 tasks/day @ Sonnet: ~$60/month
- Research/debugging @ Opus: ~$15/month (occasional)
- **Total: ~$75/month**

### Per Request
- Small fix: $0.01-0.05
- Large feature: $0.10-0.50
- Research/debugging: $0.50-2.00

Set `DAILY_COST_LIMIT` and `MONTHLY_COST_LIMIT` in `.env`. System stops when limit reached.

## Development

### Frontend Changes

```bash
# Modify source files in monitoring/dashboard/src/
./deploy.sh chat  # Builds, deploys, restarts services
# Hard refresh browser: Cmd+Shift+R
```

Pre-commit hook enforces deployment before commits.

### Testing

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html

# Specific module
pytest tests/test_formatter.py -v
```

**Coverage targets**: 70%+ overall, 80%+ for critical paths, 100% for utilities.

### Pre-commit Hooks

Automatically run on commit:
- black (formatting)
- isort (imports)
- ruff (linting)
- bandit (security)
- pytest (tests)
- secret detection
- chat-frontend-deploy

```bash
pre-commit run --all-files  # Manual run
```

## Security

- User whitelist (Telegram - deprecated)
- No hardcoded secrets
- Rate limiting (30/min, 500/hour per user)
- Cost limits (daily/monthly)
- Input sanitization (XML escaping, injection detection)
- File path validation (directory traversal prevention)

## Technologies

- Python 3.12+
- Claude API (Haiku 4.5, Sonnet 4.5, Opus 4.5)
- Claude Code CLI
- Flask (dashboard backend)
- React + TypeScript (chat frontend)
- SQLite (persistence)
- Playwright MCP (browser automation)
- Whisper (voice transcription - deprecated Telegram feature)

## Vision

Current development tools focus on code. AMIGA explores a different approach: focus on user intent and make implementation implicit through:

- **Comprehensive monitoring**: Real-time visibility into all system operations
- **Error resilience**: Automatic detection, categorization, and recovery
- **Self-improvement**: Learning from failures to prevent future issues
- **User-centric design**: Chat interface prioritizing intent over technical details

This represents a step toward software development where users express goals, not write code. The system handles implementation through specialized agents, robust monitoring, and continuous improvement.

Not a finished product - an exploration of what's possible when we prioritize user experience over technical exposure.

## Contributing

Personal project, but issues and suggestions welcome via GitHub Issues.

**Development workflow**:
1. Fork and clone
2. Set up environment: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
3. Configure: `cp .env.example .env`
4. Install hooks: `pre-commit install`
5. Create feature branch
6. Make changes with tests (mandatory)
7. Run checks: `pre-commit run --all-files`
8. Commit and submit PR

See `CLAUDE.md` for detailed conventions, architecture, and development guidelines.

## Resources

- [Claude Code Docs](https://docs.claude.com/claude-code)
- [Anthropic API Docs](https://docs.anthropic.com/)
- [Playwright MCP](https://github.com/microsoft/playwright)

## License

MIT License - See LICENSE file for details

---

**Status**: Production Ready | **Commits**: 589 | **Test Coverage**: 9,843 lines (41 modules) | **Agents**: 16

*Exploring the future of software development: user intent over code implementation.*
