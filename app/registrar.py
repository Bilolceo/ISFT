"""Registrator ofisi — talabaning qabuldan bitiruvgacha hamrohi (Registrator ofisi boshlig'i M. Baratov talablari).

Talabalar markazi (app/student_ops.py) ustiga qo'shimcha — yangi qoidalar dvigateli emas, o'sha holatlar va faktlardan foydalanadi:
  * Ish stoli: zinapoya bosqichlari bo'yicha sonlar va bir bosishda ro'yxat — kontrakt (≤3 kun → kritik; muddat o'tgan),
    davomat (30 soat → call-markaz + ogohlantirish xati; 48 soatdan oshsa → hayfsan loyihasi; davom etsa → «chetlashtirishga tayyor»),
    o'zlashtirish (JPA yetarli, lekin ≥2 qarzdor fan — baribir ogohlantirish), otrabotka muddatlari (yashil/sariq/qizil), akademik ta'til.
    Har bosqichda: kim ishlaydi, nima deyiladi, umumiy huquqiy asos («manba aniqlashtiriladi» — qaror raqamlari o'ylab topilmaydi).
  * Imtihonga kirish ruxsatnomasi (qishki sessiya): faktlardan tekshiruv — ochiq otrabotka, yakunlangan semestrlardagi akademik qarz,
    JORIY semestrning haqiqiy oraliq nazorat bali (≥ 12 / 30; fan tanlanmasa — barcha fanlar), joriy semestrdagi sababsiz soatlar,
    kontrakt jadvali yoki muddat uzaytirilgani — guruh bo'yicha kim ruxsat oladi / kim yo'q va nima uchun.
  * Hayfsan: «Chetlashtirishga tayyor» bosqichi faqat hayfsani qayd etilgan («amalda») talabalarni ko'rsatadi (discipline jadvali).
  * Shaxsiy grafik: talabaning barcha qarzlari bo'yicha muddatli reja (QR: kim, qachon, qaysi xodim bergan).
  * Otrabotka skani: yuklanganda o'qiladi (registrar_scan) — ro'yxat raqami → otrabotka, imzo bor/yo'q, ball; demo skan generatori.
Sirtqi bo'lim — xuddi shu ishlarni faqat sirtqi ta'lim talabalari uchun bajaradi (ko'lam student_ops._scope_sql / documents._sscope).
"""
import datetime as dt, json, random
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock
from . import db, rbac, academic_rules as AR, student_ops as OPS
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
REG = ("talabalar", "registrator_xodim", "sirtqi")             # ruxsatnoma, shaxsiy grafik, ish stoli (amal); kontrakt uzaytirish — faqat boshliq
DESK_VIEW = OPS.FULL_VIEW + ("sirtqi",)                        # ish stolini ko'radi (prorektor, akademik — o'qish uchun)

SCHEMA = """
CREATE TABLE IF NOT EXISTS contract_deferments(id INTEGER PRIMARY KEY, student_id INT, until TEXT, note TEXT, created_by INT, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_defer_st ON contract_deferments(student_id);
"""

def init(con):
    con.executescript(SCHEMA); con.commit()
    try:   # mavjud bazada ham: baholar modeli ustunlari, yangi jadvallar (intizom, tyutor biriktirmasi) va yangi standart qoidalar
        OPS.ensure_schema(con); OPS.ensure_policy(con)
    except Exception as e:
        print("registrar: sxema/qoidalar:", e)
    try:
        seed(con)
    except Exception as e:   # demo ma'lumot ilovani to'xtatmasin
        print("registrar seed:", e)

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def _now(): return clock.now().replace(microsecond=0)
def _iso(t): return t.isoformat(timespec="seconds")

# ---------------------------------------------------------------------------------------------
# Imtihonga kirish ruxsatnomasi: faktlar bo'yicha tekshiruv
# ---------------------------------------------------------------------------------------------
def contract_need(con, s, today=None):
    """Bugungi kungacha jadval bo'yicha to'lanishi kerak bo'lgan summa va yetishmayotgani."""
    today = today or clock.today()
    plan = db.rows(con, "SELECT * FROM contract_plan WHERE due<=? ORDER BY due DESC LIMIT 1", (today.isoformat(),))
    pct = plan[0]["cum_pct"] if plan else 0
    need = (s["contract_amount"] or 0) * pct // 100
    return need, max(0, need - (s["paid_amount"] or 0)), (plan[0] if plan else None)

def deferment(con, sid, today=None):
    today = (today or clock.today()).isoformat()
    return db.one(con, "SELECT * FROM contract_deferments WHERE student_id=? AND until>=? ORDER BY until DESC LIMIT 1", (sid, today))

