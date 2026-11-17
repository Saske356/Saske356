package io.github.saske356.arise

import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.runtime.produceState
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.window.Dialog
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private sealed class ChatPage {
    object Home : ChatPage()
    object New : ChatPage()
    object Protect : ChatPage()
    object Admin : ChatPage()
    class Talk(val code: String) : ChatPage()
    class Info(val code: String) : ChatPage()
}

/** Вход в чат: PIN (или его создание), дальше — чаты. back — выйти на главный экран. */
@Composable
fun ChatRoot(back: () -> Unit) {
    val ui by Chat.flow.collectAsState()
    val ctx = LocalContext.current
    // Запрет скриншотов и превью в «недавних», пока чат на экране
    DisposableEffect(ui.unlocked && ui.noScreens) {
        val w = (ctx as? Activity)?.window
        if (ui.unlocked && ui.noScreens) w?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        onDispose { w?.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
    }
    // Ушли с экрана чата — он закрывается: в следующий раз снова PIN
    DisposableEffect(Unit) { onDispose { Chat.lockNow() } }
    // Свернули приложение — чат закрывается, ключи уходят из памяти
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val obs = LifecycleEventObserver { _, e ->
            // во время выбора фото приложение тоже «уходит» с экрана — тогда не запираем
            if (e == Lifecycle.Event.ON_STOP && Chat.flow.value.lockOnLeave && !Chat.keepOpen) Chat.lockNow()
        }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }
    if (!ui.unlocked) {
        // Сначала выбираем хранилище этой подписки (номер от сервера), потом спрашиваем PIN
        var ready by remember { mutableStateOf(false) }
        LaunchedEffect(Unit) {
            Chat.prepare()
            ready = true
        }
        if (ready) PinScreen(back) else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("🔒", fontSize = 38.sp)
        }
        return
    }
    var page by remember { mutableStateOf<ChatPage>(ChatPage.Home) }
    val toList = { page = ChatPage.Home }
    BackHandler { if (page is ChatPage.Home) back() else if (page is ChatPage.Info) page = ChatPage.Talk((page as ChatPage.Info).code) else toList() }
    when (val p = page) {
        ChatPage.Home -> ChatList(ui, back, open = { Chat.read(it); page = ChatPage.Talk(it) },
            add = { page = ChatPage.New }, protect = { page = ChatPage.Protect })
        ChatPage.New -> NewChat(toList) { page = ChatPage.Talk(it) }
        ChatPage.Protect -> ProtectScreen(ui, toList) { page = ChatPage.Admin }
        ChatPage.Admin -> AdminScreen(ui) { page = ChatPage.Protect }
        is ChatPage.Talk -> Talk(ui, p.code, toList) { page = ChatPage.Info(p.code) }
        is ChatPage.Info -> ContactInfo(ui, p.code, back = { page = ChatPage.Talk(p.code) }, deleted = toList)
    }
}

// ---------------------------------------------------------------- PIN

private const val PIN_LEN = 6

