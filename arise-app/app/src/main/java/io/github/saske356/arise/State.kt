package io.github.saske356.arise

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit

enum class Status { STOPPED, CONNECTING, RUNNING }

/** Состояние VPN для экрана: служба пишет, экран читает. */
data class VpnUi(
    val status: Status = Status.STOPPED,
    val server: String = "",
    val ping: Long = 0L,      // живая задержка через туннель: 0 — ещё не мерили, -1 — нет связи
    val note: String = "",    // «Связь пропала — переключено на …»
    val error: String = "",
)

object VpnState {
    val flow = MutableStateFlow(VpnUi())
    fun update(f: (VpnUi) -> VpnUi) = flow.update(f)
}

/** Подписка и замеры для экрана. */
data class Data(
    val subUrl: String = "",
    val servers: List<Server> = emptyList(),
    val pings: Map<String, Long> = emptyMap(),
    val selected: String = "",
    val expire: Long = 0L,
    val title: String = "",
    val botUrl: String = "",
    val ruApps: Boolean = true,
    val loading: Boolean = false,
    val pinging: Boolean = false,
    val error: String = "",
)

object Repo {
    val flow = MutableStateFlow(Data())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    lateinit var app: Context

    fun load() {
        flow.update {
            it.copy(
                subUrl = Store.subUrl, servers = Store.servers(), pings = Store.pings,
                selected = Store.current()?.name ?: "", expire = Store.expire, title = Store.title,
                botUrl = Store.botUrl, ruApps = Store.ruApps,
            )
        }
    }

    /** Скачать подписку. Когда VPN включён — через туннель (если оператор режет прямой доступ). */
    fun refresh(newUrl: String? = null) = scope.launch {
        val url = (newUrl ?: Store.subUrl).trim()
        if (url.isBlank()) return@launch
        flow.update { it.copy(loading = true, error = "") }
        try {
            val running = VpnState.flow.value.status == Status.RUNNING
            val info = if (running) {
                try {
                    Subscription.fetch(url, Core.SOCKS_PORT)
                } catch (e: Exception) {
                    Subscription.fetch(url)
                }
            } else Subscription.fetch(url)
            Store.subUrl = url
            Store.save(info)
            load()
            pingAll()
        } catch (e: Exception) {
            flow.update { it.copy(error = e.message ?: "Не удалось обновить подписку") }
        } finally {
            flow.update { it.copy(loading = false) }
        }
    }

    /** Настоящая задержка до каждой страны (по 3 одновременно). */
    fun pingAll() = scope.launch {
        if (flow.value.pinging) return@launch
        flow.update { it.copy(pinging = true) }
        try {
            Core.init(app)
            val sem = Semaphore(3)
            val results = Store.servers().map { s ->
                async { sem.withPermit { s.name to Core.measure(s.json) } }
            }.awaitAll().toMap()
            Store.pings = results
            flow.update { it.copy(pings = results) }
        } finally {
            flow.update { it.copy(pinging = false) }
        }
    }

    fun select(name: String) {
        Store.selected = name
        flow.update { it.copy(selected = name) }
    }

    fun setRuApps(on: Boolean) {
        Store.ruApps = on
        flow.update { it.copy(ruApps = on) }
    }

    fun forget() {
        Store.subUrl = ""
        Store.configs = emptyList()
        Store.pings = emptyMap()
        Store.expire = 0L
        Store.title = ""
        load()
    }
}
