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
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
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
internal val Ink = Color(0xFF04070F)
internal val Night = Color(0xFF071433)
internal val Deep = Color(0xFF0B2A6B)
internal val Glass = Color(0x0BFFFFFF)
internal val GlassLine = Color(0x14FFFFFF)
internal val Sheet = Color(0xFF0D1526)
internal val Blue = Color(0xFF8CB8FF)
internal val BlueMid = Color(0xFF6FA4FF)
internal val BlueLight = Color(0xFFCFE0FF)
internal val BlueDeep = Color(0xFF2F5FC8)
internal val TextMain = Color(0xFFEAF1FF)
internal val TextSoft = Color(0xFF9FB0D3)
internal val TextDim = Color(0xFF7F8DAB)
internal val Green = Color(0xFF6FD08C)
internal val Amber = Color(0xFFE8C46A)
internal val Red = Color(0xFFE57373)

private const val BOT = "AriseVPN_bot"

private enum class Screen { HOME, MODES, TOOLS, APPS, DNS, CHAT }

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Repo.app = applicationContext
        Repo.load()
        takeLink(intent)
        setContent {
            // шрифт Inter для всего приложения
            androidx.compose.material3.ProvideTextStyle(androidx.compose.ui.text.TextStyle(fontFamily = Inter)) { Root() }
        }
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
        // VPN выключили — сразу меряем страны заново (без VPN), а не через 5 минут
        var lastStatus by remember { mutableStateOf(vpn.status) }
        LaunchedEffect(vpn.status) {
            if (vpn.status == Status.STOPPED && lastStatus == Status.RUNNING) Repo.pingAll()
            lastStatus = vpn.status
        }
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
                screen == Screen.CHAT -> ChatRoot(back = { screen = Screen.HOME })
                screen == Screen.APPS -> AppsScreen(data, back = { screen = Screen.TOOLS }, onChange = apply)
                else -> HomeScreen(
                    vpn, data, onToggle = toggle, onOpen = { open(it) },
                    openSheet = { sheet = true }, openModes = { screen = Screen.MODES },
                    onMode = { m -> Repo.setMode(m); apply() },
                    openTools = { screen = Screen.TOOLS }, onRuApps = { Repo.setRuApps(!data.ruApps); apply() },
                    openChat = { screen = Screen.CHAT }
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
internal fun Backdrop(on: Boolean) {
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
        // Звёзды: неподвижные, тихо мерцают (как на образцах)
        for (i in 0 until 70) {
            val seed = ((i * 7919 + 13) % 1000) / 1000f
            val x = ((i * 0.6180339f + seed * 0.37f) % 1f) * size.width
            val y = ((i * 0.4142136f + seed * 0.21f) % 1f) * size.height
            val tw = 0.5f + 0.5f * kotlin.math.sin((time * 6.2832f * (1f + seed * 2f)) + seed * 10f)
            drawCircle(Color(0xFFBFD8FF).copy(alpha = (0.10f + 0.35f * seed) * (0.4f + 0.6f * tw)),
                radius = 0.6.dp.toPx() + seed * 1.1.dp.toPx(), center = Offset(x, y))
        }
        // Светящаяся дуга внизу экрана
        val arcW = size.width * 1.6f
        val top = size.height - size.width * 0.18f
        for (k in 0..5) {
            drawArc(
                Color(0xFF3D7BFF).copy(alpha = (0.32f - k * 0.05f) * (0.6f + glow)), 200f, 140f, false,
                Offset((size.width - arcW) / 2f, top - k * 3.dp.toPx()), androidx.compose.ui.geometry.Size(arcW, size.width * 0.9f),
                style = Stroke((2 + k * 3).dp.toPx())
            )
        }
    }
}

// ---------------------------------------------------------------- главный экран

@Composable
internal fun Logo(size: Dp = 30.dp) {
    AriseMark(size)
}

