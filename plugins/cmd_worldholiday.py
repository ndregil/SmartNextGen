# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot - Plugin Libur Internasional
# Sumber data: Nager.Date (https://date.nager.at) - gratis, tanpa API key, 100+ negara.
#
# Perintah (alias: holidays):
#   worldholiday                    -> 5 libur nasional mendatang negara bawaan (setting 'holiday_country', bawaan ID)
#   worldholiday <negara>           -> 5 libur mendatang negara itu (kode ISO "JP" atau nama "japan", "jepang")
#   worldholiday <negara> <1-12>    -> libur pada bulan tertentu tahun ini
#   worldholiday <negara> year      -> semua libur tahun ini
#   worldholiday today              -> negara yang libur nasional hari ini
#   worldholiday world              -> libur di seluruh dunia 7 hari ke depan
#   worldholiday countries          -> daftar kode negara yang tersedia
#   holidayalert add|del|list <negara> -> (admin room) umumkan otomatis tiap pagi bila negara itu libur nasional
# Perintah 'holiday' (Indonesia + akhir pekan) di cmd_info.py tidak diubah.

import asyncio
import datetime
import logging
import os
import time

import aiohttp

BASE = "https://date.nager.at/api/v3"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SmartNG-Holiday/1.0)", "Accept": "application/json"}
TIMEOUT = 10
CACHE_TTL = 3600.0
COUNTRY_TTL = 86400.0
MAX_LINES = 20
NEXT_COUNT = 5
USER_COOLDOWN = 3.0
DEFAULT_COUNTRY = "ID"
ALERT_HOUR = 7           # jam (waktu server) pengumuman libur otomatis; ubah lewat setting 'holiday_alert_hour'
MAX_ALERTS = 5           # maksimal negara yang diumumkan per room

# Nama populer / bahasa Indonesia -> kode ISO (nama Inggris resmi dicocokkan dari data API)
COUNTRY_ALIASES = {
    "uk": "GB", "england": "GB", "inggris": "GB", "britain": "GB", "usa": "US", "america": "US", "amerika": "US",
    "korea": "KR", "korsel": "KR", "korea selatan": "KR", "uae": "AE", "emirates": "AE", "jepang": "JP",
    "jerman": "DE", "prancis": "FR", "perancis": "FR", "belanda": "NL", "arab saudi": "SA", "saudi": "SA",
    "singapura": "SG", "tiongkok": "CN", "cina": "CN", "china": "CN", "rusia": "RU", "turki": "TR",
    "turkey": "TR", "spanyol": "ES", "italia": "IT", "brasil": "BR", "meksiko": "MX", "selandia baru": "NZ",
    "yunani": "GR", "swiss": "CH", "swedia": "SE", "norwegia": "NO", "denmark": "DK", "polandia": "PL",
    "ukraina": "UA", "mesir": "EG", "afrika selatan": "ZA", "filipina": "PH", "vietnam": "VN", "thailand": "TH",
}


class ApiError(Exception):
    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


_cache = {}


def as_list(data):
    if isinstance(data, dict):
        data = data.get("holidays") or data.get("countries") or []
    return data if isinstance(data, list) else []


async def api_get(path, ttl=CACHE_TTL):
    now = time.time()
    hit = _cache.get(path)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=TIMEOUT), headers=HEADERS) as s:
            async with s.get(BASE + path) as r:
                if r.status == 204:
                    data = []
                elif r.status != 200:
                    raise ApiError(f"HTTP {r.status}")
                else:
                    data = await r.json(content_type=None)
    except ApiError:
        raise
    except asyncio.TimeoutError:
        raise ApiError("timeout")
    except (aiohttp.ClientError, ValueError, OSError) as e:
        raise ApiError(type(e).__name__)
    if len(_cache) > 200:
        _cache.clear()
    _cache[path] = (now, data)
    return data


