package ru.oniks.rp;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Игровой кэш: сверяет локальные файлы с манифестом сервера и докачивает изменённые.
 * Манифест (GET /api/manifest) — текст: «version X», затем строки «sha256 размер /путь».
 * Без зависимостей от Android, поэтому проверяется на обычной JVM.
 */
public final class CacheSync {

    public interface Listener {
        void onProgress(long doneBytes, long totalBytes, int doneFiles, int totalFiles, long bytesPerSec, String file);
    }

    public static final class Entry {
        public final String sha;
        public final long size;
        public final String path;

        Entry(String sha, long size, String path) {
            this.sha = sha;
            this.size = size;
            this.path = path;
        }
    }

    public static final class Plan {
        public String version;
        public final List<Entry> all = new ArrayList<>();
        public final List<Entry> missing = new ArrayList<>();
        public long missingBytes;
    }

    private static final String INDEX = ".index";
    private final String base;
    private final File dir;
    private volatile boolean cancelled;

    public CacheSync(String serverUrl, File cacheRoot) {
        this.base = serverUrl.replaceAll("/+$", "");
        this.dir = folderFor(cacheRoot, serverUrl);
    }

    /** Отдельная папка на каждый сервер: у разных серверов могут быть разные версии. */
    public static File folderFor(File cacheRoot, String serverUrl) {
        String name = serverUrl.toLowerCase(Locale.ROOT).replaceAll("^https?://", "").replaceAll("[^a-z0-9.-]", "_");
        return new File(cacheRoot, name);
    }

    public File dir() {
        return dir;
    }

    public void cancel() {
        cancelled = true;
    }

    /** Есть ли полностью скачанный кэш (без обращения к сети). */
    public boolean isReady() {
        return new File(dir, "index.html").isFile() && new File(dir, INDEX).isFile();
    }

