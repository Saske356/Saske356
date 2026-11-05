"""Мини-блокчейн с майнингом на Proof-of-Work, как у Bitcoin, только упрощённый.

Суть майнинга:
  1. Берём данные блока: номер, хеш прошлого блока, время, кто майнит, nonce.
  2. Считаем от них SHA-256 (дважды, как в Bitcoin).
  3. Если хеш, прочитанный как число, меньше цели (target), блок найден.
     Если нет, увеличиваем nonce на 1 и пробуем снова.
  Угадать подходящий хеш заранее нельзя, остаётся только перебор.
  Чем меньше target (больше «сложность»), тем дольше перебирать.
"""

import hashlib
import json
import os
import threading
import time

REWARD = 50              # монет за найденный блок
TARGET_BLOCK_TIME = 10   # сколько секунд в среднем должен майниться блок
START_BITS = 20          # стартовая сложность: хеш начинается с 20 нулевых бит
MIN_BITS, MAX_BITS = 12, 30


def sha256d(data: bytes) -> str:
    """Двойной SHA-256, как в Bitcoin."""
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


def block_header(index: int, prev_hash: str, timestamp: int, miner: int, bits: int) -> bytes:
    return f"{index}|{prev_hash}|{timestamp}|{miner}|{bits}|".encode()


def target_for(bits: int) -> int:
    """Хеш должен быть меньше этого числа. Каждый бит сложности удваивает работу."""
    return 1 << (256 - bits)


class Miner:
    """Перебирает nonce. Работает в отдельном потоке, счётчик можно читать снаружи."""

    def __init__(self, index: int, prev_hash: str, miner: int, bits: int):
        self.index, self.prev_hash, self.miner, self.bits = index, prev_hash, miner, bits
        self.timestamp = int(time.time())
        self.attempts = 0
        self.started = time.time()
        self.stop = threading.Event()

    def run(self) -> dict | None:
        prefix = block_header(self.index, self.prev_hash, self.timestamp, self.miner, self.bits)
        target = target_for(self.bits)
        nonce = 0
        while not self.stop.is_set():
            h = sha256d(prefix + str(nonce).encode())
            self.attempts = nonce + 1
            if int(h, 16) < target:
                return {
                    "index": self.index, "prev_hash": self.prev_hash, "timestamp": self.timestamp,
                    "miner": self.miner, "bits": self.bits, "nonce": nonce, "hash": h,
                    "attempts": self.attempts, "seconds": round(time.time() - self.started, 2),
                }
            nonce += 1
        return None

    @property
    def hashrate(self) -> float:
        return self.attempts / max(time.time() - self.started, 1e-6)


class Chain:
    """Цепочка блоков в JSON-файле. Каждый блок хранит хеш предыдущего."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.blocks = json.load(f)
        else:
            genesis = {"index": 0, "prev_hash": "0" * 64, "timestamp": int(time.time()),
                       "miner": 0, "bits": START_BITS, "nonce": 0, "attempts": 0, "seconds": 0}
            genesis["hash"] = sha256d(block_header(0, genesis["prev_hash"], genesis["timestamp"], 0,
                                                   START_BITS) + b"0")
            self.blocks = [genesis]
            self._save()

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.blocks, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @property
    def tip(self) -> dict:
        return self.blocks[-1]

    def next_bits(self) -> int:
        """Подстройка сложности: блоки идут быстро — сложнее, медленно — проще."""
        tip = self.tip
        if tip["index"] == 0:
            return START_BITS
        bits = tip["bits"]
        if tip["seconds"] < TARGET_BLOCK_TIME / 2:
            bits += 1
        elif tip["seconds"] > TARGET_BLOCK_TIME * 2:
            bits -= 1
        return max(MIN_BITS, min(MAX_BITS, bits))

    def new_miner(self, user_id: int) -> Miner:
        with self.lock:
            return Miner(self.tip["index"] + 1, self.tip["hash"], user_id, self.next_bits())

    @staticmethod
    def check(block: dict) -> bool:
        """Проверить чужой блок легко: один хеш вместо миллионов."""
        h = sha256d(block_header(block["index"], block["prev_hash"], block["timestamp"],
                                 block["miner"], block["bits"]) + str(block["nonce"]).encode())
        return h == block["hash"] and int(h, 16) < target_for(block["bits"])

    def add(self, block: dict) -> bool:
        """Добавить блок. False, если кто-то уже успел найти блок на этой высоте."""
        with self.lock:
            if block["prev_hash"] != self.tip["hash"] or not self.check(block):
                return False
            self.blocks.append(block)
            self._save()
            return True

    def balance(self, user_id: int) -> int:
        return sum(REWARD for b in self.blocks[1:] if b["miner"] == user_id)

    def top(self, n: int = 10) -> list[tuple[int, int]]:
        counts: dict[int, int] = {}
        for b in self.blocks[1:]:
            counts[b["miner"]] = counts.get(b["miner"], 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])[:n]
