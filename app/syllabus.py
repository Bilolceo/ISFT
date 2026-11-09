"""«O'quv dasturlari» — Akademik faoliyatni boshqarish bo'limi vositalari.

1. Sillabus (fan dasturi) oqimi:
   Akademik bo'lim so'raydi (fan × kafedra, o'qituvchi-guruh bog'lanishlaridan) → kafedra mudiri o'qituvchini biriktiradi (muddat bilan)
   → o'qituvchi tuzadi (haftalik mavzular, soatlar, adabiyot, baholash) yoki DOCX/PDF yuklaydi (mavzular ajratib olinadi) → topshiradi
   → Akademik bo'lim tekshiradi: (a) mavzular fanga mosligi (kalit so'z o'zaklari; mahalliy AI bo'lsa — qo'shimcha AI tekshiruvi),
     (b) tayanch OTM dasturlari bilan solishtirish (qamrov %, yetishmayotgan / ortiqcha mavzular — katalog NAMUNA ma'lumot),
     (c) soatlar o'quv reja me'yoriga mosligi (kredit × 30 soat, turlar bo'yicha taqsimot)
   → izoh bilan qaytaradi (versiyalar saqlanadi) yoki kelishuvga yuboradi: kafedra mudiri → Akademik bo'lim → o'quv ishlari prorektori tasdiqlaydi.
2. O'quv yuklama kalkulyatori: fan × guruhlar × potoklar × soat turi (ma'ruza — potokka, amaliy/seminar — guruhga, laboratoriya — kichik guruhga)
   → o'qituvchi va kafedra kesimida soatlar, stavka me'yori (documents.LOAD_NORM) va joriy teachers.load_hours bilan solishtirish;
   XLSX eksport va Hujjatlar markazidagi «O'quv yuklama taqsimoti» (documents.g_load) hujjatiga hisob-kitob bo'limi.
3. Kafedralarga so'rovlar: Akademik bo'lim bir yoki bir nechta kafedraga topshiriq yuboradi (yuklama rejasi, sillabus yangilash, solishtirma),
   kafedra natijani (matn/fayl) qaytaradi, bo'lim qabul qiladi yoki izoh bilan qayta ishlashga qaytaradi — tarix saqlanadi.
   (Portal xatlarida «qabul / qayta ishlashga qaytarish» amali yo'q — shu sababli ko'rib chiqish shu modul ichida, faqat o'quv dasturi va yuklama so'rovlari uchun.)

Ruxsatlar: Akademik bo'lim — hammasi; o'quv ishlari prorektori — hammasini ko'radi, yakuniy tasdiqlaydi; rektor — faqat ko'rish;
kafedra mudiri — o'z kafedrasi; o'qituvchi — o'ziga biriktirilgan fanlar. Har bir holat o'zgarishi audit jurnaliga (resurs: syllabus) yoziladi.
"""
import datetime as dt, io, json, math, re, secrets
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from . import db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
FILES = Path(__file__).resolve().parent.parent / "data" / "syllabus"
MAX_BYTES = 10 * 1024 * 1024
SEMESTER = "2026-2027 o'quv yili · kuzgi semestr"
H_PER_CREDIT = 30            # 1 kredit = 30 soat (auditoriya + mustaqil ta'lim)
REVIEW_DAYS = 3              # tekshiruv / kelishuv bosqichi uchun ichki muddat (ish kuni emas, kalendar kun)
TOL = 2                      # soatlar me'yoridan ruxsat etilgan farq

ROLE_ALL = ("akademik", "prorektor_oquv", "rektor")
ROLES_IN = ROLE_ALL + ("kafedra", "oqituvchi")

STATUS = {"soralgan": "So'ralgan", "jarayonda": "Tayyorlanmoqda", "qaytarilgan": "Qaytarilgan", "tekshiruvda": "Tekshiruvda",
          "kelishuvda": "Kelishuvda", "tasdiqlangan": "Tasdiqlangan"}
STAGES = {"kafedra": "Kafedra mudiri", "akademik": "Akademik bo'lim", "prorektor": "O'quv ishlari prorektori"}
OPEN_WORK = ("soralgan", "jarayonda", "qaytarilgan")          # muddat shu holatlarda nazorat qilinadi
HOUR_KEYS = [("lecture", "Ma'ruza"), ("practice", "Amaliy"), ("seminar", "Seminar"), ("lab", "Laboratoriya"), ("self", "Mustaqil ta'lim")]
TASK_KINDS = {"yuklama": "O'quv yuklama rejasi", "sillabus": "Sillabus yangilash", "dastur": "Fan dasturi / solishtirma"}
UNIT_ST = {"yangi": "Javob kutilmoqda", "topshirildi": "Ko'rib chiqilmoqda", "qabul": "Qabul qilindi", "qayta": "Qayta ishlashga qaytarildi"}

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def today() -> dt.date:
    from . import services as S
    return S.TODAY

def _now() -> str: return dt.datetime.now().isoformat(timespec="seconds")

# =============================================================================================
# Jadvallar
# =============================================================================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS syl_items(id INTEGER PRIMARY KEY, subject TEXT, department_id INT, semester TEXT, field TEXT,
  teacher_id INT, status TEXT, stage TEXT, due TEXT, credits INT, n_lecture INT, n_practice INT, n_seminar INT, n_lab INT, n_self INT,
  draft TEXT, version INT DEFAULT 0, note TEXT, requested_by INT, requested_at TEXT, assigned_at TEXT, submitted_at TEXT,
  approved_at TEXT, updated_at TEXT, reminded_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS syl_items_u ON syl_items(subject, department_id, semester);
CREATE TABLE IF NOT EXISTS syl_versions(id INTEGER PRIMARY KEY, item_id INT, version INT, content TEXT, file_name TEXT, file_path TEXT,
  source TEXT, created_at TEXT, author TEXT, check_json TEXT);
CREATE INDEX IF NOT EXISTS syl_versions_i ON syl_versions(item_id, version);
CREATE TABLE IF NOT EXISTS syl_log(id INTEGER PRIMARY KEY, ref_type TEXT, ref_id INT, ts TEXT, user_id INT, user_name TEXT, role TEXT,
  action TEXT, from_status TEXT, to_status TEXT, comment TEXT, version INT);
