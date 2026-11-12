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
BRIDGE_PORT="${BRIDGE_PORT:-8444}"   # вход для мостов, которые проходят белые списки

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

# ---------- Hysteria2: подключение по UDP, проходит там, где оператор режет TCP ----------
HY=/usr/local/bin/hysteria
HYDIR=/etc/aurora

hy_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo amd64 ;;
    aarch64|arm64) echo arm64 ;;
    *) return 1 ;;
  esac
}

# Бинарник принимается, только если его SHA-256 совпадает со списком из того же релиза.
install_hysteria() {
  local arch tmp base want got
  arch=$(hy_arch) || { echo "Hysteria не поддерживает процессор $(uname -m)"; return 1; }
  tmp=$(mktemp -d)
  base=https://github.com/apernet/hysteria/releases/latest/download
  grab "$tmp/hashes.txt" "$base/hashes.txt" || { rm -rf "$tmp"; return 1; }
  want=$(awk -v f="build/hysteria-linux-$arch" '$2 == f {print $1; exit}' "$tmp/hashes.txt")
  [ -n "$want" ] || { rm -rf "$tmp"; return 1; }
  if [ -x "$HY" ] && [ "$(sha256sum "$HY" | cut -d' ' -f1)" = "$want" ]; then
    echo "Hysteria уже последней версии"; rm -rf "$tmp"; return 0
  fi
  echo "Качаю Hysteria..."
  grab "$tmp/hysteria" "$base/hysteria-linux-$arch" || { rm -rf "$tmp"; return 1; }
  got=$(sha256sum "$tmp/hysteria" | cut -d' ' -f1)
  [ "$got" = "$want" ] || { echo "Файл повреждён (контрольная сумма не совпала)"; rm -rf "$tmp"; return 1; }
  install -m 755 "$tmp/hysteria" "$HY"
  rm -rf "$tmp"
}

envget() { { grep -E "^$1=" "$ENV" || true; } | tail -1 | cut -d= -f2- | tr -d '"'; }  # нет ключа — пусто

hy_config() {  # $1 — plain (похож на HTTP/3) или obfs (похож на случайный UDP)
  # Конфиг собирает Python в формате JSON (JSON — частный случай YAML, Hysteria его читает):
  # так в нём не бывает синтаксических ошибок, что бы ни лежало в .env.
  local name="$1" port stats
  port=$(envget HY2_PORT); [ "$name" = obfs ] && port=$(envget HY2_OBFS_PORT)
  stats=$(envget HY2_STATS_PORTS | cut -d, -f"$([ "$name" = obfs ] && echo 2 || echo 1)")
  umask 077
  python3 - "$HYDIR/hy2-$name.yaml" "$name" "$port" "$HYDIR" "$(envget HY2_AUTH_PORT)" "$stats" \
    "$(envget HY2_STATS_SECRET)" "$(envget HY2_SNI)" "$(envget HY2_OBFS)" <<'PY'
import json, sys
out, name, port, d, auth, stats, secret, site, obfs = sys.argv[1:]
private = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16",
           "100.64.0.0/10", "fc00::/7", "fe80::/10", "::1/128"]
cfg = {
    "listen": f":{int(port)}",
    "tls": {"cert": f"{d}/hy2.crt", "key": f"{d}/hy2.key"},
    "auth": {"type": "http", "http": {"url": f"http://127.0.0.1:{int(auth)}/hy2auth"}},
    "trafficStats": {"listen": f"127.0.0.1:{int(stats)}", "secret": secret},
    "masquerade": {"type": "proxy", "proxy": {"url": f"https://{site}/", "rewriteHost": True}},
    "acl": {"inline": [f"reject({c})" for c in private] + ["direct(all)"]},
}
if name == "obfs":
    cfg["obfs"] = {"type": "salamander", "salamander": {"password": obfs}}
with open(out, "w") as f:
    json.dump(cfg, f, indent=1)
PY
  umask 022
}

