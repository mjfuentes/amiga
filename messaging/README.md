# Messaging

## Purpose
Telegram message layer providing response formatting, per-user message queuing, and rate limiting for reliable message delivery.

## Components

### formatter.py
Response formatter for Telegram messages with HTML enhancement.
- `ResponseFormatter`: converts plain text to Telegram HTML
- Code block extraction and formatting (`<pre>`, `<code>`)
- File path highlighting with `<code>` tags
- Repository name highlighting with `<b>` tags
- List formatting
- HTML entity escaping for safety
- Markdown stripping (bold/italic → plain text)

### queue.py
Per-user message serialization to prevent rate limit violations.
- `MessageQueue`: per-user async queue with serialization
- `GlobalMessageQueue`: manages queues for all users
- Request serialization (one message per user at a time)
- Queue status tracking (length, processing state)
- Graceful shutdown with queue draining
- Thread-safe operations

### rate_limiter.py
Rate limiting implementation for Telegram API compliance.
- `RateLimiter`: token bucket algorithm
- Per-user rate limits (30 msg/min, 500 msg/hour)
- Global rate limits (30 msg/sec across all users)
- Automatic backoff and retry
- Rate limit remaining estimation
- Thread-safe token bucket operations

## Usage Examples

### Response Formatting
```python
from messaging.formatter import ResponseFormatter

formatter = ResponseFormatter(workspace_path="/Users/user/Workspace")

# Format plain text with code blocks
response = formatter.format_response("""
The bug is in **auth.py** at line 42.

Code:
```python
def authenticate(user):
    return user.is_valid  # Missing null check
```

Fix: Add null check before validation.
""")

# Output (HTML):
# The bug is in <code>auth.py</code> at line 42.
#
# Code:
# <pre>def authenticate(user):
#     return user.is_valid  # Missing null check</pre>
#
# Fix: Add null check before validation.
```

### Message Queue
```python
from messaging.queue import GlobalMessageQueue

# Initialize global queue
queue = GlobalMessageQueue()

# Add message to user's queue (automatically serializes)
await queue.add_message(
    user_id=12345,
    message="Processing your request...",
    send_func=bot.send_message,
    chat_id=12345
)

# Check queue status
status = queue.get_queue_status(user_id=12345)
# {
#     "queue_length": 3,
#     "is_processing": True,
#     "last_message_time": 1234567890.0
# }

# Graceful shutdown (drain all queues)
await queue.shutdown()
```

### Rate Limiting
```python
from messaging.rate_limiter import RateLimiter

limiter = RateLimiter()

# Check if user can send message
can_send, wait_time = await limiter.check_user_limit(user_id=12345)

if not can_send:
    print(f"Rate limited. Wait {wait_time:.1f} seconds")
else:
    await send_message()

# Check global rate limit
can_send_global, wait_time = await limiter.check_global_limit()

if not can_send_global:
    print(f"Global rate limit reached. Wait {wait_time:.1f} seconds")

# Get rate limit info
info = limiter.get_rate_limit_info(user_id=12345)
# {
#     "per_minute_remaining": 25,
#     "per_hour_remaining": 495,
#     "global_remaining": 28
# }
```

### Complete Message Delivery
```python
from messaging.formatter import ResponseFormatter
from messaging.queue import GlobalMessageQueue
from messaging.rate_limiter import RateLimiter

formatter = ResponseFormatter()
queue = GlobalMessageQueue()
limiter = RateLimiter()

async def send_formatted_message(user_id: int, text: str):
    """Send formatted message with rate limiting and queuing"""

    # Format response
    formatted = formatter.format_response(text)

    # Split if too long (Telegram limit: 4096 chars)
    chunks = split_message(formatted, max_length=4096)

    for chunk in chunks:
        # Check rate limit
        can_send, wait_time = await limiter.check_user_limit(user_id)
        if not can_send:
            await asyncio.sleep(wait_time)

        # Add to queue (serializes per user)
        await queue.add_message(
            user_id=user_id,
            message=chunk,
            send_func=bot.send_message,
            chat_id=user_id,
            parse_mode="HTML"
        )
```

## Dependencies

### Internal
- None (standalone module)

### External
- `asyncio` - Async queue management and rate limiting
- `telegram` - Telegram Bot API (for `send_message` integration)
- `re` - Regular expressions for formatting patterns

## Architecture

### Message Flow
```
User Request
    ↓
ResponseFormatter.format_response()
    ↓
Split into chunks (4096 char max)
    ↓
For each chunk:
    ↓
RateLimiter.check_user_limit()
    ↓ (if allowed)
GlobalMessageQueue.add_message()
    ↓
Per-user queue (serializes messages)
    ↓
_process_queue() → bot.send_message()
    ↓
Telegram API
```

### Rate Limit Hierarchy
```
Global Rate Limit (30 msg/sec)
    ↓
Per-User Rate Limits
    ↓
User A: 30 msg/min, 500 msg/hour
User B: 30 msg/min, 500 msg/hour
User C: 30 msg/min, 500 msg/hour
```

### Queue Architecture
```
GlobalMessageQueue
    ↓
User Queues (one per user)
    ↓
User 12345: [msg1, msg2, msg3] (processing: msg1)
User 67890: [msg1] (processing: msg1)
User 11111: [msg1, msg2] (idle, waiting)
```

## Cross-References

- **Bot Integration**: See [core/README.md](../core/README.md) for message handler integration
- **Testing**: See [tests/README.md](../tests/README.md) for formatter tests

## Key Patterns

### HTML Entity Escaping
All user-generated content is escaped before Telegram HTML parsing:
```python
text = text.replace("&", "&amp;")
text = text.replace("<", "&lt;")
text = text.replace(">", "&gt;")
```

### Code Block Preservation
Code blocks extracted before HTML escaping, then restored to preserve syntax:
1. Extract code blocks with placeholders
2. Escape HTML entities in remaining text
3. Restore code blocks (already escaped internally)

### Per-User Serialization
Each user has independent queue, preventing one user's flood from blocking others:
- User A sends 10 messages → queued and sent sequentially
- User B sends 1 message → processed immediately (independent queue)

### Token Bucket Rate Limiting
Rate limiter uses token bucket algorithm:
- Tokens refill at fixed rate (e.g., 30/minute)
- Each message consumes 1 token
- If bucket empty, request blocked until refill

### Message Chunking
Long messages split at 4096 chars (Telegram limit):
- Prefer splitting at newlines
- Preserve code block boundaries
- Each chunk sent as separate message

## Performance Considerations

### Async Queue Processing
Each user's queue processed asynchronously, allowing concurrent message delivery to multiple users.

### Rate Limit Caching
Rate limit state cached in memory, avoiding database lookups on every message.

### Backpressure Handling
If queue grows too large, consider:
- Dropping low-priority messages
- Batching similar messages
- Warning user about rate limits

## Notes

- Telegram HTML supports limited tags: `<b>`, `<i>`, `<code>`, `<pre>`, `<a>`
- Code blocks automatically get syntax highlighting in Telegram desktop
- Rate limits enforced by Telegram API, not just local checks
- Queue shutdown waits up to 30 seconds for pending messages
- Empty queues automatically cleaned up (memory management)
- Markdown formatting stripped to avoid conflicts with HTML parsing
