package io.github.saske356.arise

import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread

/**
 * Тест скорости через ядро (локальный SOCKS → туннель). Несколько потоков одновременно, как в
 * настоящих спидтестах: один поток через далёкий сервер редко забивает канал целиком.
 *
 * Cloudflare отдаёт за раз меньше 100 МБ (на 200 МБ отвечает 403 — из-за этого тест раньше
 * не работал), поэтому файлы берутся по 25 МБ и запрашиваются заново, пока идёт замер.
 * Если Cloudflare недоступен — запасные серверы Hetzner и OVH.
 */
object SpeedTest {
    private const val SECONDS = 8.0
    private const val STREAMS = 4
    private const val REPORT_NS = 250_000_000L

    private val DOWNLOAD = listOf(
        "https://speed.cloudflare.com/__down?bytes=25000000",
        "https://fsn1-speed.hetzner.com/100MB.bin",
        "https://nbg1-speed.hetzner.com/100MB.bin",
        "https://proof.ovh.net/files/100Mb.dat",
    )
    private const val UPLOAD = "https://speed.cloudflare.com/__up"
    private const val UPLOAD_CHUNK = 4_000_000

    private val proxy get() = Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", Core.SOCKS_PORT))

    private fun open(url: String): HttpURLConnection {
        val c = URL(url).openConnection(proxy) as HttpURLConnection
        c.connectTimeout = 10_000
        c.readTimeout = 10_000
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android) AriseApp")
        c.useCaches = false
        return c
    }

    /** Первый сервер, который отвечает 200 через туннель. */
    private fun pickSource(): String {
        var last: Exception? = null
        for (url in DOWNLOAD) {
            try {
                val c = open(url)
                c.setRequestProperty("Range", "bytes=0-1023")
                try {
                    val code = c.responseCode
                    if (code == 200 || code == 206) return url
                    last = IllegalStateException("$code от ${URL(url).host}")
                } finally {
                    c.disconnect()
                }
            } catch (e: Exception) {
                last = e
            }
        }
        throw IllegalStateException("серверы замера недоступны (${last?.message ?: "нет ответа"})")
    }

    /** Мбит/с. progress — промежуточные значения для счётчика на экране. */
    fun download(progress: (Double) -> Unit): Double {
        val url = pickSource()
        val got = AtomicLong()
        val err = AtomicReference<Exception?>(null)
        val t0 = System.nanoTime()
        val until = t0 + (SECONDS * 1e9).toLong()
        val workers = List(STREAMS) {
            thread(isDaemon = true) {
                val buf = ByteArray(64 * 1024)
                try {
                    while (System.nanoTime() < until) {
                        val c = open(url)
                        try {
                            if (c.responseCode !in 200..299) throw IllegalStateException("ответ ${c.responseCode}")
                            c.inputStream.use { input ->
                                while (System.nanoTime() < until) {
                                    val n = input.read(buf)
                                    if (n < 0) break
                                    got.addAndGet(n.toLong())
                                }
                            }
                        } finally {
                            c.disconnect()
                        }
                    }
                } catch (e: Exception) {
                    err.compareAndSet(null, e)
                }
            }
        }
        report(workers, t0, got, progress)
        val total = got.get()
        if (total == 0L) throw IllegalStateException("скачивание не пошло: ${err.get()?.message ?: "нет данных"}")
        return mbps(total, System.nanoTime() - t0)
    }

    /** Отдача: несколько потоков шлют куски по 4 МБ на Cloudflare. */
    fun upload(progress: (Double) -> Unit): Double {
        val sent = AtomicLong()
        val err = AtomicReference<Exception?>(null)
        val chunk = ByteArray(64 * 1024)
        val t0 = System.nanoTime()
        val until = t0 + (SECONDS * 1e9).toLong()
        val workers = List(STREAMS) {
            thread(isDaemon = true) {
                try {
                    while (System.nanoTime() < until) {
                        val c = open(UPLOAD)
                        try {
                            c.doOutput = true
                            c.requestMethod = "POST"
                            c.setFixedLengthStreamingMode(UPLOAD_CHUNK)
                            c.setRequestProperty("Content-Type", "application/octet-stream")
                            var left = UPLOAD_CHUNK
                            c.outputStream.use { out ->
                                while (left > 0 && System.nanoTime() < until) {
                                    val n = minOf(left, chunk.size)
                                    out.write(chunk, 0, n)
                                    left -= n
                                    sent.addAndGet(n.toLong())
                                }
                            }
                            if (left > 0) break  // время вышло посреди куска
                            try {
                                c.responseCode  // дождаться ответа, прежде чем слать следующий кусок
                            } catch (e: Exception) {
                                // ответ не важен, важна скорость отправки
                            }
                        } finally {
                            c.disconnect()
                        }
                    }
                } catch (e: Exception) {
                    err.compareAndSet(null, e)
                }
            }
        }
        report(workers, t0, sent, progress)
        val total = sent.get()
        if (total == 0L) throw IllegalStateException("отдача не пошла: ${err.get()?.message ?: "нет данных"}")
        return mbps(total, System.nanoTime() - t0)
    }

    /** Пока потоки работают — раз в четверть секунды отдавать текущую скорость. */
    private fun report(workers: List<Thread>, t0: Long, bytes: AtomicLong, progress: (Double) -> Unit) {
        while (workers.any { it.isAlive }) {
            Thread.sleep(REPORT_NS / 1_000_000L)
            progress(mbps(bytes.get(), System.nanoTime() - t0))
        }
    }

    private fun mbps(bytes: Long, nanos: Long): Double = if (nanos <= 0) 0.0 else bytes * 8.0 / (nanos / 1e9) / 1_000_000.0
}
