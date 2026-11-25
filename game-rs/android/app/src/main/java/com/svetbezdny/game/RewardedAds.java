package com.svetbezdny.game;

import android.app.Activity;
import android.util.Log;
import android.os.Handler;
import android.os.Looper;

import com.yandex.mobile.ads.common.AdError;
import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;
import com.yandex.mobile.ads.common.YandexAds;
import com.yandex.mobile.ads.rewarded.Reward;
import com.yandex.mobile.ads.rewarded.RewardedAd;
import com.yandex.mobile.ads.rewarded.RewardedAdEventListener;
import com.yandex.mobile.ads.rewarded.RewardedAdLoadListener;
import com.yandex.mobile.ads.rewarded.RewardedAdLoader;

/**
 * Вознаграждаемая реклама Яндекса для игры.
 * В JS доступен объект window.AndroidAds: isReady() и show(place).
 * Итог показа приходит в игру вызовом window.__adResult(place, ok).
 */
public class RewardedAds {
    private static final String TAG = "SvetAds";
    private static final long RETRY_MS = 30_000;

    private final Activity activity;
    private final Handler web = new Handler(Looper.getMainLooper()); // бывший WebView: только для отложенных задач
    private final RewardedAdLoader loader;
    private RewardedAdLoadListener listener;
    private volatile RewardedAd ad;
    private volatile boolean showing = false;
    private volatile boolean rewarded = false;
    private volatile boolean reported = true;
    private String place = "";

    public RewardedAds(Activity activity) {
        this.activity = activity;
        YandexAds.initialize(activity, () -> Log.d(TAG, "Yandex Mobile Ads ready"));
        loader = new RewardedAdLoader(activity);
        listener = new RewardedAdLoadListener() {
            @Override public void onAdLoaded(RewardedAd loaded) { ad = loaded; }
            @Override public void onAdFailedToLoad(AdRequestError error) {
                Log.w(TAG, "load failed: " + error.getDescription());
                web.postDelayed(RewardedAds.this::load, RETRY_MS);
            }
        };
        load();
    }

    private void load() {
        if (ad != null) return;
        loader.loadAd(new AdRequest.Builder(BuildConfig.YANDEX_REWARDED_ID).build(), listener);
    }

    public boolean isReady() { return ad != null && !showing; }

    public void show(String where) {
        activity.runOnUiThread(() -> {
            RewardedAd current = ad;
            if (current == null || showing) { result(where, false); return; }
            showing = true; rewarded = false; place = where;
            current.setAdEventListener(new RewardedAdEventListener() {
                @Override public void onAdShown() {}
                @Override public void onAdFailedToShow(AdError adError) { finish(); }
                @Override public void onAdDismissed() { finish(); }
                @Override public void onAdClicked() {}
                @Override public void onAdImpression(ImpressionData data) {}
                @Override public void onRewarded(Reward reward) { rewarded = true;
                    // награда пришла уже после закрытия — сообщаем игре отдельно
                    if (!showing && !reported) { reported = true; result(place, true); } }
            });
            try { current.show(activity); }
            catch (Throwable t) { Log.w(TAG, "show failed", t); showing = false; result(where, false); } // сбой показа — игра не должна ждать вечно
        });
    }

    /** Реклама закрыта. Яндекс иногда присылает onRewarded чуть позже onAdDismissed —
     *  поэтому итог отправляем через 600 мс (или сразу, если награда уже есть). */
    private void finish() {
        if (!showing) return;
        showing = false; reported = false;
        final RewardedAd old = ad;
        ad = null;
        Runnable done = () -> {
            if (!reported) { reported = true; result(place, rewarded); }
            if (old != null) old.setAdEventListener(null);
            load();
        };
        if (rewarded) done.run(); else web.postDelayed(done, 1500); // 4.8.4: награда бывает позже закрытия — ждём дольше
    }

    private void result(String where, boolean ok) {
        String safe = where == null ? "" : where.replaceAll("[^a-z0-9_]", ""); // 4.8.4: цифры были вырезаны — «pet2» приходил как «pet» и награда терялась
        MainActivity.pushAd(safe, ok);
    }

    public void destroy() {
        loader.cancelLoading();
        if (ad != null) ad.setAdEventListener(null);
        ad = null;
    }
}
