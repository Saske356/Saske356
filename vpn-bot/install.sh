#!/usr/bin/env bash
# Установщик Aurora VPN: Xray (VLESS Reality) + Hysteria2 + бот + раздача подписок.
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
HY_BIN=/usr/local/bin/hysteria
HY_DIR=/etc/hysteria
HY2="${HY2:-1}"   # HY2=0 — не ставить Hysteria2
AWG="${AWG:-1}"   # AWG=0 — не ставить AmneziaWG
HOP_PORTS="${HOP_PORTS:-20000-29999}"  # диапазон смены портов Hysteria2

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
retry3() { local n; for n in 1 2 3; do "$@" && return 0; [ "$n" -lt 3 ] && { echo "Пробую ещё раз ($((n+1)) из 3)..."; sleep 5; }; done; return 1; }
fetch() { curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 15 "$@"; }

XRAY_REPO=XTLS/Xray-core

xray_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo 64 ;;
    aarch64|arm64) echo arm64-v8a ;;
    *) return 1 ;;
  esac
}

# Загрузка, которая 30 секунд стоит на месте, считается оборванной.
grab() {
  curl -fsSL --retry 2 --retry-delay 3 --retry-all-errors --connect-timeout 15 \
    --speed-limit 1024 --speed-time 30 -o "$1" "$2"
}

# Последняя версия Xray и SHA-256 её архива по данным GitHub API.
xray_release() {
  fetch -H "Accept: application/vnd.github+json" "https://api.github.com/repos/$XRAY_REPO/releases/latest" \
    | python3 -I -c '
import json, sys
d = json.load(sys.stdin)
want = "Xray-linux-%s.zip" % sys.argv[1]
digest = next((a.get("digest") or "" for a in d.get("assets", []) if a.get("name") == want), "")
print(d["tag_name"], digest.split(":", 1)[1] if digest.startswith("sha256:") else "-")
' "$1"
}

# С некоторых серверов архивы GitHub не скачиваются, поэтому есть запасное зеркало.
# Архив принимается, только если его SHA-256 совпадает с опубликованным.
download_xray_zip() {
  local out="$1" arch info tag api_sum sum got url
  arch=$(xray_arch) || { echo "Xray не поддерживает процессор $(uname -m)"; return 1; }
  info=$(xray_release "$arch") || { echo "GitHub API не ответил"; return 1; }
  read -r tag api_sum <<<"$info"
  [ -n "$tag" ] || return 1
  if [ -x "$XRAY" ] && "$XRAY" version 2>/dev/null | head -1 | grep -qF " ${tag#v} "; then
    echo "Xray $tag уже установлен"
    return 2
  fi
  local gh="https://github.com/$XRAY_REPO/releases/download/$tag/Xray-linux-$arch.zip"
  # Контрольная сумма берётся только с GitHub: API или файл .dgst из официального релиза.
  # Сумме с зеркала верить нельзя: подменённый архив пришёл бы вместе с подменённой суммой.
  sum="$api_sum"
  if [ "$sum" = "-" ] && grab "$out.dgst" "$gh.dgst"; then
    sum=$(awk -F'= *' '/^SHA2-256/ {print $2; exit}' "$out.dgst")
  fi
  [ "$sum" = "-" ] && sum=""
  for url in "$gh" "https://downloads.sourceforge.net/project/xray-core.mirror/$tag/Xray-linux-$arch.zip"; do
    if [ -z "$sum" ] && [ "$url" != "$gh" ]; then
      echo "Нет контрольной суммы с GitHub, поэтому зеркало не используем"
      break
    fi
    echo "Качаю Xray $tag с $(printf '%s' "$url" | cut -d/ -f3)..."
    rm -f "$out"
    grab "$out" "$url" || { echo "Не скачалось, пробую другой источник"; continue; }
    # без суммы принимаем только официальный архив с GitHub
    [ -z "$sum" ] && return 0
    got=$(sha256sum "$out" | cut -d' ' -f1)
    [ -n "$sum" ] && [ "$got" = "$sum" ] && return 0
    echo "Файл повреждён (контрольная сумма не совпала), пробую другой источник"
  done
  return 1
}

