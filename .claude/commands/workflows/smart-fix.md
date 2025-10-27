---
model: claude-sonnet-4-5-20250929
---

Intelligently fix issues using automatic agent selection:

[Extended thinking: This workflow IS the orchestrator for bug fixes. Analyzes issue domain and severity, then directly invokes the most appropriate specialist agent. Complex/critical issues escalate to ultrathink-debugger (Opus). Standard issues use code_agent (Sonnet) for cost efficiency. No redundant orchestrator layer.]

## Issue Analysis Phase

Examine the issue: **$ARGUMENTS**

Determine:
1. **Problem Domain**: Code error, performance, deployment, security, integration
2. **Severity**: Critical (production down), High (major breakage), Medium (partial impact), Low (minor issue)
3. **Scope**: Localized (single file), Module (related files), System (multiple components)
4. **Complexity**: Simple (known pattern), Moderate (needs investigation), Complex (distributed/timing)

## Agent Selection and Execution

### For Critical/Complex Issues (Severity: Critical/High + Scope: System + Complexity: Complex)

**Escalate to deep debugging:**

- Use Task tool with subagent_type="ultrathink-debugger"
- Prompt: "Perform deep root cause analysis for critical issue: $ARGUMENTS

  Required analysis:
  - Trace execution paths across components
  - Identify underlying causes (not symptoms)
  - Consider timing, concurrency, distributed system effects
  - Propose robust fix preventing recurrence
  - Address edge cases and failure modes

  Critical issue analysis - use full Opus capabilities."

**Cost Warning**: ultrathink-debugger uses Opus 4.5 - expensive but comprehensive.

**When to use**:
- Multiple failed fix attempts
- Production incidents with unclear cause
- Intermittent/timing-related bugs
- Distributed system failures
- Security vulnerabilities requiring deep analysis

### For Deployment/Infrastructure Issues

**Route to code execution:**

- Use Task tool with subagent_type="code_agent"
- Prompt: "Debug and fix deployment/infrastructure issue: $ARGUMENTS

  Investigation checklist:
  - Environment variables and configuration
  - Service connectivity and dependencies
  - Initialization errors in logs
  - Permissions and resource limits
  - Container/process health checks

  Implement fix with:
  - Configuration validation
  - Health check improvements
  - Error logging enhancement
  - Deployment verification

  CRITICAL: Commit fixes with detailed explanation."

### For Code Errors and Logic Bugs

**Standard debugging:**

- Use Task tool with subagent_type="code_agent"
- Prompt: "Debug and fix code error: $ARGUMENTS

  Debug process:
  1. Analyze stack trace/error message
  2. Identify root cause (not symptom)
  3. Implement fix with proper error handling
  4. Add logging for future debugging
  5. Create test case to prevent regression

  Follow AgentLab conventions:
  - Black formatting, type hints
  - Comprehensive error handling
  - Logging at appropriate levels

  CRITICAL: Commit with descriptive message including root cause."

### For Performance Issues

**Performance optimization:**

- Use Task tool with subagent_type="code_agent"
- Prompt: "Optimize performance issue: $ARGUMENTS

  Performance analysis:
  - Profile and identify bottlenecks
  - Measure baseline performance
  - Consider caching opportunities
  - Optimize database queries (indexes, N+1)
  - Evaluate async/parallel execution

  Implementation:
  - Make targeted optimizations
  - Measure improvement (before/after)
  - Document performance gains
  - Avoid premature optimization

  CRITICAL: Commit with performance metrics."

### For Security Issues

**Security fix (high priority):**

- Use Task tool with subagent_type="code_agent"
- Prompt: "Fix security issue with priority: $ARGUMENTS

  Security assessment:
  1. Identify vulnerability type (injection, XSS, CSRF, auth bypass, etc.)
  2. Assess impact and attack vectors
  3. Search for similar issues in codebase

  Remediation:
  - Implement secure fix following OWASP guidelines
  - Add input validation and sanitization
  - Review authentication/authorization logic
  - Update dependencies if CVE-related
  - Add security tests

  CRITICAL: Commit security fixes immediately with detailed explanation."

