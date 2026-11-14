package io.github.saske356.arise

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/** Одна страна (подключение) из подписки: название и готовый конфиг Xray. */
data class Server(val name: String, val json: String)

/** Всё, что приложение помнит между запусками. */
object Store {
    private lateinit var p: SharedPreferences

    fun init(ctx: Context) {
        p = ctx.getSharedPreferences("arise", Context.MODE_PRIVATE)
    }

    private fun str(key: String) = p.getString(key, "") ?: ""
    private fun put(key: String, value: String) = p.edit().putString(key, value).apply()

    var subUrl: String
        get() = str("sub_url")
        set(v) = put("sub_url", v)

    var selected: String
        get() = str("selected")
        set(v) = put("selected", v)

    var title: String
        get() = str("title")
        set(v) = put("title", v)

    var botUrl: String
        get() = str("bot_url")
        set(v) = put("bot_url", v)

    var expire: Long
        get() = p.getLong("expire", 0L)
        set(v) = p.edit().putLong("expire", v).apply()

    /** Когда подключились: таймер не сбрасывается, если закрыть приложение. 0 — не подключены. */
    var startedAt: Long
        get() = p.getLong("started_at", 0L)
        set(v) = p.edit().putLong("started_at", v).apply()

    /** Банки, Госуслуги и подобные приложения — мимо VPN. По умолчанию включено. */
    var ruApps: Boolean
        get() = p.getBoolean("ru_apps", true)
        set(v) = p.edit().putBoolean("ru_apps", v).apply()

    var mode: Mode
        get() = Mode.of(str("mode"))
        set(v) = put("mode", v.key)

    var dns: Dns
        get() = Dns.of(str("dns"))
        set(v) = put("dns", v.key)

    var autoConnect: Boolean
        get() = p.getBoolean("auto_connect", false)
        set(v) = p.edit().putBoolean("auto_connect", v).apply()

    /** Свои приложения мимо VPN (кроме встроенного списка российских). */
    var bypass: Set<String>
        get() = p.getStringSet("bypass", emptySet())?.toSet() ?: emptySet()
        set(v) = p.edit().putStringSet("bypass", v).apply()

    var lastRefresh: Long
        get() = p.getLong("last_refresh", 0L)
        set(v) = p.edit().putLong("last_refresh", v).apply()

    var configs: List<String>
        get() = try {
            val a = JSONArray(str("configs").ifBlank { "[]" })
            List(a.length()) { a.getJSONObject(it).toString() }
        } catch (e: Exception) {
            emptyList()
        }
        set(v) {
            val a = JSONArray()
            v.forEach { a.put(JSONObject(it)) }
            put("configs", a.toString())
        }

    var pings: Map<String, Long>
        get() = try {
            val o = JSONObject(str("pings").ifBlank { "{}" })
            o.keys().asSequence().associateWith { o.getLong(it) }
        } catch (e: Exception) {
            emptyMap()
        }
        set(v) {
            val o = JSONObject()
            v.forEach { (k, ms) -> o.put(k, ms) }
            put("pings", o.toString())
        }

    fun servers(): List<Server> = configs.mapNotNull {
        try {
            Server(JSONObject(it).optString("remarks", "Сервер"), it)
        } catch (e: Exception) {
            null
        }
    }

    /** Выбранная страна; если её больше нет в подписке — первая. */
    fun current(): Server? {
        val list = servers()
        return list.firstOrNull { it.name == selected } ?: list.firstOrNull()
    }

    fun save(info: Subscription.Info) {
        configs = info.configs
        expire = info.expire
        title = info.title
        if (info.botUrl.isNotBlank()) botUrl = info.botUrl
        lastRefresh = System.currentTimeMillis()
    }

    fun clear() {
        p.edit().clear().apply()
    }
}
