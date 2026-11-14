package com.v2ray.ang.ui.main

// Главная панель Arise VPN вверху экрана: кнопка подключения, статус, таймер, выбранная страна
// с живым пингом, срок подписки, число устройств и кнопка «Продлить».
// Подменяет нижнюю полоску v2rayNG (MainBottomBar) — кладётся в сборку из android/kt/ скриптом customize.py.

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import com.v2ray.ang.AppConfig
import com.v2ray.ang.handler.MmkvManager
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val AuroraGold = Color(0xFF7AAEFF)       // холодный синий (имя от прежней золотой темы)
private val AuroraGoldLight = Color(0xFFD6E6FF)
private val AuroraGoldDeep = Color(0xFF2F5FC8)
private val AuroraInk = Color(0xFF03050B)
private val AuroraRed = Color(0xFFE57373)
private const val KEY_STARTED_AT = "aurora_connected_since"
private const val PING_EVERY_MS = 15_000L
private const val ALL_PING_EVERY_MS = 300_000L

/** Бот Arise VPN: подставляется при сборке из android/BOT (пусто — кнопки «в бота» скрыты). */
private const val AURORA_BOT = "%AURORA_BOT%"
private const val SWITCH_AFTER_FAILS = 2       // столько замеров подряд без связи — и переключаемся
private const val SWITCH_COOLDOWN_MS = 120_000L // не чаще раза в 2 минуты: если пропал весь интернет, не скачем

/** Российские приложения, которые не работают через зарубежный адрес: банки, Госуслуги,
 *  маркетплейсы, операторы. По умолчанию идут мимо VPN; переключатель в панели. Пакеты,
 *  которых нет на телефоне, Android просто пропускает. */
object AuroraRuApps {
    private const val KEY_DONE = "aurora_ru_apps_v1"
    val PACKAGES = setOf(
        "ru.sberbankmobile", "ru.sberbank.sberbankid", "com.idamob.tinkoff.android", "ru.tinkoff.investing",
        "ru.vtb24.mobilebanking.android", "ru.alfabank.mobile.android", "ru.alfabank.oavdo.amc",
        "ru.raiffeisennews", "ru.gazprombank.android.mobilebank.app", "ru.rosbank.android", "ru.psbank.online",
        "ru.mkb.mobile", "ru.sovcomcard.halva.v1", "ru.ozon.fintech.finance", "ru.pochta.bank", "ru.openbank.mobile",
        "ru.nspk.mirpay", "ru.nspk.sbpay", "ru.rostel", "ru.gosuslugi.goskey", "ru.fns.lkfl", "com.gnivts.selfemployed",
        "ru.mos.app", "ru.mos.polls", "ru.pfr.mobile", "ru.nalog.www",
        "com.wildberries.ru", "ru.ozon.app.android", "com.avito.android", "ru.yandex.taxi", "ru.yandex.market",
        "ru.yandex.yandexmaps", "ru.yandex.searchplugin", "ru.yandex.music", "ru.kinopoisk", "ru.vk.store",
        "com.vkontakte.android", "ru.ok.android", "ru.mail.mailapp", "ru.rutube.app", "ru.dublgis.dgismobile",
        "ru.mts.mymts", "ru.megafon.mlk", "ru.beeline.services", "ru.tele2.mytele2", "ru.yota.android",
        "ru.mts.money", "ru.rzd.pass", "ru.hh.android", "ru.foodfox.client", "ru.samokat.app", "ru.vprok",
    )

    fun enabled(): Boolean =
        MmkvManager.decodeSettingsBool(AppConfig.PREF_PER_APP_PROXY, false) &&
            MmkvManager.decodeSettingsBool(AppConfig.PREF_BYPASS_APPS, false) &&
            (MmkvManager.decodeSettingsStringSet(AppConfig.PREF_PER_APP_PROXY_SET)?.any { it in PACKAGES } == true)

    fun setEnabled(on: Boolean) {
        val set = MmkvManager.decodeSettingsStringSet(AppConfig.PREF_PER_APP_PROXY_SET)?.toMutableSet() ?: mutableSetOf()
        if (on) {
            set.addAll(PACKAGES)
            MmkvManager.encodeSettings(AppConfig.PREF_PER_APP_PROXY, true)
            MmkvManager.encodeSettings(AppConfig.PREF_BYPASS_APPS, true)
        } else {
            set.removeAll(PACKAGES)
            if (set.isEmpty()) MmkvManager.encodeSettings(AppConfig.PREF_PER_APP_PROXY, false)
        }
        MmkvManager.encodeSettings(AppConfig.PREF_PER_APP_PROXY_SET, set)
    }

