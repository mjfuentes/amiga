---
model: claude-sonnet-4-5-20250929
---

Implement coding task by analyzing requirements and routing to specialized agents:

[Extended thinking: This workflow directly orchestrates coding tasks. First analyzes complexity to determine if task decomposition is needed. Complex multi-component tasks get decomposed into parallelizable subtasks with optimized context. Simple tasks follow linear execution. This workflow IS the orchestrator using Sonnet 4.5.]

## Task Analysis & Decomposition

Analyze the task description to determine:
- **Domain**: Backend (Python), Frontend (HTML/CSS/JS), or Multi-domain
- **Complexity**: Simple (1-4 subtasks) vs Complex (5+ subtasks)
- **Scope**: Files affected, components to modify
- **Decomposability**: Can work be parallelized?

### Complexity Decision:

**COMPLEX TASKS** (use decomposition):
- "Build a [system/feature/application]"
- Multi-domain tasks (backend + frontend + infrastructure)
- Tasks with 5+ distinct subtasks
- Tasks with obvious parallel work streams
- Example: "Build authentication system", "Create admin dashboard", "Implement payment flow"

**SIMPLE TASKS** (skip decomposition):
- Single file modifications
- Bug fixes
- Simple feature additions (1-3 files)
- Refactoring within one module
- Example: "Fix error in message_queue.py", "Add logging to API endpoint"

### If COMPLEX: Decompose First

1. **Use Task Decomposer**
   - Use Task tool with subagent_type="task-decomposer"
   - Prompt: "Break down '$ARGUMENTS' into parallelizable subtasks with minimal context. Output task graph showing dependencies, suggested agents, and execution layers."

2. **Execute Task Graph**
   - Parse decomposition output
   - Execute tasks layer by layer (tasks in same layer run in parallel via multiple Task calls in single message)
   - Pass results from completed tasks to dependent tasks
   - Track progress and aggregate results

### If SIMPLE: Direct Execution

Based on analysis, invoke appropriate agents sequentially. **CRITICAL: Always end with merge step (N-1) then cleanup step (N).**

## Development Steps

0. **Create Worktree** (ONLY if TASK_ID is set)
   - **Check**: Only run if $TASK_ID environment variable is present
   - **Skip**: If TASK_ID not set, skip worktree creation (running in interactive/API mode)
   - Use Task tool with subagent_type="git-worktree"
   - Prompt: "create-worktree for task $TASK_ID"
   - **CRITICAL**: When running with TASK_ID, must run BEFORE any implementation steps
   - **Purpose**: Creates isolated git worktree to prevent concurrent task conflicts
   - **Note**: $TASK_ID environment variable is automatically set by ClaudeSessionPool
   - **Output**: Parse WORKTREE_CREATED message for worktree path
   - **On failure**: Abort workflow - cannot proceed without isolation

1. **Intent Analysis & Context Discovery** (CRITICAL - run BEFORE implementation)

   **Purpose**: Detect if user is referring to existing code and find it before delegating.

   **Trigger Keywords** (modify intent):
   - update, fix, improve, change, modify, enhance, refactor, adjust, correct
   - "the [feature]" (definite article indicates existing feature)

   **Process**:

   a) **Extract Features Mentioned**:
      - Parse $ARGUMENTS for component names (dashboard, authentication, message_queue, etc.)
      - Parse for file references (dashboard.html, main.py, etc.)

   b) **Search Existing Code**:
      - Use Grep to search for feature keywords across codebase
      - Use Glob to find files matching mentioned names
      - Record file paths and line ranges where features are implemented

   c) **Build Context for Agents**:
      - If existing code found → Add to agent prompt:
        "EXISTING IMPLEMENTATION: The user is referring to existing code at [file:lines].
         MODIFY this implementation, DO NOT create new sections."
      - If no code found → Proceed as creation task

   **Example**:

   User says: "update the dashboard filtering"

   Process:
   1. Detect "update" → modify intent
   2. Extract "dashboard filtering" → search for it
   3. Grep "filtering" in templates/dashboard.html → Found at lines 38-63
   4. Grep "filtering" in static/js/dashboard.js → Found at lines 105-142
   5. Pass context to frontend_agent:
      "EXISTING IMPLEMENTATION: Dashboard filtering UI exists at:
       - templates/dashboard.html:38-63 (HTML form)
       - static/js/dashboard.js:105-142 (JS handlers)
       MODIFY these sections, DO NOT add new filtering UI."

   **Skip this step if**:
   - Task is obviously creation (add, build, create, implement NEW)
   - User explicitly says "new" or "create"
   - No feature names mentioned in task

2. **Backend Implementation** (if task involves Python/backend)
   - Use Task tool with subagent_type="code_agent"
   - Prompt: "$ARGUMENTS

