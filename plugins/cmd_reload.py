# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org
#
# Plugin Reload: muat ulang plugin TANPA memutus akun bot (khusus owner bot).
#
#   reload <plugin>   : muat ulang satu plugin (contoh: reload rss  atau  reload cmd_rss)
#                       plugin yang belum pernah dimuat (file baru) juga langsung dimuat
#   reload all        : muat ulang semua plugin yang aman
#   reload list       : daftar plugin dan statusnya
#
# Cara kerja (untuk SEMUA akun jid1..jid3 sekaligus):
#   1. Kode diperiksa dulu (sintaks + import). Bila salah, plugin lama tetap berjalan.
#   2. Tugas latar milik plugin dihentikan, perintah & event handler lamanya dilepas.
#   3. Modul dimuat ulang lalu register() dijalankan lagi; handler 'session_start' milik plugin
#      dijalankan ulang agar tugas latar (RSS, libur, dst.) langsung hidup lagi.
# Tidak bisa di-reload (membungkus fungsi inti bot, pakai: restart all):
#   cmd_users, zz_aliases, cmd_reload
# Catatan: data di memori milik plugin (mis. game yang sedang berjalan) ikut ter-reset.

import asyncio
import importlib
import inspect
import os
import re
import sys

PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))
UNSAFE = {"cmd_users", "zz_aliases", "cmd_reload"}

DEFAULT_MSG = {
    "id": {
        "owner_only": "Akses ditolak: perintah ini hanya untuk owner bot.",
        "usage": "Pemakaian: reload <plugin> | reload all | reload list  (contoh: reload rss)",
        "not_found": "Plugin '{name}' tidak ditemukan di folder plugins.",
        "unsafe": "Plugin '{name}' tidak bisa dimuat ulang tanpa restart (membungkus fungsi inti). Gunakan: restart all",
        "syntax_error": "Gagal: kesalahan sintaks di {name}: {err}. Plugin lama tetap berjalan.",
        "load_error": "Gagal memuat {name}: {err}. Plugin lama tetap berjalan.",
        "no_handlers": "Gagal: versi slixmpp ini tidak mendukung pembacaan daftar handler. Gunakan: restart all",
        "ok": "Berhasil memuat ulang {name} ({bots} akun, {cmds} perintah, {tasks} tugas latar dihentikan).",
        "ok_new": "Berhasil memuat plugin baru {name} ({bots} akun, {cmds} perintah).",
        "partial": "Gagal sebagian di {name}: {ok}/{total} akun berhasil. Error: {err}. Perbaiki lalu jalankan reload lagi.",
        "list_title": "Plugin ({count}):",
        "state_loaded": "dimuat", "state_new": "belum dimuat", "state_restart": "perlu restart",
        "all_summary": "Selesai: {ok} plugin berhasil, {fail} gagal.{detail}",
        "busy": "Reload sedang berjalan, tunggu sebentar.",
    },
    "en": {
        "owner_only": "Access denied: this command is for the bot owner only.",
        "usage": "Usage: reload <plugin> | reload all | reload list  (example: reload rss)",
        "not_found": "Plugin '{name}' was not found in the plugins folder.",
        "unsafe": "Plugin '{name}' cannot be reloaded without a restart (it wraps core functions). Use: restart all",
        "syntax_error": "Failed: syntax error in {name}: {err}. The old plugin keeps running.",
        "load_error": "Failed to load {name}: {err}. The old plugin keeps running.",
        "no_handlers": "Failed: this slixmpp version does not expose its handler list. Use: restart all",
        "ok": "Successfully reloaded {name} ({bots} accounts, {cmds} commands, {tasks} background tasks stopped).",
        "ok_new": "Successfully loaded new plugin {name} ({bots} accounts, {cmds} commands).",
        "partial": "Partly failed for {name}: {ok}/{total} accounts succeeded. Error: {err}. Fix it and run reload again.",
        "list_title": "Plugins ({count}):",
        "state_loaded": "loaded", "state_new": "not loaded", "state_restart": "restart needed",
        "all_summary": "Done: {ok} plugins succeeded, {fail} failed.{detail}",
        "busy": "A reload is already running, please wait.",
    },
}

_lock = {"v": None}