install_xray() {
  local tmp rc
  tmp=$(mktemp -d)
  fetch -o "$tmp/install-release.sh" https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh \
    || { rm -rf "$tmp"; return 1; }
  # Обрезанный файл без последней строки запускать нельзя.
  tail -n 3 "$tmp/install-release.sh" | grep -q '^main "\$@"' || { rm -rf "$tmp"; return 1; }
  download_xray_zip "$tmp/xray.zip"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    bash "$tmp/install-release.sh" install -l "$tmp/xray.zip" >/dev/null
    rc=$?
  elif [ "$rc" -eq 2 ]; then
    rc=0
  fi
  rm -rf "$tmp"
  return $rc
}

hy_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    *) return 1 ;;
  esac
}

# Hysteria2 с GitHub. Файл принимается, только если его SHA-256 совпал с hashes.txt того же релиза.
install_hysteria() {
  local arch tmp sum got base=https://github.com/apernet/hysteria/releases/latest/download
  arch=$(hy_arch) || { echo "Hysteria2 не поддерживает процессор $(uname -m)"; return 1; }
  tmp=$(mktemp -d)
  if ! grab "$tmp/hashes.txt" "$base/hashes.txt"; then rm -rf "$tmp"; return 1; fi
  sum=$(awk -v f="build/hysteria-linux-$arch" '$2 == f {print $1; exit}' "$tmp/hashes.txt")
  if [ -z "$sum" ]; then echo "Нет контрольной суммы Hysteria2"; rm -rf "$tmp"; return 1; fi
  if [ -x "$HY_BIN" ] && [ "$(sha256sum "$HY_BIN" | cut -d' ' -f1)" = "$sum" ]; then
    echo "Hysteria2 последней версии уже установлен"; rm -rf "$tmp"; return 0
  fi
  echo "Качаю Hysteria2..."
  if ! grab "$tmp/hysteria" "$base/hysteria-linux-$arch"; then rm -rf "$tmp"; return 1; fi
  got=$(sha256sum "$tmp/hysteria" | cut -d' ' -f1)
  if [ "$got" != "$sum" ]; then echo "Файл повреждён (контрольная сумма не совпала)"; rm -rf "$tmp"; return 1; fi
  install -m 755 "$tmp/hysteria" "$HY_BIN"
  rm -rf "$tmp"
}

# Значение из .env или пусто. Не падает под set -e, если ключа нет.
envget() { { grep -m1 "^$1=" "$ENV" 2>/dev/null || true; } | cut -d= -f2- | sed 's/^"//; s/"$//'; }

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

export DEBIAN_FRONTEND=noninteractive

# ---------- режим моста: российский сервер пересылает порт 443 на основной ----------
# Запуск на сервере-мосте:  bash <(curl -fsSL .../install.sh) bridge
if [ "${1:-}" = "bridge" ]; then
  MAIN=$(ask "IP основного VPN-сервера")
  printf '%s' "$MAIN" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' || fail "нужен IP вида 1.2.3.4"
  say "Ставлю пересылку 443 → $MAIN:443"
  retry apt-get update -qq || fail "не удалось обновить список пакетов"
  retry apt-get install -y -qq nftables >/dev/null || fail "не удалось поставить nftables"
  echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-aurora-bridge.conf
  sysctl -q -p /etc/sysctl.d/99-aurora-bridge.conf
  cat > /etc/nftables.conf <<EOF
