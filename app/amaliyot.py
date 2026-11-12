"""«Amaliyot» — talabalar amaliyoti (docs/amaliyot.md).

1. Amaliyot bazalari reyestri: tashkilot, hamkorlik shartnomasi (raqam, sana, amal qilish muddati), yo'nalishlar bo'yicha sig'im.
2. Amaliyot davrlari: guruh bo'yicha — o'quv rejasidan (curriculum: «Malakaviy amaliyot», «…pedagogik amaliyot») yoki alohida jadval bilan.
3. Biriktirish: guruh bo'yicha ommaviy, sig'im va shartnoma muddati tekshiruvi; kafedradan amaliyot rahbari (teachers) va tashkilotdan
   rahbar; yo'llanma — Hujjatlar markazidagi «Amaliyot yo'llanmasi» shabloni (documents.issue, kalit «practice»).
4. Kuzatuv: biriktirildi → boshlandi → kundalik → hisobot topshirildi → baholandi (yoki qaytarildi). Bahoni FAQAT kafedra rahbari
   (biriktirilgan o'qituvchi yoki kafedra mudiri) qo'yadi. Ogohlantirishlar: hisobot muddati o'tgan, boshlanmagan, baholanmagan,
   shartnoma muddati tugayotgan / tugagan baza.
5. Statistika: baza va guruh bo'yicha.
Talaba o'z amaliyotini /talaba kabinetida ko'radi, kundalik yozadi va hisobot topshiradi (/api/talaba/amaliyot).
Ruxsat — moduldagi jadval (mode/guard), har bir murojaat rbac.audit(resource="practice").
"""
import datetime as dt, random, re, threading
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
RES = rbac.PRACTICE

RULES = {
    "start_grace_days": 3,      # amaliyot boshlanganidan 3 kun o'tib ham «boshlandi» belgilanmasa — ogohlantirish
    "report_after_days": 7,     # hisobot topshirish muddati (standart): amaliyot tugaganidan keyin 7 kun
    "grade_days": 7,            # topshirilgan hisobot 7 kun ichida baholanishi kerak
    "agreement_warn_days": 30,  # shartnoma muddati tugashiga 30 kundan kam qolsa — ogohlantirish
    "report_min_chars": 200,    # talaba hisobotining qisqa mazmuni
}
KINDS = {"oquv": "O'quv-tanishuv amaliyoti", "ishlab": "Ishlab chiqarish amaliyoti", "pedagogik": "Pedagogik amaliyot",
         "malakaviy": "Malakaviy (bitiruvoldi) amaliyot", "ilmiy": "Ilmiy-pedagogik amaliyot"}
ST = {"biriktirildi": "Biriktirildi", "boshlandi": "Amaliyotda", "hisobot": "Hisobot topshirildi", "baholandi": "Baholandi",
      "qaytarildi": "Hisobot qaytarildi"}
OPEN_ST = ("biriktirildi", "boshlandi", "qaytarildi")      # hisobot hali yo'q
BASE_KINDS = {"davlat": "Davlat tashkiloti", "xususiy": "Xususiy korxona", "bank": "Bank / moliya", "talim": "Ta'lim muassasasi",
              "it": "IT kompaniya", "xalqaro": "Xalqaro tashkilot"}
