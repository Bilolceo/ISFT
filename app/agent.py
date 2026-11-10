"""ISFT Core agenti: savol → reja → vositalar (RBAC orqali) → tahlil → raqamlarni tekshirish → javob + amallar.

Oldingi `ai.answer` faqat ma'lumotni qisqa matnga aylantirardi. Agent esa:
  * har bir qadamni ko'rsatadi (qaysi manbaga murojaat qildi, nimaga ruxsat berilmadi);
  * "nega?" savoliga ma'lumotdan sabab izlaydi (davomat, kontrakt bosimi, fanlar kesimi);
  * tavsiyalarni tayyor shablondan emas, aniq raqam, mas'ul va muddat bilan tuzadi;
  * javobdagi har bir raqamni manba ma'lumot bilan solishtiradi (AI o'ylab topgan raqam o'tmaydi);
  * suhbat kontekstini eslaydi ("nega?", "fakultetlar bo'yicha-chi?");
  * tavsiyani bir tugma bilan topshiriqqa aylantiradi — inson tasdiqlaydi (app/agent_hub.py).
Model bazaga baribir to'g'ridan-to'g'ri kirmaydi: raqamlarni kod hisoblaydi, model faqat matnni silliqlaydi."""
import asyncio, json, re, time, datetime as dt
from dataclasses import replace
from . import clock
from . import db, services as S, ai, academic_rules as AR
from .rbac import AccessDenied, Ctx, audit

MEMORY: dict[int, dict] = {}     # user_id -> {"topics": [...], "ts": float}
MEM_TTL = 30 * 60

TOOL_LABEL = {
    "academic": "O'zlashtirish va davomat bazasi", "risk": "Yagona xavf modeli (Talabalar markazi qoidalari)",
    "contracts": "Kontrakt to'lovlari", "finance": "Byudjet va xarajatlar", "payroll": "Ish haqi fondi", "hr": "Kadrlar bazasi",
    "science": "Ilmiy nashrlar va grantlar", "international": "Xalqaro shartnomalar", "admissions": "Qabul bazasi",
    "youth": "Murojaatlar va tadbirlar", "masters": "Magistratura", "tasks": "Majlis topshiriqlari ijrosi", "alerts": "Proaktiv ogohlantirishlar",
    "qoidalar": AR.SOURCE, "cameras": "Kameralar (Hikvision, faqat metama'lumot: xona, vaqt, tur, son)",
    "facecam": "Kirish nazorati (Face ID: faqat yozma rozilik bergan shaxslar, ko'lamingiz bo'yicha)",
}
STRATEGIC = ["ortda", "muammo", "umumiy holat", "nima qilish", "tavsiya", "xulosa", "qanday holat", "e'tibor", "strateg", "brifing",
             "bugun nima", "bugungi holat", "holat qanday", "eng muhim", "ustuvor"]
FOLLOW = re.compile(r"(^|\s)(nega|nima uchun|sababi|sabab|batafsil|ko'proq|davom|shu|bu|ular|bular|ularni|buni|solishtir|bo'yicha-chi|-chi)(\s|\?|$)")
WHY = re.compile(r"nega|nima uchun|sabab")
INTL_WORDS = ("xalqaro", "hamkor", "xorij", "erasmus", "almashinuv", "universitet")
CONTRACT_WORDS = ("talaba", "kontrakt", "to'lov", "qarz", "tushum")

def plan(q: str, mem: dict | None):
    n = ai.norm(q)
    names = ai.route(q)
    # Akademik qoidalar (o'tish bali, GPA, kredit, dars vaqti, registrator...) — me'yoriy savol. Ma'lumot savoli
    # ("nega pasaydi", "nechta talaba") bo'lsa va ma'lumot manbasi topilsa — tahlilga ketadi.
    if (rule_topics(n) or RULES_ANY.search(n)) and (not names or not DATA_INTENT.search(n)):
        return ["qoidalar"], False, False, False
    # "shartnoma" — talaba kontrakti ham, xalqaro hamkorlik ham bo'lishi mumkin
    if "international" in names and "shartnoma" in n and not any(w in n for w in INTL_WORDS):
        if any(w in n for w in CONTRACT_WORDS):
            names.remove("international")
            if "contracts" not in names: names.append("contracts")
    # "yil oxiriga qancha", "prognoz" — kontrakt prognozi
    if ("prognoz" in n or "yil oxiri" in n) and not names: names = ["contracts"]
    is_why = bool(WHY.search(n))
    strategic = any(w in n for w in STRATEGIC)
    follow = False
    if ("prognoz" in n or "yil oxiri" in n): is_why = True
    if not names and mem and not strategic and (FOLLOW.search(n) or len(n.split()) <= 4):   # "ortda qolyapmiz?" — har doim strategik
        names, follow = ([mem["main"]] if is_why and mem.get("main") else list(mem["topics"])), True
    if strategic and not names:
        names = ["academic", "risk", "contracts", "finance", "tasks", "international"]
    return names, is_why, strategic, follow

# ------------------------------------------------------------------------------------------------
# Akademik qoidalar (manba: O'quv jarayoni va akademik qoidalar taqdimoti — app/academic_rules.py)
# ------------------------------------------------------------------------------------------------
RULE_PATTERNS = [   # (mavzu, savoldagi belgi — ai.norm qilingan matnda)
    ("baholash", r"o'tish bal|o'tish chegara|o'tish uchun|baholash (?:mezon|shkala|tizim|qoida|tartib)|baho(?:lar)? shkala|harfli|\bects\b|"
                 r"\b[a-f] baho|qaysi baho|necha ball(?:ga|da|dan)? (?:o't|«?[2-5])|ball(?:i)? necha(?:ga)? baho|qoniqarsiz baho|konvertatsiya"),
    ("nazorat", r"oraliq nazorat|yakuniy nazorat|nazorat tur|yakuniyga|imtihon(?:ga|ni)? kim|imtihon(?:ga)? kirit|imtihonga ruxsat"),
    ("gpa", r"\b[gj]pa\b.*(?:hisobla|formula|nima\b|nimadir|qanday aniqlan|qanday chiq)|(?:hisobla|formula).*\b[gj]pa\b"),
    ("kredit", r"\bkredit"),
    ("dars_vaqti", r"(?:dars|para|juftlik|mashg'ulot)\w*\b.*(?:nechida|qachon (?:boshlan|tugay)|vaqtlari|boshlanadi|tugaydi)|\bsmena|tanaffus|qo'ng'iroq jadval"),
    ("registrator_joy", r"registrator\w*\b.*(?:qayer|qaysi (?:bino|xona)|xona\w*\b|manzil|joylash)"),
    ("registrator_murojaat", r"(?:qanday|qaysi) (?:masala|holat|hujjat|savol|murojaat)\w*\b.*registrator|registrator\w*\b.*(?:qanday|qaysi) "
                             r"(?:masala|holat|murojaat)|registrator\w* (?:qachon|nima bilan) murojaat"),
    ("registrator", r"registrator\w*\b.*(?:nima|vazifa|tarkib|kim|bo'lim|tuzilma|ish qila|funksiya|qanday)|^registrator(?: ofisi)?\W*$"),
    ("akademik_bolim", r"akademik faoliyat\w*\b.*(?:nima|vazifa|tarkib|kim|tuzilma|ish qila|funksiya|qanday|bo'lim\w*\W*$)"),
    ("sirtqi_bolim", r"sirtqi bo'lim\w*\b.*(?:nima|vazifa|kim|ish qila|funksiya|qanday)|^sirtqi bo'lim\w*\W*$"),
    ("malumotlar_bolim", r"ma'lumotlar bazasi bo'lim\w*\b.*(?:nima|vazifa|kim|ish qila|funksiya|qanday)|^ma'lumotlar bazasi bo'lim\w*\W*$"),
    ("kafedralar", r"(?:xalqaro|mahalliy)\w*\b.*kafedra|kafedra\w*\b.*(?:xalqaro|mahalliy)|kafedralar(?:i)? qaysi|qaysi kafedralar"),
    # Reyting moduli metodikasi (app/reyting.py) — faqat qoida; shaxsiy o'rinlar agentga chiqmaydi
    ("reyting", r"reyting\w*\b.*(?:qanday|hisobla|formula|nima\b|tartib|aniqlan|metodika|mezon|tuzil)|(?:qanday|nima asosida)\b.*\breyting|^reyting\W*$|a'lochi\w*\b.*(?:kim|qanday|mezon|shart)"),
]
RULE_RX = [(k, re.compile(p)) for k, p in RULE_PATTERNS]
RULES_ANY = re.compile(r"akademik qoida|o'quv qoida|baholash qoida")
DATA_INTENT = re.compile(r"nega|nima uchun|sabab|pasay|o'sdi|oshdi|kamay|qancha talaba|nechta talaba|necha nafar|nafar|foiz|ulush|statistika|"
                         r"bajaril|muddati o't|topshiriq|qarzdor|xavf|guruhlar(?:da|i)|fakultet(?:lar)?(?:da|i)|kurs(?:da|lar)")
