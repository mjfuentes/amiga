"""
Analytics database for user prompts and messages
Tracks conversation data for future analytics and insights
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from tasks.database import Database

logger = logging.getLogger(__name__)


class AnalyticsDB:
    """
    Analytics database wrapper for message and conversation tracking.
    Extends the main Database class with analytics-specific operations.
    """

    def __init__(self, db: Database):
        """
        Initialize analytics DB wrapper.

        Args:
            db: Existing Database instance to use
        """
        self.db = db
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure analytics tables exist"""
        cursor = self.db.conn.cursor()

        # Messages table for conversation analytics
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tokens_input INTEGER,
                tokens_output INTEGER,
                cache_creation_tokens INTEGER,
                cache_read_tokens INTEGER,
                conversation_id TEXT,
                input_method TEXT,
                has_image BOOLEAN DEFAULT 0,
                model TEXT
            )
        """
        )

        # Create indices for efficient querying
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_user_timestamp
            ON messages(user_id, timestamp DESC)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp
            ON messages(timestamp DESC)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, timestamp ASC)
        """
        )

        self.db.conn.commit()
        logger.debug("Analytics schema initialized")

    def log_message(
        self,
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
    ) -> int:
        """
        Log a message to the analytics database.

        Args:
            user_id: Telegram user ID
            role: Message role ('user' or 'assistant')
            content: Message content
            tokens_input: Input tokens consumed (for assistant messages)
            tokens_output: Output tokens generated (for assistant messages)
            cache_creation_tokens: Prompt cache creation tokens
            cache_read_tokens: Prompt cache read tokens
            conversation_id: Optional conversation/session ID for threading
            input_method: 'text', 'voice', or 'image'
            has_image: Whether message included an image
            model: Model used for response (e.g., 'claude-haiku-4-5')

        Returns:
            Message ID
        """
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (
                user_id, timestamp, role, content,
                tokens_input, tokens_output, cache_creation_tokens, cache_read_tokens,
                conversation_id, input_method, has_image, model
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                datetime.now().isoformat(),
                role,
                content,
                tokens_input,
                tokens_output,
                cache_creation_tokens,
                cache_read_tokens,
                conversation_id,
                input_method,
                has_image,
                model,
            ),
        )
        self.db.conn.commit()

        message_id = cursor.lastrowid
        logger.debug(
            f"Logged {role} message for user {user_id} " f"(tokens: {tokens_input or 0} in, {tokens_output or 0} out)"
        )

        return message_id

    def get_user_messages(
        self, user_id: int, limit: int = 100, offset: int = 0, role: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get messages for a specific user.

        Args:
            user_id: Telegram user ID
            limit: Maximum number of messages to return
            offset: Offset for pagination
            role: Filter by role ('user' or 'assistant'), None for all

        Returns:
            List of message dictionaries
        """
        cursor = self.db.conn.cursor()

        if role:
            cursor.execute(
                """
                SELECT id, user_id, timestamp, role, content,
                       tokens_input, tokens_output, cache_creation_tokens, cache_read_tokens,
                       conversation_id, input_method, has_image, model
                FROM messages
                WHERE user_id = ? AND role = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """,
                (user_id, role, limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT id, user_id, timestamp, role, content,
                       tokens_input, tokens_output, cache_creation_tokens, cache_read_tokens,
                       conversation_id, input_method, has_image, model
                FROM messages
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """,
                (user_id, limit, offset),
            )

        return [self._row_to_message_dict(row) for row in cursor.fetchall()]

    def get_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """
        Get all messages in a conversation thread.

        Args:
            conversation_id: Conversation/session ID

        Returns:
            List of message dictionaries in chronological order
        """
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT id, user_id, timestamp, role, content,
                   tokens_input, tokens_output, cache_creation_tokens, cache_read_tokens,
                   conversation_id, input_method, has_image, model
            FROM messages
            WHERE conversation_id = ?
            ORDER BY timestamp ASC
        """,
            (conversation_id,),
        )

        return [self._row_to_message_dict(row) for row in cursor.fetchall()]

    def get_user_token_usage(
        self, user_id: int, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, Any]:
        """
        Get token usage statistics for a user.

        Args:
            user_id: Telegram user ID
            start_date: Start date for filtering (inclusive)
            end_date: End date for filtering (inclusive)

        Returns:
            Dictionary with token usage totals and breakdown
        """
        cursor = self.db.conn.cursor()

        # Build query with date filters
        query = """
            SELECT
                COUNT(*) as message_count,
                COALESCE(SUM(tokens_input), 0) as total_input_tokens,
                COALESCE(SUM(tokens_output), 0) as total_output_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) as total_cache_creation_tokens,
                COALESCE(SUM(cache_read_tokens), 0) as total_cache_read_tokens,
                role
            FROM messages
            WHERE user_id = ?
        """
        params = [user_id]

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " GROUP BY role"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Aggregate results
        result = {
            "user_id": user_id,
            "total_messages": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_cache_read_tokens": 0,
            "by_role": {},
        }

        for row in rows:
            role = row[5]  # role is the 6th column (index 5)
            result["by_role"][role] = {
                "message_count": row[0],
                "input_tokens": row[1],
                "output_tokens": row[2],
                "cache_creation_tokens": row[3],
                "cache_read_tokens": row[4],
            }
            result["total_messages"] += row[0]
            result["total_input_tokens"] += row[1]
            result["total_output_tokens"] += row[2]
            result["total_cache_creation_tokens"] += row[3]
            result["total_cache_read_tokens"] += row[4]

        return result

    def get_user_activity_over_time(self, user_id: int, days: int = 30, bucket_hours: int = 24) -> list[dict[str, Any]]:
        """
        Get user message activity over time in buckets.

        Args:
            user_id: Telegram user ID
            days: Number of days to look back
            bucket_hours: Size of time bucket in hours (default: 24 = daily)

        Returns:
            List of time buckets with message counts and token usage
        """
        cursor = self.db.conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute(
            """
            SELECT
                DATE(timestamp) as date_bucket,
                COUNT(*) as message_count,
                COALESCE(SUM(tokens_input), 0) as total_input_tokens,
                COALESCE(SUM(tokens_output), 0) as total_output_tokens,
                role
            FROM messages
            WHERE user_id = ? AND timestamp >= ?
            GROUP BY date_bucket, role
            ORDER BY date_bucket ASC
        """,
            (user_id, start_date),
        )

        rows = cursor.fetchall()

        # Group by date bucket
        buckets = {}
        for row in rows:
            date_bucket = row[0]
            role = row[4]

            if date_bucket not in buckets:
                buckets[date_bucket] = {
                    "date": date_bucket,
                    "total_messages": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "by_role": {},
                }

            buckets[date_bucket]["by_role"][role] = {
                "message_count": row[1],
                "input_tokens": row[2],
                "output_tokens": row[3],
            }
            buckets[date_bucket]["total_messages"] += row[1]
            buckets[date_bucket]["total_input_tokens"] += row[2]
            buckets[date_bucket]["total_output_tokens"] += row[3]

        return list(buckets.values())

    def get_input_method_breakdown(self, user_id: int, days: int = 30) -> dict[str, Any]:
        """
        Get breakdown of input methods used by user.

        Args:
            user_id: Telegram user ID
            days: Number of days to look back

        Returns:
            Dictionary with counts and percentages by input method
        """
        cursor = self.db.conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute(
            """
            SELECT
                input_method,
                COUNT(*) as count,
                COUNT(CASE WHEN has_image = 1 THEN 1 END) as with_image_count
            FROM messages
            WHERE user_id = ? AND role = 'user' AND timestamp >= ?
            GROUP BY input_method
        """,
            (user_id, start_date),
        )

        rows = cursor.fetchall()
        total = sum(row[1] for row in rows)

        breakdown = {}
        for row in rows:
            input_method = row[0]
            count = row[1]
            with_image = row[2]

            breakdown[input_method] = {
                "count": count,
                "percentage": (count / total * 100) if total > 0 else 0,
                "with_image_count": with_image,
            }

        return {"total_messages": total, "by_method": breakdown}

    def get_model_usage(self, user_id: int | None = None, days: int = 30) -> dict[str, Any]:
        """
        Get breakdown of model usage.

        Args:
            user_id: Telegram user ID (None for all users)
            days: Number of days to look back

        Returns:
            Dictionary with counts and token usage by model
        """
        cursor = self.db.conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        if user_id:
            cursor.execute(
                """
                SELECT
                    model,
                    COUNT(*) as count,
                    COALESCE(SUM(tokens_input), 0) as total_input_tokens,
                    COALESCE(SUM(tokens_output), 0) as total_output_tokens
                FROM messages
                WHERE user_id = ? AND role = 'assistant' AND timestamp >= ?
                GROUP BY model
            """,
                (user_id, start_date),
            )
        else:
            cursor.execute(
                """
                SELECT
                    model,
                    COUNT(*) as count,
                    COALESCE(SUM(tokens_input), 0) as total_input_tokens,
                    COALESCE(SUM(tokens_output), 0) as total_output_tokens
                FROM messages
                WHERE role = 'assistant' AND timestamp >= ?
                GROUP BY model
            """,
                (start_date,),
            )

        rows = cursor.fetchall()
        total_messages = sum(row[1] for row in rows)

        models = {}
        for row in rows:
            model = row[0] or "unknown"
            count = row[1]

            models[model] = {
                "count": count,
                "percentage": (count / total_messages * 100) if total_messages > 0 else 0,
                "input_tokens": row[2],
                "output_tokens": row[3],
                "total_tokens": row[2] + row[3],
            }

        return {"total_messages": total_messages, "by_model": models}

    def get_message_statistics(self, days: int = 30) -> dict[str, Any]:
        """
        Get overall message statistics across all users.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with comprehensive message statistics
        """
        cursor = self.db.conn.cursor()
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        # Total messages
        cursor.execute(
            """
            SELECT COUNT(*) FROM messages
            WHERE timestamp >= ?
        """,
            (start_date,),
        )
        total_messages = cursor.fetchone()[0]

        # By role
        cursor.execute(
            """
            SELECT role, COUNT(*) FROM messages
            WHERE timestamp >= ?
            GROUP BY role
        """,
            (start_date,),
        )
        by_role = {row[0]: row[1] for row in cursor.fetchall()}

        # Token usage
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(tokens_input), 0),
                COALESCE(SUM(tokens_output), 0),
                COALESCE(SUM(cache_creation_tokens), 0),
                COALESCE(SUM(cache_read_tokens), 0)
            FROM messages
            WHERE timestamp >= ?
        """,
            (start_date,),
        )
        token_row = cursor.fetchone()

        # Active users
        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) FROM messages
            WHERE timestamp >= ?
        """,
            (start_date,),
        )
        active_users = cursor.fetchone()[0]

        return {
            "total_messages": total_messages,
            "by_role": by_role,
            "token_usage": {
                "input_tokens": token_row[0],
                "output_tokens": token_row[1],
                "cache_creation_tokens": token_row[2],
                "cache_read_tokens": token_row[3],
                "total_tokens": token_row[0] + token_row[1],
            },
            "active_users": active_users,
            "time_period_days": days,
        }

    def cleanup_old_messages(self, days: int = 90) -> int:
        """
        Delete messages older than specified days.

        Args:
            days: Number of days to retain

        Returns:
            Number of messages deleted
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff_date,))
        self.db.conn.commit()

        deleted_count = cursor.rowcount
        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} old messages (older than {days} days)")

        return deleted_count

    def _row_to_message_dict(self, row) -> dict[str, Any]:
        """Convert database row to message dictionary"""
        return {
            "id": row[0],
            "user_id": row[1],
            "timestamp": row[2],
            "role": row[3],
            "content": row[4],
            "tokens_input": row[5],
            "tokens_output": row[6],
            "cache_creation_tokens": row[7],
            "cache_read_tokens": row[8],
            "conversation_id": row[9],
            "input_method": row[10],
            "has_image": bool(row[11]),
            "model": row[12],
        }
