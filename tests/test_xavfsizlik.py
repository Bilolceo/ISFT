"""Xavfsizlik va izchillik regressiyasi (2026-11 ko'rib chiqish topilmalari). Har bir blok bitta topilmani qamraydi:

  1. Portal — yozish amallari (qaytarib olish, yopish, muddat, yo'naltirish, o'ziga olish, talabalar ro'yxati) xodim ocha olmaydigan xatda 403;
  2. Talabalar ko'lami — yagona qoida (rbac.Ctx.student_scope): tyutor faqat biriktirilgan guruhlar, sirtqi faqat sirtqi talabalar;
  3. Murojaatlar — navbati yo'q bo'limga yo'naltirilmaydi, boshqa bo'lim murojaatini yopib bo'lmaydi; nosozlik 404; tadbir QR;
  4. Hayfsan buyrug'i — «Buyruqlar»da bevosita tuzilgani ham imzolanganda intizomiy yozuvni «amalda» qiladi;
  5. Parol o'zgarsa Telegram ulanishi uziladi;
  7. Xodim ↔ akkaunt bog'lanishi ism tengligi bo'yicha emas (adashlar, nomi o'zgartirilgan akkaunt);
  8. AI agent takliflari har kuni takrorlanmaydi, takroriy topshiriq yaratilmaydi;
  9. Qo'ng'iroqcha va «Mening vazifalarim» — bitta yig'uvchi;
 10. Rektor suhbatda «Bugun nechta xodim ta'tilda?» savoliga jamlangan javob oladi (ism-shariflarsiz);
 11. Kiruvchi xatlar sarlavhasi (kotib), amaliyot kundaligi sanasi.
(6 — Qabul buyrug'i to'plami: tests/test_qabul.py; KPI maqsadlari: tests/test_rejalar.py.)

Ishga tushirish: ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_xavfsizlik.py
"""
import datetime as dt, json, os, pathlib, sqlite3, sys, time
import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DB = os.environ.get("ISFT_CORE_DB") or str(ROOT / "data" / "jarvis.db")
PW = "Isft2026"
N = [0]
STAMP = int(time.time())

def ok(cond, msg):
    N[0] += 1; print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid, pw=PW):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": pw}); assert r.status_code == 200, (uid, r.text)
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

def uid(role): return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))
def post(c, path, body=None): return c.post(path, json=body if body is not None else {})
def strings(x, out=None):
    """JSON ichidagi barcha satrlar (ism-sharif sizib chiqishini tekshirish uchun)."""
    out = set() if out is None else out
    if isinstance(x, dict):
        for v in x.values(): strings(v, out)
    elif isinstance(x, list):
        for v in x: strings(v, out)
    elif isinstance(x, str): out.add(x)
    return out

rektor, akad, reg, cc, kotib, ithead, itstaff = S(2), S(18), S(17), S(23), S(20), S(21), S(22)
TODAY = dt.date.fromisoformat(rektor.get("/api/me").json()["today"])

# =============================================================================================
print("— 1. Portal: yozish amallari ham «faqat shaxsan tegishli xat» qoidasiga bo'ysunadi —")
def thread(c, tag, to, **kw):
    r = post(c, "/api/portal/threads", {"subject": f"Xavfsizlik testi {tag} {STAMP}", "body": f"Sinov xati {tag}.", "to": to, **kw})
    assert r.status_code == 200, r.text
    return r.json()["id"]
due = (TODAY + dt.timedelta(days=5)).isoformat()
T1 = thread(akad, "kiruvchi", ["talabalar"], due=due)                     # Registrator ofisiga kelgan, biriktirilmagan
ok(cc.get(f"/api/portal/threads/{T1}").status_code == 403, "Call-markaz operatori (xodim) biriktirilmagan xatni ocholmaydi (403)")
ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 403, "…va uni «o'ziga olib» o'qiladigan qila olmaydi (403)")
ok(q1("SELECT assignee FROM portal_recipients WHERE thread_id=? AND unit='talabalar'", (T1,)) is None, "ijrochi tayinlanmadi")
ok(post(cc, f"/api/portal/threads/{T1}/forward", {"units": ["akademik", "sirtqi"], "note": "x"}).status_code == 403, "…yo'naltira olmaydi (403)")
ok(post(cc, f"/api/portal/threads/{T1}/archive", {"on": True}).status_code == 403, "…arxivlay olmaydi (403)")
ok(post(cc, f"/api/portal/threads/{T1}/students/mark", {"ids": [1], "status": "bajarildi"}).status_code == 403, "…talabalar ijrosini belgilay olmaydi (403)")
ok(cc.get(f"/api/portal/threads/{T1}").status_code == 403, "urinishlardan keyin ham xat yopiq")
ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 200 and cc.get(f"/api/portal/threads/{T1}").status_code == 200,
   "bo'lim rahbari biriktirgach — xodim ochadi")
ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": None}).status_code == 200 and post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 200,
   "o'ziga biriktirilgan (shaxsan tegishli) xatni bo'shatib, qayta olishi mumkin")
