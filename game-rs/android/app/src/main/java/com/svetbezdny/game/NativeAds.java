package com.svetbezdny.game;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;
import com.yandex.mobile.ads.nativeads.MediaView;
import com.yandex.mobile.ads.nativeads.NativeAd;
import com.yandex.mobile.ads.nativeads.NativeAdAssets;
import com.yandex.mobile.ads.nativeads.NativeAdEventListener;
import com.yandex.mobile.ads.nativeads.NativeAdLoadListener;
import com.yandex.mobile.ads.nativeads.NativeAdLoader;
import com.yandex.mobile.ads.nativeads.NativeAdView;
import com.yandex.mobile.ads.nativeads.NativeAdViewBinder;

/**
 * Нативная реклама — карточка в стиле игры на экране итогов забега (под кнопками).
 * Игра спрашивает ready(), оставляет под неё место и сообщает прямоугольник place(x, y, w, h) в пикселях;
 * hide() — убрать. После показа загружается следующее объявление.
 */
public class NativeAds {
    private static final String TAG = "SvetNative";
    private final Activity activity;
    private final Handler h = new Handler(Looper.getMainLooper());
    private NativeAdLoader loader;
    private volatile NativeAd ad;
    private volatile boolean shownThis = false;
    private NativeAdView card;
    private TextView title, body, cta, sponsored, age, domain, warning, price, reviews;
    private ImageView icon, favicon, feedback;
    private MediaView media;
    private int px = -1, py, pw, ph;

    public NativeAds(Activity a) { activity = a; a.runOnUiThread(this::create); }

