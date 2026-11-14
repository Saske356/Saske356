package io.github.saske356.arise

import android.Manifest
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// Чёрный и холодный синий — «восстань из тени»
private val Ink = Color(0xFF03050B)
private val Night = Color(0xFF0A0F1A)
private val Card = Color(0xFF0F1522)
private val CardHigh = Color(0xFF151C2C)
private val Line = Color(0xFF263147)
private val Blue = Color(0xFF7AAEFF)
private val BlueLight = Color(0xFFD6E6FF)
private val BlueDeep = Color(0xFF2F5FC8)
private val TextMain = Color(0xFFE3ECFF)
private val TextSoft = Color(0xFFA9B6D2)
private val Green = Color(0xFF6FD08C)
private val Amber = Color(0xFFE8C46A)
private val Red = Color(0xFFE57373)

private const val BOT = "AriseVPN_bot"

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Repo.app = applicationContext
        Repo.load()
        takeLink(intent)
        setContent { Root() }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeLink(intent)
    }

    /** arise://install-sub?url=<ссылка подписки> — из бота одним касанием. */
    private fun takeLink(i: Intent?) {
        val data = i?.data ?: return
        if (data.scheme != "arise") return
        val url = data.getQueryParameter("url") ?: return
        Repo.refresh(url)
    }

    @Composable
    private fun Root() {
        val ctx = LocalContext.current
        val vpnPermission = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
            if (r.resultCode == RESULT_OK) AriseVpnService.start(ctx)
            else Toast.makeText(ctx, "Без разрешения Android не даст включить VPN", Toast.LENGTH_LONG).show()
        }
        val notifyPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
        LaunchedEffect(Unit) {
            if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) notifyPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        // Пока приложение на экране: подписка обновляется раз в час, пинг всех стран — раз в 5 минут
        val lifecycle = LocalLifecycleOwner.current.lifecycle
        LaunchedEffect(lifecycle) {
            lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
                if (Store.subUrl.isNotBlank() && System.currentTimeMillis() - Store.lastRefresh > 3_600_000L) {
                    Repo.refresh()
                } else {
                    Repo.pingAll()
                }
                while (true) {
                    delay(300_000L)
                    Repo.pingAll()
                    if (System.currentTimeMillis() - Store.lastRefresh > 3_600_000L) Repo.refresh()
                }
            }
        }
        AriseScreen(
            onToggle = {
                if (VpnState.flow.value.status == Status.STOPPED) {
                    val ask = VpnService.prepare(ctx)
                    if (ask != null) vpnPermission.launch(ask) else AriseVpnService.start(ctx)
                } else {
                    AriseVpnService.stop(ctx)
                }
            },
            onOpen = { url ->
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                } catch (e: Exception) {
                    Toast.makeText(ctx, "Не удалось открыть ссылку", Toast.LENGTH_SHORT).show()
                }
            },
        )
    }
}

@Composable
fun AriseScreen(onToggle: () -> Unit, onOpen: (String) -> Unit) {
    val vpn by VpnState.flow.collectAsState()
    val data by Repo.flow.collectAsState()
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Ink, Night, Color(0xFF0B1C44))))
    ) {
        if (data.servers.isEmpty()) {
            Welcome(data, onOpen)
        } else {
            Main(vpn, data, onToggle, onOpen)
        }
    }
}

@Composable
private fun Header() {
    Column(Modifier.padding(start = 4.dp, top = 8.dp, bottom = 4.dp)) {
        Text("RISE FROM THE SHADOWS", color = Blue, fontSize = 10.sp, letterSpacing = 3.sp)
        Text("ARISE VPN", color = BlueLight, fontSize = 30.sp, fontWeight = FontWeight.Bold, fontFamily = FontFamily.Serif)
    }
}

