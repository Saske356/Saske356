"""Чтение мобильной базы текстур GTA SA (texdb: .txt + .dxt.toc + .dxt.dat + .dxt.tmb).

Запись в .dat: заголовок 16 байт (метка u32, ширина u16, высота u16 + флаг, размер u32, формат u32), дальше данные.
Формат 0 — несжатый DXT1 с полной цепочкой мип-уровней: такие текстуры распаковываем целиком.
Остальные сжаты собственным алгоритмом — для них берём миниатюру 8×8 RGBA из .tmb (метки совпадают по младшим 16 битам).
"""
import os
import re
import struct

import numpy as np
from PIL import Image


def _rgb565(c):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.stack([r, g, b], -1)


def dxt1(data, w, h):
    """DXT1 → RGBA (numpy, векторно)."""
    bw, bh = max(1, w // 4), max(1, h // 4)
    blk = np.frombuffer(data[: bw * bh * 8], dtype="<u2").reshape(bh, bw, 4)
    c0, c1 = blk[..., 0].astype(np.int32), blk[..., 1].astype(np.int32)
    bits = blk[..., 2].astype(np.uint32) | (blk[..., 3].astype(np.uint32) << 16)
    a, b = _rgb565(c0), _rgb565(c1)
    more = (c0 > c1)[..., None]
    p2 = np.where(more, (2 * a + b) // 3, (a + b) // 2)
    p3 = np.where(more, (a + 2 * b) // 3, 0)
    pal = np.stack([a, b, p2, p3], 2)  # bh, bw, 4, 3
    alpha = np.full((bh, bw, 4), 255, np.uint8)
    alpha[..., 3] = np.where(c0 > c1, 255, 0)
    idx = np.stack([(bits >> (2 * i)) & 3 for i in range(16)], -1).reshape(bh, bw, 4, 4)
    rgb = np.take_along_axis(pal[:, :, None, :, :].repeat(4, 2), idx[..., None].repeat(3, -1).astype(np.int64), 3)
    al = np.take_along_axis(alpha[:, :, None, :].repeat(4, 2), idx.astype(np.int64), 3)
    out = np.concatenate([rgb.astype(np.uint8), al[..., None]], -1)  # bh, bw, 4(y), 4(x), 4
    out = out.transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return Image.fromarray(out[:h, :w], "RGBA")


def dxt5(data, w, h):
    """DXT5 (с прозрачностью) → RGBA."""
    bw, bh = max(1, w // 4), max(1, h // 4)
    raw = np.frombuffer(data[: bw * bh * 16], dtype=np.uint8).reshape(bh, bw, 16)
    a0, a1 = raw[..., 0].astype(np.int32), raw[..., 1].astype(np.int32)
    abits = np.zeros((bh, bw), np.uint64)
    for k in range(6):
        abits |= raw[..., 2 + k].astype(np.uint64) << np.uint64(8 * k)
    lv = [a0, a1]
    big = a0 > a1
    for k in range(1, 7):
        lv.append(np.where(big, ((7 - k) * a0 + k * a1) // 7, 0))
    for k in range(1, 5):
        lv[1 + k] = np.where(big, lv[1 + k], ((5 - k) * a0 + k * a1) // 5)
    lv[6] = np.where(big, lv[6], 0)
    lv[7] = np.where(big, lv[7], 255)
    apal = np.stack(lv, -1)
    aidx = np.stack([((abits >> np.uint64(3 * i)) & np.uint64(7)).astype(np.int64) for i in range(16)], -1)
    alpha = np.take_along_axis(apal, aidx, 2).reshape(bh, bw, 4, 4)
    col = raw[..., 8:].copy()
    # цветовой блок DXT5 всегда в режиме 4 цветов
    c = np.frombuffer(col.tobytes(), dtype="<u2").reshape(bh, bw, 4)
    c0, c1 = c[..., 0].astype(np.int32), c[..., 1].astype(np.int32)
    bits = c[..., 2].astype(np.uint32) | (c[..., 3].astype(np.uint32) << 16)
    A, B = _rgb565(c0), _rgb565(c1)
    pal = np.stack([A, B, (2 * A + B) // 3, (A + 2 * B) // 3], 2)
    idx = np.stack([(bits >> (2 * i)) & 3 for i in range(16)], -1).reshape(bh, bw, 4, 4)
    rgb = np.take_along_axis(pal[:, :, None, :, :].repeat(4, 2), idx[..., None].repeat(3, -1).astype(np.int64), 3)
    out = np.concatenate([rgb.astype(np.uint8), alpha[..., None].astype(np.uint8)], -1)
    out = out.transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return Image.fromarray(out[:h, :w], "RGBA")


def chain(w, h, block):
    total, x, y = 0, w, h
    while True:
        total += max(1, x // 4) * max(1, y // 4) * block
        if x <= 1 and y <= 1:
            break
        x, y = max(1, x // 2), max(1, y // 2)
    return total


class TexDB:
    def __init__(self, folder, name):
        base = os.path.join(folder, name, name)
        lines = open(base + ".txt", encoding="latin1").read().split("\n")
        toc = open(base + ".dxt.toc", "rb").read()
        self.offs = struct.unpack(f"<{len(toc) // 4}I", toc)
        self.dat = open(base + ".dxt.dat", "rb")
        self.index, self.affil = {}, {}
        for i, l in enumerate(lines):
            m = re.match(r'"([^"]+)"', l)
            if not m:
                continue
            n = m.group(1).lower()
            self.index[n] = i
            a = re.search(r'affiliate=([^"\s]+)', l)
            if a:
                self.affil[n] = a.group(1).lower()
        valid = sorted(o for o in self.offs if o != 0xFFFFFFFF)
        self.next = {o: valid[k + 1] if k + 1 < len(valid) else os.path.getsize(base + ".dxt.dat") for k, o in enumerate(valid)}
        self.thumbs = {}
        if os.path.exists(base + ".dxt.tmb"):
            b = open(base + ".dxt.tmb", "rb").read()
            o = 0
            while o + 12 <= len(b):
                tag, w, hh, size = struct.unpack_from("<IHHI", b, o)
                h = hh & 0x7FFF
                if size == 4 + w * h * 4 and w * h:
                    px = b[o + 16:o + 16 + w * h * 4]
                    self.thumbs[tag & 0xFFFF] = Image.frombytes("RGBA", (w, h), px)
                o += 12 + size

    def has(self, name):
        return name.lower() in self.index

    def get(self, name, depth=0):
        """PIL-картинка текстуры или None. Возвращает (картинка, чёткая ли)."""
        n = name.lower()
        if n in self.affil and depth < 4:
            return self.get(self.affil[n], depth + 1)
        i = self.index.get(n)
        if i is None or i >= len(self.offs) or self.offs[i] == 0xFFFFFFFF:
            return None, False
        off = self.offs[i]
        self.dat.seek(off)
        e = self.dat.read(self.next[off] - off)
        tag, w, hh, size, fmt = struct.unpack_from("<IHHII", e)
        h = hh & 0x7FFF
        if fmt == 0 and w >= 4 and h >= 4:
            n = len(e) - 16
            try:
                if n >= chain(w, h, 16) - 64:
                    return dxt5(e[16:], w, h), True
                if n >= w * h // 2:
                    return dxt1(e[16:], w, h), True
            except Exception:
                pass
        t = self.thumbs.get(tag & 0xFFFF)
        if t is not None:
            return t.resize((max(8, min(w, 64)), max(8, min(h, 64))), Image.BILINEAR), False
        return None, False


class TexSet:
    """Несколько баз сразу: ищем текстуру по очереди."""

    def __init__(self, folder, names):
        self.dbs = [TexDB(folder, n) for n in names if os.path.exists(os.path.join(folder, n, n + ".txt"))]

    def get(self, name):
        for db in self.dbs:
            if db.has(name):
                img, sharp = db.get(name)
                if img is not None:
                    return img, sharp
        return None, False
