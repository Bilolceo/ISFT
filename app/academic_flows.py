"""«Talaba harakati» — akademik oqimlar (docs/talaba-harakati.md).

1. Imtihon sessiyasi va jadvali: ta'lim shakli bo'yicha sessiyalar (kunduzgi qishki/yozgi, sirtqi qishki/yozgi), jadval yozuvlari
   (fan, guruh, sana-vaqt, xona — rooms, imtihon oluvchi — teachers), xona / guruh / imtihon oluvchi to'qnashuvi tekshiruvi,
   e'lon qilish, qayta topshirish muddatlari, XLSX eksport. Jadvalni Akademik bo'lim (sirtqi — Sirtqi bo'lim) tuzadi.
2. Apellyatsiya: yakuniy nazorat natijasi e'lon qilingandan keyin APPEAL_DAYS kun ichida; komissiya (kafedra mudiri + Imtihon
   bo'limi + Akademik bo'lim) ovoz beradi, rais (Akademik bo'lim) qaror qiladi: saqlash / oshirish / pasaytirish. Baho FAQAT
   grade_attempts orqali (kind «apellyatsiya», sabab bilan) o'zgaradi. create_appeal(...) — kelajakdagi talaba portali uchun.
3. Qayta o'qish va kursda qoldirish: qayta topshirishda ham o'tmagan fan (grade_attempts tarixi) → to'lovli qayta o'qish (kredit × narx,
   Buxgalteriyaga qarz qatori) yoki kursda qoldirish (Buyruqlar loyihasi). Muddat o'tsa — «akademik qarzdorlik sababli chetlashtirish».
4. Ko'chirish va qayta tiklash: ichki (yo'nalish / shakl), boshqa OTMdan / OTMga, qayta tiklash, ta'tildan qaytish — farq fanlari
   o'quv rejalari farqidan hisoblanadi, topshirish muddati bilan; har biri Buyruqlar turi.
5. ISFT granti (davlat granti EMAS): yillik qayta reyting (kredit bilan tortilgan GPA, academic_rules.gpa formulasi), saqlab qolish
   qoidalari, nomzodlar → komissiya (rektor / o'quv prorektori) → Buyruqlar.
6. Bitiruv: kredit (240 / 120), qarzsizlik, bitiruv ishi / magistrlik dissertatsiyasi, YDA; diplomlar reyestri (imtiyozli diplom
   qoidasi — RULES["honours"], institut nizomi bilan tasdiqlanadi), diplom ilovasi (DOCX), bitirish buyrug'i.
Ruxsatlar serverda (mode/guard), har bir murojaat rbac.audit(resource="flows").
"""
import datetime as dt, io, json, random, threading
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from . import clock
from . import db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
RES = rbac.FLOWS

# ---------------------------------------------------------------------------------------------
# Qoidalar (sozlanadigan; «*» — institut tasdig'ini talab qiladi, docs/talaba-harakati.md)
# ---------------------------------------------------------------------------------------------
RULES = {
    "appeal_days": 3,                 # apellyatsiya: natija e'lon qilingandan keyin (kalendar kun, e'lon kuni hisobga olinmaydi)
    "appeal_quorum": 2,               # komissiyaning kamida 2 a'zosi ovoz bergach rais qaror qiladi
    "restudy_decision_days": 30,      # * qayta topshirishda o'tmagandan keyin qaror (qayta o'qish / kursda qoldirish) muddati
    "restudy_pay_days": 30,           # * qayta o'qish to'lovi muddati
    "credits_per_year": 60,           # 1 kredit narxi = yillik kontrakt / 60
    "diff_deadline_days": 120,        # * farq fanlarini topshirish muddati (ko'chirish / tiklash buyrug'idan)
    "grant": {"merit": 250, "social": 50, "gpa_min_merit": 4.0, "gpa_min_social": 3.0, "rank_by": "course",
              "terms": [AR.RATING_SEMESTER - 1, AR.RATING_SEMESTER]},   # * yillik GPA: oxirgi o'quv yilining 2 semestri
    # * imtiyozli diplom (institut nizomi bilan tasdiqlanadi): fanlarning kamida 75% i «A» (65+), hech bir fan «C» dan past emas (50+),
    #   qayta topshirishsiz, bitiruv ishi va YDA — «A»
    "honours": {"min_a_share": 0.75, "min_score": 50, "thesis_min": 65, "yda_min": 65, "no_retakes": True},
    "diploma_series": {"bakalavr": "B", "magistr": "M"},   # * diplom seriyasi formati (davlat namunasi bo'yicha aniqlashtiriladi)
}
SLOTS = [("09:00", "11:00"), ("11:30", "13:30"), ("14:30", "16:30")]
FORMS = {"kunduzgi": "Kunduzgi", "sirtqi": "Sirtqi", "masofaviy": "Masofaviy"}
SEASON = {"qishki": "Qishki sessiya", "yozgi": "Yozgi sessiya"}
SESSION_ST = {"reja": "Reja", "loyiha": "Jadval tuzilmoqda", "e'lon qilingan": "E'lon qilingan", "yakunlangan": "Yakunlangan"}
FINAL_COURSE = {"bakalavr": 4, "magistr": 2}
THESIS_KIND = {"bakalavr": "Bitiruv malakaviy ishi", "magistr": "Magistrlik dissertatsiyasi"}
THESIS_ST = {"tanlanmagan": "Mavzu tanlanmagan", "tasdiqlangan": "Mavzu tasdiqlangan", "himoyaga tayyor": "Himoyaga tayyor",
             "himoya qilindi": "Himoya qilindi"}
TRANSFER_KINDS = {"ichki": ("Ichki ko'chirish (yo'nalish / shakl)", "ichki_kochirish"), "kirish": ("Boshqa OTMdan ko'chirib kelish", "kochirib_qabul"),
                  "chiqish": ("Boshqa OTMga ko'chib ketish", "kochirish"), "tiklash": ("Qayta tiklash", "tiklash"),
                  "tatildan_qaytish": ("Akademik ta'tildan qaytish", "tatildan_qaytish")}
APPEAL_DEC = {"saqlash": "Baho o'zgarishsiz qoldirildi", "oshirish": "Baho oshirildi", "pasaytirish": "Baho pasaytirildi"}
MEMBERS = {"kafedra": "Kafedra mudiri", "imtihon": "Imtihon bo'limi", "akademik": "Akademik bo'lim (rais)"}
PENDING_ST = "qabul kutilmoqda"   # boshqa OTMdan ko'chirib kelayotgan shaxs — buyruq imzolanguncha

SCHEMA = """
CREATE TABLE IF NOT EXISTS exam_sessions(id INTEGER PRIMARY KEY, name TEXT, study_form TEXT, season TEXT, semester INT, start TEXT, end TEXT,
  status TEXT, published_at TEXT, published_by INT, created_by INT, created_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS retake_windows(id INTEGER PRIMARY KEY, session_id INT, name TEXT, start TEXT, end TEXT);
CREATE TABLE IF NOT EXISTS exam_slots(id INTEGER PRIMARY KEY, session_id INT, group_id INT, subject TEXT, exam_date TEXT, start_time TEXT, end_time TEXT,
  room_id INT, examiner_id INT, kind TEXT DEFAULT 'yakuniy', created_by INT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_xs_sess ON exam_slots(session_id, exam_date);
CREATE INDEX IF NOT EXISTS ix_xs_date ON exam_slots(exam_date);
CREATE TABLE IF NOT EXISTS grade_appeals(id INTEGER PRIMARY KEY, student_id INT, subject TEXT, semester INT, attempt INT, dept_id INT, examiner_id INT,
  oraliq INT, yakuniy_old INT, score_old INT, published_at TEXT, filed_at TEXT, deadline TEXT, reason TEXT, channel TEXT, status TEXT,
  decision TEXT, yakuniy_new INT, score_new INT, decision_note TEXT, decided_by INT, decided_at TEXT, created_by INT);
CREATE TABLE IF NOT EXISTS appeal_votes(id INTEGER PRIMARY KEY, appeal_id INT, member TEXT, user_id INT, user_name TEXT, vote TEXT, yakuniy INT,
  note TEXT, at TEXT, UNIQUE(appeal_id, member));
CREATE TABLE IF NOT EXISTS restudy(id INTEGER PRIMARY KEY, student_id INT, subject TEXT, semester INT, credits INT, attempt_id INT, failed_at TEXT,
  offered_at TEXT, deadline TEXT, decision TEXT DEFAULT 'kutilmoqda', decided_at TEXT, decided_by INT, per_credit INT, amount INT, paid INT DEFAULT 0,
  paid_at TEXT, pay_due TEXT, order_id INT, note TEXT, UNIQUE(student_id, subject, semester));
CREATE INDEX IF NOT EXISTS ix_rs_st ON restudy(student_id);
CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY, kind TEXT, student_id INT, applicant TEXT, from_group_id INT, from_desc TEXT, to_group_id INT,
  other_otm TEXT, reason TEXT, status TEXT, deadline TEXT, order_id INT, prior TEXT, created_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS transfer_diff(id INTEGER PRIMARY KEY, transfer_id INT, subject TEXT, sem_no INT, credits INT, status TEXT DEFAULT 'qarz',
  score INT, passed_at TEXT, by_user INT);
CREATE TABLE IF NOT EXISTS grant_holders(student_id INTEGER PRIMARY KEY, category TEXT, since TEXT);
CREATE TABLE IF NOT EXISTS grant_rounds(id INTEGER PRIMARY KEY, acad_year TEXT, status TEXT, params TEXT, created_by INT, created_at TEXT, submitted_at TEXT,
  decided_by INT, decided_at TEXT, decision_note TEXT, order_award_id INT, order_revoke_id INT);
CREATE TABLE IF NOT EXISTS grant_candidates(id INTEGER PRIMARY KEY, round_id INT, student_id INT, kind TEXT, category TEXT, course INT, direction TEXT,
  gpa REAL, avg_score REAL, debts INT, rank INT, reason TEXT, contract_amount INT, decision TEXT DEFAULT 'kutilmoqda');
CREATE TABLE IF NOT EXISTS theses(student_id INTEGER PRIMARY KEY, kind TEXT, topic TEXT, supervisor_id INT, defense_date TEXT, status TEXT, score INT,
  updated_at TEXT, updated_by INT);
CREATE TABLE IF NOT EXISTS yda_results(id INTEGER PRIMARY KEY, student_id INT, subject TEXT, exam_date TEXT, score INT, by_user INT, at TEXT,
  UNIQUE(student_id, subject));
CREATE TABLE IF NOT EXISTS diplomas(id INTEGER PRIMARY KEY, student_id INT UNIQUE, series TEXT, number TEXT, honours INT, issued_at TEXT, order_id INT,
  reg_no TEXT, by_user INT);
CREATE TABLE IF NOT EXISTS flow_meta(k TEXT PRIMARY KEY, v TEXT);
"""

def _today(): return clock.today()
def _now(): return clock.now().isoformat(timespec="seconds")
def _iso(d): return d.isoformat() if hasattr(d, "isoformat") else str(d)
def _bad(msg, code=400): raise HTTPException(code, msg)
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _date(v, label="Sana"):
    try: return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except (TypeError, ValueError): _bad(f"{label} noto'g'ri: {v}")

# ---------------------------------------------------------------------------------------------
# Ruxsat va ko'lam
# ---------------------------------------------------------------------------------------------
FULL = ("talabalar", "registrator_xodim", "akademik")
REG = ("talabalar", "registrator_xodim", "sirtqi")          # arizalar → Buyruqlar loyihasi (orders.EDIT bilan bir xil)
LEAD = ("rektor", "prorektor_oquv")
ALL_TABS = ["sessiya", "apellyatsiya", "qayta", "kochirish", "grant", "bitiruv"]
TAB_TITLES = {"sessiya": "Sessiya va jadval", "apellyatsiya": "Apellyatsiya", "qayta": "Qayta o'qish", "kochirish": "Ko'chirish / tiklash",
              "grant": "ISFT granti", "bitiruv": "Bitiruv"}
TABS = {"full": ALL_TABS, "kafedra": ALL_TABS, "lead": ALL_TABS, "imtihon": ["sessiya", "apellyatsiya"],
        "sirtqi": ["sessiya", "apellyatsiya", "qayta", "kochirish", "bitiruv"], "bux": ["qayta", "grant"]}
MODE_NOTE = {"full": "To'liq ko'rinish", "kafedra": "O'z kafedrasi guruhlari va fanlari", "lead": "Tasdiqlash va jamlangan ko'rsatkichlar",
             "imtihon": "Sessiya jadvali va apellyatsiyalar", "sirtqi": "Faqat sirtqi ta'lim talabalari",
             "bux": "Faqat qayta o'qish to'lovlari va ISFT granti moliyaviy ro'yxati"}

def mode(c: Ctx):
    k = c.role.key
    if k in FULL: return "full"
    if k in LEAD: return "lead"
    return {"kafedra": "kafedra", "imtihon": "imtihon", "sirtqi": "sirtqi", "buxgalteriya": "bux"}.get(k)

def guard(c: Ctx, tab: str, action: str, detail: str = "", roles=None) -> str:
    """Ruxsat + audit. tab — bo'lim (ALL_TABS yoki "meta"); roles — amal uchun qo'shimcha cheklov (rol kalitlari)."""
    m = mode(c)
    ok = m is not None and (tab == "meta" or tab in TABS[m]) and (roles is None or c.role.key in roles)
    rbac.audit(_con, c, f"talaba harakati: {action}", RES, ok, detail)
    if not ok:
        why = (f"«{TAB_TITLES.get(tab, tab)}» bo'limi lavozimingiz uchun yopiq" if m and tab not in TABS[m] else
               "bu amal lavozimingiz uchun emas" if m else f"«{c.role.title}» lavozimi uchun ruxsat yo'q")
        raise AccessDenied(f"⛔ Talaba harakati: {why}. So'rov audit jurnaliga yozildi.")
    return m

def _deny(c: Ctx, action: str, msg: str, detail=""):
    rbac.audit(_con, c, f"talaba harakati: {action}", RES, False, detail)
    raise AccessDenied(f"⛔ {msg}. So'rov audit jurnaliga yozildi.")

def _dept(c: Ctx) -> int: return int(c.user.get("department_id") or 0)

def st_scope(c: Ctx, a="s") -> str:
    """Talabalar ko'lami (a — students taxallusi)."""
    m = mode(c)
    if m == "sirtqi": return f"{a}.study_form='sirtqi'"
    if m == "kafedra": return f"{a}.group_id IN (SELECT id FROM groups_ WHERE department_id={_dept(c)})"
    return "1=1"

def _student(sid: int) -> dict:
    s = db.one(_con, """SELECT s.*, g.name grp, g.course, g.direction, g.department_id, g.form gform, g.level glevel
                        FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""", (sid,))
    if not s: _bad("Talaba topilmadi", 404)
    return s

def _student_in_scope(c: Ctx, sid: int, action="talaba") -> dict:
    s = _student(sid)
    if not db.one(_con, f"SELECT 1 x FROM students s WHERE s.id=? AND {st_scope(c)}", (sid,)):
        _deny(c, f"{action}: ko'lamdan tashqari", "Bu talaba sizning ko'lamingizga kirmaydi", str(sid))
    return s

def _group(gid) -> dict:
    g = db.one(_con, "SELECT * FROM groups_ WHERE id=?", (int(gid or 0),))
    if not g: _bad("Guruh topilmadi", 404)
    return g

def _who(c: Ctx) -> str:
    n = c.user.get("full_name") or ""
    return f"{c.title} — {n.split(':', 1)[1].strip()}" if ":" in n else c.title

