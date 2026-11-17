package io.github.saske356.arise

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

// Главный экран в новом стиле (образец — design/gpt/01-home.png).

@Composable
internal fun HomeScreen(
    vpn: VpnUi, data: Data, onToggle: () -> Unit, onOpen: (String) -> Unit, openSheet: () -> Unit,
    openModes: () -> Unit, onMode: (Mode) -> Unit, openTools: () -> Unit, onRuApps: () -> Unit, openChat: () -> Unit,
) {
    val running = vpn.status == Status.RUNNING
    val connecting = vpn.status == Status.CONNECTING
    Column(
        Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .navigationBarsPadding()
            .padding(bottom = 24.dp)
    ) {
        HomeTop(openTools, openChat)
        UpdateCard()
        NotifyCard()
        HomeSub(data, onOpen)
        HomeHero(running, connecting, onToggle)
        HomeStatus(vpn)
        if (vpn.note.isNotEmpty()) {
            Text(vpn.note, color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 6.dp))
            LaunchedEffect(vpn.note) {
                delay(15_000)
                VpnState.update { it.copy(note = "") }
            }
        }
        for (err in listOf(vpn.error, data.error).filter { it.isNotEmpty() }) {
            Text(err, color = Red, fontSize = 13.sp, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 4.dp))
        }
        HomeCountry(vpn, data, openSheet)
        HomeTiles(vpn, data)
        if (running) HomeGraph(vpn)
        HomeModes(data.mode, onMode, openModes)
        if (!running) {
            ToggleRow("🏦", "Банки и Госуслуги мимо VPN", data.ruApps, Modifier.padding(horizontal = 22.dp, vertical = 6.dp)) { onRuApps() }
        }
    }
}

@Composable
private fun HomeTop(openTools: () -> Unit, openChat: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        // Чат всегда скрыт: открывается только долгим нажатием на знак
        Box(Modifier.pointerInput(Unit) { detectTapGestures(onLongPress = { openChat() }) }) { AriseMark(40.dp) }
        Spacer(Modifier.width(12.dp))
        Text("Arise", color = TextMain, fontSize = 26.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        Box(
            Modifier.size(46.dp).clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0x40223A6E), Color(0x1A0E1A36))))
                .border(1.dp, Color(0x3A5B8CFF), CircleShape)
                .clickable(onClick = openTools),
            contentAlignment = Alignment.Center
        ) { LineIcon(Ico.GEAR, 22.dp, BlueLight) }
    }
}

