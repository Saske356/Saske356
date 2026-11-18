package io.github.saske356.arise

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.sin

// Экраны по HTML-макету design/mock (screens.py): шторка стран, инструменты, режимы.
// Размеры в макете — px при ширине 393, здесь те же числа в dp.

// ---------------------------------------------------------------- общие детали макета

/** Шеврон «›» как в макете (.chev): две черты, #8fb5ff. */
@Composable
internal fun Chev(len: Dp = 9.dp, color: Color = Color(0xFF8FB5FF)) {
    Canvas(Modifier.padding(start = 4.dp, end = 6.dp).size(len + 4.dp)) {
        val w = 2.4.dp.toPx()
        val s = len.toPx()
        val x0 = (this.size.width - s * 0.55f) / 2f
        val y0 = (this.size.height - s * 1.1f) / 2f
        val p = Path().apply {
            moveTo(x0, y0); lineTo(x0 + s * 0.55f, y0 + s * 0.55f); lineTo(x0, y0 + s * 1.1f)
        }
        drawPath(p, color, style = Stroke(w, cap = StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round))
    }
}

/** Круглая кнопка (.circ / .back): тёмное стекло со светлой рамкой. */
@Composable
internal fun Circ(size: Dp, onClick: (() -> Unit)? = null, glow: Boolean = false, content: @Composable () -> Unit) {
    Box(
        Modifier
            .then(if (glow) Modifier.neon(size / 2, spread = 8.dp, alpha = 0.6f) else Modifier)
            .then(if (onClick != null) Modifier.pressable(onClick = onClick) else Modifier)
            .size(size)
            .clip(CircleShape)
            .background(Brush.radialGradient(listOf(Color(0x8C28468C), Color(0xBF0A1228))))
            .border(1.dp, Color(0x736EA0FF), CircleShape),
        contentAlignment = Alignment.Center
    ) { content() }
}

/** Кнопка-обводка справа в строке инструмента (.act): «Настроить ›». */
@Composable
internal fun ActPill(text: String) {
    Row(
        Modifier.height(28.dp).clip(RoundedCornerShape(14.dp))
            .background(Color(0x8C0E1C3C)).border(1.dp, Color(0x9982AFFF), RoundedCornerShape(14.dp))
            .padding(start = 14.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(text, color = TextMain, fontSize = 12.5.sp, maxLines = 1)
        Chev(8.dp)
    }
}

/** Земля в правом верхнем углу страниц (.earthtop): та же картинка, приглушённая и растворённая по краям. */
@Composable
internal fun EarthTop() {
    Box(Modifier.fillMaxSize()) {
        Image(
            painterResource(R.drawable.globe_gpt), contentDescription = null,
            modifier = Modifier
                .align(Alignment.TopEnd)
                .offset(x = 120.dp)
                .requiredSize(420.dp)
                .graphicsLayer { alpha = 0.55f; compositingStrategy = CompositingStrategy.Offscreen }
                .drawWithContent {
                    drawContent()
                    val c = Offset(size.width * 0.6f, size.height * 0.3f)
                    val r = size.width * 0.922f
                    drawRect(
                        Brush.radialGradient(0f to Color.Black, 0.30f to Color.Black, 0.62f to Color.Transparent, center = c, radius = r),
                        blendMode = BlendMode.DstIn
                    )
                }
        )
    }
}

/** Шапка страницы (.pagehead): круглая «назад» 40 dp и заголовок 21 sp. */
@Composable
internal fun PageHead(title: String, back: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 12.dp).height(40.dp)) {
        Circ(40.dp, back, glow = true) { LineIcon(Ico.BACK, 18.dp, Color(0xFFDBE8FF)) }
        Text(title, color = TextMain, fontSize = 21.sp, fontWeight = FontWeight.Bold, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(start = 16.dp))
    }
}

