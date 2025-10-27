# Research Worker Quick Reference

Fast lookup guide for the research_worker agent and proposal workflow.

## Agent Types & When to Use

### orchestrator (Router)
- **Use for**: Route all user requests appropriately
- **Tools**: Task, Read, Glob, Grep
- **Key decision**: Is this a question, code task, research request, or background work?
- **File**: `.claude/agents/orchestrator.md`

### research_worker (Analyzer)
- **Use for**: Analyze code and propose improvements
- **Tools**: Read, Glob, Grep (READ-ONLY)
- **Spawned by**: orchestrator when user says "improve", "refactor", "suggest", etc.
- **Output**: Markdown proposal document
- **File**: `.claude/agents/research_worker.md`

### code_worker (Implementer)
- **Use for**: Execute file changes, run git, implement proposals
- **Tools**: Read, Write, Edit, Glob, Grep, Bash
- **Spawned by**: orchestrator for direct coding tasks OR after research approval
- **Output**: Implementation summary + git commit
- **File**: `.claude/agents/code_worker.md`

## Research Request Detection

Orchestrator recognizes these as research requests:

```
Keywords:
- improve        → "improve error handling"
- refactor       → "refactor the auth system"
- better         → "better architecture"
- optimize       → "optimize performance"
- review         → "review security"
- suggest        → "suggest improvements"
- propose        → "propose changes"
- enhance        → "enhance logging"
- strengthen     → "strengthen validation"
- design         → "improve design"
- analyze        → "analyze patterns"
```

## Approval Keywords

After proposal displayed, orchestrator recognizes these in user's next message:

```
Approval:
- "approve"
- "looks good"
- "do it"
- "yes" / "yep" / "yeah"
- "go ahead"
- "implement"
- "let's" (in implementation context)

Rejection/Refinement:
- "no" / "no thanks" / "not needed"
- "too much"
- "skip" / "but skip X"
- "smaller scope"
- "just X" (narrow to specific part)
```

## Complete Flow Diagram

```
USER: "improve X"
  ↓
ORCHESTRATOR detects research keyword
  ↓
SPAWN research_worker
  ├─ Analyzes codebase
  ├─ Generates proposal.md
  └─ Returns to orchestrator
  ↓
DISPLAY proposal to user
  ↓
USER reviews (approve/refine/reject)
  ↓
IF APPROVED:
  ├─ SPAWN code_worker with proposal
  ├─ Implements changes
  ├─ Commits to git
  └─ Returns summary
ELSE IF REFINED:
  ├─ Discuss refinement
  └─ Loop back
ELSE IF REJECTED:
  └─ Acknowledge, ready for next request
```

## Spawning Research Worker

From orchestrator.md, use Task tool:

```
Task(
  subagent_type: "research_worker"
  description: "Brief description of what to analyze"
  prompt: "Full context including:
- What to analyze (file, component, or subsystem)
- What improvements to propose
- Focus area (architecture, performance, security, etc.)
- Expected: Markdown proposal document"
)
```

Example prompt:

```
Analyze error handling in /path/to/orchestrator.py

Identify:
- Current patterns
- Edge cases
- Opportunities

Propose concrete improvements with code examples.
Format as Markdown proposal.
```

## Spawning Code Worker (With Proposal)

After approval, orchestrator spawns code_worker:

```
Task(
  subagent_type: "code_worker"
  description: "Implement approved proposal"
  prompt: "Implement the following proposal:

[FULL PROPOSAL TEXT HERE]

Apply all recommended changes to [file/repo].
Commit with descriptive message."
)
```

## File Locations

```
.claude/agents/
  ├─ orchestrator.md          (Router, spawner)
  ├─ code_worker.md           (Implementer)
  └─ research_worker.md       (Analyzer)

telegram_bot/
  ├─ main.py                  (Telegram handlers)
  ├─ orchestrator.py          (Claude integration)
  └─ session.py               (Conversation history)

Documentation/
  ├─ AGENT_ARCHITECTURE.md    (System overview)
  ├─ RESEARCH_WORKFLOW.md     (Two-phase workflow)
  └─ QUICK_REFERENCE.md       (This file)
```

