# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import asyncio
import aiohttp
import logging
import os
from datetime import datetime, timezone, timedelta

def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    if not hasattr(bot, "user_languages"):
        bot.user_languages = {}

    def get_lang(sender, room):
        """Mengambil bahasa yang aktif untuk user atau room tertentu (default: id)."""
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        key = room if room else str(sender)
        default_fallback = getattr(bot, "global_default_lang", "id")
        return bot.user_languages.get(key, default_fallback)

    def get_m(lang):
        """Helper untuk mengambil kamus bahasa dengan fallback aman ke 'id'."""
        return LANG_MESSAGES.get(lang, LANG_MESSAGES.get("id", {}))
    
    async def fetch_weather_data(city, lang="id"):
        clean_city = city.strip()
        m = get_m(lang)
        
        # Membaca WEATHER_API_KEY dari config bot utama
        api_key = getattr(bot, "weather_api_key", "")
        if not api_key:
            try:
                api_key = bot.get_setting("WEATHER_API_KEY", "")
            except:
                pass

        if not api_key:
            err_msg = m.get("err_api_key")
            return f"• {clean_city.title()}: {err_msg}"

        try:
            async with aiohttp.ClientSession() as session:
                current_url = f"https://api.openweathermap.org/data/2.5/weather?q={clean_city}&units=metric&lang={lang}&appid={api_key}"
                forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?q={clean_city}&units=metric&lang={lang}&appid={api_key}"
                
                async with session.get(current_url, timeout=8) as resp, session.get(forecast_url, timeout=8) as fc_resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        city_name = data.get("name", clean_city.title())
                        sys_info = data.get("sys", {})
                        country = sys_info.get("country", "")
                        
                        main = data.get("main", {})
                        temp = main.get("temp", "-")
                        feels_like = main.get("feels_like", "-")
                        humidity = main.get("humidity", "-")
                        pressure = main.get("pressure", "-")
                        
                        weather_list = data.get("weather", [])
                        default_desc = m.get("default_desc")
                        desc = weather_list[0].get("description", default_desc).capitalize() if weather_list else default_desc
                        main_weather = weather_list[0].get("main", "").lower() if weather_list else ""
                        
                        wind = data.get("wind", {})
                        wind_speed = wind.get("speed", "-")
                        
                        visibility = data.get("visibility", 0) / 1000  # Konversi meter ke kilometer
                        
                        timezone_offset = data.get("timezone", 25200) # Default WIB
                        sunrise_utc = datetime.fromtimestamp(sys_info.get("sunrise", 0), timezone.utc)
                        sunset_utc = datetime.fromtimestamp(sys_info.get("sunset", 0), timezone.utc)
                        local_tz = timezone(timedelta(seconds=timezone_offset))
                        sunrise_str = sunrise_utc.astimezone(local_tz).strftime("%H:%M")
                        sunset_str = sunset_utc.astimezone(local_tz).strftime("%H:%M")
                        
                        location_label = f"{city_name}, {country}" if country else city_name
                        
                        # --- Rekomendasi Pintar Berdasarkan Cuaca ---
                        advice = ""
                        if "hujan" in main_weather or "rain" in main_weather:
                            advice = m.get("advice_rain")
                        elif isinstance(temp, (int, float)) and temp >= 33:
                            advice = m.get("advice_hot")
                        elif isinstance(temp, (int, float)) and temp <= 23:
                            advice = m.get("advice_cold")
                        
                        # --- Ambil Prakiraan 3 Jam Kedepan ---
                        forecast_snippet = ""
                        if fc_resp.status == 200:
                            fc_data = await fc_resp.json()
                            list_fc = fc_data.get("list", [])
                            if len(list_fc) > 0:
                                next_fc = list_fc[0] # Data 3 jam ke depan
                                fc_temp = next_fc.get("main", {}).get("temp", "-")
                                fc_desc = next_fc.get("weather", [{}])[0].get("description", "").capitalize()
                                fc_time_raw = next_fc.get("dt_txt", "") # Format "YYYY-MM-DD HH:MM:SS"
                                fc_time = fc_time_raw.split(" ")[1][:5] if " " in fc_time_raw else ""
                                
                                if fc_desc:
                                    forecast_snippet = m.get("forecast_snippet").format(fc_time=fc_time, fc_desc=fc_desc, fc_temp=fc_temp)

                        # Susun Format Pesan Akhir
                        result_text = m.get("weather_format").format(
                            location_label=location_label,
                            desc=desc,
                            temp=temp,
                            feels_like=feels_like,
                            humidity=humidity,
                            pressure=pressure,
                            visibility=visibility,
                            wind_speed=wind_speed,
                            sunrise_str=sunrise_str,
                            sunset_str=sunset_str
                        )
                        
                        if forecast_snippet:
                            result_text += f"\n{forecast_snippet}"
                        if advice:
                            result_text += f"\n{advice}"
                            
                        return result_text
                        
                    elif resp.status == 404:
                        err_404 = m.get("err_404")
                        return f"• {clean_city.title()}: {err_404}"
                    else:
                        err_srv = m.get("err_srv").format(status=resp.status)
                        return f"• {clean_city.title()}: {err_srv}"
                    
        except Exception as e:
            logging.error(f"Gagal mengambil cuaca OpenWeather untuk {clean_city}: {e}")
            err_conn = m.get("err_conn")
            return f"• {clean_city.title()}: {err_conn}"

    # Menyematkan fungsi ke instance bot
    bot.fetch_weather_data = fetch_weather_data

    def get_clean_room_cities(room):
        if not hasattr(bot, "get_room_cities"):
            return []
        raw_cities = bot.get_room_cities(room)
        if not raw_cities:
            return []
        filtered = [c for c in raw_cities if c.strip().lower() != "jakarta"]
        return filtered

    async def background_weather_broadcast():
        while True:
            await asyncio.sleep(14400) # Tiap 4 jam
            if not hasattr(bot, "get_rooms"):
                continue
            rooms = bot.get_rooms()
            for room in rooms:
                cities = get_clean_room_cities(room)
                if not cities:
                    continue
                
                lang = get_lang(None, room)
                m = get_m(lang)
                header_bc = m.get("broadcast_header")
                
                laporan = [header_bc]
                for city in cities:
                    result = await fetch_weather_data(city, lang=lang)
                    laporan.append(result)
                
                pesan_final = "\n\n".join(laporan)
                try:
                    bot.send_message(mto=room, mbody=pesan_final, mtype="groupchat")
                except Exception as e:
                    logging.error(f"Gagal mengirim siaran cuaca otomatis ke room {room}: {e}")

    async def on_session_start(event):
        asyncio.create_task(background_weather_broadcast())

    bot.add_event_handler("session_start", on_session_start)

    # --- Commands ---

    @bot.command("addweather", "💎 Admin & Owner Group")
    async def cmd_addkota(sender, room, nick, is_private, args):
        """Example command: addweather <city/area>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return
        if args:
            new_city = " ".join(args).strip()
            if hasattr(bot, "add_room_city"):
                bot.add_room_city(room, new_city)
            succ_msg = m.get("add_success").format(new_city=new_city.title())
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        else:
            await bot.reply_user(sender, room, m.get("add_format_err"), is_private, nick=nick)

    @bot.command("delweather", "💎 Admin & Owner Group")
    async def cmd_delkota(sender, room, nick, is_private, args):
        """Example command: delweather <city/region name>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return
        if args:
            target_city = " ".join(args).strip()
            if hasattr(bot, "remove_room_city"):
                bot.remove_room_city(room, target_city)
            succ_msg = m.get("del_success").format(target_city=target_city)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        else:
            await bot.reply_user(sender, room, m.get("del_format_err"), is_private, nick=nick)

    @bot.command("weather", "👤 Participant & Member", aliases=["cuaca"])
    async def cmd_cuaca(sender, room, nick, is_private, args):
        """Example command: weather [city/area]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        target_cities = []
        if not args:
            if room:
                target_cities = get_clean_room_cities(room)
                if not target_cities:
                    err_empty = m.get("err_empty_default")
                    await bot.reply_user(sender, room, err_empty, is_private, nick=nick)
                    return
            else:
                err_empty = m.get("err_empty_default")
                await bot.reply_user(sender, room, err_empty, is_private, nick=nick)
                return
        else:
            joined_args = " ".join(args)
            target_cities = [c.strip() for c in joined_args.split(",") if c.strip()]

        header_res = m.get("weather_header")
        results = [header_res]
        for city in target_cities:
            res = await fetch_weather_data(city, lang=lang)
            results.append(res)
        
        await bot.reply_user(sender, room, "\n\n".join(results), is_private, nick=nick)

    @bot.command("weatherlist", "👤 Participant & Member")
    async def cmd_listkota(sender, room, nick, is_private, args):
        """Example command: weatherlist"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return
        
        cities = get_clean_room_cities(room)
        if cities:
            city_list_text = m.get("list_header") + "\n- ".join(cities)
        else:
            city_list_text = m.get("err_empty_default")
        await bot.reply_user(sender, room, city_list_text, is_private, nick=nick)
