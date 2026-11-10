import os
"""«Xalqaro hamkorlik» (app/xalqaro.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_xalqaro.py
Qamrov: shartnoma hayotiy sikli (qoralama → yuridik → imzo → amalda → uzaytirish; e'tiroz va qaytarish), hamkorlar reyestriga
sinxronlash, 90/30 kun ogohlantirishi, mobillik tanlovi (mezonlar, avtomatik tekshiruv, komissiya bali, saralash, zaxira, jo'nash,
qaytish), kredit tan olish (Akademik bo'lim), xorijiy talabalar vizasi, delegatsiyalar, talaba kabinetidan ariza, lavozimlar ko'lami.
Test bazani o'zgartiradi (test yozuvlari «TEST» belgisi bilan); demo holatini tiklash uchun — `python -m app.seed`.
"""
import datetime as dt, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
TODAY = CLK.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None

def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try: con.execute(sql, args); con.commit()
    finally: con.close()

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

X = "/api/xalqaro"
xq, yur, rek, aka, ilm, ken, cc, bux = (S(uid(r)) for r in ("xalqaro", "yuridik", "rektor", "akademik", "prorektor_ilmiy", "kengash", "call_center", "buxgalteriya"))

print("— Ruxsatlar —")
ok(httpx.get(B + X + "/meta").status_code == 401, "Kirishsiz: 401")
for cl, nm in ((cc, "Call-markaz"), (bux, "Buxgalteriya")):
    for p in ("/meta", "/overview", "/agreements", "/calls", "/foreign", "/credits"):
        ok(cl.get(X + p).status_code == 403, f"{nm}: {p} → 403")
m = J(xq.get(X + "/meta")); ok(m["can"]["edit"] and "credits" in m["tabs"], "Xalqaro bo'lim: barcha bo'limlar, tahrir")
m = J(aka.get(X + "/meta")); ok(m["tabs"] == ["credits"] and m["can"]["credits"], "Akademik bo'lim: faqat kredit tan olish")
ok(aka.get(X + "/agreements").status_code == 403, "Akademik: shartnomalar → 403")
ok(aka.get(X + "/overview").status_code == 403, "Akademik: umumiy ko'rinish → 403")
ok(ken.get(X + "/agreements").status_code == 403 and ken.get(X + "/overview").status_code == 200, "Kengash: faqat umumiy ko'rinish")
ok(yur.get(X + "/calls").status_code == 403 and yur.get(X + "/foreign").status_code == 403, "Yuridik: mobillik va xorijiy talabalar → 403")
ok(rek.get(X + "/foreign").status_code == 403, "Rektor: xorijiy talabalar ro'yxati (shaxsiy) → 403, faqat jamlangan")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='international' AND allowed=0 AND action LIKE 'xalqaro:%'") > 0, "Rad etilgan so'rovlar auditda")

print("— Demo ma'lumot —")
o = J(xq.get(X + "/overview"))
ok(o["agreements"]["active"] > 5, f"Amaldagi shartnomalar: {o['agreements']['active']}")
ok(o["agreements"]["queue"] >= 2, "Navbatda: yuridik ko'rik va imzo")
ok(all(e["days_left"] <= 90 for e in o["agreements"]["expiring"]), "Tugayotganlar ro'yxati — 90 kun ichida")
ok(o["foreign"]["total"] >= 5 and o["foreign"]["alerts"] >= 1, "Xorijiy talabalar va viza ogohlantirishlari")
ok(len(o["mobility"]["calls"]) >= 1, "Mobillik tanlovlari")

print("— Shartnoma hayotiy sikli —")
body = {"partner_name": "TEST Hamkor universiteti", "country": "Niderlandiya", "kind": "Akademik almashinuv", "start": D(10), "end": D(10 + 1826),
        "kpi_exchange": 5, "kpi_joint": 0}
