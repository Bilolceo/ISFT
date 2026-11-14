"""Talaba kabineti: «Mening darslarim» va Telegram (docs/talaba-kabineti.md, docs/lrs.md).

1. «Mening darslarim» (/api/talaba/darslar) — talaba guruhi orqali yozilgan masofaviy kurslar (dl_courses: yo'nalish × kurs, masofaviy guruh),
   darslar NEXTID tartibida (L, keyin A, S, Lab, MT — paket.lessons), har darsda holat (lrs_progress), taqvim belgisi («bu hafta», «kechikkan»)
   va «Ochish» — mavjud launch mexanizmi orqali (lrs.make_link → /xapi/l/<kod>, qisqa muddatli). Faqat TASDIQLANGAN paket (yoki muharrirda
   tasdiqlangan va eksport qilingan kurs — ds_links ustun manbasi «kurs») ochiladi; tasdiqlanmagan va hali hech kim boshlamagan darslar
   ro'yxatda ko'rinmaydi. Talaba id — faqat sessiyadan (student_portal.student). Boshqa talabaning ma'lumoti hech qayerda yo'q.
   Resume: registration talaba × kurs bo'yicha barqaror (lrs.registration_for) — State API holati keyingi ochilishda tiklanadi.

2. Telegram ulash (talaba): kabinetda bir martalik kod (8 belgi, 10 daqiqa, bitta ishlatish; bazada faqat SHA-256 xeshi) → botga
   «/start KOD» yoki shunchaki KOD. Xodimlar ulanishi kabi parol izi saqlanadi: talaba parolini almashtirsa, ulanish o'z-o'zidan uziladi.

3. Eslatma yetkazish («Ortda qolganlar» → Eslatma): ops_notices navbatidagi Telegram xabari ulangan talabaga bot orqali yuboriladi.
   Xabarda — qisqa shaxsiy izoh va «Mening darslarim» havolasi (kabinetga kirish talab qilinadi; launch tokeni/havolasi YO'Q).
   Ulanmagan talaba — xabar navbatda qoladi («Telegram ulanmagan»), talaba ulanganda yuboriladi. Bot tokeni yo'q bo'lsa — yuborish o'chiq,
   xabar navbatda. Har urinish — notice_delivery jurnalida (yuborildi / xato / ulanmagan / bot_ochiq).
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, secrets, threading, time, urllib.request, urllib.error
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, sessions as SS, lrs as L, lrs_analytics as LA

router = APIRouter()
_con = None
_lock = threading.RLock()

CODE_TTL = 600                      # bir martalik kod: 10 daqiqa
CODE_ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 0/O, 1/I yo'q
CODE_LEN = 8
CODE_LIMIT = SS.Limiter(5, 3600)    # bitta talaba: soatiga 5 ta kod
LAUNCH_HOURS = 2                    # kabinetdan ochish havolasi (keyin paketning o'zi 24 soatlik token oladi)
FLUSH_DAYS = 14                     # ulangandan keyin shu muddatdagi navbatdagi eslatmalar yuboriladi

SCHEMA = """
CREATE TABLE IF NOT EXISTS student_tg(student_id INTEGER PRIMARY KEY, telegram_id INT UNIQUE, pw_tag TEXT, linked_at TEXT);
CREATE TABLE IF NOT EXISTS student_tg_codes(code_hash TEXT PRIMARY KEY, student_id INT, created REAL, expires REAL, used_at TEXT, used_by INT);
CREATE INDEX IF NOT EXISTS ix_stg_codes_st ON student_tg_codes(student_id);
CREATE TABLE IF NOT EXISTS notice_delivery(id INTEGER PRIMARY KEY, notice_id INT, ts TEXT, channel TEXT, status TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS ix_notice_deliv ON notice_delivery(notice_id);
"""
DELIVERY = {"yuborildi": "Telegram'ga yuborildi", "xato": "Yuborishda xato — navbatda", "ulanmagan": "Telegram ulanmagan — navbatda",
            "bot_ochiq": "Bot ulanmagan (token yo'q) — navbatda"}


def init(con):
    con.executescript(SCHEMA)
    # jarayon yuborish o'rtasida to'xtagan bo'lsa — band qilingan xabar qayta urinish uchun «xato»ga qaytadi
    try: con.execute("UPDATE ops_notices SET status='xato' WHERE status='yuborilmoqda'")
    except Exception: pass
    con.commit()

def bind(con):
    global _con
    _con = con

def _iso() -> str: return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def _h(code: str) -> str: return hashlib.sha256(("stg|" + code).encode()).hexdigest()
def _norm(code: str) -> str: return "".join(ch for ch in str(code or "").upper() if ch.isalnum())[:32]
def _stp():
    from . import student_portal as STP
    return STP


# =============================================================================================
# 1. «Mening darslarim»
# =============================================================================================
def courses_of(con, s: dict) -> list[dict]:
    """Talaba yozilgan masofaviy kurslar — «Ortda qolganlar»dagi (ortda.enrolled) qoida bilan bir xil: masofaviy talaba, masofaviy guruh,
    kurs yo'nalishi va bosqichi guruhniki bilan bir xil."""
    g = db.one(con, """SELECT g.direction, g.course, g.form, s.study_form, s.status FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""",
               (int(s["id"]),))
    if not g or g["study_form"] != "masofaviy" or g["form"] != "masofaviy" or g["status"] != "faol": return []
    return db.rows(con, "SELECT * FROM dl_courses WHERE direction=? AND course=? ORDER BY semester, subject, id", (g["direction"], g["course"]))

def _approved_keys(con, cid: int) -> set:
    from . import paket as PK
    out = set()
    for r in db.rows(con, """SELECT topic_no, file FROM pk_packages WHERE course_id=? AND status='tasdiqlandi' AND mode!='none' AND file IS NOT NULL
                             AND file!=''""", (cid,)):
        if (PK.store() / r["file"]).is_file(): out.add(int(r["topic_no"]))
    return out

def _kurs_links(con, cid: int) -> dict:
    """{dars kaliti: ku kurs id} — ustun manbasi muharrir bo'lgan, muharrirda TASDIQLANGAN va eksport qilingan darslar."""
    if not db.one(con, "SELECT 1 x FROM sqlite_master WHERE type='table' AND name='ds_links'"): return {}
    out = {}
    for r in db.rows(con, """SELECT l.lkey, l.ku_course_id FROM ds_links l JOIN ku_courses k ON k.id=l.ku_course_id AND k.deleted=0 AND k.status='tasdiqlangan'
                             WHERE l.dl_course_id=? AND l.authority='kurs'""", (cid,)):
        if L.package_for(f"ku:{r['ku_course_id']}", ""): out[int(r["lkey"])] = int(r["ku_course_id"])
    return out

def _status_row(p: dict | None) -> dict:
    p = p or {}
    st = p.get("status") or "boshlanmagan"
    return {"status": st, "status_label": LA.STATUS.get(st, st), "pct": round(float(p.get("pct") or 0)), "score": p.get("score"), "best": p.get("best"),
            "attempts": int(p.get("attempts") or 0), "last": p.get("last_ts"), "time_min": round(float(p.get("time_s") or 0) / 60)}

def course_view(con, s: dict, co: dict) -> dict:
    """Bitta kurs: darslar (NEXTID tartibi), holat, taqvim belgisi, keyingi tavsiya etilgan dars, o'z progressi."""
    from . import paket as PK, ortda as ORT, haftalik as H
    sid, cid = int(s["id"]), int(co["id"])
    ref = f"dl:{cid}"
    oco = {"ref": ref, "kind": "dl", "dl_id": cid}
    cal = ORT.lessons_of(oco)                                        # taqvim tartibi (reja yoki L/A teng yoyilgan)
    cal_ix = {x["ref"]: i for i, x in enumerate(cal)}
    gid = (db.one(con, "SELECT group_id FROM students WHERE id=?", (sid,)) or {}).get("group_id")
    pl = H.plan(oco, gid, cal)                                       # guruhning haftalik taqvimi: chiqarilish sanasi va muddat
    sched, start, weeks = pl["sched"], pl["start"], pl["weeks"]
    today = clock.today()
    pol = L.policy(con)
    n = len(cal)
    rel_now = LA.released_by(sched, today)
    exp = LA.expected_by_due(sched, today, pol["grace_weeks"])
    prog = {r["lesson_ref"]: r for r in db.rows(con, "SELECT * FROM lrs_progress WHERE student_id=? AND course_ref=?", (sid, ref))}
    appr = _approved_keys(con, cid)
    kl = _kurs_links(con, cid)
    kprog = {}
    if kl:
        for r in db.rows(con, f"""SELECT * FROM lrs_progress WHERE student_id=? AND course_ref IN ({','.join('?' * len(kl))})""",
                         (sid, *[f"ku:{k}" for k in kl.values()])):
            kprog.setdefault(r["course_ref"], []).append(r)
    try: plist = PK.lessons(cid)
    except Exception: plist = []
    by_code = {l["code"]: l for l in plist}
    order = [l["code"] for l in plist] + [x["ref"] for x in cal if x["ref"] not in by_code]    # NEXTID tartibi (L, A, S, Lab, MT)
    items = []
    for code in order:
        key = L.code_to_key(code)
        if key is None: continue
        l = by_code.get(code) or {}
        title = l.get("title") or next((x["title"] for x in cal if x["ref"] == code), code)
        launch = None
        if key in kl: launch = {"course_ref": f"ku:{kl[key]}", "lesson_ref": ""}
        elif key in appr: launch = {"course_ref": ref, "lesson_ref": code}
        p = prog.get(code)
        if launch and launch["course_ref"].startswith("ku:") and not p:     # muharrir kursi: kurs darajasidagi holat
            rows = kprog.get(launch["course_ref"]) or []
            p = next((r for r in rows if r["lesson_ref"] == ""), None) or (max(rows, key=lambda r: r["last_ts"] or "") if rows else None)
        if not launch and not p: continue                                   # tasdiqlanmagan va boshlanmagan — ko'rsatilmaydi
        st = _status_row(p)
        i = cal_ix.get(code)
        done = st["status"] in LA.DONE_ST
        mark, sc = None, (sched[i] if i is not None else None)
        if sc:      # muddat bo'yicha: kechikkan — muddati o'tgan va bajarilmagan; bu hafta — chiqarilgan, muddati hali o'tmagan; keyinroq — hali chiqarilmagan
            if sc["due"] < today and not done: mark = "kechikkan"
            elif sc["release"] <= today <= sc["due"]: mark = "bu_hafta"
            elif sc["release"] > today: mark = "keyinroq"
        items.append({"code": code, "title": title, "kind": l.get("kind") or ("maruza" if code.startswith("L") else "amaliy"), **st, "mark": mark,
                      "cal": i, "can_open": bool(launch), "resume": bool(p) and not done and st["status"] != "boshlanmagan",
                      "week": sc["week"] if sc else None, "due": sc["due"].isoformat() if sc else None, "release": sc["release"].isoformat() if sc else None,
                      "due_label": H.due_label(sc["due"]) if sc else None})
    def _done_at(code: str) -> bool:
        # dars ikki manbadan biridan bajarilgan bo'lishi mumkin: dl:<cid> (paket) yoki bog'langan muharrir kursi ku:<id> (ds_links)
        if (prog.get(code) or {}).get("status") in LA.DONE_ST: return True
        k = L.code_to_key(code)
        if k is None or k not in kl: return False
        rows = kprog.get(f"ku:{kl[k]}") or []
        p = next((r for r in rows if r["lesson_ref"] == ""), None) or (max(rows, key=lambda r: r["last_ts"] or "") if rows else None)
        return bool(p) and p["status"] in LA.DONE_ST
    done_all = sum(1 for x in cal if _done_at(x["ref"]))
    cand = sorted((x for x in items if x["can_open"] and x["status"] not in LA.DONE_ST), key=lambda x: (x["cal"] if x["cal"] is not None else 10**6, x["code"]))
    nxt = cand[0] if cand else None
    scores = [x["best"] for x in items if x["best"] is not None]
    return {"ref": ref, "id": cid, "title": co["subject"], "semester": co["semester"], "lessons": items, "total": n, "done": done_all, "expected": exp,
            "released": rel_now, "lag": max(0, exp - done_all), "pct": round(100 * done_all / n) if n else 0, "week": LA.week_no(start, today), "weeks": weeks,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None, "late": sum(1 for x in items if x["mark"] == "kechikkan"),
            "next": {"code": nxt["code"], "title": nxt["title"], "resume": nxt["resume"], "mark": nxt["mark"]} if nxt else None,
            "hidden": max(0, n - len(items))}

def my_lessons(con, s: dict) -> dict:
    cos = [course_view(con, s, co) for co in courses_of(con, s)]
    pending = [c["title"] for c in cos if not c["lessons"]]       # hali birorta dars tasdiqlanmagan — ro'yxatda emas, hisobga kirmaydi
    cos = [c for c in cos if c["lessons"]]
    tot = {"courses": len(cos), "lessons": sum(c["total"] for c in cos), "done": sum(c["done"] for c in cos), "expected": sum(c["expected"] for c in cos),
           "late": sum(c["late"] for c in cos)}
    tot["lag"] = max(0, tot["expected"] - tot["done"])
    nxt = None
    for c in sorted(cos, key=lambda c: -c["lag"]):
        if c["next"]: nxt = {"course_ref": c["ref"], "course": c["title"], **c["next"]}; break
    # «Bu hafta»: joriy haftaning darslari (chiqarilgan, muddati o'tmagan) va muddati o'tgan bajarilmaganlar — muddat bo'yicha
    week = []
    for c in cos:
        for l in c["lessons"]:
            if l["mark"] in ("bu_hafta", "kechikkan"):          # kechikkan — faqat bajarilmagan (belgi shuni anglatadi)
                week.append({"course_ref": c["ref"], "course": c["title"], "code": l["code"], "title": l["title"], "due": l["due"], "due_label": l["due_label"],
                             "status": l["status"], "status_label": l["status_label"], "late": l["mark"] == "kechikkan", "can_open": l["can_open"],
                             "resume": l["resume"], "done": l["status"] in LA.DONE_ST})
    week.sort(key=lambda x: (x["done"], not x["late"], x["due"] or "", x["course"], x["code"]))
    from . import isft_ready as RDY
    try: ready = RDY.student_status(con, s["id"]) if s.get("study_form") == "masofaviy" else None
    except Exception: ready = None
    return {"courses": cos, "pending": pending, "total": tot, "next": nxt, "today": clock.today().isoformat(),
            "masofaviy": s.get("study_form") == "masofaviy", "this_week": week[:30], "ready": ready,
            "week_no": max((c["week"] for c in cos), default=0)}

def resolve_launch(con, s: dict, course_ref: str, code: str) -> dict:
    """Talaba so'ragan dars — FAQAT o'z ro'yxatidagi, ochiladigan (tasdiqlangan) dars bo'lsa. Aks holda None."""
    kind, _, cid = (course_ref or "").partition(":")
    if kind == "ku" and cid.isdigit():                 # «ISFT Ready» kirish kursi — har bir faol masofaviy talaba uchun (faqat e'lon qilingan bo'lsa)
        from . import isft_ready as RDY
        i = RDY.info(con)
        if i and i["published"] and i["id"] == int(cid) and s.get("study_form") == "masofaviy": return {"course_ref": i["ref"], "lesson_ref": ""}
        return None
    if kind != "dl" or not cid.isdigit(): return None
    co = next((c for c in courses_of(con, s) if c["id"] == int(cid)), None)
    if not co: return None
    key = L.code_to_key(code)
    if key is None: return None
    kl = _kurs_links(con, co["id"])
    if key in kl: return {"course_ref": f"ku:{kl[key]}", "lesson_ref": ""}
    if key in _approved_keys(con, co["id"]): return {"course_ref": course_ref, "lesson_ref": code}
    return None


class LaunchIn(BaseModel):
    course_ref: str = Field(..., max_length=20)
    lesson: str = Field(..., max_length=10)

@router.get("/api/talaba/darslar")
def api_darslar(request: Request):
    STP = _stp()
    s = STP.student(request)
    out = my_lessons(_con, s)
    STP._audit("mening darslarim", True, s, f"{out['total']['courses']} kurs")
    return out

@router.post("/api/talaba/darslar/launch")
def api_launch(body: LaunchIn, request: Request):
    STP = _stp()
    s = STP.student(request)
    if s["status"] != "faol": raise HTTPException(403, "Akademik ta'tilda darslar ochilmaydi")
    t = resolve_launch(_con, s, body.course_ref, body.lesson)
    if not t:
        STP._audit("darsni ochish", False, s, f"ruxsatsiz: {body.course_ref} {body.lesson}"[:120])
        raise HTTPException(404, "Dars topilmadi yoki hali tasdiqlanmagan")
    if not L.package_for(t["course_ref"], t["lesson_ref"], approved_only=True): raise HTTPException(404, "Dars paketi hali eksport qilinmagan")
    code = L.make_link(s["id"], t["course_ref"], t["lesson_ref"], days=LAUNCH_HOURS / 24, strict=True)
    STP._audit("darsni ochish", True, s, f"{body.course_ref} {body.lesson} → {t['course_ref']}")
    return {"url": f"/xapi/l/{code}"}


# =============================================================================================
# 2. Telegram ulash (talaba)
# =============================================================================================
def bot_token() -> str: return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
def bot_enabled() -> bool: return bool(bot_token()) and str(os.getenv("ISFT_CORE_TG_SEND", "1")).strip().lower() not in ("0", "false", "off", "no")

def bot_username() -> str | None:
    try:
        from . import bot as BOT
        return BOT.status().get("username")
    except Exception:
        return None

def _pw_tag(con, sid: int) -> str | None:
    a = db.one(con, "SELECT pw_hash FROM student_auth WHERE student_id=?", (int(sid),))
    return SS.pw_tag(a["pw_hash"]) if a else None

def link_of(con, sid: int) -> dict | None:
    """Amaldagi ulanish (parol o'zgarmagan va talaba faol/ta'tilda). Parol o'zgargan bo'lsa — ulanish uziladi (xodimlar kabi)."""
    r = db.one(con, "SELECT * FROM student_tg WHERE student_id=?", (int(sid),))
    if not r: return None
    st = db.one(con, "SELECT status FROM students WHERE id=?", (int(sid),))
    if not st or st["status"] not in ("faol", "akademik ta'til") or r["pw_tag"] != _pw_tag(con, sid):
        with _lock:
            con.execute("DELETE FROM student_tg WHERE student_id=?", (int(sid),)); con.commit()
        return None
    return r

def student_by_tg(con, tg_id: int) -> int | None:
    r = db.one(con, "SELECT student_id FROM student_tg WHERE telegram_id=?", (int(tg_id),))
    return r["student_id"] if r and link_of(con, r["student_id"]) else None

def new_code(con, sid: int) -> dict:
    """Bir martalik kod (eskisi bekor qilinadi). Bazada faqat xesh."""
    code = "".join(secrets.choice(CODE_ALPHA) for _ in range(CODE_LEN))
    now = time.time()
    with _lock:
        con.execute("DELETE FROM student_tg_codes WHERE (student_id=? AND used_at IS NULL) OR expires<?", (int(sid), now - 86400))
        con.execute("INSERT INTO student_tg_codes(code_hash,student_id,created,expires) VALUES(?,?,?,?)", (_h(code), int(sid), now, now + CODE_TTL))
        con.commit()
    return {"code": code, "expires_in": CODE_TTL}

def link_student(con, tg_id: int, code: str) -> dict:
    """Bot: KOD → talaba ulanadi. {ok, student_id?, error?}. Kod — bir martalik, muddatli; noto'g'ri/eski/ishlatilgan — rad."""
    c = _norm(code)
    if len(c) != CODE_LEN: return {"ok": False, "error": "format"}
    now = time.time()
    with _lock:
        r = db.one(con, "SELECT * FROM student_tg_codes WHERE code_hash=?", (_h(c),))
        if not r: return {"ok": False, "error": "noto'g'ri"}
        if r["used_at"]: return {"ok": False, "error": "ishlatilgan"}
        if r["expires"] < now: return {"ok": False, "error": "muddati o'tgan"}
        sid = int(r["student_id"])
        st = db.one(con, "SELECT status FROM students WHERE id=?", (sid,))
        if not st or st["status"] not in ("faol", "akademik ta'til"): return {"ok": False, "error": "maqom"}
        con.execute("UPDATE student_tg_codes SET used_at=?, used_by=? WHERE code_hash=?", (_iso(), int(tg_id), r["code_hash"]))
        con.execute("DELETE FROM student_tg WHERE telegram_id=? OR student_id=?", (int(tg_id), sid))
        con.execute("INSERT INTO student_tg(student_id,telegram_id,pw_tag,linked_at) VALUES(?,?,?,?)", (sid, int(tg_id), _pw_tag(con, sid), _iso()))
        con.commit()
    _sys_audit(con, "talaba Telegram'ga ulandi", True, sid, f"tg {tg_id}")
    return {"ok": True, "student_id": sid}

def unlink_tg(con, tg_id: int) -> int:
    with _lock:
        n = con.execute("DELETE FROM student_tg WHERE telegram_id=?", (int(tg_id),)).rowcount; con.commit()
    return n

def _sys_audit(con, action: str, ok: bool, sid: int, detail: str = ""):
    try:
        con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                    (_iso(), None, "Talaba (Telegram)", "Talaba", "telegram", f"talaba kabineti: {action}", "talaba", int(ok), f"talaba #{sid} · {detail}"[:300]))
        con.commit()
    except Exception:
        pass

