# Implementation Examples - Research Worker in Action

Real-world examples of how research_worker and code_worker work together.

## Example 1: Error Handling Improvement

### Scenario
User asks: "Improve the error handling in orchestrator.py"

### Step 1: Orchestrator Routing

```
Input: "Improve the error handling in orchestrator.py"
Detected: "Improve" keyword
Decision: Research request
Action: Spawn research_worker
```

### Step 2: Research Worker Spawning

Orchestrator uses Task tool:

```json
{
  "subagent_type": "research_worker",
  "description": "Analyze and propose error handling improvements",
  "prompt": "Analyze error handling in /Users/matifuentes/Workspace/agentlab/telegram_bot/orchestrator.py

Identify:
- Current error handling patterns
- What's working well
- Edge cases not handled
- Opportunities for improvement

Propose concrete changes with code examples showing:
- Current implementation
- Proposed implementation
- Benefits
- Effort to implement

Format output as Markdown proposal."
}
```

### Step 3: Research Worker Analysis

research_worker executes:

```
1. Read(/path/to/orchestrator.py)
   - Finds exception handling blocks
   - Notes generic Exception catching
   - Observes logging patterns

2. Grep("except Exception", file)
   - Identifies 5 catch blocks
   - Notes missing context in error messages

3. Read(/path/to/main.py)
   - Understands error propagation
   - Sees how errors are displayed

4. Glob(**/*.py, path=/telegram_bot)
   - Discovers other error handling patterns
   - Identifies inconsistencies

5. Generate proposal analyzing:
   - 3 improvement areas
   - Specific code changes needed
   - Effort estimates
   - Implementation priority
```

### Step 4: Proposal Output

research_worker returns Markdown:

```markdown
# Proposal: Improve Error Handling in orchestrator.py

## Summary
Current error handling uses generic Exception catching with minimal logging context. Proposal adds retry logic for transient failures, custom exception types, and structured error logging.

## Current State

### Pattern 1: Generic Exception Catching
```python
# Current code
except Exception as e:
    logger.error(f"Error invoking orchestrator: {e}")
    return None
```

### Pattern 2: Lost Error Context
- No distinction between timeout errors, network errors, parsing errors
- Error messages lack information for debugging
- No mechanism to retry transient failures

## Proposed Changes

### Change 1: Custom Exception Types (Priority: HIGH, Effort: 30 min)

**Problem**: All errors treated the same
**Solution**: Create specific exception hierarchy
**Impact**: Better error handling, easier debugging
**Risk**: Low - backward compatible

Current code:
```python
try:
    stdout, stderr = await asyncio.wait_for(...)
except asyncio.TimeoutError:
    logger.error(f"Orchestrator timeout after {timeout}s")
    return None
except Exception as e:
    logger.error(f"Error invoking orchestrator: {e}")
    return None
```

Proposed code:
```python
class OrchestratorError(Exception):
    """Base exception for orchestrator errors"""
    pass

class AgentSpawningError(OrchestratorError):
    """Raised when agent spawning fails"""
    pass

class AgentTimeoutError(OrchestratorError):
    """Raised when agent exceeds timeout"""
    pass

class AgentCommunicationError(OrchestratorError):
    """Raised for communication/parsing errors"""
    pass

# Updated exception handling:
try:
    stdout, stderr = await asyncio.wait_for(...)
except asyncio.TimeoutError as e:
    logger.error(f"Agent timeout after {timeout}s", extra={"agent": "orchestrator", "timeout": timeout})
    raise AgentTimeoutError(f"Orchestrator timeout after {timeout}s") from e
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse agent output", extra={"error": str(e)[:200]})
    raise AgentCommunicationError("Invalid agent response format") from e
except Exception as e:
    logger.error(f"Unexpected error in orchestrator", extra={"error": str(e)[:200]}, exc_info=True)
    raise OrchestratorError(f"Orchestrator error: {e}") from e
