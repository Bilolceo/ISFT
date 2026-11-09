"""Lavozimlar bo'yicha ruxsatlar auditi (2026-11): har bir bo'lim o'z vazifasini bajara oladi, ortiqcha ma'lumot ochilmaydi.
Ishga tushirish (server ishlab turgan bo'lsin): .venv/bin/python tests/test_ruxsatlar.py"""
import sys, httpx

B = "http://127.0.0.1:8000"
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
db = sqlite3.connect(f"file:{pathlib.Path(__file__).resolve().parent.parent / 'data' / 'jarvis.db'}?mode=ro", uri=True)
forms = {r[0] for r in db.execute(f"SELECT DISTINCT study_form FROM students WHERE id IN ({','.join(str(x['student_id']) for x in sc[:200]) or 0})")}
ok(sc and forms == {"sirtqi"}, "Sirtqi bo'lim: faqat sirtqi ta'lim talabalari")
card = sirtqi.get(f"/api/ops/student/{sc[0]['student_id']}").json()
ok(card["debt"] is not None and card["can_retake"] and card["can_permit"], "Sirtqi bo'lim: sirtqi talaba kartasida to'lov holati, otrabotka va ruxsatnoma amallari")
kd = db.execute("SELECT g.student_id, g.subject FROM grades g JOIN students s ON s.id=g.student_id WHERE g.semester=1 AND g.score<40 AND s.study_form='kunduzgi' AND s.status='faol' LIMIT 1").fetchone()
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
print("— Shaxsiy ma'lumotlar —")
ok(httpx.get(B + "/api/me/profile").status_code == 401, "Shaxsiy ma'lumotlar: kirishsiz yopiq")
pn = S(43).get("/api/me/profile").json()
ok(pn["unit"]["key"] == "talabalar" and not pn["unit"]["am_head"] and "Baratov" in (pn["head"] or {}).get("name", "") and pn["curator"], "Registrator xodimi: bo'lim, bevosita rahbar va kurator prorektor ko'rinadi")
pr = S(3).get("/api/me/profile").json()
ok("Registrator ofisi" in pr["curated"], "O'quv prorektori: kuratorlikdagi bo'limlar ro'yxati")
ok(all(s["ip"] for s in pr["sessions"]) and sum(s["current"] for s in pr["sessions"]) == 1, "Faol sessiyalar: joriy sessiya belgilangan")
print(f"\nJami: {N[0]} tekshiruv · HAMMASI O'TDI")