RULE_ASK = {"baholash": "O'tish bali necha?", "nazorat": "Yakuniy nazoratga kim kiritiladi?", "gpa": "GPA qanday hisoblanadi?",
            "kredit": "Kredit nima?", "dars_vaqti": "Dars soat nechida boshlanadi?", "registrator": "Registrator ofisi nima ish qiladi?",
            "registrator_joy": "Registrator ofisi qayerda?", "registrator_murojaat": "Qanday masalada registratorga murojaat qilaman?",
            "akademik_bolim": "Akademik faoliyatni boshqarish bo'limi vazifalari?", "sirtqi_bolim": "Sirtqi bo'lim nima ish qiladi?",
            "malumotlar_bolim": "Ma'lumotlar bazasi bo'limi vazifalari?", "kafedralar": "Xalqaro kafedralar qaysilar?",
            "reyting": "Reyting qanday hisoblanadi?"}

UNIT_TOPIC = {"registrator": AR.REGISTRAR_UNIT, "akademik_bolim": AR.ACADEMIC_UNIT, "sirtqi_bolim": AR.SIRTQI_UNIT,
              "malumotlar_bolim": AR.DB_UNIT}

def rule_topics(n: str) -> list[str]:
    t = [k for k, rx in RULE_RX if rx.search(n)]
    if {"registrator_joy", "registrator_murojaat"} & set(t) and "registrator" in t: t.remove("registrator")   # aniqroq mavzu ustun
    return t

def _hm(t): return t.lstrip("0") if t.startswith("0") else t
def _mins(a, b): return (int(b[:2]) * 60 + int(b[3:])) - (int(a[:2]) * 60 + int(a[3:]))

