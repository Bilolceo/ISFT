"""Ma'lumot servislari. Har bir funksiya avval RBAC tekshiruvidan o'tadi va faqat ruxsat etilgan ko'lamni qaytaradi."""
import datetime as dt
from . import db
from .rbac import (Ctx, require, AccessDenied, KPI, ACADEMIC, STUDENTS, CONTRACTS, FINANCE, PAYROLL, HR, SCIENCE,
                   INTL, ADMISSIONS, YOUTH, MASTERS, TASKS, AUDIT)

TODAY = dt.date.today()   # demo ma'lumotlar seed paytida shu sanaga suriladi (app/dateshift.py)

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
    for r in rows: r["delta"] = round(r["gpa"] - r["gpa_prev"], 1)
    total = db.one(con, f"SELECT COUNT(*) n, ROUND(AVG(gpa),1) gpa, ROUND(AVG(gpa_prev),1) gpa_prev, ROUND(AVG(attendance),1) attendance FROM students s WHERE {sc} AND status='faol'")
    # eng ko'p pasaygan guruhlar
    drops = db.rows(con, f"""SELECT g.name, g.course, f.name faculty, COUNT(*) n, ROUND(AVG(s.gpa),1) gpa, ROUND(AVG(s.gpa)-AVG(s.gpa_prev),1) delta,
        ROUND(AVG(s.attendance),1) attendance FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
        WHERE {sc} GROUP BY g.id HAVING delta < -4 ORDER BY delta LIMIT 8""")
    return {"scope": ctx.scope_label(con), "total": total, "breakdown": rows, "breakdown_by": "fakultet" if by == "f.name" else "guruh", "declining_groups": drops}

def risk_score(s):
    r = 0
    if s["gpa"] < 56: r += 45
    elif s["gpa"] < 63: r += 25
    att = s["attendance"]            # masofaviy ta'limda auditoriya davomati yo'q (None) — hisobga olinmaydi
    if att is not None and att < 70: r += 30
    elif att is not None and att < 80: r += 15
    if s["gpa"] - s["gpa_prev"] < -10: r += 15
    if s["contract_amount"] and s["paid_amount"] / s["contract_amount"] < 0.5: r += 15
    return min(100, r)

def at_risk_students(con, ctx: Ctx, limit=15, quiet=False):
    _g(con, ctx, STUDENTS, "xavf ostidagi talabalar", quiet)
    sc = ctx.student_scope("s")
    rows = db.rows(con, f"""SELECT s.id, s.full_name, s.hemis_id, g.name grp, g.course, f.name faculty, s.gpa, s.gpa_prev, s.attendance,
        s.contract_amount, s.paid_amount FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
        WHERE {sc} AND s.status='faol'""")
    for r in rows:
        r["risk"] = risk_score(r)
        reasons = []
        if r["gpa"] < 63: reasons.append(f"past ball ({r['gpa']})")
        if r["attendance"] is not None and r["attendance"] < 80: reasons.append(f"davomat {r['attendance']}%")
        if r["gpa"] - r["gpa_prev"] < -10: reasons.append(f"ball {round(r['gpa_prev']-r['gpa'],1)} ga tushgan")
        if r["contract_amount"] and r["paid_amount"] / r["contract_amount"] < .5: reasons.append("kontrakt qarzi")
        r["reasons"] = ", ".join(reasons)
    risky = sorted([r for r in rows if r["risk"] >= 40], key=lambda x: -x["risk"])
    by_group = {}
    for r in risky:
        by_group[r["grp"]] = by_group.get(r["grp"], 0) + 1
    out = {"scope": ctx.scope_label(con), "count": len(risky), "of": len(rows),
           "by_group": sorted([{"group": k, "count": v} for k, v in by_group.items()], key=lambda x: -x["count"])[:10]}
    if ctx.aggregate_only(STUDENTS):
        out["note"] = "Shaxsiy ma'lumotlar bu darajaga faqat jamlangan shaklda chiqadi"
    else:
        for r in risky:
            r.pop("contract_amount"); r.pop("paid_amount")
        out["students"] = risky[:limit]
    return out

