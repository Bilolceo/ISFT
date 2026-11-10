import os
"""«Qabul» (app/qabul.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_qabul.py
Qamrov: ruxsatlar (kirishsiz 401; Qabul komissiyasi — to'liq; rektor, o'quv prorektori, marketing — faqat ko'rish; boshqalar — 403),
abituriyent oqimi (ariza → hujjat → imtihon/suhbat → shartnoma → qabul buyrug'i loyihasi .docx | rad etildi), kiritish xatolari (4xx, 500 emas),
voronka sonlari (by_stage, by_direction, jamlangan qabul tahlili) — bazaga to'g'ridan-to'g'ri so'rov bilan solishtiriladi,
«Mening vazifalarim» (/api/mywork, pending._simple → qabul.pending) va «Bugun» (/api/bugun).
Test bazani o'zgartiradi (test yozuvlari «TEST» belgisi bilan); demo holatini tiklash uchun — `python -m app.seed`.
"""
import datetime as dt, io, sqlite3, sys
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

def docx_tables(content: bytes):
    from docx import Document
    d = Document(io.BytesIO(content))
    return d, [[[c.text for c in row.cells] for row in t.rows] for t in d.tables]

X = "/api/qabul"
qb, rek, oquv, mkt, ken, bux, oqt, stg = (S(uid(r)) for r in ("qabul", "rektor", "prorektor_oquv", "marketing", "kengash", "buxgalteriya", "oqituvchi", "strategik"))

print("— Ruxsatlar —")
for p in ("/meta", "/applicants"):
    ok(httpx.get(B + X + p).status_code == 401, f"Kirishsiz: GET {p} → 401")
ok(httpx.post(B + X + "/applicants", json={"full_name": "TEST Kirishsiz", "direction": "x"}).status_code == 401, "Kirishsiz: yangi ariza → 401")
for cl, nm in ((ken, "Kuzatuv kengashi"), (bux, "Buxgalteriya"), (oqt, "O'qituvchi"), (stg, "Strategik bo'lim")):
    ok(cl.get(X + "/meta").status_code == 403 and cl.get(X + "/applicants").status_code == 403, f"{nm}: meta va ro'yxat → 403")
m = J(qb.get(X + "/meta"))
ok(m["can_edit"] is True and m["pass_score"] == 56 and m["next"] == {"ariza": "hujjat", "hujjat": "imtihon", "imtihon": "shartnoma"}, "Qabul komissiyasi: tahrir huquqi, o'tish bali 56, bosqichlar")
for cl, nm in ((rek, "Rektor"), (oquv, "O'quv prorektori"), (mkt, "Marketing")):
    mm = J(cl.get(X + "/meta"))
    ok(mm["can_edit"] is False and cl.get(X + "/applicants").status_code == 200, f"{nm}: faqat ko'rish (can_edit=false, ro'yxat 200)")
dirs = m["directions"]
ok(len(dirs) >= 3, f"Yo'nalishlar ro'yxati: {len(dirs)} ta")
DIR0 = dirs[0]
body = {"full_name": "TEST Abituriyent Birinchi", "phone": "+998 90 000 00 01", "direction": DIR0, "study_form": "kunduzgi", "payment_type": "kontrakt"}
ok(rek.post(X + "/applicants", json=body).status_code == 403, "Rektor ariza kirita olmaydi (403)")
ok(mkt.post(X + "/applicants", json=body).status_code == 403, "Marketing ariza kirita olmaydi (403)")
any_id = q1("SELECT id FROM qb_applicants WHERE stage='ariza' ORDER BY id LIMIT 1")
ok(oquv.post(X + f"/applicants/{any_id}/advance", json={}).status_code == 403, "O'quv prorektori bosqichni o'zgartira olmaydi (403)")
ok(rek.post(X + f"/applicants/{any_id}/reject", json={"note": "sabab bor"}).status_code == 403, "Rektor rad eta olmaydi (403)")
ok(mkt.post(X + "/order", params={"direction": DIR0}).status_code == 403, "Marketing buyruq loyihasini tuza olmaydi (403)")
ok(q1("SELECT stage FROM qb_applicants WHERE id=?", (any_id,)) == "ariza", "Rad etilgan so'rovlar bazani o'zgartirmadi")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE resource='admissions' AND allowed=0 AND action='qabul: abituriyentlar'") >= 4, "Rad etilgan so'rovlar auditda")

