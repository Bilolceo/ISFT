import os
"""Lavozimlar bo'yicha ruxsatlar auditi (2026-11): har bir bo'lim o'z vazifasini bajara oladi, ortiqcha ma'lumot ochilmaydi.
Ishga tushirish (server ishlab turgan bo'lsin): .venv/bin/python tests/test_ruxsatlar.py"""
import sys, httpx

B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
N = [0]
def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}); assert r.status_code == 200, (uid, r.text)
    return c
def ok(cond, msg):
    N[0] += 1; print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

rektor, kengash, moliya, yoshlar, imtihon, buxg, kadrlar = S(2), S(1), S(5), S(6), S(8), S(11), S(12)
kafedra31, reg, akademik, kotib, ithead, sirtqi, amaliyot, mb, ilmiy_pro = S(31), S(17), S(18), S(20), S(21), S(27), S(29), S(28), S(4)

def allowed(c, key):
    return next((t["allowed"] for t in c.get("/api/docs/catalog").json() if t.get("key") == key), None)

print("— Hujjatlar markazi: o'z vazifasi uchun hujjat —")
ok(allowed(amaliyot, "practice") is True, "Amaliyot bo'limi: amaliyot yo'llanmasi")
ok(allowed(sirtqi, "call_letter") is True, "Sirtqi bo'lim: sessiyaga chaqiruv xati")
ok(allowed(imtihon, "debtors_list") is True and allowed(akademik, "debtors_list") is True, "Imtihon va Akademik: qarzdorlar ro'yxati")
ok(allowed(akademik, "load") is True, "Akademik bo'lim: o'quv yuklama taqsimoti")
ok(allowed(kotib, "minutes") is True and allowed(kotib, "exec_notice") is True, "Kotib: majlis bayonnomasi va ijro nazorati xati")
ok(allowed(ilmiy_pro, "invitation") is True, "Ilmiy ishlar prorektori: viza taklifnomasi")
ok(allowed(kengash, "exec_notice") is False and allowed(kengash, "memo") is False, "Kuzatuv kengashi: operativ xatlar yo'q")
ok(allowed(mb, "memo") is True, "Ma'lumotlar bazasi bo'limi: xizmat xati (barcha xodimlar)")
ok(allowed(sirtqi, "practice") is False, "Sirtqi bo'lim: amaliyot yo'llanmasi — yo'q")

print("— Talabalar markazi: ko'lam va qoidalar —")
rules = lambda c: {r["rule"] for r in c.get("/api/ops/summary").json()["by_rule"]}
ok(rules(buxg) <= {"kontrakt"}, "Buxgalteriya: faqat kontrakt")
ok("kontrakt" in rules(sirtqi), "Sirtqi bo'lim: o'z talabalarining kontrakt holatlari (o'qish — sessiyaga qo'yish va ruxsatnoma uchun)")
sc = sirtqi.get("/api/ops/cases").json()
import sqlite3, pathlib
db = sqlite3.connect(f"file:{os.environ.get('ISFT_CORE_DB') or pathlib.Path(__file__).resolve().parent.parent / 'data' / 'jarvis.db'}?mode=ro", uri=True)
forms = {r[0] for r in db.execute(f"SELECT DISTINCT study_form FROM students WHERE id IN ({','.join(str(x['student_id']) for x in sc[:200]) or 0})")}
ok(sc and forms == {"sirtqi"}, "Sirtqi bo'lim: faqat sirtqi ta'lim talabalari")
card = sirtqi.get(f"/api/ops/student/{sc[0]['student_id']}").json()
ok(card["debt"] is not None and card["can_retake"] and card["can_permit"], "Sirtqi bo'lim: sirtqi talaba kartasida to'lov holati, otrabotka va ruxsatnoma amallari")
kd = db.execute("SELECT g.student_id, g.subject FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester<1 AND g.score<40 AND s.study_form='kunduzgi' AND s.status='faol' LIMIT 1").fetchone()   # akademik qarz (yakunlangan semestr)
ok(sirtqi.post("/api/ops/retakes", json={"student_id": kd[0], "subject": kd[1]}).status_code == 403, "Sirtqi bo'lim: kunduzgi talabaga otrabotka varaqasi bera olmaydi")
kc = kafedra31.get("/api/ops/cases").json()
dep = {r[0] for r in db.execute(f"SELECT DISTINCT g.department_id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.id IN ({','.join(str(x['student_id']) for x in kc[:200]) or 0})")}
ok(kc and dep == {2} and {x["rule"] for x in kc} <= {"akademik", "otrabotka", "davomat"}, "Kafedra mudiri: o'z kafedrasi, o'quv holatlari")
ok(kafedra31.post("/api/ops/evaluate").status_code == 403, "Kafedra: qoidalarni ishga tushira olmaydi")
ok(imtihon.get("/api/ops/retakes").status_code == 200 and rules(imtihon) <= {"akademik", "otrabotka"}, "Imtihon bo'limi: otrabotkalar va o'zlashtirish (ko'rish)")
ok(imtihon.post("/api/ops/retakes", json={"student_id": kd[0], "subject": kd[1]}).status_code == 403, "Imtihon bo'limi: otrabotka varaqasini bermaydi — bu Registrator ofisi ishi")
ok(kafedra31.get(f"/api/ops/student/{kc[0]['student_id']}").json()["debt"] is None, "Kafedra mudiri: talaba kartasida kontrakt summasi yo'q")
ok(yoshlar.get("/api/ops/summary").status_code == 200 and yoshlar.get("/api/ops/cases").status_code == 403, "Yoshlar prorektori: faqat jamlangan")
ok(kadrlar.get("/api/ops/summary").status_code == 403, "Kadrlar: Talabalar markazi yopiq")