hy_env_defaults() {  # дописывает в .env то, чего там не хватает (старые или неполные установки)
  local k v
  for kv in HY2_PORT=443 HY2_OBFS_PORT=8443 HY2_AUTH_PORT=20809 HY2_STATS_PORTS=20810,20811; do
    k=${kv%%=*}; v=${kv#*=}
    [ -n "$(envget "$k")" ] || { sed -i -E "/^$k=/d" "$ENV"; echo "$k=$v" >> "$ENV"; }
  done
  [ -n "$(envget HY2_SNI)" ] || { sed -i -E '/^HY2_SNI=/d' "$ENV"; echo "HY2_SNI=$(envget REALITY_SNI | grep . || echo www.nvidia.com)" >> "$ENV"; }
  for k in HY2_OBFS HY2_STATS_SECRET; do
    [ -n "$(envget "$k")" ] || { sed -i -E "/^$k=/d" "$ENV"; echo "$k=$(openssl rand -hex 16)" >> "$ENV"; }
  done
  if [ -f "$HYDIR/hy2.crt" ] && [ -z "$(envget HY2_PIN)" ]; then
    sed -i -E '/^HY2_PIN=/d' "$ENV"
    echo "HY2_PIN=$(openssl x509 -in "$HYDIR/hy2.crt" -outform der | sha256sum | cut -d' ' -f1)" >> "$ENV"
  fi
}

# Кто держит порт: «программа pid служба». Пусто — порт свободен. $1 — udp или tcp.
port_owner() {
  local line pid name unit
  line=$({ ss -"${1:0:1}"lnpH "sport = :$2" 2>/dev/null || true; } | head -1)
  [ -n "$line" ] || return 0
  pid=$(printf '%s' "$line" | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
  name=$(printf '%s' "$line" | grep -oE 'users:\(\("[^"]+' | head -1 | sed 's/.*("//')
  unit=$([ -n "$pid" ] && sed -nE 's#.*/([^/]+\.service)$#\1#p' "/proc/$pid/cgroup" 2>/dev/null | head -1)
  echo "${name:-?} ${pid:-?} ${unit:--}"
}

free_port() {  # первый свободный порт начиная с $2 ($1 — udp или tcp), кроме перечисленных дальше
  local p="$2" proto="$1"; shift 2
  while [ -n "$(port_owner "$proto" "$p")" ] || [[ " $* " == *" $p "* ]]; do p=$((p + 1)); done
  echo "$p"
}

env_set() { sed -i -E "/^$1=/d" "$ENV"; echo "$1=$2" >> "$ENV"; }

# Порты Hysteria может держать прежний VPN (например, старая Hysteria): показываем, что это,
# и с согласия останавливаем. Иначе берём свободный порт. Порты статистики меняем молча.
hy_free_ports() {
  local key port owner name pid unit ans s1 s2
  systemctl stop aurora-hy2@plain aurora-hy2@obfs >/dev/null 2>&1 || true
  # Службы прежней версии установщика: одна Hysteria на 443/udp, отдельные серверы стран,
  # перенаправление портов и AmneziaWG. Бот ими больше не управляет, а порты они занимают.
  local old
  for old in hysteria-server aurora-hop awg-quick@awg0 \
             $(systemctl list-units --all --plain --no-legend 'hysteria-loc@*' 2>/dev/null | awk '{print $1}'); do
    if systemctl is-enabled -q "$old" 2>/dev/null || systemctl is-active -q "$old" 2>/dev/null; then
      echo "Отключаю службу прежней версии: $old"
      systemctl disable --now "$old" >/dev/null 2>&1 || true
    fi
  done
  rm -f /etc/systemd/system/hysteria-server.service /etc/systemd/system/hysteria-loc@.service \
        /etc/systemd/system/aurora-hop.service /etc/aurora-hop.nft /etc/hysteria/loc-*.yaml
  sleep 1
  for key in HY2_PORT HY2_OBFS_PORT; do
    port=$(envget "$key")
    owner=$(port_owner udp "$port")
    [ -n "$owner" ] || continue
    read -r name pid unit <<<"$owner"
    echo "Порт $port/udp занят: программа $name (pid $pid, служба $unit)."
    echo "Обычно это прежний VPN. Если его остановить, старые ключи от него перестанут работать,"
    echo "клиентам нужно будет взять новую подписку в боте."
    ans=$(ask "Остановить его? (Enter — да, n — оставить и взять другой порт)" "y")
    case "$ans" in
      n|N|н|Н|no|нет)
        port=$(free_port udp $(( port == 443 ? 2443 : port + 1 )) "$(envget HY2_PORT)" "$(envget HY2_OBFS_PORT)")
        env_set "$key" "$port"
        echo "Hysteria будет на порту $port/udp." ;;
      *)
        if [ "$unit" != "-" ]; then
          systemctl disable --now "$unit" >/dev/null 2>&1 || true
        elif [ "$pid" != "?" ]; then
          kill "$pid" 2>/dev/null || true
        fi
        sleep 2
        if [ -n "$(port_owner udp "$port")" ]; then
          port=$(free_port udp $(( port == 443 ? 2443 : port + 1 )) "$(envget HY2_PORT)" "$(envget HY2_OBFS_PORT)")
          env_set "$key" "$port"
          echo "Освободить не вышло, Hysteria будет на порту $port/udp."
        else
          echo "Остановлено, порт $port/udp свободен."
        fi ;;
    esac
  done
  s1=$(envget HY2_STATS_PORTS | cut -d, -f1); s2=$(envget HY2_STATS_PORTS | cut -d, -f2)
  [ -z "$(port_owner tcp "$s1")" ] || s1=$(free_port tcp 20820)
  [ -z "$(port_owner tcp "$s2")" ] && [ "$s2" != "$s1" ] || s2=$(free_port tcp $((s1 + 1)) "$s1")
  [ "$s1,$s2" = "$(envget HY2_STATS_PORTS)" ] || env_set HY2_STATS_PORTS "$s1,$s2"
}