    /** Один раз при первом запуске: включить, если человек сам не настраивал выбор приложений
     *  (свой список «только эти приложения через VPN» не трогаем). */
    fun applyDefaultsOnce() {
        if (MmkvManager.decodeSettingsBool(KEY_DONE, false)) return
        val perApp = MmkvManager.decodeSettingsBool(AppConfig.PREF_PER_APP_PROXY, false)
        val bypass = MmkvManager.decodeSettingsBool(AppConfig.PREF_BYPASS_APPS, false)
        val set = MmkvManager.decodeSettingsStringSet(AppConfig.PREF_PER_APP_PROXY_SET)
        if (!perApp || set.isNullOrEmpty() || bypass) setEnabled(true)
        MmkvManager.encodeSettings(KEY_DONE, true)
    }
}

/** Срок, устройства и ссылка на бота из заголовков подписки (их отдаёт бот Arise). */
private data class SubInfo(val expire: Long, val devices: String, val botUrl: String)

private fun subInfo(): SubInfo? {
    val usage = MmkvManager.decodeSubscriptions()
        .mapNotNull { it.subscription.usageInfo }
        .firstOrNull { it.expire > 0 || !it.supportUrl.isNullOrBlank() } ?: return null
    // Заголовок подписки: «Arise VPN · 2 устройства»
    val devices = usage.title?.substringAfter(" · ", "").orEmpty()
    return SubInfo(usage.expire, devices, usage.supportUrl.orEmpty())
}

