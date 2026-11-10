"""Ma'lumot servislari. Har bir funksiya avval RBAC tekshiruvidan o'tadi va faqat ruxsat etilgan ko'lamni qaytaradi."""
import datetime as dt, sqlite3
from . import clock
from . import db, academic_rules as AR
from .rbac import (Ctx, require, AccessDenied, KPI, ACADEMIC, STUDENTS, CONTRACTS, FINANCE, PAYROLL, HR, SCIENCE,
                   INTL, ADMISSIONS, YOUTH, MASTERS, TASKS, AUDIT)

# "Bugun" — har so'rovda clock.today() (Toshkent sanasi; yarim tundan keyin yangi kun). Demo ma'lumotlar seed paytida o'sha kunga
# suriladi (app/dateshift.py). Eski `S.TODAY` nomi faqat moslik uchun: atribut har murojaatda qayta hisoblanadi (PEP 562).
# `from .services import TODAY` ISHLATMANG — import paytida qotib qoladi; to'g'ridan-to'g'ri clock.today() chaqiring.
def __getattr__(name):
    if name == "TODAY": return clock.today()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def _g(con, ctx, res, action, quiet):
    if quiet:
        if not ctx.can(res):
            raise AccessDenied(res)
    else:
        require(con, ctx, res, action)

def mln(x):  # so'mni mln/mlrd ko'rinishga
    return f"{x/1e9:.2f} mlrd so'm" if abs(x) >= 1e9 else f"{x/1e6:.1f} mln so'm"

# ---------- O'quv ----------
def academic_overview(con, ctx: Ctx, quiet=False):
    _g(con, ctx, ACADEMIC, "o'zlashtirish ko'rsatkichlari", quiet)
    sc = ctx.student_scope("s")
    by = "f.name" if ctx.role.scope == "institut" else "g.name"
    rows = db.rows(con, f"""SELECT {by} AS name, COUNT(*) n, ROUND(AVG(s.gpa),1) gpa, ROUND(AVG(s.gpa_prev),1) gpa_prev,
        ROUND(AVG(s.attendance),1) attendance FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
        WHERE {sc} AND s.status='faol' GROUP BY 1 ORDER BY 1""")
    # gpa / gpa_prev — o'rtacha ball (100): oxirgi va undan oldingi yakunlangan semestr (academic_rules.refresh_student_metrics, baholardan).
    # 1-kurslarda yakunlangan semestr yo'q (NULL) — o'rtachaga kirmaydi; faqat 1-kurslardan iborat guruh qatori ko'rsatilmaydi.
    rows = [r for r in rows if r["gpa"] is not None]
    for r in rows: r["delta"] = round(r["gpa"] - r["gpa_prev"], 1) if r["gpa_prev"] is not None else None
    total = db.one(con, f"""SELECT COUNT(*) n, ROUND(AVG(gpa),1) gpa, ROUND(AVG(gpa_prev),1) gpa_prev, ROUND(AVG(attendance),1) attendance,
                            COUNT(gpa) n_scored FROM students s WHERE {sc} AND status='faol'""")
    # keskin (4 balldan ko'p) pasaygan guruhlar — hammasi; panelda eng ko'p pasaygan 8 tasi
    drops = db.rows(con, f"""SELECT g.name, g.course, f.name faculty, COUNT(*) n, ROUND(AVG(s.gpa),1) gpa, ROUND(AVG(s.gpa_prev),1) gpa_prev,
        ROUND(AVG(s.gpa)-AVG(s.gpa_prev),1) delta, ROUND(AVG(s.attendance),1) attendance, SUM(s.gpa) gsum, SUM(s.gpa_prev) psum
        FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
        WHERE {sc} GROUP BY g.id HAVING delta < -4 ORDER BY delta""")
    for r in drops: r["delta"] = round(r["gpa"] - r["gpa_prev"], 1)   # ko'rsatilgan ikki raqamdan — "57.6 dan 46.2 ga (−11.4)" doim mos
    drops.sort(key=lambda r: (r["delta"], r["name"]))
    return {"scope": ctx.scope_label(con), "total": total, "breakdown": rows, "breakdown_by": "fakultet" if by == "f.name" else "guruh",
            "metric": {"label": AR.SCORE_LABEL, "def": AR.SCORE_DEF, "sem": AR.SEMESTER_SHORT[AR.RATING_SEMESTER],
                       "prev_sem": AR.SEMESTER_SHORT[AR.RATING_SEMESTER - 1]},
            "declining_groups": [{k: v for k, v in r.items() if k not in ("gsum", "psum")} for r in drops[:8]],
            "declining_count": len(drops), "declining_clusters": decline_clusters(drops)}

