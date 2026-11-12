#!/usr/bin/env bash
# Диагностика Aurora VPN. Запуск на сервере от root:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Saske356/Saske356/claude/android-usage-ql87m8/vpn-bot/diag.sh)
# Подключается к VPN с самого сервера так же, как клиент, и говорит, где проблема.
# С параметром watch минуту следит за портом VPN и показывает, на каком шаге обрывается
# подключение телефона (на это время включает подробный журнал Xray, потом возвращает как было).
# Без параметра ничего не меняет в настройках. Токен, ключи и пароли не печатает.
set -u

XRAY="${XRAY:-/usr/local/bin/xray}"
CFG="${CFG:-/usr/local/etc/xray/config.json}"
ENVF="${ENVF:-/opt/aurora/vpn-bot/.env}"
TMP=$(mktemp -d)
trap 'kill "${CPID:-}" 2>/dev/null; rm -rf "$TMP"' EXIT
: > "$TMP/fails"

# Режим наблюдения:  bash <(curl -fsSL .../diag.sh) watch [секунд]
# Показывает, на каком шаге обрывается подключение телефона. На время наблюдения включает
# подробный журнал Xray (Xray перезапускается дважды), в конце возвращает конфиг как был.
if [ "${1:-}" = "watch" ]; then
  SECS="${2:-60}"
  WPORT=$(grep -E '^VPN_PORT=' "$ENVF" 2>/dev/null | cut -d= -f2); WPORT=${WPORT:-443}
  DETAIL=0
  restore() {
    # возвращаем прежний конфиг, только если его за это время не обновил сам бот
    if [ "$DETAIL" = 1 ] && cmp -s "$CFG" "$TMP/config.debug"; then
      cp -p "$TMP/config.orig" "$CFG" && systemctl restart xray
    fi
    DETAIL=0
  }
  trap 'restore; rm -rf "$TMP"' EXIT
  trap 'exit 1' INT TERM HUP
  if [ -f "$CFG" ] && cp -p "$CFG" "$TMP/config.orig" && cp -p "$CFG" "$TMP/config.debug" \
     && python3 - "$TMP/config.debug" <<'PY'
import json, sys
path = sys.argv[1]
cfg = json.load(open(path))
cfg["log"] = {"loglevel": "debug"}
for ib in cfg.get("inbounds", []):
    rs = (ib.get("streamSettings") or {}).get("realitySettings")
    if rs is not None:
        rs["show"] = True