T2 = thread(rektor, "rektoratdan", ["akademik"], due=due)                # rektorat yuborgan — kotib (rektorat xodimi) ga tegishli emas
ok(kotib.get(f"/api/portal/threads/{T2}").status_code == 403, "Rektorat kotibi rektor yuborgan xatni ocholmaydi (403)")
n_rcp = q1("SELECT COUNT(*) FROM portal_recipients WHERE thread_id=?", (T2,))
for path, body, nm in ((f"/api/portal/threads/{T2}/recall", {"note": "x"}, "qaytarib olish"), (f"/api/portal/threads/{T2}/close", {"note": "x"}, "yopish"),
                       (f"/api/portal/threads/{T2}/due", {"due": (TODAY + dt.timedelta(days=9)).isoformat()}, "muddatni o'zgartirish"),
                       (f"/api/portal/threads/{T2}/students", {"students": [1]}, "talaba qo'shish"),
                       (f"/api/portal/threads/{T2}/review", {"unit": "akademik", "decision": "accept"}, "javobni ko'rib chiqish")):
    ok(post(kotib, path, body).status_code == 403, f"kotib ocha olmaydigan xatda «{nm}» → 403")
ok(q("SELECT status, due FROM portal_threads WHERE id=?", (T2,))[0] == ("ochiq", due) and q1("SELECT COUNT(*) FROM portal_recipients WHERE thread_id=?", (T2,)) == n_rcp,
   "xat o'zgarmadi: ochiq, muddat va qabul qiluvchilar joyida")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE user_id=20 AND allowed=0 AND action LIKE 'portal: xatni qaytarib olish' AND ts>=?", (TODAY.isoformat(),)) >= 1, "rad etilgan urinish auditda")
ok(post(rektor, f"/api/portal/threads/{T2}/close", {"note": "test"}).status_code == 200 and post(rektor, f"/api/portal/threads/{T2}/reopen").status_code == 200, "rahbar (rektor) yopadi va qayta ochadi")
ok(post(kotib, f"/api/portal/threads/{T2}/reopen").status_code == 403, "kotib qayta ocholmaydi (403)")
ok(post(rektor, f"/api/portal/threads/{T2}/recall", {"note": "test yakuni"}).status_code == 200, "yuboruvchi rahbar qaytarib oladi")
post(akad, f"/api/portal/threads/{T1}/close", {"note": "test yakuni"})

# =============================================================================================
print("— 2. Talabalar ko'lami: yagona qoida (tyutor — biriktirilgan guruhlar, sirtqi — sirtqi talabalar) —")
from app import rbac
TY = uid("tyutor"); SIR = uid("sirtqi")
tyu, sir = S(TY), S(SIR)
tu = dict(zip(("id", "faculty_id"), q("SELECT id, faculty_id FROM users WHERE id=?", (TY,))[0]))
c_ty = rbac.Ctx({"id": TY, "faculty_id": tu["faculty_id"], "department_id": None, "teacher_id": None, "full_name": "t"}, rbac.ROLES["tyutor"])
c_si = rbac.Ctx({"id": SIR, "faculty_id": None, "department_id": None, "teacher_id": None, "full_name": "s"}, rbac.ROLES["sirtqi"])
ok("tutor_groups" in c_ty.student_scope("s") and "faculty_id" not in c_ty.student_scope("s"), "rbac: tyutor ko'lami — tutor_groups (fakultet emas)")
ok(c_si.student_scope("s") == "s.study_form='sirtqi'", "rbac: sirtqi ko'lami — faqat sirtqi ta'lim shakli")
from app import student_ops as OPSM, reyting as RT, documents as DOCS, orders as ORDM
for c_ in (c_ty, c_si):
    base = c_.student_scope("s")
    ok(OPSM._scope_sql(c_, "s") == base and RT.scope_sql(c_, "s", "id") == base and DOCS._sscope(c_, "s") == base,
       f"{c_.role.key}: Talabalar markazi, reyting va hujjatlar — rbac qoidasining o'zi")
ok(ORDM.st_scope(c_si, "s") == c_si.student_scope("s"), "sirtqi: buyruqlar ko'lami — rbac qoidasining o'zi")
all_names = {r[0] for r in q("SELECT full_name FROM students")}
in_ty = {r[0] for r in q("SELECT full_name FROM students WHERE group_id IN (SELECT group_id FROM tutor_groups WHERE user_id=?)", (TY,))}
in_si = {r[0] for r in q("SELECT full_name FROM students WHERE study_form='sirtqi'")}
# tyutor fakultetidagi, lekin unga biriktirilmagan guruh talabasi; kunduzgi talaba (sirtqi bo'lim uchun)
out_ty = q("""SELECT s.id, s.full_name, s.hemis_id, s.group_id FROM students s WHERE s.faculty_id=? AND s.status='faol'
              AND s.group_id NOT IN (SELECT group_id FROM tutor_groups WHERE user_id=?) AND s.full_name NOT IN
              (SELECT full_name FROM students WHERE group_id IN (SELECT group_id FROM tutor_groups WHERE user_id=?)) ORDER BY s.id LIMIT 1""", (tu["faculty_id"], TY, TY))
