# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot - Alias multibahasa per bahasa room
# Simpan di plugins/zz_aliases.py (dimuat paling akhir). FILE INI SAJA - main.py & plugin lain TIDAK perlu diubah.
# Plugin ini memasang sendiri (saat bot start): pemetaan alias -> nama asli di handle_command
# (cek owner/moderator tetap benar), daftar perintah AI tanpa alias, dan help per bahasa room.
#
# - Semua alias tetap bisa dipakai kapan saja (id, en, ru, de, fr, ar, hi, zh, jv).
# - Tampilan (help, help <perintah>) mengikuti bahasa room: bila room diset `lang ru`,
#   daftar perintah tampil dalam bahasa Rusia. Bahasa 'en' menampilkan nama asli.
#
# Kolom tiap baris, berurutan: id, ru, de, fr, ar, hi, zh, jv
# "" = tidak ada alias (tampil nama asli). Beberapa alias dalam satu kolom dipisah
# spasi; yang PERTAMA dipakai sebagai nama tampilan.

import re

ORDER = ("id", "ru", "de", "fr", "ar", "hi", "zh", "jv")

ALIASES = {
    # --- cmd_users ---
    "lang": ("", "язык", "sprache", "langue", "لغة", "भाषा", "语言", ""),
    "uptime": ("", "аптайм", "laufzeit", "disponibilite", "مدة_التشغيل", "चालूसमय", "运行时间", ""),
    "to_admin": ("", "админу", "anadmin", "auadmin", "للمشرف", "प्रशासकको", "联系管理员", ""),
    "userslist": ("", "пользователи", "benutzer", "utilisateurs", "المستخدمين", "उपयोगकर्ता", "用户列表", ""),
    "disco": ("", "обзор", "erkunden", "decouvrir", "استكشاف", "अन्वेषण", "服务发现", ""),
    "dns": ("", "днс", "", "", "نظام_النطاقات", "डीएनएस", "域名解析", ""),
    "help": ("", "помощь", "hilfe", "aide", "مساعدة", "मदद", "帮助", ""),
    "next": ("", "далее", "weiter", "suivant", "التالي", "अगला", "下一页", ""),
    "ping": ("", "пинг", "pingen", "pinger", "بنج", "पिंग", "测速", ""),
    "test": ("", "тест", "", "tester", "اختبار", "परीक्षण", "测试", ""),
    "version": ("", "версия", "", "", "الإصدار", "संस्करण", "版本", ""),
    # --- cmd_alias ---
    "alias": ("", "псевдоним", "kurzbefehl", "raccourci", "اسم_مستعار", "उपनाम", "别名", ""),
    "galias": ("", "г_псевдоним", "g_kurzbefehl", "g_raccourci", "ع_اسم_مستعار", "वै_उपनाम", "全局别名", ""),
    # --- cmd_admin ---
    "bookmark": ("", "закладки", "lesezeichen", "signets", "المفضلة", "बुकमार्क", "书签", ""),
    "botowner_add": ("", "добавить_владельца", "besitzer_hinzufuegen", "ajouter_proprietaire", "إضافة_مالك", "बॉट_स्वामी_जोड़ें", "添加机器人主人", ""),
    "botowner_del": ("", "удалить_владельца", "besitzer_entfernen", "supprimer_proprietaire", "حذف_مالك", "बॉट_स्वामी_हटाएं", "删除机器人主人", ""),
    "botowner_show": ("", "показать_владельцев", "besitzer_zeigen", "voir_proprietaires", "عرض_المالكين", "बॉट_स्वामी_दिखाएं", "查看机器人主人", ""),
    "global_msg": ("", "глобальное_сообщение", "globale_nachricht", "message_global", "رسالة_عامة", "वैश्विक_संदेश", "全局消息", ""),
    "join": ("", "войти", "beitreten", "rejoindre", "انضمام", "जुड़ें", "加入", ""),
    "leave": ("", "выйти", "verlassen", "quitter", "مغادرة", "छोड़ें", "离开", ""),
    "msg_to": ("", "отправить", "senden", "envoyer", "إرسال", "भेजें", "发送消息", ""),
    "restart": ("", "перезапуск", "neustart", "redemarrer", "إعادة_تشغيل", "पुनरारंभ", "重启", ""),
    "say": ("", "сказать", "sagen", "dire", "قل", "बोलो", "说", ""),
    "shutdown": ("", "выключить", "herunterfahren", "eteindre", "إيقاف", "बंद", "关机", ""),
    "startup": ("", "запуск", "starten", "demarrer", "تشغيل", "चालू", "启动", ""),
    "statusbot_global": ("", "статус_глобальный", "status_global", "statut_global", "حالة_عامة", "वैश्विक_स्थिति", "全局状态", ""),
    "statusbot_here": ("", "статус_здесь", "status_hier", "statut_ici", "حالة_هنا", "स्थिति_यहां", "本群状态", ""),
    # --- cmd_ai ---
    "ai_off": ("", "ии_выкл", "ki_aus", "ia_desactiver", "ذكاء_إيقاف", "एआई_बंद", "关闭ai", ""),
    "ai_on": ("", "ии_вкл", "ki_an", "ia_activer", "ذكاء_تشغيل", "एआई_चालू", "开启ai", ""),
    "ai_off_global": ("", "ии_выкл_глобально", "ki_aus_global", "ia_desactiver_global", "ذكاء_إيقاف_عام", "एआई_बंद_वैश्विक", "全局关闭ai", ""),
    "ai_on_global": ("", "ии_вкл_глобально", "ki_an_global", "ia_activer_global", "ذكاء_تشغيل_عام", "एआई_चालू_वैश्विक", "全局开启ai", ""),
    "aiprovider": ("", "провайдер_ии", "ki_anbieter", "fournisseur_ia", "مزود_ذكاء", "एआई_प्रदाता", "ai提供商", ""),
    "aimodel": ("", "модель_ии", "ki_modell", "modele_ia", "نموذج_ذكاء", "एआई_मॉडल", "ai模型", ""),
    # --- cmd_antiflood ---
    "badword": ("", "плохие_слова", "schimpfwort", "gros_mots", "كلمات_سيئة", "बुरे_शब्द", "违禁词", ""),
    "badnick": (" ", "плохие_ники", "schlechter_nick", "pseudo_interdit", "أسماء_محظورة", "बुरे_नाम", "违禁昵称", ""),
    "gbadword": (" ", "г_плохие_слова", "g_schimpfwort", "g_gros_mots", "ع_كلمات_سيئة", "वै_बुरे_शब्द", "全局违禁词", ""),
    "gbadnick": (" ", "г_плохие_ники", "g_schlechter_nick", "g_pseudo_interdit", "ع_أسماء_محظورة", "वै_बुरे_नाम", "全局违禁昵称", ""),
    "antiflood": ("", "антифлуд", "antiflut", "antispam", "مكافحة_الإغراق", "एंटीफ्लड", "防刷屏", ""),
    # --- cmd_browser ---
    "www": ("", "веб", "webseite", "siteweb", "ويب", "वेब", "网页", ""),
    # --- cmd_games ---
    "trivia": ("", "викторина", "wissensquiz", "questionnaire", "مسابقة", "प्रश्नोत्तरी", "问答", ""),
    "ans": ("", "ответ", "antwort", "reponse", "إجابة", "उत्तर", "回答", ""),
    "stoptrivia": ("", "стоп_викторина", "stopp_quiz", "stop_quiz", "إيقاف_المسابقة", "प्रश्नोत्तरी_रोकें", "停止问答", ""),
    "guess": ("", "угадай", "raten", "deviner", "خمن", "अनुमान", "猜数字", ""),
    "roll": ("", "кубик", "wuerfeln", "lancerde", "نرد", "पासा", "掷骰子", ""),
    "toss": ("", "монетка", "muenze", "piece", "عملة", "सिक्का", "抛硬币", ""),
    "wordchain": ("", "цепочка_слов", "wortkette", "chaine_mots", "سلسلة_كلمات", "शब्द_श्रृंखला", "词语接龙", ""),
    "stopwordchain": ("", "стоп_цепочка", "stopp_wortkette", "stop_chaine", "إيقاف_السلسلة", "श्रृंखला_रोकें", "停止接龙", ""),
    "pet": ("", "питомец", "haustier", "animal", "حيوان_أليف", "पालतू", "宠物", ""),
    "feed": ("", "кормить", "fuettern", "nourrir", "إطعام", "खिलाओ", "喂食", ""),
    # --- cmd_imgfilter ---
    "imgfilter": ("", "фильтр_картинок", "bildfilter", "filtre_image", "فلتر_الصور", "चित्र_फ़िल्टर", "图片过滤", ""),
    "gimgfilter": ("", "г_фильтр_картинок", "g_bildfilter", "g_filtre_image", "ع_فلتر_الصور", "वै_चित्र_फ़िल्टर", "全局图片过滤", ""),
    # --- cmd_google ---
    "tr": ("", "перевод", "uebersetzen", "traduire", "ترجمة", "अनुवाद", "翻译", ""),
    "google": ("", "поиск", "suche", "recherche", "بحث", "खोज", "搜索", ""),
    "maps": ("", "карты", "karte", "carte", "خريطة", "नक्शा", "地图", ""),
    "youtube": ("", "ютуб", "videosuche", "chercher_video", "يوتيوب", "यूट्यूब", "油管", ""),
    # --- cmd_info ---
    "earthquake": ("", "землетрясение", "erdbeben", "seisme", "زلزال", "भूकंप", "地震", ""),
    "holiday": ("", "праздник", "feiertag", "ferie", "عطلة", "छुट्टी", "假期", ""),
    # --- cmd_meme ---
    "meme": ("", "мем", "", "mème", "ميم", "मीम", "表情包", ""),
    # --- cmd_muc ---
    "access": ("", "доступ", "zugriff", "acces", "صلاحية", "अनुमति", "权限", ""),
    "admin": ("", "админ", "verwalter", "administrateur", "مشرف", "प्रशासक", "管理员", ""),
    "adminlist": ("", "список_админов", "adminliste", "liste_admins", "قائمة_المشرفين", "प्रशासक_सूची", "管理员列表", ""),
    "ban": ("", "бан", "bannen", "bannir", "حظر", "प्रतिबंध", "封禁", ""),
    "banlist": ("", "список_банов", "bannliste", "liste_bannis", "قائمة_المحظورين", "प्रतिबंध_सूची", "封禁列表", ""),
    "kick": ("", "кик", "rauswerfen", "expulser", "طرد", "निकालो", "踢出", ""),
    "member": ("", "участник", "mitglied", "membre", "عضو", "सदस्य", "成员", ""),
    "memberlist": ("", "список_участников", "mitgliederliste", "liste_membres", "قائمة_الأعضاء", "सदस्य_सूची", "成员列表", ""),
    "moderator": ("", "модератор", "", "moderateur", "مراقب", "मॉडरेटर", "协管员", ""),
    "nickbot": ("", "ник_бота", "botname", "pseudo_bot", "اسم_البوت", "बॉट_नाम", "机器人昵称", ""),
    "owner": ("", "владелец", "besitzer", "proprietaire", "مالك", "स्वामी", "所有者", ""),
    "ownerlist": ("", "список_владельцев", "besitzerliste", "liste_proprietaires", "قائمة_المالكين", "स्वामी_सूची", "所有者列表", ""),
    "participant": ("", "собеседник", "teilnehmer", "intervenant", "مشارك", "प्रतिभागी", "参与者", ""),
    "prefix": ("", "префикс", "praefix", "prefixe", "بادئة", "उपसर्ग", "前缀", ""),
    "rejoin": ("", "перезайти", "erneut_beitreten", "reentrer", "إعادة_انضمام", "पुनः_जुड़ें", "重新加入", ""),
    "unadmin": ("", "снять_админа", "admin_entfernen", "retirer_admin", "إزالة_مشرف", "प्रशासक_हटाएं", "取消管理员", ""),
    "unowner": ("", "снять_владельца", "besitzer_entziehen", "retirer_proprietaire", "إزالة_مالك", "स्वामी_हटाएं", "取消所有者", ""),
    "unban": ("", "разбан", "entbannen", "debannir", "رفع_الحظر", "प्रतिबंध_हटाएं", "解封", ""),
    "unmember": ("", "убрать_участника", "mitglied_entfernen", "retirer_membre", "إزالة_عضو", "सदस्य_हटाएं", "取消成员", ""),
    "visitor": ("", "гость", "besucher", "visiteur", "زائر", "आगंतुक", "访客", ""),
    # --- cmd_rss ---
    "rss": ("", "рсс", "newsfeed", "fluxrss", "تغذية_أخبار", "आरएसएस", "订阅", ""),
    "delrss": ("", "удалить_rss", "rss_loeschen", "supprimer_rss", "حذف_rss", "आरएसएस_हटाएं", "删除订阅", ""),
    "addrss": ("", "добавить_rss", "rss_hinzufuegen", "ajouter_rss", "إضافة_rss", "आरएसएस_जोड़ें", "添加订阅", ""),
    "listrss": ("", "список_rss", "rss_liste", "liste_rss", "قائمة_rss", "आरएसएस_सूची", "订阅列表", ""),
    # --- cmd_study ---
    "study": ("", "учеба", "lernen", "etudier", "دراسة", "पढ़ाई", "学习", ""),
    # --- cmd_weather ---
    "addweather": ("", "добавить_погоду", "wetter_hinzufuegen", "ajouter_meteo", "إضافة_طقس", "मौसम_जोड़ें", "添加天气", ""),
    "delweather": ("", "удалить_погоду", "wetter_loeschen", "supprimer_meteo", "حذف_طقس", "मौसम_हटाएं", "删除天气", ""),
    "weather": ("", "погода", "wetter", "meteo", "طقس", "मौसम", "天气", ""),
    "weatherlist": ("", "список_погоды", "wetterliste", "liste_meteo", "قائمة_الطقس", "मौसम_सूची", "天气列表", ""),
    # --- cmd_filemanager ---
    "filemanager": ("", "файловый_менеджер", "dateimanager", "gestionnaire_fichiers", "مدير_الملفات", "फ़ाइल_प्रबंधक", "文件管理", ""),
    "cd": ("", "папка", "verzeichnis", "dossier", "مجلد", "फ़ोल्डर", "目录", ""),
    "back": ("", "назад", "zurueck", "retour", "رجوع", "वापस", "返回", ""),
    "catfile": ("", "показать_файл", "datei_anzeigen", "afficher_fichier", "عرض_ملف", "फ़ाइल_देखें", "查看文件", ""),
    "mkdir": ("", "создать_папку", "ordner_erstellen", "creer_dossier", "إنشاء_مجلد", "फ़ोल्डर_बनाएं", "新建文件夹", ""),
    "download": ("", "скачать", "herunterladen", "telecharger", "تنزيل", "डाउनलोड", "下载", ""),
    "upload": ("", "загрузить", "hochladen", "televerser", "رفع_ملف", "अपलोड", "上传", ""),
    "deletefile": ("", "удалить_файл", "datei_loeschen", "supprimer_fichier", "حذف_ملف", "फ़ाइल_हटाएं", "删除文件", ""),
    "renamefile": ("", "переименовать", "umbenennen", "renommer", "إعادة_تسمية", "नाम_बदलें", "重命名", ""),
    "movefile": ("", "переместить", "verschieben", "deplacer", "نقل", "स्थानांतरित", "移动", ""),
    "copyfile": ("", "копировать", "kopieren", "copier", "نسخ", "कॉपी", "复制", ""),
    "zip": ("", "сжать", "komprimieren", "compresser", "ضغط", "ज़िप", "压缩", ""),
    "unzip": ("", "распаковать", "entpacken", "decompresser", "فك_الضغط", "अनज़िप", "解压", ""),
    "tar": ("", "архив", "archiv", "archiver", "أرشفة", "आर्काइव", "打包", ""),
    "untar": ("", "извлечь_архив", "archiv_entpacken", "desarchiver", "فك_الأرشفة", "आर्काइव_खोलें", "解包", ""),
    # --- cmd_filemanager (baru) / cmd_filetools ---
    "trash": ("", "корзина", "papierkorb", "corbeille", "سلة_المهملات", "कचरा", "回收站", ""),
    "undelete": ("", "восстановить", "wiederherstellen", "restaurer", "استعادة", "पुनर्स्थापित", "恢复", ""),
    "fmroot": ("", "ограничить_папки", "ordnerlimit", "limite_dossier", "تقييد_المجلدات", "फ़ोल्डर_सीमा", "目录限制", ""),
    "audit": ("", "аудит", "pruefprotokoll", "journal_audit", "سجل_العمليات", "ऑडिट", "审计", ""),
    "find": ("", "найти", "finden", "trouver", "بحث_ملف", "ढूंढो", "查找", ""),
    "grep": ("", "искать_текст", "textsuche", "chercher_texte", "بحث_نص", "पाठ_खोज", "搜文本", ""),
    "tree": ("", "дерево", "baum", "arbre", "شجرة", "पेड़", "目录树", ""),
    "du": ("", "размер_папки", "ordnergroesse", "taille_dossier", "حجم_المجلد", "फ़ोल्डर_आकार", "目录大小", ""),
    "df": ("", "место_диска", "speicherplatz", "espace_disque", "مساحة_القرص", "डिस्क_स्थान", "磁盘空间", ""),
    "head": ("", "начало_файла", "dateianfang", "debut_fichier", "بداية_الملف", "फ़ाइल_शुरू", "文件开头", ""),
    "tail": ("", "конец_файла", "dateiende", "fin_fichier", "نهاية_الملف", "फ़ाइल_अंत", "文件结尾", ""),
    "hash": ("", "хеш", "pruefsumme", "empreinte", "بصمة", "हैश", "哈希", ""),
    "writefile": ("", "записать_файл", "datei_schreiben", "ecrire_fichier", "كتابة_ملف", "फ़ाइल_लिखें", "写文件", ""),
    "edit": ("", "правка", "bearbeiten", "modifier_fichier", "تعديل_ملف", "फ़ाइल_संपादित", "编辑文件", ""),
    "backup": ("", "резерв", "sicherung", "sauvegarde", "نسخ_احتياطي", "बैकअप", "备份", ""),
    "deploy": ("", "развернуть", "bereitstellen", "deployer", "نشر_إضافة", "प्लगइन_लगाएं", "部署", ""),
    "rollback": ("", "откат", "zuruecksetzen", "annuler_version", "تراجع", "वापसी", "回滚", ""),
    "inbox": ("", "входящие", "posteingang", "boite_reception", "الوارد", "इनबॉक्स", "收件箱", ""),
    # --- cmd_seen / cmd_tell / cmd_voice ---
    "seen": ("", "видел", "gesehen", "vu", "شوهد", "देखा", "最后在线", ""),
    "tell": ("", "передать", "ausrichten", "dire_a", "أبلغ", "संदेश_दो", "留言", ""),
    "untell": ("", "отменить_передачу", "ausrichten_abbrechen", "annuler_message", "إلغاء_إبلاغ", "संदेश_रद्द", "取消留言", ""),
    "transcribe": ("", "расшифровать", "transkribieren", "transcrire", "تفريغ", "ट्रांसक्राइब", "转写", ""),
    "voice": ("", "голос", "sprachnotiz", "voix", "صوت", "आवाज़", "语音", ""),
    # --- cmd_media / cmd_reload ---
    "tts": ("", "озвучить", "vorlesen", "parler", "نطق", "उच्चारण", "朗读", ""),
    "ttsreply": ("", "ответ_голосом", "sprachantwort", "reponse_vocale", "رد_صوتي", "आवाज़_उत्तर", "语音回复", ""),
    "gtts": ("", "г_озвучка", "g_vorlesen", "g_parler", "ع_نطق", "वै_उच्चारण", "全局朗读", ""),
    "image": ("", "картинка", "bild", "dessiner", "صورة", "चित्र_बनाओ", "画图", ""),
    "gimage": ("", "г_картинка", "g_bild", "g_dessiner", "ع_صورة", "वै_चित्र", "全局画图", ""),
    "reload": ("", "перезагрузить", "neuladen", "recharger", "إعادة_تحميل", "पुनः_लोड", "重载", ""),
    "gvoice": ("", "г_голос", "g_sprachnotiz", "g_voix", "ع_صوت", "वै_आवाज़", "全局语音", ""),
    # --- cmd_worldholiday ---
    "worldholiday": ("", "мировые_праздники", "weltfeiertage", "feries_monde", "عطلات_العالم", "विश्व_छुट्टी", "世界假期", ""),
    "holidayalert": ("", "напоминание_праздник", "feiertag_alarm", "alerte_ferie", "تنبيه_العطلة", "छुट्टी_अलर्ट", "假期提醒", ""),
}