with open(path, "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=1)
PY
  then
    if "$XRAY" run -test -c "$TMP/config.debug" >/dev/null 2>&1; then
      cp -p "$TMP/config.debug" "$CFG" && DETAIL=1
      systemctl restart xray || restore
    fi
  fi
  HAD_DETAIL=$DETAIL
  [ "$DETAIL" = 1 ] || echo "Подробный журнал Xray включить не удалось, смотрю только на подключения."
  sleep 2
  START=$(date '+%Y-%m-%d %H:%M:%S')
  echo "Слежу за портом $WPORT $SECS секунд."
  echo ">>> Сейчас откройте приложение VPN на телефоне и запустите проверку пинга или подключитесь."
  END=$((SECONDS + SECS))
  while [ "$SECONDS" -lt "$END" ]; do
    ss -Htn "( sport = :$WPORT )" 2>/dev/null | awk '{print $1, $NF}' >>"$TMP/seen"
    sleep 0.2
  done
  journalctl -u xray --since "$START" --no-pager -o cat 2>/dev/null \
    | grep -Ev '127\.0\.0\.1|Reading config|Xray [0-9.]+ |anti-censorship|will increase the likelihood|Logger started' >"$TMP/xlog"
  restore
  # состояние, адрес и порт клиента; подключения с самого сервера не считаем
  awk '{a=$2; p=a; sub(/.*:/, "", p); sub(/:[0-9]+$/, "", a); gsub(/^\[(::ffff:)?|\]$/, "", a); print $1, a, p}' \
    "$TMP/seen" 2>/dev/null | grep -Ev ' (127\.|::1 )' | sort -u >"$TMP/peers"
  ESTAB=$(grep -c '^ESTAB ' "$TMP/peers")
  HELLO=$(grep -c 'REALITY remoteAddr' "$TMP/xlog")
  INVALID=$(grep -ciE 'invalid|failed to|rejected' "$TMP/xlog")
  ACCEPTED=$(grep -cE ' accepted |received request for|default route for|taking detour' "$TMP/xlog")
  echo
  echo "== Что видел сервер"
  if [ "$HAD_DETAIL" = 1 ]; then
    echo "Последние строки журнала Xray:"
    tail -10 "$TMP/xlog" | cut -c1-150 | sed 's/^/  /'
  fi
  AUTH=$(grep -c 'hs.c.conn == conn: true' "$TMP/xlog")
  # когда на сервере менялась версия Xray: после обновления старое приложение может перестать понимать сервер
  VERSIONS=$(journalctl -u xray --no-pager -o short-iso 2>/dev/null | grep -E 'Xray [0-9.]+ started' \
    | awk '{v=$(NF-1); if (v != last) {printf "%s%s с %s", sep, v, substr($1, 1, 10); sep=", "; last=v}}')
  SITE=$(grep -o '"dest": "[^"]*' "$CFG" | head -1 | sed -E 's/.*"//; s/:[0-9]+$//')
  echo
  echo "================ ИТОГ ================"
  echo "Подключений установлено: $ESTAB (адресов: $(awk '{print $2}' "$TMP/peers" | sort -u | wc -l))"
  if [ "$HAD_DETAIL" = 1 ]; then
    echo "Приветствий VPN дошло до Xray: $HELLO, из них от своих клиентов: $AUTH"
    echo "Отказов: $INVALID, принятых запросов: $ACCEPTED"
  fi
  echo "Сайт маскировки: ${SITE:-?}. Версии Xray: ${VERSIONS:-нет данных}"
  echo
  if [ ! -s "$TMP/peers" ] && [ "$((HELLO + INVALID + ACCEPTED))" -eq 0 ]; then
    echo "За $SECS секунд до порта $WPORT не дошло ни одного подключения."
    echo "Сервер доступен, но именно порт VPN для телефона закрыт по дороге: поможет другой порт."
  elif [ "$ACCEPTED" -gt 0 ]; then
    echo "Сервер принял подключение телефона и пустил его в интернет: со стороны сервера всё работает."
    echo "Если в приложении всё равно «н/д», не срабатывает сам замер пинга в приложении."
  elif [ "$INVALID" -gt 0 ]; then
    echo "Подключение телефона дошло, но сервер его не принял (строки с отказом выше)."
    echo "Так бывает, когда приложение и сервер не договорились: устаревшее приложение или старый ключ."
  elif [ "$AUTH" -gt 0 ]; then
    echo "Сервер узнал своего клиента и ответил ему, но телефон дальше ничего не прислал."
    echo "Ключи и сайт маскировки в порядке. Либо ответ сервера обрывают по дороге, либо приложение"
    echo "на телефоне не понимает ответ этой версии Xray (см. версии выше: менялась ли она недавно)."
  elif [ "$HELLO" -gt 0 ]; then
    echo "Приветствие телефона дошло, но сервер не узнал в нём своего клиента."
    echo "Так бывает, когда в приложении старые ключи: обновите в нём подписку и проверьте ещё раз."
  elif [ "$ESTAB" -gt 0 ] && [ "$HAD_DETAIL" = 1 ]; then
    echo "Телефон соединяется с сервером, но его первый пакет до Xray не доходит."
    echo "Это обрыв по дороге, на стороне оператора. Если смена сайта маскировки не помогла,"
    echo "остаётся другой порт или вход через другой сервер (мост)."
  elif [ "$ESTAB" -gt 0 ]; then
    echo "Телефон соединяется с сервером, но без подробного журнала не видно, что происходит дальше."
  else
    echo "Подключения начинаются, но не устанавливаются: их обрывают по дороге к серверу."
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

# Запасной вход XHTTP на том же порту: в подписке он идёт с пометкой «· запасной».
XPATH=$(python3 -c '
import json, sys
cfg = json.load(open(sys.argv[1]))
print(next((ib["streamSettings"].get("xhttpSettings", {}).get("path", "") for ib in cfg.get("inbounds", [])
            if (ib.get("streamSettings") or {}).get("network") == "xhttp"), ""))' "$CFG" 2>/dev/null)
if [ -n "$XPATH" ] && [ -n "${UUID:-}" ] && [ -n "${STARTED:-}" ]; then
  echo "== Запасное подключение XHTTP"
  make_client vnext
  python3 - "$TMP/client.json" "$XPATH" <<'PY'
import json, sys
path, xpath = sys.argv[1:]
cfg = json.load(open(path))
ob = cfg["outbounds"][0]
for u in ob["settings"]["vnext"][0]["users"]:
    u.pop("flow", None)
ob["streamSettings"]["network"] = "xhttp"
ob["streamSettings"]["xhttpSettings"] = {"path": xpath, "mode": "auto"}
json.dump(cfg, open(path, "w"))
PY
  "$XRAY" run -c "$TMP/client.json" >"$TMP/client.x.log" 2>&1 &
  CPID=$!
  sleep 3
  IP=$(curl -s -m 20 --socks5-hostname "127.0.0.1:$SOCKS" https://api.ipify.org 2>"$TMP/curl.err")
  if [ -n "$IP" ]; then
    ok "запасное подключение XHTTP работает"
  else
    { echo "curl: $(cat "$TMP/curl.err")"; tail -n 4 "$TMP/client.x.log"; } > "$TMP/xhttp.log"
    bad "запасное подключение XHTTP не прошло" "$TMP/xhttp.log"
  fi
  kill "$CPID" 2>/dev/null
fi
BPORT=$(python3 -c '
import json, sys
cfg = json.load(open(sys.argv[1]))
print(next((ib["port"] for ib in cfg.get("inbounds", []) if ib.get("tag") == "in-b"), ""))' "$CFG" 2>/dev/null)
if [ -n "$BPORT" ]; then
  listen "$BPORT" | grep -q xray && ok "вход для мостов слушает порт $BPORT" \
    || bad "вход для мостов не слушает порт $BPORT"
fi

# Hysteria (UDP): пробное подключение с паролем действующего клиента
HYBIN=/usr/local/bin/hysteria
if grep -qE '^HY2_PORT=' "$ENVF" 2>/dev/null; then
  echo "== Hysteria (UDP)"
  for unit in aurora-hy2@plain aurora-hy2@obfs; do
    systemctl is-active -q "$unit" && ok "служба $unit запущена" \
      || bad "служба $unit не запущена: journalctl -u $unit -n 20 --no-pager"
  done
  HYP=$(grep -E '^HY2_PORT=' "$ENVF" | cut -d= -f2)
  ss -ulnpH "sport = :$HYP" 2>/dev/null | grep -q hysteria && ok "Hysteria слушает $HYP/udp" \
    || bad "$HYP/udp слушает не Hysteria: $(ss -ulnpH "sport = :$HYP" 2>/dev/null | grep -oE 'users:\(\("[^"]+' | sed 's/.*("//')"
  STATEF=$(grep -E '^VPN_STATE=' "$ENVF" | tail -1 | cut -d= -f2); STATEF=${STATEF:-/var/lib/aurora/vpn.json}
  HYPASS=$(python3 - "$STATEF" <<'PY' 2>/dev/null
import hashlib, hmac, json, sys, time
st = json.load(open(sys.argv[1]))
uid = next((u for u, exp in st.get("users", {}).items() if exp > time.time()), None)
if uid:
    print(uid + "." + hmac.new(st["secret"].encode(), f"hy2:{uid}".encode(), hashlib.sha256).hexdigest()[:20])
PY
)
  HYPORT=$(grep -E '^HY2_PORT=' "$ENVF" | cut -d= -f2); HYSNI=$(grep -E '^HY2_SNI=' "$ENVF" | cut -d= -f2)
  if [ -z "$HYPASS" ]; then
    bad "нет активного ключа для пробного подключения Hysteria"
  elif [ -x "$HYBIN" ]; then
    printf 'server: 127.0.0.1:%s\nauth: %s\ntls:\n  sni: %s\n  insecure: true\nsocks5:\n  listen: 127.0.0.1:10898\n' \
      "$HYPORT" "$HYPASS" "$HYSNI" > "$TMP/hy.yaml"
    "$HYBIN" client -c "$TMP/hy.yaml" >"$TMP/hy.log" 2>&1 &
    CPID=$!
    sleep 3
    IP=$(curl -s -m 20 --socks5-hostname 127.0.0.1:10898 https://api.ipify.org 2>/dev/null)
    if [ -n "$IP" ]; then
      ok "через Hysteria открылся интернет"
    else
      { tail -n 6 "$TMP/hy.log"; journalctl -u aurora-hy2@plain -n 4 --no-pager 2>/dev/null; } > "$TMP/hyerr.log"
      bad "подключение через Hysteria не прошло" "$TMP/hyerr.log"
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
