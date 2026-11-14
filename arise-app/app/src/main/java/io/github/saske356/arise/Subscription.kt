package io.github.saske356.arise

import android.util.Base64
import org.json.JSONArray
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URI
import java.net.URL
import java.security.MessageDigest
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/** Подписка с сервера Arise: готовые конфиги Xray (JSON), зашифрованные для своего приложения. */
object Subscription {
    // Тот же ключ, что в vpn-bot/client_config.py (SUB_SECRET): маскировка, а не секрет — код открыт.
    private const val SECRET = "06c56043502cab251d01ad69c59ab1ea3885c20bd2590fca"
    private const val PREFIX = "aurora1:"
    // «aurora» в строке — сервер узнаёт своё приложение и отдаёт конфиги с турбо-режимом,
    // «(enc1)» — приложение умеет расшифровывать подписку.
    private val UA = "AriseApp/${BuildConfig.VERSION_NAME} (enc1) AuroraVPN/${BuildConfig.VERSION_NAME}"

    data class Info(val configs: List<String>, val expire: Long, val title: String, val botUrl: String)

    fun fetch(url: String, socksPort: Int? = null): Info {
        // Явно просим JSON: если в /admin выключены «JSON-конфиги», сервер иначе отдал бы
        // список ссылок, а приложение умеет только JSON («Ссылка не от Arise VPN»).
        val clean = url.trim()
        val u = URL(clean + (if ('?' in clean) "&" else "?") + "format=json")
        val conn = (if (socksPort != null)
            u.openConnection(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", socksPort)))
        else u.openConnection()) as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 20_000
        conn.setRequestProperty("User-Agent", UA)
        try {
            val code = conn.responseCode
            if (code == 403) throw IOException("Подписка закончилась — продлите её в боте")
            if (code == 404) throw IOException("Ссылка подписки не найдена — возьмите новую в боте")
            if (code != 200) throw IOException("Сервер ответил $code")
            val body = conn.inputStream.bufferedReader().use { it.readText() }
            val text = decrypt(URI(clean).rawPath ?: "", body)
            val arr = try {
                JSONArray(text)
            } catch (e: Exception) {
                val start = text.take(40).replace(Regex("\\s+"), " ")
                throw IOException("Сервер ответил не подпиской Arise VPN (${conn.contentType ?: "?"}: «$start…»). " +
                    "Проверьте ссылку или напишите в бот")
            }
            val configs = List(arr.length()) { arr.getJSONObject(it).toString() }
            if (configs.isEmpty()) throw IOException("В подписке нет стран")
            val expire = Regex("expire=(\\d+)").find(conn.getHeaderField("subscription-userinfo") ?: "")
                ?.groupValues?.get(1)?.toLongOrNull() ?: 0L
            var title = conn.getHeaderField("profile-title") ?: ""
            if (title.startsWith("base64:")) {
                title = try {
                    String(Base64.decode(title.removePrefix("base64:"), Base64.DEFAULT), Charsets.UTF_8)
                } catch (e: Exception) {
                    ""
                }
            }
            return Info(configs, expire, title, conn.getHeaderField("support-url") ?: "")
        } finally {
            conn.disconnect()
        }
    }

    /** "aurora1:" + base64(nonce 12 байт + AES-256-GCM), ключ — SHA-256(секрет + путь ссылки). */
    private fun decrypt(path: String, body: String): String {
        val text = body.trim()
        if (!text.startsWith(PREFIX)) return text
        val raw = Base64.decode(text.substring(PREFIX.length), Base64.DEFAULT)
        val key = MessageDigest.getInstance("SHA-256").digest((SECRET + path).toByteArray(Charsets.UTF_8))
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, raw, 0, 12))
        return String(cipher.doFinal(raw, 12, raw.size - 12), Charsets.UTF_8)
    }
}
