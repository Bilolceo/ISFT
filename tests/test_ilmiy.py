import os
"""«Ilmiy faoliyat» (app/ilmiy.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_ilmiy.py
Test bazani o'zgartiradi (nashr arizalari, grant loyihasi, dissertatsiya bosqichlari) — demo holatini tiklash uchun `python -m app.seed`.
Qamrov: lavozimlar va ko'lam (ilmiy bo'lim, prorektor, magistratura, kafedra, o'qituvchi, rektor, kengash; registrator → 403),
nashr: ariza → kafedra → Ilmiy bo'lim → reyestr, qaytarish va tuzatish, DOI / takror tekshiruvi; grant: loyiha → imzo → yuborish → yutildi →
hisobotlar → yakunlash; dissertatsiya: rahbar talablari, bosqichlar ketma-ketligi, bayonnoma, himoya bahosi va theses bilan bog'lanish.
"""
import sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=180)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

T0 = CLK.now().isoformat(timespec="seconds")
TODAY = CLK.today()
TAG = str(int(time.time()))[-6:]
ilm, pro, mag, rek, ken, reg = S(uid("ilmiy_bolim")), S(uid("prorektor_ilmiy")), S(uid("magistratura")), S(uid("rektor")), S(uid("kengash")), S(uid("talabalar"))
KAF_U = q1("SELECT u.id FROM users u WHERE u.role='kafedra' AND EXISTS(SELECT 1 FROM users o WHERE o.role='oqituvchi' AND o.department_id=u.department_id) ORDER BY u.id LIMIT 1")
OQ_U = q1("SELECT id FROM users WHERE role='oqituvchi' AND teacher_id IS NOT NULL ORDER BY id LIMIT 1")
kaf, oq = S(KAF_U), S(OQ_U)
DEPT = q1("SELECT department_id FROM users WHERE id=?", (KAF_U,))
TID = q1("SELECT teacher_id FROM users WHERE id=?", (OQ_U,))
OTHER_KAF = S(q1("SELECT id FROM users WHERE role='kafedra' AND department_id!=? ORDER BY id LIMIT 1", (DEPT,)))

print("— Ruxsatlar va ko'lam —")
ok(httpx.get(B + "/api/ilmiy/meta").status_code == 401, "Kirishsiz: 401")
for path in ("/api/ilmiy/meta", "/api/ilmiy/pubs", "/api/ilmiy/grants", "/api/ilmiy/diss", "/api/ilmiy/overview"):
    ok(reg.get(path).status_code == 403, f"Registrator ofisi: {path} → 403")
want = {"ilmiy": ["umumiy", "nashrlar", "grantlar", "dissertatsiya"], "prorektor": ["umumiy", "nashrlar", "grantlar", "dissertatsiya"],
        "mag": ["umumiy", "dissertatsiya"], "kafedra": ["umumiy", "nashrlar", "grantlar", "dissertatsiya"], "oqituvchi": ["nashrlar", "grantlar", "dissertatsiya"],
        "lead": ["umumiy", "nashrlar", "grantlar"], "kengash": ["umumiy"]}
for c in (ilm, pro, mag, kaf, oq, rek, ken):
    m = J(c.get("/api/ilmiy/meta"))
    ok(m["tabs"] == want[m["mode"]], f"{m['mode']}: bo'limlar {m['tabs']}")