ok(in_ty and out_ty, f"sinov ma'lumoti: tyutorga {len(in_ty)} talaba biriktirilgan; fakultetida biriktirilmagan guruh talabasi bor")
out_ty = out_ty[0]
out_si = q("SELECT id, full_name, hemis_id, group_id FROM students WHERE study_form='kunduzgi' AND status='faol' AND full_name NOT IN (SELECT full_name FROM students WHERE study_form='sirtqi') ORDER BY id LIMIT 1")[0]

def leaks(cl, scope_names, target, label):
    """Ko'lamdan tashqaridagi talabalar ism-sharifi hech bir yo'l bilan chiqmasin."""
    sur = target[1].split()[0]
    paths = ["/api/section/risk", "/api/section/academic", f"/api/search?q={target[1]}", f"/api/search?q={target[2]}", "/api/ops/cases", f"/api/ops/student/{target[0]}",
             f"/api/portal/students?q={sur}", f"/api/portal/students?group_id={target[3]}", f"/api/portal/datasets/kontingent?q={sur}",
             f"/api/docs/lookup/student?q={sur}", f"/api/reyting/list?q={sur}", f"/api/reyting/student/{target[0]}", f"/api/orders/students?q={sur}",
             f"/api/registrar/discipline?student_id={target[0]}"]
    seen = 0
    for p in paths:
        r = cl.get(p)
        if r.status_code != 200 or "json" not in r.headers.get("content-type", ""): continue
        seen += 1
        js = r.json()
        if p.startswith("/api/search"):      # faqat «Talabalar» guruhi (o'qituvchi/xodim adashlari boshqa guruhda qonuniy chiqishi mumkin)
            js = [g for g in js["groups"] if g["key"] == "talabalar"]
            ok(not ((strings(js) & all_names) - scope_names) and not any(it["id"] == target[0] for g in js for it in g["items"]), f"{label}: /api/search — ko'lamdan tashqari talaba yo'q")
            continue
        bad = (strings(js) & all_names) - scope_names
        ok(not bad and target[1] not in r.text, f"{label}: {p.split('?')[0]} — ko'lamdan tashqari talaba yo'q" + (f" (sizib chiqdi: {sorted(bad)[:2]})" if bad else ""))
    ok(seen >= 4, f"{label}: {seen} ta manba tekshirildi")
leaks(tyu, in_ty, out_ty, "tyutor")
leaks(sir, in_si, out_si, "sirtqi")
ok(tyu.post("/api/portal/students/lookup", json={"ids": [out_ty[0]], "hemis": [out_ty[2]]}).text.find(out_ty[1]) < 0, "tyutor: Portal talaba qidiruvi (id/HEMIS) — biriktirilmagan talaba chiqmaydi")
ok("Biriktirilgan guruhlar" in c_ty.scope_label(sqlite3.connect(f"file:{DB}?mode=ro", uri=True)), "tyutor ko'lami yorlig'i: «Biriktirilgan guruhlar (N ta)»")

# =============================================================================================
print("— 3. Murojaatlar: navbat egasi, holat o'zgartirish, nosozlik, tadbir QR —")
from app import service as SV
ok("Buxgalteriya bo'limi" not in SV.RECEIVING_UNITS and "Ma'naviyat va ma'rifat bo'limi" not in SV.RECEIVING_UNITS and "Registrator ofisi" in SV.RECEIVING_UNITS,
   "navbatni ocha oladigan bo'limlar: Buxgalteriya va Ma'naviyat yo'q")
ok(all(SV.route_unit(SV.classify(t)[1])[0] in SV.RECEIVING_UNITS for t in ("kontrakt to'lovi cheki qabul qilinmadi", "ijara turar joy kerak", "lms ochilmayapti", "ma'lumotnoma kerak", "boshqa savol")),
   "har qanday murojaat navbati bor bo'limga tushadi")
r = httpx.post(B + "/api/public/request", json={"text": f"Kontrakt to'lovi chekini qayerga topshiraman? (xavfsizlik testi {STAMP})"}).json()
RID = int(r["number"].split("-")[1])
row = q("SELECT unit, category, route_note FROM requests WHERE id=?", (RID,))[0]
ok(r["unit"] == "Registrator ofisi" and row[0] == "Registrator ofisi" and row[1] == "To'lov / kontrakt" and "Buxgalteriya" in (row[2] or ""),
   "to'lov murojaati: egasi — Registrator ofisi, izohda mas'ul bo'lim (Buxgalteriya)")
ok(RID in reg.get("/api/svc/overview").json()["requests"]["queue"]["unit"], "Registrator ofisi navbatida ko'rinadi (egasiz qolmadi)")
ok(q1("SELECT COUNT(*) FROM requests WHERE status IN ('yangi','jarayonda') AND assignee_user IS NULL AND unit IN ('Buxgalteriya bo''limi','Ma''naviyat va ma''rifat bo''limi')") == 0,
   "bazada navbati yo'q bo'limda egasiz ochiq murojaat qolmagan")
