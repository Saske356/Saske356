package io.github.saske356.arise

import android.Manifest
import android.app.StatusBarManager
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.drawable.Icon
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
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
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

// Чёрный и холодный синий
private val Ink = Color(0xFF04070F)
private val Night = Color(0xFF071433)
private val Deep = Color(0xFF0B2A6B)
private val Glass = Color(0x0BFFFFFF)
private val GlassLine = Color(0x14FFFFFF)
private val Sheet = Color(0xFF0D1526)
private val Blue = Color(0xFF8CB8FF)
private val BlueMid = Color(0xFF6FA4FF)
private val BlueLight = Color(0xFFCFE0FF)
private val BlueDeep = Color(0xFF2F5FC8)
private val TextMain = Color(0xFFEAF1FF)
private val TextSoft = Color(0xFF9FB0D3)
private val TextDim = Color(0xFF7F8DAB)
private val Green = Color(0xFF6FD08C)
private val Amber = Color(0xFFE8C46A)
private val Red = Color(0xFFE57373)

private const val BOT = "AriseVPN_bot"

private enum class Screen { HOME, MODES, TOOLS, APPS, DNS }

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

    private fun open(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (e: Exception) {
            Toast.makeText(this, "Не удалось открыть ссылку", Toast.LENGTH_SHORT).show()
        }
    }

    private fun addTile() {
        if (Build.VERSION.SDK_INT >= 33) {
            try {
                getSystemService(StatusBarManager::class.java).requestAddTileService(
                    ComponentName(this, AriseTile::class.java), "Arise VPN",
                    Icon.createWithResource(this, R.drawable.ic_shield), mainExecutor
                ) { }
                return
            } catch (e: Exception) {
                // покажем подсказку ниже
            }
        }
        Toast.makeText(this, "Потяните шторку вниз → ✏️ → перетащите «Arise VPN» к кнопкам", Toast.LENGTH_LONG).show()
    }

    private fun leakProtection() {
        Toast.makeText(
            this, "Нажмите ⚙ у «Arise VPN» и включите «Постоянная VPN» и «Блокировать соединения без VPN»",
            Toast.LENGTH_LONG
        ).show()
        try {
            startActivity(Intent(Settings.ACTION_VPN_SETTINGS))
        } catch (e: Exception) {
            open("https://support.google.com/android/answer/9089766")
        }
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
                if (Store.subUrl.isNotBlank() && System.currentTimeMillis() - Store.lastRefresh > 3_600_000L) Repo.refresh()
                else Repo.pingAll()
                AppUpdate.check()
                while (true) {
                    delay(300_000L)
                    Repo.pingAll()
                    if (System.currentTimeMillis() - Store.lastRefresh > 3_600_000L) Repo.refresh()
                }
            }
        }
        val vpn by VpnState.flow.collectAsState()
        val data by Repo.flow.collectAsState()
        var screen by remember { mutableStateOf(Screen.HOME) }
        var sheet by remember { mutableStateOf(false) }
        BackHandler(enabled = sheet || screen != Screen.HOME) {
            if (sheet) sheet = false
            else screen = if (screen == Screen.APPS || screen == Screen.DNS) Screen.TOOLS else Screen.HOME
        }
        val toggle = {
            if (VpnState.flow.value.status == Status.STOPPED) {
                val ask = VpnService.prepare(ctx)
                if (ask != null) vpnPermission.launch(ask) else AriseVpnService.start(ctx)
            } else {
                AriseVpnService.stop(ctx)
            }
        }
        // Любая настройка, которая меняет конфиг, применяется сразу, если VPN включён
        val apply = { if (VpnState.flow.value.status != Status.STOPPED) AriseVpnService.start(ctx) }

        Box(Modifier.fillMaxSize()) {
            Backdrop(vpn.status == Status.RUNNING)
            when {
                data.servers.isEmpty() -> Welcome(data) { open(it) }
                screen == Screen.MODES -> ModesScreen(data, back = { screen = Screen.HOME }) { m ->
                    Repo.setMode(m)
                    apply()
                }
                screen == Screen.TOOLS -> ToolsScreen(
                    data, back = { screen = Screen.HOME },
                    onApps = { screen = Screen.APPS }, onLeak = { leakProtection() }, onTile = { addTile() },
                    onDns = { screen = Screen.DNS },
                    onForget = {
                        if (VpnState.flow.value.status != Status.STOPPED) AriseVpnService.stop(ctx)
                        Repo.forget()
                        screen = Screen.HOME
                    }
                )
                screen == Screen.DNS -> DnsScreen(data, back = { screen = Screen.TOOLS }) { d ->
                    Repo.setDns(d)
                    apply()
                }
                screen == Screen.APPS -> AppsScreen(data, back = { screen = Screen.TOOLS }, onChange = apply)
                else -> Home(
                    vpn, data, onToggle = toggle, onOpen = { open(it) },
                    openSheet = { sheet = true }, openModes = { screen = Screen.MODES },
                    openTools = { screen = Screen.TOOLS }, onRuApps = { Repo.setRuApps(!data.ruApps); apply() }
                )
            }
            CountrySheet(sheet && data.servers.isNotEmpty(), vpn, data, close = { sheet = false }) { name ->
                Repo.select(name)
                sheet = false
                apply()
            }
        }
    }
}