ok(mag.get("/api/ilmiy/pubs").status_code == 403 and mag.get("/api/ilmiy/grants").status_code == 403, "Magistratura: nashrlar va grantlar yopiq (403)")
ok(rek.get("/api/ilmiy/diss").status_code == 403 and ken.get("/api/ilmiy/pubs").status_code == 403, "Rektor: dissertatsiya ro'yxati, kengash: nashrlar — yopiq (jamlangan)")
o = J(rek.get("/api/ilmiy/overview"))
ok("depts" in o and "diss" in o and o["diss"]["supervisors"] == [] and all("full_name" not in str(c) for c in o["diss"]["by_course"]), "Rektor: umumiy — faqat jamlangan sonlar")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource IN ('science','masters') AND allowed=0 AND ts>=?", (T0,)) >= 7, "Rad etilgan so'rovlar audit jurnalida")
kp = J(kaf.get("/api/ilmiy/pubs"))["rows"]
ok(kp and all(r["dept_id"] == DEPT for r in kp), f"Kafedra: arizalar — faqat o'z kafedrasi ({len(kp)} ta)")
op = J(oq.get("/api/ilmiy/pubs"))["rows"]
ok(all(r["teacher_id"] == TID for r in op), "O'qituvchi: faqat o'z arizalari")
od = J(oq.get("/api/ilmiy/diss"))
ok(all(r["supervisor_id"] == TID for r in od["rows"]), f"O'qituvchi: faqat rahbarligidagi magistrantlar ({od['total']} ta)")
kd = J(kaf.get("/api/ilmiy/diss"))
ok(kd["total"] > 0 and all(r["sup_dept"] == DEPT or r["department_id"] == DEPT for r in kd["rows"]), f"Kafedra: dissertatsiyalar — o'z kafedrasi ({kd['total']} ta)")

print("— Nashrlar —")
base = {"title": f"Test maqola: raqamli iqtisodiyotda innovatsiyalar {TAG}", "kind": "Scopus", "journal": "Sustainability", "year": TODAY.year}
ok(oq.post("/api/ilmiy/pubs", json=base).status_code == 400, "Scopus — DOI/havolasiz qabul qilinmaydi (400)")
ok(oq.post("/api/ilmiy/pubs", json={**base, "doi": "abc"}).status_code == 400, "Noto'g'ri DOI formati (400)")
ok(oq.post("/api/ilmiy/pubs", json={**base, "doi": "10.1234/x", "year": TODAY.year - 6}).status_code == 400, "Juda eski yil (400)")
doi = f"10.5555/isft.test.{TAG}"
p = J(oq.post("/api/ilmiy/pubs", json={**base, "doi": doi, "quartile": "Q2"}))
ok(p["status"] == "kafedra" and p["teacher_id"] == TID, "O'qituvchi arizasi → kafedra tekshiruviga")
ok(oq.post("/api/ilmiy/pubs", json={**base, "title": base["title"] + " II", "doi": doi}).status_code == 409, "Takror DOI (409)")
ok(oq.post("/api/ilmiy/pubs", json={**base, "doi": doi + "9"}).status_code == 409, "Takror sarlavha — bir muallifda (409)")
ok(oq.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "tasdiq"}).status_code == 403, "O'qituvchi o'z arizasini tasdiqlay olmaydi (403)")
ok(OTHER_KAF.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "tasdiq"}).status_code == 403, "Boshqa kafedra mudiri tasdiqlay olmaydi (403)")
ok(ilm.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "tasdiq"}).status_code == 403, "Ilmiy bo'lim kafedra bosqichidan sakray olmaydi (403)")
ok(kaf.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "qaytarish", "note": ""}).status_code == 400, "Qaytarish sababsiz bo'lmaydi (400)")
r = J(kaf.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "qaytarish", "note": "Jurnal sahifalari ko'rsatilmagan"}))
ok(r["status"] == "qaytarildi", "Kafedra qaytardi")
m = J(oq.get("/api/ilmiy/meta"))
ok(any("qaytarildi" in a["text"] for a in m["alerts"]), "O'qituvchiga ogohlantirish: arizangiz qaytarildi")
r = J(oq.post(f"/api/ilmiy/pubs/{p['id']}/edit", json={**base, "doi": doi, "quartile": "Q2", "journal": "Sustainability, 18(4), 112–130"}))
ok(r["status"] == "kafedra", "Tuzatildi → yana kafedraga")
r = J(kaf.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "tasdiq"}))
ok(r["status"] == "ilmiy", "Kafedra tasdiqladi → Ilmiy bo'limga")
ok(any(x["id"] == p["id"] for x in J(ilm.get("/api/ilmiy/pubs?status=navbat"))["rows"]), "Ilmiy bo'lim navbatida")
ok(ilm.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "tasdiq"}).status_code == 400, "Scopus: indeksatsiya tekshiruvi belgilanmasa — 400")
n0 = q1("SELECT COUNT(*) FROM publications")
r = J(ilm.post(f"/api/ilmiy/pubs/{p['id']}/review", json={"decision": "tasdiq", "indexed": True, "quartile": "Q2"}))
ok(r["status"] == "tasdiqlangan" and r["pub_id"], "Ilmiy bo'lim tasdiqladi")
ok(q1("SELECT COUNT(*) FROM publications") == n0 + 1 and q1("SELECT doi FROM publications WHERE id=?", (r["pub_id"],)) == doi, "Reyestrga (publications) yozildi — DOI bilan")
ok(any(x["id"] == r["pub_id"] for x in J(oq.get(f"/api/ilmiy/registry?year={TODAY.year}&q={TAG}"))["rows"]), "Muallif reyestrda ko'radi")
ok(len(J(oq.get(f"/api/ilmiy/pubs/{p['id']}"))["log"]) >= 5, "Ariza tarixi saqlanadi")
p2 = J(kaf.post("/api/ilmiy/pubs", json={"teacher_id": TID, "title": f"Kafedra kiritgan OAK maqolasi {TAG}", "kind": "OAK jurnali", "journal": "Iqtisodiyot va innovatsion texnologiyalar", "year": TODAY.year}))
ok(p2["status"] == "ilmiy", "Kafedra kiritgan ariza — to'g'ridan-to'g'ri Ilmiy bo'limga")
other_t = q1("SELECT id FROM teachers WHERE department_id!=? LIMIT 1", (DEPT,))
ok(kaf.post("/api/ilmiy/pubs", json={"teacher_id": other_t, "title": f"Boshqa kafedra muallifi {TAG}", "kind": "OAK jurnali", "journal": "X", "year": TODAY.year}).status_code == 403,
   "Kafedra boshqa kafedra o'qituvchisi nomidan kirita olmaydi (403)")