def _reg_ctx(con, student: dict) -> Ctx:
    """Buyruq loyihasini tuzadigan Registrator konteksti (sirtqi talaba — Sirtqi bo'lim): seed va avtomatik loyihalar uchun."""
    role = "sirtqi" if student.get("study_form") == "sirtqi" else "talabalar"
    u = db.one(con, "SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))
    return rbac.ctx_for(con, u["id"])

def _order_ctx(c: Ctx, studs: list) -> Ctx:
    """Registrator ofisi xodimi buyruq loyihasini o'z nomidan tuzadi; Sirtqi bo'lim — faqat sirtqi talabalar uchun."""
    if c.role.key == "sirtqi" and any(s.get("study_form") != "sirtqi" for s in studs):
        _deny(c, "buyruq loyihasi", "Sirtqi bo'lim faqat sirtqi ta'lim talabalari bilan ishlaydi")
    return c

def _order_status(oid):
    if not oid: return None
    o = db.one(_con, "SELECT id, reg_no, status, kind FROM orders WHERE id=?", (oid,))
    if not o: return None
    from . import orders as ORD
    o["status_name"] = ORD.STATUS.get(o["status"], o["status"]); o["kind_name"] = ORD.KINDS.get(o["kind"], {}).get("short", o["kind"])
    return o

def _create_order(c: Ctx, kind: str, students: list, params: dict, note: str, source="Talaba harakati") -> dict:
    from . import orders as ORD
    return ORD.create_order(c, kind, students, source=source, params=params, note=note)

# =============================================================================================
# 1. Imtihon sessiyasi va jadvali
# =============================================================================================
def _slot_rows(where: str, args=()) -> list:
    return db.rows(_con, f"""SELECT x.*, g.name grp, g.form, g.department_id dept_id, d.name kafedra, r.name room, r.capacity,
        t.full_name examiner, (SELECT COUNT(*) FROM students s WHERE s.group_id=x.group_id AND s.status='faol') n
        FROM exam_slots x JOIN groups_ g ON g.id=x.group_id LEFT JOIN departments d ON d.id=g.department_id
        LEFT JOIN rooms r ON r.id=x.room_id LEFT JOIN teachers t ON t.id=x.examiner_id WHERE {where}
        ORDER BY x.exam_date, x.start_time, g.name""", args)

def slot_scope(c: Ctx, a="x") -> str:
    m = mode(c)
    if m == "sirtqi": return f"{a}.group_id IN (SELECT id FROM groups_ WHERE form='sirtqi')"
    if m == "kafedra":
        return (f"({a}.group_id IN (SELECT id FROM groups_ WHERE department_id={_dept(c)}) OR "
                f"{a}.examiner_id IN (SELECT id FROM teachers WHERE department_id={_dept(c)}))")
    return "1=1"

def conflicts(con, session_id=None, slot_ids=None) -> list:
    """Xona, guruh va imtihon oluvchi to'qnashuvlari: bir sanada vaqt oralig'i kesishadigan ikki yozuv (barcha sessiyalar bo'yicha)."""
    w = "1=1"
    if session_id: w = f"(a.session_id={int(session_id)} OR b.session_id={int(session_id)})"
    if slot_ids: w += f" AND (a.id IN ({','.join(str(int(i)) for i in slot_ids)}) OR b.id IN ({','.join(str(int(i)) for i in slot_ids)}))"
    rs = db.rows(con, f"""SELECT a.id a_id, b.id b_id, a.exam_date, a.start_time a_start, a.end_time a_end, b.start_time b_start, b.end_time b_end,
        a.room_id=b.room_id AND a.room_id IS NOT NULL same_room, a.group_id=b.group_id same_group,
        a.examiner_id=b.examiner_id AND a.examiner_id IS NOT NULL same_exam,
        ga.name a_grp, gb.name b_grp, a.subject a_subj, b.subject b_subj, r.name room, t.full_name examiner
        FROM exam_slots a JOIN exam_slots b ON b.exam_date=a.exam_date AND b.id>a.id AND a.start_time<b.end_time AND b.start_time<a.end_time
        JOIN groups_ ga ON ga.id=a.group_id JOIN groups_ gb ON gb.id=b.group_id
        LEFT JOIN rooms r ON r.id=a.room_id LEFT JOIN teachers t ON t.id=a.examiner_id
        WHERE {w} AND ((a.room_id=b.room_id AND a.room_id IS NOT NULL) OR a.group_id=b.group_id OR (a.examiner_id=b.examiner_id AND a.examiner_id IS NOT NULL))
        ORDER BY a.exam_date, a.start_time""")
    out = []
    for r in rs:
        kinds = [k for k, f in (("xona", "same_room"), ("guruh", "same_group"), ("imtihon oluvchi", "same_exam")) if r[f]]
        out.append({"a": r["a_id"], "b": r["b_id"], "date": r["exam_date"], "kinds": kinds,
                    "text": f"{r['exam_date']} {r['a_start']}–{r['a_end']} / {r['b_start']}–{r['b_end']}: {', '.join(kinds)} to'qnashuvi — "
                            f"{r['a_grp']} «{r['a_subj']}» va {r['b_grp']} «{r['b_subj']}»"
                            + (f" · {r['room']}" if r["same_room"] else "") + (f" · {r['examiner']}" if r["same_exam"] else "")})
    return out

def sessions_list(c: Ctx) -> list:
    m = mode(c)
    w = "study_form='sirtqi'" if m == "sirtqi" else "1=1"
    out = db.rows(_con, f"SELECT * FROM exam_sessions WHERE {w} ORDER BY start DESC, id DESC")
    for s in out:
        s["status_name"] = SESSION_ST.get(s["status"], s["status"]); s["form_name"] = FORMS.get(s["study_form"], s["study_form"])
        s["slots"] = db.one(_con, f"SELECT COUNT(*) n FROM exam_slots x WHERE x.session_id=? AND {slot_scope(c)}", (s["id"],))["n"]
        s["groups"] = db.one(_con, f"SELECT COUNT(DISTINCT group_id) n FROM exam_slots x WHERE x.session_id=? AND {slot_scope(c)}", (s["id"],))["n"]
        s["windows"] = db.rows(_con, "SELECT * FROM retake_windows WHERE session_id=? ORDER BY start", (s["id"],))
        s["conflicts"] = len(conflicts(_con, s["id"])) if s["slots"] else 0
        t = _today().isoformat()
        s["phase"] = ("davom etmoqda" if s["start"] <= t <= s["end"] else "yakunlangan" if s["end"] < t else "kutilmoqda")
        s["can_edit"] = can_edit_session(c, s)
    return out

def can_edit_session(c: Ctx, s: dict) -> bool:
    k = c.role.key
    return k == "akademik" or (k == "sirtqi" and s.get("study_form") == "sirtqi")

def _session(c: Ctx, sid: int, edit=False) -> dict:
    s = db.one(_con, "SELECT * FROM exam_sessions WHERE id=?", (sid,))
    if not s: _bad("Sessiya topilmadi", 404)
    if mode(c) == "sirtqi" and s["study_form"] != "sirtqi":
        _deny(c, "sessiya: ko'lamdan tashqari", "Sirtqi bo'lim faqat sirtqi ta'lim sessiyalarini ko'radi", f"#{sid}")
    if edit and not can_edit_session(c, s):
        _deny(c, "sessiya jadvalini o'zgartirish", "Imtihon jadvalini Akademik faoliyatni boshqarish bo'limi (sirtqi — Sirtqi bo'lim) tuzadi", f"#{sid}")
    return s

def session_detail(c: Ctx, sid: int, q="", group=0, date="", offset=0, limit=200) -> dict:
    s = _session(c, sid)
    w, a = [f"x.session_id=?", slot_scope(c)], [sid]
    if group: w.append("x.group_id=?"); a.append(int(group))
    if date: w.append("x.exam_date=?"); a.append(date[:10])
    if q: w.append("(g.name LIKE ? OR x.subject LIKE ? OR t.full_name LIKE ? OR r.name LIKE ?)"); a += [f"%{q}%"] * 4
    rows = _slot_rows(" AND ".join(w), a)
    cf = conflicts(_con, sid)
    bad = {i for x in cf for i in (x["a"], x["b"])}
    for r in rows: r["conflict"] = r["id"] in bad
    s.update(status_name=SESSION_ST.get(s["status"], s["status"]), form_name=FORMS.get(s["study_form"]), can_edit=can_edit_session(c, s),
             windows=db.rows(_con, "SELECT * FROM retake_windows WHERE session_id=? ORDER BY start", (sid,)))
    days = sorted({r["exam_date"] for r in rows})
    return {"session": s, "total": len(rows), "items": rows[offset:offset + limit], "conflicts": cf if mode(c) != "kafedra" else [x for x in cf if x["a"] in {r["id"] for r in rows} or x["b"] in {r["id"] for r in rows}],
            "days": days, "slots": SLOTS}

class SessionIn(BaseModel):
    name: str = ""
    study_form: str
    season: str
    semester: int = AR.CURRENT_SEMESTER
    start: str
    end: str
    note: str = ""

def create_session(c: Ctx, b: SessionIn) -> dict:
    if b.study_form not in FORMS: _bad("Ta'lim shakli noto'g'ri")
    if b.season not in SEASON: _bad("Sessiya turi: qishki yoki yozgi")
    if c.role.key == "sirtqi" and b.study_form != "sirtqi":
        _deny(c, "sessiya yaratish", "Sirtqi bo'lim faqat sirtqi ta'lim sessiyasini tuzadi")
    if c.role.key not in ("akademik", "sirtqi"):
        _deny(c, "sessiya yaratish", "Sessiyani Akademik faoliyatni boshqarish bo'limi (sirtqi — Sirtqi bo'lim) tuzadi")
    st, en = _date(b.start, "Boshlanish"), _date(b.end, "Tugash")
    if en < st: _bad("Tugash sanasi boshlanishidan oldin")
    name = b.name.strip()[:160] or f"{AR.SEMESTERS.get(b.semester, '')} — {SEASON[b.season].lower()} ({FORMS[b.study_form].lower()})"
    cur = _con.execute("""INSERT INTO exam_sessions(name,study_form,season,semester,start,end,status,created_by,created_at,note)
                          VALUES(?,?,?,?,?,?,?,?,?,?)""", (name, b.study_form, b.season, b.semester, st, en, "loyiha", c.user["id"], _now(), b.note[:300]))
    _con.commit()
    return db.one(_con, "SELECT * FROM exam_sessions WHERE id=?", (cur.lastrowid,))

class SlotIn(BaseModel):
    group_id: int
    subject: str
    exam_date: str
    start_time: str
    end_time: str = ""
    room_id: int | None = None
    examiner_id: int | None = None
    force: bool = False

def _hm(v, label):
    v = str(v or "").strip()
    try: h, m = v.split(":"); assert 0 <= int(h) < 24 and 0 <= int(m) < 60; return f"{int(h):02d}:{int(m):02d}"
    except Exception: _bad(f"{label} noto'g'ri (SS:DD): {v}")

def add_slot(c: Ctx, sid: int, b: SlotIn) -> dict:
    s = _session(c, sid, edit=True)
    g = _group(b.group_id)
    if g["form"] != s["study_form"]: _bad(f"Guruh ta'lim shakli ({g['form']}) sessiya shakliga ({s['study_form']}) mos emas")
    d = _date(b.exam_date, "Imtihon sanasi")
    if not (s["start"] <= d <= s["end"]): _bad(f"Sana sessiya oralig'ida bo'lishi kerak ({s['start']} — {s['end']})")
    st = _hm(b.start_time, "Boshlanish vaqti"); en = _hm(b.end_time, "Tugash vaqti") if b.end_time else f"{int(st[:2]) + 2:02d}{st[2:]}"
    if en <= st: _bad("Tugash vaqti boshlanishidan keyin bo'lishi kerak")
    if b.room_id and not db.one(_con, "SELECT 1 x FROM rooms WHERE id=?", (b.room_id,)): _bad("Xona topilmadi")
    if b.examiner_id and not db.one(_con, "SELECT 1 x FROM teachers WHERE id=?", (b.examiner_id,)): _bad("Imtihon oluvchi topilmadi")
    subj = b.subject.strip()[:200]
    if not subj: _bad("Fan nomini kiriting")
    with _lock:
        cur = _con.execute("""INSERT INTO exam_slots(session_id,group_id,subject,exam_date,start_time,end_time,room_id,examiner_id,created_by,created_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?)""", (sid, g["id"], subj, d, st, en, b.room_id, b.examiner_id, c.user["id"], _now()))
        cf = conflicts(_con, slot_ids=[cur.lastrowid])
        if cf and not b.force:
            _con.rollback()
            raise HTTPException(409, {"message": "To'qnashuv: " + "; ".join(x["text"] for x in cf[:5]), "conflicts": cf})
        _con.commit()
    rbac.audit(_con, c, "talaba harakati: jadvalga yozuv qo'shildi", RES, True, f"sessiya #{sid} · {g['name']} · {subj} · {d} {st}" + (" · to'qnashuv bilan" if cf else ""))
    return {"ok": True, "id": cur.lastrowid, "conflicts": cf}

def delete_slot(c: Ctx, slot_id: int) -> dict:
    x = db.one(_con, "SELECT * FROM exam_slots WHERE id=?", (slot_id,))
    if not x: _bad("Yozuv topilmadi", 404)
    _session(c, x["session_id"], edit=True)
    _con.execute("DELETE FROM exam_slots WHERE id=?", (slot_id,)); _con.commit()
    return {"ok": True}

def publish_session(c: Ctx, sid: int) -> dict:
    s = _session(c, sid, edit=True)
    cf = conflicts(_con, sid)
    if cf: _bad(f"E'lon qilib bo'lmaydi: {len(cf)} ta to'qnashuv bor — avval tuzating")
    if not db.one(_con, "SELECT 1 x FROM exam_slots WHERE session_id=?", (sid,)): _bad("Jadval bo'sh")
    _con.execute("UPDATE exam_sessions SET status='e''lon qilingan', published_at=?, published_by=? WHERE id=?", (_now(), c.user["id"], sid)); _con.commit()
    return {"ok": True}

class WindowIn(BaseModel):
    name: str = "Qayta topshirish"
    start: str
    end: str

def add_window(c: Ctx, sid: int, b: WindowIn) -> dict:
    s = _session(c, sid, edit=True)
    st, en = _date(b.start, "Boshlanish"), _date(b.end, "Tugash")
    if en < st: _bad("Tugash sanasi boshlanishidan oldin")
    if st <= s["end"]: _bad(f"Qayta topshirish muddati sessiyadan keyin boshlanadi (sessiya {s['end']} da tugaydi)")
    _con.execute("INSERT INTO retake_windows(session_id,name,start,end) VALUES(?,?,?,?)", (sid, b.name.strip()[:120] or "Qayta topshirish", st, en)); _con.commit()
    return {"ok": True}

def _workdays(start: str, end: str) -> list:
    d, e, out = dt.date.fromisoformat(start), dt.date.fromisoformat(end), []
    while d <= e:
        if d.weekday() < 6: out.append(d.isoformat())   # dushanba–shanba
        d += dt.timedelta(days=1)
    return out

def group_subjects(con, group_ids) -> dict:
    """{guruh: [(fan, imtihon oluvchi)]} — joriy semestr fanlari (grades.semester=1) va asosiy o'qituvchi (eng ko'p baholagan)."""
    if not group_ids: return {}
    out = {}
    for k in range(0, len(group_ids), 500):
        part = ",".join(str(int(i)) for i in group_ids[k:k + 500])
        rs = con.execute(f"""SELECT s.group_id, gr.subject, gr.teacher_id, COUNT(*) n FROM grades gr JOIN students s ON s.id=gr.student_id
                             WHERE gr.semester=? AND s.group_id IN ({part}) GROUP BY 1, 2, 3 ORDER BY 1, 2, n DESC""", (AR.CURRENT_SEMESTER,)).fetchall()
        seen = set()
        for gid, subj, tid, _ in rs:
            if (gid, subj) in seen: continue
            seen.add((gid, subj)); out.setdefault(gid, []).append((subj, tid))
    return out

def generate(con, session_id: int, group_ids=None, by_user=None, gap=2) -> dict:
    """Jadvalni avtomatik tuzish (to'qnashuvsiz): har guruhga kuniga bitta imtihon, imtihonlar orasida dam olish kuni, xona sig'imi
    guruh soniga yetadi, imtihon oluvchi bir vaqtda bitta joyda. Allaqachon jadvali bor guruhlar o'tkazib yuboriladi."""
    s = db.one(con, "SELECT * FROM exam_sessions WHERE id=?", (session_id,))
    days = _workdays(s["start"], s["end"])
    have = {r[0] for r in con.execute("SELECT DISTINCT group_id FROM exam_slots WHERE session_id=?", (session_id,))}
    gs = db.rows(con, f"""SELECT g.id, g.name, (SELECT COUNT(*) FROM students x WHERE x.group_id=g.id AND x.status='faol') n FROM groups_ g
                          WHERE g.form=? {'AND g.id IN (' + ','.join(str(int(i)) for i in group_ids) + ')' if group_ids else ''} ORDER BY g.id""", (s["study_form"],))
    gs = [g for g in gs if g["id"] not in have and g["n"] > 0]
    subj = group_subjects(con, [g["id"] for g in gs])
    rooms = [tuple(r) for r in con.execute("SELECT id, capacity FROM rooms WHERE kind IN ('auditoriya','kompyuter sinfi') ORDER BY capacity, id")]
    busy_room, busy_ex, busy_grp = set(), set(), set()
    for d, st, rid, tid, gid in con.execute(f"SELECT exam_date, start_time, room_id, examiner_id, group_id FROM exam_slots WHERE exam_date BETWEEN ? AND ?",
                                            (s["start"], s["end"])):
        busy_room.add((d, st, rid)); busy_ex.add((d, st, tid)); busy_grp.add((d, gid))
    rows, skipped = [], 0
    for gi, g in enumerate(gs):
        pos = gi % gap
        for subject, tid in subj.get(g["id"], []):
            placed = False
            for tries in range(len(days)):
                di = (pos + tries) % len(days); d = days[di]
                if (d, g["id"]) in busy_grp: continue
                for k in range(len(SLOTS)):
                    st, en = SLOTS[(gi + k) % len(SLOTS)]
                    if tid and (d, st, tid) in busy_ex: continue
                    room = next((rid for rid, cap in rooms if (cap or 0) >= g["n"] and (d, st, rid) not in busy_room), None)
                    if room is None: continue
                    rows.append((session_id, g["id"], subject, d, st, en, room, tid, by_user, _now()))
                    busy_room.add((d, st, room)); busy_grp.add((d, g["id"]))
                    if tid: busy_ex.add((d, st, tid))
                    placed = True; pos = di + gap; break
                if placed: break
            if not placed: skipped += 1
    con.executemany("""INSERT INTO exam_slots(session_id,group_id,subject,exam_date,start_time,end_time,room_id,examiner_id,created_by,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", rows)
    con.commit()
    return {"groups": len(gs), "slots": len(rows), "skipped": skipped}

def slots_xlsx(c: Ctx, sid: int) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    D = session_detail(c, sid, limit=100000); s = D["session"]
    wb = Workbook(); ws = wb.active; ws.title = "Imtihon jadvali"
    thin = Side(style="thin", color="C9CED6"); brd = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.append(["ISFT INSTITUTI — International School of Finance and Technology"]); ws["A1"].font = Font(bold=True, size=14, color="7A0E14")
    ws.append([f"YAKUNIY NAZORAT JADVALI: {s['name']}"]); ws["A2"].font = Font(bold=True, size=12)
    ws.append([f"{s['form_name']} ta'lim · {s['start']} — {s['end']} · holat: {s['status_name']}" +
               ("".join(f" · {w['name']}: {w['start']} — {w['end']}" for w in s["windows"]))]); ws["A3"].font = Font(size=9, color="555B63")
    ws.append([])
    head = ["№", "Sana", "Vaqt", "Guruh", "Talabalar", "Fan", "Xona", "Sig'im", "Imtihon oluvchi", "Kafedra"]
    ws.append(head)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="7A0E14"); cell.alignment = Alignment(horizontal="center", wrap_text=True); cell.border = brd
    for i, r in enumerate(D["items"], 1):
        ws.append([i, r["exam_date"], f"{r['start_time']}–{r['end_time']}", r["grp"], r["n"], r["subject"], r["room"] or "—", r["capacity"],
                   _short(r["examiner"]) if r["examiner"] and ":" in r["examiner"] else (r["examiner"] or "—"), r["kafedra"] or ""])
        for cell in ws[ws.max_row]: cell.border = brd
    for col, wd in zip("ABCDEFGHIJ", (5, 12, 13, 15, 10, 42, 20, 8, 34, 30)): ws.column_dimensions[col].width = wd
    ws.freeze_panes = "A6"
    ws.append([]); ws.append([f"Tuzildi: ISFT Core, {clock.now():%d.%m.%Y %H:%M} · {_who(c)}"])
    if D["conflicts"]:
        ws2 = wb.create_sheet("To'qnashuvlar"); ws2.append(["Sana", "To'qnashuv"])
        for x in D["conflicts"]: ws2.append([x["date"], x["text"]])
        ws2.column_dimensions["B"].width = 120
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

# =============================================================================================
# 2. Apellyatsiya
# =============================================================================================
def publication(con, sid: int, subject: str, semester: int):
    """Hisobdagi (counted) urinish va uning e'lon qilingan sanasi. Tarix bo'lmasa — asl yakuniy nazorat, semestr oxirida e'lon qilingan."""
    g = db.one(con, "SELECT * FROM grades WHERE student_id=? AND subject=? AND semester=?", (sid, subject, semester))
    if not g: return None, None
    a = db.one(con, """SELECT * FROM grade_attempts WHERE student_id=? AND subject=? AND semester=? AND counted=1 ORDER BY attempt DESC LIMIT 1""",
               (sid, subject, semester))
    pub = (a["at"] if a and a.get("at") else AR.term_dates(semester)[1] if semester < AR.CURRENT_SEMESTER else None)
    return g, {"attempt": (a or {}).get("attempt") or g.get("attempts") or 1, "published_at": (pub or "")[:10], "kind": (a or {}).get("kind") or "asosiy"}

def _appeal_deadline(pub: str) -> str:
    return (dt.date.fromisoformat(pub) + dt.timedelta(days=RULES["appeal_days"])).isoformat()

def create_appeal(con, student_id: int, subject: str, semester: int, reason: str, channel: str = "ariza", by_user=None) -> dict:
    """Talabaning yakuniy nazorat natijasiga apellyatsiyasi. Kelajakdagi talaba portali shu funksiyani chaqiradi (channel="portal").
    Shartlar: baho yakunlangan (yakuniy ball bor), natija e'lon qilinganidan keyin RULES["appeal_days"] kun o'tmagan, shu fan bo'yicha
    ko'rib chiqilayotgan apellyatsiya yo'q, sabab yozilgan. Xato — ValueError (matn o'zbekcha)."""
    reason = (reason or "").strip()
    if len(reason) < 5: raise ValueError("Apellyatsiya sababini yozing (kamida 5 belgi)")
    s = db.one(con, "SELECT id, status FROM students WHERE id=?", (int(student_id),))
    if not s: raise ValueError("Talaba topilmadi")
    if s["status"] != "faol": raise ValueError("Apellyatsiya faqat faol talabalardan qabul qilinadi")
    g, p = publication(con, int(student_id), subject, int(semester))
    if not g: raise ValueError("Bu fan bo'yicha baho topilmadi")
    if g["score"] is None or g.get("yakuniy") is None: raise ValueError("Yakuniy nazorat natijasi hali e'lon qilinmagan")
    dl = _appeal_deadline(p["published_at"])
    today = _today().isoformat()
    if today > dl: raise ValueError(f"Apellyatsiya muddati o'tgan: natija {p['published_at']} da e'lon qilingan, muddat {dl} gacha edi "
                                    f"({RULES['appeal_days']} kun)")
    if db.one(con, "SELECT 1 x FROM grade_appeals WHERE student_id=? AND subject=? AND semester=? AND status!='qaror'", (int(student_id), subject, int(semester))):
        raise ValueError("Bu fan bo'yicha apellyatsiya allaqachon ko'rib chiqilmoqda")
    t = db.one(con, "SELECT id, department_id FROM teachers WHERE id=?", (g.get("teacher_id") or 0,))
    dept = (t or {}).get("department_id") or (db.one(con, "SELECT g.department_id d FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?",
                                                       (int(student_id),)) or {}).get("d")
    cur = con.execute("""INSERT INTO grade_appeals(student_id,subject,semester,attempt,dept_id,examiner_id,oraliq,yakuniy_old,score_old,published_at,
        filed_at,deadline,reason,channel,status,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(student_id), subject, int(semester), p["attempt"], dept, (t or {}).get("id"), g["oraliq"], g["yakuniy"], g["score"], p["published_at"],
         _now(), dl, reason[:1000], (channel or "ariza")[:20], "yangi", by_user))
    con.commit()
    return db.one(con, "SELECT * FROM grade_appeals WHERE id=?", (cur.lastrowid,))

def record_attempt(con, sid, subject, semester, kind, score, at, by_user=None, note="", force_count=False, yakuniy=None) -> dict:
    """Baholar tarixiga urinish (grade_attempts) yozadi va hisobdagi bahoni yangilaydi. Qoida (student_ops.apply_attempt bilan bir xil):
    hisobga — eng yuqori natija; force_count=True (apellyatsiya qarori) — natija pasaygan bo'lsa ham hisobga olinadi."""
    g = db.one(con, "SELECT * FROM grades WHERE student_id=? AND subject=? AND semester=?", (sid, subject, semester))
    if not g: raise ValueError("Baho yozuvi topilmadi")
    if not con.execute("SELECT 1 FROM grade_attempts WHERE student_id=? AND subject=? AND semester=?", (sid, subject, semester)).fetchone():
        con.execute("""INSERT INTO grade_attempts(student_id,subject,semester,attempt,kind,oraliq,yakuniy,score,at,counted,note)
                       VALUES(?,?,?,?,?,?,?,?,?,1,?)""", (sid, subject, semester, 1, "asosiy", g["oraliq"], g["yakuniy"], g["score"],
                                                          AR.term_dates(semester)[1], "asl urinish"))
    n = con.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM grade_attempts WHERE student_id=? AND subject=? AND semester=?", (sid, subject, semester)).fetchone()[0]
    counts = force_count or g["score"] is None or score > g["score"]
    if yakuniy is None:
        o = g["oraliq"] if g["oraliq"] is not None and AR.admitted(g["oraliq"]) and 0 <= score - g["oraliq"] <= AR.YAKUNIY_MAX else \
            (max(AR.ORALIQ_MIN, min(AR.ORALIQ_MAX, round(score * 0.3))) if score >= AR.PASS else min(AR.ORALIQ_MAX, score))
        o = min(o, score); y = score - o
    else:
        o, y = g["oraliq"], yakuniy
    if counts: con.execute("UPDATE grade_attempts SET counted=0 WHERE student_id=? AND subject=? AND semester=?", (sid, subject, semester))
    cur = con.execute("""INSERT INTO grade_attempts(student_id,subject,semester,attempt,kind,oraliq,yakuniy,score,at,counted,by_user,note)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (sid, subject, semester, n, kind, o, y, score, at, int(counts), by_user, note[:300]))
    if counts:
        con.execute("UPDATE grades SET score=?, oraliq=?, yakuniy=?, attempts=? WHERE student_id=? AND subject=? AND semester=?",
                    (score, o, y, n, sid, subject, semester))
        AR.refresh_student_metrics(con, [sid])
    else:
        con.execute("UPDATE grades SET attempts=? WHERE student_id=? AND subject=? AND semester=?", (n, sid, subject, semester))
    return {"attempt_id": cur.lastrowid, "attempt": n, "counted": counts, "score": score}

def appeal_member(c: Ctx, a: dict) -> str | None:
    k = c.role.key
    if k == "kafedra": return "kafedra" if _dept(c) == (a.get("dept_id") or -1) else None
    if k in ("imtihon", "akademik"): return k
    return None

def appeal_scope(c: Ctx, a="ap") -> str:
    m = mode(c)
    if m == "kafedra": return f"({a}.dept_id={_dept(c)} OR {a}.student_id IN (SELECT s.id FROM students s WHERE {st_scope(c)}))"
    if m == "sirtqi": return f"{a}.student_id IN (SELECT id FROM students WHERE study_form='sirtqi')"
    return "1=1"

def appeals_list(c: Ctx, status="", q="") -> dict:
    w, a = [appeal_scope(c)], []
    if status == "ochiq": w.append("ap.status!='qaror'")
    elif status: w.append("ap.status=?"); a.append(status)
    if q: w.append("(s.full_name LIKE ? OR ap.subject LIKE ? OR s.hemis_id LIKE ?)"); a += [f"%{q}%"] * 3
    rows = db.rows(_con, f"""SELECT ap.*, s.full_name, s.hemis_id, s.study_form, g.name grp, d.name kafedra, t.full_name examiner
        FROM grade_appeals ap JOIN students s ON s.id=ap.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        LEFT JOIN departments d ON d.id=ap.dept_id LEFT JOIN teachers t ON t.id=ap.examiner_id
        WHERE {' AND '.join(w)} ORDER BY ap.status='qaror', ap.filed_at DESC LIMIT 300""", a)
    for r in rows:
        r["votes"] = db.rows(_con, "SELECT member, user_name, vote, yakuniy, note, at FROM appeal_votes WHERE appeal_id=? ORDER BY at", (r["id"],))
        r["my_member"] = appeal_member(c, r)
        r["can_vote"] = bool(r["my_member"]) and r["status"] != "qaror" and not any(v["member"] == r["my_member"] for v in r["votes"])
        r["can_decide"] = c.role.key == "akademik" and r["status"] != "qaror" and len(r["votes"]) >= RULES["appeal_quorum"]
        r["decision_name"] = APPEAL_DEC.get(r["decision"] or "", "")
        r["sem_label"] = AR.SEMESTER_SHORT.get(r["semester"], r["semester"])
    agg = {x["status"]: x["n"] for x in db.rows(_con, f"SELECT ap.status, COUNT(*) n FROM grade_appeals ap WHERE {appeal_scope(c)} GROUP BY 1")}
    dec = {x["decision"]: x["n"] for x in db.rows(_con, f"SELECT ap.decision, COUNT(*) n FROM grade_appeals ap WHERE {appeal_scope(c)} AND ap.status='qaror' GROUP BY 1")}
    if mode(c) == "lead": rows = []   # rahbariyat: jamlangan ko'rsatkichlar (ism-shariflarsiz)
    return {"items": rows, "aggregate": mode(c) == "lead", "counts": agg, "decisions": dec, "rules": {"days": RULES["appeal_days"], "quorum": RULES["appeal_quorum"]},
            "members": MEMBERS, "decision_names": APPEAL_DEC}

def appeal_options(c: Ctx, sid: int) -> list:
    """Talabaning apellyatsiya berish mumkin bo'lgan baholari (muddat ichida e'lon qilingan yakuniy natijalar)."""
    _student_in_scope(c, sid, "apellyatsiya")
    lo = (_today() - dt.timedelta(days=RULES["appeal_days"])).isoformat()
    out = []
    for g in db.rows(_con, "SELECT subject, semester, score, oraliq, yakuniy FROM grades WHERE student_id=? AND semester<? AND score IS NOT NULL", (sid, AR.CURRENT_SEMESTER)):
        _, p = publication(_con, sid, g["subject"], g["semester"])
        if p and p["published_at"] >= lo:
            out.append({**g, **p, "deadline": _appeal_deadline(p["published_at"]), "sem_label": AR.SEMESTER_SHORT.get(g["semester"])})
    return out

def vote_appeal(c: Ctx, aid: int, vote: str, yakuniy=None, note="") -> dict:
    a = db.one(_con, "SELECT * FROM grade_appeals WHERE id=?", (aid,))
    if not a: _bad("Apellyatsiya topilmadi", 404)
    m = appeal_member(c, a)
    if not m: _deny(c, "apellyatsiya: ovoz", "Komissiya a'zosi emassiz (kafedra mudiri — faqat o'z kafedrasi fanlari)", f"#{aid}")
    if a["status"] == "qaror": _bad("Qaror allaqachon chiqarilgan")
    if vote not in APPEAL_DEC: _bad("Ovoz: saqlash, oshirish yoki pasaytirish")
    y = None
    if vote != "saqlash":
        try: y = int(yakuniy)
        except (TypeError, ValueError): _bad("Taklif etilayotgan yakuniy ballni kiriting")
        if not 0 <= y <= AR.YAKUNIY_MAX: _bad(f"Yakuniy ball 0–{AR.YAKUNIY_MAX} oralig'ida")
        if (vote == "oshirish") != (y > (a["yakuniy_old"] or 0)) or y == a["yakuniy_old"]: _bad("Taklif etilgan ball ovozga mos emas")
    try:
        _con.execute("INSERT INTO appeal_votes(appeal_id,member,user_id,user_name,vote,yakuniy,note,at) VALUES(?,?,?,?,?,?,?,?)",
                     (aid, m, c.user["id"], c.user["full_name"], vote, y, (note or "")[:500], _now()))
    except Exception: _bad("Siz bu apellyatsiya bo'yicha allaqachon ovoz bergansiz")
    _con.execute("UPDATE grade_appeals SET status='ko''rib chiqilmoqda' WHERE id=? AND status='yangi'", (aid,)); _con.commit()
    rbac.audit(_con, c, "talaba harakati: apellyatsiya ovozi", RES, True, f"#{aid} · {MEMBERS[m]} · {vote}" + (f" → {y}" if y is not None else ""))
    return {"ok": True}

def decide_core(con, a: dict, decision: str, yakuniy_new, note: str, user: dict) -> dict:
    if decision not in APPEAL_DEC: raise ValueError("Qaror: saqlash, oshirish yoki pasaytirish")
    res = {"changed": False}
    yk = a["yakuniy_old"]
    if decision != "saqlash":
        try: yk = int(yakuniy_new)
        except (TypeError, ValueError): raise ValueError("Yangi yakuniy ballni kiriting")
        if not 0 <= yk <= AR.YAKUNIY_MAX: raise ValueError(f"Yakuniy ball 0–{AR.YAKUNIY_MAX} oralig'ida")
        if decision == "oshirish" and yk <= (a["yakuniy_old"] or 0): raise ValueError("«Oshirish» qarori uchun yangi ball avvalgidan yuqori bo'lishi kerak")
        if decision == "pasaytirish" and yk >= (a["yakuniy_old"] or 0): raise ValueError("«Pasaytirish» qarori uchun yangi ball avvalgidan past bo'lishi kerak")
        score = (a["oraliq"] or 0) + yk
        res = record_attempt(con, a["student_id"], a["subject"], a["semester"], "apellyatsiya", score, _now(), user["id"],
                             f"apellyatsiya #{a['id']}: {APPEAL_DEC[decision].lower()} ({a['yakuniy_old']} → {yk}) · sabab: {note or a['reason']}"[:300],
                             force_count=True, yakuniy=yk)
        res["changed"] = True
    con.execute("""UPDATE grade_appeals SET status='qaror', decision=?, yakuniy_new=?, score_new=?, decision_note=?, decided_by=?, decided_at=? WHERE id=?""",
                (decision, yk, (a["oraliq"] or 0) + (yk or 0), (note or "")[:500], user["id"], _now(), a["id"]))
    con.commit()
    return res

def decide_appeal(c: Ctx, aid: int, decision: str, yakuniy_new=None, note="") -> dict:
    if c.role.key != "akademik": _deny(c, "apellyatsiya: qaror", "Komissiya qarorini rais — Akademik faoliyatni boshqarish bo'limi rasmiylashtiradi", f"#{aid}")
    a = db.one(_con, "SELECT * FROM grade_appeals WHERE id=?", (aid,))
    if not a: _bad("Apellyatsiya topilmadi", 404)
    if a["status"] == "qaror": _bad("Qaror allaqachon chiqarilgan")
    nv = db.one(_con, "SELECT COUNT(*) n FROM appeal_votes WHERE appeal_id=?", (aid,))["n"]
    if nv < RULES["appeal_quorum"]: _bad(f"Komissiyaning kamida {RULES['appeal_quorum']} a'zosi ovoz berishi kerak (hozir {nv})")
    if len((note or "").strip()) < 3: _bad("Qaror asosini yozing")
    with _lock:
        try: res = decide_core(_con, a, decision, yakuniy_new, note.strip(), c.user)
        except ValueError as e: _bad(str(e))
    rbac.audit(_con, c, "talaba harakati: apellyatsiya qarori", RES, True, f"#{aid} · {a['subject']} · {decision}" + (f" · {a['score_old']} → {res.get('score')}" if res["changed"] else ""))
    return {"ok": True, **res}

# =============================================================================================
# 3. Qayta o'qish (to'lovli) va kursda qoldirish; akademik qarzdorlik sababli chetlashtirish
# =============================================================================================
_rate_cache = {}

def contract_rate(con, form: str, level: str) -> int:
    """Yo'nalish shakli va darajasi bo'yicha odatiy yillik kontrakt (kontrakt talabalari medianasi)."""
    k = (form, level)
    if k not in _rate_cache:
        v = [r[0] for r in con.execute("SELECT contract_amount FROM students WHERE payment_type='kontrakt' AND study_form=? AND level=? AND contract_amount>0 ORDER BY 1",
                                       (form, level))]
        _rate_cache[k] = v[len(v) // 2] if v else 18_000_000
    return _rate_cache[k]

def per_credit(con, s: dict) -> int:
    base = s["contract_amount"] if s.get("payment_type") == "kontrakt" and s.get("contract_amount") else contract_rate(con, s["study_form"], s["level"])
    return int(round(base / RULES["credits_per_year"], -3))

def sync_restudy(con) -> int:
    """Qayta topshirishda ham o'tmagan (oxirgi urinish — qayta topshirish / otrabotka, ball < PASS, fan hali qarz) fanlar uchun taklif yozuvi."""
    rs = db.rows(con, f"""SELECT a.id aid, a.student_id, a.subject, a.semester, a.at, gr.credits, s.contract_amount, s.payment_type, s.study_form, s.level
        FROM grade_attempts a JOIN grades gr ON gr.student_id=a.student_id AND gr.subject=a.subject AND gr.semester=a.semester
        JOIN students s ON s.id=a.student_id
        WHERE a.kind IN ('qayta topshirish','otrabotka') AND a.score < {AR.PASS} AND gr.score < {AR.PASS} AND s.status='faol'
          AND a.attempt=(SELECT MAX(attempt) FROM grade_attempts b WHERE b.student_id=a.student_id AND b.subject=a.subject AND b.semester=a.semester)
          AND NOT EXISTS (SELECT 1 FROM restudy r WHERE r.student_id=a.student_id AND r.subject=a.subject AND r.semester=a.semester)""")
    for r in rs:
        off = dt.date.fromisoformat(r["at"][:10]) + dt.timedelta(days=1)
        con.execute("""INSERT OR IGNORE INTO restudy(student_id,subject,semester,credits,attempt_id,failed_at,offered_at,deadline,per_credit)
                       VALUES(?,?,?,?,?,?,?,?,?)""", (r["student_id"], r["subject"], r["semester"], r["credits"] or AR.CREDIT_DEFAULT, r["aid"], r["at"][:10],
                                                      off.isoformat(), (off + dt.timedelta(days=RULES["restudy_decision_days"])).isoformat(), per_credit(con, r)))
    # fan boshqa yo'l bilan yopilgan bo'lsa (otrabotka / apellyatsiya) — taklif yopiladi
    con.execute(f"""UPDATE restudy SET decision='yopilgan', note='qarz boshqa urinish bilan yopildi' WHERE decision='kutilmoqda'
                    AND EXISTS (SELECT 1 FROM grades g WHERE g.student_id=restudy.student_id AND g.subject=restudy.subject AND g.semester=restudy.semester AND g.score>={AR.PASS})""")
    con.commit()
    return len(rs)

RS_DEC = {"kutilmoqda": "Qaror kutilmoqda", "qayta_oqish": "Qayta o'qish (to'lovli)", "kursda_qoldirish": "Kursda qoldirish", "rad": "Rad etdi",
          "yopilgan": "Qarz yopildi", "chetlashtirish": "Chetlashtirish buyrug'i"}

def _expel_sql(today: str) -> str:
    return f"""(r.decision='kutilmoqda' AND r.deadline < '{today}') OR r.decision='rad'
               OR (r.decision='qayta_oqish' AND r.paid < r.amount AND r.pay_due < '{today}')"""

def restudy_list(c: Ctx, view="", q="") -> dict:
    m = mode(c); today = _today().isoformat()
    sync_restudy(_con)
    w, a = [st_scope(c)], []
    if m == "bux": w.append("r.decision='qayta_oqish'")
    if view == "kutilmoqda": w.append("r.decision='kutilmoqda'")
    elif view == "muddati_otgan": w.append(f"({_expel_sql(today)})")
    elif view in RS_DEC: w.append("r.decision=?"); a.append(view)
    if q: w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ? OR r.subject LIKE ?)"); a += [f"%{q}%"] * 3
    rows = db.rows(_con, f"""SELECT r.*, s.full_name, s.hemis_id, s.study_form, s.payment_type, s.status st_status, g.name grp, g.course,
        (SELECT o.status FROM orders o WHERE o.id=r.order_id) order_status, (SELECT o.reg_no FROM orders o WHERE o.id=r.order_id) order_reg
        FROM restudy r JOIN students s ON s.id=r.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        WHERE {' AND '.join(w)} ORDER BY r.decision!='kutilmoqda', r.deadline, s.full_name LIMIT 400""", a)
    for r in rows:
        r["decision_name"] = RS_DEC.get(r["decision"], r["decision"]); r["sem_label"] = AR.SEMESTER_SHORT.get(r["semester"], r["semester"])
        r["overdue"] = (r["decision"] == "kutilmoqda" and r["deadline"] < today) or r["decision"] == "rad" or \
                       (r["decision"] == "qayta_oqish" and (r["paid"] or 0) < (r["amount"] or 0) and (r["pay_due"] or "9") < today)
        r["quote"] = (r["credits"] or 0) * (r["per_credit"] or 0)
        if m == "bux":   # Buxgalteriya: baholarsiz — faqat to'lov qatori
            for k in ("failed_at", "attempt_id"): r.pop(k, None)
    sc = st_scope(c)
    agg = db.one(_con, f"""SELECT COUNT(*) n, COUNT(DISTINCT r.student_id) students, SUM(r.decision='kutilmoqda') pending,
        SUM(r.decision='qayta_oqish') restudy, SUM(r.decision='kursda_qoldirish') repeat_, SUM(CASE WHEN r.decision='qayta_oqish' THEN r.amount END) billed,
        SUM(CASE WHEN r.decision='qayta_oqish' THEN r.paid END) paid FROM restudy r JOIN students s ON s.id=r.student_id WHERE {sc}""")
    exp = db.one(_con, f"SELECT COUNT(DISTINCT r.student_id) n FROM restudy r JOIN students s ON s.id=r.student_id WHERE {sc} AND s.status='faol' AND ({_expel_sql(today)})")["n"]
    if m == "lead": rows = []
    return {"items": rows, "aggregate": m == "lead", "summary": {**agg, "expel": exp}, "decisions": RS_DEC,
            "rules": {"decision_days": RULES["restudy_decision_days"], "pay_days": RULES["restudy_pay_days"], "credits_per_year": RULES["credits_per_year"]}}

def _repeat_group(s: dict) -> dict | None:
    """Kursda qoldirish: shu yo'nalish, daraja va shakldagi bir kurs pastdagi guruh."""
    return db.one(_con, """SELECT * FROM groups_ WHERE direction=? AND level=? AND form=? AND course=? ORDER BY
                           (SELECT COUNT(*) FROM students x WHERE x.group_id=groups_.id AND x.status='faol'), name LIMIT 1""",
                  (s["direction"], s["glevel"] or s["level"], s["gform"] or s["study_form"], max(1, (s["course"] or 1) - 1)))

def restudy_decide(c: Ctx, sid: int, decision: str, note="") -> dict:
    if c.role.key not in REG: _deny(c, "qayta o'qish: qaror", "Talaba arizasi bo'yicha qarorni Registrator ofisi (sirtqi — Sirtqi bo'lim) rasmiylashtiradi", str(sid))
    s = _student_in_scope(c, sid, "qayta o'qish")
    if decision not in ("qayta_oqish", "kursda_qoldirish", "rad"): _bad("Qaror: qayta_oqish, kursda_qoldirish yoki rad")
    rs = db.rows(_con, "SELECT * FROM restudy WHERE student_id=? AND decision='kutilmoqda'", (sid,))
    if not rs: _bad("Bu talabada qaror kutilayotgan taklif yo'q")
    today = _today(); res = {"ok": True}
    with _lock:
        if decision == "qayta_oqish":
            due = (today + dt.timedelta(days=RULES["restudy_pay_days"])).isoformat()
            for r in rs:
                _con.execute("UPDATE restudy SET decision=?, decided_at=?, decided_by=?, amount=?, pay_due=?, note=? WHERE id=?",
                             (decision, _now(), c.user["id"], (r["credits"] or 0) * (r["per_credit"] or 0), due, note[:300], r["id"]))
            res["amount"] = sum((r["credits"] or 0) * (r["per_credit"] or 0) for r in rs)
        elif decision == "kursda_qoldirish":
            g = _repeat_group(s)
            if not g or g["id"] == s["group_id"]: _bad("Kursda qoldirish uchun mos guruh topilmadi (1-kurs talabasi?)")
            o = _create_order(_order_ctx(c, [s]), "kursda_qoldirish", [{"student_id": sid, "data": {"group_to": g["id"]}}],
                              {"date_from": today.isoformat(), "group_to": g["id"], "reason": "qayta topshirishda o'tmagan fanlar: " + ", ".join(r["subject"] for r in rs)},
                              f"Talaba harakati: qayta o'qish o'rniga kursda qoldirish ({len(rs)} ta fan)")
            for r in rs:
                _con.execute("UPDATE restudy SET decision=?, decided_at=?, decided_by=?, order_id=?, note=? WHERE id=?", (decision, _now(), c.user["id"], o["id"], note[:300], r["id"]))
            res.update(order_id=o["id"], group=g["name"])
        else:
            for r in rs: _con.execute("UPDATE restudy SET decision='rad', decided_at=?, decided_by=?, note=? WHERE id=?", (_now(), c.user["id"], note[:300], r["id"]))
        _con.commit()
    rbac.audit(_con, c, "talaba harakati: qayta o'qish qarori", RES, True, f"talaba #{sid} · {decision} · {len(rs)} ta fan")
    return res

def restudy_pay(c: Ctx, rid: int, amount: int) -> dict:
    if c.role.key != "buxgalteriya": _deny(c, "qayta o'qish: to'lov", "To'lovni Buxgalteriya qayd etadi", f"#{rid}")
    r = db.one(_con, "SELECT * FROM restudy WHERE id=?", (rid,))
    if not r or r["decision"] != "qayta_oqish": _bad("To'lov qatori topilmadi", 404)
    if amount <= 0: _bad("Summa musbat bo'lishi kerak")
    paid = min(r["amount"] or 0, (r["paid"] or 0) + int(amount))
    _con.execute("UPDATE restudy SET paid=?, paid_at=? WHERE id=?", (paid, _now(), rid)); _con.commit()
    rbac.audit(_con, c, "talaba harakati: qayta o'qish to'lovi", RES, True, f"#{rid} · +{amount} → {paid}/{r['amount']}")
    return {"ok": True, "paid": paid, "amount": r["amount"]}

def expulsion_candidates(c: Ctx) -> list:
    today = _today().isoformat()
    rs = db.rows(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.study_form, g.name grp, g.course, GROUP_CONCAT(r.subject, '; ') subjects,
        GROUP_CONCAT(DISTINCT r.decision) decisions, MIN(r.deadline) deadline
        FROM restudy r JOIN students s ON s.id=r.student_id LEFT JOIN groups_ g ON g.id=s.group_id
        WHERE {st_scope(c)} AND s.status='faol' AND ({_expel_sql(today)})
          AND s.id NOT IN (SELECT i.student_id FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                           WHERE o.kind='akademik_qarz' AND o.status IN ('loyiha','yuborilgan','kelishilgan','imzolangan'))
        GROUP BY s.id ORDER BY g.name, s.full_name""")
    for r in rs: r["why"] = ", ".join(RS_DEC.get(x, x) for x in (r["decisions"] or "").split(","))
    return rs

def expel_order(c: Ctx, ids: list) -> dict:
    if c.role.key not in REG: _deny(c, "chetlashtirish loyihasi", "Buyruq loyihasini Registrator ofisi (sirtqi — Sirtqi bo'lim) tuzadi")
    cand = {r["id"]: r for r in expulsion_candidates(c)}
    pick = [int(i) for i in ids if int(i) in cand]
    if not pick: _bad("Tanlangan talabalar chetlashtirish nomzodlari ro'yxatida yo'q")
    studs = [_student(i) for i in pick]
    o = _create_order(_order_ctx(c, studs), "akademik_qarz",
                      [{"student_id": i, "data": {"reason": cand[i]["subjects"][:280]}} for i in pick],
                      {"date_from": _today().isoformat()}, f"Talaba harakati: qayta topshirishdan keyin muddatida tugatilmagan akademik qarz ({len(pick)} ta talaba)")
    _con.execute(f"UPDATE restudy SET order_id=? WHERE student_id IN ({','.join(map(str, pick))}) AND decision IN ('kutilmoqda','rad','qayta_oqish')", (o["id"],))
    _con.commit()
    return {"ok": True, "order_id": o["id"], "count": len(pick)}

# =============================================================================================
# 4. Ko'chirish va qayta tiklash (farq fanlari)
# =============================================================================================
def diff_subjects(con, group: dict, passed: set) -> list:
    """Farq fanlari: maqsad guruh o'quv rejasida (yo'nalish × daraja) shu guruh allaqachon o'tgan semestrlardagi (dastur semestri
    < joriy) fanlardan talaba o'zlashtirmaganlari (nomi bo'yicha solishtiriladi)."""
    upto = AR.sem_no(group["course"], AR.CURRENT_SEMESTER) - 1
    req = db.rows(con, "SELECT subject, sem_no, credits FROM curriculum WHERE direction=? AND level=? AND sem_no<=? ORDER BY sem_no, id",
                  (group["direction"], group["level"], upto))
    low = {p.strip().lower() for p in passed}
    return [r for r in req if r["subject"].strip().lower() not in low]

def _passed(con, sid) -> set:
    return {r[0] for r in con.execute(f"SELECT subject FROM grades WHERE student_id=? AND score>={AR.PASS}", (sid,))}

class TransferIn(BaseModel):
    kind: str
    student_id: int | None = None
    to_group_id: int | None = None
    applicant: str = ""
    other_otm: str = ""
    prior_subjects: list[str] = []
    reason: str = ""

def create_transfer_core(con, c_user_id: int, b: TransferIn, check_scope=None) -> dict:
    if b.kind not in TRANSFER_KINDS: raise ValueError("Ko'chirish turi noto'g'ri")
    s, g = None, None
    if b.kind != "kirish":
        if not b.student_id: raise ValueError("Talabani tanlang")
        s = db.one(con, "SELECT s.*, g.name grp, g.course, g.direction FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (b.student_id,))
        if not s: raise ValueError("Talaba topilmadi")
        need = {"ichki": "faol", "chiqish": "faol", "tiklash": "chetlashtirilgan", "tatildan_qaytish": "akademik ta'til"}[b.kind]
        if s["status"] != need: raise ValueError(f"Talaba holati «{s['status']}» — bu ariza uchun «{need}» bo'lishi kerak")
        if con.execute("SELECT 1 FROM transfers WHERE student_id=? AND status NOT IN ('yakunlangan','rad')", (s["id"],)).fetchone():
            raise ValueError("Bu talaba bo'yicha ko'rib chiqilayotgan ariza bor")
    if b.kind in ("chiqish",):
        if len(b.other_otm.strip()) < 3: raise ValueError("Qabul qiluvchi OTM nomini yozing")
    else:
        gid = b.to_group_id or (s["group_id"] if b.kind == "tatildan_qaytish" and s else None)
        g = db.one(con, "SELECT * FROM groups_ WHERE id=?", (gid or 0,))
        if not g: raise ValueError("Maqsad guruhni tanlang")
        if b.kind == "ichki" and g["id"] == s["group_id"]: raise ValueError("Maqsad guruh joriy guruh bilan bir xil")
        if b.kind == "ichki" and g["level"] != s["level"]: raise ValueError("Ichki ko'chirish bir daraja (bakalavr / magistr) ichida")
    if b.kind == "kirish":
        if len(b.applicant.strip().split()) < 2: raise ValueError("Arizachining F.I.Sh.ni yozing")
        if len(b.other_otm.strip()) < 3: raise ValueError("Avvalgi OTM nomini yozing")
    if check_scope: check_scope(s, g)
    passed = set(b.prior_subjects or []) | (_passed(con, s["id"]) if s else set())
    diffs = diff_subjects(con, g, passed) if g else []
    today = _today()
    st = "farq fanlari" if diffs else "tayyor"
    from_desc = (f"{s['grp']} · {s['direction']} · {s['study_form']}" if s else b.other_otm.strip())
    cur = con.execute("""INSERT INTO transfers(kind,student_id,applicant,from_group_id,from_desc,to_group_id,other_otm,reason,status,deadline,prior,created_by,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (b.kind, s["id"] if s else None, b.applicant.strip()[:160] or None, s["group_id"] if s else None, from_desc[:200], g["id"] if g else None,
                       b.other_otm.strip()[:200] or None, b.reason.strip()[:500], st,
                       (today + dt.timedelta(days=RULES["diff_deadline_days"])).isoformat() if diffs else None,
                       json.dumps(sorted(b.prior_subjects or []), ensure_ascii=False), c_user_id, _now()))
    con.executemany("INSERT INTO transfer_diff(transfer_id,subject,sem_no,credits) VALUES(?,?,?,?)",
                    [(cur.lastrowid, d["subject"], d["sem_no"], d["credits"]) for d in diffs])
    con.commit()
    return {"id": cur.lastrowid, "diffs": len(diffs), "status": st}

