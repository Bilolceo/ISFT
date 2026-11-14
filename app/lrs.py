"""LRS — xAPI 1.0.3 statement qabul qiluvchi va to'g'ridan-to'g'ri ishga tushirish (launch) yo'li (docs/lrs.md).

Nima uchun: NEXTID.LMS (my.isft.uz) xAPI paketlarni launch parametrlarisiz (endpoint, auth, actor) ochadi — talaba natijasi hech qayerga
yozilmaydi, NEXTID faqat dars bo'yicha foizni ko'rsatadi, kim ortda qolayotganini hech kim ko'rmaydi. Bu modul:

  1. LRS (xAPI 1.0.3 kichik to'plami): POST/PUT/GET /xapi/statements (bekor qilish — «voided», idempotent id), /xapi/about,
     /xapi/activities/state (resume). X-Experience-API-Version sarlavhasi majburiy. CORS — ochiq (cookie ishlatilmaydi, faqat token).
  2. Kirish: har bir ishga tushirish uchun alohida token (HMAC imzoli, muddatli, kurs/dars + talaba bilan cheklangan) — Basic auth sifatida
     launch parametrida beriladi. Paket ichida umumiy sir YO'Q. Talaba — taxallus (learner id, HMAC asosida), URL'da ism/email yo'q.
     Hamkor (NEXTID) uchun ixtiyoriy server-server kirish: ISFT_CORE_LRS_PARTNER="login:parol" (actor — HEMIS ID).
  3. Ishga tushirish: /xapi/l/<havola kodi> → yangi token → /xapi/pkg/<kod>/index.html?endpoint=…&auth=…&actor=…&registration=…&activity_id=…
     (eksport qilingan kurs/paket zip ichidan, qat'iy CSP: connect-src faqat /xapi/). NEXTID'ga bog'liq emas.
  4. Saqlash: lrs_statements (talaba, faoliyat, fe'l, vaqt bo'yicha indekslar), lrs_progress (talaba × dars jamlanmasi — har statementdan keyin
     qayta hisoblanadi, app/lrs_analytics.lesson_summary), lrs_activities (savol ta'riflari — variantlar, to'g'ri javob), lrs_state.
  5. Cheklovlar: so'rov ≤ 512 KB, bitta statement ≤ 32 KB, bir so'rovda ≤ 100 statement, token bo'yicha daqiqasiga 120 so'rov va soatiga
     3000 statement, IP bo'yicha daqiqasiga 600 so'rov (429 + Retry-After).

Demo: seed() — SUN'IY statementlar (src='demo') bir nechta masofaviy kurs uchun; sahifada «Namuna ma'lumot» belgisi.
"""
from __future__ import annotations
import base64, binascii, collections, datetime as dt, hashlib, hmac, json, math, os, random, re, secrets, threading, time, uuid, zipfile
from pathlib import Path
from urllib.parse import quote, urlencode
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response, RedirectResponse, PlainTextResponse
from pydantic import BaseModel, Field
from . import clock, db, rbac, lrs_analytics as LA
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()

