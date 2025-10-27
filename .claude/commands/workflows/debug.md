---
model: claude-sonnet-4-5-20250929
---

Debug task issues using comprehensive inspection and automatic fix routing:

[Extended thinking: This workflow orchestrates task debugging by using debug-agent to perform comprehensive inspection, then intelligently routing to code-task workflow if fixes are needed. The debug-agent provides detailed diagnostics including git state, tool usage, session logs, and process status. If issues require code changes, the workflow passes full context to code-task for resolution.]

## Debug Protocol

### Step 1: Task Inspection

Use debug-agent to perform comprehensive task inspection:

- Use Task tool with subagent_type="debug-agent"
- Prompt: "Inspect and debug task: $ARGUMENTS

  Perform full diagnostic inspection:
  1. Task status and metadata (SQLite database)
  2. Git worktree state (uncommitted changes, branch status)
  3. Tool usage logs (failures, patterns, last activity)
  4. Session logs (errors, blocked operations)
  5. Process status (if running - PID, CPU, memory)

  Auto-fix common issues:
  - Uncommitted changes (auto-commit)
  - Hung tasks (mark as stopped, cleanup)
  - Orphaned worktrees (cleanup after safety checks)
  - Failed operations with transient errors (retry)

  Output detailed debug report with:
  - Status summary (✅/⚠️/❌ for each check)
  - Issues detected (severity: Critical/High/Medium/Low)
  - Auto-fixes applied
  - Remaining issues requiring manual intervention
  - Command outputs for diagnosis

  Be thorough and accurate with all commands."

### Step 2: Parse Debug Report

**Extract key information from debug report:**

a) **Task Status**:
   - Current state (pending/running/completed/failed/stopped)
   - Last update timestamp
   - Workspace path
   - Session UUID
   - Error message (if any)

b) **Issues Found**:
   - Parse report sections: "Issues Detected", "Remaining Issues"
   - Categorize by severity (Critical/High/Medium/Low)
   - Identify auto-fixed vs. unfixed issues

c) **Git State**:
   - Check for uncommitted changes status
   - Verify branch state
   - Check for merge conflicts

d) **Error Patterns**:
   - Repeated tool failures
   - Error categories
   - Last error timestamp

### Step 3: Determine Action

**Decision tree based on debug report findings:**

#### Scenario A: Auto-Fixed and Complete
- **Condition**: All issues auto-fixed, no remaining problems
- **Action**: Report success, no further action needed
- **Output**: "Debug complete. All issues auto-fixed: [list fixes]"

#### Scenario B: Code Issues Detected
- **Condition**: Errors in implementation, failed tests, logic bugs
- **Trigger patterns**:
  - Tool failures with code-related errors (syntax, import, type errors)
  - Test failures
  - Implementation incomplete or broken
  - Logic errors causing unexpected behavior
- **Action**: Route to code-task workflow with full context

#### Scenario C: Infrastructure/Configuration Issues
- **Condition**: Environment issues, missing dependencies, permission errors
- **Trigger patterns**:
  - File not found errors
  - Permission denied
  - Missing environment variables
  - Service connectivity issues
- **Action**: Route to smart-fix workflow

#### Scenario D: Manual Investigation Required
- **Condition**: Complex issues requiring human analysis
- **Trigger patterns**:
  - Inconsistent errors with no clear pattern
  - External service failures
  - Data corruption
  - Unknown error categories
- **Action**: Report findings and request user guidance

### Step 4: Route to Fix Workflow (if needed)

#### For Code Issues (Scenario B):

**Build context package for code-task:**

```
Task ID: [task_id]
Original Description: [from database]
Current Status: [status]
Workspace: [workspace_path]
Session UUID: [session_uuid]

DEBUG FINDINGS:
==============

Git State:
- Branch: [branch_name]
- Uncommitted changes: [Yes/No + file list]
- Status: [git status output]

Tool Failures:
[List of failed tool executions with errors]

Error Patterns:
[Error categories and frequencies]

Session Errors:
[Relevant errors from session logs]

REQUIRED FIXES:
===============

Critical Issues:
1. [Issue 1 with file:line reference]
2. [Issue 2 with file:line reference]

High Priority Issues:
1. [Issue 1 with details]
2. [Issue 2 with details]

CONTEXT FROM DEBUG:
===================

Last successful operation: [tool_name at timestamp]
Last failed operation: [tool_name with error]
Implementation files: [list from git status]
Test files affected: [if test failures detected]

INSTRUCTIONS FOR CODE-TASK:
===========================

This is a DEBUG-INITIATED FIX for task {task_id}.

CRITICAL: You are resuming work on an existing task.
- Workspace: {workspace_path}
- Branch: {branch_name}
- Files already modified: [list]

Your mission:
1. Analyze the DEBUG FINDINGS above
2. Address REQUIRED FIXES in priority order
3. Verify fixes resolve original errors
4. Commit fixes with reference to debug session
5. DO NOT create new worktree (already exists)
6. DO NOT start from scratch (modify existing implementation)

Begin implementation at Step 1 (skip worktree creation).
```

