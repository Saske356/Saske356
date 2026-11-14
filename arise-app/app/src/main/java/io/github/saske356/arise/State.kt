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
    val downBps: Long = 0L,   // скорость прямо сейчас, байт/с
    val upBps: Long = 0L,
    val sessionBytes: Long = 0L,
    val history: List<Float> = emptyList(),  // скорость скачивания за последнюю минуту, Мбит/с
)

/** Тест скорости через VPN. */
data class SpeedUi(
    val running: Boolean = false,
    val stage: String = "",
    val downMbps: Double = 0.0,
    val upMbps: Double = 0.0,
    val ping: Long = 0L,
    val jitter: Long = 0L,
    val error: String = "",
)

object SpeedState {
    val flow = MutableStateFlow(SpeedUi())
}

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
    val mode: Mode = Mode.BALANCE,
    val dns: Dns = Dns.CLOUDFLARE,
    val autoConnect: Boolean = false,
    val bypass: Set<String> = emptySet(),
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
                botUrl = Store.botUrl, ruApps = Store.ruApps, mode = Store.mode, dns = Store.dns,
                autoConnect = Store.autoConnect, bypass = Store.bypass,
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
            if (Store.subUrl != url) {
                Store.subUrl = url
                Chat.subscriptionChanged()  // у другой подписки — свой чат
            }
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

    fun setMode(m: Mode) {
        Store.mode = m
        flow.update { it.copy(mode = m) }
    }

    fun setDns(d: Dns) {
        Store.dns = d
        flow.update { it.copy(dns = d) }
    }

    fun setAutoConnect(on: Boolean) {
        Store.autoConnect = on
        flow.update { it.copy(autoConnect = on) }
    }

    fun toggleBypass(pkg: String) {
        val s = Store.bypass.toMutableSet()
        if (!s.add(pkg)) s.remove(pkg)
        Store.bypass = s
        flow.update { it.copy(bypass = s) }
    }

    /** Тест скорости через VPN: задержка и её разброс, скачивание, отдача. */
    fun speedTest() = scope.launch {
        if (SpeedState.flow.value.running) return@launch
        if (VpnState.flow.value.status != Status.RUNNING) {
            SpeedState.flow.value = SpeedUi(error = "Сначала включите VPN — тест идёт через него")
            return@launch
        }
        SpeedState.flow.value = SpeedUi(running = true, stage = "Пинг…")
        try {
            val pings = (1..6).map { AriseVpnService.measure() }.filter { it > 0 }
            val ping = pings.minOrNull() ?: -1L
            val jitter = if (pings.size > 1) pings.zipWithNext { a, b -> kotlin.math.abs(a - b) }.average().toLong() else 0L
            SpeedState.flow.update { it.copy(ping = ping, jitter = jitter, stage = "Скачивание…") }
            val down = SpeedTest.download { mbps -> SpeedState.flow.update { it.copy(downMbps = mbps) } }
            SpeedState.flow.update { it.copy(downMbps = down, stage = "Отдача…") }
            // Отдача не удалась — скачивание всё равно показываем
            val up = try {
                SpeedTest.upload { mbps -> SpeedState.flow.update { it.copy(upMbps = mbps) } }
            } catch (e: Exception) {
                SpeedState.flow.update { it.copy(error = "Отдачу измерить не удалось: ${e.message}") }
                0.0
            }
            SpeedState.flow.update { it.copy(upMbps = up, running = false, stage = "") }
        } catch (e: Exception) {
            SpeedState.flow.update { it.copy(running = false, stage = "", error = "Тест не удался: ${e.message}") }
        }
    }

    fun forget() {
        Store.subUrl = ""
        Chat.subscriptionChanged()
        Store.configs = emptyList()
        Store.pings = emptyMap()
        Store.expire = 0L
        Store.title = ""
        load()
    }
}