@Composable
internal fun Page(title: String, lead: String, back: () -> Unit, content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        EarthTop()
        Column(
            Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 14.dp)
        ) {
            Box(Modifier.padding(horizontal = 3.dp)) { PageHead(title, back) }
            if (lead.isNotEmpty()) Text(lead, color = Color(0xFFD0DDF5), fontSize = 13.sp, lineHeight = 17.5.sp,
                modifier = Modifier.padding(start = 7.dp, end = 7.dp, top = 12.dp, bottom = 14.dp))
            else Spacer(Modifier.height(20.dp))
            content()
            Spacer(Modifier.height(28.dp))
        }
    }
}

// ---------------------------------------------------------------- выбор страны (шторка)

@Composable
internal fun CountrySheet(open: Boolean, vpn: VpnUi, data: Data, close: () -> Unit, onPick: (String) -> Unit) {
    AnimatedVisibility(open, enter = fadeIn(tween(300)), exit = fadeOut(tween(300))) {
        Box(Modifier.fillMaxSize().background(Color(0x8C01040C)).clickable(
            interactionSource = remember { MutableInteractionSource() }, indication = null, onClick = close))
    }
    // Открыли список — свежий замер, если последний был больше минуты назад
    LaunchedEffect(open) { if (open) Repo.pingIfStale(60_000L) }
    AnimatedVisibility(
        open,
        enter = slideInVertically(tween(450, easing = androidx.compose.animation.core.CubicBezierEasing(0.2f, 0.9f, 0.25f, 1f))) { it },
        exit = slideOutVertically(tween(320)) { it }
    ) {
        var query by remember { mutableStateOf("") }
        var byPing by remember { mutableStateOf(true) }
        val shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
        Box(Modifier.fillMaxSize()) {
            Column(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .fillMaxHeight(0.73f)
                    .drawBehind {
                        // синий отсвет над краем шторки
                        drawRect(Brush.verticalGradient(listOf(Color.Transparent, Color(0x592864FF)), -40.dp.toPx(), 0f),
                            topLeft = Offset(0f, -40.dp.toPx()), size = Size(size.width, 40.dp.toPx()))
                    }
                    .clip(shape)
                    .background(Brush.verticalGradient(listOf(Color(0xF70E1C3E), Color(0xFC040918))))
                    .border(1.5.dp, Brush.verticalGradient(listOf(Color(0xBF78AAFF), Color(0x0078AAFF)), 0f, 120f), shape)
                    // касания по самому окну не закрывают его (под ним — затемнение, которое закрывает)
                    .clickable(interactionSource = remember { MutableInteractionSource() }, indication = null) { }
                    .navigationBarsPadding()
                    .padding(horizontal = 16.dp)
            ) {
                Box(Modifier.fillMaxWidth().padding(top = 11.dp), contentAlignment = Alignment.Center) {
                    Box(Modifier.width(44.dp).height(5.dp).clip(RoundedCornerShape(3.dp)).background(Color(0xFF5D8FE8)))
                }
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 16.dp)) {
                    Circ(40.dp) { LineIcon(Ico.GLOBE, 24.dp, BlueLight) }
                    Text("Выберите страну", color = TextMain, fontSize = 21.sp, fontWeight = FontWeight.Bold,
                        modifier = Modifier.weight(1f).padding(start = 12.dp))
                    Circ(36.dp, close) { LineIcon(Ico.CLOSE, 14.dp, Color.White) }
                }
                Row(
                    Modifier.fillMaxWidth().padding(top = 14.dp).height(40.dp).clip(RoundedCornerShape(20.dp))
                        .background(Color(0x990E1C3C)).border(1.dp, Color(0x736EA0FF), RoundedCornerShape(20.dp))
                        .padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    LineIcon(Ico.SEARCH, 20.dp, Color(0xFF8FA8D8))
                    Spacer(Modifier.width(12.dp))
                    Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) {
                        if (query.isEmpty()) Text("Поиск страны", color = Color(0xFF8FA8D8), fontSize = 15.sp)
                        BasicTextField(
                            value = query, onValueChange = { query = it.take(40) }, singleLine = true,
                            textStyle = TextStyle(color = Color(0xFFEEF4FF), fontSize = 15.sp, fontFamily = Inter),
                            cursorBrush = SolidColor(Blue), modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
                // Все страны без связи при выключенном VPN — показываем причину (для разбора)
                if (vpn.status != Status.RUNNING && data.pingError.isNotEmpty() &&
                    data.pings.isNotEmpty() && data.pings.values.none { it > 0 } && data.measuring.isEmpty()
                ) Text("Замер без VPN: ${data.pingError}", color = TextDim, fontSize = 11.5.sp,
                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 4.dp))
                // одинаковые названия (например, страна и её копия через мост) роняли список: ключи должны быть разными
                val list = data.servers.distinctBy { it.name }
                    .filter { query.isBlank() || it.name.contains(query.trim(), ignoreCase = true) }
                val special = list.filter { it.name.startsWith("🚀") || it.name.startsWith("🎮") }
                var rest = list - special.toSet()
                if (byPing) {
                    // по пингу: быстрые сверху, без замера и без связи — в конце
                    rest = rest.sortedBy { val p = data.pings[it.name] ?: 0L; if (p > 0) p else Long.MAX_VALUE }
                }
                LazyColumn(Modifier.fillMaxSize()) {
                    if (special.isNotEmpty()) {
                        item { SheetLabel("РЕКОМЕНДУЕМ") }
                        item {
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                for (s in special) RecommendTile(s, data, Modifier.weight(1f), onPick)
                                if (special.size == 1) Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                    item {
                        SheetLabel("ВСЕ СТРАНЫ") {
                            Text(
                                if (byPing) "⇅ По пингу ⌄" else "⇅ По списку ⌄", color = Color(0xFFC7D8FF), fontSize = 12.5.sp,
                                fontWeight = FontWeight.Medium,
                                modifier = Modifier.clip(RoundedCornerShape(15.dp)).background(Color(0x800E1C3C))
                                    .border(1.dp, Color(0x736EA0FF), RoundedCornerShape(15.dp))
                                    .clickable { byPing = !byPing }.padding(horizontal = 12.dp, vertical = 6.dp)
                            )
                        }
                    }
                    items(rest, key = { "c:" + it.name }) { s ->
                        Box(Modifier.animateItem().padding(vertical = 3.dp)) { CountryRow(s, vpn, data, onPick) }
                    }
                    item { Spacer(Modifier.height(20.dp)) }
                }
            }
        }
    }
}

@Composable
private fun SheetLabel(text: String, right: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(start = 2.dp, end = 2.dp, top = 18.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(text, color = Color(0xFFC7D8FF), fontSize = 13.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.4.sp,
            modifier = Modifier.weight(1f))
        right()
    }
}

/** «Лучший сервер» / «Игры» — две плитки в ряд (.rec .card). */
@Composable
private fun RecommendTile(s: Server, data: Data, modifier: Modifier, onPick: (String) -> Unit) {
    val (icon, title) = splitFlag(s.name)
    val selected = s.name == data.selected
    val note = if (s.name.startsWith("🚀")) "Выбирает самый быстрый сам" else "Напрямую, ровный пинг"
    Row(
        modifier.pressable { onPick(s.name) }.glass(20.dp, glow = selected).height(67.dp).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier.size(44.dp).neon(22.dp, spread = 8.dp, alpha = 0.5f).clip(CircleShape)
                .background(Brush.radialGradient(listOf(Color(0x8C3C78FF), Color(0x330E1A36)))),
            contentAlignment = Alignment.Center
        ) { EmojiIcon(icon, 30.dp) }
        Column(Modifier.weight(1f).padding(start = 8.dp)) {
            Text(title, color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(note, color = Color(0xFFB9C9E8), fontSize = 10.5.sp, maxLines = 2, lineHeight = 13.sp)
        }
        if (selected) LineIcon(Ico.CHECK, 16.dp, Blue) else Chev(8.dp)
    }
}

@Composable
private fun CountryRow(s: Server, vpn: VpnUi, data: Data, onPick: (String) -> Unit) {
    val (flag, title) = splitFlag(s.name)
    val selected = s.name == data.selected
    val ping = if (vpn.status == Status.RUNNING && vpn.server == s.name && vpn.ping != 0L) vpn.ping else data.pings[s.name] ?: 0L
    val busy = s.name in data.measuring
    val shown = if (busy && ping < 0) 0L else ping
    val note = if (s.name.contains("🇷🇺") || s.name.contains("Обход", true)) " · белые списки" else ""
    val shape = RoundedCornerShape(if (selected) 21.5.dp else 19.dp)
    Row(
        Modifier
            .fillMaxWidth()
            .pressable { onPick(s.name) }
            .then(if (selected) Modifier.neon(21.5.dp, spread = 10.dp, alpha = 0.9f) else Modifier)
            .clip(shape)
            .background(Brush.verticalGradient(listOf(Color(0xBF162854), Color(0xCC081026))))
            .then(if (selected) Modifier.background(Brush.radialGradient(listOf(Color(0x003C82FF), Color(0x333C82FF)), radius = 600f)) else Modifier)
            .border(if (selected) 1.5.dp else 1.dp, if (selected) Color(0xFF8FBAFF) else Color(0x808CB9FF), shape)
            .height(if (selected) 43.dp else 38.dp)
            .padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(28.dp).clip(CircleShape), contentAlignment = Alignment.Center) {
            if (icoFor(flag) != null) EmojiIcon(flag, 22.dp) else Text(flag, fontSize = 24.sp)
        }
        Text(title + note, color = TextMain, fontSize = 14.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).padding(start = 16.dp))
        PingDot(shown)
        Text(
            when {
                ping > 0 -> "$ping мс"
                busy -> "…"           // меряется прямо сейчас: старое «нет связи» не показываем
                ping < 0 -> "нет связи"
                else -> "—"
            },
            color = if (ping < 0 && !busy) Color(0xFFFF8A94) else TextMain, fontSize = 13.sp, maxLines = 1,
            modifier = Modifier.widthIn(min = 56.dp).padding(start = 7.dp)
        )
        Box(Modifier.padding(start = 4.dp, end = 14.dp)) { SmallBars(shown) }
        if (selected) {
            Box(
                Modifier.size(26.dp).neon(13.dp, spread = 6.dp, alpha = 0.8f).clip(CircleShape).background(Color(0xFF2F6BFF))
                    .border(1.dp, Color(0xFF9CC2FF), CircleShape),
                contentAlignment = Alignment.Center
            ) { LineIcon(Ico.CHECK, 15.dp, Color.White) }
        } else Chev()
    }
}

