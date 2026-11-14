"""«Yuzma-yuz tadbirlar» — masofaviy ta'lim talabalarining majburiy yuzma-yuz (o'qishga kelib) bajariladigan ishlari, identifikatsiya
va monitoring, masofaviy ta'limning huquqiy chegaralari. Batafsil va me'yoriy asos: docs/yuzma_yuz.md.

DIQQAT: me'yoriy talablar (VMQ 03.10.2022 № 559 «Masofaviy ta'lim to'g'risidagi nizom», PF-73 (2025)) ikkilamchi manbalar asosida
kodlangan — YURIST TASDIQLASHI KERAK. Raqamli chegaralar (300 / 30 / 50, 90 %) rektor tomonidan «Nazorat markazi → Qoidalar»da
o'zgartiriladi (app/nazorat.py RULES: dl_quota_bachelor, dl_quota_master, dl_per_teacher, dl_quota_warn_pct).

1. TADBIRLAR (yy_sessions → yy_assign):
     royxat      — semestr oldidan LMS'da yuzma-yuz ro'yxatdan o'tish (O'zbekiston fuqarolari uchun majburiy);
     imtihon     — yakuniy nazorat;  attestatsiya — yakuniy davlat attestatsiyasi;  himoya — bitiruv ishi himoyasi.
   Sessiya: sana, vaqt, xona, sig'im. Talabalar tayinlanadi (sig'imdan oshmaydi), Telegram navbatiga xabar (ops_notices) yoziladi.
   Xorijiy fuqarolar (students.citizenship ≠ UZ) — «ozod»: tayinlanmaydi, hisoblarda alohida.
   SHAXSNI TEKSHIRISH: xodim hujjatni ko'zdan kechiradi — pasport / ID karta OXIRGI 4 RAQAMI (yoki HEMIS ID) va rasm bilan yuzni solishtiradi.
     Bazaga FAQAT natija yoziladi: usul, raqam mosligi (1/0), moslik manbai (tizim — HEMIS'dan olingan xesh bilan; xodim — ko'zdan),
     rasm mosligi (1/0), kim va qachon tekshirgani. Kiritilgan raqamlar hech qayerda saqlanmaydi; 4 tadan ortiq raqam — 400 (to'liq hujjat
     raqami qabul qilinmaydi). Ma'lumotnoma uchun HEMIS'dagi oxirgi 4 raqam faqat HMAC-xesh ko'rinishida (yy_idref) saqlanishi mumkin.
   QAYDNOMA: bo'lim boshlig'i (masofaviy yoki Registrator ofisi) imzolaydi → sessiya yopiladi (belgilanmaganlar «kelmadi»), ro'yxat
     raqami (YQ-26/NNNN) va tekshirish kodi Hujjatlar reyestriga (documents) yoziladi (/verify/KOD), mazmunning SHA-256 xeshi saqlanadi.
     .docx va .pdf har safar bazadagi ma'lumotdan quriladi (bir xil mazmun — bir xil xesh).
   MUDDAT: semestr ro'yxatdan o'tish muddati (standart: semestr boshidan 30 kun; bo'lim boshlig'i o'zgartiradi). Muddatdan keyin
     o'tmaganlar — talaba kabinetida qizil banner (keyingi sessiya bilan) va Nazorat markazida istisno.
2. IDENTIFIKATSIYA VA MONITORING: talaba kabinetiga kirishlar (yy_access: IP / tarmoq / User-Agent — faqat HMAC-xesh, qurilma nomi),
   LRS launch'lari va statementlar soni — talaba bo'yicha jurnal (faqat Masofaviy ta'lim bo'limi). Umumiy akkaunt alomatlari
   (bir vaqtda turli tarmoqdan faol sessiyalar, imkonsiz tez tarmoq+qurilma almashishi, sutkada ko'p tarmoq) → yy_flags, KO'RIB
   CHIQISH UCHUN; avtomatik bloklanmaydi.
3. HUQUQIY CHEGARALAR: yo'nalish bo'yicha masofaviy talabalar (bakalavr ≤ 300, magistratura ≤ 30), o'qituvchiga ≤ 50 masofaviy talaba,
   kunduzgi shakli yo'q masofaviy yo'nalish, pedagogik yo'nalishda masofaviy talaba. Nazorat markazida (app/nazorat.py, «Yuzma-yuz va
   huquqiy chegaralar» bo'limi) va Masofaviy ta'lim umumiy sahifasida ko'rsatiladi.

Ruxsatlar (har bir so'rov audit jurnalida, resurs «yuzma»):
  masofaviy, talabalar (Registrator ofisi)       — boshqaradi va qaydnomani imzolaydi; muddatni o'zgartiradi;
  masofaviy_xodim, registrator_xodim             — sessiya, tayinlash, shaxsni tekshirish (imzo — yo'q);
  tyutor                                         — faqat o'z guruhlari talabalari (o'qish);
  rektor, prorektor_oquv                         — jamlangan sonlar va huquqiy chegaralar (ismlarsiz);
  talaba                                         — /api/talaba/yuzma: faqat o'z jadvali va holati.
  Kirish jurnali va umumiy akkaunt belgilari — faqat Masofaviy ta'lim bo'limi (masofaviy, masofaviy_xodim).
"""
from __future__ import annotations
import datetime as dt, hashlib, hmac, io, json, random, re, secrets, threading, zlib
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/yuzma"
RES = "yuzma"

HEAD, STAFF, REG, REG_X, TUT = "masofaviy", "masofaviy_xodim", "talabalar", "registrator_xodim", "tyutor"
LEAD = ("rektor", "prorektor_oquv")
MANAGE = (HEAD, STAFF, REG, REG_X)
SIGN = (HEAD, REG)
DEPT = (HEAD, STAFF)                       # kirish jurnali, umumiy akkaunt belgilari
LIMITS_VIEW = DEPT + (REG,) + LEAD
PROGRAM_EDIT = (HEAD, "rektor")
ALL = MANAGE + (TUT,) + LEAD

KINDS = {"royxat": "Semestr oldidan LMS'da ro'yxatdan o'tish", "imtihon": "Yakuniy nazorat (imtihon)",
         "attestatsiya": "Yakuniy davlat attestatsiyasi", "himoya": "Bitiruv ishi himoyasi"}
A_ST = {"tayinlangan": "Tayinlangan", "keldi": "Keldi — shaxsi tasdiqlandi", "shubhali": "Keldi — shaxsi tasdiqlanmadi", "kelmadi": "Kelmadi"}
S_ST = {"rejada": "Rejada", "yopilgan": "Yopilgan — qaydnoma imzolangan", "bekor": "Bekor qilingan"}
METHODS = {"pasport": "Pasport", "id_karta": "ID karta", "hemis": "Talaba guvohnomasi (HEMIS ID)"}
STATES = {"otgan": ("Ro'yxatdan o'tgan", "ok"), "tayinlangan": ("Sessiyaga tayinlangan", "info"), "kutilmoqda": ("Kutilmoqda", "warn"),
          "muddati_otgan": ("Muddat o'tgan", "bad"), "ozod": ("Ozod (xorijiy fuqaro)", ""), "tatil": ("Akademik ta'tilda", "")}
LEGAL_NOTE = ("Me'yoriy asos: VMQ 03.10.2022 № 559 «Masofaviy ta'lim to'g'risidagi nizom», PF-73 (2025) — ikkilamchi manbalar bo'yicha; "
              "yurist tasdiqlashi kerak.")
COUNTRIES = {"UZ": "O'zbekiston", "KZ": "Qozog'iston", "TJ": "Tojikiston", "KG": "Qirg'iziston", "TM": "Turkmaniston", "AF": "Afg'oniston",
             "RU": "Rossiya", "TR": "Turkiya", "KR": "Koreya Respublikasi", "IN": "Hindiston", "CN": "Xitoy"}
REG_DEADLINE_DAYS = 30                     # standart muddat: semestr boshidan
PED_WORDS = ("pedagog", "ta'lim", "o'qitish")     # pedagogik yo'nalishni avtomatik aniqlash (bo'lim boshlig'i / rektor o'zgartiradi)

# umumiy akkaunt alomatlari (docs/yuzma_yuz.md)
PARALLEL_IDLE_MIN = 30     # boshqa sessiya oxirgi shuncha daqiqada faol bo'lsa — «bir vaqtda»
SWITCH_MIN = 15            # tarmoq VA qurilma shuncha daqiqa ichida almashsa — «imkonsiz almashish»
MANY_NETS = 4              # sutkada shuncha va undan ko'p turli tarmoq
FLAG_T = {"parallel": "Bir vaqtda turli tarmoqlardan faol sessiyalar", "almashish": "Imkonsiz tez almashish (tarmoq + qurilma)",
          "kop_tarmoq": "Sutkada ko'p turli tarmoq"}
