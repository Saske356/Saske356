package io.github.saske356.arise

import androidx.compose.foundation.layout.offset
import androidx.compose.ui.graphics.drawscope.rotate
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
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.animation.AnimatedContent
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
internal val Glass = Color(0x99081026)
internal val GlassLine = Color(0x598CB9FF)
internal val Sheet = Color(0xFF0D1526)
internal val Blue = Color(0xFF8CB8FF)
internal val BlueMid = Color(0xFF6FA4FF)
internal val BlueLight = Color(0xFFCFE0FF)
internal val BlueDeep = Color(0xFF2F5FC8)
internal val TextMain = Color(0xFFFFFFFF)
internal val TextSoft = Color(0xFFC9D8F5)
internal val TextDim = Color(0xFF93A6CC)
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

        // Прошлый запуск упал — показываем причину, чтобы её можно было прислать
        var crash by remember {
            mutableStateOf(ctx.getSharedPreferences(AriseApp.CRASH_PREFS, Context.MODE_PRIVATE).getString("text", "") ?: "")
        }
        if (crash.isNotEmpty()) {
            val clear = {
                ctx.getSharedPreferences(AriseApp.CRASH_PREFS, Context.MODE_PRIVATE).edit().clear().apply()
                crash = ""
            }
            androidx.compose.material3.AlertDialog(
                onDismissRequest = clear,
                containerColor = Color(0xFF0E1C3E),
                title = { Text("Приложение упало", color = TextMain) },
                text = {
                    Text("Скопируйте текст и пришлите разработчику:\n\n" + crash.take(900), color = TextSoft, fontSize = 11.sp,
                        modifier = Modifier.verticalScroll(rememberScrollState()))
                },
                confirmButton = {
                    androidx.compose.material3.TextButton(onClick = {
                        val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        cm.setPrimaryClip(android.content.ClipData.newPlainText("Ошибка Arise", crash))
                        Toast.makeText(ctx, "Скопировано", Toast.LENGTH_SHORT).show()
                        clear()
                    }) { Text("Скопировать", color = Blue) }
                },
                dismissButton = { androidx.compose.material3.TextButton(onClick = clear) { Text("Закрыть", color = TextSoft) } }
            )
        }
        Box(Modifier.fillMaxSize()) {
            Backdrop(vpn.status == Status.RUNNING)
            // экраны сменяются плавно: вперёд — сдвиг влево, назад — вправо
            val key = if (data.servers.isEmpty()) "WELCOME" else screen.name
            AnimatedContent(
                targetState = key,
                transitionSpec = {
                    fun depth(k: String) = when (k) { "HOME", "WELCOME" -> 0; "APPS", "DNS" -> 2; else -> 1 }
                    val dir = if (depth(targetState) >= depth(initialState)) 1 else -1
                    (slideInHorizontally(tween(320, easing = FastOutSlowInEasing)) { it / 5 * dir } + fadeIn(tween(280))) togetherWith
                        (slideOutHorizontally(tween(320, easing = FastOutSlowInEasing)) { -it / 5 * dir } + fadeOut(tween(200)))
                },
                label = "screens"
            ) { k ->
            when {
                k == "WELCOME" -> Welcome(data) { open(it) }
                k == "MODES" -> ModesScreen(data, back = { screen = Screen.HOME }) { m ->
                    Repo.setMode(m)
                    apply()
                }
                k == "TOOLS" -> ToolsScreen(
                    data, back = { screen = Screen.HOME },
                    onApps = { screen = Screen.APPS }, onLeak = { leakProtection() }, onTile = { addTile() },
                    onDns = { screen = Screen.DNS },
                    onForget = {
                        if (VpnState.flow.value.status != Status.STOPPED) AriseVpnService.stop(ctx)
                        Repo.forget()
                        screen = Screen.HOME
                    }
                )
                k == "DNS" -> DnsScreen(data, back = { screen = Screen.TOOLS }) { d ->
                    Repo.setDns(d)
                    apply()
                }
                k == "CHAT" -> ChatRoot(back = { screen = Screen.HOME })
                k == "APPS" -> AppsScreen(data, back = { screen = Screen.TOOLS }, onChange = apply)
                else -> HomeScreen(
                    vpn, data, onToggle = toggle, onOpen = { open(it) },
                    openSheet = { sheet = true }, openModes = { screen = Screen.MODES },
                    onMode = { m -> Repo.setMode(m); apply() },
                    openTools = { screen = Screen.TOOLS }, onRuApps = { Repo.setRuApps(!data.ruApps); apply() },
                    openChat = { screen = Screen.CHAT }
                )
            }
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
    // Почти чёрный с синевой, как на картинках ChatGPT: синий — только отсвет за Землёй и в нижних углах
    val glow by animateFloatAsState(if (on) 0.14f else 0.07f, tween(900), label = "glow")
    val t = rememberInfiniteTransition(label = "sparks")
    val time by t.animateFloat(0f, 1f, infiniteRepeatable(tween(14_000, easing = LinearEasing)), label = "time")
    Canvas(Modifier.fillMaxSize()) {
        drawRect(Brush.verticalGradient(listOf(Color(0xFF02040B), Color(0xFF030817), Color(0xFF040A1C), Color(0xFF02050F))))
        drawRect(
            Brush.radialGradient(
                listOf(Color(0xFF2F6BFF).copy(alpha = glow), Color.Transparent),
                center = Offset(size.width / 2, size.height * 0.30f), radius = size.width * 0.75f
            )
        )
        // Звёзды: неподвижные, тихо мерцают
        for (i in 0 until 70) {
            val seed = ((i * 7919 + 13) % 1000) / 1000f
            val x = ((i * 0.6180339f + seed * 0.37f) % 1f) * size.width
            val y = ((i * 0.4142136f + seed * 0.21f) % 1f) * size.height
            val tw = 0.5f + 0.5f * kotlin.math.sin((time * 6.2832f * (1f + seed * 2f)) + seed * 10f)
            drawCircle(Color(0xFFBFD8FF).copy(alpha = (0.08f + 0.30f * seed) * (0.4f + 0.6f * tw)),
                radius = 0.6.dp.toPx() + seed * 1.1.dp.toPx(), center = Offset(x, y))
        }
        // отсвет в нижних углах
        for (cx in listOf(-0.15f, 1.15f)) {
            drawCircle(
                Brush.radialGradient(
                    listOf(Color(0xFF2F6BFF).copy(alpha = 0.30f), Color(0xFF2F6BFF).copy(alpha = 0.08f), Color.Transparent),
                    center = Offset(size.width * cx, size.height * 1.02f), radius = size.width * 0.55f
                ),
                radius = size.width * 0.55f, center = Offset(size.width * cx, size.height * 1.02f)
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
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(onClick = onClick).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text("$icon  $text", color = TextSoft, fontSize = 14.sp, modifier = Modifier.weight(1f).padding(end = 10.dp))
        MiniSwitch(on)
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
    ) {
        // «🚀 Лучший сервер», «🎮 Игры» — свои значки, флаги стран — как есть
        if (icoFor(flag) != null) EmojiIcon(flag, size * 0.56f) else Text(flag, fontSize = (size.value * 0.55f).sp)
    }
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
                    .glass(18.dp, glow = sel)
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
                if (sel) Box(
                    Modifier.size(26.dp).clip(CircleShape).background(Color(0xFF2F6BFF)).border(1.dp, Color(0xFF9CC2FF), CircleShape),
                    contentAlignment = Alignment.Center
                ) { LineIcon(Ico.CHECK, 15.dp, Color.White) }
            }
        }
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
        Spacer(Modifier.height(30.dp))
        // знак с орбитой (.wmark): эллипс повёрнут на −14°, знак светится
        Box(Modifier.size(180.dp, 130.dp), contentAlignment = Alignment.TopCenter) {
            Canvas(Modifier.size(220.dp, 120.dp).offset(y = 22.dp)) {
                rotate(-14f) {
                    val k = size.width / 220f
                    drawOval(Color(0x553D7BFF), Offset(6f * k, 30f * k), Size(208f * k, 60f * k), style = Stroke(10f * k))
                    drawOval(Color(0xFF6FA8FF), Offset(6f * k, 30f * k), Size(208f * k, 60f * k), style = Stroke(4f * k))
                }
            }
            Box(Modifier.padding(top = 8.dp)) { AriseMark(104.dp) }
        }
        Text(
            "Arise VPN", fontSize = 44.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 2.dp),
            style = androidx.compose.ui.text.TextStyle(
                brush = Brush.verticalGradient(listOf(Color.White, Color(0xFF9FC3FF))),
                shadow = androidx.compose.ui.graphics.Shadow(Color(0x993C78FF), Offset.Zero, 28f)
            )
        )
        Text("Быстрый и приватный интернет без границ", color = Color(0xFF9CC2FF), fontSize = 16.sp, textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 2.dp))
        Globe(Modifier.size(320.dp).offset(y = (-6).dp), on = true, fadeBottom = false)
        Row(Modifier.fillMaxWidth().offset(y = (-14).dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
            Feature(Ico.BOLT, "Высокая\nскорость")
            Box(Modifier.padding(top = 6.dp).width(1.dp).height(70.dp).background(Color(0x4D8CB9FF)))
            Feature(Ico.SHIELD, "Без логов")
            Box(Modifier.padding(top = 6.dp).width(1.dp).height(70.dp).background(Color(0x4D8CB9FF)))
            Feature(Ico.GLOBE, "Десятки\nстран")
        }
        Spacer(Modifier.height(4.dp))
        // главная кнопка (.wbtn): 54 dp, синяя со свечением, «›» справа
        Row(
            Modifier.fillMaxWidth().height(54.dp)
                .pressable { onOpen("https://t.me/$BOT?start=trial") }
                .neon(27.dp, spread = 18.dp, alpha = 1f)
                .clip(RoundedCornerShape(27.dp))
                .background(Brush.verticalGradient(listOf(Color(0xFF4A86FF), Color(0xFF1D4FD8))))
                .border(1.5.dp, Color(0xE6C8E1FF), RoundedCornerShape(27.dp)),
            horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically
        ) {
            Text("Попробовать бесплатно", color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            Text("›", color = Color(0xFFCFE2FF), fontSize = 26.sp, modifier = Modifier.padding(start = 12.dp, bottom = 3.dp))
        }
        Spacer(Modifier.height(12.dp))
        // вторая кнопка (.wbtn2): 50 dp, тёмное стекло, скрепка
        Row(
            Modifier.fillMaxWidth().height(50.dp)
                .pressable(enabled = !data.loading) {
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
                .clip(RoundedCornerShape(25.dp))
                .background(Color(0x990A142E)).border(1.dp, Color(0x8C8CB9FF), RoundedCornerShape(25.dp)),
            horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically
        ) {
            LineIcon(Ico.CLIP, 22.dp, BlueLight)
            Text(if (data.loading) "Загружаю…" else "Вставить ссылку подписки", color = TextMain, fontSize = 16.sp,
                modifier = Modifier.padding(start = 12.dp))
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
        Text("Подписку можно купить в Telegram-боте @$BOT", color = TextDim, fontSize = 11.5.sp, textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 12.dp).clip(RoundedCornerShape(10.dp)).clickable { onOpen("https://t.me/$BOT") }
                .padding(horizontal = 8.dp, vertical = 6.dp))
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun Feature(ico: Ico, text: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(104.dp)) {
        Box(
            Modifier.size(58.dp).neon(18.dp, color = Color(0xFF2F6BFF), spread = 10.dp, alpha = 0.6f).clip(RoundedCornerShape(18.dp))
                .background(Brush.radialGradient(listOf(Color(0x733C78FF), Color(0xB30A142E))))
                .border(1.dp, Color(0x8C8CB9FF), RoundedCornerShape(18.dp)),
            contentAlignment = Alignment.Center
        ) { LineIcon(ico, 32.dp, Blue) }
        Text(text, color = TextMain, fontSize = 14.sp, textAlign = TextAlign.Center, lineHeight = 17.5.sp,
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
        .pressable(onClick = onClick)
        .then(if (gold) Modifier.neon(27.dp, spread = 16.dp, alpha = 0.9f) else Modifier)
        .clip(shape)
    Text(
        text, color = if (gold) Color.White else TextMain, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
        modifier = (if (gold) m.background(Brush.verticalGradient(listOf(Color(0xFF4A86FF), Color(0xFF1D4FD8))))
            .border(1.5.dp, Color(0xE6C8E1FF), shape)
        else m.background(Color(0x990A142E)).border(1.dp, Color(0x8C8CB9FF), shape))
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
