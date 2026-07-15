"""
Rate Limiter & Anti-Flag Protection for TeraBox Bot.

Prevents account flagging by:
1. Global semaphore  — only N concurrent TeraBox operations at once
2. Per-user cooldown — user ko ek request ke baad wait karna padega
3. Minimum API delay — consecutive TeraBox calls ke beech minimum gap
4. Request counter   — hourly stats for monitoring
"""

import time
import asyncio
import logging
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────────────────────────
MAX_CONCURRENT      = 2          # max parallel TeraBox operations
USER_COOLDOWN_SEC   = 45         # seconds between requests per user
MIN_API_DELAY_SEC   = 3.0        # min seconds between any two TeraBox API calls
MAX_HOURLY_GLOBAL   = 60         # max requests per hour globally (safety valve)


# ── State ──────────────────────────────────────────────────────────────────
_semaphore          = asyncio.Semaphore(MAX_CONCURRENT)
_user_last_request  = {}          # user_id → timestamp of last completed request
_user_queued        = set()       # user_ids currently queued/processing
_last_api_call_time = 0.0         # timestamp of last TeraBox API call
_hourly_requests    = deque()     # timestamps of recent requests (rolling window)
_lock               = asyncio.Lock()


async def _wait_min_api_delay():
    """Ensure minimum gap between consecutive TeraBox API calls."""
    global _last_api_call_time
    async with _lock:
        now = time.time()
        elapsed = now - _last_api_call_time
        if elapsed < MIN_API_DELAY_SEC:
            wait = MIN_API_DELAY_SEC - elapsed
            logger.info(f"[RateLimit] API delay: sleeping {wait:.1f}s")
            await asyncio.sleep(wait)
        _last_api_call_time = time.time()


def _prune_hourly(now: float):
    """Remove timestamps older than 1 hour."""
    cutoff = now - 3600
    while _hourly_requests and _hourly_requests[0] < cutoff:
        _hourly_requests.popleft()


async def check_user_cooldown(user_id: int) -> float:
    """
    Returns seconds remaining in cooldown (0 if ready).
    """
    last = _user_last_request.get(user_id, 0)
    elapsed = time.time() - last
    remaining = max(0.0, USER_COOLDOWN_SEC - elapsed)
    return remaining


async def check_global_limit() -> bool:
    """Returns True if global hourly limit is OK, False if exceeded."""
    now = time.time()
    _prune_hourly(now)
    return len(_hourly_requests) < MAX_HOURLY_GLOBAL


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


class RequestGuard:
    """
    Context manager — acquire semaphore, enforce delays, track user cooldown.

    Usage:
        async with RequestGuard(user_id) as guard:
            info = await asyncio.to_thread(get_terabox_info, surl)
    """

    def __init__(self, user_id: int):
        self.user_id = user_id

    async def __aenter__(self):
        user_id = self.user_id

        # 1. Check if user already has a request in progress
        if user_id in _user_queued:
            raise RateLimitExceeded(
                "⏳ Tumhari request already processing mein hai. Thoda wait karo!",
                retry_after=10,
            )

        # 2. Check user cooldown
        remaining = await check_user_cooldown(user_id)
        if remaining > 0:
            raise RateLimitExceeded(
                f"⏳ Cooldown active! **{remaining:.0f} seconds** mein dubara try karo.",
                retry_after=remaining,
            )

        # 3. Check global hourly limit
        if not await check_global_limit():
            raise RateLimitExceeded(
                "⚠️ Bot bahut busy hai. Kuch minutes mein try karo.",
                retry_after=60,
            )

        # 4. Mark user as queued
        _user_queued.add(user_id)

        # 5. Acquire global semaphore (wait if MAX_CONCURRENT reached)
        logger.info(f"[RateLimit] user={user_id} acquiring semaphore...")
        await _semaphore.acquire()

        # 6. Enforce minimum API delay
        await _wait_min_api_delay()

        # 7. Record in hourly counter
        _hourly_requests.append(time.time())

        logger.info(
            f"[RateLimit] user={user_id} granted. "
            f"hourly={len(_hourly_requests)}/{MAX_HOURLY_GLOBAL}"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        user_id = self.user_id

        # Update user's last request timestamp
        _user_last_request[user_id] = time.time()

        # Release semaphore
        _semaphore.release()

        # Remove from queued set
        _user_queued.discard(user_id)

        logger.info(f"[RateLimit] user={user_id} released.")


def get_stats() -> dict:
    """Returns current rate limiter stats (for admin /stats command)."""
    now = time.time()
    _prune_hourly(now)
    return {
        "concurrent_slots_free": _semaphore._value,
        "concurrent_max": MAX_CONCURRENT,
        "hourly_requests": len(_hourly_requests),
        "hourly_max": MAX_HOURLY_GLOBAL,
        "users_in_queue": len(_user_queued),
        "user_cooldown_sec": USER_COOLDOWN_SEC,
    }
