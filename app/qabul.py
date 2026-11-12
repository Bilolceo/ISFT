"""«Qabul» — Qabul komissiyasi: abituriyentlar oqimi (docs/qabul.md).

ariza → hujjatlar tekshirildi → imtihon/suhbat → shartnoma → qabul buyrug'i loyihasi (yo'nalish bo'yicha .docx ro'yxat) | rad etildi.
Buyruq loyihasi ikki bosqichli: loyiha tuzish bosqichni o'zgartirmaydi; alohida tasdiq (to'plam) abituriyentlarni «buyruq»ga o'tkazadi,
to'plam imzolangan buyruq raqami kiritilguncha qaytarilishi mumkin (qb_batches — pastda).
Demo — sintetik abituriyentlar (haqiqiy shaxslar emas). Jamlangan qabul tahlili (Marketing bilan bir xil) — app/desks.admissions.
Ruxsat: qabul — to'liq; rektor, prorektor_oquv, marketing — faqat ko'rish (jamlangan + ro'yxat ismlarsiz emas, chunki ish ro'yxati).
"""
import datetime as dt, io, json, random
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
CREATE TABLE IF NOT EXISTS qb_batches(id INTEGER PRIMARY KEY, direction TEXT, label TEXT, status TEXT DEFAULT 'loyiha', ids TEXT, n INT, docx BLOB,
  created_by INT, created_by_name TEXT, created_at TEXT, confirmed_at TEXT, confirmed_by INT, confirmed_by_name TEXT, closed_at TEXT, reg_no TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS qb_log(id INTEGER PRIMARY KEY, app_id INT, ts TEXT, user_name TEXT, action TEXT, note TEXT);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat()

def init(con):
    con.executescript(SCHEMA)
    if "batch_id" not in {r[1] for r in con.execute("PRAGMA table_info(qb_applicants)")}:
        con.execute("ALTER TABLE qb_applicants ADD COLUMN batch_id INT")
    con.commit()
    try: seed_demo(con)
    except Exception as e: print("qabul.seed:", e)
    try: migrate_batches(con)
    except Exception as e: print("qabul.migrate_batches:", e)

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
    """summary=True — faqat jamlangan ko'rinish (rbac aggregate_only(ADMISSIONS): kengash, moliya prorektori)."""
    c = _ctx(request)
    ok = c.role.key in FULL or (not write and (c.role.key in READ or (summary and c.can(RES) and c.aggregate_only(RES))))
    if not ok:
        rbac.audit(_con, c, "qabul: abituriyentlar", RES, False, "ruxsat yo'q")
        raise AccessDenied("⛔ Abituriyentlar oqimini Qabul komissiyasi yuritadi.")
    return c

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request, summary=True)
    summary_only = c.role.key not in FULL and c.role.key not in READ
    by_stage = {r["stage"]: r["n"] for r in db.rows(_con, "SELECT stage, COUNT(*) n FROM qb_applicants GROUP BY 1")}
    by_dir = db.rows(_con, """SELECT direction, COUNT(*) n, SUM(stage='ariza') ariza, SUM(stage='hujjat') hujjat, SUM(stage='imtihon') imtihon,
                              SUM(stage='shartnoma') shartnoma, SUM(stage='buyruq') buyruq, SUM(stage='rad') rad FROM qb_applicants GROUP BY 1 ORDER BY n DESC""")
    by_pay = db.rows(_con, """SELECT payment_type, COUNT(*) n, SUM(stage IN ('shartnoma','buyruq')) shartnoma FROM qb_applicants
                              WHERE stage<>'rad' GROUP BY 1 ORDER BY n DESC""")
    rbac.audit(_con, c, "qabul: umumiy", RES, True)
    out = {"can_edit": c.role.key in FULL, "summary_only": summary_only, "stages": STAGES, "by_stage": by_stage, "by_direction": by_dir, "by_payment": by_pay}
    if not summary_only:   # ish ma'lumotlari (bosqich oqimi, yo'nalishlar ro'yxati, o'tgan kampaniya tahlili va CSV havolasi) — jamlangan rollarga berilmaydi
        from . import desks
        out.update({"next": NEXT, "pass_score": PASS_SCORE, "directions": _dirs(_con), "forms": list(FORMS), "payments": list(PAYS),
                    "batches": {r["status"]: r["n"] for r in db.rows(_con, "SELECT status, COUNT(*) n FROM qb_batches GROUP BY 1")}, "desk": desks.admissions(_con)})
    return out

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

