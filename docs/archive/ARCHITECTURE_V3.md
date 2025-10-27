# Cloth API & Agent Architecture V3

## Core Concept

**All tasks go through orchestrator.** The orchestrator analyzes and delegates to specialized workers.

## Architecture

```
User Message
    ↓
Claude API or Orchestrator returns BACKGROUND_TASK format
    ↓
Bot creates Task(worker_type="orchestrator")  ← ALWAYS orchestrator
    ↓
WorkerPool spawns orchestrator agent
    ↓
Orchestrator analyzes task
    ↓
Orchestrator uses Task tool to spawn:
    ├─ code_worker (backend, scripts, bug fixes, git ops)
    ├─ frontend_worker (web UI, HTML/CSS/JS, design)
    └─ research_worker (analysis, proposals, NO implementation)
    ↓
Sub-worker executes and returns result
    ↓
Orchestrator summarizes
    ↓
User receives notification
```

## What Changes from Current System

**Keep exactly as is:**
- ✓ BACKGROUND_TASK string format
- ✓ Task creation in `tasks.py`
- ✓ TaskManager
- ✓ Task dataclass with `worker_type` field
- ✓ WorkerPool execution

**Only change:**
- When creating a task, ALWAYS use `worker_type="orchestrator"`
- Orchestrator agent uses Task tool to spawn actual workers
- Orchestrator prompt updated to handle delegation

## Code Changes Required

### 1. Update task creation (claude_api.py or main.py)

**Before:**
```python
# Parse BACKGROUND_TASK and extract worker_type
task = task_manager.create_task(
    worker_type=extracted_worker_type,  # code_worker, frontend_worker, etc.
    description=description,
    ...
)
```

**After:**
```python
# Always use orchestrator
task = task_manager.create_task(
    worker_type="orchestrator",  # ALWAYS orchestrator
    description=description,
    ...
)
```

### 2. Update orchestrator agent config

Replace `.claude/agents/orchestrator.md` with `orchestrator_v3.md`

**That's it!** Everything else stays the same.

## Flow Examples

### Example 1: Bug Fix

```
User: "fix bug in main.py"
    ↓
BACKGROUND_TASK|Fix bug in main.py|Fixing the bug.
    ↓
Create Task(worker_type="orchestrator", description="Fix bug in main.py")
    ↓
Spawn orchestrator agent (Haiku)
    ↓
Orchestrator analyzes: "Bug fix → code_worker"
    ↓
Orchestrator spawns code_worker via Task tool:
  - subagent_type: code_worker
  - prompt: "Fix bug in main.py..."
    ↓
code_worker (Sonnet) executes:
  - Reads main.py
  - Fixes bug
  - Commits changes
  - Returns: "Fixed bug, committed"
    ↓
Orchestrator receives result
    ↓
Orchestrator returns: "Fixed bug in main.py. Committed changes."
    ↓
User gets notification
```

### Example 2: Landing Page

```
User: "build a landing page"
    ↓
BACKGROUND_TASK|Build landing page|Building a landing page.
    ↓
Create Task(worker_type="orchestrator", description="Build landing page")
    ↓
Spawn orchestrator agent (Haiku)
    ↓
Orchestrator analyzes: "Website/landing page → frontend_worker"
    ↓
Orchestrator spawns frontend_worker via Task tool:
  - subagent_type: frontend_worker
  - prompt: "Build responsive landing page..."
    ↓
frontend_worker (Sonnet) executes:
  - Creates HTML structure
  - Adds CSS styles
  - Implements responsive design
  - Validates with Chrome DevTools
  - Commits changes
  - Returns: "Built landing page, committed"
    ↓
Orchestrator receives result
    ↓
Orchestrator returns: "Built responsive landing page with hero, features, contact. Committed."
    ↓
User gets notification
```

### Example 3: Architecture Improvement

