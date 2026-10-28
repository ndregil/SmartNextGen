# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot (Hardened & Bulletproof Edition)
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org

import asyncio
import inspect
import logging
import os
import sqlite3
import sys
import time
import platform
import importlib
import pkgutil
import json
import random
import re
import string
import slixmpp
from slixmpp.exceptions import IqError, IqTimeout

ACTIVE_BOT_INSTANCES = {}

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("AFC").setLevel(logging.WARNING)
logging.getLogger("plist").setLevel(logging.WARNING)
logging.getLogger("google.generativeai").setLevel(logging.ERROR)
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("slixmpp").setLevel(logging.WARNING)


class _RedactSecrets(logging.Filter):
    """Samarkan data login (SASL) pada log debug agar password tidak ikut tercetak."""
    _pattern = re.compile(r"(<(?:auth|response)\b[^>]*>)[^<]+(</(?:auth|response)>)", re.I)

    def filter(self, record):
        try:
            msg = record.getMessage()
            record.msg = self._pattern.sub(r"\1***\2", msg)
            record.args = ()
        except Exception:
            pass
        return True


def enable_xmpp_debug():
    for h in logging.getLogger().handlers:
        h.addFilter(_RedactSecrets())
    logging.getLogger("slixmpp").setLevel(logging.DEBUG)

_plugins_loaded = False
_main_langs = {}
UI_LANG = "id"  # bahasa pesan sistem (diisi dari DEFAULT_LANG di config.txt)
USE_IPV6 = False  # config.txt: USE_IPV6=on bila jaringan mendukung IPv6
ENABLE_SM = True  # bisa dimatikan lewat config.txt: STREAM_MANAGEMENT=off


def now():
    return time.strftime("%H:%M:%S")

# Pengaturan stabilitas koneksi
KEEPALIVE_INTERVAL = 60      # detik antar ping ke server
KEEPALIVE_TIMEOUT = 30       # detik menunggu balasan ping
KEEPALIVE_MAX_FAILS = 3      # reconnect hanya setelah N ping gagal berturut-turut
SESSION_START_TIMEOUT = 60   # batas waktu negosiasi login setelah koneksi TCP terbentuk
STALL_TIMEOUT = 90           # bila tidak ada koneksi/sesi selama N detik, supervisor memaksa reconnect (beri waktu slixmpp pulih sendiri)
STABLE_UPTIME = 120          # koneksi dianggap stabil bila hidup >= N detik (reset backoff)
AUTH_FAIL_DELAY = 120        # jeda bila autentikasi gagal (hindari ban akibat spam login)
LOOP_LAG_WARN = 3.0          # peringatan jika event loop macet > N detik (plugin memblokir)
JOIN_TIMEOUT = 30            # detik menunggu konfirmasi join room dari server MUC (bawaan slixmpp hanya 5)
JOIN_RETRIES = 1             # ulangi join sekali bila server MUC lambat membalas
# Kondisi error MUC yang tidak akan berubah dengan mengulang (room dilewati sampai bot restart)
PERMANENT_JOIN_ERRORS = ("registration-required", "forbidden", "not-allowed")

# Kata kunci untuk emoji otomatis di reply_user (semua bahasa yang didukung; huruf kecil, pencocokan sebagian)
_EMOJI_FAIL = ("akses ditolak", "gagal", "access denied", "failed", "refused", "denied",
    "доступ запрещ", "ошибк", "не удалось", "zugriff verweigert", "fehlgeschlagen", "accès refusé", "échec", "échoué", "refusé",
    "رفض", "فشل", "अस्वीकृत", "विफल", "असफल", "拒绝", "失败", "acceso denegado", "falló", "acesso negado", "falha",
    "odmowa dostępu", "błąd", "nie udało", "accesso negato", "fallito", "دسترسی ممنوع", "ناموفق", "erişim reddedildi",
    "başarısız", "доступ заборонено", "помилка", "не вдалося")
_EMOJI_OK = ("berhasil", "sukses", "successfully", "success", "успешно", "успішно", "erfolgreich", "succès", "réussi",
    "بنجاح", "सफलतापूर्वक", "成功", "con éxito", "correctamente", "com sucesso", "pomyślnie", "con successo",
    "با موفقیت", "başarıyla")
_EMOJI_RESTART = ("mematikan", "merestart", "shutdown", "restart", "перезапуск", "выключ", "neustart", "herunterfahren",
    "redémarr", "éteindre", "إعادة تشغيل", "إيقاف", "पुनरारंभ", "重启", "关闭", "reinici", "desligando", "wyłącz",
    "riavvi", "spegn", "راه‌اندازی مجدد", "خاموش", "yeniden başlat", "kapat", "вимика")
_EMOJI_HELP = ("bantuan", "daftar perintah", "guide", "list", "справка", "помощь", "список команд", "hilfe", "befehlsliste",
    "aide", "liste des commandes", "مساعدة", "قائمة الأوامر", "मदद", "सहायता", "帮助", "命令列表", "ayuda",
    "lista de comandos", "ajuda", "pomoc", "lista poleceń", "aiuto", "elenco comandi", "راهنما", "فهرست دستورها",
    "yardım", "komut listesi", "допомога")



def tr(key, lang=None, **kwargs):
    """Terjemahan pesan sistem (untuk kode di luar class). Urutan fallback: bahasa -> id -> en -> nama key."""
    lang = (lang or UI_LANG or "id").lower()
    text = None
    for code in (lang, "id", "en"):
        text = _main_langs.get(code, {}).get(key)
        if text:
            break
    if not text:
        text = key
    try:
        return text.format(**kwargs)
    except Exception:
        return text


def _msg(key, default, **kwargs):
    """Seperti tr(), tetapi memakai teks default bila key belum ada di lang/main/*.json."""
    for code in ((UI_LANG or "id").lower(), "id", "en"):
        text = _main_langs.get(code, {}).get(key)
        if text:
            break
    else:
        text = default
    try:
        return text.format(**kwargs)
    except Exception:
        return text


def _retrieve_task_result(task, label=""):
    """Ambil exception dari task latar belakang agar tidak muncul 'Task exception was never retrieved'."""
    try:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            logging.warning(f"[{now()}] " + tr("muc_join_timeout", label=label))
        else:
            logging.warning(f"[{now()}] " + tr("muc_join_error", label=label, error=repr(exc)))
    except Exception:
        pass


def _loop_exception_handler(loop, context):
    """Redam timeout join_muc_wait milik slixmpp (tidak fatal); error lain tetap dilaporkan."""
    exc = context.get("exception")
    fut = context.get("future")
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) and "join_muc_wait" in repr(fut):
        logging.warning(f"[{now()}] " + tr("muc_join_timeout_ignored"))
        return
    loop.default_exception_handler(context)


