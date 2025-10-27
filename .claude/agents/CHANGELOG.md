# Agent Configuration Changelog

This file tracks changes to agent configurations in `.claude/agents/`.

---

## [orchestrator, code_agent] - 2025-10-27 - Self-Improvement

### Error Analysis
- Analyzed 78 failed tasks from last 7 days
- Analyzed 2,322 failed tool executions
- Identified 3 critical error patterns affecting system reliability

### Error Patterns Identified

**Pattern 1: Task Worker Pool Failures (87% of failed tasks)**
- 68 of 78 failed tasks stuck in pending state or never picked up by worker
- Root cause: CODE ISSUE - Task manager/worker pool submission/processing bugs
- Action: Task created for code fix

**Pattern 2: Unknown Tool Errors (43.4% of tool failures)**
- 1,007 tool executions returning "unknown_error" category
- Top tools affected: Bash (391), Read (347), Edit (99), Grep (82)
- Root cause: PROMPT ISSUE - Scripts writing errors to stdout instead of stderr
- Action: Updated agent prompts with guidance

**Pattern 3: Timeout Errors (14.3% of tool failures)**
- 332 tool executions timing out (Edit: 229, Read: 79)
- Root cause: PROMPT ISSUE - Large file operations without chunking strategy
- Action: Updated agent prompts with best practices

### Prompt Updates

**orchestrator.md**:
- Added "Common Error Scenarios" section
- Added guidance for "Claude produced no output" errors
- Added instructions for handling large file timeouts with chunking strategy
- Added examples of correct vs incorrect approaches for large files

**code_agent.md**:
- Added "Common Error Scenarios" section
- Added Edit/Read timeout prevention with Grep+offset/limit strategy
- Added tool error detection guidance (unknown_error category)
- Added examples showing proper file chunking approach

### Expected Impact
- Reduce timeout errors by ~60% through proper file chunking
- Improve error diagnosis with better stdout/stderr handling
- Task worker pool issue tracked for code-level fix
- Better agent understanding of error scenarios and recovery steps

---

## [orchestrator] - 2025-10-21

### Improvements
- **Forbidden Tools Section**: Added explicit list of forbidden tools to prevent direct execution violations
- **Task Recognition Patterns**: Added patterns to identify when to use expensive agents (research_agent, ultrathink-debugger) and when to route to workflows
- **Delegation Policy Enforcement**: Removed ability to do "simple file reads" - now ONLY Task and TodoWrite allowed
- **Automatic QA Triggers**: Added rules for automatic quality assurance based on file size, complexity, and task type
- **Error Handling**: Added structured approach for handling agent failures and recommendations
- **Context Passing Examples**: Added concrete examples of good vs bad context passing between agents

### Fixed Issues
- **Workflow Routing**: Added patterns to properly route agent improvement tasks to `/workflows:improve-agent`
- **Direct Execution Violations**: Orchestrator was using Read/Grep tools directly instead of delegating
- **Research Agent Underutilization**: Added trigger patterns for research-worthy tasks
- **Missing Follow-up Tasks**: Added rule to create implementation tasks when agents provide recommendations

### Examples Added
- Good vs bad context passing between agents
- Specific error handling scenarios
- Task recognition patterns for expensive agents

### Performance Impact
- Token usage: Reduced by preventing redundant direct tool usage
- Success rate: Expected +5% from better routing and error handling
- Average duration: Faster task completion through proper delegation