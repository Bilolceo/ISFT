"""«Ortda qolganlar» → keys boshqaruvi: har bir bayroq — mas'ul tyutori, muddati va majburiy natijasi bor keys (docs/keyslar.md).

Nima uchun (dalil — reports/«Onlayn universitetlar va platformalar»): bayroqning o'zi emas, bayroqqa javob beradigan ODAM natija beradi —
InsideTrack coaching RCT (+5,2 f.p. qolish), OU qo'ng'iroq RCT; MAAPS (faqat panel va maslahat tizimi) — ta'sir yo'q. Shuning uchun:
har bayroq → keys, egasi (tyutor), SLA (standart — 2 ish kuni), yopishda majburiy natija va keyingi qadam sanasi; natija ko'rsatkichlari
(bog'lanish vaqti, SLA ulushi, qayta faollashish) — tyutor va umumiy kesimda, rektorga — Nazorat markazida (app/nazorat.py, oxirgi bo'lim).

Hayot sikli:  ochiq → jarayonda (birinchi bog'lanish qayd etildi) → yopilgan (natija majburiy).
  * sync(): «Ortda qolganlar» bayroqlari (app/ortda.py — qoidalar faqat o'quv faolligiga asoslanadi, demografiya YO'Q) → har talabaga bitta
    ochiq keys (kurslar va sabablar keys ichida). Guruh tyutori bo'lsa va yuklamasi chegaradan oshmagan bo'lsa — avtomatik egasi.
  * Bayroq yo'qolsa va hali hech kim bog'lanmagan bo'lsa — keys tizim tomonidan yopiladi («Bayroq o'zi yo'qoldi»; odam natijasi emas,
    ko'rsatkichlarda alohida).
  * Yopilgandan keyin `reopen_days` (14) kun o'tib talaba hali ham bayroqli bo'lsa — keys avtomatik QAYTA ochiladi (yangi keys, reopened_from).
    «O'qishni davom ettirmaydi» natijasi bilan yopilgan keys qayta ochilmaydi (Registrator jarayoni).
  * Tyutor yuklamasi chegarasi (`caseload_max`, standart 50; VMQ 559 bo'yicha 1:50 nisbat bilan mos): biriktirishda oshsa — ogohlantirish
    (409) va yuklamani taqsimlash tavsiyasi; bo'lim ataylab tasdiqlasa (force) — audit bilan.

Ruxsat (har so'rov audit jurnalida, resurs «lrs»):
  masofaviy, masofaviy_xodim — barcha keyslar, biriktirish, bog'lanish/yopish; qoidalar (SLA, chegara) — faqat bo'lim boshlig'i;
  tyutor                     — o'ziga biriktirilgan va o'z guruhlaridagi keyslar; bog'lanish va yopish — faqat o'z keyslari;
  rektor, prorektor_oquv     — faqat jamlangan ko'rsatkichlar (talaba ismi yo'q);
  boshqalar                  — 403.
"""
from __future__ import annotations
import datetime as dt, json, random, statistics, threading, time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac, lrs_analytics as LA
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/ortda/keys"
RES = "lrs"

HEAD, STAFF, TUT = "masofaviy", "masofaviy_xodim", "tyutor"
DEPT = (HEAD, STAFF)
LEAD = ("rektor", "prorektor_oquv")
LIST_ROLES = DEPT + (TUT,)
METRIC_ROLES = DEPT + (TUT,) + LEAD

OPEN = ("ochiq", "jarayonda")
STATUS = {"ochiq": "Ochiq", "jarayonda": "Jarayonda", "yopilgan": "Yopilgan"}
OUTCOMES = {"gaplashildi": "Qo'ng'iroq qilindi — gaplashildi", "javob_bermadi": "Qo'ng'iroq qilindi — javob bermadi", "uchrashildi": "Uchrashildi",
            "davom_ettirmaydi": "Talaba o'qishni davom ettirmaydi", "boshqa": "Boshqa (izoh bilan)"}
AUTO = "avto_yoqoldi"
AUTO_LABEL = "Bayroq o'zi yo'qoldi (tizim yopdi, bog'lanilmagan)"
SRC = {"qoida": "Qoida", "qayta": "Qayta ochildi", "qolda": "Qo'lda", "demo": "Namuna"}
POLICY = [  # (kalit, standart, izoh, (min, max))
    ("sla_days", 2, "Birinchi bog'lanish muddati (ish kuni, shanba-yakshanbasiz)", (1, 10)),
    ("caseload_max", 50, "Bitta tyutordagi ochiq keyslar chegarasi", (5, 500)),
    ("reopen_days", 14, "Yopilgandan keyin shuncha kun o'tib talaba hali bayroqli bo'lsa — keys qayta ochiladi", (3, 60)),
    ("reengage_days", 14, "Qayta faollashish: bog'lanishdan keyin shuncha kun ichida LMS faolligi", (3, 60)),
]
DEFAULTS = {k: v for k, v, _, _ in POLICY}
DEMOGRAPHIC = ("gender", "jins", "birth", "tugilgan", "age", "yosh", "nation", "millat", "region", "viloyat", "tuman", "address", "manzil",
               "citizenship", "fuqaro", "religion", "income", "daromad", "payment", "kontrakt", "grant", "disab", "nogiron")
NOTE_DEMO = "Qoidalar faqat o'quv faolligiga asoslanadi (darslar, testlar, kirish sanasi). Jinsi, yoshi, millati, hududi, to'lov turi kabi demografik ma'lumotlar ishlatilmaydi."

