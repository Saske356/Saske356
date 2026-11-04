"""Генерация картинок: OpenRouter (Nano Banana), Gemini или бесплатный Pollinations (FLUX)."""
import asyncio
import random
from urllib.parse import quote

import httpx

import ai
import config

SIZES = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
}


async def pollinations(prompt: str, aspect: str = "1:1") -> bytes:
    w, h = SIZES.get(aspect, SIZES["1:1"])
    params = {
        "width": w,
        "height": h,
        "model": config.POLLINATIONS_MODEL,
        "nologo": "true",
        "seed": random.randint(1, 2_000_000_000),
    }
    headers = {}
    if config.POLLINATIONS_TOKEN:
        headers["Authorization"] = f"Bearer {config.POLLINATIONS_TOKEN}"
    # Бесплатный сервис плохо переносит длинные промпты и очередь — короче промпт и пара повторов.
    url = f"https://image.pollinations.ai/prompt/{quote(prompt[:450])}"
    last = ""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                return resp.content
            last = f"код {resp.status_code}"
        except httpx.HTTPError as e:
            last = type(e).__name__
        await asyncio.sleep(5 * (attempt + 1))
    raise ai.AIError(f"Бесплатный сервис картинок сейчас недоступен ({last}). Попробуйте позже или смените модель в /model.")


async def generate_image(prompt: str, aspect: str = "1:1", model: str | None = None) -> bytes:
    if model == "pollinations":
        return await pollinations(prompt, aspect)
    if config.IMAGE_PROVIDER == "openrouter" and config.OPENROUTER_API_KEY:
        return await ai.openrouter_image(prompt, aspect, model)  # платно — без тихого отката на худшее качество
    if config.IMAGE_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        try:
            return await ai.gemini_image(prompt, aspect)
        except ai.AIError:
            pass  # нет доступа/лимит — откатываемся на бесплатный вариант
    return await pollinations(prompt, aspect)
