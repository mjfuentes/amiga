# Improvement Branches - Quick Reference

**Generated:** October 27, 2025  
**Full Analysis:** See `CODEBASE_IMPROVEMENT_ANALYSIS.md`

---

## Quick Start

All branches are **non-breaking** and can be worked on **in parallel**.

```bash
# Create all branches at once
git checkout main
git pull origin main

# High Priority Branches
git checkout -b docs/add-module-readmes
git checkout main
git checkout -b docs/expand-api-documentation
git checkout main
git checkout -b tests/add-missing-unit-tests
git checkout main
git checkout -b tests/add-integration-tests
git checkout main
git checkout -b refactor/consolidate-database-paths
git checkout main
git checkout -b refactor/centralize-sanitization

# Medium Priority Branches  
git checkout main
git checkout -b refactor/extract-long-functions
git checkout main
git checkout -b refactor/database-singleton
git checkout main
git checkout -b quality/improve-error-handling
git checkout main
git checkout -b tests/improve-coverage-reporting
git checkout main
git checkout -b refactor/centralize-logging

# Low Priority Branches
git checkout main
git checkout -b quality/add-type-hints
git checkout main
git checkout -b security/production-config-checks
git checkout main
git checkout -b docs/add-architecture-decisions

git checkout main
```

---

## Branch Details

### HIGH PRIORITY (Start Here)

#### 1. docs/add-module-readmes (2-3 days)
**Goal:** Add README.md to all top-level modules

**Files to Create:**
```
core/README.md
tasks/README.md
messaging/README.md
utils/README.md
claude/README.md
monitoring/README.md
scripts/README.md
```

**Template:**
```markdown
# [Module Name]

## Purpose
Brief description of module's responsibility

## Components
- file1.py - Description
- file2.py - Description

## Usage Examples
\`\`\`python
from module import Class
instance = Class()
\`\`\`

## Dependencies
- List internal dependencies
- List external dependencies

## Architecture
[Optional diagram or explanation]
```

**Success Criteria:**
- [ ] All 7 modules have README.md
- [ ] Each README has purpose, components, usage, dependencies
- [ ] Cross-references to docs/API.md where relevant

---

#### 2. docs/expand-api-documentation (3-4 days)
**Goal:** Complete API documentation for all public interfaces

**Files to Update:**
```
docs/API.md (expand from 1,900 lines to ~2,500 lines)
```

**Sections to Add:**
1. **Utilities API** (utils/)
   - git.py: GitTracker class, get_git_tracker()
   - log_monitor.py: LogMonitorManager, MonitoringConfig
   - log_analyzer.py: LocalLogAnalyzer, LogIssue
   - helpers.py: (document as trivial, or remove if unused)

2. **Messaging API** (messaging/)
   - formatter.py: format_telegram_response()
   - queue.py: MessageQueueManager, UserMessageQueue
   - rate_limiter.py: RateLimiter class

3. **Monitoring API** (monitoring/)
   - metrics.py: MetricsAggregator class
   - hooks_reader.py: HooksReader class
   - commands.py: Command parsing functions

4. **Task Enforcement** (tasks/)
   - enforcer.py: WorkflowEnforcer class
   - analytics.py: AnalyticsDB class

**Template per API:**
```markdown
### ClassName (`module.py:line`)

Brief description

#### API Methods

##### method_name (`module.py:line`)

\`\`\`python
def method_name(self, arg1: type, arg2: type) -> return_type:
    """Docstring"""
\`\`\`

**Example:**
\`\`\`python
instance = ClassName()
result = instance.method_name(arg1, arg2)
\`\`\`

**Returns:**
Describe return value
```

**Success Criteria:**
- [ ] All public classes documented
- [ ] All public methods documented
- [ ] Usage examples for each API
- [ ] Return value documentation
- [ ] Cross-references between related APIs

---

#### 3. tests/add-missing-unit-tests (5-7 days)
**Goal:** Add unit tests for all untested modules

