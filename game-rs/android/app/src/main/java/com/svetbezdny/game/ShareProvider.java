package com.svetbezdny.game;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;

/** Отдаёт другим приложениям только одну картинку — карточку рекорда (files/share/record.png), только на чтение. */
public class ShareProvider extends ContentProvider {
    static final String AUTH = "com.svetbezdny.game.share";
    File file() { return new File(new File(getContext().getFilesDir(), "share"), "record.png"); }
    @Override public boolean onCreate() { return true; }
    @Override public String getType(Uri u) { return "image/png"; }
    @Override public ParcelFileDescriptor openFile(Uri u, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("read only");
        return ParcelFileDescriptor.open(file(), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) {
        MatrixCursor c = new MatrixCursor(new String[] { OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE });
        File f = file(); c.addRow(new Object[] { "light-of-the-abyss.png", f.length() }); return c;
    }
    @Override public Uri insert(Uri u, ContentValues v) { return null; }
    @Override public int delete(Uri u, String s, String[] a) { return 0; }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }
}