def rules_data(con, topics: list[str]) -> dict:
    """Mavzular bo'yicha tayyor faktlar. Birinchi fakt — savolga to'g'ridan-to'g'ri javob."""
    from .occupancy import SLOTS
    from .seed import UNIT_HEADS
    out = {}
    for k in topics or list(RULE_ASK):
        if k == "baholash":
            f = [f"Fanni o'zlashtirish uchun kamida {AR.PASS} ball kerak (100 ballik tizimda) — bu «3» baho.",
                 f"Ball nazorat turlari yig'indisidan: oraliq nazorat — maksimal {AR.ORALIQ_MAX}, minimal {AR.ORALIQ_MIN} ball; "
                 f"yakuniy nazorat — maksimal {AR.YAKUNIY_MAX}, minimal {AR.YAKUNIY_MIN} ball.",
                 "Ball → 5 baho → ECTS harfi:"]
            f += [f"  – {lo}–{hi} ball — «{g}», {l}" + (" (o'zlashtirilmagan)" if g == 2 else "") for lo, hi, l, g, _ in AR.SCALE]
            f.append("Fan bitta nazorat turidan iborat bo'lsa, shu nazorat 100 ballik tizimda baholanadi.")
        elif k == "nazorat":
            f = [f"Yakuniy nazoratga oraliq nazoratdan kamida {AR.ADMIT_PCT}% — ya'ni {AR.ORALIQ_MAX} balldan kamida {AR.ORALIQ_MIN} ball "
                 "to'plagan talaba kiritiladi.",
                 "Oraliq nazorat yakuniy nazorat muddatigacha topshirilgan bo'lishi shart; fanning xususiyatiga ko'ra 2 martagacha o'tkazilishi mumkin.",
                 "Oraliq nazorat topshiriqlarini kafedra professor-o'qituvchilari tuzadi, kafedra mudiri tasdiqlaydi.",
                 "Yakuniy nazorat semestr yakunida o'tkaziladi: jadvalni Akademik faoliyatni boshqarish bo'limi tuzadi, o'quv ishlari bo'yicha prorektor tasdiqlaydi.",
                 "Fandan dars bergan o'qituvchi yakuniy nazoratda ishtirok eta olmaydi — uni mashg'ulot olib bormagan professor-o'qituvchi "
                 "yoki imtihon bo'limi o'tkazadi.",
                 f"Ballar: oraliq — maksimal {AR.ORALIQ_MAX} (minimal {AR.ORALIQ_MIN}), yakuniy — maksimal {AR.YAKUNIY_MAX} "
                 f"(minimal {AR.YAKUNIY_MIN}); fan kamida {AR.PASS} ball bilan o'zlashtiriladi."]
        elif k == "gpa":
            ex = AR.GPA_EXAMPLE
            num, cr = sum(c * g for _, c, g in ex), sum(c for _, c, _ in ex)
            f = [f"{AR.GPA_FORMULA} — har bir fanning 5 ballik bahosi shu fan krediti bilan tortiladi.",
                 f"Misol (Korporativ boshqaruv yo'nalishi, 1-semestr): {len(ex)} ta fan, har biri {ex[0][1]} kredit, "
                 f"baholar {', '.join(str(g) for _, _, g in ex)}.",
                 f"  – ({' + '.join(f'{c}×{g}' for _, c, g in ex)}) / {cr} = {num} / {cr} = {AR.gpa([(c, g) for _, c, g in ex]):.1f}",
                 "Kredit bahoga bog'liq emas: fan «3» bilan o'zlashtirilsa ham krediti to'liq olinadi; GPA esa bahoga bog'liq.",
                 "ISFT Core transkriptida GPA shu formula bo'yicha hisoblanadi."]
        elif k == "kredit":
            f = [f"1 kredit = {AR.CREDIT_HOURS} soat: {AR.CREDIT_AUD} soat auditoriya mashg'uloti + {AR.CREDIT_SELF} soat mustaqil ish.",
                 f"Bakalavriat — {AR.BACHELOR_CREDITS} kredit, magistratura — {AR.MASTER_CREDITS} kredit.",
                 "Soatlar taqsimoti: kontakt soat — 40%, mustaqil ta'lim — 60%.",
                 "Kredit — baho emas: 5 kreditlik fanni «3» bahoga o'zlashtirgan talaba 5 kreditni to'liq qo'lga kiritadi.",
                 "Misol: ma'ruza 30 + amaliy mashg'ulot 40 + mustaqil ish 80 = 150 soat = 5 kredit.",
                 "Fanlar: asosiy, tanlov va fakultativ."]
        elif k == "dars_vaqti":
            s1, s2 = SLOTS[:3], SLOTS[3:]
            f = [f"Darslar soat {_hm(s1[0][1])} da boshlanadi: 1-smena {_hm(s1[0][1])}–{s1[-1][2]}, katta tanaffus {s1[-1][2]}–{s2[0][1]}, "
                 f"2-smena {s2[0][1]}–{s2[-1][2]}."]
            f += [f"  – {n_}-para: {_hm(a)}–{b}" + (" (1-smena)" if n_ == 1 else " (2-smena)" if n_ == 4 else "") for n_, a, b in SLOTS]
            f.append(f"Har bir para {_mins(SLOTS[0][1], SLOTS[0][2])} daqiqa, paralar orasida {_mins(SLOTS[0][2], SLOTS[1][1])} daqiqa tanaffus.")
        elif k == "registrator_joy":
            f = [f"Registrator ofisi ikki joyda qabul qiladi: {AR.REGISTRAR_ROOMS_TEXT}."]
            f += [f"  – {i}. {r}" for i, r in enumerate(AR.REGISTRAR_ROOMS, 1)]
            f.append(f"Registrator ofisi boshlig'i — {UNIT_HEADS[AR.REGISTRAR_UNIT]}.")
        elif k == "registrator_murojaat":
            f = ["Registrator ofisiga quyidagi masalalarda murojaat qilinadi:"]
            f += [f"  – {m[0].upper() + m[1:]}" for m, _ in AR.REGISTRAR_CONTACT]
            f.append(f"Manzil: {AR.REGISTRAR_ROOMS_TEXT}. Kontrakt to'lovi summasi va to'lov masalalari — Buxgalteriya bo'limida; "
                     f"akademik taqvim va fanlarga yozilish — {AR.ACADEMIC_UNIT}da.")
        elif k in UNIT_TOPIC:
            u = UNIT_TOPIC[k]
            heads = {**UNIT_HEADS, **AR.OTHER_UNIT_HEADS}
            f = [f"{u} {AR.UNIT_SUMMARY[u]}.", f"{u} boshlig'i — {heads[u]}. Vazifalari ({AR.DUTIES_NOTE.get(u, 'taqdimot bo' + chr(39) + 'yicha')}):"]
            f += [f"  – {d}" for d, _ in AR.DUTIES[u] if not d.startswith("talabalar murojaatlari:")]
            if u == AR.REGISTRAR_UNIT:
                f.append(f"Talabalar murojaat qiladigan masalalar ({AR.REGISTRAR_SOURCE}): " + "; ".join(m for m, _ in AR.REGISTRAR_CONTACT) + ".")
                f.append(f"Manzil: {AR.REGISTRAR_ROOMS_TEXT}.")
            if u == AR.SIRTQI_UNIT:
                f.append("Taqdimotda Sirtqi bo'lim uchun alohida vazifalar ro'yxati berilmagan — yuqoridagi tavsif bo'lim nomidan kelib chiqadi.")
            if u == AR.ACADEMIC_UNIT:
                f.append("Yakuniy nazorat jadvalini shu bo'lim ishlab chiqadi, o'quv ishlari bo'yicha prorektor tasdiqlaydi.")
            others = [x for x in AR.UNIT_DUTIES if x != u]
            f.append("Boshqa bo'limlar: " + "; ".join(f"{x} ({heads[x]}) — {AR.UNIT_SUMMARY[x].split(':')[0]}" for x in others) + ".")
        elif k == "kafedralar":
            heads = {r["name"]: r["head"] for r in db.rows(con, "SELECT name, head FROM departments")}
            line = lambda d, ps: f"  – {d} kafedrasi" + (f" ({heads[d]})" if heads.get(d) else "") + ": " + ", ".join(ps)
            f = [f"Taqdimotga ko'ra {len(AR.INTL_DEPTS)} ta kafedra xalqaro ta'lim yo'nalishlarini, {len(AR.LOCAL_DEPTS)} tasi mahalliy yo'nalishlarni yuritadi.",
                 "Xalqaro ta'lim yo'nalishlari kafedralari:"] + [line(d, ps) for d, ps in AR.INTL_DEPTS.items()] + \
                ["Mahalliy ta'lim yo'nalishlari kafedralari:"] + [line(d, ps) for d, ps in AR.LOCAL_DEPTS.items()]
        elif k == "reyting":
            T = AR.TOP_DEFAULTS
            f = [f"Talabalar reytingi semestr GPA bo'yicha tuziladi: {AR.GPA_FORMULA} — 5 ballik baho fan krediti bilan tortiladi "
                 f"(kredit o'quv dasturidan, ko'rsatilmagan bo'lsa {AR.CREDIT_DEFAULT} kredit).",
                 "Tartib: " + "; ".join(f"{i}) {l[0].lower() + l[1:]}" for i, (_, l, _) in enumerate(AR.RATING_ORDER, 1)) +
                 " — keyingi mezon faqat oldingisi teng bo'lganda hisobga olinadi.",
                 "O'rin besh darajada ko'rsatiladi: " + ", ".join(l.lower() for _, l in AR.RATING_LEVELS) + " — «37 / 1 240» va «yuqori N%» shaklida.",
                 f"Reytingda faqat faol talabalar. «F» (< {AR.PASS} ball) olgan talaba reytingda qoladi, lekin «akademik qarzdor» deb belgilanadi; "
                 f"a'lochi — barcha fanlardan «5» ({AR.EXCELLENT_MIN} balldan yuqori).",
                 f"Mukofot ro'yxati (standart): kurs bo'yicha eng yaxshi {T['pct']}%, «F» yo'q, davomat kamida {T['min_att']:g}%.",
                 "Batafsil — ISFT Core «Reyting» bo'limidagi «Metodika»: ro'yxat va qaydnomani Registrator ofisi va Akademik bo'lim to'liq ko'radi, "
                 "rahbariyat kuzatuvi uchun — jamlangan ko'rsatkichlar."]
        else:
            continue
        out[k] = f
    reg = {"registrator", "registrator_joy", "registrator_murojaat"} & set(out)
    src = ([AR.REGISTRAR_SOURCE] if reg else []) + ([AR.SOURCE] if set(out) - {"registrator_joy", "registrator_murojaat"} else [])
    return {"topics": out, "sources": src, "pass": AR.PASS, "scale": AR.SCALE, "slots": SLOTS, "rooms": AR.REGISTRAR_ROOMS}

def an_rules(con, ctx, v, why):
    topics = v["topics"]
    if len(topics) == 1:
        facts = next(iter(topics.values()))
    else:   # bir nechta mavzu yoki umumiy savol — har biridan asosiy qoida
        facts = ["Akademik qoidalar bo'yicha qisqacha:"] + [f[0] for f in topics.values()]
    return {"facts": facts, "why": [], "recs": [], "sev": 0, "head": "akademik qoidalar"}