SCHEMA = """
CREATE TABLE IF NOT EXISTS ok_cases(id INTEGER PRIMARY KEY, student_id INT, status TEXT, owner_user INT, opened_at TEXT, sla_due TEXT,
  first_contact_at TEXT, last_contact_at TEXT, contacts INT DEFAULT 0, closed_at TEXT, closed_by INT, outcome TEXT, outcome_note TEXT, next_step TEXT,
  reasons TEXT, courses TEXT, level TEXT, risk INT, src TEXT, reopened_from INT, assigned_at TEXT, assigned_by INT, updated TEXT);
CREATE INDEX IF NOT EXISTS ix_ok_cases_st ON ok_cases(student_id, status);
CREATE INDEX IF NOT EXISTS ix_ok_cases_ow ON ok_cases(owner_user, status);
CREATE TABLE IF NOT EXISTS ok_log(id INTEGER PRIMARY KEY, case_id INT, ts TEXT, user_id INT, user_name TEXT, action TEXT, outcome TEXT, note TEXT,
  next_step TEXT);
CREATE INDEX IF NOT EXISTS ix_ok_log ON ok_log(case_id);
CREATE TABLE IF NOT EXISTS ok_policy(k TEXT PRIMARY KEY, v INT);
CREATE TABLE IF NOT EXISTS ok_meta(k TEXT PRIMARY KEY, v TEXT);
"""


