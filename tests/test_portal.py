import os
"""Portal v2: uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_portal.py
Qayta ishga tushirish mumkin (qayta seed shart emas): test o'z yozishmalarini noyob mavzu bilan yaratadi va oxirida yopadi,
qoralama va shablonlarini o'chiradi, tashkiliy tuzilmaga kiritgan o'zgarishlarini (rahbar, kurator) asl holiga qaytaradi.
Demo yozishmalar faqat o'qiladi. Bazaga faqat o'qish rejimida murojaat qilinadi; yagona istisno — kuratorning qayta ishga
tushirishda saqlanishini tekshirish uchun alohida jarayonda `portal.sync_units()` chaqiriladi (server startida ham aynan shu bajariladi).
"""
import datetime as dt, hashlib, io, re, sqlite3, subprocess, sys, time, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"

N = [0]
SOFT = []          # backend xatolari (test davom etadi, oxirida exit 1)

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def soft(cond, msg):
    """Ma'lum backend xatosini tekshiradi: muvaffaqiyatsiz bo'lsa ham test davom etadi, oxirida natija 1."""
    N[0] += 1
    print(("✓ " if cond else "✗ BACKEND XATOSI: ") + msg)
    if not cond: SOFT.append(msg)

NOTES = []
def note(cond, msg):
    """Spetsifikatsiyadan chetlanish (muhokamali): natijaga ta'sir qilmaydi, oxirida ro'yxat chiqadi."""
    print(("✓ " if cond else "⚠ ESLATMA: ") + msg)
    if not cond: NOTES.append(msg)

def S(uid):
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def lst(c, box="inbox", flt="all", q_="", offset=0, limit=100):
    r = c.get("/api/portal/threads", params={"box": box, "flt": flt, "q": q_, "offset": offset, "limit": limit})
    assert r.status_code == 200, f"threads {box}/{flt}/{q_!r}: {r.status_code} {r.text[:300]}"
    return r.json()

def all_items(c, box="inbox", flt="all", q_=""):
    out, off = [], 0
    while True:
        d = lst(c, box, flt, q_, off, 100)
        out += d["items"]; off += 100
        if off >= d["total"]: return out

def item(c, tid, box="inbox", flt="all", q_=""):
    return next((x for x in all_items(c, box, flt, q_) if x["id"] == tid), None)

def has(c, tid, box="inbox", flt="all", q_=""): return item(c, tid, box, flt, q_) is not None

def detail(c, tid):
    r = c.get(f"/api/portal/threads/{tid}"); assert r.status_code == 200, r.text[:300]; return r.json()

def rcp(d, unit): return next((r for r in d["recipients"] if r["unit"] == unit), None)

def post(c, path, body=None): return c.post(path, json=body if body is not None else {})

STAMP = time.strftime("%Y%m%d-%H%M%S")
U = str(int(time.time() * 1000))[-9:]          # noyob so'z qo'shimchasi (FTS uchun)
TODAY = CLK.today()
D2, D3, YDAY = (TODAY + dt.timedelta(days=2)).isoformat(), (TODAY + dt.timedelta(days=3)).isoformat(), (TODAY - dt.timedelta(days=1)).isoformat()
D5, D7 = (TODAY + dt.timedelta(days=5)).isoformat(), (TODAY + dt.timedelta(days=7)).isoformat()
dmy = lambda d: dt.date.fromisoformat(d).strftime("%d.%m.%Y")
dm = lambda d: dt.date.fromisoformat(d).strftime("%d.%m")

rektor, pro, reg, cc, ithead, iteng, akad, sirtqi, buxg, kaf, kadr, mbaza = (S(i) for i in (2, 3, 17, 23, 21, 22, 18, 27, 11, 31, 12, 28))
promol, kotib = S(5), S(20)
AUDIT0 = q("SELECT COALESCE(MAX(id),0) FROM audit_log")[0][0]
MY_THREADS, MY_DRAFTS, MY_TEMPLATES = [], [], []   # (client, id)
DIRS_TO_DROP = []                                  # test yaratgan topshiriqlar (oxirida bazadan o'chiriladi)
ORG_RESTORE = {}     # bo'lim kaliti → asl {"head_user", "curator"} (test oxirida qaytariladi)

def new_thread(c, tag, to, due=None, body=None, **kw):
    r = post(c, "/api/portal/threads", {"subject": f"Portal v2 test {tag} {STAMP}", "body": body or f"Test xati {tag} ({STAMP}).",
                                        "to": to, "due": due, **kw})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]; MY_THREADS.append(tid)
    return tid, r.json()["ref_no"]

def cleanup():
    print("\n— Tozalash —")
    for tid in MY_THREADS:
        st = q("SELECT status FROM portal_threads WHERE id=?", (tid,))
        if st and st[0][0] == "ochiq":
            r = post(akad, f"/api/portal/threads/{tid}/close", {"note": "test yakuni"})
            if r.status_code == 403: r = post(rektor, f"/api/portal/threads/{tid}/close", {"note": "test yakuni"})   # akad yuboruvchi bo'lmagan xatlar
            print(f"  yozishma #{tid} yopildi: {r.status_code}")
    for c, did in MY_DRAFTS:
        c.delete(f"/api/portal/drafts/{did}")
    for key, orig in ORG_RESTORE.items():
        r = rektor.put(f"/api/portal/org/{key}", json=orig)
        print(f"  tuzilma «{key}» asl holiga qaytarildi: {r.status_code} {orig}")
    for c, tid in MY_TEMPLATES:
        c.delete(f"/api/portal/templates/{tid}")
    con = sqlite3.connect(DB, timeout=30)       # test fayllari test xatlariga ilova qilingan bo'lsa — ilova yozuvi olib tashlanadi (fayl o'chirilishi uchun)
    con.execute("DELETE FROM portal_attach WHERE file_id IN (SELECT id FROM portal_files WHERE name LIKE ?)", (f"%{U}%",))
    for did in DIRS_TO_DROP:
        for tb in ("task_log", "task_msgs"): con.execute(f"DELETE FROM {tb} WHERE task_id=?", (did,))
        con.execute("DELETE FROM tasks WHERE id=? OR parent_id=?", (did, did))
    con.commit(); con.close()
    for fid, uid in q("SELECT id, uploader_id FROM portal_files WHERE name LIKE ? ORDER BY version DESC", (f"%{U}%",)):
        c = {17: reg, 23: cc, 18: akad}.get(uid)
        if c: print(f"  test fayli #{fid} o'chirildi: {c.delete(f'/api/portal/files/{fid}').status_code}")
    left = [t for t in MY_THREADS if q("SELECT status FROM portal_threads WHERE id=?", (t,))[0][0] not in ("yopilgan", "qaytarilgan")]
    print(f"  ochiq qolgan test yozishmalari: {left or 'yo‘q'}")

