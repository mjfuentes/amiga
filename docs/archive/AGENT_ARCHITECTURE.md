# Agent-Based Architecture

**Status**: Phase 5 - Proper Separation of Concerns (October 17, 2025)

## Overview

The Telegram bot uses Claude Code's native agent system with a clear separation of concerns:
- **Orchestrator**: Routes queries, answers questions, reads/analyzes files
- **code_worker**: Executes backend coding tasks, file operations, edits, and git commands
- **frontend_worker**: Specialized for frontend/web development with Chrome DevTools validation
- **research_worker**: Analyzes code and proposes improvements without implementing

This refactoring ensures orchestrator never attempts writes or bash execution - it spawns specialized workers instead.

## Architecture

```
User Message (text or voice)
    ↓
Telegram Bot (main.py)
    ↓
Orchestrator Integration (orchestrator.py)
    ↓ Invokes claude chat
Claude Code Orchestrator Agent (.claude/agents/orchestrator.md)
    ├─ Direct response (Q&A, explanations)
    │
    ├─ Task: Spawn Research Worker (.claude/agents/research_worker.md)
    │   ↓ Returns Markdown proposal
    │   ↓ Orchestrator displays proposal
    │   ↓ User approves/rejects/refines
    │   ↓
    │   └─ If approved: Spawn Code Worker
    │
    ├─ Task: Spawn Code Worker (.claude/agents/code_worker.md)
    │  ├─ Backend coding tasks
    │  └─ Implement approved proposal
    │  ↓ Returns result
    │
    └─ Task: Spawn Frontend Worker (.claude/agents/frontend_worker.md)
       ├─ Web/UI development tasks
       └─ Uses Chrome DevTools for validation
       ↓ Returns result
Orchestrator composes response
    ↓
Bot sends to user (with proposal display or implementation summary)
```

## Research-to-Implementation Workflow

The new research_worker enables a two-phase improvement process:

### Phase 1: Research & Proposal
1. User requests improvements: "improve error handling", "better architecture", etc.
2. Orchestrator recognizes research request
3. Orchestrator spawns research_worker with Task tool
4. research_worker analyzes codebase, generates Markdown proposal
5. Orchestrator displays proposal to user in chat

### Phase 2: Approval & Implementation
6. User reviews proposal (or refines request)
7. User indicates approval: "looks good", "approve", "do it", etc.
8. Orchestrator recognizes approval in conversation history
9. Orchestrator spawns code_worker with proposal as context
10. code_worker implements changes from proposal
11. Orchestrator displays implementation summary

This workflow prevents implementing changes the user didn't specifically approve.

## Key Components

### 1. Orchestrator Agent (`.claude/agents/orchestrator.md`)

**Role**: Router and analyzer - handles ALL user interactions and agent spawning

**Can Do**:
- Answer questions and provide explanations
- Read and analyze files (Read, Glob, Grep)
- Route coding tasks to code_worker via Task tool
- Route analysis/improvement requests to research_worker via Task tool
- Compose conversational responses
- Handle voice input with transcription error tolerance
- Track pending proposals for approval/implementation

**Cannot Do** (Must spawn agents):
- Create/write files → Spawn code_worker
- Edit files → Spawn code_worker
- Run bash commands → Spawn code_worker
- Execute git operations → Spawn code_worker
- Propose refactoring → Spawn research_worker first

**Tools**: Task, Read, Glob, Grep

**Output**: Plain text user-facing message

**Spawning agents**: Uses Task tool with `subagent_type="code_worker"` or `subagent_type="research_worker"`

### 2. Research Worker Agent (`.claude/agents/research_worker.md`)

**Role**: Analyzes codebase and proposes improvements without implementing

**Responsibilities**:
- Analyze existing code patterns and architecture
- Identify improvement opportunities
- Generate detailed proposals as Markdown documents
- Provide concrete code examples (current vs. proposed)
- Estimate effort and prioritize changes
- **Do NOT implement changes**

**Tools**: Read, Glob, Grep (analysis only)

**Spawned by**: Orchestrator when user requests:
- "improve X" / "better architecture" / "refactor"
- "propose changes" / "suggest improvements"
- "optimize performance" / "review security"

**Output**: Markdown proposal document for user review

