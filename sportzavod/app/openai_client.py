import os
from openai import AsyncOpenAI

_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


async def generate_script(sport: str, team: str, event: str) -> str:
    prompt = (
        f"Создай короткий (15-30 сек) спортивный комментарий для TikTok видео. "
        f"Спорт: {sport}. Команда: {team}. Событие: {event}. "
        f"Стиль: энергичный, молодёжный. Только текст, без хэштегов."
    )
    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()
