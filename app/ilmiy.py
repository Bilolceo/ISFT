"""«Ilmiy faoliyat» — Ilmiy bo'lim va Magistratura ish jarayoni (docs/ilmiy.md).

1. Nashrlar: muallif (o'qituvchi) yoki kafedra arizasi → kafedra mudiri tekshiruvi → Ilmiy bo'lim tasdig'i (Scopus / WoS — DOI va
   indeksatsiya tekshiruvi) → «publications» reyestriga yoziladi. Qaytarilgan ariza tuzatilib qayta yuboriladi. Takror (DOI yoki
   bir muallifda bir xil sarlavha) qabul qilinmaydi. Kafedra rejalari (yil bo'yicha Scopus/WoS va OAK) va bajarilishi.
2. Grantlar va loyihalar: loyiha → prorektor imzosiga → imzolandi → ariza yuborildi (ko'rib chiqilmoqda) → yutildi (bajarilmoqda,
   har 6 oyda oraliq hisobot + yakuniy hisobot) yoki rad etildi → yakunlandi (yakuniy hisobot qabul qilingach).
3. Magistrlik dissertatsiyasi: mavzu va ilmiy rahbar (Ilmiy kengash bayonnomasi) → 1-bob → 2-bob → kafedra ilmiy seminari →
   dastlabki himoya → himoya (DAK). Har bosqich muddati qabul yilidan hisoblanadi; muddati o'tganlar — ogohlantirish.
Mavjud jadvallar (publications, grants, masters) kengaytiriladi — eski hisobotlar (services.science_summary, masters_summary)
o'zgarishsiz ishlaydi. Ruxsatlar serverda (mode/guard); har bir murojaat rbac.audit (SCIENCE yoki MASTERS).
"""
import datetime as dt, math, random, re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
P = "/api/ilmiy"
_con = None
_ctx = None

KINDS = ["Scopus", "Web of Science", "OAK jurnali", "Xorijiy jurnal", "Mahalliy jurnal", "Konferensiya tezisi", "Monografiya", "Darslik / o'quv qo'llanma"]
INDEXED = ("Scopus", "Web of Science")
QUARTILES = ["Q1", "Q2", "Q3", "Q4"]
PUB_ST = {"kafedra": "Kafedra tekshiruvida", "ilmiy": "Ilmiy bo'lim tekshiruvida", "tasdiqlangan": "Tasdiqlandi — reyestrda",
          "qaytarildi": "Qaytarildi — tuzatish kerak", "qaytarib olindi": "Muallif qaytarib oldi"}
GRANT_ST = {"loyiha": "Loyiha (tayyorlanmoqda)", "imzoda": "Prorektor imzosida", "imzolandi": "Imzolandi — yuborishga tayyor",
            "ariza berilgan": "Ariza yuborildi — ko'rib chiqilmoqda", "bajarilmoqda": "Yutildi — bajarilmoqda",
            "rad etilgan": "Rad etildi", "yakunlangan": "Yakunlandi"}
FUNDERS = ["Innovatsion rivojlanish agentligi", "Vazirlik", "Erasmus+", "Jahon banki", "Xalqaro hamkor", "Xo'jalik shartnomasi"]
REP_ST = {"kutilmoqda": "Kutilmoqda", "topshirildi": "Topshirildi — tekshiruvda", "qabul qilindi": "Qabul qilindi", "qaytarildi": "Qaytarildi"}
# dissertatsiya bosqichlari: (kalit, nom, masters.stage yorlig'i, muddat: (qabul yilidan + yil, oy, kun), bayonnoma shartmi)
STAGES = [("mavzu", "Mavzu va ilmiy rahbar tasdig'i", "Mavzu tasdiqlangan", (0, 11, 15), True),
          ("bob1", "1-bob", "1-bob tayyor", (1, 3, 1), False),
          ("bob2", "2-bob", "2-bob tayyor", (1, 6, 15), False),
          ("seminar", "Kafedra ilmiy seminari", "Ilmiy seminar o'tdi", (2, 3, 15), True),
          ("dastlabki", "Dastlabki himoya", "Dastlabki himoya", (2, 5, 10), True),
          ("himoya", "Himoya (DAK)", "Himoya qilindi", (2, 6, 20), True)]
SKEYS = [s[0] for s in STAGES]
SNAME = {s[0]: s[1] for s in STAGES}
SLABEL = {s[0]: s[2] for s in STAGES}
STAGE_ST = {"kutilmoqda": "Kutilmoqda", "topshirildi": "Material topshirildi", "o'tdi": "O'tdi", "qayta": "Qayta topshirish"}
# bosqich natijasini kim qayd etadi (magistratura — hammasini)
STAGE_JUDGE = {"mavzu": ("magistratura",), "bob1": ("oqituvchi", "kafedra", "magistratura"), "bob2": ("oqituvchi", "kafedra", "magistratura"),
               "seminar": ("kafedra", "magistratura"), "dastlabki": ("kafedra", "magistratura"), "himoya": ("magistratura",)}
SUP_MAX = 8                  # bir ilmiy rahbarga ko'pi bilan magistrant
SUP_DEGREES = ("PhD", "DSc")
DEFENSE_PASS = 55            # himoya: 55 dan past — qayta himoya
SOON_DAYS = 14

SCHEMA = """
CREATE TABLE IF NOT EXISTS pub_subs(id INTEGER PRIMARY KEY, teacher_id INT, title TEXT, kind TEXT, journal TEXT, year INT, doi TEXT, url TEXT,
  issn TEXT, quartile TEXT, coauthors TEXT, status TEXT, note TEXT, created_by INT, created_at TEXT, kaf_by INT, kaf_at TEXT, ilm_by INT, ilm_at TEXT,
  pub_id INT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_pub_subs_st ON pub_subs(status);
CREATE TABLE IF NOT EXISTS pub_log(id INTEGER PRIMARY KEY, sub_id INT, at TEXT, user_id INT, user_name TEXT, action TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS sci_plans(dept_id INT, year INT, scopus INT, oak INT, by_user INT, at TEXT, PRIMARY KEY(dept_id, year));
CREATE TABLE IF NOT EXISTS grant_reports(id INTEGER PRIMARY KEY, grant_id INT, kind TEXT, title TEXT, due TEXT, status TEXT DEFAULT 'kutilmoqda',
  note TEXT, submitted_at TEXT, submitted_by INT, reviewed_at TEXT, reviewed_by INT, review_note TEXT);
CREATE INDEX IF NOT EXISTS ix_grant_reports_g ON grant_reports(grant_id);
CREATE TABLE IF NOT EXISTS grant_log(id INTEGER PRIMARY KEY, grant_id INT, at TEXT, user_id INT, user_name TEXT, action TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS diss_stages(id INTEGER PRIMARY KEY, master_id INT, stage TEXT, due TEXT, status TEXT DEFAULT 'kutilmoqda',
  submitted_at TEXT, done_at TEXT, protocol TEXT, score INT, note TEXT, by_user INT, UNIQUE(master_id, stage));
CREATE TABLE IF NOT EXISTS diss_log(id INTEGER PRIMARY KEY, master_id INT, at TEXT, user_id INT, user_name TEXT, action TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS ilmiy_meta(k TEXT PRIMARY KEY, v TEXT);
"""
ALTERS = {"publications": [("journal", "TEXT"), ("doi", "TEXT"), ("quartile", "TEXT"), ("sub_id", "INT")],
          "grants": [("program", "TEXT"), ("deadline", "TEXT"), ("months", "INT"), ("submitted_at", "TEXT"), ("decided_at", "TEXT"),
                     ("start", "TEXT"), ("end_date", "TEXT"), ("amount_won", "INT"), ("endorsed_by", "INT"), ("endorsed_at", "TEXT"),
                     ("note", "TEXT"), ("created_by", "INT"), ("created_at", "TEXT")]}

def _today(): return clock.today()
def _now(): return clock.now_iso()
def _bad(msg, code=400): raise HTTPException(code, msg)
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _date(v, label="Sana"):
    try: return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except (TypeError, ValueError): _bad(f"{label} noto'g'ri: {v}")
def _acad_start(d=None) -> int:
    d = d or _today(); return d.year if d.month >= 9 else d.year - 1

# =============================================================================================
# Ruxsat va ko'lam
# =============================================================================================
MODES = {"ilmiy_bolim": "ilmiy", "prorektor_ilmiy": "prorektor", "magistratura": "mag", "kafedra": "kafedra", "oqituvchi": "oqituvchi",
         "rektor": "lead", "kengash": "kengash", "prorektor_oquv": "oquv"}
TABS = {"ilmiy": ["umumiy", "nashrlar", "grantlar", "dissertatsiya"], "prorektor": ["umumiy", "nashrlar", "grantlar", "dissertatsiya"],
        "mag": ["umumiy", "dissertatsiya"], "kafedra": ["umumiy", "nashrlar", "grantlar", "dissertatsiya"],
        "oqituvchi": ["nashrlar", "grantlar", "dissertatsiya"], "lead": ["umumiy", "nashrlar", "grantlar"], "kengash": ["umumiy"],
        "oquv": ["umumiy", "dissertatsiya"]}
TAB_RES = {"umumiy": rbac.SCIENCE, "nashrlar": rbac.SCIENCE, "grantlar": rbac.SCIENCE, "dissertatsiya": rbac.MASTERS}
MODE_NOTE = {"ilmiy": "Nashrlarni tasdiqlash, grantlar va loyihalar, kafedra rejalari; dissertatsiyalar — kuzatuv",
             "prorektor": "Grant arizalarini imzolash, kafedra rejalari; barcha ko'rsatkichlar",
             "mag": "Magistrlik dissertatsiyalari: mavzu, ilmiy rahbar, bosqichlar va muddatlar",
             "kafedra": "O'z kafedrasi: nashrlarni tekshirish, grant arizalari, seminar va dastlabki himoya",
             "oqituvchi": "O'z nashrlari, grant loyihalari va rahbarlikdagi magistrantlar",
             "lead": "Jamlangan ko'rsatkichlar, nashrlar reyestri va grantlar (faqat o'qish)", "kengash": "Faqat jamlangan ko'rsatkichlar",
             "oquv": "Jamlangan ko'rsatkichlar va dissertatsiyalar (faqat o'qish)"}

