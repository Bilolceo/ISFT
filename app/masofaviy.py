"""«Masofaviy ta'lim» — Masofaviy ta'lim bo'limi ish stoli (docs/masofaviy.md).

Bo'lim talabi (2026-11 uchrashuvi): ikkita asosiy narsa — (1) masofaviy ta'lim talabalari holati va (2) o'quv kontenti monitoringi;
ular ustiga «xavf ostida» ro'yxati, haftalik ko'rinish, AI xulosa va hisobot, bo'lim xodimlariga topshiriq (mavjud directives moduli).

1. Talabalar (study_form='masofaviy'):
   * LMS faolligi — dl_activity (haftalik: kirishlar, daqiqa, ko'rilgan material, videokonferensiya, topshiriqlar). Manba: LMS/VK
     platformasi eksporti (CSV/XLSX import) yoki keyinchalik API. Hozircha DEMO ma'lumot (src='demo').
   * Aktiv / noaktiv / umuman kirmagan — oxirgi kirish sanasi va «inactive_days» qoidasi bo'yicha.
   * O'zlashtirish — baholar jadvalidan (academic_rules): joriy semestr oraliq nazorati (< ORALIQ_MIN) va akademik qarzlar.
   * Buyruq holati — Buyruqlar moduli tahlilidan (orders.analyze: qabul/kursga o'tkazish/ta'til buyrug'i yo'q yoki nomuvofiq)
     va imzolanmagan (jarayondagi) buyruqlar.
2. O'quv kontenti: dl_courses (fan × yo'nalish × kurs, mas'ul o'qituvchi va kafedra) → dl_items (mavzu × material turi × muddat × holat).
   Holat: kutilmoqda → yuklandi (o'qituvchi yoki import) → tasdiqlandi / qaytarildi (bo'lim xodimi). Kafedra, o'qituvchi va yo'nalish kesimida
   foiz, muddati o'tgan, bugun va yaqin kunlarda tugaydiganlar. Kechikayotgan kafedraga bir bosishda topshiriq (directives.create_linked).
3. Xavf ostida — deterministik qoidalar (dl_policy chegaralari bilan); har bir sabab alohida, og'irlik bilan.
4. AI xulosa — Claude'ga FAQAT jamlangan raqamlar yuboriladi (talaba ismi, HEMIS ID, telefon yuborilmaydi). Raqamlarni kod hisoblaydi;
   AI matnidagi har bir raqam faktlar bilan solishtiriladi — faktlarda yo'q raqamli jumla olib tashlanadi. Kalit bo'lmasa — qoidaga asoslangan xulosa.
5. Hisobot (.docx) — ISFT blankasida; rahbariyat nusxasida talaba ismlari yo'q.

Ruxsat (modul jadvali, har bir so'rov audit jurnaliga yoziladi — rbac.DISTANCE):
   masofaviy (bo'lim boshlig'i), masofaviy_xodim — to'liq: talaba ro'yxati, import, materialni tasdiqlash/qaytarish;
   kafedraga topshiriq va qoidalar — faqat bo'lim boshlig'i;
   rektor, prorektor_oquv — faqat jamlangan ko'rinish (talaba ismlarisiz), AI xulosa va hisobot;
   kafedra — o'z kafedrasi materiallari; oqituvchi — o'z materiallari (yuklandi deb belgilash, LMS havolasi bilan).
"""
import csv, datetime as dt, hashlib, io, json, os, random, re, threading, zlib
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
P = "/api/masofaviy"
RES = rbac.DISTANCE

HEAD, STAFF = "masofaviy", "masofaviy_xodim"
DEPT = (HEAD, STAFF)                      # bo'lim: to'liq ko'rinish va amallar
LEAD = ("rektor", "prorektor_oquv")       # rahbariyat: jamlangan ko'rinish
KAF, TEACH = "kafedra", "oqituvchi"
ALL = DEPT + LEAD + (KAF, TEACH)
UNIT = "masofaviy"                        # org_units kaliti

KINDS = {"maruza": "Ma'ruza matni", "taqdimot": "Taqdimot", "video": "Videodars", "test": "Test"}
ITEM_ST = {"kutilmoqda": "Yuklanmagan", "yuklandi": "Yuklandi (tekshiruvda)", "tasdiqlandi": "Tasdiqlandi", "qaytarildi": "Qaytarildi"}
GIVEN = ("yuklandi", "tasdiqlandi")      # «berilgan» hisoblanadi
OPEN_ST = ("kutilmoqda", "qaytarildi")   # hali ish kerak
TOPICS_PER_COURSE = 15

POLICY = [  # (kalit, standart, izoh) — dl_policy jadvalida o'zgartiriladi
    ("inactive_days", 14, "Shuncha kun LMS'ga kirmasa — noaktiv"),
    ("vc_min_pct", 50, "Videokonferensiyalarga qatnashish shu foizdan past — xavf"),
    ("tasks_min_pct", 50, "LMS topshiriqlari bajarilishi shu foizdan past — xavf"),
    ("window_weeks", 4, "Qatnashish va topshiriqlar shuncha oxirgi hafta bo'yicha hisoblanadi"),
    ("soon_days", 3, "Material muddatiga shuncha kun qolsa — «yaqinlashmoqda»"),
    ("due_lead_days", 2, "Material mavzu haftasidan shuncha kun oldin yuklanishi kerak"),
    ("irregular_weeks", 6, "Notekis faollik: oxirgi shuncha to'liq hafta tekshiriladi"),
    ("irregular_min_active", 3, "Notekis faollik: shu haftalardan kamida shunchasida LMS'ga kirmagan bo'lsa — xavf"),
    ("early_min_logins", 4, "Semestr boshi (birinchi 4 hafta): kirishlar shundan kam bo'lsa — xavf"),
]
POLICY_LIM = {"inactive_days": (3, 60), "vc_min_pct": (10, 100), "tasks_min_pct": (10, 100), "window_weeks": (1, 8), "soon_days": (1, 14),
              "due_lead_days": (0, 7), "irregular_weeks": (3, 12), "irregular_min_active": (1, 12), "early_min_logins": (0, 40)}
EARLY_WEEKS = 4                           # «semestr boshi» — birinchi 4 hafta (o'quv analitikasi: eng kuchli erta ogohlantirish signali)

ISSUE_TITLES = {"no_admission": "Qabul buyrug'i topilmadi", "no_transfer": "Kursga o'tkazish buyrug'i yetishmaydi",
                "leave_no_order": "Akademik ta'til buyrug'i topilmadi", "expelled_active": "Chetlashtirilgan, lekin faol",
                "group_mismatch": "Buyruqdagi guruh boshqa", "contradiction": "Buyruqlar ziddiyatli"}
PENDING_ORDER = ("loyiha", "yuborilgan", "kelishilgan")

SCHEMA = """
CREATE TABLE IF NOT EXISTS dl_courses(id INTEGER PRIMARY KEY, subject TEXT, direction TEXT, course INT, department_id INT, teacher_id INT,
  semester INT, topics INT, lms_ref TEXT, UNIQUE(subject, direction, course, semester));
CREATE TABLE IF NOT EXISTS dl_items(id INTEGER PRIMARY KEY, course_id INT, topic_no INT, topic TEXT, kind TEXT, due TEXT, status TEXT,
  url TEXT, uploaded_at TEXT, uploaded_by INT, checked_at TEXT, checked_by INT, note TEXT, src TEXT, UNIQUE(course_id, topic_no, kind));
CREATE INDEX IF NOT EXISTS ix_dl_items_due ON dl_items(due, status);
CREATE INDEX IF NOT EXISTS ix_dl_items_course ON dl_items(course_id);
CREATE TABLE IF NOT EXISTS dl_activity(student_id INT, week TEXT, logins INT, minutes INT, views INT, vc_att INT, vc_total INT,
  tasks_done INT, tasks_total INT, last_login TEXT, src TEXT, PRIMARY KEY(student_id, week));
CREATE INDEX IF NOT EXISTS ix_dl_act_week ON dl_activity(week);
CREATE TABLE IF NOT EXISTS dl_imports(id INTEGER PRIMARY KEY, kind TEXT, ts TEXT, user_id INT, user_name TEXT, filename TEXT,
  rows INT, ok INT, skipped INT, note TEXT);
CREATE TABLE IF NOT EXISTS dl_log(id INTEGER PRIMARY KEY, item_id INT, ts TEXT, user_id INT, user_name TEXT, action TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_dl_log_item ON dl_log(item_id);
CREATE TABLE IF NOT EXISTS dl_reminders(id INTEGER PRIMARY KEY, department_id INT, task_id INT, ts TEXT, user_id INT, items INT);
CREATE TABLE IF NOT EXISTS dl_ai(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, digest TEXT, engine TEXT, data TEXT, tokens_in INT, tokens_out INT);
CREATE TABLE IF NOT EXISTS dl_policy(k TEXT PRIMARY KEY, v REAL);
CREATE TABLE IF NOT EXISTS dl_meta(k TEXT PRIMARY KEY, v TEXT);
"""

# Demo akkauntlar (sun'iy ism-shariflar). Server ishga tushganda oxiriga qo'shiladi — mavjud akkauntlar id'si o'zgarmaydi.
DEMO_USERS = [("Masofaviy ta'lim bo'limi boshlig'i: Karimova Nilufar Akmal qizi", HEAD, "MASOFAVIY"),
              ("Masofaviy ta'lim bo'limi — kontent menejeri: Tursunov Bekzod Anvar o'g'li", STAFF, "MASKONTENT"),
              ("Masofaviy ta'lim bo'limi — talabalar monitoringi: Aliyeva Gulshan Rustam qizi", STAFF, "MASMONITOR")]


def _now(): return clock.now().replace(microsecond=0)
def _iso(t): return t.isoformat(timespec="seconds")
def _today(): return clock.today()
def _d(s):
    try: return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError): return None
def _monday(d: dt.date) -> dt.date: return d - dt.timedelta(days=d.weekday())
def _short(name): return (name or "").split(":", 1)[1].strip() if ":" in (name or "") else (name or "")
def _pct(a, b): return round(100.0 * a / b, 1) if b else None
def _pf(x): return "—" if x is None else f"{_n(x)}%"          # foiz matni: None → «—» («None%» emas)


# =============================================================================================
# Sxema, qoidalar, demo ma'lumot
# =============================================================================================
def init(con):
    try:
        con.executescript(SCHEMA)
        for k, v, _ in POLICY:
            con.execute("INSERT OR IGNORE INTO dl_policy(k,v) VALUES(?,?)", (k, v))
        con.commit()
    except Exception as e:
        print("masofaviy.init:", e); return
    if not db.one(con, "SELECT 1 x FROM users"): return          # bo'sh baza (seed boshlanmagan)
    try:
        _ensure_users(con)
        seed(con)
        redate(con)
        invalidate()
    except Exception as e:   # demo ma'lumot ilovani to'xtatmasin
        print("masofaviy seed:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def policy(con=None) -> dict:
    con = con or _con
    have = {r["k"]: r["v"] for r in db.rows(con, "SELECT k, v FROM dl_policy")}
    return {k: int(have.get(k, v)) for k, v, _ in POLICY}

def _ensure_users(con):
    from . import rbac as RB
    pw = RB.hash_password(RB.DEMO_PASSWORD)
    for name, role, code in DEMO_USERS:
        if not db.one(con, "SELECT 1 x FROM users WHERE full_name=?", (name,)):
            con.execute("INSERT INTO users(full_name,role,unit,link_code,pin) VALUES(?,?,?,?,?)", (name, role, UNIT, code, pw))
    con.commit()
    try:     # bo'limlar ro'yxati (org_units) yangi bo'limni ko'rsin
        from . import portal as PT
        PT.sync_units(con)
    except Exception as e:
        print("masofaviy: org_units:", repr(e))

def _semester_start() -> dt.date:
    return dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0])

def _due_for(topic_no: int, lead: int) -> dt.date:
    """Mavzu haftasi dushanbasidan «lead» kun oldin (dars kuni siljishi chaqiruvchida qo'shiladi)."""
    return _monday(_semester_start()) + dt.timedelta(days=7 * (topic_no - 1) - lead)