FLAG_ST = {"yangi": "Ko'rib chiqilmagan", "tasdiqlandi": "Tasdiqlandi — choralar ko'rilmoqda", "asossiz": "Asossiz (yopildi)"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS yy_meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS yy_sessions(id INTEGER PRIMARY KEY, kind TEXT, term TEXT, title TEXT, date TEXT, start_time TEXT, end_time TEXT,
  room TEXT, capacity INT, direction TEXT, note TEXT, status TEXT DEFAULT 'rejada', created_by INT, created_name TEXT, created_at TEXT,
  closed_at TEXT, src TEXT DEFAULT 'ui');
CREATE INDEX IF NOT EXISTS ix_yy_sess ON yy_sessions(term, kind, date);
CREATE TABLE IF NOT EXISTS yy_assign(id INTEGER PRIMARY KEY, session_id INT NOT NULL, student_id INT NOT NULL, assigned_at TEXT, assigned_by INT,
  notice_id INT, status TEXT DEFAULT 'tayinlangan', method TEXT, doc_match INT, match_src TEXT, photo_ok INT, checked_by INT, checked_name TEXT,
  checked_at TEXT, note TEXT, UNIQUE(session_id, student_id));
CREATE INDEX IF NOT EXISTS ix_yy_as_st ON yy_assign(student_id, status);
CREATE TABLE IF NOT EXISTS yy_idref(student_id INTEGER PRIMARY KEY, last4_hash TEXT, src TEXT, updated_at TEXT, updated_by INT);
CREATE TABLE IF NOT EXISTS yy_protocols(id INTEGER PRIMARY KEY, session_id INT UNIQUE, reg_no TEXT, verify_code TEXT, signed_by INT,
  signed_name TEXT, signed_role TEXT, signed_at TEXT, sha256 TEXT, stats TEXT);
CREATE TABLE IF NOT EXISTS yy_access(id INTEGER PRIMARY KEY, student_id INT, ts TEXT, kind TEXT, ip_hash TEXT, net_hash TEXT, ua_hash TEXT,
  ua_label TEXT, parallel INT DEFAULT 0, src TEXT DEFAULT 'kabinet');
CREATE INDEX IF NOT EXISTS ix_yy_acc ON yy_access(student_id, ts);
CREATE TABLE IF NOT EXISTS yy_flags(id INTEGER PRIMARY KEY, student_id INT, kind TEXT, ts_first TEXT, ts_last TEXT, n INT, detail TEXT,
  evidence TEXT, status TEXT DEFAULT 'yangi', reviewed_by INT, reviewed_name TEXT, reviewed_at TEXT, review_note TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_yy_flags ON yy_flags(status, student_id);
CREATE TABLE IF NOT EXISTS yy_programs(direction TEXT, level TEXT, pedagogik INT, src TEXT, updated_at TEXT, updated_by TEXT,
  PRIMARY KEY(direction, level));
"""


def init(con):
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(students)").fetchall()}
    if "citizenship" not in cols:          # fuqarolik (ISO alpha-2); bo'sh — O'zbekiston
        con.execute("ALTER TABLE students ADD COLUMN citizenship TEXT")
    if not con.execute("SELECT 1 FROM yy_meta WHERE k='salt'").fetchone():
        con.execute("INSERT INTO yy_meta(k,v) VALUES('salt',?)", (secrets.token_hex(32),))
    con.commit()
    try:
        seed(con)
    except Exception as e:                 # demo ma'lumot xatosi server ishga tushishini to'xtatmasin
        print("yuzma_yuz seed:", repr(e))


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def C(request: Request) -> Ctx: return _ctx(request)
def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t: dt.datetime) -> str: return t.replace(microsecond=0).isoformat(timespec="seconds")
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _dmy(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 and v[4] == "-" else v


def _meta(con, k, default=None):
    r = db.one(con, "SELECT v FROM yy_meta WHERE k=?", (k,))
    return r["v"] if r else default


def _salt(con) -> bytes:
    return (_meta(con, "salt") or "yy").encode()


def _hm(con, *parts) -> str:
    return hmac.new(_salt(con), "|".join(str(p) for p in parts).encode(), hashlib.sha256).hexdigest()[:24]


def _inv():
    """Nazorat markazi keshini bekor qilish (holat o'zgardi)."""
    try:
        from . import nazorat as NZ; NZ.invalidate()
    except Exception:
        pass


def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"yuzma-yuz: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Yuzma-yuz tadbirlar: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")


# =============================================================================================
# Semestr va muddat
# =============================================================================================
def term_of(d: dt.date) -> str:
    """Sana → semestr kaliti: «2026-K» (2026-2027 kuzgi), «2027-B» (2026-2027 bahorgi). Iyul–avgust — kelayotgan kuzgi semestr
    (ro'yxatdan o'tish semestr OLDIDAN)."""
    if d.month >= 7: return f"{d.year}-K"
    if d.month == 1: return f"{d.year - 1}-K"
    return f"{d.year}-B"


def term_start(term: str) -> dt.date:
    y, s = term.split("-")
    return dt.date(int(y), 9, 1) if s == "K" else dt.date(int(y), 2, 1)


def term_end(term: str) -> dt.date:
    y, s = term.split("-")
    return dt.date(int(y) + 1, 1, 31) if s == "K" else dt.date(int(y), 6, 30)


def term_label(term: str) -> str:
    y, s = term.split("-"); y = int(y)
    return f"{y}–{y + 1} o'quv yili, kuzgi semestr" if s == "K" else f"{y - 1}–{y} o'quv yili, bahorgi semestr"


def cur_term() -> str: return term_of(clock.today())


def deadline(con, term: str) -> str:
    return _meta(con, f"deadline:{term}") or (term_start(term) + dt.timedelta(days=REG_DEADLINE_DAYS)).isoformat()


# =============================================================================================
# Talabalar: masofaviy, fuqarolik, semestr holati
# =============================================================================================
def is_foreign(cit) -> bool:
    return bool(cit) and str(cit).upper() not in ("UZ", "UZB", "O'ZBEKISTON")


def country(cit) -> str:
    c = (cit or "UZ").upper()
    return COUNTRIES.get(c, c)


def _scope_sql(c: Ctx | None, alias="s") -> str:
    """Masofaviy talabalar + lavozim ko'lami (tyutor — o'z guruhlari; rbac.student_scope bilan bir xil qoida)."""
    base = f"{alias}.study_form='masofaviy'"
    if c is None or c.role.key in MANAGE + LEAD: return base
    return f"{base} AND {c.student_scope(alias)}"


def registered_ids(con, term: str) -> set:
    return {r["student_id"] for r in db.rows(con, """SELECT a.student_id FROM yy_assign a JOIN yy_sessions s ON s.id=a.session_id
        WHERE s.term=? AND s.kind='royxat' AND s.status!='bekor' AND a.status='keldi'""", (term,))}


def upcoming_map(con, term: str, kind: str = "royxat") -> dict:
    """talaba → eng yaqin rejadagi sessiya (bugundan keyin yoki bugun)."""
    out = {}
    for r in db.rows(con, """SELECT a.student_id, s.id, s.date, s.start_time, s.end_time, s.room, s.title FROM yy_assign a
        JOIN yy_sessions s ON s.id=a.session_id WHERE s.term=? AND s.kind=? AND s.status='rejada' AND a.status='tayinlangan' AND s.date>=?
        ORDER BY s.date, s.start_time""", (term, kind, clock.today().isoformat())):
        out.setdefault(r["student_id"], r)
    return out


def state_of(st: dict, reg: set, up: dict, dl: str, today: str) -> str:
    if st.get("status") != "faol": return "tatil"
    if is_foreign(st.get("citizenship")): return "ozod"
    if st["id"] in reg: return "otgan"
    if st["id"] in up: return "tayinlangan" if today <= dl else "muddati_otgan"
    return "kutilmoqda" if today <= dl else "muddati_otgan"


def student_states(con, term: str, c: Ctx | None = None, extra_where: str = "", args=()) -> list[dict]:
    reg, up, dl, today = registered_ids(con, term), upcoming_map(con, term), deadline(con, term), clock.today().isoformat()
    rows = db.rows(con, f"""SELECT s.id, s.full_name, s.hemis_id, s.status, s.citizenship, s.group_id, g.name grp, g.direction, g.level, g.course
        FROM students s JOIN groups_ g ON g.id=s.group_id WHERE {_scope_sql(c)} AND s.status IN ('faol', 'akademik ta''til') {extra_where}
        ORDER BY g.name, s.full_name""", args)
    for r in rows:
        r["state"] = state_of(r, reg, up, dl, today)
        n = up.get(r["id"])
        r["next"] = {"id": n["id"], "date": n["date"], "start_time": n["start_time"], "room": n["room"]} if n else None
    return rows


def counts(con, term: str, c: Ctx | None = None) -> dict:
    out = {k: 0 for k in STATES}
    for r in student_states(con, term, c): out[r["state"]] += 1
    out["jami"] = sum(out.values())
    out["majburiy"] = out["jami"] - out["ozod"] - out["tatil"]
    return out


def overdue_count(con, term: str | None = None) -> tuple[int, str]:
    """Nazorat markazi uchun: muddat o'tgan va ro'yxatdan o'tmagan talabalar soni, muddat."""
    term = term or cur_term()
    dl = deadline(con, term)
    if clock.today().isoformat() <= dl: return 0, dl
    return counts(con, term)["muddati_otgan"], dl


# =============================================================================================
# Sessiyalar
# =============================================================================================
def _session(sid: int) -> dict:
    s = db.one(_con, "SELECT * FROM yy_sessions WHERE id=?", (int(sid),))
    if not s: raise HTTPException(404, "Sessiya topilmadi")
    return s


def _sess_view(s: dict, cnt: dict | None = None) -> dict:
    cnt = cnt or {}
    return {**{k: s[k] for k in ("id", "kind", "term", "title", "date", "start_time", "end_time", "room", "capacity", "direction", "note", "status",
                                 "created_name", "created_at", "closed_at")},
            "kind_label": KINDS.get(s["kind"], s["kind"]), "status_label": S_ST.get(s["status"], s["status"]),
            "assigned": cnt.get("n", 0), "came": cnt.get("keldi", 0), "doubt": cnt.get("shubhali", 0), "absent": cnt.get("kelmadi", 0),
            "free": max(0, (s["capacity"] or 0) - cnt.get("n", 0)), "past": s["date"] < clock.today().isoformat(),
            "today": s["date"] == clock.today().isoformat()}


def _counts_by_session(ids: list[int], c: Ctx | None = None) -> dict:
    if not ids: return {}
    w = "" if c is None or c.role.key in MANAGE + LEAD else f" AND a.student_id IN (SELECT s.id FROM students s WHERE {c.student_scope('s')})"
    out = {}
    for r in db.rows(_con, f"""SELECT a.session_id sid, COUNT(*) n, SUM(a.status='keldi') keldi, SUM(a.status='shubhali') shubhali,
            SUM(a.status='kelmadi') kelmadi FROM yy_assign a WHERE a.session_id IN ({','.join('?' * len(ids))}){w} GROUP BY a.session_id""", ids):
        out[r["sid"]] = r
    return out


def list_sessions(c: Ctx, term: str | None = None, kind: str = "") -> list[dict]:
    term = term or cur_term()
    w, a = "s.term=?", [term]
    if kind: w += " AND s.kind=?"; a.append(kind)
    if c.role.key == TUT:      # tyutor — faqat o'z talabalari tayinlangan sessiyalar
        w += f" AND s.id IN (SELECT a.session_id FROM yy_assign a JOIN students st ON st.id=a.student_id WHERE {c.student_scope('st')})"
    rows = db.rows(_con, f"SELECT s.* FROM yy_sessions s WHERE {w} ORDER BY s.date DESC, s.start_time", a)
    cnt = _counts_by_session([r["id"] for r in rows], c)
    return [_sess_view(r, cnt.get(r["id"])) for r in rows]


_TIME = re.compile(r"^\d{2}:\d{2}$")


class SessionIn(BaseModel):
    kind: str = "royxat"
    title: str = Field("", max_length=200)
    date: str = Field(..., max_length=10)
    start_time: str = Field("09:00", max_length=5)
    end_time: str = Field("13:00", max_length=5)
    room: str = Field(..., min_length=2, max_length=120)
    capacity: int = Field(..., ge=1, le=2000)
    direction: str = Field("", max_length=200)
    note: str = Field("", max_length=500)


def create_session(c: Ctx, b: SessionIn) -> dict:
    guard(c, "sessiya yaratish", MANAGE, f"{b.kind} · {b.date} · {b.room}")
    if b.kind not in KINDS: raise HTTPException(400, "Tadbir turi: " + ", ".join(KINDS))
    try: d = dt.date.fromisoformat(b.date)
    except ValueError: raise HTTPException(400, "Sana YYYY-MM-DD ko'rinishida bo'lsin")
    if d < clock.today(): raise HTTPException(400, "O'tgan sanaga sessiya rejalashtirilmaydi")
    if not (_TIME.match(b.start_time) and _TIME.match(b.end_time)) or b.start_time >= b.end_time:
        raise HTTPException(400, "Vaqt HH:MM ko'rinishida, boshlanish tugashdan oldin bo'lsin")
    clash = db.one(_con, """SELECT id, title FROM yy_sessions WHERE date=? AND room=? AND status='rejada' AND NOT (end_time<=? OR start_time>=?)""",
                   (b.date, b.room.strip(), b.start_time, b.end_time))
    if clash: raise HTTPException(409, f"Shu vaqtda bu xonada boshqa sessiya bor: «{clash['title']}» (#{clash['id']})")
    title = b.title.strip() or f"{KINDS[b.kind]} — {_dmy(b.date)}"
    with _lock:
        sid = _con.execute("""INSERT INTO yy_sessions(kind,term,title,date,start_time,end_time,room,capacity,direction,note,status,created_by,created_name,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,'rejada',?,?,?)""", (b.kind, term_of(d), title, b.date, b.start_time, b.end_time, b.room.strip(), b.capacity,
                                                         b.direction.strip(), b.note.strip(), c.user["id"], c.user["full_name"], _iso(_now()))).lastrowid
        _con.commit()
    return session_detail(c, sid, audit=False)


def session_detail(c: Ctx, sid: int, audit: bool = True) -> dict:
    if audit: guard(c, "sessiya", ALL, f"#{sid}")
    s = _session(sid)
    v = _sess_view(s, _counts_by_session([s["id"]], c).get(s["id"]))
    names = c.role.key in MANAGE + (TUT,)
    roster = []
    if names:
        w = "" if c.role.key in MANAGE else f" AND {c.student_scope('st')}"
        if c.role.key == TUT and not db.one(_con, f"SELECT 1 x FROM yy_assign a JOIN students st ON st.id=a.student_id WHERE a.session_id=?{w}", (sid,)):
            rbac.audit(_con, c, "yuzma-yuz: begona sessiya", RES, False, f"#{sid}")
            raise AccessDenied("⛔ Bu sessiyada sizning guruhingiz talabalari yo'q. So'rov audit jurnaliga yozildi.")
        for r in db.rows(_con, f"""SELECT a.*, st.full_name, st.hemis_id, st.citizenship, g.name grp FROM yy_assign a JOIN students st ON st.id=a.student_id
                JOIN groups_ g ON g.id=st.group_id WHERE a.session_id=?{w} ORDER BY g.name, st.full_name""", (sid,)):
            roster.append({"student_id": r["student_id"], "full_name": r["full_name"], "hemis_id": r["hemis_id"], "grp": r["grp"],
                           "status": r["status"], "status_label": A_ST.get(r["status"], r["status"]), "method": r["method"],
                           "method_label": METHODS.get(r["method"] or "", ""), "doc_match": r["doc_match"], "match_src": r["match_src"],
                           "photo_ok": r["photo_ok"], "checked_name": _short(r["checked_name"]) or r["checked_name"], "checked_at": r["checked_at"],
                           "note": r["note"], "has_ref": False})
        refs = {x["student_id"] for x in db.rows(_con, "SELECT student_id FROM yy_idref")} if roster else set()
        for x in roster: x["has_ref"] = x["student_id"] in refs
    pr = db.one(_con, "SELECT reg_no, verify_code, signed_name, signed_role, signed_at, sha256 FROM yy_protocols WHERE session_id=?", (sid,))
    return {"session": v, "roster": roster, "names": names, "protocol": pr,
            "caps": {"manage": c.role.key in MANAGE and s["status"] == "rejada", "sign": c.role.key in SIGN and s["status"] == "rejada"
                     and s["date"] <= clock.today().isoformat(), "check": c.role.key in MANAGE and s["status"] == "rejada" and s["date"] <= clock.today().isoformat()}}


def _notify(c: Ctx, st: dict, s: dict) -> int | None:
    """Talabaga xabar: Talabalar markazi xabarlar navbati (Telegram — kabinetda ulangan bo'lsa yuboriladi, aks holda navbatda qoladi)."""
    try:
        from . import talaba_darslar as TD
        name = (st["full_name"].split() + [""])[1] or st["full_name"]
        text = (f"Hurmatli {name}! ISFT masofaviy ta'lim: «{KINDS.get(s['kind'], s['kind'])}» — {_dmy(s['date'])}, {s['start_time']}–{s['end_time']}, "
                f"{s['room']}. Pasport yoki ID kartangizni olib keling (shaxsingiz tekshiriladi). Batafsil: talaba kabineti → «Yuzma-yuz».")
        nid = _con.execute("INSERT INTO ops_notices(ts,channel,task_id,case_id,student_id,phone,text,status,user_id) VALUES(?,?,?,?,?,?,?,?,?)",
                           (_iso(_now()), "telegram", None, None, st["id"], None, text[:900], "navbatda", c.user["id"])).lastrowid
        return nid
    except Exception as e:
        print("yuzma_yuz.notify:", repr(e)); return None


class AssignIn(BaseModel):
    student_ids: list[int] = Field(default_factory=list, max_length=2000)
    group_id: int = 0
    pending: bool = False          # semestr ro'yxatidan o'tmagan va tayinlanmaganlar (bo'sh joygacha)
    limit: int = Field(0, ge=0, le=2000)


def assign(c: Ctx, sid: int, b: AssignIn) -> dict:
    guard(c, "talabalarni tayinlash", MANAGE, f"sessiya #{sid}")
    s = _session(sid)
    if s["status"] != "rejada": raise HTTPException(409, "Sessiya yopilgan yoki bekor qilingan")
    if s["date"] < clock.today().isoformat(): raise HTTPException(409, "O'tgan sessiyaga tayinlanmaydi")
    with _lock:
        n_now = db.one(_con, "SELECT COUNT(*) n FROM yy_assign WHERE session_id=?", (sid,))["n"]
        free = (s["capacity"] or 0) - n_now
        reg = registered_ids(_con, s["term"]) if s["kind"] == "royxat" else set()
        up = upcoming_map(_con, s["term"], s["kind"])
        if b.pending:
            if s["kind"] != "royxat": raise HTTPException(400, "«Ro'yxatdan o'tmaganlar» faqat ro'yxatdan o'tish sessiyasi uchun")
            cand = [r["id"] for r in student_states(_con, s["term"], None) if r["state"] in ("kutilmoqda", "muddati_otgan") and r["id"] not in up
                    and (not s["direction"] or r["direction"] == s["direction"])]
            cand = cand[:min(free, b.limit or free)] if free > 0 else []
        elif b.group_id:
            cand = [r["id"] for r in db.rows(_con, "SELECT id FROM students WHERE group_id=? AND status='faol' ORDER BY full_name", (b.group_id,))]
        else:
            cand = list(dict.fromkeys(int(x) for x in b.student_ids))
        if not cand: return {"ok": True, "assigned": 0, "skipped": [], "free": max(0, free)}
        sts = {r["id"]: r for r in db.rows(_con, f"""SELECT s.id, s.full_name, s.status, s.study_form, s.citizenship, g.direction FROM students s
                 JOIN groups_ g ON g.id=s.group_id WHERE s.id IN ({','.join('?' * len(cand))})""", cand)}
        have = {r["student_id"] for r in db.rows(_con, "SELECT student_id FROM yy_assign WHERE session_id=?", (sid,))}
        ok, skipped = [], []
        for i in cand:
            st = sts.get(i)
            why = ("topilmadi" if not st else "masofaviy ta'lim talabasi emas" if st["study_form"] != "masofaviy"
                   else "faol emas" if st["status"] != "faol" else "xorijiy fuqaro — ozod" if is_foreign(st["citizenship"])
                   else "allaqachon tayinlangan" if i in have else "semestr ro'yxatidan o'tgan" if i in reg
                   else f"boshqa sessiyaga tayinlangan (#{up[i]['id']})" if i in up else
                   "yo'nalish mos emas" if s["direction"] and st["direction"] != s["direction"] else None)
            (skipped.append({"student_id": i, "why": why}) if why else ok.append(st))
        if len(ok) > free:
            rbac.audit(_con, c, "yuzma-yuz: sig'im yetmadi", RES, False, f"sessiya #{sid} · {len(ok)} > {free}")
            raise HTTPException(409, f"Sig'im yetarli emas: bo'sh joy {max(0, free)} ta, tayinlanmoqchi {len(ok)} ta")
        ts = _iso(_now())
        for st in ok:
            nid = _notify(c, st, s)
            _con.execute("INSERT INTO yy_assign(session_id,student_id,assigned_at,assigned_by,notice_id,status) VALUES(?,?,?,?,?,'tayinlangan')",
                         (sid, st["id"], ts, c.user["id"], nid))
        _con.commit()
    if ok:
        try:
            from . import talaba_darslar as TD
            for r in db.rows(_con, "SELECT notice_id FROM yy_assign WHERE session_id=? AND assigned_at=? AND notice_id IS NOT NULL", (sid, ts))[:200]:
                TD.deliver(_con, r["notice_id"])
        except Exception as e:
            print("yuzma_yuz.deliver:", repr(e))
    _inv()
    rbac.audit(_con, c, "yuzma-yuz: tayinlandi", RES, True, f"sessiya #{sid} · {len(ok)} ta · o'tkazildi {len(skipped)}")
    return {"ok": True, "assigned": len(ok), "skipped": skipped[:50], "skipped_n": len(skipped), "free": free - len(ok)}


def unassign(c: Ctx, sid: int, student_id: int) -> dict:
    guard(c, "tayinlovni bekor qilish", MANAGE, f"sessiya #{sid} · talaba #{student_id}")
    s = _session(sid)
    if s["status"] != "rejada": raise HTTPException(409, "Sessiya yopilgan")
    a = db.one(_con, "SELECT status FROM yy_assign WHERE session_id=? AND student_id=?", (sid, student_id))
    if not a: raise HTTPException(404, "Talaba bu sessiyaga tayinlanmagan")
    if a["status"] != "tayinlangan": raise HTTPException(409, "Davomati belgilangan talaba olib tashlanmaydi")
    _con.execute("DELETE FROM yy_assign WHERE session_id=? AND student_id=?", (sid, student_id)); _con.commit()
    return {"ok": True}


# ---------------- shaxsni tekshirish ----------------
class CheckIn(BaseModel):
    student_id: int
    method: str = "pasport"
    code: str = Field("", max_length=40)       # pasport/ID: OXIRGI 4 RAQAM; hemis: guvohnomadagi HEMIS ID. HECH QAYERDA SAQLANMAYDI
    doc_ok: bool = False                       # xodim ko'zdan tasdiqladi (HEMIS ma'lumotnomasi bo'lmasa)
    photo_ok: bool = False                     # rasm yuz bilan mos
    note: str = Field("", max_length=300)


def _clean_note(t: str) -> str:
    """Izohga hujjat raqami yozib qo'yilmasin: 5+ raqamli ketma-ketliklar yashiriladi."""
    return re.sub(r"\d{5,}", "•••", " ".join((t or "").split()))[:300]


def check(c: Ctx, sid: int, b: CheckIn) -> dict:
    guard(c, "shaxsni tekshirish", MANAGE, f"sessiya #{sid} · talaba #{b.student_id} · {b.method}")
    s = _session(sid)
    if s["status"] != "rejada": raise HTTPException(409, "Qaydnoma imzolangan — davomat o'zgarmaydi")
    if s["date"] > clock.today().isoformat(): raise HTTPException(400, "Sessiya hali boshlanmagan — davomat sessiya kuni belgilanadi")
    if b.method not in METHODS: raise HTTPException(400, "Usul: " + ", ".join(METHODS))
    a = db.one(_con, "SELECT * FROM yy_assign WHERE session_id=? AND student_id=?", (sid, b.student_id))
    if not a: raise HTTPException(404, "Talaba bu sessiyaga tayinlanmagan")
    st = db.one(_con, "SELECT id, hemis_id FROM students WHERE id=?", (b.student_id,))
    code = re.sub(r"\s", "", b.code or "")
    if b.method in ("pasport", "id_karta"):
        if code and not re.fullmatch(r"\d{4}", code):
            rbac.audit(_con, c, "yuzma-yuz: to'liq hujjat raqami rad etildi", RES, False, f"talaba #{b.student_id}")
            raise HTTPException(400, "Faqat hujjatning OXIRGI 4 RAQAMI kiritiladi — to'liq hujjat raqami qabul qilinmaydi va saqlanmaydi")
        ref = db.one(_con, "SELECT last4_hash FROM yy_idref WHERE student_id=?", (b.student_id,))
        if ref and code:
            doc_match, src = int(hmac.compare_digest(ref["last4_hash"], _hm(_con, "doc4", b.student_id, code))), "tizim"
        elif ref and not code:
            raise HTTPException(400, "Hujjatning oxirgi 4 raqamini kiriting (HEMIS ma'lumotnomasi bilan solishtiriladi)")
        else:
            doc_match, src = int(bool(b.doc_ok)), "xodim"
    else:
        if not code: raise HTTPException(400, "Talaba guvohnomasidagi HEMIS ID ni kiriting")
        doc_match, src = int(hmac.compare_digest(re.sub(r"\D", "", code), str(st["hemis_id"] or ""))), "tizim"
    ok = bool(doc_match and b.photo_ok)
    status = "keldi" if ok else "shubhali"
    with _lock:
        _con.execute("""UPDATE yy_assign SET status=?, method=?, doc_match=?, match_src=?, photo_ok=?, checked_by=?, checked_name=?, checked_at=?, note=?
                        WHERE id=?""", (status, b.method, doc_match, src, int(bool(b.photo_ok)), c.user["id"], c.user["full_name"], _iso(_now()),
                                        _clean_note(b.note), a["id"]))
        _con.commit()
    _inv()
    rbac.audit(_con, c, "yuzma-yuz: shaxs tekshirildi", RES, True,
               f"sessiya #{sid} · talaba #{b.student_id} · {METHODS[b.method]} · raqam {'mos' if doc_match else 'MOS EMAS'} ({src}) · rasm {'mos' if b.photo_ok else 'MOS EMAS'}")
    return {"ok": True, "status": status, "status_label": A_ST[status], "doc_match": bool(doc_match), "match_src": src, "photo_ok": bool(b.photo_ok)}


def mark_absent(c: Ctx, sid: int, student_id: int) -> dict:
    guard(c, "kelmadi deb belgilash", MANAGE, f"sessiya #{sid} · talaba #{student_id}")
    s = _session(sid)
    if s["status"] != "rejada": raise HTTPException(409, "Qaydnoma imzolangan")
    if s["date"] > clock.today().isoformat(): raise HTTPException(400, "Sessiya hali boshlanmagan")
    cur = _con.execute("""UPDATE yy_assign SET status='kelmadi', method=NULL, doc_match=NULL, match_src=NULL, photo_ok=NULL, checked_by=?, checked_name=?,
                          checked_at=? WHERE session_id=? AND student_id=?""", (c.user["id"], c.user["full_name"], _iso(_now()), sid, student_id))
    _con.commit()
    if cur.rowcount != 1: raise HTTPException(404, "Talaba bu sessiyaga tayinlanmagan")
    return {"ok": True}


class IdRefIn(BaseModel):
    student_id: int
    last4: str = Field(..., max_length=10)


def set_idref(c: Ctx, b: IdRefIn) -> dict:
    """HEMIS'dagi hujjatning oxirgi 4 raqami — faqat HMAC-xesh (raqamning o'zi saqlanmaydi)."""
    guard(c, "hujjat ma'lumotnomasi", (HEAD, REG, REG_X), f"talaba #{b.student_id}")
    if not re.fullmatch(r"\d{4}", b.last4 or ""): raise HTTPException(400, "Faqat oxirgi 4 raqam")
    if not db.one(_con, "SELECT 1 x FROM students WHERE id=? AND study_form='masofaviy'", (b.student_id,)): raise HTTPException(404, "Masofaviy talaba topilmadi")
    _con.execute("""INSERT INTO yy_idref(student_id,last4_hash,src,updated_at,updated_by) VALUES(?,?,'qo''lda',?,?)
                    ON CONFLICT(student_id) DO UPDATE SET last4_hash=excluded.last4_hash, src=excluded.src, updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by""", (b.student_id, _hm(_con, "doc4", b.student_id, b.last4), _iso(_now()), c.user["id"]))
    _con.commit()
    return {"ok": True}


# ---------------- qaydnoma ----------------
def _protocol_content(sid: int) -> dict:
    s = _session(sid)
    rows = db.rows(_con, """SELECT a.*, st.full_name, st.hemis_id, g.name grp FROM yy_assign a JOIN students st ON st.id=a.student_id
        JOIN groups_ g ON g.id=st.group_id WHERE a.session_id=? ORDER BY g.name, st.full_name""", (sid,))
    items = [{"n": i + 1, "name": r["full_name"], "hemis": r["hemis_id"], "grp": r["grp"], "status": A_ST.get(r["status"], r["status"]),
              "id": (f"{METHODS.get(r['method'], '')}: raqam {'mos' if r['doc_match'] else 'mos emas'}"
                     f"{' (tizim)' if r['match_src'] == 'tizim' else ' (xodim)' if r['match_src'] else ''}, rasm {'mos' if r['photo_ok'] else 'mos emas'}")
              if r["method"] else "—", "by": _short(r["checked_name"]) or "", "at": (r["checked_at"] or "")[11:16]} for i, r in enumerate(rows)]
    stats = {"tayinlangan": len(rows), "keldi": sum(r["status"] == "keldi" for r in rows), "shubhali": sum(r["status"] == "shubhali" for r in rows),
             "kelmadi": sum(r["status"] == "kelmadi" for r in rows)}
    return {"session": {k: s[k] for k in ("id", "kind", "term", "title", "date", "start_time", "end_time", "room", "capacity")}, "items": items, "stats": stats}


def _digest(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def sign(c: Ctx, sid: int) -> dict:
    guard(c, "qaydnomani imzolash", SIGN, f"sessiya #{sid}")
    with _lock:
        s = _session(sid)
        if s["status"] != "rejada": raise HTTPException(409, "Qaydnoma allaqachon imzolangan yoki sessiya bekor qilingan")
        if s["date"] > clock.today().isoformat(): raise HTTPException(400, "Sessiya o'tkazilgandan keyin imzolanadi")
        ts = _iso(_now())
        _con.execute("UPDATE yy_assign SET status='kelmadi', checked_at=? WHERE session_id=? AND status='tayinlangan'", (ts, sid))
        _con.execute("UPDATE yy_sessions SET status='yopilgan', closed_at=? WHERE id=?", (ts, sid))
        content = _protocol_content(sid)
        reg = _next_reg(); code = secrets.token_hex(4).upper()
        _con.execute("""INSERT INTO yy_protocols(session_id,reg_no,verify_code,signed_by,signed_name,signed_role,signed_at,sha256,stats)
                        VALUES(?,?,?,?,?,?,?,?,?)""", (sid, reg, code, c.user["id"], c.user["full_name"], c.title, ts, _digest(content),
                                                       json.dumps(content["stats"])))
        try:   # Hujjatlar reyestri: /verify/KOD orqali haqiqiyligini tekshirish
            _con.execute("""INSERT INTO documents(reg_no,kind,title,holder,created_by,creator_role,created_at,status,verify_code,file,params,signed_at)
                            VALUES(?,?,?,?,?,?,?,'berilgan',?,?,?,?)""",
                         (reg, "yy_qaydnoma", f"Yuzma-yuz tadbir qaydnomasi: {KINDS.get(s['kind'], s['kind'])}", f"{s['title']} · {_dmy(s['date'])}",
                          c.user["id"], c.title, ts, code, f"yuzma:{sid}", json.dumps({"session_id": sid}), ts))
        except Exception as e:
            print("yuzma_yuz.sign documents:", repr(e))
        _con.commit()
    _inv()
    rbac.audit(_con, c, "yuzma-yuz: qaydnoma imzolandi", RES, True, f"sessiya #{sid} · {reg} · keldi {content['stats']['keldi']}/{content['stats']['tayinlangan']}")
    return {"ok": True, "reg_no": reg, "verify_code": code, "stats": content["stats"]}


def _next_reg() -> str:
    y = clock.today().year % 100
    n = db.one(_con, "SELECT COUNT(*) n FROM yy_protocols WHERE reg_no LIKE ?", (f"YQ-{y:02d}/%",))["n"] + 1
    return f"YQ-{y:02d}/{n:04d}"


def cancel(c: Ctx, sid: int, note: str) -> dict:
    guard(c, "sessiyani bekor qilish", SIGN, f"sessiya #{sid}")
    s = _session(sid)
    if s["status"] != "rejada": raise HTTPException(409, "Faqat rejadagi sessiya bekor qilinadi")
    if db.one(_con, "SELECT 1 x FROM yy_assign WHERE session_id=? AND status!='tayinlangan'", (sid,)):
        raise HTTPException(409, "Davomat belgilangan sessiya bekor qilinmaydi — qaydnomani imzolang")
    _con.execute("UPDATE yy_sessions SET status='bekor', closed_at=?, note=TRIM(COALESCE(note,'') || ' · Bekor: ' || ?) WHERE id=?",
                 (_iso(_now()), _clean_note(note), sid))
    _con.execute("DELETE FROM yy_assign WHERE session_id=?", (sid,))
    _con.commit()
    return {"ok": True}


def protocol_docx(c: Ctx, sid: int, base: str) -> tuple[bytes, str]:
    from docx import Document
    from . import brand as B
    pr = _protocol_or_404(c, sid)
    ct = _protocol_content(sid); s = ct["session"]
    doc = Document(); B.setup(doc); B.letterhead(doc)
    B.regline(doc, pr["reg_no"], _dmy(pr["signed_at"]))
    B.title(doc, "YUZMA-YUZ TADBIR QAYDNOMASI", KINDS.get(s["kind"], s["kind"]))
    B.para(doc, f"Tadbir: {s['title']}. Sana: {_dmy(s['date'])}, {s['start_time']}–{s['end_time']}. Joy: {s['room']}. "
                f"Semestr: {term_label(s['term'])}. Sig'im: {s['capacity']} o'rin.", indent=False, size=11)
    st = ct["stats"]
    B.para(doc, f"Tayinlangan: {st['tayinlangan']} nafar; kelgan va shaxsi tasdiqlangan: {st['keldi']}; kelgan, shaxsi tasdiqlanmagan: {st['shubhali']}; "
                f"kelmagan: {st['kelmadi']}. Xorijiy fuqarolar (ozod) ro'yxatga kiritilmaydi.", indent=False, size=11)
    B.table(doc, ["№", "F.I.Sh.", "HEMIS ID", "Guruh", "Holat", "Shaxsni tekshirish", "Tekshirgan", "Vaqt"],
            [[i["n"], i["name"], i["hemis"], i["grp"], i["status"], i["id"], i["by"], i["at"]] for i in ct["items"]],
            widths=[0.6, 3.4, 2.3, 1.6, 2.2, 3.4, 2.2, 0.9], size=8)
    B.para(doc, "Shaxsni tekshirishda hujjat raqamlari saqlanmaydi: faqat natija (raqam va rasm mosligi), tekshirgan xodim va vaqt qayd etiladi.",
           indent=False, size=9)
    B.signature(doc, pr["signed_role"] or "Bo'lim boshlig'i", _short(pr["signed_name"]))
    B.para(doc, f"Elektron imzolangan: {_short(pr['signed_name']) or pr['signed_name']}, {pr['signed_at'].replace('T', ' ')}. "
                f"Mazmun xeshi (SHA-256): {pr['sha256']}.", indent=False, size=8)
    B.para(doc, LEGAL_NOTE, indent=False, size=8)
    B.footer_qr(doc, f"{base.rstrip('/')}/verify/{pr['verify_code']}", pr["verify_code"],
                "Qaydnoma ISFT Core ma'lumotlari asosida shakllantirildi. Haqiqiyligini QR-kod orqali tekshiring.")
    out = io.BytesIO(); doc.save(out)
    return out.getvalue(), f"{pr['reg_no'].replace('/', '-')}_qaydnoma.docx"


def _protocol_or_404(c: Ctx, sid: int) -> dict:
    guard(c, "qaydnomani yuklab olish", MANAGE + LEAD, f"sessiya #{sid}")
    pr = db.one(_con, "SELECT * FROM yy_protocols WHERE session_id=?", (sid,))
    if not pr: raise HTTPException(404, "Qaydnoma hali imzolanmagan")
    return pr


# ---------------- PDF (tashqi kutubxonasiz: Helvetica, WinAnsi) ----------------
_PDF_MAP = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "№": "No", "–": "-", "≤": "<=", "≥": ">="})


def _pdf_txt(s) -> bytes:
    b = str(s).translate(_PDF_MAP).encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _fit(s, n) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:max(1, n - 1)] + "…"


