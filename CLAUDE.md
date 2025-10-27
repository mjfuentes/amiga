# AMIGA - Claude Code Context

> Repository etiquette, conventions, and project-specific guidance for Claude Code agents.

## Project Overview

**AMIGA (Autonomous Modular Interactive Graphical Agent)** - Web-based chat interface with intelligent routing between Claude API (Haiku) for Q&A and Claude Code CLI (Sonnet) for coding tasks.

**Core Philosophy**: Right model for the right task. Fast & cheap for questions, powerful & thorough for code.

## Quick Reference: Component Locations

**The Chat Interface**: When users refer to "the chat" or "chat frontend," they mean:
- **Frontend**: `monitoring/dashboard/` (React + TypeScript)
- **Served at**: `http://localhost:3000` (root route)
- **Backend**: `monitoring/server.py` (WebSocket handlers for messaging)
- **Build output**: `static/chat/` (served by Flask)
- **Deployment**: Run `cd monitoring/dashboard && ./deploy.sh` after source changes

**Other Key Components**:
- **Monitoring Dashboard**: `templates/dashboard.html` (SSE-based metrics UI)
- **Claude Code Sessions**: `.claude/` (agent configs, hooks)
- **Playwright MCP**: Browser automation for frontend testing (see Playwright MCP Integration section)

## Quick Reference: Database & Log Access

**CRITICAL**: Before starting ANY task, check the database and logs for context.

### Database (SQLite)

**Location**: `data/agentlab.db`

**Tables**:
- `tasks` - Background task tracking and status
- `tool_usage` - Tool usage statistics with error tracking
- `sessions` - User conversation history (if exists)

**Schema**:
```sql
-- Tasks table
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending/running/completed/failed/stopped
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    model TEXT NOT NULL,
    workspace TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    session_uuid TEXT,     -- UUID for logs/sessions/<uuid>/
    result TEXT,
    error TEXT,
    pid INTEGER,
    activity_log TEXT,     -- JSON array
    workflow TEXT,
    context TEXT
);

-- Tool usage table
CREATE TABLE tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    duration_ms REAL,
    success BOOLEAN,
    error TEXT,
    error_category TEXT,
    parameters TEXT,       -- JSON blob
    screenshot_path TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_creation_tokens INTEGER,
    cache_read_tokens INTEGER
);
```

**Reading databases**:
```bash
# Pretty-print task as JSON
sqlite3 data/agentlab.db "SELECT json_object('task_id', task_id, 'status', status, 'error', error) FROM tasks WHERE task_id = 'abc123';" | jq

# Search for specific task
sqlite3 data/agentlab.db "SELECT task_id, status, description, error FROM tasks WHERE task_id = 'abc123';"

# Get active tasks only
sqlite3 data/agentlab.db "SELECT task_id, status, updated_at FROM tasks WHERE status = 'running';"

# Count tasks by status
sqlite3 data/agentlab.db "SELECT status, COUNT(*) as count FROM tasks GROUP BY status;"

# Get tool usage for task
sqlite3 data/agentlab.db "SELECT tool_name, timestamp, success, error FROM tool_usage WHERE task_id = 'abc123' ORDER BY timestamp DESC LIMIT 10;"
```

**Common queries**:
```bash
# Find errors in task tracking
sqlite3 data/agentlab.db "SELECT task_id, error, updated_at FROM tasks WHERE error IS NOT NULL ORDER BY updated_at DESC LIMIT 10;"

# Get tool usage summary
sqlite3 data/agentlab.db "SELECT tool_name, COUNT(*) as count, SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures FROM tool_usage GROUP BY tool_name ORDER BY count DESC;"

# Get error categories
sqlite3 data/agentlab.db "SELECT error_category, COUNT(*) as count FROM tool_usage WHERE error IS NOT NULL GROUP BY error_category ORDER BY count DESC;"

# Find hung tasks (running but updated >1 hour ago)
sqlite3 data/agentlab.db "SELECT task_id, status, updated_at, julianday('now') - julianday(updated_at) as hours_stale FROM tasks WHERE status = 'running' AND julianday('now') - julianday(updated_at) > 0.042;"

# Get session UUID for task (needed for log lookup)
sqlite3 data/agentlab.db "SELECT session_uuid FROM tasks WHERE task_id = 'abc123';"
```

### Log Files

**Location**: `logs/`

**Files**:
- `logs/bot.log` - Main application log (auto-rotated)
- `logs/monitoring.log` - Web dashboard log
- `logs/sessions/<session_uuid>/` - Per-session Claude Code logs
  - `pre_tool_use.jsonl` - Tool invocations (always present)
  - `post_tool_use.jsonl` - Tool results (may not exist for all sessions)
  - `summary.json` - Session summary (may not exist for all sessions)