def _topics_for(con, subject: str) -> list[str]:
    """Mavzu nomlari: tasdiqlangan sillabus → tayanch katalog (namuna) → umumiy nom."""
    titles = []
    r = db.one(con, "SELECT draft FROM syl_items WHERE subject=? AND draft IS NOT NULL AND draft!='' ORDER BY status='tasdiqlangan' DESC LIMIT 1", (subject,))
    if r:
        try: titles = [str(t.get("title") or "").strip() for t in json.loads(r["draft"]).get("topics", []) if str(t.get("title") or "").strip()]
        except (ValueError, AttributeError): titles = []
    if not titles:
        r = db.one(con, "SELECT topics FROM syl_ref WHERE subject=? LIMIT 1", (subject,))
        if r:
            try: titles = [str(t).strip() for t in json.loads(r["topics"] or "[]") if str(t).strip()]
            except ValueError: titles = []
    out = titles[:TOPICS_PER_COURSE]
    return out + [""] * (TOPICS_PER_COURSE - len(out))      # nomi noma'lum — «N-mavzu» deb ko'rsatiladi (sillabus tasdiqlangach to'ladi)

def seed(con, force=False):
    """Demo: kontent rejasi va 8 haftalik LMS faolligi (bir marta; dl_meta.seed_v1). Hammasi SUN'IY — haqiqiy LMS ulanguncha."""
    if not force and db.one(con, "SELECT 1 x FROM dl_meta WHERE k='seed_v1'"): return
    if force:
        con.executescript("DELETE FROM dl_items; DELETE FROM dl_courses; DELETE FROM dl_activity; DELETE FROM dl_log; DELETE FROM dl_reminders; DELETE FROM dl_ai;")
    R = random.Random(20261110)
    today, now = _today(), _now()
    pol = policy(con)
    sem = AR.CURRENT_SEMESTER
    # --- 1) kurslar: masofaviy guruhlardagi fan × yo'nalish × kurs; mas'ul — eng ko'p guruhda dars beradigan o'qituvchi ---
    rows = db.rows(con, """SELECT tg.subject, g.direction, g.course, tg.teacher_id, t.department_id, COUNT(*) n
                           FROM teacher_groups tg JOIN groups_ g ON g.id=tg.group_id JOIN teachers t ON t.id=tg.teacher_id
                           WHERE g.form='masofaviy' GROUP BY 1,2,3,4 ORDER BY 1,2,3, n DESC""")
    best = {}
    for r in rows:
        best.setdefault((r["subject"], r["direction"], r["course"]), r)
    if not best: return
    # Hikoyalar: (1) bitta kafedra ataylab ortda; (2) bitta o'qituvchi videodarslarni bermagan; (3) bugun muddati tugaydigan materiallar.
    depts = sorted({r["department_id"] for r in best.values()})
    lag_dept = 4 if 4 in depts else depts[-1]
    mid_dept = next((d for d in depts if d not in (lag_dept, 1)), depts[0])   # «o'rtacha» kafedra — 85% atrofida
    dept_factor = {d: (0.62 if d == lag_dept else 0.87 if d == mid_dept else round(R.uniform(0.965, 0.995), 3)) for d in depts}
    t_load = {}
    for r in best.values():
        if r["department_id"] != lag_dept: t_load[r["teacher_id"]] = t_load.get(r["teacher_id"], 0) + 1
    no_video_teacher = max(t_load, key=t_load.get) if t_load else None
    teacher_factor = {}
    lead = pol["due_lead_days"]
    notes = {"video": ["Video havolasi ochilmayapti (YouTube: «Private»)", "Video ovozi yo'q", "Video boshqa mavzuga tegishli"],
             "taqdimot": ["Taqdimot mavzuga mos emas — boshqa fan slaydlari", "Taqdimot fayli ochilmayapti"],
             "test": ["Test kaliti yo'q", "Testda 10 tadan kam savol"], "maruza": ["Ma'ruza matni rejasiz, hajmi 2 betdan kam", "Adabiyotlar ro'yxati yo'q"]}
    staff = [r["id"] for r in db.rows(con, "SELECT id FROM users WHERE role IN (?,?) ORDER BY id", (HEAD, STAFF))]
    for (subj, direc, course), r in best.items():
        con.execute("INSERT OR IGNORE INTO dl_courses(subject,direction,course,department_id,teacher_id,semester,topics,lms_ref) VALUES(?,?,?,?,?,?,?,?)",
                    (subj, direc, course, r["department_id"], r["teacher_id"], sem, TOPICS_PER_COURSE,
                     f"LMS-{zlib.crc32(f'{subj}|{direc}|{course}'.encode()) % 90000 + 10000}"))
        # lastrowid «OR IGNORE» bo'lganda eski qiymatni qaytaradi — id har doim SELECT bilan olinadi
        row = con.execute("SELECT id FROM dl_courses WHERE subject=? AND direction=? AND course=? AND semester=?", (subj, direc, course, sem)).fetchone()
        if not row: continue
        cid = row[0]
        tf = teacher_factor.setdefault(r["teacher_id"], R.choice([1] * 8 + [0.95, 0.9]))
        wd = zlib.crc32(f"{subj}|{direc}|{course}".encode()) % 5      # dars kuni (Du–Ju): muddatlar hafta bo'ylab taqsimlanadi
        for no, title in enumerate(_topics_for(con, subj), 1):
            due = _due_for(no, lead) + dt.timedelta(days=wd)
            for kind in KINDS:
                days = (today - due).days                                 # >0 — muddati o'tgan
                if days >= 0:
                    p = dept_factor[r["department_id"]] * tf
                    if kind == "video" and r["teacher_id"] == no_video_teacher and no >= 6: p = 0
                    if kind == "test": p *= 0.97
                    given = R.random() < min(0.995, p + min(0.04, days / 600))
                elif days >= -7:
                    given = R.random() < max(0.08, 0.6 + 0.08 * days)      # muddatga qancha yaqin — shuncha ko'p yuklangan
                else:
                    given = R.random() < 0.07
                st, url, up, chk, chk_by, note = "kutilmoqda", None, None, None, None, None
                if given:
                    up_d = due - dt.timedelta(days=R.randint(0, 6)) if R.random() < 0.8 else due + dt.timedelta(days=R.randint(1, 9))
                    up_d = min(up_d, today)
                    up = _iso(dt.datetime.combine(up_d, dt.time(R.randint(9, 20), R.choice([0, 15, 30, 45]))))
                    url = f"https://youtu.be/demo{cid}x{no}" if kind == "video" else f"https://lms.isft.uz/course/{cid}/topic/{no}/{kind}"
                    x = R.random()
                    if x < 0.025 and days > 3: st, note = "qaytarildi", R.choice(notes[kind])
                    elif x < (0.3 if days < 7 else 0.03): st = "yuklandi"
                    else: st = "tasdiqlandi"
                    if st in ("tasdiqlandi", "qaytarildi"):
                        chk = _iso(dt.datetime.fromisoformat(up) + dt.timedelta(hours=R.randint(3, 60)))
                        if chk > _iso(now): chk = _iso(now)
                        chk_by = R.choice(staff) if staff else None
                con.execute("""INSERT OR IGNORE INTO dl_items(course_id,topic_no,topic,kind,due,status,url,uploaded_at,checked_at,checked_by,note,src)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,'demo')""", (cid, no, title[:200], kind, due.isoformat(), st, url, up, chk, chk_by, note))
    # --- 2) LMS faolligi: oxirgi 8 hafta (talaba profili + o'zlashtirish bilan bog'liq) ---
    studs = db.rows(con, """SELECT s.id, s.status, g.course, (SELECT AVG(oraliq) FROM grades gr WHERE gr.student_id=s.id AND gr.semester=?) ora
                            FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy'""", (sem,))
    mon = _monday(today)
    weeks = [mon - dt.timedelta(weeks=k) for k in range(7, -1, -1)]
    batch = []
    for s in studs:
        rs = random.Random(s["id"] * 7907)
        ora = s["ora"] if s["ora"] is not None else 20
        if s["status"] != "faol": prof = "tatil"
        else:
            x = rs.random() - (0.12 if ora < 14 else 0) + (0.04 if ora > 22 else 0)
            prof = "kirmagan" if x < 0.012 + (0.02 if s["course"] == 1 else 0) else "toxtagan" if x < 0.075 else "sust" if x < 0.17 else "faol"
        stop = rs.randint(2, 6) if prof == "toxtagan" else None          # necha hafta oldin to'xtagan
        for wi, w in enumerate(weeks):
            ago = len(weeks) - 1 - wi                                      # 0 — joriy hafta
            if prof in ("kirmagan", "tatil") or (stop is not None and ago < stop):
                lg = 0
            elif prof == "sust":
                lg = rs.choice([0, 0, 1, 1, 2, 3])
            else:
                lg = rs.randint(2, 7)
            if ago == 0: lg = min(lg, max(0, (today - mon).days + 1))       # joriy hafta hali tugamagan
            vc_total = 2 if ago > 0 or (today - mon).days >= 3 else 1
            if lg == 0: vc = 0
            else: vc = sum(1 for _ in range(vc_total) if rs.random() < (0.85 if prof == "faol" else 0.35))
            tt = 2
            td = 0 if lg == 0 else sum(1 for _ in range(tt) if rs.random() < (0.9 if prof == "faol" else 0.45))
            last = None
            if lg:
                last_d = min(today, w + dt.timedelta(days=rs.randint(0, 6)))
                last = _iso(dt.datetime.combine(last_d, dt.time(rs.randint(8, 22), rs.randint(0, 59))))
            batch.append((s["id"], w.isoformat(), lg, lg * rs.randint(15, 70), lg * rs.randint(1, 6), vc, vc_total, td, tt, last, "demo"))
    con.executemany("""INSERT OR REPLACE INTO dl_activity(student_id,week,logins,minutes,views,vc_att,vc_total,tasks_done,tasks_total,last_login,src)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""", batch)
    _seed_orders(con, R)
    con.execute("INSERT OR REPLACE INTO dl_meta(k,v) VALUES('seed_v1', ?)", (_iso(now),))
    con.execute("INSERT OR REPLACE INTO dl_meta(k,v) VALUES('source', 'demo')")
    con.execute("INSERT OR REPLACE INTO dl_meta(k,v) VALUES('anchor', ?)", (_monday(today).isoformat(),))
    con.commit()
    invalidate()


def redate(con, today: dt.date | None = None) -> int:
    """Demo ma'lumotni joriy haftaga ko'chirish (idempotent, arzon). Demo bir marta, o'sha kunga nisbatan yaratiladi; uzoq yashaydigan bazada
    (Railway volume) 2 haftadan keyin hamma talaba «noaktiv»ga o'tib, muddatlar eskirib qolardi. Manba hali «demo» bo'lsa (haqiqiy faollik
    importi yo'q) va saqlangan langar (dl_meta.anchor — seed haftasining dushanbasi) joriy haftadan eski bo'lsa, demo qatorlar butun haftalar
    farqiga suriladi: dl_activity (hafta, oxirgi kirish) va dl_items (muddat; demo qatorlarda yuklangan/tekshirilgan vaqt ham).
    Import qilingan qatorlarga (src='import') tegilmaydi. Qaytaradi: necha haftaga surilgani (0 — kerak emas)."""
    get = lambda k: (con.execute("SELECT v FROM dl_meta WHERE k=?", (k,)).fetchone() or [None])[0]
    if get("source") not in (None, "demo") or not get("seed_v1"): return 0
    anchor = _d(get("anchor")) or _monday(_d(get("seed_v1")) or _today())      # eski bazalar: langar — seed sanasi haftasi
    cur = _monday(today or _today())
    weeks = (cur - _monday(anchor)).days // 7
    if weeks <= 0:
        if not get("anchor"): con.execute("INSERT OR REPLACE INTO dl_meta(k,v) VALUES('anchor', ?)", (_monday(anchor).isoformat(),)); con.commit()
        return 0
    n = f"+{7 * weeks} days"
    now = _iso(dt.datetime.combine(today, dt.time(23, 59, 59)) if today else _now())
    sh = lambda col: f"CASE WHEN {col} IS NULL THEN NULL ELSE strftime('%Y-%m-%dT%H:%M:%S', {col}, '{n}') END"
    try:
        # PRIMARY KEY(student_id, week): surishda vaqtincha to'qnashuv bo'lmasin — avval «~» prefiksi bilan, keyin prefiks olib tashlanadi
        con.execute(f"UPDATE dl_activity SET week='~' || date(week, '{n}'), last_login=MIN({sh('last_login')}, ?) WHERE src='demo'", (now,))
        con.execute("UPDATE dl_activity SET week=substr(week, 2) WHERE week LIKE '~%'")
        con.execute(f"UPDATE dl_items SET due=date(due, '{n}') WHERE src!='import' AND due IS NOT NULL")
        con.execute(f"UPDATE dl_items SET uploaded_at=MIN({sh('uploaded_at')}, ?), checked_at=MIN({sh('checked_at')}, ?) WHERE src='demo'", (now, now))
        con.execute("INSERT OR REPLACE INTO dl_meta(k,v) VALUES('anchor', ?)", (cur.isoformat(),))
        con.commit()
    except Exception:
        con.rollback(); raise
    return weeks

