import os
"""«Talaba kartasi (360°)» (app/talaba_karta.py, GET /api/karta/{sid}): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_talaba_karta.py
Qamrov: kirishsiz 401; har bir faol lavozim uchun ruxsat (200/403) — Talabalar markazi qoidasi (student_ops._view_guard + ko'lam);
ko'lam: sirtqi — faqat sirtqi, tyutor — o'z guruhlari, kafedra — kafedra guruhlari, buxgalteriya — faqat kontrakt va faqat moliya,
call-markaz — faqat navbatidagi talaba (cheklangan); mavjud bo'lmagan talaba → 404; kartaning bo'limlari (reyting, joriy baholar,
apellyatsiya, qayta o'qish, buyruqlar, ko'chirish, hujjatlar, amaliyot, turar joy, xalqaro, talaba so'rovlari, to'lovlar, kontrakt qarzi)
to'g'ridan-to'g'ri bazadagi so'rovlar bilan bir xil; talaba (kabinet sessiyasi) kartani ocha olmaydi.
Bazani deyarli o'zgartirmaydi: bitta talaba kabinetidan ma'lumotnoma so'rovi yaratiladi va oxirida o'chiriladi.
"""
import json, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
SPW = os.environ.get("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")
N = [0]
CLEAN = []

def cleanup():
    for sql, a in CLEAN:
        try: w(sql, a)
        except Exception as e: print("  (tozalash:", e, ")")
    CLEAN.clear()

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond:
        cleanup(); sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally: con.close()

def q1(sql, args=()):
    r = q(sql, args); return next(iter(r[0].values())) if r else None

def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try: con.execute(sql, args); con.commit()
    finally: con.close()

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

K = "/api/karta"
FULL = ("talabalar", "registrator_xodim", "akademik", "prorektor_oquv")          # student_ops.FULL_VIEW — hamma talabalar
SCOPED = ("sirtqi", "tyutor", "kafedra", "buxgalteriya", "imtihon", "call_center")  # ko'lami cheklangan
FIN = ("talabalar", "registrator_xodim", "sirtqi", "buxgalteriya", "prorektor_oquv", "akademik")   # talaba_karta.FIN
ACTIONS = {"ruxsatnoma": ("talabalar", "registrator_xodim", "sirtqi"), "otrabotka": ("talabalar", "registrator_xodim", "tyutor", "sirtqi"),
           "malumotnoma": ("talabalar", "registrator_xodim", "tyutor", "sirtqi"), "buyruq": ("talabalar", "registrator_xodim", "sirtqi", "malumotlar_bazasi"),
           "qayta_oqish": ("talabalar", "registrator_xodim", "akademik", "kafedra", "sirtqi"),
           "apellyatsiya": ("talabalar", "registrator_xodim", "akademik", "imtihon", "kafedra")}
ACAD_KEYS = {"rating", "current", "appeals", "restudy", "orders", "transfers", "changes", "docs", "practice", "dorm", "intl", "requests"}
FIN_KEYS = {"payments", "deferments"}

# ---------------------------------------------------------------- talabalarni tanlash (seed ma'lumotlaridan)
def pick(sql, args=()):
    r = q(sql + " LIMIT 1", args)
    return r[0]["id"] if r else None

ACT = "s.status='faol'"
# 1) ko'p bo'limli kunduzgi kontrakt talaba: qayta o'qish + buyruq + to'lov bo'lsa yaxshi
S_RICH = (pick(f"""SELECT s.id FROM students s WHERE {ACT} AND s.study_form='kunduzgi' AND s.payment_type='kontrakt'
                   AND s.id IN (SELECT student_id FROM restudy) AND s.id IN (SELECT student_id FROM fin_payments) ORDER BY s.id""")
          or pick(f"SELECT s.id FROM students s WHERE {ACT} AND s.payment_type='kontrakt' AND s.id IN (SELECT student_id FROM restudy) ORDER BY s.id"))