@Composable
private fun HomeSub(data: Data, onOpen: (String) -> Unit) {
    val devices = data.title.substringAfter(" · ", "")
    val expired = data.expire in 1 until System.currentTimeMillis() / 1000
    Row(
        Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 14.dp).glass(20.dp)
            .padding(start = 14.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        LineIcon(Ico.CROWN, 24.dp)
        Spacer(Modifier.width(10.dp))
        Text(
            when {
                expired -> "Подписка закончилась"
                data.expire > 0 -> "Подписка до " + date(data.expire, "dd.MM") + (if (devices.isNotBlank()) " · $devices" else "")
                else -> "Подписка Arise VPN"
            },
            color = if (expired) Red else TextSoft, fontSize = 13.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        Text(
            "Продлить", color = Color.White, fontSize = 13.5.sp, fontWeight = FontWeight.Bold,
            modifier = Modifier
                .clip(RoundedCornerShape(50))
                .background(Brush.verticalGradient(listOf(Color(0xFF3D7BFF), Color(0xFF1F4FD6))))
                .border(1.dp, Color(0x997AAEFF), RoundedCornerShape(50))
                .clickable { onOpen(botLink(data.botUrl, "renew")) }
                .padding(horizontal = 16.dp, vertical = 9.dp)
        )
    }
}

/** Глобус и кнопка включения со светящимися кольцами. */
@Composable
private fun HomeHero(running: Boolean, connecting: Boolean, onToggle: () -> Unit) {
    val haptic = LocalHapticFeedback.current
    val t = rememberInfiniteTransition(label = "hero")
    val pulse by t.animateFloat(
        0f, 1f, infiniteRepeatable(tween(if (connecting) 1100 else 2600, easing = LinearEasing), RepeatMode.Restart),
        label = "pulse"
    )
    val glow by animateFloatAsState(if (running) 1f else if (connecting) 0.7f else 0.35f, tween(700), label = "glow")
    // пока подключаемся — по кольцу бежит светящаяся дуга
    val spin by t.animateFloat(0f, 360f, infiniteRepeatable(tween(1100, easing = LinearEasing)), label = "spin")
    // подключились — вспышка расходится от кнопки
    val flash = remember { androidx.compose.animation.core.Animatable(0f) }
    LaunchedEffect(running) {
        if (running) {
            flash.snapTo(1f)
            flash.animateTo(0f, tween(900))
        }
    }
    val press = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
    val pressed by press.collectIsPressedAsState()
    val btnScale by animateFloatAsState(if (pressed) 0.93f else 1f,
        androidx.compose.animation.core.spring(dampingRatio = 0.5f, stiffness = 600f), label = "btn")
    BoxWithConstraints(
        Modifier.fillMaxWidth().height(330.dp)
            .semantics { contentDescription = if (running) "Отключить VPN" else "Подключить VPN" },
        contentAlignment = Alignment.Center
    ) {
        // глобус крупнее экрана: края уходят за поля, как на образце
        Globe(Modifier.requiredSize(maxWidth * 1.08f), on = running)
        Canvas(Modifier.size(250.dp)) {
            val r = size.minDimension / 2f
            drawCircle(
                Brush.radialGradient(listOf(Color(0xFF2F6BFF).copy(alpha = 0.45f * glow), Color.Transparent), center, r),
                radius = r
            )
            if (running || connecting) {
                for (i in 0..2) {
                    val k = (pulse + i / 3f) % 1f
                    drawCircle(Color(0xFF8CB8FF).copy(alpha = (1f - k) * 0.35f), radius = r * 0.62f + r * 0.38f * k,
                        style = Stroke(1.5.dp.toPx()))
                }
            }
            // светящееся кольцо вокруг кнопки
            for (i in 0..4) {
                drawCircle(Color(0xFF4A8BFF).copy(alpha = (0.5f - i * 0.1f) * glow), radius = r * 0.66f + i * 3.dp.toPx(),
                    style = Stroke(3.dp.toPx()))
            }
            drawCircle(Color(0xFFCFE0FF).copy(alpha = 0.35f + 0.65f * glow), radius = r * 0.66f, style = Stroke(2.5.dp.toPx()))
            if (connecting) {
                val d = r * 0.66f
                drawArc(
                    Brush.sweepGradient(listOf(Color.Transparent, Color(0xFFCFE0FF), Color.Transparent)),
                    spin, 110f, false, Offset(center.x - d, center.y - d), androidx.compose.ui.geometry.Size(d * 2, d * 2),
                    style = Stroke(5.dp.toPx(), cap = StrokeCap.Round)
                )
            }
            if (flash.value > 0f) {
                drawCircle(Color(0xFFCFE0FF).copy(alpha = 0.6f * flash.value), radius = r * (0.66f + 0.5f * (1f - flash.value)),
                    style = Stroke(4.dp.toPx()))
            }
        }
        Box(
            Modifier
                .size(150.dp)
                .graphicsLayer { scaleX = btnScale; scaleY = btnScale }
                .shadow(if (running) 28.dp else 12.dp, CircleShape, ambientColor = BlueMid, spotColor = BlueMid)
                .clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0xFF14254A), Color(0xFF070D1E))))
                .border(1.dp, Color(0x557AAEFF), CircleShape)
                .clickable(interactionSource = press, indication = null) {
                    haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    onToggle()
                },
            contentAlignment = Alignment.Center
        ) {
            PowerIcon(if (running) BlueLight else Blue.copy(alpha = 0.85f), 58.dp)
        }
    }
}