def decline_clusters(drops):
    """Pasaygan guruhlarni bitta ildiz sabab bo'yicha birlashtirish: fakultet + kurs. Eng katta klaster birinchi."""
    cl = {}
    for g in drops:
        c = cl.setdefault((g["faculty"], g["course"]), {"faculty": g["faculty"], "course": g["course"], "groups": 0, "students": 0,
                                                         "_g": 0.0, "_p": 0.0, "group_names": [], "worst": None})
        c["groups"] += 1; c["students"] += g["n"]; c["_g"] += g["gsum"]; c["_p"] += g["psum"]; c["group_names"].append(g["name"])
        if c["worst"] is None or g["delta"] < c["worst"]["delta"]:
            c["worst"] = {k: g[k] for k in ("name", "gpa_prev", "gpa", "delta", "attendance", "n")}
    out = []
    for c in cl.values():
        gs = [g["delta"] for g in drops if (g["faculty"], g["course"]) == (c["faculty"], c["course"])]
        c["gpa"], c["gpa_prev"] = round(c.pop("_g") / c["students"], 1), round(c.pop("_p") / c["students"], 1)
        c["delta"] = round(c["gpa"] - c["gpa_prev"], 1)
        c["delta_min"], c["delta_max"] = max(gs), min(gs)     # eng kichik va eng katta pasayish (manfiy)
        out.append(c)
    return sorted(out, key=lambda c: (-c["groups"], c["delta"]))

def _num(x): return f"−{abs(x)}" if x < 0 else f"{x}"     # tipografik minus

def decline_text(c):
    """Klaster ogohlantirishi: ikkala raqam bilan ("57.6 dan 46.2 ga"), "11.5 ballga tushgan" emas."""
    w = c["worst"]
    att = f", davomat {w['attendance']}%" if w.get("attendance") is not None else ""
    if c["groups"] == 1:
        return f"{w['name']} guruhida ({c['faculty']}, {c['course']}-kurs) o'rtacha ball {w['gpa_prev']} dan {w['gpa']} ga pasaygan ({_num(w['delta'])}){att}"
    rng = _num(c["delta_min"]) if c["delta_min"] == c["delta_max"] else f"{_num(c['delta_min'])}…{_num(c['delta_max'])}"
    return (f"{c['faculty']}, {c['course']}-kurs: {c['groups']} ta guruhda o'rtacha ball keskin pasaygan — {c['gpa_prev']} dan {c['gpa']} ga "
            f"({_num(c['delta'])}; guruhlar bo'yicha {rng}); eng ko'p: {w['name']} — {w['gpa_prev']} dan {w['gpa']} ga{att}")

# «O'qishda xavf» — YAGONA ta'rif (academic_rules.RISK_DEF): faol talaba, o'zlashtirish yoki davomat bo'yicha holati «kritik»/«jiddiy».
# Daraja Talabalar markazi qoidalari (student_ops) — academic_rules.akademik_level / davomat_level — bilan hisoblanadi; panel,
# ogohlantirishlar, Talabalar markazi (serious_students / metrics.at_risk) va agent bir xil sonni ko'radi. Kontrakt qarzi kirmaydi.
RISK_LABEL = AR.RISK_LABEL
RISK_DEF = AR.RISK_DEF
RISK_DEF_PRELIM = RISK_DEF + " (holatlar jadvali hali to'lmagan — xuddi shu qoidalar bilan baholardan va davomatdan to'g'ridan-to'g'ri hisoblandi)"
LV = {2: "kritik", 3: "jiddiy"}

def _risk_value(levels: dict) -> int:
    """Saralash uchun 0–100: eng yuqori daraja (kritik 60, jiddiy 80) + ikkala yo'nalishda ham bo'lsa 15."""
    return min(100, 20 * (max(levels.values()) + 1) + (15 if len(levels) > 1 else 0))

def _reason_text(rule, f):
    if rule == "akademik":
        parts = []
        if f.get("fails"): parts.append(f"akademik qarz: {len(f['fails'])} ta fan")
        if f.get("oraliq_low"): parts.append(f"oraliq < {AR.ORALIQ_MIN}: {len(f['oraliq_low'])} ta fan")
        if f.get("gpa5") is not None and not f.get("gpa_ok", True): parts.append(f"GPA (5) {f['gpa5']}")
        return ", ".join(parts) or "o'zlashtirish"
    return f"sababsiz {f.get('hours')} soat (joriy semestr)"

_RISK_CACHE: dict = {}
RISK_TTL = 15        # soniya: bitta panel so'rovi (KPI + ogohlantirishlar + panel) uchta to'liq hisob o'rniga bittasini qiladi

