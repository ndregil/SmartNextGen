# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org
#
# File manager untuk owner (DEFAULT_OWNERS di config.txt).
#
# Perintah dasar : filemanager cd back catfile mkdir download upload deletefile renamefile
#                  movefile copyfile zip unzip tar untar
# Perintah baru  : trash [empty|days <n>] | undelete <nomor|id> | fmroot ... | audit [n]
# Perintah lanjutan (find, grep, tree, du, df, head, tail, hash, writefile, edit, backup,
# deploy, rollback, inbox) ada di plugins/cmd_filetools.py dan memakai fungsi dari plugin ini
# lewat bot.fm.
#
# Keamanan:
#   - catfile/head/tail/grep menyamarkan nilai rahasia (password, token, API key) dan file
#     sensitif (config.txt, *.db, dst.) hanya boleh dibuka lewat PM.
#   - config.txt dan data/*.db dilindungi dari hapus/pindah/ganti nama/tulis.
#   - fmroot: batasi file manager ke folder tertentu (bawaan: tanpa batas).
#   - deletefile memindahkan ke tempat sampah (pulihkan: undelete); deletefile -f = permanen.
#   - unzip/untar memeriksa isi arsip (path keluar folder, link berbahaya, ukuran raksasa).
#   - operasi berat berjalan di thread terpisah sehingga bot tidak macet.
#   - setiap operasi dicatat di data/filemanager-audit.jsonl.

import asyncio
import functools
import io
import json
import logging
import os
import random
import re
import shutil
import stat
import sys
import tarfile
import time
import types
import zipfile
from datetime import datetime
from pathlib import Path

import aiohttp

FM_DIR = "filemanager"
TRASH_DIR = os.path.join(FM_DIR, ".trash")
DOWNLOAD_DIR = os.path.join(FM_DIR, "downloads")
CFG_PATH = os.path.join(FM_DIR, "fm_settings.json")
AUDIT_FILE = os.path.join("data", "filemanager-audit.jsonl")
AUDIT_MAX_BYTES = 2 * 1024 * 1024

TRASH_DAYS_DEFAULT = 7
TRASH_MAX_MB_DEFAULT = 500          # item lebih besar tidak masuk tempat sampah (pakai deletefile -f)
MAX_DOWNLOAD_MB_DEFAULT = 200
UPLOAD_MAX_BYTES = 100 * 1024 * 1024
MAX_EXTRACT_BYTES = 1 << 30         # 1 GB isi arsip
MAX_EXTRACT_FILES = 20000
UA = "Mozilla/5.0 (compatible; SmartNG-FileManager/2.0)"

SENSITIVE_NAMES = {"config.txt", ".env", "config.ini", "secrets.json", "credentials.json"}
SENSITIVE_EXT = (".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx")
SECRET_WORDS = ("pass", "secret", "token", "key", "auth", "cookie", "session", "credential")
REDACT_NAME_HINTS = ("config", "secret", "token", "cred", "pass", "auth")
REDACT_EXT = (".ini", ".cfg", ".conf", ".env", ".properties")

_KV_RE = re.compile(r"^(\s*[\"']?)([A-Za-z0-9_.\-]+)([\"']?\s*[=:]\s*)(.+)$")

DEFAULT_MSG = {
    "id": {
        "err_outside": "Akses ditolak: lokasi itu di luar folder yang diizinkan (lihat: fmroot).",
        "err_protected": "Akses ditolak: {name} adalah file/folder inti bot dan dilindungi.",
        "err_sensitive_pm": "Akses ditolak: file sensitif ({name}) hanya boleh dibuka lewat PM.",
        "err_generic": "Gagal: {err}",
        "err_binary": "Ini file biner, tidak bisa ditampilkan sebagai teks.",
        "err_exists": "Gagal: {name} sudah ada di tujuan.",
        "err_name_invalid": "Nama tidak valid (tidak boleh memuat / atau \\).",
        "err_too_big_dl": "Gagal: ukuran unduhan melebihi batas {mb} MB.",
        "err_too_big_up": "Gagal: file terlalu besar untuk diunggah (maks {mb} MB).",
        "err_archive_big": "Gagal: isi arsip terlalu besar atau terlalu banyak file (batas {mb} MB / {n} file).",
        "extract_skipped": "⚠️ {n} entri dilewati karena tidak aman atau dilindungi.",
        "set_ok": "Berhasil: {name} = {value}",
        "trash_moved": "Berhasil memindahkan {name} ke tempat sampah (id: {id}). Pulihkan dengan: undelete {id}",
        "trash_too_big": "Gagal: {name} berukuran {mb} MB, terlalu besar untuk tempat sampah (maks {max} MB). Gunakan: deletefile -f {name}",
        "trash_header": "🗑 Tempat sampah ({count} item, dibersihkan otomatis setelah {days} hari):",
        "trash_item": "{n}. {name} ({size}) — {age} lalu [{id}]",
        "trash_empty_list": "Tempat sampah kosong.",
        "trash_emptied": "Berhasil mengosongkan tempat sampah ({count} item, {size}).",
        "trash_usage": "Pemakaian: trash | trash empty | trash days <1-90>",
        "undelete_usage": "Pemakaian: undelete <nomor atau id>  (lihat daftar: trash)",
        "undelete_not_found": "Item itu tidak ditemukan di tempat sampah.",
        "undelete_ok": "Berhasil dipulihkan ke: {dest}",
        "fmroot_usage": "Pemakaian: fmroot | fmroot add <folder> | fmroot del <folder> | fmroot clear",
        "fmroot_none": "Tidak ada pembatasan folder (semua lokasi boleh diakses).",
        "fmroot_list": "Folder yang diizinkan:\n{roots}",
        "fmroot_added": "Berhasil menambah folder yang diizinkan: {path}",
        "fmroot_removed": "Berhasil menghapus dari daftar: {path}",
        "fmroot_cleared": "Berhasil menghapus semua pembatasan folder.",
        "fmroot_not_dir": "Gagal: {path} bukan folder.",
        "fmroot_not_listed": "Folder itu tidak ada dalam daftar.",
        "audit_empty": "Belum ada catatan operasi.",
        "audit_header": "📜 Catatan operasi terakhir ({count}):",
        "help_extra": ("➕ Tambahan:\n🗑 trash, undelete <id> — tempat sampah\n🔒 fmroot — batasi folder | 📜 audit [n] — log operasi\n"
                       "🔎 find, grep, tree, du, df, head, tail, hash\n✏️ writefile, edit | 💾 backup [full|send|auto]\n"
                       "🚀 deploy <url>, rollback <plugin> | 📥 inbox on|off"),
    },
    "en": {
        "err_outside": "Access denied: that location is outside the allowed folders (see: fmroot).",
        "err_protected": "Access denied: {name} is a core bot file/folder and is protected.",
        "err_sensitive_pm": "Access denied: sensitive file ({name}) can only be opened in a private chat.",
        "err_generic": "Failed: {err}",
        "err_binary": "This is a binary file and cannot be shown as text.",
        "err_exists": "Failed: {name} already exists at the destination.",
        "err_name_invalid": "Invalid name (must not contain / or \\).",
        "err_too_big_dl": "Failed: the download exceeds the {mb} MB limit.",
        "err_too_big_up": "Failed: the file is too large to upload (max {mb} MB).",
        "err_archive_big": "Failed: the archive is too large or has too many files (limit {mb} MB / {n} files).",
        "extract_skipped": "⚠️ {n} entries were skipped because they were unsafe or protected.",
        "set_ok": "Successfully set: {name} = {value}",
        "trash_moved": "Successfully moved {name} to the trash (id: {id}). Restore with: undelete {id}",
        "trash_too_big": "Failed: {name} is {mb} MB, too large for the trash (max {max} MB). Use: deletefile -f {name}",
        "trash_header": "🗑 Trash ({count} items, cleaned automatically after {days} days):",
        "trash_item": "{n}. {name} ({size}) — {age} ago [{id}]",
        "trash_empty_list": "The trash is empty.",
        "trash_emptied": "Successfully emptied the trash ({count} items, {size}).",
        "trash_usage": "Usage: trash | trash empty | trash days <1-90>",
        "undelete_usage": "Usage: undelete <number or id>  (see the list: trash)",
        "undelete_not_found": "That item was not found in the trash.",
        "undelete_ok": "Successfully restored to: {dest}",
        "fmroot_usage": "Usage: fmroot | fmroot add <folder> | fmroot del <folder> | fmroot clear",
        "fmroot_none": "No folder restriction (every location is accessible).",
        "fmroot_list": "Allowed folders:\n{roots}",
        "fmroot_added": "Successfully added allowed folder: {path}",
        "fmroot_removed": "Successfully removed from the list: {path}",
        "fmroot_cleared": "Successfully removed all folder restrictions.",
        "fmroot_not_dir": "Failed: {path} is not a folder.",
        "fmroot_not_listed": "That folder is not in the list.",
        "audit_empty": "No operations logged yet.",
        "audit_header": "📜 Latest logged operations ({count}):",
        "help_extra": ("➕ Extras:\n🗑 trash, undelete <id> — trash bin\n🔒 fmroot — restrict folders | 📜 audit [n] — operation log\n"
                       "🔎 find, grep, tree, du, df, head, tail, hash\n✏️ writefile, edit | 💾 backup [full|send|auto]\n"
                       "🚀 deploy <url>, rollback <plugin> | 📥 inbox on|off"),
    },
}