XAPI_VERSION = "1.0.3"
HOME = "https://isft.uz"                                   # actor.account.homePage (talaba taxallusi shu «uy»da)
PAKET_BASE = "https://isft.uz/xapi/paket"                  # app/paket.py ACTIVITY_BASE bilan bir xil
KURS_BASE = "https://isft.uz/xapi/kurs"                    # app/kurs.py ACTIVITY_BASE bilan bir xil
VERB = "http://adlnet.gov/expapi/verbs/"
PROGRESS_EXT = "https://w3id.org/xapi/cmi5/result/extensions/progress"
MAX_BODY = 512 * 1024
MAX_STMT = 32 * 1024
MAX_BATCH = 100
MAX_STATE = 64 * 1024
AUTH_HOURS = 24
LINK_DAYS = 150
RATE_REQ = (120, 60)          # token: so'rov / soniya
RATE_STMT = (3000, 3600)      # token: statement / soniya
RATE_IP = (600, 60)           # IP: so'rov / soniya
DEPT = ("masofaviy", "masofaviy_xodim")
ALLOWED_KEYS = {"id", "actor", "verb", "object", "result", "context", "timestamp", "stored", "authority", "version", "attachments"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS lrs_statements(id TEXT PRIMARY KEY, stored TEXT, ts TEXT, student_id INT, learner TEXT, verb TEXT, verb_id TEXT,
  activity TEXT, course_ref TEXT, lesson_ref TEXT, item_ref TEXT, registration TEXT, success INT, completion INT, score REAL, response TEXT,
  duration REAL, progress REAL, voided INT DEFAULT 0, voids TEXT, digest TEXT, token TEXT, src TEXT DEFAULT 'lrs', raw TEXT);
CREATE INDEX IF NOT EXISTS ix_lrs_st_student ON lrs_statements(student_id, ts);
CREATE INDEX IF NOT EXISTS ix_lrs_st_act ON lrs_statements(activity, ts);
CREATE INDEX IF NOT EXISTS ix_lrs_st_verb ON lrs_statements(verb, ts);
CREATE INDEX IF NOT EXISTS ix_lrs_st_course ON lrs_statements(course_ref, lesson_ref, student_id);
CREATE INDEX IF NOT EXISTS ix_lrs_st_stored ON lrs_statements(stored);
CREATE INDEX IF NOT EXISTS ix_lrs_st_learner ON lrs_statements(learner, stored);
CREATE TABLE IF NOT EXISTS lrs_progress(student_id INT, course_ref TEXT, lesson_ref TEXT, status TEXT, pct REAL, score REAL, best REAL,
  attempts INT, fails INT, time_s REAL, first_ts TEXT, last_ts TEXT, updated TEXT, src TEXT, PRIMARY KEY(student_id, course_ref, lesson_ref));
CREATE INDEX IF NOT EXISTS ix_lrs_pr_course ON lrs_progress(course_ref, lesson_ref);
CREATE TABLE IF NOT EXISTS lrs_activities(id TEXT PRIMARY KEY, course_ref TEXT, lesson_ref TEXT, item_ref TEXT, type TEXT, name TEXT,
  description TEXT, itype TEXT, choices TEXT, correct TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS ix_lrs_acts ON lrs_activities(course_ref, lesson_ref);
CREATE TABLE IF NOT EXISTS lrs_state(activity TEXT, learner TEXT, state_id TEXT, registration TEXT, student_id INT, body TEXT, ctype TEXT,
  updated TEXT, PRIMARY KEY(activity, learner, state_id, registration));
CREATE TABLE IF NOT EXISTS lrs_learners(student_id INTEGER PRIMARY KEY, learner TEXT UNIQUE, created TEXT);
CREATE TABLE IF NOT EXISTS lrs_tokens(jti TEXT PRIMARY KEY, kind TEXT, student_id INT, course_ref TEXT, lesson_ref TEXT, exp INT, created TEXT,
  created_by INT, revoked INT DEFAULT 0, n_stmt INT DEFAULT 0, last_used TEXT);
CREATE INDEX IF NOT EXISTS ix_lrs_tok_st ON lrs_tokens(student_id, course_ref);
CREATE TABLE IF NOT EXISTS lrs_plan(course_ref TEXT PRIMARY KEY, lessons TEXT, weeks INT, start TEXT, src TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS lrs_policy(k TEXT PRIMARY KEY, v REAL);
CREATE TABLE IF NOT EXISTS lrs_actions(id INTEGER PRIMARY KEY, ts TEXT, student_id INT, course_ref TEXT, kind TEXT, user_id INT, user_name TEXT,
  tutor_user INT, task_id INT, notice_id INT, note TEXT, status TEXT DEFAULT 'ochiq');
CREATE INDEX IF NOT EXISTS ix_lrs_actions ON lrs_actions(student_id, kind, ts);
CREATE INDEX IF NOT EXISTS ix_lrs_actions_tutor ON lrs_actions(tutor_user, kind, status);
CREATE TABLE IF NOT EXISTS lrs_meta(k TEXT PRIMARY KEY, v TEXT);
"""


def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t: dt.datetime) -> str: return t.isoformat(timespec="seconds")


# =============================================================================================
# Sxema, bog'lash, kalit
# =============================================================================================
def init(con):
    try:
        con.executescript(SCHEMA)
        for k, v, _, _ in LA.POLICY:
            con.execute("INSERT OR IGNORE INTO lrs_policy(k,v) VALUES(?,?)", (k, v))
        con.commit()
    except Exception as e:
        print("lrs.init:", e); return
    try:
        if db.one(con, "SELECT 1 x FROM sqlite_master WHERE type='table' AND name='dl_courses'") and db.one(con, "SELECT 1 x FROM dl_courses"):
            seed(con)
            redate(con)
    except Exception as e:      # namuna ma'lumot ilovani to'xtatmasin
        print("lrs seed:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

_KEY: dict = {}

def _key(con=None) -> bytes:
    """HMAC kaliti: ISFT_CORE_LRS_KEY (hex/matn) yoki bazada bir marta yaratilgan tasodifiy kalit. Paketlarga HECH QACHON yozilmaydi."""
    con = con or _con
    if "k" not in _KEY:
        env = os.getenv("ISFT_CORE_LRS_KEY", "").strip()
        if env: _KEY["k"] = hashlib.sha256(env.encode()).digest()
        else:
            with _lock:
                con.execute("INSERT OR IGNORE INTO lrs_meta(k,v) VALUES('key', ?)", (secrets.token_hex(32),)); con.commit()
                _KEY["k"] = bytes.fromhex(db.one(con, "SELECT v FROM lrs_meta WHERE k='key'")["v"])
    return _KEY["k"]

def _sig(domain: str, msg: str, n: int = 32) -> str:
    return hmac.new(_key(), f"{domain}|{msg}".encode(), hashlib.sha256).hexdigest()[:n]

def policy(con=None) -> dict:
    con = con or _con
    have = {r["k"]: r["v"] for r in db.rows(con, "SELECT k, v FROM lrs_policy")}
    return {k: int(have.get(k, v)) for k, v, _, _ in LA.POLICY}


# =============================================================================================
# Talaba taxallusi (learner id) va tokenlar
# =============================================================================================
def learner_id(sid: int, con=None) -> str:
    """Barqaror taxallus: «s» + HMAC(talaba id) — URL'da ism, HEMIS ID yoki email bo'lmaydi; teskari moslash — lrs_learners jadvalida."""
    con = con or _con
    r = db.one(con, "SELECT learner FROM lrs_learners WHERE student_id=?", (int(sid),))
    if r: return r["learner"]
    lid = "s" + hmac.new(_key(con), f"learner|{int(sid)}".encode(), hashlib.sha256).hexdigest()[:20]
    with _lock:
        con.execute("INSERT OR IGNORE INTO lrs_learners(student_id,learner,created) VALUES(?,?,?)", (int(sid), lid, _iso(_now())))
        con.commit()
    return lid

def student_of(lid: str) -> int | None:
    r = db.one(_con, "SELECT student_id FROM lrs_learners WHERE learner=?", (str(lid or "")[:40],))
    return r["student_id"] if r else None

def actor_for(lid: str) -> dict:
    return {"objectType": "Agent", "account": {"homePage": HOME, "name": lid}}

def registration_for(lid: str, course_ref: str) -> str:
    """Bitta talaba × kurs — bitta registration (resume holati shu kalit bilan saqlanadi)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{HOME}/reg/{lid}/{course_ref}"))

def _b64e(b: bytes) -> str: return base64.urlsafe_b64encode(b).decode().rstrip("=")
def _b64d(s: str) -> bytes: return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def make_auth(sid: int, course_ref: str, lesson_ref: str = "", hours: float = AUTH_HOURS, created_by: int | None = None, con=None) -> dict:
    """Launch tokeni (Basic auth): login — jti, parol — imzolangan yuk {l: taxallus, c: kurs, s: dars, e: muddat, r: registration}.
    Faqat shu talaba va shu kurs/dars faoliyatlariga yozadi; muddati o'tgan yoki bekor qilingani — 401."""
    con = con or _con
    lid = learner_id(sid, con)
    jti = secrets.token_hex(8)
    exp = int(time.time() + hours * 3600)
    reg = registration_for(lid, course_ref)
    pl = _b64e(json.dumps({"l": lid, "c": course_ref, "s": lesson_ref or "", "e": exp, "r": reg}, separators=(",", ":")).encode())
    sig = _sig("auth", f"{jti}.{pl}")
    with _lock:
        con.execute("INSERT INTO lrs_tokens(jti,kind,student_id,course_ref,lesson_ref,exp,created,created_by) VALUES(?,?,?,?,?,?,?,?)",
                    (jti, "auth", int(sid), course_ref, lesson_ref or "", exp, _iso(_now()), created_by))
        con.commit()
    basic = base64.b64encode(f"{jti}:{pl}.{sig}".encode()).decode()
    return {"auth": "Basic " + basic, "jti": jti, "exp": exp, "learner": lid, "registration": reg, "course_ref": course_ref, "lesson_ref": lesson_ref or ""}

class XErr(Exception):
    def __init__(self, status: int, msg: str, headers: dict | None = None):
        super().__init__(msg); self.status, self.msg, self.headers = status, msg, headers or {}

def _partner() -> tuple[str, str] | None:
    v = os.getenv("ISFT_CORE_LRS_PARTNER", "").strip()
    if ":" not in v: return None
    u, p = v.split(":", 1)
    return (u, p) if u and len(p) >= 16 else None

def parse_auth(header: str | None) -> dict:
    """Authorization → kirish ko'lami: {"kind": "launch", jti, learner, student_id, course_ref, lesson_ref, registration} yoki {"kind": "partner"}."""
    if not header or not header.lower().startswith("basic "): raise XErr(401, "Authorization (Basic) talab qilinadi", {"WWW-Authenticate": 'Basic realm="ISFT LRS"'})
    try: raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError): raise XErr(401, "Authorization noto'g'ri")
    user, _, pw = raw.partition(":")
    pt = _partner()
    if pt and hmac.compare_digest(user.encode(), pt[0].encode()) and hmac.compare_digest(pw.encode(), pt[1].encode()):
        return {"kind": "partner", "jti": "partner:" + user}
    m = re.fullmatch(r"([0-9a-f]{16})", user)
    pl, _, sig = pw.rpartition(".")
    if not m or not pl or not re.fullmatch(r"[0-9a-f]{32}", sig or ""): raise XErr(401, "Token noto'g'ri")
    if not hmac.compare_digest(_sig("auth", f"{user}.{pl}"), sig): raise XErr(401, "Token imzosi noto'g'ri")
    try: d = json.loads(_b64d(pl))
    except (ValueError, binascii.Error): raise XErr(401, "Token noto'g'ri")
    if int(d.get("e") or 0) < time.time(): raise XErr(401, "Token muddati o'tgan — darsni qayta oching")
    t = db.one(_con, "SELECT revoked, student_id FROM lrs_tokens WHERE jti=?", (user,))
    if not t or t["revoked"]: raise XErr(401, "Token bekor qilingan")
    sid = student_of(d.get("l"))
    if sid is None or sid != t["student_id"]: raise XErr(401, "Token egasi topilmadi")
    return {"kind": "launch", "jti": user, "learner": d["l"], "student_id": sid, "course_ref": d.get("c") or "", "lesson_ref": d.get("s") or "",
            "registration": d.get("r") or ""}

def make_link(sid: int, course_ref: str, lesson_ref: str = "", days: int = LINK_DAYS) -> str:
    """Uzoq muddatli ishga tushirish havolasi kodi (talaba kabineti, Telegram eslatma, NEXTID tashqi havola). Ichida faqat taxallus va kurs."""
    lid = learner_id(sid)
    pl = _b64e(json.dumps({"l": lid, "c": course_ref, "s": lesson_ref or "", "e": int(time.time() + days * 86400)}, separators=(",", ":")).encode())
    return f"{pl}.{_sig('link', pl, 24)}"

def parse_link(code: str) -> dict:
    pl, _, sig = (code or "").rpartition(".")
    if not pl or len(code) > 600 or not re.fullmatch(r"[A-Za-z0-9_\-]+", pl) or not hmac.compare_digest(_sig("link", pl, 24), sig or ""):
        raise HTTPException(403, "Havola yaroqsiz")
    d = json.loads(_b64d(pl))
    if int(d.get("e") or 0) < time.time(): raise HTTPException(403, "Havola muddati o'tgan — yangi havola so'rang")
    sid = student_of(d.get("l"))
    if sid is None: raise HTTPException(403, "Havola yaroqsiz")
    return {"learner": d["l"], "student_id": sid, "course_ref": d.get("c") or "", "lesson_ref": d.get("s") or ""}


# =============================================================================================
# Faoliyat identifikatorlari → kurs / dars / element
# =============================================================================================
_PK_RX = re.compile(r"^https://isft\.uz/xapi/paket/(\d{1,9})/((?:Lab|MT|L|A|S)?\d{1,3})(?:/(block/[A-Za-z0-9_\-]{1,40}(?:/q/[A-Za-z0-9_\-.%]{1,80})?))?$")
_KU_RX = re.compile(r"^https://isft\.uz/xapi/kurs/(\d{1,9})(?:/lesson/([a-z][a-z0-9]{5,23})(?:/(q/[A-Za-z0-9_\-.%]{1,80}))?)?$")

def parse_activity(iri: str) -> tuple[str, str, str | None] | None:
    """→ (course_ref, lesson_ref, item_ref | None). Paket: har dars — alohida paket (dars faoliyati «…/paket/<kurs>/<no|kod>»);
    kurs muharriri: kurs — bitta paket, darslar — «…/kurs/<id>/lesson/<uid>», kurs darajasi — lesson_ref ''."""
    s = str(iri or "")
    m = _PK_RX.match(s)
    if m:
        code = m[2] if not m[2].isdigit() else f"L{int(m[2])}"
        return f"dl:{int(m[1])}", code, m[3]
    m = _KU_RX.match(s)
    if m: return f"ku:{int(m[1])}", m[2] or "", m[3]
    return None

def lesson_activity(course_ref: str, lesson_ref: str) -> str:
    kind, _, cid = course_ref.partition(":")
    if kind == "dl":
        code = lesson_ref
        return f"{PAKET_BASE}/{int(cid)}/{code[1:]}" if re.fullmatch(r"L\d+", code) else f"{PAKET_BASE}/{int(cid)}/{code}"
    return f"{KURS_BASE}/{int(cid)}" + (f"/lesson/{lesson_ref}" if lesson_ref else "")

def in_scope(auth: dict, activity: str) -> bool:
    if auth["kind"] == "partner": return parse_activity(activity) is not None
    p = parse_activity(activity)
    if not p or p[0] != auth["course_ref"]: return False
    if auth["course_ref"].startswith("dl:"): return p[1] == auth["lesson_ref"]
    return not auth["lesson_ref"] or p[1] in ("", auth["lesson_ref"])      # kurs: kurs darajasi + o'sha dars


# =============================================================================================
# Statement tekshiruvi
# =============================================================================================
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_IRI = re.compile(r"^(?:https?://[^\s<>\"]{1,1900}|urn:[A-Za-z0-9][A-Za-z0-9\-]{0,31}:[^\s<>\"]{1,1900})$")
_DUR = re.compile(r"^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$")

def _is_uuid(v) -> bool: return isinstance(v, str) and bool(_UUID.match(v.lower()))
def _is_iri(v) -> bool: return isinstance(v, str) and bool(_IRI.match(v))

def parse_duration(v) -> float | None:
    m = _DUR.match(str(v or "")) if v else None
    if not m or v in ("P", "PT"): return None
    d, h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s

def _lmap(v, where: str):
    if v is None: return
    if not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(x, str) and len(k) <= 35 for k, x in v.items()):
        raise XErr(400, f"{where}: til xaritasi noto'g'ri")

def _agent(a, where: str) -> dict:
    if not isinstance(a, dict): raise XErr(400, f"{where}: Agent obyekti kerak")
    if a.get("objectType", "Agent") != "Agent": raise XErr(400, f"{where}: faqat Agent qo'llab-quvvatlanadi (Group yo'q)")
    ifis = [k for k in ("mbox", "mbox_sha1sum", "openid", "account") if a.get(k) is not None]
    if len(ifis) != 1: raise XErr(400, f"{where}: aniq bitta identifikator (mbox / mbox_sha1sum / openid / account) kerak")
    if "account" in ifis:
        ac = a["account"]
        if not isinstance(ac, dict) or not isinstance(ac.get("homePage"), str) or not isinstance(ac.get("name"), str) or not ac["name"] or set(ac) - {"homePage", "name"}:
            raise XErr(400, f"{where}: account {{homePage, name}} noto'g'ri")
    if "mbox" in ifis and not (isinstance(a["mbox"], str) and a["mbox"].startswith("mailto:")): raise XErr(400, f"{where}: mbox «mailto:» bilan boshlanadi")
    if set(a) - {"objectType", "name", "mbox", "mbox_sha1sum", "openid", "account"}: raise XErr(400, f"{where}: noma'lum maydon")
    return a

def _agent_key(a: dict) -> str:
    for k in ("account", "mbox", "mbox_sha1sum", "openid"):
        if a.get(k) is not None: return json.dumps({k: a[k]}, sort_keys=True, separators=(",", ":"))
    return ""

def _parse_ts(v) -> dt.datetime:
    s = str(v or "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", s): raise XErr(400, "timestamp ISO 8601 formatida bo'lishi kerak")
    try: t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError: raise XErr(400, "timestamp noto'g'ri")
    if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(clock.tz()).replace(tzinfo=None, microsecond=0)

def validate(s, auth: dict) -> dict:
    """xAPI 1.0.3 kichik to'plami: Agent actor (bitta IFI), verb (IRI), obyekt — Activity yoki StatementRef (faqat «voided» bilan),
    result (score, success, completion, response, duration, extensions), context (registration — UUID), timestamp. Noma'lum maydon — 400."""
    if not isinstance(s, dict): raise XErr(400, "Statement JSON obyekt bo'lishi kerak")
    if set(s) - ALLOWED_KEYS: raise XErr(400, f"Noma'lum maydon: {', '.join(sorted(set(s) - ALLOWED_KEYS))[:80]}")
    if s.get("attachments"): raise XErr(400, "Ilovalar (attachments) qabul qilinmaydi")
    out = {k: v for k, v in s.items() if k not in ("stored", "authority", "version", "attachments")}
    if "id" in s:
        if not _is_uuid(s["id"]): raise XErr(400, "Statement id UUID bo'lishi kerak")
        out["id"] = s["id"].lower()
    else: out["id"] = str(uuid.uuid4())
    actor = _agent(s.get("actor"), "actor")
    v = s.get("verb")
    if not isinstance(v, dict) or not _is_iri(v.get("id")) or set(v) - {"id", "display"}: raise XErr(400, "verb.id IRI bo'lishi kerak")
    _lmap(v.get("display"), "verb.display")
    o = s.get("object")
    if not isinstance(o, dict): raise XErr(400, "object kerak")
    ot = o.get("objectType", "Activity")
    voided = v["id"] == VERB + "voided"
    if voided:
        if ot != "StatementRef" or not _is_uuid(o.get("id")): raise XErr(400, "voided: object StatementRef (UUID) bo'lishi kerak")
    else:
        if ot != "Activity": raise XErr(400, "object faqat Activity (Agent / SubStatement / StatementRef qo'llab-quvvatlanmaydi)")
        if not _is_iri(o.get("id")): raise XErr(400, "object.id IRI bo'lishi kerak")
        if set(o) - {"objectType", "id", "definition"}: raise XErr(400, "object: noma'lum maydon")
        d = o.get("definition")
        if d is not None:
            if not isinstance(d, dict): raise XErr(400, "object.definition noto'g'ri")
            _lmap(d.get("name"), "definition.name"); _lmap(d.get("description"), "definition.description")
            if d.get("type") is not None and not _is_iri(d["type"]): raise XErr(400, "definition.type IRI bo'lishi kerak")
    r = s.get("result")
    if r is not None:
        if not isinstance(r, dict) or set(r) - {"score", "success", "completion", "response", "duration", "extensions"}: raise XErr(400, "result noto'g'ri")
        sc = r.get("score")
        if sc is not None:
            if not isinstance(sc, dict) or set(sc) - {"scaled", "raw", "min", "max"} or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in sc.values()):
                raise XErr(400, "result.score noto'g'ri")
            if "scaled" in sc and not -1 <= sc["scaled"] <= 1: raise XErr(400, "score.scaled −1..1 oralig'ida bo'lishi kerak")
            if "min" in sc and "max" in sc and sc["min"] > sc["max"]: raise XErr(400, "score.min > score.max")
            if "raw" in sc and (("min" in sc and sc["raw"] < sc["min"]) or ("max" in sc and sc["raw"] > sc["max"])): raise XErr(400, "score.raw min..max oralig'ida emas")
        for k in ("success", "completion"):
            if k in r and not isinstance(r[k], bool): raise XErr(400, f"result.{k} mantiqiy (true/false) bo'lishi kerak")
        if "response" in r and (not isinstance(r["response"], str) or len(r["response"]) > 4000): raise XErr(400, "result.response matn (≤ 4000) bo'lishi kerak")
        if "duration" in r and parse_duration(r["duration"]) is None: raise XErr(400, "result.duration ISO 8601 (PT#H#M#S) bo'lishi kerak")
        if "extensions" in r and not isinstance(r["extensions"], dict): raise XErr(400, "result.extensions obyekt bo'lishi kerak")
    c = s.get("context")
    if c is not None:
        if not isinstance(c, dict) or set(c) - {"registration", "instructor", "team", "contextActivities", "revision", "platform", "language", "statement", "extensions"}:
            raise XErr(400, "context noto'g'ri")
        if "registration" in c and not _is_uuid(c["registration"]): raise XErr(400, "context.registration UUID bo'lishi kerak")
        if "contextActivities" in c and not isinstance(c["contextActivities"], dict): raise XErr(400, "contextActivities noto'g'ri")
    ts = _parse_ts(s["timestamp"]) if s.get("timestamp") is not None else None
    # --- ko'lam: kim va qayerga yozmoqda ---
    if auth["kind"] == "launch":
        if actor.get("account") != {"homePage": HOME, "name": auth["learner"]}:
            raise XErr(403, "actor token egasiga mos emas (boshqa talaba nomidan yozib bo'lmaydi)")
        reg = (c or {}).get("registration")
        if reg and auth.get("registration") and reg.lower() != auth["registration"]: raise XErr(403, "context.registration token bilan mos emas")
        if not voided and not in_scope(auth, o["id"]): raise XErr(403, "Faoliyat token ko'lamidan tashqarida (boshqa kurs yoki dars)")
        sid = auth["student_id"]; lid = auth["learner"]
    else:
        ac = actor.get("account") or {}
        if ac.get("homePage") != partner_home(): raise XErr(400, f"Hamkor statementi: actor.account.homePage «{partner_home()}» bo'lishi kerak")
        st = db.one(_con, "SELECT id FROM students WHERE hemis_id=?", (str(ac.get("name") or "")[:40],))
        if not st: raise XErr(400, "Hamkor statementi: talaba (HEMIS ID) topilmadi")
        sid = st["id"]; lid = learner_id(sid)
        if not voided and not in_scope(auth, o["id"]): raise XErr(403, "Faoliyat ISFT paketlari nomlar fazosida emas")
    out["actor"] = actor
    return {"stmt": out, "student_id": sid, "learner": lid, "ts": ts, "voided": voided}

