# 1. Agent Routing Strategy

Date: 2025-01-15

## Status

Accepted

## Context

The Telegram bot needs to handle two distinct types of user requests:
1. **Q&A queries**: Simple questions, information requests, general conversation
2. **Coding tasks**: Complex code changes, bug fixes, feature implementations

Using a single Claude model for both creates suboptimal outcomes:
- Using Sonnet for Q&A is expensive and slow (overkill for simple questions)
- Using Haiku for coding produces lower quality code (insufficient capability)
- Token costs vary dramatically: Haiku is 10x cheaper than Sonnet

We need an intelligent routing system that selects the right model for each task.

## Decision

Implement a two-tier routing strategy:

1. **Claude API (Haiku 4.5)** for Q&A and routing decisions
   - Handles simple questions and conversations
   - Makes workflow routing decisions (via `WorkflowRouter`)
   - Fast response times (1-2 seconds)
   - Low cost ($0.0001/1K input tokens)

2. **Claude Code CLI (Sonnet 4.5)** for coding tasks
   - Full tool access (Read, Write, Edit, Bash, etc.)
   - Handles complex implementations
   - Slower but more thorough (5-60 seconds)
   - Higher cost but justified by capability

**Routing logic** (implemented in `core/routing.py`):
- Uses Claude Haiku to analyze user input and select workflow
- Intelligent keyword detection ("fix", "bug", "create", "implement")
- Defaults to code-task workflow for general development

**Implementation:**
- `core/routing.py:36-102` - WorkflowRouter class
- Uses Claude Haiku 4.5 API with temperature=0 for deterministic routing
- Returns workflow command: `/workflows:code-task`, `/workflows:smart-fix`, etc.

## Consequences

### Positive

- **10x cost reduction** for Q&A interactions (Haiku vs Sonnet)
- **Faster responses** for simple queries (1-2s vs 5-30s)
- **Better code quality** for complex tasks (Sonnet vs Haiku)
- **Intelligent workflow selection** adapts to user intent
- **Scalable** - can add more specialized workflows easily

### Negative

- **Additional routing latency** (1-2s) for all requests due to Haiku API call
- **Two systems to maintain** - Claude API client + Claude Code CLI wrapper
- **Potential misrouting** if routing logic is imperfect (mitigated by conservative defaults)
- **Complexity** in session management across two different interfaces

## Alternatives Considered

1. **Single Model Approach (Sonnet only)**
   - Rejected: Too expensive for Q&A ($1-2/day for typical usage)
   - Simple but cost-prohibitive at scale

2. **Single Model Approach (Haiku only)**
   - Rejected: Insufficient quality for complex coding tasks
   - Would require human intervention for difficult problems

3. **Manual User Selection (/haiku vs /sonnet commands)**
   - Rejected: Poor UX, users shouldn't need to understand model differences
   - Adds cognitive load and decision fatigue

4. **Static Keyword Routing**
   - Rejected: Too brittle, many edge cases ("fix the documentation" != bug fix)
   - Hard to maintain as patterns evolve

5. **Embedding-Based Similarity**
   - Rejected: Overkill for this use case, requires vector database
   - Adds infrastructure complexity

## References

- Implementation: `core/routing.py:36-102`
- Claude API Client: `claude/api_client.py`
- Claude Code CLI: `claude/code_cli.py`
- Architecture doc: `docs/ARCHITECTURE.md`
- Project philosophy: `CLAUDE.md` - "Right model for the right task"
