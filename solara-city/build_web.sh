#!/usr/bin/env bash
# Build the wasm bundle into dist/: solara.js + solara.wasm.gz + index.html
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
mkdir -p dist
wasm-bindgen --target web --no-typescript --out-dir dist --out-name solara target/wasm32-unknown-unknown/release/solara-city.wasm
if [ "${FAST:-0}" = 1 ]; then cp dist/solara_bg.wasm dist/solara_bg.opt.wasm; else
wasm-opt -Oz --enable-bulk-memory --enable-nontrapping-float-to-int --enable-sign-ext --enable-mutable-globals --enable-reference-types \
  -o dist/solara_bg.opt.wasm dist/solara_bg.wasm; fi
gzip -9 -c dist/solara_bg.opt.wasm > dist/solara.wasm.gz
rm dist/solara_bg.wasm dist/solara_bg.opt.wasm
cp web/index.html dist/index.html
ls -la dist
