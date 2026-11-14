package io.github.saske356.arise

import org.json.JSONArray
import org.json.JSONObject

/** Режимы соединения. Каждый по-настоящему меняет конфиг ядра — и честно пишет, чем жертвует. */
enum class Mode(
    val key: String,
    val emoji: String,
    val title: String,
    val desc: String,
    val plus: String,
    val minus: String,
) {
    BALANCE("balance", "⚡", "Баланс", "Турбо-скорость, реклама режется, российские сайты напрямую.", "", ""),
    GAME(
        "game", "🎮", "Игровой",
        "Ровный пинг без скачков: скорость ограничена, чтобы в канале не копились очереди.",
        "пинг ровнее, меньше лагов", "скачивание до 30 Мбит/с"
    ),
    TURBO("turbo", "🚀", "Турбо", "Максимум скорости для фильмов и загрузок.", "до 150 Мбит/с", "пинг может прыгать"),
    STEALTH(
        "stealth", "🥷", "Невидимка",
        "Весь трафик через VPN, даже российские сайты. Реклама и трекеры режутся.",
        "максимум приватности", "банки могут не открыться"
    ),
    ECO("eco", "🔋", "Эконом", "Реже фоновые проверки и бережный режим скорости.", "батарея и трафик", "медленнее");

    companion object {
        fun of(key: String): Mode = entries.firstOrNull { it.key == key } ?: BALANCE
    }

    /** Как часто мерить живую задержку через туннель. */
    val pingEveryMs: Long get() = if (this == ECO) 60_000L else 15_000L

    fun apply(o: JSONObject) {
        val outs = o.optJSONArray("outbounds") ?: return
        for (i in 0 until outs.length()) {
            val ob = outs.optJSONObject(i) ?: continue
            if (ob.optString("protocol") != "hysteria") continue
            val ss = ob.optJSONObject("streamSettings") ?: JSONObject().also { ob.put("streamSettings", it) }
            val fm = ss.optJSONObject("finalmask") ?: JSONObject().also { ss.put("finalmask", it) }
            val q = fm.optJSONObject("quicParams") ?: JSONObject().also { fm.put("quicParams", it) }
            when (this) {
                // Brutal держит заданную скорость: с потолком 30 Мбит/с канал не переполняется,
                // очереди у оператора не растут — пинг в играх перестаёт скакать.
                GAME -> q.put("congestion", "brutal").put("brutalDown", "30 mbps").put("brutalUp", "10 mbps")
                    .put("keepAlivePeriod", 5)
                TURBO -> q.put("congestion", "brutal").put("brutalDown", "150 mbps").put("brutalUp", "30 mbps")
                // Без Brutal ядро само подстраивается под канал (как обычный BBR): спокойнее и экономнее
                ECO -> {
                    q.remove("congestion")
                    q.remove("brutalDown")
                    q.remove("brutalUp")
                    q.put("keepAlivePeriod", 25)
                }
                else -> {}
            }
        }
        if (this == STEALTH) allThroughVpn(o)
    }

    /** «Невидимка»: убрать правила «российское — напрямую», оставив локальную сеть и сам сервер. */
    private fun allThroughVpn(o: JSONObject) {
        val routing = o.optJSONObject("routing") ?: return
        val rules = routing.optJSONArray("rules") ?: return
        val kept = JSONArray()
        for (i in 0 until rules.length()) {
            val r = rules.optJSONObject(i) ?: continue
            if (r.optString("outboundTag") != "direct") {
                kept.put(r)
                continue
            }
            if (r.has("domain")) continue  // российские сайты по имени
            val ips = r.optJSONArray("ip")
            if (ips == null) {
                kept.put(r)
                continue
            }
            val left = JSONArray()
            for (j in 0 until ips.length()) {
                val ip = ips.optString(j)
                if (ip != "geoip:ru" && ip != "77.88.8.8") left.put(ip)
            }
            if (left.length() > 0) kept.put(r.put("ip", left))
        }
        routing.put("rules", kept)
        // Отдельный российский DNS для российских сайтов тоже не нужен
        val dns = o.optJSONObject("dns") ?: return
        val servers = dns.optJSONArray("servers") ?: return
        val ds = JSONArray()
        for (i in 0 until servers.length()) {
            val s = servers.get(i)
            if (s is JSONObject && s.has("domains")) continue
            ds.put(s)
        }
        dns.put("servers", ds)
    }
}

/** DNS для телефона внутри туннеля. */
enum class Dns(val key: String, val title: String, val ip: String, val note: String) {
    CLOUDFLARE("cf", "Cloudflare", "1.1.1.1", "быстрый"),
    ADGUARD("adguard", "AdGuard", "94.140.14.14", "режет рекламу во всех приложениях"),
    GOOGLE("google", "Google", "8.8.8.8", "надёжный");

    companion object {
        fun of(key: String): Dns = entries.firstOrNull { it.key == key } ?: CLOUDFLARE
    }

    fun next(): Dns = entries[(ordinal + 1) % entries.size]
}
