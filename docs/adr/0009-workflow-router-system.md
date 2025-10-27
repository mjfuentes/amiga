# 9. Workflow Router System

Date: 2025-01-15

## Status

Accepted

## Context

The bot evolved to support multiple specialized workflows beyond simple coding:

1. **code-task**: General-purpose coding (original workflow)
2. **smart-fix**: Intelligent issue resolution with escalation
3. **improve-agent**: Agent self-improvement from logs

**Selection challenge:**
- Users don't know which workflow to use
- Manual selection adds cognitive load (`/workflows:code-task` is clunky)
- Different tasks need different approaches
- Want to leverage Claude's intelligence for routing

**Requirements:**
- Automatic workflow selection from user's natural language
- Support for multiple workflow types
- Easy to add new workflows
- Fall back to safe default if uncertain
- Fast routing decision (< 2 seconds)

**Constraints:**
- Must not break existing behavior
- Should be transparent to users
- Routing must be reliable (wrong workflow = poor results)

## Decision

Implement **intelligent workflow router using Claude API (Haiku)** for automatic workflow selection.

**Architecture** (`core/routing.py`):

```python
class WorkflowRouter:
    def __init__(self):
        self.client = Anthropic(api_key=...)
        self.available_workflows = {
            "code-task": {
                "description": "General-purpose coding task orchestration...",
                "use_for": "New features, bug fixes, refactoring..."
            },
            "smart-fix": {
                "description": "Intelligent issue resolution...",
                "use_for": "Bugs, errors, crashes, performance..."
            },
            "improve-agent": {
                "description": "Analyzes agent performance...",
                "use_for": "Improving agent behavior..."
            }
        }

    def route_task(self, task_description: str) -> str:
        # Use Claude Haiku to select workflow
        prompt = f"""Analyze task and select ONE workflow:
        {workflows_info}

        Task: "{task_description}"

        Respond with ONLY: code-task, smart-fix, or improve-agent"""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            temperature=0,  # Deterministic
            messages=[{"role": "user", "content": prompt}]
        )

        workflow = response.content[0].text.strip().lower()
        return f"/workflows:{workflow}"
```

**Routing logic:**
- **smart-fix**: Keywords like "fix", "bug", "error", "broken", "not working"
- **improve-agent**: Keywords like "improve", "optimize" + "agent"
- **code-task**: Everything else (safe default)

**Integration:**
- Orchestrator calls router before task creation
- Router returns workflow command (e.g., `/workflows:code-task`)
- Orchestrator executes selected workflow
- User sees transparent experience (no manual selection)

## Consequences

### Positive

- **Intelligent selection**: Leverages Claude's understanding of task intent
- **Natural language**: Users describe tasks naturally
- **Extensible**: Easy to add new workflows (update workflow dict)
- **Deterministic**: temperature=0 ensures consistent routing
- **Fast**: Haiku responds in 1-2 seconds
- **Cheap**: Haiku costs $0.0001/1K tokens (minimal cost)
- **Transparent**: Users don't need to know about workflows
- **Safe fallback**: Defaults to code-task if uncertain

### Negative

- **Added latency**: 1-2 seconds for routing decision
- **API dependency**: Routing fails if Anthropic API is down (falls back to code-task)
- **Potential misrouting**: Wrong workflow selected in edge cases
- **Token costs**: Small but non-zero cost per routing decision
- **Prompt engineering**: Routing quality depends on prompt design

## Alternatives Considered

1. **Static Keyword Matching**
   - Rejected: Too brittle, many edge cases
   - "fix the documentation" would match "fix" → smart-fix (wrong)
   - Hard to maintain as workflows evolve

2. **User Manual Selection**
   - Rejected: Poor UX, requires workflow knowledge
   - Users shouldn't need to know internal architecture
   - Higher cognitive load

3. **Embedding-Based Similarity**
   - Rejected: Overkill for 3 workflows
   - Requires vector database
   - More complex, slower, more expensive

4. **GPT-4/Sonnet for Routing**
   - Rejected: More expensive than Haiku
   - No quality improvement for simple classification
   - Haiku is sufficient

5. **Rule-Based Decision Tree**
   - Rejected: Complex to maintain
   - Doesn't handle nuance well
   - Can't adapt to new patterns

6. **No Router (Always code-task)**
   - Rejected: Misses opportunity for specialized workflows
   - smart-fix and improve-agent wouldn't be used effectively

## Routing Examples

**User input → Selected workflow:**

| Input | Workflow | Reasoning |
|-------|----------|-----------|
| "Fix the login bug" | smart-fix | Contains "fix" + "bug" |
| "Add user registration" | code-task | New feature implementation |
| "Why is the API slow?" | smart-fix | Performance issue |
| "Improve code_agent" | improve-agent | "improve" + "agent" |
| "Refactor auth module" | code-task | Refactoring (general coding) |
| "Create new endpoint" | code-task | New feature |

## Workflow Metadata

**Workflow definitions** (`core/routing.py:21-34`):

```python
available_workflows = {
    "code-task": {
        "description": "General-purpose coding task orchestration. "
                      "Analyzes task, routes to appropriate agents, "
                      "runs QA checks, commits changes.",
        "use_for": "New features, bug fixes, refactoring, "
                   "general development tasks"
    },
    "smart-fix": {
        "description": "Intelligent issue resolution with automatic "
                      "agent selection. Escalates to deep debugging "
                      "for complex issues.",
        "use_for": "Bugs, errors, crashes, performance problems, "
                   "security issues, broken functionality"
    },
    "improve-agent": {
        "description": "Analyzes agent performance from logs, "
                      "identifies patterns in failures, "
                      "updates agent configuration.",
        "use_for": "Improving existing agent behavior, "
                   "fixing agent issues, optimizing performance"
    }
}
```

## Adding New Workflows

**Process:**
1. Create workflow file in `.claude/workflows/`
2. Add entry to `available_workflows` dict
3. Update routing prompt if needed
4. Test routing with example inputs

**Example:**
```python
available_workflows["security-audit"] = {
    "description": "Security-focused code analysis...",
    "use_for": "Security reviews, vulnerability scanning..."
}
```

## References

- Implementation: `core/routing.py:16-114`
- Workflow definitions: `core/routing.py:21-34`
- Routing logic: `core/routing.py:36-102`
- Singleton instance: `core/routing.py:105-114`
- Usage in orchestrator: `core/orchestrator.py` (calls `get_workflow_router()`)
- Workflow files: `.claude/workflows/` (code-task.md, smart-fix.md, etc.)
- Related: ADR 0001 (Agent Routing Strategy) for model selection