// ---------------------------------------------------------------- фон

@Composable
private fun Backdrop(on: Boolean) {
    val glow by animateFloatAsState(if (on) 0.45f else 0.18f, tween(900), label = "glow")
    val t = rememberInfiniteTransition(label = "sparks")
    val time by t.animateFloat(0f, 1f, infiniteRepeatable(tween(14_000, easing = LinearEasing)), label = "time")
    Canvas(Modifier.fillMaxSize()) {
        drawRect(Brush.verticalGradient(listOf(Ink, Ink, Night, Deep)))
        drawRect(
            Brush.radialGradient(
                listOf(Color(0xFF4A8BFF).copy(alpha = glow), Color.Transparent),
                center = Offset(size.width / 2, size.height * 0.36f), radius = size.width * 0.8f
            )
        )
        // Искры медленно поднимаются снизу и гаснут наверху
        for (i in 0 until 26) {
            val seed = (i * 7919) % 1000 / 1000f
            val x = ((i * 0.618f) % 1f) * size.width
            val p = (time * (0.6f + seed * 0.8f) + seed) % 1f
            val y = size.height * (1f - p)
            val a = (1f - p) * (if (on) 0.55f else 0.3f)
            drawCircle(Blue.copy(alpha = a), radius = 1.2.dp.toPx() + seed * 1.6.dp.toPx(), center = Offset(x, y))
        }
    }
}

// ---------------------------------------------------------------- главный экран

@Composable
private fun Home(
    vpn: VpnUi, data: Data, onToggle: () -> Unit, onOpen: (String) -> Unit, openSheet: () -> Unit,
    openModes: () -> Unit, openTools: () -> Unit, onRuApps: () -> Unit,
) {
    val running = vpn.status == Status.RUNNING
    Box(Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(bottom = 120.dp)
        ) {
            TopBar(openTools)
            UpdateCard()
            SubBar(data, onOpen)
            Spacer(Modifier.height(if (running) 14.dp else 30.dp))
            Hero(running, vpn.status == Status.CONNECTING, onToggle)
            StateBlock(vpn, data, openModes)
            if (vpn.note.isNotEmpty()) {
                Text(vpn.note, color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 6.dp))
                LaunchedEffect(vpn.note) {
                    delay(15_000)
                    VpnState.update { it.copy(note = "") }
                }
            }
            if (vpn.error.isNotEmpty()) {
                Text(vpn.error, color = Red, fontSize = 13.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 6.dp))
            }
            if (data.error.isNotEmpty()) {
                Text(data.error, color = Red, fontSize = 13.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 4.dp))
            }
            if (running) {
                StatsRow(vpn, data)
                Graph(vpn)
            } else {
                Spacer(Modifier.height(18.dp))
                ToggleRow("🏦", "Банки и Госуслуги мимо VPN", data.ruApps, Modifier.padding(horizontal = 22.dp)) { onRuApps() }
            }
        }
        CountryCard(
            vpn, data, openSheet,
            Modifier
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(horizontal = 16.dp, vertical = 14.dp)
        )
    }
}

@Composable
private fun Logo(size: Dp = 30.dp) {
    Box(
        Modifier
            .size(size)
            .shadow(10.dp, RoundedCornerShape(size / 3.4f), ambientColor = BlueMid, spotColor = BlueMid)
            .clip(RoundedCornerShape(size / 3.4f))
            .background(Brush.linearGradient(listOf(Blue, BlueDeep))),
        contentAlignment = Alignment.Center
    ) {
        Text("A", color = Ink, fontWeight = FontWeight.ExtraBold, fontSize = (size.value * 0.53f).sp)
    }
}

