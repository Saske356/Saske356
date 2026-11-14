package io.github.saske356.arise

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build

class AriseApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Store.init(this)
        if (Build.VERSION.SDK_INT >= 26) {
            val channel = NotificationChannel(AriseVpnService.CHANNEL, "VPN", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }
}
