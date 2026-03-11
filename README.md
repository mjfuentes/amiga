# AMIGA: Autonomous Modular Interactive Graphical Agent

<p align="center">
  <img src="static/img/logo.png" alt="AMIGA Logo" width="500"/>
</p>

<p align="center">
  <strong>Repository automation through natural language</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/coverage-70%25-yellow?style=flat-square" alt="Coverage Badge"/>
  <img src="https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square" alt="Tests Badge"/>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square" alt="Python Badge"/>
</p>

## Overview

An experiment in making software development less about writing code and more about expressing intent. Specialized agents handle implementation while the system focuses on understanding what you want to achieve.

The interface is a web chat. The implementation is automated. The monitoring is comprehensive. The system learns from its mistakes.

## Core Components

**Agent Orchestration**: 19 specialized agents coordinated through a task system. Each handles specific aspects - implementation, testing, validation, debugging. They operate in isolated git worktrees created automatically by the SDK.

**Web Interface**: Real-time chat at `localhost:3000/chat` for interaction. Monitoring dashboard at `localhost:3000` for observability. No code editor - just conversations and results.

**Self-Improvement**: SQLite database tracks tool usage, failures, and patterns. The system analyzes its own errors and updates agent behavior autonomously.

**Phase-Aware Execution**: Tasks progress through Explore → Plan → Code → Commit phases. Each phase visible in real-time through the monitoring interface.

**SDK-Native Integration**: Uses the Claude Agent SDK (`claude_agent_sdk`) directly instead of spawning subprocess `claude` processes. Hooks, worktree isolation, effort controls, and agent definitions are all wired through the SDK.

## Installation

```bash
git clone <repo_url> && cd amiga
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pre-commit install

cp .env.example .env
# Add ANTHROPIC_API_KEY and WORKSPACE_PATH

./deploy.sh chat
```

Access: `localhost:3000/chat`

## Architecture

**Models**: Haiku for routing (effort=low, max $0.50), Sonnet for implementation (effort=high, max $5.00), Opus for deep debugging (effort=max, max $10.00). Cost-aware selection with per-task budget caps.

**Agents**: orchestrator (delegation), code_agent (Python), frontend_agent (UI/UX), research_agent (analysis), plus QA validators, debuggers, and git workflow managers. Agent definitions live in `.claude/agents/*.md` and are loaded automatically via `claude/agent_loader.py`.

**Hooks**: Python SDK callbacks (`claude/sdk_hooks.py`) replace shell script hooks. `PreToolUse` blocks dangerous git operations (`--no-verify`, `--force`, `--hard`). `PostToolUse` records tool completions to SQLite. `Stop` marks session end.

**Persistence**: SQLite tracks tasks, tool usage, errors. Logs in `logs/`, session data in `data/`. Query patterns in `CLAUDE.md`.

**Auth**: Session-backed JWT tokens with refresh support. Login returns both `access_token` and `refresh_token`. Sessions stored in SQLite with inactivity tracking.

**Testing**: 57 modules. Pre-commit hooks enforce quality. Coverage targets: 70%+ overall, 80%+ critical paths.

## Development

Frontend changes require deployment:
```bash
./deploy.sh chat  # Builds, deploys, restarts
```

Tests are mandatory. No exceptions.

Database queries:
```bash
sqlite3 data/agentlab.db "SELECT task_id, status FROM tasks WHERE status='running';"
```

See `CLAUDE.md` for conventions, architecture details, and comprehensive documentation.

## Philosophy

Most tools help you write code faster. This explores whether we can help users achieve goals without thinking about code at all.

Comprehensive monitoring. Error resilience. Self-improvement. User intent extraction. These matter more than syntax highlighting or autocomplete.

Not a product. An exploration.

## Technical Stack

Python 3.12+, Claude Agent SDK (`claude_agent_sdk`), Claude API (Haiku/Sonnet/Opus), Flask, React + TypeScript, SQLite, Playwright MCP

## Cost

~$75/month typical usage. Set `DAILY_COST_LIMIT` and `MONTHLY_COST_LIMIT` in `.env`.

## Contributing

Issues and suggestions welcome. Development workflow in `CLAUDE.md`.

## Resources

- [Claude Code Docs](https://docs.claude.com/claude-code)
- [Anthropic API](https://docs.anthropic.com/)

---

**Production Ready** | 57 test modules | 19 agents | Claude Agent SDK

*Intent over implementation*