@Composable
private fun TopBar(openTools: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(start = 22.dp, end = 22.dp, top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Logo()
        Spacer(Modifier.width(10.dp))
        Text("Arise", color = TextMain, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        Box(
            Modifier
                .size(42.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(Glass)
                .border(1.dp, GlassLine, RoundedCornerShape(14.dp))
                .clickable(onClick = openTools),
            contentAlignment = Alignment.Center
        ) { Text("⚙", color = TextSoft, fontSize = 19.sp) }
    }
}

@Composable
private fun SubBar(data: Data, onOpen: (String) -> Unit) {
    val devices = data.title.substringAfter(" · ", "")
    val expired = data.expire in 1 until System.currentTimeMillis() / 1000
    Row(
        Modifier
            .fillMaxWidth()
            .padding(start = 22.dp, end = 22.dp, top = 14.dp)
            .clip(RoundedCornerShape(15.dp))
            .background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(15.dp))
            .padding(horizontal = 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            when {
                expired -> "Подписка закончилась"
                data.expire > 0 -> "Подписка до " + date(data.expire, "dd.MM") + (if (devices.isNotBlank()) " · $devices" else "")
                else -> "Подписка Arise VPN"
            },
            color = if (expired) Red else TextSoft, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        Text(
            "Продлить", color = Blue, fontSize = 13.sp, fontWeight = FontWeight.Bold,
            modifier = Modifier
                .clip(RoundedCornerShape(50))
                .clickable { onOpen(botLink(data.botUrl, "renew")) }
                .padding(start = 10.dp, top = 2.dp, bottom = 2.dp)
        )
    }
}

@Composable
private fun Hero(running: Boolean, connecting: Boolean, onToggle: () -> Unit) {
    val haptic = LocalHapticFeedback.current
    val t = rememberInfiniteTransition(label = "hero")
    val pulse by t.animateFloat(
        0f, 1f, infiniteRepeatable(tween(if (connecting) 1100 else 2600, easing = LinearEasing), RepeatMode.Restart),
        label = "pulse"
    )
    val btn by animateDpAsState(if (running) 176.dp else 196.dp, tween(500), label = "btn")
    Box(
        Modifier
            .fillMaxWidth()
            .height(300.dp)
            .semantics { contentDescription = if (running) "Отключить VPN" else "Подключить VPN" },
        contentAlignment = Alignment.Center
    ) {
        Canvas(Modifier.size(300.dp)) {
            val r = size.minDimension / 2f
            if (running) {
                drawCircle(
                    Brush.radialGradient(listOf(BlueMid.copy(alpha = 0.45f), Color.Transparent), center = center, radius = r),
                    radius = r
                )
            }
            drawCircle(Blue.copy(alpha = if (running) 0.26f else 0.10f), radius = r * 0.98f, style = Stroke(1.dp.toPx()))
            drawCircle(Blue.copy(alpha = if (running) 0.40f else 0.16f), radius = r * 0.82f, style = Stroke(1.dp.toPx()))
            if (running || connecting) {
                for (i in 0..2) {
                    val k = (pulse + i / 3f) % 1f
                    drawCircle(
                        Blue.copy(alpha = (1f - k) * 0.42f), radius = r * 0.6f + r * 0.4f * k,
                        style = Stroke(2.dp.toPx())
                    )
                }
            }
        }
        Box(
            Modifier
                .size(btn)
                .shadow(if (running) 30.dp else 14.dp, CircleShape, ambientColor = BlueMid, spotColor = BlueMid)
                .clip(CircleShape)
                .background(
                    if (running) Brush.radialGradient(listOf(BlueLight, BlueMid, BlueDeep))
                    else Brush.radialGradient(listOf(Color(0xFF16223A), Color(0xFF0A101D)))
                )
                .border(1.5.dp, if (running) BlueLight else Blue.copy(alpha = 0.35f), CircleShape)
                .clickable {
                    haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    onToggle()
                },
            contentAlignment = Alignment.Center
        ) {
            PowerIcon(if (running) Ink else Blue, 62.dp)
        }
    }
}

@Composable
private fun PowerIcon(color: Color, size: Dp) {
    Canvas(Modifier.size(size)) {
        val w = size.toPx() * 0.095f
        val r = this.size.minDimension / 2f - w
        drawArc(
            color = color, startAngle = -55f, sweepAngle = 290f, useCenter = false,
            topLeft = Offset(center.x - r, center.y - r), size = Size(r * 2, r * 2),
            style = Stroke(width = w, cap = StrokeCap.Round)
        )
        drawLine(color, Offset(center.x, center.y - r - w * 0.4f), Offset(center.x, center.y - r * 0.12f), w, StrokeCap.Round)
    }
}

@Composable
private fun StateBlock(vpn: VpnUi, data: Data, openModes: () -> Unit) {
    val running = vpn.status == Status.RUNNING
    val connecting = vpn.status == Status.CONNECTING
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(running) {
        while (running) {
            now = System.currentTimeMillis()
            delay(1000)
        }
    }
    val top by animateColorAsState(if (running) Blue else TextSoft, tween(600), label = "top")
    Column(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            when {
                running -> "Защищено"
                connecting -> "Подключаемся…"
                else -> "Нажмите, чтобы подключиться"
            },
            color = top, fontSize = 15.sp
        )
        val started = Store.startedAt
        if (running && started > 0L) {
            Text(duration(now - started), color = TextMain, fontSize = 36.sp, fontWeight = FontWeight.SemiBold,
                fontFamily = FontFamily.Monospace, letterSpacing = 2.sp)
        } else {
            Text(if (connecting) "· · ·" else "Не защищено", color = TextMain, fontSize = 30.sp, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(10.dp))
        Text(
            "${data.mode.emoji} ${data.mode.title}  ›", color = BlueLight, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier
                .clip(RoundedCornerShape(50))
                .background(BlueMid.copy(alpha = 0.14f))
                .border(1.dp, Blue.copy(alpha = 0.35f), RoundedCornerShape(50))
                .clickable(onClick = openModes)
                .padding(horizontal = 14.dp, vertical = 7.dp)
        )
    }
}

@Composable
private fun StatsRow(vpn: VpnUi, data: Data) {
    val ping = if (vpn.ping != 0L) vpn.ping else data.pings[data.selected] ?: 0L
    Row(Modifier.fillMaxWidth().padding(start = 22.dp, end = 22.dp, top = 18.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        StatTile("Пинг", if (ping > 0) "$ping" else if (ping < 0) "нет" else "—", if (ping > 0) "мс" else "", Modifier.weight(1f))
        StatTile("Защита", "QUIC", "TLS 1.3", Modifier.weight(1f))
        StatTile("IP", "скрыт", "", Modifier.weight(1f))
    }
}

@Composable
private fun StatTile(k: String, v: String, unit: String, modifier: Modifier) {
    Column(
        modifier
            .clip(RoundedCornerShape(16.dp))
            .background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(16.dp))
            .padding(12.dp)
    ) {
        Text(k.uppercase(), color = TextDim, fontSize = 10.sp, letterSpacing = 1.sp)
        Row(verticalAlignment = Alignment.Bottom) {
            Text(v, color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            if (unit.isNotEmpty()) Text(" $unit", color = TextSoft, fontSize = 11.sp, modifier = Modifier.padding(bottom = 2.dp))
        }
    }
}

@Composable
private fun Graph(vpn: VpnUi) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(start = 22.dp, end = 22.dp, top = 10.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(16.dp))
            .padding(start = 14.dp, end = 14.dp, top = 12.dp, bottom = 8.dp)
    ) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text("↓ ", color = TextDim, fontSize = 12.sp)
            Text(mbit(vpn.downBps), color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Text("   ↑ ", color = TextDim, fontSize = 12.sp)
            Text(mbit(vpn.upBps), color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            Text(" Мбит/с", color = TextSoft, fontSize = 11.sp, modifier = Modifier.weight(1f))
            Text("сеанс " + bytes(vpn.sessionBytes), color = TextDim, fontSize = 12.sp)
        }
        Canvas(Modifier.fillMaxWidth().height(46.dp).padding(top = 6.dp)) {
            val h = vpn.history
            if (h.size < 2) return@Canvas
            val max = (h.maxOrNull() ?: 1f).coerceAtLeast(1f)
            val step = size.width / (h.size - 1)
            val line = Path()
            val fill = Path()
            h.forEachIndexed { i, v ->
                val x = i * step
                val y = size.height - (v / max) * size.height * 0.92f
                if (i == 0) {
                    line.moveTo(x, y); fill.moveTo(x, size.height); fill.lineTo(x, y)
                } else {
                    line.lineTo(x, y); fill.lineTo(x, y)
                }
            }
            fill.lineTo(size.width, size.height)
            fill.close()
            drawPath(fill, Brush.verticalGradient(listOf(BlueMid.copy(alpha = 0.5f), Color.Transparent)))
            drawPath(line, Blue, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round))
        }
    }
}

