import os
"""«Akkaunt so'rovlari» — AT bo'limi (app/it_requests.py): uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_it_requests.py
Qamrov: ruxsatlar (kirishsiz 401, AT dan boshqa lavozimlar 403, muhandis faqat ko'radi), Kadrlar jarayonlaridan so'rovlar
(ishga qabul: «buyruq»/«qabul_qilindi» bosqichidagi nomzod → yangi akkaunt; bo'shatish: ariza…yakunlangan → faol akkauntlarni bloklash),
AT boshlig'i «Bajarildi» belgilaydi (ro'yxat va «Mening vazifalarim»dan chiqadi), validatsiya (noma'lum tur/id, hali kutilmayotgan
so'rov, takroriy belgilash, uzun izoh → 4xx, 500 emas), /api/mywork «it_req» manbai va /api/bugun 500 bermasligi, audit.
Test o'z yozuvlarini («TEST» belgisi bilan) qo'shadi va oxirida o'chiradi.
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
    if not cond: cleanup(); sys.exit(1)

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
    try: cur = con.execute(sql, args); con.commit(); return cur.lastrowid
    finally: con.close()

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

X = "/api/it-requests"
CREATED = {"vac": [], "cand": [], "dis": []}

def cleanup():
    for k, ids in (("hire", CREATED["cand"]), ("dismiss", CREATED["dis"])):
        for i in ids: w("DELETE FROM it_req_done WHERE kind=? AND ref_id=?", (k, i))
    for t, k in (("hr_candidates", "cand"), ("hr_dismissals", "dis"), ("hr_vacancies", "vac")):
        for i in CREATED[k]: w(f"DELETE FROM {t} WHERE id=?", (i,))

def lst(cl): return J(cl.get(X))["items"]
def find(items, kind, rid): return next((i for i in items if i["kind"] == kind and i["id"] == rid), None)
def mw(cl): return [i for i in J(cl.get("/api/mywork"))["items"] if i["source"] == "it_req"]

ith, its, dv, rek, kad, oq = (S(uid(r)) for r in ("it_head", "it_staff", "devonxona", "rektor", "kadrlar", "oqituvchi"))

print("— Ruxsatlar —")
ok(httpx.get(B + X).status_code == 401, "Kirishsiz: ro'yxat → 401")
ok(httpx.post(B + X + "/hire/1/done", json={}).status_code == 401, "Kirishsiz: bajarildi → 401")
for cl, nm in ((dv, "Devonxona"), (rek, "Rektor"), (kad, "Kadrlar"), (oq, "O'qituvchi")):
    ok(cl.get(X).status_code == 403, f"{nm}: ro'yxat → 403")
    ok(cl.post(X + "/hire/1/done", json={}).status_code == 403, f"{nm}: bajarildi → 403")
d = J(ith.get(X)); ok(d["can_edit"] is True and isinstance(d["items"], list), "AT boshlig'i: ro'yxat va tahrir huquqi")
d = J(its.get(X)); ok(d["can_edit"] is False, "AT muhandisi: faqat ko'radi (can_edit=false)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='akkaunt so''rovlari' AND resource='accounts' AND allowed=1") >= 2, "Ro'yxatni ko'rish auditda")

print("— Test ma'lumotlari: Kadrlar jarayonlari —")
base = len(lst(ith))
kaf = q1("SELECT key FROM org_units WHERE key LIKE 'kaf%' ORDER BY key LIMIT 1") or "kaf1"
now = CLK.now().replace(microsecond=0).isoformat()
V = w("INSERT INTO hr_vacancies(unit_key, position, status, note, created_at) VALUES(?,?,?,?,?)", (kaf, "TEST Dotsent", "ochiq", "TEST", now)); CREATED["vac"].append(V)
C1 = w("INSERT INTO hr_candidates(vacancy_id, full_name, stage, start_date, note, created_at) VALUES(?,?,?,?,?,?)", (V, "TEST Nomzod Buyruq", "buyruq", D(5), "TEST", now))
C2 = w("INSERT INTO hr_candidates(vacancy_id, full_name, stage, start_date, note, created_at) VALUES(?,?,?,?,?,?)", (V, "TEST Nomzod Suhbat", "suhbat", D(9), "TEST", now))
CREATED["cand"] += [C1, C2]
pair = q("""SELECT s.id, u.id, s.full_name FROM staff s JOIN users u ON u.full_name LIKE '%: ' || s.full_name
            WHERE u.role NOT IN ('it_head','it_staff') AND COALESCE(u.active,1)=1 ORDER BY s.id LIMIT 1""")
ok(bool(pair), f"Akkaunti bor xodim topildi: {pair[0][2] if pair else '—'}")
SID, UACC, SNAME = pair[0]
D1 = w("INSERT INTO hr_dismissals(staff_id, reason, app_date, last_day, status, note, created_at) VALUES(?,?,?,?,?,?,?)",
       (SID, "TEST o'z xohishi", D(-3), D(3), "buyruq", "TEST", now))
D2 = w("INSERT INTO hr_dismissals(staff_id, reason, app_date, last_day, status, note, created_at) VALUES(?,?,?,?,?,?,?)",
       (SID, "TEST bekor qilingan", D(-3), D(4), "bekor", "TEST", now))
CREATED["dis"] += [D1, D2]

print("— Ro'yxat: ishga qabul va bo'shatish —")
items = lst(ith)
h = find(items, "hire", C1)
ok(h is not None and h["person"] == "TEST Nomzod Buyruq" and h["position"] == "TEST Dotsent", "Ishga qabul (buyruq bosqichi): yangi akkaunt so'rovi")
ok(h["unit"] == kaf and h["unit_name"] and h["role"] == "oqituvchi", f"Kafedra vakansiyasi → rol «oqituvchi», bo'lim: {h['unit_name']}")
ok(h["date"] == D(5) and h["signed"] is False, "Ish boshlash sanasi; buyruq hali imzolanmagan")
ok(find(items, "hire", C2) is None, "Suhbat bosqichidagi nomzod — so'rov yo'q")
x = find(items, "dismiss", D1)
ok(x is not None and x["person"] == SNAME and x["signed"] is True and x["date"] == D(3), "Bo'shatish (buyruq): bloklash so'rovi, imzolangan, oxirgi kun")
ok(UACC in x["accounts"], f"Xodimning faol akkaunti ro'yxatda (#{UACC})")
ok(find(items, "dismiss", D2) is None, "Bekor qilingan bo'shatish — so'rov yo'q")
ok(len(items) == base + 2, f"Ro'yxat 2 taga oshdi ({base} → {len(items)})")
ok({(i["kind"], i["id"]) for i in lst(its)} == {(i["kind"], i["id"]) for i in items}, "Muhandis ham xuddi shu ro'yxatni ko'radi")
w("UPDATE hr_candidates SET stage='qabul_qilindi' WHERE id=?", (C1,))
ok(find(lst(ith), "hire", C1)["signed"] is True, "Qabul qilindi bosqichi → imzolangan")

print("— «Mening vazifalarim» (it_req manbai) —")
mi = mw(ith)
mh = [i for i in mi if i["title"] == "Yangi xodim: TEST Nomzod Buyruq"]
ok(len(mh) == 1 and mh[0]["due"] == D(5) and mh[0]["kind"] == "akkaunt" and mh[0]["link"].get("view") == "accounts", "AT boshlig'i: yangi akkaunt vazifasi (muddat = ish boshlash)")
ok(mh[0]["sub"] == h["unit_name"] and not mh[0]["sign"], "Vazifa: bo'lim nomi ko'rsatilgan, imzo emas")
md = [i for i in mi if i["title"] == f"Akkauntni bloklash: {SNAME}" and i["due"] == D(3)]
ok(len(md) == 1 and md[0]["bucket"] == "week", "AT boshlig'i: bloklash vazifasi (shu hafta)")
ok(len(mi) == len(lst(ith)) and len({i["id"] for i in mi}) == len(mi), f"Vazifalar soni = ro'yxat ({len(mi)} ta), id lar takrorlanmaydi")
ok(not mw(its), "AT muhandisi vazifalarida akkaunt so'rovlari yo'q (faqat boshliq)")
ok(not mw(kad) and not mw(dv), "Kadrlar va Devonxona vazifalarida it_req yo'q")
for cl, nm in ((ith, "AT boshlig'i"), (its, "AT muhandisi"), (kad, "Kadrlar")):
    b = cl.get("/api/bugun"); m2 = cl.get("/api/mywork")
    ok(b.status_code == 200 and m2.status_code == 200 and "it_req" not in m2.json()["partial"], f"{nm}: /api/bugun va /api/mywork — 200, it_req xatosiz")
ok(J(ith.get("/api/bugun"))["counts"]["by_source"].get("it_req", 0) == len(mi), "Bosh sahifa hisoblagichi: it_req")

print("— Validatsiya —")
ok(its.post(X + f"/hire/{C1}/done", json={}).status_code == 403, "Muhandis «Bajarildi» bosa olmaydi → 403")
ok(ith.post(X + f"/parol/{C1}/done", json={}).status_code == 404, "Noma'lum tur → 404")
ok(ith.post(X + "/hire/abc/done", json={}).status_code == 422, "id raqam emas → 422")
ok(ith.post(X + "/hire/999999/done", json={}).status_code == 404, "Yo'q nomzod → 404")
ok(ith.post(X + "/dismiss/999999/done", json={}).status_code == 404, "Yo'q bo'shatish → 404")
ok(ith.post(X + f"/hire/{C2}/done", json={}).status_code == 404, "Hali suhbatdagi nomzod (so'rov yo'q) → 404")
ok(ith.post(X + f"/dismiss/{D2}/done", json={}).status_code == 404, "Bekor qilingan bo'shatish → 404")
if find(lst(ith), "dismiss", C1) is None:
    ok(ith.post(X + f"/dismiss/{C1}/done", json={}).status_code == 404, "Tur va id mos emas (nomzod id si bo'shatish sifatida) → 404")
ok(ith.post(X + f"/hire/{C1}/done", json={"note": "x" * 301}).status_code == 422, "Izoh 300 belgidan uzun → 422")
ok(ith.post(X + f"/hire/{C1}/done", content=b"{bad", headers={"content-type": "application/json"}).status_code == 422, "Buzilgan JSON → 422")
ok(q1("SELECT COUNT(*) FROM it_req_done WHERE (kind='hire' AND ref_id IN (?,?,999999)) OR (kind='dismiss' AND ref_id IN (?,999999))", (C1, C2, D2)) == 0,
   "Rad etilgan so'rovlar «bajarildi» yozuvi qoldirmadi")

print("— Hayotiy sikl: bajarildi —")
J(ith.post(X + f"/hire/{C1}/done", json={"note": "  TEST akkaunt yaratildi  "}))
row = q("SELECT user_name, note, done_at FROM it_req_done WHERE kind='hire' AND ref_id=?", (C1,))[0]
ok(row[0] == q1("SELECT full_name FROM users WHERE id=?", (uid("it_head"),)) and row[1] == "TEST akkaunt yaratildi" and row[2], "Bajarildi: kim, izoh (qirqilgan), vaqt")
ok(find(lst(ith), "hire", C1) is None, "Ishga qabul so'rovi ro'yxatdan chiqdi")
ok(not any(i["title"] == "Yangi xodim: TEST Nomzod Buyruq" for i in mw(ith)), "… va «Mening vazifalarim»dan chiqdi")
ok(ith.post(X + f"/hire/{C1}/done", json={}).status_code == 409, "Takroriy «Bajarildi» → 409")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action='akkaunt so''rovi bajarildi' AND detail=?", (f"hire #{C1}",)) == 1, "Bajarildi auditda")

# suhbatdagi nomzod keyinroq buyruq bosqichiga o'tdi — endi so'rov paydo bo'ladi (oldindan yashirilmagan)
w("UPDATE hr_candidates SET stage='buyruq' WHERE id=?", (C2,))
ok(find(lst(ith), "hire", C2) is not None, "Keyin buyruq bosqichiga o'tgan nomzod — so'rov paydo bo'ldi")
J(ith.post(X + f"/hire/{C2}/done", json={}))
ok(find(lst(ith), "hire", C2) is None and q1("SELECT note FROM it_req_done WHERE kind='hire' AND ref_id=?", (C2,)) == "", "Izohsiz bajarildi")

J(ith.post(X + f"/dismiss/{D1}/done", json={"note": "TEST akkauntlar faolsizlantirildi"}))
ok(find(lst(ith), "dismiss", D1) is None, "Bloklash so'rovi ro'yxatdan chiqdi")
ok(not any(i["title"] == f"Akkauntni bloklash: {SNAME}" and i["due"] == D(3) for i in mw(ith)), "… va vazifalardan chiqdi")
ok(len(lst(ith)) == base, f"Ro'yxat dastlabki holatga qaytdi ({base} ta)")
ok(ith.post(X + f"/dismiss/{D1}/done", json={}).status_code == 409, "Bloklash: takroriy → 409")
ok(J(ith.get("/api/bugun"))["counts"]["by_source"].get("it_req", 0) == base, "Bosh sahifa hisoblagichi kamaydi")

cleanup()
ok(q1("SELECT COUNT(*) FROM hr_candidates WHERE note='TEST'") == 0 and q1("SELECT COUNT(*) FROM hr_dismissals WHERE note='TEST'") == 0, "Test yozuvlari tozalandi")
print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