_EXTRA = globals().get("_EXTRA") or {"default": {}, "lang": {}}   # tetap ada saat plugin di-reload


def add_messages(default_msg, lang_msgs):
    """Daftarkan pesan plugin lain agar galat FmError(key) dari plugin itu bisa diterjemahkan."""
    for code, d in (default_msg or {}).items():
        _EXTRA["default"].setdefault(code, {}).update(d)
    for code, d in (lang_msgs or {}).items():
        _EXTRA["lang"].setdefault(code, {}).update(d)


class FmError(Exception):
    """Galat terduga: key = kunci pesan, kw = isian pesan."""
    def __init__(self, key, **kw):
        super().__init__(key)
        self.key = key
        self.kw = kw


class FmAccessError(FmError):
    def __init__(self, path=""):
        super().__init__("err_outside", path=path)


# ------------------------------------------------------------------
# Pengaturan bersama (file JSON, dipakai semua akun jid1..jid3)
# ------------------------------------------------------------------
_cfg_cache = {"mtime": None, "data": {}}


def fm_cfg():
    try:
        mt = os.path.getmtime(CFG_PATH)
    except OSError:
        return {}
    if _cfg_cache["mtime"] != mt:
        try:
            with open(CFG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        _cfg_cache["mtime"] = mt
        _cfg_cache["data"] = data
    return _cfg_cache["data"]


def fm_set(key, value):
    data = dict(fm_cfg())
    if value is None:
        data.pop(key, None)
    else:
        data[key] = value
    os.makedirs(FM_DIR, exist_ok=True)
    tmp = CFG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CFG_PATH)
    _cfg_cache["mtime"] = None


def _int_cfg(key, default, lo, hi):
    try:
        return max(lo, min(hi, int(fm_cfg().get(key, default))))
    except (TypeError, ValueError):
        return default


def trash_days():
    return _int_cfg("trash_days", TRASH_DAYS_DEFAULT, 1, 90)


def trash_max_mb():
    return _int_cfg("trash_max_mb", TRASH_MAX_MB_DEFAULT, 1, 100000)


def max_download_mb():
    return _int_cfg("max_download_mb", MAX_DOWNLOAD_MB_DEFAULT, 1, 5000)


# ------------------------------------------------------------------
# Perlindungan path
# ------------------------------------------------------------------
def _abs(p):
    return os.path.realpath(os.path.abspath(p))


def _nc(p):
    """Path absolut + normcase: untuk PERBANDINGAN (Windows tidak peka huruf besar/kecil)."""
    return os.path.normcase(_abs(p))


def _under(base, target):
    """True bila target sama dengan base atau berada di bawahnya (aman untuk base '/')."""
    base, target = os.path.normcase(base), os.path.normcase(target)
    return target == base or target.startswith(base.rstrip(os.sep) + os.sep)


def _inside(base, target):
    return _under(_abs(base), _abs(target))


def protected_files():
    files = {_nc("config.txt")}
    try:
        for f in os.listdir("data"):
            if f.lower().endswith((".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite", ".sqlite3")):
                files.add(_nc(os.path.join("data", f)))
    except OSError:
        pass
    return files


def protected_dirs():
    return {_nc(d) for d in ("data", "plugins", "lang", FM_DIR)}


def is_protected(path):
    """True bila path adalah file/folder inti bot, atau folder yang memuatnya (mis. folder bot, '/')."""
    p = _nc(path)
    for f in protected_files():
        if _under(p, f):
            return True
    return p in protected_dirs()


def is_sensitive(path):
    name = os.path.basename(str(path)).lower()
    return name in SENSITIVE_NAMES or name.endswith(SENSITIVE_EXT) or _nc(path) in protected_files()


def should_redact(path):
    name = os.path.basename(str(path)).lower()
    return (is_sensitive(path) or name.endswith(REDACT_EXT)
            or any(h in name for h in REDACT_NAME_HINTS))


def redact_text(text):
    """Samarkan nilai pada baris KUNCI=NILAI yang kuncinya terdengar rahasia (password, token, key, ...)."""
    out = []
    for line in str(text).splitlines(True):
        body = line.rstrip("\r\n")
        eol = line[len(body):]
        m = _KV_RE.match(body)
        if m and not body.lstrip().startswith("#") and any(w in m.group(2).lower() for w in SECRET_WORDS):
            out.append(f"{m.group(1)}{m.group(2)}{m.group(3)}***{eol}")
        else:
            out.append(line)
    return "".join(out)