# ------------------------------------------------------------------------------------------------
# Tahlil vositalari (raqamlarni kod hisoblaydi)
# ------------------------------------------------------------------------------------------------
# Fan turlari (o'quv rejasi tuzilmasi — app/seed.py): har semestrda fanlar boshqa, shuning uchun bir xil fanni semestrlararo solishtirib
# bo'lmaydi. Solishtirish — guruh, kurs, fakultet va fan TURI darajasida (bir xil talabalar, ketma-ket ikki yakunlangan semestr).
CAT_ORDER = ["Umumta'lim (ijtimoiy-gumanitar)", "Til fanlari", "Yo'nalish tayanch fanlari", "Mutaxassislik fanlari", "Umumkasbiy fanlar",
             "Amaliyot va bitiruv ishi", "Boshqa fanlar"]
_SUBJ_CAT: dict | None = None

def subject_category(subject: str) -> str:
    global _SUBJ_CAT
    if _SUBJ_CAT is None:
        from . import seed as SD
        m = {}
        for x in SD.FINAL_B + SD.FINAL_M: m.setdefault(x[0], CAT_ORDER[5])
        for x in SD.GEN_LOCAL + SD.GEN_INTL: m.setdefault(x, CAT_ORDER[0])
        for x in SD.LANG_TRACK: m.setdefault(x, CAT_ORDER[1])
        for v in SD.SUBJECTS.values():
            for x in v: m.setdefault(x, CAT_ORDER[2])
        for v in list(SD.EXTRA.values()) + [SD.MASTER_POOL]:
            for x in v: m.setdefault(x, CAT_ORDER[3])
        for v in SD.POOL.values():
            for x in v: m.setdefault(x, CAT_ORDER[4])
        _SUBJ_CAT = m
    return _SUBJ_CAT.get(subject, CAT_ORDER[6])

def _pair(now_avg, prev_avg, now_pass, prev_pass):
    """Ko'rsatilgan (yaxlitlangan) raqamlardan farq — matndagi «A dan B ga (−C)» doim mos keladi."""
    a, b = (round(prev_avg, 1) if prev_avg is not None else None), (round(now_avg, 1) if now_avg is not None else None)
    pa, pb = (round(prev_pass, 1) if prev_pass is not None else None), (round(now_pass, 1) if now_pass is not None else None)
    return {"prev": a, "now": b, "drop": round(a - b, 1) if a is not None and b is not None else None,
            "pass_prev": pa, "pass_now": pb, "pass_drop": round(pa - pb, 1) if pa is not None and pb is not None else None}

def academic_drivers(con, ctx: Ctx, groups: list[dict]):
    """Pasaygan guruhlar nega pasaygan. Ikki oxirgi yakunlangan semestr (RATING_SEMESTER va undan oldingi) solishtiriladi — o'sha talabalar,
    lekin fanlar har semestrda boshqa. Shuning uchun: guruhlar (pasaygan ↔ qolgan), kurs, fakultet va fan turi kesimida o'rtacha ball (100)
    va o'tish ulushi (ball ≥ o'tish bali); davomat va kontrakt bosimi — pasaygan guruhlar ↔ qolganlar."""
    if not groups: return None
    names = sorted({g["name"] for g in groups})
    sc = ctx.student_scope("s")
    ph = ",".join("?" * len(names))
    t1, t0 = AR.RATING_SEMESTER, AR.RATING_SEMESTER - 1
    coh = db.one(con, f"""SELECT COUNT(*) n, ROUND(AVG(s.attendance),1) att,
        ROUND(100.0*SUM(s.payment_type='kontrakt' AND s.contract_amount>0 AND s.paid_amount*2 < s.contract_amount)/COUNT(*),1) debt
        FROM students s JOIN groups_ g ON g.id=s.group_id WHERE {sc} AND s.status='faol' AND g.name IN ({ph})""", names)
    rest = db.one(con, f"""SELECT ROUND(AVG(s.attendance),1) att,
        ROUND(100.0*SUM(s.payment_type='kontrakt' AND s.contract_amount>0 AND s.paid_amount*2 < s.contract_amount)/COUNT(*),1) debt
        FROM students s JOIN groups_ g ON g.id=s.group_id WHERE {sc} AND s.status='faol' AND g.name NOT IN ({ph})""", names)
    agg = (f"AVG(CASE WHEN gr.semester={t1} THEN gr.score END) a1, AVG(CASE WHEN gr.semester={t0} THEN gr.score END) a0, "
           f"100.0*SUM(gr.semester={t1} AND gr.score>={AR.PASS})/NULLIF(SUM(gr.semester={t1}),0) p1, "
           f"100.0*SUM(gr.semester={t0} AND gr.score>={AR.PASS})/NULLIF(SUM(gr.semester={t0}),0) p0")
    base = (f"FROM grades gr JOIN students s ON s.id=gr.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id "
            f"WHERE {sc} AND s.status='faol' AND gr.semester IN ({t1},{t0}) AND gr.score IS NOT NULL")
    cmp = {}
    for r in db.rows(con, f"SELECT (g.name IN ({ph})) coh, {agg} {base} GROUP BY 1", names):
        cmp["cohort" if r["coh"] else "rest"] = _pair(r["a1"], r["a0"], r["p1"], r["p0"])
    def cut(col):
        out = []
        for r in db.rows(con, f"SELECT {col} k, COUNT(DISTINCT s.id) n, {agg} {base} GROUP BY 1"):
            if r["a0"] is None or r["a1"] is None: continue      # 1-kurs: yakunlangan semestr yo'q
            out.append({"key": r["k"], "n": r["n"], **_pair(r["a1"], r["a0"], r["p1"], r["p0"])})
        return sorted(out, key=lambda x: -(x["drop"] or 0))
    by_course, by_faculty = cut("g.course"), cut("f.name")
    cats = {}
    for r in db.rows(con, f"""SELECT gr.subject, gr.semester sem, SUM(gr.score) s, COUNT(*) n, SUM(gr.score>={AR.PASS}) p {base} AND g.name IN ({ph})
                              GROUP BY gr.subject, gr.semester""", names):
        c = cats.setdefault(subject_category(r["subject"]), {t1: [0, 0, 0], t0: [0, 0, 0]})
        c[r["sem"]][0] += r["s"]; c[r["sem"]][1] += r["n"]; c[r["sem"]][2] += r["p"]
    by_cat = []
    for k, v in cats.items():
        if v[t1][1] < 30 or v[t0][1] < 30: continue             # ikkala semestrda ham yetarli baho bo'lgan fan turlari
        by_cat.append({"key": k, **_pair(v[t1][0] / v[t1][1], v[t0][0] / v[t0][1], 100 * v[t1][2] / v[t1][1], 100 * v[t0][2] / v[t0][1])})
    by_cat.sort(key=lambda x: -(x["drop"] or 0))
    fac = {}
    for g in groups: fac[(g["faculty"], g["course"])] = fac.get((g["faculty"], g["course"]), 0) + 1
    (top_fac, top_course), top_n = max(fac.items(), key=lambda x: x[1])
    return {"cohort": coh, "rest": rest, "compare": cmp, "by_course": by_course, "by_faculty": by_faculty, "categories": by_cat,
            "top_faculty": top_fac, "top_course": top_course, "top_n": top_n, "groups": len(names),
            "sem": AR.SEMESTER_SHORT[t1], "prev_sem": AR.SEMESTER_SHORT[t0], "pass": AR.PASS}