ok(post(ithead, f"/api/svc/requests/{RID}/status", {"status": "hal qilindi"}).status_code == 403 and post(akad, f"/api/svc/requests/{RID}/status", {"status": "jarayonda"}).status_code == 403,
   "boshqa bo'lim (AT boshlig'i, Akademik) Registrator murojaatini yopa/ola olmaydi (403)")
ok(q1("SELECT status FROM requests WHERE id=?", (RID,)) == "yangi", "murojaat holati o'zgarmadi")
ok(post(reg, f"/api/svc/requests/{RID}/status", {"status": "javob berildi"}).status_code == 400, "«javob berildi» javob matnisiz → 400")
ok(post(reg, f"/api/svc/requests/{RID}/status", {"status": "javob berildi", "answer": "Chek Registrator ofisiga (104-xona) topshiriladi."}).status_code == 200
   and q("SELECT status, answer FROM requests WHERE id=?", (RID,))[0][0] == "javob berildi", "egasi bo'lgan bo'lim javob berdi")
ok(post(rektor, f"/api/svc/requests/{RID}/status", {"status": "hal qilindi"}).status_code == 200, "rahbariyat (rektor) har qanday murojaatni yopa oladi")
ok(post(reg, "/api/svc/requests/99999999/status", {"status": "hal qilindi"}).status_code == 404, "mavjud bo'lmagan murojaat → 404")
xo = S(uid("xojalik"))
ok(post(xo, "/api/svc/tickets/99999999/status", {"status": "hal qilindi"}).status_code == 404, "mavjud bo'lmagan nosozlik holati → 404 (avval ok qaytardi)")
ok(post(xo, "/api/svc/tickets/1/status", {"status": "yoq-holat"}).status_code == 400, "noto'g'ri holat → 400")
ok(post(reg, "/api/svc/incidents/99999999/notify", {"text": "x" * 30}).status_code == 404, "mavjud bo'lmagan hodisaga xabar → 404")
ys = S(uid("prorektor_yoshlar"))
ok(post(ys, "/api/svc/events/99999999/open").status_code == 404 and q1("SELECT COUNT(*) FROM event_qr WHERE event_id=99999999") == 0, "mavjud bo'lmagan tadbirga QR ochilmaydi (404, yozuv yaratilmadi)")
cols = {r[1] for r in q("PRAGMA table_info(events)")}
past = q1("SELECT id FROM events WHERE date<? ORDER BY id LIMIT 1", (TODAY.isoformat(),))
if past:
    was = q1("SELECT open FROM event_qr WHERE event_id=?", (past,))
    ok(post(ys, f"/api/svc/events/{past}/open").status_code == 409 and q1("SELECT open FROM event_qr WHERE event_id=?", (past,)) == was, "o'tgan kungi tadbirga ro'yxat ochilmaydi (409)")
if "status" in cols:
    EV = w("INSERT INTO events(title,date,kind,participants,status) VALUES(?,?,?,?,?)", (f"Xavfsizlik testi tadbiri {STAMP}", TODAY.isoformat(), "Ma'naviy", 0, "tasdiqlashda"))
    ok(post(ys, f"/api/svc/events/{EV}/open").status_code == 409, "tasdiqlanmagan tadbirga (bugun bo'lsa ham) ro'yxat ochilmaydi (409)")
    w("UPDATE events SET status='tasdiqlangan' WHERE id=?", (EV,))
    ok(post(ys, f"/api/svc/events/{EV}/open").status_code == 200 and q1("SELECT open FROM event_qr WHERE event_id=?", (EV,)) == 1, "tasdiqlangan tadbir, o'z kunida — ochiladi")
    ok(post(ys, f"/api/svc/events/{EV}/close").status_code == 200 and q1("SELECT open FROM event_qr WHERE event_id=?", (EV,)) == 0, "yopiladi")
    w("DELETE FROM event_qr WHERE event_id=?", (EV,)); w("DELETE FROM events WHERE id=?", (EV,))

# =============================================================================================
print("— 4. Hayfsan buyrug'i: bevosita «Buyruqlar»da tuzilgani ham imzolanganda intizomiy yozuvni «amalda» qiladi —")
pro = S(uid("prorektor_oquv"))
hs = q1("""SELECT s.id FROM students s WHERE s.status='faol' AND s.study_form='kunduzgi' AND s.id NOT IN (SELECT student_id FROM discipline)
           AND s.id NOT IN (SELECT i.student_id FROM order_students i JOIN orders o ON o.id=i.order_id WHERE o.status IN ('loyiha','yuborilgan','kelishilgan') AND i.student_id IS NOT NULL)
           ORDER BY s.id DESC LIMIT 1""")
