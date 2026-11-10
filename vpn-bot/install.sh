#!/usr/bin/env bash
# Установщик Aurora VPN: Xray (VLESS Reality) + бот + раздача подписок.
# Запуск на чистом сервере Ubuntu/Debian от root:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Saske356/Saske356/claude/android-usage-ql87m8/vpn-bot/install.sh)
# Повторный запуск обновляет код и сохраняет настройки.
set -euo pipefail

REPO="${REPO:-https://github.com/Saske356/Saske356.git}"
BRANCH="${BRANCH:-claude/android-usage-ql87m8}"
DIR=/opt/aurora
BOT="$DIR/vpn-bot"
ENV="$BOT/.env"
XRAY=/usr/local/bin/xray
SUB_PORT="${SUB_PORT:-2096}"

say()  { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mОшибка: %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { local q="$1" def="${2:-}" v; read -rp "$q${def:+ [$def]}: " v </dev/tty; printf '%s' "${v:-$def}"; }
# Связь с GitHub с некоторых серверов рвётся: каждую загрузку повторяем до 5 раз.
retry() {
  local n
  for n in 1 2 3 4 5; do
    "$@" && return 0
    [ "$n" -lt 5 ] && { echo "Связь оборвалась, пробую ещё раз ($((n+1)) из 5)..."; sleep $((n*3)); }
  done
  return 1
}
fetch() { curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 15 "$@"; }

install_xray() {
  local f rc
  f=$(mktemp)
  fetch -o "$f" https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh || { rm -f "$f"; return 1; }
  # Обрезанный файл без последней строки запускать нельзя.
  tail -n 3 "$f" | grep -q '^main "\$@"' || { rm -f "$f"; return 1; }
  bash "$f" install >/dev/null
  rc=$?
  rm -f "$f"
  return $rc
}

get_code() {
  if [ -d "$DIR/.git" ]; then
    git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
  else
    [ -f "$ENV" ] || rm -rf "$DIR"
    git clone -q -b "$BRANCH" "$REPO" "$DIR"
  fi
}

[ "$(id -u)" -eq 0 ] || fail "запустите от root (sudo -i)"
. /etc/os-release
case "$ID" in ubuntu|debian) ;; *) fail "нужен Ubuntu или Debian, а здесь $ID" ;; esac

say "Ставлю пакеты"
export DEBIAN_FRONTEND=noninteractive
retry apt-get update -qq || fail "не удалось обновить список пакетов"
retry apt-get install -y -qq curl git python3 python3-venv python3-pip openssl ca-certificates >/dev/null \
  || fail "не удалось поставить пакеты"

say "Ставлю Xray"
if ! retry install_xray; then
  if [ -x "$XRAY" ]; then
    echo "Обновить Xray не вышло, оставляю уже установленный."
  else
    fail "Xray не скачался с GitHub. Подождите пару минут и запустите команду ещё раз"
  fi
fi
[ -x "$XRAY" ] || fail "Xray не установился"
"$XRAY" version | head -1

say "Скачиваю бота"
retry get_code || fail "не удалось скачать бота с GitHub. Запустите команду ещё раз"
python3 -m venv "$BOT/.venv"
retry "$BOT/.venv/bin/pip" install -q --upgrade pip || true
retry "$BOT/.venv/bin/pip" install -q -r "$BOT/requirements.txt" || fail "не удалось поставить библиотеки Python"

if [ ! -f "$ENV" ]; then
  say "Настройка (один раз)"
  TOKEN=$(ask "Токен бота от @BotFather")
  [ -n "$TOKEN" ] || fail "без токена бот не запустится"
  ADMIN=$(ask "Ваш Telegram ID (узнать у @userinfobot)")
  SUPPORT=$(ask "Ник поддержки без @ (можно пусто)" "")
  LOC=$(ask "Название страны этого сервера" "🇸🇪 Швеция")
  SNI=$(ask "Сайт для маскировки Reality" "www.microsoft.com")
  MINI=$(ask "Адрес мини-приложения (пусто — без него)" "https://saske356.github.io/Saske356/")

  KEYS=$("$XRAY" x25519)
  PRIV=$(printf '%s\n' "$KEYS" | awk -F': *' 'tolower($1) ~ /private/ {print $2; exit}')
  PUB=$(printf '%s\n' "$KEYS" | awk -F': *' 'tolower($1) ~ /public|password/ {print $2; exit}')
  [ -n "$PRIV" ] && [ -n "$PUB" ] || fail "не удалось получить ключи Reality: $KEYS"
  SID=$(openssl rand -hex 8)
  IP=$(curl -fsS4 --max-time 10 https://api.ipify.org || curl -fsS4 --max-time 10 https://ifconfig.me) \
    || fail "не удалось узнать внешний IP"

  umask 077
  cat > "$ENV" <<EOF
BOT_TOKEN=$TOKEN
ADMIN_IDS=$ADMIN
SUPPORT_USERNAME=$SUPPORT
MINIAPP_URL=$MINI
VPN_MODE=xray
PUBLIC_HOST=$IP
VPN_PORT=443
SUB_PORT=$SUB_PORT
REALITY_SNI=$SNI
REALITY_PRIVATE_KEY=$PRIV
REALITY_PUBLIC_KEY=$PUB
REALITY_SHORT_ID=$SID
DEFAULT_LOCATION_NAME="$LOC"
DB_PATH=$BOT/bot.db
VPN_STATE=/var/lib/aurora/vpn.json
EOF
  umask 022
  echo "Настройки сохранены в $ENV (их видит только root)."
else
  say "Настройки уже есть, оставляю их"
fi
mkdir -p /var/lib/aurora

say "Ускорение сети (BBR)"
if ! grep -q "tcp_congestion_control=bbr" /etc/sysctl.conf 2>/dev/null; then
  printf 'net.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\n' >> /etc/sysctl.conf
fi
sysctl -p >/dev/null 2>&1 || true

say "Автозапуск"
cat > /etc/systemd/system/aurora-bot.service <<EOF
[Unit]
Description=Aurora VPN bot
After=network-online.target xray.service
Wants=network-online.target

[Service]
WorkingDirectory=$BOT
ExecStart=$BOT/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q xray
systemctl enable -q aurora-bot
systemctl restart aurora-bot

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 443/tcp >/dev/null
  ufw allow "$SUB_PORT"/tcp >/dev/null
fi

say "Проверка"
sleep 8
ok=1
systemctl is-active -q aurora-bot && echo "✅ бот работает" || { echo "❌ бот не запустился"; ok=0; }
systemctl is-active -q xray && echo "✅ Xray работает" || { echo "❌ Xray не запустился"; ok=0; }
if [ "$ok" = 1 ]; then
  echo
  echo "Готово. Откройте бота и отправьте /start, страны: /locations"
else
  echo
  echo "Пришлите вывод этих команд:"
  echo "  journalctl -u aurora-bot -n 40 --no-pager"
  echo "  journalctl -u xray -n 40 --no-pager"
fi