@Composable
fun AuroraConnectPanel(
    displayText: String,
    isRunning: Boolean,
    selectedGuid: String?,
    status: MainStatus,
    onAction: (MainAction) -> Unit,
    modifier: Modifier = Modifier
) {
    var connecting by remember { mutableStateOf(false) }
    var startedAt by remember {
        mutableLongStateOf(MmkvManager.decodeSettingsLong(KEY_STARTED_AT, 0L))
    }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    // Живая задержка через туннель: 0 — ещё не мерили, -1 — замер не прошёл.
    var livePing by remember { mutableLongStateOf(0L) }
    val act by rememberUpdatedState(onAction)
    var fails by remember { mutableStateOf(0) }
    var lastSwitch by remember { mutableLongStateOf(0L) }
    var switchNote by remember { mutableStateOf("") }
    var ruApps by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        AuroraRuApps.applyDefaultsOnce()
        ruApps = AuroraRuApps.enabled()
    }
    LaunchedEffect(switchNote) {
        if (switchNote.isNotEmpty()) {
            delay(15_000)
            switchNote = ""
        }
    }

    // Время подключения хранится в настройках: таймер не сбрасывается, если закрыть и открыть приложение.
    LaunchedEffect(isRunning) {
        if (isRunning) {
            connecting = false
            if (startedAt == 0L) {
                startedAt = System.currentTimeMillis()
                MmkvManager.encodeSettings(KEY_STARTED_AT, startedAt)
            }
            while (true) {
                now = System.currentTimeMillis()
                delay(1000)
            }
        } else {
            startedAt = 0L
            livePing = 0L
            MmkvManager.encodeSettings(KEY_STARTED_AT, 0L)
        }
    }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    // Реальная задержка до всех стран меряется сама: при открытии приложения и раз в 5 минут,
    // пока оно на экране (в фоне не меряем — не тратим батарею и трафик).
    AuroraUpdate.vpnOn = isRunning
    LaunchedEffect(lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            delay(2500)
            AuroraUpdate.check()  // новая версия приложения (не чаще раза в 6 часов)
            while (true) {
                act(MainAction.TestRealAllServers)
                delay(ALL_PING_EVERY_MS)
            }
        }
    }
    // Пока VPN включён, настоящая задержка через туннель меряется постоянно (раз в 15 секунд).
    LaunchedEffect(isRunning, selectedGuid, lifecycle) {
        if (!isRunning) return@LaunchedEffect
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            delay(1500)
            while (true) {
                act(MainAction.TestCurrentServer)
                delay(PING_EVERY_MS)
            }
        }
    }
    LaunchedEffect(status) {
        if (status is MainStatus.ConnectionTest) {
            livePing = if (status.result.delayMillis >= 0) status.result.delayMillis else -1L
            fails = if (status.result.delayMillis >= 0) 0 else fails + 1
            // Связь пропала: переключаемся на страну с лучшим недавним пингом. «Лучший сервер»
            // сам выбирает живое подключение, его не трогаем.
            val current = selectedGuid
            val now = System.currentTimeMillis()
            val currentName = current?.let { MmkvManager.decodeServerConfig(it)?.remarks }.orEmpty()
            if (isRunning && fails >= SWITCH_AFTER_FAILS && now - lastSwitch > SWITCH_COOLDOWN_MS &&
                !currentName.startsWith("🚀")
            ) {
                val best = MmkvManager.decodeAllServerList()
                    .filter { it != current }
                    .mapNotNull { g ->
                        val d = MmkvManager.decodeServerAffiliationInfo(g)?.testDelayMillis ?: 0L
                        if (d > 0) g to d else null
                    }
                    .minByOrNull { it.second }
                if (best != null) {
                    lastSwitch = now
                    fails = 0
                    switchNote = "Связь пропала — переключено на «" +
                        (MmkvManager.decodeServerConfig(best.first)?.remarks ?: "другую страну") + "»"
                    act(MainAction.SelectServer(best.first))
                }
            }
        }
    }
    LaunchedEffect(connecting) {
        if (connecting) {
            delay(15000)
            connecting = false
        }
    }

    val serverName = remember(selectedGuid, displayText) {
        selectedGuid?.let { MmkvManager.decodeServerConfig(it)?.remarks }.orEmpty()
    }
    val storedPing = remember(selectedGuid, displayText) {
        selectedGuid?.let { MmkvManager.decodeServerAffiliationInfo(it)?.testDelayMillis } ?: 0L
    }
    val sub = remember(displayText, isRunning) { subInfo() }
    val ping = if (isRunning && livePing != 0L) livePing else storedPing

    val title = when {
        isRunning -> "Защищено"
        connecting -> "Подключение…"
        else -> "Не подключено"
    }
    val accent by animateColorAsState(
        targetValue = if (isRunning) AuroraGold else MaterialTheme.colorScheme.onSurfaceVariant,
        animationSpec = tween(600),
        label = "accent"
    )

    val empty = remember(displayText, isRunning) { MmkvManager.decodeAllServerList().isEmpty() }
    if (empty && !isRunning) {
        WelcomeCard(onAction = onAction, modifier = modifier)
        return
    }
    Column(
        modifier = modifier
            .widthIn(max = 560.dp)
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .shadow(10.dp, RoundedCornerShape(28.dp))
            .clip(RoundedCornerShape(28.dp))
            .background(
                Brush.verticalGradient(
                    listOf(MaterialTheme.colorScheme.surfaceContainerHigh, MaterialTheme.colorScheme.surfaceContainerLowest)
                )
            )
            .border(1.dp, AuroraGold.copy(alpha = if (isRunning) 0.45f else 0.18f), RoundedCornerShape(28.dp))
            .padding(start = 18.dp, end = 12.dp, top = 14.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        AuroraUpdateRow()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text(text = title, color = accent, fontWeight = FontWeight.Bold, fontSize = 22.sp)
                Text(
                    text = if (isRunning && startedAt > 0L) formatDuration(now - startedAt)
                    else "Нажмите кнопку, чтобы подключиться",
                    color = if (isRunning) AuroraGoldLight else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontFamily = if (isRunning) FontFamily.Monospace else FontFamily.Default,
                    fontSize = if (isRunning) 18.sp else 13.sp,
                    fontWeight = if (isRunning) FontWeight.SemiBold else FontWeight.Normal,
                )
                ServerChip(
                    name = serverName.ifBlank { "Выберите страну ниже" },
                    ping = ping,
                    live = isRunning && livePing != 0L,
                    onClick = { onAction(MainAction.TestCurrentServer) }
                )
            }
            PowerButton(
                isRunning = isRunning,
                connecting = connecting,
                onClick = {
                    if (!isRunning) connecting = true
                    onAction(MainAction.ToggleService)
                }
            )
        }
        if (switchNote.isNotEmpty()) {
            Text(text = switchNote, color = AuroraGold, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .clip(RoundedCornerShape(12.dp))
                .clickable {
                    AuroraRuApps.setEnabled(!ruApps)
                    ruApps = AuroraRuApps.enabled()
                    if (isRunning) onAction(MainAction.RestartService)  // настройка вступает в силу сразу
                }
                .padding(vertical = 2.dp)
        ) {
            Text(
                text = "🏦 Банки и Госуслуги мимо VPN",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                modifier = Modifier.weight(1f)
            )
            Text(
                text = if (ruApps) "вкл" else "выкл",
                color = if (ruApps) AuroraGold else MaterialTheme.colorScheme.onSurfaceVariant,
                fontWeight = FontWeight.SemiBold,
                fontSize = 13.sp,
            )
        }
        if (sub != null) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                val parts = buildList {
                    if (sub.expire > 0) add("до " + formatDate(sub.expire))
                    if (sub.devices.isNotBlank()) add(sub.devices)
                }
                Text(
                    text = if (parts.isEmpty()) "Подписка Arise VPN" else "Подписка " + parts.joinToString(" · "),
                    color = if (sub.expire in 1 until System.currentTimeMillis() / 1000) AuroraRed
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 13.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                if (sub.botUrl.isNotBlank()) {
                    Text(
                        text = "Продлить · устройства",
                        color = AuroraInk,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier
                            .clip(RoundedCornerShape(50))
                            .background(Brush.horizontalGradient(listOf(AuroraGoldLight, AuroraGold)))
                            .clickable {
                                val url = sub.botUrl.substringBefore("?") + "?start=renew"
                                onAction(MainAction.OpenSubscriptionLink(url))
                            }
                            .padding(horizontal = 12.dp, vertical = 7.dp)
                    )
                }
            }
        }
    }
}