r = reg.post("/api/orders", json={"kind": "hayfsan", "students": [{"student_id": hs, "data": {"reason": "ichki tartib qoidalarini buzgani (xavfsizlik testi)"}}]})
ok(r.status_code == 200, f"Registrator «Buyruqlar»da hayfsan loyihasini bevosita tuzdi ({r.status_code})")
OID = r.json()["id"]
ok(q1("SELECT COUNT(*) FROM discipline WHERE student_id=?", (hs,)) == 0, "imzogacha intizomiy yozuv yo'q")
assert reg.post(f"/api/orders/{OID}/submit").status_code == 200
if pro.post(f"/api/orders/{OID}/forward").status_code not in (200, 400, 409): raise SystemExit("forward")
sg = rektor.post(f"/api/orders/{OID}/sign")
ok(sg.status_code == 200, f"rektor imzoladi: {sg.json().get('reg_no')}")
d = q("SELECT status, doc_reg, kind FROM discipline WHERE student_id=?", (hs,))
ok(d == [("amalda", f"BUYRUQ#{OID}", "hayfsan")], f"imzo bilan hayfsan «amalda» qayd etildi: {d}")
ok(OPSM.sync_discipline(sqlite3.connect(DB)) == 0 and q1("SELECT COUNT(*) FROM discipline WHERE student_id=?", (hs,)) == 1, "qayta sinxronlash yangi yozuv qo'shmaydi (idempotent)")
rd = reg.get(f"/api/registrar/discipline?student_id={hs}")
ok(rd.status_code == 200 and '"amalda"' in rd.text.replace(" ", ""), "intizomiy choralar ro'yxatida (Registrator) hayfsan «amalda»")
ok(not any(t.get("key") in ("reprimand", "leave_order") for t in reg.get("/api/docs/catalog").json()), "Hujjatlar markazi katalogida hayfsan taqdimnomasi / ta'til buyrug'i yo'q")
r = reg.post("/api/docs/issue", json={"key": "reprimand", "params": {"target": f"s:{hs}"}})
ok(r.status_code in (400, 403, 422) and q1("SELECT COUNT(*) FROM documents WHERE kind='reprimand' AND created_at>=?", (TODAY.isoformat(),)) == 0,
   f"Hujjatlar markazida hayfsan taqdimnomasi tuzilmaydi ({r.status_code}) — yagona yo'l «Buyruqlar»")

# =============================================================================================
print("— 5. Parol o'zgarsa Telegram ulanishi uziladi —")
TG = 7_000_000_000 + STAMP % 1000
def link(u): w("UPDATE users SET telegram_id=? WHERE id=?", (TG + u, u))
def linked(u): return q1("SELECT telegram_id FROM users WHERE id=?", (u,))
U1 = uid("xarid")
link(U1)
r = post(ithead, f"/api/accounts/{U1}/demo-password").json()
ok(r.get("telegram_unlinked") is True and linked(U1) is None and "Telegram" in r["message"], "sinov parolini tiklash: Telegram uzildi, administratorga xabar berildi")
link(U1)
r = post(ithead, f"/api/accounts/{U1}/reset-password").json()
ok(r.get("telegram_unlinked") is True and linked(U1) is None and r.get("password") and "Telegram" in r["message"], "parolni tiklash: Telegram uzildi, xabarda aytildi")
x = S(U1, r["password"])
link(U1)
r2 = post(x, "/api/me/password", {"current": r["password"], "new": "Yangi2026parol"}).json()
ok(r2.get("ok") and r2.get("telegram_unlinked") is True and linked(U1) is None and "Telegram" in r2["message"], "o'zi parolni almashtirdi: Telegram uzildi, foydalanuvchiga aytildi")
r3 = post(x, "/api/me/password", {"current": "Yangi2026parol", "new": PW}).json()
ok(r3.get("ok") and r3.get("telegram_unlinked") is False, "ulanmagan akkaunt: telegram_unlinked=false (demo parol tiklandi)")
ok(rbac.pin_fp("a") != rbac.pin_fp("b") and rbac.pin_fp("a") == rbac.pin_fp("a"), "bot: ulanish parol izi bilan bog'lanadi (parol o'zgarsa — qayta tasdiqlash)")
ok(q1("SELECT COUNT(*) FROM audit_log WHERE action IN ('akkauntlar: parol tiklandi','parol o''zgartirildi') AND detail LIKE '%Telegram uzildi%' AND ts>=?", (TODAY.isoformat(),)) >= 2, "auditda «Telegram uzildi» qaydi")

