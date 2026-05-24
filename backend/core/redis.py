# ore / redis.py
import json
from typing import Any

from redis.asyncio import Redis, from_url

from core.config import settings

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def check_redis() -> None:
    """Used in /health/ready endpoint."""
    r = await get_redis()
    await r.ping()


def _k(key: str) -> str:
    """Apply env prefix to all keys: local:pl:monthly:..."""
    return f"{settings.REDIS_PREFIX}:{key}"


# ── Cache ─────────────────────────────────────────────────────────────────────


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    val = await r.get(_k(key))
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    r = await get_redis()
    data = json.dumps(value) if not isinstance(value, str) else value
    await r.set(_k(key), data, ex=ttl)


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(_k(key))


async def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching pattern e.g. 'pl:monthly:*'"""
    r = await get_redis()
    keys = [k async for k in r.scan_iter(_k(pattern))]
    if keys:
        await r.delete(*keys)


# ── Rate limiting ─────────────────────────────────────────────────────────────


async def rate_limit_check(identifier: str, limit: int, window_secs: int = 60) -> bool:
    """True = allowed. False = rate limit exceeded."""
    r = await get_redis()
    key = _k(f"ratelimit:{identifier}")
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window_secs)
    return count <= limit


# ── Alert throttle ────────────────────────────────────────────────────────────


async def should_send_alert(alert_type: str, identifier: str, ttl_secs: int = 43200) -> bool:
    """True = send alert (first time). False = already sent within TTL."""
    r = await get_redis()
    key = _k(f"alert:{alert_type}:{identifier}")
    result = await r.set(key, 1, ex=ttl_secs, nx=True)  # SET IF NOT EXISTS
    return result is not None


# ── JWT blocklist (for logout) ────────────────────────────────────────────────


async def blocklist_token(jti: str, ttl_secs: int) -> None:
    r = await get_redis()
    await r.set(_k(f"blocklist:{jti}"), 1, ex=ttl_secs)


async def is_token_blocked(jti: str) -> bool:
    r = await get_redis()
    return bool(await r.exists(_k(f"blocklist:{jti}")))
