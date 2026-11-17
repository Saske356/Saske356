package io.github.saske356.arise

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.res.imageResource
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.animation.core.RepeatMode
import androidx.compose.ui.composed
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Шрифт Inter (SIL OFL, файлы урезаны до латиницы и кириллицы — arise-app/design/Inter-LICENSE.txt). */
internal val Inter = androidx.compose.ui.text.font.FontFamily(
    androidx.compose.ui.text.font.Font(R.font.inter_regular, androidx.compose.ui.text.font.FontWeight.Normal),
    androidx.compose.ui.text.font.Font(R.font.inter_medium, androidx.compose.ui.text.font.FontWeight.Medium),
    androidx.compose.ui.text.font.Font(R.font.inter_semibold, androidx.compose.ui.text.font.FontWeight.SemiBold),
    androidx.compose.ui.text.font.Font(R.font.inter_bold, androidx.compose.ui.text.font.FontWeight.Bold),
)

// Общие детали нового стиля (образцы — design/gpt/*.png в корне репозитория).

/**
 * Нажатие с откликом: элемент чуть «проседает» под пальцем и пружинит обратно (как в макете).
 * Ставить ДО фона/рамки в цепочке модификаторов — тогда уменьшается вся карточка.
 */
internal fun Modifier.pressable(enabled: Boolean = true, onClick: () -> Unit): Modifier = composed {
    val src = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val sc by animateFloatAsState(
        if (pressed) 0.965f else 1f,
        androidx.compose.animation.core.spring(dampingRatio = 0.55f, stiffness = 700f), label = "press"
    )
    this.graphicsLayer { scaleX = sc; scaleY = sc }
        .clickable(interactionSource = src, indication = androidx.compose.foundation.LocalIndication.current,
            enabled = enabled, onClick = onClick)
}

/** Стеклянная карточка: тёмно-синее стекло, тонкая светлая рамка. */
internal fun Modifier.glass(radius: Dp = 18.dp, glow: Boolean = false): Modifier =
    this.clip(RoundedCornerShape(radius))
        .background(Brush.verticalGradient(listOf(Color(0x33223A6E), Color(0x1A0E1A36))))
        .border(1.dp, if (glow) Blue.copy(alpha = 0.75f) else Color(0x3A5B8CFF), RoundedCornerShape(radius))

// ---------------------------------------------------------------- знак Arise

/** Вершины знака «A со стрелкой вверх» (как в design/make_logo.py), в долях квадрата. */
private val MARK = listOf(
    628f to 265f, 1038f to 937f, 713f to 815f, 683f to 704f, 776f to 741f, 628f to 515f,
    480f to 741f, 573f to 704f, 543f to 815f, 218f to 937f,
)

private fun markPath(size: Size): Path {
    val w = size.minDimension
    val k = w / (1038f - 218f)
    val h = (937f - 265f) * k
    val ox = (size.width - w) / 2f
    val oy = (size.height - h) / 2f
    return Path().apply {
        MARK.forEachIndexed { i, (x, y) ->
            val px = ox + (x - 218f) * k
            val py = oy + (y - 265f) * k
            if (i == 0) moveTo(px, py) else lineTo(px, py)
        }
        close()
    }
}

/** Знак Arise, нарисованный кодом: чёткий в любом размере, со свечением. */
@Composable
internal fun AriseMark(size: Dp, glow: Float = 1f) {
    Canvas(Modifier.size(size)) {
        val path = markPath(this.size)
        if (glow > 0f) {
            for (i in 1..4) {
                drawPath(path, Color(0xFF2F6BFF).copy(alpha = 0.10f * glow),
                    style = Stroke(width = this.size.minDimension * 0.05f * i, join = StrokeJoin.Round))
            }
        }
        drawPath(path, Brush.verticalGradient(listOf(Color(0xFFE8F4FF), Color(0xFF2563FF))))
    }
}

// ---------------------------------------------------------------- глобус

private data class Geo(val lat: Float, val lon: Float)

/** «Огни городов»: скопления точек вокруг настоящих регионов, чтобы глобус читался как Земля. */
private val CITIES: List<Geo> by lazy {
    val centers = listOf(
        50f to 10f, 45f to 25f, 55f to 37f, 40f to -75f, 34f to -100f, 47f to -122f, 35f to 135f, 37f to 127f,
        30f to 115f, 22f to 78f, 1f to 104f, -23f to -46f, 6f to 3f, 30f to 31f, 25f to 55f, -33f to 151f,
        19f to -99f, 52f to 0f, 60f to 25f, 41f to 69f,
    )
    val rnd = java.util.Random(7)
    centers.flatMap { (la, lo) ->
        List(22) { Geo(la + rnd.nextGaussian().toFloat() * 4.5f, lo + rnd.nextGaussian().toFloat() * 7f) }
    }
}