#!/usr/sbin/nft -f
flush ruleset
table ip aurora {
  chain prerouting {
    type nat hook prerouting priority dstnat; policy accept;
    tcp dport 443 dnat to $MAIN:443
  }
  chain postrouting {
    type nat hook postrouting priority srcnat; policy accept;
    ip daddr $MAIN tcp dport 443 masquerade
  }
}
EOF
  nft -f /etc/nftables.conf
  systemctl enable -q nftables
  BRIDGE_IP=$(curl -fsS4 --max-time 10 https://api.ipify.org || echo "IP_ЭТОГО_СЕРВЕРА")
  say "Мост готов"
  echo "Теперь в боте отправьте:"
  echo "  /addbridge ru1 🇷🇺 Обход | $BRIDGE_IP"
  exit 0
fi

say "Ставлю пакеты"
retry apt-get update -qq || fail "не удалось обновить список пакетов"
retry apt-get install -y -qq curl unzip git python3 python3-venv python3-pip openssl ca-certificates >/dev/null \
  || fail "не удалось поставить пакеты"
# rclone нужен только для копий в облако (BACKUP_RCLONE), поэтому без него установка продолжается
apt-get install -y -qq rclone >/dev/null 2>&1 || echo "rclone не поставился: копии в облако работать не будут"
apt-get install -y -qq certbot >/dev/null 2>&1 || echo "certbot не поставился: подписка останется по HTTP"

say "Ставлю Xray"
if ! retry3 install_xray; then
  if [ -x "$XRAY" ]; then
    echo "Обновить Xray не вышло, оставляю уже установленный."
  else
    fail "Xray не скачался ни с GitHub, ни с зеркала. Подождите пару минут и запустите команду ещё раз"
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

# ---------- Hysteria2: быстрый способ по UDP на том же порту 443 ----------
HY_OK=0
if [ "$HY2" = "1" ]; then
  say "Ставлю Hysteria2 (быстрый режим по UDP)"
  if retry3 install_hysteria; then
    id hysteria >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin hysteria
    mkdir -p "$HY_DIR"
    HY_SNI=$(envget HY2_SNI); [ -n "$HY_SNI" ] || HY_SNI=$(envget REALITY_SNI); [ -n "$HY_SNI" ] || HY_SNI=www.microsoft.com
    if [ ! -f "$HY_DIR/server.crt" ]; then
      # Свой сертификат: приложение сверяет его отпечаток из ссылки, домен для этого не нужен.
      openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -days 3650 \
        -keyout "$HY_DIR/server.key" -out "$HY_DIR/server.crt" -subj "/CN=$HY_SNI" \
        -addext "subjectAltName=DNS:$HY_SNI" >/dev/null 2>&1 || fail "не удалось создать сертификат Hysteria2"
    fi
    chown root:hysteria "$HY_DIR/server.key"; chmod 640 "$HY_DIR/server.key"; chmod 644 "$HY_DIR/server.crt"
    if [ -z "$(envget HY2_PORT)" ]; then
      umask 077
      cat >> "$ENV" <<EOF
HY2_PORT=443
HY2_CERT=$HY_DIR/server.crt
HY2_SNI=$HY_SNI
HY2_AUTH_PORT=20809
HY2_STATS_PORT=20810
HY2_STATS_SECRET=$(openssl rand -hex 16)
EOF
      umask 022
    fi
    HY_PORT=$(envget HY2_PORT); HY_AUTH=$(envget HY2_AUTH_PORT); HY_STATS=$(envget HY2_STATS_PORT)
    HY_SECRET=$(envget HY2_STATS_SECRET); HY_OBFS=$(envget HY2_OBFS_PASSWORD)
    umask 027
    cat > "$HY_DIR/config.yaml" <<EOF
# Создано установщиком Aurora VPN. Ключи проверяет бот: при подключении Hysteria спрашивает его.
listen: :${HY_PORT:-443}
tls:
  cert: $HY_DIR/server.crt
  key: $HY_DIR/server.key
  sniGuard: disable
auth:
  type: http
  http:
    url: http://127.0.0.1:${HY_AUTH:-20809}/auth
masquerade:
  type: proxy
  proxy:
    url: https://$HY_SNI/
    rewriteHost: true
trafficStats:
  listen: 127.0.0.1:${HY_STATS:-20810}
  secret: $HY_SECRET
EOF
    if [ -n "$HY_OBFS" ]; then
      printf 'obfs:\n  type: salamander\n  salamander:\n    password: %s\n' "$HY_OBFS" >> "$HY_DIR/config.yaml"
    fi
    umask 022
    chown root:hysteria "$HY_DIR/config.yaml"
    cat > /etc/systemd/system/hysteria-server.service <<EOF
[Unit]
Description=Hysteria2 server (Aurora VPN)
After=network-online.target
Wants=network-online.target

[Service]
User=hysteria
ExecStart=$HY_BIN server -c $HY_DIR/config.yaml
Restart=always
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
    # Серверы Hysteria2 для других стран: конфиги пишет бот (loc-КОД.yaml), он же включает службы.
    cat > /etc/systemd/system/hysteria-loc@.service <<EOF
[Unit]
Description=Hysteria2 server for country %i (Aurora VPN)
After=network-online.target
Wants=network-online.target

[Service]
User=hysteria
ExecStart=$HY_BIN server -c $HY_DIR/loc-%i.yaml
Restart=always
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable -q hysteria-server
    systemctl restart hysteria-server
    HY_OK=1
  else
    echo "Hysteria2 не скачался. VPN работает и без него, повторный запуск установщика попробует снова."
  fi
fi

# ---------- смена портов Hysteria2 ----------
# Файрвол перенаправляет UDP с диапазона портов на порт Hysteria2, а приложение прыгает между
# ними: заблокировать один порт оператору проще, чем десять тысяч.
if [ "$HY_OK" = 1 ] && [ "$HOP_PORTS" != 0 ]; then
  say "Смена портов Hysteria2 ($HOP_PORTS)"
  if apt-get install -y -qq nftables >/dev/null 2>&1; then
    HP=$(envget HY2_PORT); HP=${HP:-443}
    cat > /etc/aurora-hop.nft <<EOF
table inet aurora_hop
delete table inet aurora_hop
table inet aurora_hop {
  chain prerouting {
    type nat hook prerouting priority dstnat; policy accept;
    udp dport $HOP_PORTS redirect to :$HP
  }
}
EOF
    cat > /etc/systemd/system/aurora-hop.service <<EOF
[Unit]
Description=Aurora VPN: UDP port hopping for Hysteria2
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f /etc/aurora-hop.nft
ExecStop=/usr/sbin/nft delete table inet aurora_hop

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    if systemctl enable -q --now aurora-hop && systemctl restart aurora-hop; then
      if [ -z "$(envget HY2_HOP_PORTS)" ]; then echo "HY2_HOP_PORTS=$HOP_PORTS" >> "$ENV"; fi
      echo "Смена портов включена."
    else
      echo "Смена портов не включилась, Hysteria2 работает на одном порту."
    fi
  fi
fi

# ---------- AmneziaWG: запасной способ по UDP ----------
AWG_OK=0
if [ "$AWG" = 1 ]; then
  say "Ставлю AmneziaWG"
  if ! command -v awg >/dev/null; then
    if [ "$ID" = ubuntu ]; then
      apt-get install -y -qq software-properties-common "linux-headers-$(uname -r)" >/dev/null 2>&1 || true
      { add-apt-repository -y ppa:amnezia/ppa >/dev/null 2>&1 && retry apt-get update -qq \
        && apt-get install -y -qq amneziawg >/dev/null 2>&1; } || echo "AmneziaWG не поставился из PPA."
    else
      echo "AmneziaWG ставится автоматически только на Ubuntu. VPN работает и без него."
    fi
  fi
  if command -v awg >/dev/null && command -v awg-quick >/dev/null; then
    AWG_DIR=/etc/amnezia/amneziawg
    mkdir -p "$AWG_DIR"; chmod 700 "$AWG_DIR"
    if [ ! -f "$AWG_DIR/awg0.conf" ]; then
      DEV=$(ip route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "dev") {print $(i + 1); exit}}')
      AWG_PORT_NEW=${AWG_PORT:-51820}
      PRIV_AWG=$(awg genkey)
      S1=$(shuf -i 15-150 -n 1); S2=$(shuf -i 15-150 -n 1)
      [ $((S1 + 56)) -ne "$S2" ] || S2=$((S2 + 1))
      read -r H1 H2 H3 H4 < <(shuf -i 5-2147483647 -n 4 | tr '\n' ' ')
      PARAMS="Jc=4,Jmin=40,Jmax=70,S1=$S1,S2=$S2,H1=$H1,H2=$H2,H3=$H3,H4=$H4"
      umask 077
      {
        echo "[Interface]"
        echo "Address = 10.66.0.1/16"
        echo "ListenPort = $AWG_PORT_NEW"
        echo "PrivateKey = $PRIV_AWG"
        printf '%s\n' "$PARAMS" | tr ',' '\n' | sed 's/=/ = /'
        echo "PostUp = iptables -t nat -A POSTROUTING -s 10.66.0.0/16 -o $DEV -j MASQUERADE; iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT"
        echo "PostDown = iptables -t nat -D POSTROUTING -s 10.66.0.0/16 -o $DEV -j MASQUERADE; iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT"
      } > "$AWG_DIR/awg0.conf"
      umask 022
      if [ -z "$(envget AWG_PORT)" ]; then
        umask 077
        cat >> "$ENV" <<EOF