# Bahasa tambahan: es, pt, pl, it, fa, tr, ua (Ukraina; "uk" juga diterima di perintah lang).
# Latin ditulis tanpa tanda diakritik agar mudah diketik di keyboard mana pun.
ORDER_EXTRA = ("es", "pt", "pl", "it", "fa", "tr", "ua")

EXTRA = {
    "lang": ("idioma", "idioma", "jezyk", "lingua", "زبان", "dil", "мова"),
    "uptime": ("tiempoactivo", "tempoativo", "czaspracy", "tempoattivo", "زمان_فعالیت", "calisma_suresi", "час_роботи"),
    "to_admin": ("aladmin", "aoadmin", "doadmina", "alladmin", "به_مدیر", "yoneticiye", "адміну"),
    "userslist": ("usuarios", "usuarios", "uzytkownicy", "utenti", "کاربران", "kullanicilar", "користувачі"),
    "disco": ("explorar", "explorar", "przegladaj", "esplora", "کاوش", "kesfet", "огляд"),
    "dns": ("", "", "", "", "دی_ان_اس", "", "днс"),
    "help": ("ayuda", "ajuda", "pomoc", "aiuto", "راهنما", "yardim", "допомога"),
    "next": ("siguiente", "proximo", "dalej", "avanti", "بعدی", "sonraki", "далі"),
    "ping": ("", "", "", "", "پینگ", "", "пінг"),
    "test": ("prueba", "teste", "testuj", "prova", "تست", "deneme", "тест"),
    "version": ("", "versao", "wersja", "versione", "نسخه", "surum", "версія"),
    "bookmark": ("marcadores", "favoritos", "zakladki", "segnalibri", "نشانک_ها", "yer_imleri", "закладки"),
    "botowner_add": ("anadir_duenobot", "adicionar_donobot", "dodaj_wlasciciela", "aggiungi_proprietariobot", "افزودن_مالک_ربات", "bot_sahibi_ekle", "додати_власника"),
    "botowner_del": ("quitar_duenobot", "remover_donobot", "usun_wlasciciela", "rimuovi_proprietariobot", "حذف_مالک_ربات", "bot_sahibi_sil", "видалити_власника"),
    "botowner_show": ("ver_duenosbot", "ver_donosbot", "pokaz_wlascicieli", "mostra_proprietaribot", "نمایش_مالکان", "bot_sahipleri", "показати_власників"),
    "global_msg": ("mensaje_global", "mensagem_global", "wiadomosc_globalna", "messaggio_globale", "پیام_سراسری", "genel_mesaj", "глобальне_повідомлення"),
    "join": ("unirse", "entrar", "dolacz", "unisciti", "پیوستن", "katil", "приєднатися"),
    "leave": ("salir", "sair", "opusc", "esci", "ترک", "ayril", "вийти"),
    "msg_to": ("enviar", "enviar", "wyslij", "invia", "ارسال", "gonder", "надіслати"),
    "restart": ("reiniciar", "reiniciar", "restartuj", "riavvia", "راه_اندازی_مجدد", "yeniden_baslat", "перезапустити"),
    "say": ("decir", "dizer", "powiedz", "dillo", "بگو", "soyle", "сказати"),
    "shutdown": ("apagar", "desligar", "wylacz", "spegni", "خاموش", "kapat", "вимкнути"),
    "startup": ("iniciar", "iniciar", "uruchom", "avvia", "روشن", "baslat", "запустити"),
    "statusbot_global": ("estado_global", "status_global", "status_globalny", "stato_globale", "وضعیت_سراسری", "genel_durum", "глобальний_статус"),
    "statusbot_here": ("estado_aqui", "status_aqui", "status_tutaj", "stato_qui", "وضعیت_اینجا", "durum_burada", "статус_тут"),
    "ai_off": ("ia_desactivar", "ia_desligar", "ai_wylacz", "ia_disattiva", "هوش_خاموش", "yz_kapat", "ші_вимкнути"),
    "ai_on": ("ia_activar", "ia_ligar", "ai_wlacz", "ia_attiva", "هوش_روشن", "yz_ac", "ші_увімкнути"),
    "ai_off_global": ("ia_desactivar_global", "ia_desligar_global", "ai_wylacz_globalnie", "ia_disattiva_globale", "هوش_خاموش_سراسری", "yz_kapat_genel", "ші_вимкнути_глобально"),
    "ai_on_global": ("ia_activar_global", "ia_ligar_global", "ai_wlacz_globalnie", "ia_attiva_globale", "هوش_روشن_سراسری", "yz_ac_genel", "ші_увімкнути_глобально"),
    "aiprovider": ("proveedor_ia", "provedor_ia", "dostawca_ai", "fornitore_ia", "ارائه_دهنده_هوش", "yz_saglayici", "провайдер_ші"),
    "aimodel": ("modelo_ia", "modelo_ia", "model_ai", "modello_ia", "مدل_هوش", "yz_modeli", "модель_ші"),
    "badword": ("palabrotas", "palavroes", "wulgaryzmy", "parolacce", "کلمات_بد", "kufur", "погані_слова"),
    "badnick": ("nick_prohibido", "nick_proibido", "zly_nick", "nick_vietato", "نام_ممنوع", "yasakli_nick", "погані_ніки"),
    "gbadword": ("g_palabrotas", "g_palavroes", "g_wulgaryzmy", "g_parolacce", "س_کلمات_بد", "g_kufur", "г_погані_слова"),
    "gbadnick": ("g_nick_prohibido", "g_nick_proibido", "g_zly_nick", "g_nick_vietato", "س_نام_ممنوع", "g_yasakli_nick", "г_погані_ніки"),
    "antiflood": ("antispam", "antispam", "antyflood", "antispam", "ضد_اسپم", "spam_korumasi", "антифлуд"),
    "www": ("paginaweb", "paginaweb", "stronawww", "paginaweb", "وب", "websitesi", "веб"),
    "trivia": ("preguntas", "perguntas", "kwiz", "quiz", "مسابقه", "bilgi_yarismasi", "вікторина"),
    "ans": ("respuesta", "resposta", "odpowiedz", "risposta", "پاسخ", "cevap", "відповідь"),
    "stoptrivia": ("parar_preguntas", "parar_perguntas", "stop_kwiz", "ferma_quiz", "توقف_مسابقه", "yarismayi_durdur", "зупинити_вікторину"),
    "guess": ("adivinar", "adivinhar", "zgaduj", "indovina", "حدس", "tahmin", "вгадай"),
    "roll": ("dado", "dado", "kostka", "dado", "تاس", "zar", "кубик"),
    "toss": ("moneda", "moeda", "moneta", "moneta", "سکه", "yazitura", "монетка"),
    "wordchain": ("cadena_palabras", "cadeia_palavras", "lancuch_slow", "catena_parole", "زنجیره_کلمات", "kelime_zinciri", "ланцюжок_слів"),
    "stopwordchain": ("parar_cadena", "parar_cadeia", "stop_lancuch", "ferma_catena", "توقف_زنجیره", "zinciri_durdur", "зупинити_ланцюжок"),
    "pet": ("mascota", "mascote", "zwierzak", "animaletto", "حیوان_خانگی", "evcil", "улюбленець"),
    "feed": ("alimentar", "alimentar", "karm", "nutrire", "غذا_دادن", "besle", "годувати"),
    "imgfilter": ("filtro_imagen", "filtro_imagem", "filtr_obrazow", "filtro_immagini", "فیلتر_تصویر", "gorsel_filtre", "фільтр_зображень"),
    "gimgfilter": ("g_filtro_imagen", "g_filtro_imagem", "g_filtr_obrazow", "g_filtro_immagini", "س_فیلتر_تصویر", "g_gorsel_filtre", "г_фільтр_зображень"),
    "tr": ("traducir", "traduzir", "tlumacz", "traduci", "ترجمه", "cevir", "перекласти"),
    "google": ("buscar", "buscar", "szukaj", "cerca_web", "جستجو", "google_ara", "пошук"),
    "maps": ("mapa", "mapa", "mapy", "mappa", "نقشه", "harita", "карта"),
    "youtube": ("video", "video", "film", "video", "یوتیوب", "video_ara", "ютуб"),
    "earthquake": ("terremoto", "terremoto", "trzesienie", "terremoto", "زلزله", "deprem", "землетрус"),
    "holiday": ("festivo", "feriado", "swieto", "festivita", "تعطیلات", "tatil", "свято"),
    "meme": ("", "", "", "", "میم", "", "мем"),
    "access": ("acceso", "acesso", "dostep", "accesso", "دسترسی", "erisim", "доступ"),
    "admin": ("administrador", "administrador", "administrator", "amministratore", "مدیر", "yonetici", "адмін"),
    "adminlist": ("lista_admins", "lista_admins", "lista_adminow", "lista_admin", "فهرست_مدیران", "yonetici_listesi", "список_адмінів"),
    "ban": ("banear", "banir", "banuj", "banna", "مسدود", "yasakla", "заблокувати"),
    "banlist": ("lista_baneados", "lista_banidos", "lista_banow", "lista_bannati", "فهرست_مسدودها", "yasak_listesi", "список_банів"),
    "kick": ("expulsar", "expulsar", "wyrzuc", "espelli", "اخراج", "disari_at", "викинути"),
    "member": ("miembro", "membro", "czlonek", "membro", "عضو", "uye", "учасник"),
    "memberlist": ("lista_miembros", "lista_membros", "lista_czlonkow", "lista_membri", "فهرست_اعضا", "uye_listesi", "список_учасників"),
    "moderator": ("moderador", "moderador", "", "moderatore", "ناظم", "", "модератор"),
    "nickbot": ("nick_bot", "nick_bot", "nick_bota", "nick_bot", "نام_ربات", "bot_adi", "нік_бота"),
    "owner": ("propietario", "proprietario", "wlasciciel", "proprietario", "مالک", "sahip", "власник"),
    "ownerlist": ("lista_propietarios", "lista_proprietarios", "lista_wlascicieli", "lista_proprietari", "فهرست_مالکان", "sahip_listesi", "список_власників"),
    "participant": ("participante", "participante", "uczestnik", "partecipante", "شرکت_کننده", "katilimci", "учасник_чату"),
    "prefix": ("prefijo", "prefixo", "prefiks", "prefisso", "پیشوند", "onek", "префікс"),
    "rejoin": ("reunirse", "reentrar", "dolacz_ponownie", "rientra", "ورود_دوباره", "tekrar_katil", "перепідключитися"),
    "unadmin": ("quitar_admin", "remover_admin", "usun_admina", "rimuovi_admin", "حذف_مدیر", "yonetici_al", "зняти_адміна"),
    "unowner": ("quitar_propietario", "remover_proprietario", "odbierz_wlasciciela", "rimuovi_proprietario", "حذف_مالک", "sahip_al", "зняти_власника"),
    "unban": ("desbanear", "desbanir", "odbanuj", "sbanna", "رفع_مسدودیت", "yasagi_kaldir", "розблокувати"),
    "unmember": ("quitar_miembro", "remover_membro", "usun_czlonka", "rimuovi_membro", "حذف_عضو", "uyelikten_cikar", "прибрати_учасника"),
    "visitor": ("visitante", "visitante", "gosc", "visitatore", "بازدیدکننده", "ziyaretci", "гість"),
    "rss": ("noticias", "noticias", "kanalrss", "notizie", "آر_اس_اس", "rss_haber", "rss_стрічка"),
    "delrss": ("borrar_rss", "remover_rss", "usun_rss", "rimuovi_rss", "حذف_rss", "rss_sil", "видалити_rss"),
    "addrss": ("agregar_rss", "adicionar_rss", "dodaj_rss", "aggiungi_rss", "افزودن_rss", "rss_ekle", "додати_rss"),
    "listrss": ("lista_rss", "lista_rss", "lista_rss", "lista_rss", "فهرست_rss", "rss_listesi", "список_rss"),
    "study": ("estudiar", "estudar", "nauka", "studiare", "مطالعه", "calisma", "навчання"),
    "addweather": ("agregar_clima", "adicionar_clima", "dodaj_pogode", "aggiungi_meteo", "افزودن_آب_و_هوا", "hava_ekle", "додати_погоду"),
    "delweather": ("borrar_clima", "remover_clima", "usun_pogode", "rimuovi_meteo", "حذف_آب_و_هوا", "hava_sil", "видалити_погоду"),
    "weather": ("clima", "clima", "pogoda", "meteo", "آب_و_هوا", "hava", "погода"),
    "weatherlist": ("lista_clima", "lista_clima", "lista_pogody", "lista_meteo", "فهرست_آب_و_هوا", "hava_listesi", "список_погоди"),
    "filemanager": ("gestor_archivos", "gerenciador_arquivos", "menedzer_plikow", "gestore_file", "مدیر_فایل", "dosya_yoneticisi", "файловий_менеджер"),
    "cd": ("carpeta", "pasta", "katalog", "cartella", "پوشه", "klasor", "тека"),
    "back": ("volver", "voltar", "wstecz", "indietro", "بازگشت", "geri", "назад"),
    "catfile": ("ver_archivo", "ver_arquivo", "pokaz_plik", "mostra_file", "نمایش_فایل", "dosya_goster", "показати_файл"),
    "mkdir": ("crear_carpeta", "criar_pasta", "utworz_katalog", "crea_cartella", "ایجاد_پوشه", "klasor_olustur", "створити_теку"),
    "download": ("descargar", "baixar", "pobierz", "scarica", "دانلود", "indir", "завантажити"),
    "upload": ("subir", "enviar_arquivo", "wgraj", "carica", "آپلود", "yukle", "вивантажити"),
    "deletefile": ("borrar_archivo", "apagar_arquivo", "usun_plik", "elimina_file", "حذف_فایل", "dosya_sil", "видалити_файл"),
    "renamefile": ("renombrar", "renomear", "zmien_nazwe", "rinomina", "تغییر_نام", "yeniden_adlandir", "перейменувати"),
    "movefile": ("mover", "mover", "przenies", "sposta", "انتقال_فایل", "tasi", "перемістити"),
    "copyfile": ("copiar", "copiar", "kopiuj", "copia", "کپی", "kopyala", "копіювати"),
    "zip": ("comprimir_zip", "comprimir_zip", "spakuj_zip", "comprimi_zip", "فشرده_سازی_zip", "zip_sikistir", "стиснути_zip"),
    "unzip": ("descomprimir_zip", "descompactar_zip", "rozpakuj_zip", "decomprimi_zip", "استخراج_zip", "zip_ac", "розпакувати_zip"),
    "tar": ("empaquetar_tar", "empacotar_tar", "spakuj_tar", "archivia_tar", "بسته_بندی_tar", "tar_paketle", "запакувати_tar"),
    "untar": ("desempaquetar_tar", "desempacotar_tar", "rozpakuj_tar", "estrai_tar", "استخراج_tar", "tar_ac", "розпакувати_tar"),
    "trash": ("papelera", "lixeira", "kosz", "cestino", "سطل_زباله", "cop_kutusu", "кошик"),
    "undelete": ("restaurar", "restaurar", "przywroc", "ripristina", "بازیابی", "geri_yukle", "відновити"),
    "fmroot": ("limite_carpeta", "limite_pasta", "limit_katalogow", "limite_cartelle", "محدودیت_پوشه", "klasor_siniri", "обмеження_тек"),
    "audit": ("auditoria", "auditoria", "audyt", "registro_audit", "ممیزی", "denetim", "аудит"),
    "find": ("buscar_archivo", "achar", "znajdz", "trova", "یافتن", "bul", "знайти"),
    "grep": ("buscar_texto", "procurar_texto", "szukaj_tekstu", "cerca_testo", "جستجوی_متن", "metin_ara", "шукати_текст"),
    "tree": ("arbol", "arvore", "drzewo", "albero", "درخت", "agac", "дерево"),
    "du": ("tamano_carpeta", "tamanho_pasta", "rozmiar_katalogu", "dimensione_cartella", "حجم_پوشه", "klasor_boyutu", "розмір_теки"),
    "df": ("espacio_disco", "espaco_disco", "miejsce_dysku", "spazio_disco", "فضای_دیسک", "disk_alani", "місце_диска"),
    "head": ("inicio_archivo", "inicio_arquivo", "poczatek_pliku", "inizio_file", "ابتدای_فایل", "dosya_basi", "початок_файлу"),
    "tail": ("final_archivo", "fim_arquivo", "koniec_pliku", "fine_file", "انتهای_فایل", "dosya_sonu", "кінець_файлу"),
    "hash": ("huella", "impressao", "skrot", "impronta", "هش", "ozet", "хеш"),
    "writefile": ("escribir_archivo", "escrever_arquivo", "zapisz_plik", "scrivi_file", "نوشتن_فایل", "dosya_yaz", "записати_файл"),
    "edit": ("editar_archivo", "editar_arquivo", "edytuj_plik", "modifica_file", "ویرایش_فایل", "dosya_duzenle", "редагувати_файл"),
    "backup": ("respaldo", "copia_seguranca", "kopia_zapasowa", "copia_sicurezza", "پشتیبان", "yedek", "резерв_копія"),
    "deploy": ("desplegar", "implantar", "wdroz", "distribuisci", "استقرار", "dagit", "розгорнути"),
    "rollback": ("revertir", "reverter", "cofnij", "ripristina_versione", "بازگشت_نسخه", "geri_al", "відкат"),
    "inbox": ("bandeja", "caixa_entrada", "skrzynka", "posta_arrivo", "صندوق_ورودی", "gelen_kutusu", "вхідні"),
    "seen": ("visto", "visto", "widziany", "visto", "دیده_شد", "son_gorulme", "бачили"),
    "tell": ("avisar", "avisar", "powiedz_im", "riferisci", "بگو_به", "ilet", "передати"),
    "untell": ("cancelar_aviso", "cancelar_aviso", "anuluj_przekaz", "annulla_messaggio", "لغو_پیام", "iletiyi_iptal", "скасувати_передачу"),
    "transcribe": ("transcribir", "transcrever", "transkrybuj", "trascrivi", "رونویسی", "yaziya_dok", "розшифрувати"),
    "voice": ("voz", "voz", "glos", "voce", "صدا", "ses", "голос"),
    "tts": ("hablar", "falar", "mow", "parla", "گفتار", "seslendir", "озвучити"),
    "ttsreply": ("respuesta_voz", "resposta_voz", "odpowiedz_glosowa", "risposta_vocale", "پاسخ_صوتی", "sesli_yanit", "голосова_відповідь"),
    "gtts": ("g_hablar", "g_falar", "g_mow", "g_parla", "س_گفتار", "g_seslendir", "г_озвучити"),
    "image": ("dibujar", "desenhar", "rysuj", "disegna", "تصویر_بساز", "resimyap", "малюнок"),
    "gimage": ("g_dibujar", "g_desenhar", "g_rysuj", "g_disegna", "س_تصویر", "g_resimyap", "г_малюнок"),
    "reload": ("recargar", "recarregar", "przeladuj", "ricarica", "بارگذاری_مجدد", "yeniden_yukle", "перезавантажити"),
    "gvoice": ("g_voz", "g_voz", "g_glos", "g_voce", "س_صدا", "g_ses", "г_голос"),
    "worldholiday": ("festivos_mundo", "feriados_mundo", "swieta_swiat", "festivita_mondo", "تعطیلات_جهانی", "dunya_tatilleri", "світові_свята"),
    "holidayalert": ("alerta_festivo", "alerta_feriado", "alert_swieta", "avviso_festivita", "هشدار_تعطیلات", "tatil_uyarisi", "сповіщення_свята"),
    "alias": ("atajo", "atalho", "zamiennik", "scorciatoia", "نام_مستعار", "takma_ad", "псевдонім"),
    "galias": ("g_atajo", "g_atalho", "g_zamiennik", "g_scorciatoia", "س_نام_مستعار", "g_takma_ad", "г_псевдонім"),
}

