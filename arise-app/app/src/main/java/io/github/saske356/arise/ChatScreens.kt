package io.github.saske356.arise

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.compose.BackHandler
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
    // Свернули приложение — чат закрывается, ключи уходят из памяти
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val obs = LifecycleEventObserver { _, e ->
            if (e == Lifecycle.Event.ON_STOP && Chat.flow.value.lockOnLeave) Chat.lockNow()
        }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }
    if (!ui.unlocked) {
        PinScreen(back)
        return
    }
    var page by remember { mutableStateOf<ChatPage>(ChatPage.Home) }
    val toList = { page = ChatPage.Home }
    BackHandler { if (page is ChatPage.Home) back() else if (page is ChatPage.Info) page = ChatPage.Talk((page as ChatPage.Info).code) else toList() }
    when (val p = page) {
        ChatPage.Home -> ChatList(ui, back, open = { Chat.read(it); page = ChatPage.Talk(it) },
            add = { page = ChatPage.New }, protect = { page = ChatPage.Protect })
        ChatPage.New -> NewChat(toList) { page = ChatPage.Talk(it) }
        ChatPage.Protect -> ProtectScreen(ui, toList)
        is ChatPage.Talk -> Talk(ui, p.code, toList) { page = ChatPage.Info(p.code) }
        is ChatPage.Info -> ContactInfo(ui, p.code, back = { page = ChatPage.Talk(p.code) }, deleted = toList)
    }
}

// ---------------------------------------------------------------- PIN

private const val PIN_LEN = 6

@Composable
private fun PinScreen(back: () -> Unit) {
    val scope = rememberCoroutineScope()
    val first = !ChatVault.exists()
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
        !first -> "Введите PIN. Без него переписку не открыть, даже если телефон в чужих руках."
        firstPin.isEmpty() -> "6 цифр. Его не знает никто, даже мы: забудете — переписку не восстановить."
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
    Column(
        Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().padding(horizontal = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(Modifier.fillMaxWidth().padding(top = 14.dp)) { BackBtn(back) }
        Spacer(Modifier.height(36.dp))
        Box(
            Modifier.size(84.dp).clip(RoundedCornerShape(26.dp))
                .background(Brush.linearGradient(listOf(Blue, BlueDeep))),
            contentAlignment = Alignment.Center
        ) { Text("🔒", fontSize = 38.sp) }
        Text(title, color = TextMain, fontSize = 24.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 24.dp))
        Text(lead, color = TextSoft, fontSize = 13.5.sp, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 8.dp, start = 16.dp, end = 16.dp))
        Row(Modifier.padding(top = 28.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            repeat(PIN_LEN) { i ->
                Box(
                    Modifier.size(14.dp).clip(CircleShape)
                        .background(if (i < pin.length) Blue else Color.Transparent)
                        .border(1.5.dp, Blue, CircleShape)
                )
            }
        }
        Text(if (busy) "Проверяю…" else msg, color = if (busy) TextSoft else Red, fontSize = 13.sp,
            textAlign = TextAlign.Center, modifier = Modifier.padding(top = 14.dp).height(36.dp))
        val keys = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫")
        for (row in keys.chunked(3)) {
            Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                for (k in row) {
                    val isDigit = k.length == 1 && k[0].isDigit()
                    Box(
                        Modifier.size(72.dp).clip(CircleShape)
                            .background(if (isDigit) Glass else Color.Transparent)
                            .border(1.dp, if (isDigit) GlassLine else Color.Transparent, CircleShape)
                            .clickable(enabled = k.isNotEmpty() && !busy) {
                                if (k == "⌫") pin = pin.dropLast(1)
                                else if (pin.length < PIN_LEN) {
                                    pin += k
                                    if (pin.length == PIN_LEN) done(pin)
                                }
                            },
                        contentAlignment = Alignment.Center
                    ) { Text(k, color = if (isDigit) TextMain else TextSoft, fontSize = if (isDigit) 26.sp else 20.sp) }
                }
            }
        }
        if (!first) Text("После ${ChatVault.MAX_FAILS} неверных попыток переписка стирается",
            color = TextDim, fontSize = 12.sp, modifier = Modifier.padding(top = 22.dp))
    }
}

