# Scripts

## Purpose
Utility scripts for analysis, migrations, setup automation, and system maintenance.

## Components

### Analysis Scripts

#### analyze_tool_usage.py
Analyzes tool usage patterns from AgentLab database.
- Tool usage by agent/workflow
- Success/failure rates
- Duration statistics
- Error categorization
- Top tools by frequency

Usage:
```bash
python scripts/analyze_tool_usage.py --db-path data/agentlab.db --days 7
```

#### analyze_errors.py
Error analysis and categorization from database.
- Error frequency by category
- Error trends over time
- Most common error patterns
- Affected tasks and agents

Usage:
```bash
python scripts/analyze_errors.py --db-path data/agentlab.db
```

#### analyze_actual_errors.py
Analyzes actual errors from log files (vs database records).
- Cross-reference logs with database
- Identify unreported errors
- Log parsing and pattern matching

Usage:
```bash
python scripts/analyze_actual_errors.py --log-file logs/bot.log
```

### Migration Scripts

#### migrate_to_sqlite.py
Migrates data from JSON files to SQLite database.
- Converts sessions.json → database
- Converts cost_tracking.json → database
- Preserves data integrity
- Handles schema migrations

Usage:
```bash
python scripts/migrate_to_sqlite.py --data-dir data/
```

#### migrate_tasks_to_messages.py
Migrates task data between schema versions.
- Updates database schema
- Data transformation
- Backward compatibility

Usage:
```bash
python scripts/migrate_tasks_to_messages.py --db-path data/agentlab.db
```

#### merge_databases.py
Merges multiple database instances.
- Combines data/agentlab.db with workspace databases
- Resolves conflicts
- Preserves unique constraints

Usage:
```bash
python scripts/merge_databases.py --source workspace/data/agentlab.db --target data/agentlab.db
```

### Setup Scripts

#### setup_launchd.sh
macOS launchd service configuration.
- Installs launch agents for bot and monitoring
- Auto-start on login
- Log file configuration

Usage:
```bash
./scripts/setup_launchd.sh
```

#### setup_iterm_dev.sh
iTerm2 development environment setup.
- Opens split panes for bot, monitoring, logs
- Runs from project root

Usage:
```bash
./scripts/setup_iterm_dev.sh
```

#### setup_iterm_layout.applescript
AppleScript for iTerm2 layout automation.
- Creates 4-pane layout (bot, monitoring, logs, shell)
- Configurable working directory

Usage:
```bash
osascript scripts/setup_iterm_layout.applescript
```

#### start_services.sh
Starts all AgentLab services.
- Bot process
- Monitoring server
- Background workers

Usage:
```bash
./scripts/start_services.sh
```

### Validation Scripts

#### check_hook_detection.py
Validates hook detection and parsing.
- Tests hook file parsing
- Verifies session UUID correlation
- Checks tool usage tracking

Usage:
```bash
python scripts/check_hook_detection.py --sessions-dir logs/sessions/
```

#### check_improvement.py
Checks for improvements in metrics over time.
- Compares current vs historical metrics
- Success rate trends
- Performance improvements

Usage:
```bash
python scripts/check_improvement.py --days 30
```

#### check_usage.py
Checks API usage and cost tracking.
- Anthropic API usage
- Cost breakdown by model
- Daily/monthly limits

Usage:
```bash
python scripts/check_usage.py
```

### Hook Recording Scripts

#### record_tool_start.py
Records tool invocation start (pre-tool-use hook).
- Called by `.claude/hooks/pre-tool-use`
- Writes to database.tool_usage
- Tracks tool parameters

Usage (called by hook):
```bash
python scripts/record_tool_start.py --tool-name Read --task-id abc123 --params '{"file_path": "/path/to/file"}'
```

#### record_tool_usage.py
Records tool invocation completion (post-tool-use hook).
- Called by `.claude/hooks/post-tool-use`
- Updates database.tool_usage with results
- Tracks duration, success, errors

Usage (called by hook):
```bash
python scripts/record_tool_usage.py --tool-name Read --task-id abc123 --success true --duration 150
```

#### query_top_tools.py
Queries top tools by usage from database.
- Tool usage leaderboard
- Success rates
- Average durations