def build_pdf(lines_fn) -> bytes:
    """lines_fn(page) → sahifalar ro'yxati; har sahifa — buyruqlar: ("t", x, y, size, bold, text) | ("l", x1, y1, x2, y2)."""
    pages = lines_fn
    objs = []
    def add(b: bytes) -> int:
        objs.append(b); return len(objs)
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    pages_id = len(objs) + 1; objs.append(b"")        # keyin to'ldiriladi
    kids = []
    for cmds in pages:
        st = io.BytesIO()
        for c in cmds:
            if c[0] == "t":
                _, x, y, size, bold, text = c
                st.write(b"BT /F%d %.1f Tf %.1f %.1f Td (" % (2 if bold else 1, size, x, y) + _pdf_txt(text) + b") Tj ET\n")
            else:
                _, x1, y1, x2, y2 = c
                st.write(b"0.6 w %.1f %.1f m %.1f %.1f l S\n" % (x1, y1, x2, y2))
        raw = zlib.compress(st.getvalue())
        cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(raw) + raw + b"\nendstream")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                        % (pages_id, f1, f2, cid)))
    objs[pages_id - 1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)
    cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out = io.BytesIO(); out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell()); out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    x = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs))
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, x))
    return out.getvalue()


def protocol_pdf(c: Ctx, sid: int, base: str) -> tuple[bytes, str]:
    pr = _protocol_or_404(c, sid)
    ct = _protocol_content(sid); s = ct["session"]; st = ct["stats"]
    L, R, TOP, BOT = 40, 555, 800, 60
    cols = [(L, "No", 4), (L + 22, "F.I.Sh.", 30), (L + 178, "HEMIS ID", 15), (L + 250, "Guruh", 10), (L + 300, "Holat", 18),
            (L + 390, "Shaxsni tekshirish", 26)]
    pages, cur, y = [], [], TOP
    def text(x, yy, size, bold, t): cur.append(("t", x, yy, size, bold, t))
    def head_block():
        nonlocal y
        text(L, y, 15, True, "ISFT INSTITUTI"); text(R - 150, y, 9, False, f"No {pr['reg_no']}   {_dmy(pr['signed_at'])}"); y -= 20
        cur.append(("l", L, y + 8, R, y + 8))
        text(L, y - 6, 13, True, "YUZMA-YUZ TADBIR QAYDNOMASI"); y -= 24
        text(L, y, 10, True, KINDS.get(s["kind"], s["kind"])); y -= 16
        for t in (f"Tadbir: {s['title']}", f"Sana va vaqt: {_dmy(s['date'])}, {s['start_time']}-{s['end_time']}   Joy: {s['room']}   Sig'im: {s['capacity']}",
                  f"Semestr: {term_label(s['term'])}",
                  f"Tayinlangan: {st['tayinlangan']} | keldi (shaxsi tasdiqlangan): {st['keldi']} | shaxsi tasdiqlanmagan: {st['shubhali']} | kelmagan: {st['kelmadi']}"):
            text(L, y, 9, False, t); y -= 13
        y -= 6
    def table_head():
        nonlocal y
        for x, h, _ in cols: text(x, y, 8, True, h)
        cur.append(("l", L, y - 4, R, y - 4)); y -= 15
    head_block(); table_head()
    for it in ct["items"]:
        if y < BOT + 70:
            pages.append(cur); cur = []; y = TOP; table_head()
        vals = [it["n"], it["name"], it["hemis"], it["grp"], it["status"], f"{it['id']} · {it['by']} {it['at']}".strip(" ·")]
        for (x, _, n), v in zip(cols, vals): text(x, y, 7.5, False, _fit(v, n if x != cols[-1][0] else 44))
        y -= 12
    if y < BOT + 90: pages.append(cur); cur = []; y = TOP
    y -= 10; cur.append(("l", L, y + 6, R, y + 6))
    text(L, y - 8, 8, False, "Hujjat raqamlari saqlanmaydi: faqat natija (raqam va rasm mosligi), tekshirgan xodim va vaqt qayd etiladi."); y -= 26
    text(L, y, 10, True, f"{pr['signed_role'] or 'Bo`lim boshlig`i'}:  ________________   {_short(pr['signed_name'])}"); y -= 16
    text(L, y, 8, False, f"Elektron imzolangan: {pr['signed_at'].replace('T', ' ')} · SHA-256: {pr['sha256']}"); y -= 12
    text(L, y, 8, False, f"Haqiqiyligini tekshirish: {base.rstrip('/')}/verify/{pr['verify_code']}  (kod {pr['verify_code']})"); y -= 12
    text(L, y, 7, False, LEGAL_NOTE[:150]); y -= 10
    text(L, y, 7, False, LEGAL_NOTE[150:])
    pages.append(cur)
    return build_pdf(pages), f"{pr['reg_no'].replace('/', '-')}_qaydnoma.pdf"


