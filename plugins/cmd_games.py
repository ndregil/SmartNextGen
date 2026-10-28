# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import random
import asyncio
import os

# --- STATE GAMES GLOBAL DALAM MEMORI ---
ACTIVE_GAMES = {
    "trivia": {},        # room: {"question": str, "answer": str, "active": bool}
    "guessnumber": {},   # room: {"target": int, "active": bool}
    "wordchain": {}      # room: {"last_word": str, "active": bool, "last_player": str}
}

def register(bot):
    """Mendaftarkan plugin game ke bot utama."""
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

    def L(lang, key):
        """Ambil daftar (list) dari JSON dengan fallback: bahasa aktif -> en -> id."""
        for code in (lang, "en", "id"):
            val = LANG_MESSAGES.get(code, {}).get(key)
            if isinstance(val, list) and val:
                return val
        return []

    # 1. KUIS TRIVIA (Pengetahuan Umum)
    @bot.command("trivia", "👤 Participant & Member", aliases=["quiz"])
    async def cmd_trivia(sender, room, nick, is_private, args):
        """trivia"""
        target_key = room if room else sender
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        if target_key in ACTIVE_GAMES["trivia"] and ACTIVE_GAMES["trivia"][target_key].get("active"):
            msg = m.get("trivia_ongoing")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        questions = [
            (m.get("trivia_q_1"), m.get("trivia_a_1")),
            (m.get("trivia_q_2"), m.get("trivia_a_2")),
            (m.get("trivia_q_3"), m.get("trivia_a_3")),
            (m.get("trivia_q_4"), m.get("trivia_a_4")),
            (m.get("trivia_q_5"), m.get("trivia_a_5")),
            (m.get("trivia_q_6"), m.get("trivia_a_6")),
            (m.get("trivia_q_7"), m.get("trivia_a_7")),
            (m.get("trivia_q_8"), m.get("trivia_a_8"))
        ]
        
        q, a = random.choice(questions)
        ACTIVE_GAMES["trivia"][target_key] = {"question": q, "answer": a.lower(), "active": True}
        
        msg = m.get("trivia_start").format(q=q)
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("ans", "👤 Participant & Member", aliases=["answer"])
    async def cmd_ans(sender, room, nick, is_private, args):
        """Example commands:: ans <answer>"""
        target_key = room if room else sender
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        if target_key not in ACTIVE_GAMES["trivia"] or not ACTIVE_GAMES["trivia"][target_key].get("active"):
            msg = m.get("ans_no_active")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        if not args:
            msg = m.get("ans_prompt")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        user_answer = " ".join(args).lower()
        correct_answer = ACTIVE_GAMES["trivia"][target_key]["answer"]

        if user_answer == correct_answer:
            ACTIVE_GAMES["trivia"][target_key]["active"] = False
            msg = m.get("ans_correct").format(correct_answer=correct_answer)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("ans_wrong").format(user_answer=user_answer)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("stoptrivia", "💎 Admin & Owner Group", aliases=[])
    async def cmd_stoptrivia(sender, room, nick, is_private, args):
        """stoptrivia"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        is_owner = await bot.verify_real_owner_from_server(room, nick, sender) if hasattr(bot, "verify_real_owner_from_server") else False
        privilege = await bot.get_user_room_privilege(room, nick, sender) if hasattr(bot, "get_user_room_privilege") else "member"
        
        if not is_owner and privilege != "admin":
            ai_prompt = m.get("stoptrivia_ai_prompt").format(nick=nick)
            default_refusal = m.get("stoptrivia_default")

            session_key = f"room:{room}_user:{str(sender).lower()}" if room else f"pm:{str(sender).lower()}"
            
            if hasattr(bot, "ask_ai_with_fallback"):
                refusal_msg = await bot.ask_ai_with_fallback(ai_prompt, room=room, session_key=session_key)
            else:
                refusal_msg = default_refusal

            await bot.reply_user(sender, room, refusal_msg, is_private, nick=nick)
            return

        target_key = room if room else sender
        if target_key in ACTIVE_GAMES["trivia"]:
            ACTIVE_GAMES["trivia"][target_key]["active"] = False
            msg = m.get("stoptrivia_success")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("stoptrivia_none")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    # 2. TEBAK ANGKA
    @bot.command("guess", "👤 Participant & Member", aliases=["guessnumber"])
    async def cmd_guess(sender, room, nick, is_private, args):
        """guess <number> """
        target_key = room if room else sender
        lang = get_lang(sender, room)
        m = get_m(lang)

        if target_key not in ACTIVE_GAMES["guessnumber"] or not ACTIVE_GAMES["guessnumber"][target_key].get("active"):
            secret_number = random.randint(1, 50)
            ACTIVE_GAMES["guessnumber"][target_key] = {"target": secret_number, "active": True}
            msg = m.get("guess_start")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        if not args:
            msg = m.get("guess_running")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        try:
            guess = int(args[0])
        except ValueError:
            msg = m.get("guess_invalid_format")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        secret = ACTIVE_GAMES["guessnumber"][target_key]["target"]

        if guess == secret:
            ACTIVE_GAMES["guessnumber"][target_key]["active"] = False
            msg = m.get("guess_correct").format(secret=secret)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        elif guess < secret:
            msg = m.get("guess_small")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("guess_big")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    # 3. LEMPAR DADU & LEMPAR KOIN
    @bot.command("roll", "👤 Participant & Member", aliases=["dice"])
    async def cmd_roll(sender, room, nick, is_private, args):
        """roll"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        val = random.randint(1, 6)
        emojis = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
        chosen_emoji = emojis[val - 1]
        msg = m.get("roll_result").format(val=val, chosen_emoji=chosen_emoji)
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("toss", "👤 Participant & Member", aliases=["coin"])
    async def cmd_toss(sender, room, nick, is_private, args):
        """toss"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        heads_text = m.get("toss_heads")
        tails_text = m.get("toss_tails")
        result = random.choice([heads_text, tails_text])
        msg = m.get("toss_result").format(result=result)
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    # 4. SAMBUNG KATA
    @bot.command("wordchain", "👤 Participant & Member", aliases=["wc"])
    async def cmd_wordchain(sender, room, nick, is_private, args):
        """wordchain <say>"""
        target_key = room if room else sender
        lang = get_lang(sender, room)
        m = get_m(lang)

        if target_key not in ACTIVE_GAMES["wordchain"] or not ACTIVE_GAMES["wordchain"][target_key].get("active"):
            start_word = random.choice(L(lang, "wordchain_start_words") or ["bola", "mobil", "ikan", "rumah", "buku", "api", "gedung"])
            ACTIVE_GAMES["wordchain"][target_key] = {
                "last_word": start_word,
                "active": True,
                "last_player": None
            }
            char = start_word[-1].upper()
            msg = m.get("wordchain_start").format(start_word=start_word, char=char)
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        if not args:
            current_w = ACTIVE_GAMES["wordchain"][target_key]["last_word"]
            msg = m.get("wordchain_running").format(
                current_w=current_w,
                first_char=current_w[0],
                last_char=current_w[-1]
            )
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        new_word = args[0].lower()
        game_data = ACTIVE_GAMES["wordchain"][target_key]
        last_word = game_data["last_word"]
        required_char = last_word[-1]

        if not new_word.startswith(required_char):
            msg = m.get("wordchain_wrong").format(
                new_word=new_word,
                required_char=required_char.upper(),
                last_word=last_word
            )
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
            return

        game_data["last_word"] = new_word
        next_char = new_word[-1]
        msg = m.get("wordchain_correct").format(next_char=next_char.upper())
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("stopwordchain", "💎 Admin & Owner Group", aliases=[])
    async def cmd_stopwordchain(sender, room, nick, is_private, args):
        """stopwordchain"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        is_owner = await bot.verify_real_owner_from_server(room, nick, sender) if hasattr(bot, "verify_real_owner_from_server") else False
        privilege = await bot.get_user_room_privilege(room, nick, sender) if hasattr(bot, "get_user_room_privilege") else "member"

        if not is_owner and privilege != "admin":
            ai_prompt = m.get("stopwordchain_ai_prompt").format(nick=nick)
            default_refusal = m.get("stopwordchain_default")

            session_key = f"room:{room}_user:{str(sender).lower()}" if room else f"pm:{str(sender).lower()}"
            
            if hasattr(bot, "ask_ai_with_fallback"):
                refusal_msg = await bot.ask_ai_with_fallback(ai_prompt, room=room, session_key=session_key)
            else:
                refusal_msg = default_refusal

            await bot.reply_user(sender, room, refusal_msg, is_private, nick=nick)
            return

        target_key = room if room else sender
        if target_key in ACTIVE_GAMES["wordchain"]:
            ACTIVE_GAMES["wordchain"][target_key]["active"] = False
            msg = m.get("stopwordchain_success")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)
        else:
            msg = m.get("stopwordchain_none")
            await bot.reply_user(sender, room, msg, is_private, nick=nick)

    # 5. VIRTUAL PET / MONSTER SIMULATOR
    @bot.command("pet", "👤 Participant & Member", aliases=["virtualpet"])
    async def cmd_pet(sender, room, nick, is_private, args):
        """pet"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        pet_names = [T(lang, f"pet_name_{i}") for i in range(1, 5)]
            
        chosen_pet = random.choice(pet_names)
        health = random.randint(70, 100)
        hunger = random.randint(20, 80)
        
        mood = m.get("pet_mood_happy") if health > 80 else m.get("pet_mood_hungry")
        msg = m.get("pet_status").format(
            chosen_pet=chosen_pet,
            health=health,
            hunger=hunger,
            mood=mood
        )
        await bot.reply_user(sender, room, msg, is_private, nick=nick)

    @bot.command("feed", "👤 Participant & Member", aliases=[])
    async def cmd_feed(sender, room, nick, is_private, args):
        """feed"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        
        foods = [T(lang, f"food_{i}") for i in range(1, 5)]
            
        chosen_food = random.choice(foods)
        msg = m.get("feed_result").format(food=chosen_food)
        await bot.reply_user(sender, room, msg, is_private, nick=nick)
