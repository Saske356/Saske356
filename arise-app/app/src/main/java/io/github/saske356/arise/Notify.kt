package io.github.saske356.arise

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver

/**
 * Разрешение на уведомления. Системный запрос Android показывает не больше двух раз, а на Xiaomi
 * у приложений не из магазина уведомления часто выключены сразу, — поэтому своя плашка с кнопкой:
 * сначала системный запрос, а если Android его уже не показывает — настройки уведомлений приложения.
 */
object Notify {
    private const val PREFS = "arise_notify"

    fun enabled(ctx: Context): Boolean {
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return false
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return true
        if (!nm.areNotificationsEnabled()) return false
        if (Build.VERSION.SDK_INT >= 26) {
            val ch = nm.getNotificationChannel(AriseVpnService.CHAT_CHANNEL)
            if (ch != null && ch.importance == NotificationManager.IMPORTANCE_NONE) return false
        }
        return true
    }

    fun openSettings(ctx: Context) {
        val i = if (Build.VERSION.SDK_INT >= 26) Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, ctx.packageName)
        else Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:" + ctx.packageName))
        try {
            ctx.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            ctx.startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:" + ctx.packageName))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }

    /** «Не сейчас» прячет плашку на 3 дня. */
    fun snoozed(ctx: Context): Boolean =
        System.currentTimeMillis() < ctx.getSharedPreferences(PREFS, 0).getLong("snooze", 0L)

    fun snooze(ctx: Context) =
        ctx.getSharedPreferences(PREFS, 0).edit().putLong("snooze", System.currentTimeMillis() + 3 * 86_400_000L).apply()
}

/** Состояние «уведомления разрешены», обновляется, когда возвращаемся в приложение из настроек. */
@Composable
internal fun rememberNotifyEnabled(): Boolean {
    val ctx = LocalContext.current
    var on by remember { mutableStateOf(Notify.enabled(ctx)) }
    val owner = LocalLifecycleOwner.current
    DisposableEffect(owner) {
        val obs = LifecycleEventObserver { _, e -> if (e == Lifecycle.Event.ON_RESUME) on = Notify.enabled(ctx) }
        owner.lifecycle.addObserver(obs)
        onDispose { owner.lifecycle.removeObserver(obs) }
    }
    return on
}

/** Кнопка «Включить»: системный запрос, а если его уже не показывают — настройки. */
@Composable
internal fun rememberNotifyAsk(): () -> Unit {
    val ctx = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted || !Notify.enabled(ctx)) Notify.openSettings(ctx)
    }
    return {
        val act = ctx as? Activity
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
            act != null && act.shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)
        ) launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        else Notify.openSettings(ctx)
    }
}

/** Плашка на главном экране, пока уведомления выключены. */
@Composable
internal fun NotifyCard() {
    val ctx = LocalContext.current
    val on = rememberNotifyEnabled()
    var hidden by remember { mutableStateOf(Notify.snoozed(ctx)) }
    val ask = rememberNotifyAsk()
    if (on || hidden) return
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
            Text("🔔", fontSize = 20.sp)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("Включите уведомления", color = TextMain, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text("Чтобы видеть, что VPN работает, и не пропускать обновления", color = TextDim, fontSize = 12.sp)
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "Включить", color = Ink, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                modifier = Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(Blue)
                    .clickable { ask() }.padding(vertical = 10.dp)
            )
            Text(
                "Не сейчас", color = TextMain, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center,
                modifier = Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(Glass)
                    .border(1.dp, Blue.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
                    .clickable { Notify.snooze(ctx); hidden = true }.padding(vertical = 10.dp)
            )
        }
    }
}