p3 = J(oq.post("/api/ilmiy/pubs", json={"title": f"Qaytarib olinadigan konferensiya tezisi {TAG}", "kind": "Konferensiya tezisi", "year": TODAY.year}))
ok(J(oq.post(f"/api/ilmiy/pubs/{p3['id']}/withdraw"))["status"] == "qaytarib olindi", "Muallif arizani qaytarib oldi")
ok(J(ilm.post("/api/ilmiy/plans", json={"dept_id": DEPT, "year": TODAY.year, "scopus": 3, "oak": 12}))["ok"], "Ilmiy bo'lim kafedra rejasini belgiladi")
ok(kaf.post("/api/ilmiy/plans", json={"dept_id": DEPT, "year": TODAY.year, "scopus": 1, "oak": 1}).status_code == 403, "Kafedra o'z rejasini o'zgartira olmaydi (403)")
dd = next(d for d in J(kaf.get("/api/ilmiy/overview"))["depts"] if d["dept_id"] == DEPT)
ok(dd["plan_scopus"] == 3 and dd["plan_oak"] == 12 and dd["plan_scopus_pct"] is not None, f"Reja bajarilishi: Scopus/WoS {dd['indexed']}/3 · OAK {dd['oak']}/12")

print("— Grantlar —")

import datetime as dt
dl = (TODAY + dt.timedelta(days=30)).isoformat()
gb = {"title": f"Test loyihasi: raqamli ta'lim platformasi {TAG}", "funder": "Vazirlik", "amount": 300_000_000, "months": 12, "deadline": dl}
ok(oq.post("/api/ilmiy/grants", json={**gb, "deadline": (TODAY - dt.timedelta(days=1)).isoformat()}).status_code == 400, "Muddati o'tgan tanlovga loyiha — 400")
g = J(oq.post("/api/ilmiy/grants", json=gb))
ok(g["status"] == "loyiha" and g["leader_id"] == TID and g["acts"] == ["imzoga"], "O'qituvchi loyiha yaratdi (rahbar — o'zi)")
ok(pro.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "imzo"}).status_code == 403, "Loyiha holatida prorektor imzolay olmaydi (403)")
g = J(oq.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "imzoga"}))
ok(g["status"] == "imzoda", "Prorektor imzosiga yuborildi")
ok(any("imzo" in a["text"] for a in J(pro.get("/api/ilmiy/meta"))["alerts"]), "Prorektorga ogohlantirish: imzo kutilmoqda")
ok(ilm.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "imzo"}).status_code == 403, "Ilmiy bo'lim imzolay olmaydi (403)")
g = J(pro.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "imzo"}))
ok(g["status"] == "imzolandi", "Prorektor imzoladi")
g = J(ilm.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "yuborish"}))
ok(g["status"] == "ariza berilgan", "Ilmiy bo'lim moliyalashtiruvchiga yubordi")
ok(ilm.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "yutildi", "amount_won": 0}).status_code == 400, "Yutildi — summasiz 400")
g = J(ilm.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "yutildi", "amount_won": 250_000_000, "start": TODAY.isoformat(), "months": 12}))
ok(g["status"] == "bajarilmoqda" and g["amount_won"] == 250_000_000, "Yutildi → bajarilmoqda")
ok([r["kind"] for r in g["reports"]] == ["oraliq", "yakuniy"], "12 oylik loyiha: 1 oraliq + yakuniy hisobot jadvali")
ok(ilm.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "yakunlash"}).status_code == 400, "Yakuniy hisobot qabul qilinmaguncha yakunlab bo'lmaydi (400)")
r1, r2 = g["reports"][0]["id"], g["reports"][1]["id"]
ok(oq.post(f"/api/ilmiy/grants/{g['id']}/reports/{r1}", json={"action": "topshirish", "note": "qisqa"}).status_code == 400, "Hisobot mazmunsiz — 400")
ok(oq.post(f"/api/ilmiy/grants/{g['id']}/reports/{r1}", json={"action": "qabul"}).status_code == 403, "Rahbar o'z hisobotini qabul qila olmaydi (403)")
J(oq.post(f"/api/ilmiy/grants/{g['id']}/reports/{r1}", json={"action": "topshirish", "note": "Platforma prototipi ishlab chiqildi, 120 talaba sinovda qatnashdi."}))
g = J(ilm.post(f"/api/ilmiy/grants/{g['id']}/reports/{r1}", json={"action": "qaytarish", "note": "Xarajatlar smetasi ilova qilinmagan"}))
ok(g["reports"][0]["status"] == "qaytarildi", "Ilmiy bo'lim oraliq hisobotni qaytardi")
J(oq.post(f"/api/ilmiy/grants/{g['id']}/reports/{r1}", json={"action": "topshirish", "note": "Smeta ilova qilindi; prototip va sinov natijalari."}))
J(ilm.post(f"/api/ilmiy/grants/{g['id']}/reports/{r1}", json={"action": "qabul"}))
J(oq.post(f"/api/ilmiy/grants/{g['id']}/reports/{r2}", json={"action": "topshirish", "note": "Yakuniy natijalar: platforma joriy etildi, 2 ta maqola chop etildi."}))
J(ilm.post(f"/api/ilmiy/grants/{g['id']}/reports/{r2}", json={"action": "qabul"}))
g = J(ilm.post(f"/api/ilmiy/grants/{g['id']}/act", json={"action": "yakunlash"}))
ok(g["status"] == "yakunlangan", "Yakuniy hisobot qabul qilindi → loyiha yakunlandi")
ok(len(J(ilm.get(f"/api/ilmiy/grants/{g['id']}"))["log"]) >= 8, "Grant tarixi saqlanadi")
ok(OTHER_KAF.get(f"/api/ilmiy/grants/{g['id']}").status_code == 403, "Boshqa kafedra loyihani ko'rmaydi (403)")

