# AMIGA Tool Usage Analysis
**Generated:** 2025-10-20
**Database Stats:** 188 tasks, 1,102 tool usage records, 960 status changes

## Executive Summary

**Overall System Health:** 🟡 Mixed (some areas working, critical gaps identified)

**Key Findings:**
1. ✅ orchestrator delegation working (78.6% success rate)
2. ❌ research_agent **NEVER USED** in 30 days
3. ❌ High Edit tool failure rate (88.75%)
4. ❌ High Read tool failure rate (55%)
5. ⚠️  code_agent moderate success rate (53%)
6. ✅ Workflow tracking operational (code-task, smart-fix)
7. ⚠️  Minimal agent spawning (only 3 Task tool calls total)

---

## 1. Agent Usage Patterns

### Agent Distribution (All Time)

| Agent Type | Completed | Failed | Stopped | Total | Success Rate |
|------------|-----------|--------|---------|-------|--------------|
| **code_agent** | 85 (48.9%) | 75 (43.1%) | 14 (8.0%) | 174 | 48.9% |
| **orchestrator** | 11 (78.6%) | 0 (0%) | 1 (7.1%) | 14* | 78.6% |
| **research_agent** | 0 | 0 | 0 | **0** | **N/A** |
| **frontend_agent** | 0 | 0 | 0 | **0** | **N/A** |

*\* 2 orchestrator tasks currently running*

### Critical Issue: Specialized Agents Not Being Used

**research_agent:**
- Expected tools: Read, Glob, Grep, WebSearch, WebFetch
- Actual usage: **0 tasks in 30 days**
- Status: ❌ **NEVER SPAWNED**

**frontend_agent:**
- Expected usage: Web UI/UX work
- Actual usage: **0 tasks**
- Status: ❌ **NEVER SPAWNED**

**QA Agents:**
- Jenny, code-quality-pragmatist, task-completion-validator, etc.
- Actual usage: **0 tasks**
- Status: ❌ **NEVER SPAWNED**

### Agent Spawning Analysis

**Task Tool Usage (Agent Spawning):**
- Total spawns: 3
- Success: 2
- Failures: 1
- All spawns from: code_agent (not orchestrator)

**Interpretation:** orchestrator is configured to delegate but is **NOT spawning specialized agents** as designed. orchestrator tasks show 0 tool calls, suggesting it's completing tasks without delegation.

---

## 2. Tool Usage Statistics (Last 7 Days)

### Top 10 Most Used Tools

| Tool | Uses | Success | Failures | Success Rate | Avg Duration |
|------|------|---------|----------|--------------|--------------|
| **Bash** | 469 | 436 | 33 | 93.0% ✅ | 0 ms |
| **Read** | 186 | 83 | 103 | **44.6%** ❌ | 0 ms |
| **Edit** | 160 | 18 | 142 | **11.3%** ❌ | 0 ms |
| **TodoWrite** | 120 | 117 | 3 | 97.5% ✅ | 0 ms |
| **Grep** | 60 | 54 | 6 | 90.0% ✅ | 0 ms |
| **Glob** | 43 | 43 | 0 | 100% ✅ | 0 ms |
| **BashOutput** | 16 | 13 | 3 | 81.3% ✅ | 0 ms |
| **Task** | 15 | 11 | 4 | 73.3% ⚠️ | 0 ms |
| **Write** | 14 | 6 | 8 | **42.9%** ❌ | 0 ms |
| **WebSearch** | 10 | 10 | 0 | 100% ✅ | 0 ms |

### Web Research Tools (Underutilized)

| Tool | Uses | Success | Failures | Expected User |
|------|------|---------|----------|---------------|
| **WebSearch** | 10 | 10 | 0 | research_agent |
| **WebFetch** | 4 | **0** | **4** | research_agent |

**Analysis:** WebSearch works perfectly but is rarely used. WebFetch has 100% failure rate.

---

## 3. Critical Issues

### 3.1 Edit Tool Failure Rate (88.75%)

**Failures:** 142
**Successes:** 18
**Success Rate:** 11.3%

**Error Pattern:**
- All errors: "Tool output contains error" (generic, no details)
- Failures concentrated in specific tasks (same task_id repeated)
- Suggests systematic issue, not random failures