CREATE INDEX IF NOT EXISTS syl_log_i ON syl_log(ref_type, ref_id);
CREATE TABLE IF NOT EXISTS syl_ref(id INTEGER PRIMARY KEY, subject TEXT, university TEXT, topics TEXT, description TEXT, sample INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS syl_tasks(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, body TEXT, due TEXT, created_by INT, created_name TEXT,
  created_at TEXT, status TEXT DEFAULT 'ochiq');
CREATE TABLE IF NOT EXISTS syl_task_units(id INTEGER PRIMARY KEY, task_id INT, department_id INT, status TEXT, response TEXT, file_name TEXT,
  file_path TEXT, submitted_at TEXT, reviewed_at TEXT, comment TEXT, round INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS syl_load_plans(department_id INTEGER PRIMARY KEY, params TEXT, updated_at TEXT, updated_by INT);
"""

def init_tables(con):
    con.executescript(SCHEMA); con.commit()

def init(con):
    """Jadvallar + (bo'sh bo'lsa) demo holat. Server ishga tushganda chaqiriladi; mavjud ma'lumotga tegmaydi."""
    init_tables(con)
    try:
        if db.one(con, "SELECT 1 x FROM users") and not db.one(con, "SELECT 1 x FROM syl_items"):
            from . import seed_syllabus
            print("syllabus seed:", seed_syllabus.run(con))
        elif not db.one(con, "SELECT 1 x FROM syl_ref"):
            from . import seed_syllabus
            con.executemany("INSERT INTO syl_ref(subject, university, topics, description, sample) VALUES(?,?,?,?,1)", seed_syllabus.ref_rows()); con.commit()
    except Exception as e:   # demo ma'lumot bo'lmasa ham modul ishlashi kerak
        print("syllabus seed xato:", repr(e))

# =============================================================================================
# O'quv reja me'yorlari (kredit va soat turlari)
# =============================================================================================
NORMS = {   # soha: (kredit, ma'ruza, amaliy, seminar, laboratoriya) — qolgani mustaqil ta'lim
    "iqt": (6, 30, 30, 0, 0), "biz": (6, 30, 30, 0, 0), "it": (6, 30, 0, 0, 30), "til": (4, 0, 60, 0, 0),
    "gum": (4, 30, 0, 30, 0), "ped": (4, 30, 0, 30, 0), "mag": (6, 30, 0, 30, 0),
}
FIELD_LABEL = {"iqt": "Iqtisodiyot va moliya", "biz": "Biznes va boshqaruv", "it": "Axborot texnologiyalari", "til": "Tillar (amaliy)",
               "gum": "Ijtimoiy-gumanitar", "ped": "Pedagogika va psixologiya", "mag": "Magistratura"}
IT_SUBJ = {"Dasturlash asoslari", "Ma'lumotlar bazasi", "Tarmoqlar", "Operatsion tizimlar", "Tarmoq xavfsizligi", "Kriptografiya asoslari"}
LANG_SUBJ = {"Ingliz tili", "Ikkinchi xorijiy til", "Amaliy grammatika", "Akademik yozuv", "Tarjima amaliyoti", "Nutq o'stirish", "Ona tili"}
NORM_OVERRIDE = {"Leksikologiya": "gum", "Tarjima nazariyasi": "gum", "Fonetika": "gum"}   # nazariy til fanlari — ma'ruza + seminar

def field_of(subject: str, dept_id: int | None, magistr_only: bool = False) -> str:
    if subject in NORM_OVERRIDE: return NORM_OVERRIDE[subject]
    if subject in IT_SUBJ: return "it"
    if subject in LANG_SUBJ: return "til"
    if magistr_only: return "mag"
    from .seed_syllabus import CATALOG
    if subject in CATALOG:
        return CATALOG[subject][0]
    return {5: "ped", 6: "gum", 7: "gum"}.get(dept_id or 0, "iqt")

def norm_for(subject: str, field: str | None = None, dept_id: int | None = None) -> dict:
    f = field or field_of(subject, dept_id)
    cr, l, p, s, b = NORMS.get(f, NORMS["iqt"])
    total = cr * H_PER_CREDIT
    return {"field": f, "credits": cr, "lecture": l, "practice": p, "seminar": s, "lab": b, "self": total - (l + p + s + b), "total": total}

def _item_norm(it: dict) -> dict:
    n = {"credits": it["credits"], "lecture": it["n_lecture"], "practice": it["n_practice"], "seminar": it["n_seminar"], "lab": it["n_lab"], "self": it["n_self"]}
    n["total"] = n["credits"] * H_PER_CREDIT
    return n

# =============================================================================================
# Fan × kafedra juftliklari (o'qituvchi-guruh bog'lanishlaridan)
# =============================================================================================
RANK = {"Professor": 5, "Dotsent": 4, "Kafedra mudiri": 4, "Katta o'qituvchi": 3, "Assistent": 1}

def subject_pairs(con, dept_ids=None) -> list[dict]:
    w = "" if dept_ids is None else f" AND t.department_id IN ({','.join(str(int(x)) for x in dept_ids) or '0'})"
    rows = db.rows(con, f"""SELECT tg.subject, t.department_id, d.name department, d.faculty_id, COUNT(DISTINCT tg.group_id) ng,
                               COUNT(DISTINCT t.id) nt, MIN(g.level='magistr') mag
                            FROM teacher_groups tg JOIN teachers t ON t.id=tg.teacher_id JOIN departments d ON d.id=t.department_id
                            JOIN groups_ g ON g.id=tg.group_id WHERE 1=1{w} GROUP BY tg.subject, t.department_id ORDER BY t.department_id, tg.subject""")
    lead = {}
    for r in db.rows(con, f"""SELECT tg.subject, t.department_id, t.id, t.position, COUNT(DISTINCT tg.group_id) n FROM teacher_groups tg
                              JOIN teachers t ON t.id=tg.teacher_id WHERE COALESCE(t.position,'')!='Kafedra mudiri'{w} GROUP BY tg.subject, t.department_id, t.id"""):
        k = (r["subject"], r["department_id"]); sc = (RANK.get(r["position"], 2), r["n"], -r["id"])
        if k not in lead or sc > lead[k][0]: lead[k] = (sc, r["id"])
    for r in rows:
        r["field"] = field_of(r["subject"], r["department_id"], bool(r.pop("mag")))
        r["lead_teacher"] = (lead.get((r["subject"], r["department_id"])) or (None, None))[1]
    return rows

# =============================================================================================
# Ruxsatlar
# =============================================================================================
def _role(c: Ctx) -> str:
    k = c.role.key
    if k not in ROLES_IN: raise AccessDenied("⛔ O'quv dasturlari: bu bo'lim Akademik bo'lim, kafedralar, o'qituvchilar va o'quv ishlari rahbariyati uchun.")
    if k == "oqituvchi" and not c.user.get("teacher_id"): raise AccessDenied("⛔ O'qituvchi akkaunti o'qituvchilar ro'yxatiga bog'lanmagan.")
    if k == "kafedra" and not c.user.get("department_id"): raise AccessDenied("⛔ Kafedra akkaunti kafedraga bog'lanmagan.")
    return k

def _dept_scope(c: Ctx) -> list[int] | None:
    k = _role(c)
    if k == "kafedra": return [int(c.user["department_id"])]
    return None

def _item_where(c: Ctx, a="i") -> str:
    k = _role(c)
    if k == "kafedra": return f"{a}.department_id={int(c.user['department_id'])}"
    if k == "oqituvchi": return f"{a}.teacher_id={int(c.user['teacher_id'])}"
    return "1=1"

def _can_see(c: Ctx, it: dict) -> bool:
    k = _role(c)
    if k == "kafedra": return it["department_id"] == c.user["department_id"]
    if k == "oqituvchi": return it["teacher_id"] == c.user["teacher_id"]
    return True

def _audit(c: Ctx, action: str, ok: bool = True, detail: str = ""):
    rbac.audit(_con, c, f"o'quv dasturlari: {action}", "syllabus", ok, detail)

def _deny(c: Ctx, action: str, msg: str, detail: str = ""):
    _audit(c, action, False, detail)
    raise AccessDenied(msg)

def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")

def actions(c: Ctx, it: dict) -> list[str]:
    k, st, out = c.role.key, it["status"], []
    mine_dept = k == "kafedra" and it["department_id"] == c.user.get("department_id")
    mine_t = k == "oqituvchi" and it["teacher_id"] and it["teacher_id"] == c.user.get("teacher_id")
    if mine_dept and st in OPEN_WORK: out.append("assign")
    if (mine_t or mine_dept) and st in ("jarayonda", "qaytarilgan") and it["teacher_id"]: out += ["edit", "submit"]
    if k == "akademik" and st == "tekshiruvda": out.append("review")
    if st == "kelishuvda" and ((it["stage"] == "kafedra" and mine_dept) or (it["stage"] == "akademik" and k == "akademik")
                               or (it["stage"] == "prorektor" and k == "prorektor_oquv")): out.append("endorse")
    if k == "akademik" and st != "tasdiqlangan": out += ["due", "remind"]
    return out

# =============================================================================================
# Ichki amallar (API va seed uchun umumiy)
# =============================================================================================
def _log(con, ref_type, ref_id, user, action, frm=None, to=None, comment="", version=None, ts=None):
    """user: {"id", "full_name", "role"} yoki o'qituvchi (akkauntsiz) uchun {"id": None, "full_name": ..., "title": "O'qituvchi"}."""
    title = user.get("title") or (rbac.user_title(user) if user.get("role") in rbac.ROLES else "")
    con.execute("INSERT INTO syl_log(ref_type,ref_id,ts,user_id,user_name,role,action,from_status,to_status,comment,version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ref_type, ref_id, ts or _now(), user.get("id"), _short(user.get("full_name")) or user.get("full_name"), title, action, frm, to, (comment or "")[:2000], version))

def _teacher_user(con, tid):
    u = db.one(con, "SELECT id, full_name, role FROM users WHERE teacher_id=? AND role='oqituvchi'", (tid,)) if tid else None
    if u: return u
    t = db.one(con, "SELECT full_name FROM teachers WHERE id=?", (tid,)) if tid else None
    return {"id": None, "full_name": t["full_name"] if t else "O'qituvchi", "title": "O'qituvchi"}

def _empty_content(it=None) -> dict:
    return {"topics": [], "literature": [], "assessment": {"joriy": 20, "oraliq": 30, "yakuniy": 50}, "goals": ""}

def create_item(con, pair: dict, due: str, actor: dict, note: str = "", ts=None) -> int:
    n = norm_for(pair["subject"], pair.get("field"), pair.get("department_id"))
    t = (ts.isoformat(timespec="seconds") if isinstance(ts, dt.datetime) else ts) or _now()
    cur = con.execute("""INSERT INTO syl_items(subject,department_id,semester,field,status,due,credits,n_lecture,n_practice,n_seminar,n_lab,n_self,
                         draft,version,note,requested_by,requested_at,updated_at) VALUES(?,?,?,?,'soralgan',?,?,?,?,?,?,?,?,0,?,?,?,?)""",
                      (pair["subject"], pair["department_id"], SEMESTER, n["field"], due, n["credits"], n["lecture"], n["practice"], n["seminar"],
                       n["lab"], n["self"], json.dumps(_empty_content(), ensure_ascii=False), note, actor["id"], t, t))
    _log(con, "syl", cur.lastrowid, actor, "so'raldi", None, "soralgan", note, None, t)
    return cur.lastrowid

def _set(con, iid, **kw):
    kw["updated_at"] = kw.get("updated_at") or _now()
    con.execute(f"UPDATE syl_items SET {', '.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), iid))

def _assign(con, it, tid, actor, ts=None, due=None):
    to = "jarayonda" if it["status"] == "soralgan" else it["status"]
    _set(con, it["id"], teacher_id=tid, status=to, assigned_at=ts or _now(), updated_at=ts, **({"due": due} if due else {}))
    t = db.one(con, "SELECT full_name FROM teachers WHERE id=?", (tid,))
    _log(con, "syl", it["id"], actor, "o'qituvchi biriktirildi", it["status"], to, f"{t['full_name'] if t else tid}" + (f" · muddat {due}" if due else ""), None, ts)

def _submit(con, it, content, actor, ts=None, file_name=None, file_path=None, source="form", comment=""):
    v = (it["version"] or 0) + 1
    t = ts or _now()
    chk = check(con, it, content)
    con.execute("INSERT INTO syl_versions(item_id,version,content,file_name,file_path,source,created_at,author,check_json) VALUES(?,?,?,?,?,?,?,?,?)",
                (it["id"], v, json.dumps(content, ensure_ascii=False), file_name, file_path, source, t, _short(actor.get("full_name")) or actor.get("full_name"),
                 json.dumps(chk, ensure_ascii=False)))
    _set(con, it["id"], status="tekshiruvda", stage=None, version=v, submitted_at=t, updated_at=t, draft=json.dumps(content, ensure_ascii=False))
    _log(con, "syl", it["id"], actor, f"{v}-versiya topshirildi", it["status"], "tekshiruvda", comment, v, t)
    return v, chk

NEXT_STAGE = {"kafedra": "akademik", "akademik": "prorektor", "prorektor": None}

def _review(con, it, actor, action, comment="", ts=None):
    """action: qaytarish (o'qituvchiga), yuborish (tekshiruv → kafedra kelishuvi), maqullash (kelishuv bosqichi → keyingi / tasdiq)."""
    t = ts or _now()
    st, stage = it["status"], it["stage"]
    if action == "qaytarish":
        _set(con, it["id"], status="qaytarilgan", stage=None, updated_at=t)
        _log(con, "syl", it["id"], actor, "qaytarildi" + (f" ({STAGES[stage].lower()} bosqichida)" if stage else ""), st, "qaytarilgan", comment, it["version"], t)
        return "qaytarilgan"
    if action == "yuborish":
        _set(con, it["id"], status="kelishuvda", stage="kafedra", updated_at=t)
        _log(con, "syl", it["id"], actor, "tekshiruvdan o'tdi, kelishuvga yuborildi", st, "kelishuvda", comment, it["version"], t)
        return "kelishuvda"
    nxt = NEXT_STAGE.get(stage)
    if nxt:
        _set(con, it["id"], stage=nxt, updated_at=t)
        _log(con, "syl", it["id"], actor, f"ma'qullandi ({STAGES[stage].lower()})", st, "kelishuvda", comment, it["version"], t)
        return "kelishuvda"
    _set(con, it["id"], status="tasdiqlangan", stage=None, approved_at=t, updated_at=t)
    _log(con, "syl", it["id"], actor, "tasdiqlandi", st, "tasdiqlangan", comment, it["version"], t)
    return "tasdiqlangan"

# --- seed yordamchilari (ruxsat tekshiruvisiz, vaqt belgisi bilan) ---
def _item(con, iid): return db.one(con, "SELECT * FROM syl_items WHERE id=?", (iid,))
def seed_assign(con, iid, tid, head, ts): _assign(con, _item(con, iid), tid, head, ts)
def seed_draft(con, iid, content): _set(con, iid, draft=json.dumps(content, ensure_ascii=False))
def seed_submit(con, iid, content, tid, head, ts): _submit(con, _item(con, iid), content, _teacher_user(con, tid), ts)
def seed_review(con, iid, user, action, comment, ts): _review(con, _item(con, iid), user, action, comment, ts)

# =============================================================================================
# Tekshiruv: mavzular mosligi, tayanch OTM qamrovi, soatlar
# =============================================================================================
_APOS = str.maketrans({c: "'" for c in "ʻʼ‘’`´"})
STOP = set("""va bilan uchun hamda ham yoki the and for of in to a an on its as by with from into ning ga da dan ni bu shu
kirish fan fanning fani fanga predmeti maqsadi vazifalari vazifasi asoslari asosiy asoslar tushuncha tushunchasi tushunchalar turlari turi
xususiyatlari umumiy zamonaviy rivojlanish rivojlanishi masalalari mohiyati tamoyillari usullari metodlari yakuniy takrorlash nazorat oraliq
mavzu mavzusi amaliy nazariy tizimi jarayoni o'rni ahamiyati ularning uning va'zifalari davri davr""".split())

def _words(s: str) -> list[str]:
    s = (s or "").lower().translate(_APOS)
    out = []
    for w in re.findall(r"[a-zа-яёқғўҳ0-9']+", s):
        w = w.strip("'")
        if len(w) >= 3 and w not in STOP and not w.isdigit(): out.append(w)
    return out

def _stem(w: str) -> str:
    w = w.replace("'", "")
    return w[:5] if len(w) > 5 else w

def stems(s: str) -> set:
    return {_stem(w) for w in _words(s)}

def _m(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))

def _hits(ts: set, vocab: set) -> list[str]:
    return [t for t in ts if any(_m(t, v) for v in vocab)]

def topic_match(a: str, b: str) -> float:
    sa, sb = stems(a), stems(b)
    if not sa or not sb: return 0.0
    hit = sum(1 for x in sb if any(_m(x, y) for y in sa))
    return hit / min(len(sa), len(sb)) if min(len(sa), len(sb)) else 0.0

def _matches(a: str, b: str) -> bool:
    sa, sb = stems(a), stems(b)
    n = min(len(sa), len(sb))
    if n == 0: return False
    return topic_match(a, b) >= (1.0 if n == 1 else 0.67)

def refs_for(con, subject: str) -> list[dict]:
    return [{"university": r["university"], "topics": json.loads(r["topics"] or "[]"), "description": r["description"], "sample": bool(r["sample"])}
            for r in db.rows(con, "SELECT * FROM syl_ref WHERE subject=? ORDER BY id", (subject,))]

def _num(v) -> float:
    try: return max(0.0, float(v or 0))
    except (TypeError, ValueError): return 0.0

def check(con, it: dict, content: dict, ai: dict | None = None) -> dict:
    topics = [t for t in (content.get("topics") or []) if str(t.get("title") or "").strip()]
    refs = refs_for(con, it["subject"])
    desc = refs[0]["description"] if refs else ""
    # (a) mavzular mosligi
    vocab = stems(it["subject"]) | stems(desc)
    for r in refs:
        for t in r["topics"]: vocab |= stems(t)
    strong = bool(refs)
    rel_items = []
    for i, t in enumerate(topics):
        ts = stems(t["title"])
        h = _hits(ts, vocab)
        okk = (not ts) or bool(h) or not strong
        rel_items.append({"i": i, "title": t["title"], "ok": okk, "hits": sorted(h)[:4]})
    method = "heuristic"
    if ai and ai.get("items"):
        method = "ai"
        by = {x.get("i"): x for x in ai["items"] if isinstance(x, dict)}
        for r in rel_items:
            a = by.get(r["i"])
            if a is not None:
                r["ok"] = bool(a.get("relevant", r["ok"])); r["reason"] = str(a.get("reason") or "")[:200]
    flagged = [r["title"] for r in rel_items if not r["ok"]]
    rel = {"score": round(100 * sum(r["ok"] for r in rel_items) / len(rel_items)) if rel_items else 0, "method": method, "strong": strong,
           "items": rel_items, "flagged": flagged, "description": desc}
    # (b) tayanch OTM qamrovi
    titles = [t["title"] for t in topics]
    ref = {"available": bool(refs), "sample": any(r["sample"] for r in refs), "unis": [], "coverage": None, "missing": [], "extra": [], "matched": []}
    if refs:
        union, seen = [], set()
        for r in refs:
            cov = [x for x in r["topics"] if any(_matches(x, y) for y in titles)]
            ref["unis"].append({"name": r["university"], "total": len(r["topics"]), "covered": len(cov),
                                "coverage": round(100 * len(cov) / len(r["topics"])) if r["topics"] else 0})
            for x in r["topics"]:
                k = " ".join(sorted(stems(x)))
                if k not in seen: seen.add(k); union.append(x)
        cov = [x for x in union if any(_matches(x, y) for y in titles)]
        ref["coverage"] = round(100 * len(cov) / len(union)) if union else 0
        ref["total"], ref["covered"] = len(union), len(cov)
        ref["missing"] = [x for x in union if x not in cov]
        ref["extra"] = [y for y in titles if not any(_matches(x, y) for x in union)]
    # (c) soatlar
    n = _item_norm(it)
    plan = {k: round(sum(_num(t.get(k)) for t in topics), 1) for k, _ in HOUR_KEYS}
    rows = [{"key": k, "label": lab, "norm": n[k], "plan": plan[k], "diff": round(plan[k] - n[k], 1), "ok": abs(plan[k] - n[k]) <= TOL} for k, lab in HOUR_KEYS]
    aud_n = n["lecture"] + n["practice"] + n["seminar"] + n["lab"]; aud_p = plan["lecture"] + plan["practice"] + plan["seminar"] + plan["lab"]
    tot_p = aud_p + plan["self"]
    hours = {"credits": n["credits"], "rows": rows, "aud_norm": aud_n, "aud_plan": round(aud_p, 1), "total_norm": n["total"], "total_plan": round(tot_p, 1),
             "weeks": len({int(_num(t.get("week"))) for t in topics if _num(t.get("week"))}), "topics": len(topics),
             "ok": all(r["ok"] for r in rows) and abs(tot_p - n["total"]) <= TOL}
    a = content.get("assessment") or {}
    s = sum(_num(a.get(k)) for k in ("joriy", "oraliq", "yakuniy"))
    asm = {"sum": round(s), "ok": abs(s - 100) < 0.01}
    lit = [x for x in (content.get("literature") or []) if str(x).strip()]
    notes = []
    if not topics: notes.append("Mavzular kiritilmagan")
    if flagged: notes.append(f"{len(flagged)} ta mavzu fanga mos emas")
    if ref["available"] and ref["coverage"] is not None and ref["coverage"] < 80: notes.append(f"Tayanch OTM qamrovi {ref['coverage']}%")
    if not hours["ok"]: notes.append("Soatlar me'yorga mos emas")
    if not asm["ok"]: notes.append(f"Baholash yig'indisi {asm['sum']}%")
    if len(lit) < 3: notes.append("Adabiyotlar 3 tadan kam")
    level = "bad" if (flagged or not hours["ok"] or not asm["ok"] or not topics) else "warn" if notes else "ok"
    return {"relevance": rel, "reference": ref, "hours": hours, "assessment": asm, "literature": len(lit),
            "summary": {"level": level, "notes": notes}, "at": _now()}

def latest_check(con, it: dict) -> dict:
    v = db.one(con, "SELECT check_json FROM syl_versions WHERE item_id=? ORDER BY version DESC LIMIT 1", (it["id"],))
    return json.loads(v["check_json"]) if v and v["check_json"] else {}

async def ai_relevance(subject: str, desc: str, topics: list[str]) -> dict | None:
    """Mahalliy AI (Ollama) bo'lsa — har bir mavzu fanga mosligini baholaydi; bo'lmasa None (evristik natija qoladi)."""
    from . import ai
    if not topics or not await ai.llm_available(): return None
    lst = "\n".join(f"{i}. {t}" for i, t in enumerate(topics))
    msgs = [{"role": "system", "content": "Sen oliy ta'lim fan dasturlarini tekshiruvchi ekspertsan. Faqat JSON qaytar."},
            {"role": "user", "content": f"Fan: {subject}\nFan tavsifi: {desc or '-'}\nMavzular:\n{lst}\n\n"
                                        "Har bir mavzu shu fan mazmuniga tegishlimi? JSON: {\"items\":[{\"i\":0,\"relevant\":true,\"reason\":\"qisqa izoh\"}]}"}]
    schema = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "i": {"type": "integer"}, "relevant": {"type": "boolean"}, "reason": {"type": "string"}}, "required": ["i", "relevant"]}}}, "required": ["items"]}
    try:
        out = json.loads(await ai.llm_once(msgs, fmt=schema, max_tokens=900))
        return out if isinstance(out, dict) and isinstance(out.get("items"), list) else None
    except Exception as e:
        print("syllabus ai:", repr(e)); return None