print("— Dissertatsiyalar —")
m1 = q1("""SELECT m.id FROM masters m JOIN students s ON s.id=m.student_id JOIN groups_ g ON g.id=s.group_id JOIN diss_stages x ON x.master_id=m.id AND x.stage='mavzu'
           WHERE g.course=1 AND s.status='faol' AND x.status!='o''tdi' ORDER BY m.id LIMIT 1""")
ok(m1 is not None, f"1-kurs magistrant, mavzu tasdiqlanmagan: #{m1}")
ok(mag.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "bob1", "action": "otdi"}).status_code == 403, "Ketma-ketlik: mavzu tasdiqlanmasdan 1-bob o'tmaydi (403)")
nodeg = q1("SELECT id FROM teachers WHERE COALESCE(degree,'') NOT IN ('PhD','DSc') AND department_id=? LIMIT 1", (DEPT,))
ok(mag.post(f"/api/ilmiy/diss/{m1}/assign", json={"topic": "Raqamli to'lov tizimlarining bank likvidligiga ta'siri", "supervisor_id": nodeg}).status_code == 400,
   "Ilmiy darajasiz rahbar — 400")
full = q1("""SELECT m.supervisor_id FROM masters m JOIN students s ON s.id=m.student_id WHERE s.status IN ('faol','akademik ta''til') AND m.supervisor_id IS NOT NULL
             GROUP BY 1 HAVING COUNT(*)>=8 LIMIT 1""")
