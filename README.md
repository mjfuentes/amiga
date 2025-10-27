# AMIGA: Autonomous Modular Interactive Graphical Agent

<p align="center">
  <img src="static/img/logo.png" alt="Bot Logo" width="500"/>
</p>

<p align="center">
  <strong>Production-ready Telegram bot powered by Claude AI</strong><br/>
  Intelligently routes between fast Q&A and deep coding work with real-time monitoring
</p>

<p align="center">
  <img src="https://img.shields.io/badge/coverage-70%25-yellow?style=flat-square" alt="Coverage Badge"/>
  <img src="https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square" alt="Tests Badge"/>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square" alt="Python Badge"/>
</p>

## 📊 At a Glance

| Metric | Value |
|--------|-------|
| **Commits** | 589 |
| **Lines of Code** | ~15,600 (Python only) |
| **Specialized Agents** | 16 |
| **Test Modules** | 41 modules, 9,843 lines |
| **Status** | ✅ Production Ready |

## ✨ Key Features

- **🤖 Intelligent Routing**: Claude API (Haiku 4.5) for fast Q&A, Claude Code CLI (Sonnet 4.5) for coding tasks
- **🎯 16 Specialized Agents**: Orchestrator, code agents, QA agents, debugging, and git workflow management
- **💬 Dual Interface**: Telegram bot + modern React web chat at `http://localhost:3000/chat`
- **📊 Real-time Dashboard**: Live task tracking, tool usage metrics, error monitoring, and cost analytics
- **🔄 Phase Tracking**: Visual progression through Explore → Plan → Code → Commit workflow
- **🗄️ Database-backed**: SQLite for tasks, tool usage, and session persistence
- **🧪 Comprehensive Testing**: 26 test modules with pytest covering core logic and workflows
- **🎭 Playwright MCP**: Cross-browser automation for frontend testing
- **💰 Cost Controls**: Daily/monthly limits with detailed usage breakdowns
- **🔒 Security**: User whitelist, rate limiting, input sanitization, file path validation

## What it does

**Questions**: Fast answers using Claude API (Haiku 4.5). Great for "what's the difference between X and Y?" or "check logs for errors."

**Coding**: Full-featured development using Claude Code CLI (Sonnet 4.5). Reads/writes files, makes commits, runs tests. Tasks run in the background - you get notified when done.

**Voice & Images**: Send voice notes (transcribed via Whisper) or screenshots for analysis.

**Web Chat**: Use the browser-based chat interface for rich interactions without Telegram mobile app.

**Monitoring**: Built-in dashboard at `http://localhost:3000` shows running tasks, errors, API costs, and tool usage in real-time.

## 🚀 Quick Start

### Prerequisites Checklist

