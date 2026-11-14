"""Проверка безопасности сервера для команды /security: где сервер уязвим и что с этим делать.

Ничего не взламывает и не сканирует чужое — только смотрит настройки этой машины: вход по SSH,
файрвол, защиту от перебора паролей, открытые наружу порты, права на файлы с секретами,
обновления. Исправляет сам только безопасное (права файлов), остальное — командой для Termius.
"""

import os
import re
import stat
import subprocess

OK, WARN, BAD = "✅", "⚠️", "⛔"


def _run(cmd: list[str], timeout: int = 60) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


class Audit:
    """run — как запускать команды, read — как читать файлы (в тестах подменяются)."""

    def __init__(self, files: list[str], expected_ports: set[int], run=_run, read=None, exists=os.path.exists):
        self.files, self.expected = files, set(expected_ports)
        self.run, self.exists = run, exists
        self.read = read or self._read

    @staticmethod
    def _read(path: str) -> str:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    # ---------- проверки: каждая — (знак, что, подробно, как исправить) ----------

    def ssh_settings(self) -> dict[str, str]:
        """Настройки SSH: сначала спрашиваем сам sshd, не вышло — читаем файлы настроек."""
        out: dict[str, str] = {}
        for cmd in (["sshd", "-T"], ["/usr/sbin/sshd", "-T"],
                    ["/usr/sbin/sshd", "-T", "-C", "user=root,host=localhost,addr=127.0.0.1"]):
            for line in self.run(cmd).splitlines():
                k, _, v = line.partition(" ")
                if k:
                    out[k.lower()] = v.strip().lower()
            if out:
                return out
        # Запасной путь: sshd_config и подключённые файлы; у sshd действует ПЕРВОЕ встреченное значение
        import glob
        texts, seen = [], set()

        def load(path: str) -> None:
            if path in seen:
                return
            seen.add(path)
            text = self.read(path)
            for line in text.splitlines():
                k, _, v = line.strip().partition(" ")
                if k.lower() == "include":
                    for pat in v.split():
                        for f in sorted(glob.glob(pat if pat.startswith("/") else "/etc/ssh/" + pat)):
                            load(f)
                elif k.lower() == "match":
                    break  # дальше — правила для отдельных пользователей, общие настройки кончились
                else:
                    texts.append(line)
        load("/etc/ssh/sshd_config")
        for line in texts:
            k, _, v = line.strip().partition(" ")
            if k and not k.startswith("#"):
                out.setdefault(k.lower(), v.strip().lower())
        if out:  # значения OpenSSH по умолчанию, если в файлах не заданы
            out.setdefault("passwordauthentication", "yes")
            out.setdefault("permitrootlogin", "prohibit-password")
            out.setdefault("port", "22")
        return out

    def ssh(self) -> list[tuple]:
        out = self.ssh_settings()
        if not out:
            return [(WARN, "SSH", "Не удалось прочитать настройки SSH",
                     "Проверить вручную: grep -Ei 'PasswordAuthentication|PermitRootLogin' /etc/ssh/sshd_config")]
        res = []
        pw = out.get("passwordauthentication") == "yes"
        root = out.get("permitrootlogin", "")
        if pw and root == "yes":
            res.append((BAD, "SSH: вход root по паролю",
                        "Пароль root можно перебирать из интернета — это главный способ взлома серверов.",
                        "Поставьте вход по ключу (в Termius: Keychain → Generate key → Export to host), потом:\n"
                        "sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config "
                        "&& systemctl restart ssh"))
        elif pw:
            res.append((WARN, "SSH: вход по паролю", "Пароль можно перебирать. Надёжнее вход по ключу.",
                        "После настройки ключа: PasswordAuthentication no в /etc/ssh/sshd_config"))
        else:
            res.append((OK, "SSH: только по ключу", "", ""))
        port = out.get("port", "22")
        if port == "22" and pw:
            res.append((WARN, "SSH на стандартном порту 22", "Боты перебирают пароли на 22 круглосуточно.",
                        "Защита от перебора (fail2ban, ниже) решает это и без смены порта."))
        return res

    def ssh_ports(self) -> set[int]:
        port = self.ssh_settings().get("port", "22")
        return {int(port)} if port.isdigit() else {22}

    def ufw_command(self, ssh_ports: set[int]) -> str:
        """Включить файрвол, не отрезав VPN: сначала открыть все его порты, SSH и порт 80 (сертификат)."""
        rng = range(30000, 30050)
        single = sorted((self.expected | ssh_ports | {80}) - set(rng))
        cmd = " && ".join(f"ufw allow {p}" for p in single)
        if self.expected & set(rng):
            cmd += " && ufw allow 30000:30049/udp"
        return cmd + " && ufw --force enable"

    def firewall(self, ssh_ports: set[int] = frozenset({22})) -> list[tuple]:
        out = self.run(["ufw", "status"])
        if "Status: active" in out:
            return [(OK, "Файрвол ufw включён", "", "")]
        cmd = self.ufw_command(set(ssh_ports))
        if not out:
            return [(WARN, "Файрвол", "ufw не найден", "apt install -y ufw && " + cmd)]
        return [(WARN, "Файрвол выключен", "Открыт любой порт, который кто-то запустит на сервере.",
                 "Команда сначала открывает порты VPN и SSH, потом включает файрвол:\n" + cmd)]

    def bruteforce(self) -> list[tuple]:
        active = self.run(["systemctl", "is-active", "fail2ban"]).strip() == "active"
        if active:
            return [(OK, "Защита от перебора паролей (fail2ban)", "", "")]
        return [(WARN, "Нет защиты от перебора паролей",
                 "Без fail2ban адрес, перебирающий пароли SSH, не блокируется.",
                 "apt install -y fail2ban && systemctl enable --now fail2ban")]

    def ports(self, ssh_ports: set[int]) -> list[tuple]:
        """Порты, открытые наружу: всё, чего не ждём, — повод проверить."""
        seen: dict[int, str] = {}
        for line in self.run(["ss", "-H", "-tulpn"]).splitlines():
            cols = line.split()
            if len(cols) < 5:
                continue
            local = cols[4]
            host, _, port = local.rpartition(":")
            if not port.isdigit():
                continue
            if host.startswith("127.") or host in ("[::1]", "::1", "localhost") or host.startswith("[::ffff:127."):
                continue
            proc = re.search(r'\("([^"]+)"', line)
            name = proc.group(1) if proc else "?"
            # Не «открытые порты», а свои: исходящие UDP-сокеты Hysteria/Xray (случайные номера)
            # и получение адреса от хостинга (DHCP, 68 и 546)
            if cols[0] == "udp" and (name in ("hysteria", "xray") or int(port) in (68, 546)):
                continue
            seen.setdefault(int(port), name)
        if not seen:
            return [(WARN, "Открытые порты", "Не удалось получить список", "")]
        extra = {p: n for p, n in seen.items() if p not in self.expected | ssh_ports | {80}}
        if not extra:
            return [(OK, f"Наружу открыты только нужные порты ({len(seen)})", "", "")]
        lst = ", ".join(f"{p} ({n})" for p, n in sorted(extra.items())[:12])
        return [(WARN, "Наружу открыты незнакомые порты", lst,
                 "Если это не ваше — остановите программу или закройте порт: ufw deny <порт>")]

    def files_perms(self) -> list[tuple]:
        bad = []
        for path in self.files:
            try:
                mode = os.stat(path).st_mode
            except OSError:
                continue
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                bad.append(path)
        if not bad:
            return [(OK, "Файлы с секретами закрыты от других", "", "")]
        return [(BAD, "Файлы с секретами читают посторонние", ", ".join(os.path.basename(p) for p in bad),
                 "Кнопка «Исправить права» ниже (chmod 600)")]

    def updates(self) -> list[tuple]:
        res = []
        sim = self.run(["apt-get", "-s", "upgrade"], timeout=120)
        sec = sum(1 for line in sim.splitlines() if line.startswith("Inst ") and "security" in line.lower())
        if sec:
            res.append((WARN, f"Не установлены обновления безопасности: {sec}",
                        "Закрывают известные дыры в системе.", "apt update && apt -y upgrade"))
        else:
            res.append((OK, "Обновления безопасности установлены", "", ""))
        auto = self.read("/etc/apt/apt.conf.d/20auto-upgrades")
        if 'Unattended-Upgrade "1"' not in auto:
            res.append((WARN, "Автообновления системы выключены", "Дыры закрываются только вручную.",
                        "apt install -y unattended-upgrades && dpkg-reconfigure -f noninteractive unattended-upgrades"))
        if self.exists("/var/run/reboot-required"):
            res.append((WARN, "Нужна перезагрузка", "Обновлённое ядро заработает только после неё.", "reboot"))
        return res

    def accounts(self) -> list[tuple]:
        empty = [l.split(":")[0] for l in self.read("/etc/shadow").splitlines() if l.count(":") > 2 and l.split(":")[1] == ""]
        if empty:
            return [(BAD, "Учётки без пароля", ", ".join(empty[:5]), "passwd -l <имя>")]
        return []

    def check(self) -> list[tuple]:
        sp = self.ssh_ports()
        res = []
        for f in (self.ssh, lambda: self.firewall(sp), self.bruteforce, lambda: self.ports(sp), self.files_perms,
                  self.updates, self.accounts):
            try:
                res += f()
            except Exception as e:  # одна сломанная проверка не роняет весь отчёт
                res.append((WARN, "Проверка не удалась", str(e)[:120], ""))
        return res

    def fix_perms(self) -> int:
        n = 0
        for path in self.files:
            try:
                if os.stat(path).st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                    os.chmod(path, 0o600)
                    n += 1
            except OSError:
                pass
        return n


def report(results: list[tuple]) -> str:
    bad = sum(1 for r in results if r[0] != OK)
    head = ("<b>🔐 Безопасность сервера</b>\n" +
            ("Серьёзных проблем не найдено." if not bad else f"Найдено проблем: {bad}. Что сделать — под каждой."))
    lines = []
    for sign, title, detail, fix in results:
        line = f"{sign} <b>{title}</b>"
        if detail:
            line += f"\n<i>{_esc(detail)}</i>"
        if fix and sign != OK:
            line += f"\n<code>{_esc(fix)}</code>"
        lines.append(line)
    return head + "\n\n" + "\n\n".join(lines)


def problems(results: list[tuple]) -> set[str]:
    return {r[1] for r in results if r[0] != OK}


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