# =============================================================================================
# DOCX / PDF dan mavzularni ajratib olish
# =============================================================================================
_TOPIC_RE = [re.compile(r"^\s*(\d{1,2})\s*[-–]\s*mavzu\s*[:.\-–]?\s*(.{4,220})$", re.I),
             re.compile(r"^\s*(?:mavzu|topic|lecture)\s*(\d{1,2})\s*[:.\-–]\s*(.{4,220})$", re.I),
             re.compile(r"^\s*(\d{1,2})\s*[.)]\s+(.{4,220})$")]
_HEAD_COLS = [("title", ("mavzu", "topic", "nomi", "theme")), ("lecture", ("ma'ruza", "maruza", "lecture")), ("practice", ("amaliy", "practic")),
              ("seminar", ("seminar",)), ("lab", ("laborator", "lab")), ("self", ("mustaqil", "self", "independent")), ("week", ("hafta", "week", "№", "t/r"))]

def _hours_tail(s: str):
    m = re.search(r"((?:\s+\d{1,3}){2,5})\s*$", s)
    if not m: return s, []
    return s[: m.start()].strip(" .:-–"), [int(x) for x in m.group(1).split()]

def _parse_lines(lines: list[str]) -> dict:
    topics, lit, mode = [], [], "topics"
    for raw in lines:
        s = " ".join((raw or "").split())
        if not s: continue
        low = s.lower().translate(_APOS)
        if len(s) < 60 and re.search(r"adabiyot|literature|manbalar|references", low): mode = "lit"; continue
        if len(s) < 60 and re.search(r"mavzular|tematik|kalendar|topics|reja", low) and not re.match(r"^\s*\d", s): mode = "topics"; continue
        if mode == "lit":
            m = re.match(r"^\s*\d{1,2}\s*[.)]\s*(.{6,300})$", s)
            if m: lit.append(m.group(1).strip())
            continue
        for rx in _TOPIC_RE:
            m = rx.match(s)
            if m:
                title, hrs = _hours_tail(m.group(2).strip())
                if len(title) < 4: break
                t = {"week": int(m.group(1)), "title": title[:200], "lecture": 0, "practice": 0, "seminar": 0, "lab": 0, "self": 0}
                keys = ["lecture", "practice", "seminar", "lab", "self"] if len(hrs) >= 5 else ["lecture", "practice", "self"] if len(hrs) == 3 else ["lecture", "practice"]
                for k, v in zip(keys, hrs): t[k] = v
                topics.append(t); break
    return {"topics": topics[:40], "literature": lit[:30]}

def extract_topics(data: bytes, ext: str) -> dict:
    ext = ext.lower()
    if ext == "docx":
        from docx import Document
        d = Document(io.BytesIO(data))
        topics = []
        for tb in d.tables:
            cols = None
            for row in tb.rows:
                cells, seen = [], set()
                for c in row.cells:
                    if id(c._tc) in seen: continue
                    seen.add(id(c._tc)); cells.append(" ".join(c.text.split()))
                low = [x.lower().translate(_APOS) for x in cells]
                if cols is None and any(any(k in x for k in ("mavzu", "topic", "nomi")) for x in low):
                    cols = {}
                    for i, h in enumerate(low):
                        for key, kws in _HEAD_COLS:
                            if key not in cols and any(k in h for k in kws): cols[key] = i; break
                    continue
                if cols and "title" in cols and cols["title"] < len(cells):
                    title = cells[cols["title"]]
                    if len(title) < 4 or re.fullmatch(r"(jami|итого|total).*", title.lower()): continue
                    t = {"week": len(topics) + 1, "title": title[:200]}
                    for key in ("lecture", "practice", "seminar", "lab", "self", "week"):
                        i = cols.get(key)
                        if i is not None and i < len(cells):
                            m = re.search(r"\d+(?:[.,]\d+)?", cells[i]); v = float(m.group().replace(",", ".")) if m else 0
                            t[key] = int(v) if v == int(v) else v
                    for key in ("lecture", "practice", "seminar", "lab", "self"): t.setdefault(key, 0)
                    topics.append(t)
        res = _parse_lines([p.text for p in d.paragraphs])
        if topics: res["topics"] = topics[:40]
        return res
    if ext == "pdf":
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        lines = []
        for p in r.pages[:30]:
            lines += (p.extract_text() or "").splitlines()
        return _parse_lines(lines)
    raise ValueError("Faqat DOCX yoki PDF")

# =============================================================================================
# Ko'rinishlar
# =============================================================================================
def _dept_names(con) -> dict: return {d["id"]: d["name"] for d in db.rows(con, "SELECT id, name FROM departments")}
def _teacher_names(con) -> dict: return {t["id"]: t["full_name"] for t in db.rows(con, "SELECT id, full_name FROM teachers")}

def _due_info(it, td):
    d = None
    try: d = dt.date.fromisoformat(str(it.get("due") or "")[:10])
    except ValueError: pass
    over = bool(d and d < td and it["status"] in OPEN_WORK)
    return (d - td).days if d else None, over

def _row(it, dn, tn, td, chk=None, last=None):
    days, over = _due_info(it, td)
    out = {"id": it["id"], "subject": it["subject"], "department_id": it["department_id"], "department": dn.get(it["department_id"], ""),
           "teacher_id": it["teacher_id"], "teacher": tn.get(it["teacher_id"]) if it["teacher_id"] else None, "status": it["status"],
           "status_label": STATUS[it["status"]], "stage": it["stage"], "stage_label": STAGES.get(it["stage"]), "due": it["due"], "days": days,
           "overdue": over, "version": it["version"], "credits": it["credits"], "field": it["field"], "updated_at": it["updated_at"],
           "submitted_at": it["submitted_at"], "approved_at": it["approved_at"]}
    if chk:
        out["check"] = {"level": chk.get("summary", {}).get("level"), "coverage": (chk.get("reference") or {}).get("coverage"),
                        "relevance": (chk.get("relevance") or {}).get("score"), "hours_ok": (chk.get("hours") or {}).get("ok")}
    if last: out["last"] = last
    return out

def board(c: Ctx, dept: int = 0, status: str = "", q: str = "") -> dict:
    _role(c)
    td = today(); dn, tn = _dept_names(_con), _teacher_names(_con)
    w = [_item_where(c)]
    if dept: w.append(f"i.department_id={int(dept)}")
    items = db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {' AND '.join(w)} ORDER BY i.department_id, i.subject")
    ids = [i["id"] for i in items]
    chks, lasts = {}, {}
    if ids:
        ph = ",".join("?" * len(ids))
        for v in db.rows(_con, f"""SELECT v.item_id, v.check_json FROM syl_versions v JOIN (SELECT item_id, MAX(version) mv FROM syl_versions
                                   WHERE item_id IN ({ph}) GROUP BY item_id) x ON x.item_id=v.item_id AND x.mv=v.version""", ids):
            try: chks[v["item_id"]] = json.loads(v["check_json"] or "{}")
            except ValueError: pass
        for l in db.rows(_con, f"""SELECT l.ref_id, l.ts, l.action, l.user_name, l.comment FROM syl_log l JOIN (SELECT ref_id, MAX(id) mid FROM syl_log
                                   WHERE ref_type='syl' AND ref_id IN ({ph}) GROUP BY ref_id) x ON x.mid=l.id""", ids):
            lasts[l["ref_id"]] = {"ts": l["ts"], "action": l["action"], "who": l["user_name"], "comment": (l["comment"] or "")[:160]}
    rows = [_row(i, dn, tn, td, chks.get(i["id"]), lasts.get(i["id"])) for i in items]
    counts = {k: sum(r["status"] == k for r in rows) for k in STATUS}
    counts["overdue"] = sum(r["overdue"] for r in rows); counts["total"] = len(rows)
    by = {}
    for r in rows:
        b = by.setdefault(r["department_id"], {"id": r["department_id"], "name": r["department"], **{k: 0 for k in STATUS}, "overdue": 0, "total": 0})
        b[r["status"]] += 1; b["total"] += 1; b["overdue"] += r["overdue"]
    qq = (q or "").lower().translate(_APOS).strip()
    if status == "overdue": rows = [r for r in rows if r["overdue"]]
    elif status in STATUS: rows = [r for r in rows if r["status"] == status]
    elif status == "action": rows = [r for r in rows if actions(c, _item(_con, r["id"]))]
    if qq: rows = [r for r in rows if all(w in f"{r['subject']} {r['department']} {r['teacher'] or ''}".lower().translate(_APOS) for w in qq.split())]
    unreq = 0
    if c.role.key == "akademik":
        have = {(i["subject"], i["department_id"]) for i in db.rows(_con, "SELECT subject, department_id FROM syl_items WHERE semester=?", (SEMESTER,))}
        unreq = sum(1 for p in subject_pairs(_con) if (p["subject"], p["department_id"]) not in have)
    return {"items": rows, "counts": counts, "by_dept": sorted(by.values(), key=lambda b: b["id"]), "unrequested": unreq, "semester": SEMESTER}

