"""«Qabul» — Qabul komissiyasi: abituriyentlar oqimi (docs/qabul.md).

ariza → hujjatlar tekshirildi → imtihon/suhbat → shartnoma → qabul buyrug'i loyihasi (yo'nalish bo'yicha .docx ro'yxat) | rad etildi.
Demo — sintetik abituriyentlar (haqiqiy shaxslar emas). Jamlangan qabul tahlili (Marketing bilan bir xil) — app/desks.admissions.
Ruxsat: qabul — to'liq; rektor, prorektor_oquv, marketing — faqat ko'rish (jamlangan + ro'yxat ismlarsiz emas, chunki ish ro'yxati).
"""
import datetime as dt, io, random
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
P = "/api/qabul"
RES = rbac.ADMISSIONS
FULL = ("qabul",)
READ = ("rektor", "prorektor_oquv", "marketing")
SUMMARY = ("kengash", "prorektor_moliya")   # faqat jamlangan raqamlar (voronka, yo'nalishlar, kontrakt/grant) — abituriyentlar ro'yxatisiz
STAGES = {"ariza": "Ariza qabul qilindi", "hujjat": "Hujjatlar tekshirildi", "imtihon": "Imtihon / suhbatdan o'tdi",
          "shartnoma": "Shartnoma tuzildi", "buyruq": "Qabul buyrug'i loyihasida", "rad": "Rad etildi"}
NEXT = {"ariza": "hujjat", "hujjat": "imtihon", "imtihon": "shartnoma"}
PASS_SCORE = 56          # imtihon/suhbat o'tish bali (100 ballik)
FORMS = ("kunduzgi", "sirtqi", "kechki", "masofaviy")
PAYS = ("kontrakt", "grant")

SCHEMA = """
CREATE TABLE IF NOT EXISTS qb_applicants(id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT, direction TEXT, study_form TEXT, payment_type TEXT,
  stage TEXT DEFAULT 'ariza', exam_score INT, contract_no TEXT, order_batch TEXT, note TEXT, created_by INT, created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_qba_stage ON qb_applicants(stage, direction);
CREATE TABLE IF NOT EXISTS qb_log(id INTEGER PRIMARY KEY, app_id INT, ts TEXT, user_name TEXT, action TEXT, note TEXT);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat()

def init(con):
    con.executescript(SCHEMA); con.commit()
    try: seed_demo(con)
    except Exception as e: print("qabul.seed:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _dirs(con) -> list[str]:
    try: ds = [r["direction"] for r in db.rows(con, "SELECT DISTINCT direction FROM applicants WHERE direction IS NOT NULL ORDER BY 1")]
    except Exception: ds = []
    return ds or ["Iqtisodiyot", "Buxgalteriya hisobi", "Moliya va moliyaviy texnologiyalar", "Menejment", "Axborot tizimlari"]

def seed_demo(con):
    if db.one(con, "SELECT 1 x FROM qb_applicants LIMIT 1"): return
    rnd = random.Random(2027)
    fam = ["Karimov", "Rahimov", "Toshpo'latov", "Yo'ldoshev", "Nurmatov", "Ergashev", "Qodirov", "Sobirov", "Xolmatov", "Abdullayev", "Mirzayev", "Jo'rayev"]
    ism_m = ["Jasur", "Sardor", "Bekzod", "Otabek", "Diyorbek", "Shoxrux", "Azizbek", "Javohir"]
    ism_f = ["Madina", "Sevinch", "Dilnoza", "Gulnora", "Mohinur", "Zarina", "Nilufar", "Shahzoda"]
    dirs = _dirs(con)[:8]
    td = clock.today()
    plan = ["ariza"] * 22 + ["hujjat"] * 16 + ["imtihon"] * 12 + ["shartnoma"] * 10 + ["rad"] * 6
    for i, st in enumerate(plan):
        f = rnd.random() < .5; s = rnd.choice(fam)
        name = f"{s}{'a' if f else ''} {rnd.choice(ism_f if f else ism_m)} (namuna)"
        ex = rnd.randint(58, 92) if st in ("imtihon", "shartnoma") else (rnd.randint(30, 54) if st == "rad" else None)
        d = (td - dt.timedelta(days=rnd.randint(0, 20))).isoformat()
        con.execute("""INSERT INTO qb_applicants(full_name,phone,direction,study_form,payment_type,stage,exam_score,contract_no,note,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (name, f"+998 9{rnd.randint(0,9)} *** ** {rnd.randint(10,99)}", rnd.choice(dirs), rnd.choice(["kunduzgi", "kunduzgi", "sirtqi"]),
                     rnd.choice(["kontrakt", "kontrakt", "kontrakt", "grant"]), st, ex,
                     f"Q-27/{1000 + i}" if st == "shartnoma" else None, "Imtihon bali past" if st == "rad" else None, d + "T09:00:00", d + "T09:00:00"))
    con.commit()

