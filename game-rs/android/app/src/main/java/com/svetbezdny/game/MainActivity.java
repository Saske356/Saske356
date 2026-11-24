package com.svetbezdny.game;

import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.util.Log;

import android.view.View;
import android.view.Surface;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowManager.LayoutParams;
import android.view.SurfaceView;
import android.view.SurfaceHolder;
import android.view.MotionEvent;
import android.view.KeyEvent;
import android.view.inputmethod.InputMethodManager;

import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.content.ClipData;
import android.content.ClipboardManager;

import android.graphics.Color;
import android.graphics.Insets;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.EditorInfo;
import android.widget.LinearLayout;

import quad_native.QuadNative;

// note: //% is a special miniquad's pre-processor for plugins
// when there are no plugins - //% whatever will be replaced to an empty string
// before compiling



class QuadSurface
    extends
        SurfaceView
    implements
        View.OnTouchListener,
        View.OnKeyListener,
        SurfaceHolder.Callback {

    public QuadSurface(Context context){
        super(context);
        getHolder().addCallback(this);

        setFocusable(true);
        setFocusableInTouchMode(true);
        requestFocus();
        setOnTouchListener(this);
        setOnKeyListener(this);
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        Log.i("SAPP", "surfaceCreated");
        Surface surface = holder.getSurface();
        QuadNative.surfaceOnSurfaceCreated(surface);
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        Log.i("SAPP", "surfaceDestroyed");
        Surface surface = holder.getSurface();
        QuadNative.surfaceOnSurfaceDestroyed(surface);
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder,
                               int format,
                               int width,
                               int height) {
        Log.i("SAPP", "surfaceChanged");
        Surface surface = holder.getSurface();
        QuadNative.surfaceOnSurfaceChanged(surface, width, height);

    }

    @Override
    public boolean onTouch(View v, MotionEvent event) {
        int pointerCount = event.getPointerCount();
        int action = event.getActionMasked();

        switch(action) {
        case MotionEvent.ACTION_MOVE: {
            for (int i = 0; i < pointerCount; i++) {
                final int id = event.getPointerId(i);
                final float x = event.getX(i);
                final float y = event.getY(i);
                QuadNative.surfaceOnTouch(id, 0, x, y);
            }
            break;
        }
        case MotionEvent.ACTION_UP: {
            final int id = event.getPointerId(0);
            final float x = event.getX(0);
            final float y = event.getY(0);
            QuadNative.surfaceOnTouch(id, 1, x, y);
            break;
        }
        case MotionEvent.ACTION_DOWN: {
            final int id = event.getPointerId(0);
            final float x = event.getX(0);
            final float y = event.getY(0);
            QuadNative.surfaceOnTouch(id, 2, x, y);
            break;
        }
        case MotionEvent.ACTION_POINTER_UP: {
            final int pointerIndex = event.getActionIndex();
            final int id = event.getPointerId(pointerIndex);
            final float x = event.getX(pointerIndex);
            final float y = event.getY(pointerIndex);
            QuadNative.surfaceOnTouch(id, 1, x, y);
            break;
        }
        case MotionEvent.ACTION_POINTER_DOWN: {
            final int pointerIndex = event.getActionIndex();
            final int id = event.getPointerId(pointerIndex);
            final float x = event.getX(pointerIndex);
            final float y = event.getY(pointerIndex);
            QuadNative.surfaceOnTouch(id, 2, x, y);
            break;
        }
        case MotionEvent.ACTION_CANCEL: {
            for (int i = 0; i < pointerCount; i++) {
                final int id = event.getPointerId(i);
                final float x = event.getX(i);
                final float y = event.getY(i);
                QuadNative.surfaceOnTouch(id, 3, x, y);
            }
            break;
        }
        default:
            break;
        }

        return true;
    }

    // docs says getCharacters are deprecated
    // but somehow on non-latyn input all keyCode and all the relevant fields in the KeyEvent are zeros
    // and only getCharacters has some usefull data
    @SuppressWarnings("deprecation")
    @Override
    public boolean onKey(View v, int keyCode, KeyEvent event) {
        // кнопки громкости — системе (раньше игра их «съедала», и звук нельзя было убавить)
        if (keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN || keyCode == KeyEvent.KEYCODE_VOLUME_MUTE) return false;
        if (event.getAction() == KeyEvent.ACTION_DOWN && keyCode != 0) {
            QuadNative.surfaceOnKeyDown(keyCode);
        }

        if (event.getAction() == KeyEvent.ACTION_UP && keyCode != 0) {
            QuadNative.surfaceOnKeyUp(keyCode);
        }

        if (event.getAction() == KeyEvent.ACTION_UP || event.getAction() == KeyEvent.ACTION_MULTIPLE) {
            int character = event.getUnicodeChar();
            if (character == 0) {
                String characters = event.getCharacters();
                if (characters != null && !characters.isEmpty()) {
                    character = characters.charAt(0);
                }
            }

            if (character != 0) {
                QuadNative.surfaceOnCharacter(character);
            }
        }

        return true;
    }

    // There is an Android bug when screen is in landscape,
    // the keyboard inset height is reported as 0.
    // This code is a workaround which fixes the bug.
    // See https://groups.google.com/g/android-developers/c/50XcWooqk7I
    // For some reason it only works if placed here and not in the parent layout.
    @Override
    public InputConnection onCreateInputConnection(EditorInfo outAttrs) {


        InputConnection connection = super.onCreateInputConnection(outAttrs);
        outAttrs.imeOptions |= EditorInfo.IME_FLAG_NO_FULLSCREEN;
        return connection;
    }

    public Surface getNativeSurface() {
        return getHolder().getSurface();
    }
}

