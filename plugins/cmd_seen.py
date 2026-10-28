# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot - Plugin "seen"
# Mencatat terakhir kali tiap nick terlihat di room (pesan / masuk / keluar / ganti nick).
# Perintah: seen <nick>
# Pengaturan opsional (owner, lewat database settings): seen_store_msg = 0 -> isi pesan tidak disimpan.

import asyncio
import os
import re
import time

MAX_MSG_LEN = 120
KEEP_DAYS = 180
COMMIT_EVERY = 20
NS_MUC_USER = "{http://jabber.org/protocol/muc#user}"


def is_history_message(msg):
    """Pesan riwayat (delayed) dari MUC tidak dihitung sebagai aktivitas baru."""
    try:
        xml = getattr(msg, "xml", None)
        if xml is not None and (xml.find("{urn:xmpp:delay}delay") is not None
                                or xml.find("{jabber:x:delay}x") is not None):
            return True
    except Exception:
        pass
    return False


def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def get_lang(sender, room):
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        return "id"

    def T(lang, key, **kw):
        """Fallback: bahasa aktif -> en -> id -> nama key."""
        lang = str(lang or "id").lower()
        text = None
        for code in (lang, "en", "id"):
            text = LANG_MESSAGES.get(code, {}).get(key)
            if text:
                break
        text = text or key
        try:
            return text.format(**kw)
        except Exception:
            return text

    def fmt_ago(lang, ts):
        secs = int(max(0, time.time() - ts))
        if secs < 10:
            return T(lang, "just_now")
        d, r = divmod(secs, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        parts = [T(lang, k, n=n) for n, k in ((d, "dur_d"), (h, "dur_h"), (m, "dur_m"), (s, "dur_s")) if n]
        return T(lang, "ago", dur=" ".join(parts[:2]))

    # ---------------- database ----------------
    bot.cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_users (
            room_jid TEXT, nick_key TEXT, nick TEXT, ts REAL, action TEXT, extra TEXT,
            last_msg TEXT, last_msg_ts REAL,
            PRIMARY KEY (room_jid, nick_key)
        )""")
    bot.conn.commit()

    online = {}              # room(lower) -> {nick_lower: nick}
    dirty = {"v": False}

    def record(room, nick, action, extra="", msg=None):
        now = time.time()
        r, k = room.lower(), nick.lower()
        cur = bot.cursor
        if msg is not None:
            cur.execute("UPDATE seen_users SET nick=?, ts=?, action=?, extra=?, last_msg=?, last_msg_ts=? "
                        "WHERE room_jid=? AND nick_key=?", (nick, now, action, extra, msg, now, r, k))
        else:
            cur.execute("UPDATE seen_users SET nick=?, ts=?, action=?, extra=? WHERE room_jid=? AND nick_key=?",
                        (nick, now, action, extra, r, k))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO seen_users (room_jid, nick_key, nick, ts, action, extra, last_msg, last_msg_ts) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (r, k, nick, now, action, extra, msg, now if msg else None))
        dirty["v"] = True

    def is_bot_input(room, text):
        """Pesan untuk bot (perintah / sapaan ke bot) tidak disimpan sebagai 'pesan terakhir'."""
        t = text.strip()
        low = t.lower()
        my = str(bot.get_room_nick(room) or "").lower() if hasattr(bot, "get_room_nick") else ""
        if my and low.startswith(my):
            return True
        prefix = bot.get_room_prefix(room) if hasattr(bot, "get_room_prefix") else ""
        if prefix and t.startswith(prefix):
            return True
        first = low.split()[0] if low.split() else ""
        return first in getattr(bot, "COMMAND_LOOKUP", {})

    # ---------------- penangkap aktivitas ----------------
    async def on_message(msg):
        try:
            if msg.get("type") == "error" or is_history_message(msg):
                return
            from_str = str(msg.get("from", ""))
            if "/" not in from_str:
                return
            room, nick = from_str.split("/", 1)
            body = msg.get("body", "")
            if not nick or not body:
                return
            if nick.lower() == (bot.get_room_nick(room) or "").lower():
                return
            text = " ".join(body.split())
            snippet = None
            if bot.get_setting("seen_store_msg", "1") != "0" and not is_bot_input(room, text):
                snippet = text[:MAX_MSG_LEN] + ("…" if len(text) > MAX_MSG_LEN else "")
            record(room, nick, "msg", msg=snippet)
            online.setdefault(room.lower(), {})[nick.lower()] = nick
        except Exception:
            pass

    async def on_presence(p):
        try:
            room, nick = p["from"].bare, p["from"].resource
            if not nick:
                return
            my = (bot.get_room_nick(room) or "").lower()
            codes, new_nick = set(), None
            ux = p.xml.find(NS_MUC_USER + "x")
            if ux is not None:
                for st in ux.findall(NS_MUC_USER + "status"):
                    codes.add(st.attrib.get("code"))
                item = ux.find(NS_MUC_USER + "item")
                if item is not None:
                    new_nick = item.attrib.get("nick")
            if nick.lower() == my or "110" in codes:
                return
            ptype = p["type"]
            bucket = online.setdefault(room.lower(), {})
            if ptype == "unavailable":
                bucket.pop(nick.lower(), None)
                if "303" in codes and new_nick:
                    record(room, nick, "rename", new_nick)
                else:
                    record(room, nick, "leave")
            elif ptype != "error":
                if nick.lower() not in bucket:
                    bucket[nick.lower()] = nick
                    record(room, nick, "join")
        except Exception:
            pass

    async def maintenance():
        n = 0
        while True:
            await asyncio.sleep(COMMIT_EVERY)
            try:
                if dirty["v"]:
                    bot.conn.commit()
                    dirty["v"] = False
                n += 1
                if n % 180 == 1:
                    bot.cursor.execute("DELETE FROM seen_users WHERE ts < ?", (time.time() - KEEP_DAYS * 86400,))
                    bot.conn.commit()
            except Exception:
                pass

    async def on_session_start(event):
        online.clear()
        t = getattr(bot, "_seen_task", None)
        if t is None or t.done():
            bot._seen_task = asyncio.ensure_future(maintenance())

    async def on_reset(event=None):
        online.clear()

    bot.add_event_handler("groupchat_message", on_message)
    bot.add_event_handler("groupchat_presence", on_presence)
    bot.add_event_handler("session_start", on_session_start)
    bot.add_event_handler("disconnected", on_reset)

    # ---------------- perintah ----------------
    def send_raw(sender, room, is_private, text, nick):
        """Kirim tanpa heuristik emoji reply_user (isi pesan pengguna bisa memuat kata 'gagal', dll.)."""
        if is_private or not room:
            bot.send_message(mto=sender, mbody=text, mtype="chat")
        else:
            bot.send_message(mto=room, mbody=f"{nick}: {text}" if nick else text, mtype="groupchat")

    @bot.command("seen", "👤 Participant & Member")
    async def cmd_seen(sender, room, nick, is_private, args):
        """seen <nick>"""
        lang = get_lang(sender, room)

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if not room:
            return await say(T(lang, "room_only"))
        if not args:
            return await say(f"{T(lang, 'usage_word')} seen <nick>")
        target = " ".join(args).strip().lstrip("@")[:64]
        tl = target.lower()
        if tl == (nick or "").lower():
            return await say(T(lang, "self"))
        if tl == (bot.get_room_nick(room) or "").lower():
            return await say(T(lang, "bot"))

        rl = room.lower()
        row = bot.cursor.execute(
            "SELECT nick, ts, action, extra, last_msg, last_msg_ts FROM seen_users WHERE room_jid=? AND nick_key=?",
            (rl, tl)).fetchone()
        is_online = tl in online.get(rl, {})

        if not row and not is_online:
            esc = tl.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = bot.cursor.execute(
                "SELECT nick FROM seen_users WHERE room_jid=? AND nick_key LIKE ? ESCAPE '\\' ORDER BY ts DESC LIMIT 5",
                (rl, f"%{esc}%")).fetchall()
            text = T(lang, "not_found", target=target)
            if like:
                text += "\n" + T(lang, "maybe", names=", ".join(r[0] for r in like))
            return await say(text)

        name = row[0] if row else target
        lines = []
        if is_online:
            lines.append(T(lang, "online", target=name))
        else:
            _, ts, action, extra, _, _ = row
            act = {"msg": T(lang, "act_msg"), "join": T(lang, "act_join"), "leave": T(lang, "act_leave"),
                   "rename": T(lang, "act_rename", new=extra)}.get(action, T(lang, "act_msg"))
            lines.append(T(lang, "result", target=name, ago=fmt_ago(lang, ts),
                           date=time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)), action=act))
        if row and row[4]:
            lines.append(T(lang, "last_msg", ago=fmt_ago(lang, row[5] or row[1]), msg=row[4]))
        send_raw(sender, room, is_private, "\n".join(lines), nick)