def load_main_languages():
    global _main_langs
    main_lang_dir = os.path.join("lang", "main")
    if os.path.exists(main_lang_dir):
        for file_name in os.listdir(main_lang_dir):
            if file_name.endswith(".json"):
                lang_code = file_name[:-5].lower()
                file_path = os.path.join(main_lang_dir, file_name)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        _main_langs[lang_code] = json.load(f)
                except Exception as e:
                    logging.error(f"Gagal memuat kamus bahasa utama {file_name}: {e}")

load_main_languages()


def load_config(filename="config.txt"):
    config = {}
    if not os.path.exists(filename):
        err_msg = _main_langs.get("id", {}).get("config_not_found", "Configuration file '{filename}' not found!").format(filename=filename)
        logging.error(err_msg)
        sys.exit(1)

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


def generate_dynamic_resource(base_resource="SmartBot", length=5):
    if not base_resource:
        base_resource = "SmartBot"
    letters = string.ascii_letters + string.digits
    rand_str = "".join(random.choice(letters) for _ in range(length))
    return f"{base_resource}.{rand_str}"


def get_account_credentials(config, prefix=""):
    raw_jid = config.get(f"JID{prefix}", "").strip()
    base_resource = config.get("RESOURCE", "").strip() or "SmartNextGen"
    dynamic_resource = generate_dynamic_resource(base_resource, length=5)

    if raw_jid:
        clean_bare_jid = raw_jid.split("/")[0]
        jid = f"{clean_bare_jid}/{dynamic_resource}"
    else:
        jid = ""

    password = config.get(f"PASSWORD{prefix}", "").strip()
    default_nick = config.get(f"DEFAULT_NICK{prefix}", "").strip()
    return jid, password, default_nick


