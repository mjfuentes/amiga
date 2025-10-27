#!/usr/bin/env python3
"""
Test script to verify priority command system functionality

This script demonstrates:
1. Priority message queuing
2. Priority-based processing order
3. Graceful shutdown flow
"""

import asyncio
import sys
from pathlib import Path

# Add telegram_bot to path
sys.path.insert(0, str(Path(__file__).parent / "telegram_bot"))


async def test_priority_queue():
    """Test priority queue functionality"""
    from messaging.queue import MessageQueueManager, QueuedMessage

    print("\n=== Testing Priority Command System ===\n")

    # Create a simple handler
    async def test_handler(update, context):
        handler_name = getattr(update, 'handler_name', 'unknown')
        priority = getattr(update, 'priority', 0)
        print(f"  Executing: {handler_name} (priority={priority})")
        await asyncio.sleep(0.1)  # Simulate work

    # Create mock update/context
    class MockUpdate:
        def __init__(self, name, priority):
            self.handler_name = name
            self.priority = priority

    # Test queue
    queue_manager = MessageQueueManager()
    user_id = 12345

    print("1. Enqueueing normal messages (priority=0)...")
    for i in range(3):
        mock_update = MockUpdate(f"msg_{i}", 0)
        await queue_manager.enqueue_message(
            user_id=user_id,
            update=mock_update,
            context=None,
            handler=test_handler,
            handler_name=f"text_message_{i}",
            priority=0
        )
    print("   Queued: msg_0, msg_1, msg_2\n")

    print("2. Enqueueing priority command (priority=10)...")
    mock_update = MockUpdate("priority_restart", 10)
    await queue_manager.enqueue_message(
        user_id=user_id,
        update=mock_update,
        context=None,
        handler=test_handler,
        handler_name="restart_command",
        priority=10
    )
    print("   Queued: /restart with priority=10\n")

    print("3. Expected processing order:")
    print("   - msg_0 (if already processing)")
    print("   - restart_command (HIGH PRIORITY)")
    print("   - msg_1")
    print("   - msg_2\n")

    print("4. Waiting for queue to process...")
    # Give queue time to process
    await asyncio.sleep(1.5)

    # Get queue status
    status = queue_manager.get_status()
    print(f"\n5. Queue status after processing:")
    print(f"   - Active users: {status['active_users']}")
    for uid, queue_status in status['queues'].items():
        print(f"   - User {uid}: {queue_status['messages_processed']} processed")

    # Cleanup
    await queue_manager.cleanup_all()
    print("\n✓ Priority queue test completed\n")


def test_priority_command_detection():
    """Test is_priority_command helper"""
    from core.main import is_priority_command

    print("\n=== Testing Priority Command Detection ===\n")

    test_cases = [
        ("/start", True),
        ("/restart", True),
        ("/clear", True),
        ("/help", False),  # Not a priority command
        ("start", True),  # Without slash
        ("clear", True),
        ("restart", True),
        ("help", False),  # Not a priority command
        ("/status", False),  # Not a priority command
        ("/usage", False),
        ("Hello world", False),
        ("fix this bug", False),
        ("/start something", True),  # With arguments
        ("clear ", True),  # With trailing space
    ]

    print("Testing priority command detection:")
    all_passed = True
    for message, expected in test_cases:
        result = is_priority_command(message)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        print(f"  {status} is_priority_command('{message}') = {result} (expected {expected})")

    print()
    if all_passed:
        print("✓ All priority command detection tests passed\n")
    else:
        print("✗ Some tests failed\n")
        sys.exit(1)


async def main():
    """Run all tests"""
    try:
        test_priority_command_detection()
        await test_priority_queue()

        print("=" * 50)
        print("All tests passed successfully!")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