env_newline() {  # .env, поправленный вручную, может кончаться без перевода строки: дописанное склеилось бы
  [ ! -s "$ENV" ] || [ -z "$(tail -c1 "$ENV")" ] || echo >> "$ENV"
}

setup_hysteria() {
  mkdir -p "$HYDIR"
  env_newline
  if ! grep -qE '^HY2_PORT=' "$ENV"; then
    local site pin
    site=$(envget REALITY_SNI); site=${site:-www.nvidia.com}
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
      -keyout "$HYDIR/hy2.key" -out "$HYDIR/hy2.crt" -subj "/CN=$site" -addext "subjectAltName=DNS:$site" \
      >/dev/null 2>&1 || return 1
    chmod 600 "$HYDIR/hy2.key"
    pin=$(openssl x509 -in "$HYDIR/hy2.crt" -outform der | sha256sum | cut -d' ' -f1)
    umask 077
    cat >> "$ENV" <<EOF
HY2_PORT=443
HY2_OBFS_PORT=8443
HY2_SNI=$site
HY2_PIN=$pin
HY2_OBFS=$(openssl rand -hex 16)
HY2_AUTH_PORT=20809
HY2_STATS_PORTS=20810,20811
HY2_STATS_SECRET=$(openssl rand -hex 16)
EOF
    umask 022
  fi
  # ключи, которых нет или которые пустые, восстанавливаются
  if [ ! -f "$HYDIR/hy2.crt" ]; then
    local site; site=$(envget HY2_SNI); site=${site:-www.nvidia.com}
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
      -keyout "$HYDIR/hy2.key" -out "$HYDIR/hy2.crt" -subj "/CN=$site" -addext "subjectAltName=DNS:$site" \
      >/dev/null 2>&1 || return 1
    chmod 600 "$HYDIR/hy2.key"
    sed -i -E '/^HY2_PIN=/d' "$ENV"
  fi
  hy_env_defaults
  hy_free_ports
  hy_config plain || return 1
  hy_config obfs || return 1
  cat > /etc/systemd/system/aurora-hy2@.service <<EOF
[Unit]
Description=Aurora VPN Hysteria2 (%i)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$HY server -c $HYDIR/hy2-%i.yaml
Restart=always
RestartSec=3
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
  # QUIC работает быстрее с большими буферами UDP
  printf 'net.core.rmem_max=16777216\nnet.core.wmem_max=16777216\n' > /etc/sysctl.d/99-aurora-quic.conf
  sysctl -q -p /etc/sysctl.d/99-aurora-quic.conf 2>/dev/null || true
  systemctl daemon-reload
  systemctl enable -q aurora-hy2@plain aurora-hy2@obfs
  systemctl restart aurora-hy2@plain aurora-hy2@obfs
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

export DEBIAN_FRONTEND=noninteractive

# ---------- режим моста: российский сервер пересылает порт 443 на основной ----------
# Запуск на сервере-мосте:  bash <(curl -fsSL .../install.sh) bridge
# Мост пересылает подключения на отдельный вход основного сервера (порт 8444), который
# маскируется под российский сайт. Так подключение к мосту проходит и белые списки.
if [ "${1:-}" = "bridge" ]; then
  MAIN=$(ask "IP основного VPN-сервера")
  printf '%s' "$MAIN" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' || fail "нужен IP вида 1.2.3.4"
  TARGET=$(ask "Порт входа для мостов на основном сервере" "$BRIDGE_PORT")
  printf '%s' "$TARGET" | grep -Eq '^[0-9]{1,5}$' || fail "порт: число"
  say "Ставлю пересылку 443 → $MAIN:$TARGET"
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
    tcp dport 443 dnat to $MAIN:$TARGET
    udp dport 443 dnat to $MAIN:443
  }
  chain postrouting {
    type nat hook postrouting priority srcnat; policy accept;
    ip daddr $MAIN tcp dport $TARGET masquerade
    ip daddr $MAIN udp dport 443 masquerade
  }
}
EOF
  nft -f /etc/nftables.conf
  systemctl enable -q nftables
  # Мост держит много пересылаемых подключений: BBR и большая таблица соединений.
  cat > /etc/sysctl.d/99-aurora-bridge-tune.conf <<'EOF2'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.netfilter.nf_conntrack_max=262144