def _risk_core(con, sc: str):
    """(faol talabalar soni, xavfdagilar [ro'yxat, xavf bo'yicha saralangan], model hisoblanganmi). Qisqa muddat keshlanadi."""
    import time, json
    hit = _RISK_CACHE.get(sc)
    if hit and time.monotonic() - hit[0] < RISK_TTL: return hit[1]
    rows = db.rows(con, f"""SELECT s.id, s.full_name, s.hemis_id, g.name grp, g.course, f.name faculty, s.gpa, s.gpa_prev, s.attendance
        FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id WHERE {sc} AND s.status='faol'""")
    sig, evaluated = {}, False
    try:
        evaluated = con.execute("SELECT 1 FROM ops_cases LIMIT 1").fetchone() is not None
        if evaluated:
            for sid, rule, lvl, facts in con.execute(f"""SELECT student_id, rule, level, facts FROM ops_cases WHERE status='ochiq'
                                                         AND rule IN ('akademik','davomat') AND level>={AR.AT_RISK_LEVEL}"""):
                sig.setdefault(sid, {})[rule] = (lvl, json.loads(facts or "{}"))
    except sqlite3.OperationalError:     # jadval hali yo'q (yangi baza)
        evaluated = False
    if not evaluated:                    # xuddi shu qoidalar — baholar va davomatdan to'g'ridan-to'g'ri
        from . import student_ops as OPS
        try:
            P = OPS.policy(con)
            for sid, (lvl, f) in OPS.akademik_signals(con, P, f"s.status='faol' AND {sc}").items():
                if lvl >= AR.AT_RISK_LEVEL: sig.setdefault(sid, {})["akademik"] = (lvl, f)
            for sid, h, form in con.execute(f"""SELECT a.student_id, SUM(a.hours), s.study_form FROM absences a JOIN students s ON s.id=a.student_id
                                          WHERE s.status='faol' AND {sc} AND {OPS._unexcused_sql(P, clock.today())} GROUP BY a.student_id"""):
                lvl = OPS.davomat_level(h, P, form)
                if lvl >= AR.AT_RISK_LEVEL: sig.setdefault(sid, {})["davomat"] = (lvl, {"hours": h})
        except sqlite3.OperationalError:
            pass
    risky = [r for r in rows if r["id"] in sig]
    for r in risky:
        x = sig[r["id"]]
        r["risk"] = _risk_value({k: v[0] for k, v in x.items()})
        r["reasons"] = "; ".join(f"{'o' + chr(39) + 'zlashtirish' if k == 'akademik' else 'davomat'} ({LV.get(v[0], v[0])}): {_reason_text(k, v[1])}"
                                 for k, v in sorted(x.items()))
        if r["gpa"] is None: r["gpa"] = "—"   # 1-kurs: yakunlangan semestr yo'q
    risky.sort(key=lambda x: (-x["risk"], x["full_name"]))
    res = (len(rows), risky, evaluated)
    if len(_RISK_CACHE) > 64: _RISK_CACHE.clear()
    _RISK_CACHE[sc] = (time.monotonic(), res)
    return res

def at_risk_students(con, ctx: Ctx, limit=15, quiet=False):
    _g(con, ctx, STUDENTS, "xavf ostidagi talabalar", quiet)
    n_all, risky, evaluated = _risk_core(con, ctx.student_scope("s"))
    by_group = {}
    for r in risky:
        by_group[r["grp"]] = by_group.get(r["grp"], 0) + 1
    out = {"scope": ctx.scope_label(con), "count": len(risky), "of": n_all,
           "by_group": sorted([{"group": k, "count": v} for k, v in by_group.items()], key=lambda x: -x["count"])[:10]}
    out["model"] = "yagona" if evaluated else "dastlabki"
    # "O'qishda xavf" — TALABALAR soni (o'zlashtirish yoki davomat). Talabalar markazidagi "holatlar" boshqa ko'rsatkich:
    # u barcha qoidalarni (kontrakt, hujjat, ta'til...) sanaydi va bitta talabada bir nechta holat bo'lishi mumkin.
    out["label"] = RISK_LABEL
    out["definition"] = RISK_DEF if evaluated else RISK_DEF_PRELIM
    if ctx.aggregate_only(STUDENTS):
        out["note"] = "Shaxsiy ma'lumotlar bu darajaga faqat jamlangan shaklda chiqadi"
    else:
        out["students"] = [dict(r) for r in risky[:limit]]   # kesh buzilmasin — nusxa
    return out

def teacher_groups(con, ctx: Ctx, quiet=False):
    _g(con, ctx, ACADEMIC, "o'z guruhlari", quiet)
    if ctx.role.scope != "o'qituvchi":
        return None
    # Joriy semestr: yakuniy nazorat hali o'tmagan — oraliq nazorat (30 ballik) o'rtachasi va 12 dan pastlar (yakuniyga kirmaydi).
    # «O'tgan sem.» — guruhning oxirgi yakunlangan semestrdagi o'rtacha bali (100, barcha fanlar; fanlar semestrma-semestr farq qiladi).
    cur, prv = AR.CURRENT_SEMESTER, AR.RATING_SEMESTER
    return db.rows(con, f"""SELECT g.name grp, tg.subject, COUNT(gr.student_id) n, ROUND(AVG(gr.oraliq),1) avg_score, {AR.ORALIQ_MAX} max_score,
        (SELECT ROUND(AVG(x.score),1) FROM grades x JOIN students sx ON sx.id=x.student_id WHERE sx.group_id=g.id AND x.semester={prv}) prev_score,
        SUM(COALESCE(gr.oraliq,0) < {AR.ORALIQ_MIN}) failing FROM teacher_groups tg JOIN groups_ g ON g.id=tg.group_id
        LEFT JOIN grades gr ON gr.subject=tg.subject AND gr.semester={cur} AND gr.student_id IN (SELECT id FROM students WHERE group_id=g.id AND status='faol')
        WHERE tg.teacher_id=? GROUP BY g.id, tg.subject""", (ctx.user["teacher_id"],))

