#!/usr/bin/env bash
# Установщик мессенджера «Орбита» на чистый Ubuntu/Debian (от root):
#   bash <(curl -fsSL https://raw.githubusercontent.com/Saske356/Saske356/ccr-b933db82-yjyge0/messenger/install.sh)
#
# Что делает: Node.js 22, сам мессенджер (systemd), Caddy с бесплатным HTTPS-сертификатом,
# TURN-сервер coturn для звонков через мобильный интернет. Повторный запуск обновляет код, данные сохраняются.
# Домен не обязателен: без него используется адрес вида 1-2-3-4.sslip.io с настоящим сертификатом.
# Если порт 443 уже занят (например, VPN на Xray), сайт будет на порту 8443 — VPN не пострадает.
#
# Переменные (необязательно): DOMAIN=chat.example.com  HTTPS_PORT=443  BRANCH=…  NO_TURN=1
set -euo pipefail

REPO="${REPO:-https://github.com/Saske356/Saske356.git}"
BRANCH="${BRANCH:-ccr-b933db82-yjyge0}"
DIR=/opt/orbita
APP="$DIR/messenger"
DATA=/var/lib/orbita
ENVF=/etc/orbita.env
APP_PORT=3800

say()  { printf '\n\033[1;35m== %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mОшибка: %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { local q="$1" def="${2:-}" v; read -rp "$q${def:+ [$def]}: " v </dev/tty || true; printf '%s' "${v:-$def}"; }
port_busy() { ss -Hltnu "( sport = :$1 )" 2>/dev/null | grep -q .; }

[ "$(id -u)" -eq 0 ] || fail "запустите от root (sudo -i)"
. /etc/os-release
case "$ID" in ubuntu|debian) ;; *) fail "нужен Ubuntu или Debian, а здесь $ID" ;; esac
# shellcheck source=/dev/null
[ -f "$ENVF" ] && . "$ENVF" && say "Нашёл прошлую установку — обновляю, настройки сохраняю"

say "Ставлю пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl git ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https openssl iproute2 >/dev/null

if ! command -v node >/dev/null || ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a===22&&b>=13)?0:1)'; then
  say "Ставлю Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi
node --version

if ! command -v caddy >/dev/null; then
  say "Ставлю Caddy (HTTPS)"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi

say "Скачиваю Орбиту"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH" && git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --depth 1 -b "$BRANCH" "$REPO" "$DIR"
fi
(cd "$APP" && npm ci --omit=dev --no-audit --no-fund --loglevel=error)