private val ARCS = listOf(0 to 3, 0 to 6, 3 to 11, 0 to 9, 6 to 15, 2 to 14, 3 to 16, 9 to 10)
private val ARC_ENDS = listOf(
    50f to 10f, 45f to 25f, 55f to 37f, 40f to -75f, 34f to -100f, 47f to -122f, 35f to 135f, 37f to 127f,
    30f to 115f, 22f to 78f, 1f to 104f, -23f to -46f, 6f to 3f, 30f to 31f, 25f to 55f, -33f to 151f, 19f to -99f,
).map { Geo(it.first, it.second) }

/** Точка на кратчайшем пути между двумя городами (доля k), широта и долгота. */
private fun slerp(a: Geo, b: Geo, k: Float): Pair<Float, Float> {
    fun vec(g: Geo): FloatArray {
        val la = g.lat * PI.toFloat() / 180f
        val lo = g.lon * PI.toFloat() / 180f
        return floatArrayOf(cos(la) * cos(lo), cos(la) * sin(lo), sin(la))
    }
    val p = vec(a)
    val q = vec(b)
    val dot = (p[0] * q[0] + p[1] * q[1] + p[2] * q[2]).coerceIn(-1f, 1f)
    val om = kotlin.math.acos(dot)
    val v = if (om < 1e-4f) p else {
        val s1 = sin((1 - k) * om) / sin(om)
        val s2 = sin(k * om) / sin(om)
        floatArrayOf(p[0] * s1 + q[0] * s2, p[1] * s1 + q[1] * s2, p[2] * s1 + q[2] * s2)
    }
    val lat = kotlin.math.asin(v[2].coerceIn(-1f, 1f)) * 180f / PI.toFloat()
    val lon = kotlin.math.atan2(v[1], v[0]) * 180f / PI.toFloat()
    return lat to lon
}

/** Точка на сфере → экран. z > 0 — передняя сторона. Наклон оси — чтобы видно было северное полушарие. */
private fun project(lat: Float, lon: Float, rot: Float, r: Float, c: Offset, alt: Float = 1f, tilt: Float = 0.22f): Triple<Float, Float, Float> {
    val la = lat * PI.toFloat() / 180f
    val lo = (lon + rot) * PI.toFloat() / 180f
    val x = cos(la) * sin(lo)
    val y = sin(la)
    val z = cos(la) * cos(lo)
    val y2 = y * cos(tilt) - z * sin(tilt)
    val z2 = y * sin(tilt) + z * cos(tilt)
    return Triple(c.x + x * r * alt, c.y - y2 * r * alt, z2)
}

/** Доля радиуса сферы от стороны картинки globe_gpt (сфера r=440 на 1254). */
internal const val GLOBE_SPHERE = 0.351f

/**
 * Глобус с картинки ChatGPT (ночная Земля, золотые огни, орбиты): медленно «дышит», вокруг мерцают
 * огоньки. При выключенном VPN — тусклее. Низ растворяется в фоне, чтобы не мешать тексту.
 */
