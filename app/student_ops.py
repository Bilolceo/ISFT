"""Talabalar bilan ishlash markazi (Registrator ofisi, tyutorlar, call-markaz).

Dizayn: docs/talabalar-markazi.md. Qisqacha:
  * Qoidalar dvigateli (evaluate) har bir talaba bo'yicha signallarni KOD bilan hisoblaydi: kontrakt muddati, sababsiz qoldirilgan
    soatlar zinapoyasi, JPA + o'zlashtirilmagan fanlar, sababli qoldirish hujjati, akademik ta'til muddati, otrabotka muddati.
  * Har signal → bitta ochiq holat (ops_cases.key UNIQUE: "talaba:qoida"). Daraja oshsa — yangi topshiriq; shart yo'qolsa — holat yopiladi.
  * Topshiriqlar (ops_tasks) rolga tushadi: call-markaz (qo'ng'iroq + skript), tyutor (suhbat, hujjat), registrator (xat, buyruq loyihasi).
  * Natijalar (va'da, javob bermadi, ...) keyingi qadamni o'zi rejalashtiradi. Hammasi ops_log va audit jurnalida.
  * Otrabotka: varaqa (hujjatlar markazi, QR) → muddat → skan yuklash → baho yonma-yon → registrator tasdiqlaydi → baho o'tadi.

Qoidalardagi raqamlar institut tomonidan TASDIQLANMAGAN (ops_policy.verified=0) — UI'da shunday ko'rsatiladi.
Istisno: o'tish bali (40) — institutning akademik qoidalari (app/academic_rules.py), verified=1.
"""
import asyncio, base64, binascii, datetime as dt, json, random, re, secrets, threading
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
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
    ("hours_to_date", 180, "Semestr boshidan o'tilgan auditoriya soatlari (namuna)"),
    ("pass_score", AR.PASS, "Fan bo'yicha o'tish bali (100 ballik, «3» baho) — akademik qoidalar taqdimoti"),
    ("gpa_min", 3.0, "Minimal JPA (5 ballik)"),
    ("fails_warn", 2, "Shuncha fandan o'tmasa — JPA yetarli bo'lsa ham ogohlantirish"),
    ("medical_doc_days", 3, "Kasallik/komandirovkadan keyin hujjat topshirish muddati, kun"),
    ("leave_warn_days", 90, "Akademik ta'til tugashiga shuncha kun (~3 oy) qolganda ogohlantirish: call-markaz qo'ng'irog'i"),
    ("retake_days", 3, "Otrabotka varaqasini qaytarish muddati, kun"),
    ("call_max_attempts", 3, "Javob bermasa — shuncha urinishdan keyin tyutorga o'tadi"),
    # DEMO TAXMIN: institut call-markaz me'yorini bermagan — 1 operator kuniga ~60 ta qo'ng'iroq (o'rtacha 5–6 daqiqa + yozuv)
    ("call_daily_capacity", 60, "Call-markaz: bir operator bir ish kunida qiladigan qo'ng'iroqlar (navbat shu bo'yicha kunlarga taqsimlanadi)"),
    # Registrator ofisi (M. Baratov): zinapoyaning oxirgi bosqichi va imtihonga ruxsatnoma — tasdiqlanmagan namunaviy qiymatlar
    ("att_expel_hours", 72, "Sababsiz qoldirilgan soat: hayfsandan keyin ham davom etsa — «chetlashtirishga tayyor» ro'yxati"),
    ("contract_expel_days", 30, "Kontrakt muddatidan shuncha kun o'tgan va ota-onaga xat yuborilgan bo'lsa — «chetlashtirishga tayyor»"),
    ("permit_att_hours", 48, "Imtihonga ruxsatnoma: sababsiz qoldirilgan soatlar shu chegaradan oshmasligi kerak (hayfsan chegarasi)"),
]
VERIFIED = {"pass_score", "att_call_hours", "att_letter_hours", "att_reprimand_hours"}   # institut qoidasi (akademik qoidalar; davomat — rektor qarori) — qolganlari hali tasdiqlanmagan
REASONS = {"sababsiz": "Sababsiz", "kasallik": "Kasallik", "komandirovka": "Xizmat safari (komandirovka)",
           "mehnat_tatili": "Mehnat ta'tili", "oilaviy": "Oilaviy sabab"}
EXCUSABLE = ("kasallik", "komandirovka", "mehnat_tatili", "oilaviy")
RULES = {"kontrakt": "Kontrakt to'lovi", "davomat": "Davomat (sababsiz)", "akademik": "O'zlashtirish (JPA / qarzdor fanlar)",
         "hujjat": "Sababli qoldirish hujjati", "tatil": "Akademik ta'til muddati", "otrabotka": "Otrabotka muddati"}
LEVELS = {1: "Diqqat", 2: "Kritik", 3: "Jiddiy"}
KINDS = {"qongiroq": "Qo'ng'iroq", "suhbat": "Suhbat", "hujjat": "Hujjat so'rash", "xat": "Ogohlantirish xati", "buyruq": "Buyruq loyihasi"}

# Ko'rish: to'liq / fakultet / faqat jamlangan
FULL_VIEW = ("talabalar", "registrator_xodim", "akademik", "prorektor_oquv")
REG_STAFF = "registrator_xodim"   # Registrator ofisi xodimi: boshliq navbatidagi ishlar (varaqa, skan, xat, qo'ng'iroq natijasi); bahoni tasdiqlash va buyruq loyihasi — boshliqda
FAC_VIEW = ("tyutor",)   # institutda dekan lavozimi yo'q — fakultet darajasidagi ko'rinish Registrator ofisida (FULL_VIEW)
AGG_VIEW = ("rektor", "kengash", "prorektor_yoshlar")
SUPERVISOR = "talabalar"

DEMO_USERS = [  # sun'iy ism-shariflar; parol rbac.DEMO_PASSWORD
    ("Call-markaz operatori: Rahimova Nigora Odil qizi", "call_center", None),
    ("Tyutor (Xalqaro iqtisodiyot va moliya fakulteti): Ergasheva Sitora Komil qizi", "tyutor", 2),
    ("Tyutor (Iqtisodiyot va axborot texnologiyalari fakulteti): Saidov Temur Murod o'g'li", "tyutor", 1),
    ("Tyutor (Ijtimoiy-gumanitar fanlar va tillar fakulteti): Qodirova Laylo Erkin qizi", "tyutor", 3),
]

