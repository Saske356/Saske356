package com.svetbezdny.game;

import android.app.Activity;
import android.util.Log;
import android.os.Handler;
import android.os.Looper;

import com.yandex.mobile.ads.common.AdError;
import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;
import com.yandex.mobile.ads.interstitial.InterstitialAd;
import com.yandex.mobile.ads.interstitial.InterstitialAdEventListener;
import com.yandex.mobile.ads.interstitial.InterstitialAdLoadListener;
import com.yandex.mobile.ads.interstitial.InterstitialAdLoader;

/**
 * Межстраничная реклама Яндекса (между забегами).
 * В JS доступен объект window.AndroidInter: isReady() и show().
 * Как часто её показывать, решает игра (не чаще раза в несколько минут).
 * Когда реклама закрыта, игра получает window.__adResult('inter', true/false).
 */
public class InterstitialAds {
    private static final String TAG = "SvetInter";
    private static final long RETRY_MS = 30_000;

    private final Activity activity;
    private final Handler web = new Handler(Looper.getMainLooper()); // бывший WebView: только для отложенных задач
    private final InterstitialAdLoader loader;
    private InterstitialAdLoadListener listener;
    private volatile InterstitialAd ad;
    private volatile boolean showing = false;
    private boolean shown = false;

    public InterstitialAds(Activity activity) {
        this.activity = activity;
        loader = new InterstitialAdLoader(activity);
        listener = new InterstitialAdLoadListener() {
            @Override public void onAdLoaded(InterstitialAd loaded) { ad = loaded; }
            @Override public void onAdFailedToLoad(AdRequestError error) {
                Log.w(TAG, "load failed: " + error.getDescription());
                web.postDelayed(InterstitialAds.this::load, RETRY_MS);
            }
        };
        load();
    }

    private void load() {
        if (ad != null) return;
        loader.loadAd(new AdRequest.Builder(BuildConfig.YANDEX_INTERSTITIAL_ID).build(), listener);
    }

    public boolean isReady() { return ad != null && !showing; }

    public void show() {
        activity.runOnUiThread(() -> {
            InterstitialAd current = ad;
            if (current == null || showing) { result(false); return; }
            showing = true; shown = false;
            current.setAdEventListener(new InterstitialAdEventListener() {
                @Override public void onAdShown() { shown = true; }
                @Override public void onAdFailedToShow(AdError adError) { finish(); }
                @Override public void onAdDismissed() { finish(); }
                @Override public void onAdClicked() {}
                @Override public void onAdImpression(ImpressionData data) {}
            });
            try { current.show(activity); }
            catch (Throwable t) { Log.w(TAG, "show failed", t); showing = false; result(false); } // сбой показа — игра не должна ждать вечно
        });
    }

    private void finish() {
        if (!showing) return;
        showing = false;
        InterstitialAd old = ad;
        ad = null;
        if (old != null) old.setAdEventListener(null);
        result(shown);
        load();
    }

    private void result(boolean ok) {
        MainActivity.pushAd("inter", ok);
    }

    public void destroy() {
        loader.cancelLoading();
        if (ad != null) ad.setAdEventListener(null);
        ad = null;
    }
}
