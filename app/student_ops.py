"""Talabalar bilan ishlash markazi (Registrator ofisi, tyutorlar, call-markaz).

Dizayn: docs/talabalar-markazi.md. Qisqacha:
  * Qoidalar dvigateli (evaluate) har bir talaba bo'yicha signallarni KOD bilan hisoblaydi: kontrakt muddati, sababsiz qoldirilgan
    soatlar zinapoyasi, JPA + o'zlashtirilmagan fanlar, sababli qoldirish hujjati, akademik ta'til muddati, otrabotka muddati.
  * Har signal → bitta ochiq holat (ops_cases.key UNIQUE: "talaba:qoida"). Daraja oshsa — yangi topshiriq; shart yo'qolsa — holat yopiladi.
  * Topshiriqlar (ops_tasks) rolga tushadi: call-markaz (qo'ng'iroq + skript), tyutor (suhbat, hujjat), registrator (xat, buyruq loyihasi).
  * Natijalar (va'da, javob bermadi, ...) keyingi qadamni o'zi rejalashtiradi. Hammasi ops_log va audit jurnalida.
  * Otrabotka: varaqa (hujjatlar markazi, QR) → muddat → skan yuklash → baho yonma-yon → registrator tasdiqlaydi. Uch turi bor:
    «qarz» — yakunlangan semestrdagi o'zlashtirilmagan fan (o'sha semestr yozuvi yangilanadi), «oraliq» — joriy semestrda oraliq
    nazorat 12 dan past, «dars» — sababsiz qoldirilgan mashg'ulotni qayta ishlash (dars qoldirish yopiladi, baho o'zgarmaydi).
    Har urinish tarixda (grade_attempts) saqlanadi; o'tgan bahoni pasaytirib bo'lmaydi.
  * Davomat chegaralari (30 / 48 soat) — faqat JORIY semestrdagi sababsiz soatlar. Kunduzgi ta'limda sababli sabab: kasallik, oilaviy;
    xizmat safari va mehnat ta'tili — faqat sirtqi ta'lim talabalari uchun. Sirtqi davomat — o'quv sessiyasi soatlaridan.
  * Tyutor — o'ziga biriktirilgan guruhlar bilan ishlaydi (tutor_groups, ~10 guruhga bitta tyutor); sirtqi talabalarning tyutor
    ishlari — Sirtqi bo'limda, masofaviy — Registrator ofisida.

Qoidalardagi raqamlar institut tomonidan TASDIQLANMAGAN (ops_policy.verified=0) — UI'da shunday ko'rsatiladi.
Istisno: o'tish bali (40) — institutning akademik qoidalari (app/academic_rules.py), verified=1.
"""
import asyncio, base64, binascii, datetime as dt, json, random, re, secrets, threading
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import clock
from . import db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
OPS = "ops"
UPLOADS = db.DATA_DIR / "uploads" / "retakes"

# ---------------------------------------------------------------------------------------------
# Qoidalar (standart qiymatlar — tasdiqlanmagan)
# ---------------------------------------------------------------------------------------------
POLICY_DEFAULTS = [
    ("contract_critical_days", 3, "Navbatdagi kontrakt to'lovi muddatiga shuncha kun qolsa — kritik"),
    # institut me'yori (rektor qarori, 2026-11): 30 soat — call-markaz + ogohlantirish xati; 48 soatdan OSHSA (49+) — hayfsan
    ("att_call_hours", 30, "Sababsiz qoldirilgan soat: 30 soat va undan ko'p — call-markaz qo'ng'irog'i"),
    ("att_letter_hours", 30, "Sababsiz qoldirilgan soat: 30 soat va undan ko'p — ogohlantirish xati"),
    ("att_reprimand_hours", 48, "Sababsiz qoldirilgan soat: 48 soatdan oshsa — hayfsan buyrug'i loyihasi + tyutor suhbati"),
    ("hours_to_date", 180, "Kunduzgi: joriy semestr boshidan o'tilgan auditoriya soatlari (namuna)"),
    ("pass_score", AR.PASS, "Fan bo'yicha o'tish bali (100 ballik, «3» baho) — akademik qoidalar taqdimoti"),
    ("gpa_min", 3.0, "Minimal JPA (5 ballik)"),
    ("fails_warn", 2, "Shuncha fandan o'tmasa — JPA yetarli bo'lsa ham ogohlantirish"),
    ("medical_doc_days", 3, "Kasallik/komandirovkadan keyin hujjat topshirish muddati, kun"),
    ("leave_warn_days", 90, "Akademik ta'til tugashiga shuncha kun (~3 oy) qolganda ogohlantirish: call-markaz qo'ng'irog'i"),
    ("retake_days", 3, "Otrabotka varaqasini qaytarish muddati, kun"),
    ("call_max_attempts", 3, "Javob bermasa — shuncha urinishdan keyin tyutorga o'tadi"),
    # DEMO TAXMIN: institut call-markaz me'yorini bermagan — 1 operator kuniga ~60 ta qo'ng'iroq (o'rtacha 5–6 daqiqa + yozuv)
    ("call_daily_capacity", 60, "Call-markaz: bir operator bir ish kunida qiladigan qo'ng'iroqlar (standart; har operator uchun alohida sozlanadi)"),
    # Navbat to'lganda kechikadigan qo'ng'iroqlarni boshqa xodimlarga o'tkazish (TAXMIN, tasdiqlanmagan): bir kunda shuncha qo'ng'iroq
    ("tutor_call_capacity", 10, "Navbat to'lganda: bitta tyutorga bir ish kunida o'tkaziladigan qo'ng'iroqlar"),
    ("staff_call_capacity", 40, "Navbat to'lganda: Registrator ofisi xodimiga bir ish kunida o'tkaziladigan qo'ng'iroqlar"),
    # Registrator ofisi (M. Baratov): zinapoyaning oxirgi bosqichi va imtihonga ruxsatnoma — tasdiqlanmagan namunaviy qiymatlar
    ("att_expel_hours", 72, "Sababsiz qoldirilgan soat: hayfsandan keyin ham davom etsa — «chetlashtirishga tayyor» ro'yxati"),
    ("contract_expel_days", 30, "Kontrakt muddatidan shuncha kun o'tgan va ota-onaga xat yuborilgan bo'lsa — «chetlashtirishga tayyor»"),
    ("permit_att_hours", 48, "Imtihonga ruxsatnoma: sababsiz qoldirilgan soatlar shu chegaradan oshmasligi kerak (hayfsan chegarasi)"),
    ("session_hours", 96, "Sirtqi: joriy semestrdagi o'quv sessiyasi soatlari (davomat shu soatlardan hisoblanadi)"),
    # Sirtqi: sessiya qisqa (96 soat) — chegaralar kunduzgi me'yorga (30 / 48 / 72 soat 180 soatdan) mutanosib. TAXMIN, tasdiqlanmagan.
    ("sirtqi_att_call_hours", 16, "Sirtqi: sessiyada sababsiz qoldirilgan soat — qo'ng'iroq va ogohlantirish xati (30/180 ga mutanosib)"),
    ("sirtqi_att_reprimand_hours", 26, "Sirtqi: sessiyada sababsiz qoldirilgan soat shu chegaradan oshsa — hayfsan (48/180 ga mutanosib)"),
    ("sirtqi_att_expel_hours", 38, "Sirtqi: hayfsandan keyin ham davom etsa — «chetlashtirishga tayyor» (72/180 ga mutanosib)"),
]
SESSION = ("2026-10-12", "2026-10-31")   # sirtqi kuzgi o'quv sessiyasi (demo; sirtqi dars qoldirishlari shu oraliqda)
VERIFIED = {"pass_score", "att_call_hours", "att_letter_hours", "att_reprimand_hours"}   # institut qoidasi (akademik qoidalar; davomat — rektor qarori) — qolganlari hali tasdiqlanmagan
REASONS = {"sababsiz": "Sababsiz", "kasallik": "Kasallik", "komandirovka": "Xizmat safari (komandirovka)",
           "mehnat_tatili": "Mehnat ta'tili", "oilaviy": "Oilaviy sabab"}
EXCUSABLE = ("kasallik", "komandirovka", "mehnat_tatili", "oilaviy")
WORK_REASONS = ("komandirovka", "mehnat_tatili")   # ish bilan bog'liq sabablar — faqat sirtqi (ishlaydigan) talabalar uchun sababli
REASONS_BY_FORM = {"kunduzgi": ("sababsiz", "kasallik", "oilaviy"), "sirtqi": tuple(REASONS), "masofaviy": ()}
RULES = {"kontrakt": "Kontrakt to'lovi", "davomat": "Davomat (sababsiz)", "akademik": "O'zlashtirish (akademik qarz / oraliq nazorat)",
         "hujjat": "Sababli qoldirish hujjati", "tatil": "Akademik ta'til muddati", "otrabotka": "Otrabotka muddati"}
LEVELS = {1: "Diqqat", 2: "Kritik", 3: "Jiddiy"}
KINDS = {"qongiroq": "Qo'ng'iroq", "suhbat": "Suhbat", "hujjat": "Hujjat so'rash", "xat": "Ogohlantirish xati", "buyruq": "Buyruq loyihasi"}

# Ko'rish: to'liq / fakultet / faqat jamlangan
FULL_VIEW = ("talabalar", "registrator_xodim", "akademik", "prorektor_oquv")
REG_STAFF = "registrator_xodim"   # Registrator ofisi xodimi: boshliq navbatidagi ishlar (varaqa, skan, xat, qo'ng'iroq natijasi); bahoni tasdiqlash va buyruq loyihasi — boshliqda
FAC_VIEW = ("tyutor",)   # tyutor — faqat o'ziga biriktirilgan guruhlar (tutor_groups); fakultet darajasidagi ko'rinish Registrator ofisida (FULL_VIEW)
AGG_VIEW = ("rektor", "kengash", "prorektor_yoshlar")
SUPERVISOR = "talabalar"

DEMO_USERS = [  # sun'iy ism-shariflar; parol rbac.DEMO_PASSWORD
    ("Call-markaz operatori: Rahimova Nigora Odil qizi", "call_center", None),
    ("Tyutor (Xalqaro iqtisodiyot va moliya fakulteti): Ergasheva Sitora Komil qizi", "tyutor", 2),
    ("Tyutor (Iqtisodiyot va axborot texnologiyalari fakulteti): Saidov Temur Murod o'g'li", "tyutor", 1),
    ("Tyutor (Ijtimoiy-gumanitar fanlar va tillar fakulteti): Qodirova Laylo Erkin qizi", "tyutor", 3),
]

def _today(): return clock.today()
def _now(): return clock.now().replace(microsecond=0)
def _iso(t): return t.isoformat(timespec="seconds") if isinstance(t, dt.datetime) else t.isoformat()
def _short(name): return name.split(":", 1)[1].strip() if name and ":" in name else name

