import asyncio
import os
import httpx

HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_BASE = "https://api.heygen.com/v2"


async def create_video(script: str, avatar_id: str = "default") -> str:
    """Создаёт видео через HeyGen и возвращает URL файла."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{HEYGEN_BASE}/video/generate",
            headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"},
            json={
                "video_inputs": [{
                    "character": {"type": "avatar", "avatar_id": avatar_id},
                    "voice": {"type": "text", "input_text": script, "voice_id": "en-US-1"},
                }],
                "dimension": {"width": 1080, "height": 1920},
            },
        )
        resp.raise_for_status()
        video_id = resp.json()["data"]["video_id"]

    # Ждём завершения
    for _ in range(30):
        async with httpx.AsyncClient() as client:
            status_resp = await client.get(
                f"{HEYGEN_BASE}/video/{video_id}",
                headers={"X-Api-Key": HEYGEN_API_KEY},
            )
        data = status_resp.json()["data"]
        if data["status"] == "completed":
            return data["video_url"]
        if data["status"] == "failed":
            raise RuntimeError(f"HeyGen failed: {data.get('error')}")
        await asyncio.sleep(10)

    raise TimeoutError("HeyGen video generation timed out")