def students_and_review():
    """v2.2: xatga biriktirilgan talabalar ro'yxati (RBAC), talabalar bo'yicha ijro, javobni ko'rib chiqish (qabul / qaytarish)."""
    # ============================================================== 21. Talabalar ro'yxati
    print("— 21. Talabalar ro'yxati —")
    ok(reg.get("/api/portal/units").json()["students"] is True and rektor.get("/api/portal/units").json()["students"] is False
       and buxg.get("/api/portal/units").json()["students"] is False, "units.students: Registrator — ha, rektor (jamlangan) va buxgalteriya — yo'q")
    ok(kaf.get("/api/portal/units").json()["student_scope"].endswith("kafedrasi"), "kafedra mudiri: ko'lam — o'z kafedrasi")
    sr = reg.get("/api/portal/students", params={"q": "IQT-25"}).json()
    ok(sr["groups"] and all("IQT-25" in g["name"] for g in sr["groups"]), "qidiruv: guruh nomi bo'yicha «butun guruh» takliflari")
    G = sr["groups"][0]
    gs = reg.get("/api/portal/students", params={"group_id": G["id"]}).json()["items"]
    ok(len(gs) == G["n"] and len(gs) >= 11, f"butun guruh: {G['name']} — {len(gs)} ta talaba")
    ok(reg.get("/api/portal/students", params={"q": "a"}).json()["items"] == [], "1 harfli so'rov — bo'sh natija")
    for c, n in ((rektor, "rektor"), (buxg, "buxgalteriya")):
        ok(c.get("/api/portal/students", params={"q": "IQT"}).status_code == 403, f"{n}: talaba qidiruvi 403")
    lk = post(reg, "/api/portal/students/lookup", {"hemis": f"{gs[0]['hemis']}, {gs[1]['hemis']}\n99999999999"}).json()
    ok({x["id"] for x in lk["items"]} == {gs[0]["id"], gs[1]["id"]} and lk["missing"] == ["99999999999"], "HEMIS ID ro'yxati: 2 ta topildi, 1 ta topilmadi")
    ok(post(rektor, "/api/portal/students/lookup", {"ids": [gs[0]["id"]]}).status_code == 403, "rektor: id bo'yicha talaba ma'lumoti 403")
    ten = [x["id"] for x in gs[:10]]
    names = [x["name"] for x in gs[:10]]
    r = post(buxg, "/api/portal/threads", {"subject": f"Portal v2.2 rad {STAMP}", "body": "x", "to": ["talabalar"], "students": ten[:2]})
    ok(r.status_code == 403, "buxgalteriya: talabalar ro'yxatini biriktira olmaydi (403)")
    r = post(kaf, "/api/portal/threads", {"subject": f"Portal v2.2 rad {STAMP}", "body": "x", "to": ["akademik"], "students": ten[:2]})
    ok(r.status_code == 400 and "ko'lamingizda emas" in r.json()["detail"], "kafedra mudiri: boshqa kafedra talabasini biriktira olmaydi (400)")
    T, REF = new_thread(reg, "talabalar", ["prorektor_oquv"], due=D5, body=f"Harbiy ta'lim: yangi guruh ochish (test {U})", kind="xat",
                        students=ten, student_note="Yangi guruhga ko'chirish")
    d = detail(reg, T)["students"]
    ok(d["total"] == 10 and len(d["items"]) == 10 and d["can_view"] and d["can_add"] and not d["can_mark"], "yuboruvchi: 10 ta talaba, qo'shish mumkin, belgilash yo'q")
    ok(all(x["note"] == "Yangi guruhga ko'chirish" and x["exec"] == "kutilmoqda" for x in d["items"]), "har bir talabada izoh va «kutilmoqda» holati")
    it = item(reg, T, "sent")
    ok(it["students"] == {"total": 10, "done": 0, "failed": 0}, "ro'yxatda: students = {total 10, done 0}")
    dp = detail(pro, T)["students"]
    ok(dp["can_view"] and len(dp["items"]) == 10 and dp["can_mark"], "prorektor (qabul qiluvchi, rezolyutsiyasiz): ro'yxat va belgilash huquqi")
    ok(post(pro, f"/api/portal/threads/{T}/resolve", {"text": "Ko'chirilsin, HEMIS yangilansin", "units": ["akademik", "malumotlar_bazasi"],
                                                       "lead": "malumotlar_bazasi", "due": D3}).status_code == 200, "prorektor: rezolyutsiya → Akademik + Ma'lumotlar bazasi")
    dd = detail(reg, T)
    ok(rcp(dd, "prorektor_oquv")["status"] == "yo'naltirilgan", "rezolyutsiya qo'ygan prorektor: o'z holati «yo'naltirilgan» (javob kutilmaydi)")
    ok({e["unit"] for e in dd["students"]["executors"]} == {"akademik", "malumotlar_bazasi"}, "ijrochilar — rezolyutsiya bo'limlari")
    ok(not detail(pro, T)["students"]["can_mark"] and detail(mbaza, T)["students"]["can_mark"] and detail(akad, T)["students"]["can_mark"],
       "rezolyutsiyadan keyin: prorektor belgilamaydi, Ma'lumotlar bazasi va Akademik bo'lim belgilaydi")
    dr = detail(rektor, T)
    ok(dr["students"]["can_view"] is False and dr["students"]["items"] == [] and dr["students"]["total"] == 10 and dr["students"]["groups"] == [{"name": G["name"], "n": 10}],
       "rektor (jamlangan): faqat soni va guruh nomlari")
    ok(not any(n in str(dr) for n in names), "rektor javobida talabalar ismi yo'q")
    ok(kaf.get(f"/api/portal/threads/{T}").status_code == 403, "ishtirokchi bo'lmagan kafedra: yozishma 403")
    # ijro belgilari
    m = post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": ten[:6], "status": "bajarildi", "note": "HT guruhiga ko'chirildi"})
    ok(m.status_code == 200 and m.json()["done"] == 6 and m.json()["pending"] == 4, "Ma'lumotlar bazasi: 6 ta «bajarildi»")
    ok(post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": ten[6:7], "status": "bajarilmadi"}).status_code == 400, "«bajarilmadi» izohsiz — 400")
    ok(post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": ten[6:7], "status": "bajarilmadi", "note": "Qarzdorlik"}).json()["failed"] == 1,
       "«bajarilmadi» izoh bilan")
    ok(post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": ten[:1], "status": "kutilmoqda"}).json()["done"] == 5, "belgini olib tashlash (kutilmoqda)")
    ok(post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": ten[:1], "status": "xato"}).status_code == 400, "noto'g'ri holat — 400")
    ok(post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": [gs[10]["id"]], "status": "bajarildi"}).status_code == 400, "ro'yxatda yo'q talaba — 400")
    for c, n in ((reg, "yuboruvchi"), (pro, "prorektor"), (rektor, "rektor"), (kaf, "kafedra")):
        ok(post(c, f"/api/portal/threads/{T}/students/mark", {"ids": ten[:1], "status": "bajarildi"}).status_code == 403, f"{n}: belgilash 403")
    x = next(i for i in detail(reg, T)["students"]["items"] if i["id"] == ten[6])
    ok(x["exec"] == "bajarilmadi" and x["exec_note"] == "Qarzdorlik" and x["exec_unit"].startswith("Ma'lumotlar") and x["exec_by"], "belgi: kim, qaysi bo'lim, izoh")
    ok(item(reg, T, "sent")["students"] == {"total": 10, "done": 5, "failed": 1}, "ro'yxatdagi progress yangilandi (5/10, 1 bajarilmadi)")
    ok(item(pro, T, "control")["students"]["done"] == 5, "«Nazorat» qutisida ham progress")
    sysm = [mm["body"] for mm in detail(rektor, T)["messages"] if mm["kind"] == "tizim"]
    ok(any(b_.startswith("Talabalar ijrosi") for b_ in sysm) and not any(n in " ".join(sysm) for n in names), "tizim yozuvlarida faqat sonlar (ism yo'q)")
    # CSV
    cv = reg.get(f"/api/portal/threads/{T}/students.csv")
    ok(cv.status_code == 200 and cv.text.startswith("﻿") and cv.text.count("\n") == 11 and "Qarzdorlik" in cv.text, "CSV: BOM, sarlavha + 10 qator, izoh")
    ok(rektor.get(f"/api/portal/threads/{T}/students.csv").status_code == 403, "rektor: CSV 403")
    ok(kaf.get(f"/api/portal/threads/{T}/students.csv").status_code == 403, "ishtirokchi emas: CSV 403")
    # qo'shish
    ok(post(reg, f"/api/portal/threads/{T}/students", {"students": [gs[10]["id"]]}).json().get("added") == 1, "yuboruvchi talaba qo'shdi (11)")
    ok(post(reg, f"/api/portal/threads/{T}/students", {"students": [gs[10]["id"]]}).status_code == 409, "takroriy qo'shish — 409")
    ok(post(pro, f"/api/portal/threads/{T}/students", {"students": [gs[11]["id"]]}).status_code == 403, "prorektor qo'sha olmaydi — 403")
    ok(detail(mbaza, T)["students"]["total"] == 11, "ijrochida jami 11")
    # qoralama
    r = reg.put("/api/portal/drafts", json={"subject": f"Qoralama {STAMP}", "students": ten[:3]})
    MY_DRAFTS.append((reg, r.json()["id"]))
    ok(next(x for x in reg.get("/api/portal/drafts").json() if x["id"] == r.json()["id"])["students"] == ten[:3], "qoralamada talabalar saqlanadi")
    r = rektor.put("/api/portal/drafts", json={"subject": f"Qoralama {STAMP}", "students": ten[:3]})
    MY_DRAFTS.append((rektor, r.json()["id"]))
    ok(next(x for x in rektor.get("/api/portal/drafts").json() if x["id"] == r.json()["id"])["students"] == [], "jamlangan ko'rinishdagi rahbar qoralamasiga talabalar yozilmaydi")

    # ============================================================== 22. Javobni ko'rib chiqish
    print("— 22. Javobni ko'rib chiqish —")
    ok(post(reg, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "accept"}).status_code == 409, "javob yo'q — qabul 409")
    ok(post(akad, f"/api/portal/threads/{T}/reply", {"body": f"Guruh ochildi (test {U})"}).status_code == 200, "Akademik bo'lim javob yozdi")
    dd = detail(reg, T)
    ok(rcp(dd, "akademik")["can_review"] and dd["perms"]["can_review"] and not rcp(dd, "malumotlar_bazasi")["can_review"], "yuboruvchi: akademik javobini ko'rib chiqa oladi")
    ok(rcp(detail(pro, T), "akademik")["can_review"], "rezolyutsiya muallifi (prorektor) ham ko'rib chiqa oladi")
    ok(not detail(mbaza, T)["perms"]["can_review"], "boshqa ijrochi ko'rib chiqa olmaydi")
    ok(has(reg, T, "sent", "review") and item(reg, T, "sent")["to_review"] == 1, "yuboruvchi: «Ko'rib chiqish» filtri va to_review=1")
    ok(lst(reg, limit=1)["counts"]["to_review"] >= 1, "counts.to_review")
    ok(has(pro, T, "control", "review"), "prorektor: Nazorat → «Ko'rib chiqish»")
    ok(post(mbaza, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "accept"}).status_code == 403, "ijrochi bo'lim — ko'rib chiqish 403")
    ok(post(reg, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "return"}).status_code == 400, "izohsiz qaytarish — 400")
    ok(post(reg, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "maybe", "comment": "x"}).status_code == 400, "noto'g'ri qaror — 400")
    ok(post(reg, f"/api/portal/threads/{T}/review", {"unit": "buxgalteriya", "decision": "accept"}).status_code == 404, "qabul qiluvchi bo'lmagan bo'lim — 404")
    ok(post(reg, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "return", "comment": "x", "due": YDAY}).status_code == 400, "o'tgan muddat — 400")
    r = post(reg, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "return", "comment": f"Buyruq raqamini ko'rsating {U}", "due": D2})
    ok(r.status_code == 200 and r.json()["status"] == "o'qilgan" and r.json()["review"] == "qaytarildi" and r.json()["returns"] == 1, "qaytarildi: holat «o'qilgan», returns=1")
    a = rcp(detail(akad, T), "akademik")
    ok(a["review"] == "qaytarildi" and a["review_note"].startswith("Buyruq raqamini") and a["due"] == D2 and a["review_by"], "qabul qiluvchida: izoh, yangi muddat, kim qaytargani")
    ok(any(mm["kind"] == "qaytarish" and U in mm["body"] for mm in detail(akad, T)["messages"]), "yozishmada «qaytarish» xabari")
    ia = item(akad, T)
    ok(ia["review"] == "qaytarildi" and ia["my_status"] == "o'qilgan", "kiruvchi ro'yxatda: «Qaytarildi» belgisi")
    ok(has(akad, T, "inbox", "returned") and lst(akad, limit=1)["counts"]["inbox_returned"] >= 1, "qabul qiluvchi: «Qaytarilgan» filtri va hisoblagichi")
    ok(has(akad, T, "inbox", "pending"), "qaytarilgan javob yana «Javobsiz» qatorida")
    rem = akad.get("/api/portal/reminders").json()["items"]
    ok(any(x["thread_id"] == T and x.get("returned") for x in rem), "eslatma: qaytarilgan (returned=true)")
    ok(not has(reg, T, "sent", "review"), "ko'rib chiqilgandan keyin «Ko'rib chiqish» filtridan chiqdi")
    ok(post(akad, f"/api/portal/threads/{T}/reply", {"body": "Buyruq № 45-T asosida"}).status_code == 200, "qayta javob")
    a = rcp(detail(reg, T), "akademik")
    ok(a["status"] == "javob berilgan" and a["review"] is None and a["returns"] == 1 and a["can_review"], "qayta javob: ko'rib chiqish kutilmoqda, returns saqlanadi")
    ok(post(pro, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "accept", "comment": "Rahmat"}).json()["review"] == "qabul",
       "prorektor (rezolyutsiya muallifi) qabul qildi")
    ok(post(pro, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "accept"}).status_code == 409, "takroriy qabul — 409")
    ok(item(akad, T)["review"] == "qabul", "qabul qiluvchida «Qabul qilindi»")
    rv = detail(reg, T)["reviews"]
    ok([x["decision"] for x in rv] == ["return", "accept"] and rv[0]["by_unit"] == "Registrator ofisi", "ko'rib chiqish tarixi: qaytarish → qabul")
    # yopilgan yozishmada amallar yo'q
    ok(post(reg, f"/api/portal/threads/{T}/close", {"note": "test"}).status_code == 200, "yozishma yopildi")
    ok(post(mbaza, f"/api/portal/threads/{T}/students/mark", {"ids": ten[:1], "status": "bajarildi"}).status_code == 409, "yopilgan: belgilash 409")
    ok(post(reg, f"/api/portal/threads/{T}/review", {"unit": "akademik", "decision": "return", "comment": "x"}).status_code == 409, "yopilgan: ko'rib chiqish 409")
    ok(post(reg, f"/api/portal/threads/{T}/students", {"students": [gs[11]["id"]]}).status_code == 409, "yopilgan: talaba qo'shish 409")
    # demo (v2.2) — Registrator → prorektor → Akademik/Ma'lumotlar bazasi
    demo = [x for x in all_items(reg, "sent") if x["subject"].startswith("Harbiy ta'lim fakultetiga")] + \
           [x for x in all_items(reg, "archive") if x["subject"].startswith("Harbiy ta'lim fakultetiga")]
    ok(demo and demo[0]["students"]["total"] == 10, "demo: Baratov xati 10 ta talaba bilan")
    js = httpx.get(f"{B}/portal.js").text
    ok("ptStuBlock" in js and "/review" in js and "students/mark" in js and "students.csv" in js, "portal.js: ro'yxat bloki, belgilash, CSV, ko'rib chiqish")
    # audit
    rows = q("SELECT action, detail, allowed, user_id FROM audit_log WHERE id>? AND resource='portal'", (AUDIT0,))
    def seen(action, uid, allowed=1, frag=""):
        return any(a_ == action and u_ == uid and al == allowed and frag in (dt_ or "") for a_, dt_, al, u_ in rows)
    ok(seen("portal: talabalar ijrosi belgilandi", 28, 1, REF), "audit: ijro belgilandi (28)")
    ok(seen("portal: talabalar ijrosini belgilash", 17, 0, REF), "audit: yuboruvchining belgilash urinishi rad")
    ok(seen("portal: javob qayta ishlashga qaytarildi", 17, 1, REF) and seen("portal: javob qabul qilindi", 3, 1, REF), "audit: qaytarildi (17), qabul (3)")
    ok(seen("portal: javobni ko'rib chiqish", 28, 0, REF), "audit: ijrochining ko'rib chiqish urinishi rad")
    ok(seen("portal: talabalar ro'yxati CSV", 17, 1, REF) and seen("portal: talabalar ro'yxati CSV", 2, 0, REF), "audit: CSV yuklandi / rektorga rad")
    ok(seen("portal: talabalar ro'yxatini biriktirish", 11, 0), "audit: buxgalteriyaning ro'yxat biriktirish urinishi rad")
    ok(seen("portal: xat yuborildi", 17, 1, "talabalar: 10 ta"), "audit: xat yuborildi (talabalar soni bilan)")

