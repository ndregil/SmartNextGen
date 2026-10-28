# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot - Plugin Alias Pemicu Kustom
#
#   galias [add] <pemicu>=<perintah [argumen]>   (owner bot)  berlaku di SEMUA room & PM
#   alias  [add] <pemicu>=<perintah [argumen]>   (admin/mod room) hanya berlaku di room ini
#   galias|alias del <pemicu>
#   galias|alias list
#
# Contoh:  galias add pg=ping   -> user mengetik "pg"  => bot menjalankan "ping"
#          alias add t=test     -> hanya di room ini
#          galias del pg
#
# - Disimpan di database bot (data/botsettings_*.db): hilang bila database dihapus.
# - Perintah galias/alias tampil di help; pemicu (hasil alias) TIDAK tampil di help.
# - Hak akses perintah tujuan tetap diperiksa seperti biasa (alias tidak menaikkan hak akses).
# - Berjalan juga saat bot di-mention ("NickBot: t") karena pemicu didaftarkan sebagai perintah tersembunyi.
# - Alias room mengalahkan alias global bila pemicunya sama.
# - Pemicu tidak boleh sama dengan nama perintah/alias yang sudah ada.

import os
import sys
import time

MAX_ALIASES = 100
MAX_TRIGGER = 32
COOLDOWN = 1.0
GLOBAL_KEY = "*"
BLOCKED_TARGETS = {"alias", "galias"}