@Composable
private fun Main(vpn: VpnUi, data: Data, onToggle: () -> Unit, onOpen: (String) -> Unit) {
    val ctx = LocalContext.current
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .systemBarsPadding(),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { Header() }
        item { Panel(vpn, data, onToggle, onOpen) }
        if (data.error.isNotEmpty()) {
            item { Text(data.error, color = Red, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 4.dp)) }
        }
        item {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 6.dp)) {
                Text("Страны", color = TextMain, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text(
                    if (data.pinging) "замер…" else "обновить пинг",
                    color = Blue, fontSize = 13.sp,
                    modifier = Modifier
                        .clip(RoundedCornerShape(50))
                        .clickable(enabled = !data.pinging) { Repo.pingAll() }
                        .padding(horizontal = 10.dp, vertical = 6.dp)
                )
            }
        }
        items(data.servers) { s ->
            ServerRow(
                server = s,
                ping = if (vpn.status == Status.RUNNING && vpn.server == s.name && vpn.ping != 0L) vpn.ping
                else data.pings[s.name] ?: 0L,
                selected = s.name == data.selected,
                onClick = {
                    Repo.select(s.name)
                    if (vpn.status != Status.STOPPED) AriseVpnService.start(ctx)  // переключиться на ходу
                }
            )
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 6.dp, bottom = 24.dp)) {
                SmallButton(if (data.loading) "Обновляю…" else "Обновить подписку", Modifier.weight(1f)) { Repo.refresh() }
                SmallButton("Сменить подписку", Modifier.weight(1f)) {
                    if (vpn.status != Status.STOPPED) AriseVpnService.stop(ctx)
                    Repo.forget()
                }
            }
        }
    }
}

@Composable
private fun Panel(vpn: VpnUi, data: Data, onToggle: () -> Unit, onOpen: (String) -> Unit) {
    val ctx = LocalContext.current
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(vpn.status) {
        while (vpn.status == Status.RUNNING) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    var note by remember { mutableStateOf("") }
    LaunchedEffect(vpn.note) {
        if (vpn.note.isNotEmpty()) {
            note = vpn.note
            delay(15_000)
            note = ""
            VpnState.update { it.copy(note = "") }
        }
    }
    val running = vpn.status == Status.RUNNING
    val connecting = vpn.status == Status.CONNECTING
    val accent by animateColorAsState(if (running) Blue else TextSoft, tween(600), label = "accent")
    val name = data.selected.ifBlank { "Выберите страну ниже" }
    val ping = if (running && vpn.ping != 0L) vpn.ping else data.pings[data.selected] ?: 0L

    Column(
        Modifier
            .fillMaxWidth()
            .shadow(12.dp, RoundedCornerShape(28.dp))
            .clip(RoundedCornerShape(28.dp))
            .background(Brush.verticalGradient(listOf(CardHigh, Ink)))
            .border(1.dp, Blue.copy(alpha = if (running) 0.5f else 0.18f), RoundedCornerShape(28.dp))
            .padding(start = 18.dp, end = 12.dp, top = 16.dp, bottom = 14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    when {
                        running -> "Защищено"
                        connecting -> "Подключение…"
                        else -> "Не подключено"
                    },
                    color = accent, fontSize = 23.sp, fontWeight = FontWeight.Bold
                )
                val started = Store.startedAt
                Text(
                    if (running && started > 0L) duration(now - started) else "Нажмите кнопку, чтобы подключиться",
                    color = if (running) BlueLight else TextSoft,
                    fontFamily = if (running) FontFamily.Monospace else FontFamily.Default,
                    fontSize = if (running) 18.sp else 13.sp,
                    fontWeight = if (running) FontWeight.SemiBold else FontWeight.Normal
                )
                Chip(name, ping, live = running && vpn.ping != 0L)
            }
            PowerButton(running, connecting, onToggle)
        }
        if (note.isNotEmpty()) Text(note, color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        if (vpn.error.isNotEmpty()) Text(vpn.error, color = Red, fontSize = 13.sp)
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .clip(RoundedCornerShape(12.dp))
                .clickable {
                    Repo.setRuApps(!data.ruApps)
                    if (vpn.status == Status.RUNNING) AriseVpnService.start(ctx)  // применить сразу
                }
                .padding(vertical = 3.dp)
        ) {
            Text("🏦 Банки и Госуслуги мимо VPN", color = TextSoft, fontSize = 13.sp, modifier = Modifier.weight(1f))
            Text(if (data.ruApps) "вкл" else "выкл", color = if (data.ruApps) Blue else TextSoft,
                fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val devices = data.title.substringAfter(" · ", "")
            val parts = buildList {
                if (data.expire > 0) add("до " + date(data.expire))
                if (devices.isNotBlank()) add(devices)
            }
            val expired = data.expire in 1 until System.currentTimeMillis() / 1000
            Text(
                if (parts.isEmpty()) "Подписка Arise VPN" else "Подписка " + parts.joinToString(" · "),
                color = if (expired) Red else TextSoft, fontSize = 13.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f)
            )
            Text(
                "Продлить · устройства",
                color = Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(Brush.horizontalGradient(listOf(BlueLight, Blue)))
                    .clickable { onOpen(botLink(data.botUrl, "renew")) }
                    .padding(horizontal = 12.dp, vertical = 7.dp)
            )
        }
    }
}

