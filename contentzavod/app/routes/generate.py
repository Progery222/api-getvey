from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from uuid import UUID
import httpx
import os

from ..replicate_client import generate_video

router = APIRouter(prefix="/api")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


class GenerateRequest(BaseModel):
    account_id: UUID
    prompt: str
    caption: str = ""
    hashtags: list[str] = []


@router.post("/generate")
async def generate(body: GenerateRequest):
    try:
        video_url = await generate_video(body.prompt)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/api/content/queue",
                json={
                    "account_id": str(body.account_id),
                    "file_url": video_url,
                    "content_type": "video",
                    "caption": body.caption,
                    "hashtags": body.hashtags,
                    "platform": "tiktok",
                    "source_service": "contentzavod",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal error")