LANG_EXTRA_OK = {
    "es": "✅ Idioma cambiado a Español (es).",
    "pt": "✅ Idioma alterado para Português (pt).",
    "pl": "✅ Język zmieniono na polski (pl).",
    "it": "✅ Lingua cambiata in Italiano (it).",
    "fa": "✅ زبان به فارسی (fa) تغییر کرد.",
    "tr": "✅ Dil Türkçe (tr) olarak değiştirildi.",
    "ua": "✅ Мову змінено на українську (ua).",
}
LANG_CODE_ALIAS = {"uk": "ua"}

# Perintah yang nama aslinya berbahasa Indonesia: nama tampilan untuk room berbahasa Inggris.
ALIASES_EN = {"image": "", "gimage": ""}

# ----------------------------------------------------------------------
# Terjemahan kata-kata bantuan (placeholder) di deskripsi perintah, misal
# "disco <server/muc> [page/filter]" -> "обзор <сервер/muc> [страница/фильтр]".
# Kata yang tidak ada di kamus ini dibiarkan apa adanya (aman diisi bertahap).
# Tambah kata baru: tulis satu baris, urutan kolom = PH_ORDER.
# ----------------------------------------------------------------------
PH_ORDER = ("id", "ru", "de", "fr", "ar", "hi", "zh", "jv", "es", "pt", "pl", "it", "fa", "tr", "ua")

