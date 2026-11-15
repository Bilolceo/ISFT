"""AI tutor (pilot) — kursga bog'langan, faqat tasdiqlangan kurs materialidan javob beradigan yordamchi (docs/tutor.md).

Dalil: amaliyotga o'rnatilgan, cheklangan (guardrail) tutor — katta foyda (Harvard RCT, 0,63 SD); cheklovsiz GPT — imtihonda −17 %
(Bastani, PNAS 2025); hech kim ishlatmaydigan ixtiyoriy chat — nol (Khanmigo); Jill Watson — faqat kurs materialidan javob. Shuning uchun:

  1. Indeks (app/tutor_index.py): pilot kursning tasdiqlangan paket darslari va muharrir kurslari (talabaga ochiladigan eksport bilan bir xil),
     barqaror id'li parchalar, BM25; tasdiq yoki yangi versiyada imzo o'zgaradi → indeks qayta quriladi.
  2. Xulq (app/tutor_text.verify): javob faqat parchalardan; har jumla iqtibos qilingan parcha bilan kesishmasa — olib tashlanadi; hech narsa
     qolmasa — «Bu savolga kurs materialida javob topilmadi» va o'qituvchiga yuborish taklifi. Test / bilimni tekshirish / Test bank savoliga
     mos savol (yoki «Yordam» tugmasi) — MASLAHAT rejimi: yo'naltiruvchi savollar, javob harfi/matni hech qachon (leaks() filtri).
     Mavzudan tashqari savol — model chaqirilmasdan rad etiladi.
  3. Provayder (app/tutor_llm.py): ISFT_CORE_TUTOR_PROVIDER = off | ollama | claude (standart off). Modelga faqat parchalar va savol matni.
     Pilot — kurs bo'yicha (bo'lim yoqadi), rejim: «all» yoki «tajriba» — guruhlarning tasodifiy yarmi (app/tajriba.arm, barqaror).
  4. Pleyer: ISFT Core launch orqali ochilgan darsga (/xapi/pkg/…/index.html) tutor skripti qo'shiladi (lrs.x_pkg → player_inject); eksport
     zip'lar o'zgarmaydi. Ixtiyoriy: «tutor bilan» xAPI eksport (bo'lim) — skript launch tokeni bilan ISFT Core'ga murojaat qiladi.
     Kuniga cheklov (talaba), token va narx jurnali, shikoyat tugmasi, o'qituvchiga savol; jurnal — bo'lim va kurs o'qituvchisi (taxallus bilan).
  5. Xavfsizlik: tizim ko'rsatmasi o'zgarmas; parcha va savol — ma'lumot; kurs matnidagi buyruqqa o'xshash jumlalar indeksga kirmaydi;
     savoldan shaxsiy ma'lumot tozalanadi; chiqish — oddiy matn (HTML/havola yo'q), pleyerda textContent.
"""
from __future__ import annotations
import collections, hashlib, json, re, secrets, threading, time
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from . import clock, db, tutor_index as TI, tutor_llm as LLM, tutor_text as TT

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
X = "/xapi/tutor"
PLAYER_DIR = Path(__file__).resolve().parent / "tutor_player"

MODES = {"all": "Pilot kursning barcha guruhlari", "tajriba": "Tajriba: guruhlarning tasodifiy yarmi (qolgani — taqqoslash)"}
DEFAULT_LIMIT = 20
MAX_Q = 600
BURST = (5, 60)                       # talaba: 60 s da ko'pi bilan 5 savol
COUNTED = ("javob", "maslahat", "topilmadi", "rad")

OFF_MSG = "AI yordamchi hozir o'chirilgan. Savolingizni o'qituvchingiz yoki tyutoringizga yuboring."
ASK_TEACHER = "Savolingizni o'qituvchingizga yuborishingiz mumkin — u aniqlik kiritadi."
OFFTOPIC_MSG = "Men faqat shu kurs materiallari bo'yicha yordam bera olaman. Savolingizni dars mavzusiga oid qilib yozing."
LIMIT_MSG = "Bugungi savollar chegarasi ({n} ta) tugadi. Ertaga qayta urinib ko'ring yoki savolingizni o'qituvchingizga yuboring."
HINT_FALLBACK = "Javobni o'zingiz topishingiz uchun quyidagi bo'limni qayta o'qing va savoldagi asosiy tushunchani shu yerdan toping."
ERR_MSG = "AI yordamchi hozir javob bera olmadi. Birozdan keyin qayta urinib ko'ring."

