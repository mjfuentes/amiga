# 2. Task Pool Architecture

Date: 2025-01-15

## Status

Accepted

## Context

The bot needs to execute multiple Claude Code sessions concurrently for different users. Key challenges:

1. **Resource constraints**: Each Claude Code session consumes significant resources (API tokens, memory, CPU)
2. **API rate limits**: Anthropic API has limits on concurrent requests
3. **Quality vs throughput**: Too many concurrent sessions degrade response quality
4. **Isolation requirements**: Tasks must not interfere with each other
5. **Fairness**: Users should get reasonable response times even under load

Without limits, the system could spawn unlimited concurrent tasks, leading to:
- API rate limit errors and failures
- Out of memory conditions
- Poor user experience (slow responses for everyone)
- Difficulty debugging when many tasks run simultaneously

## Decision

Implement a **bounded agent pool with 3 concurrent workers** using priority queue.

**Architecture** (implemented in `tasks/pool.py`):

```python
class AgentPool:
    def __init__(self, max_agents: int = 3):
        self.task_queue = asyncio.PriorityQueue()  # Priority-ordered queue
        self.agents = []  # Fixed pool of 3 worker coroutines
        self.active_tasks = 0
```

**Key features:**
1. **Fixed pool size**: Exactly 3 agent coroutines run concurrently
2. **Priority queue**: Tasks are ordered by priority (URGENT > HIGH > NORMAL > LOW)
3. **FIFO within priority**: Same-priority tasks execute in submission order
4. **Non-blocking submission**: `submit()` returns immediately, tasks queue if pool is full
5. **Graceful shutdown**: Poison pill pattern (sentinel objects) for clean shutdown
6. **Task isolation**: Each task runs in its own async context

**Priority levels** (`tasks/pool.py:25-37`):
- **URGENT** (0): User-facing errors, critical failures
- **HIGH** (1): User requests, interactive tasks (default for most user actions)
- **NORMAL** (2): Background tasks, routine operations
- **LOW** (3): Maintenance, cleanup, analytics

## Consequences

### Positive

- **Predictable resource usage**: Maximum 3 Claude Code sessions at once
- **No API overload**: Stays well within rate limits
- **Better quality**: Each task gets full resources without competition
- **Fair queuing**: Tasks processed in priority order, FIFO within priority
- **Debuggable**: Can easily track and monitor 3 concurrent tasks
- **Graceful degradation**: System remains stable under high load (tasks queue)
- **User experience**: High-priority user requests jump the queue

### Negative

- **Queue buildup**: Tasks wait when pool is full (max 3 concurrent)
- **No parallelism beyond 3**: Can't leverage multiple cores/machines
- **Fixed limit**: May be suboptimal for different load patterns
- **Memory growth**: Queue can grow large if tasks submit faster than they complete
- **Potential starvation**: Low-priority tasks may wait indefinitely under constant high-priority load

## Alternatives Considered

1. **Unlimited Concurrency**
   - Rejected: Resource exhaustion, API rate limits, poor debugging experience
   - Would require complex backpressure and circuit breaker logic

2. **Single Worker (Sequential)**
   - Rejected: Terrible UX - users wait for all previous tasks to complete
   - 3-5 minute wait times would be common

3. **Dynamic Pool Sizing**
   - Considered: Adjust pool size based on load (e.g., 1-10 workers)
   - Rejected: Adds complexity, hard to tune, unpredictable resource usage
   - May revisit if load patterns become more varied

4. **Thread Pool Instead of Async**
   - Rejected: Claude Code CLI is subprocess-based, async is more natural
   - Thread pool would not provide better isolation

5. **Per-User Pools**
   - Rejected: Unfair (heavy users get more resources)
   - Would need quotas and complex allocation logic

6. **Different Pool Sizes** (5, 10, 20 workers)
   - 5+ workers: API rate limits become issue, quality degrades
   - 1-2 workers: Too slow for multi-user scenarios
   - 3 workers: Sweet spot based on empirical testing

## References

- Implementation: `tasks/pool.py:39-208`
- Priority enum: `tasks/pool.py:25-37`
- Agent loop: `tasks/pool.py:132-188`
- Submit method: `tasks/pool.py:100-131`
- Usage in orchestrator: `core/orchestrator.py`
- Related: ADR 0003 (Per-User Message Queue) for complementary serialization