- [ ] Python 3.12+
- [ ] [Claude Code CLI](https://docs.claude.com/claude-code) installed
- [ ] Anthropic API key ([get one here](https://console.anthropic.com/))
- [ ] Telegram account
- [ ] jq (JSON processor) - `brew install jq` on macOS
- [ ] Node.js 18+ (for chat frontend development)
- [ ] Bot token from [@BotFather](https://t.me/BotFather)
- [ ] Your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

### Installation

```bash
# Clone and setup
git clone <repo_url>
cd agentlab
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pre-commit install  # Install git hooks

# Configure
cp .env.example .env
# Edit .env with your tokens and user ID

# Deploy and run (recommended)
./deploy.sh chat  # Builds frontend, deploys, starts all services

# Or run manually (development)
python core/main.py          # Terminal 1: Bot
python monitoring/server.py  # Terminal 2: Dashboard
# Open http://localhost:3000
```

### Environment Config

```bash
# Required
TELEGRAM_BOT_TOKEN=your_bot_token
ANTHROPIC_API_KEY=your_api_key
ALLOWED_USERS=your_telegram_user_id
WORKSPACE_PATH=/path/to/your/repos

# Optional
DAILY_COST_LIMIT=100              # Stop at $100/day
MONTHLY_COST_LIMIT=1000           # Stop at $1000/month
SESSION_TIMEOUT_MINUTES=60        # Clear inactive sessions
ANTHROPIC_ADMIN_API_KEY=admin_key # For usage sync
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
```

## 🚀 Current Status

**Production Ready** - 589 commits, 41 test modules, 9,843 lines of test coverage. Stable, battle-tested, and ready for public deployment.

### Core Capabilities
- ✅ **Dual AI Models**: Haiku 4.5 for fast Q&A, Sonnet 4.5 for coding, Opus 4.5 for research
- ✅ **16 Specialized Agents**: Full orchestration pipeline with QA validation and debugging
- ✅ **Dual Interface**: Telegram bot + React web chat at `http://localhost:3000/chat`
- ✅ **Real-time Dashboard**: Live task tracking with SSE, phase progression, tool metrics
- ✅ **Comprehensive Testing**: 26 test modules covering core logic, workflows, and regressions
- ✅ **Database Persistence**: SQLite for tasks, tool usage, sessions with query tools
- ✅ **Git Worktree Management**: Isolated workspaces preventing concurrent task conflicts
- ✅ **Playwright MCP**: Cross-browser automation for frontend testing and validation
- ✅ **Cost Controls**: Daily/monthly limits, per-model tracking, detailed breakdowns
- ✅ **Production Deployment**: Single-command `./deploy.sh` for builds and service management

### Battle-Tested Features
- **Multi-agent orchestration** with delegation and validation
- **Background task execution** with async notifications
- **Phase-aware status tracking** (Explore → Plan → Code → Commit)
- **Input sanitization** against prompt injection
- **Rate limiting** (30/min, 500/hour per user)
- **Voice transcription** via Whisper
- **Screenshot analysis** with image support
- **Pre-commit hooks** (black, isort, ruff, bandit, pytest)
- **Auto-deployment enforcement** for frontend changes

## Commands

### Telegram Bot
- `/start` - Reset and show welcome
- `/help` - Command reference
- `/status` - Session stats, active tasks, costs
- `/usage` - API usage breakdown
- `/clear` - Clear history
- `/stopall` - Cancel all running tasks
- `/restart` - Restart bot (owner only)

### Web Chat
Access at `http://localhost:3000/chat` for:
- Rich message formatting with syntax highlighting
- Real-time message streaming
- Session persistence
- No Telegram client required

## Architecture

### Message Routing

```
User Input (Telegram/Web)
    ↓
Router
    ├─→ Commands (/help, /status, /clear, /stopall)
    │   └─→ Direct response (fast)
    │
    ├─→ Questions & Quick Analysis
    │   └─→ Claude API (Haiku 4.5)
    │       • 1-2s response time
    │       • 10x cheaper than Sonnet
    │       • Perfect for Q&A, log analysis
    │       • ~$0.0001 per question
    │
    └─→ Coding & Complex Tasks
        └─→ Background Worker (Claude Code CLI)
            • Sonnet 4.5 (standard coding)
            • Opus 4.5 (research & deep debugging)
            • Full file system access
            • Git integration
            • Bash commands
            • Multi-agent orchestration
            • Async with notifications
            • ~$0.01-0.50 per task
```

### Why Two Models?

| Aspect | Claude API (Haiku) | Claude Code CLI (Sonnet/Opus) |
|--------|-------------------|------------------------------|
| **Cost** | $0.0001/question | $0.01-0.50/task |
| **Speed** | 1-2 seconds | 5-60 seconds |
| **Best For** | Chat, Q&A, quick analysis | Coding, complex reasoning |
| **Tools** | None (text only) | Read/Write/Edit, Git, Bash |
| **Use Case** | "What's the error in logs?" | "Refactor auth system" |

### Agent System

**16 Specialized Agents** working together:

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

#### Debugging & Utilities
- **ultrathink-debugger**: Deep debugging (Opus 4.5 - expensive, use sparingly)
- **debug-agent**: Task diagnostics and git state checks
- **self-improvement-agent**: Analyzes error patterns and updates agent prompts
- **git-worktree**: Isolated workspace creation
- **git-merge**: Branch merging after completion
- **Explore**: Fast codebase exploration (system agent)

### Background Tasks

Long-running work happens async in isolated git worktrees. You get immediate acknowledgment, can keep chatting, and receive a notification when complete.

**Task Phases**:
1. **Explore**: Context loading and codebase research
2. **Plan**: Analysis, design, and trade-off evaluation
3. **Code**: Implementation with self-checks
4. **Commit**: Verification, testing, and git operations

## Monitoring Dashboard

Real-time web dashboard at `http://localhost:3000`:
- **Running Tasks**: Click any task to see live tool usage and phase progression
- **Sessions**: View all Claude Code sessions with sorting
- **Errors**: Recent failures with timestamps
- **API Costs**: 24h spending across models
- **Tool Usage**: Which tools are being called
- **Database Metrics**: Task counts by status

Built with Flask + SSE for live updates. Dark theme, minimal design. Chat interface at `/chat` route.

## Web Chat Frontend

Modern React + TypeScript interface:
- **Real-time messaging**: WebSocket-based communication
- **Syntax highlighting**: Code blocks with proper formatting
- **Session management**: Persistent conversations
- **Mobile responsive**: Works on all screen sizes
- **No Telegram required**: Use directly in browser

**Development**:
```bash
cd monitoring/dashboard/chat-frontend
npm install
npm run dev    # Development server
npm run build  # Production build
```

**Deployment**:
```bash
./deploy.sh chat  # From project root - builds and deploys
```

## Project Structure

```
agentlab/
├── core/                        # Core bot functionality
│   ├── main.py                  # Entry point, command handlers
│   ├── routing.py               # Message routing logic
│   ├── session.py               # Conversation history
│   ├── config.py                # Configuration
│   └── orchestrator.py          # Task orchestration
├── claude/                      # Claude AI integration
│   ├── api_client.py            # Claude API (Haiku - Q&A)
│   └── code_cli.py              # Claude Code CLI (Sonnet - coding)
├── messaging/                   # Telegram layer
│   ├── formatter.py             # Message formatting
│   ├── queue.py                 # Per-user queuing
│   └── rate_limiter.py          # Rate limiting
├── monitoring/                  # Dashboard & metrics
│   ├── server.py                # Web dashboard (Flask + SSE)
│   ├── metrics.py               # Real-time metrics
│   ├── hooks_reader.py          # Hook data parsing
│   └── dashboard/
│       └── chat-frontend/       # React chat UI (TypeScript)
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
├── tests/                       # Test suite (26 modules, 5,384 lines)
│   ├── conftest.py              # pytest configuration
│   └── test_*.py                # Comprehensive test coverage
├── scripts/                     # Utility scripts
├── docs/                        # Documentation
├── .claude/                     # Claude Code configuration
│   ├── agents/                  # 16 agent definitions
│   ├── hooks/                   # Tool usage tracking
│   └── settings.local.json      # Permissions, output style
├── data/                        # Runtime state (SQLite DB)
│   └── agentlab.db              # Tasks, tool usage, sessions
├── logs/                        # Application logs
│   ├── bot.log                  # Main bot log
│   ├── monitoring.log           # Dashboard log
│   └── sessions/                # Per-session logs
├── static/                      # Static assets
│   └── chat/                    # Deployed chat frontend
└── templates/                   # Jinja templates
```

## Hook System

Bash hooks in `.claude/hooks/` track every tool call:
- `pre-tool-use`: Logs tool name + params before execution
- `post-tool-use`: Logs results + errors after execution
- `session-end`: Aggregates session summary

Python inline for JSON parsing, bash for everything else. Resilient (`set +e`), writes to both JSONL logs and JSON databases. Monitoring dashboard reads these hooks in real-time via SSE.

## Database

SQLite database at `data/agentlab.db` tracks:
- **tasks**: Background task status and lifecycle
- **tool_usage**: Per-tool metrics, errors, and performance
- **sessions**: Conversation history (if enabled)

**Quick Queries**:
```bash
# View running tasks
sqlite3 data/agentlab.db "SELECT task_id, status, description FROM tasks WHERE status = 'running';"

# Check tool usage
sqlite3 data/agentlab.db "SELECT tool_name, COUNT(*) FROM tool_usage GROUP BY tool_name;"

# Find recent errors
sqlite3 data/agentlab.db "SELECT task_id, error FROM tasks WHERE error IS NOT NULL LIMIT 10;"
```

See `CLAUDE.md` for detailed database schema and comprehensive query patterns.

## Cost Estimates

### Typical Usage
- 500 questions/day @ Claude API: ~$15/month
- 10 coding tasks/day @ Claude Code: ~$60/month
- **Total: ~$75/month**

### Per Request
- Question (API): ~$0.0001
- Small fix (CLI): $0.01-0.05
- Large feature (CLI): $0.10-0.50
- Research/Debugging (Opus): $0.50-2.00

Set `DAILY_COST_LIMIT` and `MONTHLY_COST_LIMIT` in `.env`. Bot stops when limit reached.

## Development

### Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

Includes: black, isort, ruff, bandit, pytest, secret detection, chat-frontend-deploy

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=. --cov-report=html --cov-report=term

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v -m integration

# Run specific test module
pytest tests/unit/test_formatter.py -v

# Open coverage report in browser
open htmlcov/index.html
```

**Test Coverage**: 9,843 lines across 41 modules:
- **Unit tests** (`tests/unit/`): Core logic, utilities, formatters
- **Integration tests** (`tests/integration/`): End-to-end workflows
- **Coverage target**: 70%+ for critical modules
- **Coverage reports**: HTML reports generated in `htmlcov/` directory

### Running in Production

**macOS (launchd)**:
```bash
./deploy.sh  # One-time setup + deployment
# Services auto-start on boot
```

**Linux (systemd)**: See `docs/SETUP.md`

**Manual restart**:
```bash
./deploy.sh chat  # Restarts all services
```

## Playwright MCP Integration

Cross-browser automation for frontend testing:

**Installation**:
```bash
claude mcp add playwright npx -s user @playwright/mcp@latest -- --isolated
```

**Features**:
- Chromium, Firefox, WebKit support
- Accessibility tree inspection
- Network monitoring
- Screenshot capture (JPEG format recommended)
- Form testing and validation

**Usage**: Available to `frontend_agent` and `ui-comprehensive-tester` for comprehensive UI validation.

## Security

- User whitelist (only authorized Telegram IDs)
- No hardcoded secrets
- Rate limiting (30/min, 500/hour per user)
- Cost limits (daily/monthly)
- Git hooks prevent token commits
- Input sanitization (XML escaping, injection detection)
- File path validation (prevent directory traversal)

## Troubleshooting

| Issue | Quick Fix | Details |
|-------|-----------|---------|
| **Bot not responding** | `./deploy.sh chat` | Check `tail -100 logs/bot.log \| grep ERROR` |
| **High costs** | `/usage` in Telegram | Or `cat data/cost_tracking.json \| jq` |
| **Task stuck** | `/stopall` in Telegram | Check dashboard or query DB |
| **Frontend not updating** | `./deploy.sh chat` | Hard refresh: Cmd+Shift+R |
| **Database issues** | See CLAUDE.md | Query examples for all scenarios |

### Common Commands

```bash
# Check logs for errors
tail -100 logs/bot.log | grep ERROR
tail -100 logs/monitoring.log | grep ERROR

# Restart all services
./deploy.sh chat

# Check if services are running
ps aux | grep -E "python.*(core/main.py|monitoring/server.py)" | grep -v grep

# Database queries
sqlite3 data/agentlab.db "SELECT task_id, status FROM tasks ORDER BY updated_at DESC LIMIT 10;"
```

## Built With

- Python 3.12+
- Claude API (Haiku 4.5) + Claude Code CLI (Sonnet 4.5, Opus 4.5)
- python-telegram-bot
- Flask (monitoring dashboard)
- React + TypeScript (chat frontend)
- Whisper (voice transcription)
- SQLite (data persistence)
- Playwright MCP (browser automation)

## Contributing

This is a personal project, but issues and suggestions are welcome via GitHub Issues.

### Development Workflow

1. **Fork and clone**
   ```bash
   git clone <your-fork-url>
   cd agentlab
   ```

2. **Set up environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pre-commit install
   cp .env.example .env  # Configure with your credentials
   ```

3. **Create feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

4. **Make changes with tests**
   - Write code following project conventions (see below)
   - **Tests are MANDATORY** - no exceptions
   - Place tests in `tests/test_<module>.py`
   - Run tests: `pytest tests/test_<module>.py -v`

5. **Run quality checks**
   ```bash
   pre-commit run --all-files  # Runs black, isort, ruff, bandit, pytest
   ```

6. **Commit and push**
   ```bash
   git add .
   git commit -m "Brief descriptive message"
   git push origin feature/your-feature-name
   ```

7. **Submit PR**
   - Describe changes and motivation
   - Reference any related issues
   - Ensure all CI checks pass

### Code Style

- **Python**: Black formatter (line length 120), isort for imports, ruff linting
- **Type hints**: Required for public APIs, encouraged elsewhere
- **Async by default**: All handlers use asyncio
- **Naming**: `snake_case` for files/functions, `PascalCase` for classes, `UPPER_SNAKE` for constants

### Testing Requirements

**All implementations MUST include tests:**
- **New features**: Unit tests (core logic) + integration tests (workflows)
- **Bug fixes**: Regression test (fails without fix, passes with fix)
- **Refactoring**: Existing tests must pass before and after

**Coverage targets**:
- Critical paths: 80%+
- Utility functions: 100%
- Handlers: Best effort
- Overall project: 70%+

**Running tests**:
```bash
pytest tests/ -v                                    # All tests
pytest tests/unit/ -v                               # Unit tests only
pytest tests/unit/test_formatter.py -v              # Specific module
pytest tests/ --cov=. --cov-report=html             # With coverage report
open htmlcov/index.html                             # View coverage in browser
```

**Coverage reports**:
- HTML reports: `htmlcov/index.html` (excluded from git)
- Terminal output: Use `--cov-report=term` flag
- Configuration: `.coveragerc` and `pyproject.toml`

### Project Conventions

- **File organization**: See `CLAUDE.md` for detailed structure
- **Commit messages**: Start with verb (Add/Fix/Update/Refactor), be specific
- **Documentation**: Update `docs/` for new features, keep `CLAUDE.md` in sync
- **Frontend changes**: Run `./deploy.sh chat` before committing (pre-commit enforced)
- **No root .md files**: Use `docs/` for documentation (except README.md and CLAUDE.md)

### Pre-commit Hooks

Hooks automatically run on `git commit`:
- **black**: Code formatting
- **isort**: Import sorting
- **ruff**: Linting
- **bandit**: Security checks
- **pytest**: Run tests on modified modules
- **secret detection**: Prevent token commits
- **chat-frontend-deploy**: Ensure frontend build is current

If hooks fail, fix issues and commit again.

### Debugging

**Check logs**:
```bash
tail -f logs/bot.log          # Main bot log
tail -f logs/monitoring.log   # Dashboard log
```

**Database queries**:
```bash
sqlite3 data/agentlab.db "SELECT task_id, status FROM tasks WHERE status = 'running';"
```

**Restart services**:
```bash
./deploy.sh chat  # Rebuilds and restarts everything
```

### Need Help?

- **Issues**: Open a GitHub issue for bugs or feature requests
- **Documentation**: See `CLAUDE.md` for comprehensive project context
- **Questions**: Use GitHub Discussions for general questions

## Resources

- [Claude Code Docs](https://docs.claude.com/claude-code)
- [Anthropic API Docs](https://docs.anthropic.com/)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)
- [Playwright MCP](https://github.com/microsoft/playwright)

## License

MIT License - See LICENSE file for details

---

**Status**: Production Ready | **Commits**: 589 | **Test Coverage**: 9,843 lines (41 modules) | **Agents**: 16

*Built to route the right work to the right model and keep costs reasonable.*