class ResizingLayout
    extends
        LinearLayout
    implements
        View.OnApplyWindowInsetsListener {


    public ResizingLayout(MainActivity activity){
        super(activity);
        // When viewing in landscape mode with keyboard shown, there are
        // gaps on both sides so we fill the negative space with black.
        setBackgroundColor(Color.BLACK);
        setOnApplyWindowInsetsListener(this);


    }

    @Override
    public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
        // This handler provides a default impl which resizes content when the
        // IME is shown or hidden.
        //
        // However this will lead to flickers in your app as the content is
        // resized before you have a chance to redraw it.
        //
        // The workaround for now is:
        // * Get IME and system insets and send them to your app.
        // * Notify your app to draw and apply the insets to fit.
        // * Disable this function by returning early.



        if (Build.VERSION.SDK_INT >= 28) {
            android.view.DisplayCutout dc = insets.getDisplayCutout();
            if (dc != null) MainActivity.INSETS = dc.getSafeInsetTop() + "," + dc.getSafeInsetBottom() + "," + dc.getSafeInsetLeft() + "," + dc.getSafeInsetRight();
        }
        if (Build.VERSION.SDK_INT >= 30) {
            Insets imeInsets = insets.getInsets(WindowInsets.Type.ime());
            Insets sysInsets = insets.getInsets(WindowInsets.Type.systemBars());

            // When IME is visible then we dont need bottom inset
            int bottomPadding = sysInsets.bottom;
            if (imeInsets.bottom > 0) {
                bottomPadding = imeInsets.bottom;
            }

            // The sys insets change when orientation changes and sys bars
            // change position.
            v.setPadding(
                sysInsets.left,
                sysInsets.top,
                sysInsets.right,
                bottomPadding
            );
        }
        return insets;
    }
}

public class MainActivity extends Activity {

    // ===== Мост для Rust (вызывается из нативного кода через JNI по объекту активности) =====
    private RewardedAds ads;
    private BannerAds banner;
    /** Баннер внизу (только в меню) */
    public void setBanner(boolean on) { try { if (banner != null) banner.show(on); } catch (Throwable t) {} }
    public float bannerHeight() { try { return banner != null ? banner.height() : 0; } catch (Throwable t) { return 0; } }
    private InterstitialAds inter;
    private static final java.util.concurrent.ConcurrentLinkedQueue<String> AD_RESULTS = new java.util.concurrent.ConcurrentLinkedQueue<>();
    /** Итог показа рекламы: «место:1» или «место:0». Rust забирает через adPoll(). */
    static void pushAd(String place, boolean ok) { AD_RESULTS.add(place + ":" + (ok ? 1 : 0)); }
    public String adPoll() { String r = AD_RESULTS.poll(); return r == null ? "" : r; }
    public boolean adReady(int kind) { try { return kind == 0 ? ads != null && ads.isReady() : inter != null && inter.isReady(); } catch (Throwable t) { return false; } }
    public void adShow(int kind, String place) { try { if (kind == 0) ads.show(place); else inter.show(); } catch (Throwable t) { pushAd(kind == 0 ? place : "inter", false); } }
    public String filesDir() { return getFilesDir().getAbsolutePath(); }
    public void vibrate(int ms) {
        try { android.os.Vibrator v = (android.os.Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null) return;
            if (Build.VERSION.SDK_INT >= 26) v.vibrate(android.os.VibrationEffect.createOneShot(ms, android.os.VibrationEffect.DEFAULT_AMPLITUDE)); else v.vibrate(ms);
        } catch (Throwable t) { }
    }