@Composable
internal fun PowerIcon(color: Color, size: Dp) {
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
internal fun ToggleRow(icon: String, text: String, on: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
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
internal fun FlagCircle(flag: String, size: Dp) {
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
internal fun Bars(ping: Long) {
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
    // Открыли список — свежий замер, если последний был больше минуты назад
    LaunchedEffect(open) { if (open) Repo.pingIfStale(60_000L) }
    AnimatedVisibility(open, enter = slideInVertically { it }, exit = slideOutVertically { it }) {
        var query by remember { mutableStateOf("") }
        var byPing by remember { mutableStateOf(false) }
        Box(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .fillMaxHeight(0.86f)
                    .clip(RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp))
                    .background(Brush.verticalGradient(listOf(Color(0xFF0E1A36), Color(0xFF060B18))))
                    .border(1.dp, Blue.copy(alpha = 0.45f), RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp))
                    // касания по самому окну не должны закрывать его (под ним — затемнение, которое закрывает)
                    .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { }
                    .navigationBarsPadding()
                    .padding(horizontal = 16.dp)
            ) {
                Box(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp), contentAlignment = Alignment.Center) {
                    Box(Modifier.width(44.dp).height(5.dp).clip(RoundedCornerShape(3.dp)).background(Blue.copy(alpha = 0.7f)))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(40.dp).clip(CircleShape).glass(20.dp), contentAlignment = Alignment.Center) {
                        LineIcon(Ico.GLOBE, 22.dp, BlueLight)
                    }
                    Text("Выберите страну", color = TextMain, fontSize = 22.sp, fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f).padding(start = 12.dp))
                    Box(Modifier.size(40.dp).clip(CircleShape).glass(20.dp).clickable(onClick = close), contentAlignment = Alignment.Center) {
                        LineIcon(Ico.CLOSE, 16.dp, TextMain)
                    }
                }
                Row(
                    Modifier.fillMaxWidth().padding(top = 14.dp).glass(22.dp).padding(start = 14.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    LineIcon(Ico.SEARCH, 20.dp, Blue)
                    OutlinedTextField(
                        value = query, onValueChange = { query = it.take(40) }, singleLine = true,
                        placeholder = { Text("Поиск страны", color = TextDim) },
                        modifier = Modifier.weight(1f),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextMain, unfocusedTextColor = TextMain, cursorColor = Blue,
                            focusedBorderColor = Color.Transparent, unfocusedBorderColor = Color.Transparent,
                        )
                    )
                }
                // Все страны без связи при выключенном VPN — показываем причину (для разбора)
                if (vpn.status != Status.RUNNING && data.pingError.isNotEmpty() &&
                    data.pings.isNotEmpty() && data.pings.values.none { it > 0 } && data.measuring.isEmpty()
                ) Text("Замер без VPN: ${data.pingError}", color = TextDim, fontSize = 11.5.sp,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 4.dp))
                val list = data.servers.filter { query.isBlank() || it.name.contains(query.trim(), ignoreCase = true) }
                val special = list.filter { it.name.startsWith("🚀") || it.name.startsWith("🎮") }
                var rest = list - special.toSet()
                if (byPing) {
                    // по пингу: быстрые сверху, без замера и без связи — в конце
                    rest = rest.sortedBy { val p = data.pings[it.name] ?: 0L; if (p > 0) p else Long.MAX_VALUE }
                }
                LazyColumn(Modifier.fillMaxSize()) {
                    if (special.isNotEmpty()) {
                        item { Group("Рекомендуем") }
                        item {
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                for (s in special) RecommendTile(s, data, Modifier.weight(1f), onPick)
                            }
                        }
                    }
                    item {
                        Row(Modifier.fillMaxWidth().padding(top = 14.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("ВСЕ СТРАНЫ", color = BlueLight, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                                letterSpacing = 1.sp, modifier = Modifier.weight(1f).padding(start = 4.dp))
                            Text(
                                if (byPing) "⇅ По пингу" else "⇅ По списку", color = TextSoft, fontSize = 12.5.sp,
                                modifier = Modifier.clip(RoundedCornerShape(50)).glass(20.dp)
                                    .clickable { byPing = !byPing }.padding(horizontal = 12.dp, vertical = 7.dp)
                            )
                        }
                    }
                    items(rest) { s -> CountryRow(s, vpn, data, onPick) }
                    item { Spacer(Modifier.height(20.dp)) }
                }
            }
        }
    }
}

