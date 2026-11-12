"""Оплата рублями: картой через ЮKassa (встроенные платежи Telegram) и криптой через Crypto Pay (@CryptoBot).

Звёзды Telegram остаются основным способом. Эти два включаются командой /pay, когда админ задаст ключи:
- ЮKassa: токен платёжного провайдера из @BotFather → бот → Payments → ЮKassa. Оплата идёт счётом
  Telegram в рублях, поэтому всё проверяется так же, как у звёзд (pre_checkout и successful_payment).
- Crypto Pay: токен из @CryptoBot → Crypto Pay → Create App. Бот выставляет счёт в рублях, гость
  платит любой из монет (USDT, TON, BTC…), бот раз в 20 секунд спрашивает, оплачен ли счёт.

Ключи хранятся в payments.json рядом с базой (права 600), в чат и в журнал не попадают.
"""

import json
import logging
import os

import httpx

log = logging.getLogger("vpn-bot.payments")

RUB_PER_STAR = 1.5   # цена в рублях = цена в звёздах × курс (99 ⭐ → 149 ₽)
MIN_RUB = 100        # меньше Telegram и ЮKassa не принимают
CRYPTO_ASSETS = "USDT,TON,BTC,ETH,LTC,TRX,USDC"
CRYPTO_TTL = 3600    # сколько живёт счёт в крипте, секунд


class Settings:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {}
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("payments.json не прочитан: %s", e)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    @property
    def yookassa(self) -> str:
        return self.data.get("yookassa", "")

    @property
    def crypto(self) -> str:
        return self.data.get("crypto", "")

    @property
    def crypto_test(self) -> bool:
        return bool(self.data.get("crypto_test"))

    @property
    def rate(self) -> float:
        try:
            return float(self.data.get("rate") or RUB_PER_STAR)
        except (TypeError, ValueError):
            return RUB_PER_STAR

    @property
    def receipt(self) -> bool:
        """Передавать ли в ЮKassa данные для чека (нужно, если в магазине включены чеки по 54-ФЗ)."""
        return bool(self.data.get("receipt"))

    def set(self, **kw) -> None:
        for k, v in kw.items():
            if v in (None, ""):
                self.data.pop(k, None)
            else:
                self.data[k] = v
        self.save()

    def any_on(self) -> bool:
        return bool(self.yookassa or self.crypto)

    def rub(self, stars: int) -> int:
        """Цена в рублях для цены в звёздах: целые рубли, «красиво» на 9 в конце, не меньше MIN_RUB."""
        v = max(MIN_RUB, round(stars * self.rate))
        if v >= 100 and v % 10 != 9:
            v = v - v % 10 + 9 if v % 10 >= 5 else max(MIN_RUB, v - v % 10 - 1)
        return v


class CryptoPay:
    """Мини-клиент API Crypto Pay (https://help.send.tg/en/articles/10279948-crypto-pay-api)."""

    def __init__(self, token: str, test: bool = False):
        self.token = token
        self.base = "https://testnet-pay.crypt.bot/api/" if test else "https://pay.crypt.bot/api/"

    async def call(self, method: str, **params) -> dict | list:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(self.base + method, json=params, headers={"Crypto-Pay-API-Token": self.token})
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f"Crypto Pay: ответ не JSON (HTTP {r.status_code})") from None
        if not data.get("ok"):
            err = data.get("error") or {}
            raise RuntimeError(f"Crypto Pay: {err.get('name') or err or r.status_code}")
        return data["result"]

    async def me(self) -> dict:
        return await self.call("getMe")

    async def create(self, rub: int, description: str, payload: str) -> dict:
        """Счёт в рублях, гость платит любой из CRYPTO_ASSETS по курсу CryptoBot."""
        return await self.call("createInvoice", currency_type="fiat", fiat="RUB", amount=f"{rub}.00",
                               accepted_assets=CRYPTO_ASSETS, description=description[:1024],
                               payload=payload[:4096], expires_in=CRYPTO_TTL, allow_comments=False,
                               allow_anonymous=False)

    async def invoices(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        res = await self.call("getInvoices", invoice_ids=",".join(str(i) for i in ids), count=len(ids))
        return res.get("items", []) if isinstance(res, dict) else []


def invoice_url(inv: dict) -> str:
    return inv.get("bot_invoice_url") or inv.get("mini_app_invoice_url") or inv.get("pay_url") or ""
