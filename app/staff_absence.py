"""Xodimlar ta'tili va yo'qligi (Kadrlar bo'limi): xizmat safari, mehnat ta'tili, kasallik varaqasi, o'quv ta'tili.

Nima qiladi:
  * Kadrlar bo'limi xodim/o'qituvchining yo'qligini ro'yxatga oladi (tur, sanalar, izoh), asos hujjatini yuklaydi (fayl mazmuni
    app/filecheck.py bilan tekshiriladi, data/staffabs_files/ ichida tasodifiy nom bilan, sha256) va mehnat ta'tili uchun Hujjatlar
    markazidagi «leave_order» buyruq loyihasini yaratadi yoki mavjudini (reg. raqami bo'yicha) bog'laydi.
  * Ta'sir: dars jadvali (schedule: teacher_id, weekday 0=Du…5=Sh, slot 1..6) haftalik shablon. Yo'qlik oralig'idagi har bir sana va shu kundagi
    darslar — «o'rinbosar kerak» ro'yxati. O'rinbosar tavsiyasi: o'sha kafedra, o'sha para bo'sh, o'sha kuni yo'q emas, boshqa o'rinbosarlik yo'q;
    fan mos kelsa — birinchi. Kafedrada mos odam kam bo'lsa — boshqa kafedradan o'sha fanni o'qitadiganlar ("boshqa kafedra" belgisi bilan).
  * Kafedra mudiri o'z kafedrasi darslariga o'rinbosar tayinlaydi (bitta sana yoki shu darsning yo'qlikdagi barcha sanalariga).
    Akademik bo'lim jadval o'zgarishlarini (tayinlangan va ochiq qolgan darslar) ko'radi.
  * Tahlil: kafedra/oy kesimida yo'qlik kunlari, tez-tez kasallik varaqasi, bir kafedrada bir vaqtda yo'qliklar.
RBAC (rbac.ROLES o'zgartirilmaydi — modul ichidagi qoida):
  kadrlar — to'liq (yaratish, tahrir, bekor qilish, asos hujjat, buyruq); kafedra mudiri — o'z kafedrasi (ko'rish, o'rinbosar tayinlash);
  akademik — barcha yo'qliklar ta'siri va jadval o'zgarishlari (ko'rish); rektor, o'quv prorektori — ro'yxat va tahlil (ko'rish);
  boshqalar (o'qituvchi) — faqat o'zining yo'qligi va o'zi o'rinbosar bo'lgan darslar. Asos hujjat va izoh — faqat kadrlar va xodimning o'zi.
Har bir ko'rish, o'zgartirish, yuklash/yuklab olish va rad etilgan urinish audit jurnaliga yoziladi (resurs "staff_absence").
"""
import datetime as dt, json, mimetypes, os, re, uuid
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from . import db, rbac, services as S, filecheck as FC
from .rbac import AccessDenied, Ctx, ROLES

ROOT = Path(__file__).resolve().parent.parent
FILES = Path(os.getenv("ISFT_CORE_STAFFABS_DIR") or db.DATA_DIR / "staffabs_files")
MAX_BYTES = 10 * 1024 * 1024
RES = "staff_absence"
ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png", "doc", "docx"}

router = APIRouter()
_con = None
_ctx = None

KINDS = {"safar": "Xizmat safari (komandirovka)", "mehnat": "Mehnat ta'tili", "kasallik": "Kasallik varaqasi", "oquv": "O'quv ta'tili", "boshqa": "Boshqa"}
FULL = {"kadrlar"}
VIEW_ALL = {"akademik", "rektor", "prorektor_oquv"}
DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
SLOTS = {1: "08:30", 2: "10:00", 3: "11:30", 4: "13:30", 5: "15:00", 6: "16:30"}
TEACH_UNIT = "Professor-o'qituvchi"
MON = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS staff_absences(id INTEGER PRIMARY KEY, staff_id INT, teacher_id INT, full_name TEXT, position TEXT, unit_name TEXT,
  department_id INT, kind TEXT, start TEXT, end TEXT, note TEXT, status TEXT DEFAULT 'faol', order_doc_id INT, order_reg_no TEXT,
  created_by INT, created_by_name TEXT, created_at TEXT, updated_at TEXT, cancel_note TEXT);
