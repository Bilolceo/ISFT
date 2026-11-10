import os
"""«Kiruvchi xatlar» — Devonxona (app/devon.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_devon.py
Qamrov: ruxsatlar (kirishsiz 401, begona lavozimlar 403, rahbar faqat o'ziga yo'naltirilgan xatlarni ko'radi), xat hayotiy sikli
(ro'yxatga olish → K-YYYY/NNNN raqam → skan fayl → rezolyutsiya (ijrochi bo'lim + muddat, Portal xati) → ijroda → muddati o'tgan →
chiquvchi xat bilan javob / izoh bilan yopish), validatsiya (noto'g'ri kirish → 4xx, 500 emas), «Mening vazifalarim» (/api/mywork:
rezolyutsiya kutayotgan xat rahbarda «imzo» sifatida, muddati o'tgan ijro Devonxonada), /api/bugun 500 bermasligi, audit.
Test bazani o'zgartiradi (test xatlari «TEST» belgisi bilan); demo holatini tiklash uchun — `python -m app.seed`.
"""
import datetime as dt, sqlite3, sys
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

def mw(cl, src="devon"):
    return [i for i in J(cl.get("/api/mywork"))["items"] if i["source"] == src]

X = "/api/devon"
dv, rek, pro, pym, kot, oq, bux, ith = (S(uid(r)) for r in ("devonxona", "rektor", "prorektor_oquv", "prorektor_yoshlar", "kotib",
                                                               "oqituvchi", "buxgalteriya", "it_head"))
PDF = b"%PDF-1.4\n% TEST kiruvchi xat skani\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"

print("— Ruxsatlar —")
for p in ("/meta", "/letters", "/outgoing"):
    ok(httpx.get(B + X + p).status_code == 401, f"Kirishsiz: GET {p} → 401")
ok(httpx.post(B + X + "/letters", json={"sender": "TEST", "subject": "TEST xat"}).status_code == 401, "Kirishsiz: xat ro'yxatga olish → 401")
for cl, nm in ((oq, "O'qituvchi"), (bux, "Buxgalteriya"), (ith, "AT boshlig'i")):
    ok(cl.get(X + "/meta").status_code == 403 and cl.get(X + "/letters").status_code == 403, f"{nm}: meta va ro'yxat → 403")
    ok(cl.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST begona"}).status_code == 403, f"{nm}: xat kiritish → 403")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='chancery' AND allowed=0 AND action='kiruvchi xatlar'") >= 3, "Rad etilgan so'rovlar auditda")
