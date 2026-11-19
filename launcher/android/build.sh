#!/usr/bin/env bash
# Сборка APK лаунчера без Gradle: aapt2 → javac → d8 → zipalign → apksigner.
# Нужны JDK 17+ и Android SDK (platforms;android-34, build-tools;34.0.0).
#
#   ANDROID_HOME=/путь/к/sdk ./build.sh            # release-сборка, подпись ключом keystore/release.jks
#   DEBUG=1 ./build.sh                              # с отладкой WebView через chrome://inspect
set -euo pipefail

cd "$(dirname "$0")"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/opt/android-sdk}}"
API=34
BT="${BUILD_TOOLS:-$(ls -d "$SDK"/build-tools/*/ 2>/dev/null | sort -V | tail -1)}"; BT="${BT%/}"
JAR="$SDK/platforms/android-$API/android.jar"
[ -f "$JAR" ] || { echo "Нет $JAR — установите platforms;android-$API"; exit 1; }
[ -x "$BT/aapt2" ] || { echo "Нет $BT — установите build-tools (36.0.0 или новее)"; exit 1; }

VERSION=$(sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' AndroidManifest.xml)
OUT=build
rm -rf "$OUT"; mkdir -p "$OUT"/{res,gen,classes,dex}

echo "▸ 3D-сцена для фона лаунчера (из папки игры)"
GAME="${GAME_DIR:-../../game}"
SC=assets/launcher
mkdir -p "$SC/js" "$SC/shared" "$SC/vendor"
cp "$GAME/shared/world.js" "$SC/shared/"
cp "$GAME/public/js/city.js" "$GAME/public/js/models.js" "$GAME/public/js/traffic.js" "$SC/js/"
THREE_JS="$GAME/node_modules/three/build/three.module.js"
[ -f "$THREE_JS" ] || { echo "Нет $THREE_JS — выполните npm install в папке игры"; exit 1; }
cp "$THREE_JS" "$SC/vendor/"
ADDONS="$GAME/node_modules/three/examples/jsm"
mkdir -p "$SC/addons/loaders" "$SC/addons/utils"
cp "$ADDONS/loaders/GLTFLoader.js" "$SC/addons/loaders/"
cp "$ADDONS/utils/BufferGeometryUtils.js" "$SC/addons/utils/"

echo "▸ Игра для одиночного режима (assets/game)"
rm -rf assets/game && mkdir -p assets/game/vendor
cp -r "$GAME/public/." assets/game/
cp -r "$GAME/shared" assets/game/
cp "$THREE_JS" assets/game/vendor/
cp -r "$SC/addons" assets/game/
# модели машин (если сконвертированы в game/cache/cars) — для одиночной игры без интернета
if [ -f "$GAME/cache/cars/cars.json" ]; then mkdir -p assets/game/cache && cp -r "$GAME/cache/cars" assets/game/cache/; fi

echo "▸ Ресурсы"
"$BT/aapt2" compile --dir res -o "$OUT/res/res.zip"
"$BT/aapt2" link -I "$JAR" --manifest AndroidManifest.xml -A assets \
  --java "$OUT/gen" -o "$OUT/unsigned.apk" "$OUT/res/res.zip" --auto-add-overlay

echo "▸ Java"
DEBUG_FLAG=$([ "${DEBUG:-0}" = "1" ] && echo true || echo false)
mkdir -p "$OUT/gen/ru/oniks/rp"
cat > "$OUT/gen/ru/oniks/rp/BuildInfo.java" <<EOF
package ru.oniks.rp;
final class BuildInfo {
    static final String VERSION = "$VERSION";
    static final boolean DEBUG = $DEBUG_FLAG;
}
EOF
javac -nowarn -source 8 -target 8 -Xlint:-options -encoding UTF-8 -bootclasspath "$JAR:$BT/core-lambda-stubs.jar" -classpath "$JAR" \
  -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java') 2>&1 | grep -v "bootstrap class path" || true
[ -n "$(find "$OUT/classes" -name 'MainActivity.class')" ] || { echo "Ошибка компиляции"; exit 1; }

echo "▸ DEX"
"$BT/d8" --release --min-api 24 --lib "$JAR" --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')
(cd "$OUT/dex" && zip -q -j ../unsigned.apk classes.dex)

echo "▸ Подпись"
KS=keystore/release.jks
if [ ! -f "$KS" ]; then
  mkdir -p keystore
  PASS=$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')
  keytool -genkeypair -keystore "$KS" -alias novograd -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass "$PASS" -keypass "$PASS" -dname "CN=ONIKS RP" >/dev/null 2>&1
  echo "$PASS" > keystore/password.txt
  echo "  Создан ключ подписи $KS — сохраните его вместе с keystore/password.txt:"
  echo "  без этого ключа обновления не установятся поверх старой версии."
fi
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks "$KS" --ks-key-alias novograd --ks-pass "file:keystore/password.txt" \
  --out "$OUT/OniksRP-$VERSION.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify "$OUT/OniksRP-$VERSION.apk"
rm -f "$OUT/OniksRP-$VERSION.apk.idsig"
echo "✔ Готово: $(pwd)/$OUT/OniksRP-$VERSION.apk ($(du -h "$OUT/OniksRP-$VERSION.apk" | cut -f1))"
