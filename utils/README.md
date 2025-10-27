# Utils

## Purpose
Shared utility modules providing git operations, log formatting, log analysis, log monitoring, and git worktree management.

## Components

### git.py
Git repository operations and dirty state tracking.
- `GitTracker`: tracks repositories with uncommitted changes
- Repository status checking (staged/unstaged files)
- Dirty state persistence (JSON file)
- Blocking message generation for workflow enforcement
- Repository discovery and validation

### log_formatter.py
Terminal-style log formatting for dashboard display.
- `TerminalLogFormatter`: formats tool execution logs
- Tool color mapping (Read=green, Write=purple, etc.)
- MCP tool detection and formatting
- File path extraction and highlighting
- Timestamp formatting
- Error highlighting

### log_analyzer.py
Log file analysis for error detection and pattern matching.
- `LogAnalyzer`: parses bot.log and monitoring.log
- Error extraction (ERROR, WARNING, CRITICAL)
- Pattern matching (exceptions, tracebacks)
- Context line extraction (before/after error)
- Severity classification
- Time-based filtering

### log_monitor.py
Real-time log monitoring with alerting.
- `LogMonitor`: watches log files for changes
- Tail-like behavior (follow mode)
- Error detection and alerting
- Pattern-based filtering
- Callback hooks for new entries

### worktree.py
Git worktree management for task isolation.
- `WorktreeManager`: creates/manages git worktrees
- Task-specific worktree creation
- Automatic cleanup on task completion
- Branch management for worktrees
- Merge operations back to main

### helpers.py
Miscellaneous utility functions.
- String manipulation helpers
- Time/date formatting
- File system operations
- Common validators

## Usage Examples

### Git Tracking
```python
from utils.git import GitTracker

tracker = GitTracker(data_file="data/git_tracker.json")

# Check repository status
has_changes, status = tracker.check_repo_status("/path/to/repo")
# (True, "5 files changed (3 staged, 2 unstaged)")

# Mark repository as dirty
tracker.mark_dirty("/path/to/repo", operation="code_agent")

# Check if repo blocks work
blocking_msg = tracker.get_blocking_message("/path/to/other-repo")
if blocking_msg:
    print(blocking_msg)
    # "Cannot proceed: uncommitted changes in /path/to/repo"

# Mark repository as clean (after commit)
tracker.mark_clean("/path/to/repo")

# Get all dirty repositories
dirty_repos = tracker.get_dirty_repos()
# {"/path/to/repo": "code_agent"}
```

### Log Formatting
```python
from utils.log_formatter import TerminalLogFormatter

formatter = TerminalLogFormatter()

# Get tool color
color = formatter.get_tool_color("Read")
# "#3fb950" (green)

# Format log entry
formatted = formatter.format_log_entry({
    "timestamp": "2025-10-22T10:30:45",
    "tool_name": "Read",
    "file_path": "/path/to/file.py",
    "duration_ms": 150,
    "success": True
})
# Styled HTML with color coding and file path highlighting
```

### Log Analysis
```python
from utils.log_analyzer import LogAnalyzer

analyzer = LogAnalyzer(log_file="logs/bot.log")

# Get recent errors
errors = analyzer.get_errors(hours=24, severity="ERROR")
# [
#     {
#         "timestamp": "2025-10-22T10:30:45",
#         "level": "ERROR",
#         "message": "Failed to connect to database",
#         "context_before": [...],
#         "context_after": [...]
#     },
#     ...
# ]

# Search for patterns
matches = analyzer.search_pattern("timeout|connection.*failed")
# List of matching log entries with context

# Get error summary
summary = analyzer.get_error_summary(days=7)
# {
#     "total_errors": 45,
#     "by_severity": {"ERROR": 35, "WARNING": 10},
#     "by_module": {"core.main": 20, "tasks.manager": 15, ...}
# }
```

### Log Monitoring
```python
from utils.log_monitor import LogMonitor

def on_error(entry):
    print(f"ERROR: {entry['message']}")

monitor = LogMonitor(log_file="logs/bot.log")

# Start monitoring (blocks)
monitor.start(
    follow=True,
    on_error=on_error,
    filter_pattern="ERROR|CRITICAL"
)

# Or use async monitoring
async with LogMonitor(log_file="logs/bot.log") as monitor:
    async for entry in monitor.watch():
        if entry["level"] == "ERROR":
            handle_error(entry)
```

