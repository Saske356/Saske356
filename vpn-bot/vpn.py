"""Подключение к VPN-серверу.

Пока сервера нет, работает DemoProvider: он выдаёт ненастоящие ключи с пометкой DEMO,
чтобы можно было проверить весь путь покупки. Когда появится сервер, сюда добавляется
класс, который создаёт клиента в панели (например, 3x-ui), и в get_provider()
DemoProvider меняется на него. Остальной код бота трогать не придётся.
"""

import uuid


class VpnProvider:
    is_demo = False

    async def issue(self, user_id: int, expires_at: float) -> str:
        """Создать или продлить доступ пользователю. Вернуть ссылку-ключ."""
        raise NotImplementedError

    async def revoke(self, user_id: int) -> None:
        """Отключить доступ, когда подписка закончилась."""
        raise NotImplementedError


class DemoProvider(VpnProvider):
    is_demo = True

    async def issue(self, user_id: int, expires_at: float) -> str:
        uid = uuid.uuid5(uuid.NAMESPACE_OID, f"demo-{user_id}")
        return (f"vless://{uid}@demo.example.com:443"
                f"?type=tcp&security=reality&fp=chrome#DEMO-{user_id}")

    async def revoke(self, user_id: int) -> None:
        return None


def get_provider() -> VpnProvider:
    return DemoProvider()