@Composable
private fun PinScreen(back: () -> Unit) {
    val scope = rememberCoroutineScope()
    // Нет хранилища, но есть переписка под прежней ссылкой — спрашиваем её PIN, а не новый
    val orphan = !ChatVault.exists() && ChatVault.hasOrphans()
    var startNew by remember { mutableStateOf(false) }
    val first = !ChatVault.exists() && (!orphan || startNew)
    var pin by remember { mutableStateOf("") }
    var firstPin by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val title = when {
        !first -> "Защищённый чат"
        firstPin.isEmpty() -> "Придумайте PIN"
        else -> "Повторите PIN"
    }
    val lead = when {
        !first -> "Без PIN переписку не открыть,\nдаже если телефон в чужих руках."
        firstPin.isEmpty() -> "6 цифр. Его не знает никто, даже мы:\nзабудете — переписку не восстановить."
        else -> "Введите тот же PIN ещё раз."
    }
    fun done(entered: String) {
        busy = true
        scope.launch {
            if (!first) {
                val err = withContext(Dispatchers.IO) { Chat.unlock(entered) }
                msg = err ?: ""
            } else if (firstPin.isEmpty()) {
                firstPin = entered
            } else if (firstPin != entered) {
                firstPin = ""
                msg = "PIN не совпал — придумайте заново"
            } else {
                Chat.setup(entered)
            }
            pin = ""
            busy = false
        }
    }
    Box(Modifier.fillMaxSize()) {
    EarthTop()
    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(Modifier.fillMaxWidth().padding(top = 12.dp).offset(x = (-7).dp)) { BackBtn(back) }
        Spacer(Modifier.height(26.dp))
        // замок в светящемся круге (.lockbadge)
        Box(
            Modifier.size(100.dp).neon(50.dp, color = Color(0xFF2F6BFF), spread = 22.dp, alpha = 0.9f).clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0x803C78FF), Color(0xB30A142E))))
                .border(1.5.dp, Color(0x998CB9FF), CircleShape),
            contentAlignment = Alignment.Center
        ) { LineIcon(Ico.LOCK, 56.dp, Blue) }
        Text(if (first) title else "Введите PIN", color = TextMain, fontSize = 27.sp, fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 18.dp))
        // неверный PIN — ряд точек трясётся
        val shake = remember { androidx.compose.animation.core.Animatable(0f) }
        LaunchedEffect(msg) {
            if (msg.isNotEmpty()) for (x in listOf(14f, -12f, 8f, -4f, 0f)) shake.animateTo(x, androidx.compose.animation.core.tween(70))
        }
        Row(
            Modifier.padding(top = 18.dp).graphicsLayer { translationX = shake.value * density },
            horizontalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            repeat(PIN_LEN) { i ->
                val on = i < pin.length
                // точка «выпрыгивает», когда цифра введена
                val pop by androidx.compose.animation.core.animateFloatAsState(
                    if (on) 1.12f else 1f,
                    androidx.compose.animation.core.spring(dampingRatio = 0.35f, stiffness = 500f), label = "dot"
                )
                Box(
                    Modifier.size(18.dp).graphicsLayer { scaleX = pop; scaleY = pop }
                        .then(if (on) Modifier.neon(9.dp, color = Color(0xFF3D7BFF), spread = 6.dp, alpha = 1f) else Modifier)
                        .clip(CircleShape)
                        .background(if (on) Brush.radialGradient(listOf(Color(0xFFEAF4FF), Color(0xFF3D7BFF)))
                        else Brush.radialGradient(listOf(Color(0x990A142E), Color(0x990A142E))))
                        .border(1.5.dp, if (on) Color(0xFFCFE0FF) else Color(0x998CB9FF), CircleShape)
                )
            }
        }
        Row(Modifier.padding(top = 18.dp).height(40.dp), verticalAlignment = Alignment.CenterVertically) {
            if (busy || msg.isNotEmpty()) {
                Text(if (busy) "Проверяю…" else msg, color = if (busy) TextSoft else Color(0xFFFF8A94), fontSize = 13.5.sp,
                    textAlign = TextAlign.Center, lineHeight = 18.sp)
            } else {
                LineIcon(Ico.SHIELD, 20.dp, Blue)
                Text(lead, color = TextSoft, fontSize = 13.5.sp, lineHeight = 18.sp, modifier = Modifier.padding(start = 10.dp))
            }
        }
        val keys = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫")
        val letters = mapOf("2" to "ABC", "3" to "DEF", "4" to "GHI", "5" to "JKL", "6" to "MNO", "7" to "PQRS", "8" to "TUV", "9" to "WXYZ")
        Spacer(Modifier.height(16.dp))
        for (row in keys.chunked(3)) {
            Row(Modifier.padding(bottom = 12.dp), horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                for (k in row) {
                    if (k.isEmpty()) { Spacer(Modifier.size(76.dp)); continue }
                    Box(
                        Modifier.size(76.dp).pressable(enabled = !busy) {
                                if (k == "⌫") pin = pin.dropLast(1)
                                else if (pin.length < PIN_LEN) {
                                    pin += k
                                    msg = ""
                                    if (pin.length == PIN_LEN) done(pin)
                                }
                            }
                            .neon(38.dp, color = Color(0xFF2864FF), spread = 8.dp, alpha = 0.35f)
                            .clip(CircleShape)
                            .background(Brush.radialGradient(listOf(Color(0xB3223C78), Color(0xD9081026)),
                                center = Offset(38f * LocalDensity.current.density, 23f * LocalDensity.current.density), radius = 60f * LocalDensity.current.density))
                            .border(1.dp, Color(0x808CB9FF), CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        if (k == "⌫") LineIcon(Ico.BACKSPACE, 30.dp, BlueLight)
                        else Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(k, color = TextMain, fontSize = 28.sp, fontWeight = FontWeight.Medium, lineHeight = 30.sp)
                            Text(letters[k] ?: "", color = Color(0xFFB9C9E8), fontSize = 9.5.sp, letterSpacing = 1.sp, lineHeight = 11.sp)
                        }
                    }
                }
            }
        }
        if (orphan && !startNew) Text(
            "Забыли PIN? Начать новый чат →", color = Color(0xFF7FB2FF), fontSize = 14.sp,
            modifier = Modifier.padding(top = 10.dp).clickable { startNew = true; pin = ""; msg = "" }
        ) else if (!first) Text("После ${ChatVault.MAX_FAILS} неверных попыток переписка стирается",
            color = TextDim, fontSize = 12.sp, modifier = Modifier.padding(top = 10.dp))
    }
    }
}

// ---------------------------------------------------------------- общие кусочки

@Composable
private fun BackBtn(onClick: () -> Unit) {
    Circ(40.dp, onClick, glow = true) { LineIcon(Ico.BACK, 18.dp, Color(0xFFDBE8FF)) }
}

/** Аватар с буквой (.ava): синий шар со светлой рамкой и свечением. */
@Composable
private fun Avatar(name: String, size: Int = 48) {
    Box(
        Modifier.size(size.dp).neon((size / 2).dp, color = Color(0xFF2F6BFF), spread = 8.dp, alpha = 0.7f).clip(CircleShape)
            .background(Brush.radialGradient(listOf(Color(0xFF3D7BFF), Color(0xFF0E1A36)),
                center = Offset(size * 0.45f * LocalDensity.current.density, size * 0.35f * LocalDensity.current.density),
                radius = size * 0.75f * LocalDensity.current.density))
            .border(1.5.dp, Color(0xB396C3FF), CircleShape),
        contentAlignment = Alignment.Center
    ) { Text(name.trim().take(1).uppercase().ifEmpty { "?" }, color = Color(0xFFCFE2FF), fontSize = (size * 0.44).sp, fontWeight = FontWeight.Bold) }
}

