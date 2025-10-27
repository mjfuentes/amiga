# File Path Logging in Terminal Session Monitor

## Overview

File path logging has been added to the terminal session monitor to track which files Claude Code operates on during task execution. This provides better visibility into file operations and helps with debugging, auditing, and understanding task execution.

## What Was Changed

### 1. Hook Enhancements

#### Pre-Tool-Use Hook (`.claude/hooks/pre-tool-use`)
- Added `extract_file_paths()` function that extracts file paths from tool parameters
- Supports extraction from:
  - **File operation tools**: Read, Write, Edit (extracts `file_path` parameter)
  - **Pattern matching tools**: Glob, Grep (extracts patterns and paths)
  - **Bash commands**: Parses common file operations (cat, cp, mv, etc.)
  - **Notebook operations**: NotebookEdit (extracts `notebook_path`)
- Adds `file_paths` array to the log entry

#### Post-Tool-Use Hook (`.claude/hooks/post-tool-use`)
- Added `extract_file_paths_from_response()` function that extracts file paths from tool responses
- Captures file paths returned by:
  - **Glob**: List of matching files
  - **Grep**: Files with matches
  - Generic responses with `file_path` field
- Adds `file_paths` array to the log entry

### 2. HooksReader Updates (`telegram_bot/hooks_reader.py`)

Added new methods:
- **`get_session_file_operations(session_id)`**: Returns all file operations with file paths for a session
  - Combines pre-tool and post-tool logs
  - Matches operations by timestamp and tool name
  - Returns timestamp, tool, file paths, status, and error information

- **`_parse_timestamp(timestamp_str)`**: Helper to parse ISO timestamps for comparison

Updated existing methods:
- **`get_session_timeline()`**: Now includes `file_paths` field in each event

### 3. Monitoring API (`telegram_bot/monitoring_server.py`)

Added new endpoint:
- **`GET /api/sessions/<session_id>/file-operations`**
  - Returns all file operations for a session
  - Provides aggregated statistics:
    - Total operations count
    - Total files accessed
    - Unique files list
    - Files grouped by tool type
  - Example response:
    ```json
    {
      "session_id": "task_123",
      "file_operations": [
        {
          "timestamp": "2025-10-20T12:00:00Z",
          "tool": "Read",
          "file_paths": ["/path/to/file.py"],
          "status": "starting",
          "has_error": false
        }
      ],
      "total_operations": 5,
      "total_files": 8,
      "unique_files": ["/path/to/file1.py", "/path/to/file2.py"],
      "files_by_tool": {
        "Read": {"count": 3, "files": ["/path/to/file1.py"]},
        "Write": {"count": 2, "files": ["/path/to/file2.py"]}
      }
    }
    ```

### 4. Session Monitor Enhancements (`telegram_bot/claude_interactive.py`)

- Added workspace path to status change metadata
- Added terminal logging of working directory when session starts

## How to Use

### 1. Automatic Logging

File paths are automatically logged whenever Claude Code performs file operations during task execution. The hooks run transparently in the background.

### 2. Viewing Logs Directly

Check the JSONL log files in `logs/sessions/<session_id>/`:

```bash
# View pre-tool logs (before tool execution)
cat logs/sessions/<session_id>/pre_tool_use.jsonl | jq '.file_paths'

# View post-tool logs (after tool execution)
cat logs/sessions/<session_id>/post_tool_use.jsonl | jq '.file_paths'
```

### 3. Using the Python API

```python
from hooks_reader import HooksReader

reader = HooksReader(sessions_dir="logs/sessions")

# Get all file operations for a session
file_ops = reader.get_session_file_operations("task_123")

for op in file_ops:
    print(f"{op['tool']}: {op['file_paths']}")
```

### 4. Using the REST API

```bash
# Get file operations for a session
curl http://localhost:5001/api/sessions/task_123/file-operations

# Pretty print with jq
curl -s http://localhost:5001/api/sessions/task_123/file-operations | jq .
```

