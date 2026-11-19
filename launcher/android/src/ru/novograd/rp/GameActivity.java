package ru.novograd.rp;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.os.Bundle;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import org.json.JSONObject;

/** Игра на весь экран. После загрузки страницы выполняет автовход с данными из лаунчера. */
public class GameActivity extends Activity {
    private WebView web;
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

        web = Screen.webView(this);
        web.setWebViewClient(new WebViewClient() {
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
        String sep = url.contains("?") ? "&" : "?";
        web.loadUrl(url + sep + "launcher=android&q=" + (quality == null ? "mid" : quality));
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
