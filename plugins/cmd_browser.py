# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import os
import requests

def register(bot):
    """Mendaftarkan perintah browser/web reader ke menu umum."""
    
    # Mengambil nama plugin secara otomatis dari nama file
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    
    # Memuat kamus bahasa JSON dari direktori lang/cmd_browser/
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

    @bot.command("www", "👤 Participant & Member")
    async def cmd_www(sender, room, nick, is_private, args):
        """www <url>"""
        lang = get_lang(sender, room)
        m = get_m(lang)

        if not args:
            msg = m.get("wrong_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        url_input = args[0]

        # Pastikan URL memiliki skema http/https
        if not url_input.startswith(("http://", "https://")):
            url = "http://" + url_input
        else:
            url = url_input

        try:
            # Beritahu user proses sedang berjalan
            access_msg = m.get("accessing").format(url=url)
            await bot.reply_user(sender, room, access_msg, is_private, nick=nick)

            # Request ke Jina Reader API
            api_url = f"https://r.jina.ai/{url}"
            headers = {
                "Accept": "text/plain",
                "X-Return-Format": "text",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            response = requests.get(api_url, headers=headers, timeout=15)
            response.raise_for_status()

            clean_text = response.text.strip()

            if not clean_text:
                clean_text = m.get("no_content")

            # Batasi panjang teks agar pas di chat XMPP
            max_chars = 1200
            if len(clean_text) > max_chars:
                cut_notice = m.get("truncated_notice")
                clean_text = clean_text[:max_chars] + cut_notice

            # Kirim hasil ringkas ke pengguna/room
            formatted_output = m.get("output_title").format(url=url, text=clean_text)
            await bot.reply_user(sender, room, formatted_output, is_private, nick=nick)

        except requests.exceptions.Timeout:
            err_msg = m.get("err_timeout").format(url=url)
            await bot.reply_user(sender, room, err_msg, is_private, nick=nick)
        except requests.exceptions.HTTPError as err:
            err_msg = m.get("err_http").format(err=err)
            await bot.reply_user(sender, room, err_msg, is_private, nick=nick)
        except Exception as e:
            err_msg = m.get("err_general").format(error=str(e))
            await bot.reply_user(sender, room, err_msg, is_private, nick=nick)