def get_roots():
    roots = fm_cfg().get("roots") or []
    return [r for r in roots if isinstance(r, str)]


def check_allowed(path):
    roots = get_roots()
    if not roots:
        return
    p = _abs(path)
    if any(_under(r, p) for r in roots):
        return
    raise FmAccessError(path)


_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def safe_filename(name, default="file"):
    name = os.path.basename(str(name or "").replace("\\", "/")).strip().strip(".")
    name = re.sub(r"[^\w.\-+ ()\[\]]", "_", name, flags=re.UNICODE)[:100].strip().rstrip(". ")
    if name.split(".")[0].strip().upper() in _WIN_RESERVED:
        name = "_" + name
    return name or default


def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def fmt_age(secs):
    secs = int(max(0, secs))
    if secs < 90:
        return f"{secs}s"
    if secs < 5400:
        return f"{secs // 60}m"
    if secs < 129600:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


# ------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------
def audit(who, room, cmd, args_text, result):
    try:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        if os.path.exists(AUDIT_FILE) and os.path.getsize(AUDIT_FILE) > AUDIT_MAX_BYTES:
            os.replace(AUDIT_FILE, AUDIT_FILE + ".1")
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "who": who, "room": room or "pm",
               "cmd": cmd, "args": args_text[:120], "result": result}
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def summarize_args(cmd, args):
    if cmd in ("writefile", "edit"):
        first = next((a for a in args if not a.startswith("-")), "")
        return f"{first} (isi disembunyikan)"
    s = " ".join(args)
    s = re.sub(r"(https?://[^\s?#]+)[?#]\S*", r"\1?…", s)
    return s[:120]


def read_audit_tail(n):
    try:
        size = os.path.getsize(AUDIT_FILE)
        with open(AUDIT_FILE, "rb") as f:
            f.seek(max(0, size - 65536))
            data = f.read().decode("utf-8", "ignore")
    except OSError:
        return []
    recs = []
    for line in data.splitlines()[-n:]:
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    return recs


# ------------------------------------------------------------------
# Tempat sampah
# ------------------------------------------------------------------
def path_size(p, deadline=15.0):
    if os.path.islink(p) or os.path.isfile(p):
        try:
            return os.lstat(p).st_size
        except OSError:
            return 0
    total, t0 = 0, time.time()
    for root, dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
        if time.time() - t0 > deadline:
            break
    return total