def C(request: Request, write=False, summary=False) -> Ctx:
    c = _ctx(request)
    ok = c.role.key in FULL or (not write and (c.role.key in READ or (summary and c.role.key in SUMMARY)))
    if not ok:
        rbac.audit(_con, c, "qabul: abituriyentlar", RES, False, "ruxsat yo'q")
        raise AccessDenied("⛔ Abituriyentlar oqimini Qabul komissiyasi yuritadi.")
    return c

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request, summary=True)
    from . import desks
    by_stage = {r["stage"]: r["n"] for r in db.rows(_con, "SELECT stage, COUNT(*) n FROM qb_applicants GROUP BY 1")}
    by_dir = db.rows(_con, """SELECT direction, COUNT(*) n, SUM(stage='ariza') ariza, SUM(stage='hujjat') hujjat, SUM(stage='imtihon') imtihon,
                              SUM(stage='shartnoma') shartnoma, SUM(stage='buyruq') buyruq, SUM(stage='rad') rad FROM qb_applicants GROUP BY 1 ORDER BY n DESC""")
    by_pay = db.rows(_con, """SELECT payment_type, COUNT(*) n, SUM(stage IN ('shartnoma','buyruq')) shartnoma FROM qb_applicants
                              WHERE stage<>'rad' GROUP BY 1 ORDER BY n DESC""")
    rbac.audit(_con, c, "qabul: umumiy", RES, True)
    return {"can_edit": c.role.key in FULL, "summary_only": c.role.key in SUMMARY, "by_payment": by_pay, "stages": STAGES, "next": NEXT, "pass_score": PASS_SCORE, "by_stage": by_stage, "by_direction": by_dir,
            "directions": _dirs(_con), "desk": desks.admissions(_con)}

@router.get(P + "/applicants")
def api_list(request: Request, stage: str = "", direction: str = "", q: str = ""):
    c = C(request)
    w, a = ["1=1"], []
    if stage in STAGES: w.append("stage=?"); a.append(stage)
    if direction: w.append("direction=?"); a.append(direction)
    if q.strip(): w.append("(full_name LIKE ? OR contract_no LIKE ?)"); a += [f"%{q.strip()}%"] * 2
    rows = db.rows(_con, f"SELECT * FROM qb_applicants WHERE {' AND '.join(w)} ORDER BY updated_at DESC LIMIT 400", a)
    for r in rows: r["stage_label"] = STAGES.get(r["stage"], r["stage"])
    return {"items": rows}

class AppIn(BaseModel):
    full_name: str = Field(..., min_length=5, max_length=120)
    phone: str = Field("", max_length=30)
    direction: str
    study_form: str = "kunduzgi"
    payment_type: str = "kontrakt"

@router.post(P + "/applicants")
def api_create(body: AppIn, request: Request):
    c = C(request, True)
    if len(body.full_name.strip()) < 5: raise HTTPException(400, "F.I.Sh. ni to'liq kiriting")
    if body.direction not in _dirs(_con): raise HTTPException(400, "Yo'nalishni tanlang")
    if body.study_form not in FORMS: raise HTTPException(400, "Ta'lim shakli noto'g'ri")
    if body.payment_type not in PAYS: raise HTTPException(400, "To'lov turi noto'g'ri")
    i = _con.execute("""INSERT INTO qb_applicants(full_name,phone,direction,study_form,payment_type,stage,created_by,created_at,updated_at)
                        VALUES(?,?,?,?,?,'ariza',?,?,?)""", (body.full_name.strip(), body.phone.strip(), body.direction, body.study_form,
                                                             body.payment_type, c.user["id"], _now(), _now())).lastrowid
    _log(i, c, "ariza qabul qilindi"); _con.commit()
    rbac.audit(_con, c, "qabul: yangi ariza", RES, True, f"#{i}")
    return {"ok": True, "id": i}

def _log(i, c, action, note=""):
    _con.execute("INSERT INTO qb_log(app_id,ts,user_name,action,note) VALUES(?,?,?,?,?)", (i, _now(), c.user["full_name"], action, note))

class AdvIn(BaseModel):
    exam_score: int | None = None
    contract_no: str = ""
    note: str = Field("", max_length=300)

@router.post(P + "/applicants/{aid}/advance")
def api_advance(aid: int, body: AdvIn, request: Request):
    c = C(request, True)
    r = db.one(_con, "SELECT * FROM qb_applicants WHERE id=?", (aid,))
    if not r: raise HTTPException(404)
    to = NEXT.get(r["stage"])
    if not to: raise HTTPException(409, "Bu bosqichdan keyingi qadam yo'q")
    if to == "shartnoma":
        if body.exam_score is None and r["exam_score"] is None: raise HTTPException(400, "Imtihon balini kiriting")
    if to == "imtihon":
        if body.exam_score is None: raise HTTPException(400, "Imtihon / suhbat balini kiriting")
        if not 0 <= body.exam_score <= 100: raise HTTPException(400, "Ball 0–100")
        if body.exam_score < PASS_SCORE: raise HTTPException(400, f"O'tish bali {PASS_SCORE}. Past bo'lsa — «Rad etish»")
    cn = body.contract_no.strip() or (f"Q-27/{aid:04d}" if to == "shartnoma" else None)
    _con.execute("UPDATE qb_applicants SET stage=?, exam_score=COALESCE(?, exam_score), contract_no=COALESCE(?, contract_no), updated_at=? WHERE id=?",
                 (to, body.exam_score if to == "imtihon" else None, cn, _now(), aid))
    _log(aid, c, STAGES[to], body.note); _con.commit()
    rbac.audit(_con, c, "qabul: bosqich", RES, True, f"#{aid} → {to}")
    return {"ok": True, "stage": to}

