"""Lavozim ish stollari — o'z navbati yoki vositasi bo'lmagan bo'limlar uchun Boshqaruv panelidagi asosiy karta.

  * strategik  — institut KPI paneli (faqat jamlangan raqamlar, rbac.KPI) + hisobotlar (CSV eksport, haftalik brifing);
  * sifat      — akademik sifat ko'rsatkichlari: fakultet va kurs kesimida ball, davomat, o'zlashtirmaganlar va a'lochilar ulushi,
                 keskin pasaygan guruhlar soni, o'quv dasturlari (sillabus) holati — faqat o'qish, jamlangan (rbac.ACADEMIC aggregate_only);
  * marketing  — qabul jamlanmasi: voronka, yo'nalishlar konversiyasi, haftalik dinamika, to'lov turi (rbac.ADMISSIONS);
  * yuridik    — shartnomalar ekspertizasi: xalqaro/hamkorlik shartnomalari reyestri muddatlari bo'yicha navbat va yuridik
                 xulosa (rbac.INTL, faqat o'qish + o'z xulosasi); matnni tekshirish — «Tarjima va shartnoma» (AI'siz qoida rejimida ham).

Hech bir stol shaxsiy ma'lumot qaytarmaydi: talaba/xodim ismi yo'q, faqat sonlar va ulushlar. Har bir o'qish audit jurnaliga yoziladi.
Router accounts.py orqali ulanadi (main.py ga tegilmaydi).
"""
import csv, datetime as dt, io
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock
from . import db, rbac, academic_rules as AR, modules as MODS
from .rbac import AccessDenied, Ctx

