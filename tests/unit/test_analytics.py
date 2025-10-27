"""
Test suite for analytics database functionality
"""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks.analytics import AnalyticsDB
from tasks.database import Database


@pytest.fixture
def analytics_db():
    """Create in-memory analytics database for testing"""
    db = Database(":memory:")
    analytics = AnalyticsDB(db)
    yield analytics
    db.close()


def test_message_logging(analytics_db):
    """Test logging user and assistant messages"""
    # Log user message
    msg_id = analytics_db.log_message(user_id=123456, role="user", content="Hello, Claude!", input_method="text")
    assert msg_id is not None
    assert isinstance(msg_id, int)

    # Log assistant response with tokens
    msg_id = analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Hello! How can I help you today?",
        tokens_input=150,
        tokens_output=50,
        model="claude-haiku-4-5",
        input_method="text",
    )
    assert msg_id is not None
    assert isinstance(msg_id, int)


def test_message_retrieval(analytics_db):
    """Test retrieving user messages"""
    # Add test messages
    analytics_db.log_message(user_id=123456, role="user", content="Test message 1", input_method="text")
    analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Response 1",
        tokens_input=100,
        tokens_output=50,
        model="claude-haiku-4-5",
        input_method="text",
    )

    # Retrieve messages (ordered DESC by timestamp, so most recent first)
    messages = analytics_db.get_user_messages(user_id=123456)
    assert len(messages) == 2
    assert messages[0]["role"] == "assistant"  # Most recent message first
    assert messages[0]["content"] == "Response 1"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Test message 1"


def test_token_usage_statistics(analytics_db):
    """Test token usage statistics"""
    # Add messages with token counts
    analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Response 1",
        tokens_input=100,
        tokens_output=50,
        model="claude-haiku-4-5",
        input_method="text",
    )
    analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Response 2",
        tokens_input=200,
        tokens_output=75,
        model="claude-sonnet-4-5",
        input_method="text",
    )

    # Get usage statistics
    usage = analytics_db.get_user_token_usage(user_id=123456)
    assert usage["total_messages"] == 2
    assert usage["total_input_tokens"] == 300
    assert usage["total_output_tokens"] == 125
    assert "assistant" in usage["by_role"]
    assert usage["by_role"]["assistant"]["message_count"] == 2  # Key is 'message_count' not 'messages'


def test_activity_tracking(analytics_db):
    """Test activity tracking over time"""
    # Add multiple messages
    for i in range(5):
        analytics_db.log_message(user_id=123456, role="user", content=f"Test message {i}", input_method="text")
        analytics_db.log_message(
            user_id=123456,
            role="assistant",
            content=f"Response {i}",
            tokens_input=100,
            tokens_output=50,
            model="claude-haiku-4-5",
            input_method="text",
        )

    # Get activity data (returns list of date buckets)
    activity = analytics_db.get_user_activity_over_time(user_id=123456, days=1)
    assert len(activity) > 0
    # Structure is: {'date': '2025-10-22', 'total_messages': 10, 'by_role': {...}}
    assert "date" in activity[0]
    assert "total_messages" in activity[0]
    assert "by_role" in activity[0]


def test_input_method_breakdown(analytics_db):
    """Test input method breakdown"""
    # Add messages with different input methods
    analytics_db.log_message(user_id=123456, role="user", content="Text message", input_method="text")
    analytics_db.log_message(user_id=123456, role="user", content="Voice message", input_method="voice")
    analytics_db.log_message(user_id=123456, role="user", content="Another text message", input_method="text")

    # Get breakdown
    breakdown = analytics_db.get_input_method_breakdown(user_id=123456, days=1)
    assert breakdown["total_messages"] == 3
    assert "text" in breakdown["by_method"]
    assert "voice" in breakdown["by_method"]
    assert breakdown["by_method"]["text"]["count"] == 2
    assert breakdown["by_method"]["voice"]["count"] == 1


def test_model_usage_statistics(analytics_db):
    """Test model usage statistics"""
    # Add messages with different models
    analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Haiku response 1",
        tokens_input=100,
        tokens_output=50,
        model="claude-haiku-4-5",
        input_method="text",
    )
    analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Haiku response 2",
        tokens_input=120,
        tokens_output=60,
        model="claude-haiku-4-5",
        input_method="text",
    )
    analytics_db.log_message(
        user_id=123456,
        role="assistant",
        content="Sonnet response",
        tokens_input=200,
        tokens_output=100,
        model="claude-sonnet-4-5",
        input_method="text",
    )

    # Get model statistics
    model_stats = analytics_db.get_model_usage(user_id=123456, days=1)
    assert model_stats["total_messages"] == 3
    assert "claude-haiku-4-5" in model_stats["by_model"]
    assert "claude-sonnet-4-5" in model_stats["by_model"]
    assert model_stats["by_model"]["claude-haiku-4-5"]["count"] == 2
    assert model_stats["by_model"]["claude-sonnet-4-5"]["count"] == 1


def test_overall_statistics(analytics_db):
    """Test overall message statistics"""
    # Add messages from multiple users
    for user_id in [123456, 789012]:
        analytics_db.log_message(user_id=user_id, role="user", content="User message", input_method="text")
        analytics_db.log_message(
            user_id=user_id,
            role="assistant",
            content="Assistant response",
            tokens_input=100,
            tokens_output=50,
            model="claude-haiku-4-5",
            input_method="text",
        )

    # Get overall statistics
    stats = analytics_db.get_message_statistics(days=1)
    assert stats["total_messages"] == 4
    assert "user" in stats["by_role"]
    assert "assistant" in stats["by_role"]
    assert stats["active_users"] == 2
    # Token usage structure: {'input_tokens': X, 'output_tokens': Y, ...}
    assert stats["token_usage"]["input_tokens"] == 200
    assert stats["token_usage"]["output_tokens"] == 100


def test_multiple_users(analytics_db):
    """Test isolation between different users"""
    # Add messages for user 1
    analytics_db.log_message(user_id=111111, role="user", content="User 1 message", input_method="text")

    # Add messages for user 2
    analytics_db.log_message(user_id=222222, role="user", content="User 2 message", input_method="text")

    # Verify isolation
    user1_messages = analytics_db.get_user_messages(user_id=111111)
    user2_messages = analytics_db.get_user_messages(user_id=222222)

    assert len(user1_messages) == 1
    assert len(user2_messages) == 1
    assert user1_messages[0]["content"] == "User 1 message"
    assert user2_messages[0]["content"] == "User 2 message"


def test_empty_user_statistics(analytics_db):
    """Test statistics for user with no messages"""
    usage = analytics_db.get_user_token_usage(user_id=999999)
    assert usage["total_messages"] == 0
    assert usage["total_input_tokens"] == 0
    assert usage["total_output_tokens"] == 0
    assert len(usage["by_role"]) == 0

    messages = analytics_db.get_user_messages(user_id=999999)
    assert len(messages) == 0