**Reading logs**:
```bash
# Tail main bot log
tail -f logs/bot.log

# Last 100 lines
tail -100 logs/bot.log

# Search for errors
grep ERROR logs/bot.log | tail -50

# Search for specific user activity
grep "User 123456" logs/bot.log | tail -50

# Search for specific error pattern
grep -i "timeout\|exception\|failed" logs/bot.log | tail -50

# View session-specific logs (requires session_uuid from database)
# Step 1: Get session UUID for task
session_uuid=$(sqlite3 data/agentlab.db "SELECT session_uuid FROM tasks WHERE task_id = 'abc123';")

# Step 2: Check if session directory exists
if [ -d "logs/sessions/$session_uuid" ]; then
    # List available log files
    ls -la "logs/sessions/$session_uuid/"

    # View tool invocations
    tail -100 "logs/sessions/$session_uuid/pre_tool_use.jsonl" | jq

    # View tool results (if exists)
    if [ -f "logs/sessions/$session_uuid/post_tool_use.jsonl" ]; then
        tail -100 "logs/sessions/$session_uuid/post_tool_use.jsonl" | jq
    fi
fi
```

**Log levels and what they mean**:
- **DEBUG**: Detailed flow, tool calls, state changes (verbose)
- **INFO**: User actions, task lifecycle, API calls (normal operations)
- **WARNING**: Recoverable issues, rate limits, retries (investigate if frequent)
- **ERROR**: Failures, exceptions, blocked operations (needs attention)

**Common log patterns**:
```bash
# Find all task failures
grep "Task.*failed" logs/bot.log

# Find API errors
grep "API error\|rate limit\|timeout" logs/bot.log

# Find security issues
grep "sanitize\|injection\|blocked" logs/bot.log

# Find cost limit issues
grep "cost limit" logs/bot.log

# Track task lifecycle
grep "task_id=abc123" logs/bot.log
```

**WORKFLOW**: When debugging or starting a new task:
1. Check `data/agentlab.db` (tasks table) for related active/failed tasks
2. Check `logs/bot.log` for recent errors
3. Get session UUID from database, then check session logs in `logs/sessions/<session_uuid>/`
4. Check `data/agentlab.db` (tool_usage table) for tool performance issues

## Repository Conventions

### Python Style

- **Formatter**: Black (line length 120)
- **Import order**: isort
- **Linter**: Ruff
- **Type hints**: Required for public APIs, encouraged elsewhere
- **Async by default**: All handlers and long-running operations use asyncio

### Chat Frontend Workflow

**CRITICAL**: Changes to `monitoring/dashboard/src/` require deployment to `static/chat/`.

**Deployment script**: Centralized `deploy.sh` at project root
```bash
# From project root
./deploy.sh chat  # Builds, deploys, and restarts all services (bot + monitoring)
./deploy.sh       # Deploy all components + restart services
```

**What deploy.sh does**:
- Stops launchd service if running
- Kills existing monitoring server process
- Builds React frontend (if chat component)
- Deploys build to `static/chat/`
- Restarts monitoring server (with venv Python + PYTHONPATH)
- Verifies service started successfully

**Pre-commit enforcement**: Hook `chat-frontend-deploy` blocks commits if:
- Source files in `monitoring/dashboard/src/` modified
- Build in `static/chat/` is outdated

**Workflow**:
1. Modify source: `monitoring/dashboard/src/*.tsx`, `*.css`
2. Deploy: `./deploy.sh chat` (from project root)
3. Script automatically: builds, deploys, restarts all services
4. Hard refresh browser: Cmd+Shift+R to clear cache
5. Commit: Pre-commit hook verifies deployment

**Deployment options**:
- `./deploy.sh` - Deploy all components (chat + verify dashboard) + restart monitoring server
- `./deploy.sh chat` - Deploy chat only + restart monitoring server (recommended)
- `./deploy.sh dashboard` - Verify dashboard templates only (no restart)

**Why this matters**:
- Flask serves static files from `static/chat/`
- React builds have content hashes (e.g., `main.987fad4a.css`)
- Old builds remain cached without deployment
- Browser caches old assets until hard refresh

**Legacy script**: `monitoring/dashboard/deploy.sh` still works but use centralized script for consistency

### File Organization