PH_RAW = {
    "nick": ("nick", "ник", "nick", "pseudo", "الاسم", "उपनाम", "昵称", "jeneng", "apodo", "apelido", "pseudonim", "soprannome", "نام", "takma_ad", "нік"),
    "server": ("server", "сервер", "server", "serveur", "الخادم", "सर्वर", "服务器", "server", "servidor", "servidor", "serwer", "server", "سرور", "sunucu", "сервер"),
    "page": ("halaman", "страница", "seite", "page", "صفحة", "पृष्ठ", "页", "kaca", "pagina", "pagina", "strona", "pagina", "صفحه", "sayfa", "сторінка"),
    "page number": ("nomor_halaman", "номер_страницы", "seitenzahl", "numero_page", "رقم_الصفحة", "पृष्ठ_संख्या", "页码", "nomer_kaca", "numero_pagina", "numero_pagina", "numer_strony", "numero_pagina", "شماره_صفحه", "sayfa_no", "номер_сторінки"),
    "filter": ("filter", "фильтр", "filter", "filtre", "تصفية", "फ़िल्टर", "过滤", "saring", "filtro", "filtro", "filtr", "filtro", "فیلتر", "filtre", "фільтр"),
    "message": ("pesan", "сообщение", "nachricht", "message", "رسالة", "संदेश", "消息", "pesen", "mensaje", "mensagem", "wiadomosc", "messaggio", "پیام", "mesaj", "повідомлення"),
    "city": ("kota", "город", "stadt", "ville", "مدينة", "शहर", "城市", "kutha", "ciudad", "cidade", "miasto", "citta", "شهر", "sehir", "місто"),
    "area": ("wilayah", "район", "gebiet", "zone", "منطقة", "क्षेत्र", "地区", "wilayah", "zona", "area", "obszar", "zona", "منطقه", "bolge", "район"),
    "text": ("teks", "текст", "text", "texte", "نص", "पाठ", "文本", "teks", "texto", "texto", "tekst", "testo", "متن", "metin", "текст"),
    "keywords": ("kata_kunci", "ключевые_слова", "stichwort", "mots_cles", "كلمات_البحث", "खोज_शब्द", "关键词", "tembung_kunci", "palabras", "palavras", "slowa", "parole", "کلمات", "anahtar", "ключові_слова"),
    "place_name": ("nama_tempat", "название_места", "ortsname", "nom_lieu", "اسم_المكان", "स्थान_नाम", "地名", "jeneng_panggonan", "lugar", "lugar", "miejsce", "luogo", "مکان", "yer_adi", "місце"),
    "video_title": ("judul_video", "название_видео", "videotitel", "titre_video", "عنوان_الفيديو", "वीडियो_शीर्षक", "视频标题", "judhul_vidio", "titulo_video", "titulo_video", "tytul_filmu", "titolo_video", "عنوان_ویدیو", "video_basligi", "назва_відео"),
    "language_code": ("kode_bahasa", "код_языка", "sprachcode", "code_langue", "رمز_اللغة", "भाषा_कोड", "语言代码", "kode_basa", "codigo_idioma", "codigo_idioma", "kod_jezyka", "codice_lingua", "کد_زبان", "dil_kodu", "код_мови"),
    "number": ("angka", "число", "zahl", "nombre", "رقم", "संख्या", "数字", "angka", "numero", "numero", "liczba", "numero", "عدد", "sayi", "число"),
    "answer": ("jawaban", "ответ", "antwort", "reponse", "الإجابة", "उत्तर", "答案", "wangsulan", "respuesta", "resposta", "odpowiedz", "risposta", "پاسخ", "cevap", "відповідь"),
    "say": ("kata", "слово", "wort", "mot", "كلمة", "शब्द", "词", "tembung", "palabra", "palavra", "slowo", "parola", "کلمه", "kelime", "слово"),
    "symbol": ("simbol", "символ", "symbol", "symbole", "رمز", "प्रतीक", "符号", "simbol", "simbolo", "simbolo", "symbol", "simbolo", "نماد", "sembol", "символ"),
    "bot-name": ("nama_bot", "имя_бота", "botname", "nom_bot", "اسم_البوت", "बॉट_नाम", "机器人名", "jeneng_bot", "nombre_bot", "nome_bot", "nazwa_bota", "nome_bot", "نام_ربات", "bot_adi", "імя_бота"),
    "command": ("perintah", "команда", "befehl", "commande", "أمر", "कमान्ड", "命令", "prentah", "comando", "comando", "polecenie", "comando", "دستور", "komut", "команда"),
    "category": ("kategori", "категория", "kategorie", "categorie", "الفئة", "श्रेणी", "类别", "kategori", "categoria", "categoria", "kategoria", "categoria", "دسته", "kategori", "категорія"),
    "question": ("pertanyaan", "вопрос", "frage", "question", "سؤال", "प्रश्न", "问题", "pitakon", "pregunta", "pergunta", "pytanie", "domanda", "سوال", "soru", "питання"),
    "reason": ("alasan", "причина", "grund", "raison", "السبب", "कारण", "原因", "alesan", "razon", "motivo", "powod", "motivo", "دلیل", "neden", "причина"),
    "name_file": ("nama_file", "имя_файла", "dateiname", "nom_fichier", "اسم_الملف", "फ़ाइल_नाम", "文件名", "jeneng_berkas", "nombre_archivo", "nome_arquivo", "nazwa_pliku", "nome_file", "نام_فایل", "dosya_adi", "імя_файлу"),
    "name_output": ("nama_output", "имя_вывода", "ausgabename", "nom_sortie", "اسم_الإخراج", "आउटपुट_नाम", "输出名", "jeneng_output", "nombre_salida", "nome_saida", "nazwa_wyjscia", "nome_output", "نام_خروجی", "cikti_adi", "імя_виводу"),
    "old_name": ("nama_lama", "старое_имя", "alter_name", "ancien_nom", "الاسم_القديم", "पुराना_नाम", "旧名称", "jeneng_lawas", "nombre_antiguo", "nome_antigo", "stara_nazwa", "vecchio_nome", "نام_قدیم", "eski_ad", "стара_назва"),
    "new_name": ("nama_baru", "новое_имя", "neuer_name", "nouveau_nom", "الاسم_الجديد", "नया_नाम", "新名称", "jeneng_anyar", "nombre_nuevo", "nome_novo", "nowa_nazwa", "nuovo_nome", "نام_جدید", "yeni_ad", "нова_назва"),
    "file": ("file", "файл", "datei", "fichier", "الملف", "फ़ाइल", "文件", "berkas", "archivo", "arquivo", "plik", "file", "فایل", "dosya", "файл"),
    "source": ("sumber", "источник", "quelle", "source", "المصدر", "स्रोत", "源", "sumber", "origen", "origem", "zrodlo", "origine", "مبدا", "kaynak", "джерело"),
    "destination_folder": ("folder_tujuan", "папка_назначения", "zielordner", "dossier_destination", "مجلد_الوجهة", "गंतव्य_फ़ोल्डर", "目标文件夹", "folder_tujuan", "carpeta_destino", "pasta_destino", "folder_docelowy", "cartella_destinazione", "پوشه_مقصد", "hedef_klasor", "цільова_тека"),
    "target": ("target", "цель", "ziel", "cible", "الهدف", "लक्ष्य", "目标", "target", "objetivo", "alvo", "cel", "bersaglio", "هدف", "hedef", "ціль"),
    "path": ("jalur", "путь", "pfad", "chemin", "المسار", "पथ", "路径", "dalan", "ruta", "caminho", "sciezka", "percorso", "مسیر", "yol", "шлях"),
    "path_folder": ("jalur_folder", "путь_папки", "ordnerpfad", "chemin_dossier", "مسار_المجلد", "फ़ोल्डर_पथ", "文件夹路径", "dalan_folder", "ruta_carpeta", "caminho_pasta", "sciezka_katalogu", "percorso_cartella", "مسیر_پوشه", "klasor_yolu", "шлях_теки"),
    "pattern": ("pola", "шаблон", "muster", "motif", "نمط", "पैटर्न", "模式", "pola", "patron", "padrao", "wzorzec", "modello", "الگو", "desen", "шаблон"),
    "folder": ("folder", "папка", "ordner", "dossier", "مجلد", "फ़ोल्डर", "文件夹", "folder", "carpeta", "pasta", "katalog", "cartella", "پوشه", "klasor", "тека"),
    "count": ("jumlah", "число", "anzahl", "nombre", "العدد", "संख्या", "数量", "jumlah", "cantidad", "quantidade", "liczba", "numero", "تعداد", "adet", "кількість"),
    "depth": ("kedalaman", "глубина", "tiefe", "profondeur", "العمق", "गहराई", "深度", "jero", "profundidad", "profundidade", "glebokosc", "profondita", "عمق", "derinlik", "глибина"),
    "lines": ("baris", "строки", "zeilen", "lignes", "الأسطر", "पंक्तियाँ", "行数", "baris", "lineas", "linhas", "linie", "righe", "خطوط", "satir", "рядки"),
    "url": ("url", "url", "url", "url", "الرابط", "यूआरएल", "链接", "url", "url", "url", "url", "url", "نشانی", "url", "url"),
    "name": ("nama", "имя", "name", "nom", "الاسم", "नाम", "名称", "jeneng", "nombre", "nome", "nazwa", "nome", "نام", "ad", "назва"),
    "description": ("deskripsi", "описание", "beschreibung", "description", "وصف", "विवरण", "描述", "katrangan", "descripcion", "descricao", "opis", "descrizione", "توضیح", "aciklama", "опис"),
    "plugin": ("plugin", "плагин", "plugin", "plugin", "الإضافة", "प्लगइन", "插件", "plugin", "plugin", "plugin", "wtyczka", "plugin", "افزونه", "eklenti", "плагін"),
    "atau": ("atau", "или", "oder", "ou", "أو", "या", "或", "utawa", "o", "ou", "lub", "o", "یا", "veya", "або"),
    "audio-url": ("url_audio", "url_аудио", "audio_url", "url_audio", "رابط_الصوت", "ऑडियो_url", "音频链接", "url_audio", "url_audio", "url_audio", "url_audio", "url_audio", "نشانی_صوت", "ses_url", "url_аудіо"),
    "country": ("negara", "страна", "land", "pays", "الدولة", "देश", "国家", "negara", "pais", "pais", "kraj", "paese", "کشور", "ulke", "країна"),
    "month": ("bulan", "месяц", "monat", "mois", "الشهر", "महीना", "月份", "sasi", "mes", "mes", "miesiac", "mese", "ماه", "ay", "місяць"),
    "year": ("tahun", "год", "jahr", "annee", "السنة", "वर्ष", "年份", "taun", "ano", "ano", "rok", "anno", "سال", "yil", "рік"),
}
PH = {k: dict(zip(PH_ORDER, v)) for k, v in PH_RAW.items()}
# nama lain untuk kata yang sama (yang muncul di docstring plugin)
for _alias, _base in (("lang_code", "language_code"), ("message content", "message"), ("isi pesan", "message"),
                      ("region name", "area"), ("or", "atau"), ("file name", "name_file")):
    PH[_alias] = PH[_base]