def mode(c: Ctx): return MODES.get(c.role.key)

def guard(c: Ctx, tab: str, action: str, detail: str = "", roles=None) -> str:
    m = mode(c)
    res = TAB_RES.get(tab, rbac.SCIENCE)
    ok = m is not None and (tab == "meta" or tab in TABS[m]) and (roles is None or m in roles)
    rbac.audit(_con, c, f"ilmiy faoliyat: {action}", res, ok, detail)
    if not ok:
        why = ("bu bo'lim lavozimingiz uchun yopiq" if m and tab not in TABS[m] and tab != "meta" else
               "bu amal lavozimingiz uchun emas" if m else f"«{c.role.title}» lavozimi uchun ruxsat yo'q")
        raise AccessDenied(f"⛔ Ilmiy faoliyat: {why}. So'rov audit jurnaliga yozildi.")
    return m

def _deny(c: Ctx, action: str, msg: str, res=rbac.SCIENCE, detail=""):
    rbac.audit(_con, c, f"ilmiy faoliyat: {action}", res, False, detail)
    raise AccessDenied(f"⛔ {msg}. So'rov audit jurnaliga yozildi.")

def _dept(c: Ctx) -> int: return int(c.user.get("department_id") or 0)
def _tid(c: Ctx) -> int: return int(c.user.get("teacher_id") or 0)

def teacher_scope(c: Ctx, a="t") -> str:
    m = mode(c)
    if m == "kafedra": return f"{a}.department_id={_dept(c)}"
    if m == "oqituvchi": return f"{a}.id={_tid(c)}"
    return "1=1"

def diss_scope(c: Ctx) -> str:
    m = mode(c)
    if m == "kafedra":
        d = _dept(c)
        return f"(sup.department_id={d} OR g.department_id={d})"
    if m == "oqituvchi": return f"m.supervisor_id={_tid(c)}"
    return "1=1"

def _who(c: Ctx) -> str:
    n = _short(c.user.get("full_name"))
    return f"{c.title} — {n}" if n else c.title

def _log(table, key, id_, c: Ctx, action, note=""):
    _con.execute(f"INSERT INTO {table}({key},at,user_id,user_name,action,note) VALUES(?,?,?,?,?,?)",
                 (id_, _now(), c.user["id"], _who(c), action, (note or "")[:500]))

def _teacher(tid) -> dict:
    t = db.one(_con, "SELECT t.*, d.name kafedra FROM teachers t LEFT JOIN departments d ON d.id=t.department_id WHERE t.id=?", (int(tid or 0),))
    if not t: _bad("O'qituvchi topilmadi", 404)
    return t

# =============================================================================================
# 1. Nashrlar
# =============================================================================================
def _norm(s): return re.sub(r"[^a-z0-9а-яўқғҳʻ']+", " ", (s or "").lower()).strip()
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

def _pub_row(r: dict, c: Ctx) -> dict:
    r["status_name"] = PUB_ST.get(r["status"], r["status"])
    m = mode(c)
    st = r["status"]
    r["can_review"] = (st == "kafedra" and m == "kafedra" and r.get("dept_id") == _dept(c)) or (st == "ilmiy" and m == "ilmiy")
    r["can_edit"] = st in ("qaytarildi", "kafedra") and ((m == "oqituvchi" and r["teacher_id"] == _tid(c)) or
                                                         (m == "kafedra" and r.get("dept_id") == _dept(c)) or m == "ilmiy")
    r["can_withdraw"] = st in ("kafedra", "ilmiy", "qaytarildi") and m == "oqituvchi" and r["teacher_id"] == _tid(c)
    return r

def _sub(sid: int) -> dict:
    r = db.one(_con, """SELECT p.*, t.full_name author, t.department_id dept_id, d.name kafedra FROM pub_subs p JOIN teachers t ON t.id=p.teacher_id
                        LEFT JOIN departments d ON d.id=t.department_id WHERE p.id=?""", (sid,))
    if not r: _bad("Ariza topilmadi", 404)
    return r

class PubIn(BaseModel):
    teacher_id: int | None = None
    title: str
    kind: str
    journal: str = ""
    year: int
    doi: str = ""
    url: str = ""
    issn: str = ""
    quartile: str = ""
    coauthors: str = ""

def _validate_pub(b: PubIn, exclude_id=None) -> dict:
    t = (b.title or "").strip()
    if len(t) < 10: _bad("Sarlavha juda qisqa (kamida 10 belgi)")
    if b.kind not in KINDS: _bad("Nashr turi noto'g'ri")
    y = _today().year
    if not (y - 3 <= int(b.year) <= y): _bad(f"Nashr yili {y - 3}–{y} oralig'ida bo'lishi kerak")
    doi = (b.doi or "").strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if doi and not DOI_RE.match(doi): _bad("DOI formati noto'g'ri (masalan: 10.1016/j.econ.2026.01.004)")
    url = (b.url or "").strip()
    if url and not re.match(r"^https?://\S+\.\S+", url): _bad("Havola http(s):// bilan boshlanishi kerak")
    if b.kind in INDEXED and not (doi or url): _bad(f"{b.kind} nashri uchun DOI yoki indeksatsiya bazasidagi havola majburiy")
    q = (b.quartile or "").strip().upper()
    if q and q not in QUARTILES: _bad("Kvartil Q1–Q4 bo'lishi kerak")
    if q and b.kind not in INDEXED: q = ""
    if b.kind not in ("Konferensiya tezisi",) and not (b.journal or "").strip(): _bad("Jurnal / nashriyot nomini kiriting")
    return {"title": t, "kind": b.kind, "journal": (b.journal or "").strip()[:300], "year": int(b.year), "doi": doi or None, "url": url or None,
            "issn": (b.issn or "").strip()[:20] or None, "quartile": q or None, "coauthors": (b.coauthors or "").strip()[:500] or None}

def _dup_check(tid: int, f: dict, exclude_id=None):
    ex = f" AND id!={int(exclude_id)}" if exclude_id else ""
    if f["doi"]:
        if db.one(_con, "SELECT 1 x FROM publications WHERE lower(doi)=lower(?)", (f["doi"],)) or \
           db.one(_con, f"SELECT 1 x FROM pub_subs WHERE lower(doi)=lower(?) AND status NOT IN ('qaytarib olindi'){ex}", (f["doi"],)):
            _bad("Bu DOI bilan nashr allaqachon ro'yxatga olingan", 409)
    n = _norm(f["title"])
    for r in db.rows(_con, "SELECT title FROM publications WHERE teacher_id=?", (tid,)) + \
             db.rows(_con, f"SELECT title FROM pub_subs WHERE teacher_id=? AND status NOT IN ('qaytarib olindi'){ex}", (tid,)):
        if _norm(r["title"]) == n: _bad("Bu muallifda shu sarlavhali nashr allaqachon bor (takror)", 409)

def pubs_list(c: Ctx, status="", dept=0, q="", kind="") -> dict:
    w = [teacher_scope(c)]; a = []
    if status == "navbat":
        m = mode(c)
        w.append("p.status='kafedra'" if m == "kafedra" else "p.status='ilmiy'" if m == "ilmiy" else "p.status IN ('kafedra','ilmiy')")
    elif status: w.append("p.status=?"); a.append(status)
    if dept: w.append("t.department_id=?"); a.append(int(dept))
    if kind: w.append("p.kind=?"); a.append(kind)
    if q: w.append("(p.title LIKE ? OR t.full_name LIKE ? OR p.journal LIKE ?)"); a += [f"%{q}%"] * 3
    rs = db.rows(_con, f"""SELECT p.*, t.full_name author, t.department_id dept_id, d.name kafedra FROM pub_subs p JOIN teachers t ON t.id=p.teacher_id
        LEFT JOIN departments d ON d.id=t.department_id WHERE {' AND '.join(w)}
        ORDER BY CASE p.status WHEN 'kafedra' THEN 0 WHEN 'ilmiy' THEN 1 WHEN 'qaytarildi' THEN 2 ELSE 3 END, p.id DESC LIMIT 300""", a)
    cnt = {r["status"]: r["n"] for r in db.rows(_con, f"""SELECT p.status, COUNT(*) n FROM pub_subs p JOIN teachers t ON t.id=p.teacher_id
        WHERE {teacher_scope(c)} GROUP BY 1""")}
    return {"rows": [_pub_row(r, c) for r in rs], "counts": cnt}

def registry(c: Ctx, dept=0, kind="", year=0, q="", page=1) -> dict:
    w = [teacher_scope(c)]; a = []
    if dept: w.append("t.department_id=?"); a.append(int(dept))
    if kind: w.append("p.kind=?"); a.append(kind)
    if year: w.append("p.year=?"); a.append(int(year))
    if q: w.append("(p.title LIKE ? OR t.full_name LIKE ?)"); a += [f"%{q}%"] * 2
    W = " AND ".join(w)
    total = db.one(_con, f"SELECT COUNT(*) n FROM publications p JOIN teachers t ON t.id=p.teacher_id WHERE {W}", a)["n"]
    page = max(1, int(page or 1))
    rs = db.rows(_con, f"""SELECT p.id, p.title, p.kind, p.year, p.citations, p.journal, p.doi, p.quartile, t.full_name author, d.name kafedra
        FROM publications p JOIN teachers t ON t.id=p.teacher_id LEFT JOIN departments d ON d.id=t.department_id WHERE {W}
        ORDER BY p.year DESC, p.id DESC LIMIT 50 OFFSET ?""", a + [(page - 1) * 50])
    return {"rows": rs, "total": total, "page": page, "pages": max(1, math.ceil(total / 50))}

