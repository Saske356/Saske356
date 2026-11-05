#!/usr/bin/env python3
"""
Простой учебный CPU-майнер в стиле Monero на базе xxhash.

ВАЖНО: настоящий Monero использует алгоритм Proof-of-Work RandomX, а не xxhash.
Хеши, посчитанные этим скриптом, НЕ примет ни пул, ни сеть Monero. Скрипт
показывает устройство майнера: формат блоба блока, перебор nonce,
проверку сложности по правилам Monero, многопроцессную работу на всех ядрах
CPU и подсчёт хешрейта. Чтобы получить настоящий майнер, замените функцию
pow_hash() на RandomX (см. README.md).

Запуск:
    pip install xxhash
    python miner.py                      # все ядра, сложность 200000
    python miner.py -t 4 -d 1000000      # 4 потока, выше сложность
    python miner.py --blocks 5           # остановиться после 5 блоков
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import struct
import time
from dataclasses import dataclass

import xxhash

NONCE_OFFSET = 39          # смещение nonce в блобе (как в Monero для major_version >= 2)
NONCE_SPACE = 2 ** 32      # nonce в Monero — 4 байта little-endian
BATCH = 4096               # сколько хешей воркер считает между проверками флагов
MAX_HASH = 2 ** 256


# ---------------------------------------------------------------------------
# Формат блоба (упрощённый hashing blob Monero)
# ---------------------------------------------------------------------------

def varint(n: int) -> bytes:
    """Кодирование varint (LEB128), как в CryptoNote."""
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


@dataclass
class Job:
    height: int
    prev_hash: bytes       # 32 байта
    merkle_root: bytes     # 32 байта
    tx_count: int
    timestamp: int
    difficulty: int

    def blob(self) -> bytearray:
        """major(1) minor(1) timestamp(5) prev(32) nonce(4) merkle(32) txcount"""
        ts = varint(self.timestamp)
        assert len(ts) == 5, "timestamp должен кодироваться в 5 байт"
        head = bytes([16, 16]) + ts + self.prev_hash
        assert len(head) == NONCE_OFFSET
        return bytearray(head + b"\x00" * 4 + self.merkle_root + varint(self.tx_count))

    @property
    def target(self) -> int:
        # Правило Monero: хеш (LE, 256 бит) * difficulty < 2^256
        return MAX_HASH // self.difficulty


def new_job(height: int, prev_hash: bytes, difficulty: int) -> Job:
    return Job(
        height=height,
        prev_hash=prev_hash,
        merkle_root=os.urandom(32),    # имитация набора транзакций
        tx_count=1 + int.from_bytes(os.urandom(1), "little") % 20,
        timestamp=int(time.time()),
        difficulty=difficulty,
    )


# ---------------------------------------------------------------------------
# Функция Proof-of-Work
# ---------------------------------------------------------------------------

def pow_hash(blob: bytes) -> bytes:
    """32-байтовый хеш из двух xxh3_128 с разными сидами.

    Это место, где в настоящем майнере вызывается RandomX.
    """
    return xxhash.xxh3_128_digest(blob, seed=0) + xxhash.xxh3_128_digest(blob, seed=0x584D52)


def meets_target(h: bytes, target: int) -> bool:
    return int.from_bytes(h, "little") < target


# ---------------------------------------------------------------------------
# Воркер
# ---------------------------------------------------------------------------

def worker(wid: int, n_workers: int, job_q: mp.Queue, result_q: mp.Queue,
           hash_counter, job_id) -> None:
    """У каждого воркера своя очередь заданий; nonce = wid, wid+n, wid+2n, …"""
    pack_nonce = struct.Struct("<I").pack_into
    job, my_job_id = None, -1

    while True:
        # Ждём новое задание, если текущего нет или оно устарело
        if job is None or job_id.value != my_job_id:
            item = job_q.get()
            if item is None:
                return
            my_job_id, job = item
            if job_id.value != my_job_id:   # уже есть задание новее — берём его
                job = None
                continue
            blob = job.blob()
            target = job.target
            nonce = wid

        done = 0
        for _ in range(BATCH):
            pack_nonce(blob, NONCE_OFFSET, nonce)
            h = pow_hash(blob)
            done += 1
            if meets_target(h, target):
                result_q.put((my_job_id, wid, nonce, h))
                break
            nonce += n_workers
            if nonce >= NONCE_SPACE:
                # пространство исчерпано — ждём новое задание
                result_q.put((my_job_id, wid, None, None))
                job = None
                break

        with hash_counter.get_lock():
            hash_counter.value += done


# ---------------------------------------------------------------------------
# Координатор
# ---------------------------------------------------------------------------

def fmt_rate(hps: float) -> str:
    for unit in ("H/s", "kH/s", "MH/s"):
        if hps < 1000:
            return f"{hps:7.2f} {unit}"
        hps /= 1000
    return f"{hps:7.2f} GH/s"


def main() -> None:
    p = argparse.ArgumentParser(description="Учебный CPU-майнер в стиле Monero (xxhash)")
    p.add_argument("-t", "--threads", type=int, default=os.cpu_count() or 1,
                   help="число процессов-воркеров (по умолчанию все ядра)")
    p.add_argument("-d", "--difficulty", type=int, default=200_000,
                   help="сложность (среднее число хешей на блок)")
    p.add_argument("--blocks", type=int, default=0,
                   help="остановиться после N найденных блоков (0 — бесконечно)")
    p.add_argument("--report", type=float, default=5.0,
                   help="интервал вывода хешрейта, секунд")
    args = p.parse_args()

    n = max(1, args.threads)
    job_qs = [mp.Queue() for _ in range(n)]
    result_q: mp.Queue = mp.Queue()
    hash_counter = mp.Value("Q", 0)
    job_id = mp.Value("i", 0)

    procs = [mp.Process(target=worker, args=(i, n, job_qs[i], result_q, hash_counter, job_id),
                        daemon=True) for i in range(n)]
    for pr in procs:
        pr.start()

    def broadcast(job: Job) -> None:
        with job_id.get_lock():
            job_id.value += 1
            jid = job_id.value
        for q in job_qs:
            q.put((jid, job))

    height, prev = 1, b"\x00" * 32
    job = new_job(height, prev, args.difficulty)
    broadcast(job)
    print(f"[*] Старт: {n} воркер(ов), сложность {args.difficulty}, алгоритм xxh3-128x2")
    print(f"[*] Задание #{job.height}: prev={prev.hex()[:16]}…")

    start = last_t = time.time()
    last_hashes = 0
    found = 0
    exhausted = set()

    try:
        while True:
            try:
                jid, wid, nonce, h = result_q.get(timeout=0.5)
            except Exception:
                jid = None

            if jid is not None and jid == job_id.value:
                if nonce is None:
                    exhausted.add(wid)
                    if len(exhausted) == n:
                        print("[!] Пространство nonce исчерпано, обновляю задание")
                        exhausted.clear()
                        job = new_job(height, prev, args.difficulty)
                        broadcast(job)
                else:
                    # перепроверяем решение в координаторе
                    blob = job.blob()
                    struct.pack_into("<I", blob, NONCE_OFFSET, nonce)
                    assert pow_hash(blob) == h and meets_target(h, job.target)
                    found += 1
                    print(f"[+] Блок #{height} найден воркером {wid}: nonce={nonce:#010x} "
                          f"hash={h.hex()[:24]}…")
                    if args.blocks and found >= args.blocks:
                        break
                    height, prev = height + 1, h
                    exhausted.clear()
                    job = new_job(height, prev, args.difficulty)
                    broadcast(job)

            now = time.time()
            if now - last_t >= args.report:
                total = hash_counter.value
                rate = (total - last_hashes) / (now - last_t)
                print(f"[=] Хешрейт {fmt_rate(rate)} | всего {total} хешей | блоков {found}")
                last_t, last_hashes = now, total
    except KeyboardInterrupt:
        print("\n[*] Остановка…")
    finally:
        for q in job_qs:
            q.put(None)
        for pr in procs:
            pr.join(timeout=1)
            if pr.is_alive():
                pr.terminate()
        elapsed = time.time() - start
        total = hash_counter.value
        print(f"[*] Итого: {total} хешей за {elapsed:.1f} с "
              f"(в среднем {fmt_rate(total / max(elapsed, 1e-9)).strip()}), блоков: {found}")


if __name__ == "__main__":
    main()
