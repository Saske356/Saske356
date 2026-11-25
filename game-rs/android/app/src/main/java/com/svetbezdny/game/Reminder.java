package com.svetbezdny.game;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/** Локальные напоминания (без интернета и без серверов): игра сама ставит будильники AlarmManager,
 *  по сигналу этот приёмник показывает уведомление. Тап по уведомлению открывает игру. */
public class Reminder extends BroadcastReceiver {
    static final String CH = "svet_remind";
    static final int MAX = 4;

    @Override
    public void onReceive(Context c, Intent i) {
        try {
            NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CH) == null)
                nm.createNotificationChannel(new NotificationChannel(CH, i.getStringExtra("ch") != null ? i.getStringExtra("ch") : "Напоминания", NotificationManager.IMPORTANCE_DEFAULT));
            Intent open = new Intent(c, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent pi = PendingIntent.getActivity(c, 0, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH) : new Notification.Builder(c);
            b.setSmallIcon(R.drawable.ic_notify).setContentTitle(i.getStringExtra("t")).setContentText(i.getStringExtra("x"))
             .setStyle(new Notification.BigTextStyle().bigText(i.getStringExtra("x"))).setAutoCancel(true).setContentIntent(pi);
            nm.notify(i.getIntExtra("id", 0), b.build());
        } catch (Throwable t) { }
    }

    static PendingIntent pi(Context c, int id, Intent i) {
        return PendingIntent.getBroadcast(c, 100 + id, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** plan: строки «unixСекунды|заголовок|текст» через \n; прежние будильники снимаются. Пустой план — всё выключить. */
    static void schedule(Context c, String plan, String chName) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        for (int k = 0; k < MAX; k++) am.cancel(pi(c, k, new Intent(c, Reminder.class)));
        if (plan == null || plan.isEmpty()) return;
        String[] rows = plan.split("\n");
        for (int k = 0; k < rows.length && k < MAX; k++) {
            String[] f = rows[k].split("\\|", 3);
            if (f.length < 3) continue;
            long at;
            try { at = Long.parseLong(f[0]) * 1000L; } catch (Exception e) { continue; }
            if (at <= System.currentTimeMillis()) continue;
            Intent i = new Intent(c, Reminder.class).putExtra("id", 7000 + k).putExtra("t", f[1]).putExtra("x", f[2]).putExtra("ch", chName);
            am.set(AlarmManager.RTC, at, pi(c, k, i)); // неточный будильник: разрешения не нужны, батарею не тратит
        }
    }
}