# o'quv rejasidagi joy bilan bog'liq amaliyot fanlari (semestr davomidagi «Nutq amaliyoti» kabi auditoriya fanlari emas)
CURR_RX = re.compile(r"malakaviy amaliyot|pedagogik amaliyot", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS prac_bases(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT, address TEXT, contact_name TEXT, contact_phone TEXT,
  agreement_no TEXT, agreement_date TEXT, agreement_expires TEXT, status TEXT DEFAULT 'faol', note TEXT, created_by INT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS prac_base_caps(base_id INT, direction TEXT, capacity INT, PRIMARY KEY(base_id, direction));
CREATE TABLE IF NOT EXISTS prac_periods(id INTEGER PRIMARY KEY, title TEXT, kind TEXT, group_id INT, course INT, sem_no INT, start TEXT, end TEXT,
  report_due TEXT, credits INT, source TEXT, created_by INT, created_at TEXT, UNIQUE(group_id, kind, start));
CREATE INDEX IF NOT EXISTS ix_pp_group ON prac_periods(group_id);
CREATE TABLE IF NOT EXISTS prac_assign(id INTEGER PRIMARY KEY, period_id INT NOT NULL, student_id INT NOT NULL, base_id INT, kaf_supervisor_id INT,
  org_supervisor TEXT, org_phone TEXT, status TEXT DEFAULT 'biriktirildi', started_at TEXT, doc_reg TEXT, doc_file TEXT,
  report_text TEXT, report_at TEXT, report_by TEXT, return_note TEXT, score INT, grade_note TEXT, graded_by INT, graded_name TEXT, graded_at TEXT,
  assigned_by INT, assigned_at TEXT, UNIQUE(period_id, student_id));
CREATE INDEX IF NOT EXISTS ix_pa_period ON prac_assign(period_id);
CREATE INDEX IF NOT EXISTS ix_pa_student ON prac_assign(student_id);
CREATE INDEX IF NOT EXISTS ix_pa_base ON prac_assign(base_id);
CREATE TABLE IF NOT EXISTS prac_diary(id INTEGER PRIMARY KEY, assign_id INT NOT NULL, day TEXT, text TEXT, author TEXT, author_kind TEXT, at TEXT);
CREATE INDEX IF NOT EXISTS ix_pd_assign ON prac_diary(assign_id);
"""

def _today(): return clock.today()
def _now(): return clock.now_iso()
def _bad(msg, code=400): raise HTTPException(code, msg)
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _dmy(v) -> str:
    v = str(v or "")[:10]
    return f"{v[8:10]}.{v[5:7]}.{v[:4]}" if len(v) == 10 else v

def _date(v, label="Sana"):
    try: return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except (TypeError, ValueError): _bad(f"{label} noto'g'ri: {v}")
def _d(s): return dt.date.fromisoformat(s[:10])

# =============================================================================================
# Ruxsat va ko'lam
# =============================================================================================
FULL = ("amaliyot",)
REG = ("talabalar", "registrator_xodim", "sirtqi")
LEAD = ("rektor", "prorektor_oquv")
MODE_NOTE = {"full": "Amaliyot bo'limi: bazalar, davrlar, biriktirish, yo'llanmalar va kuzatuv",
             "kafedra": "O'z kafedrasi guruhlari: amaliyot rahbarlari, hisobotlarni qabul qilish va baholash",
             "oqituvchi": "Siz rahbarlik qilayotgan talabalar: kundalik, hisobot va baho",
             "tyutor": "O'z guruhlaringiz amaliyoti (faqat ko'rish)",
             "reg": "Talabalar amaliyoti (faqat ko'rish)",
             "lead": "Jamlangan ko'rsatkichlar: bazalar, qamrov, hisobot va baholar (ism-shariflarsiz)"}

def mode(c: Ctx):
    k = c.role.key
    if k in FULL: return "full"
    if k in REG: return "reg"
    if k in LEAD: return "lead"
    return {"kafedra": "kafedra", "oqituvchi": "oqituvchi", "tyutor": "tyutor"}.get(k)

def guard(c: Ctx, action: str, detail: str = "", modes=None) -> str:
    m = mode(c)
    ok = m is not None and (modes is None or m in modes)
    rbac.audit(_con, c, f"amaliyot: {action}", RES, ok, detail)
    if not ok:
        why = "bu amal lavozimingiz uchun emas" if m else f"«{c.role.title}» lavozimi uchun ruxsat yo'q"
        raise AccessDenied(f"⛔ Amaliyot: {why}. So'rov audit jurnaliga yozildi.")
    return m

def g_scope(c: Ctx, alias="g") -> str:
    """Guruhlar ko'lami."""
    m, u = mode(c), c.user
    if m == "kafedra": return f"{alias}.department_id={int(u['department_id'] or 0)}"
    if m == "oqituvchi":
        return f"{alias}.id IN (SELECT pp.group_id FROM prac_periods pp JOIN prac_assign pa ON pa.period_id=pp.id WHERE pa.kaf_supervisor_id={int(u['teacher_id'] or 0)})"
    if m == "tyutor": return f"{alias}.id IN (SELECT group_id FROM tutor_groups WHERE user_id={int(u['id'])})"
    if m == "reg" and c.role.key == "sirtqi": return f"{alias}.form='sirtqi'"
    return "1=1"

def a_scope(c: Ctx, a="a", g="g") -> str:
    """Biriktirishlar (talabalar) ko'lami."""
    if mode(c) == "oqituvchi": return f"{a}.kaf_supervisor_id={int(c.user['teacher_id'] or 0)}"
    return g_scope(c, g)

def _names(c: Ctx) -> bool:
    return mode(c) != "lead"

def _assign_row(c: Ctx, aid: int) -> dict:
    r = db.one(_con, f"""SELECT a.*, p.title, p.kind, p.start, p.end, p.report_due, p.group_id, g.department_id, g.name grp, s.full_name, s.hemis_id
        FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN groups_ g ON g.id=p.group_id JOIN students s ON s.id=a.student_id
        WHERE a.id=? AND {a_scope(c)}""", (int(aid),))
    if not r: raise AccessDenied("⛔ Amaliyot: bu talaba sizning ko'lamingizda emas yoki topilmadi. So'rov audit jurnaliga yozildi.")
    return r

def _period_row(c: Ctx, pid: int) -> dict:
    r = db.one(_con, f"""SELECT p.*, g.name grp, g.direction, g.level, g.form, g.department_id, d.name dept FROM prac_periods p JOIN groups_ g ON g.id=p.group_id
        LEFT JOIN departments d ON d.id=g.department_id WHERE p.id=? AND {g_scope(c)}""", (int(pid),))
    if not r: raise AccessDenied("⛔ Amaliyot: bu davr sizning ko'lamingizda emas yoki topilmadi. So'rov audit jurnaliga yozildi.")
    return r

def can_grade(c: Ctx, a: dict) -> bool:
    m = mode(c)
    if m == "oqituvchi": return a["kaf_supervisor_id"] == c.user.get("teacher_id")
    if m == "kafedra": return a["department_id"] == c.user.get("department_id")
    return False

# =============================================================================================
# Hisob-kitob
# =============================================================================================
def used(base_id: int, direction: str, start: str, end: str, exclude_period: int = 0) -> int:
    """Shu bazada shu yo'nalish bo'yicha bir vaqtda (davrlar kesishgan) amaliyotdagi talabalar soni."""
    return db.one(_con, """SELECT COUNT(*) n FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN groups_ g ON g.id=p.group_id
        WHERE a.base_id=? AND g.direction=? AND p.start<=? AND p.end>=? AND p.id!=?""", (base_id, direction, end, start, exclude_period))["n"]

def capacity(base_id: int, direction: str) -> int:
    r = db.one(_con, "SELECT capacity FROM prac_base_caps WHERE base_id=? AND direction=?", (base_id, direction))
    return int(r["capacity"]) if r else 0

def agreement_state(b: dict, today=None) -> str:
    today = (today or _today()).isoformat()
    if b.get("status") != "faol": return "to'xtatilgan"
    exp = b.get("agreement_expires") or ""
    if not exp: return "shartnomasiz"
    if exp < today: return "muddati o'tgan"
    if exp <= (_today() + dt.timedelta(days=RULES["agreement_warn_days"])).isoformat(): return "tugayapti"
    return "amalda"

def flags(a: dict, today: str) -> list:
    """Biriktirish bo'yicha ogohlantirishlar (kalitlar)."""
    out = []
    if a["status"] in OPEN_ST and a.get("report_due") and today > a["report_due"]: out.append("hisobot_kechikdi")
    if a["status"] == "biriktirildi" and a.get("start") and today > (_d(a["start"]) + dt.timedelta(days=RULES["start_grace_days"])).isoformat():
        out.append("boshlanmagan")
    if a["status"] == "hisobot" and a.get("report_at") and today > (_d(a["report_at"]) + dt.timedelta(days=RULES["grade_days"])).isoformat():
        out.append("baholanmagan")
    if not a.get("base_id"): out.append("bazasiz")
    return out

FLAG_TITLES = {"hisobot_kechikdi": "Hisobot muddati o'tgan", "boshlanmagan": "Amaliyotga chiqmagan", "baholanmagan": "Baholanmagan (7 kundan ortiq)",
               "bazasiz": "Baza biriktirilmagan"}

def period_status(p: dict, today: str) -> str:
    if today < p["start"]: return "kutilmoqda"
    if today <= p["end"]: return "davom etmoqda"
    if today <= (p["report_due"] or p["end"]): return "hisobot topshirish"
    return "yakunlangan"

# =============================================================================================
# Demo ma'lumot (jadvallar bo'sh bo'lsa) — tashkilotlar shartli (sintetik), talabalar va o'qituvchilar bazadagi mavjud yozuvlar
# =============================================================================================
BASES = [  # name, kind, address, [directions], cap, expires
    ("«Ipak yo'li» tijorat banki Chilonzor filiali (shartli)", "bank", "Toshkent sh., Chilonzor t.",
     ["Bank ishi va audit", "Buxgalteriya hisobi va moliya", "Iqtisodiyot", "Moliya sohasida boshqaruv"], 12, "2028-06-30"),
    ("«Hamkor Audit» MChJ (shartli)", "xususiy", "Toshkent sh., Yunusobod t.", ["Buxgalteriya hisobi va moliya", "Bank ishi va audit"], 8, "2027-12-31"),
    ("Toshkent shahar Moliya boshqarmasi (shartli)", "davlat", "Toshkent sh., Mirobod t.",
     ["Moliya sohasida boshqaruv", "Iqtisodiyot", "Buxgalteriya hisobi va moliya"], 10, "2026-11-30"),
    ("«Raqamli yechimlar» IT-park rezidenti (shartli)", "it", "Toshkent sh., Mirzo Ulug'bek t.",
     ["Axborot tizimlari va texnologiyalari", "Axborot xavfsizligi"], 15, "2027-09-01"),
    ("«Savdo-Servis» savdo kompaniyasi (shartli)", "xususiy", "Toshkent sh., Sergeli t.", ["Marketing", "Menejment", "Biznes va menejment", "Iqtisodiyot"], 14, "2027-08-31"),
    ("«Mehnat va bandlik markazi» (shartli)", "davlat", "Toshkent sh., Shayxontohur t.", ["Iqtisodiyot", "Menejment", "Psixologiya (faoliyat turlari bo'yicha)"], 10, "2028-01-31"),
    ("Toshkent sh. 112-umumta'lim maktabi (shartli)", "talim", "Toshkent sh., Yakkasaroy t.",
     ["Boshlang'ich ta'lim", "Pedagogika", "Pedagogika va psixologiya", "Filologiya va tillarni o'qitish (ingliz tili)", "Xorijiy til va adabiyoti"], 20, "2027-06-30"),
    ("Toshkent sh. 47-umumta'lim maktabi (shartli)", "talim", "Toshkent sh., Olmazor t.",
     ["Boshlang'ich ta'lim", "Pedagogika", "Xorijiy til va adabiyoti", "Psixologiya (faoliyat turlari bo'yicha)"], 18, "2027-06-30"),
    ("«Quyoshcha» 215-davlat maktabgacha ta'lim tashkiloti (shartli)", "talim", "Toshkent sh., Chilonzor t.", ["Maktabgacha ta'lim", "Pedagogika va psixologiya"], 15, "2027-05-31"),
    ("«Bolajon» 38-maktabgacha ta'lim tashkiloti (shartli)", "talim", "Toshkent sh., Uchtepa t.", ["Maktabgacha ta'lim"], 12, "2026-09-30"),
    ("«Global Link» tarjima va konsalting markazi (shartli)", "xalqaro", "Toshkent sh., Mirobod t.",
     ["Xalqaro munosabatlar", "Filologiya va tillarni o'qitish (ingliz tili)", "Xorijiy til va adabiyoti"], 8, "2027-10-15"),
    ("«Agro Eksport» aksiyadorlik jamiyati (shartli)", "xususiy", "Toshkent viloyati, Zangiota t.",
     ["Iqtisodiyot", "Menejment", "Marketing", "Buxgalteriya hisobi va moliya", "Biznes va menejment"], 16, "2028-03-01"),
    ("«Kiber Qalqon» axborot xavfsizligi markazi (shartli)", "it", "Toshkent sh., Yashnobod t.", ["Axborot xavfsizligi", "Axborot tizimlari va texnologiyalari"], 6, "2027-12-31"),
]
ORG_PEOPLE = ["Rahimov Botir", "Sobirova Dilnoza", "Qodirov Anvar", "Tursunova Malika", "Ismoilov Jahongir", "Nazarova Gulnoza", "Ergashev Sardor",
              "Yo'ldosheva Nilufar", "Xolmatov Sanjar", "Abdullayeva Kamola"]
DIARY_TXT = ["Tashkilot tuzilmasi va ichki tartib qoidalari bilan tanishdim.", "Bo'lim hujjatlari bilan ishlash tartibini o'rgandim.",
             "Rahbar topshirig'i bo'yicha hisobot jadvalini tayyorladim.", "Mijozlar bilan ishlash jarayonini kuzatdim.",
             "Amaliy topshiriq: ma'lumotlarni tahlil qilib, xulosa yozdim.", "Haftalik yig'ilishda qatnashdim, vazifalar taqsimlandi.",
             "Darsni kuzatdim va dars tahlilini yozdim.", "Mustaqil ravishda bitta mashg'ulot o'tkazdim (rahbar kuzatuvida)."]

def _seed(con):
    if db.one(con, "SELECT COUNT(*) n FROM prac_bases")["n"]: return
    rnd = random.Random(2026)
    now, today = _now(), _today()
    author = db.one(con, "SELECT id FROM users WHERE role='amaliyot' ORDER BY id LIMIT 1")
    au = author["id"] if author else None
    bids = {}
    for i, (name, kind, addr, dirs, cap, exp) in enumerate(BASES, 1):
        signed = (dt.date.fromisoformat(exp) - dt.timedelta(days=365 * 3)).isoformat()
        cur = con.execute("""INSERT INTO prac_bases(name,kind,address,contact_name,contact_phone,agreement_no,agreement_date,agreement_expires,status,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (name, kind, addr, ORG_PEOPLE[i % len(ORG_PEOPLE)], f"+998 71 2{i:02d} {rnd.randint(10, 99)} {rnd.randint(10, 99)}",
                                                  f"AM-{signed[:4]}/{i:03d}", signed, exp, "faol", au, now, now))
        bids[name] = cur.lastrowid
        for d_ in dirs: con.execute("INSERT OR IGNORE INTO prac_base_caps VALUES(?,?,?)", (cur.lastrowid, d_, cap + cap // 2))
    # davrlar: guruhlar (kunduzgi bakalavr)
    def groups(course, direction, n):
        return db.rows(con, """SELECT g.* FROM groups_ g WHERE g.course=? AND g.direction=? AND g.form='kunduzgi' AND g.level='bakalavr'
            AND EXISTS(SELECT 1 FROM students s WHERE s.group_id=g.id AND s.status='faol') ORDER BY g.name LIMIT ?""", (course, direction, n))
    t109 = db.one(con, "SELECT teacher_id FROM users WHERE role='oqituvchi' AND teacher_id IS NOT NULL ORDER BY id LIMIT 1")
    t109 = t109["teacher_id"] if t109 else None
    t109_groups = {r["group_id"] for r in db.rows(con, "SELECT group_id FROM teacher_groups WHERE teacher_id=?", (t109,))} if t109 else set()
    def own(course):   # demo o'qituvchisi dars beradigan shu kursdagi guruh — u rahbar bo'ladi
        return db.rows(con, f"SELECT g.* FROM groups_ g WHERE g.course=? AND g.form='kunduzgi' AND g.id IN ({','.join(map(str, t109_groups)) or 0}) LIMIT 1", (course,))
    plan = [  # kind, title, start, end, due, course, [(direction, n)], scenario
        ("ishlab", KINDS["ishlab"], "2026-10-19", "2026-11-28", "2026-12-05", 4,
         [("Iqtisodiyot", 2), ("Bank ishi va audit", 1), ("Axborot tizimlari va texnologiyalari", 1)], "davom"),
        ("oquv", KINDS["oquv"], "2026-09-28", "2026-10-24", "2026-10-31", 3, [("Iqtisodiyot", 2), ("Marketing", 1)], "yakun"),
        ("pedagogik", KINDS["pedagogik"], "2026-10-12", "2026-11-07", "2026-11-14", 3, [("Boshlang'ich ta'lim", 2), ("Maktabgacha ta'lim", 1)], "hisobot"),
    ]
    for kind, title, start, end, due, course, spec, scen in plan:
        gs = own(course) if kind != "pedagogik" else []
        for direction, n in spec: gs += groups(course, direction, n)
        seen = set()
        for g in gs:
            if g["id"] in seen: continue
            seen.add(g["id"])
            cur = con.execute("""INSERT OR IGNORE INTO prac_periods(title,kind,group_id,course,sem_no,start,end,report_due,credits,source,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (title, kind, g["id"], course, AR.sem_no(course, AR.CURRENT_SEMESTER), start, end, due, 6, "jadval", au, now))
            pid = cur.lastrowid
            dir_bases = [r["base_id"] for r in db.rows(con, "SELECT base_id FROM prac_base_caps WHERE direction=? ORDER BY base_id", (g["direction"],))
                         if db.one(con, "SELECT agreement_expires e FROM prac_bases WHERE id=?", (r["base_id"],))["e"] >= end]
            sup = t109 if g["id"] in t109_groups and t109 else None
            if not sup:
                t = db.one(con, "SELECT tg.teacher_id FROM teacher_groups tg JOIN teachers t ON t.id=tg.teacher_id WHERE tg.group_id=? AND t.department_id=? ORDER BY tg.teacher_id LIMIT 1",
                           (g["id"], g["department_id"])) or db.one(con, "SELECT id teacher_id FROM teachers WHERE department_id=? ORDER BY id LIMIT 1", (g["department_id"],))
                sup = t["teacher_id"] if t else None
            studs = db.rows(con, "SELECT id, full_name FROM students WHERE group_id=? AND status='faol' ORDER BY full_name", (g["id"],))
            for j, s in enumerate(studs):
                base = None
                for k in range(len(dir_bases)):
                    b = dir_bases[(j + k) % len(dir_bases)]
                    if used(b, g["direction"], start, end) < capacity(b, g["direction"]): base = b; break
                if base is None: continue   # sig'im tugadi — talaba «biriktirilmagan» bo'lib qoladi (Amaliyot bo'limi ishi)
                x = rnd.random()
                st, rep, rep_at, score, gby, gat, started = "biriktirildi", None, None, None, None, None, None
                if scen == "davom":
                    if x > 0.08: st, started = "boshlandi", start
                elif scen == "yakun":
                    started = start
                    if x < 0.68: st = "baholandi"
                    elif x < 0.85: st = "hisobot"
                    else: st = "boshlandi"
                else:
                    started = start
                    if x < 0.30: st = "baholandi"
                    elif x < 0.65: st = "hisobot"
                    else: st = "boshlandi"
                if st in ("hisobot", "baholandi"):
                    rep_at = (_d(end) + dt.timedelta(days=rnd.randint(0, 6))).isoformat() + "T1" + str(rnd.randint(0, 7)) + ":00:00"
                    if st == "hisobot" and scen == "yakun": rep_at = (_d(due) - dt.timedelta(days=rnd.randint(0, 2))).isoformat() + "T12:00:00"
                    rep = (f"{title} davomida {s['full_name'].split()[0]} tashkilotning asosiy faoliyati bilan tanishdi, rahbar topshiriqlarini bajardi va "
                           "kundalik yuritdi. Hisobotda tashkilot tuzilmasi, bajarilgan ishlar, olingan ko'nikmalar va takliflar bayon etilgan. "
                           "Tashkilot rahbarining tavsifnomasi va kundalik ilova qilingan.")
                if st == "baholandi":
                    score = max(35, min(98, int(rnd.gauss(76, 11))))
                    gby, gat = sup, (_d(rep_at) + dt.timedelta(days=rnd.randint(1, 5))).isoformat() + "T15:00:00"
                tn = db.one(con, "SELECT full_name FROM teachers WHERE id=?", (sup,)) if sup else None
                cur2 = con.execute("""INSERT OR IGNORE INTO prac_assign(period_id,student_id,base_id,kaf_supervisor_id,org_supervisor,org_phone,status,started_at,
                    doc_reg,report_text,report_at,report_by,score,grade_note,graded_by,graded_name,graded_at,assigned_by,assigned_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, s["id"], base, sup, ORG_PEOPLE[(base + j) % len(ORG_PEOPLE)], f"+998 90 {rnd.randint(100, 999)} {rnd.randint(10, 99)} {rnd.randint(10, 99)}", st, started,
                     None, rep, rep_at, "talaba" if rep else None, score, "Tavsifnoma ijobiy" if score and score >= 65 else None,
                     None, (tn["full_name"] if tn else None) if score else None, gat, au, (_d(start) - dt.timedelta(days=10)).isoformat() + "T10:00:00"))
                aid = cur2.lastrowid
                if started and aid:
                    last = min(_d(end), today)
                    day, k = _d(start), 0
                    while day <= last and k < 6:
                        con.execute("INSERT INTO prac_diary(assign_id,day,text,author,author_kind,at) VALUES(?,?,?,?,?,?)",
                                    (aid, day.isoformat(), DIARY_TXT[(j + k) % len(DIARY_TXT)], s["full_name"], "talaba", day.isoformat() + "T18:00:00"))
                        day += dt.timedelta(days=rnd.choice((3, 4, 5))); k += 1
    con.commit()

def init(con):
    global _con
    _con = _con or con   # used()/capacity() demo ma'lumotida ham ishlatiladi
    con.executescript(SCHEMA)
    con.commit()
    try: _seed(con)
    except Exception as e: print("amaliyot demo ma'lumoti:", type(e).__name__, e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

# =============================================================================================
# O'qish
# =============================================================================================
def kpis(c: Ctx) -> dict:
    sc, today = a_scope(c), _today().isoformat()
    rows = db.rows(_con, f"""SELECT a.status, a.base_id, a.report_at, p.start, p.end, p.report_due FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id
        JOIN groups_ g ON g.id=p.group_id WHERE {sc}""")
    k = {"jami": len(rows), "amaliyotda": 0, "hisobot": 0, "baholandi": 0, "kechikkan": 0, "boshlanmagan": 0, "baholanmagan": 0}
    for r in rows:
        if r["status"] == "boshlandi" and r["start"] <= today <= r["end"]: k["amaliyotda"] += 1
        if r["status"] == "hisobot": k["hisobot"] += 1
        if r["status"] == "baholandi": k["baholandi"] += 1
        f = flags(r, today)
        if "hisobot_kechikdi" in f: k["kechikkan"] += 1
        if "boshlanmagan" in f: k["boshlanmagan"] += 1
        if "baholanmagan" in f: k["baholanmagan"] += 1
    if mode(c) in ("full", "lead", "reg"):
        bs = db.rows(_con, "SELECT * FROM prac_bases")
        k["bazalar"] = sum(1 for b in bs if agreement_state(b) in ("amalda", "tugayapti"))
        k["shartnoma_tugayapti"] = sum(1 for b in bs if agreement_state(b) in ("tugayapti", "muddati o'tgan"))
    return k

def meta(c: Ctx) -> dict:
    m = mode(c)
    dirs = [r["direction"] for r in db.rows(_con, "SELECT DISTINCT direction FROM groups_ ORDER BY direction")]
    return {"mode": m, "mode_note": MODE_NOTE[m], "role": c.role.key, "today": _today().isoformat(), "rules": RULES, "kinds": KINDS, "statuses": ST,
            "base_kinds": BASE_KINDS, "flag_titles": FLAG_TITLES, "directions": dirs, "kpi": kpis(c),
            "scope": c.scope_label(_con) if m in ("kafedra",) else ("Sirtqi ta'lim talabalari" if c.role.key == "sirtqi" else
                     "O'z guruhlari" if m == "tyutor" else "Rahbarlik qilayotgan talabalar" if m == "oqituvchi" else "Butun institut"),
            "caps": {"edit": m == "full", "grade": m in ("kafedra", "oqituvchi"), "review": m in ("full", "kafedra", "oqituvchi"),
                     "supervisor": m in ("full", "kafedra"), "names": m != "lead", "bases": m in ("full", "lead", "reg", "kafedra")},
            "tabs": [t for t in (["davrlar", "ogohlantirish", "bazalar", "statistika"] if m in ("full", "kafedra", "reg") else
                                 ["davrlar", "ogohlantirish"] if m in ("oqituvchi", "tyutor") else ["statistika", "bazalar"])]}

def list_bases(c: Ctx, q: str = "") -> list:
    w, a = ["1=1"], []
    if q: w.append("(b.name LIKE ? OR b.agreement_no LIKE ?)"); a += [f"%{q}%", f"%{q}%"]
    out, today = [], _today().isoformat()
    for b in db.rows(_con, f"SELECT b.* FROM prac_bases b WHERE {' AND '.join(w)} ORDER BY b.name", a):
        caps = db.rows(_con, "SELECT direction, capacity FROM prac_base_caps WHERE base_id=? ORDER BY direction", (b["id"],))
        for cp in caps:
            cp["now"] = db.one(_con, """SELECT COUNT(*) n FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN groups_ g ON g.id=p.group_id
                WHERE a.base_id=? AND g.direction=? AND p.end>=?""", (b["id"], cp["direction"], today))["n"]
        b["caps"] = caps
        b["agreement_state"] = agreement_state(b)
        b["students_total"] = db.one(_con, "SELECT COUNT(*) n FROM prac_assign WHERE base_id=?", (b["id"],))["n"]
        out.append(b)
    return out

def list_periods(c: Ctx, status: str = "", q: str = "") -> list:
    today = _today().isoformat()
    w, a = [g_scope(c)], []
    if q: w.append("(g.name LIKE ? OR p.title LIKE ? OR g.direction LIKE ?)"); a += [f"%{q}%"] * 3
    ps = db.rows(_con, f"""SELECT p.*, g.name grp, g.direction, g.form, g.department_id, d.name dept,
        (SELECT COUNT(*) FROM students s WHERE s.group_id=g.id AND s.status='faol') group_size
        FROM prac_periods p JOIN groups_ g ON g.id=p.group_id LEFT JOIN departments d ON d.id=g.department_id WHERE {' AND '.join(w)} ORDER BY p.start DESC, g.name""", a)
    out = []
    for p in ps:
        p["state"] = period_status(p, today)
        if status and p["state"] != status: continue
        ar = db.rows(_con, f"""SELECT a.*, p.start, p.end, p.report_due FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN groups_ g ON g.id=p.group_id
            WHERE a.period_id=? AND {a_scope(c)}""", (p["id"],))
        cnt = {k: 0 for k in ST}
        fl = 0
        for r in ar:
            cnt[r["status"]] = cnt.get(r["status"], 0) + 1
            if flags(r, today): fl += 1
        p["counts"], p["assigned"], p["alerts"] = cnt, len(ar), fl
        p["unassigned"] = max(0, p["group_size"] - len(ar)) if mode(c) != "oqituvchi" else 0
        sc = [r["score"] for r in ar if r["score"] is not None]
        p["avg_score"] = round(sum(sc) / len(sc), 1) if sc else None
        out.append(p)
    return out

def period_detail(c: Ctx, pid: int) -> dict:
    p = _period_row(c, pid)
    today = _today().isoformat()
    p["state"] = period_status(p, today)
    names = _names(c)
    rows = db.rows(_con, f"""SELECT a.*, s.full_name, s.hemis_id, b.name base, t.full_name kaf_supervisor, p.start, p.end, p.report_due,
        (SELECT COUNT(*) FROM prac_diary d WHERE d.assign_id=a.id) diary_n
        FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN groups_ g ON g.id=p.group_id JOIN students s ON s.id=a.student_id
        LEFT JOIN prac_bases b ON b.id=a.base_id LEFT JOIN teachers t ON t.id=a.kaf_supervisor_id
        WHERE a.period_id=? AND {a_scope(c)} ORDER BY s.full_name""", (pid,))
    for r in rows:
        r["flags"] = flags(r, today)
        r["can_grade"] = can_grade(c, {**r, "department_id": p["department_id"]})
        r.pop("report_text", None)
        if not names: r["full_name"], r["hemis_id"] = "—", ""
    unassigned = []
    if mode(c) in ("full", "kafedra", "reg"):
        unassigned = db.rows(_con, """SELECT s.id, s.full_name, s.hemis_id FROM students s WHERE s.group_id=? AND s.status='faol'
            AND s.id NOT IN (SELECT student_id FROM prac_assign WHERE period_id=?) ORDER BY s.full_name""", (p["group_id"], pid))
    bases = []
    if mode(c) == "full":
        for b in db.rows(_con, """SELECT b.*, c.capacity FROM prac_bases b JOIN prac_base_caps c ON c.base_id=b.id AND c.direction=? ORDER BY b.name""", (p["direction"],)):
            st = agreement_state(b)
            bases.append({"id": b["id"], "name": b["name"], "capacity": b["capacity"], "used": used(b["id"], p["direction"], p["start"], p["end"]),
                          "agreement_state": st, "agreement_expires": b["agreement_expires"],
                          "ok": b["status"] == "faol" and (b["agreement_expires"] or "") >= p["end"]})
    teachers = []
    if mode(c) in ("full", "kafedra"):
        teachers = db.rows(_con, "SELECT id, full_name, position FROM teachers WHERE department_id=? ORDER BY full_name", (p["department_id"],))
    return {"period": p, "rows": rows, "unassigned": unassigned, "bases": bases, "teachers": teachers}

def assign_detail(c: Ctx, aid: int) -> dict:
    a = _assign_row(c, aid)
    if not _names(c): raise AccessDenied("⛔ Amaliyot: rahbariyat uchun faqat jamlangan ko'rinish. So'rov audit jurnaliga yozildi.")
    a["base"] = (db.one(_con, "SELECT name FROM prac_bases WHERE id=?", (a["base_id"],)) or {}).get("name") if a["base_id"] else None
    a["kaf_supervisor"] = (db.one(_con, "SELECT full_name FROM teachers WHERE id=?", (a["kaf_supervisor_id"],)) or {}).get("full_name") if a["kaf_supervisor_id"] else None
    a["diary"] = db.rows(_con, "SELECT day, text, author, author_kind, at FROM prac_diary WHERE assign_id=? ORDER BY day, id", (aid,))
    a["flags"] = flags(a, _today().isoformat())
    a["can_grade"] = can_grade(c, a)
    a["letter"] = AR.letter(a["score"]) if a["score"] is not None else None
    return a

def alerts(c: Ctx) -> dict:
    today = _today().isoformat()
    names = _names(c)
    out = {k: [] for k in FLAG_TITLES}
    for r in db.rows(_con, f"""SELECT a.id, a.status, a.base_id, a.report_at, a.kaf_supervisor_id, p.id period_id, p.title, p.start, p.end, p.report_due,
            g.name grp, s.full_name, t.full_name kaf_supervisor, b.name base
        FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id JOIN groups_ g ON g.id=p.group_id JOIN students s ON s.id=a.student_id
        LEFT JOIN teachers t ON t.id=a.kaf_supervisor_id LEFT JOIN prac_bases b ON b.id=a.base_id
        WHERE {a_scope(c)} AND a.status!='baholandi' ORDER BY p.report_due, g.name, s.full_name"""):
        for f in flags(r, today):
            if not names: r = {**r, "full_name": "—"}
            out[f].append(r)
    agr = []
    if mode(c) in ("full", "lead", "reg", "kafedra"):
        for b in db.rows(_con, "SELECT * FROM prac_bases WHERE status='faol' ORDER BY agreement_expires"):
            st = agreement_state(b)
            if st in ("tugayapti", "muddati o'tgan"):
                b["agreement_state"] = st
                b["future_students"] = db.one(_con, "SELECT COUNT(*) n FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id WHERE a.base_id=? AND p.end>=?",
                                              (b["id"], today))["n"]
                agr.append(b)
    # biriktirilmagan talabalar (davr bor, talaba ro'yxatda yo'q)
    unas = []
    if mode(c) in ("full", "kafedra", "reg"):
        unas = db.rows(_con, f"""SELECT p.id period_id, p.title, p.start, g.name grp,
            (SELECT COUNT(*) FROM students s WHERE s.group_id=g.id AND s.status='faol' AND s.id NOT IN (SELECT student_id FROM prac_assign WHERE period_id=p.id)) n
            FROM prac_periods p JOIN groups_ g ON g.id=p.group_id WHERE {g_scope(c)} AND p.end>=? ORDER BY p.start""", (today,))
        unas = [u for u in unas if u["n"]]
    return {"items": {k: v[:300] for k, v in out.items()}, "counts": {k: len(v) for k, v in out.items()}, "agreements": agr, "unassigned": unas}

def stats(c: Ctx) -> dict:
    sc = a_scope(c)
    by_base = db.rows(_con, f"""SELECT b.id, b.name, b.kind, COUNT(a.id) students, SUM(a.status='baholandi') graded, ROUND(AVG(a.score),1) avg_score,
        SUM(a.score IS NOT NULL AND a.score<{AR.PASS}) failed, COUNT(DISTINCT g.direction) directions
        FROM prac_bases b LEFT JOIN prac_assign a ON a.base_id=b.id LEFT JOIN prac_periods p ON p.id=a.period_id LEFT JOIN groups_ g ON g.id=p.group_id
        WHERE a.id IS NULL OR ({sc}) GROUP BY b.id ORDER BY students DESC, b.name""")
    by_group = db.rows(_con, f"""SELECT g.id, g.name grp, g.direction, p.title, p.start, p.end, COUNT(a.id) students, SUM(a.status='baholandi') graded,
        SUM(a.status IN ('hisobot','baholandi')) reported, ROUND(AVG(a.score),1) avg_score, SUM(a.score IS NOT NULL AND a.score<{AR.PASS}) failed,
        (SELECT COUNT(*) FROM students s WHERE s.group_id=g.id AND s.status='faol') group_size
        FROM prac_periods p JOIN groups_ g ON g.id=p.group_id LEFT JOIN prac_assign a ON a.period_id=p.id
        WHERE {g_scope(c)} AND (a.id IS NULL OR {sc}) GROUP BY p.id ORDER BY p.start DESC, g.name""")
    by_kind = db.rows(_con, f"""SELECT p.kind, COUNT(a.id) students, ROUND(AVG(a.score),1) avg_score FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id
        JOIN groups_ g ON g.id=p.group_id WHERE {sc} GROUP BY p.kind""")
    for k in by_kind: k["title"] = KINDS.get(k["kind"], k["kind"])
    return {"by_base": by_base, "by_group": by_group, "by_kind": by_kind, "kpi": kpis(c)}

def curriculum_plan(c: Ctx, term: int) -> list:
    """O'quv rejasidan: shu semestrda amaliyot fani bor guruhlar (davri hali yaratilmagan)."""
    if term not in (AR.CURRENT_SEMESTER, AR.CURRENT_SEMESTER + 1): _bad("Semestr: joriy yoki keyingi")
    out = []
    for g in db.rows(_con, f"""SELECT g.* FROM groups_ g WHERE {g_scope(c)} AND EXISTS(SELECT 1 FROM students s WHERE s.group_id=g.id AND s.status='faol')
            ORDER BY g.direction, g.course, g.name"""):
        n = AR.sem_no(g["course"], term)
        for cu in db.rows(_con, "SELECT subject, credits FROM curriculum WHERE direction=? AND level=? AND sem_no=?", (g["direction"], g["level"], n)):
            if not CURR_RX.search(cu["subject"]): continue
            kind = "malakaviy" if "malakaviy" in cu["subject"].lower() else "ilmiy" if "ilmiy" in cu["subject"].lower() else "pedagogik"
            exists = db.one(_con, "SELECT id FROM prac_periods WHERE group_id=? AND kind=? AND sem_no=?", (g["id"], kind, n))
            out.append({"group_id": g["id"], "grp": g["name"], "direction": g["direction"], "course": g["course"], "form": g["form"], "sem_no": n,
                        "subject": cu["subject"], "credits": cu["credits"], "kind": kind, "exists": bool(exists)})
    return out

def default_dates(term: int):
    s, e = AR.term_dates(term)
    if term % 2 == 0:   # bahorgi: bitiruvoldi amaliyot — 6 hafta, fevral boshidan
        st = dt.date.fromisoformat(s) + dt.timedelta(days=(7 - dt.date.fromisoformat(s).weekday()) % 7)
    else:
        st = dt.date.fromisoformat(s) + dt.timedelta(days=60)
        st += dt.timedelta(days=(7 - st.weekday()) % 7)
    en = st + dt.timedelta(days=41)
    return st.isoformat(), en.isoformat(), (en + dt.timedelta(days=RULES["report_after_days"])).isoformat()

# =============================================================================================
# Yozish
# =============================================================================================
class BaseIn(BaseModel):
    name: str = Field("", max_length=200)
    kind: str = "xususiy"
    address: str = Field("", max_length=300)
    contact_name: str = Field("", max_length=120)
    contact_phone: str = Field("", max_length=40)
    agreement_no: str = Field("", max_length=60)
    agreement_date: str = ""
    agreement_expires: str = ""
    caps: dict = {}
    note: str = Field("", max_length=500)

def _caps(caps: dict) -> dict:
    dirs = {r["direction"] for r in db.rows(_con, "SELECT DISTINCT direction FROM groups_")}
    out = {}
    for k, v in (caps or {}).items():
        if k not in dirs: _bad(f"Noma'lum yo'nalish: {k}")
        try: n = int(v)
        except (TypeError, ValueError): _bad(f"Sig'im son bo'lishi kerak: {k}")
        if n < 0 or n > 500: _bad(f"Sig'im 0..500: {k}")
        if n: out[k] = n
    return out

def save_base(c: Ctx, body: BaseIn, bid: int = 0) -> dict:
    name = body.name.strip()
    if len(name) < 3: _bad("Tashkilot nomini kiriting")
    if body.kind not in BASE_KINDS: _bad("Tashkilot turi noto'g'ri")
    if not body.agreement_no.strip(): _bad("Shartnoma raqamini kiriting")
    ad, ae = _date(body.agreement_date, "Shartnoma sanasi"), _date(body.agreement_expires, "Shartnoma muddati")
    if ae <= ad: _bad("Shartnoma muddati imzolangan sanadan keyin bo'lishi kerak")
    caps = _caps(body.caps)
    if not caps: _bad("Kamida bitta yo'nalish uchun sig'imni kiriting")
    now = _now()
    with _lock:
        dup = db.one(_con, "SELECT id FROM prac_bases WHERE lower(name)=lower(?) AND id!=?", (name, bid))
        if dup: _bad("Bunday nomli baza allaqachon bor")
        vals = (name, body.kind, body.address.strip(), body.contact_name.strip(), body.contact_phone.strip(), body.agreement_no.strip(), ad, ae, body.note.strip())
        if bid:
            if not db.one(_con, "SELECT id FROM prac_bases WHERE id=?", (bid,)): _bad("Baza topilmadi", 404)
            _con.execute("""UPDATE prac_bases SET name=?,kind=?,address=?,contact_name=?,contact_phone=?,agreement_no=?,agreement_date=?,agreement_expires=?,note=?,updated_at=?
                WHERE id=?""", vals + (now, bid))
        else:
            bid = _con.execute("""INSERT INTO prac_bases(name,kind,address,contact_name,contact_phone,agreement_no,agreement_date,agreement_expires,note,status,created_by,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,'faol',?,?,?)""", vals + (c.user["id"], now, now)).lastrowid
        _con.execute("DELETE FROM prac_base_caps WHERE base_id=?", (bid,))
        for k, v in caps.items(): _con.execute("INSERT INTO prac_base_caps VALUES(?,?,?)", (bid, k, v))
        _con.commit()
    return {"id": bid}

class PeriodIn(BaseModel):
    group_ids: list[int] = []
    kind: str = "ishlab"
    title: str = Field("", max_length=160)
    start: str = ""
    end: str = ""
    report_due: str = ""
    credits: int = 6

def create_periods(c: Ctx, body: PeriodIn, source="jadval", sem_map=None) -> dict:
    if body.kind not in KINDS: _bad("Amaliyot turi noto'g'ri")
    if not body.group_ids: _bad("Kamida bitta guruhni tanlang")
    if len(body.group_ids) > 60: _bad("Bir martada ko'pi bilan 60 ta guruh")
    s, e = _date(body.start, "Boshlanish"), _date(body.end, "Tugash")
    if e < s: _bad("Tugash sanasi boshlanishdan oldin")
    if (_d(e) - _d(s)).days > 120: _bad("Amaliyot davri 120 kundan oshmasligi kerak")
    due = _date(body.report_due, "Hisobot muddati") if body.report_due else (_d(e) + dt.timedelta(days=RULES["report_after_days"])).isoformat()
    if due < e: _bad("Hisobot muddati amaliyot tugaganidan keyin bo'lishi kerak")
    if not 0 < int(body.credits) <= 30: _bad("Kredit 1..30")
    title = body.title.strip() or KINDS[body.kind]
    made, skipped = [], []
    with _lock:
        for gid in dict.fromkeys(int(x) for x in body.group_ids):
            g = db.one(_con, f"SELECT g.* FROM groups_ g WHERE g.id=? AND {g_scope(c)}", (gid,))
            if not g: _bad(f"Guruh topilmadi yoki ko'lamingizda emas: #{gid}")
            clash = db.one(_con, "SELECT id, title FROM prac_periods WHERE group_id=? AND start<=? AND end>=?", (gid, e, s))
            if clash: skipped.append({"group": g["name"], "reason": f"shu vaqtda «{clash['title']}» bor"}); continue
            sem = (sem_map or {}).get(gid) or AR.sem_no(g["course"], AR.CURRENT_SEMESTER if s <= AR.term_dates(AR.CURRENT_SEMESTER)[1] else AR.CURRENT_SEMESTER + 1)
            pid = _con.execute("""INSERT INTO prac_periods(title,kind,group_id,course,sem_no,start,end,report_due,credits,source,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (title, body.kind, gid, g["course"], sem, s, e, due, int(body.credits), source, c.user["id"], _now())).lastrowid
            made.append({"id": pid, "group": g["name"]})
        _con.commit()
    return {"created": made, "skipped": skipped}

class AssignIn(BaseModel):
    base_id: int
    student_ids: list[int] = []
    all_unassigned: bool = False
    kaf_supervisor_id: int | None = None
    org_supervisor: str = Field("", max_length=120)
    org_phone: str = Field("", max_length=40)

def assign(c: Ctx, pid: int, body: AssignIn) -> dict:
    p = _period_row(c, pid)
    b = db.one(_con, "SELECT * FROM prac_bases WHERE id=?", (body.base_id,))
    if not b: _bad("Baza topilmadi", 404)
    if b["status"] != "faol": _bad("Baza faol emas (hamkorlik to'xtatilgan)")
    if (b["agreement_expires"] or "") < p["end"]:
        _bad(f"Shartnoma muddati ({b['agreement_expires'] or '—'}) amaliyot tugashidan ({p['end']}) oldin tugaydi — avval shartnomani yangilang")
    cap = capacity(b["id"], p["direction"])
    if not cap: _bad(f"«{b['name']}» bazasida «{p['direction']}» yo'nalishi uchun joy belgilanmagan")
    if body.kaf_supervisor_id and not db.one(_con, "SELECT id FROM teachers WHERE id=? AND department_id=?", (body.kaf_supervisor_id, p["department_id"])):
        _bad("Amaliyot rahbari guruh kafedrasi o'qituvchisi bo'lishi kerak")
    with _lock:
        if body.all_unassigned:
            ids = [r["id"] for r in db.rows(_con, """SELECT id FROM students WHERE group_id=? AND status='faol'
                AND id NOT IN (SELECT student_id FROM prac_assign WHERE period_id=?) ORDER BY full_name""", (p["group_id"], pid))]
        else:
            ids = list(dict.fromkeys(int(x) for x in body.student_ids))
        if not ids: _bad("Biriktiriladigan talaba yo'q")
        for sid in ids:
            s = db.one(_con, "SELECT id, status FROM students WHERE id=? AND group_id=?", (sid, p["group_id"]))
            if not s: _bad(f"Talaba #{sid} bu guruhda emas")
            if s["status"] != "faol": _bad(f"Talaba #{sid} faol emas")
            if db.one(_con, "SELECT id FROM prac_assign WHERE period_id=? AND student_id=?", (pid, sid)): _bad(f"Talaba #{sid} allaqachon biriktirilgan")
        free = cap - used(b["id"], p["direction"], p["start"], p["end"])
        if len(ids) > free:
            _bad(f"Sig'im yetmaydi: «{b['name']}» — {p['direction']} bo'yicha {cap} o'rin, bu muddatda bo'sh {max(free, 0)} ta, tanlangan {len(ids)} ta")
        now = _now()
        for sid in ids:
            _con.execute("""INSERT INTO prac_assign(period_id,student_id,base_id,kaf_supervisor_id,org_supervisor,org_phone,status,assigned_by,assigned_at)
                VALUES(?,?,?,?,?,?,'biriktirildi',?,?)""", (pid, sid, b["id"], body.kaf_supervisor_id, body.org_supervisor.strip() or None,
                                                            body.org_phone.strip() or None, c.user["id"], now))
        _con.commit()
    return {"assigned": len(ids), "free_left": free - len(ids)}

def _need_review(c: Ctx, a: dict):
    m = mode(c)
    if m == "full": return
    if m == "kafedra" and a["department_id"] == c.user.get("department_id"): return
    if m == "oqituvchi" and a["kaf_supervisor_id"] == c.user.get("teacher_id"): return
    raise AccessDenied("⛔ Amaliyot: bu talabaning amaliyoti bo'yicha amal sizga tegishli emas. So'rov audit jurnaliga yozildi.")

def set_status(c: Ctx, aid: int, action: str, note: str = "", report: str = "") -> dict:
    a = _assign_row(c, aid)
    _need_review(c, a)
    today, now = _today().isoformat(), _now()
    with _lock:
        if action == "start":
            if a["status"] != "biriktirildi": _bad("Faqat «Biriktirildi» holatidagi talaba uchun")
            if today < a["start"]: _bad(f"Amaliyot {a['start']} da boshlanadi")
            if not a["base_id"]: _bad("Avval baza biriktiring")
            _con.execute("UPDATE prac_assign SET status='boshlandi', started_at=? WHERE id=?", (today, aid))
        elif action == "receive":   # qog'ozdagi hisobotni xodim qabul qildi
            if a["status"] not in ("boshlandi", "qaytarildi"): _bad("Hisobot faqat amaliyotdagi talabadan qabul qilinadi")
            if len(report.strip()) < 20: _bad("Hisobot qisqa mazmunini yozing (kamida 20 belgi)")
            _con.execute("UPDATE prac_assign SET status='hisobot', report_text=?, report_at=?, report_by=?, return_note=NULL WHERE id=?",
                         (report.strip()[:4000], now, _short(c.user["full_name"]), aid))
        elif action == "return":
            if a["status"] != "hisobot": _bad("Faqat topshirilgan hisobot qaytariladi")
            if len(note.strip()) < 5: _bad("Qaytarish sababini yozing")
            _con.execute("UPDATE prac_assign SET status='qaytarildi', return_note=? WHERE id=?", (note.strip()[:500], aid))
        else: _bad("Noma'lum amal")
        _con.commit()
    return {"ok": True}

def grade(c: Ctx, aid: int, score: int, note: str) -> dict:
    a = _assign_row(c, aid)
    if not can_grade(c, a):
        raise AccessDenied("⛔ Amaliyot: bahoni faqat biriktirilgan kafedra rahbari yoki kafedra mudiri qo'yadi. So'rov audit jurnaliga yozildi.")
    if a["status"] not in ("hisobot", "baholandi"): _bad("Baho hisobot topshirilgandan keyin qo'yiladi")
    if not 0 <= int(score) <= 100: _bad("Ball 0..100")
    if a["status"] == "baholandi" and len(note.strip()) < 5: _bad("Bahoni o'zgartirish sababini yozing")
    with _lock:
        _con.execute("UPDATE prac_assign SET status='baholandi', score=?, grade_note=?, graded_by=?, graded_name=?, graded_at=? WHERE id=?",
                     (int(score), note.strip()[:500] or None, c.user.get("teacher_id") or c.user["id"], _short(c.user["full_name"]), _now(), aid))
        _con.commit()
    return {"ok": True, "letter": AR.letter(int(score)), "passed": int(score) >= AR.PASS}

def add_diary(aid: int, text: str, author: str, kind: str, day: str = "") -> dict:
    text = (text or "").strip()
    if len(text) < 5: _bad("Matn juda qisqa")
    a = db.one(_con, "SELECT a.status, p.start, p.end FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id WHERE a.id=?", (aid,))
    # sana berilmasa — bugun; amaliyot tugagan bo'lsa (talaba) — davrning oxirgi kuni (bugungi sana davrdan tashqarida, yozuv rad etilardi)
    d = _date(day, "Kun") if day else (min(a["end"], _today().isoformat()) if kind == "talaba" and a and a["end"] else _today().isoformat())
    if kind == "talaba":
        if a["status"] not in ("boshlandi", "qaytarildi"): _bad("Kundalik amaliyot davomida yoziladi")
        if not a["start"] <= d <= min(a["end"], _today().isoformat()):
            _bad(f"Kun amaliyot davri ichida ({_dmy(a['start'])} – {_dmy(a['end'])}) va bugundan kech bo'lmasligi kerak" +
                 (" — amaliyot yakunlangan, sanani davr ichidan tanlang" if a["end"] < _today().isoformat() else ""))
    with _lock:
        _con.execute("INSERT INTO prac_diary(assign_id,day,text,author,author_kind,at) VALUES(?,?,?,?,?,?)", (aid, d, text[:2000], author, kind, _now()))
        _con.commit()
    return {"ok": True}

def issue_referrals(c: Ctx, pid: int, base_url: str) -> dict:
    """Hujjatlar markazining «Amaliyot yo'llanmasi» shabloni (documents.issue, «practice») — har talabaga alohida, ro'yxatga olingan raqam bilan."""
    from . import documents as D
    p = _period_row(c, pid)
    rows = db.rows(_con, """SELECT a.id, a.student_id, b.name base FROM prac_assign a JOIN prac_bases b ON b.id=a.base_id
        WHERE a.period_id=? AND a.doc_reg IS NULL AND a.status IN ('biriktirildi','boshlandi') ORDER BY a.id""", (pid,))
    if not rows: _bad("Yo'llanma kerak bo'lgan talaba yo'q (barchasiga berilgan yoki biriktirilmagan)")
    made = []
    for r in rows[:80]:
        res = D.issue(_con, c, "practice", {"target": f"s:{r['student_id']}", "org": r["base"], "start": p["start"], "end": p["end"]}, base_url)
        _con.execute("UPDATE prac_assign SET doc_reg=?, doc_file=? WHERE id=?", (res["regs"][0], res["file"], r["id"]))
        made.append(res["regs"][0])
    _con.commit()
    return {"issued": len(made), "regs": made[:20], "left": max(0, len(rows) - 80)}

# =============================================================================================
# HTTP — xodimlar
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)
P = "/api/practice"

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi"); return meta(c)

@router.get(P + "/bases")
def api_bases(request: Request, q: str = ""):
    c = C(request); guard(c, "bazalar ro'yxati", q[:40], modes=("full", "lead", "reg", "kafedra")); return list_bases(c, q.strip()[:60])

@router.post(P + "/bases")
def api_base_new(body: BaseIn, request: Request):
    c = C(request); guard(c, "baza qo'shildi", body.name[:80], modes=("full",)); return save_base(c, body)

@router.post(P + "/bases/{bid}")
def api_base_edit(bid: int, body: BaseIn, request: Request):
    c = C(request); guard(c, "baza tahrirlandi", f"#{bid} {body.name[:60]}", modes=("full",)); return save_base(c, body, bid)

class StatusIn(BaseModel):
    status: str = ""
    note: str = Field("", max_length=500)
    report: str = Field("", max_length=4000)

@router.post(P + "/bases/{bid}/status")
def api_base_status(bid: int, body: StatusIn, request: Request):
    c = C(request); guard(c, "baza holati", f"#{bid} → {body.status}", modes=("full",))
    if body.status not in ("faol", "to'xtatilgan"): _bad("Holat: faol yoki to'xtatilgan")
    if not db.one(_con, "SELECT id FROM prac_bases WHERE id=?", (bid,)): _bad("Baza topilmadi", 404)
    _con.execute("UPDATE prac_bases SET status=?, note=COALESCE(NULLIF(?,''),note), updated_at=? WHERE id=?", (body.status, body.note.strip(), _now(), bid)); _con.commit()
    return {"ok": True}

@router.get(P + "/periods")
def api_periods(request: Request, status: str = "", q: str = ""):
    c = C(request); guard(c, "davrlar ro'yxati", modes=("full", "kafedra", "oqituvchi", "tyutor", "reg")); return list_periods(c, status, q.strip()[:60])

@router.post(P + "/periods")
def api_period_new(body: PeriodIn, request: Request):
    c = C(request); guard(c, "davr yaratildi (jadval)", f"{body.kind} · {len(body.group_ids)} guruh · {body.start}..{body.end}", modes=("full",))
    return create_periods(c, body)

@router.get(P + "/plan")
def api_plan(request: Request, term: int = AR.CURRENT_SEMESTER + 1):
    c = C(request); guard(c, "o'quv reja bo'yicha reja", f"semestr {term}", modes=("full", "kafedra"))
    s, e, due = default_dates(term)
    return {"term": term, "season": AR.term_season(term), "year": AR.term_year(term), "start": s, "end": e, "report_due": due, "rows": curriculum_plan(c, term)}

class FromCurrIn(BaseModel):
    term: int = AR.CURRENT_SEMESTER + 1
    group_ids: list[int] = []
    start: str = ""
    end: str = ""
    report_due: str = ""

@router.post(P + "/periods/from-curriculum")
def api_from_curr(body: FromCurrIn, request: Request):
    c = C(request); guard(c, "davr yaratildi (o'quv reja)", f"semestr {body.term} · {len(body.group_ids)} guruh", modes=("full",))
    plan = {r["group_id"]: r for r in curriculum_plan(c, body.term) if not r["exists"]}
    ids = [g for g in (body.group_ids or list(plan)) if g in plan]
    if not ids: _bad("O'quv rejasida shu semestrda amaliyoti bor (va davri hali yaratilmagan) guruh topilmadi")
    s, e, due = default_dates(body.term)
    out = {"created": [], "skipped": []}
    by_kind = {}
    for g in ids: by_kind.setdefault((plan[g]["kind"], plan[g]["subject"], plan[g]["credits"]), []).append(g)
    for (kind, subj, cr), gs in by_kind.items():
        r = create_periods(c, PeriodIn(group_ids=gs, kind=kind, title=subj, start=body.start or s, end=body.end or e, report_due=body.report_due or due,
                                       credits=cr), source="o'quv reja", sem_map={g: plan[g]["sem_no"] for g in gs})
        out["created"] += r["created"]; out["skipped"] += r["skipped"]
    return out

@router.get(P + "/periods/{pid}")
def api_period(pid: int, request: Request):
    c = C(request); guard(c, "davr ochildi", f"#{pid}", modes=("full", "kafedra", "oqituvchi", "tyutor", "reg")); return period_detail(c, pid)

@router.post(P + "/periods/{pid}/delete")
def api_period_delete(pid: int, request: Request):
    c = C(request); guard(c, "davr o'chirildi", f"#{pid}", modes=("full",))
    _period_row(c, pid)
    if db.one(_con, "SELECT COUNT(*) n FROM prac_assign WHERE period_id=?", (pid,))["n"]: _bad("Davrda biriktirilgan talabalar bor — avval ularni chiqaring")
    _con.execute("DELETE FROM prac_periods WHERE id=?", (pid,)); _con.commit()
    return {"ok": True}

@router.post(P + "/periods/{pid}/assign")
def api_assign(pid: int, body: AssignIn, request: Request):
    c = C(request); guard(c, "talabalar biriktirildi", f"davr #{pid} · baza #{body.base_id} · {'barcha biriktirilmaganlar' if body.all_unassigned else len(body.student_ids)}",
                          modes=("full",))
    return assign(c, pid, body)

@router.post(P + "/periods/{pid}/referrals")
def api_referrals(pid: int, request: Request):
    c = C(request); guard(c, "yo'llanmalar", f"davr #{pid}", modes=("full",))
    return issue_referrals(c, pid, str(request.base_url).rstrip("/"))

@router.get(P + "/assign/{aid}")
def api_assign_get(aid: int, request: Request):
    c = C(request); guard(c, "talaba amaliyoti ochildi", f"#{aid}", modes=("full", "kafedra", "oqituvchi", "tyutor", "reg")); return assign_detail(c, aid)

@router.post(P + "/assign/{aid}/unassign")
def api_unassign(aid: int, request: Request):
    c = C(request); guard(c, "biriktirish bekor qilindi", f"#{aid}", modes=("full",))
    a = _assign_row(c, aid)
    if a["status"] not in ("biriktirildi",): _bad("Amaliyot boshlangan — bekor qilib bo'lmaydi")
    _con.execute("DELETE FROM prac_diary WHERE assign_id=?", (aid,)); _con.execute("DELETE FROM prac_assign WHERE id=?", (aid,)); _con.commit()
    return {"ok": True}

class SupIn(BaseModel):
    kaf_supervisor_id: int | None = None
    org_supervisor: str = Field("", max_length=120)
    org_phone: str = Field("", max_length=40)
    assign_ids: list[int] = []

@router.post(P + "/periods/{pid}/supervisor")
def api_supervisor(pid: int, body: SupIn, request: Request):
    c = C(request); guard(c, "amaliyot rahbari", f"davr #{pid} · o'qituvchi #{body.kaf_supervisor_id} · {len(body.assign_ids) or 'hammasi'}", modes=("full", "kafedra"))
    p = _period_row(c, pid)
    if body.kaf_supervisor_id and not db.one(_con, "SELECT id FROM teachers WHERE id=? AND department_id=?", (body.kaf_supervisor_id, p["department_id"])):
        _bad("Amaliyot rahbari guruh kafedrasi o'qituvchisi bo'lishi kerak")
    ids = [r["id"] for r in db.rows(_con, "SELECT id FROM prac_assign WHERE period_id=?", (pid,))]
    if body.assign_ids: ids = [i for i in ids if i in set(body.assign_ids)]
    if not ids: _bad("Talaba tanlanmagan")
    sets, args = [], []
    if body.kaf_supervisor_id: sets.append("kaf_supervisor_id=?"); args.append(body.kaf_supervisor_id)
    if body.org_supervisor.strip(): sets.append("org_supervisor=?"); args.append(body.org_supervisor.strip())
    if body.org_phone.strip(): sets.append("org_phone=?"); args.append(body.org_phone.strip())
    if not sets: _bad("O'zgartirish yo'q")
    _con.execute(f"UPDATE prac_assign SET {', '.join(sets)} WHERE id IN ({','.join('?' * len(ids))})", args + ids); _con.commit()
    return {"updated": len(ids)}

@router.post(P + "/assign/{aid}/status")
def api_status(aid: int, body: StatusIn, request: Request):
    c = C(request); guard(c, f"holat: {body.status}", f"#{aid}", modes=("full", "kafedra", "oqituvchi"))
    return set_status(c, aid, body.status, body.note, body.report)

class GradeIn(BaseModel):
    score: int
    note: str = Field("", max_length=500)

@router.post(P + "/assign/{aid}/grade")
def api_grade(aid: int, body: GradeIn, request: Request):
    c = C(request); guard(c, "baho qo'yildi", f"#{aid} → {body.score}", modes=("kafedra", "oqituvchi"))
    return grade(c, aid, body.score, body.note)

class DiaryIn(BaseModel):
    text: str = Field("", max_length=2000)
    day: str = ""

@router.post(P + "/assign/{aid}/diary")
def api_diary(aid: int, body: DiaryIn, request: Request):
    c = C(request); guard(c, "kundalikka izoh", f"#{aid}", modes=("full", "kafedra", "oqituvchi"))
    a = _assign_row(c, aid); _need_review(c, a)
    return add_diary(aid, body.text, _short(c.user["full_name"]), "rahbar")

@router.get(P + "/alerts")
def api_alerts(request: Request):
    c = C(request); guard(c, "ogohlantirishlar"); return alerts(c)

@router.get(P + "/stats")
def api_stats(request: Request):
    c = C(request); guard(c, "statistika"); return stats(c)

@router.get(P + "/lookup/groups")
def api_lookup_groups(request: Request, q: str = ""):
    c = C(request); guard(c, "guruh qidiruvi", q[:40], modes=("full",))
    q = q.strip()[:40]
    return db.rows(_con, f"""SELECT g.id, g.name, g.course, g.direction, g.form FROM groups_ g WHERE {g_scope(c)} AND (g.name LIKE ? OR g.direction LIKE ?)
        ORDER BY g.name LIMIT 40""", (f"%{q}%", f"%{q}%"))

# =============================================================================================
# HTTP — talaba kabineti (/talaba): o'z amaliyoti, kundalik, hisobot
# =============================================================================================
def _stp(): from . import student_portal as STP; return STP

@router.get("/api/talaba/amaliyot")
def api_t_list(request: Request):
    STP = _stp(); s = STP.student(request)
    today = _today().isoformat()
    rows = db.rows(_con, """SELECT a.id, a.status, a.org_supervisor, a.org_phone, a.doc_reg, a.report_at, a.return_note, a.score, a.graded_at, a.started_at,
        p.title, p.kind, p.start, p.end, p.report_due, p.credits, b.name base, b.address, b.contact_phone base_phone, t.full_name kaf_supervisor,
        (SELECT COUNT(*) FROM prac_diary d WHERE d.assign_id=a.id) diary_n
        FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id LEFT JOIN prac_bases b ON b.id=a.base_id LEFT JOIN teachers t ON t.id=a.kaf_supervisor_id
        WHERE a.student_id=? ORDER BY p.start DESC""", (s["id"],))
    for r in rows:
        r["status_name"] = ST.get(r["status"], r["status"])
        r["flags"] = flags(r, today)
        r["letter"] = AR.letter(r["score"]) if r["score"] is not None else None
        r["can_diary"] = r["status"] in ("boshlandi", "qaytarildi") and r["start"] <= today
        # amaliyot davri tugagan (hisobot hali topshirilmagan): holat «Amaliyotda» emas, kundalik sanasi — davr ichidagi oxirgi kun
        r["ended"] = bool(r["end"]) and r["end"] < today
        if r["ended"] and r["status"] == "boshlandi":
            r["status_name"] = "Yakunlangan — hisobot kutilmoqda"
        r["diary_min"], r["diary_max"] = r["start"], min(r["end"] or today, today)
        r["diary_day"] = r["diary_max"]
        r["diary_note"] = (f"Amaliyot {_dmy(r['end'])} da yakunlangan. Kundalikka faqat amaliyot kunlari ({_dmy(r['start'])} – {_dmy(r['end'])}) uchun yozuv "
                           "qo'shiladi — sanani shu oraliqdan tanlang, so'ng hisobotni topshiring.") if r["ended"] and r["can_diary"] else ""
        r["can_report"] = r["status"] in ("boshlandi", "qaytarildi") and today >= r["start"]
        r["diary"] = db.rows(_con, "SELECT day, text, author, author_kind FROM prac_diary WHERE assign_id=? ORDER BY day DESC, id DESC LIMIT 30", (r["id"],))
    pending = db.rows(_con, """SELECT p.title, p.start, p.end FROM prac_periods p WHERE p.group_id=? AND p.end>=?
        AND NOT EXISTS(SELECT 1 FROM prac_assign a WHERE a.period_id=p.id AND a.student_id=?)""", (s["group_id"], today, s["id"]))
    STP._audit("amaliyot ko'rildi", True, s, resource=RES)
    return {"items": rows, "pending": pending, "rules": {"report_min_chars": RULES["report_min_chars"]}, "today": today}

def _t_assign(s, aid):
    a = db.one(_con, "SELECT a.*, p.start, p.end, p.report_due FROM prac_assign a JOIN prac_periods p ON p.id=a.period_id WHERE a.id=? AND a.student_id=?", (aid, s["id"]))
    if not a: _bad("Topilmadi", 404)
    return a

@router.post("/api/talaba/amaliyot/{aid}/diary")
def api_t_diary(aid: int, body: DiaryIn, request: Request):
    STP = _stp(); s = STP.student(request)
    _t_assign(s, aid)
    try: r = add_diary(aid, body.text, s["full_name"], "talaba", body.day)
    except HTTPException as e: STP._audit("amaliyot kundaligi", False, s, str(e.detail)[:100], resource=RES); raise
    STP._audit("amaliyot kundaligi", True, s, f"#{aid}", resource=RES)
    return r

class ReportIn(BaseModel):
    text: str = Field("", max_length=4000)

@router.post("/api/talaba/amaliyot/{aid}/report")
def api_t_report(aid: int, body: ReportIn, request: Request):
    STP = _stp(); s = STP.student(request)
    a = _t_assign(s, aid)
    text = (body.text or "").strip()
    if a["status"] not in ("boshlandi", "qaytarildi"):
        STP._audit("amaliyot hisoboti", False, s, f"#{aid} holat {a['status']}", resource=RES); _bad("Hisobot amaliyot davomida yoki qaytarilganda topshiriladi")
    if _today().isoformat() < a["start"]: _bad("Amaliyot hali boshlanmagan")
    if len(text) < RULES["report_min_chars"]: _bad(f"Hisobot mazmuni kamida {RULES['report_min_chars']} belgi bo'lishi kerak")
    with _lock:
        _con.execute("UPDATE prac_assign SET status='hisobot', report_text=?, report_at=?, report_by='talaba', return_note=NULL WHERE id=?", (text, _now(), aid))
        _con.commit()
    STP._audit("amaliyot hisoboti topshirildi", True, s, f"#{aid}", resource=RES)
    return {"ok": True, "late": _today().isoformat() > (a["report_due"] or a["end"])}
