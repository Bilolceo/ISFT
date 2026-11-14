"""«HEMIS almashinuvi» — ISFT Core va HEMIS ma'lumotlarini bir xil holda saqlash. Batafsil: docs/hemis.md.

Huquqiy holat: VMQ 30.12.2024 № 913 (nodavlat OTM uchun HEMIS integratsiyasi) 03.07.2026 dan VMQ № 353 bilan bekor qilingan; o'rniga
nima kelgani noma'lum — YURIST ANIQLASHI KERAK. Amalda ISFT HEMIS va ISFT Core'ni mos holda yuritishi shart.

1. IMPORT (fayl asosida): HEMIS eksporti (.xlsx / .csv) — talabalar, guruhlar, o'qituvchilar, o'quv yuklamasi, baholar.
   Ustun xaritasi bag'rikeng (app/hemis_map.py), profil sifatida saqlanadi. Avval DRY-RUN: yangi / o'zgargan / topilmadi / ziddiyatli;
   «Qo'llash» — bitta tranzaksiya: o'zgarishdan oldingi holat (snapshot) + audit; xato bo'lsa hammasi qaytariladi.
   HECH NARSA O'CHIRILMAYDI: HEMIS faylida yo'q yozuv «HEMIS'da topilmadi» deb ko'rib chiqishga belgilanadi (hemis_missing).
   Qoida: ISFT Core'da bo'sh maydon — HEMIS qiymati bilan to'ldiriladi («o'zgargan»); ikkalasida ham qiymat bor va farqli —
   FARQLAR NAVBATIGA (registrator qaror qiladi), avtomatik ustiga yozilmaydi (sozlamada `auto_fields` bilan o'zgartiriladi).
2. FARQLAR NAVBATI: maydon darajasidagi farqlar (holat, guruh, ta'lim shakli, fuqarolik, ism-sharif — kirill/lotin normallashgan),
   egasi — Registrator ofisi boshlig'i, qaror: HEMIS to'g'ri (Core yangilanadi) / ISFT Core to'g'ri (HEMIS'ga tuzatish eksportiga) /
   qo'lda (qiymat kiritiladi: Core yangilanadi va tuzatish eksportiga). Har qaror jurnalga va auditga yoziladi. Nazorat markazida —
   N kundan ortiq hal qilinmagan farqlar (app/nazorat.py, oxirgi bo'lim).
3. EKSPORT: ISFT Core egalik qiladigan ma'lumot — LRS testlari asosida oraliq ballar, masofaviy talabalar davomati (LRS faolligidan,
   QOIDA SOZLANADI VA TASDIQLANMAGAN), yuzma-yuz qaydnoma natijalari, tuzatishlar — .xlsx (shablon ustunlari sozlanadi), SHA-256, jurnal.
4. API ULAGICHI: app/hemis_api.py — skelet, standart o'chiq, token faqat secret_store'da, «Ulanishni tekshirish» — bitta GET. TASDIQLANMAGAN.
5. MA'LUMOT SIFATI: takroriy HEMIS ID, HEMIS IDsiz talabalar, guruh shakliga mos kelmagan talabalar va h.k.

Ruxsatlar (har so'rov audit jurnalida, resurs «hemis»):
  talabalar (Registrator ofisi boshlig'i), masofaviy (Masofaviy ta'lim bo'limi boshlig'i) — hammasi, shu jumladan sozlamalar va API;
  registrator_xodim — import, farqlar, eksport (sozlamalarsiz);  rektor — faqat jamlangan sonlar;  boshqalar — 403.
"""
from __future__ import annotations
import datetime as dt, hashlib, io, json, re, threading
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac, hemis_map as HM, hemis_api as HA, hemis_plan as HP
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/hemis"
RES = "hemis"

REG, REG_X, DIST = "talabalar", "registrator_xodim", "masofaviy"
HEADS = (REG, DIST)
MANAGE = (REG, REG_X, DIST)
LEAD = ("rektor",)
ALL = MANAGE + LEAD
OWNER_UNIT = "talabalar"            # farqlar egasi — Registrator ofisi

LEGAL_NOTE = ("VMQ № 913 (HEMIS integratsiyasi) 03.07.2026 dan VMQ № 353 bilan bekor qilingan; o'rniga qanday talab kelgani "
              "noma'lum — yurist aniqlashi kerak. HEMIS API hujjatlari olinmagan: integratsiya fayl orqali.")