# ---------- Moliya ----------
def contracts_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, CONTRACTS, "kontrakt to'lovlari", quiet)
    t = db.one(con, "SELECT SUM(contract_amount) total, SUM(paid_amount) paid, SUM(contract_amount>paid_amount) debtors, COUNT(*) n FROM students WHERE payment_type='kontrakt'")
    t["debt"] = t["total"] - t["paid"]; t["pct"] = round(100 * t["paid"] / t["total"], 1)
    by_fac = db.rows(con, """SELECT f.name, SUM(contract_amount) total, SUM(paid_amount) paid, SUM(contract_amount>paid_amount) debtors
        FROM students s JOIN faculties f ON f.id=s.faculty_id WHERE payment_type='kontrakt' GROUP BY f.id""")
    for r in by_fac: r["pct"] = round(100 * r["paid"] / r["total"], 1); r["debt"] = r["total"] - r["paid"]
    worst = db.rows(con, """SELECT g.name grp, f.name faculty, SUM(contract_amount-paid_amount) debt, SUM(contract_amount>paid_amount) debtors,
        ROUND(100.0*SUM(paid_amount)/SUM(contract_amount),1) pct FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
        WHERE payment_type='kontrakt' GROUP BY g.id ORDER BY pct LIMIT 6""")
    return {"total": t, "by_faculty": by_fac, "worst_groups": worst}

def finance_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, FINANCE, "byudjet bajarilishi", quiet)
    cats = db.rows(con, "SELECT category, SUM(planned) planned, SUM(actual) actual FROM budget GROUP BY category ORDER BY planned DESC")
    for c in cats: c["pct"] = round(100 * c["actual"] / c["planned"], 1)
    months = db.rows(con, "SELECT month, SUM(planned) planned, SUM(actual) actual FROM budget GROUP BY month ORDER BY month")
    over = db.rows(con, """SELECT category, month, planned, actual, ROUND(100.0*actual/planned-100,1) over_pct FROM budget
        WHERE actual > planned*1.1 ORDER BY month DESC, over_pct DESC""")
    tot = {"planned": sum(c["planned"] for c in cats), "actual": sum(c["actual"] for c in cats)}
    tot["pct"] = round(100 * tot["actual"] / tot["planned"], 1)
    return {"total": tot, "categories": cats, "months": months, "overruns": over}

def payroll_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, PAYROLL, "ish haqi fondi", quiet)
    agg = db.rows(con, "SELECT unit, COUNT(*) n, SUM(salary) fund, ROUND(AVG(salary)) avg FROM staff WHERE id NOT IN (SELECT staff_id FROM hr_files WHERE status='boshatilgan') GROUP BY unit ORDER BY fund DESC")
    out = {"by_unit": agg, "total_fund": sum(a["fund"] for a in agg)}
    if not ctx.aggregate_only(PAYROLL):
        out["staff"] = db.rows(con, "SELECT full_name, unit, position, salary FROM staff WHERE id NOT IN (SELECT staff_id FROM hr_files WHERE status='boshatilgan') ORDER BY salary DESC LIMIT 20")
    return out

def hr_list(con, ctx: Ctx, quiet=False):
    _g(con, ctx, HR, "xodimlar ro'yxati", quiet)
    return {"staff": db.rows(con, "SELECT full_name, unit, position, hired, passport FROM staff WHERE id NOT IN (SELECT staff_id FROM hr_files WHERE status='boshatilgan') ORDER BY unit LIMIT 40"),
            "by_unit": db.rows(con, "SELECT unit, COUNT(*) n FROM staff WHERE id NOT IN (SELECT staff_id FROM hr_files WHERE status='boshatilgan') GROUP BY unit ORDER BY n DESC")}

# ---------- Ilmiy ----------
def science_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, SCIENCE, "ilmiy salohiyat", quiet)
    ts = ctx.teacher_scope("t")
    kinds = db.rows(con, f"SELECT p.kind, COUNT(*) n FROM publications p JOIN teachers t ON t.id=p.teacher_id WHERE {ts} AND p.year=2026 GROUP BY 1 ORDER BY n DESC")
    by_dept = db.rows(con, f"""SELECT d.name, COUNT(DISTINCT t.id) teachers, SUM(t.degree IN ('PhD','DSc')) * 1.0 / COUNT(DISTINCT t.id) deg,
        (SELECT COUNT(*) FROM publications p JOIN teachers t2 ON t2.id=p.teacher_id WHERE t2.department_id=d.id AND p.kind IN ('Scopus','Web of Science') AND p.year=2026) scopus
        FROM teachers t JOIN departments d ON d.id=t.department_id WHERE {ts} GROUP BY d.id ORDER BY scopus DESC""")
    for r in by_dept: r["degree_pct"] = round(100 * r.pop("deg"), 0)
    deg = db.one(con, f"SELECT COUNT(*) n, SUM(degree IN ('PhD','DSc')) deg FROM teachers t WHERE {ts}")
    top = db.rows(con, f"""SELECT t.full_name, t.degree, t.h_index, COUNT(p.id) pubs, SUM(p.kind IN ('Scopus','Web of Science')) scopus
        FROM teachers t LEFT JOIN publications p ON p.teacher_id=t.id WHERE {ts} GROUP BY t.id ORDER BY scopus DESC, pubs DESC LIMIT 8""")
    zero = db.one(con, f"SELECT COUNT(*) n FROM teachers t WHERE {ts} AND id NOT IN (SELECT teacher_id FROM publications WHERE year>=2025)")["n"]
    grants = db.rows(con, "SELECT g.title, g.funder, g.amount, g.status, t.full_name leader FROM grants g JOIN teachers t ON t.id=g.leader_id ORDER BY g.amount DESC") \
        if ctx.role.scope == "institut" else []
    return {"scope": ctx.scope_label(con), "kinds_2026": kinds, "by_department": by_dept, "teachers": deg["n"],
            "degree_pct": round(100 * (deg["deg"] or 0) / max(1, deg["n"]), 1), "top_authors": top, "no_pubs_since_2025": zero, "grants": grants}

