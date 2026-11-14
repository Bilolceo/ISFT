"""Haftalik ritm — kogorta (guruh) bo'yicha kurs taqvimi: darslar har hafta chiqariladi, har birining muddati bor (docs/keyslar.md).

Nima uchun: onlayn ta'limdagi asosiy yo'qotish — vaqtni boshqarish (Bettinger va b., AER 2017). Qat'iy haftalik muddatlar talabaga «bu hafta nima
qilaman» degan aniq javob beradi, «Ortda qolganlar» esa kechikishni shu muddatlar bo'yicha hisoblaydi.

Taqvim manbai (ustunlik tartibida):
  1. lrs_cohort(kurs, guruh)   — shu guruh uchun bo'lim o'rnatgan boshlanish sanasi / haftalar soni / alohida muddatlar;
  2. lrs_cohort(kurs, 0)       — kurs bo'yicha umumiy sozlama;
  3. lrs_plan / semestr boshi  — avvalgi (ortda.calendar) qoida.
Standart: darslar haftalarga teng taqsimlanadi (lrs_analytics.schedule), dars o'z haftasining boshida chiqadi, muddati — o'sha hafta oxiri
(yakshanba). Kutilgan progress (ortda) = muddati o'tgan darslar (grace_weeks imtiyozi bilan; standart 1 — avvalgi hisob bilan aynan bir xil).

Ruxsat: ko'rish — «Ortda qolganlar» ro'yxat rollari (bo'lim, tyutor, o'qituvchi — o'z kursi); o'zgartirish — faqat bo'lim (masofaviy,
masofaviy_xodim), audit jurnalida.
"""
from __future__ import annotations
import datetime as dt, json, threading
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac, lrs as L, lrs_analytics as LA
from .rbac import Ctx

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/ortda/taqvim"

SCHEMA = """
CREATE TABLE IF NOT EXISTS lrs_cohort(course_ref TEXT, group_id INT, start TEXT, weeks INT, dues TEXT, updated TEXT, updated_by TEXT,
  PRIMARY KEY(course_ref, group_id));
"""
WD = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


def init(con):
    con.executescript(SCHEMA); con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def stamp() -> str:
    r = db.one(_con, "SELECT MAX(updated) u, COUNT(*) n FROM lrs_cohort") if _con is not None else None
    return f"{(r or {}).get('u')}|{(r or {}).get('n')}"

def _date(v) -> dt.date | None:
    try: return dt.date.fromisoformat(str(v or "")[:10])
    except ValueError: return None


# =============================================================================================
# Taqvim (kurs × guruh)
# =============================================================================================
def cal_for(co: dict, gid: int | None) -> dict:
    """{start, weeks, dues: {dars ref: sana}, src}. src: «guruh» | «kurs» | «reja» (lrs_plan yoki semestr boshi)."""
    from . import ortda as ORT
    rows = {r["group_id"]: r for r in db.rows(_con, "SELECT * FROM lrs_cohort WHERE course_ref=? AND group_id IN (?, 0)", (co["ref"], int(gid or 0)))}
    base_start, base_weeks = ORT.calendar(co)
    out = {"start": base_start, "weeks": base_weeks, "dues": {}, "src": "reja"}
    for g, src in ((0, "kurs"), (int(gid or 0), "guruh")):
        r = rows.get(g)
        if not r or (src == "guruh" and not g): continue
        out["start"] = _date(r["start"]) or out["start"]
        out["weeks"] = int(r["weeks"] or out["weeks"])
        try: d = json.loads(r["dues"] or "{}")
        except ValueError: d = {}
        out["dues"].update({k: v for k, v in ((k, _date(v)) for k, v in (d or {}).items()) if v})
        out["src"] = src
    return out

def plan(co: dict, gid: int | None, lessons: list[dict] | None = None) -> dict:
    """Guruh uchun darslar jadvali: {start, weeks, src, items: [{ref, code, title, week, release, due}]} (taqvim tartibida)."""
    from . import ortda as ORT
    ls = lessons if lessons is not None else ORT.lessons_of(co)
    cal = cal_for(co, gid)
    ix = {l["ref"]: i for i, l in enumerate(ls)}
    ov = {ix[k]: v for k, v in cal["dues"].items() if k in ix}
    sched = LA.schedule(len(ls), cal["start"], cal["weeks"], ov)
    items = [{"ref": l["ref"], "code": l.get("code") or l["ref"], "title": l.get("title") or l["ref"], **s} for l, s in zip(ls, sched)]
    return {"start": cal["start"], "weeks": cal["weeks"], "src": cal["src"], "items": items, "sched": sched}

def due_label(d: dt.date) -> str:
    return f"{d.day:02d}.{d.month:02d} ({WD[d.weekday()]})"


# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def _groups_of(co: dict) -> list[dict]:
    from . import ortda as ORT
    sids = ORT.enrolled(co)
    if not sids: return []
    return db.rows(_con, f"""SELECT g.id, g.name, COUNT(s.id) n FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id IN ({','.join(map(str, sids))})
                            GROUP BY g.id ORDER BY g.name""")