AWG_PORT=$AWG_PORT_NEW
AWG_PUBLIC_KEY=$(printf '%s' "$PRIV_AWG" | awg pubkey)
AWG_PARAMS=$PARAMS
AWG_NET=10.66.0.0/16
EOF
        umask 022
      fi
    fi
    echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-aurora-awg.conf
    sysctl -q -p /etc/sysctl.d/99-aurora-awg.conf || true
    if systemctl enable -q --now awg-quick@awg0 && awg show awg0 >/dev/null 2>&1; then
      AWG_OK=1
      echo "AmneziaWG работает на UDP $(envget AWG_PORT)."
    else
      echo "AmneziaWG не запустился: journalctl -u awg-quick@awg0 -n 30 --no-pager"
    fi
  fi
fi

# ---------- HTTPS для подписки: ключи не видны по дороге ----------
# Свой домен не нужен: имя вида 1-2-3-4.sslip.io само указывает на IP сервера,
# а Let's Encrypt бесплатно выдаёт на него сертификат (проверка идёт через порт 80).
SUB_TLS_OK=0
if [ -z "$(envget SUB_DOMAIN)" ] && command -v certbot >/dev/null; then
  say "Сертификат для подписки по HTTPS"
  IP_NOW=$(envget PUBLIC_HOST)
  if printf '%s' "$IP_NOW" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 80/tcp >/dev/null; fi
    for zone in sslip.io nip.io; do
      NAME="$(printf '%s' "$IP_NOW" | tr . -).$zone"
      if certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email \
           --preferred-challenges http -d "$NAME" >/dev/null 2>&1; then
        umask 077
        cat >> "$ENV" <<EOF