# =============================================================================================
print("— 7. Xodim ↔ akkaunt: barqaror bog'lanish (ism tengligi emas) —")
from app import staff_absence as SA
m = sqlite3.connect(":memory:"); m.row_factory = sqlite3.Row
m.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, full_name TEXT, role TEXT, teacher_id INT, active INT DEFAULT 1);
                   CREATE TABLE staff(id INTEGER PRIMARY KEY, full_name TEXT); CREATE TABLE teachers(id INTEGER PRIMARY KEY, full_name TEXT);""")
m.executescript(SA.SCHEMA)
m.executemany("INSERT INTO staff(id,full_name) VALUES(?,?)", [(1, "Aliyev Vali"), (2, "Karimova Dilnoza"), (3, "Karimova Dilnoza"), (4, "Usmonov Jasur"), (5, "Salimov Anvar")])
m.executemany("INSERT INTO users(id,full_name,role) VALUES(?,?,?)", [(1, "Buxgalter: Aliyev Vali", "buxgalteriya"), (2, "Kutubxonachi: Karimova Dilnoza", "oqituvchi"),
                                                                    (3, "Muhandis: Usmonov Jasur", "it_staff"), (4, "Laborant: Usmonov Jasur", "it_staff"),
                                                                    (5, "Xo'jalik bo'limi", "xojalik"), (6, "Yangi xodim: Toshev Bek", "it_staff")])
U = lambda i: dict(m.execute("SELECT * FROM users WHERE id=?", (i,)).fetchone())
ok(SA.user_link(m, U(1))["staff_id"] == 1, "bir qiymatli ism: akkaunt o'z xodim yozuviga bog'landi")
ok(SA.user_link(m, U(2))["staff_id"] is None, "ikki adash xodim: «o'z» yozuvi yo'q (birovning kasallik varaqasi ochilmaydi)")
ok(SA.user_link(m, U(3))["staff_id"] is None and SA.user_link(m, U(4))["staff_id"] is None, "bir ismli ikki akkaunt: hech biri bog'lanmaydi")
ok(SA.user_link(m, U(5))["staff_id"] is None, "bo'lim akkaunti (shaxs ismi yo'q) bog'lanmaydi")
m.execute("UPDATE users SET full_name='Buxgalter: Aliyeva Vali' WHERE id=1")
ok(SA.user_link(m, U(1))["staff_id"] == 1, "bog'langan akkaunt nomi o'zgarsa ham bog'lanish saqlanadi (barqaror id)")
m.execute("UPDATE users SET full_name='Yangi xodim: Salimov Anvar' WHERE id=6"); SA.lock_user_link(m, 6)     # accounts.update_account shuni chaqiradi
ok(SA.user_link(m, U(6))["staff_id"] is None, "nomi boshqa xodim ismiga o'zgartirilgan akkaunt uning yozuvlariga ulanmaydi")
m.execute("INSERT INTO users(id,full_name,role) VALUES(7,'Hisobchi: Aliyev Vali','buxgalteriya')")
ok(SA.user_link(m, U(7))["staff_id"] is None, "band xodim yozuviga ikkinchi akkaunt bog'lanmaydi")
# jonli server: akkaunt nomini boshqa xodim ismiga o'zgartirish
victim = q("""SELECT a.id, st.full_name FROM staff_absences a JOIN staff st ON st.id=a.staff_id WHERE a.status='faol'
              AND (SELECT COUNT(*) FROM staff s2 WHERE s2.full_name=st.full_name)=1 AND st.id NOT IN (SELECT staff_id FROM user_staff WHERE staff_id IS NOT NULL)
              AND NOT EXISTS(SELECT 1 FROM users u WHERE u.full_name LIKE '%' || st.full_name) ORDER BY a.id LIMIT 1""")
if victim:
    AID, vname = victim[0]
    nu = post(ithead, "/api/accounts", {"position": f"Sinov xodimi {STAMP}", "person": "Sinovov Sinov Sinovovich", "role": "xarid", "unit": "xarid"}).json()
    ok(nu.get("id"), "sinov akkaunti yaratildi")
    att = S(nu["id"], nu["password"])
    ok(att.get(f"/api/staffabs/{AID}").status_code in (403, 404), "begona akkaunt xodim yo'qligini ocholmaydi")
    r = post(ithead, f"/api/accounts/{nu['id']}/update", {"position": f"Sinov xodimi {STAMP}", "person": vname, "role": "xarid", "unit": "xarid"})
    ok(r.status_code == 200 and q1("SELECT locked FROM user_staff WHERE user_id=?", (nu["id"],)) == 1, "akkaunt nomi boshqa xodim ismiga o'zgartirildi — bog'lash yopildi")
    lst = att.get("/api/staffabs").json()
    ok(att.get(f"/api/staffabs/{AID}").status_code in (403, 404) and AID not in {x.get("id") for x in (lst.get("items") or [])},
       "nomi moslashtirilgan akkaunt baribir o'sha xodimning yo'qligi va hujjatlarini ko'rmaydi")
    post(ithead, f"/api/accounts/{nu['id']}/deactivate")
t15 = S(15)
ok(all(x.get("own") for x in (t15.get("/api/staffabs").json().get("items") or [])), "o'qituvchi (#15): faqat o'z yozuvlari")
ok(t15.get("/api/hr/me").json().get("found") is True, "o'qituvchi o'z shaxsiy ishini (barqaror bog'lanish orqali) ko'radi")

# =============================================================================================
print("— 8. AI agent takliflari: obyekt bo'yicha bitta, har kuni takrorlanmaydi —")
from app import agent_hub as AH
def pend(): return q("SELECT id, key, agent, payload FROM agent_actions WHERE status='taklif' ORDER BY id")
post(rektor, "/api/agents/run")
p0 = pend()
bases = [AH._base(k) for _, k, _, _ in p0 if AH._base(k)]
ok(len(bases) == len(set(bases)), f"har bir obyekt bo'yicha bittadan ochiq taklif ({len(bases)} ta)")
ok(not q("SELECT 1 FROM agent_actions WHERE key LIKE 'ijro:overdue:%:____-__-__' OR key LIKE 'moliya:over:%:____-__-__' OR key LIKE 'hujjat:partner:%:____-__-__' OR key LIKE 'talaba:jiddiy:____-__-__'"),
   "eski (obyekt + sana) kalitlar qolmagan")
# «ertasi kun»: ochiq takliflar kechagi sana bilan yaratilgan deb belgilanadi — skaner yangisini qo'shmasligi kerak
yday = (TODAY - dt.timedelta(days=1)).isoformat()
for i, k, _, _ in p0:
    if AH._base(k): w("UPDATE agent_actions SET key=?, created_at=? WHERE id=?", (f"{AH._base(k)}#{yday}", yday + "T08:00:00", i))
r = post(rektor, "/api/agents/run").json()
p1 = pend()
ok(len([1 for _, k, _, _ in p1 if AH._base(k)]) == len(bases) and {i for i, *_ in p1 if True} >= {i for i, k, _, _ in p0 if AH._base(k)},
   f"keyingi kungi skaner takroriy taklif yaratmadi (ochiq: {len(bases)} ta, o'zgarmadi)")
# eski takrorlarni tozalash (init): 3 kunlik takror → bittasi qoladi
con = sqlite3.connect(DB, timeout=30); con.row_factory = sqlite3.Row
for dd in ("2026-01-01", "2026-01-02", "2026-01-03"):
    con.execute("INSERT INTO agent_actions(key,agent,level,title,detail,status,created_at,payload,result) VALUES(?,?,?,?,?,?,?,?,?)",
                (f"hujjat:partner:99999999:{dd}", "hujjat", 2, "TEST takror", "", "taklif", dd + "T08:00:00", '{"effect":"none"}', ""))
con.commit()
ok(AH.dedupe(con) == 2 and AH.dedupe(con) == 0, "dedupe: 3 ta kunlik takrordan 2 tasi olib tashlandi; qayta chaqirish — 0 (idempotent)")
left = [dict(r) for r in con.execute("SELECT key FROM agent_actions WHERE title='TEST takror'")]
ok(left == [{"key": "hujjat:partner:99999999#2026-01-03"}], f"eng yangisi obyekt kaliti bilan qoldi: {left}")
con.execute("DELETE FROM agent_actions WHERE title='TEST takror'"); con.commit(); con.close()
# «Barchasini tasdiqlash»: bir xil topshiriq taklifi ikki marta tasdiqlansa ham bitta topshiriq
task_p = next(((i, k, a, json.loads(p)) for i, k, a, p in pend() if json.loads(p).get("effect") == "task"), None)
if task_p:
    i, k, a, p = task_p
    n0 = q1("SELECT COUNT(*) FROM tasks")
    dup = w("INSERT INTO agent_actions(key,agent,level,title,detail,status,created_at,payload,result) VALUES(?,?,?,?,?,?,?,?,?)",
            (f"{AH._base(k)}#2026-01-05", a, 2, "TEST takror taklif", "", "taklif", "2026-01-05T08:00:00", json.dumps(p, ensure_ascii=False), ""))
    r1, r2 = post(rektor, f"/api/agents/actions/{i}/approve").json(), post(rektor, f"/api/agents/actions/{dup}/approve").json()
    ok(r1["ok"] and "yaratildi" in r1["result"] and q1("SELECT COUNT(*) FROM tasks") == n0 + 1, "birinchi tasdiq: topshiriq yaratildi")
    ok(r2["ok"] and "takror yaratilmadi" in r2["result"] and q1("SELECT COUNT(*) FROM tasks") == n0 + 1, "ikkinchi (takroriy) tasdiq: yangi topshiriq yaratilmadi")
    ok(post(rektor, "/api/agents/run").json()["new"] == 0 or not any(AH._base(kk) == AH._base(k) for _, kk, _, _ in pend()),
       "topshirig'i ochiq obyekt bo'yicha qayta taklif qilinmaydi")
    w("DELETE FROM agent_actions WHERE id=?", (dup,))
else:
    ok(True, "topshiriq turidagi ochiq taklif yo'q — takror tasdiq sinovi o'tkazib yuborildi")

# =============================================================================================
print("— 9. Qo'ng'iroqcha va «Mening vazifalarim»: bitta yig'uvchi —")
for u in (2, 3, 17, 22, 11, 20, 14, 23):
    c = S(u)
    mw = c.get("/api/mywork").json(); nt = c.get("/api/notifications").json()
    ok(nt["work"]["total"] == mw["counts"]["total"] and nt["work"]["by_source"] == mw["counts"]["by_source"], f"#{u}: qo'ng'iroqchadagi ishlar soni = «Mening vazifalarim» ({mw['counts']['total']})")
    links = [i["link"] for i in mw["items"]]
    ev = ("xat",)       # o'qilmagan xat — hodisa (ish emas); qolgan «ish» yozuvlari mywork elementlaridan
    work_kinds = set(mw["counts"]["by_source"]) | {"buyruq", "agent", "xat_muddat"}
    bad = [n["id"] for n in nt["items"] if n["kind"] in work_kinds and n["kind"] not in ev and not n["id"].startswith(("more-", "agall", "syn")) and n["link"] not in links]
    ok(not bad, f"#{u}: qo'ng'iroqchadagi har bir ish «Mening vazifalarim»da bor {bad[:3]}")
    ag = [i for i in mw["items"] if i["source"] == "agent"]
    nag = [n for n in nt["items"] if n["kind"] == "agent"]
    ok((len(nag) == len(ag)) if len(ag) <= 3 else (len(nag) == 1 and str(len(ag)) in nag[0]["title"]), f"#{u}: AI takliflari soni mos ({len(ag)})")
from app import mywork as MWM
ok(MWM.CACHE_TTL >= 60 and callable(MWM.collect_cached), "qo'ng'iroqcha so'rovi (60 s) uchun xodim bo'yicha qisqa kesh bor")
t0 = time.time(); rektor.get("/api/mywork"); t_full = time.time() - t0
t0 = time.time(); rektor.get("/api/notifications"); t_bell = time.time() - t0
ok(t_bell <= max(t_full * 1.5, 0.5), f"qo'ng'iroqcha keshdan oladi (to'liq yig'ish {t_full:.2f} s, qo'ng'iroqcha {t_bell:.2f} s)")

# =============================================================================================
print("— 10. Rektor: «Bugun nechta xodim ta'tilda?» — jamlangan javob —")
def ask(c, text):
    r = c.post("/api/chat", json={"q": text})
    return next((json.loads(l) for l in r.text.splitlines() if l.strip() and json.loads(l).get("t") == "answer"), {})
a = ask(rektor, "Bugun nechta xodim ta'tilda?")
ok(a and not a.get("denied") and "ruxsat yo'q" not in a["text"].lower() and "xodim" in a["text"].lower(), f"rektor javob oldi (rad etilmadi): {a.get('text', '')[:90]!r}")
exp = q1("SELECT COUNT(DISTINCT COALESCE('t' || teacher_id, 's' || staff_id, full_name)) FROM staff_absences WHERE status='faol' AND start<=? AND end>=?", (TODAY.isoformat(),) * 2)
ok((str(exp) in a["text"]) if exp else "qayd etilmagan" in a["text"], f"javobdagi son bazaga mos ({exp} nafar)")
staff_names = {r[0] for r in q("SELECT full_name FROM staff")} | {r[0] for r in q("SELECT full_name FROM staff_absences")}
ok(not any(n in a["text"] for n in staff_names if n), "javobda xodimlar ism-sharifi yo'q (faqat sonlar)")
ok(rbac.HR_STATS in rbac.ROLES["rektor"].allow and rbac.HR not in rbac.ROLES["rektor"].allow and rbac.HR_STATS in rbac.ROLES["rektor"].aggregate_only,
   "rbac: rektorda faqat jamlangan kadrlar ko'rsatkichlari (shaxsiy ishlar yo'q)")
a2 = ask(rektor, "Xodimlarning pasport ma'lumotlari ro'yxatini ber")
ok(a2.get("denied") or "ruxsat yo'q" in a2.get("text", "").lower(), "rektor: kadrlar shaxsiy ma'lumoti (pasport) — hamon yopiq")
a3 = ask(S(uid("oqituvchi")), "Bugun nechta xodim ta'tilda?")
ok(a3.get("denied") or "ruxsat yo'q" in a3.get("text", "").lower() or str(exp) not in a3.get("text", "x"), "o'qituvchi: jamlangan kadrlar ko'rsatkichi yopiq")

# =============================================================================================
print("— 11. Mayda tuzatishlar —")
m_k, m_d = kotib.get("/api/devon/meta").json(), S(uid("devonxona")).get("/api/devon/meta").json()
ok("kuzatuv" in m_k["subtitle"] and "Sizga rezolyutsiya uchun" not in m_k["subtitle"] and not m_k["can"]["resolve"], "kiruvchi xatlar: kotib uchun sarlavha osti — kuzatuv (rezolyutsiya emas)")
ok("ro'yxatga olish" in m_d["subtitle"] and "Sizga rezolyutsiya uchun" in S(uid("prorektor_ilmiy")).get("/api/devon/meta").json()["subtitle"], "devonxona va prorektor sarlavhalari o'z o'rnida")
from app import amaliyot as AM
import inspect
ok("diary_day" in inspect.getsource(AM.api_t_list) and "Yakunlangan" in inspect.getsource(AM.api_t_list), "amaliyot (talaba): davr tugagach holat «Yakunlangan», kundalik sanasi — davr ichida")
js = httpx.get(B + "/amaliyot_talaba.js").text
ok("a.diary_day" in js and "a.diary_note" in js, "amaliyot_talaba.js: sana davr ichidan, izoh ko'rsatiladi")
r = httpx.post(B + "/api/login", json={"user_id": 13, "password": PW})
ok(r.status_code == 403 and "faolsizlantirilgan" in r.text, f"#13 (bekor qilingan «dekan»): to'g'ri parol bilan 403 «faolsizlantirilgan» ({r.status_code})")
ok(13 not in {u.get("id") for u in httpx.get(B + "/api/users").json()} if httpx.get(B + "/api/users").status_code == 200 else True, "#13 kirish ro'yxatida yo'q")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
