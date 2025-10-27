---
model: claude-opus-4-20250514
---

Improve an existing agent based on recent performance:

[Extended thinking: Analyzes agent performance from session logs, identifies patterns in failures or suboptimal outputs, and updates agent prompts with improved examples and instructions.]

## Agent Improvement Process

Analyze and improve the agent: **$ARGUMENTS**

### 1. Analyze Recent Performance

Examine recent uses of the specified agent:

- Use Task tool with subagent_type="research_agent"
- Prompt: "Analyze recent performance of the $ARGUMENTS agent. Search for:
  1. Session logs in logs/sessions/ directory
  2. Tool usage patterns in data/tool_usage.json
  3. Task outcomes in data/tasks.json
  4. Agent status in data/agent_status.json

  Identify patterns in:
  - Failed or incomplete tasks
  - User corrections or follow-up requests
  - Suboptimal outputs (inefficient solutions, over-engineering)
  - Common error patterns
  - Successful patterns that work well

  Provide analysis report with specific examples."

### 2. Review Current Agent Configuration

Read the current agent file:

- Use Read tool to examine `.claude/agents/$ARGUMENTS.md`
- Extract current:
  - Model specification
  - Instructions and constraints
  - Example prompts
  - Tool restrictions
  - Cost optimization notes

### 3. Identify Improvement Opportunities

Based on analysis, determine improvements:

**Common Issues to Address:**
- Insufficient error handling guidance
- Unclear instructions leading to ambiguity
- Missing examples for edge cases
- Overly broad tool permissions
- Cost inefficiencies (using expensive models unnecessarily)
- Lack of domain-specific knowledge
- Poor integration with other agents

**Improvement Categories:**
- **Clarity**: Make instructions more specific and unambiguous
- **Examples**: Add concrete examples of good/bad outputs
- **Constraints**: Define boundaries and limitations
- **Error Handling**: Provide guidance for failure scenarios
- **Cost Optimization**: Reduce unnecessary API calls or model usage
- **Integration**: Improve coordination with other agents

### 4. Update Agent Configuration

Create improved version of the agent:

- Use Edit tool to update `.claude/agents/$ARGUMENTS.md`
- Apply improvements identified in analysis
- Maintain backward compatibility where possible

**Update Structure:**
```markdown
---
model: [appropriate model based on complexity]
---

[Clear, specific description of agent purpose]

[Extended thinking: Rationale for agent design and approach]

## Instructions

[Improved, specific instructions]

## Examples

[Concrete examples from real usage]

## Error Handling

[Guidance for failure scenarios]

## Integration

[How this agent works with other agents]

## Cost Optimization

[When to use this agent, when to delegate]
```

### 5. Test Improved Agent

Validate improvements on recent failure scenarios:

- Use Task tool with the updated agent
- Prompt: "Test the improved $ARGUMENTS agent on these recent failure scenarios: [list scenarios from analysis]

  Verify:
  1. Previous failures now succeed
  2. No regression in successful cases
  3. Better efficiency (fewer tool calls, faster execution)
  4. Clearer outputs

  Provide test results."

### 6. Document Changes

Create changelog entry:

- Use Write tool to update `.claude/agents/CHANGELOG.md`
- Document:
  - What was changed
  - Why it was changed
  - Impact on existing workflows
  - Breaking changes (if any)

**Changelog Format:**
```markdown
## [Agent Name] - [Date]

### Improvements
- [Improvement 1]: [Description and rationale]
- [Improvement 2]: [Description and rationale]

### Fixed Issues
- [Issue 1]: [How it was addressed]
- [Issue 2]: [How it was addressed]

### Examples Added
- [Example scenario]: [What was added]

### Performance Impact
- Token usage: [Change]
- Success rate: [Change]
- Average duration: [Change]
```

### 7. Commit Changes

**CRITICAL**: Commit the improved agent configuration:

```bash
git add .claude/agents/$ARGUMENTS.md .claude/agents/CHANGELOG.md
git commit -m "Improve $ARGUMENTS agent based on performance analysis

Analysis findings:
- [Key finding 1]
- [Key finding 2]

Improvements:
- [Improvement 1]
- [Improvement 2]

Impact:
- [Expected improvement]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### 8. Merge to Main

**FINAL STEP - ALWAYS RUN**:

- Use Task tool with subagent_type="git-merge"
- Prompt: "Merge task branch to main"
- **CRITICAL**: Ensures agent improvements are integrated into main branch
- **Note**: Worktree cleanup disabled - preserved for debugging (manual cleanup available if needed)

## Execution Notes

- Use research_agent (Opus) for analysis - justifies cost with comprehensive insights
- Test improvements before committing
- Document rationale for changes
- Consider impact on existing workflows
- Update related documentation if needed

Agent to improve: $ARGUMENTS
