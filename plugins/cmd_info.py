# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import aiohttp
import asyncio
import datetime
import os

# Variabel global untuk menghindari spam broadcast di hari/libur yang sama
last_broadcasted_quake_id = None
last_notified_holiday_date = None

async def fetch_next_holiday():
    """Mengambil data hari libur nasional resmi Indonesia secara dinamis."""
    today = datetime.date.today()
    current_year = today.year
    years_to_check = [current_year, current_year + 1]
    
    upcoming = []
    
    async with aiohttp.ClientSession() as session:
        for year in years_to_check:
            url = f"https://api-hari-libur.vercel.app/api?year={year}"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        
                        holidays = []
                        if isinstance(res_json, list):
                            holidays = res_json
                        elif isinstance(res_json, dict):
                            for k in ["holiday", "holidays", "data", "result", "results"]:
                                if k in res_json and isinstance(res_json[k], list):
                                    holidays = res_json[k]
                                    break
                            if not holidays:
                                for val in res_json.values():
                                    if isinstance(val, list):
                                        holidays = val
                                        break

                        for h in holidays:
                            if not isinstance(h, dict):
                                continue
                            
                            is_national = True
                            for n_key in ["is_national_holiday", "national_holiday", "is_holiday"]:
                                if n_key in h:
                                    val = h[n_key]
                                    if isinstance(val, bool) and not val:
                                        is_national = False
                                    break
                            
                            if not is_national:
                                continue
                                
                            date_str = None
                            for d_key in ["holiday_date", "date", "tanggal", "start_date"]:
                                if d_key in h and h[d_key]:
                                    date_str = str(h[d_key])
                                    break
                                    
                            name_str = None
                            for name_key in ["holiday_name", "name", "summary", "title", "description"]:
                                if name_key in h and h[name_key]:
                                    name_str = str(h[name_key])
                                    break
                            
                            if date_str and name_str:
                                try:
                                    clean_date = date_str[:10]
                                    h_date = datetime.datetime.strptime(clean_date, "%Y-%m-%d").date()
                                    delta = (h_date - today).days
                                    if delta >= 0:
                                        if not any(item["date"] == clean_date for item in upcoming):
                                            upcoming.append({"name": name_str, "date": clean_date, "days": delta})
                                except Exception:
                                    pass
            except Exception:
                pass
            
            if upcoming:
                break

    if upcoming:
        upcoming.sort(key=lambda x: x["days"])
        return upcoming[0]
        
    return None

