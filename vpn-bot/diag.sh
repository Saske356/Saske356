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

ok()   { printf '✅ %s\n' "$*"; }
bad()  { printf '❌ %s\n' "$*"; PROBLEMS=$((PROBLEMS+1)); }
note() { printf '◆ %s\n' "$*"; }
PROBLEMS=0

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

echo "== Версии"
note "Код бота: $(git -C /opt/aurora rev-parse --abbrev-ref HEAD 2>/dev/null) $(git -C /opt/aurora log -1 --format='%h %cd' --date=format:'%d.%m %H:%M' 2>/dev/null)"
note "$("$XRAY" version 2>/dev/null | head -1)"

echo "== Службы и порты"
systemctl is-active -q xray && ok "служба xray запущена" || bad "служба xray не запущена"
systemctl is-active -q aurora-bot && ok "служба бота запущена" || bad "служба бота не запущена"
"$XRAY" run -test -c "$CFG" >"$TMP/test.log" 2>&1 && ok "конфиг Xray корректный" \
  || { bad "Xray ругается на конфиг:"; tail -5 "$TMP/test.log"; }

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
        print("DEST=%s" % (rs.get("dest") or rs.get("target") or ""))
        print("NCLIENTS=%d" % len(clients))
        print("UUID=%s" % (direct[0]["id"] if direct else ""))
        print("FLOW=%s" % (direct[0].get("flow", "") if direct else ""))
        print("NET=%s" % (ib["streamSettings"].get("network") or "tcp"))
        break
PY
# shellcheck disable=SC1091
. "$TMP/in.env" 2>/dev/null
if [ -z "${PORT:-}" ]; then
  bad "в конфиге Xray нет входа VLESS Reality"; cat "$TMP/py.err"
  echo; echo "ИТОГ: сервер настроен неправильно. Пришлите этот вывод."; exit 1
fi
note "Вход VPN: порт $PORT, транспорт $NET, маскировка под $SNI, ключей клиентов: $NCLIENTS"

listen() { ss -tlnpH "sport = :$1" 2>/dev/null; }
listen "$PORT" | grep -q xray && ok "Xray слушает порт $PORT" || bad "порт $PORT слушает не Xray: $(listen "$PORT" | awk '{print $NF}')"
SUBP=$(grep -E '^SUB_PORT=' "$ENVF" 2>/dev/null | cut -d= -f2); SUBP=${SUBP:-2096}
listen "$SUBP" | grep -q python && ok "подписки раздаются на порту $SUBP" || bad "подписки не раздаются на порту $SUBP"

echo "== Ключи"
PUB_ENV=$(grep -E '^REALITY_PUBLIC_KEY=' "$ENVF" 2>/dev/null | cut -d= -f2)
PUB=$("$XRAY" x25519 -i "$PRIV" 2>/dev/null | awk -F': *' 'tolower($1) ~ /public|password/ {print $2; exit}')
if [ -z "$PUB" ]; then
  bad "не удалось вычислить публичный ключ из приватного"
elif [ "$PUB" = "$PUB_ENV" ]; then
  ok "ключ в ссылках клиентов подходит к ключу сервера"
else
  bad "ключ в ссылках клиентов НЕ подходит к ключу сервера: клиенты не смогут подключиться"
fi
SNI_ENV=$(grep -E '^REALITY_SNI=' "$ENVF" 2>/dev/null | cut -d= -f2)
[ "$SNI_ENV" = "$SNI" ] && ok "имя сайта в ссылках совпадает с сервером" || bad "имя сайта в ссылках ($SNI_ENV) не совпадает с сервером ($SNI)"

echo "== Сайт для маскировки"
code=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$SNI/" 2>/dev/null)
[ "$code" != "000" ] && ok "сервер видит $SNI (ответ $code)" || bad "сервер не может открыть $SNI: Reality без него не работает"

echo "== Пробное подключение, как у клиента"
if [ -z "${UUID:-}" ]; then
  bad "нет ни одного активного ключа: возьмите в боте пробный день и запустите проверку ещё раз"
else
  SOCKS=10899
  python3 - "$TMP/client.json" "$PORT" "$UUID" "$FLOW" "$SNI" "$PUB" "$SID" "$SOCKS" <<'PY'
import json, sys
out, port, uuid, flow, sni, pub, sid, socks = sys.argv[1:]
user = {"id": uuid, "encryption": "none"}
if flow:
    user["flow"] = flow
json.dump({
    "log": {"loglevel": "warning"},
    "inbounds": [{"listen": "127.0.0.1", "port": int(socks), "protocol": "socks", "settings": {"udp": False}}],
    "outbounds": [{
        "protocol": "vless",
        "settings": {"vnext": [{"address": "127.0.0.1", "port": int(port), "users": [user]}]},
        "streamSettings": {"network": "tcp", "security": "reality",
                           "realitySettings": {"serverName": sni, "fingerprint": "chrome",
                                               "publicKey": pub, "shortId": sid}},
    }],
}, open(out, "w"))
PY
  "$XRAY" run -c "$TMP/client.json" >"$TMP/client.log" 2>&1 &
  CPID=$!
  sleep 3
  if ! kill -0 "$CPID" 2>/dev/null; then
    bad "пробный клиент не запустился:"; tail -5 "$TMP/client.log"
  else
    IP=$(curl -s -m 20 --socks5-hostname "127.0.0.1:$SOCKS" https://api.ipify.org 2>/dev/null)
    if [ -n "$IP" ]; then
      ok "через VPN открылся интернет, внешний адрес: $IP"
      LOOP_OK=1
    else
      bad "подключение через VPN не прошло:"; tail -6 "$TMP/client.log"
    fi
  fi
  kill "$CPID" 2>/dev/null
fi

echo "== Последние сообщения Xray"
journalctl -u xray -n 8 --no-pager 2>/dev/null | cut -c1-160

echo
echo "================ ИТОГ ================"
if [ "${LOOP_OK:-0}" = 1 ] && [ "$PROBLEMS" = 0 ]; then
  echo "Сервер настроен правильно: VPN на нём работает."
  echo "Если телефон при этом не подключается, соединение до сервера режет оператор"
  echo "(блокировка адреса хостинга или самого протокола). Это решается на стороне"
  echo "сервера другим способом подключения, а не правкой ключей."
elif [ "${LOOP_OK:-0}" = 1 ]; then
  echo "VPN работает, но есть замечания выше ($PROBLEMS)."
else
  echo "Проблема в настройке сервера ($PROBLEMS). Пришлите этот вывод целиком."
fi
