#!/usr/bin/env bash
# Смена сайта маскировки Reality. Запуск на сервере от root:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Saske356/Saske356/claude/android-usage-ql87m8/vpn-bot/sni.sh)
#       подобрать подходящий сайт, переключить на него сервер и проверить, что VPN работает
#   ... sni.sh) example.com    переключить на указанный сайт
#   ... sni.sh) list           только показать подходящие сайты, ничего не менять
# Нужна, когда оператор обрывает подключения к серверу: сайт маскировки виден в первом пакете.
# Если с новым сайтом VPN на сервере не заработал, прежний сайт возвращается сам.
# После смены клиентам нужно обновить подписку в приложении.
set -u

XRAY="${XRAY:-/usr/local/bin/xray}"
CFG="${CFG:-/usr/local/etc/xray/config.json}"
ENVF="${ENVF:-/opt/aurora/vpn-bot/.env}"
RAW="${RAW:-https://raw.githubusercontent.com/Saske356/Saske356/claude/android-usage-ql87m8/vpn-bot}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Крупные сайты с TLS 1.3 и HTTP/2. Не самые известные в мире: у тех адреса наперечёт,
# и чужой сервер под их именем заметен сразу (об этом Xray предупреждает сам).
CANDIDATES="www.x-kom.pl www.morele.net www.ceneo.pl www.olx.pl allegro.pl www.onet.pl www.wp.pl
www.interia.pl www.empik.com www.mediaexpert.pl www.nvidia.com www.amd.com www.asus.com
www.logitech.com www.cisco.com www.oracle.com www.sony.com www.ikea.com www.booking.com
addons.mozilla.org www.speedtest.net www.lovelive-anime.jp"

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root."; exit 1; }
[ -f "$ENVF" ] && [ -f "$CFG" ] || { echo "Не найдены настройки бота или конфиг Xray: сначала установите бота."; exit 1; }
# Действующий сайт берём из работающего конфига Xray: бот мог сменить его сам (команда /sni).
CUR=$(grep -o '"dest": "[^"]*' "$CFG" | head -1 | sed -E 's/.*"//; s/:[0-9]+$//')
[ -n "$CUR" ] || CUR=$(grep -E '^REALITY_SNI=' "$ENVF" | tail -1 | cut -d= -f2)
CUR=${CUR:-www.microsoft.com}
echo "Сейчас сервер маскируется под: $CUR"

MODE="auto"
case "${1:-}" in
  "") ;;
  list) MODE="list" ;;
  *) MODE="manual"
     printf '%s' "$1" | grep -Eq '^[a-z0-9.-]+\.[a-z]{2,}$' || { echo "Нужно имя сайта, например www.example.com"; exit 1; }
     CANDIDATES="$1" ;;
esac

# 1) Сайт должен открываться с сервера по TLS 1.3 и HTTP/2 с настоящим сертификатом.
echo "Проверяю сайты с сервера..."
# shellcheck disable=SC2086
python3 - "$CUR" $CANDIDATES >"$TMP/ranked" <<'PY'
import socket, ssl, sys, time
from concurrent.futures import ThreadPoolExecutor

current, hosts = sys.argv[1], [h for h in sys.argv[2:] if h != sys.argv[1]]


def check(host):
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    best = None
    try:
        for _ in range(2):
            t = time.monotonic()
            with socket.create_connection((host, 443), timeout=5) as raw:
                with ctx.wrap_socket(raw, server_hostname=host) as tls:
                    if tls.selected_alpn_protocol() != "h2":
                        return None
            ms = (time.monotonic() - t) * 1000
            best = ms if best is None else min(best, ms)
    except (OSError, ssl.SSLError, ValueError):
        return None
    return best


with ThreadPoolExecutor(8) as pool:
    results = list(zip(hosts, pool.map(check, hosts)))
for host, ms in sorted((r for r in results if r[1] is not None), key=lambda r: r[1]):
    print(f"{ms:.0f} {host}")
PY
if [ ! -s "$TMP/ranked" ]; then
  echo "Ни один сайт не подошёл: с сервера они не открываются по TLS 1.3 и HTTP/2. Ничего не менял."
  exit 1
fi