```
agentlab/
├── core/                # Core bot functionality
│   ├── main.py          # Entry point - bot setup, command handlers
│   ├── routing.py       # Message routing logic
│   ├── session.py       # Conversation history management
│   ├── config.py        # Configuration management
│   └── orchestrator.py  # Task orchestration
├── claude/              # Claude AI integration
│   ├── api_client.py    # Claude API (Haiku - Q&A routing)
│   └── code_cli.py      # Claude Code CLI sessions (Sonnet - coding)
├── monitoring/          # Dashboard & metrics
│   ├── server.py        # Web dashboard (Flask + SSE)
│   ├── metrics.py       # Real-time metrics from hooks
│   ├── hooks_reader.py  # Hook data parsing
│   └── dashboard/       # React chat UI (TypeScript)
│       ├── src/         # Source files (*.tsx, *.css)
│       ├── build/       # Build output (npm run build)
│       └── deploy.sh    # Deploy script (build → static/chat)
├── tasks/               # Task management
│   ├── manager.py       # Background task tracking
│   ├── pool.py          # Bounded worker pool for async execution
│   ├── database.py      # Database operations
│   ├── analytics.py     # Analytics & usage tracking
│   ├── tracker.py       # Tool usage tracking
│   └── enforcer.py      # Workflow enforcement
├── utils/               # Shared utilities
│   ├── git.py           # Git operations
│   ├── log_formatter.py # Log formatting
│   ├── log_analyzer.py  # Log analysis
│   ├── log_monitor.py   # Log monitoring
│   ├── helpers.py       # General helpers
│   └── worktree.py      # Git worktree management
├── tests/               # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py
│   └── test_*.py        # All test files
├── scripts/             # Utility scripts
│   ├── analyze_*.py     # Analysis scripts
│   ├── migrate_*.py     # Migration scripts
│   └── check_*.py       # Validation scripts
├── docs/                # Documentation
│   └── *.md             # Implementation notes, feature docs
├── .claude/             # Claude Code configuration
│   ├── agents/          # Agent definitions
│   │   ├── orchestrator.md            # Task coordinator
│   │   ├── code_agent.md              # Backend implementation (Sonnet 4.5)
│   │   ├── frontend_agent.md          # UI/UX development (Sonnet 4.5)
│   │   ├── research_agent.md          # Analysis & proposals (Opus 4.5)
│   │   ├── Jenny.md                   # Spec verification
│   │   ├── claude-md-compliance-checker.md  # Project compliance
│   │   ├── code-quality-pragmatist.md       # Complexity detection
│   │   ├── karen.md                   # Reality checks
│   │   ├── task-completion-validator.md     # Functional validation
│   │   ├── ui-comprehensive-tester.md       # UI testing
│   │   └── ultrathink-debugger.md           # Deep debugging (Opus 4.5)
│   ├── hooks/           # Tool usage tracking (pre/post-tool-use, session-end)
│   └── settings.local.json  # Permissions, output style
├── data/                # Runtime state (sessions, tasks, costs)
├── logs/                # Application logs
├── static/              # Static assets served by Flask
│   └── chat/            # Deployed dashboard build
└── templates/           # Jinja templates for web UI
```

### Agent Architecture

#### Core Agents
- **orchestrator**: Coordinates tasks, delegates to specialized agents
- **code_agent**: Backend implementation (Python, Sonnet 4.5)
- **frontend_agent**: UI/UX development (HTML/CSS/JS, Sonnet 4.5) with Playwright MCP for browser testing
- **research_agent**: Analysis, proposals, web research (Opus 4.5)

#### Quality Assurance Agents
- **Jenny**: Verifies implementation matches specifications
- **claude-md-compliance-checker**: Ensures CLAUDE.md adherence
- **code-quality-pragmatist**: Detects over-engineering
- **karen**: Reality check on project completion
- **task-completion-validator**: Validates tasks actually work
- **ui-comprehensive-tester**: Comprehensive UI testing with Playwright MCP
- **ultrathink-debugger**: Deep debugging (Opus 4.5 - expensive, use sparingly)

#### Self-Improvement Agent
- **self-improvement-agent**: Analyzes error patterns from database, updates agent prompts based on real failures, creates tasks for code fixes. Manually triggered to learn from mistakes.

#### Agent Workflow Examples

**Code Implementation Flow:**
1. orchestrator receives task
2. research_agent (if research needed)
3. code_agent (implementation)
4. task-completion-validator (verify it works)
5. code-quality-pragmatist (check complexity)
6. claude-md-compliance-checker (verify CLAUDE.md compliance)

**Bug Investigation Flow:**
1. orchestrator receives bug report
2. ultrathink-debugger (deep root cause analysis)
3. code_agent (implement fix)
4. task-completion-validator (verify fix works)

