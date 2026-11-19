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

/** Лаунчер: интерфейс из assets/launcher, мост в Java через объект NovogradApp. */
public class MainActivity extends Activity {
    private WebView web;

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

    private void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) {
        }
    }

    private class Bridge {
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