@Composable
private fun Group(text: String) {
    Text(text.uppercase(), color = BlueLight, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp,
        modifier = Modifier.padding(start = 4.dp, top = 16.dp, bottom = 8.dp))
}

/** «Лучший сервер» / «Игры» — две плитки в ряд. */
@Composable
private fun RecommendTile(s: Server, data: Data, modifier: Modifier, onPick: (String) -> Unit) {
    val (icon, title) = splitFlag(s.name)
    val selected = s.name == data.selected
    val note = if (s.name.startsWith("🚀")) "Выбирает самый быстрый сам" else "Напрямую, ровный пинг"
    Row(
        modifier.glass(20.dp, glow = selected).clickable { onPick(s.name) }.padding(start = 10.dp, end = 8.dp, top = 12.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier.size(42.dp).clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0x552F6BFF), Color(0x110E1A36)))),
            contentAlignment = Alignment.Center
        ) { EmojiIcon(icon, 26.dp) }
        Column(Modifier.weight(1f).padding(start = 8.dp)) {
            Text(title, color = TextMain, fontSize = 14.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(note, color = TextSoft, fontSize = 11.5.sp, maxLines = 2, lineHeight = 14.sp)
        }
        if (selected) LineIcon(Ico.CHECK, 16.dp, Blue) else LineIcon(Ico.CHEVRON, 14.dp, Blue)
    }
}

@Composable
private fun CountryRow(s: Server, vpn: VpnUi, data: Data, onPick: (String) -> Unit) {
    val (flag, title) = splitFlag(s.name)
    val selected = s.name == data.selected
    val ping = if (vpn.status == Status.RUNNING && vpn.server == s.name && vpn.ping != 0L) vpn.ping else data.pings[s.name] ?: 0L
    val busy = s.name in data.measuring
    val note = if (s.name.contains("🇷🇺") || s.name.contains("Обход", true)) "Для белых списков" else ""
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .glass(20.dp, glow = selected)
            .clickable { onPick(s.name) }
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        FlagCircle(flag, 40.dp)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (note.isNotEmpty()) Text(note, color = TextDim, fontSize = 12.sp)
        }
        PingLabel(ping, busy = busy)
        Spacer(Modifier.width(8.dp))
        Bars(if (busy && ping < 0) 0L else ping)
        Spacer(Modifier.width(10.dp))
        if (selected) {
            Box(Modifier.size(26.dp).clip(CircleShape).background(BlueDeep).border(1.dp, Blue, CircleShape), contentAlignment = Alignment.Center) {
                LineIcon(Ico.CHECK, 16.dp, Color.White)
            }
        } else LineIcon(Ico.CHEVRON, 16.dp, Blue)
    }
}

@Composable
private fun PingLabel(ping: Long, busy: Boolean = false) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(pingColor(if (busy && ping < 0) 0L else ping)))
        Text(
            when {
                ping > 0 -> " $ping мс"
                busy -> " …"           // меряется прямо сейчас: старое «нет связи» не показываем
                ping < 0 -> " нет связи"
                else -> " —"
            },
            color = if (ping < 0 && !busy) Red else TextMain, fontSize = 14.sp
        )
    }
}

// ---------------------------------------------------------------- режимы

@Composable
internal fun Page(title: String, lead: String, back: () -> Unit, content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 14.dp)) {
            Box(
                Modifier.size(46.dp).clip(CircleShape).glass(23.dp).clickable(onClick = back),
                contentAlignment = Alignment.Center
            ) { LineIcon(Ico.BACK, 20.dp, BlueLight) }
            Text(title, color = TextMain, fontSize = 26.sp, fontWeight = FontWeight.Bold, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(start = 16.dp))
        }
        if (lead.isNotEmpty()) Text(lead, color = TextSoft, fontSize = 14.sp, lineHeight = 19.sp,
            modifier = Modifier.padding(start = 4.dp, top = 16.dp, bottom = 16.dp))
        else Spacer(Modifier.height(18.dp))
        content()
        Spacer(Modifier.height(28.dp))
    }
}

