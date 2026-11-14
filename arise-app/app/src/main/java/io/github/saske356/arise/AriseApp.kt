package io.github.saske356.arise

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.provider.Settings
import java.security.MessageDigest

class AriseApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Store.init(this)
        ChatVault.init(this)
        // Номер устройства для лимита устройств: ANDROID_ID не меняется при переустановке приложения.
        // Серверу уходит только его отпечаток.
        val id = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID).orEmpty()
        if (id.isNotEmpty()) {
            Subscription.hwid = MessageDigest.getInstance("SHA-256").digest(("arise:" + id).toByteArray())
                .joinToString("") { "%02x".format(it) }.take(32)
        }
        if (Build.VERSION.SDK_INT >= 26) {
            val channel = NotificationChannel(AriseVpnService.CHANNEL, "VPN", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }
}
