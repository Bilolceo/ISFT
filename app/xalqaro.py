"""Xalqaro hamkorlik — ish jarayonlari (Xalqaro hamkorlik bo'limi). Batafsil: docs/xalqaro.md.

  * Hamkorlik shartnomasi hayotiy sikli: qoralama → yuridik ko'rik (Yuridik bo'lim) → rektor imzosi → amalda → tugamoqda
    (90 va 30 kun oldin ogohlantirish) → uzaytirish (yangi qoralama, eski shartnomaga bog'langan) yoki muddati tugagan.
    Yuridik e'tirozi yoki rektor qaytarishi → «qaytarildi» (tahrir va qayta yuborish). Imzolangan shartnoma hamkorlar reyestriga
    (partners — panel, agentlar, Portal ma'lumot to'plami) avtomatik yoziladi. Har shartnomada tadbirlar va KPI: reja va fakt
    (almashinuv, qo'shma dasturlar).
  * Akademik mobillik (almashinuv): tanlov e'loni (mezonlar: oxirgi yakunlangan semestr GPA — reyting keshidan, akademik qarz yo'qligi
    — academic_rules.debt_where, til sertifikati bali) → arizalar (xodim kiritadi yoki talaba kabinetidan) → avtomatik muvofiqlik
    tekshiruvi → komissiya bali (suhbat, 0–15) → saralash (o'rinlar, zaxira) → jo'nash → qaytish → kredit tan olish (Akademik bo'lim navbati).
  * Xorijiy talabalar: viza va ro'yxatga olish muddatlari, 60/30 kun ogohlantirish.
  * Xorijiy delegatsiyalar jurnali: tashrif, mezbon, natija.
Ruxsatlar (serverda): Xalqaro bo'lim — hammasi; Yuridik bo'lim — shartnomalar va yuridik xulosa; rektor — imzo/qaytarish, jamlangan ko'rinish
(talaba ismlarisiz); ilmiy ishlar prorektori (kurator) — ko'rish va komissiya bali; Kuzatuv kengashi — faqat jamlangan; Akademik bo'lim —
faqat kredit tan olish navbati. Har bir murojaat audit jurnaliga (resurs "international") yoziladi.
"""
import datetime as dt, random
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
P = "/api/xalqaro"
RES = rbac.INTL

EDIT = ("xalqaro",)
LEGAL = ("yuridik",)
SIGN = ("rektor",)
COMMISSION = ("xalqaro", "prorektor_ilmiy")
NAMES = ("xalqaro", "prorektor_ilmiy")             # talaba ism-shariflari (arizalar, xorijiy talabalar)
CREDIT = ("akademik",)                               # faqat kredit tan olish navbati (INTL ruxsatisiz)
ALL = ("xalqaro", "prorektor_ilmiy", "yuridik", "rektor", "kengash", "akademik")

TABS = {
    "xalqaro": ["overview", "agreements", "exchange", "foreign", "delegations", "credits"],
    "prorektor_ilmiy": ["overview", "agreements", "exchange", "foreign", "delegations"],
    "yuridik": ["agreements", "overview"],
    "rektor": ["overview", "agreements", "exchange", "delegations"],
    "kengash": ["overview"],
    "akademik": ["credits"],
}

AG_ST = {"qoralama": "Qoralama", "yuridik": "Yuridik ko'rikda", "qaytarildi": "Qaytarildi", "imzoda": "Rektor imzosida",
         "faol": "Amalda", "tugagan": "Muddati tugagan", "uzaytirildi": "Uzaytirildi", "bekor": "Bekor qilingan"}
KINDS = ["Akademik almashinuv", "Erasmus+ KA171", "Qo'shma dastur (2+2)", "Ilmiy hamkorlik", "Memorandum"]
ACT_KINDS = {"almashinuv": "Talabalar/xodimlar almashinuvi", "qoshma_dastur": "Qo'shma dastur (qabul)", "ilmiy": "Qo'shma ilmiy loyiha/nashr",
             "tashrif": "Tashrif / ma'ruza", "boshqa": "Boshqa tadbir"}
APP_ST = {"ariza": "Ariza qabul qilindi", "mos_emas": "Mezonga mos emas", "saralandi": "Saralandi", "zaxira": "Zaxira",
          "rad": "Saralanmadi", "voz_kechdi": "Voz kechdi", "ketdi": "Mobillikda", "qaytdi": "Qaytdi"}