### 5. Terminal Output

When a task starts, the working directory is now logged:

```
[INFO] Task task_123: Working directory: /Users/username/project
[INFO] Interactive session started (PID: 12345)
```

## File Path Extraction Details

### Supported Tools

| Tool | Extraction Method | Example |
|------|-------------------|---------|
| Read | `file_path` parameter | `/path/to/file.py` |
| Write | `file_path` parameter | `/path/to/output.txt` |
| Edit | `file_path` parameter | `/path/to/file.js` |
| Glob | `pattern` + `path` parameters | `glob:**/*.py`, `/project` |
| Grep | `path` + `glob` parameters | `/src`, `glob:*.js` |
| Bash | Regex parsing of commands | Extracts from cat, cp, mv, etc. |
| NotebookEdit | `notebook_path` parameter | `/path/to/notebook.ipynb` |

### Bash Command Parsing

The pre-tool hook uses regex patterns to extract file paths from common Bash commands:

- File viewers: `cat`, `head`, `tail`, `less`, `more`
- Editors: `vim`, `nano`, `emacs`, `code`, `open`
- File operations: `cp`, `mv`, `rm`, `chmod`, `chown`
- Directory operations: `cd`, `ls`, `mkdir`, `rmdir`, `touch`
- Redirections: `>`, `>>`

Example:
```bash
cat /tmp/test.log > /tmp/output.txt
# Extracts: ["/tmp/test.log", "/tmp/output.txt"]
```

## Testing

Run the test script to verify file path logging:

```bash
cd telegram_bot
python3 test_filepath_logging.py
```

This will:
1. List available sessions
2. Test file operations extraction
3. Display sample file paths from logs
4. Show manual extraction examples

## Log Format

### Pre-Tool Log Entry
```json
{
  "timestamp": "2025-10-20T12:00:00Z",
  "tool": "Read",
  "parameters": {
    "file_path": "/path/to/file.py"
  },
  "file_paths": ["/path/to/file.py"],
  "status": "starting"
}
```

### Post-Tool Log Entry
```json
{
  "timestamp": "2025-10-20T12:00:01Z",
  "agent": "code_agent",
  "tool": "Read",
  "output_length": 1234,
  "has_error": false,
  "file_paths": []
}
```

## Benefits

1. **Debugging**: Quickly see which files were accessed during task execution
2. **Auditing**: Track all file operations for compliance and security
3. **Performance**: Identify frequently accessed files for optimization
4. **Understanding**: Better comprehension of task execution flow
5. **Monitoring**: Real-time tracking of file operations via API

## Future Enhancements

Potential improvements:
- Add file path filtering in API queries
- Track file modification vs. read operations separately
- Add file size and checksum tracking
- Create visualizations showing file access patterns
- Add alerts for sensitive file access
- Export file operation reports

## Notes

- File paths are extracted on a best-effort basis from tool parameters and responses
- Some file paths may be missed if they're embedded in complex command strings
- Glob patterns are prefixed with `glob:` to distinguish them from actual file paths
- The hooks are resilient and won't fail the task if extraction fails
- File paths are deduplicated within each operation

## Troubleshooting

### No file paths in logs

If you don't see `file_paths` in the logs:
1. Verify hooks are executable: `ls -l .claude/hooks/`
2. Check hook error logs: `cat /tmp/post-tool-use-errors.log`
3. Ensure the session is new (created after implementing these changes)

### API returns empty file operations

- The session may not have any file operations
- Check if the session logs exist: `ls logs/sessions/<session_id>/`
- Verify the logs contain `file_paths` field: `cat logs/sessions/<session_id>/pre_tool_use.jsonl`

### Hooks not running

- Make hooks executable: `chmod +x .claude/hooks/*`
- Check Claude Code is using the correct config directory
- Verify `SESSION_ID` environment variable is set correctly