@Composable
private fun ModesScreen(data: Data, back: () -> Unit, onPick: (Mode) -> Unit) {
    Page("Режим соединения", "Каждый режим по-настоящему меняет настройки VPN. Чем-то всегда жертвуем — честно пишем, чем.", back) {
        for (m in Mode.entries) {
            val sel = m == data.mode
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp)
                    .glass(24.dp, glow = sel)
                    .clickable { onPick(m) }
                    .padding(14.dp),
                verticalAlignment = Alignment.Top
            ) {
                Box(
                    Modifier.size(58.dp).clip(RoundedCornerShape(18.dp))
                        .background(Brush.radialGradient(listOf(Color(0x662F6BFF), Color(0x220E1A36))))
                        .border(1.dp, Color(0x447AAEFF), RoundedCornerShape(18.dp)),
                    contentAlignment = Alignment.Center
                ) { EmojiIcon(m.emoji, 34.dp) }
                Column(Modifier.weight(1f).padding(start = 14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(m.title, color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                        if (m == Mode.BALANCE) Text(
                            "⭐ Рекомендуем", color = BlueLight, fontSize = 11.5.sp,
                            modifier = Modifier.padding(start = 8.dp).clip(RoundedCornerShape(50))
                                .background(BlueMid.copy(alpha = 0.18f)).border(1.dp, Blue.copy(alpha = 0.4f), RoundedCornerShape(50))
                                .padding(horizontal = 8.dp, vertical = 3.dp)
                        )
                        Spacer(Modifier.weight(1f))
                        if (sel) Box(
                            Modifier.size(28.dp).clip(CircleShape).background(BlueDeep).border(1.dp, Blue, CircleShape),
                            contentAlignment = Alignment.Center
                        ) { LineIcon(Ico.CHECK, 16.dp, Color.White) }
                        else LineIcon(Ico.CHEVRON, 16.dp, Blue)
                    }
                    Text(m.desc, color = TextSoft, fontSize = 13.5.sp, lineHeight = 18.sp, modifier = Modifier.padding(top = 4.dp))
                    if (m.plus.isNotEmpty() || m.minus.isNotEmpty()) {
                        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (m.plus.isNotEmpty()) Chip("＋ ${m.plus}", Green)
                            if (m.minus.isNotEmpty()) Chip("− ${m.minus}", Color(0xFFF0A050))
                        }
                    }
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 4.dp).glass(20.dp).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            LineIcon(Ico.INFO, 24.dp, Blue)
            Text("Выбранный режим можно изменить в любое время", color = TextSoft, fontSize = 13.5.sp,
                modifier = Modifier.padding(start = 12.dp))
        }
    }
}

