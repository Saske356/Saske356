"""Превращает исходники v2rayNG в Arise VPN: python3 customize.py <папка v2rayNG>.

Меняется только оформление и настройки по умолчанию, ядро и логика v2rayNG остаются как есть.
Каждая правка проверяет, что нужный кусок нашёлся: если v2rayNG поменяет код, сборка упадёт
сразу с понятной ошибкой, а не соберёт приложение с половиной правок.

v2rayNG распространяется по GPL-3.0, поэтому и эти правки, и сама сборка открыты в этом репозитории.
"""

import glob
import os
import re
import sys

import make_icon

# Пакет и схема ссылок остались от прежнего названия (Aurora): с ними новая версия ставится
# поверх уже установленной, а ссылки из бота продолжают открывать приложение.
APP_ID = "io.github.saske356.aurora"
APP_NAME = "Arise VPN"
SCHEME = "aurora"  # ссылка aurora://install-sub?url=... добавляет подписку одним касанием
REPO = "Saske356/Saske356"
# Проверка пинга: обычный HTTP без TLS — замер не включает лишнее рукопожатие TLS до Google,
# цифра ближе к реальной задержке до сервера, и замер быстрее.
DELAY_URL = "http://cp.cloudflare.com/generate_204"
DELAY_URL2 = "http://www.gstatic.com/generate_204"


def edit(path: str, pairs: list[tuple[str, str]], count_ok=lambda n: n >= 1) -> None:
    with open(path, encoding="utf-8") as f:
        s = f.read()
    for old, new in pairs:
        n = s.count(old) if not isinstance(old, re.Pattern) else len(old.findall(s))
        if not count_ok(n):
            sys.exit(f"customize: в {path} не найдено: {old!r}")
        s = old.sub(new, s) if isinstance(old, re.Pattern) else s.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(s)


def mask_servers(kt: str) -> None:
    """Адреса и пароли серверов из приложения не достать: убраны «Поделиться», QR-код, копирование,
    редактирование, «Экспорт всего» и резервная копия. Серверы приходят только из подписки бота,
    так что ключ нельзя переслать другу в обход подписки. Удаление и выбор сервера остались."""
    main = os.path.join(kt, "ui", "main")
    edit(os.path.join(main, "MainImportMenu.kt"), [
        ("    (includeManagementActions || action.isShareAction) && (!isComplexProfile || action.supportsComplexProfiles)\n",
         "    includeManagementActions && action == ServerMenuAction.Delete\n"),
        ("    items = MainMoreMenuAction.entries,\n",
         "    items = MainMoreMenuAction.entries.filter { it != MainMoreMenuAction.ExportAll },\n"),
    ], count_ok=lambda n: n == 1)
    edit(os.path.join(main, "MainServerPager.kt"), [
        (re.compile(r"\n *IconButton\(onClick = \{ actions\.(share|edit)\(row\.guid, row\.profile\) \}, Modifier\.size\(36\.dp\)\) \{"
                    r"\n(?: *.*\n){5} *\}"), ""),
    ], count_ok=lambda n: n == 2)
    edit(os.path.join(main, "MainDrawer.kt"), [
        ("    MainDestination.BackupRestore,\n", ""),
    ], count_ok=lambda n: n == 1)