**Next Step**: If user approves proposal, orchestrator spawns code_worker or frontend_worker to implement

### 3. Code Worker Agent (`.claude/agents/code_worker.md`)

**Role**: Executes backend coding tasks and general file operations

**Responsibilities**:
- Read, write, edit files
- Execute bash commands (git, tests, builds)
- Search codebase
- Commit changes with descriptive messages
- Return concise summaries of work

**Tools**: Read, Write, Edit, Glob, Grep, Bash

**Spawned by**: Orchestrator via Task tool for:
- Direct coding tasks: "fix bug in X", "add feature Y"
- Implementation of approved proposals: Receives proposal as context

**Key Policy**: Always commits changes after modifications

### 4. Frontend Worker Agent (`.claude/agents/frontend_worker.md`)

**Role**: Specialized frontend development with visual validation

**Responsibilities**:
- Build and modify web UIs (HTML, CSS, JavaScript)
- Implement responsive designs and layouts
- Navigate reference websites and extract design patterns
- Take screenshots and snapshots for validation
- Compare implementations against reference examples
- Test across different viewport sizes
- Validate visual design matches requirements

**Tools**: Read, Write, Edit, Glob, Grep, Bash, Chrome DevTools MCP (all browser tools)

**Spawned by**: Orchestrator when user requests involve:
- "website", "web page", "landing page", "portfolio"
- "UI", "UX", "design", "styling", "layout"
- "HTML", "CSS", "JavaScript", "frontend"
- "gallery", "navigation", "header", "footer"
- Design references: "copy this design", "similar to this site"

**Workflow**:
1. Analyze reference examples if provided (navigate, screenshot, inspect)
2. Extract design tokens (fonts, colors, spacing, layout)
3. Implement incrementally (structure → styles → responsive → interactions)
4. Validate continuously (screenshots, comparisons, responsive testing)
5. Iterate until implementation matches requirements

**Key Policy**: Extensive use of Chrome DevTools for visual validation throughout development

### 5. Orchestrator Integration (`telegram_bot/orchestrator.py`)

**Purpose**: Bridge between bot and Claude Code orchestrator agent

**Flow**:
1. Builds context (user query, input method, history, workspace, repos)
2. Invokes `claude chat --model haiku` with orchestrator agent
3. Orchestrator decides: answer directly, spawn code_worker, or BACKGROUND_TASK
4. Returns user-facing response (or BACKGROUND_TASK format)

**Context Provided to Orchestrator**:
```json
{
  "user_query": "user's message",
  "input_method": "voice" | "text",
  "conversation_history": [...last 3 messages...],
  "current_workspace": "/current/path",
  "available_repositories": [...discovered repos...],
  "bot_repository": "/path/to/bot/code",
  "active_tasks": [...]
}
```

**Routing Decision** (handled by orchestrator):
- **Direct response**: "What's async?" → Explain directly
- **Spawn code_worker**: "Fix bug in X" → Task tool with code_worker
- **Background task**: "Refactor auth system" → BACKGROUND_TASK format

## Task Routing Strategy

The orchestrator uses this decision tree for each user query:

### 1. Direct Response (Q&A, Explanations)
**Examples**: "What's async?", "Explain closures", "Show me status"
- Orchestrator answers using available context
- No Task tool usage
- Returns conversational response

### 2. Quick Code Tasks (Spawn code_worker)
**Examples**: "Fix bug in X", "Add feature Y", "Commit changes"
- Orchestrator uses Task tool: `subagent_type="code_worker"`
- Waits for code_worker result
- Composes user-facing response

### 3. Complex Tasks (BACKGROUND_TASK)
**Examples**: "Refactor entire auth system", "Create Tetris game", "Build new API"
- Orchestrator returns: `BACKGROUND_TASK: <description>`
- Bot creates background task
- code_worker executes asynchronously
- User notified when complete

**Decision Rules**:
- Estimated <2 minutes: Use Task tool (option 2)
- Estimated >2 minutes: Use BACKGROUND_TASK (option 3)
- Multiple complex files: Always BACKGROUND_TASK
- "Create/build" requests: Always BACKGROUND_TASK

## Voice Input Handling

When `input_method: "voice"`:
- Orchestrator is more permissive with typos and transcription errors
- Infers repository names despite errors
- Example: "group therapy" → fuzzy matches "grouptherapy" or "group-therapy"