def clean(text):
    return " ".join(str(text or "").split())


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

    async def get_countries():
        data = as_list(await api_get("/AvailableCountries", COUNTRY_TTL))
        return {clean(c.get("countryCode")).upper(): clean(c.get("name")) for c in data
                if isinstance(c, dict) and c.get("countryCode")}

    def resolve(query, countries):
        """Return ('ok', code, name) | ('many', [nama...]) | ('none',)."""
        q = clean(query).lower()
        if not q:
            return ("none",)
        if len(q) == 2 and q.upper() in countries:
            return ("ok", q.upper(), countries[q.upper()])
        alias = COUNTRY_ALIASES.get(q)
        if alias and alias in countries:
            return ("ok", alias, countries[alias])
        exact = [c for c, n in countries.items() if n.lower() == q]
        if exact:
            return ("ok", exact[0], countries[exact[0]])
        if len(q) < 3:
            return ("none",)
        for test in (lambda n: n.lower().startswith(q), lambda n: q in n.lower()):
            hits = [c for c, n in countries.items() if test(n)]
            if len(hits) == 1:
                return ("ok", hits[0], countries[hits[0]])
            if len(hits) > 1:
                return ("many", [f"{countries[c]} ({c})" for c in sorted(hits, key=lambda c: countries[c])[:5]])
        return ("none",)

    def delta_text(lang, d, today):
        n = (d - today).days
        if n == 0:
            return T(lang, "today")
        if n == 1:
            return T(lang, "tomorrow")
        return T(lang, "in_days", n=n) if n > 1 else ""

    def is_public(h):
        types = h.get("types")
        return (not types) or ("Public" in types)

    def fmt_item(lang, h, today):
        try:
            d = datetime.date.fromisoformat(str(h.get("date"))[:10])
        except ValueError:
            return None
        name, local = clean(h.get("name")), clean(h.get("localName"))
        label = name if (not local or local.lower() == name.lower()) else f"{name} ({local})"
        line = f"• {d.isoformat()} — {label or local}"
        dt = delta_text(lang, d, today)
        if dt:
            line += f" · {dt}"
        if h.get("global") is False:
            line += f" [{T(lang, 'regional')}]"
        return line

    def cap(lines, lang):
        if len(lines) > MAX_LINES:
            extra = len(lines) - MAX_LINES
            lines = lines[:MAX_LINES] + [T(lang, "more", n=extra)]
        return lines

    def group_world(items):
        grouped = {}
        for h in items:
            if not isinstance(h, dict):
                continue
            key = (str(h.get("date"))[:10], clean(h.get("name")) or clean(h.get("localName")))
            grouped.setdefault(key, set()).add(clean(h.get("countryCode")).upper())
        return sorted(grouped.items())

    cool = {}

    @bot.command("worldholiday", "👤 Participant & Member", aliases=["holidays"])
    async def cmd_worldholiday(sender, room, nick, is_private, args):
        """worldholiday [country/month/year]"""
        lang = get_lang(sender, room)

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        now_t = time.time()
        ck = (room or "", str(sender).split("/")[0].lower())
        if now_t - cool.get(ck, 0) < USER_COOLDOWN:
            return
        cool[ck] = now_t
        if len(cool) > 500:
            for k in [k for k, t in cool.items() if now_t - t > USER_COOLDOWN]:
                cool.pop(k, None)

        today = datetime.date.today()
        words = [a for a in args if a.strip()]
        first = words[0].lower() if words else ""
        try:
            if first in ("today", "world"):
                items = as_list(await api_get("/NextPublicHolidaysWorldwide"))
                if first == "today":
                    items = [h for h in items if isinstance(h, dict) and str(h.get("date"))[:10] == today.isoformat()]
                groups = group_world(items)
                if not groups:
                    return await say(T(lang, "none"))
                lines = [f"• {d} — {n}: {', '.join(sorted(codes))}" for (d, n), codes in groups]
                head = T(lang, "header_today" if first == "today" else "header_world")
                return await say(head + "\n" + "\n".join(cap(lines, lang)))

            countries = await get_countries()
            if first == "countries":
                return await say(T(lang, "countries_header", count=len(countries)) + "\n" + ", ".join(sorted(countries)))

            mode, month = "next", None
            if words:
                last = words[-1].lower()
                if last in ("year", "next"):
                    mode = last
                    words = words[:-1]
                elif last.isdigit() and 1 <= int(last) <= 12:
                    mode, month = "month", int(last)
                    words = words[:-1]
            query = " ".join(words).strip()
            if not query:
                query = str(bot.get_setting("holiday_country", DEFAULT_COUNTRY) or DEFAULT_COUNTRY)
            res = resolve(query, countries)
            if res[0] == "none":
                return await say(T(lang, "not_found", query=query[:40]))
            if res[0] == "many":
                return await say(T(lang, "ambiguous", query=query[:40], options=", ".join(res[1])))
            _, code, name = res

            if mode in ("next",):
                items = [h for h in as_list(await api_get(f"/NextPublicHolidays/{code}")) if isinstance(h, dict)]
                lines = [l for l in (fmt_item(lang, h, today) for h in items[:NEXT_COUNT]) if l]
                head = T(lang, "header_next", country=name, code=code)
            else:
                items = [h for h in as_list(await api_get(f"/PublicHolidays/{today.year}/{code}"))
                         if isinstance(h, dict) and is_public(h)]
                items.sort(key=lambda h: str(h.get("date")))
                if mode == "month":
                    items = [h for h in items if str(h.get("date"))[5:7] == f"{month:02d}"]
                    head = T(lang, "header_month", country=name, code=code, month=month, year=today.year)
                else:
                    head = T(lang, "header_year", country=name, code=code, year=today.year)
                lines = [l for l in (fmt_item(lang, h, today) for h in items) if l]
            if not lines:
                return await say(T(lang, "none"))
            await say(head + "\n" + "\n".join(cap(lines, lang)))
        except ApiError as e:
            await say(T(lang, "fail", err=e.detail))
        except Exception as e:
            await say(T(lang, "fail", err=type(e).__name__))

    # ------------------------------------------------------------------
    # Pengumuman libur otomatis per room (hanya libur yang berlaku nasional)
    # ------------------------------------------------------------------
    bot.cursor.execute("CREATE TABLE IF NOT EXISTS holiday_alerts "
                       "(room_jid TEXT, code TEXT, last_date TEXT, PRIMARY KEY (room_jid, code))")
    bot.conn.commit()

    def alert_hour():
        try:
            return min(23, max(0, int(bot.get_setting("holiday_alert_hour", str(ALERT_HOUR)))))
        except ValueError:
            return ALERT_HOUR

    def room_is_joined(room):
        jr = getattr(bot, "joined_rooms", None)
        return True if jr is None else room.lower() in jr

    async def check_alerts():
        now = datetime.datetime.now()
        if now.hour < alert_hour():
            return
        today = now.date().isoformat()
        rows = bot.cursor.execute("SELECT room_jid, code FROM holiday_alerts WHERE last_date IS NULL OR last_date != ?",
                                  (today,)).fetchall()
        by_room = {}
        for r, c in rows:
            by_room.setdefault(r, []).append(c)
        if not by_room:
            return
        try:
            countries = await get_countries()
        except ApiError:
            countries = {}
        for room, codes in by_room.items():
            if not room_is_joined(room):
                continue
            lang = get_lang(None, room)
            lines, done = [], []
            for code in codes:
                if code == "ID" and getattr(bot, "holiday_id_by_info", False):
                    done.append(code)   # libur Indonesia diumumkan oleh cmd_info (hindari ganda)
                    continue
                try:
                    items = as_list(await api_get(f"/PublicHolidays/{now.year}/{code}"))
                except ApiError:
                    continue   # dicoba lagi di putaran berikutnya
                names = []
                for h in items:
                    if (isinstance(h, dict) and is_public(h) and h.get("global") is not False
                            and str(h.get("date"))[:10] == today):
                        n, l = clean(h.get("name")), clean(h.get("localName"))
                        names.append(n if (not l or l.lower() == n.lower()) else f"{n} ({l})")
                done.append(code)
                if names:
                    lines.append(T(lang, "alert_today", country=countries.get(code, code), code=code,
                                   holiday=", ".join(names)))
            if lines:
                try:
                    bot.send_message(mto=room, mbody="\n".join(lines), mtype="groupchat")
                except Exception as e:
                    logging.error(f"Gagal mengirim pengumuman libur ke {room}: {e}")
            if done:
                bot.cursor.executemany("UPDATE holiday_alerts SET last_date=? WHERE room_jid=? AND code=?",
                                       [(today, room, c) for c in done])
                bot.conn.commit()
            await asyncio.sleep(1)

    async def alert_loop():
        await asyncio.sleep(90)
        while True:
            try:
                await check_alerts()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"Error pengumuman libur: {e}")
            await asyncio.sleep(900)

    async def start_alert_task(event):
        t = getattr(bot, "_holiday_task", None)   # satu task per bot walau reconnect berkali-kali
        if t is None or t.done():
            bot._holiday_task = asyncio.ensure_future(alert_loop())

    bot.add_event_handler("session_start", start_alert_task)
    bot.holiday_check_alerts = check_alerts

    def is_exempt(room, nick):
        info = bot.room_users.get(room, {}).get(nick) or {}
        return info.get("affiliation") in ("owner", "admin") or info.get("role") == "moderator"

    async def is_staff(sender, room, nick):
        if is_exempt(room, nick):
            return True
        try:
            return bool(await bot.verify_real_owner_from_server(room, nick, sender))
        except Exception:
            return False

    @bot.command("holidayalert", "💎 Admin & Owner Group")
    async def cmd_holidayalert(sender, room, nick, is_private, args):
        """holidayalert <add/del/list> <country>"""
        lang = get_lang(sender, room)

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if not room:
            return await say(T(lang, "room_only"))
        if not await is_staff(sender, room, nick):
            return await say(T(lang, "mod_only"))
        rl = room.lower()
        sub = args[0].lower() if args else "list"
        try:
            countries = await get_countries()
        except ApiError as e:
            return await say(T(lang, "fail", err=e.detail))
        cur = [r[0] for r in bot.cursor.execute("SELECT code FROM holiday_alerts WHERE room_jid=? ORDER BY rowid", (rl,))]

        if sub == "list":
            if not cur:
                return await say(T(lang, "alert_empty"))
            return await say(T(lang, "alert_list", items=", ".join(f"{countries.get(c, c)} ({c})" for c in cur)))
        if sub not in ("add", "del") or len(args) < 2:
            return await say(f"{T(lang, 'usage_word')} holidayalert add|del|list <country>")
        query = " ".join(args[1:])
        res = resolve(query, countries)
        if res[0] == "none":
            return await say(T(lang, "not_found", query=query[:40]))
        if res[0] == "many":
            return await say(T(lang, "ambiguous", query=query[:40], options=", ".join(res[1])))
        _, code, name = res
        if sub == "add":
            if code in cur:
                return await say(T(lang, "alert_exists", country=name))
            if len(cur) >= MAX_ALERTS:
                return await say(T(lang, "alert_limit", max=MAX_ALERTS))
            bot.cursor.execute("INSERT OR IGNORE INTO holiday_alerts (room_jid, code, last_date) VALUES (?, ?, NULL)",
                               (rl, code))
            bot.conn.commit()
            return await say(T(lang, "alert_added", country=name, code=code))
        if code not in cur:
            return await say(T(lang, "alert_not_in", country=name))
        bot.cursor.execute("DELETE FROM holiday_alerts WHERE room_jid=? AND code=?", (rl, code))
        bot.conn.commit()
        await say(T(lang, "alert_removed", country=name, code=code))
