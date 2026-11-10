"""Kadrlar bo'limi: xodimlarning shaxsiy ishi, ishga qabul, ishdan bo'shatish, mehnat shartnomalari, attestatsiya va malaka oshirish,
shtat jadvali (reja / amalda / bo'sh stavkalar).

Nima qiladi:
  * Shaxsiy ish (hr_files): lavozim, bo'lim, stavka, ma'lumoti, ilmiy darajasi va unvoni, mehnat shartnomasi (turi, raqami, muddati),
    oxirgi attestatsiya va malaka oshirish sanasi. Ta'til va safarlar — «Xodimlar ta'tili» (app/staff_absence.py) bo'limida, bu yerda faqat havola.
  * Ishga qabul: vakansiya (bo'lim rahbari taklif qiladi yoki Kadrlar ochadi) → Rektor tasdig'i → nomzodlar (ariza → suhbat → tanlandi)
    → Rektor tasdig'i → «Buyruqlar»da (app/orders.py, xodim_qabul) buyruq loyihasi → Rektor imzolagach xodim bazaga qo'shiladi
    → AT bo'limiga Portal orqali akkaunt so'rovi.
  * Ishdan bo'shatish: ariza → topshirish varaqasi (akkauntlar bloklandi, moddiy boyliklar, kutubxona, ish hujjatlari, hisob-kitob)
    → «Buyruqlar»da (xodim_boshatish) buyruq → imzolangach shaxsiy ish «bo'shatilgan» holatiga o'tadi.
  * Ogohlantirishlar: shartnoma muddati 30 / 60 kun ichida tugaydi yoki o'tib ketgan; attestatsiya va malaka oshirish (har 5 yilda) muddati o'tgan
    yoki 90 kun ichida. Shartnomani uzaytirish — tarix bilan (hr_contract_log).
  * Shtat jadvali: bo'lim × lavozim bo'yicha reja stavkalar va amaldagi (faol shaxsiy ishlar stavkalari yig'indisi) — bo'sh stavkalar.
RBAC (rbac.HR — faqat Kadrlar bo'limida; TELEGRAM_BLOCKED — Telegram kanalida hech narsa berilmaydi):
  kadrlar — to'liq; rektor — jamlangan ko'rsatkichlar (shaxsiy ma'lumotsiz), vakansiya va nomzodni tasdiqlash (buyruqni «Buyruqlar»da imzolaydi);
  bo'lim rahbari / kafedra mudiri — o'z bo'limi: xodimlar ismi, lavozimi, stavkasi va muddat belgilari (shaxsiy ma'lumotsiz), vakansiya taklifi;
  qolganlar — faqat o'z shaxsiy ishi (o'qish uchun, /api/hr/me).
Har bir ko'rish, o'zgartirish va rad etilgan urinish audit jurnaliga yoziladi (resurs "hr").
"""
import datetime as dt, json, random, re, threading
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from . import clock, db, rbac
from .rbac import AccessDenied, Ctx

RES = rbac.HR
router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/hr"

ATTEST_YEARS = 5
QUAL_YEARS = 5
TEACH_UNIT = "Professor-o'qituvchi"
CONTRACT_TYPES = {"muddatli": "Muddatli mehnat shartnomasi", "muddatsiz": "Muddatsiz mehnat shartnomasi", "orindosh": "O'rindoshlik (muddatli)"}
EDUCATION = ("Oliy (magistr)", "Oliy (bakalavr)", "Oliy (mutaxassis)", "O'rta maxsus")
VAC_ST = {"taklif": "Bo'lim taklifi", "tasdiqda": "Rektor tasdig'ida", "ochiq": "Ochiq", "rad": "Rad etilgan", "yopilgan": "Yopilgan"}
CAND_ST = {"ariza": "Ariza", "suhbat": "Suhbat", "tanlandi": "Tanlandi (rektor tasdig'ida)", "tasdiqlandi": "Rektor tasdiqladi",
           "buyruq": "Buyruq loyihasida", "qabul_qilindi": "Ishga qabul qilindi", "rad": "Rad etildi"}
DIS_ST = {"ariza": "Ariza", "varaqa": "Topshirish varaqasi", "buyruq": "Buyruq loyihasida", "yakunlangan": "Bo'shatildi", "bekor": "Bekor qilindi"}
CHECK = {"accounts": "Akkauntlar bloklandi (AT bo'limi)", "property": "Moddiy boyliklar topshirildi (Xo'jalik bo'limi)",
         "library": "Kutubxona (ARM) qarzdorligi yo'q", "docs": "Ish hujjatlari topshirildi (bo'lim rahbari)", "finance": "Yakuniy hisob-kitob (Buxgalteriya)"}