@Composable
private fun ToggleRow(icon: String, text: String, on: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(onClick = onClick).padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text("$icon  $text", color = TextSoft, fontSize = 14.sp, modifier = Modifier.weight(1f))
        Switch(
            checked = on, onCheckedChange = { onClick() },
            colors = SwitchDefaults.colors(
                checkedThumbColor = TextMain, checkedTrackColor = BlueDeep,
                uncheckedThumbColor = TextDim, uncheckedTrackColor = Color(0xFF1A2233), uncheckedBorderColor = GlassLine
            )
        )
    }
}

@Composable
private fun CountryCard(vpn: VpnUi, data: Data, onClick: () -> Unit, modifier: Modifier) {
    val (flag, title) = splitFlag(data.selected.ifBlank { "🌐 Выберите страну" })
    val running = vpn.status == Status.RUNNING
    val ping = if (running && vpn.ping != 0L) vpn.ping else data.pings[data.selected] ?: 0L
    Row(
        modifier
            .fillMaxWidth()
            .shadow(18.dp, RoundedCornerShape(22.dp))
            .clip(RoundedCornerShape(22.dp))
            .background(Brush.verticalGradient(listOf(Color(0xF01E2C4A), Color(0xF00F1626))))
            .border(1.dp, Blue.copy(alpha = 0.22f), RoundedCornerShape(22.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        FlagCircle(flag, 46.dp)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                when {
                    ping < 0 -> "Нет связи — выберите другую"
                    running -> "Подключено" + if (ping > 0) " · $ping мс" else ""
                    ping > 0 -> "Пинг $ping мс · нажмите, чтобы сменить"
                    else -> "Нажмите, чтобы выбрать страну"
                },
                color = TextDim, fontSize = 12.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
            )
        }
        Bars(ping)
        Text("  ›", color = TextDim, fontSize = 22.sp)
    }
}

@Composable
private fun FlagCircle(flag: String, size: Dp) {
    Box(
        Modifier
            .size(size)
            .clip(CircleShape)
            .background(Glass)
            .border(1.dp, GlassLine, CircleShape),
        contentAlignment = Alignment.Center
    ) { Text(flag, fontSize = (size.value * 0.55f).sp) }
}

@Composable
private fun Bars(ping: Long) {
    val level = when {
        ping <= 0 -> 0
        ping < 120 -> 4
        ping < 250 -> 3
        ping < 450 -> 2
        else -> 1
    }
    val color = if (level >= 3) Green else if (level == 2) Amber else Red
    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(3.dp), modifier = Modifier.height(18.dp)) {
        for (i in 1..4) {
            Box(
                Modifier
                    .width(4.dp)
                    .height((3 + i * 3.75f).dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(if (i <= level) color else Color(0x26FFFFFF))
            )
        }
    }
}

// ---------------------------------------------------------------- выбор страны

