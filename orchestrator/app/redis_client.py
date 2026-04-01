import json
import uuid
from redis.asyncio import Redis


class RedisQueue:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _queue_key(self, phone_serial: str) -> str:
        return f"queue:{phone_serial}"

    async def push(self, phone_serial: str, payload: dict) -> str:
        task_id = str(uuid.uuid4())
        item = json.dumps({"task_id": task_id, **payload})
        await self.redis.lpush(self._queue_key(phone_serial), item)
        return task_id

    async def pop(self, phone_serial: str, timeout: int = 0) -> dict | None:
        result = await self.redis.brpop(self._queue_key(phone_serial), timeout=timeout)
        if result is None:
            return None
        _, data = result
        return json.loads(data)

    async def length(self, phone_serial: str) -> int:
        return await self.redis.llen(self._queue_key(phone_serial))
