# Integration Tests

End-to-end integration tests for AgentLab workflows.

## Test Files

### ✅ test_database_migration.py (8/8 passing)
Tests database schema migrations and data integrity:
- Schema version tracking
- Migration from v1 to current version
- Data preservation during migrations
- Index creation
- Foreign key constraints
- WAL mode
- Data type preservation
- Empty database initialization
- Idempotent migrations

**Status**: All tests passing

### ⚠️ test_end_to_end_task_flow.py (0/6 passing)
Tests complete task lifecycle from creation to completion.

**Issues to fix**:
1. `get_task()` is synchronous, not async - remove `await`
2. `add_activity()` should be `log_activity()`
3. `get_tasks_by_user()` doesn't exist - use `get_user_tasks()` instead

### ⚠️ test_concurrent_execution.py (0/6 passing)
Tests concurrent task execution without interference.

**Issues to fix**:
1. Same as test_end_to_end_task_flow.py
2. `get_task()` is synchronous
3. `add_activity()` should be `log_activity()`
4. `get_tasks_by_user()` should be `get_user_tasks()`

### ⚠️ test_error_recovery.py (0/8 passing)
Tests recovery from various failure modes.

**Issues to fix**:
1. Same as above
2. `get_task()` is synchronous
3. `add_activity()` should be `log_activity()`
4. `get_tasks_by_user()` should be `get_user_tasks()`
5. Line 160: `await task_manager.get_task(t.task_id).status` - need to first get task, then access status

### ❌ test_cost_limit_enforcement.py (0/10 passing)
Tests cost tracking and limit enforcement.

**Issues to fix**:
1. `AnalyticsDB` doesn't have `record_api_call()` method
2. `AnalyticsDB` doesn't have `get_cost_by_period()` method
3. Cost tracking API needs to be implemented or tests need to be redesigned

**Options**:
- Implement cost tracking API in AnalyticsDB
- Create separate CostTracker class
- Simplify tests to use mock implementation

## Running Tests

### Run all integration tests:
```bash
pytest tests/integration/ -v -m integration
```

### Run specific test file:
```bash
pytest tests/integration/test_database_migration.py -v -m integration
```

### Run specific test:
```bash
pytest tests/integration/test_database_migration.py::test_empty_database_migration -v -m integration
```

## Required Fixes

### Priority 1: Fix API mismatches
```python
# Current (wrong):
running_task = await task_manager.get_task(task.task_id)
await task_manager.add_activity(task.task_id, "message")
user_tasks = await task_manager.get_tasks_by_user(user_id)

# Correct:
running_task = task_manager.get_task(task.task_id)  # Synchronous!
await task_manager.log_activity(task.task_id, "message")
user_tasks = task_manager.get_user_tasks(user_id)  # Synchronous!
```

### Priority 2: Implement or mock cost tracking
Either:
1. Add cost tracking methods to AnalyticsDB
2. Create new CostTracker class
3. Simplify tests with mocks

### Priority 3: Fix compound expressions
```python
# Current (wrong):
running_tasks = [t for t in tasks if await task_manager.get_task(t.task_id).status == "running"]

# Correct:
running_tasks = []
for t in tasks:
    task_data = task_manager.get_task(t.task_id)
    if task_data.status == "running":
        running_tasks.append(t)
```

## Test Coverage

- ✅ Database schema migrations: 100%
- ⚠️ Task lifecycle: 0% (needs API fixes)
- ⚠️ Concurrent execution: 0% (needs API fixes)
- ⚠️ Error recovery: 0% (needs API fixes)
- ❌ Cost limits: 0% (needs implementation)

**Overall**: 8/38 tests passing (21%)

## Next Steps

1. Fix API method names and async/sync usage
2. Implement or mock cost tracking functionality
3. Re-run tests to verify fixes
4. Add additional test scenarios as needed
