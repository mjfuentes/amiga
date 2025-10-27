# Hook Path Resolution Update

**Date**: 2025-10-21
**Hook**: `~/.claude/hooks/post-tool-use`
**Backup**: `~/.claude/hooks/post-tool-use.backup`

## Changes Made

Updated database path resolution logic in `post-tool-use` hook for improved reliability.

## Key Improvements

### 1. Priority-Based Path Resolution

**Old approach**: Hardcoded list of paths to search
```python
for base in [
    Path('/Users/matifuentes/Workspace/agentlab'),
    Path.cwd().parent if Path.cwd().name == 'telegram_bot' else Path.cwd(),
    Path('/Users/matifuentes/Workspace/agentlab/telegram_bot')
]:
    if (base / 'data').exists():
        data_dir = base / 'data'
        break
```

**New approach**: Priority-based with env var support
```python
# Priority 1: Use PROJECT_ROOT env var if available
project_root_env = os.environ.get('PROJECT_ROOT')
if project_root_env:
    project_root = Path(project_root_env)
    if (project_root / 'data').exists():
        data_dir = project_root / 'data'

# Priority 2: Search upward for .git directory
if not data_dir:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / '.git').exists():
            project_root = parent
            if (parent / 'data').exists():
                data_dir = parent / 'data'
                break

# Priority 3: Fallback to hardcoded paths
```

### 2. Database Existence Validation

**Added**: Explicit validation before database write
```python
# Validate database exists before attempting write
if not db_path.exists():
    with open('/tmp/hook_debug.log', 'a') as debug_log:
        debug_log.write(f'[WARNING] Database not found at {db_path}\n')
```

### 3. Enhanced Debug Logging

**Added**:
- Log which path resolution method succeeded
- Warn if multiple data directory candidates found
- Warn if no data directory found at all
- Log current working directory when path resolution fails

### 4. Improved Log Directory Resolution

**Added**: Use `project_root` (if found) to search for log directories
```python
if project_root:
    log_candidates = [
        project_root / 'logs',
        project_root / 'telegram_bot' / 'logs',
    ]
    for candidate in log_candidates:
        if candidate.exists():
            log_dir = candidate / 'sessions' / session_id
            break
```

## Testing

### Syntax Validation
- Bash syntax: ✅ Passed (`bash -n`)
- Python logic: ✅ Passed (extracted and tested)

### Path Resolution Test
```bash
$ python3 test_script.py
Found project root via .git: /Users/matifuentes/Workspace/agentlab
Final data_dir: /Users/matifuentes/Workspace/agentlab/data
Database exists: True
```

## Benefits

1. **Reliability**: Uses git root detection instead of hardcoded paths
2. **Flexibility**: Supports PROJECT_ROOT env var for custom configurations
3. **Debuggability**: Enhanced logging for troubleshooting path issues
4. **Safety**: Validates database exists before write attempts
5. **Consistency**: Matches application's path resolution logic

## Recovery

If issues occur, restore from backup:
```bash
cp ~/.claude/hooks/post-tool-use.backup ~/.claude/hooks/post-tool-use
```

## Related Files

- Hook: `~/.claude/hooks/post-tool-use`
- Backup: `~/.claude/hooks/post-tool-use.backup`
- Debug log: `/tmp/hook_debug.log`
- Database: `/Users/matifuentes/Workspace/agentlab/data/agentlab.db`
