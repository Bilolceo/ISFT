"""«Kiruvchi xatlar» — Devonxona: tashqi tashkilotlardan kelgan xatlarni ro'yxatga olish (docs/devonxona.md).

Oqim: ro'yxatga olindi (Devonxona) → rezolyutsiya (rektor yoki prorektor: ijrochi bo'lim + muddat; ijrochiga Portal orqali xat ketadi)
→ ijroda → javob berildi (chiquvchi xat bilan bog'lanadi) → yopildi.
Kiruvchi raqam avtomatik: K-YYYY/NNNN. Fayl (skan) — xom tana bilan yuklanadi (PDF/JPG/PNG/DOCX).
pending(ctx) — Mening vazifalarim / qo'ng'iroqcha uchun: rezolyutsiya kutayotgan xatlar (rahbar), muddati o'tgan ijro (Devonxona).
"""
import datetime as dt, re
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
P = "/api/devon"
RES = rbac.CHANCERY
REGISTRAR = ("devonxona",)
RESOLVERS = {"rektor": "Rektor", "prorektor_oquv": "O'quv ishlari prorektori", "prorektor_ilmiy": "Ilmiy ishlar prorektori",
             "prorektor_moliya": "Moliya-iqtisod prorektori", "prorektor_yoshlar": "Yoshlar masalalari prorektori"}
