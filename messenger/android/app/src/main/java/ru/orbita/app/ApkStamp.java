package ru.orbita.app;

import java.io.File;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

/**
 * Reads the server address that the Орбита server writes into the APK Signing Block
 * when it hands out the app (see server/apkstamp.js). Returns null if the APK has no stamp.
 */
final class ApkStamp {
    static final int STAMP_ID = 0x4f524254; // 'ORBT'
    private static final byte[] MAGIC = "APK Sig Block 42".getBytes(StandardCharsets.US_ASCII);

    static String read(File apk) {
        try (RandomAccessFile f = new RandomAccessFile(apk, "r")) {
            long len = f.length();
            int scan = (int) Math.min(len, 22 + 0xffff);
            byte[] tail = new byte[scan];
            f.seek(len - scan);
            f.readFully(tail);
            ByteBuffer t = ByteBuffer.wrap(tail).order(ByteOrder.LITTLE_ENDIAN);
            int eocd = -1;
            for (int i = scan - 22; i >= 0; i--) {
                if (t.getInt(i) == 0x06054b50 && i + 22 + (t.getShort(i + 20) & 0xffff) == scan) { eocd = i; break; }
            }
            if (eocd < 0) return null;
            long cd = t.getInt(eocd + 16) & 0xffffffffL;
            if (cd < 32) return null;
            byte[] foot = new byte[24];
            f.seek(cd - 24);
            f.readFully(foot);
            for (int i = 0; i < 16; i++) if (foot[8 + i] != MAGIC[i]) return null;
            long size = ByteBuffer.wrap(foot, 0, 8).order(ByteOrder.LITTLE_ENDIAN).getLong();
            if (size < 24 || size > 32 * 1024 * 1024) return null;
            byte[] block = new byte[(int) (size - 24)];
            f.seek(cd - size);
            f.readFully(block);
            ByteBuffer b = ByteBuffer.wrap(block).order(ByteOrder.LITTLE_ENDIAN);
            while (b.remaining() >= 12) {
                long pairLen = b.getLong();
                if (pairLen < 4 || pairLen > b.remaining()) return null;
                int id = b.getInt();
                int valueLen = (int) (pairLen - 4);
                if (id == STAMP_ID) {
                    byte[] v = new byte[valueLen];
                    b.get(v);
                    String s = new String(v, StandardCharsets.UTF_8).trim();
                    return s.matches("(?i)^https?://[^\\s]+$") ? s : null;
                }
                b.position(b.position() + valueLen);
            }
        } catch (Exception ignored) { }
        return null;
    }

    // Lets the parser be checked on a desktop JVM: java ApkStamp.java app.apk
    public static void main(String[] args) { System.out.println(read(new File(args[0]))); }
}
