"""Reyting — «Oliy ta'lim muassasasi talabalarining o'zlashtirish ko'rsatkichlarini reyting baholash avtomatlashtirilgan tizimi».

Batafsil: docs/reyting.md. Qisqacha:
  * Reyting baholar jadvalidan (grades) hisoblanadi: semestr GPA = Σ(kredit × 5 ballik baho) / Σ kredit (app/academic_rules.py);
    kredit — o'quv rejasidan (grades.credits). Faqat YAKUNLANGAN semestrlar (yakuniy ball bor): 2025-26 bahorgi ... 2023-24 kuzgi;
    joriy semestrda faqat oraliq nazorat bor — u talaba kartasida alohida ko'rsatiladi, reytingga kirmaydi.
    Teng kelganda: o'rtacha ball (100 ballik), keyin davomat. Faqat faol talabalar; «F» (40 dan past) bo'lgan talaba ham
    reytingda qoladi, lekin «akademik qarzdor» deb belgilanadi (ta'rif — academic_rules.DEBTOR_DEF).
  * O'rinlar besh darajada: guruh, kurs (daraja + kurs), yo'nalish (daraja + yo'nalish), fakultet, institut — «37 / 1 240» va foiz.
  * Kesh (rating_cache) SQL oyna funksiyalari (RANK() OVER ...) bilan bir so'rovda quriladi (~1 s, 29 ming talaba × 2 semestr).
    Ishga tushganda kesh yo'q yoki manba ma'lumot (baholar, talabalar, o'quv dasturi kreditlari) o'zgargan bo'lsa — qayta quriladi;
    ish paytida ham 30 soniyada bir marta barmoq izi (fingerprint) tekshiriladi. Qayta seed shart emas.
  * Ruxsatlar (serverda): to'liq — Registrator ofisi, Akademik bo'lim, rektor, o'quv prorektori, Imtihon va Ma'lumotlar bazasi bo'limlari;
    ko'lamli — Sirtqi bo'lim (faqat sirtqi), kafedra mudiri (o'z kafedrasi guruhlari), tyutor (o'ziga biriktirilgan guruhlar), o'qituvchi (o'zi baholagan
    talabalar); faqat jamlangan (ism-shariflarsiz) — Kuzatuv kengashi, boshqa prorektorlar, Sifat boshqarmasi. Qolganlar — 403.
    Har bir murojaat audit jurnaliga (resurs "rating") yoziladi.
"""
import datetime as dt, io, math, threading, time
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from . import clock
from . import db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
RES = rbac.RATING

