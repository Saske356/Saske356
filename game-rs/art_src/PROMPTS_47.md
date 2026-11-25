# Промты к версии 4.7 (ChatGPT)

Порядок: 1) первым сообщением — блок СТИЛЬ; 2) вторым — прикрепи `lumen_reference.png` (исходник облика Лазурь,
`game-rs/art_src/l_azure.webp`) и напиши: «Это главный герой Lumen. Все облики рисуй в ТОЧНО такой же позе, форме тела,
размере глаз и плавников — меняй только цвета и материал»; 3) дальше по одному промту.
Облики — НЕ плотнее и НЕ детальнее образца (плотные облики ты уже забраковал), полупрозрачные плавники как у образца.

## СТИЛЬ
```
You are drawing game sprites for a mobile deep-sea arcade "Light of the Abyss".
Style for EVERY image in this chat:
- polished hand-painted 2D game art, premium mobile game quality, rich painterly shading, clean readable silhouette;
- deep-sea bioluminescent creatures: glowing spots, translucent fins, glowing eyes;
- strong but harmonious colours, one main colour + one accent colour, no rainbow mess;
- strict side view, the creature faces RIGHT;
- one creature, centered, fills ~80% of a square 1024x1024 canvas, nothing cropped;
- TRANSPARENT background (PNG with alpha), no ground, no shadow, no frame, no text, no watermark;
- soft light from top-left, rim light on the right edge.
Reply only with the image.
```

## Облики для новых искр (1024×1024, прозрачный фон)
| Файл | Искра | Промт |
|---|---|---|
| `pl_crescent.png` | Бумеранг | `Same Lumen design and pose as the reference, golden moon theme: warm gold body, fins shaped like curved crescent blades, white-gold glowing core, small crescent mark on the forehead.` |
| `pl_scythe.png` | Коса | `Same Lumen design and pose as the reference, reaper theme: deep violet body, long sharp sickle-shaped tail fin glowing magenta at the edge, pale lilac core.` |
| `pl_mother.png` | Призыватель | `Same Lumen design and pose as the reference, nurturing sea-mother theme: soft teal-green body, flowing frilly fins with tiny glowing pearl-eggs along the fin edges, warm green core.` |
| `pl_miner.png` | Минёр | `Same Lumen design and pose as the reference, deep-sea mine theme: dark steel-blue body, small rounded spikes along the back fin like a sea mine, glowing orange-red core and orange fin tips.` |

## Награда за полный бестиарий
| `pl_keeper.png` | Хранитель глубин | `Same Lumen design and pose as the reference, keeper of the deep theme: midnight blue body covered with faint glowing silhouettes of tiny sea creatures, silver fin edges, soft white star-like core.` |

## Тайные комнаты
| Файл | Что | Промт |
|---|---|---|
| `portal.png` | Вход в тайную комнату (1024×1024) | `Draw: a magical underwater portal seen from above: a round ring of glowing seashells and coral, inside it a swirling vortex of golden light and tiny bubbles, bright center, soft glow around. Top-down view, transparent background.` |
| `ground_secret.png` | Дно комнаты (1024×1024, БЕЗ прозрачности) | `Seamless tileable top-down texture of a magical underwater treasure grotto floor: golden sand with scattered shells, pearls and faint glowing blue runes carved into flat stones, soft caustic light. Must tile seamlessly on all sides, no perspective, no objects cut by the edges, painterly game style.` |

Присылай пачкой — вырежу фон, нарежу плавники (Segment Anything), сделаю огненные/теневые не нужны (это облики).