```
User: "improve error handling"
    ↓
BACKGROUND_TASK|Improve error handling|Analyzing and improving error handling.
    ↓
Create Task(worker_type="orchestrator", description="Improve error handling")
    ↓
Spawn orchestrator agent (Haiku)
    ↓
Orchestrator analyzes: "Improve → research first, then implement"
    ↓
Step 1: Orchestrator spawns research_worker via Task tool:
  - subagent_type: research_worker
  - prompt: "Analyze error handling, generate proposal..."
    ↓
research_worker (Sonnet) executes:
  - Analyzes codebase
  - Identifies weaknesses
  - Generates Markdown proposal
  - Returns proposal
    ↓
Step 2: Orchestrator spawns code_worker via Task tool:
  - subagent_type: code_worker
  - prompt: "Implement these improvements: [proposal]..."
    ↓
code_worker (Sonnet) executes:
  - Implements changes from proposal
  - Tests thoroughly
  - Commits changes
  - Returns: "Implemented improvements, committed"
    ↓
Orchestrator receives result
    ↓
Orchestrator returns: "Analyzed error handling and implemented improvements: centralized handler, standardized responses. Committed."
    ↓
User gets notification
```

## Benefits

### 1. Separation of Concerns
- Task creation doesn't need to know about worker types
- Orchestrator makes intelligent delegation decisions
- Easy to add new worker types (just update orchestrator)

### 2. Intelligent Routing
- Orchestrator analyzes task context and keywords
- Can spawn multiple workers for complex tasks
- Can do research → approval → implementation workflows

### 3. Minimal Code Changes
- Keep existing task creation logic
- Keep TaskManager and Task dataclass
- Only change: always use `worker_type="orchestrator"`
- Update orchestrator prompt

### 4. Flexibility
- Orchestrator can spawn workers sequentially or in parallel
- Can combine multiple worker types for complex tasks
- Can add reasoning and analysis before delegating

## Worker Descriptions

### orchestrator
**File:** `.claude/agents/orchestrator.md`
**Spawned:** For EVERY task
**Tools:** Read, Glob, Grep
**Model:** Haiku (fast routing)
**Role:** Analyzes task, delegates to specialized workers via Task tool

### code_worker
**File:** `.claude/agents/code_worker.md`
**Spawned by:** Orchestrator (via Task tool)
**Tools:** Read, Write, Edit, Glob, Grep, Bash
**Model:** Sonnet (powerful coding)
**Role:** Backend code, bug fixes, features, file ops, git commands

### frontend_worker
**File:** `.claude/agents/frontend_worker.md`
**Spawned by:** Orchestrator (via Task tool)
**Tools:** Read, Write, Edit, Glob, Grep, Bash, Chrome DevTools MCP
**Model:** Sonnet
**Role:** Web UI/UX, HTML/CSS/JS, design, responsive layouts, visual validation

### research_worker
**File:** `.claude/agents/research_worker.md`
**Spawned by:** Orchestrator (via Task tool)
**Tools:** Read, Glob, Grep (NO Write/Edit/Bash)
**Model:** Sonnet
**Role:** Analyze codebase, propose improvements, generate proposals (NO implementation)

## Implementation Steps

1. **Update orchestrator prompt** ✓
   - Replace `.claude/agents/orchestrator.md` with `orchestrator_v3.md`

2. **Update task creation**
   - Find where BACKGROUND_TASK is parsed
   - Change `worker_type` to always be `"orchestrator"`

3. **Test**
   - Bug fix task → should route to code_worker
   - Landing page task → should route to frontend_worker
   - Improvement task → should route to research_worker → code_worker

4. **Deploy**
   - Replace old orchestrator with V3

## File Structure

```
agentlab/
├── .claude/agents/
│   ├── orchestrator.md          # V3: Delegation manager (uses Task tool)
│   ├── code_worker.md           # Backend worker (unchanged)
│   ├── frontend_worker.md       # Frontend worker (unchanged)
│   └── research_worker.md       # Research worker (unchanged)
├── telegram_bot/
│   ├── main.py                  # Update: worker_type="orchestrator"
│   ├── claude_api.py            # Update: worker_type="orchestrator"
│   ├── tasks.py                 # Unchanged
│   └── worker_pool.py           # Unchanged
└── ARCHITECTURE_V3.md           # This document
```

## Migration

**Step 1:** Replace orchestrator prompt
```bash
cp .claude/agents/orchestrator_v3.md .claude/agents/orchestrator.md
```

**Step 2:** Update task creation
Find where tasks are created and change:
```python
worker_type="code_worker"  # OLD
→
worker_type="orchestrator"  # NEW (always)
```

**Step 3:** Test and deploy
```bash
# Restart bot
# Test with various task types
```

That's it! 🎉
