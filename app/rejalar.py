"""«KPI maqsadlari» (Strategik bo'lim) va «Sifat amallari» (Sifatni ta'minlash boshqarmasi) — docs/rejalar.md.

Strategik: KPI maqsadi = ko'rsatkich (desks.strategic/quality dagi kalit) + mas'ul bo'lim + maqsad qiymat + muddat; amaldagi qiymat
avtomatik (o'sha ko'rsatkichdan). «Kengash hisoboti» — choraklik .docx (maqsadlar va asosiy ko'rsatkichlar).
Sifat: (1) topilma — kafedraga topshiriq sifatida yuboriladi (directives.create_linked); (2) akkreditatsiya nazorat varaqasi.
"""
import datetime as dt, io, math
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
P = "/api/rejalar"
KPI_EDIT, KPI_READ = ("strategik",), ("rektor", "kengash", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar")
SIF_EDIT, SIF_READ = ("sifat",), ("rektor", "prorektor_oquv")
AKKR_ST = {"yoq": "Boshlanmagan", "jarayonda": "Jarayonda", "tayyor": "Tayyor"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS kpi_targets(id INTEGER PRIMARY KEY, metric TEXT, title TEXT, owner_unit TEXT, target REAL, good TEXT DEFAULT 'up',
  deadline TEXT, note TEXT, created_by INT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS sifat_findings(id INTEGER PRIMARY KEY, unit TEXT, title TEXT, body TEXT, due TEXT, directive_id INT, created_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS akkr_items(id INTEGER PRIMARY KEY, section TEXT, title TEXT, owner_unit TEXT, status TEXT DEFAULT 'yoq', due TEXT, note TEXT,
  updated_by TEXT, updated_at TEXT);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat()

def _date(v: str, msg="Muddat noto'g'ri") -> str:
    """'YYYY-MM-DD' ga keltiradi (fromisoformat '20270101' kabi shakllarni ham qabul qiladi — saqlashda yagona ko'rinish, satr taqqoslash uchun)."""
    try: return dt.date.fromisoformat(str(v).strip()).isoformat()
    except ValueError: raise HTTPException(400, msg)

def init(con):
    con.executescript(SCHEMA); con.commit()
    try: seed_demo(con)
    except Exception as e: print("rejalar.seed:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def seed_demo(con):
    td = clock.today()
    if not db.one(con, "SELECT 1 x FROM kpi_targets LIMIT 1"):
        for m, t, u, v, g, mo in [("kontrakt", "Kontrakt tushumi", "buxgalteriya", 95, "up", 2), ("davomat", "Davomat", "talabalar", 90, "up", 3),
                                  ("ozlashtirmagan", "O'zlashtirmaganlar ulushi", "akademik", 10, "down", 4), ("scopus", "Scopus/WoS maqolalar", "ilmiy_bolim", 40, "up", 8),
                                  ("daraja", "Ilmiy darajali o'qituvchilar", "kadrlar", 45, "up", 10), ("ijro", "Topshiriqlar ijrosi", "rektorat", 90, "up", 1)]:
            con.execute("INSERT INTO kpi_targets(metric,title,owner_unit,target,good,deadline,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (m, t, u, v, g, (td + dt.timedelta(days=30 * mo)).isoformat(), _now(), _now()))
    if not db.one(con, "SELECT 1 x FROM akkr_items LIMIT 1"):
        items = [("Ta'lim dasturlari", "Barcha yo'nalishlar uchun tasdiqlangan o'quv rejalari", "akademik", "tayyor"),
                 ("Ta'lim dasturlari", "Fanlar sillabuslari (joriy semestr) to'liq", "akademik", "jarayonda"),
                 ("Ta'lim dasturlari", "Malakaviy amaliyot shartnomalari", "amaliyot", "jarayonda"),
                 ("Professor-o'qituvchilar", "Ilmiy darajalilar ulushi bo'yicha ma'lumotnoma", "kadrlar", "jarayonda"),
                 ("Professor-o'qituvchilar", "Malaka oshirish jadvali (5 yillik)", "kadrlar", "yoq"),
                 ("Talabalar", "O'zlashtirish va davomat tahlili (2 semestr)", "talabalar", "tayyor"),
                 ("Talabalar", "Talabalar so'rovnomasi natijalari", "sifat", "yoq"),
                 ("Moddiy-texnik baza", "Auditoriyalar va jihozlar pasporti", "xojalik", "jarayonda"),
                 ("Moddiy-texnik baza", "Axborot-resurs markazi fondi ma'lumotnomasi", "arm", "yoq"),
                 ("Ilmiy faoliyat", "Nashrlar va grantlar reyestri", "ilmiy_bolim", "tayyor"),
                 ("Xalqaro hamkorlik", "Amaldagi hamkorlik shartnomalari nusxalari", "xalqaro", "jarayonda"),
                 ("Boshqaruv", "Ichki me'yoriy hujjatlar (nizomlar) to'plami", "yuridik", "jarayonda")]
        for i, (s, t, u, st) in enumerate(items):
            con.execute("INSERT INTO akkr_items(section,title,owner_unit,status,due,updated_at) VALUES(?,?,?,?,?,?)",
                        (s, t, u, st, (td + dt.timedelta(days=20 + 5 * i)).isoformat(), _now()))
    con.commit()

def C(request: Request, edit: tuple, read: tuple, write=False) -> Ctx:
    c = _ctx(request)
    if c.role.key in edit or (not write and c.role.key in read): return c
    rbac.audit(_con, c, "KPI / sifat amallari", rbac.KPI, False, "ruxsat yo'q")
    raise AccessDenied("⛔ Bu bo'lim sizning lavozimingiz uchun emas.")

def _metrics() -> dict:
    from . import desks
    out = {}
    for d in (desks.strategic(_con), desks.quality(_con)):
        for i in d["indicators"]: out.setdefault(i["key"], i)
    return out

def _units():
    from . import portal as PT
    return {u["key"]: u["name"] for u in PT.units(_con)}

def _targets():
    ms, um, td = _metrics(), _units(), clock.today().isoformat()
    out = []
    for t in db.rows(_con, "SELECT * FROM kpi_targets ORDER BY deadline"):
        m = ms.get(t["metric"]) or {}
        v = m.get("value")
        ok = v is not None and t["target"] is not None and (v >= t["target"] if t["good"] == "up" else v <= t["target"])
        st = "bajarildi" if ok else ("muddati_otgan" if t["deadline"] and t["deadline"] < td else "yolda")
        out.append({**t, "actual": v, "unit": m.get("unit", ""), "metric_label": m.get("label", t["metric"]), "owner_name": um.get(t["owner_unit"], t["owner_unit"]),
                    "status": st, "status_label": {"bajarildi": "Erishildi", "muddati_otgan": "Muddati o'tdi", "yolda": "Jarayonda"}[st]})
    return out

@router.get(P + "/kpi")
def api_kpi(request: Request):
    c = C(request, KPI_EDIT, KPI_READ)
    ms = _metrics()
    rbac.audit(_con, c, "KPI maqsadlari", rbac.KPI, True)
    return {"can_edit": c.role.key in KPI_EDIT, "targets": _targets(),
            "metrics": [{"key": k, "label": v["label"], "unit": v["unit"], "value": v["value"], "good": v["good"]} for k, v in ms.items()],
            "units": [{"key": k, "name": n} for k, n in _units().items()]}

class TargetIn(BaseModel):
    metric: str
    title: str = Field("", max_length=120)
    owner_unit: str
    target: float
    deadline: str
    note: str = Field("", max_length=300)

@router.post(P + "/kpi")
def api_kpi_add(body: TargetIn, request: Request, tid: int = 0):
    c = C(request, KPI_EDIT, (), True)
    ms = _metrics()
    if body.metric not in ms: raise HTTPException(400, "Ko'rsatkichni tanlang")
    if body.owner_unit not in _units(): raise HTTPException(400, "Mas'ul bo'limni tanlang")
    if not math.isfinite(body.target) or body.target < 0: raise HTTPException(400, "Maqsad qiymat noto'g'ri")
    body.deadline = _date(body.deadline)
    title = body.title.strip() or ms[body.metric]["label"]
    if tid:
        if not db.one(_con, "SELECT 1 x FROM kpi_targets WHERE id=?", (tid,)): raise HTTPException(404, "Maqsad topilmadi")
        _con.execute("UPDATE kpi_targets SET metric=?, title=?, owner_unit=?, target=?, good=?, deadline=?, note=?, updated_at=? WHERE id=?",
                     (body.metric, title, body.owner_unit, body.target, ms[body.metric]["good"], body.deadline, body.note, _now(), tid))
    else:
        tid = _con.execute("INSERT INTO kpi_targets(metric,title,owner_unit,target,good,deadline,note,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (body.metric, title, body.owner_unit, body.target, ms[body.metric]["good"], body.deadline, body.note, c.user["id"], _now(), _now())).lastrowid
    _con.commit()
    rbac.audit(_con, c, "KPI maqsadi saqlandi", rbac.KPI, True, f"#{tid} {title}")
    return {"ok": True, "id": tid}

@router.post(P + "/kpi/{tid}/delete")
def api_kpi_del(tid: int, request: Request):
    c = C(request, KPI_EDIT, (), True)
    if not _con.execute("DELETE FROM kpi_targets WHERE id=?", (tid,)).rowcount: raise HTTPException(404, "Maqsad topilmadi")
    _con.commit()
    rbac.audit(_con, c, "KPI maqsadi o'chirildi", rbac.KPI, True, f"#{tid}")
    return {"ok": True}

@router.get(P + "/kengash.docx")
def api_report(request: Request):
    c = C(request, KPI_EDIT, KPI_READ)
    from docx import Document
    from docx.shared import Pt
    td = clock.today(); q = (td.month - 1) // 3 + 1
    doc = Document(); s = doc.styles["Normal"]; s.font.name = "Times New Roman"; s.font.size = Pt(12)
    doc.add_heading(f"Kuzatuv kengashi uchun {td.year}-yil {q}-chorak hisoboti", level=1)
    doc.add_paragraph(f"Tayyorladi: Strategik bo'lim · {td.strftime('%d.%m.%Y')}. Barcha raqamlar jamlangan (shaxsiy ma'lumotsiz).")
    doc.add_heading("1. KPI maqsadlari ijrosi", level=2)
    tg = _targets()
    t = doc.add_table(rows=1, cols=6); t.style = "Table Grid"
    for i, h in enumerate(["Ko'rsatkich", "Mas'ul", "Maqsad", "Amalda", "Muddat", "Holat"]): t.rows[0].cells[i].text = h
    for r in tg:
        cs = t.add_row().cells
        for i, v in enumerate([r["title"], r["owner_name"], f"{r['target']:g}{r['unit']}", "—" if r["actual"] is None else f"{r['actual']}{r['unit']}",
                               r["deadline"] or "", r["status_label"]]): cs[i].text = str(v)
    doc.add_paragraph(f"Erishilgan: {sum(r['status'] == 'bajarildi' for r in tg)} / {len(tg)}; muddati o'tgan: {sum(r['status'] == 'muddati_otgan' for r in tg)}.")
    doc.add_heading("2. Asosiy ko'rsatkichlar", level=2)
    t2 = doc.add_table(rows=1, cols=3); t2.style = "Table Grid"
    for i, h in enumerate(["Ko'rsatkich", "Qiymat", "Izoh"]): t2.rows[0].cells[i].text = h
    for m in _metrics().values():
        cs = t2.add_row().cells
        cs[0].text, cs[1].text, cs[2].text = m["label"], "—" if m["value"] is None else f"{m['value']}{m['unit']}", m.get("sub") or ""
    doc.add_paragraph(f"\n«{AR.RISK_LABEL}» ta'rifi: {AR.RISK_DEF}.")
    doc.add_paragraph("\nStrategik bo'lim boshlig'i ____________________")
    buf = io.BytesIO(); doc.save(buf)
    rbac.audit(_con, c, "Kengash hisoboti (DOCX)", rbac.KPI, True, f"{td.year}-Q{q}")
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="kengash-hisoboti-{td.year}-Q{q}.docx"'})

# ---------------------------------------------------------------------------------------------
@router.get(P + "/sifat")
def api_sifat(request: Request):
    c = C(request, SIF_EDIT, SIF_READ)
    um = _units()
    kaf = [{"key": k, "name": n} for k, n in um.items() if k.startswith("kaf")]
    items = db.rows(_con, "SELECT * FROM akkr_items ORDER BY section, id")
    for i in items: i["owner_name"] = um.get(i["owner_unit"], i["owner_unit"]); i["status_label"] = AKKR_ST.get(i["status"], i["status"])
    fs = db.rows(_con, "SELECT f.*, t.status task_status FROM sifat_findings f LEFT JOIN tasks t ON t.id=f.directive_id ORDER BY f.id DESC LIMIT 100")
    for f in fs: f["unit_name"] = um.get(f["unit"], f["unit"])
    rbac.audit(_con, c, "sifat amallari", rbac.ACADEMIC, True)
    return {"can_edit": c.role.key in SIF_EDIT, "kafedras": kaf, "units": [{"key": k, "name": n} for k, n in um.items()], "akkr": items,
            "akkr_status": AKKR_ST, "findings": fs, "risk": {"label": AR.RISK_LABEL, "def": AR.RISK_DEF}}

class FindIn(BaseModel):
    unit: str
    title: str = Field(..., min_length=5, max_length=200)
    body: str = Field(..., min_length=10, max_length=3000)
    due: str

@router.post(P + "/sifat/finding")
def api_finding(body: FindIn, request: Request):
    c = C(request, SIF_EDIT, (), True)
    if not body.unit.startswith("kaf") or body.unit not in _units(): raise HTTPException(400, "Kafedrani tanlang")
    if len(body.title.strip()) < 5 or len(body.body.strip()) < 10: raise HTTPException(400, "Topilma va tafsilotni to'liq yozing")
    body.due = _date(body.due)
    if body.due < clock.today().isoformat(): raise HTTPException(400, "Muddat o'tgan sana bo'lmasin")
    from . import directives as DIR
    tid = DIR.create_linked(_con, c.user["id"], "sifat", body.unit, f"Sifat topilmasi: {body.title.strip()}", body.body.strip(), body.due,
                            prio="muhim", expect="Kamchilik bartaraf etilgani haqida qisqa hisobot", src="sifat")
    fid = _con.execute("INSERT INTO sifat_findings(unit,title,body,due,directive_id,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                       (body.unit, body.title.strip(), body.body.strip(), body.due, tid, c.user["id"], _now())).lastrowid
    _con.commit()
    rbac.audit(_con, c, "sifat topilmasi kafedraga", rbac.ACADEMIC, True, f"#{fid} → {body.unit} · topshiriq #{tid}")
    return {"ok": True, "id": fid, "directive_id": tid}

class AkkrIn(BaseModel):
    status: str
    note: str = Field("", max_length=300)
    owner_unit: str = ""
    due: str = ""

@router.post(P + "/sifat/akkr/{iid}")
def api_akkr(iid: int, body: AkkrIn, request: Request):
    c = C(request, SIF_EDIT, (), True)
    if body.status not in AKKR_ST: raise HTTPException(400, "Holat noto'g'ri")
    r = db.one(_con, "SELECT * FROM akkr_items WHERE id=?", (iid,))
    if not r: raise HTTPException(404)
    if body.owner_unit and body.owner_unit not in _units(): raise HTTPException(400, "Mas'ul bo'limni tanlang")
    due = _date(body.due) if body.due.strip() else ""
    note = body.note.strip() if "note" in body.model_fields_set else r["note"]   # faqat holat o'zgarsa (sahifadagi ro'yxat) — izoh o'chmasin
    _con.execute("UPDATE akkr_items SET status=?, note=?, owner_unit=COALESCE(NULLIF(?,''), owner_unit), due=COALESCE(NULLIF(?,''), due), updated_by=?, updated_at=? WHERE id=?",
                 (body.status, note, body.owner_unit, due, c.user["full_name"], _now(), iid))
    _con.commit()
    rbac.audit(_con, c, "akkreditatsiya bandi", rbac.ACADEMIC, True, f"#{iid} → {body.status}")
    return {"ok": True}

class AkkrNew(BaseModel):
    section: str = Field(..., min_length=2, max_length=80)
    title: str = Field(..., min_length=3, max_length=200)
    owner_unit: str
    due: str = ""

@router.post(P + "/sifat/akkr")
def api_akkr_new(body: AkkrNew, request: Request):
    c = C(request, SIF_EDIT, (), True)
    if len(body.section.strip()) < 2 or len(body.title.strip()) < 3: raise HTTPException(400, "Bo'lim va bandni yozing")
    if body.owner_unit not in _units(): raise HTTPException(400, "Mas'ul bo'limni tanlang")
    due = _date(body.due) if body.due.strip() else None
    i = _con.execute("INSERT INTO akkr_items(section,title,owner_unit,status,due,updated_by,updated_at) VALUES(?,?,?,'yoq',?,?,?)",
                     (body.section.strip(), body.title.strip(), body.owner_unit, due, c.user["full_name"], _now())).lastrowid
    _con.commit()
    rbac.audit(_con, c, "akkreditatsiya bandi qo'shildi", rbac.ACADEMIC, True, f"#{i}")
    return {"ok": True, "id": i}

def pending(c: Ctx) -> list[dict]:
    if _con is None: return []
    td = clock.today().isoformat(); out = []
    if c.role.key in KPI_EDIT:
        for t in _targets():
            if t["status"] == "muddati_otgan":
                out.append({"kind": "kpi", "title": f"KPI maqsadi muddati o'tdi: {t['title']}", "sub": t["owner_name"], "due": t["deadline"],
                            "view": "rejalar", "src": "KPI maqsadlari", "sign": False})
    if c.role.key in SIF_EDIT:
        n = db.one(_con, "SELECT COUNT(*) n FROM akkr_items WHERE status!='tayyor' AND due < ?", (td,))["n"]
        if n: out.append({"kind": "akkr", "title": f"Akkreditatsiya: {n} ta band muddati o'tgan", "sub": "Sifat amallari", "due": td,
                          "view": "rejalar", "src": "Sifat amallari", "sign": False})
    return out