DEFAULT_MSG = {
    "id": {
        "mod_only": "Akses ditolak: perintah ini hanya untuk owner/admin/moderator room.",
        "owner_only": "Akses ditolak: perintah global hanya untuk owner bot.",
        "room_only": "Gunakan perintah ini di dalam room.",
        "usage": "Pemakaian: {cmd} [add] <pemicu>=<perintah [argumen]> | {cmd} del <pemicu> | {cmd} list",
        "bad_trigger": "Pemicu tidak valid (1-{max} karakter, tanpa spasi).",
        "conflict": "Gagal: '{t}' sudah dipakai sebagai nama perintah.",
        "bad_target": "Gagal: perintah '{c}' tidak ditemukan atau tidak boleh dijadikan alias.",
        "limit": "Gagal: batas {max} alias tercapai.",
        "added": "Berhasil: '{t}' sekarang menjalankan '{c}'{scope}.",
        "removed": "Berhasil menghapus alias '{t}'{scope}.",
        "not_found": "Alias '{t}' tidak ditemukan{scope}.",
        "empty": "Belum ada alias.",
        "list_title": "Daftar alias{scope}:",
        "scope_global": " (global)",
        "scope_room": " (room ini)",
    },
    "en": {
        "mod_only": "Access denied: this command is for room owners/admins/moderators only.",
        "owner_only": "Access denied: global commands are for the bot owner only.",
        "room_only": "Use this command inside a room.",
        "usage": "Usage: {cmd} [add] <trigger>=<command [args]> | {cmd} del <trigger> | {cmd} list",
        "bad_trigger": "Invalid trigger (1-{max} characters, no spaces).",
        "conflict": "Failed: '{t}' is already a command name.",
        "bad_target": "Failed: command '{c}' was not found or cannot be aliased.",
        "limit": "Failed: limit of {max} aliases reached.",
        "added": "Successfully set: '{t}' now runs '{c}'{scope}.",
        "removed": "Successfully removed alias '{t}'{scope}.",
        "not_found": "Alias '{t}' was not found{scope}.",
        "empty": "No aliases yet.",
        "list_title": "Aliases{scope}:",
        "scope_global": " (global)",
        "scope_room": " (this room)",
    },
}



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

    # ---------------- database (di DB bot, bukan file terpisah) ----------------
    def ensure_table(b):
        b.cursor.execute("CREATE TABLE IF NOT EXISTS cmd_aliases ("
                         "scope TEXT, trigger TEXT, command TEXT, PRIMARY KEY (scope, trigger))")
        b.conn.commit()

    ensure_table(bot)

    def all_bots():
        main_mod = sys.modules.get("__main__")
        active = getattr(main_mod, "ACTIVE_BOT_INSTANCES", {}) if main_mod else {}
        out = []
        for b in list(active.values()) + [bot]:
            if not any(b is x for x in out):
                out.append(b)
        return out

    def db_targets(scope):
        """Alias global disinkronkan ke semua akun bot; alias room hanya di akun ini."""
        if scope != GLOBAL_KEY:
            return [bot]
        bots = all_bots()
        for b in bots:
            try:
                ensure_table(b)
            except Exception:
                pass
        return bots

    def count_scope(scope):
        return bot.cursor.execute("SELECT COUNT(*) FROM cmd_aliases WHERE scope=?", (scope,)).fetchone()[0]

    def lookup_alias(b, trig, room):
        scopes = [GLOBAL_KEY] if not room else [room.lower(), GLOBAL_KEY]
        marks = ",".join("?" * len(scopes))
        rows = b.cursor.execute(f"SELECT scope, command FROM cmd_aliases WHERE trigger=? AND scope IN ({marks})",
                                (trig, *scopes)).fetchall()
        if not rows:
            return None
        rows.sort(key=lambda r: r[0] == GLOBAL_KEY)   # alias room didahulukan
        return rows[0][1]

    # ---------------- pemicu sebagai perintah tersembunyi ----------------
    # Pemicu didaftarkan ke COMMAND_LOOKUP (tidak ke COMMAND_REGISTRY, jadi tidak tampil di help)
    # supaya jalur bawaan cmd_ai mengenalinya sebagai perintah, termasuk saat bot di-mention.
    cool = {}

    def make_proxy(b, trig):
        async def proxy(sender, room, nick, is_private, args):
            target = lookup_alias(b, trig, room)
            if not target:
                return
            canon = target.split()[0]
            real = b.COMMAND_LOOKUP.get(canon)
            if real is None or getattr(real, "_alias_proxy", False):
                return
            now = time.time()
            ck = ((room or "pm").lower(), str(nick or sender).lower())
            if now - cool.get(ck, 0) < COOLDOWN:
                return
            cool[ck] = now
            if len(cool) > 1000:
                for k in [k for k, t in cool.items() if now - t > 60]:
                    cool.pop(k, None)
            text = " ".join([target] + list(args))
            prefix = str(b.get_room_prefix(room) or "") if room else ""
            if prefix and not text.startswith(prefix):
                text = prefix + text
            await b.handle_command(text, sender, room, nick, is_private)

        proxy.is_command = True
        proxy.cmd_name = trig
        proxy.cmd_aliases = []
        proxy.category = "👤 Participant & Member"
        proxy.description = ""
        proxy.__doc__ = trig
        proxy._alias_proxy = True
        return proxy

    def install(b, trig):
        cur = b.COMMAND_LOOKUP.get(trig)
        if cur is not None and not getattr(cur, "_alias_proxy", False):
            return False   # nama perintah asli tidak boleh ditimpa
        b.COMMAND_LOOKUP[trig] = make_proxy(b, trig)
        return True

    def uninstall_if_unused(b, trig):
        n = b.cursor.execute("SELECT COUNT(*) FROM cmd_aliases WHERE trigger=?", (trig,)).fetchone()[0]
        if n == 0 and getattr(b.COMMAND_LOOKUP.get(trig), "_alias_proxy", False):
            b.COMMAND_LOOKUP.pop(trig, None)

    def install_all():
        try:
            for (trig,) in bot.cursor.execute("SELECT DISTINCT trigger FROM cmd_aliases").fetchall():
                install(bot, trig)
        except Exception:
            pass

    # Dipasang saat session_start (bukan saat plugin dimuat) agar tidak ikut tercetak di log
    # startup zz_aliases dan tidak menimpa perintah dari plugin yang dimuat belakangan.
    async def on_start(event):
        install_all()

    bot.add_event_handler("session_start", on_start)

    # ---------------- hak akses ----------------
    def exempt(room, nick):
        info = bot.room_users.get(room, {}).get(nick) or {}
        return info.get("affiliation") in ("owner", "admin") or info.get("role") == "moderator"

    async def is_owner(sender, room, nick):
        try:
            return bool(await bot.verify_real_owner_from_server(room, nick, sender))
        except Exception:
            return False

    async def is_staff(sender, room, nick):
        return exempt(room, nick) or await is_owner(sender, room, nick)

    # ---------------- pengelolaan ----------------
    def resolve_target(spec):
        parts = spec.split()
        if not parts:
            return None
        func = bot.COMMAND_LOOKUP.get(parts[0].lower())
        if func is None or getattr(func, "_alias_proxy", False):
            return None
        canon = getattr(func, "cmd_name", parts[0].lower())
        if canon in BLOCKED_TARGETS:
            return None
        return " ".join([canon] + parts[1:])

    async def manage(scope, cmd_name, sender, room, nick, is_private, args):
        lang = get_lang(sender, room)
        scope_txt = T(lang, "scope_global" if scope == GLOBAL_KEY else "scope_room")

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        sub = args[0].lower() if args else ""
        # "add" boleh dilewat: galias t=test
        if args and sub not in ("add", "del", "remove", "list") and "=" in " ".join(args):
            args = ["add"] + list(args)
            sub = "add"

        if sub == "add":
            joined = " ".join(args[1:])
            left, sep, right = joined.partition("=")
            trig, cmd_spec = left.strip(), right.strip()
            if not sep or not trig or not cmd_spec:
                return await say(T(lang, "usage", cmd=cmd_name))
            if len(trig) > MAX_TRIGGER or any(c.isspace() for c in trig):
                return await say(T(lang, "bad_trigger", max=MAX_TRIGGER))
            trig = trig.lower()
            existing = bot.COMMAND_LOOKUP.get(trig)
            if existing is not None and not getattr(existing, "_alias_proxy", False):
                return await say(T(lang, "conflict", t=trig))
            target = resolve_target(cmd_spec)
            if not target:
                return await say(T(lang, "bad_target", c=cmd_spec.split()[0]))
            exists = bot.cursor.execute("SELECT 1 FROM cmd_aliases WHERE scope=? AND trigger=?",
                                        (scope, trig)).fetchone()
            if not exists and count_scope(scope) >= MAX_ALIASES:
                return await say(T(lang, "limit", max=MAX_ALIASES))
            for b in db_targets(scope):
                b.cursor.execute("INSERT OR REPLACE INTO cmd_aliases (scope, trigger, command) VALUES (?, ?, ?)",
                                 (scope, trig, target))
                b.conn.commit()
                install(b, trig)
            return await say(T(lang, "added", t=trig, c=target, scope=scope_txt))

        if sub in ("del", "remove"):
            if len(args) < 2:
                return await say(T(lang, "usage", cmd=cmd_name))
            trig = args[1].strip().lower()
            removed = 0
            for b in db_targets(scope):
                b.cursor.execute("DELETE FROM cmd_aliases WHERE scope=? AND trigger=?", (scope, trig))
                removed += b.cursor.rowcount
                b.conn.commit()
                uninstall_if_unused(b, trig)
            if removed:
                return await say(T(lang, "removed", t=trig, scope=scope_txt))
            return await say(T(lang, "not_found", t=trig, scope=scope_txt))

        if sub == "list":
            rows = bot.cursor.execute("SELECT trigger, command FROM cmd_aliases WHERE scope=? ORDER BY trigger",
                                      (scope,)).fetchall()
            if not rows:
                return await say(T(lang, "empty"))
            lines = [T(lang, "list_title", scope=scope_txt)] + [f"{t} → {c}" for t, c in rows]
            return await say("\n".join(lines))

        await say(T(lang, "usage", cmd=cmd_name))

    @bot.command("galias", "👑 Bot Owner")
    async def cmd_galias(sender, room, nick, is_private, args):
        """galias [add] <trigger>=<command> | del <trigger> | list"""
        lang = get_lang(sender, room)
        if not await is_owner(sender, room, nick):
            return await bot.reply_user(sender, room, T(lang, "owner_only"), is_private, nick=nick)
        await manage(GLOBAL_KEY, "galias", sender, room, nick, is_private, args)

    @bot.command("alias", "💎 Admin & Owner Group")
    async def cmd_alias(sender, room, nick, is_private, args):
        """alias [add] <trigger>=<command> | del <trigger> | list"""
        lang = get_lang(sender, room)
        if not room:
            return await bot.reply_user(sender, room, T(lang, "room_only"), is_private, nick=nick)
        if not await is_staff(sender, room, nick):
            return await bot.reply_user(sender, room, T(lang, "mod_only"), is_private, nick=nick)
        await manage(room.lower(), "alias", sender, room, nick, is_private, args)