@Composable
private fun CountrySheet(open: Boolean, vpn: VpnUi, data: Data, close: () -> Unit, onPick: (String) -> Unit) {
    AnimatedVisibility(open, enter = fadeIn(), exit = fadeOut()) {
        Box(Modifier.fillMaxSize().background(Color(0xA6000000)).clickable(onClick = close))
    }
    AnimatedVisibility(open, enter = slideInVertically { it }, exit = slideOutVertically { it }) {
        var query by remember { mutableStateOf("") }
        Box(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .fillMaxHeight(0.84f)
                    .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp))
                    .background(Brush.verticalGradient(listOf(Color(0xFF111A2D), Color(0xFF0A1020))))
                    .border(1.dp, Blue.copy(alpha = 0.2f), RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp))
                    // касания по самому окну не должны закрывать его (под ним — затемнение, которое закрывает)
                    .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { }
                    .navigationBarsPadding()
                    .padding(horizontal = 16.dp)
            ) {
                Box(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 14.dp), contentAlignment = Alignment.Center) {
                    Box(Modifier.width(42.dp).height(5.dp).clip(RoundedCornerShape(3.dp)).background(Color(0x2EFFFFFF)))
                }
                Text("Выберите страну", color = TextMain, fontSize = 21.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 6.dp))
                Field(query, "🔍  Поиск страны", Modifier.padding(top = 12.dp, bottom = 4.dp)) { query = it }
                val list = data.servers.filter { query.isBlank() || it.name.contains(query.trim(), ignoreCase = true) }
                val special = list.filter { it.name.startsWith("🚀") || it.name.startsWith("🎮") }
                val rest = list - special.toSet()
                LazyColumn(Modifier.fillMaxSize()) {
                    if (special.isNotEmpty()) {
                        item { Group("Рекомендуем") }
                        items(special) { s -> CountryRow(s, vpn, data, onPick) }
                    }
                    item { Group("Все страны") }
                    items(rest) { s -> CountryRow(s, vpn, data, onPick) }
                    item { Spacer(Modifier.height(20.dp)) }
                }
            }
        }
    }
}

@Composable
private fun Group(text: String) {
    Text(text.uppercase(), color = TextDim, fontSize = 11.sp, letterSpacing = 1.5.sp, modifier = Modifier.padding(start = 6.dp, top = 16.dp, bottom = 6.dp))
}

@Composable
private fun CountryRow(s: Server, vpn: VpnUi, data: Data, onPick: (String) -> Unit) {
    val (flag, title) = splitFlag(s.name)
    val selected = s.name == data.selected
    val ping = if (vpn.status == Status.RUNNING && vpn.server == s.name && vpn.ping != 0L) vpn.ping else data.pings[s.name] ?: 0L
    val note = when {
        s.name.startsWith("🚀") -> "Выбирает самый быстрый сам"
        s.name.startsWith("🎮") -> "Напрямую, ровный пинг"
        s.name.contains("🇷🇺") || s.name.contains("Обход", true) -> "Для белых списков"
        else -> ""
    }
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(if (selected) BlueMid.copy(alpha = 0.12f) else Color.Transparent)
            .border(1.dp, if (selected) Blue.copy(alpha = 0.35f) else Color.Transparent, RoundedCornerShape(16.dp))
            .clickable { onPick(s.name) }
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        FlagCircle(flag, 40.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = TextMain, fontSize = 15.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (note.isNotEmpty()) Text(note, color = TextDim, fontSize = 12.sp)
        }
        PingLabel(ping)
    }
}

@Composable
private fun PingLabel(ping: Long) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(pingColor(ping)))
        Text(
            when {
                ping > 0 -> "  $ping мс"
                ping < 0 -> "  нет связи"
                else -> "  —"
            },
            color = if (ping < 0) Red else TextSoft, fontSize = 13.sp, fontFamily = FontFamily.Monospace
        )
    }
}

// ---------------------------------------------------------------- режимы

@Composable
private fun Page(title: String, lead: String, back: () -> Unit, content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 14.dp)) {
            Text(
                "‹", color = TextMain, fontSize = 28.sp,
                modifier = Modifier.clip(RoundedCornerShape(12.dp)).clickable(onClick = back).padding(horizontal = 10.dp)
            )
            Logo(26.dp)
            Spacer(Modifier.width(8.dp))
            Text("Arise", color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
        Text(title, color = TextMain, fontSize = 26.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 4.dp, top = 14.dp))
        if (lead.isNotEmpty()) Text(lead, color = TextSoft, fontSize = 13.sp, modifier = Modifier.padding(start = 4.dp, top = 4.dp, bottom = 14.dp))
        else Spacer(Modifier.height(14.dp))
        content()
        Spacer(Modifier.height(28.dp))
    }
}