def partner_home() -> str: return os.getenv("ISFT_CORE_LRS_PARTNER_HOME", "https://my.isft.uz").strip()

def _digest(stmt: dict) -> str:
    """Idempotentlik: bir xil id bilan qayta kelgan statement mazmuni solishtiriladi (stored/authority/version hisobga olinmaydi)."""
    body = {k: v for k, v in stmt.items() if k not in ("stored", "authority", "version")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _score_pct(sc: dict | None) -> float | None:
    if not isinstance(sc, dict): return None
    if "scaled" in sc: return round(float(sc["scaled"]) * 100, 2)
    if "raw" in sc:
        lo, hi = sc.get("min", 0), sc.get("max", 100)
        return round(100.0 * (sc["raw"] - lo) / (hi - lo), 2) if hi > lo else None
    return None

def _verb_short(vid: str) -> str: return vid.rstrip("/").rsplit("/", 1)[-1][:40]


# =============================================================================================
# Saqlash, bekor qilish, progress
# =============================================================================================
def store(items: list[dict], auth: dict, now: dt.datetime | None = None, src: str = "lrs", con=None) -> list[str]:
    """Tekshirilgan statementlar → baza (bitta tranzaksiya, hammasi yoki hech biri). Bir xil id + bir xil mazmun — o'tkaziladi (idempotent),
    bir xil id + boshqa mazmun — 409. «voided» — nishon statement bekor qilinadi (o'sha talabaniki bo'lishi shart)."""
    con = con or _con
    now = now or _now()
    stored = _iso(now)
    ids, seen, touched = [], {}, set()
    with _lock:
        try:
            for it in items:
                s = it["stmt"]; sid = s["id"]
                dg = _digest(s)
                if sid in seen:
                    if seen[sid] != dg: raise XErr(400, f"Bir so'rovda bir xil id ikki xil statement bilan: {sid}")
                    ids.append(sid); continue
                old = db.one(con, "SELECT digest FROM lrs_statements WHERE id=?", (sid,))
                if old:
                    if old["digest"] != dg: raise XErr(409, f"Statement {sid} allaqachon boshqa mazmun bilan saqlangan")
                    seen[sid] = dg; ids.append(sid); continue
                seen[sid] = dg
                ts = it["ts"] or now
                if ts > now + dt.timedelta(minutes=10): ts = now          # mijoz soati oldinda — saqlash vaqti olinadi
                v = s["verb"]["id"]; o = s["object"]; r = s.get("result") or {}; c = s.get("context") or {}
                if it["voided"]:
                    tgt = db.one(con, "SELECT id, student_id, verb, course_ref, lesson_ref FROM lrs_statements WHERE id=?", (o["id"].lower(),))
                    if not tgt: raise XErr(400, "Bekor qilinadigan statement topilmadi")
                    if tgt["verb"] == "voided": raise XErr(400, "«voided» statementni bekor qilib bo'lmaydi")
                    if tgt["student_id"] != it["student_id"]: raise XErr(403, "Boshqa talabaning statementini bekor qilib bo'lmaydi")
                    con.execute("UPDATE lrs_statements SET voided=1 WHERE id=?", (tgt["id"],))
                    touched.add((tgt["student_id"], tgt["course_ref"], tgt["lesson_ref"]))
                    p = (None, None, None)
                else:
                    p = parse_activity(o["id"]) or (None, None, None)
                ext = r.get("extensions") or {}
                prog = ext.get(PROGRESS_EXT)
                prog = float(prog) if isinstance(prog, (int, float)) and not isinstance(prog, bool) and 0 <= prog <= 100 else None
                full = dict(s); full.update(stored=stored, version=XAPI_VERSION, timestamp=s.get("timestamp") or _iso(ts),
                                            authority={"objectType": "Agent", "account": {"homePage": HOME, "name": "lrs:" + auth["jti"]}})
                raw = json.dumps(full, ensure_ascii=False, separators=(",", ":"))
                if len(raw.encode()) > MAX_STMT: raise XErr(413, f"Statement hajmi {MAX_STMT // 1024} KB dan katta")
                con.execute("""INSERT INTO lrs_statements(id,stored,ts,student_id,learner,verb,verb_id,activity,course_ref,lesson_ref,item_ref,registration,
                               success,completion,score,response,duration,progress,voided,voids,digest,token,src,raw) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)""",
                            (sid, stored, _iso(ts), it["student_id"], it["learner"], _verb_short(v), v, o.get("id") if not it["voided"] else None, p[0], p[1], p[2],
                             (c.get("registration") or "").lower() or None,
                             None if "success" not in r else int(r["success"]), None if "completion" not in r else int(r["completion"]),
                             _score_pct(r.get("score")), (r.get("response") or None) if isinstance(r.get("response"), str) else None,
                             parse_duration(r.get("duration")) if r.get("duration") else None, prog,
                             o["id"].lower() if it["voided"] else None, dg, auth["jti"], src, raw))
                if p[0]:
                    touched.add((it["student_id"], p[0], p[1]))
                    _upsert_activity(con, o, p, stored)
                ids.append(sid)
            for k in touched: recompute(*k, con=con)
            if auth["kind"] == "launch":
                con.execute("UPDATE lrs_tokens SET n_stmt=n_stmt+?, last_used=? WHERE jti=?", (len(items), stored, auth["jti"]))
            con.commit()
        except Exception:
            con.rollback(); raise
    return ids

def _upsert_activity(con, o: dict, p: tuple, ts: str):
    d = o.get("definition")
    if not isinstance(d, dict): return
    def first(m):
        if not isinstance(m, dict) or not m: return None
        return m.get("uz") or m.get("en-US") or next(iter(m.values()))
    ch = d.get("choices") or d.get("source")
    choices = json.dumps([{"id": str(x.get("id")), "text": first(x.get("description")) or ""} for x in ch if isinstance(x, dict)], ensure_ascii=False)[:8000] \
        if isinstance(ch, list) else None
    corr = d.get("correctResponsesPattern")
    con.execute("""INSERT INTO lrs_activities(id,course_ref,lesson_ref,item_ref,type,name,description,itype,choices,correct,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET type=excluded.type, name=COALESCE(excluded.name,name), description=COALESCE(excluded.description,description),
                   itype=COALESCE(excluded.itype,itype), choices=COALESCE(excluded.choices,choices), correct=COALESCE(excluded.correct,correct), updated=excluded.updated""",
                (o["id"], p[0], p[1], p[2], str(d.get("type") or "")[:200], (first(d.get("name")) or "")[:300] or None,
                 (first(d.get("description")) or "")[:1000] or None, str(d.get("interactionType") or "")[:30] or None, choices,
                 json.dumps(corr, ensure_ascii=False)[:2000] if isinstance(corr, list) else None, ts))

def events_of(rows: list[dict]) -> list[dict]:
    return [{"verb": r["verb"], "ts": r["ts"], "sub": bool(r["item_ref"]), "success": r["success"], "completion": r["completion"], "score": r["score"],
             "duration": r["duration"], "progress": r["progress"], "item": r["item_ref"], "response": r["response"]} for r in rows]

def recompute(student_id: int, course_ref: str, lesson_ref: str, con=None):
    """lrs_progress qatorini statementlardan qayta hisoblash (bekor qilinganlar hisobga olinmaydi)."""
    con = con or _con
    rows = db.rows(con, """SELECT verb, ts, item_ref, success, completion, score, duration, progress, response, src FROM lrs_statements
                           WHERE student_id=? AND course_ref=? AND lesson_ref=? AND voided=0 AND verb!='voided' ORDER BY ts, stored""",
                   (student_id, course_ref, lesson_ref))
    if not rows:
        con.execute("DELETE FROM lrs_progress WHERE student_id=? AND course_ref=? AND lesson_ref=?", (student_id, course_ref, lesson_ref)); return
    s = LA.lesson_summary(events_of(rows))
    src = "demo" if all(r["src"] == "demo" for r in rows) else "lrs"
    con.execute("""INSERT OR REPLACE INTO lrs_progress(student_id,course_ref,lesson_ref,status,pct,score,best,attempts,fails,time_s,first_ts,last_ts,updated,src)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (student_id, course_ref, lesson_ref, s["status"], s["pct"], s["score"], s["best"], s["attempts"],
                                                          s["fails"], s["time_s"], s["first"], s["last"], _iso(_now()), src))


# =============================================================================================
# Cheklovlar (jarayon xotirasida)
# =============================================================================================
class Window:
    MAX_KEYS = 20000
    def __init__(self, limit: int, seconds: int):
        self.limit, self.seconds, self.h, self.lock = limit, seconds, {}, threading.Lock()
    def take(self, key: str, n: int = 1) -> int:
        """n birlik olishga urinish. 0 — mumkin; aks holda necha soniyadan keyin."""
        now = time.time()
        with self.lock:
            q = self.h.get(key)
            if q is None:
                if len(self.h) >= self.MAX_KEYS: self.h.clear()
                q = self.h[key] = collections.deque()
            while q and now - q[0][0] >= self.seconds: q.popleft()
            used = sum(x[1] for x in q)
            if used + n > self.limit: return max(1, int(self.seconds - (now - q[0][0])) + 1) if q else self.seconds
            q.append((now, n)); return 0
    def reset(self): self.h.clear()

LIM_REQ, LIM_STMT, LIM_IP = Window(*RATE_REQ), Window(*RATE_STMT), Window(*RATE_IP)

def _ip(request: Request) -> str:
    try:
        from . import main as M
        return M._ip(request)
    except Exception:
        return request.client.host if request.client else "?"

def _limits(request: Request, auth: dict | None, n_stmt: int = 0):
    w = LIM_IP.take(_ip(request))
    if not w and auth: w = LIM_REQ.take(auth["jti"])
    if not w and auth and n_stmt: w = LIM_STMT.take(auth["jti"], n_stmt)
    if w: raise XErr(429, "So'rovlar juda ko'p — birozdan keyin qayta yuboriladi", {"Retry-After": str(w)})


# =============================================================================================
# HTTP: xAPI
# =============================================================================================
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Experience-API-Version, If-Match, If-None-Match",
        "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS", "Access-Control-Expose-Headers": "X-Experience-API-Version, X-Experience-API-Consistent-Through, Last-Modified",
        "Access-Control-Max-Age": "600", "X-Experience-API-Version": XAPI_VERSION, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}

def _json(data, status: int = 200, extra: dict | None = None) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={**CORS, **(extra or {})})

def _fail(e: XErr) -> JSONResponse:
    return _json({"error": True, "message": e.msg}, e.status, e.headers)

def _version(request: Request):
    v = request.headers.get("x-experience-api-version", "")
    if not re.fullmatch(r"1\.0(\.\d+)?", v.strip()): raise XErr(400, "X-Experience-API-Version: 1.0.x sarlavhasi kerak")

async def _body(request: Request, limit: int) -> bytes:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit: raise XErr(413, f"So'rov hajmi {limit // 1024} KB dan katta")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit: raise XErr(413, f"So'rov hajmi {limit // 1024} KB dan katta")
    return bytes(buf)

def _audit_sys(action: str, ok: bool, detail: str):
    """Rad etilgan LRS so'rovlari audit jurnaliga (foydalanuvchisiz — tizim yozuvi)."""
    try:
        _con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                     (_iso(_now()), None, "LRS", "LRS", "xapi", action, "lrs", int(ok), detail[:300])); _con.commit()
    except Exception:
        pass

@router.options("/xapi/{rest:path}")
def x_options(rest: str):
    return Response(status_code=204, headers=CORS)

@router.get("/xapi/about")
def x_about():
    return _json({"version": [XAPI_VERSION], "extensions": {"https://isft.uz/xapi/ext/lrs": {"name": "ISFT Core LRS", "subset": "statements, voided, activities/state"}}})

async def _post_statements(request: Request, single_id: str | None = None):
    _version(request)
    auth = parse_auth(request.headers.get("authorization"))
    raw = await _body(request, MAX_BODY)
    try: data = json.loads(raw.decode("utf-8") or "null")
    except (ValueError, UnicodeDecodeError): raise XErr(400, "JSON noto'g'ri")
    arr = data if isinstance(data, list) else [data]
    if single_id is not None:
        if isinstance(data, list) or not isinstance(data, dict): raise XErr(400, "PUT — bitta statement")
        if "id" in data and str(data["id"]).lower() != single_id.lower(): raise XErr(400, "statementId va statement.id mos emas")
        data["id"] = single_id.lower(); arr = [data]
    if not arr or len(arr) > MAX_BATCH: raise XErr(400, f"Bir so'rovda 1–{MAX_BATCH} ta statement")
    _limits(request, auth, len(arr))
    items = [validate(s, auth) for s in arr]
    for it in items:
        if len(json.dumps(it["stmt"], ensure_ascii=False).encode()) > MAX_STMT: raise XErr(413, f"Statement hajmi {MAX_STMT // 1024} KB dan katta")
    return store(items, auth)

@router.post("/xapi/statements")
async def x_post(request: Request):
    try:
        ids = await _post_statements(request)
        return _json(ids)
    except XErr as e:
        if e.status in (401, 403, 409): _audit_sys(f"LRS: statement rad etildi ({e.status})", False, e.msg)
        return _fail(e)

@router.put("/xapi/statements")
async def x_put(request: Request, statementId: str = ""):
    try:
        if not _is_uuid(statementId): raise XErr(400, "statementId (UUID) kerak")
        await _post_statements(request, statementId)
        return Response(status_code=204, headers=CORS)
    except XErr as e:
        if e.status in (401, 403, 409): _audit_sys(f"LRS: statement rad etildi ({e.status})", False, e.msg)
        return _fail(e)

def _out(r: dict) -> dict:
    if r.get("raw"):
        try: return json.loads(r["raw"])
        except ValueError: pass
    # demo qatorlar — ixcham ustunlardan tiklanadi
    s = {"id": r["id"], "actor": actor_for(r["learner"]), "verb": {"id": r["verb_id"], "display": {"en-US": r["verb"]}},
         "object": {"objectType": "Activity", "id": r["activity"]}, "timestamp": r["ts"], "stored": r["stored"], "version": XAPI_VERSION}
    res = {}
    if r["success"] is not None: res["success"] = bool(r["success"])
    if r["completion"] is not None: res["completion"] = bool(r["completion"])
    if r["score"] is not None: res["score"] = {"scaled": round(r["score"] / 100, 4), "raw": r["score"], "min": 0, "max": 100}
    if r["response"]: res["response"] = r["response"]
    if r["duration"]: res["duration"] = f"PT{round(r['duration'], 2)}S"
    if res: s["result"] = res
    if r["registration"]: s["context"] = {"registration": r["registration"]}
    return s

@router.get("/xapi/statements")
def x_get(request: Request, statementId: str = "", voidedStatementId: str = "", agent: str = "", verb: str = "", activity: str = "",
          registration: str = "", since: str = "", until: str = "", limit: int = 0, ascending: bool = False):
    """Token egasi faqat o'z statementlarini (o'z kursi/darsi doirasida) o'qiydi; hamkor kirishi — o'qiy olmaydi."""
    try:
        _version(request)
        auth = parse_auth(request.headers.get("authorization"))
        _limits(request, auth)
        if auth["kind"] != "launch": raise XErr(403, "Hamkor kirishi faqat yozish uchun")
        if statementId or voidedStatementId:
            sid = (statementId or voidedStatementId).lower()
            r = db.one(_con, "SELECT * FROM lrs_statements WHERE id=? AND learner=?", (sid, auth["learner"]))
            if not r or bool(r["voided"]) != bool(voidedStatementId): return _fail(XErr(404, "Statement topilmadi"))
            if r["activity"] and not in_scope(auth, r["activity"]): return _fail(XErr(404, "Statement topilmadi"))
            return _json(_out(r))
        w, a = ["learner=?", "voided=0"], [auth["learner"]]
        if agent:
            try: ag = json.loads(agent)
            except ValueError: raise XErr(400, "agent JSON noto'g'ri")
            if not isinstance(ag, dict) or ag.get("account") != {"homePage": HOME, "name": auth["learner"]}: raise XErr(403, "Faqat o'z statementlaringiz")
        if verb: w.append("verb_id=?"); a.append(verb)
        if activity:
            if not in_scope(auth, activity): raise XErr(403, "Faoliyat token ko'lamidan tashqarida")
            w.append("activity=?"); a.append(activity)
        else:
            w.append("course_ref=?"); a.append(auth["course_ref"])
            if auth["course_ref"].startswith("dl:"): w.append("lesson_ref=?"); a.append(auth["lesson_ref"])
        if registration: w.append("registration=?"); a.append(registration.lower())
        if since: w.append("stored>?"); a.append(_iso(_parse_ts(since)))
        if until: w.append("stored<=?"); a.append(_iso(_parse_ts(until)))
        lim = max(1, min(500, limit or 100))
        rows = db.rows(_con, f"SELECT * FROM lrs_statements WHERE {' AND '.join(w)} ORDER BY stored {'ASC' if ascending else 'DESC'}, id LIMIT ?", (*a, lim))
        return _json({"statements": [_out(r) for r in rows], "more": ""})
    except XErr as e:
        return _fail(e)

# --- State API (resume) ---
def _state_key(request: Request, auth: dict, activityId: str, agent: str, stateId: str, registration: str) -> tuple:
    if not _is_iri(activityId): raise XErr(400, "activityId IRI bo'lishi kerak")
    if not stateId or len(stateId) > 200: raise XErr(400, "stateId kerak")
    if registration and not _is_uuid(registration): raise XErr(400, "registration UUID bo'lishi kerak")
    try: ag = json.loads(agent or "")
    except ValueError: raise XErr(400, "agent JSON noto'g'ri")
    if auth["kind"] != "launch": raise XErr(403, "State API — faqat launch tokeni bilan")
    _agent(ag, "agent")
    if ag.get("account") != {"homePage": HOME, "name": auth["learner"]}: raise XErr(403, "agent token egasiga mos emas")
    if not in_scope(auth, activityId): raise XErr(403, "Faoliyat token ko'lamidan tashqarida")
    return activityId, auth["learner"], stateId, (registration or "").lower()

@router.api_route("/xapi/activities/state", methods=["GET", "PUT", "POST", "DELETE"])
async def x_state(request: Request, activityId: str = "", agent: str = "", stateId: str = "", registration: str = ""):
    try:
        _version(request)
        auth = parse_auth(request.headers.get("authorization"))
        _limits(request, auth)
        if not stateId and request.method in ("GET", "DELETE"):
            raise XErr(400, "stateId kerak (hujjatlar ro'yxati qo'llab-quvvatlanmaydi)")
        key = _state_key(request, auth, activityId, agent, stateId, registration)
        if request.method == "GET":
            r = db.one(_con, "SELECT body, ctype, updated FROM lrs_state WHERE activity=? AND learner=? AND state_id=? AND registration=?", key)
            if not r: return Response(status_code=404, headers=CORS)
            return Response(r["body"], media_type=r["ctype"] or "application/octet-stream", headers={**CORS, "Last-Modified": r["updated"]})
        if request.method == "DELETE":
            with _lock:
                _con.execute("DELETE FROM lrs_state WHERE activity=? AND learner=? AND state_id=? AND registration=?", key); _con.commit()
            return Response(status_code=204, headers=CORS)
        body = await _body(request, MAX_STATE)
        ct = (request.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()[:100]
        try: txt = body.decode("utf-8")
        except UnicodeDecodeError: raise XErr(400, "Holat hujjati UTF-8 matn bo'lishi kerak")
        with _lock:
            if request.method == "POST" and ct == "application/json":   # POST — JSON hujjatlarni birlashtirish (xAPI)
                old = db.one(_con, "SELECT body FROM lrs_state WHERE activity=? AND learner=? AND state_id=? AND registration=?", key)
                if old:
                    try:
                        a, b = json.loads(old["body"]), json.loads(txt)
                        if isinstance(a, dict) and isinstance(b, dict): txt = json.dumps({**a, **b}, ensure_ascii=False)
                    except ValueError: raise XErr(400, "JSON hujjatlarni birlashtirib bo'lmadi")
            _con.execute("""INSERT OR REPLACE INTO lrs_state(activity,learner,state_id,registration,student_id,body,ctype,updated) VALUES(?,?,?,?,?,?,?,?)""",
                         (*key, auth["student_id"], txt, ct, _iso(_now())))
            _con.commit()
        return Response(status_code=204, headers=CORS)
    except XErr as e:
        return _fail(e)


# =============================================================================================
# Ishga tushirish (launch): havola → token → paket fayllari
# =============================================================================================
LAUNCH_TTL_H = AUTH_HOURS

def code_to_key(code: str) -> int | None:
    """Paket dars kodi («L3», «A12», «Lab2») → ichki kalit (app/paket.py lesson_key)."""
    from . import paket as PK
    m = re.fullmatch(r"(Lab|MT|L|A|S)(\d{1,3})", code or "")
    if not m: return None
    for kind, (pre, base, _, _) in PK.KINDS.items():
        if pre == m[1]: return base + int(m[2])
    return None

def package_for(course_ref: str, lesson_ref: str) -> dict | None:
    """Ishga tushiriladigan eksport: paket — o'sha dars uchun eng so'nggi (tasdiqlangani ustun) paket; kurs muharriri — oxirgi eksport (xAPI ustun).
    → {"file": Path, "activity": IRI, "title"} yoki None. Oddiy HTML (LMS'siz) eksport ishga tushirilmaydi — u natija yubormaydi."""
    kind, _, cid = course_ref.partition(":")
    if not cid.isdigit(): return None
    if kind == "dl":
        from . import paket as PK
        key = code_to_key(lesson_ref)
        if key is None: return None
        r = db.one(_con, """SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? AND mode!='none' AND file IS NOT NULL AND file!=''
                            ORDER BY (status='tasdiqlandi') DESC, version DESC, id DESC LIMIT 1""", (int(cid), key))
        f = PK.store() / r["file"] if r else None
        return {"file": f, "activity": lesson_activity(course_ref, lesson_ref), "id": r["id"]} if f and f.is_file() else None
    if kind == "ku":
        from . import kurs as KU
        r = db.one(_con, """SELECT e.* FROM ku_exports e JOIN ku_courses k ON k.id=e.course_id AND k.deleted=0 WHERE e.course_id=? AND e.mode!='none'
                            AND e.file!='' ORDER BY (e.mode='xapi') DESC, e.id DESC LIMIT 1""", (int(cid),))
        f = KU.store() / r["file"] if r else None
        return {"file": f, "activity": lesson_activity(course_ref, ""), "id": r["id"]} if f and f.is_file() else None
    return None

def public_base(request: Request) -> str:
    env = os.getenv("ISFT_CORE_PUBLIC_URL", "").strip()
    return (env.rstrip("/") if env else str(request.base_url).rstrip("/")) + "/"

def launch_query(request: Request, sid: int, course_ref: str, lesson_ref: str, activity: str, created_by: int | None = None) -> str:
    tok = make_auth(sid, course_ref, lesson_ref, LAUNCH_TTL_H, created_by)
    return urlencode({"endpoint": public_base(request) + "xapi/", "auth": tok["auth"], "actor": json.dumps(actor_for(tok["learner"]), separators=(",", ":")),
                      "registration": tok["registration"], "activity_id": activity})

def launch_csp(request: Request) -> str:
    base = public_base(request)
    origin = re.match(r"^(https?://[^/]+)", base)[1]
    anc = " ".join(x for x in os.getenv("ISFT_CORE_LRS_FRAME_ANCESTORS", "https://my.isft.uz").split() if re.fullmatch(r"https://[A-Za-z0-9.\-:]+", x))
    return ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://i.ytimg.com; font-src 'self' data:; "
            f"media-src 'self'; connect-src {origin}/xapi/; frame-src https://www.youtube-nocookie.com; object-src 'none'; base-uri 'none'; "
            f"form-action 'none'; frame-ancestors 'self' {anc}".strip())

@router.get("/xapi/l/{code}")
def x_launch(code: str, request: Request):
    """Talaba havolasi: yangi qisqa muddatli token bilan paketni ochadi (har ochilishda yangi token; registration — barqaror)."""
    w = LIM_IP.take(_ip(request))
    if w: raise HTTPException(429, "So'rovlar juda ko'p")
    L = parse_link(code)
    st = db.one(_con, "SELECT status FROM students WHERE id=?", (L["student_id"],))
    if not st: raise HTTPException(403, "Havola yaroqsiz")
    pk = package_for(L["course_ref"], L["lesson_ref"])
    if not pk: raise HTTPException(404, "Bu dars uchun paket hali eksport qilinmagan — Masofaviy ta'lim bo'limiga murojaat qiling")
    q = launch_query(request, L["student_id"], L["course_ref"], L["lesson_ref"], pk["activity"])
    return RedirectResponse(f"/xapi/pkg/{code}/index.html?{q}", 302, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

@router.get("/xapi/pkg/{code}/{path:path}")
def x_pkg(code: str, path: str, request: Request):
    from . import paket as PK
    L = parse_link(code)
    pk = package_for(L["course_ref"], L["lesson_ref"])
    if not pk: raise HTTPException(404, "Paket topilmadi")
    path = (path or "index.html").strip() or "index.html"
    if PK._bad_path(path) or "\x00" in path or "%" in path: raise HTTPException(400, "Yo'l noto'g'ri")
    f = pk["file"]; ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    with zipfile.ZipFile(f) as z:
        try: zi = z.getinfo(path)
        except KeyError: raise HTTPException(404, "Paket ichida bunday fayl yo'q")
        span = PK._stored_span(f, zi) if ext in PK._MEDIA_EXT or zi.file_size > PK.STREAM_FROM else None
        data = None if span else z.read(zi)
    hd = {"Content-Security-Policy": launch_csp(request), "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
          "Cache-Control": "no-store" if path == "index.html" else "private, max-age=300"}
    ct = PK._CT.get(ext, "application/octet-stream")
    if span is None: return Response(data, media_type=ct, headers=hd)
    return PK.range_response(f, ct, request.headers.get("range"), hd, off=span[0], size=span[1])


# =============================================================================================
# Xodimlar uchun: havola yaratish (bo'lim)
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def _guard(c: Ctx, action: str, roles=DEPT, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"LRS: {action}", "lrs", ok, detail)
    if not ok: raise AccessDenied(f"⛔ LRS: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def course_exists(course_ref: str) -> bool:
    kind, _, cid = (course_ref or "").partition(":")
    if not cid.isdigit(): return False
    if kind == "dl": return bool(db.one(_con, "SELECT 1 x FROM dl_courses WHERE id=?", (int(cid),)))
    if kind == "ku": return bool(db.one(_con, "SELECT 1 x FROM ku_courses WHERE id=? AND deleted=0", (int(cid),)))
    return False

class LinkIn(BaseModel):
    student_id: int
    course_ref: str = Field(..., max_length=20)
    lesson_ref: str = Field("", max_length=30)

@router.post("/api/lrs/launch-link")
def api_link(body: LinkIn, request: Request):
    c = C(request)
    _guard(c, "ishga tushirish havolasi", detail=f"talaba #{body.student_id} · {body.course_ref} {body.lesson_ref}")
    if not course_exists(body.course_ref): raise HTTPException(404, "Kurs topilmadi")
    if body.course_ref.startswith("dl:") and code_to_key(body.lesson_ref) is None: raise HTTPException(400, "Paket kursi uchun dars kodi (L3, A1…) kerak")
    if body.course_ref.startswith("ku:") and body.lesson_ref: raise HTTPException(400, "Kurs muharriri paketi butun kurs bo'yicha ochiladi (dars ko'rsatilmaydi)")
    if not db.one(_con, f"SELECT 1 x FROM students s WHERE s.id=? AND {c.student_scope('s')}", (body.student_id,)): raise HTTPException(404, "Talaba topilmadi")
    code = make_link(body.student_id, body.course_ref, body.lesson_ref)
    pk = package_for(body.course_ref, body.lesson_ref)
    return {"url": f"/xapi/l/{code}", "absolute": public_base(request) + f"xapi/l/{code}", "package": bool(pk),
            "note": None if pk else "Paket hali eksport qilinmagan — havola eksportdan keyin ishlaydi"}


# =============================================================================================
# Demo (SUN'IY) statementlar
# =============================================================================================
DEMO_COURSE = ("Iqtisodiyot nazariyasi", "Iqtisodiyot", 1)       # NEXTID'dagi kuzatuv: 45 dars (L1–L15 ma'ruza, A1–A30 amaliy)

def _demo_lessons(n_l: int, n_a: int) -> list[dict]:
    """Haftasiga 1 ma'ruza + 2 amaliy (taqvim tartibida)."""
    out = []
    for w in range(1, max(n_l, (n_a + 1) // 2) + 1):
        if w <= n_l: out.append({"ref": f"L{w}", "title": f"{w}-mavzu (ma'ruza)"})
        for a in (2 * w - 1, 2 * w):
            if a <= n_a: out.append({"ref": f"A{a}", "title": f"{a}-amaliy mashg'ulot"})
    return out

def _stmt_id(R: random.Random) -> str: return str(uuid.UUID(int=R.getrandbits(128), version=4))

def seed(con, force: bool = False) -> dict:
    """Namuna: bir nechta masofaviy kurs bo'yicha SUN'IY statementlar (bir marta; lrs_meta.seed_v1). Haqiqiy talaba natijasi emas."""
    if not force and db.one(con, "SELECT 1 x FROM lrs_meta WHERE k='seed_v1'"): return {}
    _key(con)
    if force:
        con.execute("DELETE FROM lrs_activities WHERE id IN (SELECT DISTINCT activity FROM lrs_statements WHERE src='demo' AND verb='answered')")
        con.execute("DELETE FROM lrs_statements WHERE src='demo'"); con.execute("DELETE FROM lrs_progress WHERE src='demo'")
        con.execute("DELETE FROM lrs_plan WHERE src='demo'")
    from . import academic_rules as AR
    R = random.Random(20261114)
    today, now = clock.today(), _now()
    start = dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0])
    weeks = policy(con)["weeks"]
    courses = []
    main = db.one(con, "SELECT * FROM dl_courses WHERE subject=? AND direction=? AND course=?", DEMO_COURSE)
    if main: courses.append((main, _demo_lessons(15, 30)))
    tu = db.one(con, "SELECT teacher_id FROM users WHERE role='oqituvchi' AND COALESCE(active,1)=1 AND teacher_id IS NOT NULL ORDER BY id LIMIT 1")
    if tu:
        for r in db.rows(con, "SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 2", (tu["teacher_id"],)):
            if not main or r["id"] != main["id"]: courses.append((r, _demo_lessons(int(r["topics"] or 15), 0)))
    other = db.one(con, "SELECT * FROM dl_courses WHERE subject='Iqtisodiyot nazariyasi' AND id NOT IN (%s) ORDER BY id LIMIT 1"
                   % ",".join(str(c[0]["id"]) for c in courses) if courses else "SELECT * FROM dl_courses ORDER BY id LIMIT 1")
    if other: courses.append((other, _demo_lessons(15, 15)))
    rows, n_st = [], 0
    acts = {}
    for co, lessons in courses:
        cref = f"dl:{co['id']}"
        con.execute("INSERT OR REPLACE INTO lrs_plan(course_ref,lessons,weeks,start,src,updated) VALUES(?,?,?,?,?,?)",
                    (cref, json.dumps(lessons, ensure_ascii=False), weeks, start.isoformat(), "demo", _iso(now)))
        studs = db.rows(con, """SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol'
                                AND g.form='masofaviy' AND g.direction=? AND g.course=? ORDER BY s.id""", (co["direction"], co["course"]))
        released = LA.released(len(lessons), start, today, weeks)
        # har dars testida 4 ta savol; 1 tasi ataylab qiyin (ko'pchilik bir xil noto'g'ri variantni tanlaydi), 1 tasi — juda oson
        qdef = {}
        for li, L in enumerate(lessons):
            qs = []
            for k in range(1, 5):
                hard = (li % 5 == 2 and k == 3)
                qs.append({"id": f"tb{co['id']}{li:02d}{k}", "k": k, "p": 0.28 if hard else 0.96 if k == 1 else R.uniform(0.55, 0.85), "trap": "b" if hard else None})
            qdef[L["ref"]] = qs
        for s in studs:
            rs = random.Random(s["id"] * 31 + co["id"])
            lid = learner_id(s["id"], con)
            reg = registration_for(lid, cref)
            x = rs.random()
            story = co is courses[0][0] and s is studs[0]
            if story: x = 0.8                                                            # hikoya talabasi — «sust»
            # profillar: a'lochi (o'z vaqtida), o'rtacha (biroz ortda), sust (ancha ortda), to'xtagan, umuman boshlamagan
            prof = "alo" if x < 0.45 else "orta" if x < 0.79 else "sust" if x < 0.9 else "toxtagan" if x < 0.97 else "yoq"
            ability = {"alo": 0.9, "orta": 0.72, "sust": 0.55, "toxtagan": 0.6, "yoq": 0.5}[prof] + rs.uniform(-0.08, 0.08)
            if prof == "yoq": continue
            share = {"alo": rs.uniform(0.96, 1.0), "orta": rs.uniform(0.86, 0.98), "sust": rs.uniform(0.35, 0.6), "toxtagan": rs.uniform(0.15, 0.3)}[prof]
            n_done = min(released, int(round(released * share)))
            if story: n_done = min(released, 6)                                          # hikoya: 6/45 — qolgani 0 %
            stop_days = rs.randint(9, 30) if prof == "toxtagan" else rs.randint(0, 5) if prof != "sust" else rs.randint(3, 12)
            last_day = today - dt.timedelta(days=stop_days)
            first_day = start + dt.timedelta(days=rs.randint(0, 6))
            span = max(1, (last_day - first_day).days)
            for li in range(n_done):
                L = lessons[li]
                day = first_day + dt.timedelta(days=int(span * (li + 1) / max(1, n_done)))
                t0 = dt.datetime.combine(day, dt.time(rs.randint(8, 22), rs.randint(0, 59)))
                act = lesson_activity(cref, L["ref"])
                dur = rs.randint(12, 55) * 60
                rows.append((_stmt_id(R), t0, s["id"], lid, "initialized", act, cref, L["ref"], None, reg, None, None, None, None, None, None))
                attempts, passed = 0, False
                while not passed and attempts < 6:
                    attempts += 1
                    good = 0
                    for q in qdef[L["ref"]]:
                        # qobiliyat ta'siri kuchli (savol kuchli va kuchsiz talabani farqlasin); qiyin savolda ko'pchilik bir xil xato variantni tanlaydi
                        ok = rs.random() < min(0.98, max(0.03, q["p"] + 1.4 * (ability - 0.72) + 0.12 * (attempts - 1)))
                        good += ok
                        resp = "a" if ok else (q["trap"] if q["trap"] and rs.random() < 0.8 else rs.choice(["b", "c", "d"]))
                        item = f"block/b9/q/{q['id']}"
                        t = t0 + dt.timedelta(minutes=10 + 3 * attempts + q["k"])
                        rows.append((_stmt_id(R), t, s["id"], lid, "answered", f"{act}/{item}", cref, L["ref"], item, reg, int(ok), None, None, resp, None, None))
                        acts[f"{act}/{item}"] = (cref, L["ref"], item, q)
                    pct = round(100 * good / 4)
                    passed = pct >= 60
                    t = t0 + dt.timedelta(minutes=15 + 3 * attempts)
                    rows.append((_stmt_id(R), t, s["id"], lid, "passed" if passed else "failed", f"{act}/block/b9", cref, L["ref"], "block/b9", reg,
                                 int(passed), 1, pct, None, None, None))
                tc = t0 + dt.timedelta(seconds=dur)
                rows.append((_stmt_id(R), tc, s["id"], lid, "completed", act, cref, L["ref"], None, reg, None, 1, None, None, None, 100.0))
                rows.append((_stmt_id(R), tc + dt.timedelta(seconds=5), s["id"], lid, "terminated", act, cref, L["ref"], None, reg, None, 1, None, None, dur, None))
            # boshlangan, lekin tugatilmagan dars (jarayonda / test qayta-qayta yiqilgan)
            if n_done < len(lessons) and prof in ("orta", "sust", "toxtagan") and not story and rs.random() < 0.7:
                L = lessons[n_done]; act = lesson_activity(cref, L["ref"])
                t0 = dt.datetime.combine(last_day, dt.time(rs.randint(8, 22), rs.randint(0, 59)))
                rows.append((_stmt_id(R), t0, s["id"], lid, "initialized", act, cref, L["ref"], None, reg, None, None, None, None, None, None))
                rows.append((_stmt_id(R), t0 + dt.timedelta(minutes=6), s["id"], lid, "progressed", act, cref, L["ref"], None, reg, None, None, None, None, None,
                             float(rs.choice([20, 35, 50, 65]))))
                for k in range(rs.choice([0, 1, 3, 4]) if prof == "sust" else rs.choice([0, 1])):
                    rows.append((_stmt_id(R), t0 + dt.timedelta(minutes=12 + k), s["id"], lid, "failed", f"{act}/block/b9", cref, L["ref"], "block/b9", reg,
                                 0, 1, rs.choice([0, 25, 50]), None, None, None))
                rows.append((_stmt_id(R), t0 + dt.timedelta(minutes=20), s["id"], lid, "suspended", act, cref, L["ref"], None, reg, None, 0, None, None, 1200.0, None))
    stored = _iso(now)
    batch = []
    for (sid_, t, stud, lid, verb, act, cref, lref, item, reg, succ, compl, score, resp, dur, prog) in rows:
        t = min(t, now)
        batch.append((sid_, stored, _iso(t), stud, lid, verb, VERB + verb, act, cref, lref, item, reg, succ, compl, score, resp, dur, prog, "demo"))
    con.executemany("""INSERT OR IGNORE INTO lrs_statements(id,stored,ts,student_id,learner,verb,verb_id,activity,course_ref,lesson_ref,item_ref,registration,
                       success,completion,score,response,duration,progress,src) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", batch)
    for aid, (cref, lref, item, q) in acts.items():
        ch = [{"id": "a", "text": "To'g'ri javob"}, {"id": "b", "text": "Keng tarqalgan xato tushuncha" if q["trap"] else "Noto'g'ri variant B"},
              {"id": "c", "text": "Noto'g'ri variant C"}, {"id": "d", "text": "Noto'g'ri variant D"}]
        con.execute("""INSERT OR IGNORE INTO lrs_activities(id,course_ref,lesson_ref,item_ref,type,name,description,itype,choices,correct,updated)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (aid, cref, lref, item, "http://adlnet.gov/expapi/activities/cmi.interaction",
                                                         f"{lref} — {q['k']}-savol", f"{lref} darsi testi, {q['k']}-savol (namuna)", "choice",
                                                         json.dumps(ch, ensure_ascii=False), json.dumps(["a"]), stored))
    n_st = len(batch)
    keys = {(r[2], r[6], r[7]) for r in rows}
    for k in keys: recompute(*k, con=con)
    con.execute("INSERT OR REPLACE INTO lrs_meta(k,v) VALUES('seed_v1', ?)", (stored,))
    con.execute("INSERT OR REPLACE INTO lrs_meta(k,v) VALUES('anchor', ?)", (LA.monday(today).isoformat(),))
    con.execute("INSERT OR REPLACE INTO lrs_meta(k,v) VALUES('source', 'demo')")
    con.commit()
    print(f"LRS namuna: {len(courses)} kurs, {n_st} ta sun'iy statement")
    return {"courses": len(courses), "statements": n_st}

def redate(con, today: dt.date | None = None) -> int:
    """Namuna statementlarni joriy haftaga ko'chirish (masofaviy.redate bilan bir xil g'oya): butun haftalar farqiga suriladi, faqat src='demo'."""
    get = lambda k: (con.execute("SELECT v FROM lrs_meta WHERE k=?", (k,)).fetchone() or [None])[0]
    if not get("seed_v1") or not get("anchor"): return 0
    cur = LA.monday(today or clock.today())
    weeks = (cur - dt.date.fromisoformat(get("anchor"))).days // 7
    if weeks <= 0: return 0
    n = f"+{7 * weeks} days"
    lim = _iso(_now())
    try:
        con.execute(f"UPDATE lrs_statements SET ts=MIN(strftime('%Y-%m-%dT%H:%M:%S', ts, '{n}'), ?) WHERE src='demo'", (lim,))
        for k in {(r["student_id"], r["course_ref"], r["lesson_ref"]) for r in db.rows(con, "SELECT DISTINCT student_id, course_ref, lesson_ref FROM lrs_progress WHERE src='demo'")}:
            recompute(*k, con=con)
        con.execute("INSERT OR REPLACE INTO lrs_meta(k,v) VALUES('anchor', ?)", (cur.isoformat(),))
        con.commit()
    except Exception:
        con.rollback(); raise
    return weeks

def source() -> str:
    r = db.one(_con, "SELECT COUNT(*) n FROM lrs_statements WHERE src!='demo'")
    d = db.one(_con, "SELECT COUNT(*) n FROM lrs_statements WHERE src='demo'")
    return "demo" if (d or {}).get("n") and not (r or {}).get("n") else "mixed" if (d or {}).get("n") else "lrs"
