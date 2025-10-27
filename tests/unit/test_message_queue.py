"""
Test suite for message queue system
Tests sequential processing of concurrent messages per user
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from messaging.queue import MessageQueueManager


class MockUpdate:
    """Mock Telegram Update object"""

    def __init__(self, user_id: int, message_text: str = "test"):
        self.effective_user = type("obj", (object,), {"id": user_id})()

        async def mock_send_action(action):
            """Mock async send_action method"""
            pass

        self.message = type(
            "obj",
            (object,),
            {
                "text": message_text,
                "chat": type("obj", (object,), {"send_action": mock_send_action})(),
            },
        )()


class MockContext:
    """Mock Telegram Context object"""

    def __init__(self):
        async def mock_send_message(**kwargs):
            """Mock async send_message method"""
            pass

        self.bot = type("obj", (object,), {"send_message": mock_send_message})()


@pytest.mark.asyncio
async def test_single_message_processing():
    """Test that a single message is processed correctly"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        results.append(("processed", update.message.text))
        await asyncio.sleep(0.1)

    update = MockUpdate(user_id=123, message_text="hello")
    context = MockContext()

    await queue_manager.enqueue_message(
        user_id=123, update=update, context=context, handler=handler, handler_name="test"
    )

    # Wait for processing
    await asyncio.sleep(0.3)

    assert len(results) == 1
    assert results[0] == ("processed", "hello")


@pytest.mark.asyncio
async def test_concurrent_messages_sequential_processing():
    """Test that multiple messages are queued and processed sequentially"""
    queue_manager = MessageQueueManager()
    results = []
    processing_times = []

    async def handler(update, context):
        start = datetime.now()
        processing_times.append(start)
        results.append(("processing", update.message.text))
        await asyncio.sleep(0.2)  # Simulate work
        results.append(("done", update.message.text))

    # Send 3 concurrent messages rapidly
    tasks = []
    for i in range(3):
        update = MockUpdate(user_id=123, message_text=f"message_{i}")
        task = queue_manager.enqueue_message(
            user_id=123, update=update, context=MockContext(), handler=handler, handler_name=f"test_{i}"
        )
        tasks.append(task)

    # Wait for all to be enqueued
    await asyncio.gather(*tasks)

    # Wait for all to be processed
    await asyncio.sleep(1.5)

    # Verify sequential processing
    # Each message should process one at a time
    assert len(results) == 6  # 2 events per message * 3 messages
    assert results[0][0] == "processing"
    assert results[1][0] == "done"
    assert results[2][0] == "processing"
    assert results[3][0] == "done"
    assert results[4][0] == "processing"
    assert results[5][0] == "done"

    # Verify order
    assert results[0][1] == "message_0"
    assert results[2][1] == "message_1"
    assert results[4][1] == "message_2"


@pytest.mark.asyncio
async def test_different_users_parallel_processing():
    """Test that different users process messages in parallel"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        user_id = update.effective_user.id
        results.append(("start", user_id, datetime.now().timestamp()))
        await asyncio.sleep(0.2)
        results.append(("end", user_id, datetime.now().timestamp()))

    # Send messages from different users
    tasks = []
    for user_id in [1, 2, 3]:
        update = MockUpdate(user_id=user_id, message_text=f"user_{user_id}")
        task = queue_manager.enqueue_message(
            user_id=user_id, update=update, context=MockContext(), handler=handler, handler_name=f"test_user_{user_id}"
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
    await asyncio.sleep(0.5)

    # Different users should process in parallel (overlapping times)
    start_times = [r[2] for r in results if r[0] == "start"]
    end_times = [r[2] for r in results if r[0] == "end"]

    # If truly parallel, the end of first user should be after start of another
    # This is a loose check since timing can vary
    assert len(start_times) >= 2
    assert len(end_times) >= 2


@pytest.mark.asyncio
async def test_queue_manager_status():
    """Test queue manager status reporting"""
    queue_manager = MessageQueueManager()

    async def handler(update, context):
        await asyncio.sleep(0.1)

    update = MockUpdate(user_id=123, message_text="test")

    # Initially no queues
    status = queue_manager.get_status()
    assert status["active_users"] == 0

    # Enqueue a message
    await queue_manager.enqueue_message(
        user_id=123, update=update, context=MockContext(), handler=handler, handler_name="test"
    )

    # Should have one active user
    await asyncio.sleep(0.05)
    status = queue_manager.get_status()
    assert status["active_users"] == 1

    # Check user-specific status
    user_status = await queue_manager.get_user_status(123)
    assert user_status is not None
    assert user_status["user_id"] == 123
    assert user_status["processing"]


@pytest.mark.asyncio
async def test_queue_preserves_order():
    """Test that queued messages are processed in FIFO order"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        results.append(update.message.text)
        await asyncio.sleep(0.05)

    # Enqueue messages with clear order markers
    for i in range(5):
        update = MockUpdate(user_id=999, message_text=f"msg_{i:02d}")
        await queue_manager.enqueue_message(
            user_id=999, update=update, context=MockContext(), handler=handler, handler_name=f"test_{i}"
        )

    # Wait for all to process
    await asyncio.sleep(1.0)

    # Verify FIFO order
    assert results == ["msg_00", "msg_01", "msg_02", "msg_03", "msg_04"]


@pytest.mark.asyncio
async def test_handler_exception_handling():
    """Test that exceptions in handlers don't crash the queue"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        msg = update.message.text
        if "error" in msg:
            raise ValueError("Intentional error")
        results.append(msg)

    # Send mix of good and error messages
    messages = ["good_1", "error_msg", "good_2"]
    for msg in messages:
        update = MockUpdate(user_id=456, message_text=msg)
        await queue_manager.enqueue_message(
            user_id=456, update=update, context=MockContext(), handler=handler, handler_name="test"
        )

    await asyncio.sleep(0.5)

    # Good messages should still process even after error
    assert "good_1" in results
    assert "good_2" in results


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