def _today(): return dt.date.today()
def _now(): return dt.datetime.now().replace(microsecond=0)
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
CREATE INDEX IF NOT EXISTS ix_abs_st ON absences(student_id);
CREATE INDEX IF NOT EXISTS ix_cases_st ON ops_cases(student_id, status);
CREATE INDEX IF NOT EXISTS ix_tasks_case ON ops_tasks(case_id, status);
CREATE INDEX IF NOT EXISTS ix_tasks_role ON ops_tasks(assignee_role, status);
CREATE INDEX IF NOT EXISTS ix_log_case ON ops_log(case_id);
"""

def init(con):
    con.executescript(SCHEMA)
    if "phone" not in {r[1] for r in con.execute("PRAGMA table_info(students)").fetchall()}:
        con.execute("ALTER TABLE students ADD COLUMN phone TEXT")
    if "planned_on" not in {r[1] for r in con.execute("PRAGMA table_info(ops_tasks)").fetchall()}:   # call-markaz: rejalashtirilgan kun
        con.execute("ALTER TABLE ops_tasks ADD COLUMN planned_on TEXT")
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
    with _lock:   # call-markaz navbati darhol kunlarga taqsimlansin (agentlar skaneri va panel birinchi so'rovdayoq to'g'ri raqam ko'radi)
        schedule_calls(con); con.commit()

def seed(con, today=None):
    """Demo ma'lumot (sun'iy): telefonlar, to'lov jadvali, dars qoldirishlar (sabablari bilan), akademik ta'tillar, otrabotkalar."""
    R = random.Random(20261106)
    today = today or _today()
    P = policy(con)
    for sid, in con.execute("SELECT id FROM students WHERE phone IS NULL").fetchall():
        con.execute("UPDATE students SET phone=? WHERE id=?",
                    (f"+998 9{R.choice('0134579')} {R.randint(100, 999)} {R.randint(10, 99)} {R.randint(10, 99)}", sid))
    for off, pct, label in [(-36, 25, "1-to'lov"), (3, 50, "2-to'lov"), (95, 75, "3-to'lov"), (185, 100, "4-to'lov")]:
        con.execute("INSERT INTO contract_plan(due,cum_pct,label) VALUES(?,?,?)", ((today + dt.timedelta(days=off)).isoformat(), pct, label))
    H = int(P["hours_to_date"])
    rows = []
    for s in db.rows(con, """SELECT s.id, s.attendance, s.level, s.study_form, g.course FROM students s JOIN groups_ g ON g.id=s.group_id
                             WHERE s.status='faol' AND COALESCE(s.study_form,'kunduzgi')!='masofaviy'"""):
        if s["study_form"] == "sirtqi":
            # sirtqi talabalar ishlaydi: sessiyadan xizmat safari, mehnat ta'tili yoki kasallik sababli qolish — hujjat bilan
            if R.random() < 0.12:
                reason = R.choices(["komandirovka", "mehnat_tatili", "kasallik"], [45, 30, 25])[0]
                h = R.choice([6, 8, 12]); end = today - dt.timedelta(days=R.randint(0, 25))
                doc = R.choices(["tasdiqlangan", "kutilmoqda", "yoq"], [55, 35, 10] if (today - end).days <= 6 else [85, 0, 15])[0]
                rows.append((s["id"], (end - dt.timedelta(days=R.randint(1, 4))).isoformat(), end.isoformat(), h, reason, doc, _iso(_now())))
            continue
        missed = int(round((100 - (s["attendance"] or 100)) / 100 * H))
        while missed > 0:
            h = min(missed, R.choice([2, 4, 4, 6, 6, 8]))
            missed -= h
            opts = ["sababsiz", "kasallik", "oilaviy"] + (["komandirovka", "mehnat_tatili"] if (s["level"] == "magistr" or s["course"] >= 3) else [])
            w = [50, 30, 10] + ([5, 5] if len(opts) == 5 else [])
            reason = R.choices(opts, w)[0]
            ago = R.randint(1, 60)
            start = today - dt.timedelta(days=ago)
            end = start + dt.timedelta(days=max(0, h // 6 - 1) + (R.randint(1, 5) if reason in ("kasallik", "komandirovka", "mehnat_tatili") else 0))
            doc = None
            if reason in EXCUSABLE:
                recent = (today - end).days <= 6
                if reason == "oilaviy":   # oilaviy sabab — ariza odatda oldindan beriladi
                    doc = R.choices(["tasdiqlangan", "yoq"], [85, 15])[0]
                else:
                    doc = R.choices(["tasdiqlangan", "kutilmoqda", "yoq"], [60, 30, 10] if recent else [88, 0, 12])[0]
            rows.append((s["id"], start.isoformat(), min(end, today).isoformat(), h, reason, doc, _iso(_now())))
    con.executemany("INSERT INTO absences(student_id,start,end,hours,reason,doc_status,created_at) VALUES(?,?,?,?,?,?,?)", rows)
    leaves = db.rows(con, "SELECT id FROM students WHERE status=\"akademik ta'til\" ORDER BY id")
    for i, s in enumerate(leaves):
        left = [12, 26, -9][i] if i < 3 else R.randint(-40, 200)        # birinchi uchtasi — ogohlantirish oynasida
        end = today + dt.timedelta(days=left)
        con.execute("INSERT INTO student_leaves(student_id,kind,start,end,order_no) VALUES(?,?,?,?,?)",
                    (s["id"], "akademik", (end - dt.timedelta(days=270)).isoformat(), end.isoformat(), f"TH-25/{R.randint(100, 999)}"))
    con.commit()

def seed_retakes(con, ctx_issuer, base_url):
    """Bir nechta otrabotka (hujjatlar markazi orqali varaqa bilan): biri ertaga tugaydi, biri muddati o'tgan."""
    R = random.Random(7)
    pass_ = int(policy(con)["pass_score"])
    cand = db.rows(con, f"""SELECT g.student_id, g.subject, g.teacher_id, g.score FROM grades g JOIN students s ON s.id=g.student_id
                           WHERE g.semester=1 AND g.score<{pass_} AND s.faculty_id=2 AND s.status='faol' ORDER BY g.student_id LIMIT 40""")
    R.shuffle(cand)
    now = _now()
    for i, c in enumerate(cand[:3]):
        due = now + dt.timedelta(hours=[20, -26, 50][i])
        issued = due - dt.timedelta(days=int(policy(con)["retake_days"]))
        cur = con.execute("""INSERT INTO retakes(student_id,subject,teacher_id,reason,status,issued_at,due_at,score_old,created_by)
                             VALUES(?,?,?,?,?,?,?,?,?)""", (c["student_id"], c["subject"], c["teacher_id"], "Qarzdor fan (o'tish balidan past)",
                                                          "berildi", _iso(issued), _iso(due), c["score"], ctx_issuer.user["id"]))
        _issue_sheet(con, ctx_issuer, cur.lastrowid, base_url)
    con.commit()

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

