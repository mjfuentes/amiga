# Development Guide

## Monitoring Dashboard

Run the monitoring server to see real-time task status:

```bash
python telegram_bot/monitoring_server.py
# Open http://localhost:3000
```

Shows:
- Running tasks (click to see tool usage)
- Recent errors
- API costs (24h)
- Tool usage stats

Built with Flask + SSE for live updates.

## Hook System

Hooks track every Claude Code tool call and write to both JSONL logs and JSON databases.

### Hook Files

Located in `~/.claude/hooks/`:

- `pre-tool-use` - Logs tool name + params before execution
- `post-tool-use` - Logs results + errors after execution
- `session-end` - Aggregates session summary

All are bash scripts with inline Python for JSON processing.

### Hook Data Flow

```
Tool executed
    ↓
pre-tool-use hook
    ↓
logs/sessions/{session_id}/pre_tool_use.jsonl
telegram_bot/data/tool_usage.json
    ↓
Tool completes
    ↓
post-tool-use hook
    ↓
logs/sessions/{session_id}/post_tool_use.jsonl
telegram_bot/data/tool_usage.json
    ↓
Session ends
    ↓
session-end hook
    ↓
logs/sessions/{session_id}/summary.json
```

### Reading Hook Data

**metrics_aggregator.py**: Reads hook data and aggregates metrics
**hooks_reader.py**: Parses JSONL logs and JSON databases
**monitoring_server.py**: Serves data via SSE to dashboard

## Message Queue System

Sequential per-user message processing with priority support.

**Key files:**
- `message_queue.py` - Queue implementation
- `main.py` - Integration

**Features:**
- Priority commands (`/restart`, `/start`) bypass queue
- Normal messages processed sequentially per user
- Prevents race conditions

## Pre-commit Hooks

Auto-runs on commit:

```bash
pre-commit install
pre-commit run --all-files
```

Checks:
- black (formatting)
- isort (imports)
- ruff (linting)
- bandit (security)
- pytest (tests)
- secret detection

Config: `.pre-commit-config.yaml`

## Testing

```bash
cd telegram_bot
pytest -v
pytest --cov=. --cov-report=html
```

## Logs

**Application logs**: `logs/bot.log`
**Session logs**: `logs/sessions/{session_id}/`
**Monitoring**: `telegram_bot/logs/monitoring_nohup.log`

```bash
# Watch bot logs
tail -f logs/bot.log

# Check for errors
grep ERROR logs/bot.log | tail -20
```

## Running in Production

**macOS (launchd)**:
```bash
cp telegram_bot/com.agentlab.telegrambot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.agentlab.telegrambot.plist
launchctl list | grep agentlab
```

**Background (screen)**:
```bash
screen -S bot
python telegram_bot/main.py
# Detach: Ctrl+A, D
# Reattach: screen -r bot
```

**Background (nohup)**:
```bash
nohup python telegram_bot/main.py > logs/bot_output.log 2>&1 &
ps aux | grep main.py
```