_REDATE = {"day": None, "lock": threading.Lock()}

def _maybe_redate():
    """Kuniga bir marta (server qayta ishga tushmasa ham) — demo sanalarini tekshirish."""
    d = _today()
    if _REDATE["day"] == d or _con is None: return
    with _REDATE["lock"]:                 # ikki oqim bir vaqtda ikki marta surmasin
        if _REDATE["day"] == d: return
        try:
            if redate(_con): _CACHE.clear()
        except Exception as e:
            print("masofaviy.redate:", repr(e))
        _REDATE["day"] = d


def _seed_orders(con, R):
    """Hikoya 4: 3 ta uzoq vaqt kirmagan talaba akademik ta'til so'ragan — buyruq loyihasi Registrator ofisida imzolanmagan."""
    try:
        from . import orders as ORD
        reg = db.one(con, "SELECT u.* FROM org_units o JOIN users u ON u.id=o.head_user WHERE o.key='talabalar'")
        if not reg or db.one(con, "SELECT 1 x FROM orders WHERE source=?", ("Masofaviy ta'lim bo'limi (demo)",)): return
        today = _today()
        cand = db.rows(con, """SELECT a.student_id sid FROM dl_activity a JOIN students s ON s.id=a.student_id WHERE s.status='faol'
                               GROUP BY a.student_id HAVING MAX(a.last_login) IS NOT NULL AND MAX(a.last_login) < ? ORDER BY a.student_id LIMIT 3""",
                           ((today - dt.timedelta(days=21)).isoformat(),))
        if not cand: return
        saved = ORD._con
        ORD._con = saved or con
        try:
            c = Ctx(user=reg, role=rbac.ROLES[reg["role"]])
            ORD.create_order(c, "akademik_tatil", [{"student_id": x["sid"], "data": {"date_from": (today + dt.timedelta(days=7)).isoformat(),
                                                    "date_to": (today + dt.timedelta(days=372)).isoformat(), "reason": "oilaviy sharoit (talaba arizasi)"}} for x in cand],
                             source="Masofaviy ta'lim bo'limi (demo)", note="Talabalar LMS'ga kirmay qo'ygan; arizalar Masofaviy ta'lim bo'limi orqali kelgan")
        finally:
            ORD._con = saved
    except Exception as e:
        print("masofaviy: demo buyruq:", repr(e))


