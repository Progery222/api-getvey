import asyncio
import json
import os
import logging
from datetime import datetime
from redis.asyncio import Redis
from adb_controller import ADBController
from tiktok_publisher import TikTokPublisher

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PHONE_SERIAL = os.environ["PHONE_SERIAL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


async def report_status(task_id: str, status: str) -> None:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{ORCHESTRATOR_URL}/api/content/tasks/{task_id}/status",
                json={"status": status},
            )
    except Exception as e:
        log.warning(f"Failed to report status for task {task_id}: {e}")


async def run_worker():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    adb = ADBController(serial=PHONE_SERIAL)
    publisher = TikTokPublisher(adb)
    queue_key = f"queue:{PHONE_SERIAL}"

    log.info(f"Worker started for phone {PHONE_SERIAL}")

    while True:
        result = await redis.brpop(queue_key, timeout=5)
        if result is None:
            continue

        _, raw = result
        task = json.loads(raw)
        task_id = task["task_id"]

        scheduled_at = datetime.fromisoformat(task["scheduled_at"])
        now = datetime.utcnow()
        if scheduled_at > now:
            wait_seconds = (scheduled_at - now).total_seconds()
            log.info(f"Task {task_id}: waiting {wait_seconds:.0f}s until {scheduled_at}")
            await asyncio.sleep(wait_seconds)

        log.info(f"Task {task_id}: publishing...")
        try:
            await publisher.publish(
                file_url=task["file_url"],
                caption=task.get("caption", ""),
                hashtags=task.get("hashtags", []),
            )
            await report_status(task_id, "done")
            log.info(f"Task {task_id}: done")
        except Exception as e:
            log.error(f"Task {task_id} failed: {e}")
            await report_status(task_id, "failed")


if __name__ == "__main__":
    asyncio.run(run_worker())