# Фирменные цвета: чёрный и холодный синий. Имена GOLD* остались от прежней темы.
GOLD, GOLD_DARK, INK = "0xFF7AAEFF", "0xFF2F5FC8", "0xFF03050B"
DARK_SCHEME = f"""private val DarkColor = darkColorScheme(
    primary = Color({GOLD}),
    onPrimary = Color({INK}),
    primaryContainer = Color(0xFF13285A),
    onPrimaryContainer = Color(0xFFD6E4FF),
    secondary = Color({GOLD}),
    onSecondary = Color({INK}),
    secondaryContainer = Color(0xFF16233F),
    onSecondaryContainer = Color(0xFFD6E4FF),
    tertiary = Color(0xFF83D6B5),
    onTertiary = Color(0xFF00382E),
    tertiaryContainer = Color(0xFF005143),
    onTertiaryContainer = Color(0xFFA0F2D0),
    error = Color(0xFFFFB4AB),
    errorContainer = Color(0xFF93000A),
    onError = Color(0xFF690005),
    onErrorContainer = Color(0xFFFFDAD6),
    background = Color(0xFF05070D),
    onBackground = Color(0xFFE3ECFF),
    surface = Color(0xFF05070D),
    onSurface = Color(0xFFE3ECFF),
    surfaceVariant = Color(0xFF1A2233),
    onSurfaceVariant = Color(0xFFA9B6D2),
    outline = Color(0xFF6E7C99),
    outlineVariant = Color(0xFF263147),
    inverseSurface = Color(0xFFE3ECFF),
    inverseOnSurface = Color(0xFF05070D),
    inversePrimary = Color({GOLD_DARK}),
    scrim = Color(0xFF000000),
    surfaceTint = Color({GOLD}),
    surfaceContainerLowest = Color(0xFF03050B),
    surfaceContainerLow = Color(0xFF0A0F1A),
    surfaceContainer = Color(0xFF0F1522),
    surfaceContainerHigh = Color(0xFF151C2C),
    surfaceContainerHighest = Color(0xFF1C2537),
)"""


def brand_theme(kt: str) -> None:
    """Тёмная чёрно-синяя тема по умолчанию; цвета обоев Android (Material You) выключены,
    иначе приложение перекрашивалось бы под каждый телефон."""
    theme = os.path.join(kt, "ui", "compose", "Theme.kt")
    edit(theme, [
        (re.compile(r"private val DarkColor = darkColorScheme\((?:.|\n)*?\n\)"), DARK_SCHEME),
        ("    primary = Color(0xFF000000), // Black\n", f"    primary = Color({GOLD_DARK}),\n"),
        ("    secondary = Color(0xFFf97910), // Orange\n    onSecondary = Color(0xFFFFFFFF)",
         f"    secondary = Color({GOLD_DARK}),\n    onSecondary = Color(0xFFFFFFFF)"),
        ("val colorConfigType = Color(0xFFf97910)", f"val colorConfigType = Color({GOLD})"),
        ("val colorFabActive = Color(0xFFf97910)", f"val colorFabActive = Color({GOLD})"),
        ("decodeSettingsBool(AppConfig.PREF_DYNAMIC_COLOR, true)", "decodeSettingsBool(AppConfig.PREF_DYNAMIC_COLOR, false)"),
        ('decodeSettingsString(AppConfig.PREF_UI_MODE_NIGHT, "0") ?: "0"',
         'decodeSettingsString(AppConfig.PREF_UI_MODE_NIGHT, "2") ?: "2"'),
    ])
    edit(os.path.join(kt, "ui", "settings", "SettingsActivity.kt"), [
        ('rememberMmkvString(AppConfig.PREF_UI_MODE_NIGHT, "0")', 'rememberMmkvString(AppConfig.PREF_UI_MODE_NIGHT, "2")'),
    ], count_ok=lambda n: n == 1)
    edit(os.path.join(kt, "ui", "settings", "SettingsActivity.kt"), [
        ("rememberMmkvBool(AppConfig.PREF_DYNAMIC_COLOR, true)", "rememberMmkvBool(AppConfig.PREF_DYNAMIC_COLOR, false)"),
    ], count_ok=lambda n: n == 1)


