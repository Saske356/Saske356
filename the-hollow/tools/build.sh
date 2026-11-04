#!/usr/bin/env bash
# Собирает dist/TheHollow.mcaddon (Behavior Pack + Resource Pack).
# Запуск из папки the-hollow:  bash tools/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf build dist && mkdir -p build dist
cp -r BP "build/The Hollow BP"
cp -r RP "build/The Hollow RP"
(cd build && zip -qr ../dist/TheHollow.mcaddon "The Hollow BP" "The Hollow RP")
rm -rf build
echo "Готово: dist/TheHollow.mcaddon"
