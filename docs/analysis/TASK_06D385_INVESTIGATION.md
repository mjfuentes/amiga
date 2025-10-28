# Task 06d385 False Failure Investigation

## Summary

Task #06d385 completed successfully (commit `3fcc6de`) but was marked as `failed` due to process death detection racing with success verification.

## Timeline

```
10:33:20 - Task created (PID 18013)
10:35:45 - Commit 3fcc6de made to main branch
10:36:41 - Process 18013 detected dead, task marked failed
```

**Gap**: ~1 minute between commit and detection

## Root Cause

### The Issue
The task monitor (`tasks/monitor.py`) has success detection logic to handle race conditions where processes die after completing work, but it **failed to detect this task's success**.

### Why Detection Failed

The `_check_task_success()` method looks for:
1. ✅ Task branch `task/06d385` exists with commits
2. ✅ Task branch merged to main
3. ✅ Merge commit pattern: `"Merge task 06d385"` in main

**None of these conditions matched** because:
- ❌ No task branch was created (`task/06d385` doesn't exist)
- ❌ Work was committed directly to `main` branch
- ❌ Commit message: `"Hide task sidebar on mobile viewports (≤768px) for full-screen chat"` doesn't match merge pattern

### The Gap

**Missing detection case**: Direct commits to main within task timeframe

The monitor checks:
```python
# tasks/monitor.py:257-266
# Pattern: "Merge task {task_id[:8]}"
result = subprocess.run(
    ["git", "log", "--oneline", "main", "-10", "--grep", f"Merge task {task_id[:8]}"],
    ...
)
```

But commit `3fcc6de` has no reference to task ID in message.

## Why The Process Died

**Unknown** - Process 18013 no longer exists and logs don't show crash reason.

Possible causes:
1. Task completed and exited normally before reporting back
2. Claude Code CLI session ended after git commit
3. Signal received (SIGTERM/SIGKILL)
4. Unhandled exception after commit

Session logs show:
- Last tool call: `09:35:49` (Bash command)
- Commit timestamp: `10:35:45`
- Process death detected: `10:36:41`

**Note**: Timestamps in session logs are UTC, commit is UTC+1 (local time)

## Impact

✅ **No data loss** - Commit successfully merged to main
❌ **False failure** - Task marked failed in database
⚠️ **User confusion** - Dashboard shows failed task despite successful work

## Recommended Fixes

### 1. Enhanced Success Detection (High Priority)

Add fallback check for recent commits on current branch:

```python
# tasks/monitor.py _check_task_success()

# After checking for task branch and merge commits:
# Check for ANY recent commits in task timeframe
task_created = task.get("created_at")  # ISO timestamp
task_window = 60  # minutes

result = subprocess.run(
    ["git", "log", "--oneline", "--since", task_created,
     "--author=Claude", "--all", "-1"],
    cwd=workspace,
    capture_output=True,
    text=True,
    timeout=5
)

if result.returncode == 0 and result.stdout.strip():
    indicators['has_commits'] = True
    logger.debug(f"Task {task_id}: Found commit in task timeframe")
```

### 2. Process Exit Logging (Medium Priority)

Add exception handling and exit logging to task execution:

```python
# core/orchestrator.py or tasks/pool.py

try:
    result = await execute_task(...)
    logger.info(f"Task {task_id}: Completed normally")
    return result
except Exception as e:
    logger.error(f"Task {task_id}: Exception during execution", exc_info=True)
    raise
finally:
    logger.debug(f"Task {task_id}: Process exiting (PID {os.getpid()})")
```

### 3. Grace Period Before Marking Failed (Low Priority)

Add delay between detecting dead process and marking failed to allow git operations to sync:

```python
# tasks/monitor.py

if not is_process_alive(pid):
    # Wait 30s before checking success - allows git ops to complete
    await asyncio.sleep(30)

    # Re-check success indicators
    success_indicators = await self._check_task_success(task)
    ...
```

## Prevention

1. **Enforce task branches**: Git-worktree agent should create isolated branches
2. **Standardize commit messages**: Include task ID in all commits
3. **Monitor agent compliance**: Pre-commit hook validates task ID in commit messages during task execution

## Related

- Git-worktree cleanup disabled (2025-10-22) - May be related
- Orchestrator workflow - Should have used git-worktree agent
- Similar issues in database: Check for other `[dead_process]` failures

## Resolution

Task status manually corrected:
```bash
sqlite3 data/agentlab.db "UPDATE tasks SET status = 'completed', error = NULL,
  result = 'Task completed successfully. Work committed in 3fcc6de.'
  WHERE task_id = '06d385';"
```

## Fix Implemented

**Date**: 2025-10-28

Updated agent prompts to include task ID in all commit messages:

**Files modified**:
- `.claude/agents/orchestrator.md` - Added task ID requirement to code_agent and frontend_agent prompts
- `.claude/agents/code_agent.md` - Updated commit message format to include `(task: $TASK_ID)`
- `.claude/agents/frontend_agent.md` - Updated commit message format to include `(task: $TASK_ID)`
- `.claude/agents/git-merge.md` - Updated merge commit format to `Merge task $TASK_ID: description`

**New format**:
- Regular commits: `"Brief description (task: $TASK_ID)"`
- Merge commits: `"Merge task $TASK_ID: brief description"`

**Impact**:
- All future commits will include task ID
- Monitor's `_check_task_success()` can detect task ID in commit messages
- Reduces false failures from dead process detection
- Improves task tracking and debugging