```

### Change 2: Retry Logic for Transient Errors (Priority: HIGH, Effort: 45 min)

**Problem**: Timeouts and network errors fail immediately
**Solution**: Implement exponential backoff retry
**Impact**: Resilience to temporary failures
**Risk**: Medium - adds complexity

Proposed code:
```python
async def invoke_with_retry(
    prompt: str,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> Optional[str]:
    """Invoke orchestrator with automatic retry on transient errors"""

    for attempt in range(max_retries):
        try:
            return await invoke_orchestrator_internal(prompt)
        except AgentTimeoutError as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # exponential backoff
                logger.warning(f"Orchestrator timeout, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
            else:
                raise
        except AgentCommunicationError:
            # Don't retry parsing errors
            raise
```

### Change 3: Structured Error Logging (Priority: MEDIUM, Effort: 20 min)

**Problem**: Error context is flat, hard to correlate
**Solution**: Add structured logging with error codes
**Impact**: Better monitoring and debugging

Proposed code:
```python
# Add context to all error logs
logger.error(
    "Orchestrator error",
    extra={
        "error_code": "ORCH_001",
        "timeout_seconds": timeout,
        "user_query": user_query[:100],
        "workspace": current_workspace,
    },
    exc_info=True
)
```

## Implementation Plan

1. Add custom exception classes (Change 1) - Foundation
2. Update error handlers to use new exceptions (Change 1)
3. Add retry logic wrapper (Change 2)
4. Update all logging to include context (Change 3)
5. Test error scenarios manually
6. Update error handling in main.py to catch specific exceptions
7. Document exception types in README

## Risks & Considerations

- Ensure backward compatibility with existing error handlers
- Document all new exception types
- Test timeout behavior extensively
- Consider timeout values for retry calculation

## Benefits Summary

- 95% of errors will have proper type information
- Transient failures (network, timeout) automatically retry
- Error logs include full debugging context
- Easier to set up monitoring/alerting
- Better error messages to end users
```

### Step 5: Orchestrator Displays Proposal

Bot sends to user (Markdown formatted):

```
Bot: "[Full proposal as formatted Markdown]"
```

### Step 6: User Approval

```
User: "looks good, let's implement it"
```

### Step 7: Orchestrator Recognizes Approval

```
Last user message: "looks good, let's implement it"
Previous context: [proposal displayed]
Detected keywords: "looks good", "implement it"
Conclusion: User approved
Next action: Spawn code_worker
```

### Step 8: Code Worker Implementation

```json
{
  "subagent_type": "code_worker",
  "description": "Implement error handling improvements",
  "prompt": "Implement the following proposal to improve error handling in /Users/matifuentes/Workspace/agentlab/telegram_bot/orchestrator.py

[FULL PROPOSAL TEXT]

Apply these changes:
1. Add custom exception classes to the file
2. Update all exception handling to use new types
3. Add structured logging context
4. Implement retry logic with exponential backoff

Commit with message: 'Improve error handling: add exception types, retry logic, structured logging'"
}
```

### Step 9: Code Worker Execution

```
1. Read orchestrator.py
2. Identify all exception handling blocks
3. Edit 1: Add exception classes at top
4. Edit 2: Update each try-except block
5. Edit 3: Add retry logic function
6. Test imports work
7. Commit with descriptive message
8. Return summary
```

### Step 10: Result to User

```
Bot: "Done. Improved error handling with custom exception types, automatic retry for transient failures, and structured logging. Error handling now provides better debugging context and resilience."
```

### Step 11: Git Commit

```
$ git log --oneline -1
a1b2c3d Improve error handling: add exception types, retry logic, structured logging
```

---

## Example 2: Security Review & Hardening

### Scenario
User asks: "Review security in the authentication code and propose hardening"

### Flow

```
User Input:
"Review security and suggest improvements for auth.py"
         ↓
Orchestrator:
- Detects "review security", "suggest"
- Spawns research_worker
         ↓
Research Worker:
- Reads auth.py
- Grep for password handling, token storage
- Searches for SQL injection patterns
- Looks for input validation
- Checks error messages for info leakage
- Generates security proposal
         ↓
Proposal Displayed:
- XSS vulnerabilities in user input
- Missing CORS headers
- Weak session validation
- Plaintext password in logs (found by grep)
- Missing rate limiting
         ↓
User Reviews:
"good, but let's do rate limiting separately"
         ↓
Orchestrator:
- Recognizes feedback/refinement
- Could respawn research_worker
- Or proceed with current proposal
         ↓
User:
"let's go with the current proposal"
         ↓
Code Worker:
- Implements security hardening
- Adds input validation
- Fixes CORS headers
- Updates session validation
- Removes password from logs
         ↓
Result:
- Secure auth.py committed
- Changes reviewed before implementation
- All security issues addressed
```

---

## Example 3: Performance Optimization

### Scenario
User asks: "Make the API faster - propose optimizations"

### Research Worker Analysis

```
Research worker finds:
1. Database queries not indexed
   - Proposal: Add query indices
   - Impact: 10x query speed

2. N+1 query problem in list endpoint
   - Proposal: Batch load related data
   - Impact: 100x faster for large datasets

3. Missing response caching
   - Proposal: Add Redis caching layer
   - Impact: 1000x faster for repeated queries

4. No connection pooling
   - Proposal: Use connection pool
   - Impact: Reduced connection overhead
```

### Proposal Output

```markdown
# Proposal: Optimize API Performance

## Priority Order
1. Add database indices (easiest, 10x improvement)
2. Fix N+1 queries (medium, 100x improvement)
3. Add caching layer (complex, 1000x improvement)

## Change 1: Database Indices
...
```

### User Decision

```
User: "approve the indices, but skip caching for now"

Orchestrator:
- Recognizes partial approval
- Could implement just indices
- Or respawn research_worker
- Or ask for clarification
```

---

## Example 4: Refactoring Proposal (Rejected Then Refined)

### First Attempt

```
User: "refactor the session management code"
Bot: [Displays major refactoring proposal]
User: "too ambitious, make it smaller"
```

### Refinement

```
Orchestrator:
- Notes rejection/refinement feedback
- Could respawn research_worker with:
  "Propose SMALLER refactoring, focus on just [specific area]"

Research Worker:
- Generates focused proposal
- Only key improvements
- Lower effort

User: "approve"
Code Worker: Implements refined proposal
```

---

## Key Patterns

### Pattern 1: Research → Approve → Implement
Most common flow. User trusts orchestrator, review is quick.

### Pattern 2: Research → Refine → Research → Approve → Implement
Thoughtful users who want to scope changes carefully.

### Pattern 3: Research → Reject
User decides changes aren't needed. Move on.

### Pattern 4: Research → Questions → Clarify → Approve → Implement
User wants to understand changes before approval.

---

## Integration with Telegram

### Proposal Display in Chat

Option 1: Code block (simple)
```
Bot sends proposal as:
```
proposal:
[markdown text]
```
```

Option 2: Document (better for long proposals)
```
Bot: [First part of proposal]
[Buttons: More ↓]
User: [clicks More]
Bot: [Rest of proposal]
```

Option 3: Approval Buttons (best UX)
```
Bot: [Proposal text]
[Approve] [Refine] [Reject]
User: [clicks Approve]
```

### Approval via Buttons

```python
# In main.py, add button handling:
if query.data == "approve_proposal":
    # Extract proposal from session
    # Respond with approval message
    # Orchestrator will spawn code_worker
```

---

## Testing These Workflows

### Test 1: Full Research Flow

```bash
# Send to bot: "improve the error handling"
# Expected:
# 1. Bot displays markdown proposal (wait ~10 seconds)
# 2. Proposal contains code examples
# 3. Proposal includes effort estimates
# 4. User can approve/reject
```

### Test 2: Approval Triggers Implementation

```bash
# After proposal:
# Send: "looks good"
# Expected:
# 1. Code worker spawns (wait ~20 seconds)
# 2. Files are modified
# 3. Git shows new commit
# 4. Bot sends implementation summary
```

### Test 3: Rejection Prevents Implementation

```bash
# After proposal:
# Send: "no thanks"
# Expected:
# 1. No code worker spawns
# 2. No files modified
# 3. Bot acknowledges rejection
```

### Test 4: Refinement Loop

```bash
# After proposal:
# Send: "good but skip part 2"
# Expected:
# 1. Orchestrator recognizes refinement
# 2. Could respawn research_worker
# 3. User gets updated proposal
# 4. Can then approve refined version
```

---

## Common Issues in Testing

**Issue**: research_worker not spawning
- Check: Does prompt contain research keywords?
- Fix: "improve", "refactor", "propose" are keywords

**Issue**: Proposal not formatted well in Telegram
- Check: Markdown rendering
- Fix: Use code blocks or split message

**Issue**: User approval not detected
- Check: Approval keywords in message
- Fix: "looks good", "approve", "do it" are keywords

**Issue**: code_worker not implementing
- Check: Was approval recognized?
- Fix: Ensure previous message is in history

---

## Production Readiness Checklist

- [ ] research_worker generates valid Markdown
- [ ] Proposal contains code examples
- [ ] Effort estimates are reasonable
- [ ] Approval keywords recognized consistently
- [ ] code_worker receives full proposal context
- [ ] Commits have descriptive messages
- [ ] Error handling in both agents
- [ ] Timeout handling for slow analysis
- [ ] Conversation history preserved
- [ ] Proposal state survives bot restart (if needed)
