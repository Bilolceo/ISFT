"""Talaba kabineti (/talaba) — talabaning o'z-o'ziga xizmat ko'rsatish portali. Batafsil: docs/talaba-kabineti.md.

Kirish va sessiyalar xodimlar tizimidan ALOHIDA:
  * HEMIS ID + parol. Sinov rejimida har bir talabaning boshlang'ich paroli — ISFT_CORE_STUDENT_DEMO_PASSWORD (standart "Talaba2026").
    Xesh (rbac.hash_password, PBKDF2) birinchi muvaffaqiyatli kirishda yaratiladi (student_auth); birinchi kirishda parolni almashtirish majburiy.
  * Cookie — "tsid" (xodimlarniki "sid"), jadval — student_sessions (token SHA-256 xeshi, pw_tag — parol o'zgarsa sessiyalar bekor bo'ladi).
    Xodim cookie'si talaba API'sida, talaba tokeni xodim API'sida ishlamaydi (har biri faqat o'z jadvalida qidiriladi).
  * Urinishlar cheklovi (sessions.Limiter): bitta HEMIS ID ga 10 daqiqada 5 ta, bitta IP dan 20 ta xato.
  * Faqat «faol» yoki «akademik ta'til» maqomidagi talaba kira oladi.
  * Har bir amal audit jurnaliga (audit_log: user_id NULL, kanal «talaba», talaba — detail maydonida).

Talaba faqat O'Z ma'lumotini ko'radi: barcha endpointlar talaba id sini sessiyadan oladi; murojaat / sessiya id lari egasi bo'yicha tekshiriladi.
Boshqa talabalarning ismi hech qayerda ko'rsatilmaydi (reyting — faqat o'rin raqami).

Murojaatlar (student_requests — shu modul jadvali): sababli qoldirish hujjati (PDF/JPG, app/filecheck.py) va o'qish joyidan ma'lumotnoma
(uz/en). Kunduzgi va masofaviy talabalarniki — Registrator ofisiga (boshliq #17, xodim #43), sirtqi talabalarniki — Sirtqi bo'limga (#27).
Xodimlar ro'yxati: /talaba/xodim (shu sahifa, xodim cookie'si bilan). Ma'lumotnoma documents.issue("study_cert") orqali beriladi.
"""
import base64, binascii, datetime as dt, hashlib, hmac, json, os, re, secrets, sqlite3, time, uuid
from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import db, rbac, clock, academic_rules as AR, sessions as SS, filecheck as FC
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "static" / "talaba.html"

