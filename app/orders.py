"""«Buyruqlar» — talabalar harakati bo'yicha buyruqlar (Registrator ofisi talablari asosida).

1. Arizadan buyruq: Registrator talaba arizasini yuklaydi (PDF / rasm / DOCX / TXT) yoki matnini yozadi → tizim matnni o'qiydi
   (orders_intake: matn qatlami, DOCX, OCR — tesseract bo'lsa, bo'lmasa qo'lda), ariza turini va maydonlarini aniqlaydi,
   talabani topadi → buyruq loyihasi shablondan to'ldiriladi (bitta buyruqda ko'p talaba bo'lishi mumkin) → Registrator
   tekshirib imzoga yuboradi → (O'quv ishlari prorektori kelishadi) → Rektor imzolaydi: buyruq ro'yxatga olinadi (raqam, sana)
   va ta'siri talabalar bazasiga AVTOMATIK o'tadi (F.I.Sh. o'zgarishi, holat, guruh, akademik ta'til yozuvi) — har bir o'zgarish
   student_changes jurnalida. Bekor qilish yo'li: tuzatuvchi («bekor qilish») buyruq imzolansa, o'zgarishlar avvalgi holatiga qaytadi.
2. Buyruqlar reyestri va muvofiqlik auditi («Muammoli talabalar»): qabul, kursga o'tkazish, ta'til va boshqa buyruqlar bilan
   talabalar bazasini solishtirish — qabul buyrug'ida yo'q, kursga o'tkazish buyrug'ida yo'q, ziddiyatli buyruqlar, guruh mos emas,
   buyruq bilan chetlashtirilgan-u bazada faol, buyruqsiz akademik ta'tilda. Har bir holatga tuzatish amali (asos hujjat bilan).
3. Katta ro'yxatlar (Excel/CSV) versiyalari: qayta yuklash — YANGI versiya (eskilari saqlanadi), kim/qachon, +/− farq, eski
   versiyani tiklash (yangi versiya sifatida), buyruq DOCX oxirgi versiyadan; imzodan keyin ro'yxat muzlatiladi.
4. Ruxsatlar: talabalar (Registrator) — to'liq; sirtqi — faqat sirtqi talabalar; malumotlar_bazasi — o'qish + muvofiqlik auditi
   (tuzatishlar bilan); prorektor_oquv — o'qish + kelishish; rektor — imzolash / qaytarish; kadrlar — xodimlar buyruqlari
   (mehnat ta'tili; talabalar buyruqlarini ko'rmaydi); devonxona — reyestrni o'qish, imzolangan buyruqni devonxona jurnaliga
   ro'yxatga olish va chiquvchi yozishmalar jurnali (rbac.CHANCERY); boshqalar — 403. Har bir amal rbac.audit(resource="orders").
5. Buyruqlar — talabalar va xodimlar buyruqlarining YAGONA joyi (imzolash, kelishish, qaytarish). Hujjatlar markazidagi eski buyruq
   loyihalari (order_student, reprimand, leave_order — status «loyiha») server startida shu yerga ko'chiriladi (migrate_legacy_docs);
   xodimlar ta'tili (staff_absence.link_order) mehnat ta'tili buyrug'ini shu yerda yaratadi (draft_staff_leave).
"""
import datetime as dt, io, json, re, secrets, threading
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from . import clock
from . import db, rbac, orders_intake as IN
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
RES = "orders"
ROOT = Path(__file__).resolve().parent.parent
DATA = db.DATA_DIR / "orders"
UPL = DATA / "uploads"
OUTD = DATA / "out"
SAMPLES = DATA / "samples"
MAX_UPLOAD = 15 * 1024 * 1024
LIST_INLINE = 400            # bundan katta ro'yxat — DOCX'da guruhlar jamlanmasi + 1-ilova (XLSX)

# ---------------------------------------------------------------------------------------------
# Buyruq turlari
# ---------------------------------------------------------------------------------------------
KINDS = {
    "qabul": dict(title="Talabalar safiga qabul qilish to'g'risida", short="Qabul", fields=[], req=[], effect=False),
    "kurs": dict(title="Talabalarni keyingi kursga o'tkazish to'g'risida", short="Kursga o'tkazish", fields=[], req=[], effect=False),
    "familiya": dict(title="Talaba familiyasini o'zgartirish to'g'risida", short="Familiya o'zgarishi",
                     fields=["old_surname", "new_surname", "basis"], req=["new_surname", "basis"], effect=True),
    "akademik_tatil": dict(title="Akademik ta'til berish to'g'risida", short="Akademik ta'til",
                           fields=["date_from", "date_to", "reason"], req=["date_from", "date_to"], effect=True),
    "tatildan_qaytish": dict(title="Akademik ta'tildan qaytgan talabalarni o'qishga qo'yish to'g'risida", short="Ta'tildan qaytish",
                             fields=["date_from", "group_to"], req=["date_from"], effect=True),
    "chetlashtirish_xohish": dict(title="O'z xohishiga ko'ra talabalar safidan chetlashtirish to'g'risida", short="Chetlashtirish (o'z xohishi)",
                                  fields=["date_from", "reason"], req=["date_from"], effect=True),
    "chetlashtirish_tolov": dict(title="To'lov-kontrakt majburiyati bajarilmagani sababli talabalar safidan chetlashtirish to'g'risida",
                                 short="Chetlashtirish (kontrakt)", fields=["date_from"], req=["date_from"], effect=True),
    "kochirish": dict(title="Boshqa oliy ta'lim muassasasiga o'qishini ko'chirish munosabati bilan talabalar safidan chiqarish to'g'risida",
                      short="Boshqa OTMga ko'chirish", fields=["date_from", "target"], req=["date_from"], effect=True),
    "guruh": dict(title="Talabalarni boshqa guruhga o'tkazish to'g'risida", short="Guruh o'zgarishi", fields=["group_to", "reason"], req=["group_to"], effect=True),
    "tiklash": dict(title="Talabalar safiga qayta tiklash to'g'risida", short="Qayta tiklash", fields=["date_from", "group_to"], req=["date_from", "group_to"], effect=True),
    "bekor": dict(title="Buyruqni bekor qilish to'g'risida", short="Bekor qilish (tuzatuvchi)", fields=[], req=[], effect=True),
    "hayfsan": dict(title="Talabaga hayfsan e'lon qilish to'g'risida", short="Hayfsan", fields=["reason"], req=[], effect=False),
    # «Talaba harakati» (app/academic_flows.py) loyihalaydigan turlar — loyihani baribir Registrator ofisi (sirtqi — Sirtqi bo'lim) imzoga yuboradi
    "akademik_qarz": dict(title="Akademik qarzdorlik sababli talabalar safidan chetlashtirish to'g'risida", short="Chetlashtirish (akademik qarzdorlik)",
                          fields=["date_from", "reason"], req=["date_from"], effect=True),
    "ichki_kochirish": dict(title="Talabalarni boshqa ta'lim yo'nalishiga (ta'lim shakliga) ko'chirish to'g'risida", short="Ichki ko'chirish",
                            fields=["date_from", "group_to", "reason"], req=["date_from", "group_to"], effect=True),
    "kochirib_qabul": dict(title="Boshqa oliy ta'lim muassasasidan o'qishini ko'chirish tartibida talabalar safiga qabul qilish to'g'risida",
                           short="Ko'chirish tartibida qabul", fields=["date_from", "group_to", "source_otm"], req=["date_from", "group_to"], effect=True),
    "kursda_qoldirish": dict(title="Talabani kursda qoldirish (o'quv yilini takroran o'qitish) to'g'risida", short="Kursda qoldirish",
                             fields=["date_from", "group_to", "reason"], req=["date_from", "group_to"], effect=True),
    "qayta_oqish": dict(title="Akademik qarzdor talabalarga fanlarni to'lov-kontrakt asosida qayta o'qishga ruxsat berish to'g'risida",
                        short="Qayta o'qish (to'lovli)", fields=["reason"], req=[], effect=False),
    "isft_granti": dict(title="ISFT granti asosida o'qishga o'tkazish to'g'risida", short="ISFT granti berish",
                        fields=["date_from", "reason"], req=["date_from"], effect=True),
    "isft_granti_mahrum": dict(title="ISFT grantidan mahrum qilish va to'lov-kontrakt asosiga o'tkazish to'g'risida", short="ISFT grantidan mahrum qilish",
                               fields=["date_from", "reason", "contract_amount"], req=["date_from"], effect=True),
    "bitirish": dict(title="Bitiruvchilarni talabalar safidan chiqarish va diplom berish to'g'risida", short="Bitirish (diplom berish)",
                     fields=["date_from"], req=["date_from"], effect=True),
    # xodimlar buyruqlari (Kadrlar bo'limi loyihalaydi, Rektor imzolaydi; talabalar ro'yxati yo'q — xodim params ichida)
    "xodim_tatil": dict(title="Xodimga mehnat ta'tili berish to'g'risida", short="Mehnat ta'tili (xodim)", fields=["date_from", "days"],
                        req=["date_from", "days"], effect=False, staff=True),
}
STAFF_KINDS = tuple(k for k, v in KINDS.items() if v.get("staff"))
def is_staff_kind(k) -> bool: return k in STAFF_KINDS
EXIT_KINDS = ("chetlashtirish_xohish", "chetlashtirish_tolov", "kochirish", "akademik_qarz")
# guruhni o'zgartiradigan turlar (muvofiqlik auditi: oxirgi buyruqdagi guruh) va ta'lim shaklini ham guruhdan oladigan turlar (academic_flows)
GROUP_KINDS = ("guruh", "tiklash", "tatildan_qaytish", "ichki_kochirish", "kochirib_qabul", "kursda_qoldirish")
FORM_KINDS = ("ichki_kochirish", "kochirib_qabul", "kursda_qoldirish")
ADMIT_KINDS = ("qabul", "tiklash", "kochirib_qabul")
GRADUATED = "bitirgan"
FIELD_LABELS = {"old_surname": "Eski familiya", "new_surname": "Yangi familiya", "basis": "Asos hujjat", "reason": "Sabab",
                "date_from": "Sanadan", "date_to": "Sanagacha", "group_to": "Yangi guruh", "target": "Qabul qiluvchi OTM",
                "days": "Kunlar soni", "source_otm": "Avvalgi OTM", "contract_amount": "Kontrakt summasi (so'm)"}
BASIS = {"familiya": "talabaning arizasi va {basis}", "akademik_tatil": "talabaning arizasi va tegishli tasdiqlovchi hujjat (tibbiy xulosa / guvohnoma)",
         "tatildan_qaytish": "talabaning arizasi va akademik ta'til muddati tugaganligi", "chetlashtirish_xohish": "talabaning arizasi",
         "chetlashtirish_tolov": "buxgalteriyaning qarzdorlik to'g'risidagi ma'lumotnomasi va Registrator ofisining bildirgisi",
         "kochirish": "talabaning arizasi va qabul qiluvchi oliy ta'lim muassasasining roziligi", "guruh": "talabaning arizasi va Registrator ofisining taqdimnomasi",
         "tiklash": "talabaning arizasi va Registrator ofisining taqdimnomasi", "qabul": "qabul komissiyasining qarori", "kurs": "o'quv rejasini to'liq bajarganligi (yakuniy nazorat natijalari)",
         "bekor": "Registrator ofisining bildirgisi (xato aniqlangan)", "hayfsan": "Registrator ofisining bildirgisi va davomat jurnali ma'lumotlari",
         "xodim_tatil": "xodimning arizasi va ta'tillar jadvali",
         "akademik_qarz": "qayta topshirish natijalari (baholar tarixi), belgilangan muddatda akademik qarzdorlik tugatilmaganligi va Registrator ofisining bildirgisi",
         "ichki_kochirish": "talabaning arizasi, akademik farq fanlari ro'yxati va Registrator ofisining taqdimnomasi",
         "kochirib_qabul": "talabaning arizasi, avvalgi OTM akademik ma'lumotnomasi (transkripti) va akademik farq fanlari ro'yxati",
         "kursda_qoldirish": "talabaning arizasi va qayta topshirish natijalari (baholar tarixi)",
         "qayta_oqish": "talabalarning arizalari va qayta topshirish natijalari (baholar tarixi)",
         "isft_granti": "ISFT granti komissiyasining yillik reyting (kredit bilan tortilgan GPA) bo'yicha qarori",
         "isft_granti_mahrum": "ISFT granti komissiyasining qarori (akademik qarzdorlik yoki GPA belgilangan chegaradan past)",
         "bitirish": "o'quv rejasining to'liq bajarilganligi, bitiruv ishi (magistrlik dissertatsiyasi) himoyasi va yakuniy davlat attestatsiyasi natijalari"}
STATUS = {"loyiha": "Loyiha", "yuborilgan": "Imzoga yuborilgan", "kelishilgan": "Prorektor kelishgan", "imzolangan": "Imzolangan",
          "bekor": "O'chirilgan loyiha", "bekor_qilingan": "Bekor qilingan"}
ACTIVE = ("faol", "akademik ta'til")
EXPELLED = "chetlashtirilgan"

# Ruxsatlar
EDIT = ("talabalar", "registrator_xodim", "sirtqi")   # Registrator ofisi (boshlig'i va xodimlari); sirtqi — faqat sirtqi talabalar
STAFF_EDIT = ("kadrlar",)                            # xodimlar buyruqlari (mehnat ta'tili)
FIX = EDIT + ("malumotlar_bazasi",)
READ = EDIT + ("prorektor_oquv", "rektor", "malumotlar_bazasi")   # talabalar ma'lumoti (ro'yxat, audit, jurnal)
CHANCERY = ("devonxona",)                            # rbac.CHANCERY: reyestr, ro'yxatga olish, chiquvchi yozishmalar
REG_READ = READ + STAFF_EDIT + CHANCERY              # buyruqlar reyestri (ko'lam ord_scope bo'yicha)
FORWARD = ("prorektor_oquv",)
SIGN = ("rektor",)

def _now(): return clock.now().isoformat(timespec="seconds")
def _today(): return clock.today()
def _short(name): return (name or "").split(":", 1)[1].strip() if ":" in (name or "") else (name or "")
def _j(s, d=None):
    try: return json.loads(s) if s else (d if d is not None else {})
    except (TypeError, ValueError): return d if d is not None else {}
def _d_uz(d):
    from .documents import d_uz
    try: return d_uz(d)
    except Exception: return str(d or "")

# ---------------------------------------------------------------------------------------------
# Sxema
# ---------------------------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, status TEXT, reg_no TEXT, order_date TEXT,
  study_form TEXT, source TEXT, basis TEXT, note TEXT, params TEXT, version INT DEFAULT 0, count INT DEFAULT 0,
  created_by INT, created_at TEXT, submitted_at TEXT, forwarded_by INT, forwarded_at TEXT, signed_by INT, signed_at TEXT,
  applied_at TEXT, returned_note TEXT, cancels_id INT, cancelled_by INT, verify_code TEXT, file TEXT, historic INT DEFAULT 0, demo TEXT);
