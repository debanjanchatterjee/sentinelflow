import os
import json
from typing import Any, Dict, Optional, List, Tuple

TESTING = os.getenv("TESTING") == "1"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

if not TESTING:
    import redis.asyncio as redis  # type: ignore
    RedisClient = redis.Redis
else:
    RedisClient = None

# Simple key names
READY_QUEUE = "ready_queue"
JOBS_HASH = "jobs"
SCHEDULED_ZSET = "scheduled_zset"


class AsyncInMemoryRedis:
    def __init__(self):
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._lists: Dict[str, List[str]] = {}
        self._zsets: Dict[str, Dict[str, float]] = {}

    async def hset(self, name: str, key: str, value: str):
        h = self._hashes.setdefault(name, {})
        h[key] = value
        return 1

    async def hget(self, name: str, key: str) -> Optional[str]:
        h = self._hashes.get(name, {})
        return h.get(key)

    async def hgetall(self, name: str) -> Dict[str, str]:
        return dict(self._hashes.get(name, {}))

    async def rpush(self, name: str, *values: str):
        lst = self._lists.setdefault(name, [])
        for v in values:
            lst.append(v)
        return len(lst)

    async def lpop(self, name: str) -> Optional[str]:
        lst = self._lists.get(name, [])
        if not lst:
            return None
        return lst.pop(0)

    # zset methods
    async def zadd(self, name: str, mapping: Dict[str, float]):
        z = self._zsets.setdefault(name, {})
        added = 0
        for member, score in mapping.items():
            if member not in z:
                added += 1
            z[member] = score
        return added

    async def zrangebyscore(self, name: str, min_score: float, max_score: float) -> List[str]:
        z = self._zsets.get(name, {})
        return [m for m, s in z.items() if min_score <= s <= max_score]

    async def zrem(self, name: str, *members: str) -> int:
        z = self._zsets.get(name, {})
        removed = 0
        for m in members:
            if m in z:
                del z[m]
                removed += 1
        return removed

    async def zpopmin(self, name: str, count: int = 1) -> List[Tuple[str, float]]:
        z = self._zsets.get(name, {})
        if not z:
            return []
        # Get members sorted by score
        items = sorted(z.items(), key=lambda kv: kv[1])
        popped = items[:count]
        for m, _ in popped:
            del z[m]
        return popped


# Singleton in-memory client for testing
_inmemory_client: Optional[AsyncInMemoryRedis] = None


async def get_redis():
    global _inmemory_client
    if TESTING:
        if _inmemory_client is None:
            _inmemory_client = AsyncInMemoryRedis()
        return _inmemory_client
    else:
        return RedisClient.from_url(REDIS_URL, decode_responses=True)  # type: ignore


# Basic helpers
async def enqueue_job(redis_client, job_id: str, payload: Dict[str, Any]):
    # Store job metadata in a hash and push job_id onto ready queue
    await redis_client.hset(JOBS_HASH, job_id, json.dumps(payload))
    await redis_client.rpush(READY_QUEUE, job_id)


async def schedule_job(redis_client, job_id: str, payload: Dict[str, Any], score: float):
    # Store job metadata and add to scheduled zset with timestamp score
    await redis_client.hset(JOBS_HASH, job_id, json.dumps(payload))
    # zadd expects mapping member->score
    if TESTING:
        await redis_client.zadd(SCHEDULED_ZSET, {job_id: score})
    else:
        await redis_client.zadd(SCHEDULED_ZSET, {job_id: score})


async def pop_due_jobs(redis_client, max_score: float, count: int = 100) -> List[str]:
    """Atomically pop up to `count` jobs from scheduled_zset with score <= max_score.
    Returns a list of job_ids removed from the zset.
    """
    if TESTING:
        pairs = await redis_client.zpopmin(SCHEDULED_ZSET, count)
        # pairs is list of (member, score)
        due = [m for m, s in pairs if s <= max_score]
        # If any popped had score > max_score, push them back
        for m, s in pairs:
            if s > max_score:
                await redis_client.zadd(SCHEDULED_ZSET, {m: s})
        return due
    else:
        # Redis 6.2+ supports ZPOPMIN
        pairs = await redis_client.zpopmin(SCHEDULED_ZSET, count)
        # pairs may be list of (member, score) or flat list depending on client; normalize
        # redis-py returns list of (member, score)
        due = [m for m, s in pairs if s <= max_score]
        # push back any with score > max_score
        for m, s in pairs:
            if s > max_score:
                await redis_client.zadd(SCHEDULED_ZSET, {m: s})
        return due


async def get_job(redis_client, job_id: str) -> Optional[Dict[str, Any]]:
    raw = await redis_client.hget(JOBS_HASH, job_id)
    if raw is None:
        return None
    return json.loads(raw)


async def list_jobs(redis_client) -> List[Dict[str, Any]]:
    all_items = await redis_client.hgetall(JOBS_HASH)
    return [json.loads(v) for v in all_items.values()]


async def set_job(redis_client, job_id: str, payload: Dict[str, Any]):
    await redis_client.hset(JOBS_HASH, job_id, json.dumps(payload))


async def pop_ready(redis_client) -> Optional[str]:
    job_id = await redis_client.lpop(READY_QUEUE)
    return job_id