/** Точка цвета пинга со свечением (.d.g/.y/.rd/.n). */
@Composable
internal fun PingDot(ping: Long) {
    val c = when {
        ping == 0L -> Color(0xFF7E8AA8)
        ping < 0 -> Color(0xFFFF4D5E)
        ping < 120 -> Color(0xFF3AD15C)
        ping < 450 -> Color(0xFFF5C33B)
        else -> Color(0xFFFF4D5E)
    }
    Box(
        Modifier.size(8.dp).drawBehind {
            if (c != Color(0xFF7E8AA8)) drawCircle(c.copy(alpha = 0.35f), size.minDimension)
        }.clip(CircleShape).background(c)
    )
}

/** Полоски связи в строке страны (.row .bars): 3 dp, до 13 dp, серые без связи. */
@Composable
private fun SmallBars(ping: Long) {
    val level = when {
        ping <= 0 -> 0
        ping < 120 -> 4
        ping < 250 -> 3
        ping < 450 -> 2
        else -> 1
    }
    val on = if (level >= 3) Color(0xFF3FD462) else if (level == 2) Color(0xFFF5C33B) else Color(0xFFFF4D5E)
    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(2.5.dp), modifier = Modifier.height(13.dp)) {
        for ((i, h) in listOf(4f, 6.5f, 9.75f, 13f).withIndex()) {
            Box(Modifier.width(3.dp).height(h.dp).clip(RoundedCornerShape(2.dp))
                .background(if (level == 0) Color(0xFF5F6F90) else if (i < level) on else Color(0x33FFFFFF)))
        }
    }
}

