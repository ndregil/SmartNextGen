# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org
#
# Perintah lanjutan file manager (khusus owner di config.txt). Membutuhkan plugins/cmd_filemanager.py
# (memakai fungsi pemeriksaan owner, perlindungan file, penyamaran rahasia, dan audit darinya).
#
#   find <pola> [folder]          cari file/folder (nama; boleh pakai * dan ?)
#   grep <teks> [-p <path>]       cari teks di dalam file (file sensitif dilewati)
#   tree [folder] [kedalaman]     struktur folder
#   du [path]                     ukuran folder & isi terbesar    | df  sisa ruang disk
#   head|tail <file> [baris]      awal / akhir file (log)         | hash <file> [md5|sha1|sha256|sha512]
#   writefile [-a] <file> <teks>  tulis file kecil (\n = baris baru)
#   edit <file> replace <lama> => <baru> | line <n> <teks> | insert <n> <teks> | delete <n>
#   backup [full] [send] | backup auto <1h|12h|1d|off>   cadangan data/*.db, plugins, lang
#   deploy <url> [nama] [sha256=<hex>]   pasang/ganti plugin dari URL + reload otomatis (gagal = kembali)
#   rollback <plugin> [n|list]    kembalikan plugin ke versi sebelumnya
#   inbox on|off|status           simpan file yang Anda kirim lewat PM ke filemanager/inbox
#
# Catatan: bot membaca pesan per kata, jadi spasi ganda & baris baru dari chat tidak tersimpan;
# pakai \n di writefile/edit untuk baris baru.

import asyncio
import fnmatch
import functools
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))
UNSAFE_RELOAD = {"cmd_users", "zz_aliases", "cmd_reload"}
UA = "Mozilla/5.0 (compatible; SmartNG-FileTools/1.0)"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".trash", ".cache"}

MAX_WRITE_CHARS = 20000
EDIT_MAX_BYTES = 500_000
DEPLOY_MAX_BYTES = 2 * 1024 * 1024
BACKUP_SEND_MAX = 50 * 1024 * 1024
BACKUP_KEEP_DEFAULT = 7
HASH_ALGOS = ("md5", "sha1", "sha256", "sha512")
INBOX_EXT = {".py", ".json", ".txt", ".md", ".log", ".zip", ".tar", ".gz", ".tgz", ".db", ".csv", ".ini", ".cfg",
             ".yml", ".yaml", ".xml", ".sql", ".sh", ".html", ".css", ".js"}
NS_OOB = "{jabber:x:oob}url"
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)

_UNITS = {"m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "menit": 60,
          "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "jam": 3600,
          "d": 86400, "day": 86400, "days": 86400, "hari": 86400}
_INTERVAL_RE = re.compile(r"^(\d{1,4})([a-z]+)$", re.I)