## Tools Available Per Agent

| Tool | Orchestrator | Research | Code |
|------|:---:|:---:|:---:|
| Read | ✓ | ✓ | ✓ |
| Write | ✗ | ✗ | ✓ |
| Edit | ✗ | ✗ | ✓ |
| Glob | ✓ | ✓ | ✓ |
| Grep | ✓ | ✓ | ✓ |
| Bash | ✗ | ✗ | ✓ |
| Task | ✓ | ✗ | ✗ |

## Key Design Principles

1. **Separation of Concerns**
   - Orchestrator: Routes only
   - Research: Analyzes only
   - Code: Implements only

2. **No Unreviewed Changes**
   - Research proposals displayed before implementation
   - User explicitly approves before code_worker runs

3. **Read-Only Analysis**
   - research_worker cannot modify files
   - Prevents accidental changes during analysis

4. **Conversation-Based State**
   - Proposal state tracked in conversation history
   - Approval detected from user's next message
   - No separate database needed (yet)

5. **Clear Tool Boundaries**
   - Each agent has exactly the tools it needs
   - Agents cannot do what they shouldn't

## Conversation Flow Examples

### Example 1: Research → Approve → Implement

```
User:      "improve the error handling"
Bot:       [Displays markdown proposal]
User:      "looks good"
Bot:       "Implementing... [summary of changes]"
```

### Example 2: Research → Refine → Approve → Implement

```
User:      "refactor the auth system"
Bot:       [Displays proposal with lots of changes]
User:      "good but skip the middleware part"
Bot:       [Shows refined proposal]
User:      "approve"
Bot:       "Implementing refined changes..."
```

### Example 3: Research → Reject

```
User:      "better architecture for API"
Bot:       [Displays proposal]
User:      "too much"
Bot:       "Got it. Want to focus on specific parts?"
```

## Testing Checklist

- [ ] "improve X" → research_worker spawns → proposal displays
- [ ] Proposal contains code examples and effort estimates
- [ ] "approve" → code_worker spawns → implements changes
- [ ] Git log shows new commit from code_worker
- [ ] "too much" → no implementation, ready for refinement
- [ ] Refined proposal → displays → on approval implements
- [ ] research_worker only reads files (no modifications)
- [ ] code_worker commits all changes

## Common Issues & Solutions

**Issue**: research_worker spawning for "fix bug" requests
- **Cause**: "improve" keyword detected incorrectly
- **Solution**: Orchestrator should distinguish between "fix" (code_worker) and "improve" (research_worker)

**Issue**: Proposal not displayed properly
- **Cause**: Markdown formatting lost in Telegram
- **Solution**: Send proposal as code block or document

**Issue**: User doesn't know proposal is pending approval
- **Cause**: Bot doesn't explicitly ask for approval
- **Solution**: Orchestrator message: "Proposal ready - approve when ready"

**Issue**: Conversation history loses proposal context
- **Cause**: Long conversations push proposal off context window
- **Solution**: Store proposal ID in session if needed

## Future Enhancements

1. **Telegram Buttons**
   - [Approve] [Refine] [Reject] inline buttons
   - Better UX than typing keywords

2. **Persistent Proposals**
   - Store proposals in database
   - Reference by ID instead of full text

3. **Diff Visualization**
   - Show before/after diffs in proposal
   - Highlight proposed changes

4. **Multi-Stage Proposals**
   - Phase 1, Phase 2, Phase 3 implementations
   - Partial approvals

5. **Rollback Support**
   - Track which proposal → which commits
   - Easy rollback: "undo the last proposal"

## Related Documentation

- **AGENT_ARCHITECTURE.md** - Full system architecture
- **RESEARCH_WORKFLOW.md** - Detailed workflow guide with examples
- **orchestrator.md** - Orchestrator agent instructions
- **research_worker.md** - Research worker agent instructions
- **code_worker.md** - Code worker agent instructions
