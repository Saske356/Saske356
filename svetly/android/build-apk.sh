#!/usr/bin/env bash
# Builds app/build/outputs/apk/release/app-release.apk
# Needs: Android SDK (ANDROID_HOME), NDK (ANDROID_NDK_HOME), JDK 17+,
#        rustup target aarch64-linux-android, cargo install cargo-ndk
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ANDROID_HOME:?set ANDROID_HOME to your Android SDK}"
if [ -z "${ANDROID_NDK_HOME:-}" ]; then
  ANDROID_NDK_HOME="$(ls -d "$ANDROID_HOME"/ndk/* "$ANDROID_HOME"/android-ndk-* 2>/dev/null | sort -V | tail -1)"
  export ANDROID_NDK_HOME
fi
cargo ndk -t arm64-v8a -P 28 -o android/app/src/main/jniLibs build --release --lib
cd android
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew --no-daemon assembleRelease
echo "APK: $(pwd)/app/build/outputs/apk/release/app-release.apk"
