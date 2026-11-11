#!/usr/bin/env bash
# Диагностика Aurora VPN. Запуск на сервере от root:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Saske356/Saske356/claude/android-usage-ql87m8/vpn-bot/diag.sh)
# Подключается к VPN с самого сервера так же, как клиент, и говорит, где проблема.
# С параметром watch следит, доходят ли подключения телефона до порта VPN.
# Ничего не меняет в настройках. Токен, ключи и пароли не печатает.
set -u

XRAY="${XRAY:-/usr/local/bin/xray}"
CFG="${CFG:-/usr/local/etc/xray/config.json}"
ENVF="${ENVF:-/opt/aurora/vpn-bot/.env}"
TMP=$(mktemp -d)
trap 'kill "${CPID:-}" 2>/dev/null; rm -rf "$TMP"' EXIT
: > "$TMP/fails"

# Режим наблюдения:  bash <(curl -fsSL .../diag.sh) watch [секунд]
# Показывает, доходят ли подключения телефона до порта VPN, пока вы подключаетесь в приложении.
if [ "${1:-}" = "watch" ]; then
  SECS="${2:-60}"
  WPORT=$(grep -E '^VPN_PORT=' "$ENVF" 2>/dev/null | cut -d= -f2); WPORT=${WPORT:-443}
  echo "Слежу за портом $WPORT $SECS секунд."
  echo "Сейчас откройте приложение VPN на телефоне и подключитесь (или запустите проверку пинга)."
  END=$((SECONDS + SECS))
  while [ "$SECONDS" -lt "$END" ]; do
    ss -Htn "( sport = :$WPORT )" 2>/dev/null | awk '{print $1, $NF}' >>"$TMP/seen"
    sleep 0.2
  done
  # состояние, адрес и порт клиента; подключения с самого сервера не считаем
  awk '{a=$2; p=a; sub(/.*:/, "", p); sub(/:[0-9]+$/, "", a); gsub(/^\[(::ffff:)?|\]$/, "", a); print $1, a, p}' \
    "$TMP/seen" 2>/dev/null | grep -Ev ' (127\.|::1 )' | sort -u >"$TMP/peers"
  echo
  if [ ! -s "$TMP/peers" ]; then
    echo "ИТОГ: за $SECS секунд на порт $WPORT не пришло ни одного подключения."
    echo "Телефон до порта VPN не доходит, хотя сервер доступен: оператор режет именно этот порт или протокол."
    exit 0
  fi
  if grep -q '^ESTAB ' "$TMP/peers"; then
    echo "Кто подключался (адрес и число подключений):"
    awk '$1 == "ESTAB" {n[$2]++} END {for (a in n) printf "  %s  %d\n", a, n[a]}' "$TMP/peers" | sort
    echo
    echo "ИТОГ: подключения до порта $WPORT доходят."
    echo "Если в приложении при этом нет связи, обрывается само VPN-соединение после установки связи:"
    echo "оператор распознаёт протокол, либо приложение на телефоне устарело."
  else
    echo "ИТОГ: подключения начинаются, но не устанавливаются: их обрывают по дороге к серверу."
  fi
  exit 0
fi


ok()   { printf '✅ %s\n' "$*"; }
note() { printf '◆ %s\n' "$*"; }
# bad "что не так" [файл с подробностями]: печатает сразу и запоминает для блока ИТОГ
bad() {
  printf '❌ %s\n' "$1"
  printf '❌ %s\n' "$1" >> "$TMP/fails"
  if [ -n "${2:-}" ] && [ -s "$2" ]; then
    tail -n 6 "$2" | cut -c1-200 | sed 's/^/     /' | tee -a "$TMP/fails"
  fi
  PROBLEMS=$((PROBLEMS+1))
}
PROBLEMS=0

echo "== Версии"
note "Код бота: $(git -C /opt/aurora rev-parse --abbrev-ref HEAD 2>/dev/null) $(git -C /opt/aurora log -1 --format='%h %cd' --date=format:'%d.%m %H:%M' 2>/dev/null)"
note "$("$XRAY" version 2>/dev/null | head -1)"