# Тот же ключ, что в vpn-bot/client_config.py (SUB_SECRET): менять только вместе.
SUB_SECRET = "06c56043502cab251d01ad69c59ab1ea3885c20bd2590fca"
CRYPTO_KT = """package com.v2ray.ang.util

import android.util.Base64
import java.net.URI
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** Подписка Aurora VPN приходит зашифрованной: "aurora1:" + base64(nonce 12 байт + AES-256-GCM).
 *  Ключ — SHA-256(секрет + путь ссылки подписки). Всё остальное возвращается как есть. */
object AuroraCrypto {
    private const val PREFIX = "aurora1:"
    private const val SECRET = "%s"

    fun decode(url: String, body: String): String {
        val text = body.trim()
        if (!text.startsWith(PREFIX)) return body
        return try {
            val raw = Base64.decode(text.substring(PREFIX.length), Base64.DEFAULT)
            val path = URI(Utils.fixIllegalUrl(url)).rawPath.orEmpty()
            val key = MessageDigest.getInstance("SHA-256").digest((SECRET + path).toByteArray(Charsets.UTF_8))
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, raw, 0, 12))
            String(cipher.doFinal(raw, 12, raw.size - 12), Charsets.UTF_8)
        } catch (e: Exception) {
            LogUtil.e("AuroraCrypto", "Failed to decrypt subscription", e)
            ""
        }
    }
}
""" % SUB_SECRET


def encrypt_subscription(kt: str) -> None:
    """Бот отдаёт своему приложению подписку зашифрованной, приложение расшифровывает её перед разбором."""
    with open(os.path.join(kt, "util", "AuroraCrypto.kt"), "w", encoding="utf-8") as f:
        f.write(CRYPTO_KT)
    edit(os.path.join(kt, "handler", "AngConfigManager.kt"), [
        ("            val count = parseConfigViaSub(configText, it.guid, false)\n",
         "            configText = com.v2ray.ang.util.AuroraCrypto.decode(url, configText)\n"
         "            if (configText.isEmpty()) {\n"
         "                return SubscriptionUpdateResult(failureCount = 1)\n"
         "            }\n"
         "            val count = parseConfigViaSub(configText, it.guid, false)\n"),
    ], count_ok=lambda n: n == 1)


def connect_screen(kt: str) -> None:
    """Главный экран как у крупных VPN: большая золотая кнопка, статус, таймер, выбранная страна
    (android/kt/AuroraConnect.kt) вместо узкой полоски v2rayNG внизу; заголовок — название приложения."""
    main = os.path.join(kt, "ui", "main")
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "kt", "AuroraConnect.kt"), encoding="utf-8") as f:
        code = f.read()
    # Ник бота для приветствия («Попробовать бесплатно»): файл android/BOT или AURORA_BOT в сборке.
    bot = os.environ.get("AURORA_BOT", "")
    if not bot and os.path.exists(os.path.join(here, "BOT")):
        with open(os.path.join(here, "BOT"), encoding="utf-8") as f:
            bot = f.read().strip()
    bot = bot.lstrip("@")
    if bot and not re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot):
        sys.exit(f"customize: странный ник бота в android/BOT: {bot!r}")
    code = code.replace("%AURORA_BOT%", bot)
    with open(os.path.join(main, "AuroraConnect.kt"), "w", encoding="utf-8") as f:
        f.write(code)
    # Панель вверху, под заголовком (снизу по центру неудобно): список стран начинается под ней.
    edit(os.path.join(main, "MainScreen.kt"), [
        ("""            MainBottomBar(
                displayText = displayText,
                isRunning = isRunning,
                isDarkTheme = isDarkTheme,
                onAction = onAction,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
""", """            AuroraConnectPanel(
                displayText = displayText,
                isRunning = isRunning,
                selectedGuid = selectedGuid,
                status = uiState.status,
                onAction = onAction,
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = innerPadding.calculateTopPadding())
"""),
        ("                            top = innerPadding.calculateTopPadding(),\n",
         "                            top = innerPadding.calculateTopPadding() + bottomBarHeight,\n"),
        ("                                bottom = bottomBarHeight + 8.dp\n", "                                bottom = 32.dp\n"),
    ], count_ok=lambda n: n == 1)
    edit(os.path.join(main, "MainTopBar.kt"), [
        ("        title = stringResource(R.string.title_server),\n", f'        title = "{APP_NAME}",\n'),
    ], count_ok=lambda n: n == 1)