/** Метка «плюс/минус» у режима. */
@Composable
private fun Chip(text: String, color: Color) {
    Text(
        text, color = color, fontSize = 12.sp, maxLines = 1,
        modifier = Modifier.clip(RoundedCornerShape(50)).background(color.copy(alpha = 0.10f))
            .border(1.dp, color.copy(alpha = 0.35f), RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 5.dp)
    )
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
            Modifier.fillMaxWidth().glass(26.dp, glow = true).padding(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Gauge(if (speed.running) 0.75f else if (speed.downMbps > 0) 0.6f else 0.3f, Modifier.size(84.dp))
                Column(Modifier.weight(1f).padding(start = 14.dp)) {
                    Text("Тест скорости", color = TextMain, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text(if (speed.running) speed.stage.ifBlank { "Проверяю…" } else "Проверьте ваше соединение",
                        color = TextSoft, fontSize = 13.sp)
                    Text(
                        if (speed.running) "Идёт проверка…" else "▶  Начать", color = Color.White, fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                        modifier = Modifier.padding(top = 10.dp).fillMaxWidth().clip(RoundedCornerShape(50))
                            .background(Brush.verticalGradient(listOf(Color(0xFF3D7BFF), Color(0xFF1F4FD6))))
                            .border(1.dp, Color(0x997AAEFF), RoundedCornerShape(50))
                            .clickable(enabled = !speed.running) { Repo.speedTest() }
                            .padding(vertical = 11.dp)
                    )
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 14.dp).glass(18.dp).padding(vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically
            ) {
                SpeedMetric(Ico.DOWN, "Загрузка", if (speed.downMbps > 0) "%.1f Мбит/с".format(speed.downMbps) else "—")
                SpeedMetric(Ico.UP, "Отдача", if (speed.upMbps > 0) "%.1f Мбит/с".format(speed.upMbps) else "—")
                SpeedMetric(Ico.CLOCK, "Пинг", if (speed.ping > 0) "${speed.ping} мс" else "—",
                    if (speed.ping > 0) "джиттер ${speed.jitter} мс" else "")
            }
            if (speed.error.isNotEmpty()) Text(speed.error, color = Red, fontSize = 12.5.sp, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        }
        Spacer(Modifier.height(14.dp))
        Tool("🛡", "Защита от утечек", "Без VPN интернет блокируется", "Настроить", onLeak)
        Tool("📱", "Приложения мимо VPN", "Банки, Госуслуги и свои",
            "${(if (data.ruApps) RuApps.PACKAGES.size else 0) + data.bypass.size} ›", onApps)
        Tool("🌐", "DNS", "${data.dns.ip} · ${data.dns.note}", "${data.dns.title} ›", onDns)
        Tool("⏻", "Автоподключение", "При включении телефона", if (data.autoConnect) "Вкл" else "Выкл") {
            Repo.setAutoConnect(!data.autoConnect)
        }
        Tool("⚡", "Кнопка в шторке", "Включать VPN, не открывая приложение", "Добавить", onTile)
        val notifyOn = rememberNotifyEnabled()
        val askNotify = rememberNotifyAsk()
        Tool("🔔", "Уведомления", if (notifyOn) "Разрешены" else "Выключены в настройках телефона",
            if (notifyOn) "Настроить" else "Включить") { if (notifyOn) Notify.openSettings(ctx) else askNotify() }
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
        Tool("👑", "Обновить подписку", if (data.loading) "Обновляю…" else "Страны и срок — с сервера", "") { Repo.refresh() }
        Tool("↩", "Сменить подписку", "Удалить эту и добавить другую", "", onForget)
        Text("Arise VPN ${BuildConfig.VERSION_NAME}", color = TextDim, fontSize = 12.sp, modifier = Modifier.fillMaxWidth().padding(top = 10.dp), textAlign = TextAlign.Center)
    }
}

/** Циферблат теста скорости. */
@Composable
private fun Gauge(level: Float, modifier: Modifier) {
    Canvas(modifier) {
        val w = size.minDimension * 0.09f
        val inset = w
        val arc = androidx.compose.ui.geometry.Size(size.width - inset * 2, size.height - inset * 2)
        drawArc(Color(0x332F6BFF), 140f, 260f, false, Offset(inset, inset), arc, style = Stroke(w, cap = StrokeCap.Round))
        drawArc(Brush.sweepGradient(listOf(Color(0xFF2F6BFF), Color(0xFF8CB8FF), Color(0xFF2F6BFF))), 140f, 260f * level, false,
            Offset(inset, inset), arc, style = Stroke(w, cap = StrokeCap.Round))
        val a = Math.toRadians((140.0 + 260.0 * level))
        val r = size.minDimension * 0.30f
        drawLine(Color(0xFF8CB8FF), center, Offset(center.x + (kotlin.math.cos(a) * r).toFloat(), center.y + (kotlin.math.sin(a) * r).toFloat()),
            w * 0.8f, StrokeCap.Round)
        drawCircle(Color(0xFF8CB8FF), w * 0.9f, center)
    }
}

@Composable
private fun SpeedMetric(ico: Ico, k: String, v: String, sub: String = "") {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        LineIcon(ico, 22.dp, Blue)
        Text(k, color = TextSoft, fontSize = 12.5.sp, modifier = Modifier.padding(top = 4.dp))
        Text(v, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        if (sub.isNotEmpty()) Text(sub, color = TextDim, fontSize = 10.5.sp)
    }
}

/** Плашка «Доступна новая версия» на главном экране: обновиться внутри или через браузер. */
@Composable
internal fun UpdateCard() {
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
internal fun Tool(icon: String, title: String, sub: String, right: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 10.dp)
            .glass(22.dp)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier.size(46.dp).clip(RoundedCornerShape(14.dp))
                .background(Brush.radialGradient(listOf(Color(0x552F6BFF), Color(0x1A0E1A36))))
                .border(1.dp, Color(0x337AAEFF), RoundedCornerShape(14.dp)),
            contentAlignment = Alignment.Center
        ) { EmojiIcon(icon, 24.dp) }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text(sub, color = TextSoft, fontSize = 12.5.sp, maxLines = 2)
        }
        when {
            right == "Вкл" || right == "Выкл" -> MiniSwitch(right == "Вкл")
            right.endsWith("›") -> {
                val v = right.removeSuffix("›").trim()
                if (v.isNotEmpty()) Text(v, color = TextMain, fontSize = 14.sp, modifier = Modifier.padding(end = 6.dp))
                LineIcon(Ico.CHEVRON, 16.dp, Blue)
            }
            right.isEmpty() -> LineIcon(Ico.CHEVRON, 16.dp, Blue)
            // действие — кнопка-обводка
            else -> Text(
                right, color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                modifier = Modifier.clip(RoundedCornerShape(50)).border(1.dp, Blue.copy(alpha = 0.6f), RoundedCornerShape(50))
                    .background(BlueMid.copy(alpha = 0.10f)).padding(horizontal = 14.dp, vertical = 8.dp)
            )
        }
    }
}

