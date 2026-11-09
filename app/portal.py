"""Bo'limlararo portal: ichki yozishmalar, ish fayllari almashinuvi va umumiy bazalar katalogi.

Tamoyillar:
  * Har bir foydalanuvchi bitta bo'limga tegishli: `org_units` jadvali va `users.unit` maydoni (bir marta aniqlanadi va saqlanadi —
    lavozim nomi o'zgarsa ham xodim boshqa bo'limga "ko'chib" qolmaydi). Bo'lim rahbari — `org_units.head_user`.
  * Yozishma: bo'limdan bo'limlarga rasmiy xat; har bir qabul qiluvchi uchun holat (yangi → o'qilgan → javob berilgan / yo'naltirilgan),
    shaxsiy muddat (rezolyutsiyadan) va bo'lim ichidagi ijrochi (xodim).
  * O'qilganlik har bir XODIM bo'yicha kuzatiladi (`portal_user_reads`): bo'limdan bittasi ochgani boshqalar uchun "o'qilgan" bo'lib qolmaydi.
  * Rezolyutsiya: rektor va prorektorlar xatga "Ijro uchun: bo'lim(lar), mas'ul, muddat" qo'yadi; ijro nazoratda kuzatiladi.
  * Yozishma yopiladi (yuboruvchi yoki rahbariyat) va arxivlanadi (har bir xodim o'zi uchun). Yangi javob kelsa — arxivdan qaytadi.
  * Ro'yxatlar SQL ichida filtrlanadi va sahifalanadi; qidiruv — SQLite FTS5 (bo'lmasa LIKE).
  * Fayl: o'z bo'limi, o'zi yuklagan, o'ziga ulashilgan (yoki "hamma") fayllar ko'rinadi; rahbariyat (rektor, prorektorlar) — hammasi.
    Fayllar ISFT_CORE_FILES_DIR (standart: data/portal_files/) ichida tasodifiy nom bilan saqlanadi; mazmuni tekshiriladi (app/filecheck.py),
    sha256 saqlanadi; zaxira nusxa — `python -m app.portal_backup`.
  * Umumiy bazalar: mavjud jadvallar ustidan faqat o'qish uchun ko'rinishlar — ma'lumot takrorlanmaydi, RBAC saqlanadi.
  * Har bir yuklash, yuklab olish, xat, rezolyutsiya, yo'naltirish va eksport audit jurnaliga yoziladi (resurs "portal").
"""
import csv, datetime as dt, io, json, mimetypes, os, re, shutil, threading, time, unicodedata, uuid, zipfile
from pathlib import Path
from xml.sax.saxutils import escape as _xe
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from . import db, rbac, services as S, filecheck as FC
from .rbac import AccessDenied, Ctx, ROLES

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILES = ROOT / "data" / "portal_files"
FILES = Path(os.getenv("ISFT_CORE_FILES_DIR") or DEFAULT_FILES)   # Railway: doimiy volume (masalan, /data/portal_files)
MAX_BYTES = 20 * 1024 * 1024
RES = "portal"
SEED_TAG = "portal-v2"
PAGE = 50

router = APIRouter()
_con = None
_ctx = None