print("— Auditoriyalar va kameralar —")
ok(akademik.get("/api/spaces/overview").status_code == 200, "Akademik bo'lim: auditoriyalar fondi (dars jadvali uchun)")
ok(moliya.get("/api/spaces/overview").status_code == 200, "Moliya prorektori: auditoriyalar (xo'jalik kuratorligi)")
ok(yoshlar.get("/api/cams/queues").status_code == 200, "Yoshlar prorektori: zal to'lishi signalini ocha oladi")
ok(kengash.get("/api/spaces/overview").status_code == 200, "Kuzatuv kengashi: bandlik statistikasi ochiq")
ok(kengash.get("/api/cams/events").status_code == 403 and kengash.get("/api/cams/health").status_code == 403, "Kuzatuv kengashi: xavfsizlik voqealari yopiq")
ev = ithead.get("/api/cams/events?days=31&prio=4").json()
ok(ev["can_manage"] and ev["manage_groups"] == ["kamera"], "AT bo'limi: faqat kamera texnik holati boshqaruvi")
sec = next((e for e in ev["events"] if e["group"] != "kamera" and e["status"] == "yangi"), None)
if sec: ok(ithead.post(f"/api/cams/events/{sec['id']}/korildi", json={"note": ""}).status_code == 403, "AT bo'limi: xavfsizlik voqeasini belgilay olmaydi (403)")
ok(ithead.get("/api/cams/health").status_code == 200, "AT bo'limi: kameralar salomatligi ochiq")

print("— Ruxsat jadvali —")
ok(httpx.get(B + "/api/rbac").status_code == 401, "Ruxsat jadvali: kirishsiz yopiq")
ok(len(reg.get("/api/rbac").json()["roles"]) == 1, "Oddiy lavozim: faqat o'z ruxsatlari")
ok(len(rektor.get("/api/rbac").json()["roles"]) > 30, "Rektor: to'liq jadval")
me = lambda c: set(c.get("/api/me").json()["allow"])
ok({"facilities", "spaces", "admissions"} <= me(moliya), "Moliya prorektori: xo'jalik, auditoriyalar, qabul")
ok("ops" in me(sirtqi) and "contracts" not in me(sirtqi), "Sirtqi: markaz bor, kontrakt yo'q")
print("— Bo'sh qolgan lavozimlarga real navbat (2026-11) —")
itstaff, devon, xarid, xoj, yurist = S(22), S(40), S(42), S(16), S(39)
ok({"tasks", "requests"} == me(itstaff), "AT muhandisi: topshiriqlar + murojaatlar (AT navbati)")
sv = itstaff.get("/api/svc/overview").json()
ok(sv["tabs"] == ["requests"] and not sv["requests"]["can_broadcast"], "AT muhandisi: faqat murojaatlar, umumiy xabar yo'q")
ok(all(r["unit"] == "Axborot texnologiyalari bo'limi" or r["assignee_user"] == 22 for r in sv["requests"]["requests"]), "AT muhandisi: faqat AT navbati va o'ziga biriktirilganlar")
inc = next((i["id"] for i in sv["requests"]["incidents"] if i["status"] == "ochiq"), None)
if inc: ok(itstaff.post(f"/api/svc/incidents/{inc}/resolve").status_code == 403 and itstaff.post(f"/api/svc/incidents/{inc}/notify", json={"text": "x" * 30}).status_code == 403,
           "AT muhandisi: hodisani yopa olmaydi va umumiy xabar yubora olmaydi (403)")
