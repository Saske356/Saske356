# Промты: Левиафан — полноценная длинная змея (boss4) и новые враги (4.5)

## Как будет работать Левиафан
Нужна **длинная ПРЯМАЯ змея** на одной картинке (голова справа, хвост слева, тело ровной горизонтальной полосой).
Игра нарежет её на полосы и изогнёт вдоль пути движения — тело будет извиваться волной, голова вести, хвост
догонять, как у настоящего морского змея. Поэтому: **никаких петель, колец и изгибов на самой картинке.**

В ChatGPT сначала вставь блок СТИЛЬ, потом промт. Формат — самый широкий, какой даёт ChatGPT (1536×1024),
прозрачный фон. Файл назови `leviathan.png`.

## СТИЛЬ (первым сообщением)
```
You are drawing game sprites for a mobile deep-sea arcade "Light of the Abyss".
Style for EVERY image in this chat:
- polished hand-painted 2D game art, premium mobile game quality, rich painterly shading, clean readable silhouette;
- deep-sea bioluminescent creatures: glowing spots, translucent fins, glowing eyes;
- strong but harmonious colours, one main colour + one accent colour, no rainbow mess;
- strict side view, the creature faces RIGHT;
- one creature, centered, nothing cropped;
- TRANSPARENT background (PNG with alpha), no ground, no shadow, no frame, no text, no watermark;
- soft light from top-left, rim light on the right edge;
- limbs, fins and tentacles clearly separated from the body (not overlapping it).
Reply only with the image.
```

## Левиафан (`leviathan.png`, 1536×1024)
```
Draw: a giant sea serpent-dragon boss "Leviathan", FULL BODY, perfectly STRAIGHT and HORIZONTAL,
like a long arrow lying flat: the head on the far right, the tail tip on the far left,
the body is one long straight band of the same thickness from neck to tail, gently tapering only near the tail.
Absolutely no loops, no coils, no S-curve, no bending — the body must be a straight horizontal line,
because the game will bend it itself. The creature fills the whole width of the wide canvas.
Head: big, menacing, dragon-like, mouth wide open with the lower jaw clearly separate and dropped down,
rows of long white fangs, dark red glowing throat inside, glowing toxic-green eyes, spiky crest on the head.
Body: dark teal-green scales, a row of glowing toxic-green spots along the side,
a translucent spiky dorsal fin running along the whole back (thin gap between fin and body),
two small translucent fins under the neck. Tail ends with a wide fan-shaped translucent tail fin.
```
Если всё равно рисует изогнутым — допиши:
`IMPORTANT: the body is a straight horizontal line like a ruler, the head and the tail are at the same height.`

---

## Новые враги (по одному промту на картинку, 1024×1024, смотрят ВПРАВО)
После СТИЛЯ — по одному. Имя файла = в первой колонке. У каждого придумана своя механика.

| Файл | Враг | Что делает в игре | Промт |
|---|---|---|---|
| `nautilus.png` | **Наутилус** | Катится по спирали, раз в несколько секунд выпускает спираль чернильных пуль. Раковина спереди держит 70% урона — бей сбоку и сзади | `Draw: a deep-sea nautilus enemy, big spiral shell with glowing amber stripes, a cluster of short tentacles and one big glowing eye peeking out on the right side, the shell is the main shape, ivory-white shell with orange glow lines, tentacles separated from the shell.` |
| `hermit.png` | **Рак-отшельник** | Прячется в раковину (неуязвим), когда ты близко; вылезает и стреляет залпом, когда отплываешь | `Draw: a deep-sea hermit crab enemy living in a spiky glowing conch shell, big claws and thin legs sticking out of the shell to the right, two eyes on stalks, purple-pink shell with glowing cyan spikes, claws and legs clearly separated from the shell.` |
| `seahorse.png` | **Конёк-снайпер** | Держится далеко, целится (видна тонкая линия 1 с) и стреляет быстрым лучом. Увернись рывком | `Draw: an armored deep-sea seahorse sniper enemy, long tube-like snout pointing right like a gun barrel with a glowing tip, curled tail, bony armor plates, a small translucent dorsal fin, dark blue body with glowing yellow-white spots, fin and tail separated from the body.` |
| `cuttle.png` | **Каракатица-хамелеон** | Становится почти невидимой и подкрадывается, перед атакой вспыхивает. Оставляет чернильные лужи, которые замедляют | `Draw: a deep-sea cuttlefish enemy with a wavy fin skirt around the body, eight short arms and two longer tentacles pointing right, W-shaped glowing pupils, skin with shimmering chromatophore patterns in teal and violet, fin skirt and arms clearly separated from the body.` |
| `puffer.png` | **Рыба-шар** | При попадании раздувается вдвое; раздутая при гибели выстреливает кольцо игл. Добивай быстро или держись подальше | `Draw: a deep-sea pufferfish enemy, round body covered with short spines, big worried glowing eyes, small fins and a small tail fin, the mouth is a small round "o", yellow-green body with glowing turquoise spots, fins separated from the body.` |
| `siphon.png` | **Сифонофора** | Длинная цепь-колония: плывёт змейкой, при уроне рвётся на 2–3 маленьких куска, которые расползаются | `Draw: a long deep-sea siphonophore colony enemy, a straight horizontal chain of glowing translucent bell-shaped segments connected by a thin glowing thread, head segment on the right is bigger with a small eye, delicate trailing tendrils below, cyan and soft pink glow, straight horizontal chain, no curves.` |
| `angler2.png` | **Малый удильщик** | Фонарь на удочке приманивает опыт к себе: пока он жив, рядом с ним осколки опыта летят к нему, а не к тебе | `Draw: a small deep-sea anglerfish enemy, big head with a wide mouth and needle teeth, a long thin lure rod on the head ending in a bright glowing bulb pointing forward-right, small body and tail fin, dark brown-black body with a glowing yellow lure, lure rod clearly separated.` |

Пришли картинки — вырежу фон, нарежу части (плавники, клешни, хвосты двигаются), пасти, придумаю атаки
как в таблице, добавлю в бестиарий и в зоны.
