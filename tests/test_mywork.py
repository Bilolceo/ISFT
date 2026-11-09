import os
"""«Mening vazifalarim» (GET /api/mywork): uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_mywork.py
Faqat o'qiydi: API'ga GET so'rovlar, bazaga — faqat o'qish rejimida (havolalar va RBAC'ni solishtirish uchun).
Portal xatlari ochilmaydi (ochish "o'qildi" belgisini qo'yadi) — havolalar bazadan tekshiriladi.
"""
import json, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None

USERS = {1: "kengash", 2: "rektor", 3: "prorektor_oquv", 11: "buxgalteriya", 25: "tyutor (fak1)", 14: "kafedra (kaf4)", 15: "oqituvchi",
         17: "Registrator rahbari", 18: "akademik", 20: "kotib", 21: "IT rahbari", 22: "IT muhandisi", 23: "call-markaz",
         24: "tyutor (fak2)", 31: "kafedra (Biznes boshqaruvi)"}
SOURCES = {"majlis", "portal", "markaz", "hujjat", "agent", "sillabus"}   # sillabus — app/syllabus.py (O'quv dasturlari)
BUCKETS = ["overdue", "today", "week", "later", "none"]
PEND = ("yangi", "o'qilgan")
LEADERS = {"rektor", "prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya", "prorektor_yoshlar"}

def user(uid):
    r = one("SELECT id, role, unit, faculty_id, department_id, full_name FROM users WHERE id=?", (uid,))
    return {"id": r[0], "role": r[1], "unit": r[2], "faculty_id": r[3], "department_id": r[4], "full_name": r[5]}

def head_of(unit):
    r = one("SELECT head_user FROM org_units WHERE key=?", (unit,))
    return r[0] if r else None

def tid_of(it):
    return it["link"].get("thread")

# ---------------------------------------------------------------------------------------------
print("— 0. Kirishsiz so'rov va sahifa fayllari")
ok(httpx.get(B + "/api/mywork").status_code == 401, "kirishsiz /api/mywork → 401")
idx = httpx.get(B + "/").text
ok('data-v="mywork"' in idx and 'id="v-mywork"' in idx and 'src="mywork.js"' in idx, "index.html: menyu, bo'lim va skript ulangan")
ok(httpx.get(B + "/mywork.js").status_code == 200 and httpx.get(B + "/mywork.css").status_code == 200, "mywork.js va mywork.css beriladi")
app_js = httpx.get(B + "/app.js").text
ok("mywork: typeof renderMywork" in app_js and "myworkBadge(set)" in app_js, "app.js: ko'rinish xaritasi va menyu belgisi ulangan")

# institutda dekan lavozimi yo'q (Yevropa modeli): sobiq dekan akkaunti (#13) kira olmaydi
ok(httpx.post(B + "/api/login", json={"user_id": 13, "password": "Isft2026"}).status_code == 403, "#13 sobiq dekan: kirish rad etildi (lavozim bekor qilingan)")
DATA = {}
for uid in USERS:
    c = S(uid)
    r = c.get("/api/mywork")
    ok(r.status_code == 200, f"#{uid} {USERS[uid]}: /api/mywork → 200")
    DATA[uid] = (c, r.json())