# ---------------------------------------------------------------------------------------------
# Qabul buyrug'i to'plami (qb_batches): loyiha → kiritilgan → imzolangan | bekor
#   loyiha     — POST /order: .docx loyiha tuziladi, abituriyentlar bosqichi O'ZGARMAYDI (shartnomada qoladi); qayta chaqirilsa — shu
#                yo'nalishning ochiq loyihasi yangilanadi (ikkinchi to'plam ochilmaydi);
#   kiritilgan — POST /batches/{id}/confirm: alohida, aniq tasdiq — abituriyentlar «buyruq» bosqichiga o'tadi; fayl qayta yuklab olinadi;
#                POST /batches/{id}/rollback — xato bo'lsa, to'plam bekor qilinadi va abituriyentlar «shartnoma»ga qaytadi;
#   imzolangan — POST /batches/{id}/finalize {reg_no}: rektor imzolagan buyruq raqami yoziladi — shundan keyin qaytarib bo'lmaydi.
# «Buyruqlar» moduli (orders «qabul» turi) bilan avtomatik bog'lanmaydi: u yerda ro'yxat talabalar bazasidagi (students) yozuvlardan tuziladi,
# abituriyent esa hali talaba emas (HEMIS ID yo'q). Imzolangan buyruq raqami shu yerga qo'lda kiritiladi (finalize).
# ---------------------------------------------------------------------------------------------
BATCH_ST = {"loyiha": "Loyiha (bosqich o'zgarmagan)", "kiritilgan": "Buyruq loyihasiga kiritilgan", "imzolangan": "Buyruq imzolangan", "bekor": "Bekor qilingan"}
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def _order_docx(direction: str, rows: list[dict], date: str) -> bytes:
    from docx import Document
    from docx.shared import Pt
    doc = Document(); st = doc.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(12)
    doc.add_heading("BUYRUQ LOYIHASI", level=1)
    doc.add_paragraph(f"Talabalikka qabul qilish to'g'risida · {date[8:10]}.{date[5:7]}.{date[:4]}")
    doc.add_paragraph(f"Qabul komissiyasi qaroriga asosan quyidagi abituriyentlar «{direction}» ta'lim yo'nalishi 1-kursiga talabalikka qabul qilinsin:")
    t = doc.add_table(rows=1, cols=5); t.style = "Table Grid"
    for i, h in enumerate(["№", "F.I.Sh.", "Ta'lim shakli", "To'lov turi", "Shartnoma"]): t.rows[0].cells[i].text = h
    for n, r in enumerate(rows, 1):
        cs = t.add_row().cells
        for i, v in enumerate([str(n), r["full_name"], r["study_form"] or "", r["payment_type"] or "", r["contract_no"] or ""]): cs[i].text = v
    doc.add_paragraph("\nAsos: qabul komissiyasi bayonnomasi, to'lov-kontrakt shartnomalari.\n\nRektor ____________________")
    buf = io.BytesIO(); doc.save(buf)
    return buf.getvalue()

def _batch(bid: int) -> dict:
    b = db.one(_con, "SELECT id, direction, label, status, ids, n, created_by, created_by_name, created_at, confirmed_at, confirmed_by_name, closed_at, reg_no, note FROM qb_batches WHERE id=?", (bid,))
    if not b: raise HTTPException(404, "Buyruq to'plami topilmadi")
    return b

