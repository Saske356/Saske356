package com.v2ray.ang.ui.main

// Обновление Arise VPN изнутри (кладётся в сборку из android/kt/ скриптом customize.py).
// Та же логика, что в новом приложении (arise-app/.../AppUpdate.kt): держи их одинаковыми.

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.v2ray.ang.BuildConfig
import com.v2ray.ang.handler.MmkvManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL

/**
 * Обновление приложения изнутри. Сервер подписок по адресу «<подписка>/update?app=arise» говорит,
 * какая версия последняя, а «…/apk» отдаёт сам файл — с нашего сервера, поэтому обновление доходит,
 * даже если GitHub не открывается (запасной адрес — GitHub). Ставит системный установщик Android:
 * пользователь один раз разрешает установку из приложения и подтверждает обновление.
 */
data class AuroraUpdateUi(
    val version: String = "",   // доступная версия; пусто — обновления нет
    val size: Long = 0L,
    val progress: Float = -1f,  // -1 — не качаем, 0..1 — качаем
    val note: String = "",
    val checking: Boolean = false,
)

object AuroraUpdate {
    private const val APP = "aurora"
    private const val SOCKS_PORT = 10808  // локальный вход ядра из конфигов подписки (client_config.py)
    private const val CHECK_EVERY_MS = 6 * 3_600_000L
    val flow = MutableStateFlow(AuroraUpdateUi())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Volatile
    private var info: JSONObject? = null
    private var lastCheck = 0L

    /** Включён ли VPN: ставит панель (AuroraConnectPanel). Тогда запросы идут через туннель. */
    @Volatile
    var vpnOn = false

    private fun proxy(): Proxy? =
        if (vpnOn) Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", SOCKS_PORT)) else null

    private fun open(url: String, viaVpn: Boolean): HttpURLConnection {
        val p = if (viaVpn) proxy() else null
        val c = (if (p != null) URL(url).openConnection(p) else URL(url).openConnection()) as HttpURLConnection
        c.connectTimeout = 15_000
        c.readTimeout = 30_000
        c.setRequestProperty("User-Agent", "AuroraVPN/${BuildConfig.VERSION_NAME}")
        return c
    }

    /** Запрос через VPN (если включён), не вышло — напрямую. */
    private fun <T> either(url: String, block: (HttpURLConnection) -> T): T {
        var last: Exception? = null
        for (viaVpn in listOf(true, false)) {
            if (viaVpn && proxy() == null) continue
            val c = open(url, viaVpn)
            try {
                if (c.responseCode != 200) throw IllegalStateException("сервер ответил ${c.responseCode}")
                return block(c)
            } catch (e: Exception) {
                last = e
            } finally {
                c.disconnect()
            }
        }
        throw last ?: IllegalStateException("нет связи")
    }

    /** Проверить новую версию (не чаще раза в 6 часов, если force = false). */
    fun check(force: Boolean = false) = scope.launch {
        val sub = MmkvManager.decodeSubscriptions().map { it.subscription.url.trim() }
            .firstOrNull { it.startsWith("http") }.orEmpty().substringBefore('?').trimEnd('/')
        if (sub.isBlank() || flow.value.checking || flow.value.progress >= 0f) return@launch
        if (!force && System.currentTimeMillis() - lastCheck < CHECK_EVERY_MS) return@launch
        lastCheck = System.currentTimeMillis()
        flow.update { it.copy(checking = true, note = "") }
        try {
            val o = either("$sub/update?app=$APP") { c -> JSONObject(c.inputStream.bufferedReader().use { it.readText() }) }
            if (o.optInt("code") > BuildConfig.VERSION_CODE && o.optString("url").isNotBlank()) {
                info = o
                flow.update { it.copy(version = o.optString("version"), size = o.optLong("size")) }
            } else {
                info = null
                flow.update { it.copy(version = "", note = if (force) "У вас последняя версия ${BuildConfig.VERSION_NAME}" else "") }
            }
        } catch (e: Exception) {
            if (force) flow.update { it.copy(note = "Не удалось проверить обновление: ${e.message}") }
        } finally {
            flow.update { it.copy(checking = false) }
        }
    }

    /** Скачать и отдать установщику Android. */
    fun install(ctx: Context) = scope.launch {
        val o = info ?: return@launch
        if (flow.value.progress >= 0f) return@launch
        val app = ctx.applicationContext
        if (Build.VERSION.SDK_INT >= 26 && !app.packageManager.canRequestPackageInstalls()) {
            flow.update { it.copy(note = "Разрешите установку из Arise VPN и нажмите «Обновить» ещё раз") }
            val i = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${app.packageName}"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            app.startActivity(i)
            return@launch
        }
        flow.update { it.copy(progress = 0f, note = "") }
        val file = File(app.cacheDir, "update.apk")
        try {
            download(listOf(o.optString("url"), o.optString("mirror")).filter { it.isNotBlank() }, file, o.optLong("size"))
            flow.update { it.copy(note = "Подтвердите установку") }
            commit(app, file)
        } catch (e: Exception) {
            flow.update { it.copy(note = "Не удалось обновить: ${e.message}") }
        } finally {
            flow.update { it.copy(progress = -1f) }
        }
    }

    private fun download(urls: List<String>, file: File, size: Long) {
        var last: Exception? = null
        for (url in urls) {
            try {
                either(url) { c ->
                    val total = c.contentLengthLong.takeIf { it > 0 } ?: size
                    c.inputStream.use { input ->
                        file.outputStream().use { out ->
                            val buf = ByteArray(64 * 1024)
                            var got = 0L
                            while (true) {
                                val n = input.read(buf)
                                if (n < 0) break
                                out.write(buf, 0, n)
                                got += n
                                if (total > 0) flow.update { it.copy(progress = (got.toFloat() / total).coerceIn(0f, 1f)) }
                            }
                        }
                    }
                }
                val head = file.inputStream().use { val b = ByteArray(2); it.read(b); b }
                if (head[0] != 'P'.code.toByte() || head[1] != 'K'.code.toByte()) throw IllegalStateException("файл повреждён")
                if (size > 0 && file.length() != size) throw IllegalStateException("файл скачался не целиком")
                return
            } catch (e: Exception) {
                last = e
            }
        }
        throw last ?: IllegalStateException("нет адреса для скачивания")
    }

    private fun commit(ctx: Context, file: File) {
        val installer = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(ctx.packageName)
        val id = installer.createSession(params)
        installer.openSession(id).use { s ->
            s.openWrite("aurora.apk", 0, file.length()).use { out ->
                file.inputStream().use { it.copyTo(out) }
                s.fsync(out)
            }
            val intent = Intent(ctx, AuroraInstallReceiver::class.java)
            // MUTABLE: установщик дописывает в намерение результат и окно подтверждения
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
            s.commit(PendingIntent.getBroadcast(ctx, id, intent, flags).intentSender)
        }
    }

    fun onStatus(note: String) = flow.update { it.copy(note = note) }
}

/** Ответ установщика Android: показать окно подтверждения или сообщить, что пошло не так. */
class AuroraInstallReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm: Intent? = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(Intent.EXTRA_INTENT)
                }
                if (confirm != null) ctx.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            PackageInstaller.STATUS_SUCCESS -> AuroraUpdate.onStatus("Обновлено")
            PackageInstaller.STATUS_FAILURE_ABORTED -> AuroraUpdate.onStatus("Обновление отменено")
            else -> AuroraUpdate.onStatus("Не удалось установить: " +
                (intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "ошибка установщика"))
        }
    }
}