print("— Voronka sonlari (bazaga solishtirish) —")
db_stage = dict(q("SELECT stage, COUNT(*) FROM qb_applicants GROUP BY 1"))
ok(m["by_stage"] == db_stage, f"by_stage = baza: {db_stage}")
ok(sum(r["n"] for r in m["by_direction"]) == q1("SELECT COUNT(*) FROM qb_applicants"), "by_direction yig'indisi = jami abituriyentlar")
bd = {r["direction"]: r for r in m["by_direction"]}
dbd = {r[0]: r[1:] for r in q("""SELECT direction, COUNT(*), SUM(stage='ariza'), SUM(stage='hujjat'), SUM(stage='imtihon'), SUM(stage='shartnoma'),
                                  SUM(stage='buyruq'), SUM(stage='rad') FROM qb_applicants GROUP BY 1""")}
ok(all((bd[d]["n"], bd[d]["ariza"], bd[d]["hujjat"], bd[d]["imtihon"], bd[d]["shartnoma"], bd[d]["buyruq"], bd[d]["rad"]) == tuple(v) for d, v in dbd.items())
   and set(bd) == set(dbd), "by_direction har bir yo'nalish va bosqich bo'yicha = baza")
ok(all(r["n"] == r["ariza"] + r["hujjat"] + r["imtihon"] + r["shartnoma"] + r["buyruq"] + r["rad"] for r in m["by_direction"]), "Yo'nalish jami = bosqichlar yig'indisi")
desk = m["desk"]
ind = {i["key"]: i for i in desk["indicators"]}
ok(ind["arizalar"]["value"] == q1("SELECT COUNT(*) FROM applicants"), "Qabul tahlili: arizalar soni = applicants jadvali")
ok(ind["talaba"]["value"] == q1("SELECT COUNT(*) FROM applicants WHERE status=\"talaba bo'ldi\""), "Qabul tahlili: «Talaba bo'ldi» = baza")
ok({f["status"]: f["n"] for f in desk["funnel"]} == dict(q("SELECT status, COUNT(*) FROM applicants GROUP BY status")), "Qabul tahlili voronkasi = baza")
lst = J(qb.get(X + "/applicants", params={"stage": "ariza"}))["items"]
ok(len(lst) == min(400, db_stage.get("ariza", 0)) and all(x["stage"] == "ariza" and x["stage_label"] == "Ariza qabul qilindi" for x in lst), "Ro'yxat filtri stage=ariza = baza")
lst = J(qb.get(X + "/applicants", params={"direction": DIR0}))["items"]
ok(len(lst) == q1("SELECT COUNT(*) FROM qb_applicants WHERE direction=?", (DIR0,)) and all(x["direction"] == DIR0 for x in lst), "Ro'yxat filtri yo'nalish bo'yicha = baza")
ok(len(J(qb.get(X + "/applicants", params={"stage": "noma'lum"}))["items"]) == min(400, q1("SELECT COUNT(*) FROM qb_applicants")), "Noma'lum bosqich filtri e'tiborsiz (500 emas)")

print("— Kiritish xatolari —")
CNT0 = q1("SELECT COUNT(*) FROM qb_applicants")
J(qb.post(X + "/applicants", json={**body, "full_name": "Ab"}), 422); ok(True, "F.I.Sh. juda qisqa → 422")
J(qb.post(X + "/applicants", json={**body, "full_name": "        "}), 400); ok(True, "F.I.Sh. faqat bo'shliq → 400")
J(qb.post(X + "/applicants", json={k: v for k, v in body.items() if k != "direction"}), 422); ok(True, "Yo'nalishsiz → 422")
J(qb.post(X + "/applicants", json={**body, "direction": "TEST mavjud bo'lmagan yo'nalish"}), 400); ok(True, "Noma'lum yo'nalish → 400")
J(qb.post(X + "/applicants", json={**body, "study_form": "xyz"}), 400); ok(True, "Noma'lum ta'lim shakli → 400")
J(qb.post(X + "/applicants", json={**body, "payment_type": "bepul"}), 400); ok(True, "Noma'lum to'lov turi → 400")
J(qb.post(X + "/applicants", json={**body, "phone": "9" * 40}), 422); ok(True, "Telefon juda uzun → 422")
ok(q1("SELECT COUNT(*) FROM qb_applicants") == CNT0 and q1("SELECT COUNT(*) FROM qb_applicants WHERE TRIM(full_name)=''") == 0, "Xato so'rovlardan yozuv qolmadi")
ok(qb.post(X + "/applicants/99999999/advance", json={}).status_code == 404, "Mavjud bo'lmagan abituriyent: bosqich → 404")
ok(qb.post(X + "/applicants/99999999/reject", json={"note": "sabab bor"}).status_code == 404, "Mavjud bo'lmagan abituriyent: rad → 404")
ok(qb.post(X + "/order").status_code == 422, "Buyruq loyihasi yo'nalishsiz → 422")
ok(qb.post(X + "/order", params={"direction": "TEST bo'sh yo'nalish"}).status_code == 409, "Shartnomasiz yo'nalish bo'yicha buyruq → 409")