/** Переключатель в строке (вся строка нажимается). */
@Composable
private fun MiniSwitch(on: Boolean) {
    Box(
        Modifier.width(50.dp).height(28.dp).clip(RoundedCornerShape(50))
            .background(if (on) Brush.horizontalGradient(listOf(Color(0xFF1F4FD6), Color(0xFF3D7BFF)))
            else Brush.horizontalGradient(listOf(Color(0xFF1A2233), Color(0xFF1A2233))))
            .border(1.dp, if (on) Color(0x997AAEFF) else GlassLine, RoundedCornerShape(50))
            .padding(3.dp),
        contentAlignment = if (on) Alignment.CenterEnd else Alignment.CenterStart
    ) { Box(Modifier.size(22.dp).clip(CircleShape).background(if (on) Color.White else TextDim)) }
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
    var manual by remember { mutableStateOf(false) }  // поле для ссылки — если в буфере её не оказалось
    Column(
        Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(28.dp))
        AriseMark(96.dp)
        Text("Arise VPN", color = TextMain, fontSize = 38.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 14.dp))
        Text("Быстрый и приватный интернет без границ", color = Blue, fontSize = 15.5.sp, textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp))
        Globe(Modifier.padding(vertical = 22.dp).size(260.dp), on = true)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            Feature(Ico.BOLT, "Высокая\nскорость")
            Feature(null, "Без логов")
            Feature(Ico.GLOBE, "Десятки\nстран")
        }
        Spacer(Modifier.height(24.dp))
        Big("Попробовать бесплатно  ›", gold = true) { onOpen("https://t.me/$BOT?start=trial") }
        Spacer(Modifier.height(12.dp))
        Big(if (data.loading) "Загружаю…" else "🔗  Вставить ссылку подписки", gold = false) {
            val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip?.getItemAt(0)?.coerceToText(ctx)?.toString()?.trim() ?: ""
            if (clip.startsWith("http")) {
                link = clip
                Repo.refresh(clip)
            } else {
                manual = true
                Toast.makeText(ctx, "Скопируйте ссылку подписки в боте или вставьте её ниже", Toast.LENGTH_LONG).show()
            }
        }
        if (manual) {
            Field(link, "Ссылка подписки", Modifier.padding(top = 12.dp)) { link = it }
            Spacer(Modifier.height(8.dp))
            Small(if (data.loading) "Загружаю…" else "Добавить", Modifier.fillMaxWidth()) {
                if (link.startsWith("http")) Repo.refresh(link)
                else Toast.makeText(ctx, "Вставьте ссылку подписки из бота", Toast.LENGTH_SHORT).show()
            }
        }
        if (data.error.isNotEmpty()) Text(data.error, color = Red, fontSize = 13.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 12.dp))
        Row(
            Modifier.padding(top = 20.dp).clip(RoundedCornerShape(14.dp)).clickable { onOpen("https://t.me/$BOT") }
                .padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(34.dp).clip(CircleShape).glass(17.dp), contentAlignment = Alignment.Center) {
                LineIcon(Ico.SEND, 18.dp, BlueLight)
            }
            Text("Подписку можно купить в Telegram-боте @$BOT", color = TextSoft, fontSize = 13.sp,
                modifier = Modifier.padding(start = 10.dp))
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun Feature(ico: Ico?, text: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(100.dp)) {
        Box(Modifier.size(56.dp).glass(18.dp), contentAlignment = Alignment.Center) {
            LineIcon(ico ?: Ico.SHIELD, 28.dp, Blue)
        }
        Text(text, color = TextMain, fontSize = 14.sp, textAlign = TextAlign.Center, lineHeight = 18.sp,
            modifier = Modifier.padding(top = 8.dp))
    }
}

