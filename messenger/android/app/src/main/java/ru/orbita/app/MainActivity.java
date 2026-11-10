package ru.orbita.app;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Insets;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * Орбита for Android: a thin native shell around the web client served by your Орбита server.
 * Encryption keys live in the WebView's IndexedDB on the device, exactly as in a browser.
 */
public class MainActivity extends Activity {
    private static final String SETUP = "file:///android_asset/setup.html";
    private static final int REQ_FILE = 1, REQ_MEDIA = 2, REQ_NOTIFY = 3;

    private WebView web;
    private FrameLayout root;
    private SharedPreferences prefs;
    private ValueCallback<Uri[]> fileCallback;
    private PermissionRequest pendingRequest;
    private String pendingOpen;
    private boolean darkUi;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        prefs = getSharedPreferences("orbita", MODE_PRIVATE);
        createChannels();

        root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        setupEdgeToEdge();
        setupWebView();

        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFY);
        }
        pendingOpen = getIntent().getStringExtra("open");
        if (saved != null) web.restoreState(saved);
        else loadHome();
    }

    // ---------------- layout ----------------
    private void setupEdgeToEdge() {
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        else root.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int l, t, r, b;
            if (Build.VERSION.SDK_INT >= 30) {
                Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime() | WindowInsets.Type.displayCutout());
                l = i.left; t = i.top; r = i.right; b = i.bottom;
            } else {
                l = insets.getSystemWindowInsetLeft(); t = insets.getSystemWindowInsetTop();
                r = insets.getSystemWindowInsetRight(); b = insets.getSystemWindowInsetBottom();
            }
            v.setPadding(l, t, r, b);
            return Build.VERSION.SDK_INT >= 30 ? WindowInsets.CONSUMED : insets.consumeSystemWindowInsets();
        });
        applyBars(false, Color.parseColor("#F4F1EA"));
    }

    private void applyBars(boolean dark, int color) {
        darkUi = dark;
        root.setBackgroundColor(color);
        getWindow().getDecorView().setBackgroundColor(color);
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(dark ? 0 : light, light);
            }
        } else {
            int f = root.getSystemUiVisibility();
            f = dark ? f & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
                     : f | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            root.setSystemUiVisibility(f);
        }
    }

    // ---------------- web view ----------------
    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setSupportZoom(false);
        s.setTextZoom(100);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setUserAgentString(s.getUserAgentString() + " OrbitaAndroid/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setBackgroundColor(Color.TRANSPARENT);
        web.addJavascriptInterface(new Bridge(), "OrbitaAndroid");
        setVolumeControlStream(AudioManager.STREAM_VOICE_CALL);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (isOwn(u.toString())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (ActivityNotFoundException ignored) { }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame() && !req.getUrl().toString().startsWith("file:")) {
                    view.loadUrl(SETUP + "#error=" + Uri.encode(server()) + "&msg=" + Uri.encode(String.valueOf(err.getDescription())));
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (pendingOpen != null && isOwn(url)) {
                    final String tag = pendingOpen;
                    pendingOpen = null;
                    view.postDelayed(() -> openTag(tag), 1500);
                }
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> handleMediaRequest(request));
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> cb, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                String[] types = params.getAcceptTypes();
                String type = types != null && types.length == 1 && !types[0].isEmpty() ? types[0] : "*/*";
                i.setType(type);
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try { startActivityForResult(Intent.createChooser(i, null), REQ_FILE); }
                catch (ActivityNotFoundException e) { fileCallback = null; return false; }
                return true;
            }
        });
    }

    private String server() {
        String s = prefs.getString("server", "");
        if (s.isEmpty() && !BuildConfig.SERVER_URL.isEmpty()) s = BuildConfig.SERVER_URL;
        return s;
    }

    private boolean isOwn(String url) {
        if (url.startsWith(SETUP)) return true;
        String s = server();
        if (s.isEmpty()) return false;
        Uri a = Uri.parse(url), b = Uri.parse(s);
        return a.getHost() != null && a.getHost().equalsIgnoreCase(b.getHost()) && a.getPort() == b.getPort()
            && String.valueOf(a.getScheme()).equalsIgnoreCase(b.getScheme());
    }

    private void loadHome() {
        String s = server();
        web.loadUrl(s.isEmpty() ? SETUP : s);
    }

    private void openTag(String tag) {
        web.evaluateJavascript("window.orbitaOpen && orbitaOpen(" + JSONObject.quote(tag) + ")", null);
    }

    // ---------------- camera / microphone for calls and voice notes ----------------
    private void handleMediaRequest(PermissionRequest request) {
        if (!isOwn(request.getOrigin().toString())) { request.deny(); return; }
        List<String> need = new ArrayList<>();
        for (String r : request.getResources()) {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r) && checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) need.add(Manifest.permission.CAMERA);
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r) && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) need.add(Manifest.permission.RECORD_AUDIO);
        }
        if (need.isEmpty()) { request.grant(request.getResources()); return; }
        if (pendingRequest != null) pendingRequest.deny();
        pendingRequest = request;
        requestPermissions(need.toArray(new String[0]), REQ_MEDIA);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (code != REQ_MEDIA || pendingRequest == null) return;
        List<String> granted = new ArrayList<>();
        for (String r : pendingRequest.getResources()) {
            if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r) && checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) granted.add(r);
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r) && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) granted.add(r);
        }
        if (granted.isEmpty()) pendingRequest.deny();
        else pendingRequest.grant(granted.toArray(new String[0]));
        pendingRequest = null;
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code != REQ_FILE || fileCallback == null) { super.onActivityResult(code, result, data); return; }
        Uri[] uris = null;
        if (result == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                uris = new Uri[n];
                for (int i = 0; i < n; i++) uris[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data.getData() != null) uris = new Uri[]{data.getData()};
        }
        fileCallback.onReceiveValue(uris);
        fileCallback = null;
    }

    // ---------------- lifecycle ----------------
    @Override
    protected void onStart() { super.onStart(); web.evaluateJavascript("window.orbitaVisible && orbitaVisible(true)", null); }

    @Override
    protected void onStop() { super.onStop(); web.evaluateJavascript("window.orbitaVisible && orbitaVisible(false)", null); }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        String tag = intent.getStringExtra("open");
        if (tag != null) openTag(tag);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        web.evaluateJavascript("window.orbitaBack ? orbitaBack() : false", v -> {
            if ("true".equals(v)) return;
            if (web.canGoBack() && !web.getUrl().startsWith(SETUP)) web.goBack();
            else moveTaskToBack(true);
        });
    }

    @Override
    protected void onDestroy() { web.destroy(); super.onDestroy(); }

    // ---------------- notifications ----------------
    private void createChannels() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel msg = new NotificationChannel("messages", getString(R.string.channel_messages), NotificationManager.IMPORTANCE_HIGH);
        NotificationChannel call = new NotificationChannel("calls", getString(R.string.channel_calls), NotificationManager.IMPORTANCE_HIGH);
        nm.createNotificationChannel(msg);
        nm.createNotificationChannel(call);
    }

    private void showNotification(String title, String body, String tag) {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return;
        Intent i = new Intent(this, MainActivity.class).putExtra("open", tag).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, tag.hashCode(), i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(this, "call".equals(tag) ? "calls" : "messages")
            .setSmallIcon(R.drawable.ic_notify)
            .setColor(Color.parseColor("#FF5F3A"))
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(new Notification.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setCategory("call".equals(tag) ? Notification.CATEGORY_CALL : Notification.CATEGORY_MESSAGE)
            .setContentIntent(pi)
            .build();
        getSystemService(NotificationManager.class).notify(tag, 1, n);
    }

    // ---------------- downloads ----------------
    private void saveDownload(byte[] data, String name, String mime) {
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                ContentValues v = new ContentValues();
                v.put(MediaStore.Downloads.DISPLAY_NAME, name);
                v.put(MediaStore.Downloads.MIME_TYPE, mime);
                v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Orbita");
                Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                if (uri == null) throw new Exception("no uri");
                try (OutputStream os = getContentResolver().openOutputStream(uri)) { os.write(data); }
                toast("Сохранено в «Загрузки/Orbita»");
            } else {
                File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                File f = new File(dir, name);
                try (FileOutputStream os = new FileOutputStream(f)) { os.write(data); }
                toast("Сохранено: " + f.getAbsolutePath());
            }
        } catch (Exception e) {
            toast("Не удалось сохранить файл");
        }
    }

    private void toast(String s) { runOnUiThread(() -> Toast.makeText(this, s, Toast.LENGTH_SHORT).show()); }

    // ---------------- JS bridge ----------------
    private final class Bridge {
        @JavascriptInterface
        public void notify(String title, String body, String tag) { showNotification(title, body, tag); }

        @JavascriptInterface
        public void saveFile(String base64, String name, String mime) {
            byte[] data = Base64.decode(base64, Base64.DEFAULT);
            String safe = name.replaceAll("[\\\\/:*?\"<>|]", "_");
            saveDownload(data, safe.isEmpty() ? "file" : safe, mime);
        }

        @JavascriptInterface
        public void setTheme(String mode, String color) {
            runOnUiThread(() -> { try { applyBars("dark".equals(mode), Color.parseColor(color)); } catch (IllegalArgumentException ignored) { } });
        }

        @JavascriptInterface
        public void setServer(String url) {
            runOnUiThread(() -> {
                if (!web.getUrl().startsWith(SETUP)) return; // only the local setup page may change the server
                String u = url.trim().replaceAll("/+$", "");
                if (!u.matches("(?i)^https?://.+")) u = "https://" + u;
                prefs.edit().putString("server", u).apply();
                web.clearHistory();
                web.loadUrl(u);
            });
        }

        @JavascriptInterface
        public void retry() { runOnUiThread(MainActivity.this::loadHome); }

        @JavascriptInterface
        public void resetServer() {
            runOnUiThread(() -> {
                prefs.edit().remove("server").apply();
                web.loadUrl(SETUP + "#change=" + Uri.encode(server()));
            });
        }

        @JavascriptInterface
        public String currentServer() { return server(); }

        @JavascriptInterface
        public void vibrate() { /* reserved */ }
    }
}
