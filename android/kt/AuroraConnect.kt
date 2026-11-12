package com.v2ray.ang.ui.main

// Главная панель Aurora VPN вверху экрана: кнопка подключения, статус, таймер, выбранная страна
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.v2ray.ang.handler.MmkvManager
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val AuroraGold = Color(0xFFE8C46A)
private val AuroraGoldLight = Color(0xFFF6E3B0)
private val AuroraGoldDeep = Color(0xFF8A6A1F)
private val AuroraInk = Color(0xFF070609)
private val AuroraRed = Color(0xFFE57373)
private const val KEY_STARTED_AT = "aurora_connected_since"
private const val PING_EVERY_MS = 15_000L

/** Срок, устройства и ссылка на бота из заголовков подписки (их отдаёт бот Aurora). */
private data class SubInfo(val expire: Long, val devices: String, val botUrl: String)

private fun subInfo(): SubInfo? {
    val usage = MmkvManager.decodeSubscriptions()
        .mapNotNull { it.subscription.usageInfo }
        .firstOrNull { it.expire > 0 || !it.supportUrl.isNullOrBlank() } ?: return null
    // Заголовок подписки: «Aurora VPN · 2 устройства»
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
    // Пока VPN включён, настоящая задержка через туннель меряется постоянно (раз в 15 секунд).
    LaunchedEffect(isRunning, selectedGuid) {
        if (!isRunning) return@LaunchedEffect
        delay(1500)
        while (true) {
            act(MainAction.TestCurrentServer)
            delay(PING_EVERY_MS)
        }
    }
    LaunchedEffect(status) {
        if (status is MainStatus.ConnectionTest) {
            livePing = if (status.result.delayMillis >= 0) status.result.delayMillis else -1L
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
                    text = if (parts.isEmpty()) "Подписка Aurora VPN" else "Подписка " + parts.joinToString(" · "),
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
                    else Brush.radialGradient(listOf(Color(0xFF2A262B), Color(0xFF121014)))
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
    ping < 400 -> AuroraGold
    else -> AuroraRed
}

private fun formatDuration(millis: Long): String {
    val s = (millis.coerceAtLeast(0L) / 1000)
    return "%02d:%02d:%02d".format(s / 3600, (s / 60) % 60, s % 60)
}

private fun formatDate(epochSeconds: Long): String =
    SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(Date(epochSeconds * 1000))
