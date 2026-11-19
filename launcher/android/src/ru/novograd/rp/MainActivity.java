package ru.novograd.rp;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import org.json.JSONObject;
import java.io.File;

/** Лаунчер: интерфейс из assets/launcher, мост в Java через объект NovogradApp. */
public class MainActivity extends Activity {
    private WebView web;
    private volatile CacheSync running;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Screen.immersive(this);
        web = Screen.webView(this);
        web.getSettings().setAllowFileAccess(true);
        web.addJavascriptInterface(new Bridge(), "NovogradApp");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if ("file".equals(u.getScheme())) return false;
                openExternal(u.toString());
                return true;
            }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/launcher/index.html");
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) Screen.immersive(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        web.evaluateJavascript("window.onLauncherResume && window.onLauncherResume()", null);
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        web.evaluateJavascript("window.onLauncherBack ? window.onLauncherBack() : false", new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String value) {
                if (!"true".equals(value)) finish();
            }
        });
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        f.delete();
    }

    private void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) {
        }
    }

    static File cacheRoot(Activity a) {
        return new File(a.getFilesDir(), "gamecache");
    }

    /** Вызов JS-функции лаунчера с объектом-аргументом из UI-потока. */
    private void emit(final String fn, final JSONObject arg) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                web.evaluateJavascript("window." + fn + " && window." + fn + "(" + arg + ")", null);
            }
        });
    }

    private static JSONObject obj(Object... kv) {
        JSONObject o = new JSONObject();
        try {
            for (int i = 0; i < kv.length; i += 2) o.put((String) kv[i], kv[i + 1]);
        } catch (org.json.JSONException ignored) {
        }
        return o;
    }

    private static String message(Exception e) {
        String m = e.getMessage();
        if (e instanceof java.net.UnknownHostException) return "Сервер не найден — проверьте адрес";
        if (e instanceof java.net.ConnectException) return "Сервер не отвечает";
        if (e instanceof java.net.SocketTimeoutException) return "Слишком долгий ответ сервера — проверьте интернет";
        return m == null ? e.getClass().getSimpleName() : m;
    }

    private class Bridge {
        /** Проверка кэша: отвечает в window.onCacheCheck({ok, files, bytes, version, ready, error}). */
        @JavascriptInterface
        public void checkCache(final String url) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    CacheSync s = new CacheSync(url, cacheRoot(MainActivity.this));
                    try {
                        CacheSync.Plan p = s.check();
                        emit("onCacheCheck", obj("ok", true, "files", p.missing.size(), "bytes", p.missingBytes,
                                "version", p.version == null ? "" : p.version, "ready", s.isReady()));
                    } catch (Exception e) {
                        emit("onCacheCheck", obj("ok", false, "error", message(e), "ready", s.isReady()));
                    }
                }
            }, "cache-check").start();
        }

        /** Загрузка кэша: прогресс в window.onCacheProgress, итог в window.onCacheDone({ok, error}). */
        @JavascriptInterface
        public void downloadCache(final String url) {
            if (running != null) return;
            final CacheSync s = new CacheSync(url, cacheRoot(MainActivity.this));
            running = s;
            new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        CacheSync.Plan p = s.check();
                        s.sync(p, new CacheSync.Listener() {
                            @Override
                            public void onProgress(long done, long total, int files, int totalFiles, long speed, String file) {
                                emit("onCacheProgress", obj("done", done, "total", total, "files", files,
                                        "totalFiles", totalFiles, "speed", speed, "file", file));
                            }
                        });
                        emit("onCacheDone", obj("ok", true));
                    } catch (Exception e) {
                        emit("onCacheDone", obj("ok", false, "error", message(e)));
                    } finally {
                        running = null;
                    }
                }
            }, "cache-download").start();
        }

        @JavascriptInterface
        public void cancelDownload() {
            CacheSync s = running;
            if (s != null) s.cancel();
        }

        /** Удаляет кэш сервера (кнопка «Проверить файлы» / «Очистить кэш»). */
        @JavascriptInterface
        public void clearCache(String url) {
            deleteTree(CacheSync.folderFor(cacheRoot(MainActivity.this), url));
        }

        @JavascriptInterface
        public void play(String url, String nick, String pass, String quality) {
            final Intent i = new Intent(MainActivity.this, GameActivity.class);
            i.putExtra("url", url);
            i.putExtra("nick", nick);
            i.putExtra("pass", pass);
            i.putExtra("quality", quality);
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    startActivity(i);
                }
            });
        }

        @JavascriptInterface
        public String version() {
            return BuildInfo.VERSION;
        }

        @JavascriptInterface
        public void open(final String url) {
            if (!url.startsWith("http://") && !url.startsWith("https://")) return;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    openExternal(url);
                }
            });
        }

        @JavascriptInterface
        public void exit() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    finish();
                }
            });
        }
    }
}
