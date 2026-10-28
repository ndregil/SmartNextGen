# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import time
import os
import re
import sys
import asyncio
import platform
import shutil
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from slixmpp.exceptions import IqError, IqTimeout


def _process_start_time():
    """Waktu mulai proses bot (epoch). Dihitung dari OS; cadangan terakhir: saat plugin dimuat."""
    try:
        import psutil
        return psutil.Process().create_time()
    except Exception:
        pass
    try:
        with open("/proc/self/stat", "r") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        start_ticks = int(fields[19])
        hz = os.sysconf("SC_CLK_TCK")
        with open("/proc/uptime", "r") as f:
            sys_up = float(f.read().split()[0])
        return time.time() - (sys_up - start_ticks / hz)
    except Exception:
        return time.time()


PROCESS_START = _process_start_time()

UPTIME_DEFAULT = {   # cadangan Inggris bila kunci belum ada di lang/cmd_users/<kode>.json
    "uptime_format": "Usage: uptime — bot uptime | uptime <server> — server uptime (example: uptime jabber.org)",
    "uptime_since": "Started",
    "uptime_session": "Connection",
    "uptime_system": "System uptime",
    "uptime_memory": "Memory",
    "uptime_accounts": "Accounts",
    "uptime_server_title": "Server uptime: {server}",
    "uptime_server_up": "Uptime",
    "uptime_server_since": "Running since",
    "uptime_server_software": "Software",
    "uptime_server_latency": "Latency",
    "uptime_server_no_uptime": "Not reported by this server",
    "uptime_server_fail": "Failed to query {server}: no response",
    "uptime_state_online": "online",
    "uptime_state_offline": "offline",
    "uptime_state_stopped": "stopped",
    "uptime_wait": "Please wait a few seconds before querying another server.",
    "uptime_reconnects": "Disconnects",
    "uptime_last_disconnect": "Last disconnect",
    "uptime_commands": "Commands run",
    "uptime_messages": "Messages seen",
    "uptime_cpu": "CPU time",
    "uptime_disk": "Disk free",
    "uptime_server_time": "Server time",
    "uptime_server_features": "Features",
    "uptime_server_contact": "Admin contact",
}
SERVER_RE = re.compile(r"^(?=.{3,253}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z0-9\-]{2,}$")