net.ipv4.tcp_keepalive_time=300
EOF2
  sysctl -q -p /etc/sysctl.d/99-aurora-bridge-tune.conf 2>/dev/null || true
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 443/tcp >/dev/null
    ufw allow 443/udp >/dev/null
    ufw route allow proto tcp to "$MAIN" port "$TARGET" >/dev/null 2>&1 || true
    ufw route allow proto udp to "$MAIN" port 443 >/dev/null 2>&1 || true
  fi
  if timeout 5 bash -c "</dev/tcp/$MAIN/$TARGET" 2>/dev/null; then
    echo "✅ основной сервер отвечает на порту $TARGET"
  else
    echo "⚠️ основной сервер не ответил на порту $TARGET. Обновите его установщиком этой версии"
    echo "   и проверьте, что порт $TARGET открыт у хостинга."
  fi
  BRIDGE_IP=$(curl -fsS4 --max-time 10 https://api.ipify.org || echo "IP_ЭТОГО_СЕРВЕРА")
  say "Мост готов"
  echo "Теперь в боте отправьте:"
  echo "  /addbridge ru1 🇷🇺 Обход | $BRIDGE_IP | ru"
  echo "Бот сам подберёт российский сайт для маскировки моста."
  exit 0
fi

say "Ставлю пакеты"
retry apt-get update -qq || fail "не удалось обновить список пакетов"
retry apt-get install -y -qq curl unzip git python3 python3-venv python3-pip openssl ca-certificates >/dev/null \
  || fail "не удалось поставить пакеты"

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
# GitHub отдаёт install.sh через кэш, и по ссылке несколько минут может приходить прошлая версия.
# Поэтому дальше работает установщик из только что скачанного кода: он всегда свежий.
if [ -z "${AURORA_REEXEC:-}" ] && [ -f "$BOT/install.sh" ]; then
  AURORA_REEXEC=1 exec bash "$BOT/install.sh" "$@"
fi
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
  # Сайт маскировки: самый быстрый с этого сервера из списка бота. Microsoft и подобные
  # самые известные сайты не предлагаем: под них маскируются слишком многие, и Xray об этом предупреждает.
  SNI_DEF=$(cd "$BOT" && timeout 90 "$BOT/.venv/bin/python" -c '
import asyncio, masking
r = asyncio.run(masking.ranked(masking.SITES))
print(r[0][0] if r else "www.nvidia.com")' 2>/dev/null || echo "www.nvidia.com")
  SNI=$(ask "Сайт для маскировки Reality" "${SNI_DEF:-www.nvidia.com}")
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

env_newline
# ---------- Xray или только Hysteria ----------
if ! grep -qE '^XRAY_ENABLED=' "$ENV"; then
  say "Способ подключения"
  echo "Hysteria (UDP) проходит там, где оператор режет обычные подключения. Xray нужен только"
  echo "для стран через прокси и как запасной вариант по TCP."
  KEEPX=$(ask "Оставить Xray вместе с Hysteria? (y — да, Enter — только Hysteria)" "n")
  case "$KEEPX" in y|Y|д|Д|yes|да) echo "XRAY_ENABLED=1" >> "$ENV" ;; *) echo "XRAY_ENABLED=0" >> "$ENV" ;; esac