print("— Abituriyent oqimi —")
before = J(qb.get(X + "/meta"))["by_stage"]
a1 = J(qb.post(X + "/applicants", json=body))["id"]
a2 = J(qb.post(X + "/applicants", json={**body, "full_name": "TEST Abituriyent Ikkinchi", "study_form": "sirtqi", "payment_type": "grant"}))["id"]
a3 = J(qb.post(X + "/applicants", json={**body, "full_name": "TEST Abituriyent Uchinchi"}))["id"]
r = q("SELECT stage, direction, study_form, payment_type, created_by FROM qb_applicants WHERE id=?", (a1,))[0]
ok(r == ("ariza", DIR0, "kunduzgi", "kontrakt", uid("qabul")), "Yangi ariza: «ariza» bosqichi, maydonlar saqlandi")
ok(J(qb.get(X + "/meta"))["by_stage"]["ariza"] == before.get("ariza", 0) + 3, "Voronka: ariza +3")
ok(any(x["id"] == a1 for x in J(qb.get(X + "/applicants", params={"q": "TEST Abituriyent Birinchi"}))["items"]), "Qidiruv ism bo'yicha topadi")
ok(q1("SELECT COUNT(*) FROM qb_log WHERE app_id=? AND action='ariza qabul qilindi'", (a1,)) == 1, "Tarix jurnali: ariza qabul qilindi")
ok(J(qb.post(X + f"/applicants/{a1}/advance", json={}))["stage"] == "hujjat", "ariza → hujjat (ball shart emas)")
J(qb.post(X + f"/applicants/{a1}/advance", json={}), 400); ok(True, "hujjat → imtihon ballsiz → 400")
J(qb.post(X + f"/applicants/{a1}/advance", json={"exam_score": 120}), 400); ok(True, "Ball > 100 → 400")
J(qb.post(X + f"/applicants/{a1}/advance", json={"exam_score": -1}), 400); ok(True, "Ball < 0 → 400")
J(qb.post(X + f"/applicants/{a1}/advance", json={"exam_score": 55}), 400); ok(True, "Ball 55 (< o'tish bali 56) → 400")
J(qb.post(X + f"/applicants/{a1}/advance", json={"exam_score": "abc"}), 422); ok(True, "Ball son emas → 422")
ok(q1("SELECT stage FROM qb_applicants WHERE id=?", (a1,)) == "hujjat", "Xato ball bosqichni o'zgartirmadi")
ok(J(qb.post(X + f"/applicants/{a1}/advance", json={"exam_score": 56}))["stage"] == "imtihon", "Ball 56 (chegara) → imtihon")
ok(q1("SELECT exam_score FROM qb_applicants WHERE id=?", (a1,)) == 56, "Imtihon bali saqlandi")
ok(J(qb.post(X + f"/applicants/{a1}/advance", json={"exam_score": 10}))["stage"] == "shartnoma", "imtihon → shartnoma")
r = q("SELECT exam_score, contract_no FROM qb_applicants WHERE id=?", (a1,))[0]
ok(r[0] == 56, "Shartnoma bosqichida yuborilgan ball imtihon balini o'zgartirmaydi")
ok(r[1] == f"Q-27/{a1:04d}", f"Shartnoma raqami avtomatik: {r[1]}")
ok(qb.post(X + f"/applicants/{a1}/advance", json={}).status_code == 409, "shartnoma → keyingi qadam yo'q (409)")
J(qb.post(X + f"/applicants/{a2}/advance", json={})); J(qb.post(X + f"/applicants/{a2}/advance", json={"exam_score": 88}))
J(qb.post(X + f"/applicants/{a2}/advance", json={"contract_no": "TEST-Q-777", "note": "TEST izoh"}))
ok(q1("SELECT contract_no FROM qb_applicants WHERE id=?", (a2,)) == "TEST-Q-777", "Qo'lda kiritilgan shartnoma raqami saqlandi")
ok(q1("SELECT COUNT(*) FROM qb_log WHERE app_id=?", (a2,)) == 4, "Tarix jurnali: 4 yozuv (ariza + 3 bosqich)")
ok(any(x["id"] == a2 for x in J(qb.get(X + "/applicants", params={"q": "TEST-Q-777"}))["items"]), "Qidiruv shartnoma raqami bo'yicha topadi")