S_DORM = pick(f"SELECT s.id FROM students s JOIN yj_residents r ON r.student_id=s.id WHERE {ACT} ORDER BY (SELECT COUNT(*) FROM yj_charges ch WHERE ch.resident_id=r.id) DESC, s.id")
S_PRAC = pick(f"SELECT s.id FROM students s WHERE {ACT} AND s.id IN (SELECT student_id FROM prac_assign WHERE base_id IS NOT NULL) ORDER BY s.id")
S_ORD = pick(f"""SELECT s.id FROM students s JOIN order_students os ON os.student_id=s.id JOIN orders o ON o.id=os.order_id
                 WHERE {ACT} AND COALESCE(o.demo,0)=0 GROUP BY s.id HAVING COUNT(DISTINCT o.id)>=2 ORDER BY s.id""")
S_APPEAL = pick("SELECT student_id id FROM grade_appeals ORDER BY id")
S_GRANT = pick(f"SELECT s.id FROM students s WHERE {ACT} AND s.payment_type='grant' ORDER BY s.id")
S_SIRTQI = pick(f"SELECT s.id FROM students s WHERE {ACT} AND s.study_form='sirtqi' AND s.payment_type='kontrakt' ORDER BY s.id")
TUT = uid("tyutor")
S_TUT_IN = pick(f"SELECT s.id FROM students s WHERE {ACT} AND s.group_id IN (SELECT group_id FROM tutor_groups WHERE user_id=?) ORDER BY s.id", (TUT,))
S_TUT_OUT = pick(f"SELECT s.id FROM students s WHERE {ACT} AND s.group_id NOT IN (SELECT group_id FROM tutor_groups WHERE user_id=?) ORDER BY s.id", (TUT,))
KAF = uid("kafedra"); KAF_DEP = q1("SELECT department_id FROM users WHERE id=?", (KAF,))
S_KAF_IN = pick(f"SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE {ACT} AND g.department_id=? ORDER BY s.id", (KAF_DEP,))
S_KAF_OUT = pick(f"SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE {ACT} AND g.department_id!=? ORDER BY s.id", (KAF_DEP,))
CC = uid("call_center")
S_CC_IN = pick("SELECT student_id id FROM ops_tasks WHERE assignee_role='call_center' ORDER BY id")
S_CC_OUT = pick("SELECT s.id FROM students s WHERE s.id NOT IN (SELECT student_id FROM ops_tasks WHERE assignee_role='call_center') ORDER BY s.id")
MAXID = q1("SELECT MAX(id) FROM students")
ok(all([S_RICH, S_DORM, S_PRAC, S_ORD, S_GRANT, S_SIRTQI, S_TUT_IN, S_TUT_OUT, S_KAF_IN, S_KAF_OUT, S_CC_IN, S_CC_OUT]),
   f"Seed'dan namunaviy talabalar tanlandi (boy #{S_RICH}, yotoqxona #{S_DORM}, amaliyot #{S_PRAC}, buyruq #{S_ORD}, grant #{S_GRANT}, sirtqi #{S_SIRTQI})")

# ---------------------------------------------------------------------------------------------
print("— 1. Kirishsiz va lavozimlar bo'yicha ruxsat")
ok(httpx.get(f"{B}{K}/{S_RICH}").status_code == 401, "Kirishsiz /api/karta → 401")
ok(httpx.get(f"{B}{K}/{S_RICH}", cookies={"sid": "soxta-token"}).status_code == 401, "Soxta sessiya → 401")

ROLES = q("SELECT role, MIN(id) id FROM users WHERE COALESCE(active,1)=1 GROUP BY role ORDER BY role")
CL = {r["role"]: S(r["id"]) for r in ROLES}
for r in ROLES:
    role = r["role"]
    st = CL[role].get(f"{K}/{S_RICH}").status_code     # S_RICH — kunduzgi kontrakt: FULL, imtihon, buxgalteriya ko'lamida
    if role in FULL + ("imtihon", "buxgalteriya"):
        ok(st == 200, f"{role} (#{r['id']}): kunduzgi kontrakt talaba kartasi → 200")
    elif role in ("sirtqi", "tyutor", "kafedra", "call_center"):
        ok(st in (200, 403), f"{role}: kartaga ruxsat ko'lamga bog'liq ({st}) — pastda alohida tekshiriladi")
    else:
        ok(st == 403, f"{role} (#{r['id']}): Talabalar markazi ruxsati yo'q yoki faqat jamlangan → 403")
