from pydantic import BaseModel, Field
from uuid import UUID
from typing import Literal


class QueueRequest(BaseModel):
    account_id: UUID
    file_url: str = Field(..., description="MinIO URL видео")
    content_type: Literal["video", "image"] = "video"
    caption: str = ""
    hashtags: list[str] = []
    platform: Literal["tiktok"] = "tiktok"
    source_service: str = Field(..., description="sportzavod | contentzavod")


class QueueResponse(BaseModel):
    task_id: UUID
    scheduled_at: str
    status: str