print("— Rad etish —")
J(qb.post(X + f"/applicants/{a3}/reject", json={"note": ""}), 400); ok(True, "Sababsiz rad → 400")
J(qb.post(X + f"/applicants/{a3}/reject", json={"note": "  a "}), 400); ok(True, "Juda qisqa sabab → 400")
J(qb.post(X + f"/applicants/{a3}/reject", json={"note": "x" * 301}), 422); ok(True, "Sabab > 300 belgi → 422")
J(qb.post(X + f"/applicants/{a3}/reject", json={"note": "TEST: hujjatlar to'liq emas"}))
ok(q("SELECT stage, note FROM qb_applicants WHERE id=?", (a3,))[0] == ("rad", "TEST: hujjatlar to'liq emas"), "Rad etildi, sabab saqlandi")
ok(qb.post(X + f"/applicants/{a3}/reject", json={"note": "yana bir bor"}).status_code == 409, "Qayta rad → 409")
ok(qb.post(X + f"/applicants/{a3}/advance", json={}).status_code == 409, "Rad etilgan → keyingi bosqich yo'q (409)")

print("— Qabul buyrug'i loyihasi —")
K = q1("SELECT COUNT(*) FROM qb_applicants WHERE stage='shartnoma' AND direction=?", (DIR0,))
ok(K >= 2, f"«{DIR0}»: shartnoma tuzilganlar {K} ta (2 tasi TEST)")
r = qb.post(X + "/order", params={"direction": DIR0})
ok(r.status_code == 200 and "wordprocessingml" in r.headers.get("content-type", "") and "qabul-buyrugi" in r.headers.get("content-disposition", ""), "Buyruq loyihasi .docx qaytdi")
doc, tables = docx_tables(r.content)
ok(len(tables) == 1 and len(tables[0]) == K + 1, f"Jadval: sarlavha + {K} qator")
names = [row[1] for row in tables[0][1:]]
ok("TEST Abituriyent Birinchi" in names and any(row[4] == "TEST-Q-777" for row in tables[0][1:]), "Jadvalda TEST abituriyentlar va shartnoma raqami")
ok(names == sorted(names), "Ro'yxat F.I.Sh. bo'yicha tartiblangan")
ok(any(DIR0 in p.text for p in doc.paragraphs), "Matnda yo'nalish nomi bor")
ok(q1("SELECT COUNT(*) FROM qb_applicants WHERE stage='shartnoma' AND direction=?", (DIR0,)) == 0, "Yo'nalishdagi barcha shartnomalar «buyruq» bosqichiga o'tdi")
r = q("SELECT stage, order_batch FROM qb_applicants WHERE id=?", (a1,))[0]
ok(r[0] == "buyruq" and r[1] == f"{DIR0[:30]} · {CLK.now().date().isoformat()}", f"Buyruq to'plami belgilandi: {r[1]}")
ok(q1("SELECT COUNT(*) FROM qb_log WHERE app_id=? AND action LIKE 'qabul buyrug%'", (a1,)) == 1, "Tarix jurnali: buyruq loyihasiga kiritildi")
ok(qb.post(X + "/order", params={"direction": DIR0}).status_code == 409, "Shu yo'nalishda ikkinchi marta → 409 (shartnoma qolmadi)")
ok(qb.post(X + f"/applicants/{a1}/reject", json={"note": "buyruqdan keyin"}).status_code == 409, "Buyruqdagi abituriyentni rad etib bo'lmaydi (409)")
ok(qb.post(X + f"/applicants/{a1}/advance", json={}).status_code == 409, "Buyruq bosqichidan keyingi qadam yo'q (409)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='qabul: buyruq loyihasi' AND allowed=1") >= 1, "Buyruq loyihasi auditda")
m2 = J(qb.get(X + "/meta"))
ok(m2["by_stage"] == dict(q("SELECT stage, COUNT(*) FROM qb_applicants GROUP BY 1")), "Oqimdan keyin voronka = baza")

