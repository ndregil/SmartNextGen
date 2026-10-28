# -*- coding: utf-8 -*-
# Smart Next-Gen XMPP Bot
# Copyright © 2026 Ndregil
# https://ndregil.eu.org
# admin@ndregil.eu.org


import os

STUDY_DATA = {
    "python": {
        "id": [
            "1. Pengenalan: Python adalah bahasa pemrograman interpreter tingkat tinggi yang mudah dibaca dan dipelajari.",
            "2. Variabel & Tipe Data: Menyimpan nilai menggunakan variabel (contoh: x = 10, nama = 'Budi'). Tipe data umum: int, float, str, bool.",
            "3. Percabangan: Menggunakan if, elif, dan else untuk membuat keputusan logika dalam kode program."
        ],
        "en": [
            "1. Introduction: Python is a high-level interpreted programming language that is easy to read and learn.",
            "2. Variables & Data Types: Store values using variables (e.g., x = 10, name = 'John'). Common types: int, float, str, bool.",
            "3. Branching: Use if, elif, and else statements to make logical decisions in program code."
        ]
    },
    "kotlin": {
        "id": [
            "1. Pengenalan: Kotlin adalah bahasa pemrograman modern yang berjalan di atas JVM (Java Virtual Machine) dan resmi untuk Android.",
            "2. Variabel: Menggunakan 'val' untuk variabel konstan (immutable) dan 'var' untuk variabel yang bisa diubah (mutable).",
            "3. Fungsi: Didefinisikan menggunakan kata kunci 'fun', contoh: fun main() { println('Halo Kotlin') }"
        ],
        "en": [
            "1. Introduction: Kotlin is a modern programming language that runs on the JVM and is official for Android.",
            "2. Variables: Use 'val' for constants (immutable) and 'var' for variables that can be changed (mutable).",
            "3. Functions: Defined using the 'fun' keyword, e.g., fun main() { println('Hello Kotlin') }"
        ]
    },
    "java": {
        "id": [
            "1. Pengenalan: Java adalah bahasa pemrograman berbasis objek (OOP) yang bersifat 'Write Once, Run Anywhere'.",
            "2. Struktur Dasar: Setiap program Java wajib memiliki sebuah kelas (class) dan fungsi utama public static void main(String[] args).",
            "3. Tipe Data: Mengenal tipe data primitif seperti int, double, char, dan boolean."
        ],
        "en": [
            "1. Introduction: Java is an object-oriented programming (OOP) language characterized by 'Write Once, Run Anywhere'.",
            "2. Basic Structure: Every Java program requires a class and a main method public static void main(String[] args).",
            "3. Data Types: Explore primitive data types such as int, double, char, and boolean."
        ]
    },
    "matematika": {
        "id": [
            "1. Aljabar Dasar: Menyelesaikan persamaan linear satu variabel, contoh: 2x + 5 = 15, maka x = 5.",
            "2. Geometri: Rumus luas lingkaran adalah L = pi * r^2, dan keliling lingkaran adalah K = 2 * pi * r.",
            "3. Pecahan: Operasi hitung penjumlahan, pengurangan, perkalian, dan pembagian pada bilangan pecahan."
        ],
        "en": [
            "1. Basic Algebra: Solving single-variable linear equations, e.g., 2x + 5 = 15, so x = 5.",
            "2. Geometry: The area of a circle is A = pi * r^2, and its circumference is C = 2 * pi * r.",
            "3. Fractions: Arithmetic operations of addition, subtraction, multiplication, and division with fractions."
        ]
    },
    "sains": {
        "id": [
            "1. Tata Surya: Matahari adalah pusat tata surya. Planet terdekat adalah Merkurius, dan yang terbesar adalah Jupiter.",
            "2. Fotosintesis: Proses tumbuhan hijau mengubah air, karbondioksida, dan cahaya matahari menjadi oksigen dan glukosa.",
            "3. Wujud Benda: Tiga wujud utama benda adalah padat, cair, dan gas beserta perubahan wujudnya (mencair, menguap, menyublim)."
        ],
        "en": [
            "1. Solar System: The Sun is the center of the solar system. The closest planet is Mercury, and the largest is Jupiter.",
            "2. Photosynthesis: The process by which green plants convert water, carbon dioxide, and sunlight into oxygen and glucose.",
            "3. States of Matter: The three main states of matter are solid, liquid, and gas, along with phase transitions."
        ]
    },
    "inggris": {
        "id": [
            "1. Greeting & Introduction: Ungkapan menyapa seperti 'Good morning', 'How are you?', dan cara memperkenalkan diri.",
            "2. Simple Present Tense: Digunakan untuk menyatakan kebiasaan atau fakta umum (Contoh: 'I go to school every day').",
            "3. Pronouns: Kata ganti orang seperti I, You, They, We, He, She, It beserta kepemilikannya (my, your, their, dll)."
        ],
        "en": [
            "1. Greeting & Introduction: Expressions like 'Good morning', 'How are you?', and how to introduce yourself.",
            "2. Simple Present Tense: Used to express habits or general facts (Example: 'I go to school every day').",
            "3. Pronouns: Personal pronouns like I, You, They, We, He, She, It along with possessives (my, your, their, etc)."
        ]
    }
}

