package com.svetbezdny.game;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import com.yandex.mobile.ads.appopenad.AppOpenAd;
import com.yandex.mobile.ads.appopenad.AppOpenAdEventListener;
import com.yandex.mobile.ads.appopenad.AppOpenAdLoadListener;
import com.yandex.mobile.ads.appopenad.AppOpenAdLoader;
import com.yandex.mobile.ads.common.AdError;
import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;

/**
 * Реклама при открытии — только при холодном запуске, пока игра и так грузится.
 * Чтобы не раздражать: не в первые сутки после установки, не чаще раза в 4 часа,
 * не при возврате из свёрнутого состояния, и только если реклама успела загрузиться за 6 с
 * (опоздала — не показываем, игрок уже играет).
 */
public class AppOpenAds {
    private static final String TAG = "SvetAppOpen";
    private static final long DAY = 24L * 3600_000L, GAP = 4L * 3600_000L, WAIT = 6_000L;
    private final Activity activity;
    private final SharedPreferences prefs;
    private final long started = System.currentTimeMillis();
    private boolean done = false;

    public AppOpenAds(Activity activity) {
        this.activity = activity;
        prefs = activity.getSharedPreferences("svet_ads", Activity.MODE_PRIVATE);
        long now = System.currentTimeMillis();
        if (prefs.getLong("first", 0) == 0) prefs.edit().putLong("first", now).apply();
        if (now - prefs.getLong("first", now) < DAY) { done = true; return; }
        if (now - prefs.getLong("appopen_last", 0) < GAP) { done = true; return; }
        try {
            AppOpenAdLoader loader = new AppOpenAdLoader(activity);
            loader.loadAd(new AdRequest.Builder(BuildConfig.YANDEX_APPOPEN_ID).build(), new AppOpenAdLoadListener() {
                @Override public void onAdLoaded(AppOpenAd ad) { show(ad); }
                @Override public void onAdFailedToLoad(AdRequestError e) { done = true; Log.w(TAG, "load failed: " + e.getDescription()); }
            });
            new Handler(Looper.getMainLooper()).postDelayed(() -> done = true, WAIT); // не успела — не показываем
        } catch (Throwable t) { done = true; Log.w(TAG, "init failed", t); }
    }

    private void show(AppOpenAd ad) {
        activity.runOnUiThread(() -> {
            if (done || System.currentTimeMillis() - started > WAIT || activity.isFinishing()) { done = true; return; }
            done = true;
            ad.setAdEventListener(new AppOpenAdEventListener() {
                @Override public void onAdShown() { prefs.edit().putLong("appopen_last", System.currentTimeMillis()).apply(); }
                @Override public void onAdFailedToShow(AdError e) {}
                @Override public void onAdDismissed() {}
                @Override public void onAdClicked() {}
                @Override public void onAdImpression(ImpressionData d) {}
            });
            try { ad.show(activity); } catch (Throwable t) { Log.w(TAG, "show failed", t); }
        });
    }
}