@router.post(P + "/applicants/{aid}/reject")
def api_reject(aid: int, body: AdvIn, request: Request):
    c = C(request, True)
    r = db.one(_con, "SELECT * FROM qb_applicants WHERE id=?", (aid,))
    if not r: raise HTTPException(404)
    if r["stage"] in ("buyruq", "rad"): raise HTTPException(409, "Rad etib bo'lmaydi")
    if len(body.note.strip()) < 3: raise HTTPException(400, "Sababini yozing")
    _con.execute("UPDATE qb_applicants SET stage='rad', note=?, updated_at=? WHERE id=?", (body.note.strip(), _now(), aid))
    _log(aid, c, "rad etildi", body.note); _con.commit()
    rbac.audit(_con, c, "qabul: rad", RES, True, f"#{aid}")
    return {"ok": True}

@router.post(P + "/order")
def api_order(request: Request, direction: str):
    """Yo'nalish bo'yicha shartnoma tuzilganlar → qabul buyrug'i loyihasi (.docx). Ular «buyruq» bosqichiga o'tadi."""
    c = C(request, True)
    rows = db.rows(_con, "SELECT * FROM qb_applicants WHERE stage='shartnoma' AND direction=? ORDER BY full_name", (direction,))
    if not rows: raise HTTPException(409, "Bu yo'nalishda shartnoma tuzilgan abituriyent yo'q")
    from docx import Document
    from docx.shared import Pt
    doc = Document(); st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(12)
    doc.add_heading("BUYRUQ LOYIHASI", level=1)
    doc.add_paragraph(f"Talabalikka qabul qilish to'g'risida · {clock.today().strftime('%d.%m.%Y')}")
    doc.add_paragraph(f"Qabul komissiyasi qaroriga asosan quyidagi abituriyentlar «{direction}» ta'lim yo'nalishi 1-kursiga talabalikka qabul qilinsin:")
    t = doc.add_table(rows=1, cols=5); t.style = "Table Grid"
    for i, h in enumerate(["№", "F.I.Sh.", "Ta'lim shakli", "To'lov turi", "Shartnoma"]): t.rows[0].cells[i].text = h
    for n, r in enumerate(rows, 1):
        cs = t.add_row().cells
        for i, v in enumerate([str(n), r["full_name"], r["study_form"] or "", r["payment_type"] or "", r["contract_no"] or ""]): cs[i].text = v
    doc.add_paragraph("\nAsos: qabul komissiyasi bayonnomasi, to'lov-kontrakt shartnomalari.\n\nRektor ____________________")
    buf = io.BytesIO(); doc.save(buf)
    batch = f"{direction[:30]} · {_now()[:10]}"
    _con.execute(f"UPDATE qb_applicants SET stage='buyruq', order_batch=?, updated_at=? WHERE id IN ({','.join('?' * len(rows))})",
                 [batch, _now()] + [r["id"] for r in rows])
    for r in rows: _log(r["id"], c, "qabul buyrug'i loyihasiga kiritildi")
    _con.commit()
    rbac.audit(_con, c, "qabul: buyruq loyihasi", RES, True, f"{direction} · {len(rows)} ta")
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="qabul-buyrugi-loyihasi.docx"'})

def pending(c: Ctx) -> list[dict]:
    if _con is None or c.role.key not in FULL: return []
    out = []
    n = db.one(_con, "SELECT COUNT(*) n FROM qb_applicants WHERE stage='ariza' AND created_at < ?",
               ((clock.today() - dt.timedelta(days=3)).isoformat(),))["n"]
    if n: out.append({"kind": "qabul", "title": f"{n} ta ariza 3 kundan beri hujjat tekshiruvini kutmoqda", "sub": "Qabul", "due": clock.today().isoformat(),
                      "view": "qabul", "src": "Qabul", "sign": False})
    m = db.one(_con, "SELECT COUNT(*) n FROM qb_applicants WHERE stage='shartnoma'")["n"]
    if m: out.append({"kind": "qabul", "title": f"{m} ta abituriyent buyruq loyihasini kutmoqda", "sub": "Qabul", "due": None,
                      "view": "qabul", "src": "Qabul", "sign": False})
    return out