# =============================================================================================
# Kirish jurnali va umumiy akkaunt alomatlari
# =============================================================================================
def _net(ip: str) -> str:
    ip = (ip or "").strip()
    if ":" in ip: return ":".join(ip.split(":")[:3])          # IPv6 /48
    p = ip.split(".")
    return ".".join(p[:3]) if len(p) == 4 else ip             # IPv4 /24


def on_login(student_id: int, ip: str, ua: str, ts: dt.datetime | None = None, con=None, src: str = "kabinet") -> dict:
    """Talaba kabinetiga muvaffaqiyatli kirish (student_portal.api_login dan). IP, tarmoq va User-Agent — faqat HMAC-xesh.
    Bir vaqtdagi sessiyalar: shu talabaning boshqa amaldagi sessiyasi (oxirgi PARALLEL_IDLE_MIN daqiqada faol) boshqa tarmoqdan."""
    import time as _t
    con = con or _con
    from . import sessions as SS
    st = db.one(con, "SELECT study_form FROM students WHERE id=?", (student_id,))
    if not st or st["study_form"] != "masofaviy": return {"new": 0, "updated": 0}     # jurnal — faqat masofaviy talabalar
    ts = ts or _now()
    net = _hm(con, "net", _net(ip))
    par = 0
    try:
        for r in db.rows(con, "SELECT ip FROM student_sessions WHERE student_id=? AND expires>? AND last_seen>?",
                         (student_id, _t.time(), _t.time() - PARALLEL_IDLE_MIN * 60)):
            if _hm(con, "net", _net(r["ip"])) != net: par = 1
    except Exception:
        pass
    with _lock:
        con.execute("INSERT INTO yy_access(student_id,ts,kind,ip_hash,net_hash,ua_hash,ua_label,parallel,src) VALUES(?,?,?,?,?,?,?,?,?)",
                    (student_id, _iso(ts), "login", _hm(con, "ip", ip), net, _hm(con, "ua", ua or ""), SS.device(ua)[:60], par, src))
        con.commit()
    r = detect_flags(con, student_id, ts)
    if r["new"]: _inv()
    return r


