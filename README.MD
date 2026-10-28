# 🤖 Smart Next-Gen XMPP Bot

Bot XMPP multi-akun berbasis **Python + slixmpp** dengan sistem plugin, AI multi-provider
(Gemini, Groq, OpenRouter, Mistral), pemahaman perintah bahasa alami, moderasi room, dan
antarmuka **16 bahasa**.

> © 2026 Ndregil — https://ndregil.eu.org — admin@ndregil.eu.org

---

## ✨ Fitur Utama

- **Hingga 3 akun sekaligus** (`jid1`, `jid2`, `jid3`), semuanya berjalan dalam satu proses.
- **Koneksi stabil**: Stream Management (XEP-0198), keepalive toleran, reconnect dengan backoff + jitter, join room bertahap.
- **AI multi-provider dengan fallback otomatis** (Gemini → Groq → OpenRouter → Mistral), memori percakapan per pengguna, dan **perintah bahasa alami** (mis. *"Bot, jadikan Joni member"*) dengan konfirmasi untuk aksi berisiko.
- **Moderasi**: anti-flood/anti-spam mention, filter kata & nickname terlarang (multi bahasa, tahan leet-speak), **filter gambar NSFW** (XEP-0425 untuk hapus pesan).
- **Manajemen MUC**: admin, owner, member, moderator, visitor, kick, ban/unban, daftar afiliasi, prefix per room, dll.
- **Utilitas**: cuaca, gempa (BMKG/USGS), hari libur (Indonesia & dunia), RSS/Atom/JSON Feed (dengan jadwal & terjemahan otomatis), terjemahan, pencarian, meme, `seen`, `tell`, uptime server XMPP, disco, ping, version.
- **Media**: transkripsi voice note otomatis (Groq Whisper / Mistral Voxtral / Gemini), balasan suara (TTS), pembuat gambar (Pollinations).
- **File manager khusus owner**: tempat sampah, audit log, cadangan, deploy plugin dari URL + rollback, `find`, `grep`, `edit`, dll.
- **Hot reload plugin** tanpa memutus akun (`reload <plugin>`).
- **Alias multibahasa** (id, en, ru, de, fr, ar, hi, zh, jv, es, pt, pl, it, fa, tr, ua) + alias kustom (`alias` / `galias`).

---

## 📁 Struktur Folder

Letakkan file sesuai struktur berikut. **`main.py` di folder utama, semua `cmd_*.py` dan `zz_aliases.py` di folder `plugins/`.**

```
SmartNextGen/
├── main.py
├── config.txt                 # dibuat sendiri (lihat bagian Konfigurasi)
├── requirements.txt
├── README.md
├── plugins/
│   ├── __init__.py            # (opsional, file kosong)
│   ├── cmd_admin.py
│   ├── cmd_ai.py
│   ├── cmd_alias.py
│   ├── cmd_antiflood.py
│   ├── cmd_browser.py
│   ├── cmd_filemanager.py
│   ├── cmd_filetools.py
│   ├── cmd_games.py
│   ├── cmd_google.py
│   ├── cmd_imgfilter.py
│   ├── cmd_info.py
│   ├── cmd_media.py
│   ├── cmd_meme.py
│   ├── cmd_muc.py
│   ├── cmd_reload.py
│   ├── cmd_rss.py
│   ├── cmd_seen.py
│   ├── cmd_study.py
│   ├── cmd_tell.py
│   ├── cmd_users.py
│   ├── cmd_voice.py
│   ├── cmd_weather.py
│   ├── cmd_worldholiday.py
│   └── zz_aliases.py          # harus dimuat paling akhir (nama sudah diatur)
├── lang/
│   ├── main/                  # id.json, en.json, ... (pesan sistem main.py)
│   ├── cmd_ai/                # <kode>.json per plugin
│   ├── cmd_users/
│   └── and others             # satu folder per plugin yang punya terjemahan
├── data/                      # dibuat otomatis (database, log, dll.)
└── filemanager/
    ├── downloads              # folder yang berisi file hasil download dari bot
    └── upload                 # Taruh file disini untuk di upload (jika perlu)
```

> Folder `lang/<nama_plugin>/<kode>.json` berisi terjemahan pesan tiap plugin.
> Kode bahasa yang didukung: `id en ru de fr ar hi zh jv es pt pl it fa tr ua`.
> Folder `filemanager/` dan `data/` dibuat otomatis saat bot berjalan.

