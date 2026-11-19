package ru.novograd.rp;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.os.Bundle;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.net.Uri;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.Map;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;

/** Игра на весь экран. После загрузки страницы выполняет автовход с данными из лаунчера. */
public class GameActivity extends Activity {
    /** Игра грузится с этого адреса; файлы подставляются из кэша, в сеть запросы не уходят. */
    static final String HOST = "game.local";
    private static final Map<String, String> MIME = new HashMap<>();
    static {
        MIME.put("html", "text/html"); MIME.put("js", "text/javascript"); MIME.put("mjs", "text/javascript");
        MIME.put("css", "text/css"); MIME.put("json", "application/json"); MIME.put("png", "image/png");
        MIME.put("jpg", "image/jpeg"); MIME.put("webp", "image/webp"); MIME.put("svg", "image/svg+xml");
        MIME.put("glb", "model/gltf-binary"); MIME.put("gltf", "model/gltf+json"); MIME.put("bin", "application/octet-stream");
        MIME.put("ogg", "audio/ogg"); MIME.put("mp3", "audio/mpeg"); MIME.put("wasm", "application/wasm"); MIME.put("txt", "text/plain");
    }
    private WebView web;
    private File cacheDir;
    private boolean failed;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Screen.immersive(this);
        final String url = getIntent().getStringExtra("url");
        final String nick = getIntent().getStringExtra("nick");
        final String pass = getIntent().getStringExtra("pass");
        String quality = getIntent().getStringExtra("quality");
        if (url == null) { finish(); return; }

        cacheDir = CacheSync.folderFor(MainActivity.cacheRoot(this), url);
        web = Screen.webView(this);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                return serve(u.getPath());
            }

            @Override
            public void onPageFinished(WebView v, String u) {
                if (failed) return;
                v.evaluateJavascript("window.__autoLogin && window.__autoLogin("
                        + JSONObject.quote(nick == null ? "" : nick) + ","
                        + JSONObject.quote(pass == null ? "" : pass) + ")", null);
            }

            @Override
            public void onReceivedError(final WebView v, WebResourceRequest r, WebResourceError e) {
                if (!r.isForMainFrame()) return;
                failed = true;
                new AlertDialog.Builder(GameActivity.this)
                        .setTitle("Нет связи с сервером")
                        .setMessage("Не удалось открыть " + url + "\n" + e.getDescription())
                        .setCancelable(false)
                        .setPositiveButton("Повторить", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                failed = false;
                                v.reload();
                            }
                        })
                        .setNegativeButton("В лаунчер", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                finish();
                            }
                        })
                        .show();
            }
        });
        setContentView(web);
        String q = quality == null ? "mid" : quality;
        try {
            if (new File(cacheDir, "index.html").isFile()) {
                web.loadUrl("http://" + HOST + "/index.html?launcher=android&q=" + q
                        + "&server=" + URLEncoder.encode(url, "UTF-8"));
            } else { // кэша нет (не должен случаться) — грузим игру с сервера
                web.loadUrl(url + "/?launcher=android&q=" + q);
            }
        } catch (java.io.UnsupportedEncodingException e) {
            finish();
        }
    }

    private WebResourceResponse serve(String path) {
        if (path == null || path.equals("/")) path = "/index.html";
        WebResourceResponse res;
        File f = new File(cacheDir, path.substring(1));
        try {
            if (!CacheSync.safePath(path) || !f.getCanonicalPath().startsWith(cacheDir.getCanonicalPath() + File.separator) || !f.isFile()) {
                res = new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", null, null);
                return res;
            }
            String ext = path.substring(path.lastIndexOf('.') + 1).toLowerCase(java.util.Locale.ROOT);
            String mime = MIME.containsKey(ext) ? MIME.get(ext) : "application/octet-stream";
            boolean text = mime.startsWith("text/") || mime.endsWith("json");
            return new WebResourceResponse(mime, text ? "utf-8" : null, new FileInputStream(f));
        } catch (IOException e) {
            return new WebResourceResponse("text/plain", "utf-8", 500, "Error", null, null);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) Screen.immersive(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) web.onResume();
    }

    @Override
    protected void onPause() {
        if (web != null) web.onPause();
        super.onPause();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        new AlertDialog.Builder(this)
                .setTitle("Выйти из игры?")
                .setMessage("Персонаж покинет сервер, прогресс сохранится.")
                .setPositiveButton("Выйти", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        finish();
                    }
                })
                .setNegativeButton("Остаться", null)
                .show();
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.loadUrl("about:blank");
            web.destroy();
        }
        super.onDestroy();
    }
}
