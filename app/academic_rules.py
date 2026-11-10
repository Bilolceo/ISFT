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
    """Yakuniy ballni oraliq (≤30) + yakuniy (≤70) ga ajratadi — FAQAT demo baholarni yaratishda (app/seed.py) ishlatiladi.
    Bazada oraliq va yakuniy alohida saqlanadi (grades.oraliq, grades.yakuniy) — hujjatlar va reyting ularni o'qiydi, qayta bo'lmaydi."""
    r = random.Random(key)
    want = round(score * ORALIQ_MAX / 100 + r.uniform(-3, 3))
    if score >= PASS:
        lo, hi = max(ORALIQ_MIN, score - YAKUNIY_MAX), min(ORALIQ_MAX, score - YAKUNIY_MIN)
    else:
        lo, hi = min(ORALIQ_MIN, score), min(ORALIQ_MAX, score)
    o = max(lo, min(hi, want))
    return o, score - o

def admitted(oraliq) -> bool:
    """Yakuniy nazoratga kiritiladimi: oraliq nazoratdan kamida 12 / 30 ball."""
    return oraliq is not None and oraliq >= ORALIQ_MIN

# ---------------- akademik taqvim ----------------
# grades.semester — o'quv davri (semestr) kodi, talabadan qat'i nazar bir xil:
#    1 — JORIY semestr (2026-2027 kuzgi): faqat joriy/oraliq nazorat ballari bor, yakuniy nazorat (qishki sessiya) hali o'tmagan;
#    0 — oxirgi yakunlangan semestr (2025-2026 bahorgi), -1 — 2025-2026 kuzgi, ... -5 — 2023-2024 kuzgi (hozirgi 4-kurs 1-semestri).
# Talabaning dastur semestri (1..8 bakalavr, 1..4 magistr): sem_no = 2·kurs − 2 + kod. 1-kursda o'tgan semestr YO'Q;
# 4-kursda 6 ta yakunlangan semestr + joriy 7-semestr.
ACAD_YEAR_START = 2026            # joriy o'quv yili: 2026-2027
CURRENT_SEMESTER = 1
OLDEST_SEMESTER = -5
PROGRAM_SEMESTERS = {"bakalavr": 8, "magistr": 4}
BACHELOR_CREDITS, MASTER_CREDITS = 240, 120
PROGRAM_CREDITS = {"bakalavr": BACHELOR_CREDITS, "magistr": MASTER_CREDITS}
SEMESTER_CREDITS = 30             # har semestr o'quv rejasida 30 kredit (240 / 8, 120 / 4)

def term_year(t: int) -> int:
    """Semestr kodi → o'quv yilining boshlanish yili (1 → 2026, 0 → 2025, -1 → 2025, -2 → 2024 ...)."""
    return ACAD_YEAR_START + (t - 1) // 2

def term_season(t: int) -> str:
    return "kuzgi" if t % 2 == 1 else "bahorgi"

def term_dates(t: int):
    """(boshlanish, tugash) ISO sanalari: kuzgi — 1 sentabr..31 yanvar, bahorgi — 1 fevral..30 iyun."""
    y = term_year(t)
    return (f"{y}-09-01", f"{y + 1}-01-31") if t % 2 == 1 else (f"{y + 1}-02-01", f"{y + 1}-06-30")

def sem_no(course: int, t: int) -> int:
    """Talabaning dastur semestri raqami (≤ 0 — o'sha davrda hali o'qimagan)."""
    return 2 * int(course) - 2 + t

def term_of(course: int, n: int) -> int:
    return n - 2 * int(course) + 2

ACAD_SCHEMA = """
CREATE TABLE IF NOT EXISTS curriculum(id INTEGER PRIMARY KEY, direction TEXT, level TEXT, sem_no INT, subject TEXT, credits INT);
CREATE INDEX IF NOT EXISTS ix_curr ON curriculum(direction, level, sem_no);
CREATE TABLE IF NOT EXISTS grade_attempts(id INTEGER PRIMARY KEY, student_id INT, subject TEXT, semester INT, attempt INT, kind TEXT,
  oraliq INT, yakuniy INT, score INT, at TEXT, counted INT, retake_id INT, by_user INT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_ga_st ON grade_attempts(student_id, semester, subject);
CREATE INDEX IF NOT EXISTS ix_grades_student ON grades(student_id, semester);
CREATE INDEX IF NOT EXISTS ix_grades_teacher ON grades(teacher_id);
"""
GRADE_COLS = [("oraliq", "INT"), ("yakuniy", "INT"), ("credits", "INT"), ("sem_no", "INT"), ("attempts", "INT DEFAULT 1")]