# 2) Xray сам знает сайты, под которые маскироваться рискованно: такие пропускаем.
with_site() {  # конфиг Xray, в котором сайт маскировки заменён на $1 -> файл $2
  python3 - "$CFG" "$1" "$2" <<'PY'
import json, sys
src, site, dst = sys.argv[1:]
cfg = json.load(open(src))
for ib in cfg.get("inbounds", []):
    rs = (ib.get("streamSettings") or {}).get("realitySettings")
    if rs is not None:
        rs.pop("target", None)
        rs["dest"] = site + ":443"
        rs["serverNames"] = [site]
json.dump(cfg, open(dst, "w"))
PY
}
: >"$TMP/good"
while read -r ms site; do
  with_site "$site" "$TMP/try.json" || continue
  out=$("$XRAY" run -test -c "$TMP/try.json" 2>&1) || continue
  if printf '%s' "$out" | grep -q "increase the likelihood"; then
    [ "$MODE" = "manual" ] || continue
    echo "Предупреждение Xray: под $site маскироваться рискованно, сервер проще распознать."
  fi
  echo "$ms $site" >>"$TMP/good"
done <"$TMP/ranked"
if [ ! -s "$TMP/good" ]; then
  echo "Все проверенные сайты Xray считает рискованными или не принимает. Ничего не менял."
  exit 1
fi
echo "Подходят (сайт, время ответа с сервера):"
head -8 "$TMP/good" | awk '{printf "  %-24s %s мс\n", $2, $1}'
[ "$MODE" = "list" ] && exit 0

set_site() {  # записать сайт в настройки бота и запустить его заново; бот сам обновит конфиг Xray
  systemctl stop aurora-bot
  if grep -qE '^REALITY_SNI=' "$ENVF"; then
    sed -i -E "s|^REALITY_SNI=.*|REALITY_SNI=$1|" "$ENVF"
  else
    echo "REALITY_SNI=$1" >>"$ENVF"
  fi
  # Новые версии бота хранят сайт маскировки в своём состоянии (команда /sni): правим и там.
  STATE=$(grep -E '^VPN_STATE=' "$ENVF" | tail -1 | cut -d= -f2); STATE=${STATE:-/var/lib/aurora/vpn.json}
  if [ -f "$STATE" ]; then
    python3 - "$STATE" "$1" <<'PY'
import json, os, sys, time
path, site = sys.argv[1:]
try:
    state = json.load(open(path, encoding="utf-8"))
except ValueError:
    sys.exit(0)
if "masking" in state:
    state["masking"].update(site=site, prev=[], changed=time.time())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
PY
  fi
  systemctl start aurora-bot
  for _ in $(seq 1 45); do
    grep -q "\"$1:443\"" "$CFG" 2>/dev/null && systemctl is-active -q xray && return 0
    sleep 1
  done
  return 1
}

vpn_works() {  # пробное подключение к VPN с самого сервера, как у клиента
  curl -fsSL -m 30 "$RAW/diag.sh" -o "$TMP/diag.sh" 2>/dev/null || return 2
  bash "$TMP/diag.sh" >"$TMP/diag.log" 2>&1
  grep -q "через VPN открылся интернет" "$TMP/diag.log"
}

# 3) Переключаем и проверяем. Не заработало — пробуем следующий сайт, в конце возвращаем прежний.
tried=0
while read -r ms site; do
  tried=$((tried + 1)); [ "$tried" -gt 3 ] && break
  echo
  echo "Переключаю сервер на $site..."
  if ! set_site "$site"; then
    echo "  бот не применил новые настройки, пробую следующий сайт."
    continue
  fi
  sleep 3
  vpn_works; res=$?
  if [ "$res" = 0 ] || [ "$res" = 2 ]; then
    [ "$res" = 2 ] && echo "  проверочный скрипт скачать не удалось: работу VPN на сервере проверьте командой diag.sh."
    echo
    echo "================ ГОТОВО ================"
    echo "Сервер теперь маскируется под $site (было: $CUR)."
    [ "$res" = 0 ] && echo "Пробное подключение на самом сервере прошло."
    echo "Что сделать: в приложении VPN обновите подписку (значок с круговыми стрелками)"
    echo "и запустите проверку пинга. Пока подписка не обновлена, старые ключи не работают."
    echo "Вернуть как было: bash <(curl -fsSL $RAW/sni.sh) $CUR"
    exit 0
  fi
  echo "  с этим сайтом VPN на сервере не заработал, пробую следующий."
done <"$TMP/good"

echo
echo "Ни с одним из сайтов VPN не заработал. Возвращаю прежний: $CUR"
set_site "$CUR" && echo "Прежние настройки возвращены." || echo "Вернуть не удалось: пришлите вывод journalctl -u aurora-bot -n 30 --no-pager"
exit 1
