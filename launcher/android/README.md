# Лаунчер Новоград RP для Android

Приложение со списком серверов (онлайн, пинг), новостями сервера, вводом ника и пароля,
настройкой графики и кнопкой «Играть». Игра открывается на весь экран в альбомной ориентации,
вход выполняется автоматически. Кнопка «Назад» в игре спрашивает, выйти ли в лаунчер.

## Как это устроено

- `assets/launcher/` — интерфейс лаунчера (HTML/CSS/JS). Его можно открыть и в обычном браузере для проверки.
- `assets/launcher/config.js` — встроенный список серверов. **Впишите сюда адрес своего сервера перед сборкой.**
- `src/ru/novograd/rp/` — Java: `MainActivity` (лаунчер), `GameActivity` (игра), `Screen` (полноэкранный режим, WebView).
- Сервер игры отдаёт `GET /api/status` → `{ name, online, max, version, news }`.
  Новости правятся в `game/news.json`, имя и лимит — переменными `SERVER_NAME` и `MAX_PLAYERS`.

## Сборка

Нужны JDK 17+ и Android SDK с `platforms;android-34` и `build-tools;36.0.0` (или новее). Gradle не нужен.

```bash
cd launcher/android
ANDROID_HOME=/путь/к/android-sdk ./build.sh
# → build/NovogradRP-<версия>.apk
```

`DEBUG=1 ./build.sh` включает отладку WebView через `chrome://inspect`.

## Ключ подписи

При первой сборке создаётся `keystore/release.jks` и `keystore/password.txt` (в git не попадают).
**Храните их в надёжном месте**: обновление APK устанавливается поверх старого только с тем же ключом.
Чтобы собрать новую версию, положите файлы обратно в `keystore/` и увеличьте `versionCode`/`versionName`
в `AndroidManifest.xml`.

## Иконка

`python3 tools/make_icon.py` перерисовывает `res/mipmap-*/ic_launcher.png` (нужен Pillow).
Можно просто заменить PNG своими.