ok(yur.post(X + "/agreements", json=body).status_code == 403, "Yuridik qoralama yarata olmaydi")
J(xq.post(X + "/agreements", json={**body, "end": D(5)}), 400); ok(True, "Tugash < boshlanish → 400")
aid = J(xq.post(X + "/agreements", json=body))["id"]
ok(J(xq.get(X + f"/agreements/{aid}"))["status"] == "qoralama", "Qoralama yaratildi")
ok(rek.post(X + f"/agreements/{aid}/sign").status_code == 409, "Qoralamani imzolab bo'lmaydi (409)")
J(xq.post(X + f"/agreements/{aid}/submit")); ok(True, "Yuridik ko'rikka yuborildi")
ok(xq.post(X + f"/agreements/{aid}/legal", json={"decision": "mos"}).status_code == 403, "Xalqaro bo'lim yuridik xulosa bera olmaydi")
J(yur.post(X + f"/agreements/{aid}/legal", json={"decision": "etiroz", "note": ""}), 400); ok(True, "E'tiroz izohsiz → 400")
J(yur.post(X + f"/agreements/{aid}/legal", json={"decision": "etiroz", "note": "8-band: intellektual mulk aniqlashtirilsin"}))
ok(q1("SELECT status FROM intl_agreements WHERE id=?", (aid,)) == "qaytarildi", "E'tiroz → qaytarildi")
J(xq.put(X + f"/agreements/{aid}", json={**body, "title": "TEST shartnoma (tuzatilgan)"})); ok(True, "Qaytarilgan shartnoma tahrirlandi")
J(xq.post(X + f"/agreements/{aid}/submit"))
J(yur.post(X + f"/agreements/{aid}/legal", json={"decision": "mos", "note": ""}))
ok(q1("SELECT status FROM intl_agreements WHERE id=?", (aid,)) == "imzoda", "Yuridik mos → rektor imzosida")
ok(xq.put(X + f"/agreements/{aid}", json=body).status_code == 400, "Imzodagi shartnoma tahrirlanmaydi")
ok(xq.post(X + f"/agreements/{aid}/sign").status_code == 403, "Xalqaro bo'lim imzolay olmaydi")
r = J(rek.post(X + f"/agreements/{aid}/sign"))
ok(r["status"] == "faol" and r["partner_id"], "Rektor imzoladi → amalda")
ok(q1("SELECT status FROM partners WHERE id=?", (r["partner_id"],)) == "faol", "Hamkorlar reyestriga yozildi (partners)")
d = J(xq.get(X + f"/agreements/{aid}"))
ok([x["action"] for x in d["log"]][:1] == ["Imzolandi"] and len(d["log"]) >= 6, "Tarix jurnali to'liq")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='xalqaro: shartnomani imzolash' AND allowed=1") >= 1, "Imzo audit jurnalida")
J(xq.post(X + f"/agreements/{aid}/activities", json={"kind": "almashinuv", "title": "TEST almashinuv", "date": D(30), "count": 2}), 400)
ok(True, "Kelajakdagi tadbir sanasi → 400")
J(xq.post(X + f"/agreements/{aid}/activities", json={"kind": "almashinuv", "title": "TEST almashinuv", "date": D(0), "count": 2}))
d = J(xq.get(X + f"/agreements/{aid}"))
ok(d["kpi"]["exchange_fact"] == 2 and d["kpi"]["exchange_plan"] == 5, "KPI: reja 5, fakt 2")
ok(q1("SELECT students_exchanged FROM partners WHERE id=?", (r["partner_id"],)) == 2, "Almashinuv soni reyestrda yangilandi")