def register(bot):
    plugin_name = os.path.splitext(os.path.basename(__file__))[0]
    LANG_MESSAGES = bot.load_plugin_messages(plugin_name)

    def get_lang(sender, room):
        """Mengambil bahasa aktif secara sinkron langsung dari database/sistem inti bot."""
        if hasattr(bot, "get_lang"):
            return bot.get_lang(sender, room)
        if not hasattr(bot, "user_languages"):
            bot.user_languages = {}
        key = room if room else str(sender)
        return bot.user_languages.get(key, "id")

    def get_m(lang):
        """Helper untuk mengambil kamus bahasa dengan fallback aman ke 'id'."""
        return LANG_MESSAGES.get(lang, LANG_MESSAGES.get("id", {}))

    @bot.command("study", "👤 Participant & Member", aliases=["belajar"])
    async def cmd_study(sender, room, nick, is_private, args):
        """study <category> [question]"""
        lang = get_lang(sender, room)
        m = get_m(lang)
        valid_categories = list(STUDY_DATA.keys())
        
        if not args:
            cat_list = ", ".join(valid_categories)
            guide_text = m.get("guide_text").format(cat_list=cat_list)
            await bot.reply_user(sender, room, guide_text, is_private, nick=nick)
            return

        category = args[0].lower()

        if category not in valid_categories:
            cat_list = ", ".join(valid_categories)
            err_cat = m.get("err_category").format(category=category, cat_list=cat_list)
            await bot.reply_user(sender, room, err_cat, is_private, nick=nick)
            return

        question = " ".join(args[1:]).strip()
        cat_upper = category.upper()

        if not question:
            materi_list = m.get(f"study_{category}") or STUDY_DATA[category].get(lang, STUDY_DATA[category]["id"])
            materi_text = m.get("materi_header").format(category=cat_upper) + "\n".join(materi_list)
            materi_text += m.get("materi_tip").format(category=category)
            await bot.reply_user(sender, room, materi_text, is_private, nick=nick)
            return

        loading_txt = m.get("loading_text").format(category=cat_upper)
        await bot.reply_user(sender, room, loading_txt, is_private, nick=nick)

        prompt = m.get("ai_prompt").format(category=cat_upper, question=question)

        if hasattr(bot, "ask_ai_with_fallback"):
            ai_response = await bot.ask_ai_with_fallback(prompt, room=room)
            formatted_reply = m.get("ai_reply_header").format(category=cat_upper, ai_response=ai_response)
            await bot.reply_user(sender, room, formatted_reply, is_private, nick=nick)
        else:
            err_ai = m.get("err_ai")
            await bot.reply_user(sender, room, err_ai, is_private, nick=nick)
