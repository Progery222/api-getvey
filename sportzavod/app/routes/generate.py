from fastapi import APIRouter
from pydantic import BaseModel
from uuid import UUID
import httpx
import os

from ..openai_client import generate_script
from ..heygen_client import create_video

router = APIRouter(prefix="/api")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


class GenerateRequest(BaseModel):
    account_id: UUID
    sport: str
    team: str
    event: str
    hashtags: list[str] = []


async def generate_and_queue(body: GenerateRequest) -> dict:
    script = await generate_script(body.sport, body.team, body.event)
    video_url = await create_video(script)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ORCHESTRATOR_URL}/api/content/queue",
            json={
                "account_id": str(body.account_id),
                "file_url": video_url,
                "content_type": "video",
                "caption": script[:150],
                "hashtags": body.hashtags or [body.sport, body.team.lower()],
                "platform": "tiktok",
                "source_service": "sportzavod",
            },
        )
        resp.raise_for_status()
        return resp.json()


@router.post("/generate")
async def generate(body: GenerateRequest):
    return await generate_and_queue(body)