print("— Ogohlantirish va uzaytirish —")
w("UPDATE intl_agreements SET end=? WHERE id=?", (D(20), aid))
a = [x for x in J(xq.get(X + "/agreements?status=tugamoqda"))["items"] if x["id"] == aid]
ok(a and a[0]["alert"] == "high", "30 kun ichida → yuqori ogohlantirish")
w("UPDATE intl_agreements SET end=? WHERE id=?", (D(70), aid))
a = [x for x in J(xq.get(X + "/agreements?status=tugamoqda"))["items"] if x["id"] == aid]
ok(a and a[0]["alert"] == "mid", "90 kun ichida → o'rta ogohlantirish")
nid = J(xq.post(X + f"/agreements/{aid}/renew"))["id"]
ok(xq.post(X + f"/agreements/{aid}/renew").status_code == 409, "Ikkinchi uzaytirish → 409")
n = J(xq.get(X + f"/agreements/{nid}"))
ok(n["renew_of"] == aid and n["start"] > D(70) and n["previous"]["id"] == aid, "Uzaytirish qoralamasi eski shartnomaga bog'langan")
J(xq.post(X + f"/agreements/{nid}/submit")); J(yur.post(X + f"/agreements/{nid}/legal", json={"decision": "mos"})); J(rek.post(X + f"/agreements/{nid}/sign"))
ok(q1("SELECT status FROM intl_agreements WHERE id=?", (aid,)) == "uzaytirildi", "Yangi imzo → eski shartnoma «uzaytirildi»")
ok(q1("SELECT partner_id FROM intl_agreements WHERE id=?", (nid,)) == r["partner_id"], "Hamkor yozuvi bitta (takrorlanmaydi)")
ok(q1("SELECT expires FROM partners WHERE id=?", (r["partner_id"],)) == n["end"], "Reyestrda yangi tugash sanasi")
w("UPDATE intl_agreements SET end=? WHERE id=?", (D(-1), nid))
J(xq.get(X + "/agreements"))
ok(q1("SELECT status FROM intl_agreements WHERE id=?", (nid,)) == "tugagan", "Muddati o'tdi → avtomatik «tugagan»")
ok(q1("SELECT status FROM partners WHERE id=?", (r["partner_id"],)) == "muddati tugagan", "Reyestrda ham «muddati tugagan»")
# rektor qaytarishi
aid2 = J(xq.post(X + "/agreements", json={**body, "partner_name": "TEST Ikkinchi hamkor"}))["id"]
J(xq.post(X + f"/agreements/{aid2}/submit")); J(yur.post(X + f"/agreements/{aid2}/legal", json={"decision": "mos"}))
J(rek.post(X + f"/agreements/{aid2}/return", json={"note": ""}), 400)
J(rek.post(X + f"/agreements/{aid2}/return", json={"note": "Moliyaviy majburiyatlar bandi qayta ko'rilsin"}))
ok(q1("SELECT status FROM intl_agreements WHERE id=?", (aid2,)) == "qaytarildi", "Rektor qaytardi → qaytarildi")
J(xq.post(X + f"/agreements/{aid2}/cancel", json={"note": "test"}))
ok(q1("SELECT status FROM intl_agreements WHERE id=?", (aid2,)) == "bekor", "Qoralama bekor qilindi")

print("— Mobillik tanlovi —")
call = {"title": "TEST almashinuv tanlovi", "country": "Niderlandiya", "seats": 2, "min_gpa": 3.5, "lang_min": 5.5, "deadline": D(10), "mob_start": D(60), "mob_end": D(180)}
ok(yur.post(X + "/calls", json=call).status_code == 403, "Yuridik tanlov e'lon qila olmaydi")
J(xq.post(X + "/calls", json={**call, "deadline": D(-1)}), 400); ok(True, "O'tgan ariza muddati → 400")
J(xq.post(X + "/calls", json={**call, "agreement_id": aid2}), 400); ok(True, "Bekor shartnoma asosida tanlov → 400")
cid = J(xq.post(X + "/calls", json=call))["id"]
SEM = q1("SELECT MAX(semester) FROM rating_cache WHERE semester < 1")
good = [r[0] for r in q(f"""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id JOIN rating_cache rc ON rc.student_id=s.id AND rc.semester=?
    WHERE s.status='faol' AND g.course BETWEEN 2 AND 3 AND rc.gpa>=4.2 AND NOT EXISTS (SELECT 1 FROM grades x WHERE x.student_id=s.id AND x.semester<1 AND x.score IS NOT NULL AND x.score<60)
    AND s.id NOT IN (SELECT student_id FROM intl_applications) ORDER BY s.id LIMIT 5""", (SEM,))]