if full and q1("SELECT degree FROM teachers WHERE id=?", (full,)) in ("PhD", "DSc"):
    ok(mag.post(f"/api/ilmiy/diss/{m1}/assign", json={"topic": "Raqamli to'lov tizimlarining bank likvidligiga ta'siri", "supervisor_id": full}).status_code == 400,
       "Rahbar chegarasi (8 ta) — 400")
sup = q1("""SELECT t.id FROM teachers t WHERE t.department_id=? AND t.degree IN ('PhD','DSc') AND
            (SELECT COUNT(*) FROM masters m WHERE m.supervisor_id=t.id) < 6 ORDER BY t.id LIMIT 1""", (DEPT,))
d = J(mag.post(f"/api/ilmiy/diss/{m1}/assign", json={"topic": f"Raqamli to'lov tizimlarining bank likvidligiga ta'siri {TAG}", "supervisor_id": sup}))
ok(d["supervisor_id"] == sup and TAG in d["topic"], "Magistratura mavzu va ilmiy rahbarni belgiladi")
ok(mag.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "mavzu", "action": "otdi"}).status_code == 400, "Mavzu tasdig'i — bayonnomasiz 400")
ok(kaf.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "mavzu", "action": "otdi", "protocol": "№3"}).status_code == 403, "Mavzuni kafedra emas, Magistratura tasdiqlaydi (403)")
d = J(mag.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "mavzu", "action": "otdi", "protocol": f"№3, {TODAY:%d.%m.%Y}"}))
ok(d["stages"][0]["status"] == "o'tdi" and q1("SELECT stage FROM masters WHERE id=?", (m1,)) == "Mavzu tasdiqlangan", "Mavzu tasdiqlandi → masters.stage yangilandi")
ok(mag.post(f"/api/ilmiy/diss/{m1}/assign", json={"topic": f"Yangi mavzu varianti uchun matn {TAG}", "supervisor_id": sup}).status_code == 400,
   "Tasdiqlangan mavzuni sababsiz o'zgartirib bo'lmaydi (400)")
J(kaf.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "bob1", "action": "topshirildi", "note": "1-bob qoralamasi"}))
d = J(kaf.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "bob1", "action": "qayta", "note": "Adabiyotlar sharhi yetarli emas"}))
s1 = d["stages"][1]
ok(s1["status"] == "qayta" and s1["due"] >= (TODAY + dt.timedelta(days=30)).isoformat(), "Kafedra: 1-bob qayta topshirishga (yangi muddat ≥ 30 kun)")
ok(mag.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "bob1", "action": "muddat", "due": (TODAY - dt.timedelta(days=3)).isoformat(), "note": "sabab"}).status_code == 400,
   "Muddat — o'tgan sanaga surilmaydi (400)")
