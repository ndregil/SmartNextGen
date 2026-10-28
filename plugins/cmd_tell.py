# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot - Plugin "tell"
# Titip pesan untuk user yang sedang tidak ada; disampaikan saat dia bicara / masuk room lagi.
# Perintah: tell <nick> <pesan>   |   untell <nick>   (batalkan titipan Anda)

import asyncio
import os
import re
import time

MAX_LEN = 300
MAX_PER_TARGET = 10
MAX_PER_USER = 10
EXPIRE_DAYS = 30
COOLDOWN = 3.0
JOIN_GRACE = 20.0        # detik setelah bot masuk room: presence awal tidak dianggap 'baru masuk'
NS_MUC_USER = "{http://jabber.org/protocol/muc#user}"


def is_history_message(msg):
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

    bot.cursor.execute("""
        CREATE TABLE IF NOT EXISTS tell_msgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_jid TEXT, target_key TEXT, target_jid TEXT,
            from_nick TEXT, from_key TEXT, text TEXT, ts REAL
        )""")
    bot.cursor.execute("CREATE INDEX IF NOT EXISTS idx_tell_target ON tell_msgs (room_jid, target_key)")
    bot.conn.commit()

    online = {}          # room(lower) -> {nick_lower: nick}
    room_first = {}      # room(lower) -> waktu presence pertama pada sesi ini
    cool = {}

    def bare_jid(room, nick):
        info = (bot.room_users.get(room) or {}).get(nick) or {}
        j = info.get("jid")
        return str(j).split("/")[0].lower() if j else ""

    def clean(text):
        return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", text).split())

    def split_target(room, args):
        joined = " ".join(args).strip()
        if joined.startswith("@"):
            joined = joined[1:]
        known = set((bot.room_users.get(room) or {}).keys()) | set(online.get(room.lower(), {}).values())
        for n in sorted(known, key=len, reverse=True):
            if joined.lower().startswith(n.lower()) and (len(joined) == len(n) or joined[len(n)].isspace()):
                return n, joined[len(n):].strip()
        parts = joined.split(None, 1)
        return (parts[0].rstrip(":,") if parts else ""), (parts[1] if len(parts) > 1 else "")

    # ---------------- pengiriman ----------------
    def pop_pending(room, nick, jid):
        r = room.lower()
        rows = bot.cursor.execute(
            "SELECT id, from_nick, text, ts FROM tell_msgs WHERE room_jid=? AND "
            "(target_key=? OR (target_jid != '' AND target_jid=?)) ORDER BY ts LIMIT 10",
            (r, nick.lower(), jid or "\x00")).fetchall()
        if rows:
            bot.cursor.executemany("DELETE FROM tell_msgs WHERE id=?", [(x[0],) for x in rows])
            bot.conn.commit()
        return rows

    async def deliver(room, nick, jid="", delay=0.0):
        rows = pop_pending(room, nick, jid)
        if not rows:
            return
        lang = get_lang(None, room)
        lines = [T(lang, "header", nick=nick, count=len(rows))]
        lines += [T(lang, "item", from_nick=f, ago=fmt_ago(lang, ts), text=t) for _, f, t, ts in rows]
        if delay:
            await asyncio.sleep(delay)
        bot.send_message(mto=room, mbody="\n".join(lines), mtype="groupchat")

    async def on_message(msg):
        try:
            if msg.get("type") == "error" or is_history_message(msg) or not msg.get("body", ""):
                return
            from_str = str(msg.get("from", ""))
            if "/" not in from_str:
                return
            room, nick = from_str.split("/", 1)
            if not nick or nick.lower() == (bot.get_room_nick(room) or "").lower():
                return
            online.setdefault(room.lower(), {})[nick.lower()] = nick
            await deliver(room, nick, bare_jid(room, nick))
        except Exception:
            pass

    async def on_presence(p):
        try:
            room, nick = p["from"].bare, p["from"].resource
            if not nick:
                return
            rl = room.lower()
            now = time.time()
            first = room_first.setdefault(rl, now)
            if nick.lower() == (bot.get_room_nick(room) or "").lower():
                return
            ptype = p["type"]
            bucket = online.setdefault(rl, {})
            if ptype == "unavailable":
                bucket.pop(nick.lower(), None)
                return
            if ptype == "error":
                return
            real = ""
            ux = p.xml.find(NS_MUC_USER + "x")
            if ux is not None:
                for st in ux.findall(NS_MUC_USER + "status"):
                    if st.attrib.get("code") == "110":
                        return
                item = ux.find(NS_MUC_USER + "item")
                if item is not None and item.attrib.get("jid"):
                    real = item.attrib["jid"].split("/")[0].lower()
            if nick.lower() not in bucket:
                bucket[nick.lower()] = nick
                if now - first > JOIN_GRACE:   # presence awal saat bot baru masuk diabaikan
                    await deliver(room, nick, real or bare_jid(room, nick), delay=2.0)
        except Exception:
            pass

    async def on_reset(event=None):
        online.clear()
        room_first.clear()

    async def maintenance():
        while True:
            try:
                bot.cursor.execute("DELETE FROM tell_msgs WHERE ts < ?", (time.time() - EXPIRE_DAYS * 86400,))
                bot.conn.commit()
            except Exception:
                pass
            await asyncio.sleep(6 * 3600)

    async def on_session_start(event):
        await on_reset()
        t = getattr(bot, "_tell_task", None)
        if t is None or t.done():
            bot._tell_task = asyncio.ensure_future(maintenance())

    bot.add_event_handler("groupchat_message", on_message)
    bot.add_event_handler("groupchat_presence", on_presence)
    bot.add_event_handler("session_start", on_session_start)
    bot.add_event_handler("disconnected", on_reset)

    # ---------------- perintah ----------------
    @bot.command("tell", "👤 Participant & Member")
    async def cmd_tell(sender, room, nick, is_private, args):
        """tell <nick> <message>"""
        lang = get_lang(sender, room)

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if not room:
            return await say(T(lang, "room_only"))
        target, text = split_target(room, args)
        text = clean(text)
        if not target or not text:
            return await say(f"{T(lang, 'usage_word')} tell <nick> <message>")
        tl = target.lower()
        sender_jid = bare_jid(room, nick) or str(sender).split("/")[0].lower()
        target_jid = bare_jid(room, target)
        if tl == (nick or "").lower() or (target_jid and target_jid == sender_jid):
            return await say(T(lang, "self"))
        if tl == (bot.get_room_nick(room) or "").lower():
            return await say(T(lang, "bot"))
        if len(text) > MAX_LEN:
            return await say(T(lang, "too_long", max=MAX_LEN))

        now = time.time()
        ck = (room.lower(), sender_jid)
        if now - cool.get(ck, 0) < COOLDOWN:
            return await say(T(lang, "cooldown"))
        cool[ck] = now
        if len(cool) > 500:
            for k in [k for k, t in cool.items() if now - t > COOLDOWN]:
                cool.pop(k, None)

        r = room.lower()
        n_target = bot.cursor.execute("SELECT COUNT(*) FROM tell_msgs WHERE room_jid=? AND target_key=?",
                                      (r, tl)).fetchone()[0]
        if n_target >= MAX_PER_TARGET:
            return await say(T(lang, "limit_target", target=target, max=MAX_PER_TARGET))
        n_user = bot.cursor.execute("SELECT COUNT(*) FROM tell_msgs WHERE room_jid=? AND from_key=?",
                                    (r, sender_jid)).fetchone()[0]
        if n_user >= MAX_PER_USER:
            return await say(T(lang, "limit_user", max=MAX_PER_USER))

        bot.cursor.execute(
            "INSERT INTO tell_msgs (room_jid, target_key, target_jid, from_nick, from_key, text, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", (r, tl, target_jid, nick or "?", sender_jid, text, now))
        bot.conn.commit()
        await say(T(lang, "saved", target=target))

    @bot.command("untell", "👤 Participant & Member")
    async def cmd_untell(sender, room, nick, is_private, args):
        """untell <nick>"""
        lang = get_lang(sender, room)

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if not room:
            return await say(T(lang, "room_only"))
        if not args:
            return await say(f"{T(lang, 'usage_word')} untell <nick>")
        target = " ".join(args).strip().lstrip("@")
        sender_jid = bare_jid(room, nick) or str(sender).split("/")[0].lower()
        bot.cursor.execute("DELETE FROM tell_msgs WHERE room_jid=? AND target_key=? AND from_key=?",
                           (room.lower(), target.lower(), sender_jid))
        n = bot.cursor.rowcount
        bot.conn.commit()
        await say(T(lang, "untell_done", count=n, target=target) if n
                  else T(lang, "untell_none", target=target))
