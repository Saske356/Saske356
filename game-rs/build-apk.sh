#!/usr/bin/env bash
# Сборка APK «Свет Бездны» (Rust): ./build-apk.sh ПУТЬ_К_КЛЮЧУ ПАРОЛЬ [appId]
# Нужны: ANDROID_HOME (platforms/android-35, build-tools/35.0.0), ANDROID_NDK_HOME, cargo-ndk, gradle.
set -euo pipefail
cd "$(dirname "$0")"
KS="$1"; PASS="$2"; APPID="${3:-com.svetbezdny.game}"
cargo ndk -t arm64-v8a -t armeabi-v7a -P 24 -o android/app/src/main/jniLibs build --release --lib
BT="$ANDROID_HOME/build-tools/35.0.0"
( cd android && ${GRADLE:-gradle} assembleRelease -q -Pks="$KS" -PksPass="$PASS" -PappId="$APPID" )
OUT=dist/Svet-rust.apk; mkdir -p dist
"$BT/zipalign" -f -p 4 android/app/build/outputs/apk/release/app-release.apk /tmp/svet-aligned.apk
"$BT/apksigner" sign --min-sdk-version 21 --ks "$KS" --ks-pass pass:"$PASS" --key-pass pass:"$PASS" --ks-key-alias svetbezdny \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --out "$OUT" /tmp/svet-aligned.apk
"$BT/apksigner" verify --min-sdk-version 21 "$OUT" && ls -la "$OUT"