def create_transfer(c: Ctx, b: TransferIn) -> dict:
    if c.role.key not in REG: _deny(c, "ko'chirish arizasi", "Arizani Registrator ofisi (sirtqi — Sirtqi bo'lim) qabul qiladi")
    def chk(s, g):
        if c.role.key == "sirtqi" and ((s and s["study_form"] != "sirtqi") or (g and g["form"] != "sirtqi" and b.kind != "ichki")):
            _deny(c, "ko'chirish arizasi", "Sirtqi bo'lim faqat sirtqi ta'lim talabalari bilan ishlaydi")
    try: r = create_transfer_core(_con, c.user["id"], b, chk)
    except ValueError as e: _bad(str(e))
    rbac.audit(_con, c, "talaba harakati: ko'chirish arizasi", RES, True, f"#{r['id']} · {TRANSFER_KINDS[b.kind][0]} · farq fanlari: {r['diffs']}")
    return {"ok": True, **r}

def transfer_scope(c: Ctx, a="t") -> str:
    m = mode(c)
    if m == "sirtqi":
        return f"({a}.student_id IN (SELECT id FROM students WHERE study_form='sirtqi') OR {a}.to_group_id IN (SELECT id FROM groups_ WHERE form='sirtqi'))"
    if m == "kafedra":
        return (f"({a}.to_group_id IN (SELECT id FROM groups_ WHERE department_id={_dept(c)}) OR "
                f"{a}.from_group_id IN (SELECT id FROM groups_ WHERE department_id={_dept(c)}))")
    return "1=1"