for role in ("rektor", "kengash", "prorektor_yoshlar"):
    if role in CL:
        d = CL[role].get(f"{K}/{S_RICH}")
        ok(d.status_code == 403 and d.json().get("denied"), f"{role}: rahbariyat — individual karta yopiq (403, denied)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='talaba kartasi (360)' AND allowed=0") >= 1, "Rad etilgan urinishlar audit jurnalida")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='talaba kartasi (360)' AND allowed=1 AND detail=?", (f"#{S_RICH}",)) >= 1, "Ochilgan karta audit jurnalida (#sid)")

print("\n— 2. Ko'lam: sirtqi, tyutor, kafedra, buxgalteriya, call-markaz")
sir = CL["sirtqi"]
ok(sir.get(f"{K}/{S_SIRTQI}").status_code == 200, "Sirtqi bo'lim: sirtqi talaba → 200")
ok(sir.get(f"{K}/{S_RICH}").status_code == 403, "Sirtqi bo'lim: kunduzgi talaba → 403")
tc = S(TUT)
ok(tc.get(f"{K}/{S_TUT_IN}").status_code == 200, f"Tyutor #{TUT}: o'z guruhidagi talaba → 200")
ok(tc.get(f"{K}/{S_TUT_OUT}").status_code == 403, f"Tyutor #{TUT}: boshqa guruh talabasi → 403")
kc = S(KAF)
ok(kc.get(f"{K}/{S_KAF_IN}").status_code == 200, f"Kafedra #{KAF}: kafedra guruhi talabasi → 200")
ok(kc.get(f"{K}/{S_KAF_OUT}").status_code == 403, f"Kafedra #{KAF}: boshqa kafedra talabasi → 403")
bux = CL["buxgalteriya"]
ok(bux.get(f"{K}/{S_GRANT}").status_code == 403, "Buxgalteriya: grant talaba (kontrakt emas) → 403")
cc = S(CC)
d = J(cc.get(f"{K}/{S_CC_IN}"))
ok(d.get("limited") is True and d["role"] == "call_center" and d["actions"] == [], "Call-markaz: navbatidagi talaba — cheklangan karta")
ok(set(d) == {"base", "role", "actions", "limited"} and d["base"]["student"]["id"] == S_CC_IN, "Call-markaz: qo'shimcha bo'limlar (baho, to'lov, buyruq) yo'q")
ok(not ({"contract_amount", "paid_amount"} & set(d["base"]["student"] or {})) and d["base"]["retakes"] == [] and d["base"]["absences"] == [],
   "Call-markaz: kontrakt summasi, otrabotka va dars qoldirishlar ko'rinmaydi")
ok(cc.get(f"{K}/{S_CC_OUT}").status_code == 403, "Call-markaz: navbatda bo'lmagan talaba → 403")

print("\n— 3. Mavjud bo'lmagan talaba → 404 (500 emas)")
for role in ("talabalar", "akademik", "imtihon", "buxgalteriya", "sirtqi", "call_center"):
    for bad in (MAXID + 1000, 0, -5):
        st = CL[role].get(f"{K}/{bad}").status_code
        ok(st == 404, f"{role}: /api/karta/{bad} → 404 ({st})")
ok(CL["talabalar"].get(f"{K}/abc").status_code == 422, "Raqam bo'lmagan id → 422")
for role in ("kengash", "marketing", "xarid"):
    if role in CL:
        ok(CL[role].get(f"{K}/{MAXID + 1000}").status_code == 403, f"{role}: ruxsatsiz lavozimga talaba borligi oshkor qilinmaydi (403)")

