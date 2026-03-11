# AMIGA: Autonomous Modular Interactive Graphical Agent

<p align="center">
  <img src="static/img/logo.png" alt="AMIGA Logo" width="500"/>
</p>

<p align="center">
  <strong>Repository automation through natural language</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/coverage-80%25%2B-brightgreen?style=flat-square" alt="Coverage Badge"/>
  <img src="https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square" alt="Tests Badge"/>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square" alt="Python Badge"/>
</p>

## Overview

An experiment in making software development less about writing code and more about expressing intent. Specialized agents handle implementation while the system focuses on understanding what you want to achieve.

The interface is a web chat. The implementation is automated. The monitoring is comprehensive. The system learns from its mistakes.

## Core Components

**Agent Orchestration**: 16 specialized agents coordinated through a task system. Each handles specific aspects - implementation, testing, validation, debugging. They operate in isolated git worktrees created natively by the SDK via the `--worktree` flag.

**Web Interface**: Real-time chat at `localhost:3000` for interaction. Monitoring dashboard at `localhost:3000/dashboard` for observability. No code editor - just conversations and results.

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

Access: `localhost:3000`

## Architecture

**Models**: Haiku for routing (effort=low, max $0.50), Sonnet 4.6 for implementation (effort=high, max $5.00), Opus 4.6 for deep debugging (effort=max, max $10.00). Cost-aware selection with per-task budget caps.

**Agents**: 16 agents defined in `.claude/agents/*.md`, loaded via `claude/agent_loader.py` which parses YAML frontmatter for model aliases, memory scope (`user`/`project`), `permissionMode`, effort level, and isolation settings.

| Agent | Role | Model |
|---|---|---|
| orchestrator | Task coordination and delegation | inherit |
| code_agent | Python backend implementation | sonnet |
| frontend_agent | UI/UX development with Playwright MCP | sonnet |
| research_agent | Analysis, proposals, web research | opus |
| debug-agent | Targeted bug investigation | sonnet |
| task-decomposer | Break complex requests into subtasks | sonnet |
| ultrathink-debugger | Deep root cause analysis (expensive, use sparingly) | opus |
| self-improvement-agent | Analyze errors, update agent behavior autonomously | opus |
| Jenny | Verify implementation matches specifications | sonnet |
| karen | Reality checks on project completion | sonnet |
| task-completion-validator | Validate tasks actually work end-to-end | sonnet |
| claude-md-compliance-checker | Ensure CLAUDE.md conventions are followed | sonnet |
| code-quality-pragmatist | Detect over-engineering and complexity | sonnet |
| ui-comprehensive-tester | Comprehensive UI testing with Playwright MCP | sonnet |
| git-worktree | Create and manage isolated task worktrees | sonnet |
| git-merge | Merge task branches back to main | sonnet |

QA/read-only agents use `permissionMode: plan`. Learning agents (self-improvement, compliance, quality) use `memory: project` for persistent context.

**Skills**: Three shared skills in `.claude/skills/` — `coding-conventions`, `testing-requirements`, `git-workflow` — injected automatically into relevant agents to enforce consistent behavior across the system.

**Hooks**: Python SDK callbacks (`claude/sdk_hooks.py`) replace the shell script hooks that previously lived in `.claude/hooks/`. `PreToolUse` blocks dangerous git operations (`--no-verify`, `--force`, `--hard`). `PostToolUse` records tool completions to SQLite. `Stop` marks session end. `SubagentStart`/`SubagentStop` track nested agent execution. All callbacks are wrapped in try/except — hook exceptions cannot crash the SDK transport layer. Shell hooks in `.claude/hooks/` remain for local developer-experience features (tmux reminders, Prettier auto-format) but no longer handle data collection.

**Worktrees**: Each task runs in an isolated git worktree under `/tmp/agentlab-worktrees/`. The SDK creates the branch `task/{task_id}` automatically via the `--worktree` flag in `ClaudeSDKSession.execute_task()`. The `git-worktree` agent manages worktree lifecycle and the `git-merge` agent handles merging back to main. Worktrees are preserved in `/tmp/` for post-task inspection and cleared on system restart.

**Persistence**: SQLite tracks tasks, tool usage, errors. Logs in `logs/`, session data in `data/`. Query patterns in `CLAUDE.md`.

**Auth**: Session-backed JWT tokens with refresh support. Login returns both `access_token` and `refresh_token`. Sessions stored in SQLite with inactivity tracking.

**Testing**: 12 test modules. Pre-commit hooks enforce quality. Coverage targets: 80%+ overall, 100% for utilities.

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

**Production Ready** | 12 test modules | 16 agents | 3 shared skills | SDK hooks | Worktree isolation | Claude Agent SDK

*Intent over implementation*