CREATE INDEX IF NOT EXISTS ix_sabs_t ON staff_absences(teacher_id, start, end);
CREATE INDEX IF NOT EXISTS ix_sabs_d ON staff_absences(department_id, start);
CREATE TABLE IF NOT EXISTS staff_abs_files(id INTEGER PRIMARY KEY, absence_id INT, name TEXT, stored TEXT UNIQUE, size INT, ext TEXT, mime TEXT,
  sha256 TEXT, scan TEXT, uploader_id INT, uploader_name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS staff_subs(id INTEGER PRIMARY KEY, absence_id INT, sched_id INT, date TEXT, sub_teacher_id INT, sub_name TEXT, note TEXT,
  assigned_by INT, assigned_by_name TEXT, assigned_at TEXT, UNIQUE(absence_id, sched_id, date));
CREATE INDEX IF NOT EXISTS ix_ssubs_t ON staff_subs(sub_teacher_id, date);
CREATE TABLE IF NOT EXISTS staffabs_meta(k TEXT PRIMARY KEY, v TEXT);
"""

def _now(): return dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
def _today() -> dt.date: return S.TODAY
def _d(s) -> dt.date: return dt.date.fromisoformat(str(s)[:10])
def _dmy(s) -> str: return _d(s).strftime("%d.%m.%Y") if s else ""
def _short(n): return (n or "").split(":", 1)[-1].strip()
def _brief(n):
    if ":" not in (n or ""): return n or ""        # shaxssiz bo'lim akkaunti ("Kadrlar bo'limi")
    w = _short(n).split()
    return f"{w[0]} {w[1][0]}." if len(w) > 1 and w[1][:1].isalpha() else (w[0] if w else "")
def _subj(s): return re.sub(r"^(Ma'ruza|Amaliy|Seminar|Laboratoriya):\s*", "", s or "").strip()
def _days(a, b): return (b - a).days + 1

def init(con):
    con.executescript(SCHEMA); con.commit()
    FILES.mkdir(parents=True, exist_ok=True)
    try:
        seed_demo(con)
    except Exception as e:          # demo ma'lumot tayyorlanmasa ham server ishlashi kerak
        import traceback; traceback.print_exc(); print("staff_absence.seed xatosi:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _audit(c, action, ok=True, detail=""):
    rbac.audit(_con, c, action, RES, ok, detail)

# ---------------------------------------------------------------------------------------------
# Kim nimani ko'radi
# ---------------------------------------------------------------------------------------------
def mode(c: Ctx) -> str:
    r = c.role.key
    if r in FULL: return "full"
    if r in VIEW_ALL: return "all"
    if r == "kafedra" and c.user.get("department_id"): return "kaf"
    return "own"

def _own_ids(con, c: Ctx) -> tuple[int | None, list[int]]:
    """Foydalanuvchiga mos o'qituvchi (teacher_id) va xodim (staff.id) yozuvlari — ism bo'yicha."""
    tid = c.user.get("teacher_id")
    name = _short(c.user.get("full_name"))
    sids = [r["id"] for r in db.rows(con, "SELECT id FROM staff WHERE full_name=?", (name,))] if name else []
    if not tid and name:
        t = db.rows(con, "SELECT id FROM teachers WHERE full_name=?", (name,))
        if len(t) == 1: tid = t[0]["id"]
    return tid, sids

def _where(c: Ctx, a="a") -> tuple[str, list]:
    m = mode(c)
    if m in ("full", "all"): return "1=1", []
    if m == "kaf": return f"{a}.department_id=?", [int(c.user["department_id"])]
    tid, sids = _own_ids(_con, c)
    ors, args = [], []
    if tid: ors.append(f"{a}.teacher_id=?"); args.append(tid)
    if sids: ors.append(f"{a}.staff_id IN ({','.join('?' * len(sids))})"); args += sids
    return ("(" + " OR ".join(ors) + ")" if ors else "0"), args

def _can_see(c: Ctx, a: dict) -> bool:
    w, args = _where(c, "a")
    return bool(_con.execute(f"SELECT 1 FROM staff_absences a WHERE a.id=? AND {w}", (a["id"], *args)).fetchone())

def _is_own(c: Ctx, a: dict) -> bool:
    tid, sids = _own_ids(_con, c)
    return bool((tid and a.get("teacher_id") == tid) or a.get("staff_id") in sids)

def _can_assign(c: Ctx, a: dict) -> bool:
    return c.role.key == "kafedra" and bool(a.get("department_id")) and int(c.user.get("department_id") or 0) == a["department_id"]

def _need_full(c: Ctx, action: str, detail=""):
    if mode(c) != "full":
        _audit(c, f"xodimlar ta'tili: {action}", False, detail)
        raise AccessDenied("⛔ Xodimlar yo'qligini faqat Kadrlar bo'limi ro'yxatga oladi va o'zgartiradi. So'rov audit jurnaliga yozildi.")

def _dept_names(con) -> dict: return {r["id"]: r["name"] for r in db.rows(con, "SELECT id, name FROM departments")}

# ---------------------------------------------------------------------------------------------
# Xodim → o'qituvchi (dars jadvali bilan bog'lash)
# ---------------------------------------------------------------------------------------------
def staff_teacher(con, staff: dict) -> dict | None:
    """staff (unit='Professor-o'qituvchi') → teachers: avval ism + lavozim, keyin seed tartibi (bir xil ismlilar uchun)."""
    if staff["unit"] != TEACH_UNIT: return None
    cands = db.rows(con, "SELECT * FROM teachers WHERE full_name=? AND position=?", (staff["full_name"], staff["position"]))
    if len(cands) == 1: return cands[0]
    rank = con.execute("SELECT COUNT(*) FROM staff WHERE unit=? AND id<=?", (TEACH_UNIT, staff["id"])).fetchone()[0]
    t = db.one(con, "SELECT * FROM teachers WHERE id=?", (rank,))
    return t if t and t["full_name"] == staff["full_name"] else (cands[0] if cands else None)

# ---------------------------------------------------------------------------------------------
# Ta'sir: darslar, o'rinbosarlar
# ---------------------------------------------------------------------------------------------
def _dates(a: dict, lo: dt.date | None = None, hi: dt.date | None = None):
    d, e = _d(a["start"]), _d(a["end"])
    if lo and lo > d: d = lo
    if hi and hi < e: e = hi
    while d <= e:
        if d.weekday() < 6: yield d
        d += dt.timedelta(days=1)

def _sched_of(con, teacher_id: int) -> dict:
    by = {}
    for r in db.rows(con, """SELECT sc.id, sc.weekday, sc.slot, sc.subject, sc.group_id, g.name grp, r.name room FROM schedule sc
                             LEFT JOIN groups_ g ON g.id=sc.group_id LEFT JOIN rooms r ON r.id=sc.room_id WHERE sc.teacher_id=? ORDER BY sc.slot""", (teacher_id,)):
        by.setdefault(r["weekday"], []).append(r)
    return by

def lessons(con, a: dict, lo=None, hi=None) -> list[dict]:
    if not a.get("teacher_id") or a.get("status") == "bekor": return []
    by = _sched_of(con, a["teacher_id"]); today = _today()
    subs = {(s["sched_id"], s["date"]): s for s in db.rows(con, "SELECT * FROM staff_subs WHERE absence_id=?", (a["id"],))}
    out = []
    for d in _dates(a, lo, hi):
        for r in by.get(d.weekday(), []):
            s = subs.get((r["id"], d.isoformat()))
            out.append({"sched_id": r["id"], "date": d.isoformat(), "weekday": DAYS[d.weekday()], "slot": r["slot"], "time": SLOTS.get(r["slot"], ""),
                        "subject": r["subject"], "group": r["grp"], "room": (r["room"] or "").split(" ·")[0], "past": d < today,
                        "sub": {"id": s["id"], "teacher_id": s["sub_teacher_id"], "name": s["sub_name"], "note": s["note"],
                                "by": _brief(s["assigned_by_name"]), "at": s["assigned_at"]} if s else None})
    return out

def _busy(con, teacher_id: int, date: str, slot: int, skip_abs: int | None = None) -> str | None:
    """O'qituvchi shu sana va parada band bo'lsa — sababi (matn); bo'sh bo'lsa None."""
    wd = _d(date).weekday()
    if con.execute("SELECT 1 FROM schedule WHERE teacher_id=? AND weekday=? AND slot=?", (teacher_id, wd, slot)).fetchone():
        return "shu parada o'z darsi bor"
    if con.execute("SELECT 1 FROM staff_absences WHERE teacher_id=? AND status='faol' AND start<=? AND end>=?", (teacher_id, date, date)).fetchone():
        return "shu kuni o'zi ham yo'q (ta'til/safar/kasallik)"
    q = """SELECT 1 FROM staff_subs ss JOIN schedule sc ON sc.id=ss.sched_id JOIN staff_absences a ON a.id=ss.absence_id
           WHERE ss.sub_teacher_id=? AND ss.date=? AND sc.slot=? AND a.status='faol'"""
    if con.execute(q, (teacher_id, date, slot)).fetchone(): return "shu parada boshqa darsga o'rinbosar"
    return None

def suggest(con, a: dict, sched_id: int, date: str, limit: int = 6) -> list[dict]:
    r = db.one(con, "SELECT * FROM schedule WHERE id=?", (sched_id,))
    if not r: return []
    subj = _subj(r["subject"]); wd = _d(date).weekday(); dn = _dept_names(con)
    teaches = {}
    for x in db.rows(con, "SELECT teacher_id, subject FROM schedule UNION SELECT teacher_id, subject FROM teacher_groups"):
        teaches.setdefault(x["teacher_id"], set()).add(_subj(x["subject"]))
    load = {x["teacher_id"]: x["n"] for x in db.rows(con, "SELECT teacher_id, COUNT(*) n FROM schedule WHERE weekday=? GROUP BY teacher_id", (wd,))}
    grp_t = {x["teacher_id"] for x in db.rows(con, "SELECT teacher_id FROM teacher_groups WHERE group_id=?", (r["group_id"],))}
    def cand(t, other):
        if t["id"] == a.get("teacher_id") or _busy(con, t["id"], date, r["slot"]): return None
        same = subj in teaches.get(t["id"], ())
        if other and not same: return None
        why = (["shu fanni o'qitadi"] if same else []) + (["guruhni taniydi"] if t["id"] in grp_t else []) + [f"shu kuni {load.get(t['id'], 0)} ta darsi bor"]
        return {"teacher_id": t["id"], "name": t["full_name"], "position": t["position"], "kafedra": dn.get(t["department_id"], ""), "other_kafedra": other,
                "same_subject": same, "score": (20 if same else 0) + (4 if t["id"] in grp_t else 0) - load.get(t["id"], 0) - (15 if other else 0), "why": why}
    out = [x for x in (cand(t, False) for t in db.rows(con, "SELECT * FROM teachers WHERE department_id=?", (a.get("department_id") or -1,))) if x]
    if sum(1 for x in out if x["same_subject"]) < 2:
        out += [x for x in (cand(t, True) for t in db.rows(con, "SELECT * FROM teachers WHERE department_id IS NOT ? ", (a.get("department_id") or -1,))) if x]
    out.sort(key=lambda x: (-x["score"], x["name"]))
    return out[:limit]

# ---------------------------------------------------------------------------------------------
# Ko'rinishlar
# ---------------------------------------------------------------------------------------------
def _view(con, c: Ctx, a: dict, dn: dict, brief=True) -> dict:
    today = _today(); m = mode(c); priv = m == "full" or _is_own(c, a)
    s, e = _d(a["start"]), _d(a["end"])
    phase = "bekor" if a["status"] == "bekor" else "joriy" if s <= today <= e else "kelgusi" if s > today else "otgan"
    L = lessons(con, a)
    fut = [x for x in L if not x["past"]]
    v = {"id": a["id"], "name": a["full_name"], "position": a["position"], "unit": dn.get(a["department_id"]) and f"{dn[a['department_id']]} kafedrasi" or a["unit_name"],
         "department_id": a["department_id"], "teacher": bool(a["teacher_id"]), "kind": a["kind"], "kind_name": KINDS.get(a["kind"], a["kind"]),
         "start": a["start"], "end": a["end"], "days": _days(s, e), "status": a["status"], "phase": phase,
         "lessons": len(L), "lessons_future": len(fut), "covered_future": sum(1 for x in fut if x["sub"]),
         "uncovered_future": sum(1 for x in fut if not x["sub"]),
         "order": {"doc_id": a["order_doc_id"], "reg_no": a["order_reg_no"]} if a.get("order_reg_no") else None,
         "files": con.execute("SELECT COUNT(*) FROM staff_abs_files WHERE absence_id=?", (a["id"],)).fetchone()[0],
         "created_at": a["created_at"], "created_by": _brief(a["created_by_name"]),
         "note": a["note"] if priv else None, "cancel_note": a["cancel_note"] if priv else None,
         "can_edit": m == "full" and a["status"] == "faol", "can_assign": _can_assign(c, a) and a["status"] == "faol", "own": _is_own(c, a)}
    if not brief:
        v["lesson_list"] = L
        v["file_list"] = [{"id": f["id"], "name": f["name"], "size": f["size"], "ext": f["ext"], "at": f["created_at"], "by": _brief(f["uploader_name"]), "scan": f["scan"]}
                          for f in db.rows(con, "SELECT * FROM staff_abs_files WHERE absence_id=? ORDER BY id", (a["id"],))] if priv else []
        if a.get("order_doc_id"):
            d = db.one(con, "SELECT reg_no, status, file, created_by FROM documents WHERE id=?", (a["order_doc_id"],))
            if d: v["order"] = {"doc_id": a["order_doc_id"], "reg_no": d["reg_no"], "status": d["status"],
                                "file": d["file"] if (c.role.key == "rektor" or d["created_by"] == c.user["id"]) else None}
    return v

PERIODS = ("current", "upcoming", "active", "past", "all")

def list_absences(c: Ctx, period="active", kind="", dept=0, q="") -> dict:
    w, args = _where(c)
    today = _today().isoformat()
    pw = {"current": "a.start<=? AND a.end>=? AND a.status='faol'", "upcoming": "a.start>? AND a.status='faol'", "active": "a.end>=? AND a.status='faol'",
          "past": "(a.end<? OR a.status='bekor')", "all": "1=1"}[period if period in PERIODS else "active"]
    pa = [today, today] if period == "current" else [] if period == "all" else [today]
    ws, xs = [w, pw], [*args, *pa]
    if kind in KINDS: ws.append("a.kind=?"); xs.append(kind)
    if dept: ws.append("a.department_id=?"); xs.append(int(dept))
    if q.strip(): ws.append("(a.full_name LIKE ? OR a.unit_name LIKE ?)"); xs += [f"%{q.strip()[:60]}%"] * 2
    rows = db.rows(_con, f"SELECT a.* FROM staff_absences a WHERE {' AND '.join(ws)} ORDER BY a.status='bekor', a.start {'DESC' if period in ('past', 'all') else 'ASC'}, a.id LIMIT 300", xs)
    dn = _dept_names(_con)
    _audit(c, "xodimlar ta'tili: ro'yxat", True, f"{period}{' · ' + kind if kind else ''}{' · kaf ' + str(dept) if dept else ''} · {len(rows)} ta")
    return {"items": [_view(_con, c, a, dn) for a in rows], "mode": mode(c)}

def _get(con, aid: int) -> dict:
    a = db.one(con, "SELECT * FROM staff_absences WHERE id=?", (aid,))
    if not a: raise HTTPException(404, "Yozuv topilmadi")
    return a

def detail(c: Ctx, aid: int) -> dict:
    a = _get(_con, aid)
    ok = _can_see(c, a)
    _audit(c, "xodimlar ta'tili: ko'rish", ok, f"#{aid} {a['full_name']}")
    if not ok: raise AccessDenied("⛔ Bu yozuv sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    return _view(_con, c, a, _dept_names(_con), brief=False)

def needs(c: Ctx, days: int = 14) -> dict:
    """«O'rinbosar kerak»: bugundan `days` kun ichidagi o'rinbosarsiz darslar, kafedralar bo'yicha."""
    w, args = _where(c)
    lo = _today(); hi = lo + dt.timedelta(days=max(1, min(60, int(days))) - 1)
    rows = db.rows(_con, f"SELECT a.* FROM staff_absences a WHERE {w} AND a.status='faol' AND a.teacher_id IS NOT NULL AND a.start<=? AND a.end>=? ORDER BY a.start",
                   (*args, hi.isoformat(), lo.isoformat()))
    dn = _dept_names(_con); groups = {}
    for a in rows:
        for x in lessons(_con, a, lo, hi):
            g = groups.setdefault(a["department_id"] or 0, {"department_id": a["department_id"], "kafedra": dn.get(a["department_id"], "—"), "open": 0, "covered": 0, "items": []})
            g["covered" if x["sub"] else "open"] += 1
            g["items"].append({**x, "absence_id": a["id"], "teacher": a["full_name"], "kind": a["kind"], "kind_name": KINDS.get(a["kind"]),
                               "can_assign": _can_assign(c, a)})
    out = sorted(groups.values(), key=lambda g: (-g["open"], g["kafedra"]))
    for g in out: g["items"].sort(key=lambda x: (x["date"], x["slot"]))
    _audit(c, "xodimlar ta'tili: o'rinbosar kerak", True, f"{days} kun · {sum(g['open'] for g in out)} ta ochiq dars")
    return {"from": lo.isoformat(), "to": hi.isoformat(), "groups": out, "open": sum(g["open"] for g in out), "covered": sum(g["covered"] for g in out)}

def changes(c: Ctx, days: int = 14) -> dict:
    """Jadval o'zgarishlari (Akademik bo'lim): tayinlangan o'rinbosarlar va ochiq qolgan darslar; o'qituvchi uchun — o'zi o'rinbosar bo'lgan darslar."""
    lo = _today(); hi = lo + dt.timedelta(days=max(1, min(60, int(days))) - 1)
    m = mode(c)
    if m == "own":
        tid, _ = _own_ids(_con, c)
        rows = db.rows(_con, """SELECT ss.*, a.full_name absent, a.kind, sc.slot, sc.subject, g.name grp, r.name room FROM staff_subs ss
            JOIN staff_absences a ON a.id=ss.absence_id JOIN schedule sc ON sc.id=ss.sched_id LEFT JOIN groups_ g ON g.id=sc.group_id
            LEFT JOIN rooms r ON r.id=sc.room_id WHERE ss.sub_teacher_id=? AND a.status='faol' AND ss.date BETWEEN ? AND ? ORDER BY ss.date, sc.slot""",
                         (tid or -1, lo.isoformat(), hi.isoformat()))
        _audit(c, "xodimlar ta'tili: mening o'rinbosarligim", True, f"{len(rows)} ta")
        return {"from": lo.isoformat(), "to": hi.isoformat(), "mine": [{"date": x["date"], "weekday": DAYS[_d(x["date"]).weekday()], "slot": x["slot"],
                 "time": SLOTS.get(x["slot"]), "subject": x["subject"], "group": x["grp"], "room": (x["room"] or "").split(" ·")[0],
                 "absent": x["absent"], "kind_name": KINDS.get(x["kind"])} for x in rows], "items": []}
    w, args = _where(c)
    rows = db.rows(_con, f"SELECT a.* FROM staff_absences a WHERE {w} AND a.status='faol' AND a.teacher_id IS NOT NULL AND a.start<=? AND a.end>=? ORDER BY a.start",
                   (*args, hi.isoformat(), lo.isoformat()))
    dn = _dept_names(_con); items = []
    for a in rows:
        for x in lessons(_con, a, lo, hi):
            items.append({**x, "absence_id": a["id"], "teacher": a["full_name"], "kafedra": dn.get(a["department_id"], ""), "kind_name": KINDS.get(a["kind"])})
    items.sort(key=lambda x: (x["date"], x["slot"], x["group"] or ""))
    _audit(c, "xodimlar ta'tili: jadval o'zgarishlari", True, f"{len(items)} ta dars")
    return {"from": lo.isoformat(), "to": hi.isoformat(), "items": items, "mine": []}

def analytics(c: Ctx) -> dict:
    m = mode(c)
    if m == "own":
        _audit(c, "xodimlar ta'tili: tahlil", False)
        raise AccessDenied("⛔ Tahlil Kadrlar bo'limi, rahbariyat, Akademik bo'lim va kafedra mudirlari uchun. So'rov audit jurnaliga yozildi.")
    w, args = _where(c)
    today = _today(); dn = _dept_names(_con)
    rows = db.rows(_con, f"SELECT a.* FROM staff_absences a WHERE {w} AND a.status='faol'", args)
    # oylar: oxirgi 5 oy + joriy + keyingi oy
    m0 = dt.date(today.year, today.month, 1)
    months = []
    for k in range(-5, 2):
        y, mo = m0.year + (m0.month - 1 + k) // 12, (m0.month - 1 + k) % 12 + 1
        months.append(dt.date(y, mo, 1))
    def mend(d): return (dt.date(d.year + d.month // 12, d.month % 12 + 1, 1) - dt.timedelta(days=1))
    unit_of = lambda a: f"{dn[a['department_id']]} kafedrasi" if a["department_id"] in dn else (a["unit_name"] or "—")
    grid = {}
    for a in rows:
        s, e = _d(a["start"]), _d(a["end"])
        for i, mm in enumerate(months):
            lo, hi = max(s, mm), min(e, mend(mm))
            if lo <= hi:
                g = grid.setdefault(unit_of(a), {"unit": unit_of(a), "department_id": a["department_id"], "months": [0] * len(months), "by_kind": {}})
                g["months"][i] += _days(lo, hi); g["by_kind"][a["kind"]] = g["by_kind"].get(a["kind"], 0) + _days(lo, hi)
    by_unit = sorted(grid.values(), key=lambda g: (-sum(g["months"]), g["unit"]))
    # tez-tez kasallik varaqasi: oxirgi 180 kunda ≥2 marta yoki ≥10 kun
    since = (today - dt.timedelta(days=180)).isoformat()
    sick = {}
    for a in rows:
        if a["kind"] != "kasallik" or a["end"] < since: continue
        k = (a["staff_id"] or 0, a["full_name"])
        x = sick.setdefault(k, {"name": a["full_name"], "unit": unit_of(a), "count": 0, "days": 0, "last": a["start"]})
        x["count"] += 1; x["days"] += _days(_d(a["start"]), _d(a["end"])); x["last"] = max(x["last"], a["start"])
    frequent = sorted([x for x in sick.values() if x["count"] >= 2 or x["days"] >= 10], key=lambda x: (-x["count"], -x["days"]))
    # bir kafedrada bir vaqtda (bugundan boshlab) kesishgan yo'qliklar
    fut = [a for a in rows if a["end"] >= today.isoformat()]
    overlaps = []
    for i, a in enumerate(fut):
        for b in fut[i + 1:]:
            if unit_of(a) != unit_of(b) or a["id"] == b["id"]: continue
            lo, hi = max(a["start"], b["start"]), min(a["end"], b["end"])
            if lo <= hi:
                tot = _con.execute("SELECT COUNT(*) FROM teachers WHERE department_id=?", (a["department_id"],)).fetchone()[0] if a["department_id"] else None
                overlaps.append({"unit": unit_of(a), "from": lo, "to": hi, "days": _days(_d(lo), _d(hi)),
                                 "people": [{"name": a["full_name"], "kind_name": KINDS.get(a["kind"])}, {"name": b["full_name"], "kind_name": KINDS.get(b["kind"])}],
                                 "staff_total": tot})
    overlaps.sort(key=lambda x: x["from"])
    cur = [a for a in rows if a["start"] <= today.isoformat() <= a["end"]]
    _audit(c, "xodimlar ta'tili: tahlil", True, f"{len(rows)} ta yozuv")
    return {"months": [f"{MON[mm.month - 1]} {mm.year}" for mm in months], "current_month": 5, "by_unit": by_unit,
            "frequent_sick": frequent, "overlaps": overlaps,
            "kpi": {"absent_now": len(cur), "by_kind_now": {k: sum(1 for a in cur if a["kind"] == k) for k in KINDS},
                    "upcoming_14": sum(1 for a in rows if today.isoformat() < a["start"] <= (today + dt.timedelta(days=14)).isoformat()),
                    "teachers_now": sum(1 for a in cur if a["teacher_id"])}}

def meta(c: Ctx) -> dict:
    m = mode(c); dn = _dept_names(_con)
    deps = [{"id": k, "name": v} for k, v in sorted(dn.items())] if m in ("full", "all") else \
           [{"id": int(c.user["department_id"]), "name": dn.get(int(c.user["department_id"]), "")}] if m == "kaf" else []
    return {"mode": m, "kinds": KINDS, "departments": deps, "today": _today().isoformat(), "can_edit": m == "full",
            "can_assign": m == "kaf", "analytics": m != "own", "slots": SLOTS,
            "kafedra": dn.get(int(c.user.get("department_id") or 0)) if m == "kaf" else None}

# ---------------------------------------------------------------------------------------------
# O'zgartirish amallari
# ---------------------------------------------------------------------------------------------
class AbsIn(BaseModel):
    staff_id: int | None = None
    kind: str
    start: str
    end: str
    note: str = ""

class CancelIn(BaseModel):
    note: str = ""

class SubIn(BaseModel):
    sched_id: int
    date: str
    teacher_id: int
    note: str = ""
    all_dates: bool = False

class OrderIn(BaseModel):
    reg_no: str = ""        # bo'sh bo'lsa — Hujjatlar markazida yangi «leave_order» loyihasi yaratiladi

def _dates_ok(start, end):
    try: s, e = _d(start), _d(end)
    except ValueError: raise HTTPException(400, "Sana noto'g'ri")
    if e < s: raise HTTPException(400, "Tugash sanasi boshlanishdan oldin bo'lishi mumkin emas")
    if _days(s, e) > 180: raise HTTPException(400, "Yo'qlik muddati 180 kundan oshmasligi kerak")
    if e < _today() - dt.timedelta(days=366): raise HTTPException(400, "Bir yildan eski yozuv kiritilmaydi")
    return s.isoformat(), e.isoformat()

def _overlap(con, a_staff, a_teacher, start, end, skip=None):
    return db.one(con, """SELECT * FROM staff_absences WHERE status='faol' AND start<=? AND end>=? AND id IS NOT ?
                          AND (staff_id=? OR (? IS NOT NULL AND teacher_id=?)) LIMIT 1""", (end, start, skip, a_staff, a_teacher, a_teacher))

def create(con, c: Ctx, b: AbsIn, ts: str | None = None, check=True) -> int:
    if check: _need_full(c, "yaratish")
    st = db.one(con, "SELECT * FROM staff WHERE id=?", (int(b.staff_id or 0),))
    if not st: raise HTTPException(400, "Xodim tanlanmagan")
    if b.kind not in KINDS: raise HTTPException(400, "Yo'qlik turi noto'g'ri")
    s, e = _dates_ok(b.start, b.end)
    t = staff_teacher(con, st)
    ov = _overlap(con, st["id"], t["id"] if t else None, s, e)
    if ov: raise HTTPException(409, f"Bu xodimning shu davrda boshqa yozuvi bor: {KINDS.get(ov['kind'])} {_dmy(ov['start'])}–{_dmy(ov['end'])}")
    ts = ts or _now()
    aid = con.execute("""INSERT INTO staff_absences(staff_id,teacher_id,full_name,position,unit_name,department_id,kind,start,end,note,status,
                         created_by,created_by_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'faol',?,?,?,?)""",
                      (st["id"], t["id"] if t else None, st["full_name"], st["position"], st["unit"], t["department_id"] if t else None, b.kind, s, e,
                       (b.note or "").strip()[:500] or None, c.user["id"], c.user["full_name"], ts, ts)).lastrowid
    con.commit()
    return aid

def update(con, c: Ctx, aid: int, b: AbsIn) -> dict:
    _need_full(c, "tahrirlash", f"#{aid}")
    a = _get(con, aid)
    if a["status"] != "faol": raise HTTPException(409, "Bekor qilingan yozuv o'zgartirilmaydi")
    if b.kind not in KINDS: raise HTTPException(400, "Yo'qlik turi noto'g'ri")
    s, e = _dates_ok(b.start, b.end)
    ov = _overlap(con, a["staff_id"], a["teacher_id"], s, e, skip=aid)
    if ov: raise HTTPException(409, f"Bu xodimning shu davrda boshqa yozuvi bor: {KINDS.get(ov['kind'])} {_dmy(ov['start'])}–{_dmy(ov['end'])}")
    dropped = con.execute("DELETE FROM staff_subs WHERE absence_id=? AND (date<? OR date>?)", (aid, s, e)).rowcount   # oraliqdan chiqqan o'rinbosarliklar
    con.execute("UPDATE staff_absences SET kind=?, start=?, end=?, note=?, updated_at=? WHERE id=?", (b.kind, s, e, (b.note or "").strip()[:500] or None, _now(), aid))
    con.commit()
    ch = [f"{k}: {a[k]} → {v}" for k, v in (("kind", b.kind), ("start", s), ("end", e)) if a[k] != v]
    return {"changes": ch, "dropped_subs": dropped}

def cancel(con, c: Ctx, aid: int, note: str) -> dict:
    _need_full(c, "bekor qilish", f"#{aid}")
    a = _get(con, aid)
    if a["status"] != "faol": raise HTTPException(409, "Yozuv allaqachon bekor qilingan")
    dropped = con.execute("DELETE FROM staff_subs WHERE absence_id=? AND date>=?", (aid, _today().isoformat())).rowcount
    con.execute("UPDATE staff_absences SET status='bekor', cancel_note=?, updated_at=? WHERE id=?", ((note or "").strip()[:300] or None, _now(), aid))
    con.commit()
    return {"dropped_subs": dropped}

def assign(con, c: Ctx, aid: int, b: SubIn, ts: str | None = None, check=True) -> dict:
    a = _get(con, aid)
    if check and not _can_assign(c, a):
        _audit(c, "xodimlar ta'tili: o'rinbosar tayinlash", False, f"#{aid} {a['full_name']}")
        raise AccessDenied("⛔ O'rinbosarni faqat shu o'qituvchi kafedrasining mudiri tayinlaydi. So'rov audit jurnaliga yozildi.")
    if a["status"] != "faol": raise HTTPException(409, "Yozuv bekor qilingan")
    r = db.one(con, "SELECT * FROM schedule WHERE id=? AND teacher_id=?", (b.sched_id, a["teacher_id"] or -1))
    if not r: raise HTTPException(400, "Bu dars yo'qlikdagi o'qituvchiga tegishli emas")
    try: d0 = _d(b.date)
    except ValueError: raise HTTPException(400, "Sana noto'g'ri")
    if not (a["start"] <= d0.isoformat() <= a["end"]) or d0.weekday() != r["weekday"]: raise HTTPException(400, "Bu sana yo'qlik oralig'ida emas yoki dars kuni emas")
    t = db.one(con, "SELECT * FROM teachers WHERE id=?", (b.teacher_id,))
    if not t or t["id"] == a["teacher_id"]: raise HTTPException(400, "O'rinbosar noto'g'ri tanlangan")
    dates = [d0.isoformat()]
    if b.all_dates:
        dates = [x.isoformat() for x in _dates(a, max(_today(), _d(a["start"]))) if x.weekday() == r["weekday"]]
        if d0.isoformat() not in dates: dates.insert(0, d0.isoformat())
    ts = ts or _now(); done, skipped = [], []
    for ds in dates:
        why = _busy(con, t["id"], ds, r["slot"])
        cur = db.one(con, "SELECT sub_teacher_id FROM staff_subs WHERE absence_id=? AND sched_id=? AND date=?", (aid, r["id"], ds))
        if why and not (cur and cur["sub_teacher_id"] == t["id"]):
            if ds == d0.isoformat() and not b.all_dates: raise HTTPException(409, f"{t['full_name']}: {why}")
            skipped.append({"date": ds, "why": why}); continue
        con.execute("""INSERT INTO staff_subs(absence_id,sched_id,date,sub_teacher_id,sub_name,note,assigned_by,assigned_by_name,assigned_at) VALUES(?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(absence_id,sched_id,date) DO UPDATE SET sub_teacher_id=excluded.sub_teacher_id, sub_name=excluded.sub_name, note=excluded.note,
                         assigned_by=excluded.assigned_by, assigned_by_name=excluded.assigned_by_name, assigned_at=excluded.assigned_at""",
                    (aid, r["id"], ds, t["id"], t["full_name"], (b.note or "").strip()[:200] or None, c.user["id"], c.user["full_name"], ts))
        done.append(ds)
    con.commit()
    return {"assigned": done, "skipped": skipped, "teacher": t["full_name"], "subject": r["subject"], "slot": r["slot"]}

def unassign(con, c: Ctx, aid: int, sub_id: int) -> dict:
    a = _get(con, aid)
    if not _can_assign(c, a):
        _audit(c, "xodimlar ta'tili: o'rinbosarni olib tashlash", False, f"#{aid}")
        raise AccessDenied("⛔ O'rinbosarni faqat shu kafedra mudiri o'zgartiradi. So'rov audit jurnaliga yozildi.")
    s = db.one(con, "SELECT * FROM staff_subs WHERE id=? AND absence_id=?", (sub_id, aid))
    if not s: raise HTTPException(404, "O'rinbosarlik topilmadi")
    con.execute("DELETE FROM staff_subs WHERE id=?", (sub_id,)); con.commit()
    return s

def link_order(con, c: Ctx, aid: int, b: OrderIn, base_url: str) -> dict:
    _need_full(c, "buyruqni bog'lash", f"#{aid}")
    a = _get(con, aid)
    if a["kind"] != "mehnat": raise HTTPException(400, "Buyruq loyihasi faqat mehnat ta'tili uchun (leave_order)")
    if a["status"] != "faol": raise HTTPException(409, "Yozuv bekor qilingan")
    if (b.reg_no or "").strip():
        d = db.one(con, "SELECT id, reg_no, params FROM documents WHERE reg_no=? AND kind='leave_order'", (b.reg_no.strip(),))
        if not d: raise HTTPException(404, "Bu raqamli mehnat ta'tili buyrug'i topilmadi")
        try: p = json.loads(d["params"] or "{}")
        except ValueError: p = {}
        if str(p.get("staff")) != str(a["staff_id"]): raise HTTPException(400, "Buyruq boshqa xodimga tegishli")
    else:
        from . import documents as D
        try:
            r = D.issue(con, c, "leave_order", {"staff": a["staff_id"], "start": a["start"], "days": _days(_d(a["start"]), _d(a["end"]))}, base_url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        d = db.one(con, "SELECT id, reg_no FROM documents WHERE reg_no=?", (r["regs"][0],))
    con.execute("UPDATE staff_absences SET order_doc_id=?, order_reg_no=?, updated_at=? WHERE id=?", (d["id"], d["reg_no"], _now(), aid)); con.commit()
    return {"doc_id": d["id"], "reg_no": d["reg_no"]}

def store_file(con, c: Ctx, aid: int, name: str, data: bytes) -> dict:
    _need_full(c, "asos hujjat yuklash", f"#{aid}")
    a = _get(con, aid)
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", (name or "").strip())[:120] or "hujjat"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT: raise HTTPException(415, f"Fayl turi qabul qilinmaydi ({', '.join(sorted(ALLOWED_EXT))})")
    if not data: raise HTTPException(400, "Fayl bo'sh")
    if len(data) > MAX_BYTES: raise HTTPException(413, "Fayl hajmi 10 MB dan oshmasligi kerak")
    try: chk = FC.inspect(name, ext, data)
    except FC.FileRejected as e: raise HTTPException(415, str(e))
    stored = f"{uuid.uuid4().hex}.{ext}"
    FILES.mkdir(parents=True, exist_ok=True)
    p = (FILES / stored).resolve()
    if p.parent != FILES.resolve(): raise HTTPException(400, "Noto'g'ri fayl nomi")
    p.write_bytes(data)
    fid = con.execute("""INSERT INTO staff_abs_files(absence_id,name,stored,size,ext,mime,sha256,scan,uploader_id,uploader_name,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (aid, name, stored, len(data), ext, chk["mime"], chk["sha256"], chk["scan"],
                                                            c.user["id"], c.user["full_name"], _now())).lastrowid
    con.commit()
    return {"id": fid, "name": name, "size": len(data), "scan": chk["scan"], "absence": a["full_name"]}

# ---------------------------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx:
    return _ctx(request)

@router.get("/api/staffabs/meta")
def api_meta(request: Request):
    return meta(C(request))

@router.get("/api/staffabs")
def api_list(request: Request, period: str = "active", kind: str = "", dept: str = "", q: str = ""):
    return list_absences(C(request), period, kind, int(dept) if dept.isdigit() else 0, q)

@router.get("/api/staffabs/needs")
def api_needs(request: Request, days: int = 14):
    return needs(C(request), days)

@router.get("/api/staffabs/changes")
def api_changes(request: Request, days: int = 14):
    return changes(C(request), days)

@router.get("/api/staffabs/analytics")
def api_analytics(request: Request):
    return analytics(C(request))

@router.get("/api/staffabs/staff")
def api_staff(request: Request, q: str = ""):
    c = C(request); _need_full(c, "xodim qidiruvi")
    q = (q or "").strip()[:60]
    if len(q) < 2: return []
    rows = db.rows(_con, "SELECT id, full_name, unit, position FROM staff WHERE full_name LIKE ? OR unit LIKE ? ORDER BY full_name LIMIT 20", (f"%{q}%", f"%{q}%"))
    dn = _dept_names(_con); out = []
    for r in rows:
        t = staff_teacher(_con, r)
        out.append({"id": r["id"], "name": r["full_name"], "unit": f"{dn.get(t['department_id'], '')} kafedrasi" if t else r["unit"], "position": r["position"],
                    "teacher_id": t["id"] if t else None,
                    "lessons_week": _con.execute("SELECT COUNT(*) FROM schedule WHERE teacher_id=?", (t["id"],)).fetchone()[0] if t else 0})
    return out

@router.get("/api/staffabs/{aid}")
def api_detail(aid: int, request: Request):
    return detail(C(request), aid)

@router.get("/api/staffabs/{aid}/suggest")
def api_suggest(aid: int, request: Request, sched_id: int, date: str):
    c = C(request); a = _get(_con, aid)
    if not (_can_assign(c, a) or mode(c) in ("full", "all")):
        _audit(c, "xodimlar ta'tili: o'rinbosar tavsiyasi", False, f"#{aid}")
        raise AccessDenied("⛔ O'rinbosar tavsiyasi kafedra mudiri, Kadrlar va Akademik bo'lim uchun. So'rov audit jurnaliga yozildi.")
    return {"items": suggest(_con, a, sched_id, date)}

@router.post("/api/staffabs")
def api_create(body: AbsIn, request: Request):
    c = C(request)
    aid = create(_con, c, body)
    a = _get(_con, aid)
    _audit(c, "xodimlar ta'tili: ro'yxatga olindi", True, f"#{aid} {a['full_name']} · {KINDS[a['kind']]} {a['start']}–{a['end']}")
    return {"ok": True, "id": aid, "lessons": len(lessons(_con, a))}

@router.put("/api/staffabs/{aid}")
def api_update(aid: int, body: AbsIn, request: Request):
    c = C(request)
    r = update(_con, c, aid, body)
    _audit(c, "xodimlar ta'tili: o'zgartirildi", True, f"#{aid}: {'; '.join(r['changes']) or 'izoh'}" + (f" · o'chirilgan o'rinbosarlik: {r['dropped_subs']}" if r["dropped_subs"] else ""))
    return {"ok": True, **r}

@router.post("/api/staffabs/{aid}/cancel")
def api_cancel(aid: int, body: CancelIn, request: Request):
    c = C(request)
    r = cancel(_con, c, aid, body.note)
    _audit(c, "xodimlar ta'tili: bekor qilindi", True, f"#{aid}" + (f" · {body.note[:120]}" if body.note else ""))
    return {"ok": True, **r}

@router.post("/api/staffabs/{aid}/subs")
def api_assign(aid: int, body: SubIn, request: Request):
    c = C(request)
    r = assign(_con, c, aid, body)
    _audit(c, "xodimlar ta'tili: o'rinbosar tayinlandi", True,
           f"#{aid} {r['subject']} {r['slot']}-para → {r['teacher']} · {', '.join(r['assigned'])}" + (f" · o'tkazib yuborildi {len(r['skipped'])}" if r["skipped"] else ""))
    return {"ok": True, **r}

@router.delete("/api/staffabs/{aid}/subs/{sid}")
def api_unassign(aid: int, sid: int, request: Request):
    c = C(request)
    s = unassign(_con, c, aid, sid)
    _audit(c, "xodimlar ta'tili: o'rinbosar olib tashlandi", True, f"#{aid} {s['date']} · {s['sub_name']}")
    return {"ok": True}

@router.post("/api/staffabs/{aid}/order")
def api_order(aid: int, body: OrderIn, request: Request):
    c = C(request)
    from . import service as SV
    r = link_order(_con, c, aid, body, SV.public_base(request))
    _audit(c, "xodimlar ta'tili: buyruq bog'landi", True, f"#{aid} → {r['reg_no']}")
    return {"ok": True, **r}

@router.post("/api/staffabs/{aid}/files")
async def api_upload(aid: int, request: Request, name: str):
    c = C(request)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BYTES:
        _audit(c, "xodimlar ta'tili: asos hujjat yuklash", False, f"#{aid} {name[:80]} — hajm")
        raise HTTPException(413, "Fayl hajmi 10 MB dan oshmasligi kerak")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_BYTES: raise HTTPException(413, "Fayl hajmi 10 MB dan oshmasligi kerak")
    try:
        r = store_file(_con, c, aid, name, bytes(buf))
    except HTTPException as e:
        if e.status_code in (413, 415): _audit(c, "xodimlar ta'tili: asos hujjat rad etildi", False, f"#{aid} {name[:80]} — {e.detail}")
        raise
    _audit(c, "xodimlar ta'tili: asos hujjat yuklandi", True, f"#{aid} {r['name']} ({r['size'] // 1024} KB, {r['scan']})")
    return {"ok": True, **r}

@router.get("/api/staffabs/files/{fid}")
def api_file(fid: int, request: Request):
    c = C(request)
    f = db.one(_con, "SELECT * FROM staff_abs_files WHERE id=?", (fid,))
    if not f: raise HTTPException(404, "Fayl topilmadi")
    a = _get(_con, f["absence_id"])
    ok = mode(c) == "full" or _is_own(c, a)
    _audit(c, "xodimlar ta'tili: asos hujjat yuklab olindi", ok, f"#{a['id']} {f['name']}")
    if not ok: raise AccessDenied("⛔ Asos hujjat faqat Kadrlar bo'limi va xodimning o'ziga ochiq. So'rov audit jurnaliga yozildi.")
    p = (FILES / f["stored"]).resolve()
    if p.parent != FILES.resolve() or not p.is_file(): raise HTTPException(404, "Fayl serverda topilmadi")
    return FileResponse(p, filename=f["name"], media_type=f.get("mime") or mimetypes.guess_type(f["name"])[0] or "application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

# ---------------------------------------------------------------------------------------------
# Demo: joriy va keyingi 2 hafta + o'tgan oylar (tahlil uchun). Idempotent: staffabs_meta 'demo' kaliti bo'yicha bir marta.
# ---------------------------------------------------------------------------------------------
DEMO_TAG = "v1"

def seed_demo(con) -> int:
    if db.one(con, "SELECT v FROM staffabs_meta WHERE k='demo'"): return 0
    if not db.one(con, "SELECT 1 x FROM staff") or not db.one(con, "SELECT 1 x FROM schedule"): return 0
    if con.execute("SELECT COUNT(*) FROM staff_absences").fetchone()[0]:
        con.execute("INSERT OR REPLACE INTO staffabs_meta(k,v) VALUES('demo',?)", (DEMO_TAG,)); con.commit(); return 0
    ku = db.one(con, "SELECT * FROM users WHERE role='kadrlar' ORDER BY id LIMIT 1")
    if not ku: return 0
    kc = Ctx(ku, ROLES["kadrlar"])
    today = _today(); day = lambda n: (today + dt.timedelta(days=n)).isoformat()
    def staff_of_teacher(tid):
        t = db.one(con, "SELECT * FROM teachers WHERE id=?", (tid,))
        if not t: return None
        for s in db.rows(con, "SELECT * FROM staff WHERE unit=? AND full_name=?", (TEACH_UNIT, t["full_name"])):
            tt = staff_teacher(con, s)
            if tt and tt["id"] == tid: return s
        return None
    def busy_teachers(dep, n, skip=()):    # kafedraning darsi ko'p o'qituvchilari (mudirdan tashqari)
        return [r["id"] for r in db.rows(con, """SELECT t.id FROM teachers t JOIN schedule sc ON sc.teacher_id=t.id WHERE t.department_id=? AND t.position!='Kafedra mudiri'
                                                GROUP BY t.id ORDER BY COUNT(*) DESC, t.id""", (dep,)) if r["id"] not in skip][:n]
    made = []
    def add(tid=None, staff=None, kind="kasallik", s=0, e=0, note="", ago_h=48):
        st = staff or (staff_of_teacher(tid) if tid else None)
        if not st: return None
        try:
            aid = create(con, kc, AbsIn(staff_id=st["id"], kind=kind, start=day(s), end=day(e), note=note),
                         ts=(dt.datetime.now() - dt.timedelta(hours=ago_h)).replace(microsecond=0).isoformat(), check=False)
        except HTTPException: return None
        made.append(aid); return aid
    k4 = busy_teachers(4, 3); k1 = busy_teachers(1, 2); k5 = busy_teachers(5, 2); k7 = busy_teachers(7, 2); k2 = busy_teachers(2, 1); k6 = busy_teachers(6, 1)
    u15 = db.one(con, "SELECT teacher_id FROM users WHERE role='oqituvchi' AND teacher_id IS NOT NULL ORDER BY id LIMIT 1")
    # joriy va yaqin 2 hafta
    a1 = add(k4[0] if k4 else None, kind="kasallik", s=-2, e=3, note="Kasallik varaqasi № 0412 (tuman poliklinikasi). Asl nusxasi chiqqanda topshiriladi.", ago_h=50)
    a2 = add(k4[1] if len(k4) > 1 else None, kind="kasallik", s=0, e=4, note="Kasallik varaqasi № 0418, ochiq.", ago_h=6)
    add(k1[0] if k1 else None, kind="safar", s=2, e=6, note="Samarqand iqtisodiyot va servis instituti — xalqaro konferensiya (rektor buyrug'i).", ago_h=30)
    a4 = add(k5[0] if k5 else None, kind="mehnat", s=7, e=20, note="Ta'tillar jadvali bo'yicha (ariza 02.11).", ago_h=70)
    add(k7[0] if k7 else None, kind="oquv", s=9, e=13, note="Malaka oshirish kursi — Bosh ilmiy-metodik markaz.", ago_h=26)
    if u15 and u15["teacher_id"]: add(u15["teacher_id"], kind="safar", s=8, e=10, note="Toshkent davlat iqtisodiyot universiteti — seminar.", ago_h=20)
    reg = db.one(con, "SELECT * FROM staff WHERE unit='Registrator ofisi' AND position!='Bo''lim boshlig''i' ORDER BY id LIMIT 1")
    if reg: add(staff=reg, kind="mehnat", s=1, e=14, note="Yillik mehnat ta'tili.", ago_h=96)
    acc = db.one(con, "SELECT * FROM staff WHERE unit='Buxgalteriya bo''limi' ORDER BY id DESC LIMIT 1")
    if acc: add(staff=acc, kind="kasallik", s=-1, e=2, note="Kasallik varaqasi.", ago_h=30)
    # o'tgan oylar (tahlil: kafedra/oy kesimi, tez-tez kasallik)
    if len(k4) > 2:
        add(k4[2], kind="kasallik", s=-150, e=-146, ago_h=3600); add(k4[2], kind="kasallik", s=-95, e=-91, ago_h=2300); add(k4[2], kind="kasallik", s=-40, e=-36, ago_h=980)
    if k2: add(k2[0], kind="kasallik", s=-70, e=-63, ago_h=1700); add(k2[0], kind="kasallik", s=-22, e=-18, ago_h=530)
    if len(k1) > 1: add(k1[1], kind="safar", s=-55, e=-50, ago_h=1330)
    if k6: add(k6[0], kind="oquv", s=-120, e=-108, ago_h=2900)
    if len(k5) > 1: add(k5[1], kind="kasallik", s=-30, e=-27, ago_h=730)
    if k7: add(k7[0], kind="safar", s=-80, e=-77, ago_h=1930)
    # o'rinbosarlar: joriy kasallik uchun bir qismi tayinlangan (kafedra mudiri nomidan)
    head = db.one(con, "SELECT * FROM users WHERE role='kafedra' AND department_id=4 ORDER BY id LIMIT 1")
    if head and a1:
        hc = Ctx(head, ROLES["kafedra"]); a = _get(con, a1); n = 0
        for x in lessons(con, a, today, today + dt.timedelta(days=3)):
            sg = suggest(con, a, x["sched_id"], x["date"], 1)
            if sg and n < 3:
                try: assign(con, hc, a1, SubIn(sched_id=x["sched_id"], date=x["date"], teacher_id=sg[0]["teacher_id"], note="Kafedra qarori"), check=False); n += 1
                except HTTPException: pass
    if a4:   # mehnat ta'tili — Hujjatlar markazidagi buyruq loyihasi bilan bog'lanadi
        try: link_order(con, kc, a4, OrderIn(), "http://127.0.0.1:8000/")
        except Exception as e: print("staff_absence demo: buyruq yaratilmadi:", e)
    con.execute("INSERT OR REPLACE INTO staffabs_meta(k,v) VALUES('demo',?)", (DEMO_TAG,)); con.commit()
    print(f"Xodimlar ta'tili demo: {len(made)} ta yozuv")
    return len(made)