SUB_DOMAIN=$NAME
SUB_TLS_PORT=2097
SUB_TLS_CERT=/etc/letsencrypt/live/$NAME/fullchain.pem
SUB_TLS_KEY=/etc/letsencrypt/live/$NAME/privkey.pem
EOF
        umask 022
        echo "Подписка будет по HTTPS: https://$NAME:2097"
        SUB_TLS_OK=1
        break
      fi
      echo "Сертификат на $NAME не выдан, пробую другое имя"
    done
    [ "$SUB_TLS_OK" = 1 ] || echo "Сертификат не получен (нужен открытый TCP 80). Подписка пока по HTTP, повторный запуск попробует снова."
  fi
elif [ -n "$(envget SUB_DOMAIN)" ]; then
  SUB_TLS_OK=1
fi

say "Ускорение сети (BBR и буферы UDP)"
if ! grep -q "tcp_congestion_control=bbr" /etc/sysctl.conf 2>/dev/null; then
  printf 'net.core.default_qdisc=fq\nnet.ipv4.tcp_congestion_control=bbr\n' >> /etc/sysctl.conf
fi
# TCP Fast Open: повторное подключение к серверу без лишнего круга.
if ! grep -q "net.ipv4.tcp_fastopen=3" /etc/sysctl.conf 2>/dev/null; then
  printf 'net.ipv4.tcp_fastopen=3\n' >> /etc/sysctl.conf
fi
# Большие буферы UDP: без них QUIC (Hysteria2) упирается в скорость на быстрых каналах.
if ! grep -q "net.core.rmem_max=16777216" /etc/sysctl.conf 2>/dev/null; then
  printf 'net.core.rmem_max=16777216\nnet.core.wmem_max=16777216\n' >> /etc/sysctl.conf
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
TimeoutStopSec=15
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q xray
systemctl enable -q aurora-bot