m = J(dv.get(X + "/meta"))
ok(m["can"]["register"] and not m["can"]["resolve"], "Devonxona: ro'yxatga oladi, rezolyutsiya bermaydi")
ok(set(m["resolvers"]) == {"rektor", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar"} and set(m["statuses"]) == {"royxatda", "ijroda", "javob", "yopildi"},
   "Meta: rezolyutsiya beruvchilar va holatlar")
units = {u["key"] for u in m["units"]}
ok(len(units) >= 5, f"Meta: ijrochi bo'limlar ro'yxati ({len(units)} ta)")
m = J(rek.get(X + "/meta")); ok(m["can"]["resolve"] and not m["can"]["register"], "Rektor: rezolyutsiya beradi, ro'yxatga olmaydi")
m = J(pro.get(X + "/meta")); ok(m["can"]["resolve"], "O'quv prorektori: rezolyutsiya beradi")
m = J(kot.get(X + "/meta")); ok(not m["can"]["register"] and not m["can"]["resolve"], "Rektorat kotibi: faqat ko'radi")
ok(kot.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST kotib"}).status_code == 403, "Kotib: xat kiritish → 403")
ok(rek.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST rektor"}).status_code == 403, "Rektor: xat kiritish → 403")
ok(dv.get(X + "/outgoing").status_code == 200 and rek.get(X + "/outgoing").status_code == 403, "Chiquvchi xatlar tanlovi — faqat Devonxona")

print("— Demo ma'lumot va ko'lam —")
all_dv = J(dv.get(X + "/letters"))["items"]
ok(len(all_dv) >= 6 and all(x["in_no"].startswith("K-") for x in all_dv), f"Devonxona: barcha xatlar ({len(all_dv)} ta), raqam K-YYYY/NNNN")
ok(all("file_stored" not in x for x in all_dv), "Ro'yxatda ichki fayl yo'li ko'rsatilmaydi")
ok(len(J(rek.get(X + "/letters"))["items"]) == len(all_dv) and len(J(kot.get(X + "/letters"))["items"]) == len(all_dv), "Rektor va kotib — hamma xatlar")
pl = J(pro.get(X + "/letters"))["items"]
ok(pl and all(x["resolver_role"] == "prorektor_oquv" for x in pl), f"O'quv prorektori — faqat o'ziga yo'naltirilganlar ({len(pl)} ta)")
ok(J(pro.get(X + "/meta"))["counts"] == {s: sum(1 for x in pl if x["status"] == s) for s in {x["status"] for x in pl}}, "Prorektor hisoblagichlari o'z ko'lamida")
r = J(dv.get(X + "/letters", params={"status": "royxatda"}))["items"]
ok(r and all(x["status"] == "royxatda" for x in r), "Holat bo'yicha filtr: royxatda")
ok(J(dv.get(X + "/letters", params={"status": "xyz"}))["items"] is not None, "Noma'lum holat filtri — 500 emas")

print("— Validatsiya (ro'yxatga olish) —")
ok(dv.post(X + "/letters", json={"sender": "T", "subject": "TEST xat"}).status_code == 422, "Jo'natuvchi juda qisqa → 422")
ok(dv.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "ab"}).status_code == 422, "Mavzu juda qisqa → 422")
ok(dv.post(X + "/letters", json={"subject": "TEST xat"}).status_code == 422, "Jo'natuvchisiz → 422")
ok(dv.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST xat", "summary": "x" * 2001}).status_code == 422, "Mazmun 2000 belgidan uzun → 422")
r = dv.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST xat", "resolver_role": "buxgalteriya"})
ok(r.status_code == 400, "Rezolyutsiya beruvchi — rahbar emas → 400")
ok(dv.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST xat", "in_date": "2026-13-45"}).status_code == 400, "Noto'g'ri kirish sanasi → 400")
ok(dv.post(X + "/letters", json={"sender": "TEST Vazirlik", "subject": "TEST xat", "sender_date": "kecha"}).status_code == 400, "Noto'g'ri jo'natuvchi sanasi → 400")
ok(dv.post(X + "/letters", content=b"not json", headers={"content-type": "application/json"}).status_code == 422, "Buzilgan JSON → 422")
n_before = q1("SELECT COUNT(*) FROM in_letters")
ok(q1("SELECT COUNT(*) FROM in_letters WHERE sender='TEST Vazirlik'") == 0, "Rad etilgan so'rovlar xat yaratmadi")

print("— Hayotiy sikl: ro'yxatga olish → fayl → rezolyutsiya —")
r = J(dv.post(X + "/letters", json={"sender": "  TEST Moliya vazirligi  ", "sender_no": "TEST-17/42", "sender_date": D(-3), "in_date": D(-1),
                                     "subject": "TEST Byudjet ijrosi bo'yicha so'rov", "summary": "TEST xat mazmuni", "resolver_role": "prorektor_oquv"}))
L1, no1 = r["id"], r["in_no"]
ok(no1 == f"K-{(TODAY - dt.timedelta(days=1)).year}/{q1('SELECT COUNT(*) FROM in_letters WHERE in_no LIKE ?', (no1[:7] + '%',)):04d}", f"Kiruvchi raqam avtomatik: {no1}")
row = q("SELECT status, sender, in_date, created_by FROM in_letters WHERE id=?", (L1,))[0]
ok(row == ("royxatda", "TEST Moliya vazirligi", D(-1), uid("devonxona")), "Holat «royxatda», jo'natuvchi qirqilgan, sana va muallif to'g'ri")
r2 = J(dv.post(X + "/letters", json={"sender": "TEST Hokimlik", "subject": "TEST Ma'lumot uchun xabarnoma"}))
L2 = r2["id"]
ok(int(r2["in_no"][-4:]) == int(no1[-4:]) + 1 if r2["in_no"][:7] == no1[:7] else True, f"Keyingi raqam ketma-ket: {r2['in_no']}")
ok(q1("SELECT resolver_role FROM in_letters WHERE id=?", (L2,)) == "rektor" and q1("SELECT in_date FROM in_letters WHERE id=?", (L2,)) == TODAY.isoformat(),
   "Standart: rektorga, bugungi sana bilan")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='kiruvchi xat ro''yxatga olindi' AND allowed=1 AND detail LIKE ?", (f"{no1}%",)) == 1, "Ro'yxatga olish auditda")
ok(any(x["id"] == L1 for x in J(dv.get(X + "/letters", params={"q": "TEST-17/42"}))["items"]), "Qidiruv: jo'natuvchi raqami bo'yicha")
ok(any(x["id"] == L1 for x in J(dv.get(X + "/letters", params={"q": no1}))["items"]), "Qidiruv: kiruvchi raqam bo'yicha")

ok(dv.post(X + f"/letters/{L1}/file", content=b"", headers={"content-type": "application/octet-stream"}).status_code == 400, "Bo'sh fayl → 400")
ok(dv.post(X + f"/letters/{L1}/file", content=b"MZ\x90\x00 exe", headers={"content-type": "application/octet-stream"}).status_code == 415, "EXE fayl → 415")
ok(pro.post(X + f"/letters/{L1}/file", content=PDF).status_code == 403, "Prorektor fayl yuklay olmaydi → 403")
ok(dv.post(X + "/letters/999999/file", content=PDF).status_code == 404, "Yo'q xatga fayl → 404")
ok(dv.get(X + f"/letters/{L1}/file").status_code == 404, "Fayl yuklanmagan → 404")
J(dv.post(X + f"/letters/{L1}/file", content=PDF, headers={"x-filename": "TEST%20xat%20sk%C3%A1n.pdf"}))
it = next(x for x in J(dv.get(X + "/letters"))["items"] if x["id"] == L1)
ok(it["has_file"] and it["file_name"] == "TEST xat skán.pdf", f"Skan yuklandi, nom dekodlandi: {it['file_name']}")
fr = dv.get(X + f"/letters/{L1}/file"); ok(fr.status_code == 200 and fr.content == PDF, "Devonxona faylni ochadi (mazmun bir xil)")
ok(pro.get(X + f"/letters/{L1}/file").status_code == 200, "Yo'naltirilgan prorektor faylni ochadi")
ok(pym.get(X + f"/letters/{L1}/file").status_code == 403, "Boshqa prorektor (yoshlar) faylni ocholmaydi → 403")
ok(kot.get(X + f"/letters/{L1}/file").status_code == 200, "Rektorat kotibi faylni ochadi")
ok(not any(x["id"] == L1 for x in J(pym.get(X + "/letters"))["items"]), "Boshqa prorektor ro'yxatida ko'rinmaydi")

print("— «Mening vazifalarim»: rezolyutsiya kutilmoqda —")
pi = [i for i in mw(pro) if i["id"] == f"devon-{L1}"]
ok(len(pi) == 1 and pi[0]["sign"] and pi[0]["kind"] == "kiruvchi" and pi[0]["link"].get("view") == "kiruvchi", "O'quv prorektori: xat «imzo» sifatida ko'rinadi")
ok(pi[0]["due"] == D(1) and no1 in pi[0]["sub"], "Rezolyutsiya muddati = kirish sanasi + 2 kun; raqam ko'rsatilgan")
ok(not any(i["id"] == f"devon-{L1}" for i in mw(rek)), "Rektorga yo'naltirilmagan xat rektor vazifalarida yo'q")
ok(any(i["id"] == f"devon-{L2}" and i["sign"] for i in mw(rek)), "Rektorga yo'naltirilgan xat rektor vazifalarida (imzo)")
ok(not any(i["id"] == f"devon-{L1}" for i in mw(pym)), "Boshqa prorektorda yo'q")
ok(not mw(oq), "O'qituvchida Kiruvchi xatlar manbai yo'q")

print("— Rezolyutsiya: validatsiya va ruxsat —")
RB = {"resolution": "TEST Ijro uchun. Javob loyihasi tayyorlansin.", "executor_unit": "buxgalteriya", "due": D(7)}
ok(dv.post(X + f"/letters/{L1}/resolution", json=RB).status_code == 403, "Devonxona rezolyutsiya bera olmaydi → 403")
ok(pym.post(X + f"/letters/{L1}/resolution", json=RB).status_code == 403, "Boshqa prorektor → 403")
ok(kot.post(X + f"/letters/{L1}/resolution", json=RB).status_code == 403, "Kotib → 403")
ok(pro.post(X + "/letters/999999/resolution", json=RB).status_code == 404, "Yo'q xat → 404")
ok(pro.post(X + f"/letters/{L1}/resolution", json={**RB, "due": D(-1)}).status_code == 400, "O'tgan muddat → 400")
ok(pro.post(X + f"/letters/{L1}/resolution", json={**RB, "due": "31.12.2026"}).status_code == 400, "Noto'g'ri sana formati → 400")
ok(pro.post(X + f"/letters/{L1}/resolution", json={**RB, "executor_unit": "yoq_bolim"}).status_code == 400, "Noma'lum bo'lim → 400")
ok(pro.post(X + f"/letters/{L1}/resolution", json={**RB, "resolution": "ok"}).status_code == 422, "Rezolyutsiya matni juda qisqa → 422")
ok(pro.post(X + f"/letters/{L1}/resolution", json={"resolution": "TEST matn"}).status_code == 422, "Bo'lim va muddatsiz → 422")
ok(q1("SELECT status FROM in_letters WHERE id=?", (L1,)) == "royxatda", "Xato so'rovlardan keyin holat o'zgarmadi")
ok(dv.post(X + f"/letters/{L1}/close", json={"note": "TEST erta yopish"}).status_code == 409, "Rezolyutsiyasiz yopish → 409")

r = J(pro.post(X + f"/letters/{L1}/resolution", json=RB))
row = q("SELECT status, executor_unit, due, resolved_by, thread_id, resolution FROM in_letters WHERE id=?", (L1,))[0]
ok(row[:4] == ("ijroda", "buxgalteriya", D(7), uid("prorektor_oquv")) and row[5] == RB["resolution"], "Rezolyutsiya: ijroda, ijrochi, muddat, kim bergan")
ok(r["thread_id"] and row[4] == r["thread_id"], f"Ijrochiga Portal xati yaratildi (#{r['thread_id']})")
th = q("SELECT kind, priority, subject FROM portal_threads WHERE id=?", (r["thread_id"],))
ok(th and th[0][0] == "topshiriq" and th[0][1] == "muhim" and no1 in th[0][2], "Portal xati: topshiriq, muhim, mavzuda kiruvchi raqam")
ok(pro.post(X + f"/letters/{L1}/resolution", json=RB).status_code == 409, "Takroriy rezolyutsiya → 409")
it = next(x for x in J(dv.get(X + "/letters"))["items"] if x["id"] == L1)
ok(it["status_label"] == "Ijroda" and it["executor_name"] and it["thread"] and it["thread"]["id"] == r["thread_id"] and not it["overdue"], "Ro'yxatda: holat, ijrochi nomi, Portal havolasi")
ok(not any(i["id"] == f"devon-{L1}" for i in mw(pro)), "Rezolyutsiyadan keyin prorektor vazifalaridan chiqdi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='kiruvchi xatga rezolyutsiya' AND detail LIKE ?", (f"{no1}%",)) == 1, "Rezolyutsiya auditda")

# rektor — boshqa rahbarga yo'naltirilgan xatga ham rezolyutsiya bera oladi
r3 = J(dv.post(X + "/letters", json={"sender": "TEST Agentlik", "subject": "TEST Rektor aralashuvi", "resolver_role": "prorektor_yoshlar"}))
J(rek.post(X + f"/letters/{r3['id']}/resolution", json={**RB, "executor_unit": "manaviyat" if "manaviyat" in units else "buxgalteriya"}))
ok(q1("SELECT status FROM in_letters WHERE id=?", (r3["id"],)) == "ijroda", "Rektor boshqa prorektorga yo'naltirilgan xatga rezolyutsiya beradi")

print("— Ijro muddati o'tgan (Devonxona nazorati) —")
ok(not any(i["id"] == f"devon-{L1}" for i in mw(dv)), "Muddati o'tmagan ijro Devonxona vazifalarida yo'q")
w("UPDATE in_letters SET due=? WHERE id=?", (D(-2), L1))
it = next(x for x in J(dv.get(X + "/letters"))["items"] if x["id"] == L1)
ok(it["overdue"], "Muddati o'tgan → overdue belgisi")
ok(any(x["id"] == L1 for x in J(dv.get(X + "/letters", params={"status": "muddati"}))["items"]), "«Muddati o'tgan» filtrida")
di = [i for i in mw(dv) if i["id"] == f"devon-{L1}"]
ok(len(di) == 1 and di[0]["overdue"] and di[0]["bucket"] == "overdue" and not di[0]["sign"], "Devonxona vazifalarida: muddati o'tgan (imzo emas)")
ok(di[0]["priority"] == "high", "Muddati o'tgan — yuqori ustuvorlik")

print("— Yopish: chiquvchi xat bilan javob / izoh bilan —")
ok(pro.post(X + f"/letters/{L1}/close", json={"note": "TEST"}).status_code == 403, "Prorektor yopa olmaydi → 403")
ok(dv.post(X + f"/letters/{L1}/close", json={"out_id": 999999}).status_code == 400, "Yo'q chiquvchi xat → 400")
ok(dv.post(X + f"/letters/{L1}/close", json={"note": "ok"}).status_code == 400, "Javobsiz, izoh juda qisqa → 400")
ok(dv.post(X + f"/letters/{L1}/close", json={"note": "x" * 501}).status_code == 422, "Izoh 500 belgidan uzun → 422")
ok(dv.post(X + "/letters/999999/close", json={"note": "TEST izoh"}).status_code == 404, "Yo'q xatni yopish → 404")
o = J(dv.post("/api/orders/outgoing", json={"addressee": "TEST Moliya vazirligi", "subject": f"TEST {no1} ga javob", "thread_id": r["thread_id"]}))
ok(any(x["id"] == o["id"] for x in J(dv.get(X + "/outgoing", params={"q": "TEST Moliya"}))["items"]), "Chiquvchi xat tanlovida qidiriladi")
J(dv.post(X + f"/letters/{L1}/close", json={"out_id": o["id"], "note": "TEST javob yuborildi"}))
row = q("SELECT status, reply_out_id, closed_at, close_note FROM in_letters WHERE id=?", (L1,))[0]
ok(row[0] == "javob" and row[1] == o["id"] and row[2] and row[3] == "TEST javob yuborildi", "Javob berildi: chiquvchi xat bog'landi")
it = next(x for x in J(dv.get(X + "/letters"))["items"] if x["id"] == L1)
ok(it["reply"] and it["reply"]["out_no"] == o["out_no"] and not it["overdue"], f"Ro'yxatda javob raqami: {o['out_no']}; endi overdue emas")
ok(not any(i["id"] == f"devon-{L1}" for i in mw(dv)), "Javobdan keyin Devonxona vazifalaridan chiqdi")
J(dv.post(X + f"/letters/{L1}/close", json={"note": "TEST arxivga"}))
ok(q1("SELECT status FROM in_letters WHERE id=?", (L1,)) == "yopildi", "Javob berilgan xat → yopildi")
ok(dv.post(X + f"/letters/{L1}/close", json={"note": "TEST yana"}).status_code == 409, "Yopilganni qayta yopish → 409")

# L2: rektor rezolyutsiyasi → izoh bilan (javobsiz) yopish
J(rek.post(X + f"/letters/{L2}/resolution", json={**RB, "executor_unit": "devonxona"}))
ok(not any(i["id"] == f"devon-{L2}" for i in mw(rek)), "Rektor rezolyutsiyasidan keyin vazifadan chiqdi")
J(dv.post(X + f"/letters/{L2}/close", json={"note": "  TEST ma'lumot uchun  "}))
row = q("SELECT status, reply_out_id, close_note FROM in_letters WHERE id=?", (L2,))[0]
ok(row == ("yopildi", None, "TEST ma'lumot uchun"), "Javobsiz yopish: izoh bilan, chiquvchi xat yo'q")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='kiruvchi xat yopildi' AND detail LIKE 'K-%'") >= 3, "Yopish auditda")
ok(q1("SELECT COUNT(*) FROM in_letters") == n_before + 3, "Jami 3 ta test xati yaratildi")

print("— Bosh sahifa (/api/bugun) va «Mening vazifalarim» —")
for cl, nm in ((dv, "Devonxona"), (rek, "Rektor"), (pro, "O'quv prorektori"), (pym, "Yoshlar prorektori"), (kot, "Kotib")):
    b = cl.get("/api/bugun"); m2 = cl.get("/api/mywork")
    ok(b.status_code == 200 and m2.status_code == 200 and "devon" not in m2.json()["partial"], f"{nm}: /api/bugun va /api/mywork — 200, devon manbai xatosiz")
r4 = J(dv.post(X + "/letters", json={"sender": "TEST Inspeksiya", "subject": "TEST Imzo papkasi", "resolver_role": "prorektor_oquv"}))
cnt = J(pro.get("/api/bugun"))["counts"]
ok(cnt["by_source"].get("devon", 0) >= 1 and cnt["sign"] >= 1, f"Prorektor bosh sahifasi: devon={cnt['by_source'].get('devon')}, imzo={cnt['sign']}")
ok(httpx.get(B + "/api/bugun").status_code == 401 and httpx.get(B + "/api/mywork").status_code == 401, "Kirishsiz /api/bugun, /api/mywork → 401")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
