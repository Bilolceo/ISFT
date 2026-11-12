#!/usr/bin/env python3
"""Bo'limlar kaliti (app/modules.py) va u bilan birga kelgan soddalashtirish testlari.

  A. birlik: standartlar, ISFT_CORE_MODULES sintaksisi, qulflangan bo'limlar
  B. API: /api/me → modules; /api/modules (ko'rish, yoqish/o'chirish, ruxsat, audit)
  C. kamera simulyatori: bo'lim o'chiq — panelda «Kameralar» KPI va ogohlantirishlari yo'q; yoqilganda (ISFT_CORE_CAM_SIM=1) — bor
  D. occupancy.cleanup: simulyator o'chiq — uning ochiq arizalari va sanoqlari o'chadi; yoqilgan — 7 kunlik saqlash
  E. kirish sahifasi: /api/users ism bermaydi, sinov paroli sahifada yo'q, dizayn almashtirgich yo'q
  F. eski endpointlar yo'q; proksi ortidagi IP (X-Forwarded-For o'ngdan); urinishlar cheklovi xotirasi chegaralangan
  G. statik: menyu, «Bo'limlar» sahifasi, «Namuna ma'lumot» belgilari

Ishga tushirish:  .venv/bin/python tests/test_modullar.py   (server: ISFT_TEST_URL; tests/run_all.py o'zi beradi)
"""
import os, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = "Isft2026"
fails = 0

def ok(cond, msg):
    global fails
    print(("✓ " if cond else "✗ XATO: ") + msg); fails += (not cond)

def S(uid, headers=None):
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/login", json={"user_id": uid, "password": PW}, headers=headers or {})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

REKTOR, IT, TEACHER, REG, XOJ = 2, 21, 15, 17, 16
ON = {"panel", "mywork", "tasks", "portal", "documents", "orders", "ops", "masofaviy", "paket", "testbank", "taqdimot", "service", "accounts", "audit", "rbac", "modullar"}
OFF = {"moliya", "kadrlar", "staffabs", "yoshlar", "spaces", "cams", "syllabus", "flows", "reyting", "amaliyot", "ilmiy", "xalqaro", "rejalar", "tekshiruv",
       "qabul", "docs", "agents", "chat", "reports", "kiruvchi"}

# ===================================================================== A
print("— A. Birlik: standartlar va muhit sintaksisi —")
_saved = {k: os.environ.pop(k, None) for k in ("ISFT_CORE_MODULES", "ISFT_CORE_CAM_SIM", "ISFT_CORE_REAL_DATA", "ISFT_CORE_SHOW_DEMO_PASSWORD")}
from app import modules as M   # noqa: E402 — bazasiz: faqat standart + muhit
st = M.state()
ok({k for k, v in st.items() if v} == ON and {k for k, v in st.items() if not v} == OFF, f"Standart: {len(ON)} ta yoqilgan, {len(OFF)} ta o'chiq")
ok(all(m["title"] and m["desc"] and (m["default"] or m["needs"]) for m in M.MODULES), "Har bir bo'limda nom, tavsif; o'chiqlarida — yoqish uchun nima kerakligi")
os.environ["ISFT_CORE_MODULES"] = "+moliya, -testbank,reyting , -panel,yoq_bolim,+"
ok(M.env_overrides() == {"moliya": True, "testbank": False, "reyting": True}, f"ISFT_CORE_MODULES: +x, -y, belgisiz = yoqish; qulflangan va noma'lum nomlar tashlanadi ({M.env_overrides()})")
ok(M.on("moliya") and not M.on("testbank") and M.on("reyting") and M.on("panel") and M.on("mavjud_emas"), "on(): muhit ustun; qulflangan bo'lim doim yoqilgan; reestrda yo'q kalit — cheklanmaydi")
ok(any(x["key"] == "moliya" and x["env"] and x["enabled"] for x in M.listing()), "listing(): muhit bilan belgilangan bo'lim «env» deb ko'rsatiladi")
os.environ.pop("ISFT_CORE_MODULES")
ok(not M.cam_sim() and not M.cam_sim_active() and not M.real_data() and not M.show_demo_password(), "Standart: kamera simulyatori, «haqiqiy ma'lumot» va sinov paroli — o'chiq")
ok(M.sample("HEMIS") == "Namuna ma'lumot (HEMIS ulanmagan)", "Manba yorlig'i: «Namuna ma'lumot (HEMIS ulanmagan)»")
os.environ["ISFT_CORE_REAL_DATA"] = "1"; ok(M.sample("HEMIS") == "HEMIS", "ISFT_CORE_REAL_DATA=1 — manba nomi o'zi"); os.environ.pop("ISFT_CORE_REAL_DATA")
os.environ["ISFT_CORE_CAM_SIM"] = "1"
ok(M.cam_sim() and not M.cam_sim_active(), "ISFT_CORE_CAM_SIM=1, lekin bo'lim o'chiq — simulyator faol emas")
os.environ["ISFT_CORE_MODULES"] = "+cams"; ok(M.cam_sim_active(), "… bo'lim ham yoqilsa — faol"); os.environ.pop("ISFT_CORE_MODULES"); os.environ.pop("ISFT_CORE_CAM_SIM")