CREATE TABLE IF NOT EXISTS order_students(id INTEGER PRIMARY KEY, order_id INT, version INT, student_id INT, hemis_id TEXT, full_name TEXT,
  group_id INT, group_name TEXT, course INT, data TEXT, raw TEXT, prev TEXT, applied INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS order_versions(id INTEGER PRIMARY KEY, order_id INT, no INT, created_by INT, created_by_name TEXT, created_at TEXT,
  source TEXT, filename TEXT, file TEXT, count INT, added INT, removed INT, unmatched INT, restored_from INT, note TEXT, UNIQUE(order_id, no));
CREATE TABLE IF NOT EXISTS order_files(id INTEGER PRIMARY KEY, order_id INT, kind TEXT, filename TEXT, stored TEXT, size INT,
  uploaded_by INT, uploaded_name TEXT, uploaded_at TEXT, student_id INT, note TEXT);
CREATE TABLE IF NOT EXISTS order_applications(id INTEGER PRIMARY KEY, created_by INT, created_at TEXT, filename TEXT, stored TEXT, method TEXT,
  text TEXT, kind TEXT, fields TEXT, student_id INT, order_id INT, status TEXT);
CREATE TABLE IF NOT EXISTS order_log(id INTEGER PRIMARY KEY, order_id INT, ts TEXT, user_id INT, user_name TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS student_changes(id INTEGER PRIMARY KEY, ts TEXT, student_id INT, field TEXT, old TEXT, new TEXT, order_id INT,
  reg_no TEXT, user_id INT, user_name TEXT, note TEXT, reverted INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS order_issue_fixes(id INTEGER PRIMARY KEY, key TEXT, kind TEXT, student_id INT, action TEXT, file_id INT,
  ref_order_id INT, new_order_id INT, user_id INT, user_name TEXT, ts TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_os_order ON order_students(order_id, version);
CREATE INDEX IF NOT EXISTS ix_os_student ON order_students(student_id);
CREATE INDEX IF NOT EXISTS ix_ord_status ON orders(status, kind);
CREATE INDEX IF NOT EXISTS ix_sc_student ON student_changes(student_id);
CREATE INDEX IF NOT EXISTS ix_ol_order ON order_log(order_id);
CREATE TABLE IF NOT EXISTS outgoing_mail(id INTEGER PRIMARY KEY, out_no TEXT UNIQUE, out_date TEXT, addressee TEXT, subject TEXT, order_id INT,
  thread_id INT, pages INT, note TEXT, created_by INT, created_by_name TEXT, created_at TEXT);
"""
JOURNAL_COLS = [("journal_at", "TEXT"), ("journal_by", "INT"), ("journal_note", "TEXT")]   # Devonxona: ro'yxatga olish

def init(con, fresh=False):
    """Jadvallar + (bo'sh bo'lsa) reyestr seed'i, namuna arizalar va demo buyruqlar. Qayta chaqirish xavfsiz (idempotent)."""
    try:
        con.executescript(SCHEMA); con.commit()
        have = {r[1] for r in con.execute("PRAGMA table_info(orders)")}
        for col, ty in JOURNAL_COLS:
            if col not in have: con.execute(f"ALTER TABLE orders ADD COLUMN {col} {ty}")
        con.commit()
        for d in (UPL, OUTD, SAMPLES): d.mkdir(parents=True, exist_ok=True)
        if con.execute("SELECT COUNT(*) FROM students").fetchone()[0]:
            from . import seed_orders
            seed_orders.run(con, force=fresh)
    except Exception as e:          # bo'sh baza (seed boshlanmagan) — server baribir ishga tushsin
        import traceback; traceback.print_exc()
        print("orders.init:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
    try:
        from . import staff_absence as SA
        SA.ensure_order_col(con)
        migrate_legacy_docs(con)
        seed_outgoing_demo(con)
    except Exception as e:
        import traceback; traceback.print_exc(); print("orders.migrate_legacy_docs:", e)

# ---------------------------------------------------------------------------------------------
# Ruxsat va ko'lam
# ---------------------------------------------------------------------------------------------
NEED = {"read": REG_READ, "read_st": READ, "edit": EDIT, "edit_any": EDIT + STAFF_EDIT, "fix": FIX, "forward": FORWARD, "sign": SIGN,
        "register": CHANCERY, "outgoing": CHANCERY + SIGN}
DENY_MSG = {"read": "Buyruqlar reyestri Registrator ofisi, Sirtqi bo'lim, Ma'lumotlar bazasi bo'limi, O'quv ishlari prorektori, Kadrlar bo'limi, Devonxona va Rektor uchun",
            "read_st": "Talabalar ro'yxatlari, muvofiqlik auditi va o'zgarishlar jurnali Registrator ofisi, Sirtqi bo'lim, Ma'lumotlar bazasi bo'limi, O'quv ishlari prorektori va Rektor uchun",
            "edit_any": "Buyruq loyihasini Registrator ofisi (talabalar) yoki Kadrlar bo'limi (xodimlar) tayyorlaydi",
            "register": "Buyruqni devonxona jurnaliga Devonxona ro'yxatga oladi",
            "outgoing": "Chiquvchi yozishmalar jurnalini Devonxona yuritadi",
            "edit": "Buyruq loyihasini Registrator ofisi (sirtqi talabalar uchun — Sirtqi bo'lim) tayyorlaydi",
            "fix": "Muvofiqlik tuzatishlarini Registrator ofisi, Sirtqi bo'lim va Ma'lumotlar bazasi bo'limi kiritadi",
            "forward": "Buyruqni O'quv ishlari bo'yicha prorektor kelishadi", "sign": "Buyruqlarni faqat Rektor imzolaydi"}

def C(request: Request, need="read", action="", detail="") -> Ctx:
    c = _ctx(request)
    if c.role.key not in NEED[need]:
        rbac.audit(_con, c, f"buyruqlar: {action or need}", RES, False, detail)
        raise AccessDenied(f"⛔ {DENY_MSG[need]}. So'rov audit jurnaliga yozildi.")
    return c

def _deny(c, action, msg, detail=""):
    rbac.audit(_con, c, f"buyruqlar: {action}", RES, False, detail)
    raise AccessDenied(f"⛔ {msg}. Urinish audit jurnaliga yozildi.")

def _audit(c, action, detail=""): rbac.audit(_con, c, f"buyruqlar: {action}", RES, True, detail)

def is_sirtqi(c: Ctx) -> bool: return c.role.key == "sirtqi"
def st_scope(c: Ctx, alias="s") -> str: return f"{alias}.study_form='sirtqi'" if is_sirtqi(c) else "1=1"
_STAFF_SQL = "(" + ",".join(f"'{k}'" for k in STAFF_KINDS) + ")"
def ord_scope(c: Ctx, alias="o") -> str:
    """Ko'lam: Kadrlar — faqat xodimlar buyruqlari; talabalar bilan ishlovchi bo'limlar — faqat talabalar buyruqlari (sirtqi — sirtqi);
    Rektor va Devonxona — hammasi."""
    k = c.role.key
    if k in SIGN + CHANCERY: return "1=1"
    if k in STAFF_EDIT: return f"{alias}.kind IN {_STAFF_SQL}"
    base = f"{alias}.kind NOT IN {_STAFF_SQL}"
    return f"{base} AND {alias}.study_form='sirtqi'" if is_sirtqi(c) else base

def can_edit_order(c: Ctx, o: dict) -> bool:
    return c.role.key in (STAFF_EDIT if is_staff_kind(o["kind"]) else EDIT)

def _order(c: Ctx, oid: int) -> dict:
    o = db.one(_con, f"SELECT * FROM orders o WHERE o.id=? AND {ord_scope(c)}", (oid,))
    if not o:
        if is_sirtqi(c) and db.one(_con, "SELECT 1 x FROM orders WHERE id=?", (oid,)):
            _deny(c, "buyruqni ochish", "Sirtqi bo'lim faqat sirtqi ta'lim talabalari buyruqlarini ko'radi", f"#{oid}")
        raise HTTPException(404, "Buyruq topilmadi")
    return o

def _log(oid, c: Ctx | None, action, detail=""):
    _con.execute("INSERT INTO order_log(order_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                 (oid, _now(), c.user["id"] if c else None, (c.user["full_name"] if c else "Tizim"), action, (detail or "")[:500]))

def _bad(msg): raise HTTPException(400, msg)

# ---------------------------------------------------------------------------------------------
# Talaba va guruh
# ---------------------------------------------------------------------------------------------
def _students(ids) -> dict:
    ids = [int(i) for i in ids if i]
    out = {}
    for k in range(0, len(ids), 900):
        part = ids[k:k + 900]
        for r in db.rows(_con, f"""SELECT s.id, s.hemis_id, s.full_name, s.group_id, s.faculty_id, s.status, s.study_form, s.payment_type, g.name grp, g.course
                                   FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id IN ({','.join('?' * len(part))})""", part):
            out[r["id"]] = r
    return out

def _group(v) -> dict | None:
    if v in (None, ""): return None
    if isinstance(v, int) or str(v).isdigit():
        return db.one(_con, "SELECT id, name, course, faculty_id, form, level FROM groups_ WHERE id=?", (int(v),))
    return db.one(_con, "SELECT id, name, course, faculty_id, form, level FROM groups_ WHERE upper(name)=?", (str(v).strip().upper(),))

def _norm_data(kind, data: dict) -> dict:
    """Maydonlarni tozalash: faqat shu tur maydonlari; guruh nomi → id; sanalar ISO."""
    out = {}
    for f in KINDS[kind]["fields"] + (["group_from"] if kind == "guruh" else []):
        v = (data or {}).get(f)
        if v in (None, ""): continue
        v = str(v).strip()[:300]
        if f.startswith("date_"):
            try: v = dt.date.fromisoformat(v[:10]).isoformat()
            except ValueError: _bad(f"«{FIELD_LABELS.get(f, f)}» sanasi noto'g'ri: {v}")
        if f == "group_to":
            g = _group((data or {}).get("group_to_id") or v)
            if not g: _bad(f"Guruh topilmadi: {v}")
            out["group_to_id"] = g["id"]; v = g["name"]
        out[f] = v
    if kind == "akademik_tatil" and out.get("date_from") and out.get("date_to") and out["date_to"] < out["date_from"]:
        _bad("Akademik ta'til tugash sanasi boshlanishidan oldin bo'lishi mumkin emas")
    return out

def _item_of(s: dict, data=None, raw=None) -> dict:
    return {"student_id": s["id"], "hemis_id": s["hemis_id"], "full_name": s["full_name"], "group_id": s["group_id"],
            "group_name": s.get("grp"), "course": s.get("course"), "data": data or {}, "raw": raw}

# ---------------------------------------------------------------------------------------------
# Versiyalar
# ---------------------------------------------------------------------------------------------
def _key(it) -> str:
    return f"s{it['student_id']}" if it.get("student_id") else "r" + IN.name_key(str(it.get("hemis_id") or "") + " " + str(it.get("full_name") or ""))

def items(oid: int, version: int | None = None) -> list[dict]:
    if version is None:
        version = db.one(_con, "SELECT version FROM orders WHERE id=?", (oid,))["version"]
    rs = db.rows(_con, "SELECT * FROM order_students WHERE order_id=? AND version=? ORDER BY id", (oid, version))
    for r in rs: r["data"] = _j(r["data"]); r["raw"] = _j(r["raw"], None)
    return rs

def _form_of(oid: int, version: int, fallback):
    fs = [r["f"] for r in db.rows(_con, """SELECT DISTINCT s.study_form f FROM order_students i JOIN students s ON s.id=i.student_id
                                          WHERE i.order_id=? AND i.version=?""", (oid, version))]
    return (fs[0] if len(fs) == 1 else "aralash") if fs else fallback

def new_version(o: dict, new_items: list[dict], c: Ctx | None, source: str, filename=None, file=None, restored_from=None, note=None,
                by_name=None, ts=None) -> dict:
    """Ro'yxatning to'liq yangi nusxasi (eski versiyalar o'zgarmaydi). → versiya yozuvi (+/− farq bilan)."""
    old = items(o["id"], o["version"]) if o["version"] else []
    ok_, nk = {_key(i) for i in old}, {_key(i) for i in new_items}
    no = (o["version"] or 0) + 1
    unmatched = sum(1 for i in new_items if not i.get("student_id"))
    _con.execute("""INSERT INTO order_versions(order_id,no,created_by,created_by_name,created_at,source,filename,file,count,added,removed,unmatched,restored_from,note)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (o["id"], no, c.user["id"] if c else None, by_name or (c.user["full_name"] if c else "Tizim"), ts or _now(), source, filename, file,
                  len(new_items), len(nk - ok_), len(ok_ - nk), unmatched, restored_from, note))
    _con.executemany("""INSERT INTO order_students(order_id,version,student_id,hemis_id,full_name,group_id,group_name,course,data,raw)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     [(o["id"], no, i.get("student_id"), i.get("hemis_id"), i.get("full_name"), i.get("group_id"), i.get("group_name"), i.get("course"),
                       json.dumps(i.get("data") or {}, ensure_ascii=False), json.dumps(i["raw"], ensure_ascii=False) if i.get("raw") else None) for i in new_items])
    form = _form_of(o["id"], no, o.get("study_form"))
    _con.execute("UPDATE orders SET version=?, count=?, study_form=? WHERE id=?", (no, len(new_items), form, o["id"]))
    o.update(version=no, count=len(new_items), study_form=form)
    v = {"no": no, "count": len(new_items), "added": len(nk - ok_), "removed": len(ok_ - nk), "unmatched": unmatched, "source": source}
    _log(o["id"], c, f"ro'yxat: {no}-versiya", f"{source} · {len(new_items)} ta (+{v['added']} / −{v['removed']})" + (f" · {unmatched} ta mos emas" if unmatched else ""))
    return v

def _editable(c: Ctx, o: dict):
    if o["status"] == "imzolangan" or o["status"] == "bekor_qilingan":
        _deny(c, "imzolangan buyruqni o'zgartirish", "Imzolangan buyruq ro'yxati muzlatilgan — o'zgartirish faqat tuzatuvchi buyruq orqali", o.get("reg_no") or f"#{o['id']}")
    if o["status"] != "loyiha":
        _bad("Buyruq imzoga yuborilgan — o'zgartirish uchun avval qaytarilishi kerak" if o["status"] in ("yuborilgan", "kelishilgan") else "Bu buyruqni o'zgartirib bo'lmaydi")

def _check_scope_students(c: Ctx, studs: list[dict], action: str):
    if is_sirtqi(c):
        bad = [s for s in studs if s.get("study_form") != "sirtqi"]
        if bad: _deny(c, action, f"Sirtqi bo'lim faqat sirtqi ta'lim talabalari bilan ishlaydi ({len(bad)} ta boshqa shakldagi talaba)", bad[0]["full_name"])

# ---------------------------------------------------------------------------------------------
# Tekshiruvlar (imzodan oldin)
# ---------------------------------------------------------------------------------------------
def checks(o: dict, its: list[dict] | None = None) -> dict:
    if is_staff_kind(o["kind"]):
        p = _j(o.get("params")); errors = []
        if not p.get("staff_id"): errors.append("Xodim tanlanmagan")
        miss = [FIELD_LABELS[f] for f in KINDS[o["kind"]]["req"] if not p.get(f)]
        if miss: errors.append("Majburiy maydon to'ldirilmagan: " + ", ".join(miss))
        return {"errors": errors, "warnings": []}
    its = its if its is not None else items(o["id"])
    st = _students([i["student_id"] for i in its if i["student_id"]])
    params = _j(o.get("params"))
    errors, warns = [], []
    um = [i for i in its if not i["student_id"]]
    if um: errors.append(f"{len(um)} ta qator bazadagi talabaga moslanmagan — ro'yxatdan olib tashlang yoki tuzating")
    if not its: errors.append("Ro'yxat bo'sh")
    k = o["kind"]; req = KINDS[k]["req"]
    miss = [i for i in its if i["student_id"] and any(not ({**params, **i["data"]}).get(f) for f in req)]
    if miss: errors.append(f"{len(miss)} ta talabada majburiy maydon to'ldirilmagan: " + ", ".join(FIELD_LABELS[f] for f in req))
    w = {}
    def add(msg, i): w.setdefault(msg, []).append(i["full_name"])
    for i in its:
        s = st.get(i["student_id"])
        if not s: continue
        d = {**params, **i["data"]}
        if k == "akademik_tatil" and s["status"] != "faol": add("talaba hozir faol emas", i)
        if k == "tatildan_qaytish" and s["status"] != "akademik ta'til": add("talaba akademik ta'tilda emas", i)
        if k in EXIT_KINDS and s["status"] == EXPELLED: add("talaba allaqachon chetlashtirilgan", i)
        if k == "tiklash" and s["status"] != EXPELLED: add("talaba chetlashtirilgan emas (tiklash shart emas)", i)
        if k == "guruh" and d.get("group_to_id") == s["group_id"]: add("yangi guruh joriy guruh bilan bir xil", i)
        if k == "familiya" and d.get("old_surname") and s["full_name"].split()[0].lower() != str(d["old_surname"]).lower(): add("eski familiya bazadagidan farq qiladi", i)
        if k in ("ichki_kochirish", "kursda_qoldirish", "isft_granti", "isft_granti_mahrum", "bitirish") and s["status"] != "faol": add("talaba hozir faol emas", i)
        if k in FORM_KINDS and d.get("group_to_id") == s["group_id"]: add("yangi guruh joriy guruh bilan bir xil", i)
        if k == "isft_granti" and s.get("payment_type") == "grant": add("talaba allaqachon grant asosida o'qiydi", i)
        if k == "isft_granti_mahrum" and s.get("payment_type") != "grant": add("talaba grant asosida o'qimaydi", i)
        if s["full_name"] != i["full_name"] and k != "bekor": add("F.I.Sh. ro'yxat tuzilgandan keyin o'zgargan", i)
    for msg, names in w.items():
        warns.append(f"{len(names)} ta: {msg}" + (f" ({', '.join(names[:3])}{'…' if len(names) > 3 else ''})" if names else ""))
    # boshqa ko'rib chiqilayotgan buyruqlarda ham bor
    ids = [i["student_id"] for i in its if i["student_id"]]
    if ids and len(ids) <= 5000:
        other = db.one(_con, f"""SELECT COUNT(DISTINCT i.student_id) n FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                                 WHERE o.id!=? AND o.status IN ('loyiha','yuborilgan','kelishilgan') AND i.student_id IN ({','.join(map(str, ids))})""", (o["id"],))["n"]
        if other: warns.append(f"{other} ta talaba boshqa ko'rib chiqilayotgan buyruq loyihasida ham bor")
    if k in EXIT_KINDS and len(ids) > 500: warns.append(f"Katta ro'yxat: imzolansa {len(ids)} ta talaba holati «chetlashtirilgan»ga o'zgaradi")
    return {"errors": errors, "warnings": warns}

# ---------------------------------------------------------------------------------------------
# Ta'sir (imzo) va bekor qilish
# ---------------------------------------------------------------------------------------------
def _change(sid, field, old, new, o, c, note=""):
    _con.execute("""INSERT INTO student_changes(ts,student_id,field,old,new,order_id,reg_no,user_id,user_name,note) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                 (_now(), sid, field, None if old is None else str(old), None if new is None else str(new), o["id"] if o else None,
                  o.get("reg_no") if o else None, c.user["id"] if c else None, c.user["full_name"] if c else "Tizim", note))

ST_COLS = "id, full_name, status, group_id, faculty_id, study_form, payment_type, contract_amount"   # buyruq ta'sir qiladigan (va qaytariladigan) maydonlar

def _apply_item(o, it, c) -> dict:
    s = db.one(_con, f"SELECT {ST_COLS} FROM students WHERE id=?", (it["student_id"],))
    if not s: return {}
    d = {**_j(o.get("params")), **it["data"]}
    k = o["kind"]; upd = {}; extra = {}
    if k == "familiya":
        parts = s["full_name"].split()
        newsur = str(d.get("new_surname") or "").strip()
        if newsur and parts and parts[0] != newsur: upd["full_name"] = " ".join([newsur] + parts[1:])
    elif k == "akademik_tatil":
        upd["status"] = "akademik ta'til"
        cur = _con.execute("INSERT INTO student_leaves(student_id,kind,start,end,order_no) VALUES(?,?,?,?,?)",
                           (s["id"], "akademik", d.get("date_from"), d.get("date_to"), o["reg_no"]))
        extra["leave_id"] = cur.lastrowid
    elif k == "tatildan_qaytish":
        upd["status"] = "faol"
        lv = db.one(_con, "SELECT id, end FROM student_leaves WHERE student_id=? ORDER BY start DESC, id DESC LIMIT 1", (s["id"],))
        if lv and d.get("date_from") and (lv["end"] or "9999") > d["date_from"]:
            extra["leave_upd"] = {"id": lv["id"], "end": lv["end"]}
            _con.execute("UPDATE student_leaves SET end=? WHERE id=?", (d["date_from"], lv["id"]))
        if d.get("group_to_id"): upd["group_id"] = int(d["group_to_id"])
    elif k in EXIT_KINDS:
        upd["status"] = EXPELLED
    elif k == "guruh":
        if d.get("group_to_id"): upd["group_id"] = int(d["group_to_id"])
    elif k == "tiklash":
        upd["status"] = "faol"
        if d.get("group_to_id"): upd["group_id"] = int(d["group_to_id"])
    elif k in FORM_KINDS:   # ichki ko'chirish, ko'chirish tartibida qabul, kursda qoldirish — guruh (va guruhdan ta'lim shakli)
        if d.get("group_to_id"): upd["group_id"] = int(d["group_to_id"])
        if k == "kochirib_qabul": upd["status"] = "faol"
    elif k == "isft_granti":
        upd["payment_type"] = "grant"; upd["contract_amount"] = 0
    elif k == "isft_granti_mahrum":
        upd["payment_type"] = "kontrakt"
        if str(d.get("contract_amount") or "").isdigit(): upd["contract_amount"] = int(d["contract_amount"])
    elif k == "bitirish":
        upd["status"] = GRADUATED
    if "group_id" in upd:
        g = _group(upd["group_id"])
        if g and g["faculty_id"] != s["faculty_id"]: upd["faculty_id"] = g["faculty_id"]
        if g and k in FORM_KINDS and g.get("form") and g["form"] != s["study_form"]: upd["study_form"] = g["form"]
    upd = {f: v for f, v in upd.items() if s[f] != v}
    if upd:
        _con.execute(f"UPDATE students SET {', '.join(f'{f}=?' for f in upd)} WHERE id=?", (*upd.values(), s["id"]))
        for f, v in upd.items(): _change(s["id"], f, s[f], v, o, c, f"{o['reg_no']}: {KINDS[k]['short']}")
    prev = {"before": {f: s[f] for f in upd}, "after": upd, **extra}
    _con.execute("UPDATE order_students SET prev=?, applied=1 WHERE id=?", (json.dumps(prev, ensure_ascii=False), it["id"]))
    return upd

def _revert(target: dict, o: dict, c) -> dict:
    """Bekor qilinayotgan buyruqning o'zgarishlarini qaytarish. Keyinroq boshqa buyruq bilan o'zgargan maydon tegilmaydi (ziddiyat jurnalga)."""
    n_ok, conflicts = 0, []
    for it in items(target["id"], target["version"]):
        p = _j(it.get("prev"))
        if not it.get("applied") or not p: continue
        s = db.one(_con, f"SELECT {ST_COLS} FROM students WHERE id=?", (it["student_id"],))
        if not s: continue
        back = {}
        for f, v in (p.get("after") or {}).items():
            if str(s.get(f)) == str(v): back[f] = p["before"].get(f)
            else: conflicts.append(f"{s['full_name']}: «{f}» keyinroq o'zgargan ({s.get(f)}) — qaytarilmadi")
        if back:
            _con.execute(f"UPDATE students SET {', '.join(f'{f}=?' for f in back)} WHERE id=?", (*back.values(), s["id"]))
            for f, v in back.items(): _change(s["id"], f, s[f], v, o, c, f"{o['reg_no']}: {target['reg_no']} bekor qilindi")
            n_ok += 1
        if p.get("leave_id"): _con.execute("DELETE FROM student_leaves WHERE id=?", (p["leave_id"],))
        if p.get("leave_upd"): _con.execute("UPDATE student_leaves SET end=? WHERE id=?", (p["leave_upd"]["end"], p["leave_upd"]["id"]))
    _con.execute("UPDATE student_changes SET reverted=1 WHERE order_id=?", (target["id"],))
    _con.execute("UPDATE orders SET status='bekor_qilingan', cancelled_by=? WHERE id=?", (o["id"], target["id"]))
    _log(target["id"], c, "bekor qilindi", f"{o['reg_no']}-son tuzatuvchi buyruq bilan · {n_ok} ta talaba ma'lumoti qaytarildi" + (f" · {len(conflicts)} ta ziddiyat" if conflicts else ""))
    for x in conflicts[:50]: _log(target["id"], c, "ziddiyat", x)
    return {"reverted": n_ok, "conflicts": conflicts[:50]}

def next_reg(year=None, prefix="TB") -> str:
    """TB — talabalar buyruqlari, ShT — xodimlar (shaxsiy tarkib) buyruqlari. Hujjatlar markazining eski raqamlari bilan to'qnashmaydi."""
    yy = f"{(year or _today().year) % 100:02d}"
    n = 0
    for r in db.rows(_con, "SELECT reg_no FROM orders WHERE reg_no LIKE ? UNION SELECT reg_no FROM documents WHERE reg_no LIKE ?", (f"{prefix}-{yy}/%",) * 2):
        try: n = max(n, int(r["reg_no"].split("/")[1]))
        except (ValueError, IndexError, AttributeError): pass
    return f"{prefix}-{yy}/{n + 1:04d}"

def sign(o: dict, c: Ctx, base_url: str) -> dict:
    with _lock:
        o = db.one(_con, "SELECT * FROM orders WHERE id=?", (o["id"],))
        if o["status"] not in ("yuborilgan", "kelishilgan"): _bad("Faqat imzoga yuborilgan buyruq imzolanadi")
        its = items(o["id"])
        ch = checks(o, its)
        if ch["errors"]: _bad("Imzolab bo'lmaydi: " + "; ".join(ch["errors"]))
        if o["kind"] == "bekor":
            tgt = db.one(_con, "SELECT * FROM orders WHERE id=?", (o["cancels_id"],))
            if not tgt or tgt["status"] != "imzolangan": _bad("Bekor qilinayotgan buyruq imzolangan holatda emas")
        reg, today = next_reg(prefix="ShT" if is_staff_kind(o["kind"]) else "TB"), _today().isoformat()
        code = secrets.token_hex(4).upper()
        try:
            _con.execute("UPDATE orders SET status='imzolangan', reg_no=?, order_date=?, signed_by=?, signed_at=?, verify_code=? WHERE id=?",
                         (reg, today, c.user["id"], _now(), code, o["id"]))
            o.update(status="imzolangan", reg_no=reg, order_date=today, verify_code=code)
            res = {"changed": 0}
            if o["kind"] == "bekor":
                res = _revert(tgt, o, c)
            elif KINDS[o["kind"]]["effect"]:
                for it in its:
                    if _apply_item(o, it, c): res["changed"] += 1
            _con.execute("UPDATE orders SET applied_at=? WHERE id=?", (_now(), o["id"]))
            _log(o["id"], c, "imzolandi", f"{reg} · {today} · " + (f"{res.get('reverted', 0)} ta talaba ma'lumoti qaytarildi" if o["kind"] == "bekor"
                                                                   else "xodimlar buyrug'i" if is_staff_kind(o["kind"]) else f"bazaga ta'sir: {res['changed']} ta talaba"))
            _con.commit()
        except Exception:
            _con.rollback(); raise
    fname = _publish(o, c, base_url)
    _audit(c, "buyruq imzolandi", f"{reg} · {KINDS[o['kind']]['short']} · " + (_j(o.get("params")).get("staff_name", "xodim") if is_staff_kind(o["kind"]) else f"{len(its)} ta talaba"))
    return {"ok": True, "reg_no": reg, "date": today, "file": fname, **res}

def _publish(o: dict, c: Ctx, base_url: str) -> str | None:
    """Imzolangan buyruq DOCX'i Hujjatlar markazi papkasiga + documents jadvaliga (QR tekshiruvi /verify/{kod} ishlaydi)."""
    from . import documents as D
    try:
        o = db.one(_con, "SELECT * FROM orders WHERE id=?", (o["id"],))
        p = render_docx(o, base_url)
        D.OUT.mkdir(parents=True, exist_ok=True)
        fname = f"{o['reg_no'].replace('/', '-')}.docx"
        (D.OUT / fname).write_bytes(p.read_bytes())
        its = items(o["id"])
        one = its[0]["full_name"] if len(its) == 1 else _j(o.get("params")).get("staff_name") if is_staff_kind(o["kind"]) else None
        holder = (lambda n: (n[0] + " " + " ".join(x[0] + "." for x in n[1:3])) if n else "")(one.split()) if one else f"{len(its)} nafar talaba"
        cr = db.one(_con, "SELECT full_name, role FROM users WHERE id=?", (o["created_by"],)) if o.get("created_by") else None
        if not db.one(_con, "SELECT 1 x FROM documents WHERE reg_no=?", (o["reg_no"],)):
            _con.execute("""INSERT INTO documents(reg_no,kind,title,holder,created_by,creator_role,created_at,status,verify_code,file,params,signed_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (o["reg_no"], "orders", f"Buyruq: {KINDS[o['kind']]['title']}", holder, o["created_by"] or c.user["id"],
                          rbac.user_title(cr) if cr else ("Kadrlar bo'limi" if is_staff_kind(o["kind"]) else "Registrator ofisi"), _now(), "imzolangan", o["verify_code"], fname,
                          json.dumps({"order_id": o["id"]}), _now()))
        _con.execute("UPDATE orders SET file=? WHERE id=?", (fname, o["id"])); _con.commit()
        return fname
    except Exception as e:
        print("orders._publish:", e)
        return None

# ---------------------------------------------------------------------------------------------
# DOCX (oxirgi versiyadan)
# ---------------------------------------------------------------------------------------------
def _cols(kind):
    base = [("F.I.Sh.", lambda i, d: i["full_name"]), ("HEMIS ID", lambda i, d: i["hemis_id"] or ""), ("Guruh", lambda i, d: i["group_name"] or "")]
    per = {"familiya": [("Yangi familiya", lambda i, d: d.get("new_surname", "")), ("Asos", lambda i, d: d.get("basis", ""))],
           "akademik_tatil": [("Muddat", lambda i, d: f"{_dmy(d.get('date_from'))} – {_dmy(d.get('date_to'))}"), ("Sabab", lambda i, d: d.get("reason", ""))],
           "tatildan_qaytish": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Guruh (yangi)", lambda i, d: d.get("group_to", "") or "—")],
           "chetlashtirish_xohish": [("Sanadan", lambda i, d: _dmy(d.get("date_from")))],
           "chetlashtirish_tolov": [("Sanadan", lambda i, d: _dmy(d.get("date_from")))],
           "kochirish": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Qabul qiluvchi OTM", lambda i, d: d.get("target", ""))],
           "guruh": [("Yangi guruh", lambda i, d: d.get("group_to", ""))],
           "tiklash": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Guruh", lambda i, d: d.get("group_to", ""))],
           "hayfsan": [("Sabab", lambda i, d: d.get("reason", ""))],
           "akademik_qarz": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Asos (qarzdor fanlar)", lambda i, d: d.get("reason", ""))],
           "ichki_kochirish": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Yangi guruh", lambda i, d: d.get("group_to", "")), ("Izoh", lambda i, d: d.get("reason", ""))],
           "kochirib_qabul": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Guruh", lambda i, d: d.get("group_to", "")), ("Avvalgi OTM", lambda i, d: d.get("source_otm", ""))],
           "kursda_qoldirish": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Guruh", lambda i, d: d.get("group_to", ""))],
           "qayta_oqish": [("Fanlar", lambda i, d: d.get("reason", ""))],
           "isft_granti": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Asos", lambda i, d: d.get("reason", ""))],
           "isft_granti_mahrum": [("Sanadan", lambda i, d: _dmy(d.get("date_from"))), ("Sabab", lambda i, d: d.get("reason", ""))],
           "bitirish": [("Sanadan", lambda i, d: _dmy(d.get("date_from")))]}
    return base + per.get(kind, [])

def _dmy(v):
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 and v[4] == "-" else v

CLAUSE = {"familiya": "Quyidagi talabaning familiyasi asos hujjatga muvofiq o'zgartirilsin va barcha o'quv hujjatlarida yangi familiya bilan yuritilsin:",
          "akademik_tatil": "Quyidagi talabalarga ko'rsatilgan muddatga akademik ta'til berilsin:",
          "tatildan_qaytish": "Akademik ta'til muddati tugagan quyidagi talabalar ko'rsatilgan sanadan o'qishga qo'yilsin:",
          "chetlashtirish_xohish": "Quyidagi talabalar o'z xohishiga ko'ra ko'rsatilgan sanadan talabalar safidan chetlashtirilsin:",
          "chetlashtirish_tolov": "To'lov-kontrakt shartnomasi bo'yicha majburiyatini belgilangan muddatda bajarmagan quyidagi talabalar ko'rsatilgan sanadan talabalar safidan chetlashtirilsin:",
          "kochirish": "Quyidagi talabalar boshqa oliy ta'lim muassasasiga o'qishini ko'chirish munosabati bilan talabalar safidan chiqarilsin:",
          "guruh": "Quyidagi talabalar ko'rsatilgan guruhga o'tkazilsin:",
          "tiklash": "Quyidagi talabalar ko'rsatilgan sanadan talabalar safiga qayta tiklansin:",
          "qabul": "Quyidagi shaxslar institut talabalari safiga qabul qilinsin:",
          "kurs": "O'quv rejasini to'liq bajargan quyidagi talabalar keyingi kursga o'tkazilsin:",
          "hayfsan": "Ichki tartib qoidalarini (sababsiz dars qoldirish) buzgani uchun quyidagi talabaga hayfsan e'lon qilinsin:",
          "akademik_qarz": "Qayta topshirish natijalariga ko'ra belgilangan muddatda akademik qarzdorligini tugatmagan quyidagi talabalar ko'rsatilgan sanadan talabalar safidan chetlashtirilsin:",
          "ichki_kochirish": "Quyidagi talabalar arizasiga ko'ra ko'rsatilgan guruhga (ta'lim yo'nalishi / ta'lim shakliga) ko'chirilsin; akademik farq fanlari belgilangan muddatda topshirilsin:",
          "kochirib_qabul": "Boshqa oliy ta'lim muassasasidan o'qishini ko'chirish tartibida quyidagi shaxslar institut talabalari safiga qabul qilinsin; akademik farq fanlari belgilangan muddatda topshirilsin:",
          "kursda_qoldirish": "Akademik qarzdorligini qayta topshirish orqali tugata olmagan quyidagi talabalar arizasiga ko'ra o'quv yilini takroran o'qish uchun kursda qoldirilsin:",
          "qayta_oqish": "Quyidagi talabalarga akademik qarzdor fanlarni to'lov-kontrakt asosida qayta o'qishga ruxsat berilsin:",
          "isft_granti": "ISFT granti komissiyasi qaroriga muvofiq quyidagi talabalar ko'rsatilgan sanadan ISFT granti asosida o'qishga o'tkazilsin:",
          "isft_granti_mahrum": "ISFT granti komissiyasi qaroriga muvofiq quyidagi talabalar ISFT grantidan mahrum qilinsin va ko'rsatilgan sanadan to'lov-kontrakt asosida o'qishga o'tkazilsin:",
          "bitirish": "O'quv rejasini to'liq bajargan, bitiruv ishini (magistrlik dissertatsiyasini) himoya qilgan va yakuniy davlat attestatsiyasidan muvaffaqiyatli o'tgan quyidagi talabalarga diplom berilsin va ular bitiruvchi sifatida talabalar safidan chiqarilsin:"}

def render_docx(o: dict, base_url: str = "http://localhost:8000/") -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from . import brand as B
    its = items(o["id"])
    params = _j(o.get("params"))
    signed = o["status"] in ("imzolangan", "bekor_qilingan") and o.get("reg_no")
    doc = Document(); B.setup(doc); B.letterhead(doc)
    if is_staff_kind(o["kind"]):
        return _render_staff(doc, o, params, signed, base_url)
    B.regline(doc, o["reg_no"] if signed else "LOYIHA", _d_uz(o["order_date"]) if signed else "«___» __________ 20___ y.")
    B.title(doc, "BUYRUQ" if signed else "BUYRUQ (LOYIHA)", o.get("title") or KINDS[o["kind"]]["title"])
    basis = o.get("basis") or BASIS[o["kind"]].format(basis=(its[0]["data"].get("basis") if its else "") or "asos hujjat")
    B.para(doc, f"«Oliy ta'lim to'g'risida»gi qonunchilik, institut Ustavi va ichki nizomlariga muvofiq, {basis} asosida")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; B.run(p, "BUYURAMAN:", 12, True)
    n = 1
    if o["kind"] == "bekor":
        tgt = db.one(_con, "SELECT * FROM orders WHERE id=?", (o["cancels_id"],)) or {}
        B.para(doc, f"{n}. Institutning {_d_uz(tgt.get('order_date')) if tgt.get('order_date') else ''}dagi {tgt.get('reg_no', '')}-son «{tgt.get('title', '')}» buyrug'i "
               f"{('(' + params['reason'] + ') ') if params.get('reason') else ''}bekor qilinsin."); n += 1
        B.para(doc, f"{n}. Mazkur buyruq bilan o'zgartirilgan talabalar ma'lumotlari (jami {len(its)} nafar) avvalgi holatiga qaytarilsin."); n += 1
        rows = [(k, i["full_name"], i["hemis_id"] or "", i["group_name"] or "") for k, i in enumerate(its[:LIST_INLINE], 1)]
        B.table(doc, ["№", "F.I.Sh.", "HEMIS ID", "Guruh"], rows, widths=[0.8, 7, 3.4, 3], size=9.5)
    else:
        B.para(doc, f"{n}. {CLAUSE[o['kind']]}"); n += 1
        cols = _cols(o["kind"])
        if len(its) <= LIST_INLINE:
            rows = [[k] + [str(f(i, {**params, **i['data']}) or "") for _, f in cols] for k, i in enumerate(its, 1)]
            B.table(doc, ["№"] + [h for h, _ in cols], rows, widths=[0.8] + [6 if h == "F.I.Sh." else 3 for h, _ in cols], size=9)
        else:
            by = {}
            for i in its: by[i["group_name"] or "—"] = by.get(i["group_name"] or "—", 0) + 1
            B.para(doc, f"Talabalar ro'yxati (jami {len(its)} nafar) ushbu buyruqning 1-ilovasida keltirilgan. Guruhlar bo'yicha jamlanma:", indent=False, size=11)
            B.table(doc, ["№", "Guruh", "Talabalar soni"], [(k, g, c_) for k, (g, c_) in enumerate(sorted(by.items()), 1)], widths=[1, 6, 3], size=9)
            if params.get("date_from"): B.para(doc, f"Sana: {_d_uz(params['date_from'])}dan.", indent=False, size=11)
    if o["kind"] == "chetlashtirish_tolov":
        B.para(doc, f"{n}. Buxgalteriya talabalarning qarzdorligini hisob-kitobda qayd etsin va undirish choralarini ko'rsin."); n += 1
    if o["kind"] in ("akademik_tatil", "tatildan_qaytish", "tiklash", "chetlashtirish_tolov", "chetlashtirish_xohish", "kochirish", "akademik_qarz", "ichki_kochirish",
                     "kochirib_qabul", "kursda_qoldirish", "qayta_oqish", "isft_granti", "isft_granti_mahrum", "bitirish"):
        B.para(doc, f"{n}. Buxgalteriya to'lov-kontrakt hisob-kitoblarini ushbu buyruqqa muvofiq qayta ko'rib chiqsin."); n += 1
    B.para(doc, f"{n}. Registrator ofisi ushbu o'zgarishlarni HEMIS axborot tizimida 3 ish kuni ichida aks ettirsin."); n += 1
    B.para(doc, f"{n}. Buyruq ijrosini nazorat qilish o'quv ishlari bo'yicha prorektor zimmasiga yuklansin.")
    p = doc.add_paragraph(); B.run(p, f"Asos: {basis}.", 11, False, italic=True)
    B.signature(doc, "Rektor", B.INST["rector_short"])
    cr = db.one(_con, "SELECT full_name FROM users WHERE id=?", (o["created_by"],)) if o.get("created_by") else None
    p = doc.add_paragraph(); B.run(p, f"Loyiha kiritdi: {_short(cr['full_name']) if cr else 'Registrator ofisi'}  _______________", 10.5)
    doc.add_paragraph(); p = doc.add_paragraph(); B.run(p, "KELISHILDI:", 10.5, True, B.RGB_TEAL_DARK)
    fw = f" (kelishildi {_dmy(o['forwarded_at'])})" if o.get("forwarded_at") else ""
    # institutda dekanat yo'q (Yevropa modeli): fakultet darajasidagi vazifani Registrator ofisi bajaradi
    for w in [f"O'quv ishlari bo'yicha prorektor{fw}", "Registrator ofisi boshlig'i"]:
        p = doc.add_paragraph(); B.run(p, f"{w}  _______________", 10.5)
    if signed and o.get("verify_code"):
        B.footer_qr(doc, f"{base_url.rstrip('/')}/verify/{o['verify_code']}", o["verify_code"],
                    "Buyruq institut axborot tizimida ro'yxatga olingan. Haqiqiyligini QR-kod orqali tekshiring.")
    ver = o.get("version")
    p = doc.add_paragraph(); B.run(p, f"Ro'yxat versiyasi: {ver} · ISFT Core «Buyruqlar»", 8, False, B.RGB_GREY)
    OUTD.mkdir(parents=True, exist_ok=True)
    out = OUTD / f"order-{o['id']}-v{ver}{'-signed' if signed else ''}.docx"
    doc.save(out)
    return out

def _render_staff(doc, o: dict, p: dict, signed, base_url) -> Path:
    """Xodimlar buyrug'i (mehnat ta'tili) — Hujjatlar markazidagi «leave_order» matni asosida."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from . import brand as B
    B.regline(doc, o["reg_no"] if signed else "LOYIHA", _d_uz(o["order_date"]) if signed else "«___» __________ 20___ y.")
    B.title(doc, "BUYRUQ" if signed else "BUYRUQ (LOYIHA)", "Mehnat ta'tili berish to'g'risida")
    B.para(doc, "O'zbekiston Respublikasi Mehnat kodeksiga va ta'tillar jadvaliga muvofiq, xodimning arizasi asosida")
    x = doc.add_paragraph(); x.alignment = WD_ALIGN_PARAGRAPH.CENTER; B.run(x, "BUYURAMAN:", 12, True)
    B.para(doc, f"1. {p.get('unit') or ''} — {p.get('position') or ''} {p.get('staff_name') or ''}ga {_d_uz(p.get('date_from'))}dan {_d_uz(p.get('date_to'))}gacha "
                f"{p.get('days')} kalendar kunlik yillik asosiy mehnat ta'tili berilsin.")
    B.para(doc, "2. Buxgalteriya ta'til haqini belgilangan tartibda hisoblab, ta'til boshlanishidan oldin to'lab bersin.")
    B.para(doc, "3. Ta'til davrida xodimning vazifalarini bajarish bo'lim boshlig'i tomonidan taqsimlansin.")
    x = doc.add_paragraph(); B.run(x, f"Asos: {o.get('basis') or BASIS['xodim_tatil']}.", 11, False, italic=True)
    B.signature(doc, "Rektor", B.INST["rector_short"])
    x = doc.add_paragraph(); B.run(x, "Loyiha kiritdi: Kadrlar bo'limi  _______________", 10.5)
    doc.add_paragraph(); x = doc.add_paragraph(); B.run(x, "KELISHILDI:", 10.5, True, B.RGB_TEAL_DARK)
    for w in ["Bosh buxgalter", "Yuriskonsult"]:
        x = doc.add_paragraph(); B.run(x, f"{w}  _______________", 10.5)
    if signed and o.get("verify_code"):
        B.footer_qr(doc, f"{base_url.rstrip('/')}/verify/{o['verify_code']}", o["verify_code"],
                    "Buyruq institut axborot tizimida ro'yxatga olingan. Haqiqiyligini QR-kod orqali tekshiring.")
    OUTD.mkdir(parents=True, exist_ok=True)
    out = OUTD / f"order-{o['id']}-staff{'-signed' if signed else ''}.docx"
    doc.save(out)
    return out

def _staff_params(staff_id: int, date_from: str, days, absence_id=None) -> dict:
    st = db.one(_con, "SELECT * FROM staff WHERE id=?", (int(staff_id or 0),))
    if not st: _bad("Xodim topilmadi")
    try: start = dt.date.fromisoformat(str(date_from)[:10])
    except ValueError: _bad("Ta'til boshlanish sanasi noto'g'ri")
    try: days = int(days or 0) or (56 if st.get("unit") == "Professor-o'qituvchi" else 21)
    except (TypeError, ValueError): _bad("Kunlar soni noto'g'ri")
    if not 1 <= days <= 120: _bad("Kunlar soni 1–120 oralig'ida bo'lishi kerak")
    p = {"staff_id": st["id"], "staff_name": st["full_name"], "position": st.get("position"), "unit": st.get("unit"),
         "date_from": start.isoformat(), "days": days, "date_to": (start + dt.timedelta(days=days - 1)).isoformat()}
    if absence_id: p["absence_id"] = int(absence_id)
    return p

def draft_staff_leave(con, c: Ctx, staff_id: int, date_from: str, days=None, absence_id=None, source="Xodimlar ta'tili", status="loyiha",
                      created_at=None) -> dict:
    """Xodimga mehnat ta'tili buyrug'i loyihasi (Buyruqlar — yagona joy). staff_absence.link_order va eski hujjatlar migratsiyasi chaqiradi."""
    global _con
    _con = _con or con
    if c.role.key not in STAFF_EDIT: _deny(c, "xodim buyrug'i loyihasi", "Xodimlar buyrug'ini Kadrlar bo'limi tayyorlaydi")
    p = _staff_params(staff_id, date_from, days, absence_id)
    ts = created_at or _now()
    cur = _con.execute("""INSERT INTO orders(kind,title,status,source,params,count,created_by,created_at,submitted_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                       ("xodim_tatil", f"{p['staff_name']}ga mehnat ta'tili berish to'g'risida"[:300], status, source, json.dumps(p, ensure_ascii=False), 1,
                        c.user["id"], ts, ts if status == "yuborilgan" else None))
    o = db.one(_con, "SELECT * FROM orders WHERE id=?", (cur.lastrowid,))
    _log(o["id"], c, "loyiha yaratildi", f"Mehnat ta'tili (xodim) · {p['staff_name']} · manba: {source}")
    if status == "yuborilgan": _log(o["id"], c, "imzoga yuborildi", "")
    _con.commit()
    _audit(c, "xodim buyrug'i loyihasi", f"#{o['id']} · {p['staff_name']} · {p['date_from']} · {p['days']} kun")
    return o

LEGACY_DOC_KINDS = ("order_student", "reprimand", "leave_order")

def _migrate_if_needed():
    """Server ishlab turganda Hujjatlar markazida (eski kod yo'li orqali) yangi buyruq loyihasi paydo bo'lsa — darhol Buyruqlarga."""
    try:
        if db.one(_con, f"SELECT 1 x FROM documents WHERE status='loyiha' AND kind IN ({','.join('?' * len(LEGACY_DOC_KINDS))}) LIMIT 1", LEGACY_DOC_KINDS):
            with _lock: migrate_legacy_docs(_con)
    except Exception as e:
        print("orders._migrate_if_needed:", e)

def migrate_legacy_docs(con) -> int:
    """Hujjatlar markazida «loyiha» holatida qolgan buyruqlar (order_student, reprimand, leave_order) → Buyruqlar. Idempotent:
    ko'chirilgan hujjat «bekor» bo'ladi (params.moved_to_order), xodimlar ta'tili yozuvi yangi buyruqqa bog'lanadi."""
    global _con
    _con = _con or con
    n = 0
    try:
        docs = db.rows(con, f"SELECT * FROM documents WHERE status='loyiha' AND kind IN ({','.join('?' * len(LEGACY_DOC_KINDS))}) ORDER BY id", LEGACY_DOC_KINDS)
    except Exception:
        return 0
    for d in docs:
        src = f"Hujjatlar markazi: {d['reg_no']}"
        if db.one(con, "SELECT 1 x FROM orders WHERE source=?", (src,)): continue
        u = db.one(con, "SELECT * FROM users WHERE id=?", (d["created_by"],))
        if not u: continue
        c = Ctx(u, rbac.ROLES[u["role"]])
        p = _j(d.get("params"))
        try:
            if d["kind"] == "leave_order":
                if c.role.key not in STAFF_EDIT: continue
                o = draft_staff_leave(con, c, p.get("staff"), p.get("start") or _today().isoformat(), p.get("days"), source=src, status="yuborilgan",
                                      created_at=d["created_at"])
                con.execute("UPDATE staff_absences SET order_id=? WHERE order_doc_id=?", (o["id"], d["id"]))
            else:
                sid = int(str(p.get("target") or "").split(":")[-1] or 0)
                kind = "hayfsan" if d["kind"] == "reprimand" else p.get("action")
                if kind not in KINDS or not sid: continue
                data = {"reason": p.get("reason")} if p.get("reason") else {}
                if p.get("from_date"): data["date_from"] = p["from_date"]
                o = create_order(c, kind, [{"student_id": sid, "data": data}], src, note=f"Hujjatlar markazidan ko'chirildi ({d['reg_no']})")
                ch = checks(db.one(con, "SELECT * FROM orders WHERE id=?", (o["id"],)))
                if ch["errors"]:
                    con.execute("UPDATE orders SET returned_note=? WHERE id=?", ("Hujjatlar markazidan ko'chirildi — majburiy maydonlarni to'ldirib, imzoga qayta yuboring", o["id"]))
                else:
                    con.execute("UPDATE orders SET status='yuborilgan', submitted_at=? WHERE id=?", (d["created_at"], o["id"]))
                    _log(o["id"], c, "imzoga yuborildi", "Hujjatlar markazidan ko'chirildi")
            p["moved_to_order"] = o["id"]
            con.execute("UPDATE documents SET status='bekor', params=? WHERE id=?", (json.dumps(p, ensure_ascii=False), d["id"]))
            con.commit(); n += 1
        except (HTTPException, AccessDenied, ValueError) as e:
            con.rollback(); print("orders.migrate_legacy_docs:", d["reg_no"], e)
    if n: print(f"Buyruqlar: Hujjatlar markazidan {n} ta buyruq loyihasi ko'chirildi")
    return n

def list_xlsx(o: dict, version: int) -> bytes:
    its = items(o["id"], version)
    params = _j(o.get("params"))
    cols = _cols(o["kind"])
    try:
        from openpyxl import Workbook
        wb = Workbook(write_only=True); ws = wb.create_sheet("Ro'yxat")
        ws.append([f"{o.get('reg_no') or 'LOYIHA'} · {o.get('title') or KINDS[o['kind']]['title']} · {version}-versiya"])
        ws.append(["№"] + [h for h, _ in cols] + ["Holat"])
        for k, i in enumerate(its, 1):
            ws.append([k] + [str(f(i, {**params, **i['data']}) or "") for _, f in cols] + ["" if i["student_id"] else "bazada topilmadi"])
        bio = io.BytesIO(); wb.save(bio); return bio.getvalue()
    except ImportError:
        import csv
        s = io.StringIO(); w = csv.writer(s, delimiter=";")
        w.writerow(["№"] + [h for h, _ in cols])
        for k, i in enumerate(its, 1): w.writerow([k] + [str(f(i, {**params, **i['data']}) or "") for _, f in cols])
        return ("﻿" + s.getvalue()).encode("utf-8")

# ---------------------------------------------------------------------------------------------
# Muvofiqlik auditi («Muammoli talabalar»)
# ---------------------------------------------------------------------------------------------
ISSUES = {
    "no_admission": ("Qabul buyrug'ida yo'q", "Talaba bazada bor, lekin hech bir imzolangan qabul (yoki qayta tiklash) buyrug'ida yo'q"),
    "no_transfer": ("Kursga o'tkazish buyrug'ida yo'q", "Kursiga ko'ra kutilgan kursga o'tkazish buyruqlaridan kamida birida yo'q"),
    "contradiction": ("Ziddiyatli buyruqlar", "Talaba bir-biriga zid buyruqlarda uchraydi"),
    "group_mismatch": ("Guruh mos emas", "Oxirgi buyruqdagi guruh bazadagi joriy guruhdan farq qiladi"),
    "expelled_active": ("Chetlashtirilgan, lekin faol", "Buyruq bilan chetlashtirilgan, lekin bazada hali faol"),
    "leave_no_order": ("Buyruqsiz akademik ta'til", "Bazada akademik ta'tilda, lekin amaldagi akademik ta'til buyrug'i yo'q"),
}
ACTIONS = {
    "guruhga_biriktirish": dict(label="Guruhga biriktirish", needs_doc=True, roles=FIX, hint="Talaba buyruqdagi guruhga biriktiriladi (bazadagi guruh o'zgaradi)"),
    "holatni_tuzatish": dict(label="Holatni «chetlashtirilgan» qilish", needs_doc=True, roles=FIX, hint="Bazadagi holat imzolangan buyruqqa moslanadi"),
    "loyiha": dict(label="Tuzatuvchi buyruq loyihasi", needs_doc=False, roles=EDIT, hint="Buyruq loyihasi tuziladi — imzolangach muammo yopiladi"),
    "izoh": dict(label="Hujjat bilan izohlash", needs_doc=True, roles=FIX, hint="Asos hujjat ilova qilinadi, holat «hal qilingan» deb belgilanadi"),
}
SUGGEST = {"no_admission": [("loyiha", "qabul"), ("izoh", None)], "no_transfer": [("loyiha", "kurs"), ("izoh", None)],
           "contradiction": [("loyiha", "tiklash"), ("izoh", None)], "group_mismatch": [("guruhga_biriktirish", None), ("loyiha", "guruh"), ("izoh", None)],
           "expelled_active": [("holatni_tuzatish", None), ("izoh", None)], "leave_no_order": [("loyiha", "akademik_tatil"), ("izoh", None)]}

def analyze(c: Ctx) -> dict:
    eff = db.rows(_con, f"""SELECT i.student_id sid, i.group_id gid, i.data, o.id oid, o.kind, o.order_date d, o.reg_no
        FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
        WHERE o.status='imzolangan' AND o.kind!='bekor' AND i.student_id IS NOT NULL ORDER BY o.order_date, o.id""")
    ev = {}
    for r in eff: ev.setdefault(r["sid"], []).append(r)
    studs = db.rows(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.status, s.study_form, s.group_id, g.name grp, g.course
                             FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE {st_scope(c)}""")
    gname = {g["id"]: g["name"] for g in db.rows(_con, "SELECT id, name FROM groups_")}
    fixed = {r["key"] for r in db.rows(_con, "SELECT key FROM order_issue_fixes WHERE action='izoh'")}
    out = []
    def ref(e): return {"id": e["oid"], "reg_no": e["reg_no"], "kind": e["kind"], "kind_name": KINDS[e["kind"]]["short"], "date": e["d"]}
    def add(kind, s, detail, refs=(), extra=None):
        key = f"{kind}:{s['id']}"
        if key in fixed: return
        out.append({"key": key, "kind": kind, "title": ISSUES[kind][0], "detail": detail, "student": {k: s[k] for k in ("id", "full_name", "hemis_id", "status", "study_form", "grp", "course")},
                    "orders": [ref(e) for e in refs], **(extra or {}),
                    "actions": [{"action": a, "label": ACTIONS[a]["label"] + (f": {KINDS[k]['short']}" if k else ""), "kind": k, "needs_doc": ACTIONS[a]["needs_doc"],
                                 "allowed": c.role.key in ACTIONS[a]["roles"], "hint": ACTIONS[a]["hint"]} for a, k in SUGGEST[kind]]})
    for s in studs:
        es = ev.get(s["id"], [])
        active = s["status"] in ACTIVE
        if active and not any(e["kind"] in ADMIT_KINDS for e in es):
            add("no_admission", s, "Hech bir imzolangan qabul buyrug'ida topilmadi", es[-1:])
        qab = [e for e in es if e["kind"] == "qabul"]
        if len({e["oid"] for e in qab}) > 1:
            add("contradiction", s, f"{len(qab)} ta qabul buyrug'ida: " + ", ".join(f"{e['reg_no']} ({gname.get(e['gid'], '?')})" for e in qab), qab)
            continue
        # chiqish (chetlashtirish/ko'chirish)dan keyin tiklashsiz boshqa buyruq
        exited, bad = None, None
        for e in es:
            if e["kind"] in EXIT_KINDS: exited = e
            elif e["kind"] == "tiklash": exited = None
            elif exited and e["kind"] in ("kurs", "guruh", "akademik_tatil", "tatildan_qaytish", "qabul"): bad = (exited, e); break
        if bad:
            add("contradiction", s, f"{bad[0]['reg_no']} bilan chetlashtirilgan, lekin keyin {bad[1]['reg_no']} ({KINDS[bad[1]['kind']]['short']}) buyrug'ida qayta tiklashsiz uchraydi", bad)
            continue
        if active and es and es[-1]["kind"] in EXIT_KINDS:
            add("expelled_active", s, f"{es[-1]['reg_no']} ({_dmy(es[-1]['d'])}) bilan chetlashtirilgan, bazadagi holat: «{s['status']}»", es[-1:])
            continue
        if active and (s["course"] or 1) >= 2 and not any(e["kind"] in ("akademik_tatil", "tiklash", "kochirib_qabul", "kursda_qoldirish") for e in es):
            n = len({e["oid"] for e in es if e["kind"] == "kurs"})
            if n < (s["course"] - 1):
                add("no_transfer", s, f"{s['course']}-kurs talabasi: kutilgan {s['course'] - 1} ta kursga o'tkazish buyrug'idan {n} tasida bor",
                    [e for e in es if e["kind"] in ("qabul", "kurs")][-2:])
        if active:
            last = None
            for e in es:
                d = _j(e["data"])
                if e["kind"] in ("qabul", "kurs"): last = (e, e["gid"])
                elif e["kind"] in GROUP_KINDS and d.get("group_to_id"): last = (e, int(d["group_to_id"]))
            if last and last[1] and last[1] != s["group_id"]:
                add("group_mismatch", s, f"{last[0]['reg_no']} buyrug'ida guruh {gname.get(last[1], '?')}, bazada — {s['grp']}", [last[0]],
                    {"order_group": {"id": last[1], "name": gname.get(last[1])}})
        if s["status"] == "akademik ta'til":
            on = False
            for e in es:
                if e["kind"] == "akademik_tatil": on = True
                elif e["kind"] in ("tatildan_qaytish", "tiklash") + EXIT_KINDS: on = False
            if not on: add("leave_no_order", s, "Bazada «akademik ta'til» holatida, lekin amaldagi akademik ta'til buyrug'i topilmadi", es[-1:])
    order = list(ISSUES)
    out.sort(key=lambda x: (order.index(x["kind"]), x["student"]["full_name"]))
    summary = [{"kind": k, "title": v[0], "desc": v[1], "count": sum(1 for x in out if x["kind"] == k)} for k, v in ISSUES.items()]
    return {"items": out, "summary": summary, "students": len(studs), "orders": len({e["oid"] for e in eff}),
            "resolved": db.one(_con, "SELECT COUNT(*) n FROM order_issue_fixes")["n"]}

# ---------------------------------------------------------------------------------------------
# Yaratish
# ---------------------------------------------------------------------------------------------
def create_order(c: Ctx, kind: str, students: list[dict], source="qo'lda", title=None, basis=None, note=None, params=None,
                 cancels_id=None, filename=None, file=None) -> dict:
    if kind not in KINDS: _bad("Noma'lum buyruq turi")
    params = _norm_data(kind, params or {}) if kind != "bekor" else {k: str(v)[:300] for k, v in (params or {}).items() if k == "reason"}
    st = _students([x.get("student_id") for x in students])
    if len(st) != len({int(x["student_id"]) for x in students if x.get("student_id")}): _bad("Ro'yxatdagi talabalardan biri topilmadi")
    _check_scope_students(c, list(st.values()), "buyruq loyihasi")
    its, seen = [], set()
    for x in students:
        s = st.get(int(x["student_id"]))
        if not s or s["id"] in seen: continue
        seen.add(s["id"])
        its.append(_item_of(s, _norm_data(kind, x.get("data") or {}) if kind != "bekor" else {}))
    cur = _con.execute("""INSERT INTO orders(kind,title,status,study_form,source,basis,note,params,created_by,created_at,cancels_id)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       (kind, (title or KINDS[kind]["title"])[:300], "loyiha", "sirtqi" if is_sirtqi(c) else None, source, (basis or "")[:500] or None,
                        (note or "")[:1000] or None, json.dumps(params, ensure_ascii=False), c.user["id"], _now(), cancels_id))
    o = db.one(_con, "SELECT * FROM orders WHERE id=?", (cur.lastrowid,))
    _log(o["id"], c, "loyiha yaratildi", f"{KINDS[kind]['short']} · manba: {source}")
    if its or filename:
        new_version(o, its, c, source, filename, file)
    _con.commit()
    _audit(c, "buyruq loyihasi yaratildi", f"#{o['id']} · {KINDS[kind]['short']} · {len(its)} ta talaba")
    return o

def _save_upload(raw: bytes, filename: str) -> str:
    UPL.mkdir(parents=True, exist_ok=True)
    ext = Path(filename or "").suffix.lower()[:6]
    name = f"{clock.now():%Y%m%d%H%M%S}-{secrets.token_hex(4)}{ext}"
    (UPL / name).write_bytes(raw)
    return name

def _attach(oid, c: Ctx | None, kind, filename, stored, size, student_id=None, note=None, by_name=None, ts=None):
    cur = _con.execute("""INSERT INTO order_files(order_id,kind,filename,stored,size,uploaded_by,uploaded_name,uploaded_at,student_id,note)
                          VALUES(?,?,?,?,?,?,?,?,?,?)""", (oid, kind, filename, stored, size, c.user["id"] if c else None,
                                                          by_name or (c.user["full_name"] if c else "Tizim"), ts or _now(), student_id, note))
    return cur.lastrowid

# ---------------------------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------------------------
def _caps(c: Ctx) -> dict:
    k = c.role.key
    return {"edit": k in EDIT, "edit_staff": k in STAFF_EDIT, "fix": k in FIX, "forward": k in FORWARD, "sign": k in SIGN, "sirtqi": k == "sirtqi",
            "register": k in CHANCERY, "outgoing": k in CHANCERY + SIGN, "students": k in READ}

def pending(c: Ctx) -> dict:
    """Mening harakatimni kutayotgan buyruqlar (badge, «Mening vazifalarim», bildirishnomalar — bitta qoida)."""
    k, sc = c.role.key, ord_scope(c)
    _migrate_if_needed()
    out = {"sign": [], "forward": [], "returned": [], "register": []}
    cols = "o.id, o.kind, o.title, o.reg_no, o.status, o.count, o.created_at, o.submitted_at, o.forwarded_at, o.signed_at, o.returned_note, o.params"
    if k in SIGN:
        out["sign"] = db.rows(_con, f"SELECT {cols} FROM orders o WHERE {sc} AND o.status IN ('yuborilgan','kelishilgan') ORDER BY COALESCE(o.forwarded_at, o.submitted_at), o.id")
    if k in FORWARD:   # xodimlar buyrug'i prorektor kelishuvisiz rektorga boradi
        out["forward"] = db.rows(_con, f"SELECT {cols} FROM orders o WHERE {sc} AND o.status='yuborilgan' ORDER BY o.submitted_at, o.id")
    if k in EDIT + STAFF_EDIT:   # qaytarilgan loyihalar: bo'lim rahbari — barchasi, xodim — o'zi tuzganlari
        mine = "" if k in ("talabalar", "sirtqi", "kadrlar") else f" AND o.created_by={int(c.user['id'])}"
        out["returned"] = db.rows(_con, f"SELECT {cols} FROM orders o WHERE {sc} AND o.status='loyiha' AND o.returned_note IS NOT NULL{mine} ORDER BY o.id")
    if k in CHANCERY:
        out["register"] = db.rows(_con, f"SELECT {cols} FROM orders o WHERE {sc} AND o.status='imzolangan' AND COALESCE(o.historic,0)=0 AND o.journal_at IS NULL ORDER BY o.signed_at, o.id")
    for v in out.values():
        for r in v: r["kind_name"] = KINDS.get(r["kind"], {}).get("short", r["kind"]); r["params"] = _j(r.get("params"))
    return out

@router.get("/api/orders/meta")
def meta(request: Request):
    c = C(request, "read", "meta")
    sc = ord_scope(c)
    cnt = {r["status"]: r["n"] for r in db.rows(_con, f"SELECT status, COUNT(*) n FROM orders o WHERE {sc} GROUP BY status")}
    pd = pending(c)
    act = len(pd["sign"]) + len(pd["forward"]) + len(pd["returned"]) + len(pd["register"])
    vis = [k for k in KINDS if (is_staff_kind(k) and c.role.key in STAFF_EDIT + SIGN + CHANCERY) or (not is_staff_kind(k) and c.role.key not in STAFF_EDIT)]
    return {"kinds": [{"key": k, "title": KINDS[k]["title"], "short": KINDS[k]["short"], "fields": KINDS[k]["fields"], "req": KINDS[k]["req"], "effect": KINDS[k]["effect"],
                       "staff": bool(KINDS[k].get("staff"))} for k in vis],
            "field_labels": FIELD_LABELS, "statuses": STATUS, "caps": _caps(c), "counts": cnt, "ocr": IN.ocr_available(),
            "pending": {"sign": len(pd["sign"]), "forward": len(pd["forward"]), "returned": len(pd["returned"]), "register": len(pd["register"]),
                        "drafts": cnt.get("loyiha", 0), "action": act},
            "samples": samples_list(c) if c.role.key in EDIT else []}

def samples_list(c: Ctx) -> list[dict]:
    try:
        idx = _j((SAMPLES / "index.json").read_text(encoding="utf-8"), [])
    except OSError:
        return []
    return [x for x in idx if not is_sirtqi(c) or x.get("sirtqi")]

@router.get("/api/orders")
def list_orders(request: Request, status: str = "", kind: str = "", q: str = "", form: str = "", hist: int = -1, offset: int = 0, limit: int = 50):
    c = C(request, "read", "reyestr")
    w, a = [ord_scope(c)], []
    if status == "jarayonda": w.append("o.status IN ('loyiha','yuborilgan','kelishilgan')")
    elif status == "imzo": w.append("o.status IN ('yuborilgan','kelishilgan')" if c.role.key not in FORWARD else "o.status='yuborilgan'")
    elif status == "jurnal": w.append("o.status='imzolangan' AND COALESCE(o.historic,0)=0 AND o.journal_at IS NULL")
    elif status == "qaytarilgan": w.append("o.status='loyiha' AND o.returned_note IS NOT NULL")
    elif status in STATUS: w.append("o.status=?"); a.append(status)
    else: w.append("o.status!='bekor'")
    if kind in KINDS: w.append("o.kind=?"); a.append(kind)
    if form in ("kunduzgi", "sirtqi", "masofaviy", "aralash"): w.append("o.study_form=?"); a.append(form)
    if hist in (0, 1): w.append("o.historic=?"); a.append(hist)
    q = (q or "").strip()
    if q:
        like = f"%{q}%"
        w.append("""(o.reg_no LIKE ? OR o.title LIKE ? OR o.id IN (SELECT i.order_id FROM order_students i JOIN orders o2 ON o2.id=i.order_id AND i.version=o2.version
                     WHERE i.full_name LIKE ? OR i.hemis_id=? OR i.group_name=?))""")
        a += [like, like, like, q, q.upper()]
    where = " AND ".join(w)
    total = db.one(_con, f"SELECT COUNT(*) n FROM orders o WHERE {where}", a)["n"]
    rows = db.rows(_con, f"""SELECT o.id, o.kind, o.title, o.status, o.reg_no, o.order_date, o.study_form, o.source, o.count, o.version, o.historic,
                              o.created_at, o.submitted_at, o.forwarded_at, o.signed_at, o.cancels_id, o.cancelled_by, o.returned_note, o.journal_at, u.full_name creator
                              FROM orders o LEFT JOIN users u ON u.id=o.created_by WHERE {where}
                              ORDER BY CASE o.status WHEN 'yuborilgan' THEN 0 WHEN 'kelishilgan' THEN 0 WHEN 'loyiha' THEN 1 ELSE 2 END,
                                       COALESCE(o.order_date, substr(o.created_at,1,10)) DESC, o.id DESC LIMIT ? OFFSET ?""", a + [min(max(limit, 1), 200), max(offset, 0)])
    for r in rows:
        r["kind_name"] = KINDS.get(r["kind"], {}).get("short", r["kind"]); r["status_name"] = STATUS.get(r["status"], r["status"]); r["creator"] = _short(r["creator"])
    if offset == 0: _audit(c, "reyestr", f"{total} ta · {status or 'hammasi'} {kind} {q}"[:200])
    return {"items": rows, "total": total}

@router.get("/api/orders/{oid}")
def detail(oid: int, request: Request, q: str = "", offset: int = 0, limit: int = 100):
    c = C(request, "read", "buyruqni ochish", f"#{oid}")
    o = _order(c, oid)
    its = items(oid)
    ch = checks(o, its) if o["status"] in ("loyiha", "yuborilgan", "kelishilgan") else {"errors": [], "warnings": []}
    st = _students([i["student_id"] for i in its if i["student_id"]]) if len(its) <= 3000 else {}
    qq = IN.norm(q)
    view = [i for i in its if not qq or qq in IN.norm(f"{i['full_name']} {i['hemis_id']} {i['group_name']}")]
    params = _j(o.get("params"))
    page = []
    for i in view[max(offset, 0):max(offset, 0) + min(max(limit, 1), 500)]:
        s = st.get(i["student_id"])
        page.append({"id": i["id"], "student_id": i["student_id"], "hemis_id": i["hemis_id"], "full_name": i["full_name"], "group_name": i["group_name"],
                     "course": i["course"], "data": i["data"], "eff": {**params, **i["data"]}, "raw": i["raw"], "applied": i["applied"],
                     "prev": _j(i.get("prev")) if i.get("prev") else None,
                     "now": {"full_name": s["full_name"], "status": s["status"], "grp": s["grp"]} if s else None})
    vers = db.rows(_con, "SELECT * FROM order_versions WHERE order_id=? ORDER BY no DESC", (oid,))
    files = db.rows(_con, "SELECT id, kind, filename, size, uploaded_name, uploaded_at, student_id, note FROM order_files WHERE order_id=? ORDER BY id DESC", (oid,))
    log = db.rows(_con, "SELECT ts, user_name, action, detail FROM order_log WHERE order_id=? ORDER BY id DESC LIMIT 200", (oid,))
    for x in log: x["user_name"] = _short(x["user_name"]) or x["user_name"]
    for x in vers: x["created_by_name"] = _short(x["created_by_name"]) or x["created_by_name"]
    for x in files: x["uploaded_name"] = _short(x["uploaded_name"]) or x["uploaded_name"]
    rel = {}
    if o.get("cancels_id"): rel["cancels"] = db.one(_con, "SELECT id, reg_no, title, status FROM orders WHERE id=?", (o["cancels_id"],))
    if o.get("cancelled_by"): rel["cancelled_by"] = db.one(_con, "SELECT id, reg_no, title, status FROM orders WHERE id=?", (o["cancelled_by"],))
    pend = db.one(_con, "SELECT id, status FROM orders WHERE cancels_id=? AND status IN ('loyiha','yuborilgan','kelishilgan')", (oid,))
    if pend: rel["cancel_pending"] = pend
    u = lambda uid: _short((db.one(_con, "SELECT full_name FROM users WHERE id=?", (uid,)) or {}).get("full_name")) if uid else None
    caps = _caps(c)
    k = c.role.key; s_ = o["status"]; ed = can_edit_order(c, o); stf = is_staff_kind(o["kind"])
    can = {"edit": ed and s_ == "loyiha", "submit": ed and s_ == "loyiha", "delete": ed and s_ == "loyiha",
           "forward": caps["forward"] and s_ == "yuborilgan", "sign": caps["sign"] and s_ in ("yuborilgan", "kelishilgan"),
           "return": (k in FORWARD and s_ == "yuborilgan") or (k in SIGN and s_ in ("yuborilgan", "kelishilgan")),
           "annul": caps["edit"] and not stf and s_ == "imzolangan" and o["kind"] != "bekor" and not pend,
           "register": caps["register"] and s_ == "imzolangan" and not o.get("historic") and not o.get("journal_at"),
           "students": caps["students"] and not stf}
    if o.get("journal_at"): rel["journal"] = {"at": o["journal_at"], "by": u(o.get("journal_by")), "note": o.get("journal_note")}
    rel["outgoing"] = db.rows(_con, "SELECT id, out_no, out_date, addressee, subject FROM outgoing_mail WHERE order_id=? ORDER BY id", (oid,))
    _audit(c, "buyruq ochildi", f"{o.get('reg_no') or '#' + str(oid)}")
    return {"order": {**o, "params": params, "kind_name": KINDS[o["kind"]]["short"], "kind_title": KINDS[o["kind"]]["title"], "status_name": STATUS.get(s_, s_),
                      "creator": u(o["created_by"]), "forwarder": u(o.get("forwarded_by")), "signer": u(o.get("signed_by"))},
            "items": page, "total": len(view), "all": len(its), "unmatched": sum(1 for i in its if not i["student_id"]),
            "versions": vers, "files": files, "log": log, "checks": ch, "related": rel, "can": can,
            "fields": KINDS[o["kind"]]["fields"], "req": KINDS[o["kind"]]["req"], "staff": stf}

class NewOrder(BaseModel):
    kind: str
    title: str | None = None
    basis: str | None = None
    note: str | None = None
    params: dict = {}
    students: list[dict] = []

@router.post("/api/orders")
def create(body: NewOrder, request: Request):
    c = C(request, "edit_any", "loyiha yaratish")
    if body.kind == "bekor": _bad("Bekor qiluvchi buyruq imzolangan buyruq sahifasidan tuziladi")
    if is_staff_kind(body.kind) or c.role.key in STAFF_EDIT:
        if not (is_staff_kind(body.kind) and c.role.key in STAFF_EDIT):
            _deny(c, "loyiha yaratish", "Xodimlar buyrug'ini Kadrlar bo'limi, talabalar buyrug'ini Registrator ofisi tayyorlaydi", body.kind)
        p = body.params or {}
        o = draft_staff_leave(_con, c, p.get("staff_id"), p.get("date_from"), p.get("days"), source="qo'lda")
        return {"ok": True, "id": o["id"]}
    o = create_order(c, body.kind, body.students[:20000], "qo'lda", body.title, body.basis, body.note, body.params)
    return {"ok": True, "id": o["id"]}

class EditOrder(BaseModel):
    title: str | None = None
    basis: str | None = None
    note: str | None = None
    params: dict | None = None

@router.post("/api/orders/{oid}/edit")
def edit(oid: int, body: EditOrder, request: Request):
    c = C(request, "edit_any", "loyihani tahrirlash", f"#{oid}")
    o = _order(c, oid); _editable(c, o)
    if not can_edit_order(c, o): _deny(c, "loyihani tahrirlash", DENY_MSG["edit_any"], f"#{oid}")
    upd = {}
    if body.title is not None: upd["title"] = body.title.strip()[:300] or KINDS[o["kind"]]["title"]
    if body.basis is not None: upd["basis"] = body.basis.strip()[:500] or None
    if body.note is not None: upd["note"] = body.note.strip()[:1000] or None
    if body.params is not None and is_staff_kind(o["kind"]):
        cur = _j(o.get("params"))
        upd["params"] = json.dumps(_staff_params(cur.get("staff_id"), body.params.get("date_from") or cur.get("date_from"),
                                                 body.params.get("days") or cur.get("days"), cur.get("absence_id")), ensure_ascii=False)
    elif body.params is not None and o["kind"] != "bekor": upd["params"] = json.dumps(_norm_data(o["kind"], body.params), ensure_ascii=False)
    if upd:
        _con.execute(f"UPDATE orders SET {', '.join(f'{k}=?' for k in upd)} WHERE id=?", (*upd.values(), oid))
        _log(oid, c, "loyiha tahrirlandi", ", ".join(upd)); _con.commit()
        _audit(c, "loyiha tahrirlandi", f"#{oid}: {', '.join(upd)}")
    return {"ok": True}

class ItemsBody(BaseModel):
    add: list[dict] = []
    remove: list[int] = []          # order_students.id (joriy versiya qatorlari)
    update: list[dict] = []         # {id, data}
    note: str | None = None

@router.post("/api/orders/{oid}/items")
def change_items(oid: int, body: ItemsBody, request: Request):
    c = C(request, "edit", "ro'yxatni o'zgartirish", f"#{oid}")
    with _lock:
        o = _order(c, oid); _editable(c, o)
        if o["kind"] == "bekor" and body.add: _bad("Bekor qiluvchi buyruq ro'yxati bekor qilinayotgan buyruqdan olinadi")
        its = items(oid)
        rm = set(body.remove)
        upd = {int(x["id"]): x.get("data") or {} for x in body.update if x.get("id")}
        new = []
        for i in its:
            if i["id"] in rm: continue
            if i["id"] in upd and i["student_id"]:
                i = dict(i, data=_norm_data(o["kind"], {**i["data"], **upd[i["id"]]}))
            new.append(i)
        have = {i["student_id"] for i in new if i["student_id"]}
        st = _students([x.get("student_id") for x in body.add])
        _check_scope_students(c, list(st.values()), "ro'yxatga qo'shish")
        added = 0
        for x in body.add:
            s = st.get(int(x.get("student_id") or 0))
            if not s or s["id"] in have: continue
            have.add(s["id"]); added += 1
            new.append(_item_of(s, _norm_data(o["kind"], x.get("data") or {})))
        if not (rm or upd or added): _bad("O'zgarish yo'q")
        parts = [f"+{added} qo'shildi" if added else "", f"−{len(rm & {i['id'] for i in its})} olib tashlandi" if rm else "", f"{len(upd)} ta tahrirlandi" if upd else ""]
        v = new_version(o, new, c, "qo'lda: " + ", ".join(p for p in parts if p), note=(body.note or "")[:300] or None)
        _con.commit()
    _audit(c, "ro'yxat o'zgartirildi", f"#{oid} → {v['no']}-versiya · +{v['added']} / −{v['removed']}")
    return {"ok": True, "version": v}

@router.post("/api/orders/{oid}/upload")
async def upload_list(oid: int, request: Request, name: str = ""):
    c = C(request, "edit", "ro'yxat yuklash", f"#{oid}")
    raw = await request.body()
    if not raw: _bad("Fayl bo'sh")
    if len(raw) > MAX_UPLOAD: _bad("Fayl hajmi 15 MB dan oshmasin")
    return await run_in_threadpool(_upload_list, c, oid, name or "royxat.xlsx", raw)

def _upload_list(c: Ctx, oid: int, name: str, raw: bytes, by_name=None, ts=None):
    with _lock:
        o = _order(c, oid); _editable(c, o)
        if o["kind"] == "bekor": _bad("Bekor qiluvchi buyruqqa ro'yxat yuklanmaydi")
        try:
            parsed = IN.parse_list(name, raw)
        except ValueError as e:
            _bad(str(e))
        ok_, bad, dup = IN.match_list(_con, parsed["rows"], "1=1")
        if is_sirtqi(c):
            other = [m for m in ok_ if m["student"]["study_form"] != "sirtqi"]
            if other: _deny(c, "ro'yxat yuklash", f"Ro'yxatda {len(other)} ta sirtqi bo'lmagan talaba bor — Sirtqi bo'lim faqat sirtqi talabalar bilan ishlaydi", name)
        old = {i["student_id"]: i["data"] for i in items(oid) if i["student_id"]} if o["version"] else {}
        new = [_item_of(m["student"], old.get(m["student"]["id"], {}), {"line": m["row"]["line"], "hemis": m["row"]["hemis"], "name": m["row"]["name"], "group": m["row"]["group"]}) for m in ok_]
        new += [{"student_id": None, "hemis_id": b.get("hemis"), "full_name": b.get("name") or "—", "group_id": None, "group_name": b.get("group"), "course": None,
                 "data": {}, "raw": {"line": b["line"], "hemis": b.get("hemis"), "name": b.get("name"), "group": b.get("group"), "why": b["why"]}} for b in bad]
        stored = _save_upload(raw, name)
        _attach(oid, c, "ro'yxat", name, stored, len(raw), by_name=by_name, ts=ts)
        v = new_version(o, new, c, "fayl", name, stored, by_name=by_name, ts=ts,
                        note=(f"{dup} ta takror olib tashlandi" if dup else None))
        _con.commit()
    _audit(c, "ro'yxat yuklandi", f"#{oid} · {name} → {v['no']}-versiya · {v['count']} ta (+{v['added']} / −{v['removed']}) · mos emas {len(bad)}")
    return {"ok": True, "version": v, "columns": parsed["columns"], "unmatched": bad[:50], "duplicates": dup, "skipped": parsed["skipped"]}

@router.get("/api/orders/{oid}/versions/{no}/diff")
def version_diff(oid: int, no: int, request: Request, against: int = 0, limit: int = 300):
    c = C(request, "read_st", "versiya farqi", f"#{oid} v{no}")
    _order(c, oid)
    base_no = against or no - 1
    a = {_key(i): i for i in items(oid, base_no)} if base_no >= 1 else {}
    b = {_key(i): i for i in items(oid, no)}
    if not b and not db.one(_con, "SELECT 1 x FROM order_versions WHERE order_id=? AND no=?", (oid, no)): raise HTTPException(404, "Versiya topilmadi")
    pick = lambda i: {"full_name": i["full_name"], "hemis_id": i["hemis_id"], "group_name": i["group_name"], "matched": bool(i["student_id"])}
    added = [pick(b[k]) for k in b if k not in a]; removed = [pick(a[k]) for k in a if k not in b]
    changed = [dict(pick(b[k]), before=a[k]["data"], after=b[k]["data"]) for k in b if k in a and a[k]["data"] != b[k]["data"]]
    return {"no": no, "against": base_no, "added": added[:limit], "removed": removed[:limit], "changed": changed[:limit],
            "n_added": len(added), "n_removed": len(removed), "n_changed": len(changed), "count_a": len(a), "count_b": len(b)}

@router.post("/api/orders/{oid}/versions/{no}/restore")
def version_restore(oid: int, no: int, request: Request):
    c = C(request, "edit", "versiyani tiklash", f"#{oid} v{no}")
    with _lock:
        o = _order(c, oid); _editable(c, o)
        if no == o["version"]: _bad("Bu versiya allaqachon joriy")
        if not db.one(_con, "SELECT 1 x FROM order_versions WHERE order_id=? AND no=?", (oid, no)): raise HTTPException(404, "Versiya topilmadi")
        old = items(oid, no)
        v = new_version(o, old, c, f"{no}-versiyadan tiklandi", restored_from=no)
        _con.commit()
    _audit(c, "ro'yxat versiyasi tiklandi", f"#{oid}: {no}-versiya → {v['no']}-versiya")
    return {"ok": True, "version": v}

def _transition(c: Ctx, o: dict, frm: tuple, to: str, action: str, detail="", **cols):
    if o["status"] not in frm: _bad(f"Holat mos emas: «{STATUS.get(o['status'], o['status'])}»")
    sets = {"status": to, **cols}
    _con.execute(f"UPDATE orders SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), o["id"]))
    _log(o["id"], c, action, detail); _con.commit()
    _audit(c, action, f"{o.get('reg_no') or '#' + str(o['id'])} · {KINDS[o['kind']]['short']}" + (f" · {detail}" if detail else ""))

@router.post("/api/orders/{oid}/submit")
def submit(oid: int, request: Request):
    c = C(request, "edit_any", "imzoga yuborish", f"#{oid}")
    o = _order(c, oid)
    if not can_edit_order(c, o): _deny(c, "imzoga yuborish", DENY_MSG["edit_any"], f"#{oid}")
    if o["status"] == "loyiha":
        ch = checks(o)
        if ch["errors"]: _bad("Yuborib bo'lmaydi: " + "; ".join(ch["errors"]))
    _transition(c, o, ("loyiha",), "yuborilgan", "imzoga yuborildi", f"{o['count']} ta talaba · {o['version']}-versiya", submitted_at=_now(), returned_note=None)
    return {"ok": True}

@router.post("/api/orders/{oid}/forward")
def forward(oid: int, request: Request):
    c = C(request, "forward", "kelishish", f"#{oid}")
    o = _order(c, oid)
    _transition(c, o, ("yuborilgan",), "kelishilgan", "prorektor kelishdi", "", forwarded_by=c.user["id"], forwarded_at=_now())
    return {"ok": True}

class Note(BaseModel):
    note: str = ""

@router.post("/api/orders/{oid}/return")
def return_(oid: int, body: Note, request: Request):
    c = _ctx(request)
    if c.role.key not in FORWARD + SIGN: C(request, "sign", "qaytarish", f"#{oid}")
    o = _order(c, oid)
    if c.role.key in FORWARD and o["status"] != "yuborilgan": _bad("Prorektor faqat kelishilmagan buyruqni qaytaradi")
    note = (body.note or "").strip()[:500]
    if len(note) < 3: _bad("Qaytarish sababini yozing")
    _transition(c, o, ("yuborilgan", "kelishilgan"), "loyiha", "qaytarildi", note, returned_note=note, forwarded_by=None, forwarded_at=None)
    return {"ok": True}

@router.post("/api/orders/{oid}/sign")
def sign_ep(oid: int, request: Request):
    c = C(request, "sign", "imzolash", f"#{oid}")
    o = _order(c, oid)
    from . import service as SV
    return sign(o, c, SV.public_base(request))

@router.post("/api/orders/{oid}/delete")
def delete(oid: int, request: Request):
    c = C(request, "edit_any", "loyihani o'chirish", f"#{oid}")
    o = _order(c, oid)
    if not can_edit_order(c, o): _deny(c, "loyihani o'chirish", DENY_MSG["edit_any"], f"#{oid}")
    _transition(c, o, ("loyiha",), "bekor", "loyiha o'chirildi", "versiyalar va jurnal saqlanadi")
    return {"ok": True}

@router.post("/api/orders/{oid}/annul")
def annul(oid: int, body: Note, request: Request):
    c = C(request, "edit", "bekor qiluvchi buyruq", f"#{oid}")
    o = _order(c, oid)
    if o["status"] != "imzolangan" or o["kind"] == "bekor": _bad("Faqat imzolangan buyruq tuzatuvchi buyruq bilan bekor qilinadi")
    if db.one(_con, "SELECT 1 x FROM orders WHERE cancels_id=? AND status IN ('loyiha','yuborilgan','kelishilgan')", (oid,)): _bad("Bu buyruqni bekor qiluvchi loyiha allaqachon bor")
    reason = (body.note or "").strip()[:300]
    if len(reason) < 3: _bad("Bekor qilish sababini yozing")
    its = [{"student_id": i["student_id"]} for i in items(oid) if i["student_id"]]
    n = create_order(c, "bekor", its, "tuzatuvchi", f"{o['reg_no']}-son buyruqni bekor qilish to'g'risida", note=reason, params={"reason": reason}, cancels_id=oid)
    _log(oid, c, "bekor qiluvchi loyiha tuzildi", f"#{n['id']} · {reason}"); _con.commit()
    return {"ok": True, "id": n["id"]}

@router.get("/api/orders/{oid}/docx")
def docx(oid: int, request: Request):
    c = C(request, "read", "buyruq DOCX", f"#{oid}")
    o = _order(c, oid)
    from . import service as SV
    p = render_docx(o, SV.public_base(request))
    _audit(c, "buyruq yuklab olindi (DOCX)", f"{o.get('reg_no') or '#' + str(oid)} · {o['version']}-versiya")
    nm = f"{(o.get('reg_no') or 'loyiha-' + str(oid)).replace('/', '-')}_v{o['version']}.docx"
    return FileResponse(p, filename=nm, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@router.get("/api/orders/{oid}/xlsx")
def xlsx(oid: int, request: Request, version: int = 0):
    c = C(request, "read_st", "ro'yxat XLSX", f"#{oid}")
    o = _order(c, oid)
    v = version or o["version"]
    data = list_xlsx(o, v)
    _audit(c, "ro'yxat yuklab olindi", f"#{oid} · {v}-versiya")
    nm = f"{(o.get('reg_no') or 'loyiha-' + str(oid)).replace('/', '-')}_royxat_v{v}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nm}"'})

@router.get("/api/orders/files/{fid}")
def file_get(fid: int, request: Request):
    c = C(request, "read_st", "ilova fayl", f"#{fid}")
    f = db.one(_con, "SELECT * FROM order_files WHERE id=?", (fid,))
    if not f: raise HTTPException(404)
    if f["order_id"]: _order(c, f["order_id"])
    elif is_sirtqi(c) and f.get("student_id"):
        s = db.one(_con, "SELECT study_form FROM students WHERE id=?", (f["student_id"],))
        if not s or s["study_form"] != "sirtqi": _deny(c, "ilova fayl", "Sirtqi bo'lim faqat sirtqi talabalar hujjatlarini ko'radi", str(fid))
    p = (UPL / f["stored"]).resolve()
    if p.parent != UPL.resolve() or not p.exists(): raise HTTPException(404)
    _audit(c, "ilova fayl yuklab olindi", f["filename"])
    return FileResponse(p, filename=f["filename"])

@router.post("/api/orders/files")
async def file_upload(request: Request, name: str = "", order_id: int = 0, student_id: int = 0, kind: str = "asos"):
    c = C(request, "fix", "asos hujjat yuklash")
    raw = await request.body()
    if not raw: _bad("Fayl bo'sh")
    if len(raw) > MAX_UPLOAD: _bad("Fayl hajmi 15 MB dan oshmasin")
    ext = Path(name or "").suffix.lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".docx"): _bad("Asos hujjat PDF, DOCX yoki rasm bo'lishi kerak")
    if raw[:4] != b"%PDF" and ext == ".pdf": _bad("Fayl PDF emas")
    if order_id: _order(c, order_id)
    if student_id and is_sirtqi(c):
        s = db.one(_con, "SELECT study_form FROM students WHERE id=?", (student_id,))
        if not s or s["study_form"] != "sirtqi": _deny(c, "asos hujjat yuklash", "Sirtqi bo'lim faqat sirtqi talabalar bilan ishlaydi", str(student_id))
    stored = _save_upload(raw, name)
    fid = _attach(order_id or None, c, kind if kind in ("asos", "ariza", "ro'yxat") else "asos", name[:200] or "hujjat" + ext, stored, len(raw), student_id or None)
    if order_id: _log(order_id, c, "hujjat ilova qilindi", name)
    _con.commit()
    _audit(c, "asos hujjat yuklandi", f"{name} · {len(raw)} bayt")
    return {"ok": True, "id": fid, "filename": name}

# ---------- arizadan buyruq ----------
class IntakeText(BaseModel):
    text: str

def _intake_result(c: Ctx, name, stored, ex: dict) -> dict:
    det = IN.detect(ex["text"]) if ex["text"] else {"kind": None, "kind_name": None, "confidence": 0, "evidence": [], "alternatives": [], "fields": {}, "hint": {}, "dates": []}
    cands = IN.match_students(_con, det["hint"], st_scope(c)) if det.get("hint") else []
    f = det["fields"]
    if det["kind"] == "familiya" and cands and not f.get("old_surname"): f["old_surname"] = cands[0]["full_name"].split()[0]
    if det["kind"] == "guruh" and cands and f.get("group_to") == cands[0]["grp"]: f.pop("group_to", None)   # joriy guruh — yangi guruh emas
    if det["kind"] == "guruh" and cands and not f.get("group_to"):
        others = [g for g in det["hint"].get("groups", []) if g != cands[0]["grp"]]
        if others: f["group_to"] = others[0]
    cur = _con.execute("""INSERT INTO order_applications(created_by,created_at,filename,stored,method,text,kind,fields,student_id,status)
                          VALUES(?,?,?,?,?,?,?,?,?,?)""", (c.user["id"], _now(), name, stored, ex["method"], ex["text"][:20000], det["kind"],
                                                           json.dumps(f, ensure_ascii=False), cands[0]["id"] if cands else None, "tahlil"))
    _con.commit()
    drafts = db.rows(_con, f"""SELECT id, title, count, kind FROM orders o WHERE status='loyiha' AND kind=? AND {ord_scope(c)} ORDER BY id DESC LIMIT 10""", (det["kind"] or "",))
    _audit(c, "ariza tahlil qilindi", f"{name or 'matn'} · {ex['method']} · {det['kind'] or 'aniqlanmadi'} · {len(cands)} nomzod")
    return {"app_id": cur.lastrowid, "filename": name, "method": ex["method"], "note": ex["note"], "text": ex["text"], **det, "fields": f,
            "candidates": cands, "drafts": drafts, "ocr": IN.ocr_available()}

@router.post("/api/orders/intake")
async def intake(request: Request, name: str = ""):
    c = C(request, "edit", "arizani o'qish")
    raw = await request.body()
    if not raw: _bad("Fayl bo'sh")
    if len(raw) > MAX_UPLOAD: _bad("Fayl hajmi 15 MB dan oshmasin")
    def work():
        try: ex = IN.extract(name, raw)
        except ValueError as e: _bad(str(e))
        return _intake_result(c, name, _save_upload(raw, name), ex)
    return await run_in_threadpool(work)

@router.post("/api/orders/intake/text")
def intake_text(body: IntakeText, request: Request):
    c = C(request, "edit", "ariza matni")
    t = IN.clean(body.text or "")[:20000]
    if len(t) < 15: _bad("Ariza matni juda qisqa")
    return _intake_result(c, None, None, {"text": t, "method": "qo'lda", "note": ""})

@router.post("/api/orders/intake/sample/{name}")
async def intake_sample(name: str, request: Request):
    c = C(request, "edit", "namuna ariza")
    sm = {x["file"]: x for x in samples_list(c)}
    if name not in sm or sm[name].get("type") != "ariza": raise HTTPException(404, "Namuna topilmadi")
    raw = (SAMPLES / name).read_bytes()
    def work():
        return _intake_result(c, name, _save_upload(raw, name), IN.extract(name, raw))
    return await run_in_threadpool(work)

@router.get("/api/orders/samples/{name}")
def sample_get(name: str, request: Request):
    c = C(request, "read_st", "namuna fayl", name)
    if name not in {x["file"] for x in samples_list(c)}: raise HTTPException(404)
    return FileResponse(SAMPLES / name, filename=name)

class FromApp(BaseModel):
    kind: str
    student_id: int
    fields: dict = {}
    order_id: int = 0

@router.post("/api/orders/intake/{app_id}/order")
def intake_order(app_id: int, body: FromApp, request: Request):
    c = C(request, "edit", "arizadan loyiha", f"ariza #{app_id}")
    ap = db.one(_con, "SELECT * FROM order_applications WHERE id=?", (app_id,))
    if not ap or (ap["created_by"] != c.user["id"] and c.role.key not in ("talabalar", "registrator_xodim")): raise HTTPException(404, "Ariza topilmadi")
    if body.kind not in KINDS or body.kind in ("bekor", "qabul", "kurs"): _bad("Ariza turi noto'g'ri")
    st = _students([body.student_id]).get(body.student_id)
    if not st: _bad("Talaba topilmadi")
    _check_scope_students(c, [st], "arizadan loyiha")
    with _lock:
        if body.order_id:
            o = _order(c, body.order_id); _editable(c, o)
            if o["kind"] != body.kind: _bad("Tanlangan loyiha boshqa turdagi buyruq")
            its = items(o["id"])
            if any(i["student_id"] == st["id"] for i in its): _bad("Bu talaba loyihada allaqachon bor")
            new_version(o, its + [_item_of(st, _norm_data(body.kind, body.fields))], c, f"ariza: {ap['filename'] or 'matn'}")
        else:
            o = create_order(c, body.kind, [{"student_id": st["id"], "data": body.fields}], "ariza")
        if ap.get("stored"): _attach(o["id"], c, "ariza", ap["filename"], ap["stored"], (UPL / ap["stored"]).stat().st_size if (UPL / ap["stored"]).exists() else 0, st["id"])
        _con.execute("UPDATE order_applications SET order_id=?, student_id=?, kind=?, fields=?, status='loyihada' WHERE id=?",
                     (o["id"], st["id"], body.kind, json.dumps(body.fields, ensure_ascii=False), app_id))
        _log(o["id"], c, "ariza qo'shildi", f"{st['full_name']} · {ap['filename'] or 'matn'} ({ap['method']})")
        _con.commit()
    _audit(c, "arizadan buyruq loyihasi", f"#{o['id']} · {KINDS[body.kind]['short']} · {st['full_name']}")
    return {"ok": True, "id": o["id"]}

# ---------- qidiruv ----------
@router.get("/api/orders/lookup/students")
def lookup_students(request: Request, q: str = "", limit: int = 15):
    c = C(request, "edit", "talaba qidiruvi")
    q = (q or "").strip()
    if len(q) < 2: return []
    like = f"%{q}%"
    return db.rows(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.status, s.study_form, g.name grp, g.course FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
                            WHERE {st_scope(c)} AND (s.full_name LIKE ? OR s.hemis_id LIKE ? OR g.name LIKE ?) ORDER BY s.full_name LIMIT ?""",
                   (like, like, q.upper(), min(max(limit, 1), 50)))

@router.get("/api/orders/lookup/groups")
def lookup_groups(request: Request, q: str = ""):
    c = C(request, "read_st", "guruh qidiruvi")
    like = f"%{(q or '').strip().upper()}%"
    w = "g.form='sirtqi'" if is_sirtqi(c) else "1=1"
    return db.rows(_con, f"SELECT g.id, g.name, g.course, g.form, g.level FROM groups_ g WHERE {w} AND upper(g.name) LIKE ? ORDER BY g.name LIMIT 30", (like,))

# ---------- muvofiqlik auditi ----------
@router.get("/api/orders/audit/issues")
def audit_issues(request: Request, kind: str = "", q: str = ""):
    c = C(request, "read_st", "muvofiqlik auditi")
    r = analyze(c)
    its = r["items"]
    if kind in ISSUES: its = [x for x in its if x["kind"] == kind]
    qq = IN.norm(q)
    if qq: its = [x for x in its if qq in IN.norm(f"{x['student']['full_name']} {x['student']['hemis_id']} {x['student']['grp']}")]
    _audit(c, "muvofiqlik auditi", f"{len(r['items'])} ta muammo")
    return {**r, "items": its[:500], "total": len(its), "caps": _caps(c)}

class Fix(BaseModel):
    key: str
    action: str
    file_id: int = 0
    ref_order_id: int = 0
    note: str = ""

@router.post("/api/orders/audit/fix")
def audit_fix(body: Fix, request: Request):
    c = C(request, "fix", "muvofiqlik tuzatishi", body.key)
    if body.action not in ACTIONS: _bad("Noma'lum amal")
    if c.role.key not in ACTIONS[body.action]["roles"]: _deny(c, "muvofiqlik tuzatishi", f"«{ACTIONS[body.action]['label']}» — Registrator ofisi yoki Sirtqi bo'lim vakolati", body.key)
    issue = next((x for x in analyze(c)["items"] if x["key"] == body.key), None)
    if not issue: _bad("Muammo topilmadi yoki allaqachon hal qilingan")
    allowed = {a["action"] for a in issue["actions"]}
    if body.action not in allowed: _bad("Bu muammo uchun amal mos emas")
    sid = issue["student"]["id"]
    if ACTIONS[body.action]["needs_doc"]:
        ok_doc = False
        if body.file_id:
            f = db.one(_con, "SELECT * FROM order_files WHERE id=?", (body.file_id,))
            ok_doc = bool(f and (f["student_id"] in (None, sid)))
        if body.ref_order_id:
            ok_doc = ok_doc or bool(db.one(_con, """SELECT 1 x FROM order_students i JOIN orders o ON o.id=i.order_id AND i.version=o.version
                                                   WHERE o.id=? AND o.status='imzolangan' AND i.student_id=?""", (body.ref_order_id, sid)))
        if not ok_doc: _bad("Avval asos hujjatni tanlang: buyruq PDF/skanini yuklang yoki reyestrdagi imzolangan buyruqni tanlang")
    if body.action == "izoh" and len(body.note.strip()) < 5: _bad("Izoh yozing (kamida 5 belgi)")
    ref = db.one(_con, "SELECT id, reg_no FROM orders WHERE id=?", (body.ref_order_id,)) if body.ref_order_id else None
    new_id = None
    with _lock:
        s = db.one(_con, "SELECT id, group_id, faculty_id, status, study_form FROM students WHERE id=?", (sid,))
        if body.action == "guruhga_biriktirish":
            g = _group((issue.get("order_group") or {}).get("id"))
            if not g: _bad("Buyruqdagi guruh topilmadi")
            upd = {"group_id": g["id"]}
            if g["faculty_id"] != s["faculty_id"]: upd["faculty_id"] = g["faculty_id"]
            _con.execute(f"UPDATE students SET {', '.join(f'{k}=?' for k in upd)} WHERE id=?", (*upd.values(), sid))
            for k, v in upd.items(): _change(sid, k, s[k], v, ref or {"id": None}, c, "Muammoli talabalar: guruhga biriktirish" + (f" ({ref['reg_no']} asosida)" if ref else " (yuklangan hujjat asosida)"))
        elif body.action == "holatni_tuzatish":
            _con.execute("UPDATE students SET status=? WHERE id=?", (EXPELLED, sid))
            _change(sid, "status", s["status"], EXPELLED, ref or {"id": None}, c, "Muammoli talabalar: holat buyruqqa moslandi")
        elif body.action == "loyiha":
            kind = next(a["kind"] for a in issue["actions"] if a["action"] == "loyiha")
            data = {}
            if kind == "guruh": data = {"group_to_id": s["group_id"], "group_to": issue["student"]["grp"], "reason": "bazadagi guruhni buyruq bilan rasmiylashtirish"}
            if kind == "tiklash": data = {"group_to_id": s["group_id"], "group_to": issue["student"]["grp"], "date_from": _today().isoformat()}
            if kind == "akademik_tatil":
                lv = db.one(_con, "SELECT start, end FROM student_leaves WHERE student_id=? ORDER BY start DESC LIMIT 1", (sid,))
                if lv: data = {"date_from": lv["start"], "date_to": lv["end"]}
            title = {"qabul": "Qabul buyrug'iga qo'shimcha (tuzatish) to'g'risida", "kurs": "Kursga o'tkazish buyrug'iga qo'shimcha (tuzatish) to'g'risida"}.get(kind)
            o = create_order(c, kind, [{"student_id": sid, "data": data}], "muvofiqlik auditi", title, note=f"Muammoli talabalar: {issue['title']} — {issue['detail']}")
            new_id = o["id"]
            if body.file_id: _con.execute("UPDATE order_files SET order_id=? WHERE id=? AND order_id IS NULL", (new_id, body.file_id))
        _con.execute("""INSERT INTO order_issue_fixes(key,kind,student_id,action,file_id,ref_order_id,new_order_id,user_id,user_name,ts,note)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (body.key, issue["kind"], sid, body.action, body.file_id or None, body.ref_order_id or None, new_id,
                                                          c.user["id"], c.user["full_name"], _now(), body.note.strip()[:500] or None))
        _con.commit()
    _audit(c, "muvofiqlik tuzatishi", f"{issue['title']} · {issue['student']['full_name']} · {ACTIONS[body.action]['label']}" + (f" · loyiha #{new_id}" if new_id else ""))
    return {"ok": True, "order_id": new_id}

@router.get("/api/orders/student/{sid}")
def student_history(sid: int, request: Request):
    c = C(request, "read_st", "talaba buyruqlari", str(sid))
    s = db.one(_con, f"SELECT s.id, s.full_name, s.hemis_id, s.status, s.study_form, g.name grp FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=? AND {st_scope(c)}", (sid,))
    if not s: raise HTTPException(404, "Talaba topilmadi")
    ords = db.rows(_con, """SELECT o.id, o.kind, o.reg_no, o.order_date, o.status, o.title, i.group_name, i.data FROM order_students i
                           JOIN orders o ON o.id=i.order_id AND i.version=o.version WHERE i.student_id=? AND o.status!='bekor'
                           ORDER BY COALESCE(o.order_date, substr(o.created_at,1,10)), o.id""", (sid,))
    for o in ords: o["kind_name"] = KINDS[o["kind"]]["short"]; o["data"] = _j(o["data"]); o["status_name"] = STATUS.get(o["status"], o["status"])
    chg = db.rows(_con, "SELECT ts, field, old, new, reg_no, user_name, note, reverted FROM student_changes WHERE student_id=? ORDER BY id DESC", (sid,))
    for x in chg: x["user_name"] = _short(x["user_name"]) or x["user_name"]
    _named(chg)
    files = db.rows(_con, "SELECT id, filename, kind, uploaded_at FROM order_files WHERE student_id=? ORDER BY id DESC", (sid,))
    _audit(c, "talaba buyruqlari", s["full_name"])
    return {"student": s, "orders": ords, "changes": chg, "files": files}

def _named(rows):
    """group_id / faculty_id qiymatlari → nomlar (jurnalda raqam emas, guruh/fakultet nomi ko'rinsin)."""
    maps = {"group_id": {g["id"]: g["name"] for g in db.rows(_con, "SELECT id, name FROM groups_")},
            "faculty_id": {f["id"]: f["name"] for f in db.rows(_con, "SELECT id, name FROM faculties")}}
    for r in rows:
        mp = maps.get(r["field"])
        if not mp: continue
        for k in ("old", "new"):
            if str(r[k] or "").isdigit(): r[k] = mp.get(int(r[k]), r[k])

@router.get("/api/orders/changes/log")
def changes_log(request: Request, q: str = "", offset: int = 0, limit: int = 100):
    c = C(request, "read_st", "o'zgarishlar jurnali")
    w, a = [st_scope(c)], []
    if q.strip():
        like = f"%{q.strip()}%"; w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ? OR ch.reg_no LIKE ? OR ch.old LIKE ? OR ch.new LIKE ?)"); a += [like] * 5
    where = " AND ".join(w)
    total = db.one(_con, f"SELECT COUNT(*) n FROM student_changes ch JOIN students s ON s.id=ch.student_id WHERE {where}", a)["n"]
    rows = db.rows(_con, f"""SELECT ch.*, s.full_name cur_name, s.hemis_id FROM student_changes ch JOIN students s ON s.id=ch.student_id
                            WHERE {where} ORDER BY ch.id DESC LIMIT ? OFFSET ?""", a + [min(max(limit, 1), 300), max(offset, 0)])
    for r in rows: r["user_name"] = _short(r["user_name"]) or r["user_name"]
    _named(rows)
    if offset == 0: _audit(c, "o'zgarishlar jurnali", q[:80])
    return {"items": rows, "total": total}

# ---------------------------------------------------------------------------------------------
# Devonxona: imzolangan buyruqni jurnalga ro'yxatga olish va chiquvchi yozishmalar jurnali (rbac.CHANCERY)
# ---------------------------------------------------------------------------------------------
@router.post("/api/orders/{oid}/register")
def register(oid: int, body: Note, request: Request):
    c = C(request, "register", "devonxona jurnaliga ro'yxatga olish", f"#{oid}")
    o = _order(c, oid)
    if o["status"] != "imzolangan" or o.get("historic"): _bad("Faqat tizimda imzolangan buyruq devonxona jurnaliga olinadi")
    if o.get("journal_at"): _bad("Buyruq allaqachon ro'yxatga olingan")
    note = (body.note or "").strip()[:300] or None
    _con.execute("UPDATE orders SET journal_at=?, journal_by=?, journal_note=? WHERE id=?", (_now(), c.user["id"], note, oid))
    _log(oid, c, "devonxona jurnaliga olindi", note or ""); _con.commit()
    _audit(c, "devonxona jurnaliga olindi", f"{o['reg_no']}" + (f" · {note}" if note else ""))
    return {"ok": True, "reg_no": o["reg_no"]}

def seed_outgoing_demo(con):
    """Devonxona demo jurnali (bo'sh bo'lsa): 3 ta chiquvchi xat — biri imzolangan buyruqqa bog'langan."""
    if db.one(con, "SELECT 1 x FROM outgoing_mail LIMIT 1"): return
    dv = db.one(con, "SELECT id, full_name FROM users WHERE role='devonxona' ORDER BY id LIMIT 1")
    if not dv: return
    o = db.one(con, "SELECT id, reg_no, title FROM orders WHERE status='imzolangan' AND reg_no IS NOT NULL ORDER BY order_date DESC, id DESC LIMIT 1")
    t = _today()
    rows = [("Oliy ta'lim, fan va innovatsiyalar vazirligi", "Talabalar kontingenti harakati to'g'risida ma'lumot (oktabr)", o["id"] if o else None, 6, 3),
            ("Toshkent shahar bandlik bosh boshqarmasi", "Bitiruvchilar bandligi monitoringi bo'yicha javob xati", None, 4, 2),
            ("Riga Technical University", "Hamkorlik memorandumini uzaytirish to'g'risida taklif", None, 1, 1)]
    for k, (addr, subj, oid, ago, pages) in enumerate(rows, 1):
        d = (t - dt.timedelta(days=ago)).isoformat()
        con.execute("""INSERT INTO outgoing_mail(out_no,out_date,addressee,subject,order_id,pages,note,created_by,created_by_name,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", (f"Ch-{t.year % 100:02d}/{k:04d}", d, addr, subj, oid, pages, "Demo yozuv", dv["id"], dv["full_name"], d + "T10:00:00"))
    con.commit()

def next_out_no(year=None) -> str:
    yy = f"{(year or _today().year) % 100:02d}"
    n = 0
    for r in db.rows(_con, "SELECT out_no FROM outgoing_mail WHERE out_no LIKE ?", (f"Ch-{yy}/%",)):
        try: n = max(n, int(r["out_no"].split("/")[1]))
        except (ValueError, IndexError): pass
    return f"Ch-{yy}/{n + 1:04d}"

class Outgoing(BaseModel):
    addressee: str
    subject: str
    out_date: str = ""
    order_id: int = 0
    thread_id: int = 0
    pages: int = 1
    note: str = ""

@router.get("/api/orders/outgoing")
def outgoing_list(request: Request, q: str = "", offset: int = 0, limit: int = 50):
    c = C(request, "outgoing", "chiquvchi yozishmalar jurnali")
    w, a = ["1=1"], []
    if q.strip():
        like = f"%{q.strip()}%"; w.append("(m.out_no LIKE ? OR m.addressee LIKE ? OR m.subject LIKE ?)"); a += [like] * 3
    where = " AND ".join(w)
    total = db.one(_con, f"SELECT COUNT(*) n FROM outgoing_mail m WHERE {where}", a)["n"]
    rows = db.rows(_con, f"""SELECT m.*, o.reg_no order_reg, o.title order_title, t.ref_no thread_ref, t.subject thread_subject FROM outgoing_mail m
                            LEFT JOIN orders o ON o.id=m.order_id LEFT JOIN portal_threads t ON t.id=m.thread_id
                            WHERE {where} ORDER BY m.id DESC LIMIT ? OFFSET ?""", a + [min(max(limit, 1), 200), max(offset, 0)])
    for r in rows: r["created_by_name"] = _short(r["created_by_name"]) or r["created_by_name"]
    if offset == 0: _audit(c, "chiquvchi yozishmalar jurnali", f"{total} ta {q}"[:120])
    return {"items": rows, "total": total, "next_no": next_out_no(), "can_add": c.role.key in CHANCERY}

@router.post("/api/orders/outgoing")
def outgoing_add(body: Outgoing, request: Request):
    c = C(request, "register", "chiquvchi xatni ro'yxatga olish")
    addr, subj = body.addressee.strip()[:200], body.subject.strip()[:300]
    if len(addr) < 3 or len(subj) < 3: _bad("Qabul qiluvchi va mavzuni yozing")
    try: d = dt.date.fromisoformat(body.out_date[:10]).isoformat() if body.out_date else _today().isoformat()
    except ValueError: _bad("Sana noto'g'ri")
    if body.order_id: _order(c, body.order_id)
    if body.thread_id and not db.one(_con, "SELECT 1 x FROM portal_threads WHERE id=?", (body.thread_id,)): _bad("Portal yozishmasi topilmadi")
    with _lock:
        no = next_out_no()
        cur = _con.execute("""INSERT INTO outgoing_mail(out_no,out_date,addressee,subject,order_id,thread_id,pages,note,created_by,created_by_name,created_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (no, d, addr, subj, body.order_id or None, body.thread_id or None, max(1, min(body.pages or 1, 999)),
                                                                (body.note or "").strip()[:500] or None, c.user["id"], c.user["full_name"], _now()))
        if body.order_id: _log(body.order_id, c, "chiquvchi xat", f"{no} · {addr}")
        _con.commit()
    _audit(c, "chiquvchi xat ro'yxatga olindi", f"{no} · {addr} · {subj}"[:200])
    return {"ok": True, "id": cur.lastrowid, "out_no": no}

# "/api/orders/outgoing" — "/api/orders/{oid}" dan oldin tekshirilsin (aks holda 422)
router.routes.sort(key=lambda r: 0 if getattr(r, "path", "") == "/api/orders/outgoing" else 1)
