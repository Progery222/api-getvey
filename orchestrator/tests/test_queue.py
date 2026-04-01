from app.schemas import QueueRequest
import uuid
import pytest
from unittest.mock import AsyncMock
from app.redis_client import RedisQueue


def test_queue_request_schema():
    req = QueueRequest(
        account_id=uuid.uuid4(),
        file_url="http://minio:9000/content/test.mp4",
        caption="Test",
        hashtags=["test"],
        source_service="sportzavod",
    )
    assert req.platform == "tiktok"


@pytest.mark.asyncio
async def test_push_task():
    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock(return_value=1)
    queue = RedisQueue(mock_redis)

    task_id = await queue.push("phone_001", {"file_url": "http://minio/test.mp4"})
    mock_redis.lpush.assert_called_once()
    assert task_id is not None