# ===================================================================== D (bazasiz — xotiradagi sqlite)
print("\n— D. occupancy.cleanup (xotiradagi baza) —")
import datetime as dt
from app import occupancy as OC, clock   # noqa: E402
def mk():
    c = sqlite3.connect(":memory:")
    c.executescript("""CREATE TABLE tickets(id INTEGER PRIMARY KEY, room_id INT, item TEXT, text TEXT, reporter TEXT, status TEXT, procurement_id INT);
        CREATE TABLE cameras(id INTEGER PRIMARY KEY, room_id INT, mode TEXT, ticket_id INT, ticket_kind TEXT);
        CREATE TABLE cam_events(id INTEGER PRIMARY KEY, ticket_id INT);
        CREATE TABLE occupancy(room_id INT, ts TEXT, count INT);""")
    c.executemany("INSERT INTO cameras(id,room_id,mode,ticket_id,ticket_kind) VALUES(?,?,?,?,?)", [(1, 1, "sim", 1, "aloqa"), (2, 2, "isapi", 2, "aloqa"), (3, 3, "sim", None, None)])
    c.executemany("INSERT INTO tickets(id,room_id,item,text,reporter,status,procurement_id) VALUES(?,?,?,?,?,?,?)", [
        (1, 1, "Kamera", "Kamera 10+ daqiqa javob bermayapti", "ISFT Core (avtomatik)", "yangi", None),          # simulyator, ochiq → o'chadi
        (2, 2, "Kamera", "Kamera 10+ daqiqa javob bermayapti", "ISFT Core (avtomatik)", "yangi", None),          # haqiqiy kamera → qoladi
        (3, 3, "Kamera", "Kamera javob bermayapti", "ISFT Core (avtomatik)", "hal qilindi", None),               # yopilgan → tarix, qoladi
        (4, 3, "Proyektor", "Yonmayapti", "o'qituvchi", "yangi", None),                                          # odam yozgan → qoladi
        (5, 3, "Xavfsizlik", "Tungi kirish", "ISFT Core (kamera voqeasi)", "jarayonda", None),                   # simulyator voqeasi, ochiq → o'chadi
        (6, 3, "Kamera", "Kamera javob bermayapti", "ISFT Core (avtomatik)", "yangi", 7)])                        # xaridga bog'langan → qoladi
    c.execute("INSERT INTO cam_events(id,ticket_id) VALUES(1,5)")
    now = clock.now().replace(microsecond=0)
    c.executemany("INSERT INTO occupancy VALUES(?,?,?)", [(1, (now - dt.timedelta(days=d)).isoformat(), 5) for d in (0, 3, 9, 30)] +
                  [(2, (now - dt.timedelta(days=d)).isoformat(), 7) for d in (0, 30)])
    c.commit(); return c