@Composable
private fun ModesScreen(data: Data, back: () -> Unit, onPick: (Mode) -> Unit) {
    Page("Режим соединения", "Каждый режим по-настоящему меняет настройки VPN. Чем-то всегда жертвуем — честно пишем, чем.", back) {
        for (m in Mode.entries) {
            val sel = m == data.mode
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 10.dp)
                    .clip(RoundedCornerShape(18.dp))
                    .background(
                        if (sel) Brush.linearGradient(listOf(BlueMid.copy(alpha = 0.25f), Color(0x40203264)))
                        else Brush.linearGradient(listOf(Glass, Glass))
                    )
                    .border(1.dp, if (sel) Blue.copy(alpha = 0.55f) else GlassLine, RoundedCornerShape(18.dp))
                    .clickable { onPick(m) }
                    .padding(16.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(m.emoji, fontSize = 20.sp)
                    Spacer(Modifier.width(10.dp))
                    Text(m.title, color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    if (m == Mode.BALANCE) Text("по умолчанию", color = TextSoft, fontSize = 11.sp)
                    if (sel) Text("  ✓", color = Blue, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                }
                Text(m.desc, color = TextSoft, fontSize = 12.5.sp, modifier = Modifier.padding(top = 6.dp))
                if (m.plus.isNotEmpty()) {
                    Row(Modifier.padding(top = 8.dp)) {
                        Text("＋ ${m.plus}", color = Green, fontSize = 12.sp, modifier = Modifier.weight(1f))
                        Text("− ${m.minus}", color = Color(0xFFE8A06A), fontSize = 12.sp, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------- DNS

@Composable
private fun DnsScreen(data: Data, back: () -> Unit, onPick: (Dns) -> Unit) {
    Page("DNS", "Через какой сервер телефон узнаёт адреса сайтов. Запросы идут через VPN, оператор их не видит. Меняется сразу.", back) {
        for (d in Dns.entries) {
            val sel = d == data.dns
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 8.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(
                        if (sel) Brush.linearGradient(listOf(BlueMid.copy(alpha = 0.25f), Color(0x40203264)))
                        else Brush.linearGradient(listOf(Glass, Glass))
                    )
                    .border(1.dp, if (sel) Blue.copy(alpha = 0.55f) else GlassLine, RoundedCornerShape(16.dp))
                    .clickable { onPick(d) }
                    .padding(horizontal = 14.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(d.title, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        if (d == Dns.CLOUDFLARE) Text("  по умолчанию", color = TextSoft, fontSize = 11.sp)
                    }
                    Text(d.note, color = TextSoft, fontSize = 12.5.sp)
                    Text("${d.ip} · ${d.ip2}", color = TextDim, fontSize = 11.5.sp)
                }
                if (sel) Text("✓", color = Blue, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}

// ---------------------------------------------------------------- инструменты

@Composable
private fun ToolsScreen(
    data: Data, back: () -> Unit, onApps: () -> Unit, onLeak: () -> Unit, onTile: () -> Unit,
    onDns: () -> Unit, onForget: () -> Unit,
) {
    val ctx = LocalContext.current
    val speed by SpeedState.flow.collectAsState()
    Page("Инструменты", "", back) {
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(22.dp))
                .background(Brush.radialGradient(listOf(BlueMid.copy(alpha = 0.30f), Color(0x990F1626))))
                .border(1.dp, Blue.copy(alpha = 0.25f), RoundedCornerShape(22.dp))
                .padding(18.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("Тест скорости через VPN", color = TextSoft, fontSize = 14.sp)
            Text(if (speed.downMbps > 0) "%.1f".format(speed.downMbps) else "—", color = TextMain, fontSize = 54.sp, fontWeight = FontWeight.ExtraBold)
            Text("Мбит/с", color = TextSoft, fontSize = 14.sp)
            Row(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalArrangement = Arrangement.SpaceAround) {
                Metric("Пинг", if (speed.ping > 0) "${speed.ping} мс" else "—")
                Metric("Джиттер", if (speed.ping > 0) "${speed.jitter} мс" else "—")
                Metric("Отдача", if (speed.upMbps > 0) "%.1f".format(speed.upMbps) else "—")
            }
            if (speed.error.isNotEmpty()) Text(speed.error, color = Red, fontSize = 12.5.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 8.dp))
            Spacer(Modifier.height(12.dp))
            Big(if (speed.running) speed.stage.ifBlank { "Проверяю…" } else "Проверить скорость", gold = !speed.running) {
                if (!speed.running) Repo.speedTest()
            }
        }
        Spacer(Modifier.height(14.dp))
        Tool("🛡", "Защита от утечек", "Без VPN интернет блокируется", "Настроить", onLeak)
        Tool("📱", "Приложения мимо VPN", "Банки, Госуслуги и свои",
            "${(if (data.ruApps) RuApps.PACKAGES.size else 0) + data.bypass.size} ›", onApps)
        Tool("🌐", "DNS", "${data.dns.ip} · ${data.dns.note}", "${data.dns.title} ›", onDns)
        Tool("⚡", "Автоподключение", "При включении телефона", if (data.autoConnect) "Вкл" else "Выкл") {
            Repo.setAutoConnect(!data.autoConnect)
        }
        Tool("🔘", "Кнопка в шторке", "Включать VPN, не открывая приложение", "Добавить", onTile)
        val upd by AppUpdate.flow.collectAsState()
        Tool("⬆️", "Обновление приложения",
            when {
                upd.progress >= 0f -> "Скачиваю… ${(upd.progress * 100).toInt()}%"
                upd.version.isNotEmpty() -> "Доступна версия ${upd.version}"
                upd.note.isNotEmpty() -> upd.note
                else -> "Сейчас ${BuildConfig.VERSION_NAME}"
            },
            if (upd.checking) "…" else if (upd.version.isNotEmpty()) "Обновить" else "Проверить") {
            if (upd.version.isNotEmpty()) AppUpdate.installHere(ctx) else AppUpdate.check(force = true)
        }
        Tool("🔄", "Обновить подписку", if (data.loading) "Обновляю…" else "Страны и срок — с сервера", "") { Repo.refresh() }
        Tool("↩", "Сменить подписку", "Удалить эту и добавить другую", "", onForget)
        Text("Arise VPN ${BuildConfig.VERSION_NAME}", color = TextDim, fontSize = 12.sp, modifier = Modifier.fillMaxWidth().padding(top = 10.dp), textAlign = TextAlign.Center)
    }
}

/** Плашка «Доступна новая версия» на главном экране: обновиться внутри или через браузер. */
@Composable
private fun UpdateCard() {
    val ctx = LocalContext.current
    val u by AppUpdate.flow.collectAsState()
    if (u.version.isEmpty() && u.progress < 0f && u.note.isEmpty()) return
    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Brush.linearGradient(listOf(BlueMid.copy(alpha = 0.30f), Color(0x40203264))))
            .border(1.dp, Blue.copy(alpha = 0.45f), RoundedCornerShape(16.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("⬆️", fontSize = 20.sp)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    if (u.version.isNotEmpty()) "Новая версия ${u.version}" else "Обновление",
                    color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold
                )
                val sub = when {
                    u.progress >= 0f -> "Скачиваю… ${(u.progress * 100).toInt()}%"
                    u.note.isNotEmpty() -> u.note
                    u.size > 0 -> "${u.size / 1_048_576} МБ"
                    else -> ""
                }
                if (sub.isNotEmpty()) Text(sub, color = TextSoft, fontSize = 12.5.sp)
            }
        }
        if (u.version.isNotEmpty() && u.progress < 0f) {
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "Обновить здесь", color = Ink, fontSize = 13.5.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
                    modifier = Modifier.weight(1f).clip(RoundedCornerShape(12.dp))
                        .background(Brush.horizontalGradient(listOf(BlueLight, BlueMid)))
                        .clickable { AppUpdate.installHere(ctx) }.padding(vertical = 10.dp)
                )
                Text(
                    "Через браузер", color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                    modifier = Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(Glass)
                        .border(1.dp, Blue.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
                        .clickable { AppUpdate.openInBrowser(ctx) }.padding(vertical = 10.dp)
                )
            }
            Text(
                "«Здесь» — быстрее, но Google Play может предупредить: нажмите «Всё равно установить». " +
                    "Через браузер — без предупреждения.",
                color = TextDim, fontSize = 11.5.sp, modifier = Modifier.padding(top = 8.dp)
            )
        }
    }
    if (u.note.isNotEmpty() && u.version.isEmpty()) {
        LaunchedEffect(u.note) {
            delay(8_000)
            AppUpdate.onStatus("")
        }
    }
}

@Composable
private fun Metric(k: String, v: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(k, color = TextDim, fontSize = 12.sp)
        Text(v, color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun Tool(icon: String, title: String, sub: String, right: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 8.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(16.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(38.dp).clip(RoundedCornerShape(12.dp)).background(BlueMid.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) {
            Text(icon, fontSize = 18.sp)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(sub, color = TextDim, fontSize = 12.sp, maxLines = 2)
        }
        if (right.isNotEmpty()) Text(right, color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

// ---------------------------------------------------------------- приложения мимо VPN

private data class AppItem(val pkg: String, val label: String)

@Composable
private fun AppsScreen(data: Data, back: () -> Unit, onChange: () -> Unit) {
    val ctx = LocalContext.current
    val apps by produceState(initialValue = emptyList<AppItem>()) {
        value = withContext(Dispatchers.IO) {
            val pm = ctx.packageManager
            val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            pm.queryIntentActivities(launcher, 0)
                .map { it.activityInfo.packageName to it.loadLabel(pm).toString() }
                .filter { it.first != ctx.packageName }
                .distinctBy { it.first }
                .map { AppItem(it.first, it.second) }
                .sortedBy { it.label.lowercase() }
        }
    }
    Page("Приложения мимо VPN", "Отмеченные приложения ходят в интернет напрямую. Изменения применяются сразу.", back) {
        ToggleRow("🏦", "Банки, Госуслуги, маркетплейсы (${RuApps.PACKAGES.size})", data.ruApps) {
            Repo.setRuApps(!data.ruApps)
            onChange()
        }
        Spacer(Modifier.height(8.dp))
        if (apps.isEmpty()) Text("Загружаю список…", color = TextDim, fontSize = 13.sp)
        for (a in apps) {
            val fromRu = data.ruApps && a.pkg in RuApps.PACKAGES
            val on = fromRu || a.pkg in data.bypass
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(enabled = !fromRu) {
                        Repo.toggleBypass(a.pkg)
                        onChange()
                    }
                    .padding(vertical = 6.dp, horizontal = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(a.label, color = TextMain, fontSize = 14.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (fromRu) Text("из списка российских", color = TextDim, fontSize = 11.5.sp)
                }
                Switch(
                    checked = on, enabled = !fromRu, onCheckedChange = { Repo.toggleBypass(a.pkg); onChange() },
                    colors = SwitchDefaults.colors(checkedThumbColor = TextMain, checkedTrackColor = BlueDeep,
                        uncheckedThumbColor = TextDim, uncheckedTrackColor = Color(0xFF1A2233), uncheckedBorderColor = GlassLine)
                )
            }
        }
    }
}

// ---------------------------------------------------------------- приветствие

@Composable
private fun Welcome(data: Data, onOpen: (String) -> Unit) {
    val ctx = LocalContext.current
    var link by remember { mutableStateOf("") }
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(56.dp))
        Image(painterResource(R.mipmap.ic_launcher_foreground), contentDescription = null, modifier = Modifier.size(150.dp))
        Text("Arise VPN", color = TextMain, fontSize = 32.sp, fontWeight = FontWeight.Bold)
        Text("Быстрый и приватный интернет без границ", color = TextSoft, fontSize = 15.sp, textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 6.dp))
        Spacer(Modifier.height(34.dp))
        Big("✦ Попробовать бесплатно", gold = true) { onOpen("https://t.me/$BOT?start=trial") }
        Spacer(Modifier.height(10.dp))
        Big("У меня есть подписка — открыть бота", gold = false) { onOpen("https://t.me/$BOT") }
        Spacer(Modifier.height(26.dp))
        Text("или вставьте ссылку подписки из бота", color = TextDim, fontSize = 13.sp)
        Field(link, "Ссылка подписки", Modifier.padding(top = 8.dp)) { link = it }
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Small("📋 Вставить", Modifier.weight(1f)) {
                val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                link = cm.primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString()?.trim() ?: ""
                if (link.startsWith("http")) Repo.refresh(link)
            }
            Small(if (data.loading) "Загружаю…" else "Добавить", Modifier.weight(1f)) {
                if (link.startsWith("http")) Repo.refresh(link)
                else Toast.makeText(ctx, "Вставьте ссылку подписки из бота", Toast.LENGTH_SHORT).show()
            }
        }
        if (data.error.isNotEmpty()) Text(data.error, color = Red, fontSize = 13.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 12.dp))
        Spacer(Modifier.height(30.dp))
    }
}

// ---------------------------------------------------------------- общие кусочки

@Composable
private fun Field(value: String, label: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value, onValueChange = onChange, singleLine = true,
        placeholder = { Text(label, color = TextDim) },
        shape = RoundedCornerShape(14.dp),
        modifier = modifier.fillMaxWidth(),
        colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = TextMain, unfocusedTextColor = TextMain,
            focusedBorderColor = Blue.copy(alpha = 0.6f), unfocusedBorderColor = GlassLine,
            focusedContainerColor = Glass, unfocusedContainerColor = Glass, cursorColor = Blue
        )
    )
}

@Composable
private fun Big(text: String, gold: Boolean, onClick: () -> Unit) {
    val m = Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp))
    Text(
        text, color = if (gold) Ink else TextMain, fontSize = 16.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
        modifier = (if (gold) m.background(Brush.horizontalGradient(listOf(BlueLight, BlueMid)))
        else m.background(Glass).border(1.dp, Blue.copy(alpha = 0.35f), RoundedCornerShape(16.dp)))
            .clickable(onClick = onClick)
            .padding(vertical = 15.dp)
    )
}

