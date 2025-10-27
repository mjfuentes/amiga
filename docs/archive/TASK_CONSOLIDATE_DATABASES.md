# Task: Consolidate Database Architecture

## Problem Statement
Tool usage data not appearing in monitoring dashboard due to database file mismatch:
- **Hooks write to**: `/agentlab/data/agentlab.db` (parent directory)
- **App reads from**: `/agentlab/telegram_bot/data/agentlab.db` (subdirectory)
- **Result**: Two separate SQLite databases with different inodes, causing data fragmentation

## Immediate Fix (DONE)
Created symlink: `telegram_bot/data` → `../data`
- Committed in: 098f8e9

## Required Permanent Solution
Consolidate to **single database location** and enforce across all code paths:

### 1. Merge Existing Data
- Copy all records from `telegram_bot/data/agentlab.db` to parent `data/agentlab.db`
- Verify no data loss (check counts before/after)
- Remove old database file after successful migration
- Handle backup files (.db.backup, .db.corrupted.*, etc.)

### 2. Code Audit & Fix
Search and replace all hardcoded database paths to use consistent base path:
- `monitoring_server.py`: Uses `data_dir = "../data"` when run from telegram_bot
- `tasks.py`, `tool_usage_tracker.py`, `database.py`: Check for hardcoded paths
- **Hooks** (`~/.claude/hooks/post-tool-use`): Currently searches multiple locations
- Ensure all components resolve to **same absolute path**

### 3. Centralize Database Configuration
Create single source of truth for data directory:
```python
# config.py or similar
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent  # agentlab/
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "agentlab.db"
```

Update all modules to import from config instead of computing paths locally.

### 4. Prevent Future Divergence
- Add pre-commit hook to block creation of `telegram_bot/data/` directory
- Add runtime check: if multiple `agentlab.db` files exist, raise error and exit
- Document in CLAUDE.md: "Single database at `/agentlab/data/agentlab.db` ONLY"

### 5. Hook Path Resolution
Update `~/.claude/hooks/post-tool-use` to:
- Use `PROJECT_ROOT` env var if set
- Fall back to searching upward from CWD for `.git` directory
- Validate database path exists before attempting write
- Log warning if multiple candidate paths found

## Acceptance Criteria
- [ ] All data from `telegram_bot/data/agentlab.db` merged into `data/agentlab.db`
- [ ] All code paths resolve to same database file (verified by inode check)
- [ ] Hooks write to correct database (verified in `/tmp/hook_debug.log`)
- [ ] Monitoring dashboard shows tool usage from current session
- [ ] No `agentlab.db` files exist outside `/agentlab/data/`
- [ ] Pre-commit hook blocks re-creation of telegram_bot/data/
- [ ] Documentation updated in CLAUDE.md

## Workflow
Run as `code_task` workflow to ensure automated, tested, and committed solution.