# ---------------------------------------------------------------------------------------------
print("\n— 1. Javob shakli, hisoblagichlar va tartib (har bir lavozim)")
for uid, (c, d) in DATA.items():
    its, cn = d["items"], d["counts"]
    keys = {"id", "source", "kind", "title", "sub", "due", "overdue", "priority", "status", "who", "link", "bucket"}
    ok(all(keys <= set(it) for it in its), f"#{uid}: har bir elementda {sorted(keys)}")
    ok(all(it["source"] in SOURCES and it["priority"] in ("high", "mid", "low") and it["bucket"] in BUCKETS for it in its), f"#{uid}: manba/ustuvorlik/guruh qiymatlari to'g'ri")
    ok(len({it["id"] for it in its}) == len(its), f"#{uid}: id'lar takrorlanmaydi")
    ok(all(isinstance(it["link"], dict) and it["link"].get("view") for it in its), f"#{uid}: har bir elementda havola (view) bor")
    ok(cn["total"] == len(its), f"#{uid}: counts.total = {len(its)}")
    for b in ("overdue", "today", "week"):
        ok(cn[b] == sum(it["bucket"] == b for it in its), f"#{uid}: counts.{b} = {cn[b]}")
    ok(cn["overdue"] == sum(bool(it["overdue"]) for it in its), f"#{uid}: overdue bayrog'i guruh bilan mos")
    ok(sum(cn["by_source"].values()) == len(its) and all(cn["by_source"][s] == sum(it["source"] == s for it in its) for s in cn["by_source"]),
       f"#{uid}: by_source yig'indisi to'g'ri {cn['by_source']}")
    ok(all(it["priority"] == "high" for it in its if it["bucket"] in ("overdue", "today")), f"#{uid}: muddati o'tgan/bugungi — yuqori ustuvorlik")
    order = [BUCKETS.index(it["bucket"]) for it in its]
    ok(order == sorted(order), f"#{uid}: tartib — avval muddati o'tganlar, keyin muddat bo'yicha, oxirida muddatsizlar")
    for b in BUCKETS[:4]:
        ds = [str(it["due"]).replace(" ", "T")[:19] for it in its if it["bucket"] == b]
        ds = [x + "T23:59:59" if len(x) == 10 else x for x in ds]
        ok(ds == sorted(ds), f"#{uid}: «{b}» ichida muddat o'sish tartibida")
    ok(all(it["due"] is None for it in its if it["bucket"] == "none") and all(it["due"] for it in its if it["bucket"] != "none"), f"#{uid}: muddatsizlar alohida")