def main():
    # ============================================================== 1. Bo'limlar
    print("— 1. Bo'limlar —")
    u17, u23 = reg.get("/api/portal/units").json(), cc.get("/api/portal/units").json()
    ok(u17["me"] == "talabalar" and u23["me"] == "talabalar", "17 va 23 — talabalar bo'limi")
    ok(u17["is_head"] is True and u23["is_head"] is False, "is_head: 17 rahbar, 23 rahbar emas")
    ok({17, 23} <= {m["id"] for m in u17["members"]} and u17["members"][0]["id"] == 17, "talabalar a'zolari: 17 (rahbar, birinchi) va 23 (boshqa modullar yangi xodim qo'shishi mumkin)")
    ok(next(m for m in u17["members"] if m["id"] == 17)["head"] and next(m for m in u23["members"] if m["id"] == 23)["me"], "members: head/me belgilari")
    ok(any(x["key"] == "sirtqi" for x in u17["units"]) and {"xat", "sorov"} <= set(u17["kinds"]), "units ro'yxati va kinds")
    for c, uid, lead in ((rektor, 2, True), (pro, 3, True), (reg, 17, False), (cc, 23, False), (ithead, 21, False), (iteng, 22, False),
                         (akad, 18, False), (sirtqi, 27, False), (buxg, 11, False), (kaf, 31, False)):
        u = c.get("/api/portal/units").json()
        ok(u["can_resolve"] is lead and u["leader"] is lead, f"user {uid}: can_resolve/leader = {lead}")
        ok(not u["curated"] if uid not in (3, 4, 5) else bool(u["curated"]), f"user {uid}: curated ({len(u['curated'])})")
    cu = set(pro.get("/api/portal/units").json()["curated"])
    ok({"akademik", "talabalar", "sirtqi", "amaliyot"} <= cu and not {"imtihon", "kadrlar", "qabul"} & cu, "prorektor_oquv kuratorligi 2024 tuzilmasi bo'yicha (imtihon, kadrlar — rektorga bevosita)")

    # ============================================================== 2. Xodim bo'yicha o'qilmagan
    print("— 2. Xodim bo'yicha o'qilmagan —")
    body1 = f"Talabalar ma'lumotlarini yangilash. Kalit so'z zarbulmasal{U}. Oshxona: sho'rva{U} tayyor."
    T1, REF1 = new_thread(akad, "T1", ["talabalar"], due=D2, body=body1)
    ok(post(akad, "/api/portal/threads", {"subject": "x", "body": "x", "to": ["akademik"]}).status_code == 400, "faqat o'z bo'limiga xat: 400")
    ok(post(akad, "/api/portal/threads", {"subject": " ", "body": "x", "to": ["talabalar"]}).status_code == 400, "mavzusiz xat: 400")
    ok(post(akad, "/api/portal/threads", {"subject": "x", "body": "x", "to": ["nomalum"]}).status_code == 400, "noma'lum bo'lim: 400")
    it = item(reg, T1, "inbox", "unread")
    ok(it is not None and it["unread"] and it["my_status"] == "yangi" and it["role"] == "to", "17: T1 kiruvchida o'qilmagan, holat yangi")
    # bo'lim xodimi (rahbar emas) — bo'limning butun pochtasini emas, faqat shaxsan unga tegishli xatlarni ko'radi
    c23 = lst(cc)["counts"]
    ok(item(cc, T1) is None and item(cc, T1, "inbox", "unread") is None, "23 (Call-markaz, bo'lim xodimi): biriktirilmagan bo'lim xati kiruvchida yo'q")
    ok(cc.get(f"/api/portal/threads/{T1}").status_code == 403, "23: biriktirilmagan bo'lim xatini ocha olmaydi (403)")
    ok(c23["member_only"] is True and lst(reg)["counts"]["member_only"] is False, "counts.member_only: 23 — xodim, 17 — rahbar")
    detail(reg, T1)
    ok(not has(reg, T1, "inbox", "unread") and item(reg, T1)["unread"] is False, "17 uchun endi o'qilgan")
    d = detail(reg, T1); r = rcp(d, "talabalar")
    ok(r["status"] == "o'qilgan" and (r["read_by"] or "").startswith("Baratov"), f"qabul qiluvchi holati o'qilgan, read_by = {r['read_by']}")
    ok([x["name"] for x in r["readers"]] == ["Baratov M."], f"o'qiganlar ro'yxati faqat 17: {r['readers']}")
    ok(d["role"] == "to" and d["perms"]["can_assign"] and not d["perms"]["can_take"], "17: role=to, can_assign (rahbar), can_take yo'q")
    sent18 = item(akad, T1, "sent")
    ok(sent18 is not None and sent18["unread"] is False and sent18["role"] == "from", "18 yuborganlar: T1 o'qilmagan emas (o'z xati)")

    # ============================================================== 3. Ijrochi tayinlash
    print("— 3. Ijrochi tayinlash —")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 17}).status_code == 403, "23 boshqa xodimga (17) tayinlay olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T1}/assign", {"user_id": 18}).status_code == 403, "yuboruvchi bo'lim ijrochi tayinlay olmaydi (403)")
    ok(post(cc, f"/api/portal/threads/{T1}/reply", {"body": "x"}).status_code == 403, "23 biriktirilmagan xatga javob yoza olmaydi (403)")
    r = post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 23})
    ok(r.status_code == 200 and r.json()["assignee"] == "Rahimova N.", "17 (rahbar) xatni 23 ga biriktirdi")
    it23 = item(cc, T1, "inbox", "unread")
    ok(it23 is not None and it23["unread"], "biriktirilgandan keyin 23 kiruvchisida T1 (17 ochgan bo'lsa ham 23 uchun o'qilmagan)")
    p23 = detail(cc, T1)["perms"]
    ok(not p23["can_take"] and not p23["can_assign"] and p23["can_reply"], "23: can_reply bor; can_take (allaqachon o'zida), can_assign yo'q")
    m = item(cc, T1, "inbox", "mine")
    ok(m is not None and m["assigned_to_me"] and m["assignee_name"] == "Rahimova N.", "23: flt=mine da T1, assigned_to_me")
    ok(not has(reg, T1, "inbox", "mine"), "17: flt=mine da T1 yo'q")
    ok(cc.get("/api/portal/units").status_code == 200 and lst(cc)["counts"]["assigned_to_me"] >= 1, "23: counts.assigned_to_me >= 1")
    # 13-band (qisman): menga biriktirilgan, muddati yaqin xat — eslatma va bildirishnoma
    rem = cc.get("/api/portal/reminders").json()["items"]
    rr = next((x for x in rem if x["thread_id"] == T1), None)
    ok(rr is not None and rr["who"] == "menga" and rr["kind"] == "yaqin" and rr["days_left"] == 2 and rr["due"] == D2,
       f"23 eslatmalari: T1 who=menga, kind=yaqin, 2 kun ({rr})")
    nt = cc.get("/api/notifications").json()
    ok(isinstance(nt["items"], list) and all({"id", "kind", "title", "ts", "link"} <= set(x) for x in nt["items"]), "/api/notifications tuzilmasi")
    ni = next((x for x in nt["items"] if x["id"] == f"pm{T1}"), None)
    ok(ni is not None and ni["kind"] == "xat_muddat" and ni["link"] == {"view": "portal", "thread": T1}, "23 bildirishnomalarida T1 muddat eslatmasi")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": None}).status_code == 200, "23 o'z ijrosidan bo'shatdi (user_id=null)")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 200, "23 qayta oldi")
    r = post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 17})
    ok(r.status_code == 200 and r.json()["assignee"] == "Baratov M.", "17 (rahbar) ijrochini o'ziga o'zgartirdi")
    d = detail(reg, T1)
    ok(rcp(d, "talabalar")["assignee_id"] == 17 and rcp(d, "talabalar")["assignee_name"] == "Baratov M.", "detail: assignee_id=17")
    ok(not has(cc, T1, "inbox", "mine") and has(reg, T1, "inbox", "mine"), "flt=mine: endi 17 da, 23 da emas")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 409, "23 boshqa ijrochidagi xatni ola olmaydi (409)")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": None}).status_code == 403, "23 boshqaning ijrochiligini olib tashlay olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 11}).status_code == 400, "17 boshqa bo'lim xodimiga tayinlay olmaydi (400)")
    ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 999999}).status_code == 400, "mavjud bo'lmagan xodim (400)")
    s18 = item(akad, T1, "sent")
    ok(s18["unread"] is False and not has(akad, T1, "sent", "unread"), "tizim yozuvlari (tayinlash) 18 uchun o'qilmagan qilmaydi")
    tz = [x for x in detail(akad, T1)["messages"] if x["kind"] == "tizim"]
    ok(len(tz) >= 4 and not any(x["new"] for x in tz), f"detail: {len(tz)} ta tizim yozuvi, 'new' emas")

    # ============================================================== 4. Yo'naltirish
    print("— 4. Yo'naltirish —")
    ok(post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["akademik"], "note": "x"}).status_code == 400, "yuboruvchi bo'limga yo'naltirish rad (400)")
    ok(post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["talabalar"], "note": "x"}).status_code == 400, "o'z bo'limiga yo'naltirish rad (400)")
    ok(post(buxg, f"/api/portal/threads/{T1}/forward", {"units": ["sirtqi"]}).status_code == 403, "qabul qilmagan bo'lim yo'naltira olmaydi (403)")
    r = post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["sirtqi"], "note": f"Sirtqi bo'lim talabalari bo'yicha ({STAMP})"})
    ok(r.status_code == 200 and r.json()["units"] == ["sirtqi"], "17 → sirtqi yo'naltirdi")
    d = detail(reg, T1); rt, rs = rcp(d, "talabalar"), rcp(d, "sirtqi")
    ok(rt["status"] == "yo'naltirilgan" and rt["forwarded_to"] == ["Sirtqi bo'lim"], "17 holati yo'naltirilgan, forwarded_to = Sirtqi bo'lim")
    ok(rs and rs["status"] == "yangi" and rs["via"] == "yonaltirish" and rs["fwd_from"] == "Registrator ofisi", "sirtqi: yangi, via yonaltirish, fwd_from Registrator ofisi")
    s = item(sirtqi, T1)
    ok(s is not None and s["my_status"] == "yangi" and s["unread"], "27 kiruvchida T1 (yangi, o'qilmagan)")
    ok(not d["perms"]["can_forward"], "17: endi can_forward yo'q")
    ok(post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["buxgalteriya"]}).status_code == 409, "qayta yo'naltirish 409")
    fm = [x for x in d["messages"] if (x.get("meta") or {}).get("forward")]
    ok(len(fm) == 1 and fm[0]["kind"] == "xat" and "Sirtqi bo'lim" in fm[0]["body"], "yo'naltirish xabari yozishmada")
    ok(item(akad, T1, "sent")["unread"] is True, "yo'naltirish izohi 18 uchun yangi xabar (o'qilmagan)")
    ok(not has(reg, T1, "inbox", "pending") and has(sirtqi, T1, "inbox", "pending"), "flt=pending: 17 da yo'q, 27 da bor")

    # ============================================================== 5. Rezolyutsiya
    print("— 5. Rezolyutsiya —")
    T2, REF2 = new_thread(akad, "T2 rezolyutsiya", ["talabalar"], body=f"Rezolyutsiya uchun xat ({STAMP}).")
    ok(post(reg, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["buxgalteriya"]}).status_code == 403, "17 rezolyutsiya qo'ya olmaydi (403)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["akademik"]}).status_code == 400, "yuboruvchi (akademik) ijrochi bo'la olmaydi (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": []}).status_code == 400, "ijrochisiz rezolyutsiya (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": " ", "units": ["buxgalteriya"]}).status_code == 400, "matnsiz rezolyutsiya (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["talabalar", "buxgalteriya"], "lead": "buxgalteriya", "due": YDAY}).status_code == 400,
       "o'tgan muddat (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["buxgalteriya"], "due": "31-12-2026"}).status_code == 400, "noto'g'ri sana (400)")
    ok(not detail(rektor, T2)["resolutions"], "rad etilgan urinishlar rezolyutsiya yaratmadi")
    RTXT = f"Ko'rib chiqib, 3 kun ichida taklif kiritilsin ({STAMP})"
    r = post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": RTXT, "units": ["talabalar", "buxgalteriya"], "lead": "buxgalteriya", "due": D3})
    ok(r.status_code == 200 and r.json()["id"], "rektor rezolyutsiya qo'ydi (talabalar + buxgalteriya, mas'ul buxgalteriya, +3 kun)")
    RID = r.json()["id"]
    d = detail(rektor, T2); z = d["resolutions"]
    ok(len(z) == 1 and z[0]["state"] == "nazoratda" and z[0]["lead_unit"] == "buxgalteriya" and z[0]["due"] == D3 and z[0]["text"] == RTXT,
       "rezolyutsiya kartasi: nazoratda, mas'ul buxgalteriya, muddat")
    ok([x["unit"] for x in z[0]["units"]] == ["talabalar", "buxgalteriya"] and z[0]["can_close"], "ijrochilar ro'yxati, can_close (muallif)")
    ok(d["role"] == "watch" and {"unit": "rektorat", "name": "Rektorat"} in d["watchers"], "rektorat kuzatuvchi (role=watch)")
    rm = [x for x in d["messages"] if x["kind"] == "rezolyutsiya"]
    ok(len(rm) == 1 and rm[0]["meta"]["res_id"] == RID and "Buxgalteriya" in rm[0]["body"], "rezolyutsiya xabari (kind=rezolyutsiya)")
    rb = rcp(d, "buxgalteriya")
    ok(rb["via"] == "rezolyutsiya" and rb["lead"] and rb["due"] == D3 and rb["status"] == "yangi", "buxgalteriya: via rezolyutsiya, lead, due")
    ok(rcp(d, "talabalar")["due"] == D3 and not rcp(d, "talabalar")["lead"], "talabalar: shaxsiy muddat D3, lead emas")
    bi = item(buxg, T2)
    ok(bi is not None and bi["due"] == D3 and bi["my_status"] == "yangi" and bi["resolution"] and bi["unread"], "11 kiruvchida T2 (due D3, resolution belgisi)")
    ri = item(rektor, T2, "control")
    ok(ri is not None and ri["role"] == "watch", "rektor nazorat qutisida T2")
    ok(lst(rektor, "control")["counts"]["control"] >= 1, "counts.control >= 1")
    ok(post(pro, f"/api/portal/threads/{T2}/resolutions/{RID}/close").status_code == 403, "prorektor_oquv rektor rezolyutsiyasini yecha olmaydi (403)")
    ok(not detail(pro, T2)["resolutions"][0]["can_close"], "prorektor uchun can_close=false")
    ok(post(reg, f"/api/portal/threads/{T2}/reply", {"body": "Registrator: taklif tayyor."}).status_code == 200, "17 javob berdi")
    ok(detail(rektor, T2)["resolutions"][0]["state"] == "nazoratda", "bitta ijrochi javobidan keyin hali nazoratda")
    ok(post(buxg, f"/api/portal/threads/{T2}/reply", {"body": "Buxgalteriya: hisob-kitob ilova qilindi."}).status_code == 200, "11 javob berdi")
    z = detail(rektor, T2)["resolutions"][0]
    ok(z["state"] == "bajarildi" and all(x["status"] == "javob berilgan" for x in z["units"]), "ikkala ijrochi javob berdi → bajarildi")
    ok(post(pro, f"/api/portal/threads/{T2}/resolutions/{RID}/close").status_code == 403, "prorektor_oquv yecha olmaydi (bajarilgandan keyin ham 403)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolutions/{RID}/close").status_code == 200, "rektor nazoratdan yechdi")
    z = detail(rektor, T2)["resolutions"][0]
    ok(z["state"] == "yechilgan" and not z["can_close"], "holat yechilgan")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolutions/999999/close").status_code == 404, "mavjud bo'lmagan rezolyutsiya (404)")

    # ============================================================== 6. Yopish / qayta ochish / arxiv
    print("— 6. Yopish, qayta ochish, arxiv —")
    ok(post(reg, f"/api/portal/threads/{T1}/close", {"note": "x"}).status_code == 403, "17 (qabul qiluvchi) yopa olmaydi (403)")
    ok(post(sirtqi, f"/api/portal/threads/{T1}/close", {"note": "x"}).status_code == 403, "27 yopa olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T1}/reopen").status_code == 403, "17 ochiq yozishmani 'qayta ocha' olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T1}/close", {"note": "Masala hal qilindi"}).status_code == 200, "18 (yuboruvchi) yopdi")
    d = detail(akad, T1)
    ok(d["status"] == "yopilgan" and d["close_note"] == "Masala hal qilindi" and d["closed_by"] and d["perms"]["can_reopen"] and not d["perms"]["can_reply"],
       "holat yopilgan, close_note, can_reopen")
    ok(post(reg, f"/api/portal/threads/{T1}/reply", {"body": "x"}).status_code == 409, "yopilgan yozishmaga javob 409")
    ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 409, "yopilgan yozishmada tayinlash 409")
    ok(post(akad, f"/api/portal/threads/{T1}/close", {"note": ""}).status_code == 409, "qayta yopish 409")
    for c, n in ((akad, 18), (reg, 17), (cc, 23), (sirtqi, 27)):
        ok(has(c, T1, "archive"), f"{n}: arxivda T1")
    ok(not has(reg, T1) and not has(sirtqi, T1) and not has(akad, T1, "sent"), "kiruvchi/yuborilganlarda T1 yo'q")
    ok(not has(buxg, T1, "archive"), "ishtirokchi bo'lmagan 11 arxivida yo'q")
    ok(post(reg, f"/api/portal/threads/{T1}/reopen").status_code == 403, "17 qayta ocha olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T1}/reopen").status_code == 200, "18 qayta ochdi")
    ok(detail(akad, T1)["status"] == "ochiq" and has(reg, T1) and has(akad, T1, "sent") and not has(reg, T1, "archive"), "qayta ochildi: kiruvchida, arxivda emas")
    ok(post(akad, f"/api/portal/threads/{T1}/reopen").status_code == 409, "ochiq yozishmani qayta ochish 409")
    ok(post(buxg, f"/api/portal/threads/{T1}/archive", {"on": True}).status_code == 403, "ishtirokchi bo'lmagan arxivlay olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T1}/archive", {"on": True}).json()["archived"] is True, "17 shaxsiy arxivga oldi")
    ok(not has(reg, T1) and has(reg, T1, "archive") and item(reg, T1, "archive")["archived"], "17: kiruvchida yo'q, arxivda (archived=true)")
    ok(has(cc, T1) and not has(cc, T1, "archive"), "23 uchun kiruvchida qoladi (shaxsiy arxiv)")
    ok(detail(reg, T1)["perms"]["archived"], "17 detail: perms.archived")
    ok(post(cc, f"/api/portal/threads/{T1}/archive", {"on": True}).status_code == 200 and not has(cc, T1), "23 arxivladi")
    ok(post(cc, f"/api/portal/threads/{T1}/archive", {"on": False}).status_code == 200 and has(cc, T1), "23 arxivdan qaytardi (on=false)")
    ok(post(akad, f"/api/portal/threads/{T1}/reply", {"body": f"Qo'shimcha ma'lumot ({STAMP})."}).status_code == 200, "18 yangi javob yozdi")
    it = item(reg, T1)
    ok(it is not None and it["archived"] is False and it["unread"], "yangi javob 17 uchun arxivdan qaytardi (o'qilmagan)")

    # ============================================================== 7. Qutilar RBAC
    print("— 7. Qutilar RBAC —")
    for box in ("all", "control", "area"):
        ok(reg.get("/api/portal/threads", params={"box": box}).status_code == 403, f"17: box={box} → 403")
    ok(rektor.get("/api/portal/threads", params={"box": "area"}).status_code == 403, "rektor: box=area → 403 (kuratorlik yo'q)")
    ok(rektor.get("/api/portal/threads", params={"box": "all"}).status_code == 200, "rektor: box=all → 200")
    a3 = pro.get("/api/portal/threads", params={"box": "area"})
    ok(a3.status_code == 200 and a3.json()["counts"].get("area_pending") is not None, "prorektor_oquv: box=area → 200, area_pending bor")
    ok(any(x["id"] == T1 for x in all_items(pro, "area")), "prorektor_oquv area: T1 (akademik → talabalar) ko'rinadi")
    ok(reg.get("/api/portal/threads", params={"box": "nomalum"}).status_code == 400, "noto'g'ri quti 400")
    ok(buxg.get(f"/api/portal/threads/{T1}").status_code == 403, "ishtirokchi bo'lmagan bo'lim yozishmani ocha olmaydi (403)")
    ok(pro.get(f"/api/portal/threads/{T1}").status_code == 200, "prorektor (rahbariyat) ochadi")
    ok(post(buxg, f"/api/portal/threads/{T1}/reply", {"body": "x"}).status_code == 403, "begona bo'lim javob yoza olmaydi (403)")

    # ============================================================== 8. Sahifalash va hisoblagichlar
    print("— 8. Sahifalash va hisoblagichlar —")
    tot = lst(rektor, "all", limit=1)["total"]
    real = q("SELECT COUNT(*) FROM portal_threads")[0][0]
    ok(tot == real, f"box=all total = COUNT(*) ({tot} = {real})")
    p1, p2, p10 = (lst(rektor, "all", offset=o, limit=l)["items"] for o, l in ((0, 5), (5, 5), (0, 10)))
    i1, i2, i10 = [x["id"] for x in p1], [x["id"] for x in p2], [x["id"] for x in p10]
    ok(len(i1) == 5 and len(i2) == 5 and not set(i1) & set(i2), "limit=5: sahifalar kesishmaydi")
    ok(i1 + i2 == i10, "1- va 2-sahifa = limit=10 ning birinchi 10 tasi (tartib bilan)")
    lp = lst(rektor, "all", offset=10**6, limit=5)
    ok(lp["items"] == [] and lp["total"] == real, "chegaradan tashqari offset: bo'sh, total saqlanadi")
    ok(lst(rektor, "all", limit=1000)["limit"] == 100 and lst(rektor, "all", offset=-5)["offset"] == 0, "limit ≤ 100, offset ≥ 0")
    for c, n in ((reg, 17), (cc, 23), (buxg, 11), (sirtqi, 27)):
        cn = lst(c, limit=1)["counts"]
        ok(cn["inbox_pending"] == lst(c, "inbox", "pending", limit=1)["total"], f"{n}: counts.inbox_pending = inbox&pending total ({cn['inbox_pending']})")
        ok(cn["inbox"] == lst(c, "inbox", limit=1)["total"], f"{n}: counts.inbox = inbox total ({cn['inbox']})")
        ok(cn["archive"] == lst(c, "archive", limit=1)["total"], f"{n}: counts.archive = archive total ({cn['archive']})")
        ok(cn["sent"] == lst(c, "sent", limit=1)["total"], f"{n}: counts.sent = sent total ({cn['sent']})")
        ok(cn["inbox_unread"] == lst(c, "inbox", "unread", limit=1)["total"], f"{n}: counts.inbox_unread = inbox&unread total ({cn['inbox_unread']})")
        ok(cn["sent_unread"] == lst(c, "sent", "unread", limit=1)["total"], f"{n}: counts.sent_unread = sent&unread total ({cn['sent_unread']})")
        ok(cn["my_overdue"] == lst(c, "inbox", "overdue", limit=1)["total"], f"{n}: counts.my_overdue = inbox&overdue total ({cn['my_overdue']})")
    rc = lst(rektor, limit=1)["counts"]
    ok(rc["all"] == real and rc["leader"] is True, "rektor counts.all = COUNT(*)")
    # Shaxsiy arxivdagi javob kutilayotgan xat: kiruvchida ko'rinmaydi — hisoblagich ham uni sanamasligi kerak
    T4, _ = new_thread(akad, "T4 arxiv-hisob", ["talabalar"])
    ok(post(reg, f"/api/portal/threads/{T4}/archive", {"on": True}).status_code == 200, "17 kutilayotgan T4 ni shaxsiy arxivga oldi")
    cn = lst(reg, limit=1)["counts"]; pt = lst(reg, "inbox", "pending", limit=1)["total"]
    soft(cn["inbox_pending"] == pt, f"17: arxivlangan kutilayotgan xat bilan counts.inbox_pending ({cn['inbox_pending']}) = inbox&pending total ({pt})")
    ok(post(reg, f"/api/portal/threads/{T4}/archive", {"on": False}).status_code == 200, "17 T4 ni arxivdan qaytardi")

    # ============================================================== 9. Qidiruv
    print("— 9. Qidiruv —")
    r = lst(rektor, "all", q_=f"zarbulmasal{U}")
    ok([x["id"] for x in r["items"]] == [T1] and r["total"] == 1, "FTS: matndagi noyob so'z bo'yicha (faqat T1)")
    ok(has(rektor, T1, "all", q_=f"zarbulmas"), "FTS: prefiks bo'yicha")
    ok(has(rektor, T1, "all", q_=f"ZARBULMASAL{U}"), "FTS: katta harf bilan")
    for v in ("ʻ", "’", "'", "‘"):
        r = lst(rektor, "all", q_=f"sho{v}rva{U}")
        ok([x["id"] for x in r["items"]] == [T1], f"FTS: apostrof varianti sho{v}rva{U}")
    ok(has(rektor, T1, "all", q_=REF1) and has(akad, T1, "sent", q_=REF1), f"ref_no bo'yicha ({REF1})")
    ok(has(rektor, T2, "all", q_=REF2), f"ref_no bo'yicha ({REF2})")
    ok(has(akad, T1, "sent", q_="Sirtqi bo'lim") and has(akad, T1, "sent", q_="Sirtqi boʻlim"), "bo'lim nomi bo'yicha (Sirtqi bo'lim, ʻ varianti)")
    ok(has(buxg, T2, "inbox", q_=f"hisob-kitob"), "javob matni bo'yicha (11: hisob-kitob)")
    ok(has(rektor, T1, "all", q_=f"Portal v2 test T1 {STAMP}"), "mavzu bo'yicha")
    r = lst(rektor, "all", q_=f"qwzxvjk{U}")
    ok(r["total"] == 0 and r["items"] == [], "mantiqsiz so'z: bo'sh")
    for s_ in ('"', '*', 'AND', '(', ')', 'OR NOT', '"zarbulmasal', "a\"b*c(", "NEAR(x y)", "'", "%", "_", "\\", "-", "^", "x:y", "{}", "''; DROP TABLE x;--"):
        r = rektor.get("/api/portal/threads", params={"box": "all", "q": s_})
        ok(r.status_code == 200 and "items" in r.json(), f"maxsus belgi q={s_!r}: 200, SQL xatosi yo'q")
    ok(reg.get("/api/portal/threads", params={"box": "inbox", "q": f"zarbulmasal{U}"}).json()["total"] == 1, "17 kiruvchida qidiruv ishlaydi")
    ok(buxg.get("/api/portal/threads", params={"box": "inbox", "q": f"zarbulmasal{U}"}).json()["total"] == 0, "qidiruv RBAC: 11 T1 ni topmaydi")

    # ============================================================== 10. Qoralamalar
    print("— 10. Qoralamalar —")
    n0 = lst(akad, limit=1)["counts"]["drafts"]
    r = akad.put("/api/portal/drafts", json={"subject": f"Qoralama {STAMP}", "body": "birinchi", "to": ["talabalar", "nomalum"], "kind": "sorov", "due": D3})
    ok(r.status_code == 200 and r.json()["ok"] and r.json()["id"], "PUT: qoralama yaratildi")
    DID = r.json()["id"]; MY_DRAFTS.append((akad, DID))
    dl = akad.get("/api/portal/drafts").json(); dd = next((x for x in dl if x["id"] == DID), None)
    ok(dd and dd["to"] == ["talabalar"] and dd["kind"] == "sorov" and dd["due"] == D3, "GET: ro'yxatda, noma'lum bo'lim tashlab yuborildi")
    ok(lst(akad, limit=1)["counts"]["drafts"] == n0 + 1, "counts.drafts +1")
    r = akad.put("/api/portal/drafts", json={"id": DID, "subject": f"Qoralama {STAMP} (tahrir)", "body": "ikkinchi", "to": ["talabalar"]})
    ok(r.status_code == 200 and r.json()["id"] == DID, "PUT: shu id yangilandi")
    dd = next(x for x in akad.get("/api/portal/drafts").json() if x["id"] == DID)
    ok(dd["body"] == "ikkinchi" and dd["subject"].endswith("(tahrir)") and sum(x["id"] == DID for x in akad.get("/api/portal/drafts").json()) == 1, "yangilangan, dublikat yo'q")
    ok(not any(x["id"] == DID for x in reg.get("/api/portal/drafts").json()), "boshqa xodim qoralamani ko'rmaydi")
    ok(reg.put("/api/portal/drafts", json={"id": DID, "subject": "hack"}).status_code == 404, "boshqa xodim qoralamani tahrirlay olmaydi (404)")
    ok(reg.delete(f"/api/portal/drafts/{DID}").status_code == 404, "boshqa xodim qoralamani o'chira olmaydi (404)")
    T3, _ = new_thread(akad, "T3 qoralamadan", ["talabalar"], draft_id=DID)
    detail(reg, T3)
    ok(post(cc, f"/api/portal/threads/{T3}/reply", {"body": "x"}).status_code == 403, "23 (xodim) biriktirilmagan T3 ga javob yoza olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T3}/assign", {"user_id": 23}).status_code == 200, "17 T3 ni 23 ga biriktirdi")
    ok(post(cc, f"/api/portal/threads/{T3}/reply", {"body": f"Hamkasb javobi ({STAMP})"}).status_code == 200, "23 T3 ga javob yozdi")
    # dizayn: "o'qilmagan" = boshqa BO'LIMdan kelgan yangi xabar (hamkasb javobi — "bizniki", kiruvchi emas); o'qilganlik esa xodim bo'yicha
    ok(item(reg, T3)["unread"] is False, "hamkasb (23) javobi 17 uchun kiruvchi xat hisoblanmaydi (o'qilmagan emas)")
    ok(not any(x["id"] == DID for x in akad.get("/api/portal/drafts").json()), "draft_id bilan yuborilganda qoralama o'chdi")
    ok(lst(akad, limit=1)["counts"]["drafts"] == n0, "counts.drafts qaytdi")
    ok(akad.delete(f"/api/portal/drafts/{DID}").status_code == 404, "o'chgan qoralamani o'chirish 404")
    r = reg.put("/api/portal/drafts", json={"subject": f"Q2 {STAMP}"}); D2ID = r.json()["id"]; MY_DRAFTS.append((reg, D2ID))
    T5, _ = new_thread(akad, "T5 begona draft_id", ["talabalar"], draft_id=D2ID)
    ok(any(x["id"] == D2ID for x in reg.get("/api/portal/drafts").json()), "boshqaning draft_id si bilan yuborish uning qoralamasini o'chirmaydi")
    ok(reg.delete(f"/api/portal/drafts/{D2ID}").status_code == 200, "egasi o'chirdi")
    ok(akad.put("/api/portal/drafts", json={"subject": "x", "due": "bugun"}).status_code == 400, "noto'g'ri sana 400")

    # ============================================================== 11. Shablonlar
    print("— 11. Shablonlar —")
    r = post(akad, "/api/portal/templates", {"title": f"Test shablon {STAMP}", "subject": "So'rov: {bolim}", "body": "Sana {sana}, muddat {muddat}",
                                             "kind": "sorov", "due_days": 5, "to": ["talabalar"]})
    ok(r.status_code == 200 and r.json()["id"], "18: akademik bo'limi uchun shablon yaratildi")
    TPL = r.json()["id"]; MY_TEMPLATES.append((akad, TPL))
    tl = akad.get("/api/portal/templates").json(); t = next((x for x in tl if x["id"] == TPL), None)
    ok(t and t["scope"] == "bolim" and t["mine"] and t["uses"] == 0 and t["due_days"] == 5 and t["to"] == ["talabalar"], "18 ro'yxatida: bolim, mine, uses=0")
    ok(not any(x["id"] == TPL for x in reg.get("/api/portal/templates").json()), "17 (boshqa bo'lim) ko'rmaydi")
    ok(reg.delete(f"/api/portal/templates/{TPL}").status_code == 403, "17 o'chira olmaydi (403)")
    ok(post(reg, f"/api/portal/templates/{TPL}/use").status_code == 200, "begona bo'lim /use: 200 (jim)")
    ok(next(x for x in akad.get("/api/portal/templates").json() if x["id"] == TPL)["uses"] == 0, "begona bo'lim /use hisoblagichni oshirmaydi")
    ok(post(akad, f"/api/portal/templates/{TPL}/use").status_code == 200, "18 /use")
    post(akad, f"/api/portal/templates/{TPL}/use")
    ok(next(x for x in akad.get("/api/portal/templates").json() if x["id"] == TPL)["uses"] == 2, "uses = 2")
    inst = {r_[0] for r_ in q("SELECT id FROM portal_templates WHERE owner_unit='*'")}
    for c, n in ((reg, 17), (sirtqi, 27), (kaf, 31), (rektor, 2), (iteng, 22)):
        tl = c.get("/api/portal/templates").json()
        ok(inst and inst <= {x["id"] for x in tl if x["scope"] == "institut" and not x["mine"]}, f"{n}: institut shablonlari ko'rinadi ({len(inst)})")
    ok(akad.delete(f"/api/portal/templates/{min(inst)}").status_code == 403, "institut shablonini bo'lim o'chira olmaydi (403)")
    ok(post(akad, "/api/portal/templates", {"title": " ", "body": "x"}).status_code == 400, "nomsiz shablon 400")
    ok(post(akad, "/api/portal/templates", {"title": "x"}).status_code == 400, "bo'sh shablon 400")
    ok(akad.delete(f"/api/portal/templates/{TPL}").status_code == 200, "18 o'z shablonini o'chirdi")
    MY_TEMPLATES.clear()
    ok(akad.delete(f"/api/portal/templates/{TPL}").status_code == 404, "qayta o'chirish 404")

    # ============================================================== 12. Fayllar
    print("— 12. Fayllar —")
    up = lambda c, name, data, cat="Boshqa": c.post("/api/portal/files", params={"name": name, "category": cat}, content=data)
    TXT = f"Portal test fayli {STAMP}\nO'zbekcha matn: sho'rva, ta'lim.\n".encode()
    r = up(reg, f"portal_test_{U}.txt", TXT)
    ok(r.status_code == 200 and r.json()["ok"] and r.json()["scan"] in ("toza", "tekshirilmadi"), f"to'g'ri .txt yuklandi (scan={r.json().get('scan')})")
    FID = r.json()["id"]
    row = q("SELECT sha256, mime, stored, size, owner_unit, category FROM portal_files WHERE id=?", (FID,))[0]
    ok(row[0] == hashlib.sha256(TXT).hexdigest(), "sha256 ustuni saqlandi va to'g'ri")
    ok(row[1].startswith("text/plain") and row[3] == len(TXT) and row[4] == "talabalar" and row[5] == "Boshqa", "mime, hajm, bo'lim, toifa")
    ok("/" not in row[2] and ".." not in row[2] and row[2].endswith(".txt") and len(row[2]) == 36, "diskdagi nom tasodifiy (uuid.txt)")
    dl = reg.get(f"/api/portal/files/{FID}/download")
    ok(dl.status_code == 200 and dl.content == TXT, "yuklab olish: mazmun bir xil")
    ok(dl.headers.get("x-content-type-options") == "nosniff", "X-Content-Type-Options: nosniff")
    ok("no-store" in dl.headers.get("cache-control", ""), "Cache-Control: no-store")
    ok(buxg.get(f"/api/portal/files/{FID}/download").status_code == 403, "ulashilmagan bo'lim yuklab ola olmaydi (403)")
    ok(cc.get(f"/api/portal/files/{FID}/download").status_code == 200, "o'z bo'limi xodimi (23) yuklab oladi")
    exe = b"MZ\x90\x00" + b"\x00" * 56 + (64).to_bytes(4, "little") + b"PE\x00\x00" + b"\x00" * 200
    r = up(reg, f"hisobot_{U}.pdf", exe)
    ok(r.status_code == 415, f"exe → .pdf nomi bilan: 415 ({r.json().get('detail', '')[:60]})")
    ok(up(reg, f"skript_{U}.txt", b"#!/bin/sh\nrm -rf /\n").status_code == 415, "shebang skript .txt: 415")
    ok(up(reg, f"soxta_{U}.pdf", b"bu pdf emas").status_code == 415, "soxta .pdf (magic yo'q): 415")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/vbaProject.bin", b"\x00VBA")
    r = up(reg, f"makros_{U}.docx", buf.getvalue())
    ok(r.status_code == 415 and "akros" in r.json().get("detail", ""), "vbaProject.bin li docx: 415 (makros)")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z: z.writestr("ichki/virus.exe", b"MZ")
    ok(up(reg, f"arxiv_{U}.zip", buf.getvalue()).status_code == 415, "ichida .exe bor zip: 415")
    ok(up(reg, f"bad_{U}.exe", b"hello").status_code == 400, ".exe kengaytma: 400")
    ok(up(reg, f"bosh_{U}.txt", b"").status_code == 400, "bo'sh fayl: 400")
    r = up(reg, f"../../x_{U}.txt", b"path traversal test\n")
    ok(r.status_code == 200 and r.json()["name"] == f"x_{U}.txt", f"'../../x_{U}.txt' → nom tozalandi: {r.json().get('name')}")
    FID2 = r.json()["id"]
    st = q("SELECT name, stored FROM portal_files WHERE id=?", (FID2,))[0]
    files_dir = Path(os.environ.get("ISFT_CORE_FILES_DIR") or Path(os.environ.get("ISFT_CORE_DATA_DIR") or ROOT / "data") / "portal_files")
    ok(st[0] == f"x_{U}.txt" and "/" not in st[1] and not (ROOT.parent / f"x_{U}.txt").exists() and not (ROOT / f"x_{U}.txt").exists(),
       "bazada xavfsiz nom, fayl papkadan tashqariga yozilmadi")
    if files_dir.is_dir(): ok((files_dir / st[1]).is_file(), "fayl portal_files ichida")
    r = up(reg, f"..\\..\\win_{U}.txt", b"win\n")
    ok(r.status_code == 200 and r.json()["name"] == f"win_{U}.txt", "Windows yo'li (..\\..\\) ham tozalandi")
    rl = rektor.get("/api/portal/files").json()
    ok(any(x["id"] == FID for x in rl["items"]), "rektor (rahbariyat) faylni ko'radi")
    ok(not any(x["id"] == FID for x in buxg.get("/api/portal/files").json()["items"]), "11 ro'yxatida yo'q")
    # prorektorlar — faqat kuratorlikdagi bo'limlar fayllari (+ o'zi ishtirok etgan yozishmalar ilovalari); rektor — hammasi
    ok(any(x["id"] == FID for x in pro.get("/api/portal/files").json()["items"]) and pro.get(f"/api/portal/files/{FID}/download").status_code == 200,
       "o'quv prorektori: kuratorlikdagi Registrator ofisi faylini ko'radi")
    ok(not any(x["id"] == FID for x in promol.get("/api/portal/files").json()["items"]) and promol.get(f"/api/portal/files/{FID}/download").status_code == 403,
       "moliya prorektori: kuratorligidan tashqari bo'lim faylini ko'rmaydi (403)")
    # faqat egasi bo'lim qayta ulashadi: Registrator fayli → Akademik bo'limga xat orqali ulashildi; Akademik uni Buxgalteriyaga ulasha olmaydi
    TS, _ = new_thread(reg, "TS ulashma", ["akademik"], file_ids=[FID])
    ok(akad.get(f"/api/portal/files/{FID}/download").status_code == 200, "xat ilovasi qabul qiluvchiga ulashildi (18 yuklab oladi)")
    r = post(akad, "/api/portal/threads", {"subject": f"Qayta ulashish {STAMP}", "body": "x", "to": ["buxgalteriya"], "file_ids": [FID]})
    ok(r.status_code == 403 and "egasi" in r.json().get("detail", ""), "begona faylni boshqa bo'limga qayta ulashish rad etildi (403)")
    ok(buxg.get(f"/api/portal/files/{FID}/download").status_code == 403, "buxgalteriyaga ulashma yaratilmadi")
    ok(post(akad, f"/api/portal/threads/{TS}/reply", {"body": "Fayl qayta ilova qilindi", "file_ids": [FID]}).status_code == 200,
       "ishtirokchilarda allaqachon bor faylni javobga ilova qilish mumkin")
    # xat qaytarib olinsa — shu xat yaratgan ulashma ham o'chadi
    TR_, _ = new_thread(reg, "TR qaytarib olish ulashma", ["sirtqi"], file_ids=[FID])
    ok(sirtqi.get(f"/api/portal/files/{FID}/download").status_code == 200, "Sirtqi bo'limga ilova orqali ulashildi")
    ok(post(reg, f"/api/portal/threads/{TR_}/recall", {"note": "test"}).status_code == 200, "17 xatni qaytarib oldi")
    ok(sirtqi.get(f"/api/portal/files/{FID}/download").status_code == 403 and not q("SELECT 1 FROM portal_shares WHERE file_id=? AND unit='sirtqi'", (FID,)),
       "qaytarib olingan xat yaratgan ulashma o'chirildi (27 endi yuklab ololmaydi)")
    ok(akad.get(f"/api/portal/files/{FID}/download").status_code == 200, "boshqa xat orqali yaratilgan ulashma saqlanib qoldi")
    au = q("SELECT COUNT(*) FROM audit_log WHERE id>? AND resource='portal' AND action='portal: fayl rad etildi' AND allowed=0", (AUDIT0,))[0][0]
    ok(au >= 4, f"rad etilgan yuklashlar auditda ({au})")

    # ============================================================== 13. Eslatmalar
    print("— 13. Eslatmalar —")
    rem = iteng.get("/api/portal/reminders").json()
    ok(isinstance(rem.get("items"), list) and all({"thread_id", "ref_no", "subject", "due", "days_left", "kind", "who"} <= set(x) for x in rem["items"]),
       "reminders tuzilmasi")
    lim = (TODAY + dt.timedelta(days=2)).isoformat()
    exp = q("""SELECT t.id FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id WHERE r.unit='it' AND r.assignee=22 AND t.status='ochiq'
               AND r.status IN ('yangi','o''qilgan') AND COALESCE(NULLIF(r.due,''), NULLIF(t.due,'')) <= ?""", (lim,))
    if exp:
        got = {x["thread_id"] for x in rem["items"] if x["who"] == "menga"}
        ok({e[0] for e in exp} <= got, f"22: biriktirilgan LMS xati who=menga ({sorted(got)})")
        ok(all(x["kind"] in ("bugun", "ertaga", "otgan", "yaqin") for x in rem["items"]), "kind qiymatlari to'g'ri")
    else:
        print("  (22 ga biriktirilgan, muddati yaqin xat demo bazada yo'q — faqat tuzilma tekshirildi)")
    nt = cc.get("/api/notifications").json()
    ok("items" in nt and "unread" in nt and all(isinstance(x["title"], str) for x in nt["items"]), "23 /api/notifications tuzilmasi")
    rem23 = {x["thread_id"] for x in cc.get("/api/portal/reminders").json()["items"] if x["who"] == "menga"}
    nids = {x["id"] for x in nt["items"]}
    ok(all(f"pm{t_}" in nids for t_ in rem23), f"23: har bir 'menga' eslatmasi bildirishnomada ({sorted(rem23)})")
    rr = reg.get("/api/portal/reminders").json()["items"]
    ok(all(x["who"] in ("menga", "bolimga", "yuborgan", "nazorat") for x in rr), "17 eslatmalari: who qiymatlari to'g'ri")

    # ============================================================== 15. Xatni qaytarib olish
    print("— 15. Xatni qaytarib olish —")
    W6 = f"qaytarma{U}"
    inbox_b0 = lst(buxg, limit=1)["counts"]["inbox"]
    T6, REF6 = new_thread(akad, "T6 qaytarib olish", ["talabalar", "buxgalteriya"], due=D3, body=f"Qaytarib olinadigan xat. Kalit so'z {W6}.")
    ok(lst(buxg, limit=1)["counts"]["inbox"] == inbox_b0 + 1 and has(buxg, T6) and has(buxg, T6, q_=W6), "11 kiruvchida T6 bor (qidiruvda ham)")
    ok(detail(akad, T6)["perms"]["can_recall"] is True, "yuboruvchi (18): perms.can_recall = true (hech kim o'qimagan)")
    ok(post(reg, f"/api/portal/threads/{T6}/recall", {"note": "x"}).status_code == 403, "qabul qiluvchi (17) qaytarib ola olmaydi (403)")
    ok(post(sirtqi, f"/api/portal/threads/{T6}/recall").status_code == 403, "begona bo'lim (27) qaytarib ola olmaydi (403)")
    ok(post(rektor, f"/api/portal/threads/{T6}/recall").status_code == 403, "rahbariyat ham (yuboruvchi emas) qaytarib ola olmaydi (403)")
    r = post(akad, f"/api/portal/threads/{T6}/recall", {"note": "Xato bo'lim tanlangan"})
    ok(r.status_code == 200 and r.json()["status"] == "qaytarilgan", "18 xatni qaytarib oldi")
    ok(q("SELECT COUNT(*) FROM portal_recipients WHERE thread_id=?", (T6,))[0][0] == 0, "bazada qabul qiluvchi yozuvlari qolmadi")
    for c, n in ((buxg, 11), (reg, 17), (cc, 23)):
        ok(not has(c, T6) and not has(c, T6, "archive") and not has(c, T6, "inbox", "unread"), f"{n}: T6 kiruvchi va arxivda yo'q")
        ok(c.get("/api/portal/threads", params={"box": "inbox", "q": W6}).json()["total"] == 0, f"{n}: qidiruvda (FTS) T6 topilmaydi")
        rr = c.get(f"/api/portal/threads/{T6}")
        ok(rr.status_code == 410 and "qaytarib olingan" in rr.json()["detail"], f"{n}: yozishmani ochish 410 «qaytarib olingan»")
        cn = lst(c, limit=1)["counts"]
        ok(cn["inbox"] == lst(c, "inbox", limit=1)["total"] and cn["archive"] == lst(c, "archive", limit=1)["total"], f"{n}: hisoblagichlar ro'yxat bilan mos")
    ok(lst(buxg, limit=1)["counts"]["inbox"] == inbox_b0, "11: counts.inbox avvalgi holatga qaytdi")
    ok(not any(x["link"] == {"view": "portal", "thread": T6} for x in buxg.get("/api/notifications").json()["items"]), "11 bildirishnomalarida T6 yo'q")
    ok(not any(x["thread_id"] == T6 for x in buxg.get("/api/portal/reminders").json()["items"]), "11 eslatmalarida T6 yo'q")
    a6 = item(akad, T6, "archive")
    ok(a6 is not None and a6["status"] == "qaytarilgan" and a6["recalled"] and not has(akad, T6, "sent"), "18: T6 Arxivda (qaytarilgan), Yuborilganlarda yo'q")
    ok([x["unit"] for x in a6["recipients"]] == ["talabalar", "buxgalteriya"], "arxiv ro'yxatida qabul qiluvchilar ko'rsatiladi")
    d = detail(akad, T6)
    ok(d["status"] == "qaytarilgan" and d["recalled"] and [x["unit"] for x in d["recalled"]["recipients"]] == ["talabalar", "buxgalteriya"]
       and d["recalled"]["due"] == D3 and d["recalled"]["note"] == "Xato bo'lim tanlangan", "detail: recalled (qabul qiluvchilar, muddat, izoh)")
    P = d["perms"]
    ok(P["can_resend"] and not P["can_reopen"] and not P["can_reply"] and not P["can_recall"] and not P["can_change_due"] and not d["recipients"], "perms: can_resend, qolganlari yo'q")
    ok(any(m["kind"] == "tizim" and m["body"].startswith("Xat qaytarib olindi") for m in d["messages"]), "tizim yozuvi «Xat qaytarib olindi»")
    ok(post(akad, f"/api/portal/threads/{T6}/reply", {"body": "x"}).status_code == 409, "qaytarilgan xatga javob 409")
    ok(post(akad, f"/api/portal/threads/{T6}/reopen").status_code == 409, "qaytarilgan xatni qayta ochish 409")
    ok(post(akad, f"/api/portal/threads/{T6}/recall").status_code == 409, "qayta qaytarib olish 409")
    ok(post(rektor, f"/api/portal/threads/{T6}/resolve", {"text": "x", "units": ["buxgalteriya"]}).status_code == 409, "qaytarilgan xatga rezolyutsiya 409")
    ar = item(rektor, T6, "all")
    ok(ar is not None and ar["recalled"], "rektor «Barchasi»: T6 «qaytarilgan» belgisi bilan")
    ok(lst(rektor, "all", limit=1)["total"] == q("SELECT COUNT(*) FROM portal_threads")[0][0], "box=all total = COUNT(*) (qaytarilgan ham)")
    # «Tahrirlab qayta yuborish»: mavjud qoralama API orqali
    r = akad.put("/api/portal/drafts", json={"subject": d["subject"], "body": d["messages"][0]["body"], "to": [x["unit"] for x in d["recalled"]["recipients"]], "due": D3})
    ok(r.status_code == 200, "qaytarilgan xatdan qoralama yaratildi"); MY_DRAFTS.append((akad, r.json()["id"]))
    T7, REF7 = new_thread(akad, "T7 o'qilgan", ["talabalar"])
    detail(reg, T7)                    # 17 (talabalar rahbari) o'qidi
    ok(detail(akad, T7)["perms"]["can_recall"] is False, "o'qilgandan keyin perms.can_recall = false")
    r = post(akad, f"/api/portal/threads/{T7}/recall")
    ok(r.status_code == 409 and r.json()["detail"] == "Xat o'qilgan — qaytarib bo'lmaydi. Yozishmani yopishingiz mumkin.", "o'qilgan xatni qaytarish 409 (aniq matn)")
    ok(has(reg, T7) and q("SELECT status FROM portal_threads WHERE id=?", (T7,))[0][0] == "ochiq", "rad etilgan qaytarish yozishmani o'zgartirmadi")
    T8, _ = new_thread(akad, "T8 rezolyutsiyali", ["talabalar"])
    ok(post(rektor, f"/api/portal/threads/{T8}/resolve", {"text": "Ko'rib chiqilsin", "units": ["buxgalteriya"]}).status_code == 200, "T8 ga rezolyutsiya (o'qilmasdan)")
    ok(post(akad, f"/api/portal/threads/{T8}/recall").status_code == 409, "rezolyutsiya qo'yilgan xatni qaytarish 409")

    # ============================================================== 15b. Bo'lim xodimi: Rektorat kotibi
    print("— 15b. Rektorat kotibi — faqat shaxsan unga tegishli xatlar —")
    TK, _ = new_thread(akad, "TK rektoratga", ["rektorat"])
    ok(has(rektor, TK) and not has(kotib, TK) and kotib.get(f"/api/portal/threads/{TK}").status_code == 403,
       "rektoratga kelgan xat: rektor (rahbar) ko'radi, kotib (xodim) — yo'q (403)")
    ok(post(rektor, f"/api/portal/threads/{TK}/assign", {"user_id": 20}).status_code == 200 and has(kotib, TK), "rektor kotibga biriktirdi — kotib ko'radi")
    ok(kotib.get("/api/portal/summary").json()["action"] >= 1, "kotib: «ishim» hisoblagichida biriktirilgan xat")
    TK2, _ = new_thread(kotib, "TK2 kotibdan", ["akademik"])
    ok(has(kotib, TK2, "sent"), "kotib o'zi yuborgan xatni ko'radi")

    # ============================================================== 15c. «Ma'lumot so'rovi» → topshiriq (directives)
    print("— 15c. Ma'lumot so'rovi → topshiriq —")
    u18 = akad.get("/api/portal/units").json()
    ok("kaf2" in u18["directive_units"] and "buxgalteriya" not in u18["directive_units"], "Akademik bo'lim: topshiriq beriladigan bo'limlar — kafedralar")
    r = post(akad, "/api/portal/threads", {"subject": f"Ma'lumot so'rovi test {STAMP}", "body": "O'qituvchilar yuklamasi bo'yicha ma'lumot bering.",
                                          "to": ["kaf2", "buxgalteriya"], "kind": "sorov", "due": D5})
    ok(r.status_code == 200 and r.json()["id"] and len(r.json()["directives"]) == 1 and r.json()["directives"][0]["unit"] == "kaf2",
       "so'rov: kafedraga — topshiriq, vakolatdan tashqari Buxgalteriyaga — xat")
    TSQ, DSQ = r.json()["id"], r.json()["directives"][0]["id"]; MY_THREADS.append(TSQ)
    row = q("SELECT origin, unit, issuer_user, src, status, due_at FROM tasks WHERE id=?", (DSQ,))[0]
    ok(row[0] == "topshiriq" and row[1] == "kaf2" and row[2] == 18 and row[3] == f"portal:{TSQ}" and row[5].startswith(D5), "topshiriq: kaf2, bergan 18, manba portal:<xat>")
    ok([x["unit"] for x in detail(akad, TSQ)["recipients"]] == ["buxgalteriya"] and detail(akad, TSQ)["directives"][0]["id"] == DSQ,
       "xatda faqat Buxgalteriya qabul qiluvchi; topshiriq xatga bog'langan")
    ok(kaf.get(f"/api/dir/{DSQ}").status_code == 200 and any(x["link"] == {"view": "tasks", "directive": DSQ} for x in kaf.get("/api/mywork").json()["items"]),
       "kafedra mudiri (#31) topshiriqni ochadi va «Mening vazifalarim»da ko'radi")
    ok(post(kaf, f"/api/dir/{DSQ}/status", {"status": "bajarildi", "result": "Ma'lumot ilova qilindi"}).status_code == 200
       and post(akad, f"/api/dir/{DSQ}/review", {"decision": "qabul"}).status_code == 200, "kafedra natija yubordi, Akademik bo'lim qabul qildi")
    r = post(buxg, "/api/portal/threads", {"subject": f"So'rov vakolatsiz {STAMP}", "body": "x", "to": ["talabalar"], "kind": "sorov"})
    ok(r.status_code == 200 and r.json()["id"] and not r.json()["directives"], "vakolati yo'q bo'lim so'rovi — oddiy xat (topshiriq yaratilmaydi)")
    MY_THREADS.append(r.json()["id"])
    DIRS_TO_DROP.append(DSQ)

    # ============================================================== 16. Muddatni o'zgartirish
    print("— 16. Muddatni o'zgartirish —")
    UN = {u["key"]: u["name"] for u in reg.get("/api/portal/units").json()["units"]}
    T9, REF9 = new_thread(akad, "T9 muddat", ["talabalar", "buxgalteriya", "sirtqi"], due=D2)
    ok(detail(akad, T9)["perms"]["can_change_due"] and not detail(buxg, T9)["perms"]["can_change_due"], "perms.can_change_due: yuboruvchida bor, qabul qiluvchida yo'q")
    ok(detail(pro, T9)["perms"]["can_change_due"], "rahbariyat (prorektor): can_change_due")
    for c, n in ((buxg, 11), (reg, 17)):
        ok(post(c, f"/api/portal/threads/{T9}/due", {"due": D5}).status_code == 403, f"{n} (qabul qiluvchi) muddatni o'zgartira olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": YDAY}).status_code == 400, "o'tgan sana 400")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": "15-11-2026"}).status_code == 400, "noto'g'ri sana 400")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": ""}).status_code == 400, "bo'sh sana 400")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": D5, "units": ["kadrlar"]}).status_code == 400, "qabul qiluvchi bo'lmagan bo'lim 400")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": D2}).status_code == 400, "o'zgarmagan muddat 400")
    r = post(akad, f"/api/portal/threads/{T9}/due", {"due": D3, "note": "ma'lumot to'planmoqda"})
    ok(r.status_code == 200 and r.json()["old"] == D2 and r.json()["due"] == D3, "18: barcha bo'limlar uchun muddat D2 → D3")
    d = detail(akad, T9)
    ok(d["due"] == D3 and all(x["due"] == D3 for x in d["recipients"]), "yozishma va barcha qabul qiluvchilar muddati D3")
    ok(any(m["kind"] == "tizim" and m["body"] == f"Muddat o'zgartirildi: {dmy(D2)} → {dmy(D3)} (ma'lumot to'planmoqda)" for m in d["messages"]),
       f"tizim yozuvi «Muddat o'zgartirildi: {dmy(D2)} → {dmy(D3)} (izoh)»")
    ok(item(buxg, T9)["due"] == D3, "11 ro'yxatida muddat D3")
    ok(post(reg, f"/api/portal/threads/{T9}/reply", {"body": "Registrator: bajarildi."}).status_code == 200, "17 javob berdi")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": D5, "units": ["talabalar"]}).status_code == 400, "javob bergan bo'lim muddatini o'zgartirish 400")
    r = post(akad, f"/api/portal/threads/{T9}/due", {"due": D5, "units": ["buxgalteriya"]})
    ok(r.status_code == 200 and r.json()["units"] == ["buxgalteriya"], "faqat buxgalteriya uchun D5")
    d = detail(akad, T9)
    ok(rcp(d, "buxgalteriya")["due"] == D5 and rcp(d, "sirtqi")["due"] == D3 and d["due"] == D3, "buxgalteriya D5, sirtqi D3, yozishma D3")
    ok(any(m["kind"] == "tizim" and m["body"] == f"Muddat o'zgartirildi ({UN['buxgalteriya']}): {dmy(D3)} → {dmy(D5)}" for m in d["messages"]), "tizim yozuvida bo'lim nomi")
    ok(item(buxg, T9)["due"] == D5 and item(sirtqi, T9)["due"] == D3, "11 da D5, 27 da D3")
    r = post(pro, f"/api/portal/threads/{T9}/due", {"due": D7})
    ok(r.status_code == 200 and r.json()["old"] is None, "prorektor (rahbariyat) hammasi uchun D7 (avvalgi — turli muddatlar)")
    d = detail(akad, T9)
    ok(rcp(d, "buxgalteriya")["due"] == D7 and rcp(d, "sirtqi")["due"] == D7 and d["due"] == D7, "kutilayotganlarning hammasi D7")
    ok(any(m["body"] == f"Muddat o'zgartirildi: turli muddatlar → {dmy(D7)}" for m in d["messages"]), "«turli muddatlar → …» yozuvi")
    ok(post(akad, f"/api/portal/threads/{T9}/close", {"note": "test"}).status_code == 200, "T9 yopildi")
    ok(post(akad, f"/api/portal/threads/{T9}/due", {"due": D7}).status_code == 409, "yopilgan yozishmada muddat 409")

    # ============================================================== 17. Rezolyutsiyani tahrirlash va bekor qilish
    print("— 17. Rezolyutsiyani tahrirlash va bekor qilish —")
    T10, REF10 = new_thread(akad, "T10 rezolyutsiya tahriri", ["talabalar"], due=D3)
    r = post(rektor, f"/api/portal/threads/{T10}/resolve", {"text": "Birgalikda ko'rib chiqilsin", "units": ["buxgalteriya", "sirtqi"], "lead": "buxgalteriya", "due": D3})
    RID10 = r.json()["id"]
    z = detail(rektor, T10)["resolutions"][0]
    ok(z["can_edit"] and z["can_cancel"] and not detail(pro, T10)["resolutions"][0]["can_edit"], "can_edit/can_cancel: muallifda bor, prorektorda yo'q")
    E = f"/api/portal/threads/{T10}/resolutions/{RID10}"
    body = {"text": "Birgalikda ko'rib chiqilsin", "units": ["buxgalteriya", "kadrlar"], "lead": "kadrlar", "due": D5}
    for c, n in ((pro, "prorektor"), (reg, 17), (buxg, 11)):
        ok(post(c, f"{E}/edit", body).status_code == 403 and post(c, f"{E}/cancel", {}).status_code == 403, f"{n}: tahrirlash/bekor qilish 403")
    ok(post(rektor, f"{E}/edit", {**body, "due": YDAY}).status_code == 400, "o'tgan muddat bilan tahrir 400")
    ok(post(rektor, f"{E}/edit", {**body, "units": ["akademik"]}).status_code == 400, "yuboruvchini ijrochi qilish 400")
    ok(post(rektor, f"{E}/edit", {"text": "Birgalikda ko'rib chiqilsin", "units": ["buxgalteriya", "sirtqi"], "lead": "buxgalteriya", "due": D3}).status_code == 400, "o'zgarishsiz tahrir 400")
    ok(post(rektor, f"/api/portal/threads/{T10}/resolutions/999999/edit", body).status_code == 404, "mavjud bo'lmagan rezolyutsiya 404")
    r = post(rektor, f"{E}/edit", body)
    ok(r.status_code == 200 and r.json()["added"] == ["kadrlar"] and r.json()["removed"] == ["sirtqi"], "tahrir: +kadrlar, −sirtqi, mas'ul kadrlar, muddat D5")
    d = detail(rektor, T10); z = d["resolutions"][0]
    ok([x["unit"] for x in z["units"]] == ["buxgalteriya", "kadrlar"] and z["lead_unit"] == "kadrlar" and z["due"] == D5 and z["edited_at"], "rezolyutsiya kartasi yangilandi")
    ok(rcp(d, "sirtqi") is None, "sirtqi (shu rezolyutsiya bilan qo'shilgan, javob bermagan) qabul qiluvchilardan olib tashlandi")
    rk, rb = rcp(d, "kadrlar"), rcp(d, "buxgalteriya")
    ok(rk and rk["via"] == "rezolyutsiya" and rk["status"] == "yangi" and rk["due"] == D5 and rk["lead"], "kadrlar: yangi, via rezolyutsiya, D5, mas'ul")
    ok(rb["due"] == D5 and not rb["lead"], "buxgalteriya: muddat D5 ga o'tdi, mas'ul emas")
    em = [m for m in d["messages"] if m["kind"] == "rezolyutsiya" and (m["meta"] or {}).get("edit")]
    ok(len(em) == 1 and em[0]["body"].startswith(f"Rezolyutsiya o'zgartirildi: muddat {dm(D3)} → {dm(D5)}; qo'shildi: {UN['kadrlar']}; olib tashlandi: {UN['sirtqi']}"),
       f"o'zgarish xabari: {em[0]['body'].splitlines()[0] if em else '—'}")
    ok(not has(sirtqi, T10) and has(kadr, T10) and item(kadr, T10)["due"] == D5, "27 kiruvchisida yo'q, 12 (kadrlar) kiruvchisida D5 bilan")
    ok(post(buxg, f"/api/portal/threads/{T10}/reply", {"body": "Buxgalteriya: hisob ilova qilindi."}).status_code == 200, "11 javob berdi")
    r = post(rektor, f"{E}/edit", {"text": "Kadrlar bo'limi yakunlasin", "units": ["kadrlar", "talabalar"], "lead": "kadrlar", "due": D5})
    ok(r.status_code == 200 and r.json()["kept"] == ["buxgalteriya"] and r.json()["added"] == ["talabalar"], "javob bergan buxgalteriya olib tashlansa — yozishmada qoladi (kept)")
    d = detail(rektor, T10)
    ok(rcp(d, "buxgalteriya")["status"] == "javob berilgan" and rcp(d, "buxgalteriya")["due"] == D3 and not rcp(d, "buxgalteriya")["lead"],
       "buxgalteriya: javob saqlandi, shaxsiy muddat bekor (yozishma muddati D3)")
    ok(rcp(d, "talabalar")["due"] == D5 and rcp(d, "talabalar")["via"] == "xat", "asl qabul qiluvchi talabalar ijrochi bo'ldi (D5), via=xat")
    ok(d["resolutions"][0]["text"] == "Kadrlar bo'limi yakunlasin", "ko'rsatma matni yangilandi")
    r = post(rektor, f"{E}/edit", {"text": "Kadrlar bo'limi yakunlasin", "units": ["kadrlar"], "lead": "kadrlar", "due": D5})
    ok(r.status_code == 200 and r.json()["kept"] == ["talabalar"], "asl qabul qiluvchi (talabalar) olib tashlansa — qoladi")
    d = detail(rektor, T10)
    ok(rcp(d, "talabalar") and rcp(d, "talabalar")["due"] == D3, "talabalar shaxsiy muddati bekor qilindi (D3)")
    c0 = lst(rektor, "control", limit=1)["counts"]["control"]
    ok(has(rektor, T10, "control"), "T10 rektor «Nazorat» qutisida")
    r = post(rektor, f"{E}/cancel", {"note": "Masala boshqa tartibda hal qilinadi"})
    ok(r.status_code == 200 and r.json()["removed"] == ["kadrlar"], "rektor rezolyutsiyani bekor qildi: kadrlar (javob bermagan) chiqarildi")
    d = detail(rektor, T10); z = d["resolutions"][0]
    ok(z["state"] == "bekor" and not z["can_edit"] and not z["can_cancel"] and not z["can_close"] and not z["overdue"], "holat «bekor», amallar yo'q")
    ok(rcp(d, "kadrlar") is None and rcp(d, "talabalar") and rcp(d, "buxgalteriya"), "kadrlar chiqarildi, boshqalar qoldi")
    ok(any(m["kind"] == "tizim" and m["body"].startswith("Rezolyutsiya bekor qilindi: Masala boshqa tartibda hal qilinadi") for m in d["messages"]), "tizim yozuvi «Rezolyutsiya bekor qilindi»")
    ok(lst(rektor, "control", limit=1)["counts"]["control"] == c0 - 1, f"counts.control kamaydi ({c0} → {c0 - 1})")
    ok(not has(rektor, T10, "control"), "bekor qilingan rezolyutsiya «Nazorat» qutisida yo'q")
    ok(not item(rektor, T10, "all")["resolution"], "ro'yxatda «Rezolyutsiya» belgisi yo'q")
    ok(not has(kadr, T10), "12 (kadrlar) kiruvchisida T10 yo'q")
    ok(not any(x["thread_id"] == T10 and x["who"] == "nazorat" for x in rektor.get("/api/portal/reminders").json()["items"]), "rektor eslatmalarida T10 nazorati yo'q")
    ok(post(rektor, f"{E}/edit", body).status_code == 409 and post(rektor, f"{E}/cancel", {}).status_code == 409, "bekor qilingandan keyin tahrir/bekor 409")
    ok(post(rektor, f"{E}/close").status_code == 409, "bekor qilingan rezolyutsiyani yechish 409")
    # bir bo'lim ikki rezolyutsiyada: biri bekor qilinsa — ikkinchisining muddati va mas'ulligi tiklanadi
    T11, _ = new_thread(akad, "T11 ikki rezolyutsiya", ["talabalar"])
    Ra = post(rektor, f"/api/portal/threads/{T11}/resolve", {"text": "Birinchi", "units": ["buxgalteriya", "sirtqi"], "lead": "sirtqi", "due": D5}).json()["id"]
    Rb = post(rektor, f"/api/portal/threads/{T11}/resolve", {"text": "Ikkinchi", "units": ["buxgalteriya"], "due": D3}).json()["id"]
    rb = rcp(detail(rektor, T11), "buxgalteriya")
    ok(rb["due"] == D3 and rb["lead"], "ikkinchi rezolyutsiya: buxgalteriya D3, mas'ul")
    r = post(rektor, f"/api/portal/threads/{T11}/resolutions/{Rb}/cancel", {})
    rb = rcp(detail(rektor, T11), "buxgalteriya")
    ok(r.status_code == 200 and r.json()["removed"] == [] and rb and rb["due"] == D5 and not rb["lead"],
       "ikkinchisi bekor: buxgalteriya qoldi, birinchi rezolyutsiya muddati (D5) tiklandi, mas'ul emas")
    ok(post(rektor, f"/api/portal/threads/{T11}/resolutions/{Ra}/edit", {"text": "Birinchi", "units": ["sirtqi"], "lead": "sirtqi", "due": D5}).json()["removed"] == ["buxgalteriya"],
       "birinchisidan olib tashlansa — endi qabul qiluvchilardan chiqariladi")
    # muddati o'tgan nazorat bekor qilinsa — control_overdue hisobiga kirmaydi (demo bazadagi rezolyutsiyalar o'zgartirilmaydi)
    cn = lst(rektor, "control", limit=1)["counts"]
    exp = q("""SELECT COUNT(*) FROM portal_resolutions z JOIN portal_threads t ON t.id=z.thread_id WHERE z.author_unit='rektorat' AND z.state='nazoratda'
               AND t.status='ochiq' AND z.due<? AND EXISTS(SELECT 1 FROM json_each(z.units) j JOIN portal_recipients r ON r.thread_id=z.thread_id
               AND r.unit=j.value WHERE r.status IN ('yangi','o''qilgan'))""", (TODAY.isoformat(),))[0][0]
    ok(cn["control_overdue"] == exp, f"counts.control_overdue faqat nazoratdagilar ({exp})")

    # ============================================================== 18. Bo'limlar katalogi va tuzilmani tahrirlash
    print("— 18. Bo'limlar katalogi —")
    o = reg.get("/api/portal/org").json()
    ok(o["can_edit"] is False and rektor.get("/api/portal/org").json()["can_edit"] and ithead.get("/api/portal/org").json()["can_edit"], "can_edit: rektor va IT boshlig'i")
    ok(not pro.get("/api/portal/org").json()["can_edit"] and not akad.get("/api/portal/org").json()["can_edit"], "prorektor va xodimlarda can_edit yo'q")
    ou = {u["key"]: u for u in o["units"]}
    ok({g["key"] for g in o["groups"]} == {"rahbariyat", "bolim", "fakultet", "kafedra"} and len(ou) >= 30, f"guruhlar va bo'limlar ({len(ou)})")
    t_ = ou["talabalar"]
    ok(t_["head_user"] == 17 and t_["members_count"] == len(t_["members"]) >= 2 and {17, 23} <= {m["id"] for m in t_["members"]} and t_["members"][0]["head"],
       f"talabalar: rahbar 17, {t_['members_count']} xodim (17, 23 va boshqalar)")
    ok(t_["curator"] == "prorektor_oquv" and "O'quv" in t_["curator_name"] and t_["info"]["place"], "talabalar: kurator, joylashuv")
    ok(ou["kadrlar"]["curator"] is None and ou["it"]["curator"] is None, "kadrlar, IT — rektorga bevosita (kurator yo'q)")
    ok(all(ou[k]["curator"] == "prorektor_moliya" for k in ("marketing", "xarid") if k in ou), "marketing, xarid — moliya prorektori")
    ok({c_["key"] for c_ in o["curators"]} >= {"prorektor_oquv", "prorektor_ilmiy", "prorektor_moliya"}, "kurator tanlovi — prorektorlar")
    ORG0 = {k: {"head_user": ou[k]["head_user"], "curator": ou[k]["curator"]} for k in ("talabalar", "xalqaro")}
    for c, n in ((reg, 17), (akad, 18), (pro, "prorektor"), (iteng, 22)):
        ok(c.put("/api/portal/org/talabalar", json={"head_user": 23}).status_code == 403, f"{n}: tuzilmani o'zgartirish 403")
    ok(rektor.put("/api/portal/org/nomalum", json={"curator": None}).status_code == 404, "noma'lum bo'lim 404")
    ok(rektor.put("/api/portal/org/talabalar", json={"head_user": 11}).status_code == 400, "boshqa bo'lim xodimini rahbar qilish 400")
    ok(rektor.put("/api/portal/org/talabalar", json={"curator": "kadrlar"}).status_code == 400, "prorektor bo'lmagan kurator 400")
    ok(rektor.put("/api/portal/org/rektorat", json={"curator": "prorektor_oquv"}).status_code == 400, "rahbariyatga kurator 400")
    ORG_RESTORE["talabalar"] = ORG0["talabalar"]
    r = rektor.put("/api/portal/org/talabalar", json={"head_user": 23})
    ok(r.status_code == 200 and r.json()["changes"], "rektor: talabalar rahbari → 23")
    ok(cc.get("/api/portal/units").json()["is_head"] and not reg.get("/api/portal/units").json()["is_head"], "is_head darhol o'zgardi (23 rahbar)")
    ok(next(u for u in reg.get("/api/portal/org").json()["units"] if u["key"] == "talabalar")["head"].startswith("Rahimova"), "katalogda rahbar ismi yangilandi")
    ok(rektor.put("/api/portal/org/talabalar", json=ORG0["talabalar"]).status_code == 200 and reg.get("/api/portal/units").json()["is_head"], "rahbar asl holiga qaytdi (17)")
    ORG_RESTORE["xalqaro"] = ORG0["xalqaro"]
    r = ithead.put("/api/portal/org/xalqaro", json={"curator": "prorektor_oquv"})
    ok(r.status_code == 200, "IT boshlig'i: Xalqaro hamkorlik kuratori → o'quv prorektori")
    ok("xalqaro" in pro.get("/api/portal/units").json()["curated"], "prorektor_oquv «Yo'nalishim»ga xalqaro qo'shildi")
    ok(q("SELECT curator, curator_manual FROM org_units WHERE key='xalqaro'")[0] == ("prorektor_oquv", 1), "bazada curator_manual=1")
    sp = subprocess.run([sys.executable, "-c", "from app import portal, db; portal.sync_units(db._open())"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    ok(sp.returncode == 0, f"sync_units (server qayta ishga tushgandagidek) bajarildi {sp.stderr[-200:]}")
    ok(q("SELECT curator, curator_manual FROM org_units WHERE key='xalqaro'")[0] == ("prorektor_oquv", 1), "qo'lda tayinlangan kurator sync_units dan keyin saqlandi")
    ok(q("SELECT head_user FROM org_units WHERE key='talabalar'")[0][0] == 17, "rahbar (head_user) sync_units dan keyin saqlandi")
    r = ithead.put("/api/portal/org/xalqaro", json=ORG0["xalqaro"])
    ok(r.status_code == 200 and q("SELECT curator, curator_manual FROM org_units WHERE key='xalqaro'")[0] == ("prorektor_ilmiy", 0), "kurator asl holiga qaytdi (curator_manual=0)")
    ORG_RESTORE.clear()
    ok("xalqaro" not in pro.get("/api/portal/units").json()["curated"], "prorektor_oquv yo'nalishidan xalqaro chiqdi")

    # ============================================================== 19. Rahbar qutilari
    print("— 19. Rahbar qutilari —")
    js = httpx.get(f"{B}/portal.js").text
    ok(re.search(r'U\.can_resolve && \["control", "Nazorat", [^\]]*, 1,', js) is not None, "portal.js: «Nazorat» rezolyutsiya qo'yuvchilar uchun asosiy segment")
    for c, n, lead in ((rektor, "rektor", True), (pro, "prorektor", True), (reg, 17, False)):
        u = c.get("/api/portal/units").json(); cn = lst(c, limit=1)["counts"]
        ok(u["can_resolve"] is lead and (("control" in cn and "control_overdue" in cn) if lead else "control" not in cn), f"{n}: can_resolve={lead}, counts.control")

    students_and_review()

    # ============================================================== 14. Audit
    print("— 20. Audit —")
    rows = q("SELECT action, detail, allowed, user_id FROM audit_log WHERE id>? AND resource='portal'", (AUDIT0,))
    def seen(action, ref, uid=None, allowed=1):
        return any(a == action and ref in (dt_ or "") and al == allowed and (uid is None or u_ == uid) for a, dt_, al, u_ in rows)
    ok(seen("portal: rezolyutsiya qo'yildi", REF2, 2), "audit: rezolyutsiya qo'yildi (rektor)")
    ok(seen("portal: rezolyutsiya nazoratdan yechildi", REF2, 2), "audit: rezolyutsiya nazoratdan yechildi")
    ok(seen("portal: ijrochi tayinlandi", REF1, 23) and seen("portal: ijrochi tayinlandi", REF1, 17), "audit: ijrochi tayinlandi (23 va 17)")
    ok(seen("portal: xat yo'naltirildi", REF1, 17), "audit: xat yo'naltirildi")
    ok(seen("portal: yozishma yopildi", REF1, 18) and seen("portal: yozishma qayta ochildi", REF1, 18), "audit: yopildi / qayta ochildi")
    ok(seen("portal: xat yuborildi", REF1, 18), "audit: xat yuborildi")
    ok(seen("portal: rezolyutsiya", REF2, 17, 0), "audit: 17 ning rezolyutsiya urinishi rad (allowed=0)")
    ok(seen("portal: yozishmani yopish", REF1, 17, 0), "audit: 17 ning yopish urinishi rad (allowed=0)")
    ok(seen("portal: yozishmani ochish", f"{REF1}", 11, 0), "audit: 11 ning begona yozishmani ochishi rad (allowed=0)")
    ok(any(a == "portal: fayl yuklab olindi" and al == 1 for a, _, al, _u in rows), "audit: fayl yuklab olindi")
    ok(any(a.startswith("portal: all qutisi") and al == 0 and u_ == 17 for a, _, al, u_ in rows), "audit: 17 ning box=all urinishi rad")
    ok(seen("portal: xat qaytarib olindi", REF6, 18) and seen("portal: xatni qaytarib olish", REF7, 18, 0), "audit: qaytarib olindi / o'qilgan xatni qaytarish rad")
    ok(seen("portal: muddat o'zgartirildi", REF9, 18) and seen("portal: muddat o'zgartirildi", REF9, 3) and seen("portal: muddatni o'zgartirish", REF9, 11, 0),
       "audit: muddat o'zgartirildi (18, prorektor), 11 urinishi rad")
    ok(seen("portal: rezolyutsiya o'zgartirildi", REF10, 2) and seen("portal: rezolyutsiya bekor qilindi", REF10, 2), "audit: rezolyutsiya o'zgartirildi / bekor qilindi")
    ok(seen("portal: rezolyutsiyani o'zgartirish", REF10, 3, 0), "audit: prorektorning tahrir urinishi rad")
    ok(seen("portal: tashkiliy tuzilma o'zgartirildi", "Registrator", 2) and seen("portal: tashkiliy tuzilmani o'zgartirish", "talabalar", 17, 0),
       "audit: tuzilma o'zgartirildi (rektor), 17 urinishi rad")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
    print(f"\nJami tekshiruvlar: {N[0]}" + (f" · backend xatolari: {len(SOFT)}" if SOFT else " · hammasi o'tdi"))
    for s_ in SOFT: print("  ✗", s_)
    for s_ in NOTES: print("  ⚠", s_)
    sys.exit(1 if SOFT else 0)