// ---------------------------------------------------------------- режимы

@Composable
internal fun ModesScreen(data: Data, back: () -> Unit, onPick: (Mode) -> Unit) {
    Page("Режим соединения", "Каждый режим по-настоящему меняет настройки VPN. Чем-то всегда жертвуем — честно пишем, чем.", back) {
        for (m in Mode.entries) {
            val sel = m == data.mode
            val shape = RoundedCornerShape(24.dp)
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 0.dp, vertical = 6.dp)
                    .pressable { onPick(m) }
                    .then(if (sel) Modifier.neon(24.dp, spread = 18.dp, alpha = 1f) else Modifier)
                    .clip(shape)
                    .background(Brush.verticalGradient(listOf(Color(0xB8162854), Color(0xC7081026))))
                    .then(if (sel) Modifier.background(Brush.radialGradient(listOf(Color(0x003C82FF), Color(0x473C82FF)), radius = 900f)) else Modifier)
                    .border(if (sel) 2.dp else 1.dp, if (sel) Color(0xFFB3D2FF) else Color(0x8C8CB9FF), shape)
            ) {
                Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 34.dp, top = 14.dp, bottom = 14.dp)) {
                    Box(
                        Modifier.padding(top = 4.dp).size(60.dp).neon(20.dp, spread = 8.dp, alpha = 0.4f)
                            .clip(RoundedCornerShape(20.dp))
                            .background(Brush.radialGradient(listOf(Color(0x733C78FF), Color(0x590E1A36))))
                            .border(1.dp, Color(0x736EA0FF), RoundedCornerShape(20.dp)),
                        contentAlignment = Alignment.Center
                    ) { EmojiIcon(m.emoji, 46.dp) }
                    Column(Modifier.weight(1f).padding(start = 14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(m.title, color = TextMain, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                            if (m == Mode.BALANCE) Text(
                                "★ Рекомендуем", color = Color(0xFFCFE0FF), fontSize = 11.5.sp, maxLines = 1,
                                modifier = Modifier.padding(start = 8.dp).clip(RoundedCornerShape(11.dp))
                                    .background(Color(0x801E3C8C)).border(1.dp, Color(0x996EA0FF), RoundedCornerShape(11.dp))
                                    .padding(horizontal = 9.dp, vertical = 3.dp)
                            )
                        }
                        Text(m.desc, color = Color(0xFFC4D6F8), fontSize = 12.sp, lineHeight = 15.6.sp, modifier = Modifier.padding(top = 3.dp))
                        if (sel) ModeSplit(m) else Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            ModeChip(true, m.plus)
                            ModeChip(false, m.minus)
                        }
                    }
                }
                if (sel) Box(
                    Modifier.align(Alignment.TopEnd).padding(top = 10.dp, end = 14.dp).size(36.dp)
                        .neon(18.dp, spread = 8.dp, alpha = 0.9f).clip(CircleShape).background(Color(0xFF2F6BFF))
                        .border(1.5.dp, Color(0xFFCFE0FF), CircleShape),
                    contentAlignment = Alignment.Center
                ) { LineIcon(Ico.CHECK, 18.dp, Color.White) }
                else Box(Modifier.align(Alignment.CenterEnd).padding(end = 12.dp)) { Chev() }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(start = 18.dp, end = 16.dp, top = 12.dp).glass(18.dp).height(44.dp).padding(horizontal = 18.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            LineIcon(Ico.INFO, 26.dp, Blue)
            Text("Выбранный режим можно изменить\nв любое время", color = Color(0xFFB8C9EA), fontSize = 13.sp, lineHeight = 16.sp,
                modifier = Modifier.padding(start = 16.dp))
        }
    }
}

