# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import asyncio
import os
from xml.etree import ElementTree as ET

MUC_ADMIN_NS = "http://jabber.org/protocol/muc#admin"


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

    def fmt(m, key, default="", **kwargs):
        """Format pesan dengan aman: tidak error jika key hilang atau placeholder berbeda.
        Placeholder umum {target_nick} dan {target_query} sama-sama disediakan."""
        template = m.get(key) or default or key
        if "target_nick" in kwargs and "target_query" not in kwargs:
            kwargs["target_query"] = kwargs["target_nick"]
        elif "target_query" in kwargs and "target_nick" not in kwargs:
            kwargs["target_nick"] = kwargs["target_query"]
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template

    # ------------------------------------------------------------------
    # Pembacaan daftar afiliasi MUC (member/admin/owner/outcast)
    # ------------------------------------------------------------------
    def _extract_jid(item):
        """Ambil JID dari berbagai tipe item (Element, dict, JID, str), termasuk domain tanpa '@'."""
        if item is None:
            return ""
        if isinstance(item, str):
            return item
        if hasattr(item, "attrib") and isinstance(item.attrib, dict):
            return item.attrib.get("jid", "")
        if isinstance(item, dict):
            return item.get("jid", "")
        if hasattr(item, "bare"):
            return str(item.bare)
        return str(item)

    def _parse_affiliation_result(iq):
        """Ubah hasil query afiliasi (IQ / set / list) menjadi list JID bersih."""
        if iq is None:
            return []

        items = []
        xml_element = getattr(iq, "xml", None)
        if xml_element is not None and hasattr(xml_element, "findall"):
            items = xml_element.findall("{%s}item" % MUC_ADMIN_NS)
            if not items:
                items = xml_element.findall(".//{%s}item" % MUC_ADMIN_NS)
            if not items:
                items = xml_element.findall(".//item")
        elif hasattr(iq, "findall"):
            items = iq.findall(".//{%s}item" % MUC_ADMIN_NS) or iq.findall(".//item")
        else:
            try:
                items = list(iq)  # set / list / tuple / generator
            except TypeError:
                items = []

        result = []
        for item in items:
            jid_val = _extract_jid(item)
            if jid_val:
                bare_jid = str(jid_val).split("/")[0].lower().strip()
                if bare_jid and bare_jid not in result:
                    result.append(bare_jid)
        return result

    async def _raw_affiliation_query(room, affiliation_type):
        """Query IQ muc#admin mentah; paling andal untuk outcast (user maupun server)."""
        iq = bot.make_iq_get(ito=room, ifrom=bot.boundjid)
        query = ET.Element("{%s}query" % MUC_ADMIN_NS)
        ET.SubElement(query, "{%s}item" % MUC_ADMIN_NS, {"affiliation": affiliation_type})
        iq.append(query)
        result = await iq.send(timeout=10)

        jids = []
        for item in result.xml.iter("{%s}item" % MUC_ADMIN_NS):
            if item.attrib.get("affiliation", affiliation_type) != affiliation_type:
                continue
            j = item.attrib.get("jid", "").split("/")[0].lower().strip()
            if j and j not in jids:
                jids.append(j)
        return jids

    async def fetch_affiliation_list(room, affiliation_type):
        """Mengembalikan list JID, [] jika server membalas kosong, None jika semua metode gagal."""
        result = None
        # 1) Coba lewat plugin xep_0045
        try:
            xep45 = bot.plugin["xep_0045"]
            iq = await xep45.get_affiliation_list(room, affiliation=affiliation_type, timeout=10)
            result = _parse_affiliation_result(iq)
        except Exception as e:
            print(f"[{plugin_name}] xep_0045 {affiliation_type} list gagal untuk {room}: {e!r}")

        # 2) Fallback: IQ mentah jika hasil kosong / gagal
        if not result:
            try:
                raw = await _raw_affiliation_query(room, affiliation_type)
                if raw:
                    return raw
                if result is not None:
                    return result  # server memang membalas kosong
                return []
            except Exception as e:
                print(f"[{plugin_name}] raw {affiliation_type} list gagal untuk {room}: {e!r}")
                return result  # None jika dua-duanya gagal
        return result

    # Helper canggih untuk mendeteksi JID asli (mendukung pencarian offline & daftar affiliation server)
    async def resolve_target_jid_safe(room, target_query):
        target_jid = target_query
        display_name = target_query

        # 1. Cek di room_users aktif
        if room and room in bot.room_users:
            if target_query in bot.room_users[room]:
                info = bot.room_users[room][target_query]
                return target_query, info.get("jid") or target_query
            else:
                for n, info in bot.room_users[room].items():
                    j = info.get("jid")
                    if n.lower() == target_query.lower() or (j and target_query.lower() in j.lower()):
                        return n, j or target_query

        # 2. Cek di roster room XEP-0045 jika user tidak ditemukan di room_users
        if room:
            try:
                room_roster = await bot.plugin["xep_0045"].get_roster(room)
                if target_query in room_roster:
                    info = room_roster[target_query]
                    return target_query, info.get("jid") or target_query
                for n, info in room_roster.items():
                    j = info.get("jid")
                    if n.lower() == target_query.lower() or (j and target_query.lower() in j.lower()):
                        return n, j or target_query
            except Exception:
                pass

        # 3. Jika input tidak memiliki '@' (kemungkinan besar nickname/nama) dan user sedang offline,
        # coba cocokkan dengan daftar member/admin/owner/outcast dari server XMPP
        if room and "@" not in target_query:
            for aff_type in ["member", "admin", "owner", "outcast"]:
                try:
                    aff_list = await fetch_affiliation_list(room, aff_type)
                    if aff_list:
                        for jid_item in aff_list:
                            username_part = jid_item.split("@")[0]
                            if target_query.lower() == username_part.lower() or target_query.lower() in jid_item.lower():
                                return jid_item, jid_item
                except Exception:
                    pass

        return display_name, target_jid

    # Helper untuk mengecek apakah sender adalah Admin, Owner Room, atau Bot Owner global
    async def check_is_privileged(sender, room, nick=None):
        sender_clean = str(sender).split("/")[0].lower()

        owners = []  # diinisialisasi dulu agar tidak NameError jika get_owners() gagal
        try:
            owners = [o.lower() for o in bot.get_owners()]
            if sender_clean in owners:
                return True
        except Exception:
            pass

        if room and room in bot.room_users:
            if nick and nick in bot.room_users[room]:
                user_info = bot.room_users[room][nick]
                user_jid = str(user_info.get("jid", "")).split("/")[0].lower()
                if user_jid in owners or user_info.get("affiliation") in ("admin", "owner"):
                    return True

            for n, info in bot.room_users[room].items():
                j = str(info.get("jid", "")).split("/")[0].lower()
                if (j and j == sender_clean) or n.lower() == str(sender).lower():
                    if j in owners or info.get("affiliation") in ("admin", "owner"):
                        return True

        if room:
            try:
                room_roster = await bot.plugin["xep_0045"].get_roster(room)
                for n, info in room_roster.items():
                    j = str(info.get("jid", "")).split("/")[0].lower()
                    if j and j == sender_clean:
                        if j in owners or info.get("affiliation") in ("admin", "owner"):
                            return True
            except Exception:
                pass

        return False

    @bot.command("access", "👤 Participant & Member")
    async def cmd_access(sender, room, nick, is_private, args):
        """access/access <nick>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return

        target_query = " ".join(args) if args else nick
        target_info = None
        real_jid = None
        found_nick = target_query

        if room in bot.room_users and target_query in bot.room_users[room]:
            target_info = bot.room_users[room][target_query]
            real_jid = target_info.get("jid")
        else:
            try:
                room_roster = await bot.plugin["xep_0045"].get_roster(room)
                if target_query in room_roster:
                    target_info = room_roster[target_query]
                    real_jid = target_info.get("jid")
            except Exception:
                pass

            if not target_info and room in bot.room_users:
                for n, info in bot.room_users[room].items():
                    j = info.get("jid")
                    if j and target_query.lower() in j.lower():
                        found_nick = n
                        target_info = info
                        real_jid = j
                        break

        if target_info:
            aff = target_info.get("affiliation", "none")
            role = target_info.get("role", "none")

            is_db_owner = False
            check_j = real_jid if real_jid else (
                bot.room_users[room].get(found_nick, {}).get("jid")
                if room in bot.room_users and found_nick in bot.room_users[room] else found_nick
            )
            if check_j:
                clean_j = str(check_j).split("/")[0].lower()
                try:
                    owners = [o.lower() for o in bot.get_owners()]
                except Exception:
                    owners = []
                if clean_j in owners:
                    is_db_owner = True

            owner_badge = m.get("owner_badge", " [Bot Owner]") if is_db_owner else ""
            default_access = m.get("default_access_template", "User: {found_nick}{owner_badge}\nAffiliation: {aff}\nRole: {role}")

            access_template = m.get("access_info", default_access)
            try:
                answer = access_template.format(found_nick=found_nick, owner_badge=owner_badge, aff=aff, role=role)
            except KeyError:
                answer = access_template.format(found_nick=found_nick, aff=aff, role=role) + owner_badge

            await bot.reply_user(sender, room, answer, is_private, nick=nick)
        else:
            err_notfound = fmt(m, "err_not_found", "User {target_query} not found.", target_query=target_query)
            await bot.reply_user(sender, room, err_notfound, is_private, nick=nick)

    @bot.command("admin", "💎 Admin & Owner Group")
    async def cmd_admin(sender, room, nick, is_private, args):
        """admin <nick/jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_query = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_query)
        clean_jid = str(target_jid).split("/")[0].lower()

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_jid, affiliation="admin")
            succ_msg = fmt(m, "admin_success", target_nick=display_name)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_admin_rights")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_nick=target_query)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "admin_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("adminlist", "💎 Admin & Owner Group")
    async def cmd_adminlist(sender, room, nick, is_private, args):
        """adminlist"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return

        if not await check_is_privileged(sender, room, nick):
            msg = m.get("err_action_forbidden")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        if room and not is_private:
            notice_msg = m.get("list_sent_pm")
            await bot.reply_user(sender, room, notice_msg, is_private=False, nick=nick)

        admin_users = await fetch_affiliation_list(room, "admin")

        if admin_users:
            admin_text = m.get("adminlist_header") + "\n- " + "\n- ".join(admin_users)
        else:
            admin_text = m.get("adminlist_empty")

        await bot.reply_user(sender, room, admin_text, is_private=True, nick=nick)

    @bot.command("ban", "💎 Admin & Owner Group", aliases=["blokir"])
    async def cmd_ban(sender, room, nick, is_private, args):
        """ban <nick/jid/server>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return
        target_nick = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_nick)

        clean_target = str(target_jid).split("/")[0].lower().strip()

        # Validasi: harus JID (user@server) atau domain server (mengandung '.'), bukan nickname mentah
        if not clean_target or ("@" not in clean_target and "." not in clean_target):
            err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
            await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            return

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_target, affiliation="outcast")

            bot.cursor.execute(
                "INSERT OR IGNORE INTO banned_list (room_jid, target) VALUES (?, ?)",
                (room.lower(), clean_target)
            )
            bot.conn.commit()

            succ_msg = fmt(m, "ban_success", target_nick=target_nick)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "ban_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("banlist", "💎 Admin & Owner Group")
    async def cmd_banlist(sender, room, nick, is_private, args):
        """banlist"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return

        if not await check_is_privileged(sender, room, nick):
            await bot.reply_user(sender, room, m.get("err_action_forbidden"), is_private, nick=nick)
            return

        if not is_private:
            await bot.reply_user(sender, room, m.get("list_sent_pm"), is_private=False, nick=nick)

        banned_users = await fetch_affiliation_list(room, "outcast")

        if banned_users:
            # Server membalas dengan daftar: tampilkan itu, sinkronkan ke database sebagai cadangan
            try:
                for jid_str in banned_users:
                    bot.cursor.execute(
                        "INSERT OR IGNORE INTO banned_list (room_jid, target) VALUES (?, ?)",
                        (room.lower(), jid_str.lower())
                    )
                bot.conn.commit()
            except Exception as e:
                print(f"[{plugin_name}] gagal sinkron banned_list: {e!r}")
        else:
            # Server gagal/kosong -> pakai database
            try:
                bot.cursor.execute("SELECT target FROM banned_list WHERE room_jid = ?", (room.lower(),))
                banned_users = [r[0] for r in bot.cursor.fetchall() if r[0]]
            except Exception as e:
                print(f"[{plugin_name}] gagal baca banned_list: {e!r}")
                banned_users = []

        if banned_users:
            ban_text = m.get("banlist_header") + "\n- " + "\n- ".join(sorted(set(banned_users)))
        else:
            ban_text = m.get("banlist_empty")

        await bot.reply_user(sender, room, ban_text, is_private=True, nick=nick)

    @bot.command("kick", "💎 Admin & Owner Group")
    async def cmd_kick(sender, room, nick, is_private, args):
        """kick <nick> [reason]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            await bot.reply_user(sender, room, m.get("kick_format_err"), is_private, nick=nick)
            return

        target_nick = None
        reason = m.get("kick_default_reason")

        joined_args = " ".join(args)
        if room in bot.room_users:
            sorted_nicks = sorted(bot.room_users[room].keys(), key=len, reverse=True)
            for n in sorted_nicks:
                if joined_args.lower().startswith(n.lower()):
                    target_nick = n
                    remaining = joined_args[len(n):].strip()
                    if remaining:
                        reason = remaining
                    break

        if not target_nick:
            target_nick = args[0]
            if len(args) > 1:
                reason = " ".join(args[1:])

        if room in bot.room_users and target_nick not in bot.room_users[room]:
            err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
            await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            return

        try:
            await bot.plugin["xep_0045"].set_role(room=room, nick=target_nick, role="none", reason=reason)
            succ_msg = fmt(m, "kick_success", target_nick=target_nick)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            elif "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            else:
                err_fail = fmt(m, "kick_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("member", "💎 Admin & Owner Group")
    async def cmd_member(sender, room, nick, is_private, args):
        """member <nick/jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_query = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_query)
        clean_jid = str(target_jid).split("/")[0].lower()

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_jid, affiliation="member")
            succ_msg = fmt(m, "member_success", target_nick=display_name)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_query=target_query)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "member_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("memberlist", "💎 Admin & Owner Group")
    async def cmd_memberlist(sender, room, nick, is_private, args):
        """memberlist"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return

        if not await check_is_privileged(sender, room, nick):
            msg = m.get("err_action_forbidden")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        if room and not is_private:
            notice_msg = m.get("list_sent_pm")
            await bot.reply_user(sender, room, notice_msg, is_private=False, nick=nick)

        member_users = await fetch_affiliation_list(room, "member")

        if member_users:
            member_text = m.get("memberlist_header") + "\n- " + "\n- ".join(member_users)
        else:
            member_text = m.get("memberlist_empty")

        await bot.reply_user(sender, room, member_text, is_private=True, nick=nick)

    @bot.command("moderator", "💎 Admin & Owner Group")
    async def cmd_moderator(sender, room, nick, is_private, args):
        """moderator <nick>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_nick = " ".join(args)
        if room in bot.room_users:
            sorted_nicks = sorted(bot.room_users[room].keys(), key=len, reverse=True)
            for n in sorted_nicks:
                if " ".join(args).lower().startswith(n.lower()):
                    target_nick = n
                    break

        if room in bot.room_users and target_nick not in bot.room_users[room]:
            err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
            await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            return

        try:
            await bot.plugin["xep_0045"].set_role(room=room, nick=target_nick, role="moderator")
            succ_msg = fmt(m, "moderator_success", target_nick=target_nick)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "moderator_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("nickbot", "💎 Admin & Owner Group")
    async def cmd_nickbot(sender, room, nick, is_private, args):
        """nickbot <bot-name>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        new_nick = " ".join(args)
        old_nick = bot.get_room_nick(room)

        bot.set_room_nick(room, new_nick)

        try:
            if room in bot.room_users and old_nick in bot.room_users[room]:
                del bot.room_users[room][old_nick]

            bot.plugin["xep_0045"].leave_muc(room, old_nick)
            await asyncio.sleep(0.5)
            bot.plugin["xep_0045"].join_muc(room, new_nick, pstatus=bot.bot_status)
        except Exception:
            pass

        succ_msg = fmt(m, "nickbot_success", new_nick=new_nick)
        await bot.reply_user(sender, room, succ_msg, is_private, nick=new_nick)

    @bot.command("owner", "💎 Admin & Owner Group")
    async def cmd_owner(sender, room, nick, is_private, args):
        """owner <nick/jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_query = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_query)
        clean_jid = str(target_jid).split("/")[0].lower()

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_jid, affiliation="owner")
            succ_msg = fmt(m, "owner_success", target_nick=display_name)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_admin_rights")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_query=target_query)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "owner_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("ownerlist", "💎 Admin & Owner Group")
    async def cmd_ownerlist(sender, room, nick, is_private, args):
        """ownerlist"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return

        if not await check_is_privileged(sender, room, nick):
            msg = m.get("err_action_forbidden")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        if room and not is_private:
            notice_msg = m.get("list_sent_pm")
            await bot.reply_user(sender, room, notice_msg, is_private=False, nick=nick)

        owner_users = await fetch_affiliation_list(room, "owner")

        if owner_users:
            owner_text = m.get("ownerlist_header") + "\n- " + "\n- ".join(owner_users)
        else:
            owner_text = m.get("ownerlist_empty")

        await bot.reply_user(sender, room, owner_text, is_private=True, nick=nick)

    @bot.command("participant", "💎 Admin & Owner Group")
    async def cmd_participant(sender, room, nick, is_private, args):
        """participant <nick>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_nick = " ".join(args)
        if room in bot.room_users:
            sorted_nicks = sorted(bot.room_users[room].keys(), key=len, reverse=True)
            for n in sorted_nicks:
                if " ".join(args).lower().startswith(n.lower()):
                    target_nick = n
                    break

        if room in bot.room_users and target_nick not in bot.room_users[room]:
            err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
            await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            return

        try:
            await bot.plugin["xep_0045"].set_role(room=room, nick=target_nick, role="participant")
            succ_msg = fmt(m, "participant_success", target_nick=target_nick)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "participant_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("prefix", "💎 Admin & Owner Group")
    async def cmd_prefix(sender, room, nick, is_private, args):
        """prefix <symbol>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_prefix_only"), is_private, nick=nick)
            return

        room_prefix = bot.get_room_prefix(room)
        if args:
            new_prefix = args[0].strip()
            if new_prefix.lower() == "del":
                bot.set_room_prefix(room, "")
                succ_msg = m.get("prefix_deleted")
                await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
            else:
                bot.set_room_prefix(room, new_prefix)
                succ_msg = fmt(m, "prefix_changed", new_prefix=new_prefix)
                await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        else:
            curr_p = room_prefix if room_prefix else m.get("prefix_none")
            succ_msg = fmt(m, "prefix_current", curr_p=curr_p)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)

    @bot.command("rejoin", "💎 Admin & Owner Group")
    async def cmd_rejoin(sender, room, nick, is_private, args):
        """rejoin"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room:
            await bot.reply_user(sender, room, m.get("err_room_only"), is_private, nick=nick)
            return
        try:
            bot_nick = bot.get_room_nick(room)
            bot.plugin["xep_0045"].leave_muc(room, bot_nick)
            await asyncio.sleep(1)
            bot.plugin["xep_0045"].join_muc(room, bot_nick, pstatus=bot.bot_status)
            succ_msg = m.get("rejoin_success")
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_fail = fmt(m, "rejoin_fail", e=e)
            await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("unadmin", "💎 Admin & Owner Group")
    async def cmd_unadmin(sender, room, nick, is_private, args):
        """unadmin <jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_query = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_query)
        clean_jid = str(target_jid).split("/")[0].lower()

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_jid, affiliation="none")
            succ_msg = fmt(m, "unadmin_success", target_nick=display_name)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            else:
                err_fail = fmt(m, "unadmin_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("unowner", "💎 Admin & Owner Group")
    async def cmd_unowner(sender, room, nick, is_private, args):
        """unowner <jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_query = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_query)
        clean_jid = str(target_jid).split("/")[0].lower()

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_jid, affiliation="none")
            succ_msg = fmt(m, "unowner_success", target_nick=display_name)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            else:
                err_fail = fmt(m, "unowner_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("unban", "💎 Admin & Owner Group")
    async def cmd_unban(sender, room, nick, is_private, args):
        """unban <jid/server>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return
        target_nick = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_nick)

        clean_target = str(target_jid).split("/")[0].lower().strip()
        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_target, affiliation="none")

            bot.cursor.execute(
                "DELETE FROM banned_list WHERE room_jid = ? AND target = ?",
                (room.lower(), clean_target)
            )
            bot.conn.commit()

            succ_msg = fmt(m, "unban_success", target_nick=target_nick)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            else:
                err_fail = fmt(m, "unban_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("unmember", "💎 Admin & Owner Group")
    async def cmd_unmember(sender, room, nick, is_private, args):
        """unmember <nick/jid>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_query = " ".join(args)
        display_name, target_jid = await resolve_target_jid_safe(room, target_query)
        clean_jid = str(target_jid).split("/")[0].lower()

        # Validasi akhir agar memastikan format JID valid (mengandung '@') sebelum dikirim ke XMPP server
        if not clean_jid or "@" not in clean_jid:
            err_absent = fmt(m, "err_user_absent", "User {target_query} not found.", target_query=target_query)
            await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            return

        try:
            await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_jid, affiliation="none")
            succ_msg = fmt(m, "unmember_success", target_nick=display_name)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            else:
                err_fail = fmt(m, "unmember_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)

    @bot.command("visitor", "💎 Admin & Owner Group", aliases=["bungkam"])
    async def cmd_visitor(sender, room, nick, is_private, args):
        """visitor <nick>"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        if not room or not args:
            return

        target_nick = " ".join(args)
        if room in bot.room_users:
            sorted_nicks = sorted(bot.room_users[room].keys(), key=len, reverse=True)
            for n in sorted_nicks:
                if " ".join(args).lower().startswith(n.lower()):
                    target_nick = n
                    break

        if room in bot.room_users and target_nick not in bot.room_users[room]:
            err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
            await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            return

        try:
            await bot.plugin["xep_0045"].set_role(room=room, nick=target_nick, role="visitor")
            succ_msg = fmt(m, "visitor_success", target_nick=target_nick)
            await bot.reply_user(sender, room, succ_msg, is_private, nick=nick)
        except Exception as e:
            err_str = str(e).lower()
            if "not-allowed" in err_str or "forbidden" in err_str or "cancel" in err_str:
                msg = m.get("err_action_forbidden")
                await bot.reply_user(sender, room, msg, is_private, nick=nick)
            elif "not-acceptable" in err_str or "does not exist" in err_str:
                err_absent = fmt(m, "err_user_absent", target_nick=target_nick)
                await bot.reply_user(sender, room, err_absent, is_private, nick=nick)
            else:
                err_fail = fmt(m, "visitor_fail", e=e)
                await bot.reply_user(sender, room, err_fail, is_private, nick=nick)