**Spec Verification Flow:**
1. orchestrator receives verification request
2. Jenny (compare implementation vs specs)
3. task-completion-validator (if gaps found, verify fixes)

**Self-Improvement Flow:**
1. User manually triggers: "analyze recent errors and improve"
2. self-improvement-agent queries SQLite database
3. Identifies error patterns (last 7 days)
4. For each pattern:
   - If prompt issue → updates agent configuration
   - If code issue → creates task for code fix
5. Updates CHANGELOG with analysis
6. Returns summary of improvements made

### Playwright MCP Integration

**Purpose**: Cross-browser automation and testing for frontend development and UI validation.

**Installation**:
```bash
claude mcp add playwright npx -s user @playwright/mcp@latest -- --isolated
```

**Configuration**: `~/.claude.json` (user-level MCP server)

**Important**: The `--isolated` flag keeps the browser profile in memory without saving to disk. When the browser closes, all session state (cookies, localStorage, cache) is permanently cleared, ensuring each session starts fresh without cross-session state leakage.

**Available to**: `frontend_agent`, `ui-comprehensive-tester`

**Key Features**:
- Cross-browser support (Chromium, Firefox, WebKit)
- Accessibility tree inspection via snapshots
- Isolated browser contexts for parallel testing
- Headed and headless modes
- Network request monitoring
- Console message capture
- Screenshot and PDF generation

**Tool Categories**:

**Navigation & Interaction**:
- `mcp__playwright__browser_navigate` - Navigate to URLs
- `mcp__playwright__browser_navigate_back` - Go back in history
- `mcp__playwright__browser_click` - Click elements
- `mcp__playwright__browser_type` - Type text into inputs
- `mcp__playwright__browser_fill_form` - Fill entire forms
- `mcp__playwright__browser_select_option` - Select dropdown options
- `mcp__playwright__browser_hover` - Hover over elements
- `mcp__playwright__browser_press_key` - Press keyboard keys
- `mcp__playwright__browser_drag` - Drag and drop elements
- `mcp__playwright__browser_file_upload` - Upload files
- `mcp__playwright__browser_handle_dialog` - Handle alerts/confirms/prompts

**Inspection & Testing**:
- `mcp__playwright__browser_take_screenshot` - Capture screenshots (use JPEG format with quality 75-85)
- `mcp__playwright__browser_snapshot` - Capture accessibility tree (semantic DOM structure)
- `mcp__playwright__browser_evaluate` - Run JavaScript in page context
- `mcp__playwright__browser_console_messages` - Monitor console output
- `mcp__playwright__browser_network_requests` - Track network activity
- `mcp__playwright__browser_wait_for` - Wait for conditions (elements, navigation, timeouts)

**Browser Management**:
- `mcp__playwright__browser_tabs` - Manage multiple tabs
- `mcp__playwright__browser_resize` - Change viewport size for responsive testing
- `mcp__playwright__browser_close` - Close browser/pages
- `mcp__playwright__browser_save_as_pdf` - Generate PDFs

**Common Workflows**:

**Visual Validation**:
1. Navigate to implementation: `browser_navigate("http://localhost:3000")`
2. Take screenshot: `browser_take_screenshot(format="jpeg", quality=80)`
3. Navigate to reference: `browser_navigate("https://example.com")`
4. Take reference screenshot: `browser_take_screenshot(format="jpeg", quality=80)`
5. Compare visually

**Form Testing**:
1. Navigate to form page
2. Fill form: `browser_fill_form(selector, data)`
3. Take screenshot of filled state
4. Submit and verify response
5. Check console for errors: `browser_console_messages()`

**Responsive Testing**:
1. Desktop: `browser_resize(1920, 1080)` → screenshot
2. Tablet: `browser_resize(768, 1024)` → screenshot
3. Mobile: `browser_resize(375, 667)` → screenshot
4. Verify layout adapts correctly

**Accessibility Validation**:
1. Navigate to page
2. Take snapshot: `browser_snapshot()` (captures accessibility tree)
3. Verify semantic structure (headings, landmarks, roles)
4. Check ARIA attributes and keyboard navigation

**Screenshot Best Practices**:
- **Always use JPEG format with quality parameter** (not PNG)
- Recommended quality: 75-85 (balance of visual fidelity and file size)
- PNG is 5-10x larger than JPEG for UI screenshots
- Only use PNG when transparency or pixel-perfect accuracy is critical

**Browser Contexts**:
- Each context is isolated (cookies, localStorage, sessionStorage)
- Use for testing different authentication states
- Parallel testing scenarios without interference
- Clean slate for each test run