echo "== Службы и порты"
systemctl is-active -q xray && ok "служба xray запущена" || bad "служба xray не запущена"
systemctl is-active -q aurora-bot && ok "служба бота запущена" || bad "служба бота не запущена"
"$XRAY" run -test -c "$CFG" >"$TMP/test.log" 2>&1 && ok "конфиг Xray корректный" \
  || bad "Xray ругается на рабочий конфиг" "$TMP/test.log"

# Основной вход VLESS Reality из рабочего конфига: порт, имя сайта, short id, приватный ключ, клиент
python3 - "$CFG" >"$TMP/in.env" 2>"$TMP/py.err" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
for ib in cfg.get("inbounds", []):
    rs = (ib.get("streamSettings") or {}).get("realitySettings")
    if ib.get("protocol") == "vless" and rs:
        clients = ib["settings"].get("clients", [])
        direct = [c for c in clients if str(c.get("email", "")).endswith(".main")] or clients
        print("PORT=%s" % ib["port"])
        print("SNI=%s" % rs["serverNames"][0])
        print("SID=%s" % rs["shortIds"][0])
        print("PRIV=%s" % rs["privateKey"])
        print("NCLIENTS=%d" % len(clients))
        print("UUID=%s" % (direct[0]["id"] if direct else ""))
        print("FLOW=%s" % (direct[0].get("flow", "") if direct else ""))
        print("NET=%s" % (ib["streamSettings"].get("network") or "tcp"))
        break
PY
# shellcheck disable=SC1091
. "$TMP/in.env" 2>/dev/null
if [ -z "${PORT:-}" ]; then
  bad "в конфиге Xray нет входа VLESS Reality" "$TMP/py.err"
  echo; echo "================ ИТОГ ================"
  cat "$TMP/fails"
  echo "Сервер настроен неправильно. Пришлите этот блок."; exit 1
fi
note "Вход VPN: порт $PORT, транспорт $NET, маскировка под $SNI, ключей клиентов: $NCLIENTS"

listen() { ss -tlnpH "sport = :$1" 2>/dev/null; }
listen "$PORT" | grep -q xray && ok "Xray слушает порт $PORT" \
  || bad "порт $PORT слушает не Xray: $(listen "$PORT" | awk '{print $NF}')"
SUBP=$(grep -E '^SUB_PORT=' "$ENVF" 2>/dev/null | cut -d= -f2); SUBP=${SUBP:-2096}
listen "$SUBP" | grep -q python && ok "подписки раздаются на порту $SUBP" || bad "подписки не раздаются на порту $SUBP"

echo "== Ключи"
PUB_ENV=$(grep -E '^REALITY_PUBLIC_KEY=' "$ENVF" 2>/dev/null | cut -d= -f2)
"$XRAY" x25519 -i "$PRIV" >"$TMP/x25519.out" 2>&1
PUB=$(awk -F': *' 'tolower($1) ~ /public|password/ {print $2; exit}' "$TMP/x25519.out")
if [ -z "$PUB" ]; then
  # сам ключ не печатаем: показываем только названия полей, которые выдал Xray
  cut -d: -f1 "$TMP/x25519.out" > "$TMP/x25519.fields"
  bad "не удалось вычислить публичный ключ из приватного, Xray выдал поля:" "$TMP/x25519.fields"
elif [ "$PUB" = "$PUB_ENV" ]; then
  ok "ключ в ссылках клиентов подходит к ключу сервера"
else
  bad "ключ в ссылках клиентов НЕ подходит к ключу сервера: клиенты не смогут подключиться"
fi
SNI_ENV=$(grep -E '^REALITY_SNI=' "$ENVF" 2>/dev/null | cut -d= -f2)
[ "$SNI_ENV" = "$SNI" ] && ok "имя сайта в ссылках совпадает с сервером" \
  || bad "имя сайта в ссылках ($SNI_ENV) не совпадает с сервером ($SNI)"

echo "== Сайт для маскировки"
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$SNI/" 2>/dev/null)
[ "$code" != "000" ] && ok "сервер видит $SNI (ответ $code)" \
  || bad "сервер не может открыть $SNI: Reality без него не работает"