    // ----- музыка: MediaPlayer играет OGG из assets потоково (мало памяти), команды из Rust -----
    private static final String[] TRACKS = {"menu", "zone1", "zone2", "zone3", "zone4", "boss1", "boss2", "boss3", "gameover", "victory"};
    private final android.media.MediaPlayer[] mp = new android.media.MediaPlayer[TRACKS.length];
    private final android.os.Handler ui = new android.os.Handler(android.os.Looper.getMainLooper());
    private static final java.util.concurrent.ConcurrentLinkedQueue<String> EVENTS = new java.util.concurrent.ConcurrentLinkedQueue<>();
    private volatile boolean paused = false;
    /** op: 1 — запустить с громкостью v, 0 — сменить громкость, -1 — остановить и освободить */
    public void musicCmd(final int i, final int op, final float v) {
        ui.post(() -> {
            try {
                if (i < 0 || i >= TRACKS.length) return;
                if (op == 1) {
                    if (mp[i] == null) {
                        android.content.res.AssetFileDescriptor fd = getAssets().openFd("audio/" + TRACKS[i] + ".ogg");
                        android.media.MediaPlayer m = new android.media.MediaPlayer();
                        m.setDataSource(fd.getFileDescriptor(), fd.getStartOffset(), fd.getLength()); fd.close();
                        m.setLooping(i < 8); m.prepare();
                        m.setOnCompletionListener(x -> EVENTS.add("music:" + i));
                        mp[i] = m;
                    }
                    mp[i].setVolume(v, v); mp[i].seekTo(0); if (!paused) mp[i].start();
                } else if (op == 0) { if (mp[i] != null) mp[i].setVolume(v, v); }
                else { if (mp[i] != null) { mp[i].stop(); mp[i].release(); mp[i] = null; } }
            } catch (Throwable t) { Log.w("SvetMusic", "music " + i, t); }
        });
    }
    public String eventPoll() { String r = EVENTS.poll(); return r == null ? "" : r; }
    public boolean isPaused() { return paused; }
    /** 0 — вертикально, 1 — горизонтально, 2 — как держишь телефон */
    public void setOrient(final int o) {
        runOnUiThread(() -> setRequestedOrientation(o == 1 ? android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            : o == 2 ? android.content.pm.ActivityInfo.SCREEN_ORIENTATION_FULL_USER : android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT));
    }
    public float density() { try { return getResources().getDisplayMetrics().density; } catch (Throwable t) { return 2.5f; } }
    /** Частота кадров: 60 — экономия батареи, иначе максимум экрана */
    public void setFps(final int fps) {
        runOnUiThread(() -> { try {
            android.view.Display d = Build.VERSION.SDK_INT >= 30 ? getDisplay() : getWindowManager().getDefaultDisplay(); if (d == null) return;
            android.view.Display.Mode cur = d.getMode(), best = null;
            for (android.view.Display.Mode m : d.getSupportedModes()) { if (m.getPhysicalWidth() != cur.getPhysicalWidth() || m.getPhysicalHeight() != cur.getPhysicalHeight()) continue;
                if (best == null) best = m;
                else if (fps == 60 ? Math.abs(m.getRefreshRate() - 60) < Math.abs(best.getRefreshRate() - 60) : m.getRefreshRate() > best.getRefreshRate()) best = m; }
            if (best == null) return;
            LayoutParams lp = getWindow().getAttributes(); lp.preferredDisplayModeId = best.getModeId(); lp.preferredRefreshRate = best.getRefreshRate(); getWindow().setAttributes(lp);
        } catch (Throwable t) { } });
    }
    public void quit() { runOnUiThread(this::finish); }
    /** Отступы под вырез камеры и системные полосы: "сверху,снизу,слева,справа" в пикселях */
    static volatile String INSETS = "0,0,0,0";
    public String insets() { return INSETS; }

    // ----- перенос сохранения из прежней версии (HTML в WebView): localStorage того же file:// -----
    private android.webkit.WebView mig;
    public void migrate() {
        runOnUiThread(() -> {
            try {
                mig = new android.webkit.WebView(this);
                android.webkit.WebSettings ws = mig.getSettings(); ws.setJavaScriptEnabled(true); ws.setDomStorageEnabled(true); ws.setAllowFileAccess(true);
                mig.addJavascriptInterface(new Object() {
                    @android.webkit.JavascriptInterface public void done(String json) {
                        EVENTS.add("save:" + (json == null ? "" : json));
                        ui.post(() -> { try { if (mig != null) { mig.destroy(); mig = null; } } catch (Throwable t) { } });
                    }
                }, "Mig");
                mig.loadUrl("file:///android_asset/migrate.html");
            } catch (Throwable t) { EVENTS.add("save:"); }
        });
    }
    /** Максимальная частота экрана (90/120 Гц), без смены разрешения */
    private void requestMaxRefreshRate() {
        try { android.view.Display d = Build.VERSION.SDK_INT >= 30 ? getDisplay() : getWindowManager().getDefaultDisplay(); if (d == null) return;
            android.view.Display.Mode cur = d.getMode(), best = cur;
            for (android.view.Display.Mode m : d.getSupportedModes()) if (m.getPhysicalWidth() == cur.getPhysicalWidth() && m.getPhysicalHeight() == cur.getPhysicalHeight() && m.getRefreshRate() > best.getRefreshRate()) best = m;
            LayoutParams lp = getWindow().getAttributes(); lp.preferredDisplayModeId = best.getModeId(); lp.preferredRefreshRate = best.getRefreshRate(); getWindow().setAttributes(lp);
        } catch (Throwable t) { }
    }