def detail(c: Ctx, iid: int) -> dict:
    _role(c)
    it = _item(_con, iid)
    if not it or not _can_see(c, it): raise HTTPException(404, "Sillabus topilmadi")
    td = today(); dn, tn = _dept_names(_con), _teacher_names(_con)
    acts = actions(c, it)
    versions = db.rows(_con, "SELECT version, created_at, author, file_name, source, check_json FROM syl_versions WHERE item_id=? ORDER BY version DESC", (iid,))
    for v in versions:
        ch = json.loads(v.pop("check_json") or "{}")
        v["level"] = (ch.get("summary") or {}).get("level"); v["coverage"] = (ch.get("reference") or {}).get("coverage")
        v["has_file"] = bool(v["file_name"])
    draft = json.loads(it["draft"] or "{}") or _empty_content()
    if "edit" in acts:
        content, src = draft, "draft"
    elif it["version"]:
        v = db.one(_con, "SELECT content FROM syl_versions WHERE item_id=? AND version=?", (iid, it["version"]))
        content, src = json.loads(v["content"]), "version"
    else:
        content, src = draft, "draft"
    chk = check(_con, it, content) if (src == "draft" and content.get("topics")) else (latest_check(_con, it) if src == "version" else None)
    hist = db.rows(_con, "SELECT ts, user_name, role, action, from_status, to_status, comment, version FROM syl_log WHERE ref_type='syl' AND ref_id=? ORDER BY id DESC", (iid,))
    out = {"item": _row(it, dn, tn, td), "note": it["note"], "norm": _item_norm(it), "field_label": FIELD_LABEL.get(it["field"], it["field"]),
           "content": content, "content_src": src, "check": chk, "versions": versions, "history": hist, "actions": acts,
           "refs": [{"university": r["university"], "topics": r["topics"], "sample": r["sample"]} for r in refs_for(_con, it["subject"])],
           "draft_file": draft.get("file", {}).get("name") if isinstance(draft.get("file"), dict) else None, "semester": it["semester"]}
    if "assign" in acts:
        ts = db.rows(_con, """SELECT t.id, t.full_name, t.position, t.load_hours, (SELECT COUNT(DISTINCT group_id) FROM teacher_groups g WHERE g.teacher_id=t.id AND g.subject=?) ng
                              FROM teachers t WHERE t.department_id=? ORDER BY ng DESC, t.full_name""", (it["subject"], it["department_id"]))
        out["teachers"] = ts
    rbac.audit(_con, c, "o'quv dasturlari: sillabus ko'rildi", "syllabus", True, f"#{iid} {it['subject']}")
    return out

# =============================================================================================
# Mening vazifalarim va bildirishnomalar uchun manba
# =============================================================================================
def _plus(ts, days):
    try: return (dt.date.fromisoformat(str(ts)[:10]) + dt.timedelta(days=days)).isoformat()
    except ValueError: return None

def mywork_items(c: Ctx, mk) -> list[dict]:
    """mywork._item(source, kind, iid, title, sub, due, link, who, status, prio, count, icon) bilan qatorlar."""
    k = c.role.key
    if k not in ("akademik", "prorektor_oquv", "kafedra", "oqituvchi"): return []
    if (k == "oqituvchi" and not c.user.get("teacher_id")) or (k == "kafedra" and not c.user.get("department_id")): return []
    td = today(); dn = _dept_names(_con); out = []
    W = _item_where(c)
    def many(rows, kind, one_title, agg_title, due_fn, who, status, icon, prio=None, cap=5, link_extra=None):
        if not rows: return
        if len(rows) <= cap:
            for r in rows:
                out.append(mk("sillabus", kind, f"sy{kind[:2]}{r['id']}", one_title(r), f"{r['subject']} · {dn.get(r['department_id'], '')} · {STATUS[r['status']]}"
                              + (f" · {STAGES[r['stage']].lower()} bosqichi" if r.get("stage") else ""), due_fn(r),
                              {"view": "syllabus", "item": r["id"]}, who, status, prio, None, icon))
        else:
            first = min((due_fn(r) for r in rows if due_fn(r)), default=None)
            names = sorted({r["subject"] for r in rows})
            out.append(mk("sillabus", kind, f"sy{kind[:2]}all", agg_title(len(rows)), ", ".join(names[:3]) + (f" va yana {len(names) - 3}" if len(names) > 3 else ""),
                          first, {"view": "syllabus", **(link_extra or {})}, who, status, prio, len(rows), icon))
    if k == "oqituvchi":
        rows = db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status IN ('jarayonda','qaytarilgan') ORDER BY i.due")
        for r in rows:
            ret = r["status"] == "qaytarilgan"
            out.append(mk("sillabus", "sillabus", f"syt{r['id']}", ("Qaytarilgan sillabusni tuzating: " if ret else "Sillabus tayyorlang: ") + r["subject"],
                          f"{dn.get(r['department_id'], '')} · {r['credits']} kredit · {SEMESTER}", r["due"], {"view": "syllabus", "item": r["id"]},
                          "menga", STATUS[r["status"]], "high" if ret else None, None, "book"))
    if k == "kafedra":
        many(db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status='soralgan' ORDER BY i.due"), "biriktirish",
             lambda r: f"O'qituvchi biriktiring: {r['subject']}", lambda n: f"Sillabus so'rovlari: {n} ta fanga o'qituvchi biriktiring",
             lambda r: r["due"], "bolimga", "so'ralgan", "book", link_extra={"status": "soralgan"})
        many(db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status='kelishuvda' AND i.stage='kafedra' ORDER BY i.updated_at"), "kelishuv",
             lambda r: f"Sillabusni ma'qullang: {r['subject']}", lambda n: f"Kafedra kelishuvi: {n} ta sillabus ma'qullashni kutmoqda",
             lambda r: _plus(r["updated_at"], REVIEW_DAYS), "bolimga", "kelishuvda", "pen", "mid", link_extra={"status": "kelishuvda"})
        over = db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status IN ('jarayonda','qaytarilgan') AND i.due < ?", (td.isoformat(),))
        if over:
            out.append(mk("sillabus", "nazorat", "syover", f"Kafedrada {len(over)} ta sillabus muddati o'tgan", ", ".join(sorted({r['subject'] for r in over})[:3]),
                          min(r["due"] for r in over), {"view": "syllabus", "status": "overdue"}, "nazorat", "muddati o'tgan", "high", len(over), "alert"))
        for u in db.rows(_con, """SELECT u.*, t.title, t.due, t.kind FROM syl_task_units u JOIN syl_tasks t ON t.id=u.task_id
                                  WHERE u.department_id=? AND u.status IN ('yangi','qayta') AND t.status='ochiq' ORDER BY t.due""", (c.user["department_id"],)):
            out.append(mk("sillabus", "sorov", f"syk{u['id']}", ("Qayta ishlang: " if u["status"] == "qayta" else "Akademik bo'lim so'rovi: ") + u["title"],
                          f"{TASK_KINDS.get(u['kind'], '')} · {UNIT_ST[u['status']]}" + (f" · «{(u['comment'] or '')[:60]}»" if u["status"] == "qayta" and u["comment"] else ""),
                          u["due"], {"view": "syllabus", "tab": "tasks", "task": u["task_id"]}, "bolimga", UNIT_ST[u["status"]],
                          "high" if u["status"] == "qayta" else None, None, "inbox"))
    if k == "akademik":
        many(db.rows(_con, "SELECT i.* FROM syl_items i WHERE i.status='tekshiruvda' ORDER BY i.submitted_at"), "tekshiruv",
             lambda r: f"Sillabusni tekshiring: {r['subject']}", lambda n: f"Tekshiruv kutmoqda: {n} ta sillabus",
             lambda r: _plus(r["submitted_at"], REVIEW_DAYS), "menga", "tekshiruvda", "checkc", link_extra={"status": "tekshiruvda"})
        many(db.rows(_con, "SELECT i.* FROM syl_items i WHERE i.status='kelishuvda' AND i.stage='akademik' ORDER BY i.updated_at"), "kelishuv",
             lambda r: f"Sillabusni ma'qullang: {r['subject']}", lambda n: f"Akademik bo'lim kelishuvi: {n} ta sillabus",
             lambda r: _plus(r["updated_at"], REVIEW_DAYS), "menga", "kelishuvda", "pen", "mid", link_extra={"status": "kelishuvda"})
        over = db.rows(_con, "SELECT i.* FROM syl_items i WHERE i.status IN ('soralgan','jarayonda','qaytarilgan') AND i.due < ?", (td.isoformat(),))
        if over:
            out.append(mk("sillabus", "nazorat", "syover", f"Ijro nazorati: {len(over)} ta sillabus muddati o'tgan",
                          ", ".join(sorted({dn.get(r['department_id'], '') for r in over})[:3]) + " kafedralari", min(r["due"] for r in over),
                          {"view": "syllabus", "status": "overdue"}, "nazorat", "muddati o'tgan", "high", len(over), "alert"))
        units = db.rows(_con, """SELECT u.*, t.title, t.due FROM syl_task_units u JOIN syl_tasks t ON t.id=u.task_id
                                 WHERE u.status='topshirildi' AND t.status='ochiq' ORDER BY u.submitted_at""")
        by = {}
        for u in units: by.setdefault(u["task_id"], []).append(u)
        for tid, us in by.items():
            out.append(mk("sillabus", "javob", f"syj{tid}", f"Kafedra javobini ko'rib chiqing: {us[0]['title']}",
                          ", ".join(dn.get(u["department_id"], "") for u in us[:3]) + (f" va yana {len(us) - 3}" if len(us) > 3 else ""),
                          _plus(min(u["submitted_at"] for u in us), REVIEW_DAYS), {"view": "syllabus", "tab": "tasks", "task": tid}, "menga",
                          f"{len(us)} ta javob", None, len(us) if len(us) > 1 else None, "inbox"))
    if k == "prorektor_oquv":
        many(db.rows(_con, "SELECT i.* FROM syl_items i WHERE i.status='kelishuvda' AND i.stage='prorektor' ORDER BY i.updated_at"), "tasdiq",
             lambda r: f"Sillabusni tasdiqlang: {r['subject']}", lambda n: f"O'quv dasturlari: {n} ta sillabus tasdiqingizni kutmoqda",
             lambda r: _plus(r["updated_at"], REVIEW_DAYS), "menga", "kelishuvda", "pen", "mid", link_extra={"status": "kelishuvda"})
    return out