@Composable
private fun Chip(name: String, ping: Long, live: Boolean) {
    Row(
        Modifier
            .clip(RoundedCornerShape(50))
            .background(CardHigh)
            .border(1.dp, Blue.copy(alpha = 0.35f), RoundedCornerShape(50))
            .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(name, color = TextMain, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        if (ping != 0L) PingText(ping, bright = live)
    }
}

@Composable
private fun PingText(ping: Long, bright: Boolean = true) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(pingColor(ping).copy(alpha = if (bright) 1f else 0.7f)))
        Text(if (ping < 0) "нет связи" else "$ping мс", color = if (ping < 0) Red else TextSoft,
            fontSize = 13.sp, fontFamily = FontFamily.Monospace)
    }
}

@Composable
private fun ServerRow(server: Server, ping: Long, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(if (selected) CardHigh else Card)
            .border(1.dp, if (selected) Blue.copy(alpha = 0.6f) else Line, RoundedCornerShape(18.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(server.name, color = TextMain, fontSize = 16.sp, fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        Spacer(Modifier.width(10.dp))
        if (ping != 0L) PingText(ping) else Text("—", color = TextSoft, fontSize = 13.sp)
    }
}

@Composable
private fun SmallButton(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Text(
        text, color = TextMain, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .border(1.dp, Line, RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp)
    )
}

@Composable
private fun BigButton(text: String, gold: Boolean, onClick: () -> Unit) {
    val m = Modifier
        .fillMaxWidth()
        .clip(RoundedCornerShape(16.dp))
    Text(
        text, color = if (gold) Ink else TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold,
        textAlign = TextAlign.Center,
        modifier = (if (gold) m.background(Brush.horizontalGradient(listOf(BlueLight, Blue)))
        else m.border(1.dp, Blue.copy(alpha = 0.4f), RoundedCornerShape(16.dp)))
            .clickable(onClick = onClick)
            .padding(vertical = 15.dp)
    )
}

@Composable
private fun Welcome(data: Data, onOpen: (String) -> Unit) {
    val ctx = LocalContext.current
    var link by remember { mutableStateOf("") }
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .padding(horizontal = 22.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Header()
        Spacer(Modifier.height(8.dp))
        Text("Восстань из тени", color = BlueLight, fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Text(
            "Чтобы подключиться, нужна подписка из нашего Telegram-бота. Уже есть? Скопируйте ссылку " +
                "подписки в боте и вставьте её сюда.",
            color = TextSoft, fontSize = 15.sp
        )
        BigButton("✦ Попробовать бесплатно", gold = true) { onOpen("https://t.me/$BOT?start=trial") }
        BigButton("Открыть бота", gold = false) { onOpen("https://t.me/$BOT") }
        Spacer(Modifier.height(6.dp))
        OutlinedTextField(
            value = link,
            onValueChange = { link = it },
            singleLine = true,
            label = { Text("Ссылка подписки") },
            modifier = Modifier.fillMaxWidth(),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = TextMain, unfocusedTextColor = TextMain,
                focusedBorderColor = Blue, unfocusedBorderColor = Line,
                focusedLabelColor = Blue, unfocusedLabelColor = TextSoft, cursorColor = Blue
            )
        )
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SmallButton("📋 Вставить", Modifier.weight(1f)) {
                val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                link = cm.primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString()?.trim() ?: ""
            }
            SmallButton(if (data.loading) "Загружаю…" else "Добавить", Modifier.weight(1f)) {
                if (link.startsWith("http")) Repo.refresh(link)
                else Toast.makeText(ctx, "Вставьте ссылку подписки из бота", Toast.LENGTH_SHORT).show()
            }
        }
        if (data.error.isNotEmpty()) Text(data.error, color = Red, fontSize = 13.sp)
    }
}

@Composable
private fun PowerButton(running: Boolean, connecting: Boolean, onClick: () -> Unit) {
    val transition = rememberInfiniteTransition(label = "halo")
    val pulse by transition.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(if (connecting) 900 else 2200), RepeatMode.Restart),
        label = "pulse"
    )
    Box(
        Modifier
            .size(118.dp)
            .semantics { contentDescription = if (running) "Отключить VPN" else "Подключить VPN" },
        contentAlignment = Alignment.Center
    ) {
        // Волны поднимаются от кнопки: медленно, когда VPN включён, быстро — пока подключается
        Canvas(Modifier.fillMaxSize()) {
            val base = size.minDimension / 2f * 0.70f
            if (running || connecting) {
                for (i in 0..1) {
                    val t = (pulse + i * 0.5f) % 1f
                    drawCircle(
                        color = Blue.copy(alpha = (1f - t) * 0.38f),
                        radius = base + (size.minDimension / 2f - base) * t,
                        style = Stroke(width = 2.5.dp.toPx())
                    )
                }
                drawCircle(
                    brush = Brush.radialGradient(listOf(Blue.copy(alpha = 0.30f), Color.Transparent), center = center,
                        radius = size.minDimension / 2f)
                )
            } else {
                drawCircle(color = Line, radius = base + 8.dp.toPx(), style = Stroke(width = 1.dp.toPx()))
            }
        }
        Box(
            Modifier
                .size(82.dp)
                .shadow(if (running) 16.dp else 6.dp, CircleShape)
                .clip(CircleShape)
                .background(
                    if (running) Brush.radialGradient(listOf(BlueLight, Blue, BlueDeep))
                    else Brush.radialGradient(listOf(Color(0xFF1C2537), Night))
                )
                .border(2.dp, if (running) BlueLight else Blue.copy(alpha = 0.7f), CircleShape)
                .clickable(onClick = onClick),
            contentAlignment = Alignment.Center
        ) {
            val icon = if (running) Ink else Blue
            Canvas(Modifier.size(34.dp)) {
                val w = 4.dp.toPx()
                val r = size.minDimension / 2f - w
                drawArc(
                    color = icon, startAngle = -60f, sweepAngle = 300f, useCenter = false,
                    topLeft = Offset(center.x - r, center.y - r), size = Size(r * 2, r * 2),
                    style = Stroke(width = w, cap = StrokeCap.Round)
                )
                drawLine(
                    color = icon, start = Offset(center.x, center.y - r - w / 2),
                    end = Offset(center.x, center.y - r * 0.15f), strokeWidth = w, cap = StrokeCap.Round
                )
            }
        }
    }
}

private fun pingColor(ping: Long): Color = when {
    ping < 0 -> Red
    ping < 150 -> Green
    ping < 400 -> Amber
    else -> Red
}

private fun duration(millis: Long): String {
    val s = millis.coerceAtLeast(0L) / 1000
    return "%02d:%02d:%02d".format(s / 3600, (s / 60) % 60, s % 60)
}

private fun date(epochSeconds: Long): String =
    SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(Date(epochSeconds * 1000))

/** Ссылка в бота из подписки (support-url), а если её нет — на @AriseVPN_bot. */
private fun botLink(botUrl: String, start: String): String =
    (botUrl.ifBlank { "https://t.me/$BOT" }).substringBefore("?") + "?start=" + start