**Test Files to Create:**
```
tests/test_code_cli.py          (claude/code_cli.py)
tests/test_config.py            (core/config.py)
tests/test_orchestrator.py      (core/orchestrator.py)
tests/test_database_advanced.py (tasks/database.py - missing methods)
tests/test_enforcer.py          (tasks/enforcer.py)
tests/test_pool_unit.py         (tasks/pool.py - priority queue)
tests/test_tracker.py           (tasks/tracker.py)
tests/test_rate_limiter.py      (messaging/rate_limiter.py)
tests/test_commands.py          (monitoring/commands.py - expand existing)
tests/test_metrics.py           (monitoring/metrics.py)
tests/test_hooks_reader.py      (monitoring/hooks_reader.py)
tests/test_git.py               (utils/git.py)
tests/test_log_monitor.py       (utils/log_monitor.py)
tests/test_log_analyzer.py      (utils/log_analyzer.py)
```

**Priority Order:**
1. claude/code_cli.py (CRITICAL - complex session management)
2. tasks/database.py (CRITICAL - missing method coverage)
3. monitoring/metrics.py (HIGH - dashboard dependencies)
4. tasks/enforcer.py (HIGH - workflow validation)
5. utils/log_monitor.py (MEDIUM - error detection)
6. Rest of modules (MEDIUM)

**Template per Test File:**
```python
"""Tests for module_name module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from module_name import ClassName

class TestClassName:
    """Test suite for ClassName functionality."""

    def test_typical_case(self):
        """Test normal operation with valid input."""
        instance = ClassName()
        result = instance.method(valid_input)
        assert result == expected_output

    def test_edge_case_empty_input(self):
        """Test handling of empty input."""
        instance = ClassName()
        result = instance.method("")
        assert result == expected_empty_result

    def test_error_handling_invalid_input(self):
        """Test that invalid input raises appropriate error."""
        instance = ClassName()
        with pytest.raises(ValueError, match="Invalid input"):
            instance.method(invalid_input)
```

**Success Criteria:**
- [ ] All critical modules have unit tests
- [ ] Each test file has 5+ test cases
- [ ] Tests cover typical, edge, and error cases
- [ ] Tests use pytest fixtures from conftest.py
- [ ] All tests pass: `pytest tests/ -v`

---

#### 4. tests/add-integration-tests (3-4 days)
**Goal:** Add end-to-end integration tests

**Test Files to Create:**
```
tests/integration/test_end_to_end_task_flow.py
tests/integration/test_concurrent_execution.py
tests/integration/test_error_recovery.py
tests/integration/test_cost_limit_enforcement.py
tests/integration/test_database_migration.py
```

**Test Scenarios:**

1. **End-to-End Task Flow** (test_end_to_end_task_flow.py)
   ```python
   async def test_complete_task_lifecycle():
       # 1. User sends message
       # 2. Router creates task
       # 3. AgentPool picks up task
       # 4. ClaudeSessionPool executes
       # 5. Task completed
       # 6. User notified
       pass
   ```

2. **Concurrent Execution** (test_concurrent_execution.py)
   ```python
   async def test_three_tasks_run_concurrently():
       # Submit 3 tasks simultaneously
       # Verify all complete without interference
       # Verify no file conflicts
       pass
   ```

3. **Error Recovery** (test_error_recovery.py)
   ```python
   async def test_restart_recovery():
       # Start task
       # Simulate crash (kill process)
       # Restart bot
       # Verify task marked as stopped
       # Verify user notification sent
       pass
   ```

4. **Cost Limit Enforcement** (test_cost_limit_enforcement.py)
   ```python
   async def test_daily_cost_limit():
       # Set limit
       # Execute tasks until limit reached
       # Verify subsequent tasks rejected
       pass
   ```

5. **Database Migration** (test_database_migration.py)
   ```python
   def test_schema_migration_v9_to_v10():
       # Create v9 schema DB
       # Populate with test data
       # Run migration
       # Verify v10 schema
       # Verify data integrity
       pass
   ```

**Success Criteria:**
- [ ] All 5 integration test files created
- [ ] Tests run in isolation (use tmp_path fixtures)
- [ ] Tests clean up resources (databases, files)
- [ ] Tests are deterministic (no flaky tests)
- [ ] All tests pass: `pytest tests/integration/ -v`

---

#### 5. refactor/consolidate-database-paths (1 day)
**Goal:** Remove all hardcoded database paths

**Files to Update:**
```
scripts/merge_databases.py
scripts/analyze_tool_usage.py
scripts/analyze_errors.py
scripts/analyze_actual_errors.py
scripts/check_improvement.py
scripts/query_top_tools.py
telegram_bot/migrate_to_sqlite.py
(+ any others found via grep)
```