@Composable
private fun HomeStatus(vpn: VpnUi) {
    val running = vpn.status == Status.RUNNING
    val connecting = vpn.status == Status.CONNECTING
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(running) {
        while (running) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    val title by animateColorAsState(if (running) TextMain else TextSoft, tween(600), label = "title")
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        androidx.compose.animation.AnimatedContent(
            targetState = when {
                running -> "Защищено"
                connecting -> "Подключаемся…"
                else -> "Не защищено"
            },
            transitionSpec = {
                (androidx.compose.animation.fadeIn(tween(350)) + androidx.compose.animation.slideInVertically(tween(350)) { it / 3 }) togetherWith
                    (androidx.compose.animation.fadeOut(tween(200)) + androidx.compose.animation.slideOutVertically(tween(250)) { -it / 3 })
            },
            label = "status"
        ) { text -> Text(text, color = title, fontSize = 30.sp, fontWeight = FontWeight.Bold) }
        val started = Store.startedAt
        if (running && started > 0L) {
            Text(duration(now - started), color = Blue, fontSize = 30.sp, fontWeight = FontWeight.SemiBold,
                fontFamily = FontFamily.Monospace, letterSpacing = 1.sp)
        } else {
            Text(if (connecting) "· · ·" else "Нажмите кнопку, чтобы подключиться", color = TextDim, fontSize = 14.sp,
                modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun HomeCountry(vpn: VpnUi, data: Data, openSheet: () -> Unit) {
    val (flag, title) = splitFlag(data.selected.ifBlank { "🌐 Выберите страну" })
    val running = vpn.status == Status.RUNNING
    val ping = if (running && vpn.ping != 0L) vpn.ping else data.pings[data.selected] ?: 0L
    val busy = data.selected in data.measuring
    Row(
        Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 18.dp)
            .pressable(onClick = openSheet)
            .shadow(16.dp, RoundedCornerShape(22.dp), ambientColor = BlueMid, spotColor = BlueMid)
            .glass(22.dp, glow = running)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        FlagCircle(flag, 46.dp)
        Spacer(Modifier.width(14.dp))
        Text(title, color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        Box(Modifier.size(8.dp).clip(CircleShape).background(pingColor(if (busy && ping < 0) 0L else ping)))
        Text(
            when {
                ping > 0 -> " $ping мс  "
                busy -> " …  "
                ping < 0 -> " нет связи  "
                else -> " —  "
            },
            color = if (ping < 0 && !busy) Red else TextMain, fontSize = 15.sp
        )
        Bars(if (busy && ping < 0) 0L else ping)
        Spacer(Modifier.width(8.dp))
        LineIcon(Ico.CHEVRON, 18.dp, Blue)
    }
}

@Composable
private fun HomeTiles(vpn: VpnUi, data: Data) {
    val running = vpn.status == Status.RUNNING
    val ping = if (running && vpn.ping != 0L) vpn.ping else data.pings[data.selected] ?: 0L
    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        val shownPing by androidx.compose.animation.core.animateIntAsState(ping.coerceAtLeast(0L).toInt(), tween(600), label = "ping")
        HomeTile(Ico.BOLT, "Пинг", if (ping > 0) "$shownPing мс" else "—", Modifier.weight(1f))
        HomeTile(Ico.DOWN, "Загрузка", if (running) mbit(vpn.downBps) + " Мбит/с" else "—", Modifier.weight(1f))
        HomeTile(Ico.UP, "Отдача", if (running) mbit(vpn.upBps) + " Мбит/с" else "—", Modifier.weight(1f))
    }
}

@Composable
private fun HomeTile(ico: Ico, k: String, v: String, modifier: Modifier) {
    Column(modifier.glass(18.dp).padding(vertical = 12.dp, horizontal = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        LineIcon(ico, 24.dp, Blue)
        Text(k, color = TextSoft, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
        Text(v, color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
private fun HomeGraph(vpn: VpnUi) {
    Column(
        Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp).glass(20.dp)
            .padding(start = 14.dp, end = 14.dp, top = 12.dp, bottom = 10.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Скорость за последнюю минуту", color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f))
            LineIcon(Ico.DOWN, 14.dp, Blue)
            Text(" " + mbit(vpn.downBps) + " Мбит/с", color = Blue, fontSize = 13.sp)
        }
        Canvas(Modifier.fillMaxWidth().height(56.dp).padding(top = 8.dp)) {
            val h = vpn.history
            if (h.size < 2) return@Canvas
            val max = (h.maxOrNull() ?: 1f).coerceAtLeast(1f)
            val step = size.width / (h.size - 1)
            val line = Path()
            val fill = Path()
            var last = Offset.Zero
            h.forEachIndexed { i, v ->
                val x = i * step
                val y = size.height - (v / max) * size.height * 0.9f
                last = Offset(x, y)
                if (i == 0) {
                    line.moveTo(x, y); fill.moveTo(x, size.height); fill.lineTo(x, y)
                } else {
                    line.lineTo(x, y); fill.lineTo(x, y)
                }
            }
            fill.lineTo(size.width, size.height)
            fill.close()
            drawPath(fill, Brush.verticalGradient(listOf(Color(0xFF2F6BFF).copy(alpha = 0.45f), Color.Transparent)))
            drawPath(line, Color(0xFF4A8BFF).copy(alpha = 0.35f), style = Stroke(6.dp.toPx(), cap = StrokeCap.Round))
            drawPath(line, Color(0xFF8CB8FF), style = Stroke(2.dp.toPx(), cap = StrokeCap.Round))
            drawCircle(Color.White, 3.dp.toPx(), last)
        }
        Text("за сеанс " + bytes(vpn.sessionBytes), color = TextDim, fontSize = 11.5.sp)
    }
}

/** Капсулы режимов: три главных + выбранный «редкий» + «ещё». */
@Composable
private fun HomeModes(mode: Mode, onMode: (Mode) -> Unit, openModes: () -> Unit) {
    val main = listOf(Mode.BALANCE, Mode.GAME, Mode.TURBO)
    val shown = if (mode in main) main else main + mode
    Row(
        Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp).glass(26.dp).padding(5.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        for (m in shown) {
            val sel = m == mode
            val on by animateFloatAsState(if (sel) 1f else 0f, tween(350), label = "mode")
            Row(
                Modifier.weight(1f).pressable { if (!sel) onMode(m) }.clip(RoundedCornerShape(22.dp))
                    .background(Brush.verticalGradient(listOf(Color(0xFF3D7BFF).copy(alpha = on), Color(0xFF1F4FD6).copy(alpha = on))))
                    .border(1.dp, Color(0xAA9CC2FF).copy(alpha = 0.67f * on), RoundedCornerShape(22.dp))
                    .padding(vertical = 10.dp),
                horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically
            ) {
                EmojiIcon(m.emoji, 20.dp, if (sel) Color.White else Blue)
                Text(" " + m.title, color = if (sel) Color.White else TextSoft, fontSize = 13.5.sp,
                    fontWeight = if (sel) FontWeight.SemiBold else FontWeight.Normal, maxLines = 1)
            }
        }
        Box(
            Modifier.size(40.dp).clip(CircleShape).clickable(onClick = openModes),
            contentAlignment = Alignment.Center
        ) { Text("⋯", color = TextSoft, fontSize = 20.sp) }
    }
}