low = q1(f"""SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id JOIN rating_cache rc ON rc.student_id=s.id AND rc.semester=?
    WHERE s.status='faol' AND g.course=2 AND rc.gpa<3.0 ORDER BY s.id LIMIT 1""", (SEM,))
ok(len(good) == 5 and low, "Sinov talabalari topildi")
apps = []
for i, sid in enumerate(good[:4]):
    r = J(xq.post(X + f"/calls/{cid}/applications", json={"student_id": sid, "lang_score": 6.0 + i * 0.5}))
    ok(r["eligible"] == 1, f"Ariza #{r['id']}: mezonlarga mos (GPA {r['gpa']})"); apps.append(r["id"])
r = J(xq.post(X + f"/calls/{cid}/applications", json={"student_id": low, "lang_score": 7.0}))
ok(r["eligible"] == 0 and "GPA" in r["note"], f"Past GPA → mos emas ({r['note']})")
r = J(xq.post(X + f"/calls/{cid}/applications", json={"student_id": good[4], "lang_score": 5.0}))
ok(r["eligible"] == 0 and "til" in r["note"], "Past til bali → mos emas")
ok(xq.post(X + f"/calls/{cid}/applications", json={"student_id": good[0], "lang_score": 6}).status_code == 409, "Takroriy ariza → 409")
hem = q1("SELECT hemis_id FROM students WHERE id=?", (good[0],))
ok(xq.post(X + f"/calls/{cid}/applications", json={"hemis_id": "000NOTEXIST", "lang_score": 6}).status_code == 404, "Noma'lum HEMIS ID → 404")
c = J(xq.get(X + f"/calls/{cid}"))
ok(c["stats"]["jami"] == 6 and all(a.get("full_name") for a in c["applications"]), "Tanlov: 6 ariza, ismlar bilan (Xalqaro bo'lim)")
rc = J(rek.get(X + f"/calls/{cid}"))
ok(rc["applications"] == [] and rc["stats"]["jami"] == 6, "Rektor: faqat jamlangan (ismlarsiz)")
ok(xq.post(X + f"/calls/{cid}/select").status_code == 409, "Komissiya bosqichisiz saralash → 409")
J(xq.post(X + f"/calls/{cid}/close"))
ok(xq.post(X + f"/calls/{cid}/applications", json={"student_id": good[4], "lang_score": 7}).status_code == 409, "Yopilgan tanlovga ariza → 409")
ok(xq.post(X + f"/calls/{cid}/select").status_code == 409, "Komissiya bali to'liq emas → 409")
ok(aka.post(X + f"/applications/{apps[0]}/score", json={"interview": 10}).status_code == 403, "Akademik bo'lim komissiya emas")
bad = q1("SELECT id FROM intl_applications WHERE call_id=? AND eligible=0", (cid,))
ok(xq.post(X + f"/applications/{bad}/score", json={"interview": 10}).status_code == 409, "Mos bo'lmagan arizaga ball → 409")
for i, a in enumerate(apps):
    J((ilm if i % 2 else xq).post(X + f"/applications/{a}/score", json={"interview": 15 - i * 3 if i < 3 else 15}))
