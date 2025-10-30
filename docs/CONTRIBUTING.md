# Contributing to AMIGA

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Development Workflow](#development-workflow)
3. [Testing Policy](#testing-policy)
4. [Pull Request Process](#pull-request-process)
5. [Architecture Guidelines](#architecture-guidelines)
6. [Commit Message Format](#commit-message-format)
7. [Code Review Checklist](#code-review-checklist)

## Getting Started

### Prerequisites

Before you begin, ensure you have:

- Python 3.12 or higher
- [Claude Code CLI](https://docs.claude.com/claude-code) installed
- Anthropic API key
- Node.js and npm (for frontend development)
- jq (JSON processor) - `brew install jq` on macOS
- SQLite (for database queries)

### Fork and Clone

```bash
# Fork the repository on GitHub
# Clone your fork
git clone https://github.com/YOUR_USERNAME/amiga.git
cd amiga

# Add upstream remote
git remote add upstream https://github.com/ORIGINAL_OWNER/amiga.git
```

### Development Environment Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install pre-commit hooks
pre-commit install

# Configure environment
cp .env.example .env
# Edit .env with your credentials:
# - ANTHROPIC_API_KEY (from Anthropic Console)
# - WORKSPACE_PATH (path to your workspace directory)
# Optional:
# - DAILY_COST_LIMIT (default: $100/day)
# - MONTHLY_COST_LIMIT (default: $1000/month)
```

### Running AMIGA Locally

```bash
# Deploy and start services (recommended)
./deploy.sh chat

# Access the application:
# - Chat Interface: http://localhost:3000
# - Monitoring Dashboard: http://localhost:3000/dashboard

# View logs
tail -f logs/monitoring.log
```

**Alternative (manual development mode)**:
```bash
# Activate virtual environment
source venv/bin/activate

# Run monitoring server (includes chat interface)
python monitoring/server.py
# Access: http://localhost:3000
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_formatter.py -v

# Run with coverage report
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html  # View coverage report
```

## Development Workflow

### Branch Naming Conventions

Create descriptive branch names following these patterns:

```bash
# New features
git checkout -b feature/add-voice-transcription
git checkout -b feature/implement-cost-tracking

# Bug fixes
git checkout -b fix/message-queue-deadlock
git checkout -b fix/null-pointer-in-session

# Documentation
git checkout -b docs/update-architecture-guide
git checkout -b docs/add-testing-examples

# Refactoring
git checkout -b refactor/split-main-module
git checkout -b refactor/improve-error-handling
```

### Code Style Requirements

This project enforces strict code quality standards:

#### Formatting
- **Black**: Line length 120 characters
- **isort**: Import sorting with Black profile
- All Python files must pass formatting checks

```bash
# Format code
black telegram_bot/ --line-length=120
isort telegram_bot/ --profile=black --line-length=120
```

#### Linting
- **Ruff**: Fast, comprehensive linting
- **Bandit**: Security vulnerability scanning
- Fix all linting errors before committing

```bash
# Run linter
ruff check telegram_bot/ --fix

# Run security scan
bandit -r telegram_bot/ -c pyproject.toml
```

#### Type Hints
- **Required** for all public APIs (exported functions, classes)
- **Encouraged** for internal functions
- Use standard typing module conventions

```python
# Good - Type hints for public API
def process_message(user_id: int, text: str) -> dict[str, Any]:
    """Process a user message and return response."""
    ...

# Acceptable - Type hints for internal function
def _sanitize_input(text: str) -> str:
    """Internal helper for sanitizing text."""
    ...
```

#### Async/Await
- Use `async def` for all handlers and long-running operations
- Always `await` async function calls
- Follow asyncio best practices

```python
# Good
async def handle_message(update: Update) -> None:
    result = await async_operation()
    await send_response(result)

# Bad - Missing await
async def handle_message(update: Update) -> None:
    result = async_operation()  # Returns coroutine, not result!
```

### Pre-commit Hook Workflow

Pre-commit hooks run automatically on `git commit`. They enforce:

1. **Code Formatting**: Black, isort
2. **Linting**: Ruff, Bandit
3. **Testing**: pytest on modified modules
4. **Security**: Secret detection, vulnerability scanning
5. **File Checks**: YAML/JSON validation, trailing whitespace

```bash
# Hooks run automatically on commit
git commit -m "Add feature"

# Run manually on all files
pre-commit run --all-files

# Skip hooks (not recommended, only for emergency fixes)
git commit --no-verify -m "Emergency fix"
```

If hooks fail:
1. Fix the reported issues
2. Stage the fixes: `git add <files>`
3. Commit again

## Testing Policy

**CRITICAL: Tests are MANDATORY for all implementations. NO EXCEPTIONS.**

### Test Requirements by Task Type

| Task Type | Required Tests |
|-----------|----------------|
| **New Features** | Unit tests (core logic) + Integration tests (workflows) |
| **Bug Fixes** | Regression test (fails without fix, passes with fix) |
| **Refactoring** | All existing tests must pass before AND after |
| **API Changes** | Test all endpoints + error cases |
| **Utility Functions** | Test edge cases, errors, typical inputs |

### Coverage Targets

- **Overall project**: 70%+ coverage
- **Critical paths**: 80%+ coverage
- **Utility functions**: 100% coverage recommended
- **Handlers**: Best effort (harder to test, but try)

### Testing Workflow

**Every contribution MUST follow this workflow:**

1. **Implement** your feature or fix
2. **Write tests** in `tests/test_<module>.py`
3. **Run tests** and fix failures:
   ```bash
   pytest tests/test_<module>.py -v
   ```
4. **Run full suite** to ensure no regressions:
   ```bash
   pytest tests/
   ```
5. **Check coverage** (optional but recommended):
   ```bash
   pytest tests/ --cov=. --cov-report=term-missing
   ```
6. **Commit implementation + tests together**

### Test Structure Template

```python
"""Tests for <module_name> module."""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from module_name import function_to_test

class TestFeatureName:
    """Test suite for feature_name functionality."""

    def test_typical_case(self):
        """Test normal operation with valid input."""
        result = function_to_test(valid_input)
        assert result == expected_output

    def test_edge_case_empty_input(self):
        """Test handling of empty input."""
        result = function_to_test("")
        assert result == expected_empty_result

    def test_edge_case_boundary(self):
        """Test boundary conditions."""
        result = function_to_test(boundary_value)
        assert result is not None

    def test_error_handling_invalid_input(self):
        """Test that invalid input raises appropriate error."""
        with pytest.raises(ValueError, match="Invalid input"):
            function_to_test(invalid_input)

    def test_error_handling_none_input(self):
        """Test handling of None input."""
        with pytest.raises(TypeError):
            function_to_test(None)
```

### Why Testing is Mandatory

- **Prevents regressions**: Bug fixes need regression tests to ensure the bug doesn't return
- **Documents behavior**: Tests serve as executable documentation
- **Enables refactoring**: Confident code changes without breaking functionality
- **Maintains quality**: Enforces code quality at scale
- **Automated validation**: CI/CD can verify changes automatically

**Quality Gates**:
- Contributions without tests will be rejected
- Failing tests block merging
- Pre-commit hooks enforce test execution
- **Agent enforcement**: `code_agent` MUST write tests before committing
- **Validation enforcement**: `task-completion-validator` REJECTS implementations without tests or with failing tests

## Pull Request Process

### Before Creating a PR

1. **Sync with upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run full test suite**:
   ```bash
   pytest tests/ -v
   ```

3. **Run pre-commit on all files**:
   ```bash
   pre-commit run --all-files
   ```

4. **Verify your changes work**:
   - Test manually with the chat interface (http://localhost:3000)
   - Check monitoring dashboard for errors (http://localhost:3000/dashboard)
   - Review logs for unexpected behavior

### PR Description Template

Use this template for your pull request description:

```markdown
## Summary

Brief description of what this PR does (1-2 sentences).

## Motivation

Why is this change needed? What problem does it solve?

## Changes

- List specific changes made
- Include file modifications
- Mention new dependencies (if any)

## Testing

- [ ] Added unit tests for new functionality
- [ ] Added integration tests for workflows
- [ ] All tests pass locally
- [ ] Manually tested with chat interface
- [ ] Checked monitoring dashboard for errors

## Screenshots (if UI changes)

Include screenshots showing before/after (if applicable).

## Breaking Changes

List any breaking changes and migration steps (if applicable).

## Checklist

- [ ] Code follows project style guidelines (Black, isort, Ruff)
- [ ] All tests pass
- [ ] Pre-commit hooks pass
- [ ] Documentation updated (if needed)
- [ ] CLAUDE.md updated (if architectural changes)
- [ ] No secrets or sensitive data in code
- [ ] Commit messages follow format
```

### PR Approval Criteria

Your PR will be reviewed for:

1. **Functionality**: Does it work as intended?
2. **Tests**: Are there sufficient tests? Do they pass?
3. **Code Quality**: Follows style guide, clean code principles
4. **Security**: No vulnerabilities, input sanitization where needed
5. **Documentation**: Clear comments, updated docs if needed
6. **Performance**: No obvious performance issues
7. **Compatibility**: Works with existing features

### Merge Strategy

- **Squash and merge**: For feature branches (default)
- **Rebase and merge**: For clean, well-structured commits
- **Merge commit**: For important feature branches with meaningful history

Maintainers will choose the appropriate strategy based on your commit history.

## Architecture Guidelines

### File Organization

```
amiga/
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
│   ├── server.py        # Web server (Flask + WebSocket)
│   ├── metrics.py       # Real-time metrics from hooks
│   ├── hooks_reader.py  # Hook data parsing
│   └── dashboard/       # React chat UI (TypeScript)
│       ├── src/         # Source files (*.tsx, *.css)
│       ├── build/       # Build output (npm run build)
│       └── deploy.sh    # Deploy script (build → static/chat)
├── tasks/               # Task management
│   ├── manager.py       # Background task tracking
│   ├── pool.py          # Bounded worker pool
│   ├── database.py      # Database operations
│   └── tracker.py       # Tool usage tracking
├── utils/               # Shared utilities
│   ├── git.py           # Git operations
│   ├── helpers.py       # General helpers
│   └── worktree.py      # Git worktree management
├── tests/               # Test suite (pytest)
│   ├── __init__.py
│   ├── conftest.py      # pytest configuration
│   └── test_*.py        # All test files
├── scripts/             # Utility scripts
│   └── analyze_*.py     # Analysis scripts
├── docs/                # Documentation
│   └── *.md             # Implementation notes, feature docs
├── .claude/             # Claude Code configuration
│   ├── agents/          # Agent definitions (16 specialized agents)
│   ├── hooks/           # Tool usage tracking
│   └── settings.local.json  # Permissions, output style
├── data/                # Runtime state (sessions, tasks, costs)
├── logs/                # Application logs
├── static/              # Static assets served by Flask
│   └── chat/            # Deployed dashboard build
└── templates/           # Jinja templates for web UI
```

**Rules**:
- Test files ONLY in `tests/` (project root)
- Follow naming: `test_*.py` for pytest discovery
- One test file per module: `test_formatter.py` tests `messaging/formatter.py`
- Documentation in `docs/`, NOT project root (except README.md and CLAUDE.md)
- Analysis files in `docs/analysis/` (not project root)

### Chat Frontend Development Workflow

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

**Why this matters**:
- Flask serves static files from `static/chat/`
- React builds have content hashes (e.g., `main.987fad4a.css`)
- Old builds remain cached without deployment
- Browser caches old assets until hard refresh

### Agent Architecture

AMIGA uses 16 specialized agents coordinated by the orchestrator:

**Core Agents**:
- **orchestrator**: Coordinates tasks, delegates to specialized agents
- **code_agent**: Backend implementation (Python, Sonnet 4.5)
- **frontend_agent**: UI/UX development (HTML/CSS/JS, Sonnet 4.5) with Playwright MCP
- **research_agent**: Analysis, proposals, web research (Opus 4.5)

**Quality Assurance Agents**:
- **Jenny**: Verifies implementation matches specifications
- **claude-md-compliance-checker**: Ensures CLAUDE.md adherence
- **code-quality-pragmatist**: Detects over-engineering
- **karen**: Reality check on project completion
- **task-completion-validator**: Validates tasks actually work
- **ui-comprehensive-tester**: Comprehensive UI testing with Playwright MCP
- **ultrathink-debugger**: Deep debugging (Opus 4.5 - expensive, use sparingly)

**Workflow Agents**:
- **git-worktree**: Creates/manages isolated worktrees for concurrent work
- **git-merge**: Merges task branches to main

**Self-Improvement Agent**:
- **self-improvement-agent**: Analyzes error patterns from database, updates agent prompts based on real failures, creates tasks for code fixes

**Agent Workflow Example** (Code Implementation):
1. orchestrator receives task
2. research_agent (if research needed)
3. code_agent (implementation)
4. task-completion-validator (verify it works)
5. code-quality-pragmatist (check complexity)
6. claude-md-compliance-checker (verify CLAUDE.md compliance)

### Database & Log Access

**CRITICAL**: Before starting ANY debugging task, check the database and logs for context.

#### Database (SQLite)

**Location**: `data/agentlab.db`

**Key Tables**:
- `tasks` - Background task tracking and status
- `tool_usage` - Tool usage statistics with error tracking
- `sessions` - User conversation history (if exists)

**Common Queries**:
```bash
# Find errors in task tracking
sqlite3 data/agentlab.db "SELECT task_id, error, updated_at FROM tasks WHERE error IS NOT NULL ORDER BY updated_at DESC LIMIT 10;"

# Get tool usage summary
sqlite3 data/agentlab.db "SELECT tool_name, COUNT(*) as count, SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures FROM tool_usage GROUP BY tool_name ORDER BY count DESC;"

# Find hung tasks (running but stale)
sqlite3 data/agentlab.db "SELECT task_id, status, updated_at FROM tasks WHERE status = 'running' AND julianday('now') - julianday(updated_at) > 0.042;"

# Get session UUID for task (needed for log lookup)
sqlite3 data/agentlab.db "SELECT session_uuid FROM tasks WHERE task_id = 'abc123';"
```

#### Log Files

**Location**: `logs/`

**Files**:
- `logs/bot.log` - Main application log (auto-rotated)
- `logs/monitoring.log` - Web dashboard log
- `logs/sessions/<session_uuid>/` - Per-session Claude Code logs
  - `pre_tool_use.jsonl` - Tool invocations
  - `post_tool_use.jsonl` - Tool results
  - `summary.json` - Session summary

**Common Commands**:
```bash
# Tail main log
tail -f logs/bot.log

# Search for errors
grep ERROR logs/bot.log | tail -50

# View session logs (requires session_uuid from database)
session_uuid=$(sqlite3 data/agentlab.db "SELECT session_uuid FROM tasks WHERE task_id = 'abc123';")
tail -100 "logs/sessions/$session_uuid/pre_tool_use.jsonl" | jq
```

**Debugging Workflow**:
1. Check `data/agentlab.db` (tasks table) for related tasks
2. Check `logs/bot.log` for recent errors
3. Get session UUID from database
4. Check session logs in `logs/sessions/<session_uuid>/`
5. Check `tool_usage` table for tool performance issues

### Playwright MCP Integration

**Purpose**: Cross-browser automation and testing for frontend development.

**Installation**:
```bash
claude mcp add playwright npx -s user @playwright/mcp@latest -- --isolated
```

**Available to**: `frontend_agent`, `ui-comprehensive-tester`

**Common Use Cases**:
- Visual validation (screenshots for comparison)
- Form testing (fill, submit, verify)
- Responsive testing (desktop/tablet/mobile)
- Accessibility validation (snapshot accessibility tree)

**Screenshot Best Practices**:
- **Always use JPEG format with quality parameter** (not PNG)
- Recommended quality: 75-85 (balance of visual fidelity and file size)
- PNG is 5-10x larger than JPEG for UI screenshots

### Manager Pattern Usage

When refactoring `core/main.py` or adding complex features, use the Manager pattern:

```python
class FeatureManager:
    """Manages feature lifecycle and dependencies."""

    def __init__(self, config: Config):
        self.config = config
        self._state = {}

    async def start(self) -> None:
        """Initialize the feature."""
        ...

    async def stop(self) -> None:
        """Clean up resources."""
        ...

    async def handle_operation(self, data: dict) -> Result:
        """Handle specific operation."""
        ...
```

**Benefits**:
- Encapsulates related functionality
- Manages lifecycle (start/stop)
- Easy to test in isolation
- Clear dependency injection

### Security Requirements

**CRITICAL: All user input MUST be sanitized before use.**

#### Input Sanitization

```python
from utils.security import (
    sanitize_xml_content,      # HTML escape + pattern removal
    detect_prompt_injection,   # Detect prompt injection attacks
    validate_file_path         # Prevent directory traversal
)

# Always sanitize user input before Claude API calls
safe_query = sanitize_xml_content(user_query)

# Detect malicious input
is_malicious, reason = detect_prompt_injection(user_query)
if is_malicious:
    return f"Input rejected: {reason}"

# Validate file paths
try:
    validate_file_path(user_path, base_path=WORKSPACE_PATH)
except ValueError as e:
    return f"Invalid path: {e}"
```

#### Why Sanitization Matters

User input is embedded in XML prompts sent to Claude. Unsanitized input could:
- Break prompt structure (XML injection)
- Inject malicious instructions
- Cause prompt confusion
- Leak sensitive data

**Security Checklist**:
- [ ] All user input sanitized before Claude API calls
- [ ] File paths validated against allowed directories
- [ ] No hardcoded secrets (use environment variables)
- [ ] API keys never logged
- [ ] Prompt injection detection active

### Cost Optimization

Keep costs reasonable by:

1. **Token minimization**:
   - Conversation history: Last 20 messages, 5000 chars per message
   - Active tasks: Max 3 tasks, omit descriptions
   - Logs: Last 50 lines only (not 200)
   - Don't include `available_repositories` list (~100 tokens saved)

2. **Model selection**:
   - Use Haiku 4.5 for Q&A routing (10x cheaper)
   - Use Sonnet 4.5 for coding tasks (more capable)
   - Use Opus 4.5 for research_agent and ultrathink-debugger (most capable, most expensive)
   - Cost-aware agent usage: Opus agents for complex analysis only

3. **Caching**:
   - Cache repeated queries
   - Reuse session context
   - Minimize redundant API calls

### Async Best Practices

```python
# Good - Parallel execution
async def handle_request():
    results = await asyncio.gather(
        fetch_data(),
        process_cache(),
        update_metrics()
    )

# Bad - Sequential when parallel is possible
async def handle_request():
    result1 = await fetch_data()
    result2 = await process_cache()
    result3 = await update_metrics()
```

## Commit Message Format

### Style Guide

Follow the Conventional Commits style with Claude Code footer:

```
<type>: <brief description>

<optional detailed description>

<optional footer>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Commit Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **refactor**: Code refactoring (no functionality change)
- **test**: Adding or updating tests
- **chore**: Maintenance tasks (dependencies, config)
- **perf**: Performance improvements
- **style**: Code style changes (formatting)

### Examples

#### Feature Addition
```
feat: Add real-time typing indicators to chat interface

Implements WebSocket-based typing indicators that show when
the AI is processing a response. Updates chat UI to display
animated ellipsis during response generation.

Fixes #42

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Bug Fix
```
fix: Resolve message queue deadlock in concurrent requests

MessageQueue could deadlock when processing multiple requests
from same user simultaneously. Added asyncio.Lock to serialize
processing per user.

Fixes message_queue.py:87

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Refactoring
```
refactor: Split core/main.py into feature managers

Extracted session management, task coordination, and message
routing into dedicated manager classes. Improves testability
and maintainability.

- SessionManager: User session lifecycle
- TaskCoordinator: Background task management
- MessageRouter: Route messages to appropriate handlers

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

#### Test Addition
```
test: Add comprehensive tests for ResponseFormatter

Tests cover:
- Markdown formatting edge cases
- Code block handling
- Message chunking at 4096 char limit
- Special character escaping

Achieves 95% coverage for formatter.py

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Commit Best Practices

- **Start with verb**: "Add", "Fix", "Update", "Refactor"
- **Be specific**: "Fix null pointer in auth.py:42" not "Fix bug"
- **Reference files**: Use `file_path:line_number` format when applicable
- **One logical change**: Don't mix unrelated changes
- **Include tests**: Commit implementation + tests together

## Code Review Checklist

Use this checklist when reviewing PRs:

### Functionality
- [ ] Feature works as described
- [ ] No obvious bugs or edge cases missed
- [ ] Error handling is appropriate
- [ ] Logging is informative and at correct level

### Testing
- [ ] Tests exist and are meaningful (not just for coverage)
- [ ] All tests pass locally
- [ ] Coverage is adequate (70%+ overall, 80%+ critical paths)
- [ ] Edge cases are tested
- [ ] Error conditions are tested

### Code Quality
- [ ] Code follows style guide (Black, isort, type hints)
- [ ] Functions have clear, single responsibilities
- [ ] No code duplication (DRY principle)
- [ ] Variable/function names are descriptive
- [ ] Comments explain "why", not "what"
- [ ] No commented-out code (use git history)

### Security
- [ ] User input is sanitized
- [ ] No hardcoded secrets or API keys
- [ ] File paths are validated
- [ ] No SQL injection risks
- [ ] No command injection risks

### Performance
- [ ] No obvious performance bottlenecks
- [ ] Async/await used correctly
- [ ] Database queries are efficient
- [ ] No unnecessary API calls

### Documentation
- [ ] Public APIs have docstrings
- [ ] Complex logic has explanatory comments
- [ ] README updated if needed
- [ ] CLAUDE.md updated if architectural changes

### Architecture
- [ ] Changes align with project structure
- [ ] Dependencies are justified
- [ ] No circular dependencies
- [ ] Follows established patterns

### Git Hygiene
- [ ] Commit messages follow format
- [ ] No merge conflicts
- [ ] Branch is up to date with main
- [ ] Commits are logical and atomic

## Questions?

If you have questions or need help:

1. **Check documentation**: README.md, CLAUDE.md, code comments
2. **Review existing code**: Look for similar patterns
3. **Open an issue**: For bugs or feature discussions
4. **Ask in PR**: Tag maintainers with specific questions

Thank you for contributing!