say "Адрес сервера"
IP=$(curl -4 -fsS --max-time 8 https://api.ipify.org || curl -4 -fsS --max-time 8 https://ifconfig.me || true)
[ -n "$IP" ] || fail "не удалось узнать внешний IP сервера"
if [ -z "${DOMAIN:-}" ]; then
  DOMAIN=$(ask "Домен для мессенджера (Enter — без домена, через ${IP//./-}.sslip.io)" "${IP//./-}.sslip.io")
fi
if [ -z "${HTTPS_PORT:-}" ]; then
  if port_busy 443 && ! ss -Hltnp "( sport = :443 )" 2>/dev/null | grep -q caddy; then HTTPS_PORT=8443; echo "Порт 443 занят (вероятно, VPN) — сайт будет на 8443"; else HTTPS_PORT=443; fi
fi
if port_busy 80 && ! ss -Hltnp "( sport = :80 )" 2>/dev/null | grep -q caddy; then
  fail "порт 80 занят другой программой — он нужен для получения HTTPS-сертификата"
fi
URL="https://$DOMAIN"; [ "$HTTPS_PORT" = 443 ] || URL="$URL:$HTTPS_PORT"

ICE='[{"urls":["stun:stun.l.google.com:19302"]}]'
if [ -z "${NO_TURN:-}" ]; then
  say "Ставлю TURN для звонков"
  apt-get install -y -qq coturn >/dev/null
  TURN_PASS="${TURN_PASS:-$(openssl rand -hex 16)}"
  cat > /etc/turnserver.conf <<EOF
listening-port=3478
fingerprint
lt-cred-mech
user=orbita:$TURN_PASS
realm=$DOMAIN
external-ip=$IP
min-port=49160
max-port=49200
no-cli
no-tlsv1
no-tlsv1_1
no-multicast-peers
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
EOF
  sed -i 's/^#\?TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn 2>/dev/null || true
  systemctl enable -q coturn && systemctl restart coturn
  ICE="[{\"urls\":[\"stun:$IP:3478\"]},{\"urls\":[\"turn:$IP:3478?transport=udp\",\"turn:$IP:3478?transport=tcp\"],\"username\":\"orbita\",\"credential\":\"$TURN_PASS\"}]"
fi

say "Настраиваю службу"
id orbita >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin orbita
mkdir -p "$DATA" && chown -R orbita:orbita "$DATA"
cat > "$ENVF" <<EOF
DOMAIN=$DOMAIN
HTTPS_PORT=$HTTPS_PORT
TURN_PASS=${TURN_PASS:-}
EOF
chmod 600 "$ENVF"
cat > /etc/systemd/system/orbita.service <<EOF
[Unit]
Description=Orbita messenger
After=network-online.target
Wants=network-online.target

[Service]
User=orbita
WorkingDirectory=$APP
Environment=PORT=$APP_PORT
Environment=DATA_DIR=$DATA
Environment=PUBLIC_URL=$URL
Environment='ICE_SERVERS=$ICE'
ExecStart=$(command -v node) --disable-warning=ExperimentalWarning server/index.js
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

ADDR="$DOMAIN"; [ "$HTTPS_PORT" = 443 ] || ADDR="$DOMAIN:$HTTPS_PORT"
if [ -f /etc/caddy/Caddyfile ] && ! grep -q "reverse_proxy 127.0.0.1:$APP_PORT" /etc/caddy/Caddyfile; then
  cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$(date +%s)"   # сохраняю чужие настройки Caddy
fi
cat > /etc/caddy/Caddyfile <<EOF
{
	https_port $HTTPS_PORT
}
$ADDR {
	encode zstd gzip
	reverse_proxy 127.0.0.1:$APP_PORT
}
EOF

if command -v ufw >/dev/null && ufw status | grep -q active; then
  ufw allow 80/tcp >/dev/null; ufw allow "$HTTPS_PORT"/tcp >/dev/null
  [ -z "${NO_TURN:-}" ] && { ufw allow 3478 >/dev/null; ufw allow 49160:49200/udp >/dev/null; }
fi

systemctl daemon-reload
systemctl enable -q orbita caddy
systemctl restart orbita
systemctl restart caddy

say "Проверяю"
for _ in $(seq 1 60); do curl -fsS --max-time 5 "$URL/api/config" >/dev/null 2>&1 && break; sleep 2; done
curl -fsS --max-time 5 "$URL/api/config" >/dev/null 2>&1 || echo "Сайт пока не отвечает по HTTPS — сертификат может выпускаться ещё минуту. Логи: journalctl -u caddy -n 50"
SETUP=$(journalctl -u orbita -n 50 --no-pager -o cat | grep -o 'https\?://[^ ]*/admin#setup=[a-f0-9]*' | tail -1 || true)

printf '\n\033[1;32m✓ Орбита работает\033[0m\n\n'
echo "  Сайт:               $URL"
echo "  Приложение Android: $URL/download/orbita.apk   (сразу знает адрес сервера)"
if [ -n "$SETUP" ]; then
  echo "  Служебный доступ:   $SETUP"
  echo "                      ↑ откройте ОДИН раз и задайте фразу администратора (ссылка живёт до перезапуска)"
else
  echo "  Служебный доступ:   $URL/admin"
fi
echo
echo "  Обновить:  запустите эту же команду ещё раз"
echo "  Логи:      journalctl -u orbita -f"