# ---------------------------------------------------------------------------------------------
print("\n— 2. Havolalar haqiqiy va RBAC (boshqa bo'lim ishi ko'rinmaydi)")
for uid, (c, d) in DATA.items():
    u = user(uid); role = u["role"]; me = u["unit"]
    for it in d["items"]:
        L = it["link"]
        if L["view"] == "portal":
            t = one("SELECT id, from_unit, from_user, status FROM portal_threads WHERE id=?", (L["thread"],))
            ok(t is not None and t[3] == "ochiq", f"#{uid} {it['id']}: portal yozishmasi #{L['thread']} mavjud va ochiq")
            part = t[1] == me or one("SELECT 1 FROM portal_recipients WHERE thread_id=? AND unit=? UNION SELECT 1 FROM portal_watchers WHERE thread_id=? AND unit=?",
                                     (t[0], me, t[0], me)) is not None
            ok(part or role in LEADERS, f"#{uid} {it['id']}: yozishma shu xodim bo'limiga tegishli (ochish huquqi bor)")
            if it["who"] == "menga":
                ok(one("SELECT 1 FROM portal_recipients WHERE thread_id=? AND unit=? AND assignee=?", (t[0], me, uid)) is not None,
                   f"#{uid} {it['id']}: «menga» — xat aynan shu xodimga biriktirilgan")
            elif it["who"] == "bolimga":
                ok(head_of(me) == uid and one("SELECT 1 FROM portal_recipients WHERE thread_id=? AND unit=? AND assignee IS NULL", (t[0], me)) is not None,
                   f"#{uid} {it['id']}: «bo'limga» — bo'lim rahbari va xat hali biriktirilmagan")
            elif it["who"] == "yuborgan":
                ok(t[2] == uid and t[1] == me, f"#{uid} {it['id']}: «javob kelmadi» — xatni shu xodim yuborgan")
            elif it["who"] == "nazorat":
                rid = int(it["id"][2:])
                z = one("SELECT author_id, state, units FROM portal_resolutions WHERE id=?", (rid,))
                ok(z and z[0] == uid and z[1] == "nazoratda", f"#{uid} {it['id']}: rezolyutsiya muallifi — shu xodim, nazoratda")
                pend = q(f"SELECT unit FROM portal_recipients WHERE thread_id=? AND status IN {PEND}", (L["thread"],))
                ok(any(p[0] in json.loads(z[2]) for p in pend), f"#{uid} {it['id']}: rezolyutsiya ijrosi hali tugamagan")
            else:
                ok(False, f"#{uid} {it['id']}: noma'lum who={it['who']}")
        elif L["view"] == "documents":
            ok(role == "rektor", f"#{uid} {it['id']}: imzo — faqat rektor")
            if L.get("reg"): ok(one("SELECT status FROM documents WHERE reg_no=?", (L["reg"],)) == ("loyiha",), f"#{uid} {it['id']}: hujjat {L['reg']} imzo kutmoqda")
        elif L["view"] == "agents":
            ok(role == "rektor" or role == "kotib" or role.startswith("prorektor_"), f"#{uid} {it['id']}: AI takliflar — faqat rahbariyat")
        elif L["view"] == "tasks":
            if it["kind"] == "topshiriq":
                tid = int(it["id"][2:])
                t = one("SELECT assignee_role, assignee_user, status, assignee FROM tasks WHERE id=?", (tid,))
                ok(t and t[2] not in ("bajarildi", "qoralama"), f"#{uid} {it['id']}: topshiriq mavjud va ochiq")
                ok(t[0] == role or t[1] == uid or one("SELECT 1 FROM tasks WHERE id=? AND unit IS NOT NULL", (tid,)) is not None,
                   f"#{uid} {it['id']}: topshiriq shu lavozim/xodimga tegishli")
            if L.get("meeting"): ok(one("SELECT 1 FROM meetings WHERE id=?", (L["meeting"],)) is not None, f"#{uid} {it['id']}: majlis #{L['meeting']} mavjud")
        elif L["view"] == "ops":
            ok(role in ("call_center", "tyutor", "talabalar"), f"#{uid} {it['id']}: Talabalar markazi navbati — faqat o'z navbati bor lavozimlarda")
            if L.get("student"): ok(one("SELECT 1 FROM students WHERE id=?", (L["student"],)) is not None, f"#{uid} {it['id']}: talaba mavjud")
        elif L["view"] == "syllabus":   # O'quv dasturlari (app/syllabus.py) — batafsil testlar: tests/test_syllabus.py
            ok(it["source"] == "sillabus" and role in ("akademik", "prorektor_oquv", "kafedra", "oqituvchi"), f"#{uid} {it['id']}: sillabus — faqat o'quv dasturlari lavozimlarida")
            if L.get("item"):
                s = one("SELECT department_id, teacher_id, status FROM syl_items WHERE id=?", (L["item"],))
                ok(s is not None and s[2] != "tasdiqlangan", f"#{uid} {it['id']}: sillabus #{L['item']} mavjud va yakunlanmagan")
                u = user(uid)
                if role == "kafedra": ok(s[0] == u["department_id"], f"#{uid} {it['id']}: sillabus o'z kafedrasidan")
                if role == "oqituvchi": ok(s[1] == one("SELECT teacher_id FROM users WHERE id=?", (uid,))[0], f"#{uid} {it['id']}: sillabus o'ziga biriktirilgan")
            if L.get("task"):
                ok(one("SELECT 1 FROM syl_tasks WHERE id=?", (L["task"],)) is not None, f"#{uid} {it['id']}: kafedra so'rovi #{L['task']} mavjud")
                if role == "kafedra": ok(one("SELECT 1 FROM syl_task_units WHERE task_id=? AND department_id=?", (L["task"], user(uid)["department_id"])) is not None,
                                         f"#{uid} {it['id']}: so'rov o'z kafedrasiga yuborilgan")
            if L.get("status"): ok(L["status"] in ("soralgan", "jarayonda", "qaytarilgan", "tekshiruvda", "kelishuvda", "tasdiqlangan", "overdue"), f"#{uid} {it['id']}: holat filtri to'g'ri")
        else:
            ok(False, f"#{uid} {it['id']}: kutilmagan havola {L}")

# ---------------------------------------------------------------------------------------------
print("\n— 3. Lavozimlar bo'yicha")
c, d = DATA[2]; its = d["items"]
nres = one(f"""SELECT COUNT(*) FROM portal_resolutions z JOIN portal_threads t ON t.id=z.thread_id WHERE z.author_id=2 AND z.state='nazoratda' AND t.status='ochiq'
               AND EXISTS(SELECT 1 FROM json_each(z.units) j JOIN portal_recipients r ON r.thread_id=z.thread_id AND r.unit=j.value WHERE r.status IN {PEND})""")[0]