def _force_writable(func, path, _exc=None):
    """Handler rmtree: cabut atribut read-only (umum di Windows, mis. folder .git) lalu ulangi."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def rmtree_force(p, ignore_errors=False):
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(p, onexc=_force_writable)
        else:
            shutil.rmtree(p, onerror=_force_writable)
    except Exception:
        if not ignore_errors:
            raise


def permanent_delete(p):
    if os.path.islink(p) or os.path.isfile(p):
        try:
            os.remove(p)
        except PermissionError:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
            os.remove(p)
    else:
        rmtree_force(p)


def trash_index():
    items = []
    if not os.path.isdir(TRASH_DIR):
        return items
    for tid in os.listdir(TRASH_DIR):
        d = os.path.join(TRASH_DIR, tid)
        try:
            with open(os.path.join(d, "meta.json"), "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        meta["id"] = tid
        items.append(meta)
    items.sort(key=lambda m: m.get("ts", 0), reverse=True)
    return items


def trash_put(path, who, size=0):
    p = os.path.abspath(path)
    name = os.path.basename(p.rstrip(os.sep)) or "item"
    tid = time.strftime("%Y%m%d-%H%M%S") + f"-{random.randint(0, 0xfff):03x}"
    d = os.path.join(TRASH_DIR, tid)
    os.makedirs(d)
    try:
        shutil.move(p, os.path.join(d, name))
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump({"orig": p, "name": name, "ts": time.time(), "size": size, "by": who}, f, ensure_ascii=False)
    except Exception:
        rmtree_force(d, ignore_errors=True)
        raise
    return tid


def trash_restore(item):
    d = os.path.join(TRASH_DIR, item["id"])
    src = os.path.join(d, item["name"])
    dest = item["orig"]
    check_allowed(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.lexists(dest):
        base, ext = os.path.splitext(dest)
        n = 1
        while os.path.lexists(f"{base}.restored{n}{ext}"):
            n += 1
        dest = f"{base}.restored{n}{ext}"
    shutil.move(src, dest)
    rmtree_force(d, ignore_errors=True)
    return dest


def trash_purge(days):
    """Hapus item tempat sampah lebih lama dari 'days' hari (0 = semuanya). Return (jumlah, ukuran)."""
    count, size = 0, 0
    cutoff = time.time() - days * 86400
    for item in trash_index():
        if days and item.get("ts", 0) > cutoff:
            continue
        rmtree_force(os.path.join(TRASH_DIR, item["id"]), ignore_errors=True)
        count += 1
        size += int(item.get("size", 0) or 0)
    if os.path.isdir(TRASH_DIR):   # sisa folder rusak (tanpa meta) yang sudah lama
        for tid in os.listdir(TRASH_DIR):
            d = os.path.join(TRASH_DIR, tid)
            if not os.path.exists(os.path.join(d, "meta.json")) and time.time() - os.path.getmtime(d) > 86400:
                rmtree_force(d, ignore_errors=True)
    return count, size


# ------------------------------------------------------------------
# Arsip (aman)
# ------------------------------------------------------------------
def make_zip(src_path, out_path):
    out_abs = _nc(out_path)
    skipped = 0
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if os.path.isdir(src_path):
            root_len = len(os.path.dirname(src_path))
            for root, dirs, files in os.walk(src_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if _nc(file_path) == out_abs:
                        continue
                    try:
                        zipf.write(file_path, file_path[root_len:].lstrip(os.sep))
                    except OSError:
                        skipped += 1
        else:
            zipf.write(src_path, os.path.basename(src_path))
    return skipped


def make_tar(src_path, out_path):
    out_abs = _nc(out_path)
    mode = 'w:gz' if (out_path.endswith('.gz') or out_path.endswith('.tgz')) else 'w'

    def skip_self(ti):
        return None if _nc(os.path.join(os.path.dirname(src_path), ti.name)) == out_abs else ti

    with tarfile.open(out_path, mode) as tar:
        tar.add(src_path, arcname=os.path.basename(src_path), filter=skip_self)


def safe_unzip(zip_path, dest):
    protected = protected_files()
    count = skipped = 0
    with zipfile.ZipFile(zip_path, 'r') as zf:
        infos = zf.infolist()
        if len(infos) > MAX_EXTRACT_FILES or sum(i.file_size for i in infos) > MAX_EXTRACT_BYTES:
            raise FmError("err_archive_big", mb=MAX_EXTRACT_BYTES >> 20, n=MAX_EXTRACT_FILES)
        for info in infos:
            target = os.path.join(dest, info.filename)
            if not _inside(dest, target) or _nc(target) in protected:
                skipped += 1
                continue
            zf.extract(info, dest)
            count += 1
    return count, skipped


def safe_untar(tar_path, dest):
    protected = protected_files()
    skipped, total = 0, 0
    with tarfile.open(tar_path, 'r:*') as tar:
        members = []
        for m in tar:
            total += max(0, m.size)
            if len(members) >= MAX_EXTRACT_FILES or total > MAX_EXTRACT_BYTES:
                raise FmError("err_archive_big", mb=MAX_EXTRACT_BYTES >> 20, n=MAX_EXTRACT_FILES)
            target = os.path.join(dest, m.name)
            ok = _inside(dest, target) and not (m.isdev() or m.isfifo())
            if ok and m.issym():
                ok = _inside(dest, os.path.join(os.path.dirname(target), m.linkname))
            elif ok and m.islnk():
                ok = _inside(dest, os.path.join(dest, m.linkname))
            if ok and _nc(target) in protected:
                ok = False
            if ok:
                members.append(m)
            else:
                skipped += 1
        try:
            tar.extractall(dest, members=members, filter="data")
        except TypeError:   # Python lama tanpa parameter filter
            tar.extractall(dest, members=members)
    return len(members), skipped


# ------------------------------------------------------------------
# Pencarian path yang dibatasi (tidak lagi menyapu seluruh penyimpanan)
# ------------------------------------------------------------------
def _find_by_name(name, dirs, max_depth=3, max_visit=4000):
    low = name.lower()
    visited = 0
    for base in dirs:
        if not base or not os.path.isdir(base):
            continue
        base_depth = base.rstrip(os.sep).count(os.sep)
        for root, dnames, fnames in os.walk(base):
            depth = root.rstrip(os.sep).count(os.sep) - base_depth
            dnames[:] = [d for d in dnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
            if depth >= max_depth:
                dnames[:] = []
            for n in fnames + dnames:
                visited += 1
                if visited > max_visit:
                    return None
                if n.lower() == low:
                    return os.path.abspath(os.path.join(root, n))
    return None


def _resolve_raw(path_str, current_base=None):
    if not path_str or path_str.strip() == "":
        return current_base if current_base and os.path.exists(current_base) else os.getcwd()

    path_str = path_str.strip().strip('"\'')

    if os.name == 'nt' and re.fullmatch(r"[A-Za-z]:", path_str):
        return path_str.upper() + os.sep   # "d:" = akar drive D, bukan folder aktif drive itu

    if path_str.lower() in ["~", "root", "home", "storage", "/"]:
        if os.name == 'nt':
            if path_str.lower() in ("~", "home"):
                return os.path.expanduser("~")
            drive = os.path.splitdrive(os.getcwd())[0]
            return (drive or "C:") + os.sep
        android_storage = "/storage/emulated/0"
        if os.path.exists(android_storage):
            return android_storage
        return "/"

    cleaned_path = path_str
    if os.name != 'nt' and cleaned_path.startswith("storage/"):
        cleaned_path = "/" + cleaned_path

    if current_base and not os.path.isabs(cleaned_path):
        combined_path = os.path.abspath(os.path.join(current_base, cleaned_path))
        if os.path.exists(combined_path):
            return combined_path

    if os.path.exists(cleaned_path):
        return os.path.abspath(cleaned_path)

    cwd_path = os.path.join(os.getcwd(), path_str)
    if os.path.exists(cwd_path):
        return os.path.abspath(cwd_path)

    found = _find_by_name(os.path.basename(path_str), [current_base, os.getcwd(), os.path.join(os.getcwd(), FM_DIR)])
    if found:
        return found
    return os.path.abspath(cleaned_path)


def resolve_path(path_str, current_base=None):
    p = _resolve_raw(path_str, current_base)
    check_allowed(p)
    return p


def default_dir():
    base = _abs(FM_DIR)
    roots = get_roots()
    if not roots or any(_under(r, base) for r in roots):
        return base
    return roots[0]


def list_dir(path, limit=40):
    folders, files, total_all = [], [], 0
    with os.scandir(path) as it:
        entries = sorted(it, key=lambda e: e.name)
    total_all = len(entries)
    for e in entries:
        if e.name.startswith('.'):
            continue
        try:
            is_dir = e.is_dir()
        except OSError:
            is_dir = False
        (folders if is_dir else files).append(e)
    lines = [f"📁 {e.name}/" for e in folders]
    shown = len(folders)
    for e in files:
        if shown >= limit:
            break
        try:
            size = format_size(e.stat().st_size)
        except OSError:
            size = "?"
        lines.append(f"📄 {e.name} ({size})")
        shown += 1
    total_display = len(folders) + len(files)
    return lines[:limit], total_display, total_all


def read_text_head(path, max_bytes=2000):
    """(teks, terpotong, biner)"""
    with open(path, "rb") as f:
        data = f.read(max_bytes + 1)
    if b"\x00" in data[:max_bytes]:
        return "", False, True
    return data[:max_bytes].decode("utf-8", "ignore"), len(data) > max_bytes, False


def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    if not hasattr(bot, "user_current_dirs"):
        bot.user_current_dirs = {}
    os.makedirs(FM_DIR, exist_ok=True)

    def get_lang(sender, room):
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        if not hasattr(bot, "user_languages"):
            bot.user_languages = {}
        key = room if room else str(sender)
        return bot.user_languages.get(key, "id")

    def T(lang, key, **kw):
        """json bahasa -> bawaan bahasa -> json en -> bawaan en -> json id -> bawaan id -> nama key."""
        lang = str(lang or "id").lower()
        text = None
        for code in (lang, "en", "id"):
            for src in (LANG_MESSAGES.get(code, {}), DEFAULT_MSG.get(code, {}),
                        _EXTRA["lang"].get(code, {}), _EXTRA["default"].get(code, {})):
                text = src.get(key)
                if text:
                    break
            if text:
                break
        text = text or key
        try:
            return text.format(**kw)
        except Exception:
            return text

    def run(fn, *a):
        return asyncio.to_thread(fn, *a)

    def get_config_owners():
        owners = set()
        config_path = "config.txt"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DEFAULT_OWNERS") and "=" in line:
                            _, val = line.split("=", 1)
                            for owner in val.split(","):
                                clean_owner = owner.strip().lower()
                                if clean_owner:
                                    owners.add(clean_owner)
            except Exception:
                pass

        if hasattr(bot, "default_owners") and bot.default_owners:
            for o in bot.default_owners:
                owners.add(str(o).strip().lower())

        return owners

    async def is_config_owner(sender, room, nick):
        allowed_owners = get_config_owners()
        if not allowed_owners:
            return False

        if sender:
            clean_sender = str(sender).split("/")[0].strip().lower()
            if clean_sender in allowed_owners:
                return True

        if room and nick:
            try:
                if hasattr(bot, "plugin") and "xep_0045" in bot.plugin:
                    room_info = await bot.plugin["xep_0045"].get_roster(room)
                    if nick in room_info:
                        server_real_jid = room_info[nick].get("jid")
                        if server_real_jid:
                            clean_server_jid = str(server_real_jid).split("/")[0].strip().lower()
                            if clean_server_jid in allowed_owners:
                                return True
            except Exception:
                pass

            if hasattr(bot, "room_users") and room in bot.room_users and nick in bot.room_users[room]:
                stored_jid = bot.room_users[room][nick].get("jid")
                if stored_jid:
                    clean_stored = str(stored_jid).split("/")[0].strip().lower()
                    if clean_stored in allowed_owners:
                        return True

        return False

    def get_session_key(room, sender):
        return f"room:{room}_user:{str(sender).lower()}" if room else f"pm:{str(sender).lower()}"

    def current_dir(sender, room):
        return bot.user_current_dirs.get(get_session_key(room, sender)) or default_dir()

    async def guarded(cmd, func, sender, room, nick, is_private, args, quiet=False):
        """Pemeriksaan owner + audit + penanganan galat untuk semua perintah file manager."""
        lang = get_lang(sender, room)
        who = f"{nick or '-'} <{str(sender).split('/')[0]}>"
        if not await is_config_owner(sender, room, nick):
            audit(who, room, cmd, summarize_args(cmd, args), "denied")
            if quiet:
                return
            ai_prompt = T(lang, "refusal_ai_prompt", nick=nick)
            default_refusal = T(lang, "refusal_default")
            session_key = get_session_key(room, sender)
            if hasattr(bot, "ask_ai_with_fallback"):
                refusal_msg = await bot.ask_ai_with_fallback(ai_prompt, room=room, session_key=session_key)
            else:
                refusal_msg = default_refusal
            await bot.reply_user(sender, room, refusal_msg, is_private, nick=nick)
            return
        result = "ok"
        try:
            return await func(sender, room, nick, is_private, args)
        except FmError as e:
            result = e.key
            await bot.reply_user(sender, room, T(lang, e.key, **e.kw), is_private, nick=nick)
        except asyncio.CancelledError:
            result = "cancelled"
            raise
        except Exception as e:
            result = f"error:{type(e).__name__}"
            logging.warning(f"[filemanager] {cmd}: {type(e).__name__}: {e}")
            await bot.reply_user(sender, room, T(lang, "err_generic", err=f"{type(e).__name__}: {e}"[:160]),
                                 is_private, nick=nick)
        finally:
            audit(who, room, cmd, summarize_args(cmd, args), result)

    def owner_config_only(func):
        cmd = func.__name__[4:] if func.__name__.startswith("cmd_") else func.__name__

        @functools.wraps(func)
        async def wrapper(sender, room, nick, is_private, args):
            return await guarded(cmd, func, sender, room, nick, is_private, args)
        return wrapper

    # ---------------- perintah dasar ----------------
    @bot.command("filemanager", "🔑 Master Bot")
    @owner_config_only
    async def cmd_filemanager(sender, room, nick, is_private, args):
        """filemanager"""
        lang = get_lang(sender, room)
        help_text = T(lang, "help_text") + "\n\n" + T(lang, "help_extra")
        await bot.reply_user(sender, room, help_text, is_private, nick=nick)

    @bot.command("cd", "🔑 Master Bot")
    @owner_config_only
    async def cmd_cd(sender, room, nick, is_private, args):
        """cd [path] atau cd .."""
        s_key = get_session_key(room, sender)
        cur = current_dir(sender, room)
        lang = get_lang(sender, room)

        if args and args[0].strip() in ["..", "back"]:
            target_path = os.path.dirname(cur)
            check_allowed(target_path)
        else:
            arg_str = " ".join(args) if args else ""
            target_path = resolve_path(arg_str, current_base=cur) if arg_str else cur

        if not os.path.exists(target_path):
            await bot.reply_user(sender, room, T(lang, "dir_not_found", path=target_path), is_private, nick=nick)
            return

        if not os.path.isdir(target_path):
            file_size = format_size(os.path.getsize(target_path))
            mod_time = datetime.fromtimestamp(os.path.getmtime(target_path)).strftime('%Y-%m-%d %H:%M:%S')
            info_text = T(lang, "file_info", name=os.path.basename(target_path), size=file_size,
                          mod_time=mod_time, path=target_path)
            await bot.reply_user(sender, room, info_text, is_private, nick=nick)
            return

        bot.user_current_dirs[s_key] = target_path

        try:
            lines, total_display, total_all = await run(list_dir, target_path)
            list_str = "\n".join(lines) if lines else T(lang, "folder_empty")
            header = T(lang, "header_dir", path=target_path, total=total_all)
            if total_display > 40:
                list_str += T(lang, "truncated_list", total=total_display)
            await bot.reply_user(sender, room, header + list_str, is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_read_dir", error=e), is_private, nick=nick)

    @bot.command("back", "🔑 Master Bot")
    @owner_config_only
    async def cmd_back(sender, room, nick, is_private, args):
        """back"""
        await cmd_cd(sender, room, nick, is_private, [".."])

    @bot.command("catfile", "🔑 Master Bot")
    @owner_config_only
    async def cmd_catfile(sender, room, nick, is_private, args):
        """catfile <nama_file>"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "catfile_prompt"), is_private, nick=nick)
            return

        file_path = resolve_path(" ".join(args), current_base=current_dir(sender, room))

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            await bot.reply_user(sender, room, T(lang, "file_not_found"), is_private, nick=nick)
            return
        if is_sensitive(file_path) and not is_private:
            raise FmError("err_sensitive_pm", name=os.path.basename(file_path))

        try:
            content, truncated, binary = await run(read_text_head, file_path)
            if binary:
                raise FmError("err_binary")
            if should_redact(file_path):
                content = redact_text(content)
            if truncated:
                content += T(lang, "catfile_truncated")
            header = T(lang, "catfile_header", name=os.path.basename(file_path), content=content)
            await bot.reply_user(sender, room, header, is_private, nick=nick)
        except FmError:
            raise
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_read_file", error=e), is_private, nick=nick)

    @bot.command("mkdir", "🔑 Master Bot")
    @owner_config_only
    async def cmd_mkdir(sender, room, nick, is_private, args):
        """mkdir <path_folder>"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "mkdir_prompt"), is_private, nick=nick)
            return

        dir_path = resolve_path(args[0].strip(), current_base=current_dir(sender, room))
        try:
            os.makedirs(dir_path, exist_ok=True)
            await bot.reply_user(sender, room, T(lang, "mkdir_success", path=dir_path), is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_mkdir", error=e), is_private, nick=nick)

    @bot.command("download", "🔑 Master Bot")
    @owner_config_only
    async def cmd_download(sender, room, nick, is_private, args):
        """download <URL> [name_file.format]"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "download_wrong_format"), is_private, nick=nick)
            return

        target_url = args[0].strip()
        custom_name = args[1].strip() if len(args) > 1 else None

        if not target_url.startswith(("http://", "https://")):
            await bot.reply_user(sender, room, T(lang, "download_url_scheme"), is_private, nick=nick)
            return

        await bot.reply_user(sender, room, T(lang, "download_init"), is_private, nick=nick)

        limit_mb = max_download_mb()
        limit = limit_mb * 1024 * 1024
        part_path = None
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            guess = custom_name or os.path.basename(target_url.split("?")[0].split("#")[0].rstrip("/"))
            file_name = safe_filename(guess, "")
            if not file_name or "." not in file_name:
                file_name = f"downloaded_{int(time.time())}.bin"
            file_path = os.path.join(DOWNLOAD_DIR, file_name)
            n = 1
            while os.path.exists(file_path):   # jangan menimpa unduhan lama
                base, ext = os.path.splitext(file_name)
                file_path = os.path.join(DOWNLOAD_DIR, f"{base}_{n}{ext}")
                n += 1
            part_path = file_path + ".part"

            timeout = aiohttp.ClientTimeout(total=900, sock_connect=15, sock_read=30)
            size = 0
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": UA}) as session:
                async with session.get(target_url) as resp:
                    if resp.status != 200:
                        await bot.reply_user(sender, room, T(lang, "download_http_error", status=resp.status),
                                             is_private, nick=nick)
                        return
                    if resp.content_length and resp.content_length > limit:
                        raise FmError("err_too_big_dl", mb=limit_mb)
                    with open(part_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            size += len(chunk)
                            if size > limit:
                                raise FmError("err_too_big_dl", mb=limit_mb)
                            f.write(chunk)
            os.replace(part_path, file_path)
            part_path = None
            await bot.reply_user(sender, room, T(lang, "download_success", path=file_path, size=format_size(size)),
                                 is_private, nick=nick)
        except FmError:
            raise
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_download", error=e), is_private, nick=nick)
        finally:
            if part_path and os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass

    @bot.command("upload", "🔑 Master Bot")
    @owner_config_only
    async def cmd_upload(sender, room, nick, is_private, args):
        """upload <name_file>"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "upload_prompt"), is_private, nick=nick)
            return

        file_path = resolve_path(" ".join(args), current_base=current_dir(sender, room))

        if not file_path or not os.path.exists(file_path) or os.path.isdir(file_path):
            await bot.reply_user(sender, room, T(lang, "upload_not_found"), is_private, nick=nick)
            return
        if is_sensitive(file_path) and not is_private:
            raise FmError("err_sensitive_pm", name=os.path.basename(file_path))
        if os.path.getsize(file_path) > UPLOAD_MAX_BYTES:
            raise FmError("err_too_big_up", mb=UPLOAD_MAX_BYTES >> 20)

        await bot.reply_user(sender, room, T(lang, "upload_init", name=os.path.basename(file_path)),
                             is_private, nick=nick)

        try:
            xep_plugin = None
            if hasattr(bot, 'plugin') and 'xep_0363' in bot.plugin:
                xep_plugin = bot.plugin['xep_0363']
            elif hasattr(bot, 'xep_0363'):
                xep_plugin = bot.xep_0363

            if xep_plugin and hasattr(xep_plugin, "upload_file"):
                real_filename = os.path.basename(file_path)

                def read_all():
                    with open(file_path, "rb") as f_local:
                        return f_local.read()
                file_bytes = await run(read_all)

                upload_result = await xep_plugin.upload_file(
                    filename=Path(real_filename),
                    size=len(file_bytes),
                    content_type="application/octet-stream",
                    input_file=io.BytesIO(file_bytes),
                    timeout=20
                )

                download_url = upload_result.get('url', '') if isinstance(upload_result, dict) else str(upload_result)

                if download_url:
                    target_jid = sender if is_private else room
                    msg_type = 'chat' if is_private else 'groupchat'
                    msg = bot.make_message(mto=target_jid, mbody=download_url, mtype=msg_type)
                    msg.send()
                else:
                    await bot.reply_user(sender, room, T(lang, "upload_no_url"), is_private, nick=nick)
            else:
                await bot.reply_user(sender, room, T(lang, "upload_no_plugin"), is_private, nick=nick)

        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_upload", error=e), is_private, nick=nick)

    @bot.command("deletefile", "🔑 Master Bot")
    @owner_config_only
    async def cmd_deletefile(sender, room, nick, is_private, args):
        """deletefile [-f] <name_file>"""
        lang = get_lang(sender, room)
        perm = any(a == "-f" for a in args)
        parts = [a for a in args if a != "-f"]
        if not parts:
            await bot.reply_user(sender, room, T(lang, "delete_prompt"), is_private, nick=nick)
            return

        file_path = resolve_path(" ".join(parts), current_base=current_dir(sender, room))

        if not os.path.lexists(file_path):
            await bot.reply_user(sender, room, T(lang, "file_not_found"), is_private, nick=nick)
            return

        name = os.path.basename(file_path.rstrip(os.sep)) or file_path
        if is_protected(file_path):
            raise FmError("err_protected", name=name)

        try:
            if perm or _inside(TRASH_DIR, file_path):
                is_dir = os.path.isdir(file_path) and not os.path.islink(file_path)
                await run(permanent_delete, file_path)
                msg = T(lang, "delete_folder_success") if is_dir else T(lang, "delete_file_success", name=name)
            else:
                size = await run(path_size, file_path)
                if size > trash_max_mb() * 1024 * 1024:
                    raise FmError("trash_too_big", name=name, mb=size >> 20, max=trash_max_mb())
                tid = await run(trash_put, file_path, nick or "-", size)
                msg = T(lang, "trash_moved", name=name, id=tid)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except FmError:
            raise
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_delete", error=e), is_private, nick=nick)

    @bot.command("renamefile", "🔑 Master Bot")
    @owner_config_only
    async def cmd_renamefile(sender, room, nick, is_private, args):
        """renamefile <old_name> <new_name>"""
        lang = get_lang(sender, room)
        if len(args) < 2:
            await bot.reply_user(sender, room, T(lang, "rename_wrong_format"), is_private, nick=nick)
            return

        old_path = resolve_path(args[0], current_base=current_dir(sender, room))

        if not os.path.lexists(old_path):
            await bot.reply_user(sender, room, T(lang, "rename_not_found"), is_private, nick=nick)
            return
        if is_protected(old_path):
            raise FmError("err_protected", name=os.path.basename(old_path))

        new_name = args[1].strip()
        if not new_name or "/" in new_name or "\\" in new_name or new_name in (".", ".."):
            raise FmError("err_name_invalid")
        new_path = os.path.join(os.path.dirname(old_path), new_name)
        check_allowed(new_path)
        if os.path.lexists(new_path) and _nc(new_path) != _nc(old_path):
            raise FmError("err_exists", name=new_name)

        try:
            os.rename(old_path, new_path)
            await bot.reply_user(sender, room, T(lang, "rename_success", name=new_name), is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_rename", error=e), is_private, nick=nick)

    @bot.command("movefile", "🔑 Master Bot")
    @owner_config_only
    async def cmd_movefile(sender, room, nick, is_private, args):
        """movefile <source> <destination_folder>"""
        lang = get_lang(sender, room)
        if len(args) < 2:
            await bot.reply_user(sender, room, T(lang, "move_wrong_format"), is_private, nick=nick)
            return

        cur = current_dir(sender, room)
        src_path = resolve_path(args[0], current_base=cur)
        dest_dir = resolve_path(args[1], current_base=cur)

        if not os.path.lexists(src_path):
            await bot.reply_user(sender, room, T(lang, "move_not_found"), is_private, nick=nick)
            return
        if is_protected(src_path):
            raise FmError("err_protected", name=os.path.basename(src_path))
        if os.path.isdir(src_path) and _inside(src_path, dest_dir):
            raise FmError("err_generic", err="destination is inside the source")

        os.makedirs(dest_dir, exist_ok=True)
        try:
            await run(shutil.move, src_path, dest_dir)
            await bot.reply_user(sender, room, T(lang, "move_success", path=dest_dir), is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_move", error=e), is_private, nick=nick)

    def copy_any(src_path, dest_dir):
        if os.path.isdir(src_path):
            shutil.copytree(src_path, os.path.join(dest_dir, os.path.basename(src_path.rstrip(os.sep))))
        else:
            shutil.copy2(src_path, dest_dir)

    @bot.command("copyfile", "🔑 Master Bot")
    @owner_config_only
    async def cmd_copyfile(sender, room, nick, is_private, args):
        """copyfile <source> <destination_folder>"""
        lang = get_lang(sender, room)
        if len(args) < 2:
            await bot.reply_user(sender, room, T(lang, "copy_wrong_format"), is_private, nick=nick)
            return

        cur = current_dir(sender, room)
        src_path = resolve_path(args[0], current_base=cur)
        dest_dir = resolve_path(args[1], current_base=cur)

        if not os.path.exists(src_path):
            await bot.reply_user(sender, room, T(lang, "copy_not_found"), is_private, nick=nick)
            return
        name = os.path.basename(src_path.rstrip(os.sep))
        if os.path.lexists(os.path.join(dest_dir, name)):   # dulu folder tujuan dihapus dulu: sekarang ditolak
            raise FmError("err_exists", name=name)
        if os.path.isdir(src_path) and _inside(src_path, dest_dir):
            raise FmError("err_generic", err="destination is inside the source")

        os.makedirs(dest_dir, exist_ok=True)
        try:
            await run(copy_any, src_path, dest_dir)
            await bot.reply_user(sender, room, T(lang, "copy_success", path=dest_dir), is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_copy", error=e), is_private, nick=nick)

    def archive_out_path(args, src_path, cur, ext_ok, default_ext):
        if len(args) > 1:
            out_name = args[1].strip()
            if not out_name.endswith(ext_ok):
                out_name += default_ext
            out_path = resolve_path(out_name, current_base=cur)
            if not os.path.isabs(out_name) and not out_path.startswith("/"):
                out_path = os.path.join(os.path.dirname(src_path), out_name)
        else:
            base_name = os.path.basename(src_path.rstrip(os.sep))
            out_path = os.path.join(os.path.dirname(src_path), f"{base_name}{default_ext}")
        check_allowed(out_path)
        if _nc(out_path) in protected_files():
            raise FmError("err_protected", name=os.path.basename(out_path))
        return out_path

    @bot.command("zip", "🔑 Master Bot")
    @owner_config_only
    async def cmd_zip(sender, room, nick, is_private, args):
        """zip <target> [name_output.zip]"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "zip_wrong_format"), is_private, nick=nick)
            return

        cur = current_dir(sender, room)
        src_path = resolve_path(args[0], current_base=cur)
        if not os.path.exists(src_path):
            await bot.reply_user(sender, room, T(lang, "zip_not_found"), is_private, nick=nick)
            return

        out_path = archive_out_path(args, src_path, cur, (".zip",), ".zip")
        await bot.reply_user(sender, room, T(lang, "zip_init"), is_private, nick=nick)

        try:
            await run(make_zip, src_path, out_path)
            zip_size = format_size(os.path.getsize(out_path))
            await bot.reply_user(sender, room, T(lang, "zip_success", path=out_path, size=zip_size),
                                 is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_zip", error=e), is_private, nick=nick)

    @bot.command("unzip", "🔑 Master Bot")
    @owner_config_only
    async def cmd_unzip(sender, room, nick, is_private, args):
        """unzip <file.zip> [destination_folder]"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "unzip_wrong_format"), is_private, nick=nick)
            return

        cur = current_dir(sender, room)
        zip_path = resolve_path(args[0], current_base=cur)
        if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
            await bot.reply_user(sender, room, T(lang, "unzip_not_found"), is_private, nick=nick)
            return

        if len(args) > 1:
            dest_dir = resolve_path(args[1], current_base=cur)
        else:
            dest_dir = os.path.splitext(zip_path)[0]
            check_allowed(dest_dir)

        os.makedirs(dest_dir, exist_ok=True)
        await bot.reply_user(sender, room, T(lang, "unzip_init"), is_private, nick=nick)

        try:
            count, skipped = await run(safe_unzip, zip_path, dest_dir)
            msg = T(lang, "unzip_success", path=dest_dir)
            if skipped:
                msg += "\n" + T(lang, "extract_skipped", n=skipped)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except FmError:
            raise
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_unzip", error=e), is_private, nick=nick)

    @bot.command("tar", "🔑 Master Bot")
    @owner_config_only
    async def cmd_tar(sender, room, nick, is_private, args):
        """tar <target> [name_output.tar.gz]"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "tar_wrong_format"), is_private, nick=nick)
            return

        cur = current_dir(sender, room)
        src_path = resolve_path(args[0], current_base=cur)
        if not os.path.exists(src_path):
            await bot.reply_user(sender, room, T(lang, "tar_not_found"), is_private, nick=nick)
            return

        out_path = archive_out_path(args, src_path, cur, (".tar.gz", ".tgz", ".tar"), ".tar.gz")
        await bot.reply_user(sender, room, T(lang, "tar_init"), is_private, nick=nick)

        try:
            await run(make_tar, src_path, out_path)
            tar_size = format_size(os.path.getsize(out_path))
            await bot.reply_user(sender, room, T(lang, "tar_success", path=out_path, tar_size=tar_size),
                                 is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_tar", error=e), is_private, nick=nick)

    @bot.command("untar", "🔑 Master Bot")
    @owner_config_only
    async def cmd_untar(sender, room, nick, is_private, args):
        """untar <file.tar.gz> [destination_folder]"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "untar_wrong_format"), is_private, nick=nick)
            return

        cur = current_dir(sender, room)
        tar_path = resolve_path(args[0], current_base=cur)
        if not os.path.exists(tar_path) or not tarfile.is_tarfile(tar_path):
            await bot.reply_user(sender, room, T(lang, "untar_not_found"), is_private, nick=nick)
            return

        if len(args) > 1:
            dest_dir = resolve_path(args[1], current_base=cur)
        else:
            dest_dir = os.path.splitext(tar_path[:-3] if tar_path.endswith(".gz") else tar_path)[0]
            check_allowed(dest_dir)

        os.makedirs(dest_dir, exist_ok=True)
        await bot.reply_user(sender, room, T(lang, "untar_init"), is_private, nick=nick)

        try:
            count, skipped = await run(safe_untar, tar_path, dest_dir)
            msg = T(lang, "untar_success", path=dest_dir)
            if skipped:
                msg += "\n" + T(lang, "extract_skipped", n=skipped)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except FmError:
            raise
        except Exception as e:
            await bot.reply_user(sender, room, T(lang, "err_untar", error=e), is_private, nick=nick)

    # ---------------- tempat sampah ----------------
    @bot.command("trash", "🔑 Master Bot")
    @owner_config_only
    async def cmd_trash(sender, room, nick, is_private, args):
        """trash [empty|days <n>]"""
        lang = get_lang(sender, room)
        sub = args[0].lower() if args else ""

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if sub == "":
            items = await run(trash_index)
            if not items:
                return await say(T(lang, "trash_empty_list"))
            now = time.time()
            lines = [T(lang, "trash_header", count=len(items), days=trash_days())]
            for i, it in enumerate(items[:15], start=1):
                lines.append(T(lang, "trash_item", n=i, name=it.get("name", "?"),
                               size=format_size(int(it.get("size", 0) or 0)),
                               age=fmt_age(now - it.get("ts", now)), id=it["id"]))
            if len(items) > 15:
                lines.append(f"… +{len(items) - 15}")
            return await say("\n".join(lines))
        if sub == "empty":
            count, size = await run(trash_purge, 0)
            return await say(T(lang, "trash_emptied", count=count, size=format_size(size)))
        if sub == "days" and len(args) > 1 and args[1].isdigit() and 1 <= int(args[1]) <= 90:
            fm_set("trash_days", int(args[1]))
            return await say(T(lang, "set_ok", name="trash days", value=args[1]))
        await say(T(lang, "trash_usage"))

    @bot.command("undelete", "🔑 Master Bot")
    @owner_config_only
    async def cmd_undelete(sender, room, nick, is_private, args):
        """undelete <number|id>"""
        lang = get_lang(sender, room)
        if not args:
            await bot.reply_user(sender, room, T(lang, "undelete_usage"), is_private, nick=nick)
            return
        items = await run(trash_index)
        token = args[0].strip()
        pick = None
        if token.isdigit() and 1 <= int(token) <= len(items):
            pick = items[int(token) - 1]
        else:
            hits = [it for it in items if it["id"].startswith(token)]
            pick = hits[0] if len(hits) == 1 else None
        if pick is None:
            await bot.reply_user(sender, room, T(lang, "undelete_not_found"), is_private, nick=nick)
            return
        dest = await run(trash_restore, pick)
        await bot.reply_user(sender, room, T(lang, "undelete_ok", dest=dest), is_private, nick=nick)

    # ---------------- batas folder & audit ----------------
    @bot.command("fmroot", "🔑 Master Bot")
    @owner_config_only
    async def cmd_fmroot(sender, room, nick, is_private, args):
        """fmroot [add|del|clear] [folder]"""
        lang = get_lang(sender, room)
        sub = args[0].lower() if args else "list"
        roots = get_roots()

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if sub == "list":
            if not roots:
                return await say(T(lang, "fmroot_none"))
            return await say(T(lang, "fmroot_list", roots="\n".join(f"- {r}" for r in roots)))
        if sub == "clear":
            fm_set("roots", None)
            return await say(T(lang, "fmroot_cleared"))
        if sub in ("add", "del") and len(args) > 1:
            path = _abs(_resolve_raw(" ".join(args[1:]), current_dir(sender, room)))
            if sub == "add":
                if not os.path.isdir(path):
                    return await say(T(lang, "fmroot_not_dir", path=path))
                if not any(_nc(r) == _nc(path) for r in roots):
                    roots.append(path)
                fm_set("roots", roots)
                return await say(T(lang, "fmroot_added", path=path))
            match = next((r for r in roots if _nc(r) == _nc(path)), None)
            if match is None:
                return await say(T(lang, "fmroot_not_listed"))
            roots.remove(match)
            fm_set("roots", roots or None)
            return await say(T(lang, "fmroot_removed", path=path))
        await say(T(lang, "fmroot_usage"))

    @bot.command("audit", "🔑 Master Bot")
    @owner_config_only
    async def cmd_audit(sender, room, nick, is_private, args):
        """audit [count]"""
        lang = get_lang(sender, room)
        n = int(args[0]) if args and args[0].isdigit() else 10
        n = max(1, min(30, n))
        recs = await run(read_audit_tail, n)
        if not recs:
            await bot.reply_user(sender, room, T(lang, "audit_empty"), is_private, nick=nick)
            return
        lines = [T(lang, "audit_header", count=len(recs))]
        for r in recs:
            lines.append(f"{str(r.get('ts', ''))[5:16]} {r.get('who', '?')} @{r.get('room', '?')} "
                         f"{r.get('cmd', '?')} {r.get('args', '')} → {r.get('result', '?')}")
        await bot.reply_user(sender, room, "\n".join(lines), is_private, nick=nick)

    # ---------------- pembersihan otomatis tempat sampah ----------------
    async def trash_loop():
        await asyncio.sleep(120)
        while True:
            try:
                await run(trash_purge, trash_days())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.warning(f"[filemanager] pembersihan sampah gagal: {type(e).__name__}")
            await asyncio.sleep(6 * 3600)

    async def start_trash_task(event):
        if not getattr(bot, "is_primary_jid", True):
            return   # satu pembersih saja walau ada beberapa akun
        t = getattr(bot, "_fm_task", None)
        if t is None or t.done():
            bot._fm_task = asyncio.ensure_future(trash_loop())

    bot.add_event_handler("session_start", start_trash_task)

    # ---------------- dipakai plugin lain (cmd_filetools) ----------------
    bot.fm = types.SimpleNamespace(
        guarded=guarded, is_config_owner=is_config_owner, resolve=resolve_path, resolve_raw=_resolve_raw,
        current_dir=current_dir, get_lang=get_lang, T=T, run=run, format_size=format_size,
        redact=redact_text, should_redact=should_redact, is_sensitive=is_sensitive, is_protected=is_protected,
        protected_files=protected_files, check_allowed=check_allowed, safe_filename=safe_filename,
        cfg=fm_cfg, cfg_set=fm_set, max_download_mb=max_download_mb, audit=audit, inside=_inside,
        abspath=_nc, FmError=FmError, FM_DIR=FM_DIR, add_messages=add_messages,
    )
