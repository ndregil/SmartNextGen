# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import aiohttp
import asyncio
import os
import io
import datetime

CATEGORY_MAP = {
    "dank": "dankmemes",
    "meirl": "meirl",
    "wholesome": "wholesomememes",
    "programmer": "programmerhumor",
    "code": "programmerhumor",
    "anime": "animememes",
    "cats": "catmemes",
    "cat": "catmemes",
    "gaming": "gamingmemes",
    "game": "gamingmemes",
    "history": "historymemes",
    "science": "sciencememes",
    "tech": "technology",
    "bug": "softwaregore",
    "error": "softwaregore",
    "comics": "webcomics",
    "comic": "webcomics",
    "lucu": "dankmemes",
    "random": "memes",
}


def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    # Kamus bahasa: lang/cmd_meme/<kode>.json
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def get_lang(sender, room):
        """Mengambil bahasa aktif langsung dari sistem inti bot agar terpusat."""
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        if not hasattr(bot, "user_languages"):
            bot.user_languages = {}
        key = room if room else str(sender)
        return bot.user_languages.get(key, "id")

    def T(lang, key, **kw):
        """Fallback: bahasa aktif -> en -> id -> nama key."""
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

    @bot.command("meme", "👤 Participant & Member")
    async def cmd_meme(sender, room, nick, is_private, args):
        """meme list"""
        lang = get_lang(sender, room)
        sub_arg = args[0].lower().strip() if args else ""

        async def say(text):
            await bot.reply_user(sender, room, text, is_private, nick=nick)

        if not sub_arg or sub_arg in ["list", "daftar", "menu"]:
            await say(T(lang, "meme_list"))
            return

        target_sub = CATEGORY_MAP.get(sub_arg, "memes")
        display_name = sub_arg.upper()

        await say(T(lang, "meme_loading", display_name=display_name))

        file_path = None
        try:
            meme_dir = "data"
            if not os.path.exists(meme_dir):
                os.makedirs(meme_dir)

            async with aiohttp.ClientSession() as session:
                url = f"https://meme-api.com/gimme/{target_sub}"
                async with session.get(url, timeout=10) as resp:
                    data = await resp.json() if resp.status == 200 else {}

                    if resp.status != 200 or "code" in data or not data.get("url"):
                        url_fallback = "https://meme-api.com/gimme/memes"
                        async with session.get(url_fallback, timeout=10) as resp_fb:
                            data = await resp_fb.json() if resp_fb.status == 200 else {}

                    image_url = data.get("url", None)
                    meme_title = data.get("title", T(lang, "meme_no_title"))

                    if not image_url:
                        await say(T(lang, "meme_err_url"))
                        return

                    async with session.get(image_url, timeout=15) as img_resp:
                        if img_resp.status != 200:
                            await say(T(lang, "meme_err_dl"))
                            return
                        image_data = await img_resp.read()

                    file_name = f"meme_{target_sub}_{int(asyncio.get_event_loop().time())}.jpg"
                    file_path = os.path.join(meme_dir, file_name)

                    with open(file_path, "wb") as f:
                        f.write(image_data)

                    xep_plugin = None
                    try:
                        if hasattr(bot, 'plugin') and 'xep_0363' in bot.plugin:
                            xep_plugin = bot.plugin['xep_0363']
                        elif hasattr(bot, 'xep_0363'):
                            xep_plugin = bot.xep_0363
                    except Exception:
                        pass

                    if xep_plugin and hasattr(xep_plugin, "upload_file"):
                        with open(file_path, "rb") as f_local:
                            file_bytes = f_local.read()

                        upload_result = await xep_plugin.upload_file(
                            filename=file_name,
                            size=len(file_bytes),
                            content_type="image/jpeg",
                            input_file=io.BytesIO(file_bytes),
                            timeout=15
                        )

                        if isinstance(upload_result, dict):
                            download_url = upload_result.get('url', '')
                        else:
                            download_url = str(upload_result)

                        if download_url:
                            target_jid = sender if is_private else room
                            msg_type = 'chat' if is_private else 'groupchat'

                            msg = bot.make_message(mto=target_jid, mbody=download_url, mtype=msg_type)
                            msg.send()

                            log_path = os.path.join(meme_dir, "meme_history.log")
                            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            requester = f"{room} ({nick})" if room and nick else str(sender)
                            log_entry = f"[{timestamp}] Category: {target_sub} | Title: {meme_title} | By: {requester} | URL: {download_url}\n"

                            with open(log_path, "a", encoding="utf-8") as log_file:
                                log_file.write(log_entry)
                        else:
                            await say(T(lang, "meme_err_upload"))
                    else:
                        await say(T(lang, "meme_err_plugin"))

        except asyncio.TimeoutError:
            await say(T(lang, "meme_timeout"))
        except Exception as e:
            await say(T(lang, "meme_error", e=e))

        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as err:
                    print(f"Failed to remove local meme file: {err}")