---

## 🧰 Persyaratan

| Kebutuhan | Keterangan |
|---|---|
| Python | **3.10+** (disarankan 3.11/3.12) |
| Akun XMPP | 1 akun (wajib) hingga 3 akun |
| API key AI | Opsional, minimal salah satu agar fitur AI aktif |
| ffmpeg | Opsional, untuk voice note format AMR/3GP/AAC/CAF |
| Server XMPP | Mendukung MUC; HTTP Upload (XEP-0363) dibutuhkan untuk meme/TTS/image/backup-send |

---

## 🚀 Instalasi

### 1. Linux / VPS (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git

# salin folder bot ke server, lalu:
cd SmartNextGen
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Termux (Android)

```bash
pkg update && pkg upgrade
pkg install python ffmpeg git libxml2 libxslt clang rust
pip install --upgrade pip
cd SmartNextGen
pip install -r requirements.txt
```

> Di Termux/jaringan seluler IPv6 sering bermasalah. Bot sudah memakai IPv4 secara bawaan
> (`USE_IPV6=off`). Jika `pillow`/`aiohttp` gagal dibangun, jalankan `pkg install python-pillow` atau
> instal ulang paket build di atas.

### 3. Windows

```powershell
cd SmartNextGen
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
(Opsional: pasang [ffmpeg](https://ffmpeg.org/download.html) dan tambahkan ke `PATH`.)

### 4. Filter gambar lokal NudeNet (opsional)

Buka komentar `nudenet` di `requirements.txt` lalu `pip install nudenet`, atau cukup andalkan
backend API (Groq/Gemini/Mistral/OpenRouter) yang sudah ada.

---

## ⚙️ Konfigurasi (`config.txt`)

Buat file `config.txt` di folder utama. Baris berawalan `#` adalah komentar.

```ini
# ===== AKUN UTAMA (wajib) =====
JID=bot_1@example.com
PASSWORD=rahasia_anda
DEFAULT_NICK=SmartNG.1
RESOURCE=SmartNG

# ===== AKUN TAMBAHAN (opsional) =====
JID2=bot_2@example.com
PASSWORD2=rahasia2
DEFAULT_NICK2=SmartNG.2

JID3=bot_3@example.com
PASSWORD3=rahasia3
DEFAULT_NICK3=SmartNG.3

# ===== UMUM =====
DEFAULT_LANG=en
DEFAULT_STATUS=online Smart Next-Gen XMPP Bot
DEFAULT_ROOMS=room1@conference.example.com,room2@conference.example.com
DEFAULT_OWNERS=admin@example.com,owner2@example.com

# ===== API KEY (isi yang dipakai saja) =====
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
MISTRAL_API_KEY=
WEATHER_API_KEY=            # OpenWeatherMap

# ===== OPSI JARINGAN =====
USE_IPV6=off                # on bila jaringan mendukung IPv6
STREAM_MANAGEMENT=on        # off untuk mematikan XEP-0198
DEBUG_XMPP=off              # on untuk log XMPP detail (password disamarkan)
```

Penjelasan singkat:

- **`DEFAULT_OWNERS`**: JID (bare) yang menjadi **owner bot**. Owner dapat memakai semua perintah 👑 (restart, shutdown, join, aiprovider, file manager, dsb.).
- **`DEFAULT_ROOMS`**: room yang otomatis dimasuki akun utama (`JID`) saat pertama kali. Selanjutnya daftar room disimpan di database.
- **`DEFAULT_LANG`**: bahasa bawaan (`id`, `en`, `ru`, `de`, `fr`, `ar`, `hi`, `zh`, `jv`, `es`, `pt`, `pl`, `it`, `fa`, `tr`, `ua`). Tiap room bisa diganti dengan `lang <kode>`.
- **`DEFAULT_STATUS`**: awali dengan `away`/`xa`/`dnd`/`chat` bila ingin status presence tertentu.

> 🔒 **Jangan pernah membagikan `config.txt`** (berisi password & API key). Tambahkan ke `.gitignore`.

### Mendapatkan API key