def transfers_list(c: Ctx, kind="", status="") -> dict:
    w, a = [transfer_scope(c)], []
    if kind: w.append("t.kind=?"); a.append(kind)
    if status: w.append("t.status=?"); a.append(status)
    rows = db.rows(_con, f"""SELECT t.*, COALESCE(s.full_name, t.applicant) full_name, s.hemis_id, s.status st_status, g.name to_grp, g.direction to_dir, g.form to_form, g.course to_course
        FROM transfers t LEFT JOIN students s ON s.id=t.student_id LEFT JOIN groups_ g ON g.id=t.to_group_id
        WHERE {' AND '.join(w)} ORDER BY t.created_at DESC LIMIT 300""", a)
    today = _today().isoformat()
    for r in rows:
        r["kind_name"] = TRANSFER_KINDS[r["kind"]][0]
        r["diffs"] = db.rows(_con, "SELECT * FROM transfer_diff WHERE transfer_id=? ORDER BY sem_no, id", (r["id"],))
        r["open"] = sum(1 for d in r["diffs"] if d["status"] != "topshirildi")
        r["overdue"] = bool(r["open"] and r["deadline"] and r["deadline"] < today)
        r["order"] = _order_status(r["order_id"])
        if r["order"] and r["order"]["status"] == "imzolangan" and r["status"] == "buyruq":
            _con.execute("UPDATE transfers SET status='yakunlangan' WHERE id=?", (r["id"],)); r["status"] = "yakunlangan"
    _con.commit()
    cnt = {x["status"]: x["n"] for x in db.rows(_con, f"SELECT t.status, COUNT(*) n FROM transfers t WHERE {transfer_scope(c)} GROUP BY 1")}
    ov = sum(1 for r in rows if r["overdue"])
    if mode(c) == "lead": rows = []
    return {"items": rows, "aggregate": mode(c) == "lead", "counts": cnt, "kinds": {k: v[0] for k, v in TRANSFER_KINDS.items()},
            "deadline_days": RULES["diff_deadline_days"], "overdue": ov}

def transfer_preview(c: Ctx, sid: int, gid: int) -> dict:
    g = _group(gid); passed = set()
    if sid: _student_in_scope(c, sid, "farq fanlari"); passed = _passed(_con, sid)
    d = diff_subjects(_con, g, passed)
    return {"group": g, "diffs": d, "credits": sum(x["credits"] or 0 for x in d)}

def diff_result(c: Ctx, did: int, score: int) -> dict:
    if c.role.key not in FULL + ("sirtqi",): _deny(c, "farq fani natijasi", "Farq fani natijasini Akademik bo'lim yoki Registrator ofisi kiritadi", f"#{did}")
    d = db.one(_con, "SELECT * FROM transfer_diff WHERE id=?", (did,))
    if not d: _bad("Yozuv topilmadi", 404)
    t = db.one(_con, f"SELECT * FROM transfers t WHERE t.id=? AND {transfer_scope(c)}", (d["transfer_id"],))
    if not t: _deny(c, "farq fani natijasi", "Ko'lamdan tashqari", f"#{did}")
    if not 0 <= int(score) <= 100: _bad("Ball 0–100")
    ok = int(score) >= AR.PASS
    _con.execute("UPDATE transfer_diff SET score=?, status=?, passed_at=?, by_user=? WHERE id=?", (int(score), "topshirildi" if ok else "qarz", _now() if ok else None, c.user["id"], did))
    left = db.one(_con, "SELECT COUNT(*) n FROM transfer_diff WHERE transfer_id=? AND status!='topshirildi'", (t["id"],))["n"]
    if not left and t["status"] == "farq fanlari": _con.execute("UPDATE transfers SET status='tayyor' WHERE id=?", (t["id"],))
    _con.commit()
    rbac.audit(_con, c, "talaba harakati: farq fani natijasi", RES, True, f"ariza #{t['id']} · {d['subject']} · {score}")
    return {"ok": True, "passed": ok, "left": left}