def _batch_view(b: dict) -> dict:
    return {**{k: b[k] for k in ("id", "direction", "label", "status", "n", "created_by_name", "created_at", "confirmed_at", "confirmed_by_name", "closed_at", "reg_no", "note")},
            "status_label": BATCH_ST.get(b["status"], b["status"]), "can_confirm": b["status"] == "loyiha",
            "can_rollback": b["status"] in ("loyiha", "kiritilgan"), "can_finalize": b["status"] == "kiritilgan", "can_download": b["status"] != "bekor"}

def _docx_response(data: bytes, bid: int) -> Response:
    return Response(data, media_type=DOCX, headers={"Content-Disposition": 'attachment; filename="qabul-buyrugi-loyihasi.docx"', "X-Qabul-Batch": str(bid),
                                                    "Access-Control-Expose-Headers": "X-Qabul-Batch"})

def migrate_batches(con) -> int:
    """Eski oqim (loyiha tuzilishi bilan bosqich o'zgargan): «buyruq» bosqichidagi, to'plam yozuvi yo'q abituriyentlar uchun «kiritilgan» to'plam. Idempotent."""
    n = 0
    for r in db.rows(con, """SELECT order_batch label, direction, GROUP_CONCAT(id) ids, COUNT(*) n, MAX(updated_at) ts FROM qb_applicants
                             WHERE stage='buyruq' AND order_batch IS NOT NULL AND batch_id IS NULL GROUP BY order_batch, direction"""):
        ids = [int(x) for x in r["ids"].split(",")]
        bid = con.execute("""INSERT INTO qb_batches(direction,label,status,ids,n,created_by_name,created_at,confirmed_at,confirmed_by_name,note)
                             VALUES(?,?,'kiritilgan',?,?,?,?,?,?,?)""", (r["direction"], r["label"], json.dumps(ids), r["n"], "Qabul komissiyasi", r["ts"], r["ts"],
                                                                      "Qabul komissiyasi", "avvalgi oqimdan ko'chirildi")).lastrowid
        con.execute(f"UPDATE qb_applicants SET batch_id=? WHERE id IN ({','.join('?' * len(ids))})", [bid] + ids); n += 1
    if n: con.commit()
    return n

@router.post(P + "/order")
def api_order(request: Request, direction: str):
    """Yo'nalish bo'yicha shartnoma tuzilganlar → qabul buyrug'i LOYIHASI (.docx). Bosqich o'zgarmaydi — abituriyentlar «buyruq» bosqichiga
    faqat alohida tasdiqdan keyin o'tadi (POST /batches/{id}/confirm). Javob — .docx; to'plam raqami X-Qabul-Batch sarlavhasida."""
    c = C(request, True)
    rows = db.rows(_con, "SELECT * FROM qb_applicants WHERE stage='shartnoma' AND direction=? ORDER BY full_name", (direction,))
    if not rows: raise HTTPException(409, "Bu yo'nalishda shartnoma tuzilgan abituriyent yo'q")
    data = _order_docx(direction, rows, _now()[:10])
    ids = [r["id"] for r in rows]; label = f"{direction[:30]} · {_now()[:10]}"
    ex = db.one(_con, "SELECT id FROM qb_batches WHERE direction=? AND status='loyiha' ORDER BY id DESC LIMIT 1", (direction,))
    if ex:
        bid = ex["id"]
        _con.execute("UPDATE qb_batches SET label=?, ids=?, n=?, docx=?, created_by=?, created_by_name=?, created_at=? WHERE id=?",
                     (label, json.dumps(ids), len(ids), data, c.user["id"], c.user["full_name"], _now(), bid))
    else:
        bid = _con.execute("INSERT INTO qb_batches(direction,label,status,ids,n,docx,created_by,created_by_name,created_at) VALUES(?,?,'loyiha',?,?,?,?,?,?)",
                           (direction, label, json.dumps(ids), len(ids), data, c.user["id"], c.user["full_name"], _now())).lastrowid
    _con.commit()
    rbac.audit(_con, c, "qabul: buyruq loyihasi", RES, True, f"{direction} · {len(rows)} ta · to'plam #{bid} (bosqich o'zgarmadi)")
    return _docx_response(data, bid)

