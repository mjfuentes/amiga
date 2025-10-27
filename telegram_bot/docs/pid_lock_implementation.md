# PID File Lock Implementation

## Problem
The bot experienced repeated "Conflict: terminated by other getUpdates request" errors when multiple instances were running concurrently. Telegram's Bot API only allows one active polling connection per bot token.

## Solution
Implemented a PID (Process ID) file-based locking mechanism to ensure only one bot instance runs at a time.

## Implementation Details

### PIDFileLock Class (`main.py:78-198`)
```python
class PIDFileLock:
    """Manages a PID file to ensure only one bot instance runs at a time."""
```

**Key Methods:**
- `acquire()`: Attempts to acquire the lock by creating/checking PID file
- `release()`: Releases the lock by removing the PID file
- `_is_process_running()`: Checks if a process is still alive using `os.kill(pid, 0)`
- `_signal_handler()`: Handles SIGTERM/SIGINT for graceful shutdown

### Startup Integration (`main.py:2393-2396`)
```python
# Acquire PID lock to prevent multiple instances
if not pid_lock.acquire():
    logger.error("Failed to acquire PID lock. Exiting.")
    sys.exit(1)
```

**Behavior:**
- Checks for existing PID file at `data/bot.pid`
- If exists, verifies the process is still running
- If process is dead, removes stale PID file and continues
- If process is alive, exits with error message
- If no PID file exists, creates one with current PID

### Shutdown Integration (`main.py:2452-2454`)
```python
# Release PID lock
logger.info("Releasing PID lock...")
pid_lock.release()
```

**Behavior:**
- Removes PID file during graceful shutdown
- Verifies PID matches before removal (prevents removing other instance's file)
- Automatically called via `atexit` handler and signal handlers

### Enhanced Error Logging (`main.py:2272-2294`)
```python
# Check for the specific getUpdates conflict error
if "Conflict: terminated by other getUpdates request" in error_msg:
    logger.error(
        "INSTANCE CONFLICT: Multiple bot instances detected! "
        f"This instance (PID: {os.getpid()}) will stop receiving updates."
    )
```

**Provides:**
- Clear identification of instance conflict errors
- Helpful troubleshooting steps (ps aux, kill commands)
- Current process PID for debugging

## Features

### Race Condition Prevention
- Atomic file operations for creating/checking PID file
- Process existence verification using OS-level signals
- No race conditions between check and create

### Stale Lock Detection
- Automatically detects and removes PID files from crashed processes
- Uses `os.kill(pid, 0)` to check process existence without sending actual signal
- Handles corrupted PID files gracefully

### Graceful Shutdown
- Signal handlers for SIGTERM and SIGINT
- Automatic cleanup via `atexit` registration
- Prevents orphaned PID files

### Error Messages
**When duplicate instance detected:**
```
ERROR - Another bot instance is already running (PID: 12345).
        Only one instance can run at a time.
        To stop the existing instance:
          kill 12345
        Or use the /restart command from Telegram.
```

**When getUpdates conflict occurs:**
```
ERROR - INSTANCE CONFLICT: Multiple bot instances detected!
        Another instance is polling for updates.
        This instance (PID: 67890) will stop receiving updates.
        To fix this issue:
        1. Check for other running instances: ps aux | grep 'telegram_bot/main.py'
        2. Stop duplicate instances: kill <PID>
        3. Use /restart command instead of starting new instances
```

## Testing

### Unit Tests (`tests/test_pid_lock.py`)
- Test successful lock acquisition
- Test lock failure with existing instance
- Test stale PID file handling
- Test corrupted PID file handling
- Test proper lock release
- Test release with different PID (safety check)
- Test double release (no errors)

### Manual Testing
```bash
# Start first instance
python telegram_bot/main.py

# Try to start second instance (should fail)
python telegram_bot/main.py
# Expected: "Failed to acquire PID lock. Exiting."

# Check PID file
cat data/bot.pid
# Expected: PID of running instance

# Stop first instance (Ctrl+C)
# Check PID file is removed
ls data/bot.pid
# Expected: file not found
```

## Files Modified
- `/Users/matifuentes/Workspace/agentlab/telegram_bot/main.py`
  - Added imports: `atexit`, `signal`, `sys`
  - Added PIDFileLock class (lines 78-198)
  - Modified main() to acquire lock (lines 2393-2396)
  - Modified shutdown() to release lock (lines 2452-2454)
  - Enhanced error_handler() for conflicts (lines 2272-2294)

- `/Users/matifuentes/Workspace/agentlab/.gitignore`
  - Added `data/*.pid` to ignore list

- `/Users/matifuentes/Workspace/agentlab/telegram_bot/tests/test_pid_lock.py`
  - New file with comprehensive unit tests

## Rollout Plan

1. **Current Instance**: Will continue running without PID file until restarted
2. **Next Restart**: Will create PID file and enforce single-instance constraint
3. **Future Starts**: Will fail if another instance is running

## Monitoring

**Log Messages to Watch:**
```bash
# Successful startup
INFO - PID file lock acquired (PID: 12345)

# Graceful shutdown
INFO - Releasing PID lock...
INFO - PID file lock released

# Instance conflict
ERROR - Another bot instance is already running (PID: 12345)
ERROR - INSTANCE CONFLICT: Multiple bot instances detected!

# Stale lock cleanup
WARNING - Found stale PID file (PID 99999 not running). Removing...
```

## Related Issues
- Resolves: "Conflict: terminated by other getUpdates request; make sure that only one bot instance is running"
- Prevents: Multiple bot instances competing for Telegram updates
- Improves: Startup safety and error diagnostics

## Future Enhancements
- Consider using `fcntl.flock()` for more robust file locking (Unix-specific)
- Add lock timeout option for automatic stale lock cleanup
- Add PID file location to config/environment variables
- Consider systemd integration for automatic instance management