COOKIE = "tsid"
TTL = 12 * 3600
DEMO_PASSWORD = os.getenv("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
ALLOWED_STATUS = ("faol", "akademik ta'til")
RES = "talaba"
FILES = Path(os.getenv("ISFT_CORE_TALABA_DIR") or (db.DATA_DIR / "talaba_files"))
MAX_BYTES = 10 * 1024 * 1024
EXCUSE_EXT = ("pdf", "jpg", "jpeg")
OPEN_LIMIT = 5                          # bir vaqtda ochiq murojaatlar (har turdan) — ko'pi bilan

LOGIN_HEMIS = SS.Limiter(5, 600)        # bitta HEMIS ID: 10 daqiqada 5 ta xato
LOGIN_IP = SS.Limiter(20, 600)          # bitta IP: 10 daqiqada 20 ta xato
PW_LIMIT = SS.Limiter(5, 600)           # parolni almashtirish: joriy parol 5 marta xato — blok
UPLOAD_LIMIT = SS.Limiter(10, 3600)     # rad etilgan fayllar: soatiga 10 ta

# Xodimlar tomoni: lavozim → navbat (bo'lim). Registrator ofisi — kunduzgi va masofaviy, Sirtqi bo'lim — faqat sirtqi talabalar.
STAFF_UNIT = {"talabalar": "talabalar", "registrator_xodim": "talabalar", "sirtqi": "sirtqi"}
UNIT_NAME = {"talabalar": AR.REGISTRAR_UNIT, "sirtqi": AR.SIRTQI_UNIT}
KINDS = {"sababli": "Sababli qoldirish hujjati", "malumotnoma": "O'qish joyidan ma'lumotnoma"}
REQ_ST = {"yangi": "Ko'rib chiqilmoqda", "qabul": "Qabul qilindi", "rad": "Rad etildi", "berildi": "Tayyor — yuklab olish mumkin"}
LANGS = {"uz": "O'zbekcha", "en": "Inglizcha"}
RETAKE_ST = {"berildi": "Varaqa berildi — topshirish kutilmoqda", "topshirildi": "Topshirildi — natija tasdiqlanmoqda",
             "tasdiqlandi": "Yakunlandi — natija tasdiqlangan", "bekor": "Bekor qilingan"}
APPEAL_ST = {"yangi": "Qabul qilindi — komissiyaga yuborildi", "ko'rib chiqilmoqda": "Komissiya ko'rib chiqmoqda", "qaror": "Qaror chiqarildi"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS student_auth(student_id INTEGER PRIMARY KEY, pw_hash TEXT NOT NULL, must_change INT DEFAULT 1,
  created_at TEXT, changed_at TEXT, last_login TEXT);
CREATE TABLE IF NOT EXISTS student_sessions(id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, student_id INT NOT NULL, created REAL,
  expires REAL, pw_tag TEXT, ip TEXT, ua TEXT, last_seen REAL);
CREATE INDEX IF NOT EXISTS ix_stsess_st ON student_sessions(student_id);
CREATE TABLE IF NOT EXISTS student_requests(id INTEGER PRIMARY KEY, student_id INT NOT NULL, kind TEXT NOT NULL, unit TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'yangi', created_at TEXT, updated_at TEXT,
  absence_id INT, reason TEXT, start TEXT, end TEXT, lang TEXT, purpose TEXT, note TEXT,
  file_name TEXT, file_stored TEXT, file_ext TEXT, file_size INT, file_sha256 TEXT, file_scan TEXT, file_mime TEXT,
  reviewed_by INT, reviewed_name TEXT, reviewed_at TEXT, review_note TEXT, doc_reg TEXT, doc_file TEXT, doc_code TEXT);
CREATE INDEX IF NOT EXISTS ix_streq_st ON student_requests(student_id, kind);
CREATE INDEX IF NOT EXISTS ix_streq_unit ON student_requests(unit, status);
"""

def init(con):
    con.executescript(SCHEMA); con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _now_iso(): return clock.now_iso()
def _today(): return clock.today()
def _h(tok: str) -> str: return hashlib.sha256(tok.encode()).hexdigest()
def _ip(request: Request) -> str: return (request.client.host if request.client else "") or "?"
def _bad(msg, code=400): raise HTTPException(code, msg)
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
_DUMMY = rbac.hash_password(secrets.token_hex(8))   # noma'lum HEMIS ID uchun ham bir xil vaqt sarflanadi (ID mavjudligi sizib chiqmasin)

# ---------------------------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------------------------
def _audit(action: str, allowed: bool, s: dict | None = None, detail: str = "", resource: str = RES):
    who = f"talaba #{s['id']} · HEMIS {s['hemis_id']}" if s else "talaba (aniqlanmagan)"
    _con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                 (_now_iso(), None, "Talaba kabineti", "Talaba", "talaba", f"talaba kabineti: {action}", resource, int(bool(allowed)),
                  (who + (" · " + detail if detail else ""))[:300]))
    _con.commit()

# ---------------------------------------------------------------------------------------------
# Sessiyalar (student_sessions) — app/sessions.py bilan bir xil tamoyil
# ---------------------------------------------------------------------------------------------
def _new_session(sid: int, pw_hash: str, ip: str, ua: str) -> str:
    tok, now = secrets.token_urlsafe(32), time.time()
    _con.execute("DELETE FROM student_sessions WHERE expires<?", (now,))
    _con.execute("INSERT INTO student_sessions(token,student_id,created,expires,pw_tag,ip,ua,last_seen) VALUES(?,?,?,?,?,?,?,?)",
                 (_h(tok), sid, now, now + TTL, SS.pw_tag(pw_hash), ip[:64], (ua or "")[:300], now))
    _con.commit()
    return tok

def _resolve(tok):
    """Token → (sessiya, auth yozuvi) yoki None (muddati o'tgan, chiqilgan, parol o'zgargan)."""
    if not tok or len(tok) > 128: return None
    r = db.one(_con, """SELECT ss.id sess_id, ss.student_id, ss.pw_tag, ss.last_seen, a.pw_hash, a.must_change FROM student_sessions ss
                        JOIN student_auth a ON a.student_id=ss.student_id WHERE ss.token=? AND ss.expires>?""", (_h(tok), time.time()))
    if not r or r["pw_tag"] != SS.pw_tag(r["pw_hash"]): return None
    if time.time() - (r["last_seen"] or 0) > 60:
        _con.execute("UPDATE student_sessions SET last_seen=? WHERE id=?", (time.time(), r["sess_id"])); _con.commit()
    return r

STUDENT_SQL = """SELECT s.id, s.hemis_id, s.full_name, s.group_id, s.faculty_id, s.gender, s.region, s.payment_type, s.contract_amount, s.paid_amount,
  s.status, s.level, s.study_form, s.phone, g.name grp, g.course, g.direction, g.level glevel, f.name faculty
  FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id WHERE s.id=?"""

def student(request: Request, allow_must_change=False) -> dict:
    """Joriy talaba (faqat talaba cookie'si orqali). Parol almashtirilmagan bo'lsa — ma'lumot endpointlari 403 (must_change)."""
    r = _resolve(request.cookies.get(COOKIE))
    if not r: raise HTTPException(401, "Talaba kabinetiga kirish talab qilinadi")
    s = db.one(_con, STUDENT_SQL, (r["student_id"],))
    if not s or s["status"] not in ALLOWED_STATUS:
        _con.execute("DELETE FROM student_sessions WHERE student_id=?", (r["student_id"],)); _con.commit()
        raise HTTPException(401, "Kabinet faqat faol yoki akademik ta'tildagi talabalar uchun")
    s["_sess"], s["_must"] = r["sess_id"], bool(r["must_change"])
    if s["_must"] and not allow_must_change:
        raise HTTPException(403, {"must_change": True, "message": "Avval boshlang'ich parolni almashtiring"})
    return s

# ---------------------------------------------------------------------------------------------
# Kirish, chiqish, parol
# ---------------------------------------------------------------------------------------------
class LoginIn(BaseModel):
    hemis_id: str = Field("", max_length=40)
    password: str = Field("", max_length=200)

class PasswordIn(BaseModel):
    current: str = Field("", max_length=200)
    new: str = Field("", max_length=200)

def _password_problem(pw: str, s: dict) -> str | None:
    from .extras import password_problem
    p = password_problem(pw)
    if p: return p
    if pw == DEMO_PASSWORD: return "Boshlang'ich (sinov) parolini qayta qo'yib bo'lmaydi"
    if s["hemis_id"] and s["hemis_id"] in pw: return "Parolda HEMIS ID bo'lmasin"
    return None

@router.get("/api/talaba/config")
def api_config():
    """Kirish sahifasi uchun: sinov paroli izohi (jonli namoyishda ISFT_HIDE_DEMO_HINT bilan yashiriladi)."""
    from .extras import hide_demo_hint
    hide = hide_demo_hint()
    return {"demo_hint": not hide, "demo_password": None if hide else DEMO_PASSWORD}

@router.post("/api/talaba/login")
def api_login(body: LoginIn, request: Request, response: Response):
    ip, ua = _ip(request), request.headers.get("user-agent", "")
    hemis = re.sub(r"\D", "", body.hemis_id or "")[:20]
    wait = (LOGIN_HEMIS.wait_min(hemis) if hemis else 0) or LOGIN_IP.wait_min(ip)
    if wait: raise HTTPException(429, f"Juda ko'p noto'g'ri urinish. {wait} daqiqadan keyin qayta urinib ko'ring.")
    s = db.one(_con, "SELECT id, hemis_id, full_name, status FROM students WHERE hemis_id=?", (hemis,)) if hemis else None
    a = db.one(_con, "SELECT * FROM student_auth WHERE student_id=?", (s["id"],)) if s else None
    pw = body.password or ""
    if a: good = rbac.check_password(a["pw_hash"], pw)
    else:   # hali kirmagan talaba: boshlang'ich (sinov) parol. Vaqt — xesh tekshiruvi bilan bir xil
        rbac.check_password(_DUMMY, pw)
        good = bool(s) and bool(pw) and hmac.compare_digest(pw.encode(), DEMO_PASSWORD.encode())
    if not good:
        left = LOGIN_HEMIS.fail(hemis) if hemis else 5; LOGIN_IP.fail(ip)
        if s: _audit("kirish", False, s, f"noto'g'ri parol · IP {ip} · {SS.device(ua)}", "auth")
        raise HTTPException(401, "HEMIS ID yoki parol noto'g'ri" + (f" · yana {left} ta urinish qoldi" if 0 < left < 3 else ""))
    if s["status"] not in ALLOWED_STATUS:
        _audit("kirish", False, s, f"maqomi: {s['status']} · IP {ip}", "auth")
        raise HTTPException(403, f"Kabinet faqat faol yoki akademik ta'tildagi talabalar uchun (maqomingiz: {s['status']}). "
                                 f"{AR.REGISTRAR_UNIT}ga murojaat qiling.")
    LOGIN_HEMIS.reset(hemis)
    now = _now_iso()
    if not a:
        h = rbac.hash_password(pw)
        _con.execute("INSERT OR IGNORE INTO student_auth(student_id,pw_hash,must_change,created_at,last_login) VALUES(?,?,1,?,?)", (s["id"], h, now, now))
        a = db.one(_con, "SELECT * FROM student_auth WHERE student_id=?", (s["id"],))
    else:
        _con.execute("UPDATE student_auth SET last_login=? WHERE student_id=?", (now, s["id"]))
    _con.commit()
    tok = _new_session(s["id"], a["pw_hash"], ip, ua)
    _audit("kirish", True, s, f"IP {ip} · {SS.device(ua)}", "auth")
    response.set_cookie(COOKIE, tok, httponly=True, samesite="lax", max_age=TTL, secure=request.url.scheme == "https")
    return {"ok": True, "must_change": bool(a["must_change"])}

@router.post("/api/talaba/logout")
def api_logout(request: Request, response: Response):
    tok = request.cookies.get(COOKIE)
    r = _resolve(tok)
    if tok: _con.execute("DELETE FROM student_sessions WHERE token=?", (_h(tok),)); _con.commit()
    if r:
        s = db.one(_con, "SELECT id, hemis_id FROM students WHERE id=?", (r["student_id"],))
        if s: _audit("chiqish", True, s, "", "auth")
    response.delete_cookie(COOKIE)
    return {"ok": True}

@router.post("/api/talaba/password")
def api_password(body: PasswordIn, request: Request):
    s = student(request, allow_must_change=True)
    sid = s["id"]
    wait = PW_LIMIT.wait_min(sid)
    if wait:
        _audit("parolni almashtirish", False, s, "bloklangan: ko'p marta noto'g'ri joriy parol", "auth")
        raise HTTPException(429, f"Juda ko'p noto'g'ri urinish. {wait} daqiqadan keyin qayta urinib ko'ring.")
    a = db.one(_con, "SELECT * FROM student_auth WHERE student_id=?", (sid,))
    if not rbac.check_password(a["pw_hash"], body.current):
        left = PW_LIMIT.fail(sid)
        _audit("parolni almashtirish", False, s, "joriy parol noto'g'ri", "auth")
        raise HTTPException(400, {"field": "current", "message": "Joriy parol noto'g'ri" + (f" · yana {left} ta urinish qoldi" if 0 < left < 5 else "")})
    if body.new == body.current: raise HTTPException(400, {"field": "new", "message": "Yangi parol joriy paroldan farq qilsin"})
    p = _password_problem(body.new, s)
    if p: raise HTTPException(400, {"field": "new", "message": p})
    PW_LIMIT.reset(sid)
    h = rbac.hash_password(body.new)
    _con.execute("UPDATE student_auth SET pw_hash=?, must_change=0, changed_at=? WHERE student_id=?", (h, _now_iso(), sid))
    n = _con.execute("DELETE FROM student_sessions WHERE student_id=? AND id!=?", (sid, s["_sess"])).rowcount
    _con.execute("UPDATE student_sessions SET pw_tag=? WHERE id=?", (SS.pw_tag(h), s["_sess"]))
    _con.commit()
    _audit("parol almashtirildi", True, s, f"boshqa sessiyalar yopildi: {n}", "auth")
    return {"ok": True, "closed": n}

# ---------------------------------------------------------------------------------------------
# Yordamchi: faktlar
# ---------------------------------------------------------------------------------------------
def _ops(): from . import student_ops as OPS; return OPS
def _flows(): from . import academic_flows as AF; return AF
def _reg(): from . import registrar as RG; return RG

def _mask_phone(p):
    d = re.sub(r"\D", "", p or "")
    if len(d) < 7: return None
    return f"+{d[:3]} {d[3:5]} *** ** {d[-2:]}" if len(d) >= 12 else f"*** ** {d[-2:]}"

def _unit(s) -> str: return "sirtqi" if s.get("study_form") == "sirtqi" else "talabalar"

def _money(x): return f"{int(x or 0):,}".replace(",", " ") + " so'm"

def _contract(s) -> dict:
    td = _today().isoformat()
    amount, paid = int(s["contract_amount"] or 0), int(s["paid_amount"] or 0)
    if s["payment_type"] != "kontrakt" or amount <= 0:
        return {"kind": s["payment_type"] or "grant", "basis": "ISFT granti" if s["payment_type"] == "grant" else (s["payment_type"] or "—"),
                "amount": 0, "paid": 0, "debt": 0, "plan": [], "next": None, "overdue": None}
    plan, nxt, over = [], None, None
    for p in db.rows(_con, "SELECT due, cum_pct, label FROM contract_plan ORDER BY due"):
        need = amount * int(p["cum_pct"]) // 100
        short = max(0, need - paid)
        st = "tolangan" if short == 0 else ("muddati_otgan" if p["due"] < td else "kutilmoqda")
        days = (dt.date.fromisoformat(p["due"]) - _today()).days
        row = {"label": p["label"], "due": p["due"], "pct": p["cum_pct"], "need": need, "short": short, "status": st, "days": days}
        plan.append(row)
        if st == "muddati_otgan" and over is None: over = row
        if st != "tolangan" and nxt is None: nxt = row
    dfr = _reg().deferment(_con, s["id"])
    return {"kind": "kontrakt", "basis": "To'lov-kontrakt", "amount": amount, "paid": paid, "debt": max(0, amount - paid),
            "pct_paid": round(paid * 100 / amount, 1), "plan": plan, "next": nxt, "overdue": over,
            "deferment": {"until": dfr["until"]} if dfr else None}

def _exam_slots(s, upcoming_only=False) -> list:
    td = _today().isoformat()
    w = " AND x.exam_date>=?" if upcoming_only else ""
    a = (s["group_id"], td) if upcoming_only else (s["group_id"],)
    rows = db.rows(_con, f"""SELECT x.id, x.subject, x.exam_date, x.start_time, x.end_time, x.kind, r.name room, t.full_name examiner,
        e.id session_id, e.name session, e.status session_status FROM exam_slots x JOIN exam_sessions e ON e.id=x.session_id
        LEFT JOIN rooms r ON r.id=x.room_id LEFT JOIN teachers t ON t.id=x.examiner_id
        WHERE x.group_id=? AND e.status IN ('e''lon qilingan','yakunlangan'){w} ORDER BY x.exam_date, x.start_time""", a)
    for r in rows:
        r["days"] = (dt.date.fromisoformat(r["exam_date"]) - _today()).days
        r["past"] = r["exam_date"] < td
    return rows

def _att(s) -> dict:
    OPS = _ops()
    P = OPS.policy(_con)
    f = OPS.student_facts(_con, s["id"])
    L = OPS.att_limits(P, s["study_form"] or "kunduzgi")
    lvl = OPS.davomat_level(f["unexcused"], P, s["study_form"] or "kunduzgi")
    return {"unexcused": f["unexcused"], "excused": f["excused"], "limits": L, "level": lvl, "facts": f}

# ---------------------------------------------------------------------------------------------
# Talaba sahifalari (API)
# ---------------------------------------------------------------------------------------------
@router.get("/api/talaba/session")
def api_session(request: Request):
    """Sahifa yuklanganda: kirilganmi (ma'lumot qaytarmaydi; 401 o'rniga 200 — brauzer konsolida xato chiqmasin)."""
    r = _resolve(request.cookies.get(COOKIE))
    return {"auth": bool(r), "must_change": bool(r and r["must_change"])}

@router.get("/api/talaba/me")
def api_me(request: Request):
    s = student(request, allow_must_change=True)
    u = _unit(s)
    return {"name": s["full_name"], "first": (s["full_name"].split() + [""])[1] or s["full_name"], "hemis_id": s["hemis_id"],
            "group": s["grp"], "course": s["course"], "faculty": s["faculty"], "direction": s["direction"], "level": s["glevel"] or s["level"],
            "study_form": s["study_form"], "status": s["status"], "must_change": s["_must"], "today": _today().isoformat(),
            "semester": AR.SEMESTERS[AR.CURRENT_SEMESTER], "sem_no": AR.sem_no(s["course"], AR.CURRENT_SEMESTER),
            "office": UNIT_NAME[u], "office_rooms": AR.REGISTRAR_ROOMS_TEXT if u == "talabalar" else None,
            "can_request": s["status"] == "faol"}

@router.get("/api/talaba/home")
def api_home(request: Request):
    s = student(request)
    OPS = _ops()
    A = _att(s); f = A["facts"]; L = A["limits"]
    warn = []
    if s["status"] != "faol":
        lv = db.one(_con, "SELECT end, order_no FROM student_leaves WHERE student_id=? ORDER BY end DESC LIMIT 1", (s["id"],))
        warn.append({"key": "tatil", "level": "info", "title": "Akademik ta'tildasiz",
                     "text": (f"Ta'til {lv['end']} gacha" + (f" (buyruq {lv['order_no']})" if lv and lv.get("order_no") else "") + ". Qaytish uchun ariza muddatidan oldin topshiriladi.")
                     if lv else "Qaytish masalasi bo'yicha Registrator ofisiga murojaat qiling.", "page": None})
    h = A["unexcused"]
    if h > L["reprimand"]:
        warn.append({"key": "davomat", "level": "bad", "title": f"Sababsiz qoldirilgan soatlar: {h}",
                     "text": f"{L['reprimand']} soatdan oshdi — hayfsan chegarasi. Imtihonga ruxsatnoma berilmasligi mumkin.", "page": "davomat"})
    elif h >= L["call"]:
        warn.append({"key": "davomat", "level": "warn", "title": f"Sababsiz qoldirilgan soatlar: {h}",
                     "text": f"{L['call']} soatga yetdi — ogohlantirish. {L['reprimand']} soatdan oshsa hayfsan e'lon qilinadi.", "page": "davomat"})
    elif h > 0:
        warn.append({"key": "davomat", "level": "info", "title": f"Sababsiz qoldirilgan soatlar: {h}",
                     "text": f"Ogohlantirish chegarasi — {L['call']} soat, hayfsan — {L['reprimand']} soatdan oshsa.", "page": "davomat"})
    if f["fails"]:
        warn.append({"key": "qarz", "level": "bad", "title": f"Akademik qarz: {len(f['fails'])} ta fan",
                     "text": "; ".join(f"{x['subject']} ({x['score']} ball, {x['sem_label']})" for x in f["fails"][:4]), "page": "baholar"})
    if f["oraliq_low"]:
        warn.append({"key": "oraliq", "level": "warn", "title": f"Oraliq nazorat {AR.ORALIQ_MIN} balldan past: {len(f['oraliq_low'])} ta fan",
                     "text": "Yakuniy nazoratga kiritilmaysiz: " + ", ".join(x["subject"] for x in f["oraliq_low"][:5]), "page": "baholar"})
    k = _contract(s)
    if k["overdue"] and not k.get("deferment"):
        warn.append({"key": "kontrakt", "level": "bad", "title": f"Kontrakt: {k['overdue']['label']} muddati o'tgan",
                     "text": f"{k['overdue']['due']} gacha {_money(k['overdue']['short'])} to'lanishi kerak edi.", "page": "kontrakt"})
    elif k["next"] and k["next"]["days"] <= 14:
        warn.append({"key": "kontrakt", "level": "warn", "title": f"Kontrakt: {k['next']['label']} — {k['next']['days']} kun qoldi",
                     "text": f"{k['next']['due']} gacha {_money(k['next']['short'])} to'lash kerak.", "page": "kontrakt"})
    rts = db.rows(_con, "SELECT subject, due_at FROM retakes WHERE student_id=? AND status='berildi' ORDER BY due_at", (s["id"],))
    for r in rts[:3]:
        hl = (dt.datetime.fromisoformat(r["due_at"]) - clock.now()).total_seconds() / 3600
        warn.append({"key": "otrabotka", "level": "bad" if hl <= 24 else "warn", "title": f"Otrabotka: {r['subject']}",
                     "text": ("Muddat o'tgan" if hl < 0 else f"Varaqani topshirish muddati: {r['due_at'].replace('T', ' ')[:16]}"), "page": "otrabotka"})
    nxt = _exam_slots(s, upcoming_only=True)
    cur = db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(credits),0) cr FROM grades WHERE student_id=? AND semester=?", (s["id"], AR.CURRENT_SEMESTER))
    st, en = AR.term_dates(AR.CURRENT_SEMESTER)
    _audit("bosh sahifa", True, s)
    return {"semester": {"label": AR.SEMESTERS[AR.CURRENT_SEMESTER], "sem_no": AR.sem_no(s["course"], AR.CURRENT_SEMESTER), "course": s["course"],
                         "start": st, "end": en, "subjects": cur["n"], "credits": cur["cr"], "status": s["status"]},
            "warnings": warn, "next_exam": nxt[0] if nxt else None, "exams_left": len(nxt),
            "attendance": {"unexcused": h, "excused": A["excused"], "limits": L},
            "gpa": f["gpa5"], "debts": len(f["fails"]), "contract": {"next": k["next"], "debt": k["debt"], "kind": k["kind"]}}

@router.get("/api/talaba/grades")
def api_grades(request: Request):
    s = student(request)
    OPS = _ops()
    cur = db.rows(_con, f"""SELECT g.subject, g.oraliq, COALESCE(g.credits,{AR.CREDIT_DEFAULT}) credits, t.full_name teacher FROM grades g
                            LEFT JOIN teachers t ON t.id=g.teacher_id WHERE g.student_id=? AND g.semester=? ORDER BY g.subject""", (s["id"], AR.CURRENT_SEMESTER))
    for g in cur: g["admitted"] = AR.admitted(g["oraliq"])
    att = {}
    for a in db.rows(_con, "SELECT subject, semester, attempt, kind, oraliq, yakuniy, score, at, counted, note FROM grade_attempts WHERE student_id=? ORDER BY attempt",
                     (s["id"],)):
        att.setdefault((a["subject"], a["semester"]), []).append(a)
    done = db.rows(_con, f"""SELECT subject, semester, score, oraliq, yakuniy, COALESCE(credits,{AR.CREDIT_DEFAULT}) credits, COALESCE(attempts,1) attempts
                             FROM grades WHERE student_id=? AND semester<? AND score IS NOT NULL ORDER BY semester DESC, subject""", (s["id"], AR.CURRENT_SEMESTER))
    sems, earned, total = {}, 0, 0
    for g in done:
        g["letter"] = AR.letter(g["score"]); g["grade5"], g["word"] = AR.grade5(g["score"])
        g["passed"] = g["score"] >= AR.PASS
        g["history"] = att.get((g["subject"], g["semester"]), [])
        sm = sems.setdefault(g["semester"], {"semester": g["semester"], "label": AR.SEMESTERS.get(g["semester"]), "short": AR.SEMESTER_SHORT.get(g["semester"]),
                                             "sem_no": AR.sem_no(s["course"], g["semester"]), "subjects": [], "credits": 0, "earned": 0})
        sm["subjects"].append(g); sm["credits"] += g["credits"]
        if g["passed"]: sm["earned"] += g["credits"]; earned += g["credits"]
        total += g["credits"]
    for sm in sems.values():
        sm["gpa"] = AR.gpa([(x["credits"], x["grade5"]) for x in sm["subjects"]])
        sm["debts"] = sum(1 for x in sm["subjects"] if not x["passed"])
    lvl = s["glevel"] or s["level"] or "bakalavr"
    need = AR.PROGRAM_CREDITS.get(lvl, AR.BACHELOR_CREDITS)
    _audit("baholar", True, s)
    return {"current": {"label": AR.SEMESTERS[AR.CURRENT_SEMESTER], "sem_no": AR.sem_no(s["course"], AR.CURRENT_SEMESTER), "subjects": cur,
                        "oraliq_max": AR.ORALIQ_MAX, "oraliq_min": AR.ORALIQ_MIN, "credits": sum(g["credits"] for g in cur)},
            "semesters": sorted(sems.values(), key=lambda x: -x["semester"]), "cum_gpa": OPS.cum_gpa(_con, s["id"]),
            "credits": {"earned": earned, "attempted": total, "required": need, "in_progress": sum(g["credits"] for g in cur), "level": lvl},
            "scale": [{"lo": lo, "hi": hi, "letter": l, "grade": g, "word": w} for lo, hi, l, g, w in AR.SCALE],
            "pass": AR.PASS, "gpa_formula": AR.GPA_FORMULA}

@router.get("/api/talaba/rating")
def api_rating(request: Request):
    s = student(request)
    rows = db.rows(_con, """SELECT semester, gpa, avg_score, credits, credits_ok, n_subj, n_f, attendance, r_group, n_group, r_course, n_course,
                            r_direction, n_direction, r_faculty, n_faculty, r_institute, n_institute FROM rating_cache WHERE student_id=? ORDER BY semester DESC""", (s["id"],))
    for r in rows:
        r["label"] = AR.SEMESTERS.get(r["semester"]); r["short"] = AR.SEMESTER_SHORT.get(r["semester"])
        for k in ("group", "course", "faculty", "direction", "institute"):
            r[f"p_{k}"] = AR.percentile(r[f"r_{k}"], r[f"n_{k}"])
    _audit("reyting", True, s)
    return {"items": rows, "rated_semester": AR.RATING_SEMESTER, "note": AR.RATING_FORMULA,
            "levels": {"group": "Guruhda", "course": f"{s['course']}-kursda", "faculty": "Fakultetda"},
            "rated": s["status"] == AR.RATED_STATUS}

def _excuse_reasons(s) -> dict:
    OPS = _ops()
    keys = OPS.REASONS_BY_FORM.get(s["study_form"] or "kunduzgi") or OPS.REASONS_BY_FORM["kunduzgi"]
    return {k: OPS.REASONS[k] for k in keys if k in OPS.EXCUSABLE}

@router.get("/api/talaba/attendance")
def api_attendance(request: Request):
    s = student(request)
    OPS = _ops()
    P = OPS.policy(_con)
    unx = OPS._unexcused_sql(P, _today())
    rows = db.rows(_con, f"""SELECT a.id, a.start, a.end, a.hours, a.reason, a.doc_status, a.semester, a.cleared_by, CASE WHEN {unx} THEN 1 ELSE 0 END unexcused
                             FROM absences a JOIN students s ON s.id=a.student_id WHERE a.student_id=? ORDER BY a.start DESC""", (s["id"],))
    sched = {}
    for r in db.rows(_con, "SELECT weekday, slot, subject FROM schedule WHERE group_id=? ORDER BY weekday, slot", (s["group_id"],)):
        sched.setdefault(r["weekday"], []).append(r["subject"])
    open_req = {r["absence_id"]: r for r in db.rows(_con, "SELECT id, absence_id, status FROM student_requests WHERE student_id=? AND kind='sababli' AND absence_id IS NOT NULL ORDER BY id",
                                                     (s["id"],))}
    by_subject = {}
    for a in rows:
        a["reason_name"] = OPS.REASONS.get(a["reason"], a["reason"])
        a["current"] = a["semester"] == AR.CURRENT_SEMESTER
        subs = []
        try:
            d0, d1 = dt.date.fromisoformat(a["start"]), dt.date.fromisoformat(a["end"] or a["start"])
            d = d0
            while d <= d1 and (d - d0).days < 31:
                for x in sched.get(d.weekday(), []):
                    subs.append(x)
                    if a["current"]: by_subject[x] = by_subject.get(x, 0) + 1
                d += dt.timedelta(days=1)
        except (TypeError, ValueError):
            pass
        a["subjects"] = sorted(set(subs))
        rq = open_req.get(a["id"])
        a["request"] = {"id": rq["id"], "status": rq["status"], "status_name": REQ_ST.get(rq["status"])} if rq else None
        a["can_upload"] = (s["status"] == "faol" and a["current"] and not a["cleared_by"] and (a["reason"] == "sababsiz" or a["doc_status"] in ("kutilmoqda", "yoq"))
                           and not (rq and rq["status"] in ("yangi", "qabul")))
    A = _att(s)
    cur = [a for a in rows if a["current"]]
    by_reason = {}
    for a in cur:
        k = "sababsiz" if a["unexcused"] else "sababli"
        by_reason[k] = by_reason.get(k, 0) + (a["hours"] or 0)
    _audit("davomat", True, s)
    return {"items": rows, "unexcused": A["unexcused"], "excused": A["excused"], "total": sum(a["hours"] or 0 for a in cur), "limits": A["limits"],
            "level": A["level"], "by_subject": sorted(({"subject": k, "classes": v} for k, v in by_subject.items()), key=lambda x: -x["classes"]),
            "has_schedule": bool(sched), "reasons": _excuse_reasons(s), "doc_days": int(P["medical_doc_days"]),
            "office": UNIT_NAME[_unit(s)], "max_mb": MAX_BYTES // (1024 * 1024), "can_request": s["status"] == "faol"}

@router.get("/api/talaba/retakes")
def api_retakes(request: Request):
    s = student(request)
    OPS = _ops()
    rows = db.rows(_con, """SELECT r.id, r.subject, r.kind, r.reason, r.status, r.issued_at, r.due_at, r.reg_no, r.score_old, r.score_new, r.semester,
                            r.submitted_at, r.approved_at, t.full_name teacher FROM retakes r LEFT JOIN teachers t ON t.id=r.teacher_id
                            WHERE r.student_id=? ORDER BY CASE r.status WHEN 'berildi' THEN 0 WHEN 'topshirildi' THEN 1 ELSE 2 END, r.due_at DESC""", (s["id"],))
    now = clock.now()
    for r in rows:
        r["kind"] = r["kind"] or "qarz"
        r["kind_label"] = OPS.RETAKE_KINDS.get(r["kind"], r["kind"])
        r["sem_label"] = AR.SEMESTER_SHORT.get(r["semester"] if r["semester"] is not None else AR.CURRENT_SEMESTER)
        r["hours_left"] = round((dt.datetime.fromisoformat(r["due_at"]) - now).total_seconds() / 3600, 1) if r["status"] == "berildi" and r["due_at"] else None
        r["tone"] = OPS.retake_tone(r["hours_left"])
        r["status_name"] = RETAKE_ST.get(r["status"], r["status"])
        r["max_score"] = AR.ORALIQ_MAX if r["kind"] == "oraliq" else None if r["kind"] == "dars" else 100
    _audit("otrabotka", True, s)
    return {"items": rows, "now": now.isoformat(timespec="seconds"), "office": UNIT_NAME[_unit(s)]}

@router.get("/api/talaba/exams")
def api_exams(request: Request):
    s = student(request)
    p = _reg().permit_check(_con, s["id"])
    slots = _exam_slots(s)
    sess = sorted({x["session_id"] for x in slots})
    wins = db.rows(_con, f"SELECT session_id, name, start, end FROM retake_windows WHERE session_id IN ({','.join(str(int(i)) for i in sess) or 0}) ORDER BY start")
    sessions = db.rows(_con, "SELECT id, name, start, end, status FROM exam_sessions WHERE study_form=? AND semester=? AND status IN ('e''lon qilingan','yakunlangan')",
                       (s["study_form"] or "kunduzgi", AR.CURRENT_SEMESTER))
    _audit("imtihonlar", True, s)
    return {"permit": {"eligible": p["eligible"], "checks": p["checks"], "reasons": p["reasons"]}, "slots": slots, "windows": wins,
            "sessions": sessions, "office": UNIT_NAME[_unit(s)]}

def _appeal_options(s) -> list:
    AF = _flows()
    days = AF.RULES["appeal_days"]
    td = _today()
    lo = (td - dt.timedelta(days=days)).isoformat()
    busy = {(a["subject"], a["semester"]) for a in db.rows(_con, "SELECT subject, semester FROM grade_appeals WHERE student_id=? AND status!='qaror'", (s["id"],))}
    out = []
    for g in db.rows(_con, "SELECT subject, semester, score, oraliq, yakuniy FROM grades WHERE student_id=? AND semester<? AND score IS NOT NULL AND yakuniy IS NOT NULL",
                     (s["id"], AR.CURRENT_SEMESTER)):
        _, p = AF.publication(_con, s["id"], g["subject"], g["semester"])
        if p and lo <= p["published_at"] <= td.isoformat() and (g["subject"], g["semester"]) not in busy:
            dl = (dt.date.fromisoformat(p["published_at"]) + dt.timedelta(days=days)).isoformat()
            out.append({**g, "published_at": p["published_at"], "kind": p["kind"], "deadline": dl, "sem_label": AR.SEMESTER_SHORT.get(g["semester"]),
                        "letter": AR.letter(g["score"])})
    return sorted(out, key=lambda x: x["deadline"])

@router.get("/api/talaba/appeals")
def api_appeals(request: Request):
    s = student(request)
    AF = _flows()
    rows = db.rows(_con, """SELECT id, subject, semester, score_old, oraliq, yakuniy_old, published_at, filed_at, deadline, reason, status, decision,
                            yakuniy_new, score_new, decision_note, decided_at FROM grade_appeals WHERE student_id=? ORDER BY filed_at DESC""", (s["id"],))
    for r in rows:
        r["sem_label"] = AR.SEMESTER_SHORT.get(r["semester"]); r["status_name"] = APPEAL_ST.get(r["status"], r["status"])
        r["decision_name"] = AF.APPEAL_DEC.get(r["decision"] or "", "")
    _audit("apellyatsiya", True, s)
    return {"items": rows, "options": _appeal_options(s) if s["status"] == "faol" else [], "days": AF.RULES["appeal_days"], "can_file": s["status"] == "faol"}

class AppealIn(BaseModel):
    subject: str = Field(..., max_length=200)
    semester: int
    reason: str = Field("", max_length=1000)

@router.post("/api/talaba/appeals")
def api_appeal_new(body: AppealIn, request: Request):
    s = student(request)
    AF = _flows()
    if not any(o["subject"] == body.subject and o["semester"] == body.semester for o in _appeal_options(s)):
        _audit("apellyatsiya berish", False, s, f"{body.subject[:60]} · {body.semester}: muddat yoki fan mos emas")
        _bad("Bu fan bo'yicha apellyatsiya berish muddati o'tgan yoki natija hali e'lon qilinmagan")
    try:
        a = AF.create_appeal(_con, s["id"], body.subject, body.semester, body.reason, channel="portal")
    except ValueError as e:
        _audit("apellyatsiya berish", False, s, f"{body.subject[:60]}: {e}")
        _bad(str(e))
    _audit("apellyatsiya berish", True, s, f"#{a['id']} · {body.subject[:80]} ({AR.SEMESTER_SHORT.get(body.semester)})")
    return {"ok": True, "id": a["id"], "deadline": a["deadline"]}

@router.get("/api/talaba/contract")
def api_contract(request: Request):
    s = student(request)
    k = _contract(s)
    _audit("kontrakt", True, s)
    return k

@router.get("/api/talaba/profile")
def api_profile(request: Request):
    s = student(request, allow_must_change=True)
    a = db.one(_con, "SELECT created_at, changed_at, last_login FROM student_auth WHERE student_id=?", (s["id"],)) or {}
    sess = db.rows(_con, "SELECT id, created, expires, ip, ua, last_seen FROM student_sessions WHERE student_id=? AND expires>? ORDER BY last_seen DESC",
                   (s["id"], time.time()))
    def ts(x): return dt.datetime.fromtimestamp(x).isoformat(timespec="minutes") if x else None
    items = [{"id": r["id"], "device": SS.device(r["ua"]), "ip": _mask_ip(r["ip"]), "created": ts(r["created"]), "last_seen": ts(r["last_seen"]),
              "current": r["id"] == s["_sess"]} for r in sess]
    return {"name": s["full_name"], "hemis_id": s["hemis_id"], "group": s["grp"], "course": s["course"], "faculty": s["faculty"],
            "direction": s["direction"], "study_form": s["study_form"], "level": s["glevel"] or s["level"], "basis": "ISFT granti" if s["payment_type"] == "grant" else "To'lov-kontrakt",
            "phone": _mask_phone(s["phone"]), "region": s["region"], "status": s["status"], "must_change": s["_must"],
            "password_changed": a.get("changed_at"), "first_login": a.get("created_at"), "sessions": items,
            "contact_note": f"Ma'lumotlarda xato bo'lsa — {UNIT_NAME[_unit(s)]}ga murojaat qiling."}

def _mask_ip(ip):
    ip = ip or ""
    if ip.count(".") == 3: return ".".join(ip.split(".")[:2]) + ".*.*"
    return ip[:6] + "…" if len(ip) > 6 else ip

@router.post("/api/talaba/sessions/{xid}/revoke")
def api_session_revoke(xid: int, request: Request):
    s = student(request, allow_must_change=True)
    if xid == s["_sess"]: _bad("Joriy sessiyani yopish uchun «Chiqish» tugmasidan foydalaning")
    n = _con.execute("DELETE FROM student_sessions WHERE id=? AND student_id=?", (xid, s["id"])).rowcount
    _con.commit()
    if not n: _bad("Sessiya topilmadi", 404)
    _audit("sessiya yopildi", True, s, f"#{xid}", "auth")
    return {"ok": True}

@router.post("/api/talaba/sessions/revoke-others")
def api_sessions_revoke_others(request: Request):
    s = student(request, allow_must_change=True)
    n = _con.execute("DELETE FROM student_sessions WHERE student_id=? AND id!=?", (s["id"], s["_sess"])).rowcount
    _con.commit()
    _audit("boshqa sessiyalar yopildi", True, s, f"{n} ta", "auth")
    return {"ok": True, "closed": n}

# ---------------------------------------------------------------------------------------------
# Murojaatlar: sababli hujjat va ma'lumotnoma
# ---------------------------------------------------------------------------------------------
def _req_view(r: dict, staff=False) -> dict:
    OPS = _ops()
    out = {k: r.get(k) for k in ("id", "kind", "status", "created_at", "updated_at", "absence_id", "reason", "start", "end", "lang", "purpose", "note",
                                 "file_name", "file_size", "review_note", "reviewed_at", "doc_reg")}
    out["kind_name"] = KINDS.get(r["kind"], r["kind"])
    out["status_name"] = REQ_ST.get(r["status"], r["status"])
    out["reason_name"] = OPS.REASONS.get(r.get("reason") or "", r.get("reason"))
    out["lang_name"] = LANGS.get(r.get("lang") or "", "")
    out["unit_name"] = UNIT_NAME.get(r["unit"], r["unit"])
    out["has_file"] = bool(r.get("file_stored"))
    out["has_doc"] = r["status"] == "berildi" and bool(r.get("doc_file"))
    if staff:
        out["reviewed_by"] = _short(r.get("reviewed_name"))
        for k in ("full_name", "hemis_id", "grp", "course", "study_form", "file_scan", "file_ext", "unit"):
            out[k] = r.get(k)
        if r.get("absence_id"):
            a = db.one(_con, "SELECT start, end, hours, reason, doc_status FROM absences WHERE id=?", (r["absence_id"],))
            out["absence"] = a
    return out

@router.get("/api/talaba/requests")
def api_requests(request: Request):
    s = student(request)
    from . import documents as D
    rows = db.rows(_con, "SELECT * FROM student_requests WHERE student_id=? ORDER BY id DESC", (s["id"],))
    _audit("murojaatlar", True, s)
    return {"items": [_req_view(r) for r in rows], "purposes": D.PURPOSES, "langs": LANGS, "office": UNIT_NAME[_unit(s)],
            "can_request": s["status"] == "faol"}

def _open_count(sid, kind):
    return db.one(_con, "SELECT COUNT(*) n FROM student_requests WHERE student_id=? AND kind=? AND status='yangi'", (sid, kind))["n"]

class CertIn(BaseModel):
    lang: str = "uz"
    purpose: str = Field("", max_length=120)
    note: str = Field("", max_length=300)

@router.post("/api/talaba/requests/certificate")
def api_cert_new(body: CertIn, request: Request):
    s = student(request)
    from . import documents as D
    if s["status"] != "faol": _bad("Ma'lumotnoma faqat faol talabalarga beriladi (akademik ta'tilda — Registrator ofisiga murojaat qiling)", 403)
    if body.lang not in LANGS: _bad("Til: uz yoki en")
    purpose = body.purpose if body.purpose in D.PURPOSES else D.PURPOSES[0]
    if db.one(_con, "SELECT 1 x FROM student_requests WHERE student_id=? AND kind='malumotnoma' AND status='yangi' AND lang=? AND purpose=?",
              (s["id"], body.lang, purpose)):
        _bad("Xuddi shunday so'rov allaqachon ko'rib chiqilmoqda", 409)
    if _open_count(s["id"], "malumotnoma") >= OPEN_LIMIT: _bad(f"Bir vaqtda ko'pi bilan {OPEN_LIMIT} ta ochiq so'rov bo'lishi mumkin", 409)
    now = _now_iso()
    rid = _con.execute("""INSERT INTO student_requests(student_id,kind,unit,status,created_at,updated_at,lang,purpose,note) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (s["id"], "malumotnoma", _unit(s), "yangi", now, now, body.lang, purpose, body.note.strip()[:300])).lastrowid
    _con.commit()
    _audit("ma'lumotnoma so'rovi", True, s, f"#{rid} · {body.lang} · {purpose}")
    return {"ok": True, "id": rid, "office": UNIT_NAME[_unit(s)]}

class ExcuseIn(BaseModel):
    absence_id: int | None = None
    reason: str = ""
    start: str = ""
    end: str = ""
    note: str = Field("", max_length=300)
    name: str = Field(..., max_length=200)
    data: str = Field(..., max_length=MAX_BYTES * 4 // 3 + 200)   # base64 (data: URL bo'lishi mumkin)

def _decode(data: str) -> bytes:
    b64 = data.split(",", 1)[1] if data.startswith("data:") and "," in data else data
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        _bad("Fayl ma'lumoti buzilgan (base64)")

@router.post("/api/talaba/requests/excuse")
def api_excuse_new(body: ExcuseIn, request: Request):
    s = student(request)
    from . import portal as PT
    if s["status"] != "faol": _bad("Sababli hujjat faqat faol talabalardan qabul qilinadi", 403)
    wait = UPLOAD_LIMIT.wait_min(s["id"])
    if wait: _bad(f"Juda ko'p rad etilgan fayl. {wait} daqiqadan keyin qayta urinib ko'ring.", 429)
    reasons = _excuse_reasons(s)
    if body.reason not in reasons: _bad("Sababni tanlang: " + ", ".join(reasons.values()))
    a = None
    if body.absence_id:
        a = db.one(_con, "SELECT * FROM absences WHERE id=? AND student_id=?", (int(body.absence_id), s["id"]))
        if not a:   # boshqa talabaning yozuvi yoki mavjud emas — bir xil javob (IDOR)
            _audit("sababli hujjat", False, s, f"dars qoldirish #{body.absence_id} topilmadi")
            _bad("Dars qoldirish yozuvi topilmadi", 404)
        if a["semester"] != AR.CURRENT_SEMESTER or a["cleared_by"] or not (a["reason"] == "sababsiz" or a["doc_status"] in ("kutilmoqda", "yoq")):
            _bad("Bu dars qoldirish uchun hujjat talab qilinmaydi")
        if db.one(_con, "SELECT 1 x FROM student_requests WHERE student_id=? AND absence_id=? AND status IN ('yangi','qabul')", (s["id"], a["id"])):
            _bad("Bu dars qoldirish bo'yicha hujjat allaqachon yuborilgan", 409)
        start, end = a["start"], a["end"]
    else:
        try:
            d0, d1 = dt.date.fromisoformat(body.start[:10]), dt.date.fromisoformat((body.end or body.start)[:10])
        except ValueError:
            _bad("Dars qoldirishni tanlang yoki sanalarni kiriting")
        st0, en0 = AR.term_dates(AR.CURRENT_SEMESTER)
        if d1 < d0 or d0.isoformat() < st0 or d1 > _today() or (d1 - d0).days > 60: _bad("Sanalar joriy semestr ichida va bugundan oldin bo'lsin")
        start, end = d0.isoformat(), d1.isoformat()
    if _open_count(s["id"], "sababli") >= OPEN_LIMIT: _bad(f"Bir vaqtda ko'pi bilan {OPEN_LIMIT} ta ochiq hujjat bo'lishi mumkin", 409)
    try:
        name, ext = PT.safe_name(body.name)
    except HTTPException as e:
        UPLOAD_LIMIT.fail(s["id"]); _audit("sababli hujjat: fayl rad etildi", False, s, f"{body.name[:60]} — {e.detail}"); raise
    if ext not in EXCUSE_EXT:
        UPLOAD_LIMIT.fail(s["id"]); _audit("sababli hujjat: fayl rad etildi", False, s, f"{name[:60]} — tur")
        _bad("Faqat PDF yoki JPG fayl qabul qilinadi")
    raw = _decode(body.data)
    if len(raw) > MAX_BYTES: _bad(f"Fayl hajmi {MAX_BYTES // (1024 * 1024)} MB dan oshmasligi kerak", 413)
    try:
        chk = FC.inspect(name, ext, raw)
    except FC.FileRejected as e:
        UPLOAD_LIMIT.fail(s["id"]); _audit("sababli hujjat: fayl rad etildi", False, s, f"{name[:60]} — {e}")
        _bad(str(e), 415)
    FILES.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    p = (FILES / stored).resolve()
    if p.parent != FILES.resolve(): _bad("Noto'g'ri fayl nomi")
    p.write_bytes(raw)
    now = _now_iso()
    rid = _con.execute("""INSERT INTO student_requests(student_id,kind,unit,status,created_at,updated_at,absence_id,reason,start,end,note,
                          file_name,file_stored,file_ext,file_size,file_sha256,file_scan,file_mime) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (s["id"], "sababli", _unit(s), "yangi", now, now, a["id"] if a else None, body.reason, start, end, body.note.strip()[:300],
                        name, stored, ext, len(raw), chk["sha256"], chk["scan"], chk["mime"])).lastrowid
    _con.commit()
    _audit("sababli hujjat yuklandi", True, s, f"#{rid} · {name} ({len(raw) // 1024} KB, {chk['scan']}) → {UNIT_NAME[_unit(s)]}")
    return {"ok": True, "id": rid, "office": UNIT_NAME[_unit(s)]}

def _own_request(s, rid) -> dict:
    r = db.one(_con, "SELECT * FROM student_requests WHERE id=? AND student_id=?", (rid, s["id"]))
    if not r:
        _audit("murojaat: begona yoki mavjud emas", False, s, f"#{rid}")
        _bad("Murojaat topilmadi", 404)
    return r

def _file_response(r):
    p = (FILES / str(r["file_stored"])).resolve()
    if p.parent != FILES.resolve() or not p.is_file(): _bad("Fayl topilmadi", 404)
    return FileResponse(p, filename=r["file_name"], media_type=r.get("file_mime") or "application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.get("/api/talaba/requests/{rid}/file")
def api_request_file(rid: int, request: Request):
    s = student(request)
    r = _own_request(s, rid)
    if not r.get("file_stored"): _bad("Fayl yo'q", 404)
    return _file_response(r)

@router.get("/api/talaba/requests/{rid}/document")
def api_request_doc(rid: int, request: Request):
    s = student(request)
    from . import documents as D
    r = _own_request(s, rid)
    if r["status"] != "berildi" or not r.get("doc_file"): _bad("Hujjat hali tayyor emas", 404)
    d = db.one(_con, "SELECT status, holder FROM documents WHERE reg_no=?", (r["doc_reg"],))
    if not d or d["status"] == "bekor": _bad("Hujjat bekor qilingan — Registrator ofisiga murojaat qiling", 410)
    f = (D.OUT / r["doc_file"]).resolve()
    if f.parent != D.OUT.resolve() or not f.is_file(): _bad("Hujjat fayli topilmadi", 404)
    _audit("ma'lumotnoma yuklab olindi", True, s, f"#{rid} · {r['doc_reg']}")
    return FileResponse(f, filename=f"{r['doc_reg'].replace('/', '-')}.docx",
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Cache-Control": "private, no-store"})

# ---------------------------------------------------------------------------------------------
# Xodimlar tomoni: «Talaba murojaatlari» (Registrator ofisi #17, #43; Sirtqi bo'lim #27 — faqat sirtqi)
# ---------------------------------------------------------------------------------------------
def _staff(request: Request, action: str) -> tuple[Ctx, str]:
    c = _ctx(request)   # xodim sessiyasi (cookie "sid"); talaba cookie'si bu yerda 401
    unit = STAFF_UNIT.get(c.role.key)
    rbac.audit(_con, c, f"talaba murojaatlari: {action}", RES, bool(unit))
    if not unit: raise AccessDenied("⛔ Talaba murojaatlari: Registrator ofisi va Sirtqi bo'lim uchun. So'rov audit jurnaliga yozildi.")
    return c, unit

def _scope_sql(unit: str) -> str:
    return "r.unit='sirtqi' AND s.study_form='sirtqi'" if unit == "sirtqi" else "r.unit='talabalar'"

REQ_FROM = """FROM student_requests r JOIN students s ON s.id=r.student_id JOIN groups_ g ON g.id=s.group_id"""

def _staff_req(c, unit, rid) -> dict:
    r = db.one(_con, f"SELECT r.*, s.full_name, s.hemis_id, s.study_form, g.name grp, g.course {REQ_FROM} WHERE r.id=? AND {_scope_sql(unit)}", (rid,))
    if not r:
        rbac.audit(_con, c, "talaba murojaatlari: ko'lamdan tashqari", RES, False, f"#{rid}")
        raise AccessDenied("⛔ Bu murojaat sizning bo'limingiz navbatida emas. So'rov audit jurnaliga yozildi.")
    return r

@router.get("/api/talaba/staff/requests")
def api_staff_list(request: Request, status: str = "ochiq", kind: str = "", student_id: int = 0, q: str = ""):
    c, unit = _staff(request, "ro'yxat")
    w, a = [_scope_sql(unit)], []
    if status == "ochiq": w.append("r.status='yangi'")
    elif status in REQ_ST: w.append("r.status=?"); a.append(status)
    if kind in KINDS: w.append("r.kind=?"); a.append(kind)
    if student_id: w.append("r.student_id=?"); a.append(int(student_id))
    if q.strip(): w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ? OR g.name LIKE ?)"); a += [f"%{q.strip()[:60]}%"] * 3
    rows = db.rows(_con, f"SELECT r.*, s.full_name, s.hemis_id, s.study_form, g.name grp, g.course {REQ_FROM} WHERE {' AND '.join(w)} ORDER BY r.status!='yangi', r.id DESC LIMIT 300", a)
    counts = {r["status"]: r["n"] for r in db.rows(_con, f"SELECT r.status, COUNT(*) n {REQ_FROM} WHERE {_scope_sql(unit)} GROUP BY 1")}
    return {"items": [_req_view(r, staff=True) for r in rows], "counts": counts, "unit": unit, "unit_name": UNIT_NAME[unit],
            "who": c.user["full_name"], "can_issue": c.role.key in STAFF_UNIT}

@router.get("/api/talaba/staff/requests/{rid}/file")
def api_staff_file(rid: int, request: Request):
    c, unit = _staff(request, "fayl")
    r = _staff_req(c, unit, rid)
    if not r.get("file_stored"): _bad("Fayl yo'q", 404)
    return _file_response(r)

class DecideIn(BaseModel):
    action: str
    note: str = Field("", max_length=300)

@router.post("/api/talaba/staff/requests/{rid}/decide")
def api_staff_decide(rid: int, body: DecideIn, request: Request):
    c, unit = _staff(request, "qaror")
    r = _staff_req(c, unit, rid)
    if r["status"] != "yangi": _bad("Murojaat allaqachon ko'rib chiqilgan", 409)
    note = body.note.strip()[:300]
    now = _now_iso()
    upd = {"status": None, "doc_reg": None, "doc_file": None, "doc_code": None}
    if body.action == "rad":
        if len(note) < 3: _bad("Rad etish sababini yozing")
        upd["status"] = "rad"   # dars qoldirish yozuvi o'zgarmaydi (talaba boshqa hujjat yuklashi mumkin)
    elif r["kind"] == "sababli" and body.action == "qabul":
        upd["status"] = "qabul"
        if r["absence_id"]:   # dars qoldirish sababli deb belgilanadi — sababsiz soatlardan chiqadi (Talabalar markazi qoidalari keyingi hisobda yangilanadi)
            _con.execute("UPDATE absences SET reason=?, doc_status='tasdiqlangan', note=COALESCE(note,'') || ? WHERE id=? AND student_id=?",
                         (r["reason"], f" · Talaba kabineti #{rid}", r["absence_id"], r["student_id"]))
    elif r["kind"] == "malumotnoma" and body.action == "berish":
        from . import documents as D, service as SV
        try:
            res = D.issue(_con, c, "study_cert", {"target": f"s:{r['student_id']}", "lang": r["lang"] or "uz", "purpose": r["purpose"] or D.PURPOSES[0]},
                          SV.public_base(request))
        except ValueError as e:
            _bad(str(e))
        d = db.one(_con, "SELECT reg_no, file, verify_code FROM documents WHERE reg_no=?", (res["regs"][0],))
        upd.update(status="berildi", doc_reg=d["reg_no"], doc_file=d["file"], doc_code=d["verify_code"])
    else:
        _bad("Amal: sababli hujjat — qabul/rad; ma'lumotnoma — berish/rad")
    _con.execute("""UPDATE student_requests SET status=?, reviewed_by=?, reviewed_name=?, reviewed_at=?, review_note=?, updated_at=?,
                    doc_reg=COALESCE(?,doc_reg), doc_file=COALESCE(?,doc_file), doc_code=COALESCE(?,doc_code) WHERE id=?""",
                 (upd["status"], c.user["id"], c.user["full_name"], now, note, now, upd["doc_reg"], upd["doc_file"], upd["doc_code"], rid))
    _con.commit()
    rbac.audit(_con, c, f"talaba murojaati: {upd['status']}", RES, True, f"#{rid} · {KINDS[r['kind']]} · HEMIS {r['hemis_id']}" + (f" · {upd['doc_reg']}" if upd["doc_reg"] else ""))
    return {"ok": True, "status": upd["status"], "doc_reg": upd["doc_reg"]}

# ---------------------------------------------------------------------------------------------
# Sahifa
# ---------------------------------------------------------------------------------------------
PAGE_HEADERS = {"Cache-Control": "no-cache", "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin"}

@router.get("/talaba", include_in_schema=False)
@router.get("/talaba/", include_in_schema=False)
@router.get("/talaba/xodim", include_in_schema=False)
def page():
    return FileResponse(PAGE, media_type="text/html; charset=utf-8", headers=PAGE_HEADERS)
