# miner-bot — Telegram-бот для управления cgminer

Бот запускает и останавливает Bitcoin-майнер **cgminer** через `subprocess`.
Хешрейт и шары он читает из JSON-API cgminer, а загрузку системы — из `psutil`.

| Команда | Что делает |
|---------|------------|
| `/start` | запускает cgminer с пулом из `.env` |
| `/stop` | останавливает: сначала `quit` через API, потом SIGTERM, в крайнем случае SIGKILL |
| `/status` | хешрейт (5с/средний), шары, пул, CPU, RAM, load avg, температура |
| `/log` | последние 20 строк лога cgminer |

Управлять ботом могут только пользователи из `ADMIN_IDS`. Остальным бот
отвечает «нет доступа» и показывает их Telegram ID, так свой ID легко узнать.

## Установка

```bash
cd miner-bot
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env            # BOT_TOKEN, ADMIN_IDS, CGMINER_PATH, POOL_URL, POOL_USER
python bot.py
```

Пример `.env`:

```ini
BOT_TOKEN=123456789:AA...        # от @BotFather
ADMIN_IDS=111111111
CGMINER_PATH=/usr/local/bin/cgminer
POOL_URL=stratum+tcp://pool.example.com:3333
POOL_USER=yourworker.1
POOL_PASS=x
CGMINER_EXTRA=--usb :1           # любые доп. ключи cgminer
```

Бот запускает cgminer такой командой:

```
cgminer -o $POOL_URL -u $POOL_USER -p $POOL_PASS --text-only \
        --api-listen --api-port 4028 --api-allow W:127.0.0.1 $CGMINER_EXTRA
```

Вывод cgminer пишется в `cgminer.log` рядом с ботом.

## Проверка без ASIC

В `tools/fake_cgminer.py` лежит заглушка с тем же API (`summary`, `pools`, `quit`):

```ini
CGMINER_PATH=./tools/fake_cgminer.py
POOL_URL=stratum+tcp://test:3333
POOL_USER=test
```

## Автозапуск (systemd)

```ini
# /etc/systemd/system/miner-bot.service
[Unit]
Description=Telegram miner bot
After=network-online.target

[Service]
WorkingDirectory=/opt/miner-bot
ExecStart=/opt/miner-bot/.venv/bin/python bot.py
Restart=always
User=miner

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now miner-bot
```

## Важно

* Bitcoin на CPU и GPU сейчас не окупается: майнят только на ASIC. Новые
  версии cgminer (4.x) работают только с ASIC и USB-устройствами.
* Не коммитьте `.env` (он уже в `.gitignore`). Если токен куда-то утёк,
  перевыпустите его в @BotFather: `/mybots` → бот → *API Token* → *Revoke*.
* API cgminer слушает только `127.0.0.1`. Не открывайте порт 4028 наружу.