def _new_student(con, t: dict, g: dict) -> int:
    hemis = f"3{random.Random(t['id'] * 7919).randint(10**11, 10**12 - 1)}"
    rate = contract_rate(con, g["form"], g["level"])
    cur = con.execute("""INSERT INTO students(hemis_id,full_name,group_id,faculty_id,gender,payment_type,contract_amount,paid_amount,status,level,study_form)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (hemis, t["applicant"], g["id"], g["faculty_id"],
                                                            "F" if t["applicant"].rstrip().endswith("qizi") else "M", "kontrakt", rate, 0, PENDING_ST, g["level"], g["form"]))
    con.execute("UPDATE transfers SET student_id=? WHERE id=?", (cur.lastrowid, t["id"]))
    return cur.lastrowid

def transfer_order_core(con, c: Ctx, tid: int) -> dict:
    t = db.one(con, "SELECT * FROM transfers WHERE id=?", (tid,))
    if not t: raise ValueError("Ariza topilmadi")
    if t["order_id"] and (_order_status(t["order_id"]) or {}).get("status") not in (None, "bekor", "bekor_qilingan"): raise ValueError("Buyruq loyihasi allaqachon tuzilgan")
    kind = TRANSFER_KINDS[t["kind"]][1]; today = _today().isoformat()
    g = db.one(con, "SELECT * FROM groups_ WHERE id=?", (t["to_group_id"] or 0,))
    sid = t["student_id"] or _new_student(con, t, g)
    data = {"date_from": today}
    if g: data["group_to"] = g["id"]
    if t["kind"] == "chiqish": data["target"] = t["other_otm"]
    if t["kind"] == "kirish": data["source_otm"] = t["other_otm"]
    if t["kind"] == "ichki": data["reason"] = t["reason"] or "talabaning arizasi"
    nd = db.one(con, "SELECT COUNT(*) n FROM transfer_diff WHERE transfer_id=?", (tid,))["n"]
    o = _create_order(c, kind, [{"student_id": sid, "data": {k: v for k, v in data.items() if k in ("group_to", "target", "source_otm", "reason")}}],
                      {k: v for k, v in data.items() if k == "date_from"},
                      f"Talaba harakati: {TRANSFER_KINDS[t['kind']][0].lower()}" + (f" · farq fanlari {nd} ta, muddat {t['deadline']}" if nd else ""))
    con.execute("UPDATE transfers SET order_id=?, status='buyruq' WHERE id=?", (o["id"], tid)); con.commit()
    return {"order_id": o["id"], "student_id": sid}

def transfer_order(c: Ctx, tid: int) -> dict:
    if c.role.key not in REG: _deny(c, "ko'chirish buyrug'i", "Buyruq loyihasini Registrator ofisi (sirtqi — Sirtqi bo'lim) tuzadi", f"#{tid}")
    if not db.one(_con, f"SELECT 1 x FROM transfers t WHERE t.id=? AND {transfer_scope(c)}", (tid,)): _deny(c, "ko'chirish buyrug'i", "Ko'lamdan tashqari", f"#{tid}")
    try:
        with _lock: r = transfer_order_core(_con, c, tid)
    except ValueError as e: _bad(str(e))
    rbac.audit(_con, c, "talaba harakati: ko'chirish buyrug'i loyihasi", RES, True, f"ariza #{tid} → buyruq #{r['order_id']}")
    return {"ok": True, **r}

# =============================================================================================
# 5. ISFT granti (institutning o'z granti; davlat granti emas)
# =============================================================================================
GRANT_ST = {"loyiha": "Nomzodlar ro'yxati tuzildi", "komissiya": "Komissiya ko'rib chiqmoqda", "tasdiqlangan": "Komissiya tasdiqladi",
            "buyruq": "Buyruq loyihalari tuzildi"}
GRANT_KIND = {"mahrum": "Grantdan mahrum qilish", "tavsiya": "Grantga tavsiya"}

def annual_metrics(con, where="1=1") -> dict:
    """{talaba: (yillik GPA, o'rtacha ball, qarzlar)} — RULES['grant']['terms'] semestrlari; GPA — academic_rules.gpa formulasi
    (Σ kredit × 5 ballik baho / Σ kredit, ratio2 yaxlitlash) SQL ko'rinishida; qarz — barcha yakunlangan semestrlar (AR.debt_where)."""
    terms = ",".join(str(int(t)) for t in RULES["grant"]["terms"])
    rs = con.execute(f"""SELECT gr.student_id, {AR.ratio2_sql(f"SUM(COALESCE(gr.credits,{AR.CREDIT_DEFAULT})*{AR.grade5_sql('gr.score')})", f"SUM(COALESCE(gr.credits,{AR.CREDIT_DEFAULT}))")},
        {AR.ratio2_sql('SUM(gr.score)', 'COUNT(*)')}
        FROM grades gr JOIN students s ON s.id=gr.student_id WHERE gr.semester IN ({terms}) AND gr.score IS NOT NULL AND {where} GROUP BY 1""").fetchall()
    debts = dict(con.execute(f"SELECT g.student_id, COUNT(*) FROM grades g JOIN students s ON s.id=g.student_id WHERE {AR.debt_where('g')} AND {where} GROUP BY 1").fetchall())
    return {sid: (gpa, avg, debts.get(sid, 0)) for sid, gpa, avg in rs}

def compute_candidates(con) -> dict:
    """Saqlab qolish qoidalari: grant egasi qarzdor bo'lsa yoki yillik GPA chegaradan past (iqtidor — gpa_min_merit, ijtimoiy — gpa_min_social)
    bo'lsa — mahrum qilishga nomzod. Bo'shagan iqtidor o'rinlari shu kurs (yoki yo'nalish) kontrakt talabalari reytingi bo'yicha to'ldiriladi:
    qarzsiz, GPA ≥ gpa_min_merit, GPA, keyin o'rtacha ball bo'yicha. Ijtimoiy o'rinlar — hujjatlar asosida komissiya (soni ko'rsatiladi)."""
    G = RULES["grant"]
    base = "s.status='faol' AND s.study_form='kunduzgi' AND s.level='bakalavr'"
    met = annual_metrics(con, base)
    studs = db.rows(con, f"""SELECT s.id, s.payment_type, s.contract_amount, g.course, g.direction, COALESCE(h.category,'iqtidor') category
                            FROM students s JOIN groups_ g ON g.id=s.group_id LEFT JOIN grant_holders h ON h.student_id=s.id WHERE {base} AND g.course>=2""")
    key = (lambda s: (s["course"],)) if G["rank_by"] == "course" else (lambda s: (s["course"], s["direction"]))
    lose, pools, holders = [], {}, {}
    for s in studs:
        gpa, avg, debts = met.get(s["id"], (None, None, 0))
        s.update(gpa=gpa, avg=avg, debts=debts)
        if s["payment_type"] == "grant":
            holders[key(s)] = holders.get(key(s), 0) + 1
            thr = G["gpa_min_social"] if s["category"] == "ijtimoiy" else G["gpa_min_merit"]
            why = [f"akademik qarz: {debts} ta"] if debts else []
            if gpa is not None and gpa < thr: why.append(f"yillik GPA {gpa:.2f} < {thr}")
            if gpa is None: why.append("yillik natija yo'q")
            if why: lose.append({**s, "kind": "mahrum", "reason": "; ".join(why)})
        elif not debts and gpa is not None and gpa >= G["gpa_min_merit"]:
            pools.setdefault(key(s), []).append(s)
    award, social_vac = [], {}
    for k, pool in pools.items():
        vac = sum(1 for x in lose if key(x) == k and x["category"] != "ijtimoiy")
        social_vac[k] = sum(1 for x in lose if key(x) == k and x["category"] == "ijtimoiy")
        pool.sort(key=lambda x: (-(x["gpa"] or 0), -(x["avg"] or 0), x["id"]))
        for i, s in enumerate(pool[:vac], 1): award.append({**s, "kind": "tavsiya", "category": "iqtidor", "rank": i,
                                                           "reason": f"kurs reytingida {i}-o'rin (bo'shagan iqtidor o'rinlari: {vac})"})
    return {"lose": lose, "award": award, "holders": sum(holders.values()), "social_vacancies": sum(social_vac.values()), "rules": G}

def create_round(con, user_id: int, status="loyiha") -> int:
    r = compute_candidates(con)
    y = AR.ACAD_YEAR_START
    cur = con.execute("INSERT INTO grant_rounds(acad_year,status,params,created_by,created_at) VALUES(?,?,?,?,?)",
                      (f"{y}-{y + 1}", status, json.dumps({**RULES["grant"], "holders": r["holders"], "social_vacancies": r["social_vacancies"]}), user_id, _now()))
    rid = cur.lastrowid
    for x in r["lose"] + r["award"]:
        amt = contract_rate(con, "kunduzgi", "bakalavr") if x["kind"] == "mahrum" else (x["contract_amount"] or 0)
        con.execute("""INSERT INTO grant_candidates(round_id,student_id,kind,category,course,direction,gpa,avg_score,debts,rank,reason,contract_amount)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (rid, x["id"], x["kind"], x["category"], x["course"], x["direction"], x["gpa"], x["avg"],
                                                            x["debts"], x.get("rank"), x["reason"], amt))
    con.commit()
    return rid

def grant_view(c: Ctx, rid=0) -> dict:
    m = mode(c)
    rounds = db.rows(_con, "SELECT * FROM grant_rounds ORDER BY id DESC")
    for r in rounds: r["status_name"] = GRANT_ST.get(r["status"], r["status"]); r["params"] = json.loads(r["params"] or "{}")
    cur = next((r for r in rounds if r["id"] == rid), rounds[0] if rounds else None)
    cands = []
    if cur:
        w = "c.round_id=?"
        if m == "kafedra": w += f" AND s.group_id IN (SELECT id FROM groups_ WHERE department_id={_dept(c)})"
        if m == "bux": w += " AND c.decision='tasdiqlandi'"
        cands = db.rows(_con, f"""SELECT c.*, s.full_name, s.hemis_id, s.payment_type, g.name grp FROM grant_candidates c JOIN students s ON s.id=c.student_id
                                  LEFT JOIN groups_ g ON g.id=s.group_id WHERE {w} ORDER BY c.kind, c.course, c.rank, c.gpa""", (cur["id"],))
        for x in cands: x["kind_name"] = GRANT_KIND[x["kind"]]
        cur["orders"] = [o for o in (_order_status(cur["order_award_id"]), _order_status(cur["order_revoke_id"])) if o]
    hold = db.rows(_con, """SELECT g.course, COUNT(*) n, SUM(COALESCE(h.category,'iqtidor')='ijtimoiy') social FROM students s JOIN groups_ g ON g.id=s.group_id
                            LEFT JOIN grant_holders h ON h.student_id=s.id WHERE s.payment_type='grant' AND s.status='faol' GROUP BY 1 ORDER BY 1""")
    fin = None
    if cur and m in ("bux", "lead", "full"):
        fin = {"revoke_income": sum(x["contract_amount"] or 0 for x in cands if x["kind"] == "mahrum" and x["decision"] == "tasdiqlandi"),
               "award_loss": sum(x["contract_amount"] or 0 for x in cands if x["kind"] == "tavsiya" and x["decision"] == "tasdiqlandi")}
    return {"rounds": rounds, "round": cur, "candidates": cands, "holders": hold, "finance": fin,
            "quota": {"merit": RULES["grant"]["merit"], "social": RULES["grant"]["social"]}, "rules": RULES["grant"],
            "caps": {"create": c.role.key in ("talabalar", "registrator_xodim"), "decide": c.role.key in LEAD}}

def grant_round_new(c: Ctx) -> dict:
    if c.role.key not in ("talabalar", "registrator_xodim"): _deny(c, "ISFT granti: nomzodlar", "Nomzodlar ro'yxatini Registrator ofisi tuzadi")
    if db.one(_con, "SELECT 1 x FROM grant_rounds WHERE status IN ('loyiha','komissiya','tasdiqlangan')"): _bad("Yakunlanmagan grant raundi bor")
    with _lock: rid = create_round(_con, c.user["id"])
    rbac.audit(_con, c, "talaba harakati: ISFT granti nomzodlari", RES, True, f"raund #{rid}")
    return {"ok": True, "id": rid}

def grant_submit(c: Ctx, rid: int) -> dict:
    if c.role.key not in ("talabalar", "registrator_xodim"): _deny(c, "ISFT granti: komissiyaga", "Ro'yxatni Registrator ofisi komissiyaga yuboradi")
    r = db.one(_con, "SELECT * FROM grant_rounds WHERE id=?", (rid,))
    if not r or r["status"] != "loyiha": _bad("Faqat loyiha holatidagi ro'yxat yuboriladi")
    _con.execute("UPDATE grant_rounds SET status='komissiya', submitted_at=? WHERE id=?", (_now(), rid)); _con.commit()
    return {"ok": True}

def grant_decide(c: Ctx, rid: int, decisions: dict, note="") -> dict:
    if c.role.key not in LEAD: _deny(c, "ISFT granti: komissiya qarori", "Komissiya qarorini Rektor yoki O'quv ishlari prorektori tasdiqlaydi", f"#{rid}")
    r = db.one(_con, "SELECT * FROM grant_rounds WHERE id=?", (rid,))
    if not r or r["status"] != "komissiya": _bad("Raund komissiya ko'rib chiqish holatida emas")
    with _lock:
        for cid, d in (decisions or {}).items():
            if d in ("tasdiqlandi", "rad"): _con.execute("UPDATE grant_candidates SET decision=? WHERE id=? AND round_id=?", (d, int(cid), rid))
        _con.execute("UPDATE grant_candidates SET decision='tasdiqlandi' WHERE round_id=? AND decision='kutilmoqda'", (rid,))
        _con.execute("UPDATE grant_rounds SET status='tasdiqlangan', decided_by=?, decided_at=?, decision_note=? WHERE id=?", (c.user["id"], _now(), (note or "")[:500], rid))
        _con.commit()
    n = db.one(_con, "SELECT SUM(decision='tasdiqlandi') ok, SUM(decision='rad') no FROM grant_candidates WHERE round_id=?", (rid,))
    rbac.audit(_con, c, "talaba harakati: ISFT granti komissiya qarori", RES, True, f"raund #{rid} · tasdiq {n['ok']} · rad {n['no']}")
    return {"ok": True, **n}

def grant_orders(c: Ctx, rid: int) -> dict:
    if c.role.key not in ("talabalar", "registrator_xodim"): _deny(c, "ISFT granti: buyruq", "Buyruq loyihasini Registrator ofisi tuzadi", f"#{rid}")
    r = db.one(_con, "SELECT * FROM grant_rounds WHERE id=?", (rid,))
    if not r or r["status"] != "tasdiqlangan": _bad("Avval komissiya qarori kerak")
    today = _today().isoformat(); out = {}
    with _lock:
        for kind, ok, col in (("tavsiya", "isft_granti", "order_award_id"), ("mahrum", "isft_granti_mahrum", "order_revoke_id")):
            cs = db.rows(_con, "SELECT * FROM grant_candidates WHERE round_id=? AND kind=? AND decision='tasdiqlandi'", (rid, kind))
            if not cs: continue
            o = _create_order(c, ok, [{"student_id": x["student_id"], "data": {"reason": x["reason"][:280], **({"contract_amount": x["contract_amount"]} if kind == "mahrum" else {})}} for x in cs],
                              {"date_from": today}, f"Talaba harakati: ISFT granti {r['acad_year']} — {GRANT_KIND[kind].lower()} ({len(cs)} ta)")
            _con.execute(f"UPDATE grant_rounds SET {col}=? WHERE id=?", (o["id"], rid)); out[ok] = o["id"]
        _con.execute("UPDATE grant_rounds SET status='buyruq' WHERE id=?", (rid,)); _con.commit()
    return {"ok": True, "orders": out}

# =============================================================================================
# 6. Bitiruv
# =============================================================================================
def _cohort_sql(c: Ctx) -> str:
    return f"""SELECT s.id, s.full_name, s.hemis_id, s.level, s.study_form, s.status, s.group_id, g.name grp, g.direction, g.course, g.department_id,
        (SELECT COALESCE(SUM(COALESCE(x.credits,{AR.CREDIT_DEFAULT})),0) FROM grades x WHERE x.student_id=s.id AND x.semester<{AR.CURRENT_SEMESTER} AND x.score>={AR.PASS}) credits,
        (SELECT COUNT(*) FROM grades x WHERE x.student_id=s.id AND {AR.debt_where('x')}) debts,
        (SELECT COALESCE(SUM(COALESCE(x.credits,{AR.CREDIT_DEFAULT})),0) FROM grades x WHERE x.student_id=s.id AND x.semester={AR.CURRENT_SEMESTER}) cur_credits,
        t.topic, t.status t_status, t.score t_score, t.defense_date, t.supervisor_id, tc.full_name supervisor,
        (SELECT MIN(score) FROM yda_results y WHERE y.student_id=s.id) yda_min, (SELECT COUNT(*) FROM yda_results y WHERE y.student_id=s.id) yda_n,
        d.series, d.number, d.honours dip_honours
        FROM students s JOIN groups_ g ON g.id=s.group_id LEFT JOIN theses t ON t.student_id=s.id LEFT JOIN teachers tc ON tc.id=t.supervisor_id
        LEFT JOIN diplomas d ON d.student_id=s.id
        WHERE {st_scope(c)} AND ((s.level='bakalavr' AND g.course={FINAL_COURSE['bakalavr']}) OR (s.level='magistr' AND g.course={FINAL_COURSE['magistr']}))
          AND s.status IN ('faol','{GRAD_ST}')"""

GRAD_ST = "bitirgan"

def eligibility(r: dict) -> dict:
    need = AR.PROGRAM_CREDITS.get(r["level"], AR.BACHELOR_CREDITS)
    chk = [{"key": "credits", "ok": r["credits"] >= need, "text": f"Kredit: {r['credits']} / {need}"
            + (f" (joriy semestr: +{r['cur_credits']} rejada)" if r["credits"] < need and r.get("cur_credits") else "")},
           {"key": "debts", "ok": not r["debts"], "text": "Akademik qarz yo'q" if not r["debts"] else f"Akademik qarz: {r['debts']} ta fan"},
           {"key": "thesis", "ok": r.get("t_status") == "himoya qilindi" and (r.get("t_score") or 0) >= AR.PASS,
            "text": f"{THESIS_KIND.get(r['level'])}: " + (f"himoya qilindi ({r['t_score']} ball)" if r.get("t_status") == "himoya qilindi"
                    else THESIS_ST.get(r.get("t_status") or "tanlanmagan", r.get("t_status") or "") + (f", himoya {r['defense_date']}" if r.get("defense_date") else ""))},
           {"key": "yda", "ok": bool(r.get("yda_n")) and (r.get("yda_min") or 0) >= AR.PASS,
            "text": "YDA: " + (f"topshirildi (eng past {r['yda_min']} ball)" if r.get("yda_n") and (r.get("yda_min") or 0) >= AR.PASS
                               else f"o'tmadi ({r['yda_min']} ball)" if r.get("yda_n") else "natija yo'q")}]
    return {"checks": chk, "eligible": all(x["ok"] for x in chk), "need": need}

def honours(con, sid: int) -> dict:
    """Imtiyozli diplom qoidasi (RULES['honours'] — institut nizomi bilan tasdiqlanadi)."""
    H = RULES["honours"]
    gs = [r[0] for r in con.execute(f"SELECT score FROM grades WHERE student_id=? AND semester<? AND score IS NOT NULL", (sid, AR.CURRENT_SEMESTER))]
    if not gs: return {"ok": False, "why": ["baholar yo'q"]}
    a_share = sum(1 for x in gs if x >= AR.SCALE[0][0]) / len(gs)
    retakes = con.execute("SELECT COUNT(*) FROM grade_attempts WHERE student_id=? AND kind!='asosiy' AND kind!='apellyatsiya'", (sid,)).fetchone()[0]
    t = db.one(con, "SELECT score FROM theses WHERE student_id=?", (sid,)) or {}
    y = con.execute("SELECT MIN(score) FROM yda_results WHERE student_id=?", (sid,)).fetchone()[0]
    why = []
    if a_share < H["min_a_share"]: why.append(f"«A» ulushi {a_share:.0%} < {H['min_a_share']:.0%}")
    if min(gs) < H["min_score"]: why.append(f"«C» dan past baho bor ({min(gs)} ball)")
    if H["no_retakes"] and retakes: why.append(f"qayta topshirilgan: {retakes} ta")
    if (t.get("score") or 0) < H["thesis_min"]: why.append("bitiruv ishi «A» emas")
    if (y or 0) < H["yda_min"]: why.append("YDA «A» emas")
    return {"ok": not why, "a_share": round(a_share, 3), "min": min(gs), "why": why}

def grad_list(c: Ctx, view="", q="", group=0, offset=0, limit=100) -> dict:
    rows = db.rows(_con, _cohort_sql(c))
    for r in rows: r.update(eligibility(r)); r["t_status_name"] = THESIS_ST.get(r.get("t_status") or "tanlanmagan", "")
    summ = {"total": sum(1 for r in rows if r["status"] == "faol"), "eligible": sum(1 for r in rows if r["status"] == "faol" and r["eligible"]),
            "graduated": sum(1 for r in rows if r["status"] == GRAD_ST), "no_topic": sum(1 for r in rows if r["status"] == "faol" and not r.get("topic")),
            "debts": sum(1 for r in rows if r["status"] == "faol" and r["debts"]), "diplomas": sum(1 for r in rows if r.get("number")),
            "honours": sum(1 for r in rows if r.get("dip_honours"))}
    if view == "eligible": rows = [r for r in rows if r["status"] == "faol" and r["eligible"]]
    elif view == "bitirgan": rows = [r for r in rows if r["status"] == GRAD_ST]
    elif view == "notopic": rows = [r for r in rows if r["status"] == "faol" and not r.get("topic")]
    elif view == "debts": rows = [r for r in rows if r["status"] == "faol" and r["debts"]]
    else: rows = [r for r in rows if r["status"] == "faol"]
    if group: rows = [r for r in rows if r["group_id"] == int(group)]
    if q: ql = q.lower(); rows = [r for r in rows if ql in (r["full_name"] or "").lower() or ql in (r["hemis_id"] or "") or ql in (r["grp"] or "").lower()]
    rows.sort(key=lambda r: (not r["eligible"], r["grp"] or "", r["full_name"]))
    page = rows[offset:offset + limit] if mode(c) != "lead" else []
    for r in page:
        if r["eligible"] or r["status"] == GRAD_ST: r["honours"] = honours(_con, r["id"])
        o = db.one(_con, """SELECT o.id, o.status, o.reg_no FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                            WHERE i.student_id=? AND o.kind='bitirish' AND o.status NOT IN ('bekor','bekor_qilingan') ORDER BY o.id DESC LIMIT 1""", (r["id"],))
        r["order"] = o
    return {"items": page, "aggregate": mode(c) == "lead", "total": len(rows), "summary": summ, "rules": {"honours": RULES["honours"], "credits": AR.PROGRAM_CREDITS},
            "thesis_statuses": THESIS_ST,
            "caps": {"order": c.role.key in REG, "thesis": c.role.key in FULL + ("sirtqi", "kafedra"), "yda": c.role.key == "akademik",
                     "diploma": c.role.key in REG}}

class ThesisIn(BaseModel):
    topic: str = ""
    supervisor_id: int | None = None
    defense_date: str = ""
    status: str = ""
    score: int | None = None

def thesis_set(c: Ctx, sid: int, b: ThesisIn) -> dict:
    if c.role.key not in FULL + ("sirtqi", "kafedra"): _deny(c, "bitiruv ishi", "Bitiruv ishi ma'lumotini kafedra, Akademik bo'lim yoki Registrator ofisi kiritadi", str(sid))
    s = _student_in_scope(c, sid, "bitiruv ishi")
    if s["status"] != "faol": _bad("Talaba faol emas")
    t = db.one(_con, "SELECT * FROM theses WHERE student_id=?", (sid,)) or {}
    st = b.status or t.get("status") or ("tasdiqlangan" if b.topic else "tanlanmagan")
    if st not in THESIS_ST: _bad("Holat noto'g'ri")
    if st == "himoya qilindi" and (b.score is None or not 0 <= b.score <= 100): _bad("Himoya bali (0–100) kiritilishi kerak")
    if b.supervisor_id and not db.one(_con, "SELECT 1 x FROM teachers WHERE id=?", (b.supervisor_id,)): _bad("Rahbar topilmadi")
    vals = (THESIS_KIND[s["level"]], (b.topic.strip() or t.get("topic") or None), b.supervisor_id or t.get("supervisor_id"),
            (_date(b.defense_date, "Himoya sanasi") if b.defense_date else t.get("defense_date")), st, b.score if b.score is not None else t.get("score"), _now(), c.user["id"])
    _con.execute("""INSERT INTO theses(student_id,kind,topic,supervisor_id,defense_date,status,score,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(student_id) DO UPDATE SET kind=excluded.kind, topic=excluded.topic, supervisor_id=excluded.supervisor_id,
                    defense_date=excluded.defense_date, status=excluded.status, score=excluded.score, updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
                 (sid, *vals)); _con.commit()
    rbac.audit(_con, c, "talaba harakati: bitiruv ishi", RES, True, f"talaba #{sid} · {st}")
    return {"ok": True}

def yda_subject(level, direction): return f"Yakuniy davlat attestatsiyasi: {direction} ({'kompleks imtihon' if level == 'bakalavr' else 'mutaxassislik'})"

def yda_set(c: Ctx, sid: int, score: int, exam_date: str) -> dict:
    if c.role.key != "akademik": _deny(c, "YDA natijasi", "YDA natijalarini Akademik faoliyatni boshqarish bo'limi kiritadi", str(sid))
    s = _student(sid)
    if not 0 <= int(score) <= 100: _bad("Ball 0–100")
    _con.execute("""INSERT INTO yda_results(student_id,subject,exam_date,score,by_user,at) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(student_id,subject) DO UPDATE SET exam_date=excluded.exam_date, score=excluded.score, by_user=excluded.by_user, at=excluded.at""",
                 (sid, yda_subject(s["level"], s["direction"]), _date(exam_date, "YDA sanasi"), int(score), c.user["id"], _now())); _con.commit()
    rbac.audit(_con, c, "talaba harakati: YDA natijasi", RES, True, f"talaba #{sid} · {score}")
    return {"ok": True}

def grad_order(c: Ctx, ids: list) -> dict:
    if c.role.key not in REG: _deny(c, "bitirish buyrug'i", "Bitirish buyrug'i loyihasini Registrator ofisi (sirtqi — Sirtqi bo'lim) tuzadi")
    rows = {r["id"]: r for r in db.rows(_con, _cohort_sql(c))}
    bad = [i for i in ids if int(i) not in rows or rows[int(i)]["status"] != "faol" or not eligibility(rows[int(i)])["eligible"]]
    if bad or not ids: _bad(f"Bitirish talablariga javob bermaydigan talaba tanlangan ({len(bad)} ta)" if ids else "Talabalarni tanlang")
    busy = db.one(_con, f"""SELECT COUNT(*) n FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version WHERE o.kind='bitirish'
                            AND o.status IN ('loyiha','yuborilgan','kelishilgan') AND i.student_id IN ({','.join(str(int(i)) for i in ids)})""")["n"]
    if busy: _bad("Tanlangan talabalardan kimdir boshqa bitirish buyrug'i loyihasida bor")
    o = _create_order(_order_ctx(c, [rows[int(i)] for i in ids]), "bitirish", [{"student_id": int(i)} for i in ids], {"date_from": _today().isoformat()},
                      f"Talaba harakati: bitiruvchilar ({len(ids)} ta) — kredit, qarzsizlik, bitiruv ishi va YDA tekshirildi")
    rbac.audit(_con, c, "talaba harakati: bitirish buyrug'i loyihasi", RES, True, f"buyruq #{o['id']} · {len(ids)} ta")
    return {"ok": True, "order_id": o["id"]}

def next_diploma(con, level: str, year: int) -> tuple:
    series = f"{RULES['diploma_series'][level]}-{year % 100:02d}"
    n = con.execute("SELECT MAX(CAST(number AS INT)) FROM diplomas WHERE series=?", (series,)).fetchone()[0] or 0
    return series, f"{n + 1:06d}"

def register_diplomas(con, user_id=None) -> int:
    """Imzolangan bitirish buyrug'idagi (holati «bitirgan») va diplomi yo'q talabalarga raqam beriladi; imtiyoz qoidasi qo'llanadi."""
    rs = db.rows(con, """SELECT DISTINCT i.student_id sid, o.id oid, o.reg_no, o.order_date, s.level FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                         JOIN students s ON s.id=i.student_id WHERE o.kind='bitirish' AND o.status='imzolangan' AND s.status=? AND
                         NOT EXISTS (SELECT 1 FROM diplomas d WHERE d.student_id=i.student_id) ORDER BY o.id, i.id""", (GRAD_ST,))
    for r in rs:
        y = int((r["order_date"] or _today().isoformat())[:4])
        ser, num = next_diploma(con, r["level"], y)
        con.execute("INSERT INTO diplomas(student_id,series,number,honours,issued_at,order_id,reg_no,by_user) VALUES(?,?,?,?,?,?,?,?)",
                    (r["sid"], ser, num, int(honours(con, r["sid"])["ok"]), r["order_date"], r["oid"], r["reg_no"], user_id))
    con.commit()
    return len(rs)

def diplomas_list(c: Ctx, q="") -> dict:
    w, a = [st_scope(c)], []
    if q: w.append("(s.full_name LIKE ? OR d.number LIKE ?)"); a += [f"%{q}%"] * 2
    rows = db.rows(_con, f"""SELECT d.*, s.full_name, s.hemis_id, s.level, g.name grp, g.direction FROM diplomas d JOIN students s ON s.id=d.student_id
                             LEFT JOIN groups_ g ON g.id=s.group_id WHERE {' AND '.join(w)} ORDER BY d.series, d.number LIMIT 500""", a)
    if mode(c) == "lead": rows = []
    return {"items": rows, "aggregate": mode(c) == "lead", "rule": "Imtiyozli diplom: fanlarning kamida 75% i «A», hech bir fan «C» dan past emas, qayta topshirishsiz, bitiruv ishi va YDA «A» "
                                   "(institut nizomi bilan tasdiqlanadi)"}

def supplement_docx(con, sid: int, who: str) -> bytes:
    """Diplom ilovasi: barcha semestrlar fanlari, kreditlar, ballar va baholar; bitiruv ishi, YDA, GPA."""
    from docx import Document
    from . import brand as B
    s = db.one(con, """SELECT s.*, g.name grp, g.direction, g.course FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""", (sid,))
    d = db.one(con, "SELECT * FROM diplomas WHERE student_id=?", (sid,)) or {}
    t = db.one(con, "SELECT t.*, tc.full_name sup FROM theses t LEFT JOIN teachers tc ON tc.id=t.supervisor_id WHERE t.student_id=?", (sid,)) or {}
    gs = db.rows(con, "SELECT * FROM grades WHERE student_id=? AND score IS NOT NULL ORDER BY semester, sem_no, subject", (sid,))
    yda = db.rows(con, "SELECT * FROM yda_results WHERE student_id=?", (sid,))
    doc = Document(); B.setup(doc); B.letterhead(doc)
    B.title(doc, "DIPLOM ILOVASI" + ("" if d else " (LOYIHA)"), f"{d['series']} № {d['number']}" if d else "diplom raqami hali berilmagan")
    B.para(doc, f"F.I.Sh.: {s['full_name']} · HEMIS ID: {s['hemis_id']} · Ta'lim yo'nalishi: {s['direction']} · Daraja: {s['level']} · "
                f"Ta'lim shakli: {s['study_form']}" + (f" · Bitirish buyrug'i: {d['reg_no']} ({d['issued_at']})" if d.get("reg_no") else ""), indent=False, size=10.5)
    tot_cr, items = 0, []
    for sem in sorted({g["semester"] for g in gs}):
        rows = [g for g in gs if g["semester"] == sem]
        p = doc.add_paragraph(); B.run(p, f"{rows[0]['sem_no'] or ''}-semestr · {AR.SEMESTERS.get(sem, sem)}", 11, True, B.RGB_TEAL_DARK)
        B.table(doc, ["№", "Fan", "Kredit", "Ball", "Baho", "Harf"],
                [(i, g["subject"], g["credits"] or AR.CREDIT_DEFAULT, g["score"], AR.grade5(g["score"])[0], AR.letter(g["score"])) for i, g in enumerate(rows, 1)],
                widths=[0.8, 8, 1.4, 1.2, 1.2, 1.2], size=9)
        for g in rows:
            if g["score"] >= AR.PASS: tot_cr += g["credits"] or AR.CREDIT_DEFAULT
            items.append((g["credits"] or AR.CREDIT_DEFAULT, AR.grade5(g["score"])[0]))
    B.para(doc, f"Jami o'zlashtirilgan kredit: {tot_cr} / {AR.PROGRAM_CREDITS.get(s['level'], 240)} · GPA: {AR.gpa(items) or '—'} ({AR.GPA_FORMULA}).", indent=False, size=10.5, bold=True)
    B.para(doc, f"{THESIS_KIND.get(s['level'], 'Bitiruv ishi')}: «{t.get('topic') or '—'}» · rahbar: {_short(t.get('sup')) or t.get('sup') or '—'} · "
                f"himoya: {t.get('defense_date') or '—'} · ball: {t.get('score') if t.get('score') is not None else '—'}.", indent=False, size=10.5)
    for y in yda: B.para(doc, f"{y['subject']}: {y['score']} ball ({AR.letter(y['score'])}) · {y['exam_date']}.", indent=False, size=10.5)
    if d.get("honours"): B.para(doc, "Diplom imtiyozli (institut nizomidagi mezonlar asosida).", indent=False, size=10.5, bold=True)
    B.para(doc, f"Baholash shkalasi: {AR.SCALE_TEXT}. {AR.CREDIT_NOTE}.", indent=False, size=9)
    B.signature(doc, "Rektor", B.INST.get("rector_short", ""))
    p = doc.add_paragraph(); B.run(p, f"Registrator ofisi boshlig'i  _______________   · Tuzildi: ISFT Core, {clock.now():%d.%m.%Y %H:%M} · {who}", 9, False, B.RGB_GREY)
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()

# =============================================================================================
# Meta
# =============================================================================================
def meta(c: Ctx) -> dict:
    m = mode(c); today = _today().isoformat(); sc = st_scope(c)
    k = {}
    if "sessiya" in TABS[m]:
        k["sessiya"] = db.one(_con, f"SELECT COUNT(*) n FROM exam_sessions WHERE end>=? {'AND study_form=' + chr(39) + 'sirtqi' + chr(39) if m == 'sirtqi' else ''}", (today,))["n"]
    if "apellyatsiya" in TABS[m]: k["apellyatsiya"] = db.one(_con, f"SELECT COUNT(*) n FROM grade_appeals ap WHERE ap.status!='qaror' AND {appeal_scope(c)}")["n"]
    if "qayta" in TABS[m]:
        k["qayta"] = db.one(_con, f"""SELECT COUNT(DISTINCT r.student_id) n FROM restudy r JOIN students s ON s.id=r.student_id WHERE {sc} AND
                                      {"r.decision='qayta_oqish' AND r.paid<r.amount" if m == 'bux' else "r.decision='kutilmoqda'"}""")["n"]
    if "kochirish" in TABS[m]: k["kochirish"] = db.one(_con, f"SELECT COUNT(*) n FROM transfers t WHERE t.status NOT IN ('yakunlangan','rad') AND {transfer_scope(c)}")["n"]
    if "grant" in TABS[m]: k["grant"] = db.one(_con, "SELECT COUNT(*) n FROM grant_rounds WHERE status IN ('loyiha','komissiya','tasdiqlangan')")["n"]
    if "bitiruv" in TABS[m]: k["bitiruv"] = db.one(_con, f"SELECT COUNT(*) n FROM diplomas d JOIN students s ON s.id=d.student_id WHERE {sc}")["n"]
    return {"mode": m, "mode_note": MODE_NOTE[m], "scope": "Sirtqi ta'lim talabalari" if m == "sirtqi" else c.scope_label(_con), "role": c.role.key,
            "tabs": [{"key": t, "title": TAB_TITLES[t], "count": k.get(t)} for t in TABS[m]], "rules": RULES, "today": today,
            "caps": {"session_edit": c.role.key in ("akademik", "sirtqi"), "reg": c.role.key in REG, "akademik": c.role.key == "akademik",
                     "lead": c.role.key in LEAD, "bux": c.role.key == "buxgalteriya", "vote": c.role.key in ("kafedra", "imtihon", "akademik")}}

# =============================================================================================
# HTTP
# =============================================================================================
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
def _file(data, name, mt): return Response(data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
def C(request: Request) -> Ctx: return _ctx(request)
P = "/api/flows"

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "meta", "bo'lim ochildi"); return meta(c)

@router.get(P + "/lookup/students")
def api_lookup_students(request: Request, q: str = "", status: str = "faol"):
    c = C(request); guard(c, "meta", "talaba qidiruvi", q[:40], roles=FULL + ("sirtqi", "kafedra"))
    q = q.strip()[:60]
    if len(q) < 2: return []
    st = status if status in ("faol", "akademik ta'til", "chetlashtirilgan") else "faol"
    return db.rows(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.status, s.study_form, s.level, g.name grp, g.course, g.direction FROM students s
        LEFT JOIN groups_ g ON g.id=s.group_id WHERE {st_scope(c)} AND s.status=? AND (s.full_name LIKE ? OR s.hemis_id LIKE ?) ORDER BY s.full_name LIMIT 15""",
                         (st, f"%{q}%", f"{q}%"))

@router.get(P + "/lookup/groups")
def api_lookup_groups(request: Request, q: str = "", form: str = ""):
    c = C(request); guard(c, "meta", "guruh qidiruvi", q[:40])
    w, a = ["1=1"], []
    if mode(c) == "sirtqi" and not form: w.append("form='sirtqi'")
    if form: w.append("form=?"); a.append(form)
    if q: w.append("(name LIKE ? OR direction LIKE ?)"); a += [f"%{q}%"] * 2
    return db.rows(_con, f"SELECT id, name, course, direction, level, form FROM groups_ WHERE {' AND '.join(w)} ORDER BY name LIMIT 30", a)

@router.get(P + "/lookup/rooms")
def api_lookup_rooms(request: Request):
    c = C(request); guard(c, "sessiya", "xonalar ro'yxati")
    return db.rows(_con, "SELECT id, name, capacity, kind FROM rooms WHERE kind IN ('auditoriya','kompyuter sinfi') ORDER BY name")

@router.get(P + "/lookup/teachers")
def api_lookup_teachers(request: Request, q: str = ""):
    c = C(request); guard(c, "meta", "o'qituvchilar qidiruvi", q[:40])
    return db.rows(_con, "SELECT t.id, t.full_name, d.name kafedra FROM teachers t LEFT JOIN departments d ON d.id=t.department_id WHERE t.full_name LIKE ? ORDER BY t.full_name LIMIT 20", (f"%{q}%",))

# --- sessiya ---
@router.get(P + "/sessions")
def api_sessions(request: Request):
    c = C(request); guard(c, "sessiya", "sessiyalar"); return {"items": sessions_list(c), "slots": SLOTS, "forms": FORMS, "seasons": SEASON}

@router.post(P + "/sessions")
def api_session_new(body: SessionIn, request: Request):
    c = C(request); guard(c, "sessiya", "sessiya yaratish", body.name[:60], roles=("akademik", "sirtqi")); return create_session(c, body)

@router.get(P + "/sessions/{sid}")
def api_session(sid: int, request: Request, q: str = "", group: int = 0, date: str = "", offset: int = 0, limit: int = 200):
    c = C(request); guard(c, "sessiya", "sessiya jadvali", f"#{sid}"); return session_detail(c, sid, q.strip()[:60], group, date, offset, min(limit, 1000))

@router.post(P + "/sessions/{sid}/slots")
def api_slot_new(sid: int, body: SlotIn, request: Request):
    c = C(request); guard(c, "sessiya", "jadvalga yozuv", f"#{sid}", roles=("akademik", "sirtqi")); return add_slot(c, sid, body)

@router.post(P + "/slots/{xid}/delete")
def api_slot_del(xid: int, request: Request):
    c = C(request); guard(c, "sessiya", "jadval yozuvini o'chirish", f"#{xid}", roles=("akademik", "sirtqi")); return delete_slot(c, xid)

@router.post(P + "/sessions/{sid}/generate")
def api_generate(sid: int, request: Request):
    c = C(request); guard(c, "sessiya", "jadvalni avtomatik tuzish", f"#{sid}", roles=("akademik", "sirtqi"))
    _session(c, sid, edit=True)
    with _lock: return generate(_con, sid, by_user=c.user["id"])

@router.post(P + "/sessions/{sid}/publish")
def api_publish(sid: int, request: Request):
    c = C(request); guard(c, "sessiya", "jadvalni e'lon qilish", f"#{sid}", roles=("akademik", "sirtqi")); return publish_session(c, sid)

@router.post(P + "/sessions/{sid}/windows")
def api_window(sid: int, body: WindowIn, request: Request):
    c = C(request); guard(c, "sessiya", "qayta topshirish muddati", f"#{sid}", roles=("akademik", "sirtqi")); return add_window(c, sid, body)

@router.get(P + "/sessions/{sid}/export")
def api_export(sid: int, request: Request):
    c = C(request); guard(c, "sessiya", "jadval eksporti (.xlsx)", f"#{sid}")
    return _file(slots_xlsx(c, sid), f"imtihon_jadvali_{sid}.xlsx", XLSX)

# --- apellyatsiya ---
@router.get(P + "/appeals")
def api_appeals(request: Request, status: str = "", q: str = ""):
    c = C(request); guard(c, "apellyatsiya", "apellyatsiyalar"); return appeals_list(c, status, q.strip()[:60])

@router.get(P + "/appeals/options/{sid}")
def api_appeal_opts(sid: int, request: Request):
    c = C(request); guard(c, "apellyatsiya", "apellyatsiya: baholar", str(sid), roles=REG + ("akademik",)); return appeal_options(c, sid)

class AppealIn(BaseModel):
    student_id: int
    subject: str
    semester: int
    reason: str
    channel: str = "ariza"

@router.post(P + "/appeals")
def api_appeal_new(body: AppealIn, request: Request):
    c = C(request); guard(c, "apellyatsiya", "apellyatsiya qabul qilish", f"talaba #{body.student_id} · {body.subject[:60]}", roles=REG)
    _student_in_scope(c, body.student_id, "apellyatsiya")
    try: a = create_appeal(_con, body.student_id, body.subject, body.semester, body.reason, body.channel if body.channel in ("ariza", "portal", "elektron") else "ariza", c.user["id"])
    except ValueError as e: _bad(str(e))
    return {"ok": True, "id": a["id"], "deadline": a["deadline"]}

class VoteIn(BaseModel):
    vote: str
    yakuniy: int | None = None
    note: str = ""

@router.post(P + "/appeals/{aid}/vote")
def api_vote(aid: int, body: VoteIn, request: Request):
    c = C(request); guard(c, "apellyatsiya", "apellyatsiya ovozi", f"#{aid}", roles=("kafedra", "imtihon", "akademik")); return vote_appeal(c, aid, body.vote, body.yakuniy, body.note)

class DecideIn(BaseModel):
    decision: str
    yakuniy: int | None = None
    note: str = ""

@router.post(P + "/appeals/{aid}/decide")
def api_decide(aid: int, body: DecideIn, request: Request):
    c = C(request); guard(c, "apellyatsiya", "apellyatsiya qarori", f"#{aid}", roles=("akademik",)); return decide_appeal(c, aid, body.decision, body.yakuniy, body.note)

# --- qayta o'qish ---
@router.get(P + "/restudy")
def api_restudy(request: Request, view: str = "", q: str = ""):
    c = C(request); guard(c, "qayta", "qayta o'qish ro'yxati", view); return restudy_list(c, view, q.strip()[:60])

class DecIn(BaseModel):
    decision: str
    note: str = ""

@router.post(P + "/restudy/student/{sid}/decide")
def api_restudy_decide(sid: int, body: DecIn, request: Request):
    c = C(request); guard(c, "qayta", "qayta o'qish qarori", str(sid), roles=REG); return restudy_decide(c, sid, body.decision, body.note)

class PayIn(BaseModel):
    amount: int

@router.post(P + "/restudy/{rid}/pay")
def api_restudy_pay(rid: int, body: PayIn, request: Request):
    c = C(request); guard(c, "qayta", "qayta o'qish to'lovi", f"#{rid}", roles=("buxgalteriya",)); return restudy_pay(c, rid, body.amount)

@router.get(P + "/restudy/expulsion")
def api_expulsion(request: Request):
    c = C(request); guard(c, "qayta", "chetlashtirish nomzodlari", roles=FULL + ("sirtqi", "kafedra")); return {"items": expulsion_candidates(c)}

class IdsIn(BaseModel):
    ids: list[int]

@router.post(P + "/restudy/expulsion/order")
def api_expulsion_order(body: IdsIn, request: Request):
    c = C(request); guard(c, "qayta", "chetlashtirish buyrug'i loyihasi", f"{len(body.ids)} ta", roles=REG); return expel_order(c, body.ids)

# --- ko'chirish ---
@router.get(P + "/transfers")
def api_transfers(request: Request, kind: str = "", status: str = ""):
    c = C(request); guard(c, "kochirish", "ko'chirish arizalari"); return transfers_list(c, kind, status)

@router.get(P + "/transfers/preview")
def api_transfer_preview(request: Request, student_id: int = 0, group_id: int = 0):
    c = C(request); guard(c, "kochirish", "farq fanlari hisobi", f"{student_id} → {group_id}", roles=FULL + ("sirtqi",)); return transfer_preview(c, student_id, group_id)

@router.post(P + "/transfers")
def api_transfer_new(body: TransferIn, request: Request):
    c = C(request); guard(c, "kochirish", "ko'chirish arizasi", body.kind, roles=REG); return create_transfer(c, body)

@router.post(P + "/transfers/{tid}/order")
def api_transfer_order(tid: int, request: Request):
    c = C(request); guard(c, "kochirish", "ko'chirish buyrug'i", f"#{tid}", roles=REG); return transfer_order(c, tid)

class ScoreIn(BaseModel):
    score: int

@router.post(P + "/transfers/diff/{did}")
def api_diff(did: int, body: ScoreIn, request: Request):
    c = C(request); guard(c, "kochirish", "farq fani natijasi", f"#{did}", roles=FULL + ("sirtqi",)); return diff_result(c, did, body.score)

# --- grant ---
@router.get(P + "/grant")
def api_grant(request: Request, round: int = 0):
    c = C(request); guard(c, "grant", "ISFT granti"); return grant_view(c, round)

@router.post(P + "/grant/rounds")
def api_grant_new(request: Request):
    c = C(request); guard(c, "grant", "ISFT granti: yangi raund", roles=("talabalar", "registrator_xodim")); return grant_round_new(c)

@router.post(P + "/grant/rounds/{rid}/submit")
def api_grant_submit(rid: int, request: Request):
    c = C(request); guard(c, "grant", "ISFT granti: komissiyaga", f"#{rid}", roles=("talabalar", "registrator_xodim")); return grant_submit(c, rid)

class GrantDecIn(BaseModel):
    decisions: dict = {}
    note: str = ""

@router.post(P + "/grant/rounds/{rid}/decide")
def api_grant_decide(rid: int, body: GrantDecIn, request: Request):
    c = C(request); guard(c, "grant", "ISFT granti: komissiya qarori", f"#{rid}", roles=LEAD); return grant_decide(c, rid, body.decisions, body.note)

@router.post(P + "/grant/rounds/{rid}/orders")
def api_grant_orders(rid: int, request: Request):
    c = C(request); guard(c, "grant", "ISFT granti: buyruq loyihalari", f"#{rid}", roles=("talabalar", "registrator_xodim")); return grant_orders(c, rid)

# --- bitiruv ---
@router.get(P + "/grad")
def api_grad(request: Request, view: str = "", q: str = "", group: int = 0, offset: int = 0, limit: int = 100):
    c = C(request); guard(c, "bitiruv", "bitiruvchilar", view); return grad_list(c, view, q.strip()[:60], group, offset, min(limit, 500))

@router.post(P + "/grad/{sid}/thesis")
def api_thesis(sid: int, body: ThesisIn, request: Request):
    c = C(request); guard(c, "bitiruv", "bitiruv ishi", str(sid), roles=FULL + ("sirtqi", "kafedra")); return thesis_set(c, sid, body)

class YdaIn(BaseModel):
    score: int
    exam_date: str

@router.post(P + "/grad/{sid}/yda")
def api_yda(sid: int, body: YdaIn, request: Request):
    c = C(request); guard(c, "bitiruv", "YDA natijasi", str(sid), roles=("akademik",)); return yda_set(c, sid, body.score, body.exam_date)

@router.post(P + "/grad/order")
def api_grad_order(body: IdsIn, request: Request):
    c = C(request); guard(c, "bitiruv", "bitirish buyrug'i", f"{len(body.ids)} ta", roles=REG); return grad_order(c, body.ids)

@router.post(P + "/grad/diplomas")
def api_diplomas_reg(request: Request):
    c = C(request); guard(c, "bitiruv", "diplom raqamlari", roles=REG)
    with _lock: n = register_diplomas(_con, c.user["id"])
    return {"ok": True, "registered": n}

@router.get(P + "/grad/diplomas")
def api_diplomas(request: Request, q: str = ""):
    c = C(request); guard(c, "bitiruv", "diplomlar reyestri"); return diplomas_list(c, q.strip()[:60])

@router.get(P + "/grad/{sid}/supplement")
def api_supplement(sid: int, request: Request):
    c = C(request); guard(c, "bitiruv", "diplom ilovasi (.docx)", str(sid), roles=FULL + ("sirtqi", "kafedra"))
    _student_in_scope(c, sid, "diplom ilovasi")
    return _file(supplement_docx(_con, sid, _who(c)), f"diplom_ilovasi_{sid}.docx", DOCX)

# =============================================================================================
# Demo ma'lumotlar (sun'iy; bir marta — flow_meta 'seeded'). Sanalar bugungi kunga nisbatan (dateshift hikoyasi bilan mos).
# =============================================================================================
TOPICS = ["«{d}» yo'nalishida raqamli texnologiyalarni joriy etish samaradorligini baholash",
          "Korxona faoliyatida {d} sohasidagi zamonaviy yondashuvlar: muammo va yechimlar",
          "{d}: xalqaro tajriba va O'zbekiston amaliyoti (qiyosiy tahlil)",
          "Tijorat tashkilotlarida {d} jarayonlarini takomillashtirish yo'llari",
          "{d} sohasida sun'iy intellekt vositalaridan foydalanish imkoniyatlari",
          "Hududiy rivojlanishda {d} omillarining ta'sirini baholash",
          "{d} bo'yicha ko'rsatkichlar tizimini ishlab chiqish (amaliy misolda)"]

def _meta_get(con, k):
    r = con.execute("SELECT v FROM flow_meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else None

def _sign_hist(con, oid: int, date: str):
    """Seed: loyihani rektor imzolaydi (ta'sir bazaga o'tadi), sana tarixiy qilib qo'yiladi."""
    from . import orders as ORD
    con.execute("UPDATE orders SET status='yuborilgan', submitted_at=? WHERE id=?", (date + "T10:00:00", oid)); con.commit()
    o = db.one(con, "SELECT * FROM orders WHERE id=?", (oid,))
    ORD.sign(o, rbac.ctx_for(con, db.one(con, "SELECT id FROM users WHERE role='rektor' ORDER BY id LIMIT 1")["id"]), "http://localhost:8000/")
    con.execute("UPDATE orders SET order_date=?, signed_at=?, applied_at=?, historic=1 WHERE id=?", (date, date + "T16:00:00", date + "T16:00:00", oid))
    con.execute("UPDATE student_changes SET ts=? WHERE order_id=?", (date + "T16:00:00", oid)); con.commit()

def _mon_after(d: dt.date) -> dt.date:
    return d + dt.timedelta(days=(7 - d.weekday()) % 7 or 7)

def seed_sessions(con, R):
    today = _today(); akad = db.one(con, "SELECT id FROM users WHERE role='akademik' ORDER BY id LIMIT 1")["id"]
    sir = db.one(con, "SELECT id FROM users WHERE role='sirtqi' ORDER BY id LIMIT 1")
    sir = sir["id"] if sir else akad
    s0 = _mon_after(today + dt.timedelta(days=3))
    def S(name, form, season, sem, st, en, status, by, wins=(), note=""):
        cur = con.execute("""INSERT INTO exam_sessions(name,study_form,season,semester,start,end,status,published_at,published_by,created_by,created_at,note)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (name, form, season, sem, _iso(st), _iso(en), status,
                                                                 _now() if status in ("e'lon qilingan", "yakunlangan") else None, by if status != "reja" else None, by, _now(), note))
        for wn, a, b in wins: con.execute("INSERT INTO retake_windows(session_id,name,start,end) VALUES(?,?,?,?)", (cur.lastrowid, wn, _iso(a), _iso(b)))
        return cur.lastrowid
    S("2025-2026 o'quv yili, bahorgi semestr — yozgi sessiya (kunduzgi)", "kunduzgi", "yozgi", 0, "2026-06-08", "2026-06-27", "yakunlangan", akad,
      [("Yozgi qayta topshirish", "2026-08-24", "2026-09-13"), ("Kuzgi qo'shimcha qayta topshirish", today - dt.timedelta(days=12), today + dt.timedelta(days=2))])
    S("2025-2026 o'quv yili, bahorgi semestr — yozgi sessiya (sirtqi)", "sirtqi", "yozgi", 0, "2026-05-18", "2026-06-13", "yakunlangan", sir,
      [("Yozgi qayta topshirish", "2026-08-24", "2026-09-13")])
    k = S(f"{AR.SEMESTERS[1]} — qishki sessiya (kunduzgi)", "kunduzgi", "qishki", 1, "2027-01-04", "2027-01-23", "e'lon qilingan", akad,
          [("Qayta topshirish", "2027-02-01", "2027-02-13")])
    s = S(f"{AR.SEMESTERS[1]} — qishki o'quv-imtihon sessiyasi (sirtqi)", "sirtqi", "qishki", 1, s0, s0 + dt.timedelta(days=26), "e'lon qilingan", sir,
          [("Qayta topshirish", s0 + dt.timedelta(days=29), s0 + dt.timedelta(days=40))])
    m = S(f"{AR.SEMESTERS[1]} — qishki sessiya (masofaviy)", "masofaviy", "qishki", 1, "2027-01-11", "2027-01-30", "loyiha", akad,
          note="Jadval tuzilmoqda: 2 ta ataylab qoldirilgan to'qnashuv — tekshiruv namunasi")
    S("2026-2027 o'quv yili, bahorgi semestr — yozgi sessiya (sirtqi)", "sirtqi", "yozgi", 2, "2027-05-17", "2027-06-12", "reja", sir)
    S("2026-2027 o'quv yili, bahorgi semestr — yozgi sessiya (kunduzgi)", "kunduzgi", "yozgi", 2, "2027-06-07", "2027-06-26", "reja", akad)
    con.commit()
    generate(con, k, by_user=akad); generate(con, s, by_user=sir)
    mg = [r[0] for r in con.execute("SELECT id FROM groups_ WHERE form='masofaviy' ORDER BY id LIMIT 6")]
    generate(con, m, group_ids=mg, by_user=akad)
    a = db.rows(con, "SELECT * FROM exam_slots WHERE session_id=? ORDER BY id LIMIT 2", (m,))
    if len(a) == 2:   # to'qnashuvlar: bir xonada bir vaqtda ikki guruh; bitta imtihon oluvchi bir vaqtda ikki joyda
        x, y = a
        other_g = con.execute("SELECT id FROM groups_ WHERE form='masofaviy' AND id NOT IN (%s) ORDER BY id LIMIT 2" % ",".join(map(str, mg))).fetchall()
        if len(other_g) == 2:
            con.execute("""INSERT INTO exam_slots(session_id,group_id,subject,exam_date,start_time,end_time,room_id,examiner_id,created_by,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", (m, other_g[0][0], x["subject"], x["exam_date"], x["start_time"], x["end_time"], x["room_id"], None, akad, _now()))
            free = con.execute("SELECT id FROM rooms WHERE kind='auditoriya' ORDER BY capacity DESC LIMIT 1").fetchone()[0]
            con.execute("""INSERT INTO exam_slots(session_id,group_id,subject,exam_date,start_time,end_time,room_id,examiner_id,created_by,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", (m, other_g[1][0], y["subject"], y["exam_date"], y["start_time"], y["end_time"], free, y["examiner_id"], akad, _now()))
    con.commit()

def seed_attempts(con, R) -> dict:
    """Yozgi qayta topshirishda o'tmaganlar (→ qayta o'qish taklifi) va kuzgi qo'shimcha muddatdagi qayta topshirishlar (yaqinda e'lon qilingan)."""
    today = _today()
    pool = db.rows(con, f"""SELECT g.student_id sid, g.subject, g.semester, g.score FROM grades g JOIN students s ON s.id=g.student_id
        WHERE g.semester=0 AND g.score<{AR.PASS} AND COALESCE(g.attempts,1)=1 AND s.status='faol' AND s.study_form IN ('kunduzgi','sirtqi')
        ORDER BY g.student_id, g.subject""")
    R.shuffle(pool)
    used, summer, autumn = set(), [], []
    for r in pool:
        if r["sid"] in used: continue
        if len(summer) < 120: summer.append(r)
        elif len(autumn) < 70: autumn.append(r)
        else: break
        used.add(r["sid"])
    for r in summer:
        d = dt.date(2026, 8, 24) + dt.timedelta(days=R.randint(0, 20))
        record_attempt(con, r["sid"], r["subject"], 0, "qayta topshirish", R.randint(max(8, r["score"] - 8), AR.PASS - 1), d.isoformat(), None, "yozgi qayta topshirish")
    for i, r in enumerate(autumn):
        d = today - dt.timedelta(days=(1 + i % 2) if i < 14 else R.randint(3, 10))
        sc = R.randint(AR.PASS, 64) if R.random() < 0.6 else R.randint(max(8, r["score"] - 6), AR.PASS - 1)
        record_attempt(con, r["sid"], r["subject"], 0, "qayta topshirish", sc, d.isoformat(), None, "kuzgi qo'shimcha qayta topshirish")
    con.commit()
    return {"summer": summer, "autumn": autumn}

def _kaf_user(con, dept):
    r = con.execute("SELECT id, full_name FROM users WHERE role='kafedra' AND department_id=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (dept or 0,)).fetchone()
    return {"id": r[0], "full_name": r[1]} if r else None

def seed_appeals(con, R, att):
    today = _today()
    im = db.one(con, "SELECT id, full_name FROM users WHERE role='imtihon' ORDER BY id LIMIT 1")
    ak = db.one(con, "SELECT id, full_name FROM users WHERE role='akademik' ORDER BY id LIMIT 1")
    reg = db.one(con, "SELECT id FROM users WHERE role='talabalar' ORDER BY id LIMIT 1")["id"]
    reasons = ["Yozma ishimdagi 3-savol javobi to'liq baholanmagan deb hisoblayman", "Test qismida kalit bilan mos javoblarim hisobga olinmagan",
               "Og'zaki qismda berilgan qo'shimcha savol dasturdan tashqarida edi", "Ish varaqamdagi hisob-kitob to'g'ri, lekin ball qo'yilmagan"]
    recent = [r for r in att["autumn"] if con.execute("SELECT at FROM grade_attempts WHERE student_id=? AND subject=? AND semester=0 ORDER BY attempt DESC LIMIT 1",
                                                       (r["sid"], r["subject"])).fetchone()[0] >= (today - dt.timedelta(days=2)).isoformat()]
    made = []
    for i, r in enumerate(recent[:4]):
        try: a = create_appeal(con, r["sid"], r["subject"], 0, reasons[i % len(reasons)], "ariza", reg)
        except ValueError: continue
        made.append(a)
    def vote(a, member, user, v, y=None):
        if not user: return
        con.execute("INSERT OR IGNORE INTO appeal_votes(appeal_id,member,user_id,user_name,vote,yakuniy,note,at) VALUES(?,?,?,?,?,?,?,?)",
                    (a["id"], member, user["id"], user["full_name"], v, y, "ish varaqasi qayta ko'rib chiqildi", _now()))
        con.execute("UPDATE grade_appeals SET status='ko''rib chiqilmoqda' WHERE id=? AND status='yangi'", (a["id"],))
    if len(made) >= 3:
        vote(made[1], "imtihon", im, "saqlash")
        vote(made[2], "imtihon", im, "oshirish", min(AR.YAKUNIY_MAX, (made[2]["yakuniy_old"] or 0) + 6))
        vote(made[2], "kafedra", _kaf_user(con, made[2]["dept_id"]), "oshirish", min(AR.YAKUNIY_MAX, (made[2]["yakuniy_old"] or 0) + 5))
    # o'tgan apellyatsiyalar (yozgi qayta topshirish natijalari bo'yicha) — qaror chiqarilgan
    past = db.rows(con, """SELECT student_id sid, subject, semester, at FROM grade_attempts a WHERE kind='qayta topshirish' AND counted=1 AND semester=0
                           AND at BETWEEN '2026-08-24' AND '2026-09-13' AND EXISTS (SELECT 1 FROM students s WHERE s.id=a.student_id AND s.status='faol')
                           ORDER BY student_id LIMIT 400""")
    R.shuffle(past)
    plan = [("saqlash", 0), ("saqlash", 0), ("oshirish", 6), ("pasaytirish", -4)]
    for (dec, dy), r in zip(plan, past[:4]):
        g = db.one(con, "SELECT * FROM grades WHERE student_id=? AND subject=? AND semester=?", (r["sid"], r["subject"], r["semester"]))
        t = db.one(con, "SELECT id, department_id FROM teachers WHERE id=?", (g["teacher_id"] or 0,)) or {}
        at = dt.date.fromisoformat(r["at"][:10])
        cur = con.execute("""INSERT INTO grade_appeals(student_id,subject,semester,attempt,dept_id,examiner_id,oraliq,yakuniy_old,score_old,published_at,filed_at,deadline,
            reason,channel,status,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["sid"], r["subject"], 0, g["attempts"], t.get("department_id"), t.get("id"), g["oraliq"], g["yakuniy"], g["score"], at.isoformat(),
             (at + dt.timedelta(days=1)).isoformat() + "T11:20:00", (at + dt.timedelta(days=3)).isoformat(), R.choice(reasons), "ariza", "ko'rib chiqilmoqda", reg))
        a = db.one(con, "SELECT * FROM grade_appeals WHERE id=?", (cur.lastrowid,))
        if dec == "pasaytirish" and (g["score"] or 0) + dy < AR.PASS + 3: dec, dy = "saqlash", 0   # demo: pasaytirish qarzga olib kelmasin
        ny = max(0, min(AR.YAKUNIY_MAX, (g["yakuniy"] or 0) + dy))
        for mem, u in (("imtihon", im), ("akademik", ak), ("kafedra", _kaf_user(con, a["dept_id"]))):
            if u: con.execute("INSERT INTO appeal_votes(appeal_id,member,user_id,user_name,vote,yakuniy,note,at) VALUES(?,?,?,?,?,?,?,?)",
                              (a["id"], mem, u["id"], u["full_name"], dec, None if dec == "saqlash" else ny, "", (at + dt.timedelta(days=3)).isoformat() + "T15:00:00"))
        try: decide_core(con, a, dec, None if dec == "saqlash" else ny, "Komissiya yig'ilishi bayonnomasi asosida", ak)
        except ValueError: continue
        when = (at + dt.timedelta(days=4)).isoformat() + "T12:00:00"
        con.execute("UPDATE grade_appeals SET decided_at=? WHERE id=?", (when, a["id"]))
        con.execute("UPDATE grade_attempts SET at=? WHERE student_id=? AND subject=? AND semester=0 AND kind='apellyatsiya'", (when[:10], r["sid"], r["subject"]))
    con.commit()

def seed_restudy(con, R):
    sync_restudy(con)
    today = _today()
    studs = [r[0] for r in con.execute("SELECT DISTINCT student_id FROM restudy WHERE failed_at < '2026-10-01' ORDER BY student_id")]
    R.shuffle(studs)
    n = len(studs); reg = rbac.ctx_for(con, db.one(con, "SELECT id FROM users WHERE role='talabalar' ORDER BY id LIMIT 1")["id"])
    for i, sid in enumerate(studs):
        rs = db.rows(con, "SELECT * FROM restudy WHERE student_id=? AND decision='kutilmoqda'", (sid,))
        if not rs: continue
        dd = dt.date.fromisoformat(rs[0]["offered_at"]) + dt.timedelta(days=R.randint(3, 20))
        if i < n * 0.65:
            amt = [(r["credits"] or 0) * (r["per_credit"] or 0) for r in rs]
            frac = R.choice([1, 1, 1, 1, 0.5, 0])
            for r, a in zip(rs, amt):
                con.execute("UPDATE restudy SET decision='qayta_oqish', decided_at=?, decided_by=?, amount=?, paid=?, paid_at=?, pay_due=? WHERE id=?",
                            (dd.isoformat(), reg.user["id"], a, int(a * frac), dd.isoformat() if frac else None,
                             (dd + dt.timedelta(days=RULES["restudy_pay_days"])).isoformat(), r["id"]))
        elif i < n * 0.65 + 2:
            s = db.one(con, """SELECT s.*, g.direction, g.course, g.form gform, g.level glevel FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""", (sid,))
            g = db.one(con, "SELECT * FROM groups_ WHERE direction=? AND level=? AND form=? AND course=? ORDER BY id LIMIT 1",
                       (s["direction"], s["glevel"], s["gform"], max(1, s["course"] - 1)))
            if not g or g["id"] == s["group_id"]: continue
            o = _create_order(_reg_ctx(con, s), "kursda_qoldirish", [{"student_id": sid, "data": {"group_to": g["id"]}}],
                              {"date_from": today.isoformat(), "group_to": g["id"], "reason": "qayta topshirishda o'tmagan fanlar"},
                              "Talaba harakati: kursda qoldirish (talaba arizasi)")
            con.execute("UPDATE restudy SET decision='kursda_qoldirish', decided_at=?, decided_by=?, order_id=? WHERE student_id=? AND decision='kutilmoqda'",
                        (dd.isoformat(), reg.user["id"], o["id"], sid))
        elif i < n * 0.65 + 4:
            con.execute("UPDATE restudy SET decision='rad', decided_at=?, decided_by=?, note='talaba qayta o''qishdan va kursda qoldirishdan voz kechdi' WHERE student_id=? AND decision='kutilmoqda'",
                        (dd.isoformat(), reg.user["id"], sid))
    con.commit()
    # tarixiy: muddati o'tib chetlashtirilganlar (imzolangan), keyin — yangi chetlashtirish loyihasi
    cands = db.rows(con, f"""SELECT r.student_id sid, MAX(r.deadline) dl, GROUP_CONCAT(r.subject, '; ') subj, s.study_form FROM restudy r JOIN students s ON s.id=r.student_id
                             WHERE r.decision='kutilmoqda' AND r.deadline < ? AND s.status='faol' AND s.study_form='kunduzgi' GROUP BY 1 ORDER BY 1""", (today.isoformat(),))
    expelled = []
    if len(cands) >= 5:
        old = cands[:2]
        date = min(today - dt.timedelta(days=5), dt.date.fromisoformat(max(x["dl"] for x in old)) + dt.timedelta(days=5)).isoformat()
        o = _create_order(reg, "akademik_qarz", [{"student_id": x["sid"], "data": {"reason": x["subj"][:280]}} for x in old], {"date_from": date},
                          "Talaba harakati: yozgi qayta topshirishdan keyin muddatida tugatilmagan akademik qarz")
        _sign_hist(con, o["id"], date)
        con.execute(f"UPDATE restudy SET decision='chetlashtirish', order_id=? WHERE student_id IN ({','.join(str(x['sid']) for x in old)}) AND decision='kutilmoqda'", (o["id"],))
        expelled = [x["sid"] for x in old]
        new = cands[2:5]
        o2 = _create_order(reg, "akademik_qarz", [{"student_id": x["sid"], "data": {"reason": x["subj"][:280]}} for x in new], {"date_from": today.isoformat()},
                           "Talaba harakati: qayta topshirishdan keyin muddatida tugatilmagan akademik qarz (loyiha)")
        con.execute(f"UPDATE restudy SET order_id=? WHERE student_id IN ({','.join(str(x['sid']) for x in new)}) AND decision='kutilmoqda'", (o2["id"],))
    con.commit()
    return expelled

def seed_transfers(con, R, expelled):
    reg = rbac.ctx_for(con, db.one(con, "SELECT id FROM users WHERE role='talabalar' ORDER BY id LIMIT 1")["id"])
    busy = {r[0] for r in con.execute("""SELECT i.student_id FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                                         WHERE o.status IN ('loyiha','yuborilgan','kelishilgan')""")} | {r[0] for r in con.execute("SELECT student_id FROM restudy")}
    def pick(sql, args=()):
        for r in con.execute(sql, args).fetchall():
            if r[0] not in busy: busy.add(r[0]); return r[0]
    def grp(sql, args=()):
        r = con.execute(sql, args).fetchone(); return r[0] if r else None
    plans = []
    s1 = pick("SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND g.form='kunduzgi' AND g.level='bakalavr' AND g.course=2 AND g.direction='Iqtisodiyot' ORDER BY s.id LIMIT 50")
    plans.append((TransferIn(kind="ichki", student_id=s1, to_group_id=grp("SELECT id FROM groups_ WHERE form='kunduzgi' AND course=2 AND direction='Bank ishi va audit' ORDER BY id"),
                             reason="yo'nalishni o'zgartirish (bank ishi bo'yicha mutaxassislik)"), False, 1))
    s2 = pick("SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND g.form='kunduzgi' AND g.level='bakalavr' AND g.course=3 AND g.direction='Marketing' ORDER BY s.id DESC LIMIT 50")
    plans.append((TransferIn(kind="ichki", student_id=s2, to_group_id=grp("SELECT id FROM groups_ WHERE form='sirtqi' AND course=3 AND direction='Marketing' ORDER BY id"),
                             reason="ishga joylashgani sababli sirtqi ta'limga o'tish"), True, 0))
    s3 = pick("SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol' AND g.form='kunduzgi' AND g.level='bakalavr' AND g.course=2 AND g.direction='Menejment' ORDER BY s.id LIMIT 50")
    plans.append((TransferIn(kind="ichki", student_id=s3, to_group_id=grp("SELECT id FROM groups_ WHERE form='kunduzgi' AND course=2 AND direction='Marketing' ORDER BY id"),
                             reason="yo'nalishni o'zgartirish"), True, 2))
    g_in = db.one(con, "SELECT * FROM groups_ WHERE form='kunduzgi' AND course=2 AND direction='Iqtisodiyot' ORDER BY id DESC LIMIT 1")
    first = [r[0] for r in con.execute("SELECT subject FROM curriculum WHERE direction=? AND level='bakalavr' AND sem_no<=2 ORDER BY sem_no, id", (g_in["direction"],))]
    plans.append((TransferIn(kind="kirish", applicant="Yo'ldosheva Kamola Anvar qizi", other_otm="Toshkent davlat iqtisodiyot universiteti (namuna)", to_group_id=g_in["id"],
                             prior_subjects=first[:-3], reason="yashash joyi o'zgargani munosabati bilan"), False, 0))
    s5 = pick("SELECT s.id FROM students s WHERE s.status='faol' AND s.study_form='sirtqi' ORDER BY s.id DESC LIMIT 80")
    plans.append((TransferIn(kind="chiqish", student_id=s5, other_otm="Samarqand davlat universiteti (namuna)", reason="oilaviy sharoit"), True, 0))
    if expelled:
        e = expelled[0]; busy.add(e)
        plans.append((TransferIn(kind="tiklash", student_id=e, to_group_id=grp("SELECT group_id FROM students WHERE id=?", (e,)),
                                 reason="akademik qarzni to'lov asosida qayta o'qish majburiyati bilan tiklash"), False, 0))
    s7 = pick("""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='akademik ta''til' AND g.form='kunduzgi' AND g.course>=2 ORDER BY s.id""")
    if s7:
        g7 = db.one(con, "SELECT g.* FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (s7,))
        to = grp("SELECT id FROM groups_ WHERE direction=? AND level=? AND form=? AND course=? ORDER BY id", (g7["direction"], g7["level"], g7["form"], max(1, g7["course"] - 1)))
        plans.append((TransferIn(kind="tatildan_qaytish", student_id=s7, to_group_id=to or g7["id"], reason="ta'til muddati tugadi"), False, 0))
    for b, order, passed in plans:
        if b.kind != "kirish" and not b.student_id: continue
        try: r = create_transfer_core(con, reg.user["id"], b)
        except ValueError as e: print("talaba harakati seed (ko'chirish):", e); continue
        for d in db.rows(con, "SELECT id FROM transfer_diff WHERE transfer_id=? ORDER BY id LIMIT ?", (r["id"], passed)):
            con.execute("UPDATE transfer_diff SET status='topshirildi', score=?, passed_at=? WHERE id=?", (R.randint(52, 80), _now(), d["id"]))
        if order:
            s = db.one(con, "SELECT study_form FROM students WHERE id=?", (b.student_id,)) if b.student_id else {"study_form": "kunduzgi"}
            try: transfer_order_core(con, _reg_ctx(con, s), r["id"])
            except ValueError as e: print("talaba harakati seed (buyruq):", e)
    con.commit()

def seed_grant(con, R):
    rows = db.rows(con, """SELECT s.id, g.course FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.payment_type='grant' AND s.study_form='kunduzgi'
                           AND s.level='bakalavr' ORDER BY s.id""")
    by = {}
    for r in rows: by.setdefault(r["course"], []).append(r["id"])
    for course, ids in by.items():
        soc = set(R.sample(ids, min(RULES["grant"]["social"], len(ids) // 6)))
        con.executemany("INSERT OR REPLACE INTO grant_holders(student_id,category,since) VALUES(?,?,?)",
                        [(i, "ijtimoiy" if i in soc else "iqtidor", f"{AR.intake_year(course)}-08-28") for i in ids])
    con.commit()
    reg = db.one(con, "SELECT id FROM users WHERE role='talabalar' ORDER BY id LIMIT 1")["id"]
    rid = create_round(con, reg, status="komissiya")
    con.execute("UPDATE grant_rounds SET submitted_at=? WHERE id=?", (_now(), rid)); con.commit()

def seed_theses(con, R):
    rows = db.rows(con, f"""SELECT s.id, s.level, g.direction, g.department_id, g.id gid FROM students s JOIN groups_ g ON g.id=s.group_id
                            WHERE s.status IN ('faol','akademik ta''til') AND ((s.level='bakalavr' AND g.course=4) OR (s.level='magistr' AND g.course=2))""")
    tea = {}
    for t in db.rows(con, "SELECT id, department_id FROM teachers ORDER BY id"): tea.setdefault(t["department_id"], []).append(t["id"])
    allt = [t for v in tea.values() for t in v]
    mas = {r["student_id"]: r for r in db.rows(con, "SELECT * FROM masters")}
    out = []
    for r in rows:
        dday = dt.date(2027, 5, 24) + dt.timedelta(days=r["gid"] % 24)
        if dday.weekday() == 6: dday += dt.timedelta(days=1)
        m = mas.get(r["id"])
        if r["level"] == "magistr" and m:
            out.append((r["id"], THESIS_KIND["magistr"], m["topic"], m["supervisor_id"], (dday + dt.timedelta(days=10)).isoformat(),
                        "himoyaga tayyor" if m["stage"] == "Dastlabki himoya" else "tasdiqlangan", None))
            continue
        if R.random() < 0.08:
            out.append((r["id"], THESIS_KIND[r["level"]], None, None, dday.isoformat(), "tanlanmagan", None)); continue
        sup = R.choice(tea.get(r["department_id"]) or allt)
        out.append((r["id"], THESIS_KIND[r["level"]], R.choice(TOPICS).format(d=r["direction"]), sup, dday.isoformat(), "tasdiqlangan", None))
    con.executemany("INSERT OR IGNORE INTO theses(student_id,kind,topic,supervisor_id,defense_date,status,score,updated_at) VALUES(?,?,?,?,?,?,?,'" + _now() + "')", out)
    con.commit()

def seed_graduates(con, R):
    """2026-yil magistr bitiruvchilari (2024 qabul; semestrlar −3..0 — mavjud akademik taqvim ichida): imzolangan bitirish buyrug'i va
    diplomlar reyestri; har guruhdan bittadan «kechiktirilgan» bitiruvchi — iyunda qarzi bor edi, sentabrda qayta topshirdi, oktabrda
    qo'shimcha YDA — hozir bitirish talablariga javob beradi (buyruq loyihasini Registrator tuzadi)."""
    from . import seed as SD
    tea = {}
    for t in db.rows(con, "SELECT id, department_id FROM teachers ORDER BY id"): tea.setdefault(t["department_id"], []).append(t["id"])
    base = db.rows(con, "SELECT * FROM groups_ WHERE level='magistr' AND course=2 AND name LIKE '%-2501'")
    qabul = db.one(con, "SELECT id, version FROM orders WHERE kind='qabul' AND study_form='kunduzgi' AND order_date LIKE '2024-08%' AND status='imzolangan' ORDER BY id LIMIT 1")
    kurs = db.one(con, "SELECT id, version FROM orders WHERE kind='kurs' AND study_form='kunduzgi' AND order_date LIKE '2025-08%' AND status='imzolangan' ORDER BY id LIMIT 1")
    grads, late = [], []
    for b in base:
        name = b["name"].replace("-2501", "-2401")
        if not name.startswith("MAG-"): name = "MAG-" + name   # bakalavr guruhlari nomi bilan to'qnashmasin (PED-2401 — bakalavr)
        if db.one(con, "SELECT 1 x FROM groups_ WHERE name=?", (name,)): continue
        gid = con.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,?)",
                          (b["department_id"], b["faculty_id"], name, 2, b["direction"], "magistr", "kunduzgi")).lastrowid
        plan = db.rows(con, "SELECT sem_no, subject, credits FROM curriculum WHERE direction=? AND level='magistr' ORDER BY sem_no, id", (b["direction"],))
        for k in range(10):
            g = "M" if R.random() < 0.5 else "F"
            surn = R.choice(SD.SURN)
            nm = f"{surn} {R.choice(SD.MALE)} {R.choice(SD.PATR_M)} o'g'li" if g == "M" else f"{surn}a {R.choice(SD.FEMALE)} {R.choice(SD.PATR_M)} qizi"
            sid = con.execute("""INSERT INTO students(hemis_id,full_name,group_id,faculty_id,gender,region,payment_type,contract_amount,paid_amount,attendance,status,level,study_form)
                                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (f"3{R.randint(10**11, 10**12 - 1)}", nm, gid, b["faculty_id"], g, R.choice(SD.REGIONS), "kontrakt",
                                                                       contract_rate(con, "kunduzgi", "magistr"), contract_rate(con, "kunduzgi", "magistr"), None, "faol", "magistr", "kunduzgi")).lastrowid
            is_late = k == 9
            ab = R.choice([88, 82, 76, 70, 64]) if k < 3 else R.gauss(68, 8)
            debt_subj = None
            for p in plan:
                t = p["sem_no"] - 4   # 1..4 → −3..0
                sc = max(41, min(100, round(R.gauss(ab, 5))))
                if k == 0: sc = max(sc, 66 if R.random() < 0.9 else 60)   # imtiyozli nomzod
                o, y = AR.split_score(sc, f"grad{sid}{p['subject']}")
                if is_late and t == 0 and debt_subj is None: sc, (o, y), debt_subj = 34, AR.split_score(34, f"late{sid}"), p["subject"]
                con.execute("INSERT INTO grades(student_id,subject,teacher_id,score,semester,oraliq,yakuniy,credits,sem_no,attempts) VALUES(?,?,?,?,?,?,?,?,?,1)",
                            (sid, p["subject"], R.choice(tea.get(b["department_id"]) or [1]), sc, t, o, y, p["credits"], p["sem_no"]))
            sup = R.choice(tea.get(b["department_id"]) or [1])
            th = 70 if k == 0 else R.randint(55, 92)
            con.execute("INSERT OR REPLACE INTO theses(student_id,kind,topic,supervisor_id,defense_date,status,score,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (sid, THESIS_KIND["magistr"], R.choice(TOPICS).format(d=b["direction"]), sup, "2026-06-15", "himoya qilindi", th, "2026-06-15T15:00:00"))
            con.execute("INSERT OR REPLACE INTO yda_results(student_id,subject,exam_date,score,at) VALUES(?,?,?,?,?)",
                        (sid, yda_subject("magistr", b["direction"]), "2026-10-20" if is_late else "2026-06-22", 74 if k == 0 else R.randint(56, 90), "2026-06-22T12:00:00"))
            if is_late:
                record_attempt(con, sid, debt_subj, 0, "qayta topshirish", R.randint(48, 60), "2026-09-08", None, "yozgi qayta topshirish")
                late.append(sid)
            else: grads.append(sid)
            for o in (qabul, kurs):
                if o: con.execute("INSERT INTO order_students(order_id,version,student_id,hemis_id,full_name,group_id,group_name,course,data,applied) "
                                  "SELECT ?,?,id,hemis_id,full_name,group_id,?,?,'{}',1 FROM students WHERE id=?", (o["id"], o["version"], name, 1 if o is qabul else 2, sid))
    for o in (qabul, kurs):
        if o: con.execute("UPDATE orders SET count=(SELECT COUNT(*) FROM order_students WHERE order_id=? AND version=?) WHERE id=?", (o["id"], o["version"], o["id"]))
    con.commit()
    AR.refresh_student_metrics(con, grads + late)
    if grads:
        reg = rbac.ctx_for(con, db.one(con, "SELECT id FROM users WHERE role='talabalar' ORDER BY id LIMIT 1")["id"])
        o = _create_order(reg, "bitirish", [{"student_id": s} for s in grads], {"date_from": "2026-07-01"}, "Talaba harakati: 2026-yil magistr bitiruvchilari")
        _sign_hist(con, o["id"], "2026-07-01")
        register_diplomas(con)
    con.commit()

def seed(con, force=False) -> bool:
    if _meta_get(con, "seeded") and not force: return False
    if not con.execute("SELECT 1 FROM students LIMIT 1").fetchone() or not con.execute("SELECT 1 FROM grades WHERE semester=0 LIMIT 1").fetchone(): return False
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='rooms'").fetchone(): return False
    R = random.Random(2611)
    import time; t0 = time.time()
    seed_sessions(con, R)
    att = seed_attempts(con, R)
    seed_appeals(con, R, att)
    expelled = seed_restudy(con, R)
    seed_transfers(con, R, expelled)
    seed_graduates(con, R)
    seed_grant(con, R)
    seed_theses(con, R)
    con.execute("INSERT OR REPLACE INTO flow_meta(k,v) VALUES('seeded',?)", (_now(),)); con.commit()
    print(f"Talaba harakati demo: {round(time.time() - t0, 1)} s · sessiyalar {con.execute('SELECT COUNT(*) FROM exam_sessions').fetchone()[0]}, "
          f"jadval {con.execute('SELECT COUNT(*) FROM exam_slots').fetchone()[0]}, apellyatsiya {con.execute('SELECT COUNT(*) FROM grade_appeals').fetchone()[0]}, "
          f"qayta o'qish {con.execute('SELECT COUNT(*) FROM restudy').fetchone()[0]}, ko'chirish {con.execute('SELECT COUNT(*) FROM transfers').fetchone()[0]}, "
          f"grant nomzodlari {con.execute('SELECT COUNT(*) FROM grant_candidates').fetchone()[0]}, diplom {con.execute('SELECT COUNT(*) FROM diplomas').fetchone()[0]}")
    return True

def init(con):
    """Jadvallar + (birinchi marta) demo ma'lumotlar. orders.bind dan KEYIN chaqiriladi (buyruq loyihalari Buyruqlar moduli orqali tuziladi)."""
    global _con
    if _con is None: _con = con
    con.executescript(SCHEMA); con.commit()
    try:
        AR.ensure_schema(con)
        with _lock: seed(con)
    except Exception as e:   # demo ma'lumot ilovani to'xtatmasin
        import traceback; traceback.print_exc(); print("academic_flows.seed:", e)
        try: con.rollback()
        except Exception: pass

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
