# Research Worker Workflow Guide

This document explains how the new research_worker agent enables proposal-based improvements with user approval before implementation.

## Overview

The system now supports a two-phase workflow for code improvements:

```
User Request (improvement/refactor)
    ↓
Research Worker analyzes & proposes (MD document)
    ↓
Orchestrator displays proposal
    ↓
User reviews & approves/rejects
    ↓
Code Worker implements (if approved)
    ↓
Changes committed to repository
```

## When to Use Research Worker

The orchestrator automatically spawns research_worker when users request:

- **Architecture improvements**: "better architecture", "improve structure"
- **Refactoring proposals**: "refactor the auth system", "improve code organization"
- **Performance optimization**: "optimize performance", "improve speed"
- **Security reviews**: "review security", "improve security"
- **Quality improvements**: "better error handling", "improve logging", "better testing"
- **Code analysis**: "analyze patterns", "propose improvements", "suggest changes"

**Keywords that trigger research requests**:
- "improve", "better", "refactor", "optimize", "review", "suggest", "propose", "analyze", "enhance", "strengthen", "architecture", "design"

## The Complete Workflow with Example

### Example: "Improve the error handling"

#### Step 1: User Request

```
User: "improve the error handling in orchestrator.py"
```

#### Step 2: Orchestrator Recognition

Orchestrator detects this is a research request (contains "improve"):

```
Orchestrator decision:
- Keyword: "improve"
- Type: Research request
- Action: Spawn research_worker with Task tool
```

#### Step 3: Research Worker Analysis

Orchestrator spawns research_worker:

```python
Task(
  subagent_type="research_worker",
  description="Analyze and propose error handling improvements for orchestrator.py",
  prompt="""Analyze the error handling in /path/to/orchestrator.py.

  Identify:
  - Current error handling patterns
  - Edge cases not handled
  - Opportunities for improvement
  - Industry best practices that apply

  Propose concrete changes with code examples.
  Format as Markdown proposal document."""
)
```

research_worker:
1. Reads orchestrator.py to understand current error handling
2. Uses Grep to find all try-except blocks
3. Analyzes patterns and identifies gaps
4. Reviews related files (main.py, session.py)
5. Generates Markdown proposal with recommendations

#### Step 4: Proposal Document

research_worker returns a Markdown proposal like:

```markdown
# Proposal: Improve Error Handling in orchestrator.py

## Summary
Current error handling catches broad exceptions. Proposal adds retry logic, custom exception types, and structured logging for better debugging and resilience.

## Current State
- Generic Exception catching
- Limited logging context
- No retry mechanism for transient failures
- No distinction between recoverable/non-recoverable errors

## Proposed Changes

### Change 1: Custom Exception Hierarchy
Problem: All errors caught as generic Exception
Solution: Create specific exception types
Impact: Better error classification and handling
Effort: ~30 minutes

Current code:
```python
except Exception as e:
    logger.error(f"Error: {e}")
```

Proposed code:
```python
class OrchestratorError(Exception):
    pass

class AgentSpawningError(OrchestratorError):
    pass

class TimeoutError(OrchestratorError):
    pass
```

### Change 2: Add Retry Logic
[... more specific proposals ...]

## Implementation Plan
1. Add custom exceptions (Change 1)
2. Update error handling blocks (Change 2)
3. Add logging context (Change 3)
4. Test error scenarios

## Risks & Considerations
- Ensure backward compatibility
- Document new exception types
- Update error handling in main.py

## Benefits Summary
- 95% of errors will now be properly typed
- Logging includes full context for debugging
- Transient failures (like timeouts) automatically retry
- Better error reporting to users
```

#### Step 5: Orchestrator Displays Proposal

Bot sends proposal to user in chat (as Markdown):

```
Bot: [displays full proposal as formatted Markdown]
```

#### Step 6: User Reviews & Approves

User can respond with:
- Approval: "looks good", "approve", "do it", "yes", "implement"
- Rejection: "no thanks", "skip this", "not needed"
- Refinement: "looks good but skip Change 1", "good but smaller scope"

```
User: "looks good, let's do it"
```

#### Step 7: Orchestrator Recognizes Approval

Orchestrator analyzes conversation history:

```
Orchestrator decision:
- Last message: "looks good, let's do it"
- Previous message: [proposal displayed]
- Conclusion: User approved
- Action: Spawn code_worker with proposal context
```

#### Step 8: Code Worker Implements

Orchestrator spawns code_worker:

```python
Task(
  subagent_type="code_worker",
  description="Implement error handling improvements for orchestrator.py",
  prompt="""Implement the following proposal for error handling improvements:

[Full proposal text pasted here]

Apply all recommended changes to /path/to/orchestrator.py:
1. Add custom exception classes
2. Update error handling with retry logic
3. Enhance logging with context
4. Test error scenarios

Commit with descriptive message."""
)
```

code_worker:
1. Reads orchestrator.py
2. Implements changes from proposal
3. Tests the changes
4. Commits with message: "Improve error handling: add custom exceptions, retry logic, structured logging"

#### Step 9: Result

Bot sends implementation result:

```
Bot: "Done. Added custom error types, retry logic for transient failures, and structured logging to all error handlers. Error handling now provides much better debugging context."
```

## Handling Rejections and Refinements

