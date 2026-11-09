"""Institutning akademik qoidalari — yagona manba.

Manba: «O'quv jarayoni va akademik qoidalar bilan tanishuv» taqdimoti (ISFT, kunduzgi ta'lim).
Hujjatlar (transkript, yakuniy nazorat qaydnomasi, ogohlantirish xati), Talabalar markazi qoidalari,
xavf modeli va ISFT Core agenti baholash shkalasini shu yerdan oladi — raqamlar bir joyda turadi."""
import random

SOURCE = "O'quv jarayoni va akademik qoidalar taqdimoti"

# ---------------- baholash (100 ballik → 5 baho → ECTS harfi) ----------------
PASS = 40                          # fanni o'zlashtirish uchun kamida 40 ball = «3»
ORALIQ_MAX, ORALIQ_MIN = 30, 12    # oraliq nazorat
YAKUNIY_MAX, YAKUNIY_MIN = 70, 28  # yakuniy nazorat
ADMIT_PCT = 40                     # yakuniy nazoratga kirish: oraliqdan kamida 40% (12 / 30 ball)

# (quyi chegara, yuqori chegara, harf, 5 baho, so'z)
SCALE = [(65, 100, "A", 5, "a'lo"), (60, 64, "B", 4, "yaxshi"), (50, 59, "C", 4, "yaxshi"),
         (45, 49, "D", 3, "qoniqarli"), (40, 44, "E", 3, "qoniqarli"), (0, 39, "F", 2, "qoniqarsiz")]
SCALE_TEXT = "; ".join(f"{lo}–{hi} — «{g}» ({l})" for lo, hi, l, g, _ in SCALE)

def _band(score):
    return next(b for b in SCALE if score >= b[0])

def grade5(score):
    """100 ballik → (5 baho, so'z)."""
    b = _band(score)
    return b[3], b[4]

def letter(score):
    return _band(score)[2]

def split_score(score: int, key: str):
    """Yakuniy ballni oraliq (≤30) + yakuniy (≤70) ga ajratadi — qaydnoma uchun, deterministik.
    O'tgan talabada ikkala nazorat ham minimal chegaradan past emas; o'tmaganda oraliq imkon qadar 12 dan
    kam emas (yakuniyga kiritilgan), yakuniy esa 28 dan past chiqadi — jami har doim bazadagi ball bilan bir xil."""
    r = random.Random(key)
    want = round(score * ORALIQ_MAX / 100 + r.uniform(-3, 3))
    if score >= PASS:
        lo, hi = max(ORALIQ_MIN, score - YAKUNIY_MAX), min(ORALIQ_MAX, score - YAKUNIY_MIN)
    else:
        lo, hi = min(ORALIQ_MIN, score), min(ORALIQ_MAX, score)
    o = max(lo, min(hi, want))
    return o, score - o

# ---------------- kredit va GPA ----------------
CREDIT_HOURS, CREDIT_AUD, CREDIT_SELF = 30, 12, 18
BACHELOR_CREDITS, MASTER_CREDITS = 240, 120
GPA_FORMULA = "GPA = Σ(kredit × baho) / Σ kredit"
CREDIT_NOTE = f"1 kredit = {CREDIT_HOURS} soat ({CREDIT_AUD} soat auditoriya + {CREDIT_SELF} soat mustaqil ta'lim)"

def ratio2(num, den):
    """num / den — 2 xonagacha, aniq «yarimdan yuqoriga» (4.625 → 4.63). Butun sonlardan hisoblanadi, shuning uchun
    Python (transkript, karta) va SQL (reyting keshi, ratio2_sql) bir xil natija beradi — float yaxlitlash farqi yo'q."""
    if not den: return None
    from fractions import Fraction
    return int(Fraction(num) * 100 / Fraction(den) + Fraction(1, 2)) / 100   # num, den ≥ 0

def ratio2_sql(num: str, den: str) -> str:
    """ratio2 ning SQL ko'rinishi (num, den — butun sonli ifodalar): ((200·num + den) div (2·den)) / 100."""
    return f"(((200 * ({num}) + ({den})) / (2 * ({den}))) / 100.0)"

def gpa(items):
    """items: [(kredit, 5 ballik baho)] → Σ(kredit × baho) / Σ kredit (2 xona, yarimdan yuqoriga)."""
    cr = sum(k for k, _ in items)
    return ratio2(sum(k * g for k, g in items), cr) if cr else None

# Fan krediti: o'quv dasturida (syl_items.credits — «O'quv dasturlari» moduli) ko'rsatilgan bo'lsa o'sha, aks holda standart.
# Standart 6 kredit — taqdimotdagi GPA misolidagi fan krediti (quyida GPA_EXAMPLE); transkript va reyting bir xil manbadan oladi.
CREDIT_DEFAULT = 6
CREDIT_SOURCE_SYL, CREDIT_SOURCE_DEFAULT = "o'quv dasturi", "standart"