TRAIN = {"attestatsiya": "Attestatsiya", "malaka": "Malaka oshirish"}
FULL = {"kadrlar"}
APPROVER = {"rektor"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS hr_files(staff_id INTEGER PRIMARY KEY, unit_key TEXT, department_id INT, rate REAL DEFAULT 1, education TEXT, specialty TEXT,
  degree TEXT, academic_title TEXT, contract_type TEXT, contract_no TEXT, contract_start TEXT, contract_end TEXT, last_attest TEXT, last_qual TEXT,
  status TEXT DEFAULT 'faol', dismissed_on TEXT, candidate_id INT, created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_hrf_unit ON hr_files(unit_key, status);
CREATE TABLE IF NOT EXISTS hr_positions(id INTEGER PRIMARY KEY, unit_key TEXT, position TEXT, plan REAL, updated_by INT, updated_at TEXT, UNIQUE(unit_key, position));
CREATE TABLE IF NOT EXISTS hr_contract_log(id INTEGER PRIMARY KEY, staff_id INT, action TEXT, contract_type TEXT, contract_no TEXT, old_end TEXT, new_end TEXT,
  note TEXT, by_id INT, by_name TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS hr_trainings(id INTEGER PRIMARY KEY, staff_id INT, kind TEXT, done_on TEXT, result TEXT, note TEXT, by_id INT, by_name TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS hr_vacancies(id INTEGER PRIMARY KEY, unit_key TEXT, position TEXT, rate REAL DEFAULT 1, requirements TEXT, note TEXT, status TEXT,
  created_by INT, created_by_name TEXT, created_at TEXT, decided_by INT, decided_at TEXT, decision_note TEXT, closed_at TEXT);
CREATE TABLE IF NOT EXISTS hr_candidates(id INTEGER PRIMARY KEY, vacancy_id INT, full_name TEXT, phone TEXT, education TEXT, degree TEXT, note TEXT,
  stage TEXT DEFAULT 'ariza', stage_note TEXT, order_id INT, staff_id INT, it_thread_id INT, start_date TEXT, contract_type TEXT, contract_end TEXT,
  created_by INT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS hr_dismissals(id INTEGER PRIMARY KEY, staff_id INT, reason TEXT, app_date TEXT, last_day TEXT, status TEXT DEFAULT 'ariza',
  checklist TEXT, order_id INT, it_thread_id INT, note TEXT, created_by INT, created_by_name TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS hr_meta(k TEXT PRIMARY KEY, v TEXT);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def _today() -> dt.date: return clock.today()
def _d(s) -> dt.date | None:
    try: return dt.date.fromisoformat(str(s)[:10]) if s else None
    except ValueError: return None
def _short(n): return (n or "").split(":", 1)[-1].strip()
def _bad(msg, code=400): raise HTTPException(code, msg)
def _years(d: dt.date, n: int) -> dt.date:
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(year=d.year + n, day=28)

# ---------------------------------------------------------------------------------------------
# Bo'limlar: staff.unit (matn) → org_units.key
# ---------------------------------------------------------------------------------------------
def _words(s): return [w for w in re.sub(r"[^\w'’ʻ-]+", " ", (s or "").lower()).split() if w]

def _units(con) -> dict:
    try: return {r["key"]: r for r in db.rows(con, "SELECT key, name, head, head_user FROM org_units ORDER BY ord")}
    except Exception: return {}

def unit_key_for(con, unit_name: str, full_name: str = "", units=None, tdept=None) -> str:
    units = units if units is not None else _units(con)
    if unit_name == TEACH_UNIT:
        if tdept is None:
            r = db.one(con, "SELECT department_id FROM teachers WHERE full_name=? LIMIT 1", (full_name,))
            d = r["department_id"] if r else None
        else: d = tdept.get(full_name)
        return f"kaf{d}" if d and f"kaf{d}" in units else "kafedralar"
    for k, u in units.items():
        if u["name"] == unit_name: return k
    w = _words(unit_name)[:2]
    for k, u in units.items():
        if len(w) == 2 and _words(u["name"])[:2] == w: return k
    return "x:" + (unit_name or "—")

def unit_name(con, key: str, units=None) -> str:
    units = units if units is not None else _units(con)
    if key in units: return units[key]["name"]
    if key == "kafedralar": return "Kafedralar (biriktirilmagan)"
    return (key or "")[2:] if (key or "").startswith("x:") else (key or "—")

def staff_unit_text(con, key: str) -> str:
    """Yangi xodim uchun staff.unit matni (boshqa modullar shu matnni ishlatadi)."""
    if (key or "").startswith("kaf"): return TEACH_UNIT
    r = db.one(con, "SELECT unit FROM staff s JOIN hr_files f ON f.staff_id=s.id WHERE f.unit_key=? GROUP BY unit ORDER BY COUNT(*) DESC LIMIT 1", (key,))
    return r["unit"] if r else unit_name(con, key)

# ---------------------------------------------------------------------------------------------
# init / seed
# ---------------------------------------------------------------------------------------------
def init(con):
    con.executescript(SCHEMA); con.commit()
    try:
        sync_files(con)
        seed_demo(con)
    except Exception as e:          # demo ma'lumot tayyorlanmasa ham server ishlashi kerak
        import traceback; traceback.print_exc(); print("kadrlar.seed xatosi:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def sync_files(con) -> int:
    """staff jadvalidagi har bir xodim uchun shaxsiy ish (yo'q bo'lsa) — sintetik, deterministik qiymatlar bilan. Idempotent."""
    have = {r[0] for r in con.execute("SELECT staff_id FROM hr_files")}
    rows = [r for r in db.rows(con, "SELECT * FROM staff ORDER BY id") if r["id"] not in have]
    if not rows: return 0
    units = _units(con)
    tch = {r["full_name"]: r for r in db.rows(con, "SELECT full_name, department_id, degree, position FROM teachers")}
    tdept = {k: v["department_id"] for k, v in tch.items()}
    today = _today(); ts = _now()
    for s in rows:
        rnd = random.Random(s["id"] * 7919)
        t = tch.get(s["full_name"]); teacher = s["unit"] == TEACH_UNIT
        hired = _d(s.get("hired")) or today - dt.timedelta(days=rnd.randint(200, 2500))
        if teacher:
            ctype = "orindosh" if rnd.random() < 0.12 else "muddatli"
            rate = 0.5 if ctype == "orindosh" else rnd.choice((1.0, 1.0, 1.0, 1.0, 0.75))
        else:
            ctype = "muddatli" if rnd.random() < 0.3 else "muddatsiz"
            rate = 1.0
        # shartnoma muddati: demo uchun bir qismi yaqin 30/60 kunda tugaydi, bir nechtasi o'tib ketgan
        b = s["id"] % 23
        if ctype == "muddatsiz": end = None
        elif b == 0: end = today - dt.timedelta(days=rnd.randint(2, 20))
        elif b == 1: end = today + dt.timedelta(days=rnd.randint(3, 30))
        elif b == 3: end = today + dt.timedelta(days=rnd.randint(31, 60))
        else: end = today + dt.timedelta(days=rnd.randint(61, 900))
        cstart = max(hired, (end - dt.timedelta(days=365 * rnd.choice((1, 2, 3)))) if end else hired)
        la = today - dt.timedelta(days=rnd.randint(30, 365 * 6 + 120))
        la = max(la, hired) if hired < today - dt.timedelta(days=60) else None
        lq = (today - dt.timedelta(days=rnd.randint(30, 365 * 6 + 60))) if teacher else None
        deg = (t or {}).get("degree") or ("—" if teacher else rnd.choice(("—", "—", "—", "—", "PhD")))
        if deg in ("", None): deg = "—"
        pos = (t or {}).get("position") or s.get("position") or ""
        title = "Professor" if pos == "Professor" else "Dotsent" if pos == "Dotsent" else "—"
        edu = "Oliy (magistr)" if teacher or deg != "—" else rnd.choice(EDUCATION[:3])
        spec = rnd.choice(("Iqtisodiyot", "Moliya", "Menejment", "Pedagogika", "Filologiya", "Axborot texnologiyalari", "Buxgalteriya hisobi", "Huquqshunoslik"))
        con.execute("""INSERT INTO hr_files(staff_id,unit_key,department_id,rate,education,specialty,degree,academic_title,contract_type,contract_no,contract_start,
                       contract_end,last_attest,last_qual,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'faol',?,?)""",
                    (s["id"], unit_key_for(con, s["unit"], s["full_name"], units, tdept), tdept.get(s["full_name"]) if teacher else None, rate, edu, spec, deg, title,
                     ctype, f"MSh-{cstart.year}/{s['id']:04d}", cstart.isoformat(), end.isoformat() if end else None,
                     la.isoformat() if la else None, lq.isoformat() if lq else None, ts, ts))
    con.commit()
    return len(rows)

def seed_demo(con):
    if db.one(con, "SELECT v FROM hr_meta WHERE k='seed'"): return
    ts = _now(); today = _today()
    # shtat jadvali: amaldagi stavkalar + ba'zi lavozimlarda bo'sh stavka
    fact = db.rows(con, """SELECT f.unit_key, s.position, SUM(f.rate) r FROM hr_files f JOIN staff s ON s.id=f.staff_id WHERE f.status='faol'
                           GROUP BY f.unit_key, s.position""")
    for i, r in enumerate(fact):
        extra = 1.0 if i % 5 == 0 else 0.5 if i % 7 == 0 else 0.0
        con.execute("INSERT OR IGNORE INTO hr_positions(unit_key,position,plan,updated_at) VALUES(?,?,?,?)", (r["unit_key"], r["position"], round(r["r"] + extra, 2), ts))
    kadr = db.one(con, "SELECT id, full_name FROM users WHERE role='kadrlar' ORDER BY id LIMIT 1") or {"id": None, "full_name": "Kadrlar bo'limi"}
    units = _units(con)
    def vac(unit, pos, rate, status, req, days_ago, by=None):
        if unit not in units: return None
        return con.execute("""INSERT INTO hr_vacancies(unit_key,position,rate,requirements,status,created_by,created_by_name,created_at,decided_at)
                              VALUES(?,?,?,?,?,?,?,?,?)""", (unit, pos, rate, req, status, (by or kadr)["id"], (by or kadr)["full_name"],
                                                             (clock.now() - dt.timedelta(days=days_ago)).isoformat(timespec="seconds"),
                                                             ts if status == "ochiq" else None)).lastrowid
    kaf = next((k for k in units if k.startswith("kaf")), None)
    v1 = vac(kaf, "Katta o'qituvchi", 1.0, "ochiq", "Magistr, kamida 3 yil pedagogik staj; ingliz tili B2", 21)
    v2 = vac("buxgalteriya", "Bosh mutaxassis", 1.0, "ochiq", "Oliy iqtisodiy ma'lumot, 1C bilan ishlash tajribasi", 14)
    vac("xalqaro", "Mutaxassis", 1.0, "tasdiqda", "Ingliz tili C1, xalqaro grantlar bilan ishlash", 3)
    hu = units.get("amaliyot", {}).get("head_user")
    head = db.one(con, "SELECT id, full_name FROM users WHERE id=?", (hu,)) if hu else None
    vac("amaliyot", "Inspektor", 0.5, "taklif", "Amaliyot bazalari bilan ishlash tajribasi", 1, head)
    def cand(v, name, edu, deg, stage, note=""):
        if not v: return
        con.execute("""INSERT INTO hr_candidates(vacancy_id,full_name,phone,education,degree,note,stage,created_by,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", (v, name, "+998 90 000-00-00", edu, deg, note, stage, kadr["id"], ts, ts))
    # nomzodlar — sintetik ismlar (real shaxslar emas)
    cand(v1, "Nomzod A. (sintetik)", "Oliy (magistr)", "PhD", "tanlandi", "Ochiq dars yaxshi baholandi")
    cand(v1, "Nomzod B. (sintetik)", "Oliy (magistr)", "—", "suhbat")
    cand(v1, "Nomzod C. (sintetik)", "Oliy (bakalavr)", "—", "rad", "Talabga javob bermaydi (magistr emas)")
    cand(v2, "Nomzod D. (sintetik)", "Oliy (bakalavr)", "—", "ariza")
    cand(v2, "Nomzod E. (sintetik)", "Oliy (magistr)", "—", "suhbat")
    # bitta bo'shatish jarayoni (topshirish varaqasi bosqichida) — administrativ xodim
    s = db.one(con, """SELECT f.staff_id FROM hr_files f JOIN staff s ON s.id=f.staff_id WHERE f.status='faol' AND s.unit NOT IN (?, 'Rektorat')
                       AND s.position NOT LIKE '%boshlig%' ORDER BY f.staff_id DESC LIMIT 1""", (TEACH_UNIT,))
    if s:
        ck = {k: False for k in CHECK}; ck.update(property=True, docs=True)
        con.execute("""INSERT INTO hr_dismissals(staff_id,reason,app_date,last_day,status,checklist,created_by,created_by_name,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", (s["staff_id"], "O'z xohishiga ko'ra (ariza)", (today - dt.timedelta(days=4)).isoformat(),
                                                       (today + dt.timedelta(days=10)).isoformat(), "varaqa", json.dumps(ck), kadr["id"], kadr["full_name"], ts, ts))
    con.execute("INSERT OR REPLACE INTO hr_meta(k,v) VALUES('seed',?)", (ts,))
    con.commit()

# ---------------------------------------------------------------------------------------------
# Kim nimani ko'radi
# ---------------------------------------------------------------------------------------------
def _audit(c, action, ok=True, detail=""):
    rbac.audit(_con, c, f"kadrlar: {action}", RES, ok, detail)

def head_unit(c: Ctx) -> str | None:
    """Foydalanuvchi rahbar bo'lgan bo'lim (org_units.head_user) yoki kafedra mudirining kafedrasi."""
    if c.role.key == "kafedra" and c.user.get("department_id"): return f"kaf{int(c.user['department_id'])}"
    r = db.one(_con, "SELECT key FROM org_units WHERE head_user=? LIMIT 1", (c.user["id"],))
    return r["key"] if r else None

def mode(c: Ctx) -> str:
    if c.role.key in FULL and c.can(RES): return "full"
    if c.role.key in APPROVER: return "rektor"
    if head_unit(c): return "head"
    return "own"

def C(request: Request, action: str, detail: str = "", need: tuple = ()) -> Ctx:
    c = _ctx(request)
    if c.channel == "telegram":           # rbac.TELEGRAM_BLOCKED: kadrlar ma'lumoti Telegram'ga chiqmaydi
        _audit(c, action, False, "telegram"); raise AccessDenied("⛔ Kadrlar ma'lumoti Telegram orqali uzatilmaydi. So'rov audit jurnaliga yozildi.")
    if need and mode(c) not in need:
        _audit(c, action, False, detail)
        raise AccessDenied(f"⛔ «{action}» — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")
    return c

def _scope(c: Ctx, m: str, alias="f") -> tuple[str, list]:
    if m in ("full", "rektor"): return "1=1", []
    if m == "head": return f"{alias}.unit_key=?", [head_unit(c)]
    return "0", []

# ---------------------------------------------------------------------------------------------
# Belgilar (muddatlar)
# ---------------------------------------------------------------------------------------------
def flags(f: dict, today: dt.date | None = None) -> dict:
    today = today or _today(); out = {}
    ce = _d(f.get("contract_end"))
    if f.get("status", "faol") == "faol" and ce:
        left = (ce - today).days
        out["contract_days"] = left
        out["contract"] = "expired" if left < 0 else "d30" if left <= 30 else "d60" if left <= 60 else None
    la = _d(f.get("last_attest"))
    if f.get("status", "faol") == "faol":
        due = _years(la, ATTEST_YEARS) if la else None
        out["attest_due"] = due.isoformat() if due else None
        out["attest"] = "none" if not la else "overdue" if due < today else "soon" if (due - today).days <= 90 else None
        if (f.get("unit_key") or "").startswith("kaf") or f.get("department_id") or f.get("last_qual"):
            lq = _d(f.get("last_qual")); qd = _years(lq, QUAL_YEARS) if lq else None
            out["qual_due"] = qd.isoformat() if qd else None
            out["qual"] = "none" if not lq else "overdue" if qd < today else "soon" if (qd - today).days <= 90 else None
    return out

def _sync_orders():
    """«Buyruqlar»da imzolangan qabul/bo'shatish buyruqlari → shaxsiy ishga ta'sir (idempotent; har bir o'qishda chaqiriladi)."""
    with _lock:
        for k in db.rows(_con, """SELECT k.*, o.status ost FROM hr_candidates k JOIN orders o ON o.id=k.order_id WHERE k.stage='buyruq'
                                   AND o.status IN ('imzolangan','bekor')"""):
            if k["ost"] == "bekor":      # loyiha o'chirildi — nomzod qayta «tasdiqlandi» bosqichiga
                _con.execute("UPDATE hr_candidates SET stage='tasdiqlandi', order_id=NULL, updated_at=? WHERE id=?", (_now(), k["id"])); continue
            _hire(k)
        for d in db.rows(_con, """SELECT d.*, o.status ost, o.order_date FROM hr_dismissals d JOIN orders o ON o.id=d.order_id WHERE d.status='buyruq'
                                   AND o.status IN ('imzolangan','bekor')"""):
            if d["ost"] == "bekor":
                _con.execute("UPDATE hr_dismissals SET status='varaqa', order_id=NULL, updated_at=? WHERE id=?", (_now(), d["id"])); continue
            _con.execute("UPDATE hr_files SET status='boshatilgan', dismissed_on=?, updated_at=? WHERE staff_id=?", (d["last_day"], _now(), d["staff_id"]))
            _con.execute("UPDATE hr_dismissals SET status='yakunlangan', updated_at=? WHERE id=?", (_now(), d["id"]))
            _con.execute("INSERT INTO hr_contract_log(staff_id,action,old_end,new_end,note,ts) VALUES(?,?,?,?,?,?)",
                         (d["staff_id"], "bekor qilindi (bo'shatish)", None, d["last_day"], f"Buyruq #{d['order_id']}", _now()))
        _con.commit()

def _hire(k: dict):
    v = db.one(_con, "SELECT * FROM hr_vacancies WHERE id=?", (k["vacancy_id"],))
    o = db.one(_con, "SELECT params FROM orders WHERE id=?", (k["order_id"],))
    p = json.loads((o or {}).get("params") or "{}")
    start = p.get("date_from") or _today().isoformat()
    unit_txt = staff_unit_text(_con, v["unit_key"])
    sid = _con.execute("INSERT INTO staff(full_name, unit, position, salary, hired, passport) VALUES(?,?,?,?,?,?)",
                       (k["full_name"], unit_txt, v["position"], None, start, None)).lastrowid
    dep = int(v["unit_key"][3:]) if v["unit_key"].startswith("kaf") and v["unit_key"][3:].isdigit() else None
    if dep:      # kafedra o'qituvchisi — o'qituvchilar ro'yxatiga ham (dars yuklamasi keyin taqsimlanadi)
        _con.execute("INSERT INTO teachers(full_name, department_id, faculty_id, degree, position, load_hours, h_index) VALUES(?,?,(SELECT faculty_id FROM departments WHERE id=?),?,?,0,0)",
                     (k["full_name"], dep, dep, k["degree"] or "—", v["position"]))
    ts = _now()
    _con.execute("""INSERT INTO hr_files(staff_id,unit_key,department_id,rate,education,degree,academic_title,contract_type,contract_no,contract_start,contract_end,
                    status,candidate_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,'faol',?,?,?)""",
                 (sid, v["unit_key"], dep, v["rate"], k["education"], k["degree"] or "—", "—", k["contract_type"] or "muddatli",
                  f"MSh-{start[:4]}/{sid:04d}", start, k["contract_end"], k["id"], ts, ts))
    _con.execute("INSERT INTO hr_contract_log(staff_id,action,contract_type,contract_no,new_end,note,ts) VALUES(?,?,?,?,?,?,?)",
                 (sid, "tuzildi (ishga qabul)", k["contract_type"], f"MSh-{start[:4]}/{sid:04d}", k["contract_end"], f"Buyruq #{k['order_id']}", ts))
    _con.execute("UPDATE hr_candidates SET stage='qabul_qilindi', staff_id=?, updated_at=? WHERE id=?", (sid, ts, k["id"]))
    hired = db.one(_con, "SELECT COUNT(*) n FROM hr_candidates WHERE vacancy_id=? AND stage='qabul_qilindi'", (v["id"],))["n"]
    if hired >= 1:
        _con.execute("UPDATE hr_vacancies SET status='yopilgan', closed_at=? WHERE id=? AND status='ochiq'", (ts, v["id"]))

# ---------------------------------------------------------------------------------------------
# Ko'rinishlar
# ---------------------------------------------------------------------------------------------
def _file_row(f: dict, full=True, units=None) -> dict:
    fl = flags(f)
    base = {"id": f["staff_id"], "name": f["full_name"], "position": f["position"], "unit_key": f["unit_key"], "unit": unit_name(_con, f["unit_key"], units),
            "rate": f["rate"], "status": f["status"], "flags": fl}
    if full:
        base.update(education=f["education"], specialty=f["specialty"], degree=f["degree"], academic_title=f["academic_title"],
                    contract_type=f["contract_type"], contract_no=f["contract_no"], contract_start=f["contract_start"], contract_end=f["contract_end"],
                    last_attest=f["last_attest"], last_qual=f["last_qual"], hired=f["hired"], dismissed_on=f["dismissed_on"])
    else:   # bo'lim rahbari: muddat belgilarigina (sana va shaxsiy ma'lumotsiz)
        base["flags"] = {k: v for k, v in fl.items() if k in ("contract", "attest", "qual")}
    return base

_FSQL = "SELECT f.*, s.full_name, s.position, s.hired FROM hr_files f JOIN staff s ON s.id=f.staff_id"

def kpi(c: Ctx, m: str) -> dict:
    w, a = _scope(c, m)
    rows = db.rows(_con, f"{_FSQL} WHERE {w} AND f.status='faol'", a)
    fl = [flags(r) for r in rows]
    pw = "1=1" if m in ("full", "rektor") else "unit_key=?"
    pa = [] if m in ("full", "rektor") else [head_unit(c)]
    plan = db.one(_con, f"SELECT COALESCE(SUM(plan),0) p FROM hr_positions WHERE {pw}", pa)["p"]
    fact = round(sum(r["rate"] or 0 for r in rows), 2)
    vw = "1=1" if m in ("full", "rektor") else "unit_key=?"
    vac = {r["status"]: r["n"] for r in db.rows(_con, f"SELECT status, COUNT(*) n FROM hr_vacancies WHERE {vw} GROUP BY status", pa)}
    return {"headcount": len(rows), "rates_plan": round(plan, 2), "rates_fact": fact, "vacant_rates": round(max(0, plan - fact), 2),
            "contract_30": sum(1 for x in fl if x.get("contract") == "d30"), "contract_60": sum(1 for x in fl if x.get("contract") == "d60"),
            "contract_expired": sum(1 for x in fl if x.get("contract") == "expired"),
            "attest_overdue": sum(1 for x in fl if x.get("attest") in ("overdue", "none")), "attest_soon": sum(1 for x in fl if x.get("attest") == "soon"),
            "qual_overdue": sum(1 for x in fl if x.get("qual") in ("overdue", "none")), "qual_soon": sum(1 for x in fl if x.get("qual") == "soon"),
            "vacancies_open": vac.get("ochiq", 0), "vacancies_pending": vac.get("tasdiqda", 0), "vacancies_proposed": vac.get("taklif", 0),
            "candidates_pending": db.one(_con, f"""SELECT COUNT(*) n FROM hr_candidates k JOIN hr_vacancies v ON v.id=k.vacancy_id WHERE k.stage='tanlandi' AND {vw.replace('unit_key', 'v.unit_key')}""", pa)["n"],
            "dismissals": db.one(_con, f"""SELECT COUNT(*) n FROM hr_dismissals d JOIN hr_files f ON f.staff_id=d.staff_id WHERE d.status IN ('ariza','varaqa','buyruq') AND {w}""", a)["n"]}

def by_unit(c: Ctx, m: str) -> list[dict]:
    units = _units(_con); w, a = _scope(c, m)
    agg = {}
    for r in db.rows(_con, f"{_FSQL} WHERE {w} AND f.status='faol'", a):
        g = agg.setdefault(r["unit_key"], {"key": r["unit_key"], "name": unit_name(_con, r["unit_key"], units), "headcount": 0, "fact": 0.0,
                                           "plan": 0.0, "contract_60": 0, "contract_expired": 0, "attest_overdue": 0, "qual_overdue": 0})
        fl = flags(r); g["headcount"] += 1; g["fact"] += r["rate"] or 0
        g["contract_60"] += fl.get("contract") in ("d30", "d60"); g["contract_expired"] += fl.get("contract") == "expired"
        g["attest_overdue"] += fl.get("attest") in ("overdue", "none"); g["qual_overdue"] += fl.get("qual") in ("overdue", "none")
    pw = "1=1" if m in ("full", "rektor") else "unit_key=?"
    for r in db.rows(_con, f"SELECT unit_key, SUM(plan) p FROM hr_positions WHERE {pw} GROUP BY unit_key", [] if m in ("full", "rektor") else [head_unit(c)]):
        g = agg.setdefault(r["unit_key"], {"key": r["unit_key"], "name": unit_name(_con, r["unit_key"], units), "headcount": 0, "fact": 0.0, "plan": 0.0,
                                           "contract_60": 0, "contract_expired": 0, "attest_overdue": 0, "qual_overdue": 0})
        g["plan"] = round(r["p"] or 0, 2)
    out = []
    for g in agg.values():
        g["fact"] = round(g["fact"], 2); g["vacant"] = round(max(0, g["plan"] - g["fact"]), 2); out.append(g)
    return sorted(out, key=lambda g: (-g["vacant"], g["name"]))

# ---------------------------------------------------------------------------------------------
# API: meta, jamlanma, shaxsiy ishlar
# ---------------------------------------------------------------------------------------------
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request, "meta"); m = mode(c); _sync_orders()
    hu = head_unit(c) if m == "head" else None
    units = _units(_con)
    return {"mode": m, "unit": {"key": hu, "name": unit_name(_con, hu, units)} if hu else None, "today": _today().isoformat(),
            "caps": {"edit": m == "full", "approve": m == "rektor", "propose": m in ("head", "full")},
            "units": [{"key": k, "name": u["name"]} for k, u in units.items()] if m in ("full", "rektor") else [],
            "contract_types": CONTRACT_TYPES, "education": EDUCATION, "vac_status": VAC_ST, "cand_stage": CAND_ST, "dis_status": DIS_ST,
            "checklist": CHECK, "trainings": TRAIN, "years": {"attest": ATTEST_YEARS, "qual": QUAL_YEARS}}

@router.get(P + "/summary")
def api_summary(request: Request):
    c = C(request, "jamlanma", need=("full", "rektor", "head")); m = mode(c); _sync_orders()
    _audit(c, "jamlanma", True, m)
    return {"mode": m, "kpi": kpi(c, m), "by_unit": by_unit(c, m)}

@router.get(P + "/staff")
def api_staff(request: Request, q: str = "", unit: str = "", flag: str = "", status: str = "faol", offset: int = 0, limit: int = 100):
    c = C(request, "xodimlar ro'yxati", need=("full", "head")); m = mode(c); _sync_orders()
    w, a = _scope(c, m)
    if status in ("faol", "boshatilgan"): w += " AND f.status=?"; a.append(status)
    if unit and m == "full": w += " AND f.unit_key=?"; a.append(unit)
    if q.strip(): w += " AND (s.full_name LIKE ? OR s.position LIKE ?)"; a += [f"%{q.strip()}%"] * 2
    rows = db.rows(_con, f"{_FSQL} WHERE {w} ORDER BY s.full_name", a)
    units = _units(_con)
    items = [_file_row(r, m == "full", units) for r in rows]
    if flag:
        key, _, val = flag.partition(":")
        items = [x for x in items if (x["flags"].get(key) in (val.split("|") if val else ("d30", "d60", "expired", "overdue", "none", "soon")))]
    _audit(c, "xodimlar ro'yxati", True, f"{m} · {len(items)} ta" + (f" · {flag}" if flag else ""))
    limit = max(1, min(int(limit or 100), 500))
    return {"total": len(items), "items": items[offset:offset + limit]}

def _own_staff_id(c: Ctx) -> int | None:
    n = _short(c.user.get("full_name"))
    r = db.rows(_con, "SELECT f.staff_id FROM hr_files f JOIN staff s ON s.id=f.staff_id WHERE s.full_name=?", (n,)) if n and ":" in (c.user.get("full_name") or "") else []
    return r[0]["staff_id"] if len(r) == 1 else None

def file_detail(sid: int, full=True) -> dict:
    f = db.one(_con, f"{_FSQL} WHERE f.staff_id=?", (sid,))
    if not f: _bad("Shaxsiy ish topilmadi", 404)
    v = _file_row(f, True)
    v["contract_log"] = db.rows(_con, "SELECT action, contract_type, contract_no, old_end, new_end, note, by_name, ts FROM hr_contract_log WHERE staff_id=? ORDER BY id DESC", (sid,))
    v["trainings"] = db.rows(_con, "SELECT kind, done_on, result, note, by_name, ts FROM hr_trainings WHERE staff_id=? ORDER BY done_on DESC, id DESC", (sid,))
    try:
        v["absences"] = db.rows(_con, "SELECT id, kind, start, end, status FROM staff_absences WHERE staff_id=? ORDER BY start DESC LIMIT 10", (sid,))
    except Exception: v["absences"] = []
    v["dismissal"] = db.one(_con, "SELECT id, status, last_day, reason FROM hr_dismissals WHERE staff_id=? AND status!='bekor' ORDER BY id DESC LIMIT 1", (sid,))
    if not full:
        for k in ("contract_no",): v.pop(k, None)
    return v

@router.get(P + "/staff/{sid}")
def api_file(sid: int, request: Request):
    c = C(request, "shaxsiy ish", f"#{sid}"); m = mode(c); _sync_orders()
    if m != "full" and _own_staff_id(c) != sid:
        _audit(c, "shaxsiy ish", False, f"#{sid}")
        raise AccessDenied("⛔ Xodimning shaxsiy ishini faqat Kadrlar bo'limi ko'radi. So'rov audit jurnaliga yozildi.")
    _audit(c, "shaxsiy ish", True, f"#{sid}")
    return file_detail(sid)

@router.get(P + "/me")
def api_me(request: Request):
    c = C(request, "o'z shaxsiy ishi"); sid = _own_staff_id(c)
    if not sid: return {"found": False}
    _audit(c, "o'z shaxsiy ishi", True, f"#{sid}")
    return {"found": True, **file_detail(sid, full=False)}

class FileIn(BaseModel):
    rate: float | None = None
    education: str | None = None
    specialty: str | None = None
    degree: str | None = None
    academic_title: str | None = None
    position: str | None = None
    unit_key: str | None = None

@router.post(P + "/staff/{sid}")
def api_file_edit(sid: int, b: FileIn, request: Request):
    c = C(request, "shaxsiy ishni tahrirlash", f"#{sid}", need=("full",))
    f = db.one(_con, "SELECT * FROM hr_files WHERE staff_id=?", (sid,))
    if not f: _bad("Shaxsiy ish topilmadi", 404)
    upd = {}
    if b.rate is not None:
        if not 0.1 <= b.rate <= 1.5: _bad("Stavka 0.1–1.5 oralig'ida bo'lishi kerak")
        upd["rate"] = round(b.rate, 2)
    for k in ("education", "specialty", "degree", "academic_title"):
        v = getattr(b, k)
        if v is not None: upd[k] = v.strip()[:120] or None
    if b.unit_key is not None:
        if b.unit_key not in _units(_con): _bad("Bo'lim topilmadi")
        upd["unit_key"] = b.unit_key
    ts = _now()
    if upd:
        _con.execute(f"UPDATE hr_files SET {', '.join(f'{k}=?' for k in upd)}, updated_at=? WHERE staff_id=?", (*upd.values(), ts, sid))
    if b.position is not None and b.position.strip():
        _con.execute("UPDATE staff SET position=? WHERE id=?", (b.position.strip()[:120], sid)); upd["position"] = b.position.strip()
    _con.commit()
    _audit(c, "shaxsiy ish tahrirlandi", True, f"#{sid}: {', '.join(upd) or '—'}")
    return {"ok": True, "changed": list(upd)}

class RenewIn(BaseModel):
    new_end: str | None = None
    contract_type: str = "muddatli"
    contract_no: str = ""
    note: str = ""

@router.post(P + "/staff/{sid}/renew")
def api_renew(sid: int, b: RenewIn, request: Request):
    c = C(request, "shartnomani uzaytirish", f"#{sid}", need=("full",))
    f = db.one(_con, "SELECT * FROM hr_files WHERE staff_id=?", (sid,))
    if not f: _bad("Shaxsiy ish topilmadi", 404)
    if f["status"] != "faol": _bad("Bo'shatilgan xodim shartnomasini uzaytirib bo'lmaydi", 409)
    if b.contract_type not in CONTRACT_TYPES: _bad("Shartnoma turi noto'g'ri")
    ne = _d(b.new_end)
    if b.contract_type == "muddatsiz": ne = None
    else:
        if not ne: _bad("Yangi tugash sanasi kiritilmagan")
        if ne <= _today(): _bad("Yangi muddat bugundan keyin bo'lishi kerak")
        if ne > _today() + dt.timedelta(days=365 * 5 + 2): _bad("Muddatli shartnoma 5 yildan oshmaydi (Mehnat kodeksi)")
    old = f["contract_end"]; start = max(_today(), (_d(old) or _today()) + dt.timedelta(days=1)).isoformat()
    no = (b.contract_no or "").strip()[:40] or f"MSh-{_today().year}/{sid:04d}-{db.one(_con, 'SELECT COUNT(*) n FROM hr_contract_log WHERE staff_id=?', (sid,))['n'] + 1}"
    ts = _now()
    _con.execute("UPDATE hr_files SET contract_type=?, contract_no=?, contract_start=?, contract_end=?, updated_at=? WHERE staff_id=?",
                 (b.contract_type, no, start, ne.isoformat() if ne else None, ts, sid))
    _con.execute("INSERT INTO hr_contract_log(staff_id,action,contract_type,contract_no,old_end,new_end,note,by_id,by_name,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (sid, "uzaytirildi", b.contract_type, no, old, ne.isoformat() if ne else None, b.note.strip()[:300], c.user["id"], c.user["full_name"], ts))
    _con.commit()
    _audit(c, "shartnoma uzaytirildi", True, f"#{sid} · {old or '—'} → {ne or 'muddatsiz'}")
    return {"ok": True, "contract_no": no, "contract_end": ne.isoformat() if ne else None}

class TrainIn(BaseModel):
    kind: str
    done_on: str
    result: str = ""
    note: str = ""

@router.post(P + "/staff/{sid}/training")
def api_training(sid: int, b: TrainIn, request: Request):
    c = C(request, "attestatsiya / malaka oshirish", f"#{sid}", need=("full",))
    f = db.one(_con, "SELECT * FROM hr_files WHERE staff_id=?", (sid,))
    if not f: _bad("Shaxsiy ish topilmadi", 404)
    if b.kind not in TRAIN: _bad("Tur noto'g'ri (attestatsiya yoki malaka)")
    d = _d(b.done_on)
    if not d: _bad("Sana noto'g'ri")
    if d > _today(): _bad("Kelajakdagi sana kiritib bo'lmaydi")
    ts = _now(); col = "last_attest" if b.kind == "attestatsiya" else "last_qual"
    _con.execute("INSERT INTO hr_trainings(staff_id,kind,done_on,result,note,by_id,by_name,ts) VALUES(?,?,?,?,?,?,?,?)",
                 (sid, b.kind, d.isoformat(), b.result.strip()[:120], b.note.strip()[:300], c.user["id"], c.user["full_name"], ts))
    _con.execute(f"UPDATE hr_files SET {col}=MAX(COALESCE({col},''), ?), updated_at=? WHERE staff_id=?", (d.isoformat(), ts, sid))
    _con.commit()
    _audit(c, f"{TRAIN[b.kind].lower()} qayd etildi", True, f"#{sid} · {d}")
    return {"ok": True, "next_due": _years(d, ATTEST_YEARS if b.kind == "attestatsiya" else QUAL_YEARS).isoformat()}

@router.get(P + "/alerts")
def api_alerts(request: Request):
    c = C(request, "muddat ogohlantirishlari", need=("full", "head", "rektor")); m = mode(c); _sync_orders()
    if m == "rektor":
        _audit(c, "muddat ogohlantirishlari", True, "jamlangan")
        return {"aggregate": True, "kpi": kpi(c, m), "by_unit": [u for u in by_unit(c, m) if u["contract_60"] or u["contract_expired"] or u["attest_overdue"] or u["qual_overdue"]]}
    w, a = _scope(c, m); units = _units(_con)
    rows = [_file_row(r, m == "full", units) for r in db.rows(_con, f"{_FSQL} WHERE {w} AND f.status='faol' ORDER BY s.full_name", a)]
    def pick(key, vals, sort):
        L = [x for x in rows if x["flags"].get(key) in vals]
        return sorted(L, key=sort)
    out = {"aggregate": False,
           "contracts": pick("contract", ("expired", "d30", "d60"), lambda x: x["flags"].get("contract_days", 0) if m == "full" else ("expired", "d30", "d60").index(x["flags"]["contract"])),
           "attest": pick("attest", ("overdue", "none", "soon"), lambda x: (x["flags"].get("attest_due") or "") if m == "full" else 0),
           "qual": pick("qual", ("overdue", "none", "soon"), lambda x: (x["flags"].get("qual_due") or "") if m == "full" else 0)}
    _audit(c, "muddat ogohlantirishlari", True, f"{m} · shartnoma {len(out['contracts'])} · attestatsiya {len(out['attest'])} · malaka {len(out['qual'])}")
    return out

# ---------------------------------------------------------------------------------------------
# Shtat jadvali
# ---------------------------------------------------------------------------------------------
@router.get(P + "/staffing")
def api_staffing(request: Request, unit: str = ""):
    c = C(request, "shtat jadvali", need=("full", "rektor", "head")); m = mode(c)
    units = _units(_con)
    pw, pa = ("unit_key=?", [head_unit(c)]) if m == "head" else (("unit_key=?", [unit]) if unit else ("1=1", []))
    plan = {(r["unit_key"], r["position"]): r for r in db.rows(_con, f"SELECT * FROM hr_positions WHERE {pw}", pa)}
    fw = pw.replace("unit_key", "f.unit_key")
    fact = {}
    for r in db.rows(_con, f"SELECT f.unit_key, s.position, SUM(f.rate) r, COUNT(*) n FROM hr_files f JOIN staff s ON s.id=f.staff_id WHERE f.status='faol' AND {fw} GROUP BY f.unit_key, s.position", pa):
        fact[(r["unit_key"], r["position"])] = r
    rows = []
    for key in sorted(set(plan) | set(fact), key=lambda k: (unit_name(_con, k[0], units), k[1] or "")):
        p = plan.get(key); f = fact.get(key)
        pl = round(p["plan"], 2) if p else 0.0; fa = round(f["r"], 2) if f else 0.0
        rows.append({"id": p["id"] if p else None, "unit_key": key[0], "unit": unit_name(_con, key[0], units), "position": key[1], "plan": pl, "fact": fa,
                     "people": f["n"] if f else 0, "vacant": round(max(0, pl - fa), 2), "over": round(max(0, fa - pl), 2)})
    _audit(c, "shtat jadvali", True, f"{m} · {len(rows)} qator")
    return {"items": rows, "total": {"plan": round(sum(r["plan"] for r in rows), 2), "fact": round(sum(r["fact"] for r in rows), 2),
                                     "vacant": round(sum(r["vacant"] for r in rows), 2)}}

class PosIn(BaseModel):
    unit_key: str
    position: str
    plan: float

@router.post(P + "/staffing")
def api_staffing_set(b: PosIn, request: Request):
    c = C(request, "shtat jadvalini o'zgartirish", f"{b.unit_key} · {b.position}", need=("full",))
    if b.unit_key not in _units(_con) and not b.unit_key.startswith("x:"): _bad("Bo'lim topilmadi")
    pos = (b.position or "").strip()[:120]
    if not pos: _bad("Lavozim kiritilmagan")
    if not 0 <= b.plan <= 200: _bad("Stavka soni 0–200 oralig'ida")
    _con.execute("""INSERT INTO hr_positions(unit_key,position,plan,updated_by,updated_at) VALUES(?,?,?,?,?)
                    ON CONFLICT(unit_key,position) DO UPDATE SET plan=excluded.plan, updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                 (b.unit_key, pos, round(b.plan, 2), c.user["id"], _now()))
    _con.commit()
    _audit(c, "shtat jadvali o'zgartirildi", True, f"{b.unit_key} · {pos} = {b.plan}")
    return {"ok": True}

# ---------------------------------------------------------------------------------------------
# Ishga qabul: vakansiya → nomzod → buyruq → AT so'rovi
# ---------------------------------------------------------------------------------------------
def _vac(vid) -> dict:
    v = db.one(_con, "SELECT * FROM hr_vacancies WHERE id=?", (vid,))
    if not v: _bad("Vakansiya topilmadi", 404)
    return v

def _cand(kid) -> dict:
    k = db.one(_con, "SELECT * FROM hr_candidates WHERE id=?", (kid,))
    if not k: _bad("Nomzod topilmadi", 404)
    return k

def _order_brief(oid):
    if not oid: return None
    o = db.one(_con, "SELECT id, reg_no, status FROM orders WHERE id=?", (oid,))
    if not o: return None
    st = {"loyiha": "Loyiha", "yuborilgan": "Imzoga yuborilgan", "kelishilgan": "Kelishilgan", "imzolangan": "Imzolangan", "bekor": "O'chirilgan"}.get(o["status"], o["status"])
    return {"id": o["id"], "reg_no": o["reg_no"] or f"Loyiha #{o['id']}", "status": st, "raw": o["status"], "link": {"view": "orders", "order": o["id"]}}

def _thread_brief(tid):
    if not tid: return None
    t = db.one(_con, "SELECT id, ref_no, status FROM portal_threads WHERE id=?", (tid,))
    return {"id": t["id"], "ref_no": t["ref_no"], "status": t["status"], "link": {"view": "portal", "thread": t["id"]}} if t else None

@router.get(P + "/vacancies")
def api_vacancies(request: Request, status: str = ""):
    c = C(request, "vakansiyalar", need=("full", "rektor", "head")); m = mode(c); _sync_orders()
    w, a = ("v.unit_key=?", [head_unit(c)]) if m == "head" else ("1=1", [])
    if status in VAC_ST: w += " AND v.status=?"; a.append(status)
    units = _units(_con); out = []
    for v in db.rows(_con, f"SELECT v.* FROM hr_vacancies v WHERE {w} ORDER BY CASE v.status WHEN 'tasdiqda' THEN 0 WHEN 'taklif' THEN 1 WHEN 'ochiq' THEN 2 ELSE 3 END, v.id DESC", a):
        ks = db.rows(_con, "SELECT * FROM hr_candidates WHERE vacancy_id=? ORDER BY id", (v["id"],))
        cands = [{"id": k["id"], "name": k["full_name"], "education": k["education"], "degree": k["degree"], "stage": k["stage"],
                  "stage_label": CAND_ST.get(k["stage"], k["stage"]), "note": k["note"] if m in ("full", "rektor") else None,
                  "phone": k["phone"] if m == "full" else None, "order": _order_brief(k["order_id"]), "it": _thread_brief(k["it_thread_id"]),
                  "staff_id": k["staff_id"], "start_date": k["start_date"], "contract_end": k["contract_end"]} for k in ks]
        out.append({**{x: v[x] for x in ("id", "unit_key", "position", "rate", "requirements", "note", "status", "created_by_name", "created_at", "decided_at", "decision_note", "closed_at")},
                    "unit": unit_name(_con, v["unit_key"], units), "status_label": VAC_ST.get(v["status"], v["status"]), "candidates": cands})
    _audit(c, "vakansiyalar", True, f"{m} · {len(out)} ta")
    return {"items": out}

class VacIn(BaseModel):
    unit_key: str = ""
    position: str
    rate: float = 1.0
    requirements: str = ""
    note: str = ""

@router.post(P + "/vacancies")
def api_vac_create(b: VacIn, request: Request):
    c = C(request, "vakansiya yaratish", b.position, need=("full", "head")); m = mode(c)
    unit = head_unit(c) if m == "head" else b.unit_key
    if m == "head" and b.unit_key and b.unit_key != unit:
        _audit(c, "vakansiya yaratish", False, f"boshqa bo'lim {b.unit_key}")
        raise AccessDenied("⛔ Bo'lim rahbari faqat o'z bo'limi uchun vakansiya taklif qiladi. So'rov audit jurnaliga yozildi.")
    if unit not in _units(_con): _bad("Bo'lim tanlanmagan")
    pos = (b.position or "").strip()[:120]
    if not pos: _bad("Lavozim kiritilmagan")
    if not 0.25 <= b.rate <= 1.5: _bad("Stavka 0.25–1.5 oralig'ida")
    st = "taklif" if m == "head" else "tasdiqda"
    vid = _con.execute("""INSERT INTO hr_vacancies(unit_key,position,rate,requirements,note,status,created_by,created_by_name,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                       (unit, pos, round(b.rate, 2), b.requirements.strip()[:600], b.note.strip()[:600], st, c.user["id"], c.user["full_name"], _now())).lastrowid
    _con.commit()
    _audit(c, "vakansiya yaratildi" if m == "full" else "vakansiya taklif qilindi", True, f"#{vid} · {unit} · {pos} · {b.rate}")
    return {"ok": True, "id": vid, "status": st}

@router.post(P + "/vacancies/{vid}/submit")
def api_vac_submit(vid: int, request: Request):
    c = C(request, "vakansiyani rektorga yuborish", f"#{vid}", need=("full",))
    v = _vac(vid)
    if v["status"] != "taklif": _bad("Faqat bo'lim taklifi rektorga yuboriladi", 409)
    _con.execute("UPDATE hr_vacancies SET status='tasdiqda' WHERE id=?", (vid,)); _con.commit()
    _audit(c, "vakansiya rektorga yuborildi", True, f"#{vid}")
    return {"ok": True}

class Decide(BaseModel):
    decision: str            # approve | reject
    note: str = ""

@router.post(P + "/vacancies/{vid}/decide")
def api_vac_decide(vid: int, b: Decide, request: Request):
    c = C(request, "vakansiyani tasdiqlash", f"#{vid}", need=("rektor",))
    v = _vac(vid)
    if v["status"] != "tasdiqda": _bad("Vakansiya tasdiq bosqichida emas", 409)
    if b.decision not in ("approve", "reject"): _bad("Qaror noto'g'ri")
    if b.decision == "reject" and not b.note.strip(): _bad("Rad etish sababi kiritilmagan")
    st = "ochiq" if b.decision == "approve" else "rad"
    _con.execute("UPDATE hr_vacancies SET status=?, decided_by=?, decided_at=?, decision_note=? WHERE id=?", (st, c.user["id"], _now(), b.note.strip()[:300], vid))
    _con.commit()
    _audit(c, "vakansiya tasdiqlandi" if st == "ochiq" else "vakansiya rad etildi", True, f"#{vid} · {v['position']}")
    return {"ok": True, "status": st}

@router.post(P + "/vacancies/{vid}/close")
def api_vac_close(vid: int, request: Request):
    c = C(request, "vakansiyani yopish", f"#{vid}", need=("full",))
    v = _vac(vid)
    if v["status"] not in ("ochiq", "taklif", "tasdiqda"): _bad("Vakansiya allaqachon yopilgan", 409)
    if db.one(_con, "SELECT 1 FROM hr_candidates WHERE vacancy_id=? AND stage='buyruq'", (vid,)): _bad("Nomzod buyruq loyihasida — avval buyruqni yakunlang", 409)
    _con.execute("UPDATE hr_vacancies SET status='yopilgan', closed_at=? WHERE id=?", (_now(), vid)); _con.commit()
    _audit(c, "vakansiya yopildi", True, f"#{vid}")
    return {"ok": True}

class CandIn(BaseModel):
    full_name: str
    phone: str = ""
    education: str = ""
    degree: str = ""
    note: str = ""

@router.post(P + "/vacancies/{vid}/candidates")
def api_cand_add(vid: int, b: CandIn, request: Request):
    c = C(request, "nomzod qo'shish", f"#{vid}", need=("full",))
    v = _vac(vid)
    if v["status"] != "ochiq": _bad("Nomzod faqat rektor tasdiqlagan (ochiq) vakansiyaga qo'shiladi", 409)
    name = re.sub(r"\s+", " ", b.full_name or "").strip()[:120]
    if len(name) < 5: _bad("Nomzodning F.I.Sh. kiritilmagan")
    ts = _now()
    kid = _con.execute("""INSERT INTO hr_candidates(vacancy_id,full_name,phone,education,degree,note,stage,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,'ariza',?,?,?)""",
                       (vid, name, b.phone.strip()[:40], b.education.strip()[:60], b.degree.strip()[:40] or "—", b.note.strip()[:600], c.user["id"], ts, ts)).lastrowid
    _con.commit()
    _audit(c, "nomzod qo'shildi", True, f"#{vid} · nomzod #{kid}")
    return {"ok": True, "id": kid}

class StageIn(BaseModel):
    stage: str
    note: str = ""

NEXT = {"ariza": ("suhbat", "rad"), "suhbat": ("tanlandi", "rad"), "tanlandi": ("suhbat",), "rad": ("ariza",)}

@router.post(P + "/candidates/{kid}/stage")
def api_cand_stage(kid: int, b: StageIn, request: Request):
    c = C(request, "nomzod bosqichi", f"#{kid}", need=("full",))
    k = _cand(kid)
    if b.stage not in NEXT.get(k["stage"], ()): _bad(f"«{CAND_ST.get(k['stage'])}» bosqichidan «{CAND_ST.get(b.stage, b.stage)}»ga o'tib bo'lmaydi", 409)
    if b.stage == "tanlandi" and db.one(_con, "SELECT 1 FROM hr_candidates WHERE vacancy_id=? AND id!=? AND stage IN ('tanlandi','tasdiqlandi','buyruq')", (k["vacancy_id"], kid)):
        _bad("Bu vakansiyaga boshqa nomzod allaqachon tanlangan", 409)
    if _vac(k["vacancy_id"])["status"] != "ochiq": _bad("Vakansiya ochiq emas", 409)
    _con.execute("UPDATE hr_candidates SET stage=?, stage_note=?, updated_at=? WHERE id=?", (b.stage, b.note.strip()[:300], _now(), kid)); _con.commit()
    _audit(c, f"nomzod: {CAND_ST[b.stage].lower()}", True, f"#{kid}")
    return {"ok": True, "stage": b.stage}

@router.post(P + "/candidates/{kid}/decide")
def api_cand_decide(kid: int, b: Decide, request: Request):
    c = C(request, "nomzodni tasdiqlash", f"#{kid}", need=("rektor",))
    k = _cand(kid)
    if k["stage"] != "tanlandi": _bad("Nomzod tasdiq bosqichida emas", 409)
    if b.decision not in ("approve", "reject"): _bad("Qaror noto'g'ri")
    if b.decision == "reject" and not b.note.strip(): _bad("Rad etish sababi kiritilmagan")
    st = "tasdiqlandi" if b.decision == "approve" else "rad"
    _con.execute("UPDATE hr_candidates SET stage=?, stage_note=?, updated_at=? WHERE id=?", (st, b.note.strip()[:300], _now(), kid)); _con.commit()
    _audit(c, "nomzod tasdiqlandi" if st == "tasdiqlandi" else "nomzod rad etildi", True, f"#{kid}")
    return {"ok": True, "stage": st}

class HireOrderIn(BaseModel):
    date_from: str
    contract_type: str = "muddatli"
    contract_end: str | None = None

@router.post(P + "/candidates/{kid}/order")
def api_cand_order(kid: int, b: HireOrderIn, request: Request):
    c = C(request, "ishga qabul buyrug'i", f"#{kid}", need=("full",))
    from . import orders as ORD
    with _lock:
        k = _cand(kid); v = _vac(k["vacancy_id"])
        if k["stage"] != "tasdiqlandi": _bad("Buyruq loyihasi rektor tasdiqlagan nomzod uchun tuziladi", 409)
        d0 = _d(b.date_from)
        if not d0: _bad("Ishga kirish sanasi noto'g'ri")
        if d0 < _today() - dt.timedelta(days=3): _bad("Ishga kirish sanasi o'tib ketgan")
        if b.contract_type not in CONTRACT_TYPES: _bad("Shartnoma turi noto'g'ri")
        ce = None
        if b.contract_type != "muddatsiz":
            ce = _d(b.contract_end) or _years(d0, 1) - dt.timedelta(days=1)
            if ce <= d0: _bad("Shartnoma tugash sanasi boshlanishdan keyin bo'lishi kerak")
            if ce > _years(d0, 5): _bad("Muddatli shartnoma 5 yildan oshmaydi")
        units = _units(_con)
        p = {"candidate_id": kid, "vacancy_id": v["id"], "staff_name": k["full_name"], "unit": unit_name(_con, v["unit_key"], units), "position": v["position"],
             "rate": v["rate"], "contract_type": CONTRACT_TYPES[b.contract_type], "date_from": d0.isoformat(), "date_to": ce.isoformat() if ce else None,
             "summary": f"{d0.strftime('%d.%m.%Y')}dan {unit_name(_con, v['unit_key'], units)} — {v['position']} ({v['rate']} stavka), "
                        f"{CONTRACT_TYPES[b.contract_type].lower()}" + (f" {ce.strftime('%d.%m.%Y')}gacha" if ce else "")}
        try:
            o = ORD.draft_staff_hr(_con, c, "xodim_qabul", p, f"{k['full_name']}ni ishga qabul qilish to'g'risida")
        except ValueError as e:
            _bad(str(e))
        _con.execute("UPDATE hr_candidates SET stage='buyruq', order_id=?, start_date=?, contract_type=?, contract_end=?, updated_at=? WHERE id=?",
                     (o["id"], d0.isoformat(), b.contract_type, ce.isoformat() if ce else None, _now(), kid))
        _con.commit()
    _audit(c, "ishga qabul buyrug'i loyihasi", True, f"nomzod #{kid} · buyruq #{o['id']}")
    return {"ok": True, "order": _order_brief(o["id"])}

def _it_thread(c: Ctx, subject: str, body: str) -> int:
    from . import portal as PT
    if "it" not in PT.unit_map(_con): _bad("AT bo'limi topilmadi", 500)
    return PT.create_thread(_con, c, PT.ThreadIn(subject=subject, body=body, to=["it"], kind="sorov", priority="muhim",
                                                  due=(_today() + dt.timedelta(days=2)).isoformat()))

@router.post(P + "/candidates/{kid}/it-request")
def api_cand_it(kid: int, request: Request):
    c = C(request, "AT bo'limiga akkaunt so'rovi", f"#{kid}", need=("full",))
    _sync_orders()
    k = _cand(kid); v = _vac(k["vacancy_id"])
    if k["stage"] != "qabul_qilindi": _bad("Akkaunt so'rovi ishga qabul buyrug'i imzolangach yuboriladi", 409)
    if k["it_thread_id"]: _bad("So'rov allaqachon yuborilgan", 409)
    o = _order_brief(k["order_id"]) or {}
    tid = _it_thread(c, f"Yangi xodim uchun akkaunt: {k['full_name']}",
                     f"Ishga qabul buyrug'i {o.get('reg_no', '')} asosida yangi xodim uchun ISFT Core akkaunti, korporativ pochta va kirish huquqlarini yaratishingizni so'raymiz.\n\n"
                     f"F.I.Sh.: {k['full_name']}\nBo'lim: {unit_name(_con, v['unit_key'])}\nLavozim: {v['position']}\nIshga kirish sanasi: {k['start_date'] or '—'}\n\n"
                     "Rol va ruxsatlar lavozimga mos (eng kam ruxsat tamoyili). Vaqtinchalik parolni xodimga shaxsan topshiring.")
    _con.execute("UPDATE hr_candidates SET it_thread_id=?, updated_at=? WHERE id=?", (tid, _now(), kid)); _con.commit()
    _audit(c, "AT bo'limiga akkaunt so'rovi", True, f"nomzod #{kid} · portal #{tid}")
    return {"ok": True, "thread": _thread_brief(tid)}

# ---------------------------------------------------------------------------------------------
# Ishdan bo'shatish: ariza → topshirish varaqasi → buyruq
# ---------------------------------------------------------------------------------------------
def _dis(did) -> dict:
    d = db.one(_con, "SELECT * FROM hr_dismissals WHERE id=?", (did,))
    if not d: _bad("Bo'shatish yozuvi topilmadi", 404)
    return d

def _dis_view(d: dict, units=None) -> dict:
    s = db.one(_con, f"{_FSQL} WHERE f.staff_id=?", (d["staff_id"],)) or {}
    ck = json.loads(d["checklist"] or "{}")
    acc = db.rows(_con, "SELECT id, active FROM users WHERE full_name LIKE ?", (f"%: {s.get('full_name')}",)) if s.get("full_name") else []
    return {"id": d["id"], "staff_id": d["staff_id"], "name": s.get("full_name"), "position": s.get("position"), "unit": unit_name(_con, s.get("unit_key"), units),
            "reason": d["reason"], "app_date": d["app_date"], "last_day": d["last_day"], "status": d["status"], "status_label": DIS_ST.get(d["status"], d["status"]),
            "checklist": [{"key": k, "label": lbl, "done": bool(ck.get(k))} for k, lbl in CHECK.items()], "done": sum(1 for k in CHECK if ck.get(k)),
            "order": _order_brief(d["order_id"]), "it": _thread_brief(d["it_thread_id"]), "note": d["note"],
            "accounts": [{"id": a["id"], "active": bool(a["active"] if a["active"] is not None else 1)} for a in acc]}

@router.get(P + "/dismissals")
def api_dismissals(request: Request, status: str = "open"):
    c = C(request, "bo'shatishlar", need=("full",)); _sync_orders()
    w = "d.status IN ('ariza','varaqa','buyruq')" if status == "open" else "1=1"
    units = _units(_con)
    items = [_dis_view(d, units) for d in db.rows(_con, f"SELECT d.* FROM hr_dismissals d WHERE {w} ORDER BY d.id DESC")]
    _audit(c, "bo'shatishlar", True, f"{len(items)} ta")
    return {"items": items}

class DisIn(BaseModel):
    staff_id: int
    reason: str
    app_date: str | None = None
    last_day: str

@router.post(P + "/dismissals")
def api_dis_create(b: DisIn, request: Request):
    c = C(request, "bo'shatish arizasi", f"#{b.staff_id}", need=("full",))
    f = db.one(_con, "SELECT * FROM hr_files WHERE staff_id=?", (b.staff_id,))
    if not f: _bad("Xodim topilmadi")
    if f["status"] != "faol": _bad("Xodim allaqachon bo'shatilgan", 409)
    if db.one(_con, "SELECT 1 FROM hr_dismissals WHERE staff_id=? AND status IN ('ariza','varaqa','buyruq')", (b.staff_id,)): _bad("Bu xodim bo'yicha jarayon allaqachon ochiq", 409)
    reason = (b.reason or "").strip()[:300]
    if not reason: _bad("Bo'shatish asosi kiritilmagan")
    ld = _d(b.last_day); ad = _d(b.app_date) or _today()
    if not ld: _bad("Oxirgi ish kuni noto'g'ri")
    if ld < ad: _bad("Oxirgi ish kuni arizadan oldin bo'lishi mumkin emas")
    if ad > _today(): _bad("Ariza sanasi kelajakda bo'lishi mumkin emas")
    ts = _now()
    did = _con.execute("""INSERT INTO hr_dismissals(staff_id,reason,app_date,last_day,status,checklist,created_by,created_by_name,created_at,updated_at)
                          VALUES(?,?,?,?,'varaqa',?,?,?,?,?)""", (b.staff_id, reason, ad.isoformat(), ld.isoformat(), json.dumps({k: False for k in CHECK}),
                                                              c.user["id"], c.user["full_name"], ts, ts)).lastrowid
    _con.commit()
    _audit(c, "bo'shatish arizasi qayd etildi", True, f"#{did} · xodim #{b.staff_id} · {ld}")
    return {"ok": True, "id": did}

class CheckIn(BaseModel):
    item: str
    done: bool = True

@router.post(P + "/dismissals/{did}/check")
def api_dis_check(did: int, b: CheckIn, request: Request):
    c = C(request, "topshirish varaqasi", f"#{did}", need=("full",))
    d = _dis(did)
    if d["status"] not in ("ariza", "varaqa"): _bad("Varaqa faqat buyruqqacha o'zgaradi", 409)
    if b.item not in CHECK: _bad("Band noto'g'ri")
    ck = json.loads(d["checklist"] or "{}"); ck[b.item] = bool(b.done)
    _con.execute("UPDATE hr_dismissals SET checklist=?, status='varaqa', updated_at=? WHERE id=?", (json.dumps(ck), _now(), did)); _con.commit()
    _audit(c, "topshirish varaqasi", True, f"#{did} · {b.item}={'ha' if b.done else 'yo`q'}")
    return {"ok": True, "done": sum(1 for k in CHECK if ck.get(k)), "total": len(CHECK)}

@router.post(P + "/dismissals/{did}/it-request")
def api_dis_it(did: int, request: Request):
    c = C(request, "AT bo'limiga bloklash so'rovi", f"#{did}", need=("full",))
    d = _dis(did)
    if d["status"] not in ("ariza", "varaqa", "buyruq"): _bad("Jarayon yopilgan", 409)
    if d["it_thread_id"]: _bad("So'rov allaqachon yuborilgan", 409)
    v = _dis_view(d)
    tid = _it_thread(c, f"Ishdan bo'shayotgan xodim akkauntlarini bloklash: {v['name']}",
                     f"Xodim {v['name']} ({v['unit']}, {v['position']}) {dt.date.fromisoformat(d['last_day']).strftime('%d.%m.%Y')} oxirgi ish kuni bilan ishdan bo'shamoqda.\n\n"
                     "Shu kuni ish kuni tugagach ISFT Core akkaunti, korporativ pochta, Wi-Fi va boshqa tizimlardagi kirish huquqlarini bloklashingizni, "
                     "bajarilgach shu xatga javob berishingizni so'raymiz.")
    _con.execute("UPDATE hr_dismissals SET it_thread_id=?, updated_at=? WHERE id=?", (tid, _now(), did)); _con.commit()
    _audit(c, "AT bo'limiga bloklash so'rovi", True, f"#{did} · portal #{tid}")
    return {"ok": True, "thread": _thread_brief(tid)}

@router.post(P + "/dismissals/{did}/order")
def api_dis_order(did: int, request: Request):
    c = C(request, "bo'shatish buyrug'i", f"#{did}", need=("full",))
    from . import orders as ORD
    with _lock:
        d = _dis(did)
        if d["status"] not in ("ariza", "varaqa"): _bad("Buyruq allaqachon tuzilgan yoki jarayon yopilgan", 409)
        ck = json.loads(d["checklist"] or "{}")
        miss = [CHECK[k] for k in CHECK if not ck.get(k)]
        if miss: _bad("Topshirish varaqasi to'liq emas: " + "; ".join(miss), 409)
        v = _dis_view(d)
        ld = dt.date.fromisoformat(d["last_day"])
        p = {"staff_id": d["staff_id"], "dismissal_id": did, "staff_name": v["name"], "unit": v["unit"], "position": v["position"], "date_from": d["last_day"],
             "reason": d["reason"], "summary": f"{ld.strftime('%d.%m.%Y')}dan lavozimidan ozod qilish · asos: {d['reason']}"}
        try:
            o = ORD.draft_staff_hr(_con, c, "xodim_boshatish", p, f"{v['name']}ni ishdan bo'shatish to'g'risida")
        except ValueError as e:
            _bad(str(e))
        _con.execute("UPDATE hr_dismissals SET status='buyruq', order_id=?, updated_at=? WHERE id=?", (o["id"], _now(), did)); _con.commit()
    _audit(c, "bo'shatish buyrug'i loyihasi", True, f"#{did} · buyruq #{o['id']}")
    return {"ok": True, "order": _order_brief(o["id"])}

@router.post(P + "/dismissals/{did}/cancel")
def api_dis_cancel(did: int, request: Request):
    c = C(request, "bo'shatishni bekor qilish", f"#{did}", need=("full",))
    d = _dis(did)
    if d["status"] not in ("ariza", "varaqa"): _bad("Buyruq tuzilgan — avval «Buyruqlar»da loyihani o'chiring", 409)
    _con.execute("UPDATE hr_dismissals SET status='bekor', updated_at=? WHERE id=?", (_now(), did)); _con.commit()
    _audit(c, "bo'shatish bekor qilindi (ariza qaytarib olindi)", True, f"#{did}")
    return {"ok": True}