ok(True, "Komissiya ballari qo'yildi (Xalqaro bo'lim va ilmiy prorektor)")
r = J(xq.post(X + f"/calls/{cid}/select"))
ok(r["saralandi"] == 2 and r["zaxira"] == 2, "Saralash: 2 o'rin, 2 zaxira")
c = J(xq.get(X + f"/calls/{cid}"))
ranks = [(a["rank"], a["status"], a["total"]) for a in c["applications"] if a["eligible"]]
ok(all(ranks[i][2] >= ranks[i + 1][2] for i in range(len(ranks) - 1)), "O'rinlar jami ball bo'yicha")
ok(c["status"] == "yakunlangan", "Tanlov yakunlandi")
sel = [a for a in c["applications"] if a["status"] == "saralandi"]
J(xq.post(X + f"/applications/{sel[1]['id']}/withdraw", json={"note": "Shaxsiy sabab"}))
z = q("SELECT status FROM intl_applications WHERE call_id=? AND status='saralandi'", (cid,))
ok(len(z) == 2, "Voz kechgan o'rniga birinchi zaxira saralandi")
a0 = sel[0]["id"]
ok(xq.post(X + f"/applications/{a0}/return", json={"date": D(0), "credits_earned": 30}).status_code == 409, "Jo'namagan talaba qaytmaydi")
J(xq.post(X + f"/applications/{a0}/depart", json={"date": D(0)}))
J(xq.post(X + f"/applications/{a0}/return", json={"date": D(-5), "credits_earned": 30}), 400); ok(True, "Qaytish < jo'nash → 400")
J(xq.post(X + f"/applications/{a0}/return", json={"date": D(1), "credits_earned": 30, "transcript_note": "TEST transkript"}))
ok(q1("SELECT credit_status FROM intl_applications WHERE id=?", (a0,)) == "kutilmoqda", "Qaytdi → Akademik bo'lim navbatiga")

print("— Kredit tan olish (Akademik bo'lim) —")
cr = J(aka.get(X + "/credits?status=kutilmoqda"))
ok(any(x["id"] == a0 for x in cr["items"]) and cr["can_decide"], "Akademik bo'lim navbatida ko'rinadi")
ok(xq.post(X + f"/credits/{a0}", json={"decision": "tan_olindi"}).status_code == 403, "Xalqaro bo'lim kreditni tan olmaydi")
J(aka.post(X + f"/credits/{a0}", json={"decision": "qisman", "credits_recognized": 24, "note": ""}), 400); ok(True, "Qisman — izohsiz → 400")
J(aka.post(X + f"/credits/{a0}", json={"decision": "qisman", "credits_recognized": 40, "note": "Bitta fan farqi"}), 400); ok(True, "Qisman — ortiqcha kredit → 400")
r = J(aka.post(X + f"/credits/{a0}", json={"decision": "qisman", "credits_recognized": 24, "note": "Moliyaviy tahlil fani farq qiladi — farq fani"}))
ok(r["credits_recognized"] == 24, "Qisman tan olindi: 24 / 30")
ok(aka.post(X + f"/credits/{a0}", json={"decision": "tan_olindi"}).status_code == 409, "Qayta qaror → 409")

print("— Xorijiy talabalar —")
fl = J(xq.get(X + "/foreign"))["items"]
ok(any(f["alert"] == "over" for f in fl) and any(f["alert"] == "high" for f in fl), "Viza muddati o'tgan va 30 kun ichidagilar belgilangan")
ok(all(not f["passport"] or f["passport"].startswith("***") for f in fl), "Pasport raqami maskalangan")
fid = J(xq.post(X + "/foreign", json={"full_name": "TEST Xorijiy talaba", "country": "Hindiston", "passport": "AB1234567", "visa_expires": D(15), "reg_expires": D(15)}))["id"]
ok(q1("SELECT passport FROM intl_foreign WHERE id=?", (fid,)) == "***4567", "Saqlashda pasport maskalandi")
ok(ilm.post(X + f"/foreign/{fid}", json={"visa_expires": D(300)}).status_code == 403, "Ilmiy prorektor faqat ko'radi")
r = J(xq.post(X + f"/foreign/{fid}", json={"visa_expires": D(300), "reg_expires": D(300)}))
ok(r["alert"] is None, "Viza uzaytirildi → ogohlantirish yo'qoldi")