@Composable
private fun ErrorLine(text: String) {
    if (text.isNotEmpty()) Text(text, color = Red, fontSize = 12.5.sp, textAlign = TextAlign.Center,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 6.dp))
}

private fun hhmm(ms: Long): String {
    val day = 86_400_000L
    val now = System.currentTimeMillis()
    return when {
        now - ms < day && SimpleDateFormat("d", Locale.ROOT).format(Date(ms)) == SimpleDateFormat("d", Locale.ROOT).format(Date(now)) ->
            SimpleDateFormat("HH:mm", Locale.ROOT).format(Date(ms))
        now - ms < 7 * day -> SimpleDateFormat("EE", Locale.forLanguageTag("ru")).format(Date(ms))
        else -> SimpleDateFormat("dd.MM", Locale.ROOT).format(Date(ms))
    }
}

private fun ttlText(h: Int) = when (h) {
    0 -> "выключено"
    1 -> "1 час"
    24 -> "24 часа"
    168 -> "7 дней"
    else -> "$h ч"
}

// ---------------------------------------------------------------- список чатов

@Composable
private fun ChatList(ui: ChatUi, back: () -> Unit, open: (String) -> Unit, add: () -> Unit, protect: () -> Unit) {
    val ctx = LocalContext.current
    Box(Modifier.fillMaxSize()) {
        EarthTop()
        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
            // шапка (.chathead): назад, «Чаты» 30 sp, круглые «＋» и щит 46 dp
            Row(Modifier.fillMaxWidth().padding(start = 17.dp, end = 17.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                BackBtn(back)
                Text("Чаты", color = TextMain, fontSize = 30.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 18.dp).weight(1f))
                Circ(46.dp, add) { Text("＋", color = Color(0xFFCFE0FF), fontSize = 24.sp) }
                Spacer(Modifier.width(10.dp))
                Circ(46.dp, protect) { LineIcon(Ico.SHIELD, 24.dp, BlueLight) }
            }
            // мой код (.codecard)
            Row(
                Modifier.fillMaxWidth().padding(start = 17.dp, end = 17.dp, top = 22.dp)
                    .neon(24.dp, spread = 16.dp, alpha = 0.8f).clip(RoundedCornerShape(24.dp))
                    .background(Brush.verticalGradient(listOf(Color(0xB8162854), Color(0xC7081026))))
                    .border(1.dp, Color(0xBF96C3FF), RoundedCornerShape(24.dp))
                    .height(88.dp).padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(
                    Modifier.size(50.dp).clip(CircleShape)
                        .background(Brush.radialGradient(listOf(Color(0x803C78FF), Color(0x990A142E))))
                        .border(1.dp, Color(0x808CB9FF), CircleShape),
                    contentAlignment = Alignment.Center
                ) { LineIcon(Ico.SHIELD, 30.dp, BlueLight) }
                Column(Modifier.weight(1f).padding(start = 12.dp)) {
                    Text("Мой код:", color = TextSoft, fontSize = 13.sp)
                    Text(if (ui.code.isEmpty()) "…" else Chat.pretty(ui.code), color = TextMain, fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold, letterSpacing = 0.3.sp, maxLines = 1)
                }
                if (ui.code.isNotEmpty()) Row(
                    Modifier.height(34.dp)
                        .pressable {
                            val text = "Мой код в чате Arise VPN: ${Chat.pretty(ui.code)}"
                            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                                .putExtra(Intent.EXTRA_TEXT, text), "Поделиться кодом").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }
                        .neon(17.dp, spread = 8.dp, alpha = 0.7f)
                        .clip(RoundedCornerShape(18.dp))
                        .background(Brush.verticalGradient(listOf(Color(0xFF4A86FF), Color(0xFF1D4FD8))))
                        .border(1.dp, Color(0xCCBED7FF), RoundedCornerShape(18.dp))
                        .padding(horizontal = 12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    LineIcon(Ico.SHARE, 18.dp, Color.White)
                    Text("Поделиться", color = Color.White, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(start = 6.dp))
                }
            }
            if (ui.notice.isNotEmpty()) Text(
                "📢 " + ui.notice, color = TextMain, fontSize = 13.5.sp,
                modifier = Modifier.fillMaxWidth().padding(start = 17.dp, end = 17.dp, top = 12.dp)
                    .clip(RoundedCornerShape(16.dp)).background(Amber.copy(alpha = 0.12f))
                    .border(1.dp, Amber.copy(alpha = 0.35f), RoundedCornerShape(16.dp)).padding(12.dp)
            )
            ErrorLine(ui.error)
            val rows = (ui.contacts.map { it.code } + ui.msgs.keys).distinct()
                .sortedByDescending { ui.msgs[it]?.lastOrNull()?.t ?: 0L }
            if (rows.isEmpty()) {
                Text("Здесь будут ваши чаты.\nНажмите «＋» и введите код собеседника.", color = TextSoft, fontSize = 14.sp,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 60.dp))
            }
            LazyColumn(Modifier.weight(1f).fillMaxWidth().padding(top = 14.dp)) {
                items(rows) { code ->
                    val c = ui.contacts.firstOrNull { it.code == code }
                    val name = c?.name ?: Chat.pretty(code)
                    val last = ui.msgs[code]?.lastOrNull()
                    // строка чата (.crow): 80 dp, аватар 54
                    Row(
                        Modifier.animateItem().fillMaxWidth().padding(horizontal = 17.dp, vertical = 6.dp).pressable { open(code) }
                            .glass(24.dp).height(80.dp).padding(start = 12.dp, end = 14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Avatar(name, 54)
                        Column(Modifier.weight(1f).padding(start = 14.dp)) {
                            Text(name, color = TextMain, fontSize = 16.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(
                                when {
                                    c?.keyChanged == true -> "⚠️ собеседник сменил ключ — сверьте код"
                                    last == null -> "сообщений нет"
                                    last.img.isNotEmpty() -> if (last.out) "Вы: 📷 Фото" else "📷 Фото"
                                    last.out -> "Вы: ${last.text}"
                                    else -> last.text
                                },
                                color = if (c?.keyChanged == true) Amber else TextSoft, fontSize = 13.5.sp, maxLines = 1,
                                overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 1.dp)
                            )
                            Row(Modifier.padding(top = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                                LineIcon(Ico.LOCK, 13.dp, TextDim)
                                Text("зашифровано", color = TextDim, fontSize = 12.sp, modifier = Modifier.padding(start = 6.dp))
                            }
                        }
                        Column(Modifier.align(Alignment.Top).padding(top = 14.dp), horizontalAlignment = Alignment.End) {
                            if (last != null) Text(hhmm(last.t), color = TextSoft, fontSize = 12.5.sp)
                            val n = ui.unread[code] ?: 0
                            if (n > 0) Box(
                                Modifier.padding(top = 8.dp).size(24.dp).neon(12.dp, color = Color(0xFF3D7BFF), spread = 6.dp, alpha = 1f)
                                    .clip(CircleShape).background(Color(0xFF2F6BFF)),
                                contentAlignment = Alignment.Center
                            ) { Text("$n", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
                        }
                    }
                }
            }
            // нижние вкладки (.tabs): «Чаты» и «Настройки» (= «Защита»)
            Row(
                Modifier.fillMaxWidth().padding(start = 17.dp, end = 17.dp, top = 6.dp, bottom = 12.dp).glass(22.dp).height(62.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                    LineIcon(Ico.BUBBLE, 26.dp, Color(0xFFCFE2FF))
                    Text("Чаты", color = Color(0xFFCFE2FF), fontSize = 12.sp, modifier = Modifier.padding(top = 3.dp))
                }
                Column(Modifier.weight(1f).clickable(onClick = protect), horizontalAlignment = Alignment.CenterHorizontally) {
                    LineIcon(Ico.GEAR, 24.dp, TextDim)
                    Text("Настройки", color = TextDim, fontSize = 12.sp, modifier = Modifier.padding(top = 3.dp))
                }
            }
        }
    }
}

// ---------------------------------------------------------------- новый собеседник

@Composable
private fun NewChat(back: () -> Unit, opened: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var err by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    Page("Новый чат", "Код собеседник видит у себя в «Чатах». Номер телефона, имя и Telegram не нужны.", back) {
        Text("Код собеседника", color = TextSoft, fontSize = 13.sp, modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
        Field(code, "K7M-2QX-9TR") { code = it.uppercase().take(11) }
        Text("Как подписать", color = TextSoft, fontSize = 13.sp, modifier = Modifier.padding(start = 4.dp, top = 16.dp, bottom = 6.dp))
        Field(name, "Например, Артём") { name = it.take(32) }
        if (err.isNotEmpty()) Text(err, color = Red, fontSize = 13.sp, modifier = Modifier.padding(top = 10.dp))
        Spacer(Modifier.height(18.dp))
        Big(if (busy) "Ищу…" else "Начать чат", gold = !busy) {
            if (busy) return@Big
            busy = true
            scope.launch {
                val e = withContext(Dispatchers.IO) { Chat.addContact(code, name) }
                busy = false
                if (e == null) opened(code.uppercase().filter { it in "ABCDEFGHJKMNPQRSTUVWXYZ23456789" }) else err = e
            }
        }
    }
}

// ---------------------------------------------------------------- переписка

@Composable
private fun Talk(ui: ChatUi, code: String, back: () -> Unit, info: () -> Unit) {
    val c = ui.contacts.firstOrNull { it.code == code }
    val name = c?.name ?: Chat.pretty(code)
    val msgs = ui.msgs[code].orEmpty()
    var text by remember { mutableStateOf("") }
    val list = rememberLazyListState()
    val ctx = LocalContext.current
    var full by remember { mutableStateOf<ImageBitmap?>(null) }  // фото на весь экран
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        Chat.keepOpen = false
        if (uri != null) Chat.sendPhoto(ctx, code, uri)
    }
    LaunchedEffect(msgs.size) {
        if (msgs.isNotEmpty()) list.animateScrollToItem(msgs.size - 1)
        Chat.read(code)
    }
    Box(Modifier.fillMaxSize()) {
    EarthTop()
    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        // шапка переписки (.talkhead): полоса 64 dp, аватар 44, «⋮»
        Row(
            Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 4.dp).height(64.dp)
                .clip(RoundedCornerShape(22.dp))
                .background(Brush.verticalGradient(listOf(Color(0xCC0E1C3E), Color(0x99060C1E))))
                .padding(horizontal = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            BackBtn(back)
            Box(Modifier.padding(start = 10.dp).clickable(onClick = info)) { Avatar(name, 44) }
            Column(Modifier.weight(1f).padding(start = 10.dp).clickable(onClick = info)) {
                Text(name, color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val col = when {
                        c?.keyChanged == true -> Amber
                        c?.verified == true -> TextSoft
                        else -> TextSoft
                    }
                    if (c?.keyChanged != true) LineIcon(Ico.LOCK, 12.dp, col)
                    Text(
                        when {
                            c?.keyChanged == true -> "⚠️ ключ сменился — сверьте код"
                            c?.verified == true -> "код безопасности сверен"
                            else -> "зашифровано · код не сверен"
                        },
                        color = col, fontSize = 12.5.sp, maxLines = 1, modifier = Modifier.padding(start = 5.dp)
                    )
                }
            }
            Circ(36.dp, info) { Text("⋮", color = Color(0xFFCFE0FF), fontSize = 18.sp, fontWeight = FontWeight.Bold) }
        }
        Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp).height(1.dp).background(Color(0x406EA0FF)))
        Text(
            if (ui.ttlHours > 0) "⏱ Сообщения исчезают через ${ttlText(ui.ttlHours)}" else "⏱ Самоудаление выключено",
            color = Color(0xFF9CC6FF), fontSize = 12.sp,
            modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 10.dp).clip(RoundedCornerShape(12.dp))
                .background(Color(0x990A142E)).border(1.dp, Color(0x596EA0FF), RoundedCornerShape(12.dp))
                .padding(horizontal = 12.dp, vertical = 5.dp)
        )
        ErrorLine(ui.error)
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp), state = list,
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(top = 10.dp, bottom = 6.dp)
        ) {
            items(msgs, key = { it.id }) { m ->
                // пузырь «выпрыгивает» при появлении (.msg pop)
                val appear = remember { androidx.compose.animation.core.Animatable(0.85f) }
                LaunchedEffect(Unit) { appear.animateTo(1f, androidx.compose.animation.core.spring(dampingRatio = 0.5f, stiffness = 600f)) }
                BoxWithConstraints(Modifier.animateItem().fillMaxWidth(), contentAlignment = if (m.out) Alignment.CenterEnd else Alignment.CenterStart) {
                    val shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp, bottomStart = if (m.out) 20.dp else 6.dp,
                        bottomEnd = if (m.out) 6.dp else 20.dp)
                    val time = hhmm(m.t) + (if (m.exp > 0) " · ⏱" else "") + (if (m.out) " ✓" else "")
                    Box(
                        Modifier.widthIn(max = maxWidth * 0.72f)
                            .graphicsLayer { scaleX = appear.value; scaleY = appear.value; alpha = ((appear.value - 0.85f) / 0.15f).coerceIn(0f, 1f) }
                            .then(if (m.out) Modifier.neon(20.dp, color = Color(0xFF2F6BFF), spread = 10.dp, alpha = 0.6f) else Modifier)
                            .clip(shape)
                            .background(if (m.out) Brush.verticalGradient(listOf(Color(0xFF3F7BFF), Color(0xFF1C48C8)))
                            else Brush.verticalGradient(listOf(Color(0xD91A2C5C), Color(0xD90A142C))))
                            .border(1.dp, if (m.out) Color(0xB3AACDFF) else Color(0x738CB9FF), shape)
                    ) {
                        if (m.img.isNotEmpty()) {
                            val bmp by produceState<ImageBitmap?>(null, m.img) {
                                value = withContext(Dispatchers.IO) {
                                    Chat.media(m.img)?.let { b -> BitmapFactory.decodeByteArray(b, 0, b.size)?.asImageBitmap() }
                                }
                            }
                            val b = bmp
                            Box(Modifier.padding(6.dp)) {
                                if (b != null) Image(
                                    b, contentDescription = "Фото", contentScale = ContentScale.Crop,
                                    modifier = Modifier.size(200.dp, (200.dp * b.height / b.width.coerceAtLeast(1)).coerceIn(110.dp, 260.dp))
                                        .clip(RoundedCornerShape(14.dp)).clickable { full = b }
                                ) else Text("📷 Фото удалено", color = TextMain, fontSize = 15.5.sp, modifier = Modifier.padding(8.dp))
                                Text(time, color = Color(0xE6E6F0FF), fontSize = 11.sp,
                                    modifier = Modifier.align(Alignment.BottomEnd).padding(8.dp).clip(RoundedCornerShape(9.dp))
                                        .background(Color(0x8C000000)).padding(horizontal = 7.dp, vertical = 2.dp))
                            }
                        } else Row(Modifier.padding(horizontal = 14.dp, vertical = 11.dp), verticalAlignment = Alignment.Bottom) {
                            // одна галочка — «доставлено на сервер» (отметок о прочтении нет — двойную не рисуем)
                            Text(m.text, color = TextMain, fontSize = 15.5.sp, lineHeight = 20.sp, modifier = Modifier.weight(1f, fill = false))
                            Text(time, color = Color(0xBFE6F0FF), fontSize = 11.sp, maxLines = 1, modifier = Modifier.padding(start = 10.dp))
                        }
                    }
                }
            }
        }
        if (ui.busy) Text("Отправляю фото…", color = TextSoft, fontSize = 12.sp, modifier = Modifier.padding(start = 18.dp))
        // строка ввода (.inputbar): скрепка 46, поле 44, отправка 50
        Row(
            Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 14.dp)
                .clip(RoundedCornerShape(30.dp))
                .background(Brush.verticalGradient(listOf(Color(0xCC0E1C3E), Color(0xCC060C1E))))
                .border(1.dp, Color(0x4D6EA0FF), RoundedCornerShape(30.dp))
                .heightIn(min = 60.dp).padding(horizontal = 5.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Circ(46.dp, onClick = {
                if (c != null && !ui.busy) {
                    Chat.keepOpen = true
                    pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }
            }) { LineIcon(Ico.CLIP, 24.dp, Color(0xFFCFE0FF)) }
            Box(
                Modifier.weight(1f).padding(horizontal = 8.dp).heightIn(min = 44.dp).clip(RoundedCornerShape(22.dp))
                    .background(Color(0x990A142E)).border(1.dp, Color(0x738CB9FF), RoundedCornerShape(22.dp))
                    .padding(horizontal = 16.dp, vertical = 11.dp),
                contentAlignment = Alignment.CenterStart
            ) {
                if (text.isEmpty()) Text("Сообщение", color = Color(0xFF8FA8D8), fontSize = 15.sp)
                BasicTextField(
                    value = text, onValueChange = { text = it.take(4000) }, maxLines = 5,
                    textStyle = TextStyle(color = TextMain, fontSize = 15.sp, fontFamily = Inter),
                    cursorBrush = SolidColor(Blue), modifier = Modifier.fillMaxWidth()
                )
            }
            Box(
                Modifier.size(50.dp)
                    .pressable(enabled = text.isNotBlank() && c != null) {
                        Chat.send(code, text.trim())
                        text = ""
                    }
                    .neon(25.dp, color = Color(0xFF3C78FF), spread = 12.dp, alpha = 1f)
                    .clip(CircleShape)
                    .background(Brush.verticalGradient(listOf(Color(0xFF4A86FF), Color(0xFF1D4FD8))))
                    .border(1.dp, Color(0xD9BED7FF), CircleShape),
                contentAlignment = Alignment.Center
            ) { LineIcon(Ico.SEND, 26.dp, Color.White) }
        }
    }
    }
    full?.let { b ->
        Dialog(onDismissRequest = { full = null }) {
            Image(b, contentDescription = "Фото", contentScale = ContentScale.Fit,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { full = null })
        }
    }
}