private val PlusGreen = Color(0xFF2FCF5A)
private val MinusOrange = Color(0xFFF5A03B)

/** Метка «плюс/минус» у невыбранного режима (.chip). */
@Composable
private fun ModeChip(plus: Boolean, text: String) {
    if (text.isEmpty()) return
    val c = if (plus) PlusGreen else MinusOrange
    Row(
        Modifier.clip(RoundedCornerShape(13.dp))
            .background(if (plus) Color(0x2928A050) else Color(0x24DC7828))
            .border(1.dp, if (plus) Color(0x593CC864) else Color(0x59F0963C), RoundedCornerShape(13.dp))
            .padding(start = 3.dp, end = 7.dp, top = 3.dp, bottom = 3.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(16.dp).clip(CircleShape).background(c), contentAlignment = Alignment.Center) {
            Text(if (plus) "+" else "−", color = Color(0xFF08121E), fontSize = 13.sp, fontWeight = FontWeight.Bold, lineHeight = 13.sp)
        }
        Text(text.replace('\n', ' '), color = if (plus) Color(0xFF9CF0B0) else Color(0xFFFFC08A), fontSize = 10.sp, maxLines = 1,
            modifier = Modifier.padding(start = 5.dp))
    }
}

/** Плюс и минус выбранного режима — в две колонки под чертой (.split). */
@Composable
private fun ModeSplit(m: Mode) {
    Column(Modifier.padding(top = 9.dp)) {
        Box(Modifier.fillMaxWidth().height(1.dp).background(Color(0x406EA0FF)))
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            for ((plus, text) in listOf(true to m.plus, false to m.minus)) {
                if (!plus) Box(Modifier.width(1.dp).height(28.dp).background(Color(0x406EA0FF)))
                Row(Modifier.weight(1f).padding(start = if (plus) 0.dp else 14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(20.dp).clip(CircleShape).background(if (plus) PlusGreen else MinusOrange), contentAlignment = Alignment.Center) {
                        Text(if (plus) "+" else "−", color = Color(0xFF08121E), fontSize = 14.sp, fontWeight = FontWeight.Bold, lineHeight = 14.sp)
                    }
                    Text(text, color = TextMain, fontSize = 10.5.sp, lineHeight = 13.sp, modifier = Modifier.padding(start = 9.dp, end = 4.dp))
                }
            }
        }
    }
}