def register(bot):
    # Otomatis mendeteksi nama plugin dari nama file (yaitu 'cmd_users')
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    
    # Memuat kamus bahasa JSON dari folder lang/cmd_users/ secara otomatis
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def get_lang(sender, room):
        """Mengambil bahasa yang aktif untuk user/room tertentu dengan fallback ke config bot."""
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        key = room if room else str(sender)
        default_fallback = getattr(bot, "global_default_lang", "id")
        return bot.user_languages.get(key, default_fallback)

    def get_m(lang):
        """Helper untuk mengambil kamus bahasa sesuai kode bahasa, dengan fallback ke 'id'."""
        return LANG_MESSAGES.get(lang, LANG_MESSAGES.get("id", {}))

    def T(lang, key, **kw):
        """Terjemahan dengan fallback: bahasa aktif -> en -> id -> nama key."""
        text = None
        for code in (lang, "en", "id"):
            text = LANG_MESSAGES.get(code, {}).get(key)
            if text:
                break
        if not text:
            text = key
        try:
            return text.format(**kw)
        except Exception:
            return text

    # Mengambil nama kategori yang aman berdasarkan terjemahan
    def get_cat(cat_key, lang):
        m = get_m(lang)
        if cat_key == "owner":
            return m.get("cat_owner", "👑 Bot Owner")
        elif cat_key == "master":
            return m.get("cat_master", "🔑 Bot Master")
        elif cat_key == "admin":
            return m.get("cat_admin", "💎 Admin & Owner Group")
        return m.get("cat_participant", "👤 Participant & Member")

    @bot.command("lang", "💎 Admin & Owner Group", aliases=["language"])
    async def cmd_lang(sender, room, nick, is_private, args):
        """lang <lang_code> or lang list"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        if not args:
            answer = m.get("lang_status")
            await bot.reply_user(sender, room, answer, is_private, nick=nick)
            return

        sub_cmd = args[0].lower()
        sub_cmd = {"uk": "ua"}.get(sub_cmd, sub_cmd)   # kode ISO Ukraina
        supported_langs = ["id", "en", "ru", "de", "fr", "ar", "hi", "zh", "jv", "es", "pt", "pl", "it", "fa", "tr", "ua"]

        if sub_cmd == "list":
            langs_str = ", ".join([f"`{l}`" for l in supported_langs])
            answer = T(lang, "lang_list_msg", langs=langs_str)
            await bot.reply_user(sender, room, answer, is_private, nick=nick)
            return

        target_lang = sub_cmd
        if target_lang in supported_langs:
            if hasattr(bot, "set_lang"):
                bot.set_lang(sender, room, target_lang)
            else:
                key = room.lower() if room else str(sender).lower()
                if not hasattr(bot, "user_languages"):
                    bot.user_languages = {}
                bot.user_languages[key] = target_lang

            new_m = get_m(target_lang)
            answer = new_m.get("lang_success")
        else:
            # Jika bahasa tidak valid / tidak ada, arahkan ke lang list
            langs_str = ", ".join([f"`{l}`" for l in supported_langs])
            invalid_text = m.get("lang_invalid")
            list_tip = T(lang, "lang_list_tip", langs=langs_str)
            answer = f"{invalid_text}\n{list_tip}"
        
        await bot.reply_user(sender, room, answer, is_private, nick=nick)

    # ------------------------------------------------------------------
    # UPTIME: bot sendiri (detail) atau server XMPP lain (XEP-0012 + versi + ping)
    # ------------------------------------------------------------------
    def U(lang, key, **kw):
        text = T(lang, key, **kw)
        if text != key:
            return text
        try:
            return UPTIME_DEFAULT.get(key, key).format(**kw)
        except Exception:
            return UPTIME_DEFAULT.get(key, key)

    def fmt_duration(seconds, lang):
        seconds = int(max(0, seconds))
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        parts = []
        if days > 0: parts.append(T(lang, "uptime_days", n=days))
        if hours > 0: parts.append(T(lang, "uptime_hours", n=hours))
        if minutes > 0: parts.append(T(lang, "uptime_minutes", n=minutes))
        parts.append(T(lang, "uptime_seconds", n=secs))
        return ", ".join(parts)

    def get_active_bots():
        main_mod = sys.modules.get("__main__")
        return getattr(main_mod, "ACTIVE_BOT_INSTANCES", {}) if main_mod else {}

    def system_uptime_seconds():
        try:
            with open("/proc/uptime", "r") as f:
                return float(f.read().split()[0])
        except Exception:
            return None

    def memory_rss_mb():
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1048576
        except Exception:
            pass
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024
        except Exception:
            pass
        return None

    # Statistik sejak bot dijalankan: putus koneksi, pesan terlihat, perintah dijalankan
    stats = getattr(bot, "uptime_stats", None)
    if stats is None:
        stats = bot.uptime_stats = {"disconnects": 0, "last_disconnect": None, "commands": 0, "messages": 0}

    async def _count_disconnect(event):
        stats["disconnects"] += 1
        stats["last_disconnect"] = time.time()

    async def _count_message(msg):
        try:
            if msg["type"] != "error" and msg["body"]:
                stats["messages"] += 1
        except Exception:
            pass

    bot.add_event_handler("disconnected", _count_disconnect)
    bot.add_event_handler("message", _count_message)

    _orig_handle_command = bot.handle_command

    async def _counted_handle_command(*a, **k):
        stats["commands"] += 1
        return await _orig_handle_command(*a, **k)

    bot.handle_command = _counted_handle_command

    def bot_uptime_text(lang, room):
        now = time.time()
        lines = [
            T(lang, "uptime_title"),
            f"{T(lang, 'uptime_active')} : {fmt_duration(now - PROCESS_START, lang)}",
            f"{U(lang, 'uptime_since')} : {datetime.fromtimestamp(PROCESS_START).strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        started = getattr(bot, "_session_started_at", None)
        if started is not None:
            lines.append(f"{U(lang, 'uptime_session')} : {fmt_duration(time.monotonic() - started, lang)}")

        rooms_count = 0
        joined = getattr(bot, "joined_rooms", None)
        if joined:
            rooms_count = len(joined)
        if not rooms_count:
            try:
                xep45 = bot.plugin.get("xep_0045") if hasattr(bot.plugin, "get") else getattr(bot.plugin, "xep_0045", None)
                if xep45:
                    rooms_count = len(getattr(xep45, "rooms", {}))
            except Exception:
                pass
        if not rooms_count and hasattr(bot, "room_users"):
            rooms_count = len(bot.room_users)
        lines.append(f"{T(lang, 'uptime_rooms')} : {rooms_count}")
        lines.append(f"{T(lang, 'uptime_pid')} : {os.getpid()}")
        line = f"{U(lang, 'uptime_reconnects')} : {stats['disconnects']}"
        if stats["last_disconnect"]:
            line += f" | {U(lang, 'uptime_last_disconnect')} : {datetime.fromtimestamp(stats['last_disconnect']).strftime('%Y-%m-%d %H:%M:%S')}"
        lines.append(line)
        lines.append(f"{U(lang, 'uptime_messages')} : {stats['messages']} | {U(lang, 'uptime_commands')} : {stats['commands']}")
        cpu_disk = [f"{U(lang, 'uptime_cpu')} : {fmt_duration(time.process_time(), lang)}"]
        try:
            du = shutil.disk_usage(os.getcwd())
            cpu_disk.append(f"{U(lang, 'uptime_disk')} : {du.free / 1e9:.1f} / {du.total / 1e9:.1f} GB")
        except Exception:
            pass
        lines.append(" | ".join(cpu_disk))

        active = get_active_bots()
        if len(active) > 1:
            lines.append(f"{U(lang, 'uptime_accounts')} :")
            for key in sorted(active):
                b = active[key]
                if getattr(b, "manual_stop", False):
                    state = U(lang, "uptime_state_stopped")
                elif getattr(b, "session_active", False):
                    st = getattr(b, "_session_started_at", None)
                    state = U(lang, "uptime_state_online")
                    if st is not None:
                        state += f" — {fmt_duration(time.monotonic() - st, lang)}"
                else:
                    state = U(lang, "uptime_state_offline")
                lines.append(f"  {key.upper()} : {state}")

        sys_up = system_uptime_seconds()
        extra = []
        if sys_up is not None:
            extra.append(fmt_duration(sys_up, lang))
        try:
            extra.append("load " + " ".join(f"{x:.2f}" for x in os.getloadavg()))
        except Exception:
            pass
        if extra:
            lines.append(f"{U(lang, 'uptime_system')} : {' | '.join(extra)}")
        mem = memory_rss_mb()
        if mem is not None:
            lines.append(f"{U(lang, 'uptime_memory')} : {mem:.1f} MB")
        try:
            import slixmpp
            lib = f" | slixmpp {getattr(slixmpp, '__version__', '?')}"
        except Exception:
            lib = ""
        lines.append(f"Python {platform.python_version()}{lib} | {platform.machine()} {platform.python_build()[0]} {platform.uname().version}")
        return "\n".join(lines)

    FEATURE_NAMES = (("urn:xmpp:mam:2", "MAM"), ("urn:xmpp:carbons:2", "Carbons"), ("urn:xmpp:csi:0", "CSI"),
                     ("urn:xmpp:push:0", "Push"), ("urn:xmpp:blocking", "Blocking"), ("jabber:iq:register", "Register"),
                     ("urn:xmpp:bookmarks:1", "Bookmarks"), ("urn:xmpp:http:upload:0", "Upload"))

    def parse_server_time(utc_text, tzo_text):
        """XEP-0202: utc (ISO 8601) + tzo ('+07:00') -> 'YYYY-MM-DD HH:MM:SS (UTC+07:00)'."""
        dt = datetime.fromisoformat((utc_text or "").strip().replace("Z", "+00:00"))
        tzo = (tzo_text or "+00:00").strip()
        sign = -1 if tzo.startswith("-") else 1
        hh, _, mm = tzo.lstrip("+-").partition(":")
        offset = timedelta(hours=int(hh or 0), minutes=int(mm or 0)) * sign
        local = dt.astimezone(timezone(offset))
        return f"{local.strftime('%Y-%m-%d %H:%M:%S')} (UTC{tzo if tzo[:1] in '+-' else '+' + tzo})"

    async def server_uptime_text(server, lang):
        async def q_last():
            iq = bot.make_iq_get(ito=server, ifrom=bot.boundjid)
            iq.append(ET.Element("{jabber:iq:last}query"))
            res = await iq.send(timeout=8)
            q = res.xml.find("{jabber:iq:last}query")
            if q is None or "seconds" not in q.attrib:
                raise ValueError("no seconds")
            return int(float(q.attrib["seconds"]))

        async def q_version():
            res = await bot.plugin["xep_0092"].get_version(server, timeout=8)
            sv = res["software_version"]
            return sv.get("name") or "", sv.get("version") or "", sv.get("os") or ""

        async def q_ping():
            t0 = time.time()
            try:
                await bot.plugin["xep_0199"].ping(jid=server, timeout=8)
            except IqError:
                pass   # server menjawab (walau error) = terjangkau
            return time.time() - t0

        async def q_time():
            iq = bot.make_iq_get(ito=server, ifrom=bot.boundjid)
            iq.append(ET.Element("{urn:xmpp:time}time"))
            res = await iq.send(timeout=8)
            t = res.xml.find("{urn:xmpp:time}time")
            if t is None:
                raise ValueError("no time")
            return parse_server_time(t.findtext("{urn:xmpp:time}utc"), t.findtext("{urn:xmpp:time}tzo"))

        async def q_info():
            """XEP-0030: fitur server + alamat kontak admin (XEP-0157) bila dipublikasikan."""
            res = await bot.plugin["xep_0030"].get_info(jid=server, timeout=8)
            feats = set(res["disco_info"]["features"])
            names = [name for ns, name in FEATURE_NAMES if ns in feats]
            contact = ""
            for var in ("admin-addresses", "support-addresses"):
                for field in res.xml.iter("{jabber:x:data}field"):
                    if field.attrib.get("var") == var:
                        vals = [(v.text or "").strip() for v in field.findall("{jabber:x:data}value") if (v.text or "").strip()]
                        if vals:
                            contact = ", ".join(vals[:2])[:90]
                            break
                if contact:
                    break
            return names, len(feats), contact

        last, ver, lat, stime, info = await asyncio.gather(q_last(), q_version(), q_ping(), q_time(), q_info(),
                                                           return_exceptions=True)
        if all(isinstance(x, Exception) for x in (last, ver, lat, stime, info)):
            return U(lang, "uptime_server_fail", server=server)

        lines = [f"🌐 {U(lang, 'uptime_server_title', server=server)}"]
        if isinstance(last, int):
            since = datetime.fromtimestamp(time.time() - last).strftime("%Y-%m-%d %H:%M")
            lines.append(f"{U(lang, 'uptime_server_up')} : {fmt_duration(last, lang)}")
            lines.append(f"{U(lang, 'uptime_server_since')} : {since}")
        else:
            lines.append(f"{U(lang, 'uptime_server_up')} : {U(lang, 'uptime_server_no_uptime')}")
        if isinstance(ver, tuple) and any(ver):
            name, version, os_ = ver
            soft = " ".join(x for x in (name, version) if x)
            if os_:
                soft += f" ({os_})"
            lines.append(f"{U(lang, 'uptime_server_software')} : {soft}")
        if isinstance(info, tuple):
            names, total, contact = info
            if names or total:
                lines.append(f"{U(lang, 'uptime_server_features')} : {', '.join(names) + ' ' if names else ''}({total})")
            if contact:
                lines.append(f"{U(lang, 'uptime_server_contact')} : {contact}")
        if isinstance(stime, str):
            lines.append(f"{U(lang, 'uptime_server_time')} : {stime}")
        if isinstance(lat, float):
            lines.append(f"{U(lang, 'uptime_server_latency')} : {round(lat, 3)} s")
        return "\n".join(lines)

    _uptime_cool = {}

    @bot.command("uptime", "👤 Participant & Member")
    async def cmd_uptime(sender, room, nick, is_private, args):
        """uptime [server]"""
        lang = get_lang(sender, room)
        try:
            target = args[0].strip().lower() if args else ""
            my_nick = str(bot.get_room_nick(room) or "").lower() if (room and hasattr(bot, "get_room_nick")) else ""
            my_bare = str(getattr(bot, "boundjid", "")).split("/")[0].lower()
            if not target or target in ("bot", my_nick, my_bare):
                answer = bot_uptime_text(lang, room)
            else:
                try:
                    host = target.encode("idna").decode("ascii")
                except Exception:
                    host = ""
                if "@" in target or "/" in target or not SERVER_RE.match(host):
                    answer = U(lang, "uptime_format")
                else:
                    key = (room or "", str(sender).split("/")[0].lower())
                    now = time.time()
                    if now - _uptime_cool.get(key, 0) < 5:
                        answer = U(lang, "uptime_wait")
                    else:
                        _uptime_cool[key] = now
                        if len(_uptime_cool) > 300:
                            for k in [k for k, t in _uptime_cool.items() if now - t > 5]:
                                _uptime_cool.pop(k, None)
                        answer = await server_uptime_text(host, lang)
        except Exception as e:
            answer = T(lang, "uptime_error", error=e)

        await bot.reply_user(sender, room, answer, is_private, nick=nick)

    @bot.command("to_admin", "👤 Participant & Member")
    async def cmd_to_admin(sender, room, nick, is_private, args):
        """to_admin <message content>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not args:
            await bot.reply_user(sender, room, m.get("to_admin_format"), is_private, nick=nick)
            return

        message_text = " ".join(args)
        sender_identity = f"{room}/{nick}" if room and nick else str(sender)
        
        notification = (
            f"{m.get('to_admin_header')}\n"
            f"{m.get('to_admin_from')}: {sender_identity}\n"
            f"{m.get('to_admin_msg')}: {message_text}"
        )

        owners_list = []
        try:
            with open("config.txt", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEFAULT_OWNERS="):
                        _, val = line.split("=", 1)
                        owners_list = [o.strip() for o in val.split(",") if o.strip()]
                        break
        except Exception as e:
            print(f"Error reading config.txt for to_admin: {e}")

        if not owners_list and hasattr(bot, "default_owners"):
            owners_list = bot.default_owners

        if not owners_list:
            await bot.reply_user(sender, room, m.get("to_admin_no_owner"), is_private, nick=nick)
            return

        success_count = 0
        for owner_jid in owners_list:
            try:
                bot.send_message(mto=owner_jid, mbody=notification, mtype="chat")
                success_count += 1
            except Exception as e:
                print(f"Failed to send to_admin message to {owner_jid}: {e}")

        if success_count > 0:
            await bot.reply_user(sender, room, m.get("to_admin_success"), is_private, nick=nick)
        else:
            await bot.reply_user(sender, room, m.get("to_admin_fail"), is_private, nick=nick)

    @bot.command("userslist", "👤 Participant & Member", aliases=["userlist", "user"])
    async def cmd_userslist(sender, room, nick, is_private, args):
        """userslist"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("userlist_muc_only"), is_private, nick=nick)
            return

        try:
            user_names = []
            xep45 = bot.plugin["xep_0045"]
            room_info = xep45.get_roster(room)
            
            if room_info:
                for item in room_info:
                    if isinstance(item, str):
                        user_names.append(item)
                    elif isinstance(item, dict) and "nick" in item:
                        user_names.append(item["nick"])
                    else:
                        user_names.append(str(item))

            if not user_names and hasattr(bot, "room_users"):
                users_dict = bot.room_users.get(room, {})
                user_names = list(users_dict.keys())

            current_bot_nick = bot.get_room_nick(room) if hasattr(bot, "get_room_nick") else ""
            if current_bot_nick and current_bot_nick not in user_names:
                user_names.append(current_bot_nick)

            if not user_names:
                await bot.reply_user(sender, room, m.get("userlist_empty"), is_private, nick=nick)
                return

            user_names = list(set(user_names))
            user_names.sort(key=lambda x: x.lower())
            users_str = ", ".join(user_names)

            answer = (
                f"{m.get('userlist_header').format(count=len(user_names))}\n"
                f"{users_str}"
            )
        except Exception as e:
            answer = m.get("userlist_error").format(error=e)

        await bot.reply_user(sender, room, answer, is_private, nick=nick)

    @bot.command("disco", "👤 Participant & Member", aliases=["discovery"])
    async def cmd_disco(sender, room, nick, is_private, args):
        """disco <server/muc> [page/filter]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not args:
            await bot.reply_user(sender, room, m.get("disco_format"), is_private, nick=nick)
            return

        server = args[0].lower()
        page = 1
        filter_ = None
        remaining_args = args[1:]
        
        if remaining_args:
            tok = remaining_args.pop(0)
            if tok.isdigit():
                page = max(1, int(tok))
                if remaining_args:
                    filter_ = remaining_args.pop(0)
            else:
                filter_ = tok

        if not hasattr(bot, "room_last_disco"):
            bot.room_last_disco = {}
        if room:
            bot.room_last_disco[room] = server

        if room and hasattr(bot, "room_users") and room in bot.room_users and server in bot.room_users[room]:
            server = bot.room_users[room][server].get("jid") or server

        is_muc_target = "@conference" in server or "@muc" in server

        try:
            result = await bot.plugin["xep_0030"].get_items(jid=server, timeout=15)
            
            items = []
            if result:
                if "disco_items" in result and "items" in result["disco_items"]:
                    items = result["disco_items"]["items"]
                elif "items" in result:
                    items = result["items"]

            if not items:
                await bot.reply_user(sender, room, m.get("disco_empty").format(server=server), is_private, nick=nick)
                return

            plain = []
            for item in items:
                if isinstance(item, (list, tuple)):
                    jid = str(item[0]) if len(item) > 0 else ""
                    name = item[2] if len(item) > 2 and item[2] else (item[1] if len(item) > 1 and item[1] else "")
                elif isinstance(item, dict):
                    jid = item.get("jid", "")
                    name = item.get("name", "") or item.get("node", "")
                else:
                    continue

                if not jid:
                    continue

                if is_muc_target:
                    if "/" in jid:
                        display_name = jid.split("/", 1)[1]
                    else:
                        display_name = name if name else jid
                else:
                    display_name = (f"{name} [{jid}]" if name and name != jid else jid)

                if filter_ and filter_.lower() not in jid.lower() and filter_.lower() not in display_name.lower():
                    continue

                plain.append(display_name)

            plain.sort()
            total_items = len(plain)

            if total_items == 0:
                await bot.reply_user(sender, room, m.get("disco_no_match").format(server=server), is_private, nick=nick)
                return

            per_page = 100
            max_pages = (total_items + per_page - 1) // per_page

            if page > max_pages:
                page = max_pages

            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_items = plain[start_idx:end_idx]

            if is_muc_target:
                items_str = ", ".join(page_items)
                title_type = T(lang, "disco_title_muc", server=server)
                page_label = m.get("disco_page_label")
                answer = f"**🔍 {title_type}** [{page_label} {page}/{max_pages}] ({total_items} total):\n{items_str}"
            else:
                result_lines = []
                for i, item_str in enumerate(page_items, start=start_idx + 1):
                    result_lines.append(f"{i}. {item_str}")
                title_type = T(lang, "disco_title_service", server=server)
                page_label = m.get("disco_page_label")
                answer = f"**🔍 {title_type}** [{page_label} {page}/{max_pages}]:\n" + "\n".join(result_lines)
                answer += f"\n\n{m.get('disco_showing').format(start=start_idx + 1, end=start_idx + len(page_items), total=total_items)}"
            
            if max_pages > 1 and page < max_pages:
                answer += f"\n{m.get('disco_next_tip').format(page=page + 1)}"

        except (IqError, IqTimeout):
            answer = m.get("disco_error_timeout").format(server=server)
        except Exception as e:
            answer = m.get("disco_error").format(error=e)

        await bot.reply_user(sender, room, answer, is_private, nick=nick)

    @bot.command("dns", "👤 Participant & Member")
    async def cmd_dns(sender, room, nick, is_private, args):
        """dns <server.tld>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not args:
            await bot.reply_user(sender, room, m.get("dns_format"), is_private, nick=nick)
            return
        try:
            import socket
            ip_address = socket.gethostbyname(args[0])
            await bot.reply_user(sender, room, T(lang, "dns_result", host=args[0], ip=ip_address), is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, m.get("dns_fail").format(error=e), is_private, nick=nick)

    @bot.command("help", "👤 Participant & Member", aliases=["commands", "cmdlist"])
    async def cmd_help(sender, room, nick, is_private, args):
        """help [command]"""
        try:
            lang = get_lang(sender, room)
            m = get_m(lang)
            clean_args = [arg.strip() for arg in args if arg.strip()] if args else []

            command_registry = getattr(bot, "COMMAND_REGISTRY", None)
            if not command_registry and hasattr(bot, "COMMAND_LOOKUP"):
                command_registry = {"General": []}
                for cmd, info in bot.COMMAND_LOOKUP.items():
                    desc = info[0] if isinstance(info, (list, tuple)) else str(info)
                    command_registry["General"].append((cmd, desc))

            if not command_registry:
                await bot.reply_user(sender, room, m.get("help_no_cmds"), is_private, nick=nick)
                return

            if clean_args:
                target_cmd = clean_args[0].lower()
                found_cmd = None
                found_desc = None
                found_category = None

                for category, cmds in command_registry.items():
                    for cmd_syntax, desc in cmds:
                        normalized_syntax = cmd_syntax.replace("/", " ")
                        cmd_tokens = [token.lower() for token in normalized_syntax.split() if token and token != "-"]
                        if target_cmd in cmd_tokens:
                            found_cmd = cmd_syntax
                            found_desc = desc
                            found_category = category
                            break
                    if found_cmd:
                        break

                if found_cmd:
                    cat_lower = found_category.lower()
                    if "admin" in cat_lower:
                        display_cat = get_cat("admin", lang)
                    elif "owner" in cat_lower:
                        display_cat = get_cat("owner", lang)
                    elif "master" in cat_lower:
                        display_cat = get_cat("master", lang)
                    else:
                        display_cat = get_cat("participant", lang)

                    detail_text = (
                        f"{m.get('help_detail_header')}\n"
                        f"{m.get('help_detail_cmd')}: `{found_cmd}`\n"
                        f"{m.get('help_detail_access')}: {display_cat}\n"
                        f"{m.get('help_detail_desc')}: {found_desc}"
                    )
                    await bot.reply_user(sender, room, detail_text, is_private, nick=nick)
                else:
                    await bot.reply_user(sender, room, m.get("help_not_found").format(cmd=target_cmd), is_private, nick=nick)
                return

            room_prefix = bot.get_room_prefix(room) if hasattr(bot, "get_room_prefix") and room else ""
            p_char = room_prefix if room_prefix else T(lang, "help_no_prefix")
            
            categories = list(command_registry.items())
            
            if len(categories) == 0:
                await bot.reply_user(sender, room, m.get("help_no_cmds"), is_private, nick=nick)
                return

            full_text_lines = [
                m.get("help_main_header").format(prefix=p_char),
                m.get("help_tip_cmd"),
                m.get("help_tip_lang"),
                "-----------------------------------"
            ]

            for category, cmds in categories:
                cat_lower = category.lower()
                if "admin" in cat_lower:
                    display_category = get_cat("admin", lang)
                elif "owner" in cat_lower:
                    display_category = get_cat("owner", lang)
                elif "master" in cat_lower:
                    display_category = get_cat("master", lang)
                else:
                    display_category = get_cat("participant", lang)

                full_text_lines.append(f"\n**{display_category}**")
                
                cmd_names = []
                for cmd_syntax, desc in cmds:
                    main_cmd = cmd_syntax.split("/")[0].split()[0] if cmd_syntax else cmd_syntax
                    if room_prefix:
                        # prefix aktif: tampilkan simbol di depan perintah (tanpa prefix: tidak ada simbol)
                        shown = f"{room_prefix}{main_cmd}"
                        if any(ch in room_prefix for ch in "*_~"):
                            shown = f"`{shown}`"   # cegah simbol dibaca sebagai format markdown
                        cmd_names.append(shown)
                    else:
                        cmd_names.append(main_cmd)
                
                full_text_lines.append(", ".join(cmd_names))

            final_message = "\n".join(full_text_lines).strip()
            await bot.reply_user(sender, room, final_message, is_private, nick=nick)

        except Exception as e:
            import traceback
            traceback.print_exc()
            lang = get_lang(sender, room)
            m = get_m(lang)
            await bot.reply_user(sender, room, m.get("help_error").format(error=e), is_private, nick=nick)

    @bot.command("next", "👤 Participant & Member")
    async def cmd_next(sender, room, nick, is_private, args):
        """next <page number>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        server = bot.room_last_disco.get(room) if hasattr(bot, "room_last_disco") and room else None
        if not server:
            await bot.reply_user(sender, room, m.get("next_no_history"), is_private, nick=nick)
            return
        
        page = 1
        filter_ = None
        if args and args[0].isdigit():
            page = max(1, int(args[0]))
            if len(args) > 1:
                filter_ = args[1]
        elif args:
            filter_ = args[0]

        await cmd_disco(sender, room, nick, is_private, [server, str(page)] + ([filter_] if filter_ else []))

    @bot.command("ping", "👤 Participant & Member", aliases=["p"])
    async def cmd_ping(sender, room, nick, is_private, args):
        """ping/ping [nick/server]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        has_target = len(args) > 0
        target = args[0] if has_target else sender
        target_jid = target

        if room and hasattr(bot, "room_users") and room in bot.room_users and target in bot.room_users[room]:
            target_jid = bot.room_users[room][target].get("jid") or target

        try:
            start_time = time.time()
            await bot.plugin["xep_0199"].ping(jid=target_jid, timeout=5)
            
            latency = round(time.time() - start_time, 3)
            
            if not has_target:
                reply_text = m.get("ping_reply").format(latency=latency)
            else:
                reply_text = m.get("ping_reply_target").format(target=target, latency=latency)
                
            await bot.reply_user(sender, room, reply_text, is_private, nick=nick)
            
        except (IqError, IqTimeout):
            await bot.reply_user(sender, room, m.get("ping_fail").format(target=target), is_private, nick=nick)
        except Exception as e:
            await bot.reply_user(sender, room, m.get("ping_error").format(error=e), is_private, nick=nick)

    @bot.command("test", "👤 Participant & Member")
    async def cmd_test(sender, room, nick, is_private, args):
        """test"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        await bot.reply_user(sender, room, m.get("test_success"), is_private, nick=nick)

    @bot.command("version", "👤 Participant & Member", aliases=["v", "ver", "versi"])
    async def cmd_version(sender, room, nick, is_private, args):
        """version/version [nick/server]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        target_query = " ".join(args) if args else None
        
        current_bot_nick = bot.get_room_nick(room) if hasattr(bot, "get_room_nick") and room else ""
        bot_bare_jid = str(bot.boundjid).split("/")[0].lower() if hasattr(bot, "boundjid") else ""
        
        is_querying_bot = False
        if target_query:
            t_lower = target_query.lower()
            if t_lower == "bot" or (room and t_lower == current_bot_nick.lower()) or t_lower == bot_bare_jid:
                is_querying_bot = True

        if is_querying_bot and hasattr(bot, "get_bot_version_info"):
            name, ver, os_str = bot.get_bot_version_info()
            display_target = target_query
            
            answer = (
                f"{m.get('version_client_info').format(target=display_target)}\n"
                f"  {m.get('version_name')} : {name}\n"
                f"  {m.get('version_ver')} : {ver}\n"
                f"  {m.get('version_os')} : {os_str}"
            )
            await bot.reply_user(sender, room, answer, is_private, nick=nick)
            return

        cands = []
        if target_query:
            if room and hasattr(bot, "room_users") and room in bot.room_users and target_query in bot.room_users[room]:
                real_jid = bot.room_users[room][target_query].get("jid")
                if real_jid:
                    cands.append(real_jid)
                cands.append(f"{room}/{target_query}")
            cands.append(target_query)
        else:
            if room and nick:
                if hasattr(bot, "room_users") and room in bot.room_users and nick in bot.room_users[room]:
                    real_jid = bot.room_users[room][nick].get("jid")
                    if real_jid:
                        cands.append(real_jid)
                cands.append(f"{room}/{nick}")
            if sender:
                cands.append(str(sender).split("/")[0])
                cands.append(str(sender))

        seen = set()
        unique_cands = [x for x in cands if not (x in seen or seen.add(x))]

        if not unique_cands:
            await bot.reply_user(sender, room, m.get("version_invalid_target"), is_private, nick=nick)
            return

        result = None
        if target_query:
            display_target = target_query
        elif room and nick:
            display_target = nick
        else:
            display_target = str(sender).split("/")[0]

        for t_jid in unique_cands:
            try:
                res = await bot.plugin["xep_0092"].get_version(t_jid, timeout=5)
                if res is not None:
                    result = res
                    break
            except Exception:
                continue

        if result is not None:
            try:
                sv   = result["software_version"]
                name = sv.get("name")    or "[None]"
                ver  = sv.get("version") or "[None]"
                os_  = sv.get("os")      or "[None]"
            except Exception:
                try:
                    xml  = getattr(result, "xml", result)
                    ns   = "jabber:iq:version"
                    q    = xml.find(".//{%s}query" % ns) if hasattr(xml, "find") else None
                    if q is None:
                        q = xml
                    name = (q.findtext("{%s}name" % ns) or q.findtext("name") or "[None]").strip()
                    ver  = (q.findtext("{%s}version" % ns) or q.findtext("version") or "[None]").strip()
                    os_  = (q.findtext("{%s}os" % ns) or q.findtext("os") or "[None]").strip()
                except Exception:
                    name = ver = os_ = "[None]"

            answer = (
                f"{m.get('version_client_info').format(target=display_target)}\n"
                f"  {m.get('version_name')} : {name}\n"
                f"  {m.get('version_ver')} : {ver}\n"
                f"  {m.get('version_os')} : {os_}"
            )
        else:
            answer = m.get("version_fail").format(target=display_target)

        await bot.reply_user(sender, room, answer, is_private, nick=nick)