FULL = ("talabalar", "registrator_xodim", "akademik", "rektor", "prorektor_oquv", "imtihon", "malumotlar_bazasi")
SCOPED = ("sirtqi", "kafedra", "tyutor", "oqituvchi")
AGG = ("kengash", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar", "sifat")
RECOMPUTE = ("talabalar", "registrator_xodim", "akademik")
LEVELS = dict(AR.RATING_LEVELS)
PART = {"group": "semester, group_id", "course": "semester, level, course", "direction": "semester, level, direction",
        "faculty": "semester, faculty_id", "institute": "semester"}
ORDER_SQL = "gpa DESC, avg_score DESC, attendance IS NULL, attendance DESC"   # AR.RATING_ORDER bilan bir xil
FORMS = {"kunduzgi": "Kunduzgi", "sirtqi": "Sirtqi", "masofaviy": "Masofaviy"}
CHECK_EVERY = 30   # soniya: manba o'zgarganini tekshirish oralig'i
CACHE_VERSION = 3   # kesh formulasi o'zgarsa oshiriladi — eski kesh ishga tushganda avtomatik qayta quriladi (3: ko'p semestr, o'quv rejasi kreditlari)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rating_cache(student_id INT, semester INT, gpa REAL, avg_score REAL, credits INT, credits_ok INT, n_subj INT,
  n_f INT, min_score INT, group_id INT, course INT, faculty_id INT, direction TEXT, level TEXT, study_form TEXT, attendance REAL,
  r_group INT, n_group INT, r_course INT, n_course INT, r_direction INT, n_direction INT, r_faculty INT, n_faculty INT,
  r_institute INT, n_institute INT, PRIMARY KEY(student_id, semester)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_rc_sem_inst ON rating_cache(semester, r_institute);
CREATE INDEX IF NOT EXISTS ix_rc_group ON rating_cache(group_id, semester);
CREATE TABLE IF NOT EXISTS rating_credits(subject TEXT PRIMARY KEY, credits INT, source TEXT);
CREATE TABLE IF NOT EXISTS rating_meta(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS ix_grades_student ON grades(student_id, semester);
CREATE INDEX IF NOT EXISTS ix_grades_teacher ON grades(teacher_id);
"""
COLS = ("student_id, semester, gpa, avg_score, credits, credits_ok, n_subj, n_f, min_score, group_id, course, faculty_id, direction, level, "
        "study_form, attendance, " + ", ".join(f"r_{k}, n_{k}" for k, _ in AR.RATING_LEVELS))

_state = {"checked": 0.0, "fp": None}
_memo = {}

def _now(): return clock.now().replace(microsecond=0)

# =============================================================================================
# Kesh
# =============================================================================================
def _meta(con, key, default=None):
    r = con.execute("SELECT value FROM rating_meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def fingerprint(con) -> str:
    """Manba ma'lumotning barmoq izi: baholar, talabalar holati/guruhi/davomati, guruhlar kursi, o'quv dasturi kreditlari."""
    g = con.execute("""SELECT COUNT(*), TOTAL(score), TOTAL(score*semester), TOTAL((student_id*score) % 9973), TOTAL(length(subject)*score),
                       TOTAL(credits*score), TOTAL(oraliq) FROM grades""").fetchone()
    s = con.execute("""SELECT COUNT(*), TOTAL(status='faol'), TOTAL(group_id*(status='faol')), TOTAL(attendance), TOTAL((id*(status='faol')) % 9973),
                       TOTAL(length(study_form)*id % 7919) FROM students""").fetchone()
    gp = con.execute("SELECT COUNT(*), TOTAL(course*id), TOTAL(length(direction)*id % 7919) FROM groups_").fetchone()
    try: c = con.execute("SELECT COUNT(*), TOTAL(credits*length(subject)) FROM curriculum").fetchone()
    except Exception: c = (0, 0)
    rules = f"v{CACHE_VERSION}:{AR.PASS}:{AR.CREDIT_DEFAULT}:{AR.CURRENT_SEMESTER}:{AR.RATING_SEMESTER}:{AR.RATED_STATUS}:" + ",".join(f"{lo}-{g}" for lo, _, _, g, _ in AR.SCALE)
    return rules + "|" + "|".join(str(round(x, 3)) if isinstance(x, float) else str(x) for x in (*g, *s, *gp, *c))

def rebuild(con, reason="") -> dict:
    """Keshni to'liq qayta quradi (bitta tranzaksiya: o'quvchilar eski yoki yangi holatni ko'radi, yarim holatni emas)."""
    t0 = time.time()
    fp = fingerprint(con)
    # kreditlar ma'lumotnomasi (metodika uchun): fan → o'quv rejasidagi eng ko'p uchragan kredit. Hisobda baho qatoridagi kredit ishlatiladi.
    subj = {}
    for x, cr, n in con.execute("""SELECT subject, credits, COUNT(*) n FROM grades WHERE semester < ? GROUP BY subject, credits
                                   ORDER BY subject, n DESC""", (AR.CURRENT_SEMESTER,)):
        subj.setdefault(x, cr)
    con.execute("DELETE FROM rating_credits")
    con.executemany("INSERT INTO rating_credits(subject,credits,source) VALUES(?,?,?)",
                    [(x, cr or AR.CREDIT_DEFAULT, AR.CREDIT_SOURCE_SYL if cr else AR.CREDIT_SOURCE_DEFAULT) for x, cr in subj.items()])
    wins = ",\n".join(f"RANK() OVER (PARTITION BY {PART[k]} ORDER BY {ORDER_SQL}), COUNT(*) OVER (PARTITION BY {PART[k]})" for k, _ in AR.RATING_LEVELS)
    con.execute("DELETE FROM rating_cache")
    con.execute(f"""INSERT INTO rating_cache({COLS})
        WITH g AS (
          SELECT gr.student_id sid, gr.semester, gr.score, COALESCE(gr.credits, {AR.CREDIT_DEFAULT}) cr, {AR.grade5_sql('gr.score')} g5
          FROM grades gr JOIN students s ON s.id=gr.student_id AND s.status='{AR.RATED_STATUS}'
          WHERE gr.semester < {AR.CURRENT_SEMESTER} AND gr.score IS NOT NULL),
        a AS (
          SELECT sid, semester, {AR.ratio2_sql('SUM(cr*g5)', 'SUM(cr)')} gpa, {AR.ratio2_sql('SUM(score)', 'COUNT(*)')} avg_score, SUM(cr) credits,
                 SUM(CASE WHEN score >= {AR.PASS} THEN cr ELSE 0 END) credits_ok, COUNT(*) n_subj, SUM(score < {AR.PASS}) n_f, MIN(score) min_score
          FROM g GROUP BY sid, semester),
        b AS (
          SELECT a.*, s.group_id, gp.course, s.faculty_id, gp.direction, s.level, s.study_form,
                 CASE WHEN a.semester={AR.RATING_SEMESTER} THEN s.attendance END attendance
          FROM a JOIN students s ON s.id=a.sid JOIN groups_ gp ON gp.id=s.group_id)
        SELECT sid, semester, gpa, avg_score, credits, credits_ok, n_subj, n_f, min_score, group_id, course, faculty_id, direction, level,
               study_form, attendance, {wins}
        FROM b""")
    n = con.execute("SELECT COUNT(*) FROM rating_cache").fetchone()[0]
    took = round(time.time() - t0, 2)
    for k, v in (("fingerprint", fp), ("computed_at", _now().isoformat(sep=" ")), ("rows", str(n)), ("seconds", str(took)), ("reason", reason)):
        con.execute("INSERT OR REPLACE INTO rating_meta(key,value) VALUES(?,?)", (k, v))
    con.commit()
    _state.update(fp=fp, checked=time.time()); _memo.clear()
    return {"rows": n, "seconds": took, "computed_at": _meta(con, "computed_at"), "credits_from_syllabus": sum(1 for v in subj.values() if v),
            "subjects": len(subj)}

def ensure(con=None, force_check=False):
    """Kesh dolzarbligini tekshiradi (30 soniyada bir marta); manba o'zgargan bo'lsa qayta quradi."""
    con = con or _con
    if not force_check and time.time() - _state["checked"] < CHECK_EVERY and _state["fp"]: return
    with _lock:
        if not force_check and time.time() - _state["checked"] < CHECK_EVERY and _state["fp"]: return
        fp = fingerprint(con)
        empty = not con.execute("SELECT 1 FROM rating_cache LIMIT 1").fetchone()
        if empty or fp != _meta(con, "fingerprint"):
            if con.execute("SELECT 1 FROM grades LIMIT 1").fetchone():
                rebuild(con, "manba o'zgardi" if not empty else "kesh yo'q edi")
                return
        _state.update(fp=fp, checked=time.time())

def init(con):
    AR.ensure_schema(con)
    con.executescript(SCHEMA)
    con.commit()
    try:   # tyutorlar va guruhlar biriktirmasi — server ishga tushishining oxirida (boshqa demo akkauntlar id'si o'zgarmasligi uchun)
        from . import student_ops as OPS
        print("Tyutorlar:", OPS.ensure_tutors(con))
    except Exception as e:
        print("tyutorlar biriktirmasi:", e)
    try:
        ensure(con, force_check=True)
    except Exception as e:   # reyting keshi ilovaning ishga tushishini to'xtatmasin — birinchi so'rovda qayta urinadi
        print("reyting: keshni qurib bo'lmadi:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

# =============================================================================================
# Ruxsat va ko'lam
# =============================================================================================
def mode(c: Ctx):
    k = c.role.key
    if k in FULL: return "full"
    if k in SCOPED: return "scoped"
    if k in AGG: return "aggregate"
    return None

def guard(c: Ctx, action: str, detail: str = "", names=False) -> str:
    """Ruxsat + audit. names=True — ism-sharif chiqadigan ko'rinish (jamlangan rollar uchun yopiq)."""
    m = mode(c)
    ok = m is not None and not (names and m == "aggregate")
    rbac.audit(_con, c, f"reyting: {action}", RES, ok, detail)
    if not ok:
        if m == "aggregate":
            raise AccessDenied("⛔ Reyting: lavozimingiz uchun faqat jamlangan ko'rsatkichlar (taqsimot, o'rtacha qiymatlar) — talabalar "
                               "ism-shariflari ko'rsatilmaydi. So'rov audit jurnaliga yozildi.")
        raise AccessDenied(f"⛔ Reyting: «{c.role.title}» lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")
    return m

def scope_sql(c: Ctx, a="r", id_col="student_id") -> str:
    """Talabalar ko'lami. a — rating_cache (r) yoki students (s) taxallusi; ikkalasida group_id, faculty_id, study_form bor."""
    k = c.role.key
    if k == "sirtqi": return f"{a}.study_form='sirtqi'"
    if k == "kafedra": return f"{a}.group_id IN (SELECT id FROM groups_ WHERE department_id={int(c.user.get('department_id') or 0)})"
    if k == "tyutor": return f"{a}.group_id IN (SELECT group_id FROM tutor_groups WHERE user_id={int(c.user.get('id') or 0)})"
    if k == "oqituvchi": return f"{a}.{id_col} IN (SELECT student_id FROM grades WHERE teacher_id={int(c.user.get('teacher_id') or 0)})"
    return "1=1"

def scope_label(c: Ctx) -> str:
    k = c.role.key
    if k == "sirtqi": return "Sirtqi ta'lim talabalari"
    if k == "oqituvchi": return "Siz baholagan talabalar"
    return c.scope_label(_con)

def _sem(sem: int) -> int:
    if sem not in AR.COMPLETED_SEMESTERS:
        raise HTTPException(400, "Noto'g'ri semestr" + (" — joriy semestr yakuniy nazorati hali o'tmagan, reyting yakunlangan semestrlar bo'yicha"
                                                         if sem == AR.CURRENT_SEMESTER else ""))
    return sem

def _level(level: str) -> str:
    if level not in LEVELS: raise HTTPException(400, "Noto'g'ri daraja")
    return level

def _group_in_scope(c: Ctx, gid: int) -> dict:
    g = db.one(_con, """SELECT g.*, f.name faculty, d.name kafedra FROM groups_ g LEFT JOIN faculties f ON f.id=g.faculty_id
                        LEFT JOIN departments d ON d.id=g.department_id WHERE g.id=?""", (gid,))
    if not g: raise HTTPException(404, "Guruh topilmadi")
    if mode(c) == "scoped" and not db.one(_con, f"SELECT 1 x FROM students s WHERE s.group_id=? AND {scope_sql(c, 's', 'id')} LIMIT 1", (gid,)):
        rbac.audit(_con, c, "reyting: ko'lamdan tashqari guruh", RES, False, str(gid))
        raise AccessDenied("⛔ Bu guruh sizning ko'lamingizga kirmaydi. So'rov audit jurnaliga yozildi.")
    return g

def _place(r, k):
    rk, n = r.get(f"r_{k}"), r.get(f"n_{k}")
    return {"rank": rk, "n": n, "pct": AR.percentile(rk, n)}

# =============================================================================================
# Ma'lumot
# =============================================================================================
def methodology(con) -> dict:
    cr = db.one(con, "SELECT COUNT(*) n, SUM(source=?) syl FROM rating_credits", (AR.CREDIT_SOURCE_SYL,)) or {"n": 0, "syl": 0}
    return {
        "title": AR.RATING_TITLE, "formula": AR.GPA_FORMULA, "formula_full": AR.RATING_FORMULA,
        "scale": [{"lo": lo, "hi": hi, "letter": l, "grade": g, "word": w} for lo, hi, l, g, w in AR.SCALE],
        "pass": AR.PASS, "oraliq": [AR.ORALIQ_MIN, AR.ORALIQ_MAX], "yakuniy": [AR.YAKUNIY_MIN, AR.YAKUNIY_MAX],
        "order": [{"key": k, "label": l, "digits": d} for k, l, d in AR.RATING_ORDER],
        "levels": [{"key": k, "label": l, "note": AR.RATING_LEVEL_NOTE[k]} for k, l in AR.RATING_LEVELS],
        "status": AR.RATED_STATUS, "excellent_min": AR.EXCELLENT_MIN, "top_defaults": AR.TOP_DEFAULTS,
        "unit_min": AR.UNIT_MIN, "unit_min_note": AR.UNIT_MIN_NOTE,
        "credit_default": AR.CREDIT_DEFAULT, "credit_note": AR.CREDIT_NOTE,
        "credits_coverage": {"subjects": cr["n"] or 0, "from_syllabus": cr["syl"] or 0},
        "semesters": [{"key": k, "label": AR.SEMESTERS[k]} for k in AR.COMPLETED_SEMESTERS], "current": AR.RATING_SEMESTER,
        "in_progress": {"key": AR.CURRENT_SEMESTER, "label": AR.SEMESTERS[AR.CURRENT_SEMESTER]},
        "program_credits": AR.PROGRAM_CREDITS, "semester_credits": AR.SEMESTER_CREDITS,
        "definitions": {"score": AR.SCORE_LABEL, "gpa": AR.GPA_LABEL, "debtor": AR.DEBTOR_DEF, "score_def": AR.SCORE_DEF},
        "source": AR.SOURCE,
        "notes": [
            "Reyting baholar jadvalidagi yakuniy ballardan (qayta topshirilgan bo'lsa — hisobdagi urinish) qayta hisoblanadi. "
            f"Panel va boshqa modullardagi «{AR.SCORE_LABEL}» ham shu baholardan, xuddi shu formula bilan hisoblanadi (students.gpa — hisoblangan qiymat).",
            f"Faqat yakunlangan semestrlar: {AR.SEMESTERS[AR.CURRENT_SEMESTER]}da hozircha faqat oraliq nazorat (30 ball) o'tkazilgan — yakuniy "
            "nazorat qishki sessiyada; joriy oraliq natijalari talaba kartasida alohida ko'rsatiladi. 1-kurs talabalarining yakunlangan semestri hali yo'q.",
            f"Kredit — o'quv rejasidan: har semestr {AR.SEMESTER_CREDITS} kredit, bakalavriat {AR.BACHELOR_CREDITS}, magistratura {AR.MASTER_CREDITS} kredit.",
            "O'rin — RANK() usulida: barcha mezonlari to'liq teng talabalar bir xil o'rinni oladi, keyingisi o'tkazib yuboriladi (1, 2, 2, 4).",
            "Foiz — «yuqoridan necha foiz ichida»: o'rin / jami × 100, yuqoriga yaxlitlanadi (1 — eng yaxshi).",
            "Davomat: oxirgi yakunlangan semestr reytingida teng kelganda joriy semestr davomati hisobga olinadi; undan oldingi semestrlar "
            "davomati bazada saqlanmagan — u yerda faqat GPA va o'rtacha ball.",
            "Masofaviy ta'limda auditoriya davomati qayd etilmaydi — davomat bo'yicha teng kelganda bunday talaba oxirida turadi; "
            "a'lochilar ro'yxatida davomat sharti unga qo'llanmaydi.",
            "Oraliq (30) va yakuniy (70) nazorat ballari bazada alohida saqlanadi; qayta topshirish urinishlari tarixda (asl urinish ham), "
            "hisobga olinadigan natija — eng yuqorisi (o'tgan baho pasaytirilmaydi).",
        ],
    }

def meta(c: Ctx) -> dict:
    m = mode(c)
    sc = scope_sql(c, "r")
    facs = db.rows(_con, f"""SELECT f.id, f.name, COUNT(*) n FROM rating_cache r JOIN faculties f ON f.id=r.faculty_id
                             WHERE r.semester=? AND {sc} GROUP BY f.id ORDER BY f.id""", (AR.RATING_SEMESTER,))
    courses = db.rows(_con, f"SELECT DISTINCT r.course FROM rating_cache r WHERE r.semester=? AND {sc} ORDER BY 1", (AR.RATING_SEMESTER,))
    forms = db.rows(_con, f"SELECT DISTINCT r.study_form FROM rating_cache r WHERE r.semester=? AND {sc} ORDER BY 1", (AR.RATING_SEMESTER,))
    groups = [] if m == "aggregate" else db.rows(_con, f"""SELECT g.id, g.name, g.course, g.faculty_id, g.form, COUNT(*) n FROM rating_cache r
                    JOIN groups_ g ON g.id=r.group_id WHERE r.semester=? AND {sc} GROUP BY g.id ORDER BY g.name""", (AR.RATING_SEMESTER,))
    units = ["group", "kafedra"] + (["teacher"] if c.role.key in FULL + ("kafedra", "oqituvchi") else [])
    tabs = (["overview", "list", "qaydnoma", "dynamics", "top", "units", "method"] if m != "aggregate"
            else ["overview", "dynamics", "units", "method"])
    return {"mode": m, "role": c.role.key, "scope": scope_label(c), "title": AR.RATING_TITLE, "tabs": tabs, "units": units,
            "can_recompute": c.role.key in RECOMPUTE, "names": m != "aggregate",
            "semesters": [{"key": k, "label": AR.SEMESTERS[k], "short": AR.SEMESTER_SHORT[k]} for k in AR.COMPLETED_SEMESTERS], "current": AR.RATING_SEMESTER,
            "in_progress": {"key": AR.CURRENT_SEMESTER, "label": AR.SEMESTERS[AR.CURRENT_SEMESTER], "short": AR.SEMESTER_SHORT[AR.CURRENT_SEMESTER]},
            "levels": [{"key": k, "label": l} for k, l in AR.RATING_LEVELS],
            "faculties": facs, "courses": [r["course"] for r in courses], "forms": [{"key": r["study_form"], "label": FORMS.get(r["study_form"], r["study_form"])} for r in forms],
            "groups": groups, "computed_at": _meta(_con, "computed_at"), "rows": int(_meta(_con, "rows", "0") or 0),
            "seconds": _meta(_con, "seconds"), "methodology": methodology(_con)}

GPA_BINS = [(2.0, 2.5), (2.5, 3.0), (3.0, 3.5), (3.5, 4.0), (4.0, 4.5), (4.5, 5.01)]

def overview(c: Ctx, sem: int) -> dict:
    sc = scope_sql(c, "r")
    agg = f"""COUNT(*) n, ROUND(AVG(r.gpa),2) gpa, ROUND(AVG(r.avg_score),1) avg_score, ROUND(100.0*SUM(r.n_f>0)/COUNT(*),1) debt_pct,
              SUM(r.n_f>0) debt, SUM(r.min_score>={AR.EXCELLENT_MIN}) excellent, ROUND(100.0*SUM(r.min_score>={AR.EXCELLENT_MIN})/COUNT(*),1) excellent_pct,
              ROUND(AVG(r.attendance),1) attendance"""
    tot = db.one(_con, f"SELECT {agg} FROM rating_cache r WHERE r.semester=? AND {sc}", (sem,))
    prev = db.one(_con, f"SELECT {agg} FROM rating_cache r WHERE r.semester=? AND {sc}", (sem - 1,)) if sem - 1 in AR.COMPLETED_SEMESTERS else None
    if prev and not prev["n"]: prev = None
    # «Akademik qarzdor» — yagona ta'rif (academic_rules.DEBTOR_DEF): barcha yakunlangan semestrlar bo'yicha, faol talabalar.
    # Talabalar markazidagi «Akademik qarzdor» bilan bir xil son; yuqoridagi «debt» — faqat shu semestrdan qolgan qarz.
    ssc = scope_sql(c, "s", "id")
    tot["debtors_all"] = db.one(_con, f"""SELECT COUNT(DISTINCT g.student_id) n FROM grades g JOIN students s ON s.id=g.student_id
                                         WHERE {AR.debt_where('g')} AND s.status='{AR.RATED_STATUS}' AND {ssc}""")["n"]
    tot["students_all"] = db.one(_con, f"SELECT COUNT(*) n FROM students s WHERE s.status='{AR.RATED_STATUS}' AND {ssc}")["n"]
    bins = []
    for lo, hi in GPA_BINS:
        n = db.one(_con, f"SELECT COUNT(*) n FROM rating_cache r WHERE r.semester=? AND {sc} AND r.gpa>=? AND r.gpa<?", (sem, lo, hi))["n"]
        bins.append({"lo": lo, "hi": min(hi, 5.0), "n": n})
    by_fac = db.rows(_con, f"""SELECT f.name label, {agg} FROM rating_cache r JOIN faculties f ON f.id=r.faculty_id
                               WHERE r.semester=? AND {sc} GROUP BY f.id ORDER BY f.id""", (sem,))
    by_course = db.rows(_con, f"""SELECT r.level || ' · ' || r.course || '-kurs' label, {agg} FROM rating_cache r WHERE r.semester=? AND {sc}
                                  GROUP BY r.level, r.course ORDER BY r.level, r.course""", (sem,))
    by_form = db.rows(_con, f"""SELECT r.study_form label, {agg} FROM rating_cache r WHERE r.semester=? AND {sc}
                                GROUP BY r.study_form ORDER BY n DESC""", (sem,))
    for r in by_form: r["label"] = FORMS.get(r["label"], r["label"])
    return {"sem": sem, "label": AR.SEMESTERS[sem], "scope": scope_label(c), "total": tot, "prev": prev, "bins": bins,
            "by_faculty": by_fac, "by_course": by_course, "by_form": by_form,
            "labels": {"score": AR.SCORE_LABEL, "gpa": AR.GPA_LABEL, "debtor": AR.DEBTOR_LABEL, "debtor_def": AR.DEBTOR_DEF,
                       "debt_sem": "shu semestrdan o'zlashtirilmagan fani qolgan (hisobdagi ball < 40)"}}

SORTS = {"place": ("r.r_{lv}", "ASC"), "gpa": ("r.gpa", "DESC"), "avg": ("r.avg_score", "DESC"), "att": ("r.attendance IS NULL, r.attendance", "DESC"),
         "credits": ("r.credits_ok", "DESC"), "nf": ("r.n_f", "DESC"), "delta": ("delta IS NULL, delta", "DESC"), "name": ("s.full_name", "ASC")}

def _filters(c: Ctx, sem, faculty=0, course=0, group=0, form="", flag="", q=""):
    w, a = [scope_sql(c, "r"), "r.semester=?"], [sem]
    if faculty: w.append("r.faculty_id=?"); a.append(faculty)
    if course: w.append("r.course=?"); a.append(course)
    if group: w.append("r.group_id=?"); a.append(group)
    if form: w.append("r.study_form=?"); a.append(form)
    if flag == "qarzdor": w.append("r.n_f>0")
    elif flag == "alochi": w.append(f"r.min_score>={AR.EXCELLENT_MIN}")
    if q:
        w.append("(s.full_name LIKE ? OR s.hemis_id LIKE ? OR g.name LIKE ?)"); a += [f"%{q}%", f"{q}%", f"{q}%"]
    return " AND ".join(w), a

def ranking(c: Ctx, sem=AR.RATING_SEMESTER, level="institute", faculty=0, course=0, group=0, form="", flag="", q="", sort="place", direction="", page=1, per=50) -> dict:
    lv = _level(level); sem = _sem(sem)
    w, a = _filters(c, sem, faculty, course, group, form, flag, q)
    col, d = SORTS.get(sort, SORTS["place"])
    col = col.format(lv=lv)
    if direction in ("asc", "desc"): d = direction.upper()
    order = ", ".join(f"{x.strip()} {d}" if not x.strip().endswith("IS NULL") else x.strip() for x in col.split(","))
    base = f"""FROM rating_cache r JOIN students s ON s.id=r.student_id JOIN groups_ g ON g.id=r.group_id
               LEFT JOIN rating_cache p ON p.student_id=r.student_id AND p.semester=r.semester-1 WHERE {w}"""
    per = max(10, min(200, per)); page = max(1, page)
    sm = db.one(_con, f"""SELECT COUNT(*) n, ROUND(AVG(r.gpa),2) gpa, SUM(r.n_f>0) debt, SUM(r.min_score>={AR.EXCELLENT_MIN}) excellent {base}""", a)
    rows = db.rows(_con, f"""SELECT r.*, s.full_name name, s.hemis_id, g.name grp, (p.r_{lv} - r.r_{lv}) delta, p.gpa gpa_prev {base}
                             ORDER BY {order}, r.r_{lv}, s.full_name LIMIT ? OFFSET ?""", a + [per, (page - 1) * per])
    out = []
    for r in rows:
        out.append({"id": r["student_id"], "name": r["name"], "hemis_id": r["hemis_id"], "group": r["grp"], "group_id": r["group_id"],
                    "course": r["course"], "form": r["study_form"], "gpa": r["gpa"], "gpa_prev": r["gpa_prev"], "avg_score": r["avg_score"],
                    "attendance": r["attendance"], "credits": r["credits"], "credits_ok": r["credits_ok"], "n_f": r["n_f"],
                    "excellent": r["min_score"] >= AR.EXCELLENT_MIN, "debtor": r["n_f"] > 0,
                    "place": _place(r, lv), "delta": r["delta"]})
    return {"sem": sem, "level": lv, "level_label": LEVELS[lv], "page": page, "per": per, "total": sm["n"], "pages": max(1, math.ceil(sm["n"] / per)),
            "summary": sm, "rows": out, "has_prev": sem - 1 in AR.COMPLETED_SEMESTERS}

def student_card(c: Ctx, sid: int) -> dict:
    s = db.one(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.status, s.level, s.study_form, s.attendance, s.group_id, s.faculty_id,
                         g.name grp, g.course, g.direction, f.name faculty, d.name kafedra FROM students s JOIN groups_ g ON g.id=s.group_id
                         LEFT JOIN faculties f ON f.id=s.faculty_id LEFT JOIN departments d ON d.id=g.department_id
                         WHERE s.id=? AND {scope_sql(c, 's', 'id')}""", (sid,))
    if not s:
        if db.one(_con, "SELECT 1 x FROM students WHERE id=?", (sid,)):
            rbac.audit(_con, c, "reyting: ko'lamdan tashqari talaba", RES, False, str(sid))
            raise AccessDenied("⛔ Bu talaba sizning ko'lamingizga kirmaydi. So'rov audit jurnaliga yozildi.")
        raise HTTPException(404, "Talaba topilmadi")
    grades = db.rows(_con, """SELECT gr.subject, gr.score, gr.semester, gr.oraliq, gr.yakuniy, gr.credits, gr.sem_no, gr.attempts, t.full_name teacher
                              FROM grades gr LEFT JOIN teachers t ON t.id=gr.teacher_id
                              WHERE gr.student_id=? ORDER BY gr.semester DESC, gr.subject""", (sid,))
    cache = {r["semester"]: r for r in db.rows(_con, "SELECT * FROM rating_cache WHERE student_id=?", (sid,))}
    sems, allitems = [], []
    for sem in AR.COMPLETED_SEMESTERS:
        gs = [g for g in grades if g["semester"] == sem and g["score"] is not None]
        if not gs: continue
        subj = []
        for g in gs:
            cr = g["credits"] or AR.CREDIT_DEFAULT
            g5, word = AR.grade5(g["score"])
            subj.append({"subject": g["subject"], "score": g["score"], "oraliq": g["oraliq"], "yakuniy": g["yakuniy"], "letter": AR.letter(g["score"]),
                         "grade": g5, "word": word, "credits": cr, "credit_source": AR.CREDIT_SOURCE_SYL if g["credits"] else AR.CREDIT_SOURCE_DEFAULT,
                         "teacher": g["teacher"], "fail": g["score"] < AR.PASS, "attempts": g["attempts"] or 1,
                         "admitted": AR.admitted(g["oraliq"])})
            allitems.append((cr, g5, g["score"]))
        r = cache.get(sem)
        sems.append({"sem": sem, "label": AR.SEMESTERS[sem], "short": AR.SEMESTER_SHORT[sem], "sem_no": gs[0]["sem_no"], "subjects": subj,
                     "gpa": r["gpa"] if r else AR.gpa([(x["credits"], x["grade"]) for x in subj]),
                     "avg_score": r["avg_score"] if r else AR.ratio2(sum(x["score"] for x in subj), len(subj)),
                     "credits": sum(x["credits"] for x in subj), "credits_ok": sum(x["credits"] for x in subj if not x["fail"]),
                     "n_f": sum(1 for x in subj if x["fail"]), "attendance": r["attendance"] if r else None,
                     "places": {k: _place(r, k) for k, _ in AR.RATING_LEVELS} if r else None})
    for i, x in enumerate(sems):   # o'rin o'zgarishi (oldingi semestrga nisbatan)
        prev = next((y for y in sems if y["sem"] == x["sem"] - 1), None)
        if x["places"] and prev and prev["places"]:
            for k in x["places"]: x["places"][k]["delta"] = prev["places"][k]["rank"] - x["places"][k]["rank"]
    cum = AR.gpa([(cr, g5) for cr, g5, _ in allitems])
    curg = [g for g in grades if g["semester"] == AR.CURRENT_SEMESTER]
    current = {"sem": AR.CURRENT_SEMESTER, "label": AR.SEMESTERS[AR.CURRENT_SEMESTER], "short": AR.SEMESTER_SHORT[AR.CURRENT_SEMESTER],
               "sem_no": curg[0]["sem_no"] if curg else None, "attendance": s["attendance"],
               "subjects": [{"subject": g["subject"], "oraliq": g["oraliq"], "admitted": AR.admitted(g["oraliq"]), "credits": g["credits"] or AR.CREDIT_DEFAULT,
                             "teacher": g["teacher"]} for g in curg],
               "note": f"Yakuniy nazorat (qishki sessiya) hali o'tkazilmagan — oraliq nazorat {AR.ORALIQ_MAX} balldan; yakuniyga kirish uchun kamida {AR.ORALIQ_MIN} ball."} if curg else None
    total = AR.PROGRAM_CREDITS.get(s["level"] or "bakalavr", AR.BACHELOR_CREDITS)
    ok_cr = sum(cr for cr, _, sc in allitems if sc >= AR.PASS)
    return {"student": {k: s[k] for k in ("id", "full_name", "hemis_id", "status", "level", "study_form", "grp", "group_id", "course", "direction",
                                          "faculty", "kafedra")},
            "form_label": FORMS.get(s["study_form"], s["study_form"]), "ranked": s["status"] == AR.RATED_STATUS,
            "semesters": sems, "current": current,
            "cumulative": {"gpa": cum, "credits": sum(cr for cr, _, _ in allitems), "credits_ok": ok_cr,
                           "avg_score": AR.ratio2(sum(sc for _, _, sc in allitems), len(allitems)),
                           "program_credits": total, "progress_pct": round(100 * ok_cr / total, 1) if total else None,
                           "debts": sum(1 for _, _, sc in allitems if sc < AR.PASS)},
            "trend": [{"sem": x["sem"], "short": x["short"], "gpa": x["gpa"], "avg_score": x["avg_score"],
                       "pct": (x["places"] or {}).get("institute", {}).get("pct"), "rank": (x["places"] or {}).get("institute", {}).get("rank"),
                       "n": (x["places"] or {}).get("institute", {}).get("n")} for x in sorted(sems, key=lambda y: y["sem"])],
            "levels": [{"key": k, "label": l} for k, l in AR.RATING_LEVELS], "pass": AR.PASS, "oraliq_min": AR.ORALIQ_MIN, "oraliq_max": AR.ORALIQ_MAX}

def qaydnoma(c: Ctx, gid: int, sem: int) -> dict:
    sem = _sem(sem)
    g = _group_in_scope(c, gid)
    subj = db.rows(_con, f"""SELECT gr.subject, MAX(gr.credits) credits, MIN(t.full_name) teacher, COUNT(*) n, ROUND(AVG(gr.score),1) avg,
                             ROUND(100.0*SUM(gr.score>={AR.PASS})/COUNT(*),1) pass_pct
                             FROM grades gr JOIN rating_cache r ON r.student_id=gr.student_id AND r.semester=gr.semester
                             LEFT JOIN teachers t ON t.id=gr.teacher_id
                             WHERE r.group_id=? AND gr.semester=? GROUP BY gr.subject ORDER BY gr.subject""", (gid, sem))
    rows = db.rows(_con, """SELECT r.*, s.full_name name, s.hemis_id FROM rating_cache r JOIN students s ON s.id=r.student_id
                            WHERE r.group_id=? AND r.semester=? ORDER BY r.r_group, s.full_name""", (gid, sem))
    sc = {}
    for x in db.rows(_con, """SELECT gr.student_id, gr.subject, gr.score FROM grades gr JOIN rating_cache r ON r.student_id=gr.student_id AND r.semester=gr.semester
                              WHERE r.group_id=? AND gr.semester=?""", (gid, sem)):
        sc.setdefault(x["student_id"], {})[x["subject"]] = x["score"]
    skipped = db.one(_con, "SELECT COUNT(*) n FROM students WHERE group_id=? AND status!=?", (gid, AR.RATED_STATUS))["n"]
    out = [{"id": r["student_id"], "name": r["name"], "hemis_id": r["hemis_id"], "scores": [sc.get(r["student_id"], {}).get(x["subject"]) for x in subj],
            "gpa": r["gpa"], "avg_score": r["avg_score"], "credits": r["credits"], "credits_ok": r["credits_ok"], "n_f": r["n_f"],
            "place": _place(r, "group"), "place_course": _place(r, "course"), "excellent": r["min_score"] >= AR.EXCELLENT_MIN} for r in rows]
    for x in subj: x["credits"] = x["credits"] or AR.CREDIT_DEFAULT
    return {"group": {k: g.get(k) for k in ("id", "name", "course", "direction", "level", "form", "faculty", "kafedra")},
            "form_label": FORMS.get(g.get("form"), g.get("form")), "sem": sem, "sem_label": AR.SEMESTERS[sem], "subjects": subj, "rows": out,
            "skipped": skipped, "pass": AR.PASS, "avg_gpa": round(sum(r["gpa"] for r in out) / len(out), 2) if out else None}

def dynamics(c: Ctx, level="course", limit=15) -> dict:
    lv = _level(level); cur, prv = AR.RATING_SEMESTER, AR.RATING_SEMESTER - 1
    sc = scope_sql(c, "r"); limit = max(5, min(50, limit))
    base = f"""FROM rating_cache r JOIN rating_cache p ON p.student_id=r.student_id AND p.semester={prv}
               JOIN students s ON s.id=r.student_id JOIN groups_ g ON g.id=r.group_id WHERE r.semester={cur} AND {sc}"""
    sm = db.one(_con, f"""SELECT COUNT(*) n, SUM(p.r_{lv} > r.r_{lv}) up, SUM(p.r_{lv} < r.r_{lv}) down, SUM(p.r_{lv} = r.r_{lv}) same,
                          ROUND(AVG(r.gpa),2) gpa, ROUND(AVG(p.gpa),2) gpa_prev {base}""")
    out = {"level": lv, "level_label": LEVELS[lv], "from": AR.SEMESTER_SHORT[prv], "to": AR.SEMESTER_SHORT[cur], "summary": sm, "scope": scope_label(c)}
    if mode(c) != "aggregate":
        q = f"""SELECT r.student_id id, s.full_name name, g.name grp, r.course, r.gpa, p.gpa gpa_prev, r.r_{lv} rank, p.r_{lv} rank_prev,
                r.n_{lv} n, (p.r_{lv} - r.r_{lv}) delta, r.n_f {base}"""
        out["risers"] = db.rows(_con, f"{q} ORDER BY delta DESC, r.r_{lv} LIMIT ?", (limit,))
        out["fallers"] = db.rows(_con, f"{q} ORDER BY delta ASC, r.r_{lv} LIMIT ?", (limit,))
    gq = f"""SELECT g.id, g.name, g.course, COUNT(*) n, ROUND(AVG(r.gpa),2) gpa, ROUND(AVG(p.gpa),2) gpa_prev, ROUND(AVG(r.gpa)-AVG(p.gpa),2) delta
             {base} GROUP BY g.id HAVING n >= {AR.UNIT_MIN['group']}"""
    out["groups_up"] = db.rows(_con, f"{gq} ORDER BY delta DESC, g.name LIMIT ?", (limit,))
    out["groups_down"] = db.rows(_con, f"{gq} ORDER BY delta ASC, g.name LIMIT ?", (limit,))
    return out

def top_list(c: Ctx, sem=AR.RATING_SEMESTER, pct=10.0, min_att=85.0, max_f=0) -> dict:
    sem = _sem(sem)
    pct = max(1.0, min(50.0, float(pct))); min_att = max(0.0, min(100.0, float(min_att))); max_f = max(0, min(3, int(max_f)))
    use_att = sem == AR.RATING_SEMESTER   # oxirgi yakunlangan semestr natijalari + joriy davomat
    att = f" AND (r.attendance IS NULL OR r.attendance >= {min_att})" if use_att else ""
    rows = db.rows(_con, f"""SELECT r.student_id id, s.full_name name, s.hemis_id, g.name grp, r.level, r.course, r.study_form, r.gpa, r.avg_score,
                             r.attendance, r.n_f, r.r_course rank, r.n_course n, f.name faculty, r.min_score
                             FROM rating_cache r JOIN students s ON s.id=r.student_id JOIN groups_ g ON g.id=r.group_id
                             LEFT JOIN faculties f ON f.id=r.faculty_id
                             WHERE r.semester=? AND {scope_sql(c, 'r')} AND r.r_course <= CAST((r.n_course * ? / 100.0) + 0.999999 AS INT)
                             AND r.n_f <= ?{att} ORDER BY r.level, r.course, r.r_course, s.full_name""", (sem, pct, max_f))
    courses = {}
    for r in rows:
        k = (r["level"], r["course"])
        cc = courses.setdefault(k, {"level": r["level"], "course": r["course"], "n": r["n"], "quota": math.ceil(r["n"] * pct / 100), "rows": []})
        r["pct"] = AR.percentile(r["rank"], r["n"]); r["excellent"] = r.pop("min_score") >= AR.EXCELLENT_MIN
        cc["rows"].append(r)
    return {"sem": sem, "sem_label": AR.SEMESTERS[sem], "params": {"pct": pct, "min_att": min_att, "max_f": max_f, "att_applied": use_att},
            "courses": list(courses.values()), "total": len(rows), "scope": scope_label(c)}

def _units_all(kind: str, sem: int) -> list:
    """Bo'linmalar reytingi butun institut bo'yicha (memo — kesh barmoq izi bilan); ko'lam keyin qo'llanadi."""
    key = (_state["fp"], kind, sem)
    if key in _memo: return _memo[key]
    agg = f"COUNT(*) n_grades, COUNT(DISTINCT gr.student_id) n_students, ROUND(AVG(gr.score),2) avg, ROUND(100.0*SUM(gr.score>={AR.PASS})/COUNT(*),1) pass_pct"
    base = f"FROM grades gr JOIN students s ON s.id=gr.student_id AND s.status='{AR.RATED_STATUS}' WHERE gr.score IS NOT NULL AND gr.semester=?"
    if kind == "group":
        rows = db.rows(_con, f"""SELECT g.id, g.name, g.course, g.form, g.department_id, f.name faculty, {agg} {base.replace('WHERE', 'JOIN groups_ g ON g.id=s.group_id LEFT JOIN faculties f ON f.id=g.faculty_id WHERE')}
                                 GROUP BY g.id""", (sem,))
        size = lambda r: r["n_students"]
    elif kind == "kafedra":
        rows = db.rows(_con, f"""SELECT d.id, d.name, d.id department_id, COUNT(DISTINCT gr.teacher_id) n_teachers, {agg}
                                 {base.replace('WHERE', 'JOIN teachers t ON t.id=gr.teacher_id JOIN departments d ON d.id=t.department_id WHERE')} GROUP BY d.id""", (sem,))
        size = lambda r: r["n_grades"]
    else:
        rows = db.rows(_con, f"""SELECT t.id, t.full_name name, t.position, t.department_id, d.name kafedra, COUNT(DISTINCT s.group_id) n_groups, {agg}
                                 {base.replace('WHERE', 'JOIN teachers t ON t.id=gr.teacher_id LEFT JOIN departments d ON d.id=t.department_id WHERE')}
                                 GROUP BY t.id""", (sem,))
        size = lambda r: r["n_grades"]
    mn = AR.UNIT_MIN[kind]
    ok = sorted([r for r in rows if size(r) >= mn], key=lambda r: (-r["pass_pct"], -r["avg"], r["name"]))
    prev = None
    for i, r in enumerate(ok, 1):   # RANK(): o'tish foizi va o'rtacha ball teng bo'lsa — bir xil o'rin
        r["rank"] = prev["rank"] if prev and (prev["pass_pct"], prev["avg"]) == (r["pass_pct"], r["avg"]) else i
        r["eligible"] = True; prev = r
    small = sorted([r for r in rows if size(r) < mn], key=lambda r: (-r["pass_pct"], -r["avg"], r["name"]))
    for r in small: r["rank"] = None; r["eligible"] = False
    for r in ok + small: r["of"] = len(ok)
    _memo[key] = ok + small
    return ok + small

def units(c: Ctx, kind="group", sem=AR.RATING_SEMESTER) -> dict:
    sem = _sem(sem)
    if kind not in AR.UNIT_MIN: raise HTTPException(400, "Noto'g'ri bo'linma turi")
    k, m = c.role.key, mode(c)
    if kind == "teacher" and k not in FULL + ("kafedra", "oqituvchi"):
        rbac.audit(_con, c, "reyting: o'qituvchilar reytingi", RES, False)
        raise AccessDenied("⛔ O'qituvchilar reytingi (shaxsiy ko'rsatkich) — Registrator ofisi, Akademik faoliyatni boshqarish bo'limi, kafedra mudiri (o'z kafedrasi) va o'qituvchining "
                           "o'ziga. So'rov audit jurnaliga yozildi.")
    rows = _units_all(kind, sem)
    dep, tid = int(c.user.get("department_id") or 0), int(c.user.get("teacher_id") or 0)
    if kind == "group" and m == "scoped":
        allowed = {r["id"] for r in db.rows(_con, f"SELECT DISTINCT r.group_id id FROM rating_cache r WHERE r.semester=? AND {scope_sql(c, 'r')}", (sem,))}
        rows = [r for r in rows if r["id"] in allowed]
    elif kind == "kafedra" and k in ("kafedra", "oqituvchi"):
        rows = [r for r in rows if r["id"] == dep]
    elif kind == "teacher" and k == "kafedra":
        rows = [r for r in rows if r["department_id"] == dep]
    elif kind == "teacher" and k == "oqituvchi":
        rows = [r for r in rows if r["id"] == tid]
    return {"kind": kind, "sem": sem, "min": AR.UNIT_MIN[kind], "min_note": AR.UNIT_MIN_NOTE[kind], "rows": rows[:400], "total": len(rows),
            "scope": scope_label(c)}

# =============================================================================================
# Eksport (.xlsx, .docx)
# =============================================================================================
def _head_name(key: str) -> str:
    """Bo'lim boshlig'i: org_units → users (ism-sharif bazadan, qisqartirilgan: «Baratov M.»)."""
    name = ""
    try:
        r = db.one(_con, "SELECT head FROM org_units WHERE key=?", (key,)); name = (r or {}).get("head") or ""
    except Exception: pass
    if not name:
        r = db.one(_con, "SELECT full_name FROM users WHERE role=? ORDER BY id LIMIT 1", (key,))
        name = r["full_name"].split(":", 1)[1].strip() if r and ":" in (r["full_name"] or "") else ""
    p = name.split()
    return f"{p[0]} {p[1][0]}." if len(p) > 1 else name

SIGNERS = [("Registrator ofisi boshlig'i", "talabalar"), (f"{AR.ACADEMIC_UNIT} boshlig'i", "akademik")]

def _xlsx_styles():
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    thin = Side(style="thin", color="C9CED6")
    return {"hdr": Font(bold=True, color="FFFFFF"), "fill": PatternFill("solid", fgColor="7A0E14"), "bold": Font(bold=True),
            "title": Font(bold=True, size=14, color="7A0E14"), "muted": Font(size=9, color="555B63"), "bad": Font(color="C0262D", bold=True),
            "center": Alignment(horizontal="center", vertical="center", wrap_text=True), "wrap": Alignment(wrap_text=True, vertical="top"),
            "border": Border(left=thin, right=thin, top=thin, bottom=thin), "alt": PatternFill("solid", fgColor="F4F5F7")}

def _xlsx_header(ws, st, title, sub, ncols):
    from openpyxl.utils import get_column_letter
    end = get_column_letter(max(ncols, 4))
    ws.append(["ISFT INSTITUTI — International School of Finance and Technology"]); ws.merge_cells(f"A1:{end}1"); ws["A1"].font = st["title"]
    ws.append([AR.RATING_TITLE]); ws.merge_cells(f"A2:{end}2"); ws["A2"].font = st["muted"]
    ws.append([title]); ws.merge_cells(f"A3:{end}3"); ws["A3"].font = Font_bold(size=12)
    ws.append([sub]); ws.merge_cells(f"A4:{end}4"); ws["A4"].font = st["muted"]
    ws.append([])

def Font_bold(size=11):
    from openpyxl.styles import Font
    return Font(bold=True, size=size)

def _xlsx_table(ws, st, head, rows, bad_cols=()):
    ws.append(head); hr = ws.max_row
    for cell in ws[hr]: cell.font = st["hdr"]; cell.fill = st["fill"]; cell.alignment = st["center"]; cell.border = st["border"]
    for i, row in enumerate(rows):
        ws.append(list(row))
        for j, cell in enumerate(ws[ws.max_row]):
            cell.border = st["border"]
            if i % 2: cell.fill = st["alt"]
            if j in bad_cols and isinstance(cell.value, (int, float)) and cell.value < AR.PASS: cell.font = st["bad"]
    return hr

def _xlsx_signers(ws, st, who):
    ws.append([])
    for pos, key in SIGNERS:
        ws.append([pos, None, None, "______________", None, _head_name(key)]); ws.cell(ws.max_row, 1).font = st["bold"]
    ws.append([]); ws.append([f"Tuzildi: ISFT Core, {_now().strftime('%d.%m.%Y %H:%M')} · {who}"]); ws.cell(ws.max_row, 1).font = st["muted"]

def qaydnoma_xlsx(Q: dict, who: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    st = _xlsx_styles(); wb = Workbook(); ws = wb.active; ws.title = "Qaydnoma"
    g = Q["group"]; subj = Q["subjects"]
    head = ["№", "F.I.Sh.", "HEMIS ID"] + [f"{x['subject']} ({x['credits']} kr.)" for x in subj] + ["GPA", "O'rtacha ball", "Kredit (o'zl./jami)", "Qarz (F)", "O'rin (guruh)", "O'rin (kurs)"]
    _xlsx_header(ws, st, f"REYTING QAYDNOMASI — {g['name']} guruhi", f"{Q['sem_label']} · {g['faculty'] or ''} · {g['direction'] or ''} · {g['course']}-kurs · "
                 f"{Q['form_label']} · Baholash: {AR.SCALE_TEXT}", len(head))
    rows = [[i, r["name"], r["hemis_id"], *[s if s is not None else "—" for s in r["scores"]], r["gpa"], r["avg_score"], f"{r['credits_ok']}/{r['credits']}",
             r["n_f"], f"{r['place']['rank']} / {r['place']['n']}", f"{r['place_course']['rank']} / {r['place_course']['n']}"] for i, r in enumerate(Q["rows"], 1)]
    hr = _xlsx_table(ws, st, head, rows, bad_cols=set(range(3, 3 + len(subj))))
    ws.append(["", "O'rtacha / o'tish foizi", ""] + [f"{x['avg']} / {x['pass_pct']}%" for x in subj] + [Q["avg_gpa"]])
    for cell in ws[ws.max_row]: cell.font = st["bold"]
    ws.row_dimensions[hr].height = 48
    ws.column_dimensions["A"].width = 5; ws.column_dimensions["B"].width = 34; ws.column_dimensions["C"].width = 15
    for i in range(len(subj)): ws.column_dimensions[get_column_letter(4 + i)].width = 14
    for i in range(6): ws.column_dimensions[get_column_letter(4 + len(subj) + i)].width = 13
    ws.freeze_panes = ws.cell(hr + 1, 3)
    _xlsx_signers(ws, st, who)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

def qaydnoma_docx(Q: dict, who: str) -> bytes:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.shared import Cm, RGBColor
    from . import brand as B
    doc = Document(); B.setup(doc)
    sec = doc.sections[0]; sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(1.6); sec.top_margin = Cm(1.2); sec.bottom_margin = Cm(1.2)
    B.letterhead(doc)
    g = Q["group"]; subj = Q["subjects"]
    B.title(doc, "REYTING QAYDNOMASI", f"{g['name']} guruhi · {Q['sem_label']}")
    B.para(doc, f"Fakultet: {g['faculty'] or '—'} · Yo'nalish: {g['direction'] or '—'} · {g['course']}-kurs · {Q['form_label']} ta'lim · "
                f"Kafedra: {g['kafedra'] or '—'}. Talabalar: {len(Q['rows'])}" + (f" (reytingda ishtirok etmaydi: {Q['skipped']})" if Q["skipped"] else "") + ".",
           indent=False, size=10)
    head = ["№", "F.I.Sh."] + [str(i) for i in range(1, len(subj) + 1)] + ["GPA", "O'rt. ball", "Qarz", "O'rin"]
    t = doc.add_table(rows=1, cols=len(head)); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(head):
        cl = t.rows[0].cells[i]; cl.text = ""; p = cl.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        B.run(p, h, 8.5, True, RGBColor(255, 255, 255)); B.shade(cl, B.TEAL_DARK)
    for k, r in enumerate(Q["rows"], 1):
        vals = [k, r["name"]] + [("—" if s is None else s) for s in r["scores"]] + [f"{r['gpa']:.2f}", f"{r['avg_score']:.1f}", r["n_f"] or "",
                                                                                  f"{r['place']['rank']}/{r['place']['n']}"]
        cells = t.add_row().cells
        for i, v in enumerate(vals):
            cells[i].text = ""; p = cells[i].paragraphs[0]
            if i != 1: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            bad = 2 <= i < 2 + len(subj) and isinstance(v, int) and v < AR.PASS
            B.run(p, str(v), 8.5, bad, RGBColor(0xC0, 0x26, 0x2D) if bad else None)
            if k % 2 == 0: B.shade(cells[i], "F4F5F7")
    sw = max(1.0, min(1.6, (26.5 - 0.8 - 6.2 - 1.3 - 1.4 - 1.1 - 1.6) / max(1, len(subj))))
    B.full_width(t, [0.8, 6.2] + [sw] * len(subj) + [1.3, 1.4, 1.1, 1.6])
    doc.add_paragraph()
    B.para(doc, "Fanlar: " + "; ".join(f"{i} — {x['subject']} ({x['credits']} kredit, o'rtacha {x['avg']}, o'tish {x['pass_pct']}%)"
                                         for i, x in enumerate(subj, 1)) + ".", indent=False, size=9)
    B.para(doc, f"Reyting: {AR.GPA_FORMULA} (5 ballik baho, kredit bilan tortilgan); teng kelganda — o'rtacha ball, keyin davomat. "
                f"Baholash: {AR.SCALE_TEXT}. Qizil — o'zlashtirilmagan (< {AR.PASS} ball).", indent=False, size=9)
    st = doc.add_table(rows=len(SIGNERS), cols=3); B._no_borders(st); B.full_width(st, [11, 6, 7])
    for i, (pos, key) in enumerate(SIGNERS):
        B.run(st.rows[i].cells[0].paragraphs[0], pos, 11, True)
        p = st.rows[i].cells[1].paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER; B.run(p, "_______________", 11)
        p = st.rows[i].cells[2].paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.RIGHT; B.run(p, _head_name(key), 11, True)
    p = doc.add_paragraph(); B.run(p, f"Tuzildi: ISFT Core, {_now().strftime('%d.%m.%Y %H:%M')} · {who}", 8.5, False, B.RGB_GREY)
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()

def top_xlsx(T: dict, who: str) -> bytes:
    from openpyxl import Workbook
    st = _xlsx_styles(); wb = Workbook(); ws = wb.active; ws.title = "A'lochilar"
    P = T["params"]
    head = ["№", "F.I.Sh.", "HEMIS ID", "Fakultet", "Guruh", "Daraja / kurs", "Shakl", "GPA", "O'rtacha ball", "Davomat, %", "Qarz (F)", "O'rin (kurs)", "Yuqori %"]
    cond = f"kurs bo'yicha eng yaxshi {P['pct']:g}% · qarz (F) ≤ {P['max_f']}" + (f" · davomat ≥ {P['min_att']:g}%" if P["att_applied"] else " · davomat sharti qo'llanmadi (o'tgan semestr)")
    _xlsx_header(ws, st, "MUKOFOTGA TAVSIYA ETILGAN TALABALAR RO'YXATI", f"{T['sem_label']} · {T['scope']} · Shartlar: {cond}", len(head))
    rows, i = [], 0
    for cc in T["courses"]:
        for r in cc["rows"]:
            i += 1
            rows.append([i, r["name"], r["hemis_id"], r["faculty"], r["grp"], f"{r['level']} · {r['course']}-kurs", FORMS.get(r["study_form"], r["study_form"]),
                         r["gpa"], r["avg_score"], r["attendance"] if r["attendance"] is not None else "qayd etilmaydi", r["n_f"], f"{r['rank']} / {r['n']}", r["pct"]])
    _xlsx_table(ws, st, head, rows)
    for col, wd in zip("ABCDEFGHIJKLM", (5, 34, 15, 30, 13, 18, 11, 8, 12, 13, 9, 13, 9)): ws.column_dimensions[col].width = wd
    _xlsx_signers(ws, st, who)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def _file(data: bytes, name: str, mt: str) -> Response:
    return Response(data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store",
                                                  "X-Content-Type-Options": "nosniff"})

def _ascii(s: str) -> str:
    return "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "_" for ch in s or "")

def _who(c: Ctx) -> str:
    n = c.user.get("full_name") or ""
    return f"{c.title} — {n.split(':', 1)[1].strip()}" if ":" in n else c.title

# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

@router.get("/api/reyting/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi"); ensure()
    return meta(c)

@router.get("/api/reyting/overview")
def api_overview(request: Request, sem: int = AR.RATING_SEMESTER):
    c = C(request); guard(c, "umumiy ko'rinish", f"semestr {sem}"); ensure()
    return overview(c, _sem(sem))

@router.get("/api/reyting/list")
def api_list(request: Request, sem: int = AR.RATING_SEMESTER, level: str = "institute", faculty: int = 0, course: int = 0, group: int = 0,
             form: str = "", flag: str = "", q: str = "", sort: str = "place", dir: str = "", page: int = 1, per: int = 50):
    c = C(request); guard(c, "reyting ro'yxati", f"semestr {sem}, daraja {level}" + (f", qidiruv «{q[:40]}»" if q else ""), names=True); ensure()
    return ranking(c, sem, level, faculty, course, group, form[:20], flag, q.strip()[:60], sort, dir, page, per)

@router.get("/api/reyting/student/{sid}")
def api_student(sid: int, request: Request):
    c = C(request); guard(c, "talaba reyting kartasi", str(sid), names=True); ensure()
    return student_card(c, sid)

@router.get("/api/reyting/qaydnoma/{gid}")
def api_qaydnoma(gid: int, request: Request, sem: int = AR.RATING_SEMESTER):
    c = C(request); guard(c, "reyting qaydnomasi", f"guruh {gid}, semestr {sem}", names=True); ensure()
    return qaydnoma(c, gid, sem)

@router.get("/api/reyting/qaydnoma/{gid}/export")
def api_qaydnoma_export(gid: int, request: Request, sem: int = AR.RATING_SEMESTER, fmt: str = "xlsx"):
    c = C(request)
    if fmt not in ("xlsx", "docx"): raise HTTPException(400, "Format: xlsx yoki docx")
    guard(c, f"reyting qaydnomasi eksporti (.{fmt})", f"guruh {gid}, semestr {sem}", names=True); ensure()
    Q = qaydnoma(c, gid, sem)
    name = f"reyting_qaydnomasi_{_ascii(Q['group']['name'])}_sem{sem}.{fmt}"
    return _file(qaydnoma_xlsx(Q, _who(c)) if fmt == "xlsx" else qaydnoma_docx(Q, _who(c)), name, XLSX if fmt == "xlsx" else DOCX)

@router.get("/api/reyting/dynamics")
def api_dynamics(request: Request, level: str = "course", limit: int = 15):
    c = C(request); guard(c, "dinamika", f"daraja {level}"); ensure()
    return dynamics(c, level, limit)

@router.get("/api/reyting/top")
def api_top(request: Request, sem: int = AR.RATING_SEMESTER, pct: float = AR.TOP_DEFAULTS["pct"], min_att: float = AR.TOP_DEFAULTS["min_att"],
            max_f: int = AR.TOP_DEFAULTS["max_f"]):
    c = C(request); guard(c, "a'lochilar ro'yxati", f"semestr {sem}, {pct}%, davomat ≥ {min_att}, F ≤ {max_f}", names=True); ensure()
    return top_list(c, sem, pct, min_att, max_f)

@router.get("/api/reyting/top/export")
def api_top_export(request: Request, sem: int = AR.RATING_SEMESTER, pct: float = AR.TOP_DEFAULTS["pct"], min_att: float = AR.TOP_DEFAULTS["min_att"],
                   max_f: int = AR.TOP_DEFAULTS["max_f"]):
    c = C(request); guard(c, "a'lochilar ro'yxati eksporti (.xlsx)", f"semestr {sem}, {pct}%", names=True); ensure()
    T = top_list(c, sem, pct, min_att, max_f)
    return _file(top_xlsx(T, _who(c)), f"alochilar_sem{sem}_{int(T['params']['pct'])}foiz.xlsx", XLSX)

@router.get("/api/reyting/units")
def api_units(request: Request, kind: str = "group", sem: int = AR.RATING_SEMESTER):
    c = C(request); guard(c, "bo'linmalar reytingi", f"{kind}, semestr {sem}"); ensure()
    return units(c, kind, sem)

@router.get("/api/reyting/methodology")
def api_methodology(request: Request):
    c = C(request); guard(c, "metodika"); ensure()
    return methodology(_con)

@router.post("/api/reyting/recompute")
def api_recompute(request: Request):
    c = C(request)
    ok = c.role.key in RECOMPUTE
    rbac.audit(_con, c, "reyting: qayta hisoblash", RES, ok)
    if not ok: raise AccessDenied("⛔ Reytingni qayta hisoblashni Registrator ofisi yoki Akademik faoliyatni boshqarish bo'limi boshlaydi. So'rov audit jurnaliga yozildi.")
    with _lock:
        return rebuild(_con, f"qo'lda: {_who(c)}")