def auto_update_subscription(kt: str) -> None:
    """Подписка обновляется сама раз в час (в v2rayNG по умолчанию выключено): гость всегда
    получает свежие страны, мосты и сайт маскировки, даже если месяц не открывал приложение.
    Уже добавленным подпискам автообновление включается при запуске приложения."""
    edit(os.path.join(kt, "handler", "AngConfigManager.kt"), [
        ("        subItem.url = url\n        MmkvManager.encodeSubscription(\"\", subItem)\n",
         "        subItem.url = url\n        subItem.autoUpdate = true\n        subItem.updateInterval = 60\n"
         "        MmkvManager.encodeSubscription(\"\", subItem)\n        SubscriptionUpdater.sync()\n"),
    ], count_ok=lambda n: n == 1)
    edit(os.path.join(kt, "ui", "main", "MainRepository.kt"), [
        ("    override fun syncSubscriptions() {\n        SubscriptionUpdater.sync(app)\n",
         "    override fun syncSubscriptions() {\n"
         "        MmkvManager.decodeSubscriptions().forEach {\n"
         "            if (it.subscription.url.isNotEmpty() &&\n"
         "                (!it.subscription.autoUpdate || it.subscription.updateInterval > 60)) {\n"
         "                it.subscription.autoUpdate = true\n"
         "                it.subscription.updateInterval = 60\n"
         "                MmkvManager.encodeSubscription(it.guid, it.subscription)\n"
         "            }\n"
         "        }\n"
         "        SubscriptionUpdater.sync(app)\n"),
    ], count_ok=lambda n: n == 1)