c = mk(); r = OC.cleanup(c)
ids = [x[0] for x in c.execute("SELECT id FROM tickets ORDER BY id")]
ok(r["tickets"] == 2 and ids == [2, 3, 4, 6], f"Simulyator o'chiq: uning OCHIQ arizalari o'chdi; haqiqiy kamera, yopilgan, odam yozgan va xaridga bog'langani qoldi ({ids})")
ok(c.execute("SELECT ticket_id FROM cameras WHERE id=1").fetchone()[0] is None and c.execute("SELECT ticket_id FROM cameras WHERE id=2").fetchone()[0] == 2
   and c.execute("SELECT ticket_id FROM cam_events").fetchone()[0] is None, "Kamera va voqea yozuvlaridagi ariza havolasi tozalandi (haqiqiy kameraniki — joyida)")
ok(c.execute("SELECT COUNT(*) FROM occupancy WHERE room_id=1").fetchone()[0] == 0 and c.execute("SELECT COUNT(*) FROM occupancy WHERE room_id=2").fetchone()[0] == 2,
   "Simulyator sanoqlari to'liq o'chdi; haqiqiy kamera xonasiniki qoldi")
ok(OC.cleanup(c) == {"tickets": 0, "occupancy": 0}, "Takror chaqiruv — hech narsa o'zgarmaydi (idempotent)")
os.environ["ISFT_CORE_CAM_SIM"] = "1"
OC.KEEP_DAYS = 7   # standart (tests/run_all.py seed tarixi uchun ISFT_CORE_OCC_KEEP_DAYS=40 beradi)
c = mk(); r = OC.cleanup(c)
ok(r["tickets"] == 0 and c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 6, "Simulyator yoqilgan: arizalarga tegilmaydi")
ok(c.execute("SELECT COUNT(*) FROM occupancy").fetchone()[0] == 3, f"Simulyator yoqilgan: {OC.KEEP_DAYS} kundan eski sanoqlar o'chadi (6 → 3)")
os.environ.pop("ISFT_CORE_CAM_SIM")
import asyncio
OC._con = mk(); before = OC._con.execute("SELECT COUNT(*) FROM occupancy").fetchone()[0]
asyncio.run(OC.poll_once())
ok(OC._con.execute("SELECT COUNT(*) FROM occupancy").fetchone()[0] == before and OC._con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 6,
   "Bo'lim o'chiq: fon so'rovchisi hech narsa yozmaydi (sanoq ham, ariza ham)")
OC._con = None

# ===================================================================== F (birlik)
print("\n— F1. Urinishlar cheklovi xotirasi —")
from app import sessions as SS   # noqa: E402
L = SS.Limiter(5, 600)
for i in range(L.MAX_KEYS + 1500): L.fail(f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}")
ok(len(L._f) <= L.MAX_KEYS + 1, f"Limiter: {L.MAX_KEYS + 1500} ta turli kalitdan keyin xotirada {len(L._f)} ta (chegara {L.MAX_KEYS})")
for _ in range(5): L.fail("hujumchi")
ok(L.wait_min("hujumchi") > 0 and L.wait_min("boshqa") == 0, "Limiter: 5 ta xato → blok; boshqa kalitga ta'sir yo'q")
for k, v in _saved.items():
    if v is not None: os.environ[k] = v