DEFAULT_MSG = {
    "id": {
        "err_syntax": "Gagal: kesalahan sintaks/format: {err}. File tidak diubah.",
        "err_not_text": "Gagal: file bukan teks UTF-8.",
        "err_not_file": "Gagal: {name} bukan file.",
        "find_usage": "Pemakaian: find <pola> [folder]  (contoh: find *.py plugins)",
        "find_none": "Tidak ada yang cocok dengan '{pattern}'.",
        "find_header": "🔎 {count} hasil untuk '{pattern}' di {base}{more}:",
        "grep_usage": "Pemakaian: grep <teks> [-p <file/folder>]  (contoh: grep api_key -p plugins)",
        "grep_none": "Tidak ada baris yang memuat '{pattern}'.",
        "grep_header": "🔎 {count} baris memuat '{pattern}'{more}:",
        "more": " (hasil dipotong)",
        "du_header": "💾 {path}: {total}{partial}",
        "du_partial": " (perkiraan, pemindaian dihentikan karena terlalu lama)",
        "df_header": "💽 Ruang disk:",
        "head_usage": "Pemakaian: head <file> [jumlah baris]",
        "tail_usage": "Pemakaian: tail <file> [jumlah baris]",
        "hash_usage": "Pemakaian: hash <file> [md5|sha1|sha256|sha512]",
        "hash_result": "🔐 {algo} {name} ({size}):\n{digest}",
        "write_usage": "Pemakaian: writefile [-a] <file> <teks>  (-a menambah di akhir; \\n = baris baru)",
        "write_ok": "Berhasil menulis {name} ({size}).",
        "write_too_big": "Gagal: isi terlalu panjang (maks {max} karakter).",
        "edit_usage": ("Pemakaian: edit <file> replace <lama> => <baru> | edit <file> line <n> <teks> | "
                       "edit <file> insert <n> <teks> | edit <file> delete <n>"),
        "edit_ok": "Berhasil mengubah {name}: {detail}",
        "edit_text_missing": "Teks yang dicari tidak ditemukan di {name}.",
        "edit_bad_line": "Nomor baris {n} di luar rentang (file punya {total} baris).",
        "backup_usage": "Pemakaian: backup [full] [send] | backup auto <1h|12h|1d|off>",
        "backup_working": "Membuat cadangan...",
        "backup_ok": "Berhasil membuat cadangan: {path} ({size}). Tersimpan {count} cadangan.",
        "backup_sent": "Berhasil mengirim cadangan ke PM Anda.",
        "backup_full_send": "Gagal: cadangan 'full' berisi password dan tidak boleh dikirim lewat chat. Ambil dari folder {dir}.",
        "backup_pm_only": "Gagal: pengiriman cadangan hanya lewat PM.",
        "backup_too_big": "Gagal: cadangan terlalu besar untuk dikirim ({size}); ambil dari folder {dir}.",
        "backup_auto_set": "Berhasil: cadangan otomatis setiap {every} (menyimpan {keep} terakhir).",
        "backup_auto_off": "Cadangan otomatis dimatikan.",
        "backup_auto_status": "Cadangan otomatis: {state}",
        "backup_interval_bad": "Interval tidak valid. Gunakan {min} sampai {max}, contoh: 12h, 1d.",
        "deploy_usage": "Pemakaian: deploy <url> [nama_plugin] [sha256=<hex>]",
        "deploy_working": "Mengunduh dan memeriksa plugin...",
        "deploy_ok": "Berhasil memasang {name} ({size}, sha256 {sha}). {reload}",
        "deploy_same": "{name} sudah sama dengan versi terpasang, tidak ada perubahan.",
        "deploy_sha_mismatch": "Gagal: sha256 tidak cocok. Unduhan dibatalkan.",
        "deploy_not_text": "Gagal: file bukan teks UTF-8.",
        "deploy_bad_name": "Gagal: nama plugin tidak valid (huruf kecil, angka, garis bawah).",
        "deploy_no_register": "Gagal: file tidak memiliki fungsi register(bot), bukan plugin.",
        "deploy_reloaded": "Plugin sudah dimuat ulang.",
        "deploy_restart_needed": "Plugin inti ini baru aktif setelah: restart all",
        "deploy_no_reload": "Plugin cmd_reload tidak ada; jalankan: restart all",
        "deploy_rolled_back": "Gagal memuat {name}: {err}. Versi sebelumnya dikembalikan{again}.",
        "deploy_again": " (reload ulang berhasil)",
        "rollback_usage": "Pemakaian: rollback <plugin> [nomor | list]",
        "rollback_none": "Tidak ada cadangan untuk {name}.",
        "rollback_list": "Cadangan {name}:\n{items}",
        "rollback_ok": "Berhasil mengembalikan {name} ke versi {when}. {reload}",
        "inbox_usage": "Pemakaian: inbox on | off | status",
        "inbox_state": "Penyimpanan file dari PM: {state}.",
        "inbox_saved": "Berhasil menyimpan file: {path} ({size})",
        "inbox_fail": "Gagal menyimpan file dari PM: {err}",
        "on": "aktif", "off": "mati",
    },
    "en": {
        "err_syntax": "Failed: syntax/format error: {err}. The file was not changed.",
        "err_not_text": "Failed: the file is not UTF-8 text.",
        "err_not_file": "Failed: {name} is not a file.",
        "find_usage": "Usage: find <pattern> [folder]  (example: find *.py plugins)",
        "find_none": "Nothing matches '{pattern}'.",
        "find_header": "🔎 {count} results for '{pattern}' in {base}{more}:",
        "grep_usage": "Usage: grep <text> [-p <file/folder>]  (example: grep api_key -p plugins)",
        "grep_none": "No line contains '{pattern}'.",
        "grep_header": "🔎 {count} lines contain '{pattern}'{more}:",
        "more": " (results truncated)",
        "du_header": "💾 {path}: {total}{partial}",
        "du_partial": " (estimate, the scan was stopped because it took too long)",
        "df_header": "💽 Disk space:",
        "head_usage": "Usage: head <file> [number of lines]",
        "tail_usage": "Usage: tail <file> [number of lines]",
        "hash_usage": "Usage: hash <file> [md5|sha1|sha256|sha512]",
        "hash_result": "🔐 {algo} {name} ({size}):\n{digest}",
        "write_usage": "Usage: writefile [-a] <file> <text>  (-a appends; \\n = new line)",
        "write_ok": "Successfully wrote {name} ({size}).",
        "write_too_big": "Failed: the content is too long (max {max} characters).",
        "edit_usage": ("Usage: edit <file> replace <old> => <new> | edit <file> line <n> <text> | "
                       "edit <file> insert <n> <text> | edit <file> delete <n>"),
        "edit_ok": "Successfully edited {name}: {detail}",
        "edit_text_missing": "The text to replace was not found in {name}.",
        "edit_bad_line": "Line number {n} is out of range (the file has {total} lines).",
        "backup_usage": "Usage: backup [full] [send] | backup auto <1h|12h|1d|off>",
        "backup_working": "Creating the backup...",
        "backup_ok": "Successfully created backup: {path} ({size}). {count} backups kept.",
        "backup_sent": "Successfully sent the backup to your PM.",
        "backup_full_send": "Failed: a 'full' backup contains passwords and must not be sent over chat. Take it from {dir}.",
        "backup_pm_only": "Failed: backups can only be sent in a private chat.",
        "backup_too_big": "Failed: the backup is too large to send ({size}); take it from {dir}.",
        "backup_auto_set": "Successfully set: automatic backup every {every} (keeping the last {keep}).",
        "backup_auto_off": "Automatic backup turned off.",
        "backup_auto_status": "Automatic backup: {state}",
        "backup_interval_bad": "Invalid interval. Use {min} to {max}, e.g. 12h, 1d.",
        "deploy_usage": "Usage: deploy <url> [plugin_name] [sha256=<hex>]",
        "deploy_working": "Downloading and checking the plugin...",
        "deploy_ok": "Successfully deployed {name} ({size}, sha256 {sha}). {reload}",
        "deploy_same": "{name} is identical to the installed version, nothing changed.",
        "deploy_sha_mismatch": "Failed: sha256 mismatch. The deployment was cancelled.",
        "deploy_not_text": "Failed: the file is not UTF-8 text.",
        "deploy_bad_name": "Failed: invalid plugin name (lowercase letters, digits, underscore).",
        "deploy_no_register": "Failed: the file has no register(bot) function, so it is not a plugin.",
        "deploy_reloaded": "The plugin was reloaded.",
        "deploy_restart_needed": "This core plugin only becomes active after: restart all",
        "deploy_no_reload": "The cmd_reload plugin is missing; run: restart all",
        "deploy_rolled_back": "Failed to load {name}: {err}. The previous version was restored{again}.",
        "deploy_again": " (reloaded again successfully)",
        "rollback_usage": "Usage: rollback <plugin> [number | list]",
        "rollback_none": "There is no backup for {name}.",
        "rollback_list": "Backups of {name}:\n{items}",
        "rollback_ok": "Successfully restored {name} to the version from {when}. {reload}",
        "inbox_usage": "Usage: inbox on | off | status",
        "inbox_state": "Saving files received in PM: {state}.",
        "inbox_saved": "Successfully saved the file: {path} ({size})",
        "inbox_fail": "Failed to save the file from PM: {err}",
        "on": "on", "off": "off",
    },
}


