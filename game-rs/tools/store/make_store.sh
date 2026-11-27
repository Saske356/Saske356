#!/usr/bin/env bash
# Материалы для RuStore с текущей версии игры: скриншоты 1080×1920, обложка 1920×1080, трейлер 720×1280.
# Запуск из game-rs:  tools/store/make_store.sh
# Нужно: cargo build (ПК-версия), Xvfb, ffmpeg, python3 + Pillow. Результат — в ../game/store/.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$(pwd); OUT=$ROOT/../game/store; TMP=$(mktemp -d); D=$TMP/save
mkdir -p "$D" "$OUT/screenshots" "$OUT/video"
cargo build -q
# витринное сохранение: открыт бестиарий, рекорд, немного жемчуга, обучение пройдено
python3 - "$D/save.json" <<'EOF'
import json, sys
foes = ['drifter','dart','jelly','urchin','spikelet','eel','squid','crab','mender','bomber','chest','boss1','boss2','boss3','boss4','crystal','ray','lantern','wisp','spawner','fry','kingcrab','queen']
s = {"best": 482350, "bestDepth": 2100, "pearls": 2415, "seenHow": 1, "seenIntro": 1, "tut": 1, "crabHint": 1, "runs": 40, "wins": 1,
     "foeSeen": {k: 1 for k in foes}, "seen": {k: 1 for k in foes}, "skin": "azure", "char": "lumen",
     "hints": dict({f"ab{i}": 1 for i in range(14)}, crystal=1)}
import datetime; t = datetime.date.today(); s["daily"] = {"day": "", "last": f"{t.year}-{t.month}-{t.day}", "streak": 1}  # без всплывашки «награда за вход»
json.dump(s, open(sys.argv[1], 'w'))
EOF
cp "$D/save.json" "$TMP/base.json"
(Xvfb :88 -screen 0 1200x2000x24 >/dev/null 2>&1 &) ; (Xvfb :89 -screen 0 540x960x24 >/dev/null 2>&1 &); sleep 2
run() { cp "$TMP/base.json" "$D/save.json"; (cd assets && DISPLAY=:88 LIBGL_ALWAYS_SOFTWARE=1 SVET_DPI=2.5 SVET_W=1080 SVET_H=1920 SVET_DATA=$D SVET_TEST="$1" timeout 150 ../target/debug/svet-desktop >/dev/null 2>&1 || true); }
S=$TMP/s
run "1:title;3.5:shot ${S}1.png;4:quit"
run "1:title;1.5:play;1.7:god;1.8:bot;2:zone 4;2.5:up multi 2;2.6:up orbit 3;2.7:up nova 2;2.8:up chain 2;3:elite 2;6:elite 6;6.5:spawn 2;6.6:spawn 6;6.7:spawn 9;7:spawn 16;16:shot ${S}2.png;16.5:quit"
run "1:title;1.2:char 11;1.5:play;1.7:god;2:zone 4;4:lvl;4.5:cards multi,hurricane,caliber;6.5:shot ${S}3.png;7:quit"
run "1:title;1.2:char 11;1.5:play;1.7:god;2:zone 4;3:spawn 2;3.1:spawn 0;3.2:spawn 1;3.3:spawn 6;4.5:elite 2;6:abil;6.6:shot ${S}4.png;7:quit"
run "1:title;1.5:play;1.7:god;2:zone 9;2.4:up multi 3;2.5:up chain 2;2.6:up orbit 3;3:spawn 14;5:shot ${S}5.png;5.5:quit"
run "1:title;1.5:play;1.7:god;2:zone 4;3:room;6:shot ${S}6.png;6.5:quit"
run "1:title;1.5:shop 1;3:shot ${S}7.png;3.5:quit"
run "1:title;1.5:shop 2;3:shot ${S}8.png;3.5:quit"
python3 "$ROOT/tools/store/compose.py" "$TMP" "$OUT"
# трейлер: запись экрана игры + музыка из игры + финальная заставка
cp "$TMP/base.json" "$D/save.json"
(cd assets && DISPLAY=:89 LIBGL_ALWAYS_SOFTWARE=1 SVET_DPI=1.25 SVET_W=540 SVET_H=960 SVET_DATA=$D SVET_TEST="2:title;3:char 11;3.4:play;3.5:god;3.6:bot;3.7:zone 2;3.8:spawn 2;3.85:spawn 0;3.9:spawn 1;3.95:spawn 6;4:spawn 2;4.1:spawn 3;4.2:spawn 5;4.3:up multi 2;4.4:up orbit 2;5:elite 2;6:spawn 7;6.1:spawn 17;7:spawn 0;7.1:spawn 2;8:xp 60;11:abil;13:spawn 7;13.1:spawn 17;13.2:spawn 18;15:elite 6;17:zone 9;17.4:spawn 14;19:spawn 2;19.1:spawn 6;22:abil;27:elite 2;28:abil;31:spawn 2;31.1:spawn 6;37:quit" timeout 60 ../target/debug/svet-desktop >/dev/null 2>&1 &)
sleep 1.5
ffmpeg -y -loglevel error -draw_mouse 0 -video_size 540x960 -framerate 30 -f x11grab -i :89+0,0 -t 34 -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p "$TMP/raw.mp4"
ffmpeg -y -loglevel error -ss 2.0 -i "$TMP/raw.mp4" -t 31 -vf "scale=720:1280:flags=lanczos,fade=t=in:st=0:d=0.6" -r 30 -c:v libx264 -crf 19 -pix_fmt yuv420p "$TMP/p1.mp4"
ffmpeg -y -loglevel error -loop 1 -i "$TMP/endcard.png" -t 3.5 -vf "fade=t=in:st=0:d=0.6,format=yuv420p" -r 30 -c:v libx264 -crf 19 "$TMP/p2.mp4"
printf "file %s\nfile %s\n" "$TMP/p1.mp4" "$TMP/p2.mp4" > "$TMP/l.txt"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$TMP/l.txt" -c copy "$TMP/v.mp4"
ffmpeg -y -loglevel error -i "$TMP/v.mp4" -i assets/audio/zone2.ogg -filter_complex "[1:a]atrim=0:34.5,afade=t=in:st=0:d=1,afade=t=out:st=32:d=2.5[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 160k -shortest "$OUT/video/trailer.mp4"
echo "готово: $OUT"
