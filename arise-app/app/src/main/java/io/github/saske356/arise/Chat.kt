package io.github.saske356.arise

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL
import java.net.URLEncoder
import java.security.SecureRandom

data class ChatContact(val code: String, val name: String, val key: String, val verified: Boolean, val keyChanged: Boolean)
data class ChatMsg(val id: String, val out: Boolean, val text: String, val t: Long, val exp: Long)

/** Состояние чата для экранов. */
data class ChatUi(
    val unlocked: Boolean = false,
    val decoy: Boolean = false,       // открыт вторым PIN: второй профиль со своим кодом и собеседниками
    val code: String = "",
    val contacts: List<ChatContact> = emptyList(),
    val msgs: Map<String, List<ChatMsg>> = emptyMap(),
    val unread: Map<String, Int> = emptyMap(),
    val ttlHours: Int = 24,
    val noScreens: Boolean = true,
    val lockOnLeave: Boolean = true,
    val hasDecoy: Boolean = false,
    val admin: Boolean = false,
    val enabled: Boolean = true,
    val adminUsers: Int = 0,
    val adminQueued: Int = 0,
    val error: String = "",
    val busy: Boolean = false,
)

/**
 * Чат: связь с сервером подписок (<подписка>/chat/…), шифрование (ChatCrypto) и хранилище (ChatVault).
 * Пока чат открыт настоящим PIN, раз в 4 секунды забираем новые письма.
 */
object Chat {
    val flow = MutableStateFlow(ChatUi())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Mutex()
    private var vault: ChatVault.Opened? = null
    private var poll: Job? = null
    private val rnd = SecureRandom()

    // ---------- сервер ----------

    private fun base(): String = Store.subUrl.trim().substringBefore('?').trimEnd('/') + "/chat/"

