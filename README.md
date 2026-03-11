<p align="center">
  <img src="static/img/logo.png" alt="AMIGA" width="500"/>
</p>

<h3 align="center">Tell it what you want. It writes the code.</h3>

<p align="center">
  <img src="https://img.shields.io/badge/coverage-80%25%2B-brightgreen?style=flat-square" alt="Coverage"/>
  <img src="https://img.shields.io/badge/tests-passing-brightgreen?style=flat-square" alt="Tests"/>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square" alt="Python"/>
</p>

---

AMIGA is a multi-agent coding system that turns natural language into working software. You chat. It codes, tests, commits, and deploys. 16 agents, each with a job. No hand-holding.

## What it does

- **Routes tasks to the right model.** Haiku for quick answers ($0.50 cap). Sonnet for implementation ($5.00 cap). Opus for deep debugging ($10.00 cap). You don't pick. It picks.
- **Runs agents in isolated git worktrees.** Each task gets its own branch, its own directory, its own mess. Merges back to main when done. No stepping on each other.
- **Tracks everything.** Every tool call, every failure, every token spent. SQLite. Queryable. The self-improvement agent reads its own error history and rewrites agent prompts to stop making the same mistakes.
- **Ships through a chat UI.** `localhost:3000`. Type what you need. Watch it work. Real-time tool usage, phase progression, cost tracking.

## Quick Start

```bash
git clone git@github.com:mjfuentes/amiga.git && cd amiga
./amiga setup
```

That's it. The setup wizard handles venv, dependencies, API keys, frontend build, and starts the server.

```bash
./amiga start    # Start the server
./amiga stop     # Stop it
./amiga status   # What's running, active tasks, cost today
./amiga logs     # Tail the logs
./amiga db "SELECT task_id, status FROM tasks ORDER BY updated_at DESC LIMIT 5;"
```

Open `localhost:3000`. Start talking.

## How it works

You send a message. Haiku decides if it's a question or a task. Questions get answered immediately. Tasks get routed to the orchestrator, which picks agents, spins up worktrees, and manages the whole lifecycle.

### Agents

Defined in `.claude/agents/*.md` with YAML frontmatter. Parsed at runtime by `claude/agent_loader.py`.

**Core** -- do the actual work:

| Agent | What it does | Model |
|---|---|---|
| orchestrator | Coordinates everything | inherit |
| code_agent | Backend implementation | Sonnet |
| frontend_agent | UI/UX + Playwright testing | Sonnet |
| research_agent | Deep analysis and proposals | Opus |
| debug-agent | Bug investigation | Sonnet |
| ultrathink-debugger | Hard problems, expensive, use sparingly | Opus |
| task-decomposer | Breaks big tasks into small ones | Sonnet |

**QA** -- keep the work honest:

| Agent | What it does | Model |
|---|---|---|
| Jenny | Checks implementation vs spec | Sonnet |
| karen | Reality checks | Sonnet |
| task-completion-validator | Does it actually work? | Sonnet |
| code-quality-pragmatist | Flags over-engineering | Sonnet |
| claude-md-compliance-checker | Enforces project conventions | Sonnet |
| ui-comprehensive-tester | Playwright-based UI testing | Sonnet |

**Infrastructure** -- handle git and self-correction:

| Agent | What it does | Model |
|---|---|---|
| git-worktree | Creates isolated task worktrees | Sonnet |
| git-merge | Merges branches back to main | Sonnet |
| self-improvement-agent | Reads error DB, rewrites agent prompts | Opus |

QA agents run in `permissionMode: plan` (read-only). Learning agents use `memory: project` for persistent context. Three shared skills (`coding-conventions`, `testing-requirements`, `git-workflow`) get injected automatically.

### SDK Integration

Uses `claude_agent_sdk` directly. No subprocess spawning.

- **Hooks** (`claude/sdk_hooks.py`): Python callbacks. `PreToolUse` blocks dangerous git ops (`--force`, `--hard`, `--no-verify`). `PostToolUse` writes tool usage to SQLite. All wrapped in try/except so a bad hook can't kill the stream.
- **Worktrees**: Each task gets `/tmp/agentlab-worktrees/{task_id}/`. SDK creates the branch via `--worktree`. Preserved after completion for debugging. Cleared on reboot.
- **Auth**: Session-backed JWT with refresh tokens. Sessions in SQLite.

### The Flow

```
Message in --> Haiku routes --> Orchestrator picks agents -->
Worktree created --> Explore --> Plan --> Code --> Commit -->
Merge to main --> Result back in chat
```

## Stack

Python 3.12+ / Claude Agent SDK / Flask / React + TypeScript / SQLite / Playwright MCP

## Cost

~$75/month typical. Set `DAILY_COST_LIMIT` and `MONTHLY_COST_LIMIT` in `.env` to cap it.

## Development

```bash
./deploy.sh chat          # Build frontend, deploy, restart
pytest tests/ -v          # Tests are mandatory. No exceptions.
```

Check the database:
```bash
sqlite3 data/agentlab.db "SELECT task_id, status, error FROM tasks ORDER BY updated_at DESC LIMIT 10;"
```

Full conventions and architecture details in [`CLAUDE.md`](CLAUDE.md). That's the real documentation.

---

<p align="center">
  <strong>16 agents</strong> / <strong>12 test modules</strong> / <strong>SDK hooks</strong> / <strong>worktree isolation</strong> / <strong>self-improving</strong>
</p>
<p align="center">
  <a href="https://docs.claude.com/claude-code">Claude Code Docs</a> · <a href="https://docs.anthropic.com/">Anthropic API</a>
</p>