**Troubleshooting**:
- If MCP tools unavailable: Verify Playwright MCP server is configured in `~/.claude.json`
- Check server status: Tools should appear with `mcp__playwright__*` prefix
- Ensure Node.js and npx are installed for MCP server runtime

### Naming Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private**: Prefix with `_` (not enforced but encouraged)

### Test Files

**Location**: `tests/`

**Naming**: `test_*.py` for pytest discovery

**Structure**:
```
tests/
├── __init__.py          # Test suite documentation
├── conftest.py          # pytest configuration
├── test_formatter.py    # Unit tests for messaging/formatter.py
├── test_queue.py        # Unit tests for messaging/queue.py
└── ...
```

**Running tests**:
```bash
# All tests
pytest tests/

# Specific module
pytest tests/test_formatter.py

# With coverage
pytest tests/ --cov=.
```

**IMPORTANT**: All test files go in `tests/` directory at the project root.

**Imports**: Tests use standard imports:
```python
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from messaging.formatter import ResponseFormatter
```

### Testing Policy

**CRITICAL: Tests are MANDATORY for all implementations. NO EXCEPTIONS.**

**Test requirements by task type**:
- **New features**: Unit tests (core logic) + integration tests (workflows)
- **Bug fixes**: Regression test (fails without fix, passes with fix)
- **Refactoring**: Existing tests must pass before and after
- **API changes**: Test all endpoints + error cases
- **Utility functions**: Test edge cases, errors, typical inputs

**Coverage targets**:
- Critical paths: 80%+ coverage
- Utility functions: 100% coverage
- Handlers: Best effort

**Testing workflow** (enforced by agents):
1. Implement feature/fix
2. Write tests in `tests/test_<module>.py`
3. Run tests: `pytest tests/test_<module>.py -v`
4. Fix failures until all pass
5. Run full suite: `pytest tests/`
6. Commit implementation + tests together

**Quality gates**:
- **code_agent**: MUST write tests before committing
- **task-completion-validator**: REJECTS implementations without tests or with failing tests
- **Pre-commit hooks**: Run pytest on modified modules

**Test structure template**:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from module_name import function_to_test

class TestFeatureName:
    def test_typical_case(self):
        result = function_to_test(input)
        assert result == expected

    def test_edge_case(self):
        # Test boundary conditions
        pass

    def test_error_handling(self):
        with pytest.raises(ExpectedError):
            function_to_test(invalid_input)