@router.get(P + "/batches")
def api_batches(request: Request, status: str = ""):
    C(request)
    w, a = ("status=?", [status]) if status in BATCH_ST else ("status!='bekor'", [])
    rows = db.rows(_con, f"""SELECT id, direction, label, status, ids, n, created_by, created_by_name, created_at, confirmed_at, confirmed_by_name, closed_at, reg_no, note
                             FROM qb_batches WHERE {w} ORDER BY id DESC LIMIT 200""", a)
    return {"items": [_batch_view(b) for b in rows], "statuses": BATCH_ST}

@router.get(P + "/batches/{bid}/docx")
def api_batch_docx(bid: int, request: Request):
    """Loyihani qayta yuklab olish (to'plam tuzilgan paytdagi ro'yxat bilan)."""
    c = C(request); b = _batch(bid)
    if b["status"] == "bekor": raise HTTPException(410, "To'plam bekor qilingan")
    data = (db.one(_con, "SELECT docx FROM qb_batches WHERE id=?", (bid,)) or {}).get("docx")
    if not data:    # eski oqimdan ko'chirilgan to'plam — fayl saqlanmagan, ro'yxatdan qayta tuziladi
        ids = json.loads(b["ids"] or "[]")
        rows = db.rows(_con, f"SELECT * FROM qb_applicants WHERE id IN ({','.join('?' * len(ids)) or 'NULL'}) ORDER BY full_name", ids)
        data = _order_docx(b["direction"], rows, (b["created_at"] or _now())[:10])
    rbac.audit(_con, c, "qabul: buyruq loyihasini yuklab olish", RES, True, f"to'plam #{bid}")
    return _docx_response(bytes(data), bid)

@router.post(P + "/batches/{bid}/confirm")
def api_batch_confirm(bid: int, request: Request):
    """Aniq tasdiq: to'plamdagi (hali «shartnoma» bosqichida turgan) abituriyentlar «buyruq» bosqichiga o'tadi."""
    c = C(request, True); b = _batch(bid)
    if b["status"] != "loyiha": raise HTTPException(409, f"To'plam holati: {BATCH_ST.get(b['status'], b['status'])} — tasdiqlab bo'lmaydi")
    ids = json.loads(b["ids"] or "[]")
    rows = db.rows(_con, f"SELECT id FROM qb_applicants WHERE stage='shartnoma' AND id IN ({','.join('?' * len(ids)) or 'NULL'})", ids)
    if len(rows) != len(ids):   # loyiha tuzilgandan keyin kimdir rad etilgan yoki boshqa to'plamga o'tgan — fayl eskirgan
        raise HTTPException(409, f"Ro'yxat o'zgargan: loyihadagi {len(ids)} tadan {len(rows)} tasi «shartnoma» bosqichida. Loyihani qayta tuzing.")
    _con.execute(f"UPDATE qb_applicants SET stage='buyruq', order_batch=?, batch_id=?, updated_at=? WHERE id IN ({','.join('?' * len(ids))})",
                 [b["label"], bid, _now()] + ids)
    for i in ids: _log(i, c, "qabul buyrug'i loyihasiga kiritildi", f"to'plam #{bid}")
    _con.execute("UPDATE qb_batches SET status='kiritilgan', confirmed_at=?, confirmed_by=?, confirmed_by_name=? WHERE id=?", (_now(), c.user["id"], c.user["full_name"], bid))
    _con.commit()
    rbac.audit(_con, c, "qabul: buyruq to'plami tasdiqlandi", RES, True, f"#{bid} · {b['direction']} · {len(ids)} ta → buyruq")
    return {"ok": True, "moved": len(ids), "batch": _batch_view(_batch(bid))}

class BatchIn(BaseModel):
    note: str = Field("", max_length=300)
    reg_no: str = Field("", max_length=40)

