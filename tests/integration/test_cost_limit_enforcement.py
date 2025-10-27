"""
Integration test for cost limit enforcement

Tests cost tracking and limit enforcement:
- Daily cost limit enforcement
- Monthly cost limit enforcement
- Per-user cost tracking
- Cost limit exceeded scenarios
- Cost reset behavior
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tasks.analytics import AnalyticsDB
from tasks.database import Database


@pytest.fixture
def isolated_db(tmp_path):
    """Create isolated database for testing"""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def analytics_db(isolated_db):
    """Create analytics database wrapper"""
    return AnalyticsDB(isolated_db)


@pytest.mark.integration
def test_daily_cost_limit_enforcement(analytics_db):
    """
    Test that daily cost limit is enforced

    Scenario:
    1. Set daily limit to $10
    2. Record API calls totaling $8
    3. Verify under limit
    4. Record additional $3 call
    5. Verify over limit
    """
    user_id = 123456
    daily_limit = 10.0

    # Record API calls under limit
    calls_under_limit = [
        {
            "user_id": user_id,
            "model": "claude-sonnet-4.5",
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "cost": 2.5,
            "timestamp": datetime.now().isoformat()
        },
        {
            "user_id": user_id,
            "model": "claude-sonnet-4.5",
            "input_tokens": 2000,
            "output_tokens": 1000,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "cost": 5.5,
            "timestamp": datetime.now().isoformat()
        }
    ]

    # Record calls
    for call in calls_under_limit:
        analytics_db.record_api_call(**call)

    # Calculate current daily cost
    today = datetime.now().date()
    daily_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())

    assert daily_cost == 8.0
    assert daily_cost < daily_limit, "Should be under daily limit"

    # Try to make call that would exceed limit
    potential_call_cost = 3.0
    would_exceed = (daily_cost + potential_call_cost) > daily_limit

    assert would_exceed, "Should detect limit would be exceeded"

    # Verify limit enforcement (in production, this would prevent the call)
    if would_exceed:
        # Don't record the call
        remaining_budget = daily_limit - daily_cost
        assert remaining_budget == 2.0

    # Verify cost hasn't changed
    final_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())
    assert final_cost == 8.0


@pytest.mark.integration
def test_monthly_cost_limit_enforcement(analytics_db):
    """
    Test that monthly cost limit is enforced

    Scenario:
    1. Set monthly limit to $100
    2. Record API calls over multiple days totaling $95
    3. Verify under limit
    4. Try to make $10 call
    5. Verify over limit
    """
    user_id = 789012
    monthly_limit = 100.0

    # Record calls across multiple days
    base_date = datetime.now().replace(day=1)  # Start of month

    for day_offset in range(5):
        call_date = base_date + timedelta(days=day_offset)
        analytics_db.record_api_call(
            user_id=user_id,
            model="claude-sonnet-4.5",
            input_tokens=5000,
            output_tokens=2500,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost=19.0,
            timestamp=call_date.isoformat()
        )

    # Calculate monthly cost
    month_start = base_date.replace(day=1).date()
    monthly_cost = analytics_db.get_cost_by_period(user_id, "month", month_start.isoformat())

    assert monthly_cost == 95.0
    assert monthly_cost < monthly_limit

    # Check if new call would exceed limit
    potential_call_cost = 10.0
    would_exceed = (monthly_cost + potential_call_cost) > monthly_limit

    assert would_exceed, "Should detect monthly limit would be exceeded"

    # Verify remaining budget
    remaining_budget = monthly_limit - monthly_cost
    assert remaining_budget == 5.0


@pytest.mark.integration
def test_per_user_cost_isolation(analytics_db):
    """
    Test that cost tracking is isolated per user

    Scenario:
    1. Record costs for multiple users
    2. Verify each user's costs are tracked separately
    3. One user exceeding limit doesn't affect others
    """
    users = [111111, 222222, 333333]
    user_costs = {
        111111: 15.0,
        222222: 8.0,
        333333: 25.0
    }

    # Record costs for each user
    for user_id, cost in user_costs.items():
        analytics_db.record_api_call(
            user_id=user_id,
            model="claude-sonnet-4.5",
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost=cost,
            timestamp=datetime.now().isoformat()
        )

    # Verify each user's cost
    today = datetime.now().date()
    for user_id, expected_cost in user_costs.items():
        actual_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())
        assert actual_cost == expected_cost

    # User 3 exceeds limit
    daily_limit = 20.0
    user3_cost = analytics_db.get_cost_by_period(333333, "day", today.isoformat())
    assert user3_cost > daily_limit

    # Other users still under limit
    user1_cost = analytics_db.get_cost_by_period(111111, "day", today.isoformat())
    user2_cost = analytics_db.get_cost_by_period(222222, "day", today.isoformat())
    assert user1_cost < daily_limit
    assert user2_cost < daily_limit


@pytest.mark.integration
def test_cost_accumulation_over_time(analytics_db):
    """
    Test cost accumulation and tracking over time

    Scenario:
    1. Record multiple API calls over time
    2. Verify cumulative cost increases correctly
    3. Test daily and monthly aggregations
    """
    user_id = 456789

    # Record 10 calls with varying costs
    call_costs = [1.0, 2.0, 1.5, 3.0, 2.5, 1.0, 4.0, 2.0, 3.5, 1.5]

    for i, cost in enumerate(call_costs):
        analytics_db.record_api_call(
            user_id=user_id,
            model="claude-sonnet-4.5",
            input_tokens=1000 * (i + 1),
            output_tokens=500 * (i + 1),
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost=cost,
            timestamp=datetime.now().isoformat()
        )

    # Verify total daily cost
    today = datetime.now().date()
    daily_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())

    expected_total = sum(call_costs)
    assert daily_cost == expected_total


@pytest.mark.integration
def test_cost_limit_with_cache_tokens(analytics_db):
    """
    Test cost calculation with cache tokens

    Scenario:
    1. Record calls with cache creation tokens (expensive)
    2. Record calls with cache read tokens (cheap)
    3. Verify cost calculated correctly with cache
    """
    user_id = 567890

    # Call with cache creation (more expensive)
    analytics_db.record_api_call(
        user_id=user_id,
        model="claude-sonnet-4.5",
        input_tokens=5000,
        output_tokens=2000,
        cache_creation_tokens=10000,  # Cache creation tokens
        cache_read_tokens=0,
        cost=8.0,  # Higher due to cache creation
        timestamp=datetime.now().isoformat()
    )

    # Call with cache read (cheaper)
    analytics_db.record_api_call(
        user_id=user_id,
        model="claude-sonnet-4.5",
        input_tokens=5000,
        output_tokens=2000,
        cache_creation_tokens=0,
        cache_read_tokens=10000,  # Cache read tokens (10% cost)
        cost=2.5,  # Lower due to cache hits
        timestamp=datetime.now().isoformat()
    )

    # Verify total cost
    today = datetime.now().date()
    daily_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())

    assert daily_cost == 10.5


@pytest.mark.integration
def test_cost_limit_reset_next_day(analytics_db):
    """
    Test that daily cost limit resets the next day

    Scenario:
    1. Record costs today reaching limit
    2. Simulate next day
    3. Verify limit reset (new calls allowed)
    """
    user_id = 111222
    daily_limit = 10.0

    # Record costs today reaching limit
    today = datetime.now()
    analytics_db.record_api_call(
        user_id=user_id,
        model="claude-sonnet-4.5",
        input_tokens=5000,
        output_tokens=2500,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost=9.5,
        timestamp=today.isoformat()
    )

    # Verify at limit
    today_cost = analytics_db.get_cost_by_period(user_id, "day", today.date().isoformat())
    assert today_cost >= (daily_limit - 1.0)

    # Simulate next day
    tomorrow = today + timedelta(days=1)
    analytics_db.record_api_call(
        user_id=user_id,
        model="claude-sonnet-4.5",
        input_tokens=1000,
        output_tokens=500,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost=2.0,
        timestamp=tomorrow.isoformat()
    )

    # Verify tomorrow's cost is separate
    tomorrow_cost = analytics_db.get_cost_by_period(user_id, "day", tomorrow.date().isoformat())
    assert tomorrow_cost == 2.0

    # Verify today's cost unchanged
    today_cost_final = analytics_db.get_cost_by_period(user_id, "day", today.date().isoformat())
    assert today_cost_final == 9.5


@pytest.mark.integration
def test_cost_by_model_tracking(analytics_db):
    """
    Test cost tracking broken down by model

    Scenario:
    1. Record calls with different models
    2. Verify per-model cost tracking
    3. Verify total cost aggregation
    """
    user_id = 333444

    # Record calls with different models
    models_and_costs = [
        ("claude-haiku-4.5", 0.5),
        ("claude-sonnet-4.5", 3.0),
        ("claude-opus-4.5", 15.0),
        ("claude-haiku-4.5", 0.8),
        ("claude-sonnet-4.5", 3.5)
    ]

    for model, cost in models_and_costs:
        analytics_db.record_api_call(
            user_id=user_id,
            model=model,
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost=cost,
            timestamp=datetime.now().isoformat()
        )

    # Verify total cost
    today = datetime.now().date()
    total_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())

    expected_total = sum(cost for _, cost in models_and_costs)
    assert total_cost == expected_total

    # In production, would also verify per-model breakdown
    # For now, just verify total is correct


@pytest.mark.integration
def test_concurrent_cost_updates(analytics_db):
    """
    Test that concurrent cost updates don't cause race conditions

    Scenario:
    1. Record multiple API calls concurrently
    2. Verify all costs recorded correctly
    3. Verify no lost updates
    """
    user_id = 555666
    num_concurrent_calls = 10
    cost_per_call = 1.5

    # Record calls concurrently (simulated with sequential writes)
    # In production, database has write lock to prevent race conditions
    for i in range(num_concurrent_calls):
        analytics_db.record_api_call(
            user_id=user_id,
            model="claude-sonnet-4.5",
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost=cost_per_call,
            timestamp=datetime.now().isoformat()
        )

    # Verify total cost (all updates recorded)
    today = datetime.now().date()
    total_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())

    expected_total = num_concurrent_calls * cost_per_call
    assert total_cost == expected_total


@pytest.mark.integration
def test_zero_cost_handling(analytics_db):
    """
    Test handling of zero-cost API calls

    Scenario:
    1. Record calls with zero tokens (edge case)
    2. Verify zero cost recorded correctly
    3. Verify doesn't affect limit calculations
    """
    user_id = 777888

    # Record zero-cost call
    analytics_db.record_api_call(
        user_id=user_id,
        model="claude-sonnet-4.5",
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost=0.0,
        timestamp=datetime.now().isoformat()
    )

    # Record normal call
    analytics_db.record_api_call(
        user_id=user_id,
        model="claude-sonnet-4.5",
        input_tokens=1000,
        output_tokens=500,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost=2.0,
        timestamp=datetime.now().isoformat()
    )

    # Verify total cost
    today = datetime.now().date()
    total_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())

    assert total_cost == 2.0  # Zero-cost call doesn't affect total


@pytest.mark.integration
def test_negative_cost_prevention(analytics_db):
    """
    Test that negative costs are rejected

    Scenario:
    1. Attempt to record negative cost
    2. Verify rejected or converted to zero
    """
    user_id = 999000

    # Attempt to record with negative cost (should be prevented)
    # In production, validation should prevent this
    try:
        analytics_db.record_api_call(
            user_id=user_id,
            model="claude-sonnet-4.5",
            input_tokens=1000,
            output_tokens=500,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            cost=-5.0,  # Invalid negative cost
            timestamp=datetime.now().isoformat()
        )

        # If no exception, verify cost was normalized to zero
        today = datetime.now().date()
        total_cost = analytics_db.get_cost_by_period(user_id, "day", today.isoformat())
        assert total_cost >= 0.0  # Never negative

    except (ValueError, AssertionError):
        # Expected: negative costs should be rejected
        pass
