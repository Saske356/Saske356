package io.github.saske356.arise

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.provider.Settings
import java.security.MessageDigest

class AriseApp : Application() {
    companion object {
        const val CRASH_PREFS = "crash"
    }

    override fun onCreate() {
        super.onCreate()
        // Падение приложения: запоминаем причину, при следующем запуске она показывается (её можно скопировать)
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try {
                val text = android.util.Log.getStackTraceString(e).take(4000)
                getSharedPreferences(CRASH_PREFS, MODE_PRIVATE).edit()
                    .putString("text", "${BuildConfig.VERSION_NAME}\n$text").commit()
            } catch (_: Throwable) {
            }
            prev?.uncaughtException(t, e)
        }
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
            // Новые письма в чате: без текста и имени (см. ChatVault.notifyMode)
            val chat = NotificationChannel(AriseVpnService.CHAT_CHANNEL, "Обновления", NotificationManager.IMPORTANCE_DEFAULT)
            getSystemService(NotificationManager::class.java).createNotificationChannel(chat)
        }
    }
}