### Case 1: User Rejects Proposal

```
User: "improve the error handling"
[Orchestrator displays proposal]
User: "no, too much"
```

Orchestrator response:
- Acknowledges rejection
- Can offer to narrow scope
- Can ask for specific feedback
- Can spawn new research_worker with refined parameters

### Case 2: User Requests Refinement

```
User: "improve the error handling"
[Orchestrator displays proposal]
User: "looks good but skip the retry logic part"
```

Orchestrator can:
1. Acknowledge feedback
2. Respawn research_worker with refined scope: "...skip retry logic proposals"
3. Display refined proposal
4. Await new approval

## Architecture

### Three Agents, Clear Roles

**Orchestrator**:
- Routes user requests
- Detects research requests
- Spawns appropriate agents
- Tracks proposal state in conversation history
- Displays results to user

**Research Worker**:
- Analyzes code with Read/Glob/Grep
- Generates Markdown proposals
- Does NOT implement changes
- Does NOT modify files
- Returns proposal document only

**Code Worker**:
- Implements proposals from research
- Also handles direct coding tasks
- Has full read/write/git access
- Always commits changes
- Returns implementation summary

### Proposal Flow

```
┌─────────────────────────────────┐
│   User Request                  │
│   "improve error handling"      │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│   Orchestrator                  │
│   - Detects "improve" keyword   │
│   - Spawns research_worker      │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│   Research Worker               │
│   - Analyzes codebase           │
│   - Generates MD proposal       │
│   - Returns to orchestrator     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│   Orchestrator                  │
│   - Displays proposal in chat   │
│   - Sets proposal_pending state │
│   - Waits for user response     │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│   User Reviews                  │
│   - Reads proposal              │
│   - Sends approval/feedback     │
└──────────────┬──────────────────┘
               │
      ┌────────┴────────┐
      │                 │
      ▼                 ▼
  APPROVED          REJECTED/REFINED
      │                 │
      ▼                 ▼
Spawn code_worker  Discuss refinement
      │                 │
      ▼                 ▼
Implement changes  Loop or abandon
      │
      ▼
Commit & notify user
```

## Comparison: Old vs. New Workflow

### Old (No Research Phase)

```
User: "improve error handling"
↓
Bot: "OK, let me refactor error handling"
↓
Makes changes immediately
↓
User discovers they didn't like the direction
✗ Changes already committed
```

### New (With Research Phase)

```
User: "improve error handling"
↓
Orchestrator: Spawns research_worker
↓
Bot: Displays proposal for review
↓
User: Reviews and approves/rejects
↓
(If approved) Code worker implements
↓
User gets desired changes
✓ Changes aligned with user expectations
```

## Implementation Technical Details

### How Orchestrator Tracks Proposals

The orchestrator maintains state in conversation history:

1. **Before research**: No pending proposal
2. **After research displays**: Implicit `proposal_pending` (last bot message contains proposal)
3. **User responds**: Orchestrator analyzes response for approval keywords
4. **If approved**: Extracts proposal from history, passes to code_worker
5. **After implementation**: Proposal state cleared

**Approval Keywords Detected**:
- "approve", "approved"
- "looks good", "good"
- "do it", "do it!", "go"
- "yes", "yep", "yeah"
- "implement", "go ahead"
- "let's" (in context of implementation)

### Integration with Existing Code

**In orchestrator.py**:
- No changes needed yet - infrastructure supports proposals
- When research_worker returns proposal, orchestrator displays it
- Conversation history naturally tracks proposal state

**In orchestrator.md (Claude agent)**:
- New routing logic detects research requests
- Spawns research_worker for applicable queries
- Recognizes approval keywords in next message
- Spawns code_worker with proposal context if approved

## Testing the Workflow

### Test Case 1: Basic Research Request

```
1. Send: "improve the error handling"
2. Expected: Bot displays Markdown proposal
3. Verify: Proposal contains code examples and effort estimates
```

### Test Case 2: Approval Flow

```
1. Send: "improve the error handling"
2. Bot: [displays proposal]
3. Send: "looks good"
4. Expected: Bot spawns code_worker and shows implementation summary
5. Verify: Git log shows new commit with changes
```

### Test Case 3: Rejection Flow

```
1. Send: "improve the error handling"
2. Bot: [displays proposal]
3. Send: "too much"
4. Expected: Bot acknowledges and offers refinement
5. Verify: No implementation occurs
```

### Test Case 4: Refinement Flow

```
1. Send: "improve the error handling"
2. Bot: [displays proposal]
3. Send: "looks good but skip the retry logic"
4. Expected: Bot refines scope and respawns research_worker
5. Send: "approve"
6. Expected: Bot spawns code_worker with refined proposal
```

## Benefits Summary

1. **User Control**: Review before implementing
2. **Transparency**: See what changes are proposed
3. **Flexibility**: Refine proposals before implementation
4. **Quality**: Prevents unwanted architectural changes
5. **Learning**: Users understand what was changed and why
6. **Safety**: No accidental refactoring
7. **Alignment**: Changes match user intent exactly

## Future Enhancements

- Telegram buttons for "Approve" / "Reject" / "Refine"
- Visual diff showing proposed changes
- Persist proposals in task database
- Multi-stakeholder approval workflows
- Proposal version history
- Rollback support for implemented proposals