# ------------------------------------------------------------------
# Fungsi murni (dijalankan di thread)
# ------------------------------------------------------------------
def parse_interval(token):
    m = _INTERVAL_RE.match((token or "").strip())
    if not m or m.group(2).lower() not in _UNITS:
        return None
    return int(m.group(1)) * _UNITS[m.group(2).lower()]


def fmt_interval(sec):
    sec = int(sec)
    for size, suffix in ((86400, "d"), (3600, "h"), (60, "m")):
        if sec % size == 0:
            return f"{sec // size}{suffix}"
    return f"{sec}s"


def walk_find(base, pattern, max_depth=8, max_results=30, max_visit=20000, deadline=10.0):
    pat = pattern.lower()
    glob_mode = any(c in pat for c in "*?[")
    t0, visited, out = time.time(), 0, []
    base = os.path.abspath(base)
    bd = base.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(base):
        depth = root.rstrip(os.sep).count(os.sep) - bd
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if depth >= max_depth:
            dirs[:] = []
        for name in dirs + sorted(files):
            if name.startswith("."):
                continue
            visited += 1
            if visited > max_visit or time.time() - t0 > deadline:
                return out, True
            low = name.lower()
            if fnmatch.fnmatch(low, pat) if glob_mode else pat in low:
                full = os.path.join(root, name)
                is_dir = os.path.isdir(full)
                try:
                    size = 0 if is_dir else os.path.getsize(full)
                except OSError:
                    size = 0
                out.append((os.path.relpath(full, base), is_dir, size))
                if len(out) >= max_results:
                    return out, True
    return out, False


def _iter_files(target, max_files):
    if os.path.isfile(target):
        yield target
        return
    n = 0
    for root, dirs, files in os.walk(target):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            n += 1
            if n > max_files:
                return
            yield os.path.join(root, name)


def walk_grep(target, needle, redact, skip, max_matches=20, max_files=3000, max_size=2 * 1024 * 1024, deadline=10.0):
    low = needle.lower()
    t0, matches = time.time(), []
    explicit = os.path.isfile(target)
    base = os.path.dirname(target) if explicit else target
    for fp in _iter_files(target, max_files):
        if time.time() - t0 > deadline:
            return matches, True
        if not explicit and skip(fp):
            continue
        try:
            if os.path.getsize(fp) > max_size:
                continue
            with open(fp, "rb") as fb:
                if b"\x00" in fb.read(1024):
                    continue
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if low in line.lower():
                        matches.append((os.path.relpath(fp, base) if not explicit else os.path.basename(fp),
                                        i, redact(line.strip())[:120]))
                        if len(matches) >= max_matches:
                            return matches, True
        except OSError:
            continue
    return matches, False


def render_tree(base, max_depth, max_lines=60):
    lines = [(os.path.basename(base.rstrip(os.sep)) or base) + "/"]
    count = [0]

    def walk(path, prefix, depth):
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError:
            return
        entries = [e for e in entries if not e.name.startswith(".") and e.name not in SKIP_DIRS]
        entries.sort(key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()))
        for i, e in enumerate(entries):
            if count[0] >= max_lines:
                return
            last = i == len(entries) - 1
            is_dir = e.is_dir(follow_symlinks=False)
            lines.append(f"{prefix}{'└── ' if last else '├── '}{e.name}{'/' if is_dir else ''}")
            count[0] += 1
            if is_dir and depth < max_depth:
                walk(e.path, prefix + ("    " if last else "│   "), depth + 1)

    walk(base, "", 1)
    return lines, count[0] >= max_lines


def dir_usage(path, deadline=20.0):
    t0 = time.time()
    partial = [False]

    def size_of(p):
        total, stack = 0, [p]
        while stack:
            if time.time() - t0 > deadline:
                partial[0] = True
                break
            cur = stack.pop()
            try:
                with os.scandir(cur) as it:
                    for e in it:
                        try:
                            if e.is_symlink():
                                continue
                            if e.is_dir(follow_symlinks=False):
                                stack.append(e.path)
                            else:
                                total += e.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
            except OSError:
                pass
        return total

    if os.path.isfile(path):
        return os.path.getsize(path), [], False
    items, total = [], 0
    with os.scandir(path) as it:
        entries = list(it)
    for e in entries:
        if time.time() - t0 > deadline:
            partial[0] = True
            break
        try:
            if e.is_symlink():
                continue
            if e.is_dir(follow_symlinks=False):
                s, label = size_of(e.path), e.name + "/"
            else:
                s, label = e.stat(follow_symlinks=False).st_size, e.name
        except OSError:
            continue
        total += s
        items.append((label, s))
    items.sort(key=lambda x: -x[1])
    return total, items[:8], partial[0]


def disk_report():
    seen, rows = set(), []
    cands = [os.getcwd(), "C:\\" if os.name == "nt" else "/", "/storage/emulated/0", "/sdcard"]
    for p in cands:
        try:
            if not os.path.exists(p):
                continue
            dev = os.stat(p).st_dev
            if dev in seen:
                continue
            seen.add(dev)
            du = shutil.disk_usage(p)
            rows.append((p, du.used, du.total, du.free))
        except OSError:
            continue
    return rows