def notif_items(c: Ctx) -> list[dict]:
    """extras.notifications formatidagi yozuvlar: yangi biriktirish, qaytarish, eslatma, kelgan sillabuslar, muddati o'tganlar."""
    k = c.role.key
    if k not in ("akademik", "prorektor_oquv", "kafedra", "oqituvchi"): return []
    if (k == "oqituvchi" and not c.user.get("teacher_id")) or (k == "kafedra" and not c.user.get("department_id")): return []
    td = today(); out = []; W = _item_where(c)
    link = lambda iid: {"view": "syllabus", "item": iid}
    def day_ts(d): return dt.datetime.combine(d, dt.time(0, 0)).isoformat(timespec="seconds")
    if k in ("oqituvchi", "kafedra"):
        evs = db.rows(_con, f"""SELECT l.*, i.subject, i.status FROM syl_log l JOIN syl_items i ON i.id=l.ref_id
                                WHERE l.ref_type='syl' AND {W} AND (l.action LIKE 'qaytarildi%' OR l.action='eslatma'{" OR l.action='o''qituvchi biriktirildi'" if k == 'oqituvchi' else ''})
                                ORDER BY l.id DESC LIMIT 8""")
        for e in evs:
            if e["action"].startswith("qaytarildi") and e["status"] != "qaytarilgan": continue
            if e["action"] != "eslatma" and not e["action"].startswith("qaytarildi") and e["status"] not in OPEN_WORK: continue
            ret, rem = e["action"].startswith("qaytarildi"), e["action"] == "eslatma"
            out.append({"id": f"syn{e['id']}", "kind": "sillabus", "icon": "alert" if ret else "clock" if rem else "book", "level": "bad" if ret else "warn" if rem else "info",
                        "title": (f"Sillabus qaytarildi: {e['subject']}" if ret else f"Eslatma: {e['subject']} sillabusi" if rem else f"Sizga sillabus biriktirildi: {e['subject']}"),
                        "sub": " · ".join(x for x in [e["user_name"], (e["comment"] or "").split("\n")[0][:90]] if x), "ts": e["ts"], "link": link(e["ref_id"])})
    if k == "kafedra":
        rq = db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status='soralgan'")
        if rq:
            out.append({"id": "synreq", "kind": "sillabus", "icon": "book", "level": "info", "title": f"Akademik bo'lim {len(rq)} ta fan bo'yicha sillabus so'radi",
                        "sub": "O'qituvchi biriktiring · " + ", ".join(sorted({r['subject'] for r in rq})[:3]), "ts": max(r["requested_at"] for r in rq),
                        "link": {"view": "syllabus", "status": "soralgan"}})
        st = db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status='kelishuvda' AND i.stage='kafedra'")
        if st:
            out.append({"id": "synkaf", "kind": "sillabus", "icon": "pen", "level": "warn", "title": f"{len(st)} ta sillabus kafedra kelishuvini kutmoqda",
                        "sub": ", ".join(sorted({r['subject'] for r in st})[:3]), "ts": max(r["updated_at"] for r in st), "link": {"view": "syllabus", "status": "kelishuvda"}})
        for u in db.rows(_con, """SELECT u.*, t.title, t.created_at FROM syl_task_units u JOIN syl_tasks t ON t.id=u.task_id
                                  WHERE u.department_id=? AND u.status IN ('yangi','qayta') AND t.status='ochiq'""", (c.user["department_id"],)):
            q = u["status"] == "qayta"
            out.append({"id": f"synt{u['id']}", "kind": "sillabus", "icon": "alert" if q else "inbox", "level": "bad" if q else "info",
                        "title": ("Qayta ishlashga qaytarildi: " if q else "Akademik bo'lim so'rovi: ") + u["title"],
                        "sub": (u["comment"] or "")[:90] if q else "Natijani shu so'rovga javob sifatida yuboring", "ts": u["reviewed_at"] if q and u["reviewed_at"] else u["created_at"],
                        "link": {"view": "syllabus", "tab": "tasks", "task": u["task_id"]}})
    if k == "akademik":
        sub = db.rows(_con, "SELECT * FROM syl_items WHERE status='tekshiruvda'")
        if sub:
            out.append({"id": "synrev", "kind": "sillabus", "icon": "book", "level": "info", "title": f"{len(sub)} ta sillabus tekshiruvga keldi",
                        "sub": ", ".join(sorted({r['subject'] for r in sub})[:3]), "ts": max(r["submitted_at"] for r in sub), "link": {"view": "syllabus", "status": "tekshiruvda"}})
        tu = db.rows(_con, "SELECT u.*, t.title FROM syl_task_units u JOIN syl_tasks t ON t.id=u.task_id WHERE u.status='topshirildi' AND t.status='ochiq'")
        if tu:
            out.append({"id": "synans", "kind": "sillabus", "icon": "inbox", "level": "info", "title": f"Kafedralardan {len(tu)} ta javob keldi",
                        "sub": ", ".join(sorted({u['title'] for u in tu})[:2]), "ts": max(u["submitted_at"] for u in tu), "link": {"view": "syllabus", "tab": "tasks"}})
    if k == "prorektor_oquv":
        st = db.rows(_con, "SELECT * FROM syl_items WHERE status='kelishuvda' AND stage='prorektor'")
        if st:
            out.append({"id": "synpro", "kind": "sillabus", "icon": "pen", "level": "warn", "title": f"{len(st)} ta sillabus tasdiqingizni kutmoqda",
                        "sub": ", ".join(sorted({r['subject'] for r in st})[:3]), "ts": max(r["updated_at"] for r in st), "link": {"view": "syllabus", "status": "kelishuvda"}})
    if k in ("akademik", "kafedra", "oqituvchi"):
        over = db.rows(_con, f"SELECT i.* FROM syl_items i WHERE {W} AND i.status IN ('soralgan','jarayonda','qaytarilgan') AND i.due < ?", (td.isoformat(),))
        if over:
            last = max(dt.date.fromisoformat(r["due"]) for r in over)
            out.append({"id": "synover", "kind": "sillabus", "icon": "alert", "level": "bad", "title": f"{len(over)} ta sillabus muddati o'tgan",
                        "sub": ", ".join(sorted({r['subject'] for r in over})[:3]), "ts": day_ts(last + dt.timedelta(days=1)), "link": {"view": "syllabus", "status": "overdue"}})
    return out

# =============================================================================================
# O'quv yuklama kalkulyatori
# =============================================================================================
DEF_SETTINGS = {"potok_max": 3, "k_kunduzgi": 1.0, "k_sirtqi": 0.5, "k_masofaviy": 0.4, "subgroups": 2}
FORM_K = {"kunduzgi": "k_kunduzgi", "sirtqi": "k_sirtqi", "masofaviy": "k_masofaviy"}

def _settings(s: dict | None) -> dict:
    out = dict(DEF_SETTINGS)
    for k, v in (s or {}).items():
        if k in out:
            try:
                f = float(v)
                out[k] = int(min(10, max(1, f))) if k in ("potok_max", "subgroups") else round(min(2.0, max(0.0, f)), 2)
            except (TypeError, ValueError): pass
    return out

def _load_scope(c: Ctx, did: int):
    k = c.role.key
    if k not in ("akademik", "prorektor_oquv", "rektor", "kafedra"):
        raise AccessDenied("⛔ Yuklama kalkulyatori Akademik bo'lim, kafedralar va o'quv ishlari rahbariyati uchun.")
    if k == "kafedra" and int(did) != int(c.user.get("department_id") or 0):
        raise AccessDenied("⛔ Yuklama kalkulyatori: faqat o'z kafedrangiz.")
    if not db.one(_con, "SELECT 1 x FROM departments WHERE id=?", (did,)): raise HTTPException(404, "Kafedra topilmadi")

def compute_load(con, did: int, settings: dict | None = None, overrides: dict | None = None) -> dict:
    from .documents import LOAD_NORM
    S = _settings(settings); ov = overrides or {}
    rows = db.rows(con, """SELECT DISTINCT tg.teacher_id, tg.group_id, tg.subject, g.name gname, g.course, g.direction, COALESCE(g.form,'kunduzgi') form, g.level
                           FROM teacher_groups tg JOIN teachers t ON t.id=tg.teacher_id JOIN groups_ g ON g.id=tg.group_id
                           WHERE t.department_id=? ORDER BY tg.subject, g.form, g.course, g.direction, g.name""", (did,))
    teachers = {t["id"]: {**t, "lecture": 0.0, "practice": 0.0, "seminar": 0.0, "lab": 0.0, "subjects": set(), "groups": set()}
                for t in db.rows(con, "SELECT id, full_name, position, degree, load_hours FROM teachers WHERE department_id=? ORDER BY id", (did,))}
    by_subj = {}
    for r in rows: by_subj.setdefault(r["subject"], []).append(r)
    out_rows = []
    kf = lambda form: S.get(FORM_K.get(form, "k_kunduzgi"), 1.0)
    for subj, rs in by_subj.items():
        groups = {}
        for r in rs: groups.setdefault(r["group_id"], {"id": r["group_id"], "name": r["gname"], "course": r["course"], "direction": r["direction"], "form": r["form"],
                                                       "level": r["level"], "teachers": []})["teachers"].append(r["teacher_id"])
        gl = sorted(groups.values(), key=lambda g: (g["form"], g["course"], g["direction"] or "", g["name"]))
        mag = all(g["level"] == "magistr" for g in gl)
        n = norm_for(subj, field_of(subj, did, mag), did)
        o = ov.get(subj) or {}
        hrs = {}
        for key in ("lecture", "practice", "seminar", "lab"):
            try: hrs[key] = max(0.0, min(400.0, float(o[key]))) if key in o and o[key] not in (None, "") else float(n[key])
            except (TypeError, ValueError): hrs[key] = float(n[key])
        try: subg = int(min(6, max(1, int(o.get("subgroups"))))) if o.get("subgroups") not in (None, "") else S["subgroups"]
        except (TypeError, ValueError): subg = S["subgroups"]
        # potoklar: (shakl, kurs, yo'nalish) bo'yicha, har potokda ko'pi bilan potok_max guruh; yoki qo'lda berilgan son
        try: want = int(o.get("streams")) if o.get("streams") not in (None, "") else 0
        except (TypeError, ValueError): want = 0
        if want > 0:
            want = min(want, len(gl)); size = math.ceil(len(gl) / want)
            streams = [gl[i:i + size] for i in range(0, len(gl), size)]
        else:
            streams, cur, key0 = [], [], None
            for g in gl:
                kk = (g["form"], g["course"], g["direction"])
                if cur and (kk != key0 or len(cur) >= S["potok_max"]): streams.append(cur); cur = []
                cur.append(g); key0 = kk
            if cur: streams.append(cur)
        tot = {"lecture": 0.0, "practice": 0.0, "seminar": 0.0, "lab": 0.0}
        for st in streams:
            h = hrs["lecture"] * max(kf(g["form"]) for g in st)
            if h <= 0: continue
            cands = {tid for g in st for tid in g["teachers"] if tid in teachers}
            if not cands: continue
            lec = max(cands, key=lambda tid: (RANK.get(teachers[tid]["position"], 2), -teachers[tid]["lecture"], sum(tid in g["teachers"] for g in st), -tid))
            teachers[lec]["lecture"] += h; teachers[lec]["subjects"].add(subj); tot["lecture"] += h
        for g in gl:
            k = kf(g["form"]); ts = [t for t in dict.fromkeys(g["teachers"]) if t in teachers]
            if not ts: continue
            for key in ("practice", "seminar"):
                h = hrs[key] * k
                if h <= 0: continue
                for tid in ts: teachers[tid][key] += h / len(ts)
                tot[key] += h
            h = hrs["lab"] * k * subg
            if h > 0:
                for tid in ts: teachers[tid]["lab"] += h / len(ts)
                tot["lab"] += h
            for tid in ts: teachers[tid]["subjects"].add(subj); teachers[tid]["groups"].add(g["id"])
        forms = {}
        for g in gl: forms[g["form"]] = forms.get(g["form"], 0) + 1
        out_rows.append({"subject": subj, "field": n["field"], "credits": n["credits"], "groups": len(gl), "streams": len(streams), "subgroups": subg,
                         "forms": forms, "hours": {k: round(v, 1) for k, v in hrs.items()}, "norm": {k: n[k] for k in ("lecture", "practice", "seminar", "lab")},
                         "overridden": sorted(k for k in o if o.get(k) not in (None, "")),
                         "totals": {k: round(v, 1) for k, v in tot.items()}, "total": round(sum(tot.values()), 1),
                         "teachers": len({t for g in gl for t in g["teachers"]}),
                         "stream_list": [[g["name"] for g in st] for st in streams]})
    trows = []
    for t in teachers.values():
        total = t["lecture"] + t["practice"] + t["seminar"] + t["lab"]
        st = round(total / LOAD_NORM, 2)
        trows.append({"id": t["id"], "name": t["full_name"], "position": t["position"], "degree": t["degree"],
                      "lecture": round(t["lecture"], 1), "practice": round(t["practice"], 1), "seminar": round(t["seminar"], 1), "lab": round(t["lab"], 1),
                      "total": round(total, 1), "stavka": st, "current": t["load_hours"], "diff": round(total - (t["load_hours"] or 0), 1),
                      "subjects": sorted(t["subjects"]), "groups": len(t["groups"]),
                      "flag": "ortiqcha" if st > 1.5 else "kam" if st < 0.75 else "me'yorda"})
    trows.sort(key=lambda r: -r["total"])
    total = round(sum(r["total"] for r in out_rows), 1)
    cur = sum(r["current"] or 0 for r in trows)
    d = db.one(con, "SELECT d.name, d.head FROM departments d WHERE d.id=?", (did,))
    return {"department_id": did, "department": d["name"] if d else "", "head": d["head"] if d else "", "settings": S, "load_norm": LOAD_NORM,
            "rows": sorted(out_rows, key=lambda r: -r["total"]), "teachers": trows,
            "summary": {"total": total, "stavka": round(total / LOAD_NORM, 2), "staff": len(trows), "current": cur, "current_stavka": round(cur / LOAD_NORM, 2),
                        "diff": round(total - cur, 1), "by_type": {k: round(sum(r["totals"][k] for r in out_rows), 1) for k in ("lecture", "practice", "seminar", "lab")},
                        "over": sum(r["flag"] == "ortiqcha" for r in trows), "under": sum(r["flag"] == "kam" for r in trows),
                        "groups": len({r["group_id"] for r in rows}), "subjects": len(out_rows)}}

