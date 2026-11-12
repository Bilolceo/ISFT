import os
"""«KPI maqsadlari» va «Sifat amallari» (app/rejalar.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_rejalar.py
Qamrov: ruxsatlar (kirishsiz 401; Strategik bo'lim — KPI tahriri, rahbariyat va kengash — KPI ko'rish; Sifat boshqarmasi — sifat tahriri,
rektor va o'quv prorektori — ko'rish; boshqalar — 403), KPI maqsadi hayotiy sikli (qo'shish → tahrirlash → «Erishildi» / «Jarayonda» /
«Muddati o'tdi» → o'chirish), amaldagi qiymat bazaga solishtiriladi, Kengash hisoboti (.docx jadvallari), sifat topilmasi → kafedraga
topshiriq (tasks, kafedra mudirining «Mening vazifalarim»), akkreditatsiya nazorat varaqasi, kiritish xatolari (4xx, 500 emas),
«Mening vazifalarim» (/api/mywork, pending._simple → rejalar.pending) va «Bugun» (/api/bugun).
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

def mw(cl, src):
    d = J(cl.get("/api/mywork"))
    return d, [i for i in d["items"] if i["source"] == src]

X = "/api/rejalar"
stg, sif, rek, ken, oquv, ilm, mol, ysh, qb, bux, mkt = (S(uid(r)) for r in ("strategik", "sifat", "rektor", "kengash", "prorektor_oquv", "prorektor_ilmiy",
                                                                             "prorektor_moliya", "prorektor_yoshlar", "qabul", "buxgalteriya", "marketing"))
K1, K2 = q1("SELECT head_user FROM org_units WHERE key='kaf1'"), q1("SELECT head_user FROM org_units WHERE key='kaf2'")
kaf1, kaf2 = S(K1), S(K2)

print("— Ruxsatlar —")
for p in ("/kpi", "/kengash.docx", "/sifat"):
    ok(httpx.get(B + X + p).status_code == 401, f"Kirishsiz: GET {p} → 401")
ok(httpx.post(B + X + "/kpi", json={"metric": "davomat", "owner_unit": "talabalar", "target": 90, "deadline": D(30)}).status_code == 401, "Kirishsiz: KPI maqsadi → 401")
k = J(stg.get(X + "/kpi"))
ok(k["can_edit"] is True and len(k["targets"]) >= 6 and k["metrics"] and k["units"], "Strategik bo'lim: KPI tahriri, demo maqsadlar, ko'rsatkichlar, bo'limlar")
for cl, nm in ((rek, "Rektor"), (ken, "Kengash"), (oquv, "O'quv prorektori"), (ilm, "Ilmiy prorektor"), (mol, "Moliya prorektori"), (ysh, "Yoshlar prorektori")):
    ok(J(cl.get(X + "/kpi"))["can_edit"] is False, f"{nm}: KPI faqat ko'rish")
for cl, nm in ((sif, "Sifat"), (qb, "Qabul"), (bux, "Buxgalteriya"), (mkt, "Marketing"), (kaf1, "Kafedra mudiri")):
    ok(cl.get(X + "/kpi").status_code == 403 and cl.get(X + "/kengash.docx").status_code == 403, f"{nm}: KPI va Kengash hisoboti → 403")
tbody = {"metric": "davomat", "title": "TEST davomat maqsadi", "owner_unit": "talabalar", "target": 50, "deadline": D(60), "note": "TEST"}
ok(rek.post(X + "/kpi", json=tbody).status_code == 403, "Rektor KPI maqsadi qo'ya olmaydi (403)")
ok(ken.post(X + "/kpi/1/delete").status_code == 403, "Kengash KPI maqsadini o'chira olmaydi (403)")
s = J(sif.get(X + "/sifat"))
ok(s["can_edit"] is True and s["akkr"] and s["kafedras"] and all(x["key"].startswith("kaf") for x in s["kafedras"]), "Sifat boshqarmasi: tahrir, nazorat varaqasi, faqat kafedralar ro'yxati")
for cl, nm in ((rek, "Rektor"), (oquv, "O'quv prorektori")):
    ok(J(cl.get(X + "/sifat"))["can_edit"] is False, f"{nm}: sifat amallari faqat ko'rish")
for cl, nm in ((stg, "Strategik"), (ken, "Kengash"), (ilm, "Ilmiy prorektor"), (kaf1, "Kafedra mudiri"), (qb, "Qabul")):
    ok(cl.get(X + "/sifat").status_code == 403, f"{nm}: sifat amallari → 403")
fbody = {"unit": "kaf1", "title": "TEST sillabus adabiyotlari eskirgan", "body": "TEST: 3 ta fanda adabiyotlar ro'yxati 2015-yildan eski.", "due": D(14)}
ok(rek.post(X + "/sifat/finding", json=fbody).status_code == 403, "Rektor topilma yubora olmaydi (403)")
ok(oquv.post(X + "/sifat/akkr/1", json={"status": "tayyor"}).status_code == 403, "O'quv prorektori akkreditatsiya bandini o'zgartira olmaydi (403)")
ok(stg.post(X + "/sifat/akkr", json={"section": "TEST", "title": "TEST band", "owner_unit": "sifat"}).status_code == 403, "Strategik akkreditatsiya bandi qo'sha olmaydi (403)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='KPI / sifat amallari' AND allowed=0") >= 10, "Rad etilgan so'rovlar auditda")

print("— Amaldagi qiymatlar (bazaga solishtirish) —")
ms = {m["key"]: m for m in k["metrics"]}
ok({"kontrakt", "davomat", "ozlashtirmagan", "scopus", "daraja", "ijro", "talabalar", "sillabus"} <= set(ms), "Ko'rsatkichlar: strategik va sifat kalitlari")
ok(ms["talabalar"]["value"] == q1("SELECT COUNT(*) FROM students WHERE status='faol'"), f"Faol talabalar = baza ({ms['talabalar']['value']})")
ok(ms["davomat"]["value"] == q1("SELECT ROUND(AVG(attendance),1) FROM students WHERE status='faol'"), f"Davomat = baza ({ms['davomat']['value']}%)")
kp = q1("SELECT 100.0*SUM(paid_amount)/SUM(contract_amount) FROM students WHERE payment_type='kontrakt'")
ok(abs(ms["kontrakt"]["value"] - kp) < 0.051, f"Kontrakt tushumi = baza ({ms['kontrakt']['value']}% ~ {kp:.2f})")
tk = q("""SELECT COUNT(*), SUM(status='bajarildi') FROM tasks WHERE status NOT IN ('qoralama','bekor')""")[0]
ok(abs(ms["ijro"]["value"] - 100.0 * tk[1] / tk[0]) < 0.051, f"Topshiriqlar ijrosi = baza ({ms['ijro']['value']}%)")
ok(ms["ozlashtirmagan"]["good"] == "down" and ms["davomat"]["good"] == "up", "Yo'nalish: o'zlashtirmaganlar — kamaygani yaxshi")
def status_of(t):
    v = t["actual"]
    if v is not None and (v >= t["target"] if t["good"] == "up" else v <= t["target"]): return "bajarildi"
    return "muddati_otgan" if t["deadline"] and t["deadline"] < TODAY.isoformat() else "yolda"
ok(all(t["actual"] == ms[t["metric"]]["value"] and t["status"] == status_of(t) for t in k["targets"]), "Har bir maqsad: amalda = ko'rsatkich, holat to'g'ri hisoblangan")
ok([t["deadline"] for t in k["targets"]] == sorted(t["deadline"] for t in k["targets"]), "Maqsadlar muddat bo'yicha tartiblangan")
ok(len(k["targets"]) == q1("SELECT COUNT(*) FROM kpi_targets"), "Maqsadlar soni = baza")

print("— KPI maqsadi: kiritish xatolari —")
J(stg.post(X + "/kpi", json={**tbody, "metric": "yoq_korsatkich"}), 400); ok(True, "Noma'lum ko'rsatkich → 400")
J(stg.post(X + "/kpi", json={**tbody, "owner_unit": "yoq_bolim"}), 400); ok(True, "Noma'lum mas'ul bo'lim → 400")
J(stg.post(X + "/kpi", json={**tbody, "deadline": "31.12.2026"}), 400); ok(True, "Muddat noto'g'ri formatda → 400")
J(stg.post(X + "/kpi", json={**tbody, "target": -5}), 400); ok(True, "Manfiy maqsad → 400")
r = stg.post(X + "/kpi", content=('{"metric":"davomat","owner_unit":"talabalar","target":NaN,"deadline":"%s"}' % D(60)).encode(), headers={"content-type": "application/json"})
ok(r.status_code in (400, 422), f"Maqsad NaN → {r.status_code} (500 emas)")
ok(stg.get(X + "/kpi").status_code == 200, "NaN urinishidan keyin KPI sahifasi ishlaydi")
J(stg.post(X + "/kpi", json={k_: v for k_, v in tbody.items() if k_ != "target"}), 422); ok(True, "Maqsad qiymatisiz → 422")
J(stg.post(X + "/kpi", json={**tbody, "title": "x" * 121}), 422); ok(True, "Nomi > 120 belgi → 422")
ok(q1("SELECT COUNT(*) FROM kpi_targets WHERE title LIKE 'TEST%' OR target IS NULL") == 0, "Xato so'rovlardan yozuv qolmadi")
ok(stg.post(X + "/kpi?tid=99999999", json=tbody).status_code == 404, "Mavjud bo'lmagan maqsadni tahrirlash → 404")
ok(stg.post(X + "/kpi/99999999/delete").status_code == 404, "Mavjud bo'lmagan maqsadni o'chirish → 404")

print("— KPI maqsadi: hayotiy sikl —")
# bir ko'rsatkichga bitta maqsad: demo bazada «davomat» va «ozlashtirmagan» maqsadlari bor — takror qo'shilmaydi (409)
SEED_COLS = "metric,title,owner_unit,target,good,deadline,note,created_by,created_at,updated_at"
SEED = q(f"SELECT {SEED_COLS} FROM kpi_targets WHERE metric IN ('davomat','ozlashtirmagan')")
if SEED:
    ok(stg.post(X + "/kpi", json={**tbody, "target": 50}).status_code == 409, "Shu ko'rsatkich bo'yicha ikkinchi maqsad → 409 (takror yo'q)")
    w("DELETE FROM kpi_targets WHERE metric IN ('davomat','ozlashtirmagan')")     # sikl sinovi uchun joy bo'shatiladi; oxirida tiklanadi
J(stg.post(X + "/kpi", json={**tbody, "target": 101}), 400); ok(True, "Foizli ko'rsatkichga 100% dan katta maqsad → 400")
J(stg.post(X + "/kpi", json={**tbody, "deadline": D(366 * 6)}), 400); ok(True, "Muddat 5 yildan uzoq → 400")
J(stg.post(X + "/kpi", json={**tbody, "deadline": D(-1)}), 400); ok(True, "Yangi maqsad muddati o'tgan sana → 400")
ok(q1("SELECT COUNT(*) FROM kpi_targets WHERE title LIKE 'TEST%'") == 0, "Rad etilgan so'rovlardan yozuv qolmadi")
dav = ms["davomat"]["value"]
tid = J(stg.post(X + "/kpi", json={**tbody, "target": dav - 5}))["id"]
row = q("SELECT metric, owner_unit, target, good, deadline, created_by FROM kpi_targets WHERE id=?", (tid,))[0]
ok(row == ("davomat", "talabalar", dav - 5, "up", D(60), uid("strategik")), "Maqsad saqlandi (yo'nalish ko'rsatkichdan olindi)")
t = next(x for x in J(stg.get(X + "/kpi"))["targets"] if x["id"] == tid)
ok(t["actual"] == dav and t["status"] == "bajarildi" and t["status_label"] == "Erishildi", f"Amalda {dav} ≥ maqsad {dav - 5} → «Erishildi»")
ok(t["owner_name"] == "Registrator ofisi" and t["unit"] == "%", "Mas'ul bo'lim nomi va o'lchov birligi")
J(stg.post(X + f"/kpi?tid={tid}", json={**tbody, "target": dav + 5}))
t = next(x for x in J(stg.get(X + "/kpi"))["targets"] if x["id"] == tid)
ok(t["target"] == dav + 5 and t["status"] == "yolda", "Tahrir: maqsad oshirildi → «Jarayonda»")
ok(stg.post(X + f"/kpi?tid={tid}", json={**tbody, "target": dav + 5, "deadline": D(-1)}).status_code == 400, "Tahrirda muddatni o'tgan sanaga surib bo'lmaydi (400)")
ok(stg.post(X + f"/kpi?tid={tid}", json={**tbody, "metric": "ozlashtirmagan", "target": 5}).status_code in (200, 409), "Tahrirda ko'rsatkichni almashtirish — takror bo'lsa 409")
J(stg.post(X + f"/kpi?tid={tid}", json={**tbody, "target": dav + 5}))
w("UPDATE kpi_targets SET deadline=? WHERE id=?", (D(-1), tid))      # vaqt o'tishi: muddat kecha tugadi
J(stg.post(X + f"/kpi?tid={tid}", json={**tbody, "target": dav + 5, "deadline": D(-1)})); ok(True, "O'tgan muddatli maqsadni (muddatini o'zgartirmay) tahrirlash mumkin")
t = next(x for x in J(stg.get(X + "/kpi"))["targets"] if x["id"] == tid)
ok(t["status"] == "muddati_otgan" and t["status_label"] == "Muddati o'tdi", "Muddat o'tdi, erishilmagan → «Muddati o'tdi»")
oz = ms["ozlashtirmagan"]["value"]
tid2 = J(stg.post(X + "/kpi", json={**tbody, "metric": "ozlashtirmagan", "title": "", "owner_unit": "akademik", "target": oz + 1, "deadline": "20270115"}))["id"]
t2 = next(x for x in J(stg.get(X + "/kpi"))["targets"] if x["id"] == tid2)
ok(t2["good"] == "down" and t2["status"] == "bajarildi", f"Kamaygani yaxshi: amalda {oz} ≤ {oz + 1} → «Erishildi»")
ok(t2["title"] == ms["ozlashtirmagan"]["label"], "Nomi bo'sh → ko'rsatkich nomi olinadi")
ok(t2["deadline"] == "2027-01-15", "Muddat YYYY-MM-DD ko'rinishida saqlanadi (20270115 → 2027-01-15)")
J(stg.post(X + f"/kpi?tid={tid2}", json={**tbody, "metric": "ozlashtirmagan", "owner_unit": "akademik", "target": max(oz - 1, 0), "deadline": D(30)}))
t2 = next(x for x in J(stg.get(X + "/kpi"))["targets"] if x["id"] == tid2)
ok(t2["status"] == "yolda", "Kamaygani yaxshi: amalda maqsaddan yuqori → «Jarayonda»")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='KPI maqsadi saqlandi' AND allowed=1") >= 5, "Saqlashlar auditda")

print("— Kengash hisoboti (DOCX) —")
from docx import Document
r = rek.get(X + "/kengash.docx")
q_ = (TODAY.month - 1) // 3 + 1
ok(r.status_code == 200 and "wordprocessingml" in r.headers.get("content-type", "") and f"{TODAY.year}-Q{q_}" in r.headers.get("content-disposition", ""),
   f"Rektor hisobotni yuklab oladi: kengash-hisoboti-{TODAY.year}-Q{q_}.docx")
doc = Document(io.BytesIO(r.content))
tg = J(stg.get(X + "/kpi"))["targets"]
ok(len(doc.tables) == 2 and len(doc.tables[0].rows) == len(tg) + 1, f"1-jadval: {len(tg)} maqsad + sarlavha")
ok(any(row.cells[0].text == "TEST davomat maqsadi" and row.cells[5].text == "Muddati o'tdi" for row in doc.tables[0].rows), "TEST maqsadi hisobotda «Muddati o'tdi» holatida")
done, late = sum(t["status"] == "bajarildi" for t in tg), sum(t["status"] == "muddati_otgan" for t in tg)
ok(any(p.text == f"Erishilgan: {done} / {len(tg)}; muddati o'tgan: {late}." for p in doc.paragraphs), f"Xulosa: erishilgan {done} / {len(tg)}, muddati o'tgan {late}")
ok(len(doc.tables[1].rows) == len(ms) + 1, f"2-jadval: {len(ms)} asosiy ko'rsatkich")
ok(any(f"{TODAY.year}-yil {q_}-chorak" in p.text for p in doc.paragraphs), "Sarlavhada yil va chorak")
ok(J(ken.get(X + "/kpi")) and ken.get(X + "/kengash.docx").status_code == 200, "Kuzatuv kengashi ham hisobotni oladi")

print("— Mening vazifalarim: KPI —")
d, its = mw(stg, "rejalar")
late_titles = [x["title"] for x in tg if x["status"] == "muddati_otgan"]
ok("rejalar" not in d["partial"], "mywork: rejalar manbasi xatosiz")
ok(sorted(i["title"] for i in its) == sorted(f"KPI maqsadi muddati o'tdi: {t}" for t in late_titles) and late_titles, f"Strategik: muddati o'tgan {len(late_titles)} ta maqsad = /kpi holati")
it = next(i for i in its if i["title"].endswith("TEST davomat maqsadi"))
ok(it["link"].get("view") == "rejalar" and it["due"] == D(-1) and it["overdue"] and it["sub"] == "Registrator ofisi", "Element: havola, muddat, kechikkan, mas'ul bo'lim")
for cl, nm in ((rek, "Rektor"), (ken, "Kengash"), (sif, "Sifat")):
    ok(not any(i["title"].startswith("KPI maqsadi") for i in mw(cl, "rejalar")[1]), f"{nm}: KPI ogohlantirishlari «Mening vazifalarim»da yo'q")
J(stg.post(X + f"/kpi/{tid}/delete"))
ok(q1("SELECT COUNT(*) FROM kpi_targets WHERE id=?", (tid,)) == 0, "Maqsad o'chirildi")
ok(not any(i["title"].endswith("TEST davomat maqsadi") for i in mw(stg, "rejalar")[1]), "O'chirilgan maqsad vazifalardan ketdi")
ok(stg.post(X + f"/kpi/{tid}/delete").status_code == 404, "Qayta o'chirish → 404")
J(stg.post(X + f"/kpi/{tid2}/delete"))
for row in SEED:     # demo maqsadlari joyiga qaytariladi
    w(f"INSERT INTO kpi_targets({SEED_COLS}) VALUES({','.join('?' * 10)})", row)

print("— Sifat topilmasi → kafedraga topshiriq —")
F0, T0 = q1("SELECT COUNT(*) FROM sifat_findings"), q1("SELECT COUNT(*) FROM tasks")
J(sif.post(X + "/sifat/finding", json={**fbody, "unit": "buxgalteriya"}), 400); ok(True, "Kafedra bo'lmagan bo'lim → 400")
J(sif.post(X + "/sifat/finding", json={**fbody, "unit": "kaf99"}), 400); ok(True, "Mavjud bo'lmagan kafedra → 400")
J(sif.post(X + "/sifat/finding", json={**fbody, "due": D(-1)}), 400); ok(True, "O'tgan muddat → 400")
J(sif.post(X + "/sifat/finding", json={**fbody, "due": "ertaga"}), 400); ok(True, "Muddat noto'g'ri → 400")
J(sif.post(X + "/sifat/finding", json={**fbody, "title": "abc"}), 422); ok(True, "Topilma juda qisqa → 422")
J(sif.post(X + "/sifat/finding", json={**fbody, "title": "            "}), 400); ok(True, "Topilma faqat bo'shliq → 400")
J(sif.post(X + "/sifat/finding", json={k_: v for k_, v in fbody.items() if k_ != "body"}), 422); ok(True, "Tafsilotsiz → 422")
ok(q1("SELECT COUNT(*) FROM sifat_findings") == F0 and q1("SELECT COUNT(*) FROM tasks") == T0, "Xato so'rovlardan topilma ham, topshiriq ham qolmadi")
r = J(sif.post(X + "/sifat/finding", json=fbody))
fid, did = r["id"], r["directive_id"]
row = q("SELECT unit, src, priority, status, due, due_at, issuer_user, text FROM tasks WHERE id=?", (did,))[0]
ok(row[:4] == ("kaf1", "sifat", "muhim", "yangi") and row[4] == D(14) and row[5] == D(14) + "T18:00" and row[6] == uid("sifat"),
   "Topshiriq yaratildi: kaf1, manba «sifat», muhim, yangi, muddat 18:00")
ok(row[7] == "Sifat topilmasi: " + fbody["title"], "Topshiriq matni topilmadan")
ok(q1("SELECT directive_id FROM sifat_findings WHERE id=?", (fid,)) == did, "Topilma topshiriqqa bog'langan")
f = next(x for x in J(sif.get(X + "/sifat"))["findings"] if x["id"] == fid)
ok(f["task_status"] == "yangi" and f["unit_name"] == "Iqtisodiyot va kompyuter injiniringi kafedrasi", "Sifat sahifasida: topshiriq holati va kafedra nomi")
ok(any(x["id"] == fid for x in J(rek.get(X + "/sifat"))["findings"]), "Rektor topilmalarni ko'radi")
d, its = mw(kaf1, "majlis")
ok(any(i["title"] == "Sifat topilmasi: " + fbody["title"] for i in its), "kaf1 mudiri: topshiriq «Mening vazifalarim»da")
ok(not any("TEST sillabus" in i["title"] for i in J(kaf2.get("/api/mywork"))["items"]), "kaf2 mudiri: boshqa kafedraning topshirig'i ko'rinmaydi")
w("UPDATE tasks SET status='bajarildi' WHERE id=?", (did,))
ok(next(x for x in J(sif.get(X + "/sifat"))["findings"] if x["id"] == fid)["task_status"] == "bajarildi", "Kafedra bajardi → topilmada «bajarildi»")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='sifat topilmasi kafedraga' AND allowed=1") >= 1, "Topilma auditda")

print("— Akkreditatsiya nazorat varaqasi —")
iid = s["akkr"][0]["id"]
J(sif.post(X + f"/sifat/akkr/{iid}", json={"status": "zor"}), 400); ok(True, "Noma'lum holat → 400")
ok(sif.post(X + "/sifat/akkr/99999999", json={"status": "tayyor"}).status_code == 404, "Mavjud bo'lmagan band → 404")
J(sif.post(X + f"/sifat/akkr/{iid}", json={"status": "jarayonda", "owner_unit": "yoq_bolim"}), 400); ok(True, "Noma'lum mas'ul bo'lim → 400")
J(sif.post(X + f"/sifat/akkr/{iid}", json={"status": "jarayonda", "due": "xyz"}), 400); ok(True, "Muddat noto'g'ri → 400")
orig = q("SELECT status, note, owner_unit, due FROM akkr_items WHERE id=?", (iid,))[0]
J(sif.post(X + f"/sifat/akkr/{iid}", json={"status": "jarayonda", "note": "TEST izoh: nusxalar to'planmoqda", "owner_unit": "kadrlar", "due": D(40)}))
ok(q("SELECT status, note, owner_unit, due, updated_by FROM akkr_items WHERE id=?", (iid,))[0][:4] == ("jarayonda", "TEST izoh: nusxalar to'planmoqda", "kadrlar", D(40)),
   "Band yangilandi: holat, izoh, mas'ul, muddat")
J(sif.post(X + f"/sifat/akkr/{iid}", json={"status": "tayyor"}))
ok(q("SELECT status, note, owner_unit, due FROM akkr_items WHERE id=?", (iid,))[0] == ("tayyor", "TEST izoh: nusxalar to'planmoqda", "kadrlar", D(40)),
   "Faqat holat o'zgardi (sahifadagi ro'yxat) — izoh, mas'ul, muddat saqlanib qoldi")
a = next(x for x in J(sif.get(X + "/sifat"))["akkr"] if x["id"] == iid)
ok(a["status_label"] == "Tayyor" and a["owner_name"] == "Kadrlar bo'limi", "Sahifada holat nomi va mas'ul bo'lim nomi")
J(sif.post(X + "/sifat/akkr", json={"section": "TEST", "title": "TEST band", "owner_unit": "yoq_bolim"}), 400); ok(True, "Yangi band: noma'lum mas'ul → 400")
J(sif.post(X + "/sifat/akkr", json={"section": "TEST", "title": "TEST band", "owner_unit": "sifat", "due": "abc"}), 400); ok(True, "Yangi band: muddat noto'g'ri → 400")
J(sif.post(X + "/sifat/akkr", json={"section": "T", "title": "TEST band", "owner_unit": "sifat"}), 422); ok(True, "Yangi band: bo'lim nomi juda qisqa → 422")
ok(q1("SELECT COUNT(*) FROM akkr_items WHERE section LIKE 'T%' AND title='TEST band'") == 0, "Xato so'rovlardan band qolmadi")
nid = J(sif.post(X + "/sifat/akkr", json={"section": "TEST mezon", "title": "TEST band: kutubxona fondi", "owner_unit": "arm", "due": D(10)}))["id"]
ok(q("SELECT status, owner_unit, due, updated_by FROM akkr_items WHERE id=?", (nid,))[0][:3] == ("yoq", "arm", D(10)), "Yangi band: «Boshlanmagan», mas'ul, muddat")
nid2 = J(sif.post(X + "/sifat/akkr", json={"section": "TEST mezon", "title": "TEST band muddatsiz", "owner_unit": "arm"}))["id"]
ok(q1("SELECT due FROM akkr_items WHERE id=?", (nid2,)) is None, "Muddatsiz band — due NULL")

print("— Mening vazifalarim: akkreditatsiya —")
exp = lambda: q1("SELECT COUNT(*) FROM akkr_items WHERE status!='tayyor' AND due < ?", (TODAY.isoformat(),))
n0 = exp()
w("UPDATE akkr_items SET due=? WHERE id=?", (D(-3), nid))
ok(exp() == n0 + 1, "Sinov: TEST bandi muddati o'tgan qilib qo'yildi")
d, its = mw(sif, "rejalar")
ok("rejalar" not in d["partial"] and len(its) == 1 and its[0]["title"] == f"Akkreditatsiya: {exp()} ta band muddati o'tgan", f"Sifat: «{its[0]['title'] if its else '—'}» = baza")
ok(its[0]["link"].get("view") == "rejalar" and its[0]["due"] == TODAY.isoformat(), "Element havolasi «rejalar», muddat bugun")
ok(d["counts"]["by_source"].get("rejalar") == 1, "counts.by_source.rejalar = 1")
for cl, nm in ((rek, "Rektor"), (oquv, "O'quv prorektori"), (stg, "Strategik")):
    ok(not any(i["title"].startswith("Akkreditatsiya") for i in mw(cl, "rejalar")[1]), f"{nm}: akkreditatsiya ogohlantirishi yo'q")
J(sif.post(X + f"/sifat/akkr/{nid}", json={"status": "tayyor"}))
its = mw(sif, "rejalar")[1]
ok((not its) if exp() == 0 else its[0]["title"] == f"Akkreditatsiya: {exp()} ta band muddati o'tgan", "Band tayyor → ogohlantirish soni kamaydi (= baza)")
w("UPDATE akkr_items SET status=?, note=?, owner_unit=?, due=? WHERE id=?", (*orig, iid))   # demo holatini tiklash

print("— Bugun —")
for cl, nm in ((stg, "Strategik"), (sif, "Sifat"), (rek, "Rektor"), (ken, "Kengash"), (oquv, "O'quv prorektori"), (kaf1, "Kafedra mudiri")):
    r = cl.get("/api/bugun")
    ok(r.status_code == 200 and "items" in r.json() and "kpis" in r.json(), f"/api/bugun ({nm}) → 200")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