## Self-Awareness

The orchestrator knows its own codebase at `bot_repository`:
- `telegram_bot/main.py` - Bot logic, handlers
- `telegram_bot/orchestrator.py` - Orchestrator integration
- `telegram_bot/session.py` - Session management
- `telegram_bot/tasks.py` - Task tracking (legacy, may be deprecated)
- `.claude/agents/` - Agent configurations

When users say "you", "your code", "the bot" → refers to bot's own code

## Simplified Flow

**Old Architecture** (Deprecated):
```
User → Bot → detect_task_type → create_task → claude_interactive.py → execute → notify
```
Problems:
- Hardcoded task detection (keyword matching)
- Hardcoded workspace extraction (regex)
- Hardcoded user messages
- Separate JSON-based action system

**New Architecture**:
```
User → Bot → orchestrator → Claude Code (with agents) → response
```
Benefits:
- Natural language understanding
- Orchestrator composes all messages
- Agents spawn sub-agents as needed
- No JSON, no action parsing
- Simpler, more flexible

## Migration Notes

### Removed Components
- `detect_task_type()` - Replaced by orchestrator's NLU
- `extract_workspace_from_message()` - Replaced by orchestrator's understanding
- `execute_action()` - No longer needed (orchestrator returns text)
- JSON action intents - Simplified to text responses

### Deprecated (But Kept for Now)
- `execute_code_task()` - Not used, may remove later
- `show_task_status()` - Not used, may remove later
- `claude_interactive.py` - Legacy session management, replaced by agents

### Current Usage
- `claude_client` (ClaudeCodeSession) - Still used as fallback if orchestrator fails
- `session_manager` - Still tracks conversation history
- `task_manager` - Exists but not actively used by orchestrator yet

## Implementation Details

### How code_worker is Spawned

1. User sends message to bot
2. Bot calls `invoke_orchestrator()` with user query and context
3. Orchestrator agent receives context prompt
4. For coding tasks, orchestrator uses Claude Code's Task tool:
   ```
   Task(
     subagent_type="code_worker",
     description="Brief description",
     prompt="Detailed task with workspace, file info, etc"
   )
   ```
5. code_worker agent executes with tools: Read, Write, Edit, Glob, Grep, Bash
6. code_worker returns summary
7. Orchestrator composes user-facing response
8. Bot sends response to user

### Logging Code_worker and research_worker Spawning

When testing, check bot logs for:
```
INFO: Invoking orchestrator agent for: [user query]
DEBUG: [Claude Code loading orchestrator agent]
INFO: [research_worker spawned for analysis requests]
INFO: [code_worker spawned for coding tasks]
INFO: Orchestrator response: [result]
```

## Proposal Tracking

The orchestrator maintains context across turns to track proposals:

**Proposal State**:
- `pending`: Proposal displayed, awaiting user decision
- `approved`: User approved, implementation spawning
- `rejected`: User rejected, ready to refine

**How it works**:
1. research_worker returns proposal → stored in conversation context
2. Orchestrator recognizes approval keywords in next user message
3. If approved: Spawn code_worker with proposal context
4. If rejected: Discuss refinements, optionally re-run research_worker

**Approval Keywords**: "approve", "looks good", "do it", "go ahead", "yes", "implement", etc.

## Testing Checklist

- [ ] Simple query: "What's async/await in Python?" (direct response)
- [ ] Code fix: "Fix the bug in auth.py line 42" (BACKGROUND_TASK with code_worker)
- [ ] Own repo: "Add a /restart command to your code" (code_worker in bot_repository)
- [ ] Other repo: "in ~/myproject, fix bug in app.py" (code_worker in specified workspace)
- [ ] Voice input: "add a logging function" (permissive with errors)
- [ ] Background task: "refactor the entire authentication system" (BACKGROUND_TASK format)
- [ ] Research request: "improve the error handling" (Task tool spawns research_worker)
- [ ] Research approval: User says "approve" after seeing proposal (Task tool spawns code_worker)
- [ ] Frontend task: "build a portfolio website" (BACKGROUND_TASK with frontend_worker)
- [ ] Frontend with reference: "copy the design from https://example.com" (frontend_worker)
- [ ] Frontend styling: "update the gallery layout" (frontend_worker)
- [ ] Check logs show correct worker types being spawned (code_worker vs frontend_worker)