EXISTING CODE CONTEXT (from Step 1):
[Include search results here if modify intent detected]

IMPLEMENTATION INSTRUCTIONS:
- CRITICAL: Review 'CONTEXT FROM ROUTING' section above for user's original request and conversation context
- CRITICAL: If EXISTING CODE CONTEXT provided, MODIFY existing code, DO NOT create new sections
- IMPORTANT: You are working in git worktree /tmp/agentlab-worktrees/{task_id}
- Branch: task/{task_id}
- Commit to this branch, git-merge agent will merge to main later
- Follow AgentLab Python conventions (Black, isort, type hints)
- Add error handling and logging
- Include docstrings
- CRITICAL: Commit changes with descriptive message"

3. **Frontend Implementation** (if task involves HTML/CSS/JS)
   - Use Task tool with subagent_type="frontend_agent"
   - Prompt: "$ARGUMENTS

EXISTING CODE CONTEXT (from Step 1):
[Include search results here if modify intent detected]

IMPLEMENTATION INSTRUCTIONS:
- CRITICAL: Review 'CONTEXT FROM ROUTING' section above for user's original request and conversation context
- CRITICAL: If EXISTING CODE CONTEXT provided, MODIFY existing code, DO NOT create new sections
- IMPORTANT: You are working in git worktree /tmp/agentlab-worktrees/{task_id}
- Branch: task/{task_id}
- Commit to this branch, git-merge agent will merge to main later
- Use responsive design and accessibility best practices
- CRITICAL: Commit changes with descriptive message"

4. **Research & Architecture** (ONLY for complex/architectural decisions - uses expensive Opus)
   - Use Task tool with subagent_type="research_agent"
   - Prompt: "Research and propose solutions for: $ARGUMENTS. Compare approaches with pros/cons. Provide implementation recommendations and code examples. Consider cost, performance, maintainability."
   - **When to use**: New framework selection, architecture decisions, security analysis
   - **Skip for**: Standard feature implementation, bug fixes, simple changes

5. **Quality Assurance** (for non-trivial tasks)

   **Functional Validation Loop**

   **CRITICAL: DO NOT MERGE until validation APPROVED. Fix issues IN THE WORKTREE before merging.**

   - Use Task tool with subagent_type="task-completion-validator"
   - Prompt: "Verify implementation of '$ARGUMENTS' actually works and meets requirements."
   - **Parse result** for VALIDATION STATUS:

   **IF REJECTED:**
   1. **DO NOT PROCEED TO MERGE** - validation must pass first
   2. Extract CRITICAL ISSUES and MISSING COMPONENTS from validator output
   3. Invoke appropriate agent to fix issues **in the worktree**:
      - For code issues → code_agent or frontend_agent
      - For missing tests → code_agent with test writing prompt
      - For deployment issues → frontend_agent with deploy prompt
   4. After fixes committed, **re-run validation** (step 5 again)
   5. Maximum 2 retry cycles total
   6. If still REJECTED after 2 retries → **ABORT MERGE**, report to user with blocker details

   **IF APPROVED:**
   - Proceed to merge step (N-1)

   **QA Result Pattern Matching:**
   ```
   Validation patterns:
   - APPROVED: /VALIDATION STATUS.*APPROVED/i
   - REJECTED: /VALIDATION STATUS.*REJECTED/i
   - Critical issues: /CRITICAL ISSUES.*Critical|High/i
   ```

   **Example Retry Flow:**
   ```
   Cycle 1: Validate → REJECTED (missing tests)
           → code_agent: "Write tests for auth feature"
           → Validate → APPROVED
           → Proceed to merge

   Cycle 2: Validate → REJECTED (deployment missing)
           → frontend_agent: "Run ./deploy.sh chat"
           → Validate → REJECTED (tests still missing)
           → ABORT - Report to user: "Cannot approve without tests"
   ```

### FINAL STEP (N-1): Merge to Main

**ONLY run if TASK_ID is set AND validation APPROVED - this is a QUALITY GATE**

- **CHECK**: Only run if $TASK_ID environment variable is present (worktree was created)
- **SKIP**: If TASK_ID not set, skip merge (working directly on main branch)
- **PREREQUISITE**: Validation status must be APPROVED
- Use Task tool with subagent_type="git-merge"
- Prompt: "Merge task branch to main"
- **CRITICAL**: Must run AFTER all implementation and QA steps complete AND approved
- **CRITICAL**: Ensures work isn't lost when worktrees are cleaned up
- **APPLIES TO**: Both simple tasks (after implementation) AND complex tasks (after all QA steps)
- **IF VALIDATION REJECTED**: DO NOT RUN THIS STEP - fix issues first