# ---------------------------------------------------------------------------------------------
print("\n— 4. Bo'limlar lavozimga qarab")
for role in sorted(set(FULL + ("imtihon", "buxgalteriya"))):
    d = J(CL[role].get(f"{K}/{S_RICH}"))
    ok(d["role"] == role and sorted(d["actions"]) == sorted(a for a, rs in ACTIONS.items() if role in rs), f"{role}: rol va «Nima qilmoqchisiz?» amallari")
    keys = set(d)
    acad, fin = role != "buxgalteriya", role in FIN
    ok((ACAD_KEYS <= keys) == acad, f"{role}: o'quv bo'limlari {'bor' if acad else 'yo`q'}")
    if not acad: ok(not (ACAD_KEYS & keys), f"{role}: hech bir o'quv bo'limi yo'q (faqat moliya)")
    ok((FIN_KEYS <= keys) == fin and (fin or not (FIN_KEYS & keys)), f"{role}: to'lovlar bo'limi {'bor' if fin else 'yo`q'}")
d = J(bux.get(f"{K}/{S_RICH}"))
ok(d["base"]["facts"] == {} and d["base"]["absences"] == [] and d["base"]["retakes"] == [] and d["base"]["attempts"] == [],
   "Buxgalteriya: baholar, davomat, otrabotka, urinishlar tarixi bo'sh")
d = J(kc.get(f"{K}/{S_KAF_IN}"))
ok("contract_amount" not in d["base"]["student"] and d["base"]["debt"] is None and "payments" not in d, "Kafedra: kontrakt summasi, qarz va to'lovlar ko'rinmaydi")
d = J(tc.get(f"{K}/{S_TUT_IN}"))
ok("payments" not in d and ACAD_KEYS <= set(d), "Tyutor: o'quv bo'limlari bor, to'lovlar reyestri yo'q")

# ---------------------------------------------------------------------------------------------
print("\n— 5. Bo'limlar bazadagi ma'lumot bilan bir xil")
reg = CL["talabalar"]

