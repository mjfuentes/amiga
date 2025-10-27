# How to Verify the TodoWrite Planning Fix

## Quick Verification

The fix has been implemented and tested. To verify it's working in your environment:

### Option 1: Check Existing Sessions (If Any Have TodoWrite)

```bash
# Find sessions with TodoWrite calls
cd /Users/matifuentes/Workspace/agentlab
grep -l "TodoWrite" logs/sessions/*/post_tool_use.jsonl

# Pick a session and check if output_preview exists
SESSION_ID="<session_id_from_above>"
grep "TodoWrite" logs/sessions/$SESSION_ID/post_tool_use.jsonl | python3 -m json.tool
```

**Expected**: You should see `output_preview` field containing the TodoWrite data.

**Note**: Only NEW sessions (created after the fix) will have output_preview. Old sessions won't be retroactively fixed.

### Option 2: Create a Test Session with TodoWrite

Use the test script from the fix to verify:

```bash
cd /Users/matifuentes/Workspace/agentlab

python3 << 'EOF'
import os
import json
import subprocess
from pathlib import Path

session_id = 'verify_fix_test'
session_dir = Path(f'logs/sessions/{session_id}')

# Clean up
import shutil
if session_dir.exists():
    shutil.rmtree(session_dir)

env = os.environ.copy()
env['SESSION_ID'] = session_id

# Simulate TodoWrite call
test_data = {
    'session_id': session_id,
    'tool_name': 'TodoWrite',
    'tool_response': {
        'oldTodos': [],
        'newTodos': [
            {'content': 'Task 1', 'status': 'completed', 'activeForm': 'Completing task 1'},
            {'content': 'Task 2', 'status': 'in_progress', 'activeForm': 'Working on task 2'},
            {'content': 'Task 3', 'status': 'pending', 'activeForm': 'Planning task 3'}
        ]
    }
}

subprocess.run(
    ['.claude/hooks/post-tool-use'],
    input=json.dumps(test_data),
    text=True,
    capture_output=True,
    env=env
)

# Verify
log_file = session_dir / 'post_tool_use.jsonl'
if log_file.exists():
    with open(log_file) as f:
        entry = json.loads(f.read())

    if 'output_preview' in entry and entry['output_preview']:
        print("✅ FIX VERIFIED: output_preview field exists!")
        print(f"\nPreview: {entry['output_preview'][:100]}...")

        # Test parsing
        jsonStr = entry['output_preview'].replace("'", '"')
        preview = json.loads(jsonStr)
        print(f"\n✅ PARSING WORKS: Found {len(preview['newTodos'])} todos")
    else:
        print("❌ FIX NOT WORKING: output_preview field missing")
else:
    print("❌ Log file not created")

# Cleanup
shutil.rmtree(session_dir)
EOF
```

### Option 3: Verify in Monitoring Dashboard (Best Test)

1. **Restart the monitoring server** (if running):
   ```bash
   # If monitoring server is running, restart it
   pkill -f monitoring_server.py
   python telegram_bot/monitoring_server.py &
   ```

2. **Create a real Claude Code session with TodoWrite**:
   ```bash
   # Start a Claude Code session (in agentlab directory)
   claude
   ```

3. **In the Claude session, use TodoWrite**:
   ```
   I need to implement a new feature. Let me break this down into tasks:
   [Claude will use TodoWrite to create a task list]
   ```

4. **Check the dashboard**:
   - Open http://localhost:5001
   - Find the session in "Recent Sessions" or "Running Tasks"
   - Click on the session/task
   - Look for the "Planning Progress" section
   - It should show your todo list with progress bars and task status

### Option 4: Check Hook Logs for Errors

```bash
# Check if there were any hook errors
cat /tmp/post-tool-use-errors.log 2>/dev/null || echo "No errors (good!)"

# Check debug data (if any recent sessions)
tail -50 /tmp/hook-debug-data.log 2>/dev/null || echo "No debug data"
```

## What You Should See (Success)

### In post_tool_use.jsonl:
```json
{
  "timestamp": "2025-10-21T07:58:06.467565Z",
  "agent": "unknown",
  "tool": "TodoWrite",
  "output_length": 567,
  "has_error": false,
  "output_preview": "{'oldTodos': [...], 'newTodos': [{'content': 'Task 1', 'status': 'completed', ...}, ...]}"
}
```

### In Monitoring Dashboard:
```
┌─────────────────────────────────────────────┐
│ 📋 Planning Progress                        │
├─────────────────────────────────────────────┤
│                                             │
│ Progress: 66% (2/3 completed)               │
│ [████████████████░░░░░░░░] 66%              │
│                                             │
│ ✓ Task 1 [completed]                        │
│ ⏳ Task 2 [in_progress]                      │
│ ○ Task 3 [pending]                          │
│                                             │
│ 📊 Stats: 2 completed • 1 in progress       │
│         • 0 pending                         │
└─────────────────────────────────────────────┘
```

## Troubleshooting

### "No planning data available" still showing

**Causes**:
1. Old session (created before fix) - Only new sessions will work
2. No TodoWrite calls made in that session
3. Hook not being called (check permissions: `ls -l .claude/hooks/post-tool-use` should show `rwxr-xr-x`)

**Solutions**:
1. Create a new session after the fix
2. Make sure Claude actually calls TodoWrite (it won't for simple tasks)
3. Check hook is executable: `chmod +x .claude/hooks/post-tool-use`

### Dashboard shows error parsing planning data

**Cause**: output_preview format doesn't match expectations

**Check**:
```bash
# Find a TodoWrite entry and examine it
grep "TodoWrite" logs/sessions/*/post_tool_use.jsonl | python3 -m json.tool | less
```

**Solution**: Verify output_preview looks like `{'oldTodos': [...], 'newTodos': [...]}`

### Hook errors in /tmp/post-tool-use-errors.log

**Check the error**:
```bash
cat /tmp/post-tool-use-errors.log
```

**Common issues**:
- Python syntax error (unlikely - tested working)
- Permission issues (check log directory is writable)
- Missing dependencies (unlikely - uses stdlib only)

## Rollback (If Needed)

If the fix causes issues, you can rollback:

```bash
cd /Users/matifuentes/Workspace/agentlab
git revert dc3dd2a  # The commit hash for the fix
```

Then restart any Claude Code sessions.

## Success Criteria

✅ Hook adds `output_preview` field to TodoWrite entries
✅ Dashboard.js can parse the output_preview
✅ Planning Progress section displays todo list
✅ Progress bars show correct percentages
✅ Task status icons show correctly (✓ ⏳ ○)

---

**Questions or Issues?**

If you encounter problems:
1. Check /tmp/post-tool-use-errors.log for hook errors
2. Check browser console for JavaScript errors
3. Verify hook is executable and recent sessions are being used
4. Create a test session with the script in Option 2 above