fi
XRAY_ON=$(envget XRAY_ENABLED); XRAY_ON=${XRAY_ON:-1}

# ---------- подписка по HTTPS на своём домене: https://домен/ТОКЕН ----------
if ! grep -qE '^SUB_DOMAIN=' "$ENV"; then
  say "Домен для подписки"
  echo "Ссылка подписки будет вида https://домен/ZKwXhAPWFBHb7NZn. Нужен домен (или поддомен),"
  echo "у которого запись A указывает на IP этого сервера. Без Cloudflare-прокси (серое облако)."
  echo "Своего домена нет? Нажмите Enter: возьму бесплатное имя вида 1-2-3-4.sslip.io."
  DOMAIN=$(ask "Домен, например sub.example.com (Enter — бесплатное имя)" "")
  DOMAIN=$(printf '%s' "$DOMAIN" | tr 'A-Z' 'a-z' | sed -E 's#^https?://##; s#/.*##')
  echo "SUB_DOMAIN=$DOMAIN" >> "$ENV"
fi
DOMAIN=$(envget SUB_DOMAIN)
# Своего домена нет: имя вида 1-2-3-4.sslip.io само указывает на IP сервера, и Let's Encrypt
# выдаёт на него сертификат. Так подписка идёт по HTTPS и ключи не видны по дороге.
# SSLIP=0 при запуске — оставить подписку по HTTP.
if [ -z "$DOMAIN" ] && [ "${SSLIP:-1}" = 1 ]; then
  MYIP=$(envget PUBLIC_HOST)
  if printf '%s' "$MYIP" | grep -Eq '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    DOMAIN="$(printf '%s' "$MYIP" | tr . -).sslip.io"
    sed -i -E '/^SUB_DOMAIN=/d' "$ENV"
    echo "SUB_DOMAIN=$DOMAIN" >> "$ENV"
    echo "Своего домена нет: беру бесплатное имя $DOMAIN"
  fi
fi
if [ -n "$DOMAIN" ] && [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  say "Сертификат для $DOMAIN"
  MYIP=$(envget PUBLIC_HOST)
  GOT=$({ getent ahostsv4 "$DOMAIN" || true; } | awk '{print $1; exit}')
  if [ "$GOT" != "$MYIP" ]; then
    echo "⚠️ $DOMAIN указывает на ${GOT:-никуда}, а этот сервер $MYIP. Поправьте запись A у регистратора"
    echo "   и запустите установщик ещё раз. Пока подписка раздаётся по HTTP."
    case "$DOMAIN" in *.sslip.io) echo "   (Имя sslip.io не определилось: возможно, у сервера не работает DNS. Повторите позже.)" ;; esac
  else
    retry apt-get install -y -qq certbot >/dev/null || echo "не удалось поставить certbot"
    for svc in nginx apache2 caddy lighttpd; do systemctl disable --now "$svc" >/dev/null 2>&1 || true; done
    command -v ufw >/dev/null && ufw status | grep -q "Status: active" && ufw allow 80/tcp >/dev/null
    if certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email \
         -d "$DOMAIN" >/tmp/aurora-certbot.log 2>&1; then
      echo "✅ сертификат получен, продлевается сам"
    else
      echo "❌ сертификат не получен: tail -20 /tmp/aurora-certbot.log. Порт 80 должен быть открыт у хостинга."
    fi
  fi