@router.get("/api/talaba/telegram")
def api_tg(request: Request):
    s = _stp().student(request)
    r = link_of(_con, s["id"])
    return {"linked": bool(r), "since": r["linked_at"] if r else None, "bot": bot_enabled(), "username": bot_username(),
            "queued": db.one(_con, "SELECT COUNT(*) n FROM ops_notices WHERE student_id=? AND channel='telegram' AND status='navbatda'", (s["id"],))["n"]}

@router.post("/api/talaba/telegram/code")
def api_tg_code(request: Request):
    STP = _stp()
    s = STP.student(request)
    wait = CODE_LIMIT.wait_min(("tg", s["id"]))
    if wait: raise HTTPException(429, f"Juda ko'p kod so'raldi. {wait} daqiqadan keyin qayta urinib ko'ring.")
    CODE_LIMIT.fail(("tg", s["id"]))
    out = new_code(_con, s["id"])
    u = bot_username()
    STP._audit("Telegram ulash kodi", True, s)
    return {**out, "bot": bot_enabled(), "username": u, "deep_link": f"https://t.me/{u}?start={out['code']}" if u else None}

@router.post("/api/talaba/telegram/unlink")
def api_tg_unlink(request: Request):
    STP = _stp()
    s = STP.student(request)
    with _lock:
        n = _con.execute("DELETE FROM student_tg WHERE student_id=?", (s["id"],)).rowcount; _con.commit()
    STP._audit("Telegram uzildi", True, s, f"{n}")
    return {"ok": True, "unlinked": bool(n)}