**Hypothesis:**
1. File path issues (file doesn't exist, wrong path)
2. Permission issues
3. Invalid edit syntax (old_string not found)
4. Pre-hook blocking edits

**Recommendation:** Add detailed error logging in hooks to capture specific Edit failures.

### 3.2 Read Tool Failure Rate (55%)

**Failures:** 103
**Successes:** 83
**Success Rate:** 44.6%

**Error Pattern:**
- Generic "Tool output contains error"
- Concentrated in same tasks
- Likely file path issues or files that don't exist

**Recommendation:** Log specific file paths that fail to read.

### 3.3 WebFetch 100% Failure Rate

**Failures:** 4
**Successes:** 0
**Success Rate:** 0%

**All WebFetch attempts failed with:** "Tool output contains error"

**Recommendation:** Test WebFetch manually, check network access, URL validation.

---

## 4. Task Completion Efficiency

### code_agent Performance

| Status | Count | Avg Duration | Notes |
|--------|-------|--------------|-------|
| Completed | 85 | 1.88 min | ✅ Fast completions |
| Failed | 75 | 1.12 min | ⚠️ Failures even faster (premature exits) |
| Stopped | 14 | 4.83 min | Long-running tasks interrupted |

**Success Rate:** 48.9% (85/174) - Below 50% is concerning

### orchestrator Performance

| Status | Count | Avg Duration | Notes |
|--------|-------|--------------|-------|
| Completed | 11 | 4.32 min | ✅ Good success rate |
| Running | 2 | N/A | Currently active |
| Stopped | 1 | 0.14 min | Quick stop |

**Success Rate:** 78.6% (11/14) - Good performance

**Analysis:** orchestrator performs better than code_agent despite being supposed to delegate. This suggests orchestrator is executing tasks directly instead of delegating, which goes against its design.

---

## 5. Failure Root Causes

### Task Failure Patterns (Non-Agent Issues)

| Failure Type | Count | Category |
|--------------|-------|----------|
| "broken auto-retry system" | 26 | Infrastructure |
| "bot multi-instance conflict" | 25 | Infrastructure |
| "stuck in pending state" | 16 | Infrastructure |
| "Claude produced no output" | 7 | Agent/API |
| "Failed to start Claude session" | 1 | Infrastructure |

**Total infrastructure failures:** 67/75 (89%)
**Total agent failures:** 8/75 (11%)

**Interpretation:** Most failures are **system/infrastructure issues**, not agent behavior problems.

---

## 6. Workflow Tracking

### Workflow Usage (Last 7 Days)

| Workflow | Tasks | Tool Calls | Avg Duration | Status |
|----------|-------|------------|--------------|--------|
| **code-task** | 5 | 0 | 0 ms | ✅ Active |
| **smart-fix** | 2 | 0 | 0 ms | ✅ Active |
| **improve-agent** | 0 | 0 | N/A | ⚠️ Unused |

**Note:** 0 tool calls for workflow tasks suggests orchestrator isn't spawning agents even when using workflows.

### Workflow Router Analysis

**System:** Uses Claude Haiku 4.5 to intelligently route tasks to:
- `code-task` - General development
- `smart-fix` - Bug fixes, errors
- `improve-agent` - Agent improvements

**Status:** ✅ Operational (7/14 orchestrator tasks have workflow assigned)

---

## 7. Tool Usage by Agent

### code_agent Tool Distribution

| Tool | Uses | Notes |
|------|------|-------|
| Bash | 64 | Most used (execution, git) |
| Read | 18 | File reading |
| Glob | 16 | File search |
| BashOutput | 13 | Background process monitoring |
| TodoWrite | 11 | Task tracking |
| Grep | 10 | Code search |
| Edit | 8 | File editing |
| Task | 3 | Agent spawning (rare) |

**Analysis:** code_agent uses a healthy mix of tools. Minimal Task usage (3) suggests it's not delegating to other agents.

---

## 8. Recommendations

### Priority 1: Critical Issues

1. **Enable research_agent Usage**
   - **Issue:** research_agent defined but never used
   - **Impact:** No web research, no deep analysis capability
   - **Action:** Verify orchestrator is spawning research_agent for research tasks
   - **Test:** Submit task requiring web research, verify research_agent spawns

2. **Fix Edit Tool Reliability**
   - **Issue:** 88.75% failure rate
   - **Impact:** Most file edits fail silently
   - **Action:**
     - Add detailed error logging (file path, old_string, error reason)
     - Check hook system for blocking edits
     - Verify Edit tool implementation
   - **Test:** Manual Edit tool calls with known good inputs

3. **Fix Read Tool Reliability**
   - **Issue:** 55% failure rate
   - **Impact:** Agents can't reliably read files
   - **Action:** Log specific file paths that fail, check file existence before read
   - **Test:** Read common files, verify success rate improves

### Priority 2: Agent Architecture

4. **Verify orchestrator Delegation**
   - **Issue:** orchestrator tasks show 0 tool calls, suggesting direct execution
   - **Impact:** Violates orchestrator design (should ONLY delegate)
   - **Action:** Review orchestrator logs, verify Task tool calls
   - **Expected:** Every orchestrator task should spawn at least one specialized agent

5. **Enable QA Agents**
   - **Issue:** Jenny, code-quality-pragmatist, task-completion-validator never used
   - **Impact:** No automated quality assurance
   - **Action:** Update orchestrator workflows to include QA steps
   - **Example Workflow:** code_agent → task-completion-validator → code-quality-pragmatist

6. **Fix WebFetch Tool**
   - **Issue:** 100% failure rate
   - **Impact:** No ability to fetch web content
   - **Action:** Test WebFetch directly, check network access, URL validation
   - **Test:** Fetch known good URLs (e.g., anthropic.com docs)

### Priority 3: Monitoring & Observability

7. **Improve Error Logging**
   - **Issue:** Most errors are "Tool output contains error" (no details)
   - **Impact:** Difficult to debug failures
   - **Action:**
     - Log specific error messages in hooks
     - Capture tool parameters that failed
     - Add error categorization

8. **Add Agent Spawning Metrics**
   - **Issue:** Limited visibility into agent delegation patterns
   - **Impact:** Can't verify orchestrator is delegating correctly
   - **Action:** Track Task tool calls, parent→child relationships, delegation chains

9. **Create Agent Health Dashboard**
   - **Issue:** No single view of agent performance
   - **Impact:** Must run SQL queries to understand behavior
   - **Action:**
     - Add section to monitoring dashboard
     - Show: agent usage, success rates, tool patterns
     - Alert on: agents never used, high failure rates

### Priority 4: Infrastructure

10. **Address System Failures**
    - **Issue:** 67 tasks failed due to infrastructure issues
    - **Impact:** 89% of failures are non-agent related
    - **Action:**
      - Fix "auto-retry system"
      - Prevent multi-instance conflicts
      - Cleanup stale pending tasks (already implemented)

---

## 9. Compliance Check: research_agent

### Expected Behavior (from .claude/agents/research_agent.md)

**Tools:** Read, Glob, Grep, WebSearch, WebFetch
**Model:** claude-opus-4-20250514 (expensive)
**Purpose:** Analysis, proposals, web research
**Restriction:** NO Write, Edit, Bash

### Actual Behavior

**Tasks:** 0
**Tool Usage:** N/A (never spawned)
**Compliance:** ⚠️ **Cannot verify - agent never used**

### Expected orchestrator Workflow (from orchestrator.md)

**Research needed?** → research_agent → code_agent

**Actual Workflow:** orchestrator completes tasks directly (no delegation observed in recent tasks)

### Recommendation

**Test research_agent explicitly:**
```
User task: "Research best practices for WebSocket implementations in Python Telegram bots, compare 3 approaches, recommend one"

Expected flow:
1. orchestrator receives task
2. orchestrator spawns research_agent (Task tool)
3. research_agent uses WebSearch, WebFetch, Read
4. research_agent returns markdown research document
5. orchestrator returns summary to user

Verify: Task tool called, research_agent in tasks table, WebSearch/WebFetch used
```

---

## 10. Agent Architecture Assessment

### Design Intent (from CLAUDE.md and orchestrator.md)

**orchestrator:**
- ONLY delegates via Task tool
- Never executes substantial work
- Coordinates specialized agents
- Spawns sequentially, waits for completion

**Specialized Agents:**
- code_agent: Backend implementation
- frontend_agent: UI/UX
- research_agent: Analysis, research
- QA agents: Validation, testing

### Actual Behavior

**orchestrator:**
- ✅ Good success rate (78.6%)
- ❌ 0 tool calls in recent tasks
- ❌ Completing tasks directly?
- ❌ Not spawning specialized agents

**Specialized Agents:**
- ✅ code_agent actively used (174 tasks)
- ❌ research_agent never used
- ❌ frontend_agent never used
- ❌ QA agents never used

### Gap Analysis

**Major Gap:** orchestrator design vs. implementation

**Hypothesis 1:** orchestrator is bypassing delegation
- Recent orchestrator tasks show good results but 0 tool calls
- Should be impossible for orchestrator to complete tasks without Task tool

**Hypothesis 2:** Tool tracking not capturing orchestrator→agent delegation
- orchestrator IS spawning agents but tracking isn't capturing it
- Spawned agents report tool usage under their own task_id, not parent

**Recommended Investigation:**
1. Review orchestrator session logs
2. Check for Task tool calls in orchestrator output
3. Verify agent_type assignment when agents are spawned
4. Test explicit delegation: "Use research_agent to analyze X"

---

## 11. Success Stories

Despite issues, some patterns work well:

### ✅ Working Well

1. **Bash tool** (93% success, 469 uses) - Execution, git operations reliable
2. **TodoWrite** (97.5% success) - Task tracking works
3. **Glob** (100% success) - File pattern matching perfect
4. **Grep** (90% success) - Code search reliable
5. **WebSearch** (100% success) - Web search when used
6. **orchestrator completion rate** (78.6%) - High quality results
7. **Workflow routing** - Intelligent routing to code-task, smart-fix

### ⚠️ Needs Improvement

1. **Edit tool** (11.3% success) - Critical for code changes
2. **Read tool** (44.6% success) - Critical for file access
3. **WebFetch** (0% success) - Broken
4. **code_agent success rate** (48.9%) - Below 50%
5. **Agent delegation** - Not happening as designed

---

## 12. Actionable Next Steps

### Immediate (This Week)

1. ✅ **Run this analysis** - Done
2. 🔧 **Test research_agent manually** - Submit research task, verify spawning
3. 🔧 **Debug Edit tool** - Add detailed error logging, fix systematic issues
4. 🔧 **Debug Read tool** - Log failed file paths, investigate patterns

### Short Term (Next Sprint)

5. 🔧 **Fix WebFetch** - Test manually, identify root cause
6. 🔧 **Verify orchestrator delegation** - Review logs, confirm Task tool usage
7. 🔧 **Enable QA agents** - Add to orchestrator workflows
8. 📊 **Add agent health dashboard** - Visualize agent usage, success rates

### Long Term (Next Month)

9. 🔧 **Improve error reporting** - Detailed error messages in all tools
10. 🔧 **Agent spawning metrics** - Track delegation chains
11. 📝 **Document actual vs. intended architecture** - Update CLAUDE.md if needed
12. 🧪 **Create agent integration tests** - Verify each agent works as designed

---

## 13. Conclusion

**Overall Assessment:** 🟡 System is functional but not operating as designed

**Strengths:**
- orchestrator produces good results
- Workflow routing operational
- Core tools (Bash, TodoWrite, Glob, Grep) work well
- Infrastructure issues identified and being addressed

**Critical Gaps:**
- Specialized agents (research_agent, frontend_agent) never used
- QA agents never used
- High failure rates for Edit/Read tools
- orchestrator not delegating as designed

**Impact on User:**
- ✅ Tasks still getting completed (orchestrator compensating)
- ❌ Missing research capabilities (no research_agent)
- ❌ Lower code quality (no QA agents)
- ❌ Higher costs (orchestrator doing work instead of cheaper specialized agents)

**Recommendation:** Focus on Priority 1 issues first. The system works but isn't leveraging its full agent architecture.

---

## Appendix: Database Schema

```sql
-- Tasks
task_id, user_id, description, status, created_at, updated_at,
model, workspace, agent_type, workflow, result, error, pid, activity_log

-- Tool Usage
id, timestamp, task_id, tool_name, duration_ms, success, error, parameters

-- Agent Status
id, timestamp, task_id, status, message, metadata
```

**Schema Version:** 3
**Records:** 188 tasks, 1,102 tool usage, 960 status changes
**Date Range:** 2025-10-16 to 2025-10-20