SCHEMA = """
CREATE TABLE IF NOT EXISTS tu_pilots(course_ref TEXT PRIMARY KEY, enabled INT DEFAULT 0, mode TEXT DEFAULT 'all', salt TEXT, daily_limit INT DEFAULT 20,
  started_at TEXT, updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS tu_chunks(pilot_ref TEXT, id TEXT, src_ref TEXT, lesson_ref TEXT, block_id TEXT, sec INT, label TEXT, title TEXT, text TEXT,
  kind TEXT, pos INT, PRIMARY KEY(pilot_ref, id));
CREATE TABLE IF NOT EXISTS tu_items(pilot_ref TEXT, src_ref TEXT, lesson_ref TEXT, item_id TEXT, kind TEXT, stem TEXT, data TEXT,
  PRIMARY KEY(pilot_ref, src_ref, item_id));
CREATE TABLE IF NOT EXISTS tu_index(pilot_ref TEXT PRIMARY KEY, sig TEXT, built_at TEXT, n_chunks INT, n_items INT, n_suspicious INT, n_lessons INT);
CREATE TABLE IF NOT EXISTS tu_log(id INTEGER PRIMARY KEY, ts TEXT, day TEXT, student_id INT, group_id INT, pilot_ref TEXT, course_ref TEXT, lesson_ref TEXT,
  item_id TEXT, arm TEXT, mode TEXT, question TEXT, answer TEXT, cites TEXT, provider TEXT, model TEXT, tok_in INT DEFAULT 0, tok_out INT DEFAULT 0,
  cost REAL DEFAULT 0, ms INT DEFAULT 0, dropped INT DEFAULT 0, injection INT DEFAULT 0, flagged INT DEFAULT 0, flag_note TEXT, flag_ts TEXT);
CREATE INDEX IF NOT EXISTS ix_tu_log_st ON tu_log(student_id, day);
CREATE INDEX IF NOT EXISTS ix_tu_log_p ON tu_log(pilot_ref, ts);
CREATE TABLE IF NOT EXISTS tu_teacher_q(id INTEGER PRIMARY KEY, ts TEXT, student_id INT, pilot_ref TEXT, log_id INT, question TEXT, status TEXT DEFAULT 'ochiq',
  reply TEXT, reply_by TEXT, reply_ts TEXT);
CREATE TABLE IF NOT EXISTS tu_meta(k TEXT PRIMARY KEY, v TEXT);
"""


def init(con):
    con.executescript(SCHEMA)
    if not db.one(con, "SELECT v FROM tu_meta WHERE k='pseudo'"):
        con.execute("INSERT INTO tu_meta(k,v) VALUES('pseudo',?)", (secrets.token_hex(16),))
    con.commit()


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def _iso() -> str: return clock.now().replace(microsecond=0).isoformat(timespec="seconds")


def pseudo(sid) -> str:
    """Talaba taxallusi (jurnalda ism yo'q): T-xxxxxx, o'rnatishga xos tuz bilan."""
    k = (db.one(_con, "SELECT v FROM tu_meta WHERE k='pseudo'") or {}).get("v", "")
    return "T-" + hashlib.sha256(f"{k}|{int(sid or 0)}".encode()).hexdigest()[:6]


# =============================================================================================
# Pilotlar va kirish
# =============================================================================================
def pilots(enabled_only: bool = False) -> dict:
    return {r["course_ref"]: r for r in db.rows(_con, "SELECT * FROM tu_pilots" + (" WHERE enabled=1" if enabled_only else ""))}


