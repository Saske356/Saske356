package io.github.saske356.arise

import android.content.Context
import android.util.Log
import go.Seq
import libv2ray.Libv2ray
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Ядро Xray (библиотека AndroidLibXrayLite): подготовка конфигов и замер задержки. */
object Core {
    const val PING_URL = "https://www.gstatic.com/generate_204"
    /** Локальный вход ядра: через него приложение само обновляет подписку по VPN, когда
     *  у оператора закрыт прямой доступ к серверу. */
    const val SOCKS_PORT = 10899
    private const val TAG = "Arise"

    @Volatile
    private var ready = false

    /** Файлы geoip/geosite (правила «российское — напрямую», «реклама — блок») и запуск среды ядра. */
    @Synchronized
    fun init(ctx: Context) {
        if (ready) return
        val dir = ctx.filesDir
        val version = BuildConfig.VERSION_CODE.toString()
        val mark = File(dir, "geo.version")
        val fresh = mark.exists() && mark.readText() == version
        for (name in listOf("geoip.dat", "geosite.dat")) {
            val f = File(dir, name)
            if (fresh && f.length() > 0) continue
            try {
                ctx.assets.open(name).use { input -> f.outputStream().use { input.copyTo(it) } }
            } catch (e: Exception) {
                Log.w(TAG, "нет $name в приложении", e)
            }
        }
        mark.writeText(version)
        Seq.setContext(ctx.applicationContext)
        Libv2ray.initCoreEnv(dir.absolutePath, "")
        ready = true
    }

    /** Конфиг для работы VPN: вход tun (трафик телефона) и локальный SOCKS для обновления подписки. */
    fun runConfig(server: String): String {
        val o = JSONObject(server)
        val sniffing = JSONObject()
            .put("enabled", true)
            .put("destOverride", JSONArray(listOf("http", "tls", "quic")))
            .put("routeOnly", true)
        val inbounds = JSONArray()
        inbounds.put(
            JSONObject().put("tag", "tun").put("protocol", "tun")
                .put("settings", JSONObject().put("name", "xray0").put("MTU", 1500).put("userLevel", 8))
                .put("sniffing", sniffing)
        )
        inbounds.put(
            JSONObject().put("tag", "socks-local").put("listen", "127.0.0.1").put("port", SOCKS_PORT)
                .put("protocol", "socks")
                .put("settings", JSONObject().put("auth", "noauth").put("udp", false))
        )
        o.put("inbounds", inbounds)
        // Запросы приложения через локальный SOCKS всегда идут в туннель — даже к самому серверу,
        // который обычные правила пускают напрямую (иначе подписку не обновить, если оператор режет TCP).
        val routing = o.optJSONObject("routing") ?: JSONObject().also { o.put("routing", it) }
        val rules = routing.optJSONArray("rules") ?: JSONArray()
        val own = JSONObject().put("type", "field").put("inboundTag", JSONArray(listOf("socks-local")))
        if ((routing.optJSONArray("balancers")?.length() ?: 0) > 0) own.put("balancerTag", "best")
        else own.put("outboundTag", "proxy")
        val merged = JSONArray().put(own)
        for (i in 0 until rules.length()) merged.put(rules.get(i))
        routing.put("rules", merged)
        return o.toString()
    }

    /** Замер задержки страны без включённого VPN: ядро поднимается на секунду только для замера. */
    fun measure(server: String): Long = try {
        val o = JSONObject(server)
        o.put("inbounds", JSONArray())
        Libv2ray.measureOutboundDelay(o.toString(), PING_URL)
    } catch (e: Exception) {
        -1L
    }
}