other = next((r for r in rektor.get("/api/svc/overview").json()["requests"]["requests"] if r["unit"] == "Registrator ofisi" and r["status"] == "yangi"), None)
if other: ok(itstaff.post(f"/api/svc/requests/{other['id']}/status", json={"status": "jarayonda"}).status_code == 404, "AT muhandisi: boshqa bo'lim murojaatini ololmaydi (404)")
ok(itstaff.post("/api/svc/requests/1/assign", json={"user_id": 22}).status_code == 403, "AT muhandisi: murojaatni biriktira olmaydi — AT boshlig'i ishi (403)")
ok({"tasks", "chancery"} == me(devon), "Devonxona: topshiriqlar + devonxona (buyruqlar reyestri, chiquvchi yozishmalar)")
ok(devon.get("/api/orders/meta").status_code == 200 and devon.get("/api/orders/outgoing").status_code == 200, "Devonxona: buyruqlar reyestri va chiquvchi jurnal ochiq")
ok(devon.get("/api/orders/audit/issues").status_code == 403 and devon.get("/api/ops/summary").status_code == 403, "Devonxona: talabalar auditi va Talabalar markazi yopiq")
ok({"tasks", "procurement"} == me(xarid), "Xarid bo'limi: topshiriqlar + xarid so'rovlari")
xv = xarid.get("/api/svc/overview").json()
ok(xv["tabs"] == ["procurement"] and xv["procurement"]["can_status"], "Xarid bo'limi: faqat xarid so'rovlari, holatni yuritadi")
ok(xarid.get("/api/svc/photo/0000000000000000.jpg").status_code == 403, "Xarid bo'limi: nosozlik rasmlari (xo'jalik ma'lumoti) yopiq")
ok("procurement" in me(xoj) and xoj.get("/api/svc/overview").json()["procurement"]["can_status"] is False, "Xo'jalik: xarid so'rovini yuboradi, holatini Xarid yuritadi")
pr = xv["procurement"]["items"]
if pr: ok(xoj.post(f"/api/svc/procurement/{pr[0]['id']}/status", json={"status": "yetkazildi"}).status_code == 403, "Xo'jalik: xarid holatini o'zgartira olmaydi (403)")
ok("procurement" in me(moliya), "Moliya prorektori: xarid so'rovlarini ko'radi (kuratorlik)")
ok("international" in me(yurist) and yurist.get("/api/section/international").status_code == 200 and yurist.get("/api/section/finance").status_code == 403,
   "Yuridik bo'lim: hamkorlik shartnomalari reyestri ochiq, moliya yopiq")
ok(kadrlar.get("/api/orders/meta").json()["caps"]["edit_staff"] and kadrlar.get("/api/orders/audit/issues").status_code == 403, "Kadrlar: xodimlar buyruqlari; talabalar auditi yopiq")
for k, want in ((37, {"kpi", "reports", "tasks"}), (38, {"kpi", "academic", "reports", "tasks"}), (41, {"admissions", "tasks"})):
    ok(me(S(k)) == want, f"#{k}: ruxsatlar o'zgarmadi — {sorted(want)} (ish stoli mavjud resurslar ustida)")

print("— Lavozim ish stollari (app/desks.py): strategik, sifat, marketing, yuridik —")
import json as _json, re as _re
strat, sifat, mark, yur = S(37), S(38), S(41), S(39)
ds = strat.get("/api/desk").json()
ok(ds["kind"] == "strategik" and len(ds["indicators"]) >= 8 and all(i["value"] is not None for i in ds["indicators"]) and ds["by_faculty"],
   f"Strategik bo'lim: KPI paneli — {len(ds['indicators'])} ta ko'rsatkich va fakultetlar kesimi (bo'sh panel emas)")
