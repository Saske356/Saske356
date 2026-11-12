#!/bin/bash
# Сборка Aurora VPN для Android из v2rayNG: bash android/build.sh [рабочая папка]
# Нужны: Java 17+, Android SDK ($ANDROID_HOME) с NDK ($NDK_HOME), git, curl, python3 с Pillow.
# Подпись: KEYSTORE, KEYSTORE_PASSWORD, KEY_ALIAS, KEY_PASSWORD (иначе — ключ из android/aurora.keystore).
# Готовые APK кладутся в android/out/.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:-$HERE/build}"
OUT="$HERE/out"
# shellcheck disable=SC1091
source <(grep -E '^[A-Z0-9_]+=' "$HERE/UPSTREAM")
: "${ANDROID_HOME:?нужен ANDROID_HOME}" "${NDK_HOME:?нужен NDK_HOME}"

if [ ! -d "$WORK/.git" ] || [ "$(git -C "$WORK" rev-parse HEAD)" != "$V2RAYNG_COMMIT" ]; then
  rm -rf "$WORK"; mkdir -p "$WORK"
  git -C "$WORK" init -q
  git -C "$WORK" remote add origin "$V2RAYNG_REPO"
  git -C "$WORK" fetch -q --depth 1 origin "$V2RAYNG_COMMIT"
  git -C "$WORK" checkout -q FETCH_HEAD
  git -C "$WORK" submodule update -q --init --recursive --depth 1
else
  git -C "$WORK" checkout -q -- .   # прошлые правки customize.py снимаем
  git -C "$WORK" clean -qfd V2rayNG/app/src
fi

APP="$WORK/V2rayNG/app"
mkdir -p "$APP/libs"
if [ ! -f "$WORK/libs/arm64-v8a/libhev-socks5-tunnel.so" ]; then
  (cd "$WORK" && bash compile-hevtun.sh)
fi
cp -r "$WORK/libs/"* "$APP/libs/"
AAR="$APP/libs/libv2ray.aar"
if [ ! -f "$AAR.$LIBXRAY_TAG" ]; then
  curl -fsSL -o "$AAR" "https://github.com/2dust/AndroidLibXrayLite/releases/download/$LIBXRAY_TAG/libv2ray.aar"
  touch "$AAR.$LIBXRAY_TAG"
fi

AURORA_NDK_VERSION="$(basename "$NDK_HOME")" python3 "$HERE/customize.py" "$WORK"

KEYSTORE="${KEYSTORE:-$HERE/aurora.keystore}"
KEYSTORE_PASSWORD="${KEYSTORE_PASSWORD:-aurora-public}"
KEY_ALIAS="${KEY_ALIAS:-aurora}"
KEY_PASSWORD="${KEY_PASSWORD:-$KEYSTORE_PASSWORD}"

cd "$WORK/V2rayNG"
echo "sdk.dir=$ANDROID_HOME" > local.properties
chmod 755 gradlew
./gradlew -q --no-daemon assemblePlaystoreRelease \
  "-PABI_FILTERS=arm64-v8a;armeabi-v7a" \
  "-Pandroid.injected.signing.store.file=$KEYSTORE" \
  "-Pandroid.injected.signing.store.password=$KEYSTORE_PASSWORD" \
  "-Pandroid.injected.signing.key.alias=$KEY_ALIAS" \
  "-Pandroid.injected.signing.key.password=$KEY_PASSWORD"

mkdir -p "$OUT"
rm -f "$OUT"/*.apk
cp app/build/outputs/apk/playstore/release/AuroraVPN_*.apk "$OUT/"
ls -la "$OUT"