/** «Новая версия X» в панели: обновиться внутри приложения или через браузер — на выбор. */
@Composable
private fun AuroraUpdateRow() {
    val ctx = LocalContext.current
    val u by AuroraUpdate.flow.collectAsState()
    if (u.version.isEmpty() && u.progress < 0f && u.note.isEmpty()) return
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(AuroraGold.copy(alpha = 0.14f))
            .border(1.dp, AuroraGold.copy(alpha = 0.45f), RoundedCornerShape(14.dp))
            .padding(horizontal = 12.dp, vertical = 9.dp)
    ) {
        Text(
            text = if (u.version.isNotEmpty()) "Новая версия ${u.version}" else "Обновление",
            color = AuroraGoldLight, fontWeight = FontWeight.SemiBold, fontSize = 14.sp
        )
        val sub = when {
            u.progress >= 0f -> "Скачиваю… ${(u.progress * 100).toInt()}%"
            u.note.isNotEmpty() -> u.note
            else -> "«Здесь» — быстрее, но Google Play может предупредить. Через браузер — без предупреждения."
        }
        Text(text = sub, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        if (u.version.isNotEmpty() && u.progress < 0f) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Box(modifier = Modifier.weight(1f)) { GoldButton(text = "Обновить здесь") { AuroraUpdate.installHere(ctx) } }
                Box(modifier = Modifier.weight(1f)) { GhostButton(text = "Через браузер") { AuroraUpdate.openInBrowser(ctx) } }
            }
        }
    }
    if (u.note.isNotEmpty() && u.version.isEmpty()) {
        LaunchedEffect(u.note) {
            delay(8_000)
            AuroraUpdate.onStatus("")
        }
    }
}

@Composable
private fun WelcomeCard(onAction: (MainAction) -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .widthIn(max = 560.dp)
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp)
            .shadow(10.dp, RoundedCornerShape(28.dp))
            .clip(RoundedCornerShape(28.dp))
            .background(
                Brush.verticalGradient(
                    listOf(MaterialTheme.colorScheme.surfaceContainerHigh, MaterialTheme.colorScheme.surfaceContainerLowest)
                )
            )
            .border(1.dp, AuroraGold.copy(alpha = 0.35f), RoundedCornerShape(28.dp))
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(text = "Добро пожаловать", color = AuroraGold, fontWeight = FontWeight.Bold, fontSize = 24.sp)
        Text(
            text = "Чтобы подключиться, нужна подписка из нашего Telegram-бота. Уже есть? В боте откройте " +
                "подписку и нажмите «⚡ Открыть в приложении» — всё добавится само.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 14.sp,
        )
        if (AURORA_BOT.isNotBlank() && !AURORA_BOT.startsWith("%")) {
            GoldButton("✦ Попробовать бесплатно") {
                onAction(MainAction.OpenSubscriptionLink("https://t.me/$AURORA_BOT?start=trial"))
            }
            GhostButton("Открыть бота") {
                onAction(MainAction.OpenSubscriptionLink("https://t.me/$AURORA_BOT"))
            }
        }
        GhostButton("📋 Вставить ссылку подписки") { onAction(MainAction.ImportClipboard) }
    }
}

