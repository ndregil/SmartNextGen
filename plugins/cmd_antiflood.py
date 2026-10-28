# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import inspect
import os
import re
import time
import unicodedata
from collections import defaultdict

def register(bot):
    # Mengambil nama plugin secara otomatis dari nama file
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    
    # Memuat kamus bahasa JSON dari direktori lang/cmd_antiflood/
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

    def debug(text):
        """Log ke terminal hanya jika setting mod_flood_debug = 1 (default: senyap)."""
        try:
            if str(bot.get_setting("mod_flood_debug", "0")) == "1":
                print(text)
        except Exception:
            pass

    def get_m(lang):
        """Helper untuk mengambil kamus bahasa dengan fallback aman ke 'id'."""
        return LANG_MESSAGES.get(lang, LANG_MESSAGES.get("id", {}))

    # Melacak jumlah pesan beruntun per user
    message_history = defaultdict(lambda: defaultdict(list))
    last_warned = defaultdict(dict)

    # Melacak frekuensi pesan mengandung '@' secara global per room dalam waktu singkat
    room_mention_burst = defaultdict(list)

    # Konfigurasi Anti-Bot Mention Cerdas
    MAX_USER_MESSAGES = 3       # Batas pesan per user dalam 1 window
    TIME_WINDOW_USER = 4.0      
    
    BURST_LIMIT_ROOM = 4        # Maksimal total pesan ber-mention dari SEMUA akun dalam waktu singkat
    TIME_WINDOW_BURST = 3.0     # Rentang waktu deteksi ledakan (detik)
    
    COOLDOWN_TIME = 15.0        # Jeda waktu hukuman

    def is_history_message(msg):
        """True jika pesan adalah riwayat (delayed) yang dikirim ulang MUC saat bot join/reconnect.

        Pesan riwayat membawa tag <delay xmlns='urn:xmpp:delay'/> (XEP-0203) atau tag lama
        <x xmlns='jabber:x:delay'/> (XEP-0091). Pesan seperti ini bukan pesan baru sehingga
        tidak boleh dihitung sebagai flood.
        """
        try:
            xml = getattr(msg, "xml", None)
            if xml is not None:
                if xml.find("{urn:xmpp:delay}delay") is not None:
                    return True
                if xml.find("{jabber:x:delay}x") is not None:
                    return True
        except Exception:
            pass
        return False

    async def handle_anti_flood(msg):
        try:
            # Abaikan riwayat chat lama (dikirim server saat bot masuk room / reconnect)
            if is_history_message(msg):
                return

            from_str = str(msg.get("from", ""))
            if not from_str:
                return
            
            room = from_str.split("/")[0]
            nick = from_str.split("/")[1] if "/" in from_str else ""
            
            if not nick:
                return

            current_bot_nick = bot.get_room_nick(room) if hasattr(bot, "get_room_nick") else ""
            if nick == current_bot_nick:
                return

            body = msg.get("body", "")
            current_time = time.time()

            # Mengambil JID asli menggunakan pola seperti plugin admin Anda
            target_jid = nick
            if hasattr(bot, "room_users") and room in bot.room_users and nick in bot.room_users[room]:
                target_jid = bot.room_users[room][nick].get("jid") or nick
            
            clean_target = str(target_jid).split("/")[0].lower()

            # 1. Cek apakah pesan mengandung karakter '@' (indikasi sedang mention seseorang)
            is_mention = "@" in body

            # 2. Deteksi Standar Per-User
            user_timestamps = message_history[room][from_str]
            user_timestamps = [t for t in user_timestamps if current_time - t <= TIME_WINDOW_USER]
            user_timestamps.append(current_time)
            message_history[room][from_str] = user_timestamps

            lang = get_lang(from_str, room)
            m = get_m(lang)

            if len(user_timestamps) > MAX_USER_MESSAGES:
                reason = T(lang, "reason_spam")
                await punish_user(bot, room, from_str, nick, clean_target, reason, lang)
                return

            # 3. Deteksi Lonjakan Mention Global (Meskipun target nick-nya berbeda-beda)
            if is_mention:
                burst_list = room_mention_burst[room]
                # Bersihkan data lama
                burst_list = [t for t in burst_list if current_time - t <= TIME_WINDOW_BURST]
                burst_list.append(current_time)
                room_mention_burst[room] = burst_list

                # Jika dalam rentang waktu singkat ada banyak pesan ber-mention masuk secara serentak
                if len(burst_list) > BURST_LIMIT_ROOM:
                    reason = T(lang, "reason_burst")
                    await punish_user(bot, room, from_str, nick, clean_target, reason, lang)
                    return

        except Exception as e:
            debug(f"Error Anti-Flood Dynamic Mention: {e}")

    async def punish_user(bot, room, from_str, nick, clean_target, reason, lang="id"):
        current_time = time.time()
        last_warn = last_warned[room].get(from_str, 0)
        m = get_m(lang)
        
        if current_time - last_warn > COOLDOWN_TIME:
            last_warned[room][from_str] = current_time

            warning_text = T(lang, "warn_message", nick=nick, reason=reason)
            await bot.reply_user(from_str, room, warning_text, is_private=False, nick=nick)

            try:
                if hasattr(bot, "plugin") and "xep_0045" in bot.plugin:
                    # 1. Eksekusi ban (outcast) menggunakan JID bersih persis seperti perintah ban manual
                    await bot.plugin["xep_0045"].set_affiliation(room=room, jid=clean_target, affiliation="outcast")
                    
                    # 2. Catat ke database banned_list lokal bot (jika cursor tersedia)
                    if hasattr(bot, "cursor") and hasattr(bot, "conn") and bot.cursor:
                        bot.cursor.execute(
                            "INSERT OR IGNORE INTO banned_list (room_jid, target) VALUES (?, ?)",
                            (room.lower(), clean_target)
                        )
                        bot.conn.commit()

            except Exception as e:
                debug(f"Gagal mem-ban otomatis pada {nick} ({clean_target}): {e}")

    # ==================================================================
    # MODERASI KONTEN: kata terlarang & nickname terlarang
    # Cakupan: GLOBAL (semua room) + per-room. Perintah global khusus owner bot.
    # ==================================================================
    WORD_WARN_LIMIT = 2            # jumlah peringatan; pelanggaran berikutnya = kick
    WORD_STRIKE_WINDOW = 600.0     # detik; pelanggaran lebih lama dari ini dilupakan
    NICK_ACTION_COOLDOWN = 30.0    # jeda minimal antar tindakan untuk nick yang sama
    MAX_ENTRIES_PER_ROOM = 200
    GLOBAL_KEY = "*"               # penanda cakupan global di database
    GLOBAL_WORDS_FILE = os.path.join("data", "badwords.txt")   # opsional: 1 kata per baris (global)

    # ---- DAFTAR BAWAAN (berlaku di semua room; bisa dimatikan: gbadword defaults off) ----
    # Kata utuh dicocokkan tanpa peduli leet-speak/huruf berulang/spasi antar huruf.
    # Tulis dengan huruf kecil. Awali/akhiri * untuk pencocokan sebagian (hati-hati salah deteksi).
    DEFAULT_BADWORDS = [
        # --- Indonesia / Melayu / Jawa ---
        "anjing", "bangsat", "bajingan", "keparat", "brengsek",
        "goblok", "tolol", "kontol", "peler", "memek", "pepek", "ngentot", "ngentod",
        "entot", "ngewe", "jancok", "jancuk", "dancok", "diancok", "lonte", "pelacur", "itil",
        "pejuh", "meki", "jembut", "pantek", "pukimak", "pukimai", "puki", "sundal", "cibai",
        # --- English ---
        "*fuck*", "shit", "shitty", "shite", "bullshit", "bitch", "bitches", "bastard",
        "asshole", "assholes", "dickhead", "cunt", "cunts", "pussy", "whore", "slut",
        "wanker", "twat", "bollocks", "faggot", "faggots", "nigger", "niggers", "nigga",
        "niggas", "retard", "retarded", "tranny", "kys",
        # --- Spanish ---
        "puta", "putas", "puto", "putos", "mierda", "pendejo", "pendeja", "cabron", "cabrona",
        "joder", "jodete", "gilipollas", "hijueputa", "hijoputa", "malparido", "marica",
        "maricon", "verga", "chingar", "chingada", "chingadera", "culero",
        # --- Portuguese ---
        "caralho", "merda", "foder", "fodase", "buceta", "arrombado", "vadia", "viado", "pqp",
        # --- French ---
        "merde", "putain", "pute", "connard", "connasse", "salope", "salopard", "batard",
        "*encul*", "nique", "niquer", "ntm", "fdp",
        # --- German ---
        "*scheiss*", "arsch", "*arschloch*", "ficken", "fick", "ficker", "hurensohn", "wichser",
        "fotze", "schlampe", "verpiss",
        # --- Italian ---
        "cazzo", "cazzi", "vaffanculo", "stronzo", "stronza", "puttana", "troia", "minchia",
        "coglione", "*porcodio*",
        # --- Dutch ---
        "klootzak", "godverdomme", "hoer", "kut", "lul", "flikker",
        # --- Polish ---
        "*kurw*", "*pierdol*", "*pierdal*", "*chuj*", "*jebac*", "*jebany*", "*pojeb*",
        "cwel", "dziwka", "pizda", "skurwysyn",
        # --- Turkish ---
        "amk", "*siktir*", "*sikeyim*", "*sikerim*", "*orospu*", "*pezevenk*", "*yarrak*",
        "amcik", "ibne", "gotveren",
        # --- Vietnamese (singkatan) ---
        "dmm", "dcm", "dkm", "vcl", "vkl", "cmm",
        # --- Tagalog ---
        "*putangina*", "*tangina*", "gago", "tarantado", "ulol", "pakshet",
        # --- Rusia (huruf Latin) ---
        "blyat", "blyad", "pizdec", "pizda", "pizdets", "ebat", "ebal", "yebat", "nahuy",
        "nahui", "pidor", "pidoras", "pidar", "mudak", "gandon", "zalupa", "dolboeb",
        # --- Arab (huruf Latin) ---
        "sharmouta", "sharmuta", "sharmoota", "kosomak", "kosomk", "manyak",
        # --- Hindi/Urdu (huruf Latin) ---
        "madarchod", "madarchodh", "behenchod", "bhenchod", "bhosdike", "bhosdi", "bhosdika",
        "chutiya", "chutia", "chutiye", "gandu", "gaandu", "harami", "raand", "randwa",
        # --- Rusia / Ukraina (Cyrillic) - butuh LANGKAH 2 ---
        "*хуй*", "*пизд*", "*бляд*", "*блят*", "блять", "бля", "сука", "суки", "сучка", "сучара",
        "ебать", "ебал", "*ебан*", "*ебуч*", "*заеб*", "*нахуй*", "*похуй*", "*охуе*",
        "*мудак*", "*мудил*", "*гандон*", "*гондон*", "*залуп*", "*пидор*", "*пидар*", "*педик*",
        "*долбоеб*", "*долбаеб*", "*шлюх*", "*шалав*", "мразь", "мрази", "*ублюд*",
        "говно", "говна", "говнюк", "*курв*", "*їбат*", "*їбан*", "*підар*", "*довбойоб*",
        # --- Arab (aksara Arab) - butuh LANGKAH 2 ---
        "كس", "كسك", "كسم", "*كسمك*", "*كسختك*", "*شرموط*", "*عاهر*", "*قحب*", "*منيوك*",
        "*متناك*",
        # --- Persia (aksara Arab-Persia) - butuh LANGKAH 2 ---
        "*کسکش*", "*کصکش*", "*جنده*", "*جاکش*", "*کونی*", "*کیرم*",
        # --- Mandarin - butuh LANGKAH 2 (cocok sebagian karena tanpa spasi) ---
        "*他妈的*", "*他媽的*", "*你妈逼*", "*操你*", "*草你*", "*幹你*", "*傻逼*", "*煞笔*",
        "*沙比*", "*婊子*", "*狗日的*", "*草泥马*", "*鸡巴*", "*贱人*",
        # --- Korea - butuh LANGKAH 2 ---
        "*시발*", "*씨발*", "*씨바*", "*병신*", "*개새끼*", "*지랄*", "*좆*",
    ]
    # Nick bawaan: mencegah peniruan peran & nick spam. Awalan "re:" = regex.
    DEFAULT_BADNICKS = [
        # peran (Latin, banyak bahasa)
        r"re:^(admin|admins|administrator|administrador|administrateur|administratore|moderator|moderador|moderateur|moderatore|owner|root|sysop|sysadmin|system|staff|support|pemilik|pengurus|pengelola|verwalter|besitzer|yonetici|sahip|wlasciciel|propietario|proprietario|proprietaire|botowner)[\W_\d]*$",
        # peran (Cyrillic / Arab / Mandarin)
        r"re:^(админ|администратор|модератор|модер|владелец|مدير|مشرف|ادمن|أدمن|管理员|管理員|版主|群主)[\W_\d]*$",
        # nick spam/porno
        r"re:(porn|onlyfans|sexcam|xxx|nudes?\b)",
    ]
    DEFAULT_MSG = {
        "id": {
            "bw_warn": "pesan Anda mengandung kata terlarang. Peringatan {n}/{limit}, jika berulang akan dikeluarkan dari room.",
            "bw_kick_notice": "{nick} dikeluarkan karena berulang kali memakai kata terlarang.",
            "bw_kick_reason": "Kata terlarang berulang kali",
            "bn_kick_notice": "{nick} dikeluarkan: nickname tidak diperbolehkan. Silakan masuk lagi dengan nick lain.",
            "bn_kick_reason": "Nickname tidak diperbolehkan",
            "mod_only": "Akses ditolak: perintah ini hanya untuk owner/admin/moderator room.",
            "owner_only": "Akses ditolak: perintah global hanya untuk owner bot.",
            "room_only": "Gunakan perintah ini di dalam room.",
            "usage_bw": "Pemakaian: add <kata...> | del <kata...> | list | on | off | defaults on/off (khusus global) | reload (global). Awali/akhiri dengan * agar cocok sebagian kata (contoh: *kata*).",
            "usage_bn": r"Pemakaian: add <pola...> | del <pola...> | list | on | off | defaults on/off (khusus global). Awali dengan re: untuk regex (contoh: re:^admin\d+$).",
            "added": "Berhasil menambah: {items}",
            "removed": "Berhasil menghapus: {items}",
            "invalid": "Dilewati (tidak valid): {items}",
            "not_found": "Tidak ditemukan: {items}",
            "limit": "Gagal: batas {max} entri tercapai.",
            "empty": "Daftar kosong.",
            "list_title": "Daftar ({count}): {items}",
            "global_info": "Ditambah {n} entri global yang berlaku di semua room.",
            "defaults_info": "Daftar bawaan script: {n} entri ({state}).",
            "defaults_set": "Daftar bawaan {what}: {state}.",
            "state_on": "Filter {what} diaktifkan.",
            "state_off": "Filter {what} dimatikan.",
            "state_info": "Filter {what}: {state} | jumlah entri: {count}",
            "reloaded": "Daftar global dimuat ulang ({count} kata dari file).",
            "what_words": "kata terlarang",
            "what_nicks": "nick terlarang",
            "scope_global": "(GLOBAL)",
            "on": "aktif",
            "off": "mati",
            "reason_spam": "spam pesan beruntun",
            "reason_burst": "serangan mention massal (bot)",
            "warn_message": "⚠️ {nick}, Anda diblokir otomatis: {reason}.",
            "info_text": "🛡️ Anti-Flood aktif\n• Maks {max_msg} pesan per {time_user} detik per pengguna\n• Maks {burst_limit} pesan ber-mention per {time_burst} detik di room\n• Pelanggar diblokir otomatis.",
        },
        "en": {
            "bw_warn": "your message contains a forbidden word. Warning {n}/{limit}; repeating it will get you kicked.",
            "bw_kick_notice": "{nick} was kicked for repeatedly using forbidden words.",
            "bw_kick_reason": "Repeated use of forbidden words",
            "bn_kick_notice": "{nick} was kicked: nickname not allowed. Please rejoin with another nick.",
            "bn_kick_reason": "Nickname not allowed",
            "mod_only": "Access denied: this command is for room owners/admins/moderators only.",
            "owner_only": "Access denied: global commands are for the bot owner only.",
            "room_only": "Use this command inside a room.",
            "usage_bw": "Usage: add <word...> | del <word...> | list | on | off | defaults on/off (global only) | reload (global). Start/end with * for partial match (e.g. *word*).",
            "usage_bn": r"Usage: add <pattern...> | del <pattern...> | list | on | off | defaults on/off (global only). Prefix with re: for regex (e.g. re:^admin\d+$).",
            "added": "Successfully added: {items}",
            "removed": "Successfully removed: {items}",
            "invalid": "Skipped (invalid): {items}",
            "not_found": "Not found: {items}",
            "limit": "Failed: limit of {max} entries reached.",
            "empty": "The list is empty.",
            "list_title": "List ({count}): {items}",
            "global_info": "Plus {n} global entries that apply in all rooms.",
            "defaults_info": "Built-in script list: {n} entries ({state}).",
            "defaults_set": "Built-in {what} list: {state}.",
            "state_on": "{what} filter enabled.",
            "state_off": "{what} filter disabled.",
            "state_info": "{what} filter: {state} | entries: {count}",
            "reloaded": "Global list reloaded ({count} words from file).",
            "what_words": "forbidden words",
            "what_nicks": "forbidden nicks",
            "scope_global": "(GLOBAL)",
            "on": "on",
            "off": "off",
            "reason_spam": "consecutive message spam",
            "reason_burst": "mass mention attack (bot)",
            "warn_message": "⚠️ {nick}, you were automatically banned: {reason}.",
            "info_text": "🛡️ Anti-Flood is active\n• Max {max_msg} messages per {time_user} seconds per user\n• Max {burst_limit} mention messages per {time_burst} seconds in a room\n• Offenders are banned automatically.",
        },
    }

    def T(lang, key, **kw):
        text = (get_m(lang).get(key)
                or DEFAULT_MSG.get(lang, DEFAULT_MSG["id"]).get(key)
                or DEFAULT_MSG["id"].get(key, key))
        try:
            return text.format(**kw)
        except Exception:
            return text

    try:
        bot.cursor.execute("CREATE TABLE IF NOT EXISTS mod_badwords (room_jid TEXT, word TEXT, PRIMARY KEY (room_jid, word))")
        bot.cursor.execute("CREATE TABLE IF NOT EXISTS mod_badnicks (room_jid TEXT, pattern TEXT, PRIMARY KEY (room_jid, pattern))")
        bot.conn.commit()
    except Exception as e:
        debug(f"Gagal membuat tabel moderasi: {e}")

    # ---------- normalisasi teks (leet-speak, aksen, huruf berulang) ----------
    _LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s",
                           "ß": "ss", "ı": "i", "ł": "l", "ø": "o", "đ": "d", "æ": "ae", "œ": "oe"})

    def normalize(text):
        text = unicodedata.normalize("NFKD", str(text))
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = re.sub("[\u200b-\u200f\u2060\ufeff]", "", text)
        return text.lower().translate(_LEET)

    def collapse(s):
        return re.sub(r"(.)\1+", r"\1", s)

    def tokenize(text):
        """Pecah jadi token huruf; huruf yang dipisah spasi (a n j i n g) digabung."""
        toks = re.findall(r"[^\W\d_]+", normalize(text))
        out, run = [], []

        def flush():
            if len(run) >= 3:
                out.append("".join(run))
            else:
                out.extend(run)
            run.clear()

        for t in toks:
            if len(t) == 1:
                run.append(t)
            else:
                flush()
                out.append(t)
        flush()
        return out

    def compile_word(w):
        sub = w.startswith("*") or w.endswith("*")
        core = collapse(re.sub(r"[\W\d_]", "", normalize(w.strip("*"))))
        return (w, core, sub) if core else None

    def load_global_words():
        words = []
        try:
            if os.path.exists(GLOBAL_WORDS_FILE):
                with open(GLOBAL_WORDS_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip().lower()
                        if line and not line.startswith("#"):
                            words.append(line)
        except Exception as e:
            debug(f"Gagal membaca {GLOBAL_WORDS_FILE}: {e}")
        return words

    _global_words = load_global_words()
    _word_cache = {}     # room -> [(kata, inti, sebagian?)]
    _nick_cache = {}     # room -> [pola]
    _word_strikes = {}   # (room, kunci user) -> [timestamp]
    _nick_acted = {}     # (room, nick) -> timestamp tindakan terakhir

    def defaults_on(kind):
        return bot.get_setting(f"mod_defaults_{kind}", "1") != "0"

    def db_rows(table, col, key):
        try:
            bot.cursor.execute(f"SELECT {col} FROM {table} WHERE room_jid = ?", (key,))
            return [r[0] for r in bot.cursor.fetchall()]
        except Exception:
            return []

    def get_word_entries(room):
        """Gabungan: bawaan script + file global + DB global + DB room. room='*' = hanya global."""
        key = room.lower()
        if key not in _word_cache:
            words = set(_global_words) | set(db_rows("mod_badwords", "word", GLOBAL_KEY))
            if defaults_on("word"):
                words.update(DEFAULT_BADWORDS)
            if key != GLOBAL_KEY:
                words.update(db_rows("mod_badwords", "word", key))
            _word_cache[key] = [e for e in (compile_word(w) for w in words) if e]
        return _word_cache[key]

    def get_nick_patterns(room):
        key = room.lower()
        if key not in _nick_cache:
            pats = list(db_rows("mod_badnicks", "pattern", GLOBAL_KEY))
            if defaults_on("nick"):
                pats = list(DEFAULT_BADNICKS) + pats
            if key != GLOBAL_KEY:
                pats += db_rows("mod_badnicks", "pattern", key)
            _nick_cache[key] = list(dict.fromkeys(pats))
        return _nick_cache[key]

    def filter_on(name, room):
        """Filter aktif bila saklar global DAN saklar room sama-sama menyala."""
        return (bot.get_setting(f"{name}_global", "1") != "0"
                and bot.get_setting(f"{name}_{room.lower()}", "1") != "0")

    def find_badword(room, text):
        entries = get_word_entries(room)
        if not entries:
            return None
        ctoks = [collapse(t) for t in tokenize(text)]
        for orig, core, sub in entries:
            for ct in ctoks:
                if (sub and core in ct) or (not sub and ct == core):
                    return orig
        return None

    def check_nick(room, nick):
        nick = nick[:64]
        low = nick.lower()
        norm = normalize(nick)
        compact = collapse(re.sub(r"[\W\d_]", "", norm))
        for pat in get_nick_patterns(room):
            if pat.startswith("re:"):
                try:
                    if re.search(pat[3:], nick, re.IGNORECASE) or re.search(pat[3:], norm, re.IGNORECASE):
                        return pat
                except re.error:
                    continue
            else:
                p_low = pat.lower()
                p_cmp = collapse(re.sub(r"[\W\d_]", "", normalize(pat)))
                if p_low in low or (p_cmp and p_cmp in compact):
                    return pat
        return find_badword(room, nick)

    def is_exempt(room, nick):
        """Owner/admin/moderator room dan owner bot tidak terkena filter."""
        info = bot.room_users.get(room, {}).get(nick) or {}
        if info.get("affiliation") in ("owner", "admin") or info.get("role") == "moderator":
            return True
        jid = info.get("jid")
        if jid:
            try:
                owners = {str(o).lower() for o in bot.get_owners()}
                if str(jid).split("/")[0].lower() in owners:
                    return True
            except Exception:
                pass
        return False

    async def kick_occupant(room, nick, reason):
        try:
            if hasattr(bot, "plugin") and "xep_0045" in bot.plugin:
                res = bot.plugin["xep_0045"].set_role(room=room, nick=nick, role="none", reason=reason)
                if inspect.isawaitable(res):
                    await res
                return True
        except Exception as e:
            debug(f"Gagal kick {nick} di {room}: {e}")
        return False

    # ---------- handler: kata terlarang di pesan ----------
    async def handle_content_filter(msg):
        try:
            if is_history_message(msg):
                return
            from_str = str(msg.get("from", ""))
            if "/" not in from_str:
                return
            room, nick = from_str.split("/", 1)
            body = msg.get("body", "")
            if not nick or not body or not filter_on("mod_words", room):
                return
            if nick.lower() == (bot.get_room_nick(room) or "").lower():
                return
            if not find_badword(room, body):
                return
            if is_exempt(room, nick):
                return

            now = time.time()
            info = bot.room_users.get(room, {}).get(nick) or {}
            key = (room.lower(), str(info.get("jid") or nick).split("/")[0].lower())
            hist = [t for t in _word_strikes.get(key, []) if now - t <= WORD_STRIKE_WINDOW]
            hist.append(now)
            lang = get_lang(from_str, room)

            if len(hist) > WORD_WARN_LIMIT:
                _word_strikes.pop(key, None)
                await bot.reply_user(from_str, room, T(lang, "bw_kick_notice", nick=nick), False)
                await kick_occupant(room, nick, T(lang, "bw_kick_reason"))
            else:
                _word_strikes[key] = hist
                await bot.reply_user(from_str, room, T(lang, "bw_warn", n=len(hist), limit=WORD_WARN_LIMIT),
                                     False, nick=nick)
            if len(_word_strikes) > 2000:
                for k in [k for k, v in _word_strikes.items() if not v or now - v[-1] > WORD_STRIKE_WINDOW]:
                    _word_strikes.pop(k, None)
        except Exception as e:
            debug(f"Error filter kata terlarang: {e}")

    # ---------- handler: nickname terlarang saat join / ganti nick ----------
    async def handle_nick_filter(presence):
        try:
            if presence["type"] in ("unavailable", "error"):
                return
            room = presence["from"].bare
            nick = presence["from"].resource
            if not room or not nick or not filter_on("mod_nicks", room):
                return
            if nick.lower() == (bot.get_room_nick(room) or "").lower():
                return

            affiliation, role, real_jid = "", "", None
            ux = presence.xml.find("{http://jabber.org/protocol/muc#user}x")
            if ux is not None:
                for st in ux.findall("{http://jabber.org/protocol/muc#user}status"):
                    if st.attrib.get("code") == "110":
                        return   # presence milik bot sendiri
                item = ux.find("{http://jabber.org/protocol/muc#user}item")
                if item is not None:
                    affiliation = item.attrib.get("affiliation", "")
                    role = item.attrib.get("role", "")
                    real_jid = item.attrib.get("jid")
            if affiliation in ("owner", "admin") or role == "moderator":
                return
            if real_jid:
                try:
                    owners = {str(o).lower() for o in bot.get_owners()}
                    if str(real_jid).split("/")[0].lower() in owners:
                        return
                except Exception:
                    pass

            if not check_nick(room, nick):
                return
            now = time.time()
            k = (room.lower(), nick)
            if now - _nick_acted.get(k, 0) < NICK_ACTION_COOLDOWN:
                return
            _nick_acted[k] = now
            if len(_nick_acted) > 2000:
                for kk in [kk for kk, t in _nick_acted.items() if now - t > 3600]:
                    _nick_acted.pop(kk, None)

            lang = get_lang(str(presence["from"]), room)
            if await kick_occupant(room, nick, T(lang, "bn_kick_reason")):
                await bot.reply_user(str(presence["from"]), room, T(lang, "bn_kick_notice", nick=nick), False)
        except Exception as e:
            debug(f"Error filter nickname: {e}")

    # ---------- pengelola daftar (dipakai perintah per-room DAN global) ----------
    KINDS = {
        "word": {"table": "mod_badwords", "col": "word", "usage": "usage_bw", "what": "what_words",
                 "setting": "mod_words", "cache": _word_cache, "defaults": DEFAULT_BADWORDS},
        "nick": {"table": "mod_badnicks", "col": "pattern", "usage": "usage_bn", "what": "what_nicks",
                 "setting": "mod_nicks", "cache": _nick_cache, "defaults": DEFAULT_BADNICKS},
    }

    def validate_entry(kind, raw):
        if kind == "word":
            w = raw.lower().strip()
            if not re.fullmatch(r"\*?(?:[^\W_]|[@$]){2,40}\*?", w) or not compile_word(w):
                return None
            return w
        pat = raw.strip()
        if not 2 <= len(pat) <= 80:
            return None
        if pat.lower().startswith("re:"):
            pat = "re:" + pat[3:]
            try:
                re.compile(pat[3:])
            except re.error:
                return None
        return pat

    def invalidate(kind, key):
        cache = KINDS[kind]["cache"]
        if key == GLOBAL_KEY:
            cache.clear()
        else:
            cache.pop(key, None)

    def effective_count(kind, key):
        return len(get_word_entries(key)) if kind == "word" else len(get_nick_patterns(key))

    async def manage(kind, key, args, lang, say):
        cfg = KINDS[kind]
        table, col = cfg["table"], cfg["col"]
        is_global = key == GLOBAL_KEY
        what = T(lang, cfg["what"]) + (" " + T(lang, "scope_global") if is_global else "")
        setting = f"{cfg['setting']}_{'global' if is_global else key}"
        sub = args[0].lower() if args else ""

        if sub in ("add", "tambah"):
            count = len(db_rows(table, col, key))
            added, bad = [], []
            for raw in args[1:]:
                val = validate_entry(kind, raw)
                if val is None:
                    bad.append(raw)
                    continue
                if count + len(added) >= MAX_ENTRIES_PER_ROOM:
                    await say(T(lang, "limit", max=MAX_ENTRIES_PER_ROOM))
                    break
                bot.cursor.execute(f"INSERT OR IGNORE INTO {table} (room_jid, {col}) VALUES (?, ?)", (key, val))
                added.append(val)
            bot.conn.commit()
            invalidate(kind, key)
            if added:
                await say(T(lang, "added", items=", ".join(added)))
            if bad:
                await say(T(lang, "invalid", items=", ".join(bad)))
            if not added and not bad:
                await say(T(lang, cfg["usage"]))

        elif sub in ("del", "hapus", "remove"):
            gone, missing = [], []
            for raw in args[1:]:
                val = raw.strip() if kind == "nick" else raw.lower().strip()
                bot.cursor.execute(f"DELETE FROM {table} WHERE room_jid = ? AND {col} = ?", (key, val))
                (gone if bot.cursor.rowcount else missing).append(val)
            bot.conn.commit()
            invalidate(kind, key)
            if gone:
                await say(T(lang, "removed", items=", ".join(gone)))
            if missing:
                await say(T(lang, "not_found", items=", ".join(missing)))
            if not gone and not missing:
                await say(T(lang, cfg["usage"]))

        elif sub in ("list", "daftar"):
            rows = sorted(db_rows(table, col, key))
            if kind == "word" and is_global:
                rows += [f"{w} (file)" for w in _global_words]
            await say(T(lang, "list_title", count=len(rows), items=", ".join(rows)) if rows else T(lang, "empty"))
            if is_global:
                state = T(lang, "on" if defaults_on(kind) else "off")
                await say(T(lang, "defaults_info", n=len(cfg["defaults"]), state=state))
            else:
                n_global = effective_count(kind, GLOBAL_KEY)
                if n_global:
                    await say(T(lang, "global_info", n=n_global))

        elif sub in ("on", "off"):
            bot.set_setting(setting, "1" if sub == "on" else "0")
            await say(T(lang, "state_on" if sub == "on" else "state_off", what=what))

        elif sub == "defaults" and is_global and len(args) > 1 and args[1].lower() in ("on", "off"):
            bot.set_setting(f"mod_defaults_{kind}", "1" if args[1].lower() == "on" else "0")
            _word_cache.clear()
            _nick_cache.clear()
            state = T(lang, "on" if args[1].lower() == "on" else "off")
            await say(T(lang, "defaults_set", what=T(lang, cfg["what"]), state=state))

        elif sub == "reload" and is_global and kind == "word":
            _global_words[:] = load_global_words()
            _word_cache.clear()
            await say(T(lang, "reloaded", count=len(_global_words)))

        else:
            on = bot.get_setting(setting, "1") != "0"
            await say(T(lang, "state_info", what=what, state=T(lang, "on" if on else "off"),
                        count=effective_count(kind, key)))
            await say(T(lang, cfg["usage"]))

    async def is_staff(sender, room, nick):
        if is_exempt(room, nick):
            return True
        try:
            return bool(await bot.verify_real_owner_from_server(room, nick, sender))
        except Exception:
            return False

    async def is_bot_owner(sender, room, nick):
        try:
            return bool(await bot.verify_real_owner_from_server(room, nick, sender))
        except Exception:
            return False

    def make_room_cmd(kind):
        async def run(sender, room, nick, is_private, args):
            lang = get_lang(sender, room)

            async def say(text):
                await bot.reply_user(sender, room, text, is_private, nick=nick)

            if not room:
                return await say(T(lang, "room_only"))
            if not await is_staff(sender, room, nick):
                return await say(T(lang, "mod_only"))
            await manage(kind, room.lower(), args, lang, say)
        return run

    def make_global_cmd(kind):
        async def run(sender, room, nick, is_private, args):
            lang = get_lang(sender, room)

            async def say(text):
                await bot.reply_user(sender, room, text, is_private, nick=nick)

            if not await is_bot_owner(sender, room, nick):
                return await say(T(lang, "owner_only"))
            await manage(kind, GLOBAL_KEY, args, lang, say)
        return run

    # ---------- perintah per-room (owner/admin/moderator room) ----------
    _c = bot.command("badword", "💎 Admin & Owner Group")
    _f = make_room_cmd("word"); _f.__doc__ = "badword add|del|list|on|off [word]"; _c(_f)
    _c = bot.command("badnick", "💎 Admin & Owner Group")
    _f = make_room_cmd("nick"); _f.__doc__ = "badnick add|del|list|on|off [pattern]"; _c(_f)

    # ---------- perintah GLOBAL (khusus owner bot; berlaku di semua room) ----------
    _c = bot.command("gbadword", "👑 Bot Owner")
    _f = make_global_cmd("word"); _f.__doc__ = "gbadword add|del|list|on|off|defaults|reload [word]"; _c(_f)
    _c = bot.command("gbadnick", "👑 Bot Owner")
    _f = make_global_cmd("nick"); _f.__doc__ = "gbadnick add|del|list|on|off|defaults [pattern]"; _c(_f)

    bot.add_event_handler("groupchat_message", handle_anti_flood)
    bot.add_event_handler("groupchat_message", handle_content_filter)
    bot.add_event_handler("groupchat_presence", handle_nick_filter)

    @bot.command("antiflood", "👤 Participant & Member")
    async def cmd_antiflood_info(sender, room, nick, is_private, args):
        """antiflood"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        info_text = T(lang, "info_text",
            max_msg=MAX_USER_MESSAGES,
            time_user=TIME_WINDOW_USER,
            burst_limit=BURST_LIMIT_ROOM,
            time_burst=TIME_WINDOW_BURST
        )
        await bot.reply_user(sender, room, info_text, is_private, nick=nick)