def subject_credits(con) -> dict:
    """{fan: kredit} — o'quv dasturlaridan (bir fanga bir nechta kafedra dasturi bo'lsa — eng ko'p uchragan qiymat).
    Ro'yxatda yo'q fan uchun CREDIT_DEFAULT ishlatiladi (credit_of)."""
    try:
        rows = con.execute("""SELECT subject, credits FROM (SELECT subject, credits, COUNT(*) n FROM syl_items
                              WHERE credits IS NOT NULL AND credits > 0 GROUP BY subject, credits) ORDER BY subject, n DESC, credits DESC""").fetchall()
    except Exception:   # yangi bazada syl_items hali bo'lmasligi mumkin
        return {}
    out = {}
    for subj, cr in rows: out.setdefault(subj, int(cr))
    return out

def credit_of(credits: dict, subject: str) -> int:
    return credits.get(subject, CREDIT_DEFAULT)

# Taqdimotdagi misol: Korporativ boshqaruv yo'nalishi talabasi, 1-semestr
GPA_EXAMPLE = [("Korporativ boshqaruv", 6, 4), ("Moliyaviy hisobot metodologiyasi", 6, 4),
               ("Buxgalteriya, tashkilotlar va jamiyat", 6, 5), ("Ilmiy tadqiqot metodologiyasi", 6, 3),
               ("Maxsus fanlarni o'qitish metodikasi", 6, 4)]

# ---------------- bo'limlar: Registrator ofisi, Akademik faoliyatni boshqarish, Sirtqi, Ma'lumotlar bazasi ----------------
# To'rtta MUSTAQIL bo'lim (taqdimot, 3- va 6-slayd). 6-slaydda vazifalar bo'lim bloklari ostida BITTA umumiy ro'yxat sifatida
# berilgan (bo'limlarga ajratilmagan) — quyidagi taqsimot vazifa mazmuni, bo'lim nomi va 16-slayddan ("yakuniy nazorat jadvalini
# akademik faoliyatni boshqarish bo'limi ishlab chiqadi") kelib chiqadi. Call-markaz bloki — Registrator ofisi bilan.
# Ism-shariflar: Registrator va Akademik bo'lim boshliqlari — institut ro'yxati ("Lavozim ism", app/seed.py UNIT_HEADS);
# Sirtqi va Ma'lumotlar bazasi bo'limlari boshliqlari — taqdimot.
REGISTRAR_UNIT = "Registrator ofisi"
ACADEMIC_UNIT = "Akademik faoliyatni boshqarish bo'limi"
SIRTQI_UNIT = "Sirtqi bo'lim"
DB_UNIT = "Ma'lumotlar bazasi bo'limi"
OTHER_UNIT_HEADS = {SIRTQI_UNIT: "Shayzakova Dilbar", DB_UNIT: "Ismatov Ravshan"}