def _ph(word, lang):
    """Terjemahkan satu kata placeholder; 'name_output.zip' -> kata + ekstensi tetap."""
    key = word.strip().lower()
    if key in PH:
        return PH[key].get(lang, word)
    if "." in key:
        left, right = key.split(".", 1)
        if left in PH:
            return PH[left].get(lang, left) + "." + right
    return word


def localize_desc(desc, lang, by_lang):
    """Lokalkan deskripsi perintah untuk tampilan help: nama perintah + kata di dalam <...> dan [...]."""
    if not desc:
        return desc
    desc = re.sub(r"^\s*Example commands?:+\s*", "", desc, flags=re.I)   # buang awalan 'Example command:'
    if lang != "en":
        desc = re.sub(r"([<\[])([^<>\[\]]+)([>\]])",
                      lambda m: m.group(1) + "/".join(_ph(x, lang) for x in m.group(2).split("/")) + m.group(3), desc)
        desc = re.sub(r"\b(atau|or)\b", lambda m: PH["atau"].get(lang, m.group(0)), desc)
    head, _, rest = desc.partition(" ")
    names = by_lang.get(head.split("/")[0], {}).get(lang)
    if names:
        head = names[0]
    return (head + " " + rest).strip()


class AliasLookup(dict):
    """dict biasa, tetapi items() hanya memuat nama asli (alias disembunyikan dari prompt AI di cmd_ai)."""
    def items(self):
        return [(k, v) for k, v in dict.items(self) if getattr(v, "cmd_name", k) == k]


