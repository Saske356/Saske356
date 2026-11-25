package com.svetbezdny.game;

import android.app.Activity;
import android.content.res.Configuration;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;

import com.yandex.mobile.ads.banner.BannerAdEventListener;
import com.yandex.mobile.ads.banner.BannerAdSize;
import com.yandex.mobile.ads.banner.BannerAdView;
import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;

/**
 * Баннер Яндекса внизу экрана — только в меню (главный экран, магазин, задания…), в забеге скрыт.
 * Игра включает/выключает его через MainActivity.setBanner(boolean). Высоту в пикселях отдаёт height(),
 * чтобы игра подняла кнопки меню над баннером.
 */
public class BannerAds {
    private static final String TAG = "SvetBanner";
    private final Activity activity;
    private BannerAdView view;
    private volatile boolean loaded = false;
    private volatile boolean want = false;
    private volatile int heightPx = 0;

    public BannerAds(Activity activity) {
        this.activity = activity;
        activity.runOnUiThread(this::create);
    }

    private void create() {
        try {
            view = new BannerAdView(activity);
            float density = activity.getResources().getDisplayMetrics().density;
            // ширина — по короткой стороне экрана: в горизонтальном режиме баннер не растягивается на весь экран
            android.util.DisplayMetrics dm = activity.getResources().getDisplayMetrics();
            int widthDp = Math.round(Math.min(dm.widthPixels, dm.heightPixels) / density);
            BannerAdSize size = BannerAdSize.sticky(activity, widthDp);
            view.setAdSize(size);
            view.setBannerAdEventListener(new BannerAdEventListener() {
                @Override public void onAdLoaded() { loaded = true; heightPx = view.getHeight() > 0 ? view.getHeight() : size.getHeightInPixels(activity); apply(); }
                @Override public void onAdFailedToLoad(AdRequestError e) { loaded = false; Log.w(TAG, "load failed: " + e.getDescription()); apply(); }
                @Override public void onAdClicked() {}
                @Override public void onImpression(ImpressionData d) {}
            });
            activity.addContentView(view, params());
            // 4.6: высота — живая: после поворота баннер перестраивается (вертикально он выше), игра должна знать новую
            view.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> { int hh = b - t; if (hh > 0) heightPx = hh; });
            view.setVisibility(View.GONE);
            view.loadAd(new AdRequest.Builder(BuildConfig.YANDEX_BANNER_ID).build());
        } catch (Throwable t) { Log.w(TAG, "banner init failed", t); view = null; }
    }

    /** Вертикально — внизу по центру; горизонтально — внизу слева (под картинкой), чтобы не закрывать кнопки справа */
    private FrameLayout.LayoutParams params() {
        boolean land = activity.getResources().getConfiguration().orientation == Configuration.ORIENTATION_LANDSCAPE;
        return new FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.BOTTOM | (land ? Gravity.START : Gravity.CENTER_HORIZONTAL));
    }

    private void apply() {
        activity.runOnUiThread(() -> { if (view != null) { view.setLayoutParams(params()); view.setVisibility(want && loaded ? View.VISIBLE : View.GONE); } });
    }

    /** Поворот экрана: переставить баннер; пока он не перестроился — оставить запас по высоте (90 dp) */
    public void onConfig() { heightPx = Math.max(heightPx, Math.round(90 * activity.getResources().getDisplayMetrics().density)); apply(); }

    /** Горизонтально баннер слева — игре не нужно поднимать кнопки (0); вертикально — его высота */
    public boolean leftSide() { return activity.getResources().getConfiguration().orientation == Configuration.ORIENTATION_LANDSCAPE; }

    public void reapply() { apply(); }
    public void show(boolean on) { if (on == want) return; want = on; apply(); }

    /** Высота видимого баннера в физических пикселях (0 — не показан) */
    public int height() { return want && loaded ? heightPx : 0; }

    public void destroy() { try { if (view != null) view.destroy(); } catch (Throwable ignored) {} }
}