@router.get(P)
def api_get(request: Request, course: str, group: int = 0):
    from . import ortda as ORT
    c = C(request); ORT.guard(c, "kurs taqvimi", ORT.LIST_ROLES, f"{course} · guruh #{group}")
    co = ORT._course(c, course)
    groups = _groups_of(co)
    if c.role.key not in ORT.DEPT:          # tyutor / o'qituvchi — faqat o'z ko'lamidagi guruhlar
        vis = ORT.visible_students(c) or set()
        own = {r["group_id"] for r in db.rows(_con, f"SELECT DISTINCT group_id FROM students WHERE id IN ({','.join(map(str, vis)) or '0'})")}
        groups = [g for g in groups if g["id"] in own]
        if group and group not in own: raise rbac.AccessDenied("⛔ Bu guruh sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    p = plan(co, group)
    today = clock.today()
    return {"course": ORT._pub_course(co), "group": group, "groups": groups, "start": p["start"].isoformat(), "weeks": p["weeks"], "src": p["src"],
            "week": LA.week_no(p["start"], today), "today": today.isoformat(), "can_edit": c.role.key in ORT.DEPT,
            "grace_weeks": L.policy()["grace_weeks"],
            "items": [{"ref": x["ref"], "code": x["code"], "title": x["title"], "week": x["week"], "release": x["release"].isoformat(), "due": x["due"].isoformat(),
                       "due_label": due_label(x["due"])} for x in p["items"]]}

class CalIn(BaseModel):
    course: str = Field(..., max_length=20)
    group_id: int = 0
    start: str = Field("", max_length=10)
    weeks: int = 0
    dues: dict = {}
    reset: bool = False

@router.post(P)
def api_set(body: CalIn, request: Request):
    """Bo'lim: kurs (group_id=0) yoki guruh taqvimi — boshlanish sanasi, haftalar soni, alohida dars muddatlari. reset — guruh sozlamasini o'chirish."""
    from . import ortda as ORT
    c = C(request); ORT.guard(c, "kurs taqvimini o'zgartirish", ORT.DEPT, f"{body.course} · guruh #{body.group_id}")
    co = ORT._course(c, body.course)
    gid = int(body.group_id or 0)
    if gid and gid not in {g["id"] for g in _groups_of(co)}: raise HTTPException(400, "Bu guruh shu kursda o'qimaydi")
    if body.reset:
        with _lock:
            _con.execute("DELETE FROM lrs_cohort WHERE course_ref=? AND group_id=?", (co["ref"], gid)); _con.commit()
        ORT._CACHE.clear()
        rbac.audit(_con, c, "ortda qolganlar: taqvim standartga qaytarildi", ORT.RES, True, f"{co['ref']} · guruh #{gid}")
        return {"ok": True}
    start = _date(body.start)
    if body.start and not start: raise HTTPException(400, "Boshlanish sanasi: YYYY-MM-DD")
    lim = {k: (lo, hi) for k, _, _, (lo, hi) in LA.POLICY}["weeks"]
    weeks = int(body.weeks or 0)
    if weeks and not lim[0] <= weeks <= lim[1]: raise HTTPException(400, f"Haftalar soni {lim[0]}–{lim[1]} oralig'ida")
    ls = ORT.lessons_of(co)
    refs = {l["ref"] for l in ls}
    dues = {}
    for k, v in (body.dues or {}).items():
        if k not in refs: raise HTTPException(400, f"Noma'lum dars: {str(k)[:20]}")
        if v in (None, ""): continue
        d = _date(v)
        if not d: raise HTTPException(400, f"{k}: muddat YYYY-MM-DD bo'lishi kerak")
        dues[k] = d.isoformat()
    cur = cal_for(co, gid)
    s0 = start or cur["start"]
    # muddat dars chiqarilishidan oldin bo'lolmaydi (aks holda talaba imkonsiz muddat oladi)
    rel = {l["ref"]: s["release"] for l, s in zip(ls, LA.schedule(len(ls), s0, weeks or cur["weeks"]))}
    bad = [k for k, v in dues.items() if dt.date.fromisoformat(v) < rel.get(k, dt.date.min)]
    if bad: raise HTTPException(400, f"Muddat dars chiqarilishidan oldin bo'lolmaydi: {', '.join(bad[:5])}")
    with _lock:
        _con.execute("INSERT OR REPLACE INTO lrs_cohort(course_ref,group_id,start,weeks,dues,updated,updated_by) VALUES(?,?,?,?,?,?,?)",
                     (co["ref"], gid, s0.isoformat(), weeks or cur["weeks"], json.dumps(dues), clock.now().replace(microsecond=0).isoformat(timespec="seconds"),
                      c.user["full_name"]))
        _con.commit()
    ORT._CACHE.clear()
    rbac.audit(_con, c, "ortda qolganlar: kurs taqvimi", ORT.RES, True, f"{co['ref']} · guruh #{gid} · {s0} · {weeks or cur['weeks']} hafta · {len(dues)} muddat")
    return {"ok": True}
