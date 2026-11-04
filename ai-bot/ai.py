"""ИИ-провайдеры: OpenRouter (по умолчанию) и Google Gemini.

История диалога хранится в нейтральном виде:
    {"role": "user" | "assistant", "text": "...", "image_b64": "..." (необязательно)}
и переводится в формат нужного провайдера перед запросом.
"""
import asyncio
import base64

import httpx

import budget
import config

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
OPENROUTER_API = "https://openrouter.ai/api/v1/chat/completions"


class AIError(Exception):
    pass


# =============================================================
#  OpenRouter
# =============================================================

def _or_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Telegram AI Bot",
    }


def _or_explain(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        msg = resp.text
    if resp.status_code == 402:
        return "На балансе OpenRouter закончились деньги."
    if resp.status_code == 429:
        return "Слишком много запросов, попробуйте через минуту."
    if resp.status_code == 401:
        return "Ключ OpenRouter не подходит."
    return f"Ошибка OpenRouter ({resp.status_code}): {str(msg)[:300]}"


def _to_openai(history: list, system: str | None) -> list:
    msgs = [{"role": "system", "content": system}] if system else []
    for m in history:
        if m.get("image_b64"):
            content = [
                {"type": "text", "text": m.get("text") or "Что на этом фото?"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{m['image_b64']}"}},
            ]
        else:
            content = m.get("text", "")
        msgs.append({"role": m["role"], "content": content})
    return msgs


async def _or_request(body: dict, timeout: float = 120) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(OPENROUTER_API, headers=_or_headers(), json=body)
    if resp.status_code != 200:
        raise AIError(_or_explain(resp))
    data = resp.json()
    if data.get("error"):
        raise AIError(f"OpenRouter: {data['error'].get('message', data['error'])}")
    budget.add(float((data.get("usage") or {}).get("cost") or 0))
    return data


async def _or_chat(history: list, system: str | None, model: str, timeout: float = 120) -> str:
    data = await _or_request({"model": model, "messages": _to_openai(history, system)}, timeout)
    msg = (data.get("choices") or [{}])[0].get("message", {})
    return (msg.get("content") or "").strip()


async def openrouter_image(prompt: str, aspect: str = "1:1", model: str | None = None) -> bytes:
    data = await _or_request({
        "model": model or config.IMAGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": aspect},
    }, timeout=180)
    msg = (data.get("choices") or [{}])[0].get("message", {})
    for img in msg.get("images") or []:
        url = img.get("image_url", {}).get("url", "")
        if url.startswith("data:") and "," in url:
            return base64.b64decode(url.split(",", 1)[1])
        if url.startswith("http"):
            async with httpx.AsyncClient(timeout=120) as client:
                return (await client.get(url)).content
    raise AIError("Модель не вернула картинку (возможно, промпт заблокирован фильтром).")


async def openrouter_video(prompt: str, model: str, params: dict, aspect: str = "16:9",
                           on_progress=None) -> tuple[bytes, float]:
    """Видео через OpenRouter: создаём задачу, ждём, скачиваем. Возвращает (mp4, цена $)."""
    body = {"model": model, "prompt": prompt, "aspect_ratio": aspect, **params}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.post("https://openrouter.ai/api/v1/videos", headers=_or_headers(), json=body)
        if r.status_code not in (200, 201, 202):
            raise AIError(_or_explain(r))
        job = r.json()
        poll = job.get("polling_url") or f"https://openrouter.ai/api/v1/videos/{job['id']}"
        for i in range(90):  # до ~15 минут
            await asyncio.sleep(10)
            r = await client.get(poll, headers=_or_headers())
            if r.status_code != 200:
                raise AIError(_or_explain(r))
            job = r.json()
            status = job.get("status")
            if status == "failed":
                err = job.get("error")
                raise AIError(f"Видео не получилось: {err.get('message', err) if isinstance(err, dict) else err}")
            if status == "completed":
                cost = float((job.get("usage") or {}).get("cost") or 0)
                budget.add(cost)
                urls = job.get("unsigned_urls") or []
                url = urls[0] if urls else f"https://openrouter.ai/api/v1/videos/{job['id']}/content?index=0"
                v = await client.get(url, headers=_or_headers(), timeout=300)
                if v.status_code != 200:
                    raise AIError(f"Не удалось скачать видео ({v.status_code}).")
                return v.content, cost
            if on_progress and i % 3 == 2:
                await on_progress((i + 1) * 10)
    raise AIError("Видео генерировалось слишком долго, попробуйте ещё раз.")


# =============================================================
#  Google Gemini (если у вас есть ключ AI Studio)
# =============================================================

def _g_headers() -> dict:
    return {"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"}


def _g_explain(resp: httpx.Response) -> str:
    try:
        msg = resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        msg = resp.text
    if resp.status_code == 429:
        return "Лимит бесплатных запросов Gemini исчерпан, попробуйте через минуту."
    if resp.status_code in (401, 403):
        return f"Ключ Gemini не подходит или нет доступа (в России нужен VPN): {str(msg)[:200]}"
    return f"Ошибка Gemini ({resp.status_code}): {str(msg)[:300]}"


def _to_gemini(history: list) -> list:
    out = []
    for m in history:
        parts = []
        if m.get("image_b64"):
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": m["image_b64"]}})
        parts.append({"text": m.get("text") or "Что на этом фото?"})
        out.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
    return out


async def _g_generate(contents: list, system: str | None, model: str,
                      generation_config: dict | None = None, timeout: float = 120) -> dict:
    body: dict = {"contents": contents}
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    if generation_config:
        body["generationConfig"] = generation_config
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{GEMINI_API}/models/{model}:generateContent", headers=_g_headers(), json=body)
    if resp.status_code != 200:
        raise AIError(_g_explain(resp))
    return resp.json()


def _g_text(data: dict) -> str:
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


async def gemini_image(prompt: str, aspect: str = "1:1") -> bytes:
    data = await _g_generate(
        [{"role": "user", "parts": [{"text": prompt}]}], None, config.IMAGE_MODEL_GEMINI,
        {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect}}, timeout=180,
    )
    for part in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])
    raise AIError("Gemini не вернул картинку (возможно, промпт заблокирован фильтром).")