@Composable
internal fun Globe(modifier: Modifier, on: Boolean, fadeBottom: Boolean = true) {
    val t = rememberInfiniteTransition(label = "globe")
    val breathe by t.animateFloat(0f, 1f, infiniteRepeatable(tween(3_000, easing = LinearEasing), RepeatMode.Reverse), label = "breathe")
    val tw by t.animateFloat(0f, 1f, infiniteRepeatable(tween(3_000, easing = LinearEasing)), label = "twinkle")
    val power by animateFloatAsState(if (on) 1f else 0f, tween(700), label = "power")
    val photo = ImageBitmap.imageResource(R.drawable.globe_gpt)
    val dim = 0.60f + 0.12f * power + 0.12f * breathe * (0.5f + 0.5f * power)
    Canvas(
        modifier.graphicsLayer(compositingStrategy = androidx.compose.ui.graphics.CompositingStrategy.Offscreen)
    ) {
        drawImage(
            photo, dstSize = IntSize(size.width.toInt(), size.height.toInt()),
            colorFilter = androidx.compose.ui.graphics.ColorFilter.colorMatrix(
                androidx.compose.ui.graphics.ColorMatrix().apply { setToScale(dim, dim, dim, 1f) }
            )
        )
        // мерцающие огоньки вокруг
        for ((i, p) in TWINKLES.withIndex()) {
            val k = ((tw + i * 0.17f) % 1f)
            val a = (0.5f - kotlin.math.abs(k - 0.5f)) * 2f
            val c = Offset(p.first * size.width, p.second * size.height)
            drawCircle(Color(0xFF6FA8FF).copy(alpha = 0.35f * a * (0.5f + 0.5f * power)), size.minDimension * 0.012f, c)
            drawCircle(Color.White.copy(alpha = (0.4f + 0.6f * a) * (0.5f + 0.5f * power)), size.minDimension * 0.005f, c)
        }
        if (fadeBottom) {
            // низ растворяется: 50% → прозрачно к 80%
            drawRect(
                Brush.verticalGradient(
                    0f to Color.Black, 0.50f to Color.Black, 0.64f to Color.Black.copy(alpha = 0.35f), 0.80f to Color.Transparent
                ),
                blendMode = androidx.compose.ui.graphics.BlendMode.DstIn
            )
        }
    }
}

private val TWINKLES = listOf(0.74f to 0.07f, 0.09f to 0.41f, 0.91f to 0.55f, 0.47f to 0.91f, 0.15f to 0.60f, 0.79f to 0.74f)

// ---------------------------------------------------------------- тонкие значки

internal enum class Ico {
    BOLT, DOWN, UP, GEAR, CHEVRON, CHECK, SEARCH, GLOBE, CLOSE, BACK, CLOCK,
    ROCKET, GAMEPAD, CROWN, SHIELD, LOCK, APPS, POWER, BELL, REFRESH, SWAP, CLIP, SEND, HAT, BATTERY, INFO,
}

/** Эмодзи из старого кода → свой значок (если есть). */
internal fun icoFor(emoji: String): Ico? = when (emoji) {
    "🚀" -> Ico.ROCKET
    "🎮" -> Ico.GAMEPAD
    "👑" -> Ico.CROWN
    "🛡" -> Ico.SHIELD
    "🔒" -> Ico.LOCK
    "📱" -> Ico.APPS
    "🌐" -> Ico.GLOBE
    "🔔" -> Ico.BELL
    "⬆️" -> Ico.REFRESH
    "↩" -> Ico.SWAP
    "⚡" -> Ico.BOLT
    "⏻" -> Ico.POWER
    "🥷" -> Ico.HAT
    "🔋" -> Ico.BATTERY
    else -> null
}

/** Значок по эмодзи: свой, если нарисован, иначе само эмодзи. */
@Composable
internal fun EmojiIcon(emoji: String, size: Dp, color: Color = Blue) {
    val ico = icoFor(emoji)
    if (ico != null) LineIcon(ico, size, color)
    else androidx.compose.material3.Text(emoji, fontSize = (size.value * 0.8f).sp)
}

/** Простые линейные значки (нарисованы кодом, в одном стиле с картинками-образцами). */
@Composable
internal fun LineIcon(ico: Ico, size: Dp, color: Color = Blue) {
    Canvas(Modifier.size(size)) { drawIco(ico, color) }
}