def analyze(events: list[dict]) -> list[dict]:
    """Sof funksiya (testlanadi): kirishlar (vaqt bo'yicha) → alomatlar [{kind, ts_first, ts_last, n, detail, evidence}].
    events: {ts (ISO), net, ua, parallel}."""
    ev = sorted(events, key=lambda e: e["ts"])
    out = {}
    def hit(kind, a, b, detail):
        f = out.setdefault(kind, {"kind": kind, "ts_first": a["ts"], "ts_last": b["ts"], "n": 0, "detail": detail, "evidence": []})
        f["ts_last"] = max(f["ts_last"], b["ts"]); f["n"] += 1; f["detail"] = detail
        if len(f["evidence"]) < 10: f["evidence"].append([a["ts"], b["ts"]])
    for e in ev:
        if e.get("parallel"): hit("parallel", e, e, "Kirish paytida boshqa tarmoqdan ochilgan faol sessiya bor edi")
    for a, b in zip(ev, ev[1:]):
        gap = (dt.datetime.fromisoformat(b["ts"]) - dt.datetime.fromisoformat(a["ts"])).total_seconds() / 60
        if gap <= SWITCH_MIN and a["net"] != b["net"] and a["ua"] != b["ua"]:
            hit("almashish", a, b, f"{int(gap)} daqiqa ichida boshqa tarmoq va boshqa qurilmadan kirish")
    by_day = {}
    for e in ev: by_day.setdefault(e["ts"][:10], []).append(e)
    for d, xs in by_day.items():
        nets = {x["net"] for x in xs}
        if len(nets) >= MANY_NETS: hit("kop_tarmoq", xs[0], xs[-1], f"{_dmy(d)}: {len(nets)} ta turli tarmoqdan kirish")
    return list(out.values())


def detect_flags(con, student_id: int, now: dt.datetime | None = None) -> dict:
    """Oxirgi 7 kun kirishlari bo'yicha alomatlar → yy_flags (idempotent). Ko'rib chiqilmagani yangilanadi; ko'rib chiqilgandan keyin yangi
    dalil bo'lsa — yangi belgi. Avtomatik bloklash YO'Q."""
    now = now or _now()
    ev = [{"ts": r["ts"], "net": r["net_hash"], "ua": r["ua_hash"], "parallel": r["parallel"]} for r in db.rows(con,
          "SELECT ts, net_hash, ua_hash, parallel FROM yy_access WHERE student_id=? AND ts>=? ORDER BY ts", (student_id, _iso(now - dt.timedelta(days=7))))]
    res = {"new": 0, "updated": 0}
    with _lock:
        for f in analyze(ev):
            o = db.one(con, "SELECT * FROM yy_flags WHERE student_id=? AND kind=? AND status='yangi'", (student_id, f["kind"]))
            if o:
                if o["ts_last"] != f["ts_last"] or o["n"] != f["n"]:
                    con.execute("UPDATE yy_flags SET ts_last=?, n=?, detail=?, evidence=? WHERE id=?",
                                (f["ts_last"], f["n"], f["detail"], json.dumps(f["evidence"]), o["id"])); res["updated"] += 1
                continue
            rv = db.one(con, "SELECT MAX(reviewed_at) t FROM yy_flags WHERE student_id=? AND kind=? AND status!='yangi'", (student_id, f["kind"]))
            if rv and rv["t"] and f["ts_last"] <= rv["t"]: continue
            con.execute("INSERT INTO yy_flags(student_id,kind,ts_first,ts_last,n,detail,evidence,status,created_at) VALUES(?,?,?,?,?,?,?,'yangi',?)",
                        (student_id, f["kind"], f["ts_first"], f["ts_last"], f["n"], f["detail"], json.dumps(f["evidence"]), _iso(now)))
            res["new"] += 1
        con.commit()
    return res


