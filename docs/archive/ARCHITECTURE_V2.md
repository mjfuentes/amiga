# Cloth API & Agent Architecture V2

## Overview

Two-tier routing system with Claude API for fast responses and Orchestrator Agent for complex task execution.

## Architecture Diagram

```
User Message
    ↓
Telegram Bot (main.py)
    ↓
Route Decision
    ├─────────────────────────────┬────────────────────────────┐
    │                             │                            │
FAST PATH                    COMPLEX PATH               DIRECT EXECUTION
    ↓                             ↓                            ↓
Claude API                   Create Task              User-initiated task
(anthropic API)           (TaskManager)                       ↓
    ↓                             ↓                            ↓
Simple questions           Spawn Orchestrator          Spawn Orchestrator
Chat responses                   Agent                        Agent
<1s response                  (Haiku model)                (Haiku model)
    │                             ↓                            ↓
    │                   Analyze task request          Analyze task request
    │                             ↓                            ↓
    │                   Use Task tool to spawn        Use Task tool to spawn
    │                   appropriate worker            appropriate worker
    │                             ├──────────┬──────────┬─────────┐
    │                             │          │          │         │
    │                        code_worker frontend research  [other]
    │                        (Sonnet)    (Sonnet)  (Sonnet)
    │                             │          │          │
    │                        Execute    Build UI   Analyze
    │                        Backend    Validate   Propose
    │                        Code       w/Chrome   Changes
    │                        Git ops    DevTools
    │                             │          │          │
    │                             └──────────┴──────────┘
    │                                      ↓
    │                               Return results
    │                                      ↓
    │                            Orchestrator summarizes
    │                                      ↓
    └──────────────────────────────────────┴─────────────────────→
                                           ↓
                                    User receives result
```

## Components

### 1. Claude API (Fast Path)
**File:** `telegram_bot/claude_api.py`

**Purpose:** Handle simple questions and chat without spawning agents

**When to use:**
- Questions: "What is async?", "Explain closures"
- Chat: "Hey", "Thanks"
- Status queries
- Quick information requests

**Response time:** <1s

**Model:** Haiku (via Anthropic API)

**Tools:** None (direct API call)

---

### 2. Orchestrator Agent (Complex Path)
**File:** `.claude/agents/orchestrator.md`

**Purpose:** Analyze complex tasks and delegate to specialized workers

**When to use:**
- File operations (create, edit, modify)
- Code changes (bug fixes, features, refactoring)
- Web UI development
- Architecture analysis
- ANY execution work

**Spawned by:** TaskManager when background task is created, or directly by user request

**Model:** Haiku (fast orchestration)

**Tools:** Read, Glob, Grep (analysis only)

**Delegation pattern:** Uses Task tool to spawn workers

**Key responsibility:**
- Analyze task request
- Decide which worker to spawn
- Delegate to worker using Task tool
- Summarize results

---

### 3. Specialized Workers

#### code_worker
**File:** `.claude/agents/code_worker.md`

**Purpose:** Execute backend code changes and file operations

**Spawned by:** Orchestrator via Task tool

**Model:** Sonnet (powerful for coding)

**Tools:** Read, Write, Edit, Glob, Grep, Bash

**Responsibilities:**
- File operations (create, edit, modify)
- Backend code (Python, JavaScript, etc.)
- Bug fixes and features
- Git operations (commit, push)
- Running tests and builds
- Most coding tasks

**Always commits changes** before returning

---

#### frontend_worker
**File:** `.claude/agents/frontend_worker.md`

**Purpose:** Build and refine web UI/UX

**Spawned by:** Orchestrator via Task tool (when keywords detected)

**Model:** Sonnet

**Tools:** Read, Write, Edit, Glob, Grep, Bash, **Chrome DevTools MCP**

**Responsibilities:**
- Web UI/UX (HTML, CSS, JavaScript)
- Design implementation
- Responsive layouts
- Visual validation with Chrome DevTools
- Screenshot comparison
- Browser-based applications

**Trigger keywords:**
- "website", "web page", "landing page", "portfolio"
- "UI", "UX", "design", "styling", "layout"
- "HTML", "CSS", "JavaScript", "frontend"
- "responsive", "gallery", "navigation"
- Design references: "like this site", "copy this design"

**Special capability:** Chrome DevTools integration for visual validation

---

#### research_worker
**File:** `.claude/agents/research_worker.md`

**Purpose:** Analyze and propose improvements WITHOUT implementing

**Spawned by:** Orchestrator via Task tool