# ===================================================================== B
print("\n— B. API: /api/me va /api/modules —")
rk, it, oq, reg = S(REKTOR), S(IT), S(TEACHER), S(REG)
def mods(c): return c.get("/api/me").json()["modules"]
m0 = mods(it)
touched = {k: m0[k] for k in ("moliya", "cams", "reyting")}
try:
    for k in touched: it.post(f"/api/modules/{k}", json={"enabled": False})
    me = oq.get("/api/me").json()
    ok(set(me["modules"]) == ON | OFF and all(me["modules"][k] for k in ON) and not any(me["modules"][k] for k in OFF),
       "/api/me: modules — standart holat (o'qituvchi ham ko'radi: menyu shundan quriladi)")
    ok(set(me["flags"]) >= {"real_data", "cam_sim", "demo_login"} and me["flags"]["real_data"] is False, "/api/me: flags (real_data=false → «Namuna ma'lumot» tasmasi)")
    ok(httpx.get(B + "/api/modules").status_code == 401, "/api/modules: kirishsiz — 401")
    d = oq.get("/api/modules").json()
    ok("list" not in d and d["can_edit"] is False and d["modules"] == me["modules"], "O'qituvchi: faqat holat, tavsiflar ro'yxati va tahrir yo'q")
    r = oq.post("/api/modules/moliya", json={"enabled": True})
    ok(r.status_code == 403 and mods(oq)["moliya"] is False, "O'qituvchi bo'limni yoqa olmaydi (403)")
    ok(reg.post("/api/modules/moliya", json={"enabled": True}).status_code == 403, "Registrator ofisi ham yoqa olmaydi (403)")
    d = it.get("/api/modules").json()
    ok(d["can_edit"] and len(d["list"]) == len(ON | OFF) and all(x["why_off"] for x in d["list"] if not x["enabled"]),
       f"AT boshlig'i: to'liq ro'yxat ({len(d['list'])}), har bir o'chiq bo'limda sababi")
    ok(next(x for x in d["list"] if x["key"] == "moliya")["why_off"] == "egasi va haqiqiy ma'lumot manbai yo'q", "O'chiq bo'lim sababi: «egasi va haqiqiy ma'lumot manbai yo'q»")
    t0 = time.strftime("%Y-%m-%dT%H:%M:%S")
    r = it.post("/api/modules/moliya", json={"enabled": True})
    ok(r.status_code == 200 and r.json()["modules"]["moliya"] is True and mods(oq)["moliya"] is True, "AT boshlig'i «Moliya»ni yoqdi — hamma foydalanuvchida darhol yoqilgan")
    ok(bool(q("SELECT 1 FROM audit_log WHERE resource='modullar' AND allowed=1 AND user_id=? AND detail LIKE 'moliya%'", (IT,))), "Audit: bo'lim yoqilgani yozildi")
    ok(bool(q("SELECT 1 FROM audit_log WHERE resource='modullar' AND allowed=0 AND user_id=?", (TEACHER,))), "Audit: o'qituvchining urinishi rad deb yozildi")
    ok(rk.post("/api/modules/moliya", json={"enabled": False}).status_code == 200 and mods(it)["moliya"] is False, "Rektor ham o'chira oladi")
    ok(it.post("/api/modules/panel", json={"enabled": False}).status_code == 400 and mods(it)["panel"] is True, "Qulflangan bo'lim (panel) o'chirilmaydi (400)")
    ok(it.post("/api/modules/yoq_bolim", json={"enabled": True}).status_code == 404, "Noma'lum bo'lim — 404")
    ok(it.post("/api/modules/moliya", json={}).status_code == 422, "enabled berilmasa — 422")
    # mahsulot kaliti, xavfsizlik chegarasi emas: o'chiq bo'lim API'si ishlayveradi (ruxsat — rbac)
    ok(mods(rk)["reyting"] is False and rk.get("/api/reyting/meta").status_code in (200, 404) and rk.get("/api/moliya/meta").status_code != 500
       and rk.get("/api/section/finance").status_code == 200, "O'chiq bo'lim API'si yopilmaydi (kalit — menyu/panel uchun, ruxsatni rbac tekshiradi)")

    # ================================================================= C
    print("\n— C. Kamera simulyatori va panel —")
    sim = rk.get("/api/me").json()["flags"]["cam_sim"]
    dash = rk.get("/api/dashboard").json()
    areas = {a["area"] for a in dash["alerts"]}
    ok(not any(k.get("key") == "kameralar" for k in dash["kpis"]), "Bo'lim o'chiq: panelda «Kameralar» KPI yo'q")
    ok(not areas & {"Auditoriyalar", "Kameralar", "Navbat", "Xavfsizlik", "Favqulodda"}, f"Bo'lim o'chiq: kamera ogohlantirishlari yo'q ({sorted(areas)})")
    ok(rk.get("/api/spaces/overview").status_code == 200, "…lekin API ishlaydi (/api/spaces/overview 200)")
    if sim:
        it.post("/api/modules/cams", json={"enabled": True})
        ok(any(k.get("key") == "kameralar" for k in rk.get("/api/dashboard").json()["kpis"]), "ISFT_CORE_CAM_SIM=1 va bo'lim yoqilgan: «Kameralar» KPI paydo bo'ldi")
        it.post("/api/modules/cams", json={"enabled": False})
        ok(not any(k.get("key") == "kameralar" for k in rk.get("/api/dashboard").json()["kpis"]), "Bo'lim o'chirildi: KPI yana yo'q")
    else:
        it.post("/api/modules/cams", json={"enabled": True})
        ok(not any(k.get("key") == "kameralar" for k in rk.get("/api/dashboard").json()["kpis"]) or bool(q("SELECT 1 FROM cameras WHERE mode='isapi'")),
           "Simulyator o'chiq (ISFT_CORE_CAM_SIM yo'q): bo'lim yoqilsa ham haqiqiy kamerasiz KPI yo'q")
        it.post("/api/modules/cams", json={"enabled": False})
    k = next((x for x in dash["kpis"] if x.get("key") == "talabalar"), None)
    ok(k is not None and k["source"].startswith("Namuna ma'lumot") and "HEMIS ulanmagan" in k["source"], f"KPI manbasi: «{k and k['source']}» («Manba: HEMIS» emas)")
    ok(not any(str(x.get("source", "")).startswith("HEMIS") for x in dash["kpis"]), "Hech bir KPI manbasi «HEMIS» deb ko'rsatilmaydi")