def teacher_groups(con, ctx: Ctx, quiet=False):
    _g(con, ctx, ACADEMIC, "o'z guruhlari", quiet)
    if ctx.role.scope != "o'qituvchi":
        return None
    return db.rows(con, """SELECT g.name grp, tg.subject, SUM(gr.semester=1) n, ROUND(AVG(CASE WHEN gr.semester=1 THEN gr.score END),1) avg_score,
        ROUND(AVG(CASE WHEN gr.semester=0 THEN gr.score END),1) prev_score,
        SUM(gr.semester=1 AND gr.score<56) failing FROM teacher_groups tg JOIN groups_ g ON g.id=tg.group_id
        LEFT JOIN grades gr ON gr.teacher_id=tg.teacher_id AND gr.subject=tg.subject AND gr.student_id IN (SELECT id FROM students WHERE group_id=g.id)
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
    agg = db.rows(con, "SELECT unit, COUNT(*) n, SUM(salary) fund, ROUND(AVG(salary)) avg FROM staff GROUP BY unit ORDER BY fund DESC")
    out = {"by_unit": agg, "total_fund": sum(a["fund"] for a in agg)}
    if not ctx.aggregate_only(PAYROLL):
        out["staff"] = db.rows(con, "SELECT full_name, unit, position, salary FROM staff ORDER BY salary DESC LIMIT 20")
    return out

def hr_list(con, ctx: Ctx, quiet=False):
    _g(con, ctx, HR, "xodimlar ro'yxati", quiet)
    return {"staff": db.rows(con, "SELECT full_name, unit, position, hired, passport FROM staff ORDER BY unit LIMIT 40"),
            "by_unit": db.rows(con, "SELECT unit, COUNT(*) n FROM staff GROUP BY unit ORDER BY n DESC")}

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
    for r in p: r["days_left"] = (dt.date.fromisoformat(r["expires"]) - TODAY).days
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
    from .decisions import UNIT_OF_ROLE
    u = UNIT_OF_ROLE.get(ctx.role.key)
    if ctx.role.key in ("rektor", "kengash", "kotib"): where = "1=1"
    else:
        where = f"(t.assignee_role='{ctx.role.key}' OR t.assignee_user={int(ctx.user['id'])}" + (f" OR t.unit='{u}'" if u else "") + ")"
    rows = db.rows(con, f"""SELECT t.*, m.title meeting, m.date meeting_date, m.source FROM tasks t JOIN meetings m ON m.id=t.meeting_id
                            WHERE {where} AND t.status!='qoralama' ORDER BY COALESCE(t.due, '9999'), t.id""")
    now = dt.datetime.now()
    for r in rows:
        r["decision"] = bool(r.get("source"))
        r["mine"] = r.get("assignee_user") == ctx.user["id"] or r.get("assignee_role") == ctx.role.key or (bool(u) and r.get("unit") == u)
        due = r.get("due_at") or r.get("due")
        if not due:                              # muddat majlisda aytilmagan — o'ylab topilmaydi
            r["overdue"], r["days"] = False, None; continue
        try:
            d = dt.datetime.fromisoformat(due) if "T" in due else dt.datetime.combine(dt.date.fromisoformat(due), dt.time(23, 59))
        except (ValueError, TypeError):
            r["overdue"], r["days"] = False, None; continue   # buzuq sana butun panelni yiqitmasin
        r["overdue"] = r["status"] != "bajarildi" and d < now
        r["days"] = (d.date() - TODAY).days
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
    if a:
        for g in a["declining_groups"][:3]:
            out.append({"level": "high", "area": "O'quv", "text": f"{g['name']} guruhida ({g['faculty']}, {g['course']}-kurs) o'rtacha ball {abs(g['delta'])} ballga tushgan, davomat {g['attendance']}%"})
    r = safe(at_risk_students)
    if r and r["count"]:
        out.append({"level": "mid", "area": "Talabalar", "text": f"{r['count']} nafar talaba akademik xavf ostida (eng ko'p: {r['by_group'][0]['group']} — {r['by_group'][0]['count']} nafar)"})
    c = safe(contracts_summary)
    if c:
        w = c["worst_groups"][0]
        out.append({"level": "mid", "area": "Kontrakt", "text": f"Kontrakt tushumi {c['total']['pct']}%. Qarz: {mln(c['total']['debt'])}. Eng past: {w['grp']} ({w['pct']}%)"})
    f = safe(finance_summary)
    if f and f["overruns"]:
        o = f["overruns"][0]
        out.append({"level": "high", "area": "Moliya", "text": f"{o['category']}: {o['month']} oyida reja {o['over_pct']}% ga oshib ketgan (ketma-ket {sum(1 for x in f['overruns'] if x['category']==o['category'])} oy)"})
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

def kpis(con, ctx: Ctx):
    out = []
    def safe(fn):
        try: return fn(con, ctx, quiet=True)
        except AccessDenied: return None
    a = safe(academic_overview)
    if a:
        t = a["total"]
        sc = ctx.student_scope("s")
        frm = {r["f"]: r["n"] for r in db.rows(con, f"SELECT COALESCE(study_form,'kunduzgi') f, COUNT(*) n FROM students s WHERE {sc} AND status='faol' GROUP BY 1")}
        k = lambda x: f"{x / 1000:.1f}k" if x >= 1000 else str(x)
        sub = " · ".join(f"{lbl} {k(frm[f])}" for f, lbl in (("kunduzgi", "kunduzgi"), ("sirtqi", "sirtqi"), ("masofaviy", "masofaviy")) if frm.get(f)) or a["scope"]
        out += [{"label": "Faol talabalar", "value": f"{t['n']:,}".replace(",", " "), "sub": sub},
                {"label": "O'rtacha ball", "value": t["gpa"], "sub": f"o'tgan semestr: {t['gpa_prev']}", "trend": round(t["gpa"] - t["gpa_prev"], 1)},
                {"label": "Davomat", "value": f"{t['attendance']}%", "sub": "kunduzgi va sirtqi (masofaviy — onlayn)"}]
    r = safe(at_risk_students)
    if r: out.append({"label": "Xavf ostida", "value": r["count"], "sub": f"{round(100*r['count']/max(1,r['of']),1)}% talaba", "bad": True})
    c = safe(contracts_summary)
    if c: out.append({"label": "Kontrakt tushumi", "value": f"{c['total']['pct']}%", "sub": f"qarz {mln(c['total']['debt'])}"})
    f = safe(finance_summary)
    if f: out.append({"label": "Byudjet ijrosi", "value": f"{f['total']['pct']}%", "sub": f"{mln(f['total']['actual'])} / {mln(f['total']['planned'])}"})
    s = safe(science_summary)
    if s:
        sc = sum(k["n"] for k in s["kinds_2026"] if k["kind"] in ("Scopus", "Web of Science"))
        out.append({"label": "Scopus/WoS 2026", "value": sc, "sub": f"ilmiy daraja: {s['degree_pct']}%"})
    i = safe(international_summary)
    if i: out.append({"label": "Xalqaro hamkorlar", "value": i["active"], "sub": f"{len(i['expiring'])} tasi tugamoqda"})
    ad = safe(admissions_summary)
    if ad: out.append({"label": "Qabul 2026", "value": f"{ad['total']:,}".replace(",", " "), "sub": "ariza"})
    t = safe(tasks_list)
    if t: out.append({"label": "Topshiriqlar", "value": f"{t['done']}/{len(t['tasks'])}", "sub": f"{t['overdue']} tasi muddati o'tgan", "bad": t["overdue"] > 0})
    y = safe(youth_summary)
    if y: out.append({"label": "Murojaatlar", "value": y["appeals_open"], "sub": "hal qilinmagan"})
    m = safe(masters_summary)
    if m: out.append({"label": "Magistrantlar", "value": m["total"], "sub": "dissertatsiya jarayonida"})
    try:
        h = hr_list(con, ctx, quiet=True); out.append({"label": "Xodimlar", "value": sum(x["n"] for x in h["by_unit"]), "sub": "shtat"})
    except AccessDenied: pass
    return out[:8]