def journal(c: Ctx, student_id: int, days: int = 30) -> dict:
    guard(c, "kirish jurnali", DEPT, f"talaba #{student_id}")
    st = db.one(_con, """SELECT s.id, s.full_name, s.hemis_id, s.citizenship, s.status, g.name grp FROM students s JOIN groups_ g ON g.id=s.group_id
                         WHERE s.id=? AND s.study_form='masofaviy'""", (student_id,))
    if not st: raise HTTPException(404, "Masofaviy talaba topilmadi")
    since = _iso(_now() - dt.timedelta(days=days))
    logins = db.rows(_con, "SELECT ts, ua_label, net_hash, ua_hash, parallel, src FROM yy_access WHERE student_id=? AND ts>=? ORDER BY ts DESC LIMIT 300",
                     (student_id, since))
    nets = {}
    for r in sorted(logins, key=lambda r: r["ts"]): nets.setdefault(r["net_hash"], f"T{len(nets) + 1}")
    devs = {}
    for r in sorted(logins, key=lambda r: r["ts"]): devs.setdefault(r["ua_hash"], f"Q{len(devs) + 1}")
    launches, stmts = [], []
    try:
        launches = db.rows(_con, "SELECT created ts, course_ref, lesson_ref FROM lrs_tokens WHERE student_id=? AND created>=? ORDER BY created DESC LIMIT 200",
                           (student_id, since))
        stmts = db.rows(_con, """SELECT substr(ts,1,10) d, COUNT(*) n FROM lrs_statements WHERE student_id=? AND ts>=? AND COALESCE(voided,0)=0
                                 GROUP BY 1 ORDER BY 1 DESC""", (student_id, since))
    except Exception:
        pass
    flags = db.rows(_con, "SELECT * FROM yy_flags WHERE student_id=? ORDER BY id DESC", (student_id,))
    inperson = db.rows(_con, """SELECT s.id, s.kind, s.title, s.date, a.status, a.method, a.doc_match, a.photo_ok, a.checked_at FROM yy_assign a
        JOIN yy_sessions s ON s.id=a.session_id WHERE a.student_id=? ORDER BY s.date DESC""", (student_id,))
    days_l = {}
    for r in logins: days_l.setdefault(r["ts"][:10], {"d": r["ts"][:10], "logins": 0, "launches": 0, "statements": 0})["logins"] += 1
    for r in launches: days_l.setdefault(r["ts"][:10], {"d": r["ts"][:10], "logins": 0, "launches": 0, "statements": 0})["launches"] += 1
    for r in stmts: days_l.setdefault(r["d"], {"d": r["d"], "logins": 0, "launches": 0, "statements": 0})["statements"] = r["n"]
    return {"student": {**st, "country": country(st["citizenship"]), "foreign": is_foreign(st["citizenship"])},
            "logins": [{"ts": r["ts"], "device": r["ua_label"], "net": nets[r["net_hash"]], "dev": devs[r["ua_hash"]], "parallel": bool(r["parallel"]),
                        "src": r["src"]} for r in logins],
            "days": sorted(days_l.values(), key=lambda x: x["d"], reverse=True),
            "totals": {"logins": len(logins), "networks": len(nets), "devices": len(devs), "launches": len(launches), "statements": sum(r["n"] for r in stmts)},
            "flags": [_flag_view(f) for f in flags], "inperson": [{**r, "kind_label": KINDS.get(r["kind"], r["kind"]), "status_label": A_ST.get(r["status"], r["status"])}
                                                               for r in inperson],
            "note": "IP manzil va qurilma ma'lumoti saqlanmaydi — faqat xesh; tarmoqlar (T1, T2…) va qurilmalar (Q1, Q2…) shu talaba doirasida raqamlangan."}


def _flag_view(f: dict) -> dict:
    return {"id": f["id"], "student_id": f["student_id"], "kind": f["kind"], "kind_label": FLAG_T.get(f["kind"], f["kind"]), "ts_first": f["ts_first"],
            "ts_last": f["ts_last"], "n": f["n"], "detail": f["detail"], "status": f["status"], "status_label": FLAG_ST.get(f["status"], f["status"]),
            "reviewed_name": _short(f.get("reviewed_name")) or f.get("reviewed_name"), "reviewed_at": f.get("reviewed_at"), "review_note": f.get("review_note")}


def flags_list(c: Ctx, status: str = "yangi") -> dict:
    guard(c, "umumiy akkaunt belgilari", DEPT)
    w, a = ("f.status=?", [status]) if status in FLAG_ST else ("1=1", [])
    rows = db.rows(_con, f"""SELECT f.*, s.full_name, s.hemis_id, g.name grp FROM yy_flags f JOIN students s ON s.id=f.student_id
                             JOIN groups_ g ON g.id=s.group_id WHERE {w} ORDER BY f.status='yangi' DESC, f.ts_last DESC LIMIT 300""", a)
    cnt = {r["status"]: r["n"] for r in db.rows(_con, "SELECT status, COUNT(*) n FROM yy_flags GROUP BY 1")}
    return {"items": [{**_flag_view(r), "full_name": r["full_name"], "hemis_id": r["hemis_id"], "grp": r["grp"]} for r in rows],
            "counts": {k: cnt.get(k, 0) for k in FLAG_ST}, "rules": {"parallel_idle_min": PARALLEL_IDLE_MIN, "switch_min": SWITCH_MIN, "many_nets": MANY_NETS}}


class ReviewIn(BaseModel):
    decision: str
    note: str = Field("", max_length=500)


def review_flag(c: Ctx, fid: int, b: ReviewIn) -> dict:
    guard(c, "belgini ko'rib chiqish", DEPT, f"belgi #{fid} · {b.decision}")
    if b.decision not in ("tasdiqlandi", "asossiz"): raise HTTPException(400, "Qaror: tasdiqlandi yoki asossiz")
    if len(b.note.strip()) < 3: raise HTTPException(400, "Izoh yozing (nima tekshirildi)")
    f = db.one(_con, "SELECT * FROM yy_flags WHERE id=?", (fid,))
    if not f: raise HTTPException(404, "Belgi topilmadi")
    if f["status"] != "yangi": raise HTTPException(409, "Belgi allaqachon ko'rib chiqilgan")
    _con.execute("UPDATE yy_flags SET status=?, reviewed_by=?, reviewed_name=?, reviewed_at=?, review_note=? WHERE id=?",
                 (b.decision, c.user["id"], c.user["full_name"], _iso(_now()), " ".join(b.note.split())[:500], fid))
    _con.commit(); _inv()
    return {"ok": True, "status": b.decision}


def open_flags(con) -> tuple[int, str | None]:
    r = db.one(con, "SELECT COUNT(DISTINCT student_id) n, MIN(created_at) t FROM yy_flags WHERE status='yangi'") or {}
    return int(r.get("n") or 0), r.get("t")


# =============================================================================================
# Huquqiy chegaralar
# =============================================================================================
def _rules(con) -> dict:
    from . import nazorat as NZ
    R = NZ.rules(con)
    return {"bakalavr": R.get("dl_quota_bachelor", 300), "magistr": R.get("dl_quota_master", 30), "teacher": R.get("dl_per_teacher", 50),
            "warn_pct": R.get("dl_quota_warn_pct", 90)}


def is_pedagogical(con, direction: str, level: str) -> tuple[bool, str]:
    r = db.one(con, "SELECT pedagogik, src FROM yy_programs WHERE direction=? AND level=?", (direction, level))
    if r: return bool(r["pedagogik"]), r["src"]
    d = (direction or "").lower().replace("ʻ", "'").replace("’", "'")
    return any(w in d for w in PED_WORDS), "avto"


def level_of(n: int, limit: int, warn_pct: int) -> str:
    """≥ 100 % — qizil (kvota to'lgan yoki oshgan), ≥ warn_pct % — sariq."""
    if limit <= 0: return "ok"
    if n >= limit: return "red"
    if n * 100 >= limit * warn_pct: return "amber"
    return "ok"


def limits_report(con, R: dict | None = None) -> dict:
    R = R or _rules(con)
    active = "s.status IN ('faol', 'akademik ta''til')"
    progs = db.rows(con, f"""SELECT g.direction, g.level, SUM(s.study_form='masofaviy') dist, SUM(s.study_form='kunduzgi') full_time
        FROM students s JOIN groups_ g ON g.id=s.group_id WHERE {active} GROUP BY g.direction, g.level""")
    out_p = []
    for p in progs:
        if not p["dist"]: continue
        lim = R["magistr"] if p["level"] == "magistr" else R["bakalavr"]
        ped, ped_src = is_pedagogical(con, p["direction"], p["level"])
        lv = level_of(p["dist"], lim, R["warn_pct"])
        out_p.append({"direction": p["direction"], "level": p["level"], "distance": p["dist"], "full_time": p["full_time"] or 0, "limit": lim,
                      "pct": round(100 * p["dist"] / lim, 1) if lim else None, "level_flag": lv, "over": p["dist"] > lim,
                      "no_full_time": not p["full_time"], "pedagogical": ped, "ped_src": ped_src})
    out_p.sort(key=lambda x: (-x["pct"] if x["pct"] is not None else 0))
    trows = db.rows(con, f"""SELECT t.id, t.full_name, d.name dept, COUNT(DISTINCT s.id) n FROM teacher_groups tg JOIN teachers t ON t.id=tg.teacher_id
        LEFT JOIN departments d ON d.id=t.department_id JOIN students s ON s.group_id=tg.group_id AND s.study_form='masofaviy' AND {active}
        GROUP BY t.id ORDER BY n DESC""")
    TL = R["teacher"]
    teachers = [{"id": t["id"], "name": t["full_name"], "dept": t["dept"], "n": t["n"], "limit": TL,
                 "level_flag": "red" if t["n"] > TL else "amber" if t["n"] * 100 >= TL * R["warn_pct"] else "ok"} for t in trows]
    tot_t = len(trows); tot_s = db.one(con, f"SELECT COUNT(*) n FROM students s WHERE s.study_form='masofaviy' AND {active}")["n"]
    return {"rules": R, "programs": out_p, "teachers": teachers[:400],
            "summary": {"programs_red": sum(p["level_flag"] == "red" for p in out_p), "programs_amber": sum(p["level_flag"] == "amber" for p in out_p),
                        "programs_over": sum(p["over"] for p in out_p), "no_full_time": sum(p["no_full_time"] for p in out_p),
                        "pedagogical": sum(p["pedagogical"] for p in out_p), "teachers_red": sum(t["level_flag"] == "red" for t in teachers),
                        "teachers_amber": sum(t["level_flag"] == "amber" for t in teachers), "teachers_total": tot_t, "students": tot_s,
                        "ratio": round(tot_s / tot_t, 1) if tot_t else None},
            "basis": "Talabalar: faol va akademik ta'tildagi. O'qituvchi yuklamasi: o'qituvchi dars beradigan masofaviy guruhlardagi talabalar (takrorlanmasdan). "
                     "Pedagogik yo'nalish — nomi bo'yicha avtomatik (pedagogika, ta'lim, o'qitish) yoki qo'lda belgilangan.",
            "legal_note": LEGAL_NOTE}


class ProgramIn(BaseModel):
    direction: str = Field(..., max_length=200)
    level: str = "bakalavr"
    pedagogik: bool


def set_program(c: Ctx, b: ProgramIn) -> dict:
    guard(c, "yo'nalish turini belgilash", PROGRAM_EDIT, f"{b.direction} · {b.level} · pedagogik={b.pedagogik}")
    if not db.one(_con, "SELECT 1 x FROM groups_ WHERE direction=? AND level=?", (b.direction, b.level)): raise HTTPException(404, "Yo'nalish topilmadi")
    _con.execute("""INSERT INTO yy_programs(direction,level,pedagogik,src,updated_at,updated_by) VALUES(?,?,?,'qo''lda',?,?)
                    ON CONFLICT(direction,level) DO UPDATE SET pedagogik=excluded.pedagogik, src='qo''lda', updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by""", (b.direction, b.level, int(b.pedagogik), _iso(_now()), c.user["full_name"]))
    _con.commit()
    try:
        from . import nazorat as NZ; NZ.invalidate()
    except Exception: pass
    return {"ok": True}