def ensure_schema(con):
    """Baholar modeli: grades — har fan × semestr uchun HISOBDAGI natija (ball, oraliq, yakuniy, kredit, dastur semestri, urinishlar soni);
    grade_attempts — urinishlar tarixi (asl urinish + qayta topshirish / otrabotka, qaysi biri hisobga olingani);
    curriculum — o'quv rejasi. Joriy semestrda grades.score NULL (yakuniy nazorat hali o'tmagan), faqat oraliq bor."""
    have = {r[1] for r in con.execute("PRAGMA table_info(grades)").fetchall()}
    for col, ty in GRADE_COLS:
        if col not in have: con.execute(f"ALTER TABLE grades ADD COLUMN {col} {ty}")
    con.executescript(ACAD_SCHEMA)
    con.commit()

def intake_year(course: int) -> int:
    """Qabul yili: 1-kurs — 2026, 4-kurs — 2023 (guruh kodi va ma'lumotnomadagi o'qish muddati shundan)."""
    return ACAD_YEAR_START - int(course) + 1

# ---------------- kredit va GPA ----------------
CREDIT_HOURS, CREDIT_AUD, CREDIT_SELF = 30, 12, 18
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

# Fan krediti — o'quv rejasidan (curriculum: yo'nalish × daraja × dastur semestri × fan → kredit, app/seed.py). Baho qatoriga ham
# yoziladi (grades.credits) — reyting, transkript va GPA shu qiymatni oladi. O'quv rejasida topilmasa (eski baza) — standart.
CREDIT_DEFAULT = 6
CREDIT_SOURCE_SYL, CREDIT_SOURCE_DEFAULT = "o'quv rejasi", "standart"

def subject_credits(con) -> dict:
    """{fan: kredit} — o'quv rejasidan (bir fan bir nechta yo'nalishda turlicha bo'lsa — eng ko'p uchragan qiymat);
    o'quv rejasi jadvali bo'lmasa — o'quv dasturlaridan (syl_items). Ro'yxatda yo'q fan uchun CREDIT_DEFAULT (credit_of)."""
    for sql in ("""SELECT subject, credits FROM (SELECT subject, credits, COUNT(*) n FROM curriculum WHERE credits>0 GROUP BY subject, credits)
                   ORDER BY subject, n DESC, credits DESC""",
                """SELECT subject, credits FROM (SELECT subject, credits, COUNT(*) n FROM syl_items
                   WHERE credits IS NOT NULL AND credits > 0 GROUP BY subject, credits) ORDER BY subject, n DESC, credits DESC"""):
        try:
            rows = con.execute(sql).fetchall()
        except Exception:   # yangi bazada jadval hali bo'lmasligi mumkin
            continue
        if rows:
            out = {}
            for subj, cr in rows: out.setdefault(subj, int(cr))
            return out
    return {}

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
# Semestrlar (yuqoridagi akademik taqvim): reyting faqat YAKUNLANGAN semestrlar bo'yicha (yakuniy ball bor); joriy semestrda
# faqat oraliq nazorat — u reytingga kirmaydi (Talabalar markazi va imtihonga ruxsatnomada ishlatiladi).
SEMESTERS = {t: f"{term_year(t)}-{term_year(t) + 1} o'quv yili, {term_season(t)} semestr" for t in range(CURRENT_SEMESTER, OLDEST_SEMESTER - 1, -1)}
SEMESTER_SHORT = {t: f"{term_year(t)}-{str(term_year(t) + 1)[2:]} · {term_season(t)}" for t in SEMESTERS}
COMPLETED_SEMESTERS = [t for t in SEMESTERS if t < CURRENT_SEMESTER]      # 0, -1, ... -5 (yangisi birinchi)
RATING_SEMESTER = CURRENT_SEMESTER - 1    # reyting standart semestri: oxirgi yakunlangan (2025-2026 bahorgi)
# Tartiblash (birinchisi asosiy, keyingilari — teng kelganda): hammasi kamayish tartibida
RATING_ORDER = [("gpa", "Semestr GPA (5 ballik, kredit bilan tortilgan)", 2),
                ("avg_score", "O'rtacha ball (100 ballik, fanlar bo'yicha oddiy o'rtacha)", 2),
                ("attendance", "Davomat, % (oxirgi yakunlangan semestr reytingida — joriy davomat; qayd etilmagan — oxirida)", 1)]
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

RATING_FORMULA = (f"{GPA_FORMULA}; baho — 100 ballik yakuniy balldan ({SCALE_TEXT}). Kredit — o'quv rejasidan "
                  f"(har semestr {SEMESTER_CREDITS} kredit), ko'rsatilmagan bo'lsa {CREDIT_DEFAULT} kredit.")

