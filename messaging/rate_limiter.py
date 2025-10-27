"""
Rate limiting for request throttling
Phase 7: Production hardening
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""

    requests_per_minute: int = 10
    requests_per_hour: int = 100
    burst_size: int = 3  # Allow small bursts
    cooldown_seconds: int = 60  # Cooldown after hitting limit


class RateLimiter:
    """Rate limiter with per-user tracking and queue system"""

    def __init__(self):
        self.user_requests: dict[int, deque] = {}  # user_id -> deque of timestamps
        self.user_cooldowns: dict[int, datetime] = {}  # user_id -> cooldown end time
        self.config = RateLimitConfig()
        self.queues: dict[int, asyncio.Queue] = {}  # user_id -> request queue

        logger.info("RateLimiter initialized")

    def _get_user_requests(self, user_id: int) -> deque:
        """Get request history for user"""
        if user_id not in self.user_requests:
            self.user_requests[user_id] = deque()
        return self.user_requests[user_id]

    def _cleanup_old_requests(self, user_id: int):
        """Remove old request timestamps outside tracking window"""
        requests = self._get_user_requests(user_id)
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)

        # Remove requests older than 1 hour
        while requests and requests[0] < hour_ago:
            requests.popleft()

    def _count_recent_requests(self, user_id: int, window: timedelta) -> int:
        """Count requests within time window"""
        requests = self._get_user_requests(user_id)
        now = datetime.now()
        cutoff = now - window

        return sum(1 for timestamp in requests if timestamp >= cutoff)

    def check_rate_limit(self, user_id: int) -> tuple[bool, str | None]:
        """
        Check if user can make a request
        Returns: (allowed, error_message)
        """
        now = datetime.now()

        # Check if user is in cooldown
        if user_id in self.user_cooldowns:
            cooldown_end = self.user_cooldowns[user_id]
            if now < cooldown_end:
                remaining = int((cooldown_end - now).total_seconds())
                return False, f"Rate limit exceeded. Please wait {remaining}s before trying again."
            else:
                # Cooldown expired
                del self.user_cooldowns[user_id]

        # Clean up old requests
        self._cleanup_old_requests(user_id)

        # Check per-minute limit
        minute_count = self._count_recent_requests(user_id, timedelta(minutes=1))
        if minute_count >= self.config.requests_per_minute:
            # Start cooldown
            self.user_cooldowns[user_id] = now + timedelta(seconds=self.config.cooldown_seconds)
            logger.warning(f"User {user_id} exceeded per-minute rate limit ({minute_count} requests)")
            return (
                False,
                f"Too many requests. Limit: {self.config.requests_per_minute}/minute. Please wait {self.config.cooldown_seconds}s.",
            )

        # Check per-hour limit
        hour_count = self._count_recent_requests(user_id, timedelta(hours=1))
        if hour_count >= self.config.requests_per_hour:
            # Start cooldown
            self.user_cooldowns[user_id] = now + timedelta(seconds=self.config.cooldown_seconds)
            logger.warning(f"User {user_id} exceeded per-hour rate limit ({hour_count} requests)")
            return False, f"Too many requests. Limit: {self.config.requests_per_hour}/hour. Please try again later."

        # Check burst limit (recent requests in last 5 seconds)
        burst_count = self._count_recent_requests(user_id, timedelta(seconds=5))
        if burst_count >= self.config.burst_size:
            logger.warning(f"User {user_id} burst limit reached ({burst_count} requests in 5s)")
            return False, "Please slow down. Wait a few seconds between requests."

        return True, None

    def record_request(self, user_id: int):
        """Record that user made a request"""
        requests = self._get_user_requests(user_id)
        requests.append(datetime.now())

        # Clean up periodically
        self._cleanup_old_requests(user_id)

        logger.debug(f"Recorded request for user {user_id} (total in last hour: {len(requests)})")

    def get_user_stats(self, user_id: int) -> dict:
        """Get rate limit stats for user"""
        self._cleanup_old_requests(user_id)

        minute_count = self._count_recent_requests(user_id, timedelta(minutes=1))
        hour_count = self._count_recent_requests(user_id, timedelta(hours=1))

        in_cooldown = user_id in self.user_cooldowns
        cooldown_remaining = 0
        if in_cooldown:
            cooldown_end = self.user_cooldowns[user_id]
            now = datetime.now()
            if now < cooldown_end:
                cooldown_remaining = int((cooldown_end - now).total_seconds())
            else:
                in_cooldown = False

        return {
            "requests_last_minute": minute_count,
            "requests_last_hour": hour_count,
            "limit_per_minute": self.config.requests_per_minute,
            "limit_per_hour": self.config.requests_per_hour,
            "in_cooldown": in_cooldown,
            "cooldown_remaining": cooldown_remaining,
            "minute_percentage": (minute_count / self.config.requests_per_minute) * 100,
            "hour_percentage": (hour_count / self.config.requests_per_hour) * 100,
        }

    async def throttle(self, user_id: int) -> bool:
        """
        Throttle request with queue system for burst handling
        Returns: True if request should proceed, False if dropped
        """
        # Check rate limit
        allowed, error_msg = self.check_rate_limit(user_id)

        if allowed:
            # Record and proceed immediately
            self.record_request(user_id)
            return True

        # Rate limited - could implement queue here
        logger.info(f"Rate limited user {user_id}: {error_msg}")
        return False

    def reset_user(self, user_id: int):
        """Reset rate limits for a user (admin function)"""
        if user_id in self.user_requests:
            del self.user_requests[user_id]
        if user_id in self.user_cooldowns:
            del self.user_cooldowns[user_id]

        logger.info(f"Reset rate limits for user {user_id}")

    def configure(
        self,
        requests_per_minute: int | None = None,
        requests_per_hour: int | None = None,
        burst_size: int | None = None,
        cooldown_seconds: int | None = None,
    ):
        """Update rate limit configuration"""
        if requests_per_minute is not None:
            self.config.requests_per_minute = requests_per_minute
        if requests_per_hour is not None:
            self.config.requests_per_hour = requests_per_hour
        if burst_size is not None:
            self.config.burst_size = burst_size
        if cooldown_seconds is not None:
            self.config.cooldown_seconds = cooldown_seconds

        logger.info(f"Rate limit config updated: {self.config}")