# =============================================================================================
# 3. Eslatma yetkazish
# =============================================================================================
def cabinet_url() -> str | None:
    """Kabinet havolasi — FAQAT sozlangan ISFT_CORE_PUBLIC_URL dan (so'rovning Host sarlavhasidan hech qachon olinmaydi: host-header
    injection / ichki manzil sizishi). Sozlanmagan bo'lsa — None (xabarga absolyut havola yozilmaydi, faqat yo'riqnoma)."""
    b = os.getenv("ISFT_CORE_PUBLIC_URL", "").strip().rstrip("/")
    return (b + "/talaba#darslarim") if b.startswith(("https://", "http://")) else None

def cabinet_hint() -> str:
    u = cabinet_url()
    return f"{u} (talaba kabineti → «Mening darslarim»)" if u else "talaba kabineti (HEMIS ID bilan kiring) → «Mening darslarim»"

def tg_send(chat_id: int, text: str):
    """Telegram Bot API sendMessage (sinxron; xato — istisno). Token logga chiqmaydi."""
    tok = bot_token()
    if not tok: raise RuntimeError("bot o'chiq")
    data = json.dumps({"chat_id": int(chat_id), "text": text[:4000], "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"Telegram tarmoq xatosi: {type(e).__name__}") from None
    if not d.get("ok"): raise RuntimeError(f"Telegram rad etdi: {str(d.get('description') or '')[:120]}")

SENDER = None          # testlar uchun almashtiriladi: SENDER(chat_id, text)

def _log(con, nid: int, status: str, detail: str = ""):
    con.execute("INSERT INTO notice_delivery(notice_id,ts,channel,status,detail) VALUES(?,?,?,?,?)", (nid, _iso(), "telegram", status, (detail or "")[:300]))

SENDING = "yuborilmoqda"     # ops_notices.status: xabar band qilingan (bitta yuboruvchi), tarmoq so'rovi ketmoqda (init() da «xato»ga qaytariladi)

def _finish(con, nid: int, st: str, det: str):
    con.execute("UPDATE ops_notices SET status=? WHERE id=?", ({"yuborildi": "yuborildi", "xato": "xato"}.get(st, "navbatda"), nid))
    _log(con, nid, st, det)
    con.execute("UPDATE lrs_actions SET note=? WHERE notice_id=? AND kind='eslatma'", (f"Telegram · {DELIVERY[st]}", nid))
    con.commit()

def deliver(con, notice_id: int, sender=None) -> dict:
    """Bitta Telegram xabarini yetkazish. → {status, label}. Holatlar: yuborildi | xato | ulanmagan | bot_ochiq.
    ops_notices.status: yuborildi → «yuborildi», xato → «xato» (qayta urinish mumkin), qolganlari — «navbatda».
    Poyga: xabar qulf ostida atomar band qilinadi (UPDATE … SET status='yuborilmoqda' WHERE status IN navbatdagi holatlar; rowcount=1 —
    faqat bitta chaqiruvchi yuboradi: masalan flush_student (bot) va ortda.remind bir vaqtda). Telegram HTTP so'rovi qulfdan TASHQARIDA;
    natija yana qulf ostida yoziladi."""
    nid = int(notice_id)
    n = db.one(con, "SELECT * FROM ops_notices WHERE id=?", (nid,))
    if not n or n["channel"] != "telegram": return {"status": "xato", "label": "Xabar topilmadi"}
    if n["status"] == "yuborildi": return {"status": "yuborildi", "label": DELIVERY["yuborildi"]}
    send = sender or SENDER or (tg_send if bot_enabled() else None)
    lk = link_of(con, n["student_id"])
    with _lock:
        if not lk or send is None:                      # tarmoq yo'q — darhol qulf ostida yoziladi
            st, det = ("ulanmagan", "talaba Telegram'ni ulamagan") if not lk else ("bot_ochiq", "TELEGRAM_BOT_TOKEN o'rnatilmagan")
            cur = con.execute("UPDATE ops_notices SET status='navbatda' WHERE id=? AND status IN ('navbatda','xato')", (nid,))
            if cur.rowcount != 1:
                con.commit()
                return _busy(con, nid)
            _finish(con, nid, st, det)
            return {"status": st, "label": DELIVERY[st], "detail": det}
        cur = con.execute("UPDATE ops_notices SET status=? WHERE id=? AND status IN ('navbatda','xato')", (SENDING, nid))
        con.commit()
        if cur.rowcount != 1:                           # boshqa chaqiruvchi allaqachon yubordi / yubormoqda
            return _busy(con, nid)
    try:                                                # tarmoq — qulfsiz (10 s gacha)
        send(int(lk["telegram_id"]), n["text"]); st, det = "yuborildi", ""
    except Exception as e:
        st, det = "xato", str(e)[:200]
    with _lock:
        _finish(con, nid, st, det)
    return {"status": st, "label": DELIVERY[st], "detail": det}

def _busy(con, nid: int) -> dict:
    r = db.one(con, "SELECT status FROM ops_notices WHERE id=?", (int(nid),))
    if r and r["status"] == "yuborildi": return {"status": "yuborildi", "label": DELIVERY["yuborildi"], "detail": ""}
    return {"status": "band", "label": "Boshqa jarayon yubormoqda", "detail": ""}

def flush_student(con, sid: int, sender=None) -> int:
    """Talaba ulanganda: oxirgi FLUSH_DAYS kundagi navbatdagi (yoki xato bo'lgan) Telegram eslatmalarini yuborish."""
    since = (clock.now() - dt.timedelta(days=FLUSH_DAYS)).isoformat(timespec="seconds")
    n = 0
    for r in db.rows(con, "SELECT id FROM ops_notices WHERE student_id=? AND channel='telegram' AND status IN ('navbatda','xato') AND ts>=? ORDER BY id",
                     (int(sid), since)):
        n += deliver(con, r["id"], sender)["status"] == "yuborildi"
    return n

def last_delivery(con, notice_ids: list[int]) -> dict:
    if not notice_ids: return {}
    return {r["notice_id"]: r["status"] for r in db.rows(con, f"""SELECT d.notice_id, d.status FROM notice_delivery d WHERE d.id IN
              (SELECT MAX(id) FROM notice_delivery WHERE notice_id IN ({','.join('?' * len(notice_ids))}) GROUP BY notice_id)""", notice_ids)}

def linked_set(con, sids: list[int]) -> set:
    """link_of'ning to'plam shakli: faqat AMALDAGI ulanishlar (talaba faol/ta'tilda va parol izi mos). Uzilgan ulanishlar — ulanmagan."""
    if not sids: return set()
    ph = ",".join("?" * len(sids))
    out = set()
    for r in db.rows(con, f"""SELECT t.student_id, t.pw_tag, s.status, a.pw_hash FROM student_tg t JOIN students s ON s.id=t.student_id
                              LEFT JOIN student_auth a ON a.student_id=t.student_id WHERE t.student_id IN ({ph})""", list(sids)):
        if r["status"] in ("faol", "akademik ta'til") and r["pw_tag"] == (SS.pw_tag(r["pw_hash"]) if r["pw_hash"] else None): out.add(r["student_id"])
    return out