@Composable
private fun GoldButton(text: String, onClick: () -> Unit) {
    Text(
        text = text,
        color = AuroraInk,
        fontWeight = FontWeight.Bold,
        fontSize = 15.sp,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(Brush.horizontalGradient(listOf(AuroraGoldLight, AuroraGold)))
            .clickable(onClick = onClick)
            .padding(vertical = 13.dp),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

@Composable
private fun GhostButton(text: String, onClick: () -> Unit) {
    Text(
        text = text,
        color = MaterialTheme.colorScheme.onSurface,
        fontWeight = FontWeight.SemiBold,
        fontSize = 15.sp,
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .border(1.dp, AuroraGold.copy(alpha = 0.35f), RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 13.dp),
        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
    )
}

@Composable
private fun PowerButton(isRunning: Boolean, connecting: Boolean, onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "halo")
    val pulse by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(if (connecting) 900 else 2200), RepeatMode.Restart),
        label = "pulse"
    )
    val ring = MaterialTheme.colorScheme.outlineVariant
    Box(
        modifier = Modifier
            .size(118.dp)
            .semantics { contentDescription = if (isRunning) "Отключить VPN" else "Подключить VPN" },
        contentAlignment = Alignment.Center
    ) {
        // Расходящиеся золотые волны: когда VPN включён — медленно, пока подключается — быстро.
        Canvas(Modifier.fillMaxSize()) {
            val base = size.minDimension / 2f * 0.70f
            if (isRunning || connecting) {
                for (i in 0..1) {
                    val t = (pulse + i * 0.5f) % 1f
                    drawCircle(
                        color = AuroraGold.copy(alpha = (1f - t) * 0.35f),
                        radius = base + (size.minDimension / 2f - base) * t,
                        style = Stroke(width = 2.5.dp.toPx())
                    )
                }
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(AuroraGold.copy(alpha = 0.28f), Color.Transparent),
                        center = center,
                        radius = size.minDimension / 2f
                    )
                )
            } else {
                drawCircle(color = ring, radius = base + 8.dp.toPx(), style = Stroke(width = 1.dp.toPx()))
            }
        }
        Box(
            modifier = Modifier
                .size(82.dp)
                .shadow(if (isRunning) 16.dp else 6.dp, CircleShape)
                .clip(CircleShape)
                .background(
                    if (isRunning) Brush.radialGradient(listOf(AuroraGoldLight, AuroraGold, AuroraGoldDeep))
                    else Brush.radialGradient(listOf(Color(0xFF1C2537), Color(0xFF0A0F1A)))
                )
                .border(2.dp, if (isRunning) AuroraGoldLight else AuroraGold.copy(alpha = 0.7f), CircleShape)
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            val icon = if (isRunning) AuroraInk else AuroraGold
            Canvas(Modifier.size(34.dp)) {
                val w = 4.dp.toPx()
                val r = size.minDimension / 2f - w
                drawArc(
                    color = icon,
                    startAngle = -60f,
                    sweepAngle = 300f,
                    useCenter = false,
                    topLeft = Offset(center.x - r, center.y - r),
                    size = Size(r * 2, r * 2),
                    style = Stroke(width = w, cap = StrokeCap.Round)
                )
                drawLine(
                    color = icon,
                    start = Offset(center.x, center.y - r - w / 2),
                    end = Offset(center.x, center.y - r * 0.15f),
                    strokeWidth = w,
                    cap = StrokeCap.Round
                )
            }
        }
    }
}

@Composable
private fun ServerChip(name: String, ping: Long, live: Boolean, onClick: () -> Unit) {
    // live: задержка измерена через туннель прямо сейчас (точка ярче), иначе — последний замер
    val dotAlpha = if (live) 1f else 0.6f
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(MaterialTheme.colorScheme.surfaceContainerHighest)
            .border(1.dp, AuroraGold.copy(alpha = 0.35f), RoundedCornerShape(50))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(
            text = name,
            color = MaterialTheme.colorScheme.onSurface,
            fontWeight = FontWeight.SemiBold,
            fontSize = 14.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 150.dp)
        )
        if (ping != 0L) {
            Box(
                Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(pingColor(ping).copy(alpha = dotAlpha))
            )
            Text(
                text = if (ping < 0) "нет связи" else "$ping мс",
                color = if (ping < 0) AuroraRed else MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                fontFamily = FontFamily.Monospace,
            )
        }
    }
}

private fun pingColor(ping: Long): Color = when {
    ping < 0 -> AuroraRed
    ping < 150 -> Color(0xFF6FD08C)
    ping < 400 -> Color(0xFFE8C46A)  // средний пинг — жёлтым, как светофор
    else -> AuroraRed
}

private fun formatDuration(millis: Long): String {
    val s = (millis.coerceAtLeast(0L) / 1000)
    return "%02d:%02d:%02d".format(s / 3600, (s / 60) % 60, s % 60)
}

private fun formatDate(epochSeconds: Long): String =
    SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(Date(epochSeconds * 1000))