def _unexcused_sql(P, today):
    """Sababsiz hisoblanadigan soatlar: 'sababsiz' + hujjati yo'q yoki muddatida topshirilmagan sababli qoldirishlar."""
    cut = (today - dt.timedelta(days=int(P["medical_doc_days"]))).isoformat()
    return (f"(reason='sababsiz' OR (reason IN ('kasallik','komandirovka','mehnat_tatili','oilaviy') AND "
            f"(doc_status='yoq' OR (doc_status='kutilmoqda' AND end < '{cut}'))))")

def student_facts(con, sid) -> dict:
    P, today = policy(con), _today()
    unx = con.execute(f"SELECT COALESCE(SUM(hours),0) FROM absences WHERE student_id=? AND {_unexcused_sql(P, today)}", (sid,)).fetchone()[0]
    exc = con.execute("SELECT COALESCE(SUM(hours),0) FROM absences WHERE student_id=?", (sid,)).fetchone()[0] - unx
    pass_ = int(P["pass_score"])
    gr = db.rows(con, "SELECT subject, score FROM grades WHERE student_id=? AND semester=1 ORDER BY subject", (sid,))
    gpa5 = round(sum(_grade5(g["score"], pass_) for g in gr) / len(gr), 2) if gr else None
    return {"unexcused": int(unx), "excused": int(exc), "gpa5": gpa5, "grades": gr,
            "fails": [g for g in gr if g["score"] < pass_]}

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
    rep_h = P["att_reprimand_hours"]
    for r in db.rows(con, f"""SELECT a.student_id, SUM(a.hours) h FROM absences a JOIN students s ON s.id=a.student_id
                              WHERE s.status='faol' AND {unx} GROUP BY a.student_id"""):
        lvl = davomat_level(r["h"], P)
        if lvl: out[f"{r['student_id']}:davomat"] = (r["student_id"], "davomat", lvl, {"hours": r["h"], "next": None if lvl >= 3 else rep_h})
    cut = today - dt.timedelta(days=int(P["medical_doc_days"]))
    for r in db.rows(con, """SELECT a.student_id, a.id, a.reason, a.end, a.hours FROM absences a JOIN students s ON s.id=a.student_id
                             WHERE s.status='faol' AND a.doc_status='kutilmoqda' ORDER BY a.end"""):
        k = f"{r['student_id']}:hujjat"
        late = dt.date.fromisoformat(r["end"]) < cut
        prev = out.get(k)
        items = (prev[3]["items"] if prev else []) + [{"id": r["id"], "reason": r["reason"], "end": r["end"], "hours": r["hours"], "late": late}]
        lvl = max(prev[2] if prev else 1, 2 if late else 1)
        out[k] = (r["student_id"], "hujjat", lvl, {"items": items, "deadline_days": int(P["medical_doc_days"])})
    pass_, fails_warn, gmin = int(P["pass_score"]), int(P["fails_warn"]), P["gpa_min"]
    agg = {}
    for g in db.rows(con, "SELECT g.student_id, g.subject, g.score FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester=1 AND s.status='faol'"):
        agg.setdefault(g["student_id"], []).append(g)
    for sid, gs in agg.items():
        fails = [g for g in gs if g["score"] < pass_]
        gpa5 = round(sum(_grade5(g["score"], pass_) for g in gs) / len(gs), 2)
        if len(fails) >= fails_warn or gpa5 < gmin:
            lvl = 3 if len(fails) >= fails_warn + 2 else 2
            out[f"{sid}:akademik"] = (sid, "akademik", lvl, {"gpa5": gpa5, "fails": [{"subject": f["subject"], "score": f["score"]} for f in fails],
                                                            "gpa_ok": gpa5 >= gmin})
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

def davomat_level(h, P) -> int:
    """Sababsiz soatlar zinapoyasi: hayfsan — chegaradan OSHSA (48 → 49+), xat va qo'ng'iroq — chegaraga yetsa (30+)."""
    if h > P["att_reprimand_hours"]: return 3
    if h >= P["att_letter_hours"]: return 2
    if h >= P["att_call_hours"]: return 1
    return 0