## Future Enhancements

1. **Task persistence**: Have orchestrator create/update tasks in TaskManager
2. **Background execution**: Long-running code_worker tasks with status updates
3. **Multi-step workflows**: Orchestrator chains multiple agents
4. **Specialized agents**: Add data_analyst, debugger, researcher agents
5. **Cost tracking**: Monitor Claude API usage per user/task

## Configuration

Agent files location: `.claude/agents/`
- `orchestrator.md` - Main orchestrator and router
- `code_worker.md` - Backend code execution worker
- `frontend_worker.md` - Frontend development worker with Chrome DevTools
- `research_worker.md` - Analysis and proposal worker

Bot configuration: `.env`
```bash
WORKSPACE_PATH=/Users/matifuentes/Workspace  # Base workspace
BOT_REPOSITORY=/Users/matifuentes/Workspace/agentlab  # Bot's own code
```

## Example Interactions

### Example 1: Simple Question (No spawning)
```
User: "Explain async/await in Python"
Bot: Orchestrator responds directly with explanation
Logs: "Invoking orchestrator..." → "Orchestrator response: [explanation]"
```

### Example 2: Quick Code Fix (code_worker spawned)
```
User: "Fix the null pointer error in auth.py line 42"
Bot: Orchestrator spawns code_worker via Task tool
code_worker: Reads auth.py, fixes error, commits change
Orchestrator: Composes response
Bot: "Fixed null pointer in auth.py:42 by adding user existence check"
Logs: "Task tool invoked with code_worker" → "code_worker returns: [summary]"
```

### Example 3: Own Code Modification (code_worker spawned)
```
User: "Add a /restart command to your code"
Bot: Orchestrator spawns code_worker with bot_repository workspace
code_worker: Modifies main.py, adds handler, commits
Orchestrator: Composes response
Bot: "Added /restart command. Use /restart to gracefully restart the bot."
```

### Example 4: Complex Task (BACKGROUND_TASK)
```
User: "Refactor the entire authentication system with OAuth2"
Orchestrator: Returns BACKGROUND_TASK format
Bot: Creates background task, sends: "Background Task Started (#xyz). Refactoring auth system... You'll be notified when complete."
Later: code_worker executes in background, bot notifies user when done
```

### Example 5: Voice Input with Transcription Error
```
User: (voice) "add logging to group therapy project"
Transcription: "add logging to group therapy project" (might be "groove therapy" etc)
Orchestrator: Fuzzy matches to "groovetherapy" workspace
code_worker: Adds logging in groovetherapy project
Bot: "Added logging to the groovetherapy project"
```

### Example 6: Research & Proposal (Two-Phase Workflow)
```
User: "improve the error handling in the auth system"
Bot: Orchestrator spawns research_worker via Task tool
research_worker: Analyzes auth.py, identifies current error patterns, proposes retry logic, custom exceptions, structured logging
Orchestrator: Displays proposal in chat:
    Bot: "[Markdown proposal showing current code vs. proposed improvements]"
User: "looks good"
Bot: Orchestrator recognizes approval, spawns code_worker with proposal context
code_worker: Implements all proposed changes, commits with "Improve error handling: add retry logic, custom exceptions, structured logging"
Orchestrator: Composes response
Bot: "Done. Improved error handling with retry logic, custom exceptions, and structured logging."
```

### Example 7: Refine Proposal Before Implementation
```
User: "better architecture for the API"
Bot: Orchestrator spawns research_worker
research_worker: Analyzes API structure, proposes modularization and middleware improvements
Orchestrator: Displays proposal
User: "good but skip the middleware part"
Bot: Orchestrator refines and respawns research_worker with refined scope
research_worker: Returns updated proposal without middleware changes
Orchestrator: Displays updated proposal
User: "approve"
Bot: Orchestrator spawns code_worker with refined proposal
code_worker: Implements refined changes
Bot: "Done. Refactored API with better modularization."
```

