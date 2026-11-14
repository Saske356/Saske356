package io.github.saske356.arise

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import libv2ray.CoreCallbackHandler
import libv2ray.CoreController
import libv2ray.Libv2ray

class AriseVpnService : VpnService() {
    companion object {
        const val CHANNEL = "vpn"
        private const val ACTION_START = "io.github.saske356.arise.START"
        private const val ACTION_STOP = "io.github.saske356.arise.STOP"
        private const val NOTIFY_ID = 1
        private const val TAG = "Arise"
        private const val SWITCH_AFTER_FAILS = 2
        private const val SWITCH_COOLDOWN_MS = 120_000L

        /** Включить VPN или переключиться на выбранную страну, если уже включён. */
        fun start(ctx: Context) {
            val i = Intent(ctx, AriseVpnService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
        }

        fun stop(ctx: Context) {
            ctx.startService(Intent(ctx, AriseVpnService::class.java).setAction(ACTION_STOP))
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private var tun: ParcelFileDescriptor? = null
    private var controller: CoreController? = null
    private var pingJob: Job? = null

    private val callback = object : CoreCallbackHandler {
        override fun onEmitStatus(p0: Long, p1: String?): Long = 0L
        override fun shutdown(): Long = 0L
        override fun startup(): Long = 0L
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            scope.launch { stopAll() }
            return START_NOT_STICKY
        }
        goForeground(VpnState.flow.value.server.ifBlank { "Подключение…" })
        scope.launch { startVpn() }
        return START_STICKY
    }

    override fun onRevoke() {
        // Другой VPN включили или разрешение отозвали в настройках Android
        scope.launch { stopAll() }
    }

    override fun onDestroy() {
        pingJob?.cancel()
        try {
            controller?.stopLoop()
        } catch (e: Exception) {
            Log.w(TAG, "stopLoop", e)
        }
        controller = null
        try {
            tun?.close()
        } catch (e: Exception) {
            Log.w(TAG, "tun close", e)
        }
        tun = null
        Store.startedAt = 0L
        VpnState.update { it.copy(status = Status.STOPPED, ping = 0L) }
        scope.cancel()
        super.onDestroy()
    }

    private suspend fun startVpn() = lock.withLock {
        VpnState.update { it.copy(status = Status.CONNECTING, error = "") }
        stopCore()
        val server = Store.current()
        if (server == null) {
            VpnState.update { it.copy(status = Status.STOPPED, error = "Сначала добавьте подписку") }
            finish()
            return@withLock
        }
        try {
            Core.init(applicationContext)
            val fd = tun ?: buildTun().also { tun = it }
            val c = Libv2ray.newCoreController(callback)
            c.startLoop(Core.runConfig(server.json), fd.fd)
            if (!c.getIsRunning()) throw IllegalStateException("ядро не запустилось")
            controller = c
            if (Store.startedAt == 0L) Store.startedAt = System.currentTimeMillis()
            Repo.select(server.name)
            VpnState.update { it.copy(status = Status.RUNNING, server = server.name, ping = 0L) }
            goForeground(server.name)
            startPingLoop()
        } catch (e: Exception) {
            Log.e(TAG, "запуск VPN", e)
            VpnState.update { it.copy(status = Status.STOPPED, error = "Не удалось подключиться: ${e.message}") }
            stopCore()
            closeTun()
            finish()
        }
    }

    private suspend fun stopAll() = lock.withLock {
        stopCore()
        closeTun()
        Store.startedAt = 0L
        VpnState.update { it.copy(status = Status.STOPPED, ping = 0L) }
        finish()
    }

    private fun stopCore() {
        pingJob?.cancel()
        pingJob = null
        try {
            controller?.stopLoop()
        } catch (e: Exception) {
            Log.w(TAG, "stopLoop", e)
        }
        controller = null
    }

    private fun closeTun() {
        try {
            tun?.close()
        } catch (e: Exception) {
            Log.w(TAG, "tun close", e)
        }
        tun = null
    }

    private fun finish() {
        stopForeground(Service.STOP_FOREGROUND_REMOVE)  // minSdk 24
        stopSelf()
    }

    private fun buildTun(): ParcelFileDescriptor {
        val b = Builder()
            .setSession("Arise VPN")
            .setMtu(1500)
            .addAddress("10.10.14.1", 30)
            .addRoute("0.0.0.0", 0)
            .addDnsServer("1.1.1.1")
        try {
            // IPv6 тоже в туннель: иначе сайты по IPv6 шли бы мимо VPN
            b.addAddress("fdfe:dcba:9876::1", 126)
            b.addRoute("::", 0)
        } catch (e: Exception) {
            Log.w(TAG, "IPv6", e)
        }
        // Само приложение (и ядро внутри него) — мимо туннеля, иначе трафик ядра ушёл бы в петлю
        b.addDisallowedApplication(packageName)
        if (Store.ruApps) {
            for (pkg in RuApps.PACKAGES) {
                try {
                    b.addDisallowedApplication(pkg)
                } catch (e: PackageManager.NameNotFoundException) {
                    // приложения нет на телефоне
                }
            }
        }
        if (Build.VERSION.SDK_INT >= 29) b.setMetered(false)
        val pi = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        b.setConfigureIntent(pi)
        return b.establish() ?: throw IllegalStateException("Android не дал создать VPN")
    }

    /** Живая задержка через туннель раз в 15 с; связь пропала дважды подряд — на страну с лучшим пингом. */
    private fun startPingLoop() {
        pingJob?.cancel()
        pingJob = scope.launch {
            delay(1500)
            var fails = 0
            var lastSwitch = 0L
            while (isActive) {
                val ms = try {
                    controller?.measureDelay(Core.PING_URL) ?: -1L
                } catch (e: Exception) {
                    -1L
                }
                VpnState.update { it.copy(ping = if (ms > 0) ms else -1L) }
                fails = if (ms > 0) 0 else fails + 1
                val now = System.currentTimeMillis()
                val current = Store.current()?.name ?: ""
                if (fails >= SWITCH_AFTER_FAILS && now - lastSwitch > SWITCH_COOLDOWN_MS && !current.startsWith("🚀")) {
                    val pings = Store.pings
                    val best = Store.servers()
                        .filter { it.name != current && (pings[it.name] ?: 0L) > 0L }
                        .minByOrNull { pings[it.name] ?: Long.MAX_VALUE }
                    if (best != null) {
                        lastSwitch = now
                        Repo.select(best.name)
                        VpnState.update { it.copy(note = "Связь пропала — переключено на «${best.name}»") }
                        scope.launch { startVpn() }
                        return@launch
                    }
                }
                delay(15_000)
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun notificationBuilder(): Notification.Builder =
        if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else Notification.Builder(this)

    private fun goForeground(text: String) {
        val pi = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val n = notificationBuilder()
            .setContentTitle("Arise VPN")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(NOTIFY_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(NOTIFY_ID, n)
    }
}