### Worktree Management
```python
from utils.worktree import WorktreeManager

manager = WorktreeManager(base_repo="/path/to/repo")

# Create task-specific worktree
worktree_path = manager.create_worktree(
    task_id="abc123",
    branch_name="task/abc123"
)
# Returns: "/tmp/agentlab-worktrees/abc123"

# Work is isolated in worktree...
# Agent makes changes and commits in worktree

# Merge back to main
success, message = manager.merge_worktree(
    task_id="abc123",
    target_branch="main"
)

# Cleanup worktree
manager.cleanup_worktree(task_id="abc123")
```

## Dependencies

### Internal
- `core/config.py` - Configuration paths

### External
- `subprocess` - Git command execution
- `pathlib` - Path operations
- `json` - State persistence
- `re` - Pattern matching for log analysis
- `asyncio` - Async log monitoring

## Architecture

### Git Tracker Flow
```
Agent modifies files
    ↓
mark_dirty() called
    ↓
check_repo_status() verifies changes
    ↓
Save to git_tracker.json
    ↓
Other agents check get_blocking_message()
    ↓ (blocked until marked clean)
mark_clean() after commit
```

### Log Analysis Pipeline
```
Log file (logs/bot.log)
    ↓
LogAnalyzer reads lines
    ↓
Parse timestamp, level, module, message
    ↓
Filter by severity/time range
    ↓
Extract context (lines before/after)
    ↓
Return structured error objects
```

### Worktree Lifecycle
```
create_worktree()
    ↓
git worktree add /tmp/agentlab-worktrees/abc123
    ↓
Agent works in isolated directory
    ↓
Changes committed to task/abc123 branch
    ↓
merge_worktree() → git merge task/abc123
    ↓
cleanup_worktree() → git worktree remove
```

## Cross-References

- **Git Operations**: See [tasks/README.md](../tasks/README.md) for task branch management
- **Log Formatting**: See [monitoring/README.md](../monitoring/README.md) for dashboard integration
- **Testing**: See [tests/README.md](../tests/README.md) for utility function tests

## Key Patterns

### Dirty State Persistence
Git tracker persists state to survive bot restarts:
```json
{
  "/path/to/repo": "code_agent",
  "/path/to/other-repo": "frontend_agent"
}
```

### Context Line Extraction
Log analyzer extracts N lines before/after errors for debugging:
```python
error_with_context = {
    "message": "Database connection failed",
    "context_before": ["Connecting to database...", "Retry attempt 1"],
    "context_after": ["Falling back to local storage"]
}
```

### Tool Color Coding
Dashboard uses consistent color scheme:
- Read: Green (#3fb950)
- Write: Purple (#a371f7)
- Edit: Light Purple (#d2a8ff)
- Bash: Cyan (#58a6ff)
- Grep: Orange (#f0883e)
- MCP tools: Dark Orange (#db6d28)
- Errors: Red (#f85149)

### Worktree Isolation
Each task gets dedicated worktree to prevent:
- Merge conflicts between concurrent tasks
- Uncommitted changes blocking other work
- Branch switching disrupting running agents

### Log Streaming
Log monitor supports tail-like behavior:
```python
async for entry in monitor.watch():
    # Process new entries as they appear
    handle_log_entry(entry)
```

## Performance Considerations

### Git Status Caching
Git tracker caches status checks for 5 seconds to reduce subprocess overhead.

### Log File Rotation
Log analyzer handles rotated logs (bot.log.1, bot.log.2, etc.).

### Worktree Cleanup
Worktrees cleaned up asynchronously to avoid blocking task completion.

### Pattern Compilation
Log analyzer pre-compiles regex patterns for faster matching.

## Notes

- Git tracker stores absolute paths (resolved via Path.resolve())
- Log files must be UTF-8 encoded
- Worktrees created in `/tmp/agentlab-worktrees/` (cleared on reboot)
- Git operations use subprocess (not gitpython library)
- Log monitor uses `tail -f` style following (not inotify)
- Color values use GitHub Dark theme palette
- Worktree branches named `task/<task_id>` for easy identification
- Git tracker blocks ALL work if ANY repo is dirty (strict enforcement)
