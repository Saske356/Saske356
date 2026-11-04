"""Учёт трат: сколько потрачено за сегодня, дневной лимит, баланс OpenRouter."""
import datetime as dt
import json
from pathlib import Path

import httpx

import config

_FILE = Path(__file__).with_name("spend.json")


def _load() -> dict:
    try:
        return json.loads(_FILE.read_text())
    except Exception:
        return {}


def _today() -> str:
    return dt.date.today().isoformat()


def spent_today() -> float:
    return float(_load().get(_today(), 0.0))


def add(cost: float) -> None:
    if not cost:
        return
    data = _load()
    data[_today()] = round(float(data.get(_today(), 0.0)) + float(cost), 6)
    # хранить только последние 30 дней
    data = dict(sorted(data.items())[-30:])
    try:
        _FILE.write_text(json.dumps(data))
    except Exception:
        pass


def can_spend(estimate: float) -> bool:
    limit = config.DAILY_LIMIT_USD
    return limit <= 0 or spent_today() + estimate <= limit


async def balance() -> float | None:
    """Остаток на аккаунте OpenRouter в $."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get("https://openrouter.ai/api/v1/credits",
                                 headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"})
        d = r.json()["data"]
        return float(d["total_credits"]) - float(d["total_usage"])
    except Exception:
        return None


def fmt(usd: float) -> str:
    return f"${usd:.3f}" if usd < 0.1 else f"${usd:.2f}"
