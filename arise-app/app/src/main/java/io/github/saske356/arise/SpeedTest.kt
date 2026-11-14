package io.github.saske356.arise

import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL

/** Скачивание и отдача через ядро (локальный SOCKS → туннель), сервер замера — Cloudflare. */
object SpeedTest {
    private const val SECONDS = 7.0
    private val proxy get() = Proxy(Proxy.Type.SOCKS, InetSocketAddress("127.0.0.1", Core.SOCKS_PORT))

    private fun open(url: String): HttpURLConnection {
        val c = URL(url).openConnection(proxy) as HttpURLConnection
        c.connectTimeout = 10_000
        c.readTimeout = 10_000
        c.setRequestProperty("User-Agent", "AriseApp")
        return c
    }

    /** Мбит/с. progress — промежуточные значения для красивого счётчика. */
    fun download(progress: (Double) -> Unit): Double {
        val c = open("https://speed.cloudflare.com/__down?bytes=200000000")
        try {
            val input = c.inputStream
            val buf = ByteArray(64 * 1024)
            val t0 = System.nanoTime()
            var got = 0L
            var lastReport = t0
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                got += n
                val now = System.nanoTime()
                if (now - lastReport > 250_000_000L) {
                    progress(mbps(got, now - t0))
                    lastReport = now
                }
                if ((now - t0) / 1e9 > SECONDS) break
            }
            return mbps(got, System.nanoTime() - t0)
        } finally {
            c.disconnect()
        }
    }

    fun upload(progress: (Double) -> Unit): Double {
        val c = open("https://speed.cloudflare.com/__up")
        c.doOutput = true
        c.requestMethod = "POST"
        c.setChunkedStreamingMode(64 * 1024)
        c.setRequestProperty("Content-Type", "application/octet-stream")
        val chunk = ByteArray(64 * 1024)
        val t0 = System.nanoTime()
        var sent = 0L
        try {
            c.outputStream.use { out ->
                var lastReport = t0
                while ((System.nanoTime() - t0) / 1e9 < SECONDS && sent < 100_000_000L) {
                    out.write(chunk)
                    sent += chunk.size
                    val now = System.nanoTime()
                    if (now - lastReport > 250_000_000L) {
                        progress(mbps(sent, now - t0))
                        lastReport = now
                    }
                }
            }
            val took = System.nanoTime() - t0
            try {
                c.responseCode  // дождаться ответа сервера
            } catch (e: Exception) {
                // ответ не важен, важна скорость отправки
            }
            return mbps(sent, took)
        } finally {
            c.disconnect()
        }
    }

    private fun mbps(bytes: Long, nanos: Long): Double = if (nanos <= 0) 0.0 else bytes * 8.0 / (nanos / 1e9) / 1_000_000.0
}