@router.post(P + "/batches/{bid}/rollback")
def api_batch_rollback(bid: int, request: Request, body: BatchIn | None = None):
    """To'plamni bekor qilish: loyiha — shunchaki yopiladi; kiritilgan — abituriyentlar «shartnoma» bosqichiga qaytadi. Imzolangandan keyin — yo'q."""
    c = C(request, True); b = _batch(bid)
    if b["status"] not in ("loyiha", "kiritilgan"):
        raise HTTPException(409, "Buyruq imzolangan — to'plamni qaytarib bo'lmaydi" if b["status"] == "imzolangan" else "To'plam allaqachon bekor qilingan")
    back = 0
    if b["status"] == "kiritilgan":
        back = _con.execute("UPDATE qb_applicants SET stage='shartnoma', order_batch=NULL, batch_id=NULL, updated_at=? WHERE batch_id=? AND stage='buyruq'", (_now(), bid)).rowcount
        for i in json.loads(b["ids"] or "[]"): _log(i, c, "qabul buyrug'i loyihasidan qaytarildi", f"to'plam #{bid}")
    _con.execute("UPDATE qb_batches SET status='bekor', closed_at=?, note=? WHERE id=?", (_now(), ((body.note if body else "") or "").strip() or None, bid))
    _con.commit()
    rbac.audit(_con, c, "qabul: buyruq to'plami bekor qilindi", RES, True, f"#{bid} · {b['direction']} · {back} ta → shartnoma")
    return {"ok": True, "returned": back, "batch": _batch_view(_batch(bid))}

@router.post(P + "/batches/{bid}/finalize")
def api_batch_finalize(bid: int, body: BatchIn, request: Request):
    """Rektor imzolagan buyruq raqami kiritiladi — to'plam yakunlanadi (endi qaytarib bo'lmaydi)."""
    c = C(request, True); b = _batch(bid)
    if b["status"] != "kiritilgan": raise HTTPException(409, "Faqat tasdiqlangan (kiritilgan) to'plam yakunlanadi")
    if len(body.reg_no.strip()) < 3: raise HTTPException(400, "Imzolangan buyruq raqamini kiriting")
    _con.execute("UPDATE qb_batches SET status='imzolangan', reg_no=?, closed_at=? WHERE id=?", (body.reg_no.strip(), _now(), bid)); _con.commit()
    rbac.audit(_con, c, "qabul: buyruq to'plami yakunlandi", RES, True, f"#{bid} · {body.reg_no.strip()}")
    return {"ok": True, "batch": _batch_view(_batch(bid))}

def pending(c: Ctx) -> list[dict]:
    if _con is None or c.role.key not in FULL: return []
    out = []
    n = db.one(_con, "SELECT COUNT(*) n FROM qb_applicants WHERE stage='ariza' AND created_at < ?",
               ((clock.today() - dt.timedelta(days=3)).isoformat(),))["n"]
    if n: out.append({"kind": "qabul", "title": f"{n} ta ariza 3 kundan beri hujjat tekshiruvini kutmoqda", "sub": "Qabul", "due": clock.today().isoformat(),
                      "view": "qabul", "src": "Qabul", "sign": False})
    for b in db.rows(_con, "SELECT id, direction, n, created_at FROM qb_batches WHERE status='loyiha' ORDER BY id"):
        out.append({"id": f"batch{b['id']}", "kind": "qabul", "title": f"Qabul buyrug'i loyihasi tasdiqlanmagan: {b['direction']} ({b['n']} ta abituriyent)",
                    "sub": f"Qabul · loyiha {str(b['created_at'])[:10]} · tasdiqlansa abituriyentlar «buyruq» bosqichiga o'tadi", "due": None,
                    "view": "qabul", "src": "Qabul", "sign": False})
    m = db.one(_con, "SELECT COUNT(*) n FROM qb_applicants WHERE stage='shartnoma'")["n"]
    if m: out.append({"kind": "qabul", "title": f"{m} ta abituriyent buyruq loyihasini kutmoqda", "sub": "Qabul", "due": None,
                      "view": "qabul", "src": "Qabul", "sign": False})
    return out