async def veo_video(prompt: str, aspect: str = "16:9", on_progress=None) -> bytes:
    """Видео через Google Veo (только платный тариф Gemini API). Занимает 1–6 минут."""
    url = f"{GEMINI_API}/models/{config.VIDEO_MODEL}:predictLongRunning"
    body = {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": aspect}}
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.post(url, headers=_g_headers(), json=body)
        if resp.status_code != 200:
            raise AIError(_g_explain(resp))
        op_name = resp.json()["name"]
        for i in range(72):
            await asyncio.sleep(10)
            r = await client.get(f"{GEMINI_API}/{op_name}", headers=_g_headers())
            if r.status_code != 200:
                raise AIError(_g_explain(r))
            op = r.json()
            if op.get("error"):
                raise AIError(f"Veo: {op['error'].get('message', op['error'])}")
            if op.get("done"):
                samples = op.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])
                if not samples:
                    raise AIError("Veo не вернул видео (возможно, промпт заблокирован фильтром).")
                v = await client.get(samples[0]["video"]["uri"],
                                     headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=300)
                if v.status_code != 200:
                    raise AIError(f"Не удалось скачать видео ({v.status_code}).")
                return v.content
            if on_progress and i % 3 == 2:
                await on_progress((i + 1) * 10)
    raise AIError("Видео генерировалось слишком долго, попробуйте ещё раз.")


# =============================================================
#  Общий интерфейс для бота
# =============================================================

def has_chat() -> bool:
    return bool(config.OPENROUTER_API_KEY if config.AI_PROVIDER == "openrouter" else config.GEMINI_API_KEY)


async def complete(history: list, system: str | None = None, timeout: float = 120, model: str | None = None) -> str:
    if config.AI_PROVIDER == "openrouter":
        return await _or_chat(history, system, model or config.CHAT_MODEL, timeout)
    data = await _g_generate(_to_gemini(history), system, model or config.CHAT_MODEL, timeout=timeout)
    return _g_text(data)


async def chat(history: list) -> str:
    text = await complete(history, config.SYSTEM_PROMPT)
    return text or "(Модель не ответила. Попробуйте переформулировать.)"


ENHANCE_IMAGE = (
    "You turn a user's idea (often in Russian) into ONE detailed English prompt for a top-tier image "
    "generator. Rules:\n"
    "1. If the idea names a character, person, franchise, game or anime (even transliterated, e.g. "
    "'Асуна' = Asuna Yuuki from Sword Art Online, 'Наруто' = Naruto Uzumaki), KEEP the exact name and "
    "franchise in the prompt and describe their canonical look (hair, eyes, outfit, weapon) so the "
    "character is unmistakable. Never replace a named character with a generic one.\n"
    "2. Match the source style: anime characters -> high-quality anime illustration / key visual "
    "style, unless the user asks for realistic. Real-world subjects -> photorealistic.\n"
    "3. Add composition, lighting, background, mood, colors and quality terms (masterpiece, highly "
    "detailed, sharp focus).\n"
    "4. Keep the user's intent and every detail they gave. Do not moralize or water it down.\n"
    "Output only the prompt, no quotes, no comments."
)
ENHANCE_VIDEO = (
    "Rewrite the user's idea (often in Russian) into ONE detailed English prompt for a cinematic "
    "text-to-video model. Keep named characters/franchises exactly (e.g. 'Асуна' = Asuna Yuuki from "
    "Sword Art Online) with their canonical look and art style. Describe the scene, the main action, "
    "camera movement, lighting, mood and ambience in under 90 words. Keep the intent, do not water it "
    "down. Output only the prompt, no quotes."
)


async def enhance_prompt(idea: str, kind: str = "image") -> str:
    """Перевести и расписать промпт — заметно улучшает качество генерации."""
    if not has_chat():
        return idea
    system = ENHANCE_IMAGE if kind == "image" else ENHANCE_VIDEO
    # Дешёвая модель, при сбое — ещё раз основной.
    for model in (config.ENHANCE_MODEL, config.CHAT_MODEL):
        try:
            text = await complete([{"role": "user", "text": idea}], system, timeout=60, model=model)
            if text:
                return text
        except Exception:
            continue
    return idea
