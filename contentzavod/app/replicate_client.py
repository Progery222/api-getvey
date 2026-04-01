import asyncio
import os
import replicate

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")


async def generate_video(prompt: str, duration_seconds: int = 5) -> str:
    """Генерирует видео через Replicate (например, Stable Video Diffusion)."""
    output = await asyncio.to_thread(
        replicate.run,
        "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
        input={
            "input_image": prompt,   # или URL картинки
            "frames_per_second": 8,
            "sizing_strategy": "crop_to_16_9",
            "motion_bucket_id": 127,
            "cond_aug": 0.02,
        },
    )
    # output — список URL
    return output[0] if isinstance(output, list) else str(output)