def _saved_plan(did) -> dict:
    r = db.one(_con, "SELECT * FROM syl_load_plans WHERE department_id=?", (did,))
    if not r: return {"settings": {}, "rows": {}, "saved": None}
    p = json.loads(r["params"] or "{}")
    u = db.one(_con, "SELECT full_name FROM users WHERE id=?", (r["updated_by"],)) if r["updated_by"] else None
    return {"settings": p.get("settings") or {}, "rows": p.get("rows") or {}, "saved": {"at": r["updated_at"], "by": _short(u["full_name"]) if u else ""}}

def docx_calc_section(I, calc: dict):
    """documents.g_load uchun: kalkulyator hisob-kitobi (o'quv reja me'yori bo'yicha) — mavjud jadvaldan keyin qo'shiladi."""
    from . import brand as B
    s = calc["summary"]
    B.para(I.doc, "O'quv reja me'yorlari bo'yicha hisob-kitob (yuklama kalkulyatori)", indent=False, size=12, bold=True)
    st = calc["settings"]
    B.para(I.doc, f"Potokdagi guruhlar soni — ko'pi bilan {st['potok_max']}; laboratoriya uchun kichik guruhlar — {st['subgroups']}; "
           f"ta'lim shakli koeffitsiyentlari: kunduzgi {st['k_kunduzgi']}, sirtqi {st['k_sirtqi']}, masofaviy {st['k_masofaviy']}. "
           "Ma'ruza — potokka, amaliy va seminar — guruhga, laboratoriya — kichik guruhga hisoblanadi.", indent=False, size=10)
    f = lambda v: f"{v:g}"
    B.table(I.doc, ["Fan", "Guruh", "Potok", "Ma'ruza", "Amaliy", "Seminar", "Lab.", "Jami"],
            [(r["subject"], r["groups"], r["streams"], f(r["totals"]["lecture"]), f(r["totals"]["practice"]), f(r["totals"]["seminar"]), f(r["totals"]["lab"]), f(r["total"]))
             for r in calc["rows"]], widths=[5, 1.3, 1.3, 1.6, 1.6, 1.6, 1.4, 1.6], size=8)
    B.table(I.doc, ["№", "F.I.Sh.", "Ma'ruza", "Amaliy", "Seminar", "Lab.", "Hisob", "Stavka", "Joriy", "Farq"],
            [(i, r["name"], f(r["lecture"]), f(r["practice"]), f(r["seminar"]), f(r["lab"]), f(r["total"]), r["stavka"], r["current"], f(r["diff"]))
             for i, r in enumerate(calc["teachers"], 1)], widths=[0.7, 4.6, 1.4, 1.4, 1.4, 1.2, 1.4, 1.3, 1.3, 1.3], size=8)
    B.para(I.doc, f"Hisoblangan jami yuklama: {f(s['total'])} soat ({s['stavka']} stavka). Joriy taqsimot: {s['current']} soat ({s['current_stavka']} stavka). "
           f"Farq: {f(s['diff'])} soat.", indent=False, size=10.5)

def xlsx_bytes(calc: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "Fanlar"
    hdr = Font(bold=True, color="FFFFFF"); fill = PatternFill("solid", fgColor="00575B")
    def head(ws, cols):
        ws.append(cols)
        for c in ws[ws.max_row]: c.font = hdr; c.fill = fill; c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.append([f"O'quv yuklama hisob-kitobi — «{calc['department']}» kafedrasi"]); ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Me'yor: 1 stavka = {calc['load_norm']} soat · potok ≤ {calc['settings']['potok_max']} guruh · kichik guruhlar {calc['settings']['subgroups']} · "
               f"koeffitsiyentlar: kunduzgi {calc['settings']['k_kunduzgi']}, sirtqi {calc['settings']['k_sirtqi']}, masofaviy {calc['settings']['k_masofaviy']}"])
    ws.append([])
    head(ws, ["Fan", "Kredit", "Guruhlar", "Potoklar", "Kichik guruh", "Ma'ruza (1 potok)", "Amaliy (1 guruh)", "Seminar (1 guruh)", "Lab. (1 kichik guruh)",
              "Ma'ruza jami", "Amaliy jami", "Seminar jami", "Lab. jami", "Jami soat"])
    for r in calc["rows"]:
        ws.append([r["subject"], r["credits"], r["groups"], r["streams"], r["subgroups"], r["hours"]["lecture"], r["hours"]["practice"], r["hours"]["seminar"],
                   r["hours"]["lab"], r["totals"]["lecture"], r["totals"]["practice"], r["totals"]["seminar"], r["totals"]["lab"], r["total"]])
    s = calc["summary"]
    ws.append(["Jami", None, s["groups"], None, None, None, None, None, None, s["by_type"]["lecture"], s["by_type"]["practice"], s["by_type"]["seminar"], s["by_type"]["lab"], s["total"]])
    for c in ws[ws.max_row]: c.font = Font(bold=True)
    ws.column_dimensions["A"].width = 34
    for col in "BCDEFGHIJKLMN": ws.column_dimensions[col].width = 12
    ws2 = wb.create_sheet("O'qituvchilar")
    head(ws2, ["№", "F.I.Sh.", "Lavozim", "Ma'ruza", "Amaliy", "Seminar", "Laboratoriya", "Hisoblangan jami", "Stavka", "Joriy yuklama (load_hours)", "Farq", "Holat", "Fanlar"])
    for i, r in enumerate(calc["teachers"], 1):
        ws2.append([i, r["name"], r["position"], r["lecture"], r["practice"], r["seminar"], r["lab"], r["total"], r["stavka"], r["current"], r["diff"], r["flag"], ", ".join(r["subjects"])])
    ws2.append([None, "Jami", None, None, None, None, None, s["total"], s["stavka"], s["current"], s["diff"]])
    for c in ws2[ws2.max_row]: c.font = Font(bold=True)
    ws2.column_dimensions["B"].width = 34; ws2.column_dimensions["C"].width = 18; ws2.column_dimensions["M"].width = 60
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

# =============================================================================================
# Kafedralarga so'rovlar
# =============================================================================================
def create_task(con, actor, kind, title, body, due, deps, ts=None) -> int:
    t = ts or _now()
    cur = con.execute("INSERT INTO syl_tasks(kind,title,body,due,created_by,created_name,created_at,status) VALUES(?,?,?,?,?,?,?,'ochiq')",
                      (kind, title, body, due, actor["id"], _short(actor["full_name"]), t))
    for d in deps:
        u = con.execute("INSERT INTO syl_task_units(task_id,department_id,status,round) VALUES(?,?,'yangi',0)", (cur.lastrowid, d))
        _log(con, "task", u.lastrowid, actor, "so'rov yuborildi", None, "yangi", "", None, t)
    con.commit()
    return cur.lastrowid

def _task_submit(con, u, actor, text, ts=None, file_name=None, file_path=None):
    t = ts or _now()
    kw = {"file_name": file_name, "file_path": file_path} if file_name else {}
    sets = ", ".join(["status='topshirildi'", "response=?", "submitted_at=?", "round=round+1"] + [f"{k}=?" for k in kw])
    con.execute(f"UPDATE syl_task_units SET {sets} WHERE id=?", (text, t, *kw.values(), u["id"]))
    _log(con, "task", u["id"], actor, "javob yuborildi", u["status"], "topshirildi", text, (u["round"] or 0) + 1, t)
    con.commit()

def _task_review(con, u, actor, action, comment, ts=None):
    t = ts or _now(); to = "qabul" if action == "qabul" else "qayta"
    con.execute("UPDATE syl_task_units SET status=?, reviewed_at=?, comment=? WHERE id=?", (to, t, comment, u["id"]))
    _log(con, "task", u["id"], actor, "qabul qilindi" if to == "qabul" else "qayta ishlashga qaytarildi", u["status"], to, comment, u["round"], t)
    con.commit()

def seed_task_submit(con, uid, actor, text, ts): _task_submit(con, db.one(con, "SELECT * FROM syl_task_units WHERE id=?", (uid,)), actor, text, ts)
def seed_task_review(con, uid, actor, action, comment, ts): _task_review(con, db.one(con, "SELECT * FROM syl_task_units WHERE id=?", (uid,)), actor, action, comment, ts)

def _task_visible(c: Ctx):
    k = _role(c)
    if k == "oqituvchi": raise AccessDenied("⛔ Kafedra so'rovlari — Akademik bo'lim va kafedra mudirlari uchun.")
    return f"u.department_id={int(c.user['department_id'])}" if k == "kafedra" else "1=1"

def tasks_list(c: Ctx) -> dict:
    w = _task_visible(c); td = today().isoformat(); dn = _dept_names(_con)
    ts = db.rows(_con, f"""SELECT t.* FROM syl_tasks t WHERE EXISTS(SELECT 1 FROM syl_task_units u WHERE u.task_id=t.id AND {w}) ORDER BY t.id DESC""")
    out = []
    for t in ts:
        us = db.rows(_con, f"SELECT u.id, u.department_id, u.status, u.submitted_at, u.reviewed_at, u.round, u.file_name FROM syl_task_units u WHERE u.task_id=? AND {w} ORDER BY u.department_id", (t["id"],))
        for u in us:
            u["department"] = dn.get(u["department_id"], ""); u["status_label"] = UNIT_ST[u["status"]]
            u["overdue"] = bool(t["due"] and t["due"] < td and u["status"] in ("yangi", "qayta"))
        out.append({**t, "kind_label": TASK_KINDS.get(t["kind"], t["kind"]), "units": us, "counts": {k: sum(u["status"] == k for u in us) for k in UNIT_ST},
                    "overdue": sum(u["overdue"] for u in us)})
    return {"tasks": out, "kinds": TASK_KINDS, "can_create": c.role.key == "akademik",
            "departments": [{"id": d["id"], "name": d["name"]} for d in db.rows(_con, "SELECT id, name FROM departments ORDER BY id")] if c.role.key == "akademik" else []}

def task_detail(c: Ctx, tid: int) -> dict:
    w = _task_visible(c); dn = _dept_names(_con)
    t = db.one(_con, "SELECT * FROM syl_tasks WHERE id=?", (tid,))
    us = db.rows(_con, f"SELECT u.* FROM syl_task_units u WHERE u.task_id=? AND {w} ORDER BY u.department_id", (tid,)) if t else []
    if not t or not us: raise HTTPException(404, "So'rov topilmadi")
    td = today().isoformat()
    for u in us:
        u["department"] = dn.get(u["department_id"], ""); u["status_label"] = UNIT_ST[u["status"]]
        u["overdue"] = bool(t["due"] and t["due"] < td and u["status"] in ("yangi", "qayta"))
        u["history"] = db.rows(_con, "SELECT ts, user_name, role, action, comment, version round FROM syl_log WHERE ref_type='task' AND ref_id=? ORDER BY id DESC", (u["id"],))
        mine = c.role.key == "kafedra" and u["department_id"] == c.user.get("department_id")
        u["can_submit"] = mine and u["status"] in ("yangi", "qayta") and t["status"] == "ochiq"
        u["can_review"] = c.role.key == "akademik" and u["status"] == "topshirildi"
        u.pop("file_path", None)
    return {**t, "kind_label": TASK_KINDS.get(t["kind"], t["kind"]), "units": us}

# =============================================================================================
# API
# =============================================================================================
def C(request) -> Ctx: return _ctx(request)

class RequestIn(BaseModel):
    pairs: list[dict]
    due: str
    note: str = ""

class AssignIn(BaseModel):
    teacher_id: int
    due: str = ""

class DraftIn(BaseModel):
    content: dict

class SubmitIn(BaseModel):
    content: dict | None = None
    comment: str = ""