# bo'lim → [(vazifa — taqdimot matni, majlis topshiriqlarini yo'naltirish belgilari — regex, app/decisions.py UNITS)]
DUTIES = {
    REGISTRAR_UNIT: [
        ("qabul komissiyasining ishini tashkil qilish", []),   # topshiriqlar Qabul komissiyasi navbatiga tushadi
        ("talabalarning shaxsiy hujjatlarini arxivgacha saqlash", [r"(?i)shaxsiy (?:hujjat|ish)", r"(?i)\barxiv"]),
        ("transkriptni yuritish va unga talabalarning baholarini kiritish", [r"(?i)\btranskript", r"(?i)baholarni kirit"]),
        ("tantanali marosimlarni tashkil qilish va o'tkazish", [r"(?i)tantanali marosim", r"(?i)bitiruv marosim"]),
        ("Call-markaz: talabalar va ota-onalar bilan qo'ng'iroqlar", [r"(?i)call[- ]?markaz"]),
    ],
    ACADEMIC_UNIT: [
        ("akademik taqvim tuzish va uning o'z vaqtida bajarilishini nazorat qilish", [r"(?i)akademik taqvim"]),
        ("fanlarga yozilishni tashkil qilish (Enrollment)", [r"(?i)fan(?:lar)?ga yozil", r"(?i)\benrol+ment"]),
        ("akademik guruhlarni shakllantirish", [r"(?i)akademik guruh"]),
        ("kirishda bilimlarni aniqlashni tashkil qilish va uni nazorat qilish", [r"(?i)kirish(?:da)? (?:test|bilim)"]),
        ("yakuniy nazorat va oraliq attestatsiyalarni tashkil qilish va o'tkazish (yakuniy nazorat jadvali)",
         [r"(?i)oraliq attestatsiya", r"(?i)(?:yakuniy nazorat|imtihon)(?:lar)? jadval"]),
        ("yakuniy davlat attestatsiyasini tashkil qilish va o'tkazishni nazorat qilish", [r"(?i)yakuniy davlat attestatsiya", r"\bYDA\b"]),
    ],
    SIRTQI_UNIT: [   # TAXMINIY: taqdimotda alohida vazifalar yo'q — sirtqi ta'lim amaliyotidan; bo'lim nizomi olinganda aniqlashtiriladi
        ("sirtqi ta'lim shakli talabalari kontingentini yuritish (guruhlar, ko'chirish, qayta tiklash)",
         [r"(?i)sirtqi bo'lim", r"(?i)sirtqi (?:ta'lim|talaba|guruh)"]),
        ("o'quv-imtihon sessiyalari jadvalini tuzish va o'tkazilishini nazorat qilish", [r"(?i)sirtqi sessiya", r"(?i)sessiya(?:lar)? jadval"]),
        ("sessiyaga chaqiruv xatlarini (ish beruvchi uchun ma'lumotnoma-chaqiruv) tayyorlash va berish", [r"(?i)chaqiruv xat"]),
        ("sirtqi talabalarning mustaqil ishlari, oraliq va yakuniy nazoratlarini tashkil qilish", [r"(?i)sirtqi (?:nazorat|imtihon)"]),
        ("sirtqi talabalarning akademik qarzdorligi va qayta topshirishlarini nazorat qilish", []),
        ("sessiya natijalari bo'yicha hisobot tayyorlash", [r"(?i)sessiya natija"]),
    ],
    DB_UNIT: [
        ("«Registrator» ma'lumotlar bazasini shakllantirish va muntazam yangilash", [r"(?i)ma'lumotlar bazasi", r"(?i)registrator\W*bazas"]),
        ("talabalar kontingenti bo'yicha statistika yuritish", [r"(?i)kontingent"]),
    ],
}
# Registrator ofisi e'loni (07.09, kunduzgi ta'lim talabalari uchun): manzil va murojaat masalalari
REGISTRAR_SOURCE = "Registrator ofisi e'loni (07.09)"
REGISTRAR_ROOMS = ["Asosiy bino, 115-xona", "Eco bino, 105-xona"]
REGISTRAR_ROOMS_TEXT = " yoki ".join(REGISTRAR_ROOMS)
REGISTRAR_CONTACT = [   # (masala, majlis topshiriqlari uchun belgilar)
    ("talabalikka oid hujjatlar va ma'lumotnomalar", [r"(?i)ma'lumotnoma"]),
    ("talaba maqomi bilan bog'liq masalalar", [r"(?i)talaba(?:lik)? maqom"]),
    ("akademik ta'til bilan bog'liq murojaatlar", [r"(?i)akademik ta'til"]),
    ("fanlar va o'quv jarayoniga oid ma'muriy masalalar", []),
    ("baholar, akademik natijalar va tegishli ma'lumotlar bo'yicha murojaatlar", [r"(?i)akademik natija"]),
    ("shartnoma va talabalik hujjatlari bilan bog'liq masalalar", [r"(?i)shartnoma hujjat", r"(?i)talabalik hujjat"]),
    ("boshqa o'quv jarayoniga oid rasmiy murojaatlar", []),
]
DUTIES[REGISTRAR_UNIT] += [(f"talabalar murojaatlari: {m}", ps) for m, ps in REGISTRAR_CONTACT]

UNIT_DUTIES = {u: [d for d, _ in ds] for u, ds in DUTIES.items()}
DUTIES_NOTE = {SIRTQI_UNIT: "ro'yxat taxminiy — bo'lim nizomi olinganda aniqlashtiriladi"}
UNIT_PATTERNS = {u: [p for _, ps in ds for p in ps] for u, ds in DUTIES.items()}
UNIT_SUMMARY = {
    REGISTRAR_UNIT: "talabaning qabuldan bitiruvgacha bo'lgan akademik hujjatlarini yuritadi: transkript, shaxsiy hujjatlar, marosimlar, Call-markaz",
    ACADEMIC_UNIT: "o'quv jarayonini tashkil qiladi: akademik taqvim, fanlarga yozilish, akademik guruhlar, nazoratlar jadvali, YDA",
    SIRTQI_UNIT: "sirtqi ta'lim shakli talabalari bilan ishlaydi: kontingent, sessiyalar jadvali, chaqiruv xatlari, nazoratlar va qarzdorlik",
    DB_UNIT: "«Registrator» ma'lumotlar bazasini yuritadi va talabalar kontingenti statistikasini beradi",
}