// ---------------------------------------------------------------- инструменты

@Composable
internal fun ToolsScreen(
    data: Data, back: () -> Unit, onApps: () -> Unit, onLeak: () -> Unit, onTile: () -> Unit,
    onDns: () -> Unit, onForget: () -> Unit,
) {
    val ctx = LocalContext.current
    val speed by SpeedState.flow.collectAsState()
    Page("Инструменты", "", back) {
        // карточка теста скорости (.speed): 172 dp, циферблат 78, кнопка 154×34, полоса цифр 60
        Column(
            Modifier.fillMaxWidth().padding(horizontal = 1.dp)
                .neon(24.dp, spread = 14.dp, alpha = 0.7f)
                .clip(RoundedCornerShape(24.dp))
                .background(Brush.verticalGradient(listOf(Color(0xB8162854), Color(0xC7081026))))
                .border(1.dp, Color(0xBF82B4FF), RoundedCornerShape(24.dp))
                .padding(8.dp)
        ) {
            Row(Modifier.padding(start = 4.dp, top = 4.dp), verticalAlignment = Alignment.Top) {
                Gauge(if (speed.running) 0.85f else if (speed.downMbps > 0) 0.7f else 0.45f, Modifier.size(78.dp))
                Column(Modifier.weight(1f).padding(start = 14.dp, top = 2.dp)) {
                    Text("Тест скорости", color = TextMain, fontSize = 19.sp, fontWeight = FontWeight.Bold, lineHeight = 23.sp)
                    Text(if (speed.running) speed.stage.ifBlank { "Проверяю…" } else "Проверьте ваше соединение",
                        color = TextSoft, fontSize = 12.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Row(
                        Modifier.padding(top = 8.dp).width(154.dp).height(34.dp)
                            .pressable(enabled = !speed.running) { Repo.speedTest() }
                            .neon(17.dp, spread = 8.dp, alpha = 0.7f)
                            .clip(RoundedCornerShape(17.dp))
                            .background(Brush.verticalGradient(listOf(Color(0xFF4A86FF), Color(0xFF1D4FD8))))
                            .border(1.dp, Color(0xCCBED7FF), RoundedCornerShape(17.dp)),
                        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically
                    ) {
                        if (!speed.running) {
                            Canvas(Modifier.width(12.dp).height(14.dp)) {
                                drawPath(Path().apply { moveTo(0f, 0f); lineTo(size.width, size.height / 2); lineTo(0f, size.height); close() }, Color.White)
                            }
                            Spacer(Modifier.width(10.dp))
                        }
                        Text(if (speed.running) "Идёт проверка…" else "Начать", color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
            Row(
                Modifier.fillMaxWidth().padding(top = 12.dp).height(60.dp).clip(RoundedCornerShape(16.dp))
                    .background(Color(0x99081026)).border(1.dp, Color(0x596EA0FF), RoundedCornerShape(16.dp)),
                verticalAlignment = Alignment.CenterVertically
            ) {
                SpeedMetric(Ico.DOWN, "Загрузка", if (speed.downMbps > 0) "%.0f Мбит/с".format(speed.downMbps) else "—", Modifier.weight(1f))
                Box(Modifier.width(1.dp).fillMaxHeight().padding(vertical = 10.dp).background(Color(0x4D6EA0FF)))
                SpeedMetric(Ico.UP, "Отдача", if (speed.upMbps > 0) "%.0f Мбит/с".format(speed.upMbps) else "—", Modifier.weight(1f))
                Box(Modifier.width(1.dp).fillMaxHeight().padding(vertical = 10.dp).background(Color(0x4D6EA0FF)))
                SpeedMetric(Ico.CLOCK, "Пинг", if (speed.ping > 0) "${speed.ping} мс" else "—", Modifier.weight(1f))
            }
            if (speed.ping > 0 && !speed.running) Text("джиттер ${speed.jitter} мс", color = TextDim, fontSize = 11.sp,
                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 4.dp))
            if (speed.error.isNotEmpty()) Text(speed.error, color = Color(0xFFFF8A94), fontSize = 12.5.sp, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp))
        }
        Spacer(Modifier.height(16.dp))
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
        Row(Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(54.dp).height(1.dp).background(Color(0x596EA0FF)))
            Text("Arise VPN ${BuildConfig.VERSION_NAME}", color = TextDim, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 14.dp))
            Box(Modifier.width(54.dp).height(1.dp).background(Color(0x596EA0FF)))
        }
    }
}

/** Циферблат теста скорости (как SVG в макете): дуга с градиентом, риски, стрелка. */
@Composable
private fun Gauge(level: Float, modifier: Modifier) {
    val lv by androidx.compose.animation.core.animateFloatAsState(level, tween(700), label = "gauge")
    Canvas(modifier) {
        val k = size.minDimension / 80f
        val c = Offset(40f * k, 44f * k)
        val r = 32f * k
        val w = 7f * k
        // дуга 240° (снизу слева через верх вниз направо), свечение — та же дуга толще и прозрачнее
        val tl = Offset(c.x - r, c.y - r)
        val sz = Size(r * 2, r * 2)
        drawArc(Color(0x553D7BFF), 150f, 240f, false, tl, sz, style = Stroke(w * 2.2f, cap = StrokeCap.Round))
        drawArc(Brush.linearGradient(listOf(Color(0xFF1F4FD6), Color(0xFF8CC0FF)), Offset(0f, size.height), Offset(size.width, 0f)),
            150f, 240f, false, tl, sz, style = Stroke(w, cap = StrokeCap.Round))
        for (deg in listOf(-90f, -135f, -45f, 180f, 0f)) {
            val a = Math.toRadians(deg.toDouble())
            val r1 = r - 8f * k
            val r2 = r - 14f * k
            drawLine(Color(0xFF4F8DFF), Offset(c.x + (cos(a) * r1).toFloat(), c.y + (sin(a) * r1).toFloat()),
                Offset(c.x + (cos(a) * r2).toFloat(), c.y + (sin(a) * r2).toFloat()), 2.5f * k, StrokeCap.Round)
        }
        val a = Math.toRadians(150.0 + 240.0 * lv)
        val rn = 22f * k
        drawLine(Color(0xFF8CC0FF), c, Offset(c.x + (cos(a) * rn).toFloat(), c.y + (sin(a) * rn).toFloat()), 4f * k, StrokeCap.Round)
        drawCircle(Color(0xFF0B1630), 6f * k, c)
        drawCircle(Color(0xFF8CC0FF), 6f * k, c, style = Stroke(3f * k))
    }
}

@Composable
private fun SpeedMetric(ico: Ico, k: String, v: String, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        LineIcon(ico, 17.dp, Blue)
        Text(k, color = Color(0xFFDBE6FB), fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp))
        Text(v, color = TextMain, fontSize = 14.sp, fontWeight = FontWeight.Medium, maxLines = 1)
    }
}