def international_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, INTL, "xalqaro hamkorlik", quiet)
    p = db.rows(con, "SELECT * FROM partners ORDER BY expires")
    for r in p: r["days_left"] = (dt.date.fromisoformat(r["expires"]) - clock.today()).days
    return {"partners": p, "active": sum(r["status"] == "faol" for r in p), "expiring": [r for r in p if 0 <= r["days_left"] <= 60],
            "exchanged": sum(r["students_exchanged"] for r in p)}

# ---------- Qabul / yoshlar / magistratura ----------
def admissions_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, ADMISSIONS, "qabul statistikasi", quiet)
    funnel = db.rows(con, "SELECT status, COUNT(*) n FROM applicants GROUP BY status ORDER BY n DESC")
    by_dir = db.rows(con, """SELECT direction, COUNT(*) applied, SUM(status="talaba bo'ldi") enrolled, ROUND(AVG(score),1) avg_score
        FROM applicants GROUP BY direction ORDER BY applied DESC""")
    for r in by_dir: r["conv"] = round(100 * r["enrolled"] / r["applied"], 1)
    weekly = db.rows(con, "SELECT strftime('%W', applied) wk, MIN(applied) start, COUNT(*) n FROM applicants GROUP BY wk ORDER BY wk")
    return {"total": sum(f["n"] for f in funnel), "funnel": funnel, "by_direction": by_dir, "weekly": weekly}

def youth_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, YOUTH, "yoshlar ishlari", quiet)
    d = db.rows(con, "SELECT * FROM dormitory")
    try:   # hamkor turar joylar (app/yoshlar.py) — jamlangan: bino, o'rinlar, band (ismlarsiz)
        d += db.rows(con, """SELECT b.name building, COALESCE(SUM(rm.beds),0) capacity,
                (SELECT COUNT(*) FROM yj_residents r JOIN yj_rooms r2 ON r2.id=r.room_id WHERE r2.building_id=b.id AND r.status IN ('band','yashaydi')) occupied
              FROM yj_buildings b LEFT JOIN yj_rooms rm ON rm.building_id=b.id WHERE COALESCE(b.active,1)=1 GROUP BY b.id""")
    except Exception: pass
    d = [r for r in d if r.get("capacity")]
    for r in d: r["pct"] = round(100 * r["occupied"] / r["capacity"], 1)
    return {"events": db.rows(con, "SELECT title, date, kind, participants FROM events ORDER BY date DESC"), "dormitory": d,
            "appeals": db.rows(con, "SELECT date, category, text, status FROM appeals ORDER BY date DESC"),
            "appeals_open": db.one(con, "SELECT COUNT(*) n FROM appeals WHERE status!='hal qilindi'")["n"]}

def masters_summary(con, ctx: Ctx, quiet=False):
    _g(con, ctx, MASTERS, "magistratura", quiet)
    return {"stages": db.rows(con, "SELECT stage, COUNT(*) n FROM masters GROUP BY stage ORDER BY n DESC"),
            "supervisors": db.rows(con, """SELECT t.full_name, t.degree, COUNT(*) n FROM masters m JOIN teachers t ON t.id=m.supervisor_id
                GROUP BY t.id ORDER BY n DESC LIMIT 8"""),
            "total": db.one(con, "SELECT COUNT(*) n FROM masters")["n"]}

