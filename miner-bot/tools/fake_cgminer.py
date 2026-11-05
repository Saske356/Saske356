#!/usr/bin/env python3
"""Заглушка cgminer для проверки бота без ASIC и пула.

Понимает те же ключи (-o, -u, --api-port …), пишет строки в лог и отвечает
на команды API summary / pools / quit случайными, но правдоподобными данными.

    CGMINER_PATH=./tools/fake_cgminer.py   # в .env, файл должен быть исполняемым
"""
import argparse
import json
import random
import socket
import sys
import threading
import time

p = argparse.ArgumentParser()
p.add_argument("-o", dest="url", default="stratum+tcp://example:3333")
p.add_argument("-u", dest="user", default="worker")
p.add_argument("-p", dest="password", default="x")
p.add_argument("--api-port", type=int, default=4028)
args, _ = p.parse_known_args()

start = time.time()
accepted = rejected = 0


def mining_loop() -> None:
    global accepted, rejected
    while True:
        time.sleep(3)
        if random.random() < 0.97:
            accepted += 1
            print(f"[{time.strftime('%H:%M:%S')}] Accepted share {accepted} to {args.url}", flush=True)
        else:
            rejected += 1
            print(f"[{time.strftime('%H:%M:%S')}] Rejected share", flush=True)


def reply(cmd: str) -> dict:
    if cmd == "summary":
        mhs = 13_500_000 * random.uniform(0.95, 1.05)          # ~13.5 TH/s
        return {"STATUS": [{"STATUS": "S"}], "SUMMARY": [{
            "Elapsed": int(time.time() - start), "MHS av": 13_500_000.0, "MHS 5s": mhs,
            "Accepted": accepted, "Rejected": rejected, "Hardware Errors": 0}]}
    if cmd == "pools":
        return {"STATUS": [{"STATUS": "S"}], "POOLS": [
            {"POOL": 0, "URL": args.url, "Status": "Alive", "Stratum Active": True}]}
    if cmd == "quit":
        return {"STATUS": [{"STATUS": "BYE"}]}
    return {"STATUS": [{"STATUS": "E", "Msg": "Invalid command"}]}


print(f"fake cgminer: pool {args.url}, user {args.user}, API :{args.api_port}", flush=True)
threading.Thread(target=mining_loop, daemon=True).start()
srv = socket.create_server(("127.0.0.1", args.api_port), reuse_port=False)
while True:
    conn, _ = srv.accept()
    with conn:
        cmd = json.loads(conn.recv(4096).decode() or "{}").get("command", "")
        conn.sendall(json.dumps(reply(cmd)).encode() + b"\x00")
    if cmd == "quit":
        print("quit by API", flush=True)
        sys.exit(0)