private fun DrawScope.drawIco(ico: Ico, color: Color) {
    val s = size.minDimension
    val w = s * 0.09f
    val st = Stroke(width = w, cap = StrokeCap.Round, join = StrokeJoin.Round)
    fun p(x: Float, y: Float) = Offset(x * s, y * s)
    fun line(pts: List<Offset>) {
        val path = Path()
        pts.forEachIndexed { i, o -> if (i == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y) }
        drawPath(path, color, style = st)
    }
    when (ico) {
        Ico.BOLT -> drawPath(Path().apply {
            moveTo(0.58f * s, 0.06f * s); lineTo(0.22f * s, 0.56f * s); lineTo(0.48f * s, 0.56f * s)
            lineTo(0.40f * s, 0.94f * s); lineTo(0.78f * s, 0.42f * s); lineTo(0.52f * s, 0.42f * s); close()
        }, Brush.verticalGradient(listOf(Color(0xFFB5D3FF), color)))
        Ico.DOWN -> { line(listOf(p(0.5f, 0.12f), p(0.5f, 0.66f))); line(listOf(p(0.27f, 0.45f), p(0.5f, 0.68f), p(0.73f, 0.45f))); line(listOf(p(0.2f, 0.88f), p(0.8f, 0.88f))) }
        Ico.UP -> { line(listOf(p(0.5f, 0.88f), p(0.5f, 0.24f))); line(listOf(p(0.27f, 0.45f), p(0.5f, 0.22f), p(0.73f, 0.45f))); line(listOf(p(0.2f, 0.1f), p(0.8f, 0.1f))) }
        Ico.CHEVRON -> line(listOf(p(0.38f, 0.2f), p(0.66f, 0.5f), p(0.38f, 0.8f)))
        Ico.BACK -> line(listOf(p(0.62f, 0.2f), p(0.34f, 0.5f), p(0.62f, 0.8f)))
        Ico.CHECK -> line(listOf(p(0.22f, 0.52f), p(0.43f, 0.72f), p(0.8f, 0.3f)))
        Ico.CLOSE -> { line(listOf(p(0.25f, 0.25f), p(0.75f, 0.75f))); line(listOf(p(0.75f, 0.25f), p(0.25f, 0.75f))) }
        Ico.SEARCH -> {
            drawCircle(color, s * 0.27f, p(0.43f, 0.43f), style = st)
            line(listOf(p(0.63f, 0.63f), p(0.86f, 0.86f)))
        }
        Ico.GLOBE -> {
            drawCircle(color, s * 0.4f, center, style = st)
            drawOval(color, Offset(s * 0.32f, s * 0.1f), Size(s * 0.36f, s * 0.8f), style = st)
            line(listOf(p(0.12f, 0.5f), p(0.88f, 0.5f)))
        }
        Ico.CLOCK -> {
            drawCircle(color, s * 0.38f, center, style = st)
            line(listOf(p(0.5f, 0.28f), p(0.5f, 0.5f), p(0.66f, 0.6f)))
        }
        Ico.ROCKET -> withTransform({ rotate(45f, center) }) {
            val fill = Brush.verticalGradient(listOf(Color(0xFFE8F4FF), color), 0f, s)
            drawPath(Path().apply {
                moveTo(0.5f * s, 0.04f * s)
                cubicTo(0.70f * s, 0.20f * s, 0.69f * s, 0.50f * s, 0.62f * s, 0.70f * s)
                lineTo(0.38f * s, 0.70f * s)
                cubicTo(0.31f * s, 0.50f * s, 0.30f * s, 0.20f * s, 0.5f * s, 0.04f * s); close()
            }, fill)
            drawPath(Path().apply {
                moveTo(0.37f * s, 0.46f * s); lineTo(0.20f * s, 0.66f * s); lineTo(0.22f * s, 0.80f * s); lineTo(0.39f * s, 0.68f * s); close()
                moveTo(0.63f * s, 0.46f * s); lineTo(0.80f * s, 0.66f * s); lineTo(0.78f * s, 0.80f * s); lineTo(0.61f * s, 0.68f * s); close()
            }, color)
            drawCircle(Color(0xFF0B1630), 0.075f * s, p(0.5f, 0.34f))
            drawPath(Path().apply {
                moveTo(0.41f * s, 0.74f * s); lineTo(0.5f * s, 0.97f * s); lineTo(0.59f * s, 0.74f * s); close()
            }, Brush.verticalGradient(listOf(Color(0xFFCFE0FF), Color(0x002F6BFF)), 0.74f * s, 0.97f * s))
        }
        Ico.GAMEPAD -> {
            val fill = Brush.verticalGradient(listOf(Color(0xFFE8F4FF), color), 0.25f * s, 0.85f * s)
            drawRoundRect(fill, Offset(0.06f * s, 0.28f * s), Size(0.88f * s, 0.40f * s), androidx.compose.ui.geometry.CornerRadius(0.2f * s))
            drawCircle(fill, 0.16f * s, p(0.25f, 0.66f))
            drawCircle(fill, 0.16f * s, p(0.75f, 0.66f))
            val dark = Color(0xFF0B1630)
            drawRect(dark, Offset(0.21f * s, 0.43f * s), Size(0.16f * s, 0.05f * s))
            drawRect(dark, Offset(0.265f * s, 0.375f * s), Size(0.05f * s, 0.16f * s))
            drawCircle(dark, 0.04f * s, p(0.68f, 0.42f))
            drawCircle(dark, 0.04f * s, p(0.76f, 0.50f))
        }
        Ico.CROWN -> {
            val gold = Brush.verticalGradient(listOf(Color(0xFFFFE9A8), Color(0xFFE2A631)), 0.2f * s, 0.88f * s)
            drawPath(Path().apply {
                moveTo(0.10f * s, 0.32f * s); lineTo(0.30f * s, 0.55f * s); lineTo(0.5f * s, 0.22f * s); lineTo(0.70f * s, 0.55f * s)
                lineTo(0.90f * s, 0.32f * s); lineTo(0.80f * s, 0.74f * s); lineTo(0.20f * s, 0.74f * s); close()
            }, gold)
            drawRoundRect(gold, Offset(0.20f * s, 0.78f * s), Size(0.60f * s, 0.09f * s), androidx.compose.ui.geometry.CornerRadius(0.03f * s))
            for ((x, y) in listOf(0.10f to 0.30f, 0.5f to 0.19f, 0.90f to 0.30f)) drawCircle(Color(0xFFFFE9A8), 0.055f * s, p(x, y))
        }
        Ico.SHIELD -> {
            val shield = Path().apply {
                moveTo(0.5f * s, 0.06f * s); lineTo(0.86f * s, 0.19f * s)
                cubicTo(0.86f * s, 0.56f * s, 0.72f * s, 0.80f * s, 0.5f * s, 0.95f * s)
                cubicTo(0.28f * s, 0.80f * s, 0.14f * s, 0.56f * s, 0.14f * s, 0.19f * s); close()
            }
            drawPath(shield, Brush.verticalGradient(listOf(color.copy(alpha = 0.30f), color.copy(alpha = 0.08f)), 0f, s))
            drawPath(shield, color, style = st)
            drawRoundRect(color, Offset(0.38f * s, 0.47f * s), Size(0.24f * s, 0.20f * s), androidx.compose.ui.geometry.CornerRadius(0.04f * s))
            drawArc(color, 180f, 180f, false, Offset(0.42f * s, 0.34f * s), Size(0.16f * s, 0.2f * s), style = Stroke(w * 0.8f))
        }
        Ico.LOCK -> {
            drawArc(color, 180f, 180f, false, Offset(0.30f * s, 0.12f * s), Size(0.40f * s, 0.42f * s), style = Stroke(w * 1.3f))
            drawLine(color, p(0.30f, 0.33f), p(0.30f, 0.47f), w * 1.3f)
            drawLine(color, p(0.70f, 0.33f), p(0.70f, 0.47f), w * 1.3f)
            drawRoundRect(Brush.verticalGradient(listOf(Color(0xFFE8F4FF), color), 0.42f * s, 0.92f * s),
                Offset(0.18f * s, 0.44f * s), Size(0.64f * s, 0.48f * s), androidx.compose.ui.geometry.CornerRadius(0.09f * s))
            drawCircle(Color(0xFF0B1630), 0.065f * s, p(0.5f, 0.64f))
            drawRect(Color(0xFF0B1630), Offset(0.475f * s, 0.64f * s), Size(0.05f * s, 0.13f * s))
        }
        Ico.APPS -> for ((x, y) in listOf(0.14f to 0.14f, 0.56f to 0.14f, 0.14f to 0.56f, 0.56f to 0.56f)) {
            drawRoundRect(color, Offset(x * s, y * s), Size(0.30f * s, 0.30f * s), androidx.compose.ui.geometry.CornerRadius(0.07f * s), style = st)
        }
        Ico.POWER -> {
            drawArc(color, -55f, 290f, false, Offset(0.17f * s, 0.19f * s), Size(0.66f * s, 0.66f * s), style = st)
            line(listOf(p(0.5f, 0.10f), p(0.5f, 0.46f)))
        }
        Ico.BELL -> {
            drawPath(Path().apply {
                moveTo(0.5f * s, 0.10f * s)
                cubicTo(0.73f * s, 0.10f * s, 0.78f * s, 0.30f * s, 0.78f * s, 0.50f * s)
                lineTo(0.87f * s, 0.72f * s); lineTo(0.13f * s, 0.72f * s); lineTo(0.22f * s, 0.50f * s)
                cubicTo(0.22f * s, 0.30f * s, 0.27f * s, 0.10f * s, 0.5f * s, 0.10f * s); close()
            }, Brush.verticalGradient(listOf(Color(0xFFE8F4FF), color), 0.1f * s, 0.75f * s))
            drawCircle(color, 0.08f * s, p(0.5f, 0.83f))
        }
        Ico.REFRESH -> {
            drawArc(color, 200f, 130f, false, Offset(0.16f * s, 0.16f * s), Size(0.68f * s, 0.68f * s), style = st)
            drawArc(color, 20f, 130f, false, Offset(0.16f * s, 0.16f * s), Size(0.68f * s, 0.68f * s), style = st)
            line(listOf(p(0.66f, 0.10f), p(0.79f, 0.24f), p(0.62f, 0.30f)))
            line(listOf(p(0.34f, 0.90f), p(0.21f, 0.76f), p(0.38f, 0.70f)))
        }
        Ico.SWAP -> {
            line(listOf(p(0.18f, 0.34f), p(0.82f, 0.34f))); line(listOf(p(0.66f, 0.18f), p(0.82f, 0.34f), p(0.66f, 0.50f)))
            line(listOf(p(0.82f, 0.68f), p(0.18f, 0.68f))); line(listOf(p(0.34f, 0.52f), p(0.18f, 0.68f), p(0.34f, 0.84f)))
        }
        Ico.CLIP -> drawPath(Path().apply {
            moveTo(0.70f * s, 0.30f * s); lineTo(0.38f * s, 0.62f * s)
            cubicTo(0.30f * s, 0.70f * s, 0.40f * s, 0.80f * s, 0.48f * s, 0.72f * s)
            lineTo(0.80f * s, 0.40f * s)
            cubicTo(0.94f * s, 0.26f * s, 0.74f * s, 0.06f * s, 0.60f * s, 0.20f * s)
            lineTo(0.24f * s, 0.56f * s)
            cubicTo(0.04f * s, 0.76f * s, 0.30f * s, 1.0f * s, 0.50f * s, 0.80f * s)
            lineTo(0.76f * s, 0.54f * s)
        }, color, style = st)
        Ico.SEND -> {
            drawPath(Path().apply {
                moveTo(0.08f * s, 0.46f * s); lineTo(0.92f * s, 0.10f * s); lineTo(0.62f * s, 0.92f * s); lineTo(0.47f * s, 0.57f * s); close()
            }, Brush.verticalGradient(listOf(Color.White, color), 0.1f * s, 0.9f * s))
            drawLine(Color(0x660B1630), p(0.47f, 0.57f), p(0.92f, 0.10f), w * 0.6f)
        }
        Ico.HAT -> {
            val fill = Brush.verticalGradient(listOf(Color(0xFFE8F4FF), color), 0.1f * s, 0.8f * s)
            drawPath(Path().apply {
                moveTo(0.30f * s, 0.42f * s); lineTo(0.36f * s, 0.14f * s); lineTo(0.64f * s, 0.14f * s); lineTo(0.70f * s, 0.42f * s); close()
            }, fill)
            drawOval(fill, Offset(0.08f * s, 0.36f * s), Size(0.84f * s, 0.14f * s))
            drawCircle(fill, 0.13f * s, p(0.34f, 0.68f))
            drawCircle(fill, 0.13f * s, p(0.66f, 0.68f))
            drawLine(color, p(0.45f, 0.66f), p(0.55f, 0.66f), w)
        }
        Ico.BATTERY -> {
            drawRoundRect(color, Offset(0.26f * s, 0.16f * s), Size(0.48f * s, 0.76f * s), androidx.compose.ui.geometry.CornerRadius(0.08f * s), style = st)
            drawRoundRect(color, Offset(0.40f * s, 0.06f * s), Size(0.20f * s, 0.08f * s), androidx.compose.ui.geometry.CornerRadius(0.03f * s))
            for (i in 0..2) drawRoundRect(Brush.verticalGradient(listOf(Color(0xFFCFE0FF), color)),
                Offset(0.34f * s, (0.66f - i * 0.19f) * s), Size(0.32f * s, 0.14f * s), androidx.compose.ui.geometry.CornerRadius(0.03f * s))
        }
        Ico.INFO -> {
            drawCircle(color, s * 0.40f, center, style = st)
            drawCircle(color, s * 0.05f, p(0.5f, 0.31f))
            line(listOf(p(0.5f, 0.45f), p(0.5f, 0.72f)))
        }
        Ico.GEAR -> {
            val r1 = s * 0.27f
            for (i in 0 until 8) {
                val a = i * PI.toFloat() / 4f
                drawLine(color, Offset(center.x + cos(a) * r1, center.y + sin(a) * r1),
                    Offset(center.x + cos(a) * s * 0.42f, center.y + sin(a) * s * 0.42f), w * 1.6f, StrokeCap.Round)
            }
            drawCircle(color, r1, center, style = st)
            drawCircle(color, s * 0.1f, center, style = st)
        }
    }
}