def contract_forecast(con):
    """O'quv yili oxiriga tushum prognozi: grafik bo'yicha to'layotganlar to'liq to'laydi, ortda qolganlar qolgan qarzning yarmini."""
    today = clock.today()
    plan_ = db.rows(con, "SELECT * FROM contract_plan ORDER BY due") if db.one(con, "SELECT name FROM sqlite_master WHERE name='contract_plan'") else []
    passed = [p for p in plan_ if p["due"] < today.isoformat()]
    nxt = next((p for p in plan_ if p["due"] >= today.isoformat()), None)
    need_pct = passed[-1]["cum_pct"] if passed else 0
    rows = con.execute("SELECT contract_amount a, paid_amount p FROM students WHERE payment_type='kontrakt' AND contract_amount>0").fetchall()
    total = sum(r[0] for r in rows); paid = sum(r[1] for r in rows)
    exp = 0.0
    for a, p in rows:
        rem = a - p
        exp += rem * (0.97 if p * 100 >= a * need_pct else 0.5)
    fpct = round(100 * (paid + exp) / total, 1) if total else 0
    out = {"total": total, "paid": paid, "pct_now": round(100 * paid / total, 1) if total else 0, "forecast_pct": fpct,
           "gap": int(total - paid - exp), "need_pct": need_pct}
    if nxt:
        behind = [(a, p) for a, p in rows if p * 100 < a * nxt["cum_pct"]]
        out["next"] = {"label": nxt["label"], "due": nxt["due"], "days": (dt.date.fromisoformat(nxt["due"]) - today).days, "pct": nxt["cum_pct"],
                       "behind": len(behind), "need": int(sum(a * nxt["cum_pct"] / 100 - p for a, p in behind))}
    return out

def dmy(iso): return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso and len(iso) >= 10 else (iso or "")

def task_action(title, assignee, role, text, days=7, agent="ijro"):
    return {"type": "propose", "label": title, "agent": agent,
            "payload": {"effect": "task", "assignee": assignee, "role": role, "text": text, "due": (clock.today() + dt.timedelta(days=days)).isoformat()}}

# ------------------------------------------------------------------------------------------------
# Har bir yo'nalish bo'yicha: faktlar, sabablar, tavsiyalar (+ og'irlik — strategik xulosa uchun)
# ------------------------------------------------------------------------------------------------
def an_academic(con, ctx, v, why):
    t = v["total"]; dg = v["declining_groups"]
    if not t["n"]:
        return {"facts": [f"{v['scope']}: kafedraga biriktirilgan talabalar guruhi yo'q — bu kafedra institut miqyosida fan o'qitadi."],
                "why": [], "recs": [], "sev": 0, "head": "guruhlar yo'q"}
    facts = [f"{v['scope']}: {S_n(t['n'])} faol talaba, o'rtacha ball {t['gpa']} (o'tgan semestr {t['gpa_prev']}), davomat {t['attendance']}%."]
    reasons, recs, sev = [], [], 1
    if dg:
        sev = 3
        cl = v.get("declining_clusters") or []
        if cl:   # bir fakultet+kurs guruhlari — bitta ildiz sabab sifatida
            facts += [S.decline_text(c) + "." for c in cl[:2]]
        facts.append(f"Keskin (4 balldan ko'p) pasaygan guruhlar: {v.get('declining_count', len(dg))} ta; eng ko'p: " +
                     ", ".join(f"{g['name']} ({g['gpa_prev']} → {g['gpa']}, {S._num(g['delta'])})" for g in dg[:3]) + ".")
        allg = [{"name": n, "faculty": c["faculty"], "course": c["course"]} for c in cl for n in c["group_names"]] or dg
        d = academic_drivers(con, ctx, allg)
        if d: v["drivers"] = d          # manba ma'lumotiga qo'shiladi — javobdagi har bir raqam shu faktlar bilan solishtiriladi
        if d:
            c, r = d["cohort"], d["rest"]
            reasons.append(f"Pasaygan {d['groups']} ta guruhdan {d['top_n']} tasi bitta joyda: {d['top_faculty']}, {d['top_course']}-kurs.")
            if c["att"] is not None and r["att"] is not None and r["att"] - c["att"] >= 3:
                reasons.append(f"Bu guruhlarda davomat {c['att']}% — qolgan talabalarda {r['att']}%. Darsga kelmaslik pasayishning birinchi omili.")
            if c["debt"] is not None and r["debt"] is not None and c["debt"] - r["debt"] >= 2:
                reasons.append(f"Kontraktning yarmidan kamini to'laganlar ulushi {c['debt']}% (qolganlarda {r['debt']}%) — moliyaviy bosim ham bor.")
            cc, rr = d["compare"].get("cohort"), d["compare"].get("rest")
            if cc and cc["pass_drop"] is not None:
                reasons.append(f"O'tish ulushi (ball ≥ {AR.PASS}) bu guruhlarda {cc['pass_prev']}% dan {cc['pass_now']}% ga tushgan ({d['prev_sem']} → {d['sem']})"
                               + (f"; qolgan guruhlarda {rr['pass_prev']}% → {rr['pass_now']}%." if rr and rr["pass_now"] is not None else "."))
            bc, bf = d["by_course"], d["by_faculty"]
            if len(bc) >= 2 and bc[0]["drop"] is not None:
                reasons.append(f"Kurs kesimida eng katta pasayish — {bc[0]['key']}-kurs: o'rtacha ball {bc[0]['prev']} dan {bc[0]['now']} ga; "
                               f"eng kichigi — {bc[-1]['key']}-kurs: {bc[-1]['prev']} dan {bc[-1]['now']} ga."
                               + (f" Fakultet kesimida: {bf[0]['key']} — {bf[0]['prev']} dan {bf[0]['now']} ga." if bf and bf[0]["drop"] is not None and bf[0]["drop"] > 0 else ""))
            ca = [x for x in d["categories"] if x["drop"] is not None]
            if len(ca) >= 2:
                if ca[0]["drop"] - ca[-1]["drop"] < 3:
                    reasons.append(f"Fan turlari bo'yicha pasayish deyarli bir xil ({ca[-1]['key'].lower()}: {ca[-1]['prev']} → {ca[-1]['now']}; "
                                   f"{ca[0]['key'].lower()}: {ca[0]['prev']} → {ca[0]['now']}) — muammo bitta fan yoki o'qituvchida emas, kurs darajasida.")
                else:
                    reasons.append(f"Fan turlari kesimida eng ko'p tushgani — {ca[0]['key'].lower()} ({ca[0]['prev']} → {ca[0]['now']}), "
                                   f"eng kami — {ca[-1]['key'].lower()} ({ca[-1]['prev']} → {ca[-1]['now']}).")
            fac_short = d["top_faculty"] + ("" if "fakultet" in d["top_faculty"].lower() else " fakulteti")
            # institutda dekan lavozimi yo'q (Yevropa modeli) — fakultet darajasidagi vazifa Registrator ofisiga (fakultet tyutorlari bilan)
            recs.append({"text": f"Registrator ofisiga: {fac_short} {d['top_course']}-kurs guruhlarida 7 kun ichida davomat tekshiruvi va fakultet tyutorlari bilan har bir qiynalayotgan talaba suhbati.",
                         "action": task_action("Registrator ofisiga topshiriq berish", "Registrator ofisi", "talabalar",
                                               f"{d['top_course']}-kurs pasaygan guruhlarida ({', '.join(g['name'] for g in dg[:4])}) davomat tekshiruvi va tyutor suhbatlari; natijani rektorga yozma taqdim etish")})
            if c["debt"] is not None and r["debt"] is not None and c["debt"] - r["debt"] >= 2:
                recs.append({"text": "Shu guruhlardagi kontrakt qarzdorlariga muddatli to'lov jadvali taklif qilish — Talabalar markazi navbatida.",
                             "action": {"type": "go", "view": "ops", "label": "Talabalar markazini ochish"}})
            recs.append({"text": "2 haftadan so'ng takroriy monitoring: shu guruhlar bo'yicha ISFT Core avtomatik solishtiradi.", "action": None})
    else:
        facts.append("Keskin pasaygan guruh yo'q.")
    return {"facts": facts, "why": reasons, "recs": recs, "sev": sev, "head": f"o'zlashtirish {t['gpa']} ({round(t['gpa'] - t['gpa_prev'], 1):+})"}