**Invoke code-task workflow:**

- Use SlashCommand tool
- Command: "/code-task [context package from above]"
- Wait for completion
- Aggregate results

#### For Infrastructure Issues (Scenario C):

**Invoke smart-fix workflow:**

- Use SlashCommand tool
- Command: "/smart-fix [infrastructure issue description from debug report]"
- Include: Environment details, error logs, configuration state
- Wait for completion

### Step 5: Verification After Fix

If fix workflow was invoked, verify resolution:

- Use Task tool with subagent_type="debug-agent"
- Prompt: "Re-inspect task {task_id} to verify fixes resolved issues.

  Quick verification (not full inspection):
  1. Check task status changed (failed → completed)
  2. Verify git state clean (no uncommitted changes)
  3. Check tool usage logs (no new failures)
  4. Confirm fix commit exists

  Report: Issue resolution confirmed ✅ or New issues detected ⚠️"

## Output Format

### Initial Debug Report

Present debug-agent findings clearly:

```markdown
# Debug Report: Task {task_id}

## Task Status
- State: [status]
- Created: [timestamp]
- Updated: [timestamp]
- Workspace: [path]
- Error: [if any]

## Inspection Results

**Git State**: [✅ Clean | ⚠️ Issues | ❌ Critical]
**Tool Usage**: [✅ Healthy | ⚠️ Failures | ❌ Broken]
**Process**: [✅ Running | ⚠️ Hung | ❌ Dead]
**Logs**: [✅ Clean | ⚠️ Errors detected]

## Issues Detected

### [Severity]: [Issue Type]
- **Details**: [Specific findings]
- **Impact**: [What this breaks]
- **Auto-fix**: [✅ Applied | ❌ Failed | N/A Manual]

## Action Taken

[Scenario A/B/C/D]

[If routing to fix workflow:]
Routing to [code-task/smart-fix] with context:
- [Context summary]

[If complete:]
All issues resolved. No further action needed.

[If manual investigation needed:]
Complex issues detected requiring human analysis:
- [Issue details]
- [Recommended investigation steps]
```

### Post-Fix Verification Report

```markdown
# Verification: Task {task_id}

## Fix Applied
- Workflow: [code-task/smart-fix]
- Commits: [commit hashes]
- Files modified: [list]

## Verification Results

**Status Change**: [old_status] → [new_status]
**Git State**: [clean/dirty]
**New Errors**: [None/List]

## Resolution Status
✅ Issues fully resolved
⚠️ Partial resolution - [remaining issues]
❌ Fix failed - [new issues]
```

## Execution Notes

- **Always start with debug-agent** - comprehensive inspection before fixes
- **Parse reports carefully** - extract task_id, status, errors, patterns
- **Include full context** when routing to fix workflows
- **Skip worktree creation** when routing to code-task (worktree already exists)
- **Verify fixes** - re-inspect after fix workflow completes
- **Handle edge cases**:
  - Task doesn't exist → Report error, don't attempt fixes
  - Multiple tasks → Process each separately, aggregate reports
  - Database locked → Retry with backoff, report if persistent
- **Preserve debug artifacts** - worktrees, logs, commits for analysis

## Special Cases

### Multiple Task IDs

If multiple task IDs provided:

1. Inspect all tasks in parallel (single message, multiple Task calls)
2. Aggregate findings by issue type
3. Group tasks with similar issues
4. Route to fix workflows in batches if patterns detected
5. Report per-task and aggregate summaries

### Task Already Completed

If task status is "completed":

1. Still run inspection (may have uncommitted changes)
2. Verify git state clean
3. Check for orphaned artifacts
4. Report: "Task completed but [issues found]" or "Task completed and clean"

### Task Never Started

If task status is "pending":

1. Check why not started (worker availability, dependencies)
2. Verify task metadata valid
3. Report: "Task pending - [reason]"
4. Offer to trigger task execution if appropriate

Task to debug: $ARGUMENTS