**Pattern:**
```python
# Before
from pathlib import Path
data_dir = Path(__file__).parent.parent / "data"
db_path = data_dir / "agentlab.db"
db = Database(str(db_path))

# After
from core.config import DATABASE_PATH_STR
db = Database(DATABASE_PATH_STR)
```

**Checklist:**
- [ ] Grep for all instances: `grep -r "data/agentlab.db" --include="*.py"`
- [ ] Replace with `from core.config import DATABASE_PATH_STR`
- [ ] Test all scripts still work
- [ ] Add pre-commit hook to prevent new hardcoded paths

**Success Criteria:**
- [ ] `grep -r "data/agentlab.db" --include="*.py"` returns 0 matches (except config.py)
- [ ] All scripts run successfully
- [ ] Tests pass: `pytest tests/ -v`

---

#### 6. refactor/centralize-sanitization (1 day)
**Goal:** Remove inline sanitization, use shared utilities

**Files to Update:**
```
core/main.py (handle_message has inline sanitization)
claude/code_cli.py (ClaudeInteractiveSession has inline sanitization)
monitoring/server.py (handle_chat_message has inline sanitization)
```

**Pattern:**
```python
# Before (inline sanitization)
async def handle_message(text):
    # Inline HTML escape
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    
    # Inline injection detection
    if "ignore all previous" in text.lower():
        return "Rejected"
    
    return await process(text)

# After (use shared utilities)
from claude.api_client import sanitize_xml_content, detect_prompt_injection

async def handle_message(text):
    # Detect injection
    is_malicious, reason = detect_prompt_injection(text)
    if is_malicious:
        return f"Input rejected: {reason}"
    
    # Sanitize
    safe_text = sanitize_xml_content(text)
    return await process(safe_text)
```

**Checklist:**
- [ ] Find all inline sanitization: `grep -r "replace.*&amp" --include="*.py"`
- [ ] Find all inline injection checks: `grep -r "ignore all previous" --include="*.py"`
- [ ] Replace with calls to `claude.api_client` functions
- [ ] Test all input paths (Telegram, web chat, voice)
- [ ] Verify security tests still pass

**Success Criteria:**
- [ ] No inline sanitization code (except in claude/api_client.py)
- [ ] All user input uses `sanitize_xml_content()`
- [ ] All user input uses `detect_prompt_injection()`
- [ ] Security tests pass: `pytest tests/test_security.py -v`

---

### MEDIUM PRIORITY

#### 7. refactor/extract-long-functions (3-4 days)
**Goal:** Break down functions > 100 lines

**Functions to Refactor:**
1. **core/main.py:handle_message()** (150 lines)
   - Extract: `authenticate_user()`
   - Extract: `check_rate_limit()`
   - Extract: `extract_message_text()`
   - Extract: `process_user_message()`
   - Extract: `send_response()`

2. **core/main.py:execute_background_task()** (120 lines)
   - Extract: `setup_task_context()`
   - Extract: `execute_claude_session()`
   - Extract: `handle_task_result()`
   - Extract: `notify_task_completion()`

3. **monitoring/server.py:stream_metrics()** (200 lines)
   - Extract: `gather_metrics_data()`
   - Extract: `format_sse_message()`
   - Extract SSE streaming logic to decorator

4. **tasks/database.py:_migrate_schema()** (300 lines)
   - Extract each migration: `_migration_v1_to_v2()`, etc.
   - Create migration registry
   - Add migration version tracking

**Success Criteria:**
- [ ] All functions < 100 lines
- [ ] Extracted functions have clear names
- [ ] Extracted functions have docstrings
- [ ] All tests still pass
- [ ] No functionality changes (pure refactoring)

---

#### 8. refactor/database-singleton (1 day)
**Goal:** Create singleton Database manager

**Files to Create:**
```
core/database_manager.py
```

**Implementation:**
```python
"""Singleton database manager for application-wide database access."""
from core.config import DATABASE_PATH_STR
from tasks.database import Database

_db_instance = None

def get_database() -> Database:
    """Get singleton Database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(DATABASE_PATH_STR)
    return _db_instance

def close_database():
    """Close database connection (call on shutdown)."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
        _db_instance = None
```