def S_n(x): return f"{x:,}".replace(",", " ")

def ops_open_cases(con, ctx):
    """Talabalar markazidagi ochiq holatlar (barcha qoidalar) — "O'qishda xavf"dan farqli ko'rsatkich (holatlar, talabalar emas)."""
    if not ctx.can("ops") or not db.one(con, "SELECT 1 x FROM sqlite_master WHERE name='ops_cases'"): return None
    r = db.one(con, f"""SELECT COUNT(*) n, SUM(oc.level>=2) crit FROM ops_cases oc JOIN students s ON s.id=oc.student_id
                        WHERE oc.status='ochiq' AND {ctx.student_scope('s')}""")
    return r if r and r["n"] else None

def an_risk(con, ctx, v, why):
    facts = [f"O'qishda xavf: {S_n(v['count'])} nafar talaba ({S_n(v['of'])} faol talabadan, {round(100 * v['count'] / max(1, v['of']), 1)}%) — "
             "o'zlashtirish yoki davomat bo'yicha «kritik»/«jiddiy» holati borlar. Kontrakt qarzi bu songa kirmaydi."]
    if v["by_group"]:
        facts.append("Eng ko'p: " + ", ".join(f"{g['group']} ({g['count']} nafar)" for g in v["by_group"][:4]) + ".")
    if v.get("students"):
        facts += [f"  – {s['full_name']} ({s['grp']}): {s['reasons']}" for s in v["students"][:5]]
    elif v.get("note"):
        facts.append(f"{v['note']}.")
    oc = ops_open_cases(con, ctx)
    if oc:
        facts.append(f"Talabalar markazida jami {S_n(oc['n'])} ta ochiq holat bor, shundan {S_n(oc['crit'] or 0)} tasi kritik/jiddiy — bu boshqa ko'rsatkich: "
                     "barcha qoidalar (kontrakt, hujjat, ta'til va h.k.) bo'yicha holatlar soni, bitta talabada bir nechta bo'lishi mumkin.")
    recs = [{"text": "Har bir holat Talabalar markazida mas'ulga biriktirilgan (call-markaz, tyutor, registrator). Kechikkanlarini tekshiring.",
             "action": {"type": "go", "view": "ops", "label": "Talabalar markazini ochish"}}]
    return {"facts": facts, "why": [], "recs": recs, "sev": 2, "head": f"o'qishda xavf: {S_n(v['count'])} talaba"}

def an_contracts(con, ctx, v, why):
    t = v["total"]; f = contract_forecast(con)
    facts = [f"Tushum {t['pct']}%: {S.mln(t['paid'])} / {S.mln(t['total'])}. Qarz {S.mln(t['debt'])}, qarzdorlar {S_n(t['debtors'])} nafar.",
             "Eng past tushum: " + ", ".join(f"{g['grp']} ({g['pct']}%)" for g in v["worst_groups"][:3]) + "."]
    reasons = [f"Prognoz: hozirgi to'lov intizomi saqlansa, o'quv yili oxiriga tushum ~{f['forecast_pct']}% bo'ladi — {S.mln(f['gap'])} yig'ilmay qoladi."]
    recs = []
    nx = f.get("next")
    if nx:
        reasons.append(f"{nx['label']} ({nx['pct']}%) muddati {dmy(nx['due'])}, {nx['days']} kun qoldi: {S_n(nx['behind'])} nafar talaba hali yetarli to'lamagan ({S.mln(nx['need'])}).")
        recs.append({"text": f"{nx['label']} oldidan {S_n(nx['behind'])} talabaga call-markaz qo'ng'irog'i va SMS — navbat Talabalar markazida tayyor.",
                     "action": {"type": "go", "view": "ops", "label": "Qo'ng'iroqlar navbati"}})
    recs.append({"text": f"Moliya prorektoriga: eng past tushumli guruhlar ({', '.join(g['grp'] for g in v['worst_groups'][:3])}) uchun muddatli to'lov jadvalini e'lon qilish.",
                 "action": task_action("Moliya prorektoriga topshiriq", "Moliya-iqtisod ishlari bo'yicha prorektor", "prorektor_moliya",
                                       f"Eng past tushumli guruhlar ({', '.join(g['grp'] for g in v['worst_groups'][:3])}) uchun muddatli to'lov jadvalini e'lon qilish", 5, "moliya")})
    sev = 3 if f["forecast_pct"] < 90 else 2
    return {"facts": facts, "why": reasons, "recs": recs, "sev": sev, "head": f"kontrakt tushumi {t['pct']}%, yil oxiriga prognoz ~{f['forecast_pct']}%"}

def an_finance(con, ctx, v, why):
    t = v["total"]
    facts = [f"Byudjet ijrosi {t['pct']}%: {S.mln(t['actual'])} / {S.mln(t['planned'])}."]
    reasons, recs, sev, head = [], [], 1, f"byudjet ijrosi {t['pct']}%"
    if v["overruns"]:
        o = v["overruns"][0]; cat = o["category"]
        seq = [x for x in v["overruns"] if x["category"] == cat]
        over_sum = sum(x["actual"] - x["planned"] for x in seq)
        months_left = max(0, 12 - len(v["months"]))
        avg = over_sum // max(1, len(seq))
        facts.append(f"{cat}: ketma-ket {len(seq)} oy rejadan oshgan (oxirgisi {o['month']} — {o['over_pct']}%). Ortiqcha sarf: {S.mln(over_sum)}.")
        reasons.append(f"{cat} ketma-ket {len(seq)} oy rejadan oshgan: jami {S.mln(over_sum)} ortiqcha sarf.")
        if "ommunal" in cat:
            reasons.append("Oshish isitish mavsumi bilan mos keladi; tariflar o'zgarishi yoki hisoblagich ko'rsatkichlari tekshirilishi kerak.")
        reasons.append(f"Shu sur'at davom etsa, yil oxirigacha yana ~{S.mln(avg * months_left)} ortiqcha sarf bo'ladi ({months_left} oy).")
        recs.append({"text": f"Buxgalteriyadan {cat.lower()} bo'yicha solishtirma dalolatnoma (hisoblagich + tarif) so'rash, 5 kun.",
                     "action": task_action("Buxgalteriyaga topshiriq", "Buxgalteriya bo'limi", "buxgalteriya",
                                           f"{cat} bo'yicha so'nggi {len(seq)} oy uchun solishtirma dalolatnoma (hisoblagich ko'rsatkichlari va tariflar) tayyorlash", 5, "moliya")})
        sev, head = 2, f"{cat.lower()} {len(seq)} oy rejadan oshgan"
    return {"facts": facts, "why": reasons, "recs": recs, "sev": sev, "head": head}