// ---------------------------------------------------------------- общие кусочки

@Composable
private fun BackBtn(onClick: () -> Unit) {
    Box(
        Modifier.size(40.dp).clip(RoundedCornerShape(13.dp)).background(Glass)
            .border(1.dp, GlassLine, RoundedCornerShape(13.dp)).clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) { Text("‹", color = TextSoft, fontSize = 22.sp) }
}

@Composable
private fun Avatar(name: String, size: Int = 48) {
    Box(
        Modifier.size(size.dp).clip(CircleShape)
            .background(Brush.linearGradient(listOf(BlueDeep, Color(0xFF16223A))))
            .border(1.dp, Blue.copy(alpha = 0.3f), CircleShape),
        contentAlignment = Alignment.Center
    ) { Text(name.trim().take(1).uppercase().ifEmpty { "?" }, color = TextMain, fontSize = (size * 0.38).sp, fontWeight = FontWeight.Bold) }
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
        Column(Modifier.fillMaxSize().statusBarsPadding()) {
            Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                BackBtn(back)
                Text("Чаты", color = TextMain, fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(start = 12.dp).weight(1f))
                Box(
                    Modifier.size(40.dp).clip(RoundedCornerShape(13.dp)).background(Glass)
                        .border(1.dp, GlassLine, RoundedCornerShape(13.dp)).clickable(onClick = protect),
                    contentAlignment = Alignment.Center
                ) { Text("🛡", fontSize = 18.sp) }
            }
            Text("🔒 сквозное шифрование: сервер видит только шифр", color = Blue, fontSize = 12.sp,
                modifier = Modifier.padding(start = 22.dp, top = 8.dp))
            // мой код
            Row(
                Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 14.dp).clip(RoundedCornerShape(18.dp))
                    .background(Glass).border(1.dp, GlassLine, RoundedCornerShape(18.dp)).padding(horizontal = 16.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("МОЙ КОД", color = TextDim, fontSize = 11.sp, letterSpacing = 1.5.sp)
                    Text(if (ui.code.isEmpty()) "…" else Chat.pretty(ui.code), color = TextMain, fontSize = 22.sp,
                        fontWeight = FontWeight.Bold, fontFamily = FontFamily.Monospace, letterSpacing = 3.sp)
                }
                if (ui.code.isNotEmpty()) Text(
                    "Поделиться", color = Blue, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(Blue.copy(alpha = 0.14f))
                        .clickable {
                            val text = "Мой код в чате Arise VPN: ${Chat.pretty(ui.code)}"
                            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain")
                                .putExtra(Intent.EXTRA_TEXT, text), "Поделиться кодом").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }.padding(horizontal = 12.dp, vertical = 9.dp)
                )
            }
            ErrorLine(ui.error)
            val rows = (ui.contacts.map { it.code } + ui.msgs.keys).distinct()
                .sortedByDescending { ui.msgs[it]?.lastOrNull()?.t ?: 0L }
            if (rows.isEmpty()) {
                Text("Здесь будут ваши чаты.\nНажмите «＋» и введите код собеседника.", color = TextSoft, fontSize = 14.sp,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 60.dp))
            }
            LazyColumn(Modifier.fillMaxSize().padding(top = 6.dp)) {
                items(rows) { code ->
                    val c = ui.contacts.firstOrNull { it.code == code }
                    val name = c?.name ?: Chat.pretty(code)
                    val last = ui.msgs[code]?.lastOrNull()
                    Row(
                        Modifier.fillMaxWidth().clickable { open(code) }.padding(horizontal = 20.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Avatar(name)
                        Column(Modifier.weight(1f).padding(start = 12.dp)) {
                            Text(name, color = TextMain, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(
                                when {
                                    c?.keyChanged == true -> "⚠️ собеседник сменил ключ — сверьте код"
                                    last == null -> "⏱ сообщений нет"
                                    last.out -> "Вы: ${last.text}"
                                    else -> last.text
                                },
                                color = if (c?.keyChanged == true) Amber else TextSoft, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis
                            )
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            if (last != null) Text(hhmm(last.t), color = TextDim, fontSize = 12.sp)
                            val n = ui.unread[code] ?: 0
                            if (n > 0) Text("$n", color = Ink, fontSize = 11.5.sp, fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(top = 4.dp).clip(RoundedCornerShape(10.dp)).background(BlueMid)
                                    .padding(horizontal = 7.dp, vertical = 2.dp))
                        }
                    }
                }
            }
        }
        Box(
            Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(22.dp).size(60.dp)
                .clip(RoundedCornerShape(20.dp)).background(Brush.linearGradient(listOf(BlueLight, BlueMid)))
                .clickable(onClick = add),
            contentAlignment = Alignment.Center
        ) { Text("＋", color = Ink, fontSize = 30.sp) }
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
    LaunchedEffect(msgs.size) {
        if (msgs.isNotEmpty()) list.animateScrollToItem(msgs.size - 1)
        Chat.read(code)
    }
    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            BackBtn(back)
            Box(Modifier.padding(start = 10.dp).clickable(onClick = info)) { Avatar(name, 40) }
            Column(Modifier.weight(1f).padding(start = 10.dp).clickable(onClick = info)) {
                Text(name, color = TextMain, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    when {
                        c?.keyChanged == true -> "⚠️ ключ сменился — сверьте код"
                        c?.verified == true -> "🔒 код безопасности сверен"
                        else -> "🔒 зашифровано · код не сверен"
                    },
                    color = when {
                        c?.keyChanged == true -> Amber
                        c?.verified == true -> Green
                        else -> TextSoft
                    },
                    fontSize = 12.sp
                )
            }
            Box(
                Modifier.size(40.dp).clip(RoundedCornerShape(13.dp)).background(Glass)
                    .border(1.dp, GlassLine, RoundedCornerShape(13.dp)).clickable(onClick = info),
                contentAlignment = Alignment.Center
            ) { Text("⋯", color = TextSoft, fontSize = 18.sp) }
        }
        Text(
            if (ui.ttlHours > 0) "⏱ Сообщения исчезают через ${ttlText(ui.ttlHours)}" else "⏱ Самоудаление выключено",
            color = Blue, fontSize = 12.sp,
            modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 10.dp).clip(RoundedCornerShape(12.dp))
                .background(Blue.copy(alpha = 0.10f)).border(1.dp, Blue.copy(alpha = 0.2f), RoundedCornerShape(12.dp))
                .padding(horizontal = 12.dp, vertical = 6.dp)
        )
        ErrorLine(ui.error)
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().padding(horizontal = 14.dp), state = list,
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(msgs, key = { it.id }) { m ->
                Box(Modifier.fillMaxWidth(), contentAlignment = if (m.out) Alignment.CenterEnd else Alignment.CenterStart) {
                    Column(
                        Modifier.widthIn(max = 300.dp)
                            .clip(RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp, bottomStart = if (m.out) 18.dp else 6.dp, bottomEnd = if (m.out) 6.dp else 18.dp))
                            .background(if (m.out) Brush.linearGradient(listOf(Color(0xFF4A86F0), BlueDeep)) else Brush.linearGradient(listOf(Color(0x12FFFFFF), Color(0x12FFFFFF))))
                            .padding(horizontal = 13.dp, vertical = 9.dp)
                    ) {
                        Text(m.text, color = TextMain, fontSize = 14.5.sp)
                        Text(hhmm(m.t) + if (m.exp > 0) " · ⏱" else "", color = TextMain.copy(alpha = 0.6f), fontSize = 10.5.sp,
                            modifier = Modifier.align(Alignment.End).padding(top = 2.dp))
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = text, onValueChange = { text = it.take(4000) },
                placeholder = { Text("Сообщение", color = TextDim) }, shape = RoundedCornerShape(18.dp),
                modifier = Modifier.weight(1f), maxLines = 5,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = TextMain, unfocusedTextColor = TextMain,
                    focusedBorderColor = Blue.copy(alpha = 0.6f), unfocusedBorderColor = GlassLine,
                    focusedContainerColor = Glass, unfocusedContainerColor = Glass, cursorColor = Blue
                )
            )
            Box(
                Modifier.padding(start = 10.dp).size(50.dp).clip(RoundedCornerShape(16.dp))
                    .background(Brush.linearGradient(listOf(BlueLight, BlueMid)))
                    .clickable(enabled = text.isNotBlank() && c != null) {
                        Chat.send(code, text.trim())
                        text = ""
                    },
                contentAlignment = Alignment.Center
            ) { Text("➤", color = Ink, fontSize = 20.sp) }
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
private fun ProtectScreen(ui: ChatUi, back: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var dialog by remember { mutableStateOf("") }  // "pin" | "decoy" | "wipe"
    var input by remember { mutableStateOf("") }
    var msg by remember { mutableStateOf("") }
    LaunchedEffect(ui.admin) { if (ui.admin) Chat.refreshAdmin() }
    Page("Защита", "", back) {
        Section("Переписка")
        Tool("⏱", "Самоудаление", "Для новых сообщений, у обоих собеседников", ttlText(ui.ttlHours) + " ›") {
            val next = listOf(1, 24, 168, 0)
            Chat.setTtl(next[(next.indexOf(ui.ttlHours) + 1).mod(next.size)])
        }
        ToggleRow("🚫", "Запрет скриншотов и превью в «недавних»", ui.noScreens) { Chat.setNoScreens(!ui.noScreens) }
        ToggleRow("⏲", "Закрывать чат, если свернули приложение", ui.lockOnLeave) { Chat.setLockOnLeave(!ui.lockOnLeave) }
        if (!ui.decoy) {
            Section("Вход")
            Tool("🔑", "Сменить PIN", "6 цифр", "›") { dialog = "pin"; input = ""; msg = "" }
            Tool("🎭", "Ложный PIN", "Открывает пустой чат — если заставят разблокировать",
                if (ui.hasDecoy) "Задан ›" else "Задать ›") { dialog = "decoy"; input = ""; msg = "" }
            if (dialog == "pin" || dialog == "decoy") {
                Field(input, if (dialog == "pin") "Новый PIN, 6 цифр" else "Ложный PIN, 6 цифр") {
                    input = it.filter { ch -> ch.isDigit() }.take(PIN_LEN)
                }
                if (msg.isNotEmpty()) Text(msg, color = Red, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
                Spacer(Modifier.height(10.dp))
                Big("Сохранить", gold = true) {
                    if (input.length != PIN_LEN) {
                        msg = "Нужно 6 цифр"
                        return@Big
                    }
                    val what = dialog
                    val value = input
                    scope.launch {
                        val e = withContext(Dispatchers.IO) { if (what == "pin") Chat.changePin(value) else Chat.setDecoy(value) }
                        if (e == null) {
                            dialog = ""
                            Toast.makeText(ctx, if (what == "pin") "PIN изменён" else "Ложный PIN задан", Toast.LENGTH_SHORT).show()
                        } else msg = e
                    }
                }
                if (dialog == "decoy" && ui.hasDecoy) {
                    Spacer(Modifier.height(8.dp))
                    Big("Убрать ложный PIN", gold = false) { Chat.dropDecoy(); dialog = "" }
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
            ToggleRow("💬", "Чат для всех (выключить — гости не смогут писать)", ui.enabled) { Chat.setEnabled(!ui.enabled) }
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatBox("Устройств в чате", ui.adminUsers.toString(), Modifier.weight(1f))
                StatBox("Ждут доставки", ui.adminQueued.toString(), Modifier.weight(1f))
            }
            Note("Админ видит только цифры. Прочитать чужие сообщения не может никто — ни админ, ни сервер.")
        }
        val clip = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        if (ui.code.isNotEmpty() && !ui.decoy) {
            Section("Мой код")
            Tool("📋", Chat.pretty(ui.code), "Скопировать", "›") {
                clip.setPrimaryClip(ClipData.newPlainText("code", Chat.pretty(ui.code)))
                Toast.makeText(ctx, "Код скопирован", Toast.LENGTH_SHORT).show()
            }
        }
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
