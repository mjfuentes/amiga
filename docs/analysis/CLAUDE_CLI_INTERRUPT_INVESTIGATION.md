# Claude CLI Interrupt Investigation

**Date**: October 27, 2025  
**Objective**: Investigate possibility of adding chat input to tool execution log to interrupt Claude CLI during task execution

## Executive Summary

**Finding**: Claude Code CLI does **NOT** officially support mid-execution interruption or command injection in the current implementation mode (non-interactive `-p` flag).

**Recommendation**: While technically possible with significant architectural changes, the complexity and limitations make this feature **not recommended** for current implementation. Alternative approaches exist that provide better UX with less complexity.

---

## Current Architecture Analysis

### How AMIGA Executes Tasks

1. **Process Spawning** (`claude/code_cli.py:271-279`):
```python
self.process = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.DEVNULL,  # ❌ No stdin pipe
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(self.workspace),
    env=env,
)
```

2. **Non-Interactive Mode**:
   - Uses `claude -p` flag (print mode)
   - Process runs, prints response, then exits
   - No interactive session maintained
   - `stdin=DEVNULL` explicitly blocks input

3. **Termination Mechanism** (`claude/code_cli.py:431-451`):
```python
async def terminate(self):
    if self.process:
        self.process.terminate()  # SIGTERM
        await self.process.wait()
```

### Dashboard Tool Execution Log

**Location**: `templates/dashboard.html` + `static/js/dashboard.js`

**Current Features**:
- Real-time display via Socket.IO (`handleToolExecutionUpdate`)
- Terminal-style UI with auto-scroll
- Read-only display of tool calls
- No input mechanism

**Key Components**:
- Modal: `#taskModal` (lines 145-179 in dashboard.html)
- Tool log container: `#taskToolUsage` rendered by `renderTaskToolUsage()` (dashboard.js:866)
- Terminal body: `#toolTimelineScroll` (dashboard.js:902)

---

## Claude Code CLI Capabilities Research

### Official Documentation Findings

From web search and `CLAUDE.md`:

1. **Non-Interactive Mode** (`-p` flag):
   - Single prompt execution
   - No stdin interaction
   - Process exits after response
   - **No documented interrupt mechanism**

2. **Interactive Mode** (without `-p`):
   - Maintains stdin/stdout session
   - User can type commands interactively
   - **But**: No documented API for programmatic mid-execution commands
   - **Limitation**: Would require full architectural rewrite

3. **Resume Capability** (`--resume`):
   - Can resume a **completed** session
   - Does NOT work for active/running sessions
   - Only useful after process exits

4. **Headless Mode**:
   - Mentioned in docs for automation
   - Still requires process completion before next command
   - No interrupt mechanism documented

### Undocumented/Experimental Approaches

None found. Claude Code CLI is designed for:
- Interactive human use (stdin/stdout)
- Non-interactive automation (single execution)
- NOT mid-execution control

---

## Technical Possibilities Analysis

### Option 1: Switch to Interactive Mode with stdin Pipe

**Implementation**:
```python
# Change in claude/code_cli.py:start()
self.process = await asyncio.create_subprocess_exec(
    *cmd,  # Remove -p flag
    stdin=asyncio.subprocess.PIPE,  # Enable stdin
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(self.workspace),
    env=env,
)

# Add method to send commands
async def send_command(self, command: str):
    if self.process and self.process.stdin:
        self.process.stdin.write(command.encode() + b'\n')
        await self.process.stdin.drain()
```

**Challenges**:
1. ❌ **No Guarantee of Effect**: Claude CLI doesn't document how it handles stdin during execution
2. ❌ **Response Parsing Complexity**: Would need to parse streaming output to detect when response is complete
3. ❌ **Session State Management**: Would need to track conversation state manually
4. ❌ **Concurrent Execution**: Current architecture runs multiple tasks concurrently - interactive mode complicates this
5. ❌ **Output Buffering**: Might miss tool execution events or get them out of order

**Estimated Effort**: 3-5 days of development + extensive testing

**Risk Level**: High (breaking existing functionality, unpredictable behavior)

---

### Option 2: Process Signal-Based Interruption

**Implementation**:
```python
# Send SIGINT (Ctrl+C) to process
self.process.send_signal(signal.SIGINT)
```

**Challenges**:
1. ✅ **Guaranteed Effect**: Process will receive signal
2. ❌ **No Partial Results**: Claude CLI will likely exit without completing response
3. ❌ **No State Preservation**: Cannot resume or get partial work
4. ❌ **Graceful Cleanup Uncertain**: May leave files in inconsistent state