### LAST STEP (N): Cleanup Worktree

**DISABLED - Worktrees are preserved for debugging and manual inspection**

- Automatic worktree cleanup has been disabled to preserve task isolation
- Worktrees remain in `/tmp/agentlab-worktrees/{task_id}` after completion
- Manual cleanup available if needed via git-worktree agent
- **Rationale**: Preserving worktrees allows post-task analysis and debugging
- **Note**: Worktrees in /tmp/ are cleared on system restart automatically

**If manual cleanup needed**:
- Use Task tool with subagent_type="git-worktree"
- Prompt: "cleanup-worktree for task {task_id}"
- Only use when explicitly requested by user

## Execution Notes

- **You ARE the orchestrator** - analyze task and invoke appropriate agents directly
- **Create worktree if TASK_ID set** - check for $TASK_ID env var before invoking git-worktree agent
- **Skip worktree for interactive mode** - if TASK_ID not set, work directly on main branch
- **Decompose complex tasks** - use task-decomposer for 5+ subtasks
- **Parallel execution** - tasks in same layer run in parallel (multiple Task calls in single message)
- **Skip research_agent** for straightforward implementations (uses Opus - expensive)
- **Skip QA agents** for trivial changes (typo fixes, comments, minor tweaks)
- **Always commit** after implementation - agents must create descriptive commits
- **Merge if TASK_ID set** - invoke git-merge agent as final step only when worktree was created
- **Worktree cleanup disabled** - worktrees are preserved for debugging (manual cleanup available if needed)
- **Invoke sequentially** for simple tasks - wait for each to complete before starting next
- **Invoke in parallel** for decomposed tasks - send all layer tasks in single message
- **Parse QA results** - extract validation status using patterns
- **Retry on failure** - if validation REJECTED, fix issues and re-validate (max 2 retries)
- **Aggregate results** from all agents and present unified summary

## Parallel Execution Example

**Task**: "Build authentication system"

**Decomposition Output**:
```yaml
Layer 1: [auth-research]
Layer 2: [auth-db, auth-ui]     # Parallel
Layer 3: [auth-api]
Layer 4: [auth-middleware]
```

**Execution**:
```
# Step 0 - Create worktree (ONLY if TASK_ID is set)
if $TASK_ID:
    Task(subagent_type="git-worktree", prompt="create-worktree for task $TASK_ID")
    [wait for completion, parse worktree path]

# Layer 1
Task(subagent_type="research_agent", ...)
[wait for completion]

# Layer 2 - PARALLEL (single message, multiple Task calls)
Task(subagent_type="code_agent", prompt="DB from research: ...")
Task(subagent_type="frontend_agent", prompt="UI from research: ...")
[wait for both]

# Layer 3
Task(subagent_type="code_agent", prompt="API using DB model: ...")

# Layer 4
Task(subagent_type="code_agent", prompt="Middleware using API: ...")

# Final step - ONLY if TASK_ID is set
if $TASK_ID:
    Task(subagent_type="git-merge", prompt="Merge task branch to main")
    # Note: Worktree cleanup disabled - preserved for debugging
```

Present implementation summary with files modified, commit hash, and merge status. Note that worktree remains at `/tmp/agentlab-worktrees/{task_id}` for inspection.

## QA Workflow with Retry Example

**Scenario:** Authentication system implementation has validation issues

**Cycle 1 - Initial Validation:**
```
Task(subagent_type="task-completion-validator", ...)
Result: "VALIDATION STATUS: REJECTED
CRITICAL ISSUES:
- Critical: Password hashing not implemented (using plaintext)
- High: No SQL injection protection in login query
..."
```

**Response:** Parse REJECTED → Invoke fix cycle
```
Task(subagent_type="code_agent",
     prompt="Fix critical issues in auth implementation:
     1. Implement bcrypt password hashing (currently plaintext)
     2. Add SQL injection protection using parameterized queries in login
     Files: auth.py:45-67, database.py:123")
[wait for completion and commit]
```

**Cycle 2 - Re-validation:**
```
Task(subagent_type="task-completion-validator", ...)
Result: "VALIDATION STATUS: APPROVED
..."
```

**Response:** APPROVED → Proceed to merge
```
Task(subagent_type="git-merge", prompt="Merge task branch to main")
# Note: Worktree cleanup disabled - preserved for debugging
```

**Final Summary:**
"Implemented authentication system with bcrypt password hashing and SQL injection protection. Validation initially REJECTED due to security issues, fixed in cycle 2, approved. Merged to main. Worktree preserved at /tmp/agentlab-worktrees/{task_id} for inspection. Commits: abc123, def456, ghi789."

Task description: $ARGUMENTS