def init(con):
    con.executescript(SCHEMA)
    con.commit()
    try:
        if db.one(con, "SELECT 1 x FROM lrs_meta WHERE k='seed_v1'") and not db.one(con, "SELECT 1 x FROM ok_meta WHERE k='seed_v1'"):
            seed(con)
        redate(con)
    except Exception as e:      # namuna ma'lumot ilovani to'xtatmasin
        print("keyslar seed:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t: dt.datetime | None) -> str | None: return t.replace(microsecond=0).isoformat(timespec="seconds") if t else None
def _P(s) -> dt.datetime | None:
    if not s: return None
    try: return dt.datetime.fromisoformat(str(s)[:19])
    except ValueError: return None
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _dmy(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 and v[4] == "-" else v

def policy(con=None) -> dict:
    con = con or _con
    have = {r["k"]: r["v"] for r in db.rows(con, "SELECT k, v FROM ok_policy")}
    return {k: int(have.get(k, v)) for k, v, _, _ in POLICY}


# =============================================================================================
# Sof funksiyalar (bazasiz — tests/test_keyslar.py)
# =============================================================================================
def add_workdays(t: dt.datetime, n: int) -> dt.datetime:
    """t dan n ish kuni keyin (shanba va yakshanba sanalmaydi), soat saqlanadi. Dam olish kuni ochilgan keys — dushanbadan sanaladi."""
    d = t
    k = 0
    while k < n:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: k += 1
    return d

def sla_state(c: dict, now: dt.datetime) -> str:
    """met — SLA ichida bog'lanildi; missed — kech bog'lanildi yoki bog'lanilmay muddat o'tdi; overdue — ochiq va muddat o'tgan;
    soon — 24 soatdan kam qoldi; ok — vaqt bor."""
    due, fc = _P(c.get("sla_due")), _P(c.get("first_contact_at"))
    if fc: return "met" if due and fc <= due else "missed"
    if c.get("status") not in OPEN: return "missed" if due and due < (_P(c.get("closed_at")) or now) else "ok"
    if due and due < now: return "overdue"
    return "soon" if due and (due - now).total_seconds() < 86400 else "ok"

def metrics(cases: list[dict], now: dt.datetime, window_days: int = 14) -> dict:
    """cases: [{status, opened_at, sla_due, first_contact_at, closed_at, outcome, reengaged_at}] (reengaged_at — bog'lanishdan keyingi birinchi
    LMS faolligi yoki None). Natija:
      opened / closed (odam yopgan) / auto_closed / open / overdue (ochiq, bog'lanilmagan, SLA o'tgan);
      median_contact_h — ochilishdan birinchi bog'lanishgacha median soat;
      sla_pct — baholanadigan keyslar (bog'lanilgan yoki SLA muddati o'tgan; SLA'dan oldin bayroq o'zi yo'qolgani hisobga olinmaydi) ichida
                SLA muddatida bog'lanilganlar ulushi;
      reeng_pct — bog'lanilgan keyslar ichida, `window_days` oynasi tugagan yoki allaqachon qaytganlar orasida bog'lanishdan keyin oyna ichida
                  LMS'da faollik ko'rsatganlar ulushi; reeng_pending — oynasi hali tugamaganlar."""
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    out = {"opened": len(cases), "closed": 0, "auto_closed": 0, "open": 0, "overdue": 0, "contacted": 0, "median_contact_h": None,
           "sla_n": 0, "sla_ok": 0, "sla_pct": None, "reeng_n": 0, "reeng_ok": 0, "reeng_pct": None, "reeng_pending": 0, "outcomes": {}}
    hrs = []
    for c in cases:
        op, due, fc, cl = _P(c.get("opened_at")), _P(c.get("sla_due")), _P(c.get("first_contact_at")), _P(c.get("closed_at"))
        if c.get("status") in OPEN:
            out["open"] += 1
            if not fc and due and due < now: out["overdue"] += 1
        elif c.get("outcome") == AUTO: out["auto_closed"] += 1
        else:
            out["closed"] += 1
            if c.get("outcome"): out["outcomes"][c["outcome"]] = out["outcomes"].get(c["outcome"], 0) + 1
        if fc or (due and due < (cl or now)):
            out["sla_n"] += 1
            if fc and due and fc <= due: out["sla_ok"] += 1
        if fc:
            out["contacted"] += 1
            if op: hrs.append(max(0.0, (fc - op).total_seconds() / 3600))
            end = fc + dt.timedelta(days=window_days)
            r = _P(c.get("reengaged_at"))
            if r and fc < r <= end: out["reeng_n"] += 1; out["reeng_ok"] += 1
            elif now >= end: out["reeng_n"] += 1
            else: out["reeng_pending"] += 1
    out["median_contact_h"] = round(statistics.median(hrs), 1) if hrs else None
    out["sla_pct"] = pct(out["sla_ok"], out["sla_n"])
    out["reeng_pct"] = pct(out["reeng_ok"], out["reeng_n"])
    return out

def suggest(cands: list[dict], limit: int) -> dict | None:
    """Yuklamani taqsimlash tavsiyasi. cands: [{id, load, group_tutor, same_faculty}]. Tartib: chegaradan past guruh tyutori → shu fakultetning
    eng kam yuklangan tyutori → qolganlarning eng kam yuklangani. Hammasi to'la — None."""
    free = [x for x in cands if x["load"] < limit]
    if not free: return None
    return sorted(free, key=lambda x: (not x.get("group_tutor"), not x.get("same_faculty"), x["load"], x["id"]))[0]

def explain(courses: list[dict], pol: dict) -> list[str]:
    """Har bir sabab — oddiy o'zbek tilida, raqamlar va qoida chegarasi bilan (talabaga va tyutorga tushunarli)."""
    p = {**LA.DEFAULTS, **(pol or {})}
    out = []
    for co in courses:
        t = co.get("title") or "Kurs"
        for r in co.get("reasons") or []:
            k = r.get("code")
            if k == "ortda":
                out.append(f"«{t}»: taqvim bo'yicha {co.get('expected', 0)} ta dars tugatilgan bo'lishi kerak edi, {co.get('done', 0)} tasi tugatilgan — "
                           f"{max(0, int(co.get('expected') or 0) - int(co.get('done') or 0))} dars ortda (qoida: {p['lag_lessons']} va undan ko'p dars).")
            elif k == "test":
                out.append(f"«{t}»: {co.get('fail_lesson') or 'bitta'} testidan {co.get('max_fails', 0)} marta o'tolmagan va hali o'tmagan "
                           f"(qoida: {p['fail_attempts']} va undan ko'p urinish).")
            elif k == "faolsiz":
                out.append(f"«{t}»: oxirgi faollik {co.get('days_inactive')} kun oldin (qoida: {p['inactive_days']} kun va undan ko'p).")
            elif k == "boshlamagan":
                out.append(f"«{t}»: {co.get('expected', 0)} ta dars kutilgan, birortasi ham boshlanmagan.")
            elif k == "ready":
                out.append(f"{r.get('label')} — kirish kursi platforma, muddatlar va yordam olish yo'llarini tushuntiradi.")
            else:
                out.append(f"«{t}»: {r.get('label')}")
    return out


# =============================================================================================
# Bayroqlar → keyslar
# =============================================================================================
def flagged() -> dict:
    """{talaba: {courses: [...], reasons: [...], risk, level}} — barcha kuzatiladigan kurslar bo'yicha («Ortda qolganlar» qoidalari)."""
    from . import ortda as ORT
    out: dict = {}
    for co in ORT._course_rows():
        for r in ORT.course_rows(co):
            if not r["reasons"]: continue
            f = out.setdefault(r["student_id"], {"courses": [], "reasons": [], "risk": 0, "group_id": r["group_id"]})
            f["courses"].append({"ref": r["course_ref"], "title": r["course"], "expected": r["expected"], "done": r["done"], "lag": r["lag"],
                                 "max_fails": r["max_fails"], "fail_lesson": r["fail_lesson"], "days_inactive": r["days_inactive"], "last": r["last"],
                                 "reasons": r["reasons"], "level": r["level"]})
            f["reasons"] += [x["label"] for x in r["reasons"]]
            f["risk"] += r["risk"]
    for f in out.values():
        f["level"] = "yuqori" if any(c["level"] == "yuqori" for c in f["courses"]) or f["risk"] >= 4 else "orta"
    return out

def loads(con=None) -> dict:
    con = con or _con
    return {r["o"]: r["n"] for r in db.rows(con, "SELECT owner_user o, COUNT(*) n FROM ok_cases WHERE status IN ('ochiq','jarayonda') AND owner_user IS NOT NULL GROUP BY 1")}

def _log(case_id: int, c: Ctx | None, action: str, outcome: str | None = None, note: str = "", next_step: str | None = None, ts: str | None = None):
    _con.execute("INSERT INTO ok_log(case_id,ts,user_id,user_name,action,outcome,note,next_step) VALUES(?,?,?,?,?,?,?,?)",
                 (case_id, ts or _iso(_now()), c.user["id"] if c else None, (c.user["full_name"] if c else "Tizim"), action, outcome, (note or "")[:500], next_step))

def _group_tutor(gid) -> int | None:
    r = db.one(_con, "SELECT t.user_id FROM tutor_groups t JOIN users u ON u.id=t.user_id WHERE t.group_id=? AND u.role='tyutor' AND COALESCE(u.active,1)!=0",
               (int(gid or 0),))
    return r["user_id"] if r else None

_SYNC = {"t": 0.0}

def sync(now: dt.datetime | None = None, force: bool = True) -> dict:
    """Bayroqlar bilan keyslarni moslashtirish (idempotent). force=False — oxirgi sinxronizatsiyadan 60 s o'tmagan bo'lsa o'tkazib yuboriladi."""
    if not force and time.time() - _SYNC["t"] < 60: return {"skipped": True}
    now = now or _now()
    pol = policy()
    fl = flagged()
    st = {"opened": 0, "reopened": 0, "auto_closed": 0, "updated": 0}
    with _lock:
        cur = {r["student_id"]: r for r in db.rows(_con, "SELECT * FROM ok_cases WHERE status IN ('ochiq','jarayonda')")}
        last = {r["student_id"]: r for r in db.rows(_con, """SELECT c.* FROM ok_cases c JOIN (SELECT student_id, MAX(id) m FROM ok_cases WHERE status='yopilgan'
                                                              GROUP BY student_id) x ON x.m=c.id""")}
        ld = loads()
        for sid, f in sorted(fl.items()):
            cj = json.dumps(f["courses"], ensure_ascii=False, sort_keys=True)
            if sid in cur:
                o = cur[sid]
                if o["courses"] != cj:
                    _con.execute("UPDATE ok_cases SET courses=?, reasons=?, level=?, risk=?, updated=? WHERE id=?",
                                 (cj, json.dumps(f["reasons"], ensure_ascii=False), f["level"], f["risk"], _iso(now), o["id"]))
                    st["updated"] += 1
                continue
            prev = last.get(sid)
            src, ref = "qoida", None
            if prev and prev["outcome"] != AUTO:
                if prev["outcome"] == "davom_ettirmaydi": continue
                cl = _P(prev["closed_at"])
                if cl and (now - cl).days < pol["reopen_days"]: continue          # yopilganiga hali 14 kun bo'lmagan — kutiladi
                src, ref = "qayta", prev["id"]
            own = _group_tutor(f.get("group_id"))
            if own and ld.get(own, 0) >= pol["caseload_max"]: own = None      # guruh tyutori to'la — bo'lim taqsimlaydi
            cid = _con.execute("""INSERT INTO ok_cases(student_id,status,owner_user,opened_at,sla_due,reasons,courses,level,risk,src,reopened_from,assigned_at,updated)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (sid, "ochiq", own, _iso(now), _iso(add_workdays(now, pol["sla_days"])), json.dumps(f["reasons"], ensure_ascii=False), cj,
                                f["level"], f["risk"], src, ref, _iso(now) if own else None, _iso(now))).lastrowid
            if own: ld[own] = ld.get(own, 0) + 1
            _log(cid, None, "qayta ochildi" if src == "qayta" else "ochildi", note=f"#{ref} yopilganidan {pol['reopen_days']}+ kun keyin talaba hali bayroqli" if ref else
                 "; ".join(f["reasons"])[:300])
            st["reopened" if src == "qayta" else "opened"] += 1
        for sid, o in cur.items():
            if sid not in fl and not o["first_contact_at"] and not o["contacts"]:
                _con.execute("UPDATE ok_cases SET status='yopilgan', closed_at=?, outcome=?, updated=? WHERE id=?", (_iso(now), AUTO, _iso(now), o["id"]))
                _log(o["id"], None, "yopildi (tizim)", AUTO, "Talaba endi «Ortda qolganlar» qoidalariga tushmaydi")
                st["auto_closed"] += 1
        _con.commit()
    _SYNC["t"] = time.time()
    return st


# =============================================================================================
# Ko'lam va ko'rinish
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=LIST_ROLES, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"keyslar: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Keyslar: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def _scope(c: Ctx, alias="k") -> tuple[str, tuple]:
    if c.role.key in DEPT: return "1=1", ()
    if c.role.key == TUT:
        return (f"({alias}.owner_user=? OR {alias}.student_id IN (SELECT s.id FROM students s WHERE {c.student_scope('s')}))", (c.user["id"],))
    return "0=1", ()

def _case(c: Ctx, cid: int) -> dict:
    sw, sa = _scope(c)
    r = db.one(_con, f"SELECT k.* FROM ok_cases k WHERE k.id=? AND {sw}", (int(cid), *sa))
    if not r:
        if db.one(_con, "SELECT 1 x FROM ok_cases WHERE id=?", (int(cid),)):
            rbac.audit(_con, c, "keyslar: begona keys", RES, False, f"keys #{cid}")
            raise AccessDenied("⛔ Bu keys sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
        raise HTTPException(404, "Keys topilmadi")
    return r

def _users(ids) -> dict:
    ids = [int(x) for x in ids if x]
    if not ids: return {}
    return {r["id"]: r for r in db.rows(_con, f"SELECT id, full_name, faculty_id FROM users WHERE id IN ({','.join(map(str, set(ids)))})")}

def _jl(s, d):
    try: v = json.loads(s) if s else d
    except (TypeError, ValueError): return d
    return v if isinstance(v, type(d)) else d

def view(c: Ctx, r: dict, st: dict, us: dict, now: dt.datetime, pol: dict, full: bool = False) -> dict:
    courses = _jl(r["courses"], [])
    ow = us.get(r["owner_user"])
    out = {"id": r["id"], "student": {"id": r["student_id"], "name": (st or {}).get("full_name"), "grp": (st or {}).get("grp")},
           "status": r["status"], "status_label": STATUS.get(r["status"]), "owner": {"id": ow["id"], "name": _short(ow["full_name"]) or ow["full_name"]} if ow else None,
           "opened_at": r["opened_at"], "sla_due": r["sla_due"], "sla": sla_state(r, now), "first_contact_at": r["first_contact_at"],
           "last_contact_at": r["last_contact_at"], "contacts": r["contacts"] or 0, "closed_at": r["closed_at"], "outcome": r["outcome"],
           "outcome_label": AUTO_LABEL if r["outcome"] == AUTO else OUTCOMES.get(r["outcome"]), "outcome_note": r["outcome_note"],
           "next_step": r["next_step"], "level": r["level"], "reasons": _jl(r["reasons"], []), "courses": [{"ref": x["ref"], "title": x["title"]} for x in courses],
           "explain": explain(courses, pol), "src": r["src"], "src_label": SRC.get(r["src"], r["src"]), "reopened_from": r["reopened_from"],
           "can_act": r["status"] in OPEN and (c.role.key in DEPT or (c.role.key == TUT and r["owner_user"] == c.user["id"])),
           "can_assign": c.role.key in DEPT and r["status"] in OPEN}
    if full:
        out["log"] = db.rows(_con, "SELECT ts, user_name, action, outcome, note, next_step FROM ok_log WHERE case_id=? ORDER BY id DESC LIMIT 50", (r["id"],))
        for x in out["log"]:
            x["user_name"] = _short(x["user_name"]) or x["user_name"]
            x["outcome_label"] = AUTO_LABEL if x["outcome"] == AUTO else OUTCOMES.get(x["outcome"])
        out["note"] = NOTE_DEMO
        out["outcomes"] = OUTCOMES
        out["course_rows"] = courses
        if out["can_act"] or c.role.key in DEPT:        # qo'ng'iroq uchun — faqat egasi va bo'lim (audit bilan)
            out["student"]["phone"] = (st or {}).get("phone")
    return out

def _students(sids) -> dict:
    sids = [int(x) for x in sids]
    if not sids: return {}
    return {r["id"]: r for r in db.rows(_con, f"""SELECT s.id, s.full_name, s.phone, s.group_id, g.name grp FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
                                                 WHERE s.id IN ({','.join(map(str, set(sids)))})""")}

def list_cases(c: Ctx, status: str = "faol", owner: str = "", q: str = "", offset: int = 0, limit: int = 50) -> dict:
    sync(force=False)
    now, pol = _now(), policy()
    sw, sa = _scope(c)
    w, a = [sw], list(sa)
    if status == "faol": w.append("k.status IN ('ochiq','jarayonda')")
    elif status in STATUS: w.append("k.status=?"); a.append(status)
    if owner == "men": w.append("k.owner_user=?"); a.append(c.user["id"])
    elif owner == "yoq": w.append("k.owner_user IS NULL")
    elif owner.isdigit(): w.append("k.owner_user=?"); a.append(int(owner))
    rows = db.rows(_con, f"SELECT k.* FROM ok_cases k WHERE {' AND '.join(w)} ORDER BY k.id DESC LIMIT 3000", tuple(a))
    st = _students([r["student_id"] for r in rows])
    if q.strip():
        ql = q.strip().lower()
        rows = [r for r in rows if ql in ((st.get(r["student_id"]) or {}).get("full_name") or "").lower() or ql in ((st.get(r["student_id"]) or {}).get("grp") or "").lower()]
    rank = {"overdue": 0, "soon": 1, "ok": 2, "missed": 3, "met": 4}
    rows.sort(key=lambda r: (r["status"] not in OPEN, rank.get(sla_state(r, now), 5), r["sla_due"] or "", -r["id"]) if r["status"] in OPEN
              else (True, 9, "", -(_P(r["closed_at"]) or now).timestamp()))
    total = len(rows)
    page = rows[max(0, offset): max(0, offset) + max(1, min(200, limit))]
    us = _users([r["owner_user"] for r in page])
    items = [view(c, r, st.get(r["student_id"]), us, now, pol) for r in page]
    cnt = db.one(_con, f"""SELECT SUM(k.status='ochiq') o, SUM(k.status='jarayonda') j, SUM(k.status IN ('ochiq','jarayonda') AND k.first_contact_at IS NULL AND k.sla_due<?) od,
                           SUM(k.status IN ('ochiq','jarayonda') AND k.owner_user IS NULL) na FROM ok_cases k WHERE {sw}""", (_iso(now), *sa)) or {}
    return {"items": items, "total": total, "offset": offset, "counts": {"ochiq": cnt.get("o") or 0, "jarayonda": cnt.get("j") or 0, "overdue": cnt.get("od") or 0,
            "unassigned": cnt.get("na") or 0}, "policy": pol, "outcomes": OUTCOMES, "demo": bool(items) and all(x["src"] == "demo" for x in items),
            "note": NOTE_DEMO, "my_load": loads().get(c.user["id"], 0) if c.role.key == TUT else None}


# =============================================================================================
# Amallar
# =============================================================================================
def candidates(c: Ctx, cid: int) -> dict:
    r = _case(c, cid)
    s = db.one(_con, "SELECT s.group_id, s.faculty_id, g.faculty_id gf FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (r["student_id"],)) or {}
    gt = _group_tutor(s.get("group_id"))
    fac = s.get("faculty_id") or s.get("gf") or 0
    ld, lim = loads(), policy()["caseload_max"]
    out = [{"id": u["id"], "name": _short(u["full_name"]) or u["full_name"], "load": ld.get(u["id"], 0), "group_tutor": u["id"] == gt,
            "same_faculty": u["faculty_id"] == fac}
           for u in db.rows(_con, "SELECT id, full_name, faculty_id FROM users WHERE role='tyutor' AND COALESCE(active,1)!=0 ORDER BY id")]
    out.sort(key=lambda x: (not x["group_tutor"], not x["same_faculty"], x["load"], x["id"]))
    sg = suggest(out, lim)
    return {"items": out[:80], "limit": lim, "suggest": sg and sg["id"], "current": r["owner_user"]}

def assign(c: Ctx, cid: int, tutor: int, force: bool = False, note: str = "") -> dict:
    r = _case(c, cid)
    if r["status"] not in OPEN: raise HTTPException(400, "Yopilgan keysni biriktirib bo'lmaydi")
    tu = db.one(_con, "SELECT * FROM users WHERE id=? AND role='tyutor' AND COALESCE(active,1)!=0", (int(tutor),))
    if not tu: raise HTTPException(400, "Tyutor topilmadi")
    lim = policy()["caseload_max"]
    with _lock:
        ld = loads()
        cur = ld.get(tu["id"], 0) - (1 if r["owner_user"] == tu["id"] else 0)
        if cur >= lim and not force:
            cd = candidates(c, cid)
            sg = next((x for x in cd["items"] if x["id"] == cd["suggest"]), None)
            rbac.audit(_con, c, "keyslar: yuklama chegarasi ogohlantirishi", RES, False, f"keys #{cid} → tyutor #{tu['id']} ({cur}/{lim})")
            raise HTTPException(409, {"message": f"{_short(tu['full_name'])}da {cur} ta ochiq keys bor (chegara — {lim}). Yuklamani taqsimlash tavsiya etiladi"
                                                 + (f": {sg['name']} ({sg['load']} ta)." if sg else " — barcha tyutorlar to'la."),
                                      "load": cur, "limit": lim, "suggest": sg, "overload": True})
        now = _iso(_now())
        _con.execute("UPDATE ok_cases SET owner_user=?, assigned_at=?, assigned_by=?, updated=? WHERE id=?", (tu["id"], now, c.user["id"], now, cid))
        _log(cid, c, "biriktirildi", note=(f"{_short(tu['full_name'])}" + (f" · chegaradan oshirildi ({cur + 1}/{lim})" if cur >= lim else "")
                                          + (f" · {note.strip()}" if note.strip() else ""))[:500])
        _con.commit()
    rbac.audit(_con, c, "keyslar: biriktirildi", RES, True, f"keys #{cid} → tyutor #{tu['id']}" + (" · chegaradan oshirildi" if cur >= lim else ""))
    return {"ok": True, "owner": {"id": tu["id"], "name": _short(tu["full_name"])}, "load": cur + 1, "limit": lim, "over": cur >= lim}

def _check_outcome(outcome: str, note: str, next_step: str, closing: bool) -> str | None:
    if outcome not in OUTCOMES: raise HTTPException(400, "Natijani tanlang — " + ", ".join(OUTCOMES.values()))
    if outcome == "boshqa" and len((note or "").strip()) < 5: raise HTTPException(400, "«Boshqa» natijasi uchun izoh yozing (kamida 5 belgi)")
    ns = (next_step or "").strip()[:10]
    if ns:
        try: d = dt.date.fromisoformat(ns)
        except ValueError: raise HTTPException(400, "Keyingi qadam sanasi: YYYY-MM-DD")
        if d < clock.today(): raise HTTPException(400, "Keyingi qadam sanasi o'tgan kun bo'lolmaydi")
        return d.isoformat()
    if closing and outcome != "davom_ettirmaydi": raise HTTPException(400, "Keyingi qadam sanasini kiriting (masalan, qayta tekshirish kuni)")
    return None

def _actor_ok(c: Ctx, r: dict):
    if c.role.key in DEPT: return
    if c.role.key == TUT and r["owner_user"] == c.user["id"]: return
    rbac.audit(_con, c, "keyslar: begona keysda amal", RES, False, f"keys #{r['id']}")
    raise AccessDenied("⛔ Faqat keys egasi (tyutor) yoki Masofaviy ta'lim bo'limi amal bajaradi. So'rov audit jurnaliga yozildi.")

def contact(c: Ctx, cid: int, outcome: str, note: str = "", next_step: str = "") -> dict:
    """Bog'lanishni qayd etish (keys ochiq qoladi → «jarayonda»)."""
    r = _case(c, cid); _actor_ok(c, r)
    if r["status"] not in OPEN: raise HTTPException(400, "Keys yopilgan")
    ns = _check_outcome(outcome, note, next_step, False)
    now = _iso(_now())
    with _lock:
        _con.execute("""UPDATE ok_cases SET status='jarayonda', first_contact_at=COALESCE(first_contact_at, ?), last_contact_at=?, contacts=COALESCE(contacts,0)+1,
                        next_step=COALESCE(?, next_step), updated=? WHERE id=?""", (now, now, ns, now, cid))
        _log(cid, c, "bog'lanildi", outcome, note, ns)
        _con.commit()
    rbac.audit(_con, c, "keyslar: bog'lanish qayd etildi", RES, True, f"keys #{cid} · {outcome}")
    return {"ok": True}

def close(c: Ctx, cid: int, outcome: str, note: str = "", next_step: str = "") -> dict:
    """Yopish — natija MAJBURIY (OUTCOMES), «boshqa» — izoh bilan, keyingi qadam sanasi («davom ettirmaydi»dan tashqari)."""
    r = _case(c, cid); _actor_ok(c, r)
    if r["status"] not in OPEN: raise HTTPException(400, "Keys allaqachon yopilgan")
    ns = _check_outcome(outcome, note, next_step, True)
    now = _iso(_now())
    with _lock:
        _con.execute("""UPDATE ok_cases SET status='yopilgan', closed_at=?, closed_by=?, outcome=?, outcome_note=?, next_step=?,
                        first_contact_at=COALESCE(first_contact_at, ?), last_contact_at=?, contacts=COALESCE(contacts,0)+1, updated=? WHERE id=?""",
                     (now, c.user["id"], outcome, (note or "").strip()[:500], ns, now, now, now, cid))
        _log(cid, c, "yopildi", outcome, note, ns)
        _con.commit()
    rbac.audit(_con, c, "keyslar: yopildi", RES, True, f"keys #{cid} · {outcome}")
    return {"ok": True}


# =============================================================================================
# Ko'rsatkichlar
# =============================================================================================
def _reengaged(rows: list[dict]) -> dict:
    """{keys id: bog'lanishdan keyingi birinchi LMS faolligi (ts) | None}."""
    out = {}
    for r in rows:
        if not r["first_contact_at"]: continue
        x = db.one(_con, "SELECT MIN(ts) t FROM lrs_statements WHERE student_id=? AND voided=0 AND ts>?", (r["student_id"], r["first_contact_at"]))
        out[r["id"]] = (x or {}).get("t")
    return out

def metrics_data(since: str | None = None, owner: int | None = None, now: dt.datetime | None = None) -> dict:
    """Umumiy va tyutorlar bo'yicha ko'rsatkichlar (ism — faqat xodimlar). since — ochilgan sana (standart — semestr boshi)."""
    from . import academic_rules as AR
    now = now or _now()
    since = since or AR.term_dates(AR.CURRENT_SEMESTER)[0]
    pol = policy()
    w, a = ["opened_at>=?"], [since]
    if owner: w.append("owner_user=?"); a.append(int(owner))
    rows = db.rows(_con, f"SELECT * FROM ok_cases WHERE {' AND '.join(w)}", tuple(a))
    re_ = _reengaged(rows)
    for r in rows: r["reengaged_at"] = re_.get(r["id"])
    tot = metrics(rows, now, pol["reengage_days"])
    by: dict = {}
    for r in rows: by.setdefault(r["owner_user"], []).append(r)
    us = _users(by.keys())
    ld = loads()
    tutors = []
    for uid, rs in by.items():
        m = metrics(rs, now, pol["reengage_days"])
        u = us.get(uid)
        tutors.append({"id": uid, "name": (_short(u["full_name"]) or u["full_name"]) if u else "Biriktirilmagan", "load": ld.get(uid, 0) if uid else m["open"],
                       "over": bool(uid) and ld.get(uid, 0) > pol["caseload_max"], **m})
    tutors.sort(key=lambda x: (x["id"] is not None, -x["overdue"], -(x["load"] or 0)))
    return {"since": since, "now": _iso(now), "total": tot, "tutors": tutors, "policy": pol, "outcomes": OUTCOMES,
            "demo": bool(rows) and all(r["src"] == "demo" for r in rows if r["status"] != "ochiq"),
            "definitions": {"sla": f"Birinchi bog'lanish {pol['sla_days']} ish kuni ichida (har qanday qayd etilgan urinish, «javob bermadi» ham)",
                            "reeng": f"Bog'lanishdan keyin {pol['reengage_days']} kun ichida LMS'da faollik (oynasi tugaganlar orasida)",
                            "median": "Keys ochilganidan birinchi bog'lanishgacha (soat, median)"}}


# =============================================================================================
# Namuna (sun'iy) keyslar — demo uchun, src='demo'
# =============================================================================================
def seed(con) -> int:
    """LRS namunasi bayroqlaridan sun'iy keyslar (o'tgan 3 hafta): yopilgan (natijali), jarayonda, ochiq (bir qismi SLA'dan o'tgan). Testlarda
    ishlatiladigan tyutorlar (eng kichik id'lar) ishlatilmaydi."""
    global _con
    old = _con
    _con = con
    try:
        fl = flagged()
        tut = [r for r in db.rows(con, "SELECT id, faculty_id FROM users WHERE role='tyutor' AND COALESCE(active,1)!=0 ORDER BY id")][4:]
        if not fl or not tut:
            con.execute("INSERT OR REPLACE INTO ok_meta(k,v) VALUES('seed_v1','0')"); con.commit(); return 0
        now = _now()
        n = 0
        fac = {r["id"]: r["faculty_id"] for r in db.rows(con, f"SELECT id, faculty_id FROM students WHERE id IN ({','.join(map(str, fl)) or '0'})")}
        outs = ["gaplashildi"] * 5 + ["javob_bermadi"] * 3 + ["uchrashildi"] * 2 + ["boshqa"]
        for sid, f in sorted(fl.items()):
            R = random.Random(sid * 7919)
            x = R.random()
            pool = [t for t in tut if t["faculty_id"] == fac.get(sid)] or tut
            owner = None if R.random() < 0.12 else R.choice(pool)["id"]
            if x < 0.35:
                op = now - dt.timedelta(days=R.randint(16, 24), hours=R.randint(0, 8))
                fc = op + dt.timedelta(hours=R.choice([3, 8, 20, 30, 44, 70, 100]))
                cl = fc + dt.timedelta(days=R.randint(0, 3), hours=R.randint(1, 6))
                oc = R.choice(outs)
                status, ns = "yopilgan", (cl + dt.timedelta(days=7)).date().isoformat()
                owner = owner or R.choice(pool)["id"]
            elif x < 0.65:
                op = now - dt.timedelta(days=R.randint(3, 9), hours=R.randint(0, 8))
                fc, cl, oc = op + dt.timedelta(hours=R.choice([2, 6, 18, 26, 40, 60])), None, None
                status, ns = "jarayonda", (now + dt.timedelta(days=R.randint(1, 6))).date().isoformat()
                owner = owner or R.choice(pool)["id"]
            else:
                op = now - dt.timedelta(days=R.randint(0, 5), hours=R.randint(0, 20))
                fc = cl = oc = ns = None
                status = "ochiq"
            due = add_workdays(op, DEFAULTS["sla_days"])
            if fc and fc > now: fc = now - dt.timedelta(hours=1)
            cid = con.execute("""INSERT INTO ok_cases(student_id,status,owner_user,opened_at,sla_due,first_contact_at,last_contact_at,contacts,closed_at,closed_by,
                                 outcome,outcome_note,next_step,reasons,courses,level,risk,src,assigned_at,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (sid, status, owner, _iso(op), _iso(due), _iso(fc), _iso(cl or fc), (1 if fc else 0) + (1 if cl else 0), _iso(cl), owner if cl else None,
                               oc, "Telefon o'chirilgan, Telegram orqali yozildi" if oc == "boshqa" else None, ns,
                               json.dumps(f["reasons"], ensure_ascii=False), json.dumps(f["courses"], ensure_ascii=False, sort_keys=True), f["level"], f["risk"],
                               "demo", _iso(op) if owner else None, _iso(now))).lastrowid
            con.execute("INSERT INTO ok_log(case_id,ts,user_id,user_name,action,note) VALUES(?,?,?,?,?,?)", (cid, _iso(op), None, "Tizim", "ochildi", "namuna"))
            if fc: con.execute("INSERT INTO ok_log(case_id,ts,user_id,user_name,action,outcome,note) VALUES(?,?,?,?,?,?,?)",
                               (cid, _iso(fc), owner, "Tyutor (namuna)", "bog'lanildi", "javob_bermadi" if oc == "javob_bermadi" else "gaplashildi", ""))
            if cl: con.execute("INSERT INTO ok_log(case_id,ts,user_id,user_name,action,outcome,note,next_step) VALUES(?,?,?,?,?,?,?,?)",
                               (cid, _iso(cl), owner, "Tyutor (namuna)", "yopildi", oc, "", ns))
            n += 1
        con.execute("INSERT OR REPLACE INTO ok_meta(k,v) VALUES('seed_v1', ?)", (_iso(now),))
        con.execute("INSERT OR REPLACE INTO ok_meta(k,v) VALUES('anchor', ?)", (LA.monday(now.date()).isoformat(),))
        con.commit()
        print(f"Keyslar namuna: {n} ta sun'iy keys")
        return n
    finally:
        _con = old

def redate(con, today: dt.date | None = None) -> int:
    """Namuna keyslar sanalarini butun haftalarga surish (LRS namunasi bilan bir xil g'oya) — faqat src='demo'."""
    r = db.one(con, "SELECT v FROM ok_meta WHERE k='anchor'")
    if not r: return 0
    cur = LA.monday(today or clock.today())
    weeks = (cur - dt.date.fromisoformat(r["v"])).days // 7
    if weeks <= 0: return 0
    n = f"+{7 * weeks} days"
    for col in ("opened_at", "sla_due", "first_contact_at", "last_contact_at", "closed_at", "assigned_at"):
        con.execute(f"UPDATE ok_cases SET {col}=strftime('%Y-%m-%dT%H:%M:%S', {col}, '{n}') WHERE src='demo' AND {col} IS NOT NULL")
    con.execute(f"UPDATE ok_cases SET next_step=date(next_step, '{n}') WHERE src='demo' AND next_step IS NOT NULL")
    con.execute(f"UPDATE ok_log SET ts=strftime('%Y-%m-%dT%H:%M:%S', ts, '{n}') WHERE case_id IN (SELECT id FROM ok_cases WHERE src='demo')")
    con.execute("INSERT OR REPLACE INTO ok_meta(k,v) VALUES('anchor', ?)", (cur.isoformat(),))
    con.commit()
    return weeks


# =============================================================================================
# Fon: har 10 daqiqada sinxronizatsiya (masofaviy bo'limi yoqilgan bo'lsa) va avtomatik eslatmalar (app/tajriba.py — yoqilganlari)
# =============================================================================================
async def poller():
    import asyncio
    from . import modules as MODS
    await asyncio.sleep(90)
    while True:
        try:
            if MODS.on("masofaviy"):
                await asyncio.to_thread(sync)
                from . import tajriba as TJ
                await asyncio.to_thread(TJ.run_due)
        except Exception as e:
            print("keyslar poller:", repr(e))
        await asyncio.sleep(600)


# =============================================================================================
# HTTP
# =============================================================================================
@router.get(P)
def api_list(request: Request, status: str = "faol", owner: str = "", q: str = "", offset: int = 0, limit: int = 50):
    c = C(request); guard(c, "ro'yxat", LIST_ROLES, f"{status} {owner}".strip())
    return list_cases(c, status, owner, q, offset, limit)

@router.get(P + "/metrics")
def api_metrics(request: Request, since: str = ""):
    """Bo'lim — hammasi; tyutor — faqat o'zi; rektor / o'quv prorektori — jamlangan (talaba ismi yo'q, tyutorlar bo'yicha sonlar)."""
    c = C(request); guard(c, "ko'rsatkichlar", METRIC_ROLES)
    s = since[:10] if since else None
    if s:
        try: dt.date.fromisoformat(s)
        except ValueError: raise HTTPException(400, "since: YYYY-MM-DD")
    return metrics_data(s, owner=c.user["id"] if c.role.key == TUT else None)

@router.get(P + "/{cid}")
def api_case(cid: int, request: Request):
    c = C(request); guard(c, "keys kartasi", LIST_ROLES, f"keys #{cid}")
    r = _case(c, cid)
    st = _students([r["student_id"]]).get(r["student_id"])
    return view(c, r, st, _users([r["owner_user"]]), _now(), policy(), full=True)

@router.get(P + "/{cid}/tyutorlar")
def api_cands(cid: int, request: Request):
    c = C(request); guard(c, "tyutor nomzodlari", DEPT, f"keys #{cid}")
    return candidates(c, cid)

class AssignIn(BaseModel):
    tutor_id: int
    force: bool = False
    note: str = Field("", max_length=500)

@router.post(P + "/{cid}/assign")
def api_assign(cid: int, body: AssignIn, request: Request):
    c = C(request); guard(c, "biriktirish", DEPT, f"keys #{cid} → #{body.tutor_id}")
    return assign(c, cid, body.tutor_id, body.force, body.note)

class OutIn(BaseModel):
    outcome: str = Field("", max_length=30)
    note: str = Field("", max_length=500)
    next_step: str = Field("", max_length=10)

@router.post(P + "/{cid}/contact")
def api_contact(cid: int, body: OutIn, request: Request):
    c = C(request); guard(c, "bog'lanish", LIST_ROLES, f"keys #{cid}")
    return contact(c, cid, body.outcome, body.note, body.next_step)

@router.post(P + "/{cid}/close")
def api_close(cid: int, body: OutIn, request: Request):
    c = C(request); guard(c, "yopish", LIST_ROLES, f"keys #{cid}")
    return close(c, cid, body.outcome, body.note, body.next_step)

@router.post(P + "/sync")
def api_sync(request: Request):
    c = C(request); guard(c, "sinxronizatsiya", DEPT)
    return sync()

@router.get("/api/ortda/keys-qoidalar")
def api_policy(request: Request):
    c = C(request); guard(c, "keys qoidalari", LIST_ROLES + LEAD)
    return {"policy": policy(), "meta": [{"k": k, "label": lb, "min": lo, "max": hi} for k, _, lb, (lo, hi) in POLICY], "can_edit": c.role.key == HEAD,
            "rule_inputs": list(LA.RULE_INPUTS), "note": NOTE_DEMO}

@router.post("/api/ortda/keys-qoidalar")
def api_policy_set(body: dict, request: Request):
    c = C(request); guard(c, "keys qoidalarini o'zgartirish", (HEAD,))
    lim = {k: (lo, hi) for k, _, _, (lo, hi) in POLICY}
    ch = []
    with _lock:
        for k, v in (body or {}).items():
            if k not in lim: raise HTTPException(400, f"Noma'lum qoida: {k}")
            try: v = int(v)
            except (TypeError, ValueError): raise HTTPException(400, f"{k}: butun son kerak")
            lo, hi = lim[k]
            if not lo <= v <= hi: raise HTTPException(400, f"{k}: {lo}–{hi} oralig'ida bo'lishi kerak")
            _con.execute("INSERT OR REPLACE INTO ok_policy(k,v) VALUES(?,?)", (k, v)); ch.append(f"{k}={v}")
        _con.commit()
    rbac.audit(_con, c, "keyslar: qoidalar", RES, True, ", ".join(ch))
    return {"ok": True, "policy": policy()}