class ReviewIn(BaseModel):
    action: str
    comment: str = ""

class DueIn(BaseModel):
    due: str

class NoteIn(BaseModel):
    comment: str = ""

class CheckIn(BaseModel):
    content: dict | None = None
    ai: bool = False

class LoadIn(BaseModel):
    department_id: int
    settings: dict = {}
    rows: dict = {}
    fmt: str = ""

class TaskIn(BaseModel):
    kind: str
    title: str
    body: str = ""
    due: str
    departments: list[int]

class TaskAnswerIn(BaseModel):
    text: str = ""

class TaskReviewIn(BaseModel):
    action: str
    comment: str = ""

def _date(v: str, field="Muddat") -> str:
    try: return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError: raise HTTPException(400, f"{field} noto'g'ri (YYYY-MM-DD)")

def _clean_content(content: dict) -> dict:
    tp = []
    for i, t in enumerate((content or {}).get("topics") or []):
        if not isinstance(t, dict): continue
        title = " ".join(str(t.get("title") or "").split())[:200]
        if not title: continue
        row = {"week": int(_num(t.get("week")) or (i + 1)), "title": title}
        for k, _ in HOUR_KEYS: row[k] = round(min(_num(t.get(k)), 200), 1)
        tp.append(row)
    a = (content or {}).get("assessment") or {}
    out = {"topics": tp[:60], "literature": [" ".join(str(x).split())[:300] for x in ((content or {}).get("literature") or []) if str(x).strip()][:40],
           "assessment": {k: round(min(_num(a.get(k)), 100)) for k in ("joriy", "oraliq", "yakuniy")},
           "goals": str((content or {}).get("goals") or "")[:3000]}
    if isinstance((content or {}).get("file"), dict): out["file"] = content["file"]
    return out

def _get_item(c: Ctx, iid: int) -> dict:
    it = _item(_con, iid)
    if not it or not _can_see(c, it): raise HTTPException(404, "Sillabus topilmadi")
    return it

def _need(c, it, act, label):
    if act not in actions(c, it):
        _deny(c, label, f"⛔ {label}: bu amal sizning lavozimingiz yoki sillabusning joriy holati ({STATUS[it['status']].lower()}) uchun mumkin emas.", f"#{it['id']} {it['subject']}")

@router.get("/api/syllabus/meta")
def api_meta(request: Request):
    c = C(request); k = _role(c)
    deps = db.rows(_con, "SELECT id, name, head FROM departments ORDER BY id")
    if k == "kafedra": deps = [d for d in deps if d["id"] == c.user["department_id"]]
    if k == "oqituvchi": deps = []
    return {"role": k, "semester": SEMESTER, "today": today().isoformat(), "statuses": STATUS, "stages": STAGES, "task_kinds": TASK_KINDS,
            "departments": deps, "can": {"request": k == "akademik", "load": k in ("akademik", "prorektor_oquv", "rektor", "kafedra"),
                                          "load_save": k == "akademik", "load_docx": k in ("akademik", "prorektor_oquv", "kafedra"),
                                          "tasks": k != "oqituvchi", "tasks_create": k == "akademik"},
            "scope": "Butun institut" if k in ROLE_ALL else (deps[0]["name"] + " kafedrasi" if k == "kafedra" and deps else "Menga biriktirilgan fanlar"),
            "load_norm": __import__("app.documents", fromlist=["LOAD_NORM"]).LOAD_NORM, "h_per_credit": H_PER_CREDIT}

@router.get("/api/syllabus/board")
def api_board(request: Request, dept: int = 0, status: str = "", q: str = ""):
    c = C(request)
    try: return board(c, dept, status, q)
    except AccessDenied: _audit(c, "holat taxtasi", False); raise

@router.get("/api/syllabus/catalog")
def api_catalog(request: Request, dept: int = 0):
    c = C(request)
    if _role(c) != "akademik": _deny(c, "so'raladigan fanlar ro'yxati", "⛔ Sillabusni faqat Akademik bo'lim so'raydi.")
    have = {(i["subject"], i["department_id"]) for i in db.rows(_con, "SELECT subject, department_id FROM syl_items WHERE semester=?", (SEMESTER,))}
    ps = [p for p in subject_pairs(_con, [dept] if dept else None) if (p["subject"], p["department_id"]) not in have]
    for p in ps:
        n = norm_for(p["subject"], p["field"], p["department_id"]); p["credits"] = n["credits"]; p["field_label"] = FIELD_LABEL.get(p["field"], p["field"])
    return {"pairs": ps, "default_due": (today() + dt.timedelta(days=14)).isoformat()}

@router.post("/api/syllabus/request")
def api_request(body: RequestIn, request: Request):
    c = C(request)
    if _role(c) != "akademik": _deny(c, "sillabus so'rash", "⛔ Sillabusni faqat Akademik bo'lim so'raydi.")
    due = _date(body.due)
    if due < today().isoformat(): raise HTTPException(400, "Muddat bugundan oldin bo'lishi mumkin emas")
    valid = {(p["subject"], p["department_id"]): p for p in subject_pairs(_con)}
    made = []
    for x in body.pairs[:300]:
        key = (str(x.get("subject") or ""), int(x.get("department_id") or 0))
        p = valid.get(key)
        if not p or db.one(_con, "SELECT 1 x FROM syl_items WHERE subject=? AND department_id=? AND semester=?", (*key, SEMESTER)): continue
        made.append(create_item(_con, p, due, c.user, body.note.strip()[:500]))
    _con.commit()
    if not made: raise HTTPException(400, "Yangi so'raladigan fan topilmadi (allaqachon so'ralgan yoki noto'g'ri)")
    _audit(c, "sillabus so'raldi", True, f"{len(made)} ta fan · muddat {due}")
    return {"ok": True, "created": made}

@router.get("/api/syllabus/items/{iid}")
def api_item(iid: int, request: Request):
    return detail(C(request), iid)

@router.post("/api/syllabus/items/{iid}/assign")
def api_assign(iid: int, body: AssignIn, request: Request):
    c = C(request); it = _get_item(c, iid); _need(c, it, "assign", "O'qituvchi biriktirish")
    t = db.one(_con, "SELECT id, full_name FROM teachers WHERE id=? AND department_id=?", (body.teacher_id, it["department_id"]))
    if not t: raise HTTPException(400, "O'qituvchi shu kafedrada emas")
    due = _date(body.due) if body.due else None
    _assign(_con, it, t["id"], c.user, due=due); _con.commit()
    _audit(c, "o'qituvchi biriktirildi", True, f"#{iid} {it['subject']} → {t['full_name']}")
    return {"ok": True}

@router.put("/api/syllabus/items/{iid}/draft")
def api_draft(iid: int, body: DraftIn, request: Request):
    c = C(request); it = _get_item(c, iid); _need(c, it, "edit", "Sillabusni tahrirlash")
    old = json.loads(it["draft"] or "{}")
    content = _clean_content(body.content)
    if isinstance(old.get("file"), dict) and "file" not in content: content["file"] = old["file"]
    _set(_con, iid, draft=json.dumps(content, ensure_ascii=False)); _con.commit()
    _audit(c, "qoralama saqlandi", True, f"#{iid} {it['subject']} · {len(content['topics'])} mavzu")
    it = _item(_con, iid)
    return {"ok": True, "content": content, "check": check(_con, it, content) if content["topics"] else None}

@router.post("/api/syllabus/items/{iid}/upload")
async def api_upload(iid: int, request: Request, name: str):
    from . import filecheck as FC
    c = C(request); it = _get_item(c, iid); _need(c, it, "edit", "Sillabus faylini yuklash")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("docx", "pdf"): raise HTTPException(415, "Faqat DOCX yoki PDF fayl yuklanadi")
    buf = bytearray()
    async for ch in request.stream():
        buf += ch
        if len(buf) > MAX_BYTES: raise HTTPException(413, "Fayl hajmi 10 MB dan oshmasligi kerak")
    data = bytes(buf)
    try: FC.inspect(name, ext, data)
    except FC.FileRejected as e:
        _audit(c, "fayl rad etildi", False, f"#{iid} {name[:80]} — {e}"); raise HTTPException(415, str(e))
    try: ex = extract_topics(data, ext)
    except Exception as e:
        _audit(c, "fayl o'qilmadi", False, f"#{iid} {name[:80]} — {e!r}"[:300]); raise HTTPException(422, "Fayl mazmunini o'qib bo'lmadi")
    FILES.mkdir(parents=True, exist_ok=True)
    fn = f"{iid}_{secrets.token_hex(6)}.{ext}"
    (FILES / fn).write_bytes(data)
    draft = json.loads(it["draft"] or "{}") or _empty_content()
    if ex["topics"]: draft["topics"] = ex["topics"]
    if ex["literature"]: draft["literature"] = ex["literature"]
    draft["file"] = {"name": Path(name).name[:120], "path": fn, "size": len(data)}
    draft = _clean_content(draft)
    _set(_con, iid, draft=json.dumps(draft, ensure_ascii=False)); _con.commit()
    _audit(c, "sillabus fayli yuklandi", True, f"#{iid} {name[:80]} · {len(ex['topics'])} mavzu ajratildi")
    it = _item(_con, iid)
    return {"ok": True, "found": len(ex["topics"]), "literature": len(ex["literature"]), "content": draft,
            "check": check(_con, it, draft) if draft["topics"] else None}

@router.post("/api/syllabus/items/{iid}/submit")
def api_submit(iid: int, body: SubmitIn, request: Request):
    c = C(request); it = _get_item(c, iid); _need(c, it, "submit", "Sillabusni topshirish")
    content = _clean_content(body.content) if body.content is not None else json.loads(it["draft"] or "{}")
    if body.content is not None:
        old = json.loads(it["draft"] or "{}")
        if isinstance(old.get("file"), dict) and "file" not in content: content["file"] = old["file"]
    if len(content.get("topics") or []) < 3: raise HTTPException(400, "Kamida 3 ta mavzu kiriting")
    f = content.get("file") if isinstance(content.get("file"), dict) else {}
    v, chk = _submit(_con, it, content, c.user, file_name=f.get("name"), file_path=f.get("path"), source="file" if f else "form", comment=body.comment.strip()[:1000])
    _con.commit()
    _audit(c, "sillabus topshirildi", True, f"#{iid} {it['subject']} · v{v} · {chk['summary']['level']}")
    return {"ok": True, "version": v, "check": chk}

@router.post("/api/syllabus/items/{iid}/check")
async def api_check(iid: int, body: CheckIn, request: Request):
    c = C(request); it = _get_item(c, iid)
    content = _clean_content(body.content) if body.content else (json.loads(db.one(_con, "SELECT content FROM syl_versions WHERE item_id=? AND version=?", (iid, it["version"]))["content"])
                                                                  if it["version"] else json.loads(it["draft"] or "{}"))
    ai_res, note = None, ""
    if body.ai:
        refs = refs_for(_con, it["subject"])
        ai_res = await ai_relevance(it["subject"], refs[0]["description"] if refs else "", [t["title"] for t in content.get("topics") or []])
        note = "" if ai_res else "Mahalliy AI hozir mavjud emas — kalit so'zlar bo'yicha tekshirildi."
    chk = check(_con, it, content, ai_res)
    _audit(c, "tekshiruv" + (" (AI)" if ai_res else ""), True, f"#{iid} {it['subject']} · {chk['summary']['level']}")
    return {"check": chk, "note": note}

@router.post("/api/syllabus/items/{iid}/review")
def api_review(iid: int, body: ReviewIn, request: Request):
    c = C(request); it = _get_item(c, iid)
    a = body.action
    if a not in ("qaytarish", "yuborish", "maqullash"): raise HTTPException(400, "Noma'lum amal")
    if it["status"] == "tekshiruvda": _need(c, it, "review", "Sillabusni ko'rib chiqish")
    else: _need(c, it, "endorse", "Kelishuv")
    if it["status"] == "tekshiruvda" and a == "maqullash": raise HTTPException(400, "Tekshiruvdan keyin avval kelishuvga yuboriladi")
    if it["status"] == "kelishuvda" and a == "yuborish": raise HTTPException(400, "Sillabus allaqachon kelishuvda")
    if a == "qaytarish" and len(body.comment.strip()) < 5: raise HTTPException(400, "Qaytarish uchun izoh yozing (nima tuzatilishi kerak)")
    to = _review(_con, it, c.user, a, body.comment.strip()[:2000]); _con.commit()
    _audit(c, {"qaytarish": "sillabus qaytarildi", "yuborish": "kelishuvga yuborildi", "maqullash": "sillabus ma'qullandi" if to != "tasdiqlangan" else "sillabus tasdiqlandi"}[a],
           True, f"#{iid} {it['subject']} · v{it['version']}" + (f" · {it['stage']}" if it["stage"] else ""))
    return {"ok": True, "status": to}