Usage:
```bash
python scripts/query_top_tools.py --limit 10
```

### Logging Scripts

#### log_claude_escalation.py
Logs escalation events (orchestrator → agent delegation).
- Tracks when tasks escalated to agents
- Records escalation reasons
- Duration from request to completion

Usage:
```bash
python scripts/log_claude_escalation.py --task-id abc123 --reason "complex_coding_task"
```

### Test Scripts

#### test-orchestrator.sh
Tests orchestrator agent invocation.
- Sends test queries
- Validates responses
- Checks background task format

Usage:
```bash
./scripts/test-orchestrator.sh "Fix bug in main.py"
```

## Usage Patterns

### Analysis Workflow
```bash
# 1. Check recent errors
python scripts/analyze_errors.py --days 7

# 2. Analyze tool usage
python scripts/analyze_tool_usage.py --days 7

# 3. Compare with actual logs
python scripts/analyze_actual_errors.py

# 4. Check for improvements
python scripts/check_improvement.py --days 30
```

### Migration Workflow
```bash
# 1. Backup current database
cp data/agentlab.db data/agentlab.db.backup

# 2. Run migration
python scripts/migrate_to_sqlite.py

# 3. Verify data integrity
sqlite3 data/agentlab.db "SELECT COUNT(*) FROM tasks;"

# 4. Merge workspace data if needed
python scripts/merge_databases.py --source workspace/data/agentlab.db
```

### Development Setup
```bash
# One-time setup
./scripts/setup_launchd.sh

# Daily development
./scripts/setup_iterm_dev.sh  # Opens iTerm with 4 panes

# Manual start (alternative)
./scripts/start_services.sh
```

## Dependencies

### Internal
- `core/config.py` - Configuration paths
- `tasks/database.py` - Database access
- `tasks/analytics.py` - Analytics queries
- `monitoring/hooks_reader.py` - Hook parsing

### External
- `sqlite3` - Database operations
- `argparse` - CLI argument parsing
- `json` - Data serialization
- `datetime` - Time calculations
- `subprocess` - Process management

## Cross-References

- **Database Schema**: See [docs/API.md](../docs/API.md#database-layer) for schema details
- **Hook System**: See `.claude/hooks/` for hook implementation
- **Task Management**: See [tasks/README.md](../tasks/README.md) for task lifecycle
- **Setup Guides**: See project README.md for initial setup instructions

## Key Patterns

### CLI Argument Patterns
All scripts use consistent argument naming:
- `--db-path` - Database file path (falls back to config.DATABASE_PATH)
- `--data-dir` - Data directory path
- `--days` - Time range filter (days)
- `--limit` - Result count limit

### Database Path Resolution
Scripts use centralized config:
```python
from core.config import get_db_path_with_fallback

db_path = get_db_path_with_fallback(cli_arg=args.db_path)
```

### Hook Recording Pattern
Pre/post hooks follow consistent flow:
1. Parse tool invocation from stdin (JSON)
2. Extract metadata (task_id, tool_name, params)
3. Write to database.tool_usage
4. Log to stderr for debugging

### Migration Safety
Migration scripts follow pattern:
1. Backup original data
2. Create new schema/tables
3. Transform and insert data
4. Verify integrity (counts, samples)
5. Keep backup for rollback

## Performance Considerations

### Analysis Script Optimization
- Use database indices for fast queries
- Limit time ranges to reduce dataset
- Stream large result sets (don't load all in memory)

### Hook Recording Overhead
- Async writes to avoid blocking tool execution
- Batch inserts where possible (post-tool-use hook)
- Minimal logging to reduce I/O

### iTerm Layout Speed
- AppleScript optimized to minimize delays
- Uses tabs instead of windows for faster load

## Notes

- All Python scripts use shebang: `#!/usr/bin/env python3`
- Shell scripts use shebang: `#!/bin/bash`
- Hook recording scripts called by `.claude/hooks/` (not directly)
- Analysis scripts safe to run on production database (read-only)
- Migration scripts should be tested on backup first
- launchd services run with user permissions (not root)
- iTerm setup scripts macOS-specific (Terminal.app not supported)
- Test scripts safe to run multiple times (idempotent)
