"""AT bo'limi: «Kutilayotgan akkaunt so'rovlari» — Kadrlar jarayonlaridan (app/kadrlar.py).

• Ishga qabul: nomzod «buyruq» yoki «qabul_qilindi» bosqichida → yangi akkaunt kerak (forma oldindan to'ldiriladi).
• Ishdan bo'shatish: ariza/varaqa/buyruq/yakunlangan → xodimning faol akkauntlari bloklanishi kerak.
AT boshlig'i «Bajarildi» deb belgilaydi (it_req_done). Kadrlar Portal xati (it_thread_id) bo'lsa — havola.
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
P = "/api/it-requests"
ROLES = ("it_head", "it_staff")

def init(con):
    con.execute("CREATE TABLE IF NOT EXISTS it_req_done(kind TEXT, ref_id INT, done_at TEXT, user_name TEXT, note TEXT, PRIMARY KEY(kind, ref_id))")
    con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _tbl(name): return bool(db.one(_con, "SELECT 1 x FROM sqlite_master WHERE type='table' AND name=?", (name,)))

def items() -> list[dict]:
    if not _tbl("hr_candidates"): return []
    from . import kadrlar as K
    done = {(r["kind"], r["ref_id"]): r for r in db.rows(_con, "SELECT * FROM it_req_done")}
    out = []
    for k in db.rows(_con, """SELECT c.*, v.unit_key, v.position FROM hr_candidates c JOIN hr_vacancies v ON v.id=c.vacancy_id
                              WHERE c.stage IN ('buyruq','qabul_qilindi') ORDER BY c.start_date"""):
        if ("hire", k["id"]) in done: continue
        role = "oqituvchi" if (k["unit_key"] or "").startswith("kaf") else None
        out.append({"kind": "hire", "id": k["id"], "title": f"Yangi xodim: {k['full_name']}", "person": k["full_name"], "position": k["position"],
                    "unit": k["unit_key"], "unit_name": K.unit_name(_con, k["unit_key"]), "role": role, "date": k["start_date"],
                    "signed": k["stage"] == "qabul_qilindi", "thread_id": k["it_thread_id"]})
    for d in db.rows(_con, "SELECT * FROM hr_dismissals WHERE status IN ('ariza','varaqa','buyruq','yakunlangan') ORDER BY last_day"):
        if ("dismiss", d["id"]) in done: continue
        s = db.one(_con, "SELECT full_name, position FROM staff WHERE id=?", (d["staff_id"],)) or {}
        acc = db.rows(_con, "SELECT id, active FROM users WHERE full_name LIKE ? AND COALESCE(active,1)=1", (f"%: {s.get('full_name')}",)) if s.get("full_name") else []
        out.append({"kind": "dismiss", "id": d["id"], "title": f"Akkauntni bloklash: {s.get('full_name', '—')}", "person": s.get("full_name"),
                    "position": s.get("position"), "date": d["last_day"], "signed": d["status"] in ("buyruq", "yakunlangan"),
                    "accounts": [a["id"] for a in acc], "thread_id": d["it_thread_id"]})
    return out

def C(request: Request) -> Ctx:
    c = _ctx(request)
    if c.role.key not in ROLES: raise AccessDenied("⛔ Akkaunt so'rovlari — AT bo'limi uchun.")
    return c

@router.get(P)
def api_list(request: Request):
    c = C(request)
    rbac.audit(_con, c, "akkaunt so'rovlari", "accounts", True)
    return {"items": items(), "can_edit": c.role.key == "it_head"}

class DoneIn(BaseModel):
    note: str = Field("", max_length=300)

@router.post(P + "/{kind}/{rid}/done")
def api_done(kind: str, rid: int, body: DoneIn, request: Request):
    c = C(request)
    if c.role.key != "it_head": raise AccessDenied("⛔ Faqat AT bo'limi boshlig'i.")
    if kind not in ("hire", "dismiss"): raise HTTPException(404)
    _con.execute("INSERT OR REPLACE INTO it_req_done(kind,ref_id,done_at,user_name,note) VALUES(?,?,?,?,?)",
                 (kind, rid, clock.now().replace(microsecond=0).isoformat(), c.user["full_name"], body.note.strip()))
    _con.commit()
    rbac.audit(_con, c, "akkaunt so'rovi bajarildi", "accounts", True, f"{kind} #{rid}")
    return {"ok": True}

def pending(c: Ctx) -> list[dict]:
    if _con is None or c.role.key != "it_head": return []
    return [{"kind": "akkaunt", "title": i["title"], "sub": i.get("unit_name") or i.get("position") or "", "due": i["date"], "view": "accounts",
             "src": "Akkauntlar", "sign": False} for i in items()]
