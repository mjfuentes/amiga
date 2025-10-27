# 3. Per-User Message Queue

Date: 2025-01-15

## Status

Accepted

## Context

Telegram bot receives messages from multiple users concurrently. Key challenges:

1. **Conversation coherence**: User's messages must be processed in order
2. **Telegram rate limits**: Per-user limits (30 messages/minute per user)
3. **Context preservation**: Each message needs previous context from same user
4. **Fair resource allocation**: One user shouldn't block others
5. **Priority commands**: Some commands (/restart, /start) need immediate processing

**Without per-user queuing:**
- Messages from same user could be processed out of order
- User sends "Create feature X" then "Actually, make it Y" - system sees in reverse
- Global queue means one slow task blocks all users
- Difficult to implement per-user rate limiting

## Decision

Implement **per-user message queues** with independent processing.

**Architecture** (implemented in `messaging/queue.py`):

```python
class UserMessageQueue:
    """Queue for a single user's messages"""
    def __init__(self, user_id: int):
        self.queue = asyncio.Queue()        # Normal priority messages
        self.priority_queue = []             # High priority messages
        self.processing = False
        self.processor_task = None

class MessageQueueManager:
    """Manages queues for all users"""
    def __init__(self):
        self.user_queues: dict[int, UserMessageQueue] = {}
```

**Key features:**
1. **Isolated per user**: Each user has their own queue and processor
2. **Sequential per user**: Messages from same user processed in order
3. **Parallel across users**: Different users' messages process concurrently
4. **Priority support**: High-priority messages (priority > 0) jump to front
5. **Automatic processor**: Queue processor starts on first message, stops when empty
6. **Wait time logging**: Tracks how long messages wait in queue

**Priority levels** (`messaging/queue.py:28`):
- **0 (normal)**: Regular messages, commands
- **1+ (priority)**: /restart, /start, /clear commands that need immediate processing

## Consequences

### Positive

- **Conversation coherence**: Messages from same user always process in order
- **Fair allocation**: One user's slow task doesn't block other users
- **Correct context**: Each message has access to previous messages from same user
- **Per-user rate limiting**: Can implement Telegram rate limits per user
- **Priority support**: Critical commands process immediately
- **Scalability**: Supports unlimited users without global bottleneck
- **Debugging**: Can track individual user's message flow easily

### Negative

- **Memory overhead**: One queue per active user (minimal in practice)
- **Complexity**: More complex than single global queue
- **Potential queue buildup**: User sending many messages rapidly will queue them
- **No cross-user ordering**: Can't guarantee "User A before User B" without additional logic

## Alternatives Considered

1. **Global FIFO Queue**
   - Rejected: One slow message blocks all users
   - Can't maintain per-user conversation order
   - Unfair resource allocation

2. **No Queue (Direct Processing)**
   - Rejected: Race conditions with concurrent messages from same user
   - Out-of-order processing breaks conversation context
   - Can't implement rate limiting

3. **Per-User Thread Pools**
   - Rejected: More complex than async queues
   - Harder to manage lifecycle
   - No benefit over async approach

4. **Priority Queue with User ID as Secondary Key**
   - Considered: Single queue with (priority, user_id, timestamp) ordering
   - Rejected: Doesn't guarantee FIFO within user, complex to implement correctly

5. **Message Deduplication**
   - Considered: Dedupe identical messages within time window
   - Rejected: Legitimate use case for repeated messages
   - Would need user confirmation for deduping

## References

- Implementation: `messaging/queue.py:42-214`
- UserMessageQueue: `messaging/queue.py:42-142`
- MessageQueueManager: `messaging/queue.py:144-214`
- Usage in handlers: `core/main.py` (message handlers)
- Priority constants: `messaging/queue.py:28`
- Related: ADR 0002 (Task Pool) for agent-level concurrency