@router.post("/api/syllabus/items/{iid}/due")
def api_due(iid: int, body: DueIn, request: Request):
    c = C(request); it = _get_item(c, iid); _need(c, it, "due", "Muddatni o'zgartirish")
    d = _date(body.due)
    _set(_con, iid, due=d); _log(_con, "syl", iid, c.user, "muddat o'zgartirildi", it["status"], it["status"], f"{it['due']} → {d}"); _con.commit()
    _audit(c, "muddat o'zgartirildi", True, f"#{iid} {it['subject']}: {it['due']} → {d}")
    return {"ok": True}

@router.post("/api/syllabus/items/{iid}/remind")
def api_remind(iid: int, body: NoteIn, request: Request):
    c = C(request); it = _get_item(c, iid); _need(c, it, "remind", "Eslatma yuborish")
    _set(_con, iid, reminded_at=_now()); _log(_con, "syl", iid, c.user, "eslatma", it["status"], it["status"], body.comment.strip()[:500] or f"Muddat: {it['due']}"); _con.commit()
    _audit(c, "eslatma yuborildi", True, f"#{iid} {it['subject']}")
    return {"ok": True}

@router.get("/api/syllabus/items/{iid}/versions/{v}")
def api_version(iid: int, v: int, request: Request):
    c = C(request); it = _get_item(c, iid)
    r = db.one(_con, "SELECT * FROM syl_versions WHERE item_id=? AND version=?", (iid, v))
    if not r: raise HTTPException(404, "Versiya topilmadi")
    return {"version": v, "content": json.loads(r["content"]), "check": json.loads(r["check_json"] or "{}"), "created_at": r["created_at"], "author": r["author"],
            "file_name": r["file_name"]}

@router.get("/api/syllabus/items/{iid}/file")
def api_file(iid: int, request: Request, v: int = 0):
    c = C(request); it = _get_item(c, iid)
    if v:
        r = db.one(_con, "SELECT file_name, file_path FROM syl_versions WHERE item_id=? AND version=?", (iid, v)); fname, fpath = (r or {}).get("file_name"), (r or {}).get("file_path")
    else:
        f = (json.loads(it["draft"] or "{}") or {}).get("file") or {}; fname, fpath = f.get("name"), f.get("path")
    p = (FILES / (fpath or "")).resolve()
    if not fpath or p.parent != FILES.resolve() or not p.exists(): raise HTTPException(404, "Fayl topilmadi")
    _audit(c, "sillabus fayli yuklab olindi", True, f"#{iid} {fname}")
    mt = "application/pdf" if p.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(p, filename=fname, media_type=mt, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

# --- yuklama ---
@router.get("/api/syllabus/load")
def api_load(request: Request, dept: int = 0):
    c = C(request)
    if not dept: dept = int(c.user.get("department_id") or 0) or 4
    try: _load_scope(c, dept)
    except AccessDenied: _audit(c, "yuklama kalkulyatori", False, f"kafedra {dept}"); raise
    plan = _saved_plan(dept)
    calc = compute_load(_con, dept, plan["settings"], plan["rows"])
    _audit(c, "yuklama kalkulyatori", True, f"kafedra {dept}")
    return {**calc, "overrides": plan["rows"], "saved": plan["saved"], "defaults": DEF_SETTINGS}

@router.post("/api/syllabus/load/calc")
def api_load_calc(body: LoadIn, request: Request):
    c = C(request); _load_scope(c, body.department_id)
    return compute_load(_con, body.department_id, body.settings, body.rows)

@router.post("/api/syllabus/load/save")
def api_load_save(body: LoadIn, request: Request):
    c = C(request); _load_scope(c, body.department_id)
    if c.role.key != "akademik": _deny(c, "yuklama rejasini saqlash", "⛔ Yuklama rejasini Akademik bo'lim saqlaydi.", f"kafedra {body.department_id}")
    rows = {str(k)[:120]: {kk: vv for kk, vv in (v or {}).items() if kk in ("streams", "subgroups", "lecture", "practice", "seminar", "lab") and vv not in (None, "")}
            for k, v in (body.rows or {}).items() if isinstance(v, dict)}
    rows = {k: v for k, v in rows.items() if v}
    _con.execute("INSERT OR REPLACE INTO syl_load_plans(department_id, params, updated_at, updated_by) VALUES(?,?,?,?)",
                 (body.department_id, json.dumps({"settings": _settings(body.settings), "rows": rows}, ensure_ascii=False), _now(), c.user["id"]))
    _con.commit()
    _audit(c, "yuklama rejasi saqlandi", True, f"kafedra {body.department_id} · {len(rows)} ta fan qo'lda o'zgartirilgan")
    return {"ok": True, "saved": _saved_plan(body.department_id)["saved"]}

@router.post("/api/syllabus/load/export")
def api_load_export(body: LoadIn, request: Request):
    c = C(request); _load_scope(c, body.department_id)
    calc = compute_load(_con, body.department_id, body.settings, body.rows)
    if body.fmt == "xlsx":
        _audit(c, "yuklama XLSX eksport", True, f"kafedra {body.department_id}")
        fn = f"yuklama_kafedra{body.department_id}_{today().isoformat()}.xlsx"
        return Response(xlsx_bytes(calc), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fn}"', "Cache-Control": "private, no-store"})
    if body.fmt == "docx":
        from . import documents as D, service as SV
        try: r = D.issue(_con, c, "load", {"department": body.department_id, "_calc": calc}, SV.public_base(request))
        except ValueError as e: raise HTTPException(400, str(e))
        _audit(c, "yuklama DOCX (Hujjatlar markazi)", True, f"kafedra {body.department_id} · {r['regs'][0]}")
        return {"ok": True, **r}
    raise HTTPException(400, "Format: xlsx yoki docx")

# --- kafedralarga so'rovlar ---
@router.get("/api/syllabus/tasks")
def api_tasks(request: Request):
    c = C(request)
    try: return tasks_list(c)
    except AccessDenied: _audit(c, "kafedra so'rovlari", False); raise

@router.post("/api/syllabus/tasks")
def api_task_create(body: TaskIn, request: Request):
    c = C(request)
    if _role(c) != "akademik": _deny(c, "kafedraga so'rov yuborish", "⛔ Kafedralarga so'rovni Akademik bo'lim yuboradi.")
    if body.kind not in TASK_KINDS: raise HTTPException(400, "So'rov turi noto'g'ri")
    title = " ".join(body.title.split())[:200]
    if len(title) < 5: raise HTTPException(400, "So'rov mavzusini yozing")
    due = _date(body.due)
    deps = sorted({int(d) for d in body.departments if db.one(_con, "SELECT 1 x FROM departments WHERE id=?", (int(d),))})
    if not deps: raise HTTPException(400, "Kamida bitta kafedrani tanlang")
    tid = create_task(_con, c.user, body.kind, title, body.body.strip()[:4000], due, deps)
    _audit(c, "kafedraga so'rov yuborildi", True, f"#{tid} {title[:80]} → {len(deps)} ta kafedra · muddat {due}")
    return {"ok": True, "id": tid}

@router.get("/api/syllabus/tasks/{tid}")
def api_task(tid: int, request: Request):
    return task_detail(C(request), tid)

def _unit(c, tid, uid):
    w = _task_visible(c)
    u = db.one(_con, f"SELECT u.* FROM syl_task_units u WHERE u.id=? AND u.task_id=? AND {w}", (uid, tid))
    if not u: raise HTTPException(404, "So'rov topilmadi")
    return u

@router.post("/api/syllabus/tasks/{tid}/units/{uid}/submit")
def api_task_submit(tid: int, uid: int, body: TaskAnswerIn, request: Request):
    c = C(request); u = _unit(c, tid, uid)
    if not (c.role.key == "kafedra" and u["department_id"] == c.user.get("department_id") and u["status"] in ("yangi", "qayta")):
        _deny(c, "so'rovga javob", "⛔ Javobni shu kafedra mudiri yuboradi (yangi yoki qaytarilgan so'rovga).", f"so'rov #{tid}")
    if len(body.text.strip()) < 3 and not u["file_name"]: raise HTTPException(400, "Javob matnini yozing yoki fayl ilova qiling")
    _task_submit(_con, u, c.user, body.text.strip()[:4000])
    _audit(c, "so'rovga javob yuborildi", True, f"so'rov #{tid} · raund {(u['round'] or 0) + 1}")
    return {"ok": True}

@router.post("/api/syllabus/tasks/{tid}/units/{uid}/file")
async def api_task_file(tid: int, uid: int, request: Request, name: str):
    from . import filecheck as FC
    c = C(request); u = _unit(c, tid, uid)
    if not (c.role.key == "kafedra" and u["department_id"] == c.user.get("department_id") and u["status"] in ("yangi", "qayta")):
        _deny(c, "so'rovga fayl ilova qilish", "⛔ Faylni shu kafedra mudiri ilova qiladi.", f"so'rov #{tid}")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("docx", "pdf", "xlsx"): raise HTTPException(415, "Faqat DOCX, XLSX yoki PDF")
    buf = bytearray()
    async for ch in request.stream():
        buf += ch
        if len(buf) > MAX_BYTES: raise HTTPException(413, "Fayl hajmi 10 MB dan oshmasligi kerak")
    try: FC.inspect(name, ext, bytes(buf))
    except FC.FileRejected as e:
        _audit(c, "fayl rad etildi", False, f"so'rov #{tid} {name[:80]} — {e}"); raise HTTPException(415, str(e))
    FILES.mkdir(parents=True, exist_ok=True)
    fn = f"t{uid}_{secrets.token_hex(6)}.{ext}"
    (FILES / fn).write_bytes(bytes(buf))
    _con.execute("UPDATE syl_task_units SET file_name=?, file_path=? WHERE id=?", (Path(name).name[:120], fn, uid)); _con.commit()
    _audit(c, "so'rovga fayl ilova qilindi", True, f"so'rov #{tid} · {name[:80]}")
    return {"ok": True, "file_name": Path(name).name[:120]}

@router.get("/api/syllabus/tasks/{tid}/units/{uid}/file")
def api_task_file_get(tid: int, uid: int, request: Request):
    c = C(request); u = _unit(c, tid, uid)
    p = (FILES / (u["file_path"] or "")).resolve()
    if not u["file_path"] or p.parent != FILES.resolve() or not p.exists(): raise HTTPException(404, "Fayl topilmadi")
    _audit(c, "so'rov fayli yuklab olindi", True, f"so'rov #{tid} · {u['file_name']}")
    return FileResponse(p, filename=u["file_name"], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

@router.post("/api/syllabus/tasks/{tid}/units/{uid}/review")
def api_task_review(tid: int, uid: int, body: TaskReviewIn, request: Request):
    c = C(request); u = _unit(c, tid, uid)
    if c.role.key != "akademik": _deny(c, "kafedra javobini ko'rib chiqish", "⛔ Kafedra javobini Akademik bo'lim ko'rib chiqadi.", f"so'rov #{tid}")
    if u["status"] != "topshirildi": raise HTTPException(400, "Bu javob ko'rib chiqish holatida emas")
    if body.action not in ("qabul", "qayta"): raise HTTPException(400, "Noma'lum amal")
    if body.action == "qayta" and len(body.comment.strip()) < 5: raise HTTPException(400, "Qaytarish uchun izoh yozing")
    _task_review(_con, u, c.user, body.action, body.comment.strip()[:2000])
    _audit(c, "kafedra javobi " + ("qabul qilindi" if body.action == "qabul" else "qayta ishlashga qaytarildi"), True, f"so'rov #{tid} · kafedra {u['department_id']}")
    return {"ok": True}

@router.post("/api/syllabus/tasks/{tid}/close")
def api_task_close(tid: int, request: Request):
    c = C(request)
    if c.role.key != "akademik": _deny(c, "so'rovni yopish", "⛔ So'rovni Akademik bo'lim yopadi.", f"so'rov #{tid}")
    t = db.one(_con, "SELECT * FROM syl_tasks WHERE id=?", (tid,))
    if not t: raise HTTPException(404, "So'rov topilmadi")
    _con.execute("UPDATE syl_tasks SET status=? WHERE id=?", ("yopilgan" if t["status"] == "ochiq" else "ochiq", tid)); _con.commit()
    _audit(c, "so'rov " + ("yopildi" if t["status"] == "ochiq" else "qayta ochildi"), True, f"#{tid} {t['title'][:80]}")
    return {"ok": True}