finally:
    for k, v in touched.items(): it.post(f"/api/modules/{k}", json={"enabled": bool(v)})

# ===================================================================== E
print("\n— E. Kirish sahifasi —")
us = httpx.get(B + "/api/users").json()
demo = rk.get("/api/me").json()["flags"]["demo_login"]
ok(len(us) > 30 and all({"id", "role", "level"} <= set(u) for u in us), f"/api/users: {len(us)} ta akkaunt — id, lavozim, daraja")
if not demo:
    ok(not any("name" in u or "photo" in u for u in us), "/api/users: F.I.Sh. va rasm yo'q (kirishdan oldin shaxsiy ma'lumot berilmaydi)")
    full = {r[0].split(":", 1)[1].strip() for r in q("SELECT full_name FROM users WHERE full_name LIKE '%:%'")}
    blob = httpx.get(B + "/api/users").text
    ok(not any(n and n in blob for n in full), "/api/users javobida xodimlar ismi umuman uchramaydi")
    titles = [u["role"] for u in us]
    dups = [u for u in us if titles.count(u["role"]) > 1]
    ok(bool(dups) and all(u.get("hint") == f"akkaunt № {u['id']}" for u in dups) and not any("hint" in u for u in us if titles.count(u["role"]) == 1),
       f"Bir xil nomli akkauntlar ({len(dups)} ta) akkaunt raqami bilan farqlanadi; qolganlarida belgi yo'q")
    core = httpx.get(B + "/api/public/core.js").text
    ok(PW not in core and '"demo_pw": ""' in core and "ISFT_HIDE_DEMO_HINT=true" in core, "/api/public/core.js: sinov paroli yo'q, izoh yashirilgan")
else:
    print("  · ISFT_CORE_SHOW_DEMO_PASSWORD=1 — namoyish rejimi: ism va parol ko'rsatiladi (tekshiruvlar o'tkazib yuborildi)")
ok(all(u.get("search_only") for u in us if u["role"].startswith("Tyutor")), "Tyutorlar — faqat qidiruvda (search_only)")
idx = httpx.get(B + "/index.html").text; appjs = httpx.get(B + "/app.js").text
ok(PW not in idx and PW not in appjs and all(PW not in httpx.get(f"{B}/login/v{n}.js").text for n in (1, 2, 3)), "Sahifa va skriptlarda sinov paroli matni yo'q")
ok("switcher.js" not in idx and "switcher.css" not in idx and "jarvis-login\",v" not in idx, "Dizayn almashtirgich (DIZAYN 1/2/3) foydalanuvchiga yuklanmaydi")
ok("LOGIN_AFTER && LOGIN_AFTER();" in idx and "USERS.length" in idx.split("LOGIN_AFTER && LOGIN_AFTER();")[1] and "drawRoles()" in idx.split("LOGIN_AFTER && LOGIN_AFTER();")[1],
   "Sovuq yuklanish: LOGIN_AFTER dan keyin ro'yxat qayta chiziladi («Yuklanmoqda…» qotmaydi)")
