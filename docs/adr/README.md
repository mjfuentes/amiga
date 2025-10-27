# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the AMIGA project.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences.

## ADR Format

Each ADR follows this structure:

```markdown
# [Number]. [Title]

Date: YYYY-MM-DD

## Status

Accepted | Superseded | Deprecated

## Context

What is the issue we're trying to solve? What are the constraints and driving factors?

## Decision

What did we decide to do? What is the architectural choice?

## Consequences

What becomes easier or harder as a result of this decision?

### Positive
- Benefit 1
- Benefit 2

### Negative
- Tradeoff 1
- Tradeoff 2

## Alternatives Considered

1. **Option A**: Why it was rejected
2. **Option B**: Why it was rejected

## References

- Related code: file.py:line
- Related docs: docs/ARCHITECTURE.md
```

## Naming Convention

ADRs are numbered sequentially and use descriptive titles:
- `0001-agent-routing-strategy.md`
- `0002-task-pool-architecture.md`
- etc.

## When to Create an ADR

Create an ADR when:
- Making a significant architectural choice
- Changing a major system component
- Selecting between multiple technical approaches
- Making decisions that will impact future development

## List of ADRs

1. [Agent Routing Strategy](0001-agent-routing-strategy.md) - Route Q&A to Haiku, coding to Sonnet
2. [Task Pool Architecture](0002-task-pool-architecture.md) - Bounded pool with 3 workers
3. [Per-User Message Queue](0003-per-user-message-queue.md) - Serialize messages per user
4. [Git Worktree Isolation](0004-git-worktree-isolation.md) - Use worktrees for concurrent tasks
5. [SQLite for Persistence](0005-sqlite-for-persistence.md) - SQLite instead of PostgreSQL
6. [Monitoring with Hooks](0006-monitoring-with-hooks.md) - Use Claude Code hooks for tracking
7. [Cost Tracking Architecture](0007-cost-tracking-architecture.md) - Track costs in JSON with limits
8. [Session Management](0008-session-management.md) - In-memory sessions with persistence
9. [Workflow Router System](0009-workflow-router-system.md) - Intelligent workflow selection via Claude API
10. [Priority Queue Enhancement](0010-priority-queue-enhancement.md) - Priority-based task execution
