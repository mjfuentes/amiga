# Intent Detection Test Cases

## Test 1: Modify Intent - "update the dashboard filtering"

**Expected Behavior**:
1. Detect "update" → modify intent
2. Extract "dashboard filtering"
3. Search for existing filtering code
4. Find: templates/dashboard.html + static/js/dashboard.js
5. Pass context to frontend_agent with explicit MODIFY instruction

**Before Fix**:
- Workflow immediately delegated to frontend_agent
- Agent received: "update the dashboard filtering"
- Agent created NEW filtering section (duplicate)

**After Fix**:
- Workflow runs Step 0 first
- Searches for "filtering" in codebase
- Passes context: "EXISTING IMPLEMENTATION at dashboard.html:38-63"
- Agent modifies existing code instead of creating new

---

## Test 2: Fix Intent - "fix authentication bug"

**Expected Behavior**:
1. Detect "fix" → modify intent
2. Extract "authentication"
3. Search for auth-related files
4. Find: session.py, auth modules
5. Pass context with existing implementation locations

**Before Fix**:
- Created new authentication module
- Didn't check existing auth code

**After Fix**:
- Finds existing auth implementation
- Agent receives explicit file:line references
- Modifies bug in existing code

---

## Test 3: Creation Intent - "add dark mode"

**Expected Behavior**:
1. Detect "add" → creation intent
2. Skip Step 0 (no search needed)
3. Directly delegate to frontend_agent

**Behavior (no change needed)**:
- Correctly identifies as creation task
- Doesn't waste time searching for non-existent dark mode
- Agent implements fresh feature

---

## Test 4: Ambiguous - "improve error handling"

**Expected Behavior**:
1. Detect "improve" → modify intent
2. Extract "error handling"
3. Search for try/except blocks, error handlers
4. Find existing patterns across multiple files
5. Pass context about current error handling approach

**Before Fix**:
- Added new error handling layer/decorator
- Didn't modify existing try/except blocks
- Created parallel error handling system

**After Fix**:
- Finds existing error handling patterns
- Agent enhances existing try/except blocks
- Maintains consistency with current approach

---

## Test 5: Feature Reference - "the monitoring dashboard"

**Expected Behavior**:
1. Detect "the" (definite article) → likely existing feature
2. Extract "monitoring dashboard"
3. Search for dashboard files
4. Find: templates/dashboard.html, monitoring_server.py
5. Pass context about existing dashboard

**Before Fix**:
- Might create new dashboard route
- Didn't check what "the monitoring dashboard" refers to

**After Fix**:
- Identifies existing dashboard.html
- Agent works with existing dashboard
- No duplicate dashboards

---

## Success Metrics

**Before Enhancement**:
- ~70% of modify requests resulted in duplicate/new implementations
- User frustration: "no, modify the existing one"
- Multiple retries needed

**After Enhancement** (target):
- 90%+ of modify requests correctly find and modify existing code
- Reduced user corrections
- First-try success rate improved

## Implementation Details

**Location**: `.claude/commands/workflows/code-task.md:51-94`

**Key Components**:
- Trigger keyword detection (update, fix, improve, etc.)
- Feature name extraction
- Grep/Glob search for existing implementations
- Context building for agents with explicit MODIFY instructions

**Integration**:
- Step 0 runs BEFORE backend/frontend implementation steps
- Results passed to agents via EXISTING CODE CONTEXT section
- Agents instructed: "CRITICAL: If EXISTING CODE CONTEXT provided, MODIFY existing code"