fi
if [ -n "$DOMAIN" ] && [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  sed -i -E '/^SUB_(CERT|KEY|TLS_PORT)=/d' "$ENV"
  cat >> "$ENV" <<EOF
SUB_CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
SUB_KEY=/etc/letsencrypt/live/$DOMAIN/privkey.pem
SUB_TLS_PORT=$([ "$XRAY_ON" = 0 ] && echo 443 || echo 2053)
EOF
  # после продления сертификата бот перезапускается и подхватывает новый
  mkdir -p /etc/letsencrypt/renewal-hooks/deploy
  printf '#!/bin/sh\nsystemctl restart aurora-bot\n' > /etc/letsencrypt/renewal-hooks/deploy/aurora.sh
  chmod 755 /etc/letsencrypt/renewal-hooks/deploy/aurora.sh
fi

say "Ставлю Hysteria (подключение по UDP)"
HY_OK=0
if retry3 install_hysteria && setup_hysteria; then
  HY_OK=1
else
  echo "Hysteria поставить не удалось. Xray работает и без неё; запустите установщик ещё раз позже."
  if [ "$XRAY_ON" = 0 ]; then  # без обоих VPN не будет вовсе
    echo "Включаю Xray обратно, чтобы VPN работал."
    sed -i -E 's/^XRAY_ENABLED=.*/XRAY_ENABLED=1/' "$ENV"; XRAY_ON=1
  fi
fi

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
TimeoutStopSec=15
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
if [ "$XRAY_ON" = 1 ]; then
  systemctl enable -q xray
else
  systemctl disable --now xray >/dev/null 2>&1 || true
fi
systemctl enable -q aurora-bot

say "Освобождаю порт 443 для VPN"
busy443() { ss -tlnpH 'sport = :443' | grep -v '"xray"' | grep -v '"python' || true; }
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
  ufw allow "$BRIDGE_PORT"/tcp >/dev/null
  ufw allow "$(envget HY2_PORT)"/udp >/dev/null 2>&1 || true
  ufw allow "$(envget HY2_OBFS_PORT)"/udp >/dev/null 2>&1 || true
  [ -n "$(envget SUB_TLS_PORT)" ] && ufw allow "$(envget SUB_TLS_PORT)"/tcp >/dev/null
fi

say "Проверка"
ok=1
# бот при запуске пишет конфиг Xray, перезапускает его и только потом поднимает раздачу
# подписок: ждём, пока заработает и то и другое (старый Xray мог держать 443 и до этого)
sleep 5
for _ in $(seq 1 45); do
  { [ "$XRAY_ON" = 0 ] || ss -tlnpH 'sport = :443' | grep -q '"xray"'; } \
    && ss -tlnpH "sport = :$SUB_PORT" | grep -q python && break
  sleep 1
done
systemctl is-active -q aurora-bot && echo "✅ бот работает" || { echo "❌ бот не запустился"; ok=0; }
if [ "$XRAY_ON" = 0 ]; then
  echo "◇ Xray выключен, VPN идёт через Hysteria"
elif ss -tlnpH 'sport = :443' | grep -q '"xray"'; then
  echo "✅ VPN принимает подключения на порту 443"
else
  echo "❌ VPN не слушает порт 443"; ok=0
fi
TLSP=$(envget SUB_TLS_PORT)
if [ -n "$TLSP" ]; then
  if curl -fsS -m 10 -o /dev/null "https://$(envget SUB_DOMAIN):$TLSP/"; then
    echo "✅ подписка раздаётся по HTTPS: https://$(envget SUB_DOMAIN)$([ "$TLSP" = 443 ] || echo ":$TLSP")/..."
  else
    echo "❌ HTTPS-подписка не отвечает на $(envget SUB_DOMAIN):$TLSP"; ok=0
  fi
fi
if [ "$HY_OK" = 1 ]; then
  # упавшая служба перезапускается по кругу: проверяем, что за 5 секунд она не перезапускалась
  N1=$(systemctl show -p NRestarts --value aurora-hy2@plain aurora-hy2@obfs | tr '\n' ' ')
  sleep 5
  N2=$(systemctl show -p NRestarts --value aurora-hy2@plain aurora-hy2@obfs | tr '\n' ' ')
  for unit in aurora-hy2@plain aurora-hy2@obfs; do
    if systemctl is-active -q "$unit" && [ "$N1" = "$N2" ]; then
      echo "✅ $unit работает ($(grep -oE '"listen": *":[0-9]+"' "$HYDIR/hy2-${unit#*@}.yaml" | grep -oE '[0-9]+')/udp)"
    else
      echo "❌ $unit не запускается. Причина из журнала:"
      journalctl -u "$unit" -n 30 --no-pager 2>/dev/null | grep -E 'FATAL|ERROR|error' | tail -3 | cut -c1-300
      ok=0
    fi
  done
fi
if ss -tlnpH "sport = :$SUB_PORT" | grep -q python; then
  echo "✅ подписки раздаются на порту $SUB_PORT"
else
  echo "❌ подписки не раздаются на порту $SUB_PORT"; ok=0
fi
if [ "$ok" = 1 ]; then
  echo
  echo "Готово. Откройте бота и отправьте /start, страны: /locations"
else
  echo
  echo "Пришлите вывод этих команд:"
  echo "  journalctl -u aurora-bot -n 40 --no-pager"
  echo "  journalctl -u xray -n 40 --no-pager"
fi
