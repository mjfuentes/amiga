# 10. Priority Queue Enhancement

Date: 2025-01-15

## Status

Accepted

## Context

Initial agent pool implementation used simple FIFO queue (first-in-first-out):

**Problems:**
1. **Critical tasks wait**: User sends `/restart` but waits behind slow background tasks
2. **Poor responsiveness**: Interactive commands blocked by batch operations
3. **No urgency signal**: All tasks treated equally (user request = cleanup job)
4. **Unfair under load**: One user's long task blocks other users' quick commands

**Real-world scenario:**
```
Queue: [User A: Refactor (5 min)] → [User B: /status (5 sec)] → [Cleanup (2 min)]
User B waits 5 minutes to see status (poor UX)
```

**Requirements:**
- Priority for interactive user requests
- Critical commands jump the queue
- Fair ordering within same priority
- No starvation of low-priority tasks

## Decision

Enhance agent pool with **priority-based task execution** using Python's `asyncio.PriorityQueue`.

**Architecture** (`tasks/pool.py`):

```python
class TaskPriority(IntEnum):
    """Lower numeric value = higher priority"""
    URGENT = 0   # User-facing errors, critical failures
    HIGH = 1     # User requests, interactive tasks
    NORMAL = 2   # Background tasks, routine operations (default)
    LOW = 3      # Maintenance, cleanup, analytics

class AgentPool:
    def __init__(self, max_agents: int = 3):
        # Changed from asyncio.Queue to PriorityQueue
        self.task_queue = asyncio.PriorityQueue()
        self._task_counter = 0  # FIFO within same priority

    async def submit(self, task_func, *args,
                    priority: TaskPriority = TaskPriority.NORMAL,
                    **kwargs):
        # Queue format: (priority, counter, (task_func, args, kwargs))
        counter = self._task_counter
        self._task_counter += 1
        await self.task_queue.put((priority, counter, (task_func, args, kwargs)))
```

**Priority assignment:**
- **URGENT**: Error notifications, critical system events
- **HIGH**: User commands (`/status`, `/stop`, `/restart`)
- **NORMAL**: Regular coding tasks (default for most work)
- **LOW**: Background cleanup, analytics, maintenance

**FIFO within priority:**
- Counter ensures tasks with same priority execute in submission order
- Prevents priority inversion within tier
- Example: Two HIGH tasks → execute in order submitted

## Consequences

### Positive

- **Responsive commands**: Interactive commands bypass long tasks
- **Better UX**: Critical operations don't wait
- **Fair within priority**: Same-priority tasks maintain FIFO order
- **Simple API**: Submit with `priority=TaskPriority.HIGH`
- **Backward compatible**: Default priority (NORMAL) preserves old behavior
- **No starvation**: Even LOW tasks eventually execute (queue drains)
- **Debuggable**: Priority level logged for each task

### Negative

- **Potential starvation**: LOW tasks could wait indefinitely under constant HIGH load
- **Complexity**: More complex than simple FIFO queue
- **Priority inversion**: If HIGH task depends on LOW task result (rare)
- **Tuning needed**: Deciding correct priority for each task type
- **Counter overflow**: _task_counter could overflow (unlikely in practice)

## Alternatives Considered

1. **Separate Queue Per Priority**
   - Rejected: More complex to implement
   - Harder to guarantee fairness
   - PriorityQueue is simpler

2. **Deadline-Based Scheduling**
   - Rejected: Requires deadline estimation
   - Complex to implement (EDF scheduling)
   - Overkill for our use case

3. **Weighted Fair Queuing**
   - Rejected: Too complex for benefit
   - Would help with starvation but adds overhead
   - Current approach is sufficient

4. **Thread Priorities (OS-level)**
   - Rejected: Doesn't work with async/subprocess model
   - OS thread priorities unreliable across platforms

5. **Dynamic Priority Adjustment**
   - Considered: Boost priority of waiting tasks over time
   - Rejected: Adds complexity, not needed yet
   - Could add later if starvation becomes issue

## Priority Usage Examples

**Message handlers** (`core/main.py`):
```python
# High priority - interactive commands
await message_queue.enqueue_message(
    user_id, update, context,
    handler=restart_handler,
    handler_name="restart",
    priority=1  # HIGH
)

# Normal priority - regular messages
await message_queue.enqueue_message(
    user_id, update, context,
    handler=message_handler,
    handler_name="message",
    priority=0  # NORMAL (default)
)
```

**Task submission** (`core/orchestrator.py`):
```python
# High priority - user-initiated tasks
await agent_pool.submit(
    execute_task,
    task_id=task.id,
    priority=TaskPriority.HIGH
)

# Low priority - background cleanup
await agent_pool.submit(
    cleanup_old_logs,
    priority=TaskPriority.LOW
)
```

## Priority Decision Matrix

**Task Type → Priority Level:**

| Task Type | Priority | Rationale |
|-----------|----------|-----------|
| /restart, /start commands | HIGH | Critical, user waiting |
| /status, /usage queries | HIGH | Interactive, quick response |
| User coding requests | NORMAL | Standard work, can queue |
| Background analytics | LOW | Not time-sensitive |
| Log cleanup | LOW | Maintenance, deferrable |
| Error notifications | URGENT | Critical failures |

## Starvation Prevention

**Current approach:**
- Pool eventually drains (tasks complete)
- LOW tasks execute when queue empties
- No infinite HIGH task generation

**If starvation becomes issue:**
- Add age-based priority boost
- Limit HIGH task rate per user
- Reserved slot for LOW tasks

## References

- Priority enum: `tasks/pool.py:25-37`
- PriorityQueue: `tasks/pool.py:56`
- Submit with priority: `tasks/pool.py:100-131`
- Counter for FIFO: `tasks/pool.py:61`, `tasks/pool.py:118-121`
- Task execution: `tasks/pool.py:132-188`
- Message queue priorities: `messaging/queue.py:28`, `messaging/queue.py:158`
- Related: ADR 0002 (Task Pool Architecture) for pool design
- Related: ADR 0003 (Per-User Queue) for message-level queueing
