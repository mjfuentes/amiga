# Analytics Database

## Overview

The analytics database tracks all user prompts and Claude responses for future analytics and insights. This data enables:
- Token usage analysis per user
- Conversation pattern analysis
- Input method breakdown (text, voice, image)
- Model performance comparison
- User activity trends

## Database Schema

### messages table

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    role TEXT NOT NULL,                  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    tokens_input INTEGER,                -- Input tokens (for assistant messages)
    tokens_output INTEGER,               -- Output tokens (for assistant messages)
    cache_creation_tokens INTEGER,       -- Prompt cache creation tokens
    cache_read_tokens INTEGER,           -- Prompt cache read tokens
    conversation_id TEXT,                -- Optional conversation threading
    input_method TEXT,                   -- 'text', 'voice', or 'image'
    has_image BOOLEAN DEFAULT 0,
    model TEXT                           -- Model used (e.g., 'claude-haiku-4-5')
)
```

**Indexes:**
- `idx_messages_user_timestamp` - User-specific queries ordered by time
- `idx_messages_timestamp` - Global time-based queries
- `idx_messages_conversation` - Conversation thread reconstruction

## API Reference

### AnalyticsDB Class

#### `log_message()`
```python
def log_message(
    user_id: int,
    role: str,
    content: str,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    cache_creation_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    conversation_id: str | None = None,
    input_method: str = "text",
    has_image: bool = False,
    model: str | None = None,
) -> int
```

**Description:** Log a single message to the database.

**Returns:** Message ID

**Example:**
```python
# Log user message
analytics_db.log_message(
    user_id=123456,
    role="user",
    content="Hello, Claude!",
    input_method="text"
)