    private int dp(float v) { return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, activity.getResources().getDisplayMetrics())); }
    private TextView tv(float sp, int col, boolean bold, int lines) {
        TextView t = new TextView(activity); t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp); t.setTextColor(col);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD); t.setMaxLines(lines); t.setEllipsize(TextUtils.TruncateAt.END); return t;
    }

    private void create() {
        try {
            loader = new NativeAdLoader(activity);
            card = new NativeAdView(activity);
            GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[] { 0xF00B2A46, 0xF0140A2E });
            bg.setCornerRadius(dp(16)); bg.setStroke(dp(1.5f), 0x995FE9FF); card.setBackground(bg); card.setPadding(dp(10), dp(6), dp(10), dp(6));
            LinearLayout col = new LinearLayout(activity); col.setOrientation(LinearLayout.VERTICAL);
            // верх: «Реклама» · возраст · жалоба
            LinearLayout top = new LinearLayout(activity); top.setGravity(Gravity.CENTER_VERTICAL);
            sponsored = tv(9, 0xFF9FDFFF, false, 1); top.addView(sponsored, new LinearLayout.LayoutParams(0, -2, 1));
            age = tv(9, 0xFF9FDFFF, false, 1); top.addView(age, new LinearLayout.LayoutParams(-2, -2));
            feedback = new ImageView(activity); LinearLayout.LayoutParams fl = new LinearLayout.LayoutParams(dp(16), dp(16)); fl.leftMargin = dp(6); top.addView(feedback, fl);
            col.addView(top);
            // середина: картинка + заголовок и текст
            LinearLayout mid = new LinearLayout(activity); mid.setGravity(Gravity.CENTER_VERTICAL);
            media = new MediaView(activity); LinearLayout.LayoutParams ml = new LinearLayout.LayoutParams(dp(84), dp(56)); ml.rightMargin = dp(8); mid.addView(media, ml);
            LinearLayout txt = new LinearLayout(activity); txt.setOrientation(LinearLayout.VERTICAL);
            LinearLayout tr = new LinearLayout(activity); tr.setGravity(Gravity.CENTER_VERTICAL);
            icon = new ImageView(activity); LinearLayout.LayoutParams il = new LinearLayout.LayoutParams(dp(20), dp(20)); il.rightMargin = dp(5); tr.addView(icon, il);
            title = tv(13, Color.WHITE, true, 1); tr.addView(title, new LinearLayout.LayoutParams(0, -2, 1)); txt.addView(tr);
            body = tv(11, 0xFFCFE6F5, false, 2); txt.addView(body);
            mid.addView(txt, new LinearLayout.LayoutParams(0, -2, 1));
            col.addView(mid, new LinearLayout.LayoutParams(-1, 0, 1));
            // низ: значок сайта, домен, цена, отзывы — кнопка
            LinearLayout bot = new LinearLayout(activity); bot.setGravity(Gravity.CENTER_VERTICAL);
            favicon = new ImageView(activity); LinearLayout.LayoutParams fv = new LinearLayout.LayoutParams(dp(12), dp(12)); fv.rightMargin = dp(4); bot.addView(favicon, fv);
            domain = tv(10, 0xFF9FDFFF, false, 1); bot.addView(domain, new LinearLayout.LayoutParams(0, -2, 1));
            price = tv(10, 0xFFFFE08A, true, 1); bot.addView(price, new LinearLayout.LayoutParams(-2, -2));
            reviews = tv(9, 0xFF9FDFFF, false, 1); bot.addView(reviews, new LinearLayout.LayoutParams(-2, -2));
            cta = tv(12, 0xFF2A1800, true, 1); cta.setGravity(Gravity.CENTER); cta.setPadding(dp(12), dp(4), dp(12), dp(4));
            GradientDrawable cb = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, new int[] { 0xFFFFE08A, 0xFFE0A63A }); cb.setCornerRadius(dp(12)); cta.setBackground(cb);
            LinearLayout.LayoutParams cl = new LinearLayout.LayoutParams(-2, -2); cl.leftMargin = dp(6); bot.addView(cta, cl);
            col.addView(bot);
            warning = tv(8, 0xFFA0B4C8, false, 2); col.addView(warning);
            card.addView(col, new FrameLayout.LayoutParams(-1, -1));
            card.setVisibility(View.GONE);
            activity.addContentView(card, new FrameLayout.LayoutParams(dp(300), dp(120), Gravity.TOP | Gravity.START));
            load();
        } catch (Throwable t) { Log.w(TAG, "init failed", t); card = null; }
    }

    private void load() {
        if (loader == null || ad != null) return;
        try {
            loader.loadAd(new AdRequest.Builder(BuildConfig.YANDEX_NATIVE_ID).build(), new NativeAdLoadListener() {
                @Override public void onAdLoaded(NativeAd a) { activity.runOnUiThread(() -> bind(a)); }
                @Override public void onAdFailedToLoad(AdRequestError e) { Log.w(TAG, "load failed: " + e.getDescription()); h.postDelayed(NativeAds.this::load, 45_000); }
            });
        } catch (Throwable t) { Log.w(TAG, "load failed", t); }
    }

    private static void vis(View v, boolean on) { v.setVisibility(on ? View.VISIBLE : View.GONE); }

    private void bind(NativeAd a) {
        try {
            NativeAdAssets as = a.getAdAssets();
            vis(media, as.getMedia() != null || as.getImage() != null); vis(icon, as.getIcon() != null); vis(favicon, as.getFavicon() != null);
            vis(price, as.getPrice() != null); vis(reviews, as.getReviewCount() != null); vis(feedback, as.isFeedbackAvailable()); vis(warning, as.getWarning() != null);
            vis(age, as.getAge() != null); vis(domain, as.getDomain() != null); vis(sponsored, as.getSponsored() != null); vis(body, as.getBody() != null);
            a.bindNativeAd(new NativeAdViewBinder.Builder(card).setTitleView(title).setBodyView(body).setCallToActionView(cta).setSponsoredView(sponsored)
                .setAgeView(age).setDomainView(domain).setWarningView(warning).setPriceView(price).setReviewCountView(reviews)
                .setIconView(icon).setFaviconView(favicon).setFeedbackView(feedback).setMediaView(media).build());
            a.setNativeAdEventListener(new NativeAdEventListener() {
                @Override public void onAdClicked() {}
                @Override public void onImpression(ImpressionData d) { shownThis = true; }
            });
            ad = a;
        } catch (Throwable t) { Log.w(TAG, "bind failed", t); ad = null; h.postDelayed(this::load, 45_000); }
    }

    public boolean ready() { return card != null && ad != null; }

    /** Поставить карточку в прямоугольник экрана (физические пиксели) */
    public void place(int x, int y, int w, int hh) {
        if (!ready()) return; if (x == px && y == py && w == pw && hh == ph && card.getVisibility() == View.VISIBLE) return;
        px = x; py = y; pw = w; ph = hh;
        activity.runOnUiThread(() -> { if (card == null) return; FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(pw, ph, Gravity.TOP | Gravity.START); lp.leftMargin = px; lp.topMargin = py;
            card.setLayoutParams(lp); card.setVisibility(View.VISIBLE); });
    }

    /** Убрать; если объявление уже показали — загрузить следующее */
    public void hide() {
        if (px < 0) return; px = -1;
        activity.runOnUiThread(() -> { if (card == null) return; card.setVisibility(View.GONE);
            if (shownThis) { shownThis = false; ad = null; load(); } });
    }
}