    private fun request(path: String, body: JSONObject? = null): JSONObject {
        var last: Exception? = null
        val viaVpn = VpnState.flow.value.status == Status.RUNNING
        for (tunnel in if (viaVpn) listOf(true, false) else listOf(false)) {
            val url = URL(base() + path)
            val c = (if (tunnel) url.openConnection(Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", Core.SOCKS_PORT)))
            else url.openConnection()) as HttpURLConnection
            try {
                c.connectTimeout = 15_000
                c.readTimeout = 20_000
                c.setRequestProperty("User-Agent", "AriseApp/${BuildConfig.VERSION_NAME}")
                c.setRequestProperty("x-hwid", Subscription.hwid)
                c.setRequestProperty("x-device-model", android.os.Build.MODEL ?: "")
                c.setRequestProperty("x-device-os", "Android")
                // второй профиль (второй PIN) — отдельный код чата на том же месте в подписке
                if (vault?.slot == ChatVault.Slot.DECOY) c.setRequestProperty("x-chat-profile", "1")
                if (body != null) {
                    val raw = body.toString().toByteArray()
                    c.requestMethod = "POST"
                    c.doOutput = true
                    c.setRequestProperty("Content-Type", "application/json")
                    c.setFixedLengthStreamingMode(raw.size)
                    c.outputStream.use { it.write(raw) }
                }
                val stream = if (c.responseCode < 400) c.inputStream else c.errorStream
                val text = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
                return JSONObject(text)
            } catch (e: Exception) {
                last = e
            } finally {
                c.disconnect()
            }
        }
        throw last ?: IllegalStateException("нет связи")
    }

    private fun explain(err: String): String = when (err) {
        "subscription expired" -> "Подписка закончилась — продлите её в боте, и чат снова откроется"
        "device limit" -> "Все места в подписке заняты другими устройствами. Освободите место в боте: подписка → 📱 Устройства"
        "disabled" -> "Чат временно выключен администратором"
        "no device id" -> "Не удалось определить устройство"
        "too fast" -> "Слишком часто — подождите минуту"
        "recipient box full" -> "У собеседника переполнен ящик: пусть откроет чат"
        "no such code" -> "Такого кода нет"
        else -> "Ошибка сервера: $err"
    }

    // ---------- вход ----------

    /** Первый вход: создать хранилище под PIN и новые ключи устройства. */
    fun setup(pin: String) = scope.launch {
        lock.withLock {
            val keys = ChatCrypto.newKeys()
            val data = JSONObject().put("sk", keys.enc).put("ssk", keys.sign).put("pk", keys.public)
                .put("code", "").put("contacts", JSONArray()).put("msgs", JSONObject())
                .put("ttl", 24).put("secure", true).put("lockLeave", true)
            vault = ChatVault.create(ChatVault.Slot.REAL, pin, data)
        }
        opened()
    }

    /** Ввод PIN. Возвращает текст ошибки или null. */
    suspend fun unlock(pin: String): String? = lock.withLock {
        when (val r = ChatVault.unlock(pin)) {
            is ChatVault.Unlock.Ok -> vault = r.vault
            is ChatVault.Unlock.Wrong -> return@withLock "Неверный PIN. Осталось попыток: ${r.left}"
            ChatVault.Unlock.Wiped -> return@withLock "Слишком много попыток — переписка стёрта"
        }
        null
    }.also { if (it == null) opened() }

    private fun opened() {
        publish()
        // Оба профиля — настоящие живые чаты: второй (по второму PIN) со своим кодом и собеседниками.
        // Пустой «ложный» чат сам вызывал подозрение, а живая обычная переписка — нет.
        scope.launch { register() }
        startPolling()
    }

    /** Закрыть чат: ключи и переписка уходят из памяти. */
    fun lockNow() {
        poll?.cancel()
        poll = null
        vault = null
        flow.value = ChatUi()
    }

    // ---------- данные хранилища ----------

    private fun d(): JSONObject? = vault?.data

    private fun contacts(): List<ChatContact> {
        val a = d()?.optJSONArray("contacts") ?: return emptyList()
        return List(a.length()) {
            val o = a.getJSONObject(it)
            ChatContact(o.getString("code"), o.optString("name"), o.optString("key"),
                o.optBoolean("verified"), o.optBoolean("changed"))
        }
    }

    private fun putContact(c: ChatContact) {
        val data = d() ?: return
        val a = JSONArray()
        var found = false
        for (x in contacts()) {
            val y = if (x.code == c.code) c.also { found = true } else x
            a.put(JSONObject().put("code", y.code).put("name", y.name).put("key", y.key)
                .put("verified", y.verified).put("changed", y.keyChanged))
        }
        if (!found) a.put(JSONObject().put("code", c.code).put("name", c.name).put("key", c.key)
            .put("verified", c.verified).put("changed", c.keyChanged))
        data.put("contacts", a)
    }

    private fun msgsOf(code: String): MutableList<ChatMsg> {
        val a = d()?.optJSONObject("msgs")?.optJSONArray(code) ?: return mutableListOf()
        return MutableList(a.length()) {
            val o = a.getJSONObject(it)
            ChatMsg(o.getString("id"), o.optBoolean("out"), o.optString("x"), o.optLong("t"), o.optLong("exp"))
        }
    }

    private fun putMsgs(code: String, list: List<ChatMsg>) {
        val data = d() ?: return
        val all = data.optJSONObject("msgs") ?: JSONObject().also { data.put("msgs", it) }
        val a = JSONArray()
        list.forEach { a.put(JSONObject().put("id", it.id).put("out", it.out).put("x", it.text).put("t", it.t).put("exp", it.exp)) }
        if (list.isEmpty()) all.remove(code) else all.put(code, a)
    }

    /** Сообщения с истёкшим сроком исчезают у обоих: срок задаёт отправитель. */
    private fun dropExpired(): Boolean {
        val now = System.currentTimeMillis()
        var changed = false
        val codes = d()?.optJSONObject("msgs")?.keys()?.asSequence()?.toList() ?: emptyList()
        for (c in codes) {
            val list = msgsOf(c)
            val left = list.filter { it.exp == 0L || it.exp > now }
            if (left.size != list.size) {
                putMsgs(c, left)
                changed = true
            }
        }
        return changed
    }

    private fun publish(unread: Map<String, Int>? = null) {
        val data = d() ?: return
        val cs = contacts()
        val codes = (cs.map { it.code } + (data.optJSONObject("msgs")?.keys()?.asSequence()?.toList() ?: emptyList())).distinct()
        flow.update {
            it.copy(
                unlocked = true, decoy = vault?.slot == ChatVault.Slot.DECOY,
                code = data.optString("code"), contacts = cs,
                msgs = codes.associateWith { c -> msgsOf(c) },
                unread = unread ?: it.unread,
                ttlHours = data.optInt("ttl", 24), noScreens = data.optBoolean("secure", true),
                lockOnLeave = data.optBoolean("lockLeave", true),
                // во втором профиле «второй PIN задан» — как в основном, иначе видно, какой профиль открыт
                hasDecoy = if (vault?.slot == ChatVault.Slot.DECOY) data.optBoolean("fd", true)
                else ChatVault.exists(ChatVault.Slot.DECOY),
            )
        }
    }

    // ---------- сеть ----------

    /** Отдать серверу открытый ключ и узнать свой код; заодно — включён ли чат и не админ ли я. */
    private suspend fun register() {
        try {
            val st = request("status")
            if (st.has("error")) {
                flow.update { it.copy(error = explain(st.getString("error"))) }
                return
            }
            flow.update { it.copy(admin = st.optBoolean("admin"), enabled = st.optBoolean("enabled", true)) }
            val data = d() ?: return
            if (st.optString("code").isEmpty() || st.optString("code") != data.optString("code")) {
                val r = request("register", JSONObject().put("key", data.getString("pk")))
                if (r.has("error")) {
                    flow.update { it.copy(error = explain(r.getString("error"))) }
                    return
                }
                lock.withLock {
                    data.put("code", r.getString("code"))
                    vault?.save()
                }
            }
            flow.update { it.copy(error = "") }
            publish()
            if (flow.value.admin) refreshAdmin()
        } catch (e: Exception) {
            flow.update { it.copy(error = "Нет связи с сервером: ${e.message}") }
        }
    }

    private fun startPolling() {
        poll?.cancel()
        poll = scope.launch {
            while (isActive) {
                try {
                    fetch()
                } catch (e: Exception) {
                    // нет связи — попробуем через 4 секунды
                }
                lock.withLock { if (dropExpired()) vault?.save() }
                publish()
                delay(4_000)
            }
        }
    }

    private suspend fun keyOf(code: String): String? {
        val r = request("key?code=" + URLEncoder.encode(code, "UTF-8"))
        return if (r.has("error")) null else r.optString("key").ifEmpty { null }
    }

    /** Забрать письма: расшифровать, проверить подпись, сохранить, подтвердить серверу. */
    private suspend fun fetch() {
        val data = d() ?: return
        if (data.optString("code").isEmpty()) return
        val r = request("inbox")
        val arr = r.optJSONArray("messages") ?: return
        if (arr.length() == 0) return
        val done = JSONArray()
        val counts = flow.value.unread.toMutableMap()
        lock.withLock {
            for (i in 0 until arr.length()) {
                val m = arr.getJSONObject(i)
                done.put(m.getString("id"))
                val from = m.optString("from")
                try {
                    val (payload, sig) = ChatCrypto.open(m.getString("box"), data.getString("sk"))
                    val p = JSONObject(String(payload))
                    if (p.optString("f") != from) continue  // внутри другой отправитель — подделка
                    var c = contacts().firstOrNull { it.code == from }
                    var key = c?.key
                    if (key == null || !ChatCrypto.verify(payload, sig, key)) {
                        // новый собеседник или он сменил ключ (новый телефон)
                        val fresh = keyOf(from) ?: continue
                        if (!ChatCrypto.verify(payload, sig, fresh)) continue
                        c = if (c == null) ChatContact(from, "Новый · ${pretty(from)}", fresh, false, false)
                        else c.copy(key = fresh, verified = false, keyChanged = true)
                        putContact(c)
                        key = fresh
                    }
                    val list = msgsOf(from)
                    val id = p.optString("id")
                    if (list.none { it.id == id }) {
                        val ttl = p.optLong("ttl")
                        list.add(ChatMsg(id, false, p.optString("x"), p.optLong("t"),
                            if (ttl > 0) System.currentTimeMillis() + ttl * 3_600_000L else 0L))
                        putMsgs(from, list)
                        counts[from] = (counts[from] ?: 0) + 1
                    }
                } catch (e: Exception) {
                    // письмо не для этого ключа (переустановка) или повреждено — просто подтверждаем
                }
            }
            vault?.save()
        }
        request("ack", JSONObject().put("ids", done))
        publish(counts)
    }

    fun pretty(code: String) = code.chunked(3).joinToString("-")

    // ---------- действия ----------

    fun send(code: String, text: String) = scope.launch {
        val c = contacts().firstOrNull { it.code == code } ?: return@launch
        val data = d() ?: return@launch
        val ttl = data.optInt("ttl", 24)
        val id = ByteArray(8).also { rnd.nextBytes(it) }.joinToString("") { "%02x".format(it) }
        val now = System.currentTimeMillis()
        val payload = JSONObject().put("f", data.optString("code")).put("id", id).put("x", text)
            .put("t", now).put("ttl", ttl)
        lock.withLock {
            val list = msgsOf(code)
            list.add(ChatMsg(id, true, text, now, if (ttl > 0) now + ttl * 3_600_000L else 0L))
            putMsgs(code, list)
            vault?.save()
        }
        publish()
        try {
            val r = request("send", JSONObject().put("to", code).put("box", ChatCrypto.seal(payload, data.getString("ssk"), c.key)))
            if (r.has("error")) flow.update { it.copy(error = explain(r.getString("error"))) }
        } catch (e: Exception) {
            flow.update { it.copy(error = "Не отправлено: нет связи") }
        }
    }

    /** Новый собеседник по коду: берём его открытый ключ с сервера. */
    suspend fun addContact(rawCode: String, name: String): String? {
        val code = rawCode.uppercase().filter { it in "ABCDEFGHJKMNPQRSTUVWXYZ23456789" }
        if (code.length != 9) return "Код — 9 знаков, например K7M-2QX-9TR"
        if (code == d()?.optString("code")) return "Это ваш собственный код"
        val key = try {
            keyOf(code)
        } catch (e: Exception) {
            return "Нет связи с сервером"
        } ?: return "Такого кода нет"
        lock.withLock {
            putContact(ChatContact(code, name.ifBlank { pretty(code) }, key, false, false))
            vault?.save()
        }
        publish()
        return null
    }

    fun rename(code: String, name: String) = scope.launch {
        lock.withLock {
            contacts().firstOrNull { it.code == code }?.let { putContact(it.copy(name = name)) }
            vault?.save()
        }
        publish()
    }

    fun markVerified(code: String) = scope.launch {
        lock.withLock {
            contacts().firstOrNull { it.code == code }?.let { putContact(it.copy(verified = true, keyChanged = false)) }
            vault?.save()
        }
        publish()
    }

    fun deleteChat(code: String) = scope.launch {
        lock.withLock {
            putMsgs(code, emptyList())
            val data = d() ?: return@withLock
            val a = JSONArray()
            contacts().filter { it.code != code }.forEach {
                a.put(JSONObject().put("code", it.code).put("name", it.name).put("key", it.key)
                    .put("verified", it.verified).put("changed", it.keyChanged))
            }
            data.put("contacts", a)
            vault?.save()
        }
        publish()
    }

    fun read(code: String) = flow.update { it.copy(unread = it.unread - code) }

    /** Подписку сменили — у новой своё хранилище. */
    fun subscriptionChanged() = lockNow()

    fun safety(code: String): String {
        val mine = d()?.optString("pk") ?: return ""
        val theirs = contacts().firstOrNull { it.code == code }?.key ?: return ""
        return ChatCrypto.safetyNumber(mine, theirs)
    }

    fun setTtl(hours: Int) = setting { put("ttl", hours) }
    fun setNoScreens(on: Boolean) = setting { put("secure", on) }
    fun setLockOnLeave(on: Boolean) = setting { put("lockLeave", on) }

    private fun setting(f: JSONObject.() -> Unit) = scope.launch {
        lock.withLock {
            d()?.f()
            vault?.save()
        }
        publish()
    }

    suspend fun changePin(pin: String): String? = lock.withLock {
        val v = vault ?: return@withLock "Чат закрыт"
        if (v.slot == ChatVault.Slot.REAL && ChatVault.exists(ChatVault.Slot.DECOY) && ChatVault.opensDecoy(pin)) {
            return@withLock "Этот PIN не подходит — выберите другой"
        }
        if (v.slot == ChatVault.Slot.DECOY && ChatVault.opensReal(pin)) {
            return@withLock "Этот PIN не подходит — выберите другой"  // то же сообщение: ничего не выдаём
        }
        v.changePin(pin)
        null
    }

    /** Второй PIN: отдельное хранилище со своими ключами — второй живой чат. Не совпадает с основным. */
    suspend fun setDecoy(pin: String): String? = lock.withLock {
        // Из второго профиля «задать второй PIN» только делает вид: основной профиль не трогаем
        if (vault?.slot == ChatVault.Slot.DECOY) {
            d()?.put("fd", true)
            vault?.save()
            return@withLock null
        }
        if (ChatVault.opensReal(pin)) return@withLock "Второй PIN должен отличаться от основного"
        val keys = ChatCrypto.newKeys()
        ChatVault.create(ChatVault.Slot.DECOY, pin,
            JSONObject().put("sk", keys.enc).put("ssk", keys.sign).put("pk", keys.public)
                .put("code", "").put("contacts", JSONArray()).put("msgs", JSONObject())
                .put("ttl", 24).put("secure", true).put("lockLeave", true))
        null
    }.also { publish() }

    fun dropDecoy() = scope.launch {
        lock.withLock {
            if (vault?.slot == ChatVault.Slot.DECOY) {
                // из второго профиля его самого не убрать — только делаем вид
                d()?.put("fd", false)
                vault?.save()
            } else ChatVault.dropDecoy()
        }
        publish()
    }

    /** «Стереть всё»: хранилища, ключи и переписка; на сервере ключ заменится при следующем входе. */
    fun wipe() {
        lockNow()
        ChatVault.wipe()
    }

    // ---------- админ ----------

    fun refreshAdmin() = scope.launch {
        try {
            val r = request("admin")
            if (!r.has("error")) flow.update {
                it.copy(enabled = r.optBoolean("enabled", true), adminUsers = r.optInt("users"), adminQueued = r.optInt("queued"))
            }
        } catch (e: Exception) {
            // нет связи
        }
    }

    fun setEnabled(on: Boolean) = scope.launch {
        try {
            val r = request("admin", JSONObject().put("enabled", on))
            if (!r.has("error")) flow.update {
                it.copy(enabled = r.optBoolean("enabled", on), adminUsers = r.optInt("users"), adminQueued = r.optInt("queued"))
            }
        } catch (e: Exception) {
            flow.update { it.copy(error = "Нет связи с сервером") }
        }
    }
}
