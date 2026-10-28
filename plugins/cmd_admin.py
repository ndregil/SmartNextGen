# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import asyncio
import os
import sys
import time

def register(bot):
    # Mendeteksi nama plugin secara otomatis dari nama file ('cmd_botowner')
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    
    # Memuat kamus bahasa JSON dari direktori lang/cmd_botowner/
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def get_lang(sender, room):
        """Mengambil bahasa aktif secara sinkron langsung dari database/sistem inti bot."""
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        return "id"

    def get_m(lang):
        """Helper untuk mengambil kamus bahasa dengan fallback aman ke 'id'."""
        return LANG_MESSAGES.get(lang, LANG_MESSAGES.get("id", {}))

    def get_active_bots():
        """Helper untuk mengambil kamus global instance bot yang aktif."""
        main_bot_module = sys.modules.get("__main__")
        return getattr(main_bot_module, "ACTIVE_BOT_INSTANCES", {}) if main_bot_module else {}

    def find_bot_key(target):
        """Cari label (jid1/jid2/jid3) dari instance bot tertentu."""
        for key, obj in get_active_bots().items():
            if obj is target:
                return key
        return "bot"

    async def _reconnect_bot(target_bot):
        """Restart koneksi SATU akun saja: putus bersih, lalu login & join room ulang."""
        try:
            main_mod = sys.modules.get("__main__")
            safe_disconnect = getattr(main_mod, "safe_disconnect", None)
            target_bot.auto_reconnect = False  # cegah reconnect ganda selama proses ini
            if safe_disconnect:
                await safe_disconnect(target_bot)
            else:
                target_bot.disconnect()
            await asyncio.sleep(3)
            target_bot.connect()
        except Exception as e:
            print(f"Failed to restart bot: {e}")
        finally:
            target_bot.auto_reconnect = True

    async def _stop_bot(target_bot):
        """Matikan SATU akun dan cegah supervisor menyambungkannya lagi."""
        try:
            target_bot.manual_stop = True
            target_bot.auto_reconnect = False
            target_bot.session_active = False
            main_mod = sys.modules.get("__main__")
            safe_disconnect = getattr(main_mod, "safe_disconnect", None)
            if safe_disconnect:
                await safe_disconnect(target_bot)
            else:
                target_bot.disconnect()
        except Exception as e:
            print(f"Failed to stop bot: {e}")

    def _start_bot(target_bot):
        """Hidupkan lagi akun yang dimatikan manual."""
        target_bot.manual_stop = False
        target_bot.auth_failed_at = None
        target_bot.last_down_at = time.monotonic()  # beri supervisor waktu penuh untuk login
        target_bot.auto_reconnect = True
        target_bot.connect()

    @bot.command("bookmark", "👑 Bot Owner")
    async def cmd_bookmark(sender, room, nick, is_private, args):
        """bookmark [jid1|jid2|jid3|all]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        active_bots = get_active_bots()
        target_keys = ["jid1", "jid2", "jid3"]
        
        # Tentukan bot mana saja yang akan ditampilkan berdasarkan argumen
        if args:
            arg = args[0].lower()
            if arg in ["jid1", "jid2", "jid3"]:
                target_keys = [arg]
            elif arg == "all":
                target_keys = ["jid1", "jid2", "jid3"]
            else:
                # Jika argumen tidak dikenali, fallback ke bot saat ini atau tampilkan pesan format
                target_keys = None

        if not target_keys:
            # Jika argumen berupa room spesifik atau teks lain, gunakan perilaku default bot saat ini
            registered_rooms = bot.get_rooms()
            if not registered_rooms:
                msg = m.get("bookmark_empty", "There are no rooms registered.")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                return

            title = m.get("bookmark_title", "Bookmark Room List:")
            room_lines = [title]
            for idx, r_jid in enumerate(sorted(registered_rooms), start=1):
                room_lines.append(f"{idx}. {r_jid}")
            
            await bot.reply_user(sender, room, "\n".join(room_lines), is_private, nick=nick)
            return

        # Mengumpulkan room dari masing-masing bot yang diminta
        response_lines = [m.get("bookmark_title", "Daftar Room Bookmark:")]
        total_rooms = 0

        for key in target_keys:
            target_bot = active_bots.get(key)
            if target_bot and hasattr(target_bot, "get_rooms"):
                rooms = target_bot.get_rooms()
                if rooms:
                    response_lines.append(f"\n[{key.upper()}]")
                    for idx, r_jid in enumerate(sorted(rooms), start=1):
                        response_lines.append(f"  {idx}. {r_jid}")
                        total_rooms += 1

        if total_rooms == 0:
            msg = m.get("bookmark_empty", "There are no rooms registered on the bot.")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        bookmark_text = "\n".join(response_lines)
        await bot.reply_user(sender, room, bookmark_text, is_private, nick=nick)

    @bot.command("botowner_add", "👑 Bot Owner")
    async def cmd_botowner_add(sender, room, nick, is_private, args):
        """botowner_add <jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if args:
            target_nick = args[0]
            target_jid = None
            if room and room in bot.room_users and target_nick in bot.room_users[room]:
                target_jid = bot.room_users[room][target_nick].get("jid")
            
            if not target_jid:
                target_jid = target_nick

            if target_jid:
                clean_jid = str(target_jid).split("/")[0].lower()
                
                # Sinkronisasi penambahan owner ke SEMUA bot aktif
                active_bots = get_active_bots()
                success_count = 0
                
                if active_bots:
                    for label, active_bot_obj in active_bots.items():
                        try:
                            active_bot_obj.add_owner_to_db(clean_jid)
                            success_count += 1
                        except Exception as e:
                            print(f"Failed to update owner on bot {label}: {e}")
                else:
                    # Fallback jika dictionary global kosong, minimal bot saat ini diperbarui
                    bot.add_owner_to_db(clean_jid)
                    success_count = 1

                msg = m.get("botowner_add_success").format(target=target_nick)
                msg = m.get("botowner_add_synced", "{msg} (disinkronkan ke {count} bot)").format(msg=msg, count=success_count)
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("botowner_add_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("botowner_del", "👑 Bot Owner")
    async def cmd_botowner_del(sender, room, nick, is_private, args):
        """botowner_del <jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if args:
            target_nick = args[0]
            target_jid = None
            if room and room in bot.room_users and target_nick in bot.room_users[room]:
                target_jid = bot.room_users[room][target_nick].get("jid")
            
            if not target_jid:
                target_jid = target_nick

            target = str(target_jid).split("/")[0].lower()
            owners = bot.get_owners()
            
            if target in owners and len(owners) > 1:
                # Sinkronisasi penghapusan owner ke SEMUA bot aktif
                active_bots = get_active_bots()
                success_count = 0
                
                if active_bots:
                    for label, active_bot_obj in active_bots.items():
                        try:
                            active_bot_obj.remove_owner_from_db(target)
                            success_count += 1
                        except Exception as e:
                            print(f"Failed to delete owner in bot {label}: {e}")
                else:
                    bot.remove_owner_from_db(target)
                    success_count = 1

                msg = m.get("botowner_del_success").format(target=target_nick)
                msg = m.get("botowner_del_synced", "{msg} (disinkronkan dari {count} bot)").format(msg=msg, count=success_count)
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            else:
                msg = m.get("botowner_del_fail")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("botowner_del_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("botowner_show", "👑 Bot Owner")
    async def cmd_botowner_show(sender, room, nick, is_private, args):
        """botowner_show [jid1|jid2|jid3]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        active_bots = get_active_bots()
        target_bot = bot

        if args:
            bot_key = args[0].lower()
            if bot_key in active_bots:
                target_bot = active_bots[bot_key]

        owners = target_bot.get_owners()
        title = m.get("botowner_show_title")
        
        # Kembali persis menggunakan struktur asli Anda yang bersih
        await bot.reply_user(sender, room, title + "\n- ".join(owners), is_private, nick=nick)

    @bot.command("global_msg", "👑 Bot Owner")
    async def cmd_global_msg(sender, room, nick, is_private, args):
        """global_msg <isi pesan>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not args:
            msg = m.get("global_msg_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        pesan = " ".join(args).strip()
        registered_rooms = bot.get_rooms()
        
        if not registered_rooms:
            msg = m.get("global_msg_empty")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        success_count = 0
        fail_count = 0

        for r_jid in registered_rooms:
            try:
                bot.send_message(mto=r_jid, mbody=pesan, mtype="groupchat")
                success_count += 1
            except Exception:
                fail_count += 1

        summary = m.get("global_msg_summary").format(success=success_count, fail=fail_count)
        await bot.reply_user(sender, room, summary, is_private, nick=nick)

    @bot.command("join", "👑 Bot Owner")
    async def cmd_join(sender, room, nick, is_private, args):
        """join [jid1|jid2|jid3] <grup@conference.server.com>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        if not args:
            msg = m.get("join_format", "Invalid format. Use: join [target_jid] <room>")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        active_bots = get_active_bots()
        target_bot_key = "jid1"
        target_room = ""

        first_arg = args[0].lower()
        if first_arg in ["jid1", "jid2", "jid3"]:
            target_bot_key = first_arg
            if len(args) > 1:
                target_room = args[1]
            else:
                msg = m.get("join_need_room", "Tulis nama room tujuan untuk {bot}.").format(bot=target_bot_key.upper())
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                return
        else:
            target_room = args[0]

        target_bot = active_bots.get(target_bot_key, bot)

        try:
            target_bot.add_room_to_db(target_room)
            
            current_status = target_bot.get_setting("bot_status", getattr(target_bot, "bot_status", ""))
            pshow = None
            pstatus = current_status
            valid_shows = ["online", "chat", "away", "xa", "dnd"]
            parts = current_status.split(" ", 1)
            if parts and parts[0].lower() in valid_shows:
                pshow = parts[0].lower()
                pstatus = parts[1].strip() if len(parts) > 1 else ""

            target_bot.plugin["xep_0045"].join_muc(target_room, target_bot.get_room_nick(target_room), pshow=pshow, pstatus=pstatus)
            
            msg = m.get("join_success", "Successfully ordered {bot} join in {room}").format(bot=target_bot_key.upper(), room=target_room)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except Exception as e:
            msg = m.get("join_fail", "Failed to join: {error}").format(error=e)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("leave", "💎 Admin & Owner Group")
    async def cmd_leave(sender, room, nick, is_private, args):
        """leave [jid1|jid2|jid3] <grup@conference.server.com>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        target_bot = bot
        target_bot_key = "jid1"
        target_room = ""

        active_bots = get_active_bots()

        if not args:
            target_room = room
        else:
            first_arg = args[0].lower()
            if first_arg in ["jid1", "jid2", "jid3"]:
                target_bot_key = first_arg
                target_bot = active_bots.get(target_bot_key, bot)
                if len(args) > 1:
                    target_room = args[1]
                else:
                    target_room = room
            else:
                target_bot = bot
                target_room = args[0]

        if target_room:
            target_bot.remove_room_from_db(target_room)
            try:
                target_bot.plugin["xep_0045"].leave_muc(target_room, target_bot.get_room_nick(target_room))
            except Exception:
                pass
            msg = m.get("leave_success", "Berhasil keluar dari {target_room}").format(target_room=target_room)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("leave_format_error", "Format salah atau Anda tidak sedang di dalam room!")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("msg_to", "👑 Bot Owner")
    async def cmd_msg_to(sender, room, nick, is_private, args):
        """msg_to <jid/muc> <message>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not args or len(args) < 2:
            msg = m.get("msg_to_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        sTo = args[0]
        pesan = " ".join(args[1:])
        m_type = "groupchat" if ("@conference" in sTo or "@muc" in sTo) else "chat"

        try:
            bot.send_message(mto=sTo, mbody=pesan, mtype=m_type)
            msg = m.get("msg_to_success").format(to=sTo)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except Exception as e:
            msg = m.get("msg_to_fail").format(to=sTo, e=e)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("restart", "👑 Bot Owner")
    async def cmd_restart(sender, room, nick, is_private, args):
        """restart [jid1|jid2|jid3|all]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        active_bots = get_active_bots()

        # Tanpa argumen: hanya bot yang menerima perintah ini
        if not args:
            target_bot = bot
            label = find_bot_key(bot).upper()
        else:
            arg = args[0].lower()

            # restart all: restart seluruh proses (semua bot + muat ulang kode/plugin)
            if arg == "all":
                msg = m.get("restart_msg")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                await asyncio.sleep(2.5)
                os.execl(sys.executable, sys.executable, *sys.argv)
                return

            if arg not in ("jid1", "jid2", "jid3"):
                msg = m.get("restart_format", "Format: restart [jid1|jid2|jid3|all]")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                return

            target_bot = active_bots.get(arg)
            label = arg.upper()
            if target_bot is None:
                msg = m.get("restart_not_active", "{bot} tidak aktif.").format(bot=label)
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                return

        msg = m.get("restart_bot_msg", "Merestart {bot}...").format(bot=label)
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

        # Jeda agar balasan terkirim dulu, lalu jalankan sebagai task terpisah
        # (supaya tidak ikut terputus bersama handler pesan bot yang direstart)
        await asyncio.sleep(2.5)
        asyncio.ensure_future(_reconnect_bot(target_bot))

    @bot.command("say", "💎 Admin & Owner Group")
    async def cmd_say(sender, room, nick, is_private, args):
        """say <message>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            msg = m.get("say_muc_only")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return
        
        if not args:
            msg = m.get("say_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        pesan = " ".join(args).strip()
        try:
            bot.send_message(mto=room, mbody=pesan, mtype="groupchat")
            if is_private:
                msg = m.get("say_success").format(room=room)
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except Exception as e:
            msg = m.get("say_fail").format(error=e)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("shutdown", "👑 Bot Owner")
    async def cmd_shutdown(sender, room, nick, is_private, args):
        """shutdown [jid1|jid2|jid3|all]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        active_bots = get_active_bots()

        # Tanpa argumen: hanya bot yang menerima perintah ini
        if not args:
            target_bot = bot
            label = find_bot_key(bot).upper()
        else:
            arg = args[0].lower()

            # shutdown all: matikan seluruh proses (semua bot)
            if arg == "all":
                msg = m.get("shutdown_msg")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                await asyncio.sleep(2.5)
                os._exit(0)

            if arg not in ("jid1", "jid2", "jid3"):
                msg = m.get("shutdown_format", "Format: shutdown [jid1|jid2|jid3|all]")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                return

            target_bot = active_bots.get(arg)
            label = arg.upper()
            if target_bot is None:
                msg = m.get("bot_not_active", "{bot} tidak aktif.").format(bot=label)
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
                return

        if getattr(target_bot, "manual_stop", False):
            msg = m.get("shutdown_already", "{bot} sudah dimatikan.").format(bot=label)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        msg = m.get("shutdown_bot_msg", "Mematikan {bot}... (hidupkan lagi dengan: startup {key})").format(bot=label, key=label.lower())
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

        # Jeda agar balasan terkirim dulu, lalu matikan sebagai task terpisah
        await asyncio.sleep(2.5)
        asyncio.ensure_future(_stop_bot(target_bot))

    @bot.command("startup", "👑 Bot Owner")
    async def cmd_startup(sender, room, nick, is_private, args):
        """startup <jid1|jid2|jid3|all>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        active_bots = get_active_bots()

        arg = args[0].lower() if args else ""
        if arg == "all":
            keys = ["jid1", "jid2", "jid3"]
        elif arg in ("jid1", "jid2", "jid3"):
            keys = [arg]
        else:
            msg = m.get("startup_format", "Format: startup <jid1|jid2|jid3|all>")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        lines = []
        started = 0
        for key in keys:
            label = key.upper()
            target_bot = active_bots.get(key)
            if target_bot is None:
                if arg != "all":
                    lines.append(m.get("bot_not_active", "{bot} tidak aktif.").format(bot=label))
                continue
            if not getattr(target_bot, "manual_stop", False):
                if arg != "all":
                    lines.append(m.get("startup_not_stopped", "{bot} tidak sedang dimatikan (gunakan: restart {key}).").format(bot=label, key=key))
                continue
            if started:
                await asyncio.sleep(3)  # jeda antar akun agar login tidak serentak
            _start_bot(target_bot)
            started += 1
            lines.append(m.get("startup_done", "{bot} dihidupkan, sedang login...").format(bot=label))

        if not lines:
            lines.append(m.get("startup_none", "Tidak ada bot yang sedang dimatikan."))
        await bot.reply_user(sender, room, "\n".join(lines), is_private, nick=nick)

    @bot.command("statusbot_global", "👑 Bot Owner")
    async def cmd_statusbot_global(sender, room, nick, is_private, args):
        """statusbot_global <online|chat|away|xa|dnd> [text]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        valid_shows = ["online", "chat", "away", "xa", "dnd"]
        
        if not args:
            await bot.reply_user(sender, room, m.get("statusbot_format_global"), is_private, nick=nick)
            return

        show_type = args[0].lower()
        if show_type not in valid_shows:
            show_type = "online"
            status_text = " ".join(args).strip()
        else:
            status_text = " ".join(args[1:]).strip() if len(args) > 1 else ""

        full_status_string = f"{show_type} {status_text}".strip() if show_type != "online" else status_text

        bot.bot_status = full_status_string
        if hasattr(bot, "set_setting"):
            bot.set_setting("bot_status", full_status_string)

        try:
            pshow = None if show_type == "online" else show_type
            pstatus = status_text

            bot.send_presence(pshow=pshow, pstatus=pstatus)
            
            registered_rooms = bot.get_rooms() if hasattr(bot, "get_rooms") else getattr(bot, "room_users", {}).keys()
            for r_jid in registered_rooms:
                bot_nick = bot.get_room_nick(r_jid) if hasattr(bot, "get_room_nick") else nick
                try:
                    if hasattr(bot, "plugin") and "xep_0045" in bot.plugin:
                        bot.plugin["xep_0045"].join_muc(r_jid, bot_nick, pshow=pshow, pstatus=pstatus)
                except Exception:
                    pass

            msg = m.get("statusbot_success").format(status=f"[{show_type.upper()}] {status_text}".strip())
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except Exception as e:
            msg = m.get("statusbot_fail").format(error=e)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("statusbot_here", "💎 Admin & Owner Group")
    async def cmd_statusbot_here(sender, room, nick, is_private, args):
        """statusbot_here <online|chat|away|xa|dnd> [text]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        if not room:
            await bot.reply_user(sender, room, m.get("statusbot_muc_only"), is_private, nick=nick)
            return

        valid_shows = ["online", "chat", "away", "xa", "dnd"]
        
        if not args:
            await bot.reply_user(sender, room, m.get("statusbot_format_here"), is_private, nick=nick)
            return

        show_type = args[0].lower()
        if show_type not in valid_shows:
            show_type = "online"
            status_text = " ".join(args).strip()
        else:
            status_text = " ".join(args[1:]).strip() if len(args) > 1 else ""

        full_status_string = f"{show_type} {status_text}".strip() if show_type != "online" else status_text

        if hasattr(bot, "set_setting"):
            bot.set_setting(f"bot_status_{room.lower()}", full_status_string)

        try:
            bot_nick = bot.get_room_nick(room) if hasattr(bot, "get_room_nick") else ""
            pshow = None if show_type == "online" else show_type
            pstatus = status_text

            if hasattr(bot, "plugin") and "xep_0045" in bot.plugin:
                bot.plugin["xep_0045"].join_muc(room, bot_nick, pshow=pshow, pstatus=pstatus)
            
            suffix = m.get("statusbot_here_suffix", "(di room ini)")
            formatted_status = f"[{show_type.upper()}] {status_text} {suffix}".strip()
            msg = m.get("statusbot_success").format(status=formatted_status)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        except Exception as e:
            msg = m.get("statusbot_fail").format(error=e)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