# =============================================================================================
# Ko'rinishlar
# =============================================================================================
def meta(c: Ctx) -> dict:
    guard(c, "ochish", ALL)
    term = cur_term()
    return {"role": c.role.key, "term": term, "term_label": term_label(term), "deadline": deadline(_con, term), "today": clock.today().isoformat(),
            "kinds": KINDS, "states": {k: v[0] for k, v in STATES.items()}, "methods": METHODS, "flag_kinds": FLAG_T,
            "caps": {"manage": c.role.key in MANAGE, "sign": c.role.key in SIGN, "names": c.role.key in MANAGE + (TUT,), "journal": c.role.key in DEPT,
                     "limits": c.role.key in LIMITS_VIEW, "programs": c.role.key in PROGRAM_EDIT, "deadline": c.role.key in SIGN,
                     "idref": c.role.key in (HEAD, REG, REG_X), "citizenship": c.role.key in (HEAD, REG, REG_X)},
            "scope": "O'z guruhlaringiz talabalari" if c.role.key == TUT else "Masofaviy ta'lim talabalari",
            "demo": _meta(_con, "seed_v1") is not None and _meta(_con, "source", "demo") == "demo", "legal_note": LEGAL_NOTE,
            "rooms": ["Asosiy bino, 115-xona", "Eco bino, 105-xona", "Asosiy bino, kompyuter zali 2", "Asosiy bino, majlislar zali"]}


def overview(c: Ctx) -> dict:
    guard(c, "umumiy", ALL)
    term = cur_term()
    cn = counts(_con, term, c)
    up = [x for x in list_sessions(c, term) if x["status"] == "rejada"]
    up.sort(key=lambda x: (x["date"], x["start_time"]))
    n_fl, _ = open_flags(_con)
    return {"term": term, "term_label": term_label(term), "deadline": deadline(_con, term), "deadline_passed": clock.today().isoformat() > deadline(_con, term),
            "counts": cn, "upcoming": up[:12], "flags_open": n_fl if c.role.key in DEPT + LEAD else None,
            "limits": limits_report(_con)["summary"] if c.role.key in LIMITS_VIEW else None}


def students(c: Ctx, state: str = "", q: str = "", offset: int = 0, limit: int = 50) -> dict:
    guard(c, "talabalar ro'yxati", MANAGE + (TUT,), f"{state} {q}".strip())
    w, a = "", []
    if q:
        w = " AND (s.full_name LIKE ? OR s.hemis_id LIKE ? OR g.name LIKE ?)"; a = [f"%{q}%"] * 3
    rows = student_states(_con, cur_term(), c, w, a)
    if state: rows = [r for r in rows if r["state"] == state]
    rows.sort(key=lambda r: (r["state"] != "muddati_otgan", r["grp"] or "", r["full_name"] or ""))
    return {"total": len(rows), "items": [{**r, "state_label": STATES[r["state"]][0], "state_cls": STATES[r["state"]][1], "country": country(r["citizenship"])}
                                          for r in rows[offset:offset + min(200, limit)]]}


class CitIn(BaseModel):
    citizenship: str = Field(..., min_length=2, max_length=3)


def set_citizenship(c: Ctx, sid: int, b: CitIn) -> dict:
    guard(c, "fuqarolikni o'zgartirish", (HEAD, REG, REG_X), f"talaba #{sid} → {b.citizenship}")
    cc = b.citizenship.upper()
    if not re.fullmatch(r"[A-Z]{2,3}", cc): raise HTTPException(400, "Mamlakat kodi (ISO): UZ, KZ, TJ …")
    cur = _con.execute("UPDATE students SET citizenship=? WHERE id=? AND study_form='masofaviy'", (None if cc in ("UZ", "UZB") else cc, sid))
    _con.commit()
    if cur.rowcount != 1: raise HTTPException(404, "Masofaviy talaba topilmadi")
    _inv()
    return {"ok": True, "foreign": is_foreign(cc), "country": country(cc)}


class DeadlineIn(BaseModel):
    date: str = Field(..., max_length=10)