@Composable
private fun Small(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Text(
        text, color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(14.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp)
    )
}

/** «🇵🇱 Польша» → флаг и название. Если флага нет — глобус. */
private fun splitFlag(name: String): Pair<String, String> {
    val first = name.substringBefore(" ")
    val emoji = name.contains(" ") && first.isNotEmpty() && first.none { it.isLetterOrDigit() }
    return if (emoji) first to name.substringAfter(" ") else "🌐" to name
}

private fun pingColor(ping: Long): Color = when {
    ping <= 0 -> if (ping < 0) Red else TextDim
    ping < 150 -> Green
    ping < 400 -> Amber
    else -> Red
}

private fun duration(millis: Long): String {
    val s = millis.coerceAtLeast(0L) / 1000
    return "%02d:%02d:%02d".format(s / 3600, (s / 60) % 60, s % 60)
}

private fun mbit(bps: Long): String = "%.1f".format(bps * 8.0 / 1_000_000.0)

private fun bytes(b: Long): String = when {
    b >= 1L shl 30 -> "%.1f ГБ".format(b / (1L shl 30).toDouble())
    b >= 1L shl 20 -> "%.0f МБ".format(b / (1L shl 20).toDouble())
    else -> "%.0f КБ".format(b / 1024.0)
}

private fun date(epochSeconds: Long, pattern: String = "dd.MM.yyyy"): String =
    SimpleDateFormat(pattern, Locale.getDefault()).format(Date(epochSeconds * 1000))

/** Ссылка в бота из подписки (support-url), а если её нет — на @AriseVPN_bot. */
private fun botLink(botUrl: String, start: String): String =
    (botUrl.ifBlank { "https://t.me/$BOT" }).substringBefore("?") + "?start=" + start