ok(nres > 0 and sum(it["kind"] == "rezolyutsiya" for it in its) == nres, f"rektor: rezolyutsiyalar nazorati — {nres} ta (bazadagi bilan teng)")
ndoc = one("SELECT COUNT(*) FROM documents WHERE status='loyiha'")[0]
ok(sum(it.get("count") or 1 for it in its if it["source"] == "hujjat") == ndoc, f"rektor: imzo kutayotgan hujjatlar — {ndoc} ta")
ag = c.get("/api/agents").json()
napp = len([p for p in ag["pending"] if p.get("can_approve")])
ok(sum(it.get("count") or 1 for it in its if it["source"] == "agent") == napp, f"rektor: AI agent takliflari — {napp} ta (agentlar sahifasidagi bilan teng)")
ok(not any(it["source"] == "markaz" for it in its), "rektor: Talabalar markazi navbati yo'q (jamlangan ko'rinish)")

c, d = DATA[20]
ag = c.get("/api/agents").json(); napp = len([p for p in ag["pending"] if p.get("can_approve")])
ok(sum(it.get("count") or 1 for it in d["items"] if it["source"] == "agent") == napp, f"kotib: faqat o'zi tasdiqlaydigan agent takliflari — {napp} ta")
ok(not any(it["source"] == "hujjat" for it in d["items"]), "kotib: hujjat imzosi yo'q")

for uid in (3,):
    c, d = DATA[uid]
    ag = c.get("/api/agents").json(); napp = len([p for p in ag["pending"] if p.get("can_approve")])
    ok(sum(it.get("count") or 1 for it in d["items"] if it["source"] == "agent") == napp, f"prorektor_oquv: agent takliflari — {napp} ta")

for uid in (22, 23):
    u = user(uid)
    want = {r[0] for r in q(f"""SELECT r.thread_id FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id
                                WHERE r.unit=? AND r.assignee=? AND t.status='ochiq' AND r.status IN {PEND}""", (u["unit"], uid))}
    got = {tid_of(it) for it in DATA[uid][1]["items"] if it["source"] == "portal" and it["who"] == "menga"}
    ok(want and got == want, f"#{uid} {USERS[uid]}: biriktirilgan xatlar ko'rinadi {sorted(want)}")
    for other in DATA:     # shu bo'limdagi boshqa xodimlar (rahbar ham) bu xatni o'z ishi sifatida ko'rmaydi
        if other == uid or user(other)["unit"] != u["unit"]: continue
        leak = {tid_of(it) for it in DATA[other][1]["items"] if it["source"] == "portal" and it["who"] in ("menga", "bolimga")} & want
        ok(not leak, f"#{uid} ga biriktirilgan xat bo'limdoshi #{other} ning «menga/bo'limga» ro'yxatida yo'q")

lms = one("SELECT t.id FROM portal_threads t JOIN portal_recipients r ON r.thread_id=t.id WHERE r.unit='it' AND r.assignee=22 AND t.subject LIKE '%LMS%'")
ok(lms and any(tid_of(it) == lms[0] and it["who"] == "menga" for it in DATA[22][1]["items"]), f"IT muhandisi (#22): LMS xati (#{lms and lms[0]}) ro'yxatda")

d = DATA[23][1]
today = d["today"]
nq = one("SELECT COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_role='call_center' AND COALESCE(planned_on,'') <= ?", (today,))[0]
mk = [it for it in d["items"] if it["source"] == "markaz"]
ok(mk and sum(it.get("count") or 1 for it in mk) == nq, f"call-markaz: bugungi qo'ng'iroqlar navbati jamlangan — {nq} ta (keyingi kunlarga rejalashtirilganlar hisobga olinmaydi)")
ok(all(it["link"]["view"] == "ops" for it in mk) and len(mk) <= 5, "call-markaz: navbat bir necha qatorga jamlangan (minglab qator emas)")