# ---------------- kafedralar (taqdimot: xalqaro va mahalliy ta'lim yo'nalishlari kafedralari) ----------------
INTL_DEPTS = {
    "Buxgalteriya hisobi": ["UOS BA (Hons) Buxgalteriya hisobi va moliya (IAAF)"],
    "Biznes boshqaruvi": ["UOS BA (Hons) Biznes va menejment (IBA)"],
    "Menejment": ["Moliya sohasida boshqaruv (MMA)"],
}
LOCAL_DEPTS = {
    "Psixologiya va pedagogika": ["Pedagogika", "Psixologiya (faoliyat turlari bo'yicha)", "Boshlang'ich ta'lim", "Maktabgacha ta'lim",
                                  "Pedagogika va psixologiya"],
    "Gumanitar va tabiiy fanlar": ["Xalqaro munosabatlar", "mahalliy yo'nalishlarda 1-kursning ijtimoiy-gumanitar fanlari"],
    "Iqtisodiyot va kompyuter injiniringi": ["Iqtisodiyot", "Bank ishi", "Marketing", "Menejment", "Axborot xavfsizligi",
                                             "Axborot tizimlari va texnologiyalari"],
    "Filologiya va tillarni o'qitish": ["Filologiya va tillarni o'qitish", "Xorijiy til va adabiyoti"],
}

# ---------------- reyting (app/reyting.py — «Reyting» moduli) ----------------
RATING_TITLE = ("Oliy ta'lim muassasasi talabalarining o'zlashtirish ko'rsatkichlarini reyting baholash "
                "avtomatlashtirilgan tizimi")
# grades.semester: 0 — yakunlangan (o'tgan) semestr, 1 — joriy semestr (app/documents.py transkripti bilan bir xil)
SEMESTERS = {0: "2025-2026 o'quv yili, bahorgi semestr", 1: "2026-2027 o'quv yili, kuzgi semestr"}
SEMESTER_SHORT = {0: "2025-26 · bahorgi", 1: "2026-27 · kuzgi"}
CURRENT_SEMESTER = 1
# Tartiblash (birinchisi asosiy, keyingilari — teng kelganda): hammasi kamayish tartibida
RATING_ORDER = [("gpa", "Semestr GPA (5 ballik, kredit bilan tortilgan)", 2),
                ("avg_score", "O'rtacha ball (100 ballik, fanlar bo'yicha oddiy o'rtacha)", 2),
                ("attendance", "Davomat, % (joriy semestr; qayd etilmagan — oxirida)", 1)]
RATING_LEVELS = [("group", "Guruh"), ("course", "Kurs"), ("direction", "Yo'nalish"), ("faculty", "Fakultet"), ("institute", "Institut")]
RATING_LEVEL_NOTE = {"group": "o'quv guruhi ichida", "course": "bir xil daraja (bakalavr/magistr) va kursdagi barcha talabalar orasida",
                     "direction": "bir xil yo'nalish va darajadagi barcha kurslar orasida", "faculty": "fakultet bo'yicha",
                     "institute": "butun institut bo'yicha"}
RATED_STATUS = "faol"                       # reytingda faqat faol talabalar
EXCELLENT_MIN = SCALE[0][0]                 # a'lochi: barcha fanlardan «5» (kamida 65 ball)
TOP_DEFAULTS = {"pct": 10, "min_att": 85.0, "max_f": 0}   # mukofotlar uchun: kurs bo'yicha eng yaxshi N%, qarzsiz, davomat ≥
UNIT_MIN = {"group": 10, "kafedra": 150, "teacher": 30}    # bo'linmalar reytingi: kamida shuncha (guruh — talaba; kafedra, o'qituvchi — baho)
UNIT_MIN_NOTE = {"group": "talaba", "kafedra": "baho", "teacher": "baho"}

def grade5_sql(col="score") -> str:
    """SCALE dan SQL: 100 ballik → 5 baho (keshni hisoblashda; qoidalar bitta joyda qoladi)."""
    parts = " ".join(f"WHEN {col} >= {lo} THEN {g}" for lo, _, _, g, _ in SCALE if lo > 0)
    return f"(CASE {parts} ELSE {SCALE[-1][3]} END)"

def percentile(rank: int, n: int) -> int:
    """Yuqoridan necha foiz ichida: 1/1240 → 1, 620/1240 → 50. (rank/n × 100, yuqoriga yaxlitlanadi)."""
    if not rank or not n: return None
    return max(1, min(100, -(-rank * 100 // n)))

RATING_FORMULA = (f"{GPA_FORMULA}; baho — 100 ballik balldan ({SCALE_TEXT}). Kredit — o'quv dasturidan, "
                  f"ko'rsatilmagan bo'lsa {CREDIT_DEFAULT} kredit.")