def read_lines(path, n, tail, max_bytes=65536):
    """Return list baris. Raise ValueError('binary') untuk file biner."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if tail:
            f.seek(max(0, size - max_bytes))
        data = f.read(max_bytes)
    if b"\x00" in data[:4096]:
        raise ValueError("binary")
    lines = data.decode("utf-8", "ignore").splitlines()
    if tail:
        if size > max_bytes and lines:
            lines = lines[1:]   # baris pertama kemungkinan terpotong
        return lines[-n:]
    return lines[:n]


def file_hash(path, algo):
    h, size = hashlib.new(algo), 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def validate_text(path, text):
    low = path.lower()
    if low.endswith(".py"):
        try:
            compile(text, path, "exec")
        except SyntaxError as e:
            return f"{e.msg} (line {e.lineno})"
    elif low.endswith(".json"):
        try:
            json.loads(text)
        except ValueError as e:
            return str(e)[:80]
    return None


def atomic_write(path, text):
    tmp = path + ".fmtmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def backup_edit(path, fm_dir, keep=5):
    d = os.path.join(fm_dir, "backups", "edits")
    os.makedirs(d, exist_ok=True)
    name = os.path.basename(path)
    shutil.copy2(path, os.path.join(d, f"{name}.{time.strftime('%Y%m%d-%H%M%S')}.bak"))
    olds = sorted((f for f in os.listdir(d) if f.startswith(name + ".")), reverse=True)
    for f in olds[keep:]:
        try:
            os.remove(os.path.join(d, f))
        except OSError:
            pass


def prune_backups(directory, pattern, keep):
    files = sorted((os.path.join(directory, f) for f in os.listdir(directory) if fnmatch.fnmatch(f, pattern)),
                   key=os.path.getmtime, reverse=True)
    for f in files[keep:]:
        try:
            os.remove(f)
        except OSError:
            pass
    return min(len(files), keep)


def make_backup(backup_dir, full, keep):
    ts = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(backup_dir, exist_ok=True)
    out = os.path.join(backup_dir, f"bot-{ts}{'-full' if full else ''}.tar.gz")
    tmpdir = tempfile.mkdtemp(prefix="fmbak_")

    def no_cache(ti):
        return None if ("__pycache__" in ti.name or ti.name.endswith(".pyc")) else ti

    try:
        with tarfile.open(out, "w:gz") as tar:
            if os.path.isdir("data"):
                for fn in sorted(os.listdir("data")):
                    p = os.path.join("data", fn)
                    if not os.path.isfile(p):
                        continue
                    low = fn.lower()
                    if low.endswith((".db", ".sqlite", ".sqlite3")):
                        snap = os.path.join(tmpdir, fn)
                        try:   # salinan konsisten walau database sedang dipakai
                            src, dst = sqlite3.connect(p, timeout=10), sqlite3.connect(snap)
                            src.backup(dst)
                            dst.close()
                            src.close()
                        except Exception:
                            shutil.copy2(p, snap)
                        tar.add(snap, arcname="data/" + fn)
                    elif low.endswith((".txt", ".json")):
                        tar.add(p, arcname="data/" + fn)
            for d in ("plugins", "lang"):
                if os.path.isdir(d):
                    tar.add(d, arcname=d, filter=no_cache)
            if full and os.path.isfile("config.txt"):
                tar.add("config.txt", arcname="config.txt")
    except Exception:
        if os.path.exists(out):
            os.remove(out)
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    kept = prune_backups(backup_dir, "bot-*.tar.gz", keep)
    return out, kept


def plugin_backups(fm_dir, name):
    d = os.path.join(fm_dir, "backups", "plugins")
    if not os.path.isdir(d):
        return []
    return sorted((os.path.join(d, f) for f in os.listdir(d) if f.startswith(name + ".") and f.endswith(".py")),
                  reverse=True)


def save_plugin_backup(fm_dir, name, current_path, keep=10):
    d = os.path.join(fm_dir, "backups", "plugins")
    os.makedirs(d, exist_ok=True)
    shutil.copy2(current_path, os.path.join(d, f"{name}.{time.strftime('%Y%m%d-%H%M%S')}.py"))
    for old in plugin_backups(fm_dir, name)[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


async def fetch_limited(url, max_bytes, timeout=30):
    cfg = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=cfg, headers={"User-Agent": UA}) as s:
        async with s.get(url) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            if r.content_length and r.content_length > max_bytes:
                raise RuntimeError("too big")
            buf = bytearray()
            async for chunk in r.content.iter_chunked(65536):
                buf += chunk
                if len(buf) > max_bytes:
                    raise RuntimeError("too big")
            return bytes(buf)


async def download_to(url, dest, limit):
    part = dest + ".part"
    cfg = aiohttp.ClientTimeout(total=900, sock_connect=15, sock_read=30)
    size = 0
    try:
        async with aiohttp.ClientSession(timeout=cfg, headers={"User-Agent": UA}) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
                if r.content_length and r.content_length > limit:
                    raise RuntimeError("too big")
                with open(part, "wb") as f:
                    async for chunk in r.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > limit:
                            raise RuntimeError("too big")
                        f.write(chunk)
        os.replace(part, dest)
        part = None
        return size
    finally:
        if part and os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass


def register(bot):
    if getattr(bot, "fm", None) is None:
        logging.warning("[filetools] cmd_filemanager belum dimuat; plugin ini dilewati")
        return
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def F():
        return bot.fm

    bot.fm.add_messages(DEFAULT_MSG, LANG_MESSAGES)

    def T(lang, key, **kw):
        lang = str(lang or "id").lower()
        text = None
        for src in (LANG_MESSAGES.get(lang, {}), DEFAULT_MSG.get(lang, {}), LANG_MESSAGES.get("en", {}),
                    DEFAULT_MSG["en"], LANG_MESSAGES.get("id", {}), DEFAULT_MSG["id"]):
            text = src.get(key)
            if text:
                break
        if not text:
            return F().T(lang, key, **kw)
        try:
            return text.format(**kw)
        except Exception:
            return text

    def owner_only(func):
        cmd = func.__name__[4:] if func.__name__.startswith("cmd_") else func.__name__

        @functools.wraps(func)
        async def wrapper(sender, room, nick, is_private, args):
            # quiet=True: kata umum (find, head, edit, ...) tidak dibalas penolakan bila bukan owner
            return await bot.fm.guarded(cmd, func, sender, room, nick, is_private, args, quiet=True)
        return wrapper

    async def reply(sender, room, nick, is_private, text):
        await bot.reply_user(sender, room, text, is_private, nick=nick)

    def backup_dir():
        return os.path.join(F().FM_DIR, "backups")

    def keep_count():
        try:
            return max(1, min(60, int(F().cfg().get("backup_keep", BACKUP_KEEP_DEFAULT))))
        except (TypeError, ValueError):
            return BACKUP_KEEP_DEFAULT

    def target_path(sender, room, tokens):
        return F().resolve(" ".join(tokens), F().current_dir(sender, room))

    def need_file(path, lang):
        if not os.path.isfile(path):
            raise F().FmError("file_not_found")

    def guard_sensitive(path, is_private):
        if F().is_sensitive(path) and not is_private:
            raise F().FmError("err_sensitive_pm", name=os.path.basename(path))

    # ---------------- pencarian & penjelajahan ----------------
    @bot.command("find", "🔑 Master Bot")
    @owner_only
    async def cmd_find(sender, room, nick, is_private, args):
        """find <pattern> [folder]"""
        f, lang = F(), F().get_lang(sender, room)
        if not args:
            return await reply(sender, room, nick, is_private, T(lang, "find_usage"))
        cur = f.current_dir(sender, room)
        base = f.resolve(" ".join(args[1:]), cur) if len(args) > 1 else cur
        if not os.path.isdir(base):
            raise f.FmError("dir_not_found", path=base)
        results, truncated = await f.run(walk_find, base, args[0])
        if not results:
            return await reply(sender, room, nick, is_private, T(lang, "find_none", pattern=args[0]))
        lines = [T(lang, "find_header", count=len(results), pattern=args[0], base=base,
                   more=T(lang, "more") if truncated else "")]
        for rel, is_dir, size in results:
            lines.append(f"📁 {rel}/" if is_dir else f"📄 {rel} ({f.format_size(size)})")
        await reply(sender, room, nick, is_private, "\n".join(lines))

    @bot.command("grep", "🔑 Master Bot")
    @owner_only
    async def cmd_grep(sender, room, nick, is_private, args):
        """grep <text> [-p <path>]"""
        f, lang = F(), F().get_lang(sender, room)
        args = list(args)
        cur = f.current_dir(sender, room)
        if "-p" in args:
            i = args.index("-p")
            needle_tokens, path_tokens = args[:i], args[i + 1:]
        else:
            needle_tokens, path_tokens = args, []
        needle = " ".join(needle_tokens).strip()
        if not needle:
            return await reply(sender, room, nick, is_private, T(lang, "grep_usage"))
        target = f.resolve(" ".join(path_tokens), cur) if path_tokens else cur
        if not os.path.exists(target):
            raise f.FmError("file_not_found")
        if os.path.isfile(target):
            guard_sensitive(target, is_private)
        redact = f.redact
        matches, truncated = await f.run(walk_grep, target, needle, redact, f.is_sensitive)
        if not matches:
            return await reply(sender, room, nick, is_private, T(lang, "grep_none", pattern=needle))
        lines = [T(lang, "grep_header", count=len(matches), pattern=needle,
                   more=T(lang, "more") if truncated else "")]
        lines += [f"{rel}:{n}: {text}" for rel, n, text in matches]
        await reply(sender, room, nick, is_private, "\n".join(lines))

    @bot.command("tree", "🔑 Master Bot")
    @owner_only
    async def cmd_tree(sender, room, nick, is_private, args):
        """tree [folder] [depth]"""
        f = F()
        args = list(args)
        depth = 2
        if args and args[-1].isdigit():
            depth = max(1, min(4, int(args.pop())))
        base = target_path(sender, room, args) if args else f.current_dir(sender, room)
        if not os.path.isdir(base):
            raise f.FmError("dir_not_found", path=base)
        lines, truncated = await f.run(render_tree, base, depth)
        if truncated:
            lines.append("…")
        await reply(sender, room, nick, is_private, "\n".join(lines))

    @bot.command("du", "🔑 Master Bot")
    @owner_only
    async def cmd_du(sender, room, nick, is_private, args):
        """du [path]"""
        f, lang = F(), F().get_lang(sender, room)
        path = target_path(sender, room, args) if args else f.current_dir(sender, room)
        if not os.path.exists(path):
            raise f.FmError("file_not_found")
        total, items, partial = await f.run(dir_usage, path)
        lines = [T(lang, "du_header", path=path, total=f.format_size(total),
                   partial=T(lang, "du_partial") if partial else "")]
        lines += [f"{f.format_size(s):>9}  {name}" for name, s in items]
        await reply(sender, room, nick, is_private, "\n".join(lines))

    @bot.command("df", "🔑 Master Bot")
    @owner_only
    async def cmd_df(sender, room, nick, is_private, args):
        """df"""
        f, lang = F(), F().get_lang(sender, room)
        rows = await f.run(disk_report)
        lines = [T(lang, "df_header")]
        for p, used, total, free in rows:
            pct = (used / total * 100) if total else 0
            lines.append(f"{p}: {f.format_size(used)} / {f.format_size(total)} ({pct:.0f}%), "
                         f"{f.format_size(free)} free")
        await reply(sender, room, nick, is_private, "\n".join(lines))

    async def show_lines(sender, room, nick, is_private, args, tail):
        f, lang = F(), F().get_lang(sender, room)
        args = list(args)
        n = 15
        if len(args) > 1 and args[-1].isdigit():
            n = max(1, min(40, int(args.pop())))
        if not args:
            return await reply(sender, room, nick, is_private, T(lang, "tail_usage" if tail else "head_usage"))
        path = target_path(sender, room, args)
        need_file(path, lang)
        guard_sensitive(path, is_private)
        try:
            lines = await f.run(read_lines, path, n, tail)
        except ValueError:
            raise f.FmError("err_binary")
        text = "\n".join(l[:300] for l in lines)
        if f.should_redact(path):
            text = f.redact(text)
        await reply(sender, room, nick, is_private, (text or "(kosong)")[:3500])

    @bot.command("head", "🔑 Master Bot")
    @owner_only
    async def cmd_head(sender, room, nick, is_private, args):
        """head <file> [lines]"""
        await show_lines(sender, room, nick, is_private, args, False)

    @bot.command("tail", "🔑 Master Bot")
    @owner_only
    async def cmd_tail(sender, room, nick, is_private, args):
        """tail <file> [lines]"""
        await show_lines(sender, room, nick, is_private, args, True)

    @bot.command("hash", "🔑 Master Bot")
    @owner_only
    async def cmd_hash(sender, room, nick, is_private, args):
        """hash <file> [md5|sha1|sha256|sha512]"""
        f, lang = F(), F().get_lang(sender, room)
        args = list(args)
        algo = "sha256"
        if len(args) > 1 and args[-1].lower() in HASH_ALGOS:
            algo = args.pop().lower()
        if not args:
            return await reply(sender, room, nick, is_private, T(lang, "hash_usage"))
        path = target_path(sender, room, args)
        need_file(path, lang)
        digest, size = await f.run(file_hash, path, algo)
        await reply(sender, room, nick, is_private,
                    T(lang, "hash_result", algo=algo, name=os.path.basename(path), size=f.format_size(size),
                      digest=digest))

    # ---------------- menulis & mengedit ----------------
    def check_writable(path):
        if F().is_protected(path) or F().abspath(path) in F().protected_files():
            raise F().FmError("err_protected", name=os.path.basename(path))

    @bot.command("writefile", "🔑 Master Bot")
    @owner_only
    async def cmd_writefile(sender, room, nick, is_private, args):
        """writefile [-a] <file> <text>"""
        f, lang = F(), F().get_lang(sender, room)
        args = list(args)
        append = False
        if args and args[0] == "-a":
            append = True
            args = args[1:]
        if len(args) < 2:
            return await reply(sender, room, nick, is_private, T(lang, "write_usage"))
        path = f.resolve(args[0], f.current_dir(sender, room))
        text = " ".join(args[1:]).replace("\\n", "\n")
        if len(text) > MAX_WRITE_CHARS:
            raise f.FmError("write_too_big", max=MAX_WRITE_CHARS)
        check_writable(path)
        if os.path.isdir(path):
            raise f.FmError("err_not_file", name=os.path.basename(path))
        if not os.path.isdir(os.path.dirname(path)):
            raise f.FmError("dir_not_found", path=os.path.dirname(path))

        def work():
            exists = os.path.isfile(path)
            old = ""
            if exists:
                with open(path, "r", encoding="utf-8", newline="") as fh:
                    old = fh.read(EDIT_MAX_BYTES + 1)
                if len(old) > EDIT_MAX_BYTES:
                    raise ValueError("big")
            new = (old + text) if (append and exists) else text
            err = validate_text(path, new)
            if err:
                return err, 0
            if exists:
                backup_edit(path, f.FM_DIR)
            atomic_write(path, new)
            return None, len(new.encode("utf-8"))

        try:
            err, size = await f.run(work)
        except UnicodeDecodeError:
            raise f.FmError("err_not_text")
        if err:
            raise f.FmError("err_syntax", err=err)
        await reply(sender, room, nick, is_private, T(lang, "write_ok", name=os.path.basename(path),
                                                      size=f.format_size(size)))

    @bot.command("edit", "🔑 Master Bot")
    @owner_only
    async def cmd_edit(sender, room, nick, is_private, args):
        """edit <file> replace|line|insert|delete ..."""
        f, lang = F(), F().get_lang(sender, room)
        if len(args) < 3 and not (len(args) == 3):
            return await reply(sender, room, nick, is_private, T(lang, "edit_usage"))
        path = f.resolve(args[0], f.current_dir(sender, room))
        sub = args[1].lower()
        rest = list(args[2:])
        if sub not in ("replace", "line", "insert", "delete") or not rest:
            return await reply(sender, room, nick, is_private, T(lang, "edit_usage"))
        need_file(path, lang)
        check_writable(path)
        name = os.path.basename(path)

        if sub == "replace":
            joined = " ".join(rest).replace("\\n", "\n")
            if "=>" not in joined:
                return await reply(sender, room, nick, is_private, T(lang, "edit_usage"))
            old_s, new_s = (x.strip() for x in joined.split("=>", 1))
            if not old_s:
                return await reply(sender, room, nick, is_private, T(lang, "edit_usage"))
        else:
            if not rest[0].isdigit():
                return await reply(sender, room, nick, is_private, T(lang, "edit_usage"))
            n = int(rest[0])
            new_line = " ".join(rest[1:]).replace("\\n", "\n")
            if sub in ("line", "insert") and not new_line:
                return await reply(sender, room, nick, is_private, T(lang, "edit_usage"))

        def work():
            if os.path.getsize(path) > EDIT_MAX_BYTES:
                raise ValueError("big")
            with open(path, "r", encoding="utf-8", newline="") as fh:
                content = fh.read()
            if sub == "replace":
                count = content.count(old_s)
                if not count:
                    return ("missing", None, None)
                new_content, detail = content.replace(old_s, new_s), f"{count}×"
            else:
                lines = content.splitlines(True)
                total = len(lines)
                if sub == "insert":
                    if not 1 <= n <= total + 1:
                        return ("range", n, total)
                    if n == total + 1 and lines and not lines[-1].endswith("\n"):
                        lines[-1] += "\n"
                    lines.insert(n - 1, new_line + "\n")
                    detail = f"+1 line @{n}"
                else:
                    if not 1 <= n <= total:
                        return ("range", n, total)
                    if sub == "line":
                        eol = "\n" if lines[n - 1].endswith("\n") else ""
                        lines[n - 1] = new_line + eol
                        detail = f"line {n}"
                    else:
                        del lines[n - 1]
                        detail = f"-1 line @{n}"
                new_content = "".join(lines)
            err = validate_text(path, new_content)
            if err:
                return ("syntax", err, None)
            backup_edit(path, f.FM_DIR)
            atomic_write(path, new_content)
            return ("ok", detail, None)

        try:
            status, a, b = await f.run(work)
        except UnicodeDecodeError:
            raise f.FmError("err_not_text")
        except ValueError:
            raise f.FmError("err_too_big_up", mb=EDIT_MAX_BYTES >> 20 or 1)
        if status == "missing":
            raise f.FmError("edit_text_missing", name=name)
        if status == "range":
            raise f.FmError("edit_bad_line", n=a, total=b)
        if status == "syntax":
            raise f.FmError("err_syntax", err=a)
        await reply(sender, room, nick, is_private, T(lang, "edit_ok", name=name, detail=a))

    # ---------------- backup ----------------
    async def upload_to_pm(path, sender):
        xep = bot.plugin["xep_0363"] if "xep_0363" in bot.plugin else None
        if xep is None or not hasattr(xep, "upload_file"):
            raise F().FmError("upload_no_plugin")

        def read_all():
            with open(path, "rb") as fh:
                return fh.read()
        data = await F().run(read_all)
        res = await xep.upload_file(filename=Path(os.path.basename(path)), size=len(data),
                                    content_type="application/gzip", input_file=io.BytesIO(data), timeout=60)
        url = (res.get("url", "") if isinstance(res, dict) else str(res or "")).strip()
        if not url.lower().startswith(("http://", "https://")):
            raise F().FmError("upload_no_url")
        bot.make_message(mto=sender, mbody=url, mtype="chat").send()

    @bot.command("backup", "🔑 Master Bot")
    @owner_only
    async def cmd_backup(sender, room, nick, is_private, args):
        """backup [full] [send] | backup auto <interval|off>"""
        f, lang = F(), F().get_lang(sender, room)
        tokens = [a.lower() for a in args]
        say = lambda text: reply(sender, room, nick, is_private, text)

        if tokens and tokens[0] == "auto":
            if len(tokens) < 2:
                iv = int(f.cfg().get("backup_interval", 0) or 0)
                state = (T(lang, "backup_auto_set", every=fmt_interval(iv), keep=keep_count()) if iv
                         else T(lang, "off"))
                return await say(T(lang, "backup_auto_status", state=state))
            if tokens[1] in ("off", "0", "mati"):
                f.cfg_set("backup_interval", None)
                return await say(T(lang, "backup_auto_off"))
            secs = parse_interval(tokens[1])
            if secs is None or not 3600 <= secs <= 30 * 86400:
                return await say(T(lang, "backup_interval_bad", min="1h", max="30d"))
            f.cfg_set("backup_interval", secs)
            f.cfg_set("backup_last", time.time())
            return await say(T(lang, "backup_auto_set", every=fmt_interval(secs), keep=keep_count()))

        unknown = [t for t in tokens if t not in ("full", "send")]
        if unknown:
            return await say(T(lang, "backup_usage"))
        full, send = "full" in tokens, "send" in tokens
        if send and full:
            raise f.FmError("backup_full_send", dir=backup_dir())
        if send and not is_private:
            raise f.FmError("backup_pm_only")

        await say(T(lang, "backup_working"))
        path, kept = await f.run(make_backup, backup_dir(), full, keep_count())
        size = os.path.getsize(path)
        await say(T(lang, "backup_ok", path=path, size=f.format_size(size), count=kept))
        if send:
            if size > BACKUP_SEND_MAX:
                raise f.FmError("backup_too_big", size=f.format_size(size), dir=backup_dir())
            await upload_to_pm(path, sender)
            await say(T(lang, "backup_sent"))

    async def backup_loop():
        await asyncio.sleep(180)
        while True:
            try:
                cfg = F().cfg()
                iv = int(cfg.get("backup_interval", 0) or 0)
                if iv > 0 and time.time() - float(cfg.get("backup_last", 0) or 0) >= iv:
                    path, _ = await F().run(make_backup, backup_dir(), False, keep_count())
                    F().cfg_set("backup_last", time.time())
                    logging.info(f"[filetools] cadangan otomatis: {path}")
                    F().audit("system", None, "backup-auto", os.path.basename(path), "ok")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.warning(f"[filetools] cadangan otomatis gagal: {type(e).__name__}: {e}")
            await asyncio.sleep(600)

    async def start_backup_task(event):
        if not getattr(bot, "is_primary_jid", True):
            return
        t = getattr(bot, "_ft_backup_task", None)
        if t is None or t.done():
            bot._ft_backup_task = asyncio.ensure_future(backup_loop())

    bot.add_event_handler("session_start", start_backup_task)

    # ---------------- deploy & rollback ----------------
    async def reload_name(name, lang):
        """(ok, pesan): ok None = reload tidak tersedia/tidak berlaku."""
        if name in UNSAFE_RELOAD:
            return None, T(lang, "deploy_restart_needed")
        fn = getattr(bot, "reload_plugin", None)
        if fn is None:
            return None, T(lang, "deploy_no_reload")
        return await fn(name, lang)

    def norm_plugin(token):
        s = os.path.basename(str(token or "").strip().lower().replace("\\", "/"))
        if s.endswith(".py"):
            s = s[:-3]
        return s if re.fullmatch(r"[a-z0-9_]{1,40}", s) and not s.startswith("__") else ""

    @bot.command("deploy", "🔑 Master Bot")
    @owner_only
    async def cmd_deploy(sender, room, nick, is_private, args):
        """deploy <url> [name] [sha256=<hex>]"""
        f, lang = F(), F().get_lang(sender, room)
        if not args or not args[0].lower().startswith(("http://", "https://")):
            return await reply(sender, room, nick, is_private, T(lang, "deploy_usage"))
        url, name_arg, sha = args[0], None, None
        for a in args[1:]:
            if a.lower().startswith(("sha256=", "sha256:")):
                sha = a.split("=", 1)[-1].split(":", 1)[-1].strip().lower()
            else:
                name_arg = a
        name = norm_plugin(name_arg or os.path.basename(urlsplit(url).path))
        if not name:
            raise f.FmError("deploy_bad_name")
        await reply(sender, room, nick, is_private, T(lang, "deploy_working"))
        data = await fetch_limited(url, DEPLOY_MAX_BYTES)
        digest = hashlib.sha256(data).hexdigest()
        if sha and digest != sha:
            raise f.FmError("deploy_sha_mismatch")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise f.FmError("deploy_not_text")
        path = os.path.join(PLUGINS_DIR, f"{name}.py")
        err = validate_text(path, text)
        if err:
            raise f.FmError("err_syntax", err=err)
        if "def register(" not in text:
            raise f.FmError("deploy_no_register")

        existed = os.path.isfile(path)
        if existed:
            with open(path, "rb") as fh:
                if hashlib.sha256(fh.read()).hexdigest() == digest:
                    return await reply(sender, room, nick, is_private, T(lang, "deploy_same", name=name))
            await f.run(save_plugin_backup, f.FM_DIR, name, path)
        await f.run(atomic_write, path, text)

        ok, msg = await reload_name(name, lang)
        if ok is False:   # gagal dimuat: kembalikan versi lama
            if existed:
                prev = plugin_backups(f.FM_DIR, name)
                if prev:
                    shutil.copyfile(prev[0], path)
            else:
                os.remove(path)
            again = ""
            if existed:
                ok2, _ = await reload_name(name, lang)
                again = T(lang, "deploy_again") if ok2 else ""
            raise f.FmError("deploy_rolled_back", name=name, err=msg[:160], again=again)
        info = T(lang, "deploy_reloaded") if ok else msg
        await reply(sender, room, nick, is_private,
                    T(lang, "deploy_ok", name=name, size=f.format_size(len(data)), sha=digest[:12], reload=info))

    @bot.command("rollback", "🔑 Master Bot")
    @owner_only
    async def cmd_rollback(sender, room, nick, is_private, args):
        """rollback <plugin> [number|list]"""
        f, lang = F(), F().get_lang(sender, room)
        if not args:
            return await reply(sender, room, nick, is_private, T(lang, "rollback_usage"))
        name = norm_plugin(args[0])
        if not name:
            raise f.FmError("deploy_bad_name")
        backups = plugin_backups(f.FM_DIR, name)
        if not backups:
            raise f.FmError("rollback_none", name=name)
        pick = args[1].lower() if len(args) > 1 else "1"
        if pick == "list":
            items = "\n".join(f"{i}. {os.path.basename(b)[len(name) + 1:-3]}" for i, b in enumerate(backups, 1))
            return await reply(sender, room, nick, is_private, T(lang, "rollback_list", name=name, items=items))
        if not pick.isdigit() or not 1 <= int(pick) <= len(backups):
            return await reply(sender, room, nick, is_private, T(lang, "rollback_usage"))
        chosen = backups[int(pick) - 1]
        when = os.path.basename(chosen)[len(name) + 1:-3]
        with open(chosen, "r", encoding="utf-8") as fh:
            text = fh.read()
        err = validate_text(chosen, text)
        if err:
            raise f.FmError("err_syntax", err=err)
        path = os.path.join(PLUGINS_DIR, f"{name}.py")
        if os.path.isfile(path):
            await f.run(save_plugin_backup, f.FM_DIR, name, path)   # versi sekarang ikut dicadangkan
        await f.run(atomic_write, path, text)
        ok, msg = await reload_name(name, lang)
        info = T(lang, "deploy_reloaded") if ok else msg
        await reply(sender, room, nick, is_private, T(lang, "rollback_ok", name=name, when=when, reload=info))

    # ---------------- inbox: simpan file yang dikirim lewat PM ----------------
    def inbox_on():
        return bool(F().cfg().get("inbox", True))

    @bot.command("inbox", "🔑 Master Bot")
    @owner_only
    async def cmd_inbox(sender, room, nick, is_private, args):
        """inbox on|off|status"""
        f, lang = F(), F().get_lang(sender, room)
        sub = args[0].lower() if args else "status"
        if sub in ("on", "off"):
            f.cfg_set("inbox", sub == "on")
        elif sub != "status":
            return await reply(sender, room, nick, is_private, T(lang, "inbox_usage"))
        await reply(sender, room, nick, is_private,
                    T(lang, "inbox_state", state=T(lang, "on" if inbox_on() else "off")))

    def inbox_url(msg):
        urls = []
        xml = getattr(msg, "xml", None)
        if xml is not None:
            for el in xml.iter():
                if el.tag == NS_OOB and (el.text or "").strip():
                    urls.append(el.text.strip())
        body = (msg.get("body", "") or "").strip()
        for u in URL_RE.findall(body):
            if body == u:   # pesan berisi tautan saja (bukan perintah seperti 'download <url>')
                urls.append(u)
        for u in urls:
            if os.path.splitext(urlsplit(u).path)[1].lower() in INBOX_EXT:
                return u
        return None

    async def on_inbox_message(msg):
        try:
            if msg.get("type") not in ("chat", "normal") or not inbox_on():
                return
            xml = getattr(msg, "xml", None)
            if xml is not None and (xml.find("{urn:xmpp:delay}delay") is not None
                                    or xml.find("{jabber:x:delay}x") is not None):
                return
            sender = str(msg.get("from", ""))
            if not sender or not await F().is_config_owner(sender, None, None):
                return
            url = inbox_url(msg)
            if not url:
                return
            f, lang = F(), F().get_lang(sender, None)
            name = f.safe_filename(os.path.basename(urlsplit(url).path), "file")
            folder = os.path.join(f.FM_DIR, "inbox")
            os.makedirs(folder, exist_ok=True)
            dest, n = os.path.join(folder, name), 1
            while os.path.exists(dest):
                base, ext = os.path.splitext(name)
                dest = os.path.join(folder, f"{base}_{n}{ext}")
                n += 1
            try:
                size = await download_to(url, dest, f.max_download_mb() * 1024 * 1024)
            except Exception as e:
                f.audit(sender.split("/")[0], None, "inbox", name, f"error:{type(e).__name__}")
                return await bot.reply_user(sender, None, T(lang, "inbox_fail", err=str(e)[:100]), True)
            f.audit(sender.split("/")[0], None, "inbox", name, "ok")
            await bot.reply_user(sender, None, T(lang, "inbox_saved", path=dest, size=f.format_size(size)), True)
        except Exception as e:
            logging.info(f"[filetools] inbox: {type(e).__name__}")

    bot.add_event_handler("message", on_inbox_message)