# Log assistant response with token data
analytics_db.log_message(
    user_id=123456,
    role="assistant",
    content="Hello! How can I help you?",
    tokens_input=150,
    tokens_output=50,
    model="claude-haiku-4-5",
    input_method="text"
)
```

#### `get_user_messages()`
```python
def get_user_messages(
    user_id: int,
    limit: int = 100,
    offset: int = 0,
    role: str | None = None
) -> list[dict]
```

**Description:** Retrieve messages for a specific user.

**Parameters:**
- `user_id` - Telegram user ID
- `limit` - Maximum messages to return (default: 100)
- `offset` - Pagination offset (default: 0)
- `role` - Filter by 'user' or 'assistant' (None = all)

**Returns:** List of message dictionaries

#### `get_user_token_usage()`
```python
def get_user_token_usage(
    user_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None
) -> dict
```

**Description:** Get token usage statistics for a user.

**Returns:**
```python
{
    "user_id": 123456,
    "total_messages": 150,
    "total_input_tokens": 45000,
    "total_output_tokens": 15000,
    "total_cache_creation_tokens": 5000,
    "total_cache_read_tokens": 10000,
    "by_role": {
        "user": {
            "message_count": 75,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0
        },
        "assistant": {
            "message_count": 75,
            "input_tokens": 45000,
            "output_tokens": 15000,
            "cache_creation_tokens": 5000,
            "cache_read_tokens": 10000
        }
    }
}
```

#### `get_user_activity_over_time()`
```python
def get_user_activity_over_time(
    user_id: int,
    days: int = 30,
    bucket_hours: int = 24
) -> list[dict]
```

**Description:** Get user message activity in time buckets.

**Returns:** List of time buckets with message counts and token usage

#### `get_input_method_breakdown()`
```python
def get_input_method_breakdown(
    user_id: int,
    days: int = 30
) -> dict
```

**Description:** Get breakdown of input methods (text, voice, image).

**Returns:**
```python
{
    "total_messages": 100,
    "by_method": {
        "text": {
            "count": 80,
            "percentage": 80.0,
            "with_image_count": 5
        },
        "voice": {
            "count": 20,
            "percentage": 20.0,
            "with_image_count": 0
        }
    }
}
```

#### `get_model_usage()`
```python
def get_model_usage(
    user_id: int | None = None,
    days: int = 30
) -> dict
```

**Description:** Get model usage statistics (optionally filtered by user).

**Returns:**
```python
{
    "total_messages": 200,
    "by_model": {
        "claude-haiku-4-5": {
            "count": 150,
            "percentage": 75.0,
            "input_tokens": 30000,
            "output_tokens": 10000,
            "total_tokens": 40000
        },
        "claude-sonnet-4-5": {
            "count": 50,
            "percentage": 25.0,
            "input_tokens": 50000,
            "output_tokens": 20000,
            "total_tokens": 70000
        }
    }
}
```

#### `get_message_statistics()`
```python
def get_message_statistics(
    days: int = 30
) -> dict
```

**Description:** Get overall message statistics across all users.

**Returns:**
```python
{
    "total_messages": 1000,
    "by_role": {
        "user": 500,
        "assistant": 500
    },
    "token_usage": {
        "input_tokens": 100000,
        "output_tokens": 50000,
        "cache_creation_tokens": 10000,
        "cache_read_tokens": 20000,
        "total_tokens": 150000
    },
    "active_users": 5,
    "time_period_days": 30
}
```

#### `cleanup_old_messages()`
```python
def cleanup_old_messages(
    days: int = 90
) -> int
```

**Description:** Delete messages older than specified days.

**Returns:** Number of messages deleted

## Integration

The analytics database is automatically integrated into:

1. **Telegram Bot** (`main.py`)
   - Text messages
   - Voice messages
   - Image messages with captions

2. **Web Chat** (`monitoring_server.py`)
   - Browser chat messages

All user prompts and Claude responses are logged with:
- Full message content
- Token usage (input/output)
- Input method (text/voice/image)
- Model used
- Timestamp

## Migration

### From sessions.json

To migrate existing conversation history from `data/sessions.json`:

```bash
python3 migrate_to_sqlite.py
```

This will:
1. Load all user sessions from `data/sessions.json`
2. Populate the `messages` table with historical data
3. Display migration statistics

**Note:** Historical messages won't have token data (only new messages track tokens).

## Analytics Queries

### Example: Top users by message count
```python
# Get top 10 users by message count in last 30 days
cursor.execute("""
    SELECT user_id, COUNT(*) as msg_count
    FROM messages
    WHERE timestamp >= date('now', '-30 days')
    AND role = 'user'
    GROUP BY user_id
    ORDER BY msg_count DESC
    LIMIT 10
""")
```

### Example: Token usage per day
```python
# Get daily token usage for last 7 days
cursor.execute("""
    SELECT
        DATE(timestamp) as date,
        SUM(tokens_input) as input_tokens,
        SUM(tokens_output) as output_tokens
    FROM messages
    WHERE timestamp >= date('now', '-7 days')
    AND role = 'assistant'
    GROUP BY date
    ORDER BY date
""")
```

### Example: Voice vs text breakdown
```python
# Compare voice vs text usage
cursor.execute("""
    SELECT
        input_method,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM messages
    WHERE role = 'user'
    GROUP BY input_method
""")
```

## Performance Considerations

### Indexing
The database includes indexes for common query patterns:
- User + timestamp (most common)
- Global timestamp (dashboard queries)
- Conversation threading

### Data Retention
Configure automatic cleanup via cron or background task:

```python
# Delete messages older than 90 days
analytics_db.cleanup_old_messages(days=90)
```

### Database Size
Estimated storage per message:
- User message: ~500 bytes
- Assistant message: ~800 bytes (includes token data)

For 10,000 messages: ~6.5 MB

## Privacy & Security

### Data Handling
- User IDs are stored as integers (Telegram user IDs)
- No personally identifiable information beyond user_id
- Message content is stored in plaintext for analytics

### Access Control
- Database file: `data/agentlab.db`
- File permissions: 600 (owner read/write only)
- No external API exposure

### GDPR Compliance
For user data deletion requests:

```python
# Delete all messages for a user
cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
```

## Testing

Run the test suite:

```bash
pytest telegram_bot/tests/test_analytics.py -v
```

Tests cover:
- Message logging
- Token tracking
- User statistics
- Activity trends
- Input method breakdown
- Model usage analysis

## Future Enhancements

Potential additions:
- [ ] Cost calculation per user (token cost * token count)
- [ ] Sentiment analysis on messages
- [ ] Topic clustering
- [ ] User engagement scoring
- [ ] Export to CSV/JSON for external analysis
- [ ] Real-time analytics dashboard
- [ ] Conversation quality metrics (response time, length, etc.)

---

**Last Updated:** 2025-10-22
**Version:** 1.0.0
