"""
Feature 1 — Redis Caching Layer
Feature 2 — Redis-backed Pagination
Feature 3 — Per-user Rate Limiting
Feature 17 — Token Replay Prevention
"""
import json
import logging
import redis.asyncio as aioredis
from info import REDIS_URL

logger = logging.getLogger(__name__)
_redis = None


async def get_redis():
    global _redis
    if _redis is None:
        try:
            _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis.ping()
            logger.info("Redis connected")
        except Exception as e:
            logger.warning(f"Redis unavailable, falling back to in-memory: {e}")
            _redis = None
    return _redis


class RedisManager:
    PREFIX = "tgbot:"

    @classmethod
    async def get(cls, key):
        r = await get_redis()
        if not r:
            return None
        try:
            val = await r.get(f"{cls.PREFIX}{key}")
            return json.loads(val) if val else None
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None

    @classmethod
    async def set(cls, key, value, ttl=None):
        r = await get_redis()
        if not r:
            return False
        try:
            s = json.dumps(value)
            if ttl:
                await r.setex(f"{cls.PREFIX}{key}", ttl, s)
            else:
                await r.set(f"{cls.PREFIX}{key}", s)
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            return False

    @classmethod
    async def delete(cls, key):
        r = await get_redis()
        if not r:
            return False
        try:
            await r.delete(f"{cls.PREFIX}{key}")
            return True
        except Exception as e:
            logger.error(f"Redis DEL error: {e}")
            return False

    @classmethod
    async def incr(cls, key, ttl=None):
        r = await get_redis()
        if not r:
            return 0
        try:
            full = f"{cls.PREFIX}{key}"
            val = await r.incr(full)
            if ttl and val == 1:
                await r.expire(full, ttl)
            return val
        except Exception as e:
            logger.error(f"Redis INCR error: {e}")
            return 0

    # ── banned lists ──────────────────────────────────────
    @classmethod
    async def get_banned_users(cls):
        return await cls.get("banned_users") or []

    @classmethod
    async def set_banned_users(cls, users):
        await cls.set("banned_users", users)

    @classmethod
    async def get_banned_chats(cls):
        return await cls.get("banned_chats") or []

    @classmethod
    async def set_banned_chats(cls, chats):
        await cls.set("banned_chats", chats)

    # ── group settings ─────────────────────────────────────
    @classmethod
    async def get_settings(cls, group_id):
        return await cls.get(f"settings:{group_id}")

    @classmethod
    async def set_settings(cls, group_id, settings, ttl=3600):
        await cls.set(f"settings:{group_id}", settings, ttl=ttl)

    # ── verification (Feature 17 — replay prevention) ─────
    @classmethod
    async def set_verify_token(cls, user_id, token, ttl=43200):
        await cls.set(f"verify_token:{user_id}", token, ttl=ttl)

    @classmethod
    async def get_verify_token(cls, user_id):
        return await cls.get(f"verify_token:{user_id}")

    @classmethod
    async def mark_token_used(cls, user_id, token):
        """Persist used state for 24 h so restarts don't re-validate old tokens."""
        await cls.set(f"used_token:{user_id}:{token}", True, ttl=86400)

    @classmethod
    async def is_token_used(cls, user_id, token):
        r = await get_redis()
        if not r:
            return False
        return await r.exists(f"{cls.PREFIX}used_token:{user_id}:{token}") > 0

    # ── verify status ──────────────────────────────────────
    @classmethod
    async def get_verify_status(cls, user_id):
        return await cls.get(f"verify_status:{user_id}")

    @classmethod
    async def set_verify_status(cls, user_id, status):
        await cls.set(f"verify_status:{user_id}", status, ttl=86400)

    # ── search result cache ────────────────────────────────
    @classmethod
    async def get_search_cache(cls, query_hash):
        return await cls.get(f"search:{query_hash}")

    @classmethod
    async def set_search_cache(cls, query_hash, results, ttl=300):
        await cls.set(f"search:{query_hash}", results, ttl=ttl)

    # ── Feature 2 — pagination state ──────────────────────
    @classmethod
    async def get_pagination(cls, key):
        return await cls.get(f"pagination:{key}")

    @classmethod
    async def set_pagination(cls, key, data, ttl=600):
        await cls.set(f"pagination:{key}", data, ttl=ttl)


class RateLimiter:
    """Feature 3 — per-user sliding-window rate limiting."""

    @classmethod
    async def check(cls, user_id: int, action: str = "search",
                    limit: int = 5, window: int = 10) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        count = await RedisManager.incr(f"rate:{action}:{user_id}", ttl=window)
        return count <= limit

    @classmethod
    async def remaining(cls, user_id: int, action: str = "search",
                        limit: int = 5) -> int:
        r = await get_redis()
        if not r:
            return limit
        val = await r.get(f"{RedisManager.PREFIX}rate:{action}:{user_id}")
        return max(0, limit - int(val)) if val else limit