# =============================================================================================
# Ruxsat
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    ok = c.role.key in roles
    rbac.audit(_con, c, f"masofaviy: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Masofaviy ta'lim: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def names_ok(c: Ctx) -> bool:
    """Talaba ism-sharifi va HEMIS ID faqat bo'limga (rahbariyat — jamlangan raqamlar)."""
    return c.role.key in DEPT

def _teacher_id(c: Ctx):
    return c.user.get("teacher_id")

def item_scope(c: Ctx, alias="c") -> tuple[str, tuple]:
    k = c.role.key
    if k == KAF: return f"{alias}.department_id=?", (int(c.user.get("department_id") or 0),)
    if k == TEACH: return f"{alias}.teacher_id=?", (int(_teacher_id(c) or 0),)
    return "1=1", ()


# =============================================================================================
# Talabalar: ko'rsatkichlar va xavf
# =============================================================================================
_CACHE: dict = {}

def _cached(key, ttl, fn):
    hit = _CACHE.get(key)
    now = clock.now().timestamp()
    if hit and now - hit[0] < ttl: return hit[1]
    v = fn(); _CACHE[key] = (now, v); return v

def invalidate(): _CACHE.clear()

def _order_flags() -> dict:
    """{student_id: {"issue": [nomlar], "pending": n}} — Buyruqlar moduli tahlili (60 s kesh)."""
    def build():
        out = {}
        try:
            from . import orders as ORD
            if ORD._con is None: return out
            fake = Ctx(user={"id": 0, "full_name": "Masofaviy ta'lim (tahlil)", "role": HEAD}, role=rbac.ROLES[HEAD])
            for it in ORD.analyze(fake)["items"]:
                if it["student"].get("study_form") != "masofaviy": continue
                out.setdefault(it["student"]["id"], {"issue": [], "pending": 0})["issue"].append(ISSUE_TITLES.get(it["kind"], it["title"]))
        except Exception as e:
            print("masofaviy: buyruqlar tahlili:", repr(e))
        try:
            for r in db.rows(_con, f"""SELECT os.student_id sid, COUNT(DISTINCT o.id) n FROM orders o JOIN order_students os ON os.order_id=o.id AND os.version=o.version
                                       JOIN students s ON s.id=os.student_id WHERE s.study_form='masofaviy' AND o.status IN ({','.join('?' * len(PENDING_ORDER))})
                                       GROUP BY os.student_id""", PENDING_ORDER):
                out.setdefault(r["sid"], {"issue": [], "pending": 0})["pending"] = r["n"]
        except Exception as e:
            print("masofaviy: jarayondagi buyruqlar:", repr(e))
        return out
    return _cached("orders", 60, build)

def _early_window(first: dt.date | None) -> tuple[str, str] | None:
    """Semestrning birinchi EARLY_WEEKS haftasi: semestr boshi (academic_rules) yoki — faollik ma'lumoti keyinroq boshlansa — eng birinchi
    faollik haftasi (first). Oyna hali tugamagan bo'lsa None (yarim oyna bo'yicha xulosa qilinmaydi)."""
    if not first: return None
    start = max(_monday(_semester_start()), _monday(first))
    end = start + dt.timedelta(weeks=EARLY_WEEKS)
    return (start.isoformat(), end.isoformat()) if end <= _monday(_today()) else None

def student_rows() -> list[dict]:
    """Har bir masofaviy talaba: faollik, qatnashish, o'zlashtirish, buyruq, xavf sabablari (30 s kesh)."""
    _maybe_redate()
    def build():
        pol = policy()
        today = _today()
        mon = _monday(today)
        win = (mon - dt.timedelta(weeks=pol["window_weeks"] - 1)).isoformat()
        # Notekis faollik — oxirgi N ta TO'LIQ hafta (joriy hafta hali tugamagan, uni hisobga olsak dushanba kuni hamma «notekis» bo'lardi)
        irr_from, irr_to = (mon - dt.timedelta(weeks=pol["irregular_weeks"])).isoformat(), mon.isoformat()
        first = _d((db.one(_con, "SELECT MIN(week) w FROM dl_activity") or {}).get("w"))
        irr_ok = bool(first) and first.isoformat() <= irr_from     # ma'lumot butun oynani qamraydi (eksportda bo'sh haftalar bo'lmasligi mumkin)
        early = _early_window(first)
        ew = early or ("9999", "9999")
        base = db.rows(_con, """SELECT s.id, s.full_name, s.hemis_id, s.status, s.payment_type, g.id gid, g.name grp, g.course, g.direction,
                                       g.department_id dept FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy'""")
        act = {r["sid"]: r for r in db.rows(_con, """SELECT student_id sid, MAX(last_login) last,
                   SUM(CASE WHEN week>=? THEN logins END) lg, SUM(CASE WHEN week>=? THEN minutes END) mins,
                   SUM(CASE WHEN week>=? THEN vc_att END) va, SUM(CASE WHEN week>=? THEN vc_total END) vt,
                   SUM(CASE WHEN week>=? THEN tasks_done END) td, SUM(CASE WHEN week>=? THEN tasks_total END) tt,
                   COUNT(CASE WHEN week>=? AND week<? AND logins>0 THEN 1 END) ia, SUM(CASE WHEN week>=? AND week<? THEN logins END) el,
                   SUM(CASE WHEN week>=? AND week<? THEN tasks_done END) etd, SUM(CASE WHEN week>=? AND week<? THEN tasks_total END) ett
                   FROM dl_activity GROUP BY student_id""", (win,) * 6 + (irr_from, irr_to) + ew * 3)}
        cur = {r["sid"]: r for r in db.rows(_con, f"""SELECT gr.student_id sid, COUNT(*) n, SUM(gr.oraliq < {AR.ORALIQ_MIN}) low, ROUND(AVG(gr.oraliq),1) avg
                   FROM grades gr JOIN students s ON s.id=gr.student_id WHERE s.study_form='masofaviy' AND gr.semester={AR.CURRENT_SEMESTER}
                   AND gr.oraliq IS NOT NULL GROUP BY gr.student_id""")}
        debts = {r["sid"]: r["n"] for r in db.rows(_con, f"""SELECT g.student_id sid, COUNT(*) n FROM grades g JOIN students s ON s.id=g.student_id
                   WHERE s.study_form='masofaviy' AND {AR.debt_where('g')} GROUP BY g.student_id""")}
        orders = _order_flags()
        out = []
        for s in base:
            a, cu = act.get(s["id"]) or {}, cur.get(s["id"]) or {}
            last = _d(a.get("last"))
            days = (today - last).days if last else None
            on_leave = s["status"] != "faol"
            if on_leave: state = "tatil"
            elif last is None: state = "kirmagan"
            elif days > pol["inactive_days"]: state = "noaktiv"
            else: state = "aktiv"
            vc = _pct(a.get("va") or 0, a.get("vt") or 0)
            tk = _pct(a.get("td") or 0, a.get("tt") or 0)
            low, n_cur, dbt = cu.get("low") or 0, cu.get("n") or 0, debts.get(s["id"], 0)
            of = orders.get(s["id"]) or {"issue": [], "pending": 0}
            reasons = []
            def add(code, label, sev): reasons.append({"code": code, "label": label, "sev": sev})
            if not on_leave:
                if state == "kirmagan": add("kirmagan", "LMS'ga umuman kirmagan", 3)
                elif state == "noaktiv": add("noaktiv", f"{days} kundan beri LMS'ga kirmagan", 3 if days > 2 * pol["inactive_days"] else 2)
                if vc is not None and a.get("vt") and vc < pol["vc_min_pct"]: add("vk", f"Videokonferensiyalar: {a.get('va') or 0}/{a.get('vt')} ({vc:.0f}%)", 2)
                if tk is not None and a.get("tt") and tk < pol["tasks_min_pct"] and state == "aktiv": add("topshiriq", f"LMS topshiriqlari: {a.get('td') or 0}/{a.get('tt')}", 1)
                if low: add("oraliq", f"Oraliq nazorat: {low} ta fanda {AR.ORALIQ_MIN} baldan past", 2 if low >= 2 else 1)
                # Erta ogohlantirish signallari (faqat aktiv talabalar — kirmagan/noaktiv sabablari bilan ikki marta sanalmasin)
                if state == "aktiv":
                    ia = a.get("ia") or 0
                    if irr_ok and ia < pol["irregular_min_active"]:
                        add("notekis", f"Notekis faollik: oxirgi {pol['irregular_weeks']} haftadan {ia} tasida kirgan", 1)
                    if early:
                        el, etk = a.get("el") or 0, _pct(a.get("etd") or 0, a.get("ett") or 0)
                        if el < pol["early_min_logins"] or (etk is not None and etk < pol["tasks_min_pct"]):
                            add("erta_sust", f"Semestr boshida sust: birinchi {EARLY_WEEKS} haftada {el} marta kirgan"
                                             + (f", topshiriqlar {a.get('etd') or 0}/{a.get('ett')}" if etk is not None else ""), 1)
            if dbt: add("qarz", f"Akademik qarz: {dbt} ta fan", 2 if dbt >= 2 else 1)
            for t in of["issue"]: add("buyruq", t, 2)
            if of["pending"]: add("buyruq_jarayon", f"Imzolanmagan buyruq: {of['pending']} ta", 1)
            perf = "qarzdor" if dbt else ("xavf" if low else ("yaxshi" if n_cur else "malumot_yoq"))
            out.append({"id": s["id"], "full_name": s["full_name"], "hemis_id": s["hemis_id"], "status": s["status"], "grp": s["grp"],
                        "course": s["course"], "direction": s["direction"], "dept": s["dept"], "state": state, "last_login": a.get("last"),
                        "days": days, "logins": a.get("lg") or 0, "minutes": a.get("mins") or 0, "vc_att": a.get("va") or 0, "vc_total": a.get("vt") or 0,
                        "vc_pct": vc, "tasks_pct": tk, "oraliq_avg": cu.get("avg"), "oraliq_low": low, "debts": dbt, "perf": perf,
                        "order_issues": of["issue"], "order_pending": of["pending"], "reasons": reasons, "risk": sum(x["sev"] for x in reasons)})
        return out
    return _cached("students", 30, build)

def students_summary(rows=None) -> dict:
    rows = rows if rows is not None else student_rows()
    n = len(rows)
    cnt = lambda f: sum(1 for r in rows if f(r))
    act = [r for r in rows if r["state"] != "tatil"]
    vt = sum(r["vc_total"] for r in act); va = sum(r["vc_att"] for r in act)
    by_dir = {}
    for r in rows:
        d = by_dir.setdefault(r["direction"], {"direction": r["direction"], "n": 0, "aktiv": 0, "noaktiv": 0, "kirmagan": 0, "risk": 0, "qarzdor": 0})
        d["n"] += 1; d["risk"] += r["risk"] >= 3
        if r["state"] in ("aktiv", "noaktiv", "kirmagan"): d[r["state"]] += 1
        d["qarzdor"] += r["perf"] == "qarzdor"
    for d in by_dir.values(): d["aktiv_pct"] = _pct(d["aktiv"], d["n"])
    return {"total": n, "aktiv": cnt(lambda r: r["state"] == "aktiv"), "noaktiv": cnt(lambda r: r["state"] == "noaktiv"),
            "kirmagan": cnt(lambda r: r["state"] == "kirmagan"), "tatil": cnt(lambda r: r["state"] == "tatil"),
            "ozlashtirgan": cnt(lambda r: r["perf"] == "yaxshi"), "ozlashtirmagan": cnt(lambda r: r["perf"] in ("qarzdor", "xavf")),
            "qarzdor": cnt(lambda r: r["perf"] == "qarzdor"), "oraliq_xavf": cnt(lambda r: r["oraliq_low"] > 0),
            "vc_pct": _pct(va, vt), "vc_low": cnt(lambda r: any(x["code"] == "vk" for x in r["reasons"])),
            "buyruq_muammo": cnt(lambda r: bool(r["order_issues"])), "buyruq_jarayon": cnt(lambda r: r["order_pending"] > 0),
            "risk_high": cnt(lambda r: r["risk"] >= 4), "risk_mid": cnt(lambda r: 2 <= r["risk"] < 4),
            "by_direction": sorted(by_dir.values(), key=lambda d: (d["aktiv_pct"] or 0)),
            "reasons": _reason_counts(rows)}

def _reason_counts(rows) -> list[dict]:
    lab = {"kirmagan": "LMS'ga umuman kirmagan", "noaktiv": "Uzoq vaqt kirmagan (noaktiv)", "notekis": "Notekis faollik (haftalar bo'yicha)",
           "erta_sust": "Semestr boshida sust (birinchi 4 hafta)", "vk": "Videokonferensiyaga kam qatnashadi",
           "topshiriq": "LMS topshiriqlarini bajarmayapti", "oraliq": "Oraliq nazoratdan past ball", "qarz": "Akademik qarzdor",
           "buyruq": "Buyruq nomuvofiqligi", "buyruq_jarayon": "Buyrug'i imzolanmagan (jarayonda)"}
    c = {}
    for r in rows:
        for x in {x["code"] for x in r["reasons"]}: c[x] = c.get(x, 0) + 1
    return [{"code": k, "label": v, "n": c.get(k, 0)} for k, v in lab.items()]


# =============================================================================================
# O'quv kontenti
# =============================================================================================
def _items_base(c: Ctx | None = None, where="1=1", args=()):
    sw, sa = item_scope(c) if c else ("1=1", ())
    return db.rows(_con, f"""SELECT i.*, c.subject, c.direction, c.course, c.department_id, c.teacher_id, d.name dept, t.full_name teacher
                             FROM dl_items i JOIN dl_courses c ON c.id=i.course_id LEFT JOIN departments d ON d.id=c.department_id
                             LEFT JOIN teachers t ON t.id=c.teacher_id WHERE {sw} AND ({where})""", sa + tuple(args))

def _blank() -> dict:
    return {"plan": 0, "due": 0, "given": 0, "approved": 0, "overdue": 0, "today": 0, "soon": 0, "returned": 0, "review": 0}

def _acc(a: dict, st: str, d, today, soon):
    a["plan"] += 1
    if d and d <= today:
        a["due"] += 1
        if st in GIVEN: a["given"] += 1
    if st == "tasdiqlandi": a["approved"] += 1
    elif st == "yuklandi": a["review"] += 1
    elif st == "qaytarildi": a["returned"] += 1
    if st in OPEN_ST and d:
        if d < today: a["overdue"] += 1
        elif d == today: a["today"] += 1
        elif (d - today).days <= soon: a["soon"] += 1

def content_summary(c: Ctx | None = None) -> dict:
    """Kafedra / o'qituvchi / yo'nalish / tur kesimlari — materiallar BIR marta aylanib chiqiladi; ko'lam bo'yicha kesh (60 s,
    yozuvlarda — yuklandi, tekshirish, import, qoidalar, demo surish — invalidate())."""
    _maybe_redate()
    sw, sa = item_scope(c) if c else ("1=1", ())
    return _cached(("content", sw, sa, _today().isoformat()), 60, lambda: _content_build(c))

def _content_build(c: Ctx | None) -> dict:
    today, soon = _today(), policy()["soon_days"]
    items = _items_base(c)
    tot = _blank(); given_all = 0
    depts, teachers, dirs, kinds, tlag = {}, {}, {}, {}, {}
    for i in items:
        d, st = _d(i["due"]), i["status"]
        _acc(tot, st, d, today, soon)
        _acc(depts.setdefault((i["department_id"], i["dept"]), _blank()), st, d, today, soon)
        _acc(teachers.setdefault((i["teacher_id"], i["teacher"], i["department_id"], i["dept"]), _blank()), st, d, today, soon)
        _acc(dirs.setdefault(i["direction"], _blank()), st, d, today, soon)
        _acc(kinds.setdefault(i["kind"], _blank()), st, d, today, soon)
        given_all += st in GIVEN
        if st in OPEN_ST and d and d < today: tlag.setdefault(i["department_id"], set()).add(i["teacher_id"])
    for a in (tot, *depts.values(), *teachers.values(), *dirs.values(), *kinds.values()):
        a["pct"] = _pct(a["given"], a["due"])
    tot["plan_pct"] = _pct(given_all, tot["plan"])
    dep = [{"department_id": k[0], "name": k[1] or "—", **a, "teachers_lagging": len(tlag.get(k[0], ())), "status": _health(a["pct"], a["overdue"])}
           for k, a in depts.items()]
    tch = [{"teacher_id": k[0], "name": k[1] or "—", "department_id": k[2], "dept": k[3], **a, "status": _health(a["pct"], a["overdue"])}
           for k, a in teachers.items()]
    drs = [{"direction": k, **a, "status": _health(a["pct"], a["overdue"])} for k, a in dirs.items()]
    knd = [{"kind": k, "label": KINDS.get(k, k), **a} for k, a in kinds.items()]
    return {"total": tot, "departments": sorted(dep, key=lambda x: (x["pct"] if x["pct"] is not None else 101, -x["overdue"])),
            "teachers": sorted(tch, key=lambda x: (-x["overdue"], x["pct"] if x["pct"] is not None else 101)),
            "directions": sorted(drs, key=lambda x: (x["pct"] if x["pct"] is not None else 101)), "kinds": knd}

def _health(pct, overdue):
    if pct is None: return "none"
    if pct >= 95: return "ok"
    if pct >= 85: return "warn"
    return "bad"


# =============================================================================================
# Hafta
# =============================================================================================
def week_view(c: Ctx) -> dict:
    today = _today(); mon = _monday(today); sun = mon + dt.timedelta(days=6)
    items = _items_base(c, "i.due BETWEEN ? AND ?", (mon.isoformat(), (sun + dt.timedelta(days=7)).isoformat()))
    def pack(i):
        d = _d(i["due"])
        return {"id": i["id"], "subject": i["subject"], "direction": i["direction"], "course": i["course"], "topic_no": i["topic_no"], "topic": i["topic"],
                "kind": i["kind"], "kind_label": KINDS.get(i["kind"]), "due": i["due"], "status": i["status"], "dept": i["dept"],
                "teacher": _short(i["teacher"]), "days": (d - today).days if d else None}
    this_week = [pack(i) for i in items if _d(i["due"]) <= sun]
    nxt = [pack(i) for i in items if _d(i["due"]) > sun]
    open_this = [x for x in this_week if x["status"] in OPEN_ST]
    out = {"monday": mon.isoformat(), "sunday": sun.isoformat(), "today": today.isoformat(),
           "content": {"this_week": len(this_week), "open": len(open_this), "today_open": sum(1 for x in open_this if x["days"] == 0),
                       "overdue_this_week": sum(1 for x in open_this if (x["days"] or 0) < 0),
                       "items": sorted(open_this, key=lambda x: (x["days"], x["dept"] or "", x["subject"]))[:200],
                       "next_week_open": sum(1 for x in nxt if x["status"] in OPEN_ST)}}
    if c.role.key in DEPT + LEAD:
        rows = student_rows(); pol = policy()
        lo, hi = pol["inactive_days"], pol["inactive_days"] + 7
        newly = [r for r in rows if r["state"] == "noaktiv" and r["days"] is not None and lo < r["days"] <= hi]
        wk = db.one(_con, "SELECT SUM(vc_att) va, SUM(vc_total) vt, SUM(logins) lg, COUNT(DISTINCT CASE WHEN logins>0 THEN student_id END) act FROM dl_activity WHERE week=?",
                    (mon.isoformat(),)) or {}
        prev = db.one(_con, "SELECT COUNT(DISTINCT CASE WHEN logins>0 THEN student_id END) act FROM dl_activity WHERE week=?",
                      ((mon - dt.timedelta(weeks=1)).isoformat(),)) or {}
        out["students"] = {"newly_inactive": len(newly), "active_this_week": wk.get("act") or 0, "active_prev_week": prev.get("act") or 0,
                           "vc_pct_week": _pct(wk.get("va") or 0, wk.get("vt") or 0),
                           "newly_list": [_student_public(r) for r in sorted(newly, key=lambda r: -r["days"])[:50]] if names_ok(c) else []}
    return out

def _student_public(r) -> dict:
    return {k: r[k] for k in ("id", "full_name", "hemis_id", "grp", "course", "direction", "state", "last_login", "days", "vc_pct", "tasks_pct",
                              "oraliq_avg", "oraliq_low", "debts", "order_issues", "order_pending", "reasons", "risk", "status")}


# =============================================================================================
# AI xulosa
# =============================================================================================
def _facts(c: Ctx) -> dict:
    s = students_summary(); k = content_summary(None); w = week_view(c)
    t = k["total"]
    return {
        "sana": _today().isoformat(),
        "talabalar": {"jami": s["total"], "aktiv": s["aktiv"], "noaktiv": s["noaktiv"], "umuman_kirmagan": s["kirmagan"], "akademik_tatilda": s["tatil"],
                      "aktiv_foiz": _pct(s["aktiv"], s["total"] - s["tatil"]), "ozlashtirgan": s["ozlashtirgan"], "ozlashtirmagan": s["ozlashtirmagan"],
                      "akademik_qarzdor": s["qarzdor"], "oraliqdan_past": s["oraliq_xavf"], "videokonferensiya_qatnashish_foiz": s["vc_pct"],
                      "buyruq_nomuvofiq": s["buyruq_muammo"], "buyruq_imzolanmagan": s["buyruq_jarayon"],
                      "xavf_yuqori": s["risk_high"], "xavf_orta": s["risk_mid"],
                      "eng_past_aktivlik_yonalishlar": [{"yonalish": d["direction"], "aktiv_foiz": d["aktiv_pct"], "talaba": d["n"]} for d in s["by_direction"][:3]]},
        "kontent": {"reja_jami": t["plan"], "muddati_kelgan": t["due"], "berilgan": t["given"], "berilgan_foiz": t["pct"], "muddati_otgan": t["overdue"],
                    "bugun_tugaydi": t["today"], "yaqin_kunlarda": t["soon"], "qaytarilgan": t["returned"], "tekshiruvda": t["review"],
                    "kafedralar": [{"kafedra": d["name"], "berilgan_foiz": d["pct"], "muddati_otgan": d["overdue"], "ortda_oqituvchilar": d["teachers_lagging"]}
                                   for d in k["departments"]],
                    "material_turlari": [{"tur": x["label"], "berilgan_foiz": x["pct"], "muddati_otgan": x["overdue"]} for x in k["kinds"]]},
        "hafta": {"bu_hafta_materiallar": w["content"]["this_week"], "bu_hafta_ochiq": w["content"]["open"], "bugun_ochiq": w["content"]["today_open"],
                  "keyingi_hafta_ochiq": w["content"]["next_week_open"],
                  **({"yangi_noaktiv_talabalar": w["students"]["newly_inactive"], "bu_hafta_kirgan_talabalar": w["students"]["active_this_week"],
                      "otgan_hafta_kirgan_talabalar": w["students"]["active_prev_week"]} if "students" in w else {})},
    }

def _numbers(obj, pct: bool = False) -> set:
    """Faktlardagi raqamlar. Foiz maydonlari (kalitida «foiz») qiymatlari qo'shimcha «p:<son>» bilan belgilanadi —
    matndagi «N%» faqat haqiqiy foiz bilan solishtiriladi (boshqa ma'nodagi 12 soni «12%» ni oqlamaydi)."""
    out = set()
    if isinstance(obj, dict): [out.update(_numbers(v, pct or "foiz" in str(k))) for k, v in obj.items()]
    elif isinstance(obj, list): [out.update(_numbers(v, pct)) for v in obj]
    elif isinstance(obj, bool): pass
    elif isinstance(obj, (int, float)):
        out.add(round(float(obj), 1)); out.add(float(round(obj)))
        if pct: out.add(f"p:{round(float(obj), 1)}")
    elif isinstance(obj, str):
        for m in re.findall(r"\d+(?:[.,]\d+)?", obj): out.add(round(float(m.replace(",", ".")), 1))
        for m in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", obj): out.add("d:" + m)     # sanalar — butunligicha (_verify)
    return out

_PCT_RE = re.compile(r"(\d[\d ]*(?:[.,]\d+)?)\s*%")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b")
_LABEL_RE = re.compile(r"\b[1-6]\s*-\s*(?:kurs|semestr|bosqich)\w*", re.I)    # «2-kurs», «1-semestr» — yorliq, statistika emas
SMALL_OK = 7                                                                     # tavsiyalarda: «3 kun ichida», «2 hafta» kabi

def _verify(text: str, known: set, lenient: bool = False) -> tuple[str, list]:
    """Faktlarda yo'q raqamli jumlalarni olib tashlaydi (AI raqam to'qimasin).
    Qat'iy rejim (xulosa, asosiy, xavflar): har bir raqam faktlarda bo'lishi shart — «5 ta kafedra to'xtagan» kabi kichik to'qima ham o'tmaydi.
    Yumshoq rejim (faqat tavsiyalar): ≤ SMALL_OK kichik sonlarga ruxsat («3 kun ichida»). Sana (faktlardagi sana bilan aynan bir xil bo'lsa) va
    «N-kurs/semestr» yorliqlari ikkala rejimda ham raqam sifatida sanalmaydi."""
    kept, dropped = [], []
    ok = lambda n: n in known or float(round(n)) in known or (lenient and n <= SMALL_OK)
    for sent in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
        if not sent: continue
        bad = False
        for m in _DATE_RE.findall(sent):
            p = [int(x) for x in re.split(r"[-.]", m)]
            y, mo, dd = (p[0], p[1], p[2]) if p[0] > 31 else (p[2], p[1], p[0])
            if f"d:{y:04d}-{mo:02d}-{dd:02d}" not in known: bad = True
        rest = _LABEL_RE.sub(" ", _DATE_RE.sub(" ", sent))
        for m in _PCT_RE.findall(rest):                     # «N%» — faqat faktlardagi foiz qiymati bilan (lenient'da ham)
            if f"p:{round(float(m.replace(',', '.').replace(' ', '')), 1)}" not in known: bad = True
        nums = [round(float(m.replace(",", ".").replace(" ", "")), 1) for m in re.findall(r"\d[\d ]*(?:[.,]\d+)?", rest) if m.strip()]
        bad = bad or any(not ok(n) for n in nums)
        (dropped if bad else kept).append(sent)
    return " ".join(kept).strip(), dropped

AI_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["xulosa", "asosiy", "xavflar", "tavsiyalar"],
             "properties": {"xulosa": {"type": "string"}, "asosiy": {"type": "array", "items": {"type": "string"}},
                            "xavflar": {"type": "array", "items": {"type": "string"}}, "tavsiyalar": {"type": "array", "items": {"type": "string"}}}}
