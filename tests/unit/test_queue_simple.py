#!/usr/bin/env python3
"""
Test script for message queue manager
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from messaging.queue import MessageQueueManager


class MockUpdate:
    """Mock Telegram Update object"""

    def __init__(self, user_id: int, message_text: str = "test"):
        self.effective_user = type("obj", (object,), {"id": user_id})()
        self.message = type("obj", (object,), {"text": message_text})()


class MockContext:
    """Mock Telegram Context object"""

    pass


@pytest.mark.asyncio
async def test_single_message():
    """Test single message processing"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        results.append(f"processed: {update.message.text}")
        await asyncio.sleep(0.1)

    update = MockUpdate(user_id=123, message_text="hello")
    await queue_manager.enqueue_message(123, update, MockContext(), handler, "test")
    await asyncio.sleep(0.3)

    assert len(results) == 1
    assert results[0] == "processed: hello"


@pytest.mark.asyncio
async def test_concurrent_messages_sequential():
    """Test concurrent messages are processed sequentially"""
    queue_manager = MessageQueueManager()
    results = []
    start_times = {}

    async def handler(update, context):
        msg = update.message.text
        start_times[msg] = datetime.now()
        results.append(f"start: {msg}")
        await asyncio.sleep(0.15)  # 150ms per message
        results.append(f"done: {msg}")

    # Send 3 messages rapidly (concurrently)
    tasks = []
    for i in range(3):
        update = MockUpdate(user_id=123, message_text=f"msg_{i}")
        task = queue_manager.enqueue_message(123, update, MockContext(), handler, f"test_{i}")
        tasks.append(task)

    await asyncio.gather(*tasks)
    await asyncio.sleep(0.8)  # 3 * 150ms + buffer

    # Verify sequential processing (FIFO order)
    expected = [
        "start: msg_0",
        "done: msg_0",
        "start: msg_1",
        "done: msg_1",
        "start: msg_2",
        "done: msg_2",
    ]

    assert results == expected, f"Expected {expected}, got {results}"


@pytest.mark.asyncio
async def test_different_users_parallel():
    """Test different users process in parallel"""
    queue_manager = MessageQueueManager()
    results = []
    start_times = {}

    async def handler(update, context):
        user_id = update.effective_user.id
        if user_id not in start_times:
            start_times[user_id] = datetime.now()
        results.append(f"start: user_{user_id}")
        await asyncio.sleep(0.2)
        results.append(f"done: user_{user_id}")

    # Send from 3 different users
    tasks = []
    for user_id in [1, 2, 3]:
        update = MockUpdate(user_id=user_id, message_text=f"user_{user_id}")
        task = queue_manager.enqueue_message(user_id, update, MockContext(), handler, f"user_{user_id}")
        tasks.append(task)

    await asyncio.gather(*tasks)
    await asyncio.sleep(0.5)

    # Verify all users are active (parallel processing)
    start_count = sum(1 for r in results if r.startswith("start:"))
    # Should have multiple starts before any dones if truly parallel
    assert start_count >= 2, "Different users should process in parallel"


@pytest.mark.asyncio
async def test_queue_order_fifo():
    """Test FIFO ordering"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        results.append(update.message.text)
        await asyncio.sleep(0.05)

    # Queue 5 messages
    for i in range(5):
        update = MockUpdate(user_id=999, message_text=f"msg_{i:02d}")
        await queue_manager.enqueue_message(999, update, MockContext(), handler, f"test_{i}")

    await asyncio.sleep(0.5)

    expected = ["msg_00", "msg_01", "msg_02", "msg_03", "msg_04"]
    assert results == expected


@pytest.mark.asyncio
async def test_queue_status():
    """Test queue status reporting"""
    queue_manager = MessageQueueManager()

    async def handler(update, context):
        await asyncio.sleep(0.1)

    # No queues initially
    status = queue_manager.get_status()
    assert status["active_users"] == 0

    # Enqueue message
    update = MockUpdate(user_id=777, message_text="test")
    await queue_manager.enqueue_message(777, update, MockContext(), handler, "test")
    await asyncio.sleep(0.05)

    # Should have one active user
    status = queue_manager.get_status()
    assert status["active_users"] == 1

    # Check user-specific status
    user_status = await queue_manager.get_user_status(777)
    assert user_status is not None
    assert user_status["user_id"] == 777


@pytest.mark.asyncio
async def test_exception_handling():
    """Test that exceptions in handlers don't crash queue"""
    queue_manager = MessageQueueManager()
    results = []

    async def handler(update, context):
        msg = update.message.text
        if "error" in msg:
            raise ValueError(f"Intentional error in {msg}")
        results.append(msg)

    # Send good, error, good
    for msg in ["good_1", "error_msg", "good_2"]:
        update = MockUpdate(user_id=555, message_text=msg)
        await queue_manager.enqueue_message(555, update, MockContext(), handler, "test")

    await asyncio.sleep(0.5)

    assert "good_1" in results and "good_2" in results
