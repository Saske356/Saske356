"""Подключение к VPN-серверу.

VPN_MODE=demo (по умолчанию) — ненастоящие ключи с пометкой DEMO, чтобы проверить покупку.
VPN_MODE=xray — настоящий VPN на этом же сервере (см. xray_provider.py и install.sh).
"""

import os
import uuid


class VpnProvider:
    is_demo = False

    async def issue(self, user_id: int, expires_at: float, devices: int | None = None) -> str:
        """Создать или продлить доступ пользователю. Вернуть ссылку-ключ.
        devices — сколько устройств оплачено: по нему сервер проверяет лимит."""
        raise NotImplementedError

    async def revoke(self, user_id: int) -> None:
        """Отключить доступ, когда подписка закончилась."""
        raise NotImplementedError


class DemoProvider(VpnProvider):
    is_demo = True

    async def issue(self, user_id: int, expires_at: float, devices: int | None = None) -> str:
        uid = uuid.uuid5(uuid.NAMESPACE_OID, f"demo-{user_id}")
        return (f"vless://{uid}@demo.example.com:443"
                f"?type=tcp&security=reality&fp=chrome#DEMO-{user_id}")

    async def revoke(self, user_id: int) -> None:
        return None


def get_provider() -> VpnProvider:
    if os.environ.get("VPN_MODE", "demo") == "xray":
        from xray_provider import from_env
        return from_env()
    return DemoProvider()