/** Строка инструмента (.tool): 50 dp, квадрат со значком 42, справа кнопка-обводка, значение или переключатель. */
@Composable
internal fun Tool(icon: String, title: String, sub: String, right: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(bottom = 6.dp)
            .pressable(onClick = onClick)
            .glass(18.dp)
            .heightIn(min = 50.dp)
            .padding(start = 9.dp, end = 10.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier.size(42.dp).clip(RoundedCornerShape(13.dp))
                .background(Brush.radialGradient(listOf(Color(0x663C78FF), Color(0x4D0E1A36))))
                .border(1.dp, Color(0x666EA0FF), RoundedCornerShape(13.dp)),
            contentAlignment = Alignment.Center
        ) { EmojiIcon(icon, 30.dp) }
        Column(Modifier.weight(1f).padding(start = 14.dp, end = 8.dp)) {
            Text(title, color = TextMain, fontSize = 14.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(sub, color = Color(0xFFB9C9E8), fontSize = 11.5.sp, lineHeight = 14.sp, maxLines = 2)
        }
        when {
            right == "Вкл" || right == "Выкл" -> MiniSwitch(right == "Вкл")
            right.endsWith("›") -> {
                val v = right.removeSuffix("›").trim()
                if (v.isNotEmpty()) Text(v, color = TextMain, fontSize = 14.sp, maxLines = 1, modifier = Modifier.padding(end = 4.dp))
                Chev()
            }
            right.isEmpty() -> Chev()
            right == "…" -> Text("…", color = TextMain, fontSize = 14.sp, modifier = Modifier.padding(end = 8.dp))
            else -> ActPill(right)
        }
    }
}