def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def get_lang(sender, room):
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        return "id"

    def T(lang, key, **kw):
        lang = str(lang or "id").lower()
        text = None
        for src in (LANG_MESSAGES.get(lang, {}), DEFAULT_MSG.get(lang, {}), LANG_MESSAGES.get("en", {}),
                    DEFAULT_MSG["en"], LANG_MESSAGES.get("id", {}), DEFAULT_MSG["id"]):
            text = src.get(key)
            if text:
                break
        text = text or key
        try:
            return text.format(**kw)
        except Exception:
            return text

    def get_bots():
        main_mod = sys.modules.get("__main__")
        active = getattr(main_mod, "ACTIVE_BOT_INSTANCES", {}) if main_mod else {}
        out = []
        for b in list(active.values()) + [bot]:
            if not any(b is x for x in out):
                out.append(b)
        return out

    def store_of(b):
        """Tabel event handler slixmpp (nama dimangle oleh Python). None bila tidak ditemukan."""
        return getattr(b, "_XMLStream__event_handlers", None)

    def handler_fn(item):
        return item[0] if isinstance(item, (tuple, list)) else item

    def err_text(e):
        return f"{type(e).__name__}: {e}"[:180]

    def norm_name(s):
        s = (s or "").strip().lower().replace("\\", "/").split("/")[-1]
        if s.endswith(".py"):
            s = s[:-3]
        if not re.fullmatch(r"[a-z0-9_]{1,40}", s) or s.startswith("__"):
            return ""
        if not s.startswith(("cmd_", "zz_")) and os.path.isfile(os.path.join(PLUGINS_DIR, f"cmd_{s}.py")):
            s = f"cmd_{s}"
        return s

    def plugin_files():
        try:
            return sorted(f[:-3] for f in os.listdir(PLUGINS_DIR)
                          if f.endswith(".py") and not f.startswith("__"))
        except OSError:
            return []

    # ---------------- pembongkaran plugin lama ----------------
    def teardown(b, modname):
        """Lepas perintah & event handler milik modul dari satu akun. Return {kunci_lookup: nama_perintah}."""
        removed = {}
        lookup = b.COMMAND_LOOKUP
        for key, func in list(dict.items(lookup)):
            if getattr(func, "__module__", "") == modname:
                removed[key] = getattr(func, "cmd_name", key)
                del lookup[key]
        names = set(removed.values())
        reg = b.COMMAND_REGISTRY
        for cat in list(reg.keys()):
            reg[cat] = [e for e in reg[cat]
                        if (str(e[0]).split("/")[0].split() or [""])[0] not in names]
        store = store_of(b)
        for ev, handlers in list(store.items()):
            for item in list(handlers):
                fn = handler_fn(item)
                if getattr(fn, "__module__", "") == modname:
                    try:
                        b.del_event_handler(ev, fn)
                    except Exception:
                        pass
        return removed

    def restore_aliases(b, removed):
        """Alias tambahan (mis. dari zz_aliases) yang ikut terhapus dihubungkan lagi ke perintah baru."""
        lookup = b.COMMAND_LOOKUP
        for key, canon in removed.items():
            if key in lookup:
                continue
            target = lookup.get(canon)
            if target is not None and getattr(target, "cmd_name", None) == canon:
                lookup[key] = target

    async def cancel_plugin_tasks(path):
        """Hentikan tugas latar yang coroutine-nya berasal dari file plugin (kecuali tugas ini sendiri)."""
        cur = asyncio.current_task()
        target = os.path.abspath(path)
        victims = []
        for t in asyncio.all_tasks():
            if t is cur or t.done():
                continue
            try:
                coro = t.get_coro()
                code = (getattr(coro, "cr_code", None) or getattr(coro, "gi_code", None)
                        or getattr(coro, "ag_code", None))
                fn = getattr(code, "co_filename", "")
                if fn and os.path.abspath(fn) == target:
                    t.cancel()
                    victims.append(t)
            except Exception:
                continue
        if victims:
            await asyncio.wait(victims, timeout=5)
        return len(victims)

    # ---------------- reload satu plugin ----------------
    async def do_reload(name, lang):
        """Return (berhasil: bool, pesan: str)."""
        modname = f"plugins.{name}"
        path = os.path.join(PLUGINS_DIR, f"{name}.py")
        if not os.path.isfile(path):
            return False, T(lang, "not_found", name=name)
        if name in UNSAFE:
            return False, T(lang, "unsafe", name=name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                compile(f.read(), path, "exec")
        except SyntaxError as e:
            return False, T(lang, "syntax_error", name=name, err=f"{e.msg} (line {e.lineno})")
        except Exception as e:
            return False, T(lang, "syntax_error", name=name, err=err_text(e))

        bots = get_bots()
        loaded = sys.modules.get(modname)
        if loaded is not None and any(store_of(b) is None for b in bots):
            return False, T(lang, "no_handlers")

        try:   # modul dimuat dulu; bila gagal, belum ada yang dibongkar
            importlib.invalidate_caches()
            module = importlib.reload(loaded) if loaded is not None else importlib.import_module(modname)
            if not hasattr(module, "register"):
                raise AttributeError("register() not found")
        except Exception as e:
            return False, T(lang, "load_error", name=name, err=err_text(e))

        stopped, removed_by_bot = 0, {}
        if loaded is not None:
            stopped = await cancel_plugin_tasks(path)
            for b in bots:
                removed_by_bot[id(b)] = teardown(b, modname)

        ok, errs = 0, []
        for b in bots:
            try:
                module.register(b)
                restore_aliases(b, removed_by_bot.get(id(b), {}))
                ok += 1
            except Exception as e:
                errs.append(err_text(e))

        # hidupkan lagi tugas latar: jalankan handler session_start milik plugin ini
        for b in bots:
            if not getattr(b, "session_active", False):
                continue
            for item in list((store_of(b) or {}).get("session_start", [])):
                fn = handler_fn(item)
                if getattr(fn, "__module__", "") == modname:
                    try:
                        res = fn(None)
                        if inspect.isawaitable(res):
                            asyncio.ensure_future(res)
                    except Exception as e:
                        errs.append(err_text(e))

        cmds = sum(1 for k, f in dict.items(bot.COMMAND_LOOKUP)
                   if getattr(f, "__module__", "") == modname and getattr(f, "cmd_name", k) == k)
        print(f"[reload] {name}: {ok}/{len(bots)} akun, {cmds} perintah" + (f", error: {errs[0]}" if errs else ""))
        if ok < len(bots) or errs:
            return False, T(lang, "partial", name=name, ok=ok, total=len(bots), err=(errs[0] if errs else "?"))
        if loaded is None:
            return True, T(lang, "ok_new", name=name, bots=ok, cmds=cmds)
        return True, T(lang, "ok", name=name, bots=ok, cmds=cmds, tasks=stopped)

    async def reload_plugin(name, lang="id"):
        """Dipakai plugin lain (deploy/rollback): muat ulang satu plugin dengan kunci yang sama. Return (ok, pesan)."""
        clean = norm_name(name)
        if not clean:
            return False, T(lang, "not_found", name=str(name)[:40])
        if _lock["v"] is None:
            _lock["v"] = asyncio.Lock()
        async with _lock["v"]:
            return await do_reload(clean, lang)

    bot.reload_plugin = reload_plugin

    # ---------------- perintah ----------------
    @bot.command("reload", "👑 Bot Owner")
    async def cmd_reload(sender, room, nick, is_private, args):
        """reload <plugin|all|list>"""
        lang = get_lang(sender, room)

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        try:
            is_owner = bool(await bot.verify_real_owner_from_server(room, nick, sender))
        except Exception:
            is_owner = False
        if not is_owner:
            return await say(T(lang, "owner_only"))
        if not args:
            return await say(T(lang, "usage"))
        if _lock["v"] is None:
            _lock["v"] = asyncio.Lock()
        if _lock["v"].locked():
            return await say(T(lang, "busy"))

        sub = args[0].strip().lower()
        async with _lock["v"]:
            if sub == "list":
                files = plugin_files()
                lines = []
                for n in files:
                    if n in UNSAFE:
                        state = T(lang, "state_restart")
                    elif f"plugins.{n}" in sys.modules:
                        state = T(lang, "state_loaded")
                    else:
                        state = T(lang, "state_new")
                    lines.append(f"{n} [{state}]")
                return await say(T(lang, "list_title", count=len(files)) + "\n" + "\n".join(lines))

            if sub == "all":
                ok, failed = 0, []
                for n in plugin_files():
                    if n in UNSAFE:
                        continue
                    good, _msg = await do_reload(n, lang)
                    if good:
                        ok += 1
                    else:
                        failed.append(n)
                detail = (" " + ", ".join(failed)) if failed else ""
                return await say(T(lang, "all_summary", ok=ok, fail=len(failed), detail=detail))

            name = norm_name(sub)
            if not name:
                return await say(T(lang, "not_found", name=sub[:40]))
            _good, msg = await do_reload(name, lang)
            await say(msg)