VIEWERS = REGISTRAR + tuple(RESOLVERS) + ("kotib",)
ST = {"royxatda": "Rezolyutsiya kutilmoqda", "ijroda": "Ijroda", "javob": "Javob berildi", "yopildi": "Yopildi"}
FILES = db.DATA_DIR / "devon_files"
MAGIC = {b"%PDF": ".pdf", b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"PK\x03\x04": ".docx"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS in_letters(id INTEGER PRIMARY KEY, in_no TEXT UNIQUE, in_date TEXT, sender TEXT, sender_no TEXT, sender_date TEXT,
  subject TEXT, summary TEXT, file_name TEXT, file_stored TEXT, resolver_role TEXT, resolution TEXT, resolved_by INT, resolved_name TEXT,
  resolved_at TEXT, executor_unit TEXT, due TEXT, status TEXT DEFAULT 'royxatda', thread_id INT, reply_out_id INT, closed_at TEXT, close_note TEXT,
  created_by INT, created_by_name TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_inl_st ON in_letters(status, resolver_role);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat()
def _today(): return clock.today()

def init(con):
    con.executescript(SCHEMA)
    # seed xatosi: «Kuzatuv kengashi uchun choraklik KPI hisoboti» — Strategik bo'lim ishi (Devonxona emas)
    con.execute("""UPDATE tasks SET assignee_role='strategik', unit='strategik', assignee_user=NULL
                   WHERE text LIKE 'Kuzatuv kengashi uchun choraklik KPI%' AND COALESCE(unit,'')='devonxona'""")
    con.commit()
    try: seed_demo(con)
    except Exception as e: print("devon.seed:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _next_no(con, d: dt.date) -> str:
    n = db.one(con, "SELECT COUNT(*) n FROM in_letters WHERE in_no LIKE ?", (f"K-{d.year}/%",))["n"] + 1
    return f"K-{d.year}/{n:04d}"

def seed_demo(con):
    if db.one(con, "SELECT 1 x FROM in_letters LIMIT 1"): return
    dv = db.one(con, "SELECT id, full_name FROM users WHERE role='devonxona' ORDER BY id LIMIT 1")
    if not dv: return
    td = _today()
    demo = [("Oliy ta'lim, fan va innovatsiyalar vazirligi", "03-07/5521", "2026 yil qabul parametrlari bo'yicha ma'lumot so'rovi", "rektor", "royxatda", 1),
            ("Toshkent shahar hokimligi", "01-12/884", "Yoshlar forumida ishtirok etish to'g'risida", "prorektor_yoshlar", "royxatda", 2),
            ("O'zbekiston Respublikasi Markaziy banki", "16-4/310", "Amaliyot o'tash uchun talabalar yuborish taklifi", "prorektor_oquv", "royxatda", 3),
            ("Davlat soliq qo'mitasi", "08/2207", "Soliq hisobotini aniqlashtirish so'rovi", "prorektor_moliya", "ijroda", 6),
            ("Innovatsion rivojlanish agentligi", "IR-1190", "Grant tanlovi natijalari to'g'risida xabarnoma", "prorektor_ilmiy", "javob", 12),
            ("Ta'lim sifatini nazorat qilish inspeksiyasi", "05-2/7712", "Akkreditatsiya hujjatlarini taqdim etish", "rektor", "ijroda", 9)]
    for i, (snd, sno, subj, res, st, ago) in enumerate(demo):
        d = td - dt.timedelta(days=ago)
        ex = {"rektor": "sifat", "prorektor_oquv": "amaliyot", "prorektor_moliya": "buxgalteriya", "prorektor_ilmiy": "ilmiy_bolim",
              "prorektor_yoshlar": "manaviyat"}.get(res)
        due = (d + dt.timedelta(days=10)).isoformat()
        con.execute("""INSERT INTO in_letters(in_no,in_date,sender,sender_no,sender_date,subject,summary,resolver_role,resolution,resolved_name,resolved_at,
                       executor_unit,due,status,created_by,created_by_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (_next_no(con, d), d.isoformat(), snd, sno, (d - dt.timedelta(days=2)).isoformat(), subj, "Namuna xat (sintetik).", res,
                     "Ijro uchun. Muddatida javob tayyorlansin." if st != "royxatda" else None, RESOLVERS[res] if st != "royxatda" else None,
                     (d + dt.timedelta(days=1)).isoformat() if st != "royxatda" else None, ex if st != "royxatda" else None,
                     due if st != "royxatda" else None, st, dv["id"], dv["full_name"], d.isoformat() + "T10:00:00"))
    con.commit()

# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx:
    c = _ctx(request)
    if c.role.key not in VIEWERS:
        rbac.audit(_con, c, "kiruvchi xatlar", RES, False, "ruxsat yo'q")
        raise AccessDenied("⛔ Kiruvchi xatlar — Devonxona va rahbariyat uchun.")
    return c

def _row(r) -> dict:
    from . import portal as PT
    um = PT.unit_map(_con)
    od = r["due"] and r["status"] == "ijroda" and r["due"] < _today().isoformat()
    out = dict(r)
    out.update(status_label=ST.get(r["status"], r["status"]), resolver_label=RESOLVERS.get(r["resolver_role"], r["resolver_role"] or "—"),
               executor_name=(um.get(r["executor_unit"]) or {}).get("name", r["executor_unit"] or ""), overdue=bool(od), has_file=bool(r["file_stored"]))
    out.pop("file_stored", None)
    if r["reply_out_id"]:
        m = db.one(_con, "SELECT id, out_no, out_date, addressee FROM outgoing_mail WHERE id=?", (r["reply_out_id"],))
        out["reply"] = m
    if r["thread_id"]:
        t = db.one(_con, "SELECT id, ref_no, status FROM portal_threads WHERE id=?", (r["thread_id"],))
        out["thread"] = t
    return out

def _scope(c: Ctx):
    if c.role.key in RESOLVERS and c.role.key != "rektor": return "resolver_role=?", [c.role.key]
    return "1=1", []

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request)
    from . import portal as PT
    units = [{"key": u["key"], "name": u["name"]} for u in PT.units(_con) if u["group"] in ("bolim", "rahbariyat", "fakultet")]
    w, a = _scope(c)
    cnt = {r["status"]: r["n"] for r in db.rows(_con, f"SELECT status, COUNT(*) n FROM in_letters WHERE {w} GROUP BY 1", a)}
    return {"can": {"register": c.role.key in REGISTRAR, "resolve": c.role.key in RESOLVERS}, "role": c.role.key,
            "resolvers": RESOLVERS, "statuses": ST, "units": units, "counts": cnt}

@router.get(P + "/letters")
def api_list(request: Request, status: str = "", q: str = ""):
    c = C(request)
    w, a = _scope(c)
    w = [w]
    if status in ST: w.append("status=?"); a.append(status)
    elif status == "muddati": w.append("status='ijroda' AND due < ?"); a.append(_today().isoformat())
    if q.strip(): w.append("(subject LIKE ? OR sender LIKE ? OR in_no LIKE ? OR sender_no LIKE ?)"); a += [f"%{q.strip()}%"] * 4
    rows = db.rows(_con, f"SELECT * FROM in_letters WHERE {' AND '.join(w)} ORDER BY CASE status WHEN 'royxatda' THEN 0 WHEN 'ijroda' THEN 1 ELSE 2 END, in_date DESC, id DESC LIMIT 300", a)
    rbac.audit(_con, c, "kiruvchi xatlar ro'yxati", RES, True, status or "hammasi")
    return {"items": [_row(r) for r in rows]}

class LetterIn(BaseModel):
    sender: str = Field(..., min_length=2, max_length=200)
    sender_no: str = Field("", max_length=60)
    sender_date: str = ""
    in_date: str = ""
    subject: str = Field(..., min_length=3, max_length=300)
    summary: str = Field("", max_length=2000)
    resolver_role: str = "rektor"

@router.post(P + "/letters")
def api_create(body: LetterIn, request: Request):
    c = C(request)
    if c.role.key not in REGISTRAR: raise AccessDenied("⛔ Kiruvchi xatni faqat Devonxona ro'yxatga oladi.")
    if body.resolver_role not in RESOLVERS: raise HTTPException(400, "Rezolyutsiya beruvchini tanlang")
    d = _today()
    try:
        if body.in_date: d = dt.date.fromisoformat(body.in_date)
        if body.sender_date: dt.date.fromisoformat(body.sender_date)
    except ValueError: raise HTTPException(400, "Sana noto'g'ri")
    no = _next_no(_con, d)
    lid = _con.execute("""INSERT INTO in_letters(in_no,in_date,sender,sender_no,sender_date,subject,summary,resolver_role,status,created_by,created_by_name,created_at)
                          VALUES(?,?,?,?,?,?,?,?,'royxatda',?,?,?)""",
                       (no, d.isoformat(), body.sender.strip(), body.sender_no.strip(), body.sender_date or None, body.subject.strip(), body.summary.strip(),
                        body.resolver_role, c.user["id"], c.user["full_name"], _now())).lastrowid
    _con.commit()
    rbac.audit(_con, c, "kiruvchi xat ro'yxatga olindi", RES, True, f"{no} · {body.sender[:60]}")
    return {"ok": True, "id": lid, "in_no": no}

def _get(lid) -> dict:
    r = db.one(_con, "SELECT * FROM in_letters WHERE id=?", (lid,))
    if not r: raise HTTPException(404, "Xat topilmadi")
    return r

@router.post(P + "/letters/{lid}/file")
async def api_file(lid: int, request: Request):
    c = C(request)
    if c.role.key not in REGISTRAR: raise AccessDenied("⛔ Faylni Devonxona yuklaydi.")
    r = _get(lid)
    data = await request.body()
    if not data or len(data) > 20 * 1024 * 1024: raise HTTPException(413, "Fayl 20 MB dan oshmasin")
    ext = next((e for m, e in MAGIC.items() if data.startswith(m)), None)
    if not ext: raise HTTPException(415, "Faqat PDF, JPG, PNG yoki DOCX")
    FILES.mkdir(parents=True, exist_ok=True)
    stored = f"in{lid}{ext}"; (FILES / stored).write_bytes(data)
    name = re.sub(r"[^\w.\- ]", "_", request.headers.get("x-filename", "") or f"{r['in_no']}{ext}")[:120]
    _con.execute("UPDATE in_letters SET file_name=?, file_stored=? WHERE id=?", (name, stored, lid)); _con.commit()
    rbac.audit(_con, c, "kiruvchi xat fayli", RES, True, r["in_no"])
    return {"ok": True}

@router.get(P + "/letters/{lid}/file")
def api_file_get(lid: int, request: Request):
    c = C(request); r = _get(lid)
    w, a = _scope(c)
    if not db.one(_con, f"SELECT 1 x FROM in_letters WHERE id=? AND {w}", [lid] + a): raise AccessDenied("⛔")
    if not r["file_stored"] or not (FILES / r["file_stored"]).exists(): raise HTTPException(404, "Fayl yo'q")
    rbac.audit(_con, c, "kiruvchi xat fayli (ko'rish)", RES, True, r["in_no"])
    return FileResponse(FILES / r["file_stored"], filename=r["file_name"] or Path(r["file_stored"]).name)

class ResIn(BaseModel):
    resolution: str = Field(..., min_length=3, max_length=1000)
    executor_unit: str
    due: str

@router.post(P + "/letters/{lid}/resolution")
def api_resolution(lid: int, body: ResIn, request: Request):
    c = C(request); r = _get(lid)
    if c.role.key not in RESOLVERS or (c.role.key != "rektor" and r["resolver_role"] != c.role.key):
        raise AccessDenied("⛔ Rezolyutsiyani xat yo'naltirilgan rahbar (yoki rektor) beradi.")
    if r["status"] != "royxatda": raise HTTPException(409, "Rezolyutsiya allaqachon berilgan")
    try: due = dt.date.fromisoformat(body.due)
    except ValueError: raise HTTPException(400, "Muddat noto'g'ri")
    if due < _today(): raise HTTPException(400, "Muddat o'tgan sana bo'lmasin")
    from . import portal as PT
    um = PT.unit_map(_con)
    if body.executor_unit not in um: raise HTTPException(400, "Ijrochi bo'limni tanlang")
    tid = None
    try:
        tid = PT.create_thread(_con, c, PT.ThreadIn(subject=f"Kiruvchi xat {r['in_no']}: {r['subject']}"[:200],
                               body=f"{r['sender']} ({r['sender_no'] or 'raqamsiz'}) xati bo'yicha rezolyutsiya:\n\n{body.resolution.strip()}\n\n"
                                    f"Ijro muddati: {due.strftime('%d.%m.%Y')}. Javob loyihasini Devonxonaga yuboring.",
                               to=[body.executor_unit], kind="topshiriq", priority="muhim", due=due.isoformat()))
    except HTTPException: tid = None       # o'z bo'limiga yuborib bo'lmaydi va h.k. — xat baribir ijroga o'tadi
    _con.execute("""UPDATE in_letters SET resolution=?, resolved_by=?, resolved_name=?, resolved_at=?, executor_unit=?, due=?, status='ijroda', thread_id=?
                    WHERE id=?""", (body.resolution.strip(), c.user["id"], c.user["full_name"], _now(), body.executor_unit, due.isoformat(), tid, lid))
    _con.commit()
    rbac.audit(_con, c, "kiruvchi xatga rezolyutsiya", RES, True, f"{r['in_no']} → {body.executor_unit}")
    return {"ok": True, "thread_id": tid}

class CloseIn(BaseModel):
    out_id: int = 0
    note: str = Field("", max_length=500)

@router.post(P + "/letters/{lid}/close")
def api_close(lid: int, body: CloseIn, request: Request):
    c = C(request); r = _get(lid)
    if c.role.key not in REGISTRAR: raise AccessDenied("⛔ Xatni Devonxona yopadi.")
    if r["status"] not in ("ijroda", "javob"): raise HTTPException(409, "Avval rezolyutsiya kerak")
    if body.out_id:
        if not db.one(_con, "SELECT 1 x FROM outgoing_mail WHERE id=?", (body.out_id,)): raise HTTPException(400, "Chiquvchi xat topilmadi")
        _con.execute("UPDATE in_letters SET reply_out_id=?, status='javob', closed_at=?, close_note=? WHERE id=?", (body.out_id, _now(), body.note.strip(), lid))
    else:
        if len(body.note.strip()) < 3: raise HTTPException(400, "Javobsiz yopishda izoh yozing (masalan: «ma'lumot uchun»)")
        _con.execute("UPDATE in_letters SET status='yopildi', closed_at=?, close_note=? WHERE id=?", (_now(), body.note.strip(), lid))
    _con.commit()
    rbac.audit(_con, c, "kiruvchi xat yopildi", RES, True, f"{r['in_no']} · chiquvchi #{body.out_id or '—'}")
    return {"ok": True}

@router.get(P + "/outgoing")
def api_outgoing(request: Request, q: str = ""):
    c = C(request)
    if c.role.key not in REGISTRAR: raise AccessDenied("⛔")
    return {"items": db.rows(_con, "SELECT id, out_no, out_date, addressee, subject FROM outgoing_mail WHERE subject LIKE ? OR addressee LIKE ? OR out_no LIKE ? ORDER BY id DESC LIMIT 30",
                             (f"%{q}%",) * 3)}

# ---------------------------------------------------------------------------------------------
def pending(c: Ctx) -> list[dict]:
    """Yagona «kutilayotgan ishlar» shakli: {kind,title,sub,due,view,src,sign}."""
    if _con is None: return []
    k = c.role.key; out = []
    if k in RESOLVERS:
        w = "status='royxatda'" + ("" if k == "rektor" else " AND resolver_role=?")
        a = [] if k == "rektor" else [k]
        if k == "rektor": w += " AND resolver_role='rektor'"
        for r in db.rows(_con, f"SELECT * FROM in_letters WHERE {w} ORDER BY in_date LIMIT 30", a):
            out.append({"kind": "kiruvchi", "title": f"Rezolyutsiya: {r['subject']}", "sub": f"{r['in_no']} · {r['sender']}",
                        "due": (dt.date.fromisoformat(r["in_date"]) + dt.timedelta(days=2)).isoformat(), "view": "kiruvchi", "src": "Kiruvchi xatlar",
                        "sign": True, "id": r["id"]})
    if k in REGISTRAR:
        for r in db.rows(_con, "SELECT * FROM in_letters WHERE status='ijroda' AND due < ? ORDER BY due LIMIT 30", (_today().isoformat(),)):
            out.append({"kind": "kiruvchi", "title": f"Ijro muddati o'tgan: {r['subject']}", "sub": f"{r['in_no']} · {r['sender']}",
                        "due": r["due"], "view": "kiruvchi", "src": "Kiruvchi xatlar", "sign": False, "id": r["id"]})
    return out
