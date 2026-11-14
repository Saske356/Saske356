package io.github.saske356.arise

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/** Автоподключение при включении телефона (если включено в инструментах и VPN уже разрешён). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (Store.autoConnect && Store.current() != null && VpnService.prepare(ctx) == null) {
            AriseVpnService.start(ctx)
        }
    }
}

/** Кнопка в шторке: включить или выключить VPN, не открывая приложение. */
class AriseTile : TileService() {
    override fun onStartListening() {
        super.onStartListening()
        refresh()
    }

    override fun onClick() {
        super.onClick()
        when {
            VpnState.flow.value.status != Status.STOPPED -> AriseVpnService.stop(this)
            Store.current() != null && VpnService.prepare(this) == null -> AriseVpnService.start(this)
            else -> openApp()  // нет подписки или разрешения на VPN — нужно приложение
        }
        refresh(Status.CONNECTING)
    }

    private fun refresh(hint: Status? = null) {
        val tile = qsTile ?: return
        val st = hint ?: VpnState.flow.value.status
        tile.state = if (st == Status.STOPPED) Tile.STATE_INACTIVE else Tile.STATE_ACTIVE
        tile.label = "Arise VPN"
        tile.updateTile()
    }

    @Suppress("DEPRECATION")
    private fun openApp() {
        val i = Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_IMMUTABLE))
        } else {
            startActivityAndCollapse(i)
        }
    }
}