def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    # Siaran libur nasional Indonesia (data khusus Indonesia) kini opt-in per room:
    # hanya room yang menjalankan  holidayalert add id  (cmd_worldholiday). Plugin itu
    # melewati kode ID agar pengumuman tidak ganda.
    bot.holiday_id_by_info = True

    def id_alert_rooms():
        try:
            bot.cursor.execute("CREATE TABLE IF NOT EXISTS holiday_alerts "
                               "(room_jid TEXT, code TEXT, last_date TEXT, PRIMARY KEY (room_jid, code))")
            bot.conn.commit()
            rows = bot.cursor.execute("SELECT room_jid FROM holiday_alerts WHERE code = 'ID'").fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    bot.holiday_id_rooms = id_alert_rooms

    # Mengambil bahasa aktif langsung dari sistem inti bot agar terpusat
    def get_lang(sender, room):
        """Mengambil bahasa aktif secara sinkron langsung dari database/sistem inti bot."""
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        # Fallback lokal jika inti bot belum menyediakan fungsi get_lang
        if not hasattr(bot, "user_languages"):
            bot.user_languages = {}
        key = room if room else str(sender)
        return bot.user_languages.get(key, "id")

    def get_m(lang):
        """Helper untuk mengambil kamus bahasa dengan fallback aman ke 'id'."""
        return LANG_MESSAGES.get(lang, LANG_MESSAGES.get("id", {}))

    @bot.command("earthquake", "👤 Participant & Member", aliases=["gempa"])
    async def cmd_earthquake(sender, room, nick, is_private, args):
        """earthquake/gempa"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        mode = args[0].lower() if args else "id"
        
        loading_msg = m.get("quake_loading")
        await bot.reply_user(sender, room, loading_msg, is_private, nick=nick)

        try:
            async with aiohttp.ClientSession() as session:
                if mode in ["us", "global", "world"]:
                    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_hour.geojson"
                    async with session.get(url, timeout=10) as resp:
                        if resp.status != 200:
                            err = m.get("quake_usgs_fail")
                            await bot.reply_user(sender, room, err, is_private, nick=nick)
                            return
                        data = await resp.json()
                        features = data.get("features", [])
                        
                        if not features:
                            no_data = m.get("quake_usgs_empty")
                            await bot.reply_user(sender, room, no_data, is_private, nick=nick)
                            return

                        latest = features[0]["properties"]
                        place = latest.get("place", m.get("quake_usgs_unknown"))
                        mag = latest.get("mag", "-")
                        time_epoch = latest.get("time", 0) / 1000.0
                        time_str = datetime.datetime.fromtimestamp(time_epoch).strftime('%Y-%m-%d %H:%M:%S')

                        reply_text = m.get("quake_usgs_result").format(
                            mag=mag,
                            place=place,
                            time_str=time_str
                        )
                        await bot.reply_user(sender, room, reply_text, is_private, nick=nick)

                else:
                    url = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
                    async with session.get(url, timeout=10) as resp:
                        if resp.status != 200:
                            err = m.get("quake_bmkg_fail")
                            await bot.reply_user(sender, room, err, is_private, nick=nick)
                            return
                        data = await resp.json()
                        infogempa = data.get("Infogempa", {}).get("gempa", {})
                        
                        if not infogempa:
                            err_fmt = m.get("quake_bmkg_empty")
                            await bot.reply_user(sender, room, err_fmt, is_private, nick=nick)
                            return

                        tanggal = infogempa.get("Tanggal", "-")
                        jam = infogempa.get("Jam", "-")
                        coordinates = infogempa.get("Coordinates", "-")
                        magnitude = infogempa.get("Magnitude", "-")
                        kedalaman = infogempa.get("Kedalaman", "-")
                        wilayah = infogempa.get("Wilayah", "-")
                        potensi = infogempa.get("Potensi", "-")
                        dirasakan = infogempa.get("Dirasakan", m.get("quake_bmkg_no_info"))

                        reply_text = m.get("quake_bmkg_result").format(
                            tanggal=tanggal,
                            jam=jam,
                            magnitude=magnitude,
                            kedalaman=kedalaman,
                            wilayah=wilayah,
                            coordinates=coordinates,
                            potensi=potensi,
                            dirasakan=dirasakan
                        )
                        await bot.reply_user(sender, room, reply_text, is_private, nick=nick)

        except asyncio.TimeoutError:
            err_timeout = m.get("quake_timeout")
            await bot.reply_user(sender, room, err_timeout, is_private, nick=nick)
        except Exception as e:
            err_exc = m.get("quake_error").format(e=e)
            await bot.reply_user(sender, room, err_exc, is_private, nick=nick)

    @bot.command("holiday", "👤 Participant & Member")
    async def cmd_holiday(sender, room, nick, is_private, args):
        """holiday"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        today = datetime.date.today()
        weekday = today.weekday() # 0=Senin, ..., 5=Sabtu, 6=Minggu
        
        if weekday == 5:
            weekend_status = m.get("holiday_sat")
        elif weekday == 6:
            weekend_status = m.get("holiday_sun")
        elif weekday == 4:
            weekend_status = m.get("holiday_fri")
        else:
            days_to_sat = 5 - weekday
            weekend_status = m.get("holiday_approaching").format(days_to_sat=days_to_sat)

        next_holiday = await fetch_next_holiday()
        
        if next_holiday:
            holiday_info = m.get("holiday_info_format").format(
                name=next_holiday['name'],
                date=next_holiday['date'],
                days=next_holiday['days']
            )
        else:
            holiday_info = m.get("holiday_none")

        reply_text = m.get("holiday_header").format(
            weekend_status=weekend_status,
            holiday_info=holiday_info
        )
        await bot.reply_user(sender, room, reply_text, is_private, nick=nick)

    # --- BACKGROUND TASK 1: AUTO-BROADCAST GEMPA TERBARU ---
    async def check_new_earthquake_loop():
        global last_broadcasted_quake_id
        await asyncio.sleep(15)

        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    url = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            infogempa = data.get("Infogempa", {}).get("gempa", {})
                            
                            if infogempa:
                                tanggal = infogempa.get("Tanggal", "")
                                jam = infogempa.get("Jam", "")
                                magnitude_str = infogempa.get("Magnitude", "0")
                                
                                current_quake_id = f"{tanggal}-{jam}"

                                if last_broadcasted_quake_id is None:
                                    last_broadcasted_quake_id = current_quake_id
                                elif current_quake_id != last_broadcasted_quake_id:
                                    last_broadcasted_quake_id = current_quake_id
                                    
                                    try:
                                        mag_val = float(magnitude_str.split()[0])
                                    except Exception:
                                        mag_val = 0.0

                                    if mag_val >= 5.0:
                                        # Gunakan default 'id' atau bahasa sistem untuk broadcast background
                                        m_def = get_m("id")
                                        tanggal = infogempa.get("Tanggal", "-")
                                        jam = infogempa.get("Jam", "-")
                                        coordinates = infogempa.get("Coordinates", "-")
                                        magnitude = infogempa.get("Magnitude", "-")
                                        kedalaman = infogempa.get("Kedalaman", "-")
                                        wilayah = infogempa.get("Wilayah", "-")
                                        potensi = infogempa.get("Potensi", "-")

                                        quake_vals = dict(
                                            tanggal=tanggal,
                                            jam=jam,
                                            magnitude=magnitude,
                                            kedalaman=kedalaman,
                                            wilayah=wilayah,
                                            coordinates=coordinates,
                                            potensi=potensi
                                        )

                                        if hasattr(bot, "get_rooms") and hasattr(bot, "send_message"):
                                            rooms = bot.get_rooms()
                                            for r in rooms:
                                                try:
                                                    alert_text = get_m(get_lang(None, r)).get("broadcast_quake_alert").format(**quake_vals)
                                                    bot.send_message(mto=r, mbody=alert_text, mtype="groupchat")
                                                    await asyncio.sleep(0.5)
                                                except Exception:
                                                    pass
            except Exception:
                pass

            await asyncio.sleep(600)

    # --- BACKGROUND TASK 2: AUTO-BROADCAST HARI MINGGU & LIBUR NASIONAL ---
    async def calendar_broadcast_loop():
        global last_notified_holiday_date
        await asyncio.sleep(25)

        while True:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            m_def = get_m("id")

            # 1. Cek Auto-Broadcast Hari Minggu (Jam 07:00 pagi)
            if now.weekday() == 6 and now.hour == 7:
                sunday_msg = m_def.get("broadcast_sunday")
                if hasattr(bot, "get_rooms") and hasattr(bot, "send_message"):
                    for r in bot.get_rooms():
                        try:
                            bot.send_message(mto=r, mbody=get_m(get_lang(None, r)).get("broadcast_sunday"), mtype="groupchat")
                            await asyncio.sleep(0.5)
                        except Exception:
                            pass
                await asyncio.sleep(86400) # Istirahat 24 jam

            # 2. Cek Auto-Broadcast Hari Libur Nasional (Jam 07:00 pagi)
            elif now.hour == 7:
                next_h = await fetch_next_holiday()
                if next_h and next_h['days'] == 0 and next_h['date'] == today_str:
                    if last_notified_holiday_date != today_str:
                        last_notified_holiday_date = today_str
                        holiday_msg = m_def.get("broadcast_national_holiday").format(name=next_h['name'])
                        if hasattr(bot, "send_message"):
                            for r in id_alert_rooms():
                                try:
                                    bot.send_message(mto=r, mbody=get_m(get_lang(None, r)).get("broadcast_national_holiday").format(name=next_h['name']), mtype="groupchat")
                                    await asyncio.sleep(0.5)
                                except Exception:
                                    pass

            # Cek berkala setiap 30 menit
            await asyncio.sleep(1800)

    if hasattr(bot, "loop") and bot.loop:
        bot.loop.create_task(check_new_earthquake_loop())
        bot.loop.create_task(calendar_broadcast_loop())
    else:
        asyncio.create_task(check_new_earthquake_loop())
        asyncio.create_task(calendar_broadcast_loop())