print("— Delegatsiyalar —")
did = J(xq.post(X + "/delegations", json={"org": "TEST delegatsiya", "country": "Yaponiya", "members": 3, "arrive": D(5), "depart": D(7), "purpose": "Hamkorlik muzokarasi"}))["id"]
ok(xq.post(X + f"/delegations/{did}/outcome", json={"status": "o'tkazildi", "outcome": "Kelishildi"}).status_code == 409, "Hali bo'lmagan tashrif «o'tkazildi» bo'lmaydi")
w("UPDATE intl_delegations SET arrive=?, depart=? WHERE id=?", (D(-3), D(-1), did))
J(xq.post(X + f"/delegations/{did}/outcome", json={"status": "o'tkazildi", "outcome": ""}), 400); ok(True, "Natijasiz → 400")
J(xq.post(X + f"/delegations/{did}/outcome", json={"status": "o'tkazildi", "outcome": "Memorandum loyihasi kelishildi"}))
ok(any(d["id"] == did and d["status"] == "o'tkazildi" for d in J(rek.get(X + "/delegations"))["items"]), "Rektor jurnalni ko'radi")

print("— Talaba kabineti —")
cid2 = J(xq.post(X + "/calls", json={**call, "title": "TEST kabinet tanlovi"}))["id"]
st = q1(f"""SELECT s.hemis_id FROM students s JOIN groups_ g ON g.id=s.group_id JOIN rating_cache rc ON rc.student_id=s.id AND rc.semester=?
    WHERE s.status='faol' AND g.course=3 AND rc.gpa>=4.3 AND s.id NOT IN (SELECT student_id FROM intl_applications) ORDER BY s.id DESC LIMIT 1""", (SEM,))
sid = q1("SELECT id FROM students WHERE hemis_id=?", (st,))
w("DELETE FROM student_auth WHERE student_id=?", (sid,)) if q("SELECT name FROM sqlite_master WHERE name='student_auth'") else None
t = httpx.Client(base_url=B, timeout=60)
lr = t.post("/api/talaba/login", json={"hemis_id": st, "password": os.environ.get("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026")})
if lr.status_code == 200:
    if lr.json().get("must_change"):
        J(t.post("/api/talaba/password", json={"current": os.environ.get("ISFT_CORE_STUDENT_DEMO_PASSWORD", "Talaba2026"), "new": "XalqaroTest#2026"}))
    tc = J(t.get("/api/talaba/xalqaro"))
    ok(any(c["id"] == cid2 for c in tc["calls"]), "Talaba ochiq tanlovni ko'radi")
    J(t.post(f"/api/talaba/xalqaro/{cid2}", json={"lang_score": 6.5, "motivation": "qisqa"}), 422); ok(True, "Motivatsiya juda qisqa → 422")
    r = J(t.post(f"/api/talaba/xalqaro/{cid2}", json={"lang_score": 6.5, "motivation": "Moliya sohasidagi xalqaro tajribani o'rganish va ingliz tilini mustahkamlash."}))
    ok(r["id"] and q1("SELECT channel FROM intl_applications WHERE id=?", (r["id"],)) == "portal", "Talaba kabinetidan ariza (kanal: portal)")
    ok(t.post(f"/api/talaba/xalqaro/{cid2}", json={"lang_score": 6.5, "motivation": "Moliya sohasidagi xalqaro tajribani o'rganish."}).status_code == 409, "Takroriy → 409")
    ok(any(m["title"] == "TEST kabinet tanlovi" for m in J(t.get("/api/talaba/xalqaro"))["mine"]), "«Mening arizalarim»da ko'rinadi")
    ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='talaba kabineti: xalqaro ariza' AND allowed=1") >= 1, "Talaba arizasi auditda")
else:
    print(f"  (talaba kabineti kirishi o'tkazib yuborildi: {lr.status_code} {lr.text[:120]})")
ok(httpx.post(B + f"/api/talaba/xalqaro/{cid2}", json={"lang_score": 6.5, "motivation": "x" * 30}).status_code == 401, "Kirishsiz talaba arizasi → 401")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