| Layanan | Kegunaan | Situs |
|---|---|---|
| Google Gemini | AI utama, gambar, voice | https://aistudio.google.com/apikey |
| Groq | AI cepat, Whisper (voice), gambar | https://console.groq.com/keys |
| OpenRouter | AI & gambar (model gratis) | https://openrouter.ai/keys |
| Mistral | AI, Voxtral (voice) | https://console.mistral.ai/ |
| OpenWeatherMap | Perintah cuaca | https://openweathermap.org/api |

---

## ▶️ Menjalankan Bot

```bash
python main.py          # Windows: py main.py
```

Jika berhasil, log akan menampilkan `LOGIN 🆗`, daftar plugin yang dimuat, dan `SUCCESS ✅` untuk tiap room.
Hentikan dengan `Ctrl + C`.

### Berjalan di latar belakang

**Termux / sederhana (tmux atau screen):**
```bash
tmux new -s SmartNextGen
python main.py
# lepas: Ctrl+B lalu D   |   kembali: tmux attach -t SmartNextGen
```

**systemd (VPS):** buat `/etc/systemd/system/xmppbot.service`
```ini
[Unit]
Description=Smart Next-Gen XMPP Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/SmartNextGen
ExecStart=/home/botuser/SmartNextGen/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xmppbot
sudo journalctl -u xmppbot -f      # lihat log
```
> Perintah `restart all` memakai `os.execl`, sehingga cocok dengan `Restart=always` maupun dijalankan manual.

---

## 💬 Cara Memakai

- **Di room**: ketik perintah langsung (`help`), atau sebut nick bot (`SmartNG: weather Jakarta`).
  Jika room memakai **prefix** (`prefix !`), ketik `!weather Jakarta`. Perintah `help`, `commands`, `cmdlist`, dan `prefix` selalu bebas prefix.
- **Di PM**: langsung ketik perintah atau ngobrol.
- **Bahasa alami**: sebut nick bot lalu tulis permintaan biasa, mis. `SmartNG: tolong kick Sari, dia spam`. Aksi berisiko (shutdown, restart, ban, owner, leave, dll.) akan meminta konfirmasi. Hak akses **tetap diperiksa** seperti biasa.
- Ketik `help` untuk daftar perintah sesuai bahasa room, dan `help <perintah>` untuk detail.

### Tingkat Akses

| Ikon | Level | Siapa |
|---|---|---|
| 👤 | Participant & Member | Semua orang |
| 💎 | Admin & Owner Group | Admin/owner/moderator room & owner bot |
| 🔑 | Master Bot | Owner di `config.txt` (file manager) |
| 👑 | Bot Owner | Owner bot |

### Ringkasan Perintah

**Umum (👤)** — `help`, `ping`, `version`, `uptime [server]`, `lang`, `userslist`, `disco`, `dns`, `to_admin`, `test`,
`weather [kota]`, `weatherlist`, `earthquake [us]`, `holiday`, `worldholiday [negara]`, `tr <kode> <teks>`, `google`, `maps`, `youtube`, `www <url>`,
`rss [url|no]`, `listrss`, `meme [kategori]`, `study`, `seen <nick>`, `tell <nick> <pesan>`, `untell`, `transcribe`, `tts`, `image`,
game: `trivia`, `ans`, `guess`, `roll`, `toss`, `wordchain`, `pet`, `feed`, `antiflood`, `access [nick]`.

**Admin room (💎)** — `admin/unadmin`, `owner/unowner`, `member/unmember`, `moderator`, `participant`, `visitor`, `kick`, `ban/unban`,
`adminlist`, `memberlist`, `ownerlist`, `banlist`, `nickbot`, `prefix`, `rejoin`, `leave`, `say`, `statusbot_here`,
`ai_on/ai_off`, `addweather/delweather`, `addrss/delrss`, `holidayalert`, `badword`, `badnick`, `imgfilter`, `voice`, `ttsreply`, `alias`.

**Bot Owner (👑)** — `join`, `restart [jid1|jid2|jid3|all]`, `shutdown`, `startup`, `global_msg`, `msg_to`, `bookmark`,
`botowner_add/del/show`, `statusbot_global`, `aiprovider`, `aimodel`, `ai_on_global/ai_off_global`,
`gbadword`, `gbadnick`, `gimgfilter`, `gvoice`, `gtts`, `gimage`, `galias`, `reload`.

