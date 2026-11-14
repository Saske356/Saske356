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
    fun runConfig(server: String, mode: Mode = Mode.BALANCE, dns: Dns = Dns.CLOUDFLARE): String {
        val o = JSONObject(server)
        mode.apply(o)
        dnsInCore(o, dns)
        directIPv4(o)
        // Счётчики трафика: из них график скорости и «за сеанс»
        o.put("stats", JSONObject())
        val policy = o.optJSONObject("policy") ?: JSONObject().also { o.put("policy", it) }
        val system = policy.optJSONObject("system") ?: JSONObject().also { policy.put("system", it) }
        system.put("statsOutboundUplink", true).put("statsOutboundDownlink", true)
        // routeOnly = false: дальше идёт имя сайта, а не адрес, который выбрал браузер. Браузеры
        // (Яндекс, Chrome) сами узнают адреса по защищённому DNS и берут IPv6; российские сайты идут
        // напрямую, и в сети без IPv6 соединение рвалось (ERR_CONNECTION_CLOSED). С именем сайта
        // прямое подключение само выбирает IPv4 (direct с UseIPv4 ниже), а сервер VPN — свой адрес.
        val sniffing = JSONObject()
            .put("enabled", true)
            .put("destOverride", JSONArray(listOf("http", "tls", "quic")))
            .put("routeOnly", false)
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

    /**
     * DNS телефона — в ядро: на запросы адресов отвечает DNS ядра и только адресами IPv4.
     * Иначе телефон получал IPv6-адреса, и российские сайты (они идут напрямую, мимо VPN) не
     * открывались в сетях без IPv6: Яндекс висел, а Google через VPN работал. Российские имена
     * спрашиваем у Яндекса (обычный DNS напрямую), остальные — у DNS, выбранного в инструментах.
     */
    /** Прямые подключения (российские сайты) — только по IPv4: в сетях без IPv6 иначе обрыв. */
    private fun directIPv4(o: JSONObject) {
        val outs = o.optJSONArray("outbounds") ?: return
        for (i in 0 until outs.length()) {
            val ob = outs.optJSONObject(i) ?: continue
            if (ob.optString("protocol") != "freedom") continue
            val st = ob.optJSONObject("settings") ?: JSONObject().also { ob.put("settings", it) }
            st.put("domainStrategy", "UseIPv4")
        }
    }

    private fun dnsInCore(o: JSONObject, choice: Dns) {
        val old = o.optJSONObject("dns") ?: JSONObject()
        val servers = JSONArray()
        val oldServers = old.optJSONArray("servers") ?: JSONArray()
        for (i in 0 until oldServers.length()) {
            val s = oldServers.optJSONObject(i) ?: continue
            if (!s.has("domains")) continue
            servers.put(JSONObject(s.toString()).put("address", "77.88.8.8"))
        }
        servers.put(choice.ip).put(choice.ip2)
        o.put("dns", JSONObject().put("servers", servers).put("queryStrategy", "UseIPv4"))
        val outs = o.optJSONArray("outbounds") ?: JSONArray().also { o.put("outbounds", it) }
        outs.put(JSONObject().put("tag", "dns-out").put("protocol", "dns"))
        val routing = o.optJSONObject("routing") ?: JSONObject().also { o.put("routing", it) }
        val rules = routing.optJSONArray("rules") ?: JSONArray()
        val merged = JSONArray().put(
            JSONObject().put("type", "field").put("inboundTag", JSONArray(listOf("tun")))
                .put("port", "53").put("outboundTag", "dns-out")
        )
        for (i in 0 until rules.length()) merged.put(rules.get(i))
        routing.put("rules", merged)
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