**Model:** Sonnet

**Tools:** Read, Glob, Grep (NO Write, Edit, or Bash)

**Responsibilities:**
- Analyze codebase architecture
- Identify improvement opportunities
- Generate Markdown proposals
- Provide code examples (current vs. proposed)
- Estimate effort and prioritize

**Output:** Single Markdown proposal document

**Workflow:**
1. User requests improvement
2. Orchestrator spawns research_worker
3. research_worker analyzes and generates proposal
4. Orchestrator shows proposal to user
5. User reviews and approves
6. Orchestrator spawns code_worker with proposal context
7. code_worker implements changes

**Trigger keywords:**
- "improve", "better architecture", "suggest"
- "propose", "analyze", "review"
- "optimize performance", "refactor strategy"

---

## Flow Examples

### Example 1: Simple Question (Fast Path)

```
User: "What's the difference between async and sync?"
    ↓
Telegram Bot → Claude API
    ↓
Claude API responds:
"Async lets code run without blocking - it pauses at 'await' and lets other stuff run.
Sync blocks until done. Use async for I/O (network, files, DB) to avoid freezing your app."
    ↓
User receives answer (<1s)
```

---

### Example 2: Bug Fix (Complex Path)

```
User: "fix bug in main.py line 42"
    ↓
Telegram Bot → Create background task
    ↓
TaskManager spawns Orchestrator Agent
    ↓
Orchestrator analyzes: "Bug fix → code_worker"
    ↓
Orchestrator uses Task tool:
  - subagent_type: code_worker
  - prompt: "Fix null pointer bug in main.py:42..."
    ↓
code_worker spawned (Sonnet)
    ↓
code_worker:
  1. Reads main.py
  2. Identifies null pointer issue
  3. Adds null check
  4. Tests the fix
  5. Commits with message: "Fix null pointer in main.py:42"
  6. Returns: "Fixed null pointer bug, added validation, committed"
    ↓
Orchestrator summarizes:
"Fixed the null pointer bug in main.py:42. Added null check before accessing user data. Committed changes."
    ↓
User receives notification
```

---

### Example 3: Website Creation (Frontend Path)

```
User: "build a landing page similar to https://example.com"
    ↓
Telegram Bot → Create background task
    ↓
TaskManager spawns Orchestrator Agent
    ↓
Orchestrator analyzes: "Website + design reference → frontend_worker"
    ↓
Orchestrator uses Task tool:
  - subagent_type: frontend_worker
  - prompt: "Build landing page inspired by example.com. Navigate to reference, analyze design, implement with responsive layout..."
    ↓
frontend_worker spawned (Sonnet + Chrome DevTools)
    ↓
frontend_worker:
  1. Navigates to https://example.com using Chrome DevTools
  2. Takes screenshot of reference
  3. Takes snapshot to inspect DOM
  4. Analyzes layout, colors, typography, spacing
  5. Creates HTML structure
  6. Implements CSS styles
  7. Adds JavaScript interactions
  8. Takes screenshot of implementation
  9. Compares with reference
  10. Refines spacing and colors
  11. Tests responsive behavior (mobile, tablet, desktop)
  12. Commits with message: "Build landing page with hero, features, and contact sections"
  13. Returns: "Built landing page matching reference design. Responsive across all breakpoints. Committed."
    ↓
Orchestrator summarizes:
"Built responsive landing page with navigation, hero section, features grid, and contact form. Validated visually with Chrome DevTools. Committed changes."
    ↓
User receives notification
```

---

### Example 4: Architecture Improvement (Research → Implementation)

```
User: "improve error handling"
    ↓
Telegram Bot → Create background task
    ↓
TaskManager spawns Orchestrator Agent
    ↓
Orchestrator analyzes: "Improvement proposal → research_worker"
    ↓
Orchestrator uses Task tool:
  - subagent_type: research_worker
  - prompt: "Analyze error handling patterns. Generate detailed proposal..."
    ↓
research_worker spawned (Sonnet, read-only)
    ↓
research_worker:
  1. Reads error handling code across codebase
  2. Identifies patterns and weaknesses
  3. Generates Markdown proposal with:
     - Current state analysis
     - Specific improvements
     - Code examples (current vs. proposed)
     - Effort estimates
     - Prioritization
  4. Returns proposal document
    ↓
Orchestrator shows proposal to user:
"Here's the error handling improvement proposal:

# Error Handling Improvements

## Summary
...

## Proposed Changes
...

Want me to implement these changes?"
    ↓
User: "Yes, implement it"
    ↓
Orchestrator uses Task tool:
  - subagent_type: code_worker
  - prompt: "Implement error handling improvements from this proposal: [full proposal]..."
    ↓
code_worker spawned (Sonnet)
    ↓
code_worker:
  1. Reads proposal
  2. Implements each change
  3. Tests thoroughly
  4. Commits each change with descriptive messages
  5. Returns: "Implemented all error handling improvements"
    ↓
Orchestrator summarizes:
"Analyzed error handling and implemented improvements: centralized error handler, standardized responses, retry logic. All changes committed."
    ↓
User receives notification
```

