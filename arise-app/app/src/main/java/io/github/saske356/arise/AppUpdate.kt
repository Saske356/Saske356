package io.github.saske356.arise

import android.content.Context
import android.content.Intent
import android.net.Uri
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL

/**
 * Обновление приложения изнутри. Сервер подписок по адресу «<подписка>/update?app=arise» говорит,
 * какая версия последняя, а «…/apk» отдаёт сам файл — с нашего сервера, поэтому обновление доходит,
 * даже если GitHub не открывается (запасной адрес — GitHub). Сам файл приложение не ставит:
 * приложение открывает ссылку в браузере, дальше обычная установка файла.
 */
data class UpdateUi(
    val version: String = "",   // доступная версия; пусто — обновления нет
    val size: Long = 0L,
    val progress: Float = -1f,  // -1 — не качаем, 0..1 — качаем
    val note: String = "",
    val checking: Boolean = false,
)

object AppUpdate {
    private const val APP = "arise"
    private const val CHECK_EVERY_MS = 6 * 3_600_000L
    val flow = MutableStateFlow(UpdateUi())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Volatile
    private var info: JSONObject? = null
    private var lastCheck = 0L

    private fun proxy(): Proxy? =
        if (VpnState.flow.value.status == Status.RUNNING) Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", Core.SOCKS_PORT))
        else null

    private fun open(url: String, viaVpn: Boolean): HttpURLConnection {
        val p = if (viaVpn) proxy() else null
        val c = (if (p != null) URL(url).openConnection(p) else URL(url).openConnection()) as HttpURLConnection
        c.connectTimeout = 15_000
        c.readTimeout = 30_000
        c.setRequestProperty("User-Agent", "AriseApp/${BuildConfig.VERSION_NAME}")
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
        val sub = Store.subUrl.trim().substringBefore('?').trimEnd('/')
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

    /**
     * Открыть новую версию в браузере: он скачает файл, а Android предложит установить.
     * Само приложение APK не ставит: Play Защита считала такое приложение «загрузчиком»
     * и помечала как вредоносное.
     */
    fun install(ctx: Context) {
        val o = info ?: return
        val url = o.optString("url").ifBlank { o.optString("mirror") }
        if (url.isBlank()) return
        try {
            ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            flow.update { it.copy(note = "Скачайте файл в браузере и откройте его, чтобы обновить") }
        } catch (e: Exception) {
            flow.update { it.copy(note = "Не удалось открыть браузер: ${e.message}") }
        }
    }

    fun onStatus(note: String) = flow.update { it.copy(note = note) }
}