**Files to Update:**
```
core/main.py
monitoring/server.py
web_chat/server.py
(All files that initialize Database)
```

**Success Criteria:**
- [ ] Only one Database connection per process
- [ ] All code uses `get_database()` function
- [ ] Shutdown properly closes connection
- [ ] Tests use separate database instances (via dependency injection)

---

#### 9. quality/improve-error-handling (1-2 days)
**Goal:** Standardize error handling

**Changes:**
1. Define custom exception hierarchy
   ```python
   # core/exceptions.py (NEW FILE)
   class AMIGAError(Exception):
       """Base exception for AMIGA"""
   
   class DatabaseError(AMIGAError):
       """Database operation failed"""
   
   class ConfigError(AMIGAError):
       """Configuration error"""
   
   class APIError(AMIGAError):
       """External API error"""
   ```

2. Replace bare except with specific exceptions
3. Add context to all error logs
4. Use `exc_info=True` for logger.error

**Success Criteria:**
- [ ] No bare `except:` blocks
- [ ] All exceptions inherit from AMIGAError
- [ ] All logger.error calls have exc_info=True
- [ ] Error messages include context (task_id, user_id, etc.)

---

#### 10. tests/improve-coverage-reporting (1 day)
**Goal:** Setup coverage infrastructure

**Files to Create:**
```
.coveragerc
```

**Content:**
```ini
[run]
source = .
omit =
    venv/*
    */tests/*
    */node_modules/*
    setup.py

[report]
precision = 2
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:

[html]
directory = htmlcov
```

**Changes:**
- [ ] Create `.coveragerc`
- [ ] Update `pyproject.toml` with coverage config
- [ ] Add coverage badge to README
- [ ] Separate `tests/unit/` and `tests/integration/`
- [ ] Add coverage check to pre-commit hooks

**Success Criteria:**
- [ ] `pytest --cov=. --cov-report=html` generates report
- [ ] Coverage report shows > 70% for critical modules
- [ ] Tests organized into unit/ and integration/
- [ ] Pre-commit hook enforces coverage minimums

---

### LOW PRIORITY

#### 11. refactor/centralize-logging (0.5 days)
Quick win - extract logging setup to utility.

#### 12. quality/add-type-hints (2 days)
Add type hints to utils/, monitoring/, configure mypy.

#### 13. security/production-config-checks (0.5 days)
Add startup warnings for insecure defaults.

#### 14. docs/add-architecture-decisions (2 days)
Create ADRs documenting key architectural choices.

---

## Testing Strategy

### Before Starting Any Branch
```bash
# Ensure main is clean
git checkout main
git pull origin main
pytest tests/ -v
```

### While Working on Branch
```bash
# Run relevant tests frequently
pytest tests/test_<module>.py -v

# Run full suite before commit
pytest tests/ -v

# Check code quality
pre-commit run --all-files
```

### Before Merging
```bash
# Rebase on latest main
git fetch origin
git rebase origin/main

# Run full test suite
pytest tests/ -v --cov=. --cov-report=term

# Verify no breaking changes
python -m core.main --help  # Should still work
```

---

## Progress Tracking

### High Priority (Complete First)
- [ ] docs/add-module-readmes
- [ ] docs/expand-api-documentation
- [ ] tests/add-missing-unit-tests
- [ ] tests/add-integration-tests
- [ ] refactor/consolidate-database-paths
- [ ] refactor/centralize-sanitization

### Medium Priority
- [ ] refactor/extract-long-functions
- [ ] refactor/database-singleton
- [ ] quality/improve-error-handling
- [ ] tests/improve-coverage-reporting
- [ ] refactor/centralize-logging

### Low Priority
- [ ] quality/add-type-hints
- [ ] security/production-config-checks
- [ ] docs/add-architecture-decisions

---

## Questions?

See full analysis: `docs/analysis/CODEBASE_IMPROVEMENT_ANALYSIS.md`

**Next Steps:**
1. Review this document
2. Choose branches to work on (can be parallel)
3. Create branch: `git checkout -b branch-name`
4. Make changes
5. Test thoroughly
6. Submit PR

**Estimated Timeline:**
- Phase 1 (High Priority): 2-3 weeks
- Phase 2 (Medium Priority): 1-2 weeks  
- Phase 3 (Low Priority): 1 week
- **Total: 4-6 weeks**