def create_pub(c: Ctx, b: PubIn) -> dict:
    m = guard(c, "nashrlar", "nashr arizasi", b.title[:80], roles=("oqituvchi", "kafedra", "ilmiy"))
    tid = _tid(c) if m == "oqituvchi" else int(b.teacher_id or 0)
    if not tid: _bad("Muallifni (o'qituvchi) tanlang")
    t = _teacher(tid)
    if m == "kafedra" and t["department_id"] != _dept(c): _deny(c, "nashr arizasi", "Muallif boshqa kafedrada", detail=str(tid))
    f = _validate_pub(b)
    _dup_check(tid, f)
    st = "kafedra" if m == "oqituvchi" else "ilmiy"
    now = _now()
    cur = _con.execute("""INSERT INTO pub_subs(teacher_id,title,kind,journal,year,doi,url,issn,quartile,coauthors,status,created_by,created_at,kaf_by,kaf_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (tid, f["title"], f["kind"], f["journal"], f["year"], f["doi"], f["url"], f["issn"], f["quartile"],
        f["coauthors"], st, c.user["id"], now, c.user["id"] if m == "kafedra" else None, now if m == "kafedra" else None, now))
    sid = cur.lastrowid
    _log("pub_log", "sub_id", sid, c, "yuborildi", PUB_ST[st])
    _con.commit()
    return _pub_row(_sub(sid), c)

def edit_pub(c: Ctx, sid: int, b: PubIn) -> dict:
    guard(c, "nashrlar", "nashr arizasini tuzatish", f"#{sid}", roles=("oqituvchi", "kafedra", "ilmiy"))
    r = _pub_row(_sub(sid), c)
    if not r["can_edit"]: _deny(c, "nashr arizasini tuzatish", "Bu arizani tuzatish huquqingiz yo'q (holati yoki muallif)", detail=f"#{sid}")
    f = _validate_pub(b)
    _dup_check(r["teacher_id"], f, exclude_id=sid)
    st = "ilmiy" if mode(c) in ("kafedra", "ilmiy") else "kafedra"
    _con.execute("""UPDATE pub_subs SET title=?,kind=?,journal=?,year=?,doi=?,url=?,issn=?,quartile=?,coauthors=?,status=?,updated_at=? WHERE id=?""",
                 (f["title"], f["kind"], f["journal"], f["year"], f["doi"], f["url"], f["issn"], f["quartile"], f["coauthors"], st, _now(), sid))
    _log("pub_log", "sub_id", sid, c, "tuzatildi va qayta yuborildi", PUB_ST[st])
    _con.commit()
    return _pub_row(_sub(sid), c)

def review_pub(c: Ctx, sid: int, decision: str, note: str = "", indexed: bool = False, quartile: str = "") -> dict:
    m = guard(c, "nashrlar", "nashr tekshiruvi", f"#{sid} · {decision}", roles=("kafedra", "ilmiy"))
    r = _pub_row(_sub(sid), c)
    if not r["can_review"]: _deny(c, "nashr tekshiruvi", "Bu ariza sizning tekshiruv navbatingizda emas", detail=f"#{sid} · {r['status']}")
    if decision not in ("tasdiq", "qaytarish"): _bad("Qaror: tasdiq yoki qaytarish")
    note = (note or "").strip()
    now = _now()
    if decision == "qaytarish":
        if len(note) < 5: _bad("Qaytarish sababini yozing")
        _con.execute("UPDATE pub_subs SET status='qaytarildi', note=?, updated_at=? WHERE id=?", (note, now, sid))
        _log("pub_log", "sub_id", sid, c, "qaytarildi", note)
    elif m == "kafedra":
        _con.execute("UPDATE pub_subs SET status='ilmiy', kaf_by=?, kaf_at=?, note=NULL, updated_at=? WHERE id=?", (c.user["id"], now, now, sid))
        _log("pub_log", "sub_id", sid, c, "kafedra tasdiqladi", note)
    else:
        if r["kind"] in INDEXED and not indexed:
            _bad(f"{r['kind']}: nashr bazada indekslanganini tekshirib, belgilang")
        q = (quartile or r.get("quartile") or "").upper() or None
        if q and q not in QUARTILES: _bad("Kvartil Q1–Q4")
        cur = _con.execute("INSERT INTO publications(teacher_id,title,kind,year,citations,journal,doi,quartile,sub_id) VALUES(?,?,?,?,0,?,?,?,?)",
                           (r["teacher_id"], r["title"], r["kind"], r["year"], r["journal"], r["doi"], q if r["kind"] in INDEXED else None, sid))
        _con.execute("UPDATE pub_subs SET status='tasdiqlangan', ilm_by=?, ilm_at=?, pub_id=?, quartile=?, note=NULL, updated_at=? WHERE id=?",
                     (c.user["id"], now, cur.lastrowid, q, now, sid))
        _log("pub_log", "sub_id", sid, c, "tasdiqlandi — reyestrga yozildi", note)
    _con.commit()
    rbac.audit(_con, c, "ilmiy faoliyat: nashr qarori", rbac.SCIENCE, True, f"#{sid} · {decision}")
    return _pub_row(_sub(sid), c)

def withdraw_pub(c: Ctx, sid: int) -> dict:
    guard(c, "nashrlar", "nashr arizasini qaytarib olish", f"#{sid}", roles=("oqituvchi",))
    r = _pub_row(_sub(sid), c)
    if not r["can_withdraw"]: _deny(c, "nashr arizasini qaytarib olish", "Faqat o'z, hali tasdiqlanmagan arizangizni qaytarib olasiz", detail=f"#{sid}")
    _con.execute("UPDATE pub_subs SET status='qaytarib olindi', updated_at=? WHERE id=?", (_now(), sid))
    _log("pub_log", "sub_id", sid, c, "muallif qaytarib oldi"); _con.commit()
    return _pub_row(_sub(sid), c)

def pub_detail(c: Ctx, sid: int) -> dict:
    guard(c, "nashrlar", "nashr arizasi", f"#{sid}")
    r = _sub(sid)
    if not db.one(_con, f"SELECT 1 x FROM teachers t WHERE t.id=? AND {teacher_scope(c)}", (r["teacher_id"],)):
        _deny(c, "nashr arizasi", "Bu ariza ko'lamingizdan tashqarida", detail=f"#{sid}")
    r = _pub_row(r, c)
    r["log"] = db.rows(_con, "SELECT at, user_name, action, note FROM pub_log WHERE sub_id=? ORDER BY id", (sid,))
    return r

def dept_stats(c: Ctx, year=None) -> list:
    y = int(year or _today().year)
    w = "d.id=" + str(_dept(c)) if mode(c) == "kafedra" else "1=1"
    out = []
    for d in db.rows(_con, f"SELECT d.id, d.name FROM departments d WHERE {w} ORDER BY d.id"):
        t = db.one(_con, """SELECT COUNT(*) n, SUM(degree IN ('PhD','DSc')) deg FROM teachers WHERE department_id=?""", (d["id"],))
        k = {r["kind"]: r["n"] for r in db.rows(_con, """SELECT p.kind, COUNT(*) n FROM publications p JOIN teachers t ON t.id=p.teacher_id
            WHERE t.department_id=? AND p.year=? GROUP BY 1""", (d["id"], y))}
        idx = sum(k.get(x, 0) for x in INDEXED)
        oak = k.get("OAK jurnali", 0)
        zero = db.one(_con, """SELECT COUNT(*) n FROM teachers t WHERE t.department_id=? AND NOT EXISTS
            (SELECT 1 FROM publications p WHERE p.teacher_id=t.id AND p.year>=?)""", (d["id"], y - 1))["n"]
        pend = db.one(_con, """SELECT COUNT(*) n FROM pub_subs p JOIN teachers t ON t.id=p.teacher_id WHERE t.department_id=? AND p.status IN ('kafedra','ilmiy')""",
                      (d["id"],))["n"]
        pl = db.one(_con, "SELECT scopus, oak FROM sci_plans WHERE dept_id=? AND year=?", (d["id"], y)) or {}
        out.append({"dept_id": d["id"], "kafedra": d["name"], "teachers": t["n"], "degree_pct": round(100 * (t["deg"] or 0) / t["n"], 1) if t["n"] else 0,
                    "indexed": idx, "oak": oak, "total": sum(k.values()), "by_kind": k, "per_teacher": round(sum(k.values()) / t["n"], 2) if t["n"] else 0,
                    "zero_teachers": zero, "pending": pend, "plan_scopus": pl.get("scopus"), "plan_oak": pl.get("oak"),
                    "plan_scopus_pct": round(100 * idx / pl["scopus"]) if pl.get("scopus") else None,
                    "plan_oak_pct": round(100 * oak / pl["oak"]) if pl.get("oak") else None})
    return out

def set_plan(c: Ctx, dept_id: int, year: int, scopus: int, oak: int):
    guard(c, "umumiy", "kafedra ilmiy rejasi", f"kafedra #{dept_id} · {year}: {scopus}/{oak}", roles=("ilmiy", "prorektor"))
    if not db.one(_con, "SELECT 1 x FROM departments WHERE id=?", (dept_id,)): _bad("Kafedra topilmadi", 404)
    if not (0 <= scopus <= 500 and 0 <= oak <= 2000): _bad("Reja qiymatlari noto'g'ri")
    if year not in (_today().year, _today().year + 1): _bad("Reja joriy yoki keyingi yil uchun tuziladi")
    _con.execute("INSERT OR REPLACE INTO sci_plans(dept_id,year,scopus,oak,by_user,at) VALUES(?,?,?,?,?,?)", (dept_id, year, scopus, oak, c.user["id"], _now()))
    _con.commit()

# =============================================================================================
# 2. Grantlar va loyihalar
# =============================================================================================
def _grant(gid: int) -> dict:
    g = db.one(_con, """SELECT g.*, t.full_name leader, t.department_id dept_id, d.name kafedra FROM grants g LEFT JOIN teachers t ON t.id=g.leader_id
                        LEFT JOIN departments d ON d.id=t.department_id WHERE g.id=?""", (gid,))
    if not g: _bad("Grant topilmadi", 404)
    return g

def _grant_acts(g: dict, c: Ctx) -> list:
    m = mode(c); st = g["status"]
    own = (m == "oqituvchi" and g["leader_id"] == _tid(c)) or (m == "kafedra" and g.get("dept_id") == _dept(c)) or m == "ilmiy"
    acts = []
    if st == "loyiha" and own: acts.append("imzoga")
    if st == "imzoda" and m == "prorektor": acts += ["imzo", "qaytarish"]
    if st == "imzolandi" and m == "ilmiy": acts.append("yuborish")
    if st == "ariza berilgan" and m == "ilmiy": acts += ["yutildi", "rad"]
    if st == "bajarilmoqda" and m == "ilmiy": acts.append("yakunlash")
    return acts

def _grant_row(g: dict, c: Ctx) -> dict:
    t = _today().isoformat()
    g["status_name"] = GRANT_ST.get(g["status"], g["status"])
    g["acts"] = _grant_acts(g, c)
    reps = db.rows(_con, "SELECT * FROM grant_reports WHERE grant_id=? ORDER BY due", (g["id"],))
    m = mode(c)
    own = (m == "oqituvchi" and g["leader_id"] == _tid(c)) or (m == "kafedra" and g.get("dept_id") == _dept(c))
    for r in reps:
        r["status_name"] = REP_ST.get(r["status"], r["status"])
        r["overdue"] = r["status"] in ("kutilmoqda", "qaytarildi") and r["due"] < t
        r["acts"] = (["topshirish"] if r["status"] in ("kutilmoqda", "qaytarildi") and (own or m == "ilmiy") and g["status"] == "bajarilmoqda" else []) + \
                    (["qabul", "qaytarish"] if r["status"] == "topshirildi" and m == "ilmiy" else [])
    g["reports"] = reps
    g["overdue_reports"] = sum(1 for r in reps if r["overdue"])
    g["deadline_passed"] = bool(g.get("deadline") and g["deadline"] < t and g["status"] in ("loyiha", "imzoda", "imzolandi"))
    return g

def grants_list(c: Ctx, status="", q="") -> dict:
    w = [teacher_scope(c)]; a = []
    if status == "faol": w.append("g.status IN ('loyiha','imzoda','imzolandi','ariza berilgan','bajarilmoqda')")
    elif status: w.append("g.status=?"); a.append(status)
    if q: w.append("(g.title LIKE ? OR t.full_name LIKE ? OR g.funder LIKE ?)"); a += [f"%{q}%"] * 3
    rs = db.rows(_con, f"""SELECT g.*, t.full_name leader, t.department_id dept_id, d.name kafedra FROM grants g JOIN teachers t ON t.id=g.leader_id
        LEFT JOIN departments d ON d.id=t.department_id WHERE {' AND '.join(w)}
        ORDER BY CASE g.status WHEN 'imzoda' THEN 0 WHEN 'imzolandi' THEN 1 WHEN 'loyiha' THEN 2 WHEN 'ariza berilgan' THEN 3 WHEN 'bajarilmoqda' THEN 4 ELSE 5 END,
        g.id DESC""", a)
    rows = [_grant_row(g, c) for g in rs]
    cnt = {}
    for g in db.rows(_con, f"SELECT g.status FROM grants g JOIN teachers t ON t.id=g.leader_id WHERE {teacher_scope(c)}"):
        cnt[g["status"]] = cnt.get(g["status"], 0) + 1
    return {"rows": rows, "counts": cnt}

class GrantIn(BaseModel):
    title: str
    funder: str
    program: str = ""
    amount: int
    months: int = 12
    deadline: str
    leader_id: int | None = None
    note: str = ""

def create_grant(c: Ctx, b: GrantIn) -> dict:
    m = guard(c, "grantlar", "grant loyihasi", b.title[:80], roles=("oqituvchi", "kafedra", "ilmiy"))
    lid = _tid(c) if m == "oqituvchi" else int(b.leader_id or 0)
    if not lid: _bad("Loyiha rahbarini tanlang")
    t = _teacher(lid)
    if m == "kafedra" and t["department_id"] != _dept(c): _deny(c, "grant loyihasi", "Loyiha rahbari boshqa kafedrada", detail=str(lid))
    title = (b.title or "").strip()
    if len(title) < 10: _bad("Loyiha nomi juda qisqa")
    if b.funder not in FUNDERS: _bad("Moliyalashtiruvchi ro'yxatdan tanlanadi")
    if not (1_000_000 <= int(b.amount) <= 50_000_000_000): _bad("So'ralgan summa noto'g'ri")
    if not (3 <= int(b.months) <= 60): _bad("Loyiha muddati 3–60 oy")
    dl = _date(b.deadline, "Ariza topshirish muddati")
    if dl < _today().isoformat(): _bad("Ariza topshirish muddati o'tib bo'lgan")
    now = _now()
    cur = _con.execute("""INSERT INTO grants(title,leader_id,funder,amount,status,year,program,deadline,months,note,created_by,created_at)
        VALUES(?,?,?,?,'loyiha',?,?,?,?,?,?,?)""", (title, lid, b.funder, int(b.amount), int(dl[:4]), (b.program or "").strip()[:200] or None, dl,
                                                    int(b.months), (b.note or "").strip()[:500] or None, c.user["id"], now))
    gid = cur.lastrowid
    _log("grant_log", "grant_id", gid, c, "loyiha yaratildi"); _con.commit()
    return _grant_row(_grant(gid), c)

def _add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, min(d.day, 28))

def make_reports(con, gid: int, start: dt.date, months: int):
    end = _add_months(start, months)
    k = 6
    while k < months:
        due = _add_months(start, k) + dt.timedelta(days=15)
        con.execute("INSERT INTO grant_reports(grant_id,kind,title,due) VALUES(?,?,?,?)", (gid, "oraliq", f"{k // 6}-oraliq hisobot ({k} oy)", due.isoformat()))
        k += 6
    con.execute("INSERT INTO grant_reports(grant_id,kind,title,due) VALUES(?,?,?,?)", (gid, "yakuniy", "Yakuniy hisobot", (end + dt.timedelta(days=30)).isoformat()))
    return end

class GrantAct(BaseModel):
    action: str
    note: str = ""
    amount_won: int | None = None
    start: str = ""
    months: int | None = None

def grant_act(c: Ctx, gid: int, b: GrantAct) -> dict:
    guard(c, "grantlar", f"grant amali: {b.action}", f"#{gid}")
    g = _grant(gid)
    if b.action not in _grant_acts(g, c):
        _deny(c, f"grant amali: {b.action}", f"«{GRANT_ST.get(g['status'], g['status'])}» holatida bu amal sizga ruxsat etilmagan", detail=f"#{gid}")
    now = _now(); note = (b.note or "").strip(); a = b.action
    if a == "imzoga":
        if g.get("deadline") and g["deadline"] < _today().isoformat(): _bad("Ariza topshirish muddati o'tib ketgan — loyihani yangilang")
        _con.execute("UPDATE grants SET status='imzoda' WHERE id=?", (gid,))
    elif a == "imzo":
        _con.execute("UPDATE grants SET status='imzolandi', endorsed_by=?, endorsed_at=? WHERE id=?", (c.user["id"], now, gid))
    elif a == "qaytarish":
        if len(note) < 5: _bad("Qaytarish sababini yozing")
        _con.execute("UPDATE grants SET status='loyiha', note=? WHERE id=?", (note, gid))
    elif a == "yuborish":
        _con.execute("UPDATE grants SET status='ariza berilgan', submitted_at=? WHERE id=?", (now, gid))
    elif a == "rad":
        _con.execute("UPDATE grants SET status='rad etilgan', decided_at=?, note=? WHERE id=?", (now, note or g.get("note"), gid))
    elif a == "yutildi":
        won = int(b.amount_won or 0)
        if not (1 <= won <= 50_000_000_000): _bad("Ajratilgan summani kiriting")
        st = dt.date.fromisoformat(_date(b.start or _today().isoformat(), "Boshlanish sanasi"))
        months = int(b.months or g.get("months") or 12)
        if not (3 <= months <= 60): _bad("Loyiha muddati 3–60 oy")
        end = make_reports(_con, gid, st, months)
        _con.execute("UPDATE grants SET status='bajarilmoqda', decided_at=?, amount_won=?, amount=?, start=?, end_date=?, months=?, year=? WHERE id=?",
                     (now, won, won, st.isoformat(), end.isoformat(), months, st.year, gid))
    elif a == "yakunlash":
        fin = db.one(_con, "SELECT status FROM grant_reports WHERE grant_id=? AND kind='yakuniy'", (gid,))
        if fin and fin["status"] != "qabul qilindi": _bad("Yakuniy hisobot hali qabul qilinmagan")
        _con.execute("UPDATE grants SET status='yakunlangan' WHERE id=?", (gid,))
    _log("grant_log", "grant_id", gid, c, GRANT_ST.get(_grant(gid)["status"], a), note)
    _con.commit()
    rbac.audit(_con, c, "ilmiy faoliyat: grant holati", rbac.SCIENCE, True, f"#{gid} · {g['status']} → {a}")
    return _grant_row(_grant(gid), c)

def report_act(c: Ctx, gid: int, rid: int, action: str, note: str = "") -> dict:
    guard(c, "grantlar", f"grant hisoboti: {action}", f"#{gid}/{rid}")
    g = _grant_row(_grant(gid), c)
    r = next((x for x in g["reports"] if x["id"] == rid), None)
    if not r: _bad("Hisobot topilmadi", 404)
    if action not in r["acts"]: _deny(c, f"grant hisoboti: {action}", "Bu hisobot bo'yicha amal sizga ruxsat etilmagan", detail=f"#{gid}/{rid}")
    note = (note or "").strip(); now = _now()
    if action == "topshirish":
        if len(note) < 10: _bad("Hisobot mazmunini qisqacha yozing (bajarilgan ishlar, natijalar)")
        _con.execute("UPDATE grant_reports SET status='topshirildi', note=?, submitted_at=?, submitted_by=? WHERE id=?", (note, now, c.user["id"], rid))
    elif action == "qabul":
        _con.execute("UPDATE grant_reports SET status='qabul qilindi', reviewed_at=?, reviewed_by=?, review_note=? WHERE id=?", (now, c.user["id"], note or None, rid))
    else:
        if len(note) < 5: _bad("Qaytarish sababini yozing")
        _con.execute("UPDATE grant_reports SET status='qaytarildi', reviewed_at=?, reviewed_by=?, review_note=? WHERE id=?", (now, c.user["id"], note, rid))
    _log("grant_log", "grant_id", gid, c, f"{r['title']}: {action}", note)
    _con.commit()
    return _grant_row(_grant(gid), c)

def grant_detail(c: Ctx, gid: int) -> dict:
    guard(c, "grantlar", "grant", f"#{gid}")
    g = _grant(gid)
    if not db.one(_con, f"SELECT 1 x FROM teachers t WHERE t.id=? AND {teacher_scope(c)}", (g["leader_id"],)):
        _deny(c, "grant", "Bu loyiha ko'lamingizdan tashqarida", detail=f"#{gid}")
    g = _grant_row(g, c)
    g["log"] = db.rows(_con, "SELECT at, user_name, action, note FROM grant_log WHERE grant_id=? ORDER BY id", (gid,))
    return g

# =============================================================================================
# 3. Magistrlik dissertatsiyasi
# =============================================================================================
def stage_due(entry_year: int, key: str) -> str:
    dy, mo, d = next(s[3] for s in STAGES if s[0] == key)
    return dt.date(entry_year + dy, mo, d).isoformat()

def _entry_year(course: int, ref=None) -> int: return _acad_start(ref) - (int(course or 1) - 1)

def ensure_stages(con, mid: int, course: int):
    ey = _entry_year(course)
    for k in SKEYS:
        con.execute("INSERT OR IGNORE INTO diss_stages(master_id,stage,due) VALUES(?,?,?)", (mid, k, stage_due(ey, k)))

DISS_SQL = """SELECT m.id, m.student_id, m.topic, m.supervisor_id, m.stage, s.full_name student, s.status st_status, g.name grp, g.course, g.direction,
    g.department_id, sup.full_name supervisor, sup.degree sup_degree, sup.department_id sup_dept, d.name kafedra
    FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN teachers sup ON sup.id=m.supervisor_id
    LEFT JOIN departments d ON d.id=COALESCE(sup.department_id, g.department_id)"""

def _stage_info(mid: int) -> list:
    t = _today(); soon = (t + dt.timedelta(days=SOON_DAYS)).isoformat(); ts = t.isoformat()
    out = []
    for r in db.rows(_con, "SELECT * FROM diss_stages WHERE master_id=?", (mid,)):
        r["name"] = SNAME.get(r["stage"], r["stage"]); r["status_name"] = STAGE_ST.get(r["status"], r["status"])
        r["overdue"] = r["status"] != "o'tdi" and r["due"] < ts
        r["soon"] = r["status"] != "o'tdi" and ts <= r["due"] <= soon
        out.append(r)
    out.sort(key=lambda r: SKEYS.index(r["stage"]))
    return out

def _current(stages: list):
    return next((s for s in stages if s["status"] != "o'tdi"), None)

def diss_list(c: Ctx, course=0, dept=0, flag="", q="", page=1) -> dict:
    m = guard(c, "dissertatsiya", "dissertatsiyalar ro'yxati")
    w = [diss_scope(c), "s.status IN ('faol','akademik ta''til')"]; a = []
    if course: w.append("g.course=?"); a.append(int(course))
    if dept: w.append("COALESCE(sup.department_id, g.department_id)=?"); a.append(int(dept))
    if q: w.append("(s.full_name LIKE ? OR m.topic LIKE ? OR sup.full_name LIKE ?)"); a += [f"%{q}%"] * 3
    ts = _today().isoformat(); soon = (_today() + dt.timedelta(days=SOON_DAYS)).isoformat()
    if flag == "overdue": w.append(f"EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status!='o''tdi' AND x.due<'{ts}')")
    elif flag == "soon": w.append(f"EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status!='o''tdi' AND x.due BETWEEN '{ts}' AND '{soon}')")
    elif flag == "topshirildi": w.append("EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status='topshirildi')")
    elif flag == "no_sup": w.append("m.supervisor_id IS NULL")
    W = " AND ".join(w)
    total = db.one(_con, f"SELECT COUNT(*) n FROM ({DISS_SQL} WHERE {W})", a)["n"]
    page = max(1, int(page or 1))
    rows = db.rows(_con, f"{DISS_SQL} WHERE {W} ORDER BY g.course DESC, s.full_name LIMIT 50 OFFSET ?", a + [(page - 1) * 50])
    for r in rows:
        st = _stage_info(r["id"]); cur = _current(st)
        r["current"] = cur and {"stage": cur["stage"], "name": cur["name"], "due": cur["due"], "status": cur["status"], "overdue": cur["overdue"], "soon": cur["soon"]}
        r["overdue"] = sum(1 for s in st if s["overdue"]); r["done"] = sum(1 for s in st if s["status"] == "o'tdi")
    base = f"FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN teachers sup ON sup.id=m.supervisor_id WHERE {diss_scope(c)} AND s.status IN ('faol','akademik ta''til')"
    cnt = {"all": db.one(_con, f"SELECT COUNT(*) n {base}")["n"],
           "overdue": db.one(_con, f"SELECT COUNT(*) n {base} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status!='o''tdi' AND x.due<'{ts}')")["n"],
           "soon": db.one(_con, f"SELECT COUNT(*) n {base} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status!='o''tdi' AND x.due BETWEEN '{ts}' AND '{soon}')")["n"],
           "topshirildi": db.one(_con, f"SELECT COUNT(*) n {base} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status='topshirildi')")["n"],
           "no_sup": db.one(_con, f"SELECT COUNT(*) n {base} AND m.supervisor_id IS NULL")["n"]}
    return {"rows": rows, "total": total, "page": page, "pages": max(1, math.ceil(total / 50)), "counts": cnt}

def _diss(c: Ctx, mid: int, action="dissertatsiya") -> dict:
    r = db.one(_con, f"{DISS_SQL} WHERE m.id=?", (mid,))
    if not r: _bad("Magistrant topilmadi", 404)
    if not db.one(_con, f"SELECT 1 x FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id "
                        f"LEFT JOIN teachers sup ON sup.id=m.supervisor_id WHERE m.id=? AND {diss_scope(c)}", (mid,)):
        _deny(c, action, "Bu magistrant ko'lamingizdan tashqarida", rbac.MASTERS, f"#{mid}")
    return r

def _can_stage(c: Ctx, r: dict, st: dict, prev_ok: bool) -> list:
    m = mode(c); acts = []
    sup = m == "oqituvchi" and r["supervisor_id"] == _tid(c)
    kaf = m == "kafedra"
    role = "oqituvchi" if sup else "kafedra" if kaf else "magistratura" if m == "mag" else None
    if not role or st["status"] == "o'tdi" or not prev_ok: return acts
    if st["status"] in ("kutilmoqda", "qayta") and (sup or kaf or m == "mag"): acts.append("topshirildi")
    if role in STAGE_JUDGE[st["stage"]]: acts += ["otdi", "qayta"]
    if m == "mag": acts.append("muddat")
    return acts

def diss_detail(c: Ctx, mid: int) -> dict:
    guard(c, "dissertatsiya", "magistrant dissertatsiyasi", f"#{mid}")
    r = _diss(c, mid)
    st = _stage_info(mid)
    prev_ok = True
    for s in st:
        s["acts"] = _can_stage(c, r, s, prev_ok)
        prev_ok = prev_ok and s["status"] == "o'tdi"
    r["stages"] = st
    r["log"] = db.rows(_con, "SELECT at, user_name, action, note FROM diss_log WHERE master_id=? ORDER BY id DESC LIMIT 50", (mid,))
    cur = _current(st)
    r["can_assign"] = mode(c) == "mag" or (mode(c) == "kafedra" and st and st[0]["status"] != "o'tdi")
    return r

def sup_load(tid: int, exclude_mid=None) -> int:
    return db.one(_con, f"""SELECT COUNT(*) n FROM masters m JOIN students s ON s.id=m.student_id WHERE m.supervisor_id=? AND s.status IN ('faol','akademik ta''til')
        {'AND m.id!=' + str(int(exclude_mid)) if exclude_mid else ''}""", (tid,))["n"]

class AssignIn(BaseModel):
    topic: str
    supervisor_id: int
    reason: str = ""

def diss_assign(c: Ctx, mid: int, b: AssignIn) -> dict:
    m = guard(c, "dissertatsiya", "mavzu va ilmiy rahbar", f"#{mid}", roles=("mag", "kafedra"))
    r = diss_detail(c, mid)
    if not r["can_assign"]: _deny(c, "mavzu va ilmiy rahbar", "Mavzu tasdiqlangan — o'zgartirishni faqat Magistratura bo'limi kiritadi", rbac.MASTERS, f"#{mid}")
    topic = (b.topic or "").strip()
    if len(topic) < 15: _bad("Mavzu juda qisqa (kamida 15 belgi)")
    t = _teacher(b.supervisor_id)
    if m == "kafedra" and t["department_id"] != _dept(c): _bad("Kafedra o'z o'qituvchisini ilmiy rahbar sifatida taklif qiladi")
    changed_sup = t["id"] != r["supervisor_id"]
    if changed_sup:
        if t.get("degree") not in SUP_DEGREES: _bad(f"Ilmiy rahbar ilmiy darajaga ega bo'lishi kerak (PhD yoki DSc) — {t['full_name']}: {t.get('degree') or 'darajasiz'}")
        if sup_load(t["id"], mid) >= SUP_MAX: _bad(f"{t['full_name']} rahbarligida allaqachon {SUP_MAX} ta magistrant — chegara")
    approved = r["stages"] and r["stages"][0]["status"] == "o'tdi"
    if approved and len((b.reason or "").strip()) < 5: _bad("Tasdiqlangan mavzu/rahbarni o'zgartirish sababini (bayonnoma) yozing")
    _con.execute("UPDATE masters SET topic=?, supervisor_id=? WHERE id=?", (topic, t["id"], mid))
    _con.execute("UPDATE theses SET topic=?, supervisor_id=?, updated_at=?, updated_by=? WHERE student_id=?", (topic, t["id"], _now(), c.user["id"], r["student_id"]))
    _log("diss_log", "master_id", mid, c, "mavzu / ilmiy rahbar" + (" o'zgartirildi" if approved else " belgilandi"),
         f"{topic} · {t['full_name']}" + (f" · sabab: {b.reason.strip()}" if approved else ""))
    _con.commit()
    return diss_detail(c, mid)

class StageIn(BaseModel):
    stage: str
    action: str
    note: str = ""
    protocol: str = ""
    score: int | None = None
    due: str = ""

def diss_stage(c: Ctx, mid: int, b: StageIn) -> dict:
    guard(c, "dissertatsiya", f"bosqich: {b.stage} · {b.action}", f"#{mid}", roles=("mag", "kafedra", "oqituvchi"))
    r = diss_detail(c, mid)
    s = next((x for x in r["stages"] if x["stage"] == b.stage), None)
    if not s: _bad("Bosqich topilmadi", 404)
    if b.action not in s["acts"]:
        why = ("oldingi bosqich hali o'tmagan" if s["status"] != "o'tdi" and not s["acts"] and any(x["status"] != "o'tdi" for x in r["stages"][:SKEYS.index(b.stage)])
               else "bu bosqich natijasini boshqa bo'linma qayd etadi")
        _deny(c, f"bosqich: {b.stage}", f"{SNAME[b.stage]}: {why}", rbac.MASTERS, f"#{mid}")
    note = (b.note or "").strip(); proto = (b.protocol or "").strip(); now = _now(); ts = _today().isoformat()
    need_proto = next(x[4] for x in STAGES if x[0] == b.stage)
    if b.action == "topshirildi":
        _con.execute("UPDATE diss_stages SET status='topshirildi', submitted_at=?, note=? WHERE id=?", (now, note or None, s["id"]))
        msg = "material topshirildi"
    elif b.action == "otdi":
        if need_proto and len(proto) < 2: _bad(f"{SNAME[b.stage]}: bayonnoma raqami va sanasini kiriting")
        if b.stage == "mavzu" and (not r["topic"] or not r["supervisor_id"]): _bad("Avval mavzu va ilmiy rahbarni belgilang")
        score = None
        if b.stage == "himoya":
            if b.score is None or not (0 <= int(b.score) <= 100): _bad("Himoya bahosini kiriting (0–100)")
            score = int(b.score)
            if score < DEFENSE_PASS: _bad(f"{score} ball — himoyadan o'tmagan ({DEFENSE_PASS} dan past): «Qayta» ni tanlang")
        _con.execute("UPDATE diss_stages SET status='o''tdi', done_at=?, protocol=?, score=?, note=?, by_user=? WHERE id=?",
                     (ts, proto or None, score, note or None, c.user["id"], s["id"]))
        _con.execute("UPDATE masters SET stage=? WHERE id=?", (SLABEL[b.stage], mid))
        if b.stage == "dastlabki":
            _con.execute("UPDATE theses SET status='himoyaga tayyor', updated_at=?, updated_by=? WHERE student_id=? AND status!='himoya qilindi'", (now, c.user["id"], r["student_id"]))
        if b.stage == "himoya":
            _con.execute("UPDATE theses SET status='himoya qilindi', score=?, defense_date=?, updated_at=?, updated_by=? WHERE student_id=?",
                         (score, ts, now, c.user["id"], r["student_id"]))
        msg = "o'tdi" + (f" · {score} ball" if score is not None else "")
    elif b.action == "qayta":
        if len(note) < 5: _bad("Kamchiliklarni yozing (qayta topshirish sababi)")
        nd = max(s["due"], (_today() + dt.timedelta(days=30)).isoformat())
        _con.execute("UPDATE diss_stages SET status='qayta', due=?, note=?, protocol=?, by_user=? WHERE id=?", (nd, note, proto or None, c.user["id"], s["id"]))
        msg = f"qayta topshirish · yangi muddat {nd}"
    else:
        nd = _date(b.due, "Yangi muddat")
        if nd < ts: _bad("Yangi muddat o'tgan sana bo'lmasin")
        if len(note) < 5: _bad("Muddatni o'zgartirish sababini yozing")
        _con.execute("UPDATE diss_stages SET due=? WHERE id=?", (nd, s["id"]))
        msg = f"muddat {s['due']} → {nd}"
    _log("diss_log", "master_id", mid, c, f"{SNAME[b.stage]}: {msg}", " · ".join(x for x in (proto and f"bayonnoma {proto}", note) if x))
    _con.commit()
    rbac.audit(_con, c, "ilmiy faoliyat: dissertatsiya bosqichi", rbac.MASTERS, True, f"#{mid} · {b.stage} · {b.action}")
    return diss_detail(c, mid)

def diss_stats(c: Ctx) -> dict:
    ts = _today().isoformat()
    base = f"""FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN teachers sup ON sup.id=m.supervisor_id
               WHERE {diss_scope(c)} AND s.status IN ('faol','akademik ta''til')"""
    by_course = []
    for co in (1, 2):
        n = db.one(_con, f"SELECT COUNT(*) n {base} AND g.course={co}")["n"]
        stg = {k: db.one(_con, f"SELECT COUNT(*) n {base} AND g.course={co} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.stage='{k}' AND x.status='o''tdi')")["n"] for k in SKEYS}
        od = db.one(_con, f"SELECT COUNT(*) n {base} AND g.course={co} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status!='o''tdi' AND x.due<'{ts}')")["n"]
        by_course.append({"course": co, "n": n, "passed": stg, "overdue": od})
    overdue_by_stage = {r["stage"]: r["n"] for r in db.rows(_con, f"""SELECT x.stage, COUNT(*) n {base.replace('WHERE', 'JOIN diss_stages x ON x.master_id=m.id WHERE', 1)}
        AND x.status!='o''tdi' AND x.due<'{ts}' GROUP BY 1""")}
    sups = db.rows(_con, f"""SELECT sup.full_name, sup.degree, COUNT(*) n {base} AND m.supervisor_id IS NOT NULL GROUP BY m.supervisor_id ORDER BY n DESC LIMIT 8""")
    return {"by_course": by_course, "overdue_by_stage": overdue_by_stage, "stages": [{"key": k, "name": SNAME[k]} for k in SKEYS],
            "supervisors": sups if mode(c) not in ("lead", "kengash") else [], "sup_max": SUP_MAX}

# =============================================================================================
# Umumiy: ko'rsatkichlar va ogohlantirishlar
# =============================================================================================
def overview(c: Ctx) -> dict:
    m = guard(c, "umumiy", "ilmiy faoliyat ko'rsatkichlari")
    y = _today().year
    out = {"year": y, "mode": m}
    ts = _today().isoformat()
    if "nashrlar" in TABS[m] or m in ("kengash", "lead", "mag", "oquv"):
        if m not in ("mag", "oquv"):
            out["depts"] = dept_stats(c, y)
            gs = db.rows(_con, f"SELECT g.status, COUNT(*) n, SUM(COALESCE(g.amount_won, CASE WHEN g.status IN ('bajarilmoqda','yakunlangan') THEN g.amount END)) won FROM grants g JOIN teachers t ON t.id=g.leader_id WHERE {teacher_scope(c)} GROUP BY 1")
            out["grants"] = {r["status"]: {"n": r["n"], "won": r["won"] or 0, "name": GRANT_ST.get(r["status"], r["status"])} for r in gs}
            out["reports_overdue"] = db.one(_con, f"""SELECT COUNT(*) n FROM grant_reports r JOIN grants g ON g.id=r.grant_id JOIN teachers t ON t.id=g.leader_id
                WHERE {teacher_scope(c)} AND g.status='bajarilmoqda' AND r.status IN ('kutilmoqda','qaytarildi') AND r.due<?""", (ts,))["n"]
            out["pubs_pending"] = {r["status"]: r["n"] for r in db.rows(_con, f"""SELECT p.status, COUNT(*) n FROM pub_subs p JOIN teachers t ON t.id=p.teacher_id
                WHERE {teacher_scope(c)} AND p.status IN ('kafedra','ilmiy','qaytarildi') GROUP BY 1""")}
    if m in ("ilmiy", "prorektor", "mag", "kafedra", "lead", "oquv", "kengash"):
        out["diss"] = diss_stats(c)
    return out

def alerts(c: Ctx) -> list:
    m = mode(c)
    if not m: return []
    ts = _today().isoformat(); out = []
    if m in ("kafedra", "ilmiy"):
        n = db.one(_con, f"SELECT COUNT(*) n FROM pub_subs p JOIN teachers t ON t.id=p.teacher_id WHERE {teacher_scope(c)} AND p.status=?",
                   ("kafedra" if m == "kafedra" else "ilmiy",))["n"]
        if n: out.append({"kind": "pubs", "n": n, "text": f"{n} ta nashr arizasi tekshiruvingizni kutmoqda", "tab": "nashrlar"})
    if m == "oqituvchi":
        n = db.one(_con, "SELECT COUNT(*) n FROM pub_subs WHERE teacher_id=? AND status='qaytarildi'", (_tid(c),))["n"]
        if n: out.append({"kind": "pubs", "n": n, "text": f"{n} ta nashr arizangiz qaytarildi — tuzating", "tab": "nashrlar"})
    if m == "prorektor":
        n = db.one(_con, "SELECT COUNT(*) n FROM grants WHERE status='imzoda'")["n"]
        if n: out.append({"kind": "grants", "n": n, "text": f"{n} ta grant arizasi imzongizni kutmoqda", "tab": "grantlar"})
    if m in ("ilmiy", "kafedra", "oqituvchi", "prorektor"):
        n = db.one(_con, f"""SELECT COUNT(*) n FROM grant_reports r JOIN grants g ON g.id=r.grant_id JOIN teachers t ON t.id=g.leader_id
            WHERE {teacher_scope(c)} AND g.status='bajarilmoqda' AND r.status IN ('kutilmoqda','qaytarildi') AND r.due<?""", (ts,))["n"]
        if n: out.append({"kind": "reports", "n": n, "text": f"{n} ta grant hisobotining muddati o'tgan", "tab": "grantlar"})
        if m == "ilmiy":
            n = db.one(_con, "SELECT COUNT(*) n FROM grant_reports r JOIN grants g ON g.id=r.grant_id WHERE g.status='bajarilmoqda' AND r.status='topshirildi'")["n"]
            if n: out.append({"kind": "reports", "n": n, "text": f"{n} ta grant hisoboti qabulingizni kutmoqda", "tab": "grantlar"})
    if m in ("mag", "kafedra", "oqituvchi"):
        base = f"""FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id LEFT JOIN teachers sup ON sup.id=m.supervisor_id
                   WHERE {diss_scope(c)} AND s.status IN ('faol','akademik ta''til')"""
        n = db.one(_con, f"SELECT COUNT(*) n {base} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status!='o''tdi' AND x.due<?)", (ts,))["n"]
        if n: out.append({"kind": "diss", "n": n, "text": f"{n} ta magistrantda dissertatsiya bosqichi muddati o'tgan", "tab": "dissertatsiya", "flag": "overdue"})
        n = db.one(_con, f"SELECT COUNT(*) n {base} AND EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id AND x.status='topshirildi')")["n"]
        if n: out.append({"kind": "diss", "n": n, "text": f"{n} ta magistrant materiali ko'rib chiqishni kutmoqda", "tab": "dissertatsiya", "flag": "topshirildi"})
    return out

def meta(c: Ctx) -> dict:
    m = guard(c, "meta", "ilmiy faoliyat")
    depts = db.rows(_con, "SELECT id, name FROM departments ORDER BY id")
    if m == "kafedra": depts = [d for d in depts if d["id"] == _dept(c)]
    return {"mode": m, "note": MODE_NOTE[m], "tabs": TABS[m], "kinds": KINDS, "indexed": list(INDEXED), "quartiles": QUARTILES, "pub_st": PUB_ST,
            "grant_st": GRANT_ST, "funders": FUNDERS, "stages": [{"key": s[0], "name": s[1], "protocol": s[4]} for s in STAGES], "stage_st": STAGE_ST,
            "depts": depts, "year": _today().year, "today": _today().isoformat(), "teacher_id": _tid(c) or None, "dept_id": _dept(c) or None,
            "can": {"pub_create": m in ("oqituvchi", "kafedra", "ilmiy"), "grant_create": m in ("oqituvchi", "kafedra", "ilmiy"),
                    "plan": m in ("ilmiy", "prorektor"), "diss_edit": m in ("mag", "kafedra", "oqituvchi")},
            "sup_max": SUP_MAX, "sup_degrees": list(SUP_DEGREES), "defense_pass": DEFENSE_PASS, "alerts": alerts(c)}

def teachers_pick(c: Ctx, q: str) -> list:
    guard(c, "meta", "o'qituvchi qidiruvi", q[:40])
    if mode(c) not in ("ilmiy", "kafedra", "mag"): return []
    w = "1=1" if mode(c) != "kafedra" else f"t.department_id={_dept(c)}"
    rs = db.rows(_con, f"""SELECT t.id, t.full_name, t.degree, t.position, d.name kafedra FROM teachers t LEFT JOIN departments d ON d.id=t.department_id
        WHERE {w} AND t.full_name LIKE ? ORDER BY t.full_name LIMIT 15""", (f"%{q}%",))
    for r in rs: r["load"] = sup_load(r["id"])
    return rs

# =============================================================================================
# Demo ma'lumot (bir martalik, sintetik): navbatdagi arizalar, rejalar, grant bosqichlari va hisobotlar, dissertatsiya bosqichlari
# =============================================================================================
PUB_TITLES = ["Raqamli iqtisodiyotda kichik biznesni qo'llab-quvvatlash mexanizmlari", "Hududiy innovatsion salohiyatni baholash metodikasi",
              "Oliy ta'limda masofaviy o'qitish samaradorligi tahlili", "Tijorat banklarida kredit riskini boshqarishning zamonaviy usullari",
              "Talabalarning kasbiy motivatsiyasini shakllantirish omillari", "Xizmat ko'rsatish sohasida mijozlar sodiqligini oshirish",
              "Soliq yukining korxona investitsion faolligiga ta'siri", "Ingliz tilini o'qitishda kommunikativ yondashuv",
              "Xalqaro moliyaviy hisobot standartlariga o'tish muammolari", "Mehnat bozorida yoshlar bandligini ta'minlash yo'llari",
              "Klaster yondashuvi asosida qishloq xo'jaligini rivojlantirish", "Davlat-xususiy sheriklik loyihalarini baholash",
              "Pedagogik texnologiyalar asosida mustaqil ta'limni tashkil etish", "Logistika xarajatlarini optimallashtirish modeli",
              "Inflyatsiya va valyuta kursi o'rtasidagi bog'liqlikning ekonometrik tahlili", "Turizm xizmatlari bozorida raqobatbardoshlik"]
JOURNALS = {"Scopus": ["Journal of Economics and Finance", "Sustainability", "Economies", "Education Sciences"],
            "Web of Science": ["Problems and Perspectives in Management", "Journal of Eastern European and Central Asian Research"],
            "OAK jurnali": ["Iqtisodiyot va innovatsion texnologiyalar", "Xalqaro moliya va hisob", "Pedagogika", "Biznes-Ekspert"],
            "Xorijiy jurnal": ["European Journal of Business", "International Journal of Social Science"],
            "Mahalliy jurnal": ["ISFT ilmiy axborotnomasi"], "Monografiya": ["Fan va texnologiya nashriyoti"],
            "Darslik / o'quv qo'llanma": ["Iqtisodiyot nashriyoti"], "Konferensiya tezisi": ["Respublika ilmiy-amaliy konferensiyasi to'plami"]}

def seed(con):
    if db.one(con, "SELECT v FROM ilmiy_meta WHERE k='seeded'"): return
    if not db.one(con, "SELECT COUNT(*) n FROM teachers")["n"]: return
    R = random.Random(2026)
    now = clock.now_iso(); today = clock.today(); y = today.year
    sys_u = (db.one(con, "SELECT id FROM users WHERE role='ilmiy_bolim' ORDER BY id LIMIT 1") or {"id": None})["id"]
    teachers = db.rows(con, "SELECT id, department_id FROM teachers ORDER BY id")
    # --- kafedra rejalari
    for d in db.rows(con, "SELECT d.id, (SELECT COUNT(*) FROM teachers t WHERE t.department_id=d.id) n FROM departments d"):
        con.execute("INSERT OR IGNORE INTO sci_plans(dept_id,year,scopus,oak,by_user,at) VALUES(?,?,?,?,?,?)",
                    (d["id"], y, max(2, math.ceil(d["n"] * 0.2)), max(5, d["n"]), sys_u, now))
    # --- nashr arizalari: navbatdagilar va tasdiqlanganlar (mavjud reyestr yozuvlariga bog'langan)
    me = db.one(con, "SELECT teacher_id FROM users WHERE role='oqituvchi' AND teacher_id IS NOT NULL ORDER BY id LIMIT 1")
    pool = [t["id"] for t in teachers]
    plan = ["kafedra"] * 12 + ["ilmiy"] * 9 + ["qaytarildi"] * 3
    for i, st in enumerate(plan):
        tid = me["teacher_id"] if (me and i in (0, 12, 21)) else R.choice(pool)
        kind = R.choice(["Scopus", "OAK jurnali", "OAK jurnali", "Xorijiy jurnal", "Konferensiya tezisi", "Web of Science", "Monografiya"])
        title = f"{R.choice(PUB_TITLES)}" + R.choice(["", " (O'zbekiston misolida)", ": nazariy va amaliy jihatlar", " — empirik tahlil"])
        if db.one(con, "SELECT 1 x FROM pub_subs WHERE teacher_id=? AND title=?", (tid, title)): title += f" ({i + 1})"
        doi = f"10.{R.randint(3000, 9999)}/isft.{y}.{R.randint(1000, 9999)}" if kind in INDEXED or R.random() < 0.3 else None
        at = (dt.datetime.combine(today, dt.time(10)) - dt.timedelta(days=R.randint(1, 25), hours=R.randint(0, 6))).isoformat(timespec="seconds")
        cur = con.execute("""INSERT INTO pub_subs(teacher_id,title,kind,journal,year,doi,url,quartile,status,note,created_at,kaf_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (tid, title, kind, R.choice(JOURNALS[kind]), y, doi,
            f"https://www.scopus.com/record/display.uri?eid=2-s2.0-{R.randint(10**10, 10**11)}" if kind == "Scopus" else None,
            R.choice(QUARTILES) if kind in INDEXED else None, st,
            "DOI havolasi ochilmaydi va jurnal OAK ro'yxatida emas — tekshirib qayta yuboring" if st == "qaytarildi" else None,
            at, at if st == "ilmiy" else None, at))
        con.execute("INSERT INTO pub_log(sub_id,at,user_name,action,note) VALUES(?,?,?,?,?)", (cur.lastrowid, at, "Demo", "yuborildi", PUB_ST[st]))
    for p in db.rows(con, f"SELECT id, teacher_id, title, kind, year FROM publications WHERE year={y} ORDER BY id DESC LIMIT 40"):
        cur = con.execute("""INSERT INTO pub_subs(teacher_id,title,kind,journal,year,status,created_at,pub_id,updated_at) VALUES(?,?,?,?,?,'tasdiqlangan',?,?,?)""",
                          (p["teacher_id"], p["title"], p["kind"], R.choice(JOURNALS.get(p["kind"], ["—"])), p["year"], now, p["id"], now))
        con.execute("UPDATE publications SET sub_id=?, journal=COALESCE(journal,?) WHERE id=?", (cur.lastrowid, R.choice(JOURNALS.get(p["kind"], ["—"])), p["id"]))
    # --- grantlar: mavjudlarga sana va hisobotlar; yangi loyihalar
    for g in db.rows(con, "SELECT * FROM grants ORDER BY id"):
        if g["status"] in ("bajarilmoqda", "yakunlangan"):
            months = 24 if g["status"] == "bajarilmoqda" else 12
            st = dt.date(int(g["year"] or y) - (1 if g["status"] == "bajarilmoqda" else 0), R.choice([2, 3, 4]), 1)
            if g["status"] == "yakunlangan": st = dt.date(int(g["year"] or y) - 1, 3, 1)
            end = make_reports(con, g["id"], st, months)
            for r in db.rows(con, "SELECT * FROM grant_reports WHERE grant_id=? ORDER BY due", (g["id"],)):
                if g["status"] == "yakunlangan" or r["due"] < (today - dt.timedelta(days=150)).isoformat():
                    con.execute("UPDATE grant_reports SET status='qabul qilindi', submitted_at=?, reviewed_at=? WHERE id=?", (r["due"], r["due"], r["id"]))
                elif r["due"] < today.isoformat():
                    if R.random() < 0.5:
                        con.execute("UPDATE grant_reports SET status='topshirildi', submitted_at=?, note=? WHERE id=?",
                                    (r["due"], "Rejadagi tadqiqot bosqichi bajarildi: so'rovnoma o'tkazildi, 2 ta maqola tayyorlandi.", r["id"]))
            con.execute("UPDATE grants SET start=?, end_date=?, months=?, amount_won=amount, decided_at=?, submitted_at=? WHERE id=?",
                        (st.isoformat(), end.isoformat(), months, (st - dt.timedelta(days=20)).isoformat(), (st - dt.timedelta(days=90)).isoformat(), g["id"]))
        elif g["status"] == "ariza berilgan":
            con.execute("UPDATE grants SET submitted_at=?, deadline=?, months=24 WHERE id=?",
                        ((today - dt.timedelta(days=R.randint(10, 80))).isoformat(), (today - dt.timedelta(days=R.randint(5, 9))).isoformat(), g["id"]))
        elif g["status"] == "rad etilgan":
            con.execute("UPDATE grants SET decided_at=?, note=? WHERE id=?", ((today - dt.timedelta(days=R.randint(30, 200))).isoformat(),
                        "Tanlov komissiyasi: byudjet asoslanmagan, xalqaro hamkor ishtiroki yo'q", g["id"]))
    tid0 = me["teacher_id"] if me else pool[0]
    for title, funder, amount, st, lid in [("Raqamli moliyaviy savodxonlik: talabalar uchun onlayn kurs ishlab chiqish", "Innovatsion rivojlanish agentligi", 320_000_000, "loyiha", tid0),
                                           ("Hududlarda kichik biznes ekotizimini baholash platformasi", "Vazirlik", 540_000_000, "imzoda", R.choice(pool)),
                                           ("Oliy ta'limda inklyuziv ta'lim modelini joriy etish", "Erasmus+", 780_000_000, "imzolandi", R.choice(pool))]:
        cur = con.execute("""INSERT INTO grants(title,leader_id,funder,amount,status,year,program,deadline,months,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (title, lid, funder, amount, st, y, "Amaliy tadqiqotlar tanlovi", (today + dt.timedelta(days=R.randint(15, 40))).isoformat(), 24, now))
        con.execute("INSERT INTO grant_log(grant_id,at,user_name,action) VALUES(?,?,?,?)", (cur.lastrowid, now, "Demo", GRANT_ST[st]))
    # --- dissertatsiya bosqichlari (mavjud masters.stage dan): 1-kurs — joriy o'quv yili boshlangan, 2-kurs — o'tgan yil
    lab2i = {"Mavzu tasdiqlangan": 0, "1-bob tayyor": 1, "2-bob tayyor": 2, "Dastlabki himoya": 4}
    ms = db.rows(con, "SELECT m.id, m.stage, g.course FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id")
    for r in ms:
        course = int(r["course"] or 1)
        ensure_stages(con, r["id"], course)
        if course <= 1:   # birinchi yil: mavzu 15-noyabrgacha tasdiqlanadi
            x = R.random()
            done = 0 if x < 0.45 else -1
            if done == -1:
                con.execute("UPDATE masters SET stage='Mavzu tanlanmoqda' WHERE id=?", (r["id"],))
                if x < 0.75: con.execute("UPDATE diss_stages SET status='topshirildi', submitted_at=? WHERE master_id=? AND stage='mavzu'",
                                         ((today - dt.timedelta(days=R.randint(1, 20))).isoformat(), r["id"]))
                continue
            con.execute("UPDATE masters SET stage=? WHERE id=?", (SLABEL["mavzu"], r["id"]))
        else:
            done = lab2i.get(r["stage"], 0)
        ey = _entry_year(course)
        for i in range(done + 1):
            k = SKEYS[i]; due = dt.date.fromisoformat(stage_due(ey, k))
            dd = min(due - dt.timedelta(days=R.randint(0, 25)), today - dt.timedelta(days=1))
            con.execute("UPDATE diss_stages SET status='o''tdi', done_at=?, protocol=? WHERE master_id=? AND stage=?",
                        (dd.isoformat(), f"№{R.randint(2, 9)}, {dd.strftime('%d.%m.%Y')}" if STAGES[i][4] else None, r["id"], k))
        if course >= 2 and done < len(SKEYS) - 1 and R.random() < 0.15:
            con.execute("UPDATE diss_stages SET status='topshirildi', submitted_at=? WHERE master_id=? AND stage=?",
                        ((today - dt.timedelta(days=R.randint(1, 15))).isoformat(), r["id"], SKEYS[done + 1]))
    con.execute("INSERT OR REPLACE INTO ilmiy_meta(k,v) VALUES('seeded',?)", (now,))
    con.commit()

def init(con):
    try:
        con.executescript(SCHEMA)
        for t, cols in ALTERS.items():
            have = {r["name"] for r in db.rows(con, f"PRAGMA table_info({t})")}
            if not have: continue
            for col, typ in cols:
                if col not in have: con.execute(f"ALTER TABLE {t} ADD COLUMN {col} {typ}")
        con.commit()
        seed(con)
        # yangi magistrantlar (qabul / ko'chirish) uchun bosqichlar
        for r in db.rows(con, """SELECT m.id, g.course FROM masters m JOIN students s ON s.id=m.student_id LEFT JOIN groups_ g ON g.id=s.group_id
                                 WHERE NOT EXISTS(SELECT 1 FROM diss_stages x WHERE x.master_id=m.id)"""):
            ensure_stages(con, r["id"], r["course"])
        con.commit()
    except Exception as e:
        print("ilmiy.init:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

@router.get(P + "/meta")
def api_meta(request: Request): return meta(C(request))

@router.get(P + "/overview")
def api_overview(request: Request): return overview(C(request))

@router.get(P + "/teachers")
def api_teachers(request: Request, q: str = ""): return teachers_pick(C(request), q)

@router.get(P + "/pubs")
def api_pubs(request: Request, status: str = "", dept: int = 0, q: str = "", kind: str = ""):
    c = C(request); guard(c, "nashrlar", "nashr arizalari", status); return pubs_list(c, status, dept, q, kind)

@router.get(P + "/registry")
def api_registry(request: Request, dept: int = 0, kind: str = "", year: int = 0, q: str = "", page: int = 1):
    c = C(request); guard(c, "nashrlar", "nashrlar reyestri"); return registry(c, dept, kind, year, q, page)

@router.get(P + "/pubs/{sid}")
def api_pub(sid: int, request: Request): return pub_detail(C(request), sid)

@router.post(P + "/pubs")
def api_pub_create(b: PubIn, request: Request): return create_pub(C(request), b)

@router.post(P + "/pubs/{sid}/edit")
def api_pub_edit(sid: int, b: PubIn, request: Request): return edit_pub(C(request), sid, b)

class ReviewIn(BaseModel):
    decision: str
    note: str = ""
    indexed: bool = False
    quartile: str = ""

@router.post(P + "/pubs/{sid}/review")
def api_pub_review(sid: int, b: ReviewIn, request: Request): return review_pub(C(request), sid, b.decision, b.note, b.indexed, b.quartile)

@router.post(P + "/pubs/{sid}/withdraw")
def api_pub_withdraw(sid: int, request: Request): return withdraw_pub(C(request), sid)

class PlanIn(BaseModel):
    dept_id: int
    year: int
    scopus: int
    oak: int

@router.post(P + "/plans")
def api_plan(b: PlanIn, request: Request):
    c = C(request); set_plan(c, b.dept_id, b.year, b.scopus, b.oak); return {"ok": True, "depts": dept_stats(c, b.year)}

@router.get(P + "/grants")
def api_grants(request: Request, status: str = "", q: str = ""):
    c = C(request); guard(c, "grantlar", "grantlar ro'yxati", status); return grants_list(c, status, q)

@router.get(P + "/grants/{gid}")
def api_grant(gid: int, request: Request): return grant_detail(C(request), gid)

@router.post(P + "/grants")
def api_grant_create(b: GrantIn, request: Request): return create_grant(C(request), b)

@router.post(P + "/grants/{gid}/act")
def api_grant_act(gid: int, b: GrantAct, request: Request): return grant_act(C(request), gid, b)

class RepIn(BaseModel):
    action: str
    note: str = ""

@router.post(P + "/grants/{gid}/reports/{rid}")
def api_grant_report(gid: int, rid: int, b: RepIn, request: Request): return report_act(C(request), gid, rid, b.action, b.note)

@router.get(P + "/diss")
def api_diss(request: Request, course: int = 0, dept: int = 0, flag: str = "", q: str = "", page: int = 1):
    return diss_list(C(request), course, dept, flag, q, page)

@router.get(P + "/diss/{mid}")
def api_diss_one(mid: int, request: Request): return diss_detail(C(request), mid)

@router.post(P + "/diss/{mid}/assign")
def api_diss_assign(mid: int, b: AssignIn, request: Request): return diss_assign(C(request), mid, b)

@router.post(P + "/diss/{mid}/stage")
def api_diss_stage(mid: int, b: StageIn, request: Request): return diss_stage(C(request), mid, b)
