# Research Documents

Research documents for implementation tasks.

## Workflow

**1. Research Agent** (Comprehensive Research)
- Spawned by orchestrator for feature research
- Tools: Read, Glob, Grep, WebSearch, WebFetch
- **Online research**: Searches docs, comparisons, tutorials (3+ sources, 2024-2025)
- **Code analysis**: Analyzes existing code extensively
- **Comparative evaluation**: Compares 2-3 approaches
- Returns comprehensive proposal combining online + code analysis

**2. Orchestrator** (Document Saving)
- Receives full research proposal from research agent
- Saves to `research/{task_id}_research.md`
- Provides task ID to code agent

**3. Code Agent** (Implementation)
- Reads `research/{task_id}_research.md` first
- Follows recommendations and code templates
- References research in commits

## Structure

- Each document named: `{task_id}_research.md`
- Task ID format: `{type}-{brief-name}`
  - Examples: `feature-voice`, `library-websockets`, `api-stripe`, `refactor-routing`

## Document Template

```markdown
# Research: [Feature Name]

**Task ID**: {task_id}
**Date**: YYYY-MM-DD
**Sources**: Online Research + Code Analysis

---

## Executive Summary
[2-3 sentences with clear recommendation]

## Online Research

### Source 1: [Official Documentation]
- **URL**: https://...
- **Credibility**: ⭐⭐⭐⭐⭐
- **Date**: 2024-2025
- **Key Findings**: ...

### Source 2: [Comparison/Tutorial]
- **URL**: https://...
- **Key Findings**: ...

### Source 3: [GitHub/Blog]
- **URL**: https://...
- **Key Findings**: ...

## Current Implementation Analysis
### Relevant Files
- `file.py:123` - Description

### Integration Points
[Where feature connects]

## Approach Comparison
| Criteria | Option A | Option B | Option C |
|----------|----------|----------|----------|
| ... | ... | ... | ... |

**Recommendation**: ✅ Option X - [Reasoning]

## Implementation Plan
1. Step 1 (X min)
2. Step 2 (X min)
...

**Total**: ~X hours

## Code Templates
```python
# Implementation following existing patterns
```

## Security Considerations
- [ ] Checks...

## Testing Strategy
- Unit tests
- Integration tests
- Manual testing

## References
### Online Sources
- [Docs](url)
- [Tutorial](url)

### Code Analysis
- `file.py:line`
```

## Example

WebSocket research from testing:
- Task ID: `feature-websocket-support`
- **Online research**: Flask-SocketIO docs, comparisons, alternatives
- **Code analysis**: `monitoring_server.py` SSE implementation
- **Comparison**: Flask-SocketIO vs websockets vs python-socketio
- **Recommendation**: Flask-SocketIO (best Flask integration)
- **Result**: Full code templates, 9-12hr estimate

## Best Practices

**Research Agent**:
- ✅ Online research (3+ sources, 2024-2025, with URLs)
- ✅ Deep code analysis (file:line refs)
- ✅ Compare 2-3 approaches
- ✅ Code templates from existing patterns
- ✅ Realistic time estimates
- ✅ Credibility ratings for sources

**Orchestrator**:
- ✅ Receive research from research agent
- ✅ Save to `research/{task_id}_research.md`
- ✅ Pass task ID to code agent

**Code Agent**:
- ✅ Read research FIRST
- ✅ Follow recommendations
- ✅ Use code templates
- ✅ Reference research in commits

---

**Purpose**: Separate research from implementation for better decisions and consistent patterns.