def check_card(sid, label):
    d = J(reg.get(f"{K}/{sid}"))
    s = q("""SELECT s.full_name, s.study_form, s.payment_type, s.contract_amount, s.paid_amount, s.group_id, g.name grp, g.course
             FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""", (sid,))[0]
    st = d["base"]["student"]
    ok(st["id"] == sid and st["full_name"] == s["full_name"] and st["grp"] == s["grp"] and st["course"] == s["course"], f"{label}: asosiy ma'lumot (ism, guruh, kurs)")
    ok(d["study_form"] == s["study_form"], f"{label}: ta'lim shakli = {s['study_form']}")
    ok(st["contract_amount"] == s["contract_amount"] and st["paid_amount"] == s["paid_amount"]
       and d["base"]["debt"] == (s["contract_amount"] or 0) - (s["paid_amount"] or 0), f"{label}: kontrakt / to'langan / qarz bazadagidek")
    rc = q("SELECT semester, gpa, avg_score FROM rating_cache WHERE student_id=? ORDER BY semester DESC LIMIT 1", (sid,))
    ok((d["rating"] is None and not rc) or (d["rating"] and d["rating"]["semester"] == rc[0]["semester"] and d["rating"]["gpa"] == rc[0]["gpa"]),
       f"{label}: reyting — oxirgi semestr ({rc[0]['semester'] if rc else '—'})")
    cur = q("SELECT subject, oraliq FROM grades WHERE student_id=? AND semester=1 ORDER BY subject", (sid,))
    ok([(g["subject"], g["oraliq"]) for g in d["current"]] == [(g["subject"], g["oraliq"]) for g in cur], f"{label}: joriy semestr baholari ({len(cur)} ta fan)")
    ap = q("SELECT subject, status FROM grade_appeals WHERE student_id=? ORDER BY id DESC", (sid,))
    ok([(a["subject"], a["status"]) for a in d["appeals"]] == [(a["subject"], a["status"]) for a in ap], f"{label}: apellyatsiyalar ({len(ap)})")
    rs = q("SELECT subject, decision, amount, paid FROM restudy WHERE student_id=? ORDER BY id DESC", (sid,))
    ok([(x["subject"], x["decision"], x["amount"], x["paid"]) for x in d["restudy"]] == [(x["subject"], x["decision"], x["amount"], x["paid"]) for x in rs],
       f"{label}: qayta o'qish (summa, to'langan) — {len(rs)} ta")
    od = q("""SELECT DISTINCT o.id FROM order_students os JOIN orders o ON o.id=os.order_id WHERE os.student_id=? AND COALESCE(o.demo,0)=0""", (sid,))
    ok(sorted(o["id"] for o in d["orders"]) == sorted(o["id"] for o in od)[:40] if len(od) <= 40 else len(d["orders"]) == 40,
       f"{label}: buyruqlar — {len(od)} ta (demo buyruqlarsiz, takrorlanmaydi)")
    ok(len({o["id"] for o in d["orders"]}) == len(d["orders"]), f"{label}: buyruqlar ro'yxatida takror yo'q")
    ok(len(d["transfers"]) == q1("SELECT COUNT(*) FROM transfers WHERE student_id=?", (sid,)), f"{label}: ko'chirish/tiklash soni")
    ok(len(d["practice"]) == q1("SELECT COUNT(*) FROM prac_assign WHERE student_id=?", (sid,)), f"{label}: amaliyot biriktirishlari soni")
    pr = q("""SELECT a.status, b.name base FROM prac_assign a LEFT JOIN prac_bases b ON b.id=a.base_id WHERE a.student_id=? ORDER BY a.id DESC""", (sid,))
    ok([(p["status"], p["base"]) for p in d["practice"]] == [(p["status"], p["base"]) for p in pr], f"{label}: amaliyot holati va bazasi")
    dm = d["dorm"]
    ok(len(dm["residents"]) == q1("SELECT COUNT(*) FROM yj_residents WHERE student_id=?", (sid,))
       and len(dm["applications"]) == q1("SELECT COUNT(*) FROM yj_applications WHERE student_id=?", (sid,))
       and len(dm["rental"]) == q1("SELECT COUNT(*) FROM yj_rentals WHERE student_id=?", (sid,)), f"{label}: turar joy (yashash, ariza, ijara)")
    ok(len(d["intl"]) == q1("SELECT COUNT(*) FROM intl_applications WHERE student_id=?", (sid,)), f"{label}: xalqaro arizalar")
    ok(len(d["requests"]) == min(30, q1("SELECT COUNT(*) FROM student_requests WHERE student_id=?", (sid,))), f"{label}: talaba kabineti so'rovlari")
    ok(len(d["docs"]) == min(40, q1("SELECT COUNT(*) FROM documents WHERE params LIKE ?", (f'%"s:{sid}"%',))), f"{label}: berilgan hujjatlar")
    fp = q("SELECT receipt_no, amount, status, COALESCE(kind,'kontrakt') kind FROM fin_payments WHERE student_id=? ORDER BY paid_on DESC, id DESC LIMIT 30", (sid,))
    ok([(p["receipt_no"], p["amount"], p["status"]) for p in d["payments"]] == [(p["receipt_no"], p["amount"], p["status"]) for p in fp],
       f"{label}: to'lovlar reyestri ({len(fp)} ta kvitansiya)")
    ok(all(p.get("kind") in ("kontrakt", "qayta_oqish", "turar_joy") for p in d["payments"]), f"{label}: har bir to'lovda turi (kontrakt / qayta o'qish / turar joy)")
    ch = q("""SELECT ch.id, ch.amount, ch.paid FROM yj_charges ch JOIN yj_residents r ON r.id=ch.resident_id WHERE r.student_id=? ORDER BY ch.period DESC, ch.id DESC LIMIT 24""", (sid,))
    ok([(c["id"], c["amount"], c["paid"]) for c in d.get("dorm_charges", [])] == [(c["id"], c["amount"], c["paid"]) for c in ch],
       f"{label}: turar joy hisoblari (summa / to'langan) — {len(ch)} ta")
    ok(len(d["deferments"]) == q1("SELECT COUNT(*) FROM contract_deferments WHERE student_id=?", (sid,)), f"{label}: kontrakt muddati uzaytirishlari")
    tasks = q("SELECT id FROM ops_tasks WHERE student_id=? ORDER BY id DESC", (sid,))
    ok([t["id"] for t in d["base"]["tasks"]] == [t["id"] for t in tasks], f"{label}: Talabalar markazi topshiriqlari ({len(tasks)})")
    return d

seen = set()
for sid, label in ((S_RICH, "boy karta"), (S_DORM, "yotoqxona"), (S_PRAC, "amaliyot"), (S_ORD, "buyruqlar"), (S_APPEAL, "apellyatsiya"),
                   (S_SIRTQI, "sirtqi"), (S_GRANT, "grant")):
    if sid and sid not in seen:
        seen.add(sid); check_card(sid, f"#{sid} {label}")
