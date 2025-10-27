# Clean Log Format - Quick Reference

## What Changed

The tool usage monitor now uses a clean, human-readable log format with visual icons and concise formatting.

## Before vs After

### Before
```
2025-10-20 15:29:08,123 - tool_usage_tracker - INFO - Tool completed: test-task-123456789 - Read (45.50ms, success)
2025-10-20 15:29:08,456 - tool_usage_tracker - INFO - Tool completed: test-task-987654321 - Bash (567.20ms, failed)
2025-10-20 15:29:10,789 - tool_usage_tracker - INFO - Agent status: test-task-123456789 - completed (Task finished)
```

### After
```
[15:29:08] ✓ Read completed in 46ms (task: test-tas)
[15:29:08] ✗ Bash failed in 567ms (task: test-tas)
    Error: Command failed with exit code 1
[15:29:10] ✓ Status: completed (task: test-tas) - Task finished
```

## Log Format Patterns

### Tool Start
```
[HH:MM:SS] 🔧 TOOL_NAME started (task: TASK_ID) (key_parameters)
```

### Tool Complete (Success)
```
[HH:MM:SS] ✓ TOOL_NAME completed in DURATION (task: TASK_ID)
```

### Tool Complete (Failure)
```
[HH:MM:SS] ✗ TOOL_NAME failed in DURATION (task: TASK_ID)
    Error: ERROR_MESSAGE
```

### Status Change
```
[HH:MM:SS] ICON Status: STATUS (task: TASK_ID) - MESSAGE
```

## Icons Reference

- **🔧** - Tool started
- **✓** - Success/completed
- **✗** - Failed/error
- **▶** - Started/resumed
- **⏸** - Paused

## Features

1. **Concise timestamps** - [HH:MM:SS] instead of full date/time
2. **Visual icons** - Quick status recognition
3. **Short task IDs** - First 8 characters only
4. **Smart parameters** - Shows only relevant info per tool
5. **Human-friendly durations** - "46ms" or "2.35s"
6. **Truncated errors** - First 100 chars to prevent clutter

## Structured JSON Logging (Optional)

To enable machine-readable JSON logs, modify `main.py`:

```python
tool_usage_tracker = ToolUsageTracker(
    db=db,
    data_dir="data",
    enable_structured_logging=True  # Add this
)
```

This creates `logs/tool_usage_structured.jsonl`:
```json
{"timestamp":"2025-10-20T15:29:08.123","event_type":"tool_complete","task_id":"test-task-123","tool_name":"Read","duration_ms":45.5,"success":true}
```

## Testing

Run the test to see examples:
```bash
python3 test_log_format_simple.py
```

## Where to Find Logs

- **Standard logs:** `logs/bot.log`
- **Structured JSON logs:** `logs/tool_usage_structured.jsonl` (if enabled)

## Integration

The clean format is already active! All tool usage is automatically logged in the new format through the hooks in `main.py:100-122`.

## Code References

- **Formatter:** `telegram_bot/tool_usage_tracker.py:21-183` (CleanLogFormatter class)
- **Hooks:** `telegram_bot/main.py:100-122` (log_tool_start, log_tool_complete, log_status_change)
- **Structured logging:** `telegram_bot/tool_usage_tracker.py:478-506` (_write_structured_log method)

## No Action Required

The clean log format is already implemented and active. Your existing code will automatically benefit from the improved logging.

For detailed documentation, see `CLEAN_LOG_FORMAT_IMPLEMENTATION.md`.