class ModernMultiMucBot(slixmpp.ClientXMPP):

    def __init__(self, jid, password, default_rooms, default_owners, gemini_api_key, groq_api_key, openrouter_api_key, mistral_api_key, weather_api_key, default_nick="", default_status="", default_lang="id", should_join_rooms=True, is_primary_jid=True, show_plugin_logs=False):
        super().__init__(jid, password)

        # Reconnect dikerjakan oleh slixmpp sendiri (satu-satunya "pengemudi" koneksi).
        # run_bot_instance hanya memantau dan memaksa reconnect bila macet. Dua jalur reconnect
        # yang berjalan bersamaan membuat resource yang sama login ganda sehingga server
        # menutup koneksi ("End of stream") berulang-ulang.
        self.auto_reconnect = True
        self.session_active = False
        self.last_down_at = time.monotonic()
        self.auth_failed_at = None
        self.manual_stop = False  # True bila dimatikan lewat perintah shutdown; supervisor tidak boleh menyambungkan ulang

        self.default_rooms = default_rooms
        self.default_owners = default_owners
        self.global_default_nick = default_nick
        self.global_default_lang = default_lang
        self.gemini_api_key = gemini_api_key
        self.groq_api_key = groq_api_key
        self.openrouter_api_key = openrouter_api_key
        self.mistral_api_key = mistral_api_key
        self.weather_api_key = weather_api_key
        self.should_join_rooms = should_join_rooms
        self.is_primary_jid = is_primary_jid
        self.show_plugin_logs = show_plugin_logs
        self.room_last_disco = {}
        self.auto_subscribe = True

        self._keepalive_task = None
        self._session_started_at = None
        self._join_tasks = set()
        self.joined_rooms = set()    # room yang kehadiran bot-nya sudah terkonfirmasi lewat presence
        self.rejected_rooms = set()  # room yang ditolak permanen (members-only/banned) agar tidak dicoba terus

        self.COMMAND_REGISTRY = {}
        self.COMMAND_LOOKUP = {}
        self.room_users = {}

        db_name = f"botsettings_{str(jid).split('/')[0].replace('@', '_').replace('.', '_')}.db"
        self.init_db(db_name)

        self.user_languages = {}
        self.load_languages_from_db()

        self.bot_status = self.get_setting("bot_status", default_status)

        self.register_plugin("xep_0030")
        self.register_plugin("xep_0045")
        # Keepalive bawaan xep_0199 dimatikan; diganti keep_alive_ping() milik bot yang lebih toleran.
        self.register_plugin("xep_0199", {"keepalive": False})
        self.register_plugin("xep_0092")
        self.register_plugin("xep_0115")
        self.register_plugin('xep_0363')

        try:
            if hasattr(self.plugin["xep_0199"], "disable_keepalive"):
                self.plugin["xep_0199"].disable_keepalive()
        except Exception:
            pass

        # Stream Management (XEP-0198): sesi bisa dilanjutkan setelah putus singkat
        # tanpa login ulang & tanpa join ulang semua room. Aman diabaikan bila server tidak mendukung.
        if ENABLE_SM:
            try:
                self.register_plugin("xep_0198")
            except Exception as e:
                logging.warning(tr("sm_disabled", default_lang, error=e))

        SmartBotName = "Smart Next-Gen XMPP Bot"
        SmartBotVer = "1.0.6 Bulletproof Edition (Multi lang+aiprovider) (antiflood+imgfilter)"
        Caps = " "

        psystem  = platform.system()
        prelease = platform.release()
        pmechine = platform.machine()
        ppyim = platform.python_implementation()
        ppyv = platform.python_version()
        ppyb = platform.python_build()[0]
        ppyu = platform.uname().version
        psql = sqlite3.sqlite_version
        possys = "%s (%s %s) [Build %s %s] | (SQL: %s)" % (pmechine, ppyim, ppyv, ppyb, ppyu, psql)

        xep92 = self.plugin["xep_0092"]
        xep15 = self.plugin["xep_0115"]

        if hasattr(xep92, "name"):
            xep92.name    = SmartBotName
            xep92.version = SmartBotVer
            xep92.os      = possys

        cfg = getattr(xep92, "config", None) or {}
        cfg.update({
            "software_name": SmartBotName,
            "version":       SmartBotVer,
            "os":            possys,
        })

        capss = getattr(xep15, "config", None) or {}
        capss.update({
            "caps_node": Caps,
        })

        for attr, val in (
            ("software_name", SmartBotName),
            ("version",       SmartBotVer),
            ("os",            possys),
        ):
            if hasattr(xep92, attr):
                setattr(xep92, attr, val)

        self.load_plugins()

        self.add_event_handler("session_start", self.start)
        self.add_event_handler("session_resumed", self.on_session_resumed)
        self.add_event_handler("groupchat_presence", self.muc_presence)
        self.add_event_handler("disconnected", self.on_disconnect)
        self.add_event_handler("failed_auth", self.on_failed_auth)
        self.add_event_handler("stream_error", self.on_stream_error)
        self.add_event_handler("connection_failed", self.on_connection_failed)
        self.add_event_handler("connected", self.on_connected)

    def get_text(self, key, lang_code=None, **kwargs):
        if not lang_code:
            lang_code = self.global_default_lang
        lang_code = lang_code.lower()
        if lang_code not in _main_langs:
            lang_code = "id"
        text_template = (_main_langs.get(lang_code, {}).get(key)
                         or _main_langs.get("id", {}).get(key)
                         or _main_langs.get("en", {}).get(key)
                         or key)
        try:
            return text_template.format(**kwargs)
        except Exception:
            return text_template

    def load_plugin_messages(self, plugin_name):
        lang_messages = {}
        plugin_lang_dir = os.path.join("lang", plugin_name)
        if os.path.exists(plugin_lang_dir):
            for file_name in os.listdir(plugin_lang_dir):
                if file_name.endswith(".json"):
                    lang_code = file_name[:-5]
                    file_path = os.path.join(plugin_lang_dir, file_name)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            lang_messages[lang_code] = json.load(f)
                    except Exception as e:
                        logging.error(self.get_text("plugin_lang_load_failed", self.global_default_lang, file_name=file_name, plugin_name=plugin_name, error=e))
        return lang_messages

    def load_languages_from_db(self):
        try:
            self.cursor.execute("SELECT key, value FROM settings WHERE key LIKE 'lang_%'")
            for k, v in self.cursor.fetchall():
                target = k[5:].lower()
                if target:
                    self.user_languages[target] = v
        except Exception as e:
            err_msg = self.get_text("db_load_failed", self.global_default_lang, error=e)
            logging.error(err_msg)

    def get_lang(self, sender, room):
        key = room.lower() if room else str(sender).lower()
        if key in self.user_languages:
            return self.user_languages[key]

        saved_lang = self.get_setting(f"lang_{key}")
        if saved_lang:
            self.user_languages[key] = saved_lang
            return saved_lang

        return self.global_default_lang

    def set_lang(self, sender, room, lang_code):
        key = room.lower() if room else str(sender).lower()
        self.user_languages[key] = lang_code
        self.set_setting(f"lang_{key}", lang_code)

    def get_bot_version_info(self):
        xep92 = self.plugin["xep_0092"] if "xep_0092" in self.plugin else None
        name = getattr(xep92, "name", "[None]")
        ver = getattr(xep92, "version", "[None]")
        os_str = getattr(xep92, "os", "[None]")
        return name, ver, os_str

    def load_plugins(self):
        global _plugins_loaded
        plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")

        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        CYAN = "\033[96m"
        RESET = "\033[0m"

        if not os.path.exists(plugins_dir):
            os.makedirs(plugins_dir)
            if self.show_plugin_logs and not _plugins_loaded:
                msg = self.get_text("plugin_folder_created", self.global_default_lang)
                print(f"{YELLOW}WARNING ❗ {RESET}{msg}")
            return

        for _, modname, _ in pkgutil.iter_modules([plugins_dir]):
            if modname.startswith("__"):
                continue
            try:
                module = importlib.import_module(f"plugins.{modname}")
                if hasattr(module, "register"):
                    module.register(self)
                    if self.show_plugin_logs and not _plugins_loaded:
                        msg = self.get_text("plugin_load_success", self.global_default_lang, modname=modname)
                        print(f"{GREEN}SUCCESS ☑️ {RESET}{msg} {CYAN}{modname}{RESET}")
            except Exception as e:
                if self.show_plugin_logs and not _plugins_loaded:
                    msg = self.get_text("plugin_load_error", self.global_default_lang, modname=modname, error=e)
                    print(f"{RED}ERROR  ❌  {RESET}{msg}")

        if self.show_plugin_logs:
            _plugins_loaded = True

    def command(self, name, category, aliases=None):
        if aliases is None:
            aliases = []

        def decorator(func):
            func.is_command = True
            func.cmd_name = name
            func.cmd_aliases = aliases
            func.category = category
            doc = func.__doc__
            func.description = doc.strip().split("\n")[0] if doc else ""

            if category not in self.COMMAND_REGISTRY:
                self.COMMAND_REGISTRY[category] = []

            syntax_info = f"{name}" + (f" / {' / '.join(aliases)}" if aliases else "")
            self.COMMAND_REGISTRY[category].append((syntax_info, func.description))

            self.COMMAND_LOOKUP[name] = func
            for alias in aliases:
                self.COMMAND_LOOKUP[alias] = func

            return func
        return decorator

    def init_db(self, db_name="botsettings.db"):
        db_dir = "data"
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        db_path = os.path.join(db_dir, db_name)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

        self.cursor.execute("CREATE TABLE IF NOT EXISTS owners (jid TEXT PRIMARY KEY)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS rooms (room_jid TEXT PRIMARY KEY)")
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS banned_list (
                room_jid TEXT,
                target TEXT,
                PRIMARY KEY (room_jid, target)
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS room_nicks (
                room_jid TEXT PRIMARY KEY,
                nick TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS room_ai_config (
                room_jid TEXT PRIMARY KEY,
                prefix TEXT DEFAULT '',
                ai_enabled INTEGER DEFAULT 1
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS room_weather_cities (
                room_jid TEXT,
                city TEXT,
                PRIMARY KEY (room_jid, city)
            )
        """)

        try:
            self.cursor.execute("ALTER TABLE room_ai_config ADD COLUMN prefix TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        try:
            self.cursor.execute("ALTER TABLE room_ai_config ADD COLUMN ai_enabled INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass

        self.conn.commit()

        for owner in self.default_owners:
            self.cursor.execute(
                "INSERT OR IGNORE INTO owners (jid) VALUES (?)",
                (owner.lower(),),
            )

        if self.is_primary_jid:
            for room in self.default_rooms:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO rooms (room_jid) VALUES (?)",
                    (room.lower(),),
                )
                self.cursor.execute(
                    "INSERT OR IGNORE INTO room_ai_config (room_jid, prefix, ai_enabled) VALUES (?, '', 1)",
                    (room.lower(),),
                )
                self.cursor.execute(
                    "INSERT OR IGNORE INTO room_weather_cities (room_jid, city) VALUES (?, ?)",
                    (room.lower(), "Jakarta")
                )

        self.conn.commit()

    def get_setting(self, key, default=""):
        self.cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        self.cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def get_room_prefix(self, room_jid):
        if not room_jid:
            return ""
        self.cursor.execute("SELECT prefix FROM room_ai_config WHERE room_jid = ?", (room_jid.lower(),))
        row = self.cursor.fetchone()
        return row[0] if row and row[0] is not None else ""

    def set_room_prefix(self, room_jid, prefix):
        self.cursor.execute(
            "INSERT OR IGNORE INTO room_ai_config (room_jid, prefix, ai_enabled) VALUES (?, '', 1)",
            (room_jid.lower(),)
        )
        self.cursor.execute(
            "UPDATE room_ai_config SET prefix = ? WHERE room_jid = ?",
            (prefix, room_jid.lower())
        )
        self.conn.commit()

    def get_room_ai_status(self, room_jid):
        if not room_jid:
            return True
        self.cursor.execute("SELECT ai_enabled FROM room_ai_config WHERE room_jid = ?", (room_jid.lower(),))
        row = self.cursor.fetchone()
        return bool(row[0]) if row and row[0] is not None else True

    def set_room_ai_status(self, room_jid, enabled: bool):
        self.cursor.execute(
            "INSERT OR IGNORE INTO room_ai_config (room_jid, prefix, ai_enabled) VALUES (?, '', 1)",
            (room_jid.lower(),)
        )
        self.cursor.execute(
            "UPDATE room_ai_config SET ai_enabled = ? WHERE room_jid = ?",
            (1 if enabled else 0, room_jid.lower())
        )
        self.conn.commit()

    def get_room_nick(self, room_jid):
        if not room_jid:
            return self.global_default_nick
        self.cursor.execute(
            "SELECT nick FROM room_nicks WHERE room_jid = ?", (room_jid.lower(),)
        )
        row = self.cursor.fetchone()
        return row[0] if row else self.global_default_nick

    def set_room_nick(self, room_jid, nick):
        self.cursor.execute(
            "INSERT OR REPLACE INTO room_nicks (room_jid, nick) VALUES (?, ?)",
            (room_jid.lower(), nick),
        )
        self.conn.commit()

    def get_room_cities(self, room_jid):
        self.cursor.execute("SELECT city FROM room_weather_cities WHERE room_jid = ?", (room_jid.lower(),))
        return [row[0] for row in self.cursor.fetchall()]

    def add_room_city(self, room_jid, city):
        self.cursor.execute(
            "INSERT OR IGNORE INTO room_weather_cities (room_jid, city) VALUES (?, ?)",
            (room_jid.lower(), city.title())
        )
        self.conn.commit()

    def remove_room_city(self, room_jid, city):
        self.cursor.execute(
            "DELETE FROM room_weather_cities WHERE room_jid = ? AND city COLLATE NOCASE = ?",
            (room_jid.lower(), city)
        )
        self.conn.commit()

    def add_owner_to_db(self, jid):
        self.cursor.execute(
            "INSERT OR IGNORE INTO owners (jid) VALUES (?)", (jid.lower(),)
        )
        self.conn.commit()

    def remove_owner_from_db(self, jid):
        self.cursor.execute("DELETE FROM owners WHERE jid = ?", (jid.lower(),))
        self.conn.commit()

    def get_owners(self):
        self.cursor.execute("SELECT jid FROM owners")
        return {row[0] for row in self.cursor.fetchall()}

    async def verify_real_owner_from_server(self, room, nick, sender_jid):
        owners = {o.lower() for o in self.get_owners()}
        if sender_jid:
            s_str = str(sender_jid).split("/")[0].lower()
            if s_str in owners:
                return True

        if room and nick:
            try:
                room_info = await self.plugin["xep_0045"].get_roster(room)
                if nick in room_info:
                    server_real_jid = room_info[nick].get("jid")
                    if server_real_jid:
                        clean_server_jid = str(server_real_jid).split("/")[0].lower()
                        if clean_server_jid in owners:
                            return True
            except Exception:
                pass

            if room in self.room_users and nick in self.room_users[room]:
                stored_jid = self.room_users[room][nick].get("jid")
                if stored_jid:
                    clean_stored = str(stored_jid).split("/")[0].lower()
                    if clean_stored in owners:
                        return True

        return False

    def get_rooms(self):
        self.cursor.execute("SELECT room_jid FROM rooms")
        return {row[0] for row in self.cursor.fetchall()}

    def add_room_to_db(self, room):
        self.cursor.execute(
            "INSERT OR IGNORE INTO rooms (room_jid) VALUES (?)", (room.lower(),)
        )
        self.cursor.execute(
            "INSERT OR IGNORE INTO room_ai_config (room_jid, prefix, ai_enabled) VALUES (?, '', 1)",
            (room.lower(),)
        )
        self.cursor.execute(
            "INSERT OR IGNORE INTO room_weather_cities (room_jid, city) VALUES (?, ?)",
            (room.lower(), "Jakarta")
        )
        self.conn.commit()

    def remove_room_from_db(self, room):
        self.cursor.execute("DELETE FROM rooms WHERE room_jid = ?", (room.lower(),))
        self.cursor.execute("DELETE FROM room_nicks WHERE room_jid = ?", (room.lower(),))
        self.cursor.execute("DELETE FROM room_ai_config WHERE room_jid = ?", (room.lower(),))
        self.cursor.execute("DELETE FROM room_weather_cities WHERE room_jid = ?", (room.lower(),))
        self.conn.commit()

    async def muc_presence(self, presence):
        try:
            room = presence["from"].bare
            nick = presence["from"].resource
            if not nick:
                return

            current_bot_nick = self.get_room_nick(room)
            # Presence milik bot dikenali lewat status 110 (andal) atau nick yang sama (tanpa beda huruf besar/kecil)
            _ux = presence.xml.find("{http://jabber.org/protocol/muc#user}x")
            _is_self = nick.lower() == (current_bot_nick or "").lower()
            if _ux is not None:
                for _st in _ux.findall("{http://jabber.org/protocol/muc#user}status"):
                    if _st.attrib.get("code") == "110":
                        _is_self = True
            if _is_self:
                # Presence milik bot sendiri = bukti nyata sudah masuk (atau keluar) room
                if presence["type"] in ("unavailable", "error"):
                    self.joined_rooms.discard(room.lower())
                else:
                    self.joined_rooms.add(room.lower())
                return

            if room not in self.room_users:
                self.room_users[room] = {}

            muc_x = presence.xml.find("{http://jabber.org/protocol/muc#user}x")
            if muc_x is not None:
                item = muc_x.find("{http://jabber.org/protocol/muc#user}item")
                if item is not None:
                    real_jid = item.attrib.get("jid")
                    affiliation = item.attrib.get("affiliation", "member")
                    role = item.attrib.get("role", "participant")

                    self.room_users[room][nick] = {
                        "jid": real_jid,
                        "affiliation": affiliation,
                        "role": role,
                    }
        except Exception as e:
            err_msg = self.get_text("muc_presence_error", self.global_default_lang, error=e)
            logging.error(err_msg)

    async def get_user_room_privilege(self, room, nick, sender_jid):
        if await self.verify_real_owner_from_server(room, nick, sender_jid):
            return "admin"

        if not room or not nick:
            return "member"

        room_data = self.room_users.get(room, {})
        if nick in room_data:
            user_info = room_data[nick]
            affiliation = user_info.get("affiliation", "")
            role = user_info.get("role", "")

            if affiliation in ["owner", "admin"] or role == "moderator":
                return "admin"

        if not room_data:
            return "admin"

        return "member"

    async def start(self, event):
        # Sesi baru: data user room lama sudah tidak valid, akan terisi ulang dari presence
        self.room_users = {}
        self.joined_rooms = set()
        self._session_started_at = time.monotonic()
        self.session_active = True
        self.auth_failed_at = None
        logging.info(f"[{now()}] " + self.get_text("session_started", self.global_default_lang, jid=self.boundjid.full))

        db_status = self.get_setting("bot_status", "").strip()
        current_bot_status = db_status if db_status else self.bot_status.strip()

        pshow = None
        pstatus = current_bot_status

        valid_shows = ["online", "chat", "away", "xa", "dnd"]
        parts = current_bot_status.split(" ", 1)

        if parts and parts[0].lower() in valid_shows:
            show_val = parts[0].lower()
            if show_val != "online":
                pshow = show_val
            pstatus = parts[1].strip() if len(parts) > 1 else ""

        self.send_presence(pshow=pshow, pstatus=pstatus)

        # Jangan sampai gagal ambil roster membatalkan seluruh proses join room
        try:
            await self.get_roster()
        except (IqError, IqTimeout) as e:
            logging.warning(self.get_text("roster_failed", self.global_default_lang, error=repr(e)))
        except Exception as e:
            logging.warning(self.get_text("roster_failed", self.global_default_lang, error=repr(e)))

        self._restart_keepalive()

        if not self.should_join_rooms:
            return

        saved_rooms = self.get_rooms()

        # Masuk ke room secara bertahap & aman (Staggered Delay untuk mencegah overload/disconnect)
        for room in saved_rooms:
            if not self.is_connected():
                break
            if room in self.rejected_rooms:
                continue
            try:
                bot_nick = self.get_room_nick(room)
                room_db_status = self.get_setting(f"bot_status_{room.lower()}", "").strip()

                r_pshow, r_pstatus = pshow, pstatus
                if room_db_status:
                    r_parts = room_db_status.split(" ", 1)
                    if r_parts and r_parts[0].lower() in valid_shows:
                        r_show_val = r_parts[0].lower()
                        if r_show_val != "online":
                            r_pshow = r_show_val
                        r_pstatus = r_parts[1].strip() if len(r_parts) > 1 else ""

                # Join berjalan sebagai task terpisah (timeout panjang + retry), hasilnya selalu diambil
                task = asyncio.ensure_future(self._join_one_room(room, bot_nick, r_pshow, r_pstatus))
                self._join_tasks.add(task)
                task.add_done_callback(self._join_tasks.discard)
                task.add_done_callback(lambda t, _room=room: self._on_join_done(t, _room))

                # Jeda aman per room untuk mencegah rate limit server saat load banyak room sekaligus
                await asyncio.sleep(2.0)
            except Exception as e:
                err_msg = self.get_text("join_failed", self.global_default_lang, room=room, error=e)
                logging.error(f"❌ {err_msg}")

    async def _join_muc_once(self, room, nick, pshow, pstatus):
        """Satu kali percobaan join; menunggu konfirmasi server hingga JOIN_TIMEOUT detik."""
        muc = self.plugin["xep_0045"]
        wait_fn = getattr(muc, "join_muc_wait", None)
        if wait_fn is not None and inspect.iscoroutinefunction(wait_fn):
            params = inspect.signature(wait_fn).parameters
            kw = {}
            if "maxchars" in params:
                kw["maxchars"] = 0  # jangan minta riwayat chat lama
            if "timeout" in params:
                kw["timeout"] = JOIN_TIMEOUT
            if "pshow" in params:
                kw["pshow"] = pshow
            if "pstatus" in params:
                kw["pstatus"] = pstatus
            return await asyncio.wait_for(wait_fn(room, nick, **kw), timeout=JOIN_TIMEOUT + 5)
        try:
            res = muc.join_muc(room, nick, maxhistory="0", pshow=pshow, pstatus=pstatus)
        except TypeError:
            res = muc.join_muc(room, nick, pshow=pshow, pstatus=pstatus)
        if inspect.isawaitable(res):
            return await asyncio.wait_for(res, timeout=JOIN_TIMEOUT)
        return res

    async def _join_one_room(self, room, nick, pshow, pstatus):
        last = None
        for attempt in range(JOIN_RETRIES + 1):
            try:
                return await self._join_muc_once(room, nick, pshow, pstatus)
            except (asyncio.TimeoutError, TimeoutError) as e:
                last = e
                if room.lower() in self.joined_rooms:
                    return  # sudah masuk; konfirmasi slixmpp saja yang tidak terdeteksi
                if attempt >= JOIN_RETRIES or not self.is_connected():
                    break
                await asyncio.sleep(5)
        raise last

    @staticmethod
    def _error_condition(exc):
        cond = getattr(exc, "condition", None)
        if cond:
            return str(cond)
        pres = getattr(exc, "presence", None)
        try:
            return str(pres["error"]["condition"]) if pres is not None else ""
        except Exception:
            return ""

    def _on_join_done(self, task, room):
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        RESET = "\033[0m"
        if task.cancelled():
            return
        exc = task.exception()
        who = f"{self.boundjid.bare} -> {room}"
        if exc is None:
            ok_msg = self.get_text("join_success_log", self.global_default_lang, room=room)
            print(f"{GREEN}SUCCESS ✅ {RESET}{ok_msg} {CYAN}{room}{RESET}")
            return
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            if room.lower() in self.joined_rooms:
                ok_msg = self.get_text("join_success_log", self.global_default_lang, room=room)
                print(f"{GREEN}SUCCESS ✅ {RESET}{ok_msg} {CYAN}{room}{RESET}")
                return
            logging.warning(f"[{now()}] " + _msg(
                "muc_join_timeout_soft",
                "{label}: belum ada konfirmasi join dari server MUC (timeout). Bot mungkin tetap sudah masuk; dicoba lagi saat reconnect.",
                label=who))
            return
        cond = self._error_condition(exc)
        if cond in PERMANENT_JOIN_ERRORS:
            self.rejected_rooms.add(room)
            reason = {
                "registration-required": _msg("muc_reason_registration_required", "room khusus member, akun ini belum terdaftar"),
                "forbidden": _msg("muc_reason_forbidden", "akun ini diblokir (banned) dari room"),
                "not-allowed": _msg("muc_reason_not_allowed", "tidak diizinkan masuk/membuat room"),
            }.get(cond, cond)
            logging.warning(f"[{now()}] " + _msg(
                "muc_join_rejected",
                "{label}: ditolak ({reason}). Room dilewati sampai bot di-restart.",
                label=who, reason=reason))
        else:
            logging.warning(f"[{now()}] " + _msg(
                "muc_join_error_short",
                "{label}: gagal join room ({error})",
                label=who, error=cond or type(exc).__name__))

    async def on_session_resumed(self, event):
        # Sesi dilanjutkan via Stream Management: room & presence tetap utuh, cukup hidupkan keepalive lagi
        self._session_started_at = time.monotonic()
        self.session_active = True
        self._restart_keepalive()
        logging.info(self.get_text("session_resumed", self.global_default_lang))

    # ------------------------------------------------------------------
    # Keepalive: SATU task per koneksi, toleran terhadap ping yang sesekali lambat
    # ------------------------------------------------------------------
    def _restart_keepalive(self):
        if self._keepalive_task is not None and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        self._keepalive_task = asyncio.ensure_future(self.keep_alive_ping())

    def _stop_keepalive(self):
        if self._keepalive_task is not None and not self._keepalive_task.done():
            self._keepalive_task.cancel()
        self._keepalive_task = None

    async def keep_alive_ping(self):
        fails = 0
        try:
            while self.is_connected():
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if not self.is_connected():
                    break
                try:
                    await self.plugin["xep_0199"].ping(self.boundjid.domain, timeout=KEEPALIVE_TIMEOUT)
                    fails = 0
                except IqTimeout:
                    fails += 1
                    logging.warning(self.get_text("ping_no_reply", self.global_default_lang, fails=fails, max_fails=KEEPALIVE_MAX_FAILS, jid=self.boundjid.bare))
                    if fails >= KEEPALIVE_MAX_FAILS:
                        logging.warning(self.get_text("connection_dead", self.global_default_lang, jid=self.boundjid.bare))
                        try:
                            self.abort()
                        except Exception:
                            try:
                                self.disconnect()
                            except Exception:
                                pass
                        break
                except IqError:
                    # Server menjawab (walau error, mis. ping tidak didukung) = koneksi masih hidup
                    fails = 0
                except Exception as e:
                    logging.debug(f"Keepalive error: {e!r}")
        except asyncio.CancelledError:
            pass

    async def on_disconnect(self, event):
        self.session_active = False
        self.last_down_at = time.monotonic()
        self._stop_keepalive()
        self.joined_rooms.clear()
        for jt in list(self._join_tasks):
            jt.cancel()
        RED = "\033[91m"
        RESET = "\033[0m"
        msg = self.get_text("connection_lost", self.global_default_lang)
        reason = f" [{event}]" if event else ""
        uptime = ""
        if self._session_started_at is not None:
            uptime = " " + self.get_text("session_uptime", self.global_default_lang, seconds=int(time.monotonic() - self._session_started_at))
            self._session_started_at = None
        print(f"{RED}WARNING ❗ {RESET}[{now()}] {self.boundjid.bare}: {msg}{reason}{uptime}")

    async def on_failed_auth(self, event):
        self.auth_failed_at = time.monotonic()
        self.auto_reconnect = False  # jangan spam login dengan kredensial yang ditolak
        self.session_active = False
        RED = "\033[91m"
        RESET = "\033[0m"
        logging.error(f"{RED}AUTH ERROR ❌ {RESET} " + self.get_text("auth_failed", self.global_default_lang))

    async def on_connected(self, event):
        logging.info(f"[{now()}] " + self.get_text("tcp_connected", self.global_default_lang, jid=self.boundjid.bare))

    async def on_connection_failed(self, event):
        self.last_down_at = time.monotonic()
        logging.error(f"[{now()}] " + self.get_text("connection_failed", self.global_default_lang, jid=self.boundjid.bare, reason=repr(event)))

    async def on_stream_error(self, error):
        try:
            condition = error["condition"]
        except Exception:
            condition = error
        if str(condition) == "conflict":
            logging.error(self.get_text("stream_error_conflict", self.global_default_lang, jid=self.boundjid.bare))
        else:
            logging.error(self.get_text("stream_error", self.global_default_lang, jid=self.boundjid.bare, condition=condition))

    async def handle_command(self, body, sender, room, nick, is_private):
        current_bot_nick = self.get_room_nick(room) if room else self.global_default_nick
        room_prefix = self.get_room_prefix(room) if room else ""

        if room and not is_private:
            body_stripped = body.strip()
            for label, bot_instance in ACTIVE_BOT_INSTANCES.items():
                other_bot_nick = bot_instance.get_room_nick(room)
                if other_bot_nick and other_bot_nick.lower() != current_bot_nick.lower():
                    if body_stripped.lower().startswith(other_bot_nick.lower()):
                        return

        if body.startswith(current_bot_nick):
            body = body[len(current_bot_nick) :].strip(" ,:")

        temp_parts = body.strip().lstrip(room_prefix if room_prefix else "").split()
        free_prefix_commands = ["prefix", "help", "commands", "cmdlist"]
        is_free_command = temp_parts and temp_parts[0].lower() in free_prefix_commands

        if is_free_command:
            if room_prefix and body.startswith(room_prefix):
                cmd_text = body[len(room_prefix):].strip()
            else:
                cmd_text = body.strip()
        else:
            if room_prefix and body.startswith(room_prefix):
                cmd_text = body[len(room_prefix):].strip()
            elif not room_prefix:
                cmd_text = body.strip()
            else:
                return

        parts = cmd_text.split()
        if not parts:
            return

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd not in self.COMMAND_LOOKUP:
            return

        target_func = self.COMMAND_LOOKUP[cmd]
        lang = self.get_lang(sender, room)

        owner_only_cmds = [
            "botowner_add", "botowner_del", "msg_to", "sheets", "botowner_show", "statusbot_global",
            "statusbot", "shutdown", "startup", "restart", "join", "aimodel", "gimgfilter", "gbadword",
            "ai_off_global", "ai_on_global", "say", "global_msg", "bookmark", "aiprovider", "gbadnick",
            "download", "upload", "deletefile", "deletefile_all", "renamefile", "movefile", "copyfile"
        ]

        moderator_cmds = [
            "ai_off", "ai_on", "nickbot", "kick", "ban", "unban", "banlist", "rejoin", "lang", "adminlist", "unadmin",
            "visitor", "participant", "member", "moderator", "admin", "owner", "statusbot_here", "unmember", "unowner",
            "prefix", "addweather", "delweather", "addrss", "delrss", "stopwordchain", "memberlist", "ownerlist", "leave",
            "badword", "badnick", "imgfilter"
        ]

        if cmd in owner_only_cmds:
            is_owner = await self.verify_real_owner_from_server(room, nick, sender)
            if not is_owner:
                ai_prompt = self.get_text("ai_prompt_owner", lang, nick=nick, cmd=cmd)
                session_key = f"room:{room}_user:{str(sender).lower()}" if room else f"pm:{str(sender).lower()}"

                if hasattr(self, "ask_ai_with_fallback"):
                    refusal_msg = await self.ask_ai_with_fallback(ai_prompt, room=room, session_key=session_key)
                else:
                    refusal_msg = self.get_text("refusal_owner", lang)

                await self.reply_user(sender, room, refusal_msg, is_private, nick=nick)
                return

        if cmd in moderator_cmds:
            is_owner = await self.verify_real_owner_from_server(room, nick, sender)
            privilege = await self.get_user_room_privilege(room, nick, sender)
            if not is_owner and privilege != "admin":
                ai_prompt = self.get_text("ai_prompt_mod", lang, nick=nick, cmd=cmd)
                session_key = f"room:{room}_user:{str(sender).lower()}" if room else f"pm:{str(sender).lower()}"

                if hasattr(self, "ask_ai_with_fallback"):
                    refusal_msg = await self.ask_ai_with_fallback(ai_prompt, room=room, session_key=session_key)
                else:
                    refusal_msg = self.get_text("refusal_mod", lang)

                await self.reply_user(sender, room, refusal_msg, is_private, nick=nick)
                return

        await target_func(sender, room, nick, is_private, args)

    async def reply_user(self, sender, room, text, is_private, nick=None):
        try:
            lower_text = text.lower()
            prefix_emoji = ""

            if any(w in lower_text for w in _EMOJI_FAIL):
                prefix_emoji = "❌ "
            elif any(w in lower_text for w in _EMOJI_OK):
                prefix_emoji = "✅ "
            elif any(w in lower_text for w in _EMOJI_RESTART):
                prefix_emoji = "🔄 "
            elif any(w in lower_text for w in _EMOJI_HELP):
                prefix_emoji = "🤖 "

            if prefix_emoji and not text.startswith(("❌", "✅", "🔄", "🤖", "📌", "🛡️", "👑", "💻", "🌤", "🌍", "ℹ️", "🚫", "🆗", "🔍", "📰", "📋", "🌐", "🧠", "📖")):
                text = prefix_emoji + text

            if is_private:
                self.send_message(mto=sender, mbody=text, mtype="chat")
            elif room and not is_private:
                final_text = f"{nick}: {text}" if nick else text
                self.send_message(mto=room, mbody=final_text, mtype="groupchat")
            else:
                self.send_message(mto=sender, mbody=text, mtype="chat")
        except Exception as e:
            lang_code = self.get_lang(sender, room)
            err_msg = self.get_text("reply_error", lang_code, error=e)
            logging.error(err_msg)


async def safe_disconnect(xmpp):
    """Putuskan koneksi dengan aman tanpa pernah menggantung atau melempar error."""
    try:
        res = xmpp.disconnect(wait=2.0)
        if inspect.isawaitable(res):
            await asyncio.wait_for(res, timeout=5)
    except Exception:
        try:
            xmpp.abort()
        except Exception:
            pass


async def run_bot_instance(jid, password, default_rooms, default_owners,
                           gemini_api_key, groq_api_key, openrouter_api_key, mistral_api_key, weather_api_key,
                           default_nick, default_status, default_lang, auto_join_rooms, is_primary_jid, jid_label, initial_delay=0, show_plugin_logs=False):
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)

    YELLOW = "\033[93m"
    RED = "\033[91m"
    PURPLE = "\033[95m"
    RESET = "\033[0m"

    backoff_delay = 5
    max_backoff = 60

    # Satu instance per akun, dibuat sekali. Koneksi ulang dikerjakan slixmpp sendiri;
    # loop di bawah hanya memantau (tidak ikut memanggil connect() selama koneksi masih pulih).
    try:
        xmpp = ModernMultiMucBot(
            jid, password, default_rooms, default_owners,
            gemini_api_key, groq_api_key, openrouter_api_key, mistral_api_key, weather_api_key,
            default_nick, default_status, default_lang,
            should_join_rooms=auto_join_rooms,
            is_primary_jid=is_primary_jid,
            show_plugin_logs=show_plugin_logs
        )
    except Exception as e:
        loop_err_msg = _main_langs.get(default_lang, {}).get("loop_error", "Error in loop for {jid_label}: {e}. Retry in {delay} seconds...").format(jid_label=jid_label, e=e, delay=0)
        print(f"{RED}ERROR  \u274c  {RESET}{loop_err_msg}")
        return

    xmpp.use_signals = False
    if not USE_IPV6:
        # Termux/jaringan seluler sering gagal di IPv6 (OSError 101 'Network is unreachable')
        xmpp.use_ipv6 = False

    clean_label = jid_label.lower().replace(":", "").replace("\x1b[93m", "").replace("\x1b[0m", "").strip()
    ACTIVE_BOT_INSTANCES[clean_label] = xmpp

    healthy_since = None
    xmpp.connect()
    last_attempt = time.monotonic()

    while True:
        try:
            await asyncio.sleep(1)
            t = time.monotonic()

            # 1) Sesi sehat: cukup catat, jangan ganggu
            if xmpp.session_active:
                if healthy_since is None:
                    healthy_since = t
                    connected_msg = xmpp.get_text("bot_connected", default_lang, jid_label=jid_label, jid=jid)
                    print(f"{PURPLE}LOGIN \U0001f197 {RESET}[{now()}] {connected_msg}")
                elif t - healthy_since >= STABLE_UPTIME:
                    backoff_delay = 5
                continue

            healthy_since = None

            # 1b) Dimatikan manual lewat perintah: biarkan mati sampai ada perintah startup
            if getattr(xmpp, "manual_stop", False):
                continue

            # 2) Login ditolak: tunggu lama sebelum mencoba lagi (hindari diblokir server)
            if xmpp.auth_failed_at is not None:
                if t - xmpp.auth_failed_at >= AUTH_FAIL_DELAY:
                    xmpp.auth_failed_at = None
                    xmpp.auto_reconnect = True
                    last_attempt = t
                    xmpp.connect()
                continue

            # 3) Beri kesempatan slixmpp pulih sendiri; paksa reconnect hanya bila benar-benar macet
            limit = SESSION_START_TIMEOUT if xmpp.is_connected() else STALL_TIMEOUT
            if t - max(last_attempt, xmpp.last_down_at) < limit:
                continue

            logging.warning(f"[{now()}] " + tr("session_timeout_force", default_lang, jid_label=jid_label, seconds=int(limit)))
            xmpp.auto_reconnect = False  # cegah reconnect ganda selama kita yang mengendalikan
            await safe_disconnect(xmpp)

            delay = backoff_delay + random.uniform(0, 3)  # jitter agar multi JID tidak serentak
            reconnect_msg = _main_langs.get(default_lang, {}).get("reconnect_notice", "Connection lost for {jid_label}. Reconnecting in {delay} seconds...").format(jid_label=jid_label, delay=int(delay))
            print(f"{YELLOW}WARNING \u2757 {RESET}[{now()}] {reconnect_msg} {tr('reconnect_actual_delay', default_lang, delay=int(delay))}")
            await asyncio.sleep(delay)
            backoff_delay = min(backoff_delay * 2, max_backoff)

            last_attempt = time.monotonic()
            xmpp.connect()
            xmpp.auto_reconnect = True

        except asyncio.CancelledError:
            xmpp.auto_reconnect = False
            await safe_disconnect(xmpp)
            break
        except Exception as e:
            loop_err_msg = _main_langs.get(default_lang, {}).get("loop_error", "Error in loop for {jid_label}: {e}. Retry in {delay} seconds...").format(jid_label=jid_label, e=e, delay=backoff_delay)
            print(f"{RED}ERROR  \u274c  {RESET}{loop_err_msg}")
            await asyncio.sleep(backoff_delay)
            backoff_delay = min(backoff_delay * 2, max_backoff)


async def loop_lag_monitor():
    """Deteksi event loop yang macet. Jika plugin memakai panggilan blocking (requests, time.sleep,
    query berat), ping XMPP tidak sempat dibalas dan server memutus koneksi."""
    # Beri waktu startup: memuat plugin/import library berat memang memblokir loop sesaat (normal)
    await asyncio.sleep(25)
    while True:
        t0 = time.monotonic()
        await asyncio.sleep(1)
        lag = time.monotonic() - t0 - 1
        if lag > LOOP_LAG_WARN:
            logging.warning(tr("loop_lag", lag=f"{lag:.1f}"))


async def main_async():
    global ENABLE_SM, USE_IPV6, UI_LANG
    config = load_config("config.txt")
    ENABLE_SM = config.get("STREAM_MANAGEMENT", "on").strip().lower() not in ("off", "false", "0", "no")
    USE_IPV6 = config.get("USE_IPV6", "off").strip().lower() in ("on", "true", "1", "yes")
    asyncio.get_running_loop().set_exception_handler(_loop_exception_handler)
    if config.get("DEBUG_XMPP", "off").strip().lower() in ("on", "true", "1", "yes"):
        enable_xmpp_debug()

    jid1, pwd1, nick1 = get_account_credentials(config, "")
    jid2, pwd2, nick2 = get_account_credentials(config, "2")
    jid3, pwd3, nick3 = get_account_credentials(config, "3")

    DEFAULT_STATUS = config.get("DEFAULT_STATUS", "")
    DEFAULT_LANG = config.get("DEFAULT_LANG", "id").lower()
    UI_LANG = DEFAULT_LANG

    GEMINI_API_KEY = config.get("GEMINI_API_KEY", "")
    GROQ_API_KEY = config.get("GROQ_API_KEY", "")
    OPENROUTER_API_KEY = config.get("OPENROUTER_API_KEY", "") or os.getenv("OPENROUTER_API_KEY", "")
    MISTRAL_API_KEY = config.get("MISTRAL_API_KEY", "")
    WEATHER_API_KEY = config.get("WEATHER_API_KEY", "")

    DEFAULT_ROOMS = {r.strip() for r in config.get("DEFAULT_ROOMS", "").split(",") if r.strip()}
    DEFAULT_OWNERS = [o.strip() for o in config.get("DEFAULT_OWNERS", "").split(",") if o.strip()]

    if not jid1 or not pwd1:
        empty_err = _main_langs.get(DEFAULT_LANG, {}).get("config_jid_empty", "The primary JID or PASSWORD cannot be empty in config.txt!")
        logging.error(empty_err)
        sys.exit(1)

    tasks = [asyncio.create_task(loop_lag_monitor())]

    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

    # JID 1 (Utama)
    tasks.append(asyncio.create_task(run_bot_instance(
        jid1, pwd1, DEFAULT_ROOMS, DEFAULT_OWNERS,
        GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, WEATHER_API_KEY,
        nick1, DEFAULT_STATUS, DEFAULT_LANG, auto_join_rooms=True, is_primary_jid=True,
        jid_label=f"{YELLOW}JID1:{RESET}", initial_delay=0, show_plugin_logs=True
    )))

    # JID 2 (Jeda 3 detik)
    if jid2 and pwd2:
        tasks.append(asyncio.create_task(run_bot_instance(
            jid2, pwd2, set(), DEFAULT_OWNERS,
            GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, WEATHER_API_KEY,
            nick2, DEFAULT_STATUS, DEFAULT_LANG, auto_join_rooms=True, is_primary_jid=False,
            jid_label=f"{YELLOW}JID2:{RESET}", initial_delay=3.0, show_plugin_logs=False
        )))

    # JID 3 (Jeda 6 detik)
    if jid3 and pwd3:
        tasks.append(asyncio.create_task(run_bot_instance(
            jid3, pwd3, set(), DEFAULT_OWNERS,
            GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, WEATHER_API_KEY,
            nick3, DEFAULT_STATUS, DEFAULT_LANG, auto_join_rooms=True, is_primary_jid=False,
            jid_label=f"{YELLOW}JID3:{RESET}", initial_delay=6.0, show_plugin_logs=False
        )))

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        stop_msg = _main_langs.get("id", {}).get("all_bots_stopped", "All bots stopped by user.")
        print(f"\n{GREEN}INFO  ⚠️   {RESET}{RED}{stop_msg}")