#!/usr/bin/env bash
# Скачивает официальный XMRig (github.com/xmrig/xmrig) в папку ./xmrig
set -euo pipefail
cd "$(dirname "$0")"
URL=$(curl -fsSL https://api.github.com/repos/xmrig/xmrig/releases/latest \
  | grep -o '"browser_download_url": *"[^"]*linux-static-x64.tar.gz"' | head -1 | cut -d'"' -f4)
[ -n "$URL" ] || { echo "Не нашёл сборку XMRig для linux-x64"; exit 1; }
echo "Качаю $URL"
mkdir -p xmrig
curl -fsSL "$URL" | tar -xz -C xmrig --strip-components=1
chmod +x xmrig/xmrig
./xmrig/xmrig --version | head -1
echo "Готово. Теперь заполни .env и запусти: python bot.py"