def an_tasks(con, ctx, v, why):
    od = [t for t in v["tasks"] if t["overdue"]]
    facts = [f"Topshiriqlar: {len(v['tasks'])} ta, bajarilgan {v['done']}, muddati o'tgan {v['overdue']}."]
    for t in od[:4]:
        late = -t["days"] if t.get("days") is not None else None
        facts.append(f"  – {t['assignee']}: {t['text']} (muddat {dmy(t.get('due_at') or t['due'])}" + (f", {late} kun kechikdi)" if late else ")"))
    recs = []
    if od:
        recs.append({"text": f"Muddati o'tgan {len(od)} ta topshiriq bo'yicha ijrochilarga rasmiy eslatma va yangi muddatni yozma so'rash.",
                     "action": {"type": "propose", "label": "Eslatmalarni yuborish", "agent": "ijro",
                                "payload": {"effect": "remind", "task_ids": [t["id"] for t in od]}}})
    return {"facts": facts, "why": [], "recs": recs, "sev": 3 if od else 1, "head": f"{len(od)} ta topshiriq muddati o'tgan" if od else "topshiriqlar muddatida"}

def an_international(con, ctx, v, why):
    facts = [f"Faol hamkorlar: {v['active']}, almashinuvda {v['exchanged']} talaba."]
    recs = []
    for p in v["expiring"][:3]:
        facts.append(f"  – {p['name']} ({p['country']}): shartnoma {p['days_left']} kundan keyin tugaydi.")
        recs.append({"text": f"{p['name']} bilan uzaytirish xatini shu hafta yuborish.",
                     "action": task_action("Xalqaro bo'limga topshiriq", "Xalqaro hamkorlik bo'limi", "xalqaro",
                                           f"{p['name']} ({p['country']}) bilan hamkorlik shartnomasini uzaytirish xatini tayyorlash va yuborish", 5, "hujjat")})
    return {"facts": facts, "why": [], "recs": recs, "sev": 2 if v["expiring"] else 1,
            "head": f"{len(v['expiring'])} ta xalqaro shartnoma tugamoqda" if v["expiring"] else "xalqaro shartnomalar joyida"}

def an_science(con, ctx, v, why):
    sc = sum(k["n"] for k in v["kinds_2026"] if k["kind"] in ("Scopus", "Web of Science"))
    facts = [f"2026: Scopus/WoS {sc} ta maqola, ilmiy darajalilik {v['degree_pct']}%, 2025 yildan beri nashrsiz {v['no_pubs_since_2025']} o'qituvchi."]
    weak = [d for d in v["by_department"] if d["scopus"] == 0]
    reasons = []
    if v["by_department"]:
        top = v["by_department"][0]
        facts.append(f"Eng faol kafedra: {top['name']} ({top['scopus']} ta). Scopus'siz kafedralar: {len(weak)} ta.")
        if weak: reasons.append("Scopus'siz kafedralar: " + ", ".join(d["name"] for d in weak[:3]) + ".")
    recs = [{"text": f"Ilmiy bo'limga: nashrsiz {v['no_pubs_since_2025']} o'qituvchi uchun individual ilmiy reja va Scopus jurnallari bo'yicha seminar.",
             "action": task_action("Ilmiy bo'limga topshiriq", "Ilmiy tadqiqotlar bo'limi", "ilmiy_bolim",
                                   f"2025 yildan beri nashri yo'q {v['no_pubs_since_2025']} o'qituvchi uchun individual ilmiy reja tuzish", 14, "ijro")}]
    return {"facts": facts, "why": reasons, "recs": recs, "sev": 1, "head": f"Scopus/WoS 2026: {sc} ta"}

def an_cameras(con, ctx, v, why):
    from . import camsec
    return camsec.agent_facts(v)

def an_facecam(con, ctx, v, why):
    from . import facecam
    return facecam.agent_facts(v)

ANALYZERS = {"facecam": an_facecam, "cameras": an_cameras, "qoidalar": an_rules, "academic": an_academic, "risk": an_risk, "contracts": an_contracts, "finance": an_finance, "tasks": an_tasks,
             "international": an_international, "science": an_science}

def an_generic(name, v):
    txt = ai.fallback_answer({name: v}, [])
    return {"facts": [l for l in txt.splitlines() if l.strip()], "why": [], "recs": [], "sev": 1, "head": TOOL_LABEL.get(name, name).lower()}

FOLLOWUPS = {
    "academic": ["Nega pasaydi?", "Xavf ostidagi talabalar qaysi guruhlarda?"],
    "risk": ["Kontrakt qarzdorligi qanday?", "Qaysi guruhlarda o'zlashtirish pasaygan?"],
    "contracts": ["Yil oxiriga tushum qancha bo'ladi?", "Qaysi xarajat rejadan oshgan?"],
    "finance": ["Kommunal xarajatlar nega oshdi?", "Kontrakt tushumi qanday?"],
    "tasks": ["Qaysi yo'nalishda ortda qolyapmiz?"],
    "international": ["Ilmiy faoliyat qanday?"],
    "science": ["Qaysi xalqaro shartnomalar tugayapti?"],
}

# ------------------------------------------------------------------------------------------------
# Raqamlarni tekshirish
# ------------------------------------------------------------------------------------------------
NUM = re.compile(r"\d+(?:[.,]\d+)?")

def verify(text: str, source: str) -> dict:
    src = {x.replace(",", ".") for x in NUM.findall(source.replace(" ", ""))} | {x.replace(",", ".") for x in NUM.findall(source)}
    found = [x.replace(",", ".") for x in NUM.findall(text)]
    found = [x for x in found if not (x.isdigit() and int(x) <= 12)]     # ro'yxat raqamlari, oylar, kurslar
    bad = sorted({x for x in found if x not in src})
    return {"n": len(found), "ok": len(found) - sum(1 for x in found if x in bad), "bad": bad[:5]}

# ------------------------------------------------------------------------------------------------
def compose(parts: list[tuple[str, dict]], strategic: bool, why: bool) -> dict:
    """Bo'limlar → yagona javob tuzilmasi."""
    parts = sorted(parts, key=lambda p: -p[1]["sev"]) if strategic else parts
    if strategic:
        hot = [p for p in parts if p[1]["sev"] >= 2][:3] or parts[:2]
        summary = "Eng ko'p e'tibor talab qiladigan yo'nalishlar: " + "; ".join(p[1]["head"] for p in hot) + "."
        facts = [f["facts"][0] for _, f in parts]
        reasons = [r for _, f in hot for r in f["why"][:2]]
        recs = [r for _, f in hot for r in f["recs"][:2]][:5]
    else:
        main = parts[0][1]
        summary = (main["why"][0] if why and main["why"] else main["facts"][0])
        facts = [x for _, f in parts for x in f["facts"] if x != summary]
        reasons = [r for _, f in parts for r in f["why"] if r != summary]
        recs = [r for _, f in parts for r in f["recs"]][:5]
    return {"summary": summary, "facts": facts[:9], "why": reasons[:5], "recs": recs}

def as_text(c: dict) -> str:
    out = [c["summary"], ""]
    out += [f"• {x}" if not x.startswith("  –") else x for x in c["facts"]]
    if c["why"]: out += ["", "Nega:"] + [f"• {x}" for x in c["why"]]
    if c["recs"]: out += ["", "Tavsiya:"] + [f"{i}. {r['text']}" for i, r in enumerate(c["recs"], 1)]
    return "\n".join(out).strip()

