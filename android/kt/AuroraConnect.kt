package com.v2ray.ang.ui.main

// Главный экран Aurora VPN: большая кнопка подключения, статус, таймер и выбранная страна.
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
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.v2ray.ang.handler.MmkvManager
import kotlinx.coroutines.delay

private val AuroraGold = Color(0xFFE8C46A)
private val AuroraGoldLight = Color(0xFFF6E3B0)
private val AuroraGoldDeep = Color(0xFF8A6A1F)
private val AuroraInk = Color(0xFF070609)
private const val KEY_STARTED_AT = "aurora_connected_since"

@Composable
fun AuroraConnectPanel(
    displayText: String,
    isRunning: Boolean,
    selectedGuid: String?,
    onAction: (MainAction) -> Unit,
    modifier: Modifier = Modifier
) {
    var connecting by remember { mutableStateOf(false) }
    var startedAt by remember {
        mutableLongStateOf(MmkvManager.decodeSettingsLong(KEY_STARTED_AT, 0L))
    }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }

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
            MmkvManager.encodeSettings(KEY_STARTED_AT, 0L)
        }
    }
    LaunchedEffect(connecting) {
        if (connecting) {
            delay(15000)
            connecting = false
        }
    }

    // Название и пинг выбранной страны; перечитываются, когда меняется выбор или приходит замер.
    val serverName = remember(selectedGuid, displayText) {
        selectedGuid?.let { MmkvManager.decodeServerConfig(it)?.remarks }.orEmpty()
    }
    val ping = remember(selectedGuid, displayText) {
        selectedGuid?.let { MmkvManager.decodeServerAffiliationInfo(it)?.testDelayMillis } ?: 0L
    }

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

    Box(
        modifier = modifier
            .widthIn(max = 520.dp)
            .fillMaxWidth()
            .shadow(16.dp, RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp))
            .clip(RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp))
            .background(
                Brush.verticalGradient(
                    listOf(MaterialTheme.colorScheme.surfaceContainerHigh, MaterialTheme.colorScheme.surfaceContainerLowest)
                )
            )
            .windowInsetsPadding(WindowInsets.navigationBars)
            .padding(start = 20.dp, end = 20.dp, top = 18.dp, bottom = 16.dp)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Text(
                text = title,
                color = accent,
                fontWeight = FontWeight.Bold,
                fontSize = 22.sp,
            )
            PowerButton(
                isRunning = isRunning,
                connecting = connecting,
                onClick = {
                    if (!isRunning) connecting = true
                    onAction(MainAction.ToggleService)
                }
            )
            Text(
                text = if (isRunning && startedAt > 0L) formatDuration(now - startedAt)
                else "Нажмите, чтобы подключиться",
                color = if (isRunning) AuroraGoldLight else MaterialTheme.colorScheme.onSurfaceVariant,
                fontFamily = if (isRunning) FontFamily.Monospace else FontFamily.Default,
                fontSize = if (isRunning) 20.sp else 14.sp,
                fontWeight = if (isRunning) FontWeight.SemiBold else FontWeight.Normal,
            )
            ServerChip(
                name = serverName.ifBlank { "Выберите страну в списке" },
                ping = ping,
                onClick = { onAction(MainAction.TestCurrentServer) }
            )
            Text(
                text = displayText.replace('\n', ' '),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onAction(MainAction.TestCurrentServer) }
            )
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
            .size(168.dp)
            .semantics { contentDescription = if (isRunning) "Отключить VPN" else "Подключить VPN" },
        contentAlignment = Alignment.Center
    ) {
        // Расходящиеся золотые волны: когда VPN включён — медленно, пока подключается — быстро.
        Canvas(Modifier.fillMaxSize()) {
            val base = size.minDimension / 2f * 0.66f
            if (isRunning || connecting) {
                for (i in 0..1) {
                    val t = (pulse + i * 0.5f) % 1f
                    drawCircle(
                        color = AuroraGold.copy(alpha = (1f - t) * 0.35f),
                        radius = base + (size.minDimension / 2f - base) * t,
                        style = Stroke(width = 3.dp.toPx())
                    )
                }
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(AuroraGold.copy(alpha = 0.30f), Color.Transparent),
                        center = center,
                        radius = size.minDimension / 2f
                    )
                )
            } else {
                drawCircle(color = ring, radius = base + 10.dp.toPx(), style = Stroke(width = 1.dp.toPx()))
            }
        }
        Box(
            modifier = Modifier
                .size(112.dp)
                .shadow(if (isRunning) 18.dp else 6.dp, CircleShape)
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
            Canvas(Modifier.size(44.dp)) {
                val w = 4.5.dp.toPx()
                val r = size.minDimension / 2f - w
                drawArc(
                    color = icon,
                    startAngle = -60f,
                    sweepAngle = 300f,
                    useCenter = false,
                    topLeft = Offset(center.x - r, center.y - r),
                    size = androidx.compose.ui.geometry.Size(r * 2, r * 2),
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
private fun ServerChip(name: String, ping: Long, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(MaterialTheme.colorScheme.surfaceContainerHighest)
            .border(1.dp, AuroraGold.copy(alpha = 0.35f), RoundedCornerShape(50))
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text(
            text = name,
            color = MaterialTheme.colorScheme.onSurface,
            fontWeight = FontWeight.SemiBold,
            fontSize = 15.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 220.dp)
        )
        if (ping > 0L) {
            Box(
                Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(pingColor(ping))
            )
            Text(
                text = "$ping мс",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
            )
        }
    }
    Spacer(Modifier.height(2.dp))
}

private fun pingColor(ping: Long): Color = when {
    ping < 150 -> Color(0xFF6FD08C)
    ping < 400 -> AuroraGold
    else -> Color(0xFFE57373)
}

private fun formatDuration(millis: Long): String {
    val s = (millis.coerceAtLeast(0L) / 1000)
    return "%02d:%02d:%02d".format(s / 3600, (s / 60) % 60, s % 60)
}