**Estimated Effort**: 1 day for basic implementation

**Risk Level**: Medium (works but destroys task state)

---

### Option 3: External Command Queue (New Architecture)

**Concept**: Create a command queue system that Claude CLI could check between tool calls.

**Implementation**:
```python
# Shared state file or Redis queue
command_queue = {
    'task_id_123': ['pause', 'show current state']
}

# Claude would need to check this between tools
# BUT: Requires modifying Claude CLI itself or using a wrapper
```

**Challenges**:
1. ❌ **Requires Claude CLI Modification**: Not possible without Anthropic support
2. ❌ **Custom Wrapper Complexity**: Would need to intercept and inject between tool calls
3. ❌ **Race Conditions**: Queue polling timing issues

**Estimated Effort**: 1-2 weeks (if even possible)

**Risk Level**: Very High (architectural complexity, no guarantee of success)

---

## Alternative Approaches (Recommended)

### Alternative 1: Enhanced Stop/Pause Functionality ⭐

Instead of sending commands during execution, improve the existing termination mechanism:

**Features**:
1. Graceful Stop Button in UI
   - Add "Stop Task" button to tool execution modal
   - On click: Send SIGTERM to process
   - Display partial results that were captured
   
2. Save Partial State
   - Tool usage hooks already track all tool calls
   - Activity log already records progress
   - Show "Task stopped by user" message with current state

3. Resume/Retry Mechanism
   - Allow user to restart stopped task
   - Show what was completed before stop
   - Provide context for retry

**Implementation**:
```javascript
// In dashboard.js - add to terminal controls
html += `<button class="terminal-btn" onclick="stopTask('${taskId}')">⏹ Stop Task</button>`;

async function stopTask(taskId) {
    const response = await fetch(`/api/tasks/${taskId}/stop`, { method: 'POST' });
    if (response.ok) {
        showToast('Task stop requested', 'info');
    }
}
```

```python
# In monitoring/server.py - add endpoint
@app.route('/api/tasks/<task_id>/stop', methods=['POST'])
async def stop_task(task_id):
    # Find and terminate process
    await claude_pool.terminate_session(task_id)
    await task_manager.update_task(task_id, status='stopped')
    return jsonify({'success': True})
```

**Advantages**:
- ✅ Simple implementation (2-3 hours)
- ✅ Uses existing architecture
- ✅ No risk to stability
- ✅ Provides user control
- ✅ Preserves partial results

**Estimated Effort**: 3-4 hours

**Risk Level**: Low

---

### Alternative 2: Pre-Task Command Input ⭐⭐

Allow users to provide context or instructions **before** task starts:

**Features**:
1. Task Configuration Modal
   - Shows task description
   - Text input: "Additional instructions or constraints"
   - Constraints: "Stop after 5 minutes", "Only modify files in X directory"

2. Pass to Claude as Context
   - Append user instructions to initial prompt
   - Claude follows constraints during execution

**Implementation**:
```javascript
// Show modal before task submission
function showTaskConfigModal(taskDescription) {
    const modal = document.getElementById('taskConfigModal');
    document.getElementById('taskDescriptionPreview').textContent = taskDescription;
    modal.classList.add('active');
}

function submitTaskWithConfig() {
    const additionalInstructions = document.getElementById('taskInstructions').value;
    const taskDescription = baseDescription + '\n\nUser instructions: ' + additionalInstructions;
    // Submit task...
}
```

**Advantages**:
- ✅ Very simple implementation (1-2 hours)
- ✅ No architectural changes
- ✅ Better UX (clarify before starting)
- ✅ No execution interruption needed

**Estimated Effort**: 2 hours

**Risk Level**: Very Low

---

### Alternative 3: Multi-Step Task Approval

Break complex tasks into phases with approval gates:

**Features**:
1. Task Phases
   - Phase 1: Analysis (Claude proposes plan)
   - User reviews and approves/modifies
   - Phase 2: Implementation (Claude executes approved plan)
   - User reviews results
   - Phase 3: Testing/QA

2. Between-Phase Communication
   - User can modify instructions between phases
   - Effectively allows "mid-task" input without interrupting execution

**Implementation**:
- Leverage existing workflow system
- Add approval step after planning phase
- Pause execution, show plan to user, wait for approval

**Advantages**:
- ✅ Natural break points for input
- ✅ No process interruption needed
- ✅ Better quality control
- ✅ Aligns with plan mode workflow

