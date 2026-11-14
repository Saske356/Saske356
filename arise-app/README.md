# Arise VPN — новое приложение (с нуля)

Своё Android-приложение без кода v2rayNG. Сейчас — тестовая версия: ставится рядом с текущим
приложением (`android/`, пакет `io.github.saske356.aurora`) и его не заменяет (пакет
`io.github.saske356.arise`).

- Интерфейс, логика, подписка, VPN-служба — свой код (Kotlin, Jetpack Compose), папка `app/src`.
- Ядро — Xray для Android: библиотека [AndroidLibXrayLite](https://github.com/2dust/AndroidLibXrayLite)
  (LGPL-3.0, подключается как отдельная библиотека). Версия — `LIBXRAY_TAG` в `android/UPSTREAM`.
- Туннель — встроенный вход `tun` ядра Xray (дескриптор VpnService передаётся в `startLoop`).
- Правила geoip/geosite — Loyalsoldier/v2ray-rules-dat, скачиваются при сборке.

Подписка та же, что у бота: приложение представляется `AriseApp/… (enc1) AuroraVPN/…`, сервер
отдаёт зашифрованные JSON-конфиги с турбо-режимом. Ссылка `arise://install-sub?url=…` добавляет
подписку одним касанием.

Сборка — только в GitHub Actions (`.github/workflows/arise-app.yml`): APK выкладывается
предварительной версией `arise-new-0.1.N` (бот такие не раздаёт).