def main(root: str) -> None:
    app = os.path.join(root, "V2rayNG", "app")
    src = os.path.join(app, "src", "main")
    kt = os.path.join(src, "java", "com", "v2ray", "ang")
    code = os.environ.get("AURORA_VERSION_CODE", "1")
    name = os.environ.get("AURORA_VERSION_NAME", "1.0." + code)

    # Своё имя пакета: ставится рядом с обычным v2rayNG и не путается с ним. Пространство имён
    # в коде (com.v2ray.ang) не трогаем — на него завязаны JNI-библиотеки туннеля.
    ndk = os.environ.get("AURORA_NDK_VERSION", "")
    edit(os.path.join(app, "build.gradle.kts"), [
        ('applicationId = "com.v2ray.ang"', f'applicationId = "{APP_ID}"'),
        (re.compile(r"versionCode = \d+"), f"versionCode = {code}"),
        (re.compile(r'versionName = "[^"]*"'), f'versionName = "{name}"'),
        ('"v2rayNG_${variant.versionName}', '"AriseVPN_${variant.versionName}'),
        ("compileSdk = ", (f'ndkVersion = "{ndk}"\n    ' if ndk else "") + "compileSdk = "),
    ])

    for p in glob.glob(os.path.join(src, "res", "values*", "strings.xml")):
        edit(p, [("v2rayNG", APP_NAME)], count_ok=lambda n: True)
    # Раздел подписок в русском переводе назывался «Группы» — гости не находили, где удалить подписку.
    edit(os.path.join(src, "res", "values-ru", "strings.xml"), [
        ('<string name="title_sub_setting">Группы</string>', '<string name="title_sub_setting">Подписки</string>'),
    ], count_ok=lambda n: n == 1)
    edit(os.path.join(src, "res", "values", "strings.xml"), [(f">{APP_NAME}<", f">{APP_NAME}<")])

    edit(os.path.join(src, "AndroidManifest.xml"), [
        ('<data android:scheme="v2rayng" />', f'<data android:scheme="{SCHEME}" />'),
    ])

    edit(os.path.join(kt, "AppConfig.kt"), [
        ('"$GITHUB_URL/2dust/v2rayNG"', f'"$GITHUB_URL/{REPO}"'),
        ('"https://api.github.com/repos/2dust/v2rayNG/releases"', f'"https://api.github.com/repos/{REPO}/releases"'),
        ('DELAY_TEST_URL = "https://www.gstatic.com/generate_204"', f'DELAY_TEST_URL = "{DELAY_URL}"'),
        ('DELAY_TEST_URL2 = "https://www.google.com/generate_204"', f'DELAY_TEST_URL2 = "{DELAY_URL2}"'),
        # «Лучший сервер» в приложении перепроверяет пинг раз в минуту, а не раз в 3 минуты
        ('OBSERVATORY_LEAST_PING_INTERVAL = "3m"', 'OBSERVATORY_LEAST_PING_INTERVAL = "1m"'),
    ])

    # Рекламный пункт меню v2rayNG ведёт на чужой сайт — убираем.
    edit(os.path.join(kt, "ui", "main", "MainDrawer.kt"), [
        ("    MainDestination.Promotion,\n", ""),
    ])

    # Бот узнаёт своё приложение по User-Agent и отдаёт ему конфиги с настройками под скорость.
    # «v2rayNG» в строке остаётся: по нему бот понимает, что приложение умеет JSON-конфиги.
    edit(os.path.join(kt, "util", "HttpUtil.kt"), [
        # «(enc1)» — приложение умеет расшифровывать подписку (encrypt_subscription ниже)
        ('"v2rayNG/${BuildConfig.VERSION_NAME}"',
         '"AuroraVPN/${BuildConfig.VERSION_NAME} (enc1) v2rayNG/${BuildConfig.VERSION_NAME}"'),
    ])

    # Импорт подписки по ссылке aurora://install-sub:
    # - повторный импорт той же подписки v2rayNG считает ошибкой («невозможно импортировать»),
    #   хотя подписка уже на месте, — считаем успехом (дальше она всё равно обновится);
    # - v2rayNG принимает подписку только по https:// (или http:// на локальный адрес), а бот без
    #   своего домена раздаёт её по http:// — разрешаем и его.
    edit(os.path.join(kt, "handler", "AngConfigManager.kt"), [
        ("            if (it.subscription.url == url) {\n                return 0\n",
         "            if (it.subscription.url == url) {\n                return 1\n"),
    ], count_ok=lambda n: n == 1)
    edit(os.path.join(kt, "util", "Utils.kt"), [
        ("if (URLUtil.isHttpsUrl(value)) return true",
         "if (URLUtil.isHttpsUrl(value) || URLUtil.isHttpUrl(value)) return true"),
    ], count_ok=lambda n: n == 1)

    mask_servers(kt)
    encrypt_subscription(kt)
    brand_theme(kt)
    connect_screen(kt)
    auto_update_subscription(kt)

    # По умолчанию: после обновления подписки сразу замерить пинг и поставить быстрые сверху.
    for key in ("PREF_AUTO_TEST_AFTER_UPDATE_SUBSCRIPTION", "PREF_AUTO_SORT_AFTER_TEST"):
        pat = re.compile(r"((?:decodeSettingsBool|rememberMmkvBool)\(AppConfig\." + key + r", )false\)")
        files = [p for p in glob.glob(os.path.join(kt, "**", "*.kt"), recursive=True)
                 if pat.search(open(p, encoding="utf-8").read())]
        if not files:
            sys.exit(f"customize: не найдена настройка {key}")
        for p in files:
            edit(p, [(pat, r"\1true)")])

    make_icon.main(os.path.join(src, "res"))
    print(f"customize: {APP_NAME} {name} ({code}), пакет {APP_ID}")


if __name__ == "__main__":
    main(sys.argv[1])