d = J(mag.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "bob1", "action": "muddat", "due": (TODAY + dt.timedelta(days=60)).isoformat(), "note": "Kasallik ta'tili"}))
ok(d["stages"][1]["due"] == (TODAY + dt.timedelta(days=60)).isoformat(), "Magistratura muddatni uzaytirdi (sabab bilan)")
ok(kaf.post(f"/api/ilmiy/diss/{m1}/stage", json={"stage": "bob1", "action": "muddat", "due": (TODAY + dt.timedelta(days=90)).isoformat(), "note": "x y z w"}).status_code == 403,
   "Muddatni faqat Magistratura o'zgartiradi (403)")
# himoya: dastlabki himoyadan o'tgan 2-kurs magistrant
m2 = q1("""SELECT m.id FROM masters m JOIN students s ON s.id=m.student_id JOIN diss_stages x ON x.master_id=m.id AND x.stage='dastlabki' AND x.status='o''tdi'
           JOIN diss_stages h ON h.master_id=m.id AND h.stage='himoya' AND h.status!='o''tdi' WHERE s.status='faol' ORDER BY m.id LIMIT 1""")
ok(m2 is not None, f"Dastlabki himoyadan o'tgan magistrant: #{m2}")
ok(kaf.post(f"/api/ilmiy/diss/{m2}/stage", json={"stage": "himoya", "action": "otdi", "protocol": "DAK №1", "score": 80}).status_code == 403, "Himoyani kafedra qayd eta olmaydi (403)")
ok(mag.post(f"/api/ilmiy/diss/{m2}/stage", json={"stage": "himoya", "action": "otdi", "protocol": "DAK №1", "score": 50}).status_code == 400, "Himoya: 55 dan past — «o'tdi» emas (400)")
d = J(mag.post(f"/api/ilmiy/diss/{m2}/stage", json={"stage": "himoya", "action": "otdi", "protocol": "DAK №1", "score": 86}))
ok(d["stages"][-1]["status"] == "o'tdi" and d["stages"][-1]["score"] == 86, "Himoya qilindi (86 ball)")
st = q1("SELECT student_id FROM masters WHERE id=?", (m2,))
th = q("SELECT status, score FROM theses WHERE student_id=?", (st,))
ok(not th or (th[0][0] == "himoya qilindi" and th[0][1] == 86), "Bitiruv ishi (theses) — «himoya qilindi», ball bilan (Talaba harakati → Bitiruv)")
ok(q1("SELECT stage FROM masters WHERE id=?", (m2,)) == "Himoya qilindi", "masters.stage — «Himoya qilindi»")
L = J(mag.get("/api/ilmiy/diss?flag=overdue"))
ok(L["counts"]["overdue"] == L["total"] and all(r["overdue"] > 0 for r in L["rows"]), f"Muddati o'tganlar filtri: {L['total']} ta")
ok(all(a.get("tab") for a in J(mag.get("/api/ilmiy/meta"))["alerts"]), "Magistraturaga ogohlantirishlar (bo'limga havola bilan)")
out_m = q1("""SELECT m.id FROM masters m JOIN students s ON s.id=m.student_id JOIN groups_ g ON g.id=s.group_id LEFT JOIN teachers t ON t.id=m.supervisor_id
              WHERE COALESCE(t.department_id,-1)!=? AND g.department_id!=? LIMIT 1""", (DEPT, DEPT))
if out_m: ok(kaf.get(f"/api/ilmiy/diss/{out_m}").status_code == 403, "Kafedra: boshqa kafedra magistranti yopiq (403)")
ok(oq.get(f"/api/ilmiy/diss/{m2}").status_code == 403 or q1("SELECT supervisor_id FROM masters WHERE id=?", (m2,)) == TID, "O'qituvchi: boshqa rahbar magistranti yopiq (403)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource IN ('science','masters') AND allowed=1 AND ts>=?", (T0,)) > 40, "Barcha amallar audit jurnalida (science / masters)")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv")