### Example 8: Frontend Development (frontend_worker spawned)
```
User: "Build a portfolio website with a gallery similar to https://example.com/gallery"
Bot: Orchestrator recognizes frontend task, returns BACKGROUND_TASK format with frontend_worker
Bot: Creates background task, sends: "Background Task Started (#abc). Creating a portfolio website with gallery."
frontend_worker:
  1. Navigates to https://example.com/gallery
  2. Takes screenshot of reference design
  3. Takes snapshot to inspect DOM structure
  4. Analyzes: 3-column masonry layout, minimal gaps, rounded corners
  5. Extracts: Google Font links, color palette, spacing values
  6. Implements HTML structure
  7. Adds CSS with extracted design tokens
  8. Takes screenshot of implementation
  9. Compares side-by-side with reference
  10. Adjusts spacing and styling to match
  11. Tests responsive behavior (desktop, tablet, mobile)
  12. Commits changes
Bot: Notifies user with result and screenshots showing comparison
```

### Example 9: Frontend Task with Exact Copy Request
```
User: "Copy the design from https://example.com exactly for my landing page"
Bot: Orchestrator recognizes frontend copy task, returns BACKGROUND_TASK with frontend_worker
frontend_worker:
  1. Navigates to https://example.com
  2. Screenshots entire page
  3. Inspects header, hero, sections, footer
  4. Extracts ALL design tokens:
     - Fonts: Checks <link> tags for Google Fonts (e.g., 'Inter', 'Playfair Display')
     - Colors: Inspects all color values (#1a1a1a, #f5f5f5, etc.)
     - Spacing: Measures margins (80px sections), padding (24px), gaps (16px)
     - Layout: Identifies CSS Grid (1fr 1fr 1fr), max-width: 1200px
  5. Creates matching HTML structure with semantic tags
  6. Imports exact same Google Fonts
  7. Uses extracted color values in CSS
  8. Matches spacing pixel-perfect
  9. Implements responsive breakpoints to match reference
  10. Screenshots implementation
  11. Compares side-by-side with reference
  12. Iterates on differences (font sizes, line heights, shadows)
  13. Final validation across all sections
  14. Commits with descriptive message
Bot: Notifies with "Landing page created matching https://example.com design"
```

## Refactoring Summary (October 17, 2025 + Research Worker Enhancement)

**Phase 1 - Proper Separation of Concerns** (October 17, 2025):
1. Orchestrator no longer handles file writes or bash execution
2. Orchestrator spawns code_worker via Task tool for coding tasks
3. Added clear routing logic: Direct response, code_worker task, or background task
4. code_worker now commits changes automatically

**Phase 2 - Two-Phase Approval Workflow**:
5. Added research_worker for analysis and proposals without implementation
6. Orchestrator can spawn research_worker for improvement requests
7. Proposal-approval workflow prevents unintended changes
8. Two-phase process: Research → Display Proposal → Approval → Implement

**Phase 3 - Specialized Frontend Worker** (October 18, 2025):
9. Added frontend_worker specialized for web UI/UX development
10. Chrome DevTools MCP integration for visual validation
11. Orchestrator routes frontend tasks based on keywords
12. Worker type selection system: code_worker vs frontend_worker
13. Background task format extended to support worker_type specification

**Benefits**:
- Clear separation of concerns between agent types
- Orchestrator focuses on routing and agent management
- research_worker handles analysis and proposals (Read-only)
- code_worker handles backend coding and general file operations
- frontend_worker handles web development with visual validation
- Users can review proposals before implementation
- Specialized workers leverage appropriate tools (Chrome DevTools for frontend)
- Easier to test and maintain with focused responsibilities
- Better error handling per agent type
- Logs clearly show which agents are spawned

**Files Modified**:
- `.claude/agents/orchestrator.md` - Updated with worker type selection and routing
- `.claude/agents/code_worker.md` - Backend coding worker
- `.claude/agents/frontend_worker.md` - NEW: Frontend development worker with Chrome DevTools
- `.claude/agents/research_worker.md` - Analysis and proposal agent
- `telegram_bot/claude_api.py` - Extended BACKGROUND_TASK parsing for worker_type
- `telegram_bot/tasks.py` - Added worker_type field to Task dataclass
- `telegram_bot/claude_interactive.py` - Added agent parameter to session spawning
- `telegram_bot/main.py` - Pass worker_type when creating and executing tasks
- `AGENT_ARCHITECTURE.md` - Documented frontend_worker and worker type system