print("— Mening vazifalarim va Bugun —")
def mw_qabul(cl):
    d = J(cl.get("/api/mywork"))
    return d, [i for i in d["items"] if i["source"] == "qabul"]
cut = (TODAY - dt.timedelta(days=3)).isoformat()
exp_old = lambda: q1("SELECT COUNT(*) FROM qb_applicants WHERE stage='ariza' AND created_at < ?", (cut,))
exp_sh = lambda: q1("SELECT COUNT(*) FROM qb_applicants WHERE stage='shartnoma'")
a4 = J(qb.post(X + "/applicants", json={**body, "full_name": "TEST Eski ariza"}))["id"]
n0 = exp_old()
w("UPDATE qb_applicants SET created_at=? WHERE id=?", (D(-5) + "T09:00:00", a4))
ok(exp_old() == n0 + 1, "Sinov: TEST arizasi 5 kun oldinga surildi")
d, its = mw_qabul(qb)
ok("qabul" not in d["partial"], "mywork: qabul manbasi xatosiz")
old = [i for i in its if "3 kundan beri" in i["title"]]
ok(len(old) == 1 and old[0]["title"].startswith(f"{exp_old()} ta ariza"), f"Qabul komissiyasi: «{old[0]['title'] if old else '—'}» = baza")
ok(old and old[0]["link"].get("view") == "qabul" and old[0]["due"] == TODAY.isoformat(), "Element havolasi «qabul» sahifasiga, muddat bugun")
sh = [i for i in its if "buyruq loyihasini" in i["title"]]
ok((len(sh) == 1 and sh[0]["title"].startswith(f"{exp_sh()} ta abituriyent")) if exp_sh() else not sh, f"Buyruq kutayotganlar: {exp_sh()} ta = baza")
ok(d["counts"]["by_source"].get("qabul") == len(its), "counts.by_source.qabul = elementlar soni")
# shartnoma bosqichidagi yangi abituriyent — son ortadi
J(qb.post(X + f"/applicants/{a4}/advance", json={})); J(qb.post(X + f"/applicants/{a4}/advance", json={"exam_score": 70})); J(qb.post(X + f"/applicants/{a4}/advance", json={}))
_, its = mw_qabul(qb)
sh = [i for i in its if "buyruq loyihasini" in i["title"]]
ok(len(sh) == 1 and sh[0]["title"].startswith(f"{exp_sh()} ta abituriyent") and exp_sh() >= 1, f"Shartnomadan keyin: {exp_sh()} ta buyruq kutmoqda")
old = [i for i in its if "3 kundan beri" in i["title"]]
ok((not old) if exp_old() == 0 else old[0]["title"].startswith(f"{exp_old()} ta ariza"), "Eski ariza bosqichdan o'tdi → «3 kundan beri» soni = baza")
for cl, nm in ((rek, "Rektor"), (mkt, "Marketing"), (oquv, "O'quv prorektori")):
    _, its = mw_qabul(cl)
    ok(not its, f"{nm}: qabul ishlari «Mening vazifalarim»da yo'q (faqat ko'radi)")
for cl, nm in ((qb, "Qabul"), (rek, "Rektor"), (mkt, "Marketing"), (oquv, "O'quv prorektori"), (ken, "Kengash")):
    r = cl.get("/api/bugun")
    ok(r.status_code == 200 and "items" in r.json() and "kpis" in r.json(), f"/api/bugun ({nm}) → 200")
ok(J(qb.get("/api/bugun"))["counts"]["by_source"].get("qabul", 0) >= 1, "Bugun: Qabul komissiyasida qabul ishlari sanaladi")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