CATEGORIES = ["Buyruq va me'yoriy hujjatlar", "Hisobotlar", "Moliyaviy", "O'quv-uslubiy", "Rejalar", "Shablonlar", "Yozishmalar ilovasi", "Boshqa"]
KINDS = {"xat": "Rasmiy xat", "sorov": "Ma'lumot so'rovi", "xabarnoma": "Xabarnoma", "topshiriq": "Topshiriq"}
PRIOS = {"oddiy": "Oddiy", "muhim": "Muhim", "shoshilinch": "Shoshilinch"}
ALLOWED_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "rtf", "txt", "csv", "png", "jpg", "jpeg", "zip"}
LEADERS = {"rektor", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar"}
RESOLVERS = LEADERS                       # rezolyutsiya qo'yish huquqi
PENDING = ("yangi", "o'qilgan")           # javob kutilayotgan holatlar
DONE = ("javob berilgan", "yo'naltirilgan")
_PEND_SQL = "('yangi','o''qilgan')"

def _now(): return dt.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
def _today(): return S.TODAY.isoformat()
def _short(name): return (name or "").split(":", 1)[-1].strip() if ":" in (name or "") else ""
def is_leader(c: Ctx) -> bool: return c.role.key in LEADERS
def _pos(name): return (name or "").split(":", 1)[0].strip() if ":" in (name or "") else ""
def _brief(name):
    """"Baratov Ma'rufbek Baxodir o'g'li" → "Baratov M." (ro'yxatlar uchun qisqa)."""
    w = (_short(name) or name or "").split()
    return f"{w[0]} {w[1][0]}." if len(w) > 1 and w[1][:1].isalpha() else (w[0] if w else "")

# O'zgarishlar hisoblagichi: har bir yozuvdan keyin oshadi — hisoblagichlar keshi shunga bog'langan
_VER = [0]
_CNT: dict = {}
def _bump():
    _VER[0] += 1
    if len(_CNT) > 500: _CNT.clear()

# ---------------------------------------------------------------------------------------------
# Bo'limlar: org_units jadvali + users.unit
# ---------------------------------------------------------------------------------------------
ROLE_UNIT = {"rektor": "rektorat", "kotib": "rektorat", "it_head": "it", "it_staff": "it", "call_center": "talabalar"}   # Call-markaz — Registrator ofisi tarkibida
UNIT_TITLE = {"rektorat": "Rektorat", "it": "Axborot texnologiyalari bo'limi", "kengash": "Kuzatuv kengashi",
              "prorektor_oquv": "O'quv ishlari prorektori", "prorektor_ilmiy": "Ilmiy ishlar prorektori",
              "prorektor_moliya": "Moliya-iqtisod prorektori", "prorektor_yoshlar": "Yoshlar masalalari prorektori",
              "ilmiy_bolim": "Ilmiy tadqiqotlar bo'limi"}   # qolganlari — rbac.ROLES nomi (masalan, "Akademik faoliyatni boshqarish bo'limi")
HEAD_ROLES = {"rektor", "kafedra", "dekan", "it_head"}
GROUPS = [("rahbariyat", "Rahbariyat"), ("bolim", "Bo'limlar"), ("fakultet", "Dekanatlar"), ("kafedra", "Kafedralar")]
LEAD_ORDER = ["rektorat", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar", "kengash"]
# Prorektorlar kuratorligi — ISFT tashkiliy tuzilmasi (04.09.2024 tasdiqlangan):
#   O'quv ishlari prorektori: Akademik faoliyat va registrator departamenti (Akademik bo'lim, Registrator ofisi, Ma'lumotlar bazasi),
#     Sirtqi bo'lim, Amaliyot bo'limi, fakultetlar va kafedralar;
#   Ilmiy ishlar prorektori: Ilmiy tadqiqotlar bo'limi, Magistratura bo'limi;
#   Moliya-iqtisod prorektori: Buxgalteriya, Xo'jalik va texnik bo'lim;
#   Yoshlar masalalari birinchi prorektori: Ma'naviyat va ma'rifat bo'limi (tizimda akkaunti yo'q);
#   Rektorga bevosita: Imtihon bo'limi, Kadrlar bo'limi, Strategik, Yuridik, Sifatni ta'minlash, Devonxona, Arxiv.
#   Xalqaro aloqalar va Raqamlashtirish prorektorlari joriy rahbarlar ro'yxatida yo'q: Xalqaro hamkorlik bo'limi — ilmiy ishlar prorektoriga
#   (RBAC'da ham INTL unda), Axborot texnologiyalari bo'limi — rektorga bevosita. Qabul komissiyasi tuzilmada yo'q — raisi rektor.
CURATOR = {"akademik": "prorektor_oquv", "talabalar": "prorektor_oquv", "malumotlar_bazasi": "prorektor_oquv", "sirtqi": "prorektor_oquv",
           "amaliyot": "prorektor_oquv",
           "ilmiy_bolim": "prorektor_ilmiy", "magistratura": "prorektor_ilmiy", "xalqaro": "prorektor_ilmiy",
           "buxgalteriya": "prorektor_moliya", "xojalik": "prorektor_moliya"}
def _curator_of(k): return CURATOR.get(k) or ("prorektor_oquv" if k.startswith(("fak", "kaf")) else None)

# Alohida bo'limlar (o'z roli bo'lmasa ham lavozim nomidan aniqlanadi; akkaunti bo'lmasa ham qabul qiluvchi sifatida ko'rinadi)
EXTRA_UNITS = [("sirtqi", "Sirtqi bo'lim", "Shayzakova Dilbar"), ("malumotlar_bazasi", "Ma'lumotlar bazasi bo'limi", "Ismatov Ravshan")]
_TITLE_UNIT = {n.lower(): k for k, n, _ in EXTRA_UNITS}
# Bo'lim kartasi (qabul qiluvchini tanlashda ko'rsatiladi)
UNIT_INFO = {
    "talabalar": {"place": "Asosiy bino 115-xona · Eco bino 105-xona",
                  "does": ["Talaba hujjatlari va ma'lumotnomalar", "Talaba maqomi, akademik ta'til", "Fanlar va o'quv jarayoni bo'yicha ma'muriy masalalar",
                           "Baholar va akademik natijalar", "Kontrakt va talaba hujjatlari masalalari", "Boshqa rasmiy o'quv jarayoni murojaatlari"]},
    "akademik": {"does": ["Akademik kalendar", "Fanlarga yozilish (enrollment)", "Akademik guruhlarni shakllantirish",
                          "Oraliq va yakuniy nazorat jadvallari", "Yakuniy davlat attestatsiyasi (YDA)"]},
    "sirtqi": {"does": ["Sirtqi ta'lim talabalari bilan ishlash", "Sessiyaga chaqiruv xatlari"]},
    "malumotlar_bazasi": {"does": ["«Registrator» ma'lumotlar bazasini yuritish va yangilash"]},
}

def derive_unit(u: dict) -> str:
    """Bo'limni rol va lavozimdan aniqlash — faqat bir marta (users.unit bo'sh bo'lsa) ishlatiladi."""
    r = u.get("role")
    t = (u.get("full_name") or "").split(":")[0].strip().lower() if ":" in (u.get("full_name") or "") else ""
    for n, k in _TITLE_UNIT.items():
        if t.startswith(n): return k
    if r in ("kafedra", "oqituvchi") and u.get("department_id"): return f"kaf{int(u['department_id'])}"
    if r in ("dekan", "tyutor") and u.get("faculty_id"): return f"fak{int(u['faculty_id'])}"
    return ROLE_UNIT.get(r, r)

def unit_key(u: dict) -> str:
    return u.get("unit") or derive_unit(u)

def my_unit(c: Ctx) -> str:
    if not c.user.get("unit") and _con is not None:      # yangi akkaunt: bo'lim bir marta aniqlanib saqlanadi
        k = derive_unit(c.user)
        try:
            _con.execute("UPDATE users SET unit=? WHERE id=? AND (unit IS NULL OR unit='')", (k, c.user["id"])); _con.commit()
            if isinstance(c.user, dict): c.user["unit"] = k
        except Exception: pass
        return k
    return unit_key(c.user)

def _derive_units(con) -> list[dict]:
    deps = {d["id"]: d for d in db.rows(con, "SELECT * FROM departments")}
    facs = {f["id"]: f for f in db.rows(con, "SELECT * FROM faculties")}
    out = {}
    for u in db.rows(con, "SELECT * FROM users ORDER BY id"):
        if u["role"] not in ROLES: continue
        k = unit_key(u)
        if k.startswith("kaf"):
            d = deps.get(int(k[3:])) or {}
            name, grp, order = f"{d.get('name', 'Kafedra')} kafedrasi", "kafedra", int(k[3:])
        elif k.startswith("fak"):
            f = facs.get(int(k[3:])) or {}
            name, grp, order = f"{f.get('name', 'Fakultet')} fakulteti", "fakultet", int(k[3:])
        elif k in LEAD_ORDER:
            name, grp, order = UNIT_TITLE.get(k) or ROLES[u["role"]].title, "rahbariyat", LEAD_ORDER.index(k)
        else:
            name, grp, order = UNIT_TITLE.get(k) or ROLES[u["role"]].title, "bolim", 0
        rank = 0 if u["role"] in HEAD_ROLES else 1
        cur = out.get(k)
        if not cur:
            out[k] = {"key": k, "name": name, "grp": grp, "ord": order, "head": _short(u["full_name"]), "head_user": u["id"], "_r": rank}
        elif rank < cur["_r"] or (not cur["head"] and _short(u["full_name"])):
            cur.update(head=_short(u["full_name"]) or cur["head"], head_user=u["id"] if rank < cur["_r"] else cur["head_user"], _r=min(rank, cur["_r"]))
    for k, n, head in EXTRA_UNITS:
        if k not in out: out[k] = {"key": k, "name": n, "grp": "bolim", "ord": 0, "head": head, "head_user": None, "_r": 1}
        elif not out[k]["head"]: out[k]["head"] = head
        out[k]["name"] = n
    return list(out.values())

def sync_units(con):
    """users.unit ni to'ldirish (bir marta) va org_units ni yangilash (kurator — tasdiqlangan tuzilmadan; qo'lda tayinlangan rahbar saqlanadi)."""
    for u in db.rows(con, "SELECT * FROM users WHERE unit IS NULL OR unit=''"):
        if u["role"] in ROLES: con.execute("UPDATE users SET unit=? WHERE id=?", (derive_unit(u), u["id"]))
    for x in _derive_units(con):
        info = UNIT_INFO.get(x["key"])
        con.execute("""INSERT INTO org_units(key,name,grp,ord,head,head_user,curator,info) VALUES(?,?,?,?,?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET name=excluded.name, grp=excluded.grp, ord=excluded.ord, head=excluded.head,
                         head_user=COALESCE(org_units.head_user, excluded.head_user), curator=excluded.curator,
                         info=excluded.info""",
                    (x["key"], x["name"], x["grp"], x["ord"], x["head"], x["head_user"], _curator_of(x["key"]), json.dumps(info, ensure_ascii=False) if info else None))
    con.commit()
    _UNITS_CACHE.clear()

_UNITS_CACHE: dict = {}
def units(con) -> list[dict]:
    hit = _UNITS_CACHE.get("u")
    if hit and time.time() - hit[0] < 60: return hit[1]
    gi = {g: i for i, (g, _) in enumerate(GROUPS)}
    res = []
    for r in db.rows(con, "SELECT * FROM org_units"):
        x = {"key": r["key"], "name": r["name"], "group": r["grp"], "order": r["ord"], "head": r["head"] or "", "curator": r["curator"]}
        if r["info"]: x["info"] = json.loads(r["info"])
        res.append(x)
    res.sort(key=lambda x: (gi.get(x["group"], 9), x["order"], x["name"]))
    _UNITS_CACHE["u"] = (time.time(), res)
    return res

def unit_map(con) -> dict: return {u["key"]: u for u in units(con)}
def _uname(um, k): return "Hamma bo'limlar" if k == "*" else (um.get(k) or {}).get("name", k)

def head_user(con, unit) -> int | None:
    r = db.one(con, "SELECT head_user FROM org_units WHERE key=?", (unit,))
    return r["head_user"] if r else None

def is_head(c: Ctx) -> bool:
    return head_user(_con, my_unit(c)) == c.user["id"]

def members(con, unit) -> list[dict]:
    hu = head_user(con, unit)
    return [{"id": u["id"], "name": _short(u["full_name"]) or u["full_name"], "short": _brief(u["full_name"]), "position": _pos(u["full_name"]), "head": u["id"] == hu}
            for u in db.rows(con, "SELECT id, full_name FROM users WHERE unit=? ORDER BY (id!=?), id", (unit, hu or 0))]

def curated(c: Ctx) -> list[str]:
    if not c.role.key.startswith("prorektor_"): return []
    return [r["key"] for r in db.rows(_con, "SELECT key FROM org_units WHERE curator=? ORDER BY grp, ord", (c.role.key,))]

# ---------------------------------------------------------------------------------------------
# Sxema va migratsiya
# ---------------------------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS portal_threads(id INTEGER PRIMARY KEY, ref_no TEXT, subject TEXT, kind TEXT, priority TEXT, due TEXT,
  from_unit TEXT, from_user INT, from_name TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS portal_recipients(thread_id INT, unit TEXT, status TEXT, read_at TEXT, read_by TEXT, answered_at TEXT,
  PRIMARY KEY(thread_id, unit));
CREATE TABLE IF NOT EXISTS portal_msgs(id INTEGER PRIMARY KEY, thread_id INT, unit TEXT, user_id INT, user_name TEXT, body TEXT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_portal_msgs_t ON portal_msgs(thread_id, id);
CREATE TABLE IF NOT EXISTS portal_reads(thread_id INT, unit TEXT, last_msg INT, PRIMARY KEY(thread_id, unit));
CREATE TABLE IF NOT EXISTS portal_attach(msg_id INT, file_id INT, PRIMARY KEY(msg_id, file_id));
CREATE TABLE IF NOT EXISTS portal_files(id INTEGER PRIMARY KEY, name TEXT, stored TEXT UNIQUE, size INT, ext TEXT, category TEXT,
  owner_unit TEXT, uploader_id INT, uploader_name TEXT, created_at TEXT, note TEXT, version INT DEFAULT 1, latest INT DEFAULT 1, downloads INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS portal_shares(file_id INT, unit TEXT, PRIMARY KEY(file_id, unit));
CREATE TABLE IF NOT EXISTS portal_datasets(key TEXT PRIMARY KEY, updated_at TEXT, views INT DEFAULT 0, exports INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS portal_meta(k TEXT PRIMARY KEY, v TEXT);
-- v2
CREATE TABLE IF NOT EXISTS org_units(key TEXT PRIMARY KEY, name TEXT, grp TEXT, ord INT, head TEXT, head_user INT, curator TEXT, info TEXT);
CREATE TABLE IF NOT EXISTS portal_user_reads(thread_id INT, user_id INT, last_msg INT, read_at TEXT, PRIMARY KEY(thread_id, user_id));
CREATE TABLE IF NOT EXISTS portal_watchers(thread_id INT, unit TEXT, added_at TEXT, PRIMARY KEY(thread_id, unit));
CREATE TABLE IF NOT EXISTS portal_hidden(thread_id INT, user_id INT, at TEXT, PRIMARY KEY(thread_id, user_id));
CREATE TABLE IF NOT EXISTS portal_resolutions(id INTEGER PRIMARY KEY, thread_id INT, author_id INT, author_name TEXT, author_unit TEXT,
  text TEXT, units TEXT, lead_unit TEXT, due TEXT, created_at TEXT, state TEXT DEFAULT 'nazoratda', closed_at TEXT);
CREATE INDEX IF NOT EXISTS ix_portal_res_t ON portal_resolutions(thread_id);
CREATE TABLE IF NOT EXISTS portal_drafts(id INTEGER PRIMARY KEY, user_id INT, subject TEXT, body TEXT, to_units TEXT, kind TEXT, priority TEXT,
  due TEXT, file_ids TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS portal_templates(id INTEGER PRIMARY KEY, owner_unit TEXT, title TEXT, subject TEXT, body TEXT, kind TEXT, priority TEXT,
  due_days INT, to_units TEXT, created_by INT, created_at TEXT, uses INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS portal_reminders(user_id INT, thread_id INT, kind TEXT, sent_on TEXT, PRIMARY KEY(user_id, thread_id, kind, sent_on));
CREATE INDEX IF NOT EXISTS ix_portal_rcp_unit ON portal_recipients(unit, status);
CREATE INDEX IF NOT EXISTS ix_portal_thr_from ON portal_threads(from_unit, updated_at);
CREATE INDEX IF NOT EXISTS ix_portal_thr_upd ON portal_threads(updated_at, id);
CREATE INDEX IF NOT EXISTS ix_portal_msgs_unit ON portal_msgs(thread_id, unit, id);
"""
FTS_OK = [False]

def _add_cols(con, table, cols):
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    for n, t in cols:
        if n not in have: con.execute(f"ALTER TABLE {table} ADD COLUMN {n} {t}")

def migrate(con):
    con.executescript(SCHEMA)
    _add_cols(con, "users", [("unit", "TEXT")])
    _add_cols(con, "portal_threads", [("status", "TEXT DEFAULT 'ochiq'"), ("closed_at", "TEXT"), ("closed_by", "TEXT"), ("close_note", "TEXT")])
    _add_cols(con, "portal_recipients", [("due", "TEXT"), ("assignee", "INT"), ("assignee_name", "TEXT"), ("assigned_at", "TEXT"), ("assigned_by", "TEXT"),
                                         ("via", "TEXT DEFAULT 'xat'"), ("lead", "INT DEFAULT 0"), ("forwarded_to", "TEXT"), ("fwd_from", "TEXT")])
    _add_cols(con, "portal_msgs", [("kind", "TEXT DEFAULT 'xat'"), ("meta", "TEXT")])
    _add_cols(con, "portal_files", [("sha256", "TEXT"), ("scan", "TEXT"), ("mime", "TEXT")])
    con.execute("CREATE INDEX IF NOT EXISTS ix_users_unit ON users(unit)")
    con.execute("UPDATE portal_threads SET status='ochiq' WHERE status IS NULL")
    try:
        con.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS portal_fts USING fts5(thread_id UNINDEXED, subject, body,
                       tokenize="unicode61 remove_diacritics 2")""")
        FTS_OK[0] = True
    except Exception as e:          # FTS5 yo'q SQLite yig'ilmasi — LIKE bilan ishlaydi
        print("portal: FTS5 mavjud emas, LIKE qidiruv ishlatiladi:", e)
    con.commit()
    sync_units(con)
    # v1 → v2: bo'lim bo'yicha o'qilganlik → xodim bo'yicha (o'qigan xodim aniq bo'lsa yoki bo'limda bitta xodim bo'lsa)
    if not con.execute("SELECT 1 FROM portal_user_reads LIMIT 1").fetchone() and con.execute("SELECT 1 FROM portal_reads LIMIT 1").fetchone():
        users_of = {}
        for u in db.rows(con, "SELECT id, full_name, unit FROM users"): users_of.setdefault(u["unit"], []).append(u)
        for r in db.rows(con, """SELECT pr.thread_id, pr.unit, pr.last_msg, rc.read_by, rc.read_at, t.from_unit, t.from_user FROM portal_reads pr
                                 JOIN portal_threads t ON t.id=pr.thread_id LEFT JOIN portal_recipients rc ON rc.thread_id=pr.thread_id AND rc.unit=pr.unit"""):
            us = users_of.get(r["unit"], [])
            who = us if len(us) == 1 else [u for u in us if u["full_name"] == r["read_by"] or (r["unit"] == r["from_unit"] and u["id"] == r["from_user"])]
            for u in who:
                con.execute("INSERT OR IGNORE INTO portal_user_reads(thread_id,user_id,last_msg,read_at) VALUES(?,?,?,?)", (r["thread_id"], u["id"], r["last_msg"], r["read_at"]))
        con.commit()
    if FTS_OK[0] and not con.execute("SELECT 1 FROM portal_fts LIMIT 1").fetchone() and con.execute("SELECT 1 FROM portal_msgs LIMIT 1").fetchone():
        reindex(con)

def _norm(s: str) -> str:
    return re.sub(r"[ʻʼ‘’`´]", "'", unicodedata.normalize("NFC", s or ""))

def _fts_add(con, mid: int, tid: int, body: str):
    if not FTS_OK[0]: return
    t = db.one(con, "SELECT ref_no, subject FROM portal_threads WHERE id=?", (tid,)) or {}
    con.execute("INSERT INTO portal_fts(rowid, thread_id, subject, body) VALUES(?,?,?,?)", (mid, tid, _norm(f"{t.get('ref_no') or ''} {t.get('subject') or ''}"), _norm(body)))

def reindex(con):
    if not FTS_OK[0]: return
    con.execute("DELETE FROM portal_fts")
    con.execute("""INSERT INTO portal_fts(rowid, thread_id, subject, body)
                   SELECT m.id, m.thread_id, COALESCE(t.ref_no,'')||' '||COALESCE(t.subject,''), m.body FROM portal_msgs m JOIN portal_threads t ON t.id=m.thread_id""")
    # apostrof variantlari bitta ko'rinishga
    for r in db.rows(con, "SELECT rowid, subject, body FROM portal_fts"):
        s, b = _norm(r["subject"]), _norm(r["body"])
        if s != r["subject"] or b != r["body"]: con.execute("UPDATE portal_fts SET subject=?, body=? WHERE rowid=?", (s, b, r["rowid"]))
    con.commit()

def fts_query(q: str) -> str | None:
    """Foydalanuvchi so'zlaridan xavfsiz FTS5 so'rovi: har bir so'z — prefiks ibora ("o'quv" → "o quv"*), hammasi AND."""
    parts = []
    for w in _norm(q).split()[:8]:
        toks = re.findall(r"\w+", w, flags=re.UNICODE)
        if toks: parts.append('"' + " ".join(toks) + '"*')
    return " AND ".join(parts) or None

def init(con):
    FILES.mkdir(parents=True, exist_ok=True)
    migrate(con)
    try:
        seed(con)
    except Exception as e:      # demo: portal namunasi tayyorlanmasa ham server ishlashi kerak
        import traceback; traceback.print_exc()
        print("portal.seed xatosi:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _audit(c, action, ok=True, detail=""):
    rbac.audit(_con, c, action, RES, ok, detail)

# ---------------------------------------------------------------------------------------------
# Yozishmalar: SQL bo'laklari
# ---------------------------------------------------------------------------------------------
_EFF_DUE = "COALESCE(NULLIF(r.due,''), NULLIF(t.due,''))"

def _part_sql(a="t") -> str:
    """Ishtirokchi bo'lim sharti (3 ta ? — bo'lim kaliti)."""
    return (f"({a}.from_unit=? OR EXISTS(SELECT 1 FROM portal_recipients rp WHERE rp.thread_id={a}.id AND rp.unit=?)"
            f" OR EXISTS(SELECT 1 FROM portal_watchers wp WHERE wp.thread_id={a}.id AND wp.unit=?))")

def _unread_sql(a="t") -> str:
    """Xodim uchun o'qilmagan (2 ta ?: bo'lim, xodim). Tizim yozuvlari (tayinlash, yopish) "yangi xat" hisoblanmaydi."""
    return (f"((SELECT COALESCE(MAX(m.id),0) FROM portal_msgs m WHERE m.thread_id={a}.id AND m.unit!=? AND COALESCE(m.kind,'xat')!='tizim')"
            f" > COALESCE((SELECT ur.last_msg FROM portal_user_reads ur WHERE ur.thread_id={a}.id AND ur.user_id=?),0))")

def _hidden_sql(a="t") -> str:
    return f"EXISTS(SELECT 1 FROM portal_hidden h WHERE h.thread_id={a}.id AND h.user_id=?)"

def _box_where(c: Ctx, box: str) -> tuple[str, list]:
    me, uid = my_unit(c), c.user["id"]
    if box in ("all", "control") and not is_leader(c) or box == "area" and not curated(c):
        _audit(c, f"portal: {box} qutisi", False)
        raise AccessDenied("⛔ " + ("«Yo'nalishim» qutisi faqat prorektorlar uchun (kuratorlik qilinadigan bo'limlar)." if box == "area"
                                    else "Bu bo'lim faqat rektor va prorektorlarga ko'rinadi.") + " So'rov audit jurnaliga yozildi.")
    if box == "sent": return f"t.from_unit=? AND t.status='ochiq' AND NOT {_hidden_sql()}", [me, uid]
    if box == "all": return "1=1", []
    if box == "control": return "t.status='ochiq' AND EXISTS(SELECT 1 FROM portal_resolutions z WHERE z.thread_id=t.id AND z.author_unit=?)", [me]
    if box == "area":
        cu = curated(c); ph = ",".join("?" * len(cu))
        return f"(t.from_unit IN ({ph}) OR EXISTS(SELECT 1 FROM portal_recipients ra WHERE ra.thread_id=t.id AND ra.unit IN ({ph})))", [*cu, *cu]
    if box == "archive": return f"{_part_sql()} AND (t.status='yopilgan' OR {_hidden_sql()})", [me, me, me, uid]
    return (f"EXISTS(SELECT 1 FROM portal_recipients ri WHERE ri.thread_id=t.id AND ri.unit=?) AND t.status='ochiq' AND NOT {_hidden_sql()}", [me, uid])

def _flt_where(c: Ctx, box: str, flt: str) -> tuple[str, list]:
    me, uid, today = my_unit(c), c.user["id"], _today()
    if flt == "unread": return f"{_part_sql()} AND {_unread_sql()}", [me, me, me, me, uid]
    mine_only = box == "inbox"
    scope = "r.unit=? AND " if mine_only else ""
    sa = [me] if mine_only else []
    if flt == "pending":
        return f"t.status='ochiq' AND EXISTS(SELECT 1 FROM portal_recipients r WHERE r.thread_id=t.id AND {scope}r.status IN {_PEND_SQL})", sa
    if flt == "overdue":
        return (f"t.status='ochiq' AND EXISTS(SELECT 1 FROM portal_recipients r WHERE r.thread_id=t.id AND {scope}r.status IN {_PEND_SQL}"
                f" AND {_EFF_DUE} < ?)", [*sa, today])
    if flt == "mine":
        return f"EXISTS(SELECT 1 FROM portal_recipients r WHERE r.thread_id=t.id AND r.unit=? AND r.assignee=?)", [me, uid]
    return "1=1", []

def _q_where(q: str) -> tuple[str, list]:
    q = (q or "").strip()[:80]
    if not q: return "1=1", []
    um = units(_con); ql = _norm(q).lower()
    hit_units = [u["key"] for u in um if ql in _norm(u["name"]).lower() or ql in _norm(u.get("head") or "").lower()][:20]
    ors, args = [], []
    fq = fts_query(q) if FTS_OK[0] else None
    if fq:
        ors.append("t.id IN (SELECT thread_id FROM portal_fts WHERE portal_fts MATCH ?)"); args.append(fq)
    else:
        ors.append("(t.subject LIKE ? OR t.ref_no LIKE ? OR EXISTS(SELECT 1 FROM portal_msgs m WHERE m.thread_id=t.id AND m.body LIKE ?))")
        args += [f"%{q}%"] * 3
    ors.append("t.ref_no LIKE ?"); args.append(f"%{q}%")
    if hit_units:
        ph = ",".join("?" * len(hit_units))
        ors.append(f"(t.from_unit IN ({ph}) OR EXISTS(SELECT 1 FROM portal_recipients rq WHERE rq.thread_id=t.id AND rq.unit IN ({ph})))")
        args += hit_units * 2
    return "(" + " OR ".join(ors) + ")", args

# ---------------------------------------------------------------------------------------------
# Ro'yxat va hisoblagichlar
# ---------------------------------------------------------------------------------------------
def _summaries(con, c: Ctx, ts: list[dict], box: str = "inbox") -> list[dict]:
    if not ts: return []
    me, uid = my_unit(c), c.user["id"]; um = unit_map(con)
    ids = ",".join(str(int(t["id"])) for t in ts)
    rec = {}
    for r in db.rows(con, f"SELECT * FROM portal_recipients WHERE thread_id IN ({ids}) ORDER BY rowid"): rec.setdefault(r["thread_id"], []).append(r)
    last = {r["thread_id"]: r for r in db.rows(con, f"""SELECT m.* FROM portal_msgs m JOIN (SELECT thread_id, MAX(id) mid FROM portal_msgs
        WHERE thread_id IN ({ids}) AND COALESCE(kind,'xat')!='tizim' GROUP BY thread_id) x ON x.mid=m.id""")}
    cnt = {r["thread_id"]: r["n"] for r in db.rows(con, f"SELECT thread_id, COUNT(*) n FROM portal_msgs WHERE thread_id IN ({ids}) AND COALESCE(kind,'xat')!='tizim' GROUP BY thread_id")}
    att = {r["thread_id"]: r["n"] for r in db.rows(con, f"""SELECT m.thread_id, COUNT(*) n FROM portal_attach a JOIN portal_msgs m ON m.id=a.msg_id
        WHERE m.thread_id IN ({ids}) GROUP BY m.thread_id""")}
    reads = {r["thread_id"]: r["last_msg"] for r in db.rows(con, f"SELECT thread_id, last_msg FROM portal_user_reads WHERE user_id=? AND thread_id IN ({ids})", (uid,))}
    other_max = {r["thread_id"]: r["mid"] for r in db.rows(con, f"""SELECT thread_id, MAX(id) mid FROM portal_msgs WHERE thread_id IN ({ids}) AND unit!=?
        AND COALESCE(kind,'xat')!='tizim' GROUP BY thread_id""", (me,))}
    watch = {r["thread_id"] for r in db.rows(con, f"SELECT thread_id FROM portal_watchers WHERE unit=? AND thread_id IN ({ids})", (me,))}
    hidden = {r["thread_id"] for r in db.rows(con, f"SELECT thread_id FROM portal_hidden WHERE user_id=? AND thread_id IN ({ids})", (uid,))}
    res_on = {r["thread_id"] for r in db.rows(con, f"SELECT DISTINCT thread_id FROM portal_resolutions WHERE state='nazoratda' AND thread_id IN ({ids})")}
    today = _today(); out = []
    for t in ts:
        rs = rec.get(t["id"], [])
        mine = next((r for r in rs if r["unit"] == me), None)
        role = "from" if t["from_unit"] == me else "to" if mine else "watch" if t["id"] in watch else "observer"
        open_ = (t.get("status") or "ochiq") == "ochiq"
        pending = [r for r in rs if r["status"] in PENDING]
        due_of = lambda r: r.get("due") or t["due"]
        my_due = (due_of(mine) if mine else t["due"]) or None
        over = open_ and (bool(mine and mine["status"] in PENDING and my_due and my_due < today) if role == "to" and box in ("inbox", "archive")
                          else any(due_of(r) and due_of(r) < today for r in pending))
        lm = last.get(t["id"]) or {}
        out.append({"id": t["id"], "ref_no": t["ref_no"], "subject": t["subject"], "kind": t["kind"], "priority": t["priority"], "due": my_due,
                    "status": t.get("status") or "ochiq", "from_unit": t["from_unit"], "from_unit_name": _uname(um, t["from_unit"]), "from_name": _short(t["from_name"]),
                    "recipients": [{"unit": r["unit"], "name": _uname(um, r["unit"]), "status": r["status"]} for r in rs],
                    "my_status": mine["status"] if mine else None, "role": role,
                    "unread": role != "observer" and (other_max.get(t["id"]) or 0) > (reads.get(t["id"]) or 0),
                    "overdue": over, "pending": len(pending) if open_ else 0, "answered": sum(1 for r in rs if r["status"] in DONE), "total": len(rs),
                    "snippet": re.sub(r"\s+", " ", lm.get("body") or "")[:160], "last_unit_name": _uname(um, lm.get("unit")) if lm else "",
                    "last_at": lm.get("created_at") or t["updated_at"], "created_at": t["created_at"],
                    "count": cnt.get(t["id"], 0), "files": att.get(t["id"], 0),
                    "assignee_name": _brief(mine["assignee_name"]) if mine and mine.get("assignee_name") else None,
                    "assigned_to_me": bool(mine and mine.get("assignee") == uid),
                    "resolution": t["id"] in res_on, "archived": t["id"] in hidden})
    return out

def counts(con, c: Ctx) -> dict:
    me, uid, today = my_unit(c), c.user["id"], _today()
    key = (uid, me, _VER[0], today)
    hit = _CNT.get(key)
    if hit and time.time() - hit[0] < 30: return dict(hit[1])
    p = {"me": me, "uid": uid, "today": today}
    row = con.execute(f"""
      WITH p AS (
        SELECT t.id, t.status='ochiq' AS op, t.from_unit=:me AS frm,
          EXISTS(SELECT 1 FROM portal_recipients r WHERE r.thread_id=t.id AND r.unit=:me) AS rcp,
          EXISTS(SELECT 1 FROM portal_watchers w WHERE w.thread_id=t.id AND w.unit=:me) AS wch,
          EXISTS(SELECT 1 FROM portal_hidden h WHERE h.thread_id=t.id AND h.user_id=:uid) AS hid,
          (SELECT COALESCE(MAX(m.id),0) FROM portal_msgs m WHERE m.thread_id=t.id AND m.unit!=:me AND COALESCE(m.kind,'xat')!='tizim')
            > COALESCE((SELECT x.last_msg FROM portal_user_reads x WHERE x.thread_id=t.id AND x.user_id=:uid),0) AS unr
        FROM portal_threads t)
      SELECT COALESCE(SUM((frm OR rcp OR wch) AND unr AND op AND NOT hid),0),
             COALESCE(SUM(rcp AND unr AND op AND NOT hid),0),
             COALESCE(SUM(frm AND NOT rcp AND unr AND op AND NOT hid),0),
             COALESCE(SUM(rcp AND op AND NOT hid),0),
             COALESCE(SUM(frm AND op AND NOT hid),0),
             COALESCE(SUM((frm OR rcp OR wch) AND (NOT op OR hid)),0)
      FROM p""", p).fetchone()
    rc = con.execute(f"""SELECT COALESCE(SUM(r.status IN {_PEND_SQL}),0), COALESCE(SUM(r.status IN {_PEND_SQL} AND {_EFF_DUE} < :today),0),
                                COALESCE(SUM(r.status IN {_PEND_SQL} AND r.assignee=:uid),0)
                         FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id WHERE r.unit=:me AND t.status='ochiq'
                           AND NOT EXISTS(SELECT 1 FROM portal_hidden h WHERE h.thread_id=t.id AND h.user_id=:uid)""", p).fetchone()
    d = {"unit": me, "unread": row[0], "inbox_unread": row[1], "sent_unread": row[2], "inbox": row[3], "sent": row[4], "archive": row[5],
         "inbox_pending": rc[0], "my_overdue": rc[1], "assigned_to_me": rc[2], "leader": is_leader(c),
         "drafts": con.execute("SELECT COUNT(*) FROM portal_drafts WHERE user_id=?", (uid,)).fetchone()[0]}
    if is_leader(c):
        cr = con.execute(f"""SELECT COUNT(*), COALESCE(SUM(z.due IS NOT NULL AND z.due!='' AND z.due < :today),0) FROM portal_resolutions z
            JOIN portal_threads t ON t.id=z.thread_id
            WHERE z.author_unit=:me AND z.state='nazoratda' AND t.status='ochiq' AND EXISTS(SELECT 1 FROM json_each(z.units) j
              JOIN portal_recipients r ON r.thread_id=z.thread_id AND r.unit=j.value WHERE r.status IN {_PEND_SQL})""", p).fetchone()
        d.update(control=cr[0], control_overdue=cr[1])
        d["all"] = con.execute("SELECT COUNT(*) FROM portal_threads").fetchone()[0]
        d["all_pending"] = con.execute(f"""SELECT COUNT(DISTINCT r.thread_id) FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id
            WHERE t.status='ochiq' AND r.status IN {_PEND_SQL}""").fetchone()[0]
        d["all_overdue"] = con.execute(f"""SELECT COUNT(DISTINCT t.id) FROM portal_threads t JOIN portal_recipients r ON r.thread_id=t.id
            WHERE t.status='ochiq' AND r.status IN {_PEND_SQL} AND {_EFF_DUE} < ?""", (today,)).fetchone()[0]
    cu = curated(c)
    if cu:
        ph = ",".join("?" * len(cu))
        a = con.execute(f"""SELECT COUNT(DISTINCT t.id), COUNT(DISTINCT CASE WHEN {_EFF_DUE} < ? THEN t.id END) FROM portal_recipients r
            JOIN portal_threads t ON t.id=r.thread_id WHERE t.status='ochiq' AND r.status IN {_PEND_SQL} AND r.unit IN ({ph})""", (today, *cu)).fetchone()
        d.update(area_pending=a[0], area_overdue=a[1])
    _CNT[key] = (time.time(), d)
    return dict(d)

BOXES = ("inbox", "sent", "control", "area", "all", "archive")
FLTS = ("all", "unread", "pending", "overdue", "mine")

def list_threads(c: Ctx, box="inbox", q="", flt="all", offset=0, limit=PAGE) -> dict:
    if box not in BOXES: raise HTTPException(400, "Noto'g'ri quti")
    flt = flt if flt in FLTS else "all"
    w1, a1 = _box_where(c, box)
    w2, a2 = _flt_where(c, box, flt)
    w3, a3 = _q_where(q)
    where, args = f"{w1} AND {w2} AND {w3}", [*a1, *a2, *a3]
    offset = max(0, int(offset or 0)); limit = max(1, min(100, int(limit or PAGE)))
    total = _con.execute(f"SELECT COUNT(*) FROM portal_threads t WHERE {where}", args).fetchone()[0]
    ts = db.rows(_con, f"SELECT t.* FROM portal_threads t WHERE {where} ORDER BY t.updated_at DESC, t.id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
    return {"items": _summaries(_con, c, ts, box), "total": total, "offset": offset, "limit": limit, "box": box, "counts": counts(_con, c)}

# ---------------------------------------------------------------------------------------------
# Yozishma: ko'rish
# ---------------------------------------------------------------------------------------------
def _thread(con, tid) -> dict:
    t = db.one(con, "SELECT * FROM portal_threads WHERE id=?", (tid,))
    if not t: raise HTTPException(404, "Yozishma topilmadi")
    return t

def _is_part(con, t, unit) -> bool:
    return t["from_unit"] == unit or bool(con.execute("""SELECT 1 FROM portal_recipients WHERE thread_id=? AND unit=?
        UNION SELECT 1 FROM portal_watchers WHERE thread_id=? AND unit=?""", (t["id"], unit, t["id"], unit)).fetchone())

def _res_view(con, c: Ctx, z: dict, rmap: dict, um: dict) -> dict:
    us = json.loads(z["units"] or "[]"); today = _today()
    ex = [{"unit": u, "name": _uname(um, u), "status": (rmap.get(u) or {}).get("status"), "answered_at": (rmap.get(u) or {}).get("answered_at"),
           "lead": u == z["lead_unit"]} for u in us]
    done = all(x["status"] in DONE for x in ex) if ex else True
    state = "yechilgan" if z["state"] == "yechilgan" else "bajarildi" if done else "nazoratda"
    return {"id": z["id"], "author": _short(z["author_name"]) or z["author_name"], "author_position": _pos(z["author_name"]),
            "author_unit_name": _uname(um, z["author_unit"]), "text": z["text"], "due": z["due"], "created_at": z["created_at"], "lead_unit": z["lead_unit"],
            "units": ex, "state": state, "overdue": state == "nazoratda" and bool(z["due"] and z["due"] < today),
            "can_close": z["state"] != "yechilgan" and (z["author_unit"] == my_unit(c) and c.role.key in RESOLVERS)}

def thread_detail(c: Ctx, tid: int) -> dict:
    t = _thread(_con, tid)
    me, uid = my_unit(c), c.user["id"]; um = unit_map(_con)
    rs = db.rows(_con, "SELECT * FROM portal_recipients WHERE thread_id=? ORDER BY rowid", (tid,))
    watchers = [r["unit"] for r in db.rows(_con, "SELECT unit FROM portal_watchers WHERE thread_id=? ORDER BY added_at", (tid,))]
    mine = next((r for r in rs if r["unit"] == me), None)
    part = t["from_unit"] == me or bool(mine) or me in watchers
    ok = part or is_leader(c)
    _audit(c, "portal: yozishmani ochish", ok, f"{t['ref_no']} {t['subject']}")
    if not ok:
        raise AccessDenied("⛔ Bu yozishma sizning bo'limingizga tegishli emas. So'rov audit jurnaliga yozildi.")
    msgs = db.rows(_con, "SELECT * FROM portal_msgs WHERE thread_id=? ORDER BY id", (tid,))
    att = {}
    if msgs:
        for a in db.rows(_con, f"""SELECT a.msg_id, f.id, f.name, f.ext, f.size, f.version FROM portal_attach a JOIN portal_files f ON f.id=a.file_id
                WHERE a.msg_id IN ({','.join(str(m['id']) for m in msgs)})"""):
            att.setdefault(a.pop("msg_id"), []).append(a)
    reads_before = (db.one(_con, "SELECT last_msg FROM portal_user_reads WHERE thread_id=? AND user_id=?", (tid, uid)) or {}).get("last_msg") or 0
    if part and msgs:   # shu xodim uchun o'qildi; bo'lim holati "yangi" bo'lsa — "o'qilgan" (birinchi o'qigan xodim yoziladi)
        mx = msgs[-1]["id"]; now = _now()
        _con.execute("""INSERT INTO portal_user_reads(thread_id,user_id,last_msg,read_at) VALUES(?,?,?,?)
                        ON CONFLICT(thread_id,user_id) DO UPDATE SET last_msg=MAX(last_msg, excluded.last_msg), read_at=excluded.read_at""", (tid, uid, mx, now))
        if mine and mine["status"] == "yangi":
            _con.execute("UPDATE portal_recipients SET status='o''qilgan', read_at=?, read_by=? WHERE thread_id=? AND unit=? AND status='yangi'",
                         (now, c.user["full_name"], tid, me))
        _con.commit(); _bump()
        rs = db.rows(_con, "SELECT * FROM portal_recipients WHERE thread_id=? ORDER BY rowid", (tid,))
        mine = next((r for r in rs if r["unit"] == me), None)
    # kim o'qigan: har bir qabul qiluvchi bo'lim bo'yicha xodimlar
    readers = {}
    for r in db.rows(_con, """SELECT u.unit, u.full_name, ur.read_at FROM portal_user_reads ur JOIN users u ON u.id=ur.user_id
                              WHERE ur.thread_id=? ORDER BY ur.read_at""", (tid,)):
        readers.setdefault(r["unit"], []).append({"name": _brief(r["full_name"]), "at": r["read_at"]})
    today = _today(); open_ = (t["status"] or "ochiq") == "ochiq"
    rmap = {r["unit"]: r for r in rs}
    resolutions = [_res_view(_con, c, z, rmap, um) for z in db.rows(_con, "SELECT * FROM portal_resolutions WHERE thread_id=? ORDER BY id", (tid,))]
    hidden = bool(_con.execute("SELECT 1 FROM portal_hidden WHERE thread_id=? AND user_id=?", (tid, uid)).fetchone())
    head = is_head(c)
    mem_n = _con.execute("SELECT COUNT(*) FROM users WHERE unit=?", (me,)).fetchone()[0]
    def due_of(r): return r.get("due") or t["due"]
    perms = {"can_reply": part and open_,
             "can_resolve": open_ and c.role.key in RESOLVERS,
             "can_assign": open_ and bool(mine) and head and mem_n > 1,
             "can_take": open_ and bool(mine) and not head and not mine.get("assignee") and mine["status"] in PENDING,
             "can_forward": open_ and bool(mine) and mine["status"] in PENDING,
             "can_close": open_ and (t["from_unit"] == me or is_leader(c)),
             "can_reopen": not open_ and (t["from_unit"] == me or is_leader(c)),
             "can_archive": part and not hidden, "archived": hidden}
    return {"id": t["id"], "ref_no": t["ref_no"], "subject": t["subject"], "kind": t["kind"], "priority": t["priority"], "due": t["due"],
            "status": t["status"] or "ochiq", "closed_at": t["closed_at"], "closed_by": t["closed_by"], "close_note": t["close_note"],
            "from_unit": t["from_unit"], "from_unit_name": _uname(um, t["from_unit"]), "from_name": _short(t["from_name"]), "created_at": t["created_at"],
            "recipients": [{"unit": r["unit"], "name": _uname(um, r["unit"]), "status": r["status"], "read_at": r["read_at"],
                            "read_by": _short(r["read_by"]), "answered_at": r["answered_at"], "due": due_of(r),
                            "overdue": open_ and r["status"] in PENDING and bool(due_of(r) and due_of(r) < today),
                            "via": r.get("via") or "xat", "lead": bool(r.get("lead")), "assignee_id": r.get("assignee"),
                            "assignee_name": _brief(r["assignee_name"]) if r.get("assignee_name") else None,
                            "forwarded_to": [_uname(um, u) for u in json.loads(r["forwarded_to"] or "[]")] if r.get("forwarded_to") else [],
                            "fwd_from": _uname(um, r["fwd_from"]) if r.get("fwd_from") else None,
                            "readers": readers.get(r["unit"], [])} for r in rs],
            "watchers": [{"unit": u, "name": _uname(um, u)} for u in watchers],
            "resolutions": resolutions,
            "messages": [{"id": m["id"], "kind": m.get("kind") or "xat", "unit": m["unit"], "unit_name": _uname(um, m["unit"]),
                          "name": _short(m["user_name"]) or _uname(um, m["unit"]), "position": _pos(m["user_name"]),
                          "mine": m["unit"] == me, "body": m["body"], "created_at": m["created_at"],
                          "new": m["id"] > reads_before and m["unit"] != me and part and (m.get("kind") or "xat") != "tizim",
                          "meta": json.loads(m["meta"]) if m.get("meta") else None, "files": att.get(m["id"], [])} for m in msgs],
            "can_reply": perms["can_reply"], "perms": perms,
            "role": "from" if t["from_unit"] == me else "to" if mine else "watch" if me in watchers else "observer",
            "overdue": open_ and any(r["status"] in PENDING and due_of(r) and due_of(r) < today for r in rs)}

# ---------------------------------------------------------------------------------------------
# Yozishma: yozish amallari
# ---------------------------------------------------------------------------------------------
def _attach(con, c: Ctx, msg_id: int, file_ids, units_to_share):
    """Xatga fayl biriktirish: yuboruvchi ko'ra oladigan fayl bo'lsa — yozishma ishtirokchilariga ulashiladi."""
    n = 0
    for fid in list(dict.fromkeys(int(x) for x in (file_ids or [])))[:10]:
        f = db.one(con, "SELECT * FROM portal_files WHERE id=?", (fid,))
        if not f or not can_see_file(con, c, f): continue
        con.execute("INSERT OR IGNORE INTO portal_attach(msg_id,file_id) VALUES(?,?)", (msg_id, fid))
        for u in units_to_share:
            if u != f["owner_unit"]: con.execute("INSERT OR IGNORE INTO portal_shares(file_id,unit) VALUES(?,?)", (fid, u))
        n += 1
    return n

class ThreadIn(BaseModel):
    subject: str
    body: str
    to: list[str]
    kind: str = "xat"
    priority: str = "oddiy"
    due: str | None = None
    file_ids: list[int] = []
    draft_id: int | None = None

class ReplyIn(BaseModel):
    body: str
    file_ids: list[int] = []

class ResolveIn(BaseModel):
    text: str
    units: list[str]
    lead: str | None = None
    due: str | None = None

class AssignIn(BaseModel):
    user_id: int | None = None

class ForwardIn(BaseModel):
    units: list[str]
    note: str = ""

class NoteIn(BaseModel):
    note: str = ""

class ArchiveIn(BaseModel):
    on: bool = True

def _valid_due(v, future=False):
    if not v: return None
    try: d = dt.date.fromisoformat(str(v)[:10])
    except ValueError: raise HTTPException(400, "Muddat sanasi noto'g'ri")
    if future and d < S.TODAY: raise HTTPException(400, "Muddat o'tgan sana bo'lishi mumkin emas")
    return d.isoformat()

def _msg(con, c: Ctx, tid, unit, body, ts, kind="xat", meta=None) -> int:
    mid = con.execute("INSERT INTO portal_msgs(thread_id,unit,user_id,user_name,body,created_at,kind,meta) VALUES(?,?,?,?,?,?,?,?)",
                      (tid, unit, c.user["id"], c.user["full_name"], body, ts, kind, json.dumps(meta, ensure_ascii=False) if meta else None)).lastrowid
    if kind != "tizim":
        _fts_add(con, mid, tid, body)
        con.execute("UPDATE portal_threads SET updated_at=? WHERE id=?", (ts, tid))
        con.execute("DELETE FROM portal_hidden WHERE thread_id=? AND user_id!=?", (tid, c.user["id"]))   # yangi xabar — arxivdan qaytadi
        con.execute("""INSERT INTO portal_user_reads(thread_id,user_id,last_msg,read_at) VALUES(?,?,?,?)
                       ON CONFLICT(thread_id,user_id) DO UPDATE SET last_msg=MAX(last_msg, excluded.last_msg), read_at=excluded.read_at""", (tid, c.user["id"], mid, ts))
    return mid

def create_thread(con, c: Ctx, body: ThreadIn, ts: str | None = None) -> int:
    me = my_unit(c); um = unit_map(con)
    subj = re.sub(r"\s+", " ", body.subject or "").strip()[:200]
    text = (body.body or "").strip()[:8000]
    to = [u for u in dict.fromkeys(body.to or []) if u in um and u != me]
    if not subj: raise HTTPException(400, "Mavzu kiritilmagan")
    if not text: raise HTTPException(400, "Xat matni bo'sh")
    if not to: raise HTTPException(400, "Qabul qiluvchi bo'lim tanlanmagan")
    if len(to) > 60: raise HTTPException(400, "Qabul qiluvchilar juda ko'p")
    kind = body.kind if body.kind in KINDS else "xat"
    prio = body.priority if body.priority in PRIOS else "oddiy"
    ts = ts or _now()
    cur = con.execute("INSERT INTO portal_threads(ref_no,subject,kind,priority,due,from_unit,from_user,from_name,created_at,updated_at,status) VALUES(?,?,?,?,?,?,?,?,?,?,'ochiq')",
                      ("", subj, kind, prio, _valid_due(body.due), me, c.user["id"], c.user["full_name"], ts, ts))
    tid = cur.lastrowid
    con.execute("UPDATE portal_threads SET ref_no=? WHERE id=?", (f"ICH-{ts[:4]}/{tid:04d}", tid))
    for u in to:
        con.execute("INSERT INTO portal_recipients(thread_id,unit,status,via) VALUES(?,?,?,'xat')", (tid, u, "yangi"))
    mid = _msg(con, c, tid, me, text, ts)
    _attach(con, c, mid, body.file_ids, to)
    if body.draft_id: con.execute("DELETE FROM portal_drafts WHERE id=? AND user_id=?", (body.draft_id, c.user["id"]))
    con.commit(); _bump()
    return tid

def _need_open(t):
    if (t["status"] or "ochiq") != "ochiq": raise HTTPException(409, "Yozishma yopilgan — avval qayta oching")

def reply(con, c: Ctx, tid: int, body: ReplyIn, ts: str | None = None) -> int:
    t = _thread(con, tid)
    me = my_unit(c)
    if not _is_part(con, t, me):
        rbac.audit(con, c, "portal: javob yozish", RES, False, t["ref_no"])
        raise AccessDenied("⛔ Faqat yozishma ishtirokchisi bo'lgan bo'limlar javob yoza oladi.")
    _need_open(t)
    text = (body.body or "").strip()[:8000]
    if not text: raise HTTPException(400, "Javob matni bo'sh")
    ts = ts or _now()
    mid = _msg(con, c, tid, me, text, ts)
    con.execute("""UPDATE portal_recipients SET status='javob berilgan', answered_at=?, read_at=COALESCE(read_at,?), read_by=COALESCE(read_by,?)
                   WHERE thread_id=? AND unit=?""", (ts, ts, c.user["full_name"], tid, me))
    others = [u for u in [t["from_unit"]] + [r["unit"] for r in db.rows(con, "SELECT unit FROM portal_recipients WHERE thread_id=?", (tid,))]
              + [r["unit"] for r in db.rows(con, "SELECT unit FROM portal_watchers WHERE thread_id=?", (tid,))] if u != me]
    _attach(con, c, mid, body.file_ids, list(dict.fromkeys(others)))
    con.commit(); _bump()
    return mid

def resolve(con, c: Ctx, tid: int, body: ResolveIn, ts: str | None = None) -> int:
    t = _thread(con, tid)
    if c.role.key not in RESOLVERS:
        rbac.audit(con, c, "portal: rezolyutsiya", RES, False, t["ref_no"])
        raise AccessDenied("⛔ Rezolyutsiya faqat rektor va prorektorlar tomonidan qo'yiladi. So'rov audit jurnaliga yozildi.")
    _need_open(t)
    me = my_unit(c); um = unit_map(con)
    text = (body.text or "").strip()[:2000]
    us = [u for u in dict.fromkeys(body.units or []) if u in um and u != me]
    if not text: raise HTTPException(400, "Rezolyutsiya matni bo'sh")
    if not us: raise HTTPException(400, "Ijrochi bo'lim tanlanmagan")
    if t["from_unit"] in us: raise HTTPException(400, f"{_uname(um, t['from_unit'])} — xat yuboruvchisi; unga javob yozing, ijrochi qilib bo'lmaydi")
    if len(us) > 20: raise HTTPException(400, "Ijrochilar juda ko'p")
    lead = body.lead if body.lead in us else us[0]
    due = _valid_due(body.due, future=ts is None)
    ts = ts or _now()
    rid = con.execute("""INSERT INTO portal_resolutions(thread_id,author_id,author_name,author_unit,text,units,lead_unit,due,created_at,state)
                         VALUES(?,?,?,?,?,?,?,?,?,'nazoratda')""",
                      (tid, c.user["id"], c.user["full_name"], me, text, json.dumps(us), lead, due, ts)).lastrowid
    for u in us:
        r = db.one(con, "SELECT * FROM portal_recipients WHERE thread_id=? AND unit=?", (tid, u))
        if r:   # allaqachon qabul qiluvchi: ijro uchun qayta ochiladi
            st = "o'qilgan" if r["status"] in DONE or r["read_at"] else "yangi"
            con.execute("UPDATE portal_recipients SET status=?, answered_at=NULL, due=COALESCE(?, due), lead=? WHERE thread_id=? AND unit=?",
                        (st, due, int(u == lead), tid, u))
        else:
            con.execute("INSERT INTO portal_recipients(thread_id,unit,status,via,due,lead) VALUES(?,?,'yangi','rezolyutsiya',?,?)", (tid, u, due, int(u == lead)))
    if not _is_part(con, t, me):
        con.execute("INSERT OR IGNORE INTO portal_watchers(thread_id,unit,added_at) VALUES(?,?,?)", (tid, me, ts))
    names = [_uname(um, u) + (" (mas'ul)" if u == lead and len(us) > 1 else "") for u in us]
    body_txt = f"Ijro uchun: {', '.join(names)}." + (f" Muddat: {dt.date.fromisoformat(due).strftime('%d.%m.%Y')}." if due else "") + f"\n{text}"
    _msg(con, c, tid, me, body_txt, ts, "rezolyutsiya", {"res_id": rid, "units": us, "lead": lead, "due": due})
    con.commit(); _bump()
    return rid

def close_resolution(con, c: Ctx, tid: int, rid: int):
    z = db.one(con, "SELECT * FROM portal_resolutions WHERE id=? AND thread_id=?", (rid, tid))
    if not z: raise HTTPException(404, "Rezolyutsiya topilmadi")
    if z["author_unit"] != my_unit(c) or c.role.key not in RESOLVERS:
        rbac.audit(con, c, "portal: rezolyutsiyani nazoratdan yechish", RES, False, str(rid))
        raise AccessDenied("⛔ Rezolyutsiyani faqat uni qo'ygan rahbar nazoratdan yechadi.")
    ts = _now()
    con.execute("UPDATE portal_resolutions SET state='yechilgan', closed_at=? WHERE id=?", (ts, rid))
    _msg(con, c, tid, my_unit(c), "Rezolyutsiya nazoratdan yechildi", ts, "tizim")
    con.commit(); _bump()

def assign(con, c: Ctx, tid: int, user_id: int | None, ts: str | None = None):
    t = _thread(con, tid); _need_open(t)
    me = my_unit(c)
    r = db.one(con, "SELECT * FROM portal_recipients WHERE thread_id=? AND unit=?", (tid, me))
    if not r:
        rbac.audit(con, c, "portal: ijrochi tayinlash", RES, False, t["ref_no"])
        raise AccessDenied("⛔ Ijrochi faqat xat kelgan bo'lim ichida tayinlanadi.")
    head = head_user(con, me) == c.user["id"]
    if user_id is None:
        if not head and r["assignee"] != c.user["id"]: raise AccessDenied("⛔ Ijrochini faqat bo'lim rahbari olib tashlaydi.")
        con.execute("UPDATE portal_recipients SET assignee=NULL, assignee_name=NULL, assigned_at=NULL, assigned_by=NULL WHERE thread_id=? AND unit=?", (tid, me))
        _msg(con, c, tid, me, "Ijrochi olib tashlandi", ts or _now(), "tizim")
        con.commit(); _bump(); return None
    u = db.one(con, "SELECT id, full_name, unit FROM users WHERE id=?", (user_id,))
    if not u or u["unit"] != me: raise HTTPException(400, "Ijrochi faqat o'z bo'limingiz xodimi bo'lishi mumkin")
    if not head:
        if user_id != c.user["id"]: raise AccessDenied("⛔ Boshqa xodimga faqat bo'lim rahbari tayinlaydi. Siz xatni o'z ijroingizga olishingiz mumkin.")
        if r["assignee"] and r["assignee"] != c.user["id"]: raise HTTPException(409, f"Xat allaqachon {_brief(r['assignee_name'])} ijrosida")
    ts = ts or _now()
    con.execute("UPDATE portal_recipients SET assignee=?, assignee_name=?, assigned_at=?, assigned_by=? WHERE thread_id=? AND unit=?",
                (u["id"], u["full_name"], ts, c.user["full_name"], tid, me))
    txt = f"{_brief(u['full_name'])} xatni o'z ijrosiga oldi" if u["id"] == c.user["id"] else f"Ijrochi tayinlandi: {_brief(u['full_name'])} (tayinladi: {_brief(c.user['full_name'])})"
    _msg(con, c, tid, me, txt, ts, "tizim", {"assignee": u["id"]})
    con.commit(); _bump()
    return u

def forward(con, c: Ctx, tid: int, body: ForwardIn, ts: str | None = None) -> list[str]:
    t = _thread(con, tid); _need_open(t)
    me = my_unit(c); um = unit_map(con)
    r = db.one(con, "SELECT * FROM portal_recipients WHERE thread_id=? AND unit=?", (tid, me))
    if not r:
        rbac.audit(con, c, "portal: yo'naltirish", RES, False, t["ref_no"])
        raise AccessDenied("⛔ Xatni faqat uni qabul qilgan bo'lim yo'naltira oladi.")
    if r["status"] not in PENDING: raise HTTPException(409, "Xatga javob berilgan yoki u allaqachon yo'naltirilgan")
    have = {x["unit"] for x in db.rows(con, "SELECT unit FROM portal_recipients WHERE thread_id=?", (tid,))}
    to = [u for u in dict.fromkeys(body.units or []) if u in um and u != me and u != t["from_unit"] and u not in have]
    if not to: raise HTTPException(400, "Yo'naltirish uchun yangi bo'lim tanlanmagan (tanlanganlar allaqachon ishtirokchi)")
    ts = ts or _now(); due = r["due"]
    for u in to:
        con.execute("INSERT INTO portal_recipients(thread_id,unit,status,via,due,fwd_from) VALUES(?,?,'yangi','yonaltirish',?,?)", (tid, u, due, me))
    con.execute("UPDATE portal_recipients SET status='yo''naltirilgan', answered_at=?, forwarded_to=?, read_at=COALESCE(read_at,?), read_by=COALESCE(read_by,?) WHERE thread_id=? AND unit=?",
                (ts, json.dumps(to), ts, c.user["full_name"], tid, me))
    names = ", ".join(_uname(um, u) for u in to)
    note = (body.note or "").strip()[:2000]
    _msg(con, c, tid, me, f"Yo'naltirildi → {names}" + (f"\n{note}" if note else ""), ts, "xat", {"forward": to})
    con.commit(); _bump()
    return to

def close_thread(con, c: Ctx, tid: int, note: str = "", ts: str | None = None):
    t = _thread(con, tid); me = my_unit(c)
    if t["from_unit"] != me and not is_leader(c):
        rbac.audit(con, c, "portal: yozishmani yopish", RES, False, t["ref_no"])
        raise AccessDenied("⛔ Yozishmani faqat yuboruvchi bo'lim yoki rahbariyat yopadi.")
    _need_open(t)
    ts = ts or _now(); note = (note or "").strip()[:300]
    who = f"{_brief(c.user['full_name']) or c.role.title} ({_uname(unit_map(con), me)})"
    con.execute("UPDATE portal_threads SET status='yopilgan', closed_at=?, closed_by=?, close_note=? WHERE id=?", (ts, who, note, tid))
    _msg(con, c, tid, me, "Yozishma yopildi" + (f": {note}" if note else ""), ts, "tizim")
    con.commit(); _bump()

def reopen_thread(con, c: Ctx, tid: int):
    t = _thread(con, tid); me = my_unit(c)
    if t["from_unit"] != me and not is_leader(c):
        raise AccessDenied("⛔ Yozishmani faqat yuboruvchi bo'lim yoki rahbariyat qayta ochadi.")
    if (t["status"] or "ochiq") == "ochiq": raise HTTPException(409, "Yozishma ochiq")
    con.execute("UPDATE portal_threads SET status='ochiq', closed_at=NULL, closed_by=NULL, close_note=NULL WHERE id=?", (tid,))
    _msg(con, c, tid, me, "Yozishma qayta ochildi", _now(), "tizim")
    con.commit(); _bump()

def archive(con, c: Ctx, tid: int, on: bool):
    t = _thread(con, tid)
    if not _is_part(con, t, my_unit(c)): raise AccessDenied("⛔ Faqat o'z yozishmalaringizni arxivlash mumkin.")
    if on: con.execute("INSERT OR IGNORE INTO portal_hidden(thread_id,user_id,at) VALUES(?,?,?)", (tid, c.user["id"], _now()))
    else: con.execute("DELETE FROM portal_hidden WHERE thread_id=? AND user_id=?", (tid, c.user["id"]))
    con.commit(); _bump()

# ---------------------------------------------------------------------------------------------
# Qoralamalar va shablonlar
# ---------------------------------------------------------------------------------------------
class DraftIn(BaseModel):
    id: int | None = None
    subject: str = ""
    body: str = ""
    to: list[str] = []
    kind: str = "xat"
    priority: str = "oddiy"
    due: str | None = None
    file_ids: list[int] = []

class TemplateIn(BaseModel):
    title: str
    subject: str = ""
    body: str = ""
    kind: str = "xat"
    priority: str = "oddiy"
    due_days: int | None = None
    to: list[str] = []

def _draft_view(d):
    return {"id": d["id"], "subject": d["subject"] or "", "body": d["body"] or "", "to": json.loads(d["to_units"] or "[]"), "kind": d["kind"] or "xat",
            "priority": d["priority"] or "oddiy", "due": d["due"], "file_ids": json.loads(d["file_ids"] or "[]"), "updated_at": d["updated_at"]}

def drafts(c: Ctx) -> list[dict]:
    return [_draft_view(d) for d in db.rows(_con, "SELECT * FROM portal_drafts WHERE user_id=? ORDER BY updated_at DESC, id DESC", (c.user["id"],))]

def save_draft(con, c: Ctx, b: DraftIn, ts: str | None = None) -> dict:
    um = unit_map(con); ts = ts or _now()
    vals = (b.subject.strip()[:200], b.body[:8000], json.dumps([u for u in dict.fromkeys(b.to) if u in um][:60]), b.kind if b.kind in KINDS else "xat",
            b.priority if b.priority in PRIOS else "oddiy", _valid_due(b.due) if b.due else None, json.dumps([int(x) for x in b.file_ids][:10]), ts)
    if b.id:
        n = con.execute("""UPDATE portal_drafts SET subject=?, body=?, to_units=?, kind=?, priority=?, due=?, file_ids=?, updated_at=?
                           WHERE id=? AND user_id=?""", (*vals, b.id, c.user["id"])).rowcount
        if not n: raise HTTPException(404, "Qoralama topilmadi")
        did = b.id
    else:
        if con.execute("SELECT COUNT(*) FROM portal_drafts WHERE user_id=?", (c.user["id"],)).fetchone()[0] >= 50:
            raise HTTPException(400, "Qoralamalar soni 50 tadan oshdi — keraksizlarini o'chiring")
        did = con.execute("INSERT INTO portal_drafts(user_id,subject,body,to_units,kind,priority,due,file_ids,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (c.user["id"], *vals)).lastrowid
    con.commit(); _bump()
    return {"ok": True, "id": did, "updated_at": ts}

def templates(c: Ctx) -> list[dict]:
    me = my_unit(c)
    return [{"id": t["id"], "title": t["title"], "subject": t["subject"] or "", "body": t["body"] or "", "kind": t["kind"] or "xat", "priority": t["priority"] or "oddiy",
             "due_days": t["due_days"], "to": json.loads(t["to_units"] or "[]"), "scope": "institut" if t["owner_unit"] == "*" else "bolim",
             "mine": t["owner_unit"] == me, "uses": t["uses"] or 0}
            for t in db.rows(_con, "SELECT * FROM portal_templates WHERE owner_unit IN ('*', ?) ORDER BY owner_unit='*', uses DESC, id", (me,))]

def save_template(con, c: Ctx, b: TemplateIn, owner: str | None = None) -> int:
    um = unit_map(con)
    title = re.sub(r"\s+", " ", b.title or "").strip()[:80]
    if not title: raise HTTPException(400, "Shablon nomi kiritilmagan")
    if not (b.subject or "").strip() and not (b.body or "").strip(): raise HTTPException(400, "Shablon bo'sh")
    dd = None if b.due_days is None else max(0, min(90, int(b.due_days)))
    tid = con.execute("""INSERT INTO portal_templates(owner_unit,title,subject,body,kind,priority,due_days,to_units,created_by,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (owner or my_unit(c), title, (b.subject or "").strip()[:200], (b.body or "")[:8000], b.kind if b.kind in KINDS else "xat",
                       b.priority if b.priority in PRIOS else "oddiy", dd, json.dumps([u for u in dict.fromkeys(b.to) if u in um][:60]), c.user["id"], _now())).lastrowid
    con.commit()
    return tid

# ---------------------------------------------------------------------------------------------
# Muddat eslatmalari (veb bildirishnomalar va Telegram uchun umumiy manba)
# ---------------------------------------------------------------------------------------------
def reminders_for(con, user: dict, horizon: int = 2) -> list[dict]:
    """Xodim uchun muddati yaqin/o'tgan xatlar:
       * menga — xat menga biriktirilgan;  * bolimga — biriktirilmagan, men bo'lim rahbariman;
       * yuborgan — men yuborgan xatga muddatda javob kelmagan;  * nazorat — men qo'ygan rezolyutsiya ijrosi muddatdan o'tgan."""
    me, uid = unit_key(user), user["id"]; today = S.TODAY
    lim = (today + dt.timedelta(days=horizon)).isoformat()
    head = head_user(con, me) == uid
    out = []
    def add(r, who, d):
        days = (dt.date.fromisoformat(d) - today).days
        kind = "otgan" if days < 0 else "bugun" if days == 0 else "ertaga" if days == 1 else "yaqin"
        out.append({"thread_id": r["id"], "ref_no": r["ref_no"], "subject": r["subject"], "due": d, "days_left": days, "kind": kind, "who": who,
                    "from_unit": r.get("from_unit")})
    for r in db.rows(con, f"""SELECT t.id, t.ref_no, t.subject, t.from_unit, r.assignee, {_EFF_DUE} d FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id
                              WHERE r.unit=? AND t.status='ochiq' AND r.status IN {_PEND_SQL} AND {_EFF_DUE} <= ? ORDER BY d""", (me, lim)):
        if r["assignee"] == uid: add(r, "menga", r["d"])
        elif not r["assignee"] and head: add(r, "bolimga", r["d"])
    for r in db.rows(con, f"""SELECT t.id, t.ref_no, t.subject, t.from_unit, MIN({_EFF_DUE}) d FROM portal_threads t JOIN portal_recipients r ON r.thread_id=t.id
                              WHERE t.from_unit=? AND t.from_user=? AND t.status='ochiq' AND r.status IN {_PEND_SQL} AND {_EFF_DUE} < ? GROUP BY t.id""",
                       (me, uid, today.isoformat())):
        add(r, "yuborgan", r["d"])
    for r in db.rows(con, f"""SELECT t.id, t.ref_no, t.subject, t.from_unit, z.due d FROM portal_resolutions z JOIN portal_threads t ON t.id=z.thread_id
                              WHERE z.author_id=? AND z.state='nazoratda' AND t.status='ochiq' AND z.due IS NOT NULL AND z.due < ?
                                AND EXISTS(SELECT 1 FROM json_each(z.units) j JOIN portal_recipients r ON r.thread_id=z.thread_id AND r.unit=j.value
                                           WHERE r.status IN {_PEND_SQL})""", (uid, today.isoformat())):
        add(r, "nazorat", r["d"])
    out.sort(key=lambda x: (x["days_left"], x["thread_id"]))
    return out

REMIND_LABEL = {"otgan": "muddati o'tgan", "bugun": "muddat — bugun", "ertaga": "muddat — ertaga", "yaqin": "muddat yaqin"}
WHO_LABEL = {"menga": "sizga biriktirilgan", "bolimga": "bo'limingizga", "yuborgan": "javob kelmadi", "nazorat": "rezolyutsiya ijrosi"}

def telegram_digest(con) -> list[tuple[dict, str, list]]:
    """Telegram'ga ulangan xodimlar uchun kunlik eslatma matni. Bir xil (xat, tur) uchun kuniga ko'pi bilan bitta;
       muddati o'tganlar — har 3 kunda bir marta takrorlanadi."""
    today = S.TODAY.isoformat(); out = []
    for u in db.rows(con, "SELECT * FROM users WHERE telegram_id IS NOT NULL"):
        if u["role"] not in ROLES or ROLES[u["role"]].local_only: continue
        items = []
        for it in reminders_for(con, u):
            k = f"{it['who']}:{it['kind']}"
            if con.execute("SELECT 1 FROM portal_reminders WHERE user_id=? AND thread_id=? AND kind=? AND sent_on>=?",
                           (u["id"], it["thread_id"], k, (S.TODAY - dt.timedelta(days=2 if it["kind"] == "otgan" else 0)).isoformat())).fetchone():
                continue
            items.append((it, k))
        if not items: continue
        lines = ["📬 Portal: muddat eslatmasi"]
        for it, _ in items[:12]:
            mark = "🔴" if it["kind"] == "otgan" else "🟠" if it["kind"] == "bugun" else "🟡"
            lines.append(f"{mark} {it['ref_no']} «{it['subject'][:90]}» — {REMIND_LABEL[it['kind']]} ({dt.date.fromisoformat(it['due']).strftime('%d.%m')}), {WHO_LABEL[it['who']]}")
        if len(items) > 12: lines.append(f"… va yana {len(items) - 12} ta")
        lines.append("\nBatafsil: ISFT Core → Portal")
        out.append((u, "\n".join(lines), [(it["thread_id"], k) for it, k in items]))
    return out

def mark_reminded(con, user_id: int, keys: list):
    today = S.TODAY.isoformat()
    con.executemany("INSERT OR IGNORE INTO portal_reminders(user_id,thread_id,kind,sent_on) VALUES(?,?,?,?)", [(user_id, t, k, today) for t, k in keys])
    con.commit()

# ---------------------------------------------------------------------------------------------
# Fayllar
# ---------------------------------------------------------------------------------------------
def can_see_file(con, c: Ctx, f: dict) -> bool:
    if is_leader(c) or f["uploader_id"] == c.user["id"] or f["owner_unit"] == my_unit(c): return True
    return bool(con.execute("SELECT 1 FROM portal_shares WHERE file_id=? AND unit IN ('*', ?)", (f["id"], my_unit(c))).fetchone())

def _vis_sql(c: Ctx, alias="f") -> tuple[str, tuple]:
    if is_leader(c): return "1=1", ()
    me = my_unit(c)
    return (f"({alias}.uploader_id=? OR {alias}.owner_unit=? OR EXISTS(SELECT 1 FROM portal_shares s WHERE s.file_id={alias}.id AND s.unit IN ('*', ?)))",
            (c.user["id"], me, me))

def safe_name(name: str) -> tuple[str, str]:
    n = unicodedata.normalize("NFC", str(name or "")).replace("\\", "/").split("/")[-1]
    n = "".join(ch for ch in n if unicodedata.category(ch)[0] != "C")
    n = re.sub(r"[^\w\s.\-()'ʻʼ‘’,+&№]", "_", n, flags=re.UNICODE).strip(" ._")
    n = re.sub(r"\s+", " ", n)
    if "." not in n: raise HTTPException(400, "Fayl kengaytmasi yo'q")
    stem, ext = n.rsplit(".", 1)
    ext = ext.lower()
    if ext not in ALLOWED_EXT: raise HTTPException(400, f"«.{ext}» turidagi fayllar qabul qilinmaydi")
    stem = stem[:120].strip(" ._") or "fayl"
    return f"{stem}.{ext}", ext

def _file_view(con, c: Ctx, f: dict, um: dict, shares: dict, vers: dict) -> dict:
    sh = shares.get(f["id"], [])
    return {"id": f["id"], "name": f["name"], "ext": f["ext"], "size": f["size"], "category": f["category"], "owner_unit": f["owner_unit"],
            "owner_unit_name": _uname(um, f["owner_unit"]), "uploader": _short(f["uploader_name"]) or _uname(um, f["owner_unit"]),
            "created_at": f["created_at"], "note": f["note"] or "", "version": f["version"], "versions": vers.get((f["owner_unit"], f["name"].lower()), 1),
            "downloads": f["downloads"], "public": "*" in sh, "shares": [{"unit": u, "name": _uname(um, u)} for u in sh if u != "*"],
            "mine": f["uploader_id"] == c.user["id"], "own_unit": f["owner_unit"] == my_unit(c)}

def list_files(c: Ctx, q="", unit="", cat="", scope="all") -> dict:
    con = _con; me = my_unit(c); um = unit_map(con)
    vw, va = _vis_sql(c)
    rows = db.rows(con, f"SELECT * FROM portal_files f WHERE latest=1 AND {vw} ORDER BY created_at DESC, id DESC", va)
    shares = {}
    if rows:
        for s in db.rows(con, f"SELECT * FROM portal_shares WHERE file_id IN ({','.join(str(r['id']) for r in rows)})"):
            shares.setdefault(s["file_id"], []).append(s["unit"])
    vers = {(r["owner_unit"], r["n"]): r["c"] for r in db.rows(con, "SELECT owner_unit, lower(name) n, COUNT(*) c FROM portal_files GROUP BY 1, 2")}
    allv = [_file_view(con, c, f, um, shares, vers) for f in rows]
    def in_scope(x):
        if scope == "mine": return x["own_unit"] or x["mine"]
        if scope == "shared": return not x["own_unit"] and not x["mine"]
        return True
    base = [x for x in allv if in_scope(x)]
    fac_units, fac_cats = {}, {}
    for x in base:
        fac_units[x["owner_unit"]] = fac_units.get(x["owner_unit"], 0) + 1
    ql = (q or "").strip().lower()[:80]
    items = [x for x in base if (not unit or x["owner_unit"] == unit)
             and (not ql or ql in x["name"].lower() or ql in x["note"].lower() or ql in x["owner_unit_name"].lower() or ql in x["uploader"].lower())]
    for x in items: fac_cats[x["category"]] = fac_cats.get(x["category"], 0) + 1
    if cat: items = [x for x in items if x["category"] == cat]
    order = {u["key"]: i for i, u in enumerate(units(con))}
    return {"items": items, "total": len(base),
            "units": sorted([{"key": k, "name": _uname(um, k), "n": n} for k, n in fac_units.items()], key=lambda u: order.get(u["key"], 999)),
            "cats": [{"name": k, "n": fac_cats[k]} for k in CATEGORIES if k in fac_cats],
            "scopes": {"all": len(allv), "mine": sum(1 for x in allv if x["own_unit"] or x["mine"]), "shared": sum(1 for x in allv if not x["own_unit"] and not x["mine"])},
            "categories": CATEGORIES, "max_mb": MAX_BYTES // (1024 * 1024), "leader": is_leader(c), "unit": me, "unit_name": _uname(um, me)}

def store_file(con, c: Ctx, name: str, data: bytes, category: str, share: list[str], note: str = "", ts: str | None = None, owner_unit: str | None = None) -> dict:
    name, ext = safe_name(name)
    if not data: raise HTTPException(400, "Fayl bo'sh")
    if len(data) > MAX_BYTES: raise HTTPException(413, f"Fayl hajmi {MAX_BYTES // (1024 * 1024)} MB dan oshmasligi kerak")
    um = unit_map(con)
    me = owner_unit or my_unit(c)
    share = ["*"] if "*" in (share or []) else [u for u in dict.fromkeys(share or []) if u in um and u != me]
    category = category if category in CATEGORIES else "Boshqa"
    try:
        chk = FC.inspect(name, ext, data)          # magic bytes, makros, arxiv ichi, ixtiyoriy ClamAV
    except FC.FileRejected as e:
        raise HTTPException(415, str(e))
    stored = f"{uuid.uuid4().hex}.{ext}"
    FILES.mkdir(parents=True, exist_ok=True)
    p = (FILES / stored).resolve()
    if p.parent != FILES.resolve(): raise HTTPException(400, "Noto'g'ri fayl nomi")
    p.write_bytes(data)
    prev = db.one(con, "SELECT * FROM portal_files WHERE owner_unit=? AND lower(name)=lower(?) AND latest=1", (me, name))
    ver = (prev["version"] + 1) if prev else 1
    if prev: con.execute("UPDATE portal_files SET latest=0 WHERE owner_unit=? AND lower(name)=lower(?)", (me, name))
    fid = con.execute("""INSERT INTO portal_files(name,stored,size,ext,category,owner_unit,uploader_id,uploader_name,created_at,note,version,latest,sha256,scan,mime)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                      (name, stored, len(data), ext, category, me, c.user["id"], c.user["full_name"], ts or _now(), (note or "").strip()[:300], ver,
                       chk["sha256"], chk["scan"], chk["mime"])).lastrowid
    for u in share: con.execute("INSERT OR IGNORE INTO portal_shares(file_id,unit) VALUES(?,?)", (fid, u))
    con.commit()
    return {"id": fid, "name": name, "version": ver, "size": len(data), "scan": chk["scan"]}

def file_path(f: dict) -> Path:
    p = (FILES / str(f["stored"])).resolve()
    if p.parent != FILES.resolve(): raise HTTPException(404, "Fayl topilmadi")
    if not p.is_file(): raise HTTPException(404, "Fayl serverda topilmadi — zaxira nusxadan tiklash kerak (Axborot texnologiyalari bo'limi)")
    return p

# ---------------------------------------------------------------------------------------------
# Umumiy bazalar (mavjud jadvallar ustidan faqat o'qish uchun ko'rinishlar)
# ---------------------------------------------------------------------------------------------
DAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]
SLOTS = {1: "08:30", 2: "10:00", 3: "11:30", 4: "13:30", 5: "15:00", 6: "16:30"}

def _student_detail(c: Ctx) -> bool:
    return c.can(rbac.STUDENTS) and not c.aggregate_only(rbac.STUDENTS)

def _like(q, cols):
    q = (q or "").strip()[:60]
    if not q: return "", ()
    return " AND (" + " OR ".join(f"{x} LIKE ?" for x in cols) + ")", tuple(f"%{q}%" for _ in cols)

def ds_kontingent(con, c: Ctx, q=""):
    if _student_detail(c):
        w, a = _like(q, ["s.full_name", "s.hemis_id", "g.name"])
        sql = f"""SELECT s.hemis_id, s.full_name, g.name, f.name, g.course, s.study_form, s.payment_type, s.status FROM students s
                  JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id WHERE {c.student_scope('s')}{w} ORDER BY g.name, s.full_name"""
        note = f"To'liq ro'yxat — ko'lamingiz: {c.scope_label(con)}. Shaxsiy ma'lumot: faqat xizmat maqsadida."
        return ["HEMIS ID", "F.I.Sh.", "Guruh", "Fakultet", "#Kurs", "Ta'lim shakli", "To'lov turi", "Holat"], sql, a, "toliq", note
    w, a = _like(q, ["g.name", "g.direction", "f.name"])
    sql = f"""SELECT g.name, f.name, g.direction, g.course, g.form, COUNT(s.id), SUM(s.status='faol'), SUM(s.status!='faol') FROM groups_ g
              JOIN faculties f ON f.id=g.faculty_id LEFT JOIN students s ON s.group_id=g.id WHERE 1=1{w} GROUP BY g.id ORDER BY g.name"""
    return (["Guruh", "Fakultet", "Yo'nalish", "#Kurs", "Ta'lim shakli", "#Talabalar", "#Faol", "#Ta'tilda"], sql, a, "jamlangan",
            "Jamlangan ko'rinish: guruhlar kesimida soni. Talabalarning shaxsiy ro'yxati lavozimingiz uchun yopiq.")

def ds_jadval(con, c: Ctx, q=""):
    w, a = _like(q, ["g.name", "sc.subject", "t.full_name", "r.name"])
    day = "CASE sc.weekday " + " ".join(f"WHEN {i} THEN '{d}'" for i, d in enumerate(DAYS)) + " END"
    tm = "CASE sc.slot " + " ".join(f"WHEN {i} THEN '{i}-para · {h}'" for i, h in SLOTS.items()) + " END"
    sql = f"""SELECT {day}, {tm}, g.name, sc.subject, t.full_name, substr(r.name,1,instr(r.name||' ·',' ·')-1) FROM schedule sc
              LEFT JOIN groups_ g ON g.id=sc.group_id LEFT JOIN teachers t ON t.id=sc.teacher_id LEFT JOIN rooms r ON r.id=sc.room_id
              WHERE 1=1{w} ORDER BY sc.weekday, sc.slot, r.name"""
    return ["Kun", "Para", "Guruh", "Fan", "O'qituvchi", "Auditoriya"], sql, a, "toliq", "Haftalik dars jadvali — barcha bo'limlar uchun ochiq."

def ds_oqituvchilar(con, c: Ctx, q=""):
    w, a = _like(q, ["t.full_name", "d.name", "t.position"])
    sql = f"""SELECT t.full_name, d.name, t.position, t.degree, t.load_hours, t.h_index FROM teachers t LEFT JOIN departments d ON d.id=t.department_id
              WHERE 1=1{w} ORDER BY d.id, CASE WHEN t.position='Kafedra mudiri' THEN 0 ELSE 1 END, t.full_name"""
    return (["F.I.Sh.", "Kafedra", "Lavozim", "Ilmiy daraja", "#Yuklama (soat)", "#h-indeks"], sql, a, "toliq",
            "Maosh, pasport va boshqa shaxsiy kadrlar ma'lumoti bu ro'yxatga kiritilmagan — ular faqat Kadrlar bo'limida.")

def ds_kontrakt(con, c: Ctx, q=""):
    if not c.can(rbac.CONTRACTS):
        raise AccessDenied(f"⛔ Kontrakt to'lovlari: '{c.role.title}' lavozimi uchun ruxsat yo'q.")
    w, a = _like(q, ["g.name", "f.name"])
    sql = f"""SELECT g.name, f.name, COUNT(*), SUM(s.contract_amount), SUM(s.paid_amount), SUM(s.contract_amount-s.paid_amount),
              ROUND(100.0*SUM(s.paid_amount)/MAX(SUM(s.contract_amount),1),1), SUM(s.contract_amount>s.paid_amount)
              FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
              WHERE s.payment_type='kontrakt' AND {c.student_scope('s')}{w} GROUP BY g.id ORDER BY 7, g.name"""
    return (["Guruh", "Fakultet", "#Kontrakt talabalar", "#Shartnoma (so'm)", "#To'langan (so'm)", "#Qarz (so'm)", "#To'lov %", "#Qarzdorlar"], sql, a, "jamlangan",
            "Guruhlar kesimida jamlangan; eng past to'lov foizi yuqorida. Talaba bo'yicha tafsilot — Buxgalteriya va Registrator ofisida.")

def ds_auditoriyalar(con, c: Ctx, q=""):
    w, a = _like(q, ["r.name", "r.building", "r.kind"])
    sql = f"""SELECT substr(r.name,1,instr(r.name||' ·',' ·')-1), r.building, r.kind, r.capacity,
              (SELECT COUNT(*) FROM schedule sc WHERE sc.room_id=r.id), ROUND(100.0*(SELECT COUNT(*) FROM schedule sc WHERE sc.room_id=r.id)/36,0),
              (SELECT COUNT(*) FROM json_each(r.equipment)) FROM rooms r WHERE 1=1{w} ORDER BY r.building, r.name"""
    return (["Xona", "Bino", "Turi", "#Sig'im", "#Haftalik darslar", "#Bandlik %", "#Jihozlar"], sql, a, "toliq",
            "Bandlik — dars jadvali bo'yicha (haftada 36 para). Jonli bandlik «Auditoriyalar» bo'limida.")

def ds_tuzilma(con, c: Ctx, q=""):
    w, a = _like(q, ["d.name", "f.name", "d.head"])
    sql = f"""SELECT d.name, COALESCE(f.name,'Institut miqyosida'), d.head, (SELECT COUNT(*) FROM teachers t WHERE t.department_id=d.id),
              (SELECT COUNT(*) FROM groups_ g WHERE g.department_id=d.id),
              (SELECT COUNT(*) FROM students s JOIN groups_ g ON g.id=s.group_id WHERE g.department_id=d.id)
              FROM departments d LEFT JOIN faculties f ON f.id=d.faculty_id WHERE 1=1{w} ORDER BY d.id"""
    return ["Kafedra", "Fakultet", "Mudir", "#O'qituvchilar", "#Guruhlar", "#Talabalar"], sql, a, "toliq", "Fakultet va kafedralar tuzilmasi — barcha uchun ochiq."

def ds_hamkorlar(con, c: Ctx, q=""):
    w, a = _like(q, ["p.name", "p.country", "p.kind"])
    sql = f"""SELECT p.name, p.country, p.kind, p.signed, p.expires, p.status, p.students_exchanged FROM partners p WHERE 1=1{w} ORDER BY p.expires"""
    return ["Hamkor", "Davlat", "Dastur turi", "Imzolangan", "Tugaydi", "Holat", "#Almashinuv"], sql, a, "toliq", "Xalqaro hamkorlik shartnomalari reyestri."

def ds_nashrlar(con, c: Ctx, q=""):
    w, a = _like(q, ["p.title", "t.full_name", "d.name", "p.kind"])
    sql = f"""SELECT p.title, p.kind, p.year, p.citations, t.full_name, d.name FROM publications p LEFT JOIN teachers t ON t.id=p.teacher_id
              LEFT JOIN departments d ON d.id=t.department_id WHERE 1=1{w} ORDER BY p.year DESC, p.citations DESC"""
    return ["Nashr", "Turi", "#Yil", "#Iqtiboslar", "Muallif", "Kafedra"], sql, a, "toliq", "Professor-o'qituvchilarning ilmiy nashrlari."

def ds_qabul(con, c: Ctx, q=""):
    w, a = _like(q, ["direction"])
    sql = f"""SELECT direction, COUNT(*), SUM(status='talaba bo''ldi'), SUM(status='tavsiya etildi'), SUM(status='rad etildi'),
              ROUND(AVG(score),1), SUM(payment_type='grant') FROM applicants WHERE 1=1{w} GROUP BY direction ORDER BY 2 DESC"""
    return (["Yo'nalish", "#Arizalar", "#Talaba bo'ldi", "#Tavsiya etildi", "#Rad etildi", "#O'rtacha ball", "#Grant"], sql, a, "jamlangan",
            "2026 qabul kampaniyasi — yo'nalishlar kesimida jamlangan.")

DATASETS = [
    {"key": "kontingent", "title": "Talabalar kontingenti", "owner": "talabalar", "icon": "users", "fn": ds_kontingent,
     "desc": "«Registrator» ma'lumotlar bazasidan: guruhlar bo'yicha talabalar soni va holati. Ruxsati bor lavozimlarga — o'z ko'lamidagi ro'yxat.",
     "access": "Hamma — jamlangan · shaxsiy ro'yxat: Registrator, dekanat, kafedra (o'z ko'lami)"},
    {"key": "jadval", "title": "Dars jadvali", "owner": "akademik", "icon": "calendar", "fn": ds_jadval,
     "desc": "Haftalik dars jadvali: kun, para, guruh, fan, o'qituvchi va auditoriya.", "access": "Barcha bo'limlar"},
    {"key": "oqituvchilar", "title": "O'qituvchilar ro'yxati", "owner": "kadrlar", "icon": "user", "fn": ds_oqituvchilar,
     "desc": "Professor-o'qituvchilar: kafedra, lavozim, ilmiy daraja, o'quv yuklamasi.", "access": "Barcha bo'limlar · maosh va pasportsiz"},
    {"key": "kontrakt", "title": "Kontrakt to'lovlari holati", "owner": "buxgalteriya", "icon": "money", "fn": ds_kontrakt,
     "desc": "Guruhlar kesimida shartnoma summasi, to'langan va qarz, to'lov foizi.", "access": "Kontrakt ma'lumotiga ruxsati bor lavozimlar"},
    {"key": "auditoriyalar", "title": "Auditoriyalar fondi", "owner": "xojalik", "icon": "camera", "fn": ds_auditoriyalar,
     "desc": "Xonalar, sig'imi, jihozlar soni va dars jadvali bo'yicha haftalik bandlik.", "access": "Barcha bo'limlar"},
    {"key": "tuzilma", "title": "Fakultet va kafedralar", "owner": "akademik", "icon": "folder", "fn": ds_tuzilma,
     "desc": "Kafedralar, mudirlar, o'qituvchilar, guruhlar va talabalar soni.", "access": "Barcha bo'limlar"},
    {"key": "hamkorlar", "title": "Xalqaro hamkorlar", "owner": "xalqaro", "icon": "globe", "fn": ds_hamkorlar,
     "desc": "Hamkor OTMlar bilan shartnomalar: dastur, amal qilish muddati, almashinuv.", "access": "Barcha bo'limlar"},
    {"key": "nashrlar", "title": "Ilmiy nashrlar", "owner": "ilmiy_bolim", "icon": "book", "fn": ds_nashrlar,
     "desc": "Scopus, Web of Science, OAK jurnallari va konferensiya tezislari.", "access": "Barcha bo'limlar"},
    {"key": "qabul", "title": "Qabul statistikasi", "owner": "qabul", "icon": "cap", "fn": ds_qabul,
     "desc": "2026 qabul: yo'nalishlar bo'yicha arizalar, tavsiya va o'rtacha ball.", "access": "Barcha bo'limlar · jamlangan"},
]
DS = {d["key"]: d for d in DATASETS}

def _ds_count(con, sql, a) -> int:
    return con.execute(f"SELECT COUNT(*) FROM ({sql})", a).fetchone()[0]

def datasets(c: Ctx) -> dict:
    um = unit_map(_con)
    meta = {r["key"]: r for r in db.rows(_con, "SELECT * FROM portal_datasets")}
    out = []
    for d in DATASETS:
        m = meta.get(d["key"]) or {}
        it = {"key": d["key"], "title": d["title"], "owner": d["owner"], "owner_name": _uname(um, d["owner"]), "icon": d["icon"], "desc": d["desc"],
              "access": d["access"], "updated_at": m.get("updated_at"), "views": m.get("views") or 0, "own": d["owner"] == my_unit(c)}
        try:
            cols, sql, a, mode, note = d["fn"](_con, c)
            it.update(mode=mode, rows=_ds_count(_con, sql, a), cols=len(cols))
        except AccessDenied as e:
            it.update(mode="yopiq", rows=None, reason=str(e).replace("⛔ ", ""))
        out.append(it)
    return {"items": out, "unit": my_unit(c)}

def dataset_view(c: Ctx, key: str, q="", offset=0, limit=100) -> dict:
    d = DS.get(key)
    if not d: raise HTTPException(404, "Baza topilmadi")
    try:
        cols, sql, a, mode, note = d["fn"](_con, c, q)
    except AccessDenied:
        _audit(c, f"portal: umumiy baza — {d['title']}", False)
        raise
    _audit(c, f"portal: umumiy baza — {d['title']}", True, f"q={q[:40]}" if q else "")
    total = _ds_count(_con, sql, a)
    offset = max(0, int(offset)); limit = max(1, min(200, int(limit)))
    rows = [list(r) for r in _con.execute(f"{sql} LIMIT ? OFFSET ?", (*a, limit, offset)).fetchall()]
    if not offset and not q:
        _con.execute("INSERT INTO portal_datasets(key,updated_at,views) VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET views=views+1", (key, _now()))
        _con.commit()
    um = unit_map(_con)
    m = db.one(_con, "SELECT * FROM portal_datasets WHERE key=?", (key,)) or {}
    return {"key": key, "title": d["title"], "owner": d["owner"], "owner_name": _uname(um, d["owner"]), "desc": d["desc"], "access": d["access"],
            "updated_at": m.get("updated_at"), "cols": cols, "rows": rows, "total": total, "offset": offset, "limit": limit, "mode": mode, "note": note}

def dataset_csv(c: Ctx, key: str, q="") -> tuple[str, bytes]:
    d = DS.get(key)
    if not d: raise HTTPException(404, "Baza topilmadi")
    try:
        cols, sql, a, mode, note = d["fn"](_con, c, q)
    except AccessDenied:
        _audit(c, f"portal: CSV eksport — {d['title']}", False)
        raise
    rows = _con.execute(f"{sql} LIMIT 50000", a).fetchall()
    _audit(c, f"portal: CSV eksport — {d['title']}", True, f"{len(rows)} qator")
    _con.execute("INSERT INTO portal_datasets(key,updated_at,exports) VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET exports=exports+1", (key, _now()))
    _con.commit()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([x.lstrip("#") for x in cols])
    for r in rows: w.writerow(["" if v is None else v for v in r])
    return f"{key}_{_today()}.csv", ("﻿" + buf.getvalue()).encode("utf-8")

# ---------------------------------------------------------------------------------------------
# Rahbariyat paneli uchun qisqa xulosa
# ---------------------------------------------------------------------------------------------
def summary(c: Ctx) -> dict:
    d = counts(_con, c)
    d["unit_name"] = _uname(unit_map(_con), d["unit"])
    return d

# ---------------------------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx:
    try:
        _con.execute("SELECT 1 FROM portal_meta LIMIT 1")
        _con.execute("SELECT 1 FROM org_units LIMIT 1")
    except Exception:          # baza qayta seed qilingan (server to'xtatilmagan) — jadvallar va namuna qayta tiklanadi
        _UNITS_CACHE.clear(); _CNT.clear()
        init(_con)
    return _ctx(request)

@router.get("/api/portal/units")
def api_units(request: Request):
    c = C(request); me = my_unit(c)
    return {"me": me, "groups": [{"key": k, "name": n} for k, n in GROUPS], "units": units(_con), "kinds": KINDS, "prios": PRIOS,
            "leader": is_leader(c), "can_resolve": c.role.key in RESOLVERS, "curated": curated(c), "is_head": is_head(c),
            "members": [{**m, "me": m["id"] == c.user["id"]} for m in members(_con, me)]}

@router.get("/api/portal/summary")
def api_summary(request: Request):
    return summary(C(request))

@router.get("/api/portal/threads")
def api_threads(request: Request, box: str = "inbox", q: str = "", flt: str = "all", offset: int = 0, limit: int = PAGE):
    return list_threads(C(request), box, q, flt, offset, limit)

@router.get("/api/portal/threads/{tid}")
def api_thread(tid: int, request: Request):
    return thread_detail(C(request), tid)

@router.post("/api/portal/threads")
def api_create(body: ThreadIn, request: Request):
    c = C(request)
    tid = create_thread(_con, c, body)
    t = db.one(_con, "SELECT ref_no, subject FROM portal_threads WHERE id=?", (tid,))
    _audit(c, "portal: xat yuborildi", True, f"{t['ref_no']} → {', '.join(body.to)[:120]} · {t['subject']}")
    return {"ok": True, "id": tid, "ref_no": t["ref_no"]}

@router.post("/api/portal/threads/{tid}/reply")
def api_reply(tid: int, body: ReplyIn, request: Request):
    c = C(request)
    mid = reply(_con, c, tid, body)
    _audit(c, "portal: javob yuborildi", True, _thread(_con, tid)["ref_no"])
    return {"ok": True, "id": mid}

@router.post("/api/portal/threads/{tid}/resolve")
def api_resolve(tid: int, body: ResolveIn, request: Request):
    c = C(request)
    rid = resolve(_con, c, tid, body)
    _audit(c, "portal: rezolyutsiya qo'yildi", True, f"{_thread(_con, tid)['ref_no']} → {', '.join(body.units)[:120]}" + (f" · muddat {body.due}" if body.due else ""))
    return {"ok": True, "id": rid}

@router.post("/api/portal/threads/{tid}/resolutions/{rid}/close")
def api_res_close(tid: int, rid: int, request: Request):
    c = C(request)
    close_resolution(_con, c, tid, rid)
    _audit(c, "portal: rezolyutsiya nazoratdan yechildi", True, f"{_thread(_con, tid)['ref_no']} #{rid}")
    return {"ok": True}

@router.post("/api/portal/threads/{tid}/assign")
def api_assign(tid: int, body: AssignIn, request: Request):
    c = C(request)
    u = assign(_con, c, tid, body.user_id)
    _audit(c, "portal: ijrochi tayinlandi" if u else "portal: ijrochi olib tashlandi", True, f"{_thread(_con, tid)['ref_no']} → {_brief(u['full_name']) if u else '—'}")
    return {"ok": True, "assignee": _brief(u["full_name"]) if u else None}

@router.post("/api/portal/threads/{tid}/forward")
def api_forward(tid: int, body: ForwardIn, request: Request):
    c = C(request)
    to = forward(_con, c, tid, body)
    _audit(c, "portal: xat yo'naltirildi", True, f"{_thread(_con, tid)['ref_no']} → {', '.join(to)}")
    return {"ok": True, "units": to}

@router.post("/api/portal/threads/{tid}/close")
def api_close(tid: int, body: NoteIn, request: Request):
    c = C(request)
    close_thread(_con, c, tid, body.note)
    _audit(c, "portal: yozishma yopildi", True, _thread(_con, tid)["ref_no"])
    return {"ok": True}

@router.post("/api/portal/threads/{tid}/reopen")
def api_reopen(tid: int, request: Request):
    c = C(request)
    reopen_thread(_con, c, tid)
    _audit(c, "portal: yozishma qayta ochildi", True, _thread(_con, tid)["ref_no"])
    return {"ok": True}

@router.post("/api/portal/threads/{tid}/archive")
def api_archive(tid: int, body: ArchiveIn, request: Request):
    archive(_con, C(request), tid, body.on)
    return {"ok": True, "archived": body.on}

@router.get("/api/portal/drafts")
def api_drafts(request: Request):
    return drafts(C(request))

@router.put("/api/portal/drafts")
def api_draft_save(body: DraftIn, request: Request):
    return save_draft(_con, C(request), body)

@router.delete("/api/portal/drafts/{did}")
def api_draft_del(did: int, request: Request):
    c = C(request)
    n = _con.execute("DELETE FROM portal_drafts WHERE id=? AND user_id=?", (did, c.user["id"])).rowcount; _con.commit(); _bump()
    if not n: raise HTTPException(404, "Qoralama topilmadi")
    return {"ok": True}

@router.get("/api/portal/templates")
def api_templates(request: Request):
    return templates(C(request))

@router.post("/api/portal/templates")
def api_template_add(body: TemplateIn, request: Request):
    c = C(request)
    tid = save_template(_con, c, body)
    _audit(c, "portal: shablon saqlandi", True, body.title[:80])
    return {"ok": True, "id": tid}

@router.delete("/api/portal/templates/{tid}")
def api_template_del(tid: int, request: Request):
    c = C(request)
    t = db.one(_con, "SELECT * FROM portal_templates WHERE id=?", (tid,))
    if not t: raise HTTPException(404, "Shablon topilmadi")
    if t["owner_unit"] != my_unit(c):
        _audit(c, "portal: shablonni o'chirish", False, t["title"])
        raise AccessDenied("⛔ Faqat o'z bo'limingiz shablonini o'chirish mumkin.")
    _con.execute("DELETE FROM portal_templates WHERE id=?", (tid,)); _con.commit()
    _audit(c, "portal: shablon o'chirildi", True, t["title"])
    return {"ok": True}

@router.post("/api/portal/templates/{tid}/use")
def api_template_use(tid: int, request: Request):
    c = C(request)
    _con.execute("UPDATE portal_templates SET uses=COALESCE(uses,0)+1 WHERE id=? AND owner_unit IN ('*', ?)", (tid, my_unit(c))); _con.commit()
    return {"ok": True}

@router.get("/api/portal/reminders")
def api_reminders(request: Request):
    c = C(request)
    return {"items": reminders_for(_con, c.user)}

@router.get("/api/portal/files")
def api_files(request: Request, q: str = "", unit: str = "", cat: str = "", scope: str = "all"):
    return list_files(C(request), q, unit, cat, scope if scope in ("all", "mine", "shared") else "all")

@router.post("/api/portal/files")
async def api_upload(request: Request, name: str, category: str = "Boshqa", share: str = "", note: str = ""):
    c = C(request)
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BYTES:
        _audit(c, "portal: fayl yuklash", False, f"{name[:80]} — hajm {int(cl) // 1024} KB")
        raise HTTPException(413, f"Fayl hajmi {MAX_BYTES // (1024 * 1024)} MB dan oshmasligi kerak")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_BYTES:
            raise HTTPException(413, f"Fayl hajmi {MAX_BYTES // (1024 * 1024)} MB dan oshmasligi kerak")
    try:
        r = store_file(_con, c, name, bytes(buf), category, [s for s in share.split(",") if s], note)
    except HTTPException as e:
        if e.status_code == 415: _audit(c, "portal: fayl rad etildi", False, f"{name[:80]} — {e.detail}")
        raise
    _audit(c, "portal: fayl yuklandi", True, f"{r['name']} (v{r['version']}, {r['size'] // 1024} KB, {r['scan']}) → {share or 'faqat o‘z bo‘limi'}")
    return {"ok": True, **r}

@router.get("/api/portal/files/{fid}/download")
def api_download(fid: int, request: Request):
    c = C(request)
    f = db.one(_con, "SELECT * FROM portal_files WHERE id=?", (fid,))
    if not f: raise HTTPException(404, "Fayl topilmadi")
    ok = can_see_file(_con, c, f)
    _audit(c, "portal: fayl yuklab olindi", ok, f"{f['name']} (v{f['version']})")
    if not ok:
        raise AccessDenied("⛔ Bu fayl sizning bo'limingizga ulashilmagan. So'rov audit jurnaliga yozildi.")
    p = file_path(f)
    _con.execute("UPDATE portal_files SET downloads=downloads+1 WHERE id=?", (fid,)); _con.commit()
    return FileResponse(p, filename=f["name"], media_type=f.get("mime") or mimetypes.guess_type(f["name"])[0] or "application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.delete("/api/portal/files/{fid}")
def api_file_delete(fid: int, request: Request):
    """Faylni (shu versiyani) o'chirish: yuklagan xodim yoki o'z bo'limi rahbari. Xatga ilova qilingan fayl o'chirilmaydi — yozishma yaxlitligi."""
    c = C(request)
    f = db.one(_con, "SELECT * FROM portal_files WHERE id=?", (fid,))
    if not f or not can_see_file(_con, c, f): raise HTTPException(404, "Fayl topilmadi")
    if not (f["uploader_id"] == c.user["id"] or (f["owner_unit"] == my_unit(c) and is_head(c))):
        _audit(c, "portal: faylni o'chirish", False, f["name"])
        raise AccessDenied("⛔ Faylni faqat uni yuklagan xodim yoki bo'lim rahbari o'chiradi.")
    if _con.execute("SELECT 1 FROM portal_attach WHERE file_id=?", (fid,)).fetchone():
        raise HTTPException(409, "Fayl xatga ilova qilingan — yozishma yaxlitligi uchun o'chirilmaydi")
    _con.execute("DELETE FROM portal_shares WHERE file_id=?", (fid,))
    _con.execute("DELETE FROM portal_files WHERE id=?", (fid,))
    if f["latest"]:     # oldingi versiya yana "oxirgi" bo'ladi
        _con.execute("""UPDATE portal_files SET latest=1 WHERE id=(SELECT id FROM portal_files WHERE owner_unit=? AND lower(name)=lower(?)
                        ORDER BY version DESC LIMIT 1)""", (f["owner_unit"], f["name"]))
    _con.commit()
    try: file_path(f).unlink()
    except HTTPException: pass
    _audit(c, "portal: fayl o'chirildi", True, f"{f['name']} (v{f['version']})")
    return {"ok": True}

@router.get("/api/portal/files/{fid}/versions")
def api_versions(fid: int, request: Request):
    c = C(request)
    f = db.one(_con, "SELECT * FROM portal_files WHERE id=?", (fid,))
    if not f or not can_see_file(_con, c, f): raise HTTPException(404, "Fayl topilmadi")
    vs = db.rows(_con, "SELECT id, version, size, created_at, uploader_name, note FROM portal_files WHERE owner_unit=? AND lower(name)=lower(?) ORDER BY version DESC",
                 (f["owner_unit"], f["name"]))
    return [{**v, "uploader": _short(v.pop("uploader_name"))} for v in vs]

@router.get("/api/portal/datasets")
def api_datasets(request: Request):
    return datasets(C(request))

@router.get("/api/portal/datasets/{key}")
def api_dataset(key: str, request: Request, q: str = "", offset: int = 0):
    return dataset_view(C(request), key, q, offset)

@router.get("/api/portal/datasets/{key}/csv")
def api_dataset_csv(key: str, request: Request, q: str = ""):
    fn, data = dataset_csv(C(request), key, q)
    return Response(data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{fn}"'})

# ---------------------------------------------------------------------------------------------
# Demo namunasi: haqiqiy ochiladigan fayllar (docx / xlsx / pdf / txt) va yozishmalar
# ---------------------------------------------------------------------------------------------
def _xlsx(sheet: str, header: list, rows: list) -> bytes:
    """Minimal, Excel/LibreOffice ochadigan .xlsx (kutubxonasiz)."""
    def col(i):
        s = ""
        i += 1
        while i: i, r = divmod(i - 1, 26); s = chr(65 + r) + s
        return s
    def cell(v, ref, st=0):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f'<c r="{ref}"{f" s=\"{st}\"" if st else ""}><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"{f" s=\"{st}\"" if st else ""}><is><t xml:space="preserve">{_xe(str(v if v is not None else ""))}</t></is></c>'
    xr = []
    for ri, r in enumerate([header] + rows, 1):
        xr.append(f'<row r="{ri}">' + "".join(cell(v, f"{col(ci)}{ri}", 1 if ri == 1 else 0) for ci, v in enumerate(r)) + "</row>")
    widths = [max(len(str(r[i])) if i < len(r) and r[i] is not None else 0 for r in [header] + rows) for i in range(len(header))]
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(60, max(8, w + 2))}" customWidth="1"/>' for i, w in enumerate(widths))
    ws = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
          f'<cols>{cols}</cols><sheetData>{"".join(xr)}</sheetData></worksheet>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FFF6E6ED"/><bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{_xe(sheet[:31])}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", ws)
        z.writestr("xl/styles.xml", styles)
    return b.getvalue()

def _pdf(title: str, lines: list[str]) -> bytes:
    """Minimal bir/ko'p sahifali PDF (Helvetica, WinAnsi) — kutubxonasiz."""
    def enc(s):
        s = str(s).replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'").replace("—", "-").replace("–", "-").replace("№", "No").replace("«", '"').replace("»", '"')
        s = s.encode("cp1252", "replace").decode("latin-1")
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    wrapped = []
    for ln in lines:
        if not ln: wrapped.append(""); continue
        bold = ln.startswith("**")
        t = ln[2:] if bold else ln
        while len(t) > 92:
            cut = t.rfind(" ", 0, 92)
            cut = cut if cut > 40 else 92
            wrapped.append(("**" if bold else "") + t[:cut]); t = t[cut:].lstrip()
        wrapped.append(("**" if bold else "") + t)
    per = 46
    pages = [wrapped[i:i + per] for i in range(0, max(1, len(wrapped)), per)] or [[]]
    objs = []   # 1 catalog, 2 pages, 3 font, 4 bold font, then (page, content) pairs
    kids = []
    for pi, pl in enumerate(pages):
        ops = ["BT", "/F2 15 Tf", "56 790 Td", f"({enc('ISFT INSTITUTI')}) Tj", "/F1 9 Tf", "0 -14 Td",
               f"({enc('International School of Finance and Technology · Toshkent viloyati, Qibray tumani')}) Tj", "ET",
               "0.53 0 0.22 RG 1.2 w 56 768 m 539 768 l S"]
        y = 744
        if pi == 0:
            ops += ["BT", "/F2 13 Tf", f"56 {y} Td", f"({enc(title)}) Tj", "ET"]; y -= 26
        for ln in pl:
            bold = ln.startswith("**")
            ops += ["BT", f"/{'F2' if bold else 'F1'} 10.5 Tf", f"56 {y} Td", f"({enc(ln[2:] if bold else ln)}) Tj", "ET"]; y -= 15
        ops += ["BT", "/F1 8 Tf", "56 40 Td", f"({enc(f'ISFT Core · Bo`limlararo portal · {pi + 1}/{len(pages)}-sahifa'.replace('`', chr(39)))}) Tj", "ET"]
        stream = "\n".join(ops).encode("latin-1")
        kids.append(len(objs) + 5)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {len(objs) + 6} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    head = [b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    allo = head + objs
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offs = []
    for i, o in enumerate(allo, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(allo) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    out += f"trailer\n<< /Size {len(allo) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return bytes(out)

def _docx(title: str, paras: list, table: tuple | None = None, sign: str = "") -> bytes:
    from docx import Document
    from docx.shared import Pt
    d = Document()
    st = d.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(12)
    h = d.add_paragraph(); r = h.add_run("ISFT INSTITUTI"); r.bold = True; r.font.size = Pt(14)
    d.add_paragraph("International School of Finance and Technology").runs[0].font.size = Pt(9)
    t = d.add_paragraph(); r = t.add_run(title); r.bold = True; r.font.size = Pt(13)
    for p in paras:
        if p.startswith("**"): d.add_paragraph().add_run(p[2:]).bold = True
        elif p.startswith("- "): d.add_paragraph(p[2:], style="List Bullet")
        else: d.add_paragraph(p)
    if table:
        hdr, rows = table
        tb = d.add_table(rows=1, cols=len(hdr)); tb.style = "Table Grid"
        for i, x in enumerate(hdr):
            tb.rows[0].cells[i].text = ""; tb.rows[0].cells[i].paragraphs[0].add_run(str(x)).bold = True
        for row in rows:
            cs = tb.add_row().cells
            for i, x in enumerate(row): cs[i].text = str(x)
    if sign:
        d.add_paragraph(); d.add_paragraph(sign)
    b = io.BytesIO(); d.save(b); return b.getvalue()

def _mln(x): return f"{(x or 0) / 1e6:,.1f}".replace(",", " ") + " mln"

def seed(con, force=False):
    if not force:
        if db.one(con, "SELECT v FROM portal_meta WHERE k='seed'"): return
        if con.execute("SELECT COUNT(*) FROM portal_threads").fetchone()[0] or con.execute("SELECT COUNT(*) FROM portal_files").fetchone()[0]:
            con.execute("INSERT OR REPLACE INTO portal_meta(k,v) VALUES('seed',?)", (SEED_TAG,)); con.commit(); return
    if not db.one(con, "SELECT 1 x FROM users"): return     # baza hali seed qilinmagan
    for t in ("portal_threads", "portal_recipients", "portal_msgs", "portal_reads", "portal_attach", "portal_files", "portal_shares", "portal_datasets",
              "portal_user_reads", "portal_watchers", "portal_hidden", "portal_resolutions", "portal_drafts", "portal_templates", "portal_reminders"):
        con.execute(f"DELETE FROM {t}")
    if FTS_OK[0]: con.execute("DELETE FROM portal_fts")
    if FILES.exists() and FILES.resolve() == DEFAULT_FILES.resolve():
        shutil.rmtree(FILES, ignore_errors=True)
    elif FILES.exists():          # tashqi papka (volume): faqat portal fayl nomlari (uuid.ext) o'chiriladi
        for f in FILES.iterdir():
            if f.is_file() and re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]{2,5}", f.name): f.unlink(missing_ok=True)
    FILES.mkdir(parents=True, exist_ok=True)
    um = unit_map(con)
    users_by_unit = {}
    for u in db.rows(con, "SELECT * FROM users ORDER BY id"):
        if u["role"] not in ROLES: continue
        k = unit_key(u)
        cur = users_by_unit.get(k)
        if not cur or (u["role"] in HEAD_ROLES and cur["role"] not in HEAD_ROLES): users_by_unit[k] = u
    def cx(unit, role=None, who=None):
        u = db.one(con, "SELECT * FROM users WHERE full_name LIKE ? ORDER BY id LIMIT 1", (f"%{who}%",)) if who else None
        if u and u["role"] in ROLES and unit_key(u) == unit: return Ctx(u, ROLES[u["role"]])
        if role:
            u = db.one(con, "SELECT * FROM users WHERE role=? ORDER BY id LIMIT 1", (role,))
        else:
            u = users_by_unit.get(unit)
        return Ctx(u, ROLES[u["role"]]) if u else None
    now = dt.datetime.now().replace(microsecond=0, second=0)
    def ago(h): return (now - dt.timedelta(hours=h)).isoformat(timespec="seconds")
    def day(n): return (S.TODAY + dt.timedelta(days=n)).isoformat()
    kafs = [k for k in um if k.startswith("kaf")]
    faks = [k for k in um if k.startswith("fak")]

    # ---------- fayllar (haqiqiy mazmun — bazadagi raqamlardan) ----------
    F = {}
    def put(key, unit, name, data, cat, share, note, h, role=None, who=None):
        c = cx(unit, role, who)
        if not c or unit not in um: return
        r = store_file(con, c, name, data, cat, share, note, ago(h), owner_unit=unit)
        F[key] = r["id"]
    by_fac = db.rows(con, """SELECT f.name fak, COUNT(s.id) n, SUM(s.status='faol') faol, SUM(s.payment_type='kontrakt') k, SUM(s.payment_type='grant') g
                            FROM faculties f LEFT JOIN students s ON s.faculty_id=f.id GROUP BY f.id ORDER BY f.id""")
    by_form = db.rows(con, "SELECT study_form, level, COUNT(*) n FROM students GROUP BY 1, 2 ORDER BY 3 DESC")
    put("kont", "talabalar", "Kontingent_hisobot_noyabr_2026.xlsx",
        _xlsx("Kontingent", ["Fakultet", "Jami talabalar", "Faol", "Kontrakt", "Grant"],
              [[r["fak"], r["n"], r["faol"], r["k"], r["g"]] for r in by_fac] + [["JAMI", sum(r["n"] for r in by_fac), sum(r["faol"] for r in by_fac),
                                                                                  sum(r["k"] for r in by_fac), sum(r["g"] for r in by_fac)]]),
        "Hisobotlar", ["rektorat", "prorektor_oquv", "akademik"], "1-noyabr holatiga fakultetlar kesimida kontingent", 30)
    ct = db.one(con, "SELECT SUM(contract_amount) t, SUM(paid_amount) p, SUM(contract_amount>paid_amount) d FROM students WHERE payment_type='kontrakt'")
    cf = db.rows(con, """SELECT f.name, SUM(contract_amount) t, SUM(paid_amount) p FROM students s JOIN faculties f ON f.id=s.faculty_id
                         WHERE payment_type='kontrakt' GROUP BY f.id ORDER BY f.id""")
    put("kontr", "buxgalteriya", "Kontrakt_tushumi_1-noyabr.pdf",
        _pdf("Kontrakt to'lovlari tushumi: 1-noyabr holatiga ma'lumotnoma",
             [f"Jami shartnoma summasi: {_mln(ct['t'])} so'm", f"To'langan: {_mln(ct['p'])} so'm ({100 * ct['p'] / max(ct['t'], 1):.1f}%)",
              f"Qarzdorlik: {_mln(ct['t'] - ct['p'])} so'm · qarzdor talabalar: {ct['d']} nafar", "", "**Fakultetlar kesimida:"] +
             [f"  {r['name']}: {_mln(r['p'])} / {_mln(r['t'])} so'm ({100 * r['p'] / max(r['t'], 1):.1f}%)" for r in cf] +
             ["", "Izoh: navbatdagi to'lov muddati - 1-dekabr. Qarzdorligi 50% dan oshgan guruhlar ro'yxati dekanatlarga alohida yuboriladi.", "",
              "Bosh buxgalter ______________________"]),
        "Moliyaviy", ["rektorat", "prorektor_moliya"], "Ma'lumotnoma, PDF", 27)
    sch = db.rows(con, """SELECT sc.weekday, sc.slot, g.name grp, sc.subject, t.full_name tch, r.name room FROM schedule sc LEFT JOIN groups_ g ON g.id=sc.group_id
                          LEFT JOIN teachers t ON t.id=sc.teacher_id LEFT JOIN rooms r ON r.id=sc.room_id ORDER BY sc.weekday, sc.slot, r.name LIMIT 160""")
    jrows = [[DAYS[x["weekday"]], f"{x['slot']}-para ({SLOTS.get(x['slot'], '')})", x["grp"], x["subject"], x["tch"], (x["room"] or "").split(" ·")[0]] for x in sch]
    put("jad", "akademik", "Dars_jadvali_bahorgi_semestr_loyiha.xlsx", _xlsx("Jadval", ["Kun", "Para", "Guruh", "Fan", "O'qituvchi", "Auditoriya"], jrows[:120]),
        "O'quv-uslubiy", ["*"], "Loyiha: kafedralar takliflari asosida tuzatiladi", 120)
    put("jad", "akademik", "Dars_jadvali_bahorgi_semestr_loyiha.xlsx", _xlsx("Jadval", ["Kun", "Para", "Guruh", "Fan", "O'qituvchi", "Auditoriya"], jrows),
        "O'quv-uslubiy", ["*"], "2-versiya: Buxgalteriya hisobi va Menejment kafedralari takliflari kiritildi", 20)
    put("yuk", "akademik", "Oquv_yuklama_shakli_2027.xlsx",
        _xlsx("Yuklama", ["Kafedra", "O'qituvchi", "Fan", "Guruh", "Ma'ruza (soat)", "Amaliy (soat)", "Jami"], [["", "", "", "", 0, 0, 0] for _ in range(3)]),
        "Shablonlar", ["*"], "Kafedralar to'ldiradigan shakl", 160)
    put("malaka", "kadrlar", "Malaka_oshirish_rejasi_shakli.docx",
        _docx("2027-yil uchun malaka oshirish rejasi (shakl)", ["Kafedra: ____________________", "Kafedra mudiri: ____________________",
              "Har bir professor-o'qituvchi uchun malaka oshirish yo'nalishi, muddati va tashkilotini ko'rsating."],
              (["№", "F.I.Sh.", "Lavozimi", "Yo'nalish", "Muddat", "Tashkilot"], [[i, "", "", "", "", ""] for i in range(1, 6)]),
              "Kadrlar bo'limi boshlig'i ______________"),
        "Shablonlar", kafs, "To'ldirib, 20-noyabrgacha qaytaring", 96)
    put("smeta", "xojalik", "Smeta_2-bino_isitish_tizimi.pdf",
        _pdf("2-o'quv binosi isitish tizimini ta'mirlash: smeta loyihasi",
             ["**Ish turlari:", "  1. Qozonxona nasoslarini almashtirish (2 dona) - 38,4 mln so'm", "  2. Quvurlarni yuvish va bosim sinovi - 12,0 mln so'm",
              "  3. Radiator klapanlarini almashtirish (64 dona) - 9,6 mln so'm", "  4. Avtomatik termoregulyator o'rnatish - 15,2 mln so'm", "",
              "**Jami: 75,2 mln so'm (QQS bilan)", "Bajarish muddati: 10 ish kuni. Darslar shanba-yakshanba kunlari to'xtatilmaydi.", "",
              "Xo'jalik va texnik bo'lim boshlig'i ______________"]),
        "Moliyaviy", ["prorektor_yoshlar", "rektorat", "buxgalteriya"], "Kommunal xarajatlar oshishi bo'yicha", 50)
    put("tartib", "kadrlar", "Ichki_mehnat_tartibi_qoidalari_2026.pdf",
        _pdf("Ichki mehnat tartibi qoidalari (2026-yil tahriri)",
             ["**1. Umumiy qoidalar", "Ushbu qoidalar ISFT institutining barcha xodimlari va professor-o'qituvchilari uchun majburiydir.", "",
              "**2. Ish vaqti", "Ish kuni 09:00 dan 18:00 gacha, tushlik 13:00-14:00. Dars mashg'ulotlari dars jadvaliga muvofiq.", "",
              "**3. Elektron hujjat aylanishi", "Bo'limlararo yozishmalar ISFT Core portali orqali yuritiladi; har bir xatga ro'yxat raqami beriladi.",
              "Javob muddati ko'rsatilgan xatlarga belgilangan muddatda javob beriladi.", "",
              "**4. Axborot xavfsizligi", "Talabalar va xodimlarning shaxsiy ma'lumotlari faqat xizmat maqsadida ishlatiladi.",
              "Barcha so'rovlar audit jurnalida qayd etiladi."]),
        "Buyruq va me'yoriy hujjatlar", ["*"], "Rektor buyrug'i bilan tasdiqlangan", 400)
    put("kochir", "talabalar", "Buyruq_loyihasi_talaba_kochirish_namuna.docx",
        _docx("Talabani boshqa ta'lim yo'nalishiga ko'chirish to'g'risida (buyruq loyihasi namunasi)",
              ["Asos: talabaning arizasi, dekanat taqdimnomasi va akademik farqlar jadvali.", "**BUYURAMAN:",
               "1. ________ guruh talabasi ________ ni 2026-2027 o'quv yilining kuzgi semestridan ________ yo'nalishiga ko'chirilsin.",
               "2. Akademik farqlarni topshirish muddati - 2027-yil 1-fevral.", "3. Buyruq ijrosini nazorat qilish Registrator ofisi zimmasiga yuklansin."],
              sign="Rektor ______________ " + (cx("rektorat") and _short(cx("rektorat").user["full_name"]) or "")),
        "Shablonlar", faks, "Dekanatlar uchun namuna", 200)
    pr = db.rows(con, "SELECT name, country, kind, expires, students_exchanged FROM partners WHERE status='faol' ORDER BY expires LIMIT 8")
    put("erasmus", "xalqaro", "Erasmus_KA171_nomzodlar_royxati.xlsx",
        _xlsx("Nomzodlar", ["№", "Hamkor OTM", "Davlat", "Dastur", "O'rinlar", "Tanlov holati"],
              [[i, p["name"], p["country"], p["kind"], max(1, (p["students_exchanged"] or 2) // 2), "hujjatlar qabul qilinmoqda"] for i, p in enumerate(pr, 1)]),
        "Hisobotlar", ["rektorat", "prorektor_ilmiy"], "Ichki tanlov, 2027 bahorgi mobillik", 70)
    put("hemis", "it", "HEMIS_texnik_ishlar_yoriqnoma.txt",
        ("HEMIS TIZIMIDA REJALASHTIRILGAN TEXNIK ISHLAR\n\nVaqti: shanba, 22:00 - yakshanba, 02:00\nTa'sir: HEMIS, LMS va ISFT Core bilan sinxronlash vaqtincha to'xtaydi.\n\n"
         "Bo'limlarga tavsiya:\n1. Baholar va davomatni shanba 20:00 gacha kiriting.\n2. Texnik ishlar paytida eksport qilingan fayllarni o'zgartirmang.\n"
         "3. Muammo bo'lsa: Axborot texnologiyalari bo'limi, ichki tel. 105.\n").encode("utf-8"),
        "Buyruq va me'yoriy hujjatlar", ["*"], "Yo'riqnoma", 44, role="it_head")
    put("tezis", "ilmiy_bolim", "Konferensiya_tezis_talablari.docx",
        _docx("«Raqamli iqtisodiyot va moliya: zamonaviy yondashuvlar» ilmiy-amaliy konferensiyasi",
              ["Konferensiya 2026-yil dekabr oyida ISFT institutida bo'lib o'tadi.", "**Tezislarga talablar:",
               "- Hajmi: 3-5 sahifa, Times New Roman 14, interval 1,5", "- Tillar: o'zbek, rus, ingliz", "- Annotatsiya va kalit so'zlar (5-7 ta)",
               "- Adabiyotlar ro'yxati APA uslubida", "Tezislar kafedra mudiri orqali Ilmiy tadqiqotlar bo'limiga yuboriladi."]),
        "O'quv-uslubiy", kafs + ["prorektor_ilmiy"], "Barcha kafedralar uchun", 140)
    put("monit", "akademik", "Dars_monitoringi_noyabr_1-hafta.pdf",
        _pdf("Dars mashg'ulotlari monitoringi: noyabr, 1-hafta",
             ["Monitoring 3 fakultetning 42 ta dars mashg'ulotida o'tkazildi.", "", "**Asosiy natijalar:",
              "  - Darsning o'z vaqtida boshlanishi: 93%", "  - Auditoriya jihozlari soz: 88% (proyektor nosozligi - 5 ta xona)",
              "  - Davomat o'rtacha: 86%; sirtqi guruhlarda 71%", "  - 4 ta dars jadvaldan tashqari xonada o'tkazilgan", "",
              "**Takliflar:", "  1. Sirtqi guruhlar uchun masofaviy darslar ulushini oshirish.",
              "  2. Xo'jalik bo'limiga proyektorlarni almashtirish bo'yicha topshiriq berish.", "",
              "Akademik faoliyatni boshqarish bo'limi"]),
        "Hisobotlar", ["rektorat", "prorektor_oquv"], "Haftalik monitoring", 9)
    ri = UNIT_INFO["talabalar"]
    put("regxizmat", "talabalar", "Registrator_ofisi_murojaat_tartibi.pdf",
        _pdf("Registrator ofisi: murojaatlar qabul qilish tartibi",
             ["**Joylashuv: " + ri["place"], "Qabul vaqti: dushanba-juma, 09:00-17:00 (tushlik 13:00-14:00)", "",
              "**Registrator ofisi quyidagi masalalarni hal qiladi:"] + [f"  - {x}" for x in ri["does"]] +
             ["", "**Bo'limlar uchun:", "Talaba bo'yicha rasmiy so'rovlar ISFT Core portali orqali yuboriladi (ro'yxat raqami bilan).",
              "Kontingent bo'yicha statistika portaldagi «Talabalar kontingenti» umumiy bazasida — alohida so'rov shart emas.", "",
              "Registrator ofisi"]),
        "Buyruq va me'yoriy hujjatlar", ["*"], "Barcha bo'limlar va dekanatlar uchun", 210)
    put("kalendar", "akademik", "Akademik_kalendar_2026-2027.pdf",
        _pdf("2026-2027 o'quv yili akademik kalendari",
             ["**Kuzgi semestr", "  Darslar: 1-sentabr - 20-dekabr", "  Oraliq attestatsiya: 27-oktabr - 8-noyabr",
              "  Yakuniy nazorat (qishki sessiya): 22-dekabr - 17-yanvar", "  Qishki ta'til: 18-yanvar - 1-fevral", "",
              "**Bahorgi semestr", "  Fanlarga yozilish (enrollment): 1 - 15-dekabr", "  Akademik guruhlarni shakllantirish: 16 - 25-yanvar",
              "  Darslar: 2-fevral - 30-may", "  Yakuniy nazorat: 1 - 20-iyun", "  Yakuniy davlat attestatsiyasi (YDA): 22-iyun - 10-iyul", "",
              "Sirtqi ta'lim shakli uchun sessiya muddatlari Registrator ofisining Sirtqi bo'limi bilan alohida belgilanadi.", "",
              "Akademik faoliyatni boshqarish bo'limi"]),
        "Buyruq va me'yoriy hujjatlar", ["*"], "Ilmiy kengashda tasdiqlangan", 300)
    yn = db.rows(con, """SELECT g.name grp, sc.subject, MIN(t.full_name) tch FROM schedule sc JOIN groups_ g ON g.id=sc.group_id LEFT JOIN teachers t ON t.id=sc.teacher_id
                         GROUP BY g.id, sc.subject ORDER BY g.name LIMIT 60""")
    put("yanaz", "akademik", "Yakuniy_nazorat_jadvali_qishki_sessiya_loyiha.xlsx",
        _xlsx("Yakuniy nazorat", ["Sana", "Vaqt", "Guruh", "Fan", "Nazorat shakli", "Mas'ul o'qituvchi"],
              [[(S.TODAY + dt.timedelta(days=44 + (i % 18))).strftime("%d.%m.%Y"), ["09:00", "11:00", "14:00"][i % 3], r["grp"], r["subject"],
                ["yozma", "test", "og'zaki"][i % 3], r["tch"] or ""] for i, r in enumerate(yn)]),
        "O'quv-uslubiy", faks + ["imtihon"], "Loyiha — dekanatlar takliflari bilan yakunlanadi", 48)
    put("sirtqi", "sirtqi", "Sirtqi_sessiya_chaqiruv_xati_namuna.docx",
        _docx("Sirtqi ta'lim talabasini o'quv-imtihon sessiyasiga chaqiruv xati (namuna)",
              ["Hurmatli ________________________!", "Sizni 2026-2027 o'quv yilining qishki o'quv-imtihon sessiyasiga chaqiramiz.",
               "Sessiya muddati: ______________ dan ______________ gacha.", "Chaqiruv xati ish joyingizga taqdim etish uchun asos bo'ladi (O'zbekiston Respublikasi Mehnat kodeksi).",
               "Kontrakt to'lovi bo'yicha qarzdorligi bor talabalar sessiyaga qarzdorlikni bartaraf etgach qo'yiladi."],
              sign="Sirtqi bo'lim boshlig'i ______________ D. Shayzakova"),
        "Shablonlar", faks + ["akademik", "talabalar"], "Dekanatlar va Registrator ofisi uchun", 16, who="Shayzakova")
    t4 = db.rows(con, "SELECT full_name, position, load_hours FROM teachers WHERE department_id=4 ORDER BY id LIMIT 10")
    if "kaf4" in um:
        put("yukbh", "kaf4", "Yuklama_Buxgalteriya_hisobi_kafedrasi.xlsx",
            _xlsx("Yuklama", ["O'qituvchi", "Lavozim", "Bahorgi semestr (soat)"], [[t["full_name"], t["position"], t["load_hours"] // 2] for t in t4]),
            "Hisobotlar", ["akademik"], "Bahorgi semestr o'quv yuklamasi", 60)
    apps = db.rows(con, "SELECT direction, COUNT(*) n FROM applicants GROUP BY 1 ORDER BY 2 DESC LIMIT 6")
    put("qabul", "qabul", "Qabul_2027_marketing_rejasi.docx",
        _docx("2027 qabul kampaniyasi: marketing rejasi (loyiha)",
              ["2026 qabulida eng ko'p ariza tushgan yo'nalishlar asosida 2027 yil uchun reja tuzildi.", "**Asosiy kanallar:",
               "- Ochiq eshiklar kunlari (har oyning oxirgi shanbasi)", "- Maktab va litseylarda taqdimotlar (Toshkent viloyati, 40 ta)",
               "- Ijtimoiy tarmoqlar va Telegram kanal", "**Smeta loyihasi: 186 mln so'm"],
              (["Yo'nalish", "2026 arizalar", "2027 maqsad"], [[a["direction"], a["n"], int(a["n"] * 1.15)] for a in apps])),
        "Rejalar", ["rektorat", "buxgalteriya"], "Rektor ko'rib chiqishi uchun", 6)
    put("qarz", "prorektor_moliya", "Kontrakt_qarzdorlik_reja_shakli.xlsx",
        _xlsx("Reja", ["Guruh", "Qarzdorlar soni", "Qarz summasi", "Mas'ul (tyutor)", "Suhbat sanasi", "To'lov va'da sanasi"], [["", 0, 0, "", "", ""] for _ in range(5)]),
        "Shablonlar", faks + ["buxgalteriya"], "Dekanatlar to'ldiradi", 75)
    put("ishhaqi", "buxgalteriya", "Ish_haqi_fondi_oktabr_jamlanma.xlsx",
        _xlsx("Jamlanma", ["Bo'lim", "Xodimlar", "Ish haqi fondi (so'm)"],
              [[r["unit"], r["n"], r["fund"]] for r in db.rows(con, "SELECT unit, COUNT(*) n, SUM(salary) fund FROM staff GROUP BY unit ORDER BY fund DESC LIMIT 12")]),
        "Moliyaviy", [], "Ichki hujjat — faqat Buxgalteriya va rahbariyat", 100)

    # ---------- yozishmalar ----------
    def letter(frm, to, subj, body, kind="xat", prio="oddiy", due=None, h=24, files=(), read=(), replies=(), sender_seen=True, frm_role=None, who=None):
        c = cx(frm, frm_role, who)
        to = [u for u in to if u in um and u != frm]
        if not c or frm not in um or not to: return None
        tid = create_thread(con, c, ThreadIn(subject=subj, body=body, to=to, kind=kind, priority=prio, due=day(due) if due is not None else None,
                                             file_ids=[F[k] for k in files if k in F]), ts=ago(h))
        first = con.execute("SELECT MIN(id) FROM portal_msgs WHERE thread_id=?", (tid,)).fetchone()[0]
        for u in read:        # o'qilgan, lekin javob berilmagan
            if u not in to: continue
            rc = cx(u)
            con.execute("UPDATE portal_recipients SET status='o''qilgan', read_at=?, read_by=? WHERE thread_id=? AND unit=?",
                        (ago(max(0.2, h - 1.5)), rc.user["full_name"] if rc else "", tid, u))
            if rc: con.execute("INSERT OR REPLACE INTO portal_user_reads(thread_id,user_id,last_msg,read_at) VALUES(?,?,?,?)", (tid, rc.user["id"], first, ago(max(0.2, h - 1.5))))
        hh = h
        for rp in replies:
            u, txt, dh = rp[0], rp[1], rp[2]
            fk = rp[3] if len(rp) > 3 else ()
            rc = cx(u, None, rp[4] if len(rp) > 4 else None)
            if not rc or (u not in to and u != frm): continue
            hh = max(0.1, hh - dh)
            con.execute("UPDATE portal_recipients SET read_at=?, read_by=? WHERE thread_id=? AND unit=? AND read_at IS NULL", (ago(hh + 0.4), rc.user["full_name"], tid, u))
            reply(con, rc, tid, ReplyIn(body=txt, file_ids=[F[k] for k in fk if k in F]), ts=ago(hh))
        if sender_seen:
            mx = con.execute("SELECT MAX(id) FROM portal_msgs WHERE thread_id=?", (tid,)).fetchone()[0]
            con.execute("INSERT OR REPLACE INTO portal_user_reads(thread_id,user_id,last_msg,read_at) VALUES(?,?,?,?)", (tid, c.user["id"], mx, ago(max(0.05, hh - 0.2))))
        con.commit()
        return tid

    R = "rektorat"
    letter("talabalar", [R, "prorektor_oquv"], "Kuzgi semestr kontingenti: 1-noyabr holatiga hisobot",
           "Hurmatli Ibroxim Rustamovich!\n\n2026-2027 o'quv yili kuzgi semestri bo'yicha 1-noyabr holatiga talabalar kontingenti hisoboti ilova qilinmoqda. "
           "O'tgan oyga nisbatan akademik ta'tilga chiqqanlar soni ortgan, asosan sirtqi ta'lim shaklida.\n\nBatafsil ro'yxat «Umumiy bazalar → Talabalar kontingenti» bo'limida yangilandi.",
           "xat", "muhim", None, 29, files=["kont"], read=["prorektor_oquv"])
    letter("buxgalteriya", [R, "prorektor_moliya"], "Kontrakt to'lovlari tushumi: 1-noyabr holati",
           "Kontrakt to'lovlari bo'yicha 1-noyabr holatiga ma'lumotnoma ilova qilindi. Navbatdagi to'lov muddati — 1-dekabr. "
           "Qarzdorligi yuqori guruhlar bo'yicha dekanatlar bilan ishlash taklif etiladi.", "xabarnoma", "muhim", None, 26, files=["kontr"],
           replies=[("prorektor_moliya", "Qabul qilindi. Qarzdorligi 50% dan oshgan guruhlar ro'yxatini dekanatlar kesimida alohida tayyorlang, dushanbagacha.", 3)])
    letter(R, faks, "Qishki imtihon sessiyasiga tayyorgarlik to'g'risida",
           "Fakultet dekanlariga!\n\nQishki imtihon sessiyasiga tayyorgarlik bo'yicha quyidagilarni ta'minlang:\n1. Yakuniy nazorat jadvalini kafedralar bilan kelishib, Akademik faoliyatni boshqarish bo'limiga taqdim etish.\n"
           "2. Akademik qarzdor talabalar bilan individual ishlash rejasini tuzish.\n3. Kontrakt qarzdorligi bo'yicha talabalar ota-onalari bilan uchrashuvlar o'tkazish.\n\nNatijalar haqida ma'lumot bering.",
           "topshiriq", "muhim", 7, 52, read=[faks[0]] if faks else (),
           replies=[(faks[1], "Imtihon jadvali loyihasi tayyorlandi va kafedralar bilan kelishildi. Akademik qarzdorlar bilan suhbatlar 15-noyabrgacha yakunlanadi.", 20)] if len(faks) > 1 else (),
           sender_seen=False)
    letter("akademik", kafs, "Bahorgi semestr dars jadvali uchun o'quv yuklamalarini taqdim etish",
           "Kafedra mudirlariga!\n\nBahorgi semestr dars jadvalini shakllantirish uchun kafedrangiz o'quv yuklamasini ilova qilingan shaklda to'ldirib, belgilangan muddatda yuboring. "
           "Jadval loyihasi «Fayllar» bo'limida barcha uchun ochiq.", "sorov", "muhim", 3, 98, files=["yuk", "jad"],
           read=[k for k in kafs if k not in ("kaf1", "kaf4", "kaf3")][:3],
           replies=[("kaf4", "Kafedramiz yuklamasi ilova qilindi. 2 nafar o'qituvchi bahorda malaka oshirishda bo'ladi — jadvalda hisobga olishingizni so'raymiz.", 38, ["yukbh"]),
                    ("kaf1", "Yuklama shakli to'ldirildi, ertaga ilova qilamiz. Kompyuter sinflari bo'yicha alohida talabimiz bor: haftasiga 12 para.", 10)])
    letter("imtihon", ["talabalar"], "Akademik qarzdor talabalar ro'yxatini tasdiqlash",
           "Kuzgi semestr oraliq nazoratlari natijalariga ko'ra akademik qarzdor talabalar ro'yxati shakllantirildi. Ro'yxatni kontingent ma'lumotlari bilan solishtirib, tasdiqlab berishingizni so'raymiz.",
           "sorov", "shoshilinch", -2, 120, read=["talabalar"])
    letter("xalqaro", [R, "prorektor_ilmiy"], "Erasmus+ KA171: bahorgi mobillik uchun nomzodlar",
           "Polsha va Latviyadagi hamkor OTMlar bilan Erasmus+ KA171 dasturi bo'yicha 2027 bahorgi semestr uchun ichki tanlov e'lon qilindi. Nomzodlar ro'yxati ilova qilingan. Ko'rib chiqishingizni so'raymiz.",
           "xat", "oddiy", 10, 72, files=["erasmus"],
           replies=[(R, "Nomzodlar ro'yxatini o'quv ishlari prorektori bilan kelishing, akademik qarzdorligi bor talabalar tanlovga qo'yilmasin.", 30)])
    letter("it", [R, "talabalar", "akademik", "imtihon", "buxgalteriya"] + faks, "HEMIS tizimida rejalashtirilgan texnik ishlar (shanba 22:00–02:00)",
           "Hurmatli hamkasblar!\n\nShanba kuni 22:00 dan yakshanba 02:00 gacha HEMIS va LMS tizimlarida texnik ishlar o'tkaziladi. Bu vaqtda ISFT Core bilan sinxronlash to'xtaydi. "
           "Baholar va davomatni shanba 20:00 gacha kiritishingizni so'raymiz. Yo'riqnoma ilova qilingan.", "xabarnoma", "oddiy", None, 46, files=["hemis"],
           read=[R, "talabalar", "akademik", "imtihon"] + faks[:2], frm_role="it_head")
    letter("xojalik", ["prorektor_yoshlar", R], "2-o'quv binosi isitish tizimi: ta'mirlash smetasi",
           "2-o'quv binosida isitish tizimi bo'yicha talabalar murojaatlari ko'paydi. Nasoslarni almashtirish va quvurlarni yuvish bo'yicha smeta loyihasi ilova qilindi (75,2 mln so'm). "
           "Moliyalashtirishni tasdiqlashingizni so'raymiz.", "xat", "shoshilinch", 2, 49, files=["smeta"],
           replies=[("prorektor_yoshlar", "Smeta bilan tanishdim. Buxgalteriya bilan kelishilgan holda rektor tasdig'iga kiritaman. Ishlarni dam olish kunlarida bajarish rejasini ham yuboring.", 6)])
    letter("kadrlar", kafs, "2027-yil malaka oshirish rejasini taqdim etish",
           "Kafedra mudirlariga!\n\nProfessor-o'qituvchilarning 2027-yil uchun malaka oshirish rejasini ilova qilingan shaklda to'ldirib, 20-noyabrgacha yuboring.",
           "sorov", "oddiy", 12, 95, files=["malaka"], read=kafs[:2] + kafs[5:6])
    letter("prorektor_oquv", ["akademik", "imtihon", "talabalar"], "Akkreditatsiya: o'quv dasturlari va reyting nizomini yangilash",
           "Davlat akkreditatsiyasiga tayyorgarlik doirasida:\n— Akademik faoliyatni boshqarish bo'limi: o'quv dasturlarini yangilash rejasini;\n— Imtihon bo'limi: reyting nizomi loyihasini;\n"
           "— Registrator ofisi: kontingent harakati bo'yicha 3 yillik tahlilni tayyorlasin.", "topshiriq", "muhim", 12, 22, read=["akademik"], frm_role="prorektor_oquv")
    letter("qabul", [R, "buxgalteriya"], "2027 qabul kampaniyasi: marketing rejasi va smeta loyihasi",
           "2027 qabul kampaniyasi uchun marketing rejasi va smeta loyihasi tayyorlandi. Asosiy urg'u — Toshkent viloyati maktab va litseylari hamda ijtimoiy tarmoqlar. Ko'rib chiqib, tasdiqlashingizni so'raymiz.",
           "xat", "muhim", 5, 5, files=["qabul"])
    letter("kaf4", ["ilmiy_bolim"], "Scopus jurnallarida maqola chop etish rejasi (2027)",
           "Kafedramiz professor-o'qituvchilarining 2027-yilda Scopus va Web of Science jurnallarida maqola chop etish rejasi: 6 ta maqola, shundan 2 tasi xorijiy hammualliflar bilan. "
           "Chop etish to'lovlarini qoplash masalasida ko'mak so'raymiz.", "xat", "oddiy", None, 130,
           replies=[("ilmiy_bolim", "Rejangiz qabul qilindi. Chop etish xarajatlarini qoplash grant jamg'armasi hisobidan ko'rib chiqiladi — maqolalar qabul qilingach ariza yuboring.", 40)])
    letter("ilmiy_bolim", kafs, "Ilmiy-amaliy konferensiya: ma'ruza tezislarini yuborish",
           "Dekabr oyida «Raqamli iqtisodiyot va moliya: zamonaviy yondashuvlar» ilmiy-amaliy konferensiyasi o'tkaziladi. Har bir kafedradan kamida 3 ta tezis kutilmoqda. Talablar ilova qilingan.",
           "xabarnoma", "oddiy", 14, 3, files=["tezis"])
    letter("magistratura", [k for k in ("kaf2", "kaf4", "kaf7") if k in um], "Magistrlik dissertatsiyalari mavzularini tasdiqlash",
           "1-kurs magistrantlarining dissertatsiya mavzulari va ilmiy rahbarlarini kafedra yig'ilishida ko'rib chiqib, bayonnoma ko'chirmasini yuborishingizni so'raymiz.",
           "sorov", "oddiy", 6, 75, read=["kaf2"],
           replies=[("kaf4", "Mavzular kafedra yig'ilishida (bayonnoma №4) ko'rib chiqildi va tasdiqlandi. Ko'chirma qog'oz shaklda ham yuborildi.", 30)])
    letter("amaliyot", faks, "Malakaviy amaliyot: hamkor korxonalar ro'yxatini yangilash",
           "Bahorgi malakaviy amaliyot uchun hamkor korxonalar va tashkilotlar ro'yxatini yangilash zarur. Har bir fakultetdan yo'nalishlar kesimida takliflaringizni kutamiz.",
           "sorov", "oddiy", 8, 34, read=faks[:1])
    letter("talabalar", ["buxgalteriya"], "Akademik ta'tildan qaytgan talabalar kontraktini qayta hisoblash",
           "Akademik ta'tildan qaytgan 14 nafar talabaning kontrakt summasini joriy o'quv yili narxlari bo'yicha qayta hisoblashingizni so'raymiz. Ro'yxat «Umumiy bazalar»da mavjud.",
           "sorov", "oddiy", 4, 60, replies=[("buxgalteriya", "Qayta hisoblandi; 3 nafar talabada farq bor, ularga xabarnoma yuborildi.", 20)])
    if len(faks) > 1:
        letter(faks[1], ["talabalar"], "Ko'chirish (perevod) bo'yicha 3 nafar talaba hujjatlari",
               "Boshqa OTMdan ko'chirib o'tish istagini bildirgan 3 nafar talabaning hujjatlari dekanatda ko'rib chiqildi. Akademik farqlar jadvali bilan birga buyruq loyihasini tayyorlashingizni so'raymiz.",
               "xat", "muhim", 2, 4)
    letter("prorektor_moliya", faks + ["buxgalteriya"], "Kontrakt qarzdorligi bo'yicha guruhlar kesimida reja",
           "Dekanlarga!\n\nKontrakt qarzdorligi bo'yicha guruhlar kesimida reja ishlab chiqing: mas'ul tyutor, talaba bilan suhbat sanasi va to'lov va'da qilingan sana. Shakl ilova qilingan.",
           "topshiriq", "muhim", -1, 80, files=["qarz"], read=faks[2:3] + ["buxgalteriya"],
           replies=[(faks[1], "Reja to'ldirildi: 18 ta guruh, 214 nafar qarzdor. Tyutorlar suhbatlarni boshladi.", 30)] if len(faks) > 1 else (), frm_role="prorektor_moliya")
    letter(R, ["prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar", "akademik", "talabalar", "buxgalteriya"],
           "Rektorat yig'ilishi kun tartibi (dushanba, 10:00)",
           "Kun tartibi:\n1. Qishki sessiyaga tayyorgarlik (o'quv prorektori).\n2. Kontrakt tushumi prognozi (moliya prorektori).\n3. 2-bino isitish tizimi (yoshlar masalalari prorektori).\n"
           "4. Turli masalalar.\n\nMa'ruzachilar materiallarni yakshanba 18:00 gacha yuborsin.", "xabarnoma", "oddiy", None, 12,
           read=["prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "akademik", "buxgalteriya"], frm_role="kotib")
    letter("akademik", [R, "prorektor_oquv"], "Dars mashg'ulotlari monitoringi: noyabr 1-hafta natijalari",
           "Noyabr oyining 1-haftasida o'tkazilgan dars mashg'ulotlari monitoringi natijalari ilova qilindi. Sirtqi guruhlarda davomat past (71%) — chora ko'rish taklif etiladi.",
           "xat", "oddiy", None, 8, files=["monit"])
    letter("talabalar", ["akademik", "imtihon", "sirtqi", "malumotlar_bazasi"] + faks, "«Talabalar kontingenti» umumiy bazasi yangilandi",
           "Hurmatli hamkasblar! Ma'lumotlar bazasi bo'limi bilan birgalikda «Registrator» bazasi 1-noyabr holatiga yangilandi — portaldagi «Talabalar kontingenti» umumiy bazasi ham yangilandi. Ro'yxatlarni alohida so'rash shart emas — o'z ko'lamingizdagi ma'lumot portalda.",
           "xabarnoma", "oddiy", None, 28, read=["akademik", "imtihon"] + faks[:2])

    letter("akademik", faks + kafs, "Bahorgi semestr: fanlarga yozilish (enrollment) va akademik guruhlarni shakllantirish",
           "Hurmatli hamkasblar!\n\nAkademik kalendarga muvofiq bahorgi semestr uchun fanlarga yozilish 1-dekabrdan 15-dekabrgacha o'tkaziladi. Kafedralar tanlov fanlari ro'yxatini, "
           "dekanatlar esa talabalarni yozilish jarayoni bilan tanishtirishni 28-noyabrgacha ta'minlasin. Akademik guruhlar yozilish natijalari asosida shakllantiriladi.",
           "xabarnoma", "muhim", 9, 14, files=["kalendar"], read=faks[:2] + kafs[:4])
    letter("akademik", ["imtihon"] + faks, "Qishki sessiya: yakuniy nazorat jadvali loyihasi",
           "Qishki sessiya yakuniy nazorat jadvali loyihasi ilova qilindi. Dekanatlardan guruhlar kesimidagi takliflarni, Imtihon bo'limidan esa nazorat xonalari va kuzatuvchilar "
           "taqsimotini kutamiz.", "sorov", "muhim", 4, 47, files=["yanaz"], read=["imtihon"] + faks[2:3],
           replies=[(faks[0], "Jadval bo'yicha takliflarimiz: sirtqi guruhlar uchun nazoratlarni shanba kunlariga ko'chirish so'raladi (6 ta guruh).", 22)] if faks else ())
    letter("sirtqi", faks + ["buxgalteriya", "talabalar"], "Sirtqi ta'lim: qishki sessiyaga chaqiruv xatlari",
           "Sirtqi ta'lim shaklidagi talabalarga qishki o'quv-imtihon sessiyasi uchun chaqiruv xatlari tayyorlanmoqda. Dekanatlardan sessiyaga qo'yilmaydigan talabalar ro'yxatini, "
           "Buxgalteriyadan kontrakt qarzdorligi bo'yicha ma'lumotni so'raymiz. Chaqiruv xati namunasi ilova qilingan.",
           "sorov", "oddiy", 5, 15, files=["sirtqi"], read=["buxgalteriya"], who="Shayzakova")
    letter(faks[0] if faks else "fak1", ["talabalar"], "Bitiruvchilar transkriptlari: yakuniy davlat attestatsiyasi oldidan",
           "4-kurs bitiruvchi talabalarining transkriptlarini yakuniy davlat attestatsiyasi (YDA) oldidan tekshirish uchun taqdim etishingizni so'raymiz. "
           "Transkriptda baholari to'liq kiritilmagan fanlar bo'lsa, alohida ko'rsating.", "sorov", "oddiy", 6, 2)

    letter("talabalar", ["malumotlar_bazasi"], "«Registrator» bazasi: ko'chirilgan va ta'tildan qaytgan talabalar ma'lumotini yangilash",
           "Oktabr oyida ko'chirilgan (12 nafar) va akademik ta'tildan qaytgan (14 nafar) talabalar bo'yicha buyruqlar ilova qilinmoqda. «Registrator» bazasida guruh va holat "
           "ma'lumotlarini yangilab, portaldagi «Talabalar kontingenti» umumiy bazasini qayta yuklashingizni so'raymiz.", "sorov", "oddiy", 3, 31)
    letter("akademik", ["sirtqi", "talabalar"], "Sirtqi ta'lim shakli: qishki sessiya muddatlarini kelishish",
           "Akademik kalendarga ko'ra sirtqi ta'lim shakli uchun qishki sessiya muddatlarini kelishib olish zarur. Sirtqi bo'limdan guruhlar kesimida taklif, "
           "Registrator ofisidan sessiyaga chaqiriladigan talabalar soni bo'yicha ma'lumot kutamiz.", "sorov", "muhim", 6, 40,
           replies=[("sirtqi", "Taklifimiz: 1-2-kurslar 12-yanvardan, 3-4-kurslar 19-yanvardan, har biri 20 kun. 412 nafar talaba ish joyidan chaqiruv xati so'ragan.", 18, [], "Shayzakova")])

    # ---------- v2: yangi xatlar, rezolyutsiyalar, ijrochilar, yo'naltirish, yopilgan yozishmalar ----------
    letter("talabalar", ["it"], "Call-markaz: LMS parolini tiklash so'rovlari keskin ko'paydi",
           "Oxirgi 3 kunda Call-markazga LMS parolini tiklash bo'yicha 140 dan ortiq murojaat tushdi (odatda kuniga 10-15 ta). Talabalar SMS kod kelmayotganini aytmoqda. "
           "Sababini aniqlab, vaqtinchalik yechim berishingizni so'raymiz.", "sorov", "shoshilinch", 2, 7, read=["it"], who="Rahimova")
    letter(faks[1] if len(faks) > 1 else "fak2", ["talabalar"], "Sirtqi guruh talabalari uchun ish joyiga ma'lumotnoma",
           "Sirtqi ta'lim shaklidagi 18 nafar talaba ish joyiga taqdim etish uchun o'qish joyidan ma'lumotnoma so'ramoqda. Ro'yxat dekanatda. Tayyorlab berishingizni so'raymiz.",
           "sorov", "oddiy", 3, 30)
    def T(subj):
        r = db.one(con, "SELECT id FROM portal_threads WHERE subject=? ORDER BY id DESC LIMIT 1", (subj,))
        return r["id"] if r else None
    def safe(fn, *a, **k):
        try: return fn(*a, **k)
        except Exception as e: print("portal seed v2:", fn.__name__, e)
    rek, pro = cx("rektorat"), cx("prorektor_oquv", "prorektor_oquv")
    # 1) Rektor rezolyutsiyasi: isitish smetasi — Buxgalteriya (mas'ul) va moliya prorektori, muddat +3 kun
    tid = T("2-o'quv binosi isitish tizimi: ta'mirlash smetasi")
    if tid and rek:
        safe(resolve, con, rek, tid, ResolveIn(text="Moliyalashtirish manbasini aniqlang va smetani 75,2 mln so'm doirasida kelishing. Ishlar dam olish kunlari bajarilsin, "
                                                     "darslar to'xtatilmasin.", units=["buxgalteriya", "prorektor_moliya"], lead="buxgalteriya", due=day(3)), ts=ago(5))
    # 2) Rektor rezolyutsiyasi (muddati o'tgan, qisman bajarilgan): Erasmus nomzodlari
    tid = T("Erasmus+ KA171: bahorgi mobillik uchun nomzodlar")
    if tid and rek:
        safe(resolve, con, rek, tid, ResolveIn(text="Nomzodlarning akademik qarzdorligini Registrator ofisi orqali tekshiring, yakuniy ro'yxatni o'quv ishlari prorektori tasdiqlasin.",
                                                     units=["prorektor_oquv", "talabalar"], lead="prorektor_oquv", due=day(-1)), ts=ago(60))
        rg = cx("talabalar")
        if rg: safe(reply, con, rg, tid, ReplyIn(body="Tekshirildi: 2 nafar nomzodda akademik qarzdorlik bor — ular ro'yxatdan chiqarildi. Yangilangan ro'yxat Xalqaro hamkorlik bo'limiga yuborildi."), ts=ago(20))
    # 3) O'quv prorektori rezolyutsiyasi (kuzatuvchi sifatida qo'shiladi): akademik qarzdorlar ro'yxati
    tid = T("Akademik qarzdor talabalar ro'yxatini tasdiqlash")
    if tid and pro:
        safe(resolve, con, pro, tid, ResolveIn(text="Registrator ofisi ro'yxatni ertaga soat 12:00 gacha tasdiqlasin; kelishmovchiliklar bo'yicha Imtihon bo'limi bilan birga ishlang.",
                                                     units=["talabalar"], lead="talabalar", due=day(1)), ts=ago(26))
    # 4) Bo'lim ichida ijrochi: Registrator → Call-markaz operatori; IT boshlig'i → IT muhandisi
    rg = cx("talabalar")
    op = db.one(con, "SELECT id FROM users WHERE role='call_center' ORDER BY id LIMIT 1")
    tid = T("Sirtqi ta'lim: qishki sessiyaga chaqiruv xatlari")
    if tid and rg and op:
        con.execute("UPDATE portal_recipients SET status='o''qilgan', read_at=?, read_by=? WHERE thread_id=? AND unit='talabalar' AND status='yangi'", (ago(12), rg.user["full_name"], tid))
        con.execute("INSERT OR REPLACE INTO portal_user_reads(thread_id,user_id,last_msg,read_at) VALUES(?,?,(SELECT MAX(id) FROM portal_msgs WHERE thread_id=?),?)", (tid, rg.user["id"], tid, ago(12)))
        safe(assign, con, rg, tid, op["id"], ts=ago(10))
    itc = cx("it", "it_head"); eng = db.one(con, "SELECT id FROM users WHERE role='it_staff' ORDER BY id LIMIT 1")
    tid = T("Call-markaz: LMS parolini tiklash so'rovlari keskin ko'paydi")
    if tid and itc and eng: safe(assign, con, itc, tid, eng["id"], ts=ago(5))
    # 5) Yo'naltirish: Registrator → Sirtqi bo'lim; Sirtqi javob berdi
    tid = T("Sirtqi guruh talabalari uchun ish joyiga ma'lumotnoma")
    if tid and rg:
        con.execute("UPDATE portal_recipients SET status='o''qilgan', read_at=?, read_by=? WHERE thread_id=? AND unit='talabalar'", (ago(27), rg.user["full_name"], tid))
        safe(forward, con, rg, tid, ForwardIn(units=["sirtqi"], note="Sirtqi ta'lim talabalari masalasi — Sirtqi bo'lim vakolatida. Iltimos, bevosita ko'rib chiqing."), ts=ago(26))
        sq = cx("sirtqi", None, "Shayzakova")
        if sq: safe(reply, con, sq, tid, ReplyIn(body="Ma'lumotnomalar tayyorlandi: 18 nafar talabaga dekanat orqali ertaga topshiriladi."), ts=ago(8))
    # 6) Yopilgan yozishmalar
    for subj, unit, note, h in [("Akademik ta'tildan qaytgan talabalar kontraktini qayta hisoblash", "talabalar", "Masala hal qilindi", 18),
                                ("Scopus jurnallarida maqola chop etish rejasi (2027)", "kaf4", "Javob olindi, reja ishga tushirildi", 30)]:
        tid, cc = T(subj), cx(unit)
        if tid and cc: safe(close_thread, con, cc, tid, note, ts=ago(h))
    # 7) Shaxsiy arxiv: rektor o'qib bo'lgan xabarnomani arxivladi
    tid = T("HEMIS tizimida rejalashtirilgan texnik ishlar (shanba 22:00–02:00)")
    if tid and rek: con.execute("INSERT OR IGNORE INTO portal_hidden(thread_id,user_id,at) VALUES(?,?,?)", (tid, rek.user["id"], ago(40)))
    # 8) Qoralamalar
    if rg: save_draft(con, rg, DraftIn(subject="Talabalarga ma'lumotnoma berishning yangi tartibi", to=["akademik"] + faks,
                                        body="Hurmatli hamkasblar!\n\n1-dekabrdan boshlab o'qish joyidan ma'lumotnomalar faqat ISFT Core orqali, QR-kod bilan beriladi. "), ts=ago(3))
    if rek: save_draft(con, rek, DraftIn(subject="Ilmiy kengash yig'ilishiga tayyorgarlik", to=["prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar"],
                                         kind="topshiriq", priority="muhim", body="Prorektorlarga!\n\nNoyabr oyi Ilmiy kengash yig'ilishi uchun "), ts=ago(1))
    # 9) Shablonlar: institut miqyosida va bo'lim shablonlari
    admin = rek or rg
    TPL = [("*", "Ma'lumot so'rovi", "", "sorov", "oddiy", 5, [],
            "Hurmatli hamkasblar!\n\n{bolim} faoliyati doirasida quyidagi ma'lumotlarni {muddat} gacha taqdim etishingizni so'raymiz:\n1. \n2. \n\nMa'lumot portal orqali, ushbu yozishmaga javob sifatida yuborilsin.\n\nHurmat bilan,\n{bolim}"),
           ("*", "Hisobot taqdim etish", "… bo'yicha hisobot", "sorov", "muhim", 7, [],
            "Hurmatli hamkasblar!\n\n{sana} holatiga … bo'yicha hisobotni ilova qilingan shaklda {muddat} gacha taqdim eting.\n\nHisobot Excel (.xlsx) yoki PDF formatida ilova qilinsin."),
           ("*", "Xabarnoma (bo'limlarga)", "", "xabarnoma", "oddiy", None, [],
            "Hurmatli hamkasblar!\n\nMa'lumot uchun xabar qilamiz: …\n\n{bolim}"),
           ("*", "Topshiriq", "", "topshiriq", "muhim", 3, [],
            "Topshiriq:\n1. …\n2. …\n\nIjro natijasi haqida {muddat} gacha ma'lumot bering."),
           ("*", "Yig'ilishga taklif", "Yig'ilish: … (sana, vaqt)", "xabarnoma", "oddiy", None, [],
            "Hurmatli hamkasblar!\n\n… kuni soat … da … xonada yig'ilish bo'lib o'tadi.\nKun tartibi:\n1. …\n2. …\n\nIshtirokingiz shart."),
           ("talabalar", "Talaba bo'yicha so'rovga javob", "", "xat", "oddiy", None, [],
            "Hurmatli hamkasblar!\n\nSo'rovingizga ko'ra, «Registrator» bazasidagi {sana} holatiga ma'lumot:\n— Talaba: …\n— Guruh: …\n— Holati: …\n\nRegistrator ofisi"),
           ("akademik", "Kafedralardan o'quv yuklamasi so'rovi", "O'quv yuklamasini taqdim etish", "sorov", "muhim", 10, kafs,
            "Kafedra mudirlariga!\n\nKafedrangiz o'quv yuklamasini ilova qilingan shaklda to'ldirib, {muddat} gacha yuboring.")]
    for owner, title, subj, kind, prio, dd, to, body in TPL:
        cc = cx(owner) if owner != "*" else admin
        if cc: save_template(con, cc, TemplateIn(title=title, subject=subj, body=body, kind=kind, priority=prio, due_days=dd, to=to), owner=owner)
    con.execute("UPDATE portal_templates SET uses=? WHERE title=?", (14, "Ma'lumot so'rovi"))
    con.execute("UPDATE portal_templates SET uses=? WHERE title=?", (9, "Hisobot taqdim etish"))
    con.commit(); _bump()

    # ---------- umumiy bazalar katalogi: oxirgi yangilanish ----------
    for i, (k, hrs) in enumerate([("kontingent", 28), ("jadval", 20), ("oqituvchilar", 260), ("kontrakt", 26), ("auditoriyalar", 140),
                                  ("tuzilma", 700), ("hamkorlar", 330), ("nashrlar", 180), ("qabul", 900)]):
        con.execute("INSERT OR REPLACE INTO portal_datasets(key,updated_at,views,exports) VALUES(?,?,?,?)", (k, ago(hrs), [42, 87, 35, 19, 23, 14, 11, 16, 9][i], [6, 21, 4, 3, 2, 1, 1, 2, 1][i]))
    con.execute("INSERT OR REPLACE INTO portal_meta(k,v) VALUES('seed',?)", (SEED_TAG,))
    con.commit()
    print(f"Portal namunasi: {con.execute('SELECT COUNT(*) FROM portal_threads').fetchone()[0]} ta yozishma, "
          f"{con.execute('SELECT COUNT(*) FROM portal_files').fetchone()[0]} ta fayl")

if __name__ == "__main__":   # qo'lda qayta tiklash: .venv/bin/python -m app.portal
    _c = db.connect(); db.init(_c); _c.executescript(SCHEMA); seed(_c, force=True)