**File manager (🔑, khusus owner)** — `filemanager`, `cd`, `back`, `catfile`, `mkdir`, `download`, `upload`, `deletefile`,
`renamefile`, `movefile`, `copyfile`, `zip/unzip`, `tar/untar`, `trash`, `undelete`, `fmroot`, `audit`,
`find`, `grep`, `tree`, `du`, `df`, `head`, `tail`, `hash`, `writefile`, `edit`, `backup`, `deploy`, `rollback`, `inbox`.

Contoh:
```
aiprovider groq              # ganti provider AI
gimgfilter on                # aktifkan filter gambar global
imgfilter off                # matikan di room ini
addrss 1h https://contoh.com/feed   # kirim berita terbaru tiap 1 jam
galias add pg=ping           # "pg" menjalankan "ping" di semua room
reload rss                   # muat ulang plugin tanpa memutus akun
backup auto 1d               # cadangan otomatis harian
```

---

## 🔄 Memperbarui & Reload

- Edit plugin, lalu jalankan **`reload <nama_plugin>`** (mis. `reload rss`) atau `reload all`.
  Kode diperiksa dulu; bila ada kesalahan, versi lama tetap berjalan.
- `cmd_users`, `zz_aliases`, dan `cmd_reload` **tidak bisa** di-reload → gunakan `restart all`.
- Pasang plugin dari URL: `deploy <url> [nama] [sha256=<hex>]` (otomatis cadangan + rollback bila gagal).

---

## 🗄️ Data & Cadangan

- Database tiap akun: `data/botsettings_<jid>.db` (owner, room, setting, RSS, alias, dll.).
- Log AI: `data/AI.log` · Log filter gambar: `data/imgfilter-YYYY-MM-DD.jsonl` · Audit file manager: `data/filemanager-audit.jsonl`.
- Cadangan: perintah `backup` (data + plugins + lang), `backup full` (termasuk `config.txt`, **jangan dikirim lewat chat**).

---

## 🛠️ Pemecahan Masalah

| Masalah | Solusi |
|---|---|
| `Configuration file 'config.txt' not found` | Buat `config.txt` di folder yang sama dengan `main.py`. |
| `The primary JID or PASSWORD cannot be empty` | Isi `JID` dan `PASSWORD` di `config.txt`. |
| `AUTH ERROR` | Password/JID salah. Bot menunggu 120 detik sebelum mencoba lagi (hindari ban server). |
| Plugin tidak termuat / `ModuleNotFoundError: plugins` | Pastikan folder `plugins/` ada di sebelah `main.py` dan jalankan dari folder bot. |
| `ModuleNotFoundError: google.genai` | `pip install google-genai` (bukan `google-generativeai`). |
| AI tidak membalas | Isi minimal satu API key; cek `data/AI.log`; coba `aiprovider <nama>`. |
| Bot tidak masuk room (`registration-required` / `forbidden`) | Room khusus member atau akun diblokir. Room dilewati sampai bot di-restart. |
| Terputus berulang di jaringan seluler | Biarkan `USE_IPV6=off`; cek peringatan `loop lag` (plugin yang memblokir). |
| Meme/TTS/image/backup gagal terkirim | Server XMPP harus menyediakan HTTP Upload (XEP-0363). |
| Voice note AMR/3GP tidak terbaca | Pasang `ffmpeg`. |
| Pesan tidak terhapus oleh filter gambar | Bot harus **moderator** di room dan server mendukung XEP-0425 + stanza-id. |
| Cuaca: "API key kosong" | Isi `WEATHER_API_KEY` (OpenWeatherMap). |

Aktifkan `DEBUG_XMPP=on` untuk log XMPP detail (data login otomatis disamarkan).

---

## 🔐 Catatan Keamanan

- Simpan `config.txt` dengan izin ketat (`chmod 600 config.txt`).
- Hanya isi `DEFAULT_OWNERS` dengan JID yang benar-benar dipercaya; owner dapat menjalankan file manager, `deploy`, dan `edit` plugin (setara akses kode).
- Unduhan RSS, filter gambar, dan voice memakai perlindungan anti-SSRF (hanya IP publik).
- `config.txt` dan `data/*.db` dilindungi dari hapus/pindah/tulis lewat file manager.

---

## 📄 Lisensi

Hak cipta © 2026 Ndregil. Hubungi pembuat untuk ketentuan penggunaan dan distribusi.