# qoida + daraja -> topshiriqlar: (tur, rol, muddat soatda)
PLAN = {
    ("kontrakt", 2): [("qongiroq", "call_center", 8)],
    ("kontrakt", 3): [("qongiroq", "call_center", 8), ("xat", "talabalar", 48)],
    ("davomat", 1): [("qongiroq", "call_center", 24)],
    ("davomat", 2): [("qongiroq", "call_center", 24), ("xat", "talabalar", 48)],   # 30 soat: qo'ng'iroq + ogohlantirish xati
    ("davomat", 3): [("buyruq", "talabalar", 72), ("suhbat", "tyutor", 48)],
    ("hujjat", 1): [("hujjat", "tyutor", 24)],
    ("hujjat", 2): [("hujjat", "tyutor", 8)],
    ("akademik", 2): [("suhbat", "tyutor", 72)],
    ("akademik", 3): [("suhbat", "tyutor", 48), ("xat", "talabalar", 72)],
    ("tatil", 1): [("qongiroq", "call_center", 48)],
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
    ("davomat", "qongiroq"): "Davomat bo'yicha qo'ng'iroq", ("davomat", "xat"): "Davomat bo'yicha ogohlantirish xati",
    ("davomat", "buyruq"): "Hayfsan buyrug'i loyihasi", ("davomat", "suhbat"): "Tyutor suhbati: davomat",
    ("hujjat", "hujjat"): "Sababli qoldirish hujjatini so'rash", ("akademik", "suhbat"): "Tyutor suhbati: o'zlashtirish",
    ("akademik", "xat"): "O'zlashtirish bo'yicha ogohlantirish xati", ("akademik", "qongiroq"): "O'zlashtirish bo'yicha qo'ng'iroq",
    ("tatil", "qongiroq"): "Akademik ta'til tugashi haqida eslatma", ("tatil", "buyruq"): "Ta'tildan qaytish buyrug'i loyihasi",
    ("otrabotka", "qongiroq"): "Otrabotka muddati eslatmasi", ("otrabotka", "suhbat"): "Otrabotka muddati o'tdi: tyutor ogohlantirsin",
}

def _dmy(d): return f"{d[8:10]}.{d[5:7]}.{d[:4]}" if d and len(d) >= 10 else d

def _money(x): return f"{int(x):,}".replace(",", " ") + " so'm"

def script(rule, kind, facts, s, P):
    """Qo'ng'iroq/suhbat skripti — faqat bazadagi faktlardan. Me'yoriy havolalar o'ylab topilmaydi."""
    facts = {**facts}
    for k in ("due", "end"):
        if facts.get(k): facts[k] = _dmy(facts[k])
    name = s["full_name"].split()[1] if len(s["full_name"].split()) > 1 else s["full_name"]
    say = []
    if rule == "kontrakt":
        say = [f"Assalomu alaykum, {name}. ISFT institutining Registrator ofisidan bezovta qilyapmiz.",
               f"{facts['installment']} muddati {facts['due']} — hozircha {_money(facts['need_now'])} yetishmayapti (umumiy qarz {_money(facts['debt_total'])}).",
               "To'lov qachon amalga oshirilishini aniq sana bilan kelishib oling. Bo'lib to'lash kerak bo'lsa — buxgalteriya bo'limiga yo'naltiring.",
               "Sana aytilsa — «Va'da berdi» natijasini o'sha sana bilan belgilang: tizim muddat o'tganda o'zi qayta eslatadi."]
    elif rule == "davomat":
        say = [f"Assalomu alaykum, {name}. ISFT institutining Registrator ofisidan qo'ng'iroq qilyapmiz.",
               f"Joriy semestrda {facts['hours']} soat dars sababsiz qoldirilgan." + (f" {int(facts['next'])} soatdan oshsa, hayfsan e'lon qilish masalasi ko'riladi." if facts.get("next") else " Hayfsan chegarasidan oshgan."),
               "Sababini so'rang. Kasallik yoki xizmat safari bo'lsa — hujjatni 3 kun ichida tyutorga topshirish kerakligini ayting.",
               "Muammo bo'lsa (ish, oilaviy holat) — tyutor bilan uchrashuv belgilang."]
    elif rule == "akademik":
        fl = ", ".join(f"{f['subject']} ({f['score']})" for f in facts["fails"]) or "—"
        say = [f"Talabaga o'zlashtirilmagan fanlar: {fl}. JPA: {facts['gpa5']}" + (" — umumiy ko'rsatkich yetarli, lekin qarzdor fanlar bor." if facts["gpa_ok"] else "."),
               "Qayta topshirish (otrabotka) tartibini tushuntiring va varaqa olish uchun kunni kelishing.",
               "Qiyinchilik sababini aniqlang (dars qoldirish, fan murakkabligi, ish) — natijani qisqa yozib qo'ying."]
    elif rule == "hujjat":
        it = facts["items"][-1]
        say = [f"{REASONS.get(it['reason'], it['reason'])} sababli {it['hours']} soat qoldirilgan (tugagan sana {_dmy(it['end'])}).",
               f"Tasdiqlovchi hujjat {facts['deadline_days']} kun ichida topshirilishi kerak, aks holda soatlar sababsiz hisoblanadi.",
               "Hujjat kelsa — «Hujjat keldi», kelmasa — «Hujjat yo'q» deb belgilang."]
    elif rule == "tatil":
        say = [f"Akademik ta'til ({facts['order_no']}) {facts['end']}da tugaydi" + (" — muddat o'tgan." if facts["days"] < 0 else f" ({facts['days']} kun qoldi)."),
               "O'qishga qaytish arizasi va kerakli hujjatlarni (tibbiy xulosa va h.k.) eslating; talaba ikki tomonga borib yurmasligi uchun ro'yxatni aniq ayting.",
               "Qaytish kursi, guruh va o'quv rejalaridagi farq (akademik farq fanlari) bo'yicha Registrator ofisiga oldindan kelishini so'rang.",
               "Kontrakt asosida o'qisa — qaytish semestri uchun to'lov jadvalini buxgalteriyadan aniqlab olishini eslating."]
        if kind == "buyruq":
            say.append("Ariza kelgach «Ta'tildan qaytish» buyrug'i loyihasini tayyorlang (Hujjatlar markazi → talabalar harakati: qayta tiklash). "
                       "Ariza → buyruq oqimi buyruqlar modulida yuritilsa — shu topshiriq o'sha arizaga bog'lanadi.")
    elif rule == "otrabotka":
        late = (facts.get("hours_left") or 0) < 0
        say = [f"«{facts['subject']}» fanidan otrabotka varaqasi muddati: {_dmy(facts['due_at'])}, soat {facts['due_at'][11:16]}"
               + (" — MUDDAT O'TDI, varaqa hali qaytarilmagan." if late else "."),
               f"Varaqani o'qituvchiga imzolatib, Registrator ofisiga ({AR.REGISTRAR_ROOMS_TEXT}) topshirishni eslating."]
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
        if con.execute("SELECT 1 FROM ops_tasks WHERE case_id=? AND kind=? AND status='yangi'", (case_id, kind)).fetchone():
            continue   # shu holat bo'yicha ochiq topshiriq bor — dublikat yo'q
        sc = script(rule, kind, facts, s, P)
        cur = con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (case_id, sid, kind, TITLE.get((rule, kind), KINDS[kind]), role, fac,
                                                                _iso(now + dt.timedelta(hours=hrs)), "yangi", level, json.dumps(sc, ensure_ascii=False), _iso(now)))
        _log(con, case_id, cur.lastrowid, sid, None, "topshiriq yaratildi", f"{KINDS[kind]} → {ROLE_T.get(role, role)}")
        made += 1
    return made