def permit_check(con, sid, subject=None) -> dict:
    P = OPS.policy(con)
    s = db.one(con, "SELECT id, full_name, hemis_id, status, payment_type, contract_amount, paid_amount, study_form FROM students WHERE id=?", (sid,))
    if not s: raise ValueError("Talaba topilmadi")
    cur = AR.CURRENT_SEMESTER
    checks = []
    def add(key, label, ok, detail=""): checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})
    add("holat", "Talaba maqomi — faol", s["status"] == "faol", "" if s["status"] == "faol" else f"maqomi: {s['status']}")
    rt = db.rows(con, "SELECT subject, status, due_at, kind FROM retakes WHERE student_id=? AND status IN ('berildi','topshirildi')", (sid,))
    add("otrabotka", "Ochiq otrabotka yo'q", not rt,
        "; ".join(f"«{r['subject']}» — {'varaqa qaytarilmagan' if r['status'] == 'berildi' else 'natija tasdiqlanmagan'}" for r in rt))
    debts = OPS._debts(con, sid)
    add("qarz", "Yakunlangan semestrlardan akademik qarz yo'q", not debts,
        "; ".join(f"«{g['subject']}» ({g['score']} ball, {AR.SEMESTER_SHORT.get(g['semester'], '')})" for g in debts))
    curg = db.rows(con, "SELECT subject, oraliq FROM grades WHERE student_id=? AND semester=? ORDER BY subject", (sid, cur))
    if subject:
        g = next((x for x in curg if x["subject"] == subject), None)
        if not g:
            add("oraliq", f"«{subject}» fani joriy semestr o'quv rejasida", False, "talabada bu fan yo'q")
        else:
            add("oraliq", f"Oraliq nazorat ≥ {AR.ORALIQ_MIN} / {AR.ORALIQ_MAX} («{subject}»)", AR.admitted(g["oraliq"]),
                f"oraliq: {g['oraliq'] if g['oraliq'] is not None else 'kiritilmagan'} / {AR.ORALIQ_MAX}")
    elif s["status"] == "faol":
        low = [x for x in curg if not AR.admitted(x["oraliq"])]
        add("oraliq", f"Oraliq nazorat ≥ {AR.ORALIQ_MIN} / {AR.ORALIQ_MAX} — barcha fanlar ({len(curg)})", curg and not low,
            ("; ".join(f"«{x['subject']}» — {x['oraliq'] if x['oraliq'] is not None else 'kiritilmagan'} / {AR.ORALIQ_MAX}" for x in low)
             if low else f"eng past: {min(x['oraliq'] for x in curg)} / {AR.ORALIQ_MAX}" if curg else "joriy semestr baholari yo'q"))
    unx = OPS.student_facts(con, sid)["unexcused"]
    lim = int(P.get("permit_att_hours", P["att_reprimand_hours"])) if s["study_form"] != "sirtqi" else OPS.att_limits(P, "sirtqi")["reprimand"]
    add("davomat", f"Joriy semestrda sababsiz qoldirilgan soatlar {lim} dan oshmagan", unx <= lim, f"{unx} soat")
    if s["payment_type"] == "kontrakt" and (s["contract_amount"] or 0) > 0:
        need, short_, inst = contract_need(con, s)
        dfr = deferment(con, sid) if short_ else None
        add("kontrakt", "Kontrakt to'lovi jadval bo'yicha", short_ == 0 or bool(dfr),
            "" if short_ == 0 else (f"muddat uzaytirilgan: {dfr['until']}gacha" if dfr else f"{inst['label'] if inst else 'jadval'} bo'yicha {OPS._money(short_)} yetishmaydi"))
    else:
        add("kontrakt", "Kontrakt to'lovi jadval bo'yicha", True, "ISFT granti asosida")
    bad = [c for c in checks if not c["ok"]]
    return {"student_id": sid, "full_name": s["full_name"], "eligible": not bad, "checks": checks,
            "reasons": [f"{c['label']}: {c['detail']}" if c["detail"] else c["label"] for c in bad]}

def gen_exam_permit(I, p):
    """documents.py → 'exam_permit'. Faqat ruxsat olganlarga sahifa; hech kim olmasa — sabablar bilan rad."""
    from . import documents as D, brand as B
    subject = (p.get("subject_name") or "").strip()[:120] or None
    sts = D._expand_students(I.con, I.ctx, p)
    res = [(s, permit_check(I.con, s["id"], subject)) for s in sts]
    ok = [(s, r) for s, r in res if r["eligible"]]
    if not ok:
        r0 = res[0][1]
        raise ValueError(("Ruxsatnoma berilmaydi: " + "; ".join(r0["reasons"])) if len(res) == 1
                         else f"Tanlangan {len(res)} nafar talabadan hech biri talablarga javob bermaydi")
    for s, r in ok:
        I.page(s["full_name"], title=f"Imtihonga kirish ruxsatnomasi{': ' + subject if subject else ''}")
        B.title(I.doc, "IMTIHONGA KIRISH RUXSATNOMASI", f"{AR.SEMESTERS[AR.CURRENT_SEMESTER]} — yakuniy nazorat (qishki sessiya)" + (f" · «{subject}»" if subject else " · barcha fanlar"))
        B.table(I.doc, ["Ma'lumot", ""], [("Talaba", s["full_name"]), ("HEMIS ID", s["hemis_id"]), ("Fakultet / guruh", f"{s['faculty']} · {s['grp']} ({s['course']}-kurs)"),
                                          ("Ta'lim shakli", D.FORM_UZ.get(s.get("study_form"), "kunduzgi"))], widths=[5, 12], size=10.5)
        B.table(I.doc, ["Tekshiruv", "Natija"], [(c["label"], "✓ " + (c["detail"] or "talabga javob beradi")) for c in r["checks"]], widths=[9, 8], size=9.5)
        B.para(I.doc, "Ruxsatnoma ISFT Core tizimidagi faktlar (HEMIS: joriy semestr oraliq nazorat ballari va davomati, yakunlangan semestrlar "
                      "natijalari, otrabotkalar, buxgalteriya ma'lumoti) asosida berildi va joriy sessiya davomida amal qiladi. "
                      "Imtihon oluvchi QR-kod orqali haqiqiyligini tekshiradi.", size=10.5)
        B.signature(I.doc, *D.signer(I.con, I.ctx))
        I.qr()

