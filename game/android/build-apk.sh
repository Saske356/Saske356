#!/usr/bin/env bash
# Собирает dist/SvetBezdny.apk без Gradle: aapt2 -> javac -> d8 -> zipalign -> apksigner.
#
# Нужно: JDK 17+, Android build-tools 35 и platform android-35.
#   ANDROID_BUILD_TOOLS=/путь/к/build-tools/35.0.0
#   ANDROID_JAR=/путь/к/platforms/android-35/android.jar
#   KEYSTORE=/путь/к/release.keystore (создастся, если нет)  KS_PASS=пароль
# Запуск из папки game/android:  bash build-apk.sh
set -euo pipefail
cd "$(dirname "$0")"

BT="${ANDROID_BUILD_TOOLS:?укажите ANDROID_BUILD_TOOLS}"
JAR="${ANDROID_JAR:?укажите ANDROID_JAR}"
KEYSTORE="${KEYSTORE:-$HOME/.svetbezdny.keystore}"
KS_PASS="${KS_PASS:-svetbezdny}"

OUT=build
rm -rf "$OUT" && mkdir -p "$OUT"/{res,gen,classes,dex,assets} ../dist

# Игра — тот же единый index.html
cp ../index.html "$OUT/assets/index.html"

# Иконка лаунчера из иконки PWA
cp ../icons/icon-512.png res/mipmap-xxxhdpi/ic_launcher.png

"$BT/aapt2" compile --dir res -o "$OUT/res/res.zip"
"$BT/aapt2" link -o "$OUT/unsigned.apk" -I "$JAR" \
  --manifest AndroidManifest.xml -A "$OUT/assets" \
  --java "$OUT/gen" "$OUT/res/res.zip" --auto-add-overlay

javac -source 17 -target 17 -encoding UTF-8 -classpath "$JAR" -d "$OUT/classes" \
  $(find src "$OUT/gen" -name '*.java')

"$BT/d8" --release --min-api 24 --lib "$JAR" --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')
(cd "$OUT/dex" && zip -q -u ../unsigned.apk classes.dex)

"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"

if [ ! -f "$KEYSTORE" ]; then
  keytool -genkeypair -keystore "$KEYSTORE" -alias svetbezdny -keyalg RSA -keysize 2048 \
    -validity 10000 -storepass "$KS_PASS" -keypass "$KS_PASS" \
    -dname "CN=Svet Bezdny, O=Indie, C=RU" >/dev/null
fi
"$BT/apksigner" sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" --ks-key-alias svetbezdny \
  --out ../dist/SvetBezdny.apk "$OUT/aligned.apk"
"$BT/apksigner" verify ../dist/SvetBezdny.apk

rm -rf "$OUT"
echo "Готово: game/dist/SvetBezdny.apk ($(du -h ../dist/SvetBezdny.apk | cut -f1))"