# =====================================================================================================
# YAGONA TA'RIFLAR — panel (KPI), Talabalar markazi, Reyting, hujjatlar va call-markaz shu yerdan oladi
# =====================================================================================================
SCORE_LABEL = "O'rtacha ball (100)"     # fanlar bo'yicha 100 ballik yakuniy ballarning oddiy o'rtachasi
GPA_LABEL = "GPA (5)"                    # 5 ballik baho, kredit bilan tortilgan: Σ(kredit × baho) / Σ kredit
SCORE_DEF = (f"{SCORE_LABEL}: oxirgi yakunlangan semestr ({SEMESTERS[RATING_SEMESTER]}) fanlari bo'yicha 100 ballik yakuniy "
             "ballarning o'rtachasi (qayta topshirilgan bo'lsa — hisobdagi urinish). 1-kurs talabalarida hali yakunlangan semestr yo'q.")
# students.gpa / students.gpa_prev — HISOBLANGAN qiymatlar (refresh_student_metrics): oxirgi va undan oldingi yakunlangan semestrning
# o'rtacha bali (100). Qo'lda o'zgartirilmaydi; baho o'zgarsa (otrabotka tasdiqlansa) qayta hisoblanadi.

# O'zlashtirish holati (Talabalar markazi «akademik» qoidasi) — darajalar:
FAILS_WARN, GPA_MIN = 2, 3.0           # ops_policy dagi standart qiymatlar (fails_warn, gpa_min)
DEBTOR_LABEL = "Akademik qarzdor"
DEBTOR_DEF = (f"yakunlangan semestr(lar)dan kamida bitta fani o'zlashtirilmagan (hisobdagi yakuniy ball {PASS} dan past va qayta "
              "topshirish bilan yopilmagan) faol talaba")
RISK_LABEL = "O'qishda xavf"
AT_RISK_LEVEL = 2                       # «kritik» va «jiddiy»
RISK_DEF = ("faol talaba, o'zlashtirish yoki davomat bo'yicha holati «kritik»/«jiddiy»: kamida "
            f"{FAILS_WARN} ta akademik qarz yoki kumulyativ GPA {GPA_MIN} dan past yoki joriy semestrda {FAILS_WARN} va undan ko'p fandan "
            f"oraliq nazorat {ORALIQ_MIN} balldan past, yoki joriy semestrda 30+ soat (sirtqi — sessiya soatlariga mutanosib, 16+) sababsiz "
            "qoldirilgan dars. Kontrakt qarzi bu songa kirmaydi")

def akademik_level(debts: int, gpa5, oraliq_low: int, fails_warn=FAILS_WARN, gpa_min=GPA_MIN) -> int:
    """0 — holat yo'q; 1 — diqqat (1 ta qarz yoki 1 ta fandan oraliq < 12); 2 — kritik (≥ fails_warn qarz, kumulyativ GPA < gpa_min,
    ≥ fails_warn fandan oraliq < 12 yoki qarz + past oraliq birga); 3 — jiddiy (≥ fails_warn + 2 qarz)."""
    fw = int(fails_warn)
    if debts >= fw + 2: return 3
    if debts >= fw or (gpa5 is not None and gpa5 < gpa_min) or oraliq_low >= fw or (debts and oraliq_low): return 2
    if debts or oraliq_low: return 1
    return 0

def davomat_level(h, call=30, letter=30, reprimand=48) -> int:
    """Joriy semestrdagi sababsiz soatlar zinapoyasi: hayfsan — chegaradan OSHSA (48 → 49+), xat va qo'ng'iroq — chegaraga yetsa (30+)."""
    if h > reprimand: return 3
    if h >= letter: return 2
    if h >= call: return 1
    return 0

def debt_where(alias="g") -> str:
    """Akademik qarz (SQL sharti): yakunlangan semestrdagi hisobdagi ball o'tish balidan past."""
    return f"{alias}.semester < {CURRENT_SEMESTER} AND {alias}.score IS NOT NULL AND {alias}.score < {PASS}"

def refresh_student_metrics(con, ids=None) -> int:
    """students.gpa / gpa_prev ni baholardan qayta hisoblaydi (o'rtacha ball (100): oxirgi va undan oldingi yakunlangan semestr).
    Reyting keshidagi avg_score bilan bir xil formula (ratio2) — panel KPI va reyting bir xil raqam ko'rsatadi."""
    def q(t): return (f"(SELECT {ratio2_sql('SUM(x.score)', 'COUNT(*)')} FROM grades x WHERE x.student_id=students.id "
                      f"AND x.semester={t} AND x.score IS NOT NULL)")   # 0 ta baho → 0 ga bo'lish → NULL
    w = f" WHERE id IN ({','.join(str(int(i)) for i in ids)})" if ids else ""
    if ids is not None and not ids: return 0
    return con.execute(f"UPDATE students SET gpa={q(RATING_SEMESTER)}, gpa_prev={q(RATING_SEMESTER - 1)}{w}").rowcount