dq = sifat.get("/api/desk").json()
ok(dq["kind"] == "sifat" and dq["by_faculty"] and dq["by_course"] and any(i["key"] == "ozlashtirmagan" for i in dq["indicators"]),
   "Sifat boshqarmasi: akademik sifat — fakultet/kurs kesimi, o'zlashtirmaganlar ulushi")
dm = mark.get("/api/desk").json()
ok(dm["kind"] == "marketing" and dm["funnel"] and dm["by_direction"] and all("conv" in r for r in dm["by_direction"]), "Marketing: qabul voronkasi va yo'nalishlar konversiyasi")
dy = yur.get("/api/desk").json()
ok(dy["kind"] == "yuridik" and dy["agreements"] and all("days_left" in a for a in dy["agreements"]), f"Yuridik: shartnomalar reyestri ({len(dy['agreements'])} ta), muddat bo'yicha navbat")
blob = _json.dumps([ds, dq, dm, dy], ensure_ascii=False)
ok(not _re.search(r'"(full_name|phone|passport|hemis_id|contact)"', blob), "Ish stollarida shaxsiy ma'lumot yo'q (ism, telefon, pasport, HEMIS ID)")
ok(rektor.get("/api/desk").json() == {"kind": None} and S(22).get("/api/desk").json() == {"kind": None}, "Boshqa lavozimlar: ish stoli yo'q (kind=None), xato emas")
csvr = strat.get("/api/desk/export.csv")
ok(csvr.status_code == 200 and "text/csv" in csvr.headers["content-type"] and "Faol talabalar" in csvr.text, "Strategik: KPI jadvali CSV eksporti")
ok(yur.get("/api/desk/export.csv").status_code == 403, "Yuridik: CSV eksport yo'q (403)")
pid = dy["agreements"][0]["id"]
ok(yur.post(f"/api/desk/legal/{pid}", json={"status": "etiroz", "note": ""}).status_code == 400, "Yuridik xulosa: e'tirozda izoh majburiy (400)")
ok(yur.post(f"/api/desk/legal/{pid}", json={"status": "boshqa"}).status_code == 400, "Yuridik xulosa: noto'g'ri tur (400)")
ok(strat.post(f"/api/desk/legal/{pid}", json={"status": "korib_chiqildi"}).status_code == 403, "Yuridik xulosani boshqa bo'lim qayd eta olmaydi (403)")
ok(yur.post(f"/api/desk/legal/{pid}", json={"status": "uzaytirish", "note": "test: uzaytirish tavsiya"}).status_code == 200, "Yuridik: xulosa qayd etildi")
a1 = next(a for a in yur.get("/api/desk").json()["agreements"] if a["id"] == pid)
ok(a1["review"] and a1["review"]["status"] == "uzaytirish", "Yuridik: xulosa reyestrda ko'rinadi")
db2 = sqlite3.connect(os.environ.get("ISFT_CORE_DB") or str(pathlib.Path(__file__).resolve().parent.parent / "data" / "jarvis.db"))
db2.execute("DELETE FROM legal_reviews WHERE note LIKE 'test:%'"); db2.commit(); db2.close()
import time as _t
t0 = _t.time(); r15 = S(15).get("/api/dashboard"); dt15 = _t.time() - t0
ok(r15.status_code == 200 and dt15 < 15, f"O'qituvchi paneli: {dt15:.1f} s (ix_students_group indeksi; avval ~60–90 s / 500)")

print("— Shaxsiy ma'lumotlar —")
ok(httpx.get(B + "/api/me/profile").status_code == 401, "Shaxsiy ma'lumotlar: kirishsiz yopiq")
pn = S(43).get("/api/me/profile").json()
ok(pn["unit"]["key"] == "talabalar" and not pn["unit"]["am_head"] and "Baratov" in (pn["head"] or {}).get("name", "") and pn["curator"], "Registrator xodimi: bo'lim, bevosita rahbar va kurator prorektor ko'rinadi")
pr = S(3).get("/api/me/profile").json()
ok("Registrator ofisi" in pr["curated"], "O'quv prorektori: kuratorlikdagi bo'limlar ro'yxati")
ok(all(s["ip"] for s in pr["sessions"]) and sum(s["current"] for s in pr["sessions"]) == 1, "Faol sessiyalar: joriy sessiya belgilangan")
print(f"\nJami: {N[0]} tekshiruv · HAMMASI O'TDI")