// ---------------------------------------------------------------- о собеседнике: код безопасности

@Composable
private fun ContactInfo(ui: ChatUi, code: String, back: () -> Unit, deleted: () -> Unit) {
    val c = ui.contacts.firstOrNull { it.code == code }
    var name by remember { mutableStateOf(c?.name ?: "") }
    var confirm by remember { mutableStateOf(false) }
    Page(c?.name ?: Chat.pretty(code), "Код собеседника: ${Chat.pretty(code)}", back) {
        Section("Код безопасности")
        Text(
            Chat.safety(code).chunked(18).joinToString("\n") { it.trim() },
            color = BlueLight, fontSize = 16.sp, fontFamily = FontFamily.Monospace, letterSpacing = 2.sp, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Glass)
                .border(1.dp, GlassLine, RoundedCornerShape(18.dp)).padding(16.dp)
        )
        Note("Сравните с кодом у собеседника при встрече или голосом. Совпадает — между вами никто не подслушивает " +
            "и сервер не подменил ключ.")
        Spacer(Modifier.height(12.dp))
        if (c != null && !c.verified) Big("✓ Коды совпали", gold = true) { Chat.markVerified(code) }
        else if (c != null) Text("✓ Код сверен", color = Green, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
        Section("Имя")
        Field(name, "Как подписать") { name = it.take(32) }
        Spacer(Modifier.height(10.dp))
        Big("Сохранить", gold = false) { Chat.rename(code, name.ifBlank { Chat.pretty(code) }) }
        if (ui.admin && !ui.decoy) {
            Section("Админ")
            val isBanned = code in ui.banned
            Big(if (isBanned) "Разблокировать этот код" else "⛔ Заблокировать этот код в чате", gold = false) {
                if (isBanned) Chat.unban(code) else Chat.ban(code)
            }
            Note("Заблокированный не сможет писать никому, письма ему не доставляются.")
        }
        Section("Удаление")
        Big(if (confirm) "Точно удалить? Нажмите ещё раз" else "🗑 Удалить чат и переписку", gold = false) {
            if (confirm) {
                Chat.deleteChat(code)
                deleted()
            } else confirm = true
        }
    }
}