// ---------------------------------------------------------------- общие кусочки

@Composable
internal fun Field(value: String, label: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
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
internal fun Big(text: String, gold: Boolean, onClick: () -> Unit) {
    // gold — главная кнопка (имя осталось с прошлого стиля): синяя со свечением; иначе — стеклянная
    val shape = RoundedCornerShape(50)
    val m = Modifier.fillMaxWidth()
        .then(if (gold) Modifier.shadow(14.dp, shape, ambientColor = BlueMid, spotColor = BlueMid) else Modifier)
        .clip(shape)
    Text(
        text, color = if (gold) Color.White else TextMain, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
        modifier = (if (gold) m.background(Brush.verticalGradient(listOf(Color(0xFF3D7BFF), Color(0xFF1F4FD6))))
            .border(1.dp, Color(0xAA9CC2FF), shape)
        else m.background(Color(0x1A223A6E)).border(1.dp, Blue.copy(alpha = 0.45f), shape))
            .clickable(onClick = onClick)
            .padding(vertical = 16.dp)
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
internal fun splitFlag(name: String): Pair<String, String> {
    val first = name.substringBefore(" ")
    val emoji = name.contains(" ") && first.isNotEmpty() && first.none { it.isLetterOrDigit() }
    return if (emoji) first to name.substringAfter(" ") else "🌐" to name
}

internal fun pingColor(ping: Long): Color = when {
    ping <= 0 -> if (ping < 0) Red else TextDim
    ping < 150 -> Green
    ping < 400 -> Amber
    else -> Red
}

internal fun duration(millis: Long): String {
    val s = millis.coerceAtLeast(0L) / 1000
    return "%02d:%02d:%02d".format(s / 3600, (s / 60) % 60, s % 60)
}

internal fun mbit(bps: Long): String = "%.1f".format(bps * 8.0 / 1_000_000.0)

internal fun bytes(b: Long): String = when {
    b >= 1L shl 30 -> "%.1f ГБ".format(b / (1L shl 30).toDouble())
    b >= 1L shl 20 -> "%.0f МБ".format(b / (1L shl 20).toDouble())
    else -> "%.0f КБ".format(b / 1024.0)
}

internal fun date(epochSeconds: Long, pattern: String = "dd.MM.yyyy"): String =
    SimpleDateFormat(pattern, Locale.getDefault()).format(Date(epochSeconds * 1000))

/** Ссылка в бота из подписки (support-url), а если её нет — на @AriseVPN_bot. */
internal fun botLink(botUrl: String, start: String): String =
    (botUrl.ifBlank { "https://t.me/$BOT" }).substringBefore("?") + "?start=" + start