# ---------------------------------------------------------------------------------------------
# Sxema va demo ma'lumot
# ---------------------------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_policy(key TEXT PRIMARY KEY, value REAL, label TEXT, verified INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS contract_plan(id INTEGER PRIMARY KEY, due TEXT, cum_pct INT, label TEXT);
CREATE TABLE IF NOT EXISTS absences(id INTEGER PRIMARY KEY, student_id INT, start TEXT, end TEXT, hours INT, reason TEXT,
  doc_status TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS student_leaves(id INTEGER PRIMARY KEY, student_id INT, kind TEXT, start TEXT, end TEXT, order_no TEXT);
CREATE TABLE IF NOT EXISTS ops_cases(id INTEGER PRIMARY KEY, key TEXT UNIQUE, student_id INT, rule TEXT, level INT, status TEXT,
  opened_at TEXT, updated_at TEXT, closed_at TEXT, close_reason TEXT, facts TEXT);
CREATE TABLE IF NOT EXISTS ops_tasks(id INTEGER PRIMARY KEY, case_id INT, student_id INT, kind TEXT, title TEXT, assignee_role TEXT,
  faculty_id INT, due_at TEXT, status TEXT, outcome TEXT, note TEXT, promise_date TEXT, attempts INT DEFAULT 0, level INT,
  script TEXT, created_at TEXT, done_at TEXT, done_by INT, doc_reg TEXT);
CREATE TABLE IF NOT EXISTS ops_log(id INTEGER PRIMARY KEY, case_id INT, task_id INT, student_id INT, ts TEXT, user_id INT, user_name TEXT,
  action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS retakes(id INTEGER PRIMARY KEY, student_id INT, subject TEXT, teacher_id INT, reason TEXT, status TEXT,
  issued_at TEXT, due_at TEXT, reg_no TEXT, file TEXT, score_old INT, score_new INT, created_by INT, submitted_at TEXT,
  approved_at TEXT, approved_by INT, note TEXT);
CREATE TABLE IF NOT EXISTS discipline(id INTEGER PRIMARY KEY, student_id INT, kind TEXT, reason TEXT, hours INT, semester INT, doc_reg TEXT,
  status TEXT, created_at TEXT, created_by INT, signed_at TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_disc_st ON discipline(student_id, status);
CREATE TABLE IF NOT EXISTS tutor_groups(group_id INTEGER PRIMARY KEY, user_id INT);
CREATE TABLE IF NOT EXISTS call_operators(user_id INTEGER PRIMARY KEY, capacity INT, active INT DEFAULT 1, updated_at TEXT, updated_by INT);
CREATE TABLE IF NOT EXISTS ops_notices(id INTEGER PRIMARY KEY, ts TEXT, channel TEXT, task_id INT, case_id INT, student_id INT, phone TEXT,
  text TEXT, status TEXT, user_id INT);
CREATE TABLE IF NOT EXISTS ops_batches(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, kind TEXT, n INT, files TEXT, zip TEXT, order_ids TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_tg_user ON tutor_groups(user_id);
CREATE INDEX IF NOT EXISTS ix_abs_st ON absences(student_id);
CREATE INDEX IF NOT EXISTS ix_cases_st ON ops_cases(student_id, status);
CREATE INDEX IF NOT EXISTS ix_tasks_case ON ops_tasks(case_id, status);
CREATE INDEX IF NOT EXISTS ix_tasks_role ON ops_tasks(assignee_role, status);
CREATE INDEX IF NOT EXISTS ix_log_case ON ops_log(case_id);
"""

def _add_cols(con, table, cols):
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for c, ty in cols:
        if c not in have: con.execute(f"ALTER TABLE {table} ADD COLUMN {c} {ty}")

def ensure_schema(con):
    con.executescript(SCHEMA)
    AR.ensure_schema(con)
    _add_cols(con, "absences", [("semester", f"INT DEFAULT {AR.CURRENT_SEMESTER}"), ("cleared_by", "INT")])   # semestr; otrabotka bilan yopilgan
    _add_cols(con, "retakes", [("semester", f"INT DEFAULT {AR.CURRENT_SEMESTER}"), ("kind", "TEXT DEFAULT 'qarz'"), ("absence_id", "INT"), ("hours", "INT")])
    # planned_on — call-markaz rejalashtirgan kun (due_at — HAQIQIY muddat, rejalashtirish uni o'zgartirmaydi); assignee_user — qaysi operator
    _add_cols(con, "ops_tasks", [("planned_on", "TEXT"), ("assignee_user", "INT")])
    con.execute("CREATE INDEX IF NOT EXISTS ix_abs_sem ON absences(semester, student_id)")

def ensure_policy(con):
    """Yangi qo'shilgan standart qoidalar mavjud bazaga ham yoziladi (qiymati o'zgartirilganlari tegilmaydi)."""
    for k, v, label in POLICY_DEFAULTS:
        con.execute("INSERT OR IGNORE INTO ops_policy(key,value,label,verified) VALUES(?,?,?,?)", (k, v, label, int(k in VERIFIED)))
    con.commit()

def init(con):
    ensure_schema(con)
    if "phone" not in {r[1] for r in con.execute("PRAGMA table_info(students)").fetchall()}:
        con.execute("ALTER TABLE students ADD COLUMN phone TEXT")
    if "scan_meta" not in {r[1] for r in con.execute("PRAGMA table_info(retakes)").fetchall()}:   # skanni o'qish natijasi (registrar_scan)
        con.execute("ALTER TABLE retakes ADD COLUMN scan_meta TEXT")
    # akademik ta'til: ogohlantirish oynasi 30 kundan ~3 oyga (Registrator ofisi) — faqat tasdiqlanmagan eski standart qiymat yangilanadi
    con.execute("UPDATE ops_policy SET value=90, label=? WHERE key='leave_warn_days' AND value=30 AND verified=0", (POLICY_DEFAULTS[9][2],))
    for k, v, label in POLICY_DEFAULTS:
        con.execute("INSERT OR IGNORE INTO ops_policy(key,value,label,verified) VALUES(?,?,?,?)", (k, v, label, int(k in VERIFIED)))
        if k in VERIFIED:   # tasdiqlangan institut qoidasi eski bazadagi standart qiymatdan ustun (masalan, pass_score 56 → 40)
            con.execute("UPDATE ops_policy SET value=?, label=?, verified=1 WHERE key=? AND (value!=? OR verified!=1)", (v, label, k, v))
    roles = {r[0] for r in con.execute("SELECT role FROM users").fetchall()}
    if roles:
        have = {r[0] for r in con.execute("SELECT full_name FROM users").fetchall()}
        for name, role, fac in DEMO_USERS:
            if name not in have:
                con.execute("INSERT INTO users(full_name,role,faculty_id,pin) VALUES(?,?,?,?)", (name, role, fac, rbac.hash_password(rbac.DEMO_PASSWORD)))
    con.commit()
    if con.execute("SELECT COUNT(*) FROM students").fetchone()[0] and not con.execute("SELECT COUNT(*) FROM contract_plan").fetchone()[0]:
        seed(con)
    reg = con.execute("SELECT id FROM users WHERE role='talabalar'").fetchone()
    if reg and not con.execute("SELECT COUNT(*) FROM retakes").fetchone()[0] and con.execute("SELECT COUNT(*) FROM contract_plan").fetchone()[0]:
        seed_retakes(con, rbac.ctx_for(con, reg[0]), "http://localhost:8000/")
    # Sirtqi bo'lim — sirtqi talabalar uchun registrator: ogohlantirish xatlari uning navbatiga (bir martalik ko'chirish, idempotent)
    con.execute(f"""UPDATE ops_tasks SET assignee_role='sirtqi' WHERE status='yangi' AND assignee_role='talabalar'
                    AND kind='xat' AND case_id IN (SELECT id FROM ops_cases WHERE rule IN ({','.join(repr(r) for r, _ in SIRTQI_ROUTE)}))
                    AND student_id IN (SELECT id FROM students WHERE study_form='sirtqi')""")
    con.commit()
    migrate_v2(con)
    with _lock:   # call-markaz navbati darhol kunlarga taqsimlansin (agentlar skaneri va panel birinchi so'rovdayoq to'g'ri raqam ko'radi)
        schedule_calls(con); con.commit()

def migrate_v2(con):
    """Bir martalik (idempotent, _ops_v2 belgisi): 1) eski rejalashtiruvchi ochiq qo'ng'iroqlarning due_at'ini rejalashtirilgan kunga
    almashtirgan edi — haqiqiy muddat (SLA) yaratilgan vaqt + qoida muddatidan tiklanadi; 2) standart topshiriqlar skripti
    so'zlovchi (call-markaz / tyutor / Registrator ofisi / Sirtqi bo'lim) va ta'lim shakliga moslab qayta tuziladi."""
    if con.execute("SELECT 1 FROM ops_policy WHERE key='_ops_v2'").fetchone(): return 0
    P = policy(con); n = 0
    std = {v: k for k, v in TITLE.items()}
    for t in db.rows(con, """SELECT t.id, t.kind, t.title, t.level, t.created_at, t.attempts, t.assignee_role, oc.rule, oc.facts,
                             s.full_name, s.study_form, s.level slevel FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id
                             JOIN students s ON s.id=t.student_id WHERE t.status='yangi'"""):
        facts = json.loads(t["facts"] or "{}")
        s = {"full_name": t["full_name"], "study_form": t["study_form"], "level": t["slevel"]}
        sets = {}
        if t["assignee_role"] == "call_center" and not t["attempts"] and t["created_at"]:
            hrs = 8 if (t["title"] or "").startswith("Va'da muddati") else next(
                (h for k, ro, h in PLAN.get((t["rule"], t["level"]), []) if k == t["kind"]), 24)
            sets["due_at"] = _iso(_sla(t["rule"], t["kind"], facts, dt.datetime.fromisoformat(t["created_at"]), hrs))
        if t["title"] in std:
            try: sets["script"] = json.dumps(script(t["rule"], t["kind"], facts, s, P, t["assignee_role"]), ensure_ascii=False)
            except (KeyError, TypeError, ValueError): pass
        if sets:
            con.execute(f"UPDATE ops_tasks SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), t["id"])); n += 1
    con.execute("INSERT OR REPLACE INTO ops_policy(key,value,label,verified) VALUES('_ops_v2',1,'Navbat v2 migratsiyasi',1)")
    con.commit()
    return n

# Kontrakt to'lov jadvali — 2026-2027 o'quv yili uchun QAT'IY sanalar (seed sanasiga bog'liq emas). TAXMIN: institut to'lov jadvali
# hali kiritilmagan — namunaviy bo'lib to'lash tartibi (25 / 50 / 75 / 100%).
CONTRACT_PLAN = [("2026-10-01", 25, "1-to'lov"), ("2026-11-12", 50, "2-to'lov"), ("2027-02-15", 75, "3-to'lov"), ("2027-05-01", 100, "4-to'lov")]

def seed(con, today=None):
    """Demo ma'lumot (sun'iy): telefonlar, to'lov jadvali, dars qoldirishlar (sabablari, semestri bilan), davomat foizi."""
    R = random.Random(20261106)
    today = today or _today()
    P = policy(con)
    for sid, in con.execute("SELECT id FROM students WHERE phone IS NULL").fetchall():
        con.execute("UPDATE students SET phone=? WHERE id=?",
                    (f"+998 9{R.choice('0134579')} {R.randint(100, 999)} {R.randint(10, 99)} {R.randint(10, 99)}", sid))
    for due, pct, label in CONTRACT_PLAN:
        con.execute("INSERT INTO contract_plan(due,cum_pct,label) VALUES(?,?,?)", (due, pct, label))
    H, HS = int(P["hours_to_date"]), int(P.get("session_hours", 96))
    t0 = max(dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0]), today - dt.timedelta(days=60))
    s0, s1 = (dt.date.fromisoformat(x) for x in SESSION)
    p0, p1 = (dt.date.fromisoformat(x) for x in AR.term_dates(AR.CURRENT_SEMESTER - 1))
    rows, att = [], []
    for s in db.rows(con, """SELECT s.id, s.attendance, s.level, s.study_form, g.course FROM students s JOIN groups_ g ON g.id=s.group_id
                             WHERE s.status='faol' AND COALESCE(s.study_form,'kunduzgi')!='masofaviy'"""):
        sirtqi = s["study_form"] == "sirtqi"
        total = HS if sirtqi else H
        missed = int(round((100 - (s["attendance"] or 100)) / 100 * total))
        att.append((round(100 * (total - missed) / total, 1), s["id"]))   # davomat foizi = qoldirilgan soatlardan (bir manba)
        while missed > 0:
            h = min(missed, R.choice([2, 4, 4, 6, 6, 8]))
            missed -= h
            if sirtqi:   # ishlaydigan talaba: sessiyadan xizmat safari, mehnat ta'tili, kasallik yoki sababsiz
                reason = R.choices(["sababsiz", "komandirovka", "mehnat_tatili", "kasallik", "oilaviy"], [40, 25, 10, 15, 10])[0]
                start = s0 + dt.timedelta(days=R.randint(0, (min(s1, today) - s0).days))
                end = min(start + dt.timedelta(days=max(0, h // 6 - 1)), s1, today)
            else:        # kunduzgi: xizmat safari va mehnat ta'tili sababli qoldirish yo'q (ular ish bilan bog'liq)
                reason = R.choices(["sababsiz", "kasallik", "oilaviy"], [55, 33, 12])[0]
                start = t0 + dt.timedelta(days=R.randint(0, max(0, (today - t0).days - 1)))
                end = start + dt.timedelta(days=max(0, h // 6 - 1) + (R.randint(1, 5) if reason == "kasallik" else 0))
            doc = None
            if reason in EXCUSABLE:
                recent = (today - end).days <= 6
                if reason == "oilaviy":   # oilaviy sabab — ariza odatda oldindan beriladi
                    doc = R.choices(["tasdiqlangan", "yoq"], [85, 15])[0]
                else:
                    doc = R.choices(["tasdiqlangan", "kutilmoqda", "yoq"], [60, 30, 10] if recent else [88, 0, 12])[0]
            rows.append((s["id"], start.isoformat(), min(end, today).isoformat(), h, reason, doc, _iso(_now()), AR.CURRENT_SEMESTER))
        # o'tgan semestr (bahorgi) qoldirishlari — tarix uchun; joriy semestr chegaralariga (30 / 48 soat) KIRMAYDI
        if not sirtqi and s["course"] > 1 and R.random() < 0.12:
            for _ in range(R.randint(2, 6)):
                st = p0 + dt.timedelta(days=R.randint(0, (p1 - p0).days - 5))
                rows.append((s["id"], st.isoformat(), st.isoformat(), R.choice([4, 6, 8]), "sababsiz", None, _iso(_now()), AR.CURRENT_SEMESTER - 1))
    con.executemany("INSERT INTO absences(student_id,start,end,hours,reason,doc_status,created_at,semester) VALUES(?,?,?,?,?,?,?,?)", rows)
    con.executemany("UPDATE students SET attendance=? WHERE id=?", att)
    # akademik ta'tildagilar: joriy semestr davomati yo'q
    con.execute("UPDATE students SET attendance=NULL WHERE status=\"akademik ta'til\" OR COALESCE(study_form,'kunduzgi')='masofaviy'")
    if not con.execute("SELECT 1 FROM student_leaves LIMIT 1").fetchone():   # eski baza: ta'til davrlari app/seed.py da yaratilmagan
        for i, s in enumerate(db.rows(con, "SELECT id FROM students WHERE status=\"akademik ta'til\" ORDER BY id")):
            end = today + dt.timedelta(days=[12, 26, -9][i] if i < 3 else R.randint(-40, 200))
            con.execute("INSERT INTO student_leaves(student_id,kind,start,end,order_no) VALUES(?,?,?,?,?)",
                        (s["id"], "akademik", (end - dt.timedelta(days=270)).isoformat(), end.isoformat(), f"TH-25/{R.randint(100, 999)}"))
    con.commit()

def seed_retakes(con, ctx_issuer, base_url):
    """Bir nechta otrabotka (hujjatlar markazi orqali varaqa bilan): biri ertaga tugaydi, biri muddati o'tgan."""
    R = random.Random(7)
    pass_ = int(policy(con)["pass_score"])
    cand = db.rows(con, f"""SELECT g.student_id, g.subject, g.teacher_id, g.score, g.semester FROM grades g JOIN students s ON s.id=g.student_id
                           WHERE {AR.debt_where('g')} AND g.semester={AR.RATING_SEMESTER} AND s.faculty_id=2 AND s.status='faol'
                           AND s.study_form='kunduzgi' ORDER BY g.student_id LIMIT 40""")
    R.shuffle(cand)
    now = _now()
    for i, c in enumerate(cand[:3]):
        due = now + dt.timedelta(hours=[20, -26, 50][i])
        issued = due - dt.timedelta(days=int(policy(con)["retake_days"]))
        cur = con.execute("""INSERT INTO retakes(student_id,subject,teacher_id,reason,status,issued_at,due_at,score_old,created_by,semester,kind)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (c["student_id"], c["subject"], c["teacher_id"], RETAKE_REASON["qarz"],
                                                          "berildi", _iso(issued), _iso(due), c["score"], ctx_issuer.user["id"], c["semester"], "qarz"))
        _issue_sheet(con, ctx_issuer, cur.lastrowid, base_url)
    con.commit()

# ---------------------------------------------------------------------------------------------
# Tyutorlar: ~10 kunduzgi guruhga bitta tyutor (TAXMIN — institut me'yori kiritilmagan). Mavjud demo tyutorlar (24–26) ham shu ro'yxatda.
# Akkauntlar server ishga tushishining OXIRIDA yaratiladi (reyting.init) — boshqa demo akkauntlar id'si o'zgarmasligi uchun.
# Tyutorlar kirish ro'yxatida ko'rsatilmaydi (main.py /api/users), API va parol bilan ishlaydi.
# ---------------------------------------------------------------------------------------------
TUTOR_GROUPS = 10
_T_M = ["Akmal", "Bobur", "Doniyor", "Elyor", "Farrux", "Jamshid", "Laziz", "Nodir", "Rustam", "Sanjar", "Shoxrux", "Ulug'bek"]
_T_F = ["Dilnoza", "Feruza", "Gulnora", "Kamola", "Madina", "Malika", "Nargiza", "Nilufar", "Sevara", "Shahnoza", "Umida", "Zarina"]
_T_S = ["Abdurahmonov", "Azimov", "Boboyev", "Fayziyev", "G'aniyev", "Ismatov", "Jalilov", "Karimov", "Latipov", "Murodov", "Nurmatov",
        "Olimov", "Po'latov", "Qosimov", "Rasulov", "Sattorov", "Tojiyev", "Usmonov", "Valiyev", "Xudoyberdiyev", "Yo'ldoshev", "Zokirov"]
_T_P = ["Anvar", "Baxtiyor", "Farhod", "Ilhom", "Komil", "Murod", "Rustam", "Shavkat"]

def _tutor_name(R):
    s = R.choice(_T_S)
    if R.random() < 0.55: return f"{s}a {R.choice(_T_F)} {R.choice(_T_P)} qizi"
    return f"{s} {R.choice(_T_M)} {R.choice(_T_P)} o'g'li"

def ensure_tutors(con) -> dict:
    """Tyutor ↔ guruh biriktirmasi (tutor_groups). Har fakultetning kunduzgi guruhlari ~10 tadan bo'linadi (avval 2-kurs —
    hikoya kogortasi, keyin 3, 4, 1-kurslar); yetishmagan tyutor akkauntlari yaratiladi. Idempotent."""
    con.executescript(SCHEMA)
    groups = db.rows(con, "SELECT id, faculty_id FROM groups_ WHERE form='kunduzgi' ORDER BY faculty_id, (course + 2) % 4, direction, name")
    if not groups: return {"tutors": 0, "groups": 0}
    mapped = con.execute("""SELECT COUNT(*) FROM tutor_groups tg JOIN users u ON u.id=tg.user_id AND u.role='tyutor'
                            JOIN groups_ g ON g.id=tg.group_id AND g.form='kunduzgi'""").fetchone()[0]
    if mapped == len(groups):
        return {"tutors": con.execute("SELECT COUNT(DISTINCT user_id) FROM tutor_groups").fetchone()[0], "groups": mapped, "created": 0}
    R = random.Random(20261111)
    fac_name = {r["id"]: r["name"] for r in db.rows(con, "SELECT id, name FROM faculties")}
    by_fac = {}
    for g in groups: by_fac.setdefault(g["faculty_id"], []).append(g["id"])
    con.execute("DELETE FROM tutor_groups")
    created, pw = 0, None
    for fid, gids in by_fac.items():
        k = max(1, -(-len(gids) // TUTOR_GROUPS))
        have = [r[0] for r in con.execute("SELECT id FROM users WHERE role='tyutor' AND faculty_id=? AND COALESCE(active,1)!=0 ORDER BY id", (fid,))] \
            if "active" in {r[1] for r in con.execute("PRAGMA table_info(users)")} else \
            [r[0] for r in con.execute("SELECT id FROM users WHERE role='tyutor' AND faculty_id=? ORDER BY id", (fid,))]
        while len(have) < k:
            pw = pw or rbac.hash_password(rbac.DEMO_PASSWORD)
            cur = con.execute("INSERT INTO users(full_name,role,faculty_id,pin) VALUES(?,?,?,?)",
                              (f"Tyutor ({fac_name.get(fid, '')} fakulteti): {_tutor_name(R)}", "tyutor", fid, pw))
            have.append(cur.lastrowid); created += 1
        for i, gid in enumerate(gids):   # teng bo'laklar: birinchi tyutor — birinchi ~10 guruh
            con.execute("INSERT OR REPLACE INTO tutor_groups(group_id,user_id) VALUES(?,?)", (gid, have[i * k // len(gids)]))
    con.commit()
    return {"tutors": con.execute("SELECT COUNT(DISTINCT user_id) FROM tutor_groups").fetchone()[0], "groups": len(groups), "created": created}

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def policy(con) -> dict:
    return {r["key"]: r["value"] for r in db.rows(con, "SELECT key, value FROM ops_policy")}

# ---------------------------------------------------------------------------------------------
# Faktlar
# ---------------------------------------------------------------------------------------------
def _grade5(score, pass_):
    """5 ballik baho — institut shkalasi (academic_rules.SCALE); o'tish chegarasi siyosatdan."""
    return 2 if score < pass_ else max(3, AR.grade5(score)[0])

def _unexcused_sql(P, today, a="a", s="s"):
    """JORIY semestrda sababsiz hisoblanadigan soatlar (a — absences, s — students taxallusi):
    «sababsiz»; xizmat safari / mehnat ta'tili — sirtqi bo'lmagan talabada (kunduzgi ta'limda bunday sabab qabul qilinmaydi);
    sababli qoldirish — hujjati yo'q yoki muddatida topshirilmagan. Otrabotka bilan yopilgan dars (cleared_by) hisobga olinmaydi."""
    cut = (today - dt.timedelta(days=int(P["medical_doc_days"]))).isoformat()
    work = ",".join(repr(x) for x in WORK_REASONS)
    return (f"({a}.semester={AR.CURRENT_SEMESTER} AND {a}.cleared_by IS NULL AND ({a}.reason='sababsiz' "
            f"OR ({a}.reason IN ({work}) AND COALESCE({s}.study_form,'kunduzgi')!='sirtqi') "
            f"OR ({a}.reason IN ('kasallik','komandirovka','mehnat_tatili','oilaviy') AND "
            f"({a}.doc_status='yoq' OR ({a}.doc_status='kutilmoqda' AND {a}.end < '{cut}')))))")

def _debts(con, sid):
    return db.rows(con, f"""SELECT subject, score, semester, credits, attempts FROM grades g WHERE g.student_id=? AND {AR.debt_where('g')}
                            ORDER BY semester DESC, subject""", (sid,))

def cum_gpa(con, sid):
    """Kumulyativ GPA (5) — barcha yakunlangan semestrlar, kredit bilan tortilgan (academic_rules.gpa)."""
    rows = con.execute(f"SELECT credits, score FROM grades WHERE student_id=? AND semester<? AND score IS NOT NULL",
                       (sid, AR.CURRENT_SEMESTER)).fetchall()
    return AR.gpa([(cr or AR.CREDIT_DEFAULT, AR.grade5(sc)[0]) for cr, sc in rows])

def student_facts(con, sid) -> dict:
    """Talabaning akademik faktlari — barchasi baholar va davomatdan (academic_rules ta'riflari):
    unexcused/excused — JORIY semestr soatlari; fails — akademik qarzlar (yakunlangan semestrlar); gpa5 — kumulyativ GPA (5);
    oraliq_low — joriy semestrda oraliq < 12 fanlar; grades — kartadagi jadval (qarzlar + joriy fanlar oraliq bilan)."""
    P, today = policy(con), _today()
    cur = AR.CURRENT_SEMESTER
    unx = con.execute(f"""SELECT COALESCE(SUM(a.hours),0) FROM absences a JOIN students s ON s.id=a.student_id
                          WHERE a.student_id=? AND {_unexcused_sql(P, today)}""", (sid,)).fetchone()[0]
    tot = con.execute("SELECT COALESCE(SUM(hours),0) FROM absences WHERE student_id=? AND semester=?", (sid, cur)).fetchone()[0]
    debts = _debts(con, sid)
    curg = db.rows(con, "SELECT subject, oraliq, credits FROM grades WHERE student_id=? AND semester=? ORDER BY subject", (sid, cur))
    low = [g for g in curg if not AR.admitted(g["oraliq"])]
    grades = [{"subject": d["subject"], "semester": d["semester"], "score": d["score"], "oraliq": None, "fail": True, "kind": "qarz",
               "shown": f"{d['score']} · {AR.SEMESTER_SHORT.get(d['semester'], d['semester'])} (qarz)"} for d in debts]
    grades += [{"subject": g["subject"], "semester": cur, "score": None, "oraliq": g["oraliq"], "fail": not AR.admitted(g["oraliq"]),
                "kind": "oraliq", "shown": f"oraliq {g['oraliq'] if g['oraliq'] is not None else '—'} / {AR.ORALIQ_MAX}"} for g in curg]
    gpa5 = cum_gpa(con, sid)
    return {"unexcused": int(unx), "excused": int(tot - unx), "gpa5": gpa5, "gpa_label": AR.GPA_LABEL + ", kumulyativ",
            "fails": [{"subject": d["subject"], "score": d["score"], "semester": d["semester"],
                       "sem_label": AR.SEMESTER_SHORT.get(d["semester"])} for d in debts],
            "oraliq_low": [{"subject": g["subject"], "oraliq": g["oraliq"]} for g in low], "grades": grades,
            "level": AR.akademik_level(len(debts), gpa5, len(low), P["fails_warn"], P["gpa_min"])}

# ---------------------------------------------------------------------------------------------
# Qoidalar dvigateli
# ---------------------------------------------------------------------------------------------
def _signals(con, today):
    P = policy(con)
    out = {}   # key -> (student_id, rule, level, facts)
    plan = db.rows(con, "SELECT * FROM contract_plan ORDER BY due")
    crit = int(P["contract_critical_days"])
    for s in db.rows(con, "SELECT id, contract_amount, paid_amount FROM students WHERE status='faol' AND payment_type='kontrakt' AND contract_amount>0"):
        for inst in plan:
            need = s["contract_amount"] * inst["cum_pct"] // 100
            if s["paid_amount"] < need:
                days = (dt.date.fromisoformat(inst["due"]) - today).days
                lvl = 3 if days < 0 else 2 if days <= crit else 0
                if lvl:
                    out[f"{s['id']}:kontrakt"] = (s["id"], "kontrakt", lvl, {"due": inst["due"], "installment": inst["label"], "pct": inst["cum_pct"],
                        "need_now": need - s["paid_amount"], "debt_total": s["contract_amount"] - s["paid_amount"], "days": days})
                break
    unx = _unexcused_sql(P, today)
    for r in db.rows(con, f"""SELECT a.student_id, SUM(a.hours) h, s.study_form form FROM absences a JOIN students s ON s.id=a.student_id
                              WHERE s.status='faol' AND {unx} GROUP BY a.student_id"""):   # faqat joriy semestr
        L = att_limits(P, r["form"])
        lvl = davomat_level(r["h"], P, r["form"])
        if lvl: out[f"{r['student_id']}:davomat"] = (r["student_id"], "davomat", lvl, {"hours": r["h"], "next": None if lvl >= 3 else L["reprimand"],
                                                                                       "expel": L["expel"], "form": r["form"] or "kunduzgi"})
    cut = today - dt.timedelta(days=int(P["medical_doc_days"]))
    for r in db.rows(con, """SELECT a.student_id, a.id, a.reason, a.end, a.hours FROM absences a JOIN students s ON s.id=a.student_id
                             WHERE s.status='faol' AND a.doc_status='kutilmoqda' ORDER BY a.end"""):
        k = f"{r['student_id']}:hujjat"
        late = dt.date.fromisoformat(r["end"]) < cut
        prev = out.get(k)
        items = (prev[3]["items"] if prev else []) + [{"id": r["id"], "reason": r["reason"], "end": r["end"], "hours": r["hours"], "late": late}]
        lvl = max(prev[2] if prev else 1, 2 if late else 1)
        out[k] = (r["student_id"], "hujjat", lvl, {"items": items, "deadline_days": int(P["medical_doc_days"])})
    for sid, (lvl, facts) in akademik_signals(con, P).items():
        out[f"{sid}:akademik"] = (sid, "akademik", lvl, facts)
    win = int(P["leave_warn_days"])
    for l in db.rows(con, """SELECT l.* FROM student_leaves l JOIN students s ON s.id=l.student_id WHERE s.status="akademik ta'til" """):
        days = (dt.date.fromisoformat(l["end"]) - today).days
        if days <= win:
            lvl = 3 if days < 0 else 2 if days <= 7 else 1
            out[f"{l['student_id']}:tatil"] = (l["student_id"], "tatil", lvl, {"end": l["end"], "days": days, "order_no": l["order_no"]})
    now = _now()
    for r in db.rows(con, "SELECT * FROM retakes WHERE status='berildi'"):
        hrs = (dt.datetime.fromisoformat(r["due_at"]) - now).total_seconds() / 3600
        if hrs <= 24:
            out[f"{r['student_id']}:otrabotka:{r['id']}"] = (r["student_id"], "otrabotka", 2 if hrs < 0 else 1,
                                                           {"retake_id": r["id"], "subject": r["subject"], "due_at": r["due_at"], "hours_left": round(hrs, 1)})
    return out

def akademik_signals(con, P, where="s.status='faol'") -> dict:
    """{talaba: (daraja, faktlar)} — academic_rules.akademik_level: akademik qarzlar (yakunlangan semestrlar), kumulyativ GPA,
    joriy semestrda oraliq < 12 fanlar. Bitta SQL o'tishda (29 ming talaba)."""
    cur, pass_ = AR.CURRENT_SEMESTER, AR.PASS
    debts, gp, low = {}, {}, {}
    for r in db.rows(con, f"""SELECT g.student_id sid, g.subject, g.score, g.semester FROM grades g JOIN students s ON s.id=g.student_id
                              WHERE {where} AND {AR.debt_where('g')} ORDER BY g.semester DESC, g.subject"""):
        debts.setdefault(r["sid"], []).append({"subject": r["subject"], "score": r["score"], "semester": r["semester"],
                                               "sem_label": AR.SEMESTER_SHORT.get(r["semester"])})
    for r in db.rows(con, f"""SELECT g.student_id sid, g.subject, g.oraliq FROM grades g JOIN students s ON s.id=g.student_id
                              WHERE {where} AND g.semester={cur} AND COALESCE(g.oraliq, 0) < {AR.ORALIQ_MIN} ORDER BY g.subject"""):
        low.setdefault(r["sid"], []).append({"subject": r["subject"], "oraliq": r["oraliq"]})
    if debts or low:
        for r in con.execute(f"""SELECT g.student_id, SUM(COALESCE(g.credits,{AR.CREDIT_DEFAULT}) * {AR.grade5_sql('g.score')}),
                                 SUM(COALESCE(g.credits,{AR.CREDIT_DEFAULT})) FROM grades g JOIN students s ON s.id=g.student_id
                                 WHERE {where} AND g.semester<{cur} AND g.score IS NOT NULL GROUP BY g.student_id"""):
            gp[r[0]] = AR.ratio2(r[1], r[2])
    out = {}
    for sid in set(debts) | set(low) | {k for k, v in gp.items() if v is not None and v < P["gpa_min"]}:
        d, l, g = debts.get(sid, []), low.get(sid, []), gp.get(sid)
        lvl = AR.akademik_level(len(d), g, len(l), P["fails_warn"], P["gpa_min"])
        if lvl:
            out[sid] = (lvl, {"gpa5": g, "fails": d, "oraliq_low": l, "gpa_ok": g is None or g >= P["gpa_min"]})
    return out

def att_limits(P, form="kunduzgi") -> dict:
    """Joriy semestr sababsiz soat chegaralari: kunduzgi — institut me'yori (30 / 48 / 72), sirtqi — sessiya soatlariga mutanosib."""
    if form == "sirtqi":
        c = int(P.get("sirtqi_att_call_hours", 16))
        return {"call": c, "letter": c, "reprimand": int(P.get("sirtqi_att_reprimand_hours", 26)), "expel": int(P.get("sirtqi_att_expel_hours", 38))}
    return {"call": int(P["att_call_hours"]), "letter": int(P["att_letter_hours"]), "reprimand": int(P["att_reprimand_hours"]),
            "expel": int(P.get("att_expel_hours", 72))}

def davomat_level(h, P, form="kunduzgi") -> int:
    """Sababsiz soatlar zinapoyasi (academic_rules.davomat_level): hayfsan — 48 dan OSHSA, xat va qo'ng'iroq — 30 ga yetsa (sirtqi — mutanosib)."""
    L = att_limits(P, form)
    return AR.davomat_level(h, L["call"], L["letter"], L["reprimand"])

def adult(s) -> bool:
    """Ishlaydigan / katta yoshli talaba: sirtqi, masofaviy yoki magistrant — ota-onaga xat yuborilmaydi, xat talabaning o'ziga."""
    return (s.get("study_form") or "kunduzgi") in ("sirtqi", "masofaviy") or s.get("level") == "magistr"

def route(role, s) -> str:
    """Topshiriq egasi: tyutorlar kunduzgi guruhlarga biriktirilgan — sirtqi talabaning tyutor ishi Sirtqi bo'limga,
    masofaviy talabaniki Registrator ofisiga o'tadi."""
    form = s.get("study_form") or "kunduzgi"
    if role == "tyutor" and form != "kunduzgi": return "sirtqi" if form == "sirtqi" else SUPERVISOR
    return role

# qoida + daraja -> topshiriqlar: (tur, rol, muddat soatda). Muddat — HAQIQIY (SLA) muddat: call-markaz rejalashtiruvchisi uni o'zgartirmaydi.
# Kontrakt eslatmasi (2-daraja) muddati — to'lov sanasidan oldingi ish kuni 18:00 (_sla). TAXMIN (tasdiqlanmagan): muddati o'tgan kontrakt —
# 2 ish kuni ichida qo'ng'iroq; akademik ta'til tugashiga ≤ 90 kun — 5 kun ichida eslatma.
PLAN = {
    ("kontrakt", 2): [("qongiroq", "call_center", 8)],
    ("kontrakt", 3): [("qongiroq", "call_center", 48), ("xat", "talabalar", 48)],
    ("davomat", 1): [("qongiroq", "call_center", 24)],
    ("davomat", 2): [("qongiroq", "call_center", 24), ("xat", "talabalar", 48)],   # 30 soat: qo'ng'iroq + ogohlantirish xati
    ("davomat", 3): [("buyruq", "talabalar", 72), ("suhbat", "tyutor", 48)],
    ("hujjat", 1): [("hujjat", "tyutor", 24)],
    ("hujjat", 2): [("hujjat", "tyutor", 8)],
    ("akademik", 2): [("suhbat", "tyutor", 72)],   # 1-daraja (diqqat: 1 ta qarz yoki 1 fandan past oraliq) — topshiriqsiz, ish stolida
    ("akademik", 3): [("suhbat", "tyutor", 48), ("xat", "talabalar", 72)],
    ("tatil", 1): [("qongiroq", "call_center", 120)],
    ("tatil", 2): [("buyruq", "talabalar", 72)],
    ("tatil", 3): [("buyruq", "talabalar", 24)],
    ("otrabotka", 1): [("qongiroq", "call_center", 4)],
    ("otrabotka", 2): [("suhbat", "tyutor", 24), ("qongiroq", "call_center", 8)],   # muddat o'tdi: tyutor ogohlantiradi, call-markaz qo'ng'iroq qiladi
}
# Sirtqi ta'lim talabalari bo'yicha Registrator ofisi topshiriqlaridan Sirtqi bo'limga o'tadiganlari (qoida, tur).
# Kontrakt xati (moliya), hayfsan va talabalar harakati buyruqlari loyihasi — institut darajasida, Registrator ofisida qoladi.
SIRTQI_ROUTE = {("akademik", "xat"), ("davomat", "xat")}
TITLE = {
    ("kontrakt", "qongiroq"): "Kontrakt to'lovi bo'yicha qo'ng'iroq", ("kontrakt", "xat"): "Ota-onaga qarzdorlik xati",
    ("kontrakt", "xat_talaba"): "Talabaga qarzdorlik xati",
    ("davomat", "qongiroq"): "Davomat bo'yicha qo'ng'iroq", ("davomat", "xat"): "Davomat bo'yicha ogohlantirish xati",
    ("davomat", "buyruq"): "Hayfsan buyrug'i loyihasi", ("davomat", "suhbat"): "Tyutor suhbati: davomat",
    ("hujjat", "hujjat"): "Sababli qoldirish hujjatini so'rash", ("akademik", "suhbat"): "Tyutor suhbati: o'zlashtirish",
    ("akademik", "xat"): "O'zlashtirish bo'yicha ogohlantirish xati", ("akademik", "qongiroq"): "O'zlashtirish bo'yicha qo'ng'iroq",
    ("tatil", "qongiroq"): "Akademik ta'til tugashi haqida eslatma", ("tatil", "buyruq"): "Ta'tildan qaytish buyrug'i loyihasi",
    ("otrabotka", "qongiroq"): "Otrabotka muddati eslatmasi", ("otrabotka", "suhbat"): "Otrabotka muddati o'tdi: tyutor ogohlantirsin",
}

def _dmy(d): return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if d and len(d) >= 10 else d

def _money(x): return f"{int(x):,}".replace(",", " ") + " so'm"

# Kim gapiradi (topshiriq egasi) — skript shu bo'yicha tuziladi: call-markaz tyutor nomidan gapirmaydi, tyutor «tyutor bilan uchrashuv
# belgilang» demaydi, sirtqi talabaga Sirtqi bo'lim (tyutor emas) uchrashuv belgilaydi.
SPEAKER = {"call_center": "ISFT institutining call-markazidan", "talabalar": "ISFT institutining Registrator ofisidan",
           "registrator_xodim": "ISFT institutining Registrator ofisidan", "sirtqi": "ISFT institutining Sirtqi bo'limidan"}

def _voice(role, s) -> dict:
    """{opener(name), meet, docs_to, reasons} — so'zlovchi lavozimi va talabaning ta'lim shakliga qarab."""
    form = (s or {}).get("study_form") or "kunduzgi"
    role = role or "call_center"
    # yuzma-yuz uchrashuvni kim o'tkazadi: kunduzgi — guruh tyutori, sirtqi — Sirtqi bo'lim, masofaviy — Registrator ofisi
    owner = {"kunduzgi": "tyutor", "sirtqi": "sirtqi"}.get(form, "talabalar")
    if owner == role or (owner == "talabalar" and role == "registrator_xodim"):
        meet = "o'zingiz bilan uchrashuv vaqtini kelishing va natijani yozib qo'ying"
    else:
        meet = {"tyutor": "guruh tyutori bilan uchrashuv belgilang", "sirtqi": "Sirtqi bo'limga uchrashuvga taklif qiling",
                "talabalar": "Registrator ofisiga uchrashuvga taklif qiling"}[owner]
    docs_to = {"kunduzgi": "tyutorga", "sirtqi": "Sirtqi bo'limga"}.get(form, "Registrator ofisiga")
    reasons = "Kasallik, xizmat safari yoki mehnat ta'tili" if form == "sirtqi" else "Kasallik yoki oilaviy sabab"
    if role == "tyutor":
        opener = lambda n: f"Assalomu alaykum, {n}. Guruhingiz tyutori qo'ng'iroq qilyapti."
    else:
        opener = lambda n: f"Assalomu alaykum, {n}. {SPEAKER.get(role, SPEAKER['call_center'])} qo'ng'iroq qilyapmiz."
    return {"opener": opener, "meet": meet, "docs_to": docs_to, "reasons": reasons, "form": form, "role": role}

def script(rule, kind, facts, s, P, role="call_center"):
    """Qo'ng'iroq/suhbat skripti — faqat bazadagi faktlardan. Me'yoriy havolalar o'ylab topilmaydi. role — topshiriq egasi (so'zlovchi)."""
    facts = {**facts}
    for k in ("due", "end"):
        if facts.get(k): facts[k] = _dmy(facts[k])
    name = s["full_name"].split()[1] if len(s["full_name"].split()) > 1 else s["full_name"]
    V = _voice(role, s)
    hello = [V["opener"](name)] if kind == "qongiroq" else [f"{s['full_name']} bilan yuzma-yuz suhbat: avval sababini so'rang."] if kind == "suhbat" else []
    say = []
    if rule == "kontrakt":
        say = hello + [
               f"{facts['installment']} muddati {facts['due']} — hozircha {_money(facts['need_now'])} yetishmayapti (umumiy qarz {_money(facts['debt_total'])}).",
               "To'lov qachon amalga oshirilishini aniq sana bilan kelishib oling. Bo'lib to'lash kerak bo'lsa — buxgalteriya bo'limiga yo'naltiring.",
               "Sana aytilsa — «Va'da berdi» natijasini o'sha sana bilan belgilang: tizim muddat o'tganda o'zi qayta eslatadi."]
    elif rule == "davomat":
        say = hello + [
               f"Joriy semestrda ({AR.SEMESTER_SHORT[AR.CURRENT_SEMESTER]}{', o' + chr(39) + 'quv sessiyasi' if V['form'] == 'sirtqi' else ''}) {facts['hours']} soat dars sababsiz qoldirilgan." + (f" {int(facts['next'])} soatdan oshsa, hayfsan e'lon qilish masalasi ko'riladi." if facts.get("next") else " Hayfsan chegarasidan oshgan."),
               f"Sababini so'rang. {V['reasons']} bo'lsa — tasdiqlovchi hujjatni {int(P.get('medical_doc_days', 3))} kun ichida {V['docs_to']} topshirish kerakligini ayting.",
               f"Muammo bo'lsa (ish, oilaviy holat) — {V['meet']}."]
    elif rule == "akademik":
        fl = ", ".join(f"{f['subject']} ({f['score']} ball, {f.get('sem_label') or ''})" for f in facts["fails"])
        lo = ", ".join(f"{f['subject']} ({f['oraliq']}/{AR.ORALIQ_MAX})" for f in facts.get("oraliq_low", []))
        say = hello + ([f"Akademik qarzlar (yakunlangan semestrlar): {fl}." if fl else "Yakunlangan semestrlardan akademik qarz yo'q."]
               + ([f"Joriy semestrda oraliq nazorat {AR.ORALIQ_MIN} balldan past: {lo} — bunday fandan yakuniy nazoratga kiritilmaydi."] if lo else [])
               + [f"Kumulyativ GPA (5): {facts['gpa5'] if facts['gpa5'] is not None else '—'}" + (" — umumiy ko'rsatkich yetarli, lekin qarzlar bor." if facts["gpa_ok"] else "."),
                  "Qayta topshirish (otrabotka) tartibini tushuntiring va varaqa olish uchun kunni kelishing.",
                  "Qiyinchilik sababini aniqlang (dars qoldirish, fan murakkabligi, ish) — natijani qisqa yozib qo'ying."])
    elif rule == "hujjat":
        it = facts["items"][-1]
        say = [f"{REASONS.get(it['reason'], it['reason'])} sababli {it['hours']} soat qoldirilgan (tugagan sana {_dmy(it['end'])}).",
               f"Tasdiqlovchi hujjat {facts['deadline_days']} kun ichida topshirilishi kerak, aks holda soatlar sababsiz hisoblanadi.",
               "Hujjat kelsa — «Hujjat keldi», kelmasa — «Hujjat yo'q» deb belgilang."]
    elif rule == "tatil":
        say = hello + [f"Akademik ta'til ({facts['order_no']}) {facts['end']}da tugaydi" + (" — muddat o'tgan." if facts["days"] < 0 else f" ({facts['days']} kun qoldi)."),
               "O'qishga qaytish arizasi va kerakli hujjatlarni (tibbiy xulosa va h.k.) eslating; talaba ikki tomonga borib yurmasligi uchun ro'yxatni aniq ayting.",
               "Qaytish kursi, guruh va o'quv rejalaridagi farq (akademik farq fanlari) bo'yicha Registrator ofisiga oldindan kelishini so'rang.",
               "Kontrakt asosida o'qisa — qaytish semestri uchun to'lov jadvalini buxgalteriyadan aniqlab olishini eslating."]
        if kind == "buyruq":
            say.append("Ariza kelgach «Ta'tildan qaytish» (qayta tiklash) buyrug'i loyihasini Buyruqlar bo'limida tayyorlang — "
                       "«Hujjat tayyorlash» tugmasi loyihani buyruqlar modulida yaratadi va shu topshiriqqa bog'laydi.")
    elif rule == "otrabotka":
        late = (facts.get("hours_left") or 0) < 0
        say = [f"«{facts['subject']}» fanidan otrabotka varaqasi muddati: {_dmy(facts['due_at'])}, soat {facts['due_at'][11:16]}"
               + (" — MUDDAT O'TDI, varaqa hali qaytarilmagan." if late else "."),
               f"Varaqani o'qituvchiga imzolatib, Registrator ofisiga ({AR.REGISTRAR_ROOMS_TEXT}) topshirishni eslating."]
        if kind == "qongiroq": say.insert(1, f"(Qo'ng'iroq: {'guruh tyutori' if role == 'tyutor' else SPEAKER.get(role, SPEAKER['call_center'])}.)")
        if late:
            say.append("Sababini so'rang: o'qituvchi topilmadimi, talaba kelmadimi? Kerak bo'lsa yangi varaqa (yangi muddat) Registrator ofisida beriladi.")
    tone = ["Hurmat bilan gapiring, ayblamang; avval sababini so'rang.", "Aniq sana va keyingi qadamni kelishing; va'dani tizimga kiriting.",
            "Shaxsiy ma'lumotni faqat talabaning o'zi yoki tasdiqlangan qonuniy vakili bilan muhokama qiling."]
    # Me'yoriy hujjatlar ro'yxatini institut kiritadi; u bo'lmaguncha havola O'YLAB TOPILMAYDI.
    return {"say": say, "tone": tone, "basis": ["Me'yoriy hujjat havolasi institut tomonidan hali kiritilmagan — o'ylab topilmaydi."] + BASIS.get(rule, [])}

# Umumiy huquqiy asos — aniq qaror raqamlari O'YLAB TOPILMAYDI; institut yuristi tasdiqlaguncha «manba aniqlashtiriladi».
BASIS = {
    "kontrakt": ["To'lov-kontrakt shartnomasi shartlari (manba aniqlashtiriladi)",
                 "Oliy ta'lim muassasalarida to'lov-kontrakt asosida o'qitish tartibi bo'yicha Vazirlar Mahkamasi qarori (manba aniqlashtiriladi)"],
    "davomat": ["Institut ichki tartib qoidalari va talabalar odob-axloq qoidalari (manba aniqlashtiriladi)",
                "Oliy ta'lim muassasalarida o'quv jarayonini tashkil etish va talabalar intizomi bo'yicha Vazirlar Mahkamasi qarori (manba aniqlashtiriladi)"],
    "akademik": ["Talabalar bilimini nazorat qilish va baholash tartibi to'g'risidagi nizom (manba aniqlashtiriladi)",
                 f"Institut akademik qoidalari: o'tish bali {AR.PASS} (akademik qoidalar taqdimoti)"],
    "hujjat": ["Institut ichki tartib qoidalari: sababli qoldirishni tasdiqlovchi hujjat muddati (manba aniqlashtiriladi)"],
    "tatil": ["Talabalarga akademik ta'til berish va o'qishga qayta tiklash tartibi bo'yicha Vazirlar Mahkamasi qarori (manba aniqlashtiriladi)"],
    "otrabotka": ["Institut akademik qoidalari: qayta topshirish (otrabotka) tartibi (manba aniqlashtiriladi)"],
}

def _log(con, case_id, task_id, sid, ctx, action, detail=""):
    con.execute("INSERT INTO ops_log(case_id,task_id,student_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?,?,?)",
                (case_id, task_id, sid, _iso(_now()), ctx.user["id"] if ctx else None, ctx.user["full_name"] if ctx else "ISFT Core (avtomatik)",
                 action, (detail or "")[:500]))

def _make_tasks(con, case_id, sid, fac, rule, level, facts, s, P, now):
    made = 0
    for kind, role, hrs in PLAN.get((rule, level), []):
        if role == SUPERVISOR and (rule, kind) in SIRTQI_ROUTE and s.get("study_form") == "sirtqi":
            role = "sirtqi"   # sirtqi talaba: ogohlantirish xatini Sirtqi bo'lim tayyorlaydi
        role = route(role, s)
        if con.execute("SELECT 1 FROM ops_tasks WHERE case_id=? AND kind=? AND status='yangi'", (case_id, kind)).fetchone():
            continue   # shu holat bo'yicha ochiq topshiriq bor — dublikat yo'q
        sc = script(rule, kind, facts, s, P, role)
        title = TITLE.get((rule, "xat_talaba") if rule == "kontrakt" and kind == "xat" and adult(s) else (rule, kind), KINDS[kind])
        cur = con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (case_id, sid, kind, title, role, fac,
                                                                _iso(_sla(rule, kind, facts, now, hrs)), "yangi", level, json.dumps(sc, ensure_ascii=False), _iso(now)))
        _log(con, case_id, cur.lastrowid, sid, None, "topshiriq yaratildi", f"{KINDS[kind]} → {ROLE_T.get(role, role)}")
        made += 1
    return made

ROLE_T = {"call_center": "Call-markaz", "tyutor": "Tyutor", "talabalar": "Registrator ofisi", "sirtqi": "Sirtqi bo'lim",
          "registrator_xodim": "Registrator ofisi xodimi"}

def _prev_workday(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5: d -= dt.timedelta(days=1)
    return d

def _sla(rule, kind, facts, created: dt.datetime, hrs) -> dt.datetime:
    """Topshiriqning HAQIQIY muddati. Kontrakt eslatmasi (to'lov sanasi hali o'tmagan) — sanadan oldingi ish kuni 18:00 gacha
    (qo'ng'iroq to'lovdan OLDIN bo'lishi kerak; juda kech ochilgan bo'lsa — kamida 8 soat, lekin to'lov kuni 18:00 dan kech emas)."""
    due = created + dt.timedelta(hours=hrs)
    if rule == "kontrakt" and kind == "qongiroq" and facts.get("due") and (facts.get("days") or 0) >= 0:
        d = dt.date.fromisoformat(facts["due"][:10])
        due = min(dt.datetime.combine(d, dt.time(18, 0)),
                  max(created + dt.timedelta(hours=8), dt.datetime.combine(_prev_workday(d), dt.time(18, 0))))
    return due.replace(microsecond=0)

def evaluate(con, today=None) -> dict:
    """Qoidalarni ishga tushiradi. Idempotent: necha marta chaqirilsa ham bitta holat = bitta ochiq yozuv."""
    with _lock:
        today = today or _today(); now = _now(); P = policy(con)
        sig = _signals(con, today)
        open_ = {c["key"]: c for c in db.rows(con, "SELECT * FROM ops_cases WHERE status='ochiq'")}
        studs = {s["id"]: s for s in db.rows(con, "SELECT id, full_name, faculty_id, study_form, level FROM students")}
        st = {"opened": 0, "escalated": 0, "closed": 0, "tasks": 0, "followups": 0}
        for key, (sid, rule, lvl, facts) in sig.items():
            s = studs[sid]; fj = json.dumps(facts, ensure_ascii=False)
            c = open_.get(key)
            if not c:
                cur = con.execute("""INSERT INTO ops_cases(key,student_id,rule,level,status,opened_at,updated_at,facts) VALUES(?,?,?,?,?,?,?,?)
                                     ON CONFLICT(key) DO UPDATE SET status='ochiq', level=excluded.level, opened_at=excluded.opened_at,
                                     updated_at=excluded.updated_at, facts=excluded.facts, closed_at=NULL, close_reason=NULL""",
                                  (key, sid, rule, lvl, "ochiq", _iso(now), _iso(now), fj))
                cid = con.execute("SELECT id FROM ops_cases WHERE key=?", (key,)).fetchone()[0]   # UPSERT'da lastrowid ishonchli emas
                _log(con, cid, None, sid, None, "holat ochildi", f"{RULES[rule]} · {LEVELS[lvl]}")
                st["opened"] += 1; st["tasks"] += _make_tasks(con, cid, sid, s["faculty_id"], rule, lvl, facts, s, P, now)
            else:
                con.execute("UPDATE ops_cases SET facts=?, updated_at=? WHERE id=?", (fj, _iso(now), c["id"]))
                if lvl > c["level"]:
                    con.execute("UPDATE ops_cases SET level=? WHERE id=?", (lvl, c["id"]))
                    _log(con, c["id"], None, sid, None, "daraja oshdi", f"{LEVELS[c['level']]} → {LEVELS[lvl]}")
                    st["escalated"] += 1; st["tasks"] += _make_tasks(con, c["id"], sid, s["faculty_id"], rule, lvl, facts, s, P, now)
                elif lvl < c["level"]:
                    con.execute("UPDATE ops_cases SET level=? WHERE id=?", (lvl, c["id"]))
                    _log(con, c["id"], None, sid, None, "daraja pasaydi", f"{LEVELS[c['level']]} → {LEVELS[lvl]}")
                # va'da muddati o'tdi va holat hamon ochiq → qayta qo'ng'iroq
                pr = db.one(con, """SELECT MAX(promise_date) p FROM ops_tasks WHERE case_id=? AND outcome='vada'""", (c["id"],))
                if pr and pr["p"] and pr["p"] < today.isoformat() and not con.execute(
                        "SELECT 1 FROM ops_tasks WHERE case_id=? AND status='yangi' AND kind='qongiroq'", (c["id"],)).fetchone() and not con.execute(
                        "SELECT 1 FROM ops_tasks WHERE case_id=? AND created_at>? AND kind='qongiroq'", (c["id"], pr["p"] + "T23:59:59")).fetchone():
                    sc = script(rule, "qongiroq", facts, s, P, "call_center"); sc["say"].insert(0, f"Talaba {_dmy(pr['p'])} gacha hal qilishga va'da bergan edi — muddat o'tdi.")
                    cur = con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (c["id"], sid, "qongiroq", "Va'da muddati o'tdi: qayta qo'ng'iroq", "call_center",
                                                                            s["faculty_id"], _iso(now + dt.timedelta(hours=8)), "yangi", lvl, json.dumps(sc, ensure_ascii=False), _iso(now)))
                    _log(con, c["id"], cur.lastrowid, sid, None, "va'da muddati o'tdi", f"qayta qo'ng'iroq rejalashtirildi ({pr['p']})")
                    st["followups"] += 1
        reasons = {"kontrakt": "to'lov yetarli darajada amalga oshirildi", "davomat": "sababsiz soatlar chegaradan pastga tushdi (hujjat tasdiqlangan)",
                   "akademik": "qarzdor fanlar yopildi", "hujjat": "hujjat masalasi hal bo'ldi", "tatil": "talaba o'qishga qaytdi",
                   "otrabotka": "varaqa topshirildi"}
        for key, c in open_.items():
            if key not in sig:
                con.execute("UPDATE ops_cases SET status='yopildi', closed_at=?, close_reason=? WHERE id=?", (_iso(now), reasons[c["rule"]], c["id"]))
                n = con.execute("UPDATE ops_tasks SET status='bekor', outcome='holat_yopildi', done_at=? WHERE case_id=? AND status='yangi'", (_iso(now), c["id"])).rowcount
                _log(con, c["id"], None, c["student_id"], None, "holat yopildi", reasons[c["rule"]] + (f"; {n} ta ochiq topshiriq bekor qilindi" if n else ""))
                st["closed"] += 1
        schedule_calls(con, today, now)
        sync_discipline(con)
        con.execute("INSERT OR REPLACE INTO ops_policy(key,value,label,verified) VALUES('_last_run',?, 'Oxirgi tekshiruv', 1)", (now.timestamp(),))
        con.commit()
        return st

# ---------------------------------------------------------------------------------------------
# Call-markaz navbatini kunlarga taqsimlash
# ---------------------------------------------------------------------------------------------
def _workday(d: dt.date, n: int) -> dt.date:
    """d dan boshlab n-ish kuni (dushanba–juma; d ish kuni bo'lmasa — keyingi ish kunidan)."""
    while d.weekday() >= 5: d += dt.timedelta(days=1)
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d

def operators(con) -> list[dict]:
    """Call-markaz operatorlari va har birining kunlik me'yori (call_operators; yozuv bo'lmasa — standart call_daily_capacity)."""
    std = int(policy(con).get("call_daily_capacity", 60))
    act = "AND COALESCE(u.active,1)!=0" if "active" in {r[1] for r in con.execute("PRAGMA table_info(users)")} else ""
    rows = db.rows(con, f"""SELECT u.id, u.full_name, COALESCE(co.capacity, {std}) capacity, COALESCE(co.active, 1) active
                            FROM users u LEFT JOIN call_operators co ON co.user_id=u.id WHERE u.role='call_center' {act} ORDER BY u.id""")
    for r in rows: r["short"] = _short(r["full_name"]); r["capacity"] = int(r["capacity"] or 0)
    return rows

def call_capacity(con) -> tuple[int, int]:
    """(kunlik umumiy imkoniyat, faol operatorlar soni)."""
    ops = [o for o in operators(con) if o["active"] and o["capacity"] > 0]
    return sum(o["capacity"] for o in ops), len(ops)

CALL_CAT_SQL = """CASE WHEN oc.rule='otrabotka' THEN 'otrabotka' WHEN t.title LIKE 'Va''da muddati%' THEN 'vada'
  WHEN oc.rule='kontrakt' AND CAST(COALESCE(json_extract(oc.facts,'$.days'),0) AS INT) >= 0 THEN 'kontrakt_eslatma'
  WHEN oc.rule='kontrakt' THEN 'kontrakt_otgan' ELSE oc.rule END"""
CALL_CAT = {"otrabotka": "Otrabotka muddati (bir necha soat ichida)", "vada": "Va'da muddati o'tgan — qayta qo'ng'iroq (8 soat)",
            "davomat": "Davomat: 30+ soat sababsiz (24 soat ichida)", "kontrakt_eslatma": "Kontrakt: to'lov sanasidan oldin eslatma",
            "kontrakt_otgan": "Kontrakt: muddati o'tgan to'lov (2 ish kuni)", "tatil": "Akademik ta'til tugashi (5 kun)",
            "akademik": "O'zlashtirish", "hujjat": "Hujjat"}

def _done_today(con, today):
    """Bugun operatorlar haqiqatda qilgan qo'ng'iroqlar (SMS bilan yopilgan va avtomatik bekor qilinganlar hisoblanmaydi)."""
    return {r[0]: r[1] for r in con.execute("""SELECT t.done_by, COUNT(*) FROM ops_tasks t JOIN users u ON u.id=t.done_by AND u.role='call_center'
                                               WHERE t.kind='qongiroq' AND t.done_at>=? AND COALESCE(t.outcome,'') NOT IN ('sms','holat_yopildi')
                                               GROUP BY t.done_by""", (today.isoformat(),))}

def schedule_calls(con, today=None, now=None):
    """Call-markaz navbatini ish kunlariga va operatorlarga taqsimlaydi. due_at — HAQIQIY muddat, bu yerda O'ZGARMAYDI; faqat planned_on
    (qaysi kun) va assignee_user (qaysi operator) yoziladi. Tartib: muddat kuni (o'tganlari — bugun) → jiddiylik → aniq muddat.
    Kunlik imkoniyat — operatorlar me'yorlari yig'indisi; bugun allaqachon qilingan qo'ng'iroqlar bugungi imkoniyatdan ayriladi.
    «Javob bermadi» bilan ertaga qoldirilgani shu kundan oldin qo'yilmaydi. Idempotent: bir xil holatda bir xil taqsimot."""
    today = today or _today(); now = now or _now()
    ops = [o for o in operators(con) if o["active"] and o["capacity"] > 0]
    rows = db.rows(con, """SELECT t.id, t.planned_on, t.due_at, t.level, t.attempts, t.assignee_user FROM ops_tasks t
                           WHERE t.status='yangi' AND t.assignee_role='call_center'""")
    if not ops:   # operator yo'q — rejalashtirilmaydi (summary «operator yo'q» deb ko'rsatadi)
        upd = [(r["id"],) for r in rows if r["planned_on"] or r["assignee_user"]]
        if upd: con.executemany("UPDATE ops_tasks SET planned_on=NULL, assignee_user=NULL WHERE id=?", upd)
        return len(upd)
    td = today.isoformat()
    rows.sort(key=lambda r: (max((r["due_at"] or "9999")[:10], td), -(r["level"] or 0), r["due_at"] or "", r["id"]))
    done = _done_today(con, today)
    used: dict[str, dict] = {}
    def left(day, o):
        u = used.setdefault(day, {})
        return o["capacity"] - u.get(o["id"], 0) - (done.get(o["id"], 0) if day == td else 0)
    first = _workday(today, 0)
    upd, day_ptr = [], first
    for r in rows:
        retry = bool(r["attempts"]) and r["planned_on"] and r["planned_on"] > td
        d = dt.date.fromisoformat(r["planned_on"]) if retry else day_ptr
        while True:
            ds = d.isoformat()
            o = max(ops, key=lambda o: (left(ds, o), -o["id"]))
            if left(ds, o) > 0: break
            d = _workday(d, 1)
            if not retry: day_ptr = d
        used[ds][o["id"]] = used[ds].get(o["id"], 0) + 1
        if r["planned_on"] != ds or r["assignee_user"] != o["id"]:
            upd.append((ds, o["id"], r["id"]))
    if upd:
        con.executemany("UPDATE ops_tasks SET planned_on=?, assignee_user=? WHERE id=?", upd)
    return len(upd)

def calls_summary(con, where="1=1", args=()):
    """Call-markaz navbati — HAQIQIY ko'rsatkichlar: kechikkan (muddati o'tgan), bugun muddati tugaydiganlar va bugungi imkoniyat,
    rejaga ko'ra kechikadiganlar (rejalashtirilgan kun muddatdan keyin), navbat qaysi kungacha yetadi, muqobil yo'llar."""
    today, nowd = _today(), _now()
    td, now = today.isoformat(), _iso(nowd)
    # «bugun qilinishi kerak» — muddati keyingi ish kuni ertalabigacha (09:00) tugaydiganlar: ertaga ish boshlanganda kech bo'ladi
    eod = _iso(dt.datetime.combine(_workday(today, 1) if today.weekday() < 5 else _workday(today, 0), dt.time(9, 0)))
    proj = _proj_sql(td, now)
    base = f"""FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id JOIN students s ON s.id=t.student_id
               WHERE t.status='yangi' AND t.assignee_role='call_center' AND {where}"""
    r = db.one(con, f"""SELECT COUNT(*) total, SUM(COALESCE(t.planned_on,'') <= ?) today, SUM(COALESCE(t.planned_on,'') > ?) scheduled,
                         SUM(t.due_at < ?) late, SUM(t.due_at < ?) due_today, SUM({proj}) projected_late, MAX(t.planned_on) last_day {base}""",
               (td, td, now, eod, *args))
    cap, nops = call_capacity(con)
    done = sum(_done_today(con, today).values())
    out = {k: (r[k] or 0) for k in ("total", "today", "scheduled", "late", "due_today", "projected_late")}
    cap_today = max(0, cap - done) if today.weekday() < 5 else 0
    out.update(capacity=cap, operators=nops, per_operator=(cap // nops) if nops else 0, last_day=r["last_day"], done_today=done,
               capacity_today=cap_today, shortfall_today=max(0, out["due_today"] - cap_today),
               days=(_busdays(today, dt.date.fromisoformat(r["last_day"])) + 1) if r["last_day"] and r["last_day"] > td else (1 if out["total"] else 0))
    out["groups"] = []
    for g in db.rows(con, f"""SELECT {CALL_CAT_SQL} cat, COUNT(*) n, SUM(t.due_at < ?) late, SUM({proj}) proj, MIN(t.due_at) first_due,
                               MAX(t.due_at) last_due, MAX(t.planned_on) last_plan {base} GROUP BY 1 ORDER BY MIN(t.due_at)""", (now, *args)):
        g["label"] = CALL_CAT.get(g["cat"], g["cat"]); out["groups"].append(g)
    # muqobil yo'llar: past jiddiylikdagi kontrakt eslatmasi — ommaviy SMS/Telegram; kechikadiganlarni boshqa xodimlarga o'tkazish
    sms = db.one(con, f"SELECT COUNT(*) n {base} AND {CALL_CAT_SQL}='kontrakt_eslatma'", args)["n"]
    red = db.one(con, f"""SELECT SUM(COALESCE(s.study_form,'kunduzgi')='kunduzgi' AND s.group_id IN (SELECT group_id FROM tutor_groups)) tutor,
                           SUM(s.study_form='sirtqi') sirtqi, COUNT(*) n {base} AND {proj} AND {CALL_CAT_SQL}!='kontrakt_eslatma'""", args)
    P = policy(con)
    nt = con.execute("SELECT COUNT(DISTINCT user_id) FROM tutor_groups").fetchone()[0]
    nx = con.execute("SELECT COUNT(*) FROM users WHERE role=?", (REG_STAFF,)).fetchone()[0]
    out["alternatives"] = {"sms": sms, "overflow": red["n"] or 0, "to_tutor": red["tutor"] or 0, "to_sirtqi": red["sirtqi"] or 0,
                           "to_staff": (red["n"] or 0), "tutors": nt, "staff": nx,
                           "tutor_capacity": int(P.get("tutor_call_capacity", 10)), "staff_capacity": int(P.get("staff_call_capacity", 40))}
    out["text"] = shortfall_text(out)
    return out

def _proj_sql(td, now):
    """Rejaga ko'ra kechikadimi: bugungi ro'yxatda — muddati allaqachon o'tgan bo'lsa; keyingi kunlarda — o'sha kun 18:00 muddatdan keyin bo'lsa."""
    return (f"(t.planned_on IS NULL OR (t.planned_on <= '{td}' AND t.due_at < '{now}') "
            f"OR (t.planned_on > '{td}' AND t.planned_on || 'T18:00:00' > t.due_at))")

def _fmt(n): return f"{int(n):,}".replace(",", " ")

def shortfall_text(cs) -> str:
    """«bugun 60 ta imkoniyat, muddati ichida qilinishi kerak 412 ta — 352 ta kechikadi» — yashirmasdan."""
    if not cs["total"]: return "Call-markaz navbati bo'sh."
    if not cs["operators"]: return f"Faol operator yo'q: {_fmt(cs['total'])} ta qo'ng'iroq rejalashtirilmagan — operator me'yorini kiriting."
    t = (f"Bugun {_fmt(cs['capacity_today'])} ta imkoniyat ({cs['operators']} operator), muddati ichida qilinishi kerak "
         f"{_fmt(cs['due_today'])} ta" + (f" — {_fmt(cs['shortfall_today'])} tasi kechikadi." if cs["shortfall_today"] else " — imkoniyat yetadi."))
    if cs["projected_late"]:
        t += f" Joriy reja bo'yicha jami {_fmt(cs['projected_late'])} ta qo'ng'iroq muddatidan keyin qilinadi"
        t += f" (navbat {_dmy(cs['last_day'])} gacha, ~{cs['days']} ish kuni)." if cs.get("last_day") else "."
    if cs["late"]: t += f" Hozir {_fmt(cs['late'])} tasining muddati o'tgan."
    return t

def _busdays(a: dt.date, b: dt.date) -> int:
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: n += 1
    return n

async def poller():
    await asyncio.sleep(5)
    while True:
        try:
            await asyncio.to_thread(evaluate, _con)
        except Exception as e:   # fon jarayoni to'xtamasin
            print("student_ops poller:", e)
        await asyncio.sleep(600)

# ---------------------------------------------------------------------------------------------
# Ruxsat va ko'lam
# ---------------------------------------------------------------------------------------------
def _guard(c: Ctx, action, detail=""):
    rbac.require(_con, c, OPS, action, detail)

# Ko'lami va qoidalari cheklangan lavozimlar:
#   Sirtqi bo'lim — sirtqi ta'lim talabalari uchun REGISTRATOR (Baratov): otrabotka varaqasi, bahoni tasdiqlash/qaytarish, topshiriqlar
#     (kontrakt va buyruq loyihalaridan tashqari), ma'lumotnoma/transkript/ogohlantirish/chaqiruv xati/ruxsatnoma — faqat sirtqi talabalarga.
#     Kontrakt holatlarini faqat O'QIYDI: sessiyaga qo'yish va imtihonga ruxsatnoma to'lov holatiga bog'liq. Institut bo'yicha
#     kontrakt jamlanmasi (rbac CONTRACTS) ochilmaydi — faqat o'z ko'lamidagi talabaning to'lov holati.
#   Kafedra mudiri — o'z kafedrasi guruhlari, o'quv qoidalari (o'qish); Buxgalteriya — faqat kontrakt qoidasi (o'qish);
#   Imtihon bo'limi — o'zlashtirish va otrabotka holatlarini faqat ko'radi (varaqa bermaydi — bu Registrator ofisi ishi).
SCOPED_VIEW = ("sirtqi", "kafedra", "buxgalteriya", "imtihon")
RETAKE_ISSUERS = (SUPERVISOR, REG_STAFF, "tyutor", "sirtqi")   # otrabotka varaqasini beradi va skanni yuklaydi (sirtqi — faqat sirtqi talabalarga)
RETAKE_APPROVERS = (SUPERVISOR, "sirtqi")            # bahoni tasdiqlaydi / varaqani qaytaradi (sirtqi — o'z ko'lamida)
RETAKE_DENY = "⛔ Otrabotka varaqasini Registrator ofisi, tyutor yoki (sirtqi talabalarga) Sirtqi bo'lim beradi. Imtihon bo'limi faqat ko'radi."
RULE_SCOPE = {"kafedra": ("akademik", "otrabotka", "davomat"), "buxgalteriya": ("kontrakt",),
              "sirtqi": ("kontrakt", "akademik", "davomat", "hujjat", "tatil", "otrabotka"), "imtihon": ("akademik", "otrabotka")}

def tutor_groups_sql(c: Ctx) -> str:
    """Tyutorga biriktirilgan guruhlar (tutor_groups) — SQL ichki so'rovi."""
    return f"(SELECT group_id FROM tutor_groups WHERE user_id={int(c.user['id'] or 0)})"

def _scope_sql(c: Ctx, alias="s"):
    k = c.role.key
    if k in FULL_VIEW: return "1=1"
    if k in FAC_VIEW: return f"{alias}.group_id IN {tutor_groups_sql(c)}"
    if k == "sirtqi": return f"{alias}.study_form='sirtqi'"
    if k == "kafedra": return f"{alias}.group_id IN (SELECT id FROM groups_ WHERE department_id={int(c.user['department_id'] or 0)})"
    if k == "buxgalteriya": return f"{alias}.payment_type='kontrakt'"
    if k == "imtihon": return "1=1"
    return "0=1"

def _rule_sql(c: Ctx, col="oc.rule"):
    rs = RULE_SCOPE.get(c.role.key)
    return "1=1" if not rs else f"{col} IN ({','.join(repr(r) for r in rs)})"

def _rule_ok(c: Ctx, rule) -> bool:
    rs = RULE_SCOPE.get(c.role.key)
    return not rs or rule in rs

MY_QUEUE = {SUPERVISOR: ("talabalar", REG_STAFF), REG_STAFF: ("talabalar", REG_STAFF), "sirtqi": ("sirtqi",)}
ROLE_FILTER = (SUPERVISOR, "prorektor_oquv", "akademik", "sirtqi")   # «Mas'ul» filtri bor lavozimlar (boshqalar navbatini ham ko'radi)   # «Mening navbatim» — Registrator ofisi ishlari

def _task_scope_sql(c: Ctx):
    k = c.role.key
    if k == REG_STAFF:   # xodimning navbati: Registrator ofisi ishlari va unga o'tkazilganlar; call-markaz qo'ng'iroqlari va buyruq loyihalari — yo'q
        return f"t.assignee_role IN ('{SUPERVISOR}','{REG_STAFF}') AND t.kind!='buyruq'"
    if k in FULL_VIEW: return "1=1"
    if k == "call_center":   # bir nechta operator: o'ziga taqsimlangan (yoki hali taqsimlanmagan) qo'ng'iroqlar
        return f"t.assignee_role='call_center' AND (t.assignee_user IS NULL OR t.assignee_user={int(c.user['id'] or 0)})"
    if k == "tyutor": return f"t.assignee_role='tyutor' AND s.group_id IN {tutor_groups_sql(c)}"   # faqat o'z guruhlari talabalari
    if k in SCOPED_VIEW: return f"{_scope_sql(c, 's')} AND t.case_id IN (SELECT id FROM ops_cases oc2 WHERE {_rule_sql(c, 'oc2.rule')})"
    return "0=1"

def _can_act(c: Ctx, t) -> bool:
    if t["status"] != "yangi": return False
    if c.role.key == SUPERVISOR: return True
    if c.role.key == REG_STAFF: return t["assignee_role"] in (SUPERVISOR, REG_STAFF, "call_center", "tyutor") and t["kind"] != "buyruq"
    if c.role.key == "call_center": return t["assignee_role"] == "call_center"
    if c.role.key == "tyutor":
        return t["assignee_role"] == "tyutor" and bool(_con.execute(
            f"SELECT 1 FROM students WHERE id=? AND group_id IN {tutor_groups_sql(c)}", (t["student_id"],)).fetchone())
    if c.role.key == "sirtqi":   # sirtqi talabalar bo'yicha registrator: kontrakt va buyruq loyihasidan tashqari hammasi
        if t["kind"] == "buyruq": return False
        r = _con.execute("""SELECT oc.rule, s.study_form FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE oc.id=?""", (t["case_id"],)).fetchone()
        return bool(r) and r[1] == "sirtqi" and r[0] != "kontrakt"
    return False

def _mask(phone, c: Ctx):
    if not phone: return None
    return phone if c.role.key in ("call_center", "tyutor", SUPERVISOR, REG_STAFF) else phone[:8] + " *** ** " + phone[-2:]

def rule_scope(c: Ctx) -> list[str]:
    """Lavozim ishlaydigan qoidalar (kartalar faqat shular uchun; ko'lamdan tashqari qoida «0, yashil» bo'lib chiqmaydi)."""
    k = c.role.key
    if k in RULE_SCOPE: return [r for r in RULES if r in RULE_SCOPE[k]]
    if k in ("call_center", "tyutor"):
        mine = {r for (r, _), v in PLAN.items() for _, ro, _ in v if ro == k}
        mine |= {r[0] for r in _con.execute(f"""SELECT DISTINCT oc.rule FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id
                                                JOIN students s ON s.id=t.student_id WHERE t.status='yangi' AND {_task_scope_sql(c)}""")}
        return [r for r in RULES if r in mine]
    return list(RULES)

# ---------------------------------------------------------------------------------------------
# O'qish
# ---------------------------------------------------------------------------------------------
def summary(c: Ctx):
    sync_discipline(_con)
    now = _iso(_now())
    if c.role.key == "call_center":   # operator: faqat o'z navbatidagi holatlar
        tw = _task_scope_sql(c)
        by = db.rows(_con, f"""SELECT oc.rule, oc.level, COUNT(DISTINCT oc.id) n FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id
                                  WHERE t.status='yangi' AND oc.status='ochiq' AND {tw} GROUP BY oc.rule, oc.level""")
        tasks = db.rows(_con, f"""SELECT t.assignee_role role, COUNT(*) n, SUM(t.due_at < ?) late FROM ops_tasks t
                                    WHERE t.status='yangi' AND {tw} GROUP BY t.assignee_role""", (now,))
        done = _con.execute("SELECT COUNT(*) FROM ops_tasks WHERE done_by=? AND done_at>=?", (c.user["id"], _today().isoformat())).fetchone()[0]
        return {"by_rule": by, "tasks": tasks, "closed_7d": 0, "done_today": done, "rules": RULES, "levels": LEVELS, "last_run": None,
                "calls": calls_summary(_con), "unit": "holat", "rule_scope": rule_scope(c), "can_plan": False,
                "note": "Call-markaz navbatidagi HOLATLAR soni (bitta talabada bir nechta holat bo'lishi mumkin) — «O'qishda xavf» (talabalar soni) bilan bir xil ko'rsatkich emas"}
    w = "1=1" if c.role.key in FULL_VIEW + AGG_VIEW else _scope_sql(c)
    rw = _rule_sql(c)
    by = db.rows(_con, f"""SELECT oc.rule, oc.level, COUNT(*) n FROM ops_cases oc JOIN students s ON s.id=oc.student_id
                              WHERE oc.status='ochiq' AND {w} AND {rw} GROUP BY oc.rule, oc.level""")
    tasks = db.rows(_con, f"""SELECT t.assignee_role role, COUNT(*) n, SUM(t.due_at < ?) late FROM ops_tasks t JOIN students s ON s.id=t.student_id
                                WHERE t.status='yangi' AND {w} AND t.case_id IN (SELECT id FROM ops_cases oc WHERE {rw})
                                GROUP BY t.assignee_role""", (now,))
    closed7 = _con.execute(f"""SELECT COUNT(*) FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE oc.status='yopildi'
                                 AND oc.closed_at>=? AND {w} AND {rw}""", (_iso(_now() - dt.timedelta(days=7)),)).fetchone()[0]
    last = _con.execute("SELECT value FROM ops_policy WHERE key='_last_run'").fetchone()
    M = risk_metrics(_con, w) if c.role.key not in RULE_SCOPE else None   # qoidalari cheklangan lavozimlarda — umumiy xavf soni ko'rsatilmaydi
    mine = None
    if c.role.key in ("tyutor", REG_STAFF, SUPERVISOR, "sirtqi"):   # «Mening navbatim» hisoblagichi — kartadagi bilan bir xil ko'lam
        mw = _task_scope_sql(c) + (f" AND t.assignee_role IN ({','.join(repr(x) for x in MY_QUEUE[c.role.key])})" if c.role.key in (SUPERVISOR, "sirtqi") else "")
        mine = db.one(_con, f"""SELECT COUNT(*) n, SUM(t.due_at < ?) late FROM ops_tasks t JOIN students s ON s.id=t.student_id
                                WHERE t.status='yangi' AND {mw}""", (now,))
        mine = {"n": mine["n"] or 0, "late": mine["late"] or 0}
    return {"by_rule": by, "tasks": tasks, "closed_7d": closed7, "rules": RULES, "levels": LEVELS, "unit": "holat",
            # serious_students — panelda «O'qishda xavf» bilan bir xil son (academic_rules.RISK_DEF); holatlar (by_rule) — boshqa birlik
            "serious_students": M["at_risk"]["n"] if M else None, "metrics": M, "rule_scope": rule_scope(c), "mine": mine,
            "can_plan": c.role.key == SUPERVISOR,
            "last_run": clock.from_ts(last[0]).isoformat(timespec="seconds") if last else None,
            "calls": calls_summary(_con, w)}

def risk_metrics(con, w="1=1") -> dict:
    """Yagona ko'rsatkichlar (academic_rules): «O'qishda xavf» — talabalar soni, «Akademik qarzdor» — talabalar soni, faol talabalar.
    Panel (services), Talabalar markazi va Reyting shu funksiyadan / shu ta'riflardan oladi."""
    n = con.execute(f"SELECT COUNT(*) FROM students s WHERE s.status='faol' AND {w}").fetchone()[0]
    risk = con.execute(f"""SELECT COUNT(DISTINCT oc.student_id) FROM ops_cases oc JOIN students s ON s.id=oc.student_id
                           WHERE oc.status='ochiq' AND oc.rule IN ('akademik','davomat') AND oc.level>={AR.AT_RISK_LEVEL}
                           AND s.status='faol' AND {w}""").fetchone()[0]
    debt = con.execute(f"""SELECT COUNT(DISTINCT g.student_id) FROM grades g JOIN students s ON s.id=g.student_id
                           WHERE {AR.debt_where('g')} AND s.status='faol' AND {w}""").fetchone()[0]
    return {"students": n, "at_risk": {"n": risk, "label": AR.RISK_LABEL, "unit": "talaba", "def": AR.RISK_DEF},
            "debtors": {"n": debt, "label": AR.DEBTOR_LABEL, "unit": "talaba", "def": AR.DEBTOR_DEF}}

def _student_row(c: Ctx, sid):
    s = db.one(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.phone, s.faculty_id, s.status, s.payment_type, s.contract_amount, s.paid_amount,
                         g.name grp, g.course, f.name faculty FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
                         WHERE s.id=? AND {_scope_sql(c)}""", (sid,))
    if not s: raise AccessDenied("⛔ Bu talaba sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    s["phone"] = _mask(s["phone"], c)
    return s

def cases(c: Ctx, rule="", level=0, q="", faculty=0, limit=300, grp="", course=0):
    w = [_scope_sql(c), "oc.status='ochiq'", _rule_sql(c)]; a = []
    if grp: w.append("g.name=?"); a.append(grp[:40])
    if course: w.append("g.course=?"); a.append(int(course))
    if rule in RULES: w.append("oc.rule=?"); a.append(rule)
    if level: w.append("oc.level>=?"); a.append(int(level))
    if faculty: w.append("s.faculty_id=?"); a.append(int(faculty))
    if q: w.append("(s.full_name LIKE ? OR g.name LIKE ? OR s.hemis_id LIKE ?)"); a += [f"%{q}%"] * 3
    rows = db.rows(_con, f"""SELECT oc.id, oc.rule, oc.level, oc.opened_at, oc.updated_at, oc.facts, s.id student_id, s.full_name, g.name grp, g.course,
                              f.name faculty, (SELECT COUNT(*) FROM ops_tasks t WHERE t.case_id=oc.id AND t.status='yangi') open_tasks
                              FROM ops_cases oc JOIN students s ON s.id=oc.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
                              WHERE {' AND '.join(w)} ORDER BY oc.level DESC, oc.updated_at DESC LIMIT ?""", (*a, limit))
    for r in rows: r["facts"] = json.loads(r["facts"] or "{}")
    return rows

def _filters(c: Ctx, rule="", kind="", grp="", course=0, faculty=0, role="", late=False):
    """Navbat filtrlari (SQL, args): qoida, tur, guruh, kurs, fakultet, mas'ul lavozim (Registrator ofisi uchun), faqat kechikkan."""
    w, a = [], []
    if rule in RULES: w.append("oc.rule=?"); a.append(rule)
    if kind in KINDS: w.append("t.kind=?"); a.append(kind)
    if grp: w.append("g.name=?"); a.append(grp[:40])
    if course: w.append("g.course=?"); a.append(int(course))
    if faculty: w.append("s.faculty_id=?"); a.append(int(faculty))
    if c.role.key in ROLE_FILTER:
        if role == "all": pass
        elif role in ROLE_T: w.append("t.assignee_role=?"); a.append(role)
        elif c.role.key in MY_QUEUE: w.append(f"t.assignee_role IN ({','.join(repr(x) for x in MY_QUEUE[c.role.key])})")
    if late: w.append("t.due_at < ?"); a.append(_iso(_now()))
    return (" AND " + " AND ".join(w)) if w else "", a

TASK_FROM = """FROM ops_tasks t JOIN students s ON s.id=t.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
               JOIN ops_cases oc ON oc.id=t.case_id"""

def tasks(c: Ctx, status="yangi", limit=200, rule="", kind="", grp="", course=0, faculty=0, role="", late=False):
    extra, a = _filters(c, rule, kind, grp, course, faculty, role, late)
    td, now = _today().isoformat(), _iso(_now())
    rows = db.rows(_con, f"""SELECT t.*, s.full_name, s.phone, s.hemis_id, s.study_form, g.name grp, g.course, f.name faculty, oc.rule, oc.facts
                              {TASK_FROM} WHERE {_task_scope_sql(c)} AND t.status=?{extra}
                              ORDER BY (COALESCE(t.planned_on,'') > ?), COALESCE(t.planned_on,''), MAX(substr(t.due_at,1,10), ?), t.level DESC, t.due_at, t.id
                              LIMIT ?""", (status, *a, td, td, limit))
    for r in rows: _task_view(r, c, now, td)
    return rows

def _task_view(r, c: Ctx, now, td):
    r["scheduled"] = bool(r.get("planned_on") and r["planned_on"] > td)   # keyingi kunlarga rejalashtirilgan qo'ng'iroq
    r["script"] = json.loads(r["script"] or "{}") if isinstance(r.get("script"), str) else (r.get("script") or {})
    if isinstance(r.get("facts"), str): r["facts"] = json.loads(r["facts"] or "{}")
    if "phone" in r: r["phone"] = _mask(r["phone"], c)
    r["late"] = r["status"] == "yangi" and bool(r["due_at"]) and r["due_at"] < now          # faqat muddati haqiqatda o'tganlar
    r["will_be_late"] = (not r["late"] and r["status"] == "yangi" and bool(r.get("planned_on")) and bool(r["due_at"])
                         and r["planned_on"] > td and r["planned_on"] + "T18:00:00" > r["due_at"])                     # reja bo'yicha muddatdan keyin qilinadi
    r["can_act"] = _can_act(c, r)
    return r

def task_facets(c: Ctx, rule="", kind="", grp="", course=0, faculty=0, role="", late=False):
    """Navbat filtrlari uchun: jami, kechikkan, guruhlar va kurslar (shu filtrlar bilan), turlar bo'yicha son."""
    extra, a = _filters(c, rule, kind, grp, course, faculty, role, late)
    base = f"{TASK_FROM} WHERE {_task_scope_sql(c)} AND t.status='yangi'{extra}"
    now = _iso(_now())
    tot = db.one(_con, f"SELECT COUNT(*) n, SUM(t.due_at < ?) late, SUM(COALESCE(t.planned_on,'') > ?) later {base}", (now, _today().isoformat(), *a))
    ex_g, a_g = _filters(c, rule, kind, "", course, faculty, role, late)
    ex_c, a_c = _filters(c, rule, kind, "", 0, faculty, role, late)
    ex_k, a_k = _filters(c, rule, "", grp, course, faculty, role, late)
    sc = _task_scope_sql(c)
    return {"n": tot["n"] or 0, "late": tot["late"] or 0, "later": tot["later"] or 0,
            "groups": db.rows(_con, f"SELECT g.name, COUNT(*) n {TASK_FROM} WHERE {sc} AND t.status='yangi'{ex_g} GROUP BY g.name ORDER BY g.name", a_g),
            "courses": db.rows(_con, f"SELECT g.course, COUNT(*) n {TASK_FROM} WHERE {sc} AND t.status='yangi'{ex_c} GROUP BY g.course ORDER BY g.course", a_c),
            "kinds": db.rows(_con, f"SELECT t.kind, COUNT(*) n {TASK_FROM} WHERE {sc} AND t.status='yangi'{ex_k} GROUP BY t.kind", a_k),
            "roles": db.rows(_con, f"""SELECT t.assignee_role role, COUNT(*) n {TASK_FROM} WHERE {sc} AND t.status='yangi'
                                       {_filters(c, rule, kind, grp, course, faculty, 'all', late)[0]} GROUP BY 1""",
                             _filters(c, rule, kind, grp, course, faculty, "all", late)[1]) if c.role.key in ROLE_FILTER else []}

def student_card(c: Ctx, sid):
    s = _student_row(c, sid)
    f = student_facts(_con, sid)
    cs = [x for x in db.rows(_con, "SELECT * FROM ops_cases WHERE student_id=? ORDER BY status, level DESC, id DESC", (sid,)) if _rule_ok(c, x["rule"])]
    for x in cs: x["facts"] = json.loads(x["facts"] or "{}")
    ok_case = {x["id"] for x in cs}
    ts = [x for x in db.rows(_con, f"SELECT t.* FROM ops_tasks t WHERE t.student_id=? ORDER BY t.id DESC", (sid,)) if c.role.key not in RULE_SCOPE or x["case_id"] in ok_case]
    now, td = _iso(_now()), _today().isoformat()
    for x in ts: _task_view(x, c, now, td)
    ab = db.rows(_con, "SELECT * FROM absences WHERE student_id=? ORDER BY start DESC", (sid,))
    log = db.rows(_con, "SELECT * FROM ops_log WHERE student_id=? ORDER BY id DESC LIMIT 60", (sid,))
    if c.role.key == "buxgalteriya":   # faqat kontrakt: baholar, davomat va boshqa holatlar jurnali ko'rsatilmaydi
        f = {}; ab = []; log = [x for x in log if x.get("case_id") in ok_case]
    for x in log: x["user_short"] = _short(x["user_name"])
    rt = [] if c.role.key == "buxgalteriya" else db.rows(_con, "SELECT * FROM retakes WHERE student_id=? ORDER BY id DESC", (sid,))
    lv = db.rows(_con, "SELECT * FROM student_leaves WHERE student_id=?", (sid,))
    debt = (s["contract_amount"] or 0) - (s["paid_amount"] or 0)
    if c.role.key == "kafedra":   # kontrakt ruxsati yo'q — moliyaviy maydonlar ko'rsatilmaydi (sirtqi bo'lim o'z talabalarining to'lov holatini ko'radi)
        debt = None; s = {k: v for k, v in s.items() if k not in ("contract_amount", "paid_amount")}
    now = _now()
    for r in rt: _retake_view(r, now)
    reg = c.role.key in RETAKE_APPROVERS + (REG_STAFF,)
    disc = [] if c.role.key == "buxgalteriya" else db.rows(_con, "SELECT * FROM discipline WHERE student_id=? ORDER BY id DESC", (sid,))
    hist = [] if c.role.key == "buxgalteriya" else db.rows(_con, """SELECT subject, semester, attempt, kind, oraliq, yakuniy, score, at, counted
                                                                    FROM grade_attempts WHERE student_id=? ORDER BY semester DESC, subject, attempt""", (sid,))
    for h in hist: h["sem_label"] = AR.SEMESTER_SHORT.get(h["semester"])
    return {"student": s, "facts": f, "debt": debt, "cases": cs, "tasks": ts, "absences": ab, "log": log, "retakes": rt, "leaves": lv,
            "discipline": disc, "attempts": hist,
            "reasons": REASONS, "can_doc": c.role.key in (SUPERVISOR, REG_STAFF, "tyutor", "sirtqi"), "can_retake": c.role.key in RETAKE_ISSUERS,
            "can_permit": reg, "can_schedule": reg, "can_defer": c.role.key == SUPERVISOR}

# ---------------------------------------------------------------------------------------------
# Otrabotka
# ---------------------------------------------------------------------------------------------
def _issue_sheet(con, ctx, rid, base_url):
    from . import documents as D
    r = D.issue(con, ctx, "retake_sheet", {"retake": rid}, base_url)
    con.execute("UPDATE retakes SET reg_no=? WHERE id=?", (r["regs"][0], rid))
    return r

RETAKE_KINDS = {"qarz": "Akademik qarz (yakunlangan semestr)", "oraliq": "Oraliq nazorat (joriy semestr)", "dars": "Qoldirilgan mashg'ulot"}
RETAKE_REASON = {"qarz": "Akademik qarz: yakuniy ball o'tish balidan past", "oraliq": f"Oraliq nazorat {AR.ORALIQ_MIN} balldan past (yakuniyga kiritilmaydi)",
                 "dars": "Sababsiz qoldirilgan mashg'ulotni qayta ishlash"}

def retakes_list(c: Ctx):
    rows = db.rows(_con, f"""SELECT r.*, s.full_name, s.study_form, g.name grp, f.name faculty, t.full_name teacher,
                              (SELECT CASE WHEN COALESCE(r.kind,'qarz')='oraliq' THEN gg.oraliq WHEN r.kind='dars' THEN NULL ELSE gg.score END
                               FROM grades gg WHERE gg.student_id=r.student_id AND gg.subject=r.subject
                               AND gg.semester=COALESCE(r.semester, {AR.CURRENT_SEMESTER})) hemis_score FROM retakes r
                              JOIN students s ON s.id=r.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
                              LEFT JOIN teachers t ON t.id=r.teacher_id WHERE {_scope_sql(c)}
                              ORDER BY CASE r.status WHEN 'topshirildi' THEN 0 WHEN 'berildi' THEN 1 ELSE 2 END, r.due_at""")
    now = _now()
    for r in rows: _retake_view(r, now)
    return rows

def retake_tone(hours_left):
    """Otrabotka muddati rangi (Baratov): yashil → 2 kun qolganda sariq → 1 kun va kam / o'tgan — qizil."""
    if hours_left is None: return None
    return "red" if hours_left <= 24 else "amber" if hours_left <= 48 else "green"

def _retake_view(r, now):
    r["kind"] = r.get("kind") or "qarz"
    r["kind_label"] = RETAKE_KINDS.get(r["kind"], r["kind"])
    r["sem_label"] = AR.SEMESTER_SHORT.get(r.get("semester") if r.get("semester") is not None else AR.CURRENT_SEMESTER)
    r["max_score"] = AR.ORALIQ_MAX if r["kind"] == "oraliq" else None if r["kind"] == "dars" else 100
    r["hours_left"] = round((dt.datetime.fromisoformat(r["due_at"]) - now).total_seconds() / 3600, 1) if r["status"] == "berildi" and r.get("due_at") else None
    r["tone"] = retake_tone(r["hours_left"])
    r["overdue"] = r["hours_left"] is not None and r["hours_left"] < 0
    try: r["scan"] = json.loads(r.get("scan_meta") or "null")
    except ValueError: r["scan"] = None
    r.pop("scan_meta", None)
    return r

# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx: return _ctx(request)

def _view_guard(c: Ctx, action):
    _guard(c, action)
    if c.role.key in AGG_VIEW:
        raise AccessDenied("⛔ Rahbariyat uchun bu bo'lim faqat jamlangan ko'rinishda — individual talaba ro'yxati registrator va tyutorlarda.")

@router.get("/api/ops/summary")
def api_summary(request: Request):
    c = C(request); _guard(c, "talabalar markazi: umumiy holat")
    return summary(c)

@router.get("/api/ops/cases")
def api_cases(request: Request, rule: str = "", level: int = 0, q: str = "", faculty: int = 0, grp: str = "", course: int = 0):
    c = C(request); _view_guard(c, "talabalar markazi: holatlar ro'yxati")
    if c.role.key == "call_center": raise AccessDenied("⛔ Call-markaz faqat o'z qo'ng'iroqlar navbatini ko'radi.")
    return cases(c, rule, level, q.strip()[:60], faculty, grp=grp.strip(), course=course)

@router.get("/api/ops/tasks")
def api_tasks(request: Request, status: str = "yangi", rule: str = "", kind: str = "", grp: str = "", course: int = 0, faculty: int = 0,
              role: str = "", late: int = 0, limit: int = 200):
    c = C(request); _view_guard(c, "talabalar markazi: topshiriqlar navbati")
    if status not in ("yangi", "bajarildi"): raise HTTPException(400)
    return tasks(c, status, max(1, min(limit, 500)), rule, kind, grp.strip(), course, faculty, role, bool(late))

@router.get("/api/ops/tasks/facets")
def api_task_facets(request: Request, rule: str = "", kind: str = "", grp: str = "", course: int = 0, faculty: int = 0, role: str = "", late: int = 0):
    c = C(request); _view_guard(c, "talabalar markazi: navbat filtrlari")
    return task_facets(c, rule, kind, grp.strip(), course, faculty, role, bool(late))

@router.get("/api/ops/student/{sid}")
def api_student(sid: int, request: Request):
    c = C(request); _view_guard(c, "talabalar markazi: talaba kartasi")
    if c.role.key == "call_center":   # call-markaz: faqat o'z navbatidagi talaba, minimal ma'lumot
        if not _con.execute("SELECT 1 FROM ops_tasks WHERE student_id=? AND assignee_role='call_center'", (sid,)).fetchone():
            raise AccessDenied("⛔ Bu talaba sizning navbatingizda emas.")
        st = db.one(_con, """SELECT s.id, s.full_name, s.phone, g.name grp, g.course, f.name faculty FROM students s
                             JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id WHERE s.id=?""", (sid,))
        ts = db.rows(_con, "SELECT * FROM ops_tasks WHERE student_id=? AND assignee_role='call_center' ORDER BY id DESC", (sid,))
        now, td = _iso(_now()), _today().isoformat()
        for x in ts: _task_view(x, c, now, td)
        return {"student": st, "tasks": ts, "log": [], "cases": [], "absences": [], "retakes": [], "leaves": [], "limited": True}
    rbac.audit(_con, c, "talaba kartasi (markaz)", OPS, True, f"#{sid}")
    return student_card(c, sid)

class Outcome(BaseModel):
    outcome: str
    note: str = Field("", max_length=1000)
    promise_date: str | None = None

OUTCOMES = {"qongiroq": ("gaplashildi", "vada", "javob_bermadi", "notogri_raqam"),
            "suhbat": ("bajarildi",), "hujjat": ("hujjat_keldi", "hujjat_yoq"), "xat": ("bajarildi",), "buyruq": ("bajarildi",)}
OUT_T = {"sms": "SMS/Telegram eslatma yuborildi", "taqsimlandi": "Boshqa xodimga o'tkazildi", "gaplashildi": "Gaplashildi", "vada": "Va'da berdi", "javob_bermadi": "Javob bermadi", "notogri_raqam": "Noto'g'ri raqam",
         "bajarildi": "Bajarildi", "hujjat_keldi": "Hujjat keldi (tasdiqlandi)", "hujjat_yoq": "Hujjat yo'q (sababsiz hisoblanadi)"}

@router.post("/api/ops/tasks/{tid}/outcome")
def api_outcome(tid: int, body: Outcome, request: Request):
    c = C(request); _guard(c, "talabalar markazi: topshiriq natijasi", f"#{tid} {body.outcome}")
    t = db.one(_con, "SELECT * FROM ops_tasks WHERE id=?", (tid,))
    if not t: raise HTTPException(404)
    if t["status"] != "yangi": raise HTTPException(409, "Topshiriq allaqachon yopilgan")
    if not _can_act(c, t): raise AccessDenied("⛔ Bu topshiriq sizning navbatingizda emas.")
    if body.outcome not in OUTCOMES.get(t["kind"], ()): raise HTTPException(400, "Bu topshiriq uchun natija noto'g'ri")
    now, today, P = _now(), _today(), policy(_con)
    note = body.note.strip()
    if body.outcome == "vada":
        try: pd = dt.date.fromisoformat(body.promise_date or "")
        except ValueError: raise HTTPException(400, "Va'da sanasini kiriting")
        if not (today <= pd <= today + dt.timedelta(days=30)): raise HTTPException(400, "Va'da sanasi bugundan 30 kungacha bo'lishi kerak")
    with _lock:
        if body.outcome == "javob_bermadi":
            att = (t["attempts"] or 0) + 1
            if att < int(P["call_max_attempts"]):
                nxt = _workday(today, 1)
                _con.execute("UPDATE ops_tasks SET attempts=?, due_at=?, planned_on=?, note=? WHERE id=?",
                             (att, _iso(max(now + dt.timedelta(days=1), dt.datetime.combine(nxt, dt.time(18, 0)))), nxt.isoformat(), note, tid))
                _log(_con, t["case_id"], tid, t["student_id"], c, "javob bermadi", f"{att}-urinish; ertaga qayta")
                _con.commit(); return {"ok": True, "rescheduled": True, "attempts": att}
            _con.execute("UPDATE ops_tasks SET attempts=?, status='bajarildi', outcome=?, note=?, done_at=?, done_by=? WHERE id=?",
                         (att, body.outcome, note, _iso(now), c.user["id"], tid))
            st_ = db.one(_con, "SELECT study_form FROM students WHERE id=?", (t["student_id"],)) or {}
            who = route("tyutor", st_)
            sc = {"say": [f"{ROLE_T.get(t['assignee_role'], 'Call-markaz')} {att} marta qo'ng'iroq qildi — javob bo'lmadi.",
                          "Talabani dars paytida toping va masalani yuzma-yuz gaplashing." if (st_.get("study_form") or "kunduzgi") == "kunduzgi" else
                          "Sirtqi talaba: ish joyi yoki shaxsiy ishdagi qo'shimcha aloqa orqali bog'laning; sessiyada yuzma-yuz gaplashing." if st_.get("study_form") == "sirtqi" else
                          "Masofaviy talaba: LMS xabari va elektron pochta orqali bog'laning, onlayn uchrashuv belgilang."],
                  "tone": ["Hurmat bilan, ayblamasdan gaplashing."], "basis": []}
            cur = _con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (t["case_id"], t["student_id"], "suhbat", "Javob bermadi: tyutor topib gaplashsin", who,
                                                                   t["faculty_id"], _iso(now + dt.timedelta(hours=24)), "yangi", t["level"], json.dumps(sc, ensure_ascii=False), _iso(now)))
            _log(_con, t["case_id"], tid, t["student_id"], c, "javob bermadi", f"{att} urinish — tyutorga o'tkazildi")
            _con.commit(); return {"ok": True, "escalated": cur.lastrowid}
        _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome=?, note=?, promise_date=?, done_at=?, done_by=? WHERE id=?",
                     (body.outcome, note, body.promise_date if body.outcome == "vada" else None, _iso(now), c.user["id"], tid))
        _log(_con, t["case_id"], tid, t["student_id"], c, OUT_T[body.outcome].lower(),
             (f"va'da: {body.promise_date}. " if body.outcome == "vada" else "") + note)
        if body.outcome == "notogri_raqam":
            sc = {"say": ["Call-markaz talabaga ulana olmadi: telefon raqami noto'g'ri.", "HEMIS'dagi aloqa ma'lumotini yangilang."], "tone": [], "basis": []}
            who = route("tyutor", db.one(_con, "SELECT study_form FROM students WHERE id=?", (t["student_id"],)) or {})
            _con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (t["case_id"], t["student_id"], "suhbat", "Telefon raqamini aniqlash", who, t["faculty_id"],
                                                             _iso(now + dt.timedelta(hours=24)), "yangi", t["level"], json.dumps(sc, ensure_ascii=False), _iso(now)))
        if t["kind"] == "hujjat":
            facts = json.loads(db.one(_con, "SELECT facts FROM ops_cases WHERE id=?", (t["case_id"],))["facts"] or "{}")
            ids = [i["id"] for i in facts.get("items", [])]
            if ids:
                _con.execute(f"UPDATE absences SET doc_status=? WHERE id IN ({','.join(map(str, ids))}) AND doc_status='kutilmoqda'",
                             ("tasdiqlangan" if body.outcome == "hujjat_keldi" else "yoq",))
        _con.commit()
    st = evaluate(_con)   # holatlar darhol qayta hisoblanadi (masalan, hujjat keldi → davomat soatlari kamayadi)
    return {"ok": True, "engine": st}

class Letter(BaseModel):
    reason: str = Field("", max_length=300)

@router.post("/api/ops/tasks/{tid}/document")
def api_document(tid: int, body: Letter, request: Request):
    """'xat' / 'buyruq' topshirig'i uchun hujjatlar markazida hujjat tayyorlash va topshiriqqa bog'lash."""
    c = C(request); _guard(c, "talabalar markazi: hujjat tayyorlash", f"#{tid}")
    t = db.one(_con, "SELECT t.*, oc.rule FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id WHERE t.id=?", (tid,))
    if not t: raise HTTPException(404)
    if t["kind"] not in ("xat", "buyruq"): raise HTTPException(400, "Bu topshiriq uchun hujjat yo'q")
    if not _can_act(c, t): raise AccessDenied("⛔ Bu topshiriq sizning navbatingizda emas.")
    from . import documents as D, service as SV
    tgt = f"s:{t['student_id']}"
    if t["kind"] == "buyruq" and t["rule"] == "tatil":
        # Buyruqlar Hujjatlar markazida emas — «Buyruqlar» modulida: «ta'tildan qaytish» loyihasi o'sha yerda yaratiladi va topshiriqqa bog'lanadi
        from . import orders as ORD
        lv = db.one(_con, "SELECT end FROM student_leaves WHERE student_id=? ORDER BY start DESC, id DESC LIMIT 1", (t["student_id"],))
        try:
            o = ORD.create_order(c, "tatildan_qaytish", [{"student_id": t["student_id"], "data": {"date_from": (lv or {}).get("end") or _today().isoformat()}}],
                                 source="Talabalar markazi", note=f"Talabalar markazi topshirig'i #{tid}: akademik ta'til muddati tugashi munosabati bilan")
        except HTTPException: raise
        except Exception as e: raise HTTPException(400, f"Buyruq loyihasini yaratib bo'lmadi: {e}")
        ref = f"BUYRUQ#{o['id']}"
        _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='bajarildi', doc_reg=?, done_at=?, done_by=?, note=? WHERE id=?",
                     (ref, _iso(_now()), c.user["id"], f"Buyruqlar bo'limida «Ta'tildan qaytish» loyihasi #{o['id']} (rektor imzosini kutadi)", tid))
        _log(_con, t["case_id"], tid, t["student_id"], c, "buyruq loyihasi yaratildi", f"Buyruqlar · #{o['id']} · ta'tildan qaytish")
        _con.commit()
        return {"ok": True, "reg_no": ref, "order_id": o["id"], "file": None, "status": "loyiha", "title": "Buyruq loyihasi (Buyruqlar bo'limi)"}
    if t["kind"] == "buyruq" and t["rule"] == "davomat":
        # Hayfsan — buyruq: «Buyruqlar» modulida loyiha (rektor imzolaydi); imzolangach hayfsan «amalda» (sync_discipline)
        o = hayfsan_order(c, [t], body.reason)
        _con.commit()
        return {"ok": True, "reg_no": f"BUYRUQ#{o['id']}", "order_id": o["id"], "file": None, "status": "loyiha", "title": "Hayfsan buyrug'i loyihasi (Buyruqlar bo'limi)"}
    if t["rule"] == "kontrakt": key, params = "debt_letter", {"target": tgt}
    elif t["kind"] == "buyruq": key, params = "reprimand", {"target": tgt, "reason": body.reason}
    else: key, params = "warn_letter", {"target": tgt, "basis": "akademik" if t["rule"] == "akademik" else "davomat"}
    try:
        r = D.issue(_con, c, key, params, SV.public_base(request))
    except ValueError as e:
        raise HTTPException(400, str(e))
    reg = r["regs"][0]
    if key == "reprimand":   # hayfsan qayd etiladi: taqdimnoma rektor imzosini kutadi → imzolansa «amalda» (documents.set_status)
        record_reprimand(_con, c, t["student_id"], reg, r["status"], body.reason)
    _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='bajarildi', doc_reg=?, done_at=?, done_by=?, note=? WHERE id=?",
                 (reg, _iso(_now()), c.user["id"], f"{D.CAT[key]['title']} — {reg}" + (" (rektor imzosini kutadi)" if r["status"] == "loyiha" else ""), tid))
    _log(_con, t["case_id"], tid, t["student_id"], c, "hujjat tayyorlandi", f"{D.CAT[key]['title']} · {reg}")
    _con.commit()
    return {"ok": True, "reg_no": reg, "file": r["file"], "status": r["status"], "title": D.CAT[key]["title"]}

# --- intizomiy choralar (hayfsan) ---
DISC_STATUS = {"loyiha": "Taqdimnoma rektorga yuborilgan", "amalda": "E'lon qilingan (rektor imzolagan)", "bekor": "Bekor qilingan"}

def record_reprimand(con, ctx, sid, doc_reg, doc_status, reason=""):
    """Hayfsan yozuvi (discipline). Hujjat (taqdimnoma) imzolanmagan bo'lsa — «loyiha», imzolangach — «amalda».
    «Chetlashtirishga tayyor» bosqichi faqat «amalda» hayfsani bor talabani ko'rsatadi (app/registrar.py)."""
    P, today = policy(con), _today()
    h = con.execute(f"""SELECT COALESCE(SUM(a.hours),0) FROM absences a JOIN students s ON s.id=a.student_id
                        WHERE a.student_id=? AND {_unexcused_sql(P, today)}""", (sid,)).fetchone()[0]
    st = "amalda" if doc_status in ("imzolangan", "amalda") else "loyiha"
    con.execute("""INSERT INTO discipline(student_id,kind,reason,hours,semester,doc_reg,status,created_at,created_by,signed_at,note)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (sid, "hayfsan", (reason or "").strip()[:300] or f"joriy semestrda {h} soat dars sababsiz qoldirilgani",
                                                     h, AR.CURRENT_SEMESTER, doc_reg, st, _iso(_now()), ctx.user["id"] if ctx else None,
                                                     _iso(_now()) if st == "amalda" else None, None))
    _log(con, None, None, sid, ctx, "hayfsan qayd etildi", f"{doc_reg} · {DISC_STATUS[st]} · {h} soat")

def discipline_on_doc(con, doc_reg, action, ctx=None):
    """documents.set_status chaqiradi: taqdimnoma imzolansa — hayfsan amalda, bekor qilinsa — bekor."""
    st = {"sign": "amalda", "cancel": "bekor"}.get(action)
    if not st: return 0
    n = con.execute("UPDATE discipline SET status=?, signed_at=CASE WHEN ?='amalda' THEN ? ELSE signed_at END WHERE doc_reg=? AND status!='bekor'",
                    (st, st, _iso(_now()), doc_reg)).rowcount
    for r in db.rows(con, "SELECT student_id FROM discipline WHERE doc_reg=?", (doc_reg,)):
        _log(con, None, None, r["student_id"], ctx, "hayfsan " + ("e'lon qilindi (rektor imzoladi)" if st == "amalda" else "bekor qilindi"), doc_reg)
    return n

def _unexcused_hours(con, sid):
    P = policy(con)
    return con.execute(f"""SELECT COALESCE(SUM(a.hours),0) FROM absences a JOIN students s ON s.id=a.student_id
                           WHERE a.student_id=? AND {_unexcused_sql(P, _today())}""", (sid,)).fetchone()[0]

def hayfsan_order(c: Ctx, ts: list, reason="") -> dict:
    """Davomat bo'yicha hayfsan topshiriqlari → BITTA «Hayfsan» buyrug'i loyihasi (Buyruqlar moduli, talabalar ro'yxati bilan).
    Har talabaga hayfsan yozuvi (discipline: loyiha, doc_reg=BUYRUQ#id); topshiriqlar bajarildi deb yopiladi va buyruqqa bog'lanadi."""
    from . import orders as ORD
    items = []
    for t in ts:
        h = _unexcused_hours(_con, t["student_id"])
        items.append({"student_id": t["student_id"], "data": {"reason": (reason or "").strip()[:300] or
                      f"joriy semestrda {h} soat mashg'ulotni sababsiz qoldirgani (ichki tartib qoidalarini buzish)"}})
    try:
        o = ORD.create_order(c, "hayfsan", items, source="Talabalar markazi",
                             note=f"Talabalar markazi: davomat — hayfsan bosqichi ({len(items)} ta talaba). Topshiriqlar: " +
                                  ", ".join(f"#{t['id']}" for t in ts[:40]) + (" …" if len(ts) > 40 else ""))
    except HTTPException: raise
    except Exception as e: raise HTTPException(400, f"Buyruq loyihasini yaratib bo'lmadi: {e}")
    ref, now = f"BUYRUQ#{o['id']}", _iso(_now())
    for t, it in zip(ts, items):
        record_reprimand(_con, c, t["student_id"], ref, "loyiha", it["data"]["reason"])
        _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='bajarildi', doc_reg=?, done_at=?, done_by=?, note=? WHERE id=?",
                     (ref, now, c.user["id"], f"Buyruqlar bo'limida «Hayfsan» loyihasi #{o['id']} (rektor imzosini kutadi)", t["id"]))
        _log(_con, t["case_id"], t["id"], t["student_id"], c, "buyruq loyihasi yaratildi", f"Buyruqlar · #{o['id']} · hayfsan")
    return o

def sync_discipline(con) -> int:
    """Buyruqlar modulidagi hayfsan buyrug'i holati → discipline: imzolangan — «amalda», o'chirilgan/bekor qilingan — «bekor»."""
    try:
        rows = db.rows(con, """SELECT d.id, d.student_id, d.status, d.doc_reg, o.status ostatus FROM discipline d
                               JOIN orders o ON 'BUYRUQ#' || o.id = d.doc_reg WHERE d.doc_reg LIKE 'BUYRUQ#%' AND d.status!='bekor'""")
    except Exception:
        return 0
    n = 0
    for r in rows:
        st = "amalda" if r["ostatus"] == "imzolangan" else "bekor" if r["ostatus"] in ("bekor", "bekor_qilingan") else None
        if st and st != r["status"]:
            con.execute("UPDATE discipline SET status=?, signed_at=CASE WHEN ?='amalda' THEN ? ELSE signed_at END WHERE id=?", (st, st, _iso(_now()), r["id"]))
            _log(con, None, None, r["student_id"], None, "hayfsan " + ("e'lon qilindi (rektor buyruqni imzoladi)" if st == "amalda" else "bekor qilindi"), r["doc_reg"])
            n += 1
    if n: con.commit()
    return n

def has_reprimand(con, sid) -> bool:
    return bool(con.execute("SELECT 1 FROM discipline WHERE student_id=? AND kind='hayfsan' AND status='amalda'", (sid,)).fetchone())

@router.post("/api/ops/evaluate")
def api_evaluate(request: Request):
    c = C(request); _guard(c, "talabalar markazi: qoidalarni hozir tekshirish")
    if c.role.key not in FULL_VIEW: raise AccessDenied("⛔ Qoidalarni qo'lda ishga tushirish — Registrator ofisi.")
    return evaluate(_con)

@router.get("/api/ops/policy")
def api_policy(request: Request):
    c = C(request); _guard(c, "talabalar markazi: qoidalar")
    return {"policy": db.rows(_con, "SELECT * FROM ops_policy WHERE key NOT LIKE '\\_%' ESCAPE '\\' ORDER BY rowid"),
            "plan": db.rows(_con, "SELECT * FROM contract_plan ORDER BY due"),
            "matrix": [{"rule": RULES[r], "level": LEVELS[l], "tasks": [f"{KINDS[k]} → {ROLE_T[ro]} ({h} soat)" for k, ro, h in v]} for (r, l), v in PLAN.items()]}

# --- otrabotka ---
@router.get("/api/ops/retakes")
def api_retakes(request: Request):
    c = C(request); _view_guard(c, "talabalar markazi: otrabotkalar")
    if c.role.key in ("call_center", "buxgalteriya"): raise AccessDenied("⛔ Otrabotkalar bu lavozim uchun emas.")
    return retakes_list(c)

class RetakeIn(BaseModel):
    student_id: int
    subject: str = Field(..., max_length=120)
    semester: int | None = None          # bo'sh — avtomatik: shu fan bo'yicha qarz bor semestr, bo'lmasa joriy semestr
    kind: str | None = Field(None, pattern="^(qarz|oraliq|dars)$")
    absence_id: int | None = None        # «dars» — qaysi qoldirilgan mashg'ulot (bo'sh — eng eski yopilmagan sababsiz qoldirish)

def resolve_retake(con, sid, subject, semester=None, kind=None, absence_id=None) -> dict:
    """Otrabotka turi va asosini aniqlaydi: «qarz» — yakunlangan semestrdagi o'zlashtirilmagan fan; «oraliq» — joriy semestrda oraliq < 12
    yoki kiritilmagan; «dars» — joriy semestrda sababsiz qoldirilgan mashg'ulot (baho o'zgarmaydi, qoldirish yopiladi)."""
    cur = AR.CURRENT_SEMESTER
    rows = db.rows(con, "SELECT * FROM grades WHERE student_id=? AND subject=? ORDER BY semester DESC", (sid, subject))
    if semester is not None: rows = [g for g in rows if g["semester"] == semester]
    if not rows: raise HTTPException(400, "Talabada bu fan yo'q" + (" (tanlangan semestrda)" if semester is not None else ""))
    debt = next((g for g in rows if g["semester"] < cur and g["score"] is not None and g["score"] < AR.PASS), None)
    now = next((g for g in rows if g["semester"] == cur), None)
    if kind in (None, "qarz") and debt:
        return {"kind": "qarz", "grade": debt, "semester": debt["semester"], "score_old": debt["score"]}
    if kind == "qarz": raise HTTPException(400, "Bu fan bo'yicha akademik qarz yo'q (o'tgan yoki yopilgan)")
    if not now: raise HTTPException(400, "Bu fan joriy semestrda o'qitilmaydi")
    if kind in (None, "oraliq") and not AR.admitted(now["oraliq"]):
        return {"kind": "oraliq", "grade": now, "semester": cur, "score_old": now["oraliq"]}
    if kind == "oraliq": raise HTTPException(400, f"Oraliq nazorat {AR.ORALIQ_MIN} va undan yuqori — otrabotka kerak emas")
    P, today = policy(con), _today()
    ab = db.rows(con, f"""SELECT a.* FROM absences a JOIN students s ON s.id=a.student_id WHERE a.student_id=? AND {_unexcused_sql(P, today)}
                          {'AND a.id=' + str(int(absence_id)) if absence_id else ''} ORDER BY a.start, a.id LIMIT 1""", (sid,))
    if not ab: raise HTTPException(400, "Bu fan bo'yicha akademik qarz, past oraliq yoki sababsiz qoldirilgan (yopilmagan) dars yo'q")
    return {"kind": "dars", "grade": now, "semester": cur, "score_old": None, "absence": ab[0]}

@router.post("/api/ops/retakes")
def api_retake_new(body: RetakeIn, request: Request):
    c = C(request); _guard(c, "otrabotka varaqasi berish", f"#{body.student_id} {body.subject}")
    if c.role.key not in RETAKE_ISSUERS: raise AccessDenied(RETAKE_DENY)
    _student_row(c, body.student_id)
    x = resolve_retake(_con, body.student_id, body.subject, body.semester, body.kind, body.absence_id)
    g = x["grade"]
    busy = "SELECT 1 x FROM retakes WHERE student_id=? AND subject=? AND COALESCE(semester, ?)=? AND status IN ('berildi','topshirildi')"
    if db.one(_con, busy + (" AND kind='dars' AND absence_id=?" if x["kind"] == "dars" else " AND COALESCE(kind,'qarz')!='dars'"),
              (body.student_id, g["subject"], AR.CURRENT_SEMESTER, x["semester"]) + ((x["absence"]["id"],) if x["kind"] == "dars" else ())):
        raise HTTPException(409, "Bu fan bo'yicha ochiq otrabotka bor")
    tid = g["teacher_id"]
    if x["semester"] == AR.CURRENT_SEMESTER:   # joriy semestr — fanni hozir o'qitayotgan o'qituvchi
        tg = db.one(_con, "SELECT tg.teacher_id FROM teacher_groups tg JOIN students s ON s.group_id=tg.group_id WHERE s.id=? AND tg.subject=?",
                    (body.student_id, g["subject"]))
        tid = (tg or {}).get("teacher_id") or tid
    now = _now(); due = now + dt.timedelta(days=int(policy(_con)["retake_days"]))
    ab = x.get("absence") or {}
    reason = RETAKE_REASON[x["kind"]] + (f" ({AR.SEMESTER_SHORT.get(x['semester'])})" if x["kind"] == "qarz" else
                                         f" ({_dmy(ab.get('start'))}, {ab.get('hours')} soat)" if x["kind"] == "dars" else "")
    cur = _con.execute("""INSERT INTO retakes(student_id,subject,teacher_id,reason,status,issued_at,due_at,score_old,created_by,semester,kind,absence_id,hours)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (body.student_id, g["subject"], tid, reason, "berildi", _iso(now), _iso(due),
                                                               x["score_old"], c.user["id"], x["semester"], x["kind"], ab.get("id"), ab.get("hours")))
    from . import service as SV
    r = _issue_sheet(_con, c, cur.lastrowid, SV.public_base(request))
    _log(_con, None, None, body.student_id, c, "otrabotka varaqasi berildi",
         f"{g['subject']} · {RETAKE_KINDS[x['kind']]} · {r['regs'][0]} · muddat {due:%Y-%m-%d %H:%M}")
    _con.commit()
    return {"ok": True, "id": cur.lastrowid, "reg_no": r["regs"][0], "file": r["file"], "due_at": _iso(due), "kind": x["kind"], "semester": x["semester"]}

class Upload(BaseModel):
    data_url: str = Field(..., max_length=14_000_000)

@router.post("/api/ops/retakes/{rid}/upload")
def api_retake_upload(rid: int, body: Upload, request: Request):
    c = C(request); _guard(c, "otrabotka: skan yuklash", f"#{rid}")
    if c.role.key not in RETAKE_ISSUERS: raise AccessDenied("⛔ Skanni Registrator ofisi, tyutor yoki (sirtqi talabalarniki) Sirtqi bo'lim yuklaydi.")
    r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
    if not r: raise HTTPException(404)
    _student_row(c, r["student_id"])
    raw, ext = decode_upload(body.data_url)
    return store_scan(c, r, raw, ext)

def decode_upload(data_url: str):
    m = re.match(r"^data:(application/pdf|image/jpeg|image/png);base64,(.+)$", data_url, re.S)
    if not m: raise HTTPException(400, "Faqat PDF, JPG yoki PNG")
    try: raw = base64.b64decode(m.group(2), validate=True)
    except binascii.Error: raise HTTPException(400, "Fayl buzilgan")
    if len(raw) > 10_000_000: raise HTTPException(413, "Fayl 10 MB dan katta")
    ext = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[m.group(1)]
    magic = {".pdf": b"%PDF", ".jpg": b"\xff\xd8", ".png": b"\x89PNG"}[ext]
    if not raw.startswith(magic): raise HTTPException(400, "Fayl turi mazmuniga mos emas")
    return raw, ext

def store_scan(c: Ctx, r, raw: bytes, ext: str, con=None):
    """Skanni saqlaydi va o'qiydi (registrar_scan): ro'yxat raqami, imzo, ball. Natija retakes.scan_meta da."""
    con = con or _con
    if r["status"] not in ("berildi", "qaytarildi"): raise HTTPException(409, "Bu holatda yuklab bo'lmaydi")
    from . import registrar_scan as RS
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = f"{r['id']}-{secrets.token_hex(6)}{ext}"
    (UPLOADS / name).write_bytes(raw)
    try:
        meta = RS.read_scan(raw, ext)
    except Exception as e:   # o'qish muvaffaqiyatsiz bo'lsa ham skan qabul qilinadi — registrator ko'z bilan tekshiradi
        meta = {"method": "qo'lda", "reg_no": None, "signed": None, "score": None, "warnings": [f"Skanni o'qib bo'lmadi: {type(e).__name__}"]}
    meta["match"] = (meta["reg_no"] == r["reg_no"]) if meta.get("reg_no") and r["reg_no"] else None
    if meta["match"] is False: meta["warnings"].insert(0, f"Varaqadagi raqam {meta['reg_no']} — bu otrabotka {r['reg_no']} emas")
    con.execute("UPDATE retakes SET status='topshirildi', file=?, submitted_at=?, scan_meta=? WHERE id=?",
                (name, _iso(_now()), json.dumps(meta, ensure_ascii=False), r["id"]))
    flags = "; ".join(meta.get("warnings") or []) or "imzo va ball aniqlandi"
    _log(con, None, None, r["student_id"], c, "otrabotka varaqasi yuklandi",
         f"{r['subject']} · {len(raw) // 1024} KB · o'qildi: {meta['method']}" + (f", ball {meta['score']}" if meta.get("score") is not None else "") + f" · {flags}")
    con.commit()
    evaluate(con)
    return {"ok": True, "scan": meta}

@router.get("/api/ops/retakes/{rid}/file")
def api_retake_file(rid: int, request: Request):
    c = C(request); _view_guard(c, "otrabotka: skanni ko'rish")
    r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
    if not r or not r["file"]: raise HTTPException(404)
    _student_row(c, r["student_id"])
    f = (UPLOADS / r["file"]).resolve()
    if f.parent != UPLOADS.resolve() or not f.exists(): raise HTTPException(404)
    return FileResponse(f, media_type={"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}[f.suffix[1:]],
                        headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})

class Approve(BaseModel):
    score: int | None = Field(None, ge=0, le=100)   # «qarz» — 100 ballik yakuniy ball; «oraliq» — 0..30; «dars» — kerak emas
    note: str = Field("", max_length=500)
    force: bool = False          # skanda imzo aniqlanmagan, lekin registrator ko'z bilan tekshirdi (izoh majburiy)

def _approver(c: Ctx, r):
    if c.role.key not in RETAKE_APPROVERS: raise AccessDenied("⛔ Bahoni Registrator ofisi (sirtqi talabalarniki — Sirtqi bo'lim) tasdiqlaydi.")
    _student_row(c, r["student_id"])   # sirtqi — faqat sirtqi talaba

def _components(value, oraliq):
    """Qayta topshirish natijasi (jami) → (oraliq, yakuniy): jami har doim oraliq + yakuniy. Asl oraliq yakuniyga kirish uchun yetarli bo'lsa
    saqlanadi; aks holda (talaba oraliqni ham qayta topshirgan) — institut shkalasiga mos taqsimlanadi."""
    if oraliq is not None and AR.admitted(oraliq) and 0 <= value - oraliq <= AR.YAKUNIY_MAX: return oraliq, value - oraliq
    o = max(AR.ORALIQ_MIN, min(AR.ORALIQ_MAX, round(value * 0.3))) if value >= AR.PASS else min(AR.ORALIQ_MAX, value)
    o = min(o, value)
    return o, value - o

def apply_attempt(con, r, value, ctx) -> dict:
    """Otrabotka natijasini baholar tarixiga yozadi (grade_attempts). Asl urinish birinchi marta tarixga ko'chiriladi.
    Hisobga olinadigan natija — eng yuqorisi: o'tgan (yoki avvalgi) bahodan past natija bahoni PASAYTIRMAYDI (urinish tarixda qoladi).
    «qarz» — o'sha semestr yozuvi (ball) yangilanadi; «oraliq» — joriy semestr oraliq bali."""
    sem = r["semester"] if r.get("semester") is not None else AR.CURRENT_SEMESTER
    g = db.one(con, "SELECT * FROM grades WHERE student_id=? AND subject=? AND semester=?", (r["student_id"], r["subject"], sem))
    if not g: raise HTTPException(409, "Baho yozuvi topilmadi")
    field = "oraliq" if r["kind"] == "oraliq" else "score"
    old = g[field]
    if not con.execute("SELECT 1 FROM grade_attempts WHERE student_id=? AND subject=? AND semester=?", (g["student_id"], g["subject"], sem)).fetchone():
        con.execute("""INSERT INTO grade_attempts(student_id,subject,semester,attempt,kind,oraliq,yakuniy,score,at,counted,note)
                       VALUES(?,?,?,?,?,?,?,?,?,1,?)""", (g["student_id"], g["subject"], sem, 1, "asosiy", g["oraliq"], g["yakuniy"], g["score"],
                                                          AR.term_dates(sem)[1] if sem < AR.CURRENT_SEMESTER else None, "asl urinish"))
    n = con.execute("SELECT COALESCE(MAX(attempt),0) + 1 FROM grade_attempts WHERE student_id=? AND subject=? AND semester=?",
                    (g["student_id"], g["subject"], sem)).fetchone()[0]
    counts = old is None or value > old
    if counts: con.execute("UPDATE grade_attempts SET counted=0 WHERE student_id=? AND subject=? AND semester=?", (g["student_id"], g["subject"], sem))
    o_new, y = _components(value, g["oraliq"]) if field == "score" else (value, None)
    con.execute("""INSERT INTO grade_attempts(student_id,subject,semester,attempt,kind,oraliq,yakuniy,score,at,counted,retake_id,by_user,note)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (g["student_id"], g["subject"], sem, n, "otrabotka" + (" (oraliq)" if field == "oraliq" else ""),
                                                          o_new, y if field == "score" else None,
                                                          value if field == "score" else None, _iso(_now()), int(counts), r["id"], ctx.user["id"],
                                                          f"varaqa {r['reg_no'] or '—'}"))
    if counts:
        if field == "score": con.execute("UPDATE grades SET score=?, oraliq=?, yakuniy=?, attempts=? WHERE student_id=? AND subject=? AND semester=?",
                                         (value, o_new, y, n, g["student_id"], g["subject"], sem))
        else: con.execute("UPDATE grades SET oraliq=?, attempts=? WHERE student_id=? AND subject=? AND semester=?", (value, n, g["student_id"], g["subject"], sem))
        AR.refresh_student_metrics(con, [g["student_id"]])
    else:
        con.execute("UPDATE grades SET attempts=? WHERE student_id=? AND subject=? AND semester=?", (n, g["student_id"], g["subject"], sem))
    return {"field": field, "old": old, "new": value, "counted": counts, "attempt": n, "semester": sem}

@router.post("/api/ops/retakes/{rid}/approve")
def api_retake_approve(rid: int, body: Approve, request: Request):
    c = C(request); _guard(c, "otrabotka: bahoni tasdiqlash", f"#{rid} → {body.score}")
    if c.role.key not in RETAKE_APPROVERS: raise AccessDenied("⛔ Bahoni Registrator ofisi (sirtqi talabalarniki — Sirtqi bo'lim) tasdiqlaydi.")
    with _lock:
        r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
        if not r: raise HTTPException(404)
        _approver(c, r)
        r["kind"] = r.get("kind") or "qarz"
        if r["status"] != "topshirildi" or not r["file"]: raise HTTPException(409, "Avval imzolangan varaqa skanini yuklang")
        sm = json.loads(r.get("scan_meta") or "{}")
        if sm.get("match") is False and not body.force: raise HTTPException(409, f"Skandagi ro'yxat raqami ({sm.get('reg_no')}) bu otrabotkaga mos emas")
        if sm.get("signed") is False and not body.force:
            raise HTTPException(409, "Skanda o'qituvchi imzosi aniqlanmadi. Varaqani qaytaring yoki imzoni ko'z bilan tekshirib, izoh bilan tasdiqlang")
        if body.force and len(body.note.strip()) < 3: raise HTTPException(400, "Qo'lda tasdiqlash sababini yozing")
        if r["kind"] != "dars" and body.score is None: raise HTTPException(400, "Varaqadagi ballni kiriting")
        if r["kind"] == "oraliq" and body.score > AR.ORALIQ_MAX: raise HTTPException(400, f"Oraliq nazorat bali {AR.ORALIQ_MAX} dan oshmaydi")
        cur = _con.execute("UPDATE retakes SET status='tasdiqlandi', score_new=?, approved_at=?, approved_by=?, note=? WHERE id=? AND status='topshirildi'",
                           (body.score if r["kind"] != "dars" else None, _iso(_now()), c.user["id"], body.note.strip(), rid))
        if cur.rowcount != 1: raise HTTPException(409, "Allaqachon tasdiqlangan")
        if r["kind"] == "dars":   # baho o'zgarmaydi — qoldirilgan dars otrabotka bilan yopiladi (sababsiz soatlardan chiqadi)
            n = _con.execute("UPDATE absences SET cleared_by=? WHERE id=? AND cleared_by IS NULL", (rid, r["absence_id"])).rowcount
            res = {"field": "dars", "cleared": n, "hours": r.get("hours")}
            detail = f"{r['subject']}: qoldirilgan dars ({r.get('hours') or '—'} soat) otrabotka bilan yopildi — baho o'zgarmadi"
        else:
            res = apply_attempt(_con, r, body.score, c)
            lbl = "oraliq" if res["field"] == "oraliq" else AR.SEMESTER_SHORT.get(res["semester"], "")
            detail = (f"{r['subject']} ({lbl}): {res['old']} → {body.score}" + ("" if res["counted"] else
                      f" — hisobga olinmadi (avvalgi natija {res['old']} yuqori, baho pasaytirilmaydi)") + f" (varaqa {r['reg_no']}, {res['attempt']}-urinish)")
        _log(_con, None, None, r["student_id"], c, "otrabotka natijasi tasdiqlandi", detail
             + (f" · skandan o'qilgan ball: {sm['score']}" if sm.get("score") is not None else "")
             + (f" · qo'lda tasdiqlandi: {body.note.strip()}" if body.force else ""))
        _con.commit()
    rbac.audit(_con, c, "baho o'zgartirildi (otrabotka)" if r["kind"] != "dars" else "dars qoldirish yopildi (otrabotka)", OPS, True,
               f"talaba #{r['student_id']} {r['subject']}: {detail}")
    return {"ok": True, "result": res, "engine": evaluate(_con)}

class Return(BaseModel):
    note: str = Field(..., min_length=3, max_length=500)

@router.post("/api/ops/retakes/{rid}/return")
def api_retake_return(rid: int, body: Return, request: Request):
    c = C(request); _guard(c, "otrabotka: qaytarish", f"#{rid}")
    if c.role.key not in RETAKE_APPROVERS: raise AccessDenied("⛔ Qaytarishni Registrator ofisi (sirtqi talabalarniki — Sirtqi bo'lim) qiladi.")
    r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
    if not r or r["status"] != "topshirildi": raise HTTPException(409, "Faqat topshirilgan varaqa qaytariladi")
    _approver(c, r)
    due = _now() + dt.timedelta(days=int(policy(_con)["retake_days"]))
    _con.execute("UPDATE retakes SET status='berildi', note=?, due_at=? WHERE id=?", (body.note.strip(), _iso(due), rid))
    _log(_con, None, None, r["student_id"], c, "otrabotka varaqasi qaytarildi", body.note.strip())
    _con.commit(); evaluate(_con)
    return {"ok": True}

# =============================================================================================
# Call-markaz navbatini boshqarish: imkoniyat (operatorlar), ommaviy SMS/Telegram eslatma, kechikadiganlarni o'tkazish
# =============================================================================================
def _sup(c: Ctx, what):
    if c.role.key != SUPERVISOR: raise AccessDenied(f"⛔ {what} — Registrator ofisi boshlig'i. So'rov audit jurnaliga yozildi.")

def call_plan(con, days=10) -> list[dict]:
    """Keyingi ish kunlari bo'yicha reja: kunda nechta qo'ng'iroq va shundan nechtasi muddatidan keyin."""
    return db.rows(con, f"""SELECT t.planned_on day, COUNT(*) n, SUM({_proj_sql(_today().isoformat(), _iso(_now()))}) late FROM ops_tasks t
                           WHERE t.status='yangi' AND t.assignee_role='call_center' AND t.planned_on IS NOT NULL
                           GROUP BY t.planned_on ORDER BY t.planned_on LIMIT ?""", (days,))

@router.get("/api/ops/calls/plan")
def api_call_plan(request: Request):
    c = C(request); _view_guard(c, "talabalar markazi: call-markaz rejasi")
    if c.role.key not in FULL_VIEW + ("call_center",): raise AccessDenied("⛔ Call-markaz rejasi — Registrator ofisi va call-markaz uchun.")
    return {"summary": calls_summary(_con), "operators": operators(_con), "plan": call_plan(_con), "can_plan": c.role.key == SUPERVISOR,
            "categories": CALL_CAT, "default_capacity": int(policy(_con).get("call_daily_capacity", 60))}

class OperatorIn(BaseModel):
    user_id: int
    capacity: int = Field(..., ge=0, le=300)
    active: bool = True

class OperatorsIn(BaseModel):
    items: list[OperatorIn] = Field(..., min_length=1, max_length=50)

@router.post("/api/ops/calls/operators")
def api_call_operators(body: OperatorsIn, request: Request):
    c = C(request); _guard(c, "call-markaz: operator me'yori", ", ".join(f"#{x.user_id}={x.capacity}" for x in body.items))
    _sup(c, "Operatorlar me'yorini o'zgartirish")
    ok_ids = {r[0] for r in _con.execute("SELECT id FROM users WHERE role='call_center'")}
    with _lock:
        for x in body.items:
            if x.user_id not in ok_ids: raise HTTPException(400, f"#{x.user_id} — call-markaz operatori emas")
            _con.execute("""INSERT INTO call_operators(user_id,capacity,active,updated_at,updated_by) VALUES(?,?,?,?,?)
                            ON CONFLICT(user_id) DO UPDATE SET capacity=excluded.capacity, active=excluded.active, updated_at=excluded.updated_at,
                            updated_by=excluded.updated_by""", (x.user_id, x.capacity, int(x.active), _iso(_now()), c.user["id"]))
        schedule_calls(_con); _con.commit()
    rbac.audit(_con, c, "call-markaz: operator me'yori o'zgartirildi", OPS, True, ", ".join(f"#{x.user_id}: {x.capacity}{'' if x.active else ' (nofaol)'}" for x in body.items))
    return {"ok": True, "operators": operators(_con), "summary": calls_summary(_con)}

def _sms_text(r, facts) -> str:
    name = r["full_name"].split()[1] if len(r["full_name"].split()) > 1 else r["full_name"]
    return (f"Hurmatli {name}! ISFT: kontrakt {facts.get('installment', 'navbatdagi to‘lov').lower()} muddati {_dmy(facts.get('due'))}. "
            f"Jadval bo'yicha {_money(facts.get('need_now') or 0)} to'lanishi kerak. Savollar: buxgalteriya, {AR.REGISTRAR_ROOMS[0]}.").replace("‘", "'")

class NotifyIn(BaseModel):
    channel: str = Field("sms", pattern="^(sms|telegram)$")
    preview: bool = True

@router.post("/api/ops/calls/notify")
def api_call_notify(body: NotifyIn, request: Request):
    """Past jiddiylikdagi kontrakt eslatmalari (to'lov sanasi hali o'tmagan) — qo'ng'iroq o'rniga ommaviy SMS/Telegram xabari.
    Holat ochiq qoladi: to'lov sanasigacha to'lanmasa, holat «jiddiy» bo'ladi va qo'ng'iroq qaytadan navbatga tushadi."""
    c = C(request); _guard(c, "call-markaz: ommaviy eslatma", body.channel)
    _sup(c, "Ommaviy SMS/Telegram eslatma")
    rows = db.rows(_con, f"""SELECT t.id, t.case_id, t.student_id, s.full_name, s.phone, s.telegram_id, oc.facts FROM ops_tasks t
                             JOIN ops_cases oc ON oc.id=t.case_id JOIN students s ON s.id=t.student_id
                             WHERE t.status='yangi' AND t.assignee_role='call_center' AND {CALL_CAT_SQL}='kontrakt_eslatma' ORDER BY t.due_at, t.id""") \
        if "telegram_id" in {r[1] for r in _con.execute("PRAGMA table_info(students)")} else \
        db.rows(_con, f"""SELECT t.id, t.case_id, t.student_id, s.full_name, s.phone, NULL telegram_id, oc.facts FROM ops_tasks t
                          JOIN ops_cases oc ON oc.id=t.case_id JOIN students s ON s.id=t.student_id
                          WHERE t.status='yangi' AND t.assignee_role='call_center' AND {CALL_CAT_SQL}='kontrakt_eslatma' ORDER BY t.due_at, t.id""")
    ch = "SMS" if body.channel == "sms" else "Telegram"
    no_phone = sum(1 for r in rows if not r["phone"])
    gw = f"{ch} shlyuzi ulanmagan (demo): xabarlar chiqish navbatiga yoziladi va ulanganda yuboriladi."
    if body.preview:
        return {"n": len(rows), "channel": ch, "no_phone": no_phone, "gateway": gw,
                "sample": _sms_text(rows[0], json.loads(rows[0]["facts"] or "{}")) if rows else None,
                "effect": "Qo'ng'iroq topshiriqlari «SMS/Telegram eslatma» natijasi bilan yopiladi; to'lov sanasigacha to'lanmasa — qo'ng'iroq qaytadan navbatga tushadi."}
    now, n = _iso(_now()), 0
    with _lock:
        for r in rows:
            if not r["phone"] and body.channel == "sms": continue
            facts = json.loads(r["facts"] or "{}")
            _con.execute("INSERT INTO ops_notices(ts,channel,task_id,case_id,student_id,phone,text,status,user_id) VALUES(?,?,?,?,?,?,?,?,?)",
                         (now, body.channel, r["id"], r["case_id"], r["student_id"], r["phone"], _sms_text(r, facts), "navbatda", c.user["id"]))
            _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='sms', note=?, done_at=?, done_by=? WHERE id=? AND status='yangi'",
                         (f"Qo'ng'iroq o'rniga ommaviy {ch} eslatma (past jiddiylik)", now, c.user["id"], r["id"]))
            _log(_con, r["case_id"], r["id"], r["student_id"], c, f"{ch} eslatma", f"{facts.get('installment', '')} · {_dmy(facts.get('due'))}")
            n += 1
        schedule_calls(_con); _con.commit()
    rbac.audit(_con, c, f"call-markaz: ommaviy {ch} eslatma", OPS, True, f"{n} ta talaba")
    return {"ok": True, "sent": n, "skipped": len(rows) - n, "channel": ch, "gateway": gw, "summary": calls_summary(_con)}

class RedistIn(BaseModel):
    target: str = Field(..., pattern="^(tyutor|registrator_xodim)$")
    preview: bool = True
    days: int = Field(1, ge=1, le=10)        # necha kunlik ulush (tyutor / xodim kunlik me'yori × kun)

def _overflow(con):
    """Rejaga ko'ra muddatidan keyin qilinadigan qo'ng'iroqlar (kontrakt eslatmasidan tashqari — unga SMS taklif qilinadi), muddat tartibida."""
    return db.rows(con, f"""SELECT t.id, t.case_id, t.student_id, t.kind, t.level, t.due_at, oc.rule, oc.facts, s.full_name, s.study_form, s.level slevel,
                            s.group_id, tg.user_id tutor FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id JOIN students s ON s.id=t.student_id
                            LEFT JOIN tutor_groups tg ON tg.group_id=s.group_id
                            WHERE t.status='yangi' AND t.assignee_role='call_center' AND {_proj_sql(_today().isoformat(), _iso(_now()))}
                            AND {CALL_CAT_SQL}!='kontrakt_eslatma' ORDER BY t.due_at, t.level DESC, t.id""")

def _redist_pick(con, target, days):
    P = policy(con)
    rows, out, per = _overflow(con), [], {}
    if target == "tyutor":
        lim = int(P.get("tutor_call_capacity", 10)) * days
        for r in rows:
            form = r["study_form"] or "kunduzgi"
            if form == "kunduzgi" and r["tutor"]: key, role = r["tutor"], "tyutor"
            elif form == "sirtqi": key, role = "sirtqi", "sirtqi"
            else: continue      # masofaviy / tyutori yo'q — Registrator xodimiga o'tkaziladi (ikkinchi tugma)
            cap = lim if role == "tyutor" else lim * 3
            if per.get(key, 0) >= cap: continue
            per[key] = per.get(key, 0) + 1; out.append((r, role))
    else:
        nx = max(1, con.execute("SELECT COUNT(*) FROM users WHERE role=?", (REG_STAFF,)).fetchone()[0])
        out = [(r, REG_STAFF) for r in rows[:int(P.get("staff_call_capacity", 40)) * nx * days]]
    return rows, out

@router.post("/api/ops/calls/redistribute")
def api_call_redistribute(body: RedistIn, request: Request):
    """Navbat to'lganda: muddatidan keyin qilinadigan qo'ng'iroqlarni bir bosishda tyutorlarga (kunduzgi — guruh tyutori, sirtqi — Sirtqi
    bo'lim) yoki Registrator ofisi xodimiga o'tkazish. Har biriga kunlik me'yordan ortiq berilmaydi. Muddat (SLA) o'zgarmaydi."""
    c = C(request); _guard(c, "call-markaz: navbatni taqsimlash", body.target)
    _sup(c, "Navbatni boshqa xodimlarga taqsimlash")
    with _lock:
        rows, pick = _redist_pick(_con, body.target, body.days)
        by = {}
        for _, role in pick: by[role] = by.get(role, 0) + 1
        if body.preview:
            return {"overflow": len(rows), "n": len(pick), "by_role": [{"role": k, "label": ROLE_T[k], "n": v} for k, v in by.items()],
                    "left": len(rows) - len(pick), "target": body.target, "days": body.days}
        P, now = policy(_con), _iso(_now())
        for r, role in pick:
            s = {"full_name": r["full_name"], "study_form": r["study_form"], "level": r["slevel"]}
            sc = script(r["rule"], "qongiroq", json.loads(r["facts"] or "{}"), s, P, role)
            sc["say"].append("Bu qo'ng'iroq call-markazdan o'tkazildi (navbat to'lgan) — natijani shu yerda belgilang.")
            _con.execute("""UPDATE ops_tasks SET assignee_role=?, assignee_user=NULL, planned_on=NULL, script=?, note=? WHERE id=? AND status='yangi'""",
                         (role, json.dumps(sc, ensure_ascii=False), f"Call-markazdan o'tkazildi: navbat to'lgan ({_dmy(now[:10])})", r["id"]))
            _log(_con, r["case_id"], r["id"], r["student_id"], c, "qo'ng'iroq o'tkazildi", f"Call-markaz → {ROLE_T[role]} (navbat to'lgan; muddat {r['due_at'][:16].replace('T', ' ')})")
        schedule_calls(_con); _con.commit()
    rbac.audit(_con, c, "call-markaz: navbat taqsimlandi", OPS, True, ", ".join(f"{ROLE_T[k]}: {v}" for k, v in by.items()))
    return {"ok": True, "moved": len(pick), "by_role": [{"role": k, "label": ROLE_T[k], "n": v} for k, v in by.items()], "summary": calls_summary(_con)}

# =============================================================================================
# Ommaviy amallar: tanlanganlarni bajarildi deb belgilash; xatlar paketi (DOCX/ZIP, hujjatlar reyestrida); buyruq loyihalari (Buyruqlar)
# =============================================================================================
BULK_OUT = {"qongiroq": "gaplashildi", "suhbat": "bajarildi", "xat": "bajarildi", "buyruq": "bajarildi"}   # hujjat — alohida (keldi/yo'q)

class BulkOutcome(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=500)
    note: str = Field(..., min_length=3, max_length=1000)

@router.post("/api/ops/tasks/bulk-outcome")
def api_bulk_outcome(body: BulkOutcome, request: Request):
    c = C(request); _guard(c, "talabalar markazi: tanlanganlarni bajarildi deb belgilash", f"{len(body.ids)} ta")
    note, now, done, skipped = body.note.strip(), _iso(_now()), 0, []
    if len(note) < 3: raise HTTPException(400, "Natija izohini yozing (kamida 3 belgi)")
    with _lock:
        ts = {t["id"]: t for t in db.rows(_con, f"SELECT * FROM ops_tasks WHERE id IN ({','.join(str(int(i)) for i in set(body.ids))})")}
        for i in body.ids:
            t = ts.get(i)
            if not t: skipped.append({"id": i, "why": "topilmadi"}); continue
            if t["status"] != "yangi": skipped.append({"id": i, "why": "allaqachon yopilgan"}); continue
            if not _can_act(c, t): skipped.append({"id": i, "why": "navbatingizda emas"}); continue
            out = BULK_OUT.get(t["kind"])
            if not out: skipped.append({"id": i, "why": "hujjat topshirig'i alohida belgilanadi (keldi / yo'q)"}); continue
            _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome=?, note=?, done_at=?, done_by=? WHERE id=? AND status='yangi'",
                         (out, note, now, c.user["id"], i))
            _log(_con, t["case_id"], i, t["student_id"], c, OUT_T[out].lower() + " (ommaviy)", note)
            done += 1
        _con.commit()
    rbac.audit(_con, c, "talabalar markazi: ommaviy natija", OPS, True, f"{done} ta bajarildi, {len(skipped)} ta o'tkazib yuborildi · {note[:80]}")
    return {"ok": True, "done": done, "skipped": skipped, "engine": evaluate(_con) if done else None}

class BulkIn(BaseModel):
    kind: str = Field(..., pattern="^(xat|buyruq)$")
    rule: str = ""
    grp: str = ""
    course: int = 0
    faculty: int = 0
    ids: list[int] | None = Field(None, max_length=5000)

def _bulk_tasks(c: Ctx, b: BulkIn):
    extra, a = _filters(c, b.rule, b.kind, b.grp, b.course, b.faculty, "")
    if b.ids: extra += f" AND t.id IN ({','.join(str(int(i)) for i in b.ids)})"
    rows = db.rows(_con, f"""SELECT t.*, s.full_name, s.study_form, s.level slevel, g.name grp, g.course, oc.rule, oc.facts {TASK_FROM}
                             WHERE {_task_scope_sql(c)} AND t.status='yangi'{extra} ORDER BY oc.rule, g.name, s.full_name LIMIT 5000""", a)
    act = [r for r in rows if _can_act(c, r)]
    return act, len(rows) - len(act)

def _tpl(t):
    if t["kind"] == "buyruq": return {"davomat": "hayfsan", "tatil": "tatildan_qaytish"}.get(t["rule"])
    return "debt_letter" if t["rule"] == "kontrakt" else "warn_letter"

def _bulk_titles():
    from . import documents as D, orders as ORD
    return {"debt_letter": D.CAT["debt_letter"]["title"], "warn_letter": D.CAT["warn_letter"]["title"],
            "hayfsan": ORD.KINDS["hayfsan"]["title"], "tatildan_qaytish": ORD.KINDS["tatildan_qaytish"]["title"]}

@router.post("/api/ops/bulk/preview")
def api_bulk_preview(body: BulkIn, request: Request):
    c = C(request); _view_guard(c, "talabalar markazi: ommaviy hujjat (ko'rib chiqish)")
    ts, cant = _bulk_tasks(c, body)
    T, by = _bulk_titles(), {}
    for t in ts:
        k = _tpl(t)
        if k: by.setdefault(k, []).append(t)
    first = ts[0] if ts else None
    sample = None
    if first:
        f = json.loads(first["facts"] or "{}")
        sample = {"student": first["full_name"], "grp": first["grp"], "title": first["title"],
                  "facts": (f"{f.get('hours')} soat sababsiz" if first["rule"] == "davomat" else
                            f"{f.get('installment', '')}: {_money(f.get('need_now') or 0)} yetishmaydi" if first["rule"] == "kontrakt" else
                            f"{len(f.get('fails') or [])} ta akademik qarz, {len(f.get('oraliq_low') or [])} fandan oraliq < {AR.ORALIQ_MIN}" if first["rule"] == "akademik" else
                            f"ta'til tugashi {_dmy(f.get('end'))}" if first["rule"] == "tatil" else "")}
    out = [{"key": k, "title": T.get(k, k), "n": len(v), "how": ("1 ta buyruq loyihasi (talabalar ro'yxati bilan) — Buyruqlar bo'limida"
                                                                  if body.kind == "buyruq" else f"1 ta DOCX paket ({len(v)} sahifa), har bir xat hujjatlar reyestrida o'z raqami bilan")}
           for k, v in by.items()]
    return {"kind": body.kind, "n": sum(len(v) for v in by.values()), "cant": cant, "packets": out, "sample": sample,
            "students": [{"name": t["full_name"], "grp": t["grp"], "title": t["title"]} for t in ts[:12]],
            "zip": body.kind == "xat" and len(by) > 1}

@router.post("/api/ops/bulk/run")
def api_bulk_run(body: BulkIn, request: Request):
    """Ommaviy tayyorlash. Xatlar — shablon bo'yicha bitta birlashtirilgan DOCX (har sahifa reyestrda o'z raqami va QR bilan), bir nechta
    shablon bo'lsa — qo'shimcha ZIP. Buyruq loyihalari — Buyruqlar modulida, har tur bo'yicha BITTA buyruq (talabalar ro'yxati bilan)."""
    c = C(request); _guard(c, f"talabalar markazi: ommaviy {'xatlar' if body.kind == 'xat' else 'buyruq loyihalari'}")
    from . import documents as D, service as SV
    ts, cant = _bulk_tasks(c, body)
    if not ts: raise HTTPException(400, "Tanlangan filtr bo'yicha bajarishingiz mumkin bo'lgan topshiriq yo'q")
    T, by = _bulk_titles(), {}
    for t in ts:
        k = _tpl(t)
        if k: by.setdefault(k, []).append(t)
    files, orders_, skipped, now = [], [], [], _iso(_now())
    with _lock:
        if body.kind == "xat":
            base = SV.public_base(request)
            for key, lst in by.items():
                I = D.Issuer(_con, c, D.CAT[key], base)
                if c.role.key not in D.CAT[key]["roles"]: skipped += [{"id": t["id"], "why": "shablon lavozimingiz uchun emas"} for t in lst]; continue
                got = []
                for t in lst:
                    n0 = len(I.items)
                    p = {"target": f"s:{t['student_id']}"}
                    if key == "warn_letter": p["basis"] = "akademik" if t["rule"] == "akademik" else "davomat"
                    try: D.GEN[key](I, p)
                    except (ValueError, AccessDenied) as e: skipped.append({"id": t["id"], "why": str(e)[:120]}); continue
                    if len(I.items) > n0: got.append((t, I.items[-1]["reg_no"]))
                if not got: continue
                r = I.save({"bulk": len(got), "template": key, "source": "Talabalar markazi"})
                for t, reg in got:
                    _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='bajarildi', doc_reg=?, done_at=?, done_by=?, note=? WHERE id=? AND status='yangi'",
                                 (reg, now, c.user["id"], f"{T[key]} — {reg} (ommaviy paket {r['file']})", t["id"]))
                    _log(_con, t["case_id"], t["id"], t["student_id"], c, "hujjat tayyorlandi (ommaviy)", f"{T[key]} · {reg} · {r['file']}")
                files.append({"file": r["file"], "title": T[key], "n": len(got), "first": got[0][1], "last": got[-1][1]})
        else:
            if c.role.key != SUPERVISOR: raise AccessDenied("⛔ Buyruq loyihalari — Registrator ofisi boshlig'ida.")
            from . import orders as ORD
            for key, lst in by.items():
                if key == "hayfsan": o = hayfsan_order(c, lst)
                else:
                    items = []
                    for t in lst:
                        lv = db.one(_con, "SELECT end FROM student_leaves WHERE student_id=? ORDER BY start DESC, id DESC LIMIT 1", (t["student_id"],))
                        items.append({"student_id": t["student_id"], "data": {"date_from": (lv or {}).get("end") or _today().isoformat()}})
                    o = ORD.create_order(c, key, items, source="Talabalar markazi",
                                         note=f"Talabalar markazi: akademik ta'til muddati tugashi ({len(items)} ta talaba)")
                    ref = f"BUYRUQ#{o['id']}"
                    for t in lst:
                        _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='bajarildi', doc_reg=?, done_at=?, done_by=?, note=? WHERE id=? AND status='yangi'",
                                     (ref, now, c.user["id"], f"Buyruqlar bo'limida «{ORD.KINDS[key]['short']}» loyihasi #{o['id']}", t["id"]))
                        _log(_con, t["case_id"], t["id"], t["student_id"], c, "buyruq loyihasi yaratildi (ommaviy)", f"Buyruqlar · #{o['id']} · {ORD.KINDS[key]['short']}")
                orders_.append({"order_id": o["id"], "title": T[key], "n": len(lst)})
        zipname = None
        cur = _con.execute("INSERT INTO ops_batches(ts,user_id,kind,n,files,order_ids,note) VALUES(?,?,?,?,?,?,?)",
                           (now, c.user["id"], body.kind, sum(f["n"] for f in files) + sum(o["n"] for o in orders_),
                            json.dumps(files, ensure_ascii=False), json.dumps([o["order_id"] for o in orders_]), json.dumps(skipped[:200], ensure_ascii=False)))
        bid = cur.lastrowid
        if len(files) > 1:
            import zipfile
            zipname = f"PAKET-{bid:04d}.zip"
            with zipfile.ZipFile(D.OUT / zipname, "w", zipfile.ZIP_DEFLATED) as z:
                for f in files: z.write(D.OUT / f["file"], f["file"])
            _con.execute("UPDATE ops_batches SET zip=? WHERE id=?", (zipname, bid))
        _con.commit()
    rbac.audit(_con, c, f"talabalar markazi: ommaviy {'xatlar paketi' if body.kind == 'xat' else 'buyruq loyihalari'}", OPS, True,
               "; ".join(f"{f['title']}: {f['n']} ({f['file']})" for f in files) + "; ".join(f"{o['title']}: #{o['order_id']} ({o['n']} talaba)" for o in orders_))
    ev = evaluate(_con)
    return {"ok": True, "batch": bid, "files": files, "zip": zipname, "orders": orders_, "skipped": skipped[:50], "cant": cant,
            "n": sum(f["n"] for f in files) + sum(o["n"] for o in orders_), "engine": ev}

@router.get("/api/ops/bulk/{bid}/zip")
def api_bulk_zip(bid: int, request: Request):
    c = C(request); _view_guard(c, "talabalar markazi: ommaviy paket (ZIP)")
    from . import documents as D
    b = db.one(_con, "SELECT * FROM ops_batches WHERE id=?", (bid,))
    if not b or not b["zip"]: raise HTTPException(404)
    if b["user_id"] != c.user["id"] and c.role.key != SUPERVISOR: raise AccessDenied("⛔ Paketni tayyorlagan xodim yoki Registrator ofisi boshlig'i yuklab oladi.")
    f = (D.OUT / b["zip"]).resolve()
    if f.parent != D.OUT.resolve() or not f.exists(): raise HTTPException(404)
    return FileResponse(f, media_type="application/zip", filename=b["zip"])