@Composable
private fun Section(title: String) {
    Text(title.uppercase(), color = TextDim, fontSize = 11.sp, letterSpacing = 1.5.sp, modifier = Modifier.padding(start = 4.dp, top = 18.dp, bottom = 8.dp))
}

@Composable
private fun Note(text: String) {
    Text(text, color = TextDim, fontSize = 12.sp, modifier = Modifier.padding(start = 4.dp, top = 8.dp, end = 4.dp))
}

// ---------------------------------------------------------------- защита и админ

@Composable
private fun ProtectScreen(ui: ChatUi, back: () -> Unit, openAdmin: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var dialog by remember { mutableStateOf("") }  // "pin" | "decoy" | "wipe"
    var input by remember { mutableStateOf("") }
    var oldPin by remember { mutableStateOf("") }  // текущий второй PIN — без него второй чат не пересоздаём
    var msg by remember { mutableStateOf("") }
    LaunchedEffect(ui.admin) { if (ui.admin && !ui.decoy) Chat.refreshAdmin() }
    Page("Защита", "", back) {
        Section("Переписка")
        Tool("⏱", "Самоудаление", "Для новых сообщений, у обоих собеседников", ttlText(ui.ttlHours) + " ›") {
            val next = listOf(1, 24, 168, 0)
            Chat.setTtl(next[(next.indexOf(ui.ttlHours) + 1).mod(next.size)])
        }
        ToggleRow("🚫", "Запрет скриншотов и превью в «недавних»", ui.noScreens) { Chat.setNoScreens(!ui.noScreens) }
        ToggleRow("⏲", "Закрывать чат, если свернули приложение", ui.lockOnLeave) { Chat.setLockOnLeave(!ui.lockOnLeave) }
        if (!rememberNotifyEnabled()) {
            val askNotify = rememberNotifyAsk()
            Tool("⚠️", "Уведомления запрещены", "Телефон их не покажет, пока не разрешите", "Включить") { askNotify() }
        }
        if (ui.decoy) {
            // Во втором профиле — своя настройка (основную отсюда не трогаем): только тихие уведомления
            var on by remember { mutableStateOf(ChatVault.secondNotify) }
            Tool("🔔", "Уведомления о письмах",
                (if (on) "«Arise VPN: есть обновление» — чат не выдаёт себя" else "Выключены") +
                    " · приходят, пока включён VPN",
                if (on) "Тихие ›" else "Выкл ›") {
                on = !on
                ChatVault.secondNotify = on
            }
        } else {
        var notify by remember { mutableStateOf(ChatVault.notifyMode()) }
        Tool("🔔", "Уведомления о письмах",
            when (notify) {
                "plain" -> "«Новое сообщение» — без текста и имени"
                "off" -> "Выключены"
                else -> "«Arise VPN: есть обновление» — чат не выдаёт себя"
            } + " · приходят, пока включён VPN",
            when (notify) { "plain" -> "Явные ›"; "off" -> "Выкл ›"; else -> "Тихие ›" }) {
            notify = when (notify) { "neutral" -> "plain"; "plain" -> "off"; else -> "neutral" }
            ChatVault.setNotifyMode(notify)
        }
        }
        run {
            Section("Вход")
            // Второй PIN нигде не показан: его задают долгим нажатием на «Сменить PIN».
            // Пункт «ложный PIN» в настройках сам выдавал, что второй чат может быть.
            LongTool("🔑", "Сменить PIN", "6 цифр", "›",
                onClick = { dialog = "pin"; input = ""; msg = "" },
                onLong = { dialog = "decoy"; input = ""; oldPin = ""; msg = "" })
            if (dialog == "pin" || dialog == "decoy") {
                if (dialog == "decoy") Note(
                    "Второй PIN открывает второй, отдельный чат: свой код, свои собеседники. Если заставят " +
                        "разблокировать — введите его. Об этом экране знаете только вы."
                )
                val changeDecoy = dialog == "decoy" && ui.hasDecoy
                if (changeDecoy) {
                    Field(oldPin, "Текущий второй PIN") { oldPin = it.filter { ch -> ch.isDigit() }.take(PIN_LEN) }
                    Spacer(Modifier.height(8.dp))
                }
                Field(input, if (dialog == "pin") "Новый PIN, 6 цифр" else if (changeDecoy) "Новый второй PIN" else "Второй PIN, 6 цифр") {
                    input = it.filter { ch -> ch.isDigit() }.take(PIN_LEN)
                }
                if (msg.isNotEmpty()) Text(msg, color = Red, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
                Spacer(Modifier.height(10.dp))
                Big("Сохранить", gold = true) {
                    if (input.length != PIN_LEN) {
                        msg = "Нужно 6 цифр"
                        return@Big
                    }
                    if (changeDecoy && oldPin.length != PIN_LEN) {
                        msg = "Введите текущий второй PIN"
                        return@Big
                    }
                    val what = dialog
                    val value = input
                    val old = if (changeDecoy) oldPin else ""
                    scope.launch {
                        val e = withContext(Dispatchers.IO) { if (what == "pin") Chat.changePin(value) else Chat.setDecoy(value, old) }
                        if (e == null) {
                            dialog = ""
                            Toast.makeText(ctx, if (what == "pin") "PIN изменён" else if (old.isNotEmpty()) "Второй PIN изменён"
                                else "Второй PIN задан", Toast.LENGTH_SHORT).show()
                        } else msg = e
                    }
                }
                if (dialog == "decoy" && ui.hasDecoy) {
                    Spacer(Modifier.height(8.dp))
                    Big("Убрать второй PIN и его чат", gold = false) { Chat.dropDecoy(); dialog = "" }
                }
            }
        }
        Section("Экстренно")
        Tool("🧨", "Стереть всё", "Переписку, ключи и контакты — без возможности восстановить",
            if (dialog == "wipe") "Точно? ›" else "") {
            if (dialog == "wipe") {
                Chat.wipe()
                back()
            } else dialog = "wipe"
        }
        if (ui.admin && !ui.decoy) {
            Section("Админ · только у твоей подписки")
            Tool("👑", "Админ-панель", "Сводка, чат, объявление, блокировки", "›", openAdmin)
        }
        val clip = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        if (ui.code.isNotEmpty()) {
            Section("Мой код")
            Tool("📋", Chat.pretty(ui.code), "Скопировать", "›") {
                clip.setPrimaryClip(ClipData.newPlainText("code", Chat.pretty(ui.code)))
                Toast.makeText(ctx, "Код скопирован", Toast.LENGTH_SHORT).show()
            }
        }
    }
}

/** Как Tool, но с долгим нажатием (скрытые действия). */
@Composable
private fun LongTool(icon: String, title: String, sub: String, right: String, onClick: () -> Unit, onLong: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 8.dp)
            .clip(RoundedCornerShape(16.dp))
            .background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(16.dp))
            .pointerInput(Unit) { detectTapGestures(onTap = { onClick() }, onLongPress = { onLong() }) }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(38.dp).clip(RoundedCornerShape(12.dp)).background(BlueMid.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) {
            EmojiIcon(icon, 22.dp)
        }
        Column(Modifier.weight(1f).padding(start = 12.dp)) {
            Text(title, color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
            Text(sub, color = TextDim, fontSize = 12.sp, maxLines = 2)
        }
        if (right.isNotEmpty()) Text(right, color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun StatBox(k: String, v: String, modifier: Modifier) {
    Column(
        modifier.clip(RoundedCornerShape(16.dp)).background(Glass).border(1.dp, GlassLine, RoundedCornerShape(16.dp)).padding(12.dp)
    ) {
        Text(k.uppercase(), color = TextDim, fontSize = 10.5.sp, letterSpacing = 1.sp)
        Text(v, color = TextMain, fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
    }
}

// ---------------------------------------------------------------- админ-панель

@Composable
private fun AdminScreen(ui: ChatUi, back: () -> Unit) {
    var notice by remember { mutableStateOf(ui.notice) }
    var banCode by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        while (true) {  // пока экран открыт — свежие цифры раз в 15 секунд
            Chat.refreshAdmin()
            kotlinx.coroutines.delay(15_000)
        }
    }
    val st = ui.adminStats
    fun n(k: String) = st[k]?.toString() ?: "—"
    Page("Админ-панель", "Видно только с твоей подписки. Чужую переписку админ не видит — только цифры.", back) {
        Section("Сводка")
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatBox("Подписок", n("subs"), Modifier.weight(1f))
            StatBox("Платящих", n("people"), Modifier.weight(1f))
            StatBox("Онлайн устр.", n("online"), Modifier.weight(1f))
        }
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatBox("Новых за сутки", n("new_today"), Modifier.weight(1f))
            StatBox("Всего в боте", n("users_all"), Modifier.weight(1f))
            StatBox("Автопродл.", n("auto"), Modifier.weight(1f))
        }
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatBox("⭐ за сутки", n("stars_today"), Modifier.weight(1f))
            StatBox("⭐ всего", n("stars"), Modifier.weight(1f))
            StatBox("₽ всего", n("rub"), Modifier.weight(1f))
        }
        Section("Чат")
        ToggleRow("💬", "Чат для всех (выключить — никто не сможет писать)", ui.enabled) { Chat.setEnabled(!ui.enabled) }
        Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatBox("Устройств в чате", ui.adminUsers.toString(), Modifier.weight(1f))
            StatBox("Ждут доставки", ui.adminQueued.toString(), Modifier.weight(1f))
        }
        Section("Объявление всем")
        Field(notice, "Например: технические работы в 23:00") { notice = it.take(500) }
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.weight(1f)) { Big("Опубликовать", gold = true) { Chat.setNotice(notice) } }
            Box(Modifier.weight(1f)) { Big("Убрать", gold = false) { notice = ""; Chat.setNotice("") } }
        }
        Note("Видно сверху списка чатов у всех. Объявление не шифруется — не пишите в нём секретов.")
        Section("Блокировки")
        Field(banCode, "Код, например K7M-2QX-9TR") { banCode = it.uppercase().take(11) }
        Spacer(Modifier.height(10.dp))
        Big("⛔ Заблокировать", gold = false) {
            if (banCode.isNotBlank()) Chat.ban(banCode)
            banCode = ""
        }
        if (ui.banned.isEmpty()) Note("Заблокированных нет.")
        for (c in ui.banned) {
            Tool("⛔", Chat.pretty(c), "Не может писать, письма ему не доставляются", "Разблокировать") { Chat.unban(c) }
        }
        ErrorLine(ui.error)
    }
}