d = J(reg.get(f"{K}/{S_DORM}"))
ok(len(d["dorm"]["residents"]) >= 1 and len(d["dorm_charges"]) >= 1, f"#{S_DORM}: yotoqxonada yashaydi va turar joy hisobi bor")
d = J(reg.get(f"{K}/{S_PRAC}"))
ok(any(p["base"] for p in d["practice"]), f"#{S_PRAC}: amaliyot bazasi ko'rsatiladi")
# buxgalteriya kartasidagi moliya bo'limi Registrator ofisi kartasi bilan bir xil
a, b = J(reg.get(f"{K}/{S_RICH}")), J(bux.get(f"{K}/{S_RICH}"))
ok(a["payments"] == b["payments"] and a["deferments"] == b["deferments"] and a["base"]["debt"] == b["base"]["debt"],
   "Buxgalteriya va Registrator ofisi bir xil to'lovlar va qarzni ko'radi")
# grant talaba: kontrakt qarzi yo'q
d = J(reg.get(f"{K}/{S_GRANT}"))
ok(d["base"]["student"]["payment_type"] == "grant" and (d["base"]["debt"] or 0) <= 0, "Grant talaba: kontrakt qarzi yo'q")

# ---------------------------------------------------------------------------------------------
print("\n— 6. Talaba kabineti: o'z so'rovi kartada; boshqa talaba kartasi ochilmaydi")
ST = q(f"""SELECT s.id, s.hemis_id FROM students s WHERE {ACT} AND s.hemis_id IS NOT NULL AND s.hemis_id!='' AND s.study_form='kunduzgi'
           AND s.id NOT IN (SELECT student_id FROM student_auth) AND s.id NOT IN (SELECT student_id FROM student_requests) ORDER BY s.id DESC LIMIT 1""")
if ST:
    me_sid, hemis = ST[0]["id"], ST[0]["hemis_id"]
    t = httpx.Client(base_url=B, timeout=60)
    lr = t.post("/api/talaba/login", json={"hemis_id": hemis, "password": SPW})
    ok(lr.status_code == 200, f"Talaba #{me_sid} kabinetga kirdi")
    CLEAN.append(("DELETE FROM student_auth WHERE student_id=?", (me_sid,)))
    if lr.json().get("must_change"):
        J(t.post("/api/talaba/password", json={"current": SPW, "new": "KartaTest#2026"}))
    r = J(t.post("/api/talaba/requests/certificate", json={"lang": "uz", "purpose": "", "note": "TEST karta"}))
    CLEAN.insert(0, ("DELETE FROM student_requests WHERE id=?", (r["id"],)))
    d = J(reg.get(f"{K}/{me_sid}"))
    ok(len(d["requests"]) == 1 and d["requests"][0]["kind"] == "malumotnoma" and d["requests"][0]["status"] == "yangi",
       "Talaba kabinetidagi ma'lumotnoma so'rovi kartaning «so'rovlar» bo'limida")
    ok(t.get(f"{K}/{me_sid}").status_code == 401, "Talaba sessiyasi bilan o'z kartasi (xodimlar API) → 401")
    ok(t.get(f"{K}/{S_RICH}").status_code == 401, "Talaba boshqa talabaning kartasini ocha olmaydi → 401")
    ok(t.get(f"/api/ops/student/{S_RICH}").status_code == 401, "Talaba Talabalar markazi kartasini ham ocha olmaydi → 401")
    tm = J(t.get("/api/talaba/me"))
    ok(json.dumps(tm).find(str(q1("SELECT full_name FROM students WHERE id=?", (S_RICH,)))) < 0, "Talaba kabineti faqat o'z ma'lumotini beradi")
    ok(t.get(f"/api/moliya/student/{S_RICH}").status_code == 401, "Talaba moliya kartasini ocha olmaydi → 401")
else:
    print("  (talaba kabineti tekshiruvi o'tkazib yuborildi: mos talaba topilmadi)")

cleanup()
print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