ROLE_T = {"call_center": "Call-markaz", "tyutor": "Tyutor", "talabalar": "Registrator ofisi", "sirtqi": "Sirtqi bo'lim"}

def evaluate(con, today=None) -> dict:
    """Qoidalarni ishga tushiradi. Idempotent: necha marta chaqirilsa ham bitta holat = bitta ochiq yozuv."""
    with _lock:
        today = today or _today(); now = _now(); P = policy(con)
        sig = _signals(con, today)
        open_ = {c["key"]: c for c in db.rows(con, "SELECT * FROM ops_cases WHERE status='ochiq'")}
        studs = {s["id"]: s for s in db.rows(con, "SELECT id, full_name, faculty_id, study_form FROM students")}
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
                    sc = script(rule, "qongiroq", facts, s, P); sc["say"].insert(0, f"Talaba {_dmy(pr['p'])} gacha hal qilishga va'da bergan edi — muddat o'tdi.")
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

def call_capacity(con) -> tuple[int, int]:
    ops = max(1, con.execute("SELECT COUNT(*) FROM users WHERE role='call_center'").fetchone()[0])
    return int(policy(con).get("call_daily_capacity", 60)) * ops, ops

def schedule_calls(con, today=None, now=None):
    """Call-markaz navbati: bugungi ro'yxat = kunlik imkoniyat (operatorlar × me'yor). Qolgani o'chirilmaydi — ustuvorlik
    tartibida keyingi ish kunlariga rejalashtiriladi (planned_on), muddati o'sha kun 18:00. Ustuvorlik: otrabotka va va'da
    muddati o'tgan qayta qo'ng'iroqlar → jiddiylik darajasi → asl muddat. Bugunga yoki o'tgan kunga rejalashtirilgani joyida
    qoladi (o'tgan kundan qolgani — kechikkan). Idempotent: necha marta chaqirilsa ham bir xil taqsimot."""
    today = today or _today(); now = now or _now()
    cap, _ = call_capacity(con)
    rows = db.rows(con, """SELECT t.id, t.planned_on, t.due_at, t.level, t.title, oc.rule FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id
                           WHERE t.status='yangi' AND t.assignee_role='call_center'""")
    td = today.isoformat()
    fixed = [r for r in rows if r["planned_on"] and r["planned_on"] <= td]
    free = [r for r in rows if not (r["planned_on"] and r["planned_on"] <= td)]
    urgent = lambda r: r["rule"] == "otrabotka" or (r["title"] or "").startswith("Va'da muddati")
    free.sort(key=lambda r: (not urgent(r), -(r["level"] or 0), r["due_at"] or "", r["id"]))
    first = _workday(today, 0)
    slots = max(0, cap - len(fixed)) if first == today else 0
    upd = []
    for i, r in enumerate(free):
        if urgent(r) or i < slots:
            day = today                                     # bugungi navbat: asl muddat saqlanadi
            due = r["due_at"] if (r["planned_on"] in (None, td)) else _iso(dt.datetime.combine(today, dt.time(18, 0)))
        else:
            j = i - slots     # bugun ish kuni bo'lsa — ertadan, aks holda birinchi ish kunidan
            day = _workday(first, j // cap + (1 if first == today else 0))
            due = _iso(dt.datetime.combine(day, dt.time(18, 0)))
        if r["planned_on"] != day.isoformat() or r["due_at"] != due:
            upd.append((day.isoformat(), due, r["id"]))
    if upd:
        con.executemany("UPDATE ops_tasks SET planned_on=?, due_at=? WHERE id=?", upd)
    return len(upd)

def calls_summary(con, where="1=1", args=()):
    """Call-markaz navbati: jami, bugun, rejalashtirilgan (keyingi kunlar), kechikkan, navbat necha ish kunida tugaydi."""
    td, now = _today().isoformat(), _iso(_now())
    r = db.one(con, f"""SELECT COUNT(*) total, SUM(COALESCE(t.planned_on,'') <= ?) today, SUM(COALESCE(t.planned_on,'') > ?) scheduled,
                         SUM(COALESCE(t.planned_on,'') <= ? AND t.due_at < ?) late, MAX(t.planned_on) last_day
                         FROM ops_tasks t JOIN students s ON s.id=t.student_id
                         WHERE t.status='yangi' AND t.assignee_role='call_center' AND {where}""", (td, td, td, now, *args))
    cap, ops = call_capacity(con)
    out = {k: (r[k] or 0) for k in ("total", "today", "scheduled", "late")}
    out.update(capacity=cap, operators=ops, per_operator=cap // ops, last_day=r["last_day"],
               days=(_busdays(_today(), dt.date.fromisoformat(r["last_day"])) + 1) if r["last_day"] and r["last_day"] > td else (1 if out["total"] else 0))
    return out

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

def _scope_sql(c: Ctx, alias="s"):
    k = c.role.key
    if k in FULL_VIEW: return "1=1"
    if k in FAC_VIEW: return f"{alias}.faculty_id={int(c.user['faculty_id'] or 0)}"
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

def _task_scope_sql(c: Ctx):
    k = c.role.key
    if k in FULL_VIEW: return "1=1"
    if k == "call_center": return "t.assignee_role='call_center'"
    if k == "tyutor": return f"t.assignee_role='tyutor' AND t.faculty_id={int(c.user['faculty_id'] or 0)}"
    if k in SCOPED_VIEW: return f"{_scope_sql(c, 's')} AND t.case_id IN (SELECT id FROM ops_cases oc2 WHERE {_rule_sql(c, 'oc2.rule')})"
    return "0=1"

def _can_act(c: Ctx, t) -> bool:
    if t["status"] != "yangi": return False
    if c.role.key == SUPERVISOR: return True
    if c.role.key == REG_STAFF: return t["assignee_role"] in (SUPERVISOR, "call_center", "tyutor") and t["kind"] != "buyruq"
    if c.role.key == "call_center": return t["assignee_role"] == "call_center"
    if c.role.key == "tyutor": return t["assignee_role"] == "tyutor" and t["faculty_id"] == c.user["faculty_id"]
    if c.role.key == "sirtqi":   # sirtqi talabalar bo'yicha registrator: kontrakt va buyruq loyihasidan tashqari hammasi
        if t["kind"] == "buyruq": return False
        r = _con.execute("""SELECT oc.rule, s.study_form FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE oc.id=?""", (t["case_id"],)).fetchone()
        return bool(r) and r[1] == "sirtqi" and r[0] != "kontrakt"
    return False

def _mask(phone, c: Ctx):
    if not phone: return None
    return phone if c.role.key in ("call_center", "tyutor", SUPERVISOR, REG_STAFF) else phone[:8] + " *** ** " + phone[-2:]

# ---------------------------------------------------------------------------------------------
# O'qish
# ---------------------------------------------------------------------------------------------
def summary(c: Ctx):
    if c.role.key == "call_center":   # operator: faqat o'z navbatidagi holatlar
        tw = _task_scope_sql(c)
        by = db.rows(_con, f"""SELECT oc.rule, oc.level, COUNT(DISTINCT oc.id) n FROM ops_tasks t JOIN ops_cases oc ON oc.id=t.case_id
                                  WHERE t.status='yangi' AND oc.status='ochiq' AND {tw} GROUP BY oc.rule, oc.level""")
        tasks = db.rows(_con, f"""SELECT t.assignee_role role, COUNT(*) n, SUM(t.due_at < ?) late FROM ops_tasks t
                                    WHERE t.status='yangi' AND {tw} GROUP BY t.assignee_role""", (_iso(_now()),))
        done = _con.execute("SELECT COUNT(*) FROM ops_tasks WHERE done_by=? AND done_at>=?", (c.user["id"], _today().isoformat())).fetchone()[0]
        return {"by_rule": by, "tasks": tasks, "closed_7d": 0, "done_today": done, "rules": RULES, "levels": LEVELS, "last_run": None,
                "calls": calls_summary(_con)}
    w = "1=1" if c.role.key in FULL_VIEW + AGG_VIEW else _scope_sql(c)
    rw = _rule_sql(c)
    by = db.rows(_con, f"""SELECT oc.rule, oc.level, COUNT(*) n FROM ops_cases oc JOIN students s ON s.id=oc.student_id
                              WHERE oc.status='ochiq' AND {w} AND {rw} GROUP BY oc.rule, oc.level""")
    tasks = db.rows(_con, f"""SELECT t.assignee_role role, COUNT(*) n, SUM(t.due_at < ?) late FROM ops_tasks t JOIN students s ON s.id=t.student_id
                                WHERE t.status='yangi' AND {w} AND t.case_id IN (SELECT id FROM ops_cases oc WHERE {rw})
                                GROUP BY t.assignee_role""", (_iso(_now()),))
    closed7 = _con.execute(f"""SELECT COUNT(*) FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE oc.status='yopildi'
                                 AND oc.closed_at>=? AND {w} AND {rw}""", (_iso(_now() - dt.timedelta(days=7)),)).fetchone()[0]
    last = _con.execute("SELECT value FROM ops_policy WHERE key='_last_run'").fetchone()
    serious = _con.execute(f"""SELECT COUNT(DISTINCT oc.student_id) FROM ops_cases oc JOIN students s ON s.id=oc.student_id
                                 WHERE oc.status='ochiq' AND oc.level>=3 AND {w} AND {rw}""").fetchone()[0]
    return {"by_rule": by, "tasks": tasks, "closed_7d": closed7, "rules": RULES, "levels": LEVELS, "serious_students": serious,
            "last_run": dt.datetime.fromtimestamp(last[0]).isoformat(timespec="seconds") if last else None,
            "calls": calls_summary(_con, w)}

def _student_row(c: Ctx, sid):
    s = db.one(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.phone, s.faculty_id, s.status, s.payment_type, s.contract_amount, s.paid_amount,
                         g.name grp, g.course, f.name faculty FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
                         WHERE s.id=? AND {_scope_sql(c)}""", (sid,))
    if not s: raise AccessDenied("⛔ Bu talaba sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    s["phone"] = _mask(s["phone"], c)
    return s

def cases(c: Ctx, rule="", level=0, q="", faculty=0, limit=300):
    w = [_scope_sql(c), "oc.status='ochiq'", _rule_sql(c)]; a = []
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

def tasks(c: Ctx, status="yangi", limit=200, rule="", kind=""):
    extra, a = "", []
    if rule in RULES: extra += " AND oc.rule=?"; a.append(rule)
    if kind in KINDS: extra += " AND t.kind=?"; a.append(kind)
    rows = db.rows(_con, f"""SELECT t.*, s.full_name, s.phone, s.hemis_id, g.name grp, g.course, f.name faculty, oc.rule, oc.facts
                              FROM ops_tasks t JOIN students s ON s.id=t.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
                              JOIN ops_cases oc ON oc.id=t.case_id
                              WHERE {_task_scope_sql(c)} AND t.status=?{extra}
                              ORDER BY (COALESCE(t.planned_on,'') > ?), (t.due_at < ?) DESC, t.level DESC, t.due_at LIMIT ?""",
                   (status, *a, _today().isoformat(), _iso(_now()), limit))
    now, td = _iso(_now()), _today().isoformat()
    for r in rows:
        r["scheduled"] = bool(r.get("planned_on") and r["planned_on"] > td)   # keyingi kunlarga rejalashtirilgan qo'ng'iroq
        r["script"] = json.loads(r["script"] or "{}"); r["facts"] = json.loads(r["facts"] or "{}")
        r["phone"] = _mask(r["phone"], c); r["late"] = r["due_at"] < now; r["can_act"] = _can_act(c, r)
    return rows

def student_card(c: Ctx, sid):
    s = _student_row(c, sid)
    f = student_facts(_con, sid)
    cs = [x for x in db.rows(_con, "SELECT * FROM ops_cases WHERE student_id=? ORDER BY status, level DESC, id DESC", (sid,)) if _rule_ok(c, x["rule"])]
    for x in cs: x["facts"] = json.loads(x["facts"] or "{}")
    ok_case = {x["id"] for x in cs}
    ts = [x for x in db.rows(_con, f"SELECT t.* FROM ops_tasks t WHERE t.student_id=? ORDER BY t.id DESC", (sid,)) if c.role.key not in RULE_SCOPE or x["case_id"] in ok_case]
    for x in ts: x["script"] = json.loads(x["script"] or "{}"); x["can_act"] = _can_act(c, x)
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
    return {"student": s, "facts": f, "debt": debt, "cases": cs, "tasks": ts, "absences": ab, "log": log, "retakes": rt, "leaves": lv,
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

def retakes_list(c: Ctx):
    rows = db.rows(_con, f"""SELECT r.*, s.full_name, s.study_form, g.name grp, f.name faculty, t.full_name teacher,
                              (SELECT gg.score FROM grades gg WHERE gg.student_id=r.student_id AND gg.subject=r.subject AND gg.semester=1) hemis_score FROM retakes r
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
def api_cases(request: Request, rule: str = "", level: int = 0, q: str = "", faculty: int = 0):
    c = C(request); _view_guard(c, "talabalar markazi: holatlar ro'yxati")
    if c.role.key == "call_center": raise AccessDenied("⛔ Call-markaz faqat o'z qo'ng'iroqlar navbatini ko'radi.")
    return cases(c, rule, level, q.strip()[:60], faculty)

@router.get("/api/ops/tasks")
def api_tasks(request: Request, status: str = "yangi", rule: str = "", kind: str = ""):
    c = C(request); _view_guard(c, "talabalar markazi: topshiriqlar navbati")
    if status not in ("yangi", "bajarildi"): raise HTTPException(400)
    return tasks(c, status, rule=rule, kind=kind)

@router.get("/api/ops/student/{sid}")
def api_student(sid: int, request: Request):
    c = C(request); _view_guard(c, "talabalar markazi: talaba kartasi")
    if c.role.key == "call_center":   # call-markaz: faqat o'z navbatidagi talaba, minimal ma'lumot
        if not _con.execute("SELECT 1 FROM ops_tasks WHERE student_id=? AND assignee_role='call_center'", (sid,)).fetchone():
            raise AccessDenied("⛔ Bu talaba sizning navbatingizda emas.")
        st = db.one(_con, """SELECT s.id, s.full_name, s.phone, g.name grp, g.course, f.name faculty FROM students s
                             JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id WHERE s.id=?""", (sid,))
        ts = db.rows(_con, "SELECT * FROM ops_tasks WHERE student_id=? AND assignee_role='call_center' ORDER BY id DESC", (sid,))
        for x in ts: x["script"] = json.loads(x["script"] or "{}"); x["can_act"] = _can_act(c, x)
        return {"student": st, "tasks": ts, "log": [], "cases": [], "absences": [], "retakes": [], "leaves": [], "limited": True}
    rbac.audit(_con, c, "talaba kartasi (markaz)", OPS, True, f"#{sid}")
    return student_card(c, sid)

class Outcome(BaseModel):
    outcome: str
    note: str = Field("", max_length=1000)
    promise_date: str | None = None

OUTCOMES = {"qongiroq": ("gaplashildi", "vada", "javob_bermadi", "notogri_raqam"),
            "suhbat": ("bajarildi",), "hujjat": ("hujjat_keldi", "hujjat_yoq"), "xat": ("bajarildi",), "buyruq": ("bajarildi",)}
OUT_T = {"gaplashildi": "Gaplashildi", "vada": "Va'da berdi", "javob_bermadi": "Javob bermadi", "notogri_raqam": "Noto'g'ri raqam",
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
            sc = {"say": [f"Call-markaz {att} marta qo'ng'iroq qildi — javob bo'lmadi.", "Talabani dars paytida toping va masalani yuzma-yuz gaplashing."],
                  "tone": ["Hurmat bilan, ayblamasdan gaplashing."], "basis": []}
            cur = _con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (t["case_id"], t["student_id"], "suhbat", "Javob bermadi: tyutor topib gaplashsin", "tyutor",
                                                                   t["faculty_id"], _iso(now + dt.timedelta(hours=24)), "yangi", t["level"], json.dumps(sc, ensure_ascii=False), _iso(now)))
            _log(_con, t["case_id"], tid, t["student_id"], c, "javob bermadi", f"{att} urinish — tyutorga o'tkazildi")
            _con.commit(); return {"ok": True, "escalated": cur.lastrowid}
        _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome=?, note=?, promise_date=?, done_at=?, done_by=? WHERE id=?",
                     (body.outcome, note, body.promise_date if body.outcome == "vada" else None, _iso(now), c.user["id"], tid))
        _log(_con, t["case_id"], tid, t["student_id"], c, OUT_T[body.outcome].lower(),
             (f"va'da: {body.promise_date}. " if body.outcome == "vada" else "") + note)
        if body.outcome == "notogri_raqam":
            sc = {"say": ["Call-markaz talabaga ulana olmadi: telefon raqami noto'g'ri.", "HEMIS'dagi aloqa ma'lumotini yangilang."], "tone": [], "basis": []}
            _con.execute("""INSERT INTO ops_tasks(case_id,student_id,kind,title,assignee_role,faculty_id,due_at,status,level,script,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (t["case_id"], t["student_id"], "suhbat", "Telefon raqamini aniqlash", "tyutor", t["faculty_id"],
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
    if t["rule"] == "kontrakt": key, params = "debt_letter", {"target": tgt}
    elif t["kind"] == "buyruq" and t["rule"] == "tatil": key, params = "order_student", {"target": tgt, "action": "tiklash", "reason": "akademik ta'til muddati tugashi munosabati bilan"}
    elif t["kind"] == "buyruq": key, params = "reprimand", {"target": tgt, "reason": body.reason}
    else: key, params = "warn_letter", {"target": tgt, "basis": "akademik" if t["rule"] == "akademik" else "davomat"}
    try:
        r = D.issue(_con, c, key, params, SV.public_base(request))
    except ValueError as e:
        raise HTTPException(400, str(e))
    reg = r["regs"][0]
    _con.execute("UPDATE ops_tasks SET status='bajarildi', outcome='bajarildi', doc_reg=?, done_at=?, done_by=?, note=? WHERE id=?",
                 (reg, _iso(_now()), c.user["id"], f"{D.CAT[key]['title']} — {reg}" + (" (rektor imzosini kutadi)" if r["status"] == "loyiha" else ""), tid))
    _log(_con, t["case_id"], tid, t["student_id"], c, "hujjat tayyorlandi", f"{D.CAT[key]['title']} · {reg}")
    _con.commit()
    return {"ok": True, "reg_no": reg, "file": r["file"], "status": r["status"], "title": D.CAT[key]["title"]}

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

@router.post("/api/ops/retakes")
def api_retake_new(body: RetakeIn, request: Request):
    c = C(request); _guard(c, "otrabotka varaqasi berish", f"#{body.student_id} {body.subject}")
    if c.role.key not in RETAKE_ISSUERS: raise AccessDenied(RETAKE_DENY)
    _student_row(c, body.student_id)
    g = db.one(_con, "SELECT subject, score, teacher_id FROM grades WHERE student_id=? AND subject=? AND semester=1", (body.student_id, body.subject))
    if not g: raise HTTPException(400, "Talabada bu fan yo'q")
    if db.one(_con, "SELECT 1 x FROM retakes WHERE student_id=? AND subject=? AND status IN ('berildi','topshirildi')", (body.student_id, body.subject)):
        raise HTTPException(409, "Bu fan bo'yicha ochiq otrabotka bor")
    now = _now(); due = now + dt.timedelta(days=int(policy(_con)["retake_days"]))
    cur = _con.execute("""INSERT INTO retakes(student_id,subject,teacher_id,reason,status,issued_at,due_at,score_old,created_by)
                          VALUES(?,?,?,?,?,?,?,?,?)""", (body.student_id, g["subject"], g["teacher_id"],
                                                       "Qarzdor fan (o'tish balidan past)" if g["score"] < policy(_con)["pass_score"] else "Qoldirilgan mashg'ulot",
                                                       "berildi", _iso(now), _iso(due), g["score"], c.user["id"]))
    from . import service as SV
    r = _issue_sheet(_con, c, cur.lastrowid, SV.public_base(request))
    _log(_con, None, None, body.student_id, c, "otrabotka varaqasi berildi", f"{g['subject']} · {r['regs'][0]} · muddat {due:%Y-%m-%d %H:%M}")
    _con.commit()
    return {"ok": True, "id": cur.lastrowid, "reg_no": r["regs"][0], "file": r["file"], "due_at": _iso(due)}

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
    score: int = Field(..., ge=0, le=100)
    note: str = Field("", max_length=500)
    force: bool = False          # skanda imzo aniqlanmagan, lekin registrator ko'z bilan tekshirdi (izoh majburiy)

def _approver(c: Ctx, r):
    if c.role.key not in RETAKE_APPROVERS: raise AccessDenied("⛔ Bahoni Registrator ofisi (sirtqi talabalarniki — Sirtqi bo'lim) tasdiqlaydi.")
    _student_row(c, r["student_id"])   # sirtqi — faqat sirtqi talaba

@router.post("/api/ops/retakes/{rid}/approve")
def api_retake_approve(rid: int, body: Approve, request: Request):
    c = C(request); _guard(c, "otrabotka: bahoni tasdiqlash", f"#{rid} → {body.score}")
    if c.role.key not in RETAKE_APPROVERS: raise AccessDenied("⛔ Bahoni Registrator ofisi (sirtqi talabalarniki — Sirtqi bo'lim) tasdiqlaydi.")
    with _lock:
        r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
        if not r: raise HTTPException(404)
        _approver(c, r)
        if r["status"] != "topshirildi" or not r["file"]: raise HTTPException(409, "Avval imzolangan varaqa skanini yuklang")
        sm = json.loads(r.get("scan_meta") or "{}")
        if sm.get("match") is False and not body.force: raise HTTPException(409, f"Skandagi ro'yxat raqami ({sm.get('reg_no')}) bu otrabotkaga mos emas")
        if sm.get("signed") is False and not body.force:
            raise HTTPException(409, "Skanda o'qituvchi imzosi aniqlanmadi. Varaqani qaytaring yoki imzoni ko'z bilan tekshirib, izoh bilan tasdiqlang")
        if body.force and len(body.note.strip()) < 3: raise HTTPException(400, "Qo'lda tasdiqlash sababini yozing")
        cur = _con.execute("UPDATE retakes SET status='tasdiqlandi', score_new=?, approved_at=?, approved_by=?, note=? WHERE id=? AND status='topshirildi'",
                           (body.score, _iso(_now()), c.user["id"], body.note.strip(), rid))
        if cur.rowcount != 1: raise HTTPException(409, "Allaqachon tasdiqlangan")
        _con.execute("UPDATE grades SET score=? WHERE student_id=? AND subject=? AND semester=1", (body.score, r["student_id"], r["subject"]))
        _log(_con, None, None, r["student_id"], c, "otrabotka bahosi tasdiqlandi", f"{r['subject']}: {r['score_old']} → {body.score} (varaqa {r['reg_no']})"
             + (f" · skandan o'qilgan ball: {sm['score']}" if sm.get("score") is not None else "")
             + (f" · qo'lda tasdiqlandi: {body.note.strip()}" if body.force else ""))
        _con.commit()
    rbac.audit(_con, c, "baho o'zgartirildi (otrabotka)", OPS, True, f"talaba #{r['student_id']} {r['subject']}: {r['score_old']}→{body.score}")
    return {"ok": True, "engine": evaluate(_con)}

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