    public Plan check() throws IOException {
        Plan plan = new Plan();
        HttpURLConnection c = open(base + "/api/manifest", 0);
        try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;
                if (line.startsWith("version ")) { plan.version = line.substring(8).trim(); continue; }
                String[] p = line.split(" ");
                if (p.length != 3 || !p[0].matches("[0-9a-f]{64}") || !safePath(p[2])) throw new IOException("Повреждённый манифест");
                plan.all.add(new Entry(p[0], Long.parseLong(p[1]), p[2]));
            }
        } finally {
            c.disconnect();
        }
        if (plan.all.isEmpty()) throw new IOException("Сервер не отдал список файлов");
        Map<String, String> local = readIndex();
        for (Entry e : plan.all) {
            File f = file(e.path);
            if (!e.sha.equals(local.get(e.path)) || !f.isFile() || f.length() != e.size) {
                plan.missing.add(e);
                plan.missingBytes += e.size;
            }
        }
        return plan;
    }

    /** Скачивает недостающие файлы, проверяет sha256 и удаляет лишние. */
    public void sync(Plan plan, Listener listener) throws IOException {
        cancelled = false;
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("Не удалось создать папку кэша");
        Map<String, String> index = readIndex();
        long done = 0, windowBytes = 0, speed = 0;
        long windowStart = System.nanoTime(), lastReport = 0;
        int files = 0;
        byte[] buf = new byte[64 * 1024];
        for (Entry e : plan.missing) {
            if (cancelled) throw new IOException("Загрузка отменена");
            File target = file(e.path), part = new File(target.getPath() + ".part");
            File parent = target.getParentFile();
            if (parent != null && !parent.isDirectory() && !parent.mkdirs()) throw new IOException("Нет доступа к " + parent);
            MessageDigest md = sha256();
            long have = part.isFile() ? part.length() : 0;
            if (have > e.size) { part.delete(); have = 0; }
            if (have > 0) {
                try (InputStream in = new FileInputStream(part)) {
                    int n;
                    while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
                }
            }
            done += have;
            if (have < e.size || e.size == 0) {
                HttpURLConnection c = open(base + encode(e.path), have);
                boolean resumed = c.getResponseCode() == 206;
                if (have > 0 && !resumed) { // сервер не умеет докачку — начинаем файл заново
                    done -= have;
                    have = 0;
                    md = sha256();
                }
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(part, resumed)) {
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        if (cancelled) throw new IOException("Загрузка отменена");
                        out.write(buf, 0, n);
                        md.update(buf, 0, n);
                        done += n;
                        windowBytes += n;
                        long now = System.nanoTime();
                        if (now - windowStart > 1_000_000_000L) {
                            speed = windowBytes * 1_000_000_000L / (now - windowStart);
                            windowBytes = 0;
                            windowStart = now;
                        }
                        if (listener != null && now - lastReport > 150_000_000L) {
                            lastReport = now;
                            listener.onProgress(done, plan.missingBytes, files, plan.missing.size(), speed, e.path);
                        }
                    }
                } finally {
                    c.disconnect();
                }
            }
            String got = hex(md.digest());
            if (!got.equals(e.sha)) {
                part.delete();
                throw new IOException("Файл повреждён при загрузке: " + e.path + ". Попробуйте ещё раз");
            }
            if (target.exists() && !target.delete()) throw new IOException("Не удалось заменить " + e.path);
            if (!part.renameTo(target)) throw new IOException("Не удалось сохранить " + e.path);
            index.put(e.path, e.sha);
            writeIndex(index);
            files++;
            if (listener != null) listener.onProgress(done, plan.missingBytes, files, plan.missing.size(), speed, e.path);
        }
        // удаляем файлы, которых больше нет в манифесте
        Map<String, String> fresh = new LinkedHashMap<>();
        for (Entry e : plan.all) fresh.put(e.path, e.sha);
        for (String p : index.keySet()) if (!fresh.containsKey(p)) file(p).delete();
        writeIndex(fresh);
    }

    // ---------- вспомогательное ----------

    private HttpURLConnection open(String url, long from) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(8000);
        c.setReadTimeout(20000);
        c.setRequestProperty("Accept-Encoding", "identity");
        if (from > 0) c.setRequestProperty("Range", "bytes=" + from + "-");
        int code = c.getResponseCode();
        if (code != 200 && code != 206) {
            c.disconnect();
            throw new IOException("Сервер ответил " + code + " на " + url);
        }
        return c;
    }

    static boolean safePath(String p) {
        return p.startsWith("/") && !p.contains("..") && !p.contains("\\") && !p.contains("//") && !p.endsWith("/")
                && !p.endsWith(".part") && !p.equals("/" + INDEX);
    }

    private File file(String path) {
        return new File(dir, path.substring(1));
    }

    private static String encode(String path) {
        StringBuilder b = new StringBuilder();
        for (String seg : path.substring(1).split("/")) {
            try {
                b.append('/').append(java.net.URLEncoder.encode(seg, "UTF-8").replace("+", "%20"));
            } catch (java.io.UnsupportedEncodingException ex) {
                throw new IllegalStateException(ex);
            }
        }
        return b.toString();
    }

    private Map<String, String> readIndex() {
        Map<String, String> m = new LinkedHashMap<>();
        File f = new File(dir, INDEX);
        if (!f.isFile()) return m;
        try (BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(f), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                int sp = line.indexOf(' ');
                if (sp == 64) m.put(line.substring(65), line.substring(0, 64));
            }
        } catch (IOException ignored) {
        }
        return m;
    }

    private void writeIndex(Map<String, String> m) throws IOException {
        File tmp = new File(dir, INDEX + ".tmp"), f = new File(dir, INDEX);
        try (Writer w = new OutputStreamWriter(new FileOutputStream(tmp), StandardCharsets.UTF_8)) {
            for (Map.Entry<String, String> e : m.entrySet()) w.write(e.getValue() + " " + e.getKey() + "\n");
        }
        if (f.exists() && !f.delete()) throw new IOException("Не удалось обновить индекс кэша");
        if (!tmp.renameTo(f)) throw new IOException("Не удалось обновить индекс кэша");
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder(b.length * 2);
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }
}
