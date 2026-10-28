# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import asyncio
import aiohttp
import logging
from html import unescape
import re
import os

def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

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

    # 1. Google/MyMemory Translate Command (Publik)
    @bot.command("tr", "👤 Participant & Member", ["translate"])
    async def cmd_translate(sender, room, nick, is_private, args):
        """tr <language_code> <text>"""
        lang = get_lang(sender, room)
        m = get_m(lang)

        if len(args) < 2:
            msg = m.get("tr_format_error")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        target_lang = args[0].lower()
        text_to_translate = " ".join(args[1:])

        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.mymemory.translated.net/get?q={aiohttp.helpers.quote(text_to_translate)}&langpair=autodetect|{target_lang}"
                async with session.get(url, timeout=6) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response_data = data.get("responseData", {})
                        translated_text = response_data.get("translatedText", "")
                        
                        if translated_text:
                            result_msg = m.get("tr_success").format(
                                target_lang=target_lang.upper(),
                                translated_text=translated_text
                            )
                            await bot.reply_user(sender, room, result_msg, is_private, nick=nick)
                        else:
                            err_msg = m.get("tr_failed_text")
                            await bot.reply_user(sender, room, err_msg, is_private, nick=nick)
                    else:
                        err_status = m.get("tr_failed_conn").format(status=resp.status)
                        await bot.reply_user(sender, room, err_status, is_private, nick=nick)
        except Exception as e:
            logging.error(f"Error Translate: {e}")
            err_err = m.get("tr_error")
            await bot.reply_user(sender, room, err_err, is_private, nick=nick)

    # 2. Google Search Command dengan Cuplikan & Link Sumber Akurat (Publik)
    @bot.command("google", "👤 Participant & Member", ["search", "cari"])
    async def cmd_google(sender, room, nick, is_private, args):
        """google <keywords>"""
        lang = get_lang(sender, room)
        m = get_m(lang)

        if not args:
            msg = m.get("google_format_error")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        query = " ".join(args)
        google_url = f"https://www.google.com/search?q={aiohttp.helpers.quote(query)}"
        
        snippet = ""
        source_title = ""
        source_link = ""
        
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with aiohttp.ClientSession(headers=headers) as session:
                url = f"https://html.duckduckgo.com/html/?q={aiohttp.helpers.quote(query)}"
                async with session.post(url, timeout=6) as resp:
                    if resp.status == 200:
                        html_content = await resp.text()
                        
                        snippet_match = re.search(r'<a class="result__snippet[^>]*>(.*?)</a>', html_content, re.DOTALL)
                        if snippet_match:
                            clean_text = re.sub(r'<.*?>', '', snippet_match.group(1))
                            snippet = unescape(clean_text).strip()

                        title_match = re.search(r'<a class="result__title"[^>]*>(.*?)</a>', html_content, re.DOTALL)
                        if title_match:
                            clean_title = re.sub(r'<.*?>', '', title_match.group(1))
                            source_title = unescape(clean_title).strip()

                        link_match = re.search(r'<a class="result__url"[^>]*href="([^"]+)"', html_content)
                        if link_match:
                            raw_link = link_match.group(1)
                            if "uddg=" in raw_link:
                                import urllib.parse
                                parsed_uddg = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                                if "uddg" in parsed_uddg:
                                    source_link = parsed_uddg["uddg"][0]
                            else:
                                source_link = raw_link
                            source_link = unescape(source_link).strip()
        except Exception as e:
            logging.error(f"Error fetching search result: {e}")

        if snippet and source_link:
            msg = m.get("google_result_msg").format(
                query=query,
                title=source_title if source_title else "Link URL",
                link=source_link,
                snippet=snippet,
                google_url=google_url
            )
        else:
            msg = m.get("google_no_snippet_msg").format(
                query=query,
                google_url=google_url
            )

        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    # 3. Google Maps Command (Publik)
    @bot.command("maps", "👤 Participant & Member")
    async def cmd_maps(sender, room, nick, is_private, args):
        """maps <place_name>"""
        lang = get_lang(sender, room)
        m = get_m(lang)

        if not args:
            msg = m.get("maps_format_error")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        place = " ".join(args)
        maps_url = f"https://www.google.com/maps/search/?api=1&query={aiohttp.helpers.quote(place)}"
        msg = m.get("maps_msg").format(place=place.title(), maps_url=maps_url)
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    # 4. YouTube Command (Publik)
    @bot.command("youtube", "👤 Participant & Member", ["yt"])
    async def cmd_youtube(sender, room, nick, is_private, args):
        """youtube <video_title>"""
        lang = get_lang(sender, room)
        m = get_m(lang)

        if not args:
            msg = m.get("yt_format_error")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        query = " ".join(args)
        yt_search_url = f"https://www.youtube.com/results?search_query={aiohttp.helpers.quote(query)}"
        
        wasm_msg = m.get("yt_msg").format(query=query, yt_search_url=yt_search_url)
        await bot.reply_user(sender, room, wasm_msg, is_private, nick=nick)