```

**Why mandatory testing?**:
- Prevents regressions (bug fixes need regression tests)
- Documents expected behavior
- Enables confident refactoring
- Maintains code quality at scale
- Enforced by task-completion-validator agent (automatic rejection without tests)

### Module Documentation

**Location**: `docs/`

**Purpose**: Project-wide technical documentation

**Examples**:
- Feature design documents
- Implementation notes
- API documentation
- Architecture documentation

**Distinction**:
- `docs/`: All project documentation
- **Root `.md` files**: ONLY `README.md` and `CLAUDE.md` are allowed

### Analysis and Investigation Files

**CRITICAL**: Do NOT create .md files in project root (except README.md and CLAUDE.md)

**Location**: `docs/analysis/` for analysis/investigation documents

**Naming**:
- Analysis docs: `docs/analysis/*_ANALYSIS.md`, `docs/analysis/*_INVESTIGATION.md`
- Analysis scripts: `analyze_*.py` (project root is OK for scripts)

**Examples**:
- `docs/analysis/TOOL_USAGE_ANALYSIS.md` - Investigation results
- `docs/analysis/ERROR_TRACKING_INVESTIGATION.md` - Error analysis
- `analyze_tool_usage.py` - Analysis script (root OK)

**Purpose**: One-time investigations, not permanent documentation

**Pre-commit enforcement**: A pre-commit hook blocks new .md files in root (except README.md and CLAUDE.md)

### Git Workflow

**CRITICAL**: Always commit after code changes.

```bash
# Standard workflow
git add <modified_files>
git commit -m "Brief descriptive message

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Commit message style**:
- Start with verb: "Add", "Fix", "Update", "Refactor"
- Be specific: "Fix null pointer in auth.py:42" not "Fix bug"
- Reference file:line when applicable

**Never commit**:
- `.env` files (use `.env.example`)
- `data/*` (runtime state)
- `logs/*` (application logs)
- `__pycache__/`, `*.pyc`

### Worktree Management (Updated 2025-10-22)

**Current approach**: Workflows handle worktrees explicitly via git-worktree agent.

**Workflow integration**:
- Step 0: `git-worktree create-worktree` - Create isolated worktree
- Step 1-N: Implementation work
- Step N: `git-merge` - Merge branch to main
- **Cleanup disabled**: Worktrees preserved in `/tmp/agentlab-worktrees/` for debugging
- Manual cleanup available via `git-worktree cleanup-worktree` (only when user requests)

**Rationale for disabled cleanup**:
- Preserves worktrees for post-task analysis and debugging
- Allows inspection of task-specific state after completion
- Worktrees automatically cleared on system restart (in /tmp/)
- Manual cleanup still available when explicitly needed

**Deprecated**: `WorktreeManager` class (automatic worktree creation in session pool)

See `.claude/agents/git-worktree.md` for details.

### Pre-commit Hooks

**Installed**: black, isort, ruff, bandit, pytest, secret detection

**Before committing**: Hooks run automatically. Fix any failures before proceeding.

**Manual run**: `pre-commit run --all-files`

### Plan Mode Workflow

**Purpose**: Separate research/planning from execution for safer, higher-quality implementations.

**When to Use**:
- Complex multi-file changes
- Architectural decisions
- Performance optimizations
- Security-critical modifications
- Any task requiring deep analysis

**The 4-Phase Workflow**:

#### 1. Explore Phase (Context Loading)
- Read relevant documentation and code
- Understand existing patterns and constraints
- Map out dependencies and impacts
- **NO file modifications in this phase**

#### 2. Plan Phase (Analysis & Design)
- Use `ultrathink` keyword for maximum thinking budget (31,999 tokens)
- Generate comprehensive implementation plan
- Consider multiple approaches with trade-offs
- Document assumptions and risks
- **Output**: Detailed plan for human review

#### 3. Code Phase (Implementation)
- Execute the approved plan methodically
- Self-check against plan at each step
- Handle edge cases identified in planning
- Maintain clear audit trail of changes

#### 4. Commit Phase (Verification)
- Validate implementation matches plan
- Run tests and verify functionality
- Create descriptive commit messages
- Update documentation if needed

**Ultrathink Usage**:
```
# In agent prompts or commands
"Use ultrathink to analyze the performance bottleneck..."
"Apply ultrathink to design the refactoring strategy..."
```

**Plan Artifacts**:
Store significant plans in `docs/plans/` for:
- Audit trail and compliance
- Team knowledge sharing
- Future reference
- CI/CD integration

**Integration with Agents**:
- **orchestrator**: Coordinates plan mode phases
- **research_agent**: Uses ultrathink for deep analysis
- **ultrathink-debugger**: Applies maximum thinking to bug investigation
- **Jenny**: Validates implementation against plan

**Example Workflow**:
```
User: "Refactor the authentication system for better security"
1. Orchestrator enters plan mode
2. Research_agent explores current implementation (ultrathink)
3. Generated plan reviewed by user
4. Code_agent implements approved plan
5. Task-completion-validator verifies functionality
6. Changes committed with plan reference
```

## Development Environment Setup

### Initial Setup

```bash
# Clone repo
git clone <repo_url>
cd agentlab

# Install system dependencies
brew install jq  # Required: JSON processor used by hooks and CLI operations

# Create venv (Python 3.12+)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install pre-commit
pre-commit install

# Configure environment
cp .env.example .env
# Edit .env with your tokens
```

### Required Environment Variables

```bash
ANTHROPIC_API_KEY        # For Claude API (Haiku)
WORKSPACE_PATH           # Base path for repositories (/Users/matifuentes/Workspace)
```

### Optional Environment Variables

```bash
DAILY_COST_LIMIT=100             # Stop at $100/day
MONTHLY_COST_LIMIT=1000          # Stop at $1000/month
SESSION_TIMEOUT_MINUTES=60       # Clear inactive sessions
ANTHROPIC_ADMIN_API_KEY          # For usage API sync (optional)
LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR
```

### Running the Application

**Recommended (production-like)**:
```bash
# Deploy and start monitoring server
./deploy.sh chat

# Service runs in background
# Access: http://localhost:3000 (chat UI), http://localhost:3000/dashboard (metrics dashboard)
# Logs: tail -f logs/monitoring.log
```

**Manual (development)**:
```bash
# Activate venv
source venv/bin/activate

# Run monitoring server (includes chat interface)
python monitoring/server.py
# Open http://localhost:3000
```

**Notes**:
- `deploy.sh` handles PYTHONPATH setup automatically
- Manual mode requires running from project root for imports to work
- Manual mode runs service in foreground (good for debugging)

## Project-Specific Patterns

### Security: Input Sanitization

**CRITICAL**: All user input goes through sanitization before Claude API calls.

```python
# In claude/api_client.py
safe_query = sanitize_xml_content(user_query)  # HTML escape + pattern removal
is_malicious, reason = detect_prompt_injection(user_query)  # Detect attacks
validate_file_path(path, base_path)  # Prevent directory traversal
```

**Why**: User input is embedded in XML prompts. Unsanitized input could break prompt structure or inject instructions.

### Cost Optimization

**Token minimization** in `claude/api_client.py`:
- Conversation history: Last 2 messages only, truncate to 500 chars
- Active tasks: Max 3 tasks, omit descriptions
- Logs: Last 50 lines only (not 200)
- Don't include `available_repositories` list (~100 tokens saved)

**Model selection**:
- Haiku 4.5 for Q&A (10x cheaper)
- Sonnet 4.5 for coding (more capable)
- Opus 4.5 for research_agent and ultrathink-debugger (most capable, most expensive)

**Cost-aware agent usage**:
- research_agent (Opus): Use for complex analysis only
- ultrathink-debugger (Opus): Reserve for critical bugs and deep debugging
- Other agents (Sonnet/inherited): Standard usage

**Model specification rationale**:
- Explicit model specifications added to agents for cost predictability
- code_agent, frontend_agent: Sonnet 4.5 for balance of capability/cost
- research_agent: Opus 4.5 for comprehensive research and analysis
- ultrathink-debugger: Opus 4.5 for deep reasoning in complex debugging

### Background Task Format

**CRITICAL**: Responses from Claude API using BACKGROUND_TASK must follow exact format:

```
BACKGROUND_TASK|task_description|user_message
```

**Rules**:
- Single line, pipe-delimited
- NO markdown code blocks
- NO extra text before/after
- `task_description`: Internal use (what needs doing)
- `user_message`: Shown to user immediately

**Parsing**: `claude/api_client.py` looks for `BACKGROUND_TASK|` anywhere in response, strips markdown blocks, splits on `|`.

### Session Management

**Per-user isolation**: Each web user has independent:
- Conversation history (`core/session.py`)
- WebSocket connection
- Cost tracking
- Active tasks

**History limits**:
- Max 10 messages in memory
- Cleared on session timeout

### Agent Communication

**Orchestrator → Agent**:
```python
await agent_pool.submit(
    execute_background_task,
    task_id=task.id,
    task_description=description,
    user_id=user_id
)
```

**Agent → User**:
- Agents return summary strings
- Orchestrator aggregates results
- Server sends via WebSocket to chat UI

### Logging Strategy

**Structured logging** with context:

```python
logger.info(f"User {user_id}: {action} - {details}")
logger.error(f"Error in {component}: {error}", exc_info=True)
```

**Log levels**:
- DEBUG: Detailed flow, tool calls, state changes
- INFO: User actions, task lifecycle, API calls
- WARNING: Recoverable issues, rate limits, retries
- ERROR: Failures, exceptions, blocked operations

**Log location**: `logs/bot.log` (auto-rotated)

## Common Pitfalls

### 1. **Modifying Running Code**

**Problem**: The bot runs `core/main.py`. Modifying it while running causes unpredictable behavior.

**Solution**: Make changes, commit, then user must `/restart` for changes to take effect.

### 2. **Async/Await Forgotten**

**Problem**: Calling async functions without `await` returns coroutine objects, not results.

**Example**:
```python
# ❌ Wrong
result = async_function()

# ✅ Correct
result = await async_function()
```

### 3. **Uncommitted Changes**

**Problem**: Agents make changes but forget to commit. Git tracker blocks work on other repos.

**Solution**: `code_agent` ALWAYS commits after file modifications. Check `.claude/agents/code_agent.md` for policy.

### 4. **Token Bloat in API Calls**

**Problem**: Including full conversation history or all logs wastes tokens and increases cost.

**Solution**: Strict limits in `claude/api_client.py`:
- History: Last 2 messages, 500 chars each
- Logs: Last 50 lines
- Tasks: Max 3, no descriptions

### 5. **Background Task Format Errors**

**Problem**: Claude API returns BACKGROUND_TASK wrapped in markdown or with extra text.

**Example**:
```markdown
# ❌ Wrong
Here's the task:
```
BACKGROUND_TASK|Fix bug|Fixing the bug
```

# ✅ Correct
BACKGROUND_TASK|Fix bug|Fixing the bug
```

**Solution**: Check `claude/api_client.py` system prompt - instructs to return ONLY the pipe-delimited line.

### 6. **Tool Permission Violations**

**Problem**: Agents attempt restricted operations (e.g., `rm -rf`).

**Solution**: Check `.claude/settings.local.json` for allowed/denied commands. Add to allow list if needed.

## Testing

### Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html
```

### Test Structure

Tests in `tests/test_*.py`

**Coverage targets**:
- Critical paths: 80%+
- Utility functions: 100%
- Handlers: Best effort

**Mocking**: Use `unittest.mock` for external APIs (Telegram, Anthropic)

### Test Data

- No real API keys in tests
- Use fixtures for common setups
- Temporary directories for file operations

## Monitoring & Debugging

### Dashboard

**URL**: http://localhost:3000 (when `monitoring_server.py` running)

**Features**:
- Running tasks (click for live tool usage)
- Recent errors
- 24h API costs
- Tool usage stats

**Tech**: Flask + SSE for real-time updates

### Hook System

**Location**: `~/.claude/hooks/`

**Hooks**:
- `pre-tool-use`: Logs before tool execution
- `post-tool-use`: Logs results/errors
- `session-end`: Aggregates summary

**Data**: Written to JSONL logs + JSON databases

**Reading**: `hooks_reader.py` parses for metrics dashboard

### Cost Tracking

**File**: `data/cost_tracking.json`

**Command**: `/usage` in Telegram

**Tracking**:
- Per-model costs (Haiku, Sonnet)
- Daily/monthly totals
- Usage breakdown by operation type

**Limits**: Set `DAILY_COST_LIMIT` and `MONTHLY_COST_LIMIT` in `.env`

## Unexpected Behaviors

### Voice Input Transcription

**Issue**: Whisper transcription not always perfect (especially project names).

**Mitigation**: `claude/api_client.py` system prompt instructs permissiveness with voice input. Orchestrator does fuzzy matching on repo names.

**Example**: "group therapy" → matches "groovetherapy" or "group-therapy"

### Claude Code CLI Timeouts

**Issue**: Complex tasks can take >5 minutes, exceeding default timeout.

**Solution**: Timeout set to 300s (5 min) in `claude/code_cli.py`. For longer tasks, use `--timeout` flag.

### Agent Pool Blocking

**Issue**: All 3 workers busy → new tasks queue indefinitely.

**Current**: Basic queue, no priority
**Future**: Priority queue for urgent vs background (see TODO #2)

### Git Dirty State Blocking

**Issue**: Uncommitted changes in one repo block work on other repos (defensive measure).

**Solution**: `code_agent` always commits. If stuck, check `git status` in affected repos.

## Troubleshooting Commands

```bash
# Check logs for errors
tail -100 logs/monitoring.log | grep ERROR

# Restart monitoring server
./deploy.sh chat

# Stop service manually
pkill -9 -f "python.*monitoring/server.py"

# Check if service is running
ps aux | grep "python.*monitoring/server.py" | grep -v grep

# Check running tasks
# Monitoring dashboard: http://localhost:3000

# Check cost usage
cat data/cost_tracking.json | jq

# Check agent pool status
# Monitoring dashboard: http://localhost:3000

# Access chat interface
# Open: http://localhost:3000
```

## Performance Optimization

### Token Reduction

**Current optimizations** in `claude/api_client.py`:
- ✅ History truncation (last 2 messages, 500 chars)
- ✅ Log truncation (last 50 lines)
- ✅ Task truncation (max 3)
- ✅ Omit repos list

**Future**:
- TODO: Semantic compression of history
- TODO: Smart log filtering (errors only)

### Response Speed

**Haiku 4.5**: 1-2s for Q&A
**Sonnet 4.5**: 5-60s for coding tasks

**Optimization**: Route correctly. Don't use Sonnet for simple questions.

### Agent Pool

**Current**: 3 workers, basic queue

**Future** (see TODOs):
- Priority queue
- Dynamic scaling (reduce workers under load)
- Task timeout/cancellation

## Resources

### Documentation

- [Claude Code Docs](https://docs.claude.com/claude-code)
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Anthropic API Docs](https://docs.anthropic.com/)

### Internal Docs

- `README.md` - Project overview, quick start
- `docs/archive/AGENT_ARCHITECTURE.md` - Detailed agent system design
- `.claude/agents/*.md` - Agent configurations

### External Tools

- Claude Code CLI: `claude --help`
- Pre-commit hooks: `pre-commit run --help`
- Monitoring dashboard: `http://localhost:3000`

---

**Last Updated**: 2025-10-23
**Maintained By**: Matias Fuentes
**Claude Code Version**: Latest (Sonnet 4.5)