ok("Yuklanmoqda" not in httpx.get(B + "/login/v1.js").text, "Kirish (1-variant): lavozim maydonida «Yuklanmoqda…» yozuvi yo'q")

# ===================================================================== F
print("\n— F2. Eski endpointlar va proksi ortidagi IP —")
for path, body in (("/api/meetings", {"title": "t", "transcript": "t", "tasks": []}), ("/api/meetings/extract", {"transcript": "t"}), ("/api/tasks/1/status", {"status": "bajarildi"})):
    ok(rk.post(path, json=body).status_code in (404, 405), f"POST {path} — yo'q")
t0 = time.strftime("%Y-%m-%dT%H:%M:%S")
S(XOJ, {"X-Forwarded-For": "198.51.100.9, 203.0.113.77"})
rows = [r[0] for r in q("SELECT detail FROM audit_log WHERE user_id=? AND action='tizimga kirish' AND allowed=1 ORDER BY id DESC LIMIT 1", (XOJ,))]
ok(bool(rows) and "IP 203.0.113.77" in rows[0] and "198.51.100.9" not in rows[0],
   f"X-Forwarded-For: mijoz yozgan chap qiymat emas, ishonchli proksi qo'shgan o'ng qiymat olinadi ({rows[0] if rows else '-'})")
S(XOJ, {"X-Forwarded-For": "bu-ip-emas"})
rows = [r[0] for r in q("SELECT detail FROM audit_log WHERE user_id=? AND action='tizimga kirish' AND allowed=1 ORDER BY id DESC LIMIT 1", (XOJ,))]
ok(bool(rows) and "bu-ip-emas" not in rows[0], f"Buzuq sarlavha qiymati IP sifatida qabul qilinmaydi ({rows[0] if rows else '-'})")
ok(it.get("/api/section/audit").status_code == 200 and rk.get("/api/section/audit").status_code == 200 and oq.get("/api/section/audit").status_code == 403,
   "Audit jurnali: AT boshlig'i va rektor ko'radi, o'qituvchi — yo'q")

# ===================================================================== G
print("\n— G. Statik —")
navjs = httpx.get(B + "/nav.js").text
ok('data-v="modullar"' in idx and 'id="v-modullar"' in idx and 'id="dataBanner"' in idx and "Namuna ma'lumot — haqiqiy tizimlar (HEMIS, NEXTID) hali ulanmagan" in idx,
   "index.html: «Bo'limlar» menyu bandi va sahifasi, «Namuna ma'lumot» tasmasi")
ok(all(s in appjs for s in ("function modGate", "function navApply", "async function renderModullar", "Bu bo'lim o'chirilgan", "function modWork")), "app.js: kalit, menyu, «Bu bo'lim o'chirilgan» kartasi, sahifa")
ok("modGate(v)" in idx, "index.html: go() eng tashqi qatlamda kalit bilan o'ralgan")
import re
ok(not re.search(r'(?<!realData\(\) \? ["`])Manba: HEMIS', appjs) and "demoChip(" in appjs, "app.js: «Manba: HEMIS» faqat ISFT_CORE_REAL_DATA=1 tarmog'ida, aks holda «Namuna ma'lumot» belgisi")
ok('>Nosozliklar va murojaatlar</a>' in idx and "xarid: \"Xarid so'rovlari\"" not in navjs, "Menyu: «Nosozliklar va murojaatlar» nomi lavozimga qarab o'zgarmaydi")
ok("Portal</button>" not in httpx.get(B + "/mywork.js").text and "Hujjatlar markazi" not in appjs.replace("/* ---------- Hujjatlar markazi ---------- */", ""),
   "Nomlar: «Yozishmalar» va «Hujjat chiqarish» (foydalanuvchi matnlarida «Portal» / «Hujjatlar markazi» yo'q)")
ok((ROOT / "docs" / "modullar.md").is_file(), "docs/modullar.md mavjud")

print(f"\n{'Hammasi o`tdi' if not fails else str(fails) + ' ta XATO'}".replace("`", "'"))
sys.exit(1 if fails else 0)