AI_SYSTEM = ("Sen ISFT institutining Masofaviy ta'lim bo'limi uchun tahlilchisan. Senga faqat jamlangan raqamlar (JSON) beriladi. "
             "Vazifa: bo'lim boshlig'i va rahbariyat uchun o'zbek tilida (lotin) qisqa, aniq xulosa yozish. QOIDALAR: "
             "1) Faqat berilgan raqamlardan foydalan, yangi raqam, foiz yoki taxmin qo'shma; raqamni hisoblab chiqarma — bor raqamni keltir. "
             "2) Shaxslar haqida yozma (ismlar berilmagan). 3) xulosa — 3–4 jumla; asosiy — 3–5 ta fakt; xavflar — eng muhim 3–4 ta; "
             "tavsiyalar — 3–5 ta amaliy qadam (kim nima qiladi: bo'lim, kafedra, tyutor, registrator). 4) Rasmiy, lekin sodda uslub.")

def _digest(facts: dict) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]

def _ai_result(facts: dict, call=None) -> tuple[dict, str, dict, bool]:
    """(ma'lumot, dvigatel, tokenlar, keshlash_mumkinmi). call — AI chaqiruvi (facts → (data, usage)); None — kalit yo'q.
    Keshga faqat muvaffaqiyatli AI javobi yoki (kalit yo'q bo'lganda) qoidaga asoslangan xulosa yoziladi. AI xatosi yoki bo'sh/buzuq javob —
    qoidaga asoslangan xulosa ko'rsatiladi, lekin KESHLANMAYDI (keyingi so'rovda AI qayta uriniladi)."""
    if call is None:
        return {**_rule_summary(facts), "removed": []}, "qoida", {"in": 0, "out": 0}, True
    try:
        data, usage = call(facts)
    except Exception as e:     # AI ishlamasa — qoidaga asoslangan xulosa (ish to'xtamaydi)
        return {**_rule_summary(facts), "removed": [], "ai_error": str(e)[:200]}, "qoida", {"in": 0, "out": 0}, False
    usage = usage or {"in": 0, "out": 0}
    if not isinstance(data, dict) or not isinstance(data.get("xulosa"), str) or not all(isinstance(data.get(k, []), list) for k in ("asosiy", "xavflar", "tavsiyalar")):
        return {**_rule_summary(facts), "removed": [], "ai_error": "AI javobi noto'g'ri formatda"}, "qoida", usage, False
    known = _numbers(facts)
    out, removed = {}, []
    out["xulosa"], d0 = _verify(data["xulosa"], known); removed += d0
    for key in ("asosiy", "xavflar", "tavsiyalar"):
        keep = []
        for line in data.get(key) or []:
            if not isinstance(line, str): continue
            t, d1 = _verify(line, known, lenient=key == "tavsiyalar")
            if t and not d1: keep.append(t)
            elif d1 or line.strip(): removed += d1 or [line]
        out[key] = keep
    if not out["xulosa"] or not (out["asosiy"] or out["xavflar"] or out["tavsiyalar"]):
        why = "AI javobi bo'sh" if not removed else f"AI javobidagi {len(removed)} ta jumlada faktlarda yo'q raqam bor"
        return {**_rule_summary(facts), "removed": removed, "ai_error": why}, "qoida", usage, False
    out["removed"] = removed
    return out, "claude", usage, True

def ai_summary(c: Ctx, force=False) -> dict:
    facts = _facts(c)
    digest = _digest(facts)
    from . import claude_client as CC
    key = CC.has_key()
    if not force:
        # kalit bor bo'lsa — faqat AI xulosasi qaytariladi (kalit qo'shilgunga qadar saqlangan qoidaviy xulosa uni to'smasin)
        hit = db.one(_con, "SELECT * FROM dl_ai WHERE digest=?" + (" AND engine='claude'" if key else "") + " ORDER BY id DESC LIMIT 1", (digest,))
        if hit:
            return {**json.loads(hit["data"]), "cached": True, "ts": hit["ts"], "engine": hit["engine"], "facts": facts}
    call = None
    if key:
        call = lambda f: CC.call_json(model=os.getenv("ISFT_CORE_DL_MODEL", "claude-opus-5-5"), system=AI_SYSTEM,
                                      content=[{"type": "text", "text": "Faktlar (JSON):\n" + json.dumps(f, ensure_ascii=False, indent=1)}],
                                      schema=AI_SCHEMA, max_tokens=3000, effort="low", timeout=120, what="xulosa")
    data, engine, usage, cacheable = _ai_result(facts, call)
    ts = _iso(_now())
    if cacheable:
        _con.execute("INSERT INTO dl_ai(ts,user_id,digest,engine,data,tokens_in,tokens_out) VALUES(?,?,?,?,?,?,?)",
                     (ts, c.user["id"], digest, engine, json.dumps(data, ensure_ascii=False), usage.get("in", 0), usage.get("out", 0)))
        _con.commit()
    return {**data, "cached": False, "ts": ts, "engine": engine, "facts": facts}

def _n(x):
    """Son: minglik ajratuvchi — bo'sh joy (3 765), kasr — vergul (92,9)."""
    if isinstance(x, float): return f"{x:.1f}".replace(".", ",")
    return f"{x:,}".replace(",", " ") if isinstance(x, int) else str(x)

def _rule_summary(f: dict) -> dict:
    s, k, h = f["talabalar"], f["kontent"], f["hafta"]
    worst = [d for d in k["kafedralar"] if d["berilgan_foiz"] is not None][:2]
    xul = (f"Masofaviy ta'limda {_n(s['jami'])} nafar talaba: {_n(s['aktiv'])} nafari aktiv, {_n(s['noaktiv'])} nafari noaktiv, {_n(s['umuman_kirmagan'])} nafari LMS'ga umuman kirmagan. "
           f"O'quv kontenti muddati kelgan {_n(k['muddati_kelgan'])} ta materialdan {_n(k['berilgan'])} tasi berilgan ({_pf(k['berilgan_foiz'])}), {_n(k['muddati_otgan'])} tasining muddati o'tgan.")
    asosiy = [f"Akademik qarzdor talabalar: {_n(s['akademik_qarzdor'])}; oraliq nazoratdan past: {_n(s['oraliqdan_past'])}.",
              f"Videokonferensiyalarga qatnashish: {_pf(s['videokonferensiya_qatnashish_foiz'])}.",
              f"Bu hafta {_n(h['bu_hafta_materiallar'])} ta material muddati, ochiq: {_n(h['bu_hafta_ochiq'])}; bugun tugaydi: {_n(h['bugun_ochiq'])}."]
    xavf = [f"«{d['kafedra']}» kafedrasi: {_pf(d['berilgan_foiz'])} berilgan, {_n(d['muddati_otgan'])} ta muddati o'tgan." for d in worst]
    if s["buyruq_nomuvofiq"]: xavf.append(f"Buyruq nomuvofiqligi: {_n(s['buyruq_nomuvofiq'])} nafar talaba.")
    xavf.append(f"Yuqori xavfli talabalar: {_n(s['xavf_yuqori'])}.")
    tav = ["Ortda qolgan kafedralarga kafedralar jadvalidagi «Topshiriq» tugmasi orqali muddatli topshiriq yuborish.",
           "Umuman kirmagan va noaktiv talabalarni tyutor va call-markaz orqali bog'lanishga yo'naltirish.",
           "Qaytarilgan materiallar bo'yicha o'qituvchilar bilan 2 kun ichida qayta yuklashni kelishish."]
    if s["buyruq_nomuvofiq"]: tav.append("Buyruq nomuvofiqliklarini Registrator ofisi bilan solishtirib chiqish.")
    return {"xulosa": xul, "asosiy": asosiy, "xavflar": xavf, "tavsiyalar": tav}