def register(bot):
    lookup = AliasLookup(bot.COMMAND_LOOKUP)
    bot.COMMAND_LOOKUP = lookup
    by_lang = {}   # nama_asli -> {kode_bahasa: [alias...]}

    # 1) Daftarkan semua alias ke tabel perintah
    for name, cols in ALIASES.items():
        func = lookup.get(name)
        if func is None:
            continue  # plugin pemilik perintah ini tidak dimuat
        added, langs = [], {}
        cols = tuple(cols) + EXTRA.get(name, ("",) * len(ORDER_EXTRA))
        pairs = list(zip(ORDER + ORDER_EXTRA, cols)) + [("en", ALIASES_EN.get(name, ""))]
        for code, cell in pairs:
            for alias in cell.lower().split():
                current = lookup.get(alias)
                if current is func:
                    langs.setdefault(code, []).append(alias)
                    continue
                if current is not None:
                    print(f"[zz_aliases] alias '{alias}' untuk '{name}' bentrok dengan perintah lain, dilewati")
                    continue
                langs.setdefault(code, []).append(alias)
                lookup[alias] = func
                added.append(alias)
        by_lang[name] = langs
        if added:
            func.cmd_aliases = list(getattr(func, "cmd_aliases", [])) + added
    missing = sorted({getattr(f, "cmd_name", k) for k, f in dict.items(lookup)
                      if getattr(f, "cmd_name", k) == k} - set(ALIASES))
    if missing:
        print(f"[zz_aliases] perintah tanpa entri alias: {', '.join(missing)}")
    bot.CMD_ALIASES = by_lang

    # alias (termasuk alias lama seperti 'blokir') -> nama asli
    to_canon = {k: v.cmd_name for k, v in dict.items(lookup) if getattr(v, "cmd_name", k) != k}

    # 2) handle_command: ubah alias menjadi nama asli SEBELUM cek owner/moderator & prefix
    orig_handle = bot.handle_command

    def canon_body(body, room):
        cur = (bot.get_room_nick(room) if room else getattr(bot, "global_default_nick", "")) or ""
        pos = 0
        if cur and body.startswith(cur):
            pos = len(cur)
            while pos < len(body) and body[pos] in " ,:":
                pos += 1
        prefix = bot.get_room_prefix(room) if room else ""
        if prefix and body.startswith(prefix, pos):
            pos += len(prefix)
        while pos < len(body) and body[pos].isspace():
            pos += 1
        m = re.match(r"\S+", body[pos:])
        if not m:
            return body
        canon = to_canon.get(m.group(0).lower())
        if not canon:
            return body
        return body[:pos] + canon + body[pos + len(m.group(0)):]

    async def handle_command(body, sender, room, nick, is_private):
        try:
            body = canon_body(body, room)
        except Exception:
            pass
        return await orig_handle(body, sender, room, nick, is_private)

    bot.handle_command = handle_command

    # 3) help: tampilkan nama perintah sesuai bahasa room
    orig_help = lookup.get("help")
    if orig_help is not None:
        def localized_registry(lang):
            reg = {}
            for cat, entries in bot.COMMAND_REGISTRY.items():
                new = []
                for syntax, desc in entries:
                    canon = syntax.split("/")[0].split()[0] if syntax else syntax
                    lst = by_lang.get(canon, {}).get(lang)
                    new.append((" / ".join(lst) + " / " + syntax if lst else syntax,
                                localize_desc(desc, lang, by_lang)))
                reg[cat] = new
            return reg


        NO_PREFIX = {"id": "(Tanpa Prefix)", "en": "(No Prefix)", "ru": "(без префикса)", "de": "(Kein Präfix)",
                     "fr": "(Sans préfixe)", "ar": "(بدون بادئة)", "hi": "(बिना उपसर्ग)", "zh": "(无前缀)",
                     "jv": "(Tanpa Awalan)",
                     "es": "(Sin prefijo)", "pt": "(Sem prefixo)", "pl": "(Bez prefiksu)", "it": "(Senza prefisso)",
                     "fa": "(بدون پیشوند)", "tr": "(Önek yok)", "ua": "(Без префікса)"}
        LANG_CODES = "/".join(("id", "en", "ru", "de", "fr", "ar", "hi", "zh", "jv", "es", "pt", "pl", "it", "fa", "tr", "ua"))

        def disp(cmd, lang):
            lst = by_lang.get(cmd, {}).get(lang)
            return lst[0] if lst else cmd

        def localize_help_text(text, lang):
            """Terjemahkan sisa teks bawaan help: '(Tanpa Prefix)', nama perintah help/lang, daftar kode bahasa."""
            np_text = NO_PREFIX.get(lang, NO_PREFIX["en"])
            text = text.replace("(Tanpa Prefix)", np_text).replace("(No Prefix)", np_text)
            if lang == "en":
                return re.sub(r"`lang <[^>`]*>`", "`lang <%s>`" % LANG_CODES, text)
            d_help, d_lang = disp("help", lang), disp("lang", lang)
            text = re.sub(r"`lang\b", "`" + d_lang, text)
            text = re.sub(r"`help\b", "`" + d_help, text)
            return re.sub(r"`%s <[^>`]*>`" % re.escape(d_lang), "`%s <%s>`" % (d_lang, LANG_CODES), text)

        async def help_wrapper(sender, room, nick, is_private, args):
            lang = str(bot.get_lang(sender, room) or "id").lower()
            args = list(args or [])
            if args:
                args[0] = to_canon.get(args[0].lower(), args[0])   # help пинг -> help ping
            saved = bot.COMMAND_REGISTRY
            had_own = "reply_user" in bot.__dict__
            saved_reply = bot.__dict__.get("reply_user")
            base_reply = bot.reply_user

            async def reply(s_, r_, text, is_private_, nick=None):
                return await base_reply(s_, r_, localize_help_text(text, lang), is_private_, nick=nick)

            try:
                bot.COMMAND_REGISTRY = localized_registry(lang)
                bot.reply_user = reply
                return await orig_help(sender, room, nick, is_private, args)
            finally:
                bot.COMMAND_REGISTRY = saved
                if had_own:
                    bot.reply_user = saved_reply
                else:
                    bot.__dict__.pop("reply_user", None)

        for attr in ("is_command", "cmd_name", "cmd_aliases", "category", "description"):
            if hasattr(orig_help, attr):
                setattr(help_wrapper, attr, getattr(orig_help, attr))
        help_wrapper.__doc__ = orig_help.__doc__
        for k, v in list(dict.items(lookup)):
            if v is orig_help:
                lookup[k] = help_wrapper