def ev(**kw): return json.dumps(kw, ensure_ascii=False, default=str) + "\n"

async def run(con, ctx: Ctx, q: str):
    """NDJSON hodisalar oqimi: step (qadamlar), answer (yakuniy javob)."""
    t0 = time.time()
    audit(con, ctx, "agentga savol", "chat", True, q)
    mem = MEMORY.get(ctx.user["id"])
    if mem and time.time() - mem["ts"] > MEM_TTL: mem = None
    names, is_why, strategic, follow = plan(q, mem)
    if not names and await ai.llm_available():
        names = await ai.classify(q)
    lbl = ("Strategik xulosa: bir nechta manba" if strategic else
           "Oldingi savol davomi: " + ", ".join(TOOL_LABEL.get(n, n).lower() for n in names) if follow else
           ("Manbalar: " + ", ".join(TOOL_LABEL.get(n, n).lower() for n in names)) if names else "Mos manba topilmadi")
    if is_why: lbl += " · sabab tahlili"
    yield ev(t="step", id="plan", label="Savolni tahlil qildim — " + lbl, status="done")
    data, denied = {}, []
    for n in names:
        yield ev(t="step", id=n, label=TOOL_LABEL.get(n, n), status="run")
        await asyncio.sleep(0.12)
        try:
            if n == "qoidalar":   # me'yoriy ma'lumot — RBAC talab qilmaydi; mavzu savoldan (yoki oldingi savoldan)
                rt = rule_topics(ai.norm(q)) or (mem or {}).get("rules") or []
                data[n] = rules_data(con, rt)
            else:
                data[n] = ai.TOOLS[n][0](con, ctx)
            yield ev(t="step", id=n, label=TOOL_LABEL.get(n, n), status="done")
        except AccessDenied as e:
            denied.append(str(e))
            yield ev(t="step", id=n, label=TOOL_LABEL.get(n, n), status="denied", note=str(e))
    if not data:
        txt = "\n".join(denied) if denied else ("Savolni aniqlashtiring. Masalan: o'zlashtirish, kontrakt, byudjet, ilmiy faoliyat, "
                                                  "xalqaro hamkorlik, qabul, topshiriqlar yoki «Qaysi yo'nalishda ortda qolyapmiz?»")
        yield ev(t="answer", mode="kod", text=txt, structured=None, sources=[], denied=denied, verify=None, actions=[],
                 followups=["Qaysi yo'nalishda ortda qolyapmiz?", "Kontrakt tushumi qanday?"], ms=int(1000 * (time.time() - t0)))
        return
    yield ev(t="step", id="analyze", label="Sabablarni izladim va tavsiyalarni raqamlar asosida tuzdim" if (is_why or strategic) else "Tavsiyalarni raqamlar asosida tuzdim", status="done")
    parts = []
    for n, v in data.items():
        try:
            parts.append((n, (ANALYZERS[n](con, ctx, v, is_why) if n in ANALYZERS else an_generic(n, v))))
        except Exception:
            parts.append((n, an_generic(n, v)))
    c = compose(parts, strategic, is_why)
    if denied: c["facts"].append(" ".join(d.replace("⛔ ", "") for d in denied))
    text = as_text(c)
    source_blob = json.dumps(data, ensure_ascii=False, default=str) + "\n" + text
    mode = "kod"
    if "qoidalar" not in data and await ai.llm_available():   # qoida matni tahrirlanmaydi — taqdimotdagi ifoda saqlanadi
        yield ev(t="step", id="llm", label=f"Mahalliy AI ({ai.MODEL}) matnni tahrir qilmoqda", status="run")
        try:
            sysmsg = ai.SYSTEM.format(inst="ISFT instituti", today=clock.today().isoformat(), who=ctx.user["full_name"], role=ctx.role.title, scope=ctx.scope_label(con))
            out = await ai.llm_once([{"role": "system", "content": sysmsg + "\n9. Senga tayyor javob qoralamasi beriladi. Uni ravon, rasmiy o'zbek tilida qayta yoz. "
                                      "Raqamlar, guruh nomlari va tavsiyalar tartibini O'ZGARTIRMA. Yangi raqam qo'shma. 180 so'zdan oshmasin."},
                                     {"role": "user", "content": f"SAVOL: {q}\n\nQORALAMA:\n{text}"}], max_tokens=600)
            vv = verify(out, source_blob)
            if out.strip() and not vv["bad"]:
                text, mode = out.strip(), "ai"
                yield ev(t="step", id="llm", label=f"Mahalliy AI ({ai.MODEL}) matnni tahrir qildi", status="done")
            else:
                yield ev(t="step", id="llm", label="AI matnida manbada yo'q raqam topildi — kod tuzgan matn ko'rsatiladi", status="denied")
        except Exception:
            yield ev(t="step", id="llm", label="Mahalliy AI javob bermadi — kod tuzgan matn ko'rsatiladi", status="denied")
    vr = verify(text, source_blob)
    yield ev(t="step", id="verify", label=f"Javobdagi {vr['n']} ta raqamni manba bilan solishtirdim: {vr['ok']} tasi mos", status="done" if not vr["bad"] else "denied")
    main = max(parts, key=lambda p: p[1]["sev"])[0] if strategic else parts[0][0]
    MEMORY[ctx.user["id"]] = {"topics": [n for n in data], "main": main, "ts": time.time(),
                              "rules": list(data["qoidalar"]["topics"]) if "qoidalar" in data else []}
    fu = []
    for n in data:
        for x in FOLLOWUPS.get(n, []):
            if x not in fu and ai.norm(x) != ai.norm(q) and not (is_why and x.startswith("Nega")) and not ("yil oxiri" in ai.norm(q) and "yil oxiri" in ai.norm(x)): fu.append(x)
    if "qoidalar" in data:
        seen = set(data["qoidalar"]["topics"])
        fu = [x for k, x in RULE_ASK.items() if k not in seen or len(seen) > 1][:3]
    elif not is_why and not strategic: fu.insert(0, "Nega?")
    yield ev(t="answer", mode=mode, text=text, structured=c if mode == "kod" else None,
             sources=[x for n in data for x in (data[n]["sources"] if n == "qoidalar" else [TOOL_LABEL.get(n, n)])], denied=denied, verify=vr,
             actions=[r["action"] for r in c["recs"] if r.get("action")], followups=fu[:4], ms=int(1000 * (time.time() - t0)))

def forget(user_id: int):
    MEMORY.pop(user_id, None)

# ------------------------------------------------------------------------------------------------
# Favqulodda kirish (break-glass): rektor sababini yozib, xavf ostidagi talabalar ro'yxatini ochadi
# ------------------------------------------------------------------------------------------------
def breakglass(con, ctx: Ctx, reason: str):
    if ctx.role.key != "rektor":
        raise AccessDenied("⛔ Favqulodda kirish faqat rektor uchun.")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ValueError("Sababni to'liqroq yozing (kamida 10 belgi).")
    role = replace(ctx.role, aggregate_only=frozenset(x for x in ctx.role.aggregate_only if x != "students"))
    c2 = Ctx(ctx.user, role, ctx.channel)
    out = S.at_risk_students(con, c2, limit=25, quiet=True)
    audit(con, ctx, "FAVQULODDA KIRISH: xavf ostidagi talabalar ro'yxati", "students", True, reason)
    return out