# =============================================================================================
# Hisobot (.docx)
# =============================================================================================
def report_docx(c: Ctx) -> bytes:
    from docx import Document
    from . import brand as B
    s = students_summary(); k = content_summary(None); w = week_view(c)
    doc = Document(); B.setup(doc); B.letterhead(doc)
    today = _today()
    B.title(doc, "MASOFAVIY TA'LIM: MONITORING HISOBOTI", f"{today.strftime('%d.%m.%Y')} holatiga · {w['monday'][8:10]}.{w['monday'][5:7]}–{w['sunday'][8:10]}.{w['sunday'][5:7]} haftasi")
    B.para(doc, "1. Talabalar", indent=False, bold=True)
    act_base = s["total"] - s["tatil"]
    B.table(doc, ["Ko'rsatkich", "Soni", "Ulushi"], [
        ("Jami masofaviy ta'lim talabalari", s["total"], "100%"),
        ("LMS'da aktiv", s["aktiv"], _pf(_pct(s['aktiv'], act_base))),
        ("Noaktiv (uzoq vaqt kirmagan)", s["noaktiv"], _pf(_pct(s['noaktiv'], act_base))),
        ("LMS'ga umuman kirmagan", s["kirmagan"], _pf(_pct(s['kirmagan'], act_base))),
        ("Akademik ta'tilda", s["tatil"], ""),
        ("O'zlashtirgan (qarzsiz, oraliq ≥ 12)", s["ozlashtirgan"], _pf(_pct(s['ozlashtirgan'], s['total']))),
        ("Akademik qarzdor", s["qarzdor"], _pf(_pct(s['qarzdor'], s['total']))),
        ("Videokonferensiyalarga qatnashish", "", _pf(s["vc_pct"])),
        ("Buyruq nomuvofiqligi / imzolanmagan buyruq", f"{s['buyruq_muammo']} / {s['buyruq_jarayon']}", ""),
        ("Xavf ostida (yuqori / o'rta)", f"{s['risk_high']} / {s['risk_mid']}", ""),
    ], widths=[10, 3, 3])
    B.para(doc, "2. O'quv kontenti (muddati kelgan materiallar bo'yicha)", indent=False, bold=True)
    t = k["total"]
    B.para(doc, f"Semestr rejasi: {t['plan']} ta material. Muddati kelgan: {t['due']}, berilgan: {t['given']} ({_pf(t['pct'])}). "
                f"Muddati o'tgan: {t['overdue']}, bugun tugaydi: {t['today']}, yaqin {policy()['soon_days']} kunda: {t['soon']}. "
                f"Tekshiruvda: {t['review']}, qaytarilgan: {t['returned']}.", indent=False, size=10.5)
    B.table(doc, ["Kafedra", "Muddati kelgan", "Berilgan", "%", "Muddati o'tgan", "Ortda o'qituvchi"],
            [(d["name"], d["due"], d["given"], "—" if d["pct"] is None else _n(d["pct"]), d["overdue"], d["teachers_lagging"]) for d in k["departments"]], widths=[6.5, 2.2, 2, 1.6, 2.2, 2.3], size=9)
    B.para(doc, "3. Xavf ostidagilar — sabablar kesimida", indent=False, bold=True)
    B.table(doc, ["Sabab", "Talabalar"], [(r["label"], r["n"]) for r in s["reasons"]], widths=[11, 4], size=9.5)
    if names_ok(c):
        top = sorted((r for r in student_rows() if r["risk"] >= 4), key=lambda r: -r["risk"])[:25]
        if top:
            B.para(doc, "Eng yuqori xavfli talabalar (25 tagacha):", indent=False, size=10)
            B.table(doc, ["F.I.Sh.", "Guruh", "Sabablar"], [(r["full_name"], r["grp"], "; ".join(x["label"] for x in r["reasons"])) for r in top],
                    widths=[5, 2.5, 9], size=8.5)
    else:
        B.para(doc, "Rahbariyat nusxasi: talabalar ism-shariflari keltirilmagan (individual ro'yxat — Masofaviy ta'lim bo'limida).", indent=False, size=9.5)
    B.para(doc, "4. Bu hafta", indent=False, bold=True)
    wc = w["content"]
    B.para(doc, f"Bu hafta muddati tugaydigan materiallar: {wc['this_week']}, ochiq: {wc['open']} (bugun: {wc['today_open']}). Keyingi hafta ochiq: {wc['next_week_open']}."
                + (f" Bu hafta yangi noaktiv bo'lgan talabalar: {w['students']['newly_inactive']}." if "students" in w else ""), indent=False, size=10.5)
    # Xulosa faqat JORIY faktlarga mos bo'lsa (digest) — eski xulosa «tekshirilgan» deb hisobotga tushmasin
    hit = db.one(_con, "SELECT data, engine, ts FROM dl_ai WHERE digest=? ORDER BY engine='claude' DESC, id DESC LIMIT 1", (_digest(_facts(c)),))
    if hit:
        d = json.loads(hit["data"])
        B.para(doc, "5. Xulosa" + (" (AI, raqamlar tizimdan tekshirilgan)" if hit["engine"] == "claude" else " (qoidalar asosida)"), indent=False, bold=True)
        B.para(doc, d.get("xulosa", ""), size=10.5)
        for line in d.get("tavsiyalar", [])[:5]: B.para(doc, "• " + line, indent=False, size=10)
    else:
        last = db.one(_con, "SELECT ts FROM dl_ai ORDER BY id DESC LIMIT 1")
        if last:
            B.para(doc, f"5. Xulosa: oxirgi xulosa {_d(last['ts']).strftime('%d.%m.%Y')} holatiga tayyorlangan, ma'lumot o'shandan beri o'zgargan — "
                        "hisobotga kiritilmadi. Yangi xulosa uchun «Umumiy» bo'limida «Xulosa tayyorlash»ni bosing.", indent=False, size=9.5)
    B.para(doc, "Manba: ISFT Core (baholar, buyruqlar), LMS va videokonferensiya eksporti" + (" — DEMO ma'lumot" if _source() == "demo" else "") + ".", indent=False, size=8.5)
    B.signature(doc, "Masofaviy ta'lim bo'limi boshlig'i", _short(db.one(_con, "SELECT full_name FROM users WHERE role=? ORDER BY id LIMIT 1", (HEAD,))["full_name"])
                if db.one(_con, "SELECT 1 x FROM users WHERE role=?", (HEAD,)) else "")
    bio = io.BytesIO(); doc.save(bio); return bio.getvalue()

def _source() -> str:
    r = db.one(_con, "SELECT v FROM dl_meta WHERE k='source'")
    return r["v"] if r else "demo"


# =============================================================================================
# Import (CSV / XLSX): LMS faolligi va kontent nazorat varag'i
# =============================================================================================
TEMPLATES = {
    "activity": ["hemis_id", "hafta", "kirishlar", "daqiqa", "korilgan_material", "vk_qatnashgan", "vk_jami", "topshiriq_bajarilgan", "topshiriq_jami", "oxirgi_kirish"],
    "content": ["fan", "yonalish", "kurs", "mavzu_no", "tur", "holat", "havola", "muddat"],
}
TEMPLATE_EXAMPLE = {
    "activity": ["301234567890", "2026-11-02", "4", "120", "9", "2", "2", "2", "2", "2026-11-06 19:40"],
    "content": ["Mikroiqtisodiyot", "Iqtisodiyot", "1", "5", "video", "yuklandi", "https://youtu.be/...", "2026-09-27"],
}
KIND_ALIASES = {"maruza": "maruza", "ma'ruza": "maruza", "ma'ruza matni": "maruza", "matn": "maruza", "taqdimot": "taqdimot", "slayd": "taqdimot",
                "ppt": "taqdimot", "video": "video", "videodars": "video", "test": "test"}
ST_ALIASES = {"yuklandi": "yuklandi", "yuklangan": "yuklandi", "berildi": "yuklandi", "ha": "yuklandi", "bor": "yuklandi",
              "tasdiqlandi": "tasdiqlandi", "tasdiqlangan": "tasdiqlandi", "qaytarildi": "qaytarildi", "kutilmoqda": "kutilmoqda",
              "yo'q": "kutilmoqda", "yoq": "kutilmoqda", "yuklanmagan": "kutilmoqda", "": None}

def _read_table(raw: bytes, name: str) -> list[dict]:
    if len(raw) > 8 * 1024 * 1024: raise HTTPException(413, "Fayl 8 MB dan katta")
    if name.lower().endswith(".xlsx"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            it = ws.iter_rows(values_only=True)
            head = [str(h or "").strip().lower() for h in next(it)]
            return [{head[i]: ("" if v is None else str(v)).strip() for i, v in enumerate(r) if i < len(head)} for r in it if any(v not in (None, "") for v in r)]
        except HTTPException: raise
        except Exception as e:
            raise HTTPException(400, f"XLSX faylni o'qib bo'lmadi: {str(e)[:120]}")
    try: txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError: txt = raw.decode("cp1251", errors="replace")
    dialect = ";" if txt.count(";") > txt.count(",") else ","
    rd = csv.DictReader(io.StringIO(txt), delimiter=dialect)
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rd]

def _int(v, default=0):
    try: return int(float(str(v).replace(",", ".").strip()))
    except (TypeError, ValueError): return default

