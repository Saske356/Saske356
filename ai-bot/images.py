"""Генерация картинок. По умолчанию — Pollinations (FLUX), бесплатно и без ключа."""
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
        "enhance": "false",
        "seed": random.randint(1, 2_000_000_000),
    }
    headers = {}
    if config.POLLINATIONS_TOKEN:
        headers["Authorization"] = f"Bearer {config.POLLINATIONS_TOKEN}"
    url = f"https://image.pollinations.ai/prompt/{quote(prompt[:1500])}"
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=headers)
    if resp.status_code != 200 or not resp.headers.get("content-type", "").startswith("image"):
        raise ai.AIError(f"Сервис картинок не ответил ({resp.status_code}). Попробуйте ещё раз через минуту.")
    return resp.content


async def generate_image(prompt: str, aspect: str = "1:1") -> bytes:
    if config.IMAGE_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        try:
            return await ai.gemini_image(prompt, aspect)
        except ai.AIError:
            pass  # нет доступа/лимит — откатываемся на бесплатный вариант
    return await pollinations(prompt, aspect)
