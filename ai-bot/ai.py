"""Работа с Google Gemini через REST: чат, улучшение промптов, картинки и видео (Veo)."""
import asyncio
import base64

import httpx

import config

API = "https://generativelanguage.googleapis.com/v1beta"


class AIError(Exception):
    pass


def _headers() -> dict:
    return {"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"}


def _explain(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        msg = resp.text
    if resp.status_code == 429:
        return "Лимит бесплатных запросов исчерпан, попробуйте через минуту."
    if resp.status_code in (401, 403):
        return f"Ключ Gemini не подходит или нет доступа к модели: {msg[:200]}"
    return f"Ошибка Gemini ({resp.status_code}): {msg[:300]}"


async def generate(contents: list, system: str | None = None, model: str | None = None,
                   generation_config: dict | None = None, timeout: float = 120) -> dict:
    body: dict = {"contents": contents}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    if generation_config:
        body["generationConfig"] = generation_config
    url = f"{API}/models/{model or config.CHAT_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=_headers(), json=body)
    if resp.status_code != 200:
        raise AIError(_explain(resp))
    return resp.json()


def _text_of(data: dict) -> str:
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


async def chat(history: list) -> str:
    """history — список {"role": "user"|"model", "parts": [...]}."""
    data = await generate(history, system=config.SYSTEM_PROMPT)
    text = _text_of(data)
    if not text:
        reason = (data.get("candidates") or [{}])[0].get("finishReason", "")
        return f"(Модель не ответила{': ' + reason if reason else ''}. Попробуйте переформулировать.)"
    return text


ENHANCE_IMAGE = (
    "Rewrite the user's idea into ONE detailed English prompt for a photorealistic/high-end image "
    "generator. Describe subject, setting, composition, lighting, lens, mood, colors, and add quality "
    "terms (ultra detailed, 8k, sharp focus, professional photography or cinematic concept art — "
    "whichever fits). Keep the user's intent exactly. Output only the prompt, no quotes."
)
ENHANCE_VIDEO = (
    "Rewrite the user's idea into ONE detailed English prompt for a cinematic text-to-video model. "
    "Describe the scene, camera movement, lighting, mood, motion and sound/ambience. Keep the intent. "
    "Output only the prompt, no quotes."
)


async def enhance_prompt(idea: str, kind: str = "image") -> str:
    """Перевести и расписать промпт — сильно улучшает качество генерации."""
    if not config.GEMINI_API_KEY:
        return idea
    try:
        data = await generate([{"role": "user", "parts": [{"text": idea}]}],
                              system=ENHANCE_IMAGE if kind == "image" else ENHANCE_VIDEO, timeout=40)
        return _text_of(data) or idea
    except Exception:
        return idea


async def gemini_image(prompt: str, aspect: str = "1:1") -> bytes:
    data = await generate(
        [{"role": "user", "parts": [{"text": prompt}]}],
        model=config.IMAGE_MODEL_GEMINI,
        generation_config={"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect}},
        timeout=180,
    )
    for part in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise AIError("Gemini не вернул картинку (возможно, промпт заблокирован фильтром).")


async def veo_video(prompt: str, aspect: str = "16:9", on_progress=None) -> bytes:
    """Видео через Google Veo. Долгая операция: 1–6 минут."""
    url = f"{API}/models/{config.VIDEO_MODEL}:predictLongRunning"
    body = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": aspect}}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.post(url, headers=_headers(), json=body)
        if resp.status_code != 200:
            raise AIError(_explain(resp))
        op_name = resp.json()["name"]

        for i in range(72):  # до ~12 минут
            await asyncio.sleep(10)
            r = await client.get(f"{API}/{op_name}", headers=_headers())
            if r.status_code != 200:
                raise AIError(_explain(r))
            op = r.json()
            if op.get("error"):
                raise AIError(f"Veo: {op['error'].get('message', op['error'])}")
            if op.get("done"):
                samples = op.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])
                if not samples:
                    raise AIError("Veo не вернул видео (возможно, промпт заблокирован фильтром).")
                video_uri = samples[0]["video"]["uri"]
                v = await client.get(video_uri, headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=300)
                if v.status_code != 200:
                    raise AIError(f"Не удалось скачать видео ({v.status_code}).")
                return v.content
            if on_progress and i % 3 == 2:
                await on_progress((i + 1) * 10)
    raise AIError("Видео генерировалось слишком долго, попробуйте ещё раз.")