def set_deadline(c: Ctx, b: DeadlineIn) -> dict:
    guard(c, "ro'yxatdan o'tish muddati", SIGN, b.date)
    try: d = dt.date.fromisoformat(b.date)
    except ValueError: raise HTTPException(400, "Sana YYYY-MM-DD ko'rinishida")
    term = cur_term()
    if not (term_start(term) - dt.timedelta(days=60) <= d <= term_end(term)): raise HTTPException(400, "Muddat joriy semestr doirasida bo'lsin")
    _con.execute("INSERT INTO yy_meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (f"deadline:{term}", d.isoformat()))
    _con.commit()
    try:
        from . import nazorat as NZ; NZ.invalidate()
    except Exception: pass
    return {"ok": True, "deadline": d.isoformat()}


# ---------------- talaba kabineti ----------------
def student_card(s: dict) -> dict:
    """Talaba o'z holatini ko'radi (faqat o'zi: id sessiyadan)."""
    term = cur_term()
    st = db.one(_con, "SELECT id, status, study_form, citizenship FROM students WHERE id=?", (s["id"],))
    if not st or st["study_form"] != "masofaviy": return {"applies": False}
    reg, up, dl, today = registered_ids(_con, term), upcoming_map(_con, term), deadline(_con, term), clock.today().isoformat()
    state = state_of(st, reg, up, dl, today)
    mine = db.rows(_con, """SELECT s.id, s.kind, s.title, s.date, s.start_time, s.end_time, s.room, s.status sstatus, a.status FROM yy_assign a
        JOIN yy_sessions s ON s.id=a.session_id WHERE a.student_id=? AND s.status!='bekor' ORDER BY s.date DESC""", (s["id"],))
    nxt = next((m for m in sorted(mine, key=lambda m: (m["date"], m["start_time"])) if m["sstatus"] == "rejada" and m["date"] >= today), None)
    banner = None
    if state == "muddati_otgan":
        banner = {"level": "bad", "title": "Yuzma-yuz ro'yxatdan o'tish muddati o'tdi",
                  "text": (f"Muddat {_dmy(dl)} edi. " + (f"Sizga tayinlangan sessiya: {_dmy(nxt['date'])}, {nxt['start_time']}, {nxt['room']}."
                           if nxt else "Masofaviy ta'lim bo'limiga murojaat qiling — sizga sessiya tayinlanadi."))}
    elif state in ("kutilmoqda", "tayinlangan"):
        banner = {"level": "warn", "title": "Semestr oldidan yuzma-yuz ro'yxatdan o'ting",
                  "text": (f"Muddat — {_dmy(dl)}. " + (f"Sessiyangiz: {_dmy(nxt['date'])}, {nxt['start_time']}, {nxt['room']}." if nxt
                           else "Sessiya hali tayinlanmagan — bo'lim xabar beradi."))}
    return {"applies": True, "term": term, "term_label": term_label(term), "deadline": dl, "state": state, "state_label": STATES[state][0],
            "state_cls": STATES[state][1], "foreign": is_foreign(st["citizenship"]), "banner": banner,
            "next": {k: nxt[k] for k in ("kind", "title", "date", "start_time", "end_time", "room")} | {"kind_label": KINDS.get(nxt["kind"], "")} if nxt else None,
            "items": [{"kind_label": KINDS.get(m["kind"], m["kind"]), "title": m["title"], "date": m["date"], "start_time": m["start_time"],
                       "end_time": m["end_time"], "room": m["room"], "status": m["status"], "status_label": A_ST.get(m["status"], m["status"])} for m in mine[:20]],
            "bring": "Pasport yoki ID karta (asl nusxa). Shaxsingiz hujjat va rasm bo'yicha tekshiriladi; hujjat raqami saqlanmaydi."}


# =============================================================================================
# Demo ma'lumot (sun'iy) — bir marta (yy_meta.seed_v1)
# =============================================================================================
def seed(con, force: bool = False):
    if not force and con.execute("SELECT 1 FROM yy_meta WHERE k='seed_v1'").fetchone(): return
    if not con.execute("SELECT 1 FROM students WHERE study_form='masofaviy' LIMIT 1").fetchone(): return
    rnd = random.Random(559)
    today = clock.today(); term = term_of(today); t0 = term_start(term)
    ds = [r[0] for r in con.execute("SELECT id FROM students WHERE study_form='masofaviy' ORDER BY id").fetchall()]
    act = [r[0] for r in con.execute("SELECT id FROM students WHERE study_form='masofaviy' AND status='faol' ORDER BY id").fetchall()]
    # 1) fuqarolik: ~1,2 % xorijiy (namuna)
    foreign = rnd.sample(act, max(3, len(act) // 80))
    for i, sid in enumerate(foreign):
        con.execute("UPDATE students SET citizenship=? WHERE id=? AND citizenship IS NULL", (["KZ", "TJ", "TM", "AF", "KG", "TR"][i % 6], sid))
    fset = set(foreign)
    uz = [i for i in act if i not in fset]
    rnd.shuffle(uz)
    # 2) o'tgan ro'yxatdan o'tish sessiyalari: semestr boshidan har 3 kunda, 8 ta (o'tgan sanalar — yopilgan)
    rooms = ["Asosiy bino, 115-xona", "Eco bino, 105-xona"]
    staff = con.execute("SELECT id, full_name FROM users WHERE role IN ('masofaviy_xodim','registrator_xodim') ORDER BY id").fetchall() or \
        con.execute("SELECT id, full_name FROM users WHERE role='masofaviy'").fetchall()
    head = con.execute("SELECT id, full_name FROM users WHERE role='masofaviy' ORDER BY id").fetchone()
    n_miss = int(len(uz) * 0.035); missing = uz[:n_miss]; pool = uz[n_miss:]
    per = max(1, -(-len(pool) // 8))
    created = _iso(dt.datetime.combine(t0 - dt.timedelta(days=10), dt.time(10)))
    for k in range(8):
        d = t0 + dt.timedelta(days=2 + 3 * k)
        if d >= today: d = today - dt.timedelta(days=1 + k)
        part = pool[k * per:(k + 1) * per]
        if not part: continue
        sid = con.execute("""INSERT INTO yy_sessions(kind,term,title,date,start_time,end_time,room,capacity,direction,note,status,created_by,created_name,
            created_at,closed_at,src) VALUES('royxat',?,?,?,?,?,?,?,'','',?,?,?,?,?,'demo')""",
            (term, f"Semestr ro'yxati — {k + 1}-oqim", d.isoformat(), "09:00", "17:00", rooms[k % 2], len(part) + 20, "rejada",
             head[0] if head else None, head[1] if head else "", created, None)).lastrowid
        for j, st in enumerate(part):
            who = staff[j % len(staff)]
            tm = dt.datetime.combine(d, dt.time(9)) + dt.timedelta(minutes=int(j * 480 / max(1, len(part))))
            r = rnd.random()
            if r < 0.025: status, m, dm, ph = "kelmadi", None, None, None
            elif r < 0.03: status, m, dm, ph = "shubhali", "pasport", 1, 0
            else: status, m, dm, ph = "keldi", rnd.choice(["pasport", "id_karta", "id_karta", "hemis"]), 1, 1
            con.execute("""INSERT INTO yy_assign(session_id,student_id,assigned_at,assigned_by,status,method,doc_match,match_src,photo_ok,checked_by,checked_name,checked_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (sid, st, created, head[0] if head else None, status, m, dm, "xodim" if m else None, ph,
                                                     who[0] if m else None, who[1] if m else None, _iso(tm) if m else None))
        # qaydnoma (imzolangan)
        ts = _iso(dt.datetime.combine(d, dt.time(17, 30)))
        con.execute("UPDATE yy_sessions SET status='yopilgan', closed_at=? WHERE id=?", (ts, sid))
        st = con.execute("SELECT COUNT(*), SUM(status='keldi'), SUM(status='shubhali'), SUM(status='kelmadi') FROM yy_assign WHERE session_id=?", (sid,)).fetchone()
        reg = f"YQ-{d.year % 100:02d}/{k + 1:04d}"; code = secrets.token_hex(4).upper()
        con.execute("""INSERT INTO yy_protocols(session_id,reg_no,verify_code,signed_by,signed_name,signed_role,signed_at,sha256,stats) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (sid, reg, code, head[0] if head else None, head[1] if head else "", "Masofaviy ta'lim bo'limi boshlig'i", ts, "",
                     json.dumps({"tayinlangan": st[0], "keldi": st[1], "shubhali": st[2], "kelmadi": st[3]})))
        try:
            con.execute("""INSERT INTO documents(reg_no,kind,title,holder,created_by,creator_role,created_at,status,verify_code,file,params,signed_at)
                VALUES(?,?,?,?,?,?,?,'berilgan',?,?,?,?)""", (reg, "yy_qaydnoma", "Yuzma-yuz tadbir qaydnomasi: " + KINDS["royxat"],
                     f"Semestr ro'yxati — {k + 1}-oqim · {_dmy(d.isoformat())}", head[0] if head else None, "Masofaviy ta'lim bo'limi", ts, code,
                     f"yuzma:{sid}", json.dumps({"session_id": sid}), ts))
        except Exception:
            pass
    # 3) rejadagi: qo'shimcha ro'yxat sessiyasi (6 kundan keyin) va yakuniy nazorat (semestr oxirida)
    up_d = today + dt.timedelta(days=6)
    sid = con.execute("""INSERT INTO yy_sessions(kind,term,title,date,start_time,end_time,room,capacity,direction,note,status,created_by,created_name,created_at,src)
        VALUES('royxat',?,?,?,?,?,?,?,'','Muddatni o''tkazib yuborganlar uchun',?,?,?,?,'demo')""",
        (term, "Qo'shimcha ro'yxatdan o'tish", up_d.isoformat(), "10:00", "16:00", rooms[0], 80, "rejada",
         head[0] if head else None, head[1] if head else "", _iso(_now()))).lastrowid
    for st in missing[:50]:
        con.execute("INSERT INTO yy_assign(session_id,student_id,assigned_at,assigned_by,status) VALUES(?,?,?,?,'tayinlangan')",
                    (sid, st, _iso(_now()), head[0] if head else None))
    ex_d = max(term_end(term) - dt.timedelta(days=14), today + dt.timedelta(days=20))
    g = con.execute("""SELECT g.id, g.name, g.direction FROM groups_ g WHERE g.form='masofaviy' AND g.course=4 ORDER BY g.id LIMIT 1""").fetchone()
    if g:
        ids = [r[0] for r in con.execute("SELECT id FROM students WHERE group_id=? AND status='faol' AND citizenship IS NULL ORDER BY full_name", (g[0],)).fetchall()]
        sid = con.execute("""INSERT INTO yy_sessions(kind,term,title,date,start_time,end_time,room,capacity,direction,note,status,created_by,created_name,created_at,src)
            VALUES('imtihon',?,?,?,?,?,?,?,?,'',?,?,?,?,'demo')""", (term, f"Yakuniy nazorat — {g[1]}", ex_d.isoformat(), "09:00", "12:00",
            "Asosiy bino, kompyuter zali 2", max(len(ids), 30), g[2], "rejada", head[0] if head else None, head[1] if head else "", _iso(_now()))).lastrowid
        for st in ids:
            con.execute("INSERT INTO yy_assign(session_id,student_id,assigned_at,assigned_by,status) VALUES(?,?,?,?,'tayinlangan')",
                        (sid, st, _iso(_now()), head[0] if head else None))
    # 4) kirish jurnali (sun'iy): LRS statementi bor talabalar + tasodifiy 300 ta, oxirgi 21 kun
    import hashlib as _h
    def H(*p): return hmac.new(_salt(con), "|".join(map(str, p)).encode(), _h.sha256).hexdigest()[:24]
    devices = [("Chrome, Android", "Mozilla/5.0 (Linux; Android 13) Chrome/129"), ("Chrome, Windows", "Mozilla/5.0 (Windows NT 10.0) Chrome/129"),
               ("Safari, iPhone", "Mozilla/5.0 (iPhone; CPU iPhone OS 17) Safari/604"), ("Yandex, Android", "Mozilla/5.0 (Linux; Android 12) YaBrowser/24")]
    try:
        lrs_st = [r[0] for r in con.execute("SELECT DISTINCT student_id FROM lrs_statements WHERE student_id IS NOT NULL").fetchall()]
    except Exception:
        lrs_st = []
    sample = list(dict.fromkeys(lrs_st + rnd.sample(uz, min(300, len(uz)))))
    now = _now()
    rows = []
    for sid in sample:
        home = f"10.{rnd.randint(1, 250)}.{rnd.randint(0, 250)}.{rnd.randint(2, 250)}"; dev = rnd.choice(devices)
        for day in range(21, 0, -1):
            if rnd.random() < 0.45: continue
            t = dt.datetime.combine(today - dt.timedelta(days=day), dt.time(rnd.randint(8, 22), rnd.randint(0, 59)))
            ip = home if rnd.random() < 0.85 else f"172.{rnd.randint(16, 31)}.{rnd.randint(0, 250)}.{rnd.randint(2, 250)}"
            d2 = dev if rnd.random() < 0.9 else rnd.choice(devices)
            rows.append((sid, _iso(t), "login", H("ip", ip), H("net", _net(ip)), H("ua", d2[1]), d2[0], 0, "demo"))
    # ataylab qo'yilgan holatlar: umumiy akkaunt alomatlari
    planted = [x for x in uz if x not in set(sample)][:3]
    if len(planted) == 3:
        a, b, c3 = planted
        base_t = dt.datetime.combine(today - dt.timedelta(days=2), dt.time(20, 5))
        rows += [(a, _iso(base_t), "login", H("ip", "10.20.30.4"), H("net", "10.20.30"), H("ua", devices[1][1]), devices[1][0], 0, "demo"),
                 (a, _iso(base_t + dt.timedelta(minutes=12)), "login", H("ip", "10.77.1.9"), H("net", "10.77.1"), H("ua", devices[0][1]), devices[0][0], 1, "demo")]
        base_t = dt.datetime.combine(today - dt.timedelta(days=1), dt.time(9, 40))
        rows += [(b, _iso(base_t), "login", H("ip", "10.41.2.8"), H("net", "10.41.2"), H("ua", devices[2][1]), devices[2][0], 0, "demo"),
                 (b, _iso(base_t + dt.timedelta(minutes=6)), "login", H("ip", "10.99.5.3"), H("net", "10.99.5"), H("ua", devices[1][1]), devices[1][0], 0, "demo")]
        base_t = dt.datetime.combine(today - dt.timedelta(days=3), dt.time(8, 0))
        for i in range(5):
            ip = f"10.{60 + i}.{i}.7"
            rows.append((c3, _iso(base_t + dt.timedelta(hours=2 * i + 1)), "login", H("ip", ip), H("net", _net(ip)), H("ua", devices[0][1]), devices[0][0], 0, "demo"))
    con.executemany("INSERT INTO yy_access(student_id,ts,kind,ip_hash,net_hash,ua_hash,ua_label,parallel,src) VALUES(?,?,?,?,?,?,?,?,?)", rows)
    con.execute("INSERT OR REPLACE INTO yy_meta(k,v) VALUES('seed_v1',?)", (_iso(now),))
    con.execute("INSERT OR IGNORE INTO yy_meta(k,v) VALUES('source','demo')")
    con.commit()
    for sid in {r[0] for r in rows}:
        detect_flags(con, sid, now)


# =============================================================================================
# API
# =============================================================================================
def _mod_on() -> bool:
    try:
        from . import modules as MODS
        return MODS.on("masofaviy")
    except Exception:
        return True


@router.get(P + "/meta")
def api_meta(request: Request): return meta(C(request))

@router.get(P + "/overview")
def api_overview(request: Request): return overview(C(request))

@router.get(P + "/sessions")
def api_sessions(request: Request, kind: str = "", term: str = ""):
    c = C(request); guard(c, "sessiyalar", ALL)
    return {"items": list_sessions(c, term or None, kind)}

@router.post(P + "/sessions")
def api_session_new(body: SessionIn, request: Request): return create_session(C(request), body)

@router.get(P + "/sessions/{sid}")
def api_session(sid: int, request: Request): return session_detail(C(request), sid)

@router.post(P + "/sessions/{sid}/assign")
def api_assign(sid: int, body: AssignIn, request: Request): return assign(C(request), sid, body)

@router.post(P + "/sessions/{sid}/unassign/{student_id}")
def api_unassign(sid: int, student_id: int, request: Request): return unassign(C(request), sid, student_id)

@router.post(P + "/sessions/{sid}/check")
def api_check(sid: int, body: CheckIn, request: Request): return check(C(request), sid, body)

@router.post(P + "/sessions/{sid}/absent/{student_id}")
def api_absent(sid: int, student_id: int, request: Request): return mark_absent(C(request), sid, student_id)

@router.post(P + "/sessions/{sid}/sign")
def api_sign(sid: int, request: Request): return sign(C(request), sid)

class CancelIn(BaseModel):
    note: str = Field("", max_length=300)

@router.post(P + "/sessions/{sid}/cancel")
def api_cancel(sid: int, body: CancelIn, request: Request): return cancel(C(request), sid, body.note)

def _base(request: Request) -> str:
    try:
        from . import service as SV
        return SV.public_base(request)
    except Exception:
        return str(request.base_url)

@router.get(P + "/sessions/{sid}/protocol.docx")
def api_protocol_docx(sid: int, request: Request):
    data, name = protocol_docx(C(request), sid, _base(request))
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})

@router.get(P + "/sessions/{sid}/protocol.pdf")
def api_protocol_pdf(sid: int, request: Request):
    data, name = protocol_pdf(C(request), sid, _base(request))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})

@router.get(P + "/students")
def api_students(request: Request, state: str = "", q: str = "", offset: int = 0, limit: int = 50):
    return students(C(request), state, q[:80], max(0, offset), max(1, limit))

@router.post(P + "/students/{sid}/citizenship")
def api_citizenship(sid: int, body: CitIn, request: Request): return set_citizenship(C(request), sid, body)

@router.post(P + "/idref")
def api_idref(body: IdRefIn, request: Request): return set_idref(C(request), body)

@router.post(P + "/deadline")
def api_deadline(body: DeadlineIn, request: Request): return set_deadline(C(request), body)

@router.get(P + "/journal/{sid}")
def api_journal(sid: int, request: Request, days: int = 30): return journal(C(request), sid, max(1, min(days, 120)))

@router.get(P + "/flags")
def api_flags(request: Request, status: str = "yangi"): return flags_list(C(request), status)

@router.post(P + "/flags/{fid}/review")
def api_flag_review(fid: int, body: ReviewIn, request: Request): return review_flag(C(request), fid, body)

@router.get(P + "/limits")
def api_limits(request: Request):
    c = C(request); guard(c, "huquqiy chegaralar", LIMITS_VIEW)
    return {**limits_report(_con), "can_programs": c.role.key in PROGRAM_EDIT}

@router.post(P + "/programs")
def api_programs(body: ProgramIn, request: Request): return set_program(C(request), body)

@router.get("/api/talaba/yuzma")
def api_student_card(request: Request):
    from . import student_portal as SP
    s = SP.student(request)
    return student_card(s)