# ---------- Topshiriqlar ----------
def tasks_list(con, ctx: Ctx, quiet=False):
    _g(con, ctx, TASKS, "majlis topshiriqlari", quiet)
    # Ko'rinish va "mine" — bo'lim bo'yicha (Portal org_units, app/decisions.py reestri): bo'limli topshiriq o'z bo'limi xodimlariga,
    # biriktirilgan xodimga va kurator prorektorga ko'rinadi; "mine" — biriktirilgan xodim yoki bo'lim rahbari.
    # Bo'limsiz eski topshiriq — rol bo'yicha, lekin ko'p bo'limli rollarda (kafedra, tyutor...) mas'ul matnidagi bo'lim ham mos bo'lishi shart.
    from . import decisions as DEC
    uid, role = int(ctx.user["id"]), ctx.role.key
    u = DEC.unit_of(ctx)
    head = bool(u) and DEC.is_head(ctx, u)
    if role in ("rektor", "kengash", "kotib"): where, args = "1=1", []
    else:
        us = sorted(({u} if u else set()) | DEC.curated_units(ctx))
        where = "((t.unit IS NULL AND t.assignee_role=?) OR t.assignee_user=?" + (f" OR t.unit IN ({','.join('?' * len(us))})" if us else "") + ")"
        args = [role, uid, *us]
    rows = db.rows(con, f"""SELECT t.*, m.title meeting, m.date meeting_date, m.source FROM tasks t JOIN meetings m ON m.id=t.meeting_id
                            WHERE {where} AND t.status!='qoralama' ORDER BY COALESCE(t.due, '9999'), t.id""", args)
    if args:   # boshqa kafedra/fakultetning bo'limsiz eski topshiriqlari ko'rinmaydi
        rows = [r for r in rows if r.get("unit") or r.get("assignee_user") == uid or DEC.legacy_mine(ctx, r)]
    now = clock.now()
    for r in rows:
        r["decision"] = bool(r.get("source"))
        r["mine"] = r.get("assignee_user") == uid or DEC.legacy_mine(ctx, r) or (head and r.get("unit") == u)
        due = r.get("due_at") or r.get("due")
        if not due:                              # muddat majlisda aytilmagan — o'ylab topilmaydi
            r["overdue"], r["days"] = False, None; continue
        try:
            d = dt.datetime.fromisoformat(due) if "T" in due else dt.datetime.combine(dt.date.fromisoformat(due), dt.time(23, 59))
        except (ValueError, TypeError):
            r["overdue"], r["days"] = False, None; continue   # buzuq sana butun panelni yiqitmasin
        r["overdue"] = r["status"] != "bajarildi" and d < now
        r["days"] = (d.date() - clock.today()).days
    from . import directives as DIR   # majlisdan tashqari topshiriqlar (meeting_id yo'q): ko'rinish, "mine", muddat — app/directives.py
    rows += DIR.task_rows(ctx)
    return {"tasks": rows, "overdue": sum(r["overdue"] for r in rows), "done": sum(r["status"] == "bajarildi" for r in rows)}