**Estimated Effort**: 1-2 days (workflow modifications)

**Risk Level**: Low-Medium

---

## Recommendations

### Immediate Action (This Week)

**Implement Alternative 1**: Enhanced Stop Functionality
- Low risk, high value
- 3-4 hours of work
- Provides user control without complexity

### Short Term (Next Sprint)

**Implement Alternative 2**: Pre-Task Command Input
- Extremely simple, high UX value
- 2 hours of work
- Prevents need for mid-execution changes

### Long Term (If Still Needed)

**Evaluate Alternative 3**: Multi-Step Task Approval
- More complex but provides comprehensive solution
- Only if user feedback indicates need for mid-task changes
- Consider after gathering usage data

### Do NOT Pursue

**Option 1-3 from Technical Possibilities**:
- High risk, uncertain outcome
- Would destabilize existing system
- No official Claude CLI support
- User needs better served by alternatives

---

## Implementation Plan: Enhanced Stop Functionality

### Phase 1: Backend (1 hour)

1. Add terminate method to ClaudeSessionPool:
```python
# claude/code_cli.py
async def terminate_session(self, task_id: str):
    """Gracefully terminate a running session"""
    if task_id in self.active_sessions:
        session = self.active_sessions[task_id]
        await session.terminate()
        
        # Record stop event
        if self.usage_tracker:
            self.usage_tracker.record_status_change(
                task_id, 
                "stopped", 
                "Task stopped by user"
            )
            await self.usage_tracker.db.update_task(
                task_id, 
                status="stopped"
            )
```

2. Add API endpoint:
```python
# monitoring/server.py
@app.route('/api/tasks/<task_id>/stop', methods=['POST'])
async def stop_task(task_id):
    """Stop a running task"""
    try:
        # Terminate Claude session
        await claude_pool.terminate_session(task_id)
        
        # Emit stop event to frontend
        socketio.emit('task_stopped', {
            'task_id': task_id,
            'message': 'Task stopped by user'
        })
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error stopping task: {e}")
        return jsonify({'error': str(e)}), 500
```

### Phase 2: Frontend (2 hours)

1. Add stop button to terminal controls:
```javascript
// static/js/dashboard.js - in renderTaskToolUsage()
html += `<button class="terminal-btn" id="stopTaskBtn" onclick="stopCurrentTask()">⏹ Stop Task</button>`;
```

2. Implement stop function:
```javascript
async function stopCurrentTask() {
    if (!currentTaskId) return;
    
    if (!confirm('Stop this task? Progress will be saved but task will not complete.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/tasks/${currentTaskId}/stop`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showToast('Task stopped', 'success');
            // Button will be hidden by task_stopped event
        } else {
            showToast('Failed to stop task', 'error');
        }
    } catch (error) {
        console.error('Error stopping task:', error);
        showToast('Error stopping task', 'error');
    }
}
```

3. Handle stop event:
```javascript
socket.on('task_stopped', (data) => {
    if (data.task_id === currentTaskId) {
        // Hide stop button
        const stopBtn = document.getElementById('stopTaskBtn');
        if (stopBtn) stopBtn.style.display = 'none';
        
        // Show stopped message
        appendToolExecutionToModal({
            tool_name: 'System',
            timestamp: new Date().toISOString(),
            success: true,
            output_preview: JSON.stringify({
                message: 'Task stopped by user'
            })
        });
    }
});
```

### Phase 3: Testing (1 hour)

1. Test stop button during active task
2. Verify partial results are preserved
3. Check that process terminates cleanly
4. Validate task status updates correctly
5. Test edge cases (task already completed, invalid task ID)

---

## Conclusion

**Direct Answer**: No, Claude Code CLI does not support mid-execution command injection or interruption as documented or implemented.

**Recommended Solution**: Instead of trying to interrupt Claude during execution, implement:
1. Enhanced stop/pause functionality (immediate)
2. Pre-task instruction input (short term)
3. Multi-phase approval workflow (long term if needed)

These alternatives provide better UX with significantly lower complexity and risk.

**Next Steps**:
1. Review this analysis with stakeholders
2. Get approval for Alternative 1 implementation
3. Create implementation task in tracking system
4. Execute Phase 1-3 of implementation plan
5. Gather user feedback before considering other alternatives

---

## References

- Current implementation: `claude/code_cli.py`
- Dashboard UI: `templates/dashboard.html`, `static/js/dashboard.js`
- Project documentation: `CLAUDE.md`
- Web search: Claude Code CLI documentation (no interrupt feature found)