CALL_ST = {"ochiq": "Arizalar qabul qilinmoqda", "komissiya": "Komissiya ko'rigida", "yakunlangan": "Saralash yakunlangan"}
CREDIT_ST = {"kutilmoqda": "Akademik bo'limda", "tan_olindi": "To'liq tan olindi", "qisman": "Qisman tan olindi", "rad": "Tan olinmadi"}
WARN_90, WARN_30 = 90, 30
VISA_WARN, VISA_HIGH = 60, 30
LANG_MAX = 9.0           # til bali IELTS shkalasida (ekvivalent: B2 ≈ 5.5, C1 ≈ 6.5)
RESERVE = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS intl_agreements(id INTEGER PRIMARY KEY, partner_id INT, partner_name TEXT, country TEXT, kind TEXT, title TEXT,
  start TEXT, end TEXT, status TEXT, renew_of INT, kpi_exchange INT DEFAULT 0, kpi_joint INT DEFAULT 0, note TEXT DEFAULT '',
  legal_note TEXT, legal_by TEXT, legal_at TEXT, signed_by TEXT, signed_at TEXT, created_by INT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS intl_agreement_log(id INTEGER PRIMARY KEY, agreement_id INT, at TEXT, user_id INT, user_name TEXT, action TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_intl_aglog ON intl_agreement_log(agreement_id, id);
CREATE TABLE IF NOT EXISTS intl_activities(id INTEGER PRIMARY KEY, agreement_id INT, kind TEXT, title TEXT, date TEXT, count INT DEFAULT 0,
  note TEXT DEFAULT '', by_user INT, at TEXT);
CREATE INDEX IF NOT EXISTS ix_intl_act ON intl_activities(agreement_id);
CREATE TABLE IF NOT EXISTS intl_calls(id INTEGER PRIMARY KEY, title TEXT, agreement_id INT, host TEXT, country TEXT, seats INT,
  min_gpa REAL, lang_min REAL, lang_req TEXT, no_debts INT DEFAULT 1, min_course INT DEFAULT 2, deadline TEXT, mob_start TEXT, mob_end TEXT,
  status TEXT, created_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS intl_applications(id INTEGER PRIMARY KEY, call_id INT, student_id INT, channel TEXT, lang_cert TEXT, lang_score REAL,
  motivation TEXT DEFAULT '', created_at TEXT, gpa REAL, debts INT, eligible INT, elig_note TEXT, interview REAL, total REAL, rank INT,
  status TEXT, status_note TEXT DEFAULT '', departed TEXT, returned TEXT, credits_earned INT, transcript_note TEXT,
  credit_status TEXT, credits_recognized INT, credit_note TEXT, credit_by TEXT, credit_at TEXT, UNIQUE(call_id, student_id));
CREATE TABLE IF NOT EXISTS intl_foreign(id INTEGER PRIMARY KEY, full_name TEXT, country TEXT, program TEXT, course INT, passport TEXT,
  visa_type TEXT, visa_no TEXT, visa_expires TEXT, reg_expires TEXT, status TEXT, note TEXT DEFAULT '', updated_at TEXT);
CREATE TABLE IF NOT EXISTS intl_delegations(id INTEGER PRIMARY KEY, org TEXT, country TEXT, head TEXT, members INT, arrive TEXT, depart TEXT,
  purpose TEXT, agreement_id INT, host TEXT, status TEXT, outcome TEXT DEFAULT '', created_by INT, created_at TEXT);
"""

def _today(): return clock.today()
def _now(): return clock.now_iso()
def _d(s):
    try: return dt.date.fromisoformat(str(s)[:10])
    except Exception: return None

# =============================================================================================
# Ruxsat
# =============================================================================================
def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    k = c.role.key
    if k not in roles:
        rbac.audit(_con, c, action, RES, False, detail)
        raise AccessDenied(f"⛔ Xalqaro hamkorlik: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")
    if k in CREDIT:   # Akademik bo'limda INTL resursi yo'q — faqat kredit tan olish navbati (modul jadvali bo'yicha)
        rbac.audit(_con, c, action, RES, True, detail)
    else:
        rbac.require(_con, c, RES, action, detail)

def _bad(msg, code=400): raise HTTPException(code, msg)

def _ctx_of(request: Request) -> Ctx: return _ctx(request)

# =============================================================================================
# Shartnomalar
# =============================================================================================
def _log(aid, c: Ctx | None, action, note=""):
    _con.execute("INSERT INTO intl_agreement_log(agreement_id,at,user_id,user_name,action,note) VALUES(?,?,?,?,?,?)",
                 (aid, _now(), c.user["id"] if c else None, (c.title if c else "Tizim"), action, note))

def _sync_partner(a: dict):
    """Amaldagi shartnoma → hamkorlar reyestri (partners). Panel, agentlar, desks va Portal shu jadvaldan o'qiydi."""
    st = "faol" if a["status"] == "faol" else "muddati tugagan" if a["status"] in ("tugagan", "uzaytirildi", "bekor") else None
    if st is None: return
    if a["partner_id"] and db.one(_con, "SELECT 1 x FROM partners WHERE id=?", (a["partner_id"],)):
        if a["status"] == "uzaytirildi": return   # yangi shartnoma o'sha hamkor yozuvini yangilaydi
        _con.execute("UPDATE partners SET name=?, country=?, kind=?, signed=?, expires=?, status=? WHERE id=?",
                     (a["partner_name"], a["country"], a["kind"], a["start"], a["end"], st, a["partner_id"]))
    elif a["status"] == "faol":
        pid = _con.execute("INSERT INTO partners(name,country,kind,signed,expires,status,students_exchanged) VALUES(?,?,?,?,?,?,0)",
                           (a["partner_name"], a["country"], a["kind"], a["start"], a["end"], st)).lastrowid
        _con.execute("UPDATE intl_agreements SET partner_id=? WHERE id=?", (pid, a["id"]))

def sweep():
    """Muddati o'tgan amaldagi shartnomalar → «tugagan» (har o'qishda; idempotent)."""
    td = _today().isoformat()
    rows = db.rows(_con, "SELECT * FROM intl_agreements WHERE status='faol' AND end < ?", (td,))
    for a in rows:
        _con.execute("UPDATE intl_agreements SET status='tugagan', updated_at=? WHERE id=?", (_now(), a["id"]))
        _log(a["id"], None, "Muddati tugadi", f"tugash sanasi {a['end']}")
        a["status"] = "tugagan"; _sync_partner(a)
    if rows: _con.commit()

def _kpi_fact(aid):
    r = db.rows(_con, "SELECT kind, COALESCE(SUM(count),0) n FROM intl_activities WHERE agreement_id=? GROUP BY kind", (aid,))
    m = {x["kind"]: x["n"] for x in r}
    return {"exchange": m.get("almashinuv", 0), "joint": m.get("qoshma_dastur", 0), "activities": sum(1 for _ in r)}

def _decorate(a: dict) -> dict:
    td = _today()
    e = _d(a.get("end"))
    a["days_left"] = (e - td).days if e else None
    a["status_label"] = AG_ST.get(a["status"], a["status"])
    a["alert"] = None
    if a["status"] == "faol" and a["days_left"] is not None:
        if a["days_left"] <= WARN_30: a["alert"] = "high"
        elif a["days_left"] <= WARN_90: a["alert"] = "mid"
    a["renewal"] = db.one(_con, "SELECT id, status FROM intl_agreements WHERE renew_of=? AND status NOT IN ('bekor') ORDER BY id DESC LIMIT 1", (a["id"],))
    f = _kpi_fact(a["id"])
    a["kpi"] = {"exchange_plan": a["kpi_exchange"] or 0, "exchange_fact": f["exchange"], "joint_plan": a["kpi_joint"] or 0, "joint_fact": f["joint"]}
    return a

def _ag(aid) -> dict:
    a = db.one(_con, "SELECT * FROM intl_agreements WHERE id=?", (aid,))
    if not a: _bad("Shartnoma topilmadi", 404)
    return a

def agreements_list(status=""):
    sweep()
    w, args = "", ()
    if status == "tugamoqda":
        w, args = " WHERE status='faol' AND end <= ?", ((_today() + dt.timedelta(days=WARN_90)).isoformat(),)
    elif status == "navbat":
        w = " WHERE status IN ('yuridik','imzoda','qaytarildi','qoralama')"
    elif status:
        w, args = " WHERE status=?", (status,)
    rows = db.rows(_con, f"SELECT * FROM intl_agreements{w} ORDER BY CASE status WHEN 'imzoda' THEN 0 WHEN 'yuridik' THEN 1 WHEN 'qaytarildi' THEN 2 "
                          f"WHEN 'qoralama' THEN 3 WHEN 'faol' THEN 4 ELSE 5 END, end", args)
    return [_decorate(a) for a in rows]

# =============================================================================================
# Akademik mobillik
# =============================================================================================
def _student(sid=None, hemis=None):
    q = """SELECT s.id, s.hemis_id, s.full_name, s.status, s.study_form, g.name grp, g.course, f.name faculty FROM students s
           JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id WHERE """
    return db.one(_con, q + ("s.id=?" if sid else "s.hemis_id=?"), (sid or hemis,))

def eligibility(call: dict, sid: int, lang_score) -> dict:
    s = _student(sid)
    notes = []
    r = db.one(_con, "SELECT gpa FROM rating_cache WHERE student_id=? AND semester=?", (sid, AR.RATING_SEMESTER))
    gpa = round(r["gpa"], 2) if r and r["gpa"] is not None else None
    debts = db.one(_con, f"SELECT COUNT(*) n FROM grades g WHERE g.student_id=? AND {AR.debt_where('g')}", (sid,))["n"]
    if not s or s["status"] != "faol": notes.append("faol talaba emas")
    elif (s["course"] or 0) < (call["min_course"] or 1): notes.append(f"kamida {call['min_course']}-kurs talabasi bo'lishi kerak")
    if gpa is None: notes.append("yakunlangan semestr GPA yo'q")
    elif gpa < (call["min_gpa"] or 0): notes.append(f"GPA {gpa:.2f} < {call['min_gpa']:.2f}")
    if call["no_debts"] and debts: notes.append(f"{debts} ta akademik qarz")
    if lang_score is None: notes.append("til sertifikati bali kiritilmagan")
    elif lang_score < (call["lang_min"] or 0): notes.append(f"til bali {lang_score} < {call['lang_min']}")
    return {"gpa": gpa, "debts": debts, "eligible": int(not notes), "note": "; ".join(notes) or "barcha mezonlarga mos"}

def _total(gpa, lang, interview):
    if gpa is None: return None
    return round(gpa / 5 * 60 + min((lang or 0) / LANG_MAX, 1) * 25 + (interview or 0), 1)

def _rerank(cid):
    """Muvofiq arizalar: jami ball bo'yicha o'rin (teng bo'lsa GPA, keyin ariza vaqti)."""
    apps = db.rows(_con, "SELECT id, gpa, lang_score, interview, eligible, created_at FROM intl_applications WHERE call_id=?", (cid,))
    for a in apps:
        _con.execute("UPDATE intl_applications SET total=? WHERE id=?", (_total(a["gpa"], a["lang_score"], a["interview"]) if a["eligible"] else None, a["id"]))
    ok = sorted([a for a in apps if a["eligible"]], key=lambda a: (-(_total(a["gpa"], a["lang_score"], a["interview"]) or 0), -(a["gpa"] or 0), a["created_at"]))
    _con.execute("UPDATE intl_applications SET rank=NULL WHERE call_id=?", (cid,))
    for i, a in enumerate(ok, 1): _con.execute("UPDATE intl_applications SET rank=? WHERE id=?", (i, a["id"]))

def _call(cid) -> dict:
    c = db.one(_con, "SELECT * FROM intl_calls WHERE id=?", (cid,))
    if not c: _bad("Tanlov topilmadi", 404)
    return c

def _app(aid) -> dict:
    a = db.one(_con, "SELECT * FROM intl_applications WHERE id=?", (aid,))
    if not a: _bad("Ariza topilmadi", 404)
    return a

def add_application(call: dict, sid: int, lang_cert: str, lang_score, motivation: str, channel: str) -> dict:
    if call["status"] != "ochiq": raise ValueError("Bu tanlov bo'yicha arizalar qabul qilinmaydi")
    if channel == "portal" and call["deadline"] < _today().isoformat(): raise ValueError("Ariza topshirish muddati o'tgan")
    if db.one(_con, "SELECT 1 x FROM intl_applications WHERE call_id=? AND student_id=?", (call["id"], sid)):
        raise ValueError("Bu talaba ushbu tanlovga allaqachon ariza bergan")
    e = eligibility(call, sid, lang_score)
    aid = _con.execute("""INSERT INTO intl_applications(call_id,student_id,channel,lang_cert,lang_score,motivation,created_at,gpa,debts,eligible,elig_note,status)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (call["id"], sid, channel, lang_cert, lang_score, motivation, _now(), e["gpa"], e["debts"], e["eligible"], e["note"],
                                              "ariza" if e["eligible"] else "mos_emas")).lastrowid
    _rerank(call["id"]); _con.commit()
    return {"id": aid, **e}

def _app_rows(cid, names=True):
    rows = db.rows(_con, """SELECT a.*, s.full_name, s.hemis_id, g.name grp, g.course, f.name faculty FROM intl_applications a
        JOIN students s ON s.id=a.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
        WHERE a.call_id=? ORDER BY a.rank IS NULL, a.rank, a.created_at""", (cid,))
    for r in rows:
        r["status_label"] = APP_ST.get(r["status"], r["status"])
        r["credit_label"] = CREDIT_ST.get(r["credit_status"] or "", "")
        if not names:
            for k in ("full_name", "hemis_id", "motivation", "grp"): r.pop(k, None)
    return rows

def _call_stats(cid):
    r = db.rows(_con, "SELECT status, COUNT(*) n FROM intl_applications WHERE call_id=? GROUP BY status", (cid,))
    m = {x["status"]: x["n"] for x in r}
    m["jami"] = sum(m.values())
    return m

# =============================================================================================
# Xorijiy talabalar, delegatsiyalar
# =============================================================================================
def _foreign_dec(f):
    td = _today()
    for k in ("visa", "reg"):
        d = _d(f[f"{k}_expires"])
        f[f"{k}_days"] = (d - td).days if d else None
    days = [x for x in (f["visa_days"], f["reg_days"]) if x is not None]
    m = min(days) if days else None
    f["alert"] = None if f["status"] != "o'qimoqda" or m is None else "over" if m < 0 else "high" if m <= VISA_HIGH else "mid" if m <= VISA_WARN else None
    return f

def foreign_list():
    return [_foreign_dec(f) for f in db.rows(_con, "SELECT * FROM intl_foreign ORDER BY status!='o''qimoqda', MIN(visa_expires, reg_expires)")]

def delegations_list():
    rows = db.rows(_con, """SELECT d.*, a.partner_name agreement FROM intl_delegations d LEFT JOIN intl_agreements a ON a.id=d.agreement_id
                            ORDER BY d.arrive DESC""")
    td = _today().isoformat()
    for d in rows: d["upcoming"] = d["arrive"] >= td and d["status"] == "rejalashtirilgan"
    return rows

# =============================================================================================
# Umumiy ko'rinish (barcha INTL lavozimlari; talaba ismlarisiz)
# =============================================================================================
def overview():
    ags = agreements_list()
    st = {}
    for a in ags: st[a["status"]] = st.get(a["status"], 0) + 1
    act = [a for a in ags if a["status"] == "faol"]
    exp = [{k: a[k] for k in ("id", "partner_name", "country", "kind", "end", "days_left", "alert")} | {"renewal": a["renewal"]}
           for a in act if a["alert"]]
    calls = db.rows(_con, "SELECT * FROM intl_calls ORDER BY id DESC")
    for c in calls: c["stats"] = _call_stats(c["id"]); c["status_label"] = CALL_ST.get(c["status"], c["status"])
    fl = foreign_list()
    abroad = db.one(_con, "SELECT COUNT(*) n FROM intl_applications WHERE status='ketdi'")["n"]
    credit_wait = db.one(_con, "SELECT COUNT(*) n FROM intl_applications WHERE credit_status='kutilmoqda'")["n"]
    td = _today().isoformat()
    return {
        "today": td,
        "agreements": {"by_status": [{"status": k, "label": AG_ST.get(k, k), "n": v} for k, v in st.items()], "active": len(act),
                       "expiring": sorted(exp, key=lambda x: x["days_left"]), "queue": st.get("yuridik", 0) + st.get("imzoda", 0),
                       "countries": len({a["country"] for a in act})},
        "kpi": {"exchange_plan": sum(a["kpi"]["exchange_plan"] for a in act), "exchange_fact": sum(a["kpi"]["exchange_fact"] for a in act),
                "joint_plan": sum(a["kpi"]["joint_plan"] for a in act), "joint_fact": sum(a["kpi"]["joint_fact"] for a in act),
                "no_activity": sum(1 for a in act if not a["kpi"]["exchange_fact"] and not a["kpi"]["joint_fact"])},
        "mobility": {"calls": [{k: c[k] for k in ("id", "title", "country", "seats", "deadline", "status", "status_label", "stats")} for c in calls],
                     "abroad": abroad, "credit_wait": credit_wait},
        "foreign": {"total": sum(1 for f in fl if f["status"] == "o'qimoqda"), "alerts": sum(1 for f in fl if f["alert"] in ("high", "over")),
                    "warn": sum(1 for f in fl if f["alert"] == "mid"),
                    "by_country": sorted(({"country": k, "n": v} for k, v in _count(f["country"] for f in fl if f["status"] == "o'qimoqda").items()), key=lambda x: -x["n"])},
        "delegations": {"upcoming": db.one(_con, "SELECT COUNT(*) n FROM intl_delegations WHERE arrive>=? AND status='rejalashtirilgan'", (td,))["n"],
                        "year": db.one(_con, "SELECT COUNT(*) n FROM intl_delegations WHERE status='o''tkazildi' AND arrive>=?", (f"{_today().year}-01-01",))["n"]},
    }

def _count(it):
    m = {}
    for x in it: m[x] = m.get(x, 0) + 1
    return m

def alerts(c: Ctx) -> list:
    """Panel uchun ogohlantirishlar (ixtiyoriy chaqiriladi)."""
    if c.role.key not in ("xalqaro", "prorektor_ilmiy", "rektor"): return []
    out = []
    for a in agreements_list():
        if a["alert"] == "high" and not a["renewal"]:
            out.append({"level": "mid", "area": "Xalqaro", "text": f"{a['partner_name']} bilan shartnoma {a['days_left']} kunda tugaydi — uzaytirish boshlanmagan"})
    return out

# =============================================================================================
# Seed (bo'sh bo'lsa — demo; sintetik)
# =============================================================================================
FOREIGN = [("Nurlanov Aydos", "Qozog'iston"), ("Rahmonov Firuz", "Tojikiston"), ("Ataýew Merdan", "Turkmaniston"), ("Sharma Rohan", "Hindiston"),
           ("Park Min-jun", "Janubiy Koreya"), ("Toktogulov Adilet", "Qirg'iziston"), ("Yılmaz Emre", "Turkiya"), ("Ahmadi Sahar", "Afg'oniston"),
           ("Bekova Aruzhan", "Qozog'iston"), ("Kumar Priya", "Hindiston")]

def seed(con):
    if con.execute("SELECT COUNT(*) FROM intl_agreements").fetchone()[0]: return 0
    global _con
    old = _con; _con = con
    try: return _seed(con)
    finally: _con = old

def _seed(con):
    R = random.Random(2026)
    td = clock.today(); now = clock.now_iso()
    rows = db.rows(con, "SELECT * FROM partners ORDER BY id")
    ids = {}
    for p in rows:
        st = "faol" if p["status"] == "faol" and p["expires"] >= td.isoformat() else "tugagan"
        kx = {"Erasmus+ KA171": 10, "Akademik almashinuv": 8, "Qo'shma dastur (2+2)": 6, "Ilmiy hamkorlik": 2}.get(p["kind"], 3)
        kj = 15 if p["kind"] == "Qo'shma dastur (2+2)" else 0
        aid = con.execute("""INSERT INTO intl_agreements(partner_id,partner_name,country,kind,title,start,end,status,kpi_exchange,kpi_joint,
            legal_note,legal_by,legal_at,signed_by,signed_at,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p["id"], p["name"], p["country"], p["kind"], f"{p['kind']} bo'yicha hamkorlik shartnomasi", p["signed"], p["expires"], st, kx, kj,
             "Yuridik e'tiroz yo'q", "Yuridik bo'lim", p["signed"], "Rektor", p["signed"], 10, p["signed"], now)).lastrowid
        ids[p["id"]] = aid
        if st == "tugagan" and p["status"] == "faol": con.execute("UPDATE partners SET status='muddati tugagan' WHERE id=?", (p["id"],))
        con.execute("INSERT INTO intl_agreement_log(agreement_id,at,user_name,action,note) VALUES(?,?,?,?,?)", (aid, p["signed"], "Rektor", "Imzolandi", "reyestrdan ko'chirildi"))
        n = p["students_exchanged"] or 0
        if n:
            a1 = R.randint(0, n)
            for cnt in (a1, n - a1):
                if cnt: con.execute("INSERT INTO intl_activities(agreement_id,kind,title,date,count,by_user,at) VALUES(?,?,?,?,?,?,?)",
                                    (aid, "almashinuv", "Semestrlik talabalar almashinuvi", (td - dt.timedelta(days=R.randint(30, 500))).isoformat(), cnt, 10, now))
        if kj: con.execute("INSERT INTO intl_activities(agreement_id,kind,title,date,count,by_user,at) VALUES(?,?,?,?,?,?,?)",
                           (aid, "qoshma_dastur", "2+2 dasturiga qabul", (td - dt.timedelta(days=R.randint(60, 400))).isoformat(), R.randint(4, 14), 10, now))
        if p["kind"] == "Ilmiy hamkorlik" and R.random() < .7:
            con.execute("INSERT INTO intl_activities(agreement_id,kind,title,date,count,by_user,at) VALUES(?,?,?,?,?,?,?)",
                        (aid, "ilmiy", "Qo'shma maqola (Scopus)", (td - dt.timedelta(days=R.randint(30, 300))).isoformat(), 1, 10, now))
    # navbatdagi shartnomalar: qoralama, yuridik ko'rikda, rektor imzosida (muddati tugaganining uzaytirilishi)
    expired = db.one(con, "SELECT id, partner_id, partner_name, country, kind FROM intl_agreements WHERE status='tugagan' ORDER BY end DESC LIMIT 1")
    drafts = [("Hamkor OTM — Yaponiya (namuna)", "Yaponiya", "Akademik almashinuv", "qoralama", None, None),
              ("Hamkor OTM — Fransiya (namuna)", "Fransiya", "Erasmus+ KA171", "yuridik", None, None)]
    if expired: drafts.append((expired["partner_name"], expired["country"], expired["kind"], "imzoda", expired["id"], expired["partner_id"]))
    for name, cn, kind, st, ren, pid in drafts:
        s = td + dt.timedelta(days=14)
        aid = con.execute("""INSERT INTO intl_agreements(partner_id,partner_name,country,kind,title,start,end,status,renew_of,kpi_exchange,kpi_joint,
            legal_note,legal_by,legal_at,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, name, cn, kind, ("Shartnomani uzaytirish: " if ren else "") + f"{kind} bo'yicha hamkorlik shartnomasi", s.isoformat(),
             (s + dt.timedelta(days=1826)).isoformat(), st, ren, 6, 0,
             "Mos: 7-band (nizolarni hal qilish) aniqlashtirildi" if st == "imzoda" else None, "Yuridik bo'lim" if st == "imzoda" else None,
             now if st == "imzoda" else None, 10, now, now)).lastrowid
        con.execute("INSERT INTO intl_agreement_log(agreement_id,at,user_id,user_name,action,note) VALUES(?,?,?,?,?,?)", (aid, now, 10, "Xalqaro hamkorlik bo'limi", "Qoralama yaratildi", ""))
        if st in ("yuridik", "imzoda"):
            con.execute("INSERT INTO intl_agreement_log(agreement_id,at,user_id,user_name,action,note) VALUES(?,?,?,?,?,?)", (aid, now, 10, "Xalqaro hamkorlik bo'limi", "Yuridik ko'rikka yuborildi", ""))
        if st == "imzoda":
            con.execute("INSERT INTO intl_agreement_log(agreement_id,at,user_name,action,note) VALUES(?,?,?,?,?)", (aid, now, "Yuridik bo'lim", "Yuridik xulosa: mos", "7-band aniqlashtirildi"))
    # tanlovlar
    def ag_of(country):
        r = db.one(con, "SELECT id, partner_name FROM intl_agreements WHERE country=? AND status='faol' ORDER BY id LIMIT 1", (country,))
        return (r["id"], r["partner_name"]) if r else (None, f"Hamkor OTM — {country}")
    pool = [r["id"] for r in db.rows(con, f"""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id JOIN rating_cache rc ON rc.student_id=s.id AND rc.semester={AR.RATING_SEMESTER}
        WHERE s.status='faol' AND g.course BETWEEN 2 AND 3 AND s.level='bakalavr' AND rc.gpa >= 3.0 ORDER BY s.id""")] if _has(con, "rating_cache") else []
    R.shuffle(pool)
    calls = [("Erasmus+ KA171: bahorgi semestr mobilligi", "Polsha", 4, 3.5, 5.5, "IELTS 5.5 yoki ekvivalent (B2)", 21, 90, 240, "ochiq", 11),
             ("Akademik almashinuv: kuzgi semestr", "Latviya", 3, 3.5, 5.5, "IELTS 5.5 yoki ekvivalent (B2)", -150, -70, 80, "yakunlangan", 6),
             ("Akademik almashinuv: bahorgi semestr", "Turkiya", 3, 3.4, 5.0, "IELTS 5.0 yoki TÖMER B1", -330, -280, -130, "yakunlangan", 5)]
    for title, cn, seats, mg, ml, lr, dl, ms, me, st, napp in calls:
        agid, host = ag_of(cn)
        cid = con.execute("""INSERT INTO intl_calls(title,agreement_id,host,country,seats,min_gpa,lang_min,lang_req,no_debts,min_course,deadline,mob_start,mob_end,status,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,1,2,?,?,?,?,10,?)""", (title, agid, host, cn, seats, mg, ml, lr, (td + dt.timedelta(days=dl)).isoformat(),
            (td + dt.timedelta(days=ms)).isoformat(), (td + dt.timedelta(days=me)).isoformat(), st, now)).lastrowid
        call = db.one(con, "SELECT * FROM intl_calls WHERE id=?", (cid,))
        for i in range(napp):
            if not pool: break
            sid = pool.pop()
            lang = R.choice([5.0, 5.5, 6.0, 6.5, 7.0, 5.5, 6.0, 4.5])
            e = eligibility(call, sid, lang)
            con.execute("""INSERT INTO intl_applications(call_id,student_id,channel,lang_cert,lang_score,motivation,created_at,gpa,debts,eligible,elig_note,status,interview)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (cid, sid, R.choice(["xodim", "portal"]), "IELTS Academic", lang,
                "Mutaxassislik bo'yicha xorijiy tajriba va til ko'nikmasini oshirish maqsadida.", (td + dt.timedelta(days=dl - 20 + i)).isoformat() + "T10:00:00",
                e["gpa"], e["debts"], e["eligible"], e["note"], "ariza" if e["eligible"] else "mos_emas",
                None if st == "ochiq" else R.randint(8, 15)))
        if True:
            _rerank(cid)
            if st == "yakunlangan":
                _select(cid)
                sel = db.rows(con, "SELECT id FROM intl_applications WHERE call_id=? AND status='saralandi' ORDER BY rank", (cid,))
                for j, a in enumerate(sel):
                    if ms < 0:
                        con.execute("UPDATE intl_applications SET status='ketdi', departed=? WHERE id=?", ((td + dt.timedelta(days=ms)).isoformat(), a["id"]))
                    if me < 0:
                        cs = "tan_olindi" if j == 0 else "kutilmoqda"
                        con.execute("""UPDATE intl_applications SET status='qaytdi', returned=?, credits_earned=30, transcript_note=?, credit_status=?,
                            credits_recognized=?, credit_by=?, credit_at=? WHERE id=?""",
                            ((td + dt.timedelta(days=me)).isoformat(), "Hamkor OTM transkripti: 5 fan, 30 ECTS", cs, 30 if cs == "tan_olindi" else None,
                             "Akademik faoliyatni boshqarish bo'limi" if cs == "tan_olindi" else None, now if cs == "tan_olindi" else None, a["id"]))
    # xorijiy talabalar
    progs = ["Iqtisodiyot (bakalavr)", "Bank ishi (bakalavr)", "Moliya (magistratura)", "Turizm (bakalavr)", "Menejment (bakalavr)"]
    offs = [-4, 12, 26, 48, 75, 140, 190, 260, 320, 400]
    for (nm, cn), off in zip(FOREIGN, offs):
        con.execute("""INSERT INTO intl_foreign(full_name,country,program,course,passport,visa_type,visa_no,visa_expires,reg_expires,status,note,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (nm + " (namuna)", cn, R.choice(progs), R.randint(1, 4), "***" + str(R.randint(1000, 9999)),
            "O'qish vizasi (S-3)" if cn not in ("Qozog'iston", "Qirg'iziston", "Tojikiston") else "Vizasiz (ro'yxatga olish)",
            "—" if cn in ("Qozog'iston", "Qirg'iziston", "Tojikiston") else f"S3-{R.randint(100000, 999999)}",
            (td + dt.timedelta(days=off)).isoformat(), (td + dt.timedelta(days=min(off + R.randint(-10, 20), 365))).isoformat(), "o'qimoqda", "", now))
    # delegatsiyalar
    dels = [("Hamkor OTM — Polsha (namuna)", "Polsha", "Prorektor (xalqaro aloqalar)", 3, -40, "Erasmus+ KA171 monitoringi", "o'tkazildi",
             "Bahorgi mobillik uchun 4 o'rin kelishildi"),
            ("Hamkor OTM — Janubiy Koreya (namuna)", "Janubiy Koreya", "Xalqaro bo'lim direktori", 2, -12, "Shartnomani uzaytirish muzokarasi", "o'tkazildi",
             "Uzaytirish loyihasi tayyorlanadi; 2+2 dasturiga 10 o'rin"),
            ("Hamkor OTM — Germaniya (namuna)", "Germaniya", "Fakultet dekani", 4, 9, "Qo'shma magistratura dasturi taqdimoti", "rejalashtirilgan", ""),
            ("Xalqaro tashkilot vakolatxonasi (namuna)", "Xalqaro", "Loyiha koordinatori", 2, 23, "Grant loyihasi bo'yicha uchrashuv", "rejalashtirilgan", "")]
    for org, cn, head, m, off, purpose, st, outc in dels:
        a = db.one(con, "SELECT id FROM intl_agreements WHERE partner_name=? ORDER BY id LIMIT 1", (org,))
        d0 = td + dt.timedelta(days=off)
        con.execute("""INSERT INTO intl_delegations(org,country,head,members,arrive,depart,purpose,agreement_id,host,status,outcome,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,10,?)""", (org, cn, head, m, d0.isoformat(), (d0 + dt.timedelta(days=2)).isoformat(), purpose, a["id"] if a else None,
            "Ilmiy ishlar va innovatsiyalar bo'yicha prorektor", st, outc, now))
    con.commit()
    return 1

def _has(con, t): return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())

def _select(cid):
    """Saralash: muvofiq arizalar o'rni bo'yicha — o'rinlar soni «saralandi», keyingi RESERVE tasi «zaxira», qolgani «saralanmadi»."""
    call = _call(cid)
    ok = db.rows(_con, "SELECT id FROM intl_applications WHERE call_id=? AND eligible=1 AND status IN ('ariza','saralandi','zaxira','rad') ORDER BY rank", (cid,))
    out = {"saralandi": 0, "zaxira": 0, "rad": 0}
    for i, a in enumerate(ok):
        st = "saralandi" if i < call["seats"] else "zaxira" if i < call["seats"] + RESERVE else "rad"
        out[st] += 1
        _con.execute("UPDATE intl_applications SET status=?, status_note=? WHERE id=?", (st, "o'rin yetmadi" if st == "rad" else "", a["id"]))
    _con.execute("UPDATE intl_calls SET status='yakunlangan' WHERE id=?", (cid,))
    return out

def init(con):
    con.executescript(SCHEMA)
    con.commit()
    try:
        if seed(con): print("Xalqaro: demo ma'lumotlar yaratildi")
    except Exception as e:
        print("xalqaro seed:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

# =============================================================================================
# API: xodimlar
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: bo'lim")
    k = c.role.key
    return {"role": k, "tabs": TABS[k], "today": _today().isoformat(),
            "can": {"edit": k in EDIT, "legal": k in LEGAL, "sign": k in SIGN, "commission": k in COMMISSION, "names": k in NAMES, "credits": k in CREDIT},
            "labels": {"agreement": AG_ST, "application": APP_ST, "call": CALL_ST, "credit": CREDIT_ST, "activity": ACT_KINDS},
            "kinds": KINDS, "rules": {"warn90": WARN_90, "warn30": WARN_30, "visa_warn": VISA_WARN, "visa_high": VISA_HIGH,
                                      "score": "Jami = GPA/5 × 60 + til bali/9 × 25 + suhbat (0–15)", "reserve": RESERVE,
                                      "gpa": f"GPA — oxirgi yakunlangan semestr ({AR.SEMESTERS.get(AR.RATING_SEMESTER, '')}), reyting tizimi bilan bir xil"}}

def _tab(c: Ctx, tab: str, action: str):
    if c.role.key not in TABS or tab not in TABS[c.role.key]:
        guard(c, action, roles=())
    guard(c, action)

@router.get(P + "/overview")
def api_overview(request: Request):
    c = _ctx_of(request); _tab(c, "overview", "xalqaro: umumiy ko'rinish")
    return overview()

# ---- shartnomalar ----
class AgIn(BaseModel):
    partner_id: int | None = None
    partner_name: str = Field(..., min_length=3, max_length=200)
    country: str = Field(..., min_length=2, max_length=80)
    kind: str = Field(..., max_length=80)
    title: str = Field("", max_length=300)
    start: str
    end: str
    kpi_exchange: int = Field(0, ge=0, le=500)
    kpi_joint: int = Field(0, ge=0, le=500)
    note: str = Field("", max_length=1000)

class NoteIn(BaseModel):
    note: str = Field("", max_length=1000)

class LegalIn(BaseModel):
    decision: str
    note: str = Field("", max_length=1000)

def _check_dates(b: AgIn):
    s, e = _d(b.start), _d(b.end)
    if not s or not e: _bad("Sanalarni YYYY-MM-DD ko'rinishida kiriting")
    if e <= s: _bad("Tugash sanasi boshlanishidan keyin bo'lishi kerak")
    if (e - s).days > 3660: _bad("Shartnoma muddati 10 yildan oshmasligi kerak")

@router.get(P + "/agreements")
def api_agreements(request: Request, status: str = ""):
    c = _ctx_of(request); _tab(c, "agreements", "xalqaro: shartnomalar reyestri")
    return {"items": agreements_list(status)}

@router.get(P + "/agreements/{aid}")
def api_agreement(aid: int, request: Request):
    c = _ctx_of(request); _tab(c, "agreements", "xalqaro: shartnoma"); sweep()
    a = _decorate(_ag(aid))
    a["log"] = db.rows(_con, "SELECT at, user_name, action, note FROM intl_agreement_log WHERE agreement_id=? ORDER BY id DESC", (aid,))
    a["activities"] = db.rows(_con, "SELECT id, kind, title, date, count, note FROM intl_activities WHERE agreement_id=? ORDER BY date DESC", (aid,))
    for x in a["activities"]: x["kind_label"] = ACT_KINDS.get(x["kind"], x["kind"])
    a["previous"] = db.one(_con, "SELECT id, start, end, status FROM intl_agreements WHERE id=?", (a["renew_of"],)) if a["renew_of"] else None
    return a

@router.post(P + "/agreements")
def api_ag_new(body: AgIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: shartnoma qoralamasi", EDIT, body.partner_name[:80])
    _check_dates(body)
    if body.partner_id and not db.one(_con, "SELECT 1 x FROM partners WHERE id=?", (body.partner_id,)): _bad("Hamkor topilmadi")
    now = _now()
    aid = _con.execute("""INSERT INTO intl_agreements(partner_id,partner_name,country,kind,title,start,end,status,kpi_exchange,kpi_joint,note,created_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,'qoralama',?,?,?,?,?,?)""", (body.partner_id, body.partner_name.strip(), body.country.strip(), body.kind, body.title.strip() or f"{body.kind} bo'yicha hamkorlik shartnomasi",
        body.start, body.end, body.kpi_exchange, body.kpi_joint, body.note.strip(), c.user["id"], now, now)).lastrowid
    _log(aid, c, "Qoralama yaratildi"); _con.commit()
    return {"ok": True, "id": aid}

@router.put(P + "/agreements/{aid}")
def api_ag_edit(aid: int, body: AgIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: shartnomani tahrirlash", EDIT, f"#{aid}")
    a = _ag(aid)
    if a["status"] not in ("qoralama", "qaytarildi"): _bad("Faqat qoralama yoki qaytarilgan shartnoma tahrirlanadi")
    _check_dates(body)
    _con.execute("""UPDATE intl_agreements SET partner_name=?, country=?, kind=?, title=?, start=?, end=?, kpi_exchange=?, kpi_joint=?, note=?, updated_at=? WHERE id=?""",
                 (body.partner_name.strip(), body.country.strip(), body.kind, body.title.strip() or a["title"], body.start, body.end, body.kpi_exchange, body.kpi_joint,
                  body.note.strip(), _now(), aid))
    _log(aid, c, "Tahrirlandi"); _con.commit()
    return {"ok": True}

def _move(aid, c, frm, to, action, note="", extra=None):
    a = _ag(aid)
    if a["status"] not in frm: _bad(f"Bu amal «{AG_ST.get(a['status'], a['status'])}» holatidagi shartnoma uchun mumkin emas", 409)
    sets, args = ["status=?", "updated_at=?"], [to, _now()]
    for k, v in (extra or {}).items(): sets.append(f"{k}=?"); args.append(v)
    _con.execute(f"UPDATE intl_agreements SET {', '.join(sets)} WHERE id=?", (*args, aid))
    _log(aid, c, action, note)
    return a

@router.post(P + "/agreements/{aid}/submit")
def api_ag_submit(aid: int, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: yuridik ko'rikka yuborish", EDIT, f"#{aid}")
    _move(aid, c, ("qoralama", "qaytarildi"), "yuridik", "Yuridik ko'rikka yuborildi"); _con.commit()
    return {"ok": True, "status": "yuridik"}

@router.post(P + "/agreements/{aid}/legal")
def api_ag_legal(aid: int, body: LegalIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: yuridik xulosa", LEGAL, f"#{aid} → {body.decision}")
    if body.decision not in ("mos", "etiroz"): _bad("Xulosa: «mos» yoki «etiroz»")
    if body.decision == "etiroz" and len(body.note.strip()) < 5: _bad("E'tiroz uchun izoh yozing (kamida 5 belgi)")
    to = "imzoda" if body.decision == "mos" else "qaytarildi"
    _move(aid, c, ("yuridik",), to, "Yuridik xulosa: " + ("mos" if to == "imzoda" else "e'tiroz"), body.note.strip(),
          {"legal_note": body.note.strip() or ("E'tiroz yo'q" if to == "imzoda" else ""), "legal_by": c.title, "legal_at": _now()})
    _con.commit()
    return {"ok": True, "status": to}

@router.post(P + "/agreements/{aid}/sign")
def api_ag_sign(aid: int, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: shartnomani imzolash", SIGN, f"#{aid}")
    a = _ag(aid)
    if a["status"] != "imzoda": _bad("Faqat yuridik ko'rikdan o'tgan shartnoma imzolanadi", 409)
    if _d(a["end"]) < _today(): _bad("Tugash sanasi o'tib ketgan — shartnomani qaytaring va sanani tuzating", 409)
    _move(aid, c, ("imzoda",), "faol", "Imzolandi", "", {"signed_by": c.title, "signed_at": _now()})
    a = _ag(aid)
    if a["renew_of"]:
        old = _ag(a["renew_of"])
        if not a["partner_id"] and old["partner_id"]:
            _con.execute("UPDATE intl_agreements SET partner_id=? WHERE id=?", (old["partner_id"], aid)); a["partner_id"] = old["partner_id"]
        if old["status"] in ("faol", "tugagan"):
            _con.execute("UPDATE intl_agreements SET status='uzaytirildi', updated_at=? WHERE id=?", (_now(), old["id"]))
            _log(old["id"], c, "Uzaytirildi", f"yangi shartnoma #{aid}")
    _sync_partner(a); _con.commit()
    return {"ok": True, "status": "faol", "partner_id": _ag(aid)["partner_id"]}

@router.post(P + "/agreements/{aid}/return")
def api_ag_return(aid: int, body: NoteIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: shartnomani qaytarish", SIGN, f"#{aid}")
    if len(body.note.strip()) < 5: _bad("Qaytarish sababini yozing (kamida 5 belgi)")
    _move(aid, c, ("imzoda", "yuridik"), "qaytarildi", "Rektor qaytardi", body.note.strip()); _con.commit()
    return {"ok": True, "status": "qaytarildi"}

@router.post(P + "/agreements/{aid}/cancel")
def api_ag_cancel(aid: int, body: NoteIn, request: Request):
    c = _ctx_of(request)
    a = _ag(aid)
    if a["status"] == "faol":
        guard(c, "xalqaro: amaldagi shartnomani bekor qilish", SIGN, f"#{aid}")
        if len(body.note.strip()) < 5: _bad("Bekor qilish sababini yozing")
    else:
        guard(c, "xalqaro: qoralamani bekor qilish", EDIT, f"#{aid}")
    _move(aid, c, ("qoralama", "qaytarildi", "faol"), "bekor", "Bekor qilindi", body.note.strip())
    a = _ag(aid)
    if a["partner_id"] and not db.one(_con, "SELECT 1 x FROM intl_agreements WHERE partner_id=? AND status='faol' AND id!=?", (a["partner_id"], aid)):
        _sync_partner(a)
    _con.commit()
    return {"ok": True, "status": "bekor"}

@router.post(P + "/agreements/{aid}/renew")
def api_ag_renew(aid: int, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: shartnomani uzaytirish", EDIT, f"#{aid}")
    a = _ag(aid)
    if a["status"] not in ("faol", "tugagan"): _bad("Faqat amaldagi yoki muddati tugagan shartnoma uzaytiriladi", 409)
    r = db.one(_con, "SELECT id FROM intl_agreements WHERE renew_of=? AND status NOT IN ('bekor')", (aid,))
    if r: _bad(f"Uzaytirish allaqachon boshlangan (#{r['id']})", 409)
    s = max(_d(a["end"]) + dt.timedelta(days=1), _today())
    now = _now()
    nid = _con.execute("""INSERT INTO intl_agreements(partner_id,partner_name,country,kind,title,start,end,status,renew_of,kpi_exchange,kpi_joint,note,created_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,'qoralama',?,?,?,?,?,?,?)""", (a["partner_id"], a["partner_name"], a["country"], a["kind"], "Shartnomani uzaytirish: " + (a["title"] or ""),
        s.isoformat(), (s + dt.timedelta(days=1826)).isoformat(), aid, a["kpi_exchange"], a["kpi_joint"], "", c.user["id"], now, now)).lastrowid
    _log(nid, c, "Qoralama yaratildi", f"#{aid} shartnomasini uzaytirish"); _log(aid, c, "Uzaytirish boshlandi", f"yangi qoralama #{nid}")
    _con.commit()
    return {"ok": True, "id": nid}

class ActIn(BaseModel):
    kind: str
    title: str = Field(..., min_length=3, max_length=200)
    date: str
    count: int = Field(0, ge=0, le=1000)
    note: str = Field("", max_length=600)

@router.post(P + "/agreements/{aid}/activities")
def api_act_new(aid: int, body: ActIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: shartnoma tadbiri", EDIT, f"#{aid} · {body.kind}")
    a = _ag(aid)
    if a["status"] not in ("faol", "tugagan", "uzaytirildi"): _bad("Tadbir faqat imzolangan shartnomaga yoziladi", 409)
    if body.kind not in ACT_KINDS: _bad("Noto'g'ri tadbir turi")
    if not _d(body.date) or _d(body.date) > _today(): _bad("Tadbir sanasi bugundan keyin bo'lmasligi kerak")
    tid = _con.execute("INSERT INTO intl_activities(agreement_id,kind,title,date,count,note,by_user,at) VALUES(?,?,?,?,?,?,?,?)",
                       (aid, body.kind, body.title.strip(), body.date, body.count, body.note.strip(), c.user["id"], _now())).lastrowid
    if body.kind == "almashinuv" and a["partner_id"]:
        _con.execute("UPDATE partners SET students_exchanged=COALESCE(students_exchanged,0)+? WHERE id=?", (body.count, a["partner_id"]))
    _log(aid, c, "Tadbir qo'shildi", f"{ACT_KINDS[body.kind]}: {body.title.strip()[:80]} ({body.count})"); _con.commit()
    return {"ok": True, "id": tid}

# ---- akademik mobillik ----
class CallIn(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    agreement_id: int | None = None
    host: str = Field("", max_length=200)
    country: str = Field(..., min_length=2, max_length=80)
    seats: int = Field(..., ge=1, le=100)
    min_gpa: float = Field(3.5, ge=0, le=5)
    lang_min: float = Field(5.5, ge=0, le=9)
    lang_req: str = Field("IELTS 5.5 yoki ekvivalent (B2)", max_length=200)
    no_debts: bool = True
    min_course: int = Field(2, ge=1, le=4)
    deadline: str
    mob_start: str
    mob_end: str

class AppIn(BaseModel):
    student_id: int | None = None
    hemis_id: str = ""
    lang_cert: str = Field("IELTS Academic", max_length=120)
    lang_score: float | None = Field(None, ge=0, le=9)
    motivation: str = Field("", max_length=2000)

class ScoreIn(BaseModel):
    interview: float = Field(..., ge=0, le=15)

class DepartIn(BaseModel):
    date: str

class ReturnIn(BaseModel):
    date: str
    credits_earned: int = Field(..., ge=0, le=90)
    transcript_note: str = Field("", max_length=600)

class CreditIn(BaseModel):
    decision: str
    credits_recognized: int = Field(0, ge=0, le=90)
    note: str = Field("", max_length=1000)

@router.get(P + "/calls")
def api_calls(request: Request):
    c = _ctx_of(request); _tab(c, "exchange", "xalqaro: mobillik tanlovlari")
    rows = db.rows(_con, "SELECT * FROM intl_calls ORDER BY status='yakunlangan', deadline DESC")
    for r in rows: r["stats"] = _call_stats(r["id"]); r["status_label"] = CALL_ST.get(r["status"], r["status"])
    ags = db.rows(_con, "SELECT id, partner_name, country FROM intl_agreements WHERE status='faol' ORDER BY partner_name") if c.role.key in EDIT else []
    return {"items": rows, "agreements": ags}

@router.get(P + "/calls/{cid}")
def api_call(cid: int, request: Request):
    c = _ctx_of(request); _tab(c, "exchange", "xalqaro: tanlov arizalari", )
    call = _call(cid); call["status_label"] = CALL_ST.get(call["status"], call["status"]); call["stats"] = _call_stats(cid)
    names = c.role.key in NAMES
    call["applications"] = _app_rows(cid, names) if names else []
    call["names"] = names
    return call

@router.post(P + "/calls")
def api_call_new(body: CallIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: tanlov e'loni", EDIT, body.title[:80])
    d, s, e = _d(body.deadline), _d(body.mob_start), _d(body.mob_end)
    if not (d and s and e): _bad("Sanalarni YYYY-MM-DD ko'rinishida kiriting")
    if d < _today(): _bad("Ariza muddati o'tgan sana bo'lmasin")
    if not (d < s < e): _bad("Tartib: ariza muddati < mobillik boshlanishi < tugashi")
    host = body.host.strip()
    if body.agreement_id:
        a = db.one(_con, "SELECT partner_name, status FROM intl_agreements WHERE id=?", (body.agreement_id,))
        if not a or a["status"] != "faol": _bad("Tanlov faqat amaldagi shartnoma asosida e'lon qilinadi")
        host = host or a["partner_name"]
    cid = _con.execute("""INSERT INTO intl_calls(title,agreement_id,host,country,seats,min_gpa,lang_min,lang_req,no_debts,min_course,deadline,mob_start,mob_end,status,created_by,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'ochiq',?,?)""", (body.title.strip(), body.agreement_id, host or "—", body.country.strip(), body.seats, body.min_gpa, body.lang_min,
        body.lang_req.strip(), int(body.no_debts), body.min_course, body.deadline, body.mob_start, body.mob_end, c.user["id"], _now())).lastrowid
    _con.commit()
    return {"ok": True, "id": cid}

@router.post(P + "/calls/{cid}/applications")
def api_app_new(cid: int, body: AppIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: mobillik arizasi (xodim)", EDIT, f"tanlov #{cid} · {body.hemis_id or body.student_id}")
    s = _student(sid=body.student_id) if body.student_id else _student(hemis=body.hemis_id.strip()) if body.hemis_id.strip() else None
    if not s: _bad("Talaba topilmadi (HEMIS ID ni tekshiring)", 404)
    try: r = add_application(_call(cid), s["id"], body.lang_cert.strip(), body.lang_score, body.motivation.strip(), "xodim")
    except ValueError as e: _bad(str(e), 409)
    return {"ok": True, **r, "student": s["full_name"]}

@router.post(P + "/calls/{cid}/recheck")
def api_recheck(cid: int, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: mezonlarni qayta tekshirish", EDIT, f"tanlov #{cid}")
    call = _call(cid)
    if call["status"] == "yakunlangan": _bad("Saralash yakunlangan", 409)
    n = 0
    for a in db.rows(_con, "SELECT * FROM intl_applications WHERE call_id=? AND status IN ('ariza','mos_emas')", (cid,)):
        e = eligibility(call, a["student_id"], a["lang_score"])
        _con.execute("UPDATE intl_applications SET gpa=?, debts=?, eligible=?, elig_note=?, status=? WHERE id=?",
                     (e["gpa"], e["debts"], e["eligible"], e["note"], "ariza" if e["eligible"] else "mos_emas", a["id"])); n += 1
    _rerank(cid); _con.commit()
    return {"ok": True, "checked": n}

@router.post(P + "/calls/{cid}/close")
def api_call_close(cid: int, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: arizalar qabulini yopish", EDIT, f"tanlov #{cid}")
    call = _call(cid)
    if call["status"] != "ochiq": _bad("Tanlov ochiq emas", 409)
    _con.execute("UPDATE intl_calls SET status='komissiya' WHERE id=?", (cid,)); _con.commit()
    return {"ok": True, "status": "komissiya"}

@router.post(P + "/applications/{aid}/score")
def api_score(aid: int, body: ScoreIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: komissiya bali", COMMISSION, f"ariza #{aid} · {body.interview}")
    a = _app(aid)
    if _call(a["call_id"])["status"] == "yakunlangan": _bad("Saralash yakunlangan — ball o'zgarmaydi", 409)
    if not a["eligible"]: _bad("Mezonga mos bo'lmagan arizaga ball qo'yilmaydi", 409)
    _con.execute("UPDATE intl_applications SET interview=? WHERE id=?", (body.interview, aid))
    _rerank(a["call_id"]); _con.commit()
    return {"ok": True, "total": _app(aid)["total"], "rank": _app(aid)["rank"]}

@router.post(P + "/calls/{cid}/select")
def api_select(cid: int, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: saralash natijasi", EDIT, f"tanlov #{cid}")
    call = _call(cid)
    if call["status"] != "komissiya": _bad("Avval arizalar qabulini yoping (komissiya bosqichi)", 409)
    miss = db.one(_con, "SELECT COUNT(*) n FROM intl_applications WHERE call_id=? AND eligible=1 AND interview IS NULL", (cid,))["n"]
    if miss: _bad(f"{miss} ta muvofiq arizaga komissiya bali qo'yilmagan", 409)
    _rerank(cid); out = _select(cid); _con.commit()
    return {"ok": True, **out}

@router.post(P + "/applications/{aid}/withdraw")
def api_withdraw(aid: int, body: NoteIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: nomzod voz kechdi", EDIT, f"ariza #{aid}")
    a = _app(aid)
    if a["status"] not in ("saralandi", "zaxira"): _bad("Faqat saralangan yoki zaxiradagi nomzod", 409)
    _con.execute("UPDATE intl_applications SET status='voz_kechdi', status_note=? WHERE id=?", (body.note.strip() or "voz kechdi", aid))
    promoted = None
    if a["status"] == "saralandi":
        z = db.one(_con, "SELECT id FROM intl_applications WHERE call_id=? AND status='zaxira' ORDER BY rank LIMIT 1", (a["call_id"],))
        if z:
            _con.execute("UPDATE intl_applications SET status='saralandi', status_note='zaxiradan o''tkazildi' WHERE id=?", (z["id"],)); promoted = z["id"]
    _con.commit()
    return {"ok": True, "promoted": promoted}

@router.post(P + "/applications/{aid}/depart")
def api_depart(aid: int, body: DepartIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: mobillikka jo'nadi", EDIT, f"ariza #{aid}")
    a = _app(aid)
    if a["status"] != "saralandi": _bad("Faqat saralangan nomzod jo'naydi", 409)
    if not _d(body.date): _bad("Sana noto'g'ri")
    _con.execute("UPDATE intl_applications SET status='ketdi', departed=? WHERE id=?", (body.date, aid)); _con.commit()
    return {"ok": True}

@router.post(P + "/applications/{aid}/return")
def api_return(aid: int, body: ReturnIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: mobillikdan qaytdi", EDIT, f"ariza #{aid} · {body.credits_earned} kredit")
    a = _app(aid)
    if a["status"] != "ketdi": _bad("Faqat mobillikdagi talaba qaytadi", 409)
    r = _d(body.date)
    if not r or r < _d(a["departed"]): _bad("Qaytish sanasi jo'nashdan oldin bo'lmasin")
    _con.execute("""UPDATE intl_applications SET status='qaytdi', returned=?, credits_earned=?, transcript_note=?, credit_status='kutilmoqda' WHERE id=?""",
                 (body.date, body.credits_earned, body.transcript_note.strip(), aid))
    call = _call(a["call_id"])
    if call["agreement_id"]:
        _con.execute("INSERT INTO intl_activities(agreement_id,kind,title,date,count,note,by_user,at) VALUES(?,?,?,?,?,?,?,?)",
                     (call["agreement_id"], "almashinuv", f"Mobillik yakunlandi: {call['title'][:80]}", body.date, 1, f"ariza #{aid}", c.user["id"], _now()))
    _con.commit()
    return {"ok": True, "credit_status": "kutilmoqda"}

# ---- kredit tan olish (Akademik bo'lim) ----
@router.get(P + "/credits")
def api_credits(request: Request, status: str = ""):
    c = _ctx_of(request); _tab(c, "credits", "xalqaro: kredit tan olish navbati")
    w = " AND a.credit_status=?" if status else ""
    rows = db.rows(_con, f"""SELECT a.id, a.credits_earned, a.transcript_note, a.returned, a.departed, a.credit_status, a.credits_recognized, a.credit_note,
        a.credit_by, a.credit_at, s.full_name, s.hemis_id, g.name grp, g.course, c.title call, c.host, c.country
        FROM intl_applications a JOIN students s ON s.id=a.student_id JOIN groups_ g ON g.id=s.group_id JOIN intl_calls c ON c.id=a.call_id
        WHERE a.credit_status IS NOT NULL{w} ORDER BY a.credit_status!='kutilmoqda', a.returned""", (status,) if status else ())
    for r in rows: r["credit_label"] = CREDIT_ST.get(r["credit_status"], r["credit_status"])
    return {"items": rows, "can_decide": c.role.key in CREDIT}

@router.post(P + "/credits/{aid}")
def api_credit_decide(aid: int, body: CreditIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: kreditni tan olish", CREDIT, f"ariza #{aid} → {body.decision}")
    a = _app(aid)
    if a["credit_status"] != "kutilmoqda": _bad("Bu ariza kredit tan olish navbatida emas", 409)
    if body.decision not in ("tan_olindi", "qisman", "rad"): _bad("Noto'g'ri qaror")
    cr = a["credits_earned"] if body.decision == "tan_olindi" else 0 if body.decision == "rad" else body.credits_recognized
    if body.decision == "qisman" and not (0 < cr < (a["credits_earned"] or 0)): _bad("Qisman tan olishda kredit 0 dan katta va olinganidan kichik bo'lsin")
    if body.decision != "tan_olindi" and len(body.note.strip()) < 5: _bad("Qisman yoki rad etish uchun izoh yozing (qaysi fanlar farq qiladi)")
    _con.execute("UPDATE intl_applications SET credit_status=?, credits_recognized=?, credit_note=?, credit_by=?, credit_at=? WHERE id=?",
                 (body.decision, cr, body.note.strip(), c.title, _now(), aid)); _con.commit()
    return {"ok": True, "credits_recognized": cr}

# ---- xorijiy talabalar ----
class ForeignIn(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=200)
    country: str = Field(..., min_length=2, max_length=80)
    program: str = Field("", max_length=200)
    course: int = Field(1, ge=1, le=6)
    passport: str = Field("", max_length=20)
    visa_type: str = Field("O'qish vizasi (S-3)", max_length=120)
    visa_no: str = Field("", max_length=40)
    visa_expires: str
    reg_expires: str
    note: str = Field("", max_length=600)

class ForeignUpd(BaseModel):
    visa_expires: str | None = None
    reg_expires: str | None = None
    visa_no: str | None = Field(None, max_length=40)
    status: str | None = None
    note: str | None = Field(None, max_length=600)

def _mask(p: str) -> str:
    p = (p or "").strip()
    return ("***" + p[-4:]) if len(p) > 4 else p

@router.get(P + "/foreign")
def api_foreign(request: Request):
    c = _ctx_of(request); _tab(c, "foreign", "xalqaro: xorijiy talabalar")
    return {"items": foreign_list(), "can_edit": c.role.key in EDIT}

@router.post(P + "/foreign")
def api_foreign_new(body: ForeignIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: xorijiy talaba qo'shish", EDIT, body.country)
    if not _d(body.visa_expires) or not _d(body.reg_expires): _bad("Sanalarni YYYY-MM-DD ko'rinishida kiriting")
    fid = _con.execute("""INSERT INTO intl_foreign(full_name,country,program,course,passport,visa_type,visa_no,visa_expires,reg_expires,status,note,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,'o''qimoqda',?,?)""", (body.full_name.strip(), body.country.strip(), body.program.strip(), body.course, _mask(body.passport),
        body.visa_type.strip(), body.visa_no.strip(), body.visa_expires, body.reg_expires, body.note.strip(), _now())).lastrowid
    _con.commit()
    return {"ok": True, "id": fid}

@router.post(P + "/foreign/{fid}")
def api_foreign_upd(fid: int, body: ForeignUpd, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: viza/ro'yxat yangilash", EDIT, f"#{fid}")
    f = db.one(_con, "SELECT * FROM intl_foreign WHERE id=?", (fid,))
    if not f: _bad("Topilmadi", 404)
    sets, args = [], []
    for k in ("visa_expires", "reg_expires"):
        v = getattr(body, k)
        if v is not None:
            if not _d(v): _bad("Sana noto'g'ri")
            sets.append(f"{k}=?"); args.append(v)
    if body.visa_no is not None: sets.append("visa_no=?"); args.append(body.visa_no.strip())
    if body.status is not None:
        if body.status not in ("o'qimoqda", "bitirgan", "chetlashtirilgan", "akademik ta'til"): _bad("Noto'g'ri holat")
        sets.append("status=?"); args.append(body.status)
    if body.note is not None: sets.append("note=?"); args.append(body.note.strip())
    if not sets: _bad("O'zgarish yo'q")
    _con.execute(f"UPDATE intl_foreign SET {', '.join(sets)}, updated_at=? WHERE id=?", (*args, _now(), fid)); _con.commit()
    return {"ok": True, **_foreign_dec(db.one(_con, "SELECT * FROM intl_foreign WHERE id=?", (fid,)))}

# ---- delegatsiyalar ----
class DelIn(BaseModel):
    org: str = Field(..., min_length=3, max_length=200)
    country: str = Field(..., min_length=2, max_length=80)
    head: str = Field("", max_length=200)
    members: int = Field(1, ge=1, le=200)
    arrive: str
    depart: str
    purpose: str = Field(..., min_length=3, max_length=500)
    agreement_id: int | None = None
    host: str = Field("", max_length=200)

class DelOut(BaseModel):
    status: str
    outcome: str = Field("", max_length=1500)

@router.get(P + "/delegations")
def api_dels(request: Request):
    c = _ctx_of(request); _tab(c, "delegations", "xalqaro: delegatsiyalar jurnali")
    return {"items": delegations_list(), "can_edit": c.role.key in EDIT}

@router.post(P + "/delegations")
def api_del_new(body: DelIn, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: delegatsiya qayd etish", EDIT, body.org[:80])
    a, d = _d(body.arrive), _d(body.depart)
    if not a or not d or d < a: _bad("Kelish va ketish sanalarini tekshiring")
    did = _con.execute("""INSERT INTO intl_delegations(org,country,head,members,arrive,depart,purpose,agreement_id,host,status,created_by,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,'rejalashtirilgan',?,?)""", (body.org.strip(), body.country.strip(), body.head.strip(), body.members, body.arrive, body.depart,
        body.purpose.strip(), body.agreement_id, body.host.strip(), c.user["id"], _now())).lastrowid
    _con.commit()
    return {"ok": True, "id": did}

@router.post(P + "/delegations/{did}/outcome")
def api_del_out(did: int, body: DelOut, request: Request):
    c = _ctx_of(request); guard(c, "xalqaro: delegatsiya natijasi", EDIT, f"#{did} → {body.status}")
    d = db.one(_con, "SELECT * FROM intl_delegations WHERE id=?", (did,))
    if not d: _bad("Topilmadi", 404)
    if body.status not in ("o'tkazildi", "bekor"): _bad("Holat: «o'tkazildi» yoki «bekor»")
    if body.status == "o'tkazildi" and _d(d["arrive"]) > _today(): _bad("Tashrif hali bo'lmagan", 409)
    if body.status == "o'tkazildi" and len(body.outcome.strip()) < 5: _bad("Natijani yozing (kelishuvlar, keyingi qadamlar)")
    _con.execute("UPDATE intl_delegations SET status=?, outcome=? WHERE id=?", (body.status, body.outcome.strip(), did)); _con.commit()
    return {"ok": True}

# =============================================================================================
# API: talaba kabineti (/talaba) — ochiq tanlovlar va o'z arizalari
# =============================================================================================
def _stp():
    from . import student_portal as STP
    return STP

class StudentAppIn(BaseModel):
    lang_cert: str = Field("IELTS Academic", max_length=120)
    lang_score: float = Field(..., ge=0, le=9)
    motivation: str = Field(..., min_length=20, max_length=2000)

@router.get("/api/talaba/xalqaro")
def api_student_calls(request: Request):
    STP = _stp(); s = STP.student(request)
    td = _today().isoformat()
    calls = db.rows(_con, "SELECT id, title, host, country, seats, min_gpa, lang_min, lang_req, no_debts, min_course, deadline, mob_start, mob_end FROM intl_calls WHERE status='ochiq' AND deadline>=? ORDER BY deadline", (td,))
    for c in calls:
        e = eligibility(c, s["id"], c["lang_min"])   # til bali — talabaning o'zi kiritadi; oldindan ko'rinish uchun minimal bal bilan
        c["preview"] = {"gpa": e["gpa"], "debts": e["debts"], "ok": bool(e["eligible"]), "note": e["note"]}
        c["applied"] = bool(db.one(_con, "SELECT 1 x FROM intl_applications WHERE call_id=? AND student_id=?", (c["id"], s["id"])))
    mine = db.rows(_con, """SELECT a.id, a.status, a.elig_note, a.eligible, a.rank, a.total, a.created_at, a.credit_status, c.title, c.host, c.country, c.seats, c.status call_status
        FROM intl_applications a JOIN intl_calls c ON c.id=a.call_id WHERE a.student_id=? ORDER BY a.id DESC""", (s["id"],))
    for m in mine:
        m["status_label"] = APP_ST.get(m["status"], m["status"]); m["credit_label"] = CREDIT_ST.get(m["credit_status"] or "", "")
    STP._audit("xalqaro tanlovlar", True, s, resource=RES)
    return {"calls": calls, "mine": mine, "score_rule": "Jami = GPA/5 × 60 + til bali/9 × 25 + suhbat (0–15)"}

@router.post("/api/talaba/xalqaro/{cid}")
def api_student_apply(cid: int, body: StudentAppIn, request: Request):
    STP = _stp(); s = STP.student(request)
    if s["status"] != "faol": STP._audit("xalqaro ariza", False, s, "faol emas", resource=RES); _bad("Ariza faqat faol talabalar uchun", 403)
    try: r = add_application(_call(cid), s["id"], body.lang_cert.strip(), body.lang_score, body.motivation.strip(), "portal")
    except ValueError as e:
        STP._audit("xalqaro ariza", False, s, f"tanlov #{cid}: {e}", resource=RES); _bad(str(e), 409)
    STP._audit("xalqaro ariza", True, s, f"tanlov #{cid} · ariza #{r['id']} · {'mos' if r['eligible'] else 'mos emas'}", resource=RES)
    return {"ok": True, **r}