def audit_log(con, ctx: Ctx, limit=50, quiet=False):
    _g(con, ctx, AUDIT, "audit jurnali", quiet)
    return db.rows(con, "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))

# ---------- Ogohlantirishlar (proaktiv) ----------
def alerts(con, ctx: Ctx):
    out = []
    def safe(fn, *a):
        try: return fn(con, ctx, *a, quiet=True)
        except AccessDenied: return None
    a = safe(academic_overview)
    if a:   # bir fakultet+kurs guruhlari — bitta ildiz sabab, bitta ogohlantirish (guruhlar ro'yxati panels.academic da)
        for c in a["declining_clusters"][:3]:
            out.append({"level": "high", "area": "O'quv", "text": decline_text(c)})
    r = safe(at_risk_students)
    if r and r["count"]:
        out.append({"level": "mid", "area": "Talabalar", "text": f"{RISK_LABEL}: {r['count']:,} nafar talaba".replace(",", " ") +
                    f" — o'zlashtirish (akademik qarz, past oraliq) yoki joriy semestr davomati bo'yicha kritik/jiddiy holat"
                    f" (eng ko'p: {r['by_group'][0]['group']} — {r['by_group'][0]['count']} nafar)"})
    c = safe(contracts_summary)
    if c:
        w = c["worst_groups"][0]
        out.append({"level": "mid", "area": "Kontrakt", "text": f"Kontrakt tushumi {c['total']['pct']}%. Qarz: {mln(c['total']['debt'])}. Eng past: {w['grp']} ({w['pct']}%)"})
    f = safe(finance_summary)
    if f and f["overruns"]:
        o = f["overruns"][0]
        out.append({"level": "high", "area": "Moliya", "text": f"{o['category']}: {o['month']} oyida xarajat {mln(o['actual'])} — rejadagi {mln(o['planned'])} dan {o['over_pct']}% ko'p (ketma-ket {sum(1 for x in f['overruns'] if x['category']==o['category'])} oy)"})
    i = safe(international_summary)
    if i:
        for p in i["expiring"]:
            out.append({"level": "mid", "area": "Xalqaro", "text": f"{p['name']} ({p['country']}) bilan shartnoma {p['days_left']} kundan keyin tugaydi"})
    t = safe(tasks_list)
    if t and t["overdue"]:
        out.append({"level": "high", "area": "Topshiriqlar", "text": f"{t['overdue']} ta majlis topshirig'i muddati o'tgan"})
    y = safe(youth_summary)
    if y:
        full = [d for d in y["dormitory"] if d["pct"] >= 95]
        if full: out.append({"level": "low", "area": "Yotoqxona", "text": f"{full[0]['building']} {full[0]['pct']}% to'lgan"})
        if y["appeals_open"]: out.append({"level": "low", "area": "Murojaatlar", "text": f"{y['appeals_open']} ta anonim murojaat hal qilinmagan"})
    from . import service
    out += service.alerts(con, ctx)
    from . import occupancy
    out += occupancy.alerts(con, ctx)
    order = {"high": 0, "mid": 1, "low": 2}
    return sorted(out, key=lambda x: order[x["level"]])

# ---------- KPI ----------
# Har bir KPI elementi (eski maydonlar o'zgarmagan — joriy UI ishlayveradi):
#   label, value, sub            — ko'rsatiladigan matn
#   trend (ixtiyoriy)            — o'tgan davrga nisbatan o'zgarish (son)
#   bad (ixtiyoriy)              — eski UI uchun qizil belgi
# Yangi (ixtiyoriy) maydonlar — dizayn uchun:
#   key        — barqaror identifikator (label o'zgarsa ham o'zgarmaydi)
#   source     — ma'lumot manbasi (demo bazada nimani ifodalasa — o'sha tizim nomi)
#   updated    — ma'lumot holati sanasi, ISO datetime
#   spark      — mini-grafik uchun qisqa sonlar qatori; har doim bazadan deterministik hisoblanadi (so'rov paytida tasodifiy emas)
#   spark_kind — "line": vaqt qatori (eskidan yangiga) · "bars": kategoriyalar (spark_labels — nomlari)
#                "ring": [qism, butun] (ulush = qism/butun) · "progress": [joriy, maksimal] bir xil birlikda
#   spark_labels (ixtiyoriy) — spark nuqtalari/ustunlari nomlari
def _sync_at():
    """HEMIS va buxgalteriya bilan kunlik sinxronlash vaqti. DEMO TAXMIN: jadval — har kuni 08:00 (demo bazada ma'lumot sun'iy)."""
    now = clock.now().replace(microsecond=0)
    t = dt.datetime.combine(now.date(), dt.time(8, 0))
    return (t if now >= t else t - dt.timedelta(days=1)).isoformat()

def _now_iso(): return clock.now().replace(microsecond=0).isoformat()

def _k(key, label, value, sub, source, updated, spark=None, spark_kind=None, labels=None, **old):
    k = {"label": label, "value": value, "sub": sub, **old, "key": key, "source": source, "updated": updated}
    if spark:
        k["spark"], k["spark_kind"] = spark, spark_kind
        if labels: k["spark_labels"] = labels
    return k

def kpis(con, ctx: Ctx):
    out = []
    def safe(fn):
        try: return fn(con, ctx, quiet=True)
        except AccessDenied: return None
    sync = _sync_at()
    a = safe(academic_overview)
    if a and not a["total"]["n"]:   # masalan, institut kafedrasi (Fundamental iqtisodiy fanlar) — o'z guruhlari yo'q
        out.append(_k("talabalar", "Talabalar", 0, "kafedraga biriktirilgan guruh yo'q", "HEMIS", sync)); a = None
    if a:
        t = a["total"]
        sc = ctx.student_scope("s")
        frm = {r["f"]: r["n"] for r in db.rows(con, f"SELECT COALESCE(study_form,'kunduzgi') f, COUNT(*) n FROM students s WHERE {sc} AND status='faol' GROUP BY 1")}
        k = lambda x: f"{x / 1000:.1f}k" if x >= 1000 else str(x)
        forms = [(f, lbl) for f, lbl in (("kunduzgi", "kunduzgi"), ("sirtqi", "sirtqi"), ("masofaviy", "masofaviy")) if frm.get(f)]
        sub = " · ".join(f"{lbl} {k(frm[f])}" for f, lbl in forms) or a["scope"]
        att = db.rows(con, f"""SELECT g.course, ROUND(AVG(s.attendance),1) a FROM students s JOIN groups_ g ON g.id=s.group_id
                               WHERE {sc} AND s.status='faol' AND s.attendance IS NOT NULL GROUP BY g.course ORDER BY g.course""")
        out += [_k("talabalar", "Faol talabalar", f"{t['n']:,}".replace(",", " "), sub, "HEMIS", sync,
                   [frm[f] for f, _ in forms], "bars", [lbl for _, lbl in forms]),
                # o'rtacha ball (100): oxirgi yakunlangan semestr (Reyting → umumiy ko'rinish bilan bir xil son); avvalgisi — undan oldingi semestr
                _k("ball", AR.SCORE_LABEL, t["gpa"], f"{AR.SEMESTER_SHORT[AR.RATING_SEMESTER]} · avvalgi semestr: {t['gpa_prev']}", "HEMIS (baholar)", sync,
                   [t["gpa_prev"], t["gpa"]], "line", [AR.SEMESTER_SHORT[AR.RATING_SEMESTER - 1], AR.SEMESTER_SHORT[AR.RATING_SEMESTER]],
                   trend=round(t["gpa"] - t["gpa_prev"], 1) if t["gpa"] is not None and t["gpa_prev"] is not None else None),
                _k("davomat", "Davomat", f"{t['attendance']}%", "kunduzgi va sirtqi (masofaviy — onlayn)", "HEMIS", sync,
                   [r["a"] for r in att], "bars", [f"{r['course']}-kurs" for r in att])]
    r = safe(at_risk_students)
    if r:
        last = db.one(con, "SELECT value FROM ops_policy WHERE key='_last_run'") if db.one(con, "SELECT 1 x FROM sqlite_master WHERE name='ops_policy'") else None
        upd = clock.from_ts(last["value"]).replace(microsecond=0).isoformat() if last else sync
        out.append(_k("oqishda_xavf", RISK_LABEL, r["count"], f"{round(100*r['count']/max(1,r['of']),1)}% faol talaba · o'zlashtirish yoki davomat (kritik/jiddiy)",
                      "Talabalar markazi qoidalari (HEMIS baholari va davomati)", upd, [r["count"], r["of"]], "ring", bad=True))
    c = safe(contracts_summary)
    if c:
        out.append(_k("kontrakt", "Kontrakt tushumi", f"{c['total']['pct']}%", f"qarz {mln(c['total']['debt'])}", "Buxgalteriya (kontrakt to'lovlari)", sync,
                      [c["total"]["pct"], 100], "progress"))
    try:   # kameralar: bugungi P1/P2 voqealar, oflayn kameralar, eng band bino (faqat auditoriyalar ruxsati borlarga)
        from . import camsec
        ck = camsec.kpi(con, ctx)
        if ck: out.append(ck)
    except Exception as e:
        print("camsec.kpi:", e)
    f = safe(finance_summary)
    if f:
        out.append(_k("byudjet", "Byudjet ijrosi", f"{f['total']['pct']}%", f"{mln(f['total']['actual'])} / {mln(f['total']['planned'])}",
                      "Buxgalteriya (byudjet ijrosi)", sync, [round(100 * m["actual"] / m["planned"], 1) for m in f["months"] if m["planned"]], "line",
                      [m["month"] for m in f["months"] if m["planned"]]))
    s = safe(science_summary)
    if s:
        sc = sum(k["n"] for k in s["kinds_2026"] if k["kind"] in ("Scopus", "Web of Science"))
        ts = ctx.teacher_scope("t")
        yr = db.rows(con, f"""SELECT p.year y, COUNT(*) n FROM publications p JOIN teachers t ON t.id=p.teacher_id WHERE {ts}
                              AND p.kind IN ('Scopus','Web of Science') AND p.year BETWEEN 2022 AND 2026 GROUP BY 1 ORDER BY 1""")
        out.append(_k("scopus", "Scopus/WoS 2026", sc, f"ilmiy daraja: {s['degree_pct']}%", "Ilmiy nashrlar bazasi", sync,
                      [x["n"] for x in yr], "line", [str(x["y"]) for x in yr]))
    i = safe(international_summary)
    if i:
        yrs = list(range(clock.today().year - 4, clock.today().year + 1))   # yil oxiridagi amaldagi shartnomalar soni (imzolangan va tugamagan)
        ps = i["partners"]
        act = [sum(1 for p in ps if p["signed"][:4] <= str(y) and p["expires"] >= (f"{y}-12-31" if y < clock.today().year else clock.today().isoformat())) for y in yrs]
        out.append(_k("hamkorlar", "Xalqaro hamkorlar", i["active"], f"{len(i['expiring'])} tasi tugamoqda", "Xalqaro shartnomalar reyestri", sync,
                      act, "line", [str(y) for y in yrs]))
    ad = safe(admissions_summary)
    if ad:
        wk = ad["weekly"][-10:]
        out.append(_k("qabul", "Qabul 2026", f"{ad['total']:,}".replace(",", " "), "ariza", "Qabul bazasi", sync,
                      [w["n"] for w in wk], "bars", [w["start"] for w in wk]))
    t = safe(tasks_list)
    if t: out.append(_k("topshiriqlar", "Topshiriqlar", f"{t['done']}/{len(t['tasks'])}", f"{t['overdue']} tasi muddati o'tgan",
                        "ISFT Core · majlis topshiriqlari", _now_iso(), [t["done"], len(t["tasks"])], "progress", bad=t["overdue"] > 0))
    y = safe(youth_summary)
    if y:
        wk = [(clock.today() - dt.timedelta(days=7 * (5 - j) + 6), clock.today() - dt.timedelta(days=7 * (5 - j))) for j in range(6)]   # oxirgi 6 hafta
        ser = [sum(1 for x in y["appeals"] if a0.isoformat() <= x["date"] <= a1.isoformat()) for a0, a1 in wk]
        out.append(_k("murojaatlar", "Murojaatlar", y["appeals_open"], "hal qilinmagan", "ISFT Core · anonim murojaatlar", _now_iso(),
                      ser, "bars", [a1.isoformat() for _, a1 in wk]))
    m = safe(masters_summary)
    if m: out.append(_k("magistrantlar", "Magistrantlar", m["total"], "dissertatsiya jarayonida", "Magistratura bazasi", sync,
                        [x["n"] for x in m["stages"]], "bars", [x["stage"] for x in m["stages"]]))
    try:
        h = hr_list(con, ctx, quiet=True)
        out.append(_k("xodimlar", "Xodimlar", sum(x["n"] for x in h["by_unit"]), "shtat", "Kadrlar bazasi", sync,
                      [x["n"] for x in h["by_unit"][:6]], "bars", [x["unit"] for x in h["by_unit"][:6]]))
    except AccessDenied: pass
    return out[:10]