def resolve(sid: int, course_ref: str) -> dict | None:
    """Talaba × ochilgan kurs (launch tokeni course_ref) → {"pilot_ref", "arm", "limit", "group_id"} yoki None.
    Shartlar: faol talaba; kurs talabaning o'z ro'yxatida (talaba_darslar.courses_of / «ISFT Ready»); pilot yoqilgan; tajriba rejimida guruh
    «tajriba» qo'lida (nazorat qo'li — tutor yo'q)."""
    from . import talaba_darslar as TD, tajriba as TJ
    s = db.one(_con, "SELECT id, status, study_form, group_id FROM students WHERE id=?", (int(sid),))
    if not s or s["status"] != "faol": return None
    pil = pilots(True)
    if not pil: return None
    kind, _, cid = str(course_ref or "").partition(":")
    if not cid.isdigit(): return None
    cos = TD.courses_of(_con, s)
    ref = None
    if kind == "dl":
        if course_ref in pil and any(int(c["id"]) == int(cid) for c in cos): ref = course_ref
    elif kind == "ku":
        kid = int(cid)
        links = {c["id"]: set(TD._kurs_links(_con, c["id"]).values()) for c in cos}
        if course_ref in pil:
            ok = any(kid in v for v in links.values())
            if not ok:
                try:
                    from . import isft_ready as RDY
                    i = RDY.info(_con)
                    ok = bool(i and i["published"] and i["id"] == kid and s["study_form"] == "masofaviy")
                except Exception:
                    ok = False
            if ok: ref = course_ref
        if not ref:
            ref = next((f"dl:{k}" for k, v in links.items() if f"dl:{k}" in pil and kid in v), None)
    if not ref: return None
    p = pil[ref]
    arm = "hammasi" if p["mode"] != "tajriba" else TJ.arm("tutor:" + ref, p["salt"] or "", s["group_id"])
    if arm == "nazorat": return None
    return {"pilot_ref": ref, "arm": arm, "limit": int(p["daily_limit"] or DEFAULT_LIMIT), "group_id": s["group_id"]}


def player_inject(data: bytes, L: dict) -> bytes:
    """lrs.x_pkg: launch orqali ochilgan index.html ga tutor skripti (faqat provayder yoqilgan, pilot va qo'l mos bo'lsa). Xatoda — o'zgarishsiz."""
    try:
        if LLM.provider() == "off" or not resolve(L["student_id"], L["course_ref"]): return data
        tag = b'<link rel="stylesheet" href="/xapi/tutor/tutor.css"><script src="/xapi/tutor/tutor.js" defer></script>'
        i = data.rfind(b"</body>")
        return data[:i] + tag + data[i:] if i >= 0 else data + tag
    except Exception:
        return data


# =============================================================================================
# Savol → javob
# =============================================================================================
_BURST: dict = collections.defaultdict(collections.deque)


def used_today(sid: int) -> int:
    return int((db.one(_con, f"SELECT COUNT(*) n FROM tu_log WHERE student_id=? AND day=? AND mode IN ({','.join('?' * len(COUNTED))})",
                       (int(sid), clock.today().isoformat(), *COUNTED)) or {}).get("n") or 0)


def _cite(c: dict) -> dict:
    return {"id": c["id"], "label": c["label"], "title": c.get("title") or "", "src": c["src_ref"], "lesson": c["lesson_ref"], "block": c["block_id"]}


