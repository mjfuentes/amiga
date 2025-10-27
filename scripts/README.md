# Scripts

## Purpose
Utility scripts for analysis, hook recording, and system maintenance.

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

#### query_top_tools.py
Queries top tools by usage from database.
- Tool usage leaderboard
- Success rates
- Average durations

Usage:
```bash
python scripts/query_top_tools.py --limit 10
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

## Usage Patterns

### Analysis Workflow
```bash
# 1. Check recent errors
python scripts/analyze_errors.py --days 7

# 2. Analyze tool usage
python scripts/analyze_tool_usage.py --days 7

# 3. Check API usage
python scripts/check_usage.py

# 4. Query top tools
python scripts/query_top_tools.py --limit 10
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

## Cross-References

- **Database Schema**: See CLAUDE.md for schema details
- **Hook System**: See `.claude/hooks/` for hook implementation
- **Task Management**: See `tasks/` for task lifecycle

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

## Performance Considerations

### Analysis Script Optimization
- Use database indices for fast queries
- Limit time ranges to reduce dataset
- Stream large result sets (don't load all in memory)

### Hook Recording Overhead
- Async writes to avoid blocking tool execution
- Batch inserts where possible (post-tool-use hook)
- Minimal logging to reduce I/O

## Notes

- All Python scripts use shebang: `#!/usr/bin/env python3`
- Shell scripts use shebang: `#!/bin/bash`
- Hook recording scripts called by `.claude/hooks/` (not directly)
- Analysis scripts safe to run on production database (read-only)
- launchd services run with user permissions (not root)