/** Переключатель в строке (.sw): синий со свечением, вся строка нажимается. */
@Composable
internal fun MiniSwitch(on: Boolean) {
    val x by androidx.compose.animation.core.animateDpAsState(if (on) 24.dp else 2.dp, tween(300), label = "sw")
    Box(
        Modifier.width(50.dp).height(28.dp)
            .then(if (on) Modifier.neon(14.dp, spread = 7.dp, alpha = 0.7f) else Modifier)
            .clip(RoundedCornerShape(14.dp))
            .background(if (on) Brush.horizontalGradient(listOf(Color(0xFF1F4FD6), Color(0xFF4A86FF)))
            else Brush.horizontalGradient(listOf(Color(0xFF1A2233), Color(0xFF1A2233))))
            .border(1.dp, if (on) Color(0xB3BED7FF) else Color(0x4D8CB9FF), RoundedCornerShape(14.dp))
    ) {
        Box(Modifier.offset(x = x, y = 2.dp).size(22.dp).clip(CircleShape).background(if (on) Color.White else Color(0xFF7F8DAB)))
    }
}

// ---------------------------------------------------------------- свечение

/**
 * Мягкое свечение вокруг карточки (box-shadow 0 0 Npx синим из макета). Рисуется за элементом
 * кольцами, без тени Android — та у полупрозрачных карточек просвечивает тёмной полосой.
 * Ставить ДО clip/background.
 */
internal fun Modifier.neon(radius: Dp, color: Color = Color(0xFF3C82FF), spread: Dp = 12.dp, alpha: Float = 0.5f): Modifier =
    this.drawBehind {
        val steps = 8
        val sp = spread.toPx()
        val step = sp / steps
        for (i in 1..steps) {
            val d = step * (i - 0.5f)
            val a = alpha * 0.22f * (1f - (i - 1f) / steps) * (1f - (i - 1f) / steps)
            drawRoundRect(
                color.copy(alpha = a.coerceIn(0f, 1f)),
                topLeft = Offset(-d, -d), size = Size(size.width + 2 * d, size.height + 2 * d),
                cornerRadius = CornerRadius(radius.toPx() + d), style = Stroke(step * 1.05f)
            )
        }
    }