def gen_personal_schedule(I, p):
    """documents.py → 'personal_schedule': talabaning qarzlarini yopish rejasi (bandlar — faktlardan)."""
    from . import documents as D, brand as B
    s = D._expand_students(I.con, I.ctx, p)[0]
    P, today = OPS.policy(I.con), clock.today()
    try: deadline = dt.date.fromisoformat(p.get("deadline") or "")
    except ValueError: deadline = today + dt.timedelta(days=21)
    if deadline <= today: raise ValueError("Yakuniy muddat bugundan keyin bo'lishi kerak")
    pass_ = int(P["pass_score"])
    items = []   # (sana, vazifa, mas'ul)
    rt = db.rows(I.con, "SELECT subject, status, due_at FROM retakes WHERE student_id=? AND status IN ('berildi','topshirildi')", (s["id"],))
    open_subj = {r["subject"] for r in rt}
    for r in rt:
        if r["status"] == "berildi":
            items.append((min(deadline, max(today, dt.date.fromisoformat(r["due_at"][:10]))), f"«{r['subject']}»: otrabotka varaqasini o'qituvchiga imzolatib qaytarish", "Talaba → Registrator ofisi"))
    debts = [g for g in OPS._debts(I.con, s["id"]) if g["subject"] not in open_subj]
    low = [g for g in OPS.student_facts(I.con, s["id"])["oraliq_low"] if g["subject"] not in open_subj]
    todo = [(f"«{g['subject']}» ({g['score']} ball, {AR.SEMESTER_SHORT.get(g['semester'], '')}): akademik qarz — otrabotka varaqasini olish va qayta topshirish",
             "Talaba, o'qituvchi → Registrator ofisi") for g in debts]
    todo += [(f"«{g['subject']}»: oraliq nazorat {g['oraliq'] if g['oraliq'] is not None else 'kiritilmagan'} / {AR.ORALIQ_MAX} — "
              f"yakuniyga kirish uchun kamida {AR.ORALIQ_MIN} ball (otrabotka)", "Talaba, o'qituvchi") for g in low]
    step = max(2, (deadline - today).days // max(1, len(todo) + 1))
    for i, (txt, who) in enumerate(todo, 1):
        items.append((min(deadline, today + dt.timedelta(days=step * i)), txt, who))
    if s["payment_type"] == "kontrakt" and (s["contract_amount"] or 0) > 0:
        need, short_, inst = contract_need(I.con, s)
        if short_:
            dfr = deferment(I.con, s["id"])
            due = dt.date.fromisoformat(dfr["until"]) if dfr else min(deadline, today + dt.timedelta(days=5))
            items.append((due, f"Kontrakt to'lovi: {OPS._money(short_)} ({inst['label'] if inst else 'jadval'})" + (" — muddat uzaytirilgan" if dfr else ""), "Talaba → buxgalteriya"))
    pend = db.rows(I.con, "SELECT reason, end, hours FROM absences WHERE student_id=? AND doc_status='kutilmoqda' AND semester=?", (s["id"], AR.CURRENT_SEMESTER))
    if pend:
        items.append((today + dt.timedelta(days=int(P["medical_doc_days"])), f"Sababli qoldirish hujjati ({sum(a['hours'] for a in pend)} soat) — tasdiqlovchi hujjatni topshirish", "Talaba → tyutor"))
    unx = OPS.student_facts(I.con, s["id"])["unexcused"]
    if unx >= P["att_call_hours"]:
        items.append((today + dt.timedelta(days=3), f"Joriy semestrda sababsiz qoldirilgan {unx} soat: tyutor bilan suhbat, tushuntirish xati, "
                      "qoldirilgan mashg'ulotlarni otrabotka qilish", "Talaba, tyutor"))
    if not items: raise ValueError("Talabada yopiladigan qarz yo'q — shaxsiy grafik kerak emas")
    items.sort(key=lambda x: x[0])
    reg, _ = I.page(s["full_name"], title="Shaxsiy grafik (qarzlarni yopish rejasi)")
    B.title(I.doc, "SHAXSIY GRAFIK", "akademik va moliyaviy qarzlarni yopish rejasi")
    B.table(I.doc, ["Ma'lumot", ""], [("Talaba", s["full_name"]), ("HEMIS ID", s["hemis_id"]), ("Fakultet / guruh", f"{s['faculty']} · {s['grp']} ({s['course']}-kurs)"),
                                      ("Ta'lim shakli", D.FORM_UZ.get(s.get("study_form"), "kunduzgi")), ("Yakuniy muddat", D.d_uz(deadline))], widths=[5, 12], size=10.5)
    B.table(I.doc, ["№", "Vazifa", "Muddat", "Mas'ul", "Bajarildi"], [(i, t, x.strftime("%d.%m.%Y"), w, "") for i, (x, t, w) in enumerate(items, 1)],
            widths=[0.8, 8.4, 2.4, 3.4, 2], size=9.5)
    note = (p.get("note") or "").strip()
    if note: B.para(I.doc, f"Izoh: {note[:300]}", size=10.5)
    B.para(I.doc, "Grafik bajarilmasa, institut ichki tartib qoidalari va akademik qoidalarga muvofiq choralar ko'riladi (manba aniqlashtiriladi). "
                  f"Savollar bo'yicha Registrator ofisiga murojaat qiling: {AR.REGISTRAR_ROOMS_TEXT}.", size=10)
    who = I.ctx.user["full_name"].split(":", 1)[-1].strip()
    B.para(I.doc, f"Grafikni tuzdi: {I.ctx.title} — {who}, {_now().strftime('%d.%m.%Y %H:%M')}.", size=10, indent=False)
    B.signature(I.doc, *D.signer(I.con, I.ctx))
    B.run(I.doc.add_paragraph(), "Tanishdim va bajarishga roziman: ____________________  (talaba imzosi)        Sana: «___» __________ 20___ y.", 10.5)
    I.qr()
    OPS._log(I.con, None, None, s["id"], I.ctx, "shaxsiy grafik berildi", f"{reg} · {len(items)} band · yakuniy muddat {deadline.isoformat()}")

# ---------------------------------------------------------------------------------------------
# Ish stoli: zinapoya bosqichlari
# ---------------------------------------------------------------------------------------------
def _stages(P):
    crit = int(P["contract_critical_days"]); call, letter, rep = int(P["att_call_hours"]), int(P["att_letter_hours"]), int(P["att_reprimand_hours"])
    expel, cexp = int(P.get("att_expel_hours", 72)), int(P.get("contract_expel_days", 30))
    B = OPS.BASIS
    return [
        dict(key="kontrakt_kritik", chain="kontrakt", title=f"To'lov muddatiga ≤ {crit} kun", who="Call-markaz",
             sql="oc.rule='kontrakt' AND oc.level=2",
             say=["To'lov qachon amalga oshirilishini aniq sana bilan kelishing; va'dani tizimga kiriting — muddat o'tsa tizim o'zi qayta eslatadi.",
                  "Bo'lib to'lash yoki muddat uzaytirish kerak bo'lsa — buxgalteriya va Registrator ofisiga yo'naltiring (uzaytirilsa ruxsatnomaga ta'sir qilmaydi)."],
             basis=B["kontrakt"]),
        dict(key="kontrakt_otgan", chain="kontrakt", title="To'lov muddati o'tgan", who="Call-markaz → Registrator (qarzdorlik xati)",
             sql="oc.rule='kontrakt' AND oc.level=3",
             say=["Muddat o'tganini va qarz summasini aniq ayting; rasmiy xat yuborilishini ogohlantiring (kunduzgi bakalavr — ota-onaga, "
                  "sirtqi / masofaviy / magistratura talabasi — o'ziga).",
                  "Sessiyaga qo'yish va imtihonga ruxsatnoma to'lov (yoki rasmiy uzaytirish) bo'lmaguncha berilmasligini tushuntiring."],
             basis=B["kontrakt"]),
        dict(key="davomat_30", chain="davomat", title=f"{call} soat sababsiz: qo'ng'iroq + ogohlantirish xati", who="Call-markaz + Registrator ofisi",
             sql="oc.rule='davomat' AND oc.level IN (1,2)",
             say=[f"Sababsiz qoldirilgan soatlarni aniq ayting; {rep} soatdan oshsa hayfsan e'lon qilinishini tushuntiring.",
                  "Kasallik yoki xizmat safari bo'lsa — hujjatni 3 kun ichida tyutorga topshirsin; ogohlantirish xatiga imzo qo'ydiring."],
             basis=B["davomat"]),
        dict(key="davomat_hayfsan", chain="davomat", title=f"{rep} soatdan oshdi: hayfsan", who="Registrator ofisi + tyutor suhbati",
             sql=f"oc.rule='davomat' AND oc.level=3 AND (CAST(json_extract(oc.facts,'$.hours') AS INT) < {EXPEL_SQL.format(expel=expel)} OR NOT {HAYFSAN_SQL})",
             say=["Hayfsan e'lon qilish to'g'risida taqdimnoma tayyorlang (rektor imzolaydi — hayfsan qayd etiladi) va tyutor suhbatini o'tkazing.",
                  f"Hayfsan e'lon qilingandan keyin ham sababsiz qoldirish davom etib {expel} soatga yetsa — talabalar safidan chetlashtirish masalasi ko'riladi."],
             basis=B["davomat"]),
        dict(key="chetlashtirish", chain="yakun", title="Chetlashtirishga tayyor", who="Registrator ofisi → rektor",
             sql=(f"((oc.rule='davomat' AND oc.level=3 AND CAST(json_extract(oc.facts,'$.hours') AS INT) >= {EXPEL_SQL.format(expel=expel)} AND {HAYFSAN_SQL}) OR "
                  f"(oc.rule='kontrakt' AND oc.level=3 AND CAST(json_extract(oc.facts,'$.days') AS INT) <= -{cexp} AND EXISTS "
                  f"(SELECT 1 FROM ops_tasks tx WHERE tx.case_id=oc.id AND tx.kind='xat' AND tx.status='bajarildi')))"),
             say=["Zinapoyaning barcha bosqichlari o'tilgan: qo'ng'iroq, ogohlantirish xati, e'lon qilingan hayfsan (davomat) yoki qarzdorlik xati (kontrakt).",
                  "Buyruq loyihasidan oldin talaba bilan oxirgi yuzma-yuz suhbat va tushuntirish xatini oling; hujjatlar to'plamini tekshiring. "
                  "Chetlashtirish buyrug'i — Buyruqlar bo'limida."],
             basis=B["davomat"] + B["kontrakt"][:1]),
        dict(key="akademik_diqqat", chain="akademik", title="Diqqat: 1 ta akademik qarz yoki 1 fandan oraliq < 12", who="Tyutor",
             sql="oc.rule='akademik' AND oc.level=1",
             say=["Qarzni yoki past oraliq nazoratni sessiyagacha yopish rejasini kelishing — otrabotka varaqasi Registrator ofisida beriladi."],
             basis=B["akademik"]),
        dict(key="akademik_jpa_ok", chain="akademik", title=f"GPA (5) yetarli, lekin ≥ {int(P['fails_warn'])} qarz yoki past oraliq", who="Tyutor + Registrator ofisi",
             sql="oc.rule='akademik' AND oc.level>=2 AND json_extract(oc.facts,'$.gpa_ok') IN (1, 'true')",
             say=["Kumulyativ GPA yetarli bo'lsa ham, akademik qarzlar keyingi kursga o'tishga, past oraliq esa yakuniy nazoratga kirishga to'sqinlik "
                  "qiladi — otrabotka varaqasini olishni kelishing."],
             basis=B["akademik"]),
        dict(key="akademik_jpa_past", chain="akademik", title=f"Kumulyativ GPA (5) {P['gpa_min']} dan past", who="Tyutor + Registrator ofisi",
             sql="oc.rule='akademik' AND oc.level>=2 AND json_extract(oc.facts,'$.gpa_ok') IN (0, 'false')",
             say=["Qiyinchilik sababini aniqlang; shaxsiy grafik tuzib, qarzlarni yopish muddatlarini yozma kelishing."],
             basis=B["akademik"]),
        dict(key="tatil_oldin", chain="tatil", title=f"Akademik ta'til tugashiga ≤ {int(P['leave_warn_days'])} kun", who="Call-markaz",
             sql="oc.rule='tatil' AND oc.level=1",
             say=["Qaytish sanasi, ariza va kerakli hujjatlar ro'yxatini eslating; akademik farq fanlari bo'yicha Registrator ofisiga kelsin."],
             basis=B["tatil"]),
        dict(key="tatil_qaytish", chain="tatil", title="Ta'tildan qaytish: buyruq loyihasi", who="Registrator ofisi",
             sql="oc.rule='tatil' AND oc.level>=2",
             say=["Ariza kelgach «Ta'tildan qaytish» buyrug'i loyihasini Buyruqlar bo'limida tayyorlang (topshiriqdagi «Hujjat tayyorlash» — loyihani o'sha yerda yaratadi)."],
             basis=B["tatil"]),
    ]

EXPEL_SQL = "COALESCE(CAST(json_extract(oc.facts,'$.expel') AS INT), {expel})"   # sirtqi — sessiyaga mutanosib chegara (faktlarda)
HAYFSAN_SQL = "EXISTS (SELECT 1 FROM discipline d WHERE d.student_id=oc.student_id AND d.kind='hayfsan' AND d.status='amalda')"

def _stage_where(c: Ctx):
    return f"oc.status='ochiq' AND {OPS._scope_sql(c)} AND {OPS._rule_sql(c)}"

def desk(c: Ctx):
    P = OPS.policy(_con)
    w = _stage_where(c)
    out = []
    for st in _stages(P):
        r = db.one(_con, f"""SELECT COUNT(DISTINCT oc.student_id) n,
                               (SELECT COUNT(*) FROM ops_tasks t WHERE t.status='yangi' AND t.case_id IN
                                  (SELECT oc.id FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE {w} AND {st['sql']})) open_tasks
                             FROM ops_cases oc JOIN students s ON s.id=oc.student_id WHERE {w} AND {st['sql']}""")
        out.append({k: st[k] for k in ("key", "chain", "title", "who", "say", "basis")} | {"n": r["n"] or 0, "open_tasks": r["open_tasks"] or 0})
    now = _now()
    tones = {"green": 0, "amber": 0, "red": 0, "overdue": 0, "review": 0, "flagged": 0}
    for r in db.rows(_con, f"""SELECT r.status, r.due_at, r.scan_meta FROM retakes r JOIN students s ON s.id=r.student_id
                               WHERE r.status IN ('berildi','topshirildi') AND {OPS._scope_sql(c)}"""):
        if r["status"] == "topshirildi":
            tones["review"] += 1
            m = json.loads(r["scan_meta"] or "{}")
            tones["flagged"] += bool(m.get("signed") is False or m.get("match") is False)
            continue
        h = (dt.datetime.fromisoformat(r["due_at"]) - now).total_seconds() / 3600
        tones["overdue" if h < 0 else OPS.retake_tone(h)] += 1
    S = OPS.att_limits(P, "sirtqi")
    return {"stages": out, "retakes": tones, "sirtqi_limits": S, "policy": {k: P[k] for k in ("att_call_hours", "att_letter_hours", "att_reprimand_hours", "att_expel_hours",
                                                                          "contract_critical_days", "contract_expel_days", "leave_warn_days", "retake_days", "fails_warn", "gpa_min")},
            "scope": "Sirtqi ta'lim talabalari" if c.role.key == "sirtqi" else "Butun institut",
            "verified": [r["key"] for r in db.rows(_con, "SELECT key FROM ops_policy WHERE verified=1 AND key NOT LIKE '\\_%' ESCAPE '\\'")]}

def stage_list(c: Ctx, key, q="", limit=300):
    st = next((x for x in _stages(OPS.policy(_con)) if x["key"] == key), None)
    if not st: raise HTTPException(404, "Bunday bosqich yo'q")
    a = []; extra = ""
    if q: extra = " AND (s.full_name LIKE ? OR g.name LIKE ? OR s.hemis_id LIKE ?)"; a = [f"%{q}%"] * 3
    rows = db.rows(_con, f"""SELECT oc.id case_id, oc.rule, oc.level, oc.facts, s.id student_id, s.full_name, s.study_form, g.name grp, f.name faculty,
                              (SELECT COUNT(*) FROM ops_tasks t WHERE t.case_id=oc.id AND t.status='yangi') open_tasks
                              FROM ops_cases oc JOIN students s ON s.id=oc.student_id JOIN groups_ g ON g.id=s.group_id JOIN faculties f ON f.id=s.faculty_id
                              WHERE {_stage_where(c)} AND {st['sql']}{extra} ORDER BY oc.level DESC, oc.updated_at DESC LIMIT ?""", (*a, limit))
    for r in rows: r["facts"] = json.loads(r["facts"] or "{}")
    return {"stage": {k: st[k] for k in ("key", "title", "who", "say", "basis")}, "rows": rows}

# ---------------------------------------------------------------------------------------------
# Demo ma'lumot (idempotent, mavjud bazada ham chaqiriladi; seed.py oxirida ham)
# ---------------------------------------------------------------------------------------------
def seed(con, base_url="http://localhost:8000/"):
    con.executescript(SCHEMA)
    if con.execute("SELECT 1 FROM ops_policy WHERE key='_seed_registrar'").fetchone(): return False
    reg = con.execute("SELECT id FROM users WHERE role='talabalar' ORDER BY id").fetchone()
    if not reg or not con.execute("SELECT COUNT(*) FROM contract_plan").fetchone()[0]: return False
    ctx = rbac.ctx_for(con, reg[0])
    R = random.Random(20261109)
    pass_ = int(OPS.policy(con)["pass_score"])
    now = _now()
    taken = {(r[0], r[1]) for r in con.execute("SELECT student_id, subject FROM retakes")}
    def cand(form, n):
        rows = db.rows(con, f"""SELECT g.student_id, g.subject, g.teacher_id, g.score, g.semester FROM grades g JOIN students s ON s.id=g.student_id
                               WHERE {AR.debt_where('g')} AND s.status='faol' AND s.study_form=? ORDER BY g.student_id LIMIT 200""", (form,))
        rows = [r for r in rows if (r["student_id"], r["subject"]) not in taken]
        R.shuffle(rows); return rows[:n]
    def mk(c, ctx_, hours):
        due = now + dt.timedelta(hours=hours); issued = due - dt.timedelta(days=int(OPS.policy(con)["retake_days"]))
        cur = con.execute("""INSERT INTO retakes(student_id,subject,teacher_id,reason,status,issued_at,due_at,score_old,created_by,semester,kind)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (c["student_id"], c["subject"], c["teacher_id"],
                                                          f"{OPS.RETAKE_REASON['qarz']} ({AR.SEMESTER_SHORT.get(c['semester'], '')})",
                                                          "berildi", _iso(issued), _iso(due), c["score"], ctx_.user["id"], c["semester"], "qarz"))
        rid = cur.lastrowid; OPS._issue_sheet(con, ctx_, rid, base_url)
        OPS._log(con, None, None, c["student_id"], ctx_, "otrabotka varaqasi berildi", f"{c['subject']} · demo")
        return rid
    k = cand("kunduzgi", 4)
    if len(k) >= 4:
        mk(k[0], ctx, 66)                                  # yashil: 2,75 kun qoldi
        for (c, variant, fmt) in ((k[1], "signed", "pdf"), (k[2], "unsigned", "png")):
            rid = mk(c, ctx, 30)
            r = db.one(con, "SELECT * FROM retakes WHERE id=?", (rid,))
            raw, ext, _ = make_demo_scan(con, r, variant, fmt)
            OPS.store_scan(ctx, r, raw, ext, con=con)
        mk(k[3], ctx, -40)                                 # muddati o'tgan → tyutor + call-markaz topshirig'i
    sir = con.execute("SELECT id FROM users WHERE role='sirtqi' ORDER BY id").fetchone()
    sc = cand("sirtqi", 2)
    if sir and sc:
        sctx = rbac.ctx_for(con, sir[0])
        mk(sc[0], sctx, 40)                                # sariq: 2 kundan kam qoldi
        if len(sc) > 1: mk(sc[1], sctx, 12)                # qizil
    # muddat uzaytirish namunasi: jadvaldan orqada qolgan bitta kontrakt talaba
    for s in db.rows(con, """SELECT id, contract_amount, paid_amount FROM students WHERE status='faol' AND payment_type='kontrakt' AND contract_amount>0
                             AND faculty_id=2 AND study_form='kunduzgi' ORDER BY id LIMIT 200"""):
        need, short_, _ = contract_need(con, s)
        if short_:
            con.execute("INSERT INTO contract_deferments(student_id,until,note,created_by,created_at) VALUES(?,?,?,?,?)",
                        (s["id"], (clock.today() + dt.timedelta(days=20)).isoformat(), "Buxgalteriya bilan kelishildi (demo)", ctx.user["id"], _iso(now)))
            break
    con.execute("INSERT OR REPLACE INTO ops_policy(key,value,label,verified) VALUES('_seed_registrar',1,'Registrator demo ma''lumoti',1)")
    con.commit()
    OPS.evaluate(con)
    seed_discipline(con, R)
    return True

def seed_discipline(con, R=None):
    """Demo: tizimdan oldin (qog'ozda) e'lon qilingan hayfsanlar — 60+ soat sababsiz qoldirganlarning ko'pchiligida; 48–60 soatda —
    ba'zilarida taqdimnoma rektorga yuborilgan («loyiha»). Idempotent: hayfsan yozuvi bo'lsa qayta qo'shilmaydi."""
    if con.execute("SELECT 1 FROM discipline LIMIT 1").fetchone(): return 0
    R = R or random.Random(20261109)
    P, today = OPS.policy(con), clock.today()
    rows = []
    for r in db.rows(con, """SELECT student_id, CAST(json_extract(facts,'$.hours') AS INT) h, json_extract(facts,'$.expel') expel FROM ops_cases
                             WHERE rule='davomat' AND status='ochiq' AND level=3 ORDER BY student_id"""):
        h = r["h"] or 0
        st = "amalda" if h >= int(r["expel"] or 72) - 12 and R.random() < 0.8 else "loyiha" if R.random() < 0.3 else None
        if not st: continue
        when = dt.datetime.combine(today - dt.timedelta(days=R.randint(3, 20)), dt.time(R.randint(9, 17), R.randint(0, 59)))
        rows.append((r["student_id"], "hayfsan", f"joriy semestrda {h} soat dars sababsiz qoldirilgani (hayfsan chegarasidan oshgan)",
                     h, AR.CURRENT_SEMESTER, None, st, _iso(when), None, _iso(when + dt.timedelta(days=2)) if st == "amalda" else None,
                     "demo: tizimga qadar qog'ozda rasmiylashtirilgan" if st == "amalda" else "demo: taqdimnoma rektor imzosida"))
    con.executemany("""INSERT INTO discipline(student_id,kind,reason,hours,semester,doc_reg,status,created_at,created_by,signed_at,note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""", rows)
    con.commit()
    return len(rows)

def demo_info(con, r):
    s = db.one(con, """SELECT s.full_name, s.hemis_id, g.name grp, f.name faculty FROM students s JOIN groups_ g ON g.id=s.group_id
                       JOIN faculties f ON f.id=s.faculty_id WHERE s.id=?""", (r["student_id"],))
    t = db.one(con, "SELECT full_name FROM teachers WHERE id=?", (r["teacher_id"],)) if r["teacher_id"] else None
    d = db.one(con, "SELECT verify_code FROM documents WHERE reg_no=?", (r["reg_no"],)) if r["reg_no"] else None
    return dict(reg_no=r["reg_no"] or "OV-26/0000", code=(d or {}).get("verify_code", ""), url=f"/verify/{(d or {}).get('verify_code', '')}",
                student=s["full_name"], hemis=s["hemis_id"], faculty=s["faculty"], grp=s["grp"], subject=r["subject"],
                teacher=t["full_name"] if t else "—", score_old=r["score_old"], issued=(r["issued_at"] or "")[:10],
                due=f"{r['due_at'][8:10]}.{r['due_at'][5:7]}.{r['due_at'][:4]}, {r['due_at'][11:16]}")

def make_demo_scan(con, r, variant="signed", fmt="pdf"):
    from . import registrar_scan as RS
    return RS.make_sheet(demo_info(con, r), variant, fmt)

# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx: return _ctx(request)

def _need(c: Ctx, roles, action, msg):
    OPS._guard(c, action)
    if c.role.key not in roles: raise AccessDenied(msg)

@router.get("/api/registrar/desk")
def api_desk(request: Request):
    c = C(request); _need(c, DESK_VIEW, "registrator ish stoli", "⛔ Ish stoli — Registrator ofisi va Sirtqi bo'lim uchun.")
    return desk(c)

@router.get("/api/registrar/stage/{key}")
def api_stage(key: str, request: Request, q: str = ""):
    c = C(request); _need(c, DESK_VIEW, f"registrator ish stoli: {key}", "⛔ Ish stoli — Registrator ofisi va Sirtqi bo'lim uchun.")
    return stage_list(c, key, q.strip()[:60])

@router.get("/api/registrar/permits")
def api_permits(request: Request, group: int, subject: str = ""):
    """Guruh bo'yicha: kim imtihonga kira oladi, kim yo'q va nima uchun."""
    c = C(request); _need(c, REG, "imtihonga ruxsatnoma: guruh tekshiruvi", "⛔ Ruxsatnomani Registrator ofisi (sirtqi talabalarga — Sirtqi bo'lim) beradi.")
    from . import documents as D
    g = D._group(_con, c, group)
    subj = [r["subject"] for r in db.rows(_con, "SELECT DISTINCT gr.subject FROM grades gr JOIN students s ON s.id=gr.student_id WHERE s.group_id=? AND gr.semester=? ORDER BY 1",
                                          (group, AR.CURRENT_SEMESTER))]
    subject = subject.strip()[:120]
    if subject and subject not in subj: raise HTTPException(400, "Guruhda bunday fan yo'q")
    rows = [permit_check(_con, s["id"], subject or None) for s in db.rows(_con, f"SELECT s.id FROM students s WHERE s.group_id=? AND {D._sscope(c, 's')} ORDER BY s.full_name", (group,))]
    return {"group": {"id": g["id"], "name": g["name"], "course": g["course"], "faculty": g["faculty"]}, "subjects": subj, "subject": subject,
            "rows": rows, "eligible": sum(r["eligible"] for r in rows)}

@router.get("/api/registrar/permit/{sid}")
def api_permit(sid: int, request: Request, subject: str = ""):
    c = C(request); _need(c, REG, "imtihonga ruxsatnoma: tekshiruv", "⛔ Ruxsatnomani Registrator ofisi (sirtqi talabalarga — Sirtqi bo'lim) beradi.")
    OPS._student_row(c, sid)
    return permit_check(_con, sid, subject.strip()[:120] or None)

@router.get("/api/registrar/discipline")
def api_discipline(request: Request, student_id: int = 0, status: str = ""):
    """Intizomiy choralar (hayfsan) yozuvlari — boshqa modullar (masalan, Buyruqlar) uchun ochiq ma'lumot. Ko'lam — Talabalar markazi ko'lami."""
    c = C(request); _need(c, DESK_VIEW, "intizomiy choralar ro'yxati", "⛔ Intizomiy choralar — Registrator ofisi va Sirtqi bo'lim uchun.")
    w, a = [OPS._scope_sql(c, "s")], []
    if student_id: w.append("d.student_id=?"); a.append(int(student_id))
    if status in OPS.DISC_STATUS: w.append("d.status=?"); a.append(status)
    rows = db.rows(_con, f"""SELECT d.*, s.full_name, s.hemis_id, g.name grp FROM discipline d JOIN students s ON s.id=d.student_id
                             JOIN groups_ g ON g.id=s.group_id WHERE {' AND '.join(w)} ORDER BY d.id DESC LIMIT 500""", a)
    for r in rows: r["status_label"] = OPS.DISC_STATUS.get(r["status"], r["status"])
    return {"rows": rows, "statuses": OPS.DISC_STATUS}

class DeferIn(BaseModel):
    student_id: int
    until: str
    note: str = Field(..., min_length=3, max_length=300)

@router.post("/api/registrar/deferment")
def api_defer(body: DeferIn, request: Request):
    c = C(request); _need(c, (OPS.SUPERVISOR,), "kontrakt muddatini uzaytirish", "⛔ Kontrakt muddatini uzaytirishni Registrator ofisi (buxgalteriya bilan kelishib) qayd etadi.")
    OPS._student_row(c, body.student_id)
    try: until = dt.date.fromisoformat(body.until)
    except ValueError: raise HTTPException(400, "Sanani kiriting")
    if not (clock.today() < until <= clock.today() + dt.timedelta(days=120)): raise HTTPException(400, "Muddat bugundan 120 kungacha bo'lishi kerak")
    _con.execute("INSERT INTO contract_deferments(student_id,until,note,created_by,created_at) VALUES(?,?,?,?,?)",
                 (body.student_id, until.isoformat(), body.note.strip(), c.user["id"], _iso(_now())))
    OPS._log(_con, None, None, body.student_id, c, "kontrakt muddati uzaytirildi", f"{until.isoformat()}gacha · {body.note.strip()}")
    _con.commit(); rbac.audit(_con, c, "kontrakt muddati uzaytirildi", OPS.OPS, True, f"talaba #{body.student_id} → {until}")
    return {"ok": True}

class ScanIn(BaseModel):
    data_url: str = Field(..., max_length=14_000_000)

@router.post("/api/registrar/scan")
def api_scan(body: ScanIn, request: Request):
    """Skanni otrabotkani tanlamasdan yuklash: varaqadagi ro'yxat raqami o'qiladi va mos otrabotka topiladi."""
    c = C(request); _need(c, OPS.RETAKE_ISSUERS, "otrabotka: skanni avtomatik moslashtirish", OPS.RETAKE_DENY)
    from . import registrar_scan as RS
    raw, ext = OPS.decode_upload(body.data_url)
    meta = RS.read_scan(raw, ext)
    if not meta.get("reg_no"):
        raise HTTPException(422, "Varaqadagi ro'yxat raqami o'qilmadi — otrabotkani ro'yxatdan tanlab yuklang")
    r = db.one(_con, "SELECT * FROM retakes WHERE reg_no=?", (meta["reg_no"],))
    if not r: raise HTTPException(404, f"{meta['reg_no']} raqamli otrabotka varaqasi topilmadi")
    OPS._student_row(c, r["student_id"])
    out = OPS.store_scan(c, r, raw, ext)
    return {**out, "retake_id": r["id"], "reg_no": r["reg_no"]}

class DemoIn(BaseModel):
    variant: str = Field("signed", pattern="^(signed|unsigned)$")
    fmt: str = Field("pdf", pattern="^(pdf|png)$")

@router.post("/api/registrar/retakes/{rid}/demo-scan")
def api_demo_scan(rid: int, body: DemoIn, request: Request):
    """DEMO: o'qituvchi to'ldirgan (yoki imzolamagan) varaqaning sun'iy skanini yaratib, oddiy yuklash oqimidan o'tkazadi."""
    c = C(request); _need(c, OPS.RETAKE_ISSUERS, "otrabotka: demo skan", OPS.RETAKE_DENY)
    r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
    if not r: raise HTTPException(404)
    OPS._student_row(c, r["student_id"])
    raw, ext, _ = make_demo_scan(_con, r, body.variant, body.fmt)
    return OPS.store_scan(c, r, raw, ext)

@router.get("/api/registrar/retakes/{rid}/preview")
def api_preview(rid: int, request: Request):
    c = C(request); OPS._view_guard(c, "otrabotka: skan ko'rinishi")
    if c.role.key in ("call_center", "buxgalteriya"): raise AccessDenied("⛔ Otrabotkalar bu lavozim uchun emas.")
    r = db.one(_con, "SELECT * FROM retakes WHERE id=?", (rid,))
    if not r or not r["file"]: raise HTTPException(404)
    OPS._student_row(c, r["student_id"])
    f = (OPS.UPLOADS / r["file"]).resolve()
    if f.parent != OPS.UPLOADS.resolve() or not f.exists(): raise HTTPException(404)
    from . import registrar_scan as RS
    png = RS.preview_png(f.read_bytes(), f.suffix)
    if not png: raise HTTPException(415, "Skan ko'rinishini chiqarib bo'lmadi — faylni oching")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