### For Integration/API Issues

**Integration debugging:**

- Use Task tool with subagent_type="code_agent"
- Prompt: "Fix integration/API issue: $ARGUMENTS

  Troubleshooting:
  - Verify endpoint availability and authentication
  - Check request/response format and headers
  - Test with actual API (if available)
  - Review API documentation/contract

  Implementation:
  - Add retry logic with exponential backoff
  - Implement circuit breaker pattern
  - Enhance error handling and logging
  - Add integration tests with mocking

  CRITICAL: Commit with integration details."

### For Telegram Bot Issues (Special Case)

**Bot-specific debugging:**

- Use Task tool with subagent_type="code_agent"
- Prompt: "Fix Telegram bot issue: $ARGUMENTS

  Context: This is the Telegram bot codebase at /Users/matifuentes/Workspace/agentlab
  When debugging 'the bot', 'your code', 'this bot' - refers to AgentLab bot.

  Bot-specific checks:
  - Telegram API rate limits (30/min per user, 500/hr global)
  - Message queue serialization
  - Session management and cleanup
  - Background task coordination
  - Hook system logging

  Common issues:
  - Message chunking (4096 char limit)
  - Voice transcription accuracy
  - Cost tracking accuracy
  - Agent pool saturation

  CRITICAL: Test fix with real Telegram interaction if possible."

## Validation Phase

After implementing fix:

### 1. Verify Fix Works

- Use Task tool with subagent_type="task-completion-validator"
- Prompt: "Verify that fix for '$ARGUMENTS' actually resolves the issue and introduces no regressions.

  Validation checklist:
  - Original issue resolved
  - No new errors introduced
  - Related functionality still works
  - Performance not degraded
  - Edge cases handled"

### 2. Reality Check

- Use Task tool with subagent_type="karen"
- Prompt: "Reality check on fix for '$ARGUMENTS': Is this actually complete or just a temporary band-aid?

  Honest assessment:
  - Root cause addressed (not symptom)
  - Long-term solution (not quick hack)
  - Technical debt considered
  - Future-proof implementation"

## Documentation Phase

Create root cause analysis:

**Format:**
```markdown
## Issue: [Brief description]

**Root Cause**: [Why it happened - be specific]

**Fix**: [What was changed - files, logic, approach]

**Prevention**: [How to avoid in future - tests, checks, refactoring]

**Files Modified**:
- file1.py:123 - [Change description]
- file2.py:456 - [Change description]

**Testing**: [How to verify fix works]
```

## Commit Verification

**CRITICAL**: Ensure fix is committed with descriptive message:

```bash
git commit -m "Fix: [Brief description of issue]

Root cause: [One line explanation]
Solution: [What was changed]

Impact: [What this fixes, any side effects]

Fixes: #[issue number if applicable]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## Merge to Main

**FINAL STEP - ALWAYS RUN**:

- Use Task tool with subagent_type="git-merge"
- Prompt: "Merge task branch to main"
- **CRITICAL**: Ensures fix is integrated into main branch
- **Note**: Worktree cleanup disabled - preserved for debugging (manual cleanup available if needed)

## Multi-Domain Issues

For issues spanning multiple domains:
1. Start with primary agent for main symptom
2. Coordinate secondary agents for related aspects
3. Ensure fixes integrate properly
4. Test end-to-end functionality
5. Consider system-wide impact

## Cost Optimization Strategy

**Start cheap, escalate when needed:**

1. **First attempt**: code_agent (Sonnet) - covers 90% of issues
2. **Escalate if**: Multiple failures, complex distributed issue, timing bugs
3. **Use Opus only when**: Genuinely requires deep reasoning and comprehensive analysis

**Escalation triggers:**
- 2+ failed fix attempts
- Issue involves multiple services/components
- Intermittent or timing-dependent
- Security incident requiring thorough analysis
- Production impact with unclear root cause

Issue to fix: $ARGUMENTS