def import_activity(c: Ctx, raw: bytes, name: str) -> dict:
    rows = _read_table(raw, name)
    need = {"hemis_id", "hafta"}
    if rows and not need <= set(rows[0]): raise HTTPException(400, f"Ustunlar yetishmaydi: {', '.join(sorted(need - set(rows[0])))}. Namuna faylni yuklab oling.")
    ids = {r["hemis_id"]: r["id"] for r in db.rows(_con, "SELECT id, hemis_id FROM students WHERE study_form='masofaviy'")}
    ok, skipped, errs = 0, 0, []
    batch = []
    for n, r in enumerate(rows, 2):
        sid = ids.get(r.get("hemis_id", ""))
        w = _d(r.get("hafta"))
        if not sid or not w:
            skipped += 1
            if len(errs) < 20: errs.append(f"{n}-qator: " + ("HEMIS ID masofaviy talabalar orasida topilmadi" if not sid else "hafta sanasi noto'g'ri"))
            continue
        last = (r.get("oxirgi_kirish") or "").replace(" ", "T")[:19] or None
        if last and not _d(last): last = None
        batch.append((sid, _monday(w).isoformat(), _int(r.get("kirishlar")), _int(r.get("daqiqa")), _int(r.get("korilgan_material")),
                      _int(r.get("vk_qatnashgan")), _int(r.get("vk_jami")), _int(r.get("topshiriq_bajarilgan")), _int(r.get("topshiriq_jami")), last, "import"))
        ok += 1
    if batch:
        _con.executemany("""INSERT OR REPLACE INTO dl_activity(student_id,week,logins,minutes,views,vc_att,vc_total,tasks_done,tasks_total,last_login,src)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", batch)
        _con.execute("INSERT OR REPLACE INTO dl_meta(k,v) VALUES('source','import')")
    _log_import(c, "activity", name, len(rows), ok, skipped, "; ".join(errs[:3]))
    invalidate()
    return {"rows": len(rows), "ok": ok, "skipped": skipped, "errors": errs}

def import_content(c: Ctx, raw: bytes, name: str) -> dict:
    rows = _read_table(raw, name)
    need = {"fan", "yonalish", "kurs", "mavzu_no", "tur"}
    if rows and not need <= set(rows[0]): raise HTTPException(400, f"Ustunlar yetishmaydi: {', '.join(sorted(need - set(rows[0])))}. Namuna faylni yuklab oling.")
    courses = {(r["subject"].lower(), r["direction"].lower(), r["course"]): r["id"] for r in db.rows(_con, "SELECT id, subject, direction, course FROM dl_courses")}
    ok, skipped, errs = 0, 0, []
    now = _iso(_now())
    for n, r in enumerate(rows, 2):
        cid = courses.get((r.get("fan", "").lower(), r.get("yonalish", "").lower(), _int(r.get("kurs"))))
        kind = KIND_ALIASES.get(r.get("tur", "").lower())
        no = _int(r.get("mavzu_no"))
        st = ST_ALIASES.get(r.get("holat", "").lower(), "x")
        url = (r.get("havola") or "").strip()
        why = ("fan/yo'nalish/kurs rejada topilmadi" if not cid else "material turi noma'lum" if not kind else
               "mavzu raqami noto'g'ri" if not 1 <= no <= TOPICS_PER_COURSE else "holat noma'lum" if st == "x" else
               "havola http:// yoki https:// bilan boshlanishi kerak" if url and (len(url) > 500 or not URL_RE.match(url)) else None)   # XSS: javascript: va h.k.
        if why:
            skipped += 1
            if len(errs) < 20: errs.append(f"{n}-qator: {why}")
            continue
        it = db.one(_con, "SELECT * FROM dl_items WHERE course_id=? AND topic_no=? AND kind=?", (cid, no, kind))
        if not it:
            skipped += 1
            if len(errs) < 20: errs.append(f"{n}-qator: material rejada topilmadi")
            continue
        upd = {}
        if st and st != it["status"]:
            upd["status"] = st
            if st in GIVEN and not it["uploaded_at"]: upd["uploaded_at"] = now
        if url: upd["url"] = url
        if _d(r.get("muddat")): upd["due"] = _d(r["muddat"]).isoformat()
        if upd:
            upd["src"] = "import"
            _con.execute(f"UPDATE dl_items SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), it["id"]))
            _log(it["id"], c, "import", ", ".join(f"{k}={v}" for k, v in upd.items() if k != "src")[:200])
        ok += 1
    _log_import(c, "content", name, len(rows), ok, skipped, "; ".join(errs[:3]))
    _con.commit(); invalidate()
    return {"rows": len(rows), "ok": ok, "skipped": skipped, "errors": errs}

def _log_import(c, kind, name, rows, ok, skipped, note):
    _con.execute("INSERT INTO dl_imports(kind,ts,user_id,user_name,filename,rows,ok,skipped,note) VALUES(?,?,?,?,?,?,?,?,?)",
                 (kind, _iso(_now()), c.user["id"], c.user["full_name"], name[:160], rows, ok, skipped, note[:500]))
    _con.commit()

def _log(item_id, c: Ctx, action, note=""):
    _con.execute("INSERT INTO dl_log(item_id,ts,user_id,user_name,action,note) VALUES(?,?,?,?,?,?)",
                 (item_id, _iso(_now()), c.user["id"], c.user["full_name"], action, note[:500]))


# =============================================================================================
# «Mening vazifalarim» va bosh sahifa (app/pending.py)
# =============================================================================================
# Havola yorlig'i filtrlarni ham olib yuradi: "yorliq:kalit=qiymat,..." — masofaviy.js renderMasofaviy() uni o'qiydi.
# (pending.py faqat view/tab/href ni uzatadi, extras.js openLink esa tab'ni DL.tab ga yozadi.)
_FLT0 = "department_id=0,teacher_id=0,direction=,kind=,q="
TAB_REVIEW = f"kontent:view=materiallar,due=,status=yuklandi,{_FLT0}"
TAB_TODAY = f"kontent:view=materiallar,due=today,status=,{_FLT0}"
TAB_MINE = f"kontent:view=materiallar,due=overdue,status=,{_FLT0}"

def pending(c: Ctx) -> list[dict]:
    k = c.role.key
    today = _today().isoformat()
    out = []
    try:
        if k in DEPT:
            r = db.one(_con, "SELECT COUNT(*) n FROM dl_items WHERE status='yuklandi'")
            if r and r["n"]:
                out.append({"id": "review", "kind": "ish", "title": f"Masofaviy ta'lim: tekshiruvni kutayotgan materiallar — {r['n']} ta",
                            "sub": "o'qituvchilar yuklagan, tasdiqlash yoki qaytarish kerak", "view": "masofaviy", "tab": TAB_REVIEW})
            r = db.one(_con, "SELECT COUNT(*) n FROM dl_items WHERE status IN ('kutilmoqda','qaytarildi') AND due=?", (today,))
            if r and r["n"]:
                out.append({"id": "today", "kind": "ish", "title": f"Bugun muddati tugaydigan materiallar — {r['n']} ta", "sub": "hali yuklanmagan",
                            "due": today, "view": "masofaviy", "tab": TAB_TODAY})
        elif k == TEACH and _teacher_id(c):
            r = db.one(_con, """SELECT COUNT(*) n, MIN(i.due) d FROM dl_items i JOIN dl_courses c ON c.id=i.course_id WHERE c.teacher_id=?
                                AND i.status IN ('kutilmoqda','qaytarildi') AND i.due<=?""", (int(_teacher_id(c)), today))
            if r and r["n"]:
                out.append({"id": "mine", "kind": "ish", "title": f"Masofaviy ta'lim: LMS'ga yuklanmagan materiallaringiz — {r['n']} ta",
                            "sub": f"eng eskisining muddati {str(r['d'])[:10]}", "due": r["d"], "view": "masofaviy", "tab": TAB_MINE})
    except Exception as e:
        print("masofaviy.pending:", repr(e))
    return out

def bugun(c: Ctx) -> list[dict]:
    """Bosh sahifa ko'rsatkichlari (bo'lim va rahbariyat)."""
    s = students_summary(); t = content_summary(None)["total"]
    tone = lambda bad: "bad" if bad else "good"
    return [{"label": "Aktiv talabalar", "value": s["aktiv"], "sub": f"{s['total']} dan · noaktiv {s['noaktiv']}, kirmagan {s['kirmagan']}", "tone": "",
             "link": {"view": "masofaviy", "tab": "talabalar"}},
            {"label": "Kontent berilgan", "value": _pf(t["pct"]), "sub": f"muddati o'tgan: {t['overdue']}", "tone": tone(t["overdue"]),
             "link": {"view": "masofaviy", "tab": "kontent"}},
            {"label": "Bugun muddati", "value": t["today"], "sub": "yuklanmagan material", "tone": "warn" if t["today"] else "good",
             "link": {"view": "masofaviy", "tab": TAB_TODAY}},
            {"label": "Xavf ostida", "value": s["risk_high"], "sub": "yuqori xavfli talaba", "tone": tone(s["risk_high"]),
             "link": {"view": "masofaviy", "tab": "xavf"}}]


# =============================================================================================
# API
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi")
    k = c.role.key
    last = {r["kind"]: dict(r) for r in db.rows(_con, "SELECT kind, MAX(ts) ts, user_name, filename, ok, skipped FROM dl_imports GROUP BY kind")}
    from . import claude_client as CC
    tabs = (["umumiy", "talabalar", "kontent", "xavf", "hafta", "import"] if k in DEPT else
            ["umumiy", "kontent", "xavf", "hafta"] if k in LEAD else ["kontent", "hafta"])
    return {"role": k, "tabs": tabs, "names": names_ok(c), "today": _today().isoformat(), "policy": policy(),
            "policy_help": {k2: h for k2, _, h in POLICY}, "kinds": KINDS, "item_status": ITEM_ST, "source": _source(), "imports": last,
            "ai": "claude" if CC.has_key() else "qoida",
            "caps": {"review": k in DEPT, "remind": k == HEAD, "import": k in DEPT, "upload": k == TEACH, "policy": k == HEAD,
                     "report": k in DEPT + LEAD, "ai": k in DEPT + LEAD},
            "scope": ("O'z kafedrangiz materiallari" if k == KAF else "O'z materiallaringiz" if k == TEACH else
                      "Jamlangan ko'rinish (talaba ismlarisiz)" if k in LEAD else "Masofaviy ta'lim — to'liq")}

@router.get(P + "/overview")
def api_overview(request: Request):
    c = C(request); guard(c, "umumiy holat", DEPT + LEAD)
    s = students_summary()
    return {"students": s, "content": content_summary(None), "week": week_view(c), "source": _source()}

@router.get(P + "/students")
def api_students(request: Request, state: str = "", reason: str = "", direction: str = "", course: int = 0, q: str = "",
                 sort: str = "risk", offset: int = 0, limit: int = 50):
    c = C(request); guard(c, "talabalar ro'yxati", DEPT, f"{state}/{reason}/{q[:30]}")
    rows = student_rows()
    if state: rows = [r for r in rows if r["state"] == state]
    if reason: rows = [r for r in rows if any(x["code"] == reason for x in r["reasons"])]
    if direction: rows = [r for r in rows if r["direction"] == direction]
    if course: rows = [r for r in rows if r["course"] == course]
    if q:
        ql = q.lower().strip()
        rows = [r for r in rows if ql in (r["full_name"] or "").lower() or ql in (r["hemis_id"] or "") or ql in (r["grp"] or "").lower()]
    key = {"risk": lambda r: (-r["risk"], r["full_name"]), "days": lambda r: (-(r["days"] if r["days"] is not None else 10 ** 4), r["full_name"]),
           "name": lambda r: r["full_name"], "vc": lambda r: (r["vc_pct"] if r["vc_pct"] is not None else -1, r["full_name"])}.get(sort)
    rows = sorted(rows, key=key or (lambda r: (-r["risk"], r["full_name"])))
    limit = max(1, min(200, limit))
    return {"total": len(rows), "items": [_student_public(r) for r in rows[offset:offset + limit]],
            "directions": sorted({r["direction"] for r in student_rows()})}

@router.get(P + "/students/{sid}")
def api_student(sid: int, request: Request):
    c = C(request); guard(c, "talaba kartasi", DEPT, str(sid))
    r = next((x for x in student_rows() if x["id"] == sid), None)
    if not r: raise HTTPException(404, "Masofaviy ta'lim talabasi topilmadi")
    weeks = db.rows(_con, "SELECT week, logins, minutes, views, vc_att, vc_total, tasks_done, tasks_total, last_login, src FROM dl_activity WHERE student_id=? ORDER BY week", (sid,))
    grades = db.rows(_con, f"SELECT subject, oraliq FROM grades WHERE student_id=? AND semester={AR.CURRENT_SEMESTER} ORDER BY subject", (sid,))
    debts = db.rows(_con, f"SELECT subject, score, semester FROM grades g WHERE g.student_id=? AND {AR.debt_where('g')} ORDER BY semester DESC", (sid,))
    return {**_student_public(r), "weeks": weeks, "grades": grades, "debts": debts, "oraliq_min": AR.ORALIQ_MIN}

@router.get(P + "/content")
def api_content(request: Request):
    c = C(request); guard(c, "kontent monitoringi")
    return content_summary(c)

@router.get(P + "/items")
def api_items(request: Request, department_id: int = 0, teacher_id: int = 0, direction: str = "", status: str = "", due: str = "",
              kind: str = "", q: str = "", offset: int = 0, limit: int = 100):
    c = C(request); guard(c, "materiallar ro'yxati", ALL, f"{department_id}/{teacher_id}/{due}")
    today = _today().isoformat(); soon = (_today() + dt.timedelta(days=policy()["soon_days"])).isoformat()
    w, a = ["1=1"], []
    if department_id: w.append("c.department_id=?"); a.append(department_id)
    if teacher_id: w.append("c.teacher_id=?"); a.append(teacher_id)
    if direction: w.append("c.direction=?"); a.append(direction)
    if kind in KINDS: w.append("i.kind=?"); a.append(kind)
    if status in ITEM_ST: w.append("i.status=?"); a.append(status)
    if due == "overdue": w.append("i.status IN ('kutilmoqda','qaytarildi') AND i.due<?"); a.append(today)
    elif due == "today": w.append("i.status IN ('kutilmoqda','qaytarildi') AND i.due=?"); a.append(today)
    elif due == "soon": w.append("i.status IN ('kutilmoqda','qaytarildi') AND i.due>? AND i.due<=?"); a += [today, soon]
    elif due == "past": w.append("i.due<=?"); a.append(today)
    if q: w.append("(c.subject LIKE ? OR i.topic LIKE ? OR t.full_name LIKE ?)"); a += [f"%{q}%"] * 3
    rows = _items_base(c, " AND ".join(w), a)
    rows.sort(key=lambda i: (i["due"], i["dept"] or "", i["subject"], i["topic_no"], list(KINDS).index(i["kind"]) if i["kind"] in KINDS else 9))
    limit = max(1, min(300, limit))
    out = []
    for i in rows[offset:offset + limit]:
        d = _d(i["due"])
        out.append({"id": i["id"], "subject": i["subject"], "direction": i["direction"], "course": i["course"], "dept": i["dept"],
                    "department_id": i["department_id"], "teacher": _short(i["teacher"]), "teacher_id": i["teacher_id"], "topic_no": i["topic_no"],
                    "topic": i["topic"], "kind": i["kind"], "kind_label": KINDS.get(i["kind"]), "due": i["due"], "days": (d - _today()).days if d else None,
                    "status": i["status"], "url": i["url"], "uploaded_at": i["uploaded_at"], "checked_at": i["checked_at"], "note": i["note"]})
    return {"total": len(rows), "items": out}

class UploadIn(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    note: str = Field("", max_length=300)

URL_RE = re.compile(r"^https?://[^\s<>\"']{3,}$", re.I)

@router.post(P + "/items/{iid}/upload")
def api_upload(iid: int, body: UploadIn, request: Request):
    c = C(request); guard(c, "material yuklandi deb belgilash", (TEACH,) + DEPT, f"#{iid}")
    if not URL_RE.match(body.url.strip()): raise HTTPException(400, "Havola http:// yoki https:// bilan boshlanishi kerak")
    sw, sa = item_scope(c)
    it = db.one(_con, f"SELECT i.* FROM dl_items i JOIN dl_courses c ON c.id=i.course_id WHERE i.id=? AND {sw}", (iid, *sa))
    if not it: raise HTTPException(404, "Material topilmadi yoki sizga tegishli emas")
    if it["status"] == "tasdiqlandi": raise HTTPException(409, "Material allaqachon tasdiqlangan")
    n = _con.execute("UPDATE dl_items SET status='yuklandi', url=?, uploaded_at=?, uploaded_by=?, note=NULL, src='qolda' WHERE id=? AND status!='tasdiqlandi'",
                     (body.url.strip(), _iso(_now()), c.user["id"], iid)).rowcount
    _log(iid, c, "yuklandi", body.note or body.url[:200]); _con.commit(); invalidate()
    return {"ok": bool(n), "status": "yuklandi"}

class ReviewIn(BaseModel):
    ok: bool
    note: str = Field("", max_length=500)

@router.post(P + "/items/{iid}/review")
def api_review(iid: int, body: ReviewIn, request: Request):
    c = C(request); guard(c, "materialni tekshirish", DEPT, f"#{iid} {'tasdiq' if body.ok else 'qaytarish'}")
    if not body.ok and len(body.note.strip()) < 5: raise HTTPException(400, "Qaytarish sababini yozing (kamida 5 belgi)")
    to = "tasdiqlandi" if body.ok else "qaytarildi"
    n = _con.execute("UPDATE dl_items SET status=?, checked_at=?, checked_by=?, note=? WHERE id=? AND status='yuklandi'",
                     (to, _iso(_now()), c.user["id"], None if body.ok else body.note.strip(), iid)).rowcount
    if not n:
        it = db.one(_con, "SELECT status FROM dl_items WHERE id=?", (iid,))
        if not it: raise HTTPException(404, "Material topilmadi")
        raise HTTPException(409, f"Bu holatda tekshirib bo'lmaydi: «{ITEM_ST.get(it['status'], it['status'])}»")
    _log(iid, c, to, body.note.strip()); _con.commit(); invalidate()
    return {"ok": True, "status": to}

@router.get(P + "/items/{iid}/log")
def api_item_log(iid: int, request: Request):
    c = C(request); guard(c, "material tarixi", ALL, f"#{iid}")
    sw, sa = item_scope(c)
    if not db.one(_con, f"SELECT 1 x FROM dl_items i JOIN dl_courses c ON c.id=i.course_id WHERE i.id=? AND {sw}", (iid, *sa)): raise HTTPException(404)
    return {"items": db.rows(_con, "SELECT ts, user_name, action, note FROM dl_log WHERE item_id=? ORDER BY id", (iid,))}

class RemindIn(BaseModel):
    department_id: int
    days: int = Field(3, ge=1, le=14)

@router.post(P + "/remind")
def api_remind(body: RemindIn, request: Request):
    """Kafedraga topshiriq: muddati o'tgan materiallar ro'yxati bilan (Topshiriqlar moduli — kafedra mudiri navbatiga tushadi)."""
    c = C(request); guard(c, "kafedraga topshiriq", (HEAD,), f"kafedra #{body.department_id}")   # kafedra mudiriga topshiriq — faqat bo'lim boshlig'i (rbac deny_note)
    today = _today()
    d = db.one(_con, "SELECT id, name FROM departments WHERE id=?", (body.department_id,))
    if not d: raise HTTPException(404, "Kafedra topilmadi")
    prev = db.one(_con, "SELECT task_id, ts FROM dl_reminders WHERE department_id=? AND substr(ts,1,10)=? ORDER BY id DESC LIMIT 1", (d["id"], today.isoformat()))
    if prev: return {"ok": True, "already": True, "task_id": prev["task_id"], "ts": prev["ts"]}
    items = _items_base(None, "c.department_id=? AND i.status IN ('kutilmoqda','qaytarildi') AND i.due<?", (d["id"], today.isoformat()))
    if not items: raise HTTPException(409, "Bu kafedrada muddati o'tgan material yo'q")
    by_t = {}
    for i in items: by_t.setdefault(_short(i["teacher"]) or "—", []).append(i)
    lines = []
    for t, its in sorted(by_t.items(), key=lambda x: -len(x[1])):
        lines.append(f"{t} — {len(its)} ta:")
        for i in sorted(its, key=lambda i: (i["subject"], i["topic_no"]))[:12]:
            lines.append(f"  • {i['subject']} ({i['direction']}, {i['course']}-kurs) — {i['topic_no']}-mavzu{(' «' + i['topic'] + '»') if i['topic'] else ''}, {KINDS.get(i['kind'])}"
                         f"{' (qaytarilgan: ' + i['note'] + ')' if i['status'] == 'qaytarildi' and i['note'] else ''}, muddat {i['due']}")
        if len(its) > 12: lines.append(f"  … yana {len(its) - 12} ta")
    due = (today + dt.timedelta(days=body.days)).isoformat()
    from . import directives as DIR
    tid = DIR.create_linked(_con, c.user["id"], UNIT, f"kaf{d['id']}", f"Masofaviy ta'lim: LMS'ga yuklanmagan materiallar — {len(items)} ta",
                            "Masofaviy ta'lim bo'limi kontent monitoringi bo'yicha quyidagi materiallarning muddati o'tgan. "
                            "Iltimos, LMS'ga yuklab, ISFT Core'da «Yuklandi» deb belgilang (havola bilan).\n\n" + "\n".join(lines),
                            due, "muhim", "Har bir material LMS'ga yuklangan va «Masofaviy ta'lim» bo'limida belgilangan", src=f"dl:{d['id']}")
    _con.execute("INSERT INTO dl_reminders(department_id,task_id,ts,user_id,items) VALUES(?,?,?,?,?)", (d["id"], tid, _iso(_now()), c.user["id"], len(items)))
    _con.commit()
    return {"ok": True, "already": False, "task_id": tid, "items": len(items), "teachers": len(by_t), "due": due}

@router.get(P + "/risk")
def api_risk(request: Request, kind: str = "students", limit: int = 100):
    c = C(request); guard(c, "xavf ostidagilar", DEPT + LEAD, kind)
    if kind == "content":
        today = _today().isoformat()
        rows = _items_base(None, "i.status IN ('kutilmoqda','qaytarildi') AND i.due<=?", (today,))
        by = {}
        for i in rows:
            k = (i["teacher_id"], _short(i["teacher"]), i["dept"])
            x = by.setdefault(k, {"teacher": k[1], "dept": k[2], "overdue": 0, "returned": 0, "oldest": i["due"], "subjects": set()})
            x["overdue"] += 1; x["returned"] += i["status"] == "qaytarildi"; x["oldest"] = min(x["oldest"], i["due"]); x["subjects"].add(i["subject"])
        out = sorted(({**v, "subjects": sorted(v["subjects"])[:4], "days": (_today() - _d(v["oldest"])).days} for v in by.values()), key=lambda x: (-x["overdue"], x["oldest"]))
        return {"items": out[:max(1, min(300, limit))], "total": len(out)}
    rows = sorted((r for r in student_rows() if r["risk"] >= 2), key=lambda r: (-r["risk"], r["full_name"]))
    s = students_summary()
    return {"reasons": s["reasons"], "high": s["risk_high"], "mid": s["risk_mid"], "total": len(rows),
            "items": [_student_public(r) for r in rows[:max(1, min(300, limit))]] if names_ok(c) else []}

@router.get(P + "/week")
def api_week(request: Request):
    c = C(request); guard(c, "haftalik ko'rinish")
    return week_view(c)

class AiIn(BaseModel):
    force: bool = False

@router.post(P + "/ai/summary")
def api_ai(body: AiIn, request: Request):
    c = C(request); guard(c, "AI xulosa", DEPT + LEAD, "qayta" if body.force else "")
    return ai_summary(c, body.force)

@router.get(P + "/report.docx")
def api_report(request: Request):
    c = C(request); guard(c, "hisobot (.docx)", DEPT + LEAD)
    data = report_docx(c)
    fn = f"Masofaviy_talim_monitoring_{_today().isoformat()}.docx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})

@router.get(P + "/template/{kind}.csv")
def api_template(kind: str, request: Request):
    c = C(request); guard(c, "import namunasi", DEPT, kind)
    if kind not in TEMPLATES: raise HTTPException(404)
    bio = io.StringIO(); w = csv.writer(bio, delimiter=";"); w.writerow(TEMPLATES[kind]); w.writerow(TEMPLATE_EXAMPLE[kind])
    return Response("﻿" + bio.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="masofaviy_{kind}_namuna.csv"'})

@router.post(P + "/import/{kind}")
async def api_import(kind: str, request: Request, name: str = "fayl.csv"):
    c = C(request); guard(c, "import", DEPT, f"{kind}: {name[:60]}")
    raw = await request.body()
    if not raw: raise HTTPException(400, "Fayl bo'sh")
    if not name.lower().endswith((".csv", ".xlsx", ".txt")): raise HTTPException(400, "Faqat .csv yoki .xlsx")
    if kind == "activity": return import_activity(c, raw, name)
    if kind == "content": return import_content(c, raw, name)
    raise HTTPException(404)

@router.get(P + "/imports")
def api_imports(request: Request):
    c = C(request); guard(c, "importlar tarixi", DEPT)
    return {"items": db.rows(_con, "SELECT * FROM dl_imports ORDER BY id DESC LIMIT 30"), "source": _source()}

class PolicyIn(BaseModel):
    values: dict

@router.post(P + "/policy")
def api_policy(body: PolicyIn, request: Request):
    c = C(request); guard(c, "qoidalarni o'zgartirish", (HEAD,), json.dumps(body.values)[:200])
    lim = POLICY_LIM
    changed = {}
    for k, v in body.values.items():
        if k not in lim: raise HTTPException(400, f"Noma'lum qoida: {k}")
        try: v = int(v)
        except (TypeError, ValueError): raise HTTPException(400, f"{k}: butun son kerak")
        lo, hi = lim[k]
        if not lo <= v <= hi: raise HTTPException(400, f"{k}: {lo}–{hi} oralig'ida bo'lishi kerak")
        changed[k] = v
    pol = {**policy(), **changed}
    if pol["irregular_min_active"] > pol["irregular_weeks"]:
        raise HTTPException(400, "irregular_min_active: tekshiriladigan haftalar sonidan (irregular_weeks) oshmasligi kerak")
    for k, v in changed.items():
        _con.execute("INSERT OR REPLACE INTO dl_policy(k,v) VALUES(?,?)", (k, v))
    _con.commit(); invalidate()
    return {"ok": True, "policy": policy(), "changed": changed}