FIELD_T = HP.FIELD_T
DECISIONS = {"hemis": "HEMIS to'g'ri", "core": "ISFT Core to'g'ri", "qolda": "Qo'lda tuzatildi", "mos": "Keyingi importda mos keldi"}
DEFAULTS = {
    "api_enabled": False, "api_base_url": "", "api_probe_path": "", "api_auth_scheme": "Bearer", "api_probe_auth": False,
    "auto_fields": [],                                   # farqni navbatsiz HEMIS qiymati bilan yozish (masalan ["payment_type"])
    "hemis_id_regex": r"^\d{10,16}$",                    # TASDIQLANMAGAN: talaba HEMIS ID formati
    "att_rule": {"min_minutes": 30, "min_statements": 3, "weeks": 4},     # TASDIQLANMAGAN davomat qoidasi
    "grade_rule": {"enabled": True, "scale_max": 30, "min_lessons": 1, "label": "Oraliq nazorat (LRS testlari)"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS hemis_settings(k TEXT PRIMARY KEY, v TEXT, updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS hemis_profiles(id INTEGER PRIMARY KEY, entity TEXT, name TEXT, mapping TEXT, created_by INT, created_name TEXT,
  created_at TEXT, UNIQUE(entity, name));
CREATE TABLE IF NOT EXISTS hemis_imports(id INTEGER PRIMARY KEY, entity TEXT, filename TEXT, sha256 TEXT, size INT, ts TEXT, user_id INT,
  user_name TEXT, status TEXT DEFAULT 'preview', scope TEXT DEFAULT 'qisman', profile_id INT, mapping TEXT, header_row INT, raw_rows TEXT,
  counts TEXT, applied_at TEXT, applied_by INT, applied_name TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS hemis_snapshots(id INTEGER PRIMARY KEY, import_id INT, tbl TEXT, row_id INT, op TEXT, before TEXT, after TEXT);
CREATE INDEX IF NOT EXISTS ix_hemis_snap ON hemis_snapshots(import_id);
CREATE TABLE IF NOT EXISTS hemis_diffs(id INTEGER PRIMARY KEY, entity TEXT, ref TEXT, label TEXT, core_id INT, core_key TEXT, field TEXT,
  core_value TEXT, hemis_value TEXT, status TEXT DEFAULT 'ochiq', decision TEXT, final_value TEXT, owner_user INT, created_at TEXT,
  first_import INT, last_import INT, resolved_at TEXT, resolved_by INT, resolved_name TEXT, note TEXT, export_pending INT DEFAULT 0,
  exported_id INT);
CREATE INDEX IF NOT EXISTS ix_hemis_diffs ON hemis_diffs(status, entity, ref, field);
CREATE TABLE IF NOT EXISTS hemis_diff_log(id INTEGER PRIMARY KEY, diff_id INT, ts TEXT, user_id INT, user_name TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS hemis_missing(id INTEGER PRIMARY KEY, entity TEXT, core_id INT, ref TEXT, label TEXT, status TEXT DEFAULT 'ochiq',
  since TEXT, first_import INT, last_import INT, reviewed_by INT, reviewed_name TEXT, reviewed_at TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_hemis_miss ON hemis_missing(status, entity, ref);
CREATE TABLE IF NOT EXISTS hemis_exports(id INTEGER PRIMARY KEY, kind TEXT, ts TEXT, user_id INT, user_name TEXT, rows INT, sha256 TEXT,
  content_sha256 TEXT, file TEXT, params TEXT, rule TEXT);
"""


def init(con):
    con.executescript(SCHEMA)
    for tbl in ("groups_", "teachers"):
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({tbl})").fetchall()}
        if "hemis_id" not in cols: con.execute(f"ALTER TABLE {tbl} ADD COLUMN hemis_id TEXT")
    cols = {r[1] for r in con.execute("PRAGMA table_info(students)").fetchall()}
    if "citizenship" not in cols: con.execute("ALTER TABLE students ADD COLUMN citizenship TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS ix_students_hemis ON students(hemis_id)")
    con.commit()


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def C(request: Request) -> Ctx: return _ctx(request)
def _now() -> str: return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def _j(v) -> str: return json.dumps(v, ensure_ascii=False, default=str)


def guard(c: Ctx, action: str, roles=MANAGE, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"hemis: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ HEMIS almashinuvi: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")


def _audit_tx(con, c: Ctx, action: str, detail: str):
    """Audit yozuvi JORIY tranzaksiya ichida (rbac.audit commit qiladi — qo'llash o'rtasida chaqirilmaydi)."""
    con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                (_now(), c.user["id"], c.user["full_name"], c.title, c.channel, f"hemis: {action}", RES, 1, detail[:300]))


def _inv():
    try:
        from . import nazorat as NZ; NZ.invalidate()
    except Exception:
        pass


# =============================================================================================
# Sozlamalar (token — bu yerda EMAS: secret_store)
# =============================================================================================
def settings(con=None) -> dict:
    con = con or _con
    out = json.loads(json.dumps(DEFAULTS))
    for r in db.rows(con, "SELECT k, v FROM hemis_settings"):
        if r["k"] in DEFAULTS or r["k"].startswith("tpl:"):
            try: out[r["k"]] = json.loads(r["v"])
            except ValueError: pass
    return out


def set_setting(con, k: str, v, who: str = ""):
    con.execute("INSERT OR REPLACE INTO hemis_settings(k,v,updated_at,updated_by) VALUES(?,?,?,?)", (k, _j(v), _now(), who))


def owner_user(con) -> int | None:
    try:
        r = db.one(con, "SELECT head_user FROM org_units WHERE key=?", (OWNER_UNIT,))
        if r and r["head_user"]: return r["head_user"]
    except Exception:
        pass
    r = db.one(con, "SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (REG,))
    return r["id"] if r else None


def _begin(con):
    if con.in_transaction: con.commit()
    con.execute("BEGIN IMMEDIATE")


# =============================================================================================
# Import: yuklash → dry-run (ko'rib chiqish) → qo'llash
# =============================================================================================
def _profile(con, pid) -> dict | None:
    if not pid: return None
    r = db.one(con, "SELECT * FROM hemis_profiles WHERE id=?", (pid,))
    if not r: raise HTTPException(404, "Profil topilmadi")
    return json.loads(r["mapping"] or "{}")


def _parsed(con, imp: dict) -> dict:
    rows = json.loads(imp["raw_rows"] or "[]")
    prof = _profile(con, imp["profile_id"]) if imp["profile_id"] else None
    try:
        return HM.parse_rows(rows, imp["entity"], prof, json.loads(imp["mapping"] or "{}"))
    except HM.ReadError as e:
        raise HTTPException(400, str(e))


def preview_view(con, imp: dict, parsed: dict | None = None, pl: dict | None = None) -> dict:
    parsed = parsed or _parsed(con, imp)
    out = {k: imp[k] for k in ("id", "entity", "filename", "sha256", "size", "ts", "user_name", "status", "scope", "profile_id",
                                "applied_at", "applied_name", "error")}
    out.update({"entity_t": HM.ENTITIES[imp["entity"]], "header_row": parsed["header_row"], "headers": parsed["headers"],
                "map": parsed["map"], "unmapped": parsed["unmapped"], "ignored": parsed["ignored"],
                "missing_fields": [{"key": f, "title": HM.FIELDS[imp["entity"]][f][0]} for f in parsed["missing"]],
                "fields": [{"key": k, "title": t, "required": bool(rq)} for k, (t, rq) in HM.FIELDS[imp["entity"]].items()]})
    if imp["status"] != "preview":
        out["counts"] = json.loads(imp["counts"] or "{}"); out["samples"] = {}; return out
    if parsed["missing"]:
        out["counts"] = None; out["samples"] = {}; return out
    pl = pl or HP.plan(con, imp["entity"], parsed["records"], imp["scope"], settings(con).get("auto_fields"))
    out["counts"] = HP.counts(pl)
    out["samples"] = {k: v[:HP_SAMPLE] for k, v in pl["cats"].items()}
    out["samples"]["missing"] = pl["missing"][:HP_SAMPLE]
    fc = {}
    for d in pl["diffs"]: fc[d["field"]] = fc.get(d["field"], 0) + 1
    out["diff_fields"] = [{"field": k, "title": FIELD_T.get(k, k), "n": v} for k, v in sorted(fc.items(), key=lambda x: -x[1])]
    if "hours" in pl: out["hours"] = pl["hours"]
    return out


HP_SAMPLE = 150


def create_preview(c: Ctx, entity: str, raw: bytes, name: str, profile_id: int | None, scope: str) -> dict:
    if entity not in HM.FIELDS: raise HTTPException(404, "Noma'lum tur")
    if scope not in ("qisman", "toliq"): raise HTTPException(400, "Ko'lam: qisman yoki toliq")
    if not raw: raise HTTPException(400, "Fayl bo'sh")
    if not (name or "").lower().endswith((".xlsx", ".csv", ".txt")): raise HTTPException(400, "Faqat .xlsx yoki .csv (HEMIS eksporti)")
    try:
        rows = HM.read_rows(raw, name)
    except HM.ReadError as e:
        raise HTTPException(400, str(e))
    prof = _profile(_con, profile_id)
    try:
        hi = HM.find_header(rows, entity, prof)
    except HM.ReadError as e:
        raise HTTPException(400, str(e))
    pii = HM.pii_cols(rows[hi])          # JShShIR va h.k. qiymatlari bazaga (ko'rib chiqish nusxasiga ham) tushmaydi
    if pii: rows = rows[:hi + 1] + [["" if i in pii else v for i, v in enumerate(r)] for r in rows[hi + 1:]]
    sha = hashlib.sha256(raw).hexdigest()
    with _lock:
        cur = _con.execute("""INSERT INTO hemis_imports(entity,filename,sha256,size,ts,user_id,user_name,status,scope,profile_id,mapping,raw_rows)
                              VALUES(?,?,?,?,?,?,?,'preview',?,?,'{}',?)""",
                           (entity, (name or "fayl")[:120], sha, len(raw), _now(), c.user["id"], c.user["full_name"], scope, profile_id,
                            _j(rows)))
        _con.commit()
    imp = db.one(_con, "SELECT * FROM hemis_imports WHERE id=?", (cur.lastrowid,))
    out = preview_view(_con, imp)
    same = db.one(_con, "SELECT id, ts FROM hemis_imports WHERE sha256=? AND status='applied' AND entity=? ORDER BY id DESC LIMIT 1", (sha, entity))
    if same: out["warning"] = f"Shu fayl avval qo'llangan (#{same['id']}, {same['ts'][:16].replace('T', ' ')})"
    return out


def remap(c: Ctx, iid: int, mapping: dict, scope: str | None, profile_name: str | None) -> dict:
    imp = _imp(iid)
    if imp["status"] != "preview": raise HTTPException(409, "Import allaqachon yakunlangan")
    fields = set(HM.FIELDS[imp["entity"]])
    clean = {}
    for h, f in (mapping or {}).items():
        if f not in fields and f != "": raise HTTPException(400, f"Noma'lum maydon: {f}")
        clean[str(h)[:120]] = f
    sc = scope or imp["scope"]
    if sc not in ("qisman", "toliq"): raise HTTPException(400, "Ko'lam: qisman yoki toliq")
    with _lock:
        _con.execute("UPDATE hemis_imports SET mapping=?, scope=? WHERE id=?", (_j(clean), sc, iid))
        if profile_name:
            parsed = _parsed(_con, {**imp, "mapping": _j(clean)})
            full = {h: f for h, f in parsed["map"].items()}
            full.update({h: "" for h, f in clean.items() if f == ""})
            _con.execute("""INSERT INTO hemis_profiles(entity,name,mapping,created_by,created_name,created_at) VALUES(?,?,?,?,?,?)
                            ON CONFLICT(entity,name) DO UPDATE SET mapping=excluded.mapping, created_at=excluded.created_at""",
                         (imp["entity"], profile_name.strip()[:60], _j(full), c.user["id"], c.user["full_name"], _now()))
            pid = db.one(_con, "SELECT id FROM hemis_profiles WHERE entity=? AND name=?", (imp["entity"], profile_name.strip()[:60]))["id"]
            _con.execute("UPDATE hemis_imports SET profile_id=?, mapping='{}' WHERE id=?", (pid, iid))
        _con.commit()
    return preview_view(_con, _imp(iid))


def _imp(iid) -> dict:
    imp = db.one(_con, "SELECT * FROM hemis_imports WHERE id=?", (iid,))
    if not imp: raise HTTPException(404, "Import topilmadi")
    return imp


def _snap(con, iid, tbl, rid, op, before, after):
    con.execute("INSERT INTO hemis_snapshots(import_id,tbl,row_id,op,before,after) VALUES(?,?,?,?,?,?)",
                (iid, tbl, rid, op, None if before is None else _j(before), None if after is None else _j(after)))


def _write_plan(con, iid: int, pl: dict):
    for ins in pl["inserts"]:
        cols = list(ins["values"])
        cur = con.execute(f"INSERT INTO {ins['tbl']}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [ins["values"][k] for k in cols])
        _snap(con, iid, ins["tbl"], cur.lastrowid, "insert", None, ins["values"])
    for u in pl["updates"]:
        cols = list(u["set"])
        con.execute(f"UPDATE {u['tbl']} SET {','.join(k + '=?' for k in cols)} WHERE {u['idcol']}=?", [u["set"][k] for k in cols] + [u["id"]])
        _snap(con, iid, u["tbl"], u["id"], "update", u["before"], u["set"])


def _apply_diffs(con, iid: int, pl: dict, owner, now):
    ents = {d["entity"] for d in pl["diffs"]} | {e for e, _, _ in pl["equal"]} | {pl["entity"]}
    opened = {}
    for e in ents:
        for r in db.rows(con, "SELECT id, ref, field FROM hemis_diffs WHERE status='ochiq' AND entity=?", (e,)):
            opened[(e, r["ref"], r["field"])] = r["id"]
    for d in pl["diffs"]:
        k = (d["entity"], d["ref"], d["field"])
        if k in opened:
            con.execute("UPDATE hemis_diffs SET core_value=?, hemis_value=?, label=?, core_id=?, core_key=?, last_import=? WHERE id=?",
                        (d["core_value"], d["hemis_value"], d["label"], d["core_id"], d["core_key"], iid, opened[k]))
            continue
        cur = con.execute("""INSERT INTO hemis_diffs(entity,ref,label,core_id,core_key,field,core_value,hemis_value,status,owner_user,created_at,
                             first_import,last_import) VALUES(?,?,?,?,?,?,?,?,'ochiq',?,?,?,?)""",
                          (d["entity"], d["ref"], d["label"], d["core_id"], d["core_key"], d["field"], d["core_value"], d["hemis_value"],
                           owner, now, iid, iid))
        opened[k] = cur.lastrowid
        con.execute("INSERT INTO hemis_diff_log(diff_id,ts,action,detail) VALUES(?,?,?,?)", (cur.lastrowid, now, "yaratildi", f"import #{iid}"))
    closed = 0
    for k in set(pl["equal"]):
        did = opened.get(tuple(k))
        if not did: continue
        con.execute("""UPDATE hemis_diffs SET status='hal', decision='mos', resolved_at=?, resolved_name='HEMIS importi', last_import=?
                       WHERE id=? AND status='ochiq'""", (now, iid, did))
        con.execute("INSERT INTO hemis_diff_log(diff_id,ts,action,detail) VALUES(?,?,?,?)", (did, now, "mos keldi", f"import #{iid}: qiymatlar bir xil"))
        closed += 1
    return closed


def _apply_missing(con, iid: int, pl: dict, now):
    e = pl["entity"]
    opened = {r["ref"]: r["id"] for r in db.rows(con, "SELECT id, ref FROM hemis_missing WHERE status='ochiq' AND entity=?", (e,))}
    for m in pl["missing"]:
        if m["ref"] in opened:
            con.execute("UPDATE hemis_missing SET last_import=? WHERE id=?", (iid, opened[m["ref"]])); continue
        con.execute("""INSERT INTO hemis_missing(entity,core_id,ref,label,status,since,first_import,last_import) VALUES(?,?,?,?,'ochiq',?,?,?)""",
                    (e, m["core_id"], m["ref"], m["label"], now, iid, iid))
    back = 0
    for ref in set(pl["present"]):
        if ref in opened:
            con.execute("UPDATE hemis_missing SET status='qaytdi', reviewed_at=?, reviewed_name='HEMIS importi', last_import=? WHERE id=?",
                        (now, iid, opened[ref])); back += 1
    return back


def apply_import(c: Ctx, iid: int) -> dict:
    with _lock:
        imp = _imp(iid)
        if imp["status"] != "preview": raise HTTPException(409, "Bu import allaqachon qo'llangan yoki bekor qilingan")
        parsed = _parsed(_con, imp)
        if parsed["missing"]: raise HTTPException(400, "Majburiy ustunlar moslanmagan: " + ", ".join(parsed["missing"]))
        S, now = settings(), _now()
        con = _con
        try:
            _begin(con)
            pl = HP.plan(con, imp["entity"], parsed["records"], imp["scope"], S.get("auto_fields"))   # Core holati — qo'llash paytidagi
            _write_plan(con, iid, pl)
            closed = _apply_diffs(con, iid, pl, owner_user(con), now)
            back = _apply_missing(con, iid, pl, now)
            cn = {**HP.counts(pl), "diffs_closed": closed, "missing_back": back}
            con.execute("""UPDATE hemis_imports SET status='applied', counts=?, applied_at=?, applied_by=?, applied_name=?, raw_rows=NULL
                           WHERE id=?""", (_j(cn), now, c.user["id"], c.user["full_name"], iid))
            _audit_tx(con, c, "import qo'llandi", f"#{iid} {imp['entity']} {imp['filename']}: yangi {cn['new']}, o'zgargan {cn['changed']}, "
                                                   f"ziddiyatli {cn['conflicting']}, topilmadi {cn['missing']} · sha256 {imp['sha256'][:12]}")
            con.commit()
        except Exception as e:
            con.rollback()
            msg = e.detail if isinstance(e, HTTPException) else f"{type(e).__name__}: {str(e)[:200]}"
            con.execute("UPDATE hemis_imports SET error=? WHERE id=?", (str(msg)[:300], iid)); con.commit()
            rbac.audit(con, c, "hemis: import xatosi (hammasi qaytarildi)", RES, True, f"#{iid}: {msg}"[:300])
            if isinstance(e, HTTPException): raise
            raise HTTPException(500, f"Import qo'llanmadi, hech narsa o'zgarmadi: {msg}")
    _inv()
    return {"ok": True, "id": iid, "counts": cn, "snapshot_rows": len(pl["inserts"]) + len(pl["updates"])}


def cancel_import(c: Ctx, iid: int) -> dict:
    imp = _imp(iid)
    if imp["status"] != "preview": raise HTTPException(409, "Faqat ko'rib chiqilayotgan importni bekor qilish mumkin")
    _con.execute("UPDATE hemis_imports SET status='bekor', raw_rows=NULL WHERE id=?", (iid,)); _con.commit()
    return {"ok": True}


# =============================================================================================
# Farqlar navbati: qaror va ISFT Core'ga yozish
# =============================================================================================
NORM = {("students", "status"): HM.status, ("students", "study_form"): HM.form, ("students", "citizenship"): HM.citizenship,
        ("students", "payment_type"): HM.payment, ("students", "full_name"): lambda v: HM.display_name(v) or None,
        ("groups", "level"): HM.level, ("groups", "study_form"): HM.form, ("groups", "course"): HM.course,
        ("groups", "direction"): lambda v: HM.display_name(v) or None, ("teachers", "full_name"): lambda v: HM.display_name(v) or None,
        ("teachers", "position"): lambda v: HM.clean_spaces(v) or None, ("teachers", "degree"): lambda v: HM.clean_spaces(v) or None,
        ("grades", "score"): HM.score}


def _set_core(con, d: dict, value: str) -> tuple[dict, dict, str]:
    """Farq qiymatini ISFT Core'ga yozadi. Qaytaradi: (oldin, keyin, jadval)."""
    e, f = d["entity"], d["field"]
    if (e, f) in (("students", "group"),):
        g = HP.groups_idx(con)[0].get(HM.group_key(value))
        if not g: raise HTTPException(409, f"Guruh «{value}» ISFT Core'da yo'q — avval Guruhlar faylini import qiling")
        before = db.one(con, "SELECT group_id, faculty_id FROM students WHERE id=?", (d["core_id"],))
        after = {"group_id": g["id"], "faculty_id": g["faculty_id"]}
        con.execute("UPDATE students SET group_id=?, faculty_id=? WHERE id=?", (g["id"], g["faculty_id"], d["core_id"]))
        return before, after, "students"
    if (e, f) == ("teachers", "department"):
        dep = {HM.subject_key(x["name"]): x for x in db.rows(con, "SELECT id, name, faculty_id FROM departments")}.get(HM.subject_key(value))
        if not dep: raise HTTPException(409, f"Kafedra «{value}» ISFT Core'da yo'q")
        before = db.one(con, "SELECT department_id, faculty_id FROM teachers WHERE id=?", (d["core_id"],))
        con.execute("UPDATE teachers SET department_id=?, faculty_id=? WHERE id=?", (dep["id"], dep["faculty_id"], d["core_id"]))
        return before, {"department_id": dep["id"], "faculty_id": dep["faculty_id"]}, "teachers"
    fn = NORM.get((e, f))
    if not fn: raise HTTPException(400, "Bu maydonni avtomatik yozib bo'lmaydi")
    v = fn(value)
    if v is None: raise HTTPException(400, f"{FIELD_T.get(f, f)}: «{value}» qiymati tanilmadi")
    if e == "grades":
        rid = json.loads(d["core_key"] or "{}").get("rowid")
        before = db.one(con, "SELECT score FROM grades WHERE rowid=?", (rid,))
        if before is None: raise HTTPException(409, "Baho yozuvi ISFT Core'da topilmadi")
        con.execute("UPDATE grades SET score=? WHERE rowid=?", (v, rid))
        return before, {"score": v}, "grades"
    tbl, col = {"students": "students", "groups": "groups_", "teachers": "teachers"}[e], ("form" if (e, f) == ("groups", "study_form") else f)
    before = db.one(con, f"SELECT {col} FROM {tbl} WHERE id=?", (d["core_id"],))
    if before is None: raise HTTPException(409, "Yozuv ISFT Core'da topilmadi")
    con.execute(f"UPDATE {tbl} SET {col}=? WHERE id=?", (v, d["core_id"]))
    return before, {col: v}, tbl


def resolve_diff(c: Ctx, did: int, decision: str, value: str, note: str, _commit: bool = True) -> dict:
    if decision not in ("hemis", "core", "qolda"): raise HTTPException(400, "Qaror: hemis, core yoki qolda")
    note, value = (note or "").strip()[:500], (value or "").strip()[:200]
    if decision == "qolda" and not value: raise HTTPException(400, "To'g'ri qiymatni kiriting")
    if decision in ("core", "qolda") and len(note) < 3: raise HTTPException(400, "Izoh yozing (nega HEMIS qiymati noto'g'ri)")
    con, now = _con, _now()
    with _lock:
        d = db.one(con, "SELECT * FROM hemis_diffs WHERE id=?", (did,))
        if not d: raise HTTPException(404, "Farq topilmadi")
        if d["status"] != "ochiq": raise HTTPException(409, "Farq allaqachon hal qilingan")
        try:
            if con.in_transaction and _commit: con.commit()
            if _commit: con.execute("BEGIN IMMEDIATE")
            final = d["core_value"] if decision == "core" else (value or d["hemis_value"])
            if decision in ("hemis", "qolda"):
                before, after, tbl = _set_core(con, d, final)
                _snap(con, 0, tbl, d["core_id"], f"farq:{did}", before, after)
            con.execute("""UPDATE hemis_diffs SET status='hal', decision=?, final_value=?, resolved_at=?, resolved_by=?, resolved_name=?, note=?,
                           export_pending=? WHERE id=?""",
                        (decision, final, now, c.user["id"], c.user["full_name"], note, int(decision in ("core", "qolda")), did))
            con.execute("INSERT INTO hemis_diff_log(diff_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                        (did, now, c.user["id"], c.user["full_name"], DECISIONS[decision], f"{FIELD_T.get(d['field'], d['field'])}: {final} · {note}"[:300]))
            _audit_tx(con, c, "farq hal qilindi", f"#{did} {d['entity']} {d['ref']} {d['field']}: {DECISIONS[decision]}")
            if _commit: con.commit()
        except Exception:
            if _commit: con.rollback()
            raise
    if _commit: _inv()
    return diff_view(db.one(con, "SELECT * FROM hemis_diffs WHERE id=?", (did,)))


def resolve_bulk(c: Ctx, ids: list[int], decision: str, note: str) -> dict:
    if decision not in ("hemis", "core"): raise HTTPException(400, "Ommaviy qaror: hemis yoki core")
    if len(ids) > 500: raise HTTPException(400, "Bir martada ko'pi bilan 500 ta")
    ok, errs = 0, []
    for i in ids:
        try:
            resolve_diff(c, int(i), decision, "", note); ok += 1
        except HTTPException as e:
            errs.append(f"#{i}: {e.detail}")
    return {"ok": ok, "errors": errs[:20]}


def diff_view(r: dict) -> dict:
    now = clock.now()
    try: age = (now.replace(tzinfo=None) - dt.datetime.fromisoformat(r["created_at"]).replace(tzinfo=None)).days
    except Exception: age = 0
    return {**{k: r[k] for k in ("id", "entity", "ref", "label", "field", "core_value", "hemis_value", "status", "decision", "final_value",
                                  "created_at", "resolved_at", "resolved_name", "note", "export_pending", "owner_user", "first_import", "last_import")},
            "entity_t": HM.ENTITIES.get(r["entity"], r["entity"]), "field_t": FIELD_T.get(r["field"], r["field"]),
            "decision_t": DECISIONS.get(r["decision"] or "", ""), "age_days": age,
            "spelling_only": r["field"] == "full_name" and HM.name_key(r["core_value"]) == HM.name_key(r["hemis_value"])}


def review_missing(c: Ctx, mid: int, note: str) -> dict:
    note = (note or "").strip()[:500]
    if len(note) < 3: raise HTTPException(400, "Izoh yozing (masalan: «chetlashtirilgan, buyruq № …»)")
    r = db.one(_con, "SELECT * FROM hemis_missing WHERE id=?", (mid,))
    if not r: raise HTTPException(404)
    if r["status"] != "ochiq": raise HTTPException(409, "Allaqachon ko'rib chiqilgan")
    _con.execute("UPDATE hemis_missing SET status='tekshirildi', reviewed_by=?, reviewed_name=?, reviewed_at=?, note=? WHERE id=?",
                 (c.user["id"], c.user["full_name"], _now(), note, mid))
    _con.commit(); _inv()
    return db.one(_con, "SELECT * FROM hemis_missing WHERE id=?", (mid,))


# =============================================================================================
# Ma'lumot sifati
# =============================================================================================
def quality(con, names: bool = True) -> list[dict]:
    S = settings(con)
    act = f"s.status IN {HP.ACTIVE}"
    out = []

    def add(key, title, level, hint, n, sample=()):
        out.append({"key": key, "title": title, "level": level, "hint": hint, "n": n, "sample": list(sample)[:20] if names else []})

    dups = db.rows(con, """SELECT hemis_id, COUNT(*) n, GROUP_CONCAT(full_name, ' | ') names FROM students
                           WHERE hemis_id IS NOT NULL AND hemis_id!='' GROUP BY hemis_id HAVING n>1 ORDER BY n DESC""")
    add("dup_hemis", "Takroriy HEMIS ID (bir nechta talabada)", "bad", "Bitta HEMIS ID — bitta talaba. Ortiqcha yozuvni Registrator ofisi aniqlaydi.",
        len(dups), [f"{d['hemis_id']}: {d['names'][:120]}" for d in dups])
    no = db.rows(con, f"""SELECT s.full_name, g.name grp FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
                          WHERE {act} AND (s.hemis_id IS NULL OR s.hemis_id='')""")
    add("no_hemis", "HEMIS IDsiz faol talabalar", "bad", "HEMIS ID bo'lmasa ma'lumot HEMIS bilan solishtirilmaydi.", len(no),
        [f"{r['full_name']} · {r['grp'] or '—'}" for r in no])
    try: rx = re.compile(S.get("hemis_id_regex") or DEFAULTS["hemis_id_regex"])
    except re.error: rx = re.compile(DEFAULTS["hemis_id_regex"])
    bad = [r for r in db.rows(con, f"SELECT s.hemis_id, s.full_name FROM students s WHERE {act} AND s.hemis_id IS NOT NULL AND s.hemis_id!=''")
           if not rx.match(r["hemis_id"])]
    add("bad_hemis", "HEMIS ID formati shubhali", "warn", f"Kutilgan format: {rx.pattern} (TASDIQLANMAGAN — sozlamada o'zgartiriladi).",
        len(bad), [f"{r['hemis_id']} · {r['full_name']}" for r in bad])
    dist = db.rows(con, f"""SELECT s.full_name, g.name grp, g.form FROM students s JOIN groups_ g ON g.id=s.group_id
                            WHERE {act} AND s.study_form='masofaviy' AND COALESCE(g.form,'')!='masofaviy'""")
    add("dist_form", "Masofaviy talaba masofaviy bo'lmagan guruhda", "bad",
        "Talabaning ta'lim shakli va guruh shakli mos emas — guruh yoki shaklni tuzating (HEMIS bilan solishtiring).", len(dist),
        [f"{r['full_name']} · {r['grp']} ({r['form'] or '—'})" for r in dist])
    oth = db.rows(con, f"""SELECT s.full_name, g.name grp, s.study_form FROM students s JOIN groups_ g ON g.id=s.group_id
                           WHERE {act} AND COALESCE(s.study_form,'')!='masofaviy' AND g.form='masofaviy'""")
    add("form_other", "Masofaviy guruhda boshqa shakldagi talaba", "warn", "Guruh masofaviy, talaba shakli boshqa.", len(oth),
        [f"{r['full_name']} · {r['grp']} ({r['study_form'] or '—'})" for r in oth])
    ng = db.rows(con, f"SELECT s.full_name, s.hemis_id FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE {act} AND g.id IS NULL")
    add("no_group", "Guruhi yo'q (yoki o'chirilgan guruhdagi) talabalar", "bad", "", len(ng), [f"{r['full_name']} · {r['hemis_id']}" for r in ng])
    td = db.rows(con, """SELECT hemis_id, COUNT(*) n FROM teachers WHERE hemis_id IS NOT NULL AND hemis_id!='' GROUP BY hemis_id HAVING n>1""")
    add("teacher_dup", "Takroriy xodim HEMIS ID", "warn", "", len(td), [f"{r['hemis_id']} ({r['n']})" for r in td])
    ms = db.rows(con, "SELECT entity, label FROM hemis_missing WHERE status='ochiq' ORDER BY id")
    add("missing", "«HEMIS'da topilmadi» — ko'rib chiqilmagan", "warn", "HEMIS faylida yo'q, ISFT Core'da bor. O'chirilmaydi — registrator tekshiradi.",
        len(ms), [f"{HM.ENTITIES.get(r['entity'], r['entity'])}: {r['label']}" for r in ms])
    return out


# =============================================================================================
# Eksport (.xlsx, shablon, SHA-256, jurnal)
# =============================================================================================
TEMPLATES = {
    "baholar": ("Oraliq ballar (LRS testlari)", [("hemis_id", "Talaba HEMIS ID"), ("full_name", "F.I.Sh."), ("group", "Guruh"), ("subject", "Fan"),
                                                ("semester", "Semestr"), ("control", "Nazorat turi"), ("score", "Ball"), ("max", "Maksimal ball"),
                                                ("lessons", "Baholangan darslar"), ("date", "Oxirgi faollik")]),
    "davomat": ("Masofaviy talabalar davomati (LRS faolligi)", [("hemis_id", "Talaba HEMIS ID"), ("full_name", "F.I.Sh."), ("group", "Guruh"),
                                                               ("week", "Hafta (dushanba)"), ("status", "Holat"), ("minutes", "Daqiqa"),
                                                               ("statements", "LRS yozuvlari"), ("basis", "Asos")]),
    "yuzma": ("Yuzma-yuz qaydnoma natijalari", [("hemis_id", "Talaba HEMIS ID"), ("full_name", "F.I.Sh."), ("group", "Guruh"), ("kind", "Tadbir"),
                                               ("date", "Sana"), ("result", "Natija"), ("protocol", "Qaydnoma raqami")]),
    "tuzatishlar": ("HEMIS'ga tuzatishlar (Farqlar navbatidan)", [("entity", "Tur"), ("ref", "HEMIS ID / kalit"), ("label", "Nomi"),
                                                                 ("field", "Maydon"), ("hemis_value", "HEMIS'dagi qiymat"), ("correct", "To'g'ri qiymat"),
                                                                 ("decision", "Qaror"), ("date", "Qaror sanasi"), ("who", "Kim")]),
}
UNVERIFIED = {"davomat": "QOIDA TASDIQLANMAGAN: vazirlik davomat qoidasi masofaviy ta'lim uchun rasmiy tasdiqlanmagan — sozlanadi.",
              "baholar": "LRS testlari asosidagi oraliq ball; HEMIS'ga yuklash tartibi va baholash siyosati Registrator ofisi tomonidan tasdiqlanadi."}


def template(kind: str, S: dict | None = None) -> list[tuple[str, str]]:
    S = S or settings()
    over = S.get(f"tpl:{kind}") or {}
    return [(k, (over.get(k) or h)) for k, h in TEMPLATES[kind][1]]


def _mondays(n: int) -> list[str]:
    t = clock.today(); m = t - dt.timedelta(days=t.weekday())
    return [(m - dt.timedelta(weeks=i)).isoformat() for i in range(n)][::-1]


def rows_baholar(con, S, params) -> tuple[list[dict], str]:
    rule = S["grade_rule"]
    if not rule.get("enabled"): raise HTTPException(409, "Baholar eksporti siyosat bo'yicha o'chirilgan (sozlamalar)")
    mx, mn = float(rule.get("scale_max") or 30), int(rule.get("min_lessons") or 1)
    w, a = "", []
    if params.get("group"): w, a = " AND g.name=?", [params["group"]]
    try:
        rs = db.rows(con, f"""SELECT st.hemis_id, st.full_name, g.name grp, g.course, c.subject, AVG(COALESCE(p.best, p.score)) sc, COUNT(*) n,
                                     MAX(p.last_ts) last FROM lrs_progress p JOIN students st ON st.id=p.student_id JOIN groups_ g ON g.id=st.group_id
                              JOIN dl_courses c ON 'dl:' || c.id = p.course_ref
                              WHERE COALESCE(p.best, p.score) IS NOT NULL{w} GROUP BY p.student_id, p.course_ref HAVING n>=? ORDER BY g.name, st.full_name, c.subject""",
                     a + [mn])
    except Exception as e:
        print("hemis.rows_baholar:", repr(e)); rs = []
    out = [{"hemis_id": r["hemis_id"], "full_name": r["full_name"], "group": r["grp"], "subject": r["subject"],
            "semester": 2 * int(r["course"] or 1) - 1, "control": rule.get("label") or "Oraliq nazorat", "score": round(r["sc"] / 100 * mx, 1),
            "max": mx, "lessons": r["n"], "date": (r["last"] or "")[:10]} for r in rs]
    return out, f"o'rtacha LRS ball × {mx:g} / 100; kamida {mn} ta baholangan dars"


def rows_davomat(con, S, params) -> tuple[list[dict], str]:
    rule = S["att_rule"]
    n = max(1, min(int(params.get("weeks") or rule.get("weeks") or 4), 26))
    mm, ms = int(rule.get("min_minutes") or 30), int(rule.get("min_statements") or 3)
    weeks = _mondays(n)
    w, a = "", []
    if params.get("group"): w, a = " AND g.name=?", [params["group"]]
    st = db.rows(con, f"""SELECT s.id, s.hemis_id, s.full_name, g.name grp FROM students s JOIN groups_ g ON g.id=s.group_id
                          WHERE s.study_form='masofaviy' AND s.status='faol'{w} ORDER BY g.name, s.full_name""", a)
    mins, stmts = {}, {}
    try:
        for r in db.rows(con, "SELECT student_id, week, minutes FROM dl_activity WHERE week>=?", (weeks[0],)):
            mins[(r["student_id"], r["week"])] = r["minutes"] or 0
    except Exception: pass
    try:
        for r in db.rows(con, """SELECT student_id, date(ts, 'weekday 0', '-6 days') wk, COUNT(*) n FROM lrs_statements
                                 WHERE ts>=? AND COALESCE(voided,0)=0 GROUP BY 1, 2""", (weeks[0],)):
            stmts[(r["student_id"], r["wk"])] = r["n"]
    except Exception: pass
    basis = f"≥ {mm} daqiqa LMS faolligi YOKI ≥ {ms} ta LRS yozuvi haftada (TASDIQLANMAGAN qoida)"
    out = []
    for s in st:
        for wk in weeks:
            m, k = mins.get((s["id"], wk), 0), stmts.get((s["id"], wk), 0)
            out.append({"hemis_id": s["hemis_id"], "full_name": s["full_name"], "group": s["grp"], "week": wk,
                        "status": "Qatnashdi" if (m >= mm or k >= ms) else "Qatnashmadi", "minutes": m, "statements": k, "basis": basis})
    return out, basis


def rows_yuzma(con, S, params) -> tuple[list[dict], str]:
    try:
        from . import yuzma_yuz as YY
        rs = db.rows(con, """SELECT st.hemis_id, st.full_name, g.name grp, s.kind, s.date, a.status, p.reg_no FROM yy_assign a
                             JOIN yy_sessions s ON s.id=a.session_id JOIN students st ON st.id=a.student_id LEFT JOIN groups_ g ON g.id=st.group_id
                             LEFT JOIN yy_protocols p ON p.session_id=s.id WHERE s.status='yopilgan' ORDER BY s.date, g.name, st.full_name""")
    except Exception as e:
        print("hemis.rows_yuzma:", repr(e)); return [], ""
    return [{"hemis_id": r["hemis_id"], "full_name": r["full_name"], "group": r["grp"], "kind": YY.KINDS.get(r["kind"], r["kind"]),
             "date": r["date"], "result": YY.A_ST.get(r["status"], r["status"]), "protocol": r["reg_no"] or ""} for r in rs], "imzolangan qaydnomalar"


def rows_tuzatishlar(con, S, params) -> tuple[list[dict], str]:
    w = "decision IN ('core','qolda')" if params.get("include_exported") else "export_pending=1"
    rs = db.rows(con, f"SELECT * FROM hemis_diffs WHERE {w} ORDER BY entity, ref, field")
    return [{"id": r["id"], "entity": HM.ENTITIES.get(r["entity"], r["entity"]), "ref": r["ref"], "label": r["label"],
             "field": FIELD_T.get(r["field"], r["field"]), "hemis_value": r["hemis_value"], "correct": r["final_value"],
             "decision": DECISIONS.get(r["decision"], r["decision"]), "date": (r["resolved_at"] or "")[:10], "who": r["resolved_name"]} for r in rs], \
        "ISFT Core to'g'ri / qo'lda tuzatilgan farqlar"


BUILDERS = {"baholar": rows_baholar, "davomat": rows_davomat, "yuzma": rows_yuzma, "tuzatishlar": rows_tuzatishlar}


def _xdir():
    d = db.DATA_DIR / "hemis_exports"; d.mkdir(parents=True, exist_ok=True); return d


def build_xlsx(kind: str, cols: list[tuple[str, str]], rows: list[dict], meta: list[tuple[str, str]], when: dt.datetime) -> tuple[bytes, str]:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    def cell(v):   # o'qib qayta hisoblaganda ham bir xil xesh chiqsin: None → "", 30.0 → 30
        if v is None: return ""
        return int(v) if isinstance(v, float) and v.is_integer() else v
    data = [[h for _, h in cols]] + [[cell(r.get(k)) for k, _ in cols] for r in rows]
    content_sha = hashlib.sha256(_j(data).encode()).hexdigest()
    wb = Workbook(); ws = wb.active; ws.title = "HEMIS"
    for row in data: ws.append(row)
    for cell in ws[1]: cell.font = Font(bold=True); cell.fill = PatternFill("solid", fgColor="DDE6F0")
    for i, (k, h) in enumerate(cols):
        ws.column_dimensions[chr(65 + i) if i < 26 else "A" + chr(65 + i - 26)].width = max(12, min(40, len(h) + 4))
    ws.freeze_panes = "A2"
    m = wb.create_sheet("Ma'lumot")
    for k, v in meta + [("Mazmun SHA-256 (sarlavha + qatorlar, JSON)", content_sha)]: m.append([k, v])
    m.column_dimensions["A"].width = 44; m.column_dimensions["B"].width = 90
    wb.properties.creator = "ISFT Core"; wb.properties.created = when.replace(tzinfo=None); wb.properties.modified = when.replace(tzinfo=None)
    bio = io.BytesIO(); wb.save(bio)
    return bio.getvalue(), content_sha


def make_export(c: Ctx, kind: str, params: dict) -> dict:
    if kind not in TEMPLATES: raise HTTPException(404, "Noma'lum eksport turi")
    S = settings()
    with _lock:
        rows, rule = BUILDERS[kind](_con, S, params or {})
        if not rows: raise HTTPException(409, "Eksport uchun ma'lumot yo'q")
        cols, when = template(kind, S), clock.now().replace(microsecond=0)
        meta = [("Eksport", TEMPLATES[kind][0]), ("Tayyorlandi", when.isoformat(timespec="seconds")), ("Kim", c.user["full_name"]),
                ("Qatorlar", str(len(rows))), ("Qoida", rule), ("Manba", "ISFT Core"),
                ("Diqqat", UNVERIFIED.get(kind, "HEMIS yuklash shabloni rasmiy tasdiqlanmagan — ustun nomlari sozlamada o'zgartiriladi."))]
        data, csha = build_xlsx(kind, cols, rows, meta, when)
        sha = hashlib.sha256(data).hexdigest()
        cur = _con.execute("""INSERT INTO hemis_exports(kind,ts,user_id,user_name,rows,sha256,content_sha256,file,params,rule)
                              VALUES(?,?,?,?,?,?,?,?,?,?)""", (kind, _now(), c.user["id"], c.user["full_name"], len(rows), sha, csha, "", _j(params or {}), rule))
        eid = cur.lastrowid
        fn = f"{eid}_{kind}.xlsx"
        (_xdir() / fn).write_bytes(data)
        _con.execute("UPDATE hemis_exports SET file=? WHERE id=?", (fn, eid))
        if kind == "tuzatishlar":
            ids = [r["id"] for r in rows]
            for i in range(0, len(ids), 900):
                ch = ids[i:i + 900]
                _con.execute(f"UPDATE hemis_diffs SET export_pending=0, exported_id=? WHERE id IN ({','.join('?' * len(ch))})", [eid] + ch)
        _audit_tx(_con, c, "eksport tayyorlandi", f"#{eid} {kind}: {len(rows)} qator · sha256 {sha[:16]}")
        _con.commit()
    return export_view(db.one(_con, "SELECT * FROM hemis_exports WHERE id=?", (eid,)))


def export_view(r: dict) -> dict:
    return {**{k: r[k] for k in ("id", "kind", "ts", "user_name", "rows", "sha256", "content_sha256", "rule")},
            "kind_t": TEMPLATES.get(r["kind"], ("",))[0], "params": json.loads(r["params"] or "{}"), "url": f"{P}/exports/{r['id']}/file"}


# =============================================================================================
# Nazorat markazi uchun (app/nazorat.py, «HEMIS almashinuvi» bo'limi)
# =============================================================================================
def overdue_diffs(con, days: int) -> tuple[int, str | None, int]:
    try:
        lim = (clock.now().replace(tzinfo=None) - dt.timedelta(days=days)).isoformat(timespec="seconds")
        r = db.one(con, "SELECT COUNT(*) n, MIN(created_at) t0 FROM hemis_diffs WHERE status='ochiq' AND created_at<=?", (lim,))
        tot = db.one(con, "SELECT COUNT(*) n FROM hemis_diffs WHERE status='ochiq'")["n"]
        return r["n"] or 0, r["t0"], tot
    except Exception:
        return 0, None, 0


def quality_counts(con) -> dict:
    try: return {q["key"]: q["n"] for q in quality(con, names=False)}
    except Exception as e:
        print("hemis.quality:", repr(e)); return {}


def _counts(con) -> dict:
    d = {r["status"]: r["n"] for r in db.rows(con, "SELECT status, COUNT(*) n FROM hemis_diffs GROUP BY status")}
    m = {r["status"]: r["n"] for r in db.rows(con, "SELECT status, COUNT(*) n FROM hemis_missing GROUP BY status")}
    return {"diffs_open": d.get("ochiq", 0), "diffs_done": d.get("hal", 0), "missing_open": m.get("ochiq", 0),
            "export_pending": db.one(con, "SELECT COUNT(*) n FROM hemis_diffs WHERE export_pending=1")["n"]}


# =============================================================================================
# API
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "ochish", ALL)
    S = settings()
    head, mng = c.role.key in HEADS, c.role.key in MANAGE
    out = {"role": c.role.key, "caps": {"manage": mng, "settings": head, "names": mng, "aggregate_only": not mng}, "legal_note": LEGAL_NOTE,
           "api_label": HA.LABEL, "entities": [{"key": k, "title": t} for k, t in HM.ENTITIES.items()], "today": clock.today().isoformat(),
           "decisions": DECISIONS, "fields_t": FIELD_T}
    if mng:
        out["profiles"] = db.rows(_con, "SELECT id, entity, name, created_name, created_at FROM hemis_profiles ORDER BY entity, name")
        out["exports"] = [{"key": k, "title": t[0], "unverified": UNVERIFIED.get(k, ""), "columns": template(k, S)} for k, t in TEMPLATES.items()]
        out["rules"] = {"att_rule": S["att_rule"], "grade_rule": S["grade_rule"], "auto_fields": S["auto_fields"], "hemis_id_regex": S["hemis_id_regex"]}
    return out


@router.get(P + "/summary")
def api_summary(request: Request):
    """Rektor (va boshqaruvchilar): faqat jamlangan sonlar — ism, HEMIS ID yo'q."""
    c = C(request); guard(c, "jamlanma", ALL)
    try:
        from . import nazorat as NZ; days = NZ.rules(_con).get("hemis_diff_days", 7)
    except Exception: days = 7
    od, t0, tot = overdue_diffs(_con, days)
    last = db.rows(_con, "SELECT entity, MAX(applied_at) t FROM hemis_imports WHERE status='applied' GROUP BY entity")
    return {**_counts(_con), "overdue_days": days, "diffs_overdue": od, "oldest": t0,
            "quality": [{k: q[k] for k in ("key", "title", "level", "n")} for q in quality(_con, names=False)],
            "last_import": {r["entity"]: r["t"] for r in last}, "api_enabled": bool(settings()["api_enabled"]), "api_verified": HA.VERIFIED,
            "legal_note": LEGAL_NOTE}


@router.post(P + "/import/{entity}")
async def api_import(entity: str, request: Request, name: str = "fayl.xlsx", profile_id: int = 0, scope: str = "qisman"):
    c = C(request); guard(c, "import (ko'rib chiqish)", MANAGE, f"{entity}: {name[:60]}")
    raw = await request.body()
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(create_preview, c, entity, raw, name, profile_id or None, scope)


@router.get(P + "/imports")
def api_imports(request: Request, entity: str = ""):
    c = C(request); guard(c, "importlar", MANAGE)
    w, a = ("WHERE entity=?", [entity]) if entity else ("", [])
    rs = db.rows(_con, f"""SELECT id, entity, filename, sha256, size, ts, user_name, status, scope, counts, applied_at, applied_name, error
                           FROM hemis_imports {w} ORDER BY id DESC LIMIT 50""", a)
    for r in rs: r["counts"] = json.loads(r["counts"] or "null"); r["entity_t"] = HM.ENTITIES.get(r["entity"], r["entity"])
    return {"items": rs}


@router.get(P + "/imports/{iid}")
def api_import_get(iid: int, request: Request):
    c = C(request); guard(c, "import", MANAGE, f"#{iid}")
    return preview_view(_con, _imp(iid))


class RemapIn(BaseModel):
    mapping: dict = {}
    scope: str | None = None
    save_profile: str | None = Field(None, max_length=60)


@router.post(P + "/imports/{iid}/remap")
def api_remap(iid: int, body: RemapIn, request: Request):
    c = C(request); guard(c, "ustunlarni moslash", MANAGE, f"#{iid}")
    return remap(c, iid, body.mapping, body.scope, body.save_profile)


@router.post(P + "/imports/{iid}/apply")
def api_apply(iid: int, request: Request):
    c = C(request); guard(c, "importni qo'llash", MANAGE, f"#{iid}")
    return apply_import(c, iid)


@router.post(P + "/imports/{iid}/cancel")
def api_cancel(iid: int, request: Request):
    c = C(request); guard(c, "importni bekor qilish", MANAGE, f"#{iid}")
    return cancel_import(c, iid)


@router.delete(P + "/profiles/{pid}")
def api_profile_del(pid: int, request: Request):
    c = C(request); guard(c, "profilni o'chirish", MANAGE, f"#{pid}")
    _con.execute("DELETE FROM hemis_profiles WHERE id=?", (pid,)); _con.commit()
    return {"ok": True}


@router.get(P + "/diffs")
def api_diffs(request: Request, status: str = "ochiq", entity: str = "", field: str = "", q: str = "", overdue: int = 0,
              offset: int = 0, limit: int = 50):
    c = C(request); guard(c, "farqlar navbati", MANAGE)
    w, a = ["1=1"], []
    if status in ("ochiq", "hal"): w.append("status=?"); a.append(status)
    if entity: w.append("entity=?"); a.append(entity)
    if field: w.append("field=?"); a.append(field)
    if q: w.append("(ref LIKE ? OR label LIKE ?)"); a += [f"%{q[:60]}%"] * 2
    if overdue:
        w.append("created_at<=?"); a.append((clock.now().replace(tzinfo=None) - dt.timedelta(days=int(overdue))).isoformat(timespec="seconds"))
    where = " AND ".join(w)
    limit = max(1, min(limit, 200))
    total = db.one(_con, f"SELECT COUNT(*) n FROM hemis_diffs WHERE {where}", a)["n"]
    rs = db.rows(_con, f"SELECT * FROM hemis_diffs WHERE {where} ORDER BY status='hal', created_at, id LIMIT ? OFFSET ?", a + [limit, max(0, offset)])
    by_f = db.rows(_con, "SELECT field, COUNT(*) n FROM hemis_diffs WHERE status='ochiq' GROUP BY field ORDER BY n DESC")
    return {"items": [diff_view(r) for r in rs], "total": total, "offset": offset, "limit": limit, "counts": _counts(_con),
            "by_field": [{"field": r["field"], "title": FIELD_T.get(r["field"], r["field"]), "n": r["n"]} for r in by_f]}


@router.get(P + "/diffs/{did}")
def api_diff(did: int, request: Request):
    c = C(request); guard(c, "farq", MANAGE, f"#{did}")
    r = db.one(_con, "SELECT * FROM hemis_diffs WHERE id=?", (did,))
    if not r: raise HTTPException(404)
    return {**diff_view(r), "log": db.rows(_con, "SELECT ts, user_name, action, detail FROM hemis_diff_log WHERE diff_id=? ORDER BY id", (did,))}


class ResolveIn(BaseModel):
    decision: str
    value: str = Field("", max_length=200)
    note: str = Field("", max_length=500)


@router.post(P + "/diffs/{did}/resolve")
def api_resolve(did: int, body: ResolveIn, request: Request):
    c = C(request); guard(c, "farq bo'yicha qaror", MANAGE, f"#{did} {body.decision}")
    return resolve_diff(c, did, body.decision, body.value, body.note)


class BulkIn(BaseModel):
    ids: list[int]
    decision: str
    note: str = Field("", max_length=500)


@router.post(P + "/diffs/bulk")
def api_bulk(body: BulkIn, request: Request):
    c = C(request); guard(c, "farqlar: ommaviy qaror", MANAGE, f"{len(body.ids)} ta {body.decision}")
    r = resolve_bulk(c, body.ids, body.decision, body.note); _inv(); return r


@router.get(P + "/missing")
def api_missing(request: Request, status: str = "ochiq", entity: str = "", offset: int = 0, limit: int = 50):
    c = C(request); guard(c, "HEMIS'da topilmadi", MANAGE)
    w, a = ["status=?"], [status if status in ("ochiq", "tekshirildi", "qaytdi") else "ochiq"]
    if entity: w.append("entity=?"); a.append(entity)
    where = " AND ".join(w); limit = max(1, min(limit, 200))
    total = db.one(_con, f"SELECT COUNT(*) n FROM hemis_missing WHERE {where}", a)["n"]
    rs = db.rows(_con, f"SELECT * FROM hemis_missing WHERE {where} ORDER BY id LIMIT ? OFFSET ?", a + [limit, max(0, offset)])
    for r in rs: r["entity_t"] = HM.ENTITIES.get(r["entity"], r["entity"])
    return {"items": rs, "total": total, "offset": offset, "limit": limit}


class NoteIn(BaseModel):
    note: str = Field("", max_length=500)


@router.post(P + "/missing/{mid}/review")
def api_missing_review(mid: int, body: NoteIn, request: Request):
    c = C(request); guard(c, "topilmadi: ko'rib chiqildi", MANAGE, f"#{mid}")
    return review_missing(c, mid, body.note)


@router.get(P + "/quality")
def api_quality(request: Request):
    c = C(request); guard(c, "ma'lumot sifati", ALL)
    return {"items": quality(_con, names=c.role.key in MANAGE)}


@router.get(P + "/exports")
def api_exports(request: Request):
    c = C(request); guard(c, "eksportlar jurnali", MANAGE)
    return {"items": [export_view(r) for r in db.rows(_con, "SELECT * FROM hemis_exports ORDER BY id DESC LIMIT 50")]}


class ExportIn(BaseModel):
    group: str = Field("", max_length=40)
    weeks: int = 0
    include_exported: bool = False


@router.post(P + "/export/{kind}")
def api_export(kind: str, body: ExportIn, request: Request):
    c = C(request); guard(c, "eksport", MANAGE, kind)
    return make_export(c, kind, {k: v for k, v in body.model_dump().items() if v})


@router.get(P + "/exports/{eid}/file")
def api_export_file(eid: int, request: Request):
    c = C(request); guard(c, "eksport faylini yuklab olish", MANAGE, f"#{eid}")
    r = db.one(_con, "SELECT * FROM hemis_exports WHERE id=?", (eid,))
    if not r or not r["file"]: raise HTTPException(404)
    p = _xdir() / r["file"]
    if not p.exists(): raise HTTPException(410, "Fayl topilmadi")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != r["sha256"]: raise HTTPException(409, "Fayl nazorat summasi jurnaldagiga mos emas — fayl o'zgartirilgan")
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="hemis_{r["kind"]}_{eid}.xlsx"', "X-Content-SHA256": r["sha256"]})


class TemplateIn(BaseModel):
    kind: str
    headers: dict


@router.post(P + "/templates")
def api_template(body: TemplateIn, request: Request):
    c = C(request); guard(c, "eksport shabloni", HEADS, body.kind)
    if body.kind not in TEMPLATES: raise HTTPException(404)
    keys = {k for k, _ in TEMPLATES[body.kind][1]}
    clean = {k: HM.clean_spaces(v)[:60] for k, v in body.headers.items() if k in keys and HM.clean_spaces(v)}
    set_setting(_con, f"tpl:{body.kind}", clean, c.user["full_name"]); _con.commit()
    return {"columns": template(body.kind)}


@router.get(P + "/settings")
def api_settings(request: Request):
    c = C(request); guard(c, "sozlamalar", MANAGE)
    S = settings()
    return {**{k: S[k] for k in DEFAULTS}, "token_set": HA.token_set(), "secret_mode": _secret_mode(), "verified": HA.VERIFIED,
            "label": HA.LABEL, "can_edit": c.role.key in HEADS}


def _secret_mode():
    try:
        from . import secret_store as SS; return SS.mode()
    except Exception: return "?"


class SettingsIn(BaseModel):
    values: dict


@router.post(P + "/settings")
def api_settings_set(body: SettingsIn, request: Request):
    c = C(request); guard(c, "sozlamalarni o'zgartirish", HEADS, _j(body.values)[:200])
    v = body.values
    out = {}
    for k, val in v.items():
        if k not in DEFAULTS: raise HTTPException(400, f"Noma'lum sozlama: {k}")
        if k in ("api_enabled", "api_probe_auth"): val = bool(val)
        elif k == "api_base_url":
            try: val = HA.validate_url(str(val))
            except ValueError as e: raise HTTPException(400, str(e))
        elif k == "api_probe_path":
            try: val = HA.validate_path(str(val))
            except ValueError as e: raise HTTPException(400, str(e))
        elif k == "api_auth_scheme":
            val = str(val).strip()
            if val not in ("Bearer", "Token", "Basic"): raise HTTPException(400, "Sxema: Bearer, Token yoki Basic")
        elif k == "auto_fields":
            if not isinstance(val, list) or any(f not in FIELD_T for f in val): raise HTTPException(400, "auto_fields: maydonlar ro'yxati")
        elif k == "hemis_id_regex":
            try: re.compile(str(val))
            except re.error: raise HTTPException(400, "Noto'g'ri ifoda")
            val = str(val)[:80]
        elif k in ("att_rule", "grade_rule"):
            if not isinstance(val, dict): raise HTTPException(400, f"{k}: obyekt kerak")
            base = DEFAULTS[k]
            val = {kk: val.get(kk, settings()[k].get(kk)) for kk in base}
            for kk, dv in base.items():
                if isinstance(dv, bool): val[kk] = bool(val[kk])
                elif isinstance(dv, int):
                    try: val[kk] = int(val[kk])
                    except (TypeError, ValueError): raise HTTPException(400, f"{k}.{kk}: son kerak")
                    if not 0 <= val[kk] <= 10000: raise HTTPException(400, f"{k}.{kk}: 0–10000")
                else: val[kk] = str(val[kk])[:80]
        if isinstance(val, str) and re.search(r"(?i)(token|bearer|secret|parol)\s*[:=]", val):
            raise HTTPException(400, "Token bazaga yozilmaydi — «Token» maydonidan foydalaning (maxfiy ombor)")
        set_setting(_con, k, val, c.user["full_name"]); out[k] = val
    _con.commit()
    return {"ok": True, "changed": out}


class TokenIn(BaseModel):
    token: str | None = Field(None, max_length=2000)


@router.post(P + "/api/token")
def api_token(body: TokenIn, request: Request):
    c = C(request); guard(c, "API token (maxfiy ombor)", HEADS, "o'rnatildi" if body.token else "o'chirildi")
    HA.set_token(body.token)
    return {"ok": True, "token_set": HA.token_set(), "secret_mode": _secret_mode()}


@router.post(P + "/api/probe")
def api_probe(request: Request):
    c = C(request); guard(c, "ulanishni tekshirish", HEADS)
    r = HA.probe(settings())
    rbac.audit(_con, c, "hemis: ulanish tekshirildi", RES, True, f"{r['result']} {r.get('status', '')} {r.get('target', '')}"[:300])
    return r