router = APIRouter()
_con = None
_ctx = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS legal_reviews(id INTEGER PRIMARY KEY, partner_id INT, status TEXT, note TEXT, by_user INT, by_name TEXT, at TEXT);
CREATE INDEX IF NOT EXISTS ix_legal_reviews_p ON legal_reviews(partner_id, id);
"""
# Ishlash tezligi: guruh bo'yicha talabalar (o'qituvchi paneli — «Mening guruhlarim», Talabalar markazi, reyting) — 57 s → 0.2 s
PERF_INDEXES = ["CREATE INDEX IF NOT EXISTS ix_students_group ON students(group_id, status)"]

DESK_RES = {"strategik": rbac.KPI, "sifat": rbac.ACADEMIC, "marketing": rbac.ADMISSIONS, "qabul": rbac.ADMISSIONS, "yuridik": rbac.INTL}
LEGAL_ST = {"korib_chiqildi": "Ko'rib chiqildi — e'tiroz yo'q", "etiroz": "E'tiroz bor — tuzatish kerak", "uzaytirish": "Uzaytirish tavsiya etiladi",
            "tugatish": "Tugatish tavsiya etiladi"}

def init(con):
    try:
        con.executescript(SCHEMA)
        for q in PERF_INDEXES: con.execute(q)
        con.commit()
    except Exception as e:        # bo'sh baza (seed boshlanmagan)
        print("desks.init:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn
    init(con)

def _today() -> dt.date:
    from . import services as S
    return clock.today()

def _pct(a, b, d=1):
    return round(100 * (a or 0) / b, d) if b else None

def _tbl(con, name) -> bool:
    return bool(db.one(con, "SELECT 1 x FROM sqlite_master WHERE type='table' AND name=?", (name,)))

def _ind(key, label, value, unit="", sub="", prev=None, good="up", source="", tip=""):
    delta = round(value - prev, 1) if isinstance(value, (int, float)) and isinstance(prev, (int, float)) else None
    return {"key": key, "label": label, "value": value, "unit": unit, "sub": sub, "prev": prev, "delta": delta, "good": good,
            "source": source, "tip": tip}

# --------------------------------------------------------------------------------------------------
# Strategik bo'lim: institut KPI (jamlangan)
# --------------------------------------------------------------------------------------------------
def strategic(con) -> dict:
    td = _today()
    st = db.one(con, """SELECT COUNT(*) n, ROUND(AVG(gpa),1) gpa, ROUND(AVG(gpa_prev),1) gpa_prev, ROUND(AVG(attendance),1) att,
                        SUM(gpa IS NOT NULL AND gpa < ?) below, COUNT(gpa) scored FROM students WHERE status='faol'""", (AR.PASS,))
    forms = db.rows(con, "SELECT COALESCE(study_form,'kunduzgi') f, COUNT(*) n FROM students WHERE status='faol' GROUP BY 1 ORDER BY n DESC")
    ct = db.one(con, "SELECT SUM(contract_amount) total, SUM(paid_amount) paid FROM students WHERE payment_type='kontrakt'")
    ad = db.one(con, """SELECT COUNT(*) n, SUM(status="talaba bo'ldi") enr FROM applicants""") if _tbl(con, "applicants") else {"n": 0, "enr": 0}
    pr = db.rows(con, "SELECT expires, status FROM partners") if _tbl(con, "partners") else []
    act = [p for p in pr if p["status"] == "faol" and p["expires"] >= td.isoformat()]
    soon = [p for p in act if (dt.date.fromisoformat(p["expires"]) - td).days <= 60]
    pub = {r["year"]: r["n"] for r in db.rows(con, "SELECT year, COUNT(*) n FROM publications WHERE kind IN ('Scopus','Web of Science') GROUP BY 1")} if _tbl(con, "publications") else {}
    deg = db.one(con, "SELECT COUNT(*) n, SUM(COALESCE(degree,'') NOT IN ('','yo''q','—')) d FROM teachers") if _tbl(con, "teachers") else {"n": 0, "d": 0}
    tk = db.one(con, """SELECT COUNT(*) n, SUM(status='bajarildi') done,
                        SUM(status NOT IN ('bajarildi','bekor','qoralama') AND COALESCE(due_at, due) < ?) late
                        FROM tasks WHERE status NOT IN ('qoralama','bekor')""", (td.isoformat(),))
    ind = [
        _ind("talabalar", "Faol talabalar", st["n"], "", " · ".join(f"{r['f']} {r['n']:,}".replace(",", " ") for r in forms), source=MODS.sample("HEMIS")),
        _ind("ball", AR.SCORE_LABEL, st["gpa"], "", "oxirgi yakunlangan semestr", st["gpa_prev"], source=MODS.sample("HEMIS"),
             tip="Fanlar bo'yicha 100 ballik yakuniy ballarning o'rtachasi; o'zgarish — avvalgi semestrga nisbatan"),
        _ind("davomat", "Davomat", st["att"], "%", "faol talabalar o'rtachasi", source=MODS.sample("HEMIS")),
        _ind("ozlashtirmagan", "O'zlashtirmaganlar ulushi", _pct(st["below"], st["scored"]), "%", f"o'rtacha ball {AR.PASS} dan past", good="down", source=MODS.sample("HEMIS")),
        _ind("kontrakt", "Kontrakt tushumi", _pct(ct["paid"], ct["total"]), "%", f"qarz {round(((ct['total'] or 0) - (ct['paid'] or 0)) / 1e9, 2)} mlrd so'm",
             source="Buxgalteriya (jamlangan)"),
        _ind("qabul", "Qabul: konversiya", _pct(ad["enr"], ad["n"]), "%", f"{(ad['n'] or 0):,} ariza → {(ad['enr'] or 0):,} talaba".replace(",", " "), source="Qabul bazasi"),
        _ind("hamkorlar", "Amaldagi xalqaro shartnomalar", len(act), "", f"{len(soon)} tasi 60 kun ichida tugaydi", source="Xalqaro shartnomalar reyestri"),
        _ind("scopus", f"Scopus/WoS {td.year}", pub.get(td.year, 0), "", f"{td.year - 1}-yilda: {pub.get(td.year - 1, 0)}", pub.get(td.year - 1), source="Ilmiy nashrlar bazasi",
             tip="Joriy yil hali tugamagan — taqqoslash yil oxirida to'liq bo'ladi"),
        _ind("daraja", "Ilmiy darajali o'qituvchilar", _pct(deg["d"], deg["n"]), "%", f"{deg['n'] or 0} o'qituvchidan", source="Kadrlar (jamlangan)"),
        _ind("ijro", "Topshiriqlar ijrosi", _pct(tk["done"], tk["n"]), "%", f"{tk['done'] or 0}/{tk['n'] or 0} bajarildi · {tk['late'] or 0} tasi muddati o'tgan",
             source="ISFT Core · topshiriqlar"),
    ]
    fac = db.rows(con, """SELECT f.name, COUNT(*) n, ROUND(AVG(s.gpa),1) gpa, ROUND(AVG(s.attendance),1) att,
                          ROUND(100.0*SUM(CASE WHEN s.payment_type='kontrakt' THEN s.paid_amount END)/NULLIF(SUM(CASE WHEN s.payment_type='kontrakt' THEN s.contract_amount END),0),1) contract
                          FROM students s JOIN faculties f ON f.id=s.faculty_id WHERE s.status='faol' GROUP BY f.id ORDER BY f.name""")
    if _tbl(con, "applicants"):
        adf = {r["fid"]: r for r in db.rows(con, """SELECT faculty_id fid, COUNT(*) n, SUM(status="talaba bo'ldi") enr FROM applicants GROUP BY 1""")}
        fid = {r["name"]: r["id"] for r in db.rows(con, "SELECT id, name FROM faculties")}
        for r in fac:
            a = adf.get(fid.get(r["name"])) or {}
            r["applied"], r["enrolled"] = a.get("n") or 0, a.get("enr") or 0
    return {"kind": "strategik", "title": "Institut KPI paneli", "indicators": ind, "by_faculty": fac,
            "reports": [{"key": "brifing", "title": "Rahbariyat uchun haftalik brifing (DOCX)", "href": "/api/report/brifing"},
                        {"key": "csv", "title": "KPI jadvali (CSV, Excel uchun)", "href": "/api/desk/export.csv"}],
            "note": "Faqat jamlangan ko'rsatkichlar — shaxsiy ma'lumot yo'q. Manba va yangilanish vaqti har bir ko'rsatkichda."}

# --------------------------------------------------------------------------------------------------
# Sifatni ta'minlash boshqarmasi: akademik sifat (jamlangan, faqat o'qish)
# --------------------------------------------------------------------------------------------------
def quality(con) -> dict:
    td = _today().isoformat()
    q = lambda by, extra="": db.rows(con, f"""SELECT {by} name, COUNT(*) n, ROUND(AVG(s.gpa),1) gpa, ROUND(AVG(s.gpa_prev),1) gpa_prev,
            ROUND(AVG(s.attendance),1) att, ROUND(100.0*SUM(s.gpa < {AR.PASS})/NULLIF(COUNT(s.gpa),0),1) below,
            ROUND(100.0*SUM(s.gpa >= {AR.EXCELLENT_MIN})/NULLIF(COUNT(s.gpa),0),1) excellent
            FROM students s JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
            WHERE s.status='faol' {extra} GROUP BY 1 HAVING COUNT(s.gpa) > 0 ORDER BY 1""")
    fac, course = q("f.name"), q("g.course")
    for r in fac + course: r["delta"] = round(r["gpa"] - r["gpa_prev"], 1) if r["gpa"] is not None and r["gpa_prev"] is not None else None
    tot = db.one(con, f"""SELECT ROUND(AVG(gpa),1) gpa, ROUND(AVG(gpa_prev),1) gpa_prev, ROUND(AVG(attendance),1) att,
                          ROUND(100.0*SUM(gpa < {AR.PASS})/NULLIF(COUNT(gpa),0),1) below, ROUND(100.0*SUM(gpa >= {AR.EXCELLENT_MIN})/NULLIF(COUNT(gpa),0),1) excellent
                          FROM students WHERE status='faol'""")
    drops = db.one(con, """SELECT COUNT(*) n FROM (SELECT g.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.status='faol'
                           GROUP BY g.id HAVING AVG(s.gpa) - AVG(s.gpa_prev) < -4)""")["n"]
    syl = {"by_status": [], "overdue": 0, "total": 0}
    if _tbl(con, "syl_items"):
        SYL = {"soralgan": "So'ralgan", "jarayonda": "Tayyorlanmoqda", "tekshiruvda": "Tekshiruvda", "kelishuvda": "Kelishuvda",
               "qaytarilgan": "Qaytarilgan", "tasdiqlangan": "Tasdiqlangan"}
        rows = db.rows(con, "SELECT status, COUNT(*) n FROM syl_items GROUP BY 1")
        syl = {"by_status": [{"status": r["status"], "label": SYL.get(r["status"], r["status"]), "n": r["n"]} for r in rows],
               "total": sum(r["n"] for r in rows),
               "overdue": db.one(con, "SELECT COUNT(*) n FROM syl_items WHERE status!='tasdiqlangan' AND due IS NOT NULL AND due < ?", (td,))["n"]}
    ind = [_ind("ball", AR.SCORE_LABEL, tot["gpa"], "", "institut o'rtachasi", tot["gpa_prev"], source=MODS.sample("HEMIS")),
           _ind("davomat", "Davomat", tot["att"], "%", "faol talabalar", source=MODS.sample("HEMIS")),
           _ind("ozlashtirmagan", f"O'rtacha bali {AR.PASS} dan past", tot["below"], "%", f"faol talabalar ulushi · bu «{AR.RISK_LABEL}» emas", good="down", source=MODS.sample("HEMIS"),
                tip=f"«{AR.RISK_LABEL}» (Talabalar markazi, bosh sahifa) boshqa ko'rsatkich: {AR.RISK_DEF}"),
           _ind("alo", "A'lochilar ulushi", tot["excellent"], "%", f"o'rtacha ball {AR.EXCELLENT_MIN}+", source=MODS.sample("HEMIS")),
           _ind("pasaygan", "Keskin pasaygan guruhlar", drops, "", "o'rtacha ball 4+ ga tushgan", good="down", source=MODS.sample("HEMIS")),
           _ind("sillabus", "Tasdiqlangan sillabuslar", _pct(sum(r["n"] for r in syl["by_status"] if r["status"] == "tasdiqlangan"), syl["total"]), "%",
                f"{syl['total']} tadan · {syl['overdue']} tasi muddati o'tgan", source="O'quv dasturlari")]
    return {"kind": "sifat", "title": "Akademik sifat ko'rsatkichlari", "indicators": ind, "by_faculty": fac, "by_course": course, "syllabus": syl,
            "reports": [{"key": "csv", "title": "Fakultetlar kesimi (CSV)", "href": "/api/desk/export.csv"}],
            "note": "Faqat o'qish va jamlangan ko'rinish: talabalar ro'yxati yo'q. Pasayish — avvalgi semestrga nisbatan."}

# --------------------------------------------------------------------------------------------------
# Marketing bo'limi: qabul jamlanmasi
# --------------------------------------------------------------------------------------------------
def admissions(con) -> dict:
    if not _tbl(con, "applicants"):
        return {"kind": "marketing", "title": "Qabul jamlanmasi", "indicators": [], "funnel": [], "by_direction": [], "weekly": []}
    t = db.one(con, """SELECT COUNT(*) n, SUM(status="talaba bo'ldi") enr, SUM(status='rad etildi') rej, ROUND(AVG(score),1) score,
                       SUM(payment_type='kontrakt') kontrakt FROM applicants""")
    funnel = db.rows(con, "SELECT status, COUNT(*) n FROM applicants GROUP BY status ORDER BY n DESC")
    by_dir = db.rows(con, """SELECT direction, COUNT(*) applied, SUM(status="talaba bo'ldi") enrolled, ROUND(AVG(score),1) score
                             FROM applicants GROUP BY direction ORDER BY applied DESC""")
    for r in by_dir: r["conv"] = _pct(r["enrolled"], r["applied"])
    weekly = db.rows(con, "SELECT strftime('%W', applied) wk, MIN(applied) start, COUNT(*) n FROM applicants GROUP BY wk ORDER BY wk")[-12:]
    fac = db.rows(con, """SELECT f.name, COUNT(*) applied, SUM(a.status="talaba bo'ldi") enrolled FROM applicants a JOIN faculties f ON f.id=a.faculty_id
                          GROUP BY f.id ORDER BY applied DESC""")
    for r in fac: r["conv"] = _pct(r["enrolled"], r["applied"])
    best = max(by_dir, key=lambda r: r["conv"] or 0) if by_dir else None
    ind = [_ind("arizalar", "Arizalar", t["n"], "", "qabul 2026", source="Qabul bazasi"),
           _ind("talaba", "Talaba bo'ldi", t["enr"], "", f"konversiya {_pct(t['enr'], t['n'])}%", source="Qabul bazasi"),
           _ind("rad", "Rad etildi", _pct(t["rej"], t["n"]), "%", f"{t['rej'] or 0} ta ariza", good="down", source="Qabul bazasi"),
           _ind("ball", "O'rtacha kirish bali", t["score"], "", "barcha arizachilar", source="Qabul bazasi"),
           _ind("kontrakt", "Kontrakt asosida", _pct(t["kontrakt"], t["n"]), "%", "arizalar ulushi", source="Qabul bazasi"),
           _ind("eng", "Eng yuqori konversiya", best["conv"] if best else None, "%", best["direction"] if best else "", source="Qabul bazasi")]
    return {"kind": "marketing", "title": "Qabul jamlanmasi", "indicators": ind, "funnel": funnel, "by_direction": by_dir, "weekly": weekly, "by_faculty": fac,
            "reports": [{"key": "csv", "title": "Yo'nalishlar kesimi (CSV)", "href": "/api/desk/export.csv"}],
            "note": "Faqat jamlangan sonlar — arizachilar ismi va aloqa ma'lumoti ko'rsatilmaydi."}

# --------------------------------------------------------------------------------------------------
# Yuridik bo'lim: shartnomalar ekspertizasi
# --------------------------------------------------------------------------------------------------
def legal(con) -> dict:
    """Yagona yuridik navbat — Xalqaro hamkorlik modulidagi «Yuridik ko'rikda» shartnomalar (app/xalqaro.py). Xulosa o'sha yerda beriladi."""
    td = _today()
    if not _tbl(con, "intl_agreements"):
        return {"kind": "yuridik", "title": "Shartnomalar ekspertizasi", "indicators": [], "queue": [], "expiring": []}
    q = db.rows(con, "SELECT id, partner_name, country, kind, title, start, end, updated_at FROM intl_agreements WHERE status='yuridik' ORDER BY updated_at")
    exp = db.rows(con, "SELECT id, partner_name, country, kind, title, end FROM intl_agreements WHERE status='faol' AND end <= ? ORDER BY end",
                  ((td + dt.timedelta(days=90)).isoformat(),))
    for r in exp: r["days_left"] = (dt.date.fromisoformat(r["end"]) - td).days if r["end"] else None
    act = db.one(con, "SELECT COUNT(*) n FROM intl_agreements WHERE status='faol'")["n"]
    ind = [_ind("navbat", "Yuridik xulosa kutmoqda", len(q), "", "Xalqaro hamkorlik → Shartnomalar", good="down", source="Xalqaro hamkorlik"),
           _ind("90", "90 kun ichida tugaydi", len(exp), "", "uzaytirish loyihasi Xalqaro bo'limdan keladi", good="down", source="Xalqaro hamkorlik"),
           _ind("amalda", "Amaldagi shartnomalar", act, "", "", source="Xalqaro hamkorlik")]
    return {"kind": "yuridik", "title": "Shartnomalar ekspertizasi", "indicators": ind, "queue": q, "expiring": exp,
            "note": "Yagona navbat: xulosa (mos / e'tiroz) «Xalqaro hamkorlik» → «Shartnomalar» da beriladi."}

BUILD = {"strategik": strategic, "sifat": quality, "marketing": admissions, "qabul": admissions, "yuridik": legal}

def desk_for(c: Ctx, quiet=False) -> dict | None:
    k = c.role.key
    if k not in BUILD: return None
    res = DESK_RES[k]
    if quiet:
        if not c.can(res): raise AccessDenied("")
        rbac.audit(_con, c, "lavozim ish stoli", res, True, k)
    else:
        rbac.require(_con, c, res, "lavozim ish stoli", k)
    return BUILD[k](_con)

@router.get("/api/desk")
def api_desk(request: Request):
    c = _ctx(request)
    d = desk_for(c)
    return d or {"kind": None}

@router.get("/api/desk/export.csv")
def api_desk_csv(request: Request):
    c = _ctx(request)
    if c.role.key not in ("strategik", "sifat", "marketing", "qabul"): raise AccessDenied("⛔ Eksport faqat KPI, sifat va qabul ish stollari uchun.")
    d = desk_for(c)
    rbac.audit(_con, c, "ish stoli eksporti (CSV)", DESK_RES[c.role.key], True, c.role.key)
    buf = io.StringIO(); w = csv.writer(buf, delimiter=";")
    w.writerow(["Ko'rsatkich", "Qiymat", "Birlik", "Avvalgi", "O'zgarish", "Izoh", "Manba"])
    for i in d["indicators"]:
        w.writerow([i["label"], i["value"], i["unit"], i["prev"] if i["prev"] is not None else "", i["delta"] if i["delta"] is not None else "", i["sub"], i["source"]])
    rows = d.get("by_faculty") or []
    if c.role.key in ("marketing", "qabul"): rows = d.get("by_direction") or []
    if rows:
        w.writerow([]); keys = list(rows[0].keys()); w.writerow(keys)
        for r in rows: w.writerow([r.get(k) for k in keys])
    name = {"strategik": "kpi", "sifat": "sifat", "marketing": "qabul", "qabul": "qabul"}[c.role.key]
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="isft-{name}-{_today().isoformat()}.csv"'})

# Eski «/api/desk/legal» xulosa navbati olib tashlandi — yagona navbat: Xalqaro hamkorlik → Shartnomalar (app/xalqaro.py).