---

## Key Design Principles

### 1. **Orchestrator doesn't know worker types ahead of time**
   - The Cloth API (task creation) doesn't specify worker type
   - Orchestrator agent decides dynamically based on task analysis
   - Clean separation of routing logic from task creation

### 2. **Two-tier performance optimization**
   - Fast path (Claude API): <1s for questions
   - Complex path (Orchestrator → Workers): Background execution for tasks
   - Users get immediate acknowledgment + notification when complete

### 3. **Orchestrator is a delegator, not an executor**
   - Has only Read, Glob, Grep tools (analysis only)
   - Cannot write files, execute code, or run bash commands
   - MUST delegate all execution work to specialized workers

### 4. **Workers are specialized and focused**
   - code_worker: Backend code and general file operations
   - frontend_worker: Web UI/UX with visual validation
   - research_worker: Analysis and proposals (read-only)
   - Each worker has appropriate tools for its domain

### 5. **Context-aware routing**
   - Orchestrator analyzes task keywords and context
   - Automatically detects frontend work (UI, design, HTML, CSS, JavaScript)
   - Routes analysis requests to research_worker
   - Defaults to code_worker for general coding

### 6. **Progressive enhancement workflow**
   - Research first (analyze, propose) → User approval → Implementation
   - Prevents unwanted changes
   - Allows user to review architectural decisions
   - Clear separation of analysis vs. execution

---

## File Structure

```
agentlab/
├── .claude/
│   └── agents/
│       ├── orchestrator.md          # Main orchestrator (delegates to workers)
│       ├── code_worker.md           # Backend coding agent
│       ├── frontend_worker.md       # Web UI/UX agent (Chrome DevTools)
│       └── research_worker.md       # Analysis & proposals (read-only)
├── telegram_bot/
│   ├── main.py                      # Bot entry point, message routing
│   ├── claude_api.py                # Fast path (Claude API integration)
│   ├── orchestrator.py              # Orchestrator agent invocation
│   ├── tasks.py                     # TaskManager, Task dataclass
│   ├── worker_pool.py               # Background task execution
│   └── session.py                   # Session management
└── ARCHITECTURE_V2.md               # This document
```

---

## Benefits of V2 Architecture

### Before (V1)
- Orchestrator returns `BACKGROUND_TASK|worker_type|description|message` string
- Telegram bot parses string and creates task with pre-selected worker
- Tight coupling between orchestrator and task creation format
- Hard to extend or modify routing logic

### After (V2)
- Orchestrator is a running agent that uses Task tool
- Orchestrator decides worker type dynamically
- Clean separation: Cloth API creates task → Orchestrator delegates → Workers execute
- Easy to add new worker types (just update orchestrator's decision logic)
- Orchestrator can spawn multiple workers for complex tasks
- Better error handling and result aggregation

---

## Migration Path

### Phase 1: Create V2 Prompts (DONE)
- ✅ New orchestrator_v2.md with Task tool delegation
- ✅ Update worker descriptions to clarify spawn triggers
- ✅ Document architecture

### Phase 2: Update Cloth API Integration
- Modify `orchestrator.py` to spawn orchestrator as a running agent
- Remove BACKGROUND_TASK string parsing
- Orchestrator returns final result directly

### Phase 3: Update TaskManager
- Remove `worker_type` from Task dataclass (orchestrator decides)
- Simplify task creation (no worker_type parameter)
- Tasks just contain description and context

### Phase 4: Testing & Rollout
- Test with various task types
- Verify correct worker selection
- Validate multi-step workflows (research → approval → implementation)
- Monitor performance and accuracy

---

## Next Steps

1. **Review orchestrator_v2.md** - validate prompt logic
2. **Update orchestrator.py** - remove string parsing, spawn orchestrator agent
3. **Update tasks.py** - remove worker_type field
4. **Test delegation** - verify orchestrator correctly chooses workers
5. **Deploy** - replace old orchestrator with V2