echo "== Пробное подключение, как у клиента"
SOCKS=10899
# Пробный клиент в двух форматах настроек: классическом (vnext) и новом плоском.
make_client() {
  python3 - "$TMP/client.json" "$1" "$PORT" "$UUID" "$FLOW" "$SNI" "${PUB:-$PUB_ENV}" "$SID" "$SOCKS" <<'PY'
import json, sys
out, fmt, port, uuid, flow, sni, pub, sid, socks = sys.argv[1:]
if fmt == "vnext":
    user = {"id": uuid, "encryption": "none"}
    if flow:
        user["flow"] = flow
    settings = {"vnext": [{"address": "127.0.0.1", "port": int(port), "users": [user]}]}
else:
    settings = {"address": "127.0.0.1", "port": int(port), "id": uuid, "encryption": "none"}
    if flow:
        settings["flow"] = flow
json.dump({
    "log": {"loglevel": "warning"},
    "inbounds": [{"listen": "127.0.0.1", "port": int(socks), "protocol": "socks", "settings": {"udp": False}}],
    "outbounds": [{
        "protocol": "vless", "settings": settings,
        "streamSettings": {"network": "tcp", "security": "reality",
                           "realitySettings": {"serverName": sni, "fingerprint": "chrome",
                                               "publicKey": pub, "shortId": sid}},
    }],
}, open(out, "w"))
PY
}

if [ -z "${UUID:-}" ]; then
  bad "нет ни одного активного ключа: возьмите в боте пробный день (или оформите подписку) и запустите проверку ещё раз"
else
  STARTED=""
  for fmt in vnext flat; do
    make_client "$fmt"
    "$XRAY" run -c "$TMP/client.json" >"$TMP/client.$fmt.log" 2>&1 &
    CPID=$!
    sleep 3
    if kill -0 "$CPID" 2>/dev/null; then STARTED=$fmt; break; fi
  done
  if [ -z "$STARTED" ]; then
    cat "$TMP/client.vnext.log" "$TMP/client.flat.log" 2>/dev/null | grep -v '^$' > "$TMP/client.all.log"
    bad "пробный клиент не запустился ни в одном формате (это ошибка самой проверки, а не VPN)" "$TMP/client.all.log"
    CHECK_BROKEN=1
  else
    SINCE=$(date '+%Y-%m-%d %H:%M:%S')
    IP=$(curl -s -m 20 --socks5-hostname "127.0.0.1:$SOCKS" https://api.ipify.org 2>"$TMP/curl.err")
    if [ -n "$IP" ]; then
      ok "через VPN открылся интернет, внешний адрес: $IP"
      LOOP_OK=1
    else
      { echo "curl: $(cat "$TMP/curl.err")"; echo "клиент:"; tail -n 4 "$TMP/client.$STARTED.log"
        echo "сервер:"; journalctl -u xray --since "$SINCE" --no-pager 2>/dev/null | tail -n 4; } > "$TMP/tunnel.log"
      bad "подключение через VPN не прошло" "$TMP/tunnel.log"
    fi
    kill "$CPID" 2>/dev/null
  fi
fi

echo "== Последние сообщения Xray"
journalctl -u xray -n 6 --no-pager 2>/dev/null | cut -c1-160

echo
echo "================ ИТОГ ================"
cat "$TMP/fails"
if [ "${LOOP_OK:-0}" = 1 ] && [ "$PROBLEMS" = 0 ]; then
  echo "Сервер настроен правильно: VPN на нём работает."
  echo "Если телефон при этом не подключается, соединение до сервера режет оператор"
  echo "(блокировка адреса хостинга или самого протокола). Это решается на стороне"
  echo "сервера другим способом подключения, а не правкой ключей."
elif [ "${LOOP_OK:-0}" = 1 ]; then
  echo "VPN работает, но есть замечания выше ($PROBLEMS)."
elif [ "${CHECK_BROKEN:-0}" = 1 ] && [ "$PROBLEMS" = 1 ]; then
  echo "Остальные проверки прошли, но пробное подключение выполнить не удалось."
  echo "Пришлите этот блок ИТОГ: по нему поправлю саму проверку."
else
  echo "Найдено проблем: $PROBLEMS. Пришлите этот блок ИТОГ целиком."
fi