    private QuadSurface view;

    static {
        System.loadLibrary("svet");
    }

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        this.requestWindowFeature(Window.FEATURE_NO_TITLE);

        view = new QuadSurface(this);
        // Put it inside a parent layout which can resize it using padding
        ResizingLayout layout = new ResizingLayout(this);
        layout.addView(view);
        setContentView(layout);

        QuadNative.activityOnCreate(this);
        setVolumeControlStream(android.media.AudioManager.STREAM_MUSIC); // кнопки громкости управляют звуком игры
        getWindow().addFlags(LayoutParams.FLAG_KEEP_SCREEN_ON);
        requestMaxRefreshRate();
        setFullScreen(true);
        try { ads = new RewardedAds(this); inter = new InterstitialAds(this); } catch (Throwable t) { Log.w("SvetAds", "ads init failed", t); }
        try { banner = new BannerAds(this); } catch (Throwable t) { Log.w("SvetAds", "banner init failed", t); }


    }

    @Override
    protected void onResume() {
        super.onResume();
        QuadNative.activityOnResume();
        paused = false; setFullScreen(true);
        ui.post(() -> { for (android.media.MediaPlayer m : mp) if (m != null) try { m.start(); } catch (Throwable t) { } });


    }

    @Override
    public void onBackPressed() {
        Log.w("SAPP", "onBackPressed");

        // TODO: here is the place to handle request_quit/order_quit/cancel_quit

        super.onBackPressed();
    }

    @Override
    protected void onStop() {
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();

        QuadNative.activityOnDestroy();
        if (ads != null) ads.destroy(); if (inter != null) inter.destroy();
        for (int i = 0; i < mp.length; i++) if (mp[i] != null) { try { mp[i].release(); } catch (Throwable t) { } mp[i] = null; }
    }

    @Override
    protected void onPause() {
        super.onPause();
        QuadNative.activityOnPause();
        paused = true;
        ui.post(() -> { for (android.media.MediaPlayer m : mp) if (m != null) try { if (m.isPlaying()) m.pause(); } catch (Throwable t) { } });


    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {

    }

    public void setFullScreen(final boolean fullscreen) {
        runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    View decorView = getWindow().getDecorView();

                    if (fullscreen) {
                        getWindow().setFlags(LayoutParams.FLAG_LAYOUT_NO_LIMITS, LayoutParams.FLAG_LAYOUT_NO_LIMITS);
                        if (Build.VERSION.SDK_INT >= 28) {
                            getWindow().getAttributes().layoutInDisplayCutoutMode = LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
                        }
                        if (Build.VERSION.SDK_INT >= 30) {
                            getWindow().setDecorFitsSystemWindows(false);
                            android.view.WindowInsetsController c = getWindow().getInsetsController();
                            if (c != null) { c.hide(WindowInsets.Type.systemBars()); c.setSystemBarsBehavior(android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE); }
                        } else {
                            int uiOptions = View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY;
                            decorView.setSystemUiVisibility(uiOptions);
                        }
                    }
                    else {
                        if (Build.VERSION.SDK_INT >= 30) {
                            getWindow().setDecorFitsSystemWindows(true);
                        } else {
                          decorView.setSystemUiVisibility(0);
                        }

                    }
                }
            });
    }

    public void showKeyboard(final boolean show) {
        runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (show) {
                        InputMethodManager imm = (InputMethodManager)getSystemService(Context.INPUT_METHOD_SERVICE);
                        imm.showSoftInput(view, 0);
                    } else {
                        InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
                        imm.hideSoftInputFromWindow(view.getWindowToken(),0);
                    }
                }
            });
    }

    public String getClipboardText() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);

        if (!clipboard.hasPrimaryClip())
            return null;

        ClipData primaryClip = clipboard.getPrimaryClip();
        if (primaryClip == null || primaryClip.getItemCount() < 1)
            return null;

        CharSequence clipData = clipboard.getPrimaryClip().getItemAt(0).getText();
        if (clipData == null) {
            return null;
        }

        return clipData.toString();
    }
    public void setClipboardText(String text) {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        ClipData clip = ClipData.newPlainText("label", text);
        clipboard.setPrimaryClip(clip);
    }
}