def _log(sid, R, auth, lesson, item_id, mode, q, ans, cites, info=None, dropped=0, inj=0) -> int:
    info = info or {}
    with _lock:
        lid = _con.execute("""INSERT INTO tu_log(ts,day,student_id,group_id,pilot_ref,course_ref,lesson_ref,item_id,arm,mode,question,answer,cites,provider,model,
                              tok_in,tok_out,cost,ms,dropped,injection) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (_iso(), clock.today().isoformat(), int(sid), R.get("group_id"), R["pilot_ref"], auth["course_ref"], lesson or "", item_id or "", R["arm"], mode,
                            q[:MAX_Q], ans[:4000], json.dumps(cites, ensure_ascii=False), info.get("provider") or LLM.provider(), info.get("model") or "",
                            int(info.get("in") or 0), int(info.get("out") or 0), LLM.cost(info.get("model") or "", int(info.get("in") or 0), int(info.get("out") or 0)),
                            int(info.get("ms") or 0), int(dropped), int(inj))).lastrowid
        _con.commit()
    return lid


class TErr(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg); self.status, self.msg = status, msg


def ask(auth: dict, question: str, lesson: str = "", item_id: str = "") -> dict:
    """auth — lrs.parse_auth natijasi (launch). → {mode, answer, cites, log_id, remaining}."""
    sid = int(auth["student_id"])
    R = resolve(sid, auth["course_ref"])
    if not R: raise TErr(403, "AI yordamchi bu kurs uchun yoqilmagan")
    ok, why = LLM.available()
    if not ok: return {"mode": "off", "answer": OFF_MSG, "cites": [], "reason": why}
    used = used_today(sid)
    if used >= R["limit"]: raise TErr(429, LIMIT_MSG.format(n=R["limit"]))
    now, dq = time.time(), _BURST[sid]
    while dq and now - dq[0] > BURST[1]: dq.popleft()
    if len(dq) >= BURST[0]: raise TErr(429, "Juda tez-tez so'rayapsiz — bir daqiqadan keyin qayta urinib ko'ring.")
    dq.append(now)
    q = re.sub(r"\s+", " ", str(question or "")).strip()[:MAX_Q]
    if len(q) < 3 and not item_id: raise TErr(400, "Savolni yozing")
    st = db.one(_con, "SELECT full_name FROM students WHERE id=?", (sid,)) or {}
    q = TT.scrub(q, [st.get("full_name") or ""])
    inj = TT.injection(q)
    q2 = TT.strip_injection(q)[0] if inj else q
    lesson = str(lesson or auth.get("lesson_ref") or "")[:40]
    m = TI.load(_con, R["pilot_ref"])
    item = TI.item_by_id(m, auth["course_ref"], item_id) if item_id else None
    if item_id and not item: raise TErr(404, "Topshiriq topilmadi")
    if not item and q2: item = TI.match_item(m, q2) or TI.near_item(m, q2)
    mode = "maslahat" if item or TT.ANSWER_SEEK.search(TT.norm(q2)) else "javob"
    query = (q2 + " " + (item["stem"] if item else "")).strip()
    rem = lambda: max(0, R["limit"] - used_today(sid))
    if not query or (not item and (TI.coverage(m, q2) < 0.4 or not TI.search(m, q2))):
        lid = _log(sid, R, auth, lesson, item_id, "rad", q, OFFTOPIC_MSG, [], inj=inj)
        return {"mode": "rad", "answer": OFFTOPIC_MSG, "cites": [], "log_id": lid, "remaining": rem()}
    hits = TI.search(m, query, prefer=(auth["course_ref"], lesson), k=5)
    loc = {f"c{i}": c for i, (_, c) in enumerate(hits, 1)}
    try:
        data, info = LLM.call(LLM.build_prompt(mode, list(loc.items()), q2 or "Maslahat bering", item))
    except LLM.LLMError as e:
        _log(sid, R, auth, lesson, item_id, "xato", q, str(e), [], inj=inj)
        return {"mode": "xato", "answer": ERR_MSG, "cites": [], "remaining": rem()}
    kept, dropped, status = TT.verify(data, loc, mode, item)
    if status == "mavzudan_tashqari" and not item:
        lid = _log(sid, R, auth, lesson, item_id, "rad", q, OFFTOPIC_MSG, [], info, dropped, inj)
        return {"mode": "rad", "answer": OFFTOPIC_MSG, "cites": [], "log_id": lid, "remaining": rem()}
    order = []
    for s in kept:
        for c in s["cites"]:
            if c not in order: order.append(c)
    cites = [_cite(loc[c]) for c in order]
    if mode == "maslahat":
        if not kept:
            answer, cites = HINT_FALLBACK, [_cite(c) for _, c in hits[:2]]
        else:
            answer = " ".join(s["text"] for s in kept)
        out_mode = "maslahat"
    elif kept and status != "topilmadi":
        answer, out_mode = " ".join(s["text"] for s in kept), "javob"
    else:
        answer, out_mode, cites = TT.NOT_FOUND + " " + ASK_TEACHER, "topilmadi", []
    lid = _log(sid, R, auth, lesson, item_id, out_mode, q, answer, cites, info, dropped, inj)
    return {"mode": out_mode, "answer": answer, "cites": cites, "log_id": lid, "remaining": rem(), "dropped": dropped}


# =============================================================================================
# HTTP: pleyer (launch tokeni bilan, /xapi/ ostida — pleyer CSP'si connect-src faqat /xapi/)
# =============================================================================================
def _json(data, status: int = 200) -> JSONResponse:
    from . import lrs as L
    return JSONResponse(data, status_code=status, headers={**L.CORS, "Cache-Control": "no-store"})


def _auth(request: Request) -> dict:
    from . import lrs as L
    if L.LIM_IP.take(L._ip(request)): raise TErr(429, "So'rovlar juda ko'p")
    try:
        a = L.parse_auth(request.headers.get("authorization"))
    except L.XErr as e:
        raise TErr(e.status, e.msg)
    if a["kind"] != "launch": raise TErr(403, "Faqat talaba launch tokeni bilan")
    return a


async def _body(request: Request) -> dict:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > 8192: raise TErr(413, "So'rov juda katta")
    raw = await request.body()
    if len(raw) > 8192: raise TErr(413, "So'rov juda katta")
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        raise TErr(400, "JSON noto'g'ri")
    if not isinstance(d, dict): raise TErr(400, "JSON noto'g'ri")
    return d


def _wrap(fn):
    async def h(request: Request):
        try:
            return _json(await fn(request))
        except TErr as e:
            return _json({"error": True, "message": e.msg}, e.status)
    return h


async def x_status(request: Request):
    a = _auth(request)
    R = resolve(a["student_id"], a["course_ref"])
    if not R: raise TErr(403, "AI yordamchi bu kurs uchun yoqilmagan")
    ok, _ = LLM.available()
    mine = db.rows(_con, """SELECT id, ts, question, status, reply, reply_ts FROM tu_teacher_q WHERE student_id=? AND pilot_ref=? ORDER BY id DESC LIMIT 20""",
                   (int(a["student_id"]), R["pilot_ref"]))
    return {"enabled": ok, "message": None if ok else OFF_MSG, "limit": R["limit"], "remaining": max(0, R["limit"] - used_today(a["student_id"])),
            "course_ref": a["course_ref"], "lesson": a["lesson_ref"], "teacher_questions": mine}


async def x_ask(request: Request):
    a = _auth(request)
    d = await _body(request)
    from fastapi.concurrency import run_in_threadpool
    return await run_in_threadpool(ask, a, str(d.get("question") or ""), str(d.get("lesson") or ""), str(d.get("item") or "")[:80])


def _own_log(a: dict, log_id) -> dict:
    try: lid = int(log_id or 0)
    except (TypeError, ValueError): lid = 0
    r = db.one(_con, "SELECT * FROM tu_log WHERE id=? AND student_id=?", (lid, int(a["student_id"])))
    if not r: raise TErr(404, "Javob topilmadi")
    return r


async def x_flag(request: Request):
    a = _auth(request)
    d = await _body(request)
    r = _own_log(a, d.get("log_id"))
    st = db.one(_con, "SELECT full_name FROM students WHERE id=?", (int(a["student_id"]),)) or {}
    note = TT.scrub(TT.clean_out(d.get("note")), [st.get("full_name") or ""])[:300]     # jurnal o'qituvchiga ko'rinadi — taxallus buzilmasin
    with _lock:
        _con.execute("UPDATE tu_log SET flagged=1, flag_note=?, flag_ts=? WHERE id=?", (note, _iso(), r["id"])); _con.commit()
    return {"ok": True}


async def x_teacher(request: Request):
    a = _auth(request)
    d = await _body(request)
    r = _own_log(a, d.get("log_id"))
    if db.one(_con, "SELECT id FROM tu_teacher_q WHERE log_id=?", (r["id"],)): return {"ok": True, "duplicate": True}
    with _lock:
        _con.execute("INSERT INTO tu_teacher_q(ts,student_id,pilot_ref,log_id,question) VALUES(?,?,?,?,?)",
                     (_iso(), int(a["student_id"]), r["pilot_ref"], r["id"], r["question"])); _con.commit()
    return {"ok": True}


router.add_api_route(X + "/status", _wrap(x_status), methods=["GET"])
router.add_api_route(X + "/ask", _wrap(x_ask), methods=["POST"])
router.add_api_route(X + "/flag", _wrap(x_flag), methods=["POST"])
router.add_api_route(X + "/teacher", _wrap(x_teacher), methods=["POST"])


@router.get(X + "/{name}")
def x_asset(name: str):
    if name not in ("tutor.js", "tutor.css"): return Response(status_code=404)
    f = PLAYER_DIR / name
    if not f.is_file(): return Response(status_code=404)
    return Response(f.read_bytes(), media_type="text/javascript" if name.endswith(".js") else "text/css",
                    headers={"Access-Control-Allow-Origin": "*", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})