say "Освобождаю порт 443 для VPN"
busy443() { ss -tlnpH 'sport = :443' | grep -v '"xray"' || true; }
if [ -n "$(busy443)" ]; then
  for svc in caddy nginx apache2 httpd lighttpd haproxy; do
    if systemctl is-active -q "$svc" 2>/dev/null; then
      echo "Порт 443 занят службой $svc, отключаю её: этот сервер нужен под VPN."
      systemctl disable --now "$svc" >/dev/null 2>&1 || true
    fi
  done
  sleep 2
  [ -z "$(busy443)" ] || fail "порт 443 занят другой программой: $(busy443). Остановите её или переустановите чистую Ubuntu."
fi
echo "Порт 443 свободен."

systemctl restart aurora-bot

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 443/tcp >/dev/null
  ufw allow "$SUB_PORT"/tcp >/dev/null
  if [ "$HY_OK" = 1 ]; then
    ufw allow "$(envget HY2_PORT)"/udp >/dev/null
    HY_EXTRA=$(envget HY2_EXTRA_PORTS); HY_EXTRA=${HY_EXTRA:-30000-30049}
    [ "$HY_EXTRA" = 0 ] || ufw allow "${HY_EXTRA/-/:}"/udp >/dev/null
  fi
  if [ "$SUB_TLS_OK" = 1 ]; then
    T_PORT=$(envget SUB_TLS_PORT); ufw allow "${T_PORT:-2097}"/tcp >/dev/null
  fi
  if [ "$AWG_OK" = 1 ]; then
    ufw allow "$(envget AWG_PORT)"/udp >/dev/null
    ufw route allow in on awg0 >/dev/null 2>&1 || true
  fi
  if [ -n "$(envget HY2_HOP_PORTS)" ]; then ufw allow "$(envget HY2_HOP_PORTS | tr - :)"/udp >/dev/null; fi
  XH_PORT=$(envget XRAY_XHTTP_PORT); XH_PORT=${XH_PORT:-8443}
  [ "$XH_PORT" = 0 ] || ufw allow "$XH_PORT"/tcp >/dev/null
fi

say "Проверка"
ok=1
# бот при запуске пишет конфиг Xray, перезапускает его и только потом поднимает раздачу
# подписок: ждём, пока заработает и то и другое (старый Xray мог держать 443 и до этого)
sleep 5
for _ in $(seq 1 45); do
  ss -tlnpH 'sport = :443' | grep -q '"xray"' && ss -tlnpH "sport = :$SUB_PORT" | grep -q python && break
  sleep 1
done
systemctl is-active -q aurora-bot && echo "✅ бот работает" || { echo "❌ бот не запустился"; ok=0; }
if ss -tlnpH 'sport = :443' | grep -q '"xray"'; then
  echo "✅ VPN принимает подключения на порту 443"
else
  echo "❌ VPN не слушает порт 443"; ok=0
fi
if ss -tlnpH "sport = :$SUB_PORT" | grep -q python; then
  echo "✅ подписки раздаются на порту $SUB_PORT"
else
  echo "❌ подписки не раздаются на порту $SUB_PORT"; ok=0
fi
if [ "$HY_OK" = 1 ]; then
  if systemctl is-active -q hysteria-server && ss -ulnpH "sport = :$(envget HY2_PORT)" | grep -q hysteria; then
    echo "✅ Hysteria2 принимает подключения на UDP $(envget HY2_PORT)"
  else
    echo "⚠️ Hysteria2 не запустился: journalctl -u hysteria-server -n 40 --no-pager"
    echo "   Reality работает и без него."
  fi
fi
if [ "$ok" = 1 ]; then
  echo
  echo "Готово. Откройте бота и отправьте /start, страны: /locations"
else
  echo
  echo "Пришлите вывод этих команд:"
  echo "  journalctl -u aurora-bot -n 40 --no-pager"
  echo "  journalctl -u xray -n 40 --no-pager"
  if [ "$HY_OK" = 1 ]; then echo "  journalctl -u hysteria-server -n 40 --no-pager"; fi
fi
