from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from ..database import get_db
from ..models import Phone, ContentTask, TaskStatus
from ..schemas import QueueRequest, QueueResponse
from ..scheduler import SmartScheduler
from ..redis_client import RedisQueue
from redis.asyncio import Redis
import os

router = APIRouter(prefix="/api/content")
scheduler = SmartScheduler()


async def get_redis() -> Redis:
    return Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


@router.post("/queue", response_model=QueueResponse)
async def queue_content(
    body: QueueRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Phone).where(Phone.account_id == body.account_id))
    phone = result.scalar_one_or_none()
    if phone is None:
        raise HTTPException(status_code=404, detail="Phone not found for account_id")

    last_task_result = await db.execute(
        select(ContentTask)
        .where(ContentTask.phone_id == phone.id, ContentTask.status == TaskStatus.done)
        .order_by(ContentTask.scheduled_at.desc())
        .limit(1)
    )
    last_task = last_task_result.scalar_one_or_none()
    last_post_at = last_task.scheduled_at if last_task else None

    scheduled_at = scheduler.next_scheduled_at(
        {"warmup_days": phone.warmup_days, "error_count": phone.error_count, "timezone": phone.timezone},
        last_post_at=last_post_at,
    )

    task = ContentTask(
        phone_id=phone.id,
        account_id=body.account_id,
        file_url=body.file_url,
        caption=body.caption,
        hashtags=json.dumps(body.hashtags),
        platform=body.platform,
        source_service=body.source_service,
        status=TaskStatus.scheduled,
        scheduled_at=scheduled_at,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    redis = await get_redis()
    queue = RedisQueue(redis)
    await queue.push(phone.serial, {
        "task_id": str(task.id),
        "file_url": body.file_url,
        "caption": body.caption,
        "hashtags": body.hashtags,
        "platform": body.platform,
        "scheduled_at": scheduled_at.isoformat(),
    })

    return QueueResponse(
        task_id=task.id,
        scheduled_at=scheduled_at.isoformat(),
        status=task.status.value,
    )