u = user(24)
nt = one("SELECT COUNT(*) FROM ops_tasks WHERE status='yangi' AND assignee_role='tyutor' AND faculty_id=? AND COALESCE(planned_on,'') <= ?", (u["faculty_id"], DATA[24][1]["today"]))[0]
ok(sum(it.get("count") or 1 for it in DATA[24][1]["items"] if it["source"] == "markaz") == nt, f"tyutor (fak{u['faculty_id']}): faqat o'z fakulteti navbati — {nt} ta")
for uid in (2, 3, 18, 21, 22, 31, 11, 1):
    ok(not any(it["source"] == "markaz" for it in DATA[uid][1]["items"]), f"#{uid} {USERS[uid]}: Talabalar markazi navbati ko'rinmaydi (o'z navbati yo'q)")

# kafedra: o'z majlis topshiriqlari; boshqa kafedra topshirig'i ko'rinmaydi
k14 = {int(it["id"][2:]) for it in DATA[14][1]["items"] if it["kind"] == "topshiriq"}
want14 = {r[0] for r in q("SELECT id FROM tasks WHERE assignee_role='kafedra' AND status NOT IN ('bajarildi','qoralama') AND assignee LIKE '%Buxgalteriya hisobi%'")}
ok(k14 == want14, f"kafedra (kaf4): o'z majlis topshiriqlari ko'rinadi {sorted(want14)}")
k31 = [it for it in DATA[31][1]["items"] if it["source"] == "majlis"]
ok(not any("Buxgalteriya hisobi" in it["sub"] for it in k31), "kafedra (Biznes boshqaruvi): boshqa kafedra (Buxgalteriya hisobi) topshiriqlari ko'rinmaydi")
mine31 = {r[0] for r in q("""SELECT id FROM tasks WHERE status NOT IN ('bajarildi','qoralama') AND (assignee_user=31 OR
                              (assignee_role='kafedra' AND assignee LIKE '%Biznes boshqaruvi%'))""")}
ok({int(it["id"][2:]) for it in k31 if it["kind"] == "topshiriq"} == mine31, f"kafedra (Biznes boshqaruvi): o'z topshiriqlari — {len(mine31)} ta")

# IT rahbari: #22 ga biriktirilgan xat rahbarning «bo'limga» ro'yxatida takrorlanmaydi
ok(not any(it["source"] == "portal" and tid_of(it) == (lms and lms[0]) for it in DATA[21][1]["items"]), "IT rahbari: xodimga biriktirilgan xat rahbarning ishlari ro'yxatida yo'q")

# rahbariyatdan boshqasi uchun hujjat/agent manbalari yo'q
for uid in (11, 25, 14, 15, 17, 18, 21, 22, 23, 24, 31, 1):
    ok(not any(it["source"] in ("hujjat", "agent") for it in DATA[uid][1]["items"]), f"#{uid} {USERS[uid]}: imzo va AI takliflari ko'rinmaydi")

# ---------------------------------------------------------------------------------------------
print("\n— 4. Bildirishnomalar bilan muvofiqlik (muddat eslatmalari ishlar ro'yxatida bor)")
for uid in (2, 3, 17, 22, 23, 11, 25):
    c, d = DATA[uid]
    ns = c.get("/api/notifications").json()["items"]
    ths = {tid_of(it) for it in d["items"] if it["source"] == "portal"}
    rem = [n for n in ns if n["kind"] == "xat_muddat" and n["id"][1] in ("m", "b", "y", "n")]
    ok(all(n["link"]["thread"] in ths for n in rem), f"#{uid}: {len(rem)} ta portal muddat eslatmasi «Mening vazifalarim»da ham bor")
    tn = [n for n in ns if n["kind"] in ("topshiriq", "topshiriq_muddat") and n["id"].startswith(("to", "tn"))]
    mids = {it["id"][2:] for it in d["items"] if it["kind"] == "topshiriq"}
    if uid not in (14, 31):
        ok(all(n["id"][2:] in mids for n in tn), f"#{uid}: {len(tn)} ta topshiriq eslatmasi ro'yxatda ham bor")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
