import os
"""«O'quv dasturlari» (app/syllabus.py, /api/syllabus/*): uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_syllabus.py
Qayta ishga tushirsa bo'ladi: test o'zi yaratgan sillabus va kafedra so'rovini oxirida bazadan o'chiradi (demo holat o'zgarmaydi;
faqat audit jurnali yozuvlari qoladi).
Tekshiriladi: RBAC (akademik / prorektor / rektor / kafedra / o'qituvchi; boshqa lavozimlar — 403), to'liq oqim
(so'rash → biriktirish → DOCX yuklash va mavzularni ajratish → topshirish → tekshiruv → qaytarish → qayta topshirish → kelishuv
kafedra → Akademik bo'lim → prorektor tasdig'i), tekshiruv natijalari, versiyalar, tarix, audit, yuklama kalkulyatori
(qayta hisoblash, XLSX, Hujjatlar markazi DOCX), kafedra so'rovlari (javob → qaytarish → qayta javob → qabul), «Mening vazifalarim» va bildirishnomalar.
"""
import io, json, sqlite3, sys, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); from app import clock as CLK   # noqa: E402 — institut vaqti (ISFT_CORE_TZ / ISFT_CORE_FAKE_TODAY), server bilan bir xil
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
AK, PRO, REK, KAF4, KAF2, TCH, BUX = 18, 3, 2, 14, 31, 15, 11

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
    r = q(sql, args); return r[0] if r else None

def audit_has(uid, action_like, after_id):
    return one("SELECT 1 FROM audit_log WHERE id>? AND user_id=? AND resource='syllabus' AND action LIKE ?", (after_id, uid, action_like)) is not None

def make_docx(topics):
    from docx import Document
    d = Document(); d.add_heading("Fan dasturi (sillabus)", 1)
    d.add_paragraph("Mavzular rejasi")
    t = d.add_table(rows=1, cols=7)
    for i, h in enumerate(["№", "Mavzu nomi", "Ma'ruza", "Amaliy", "Seminar", "Laboratoriya", "Mustaqil ta'lim"]): t.rows[0].cells[i].text = h
    for i, (title, l, p, s) in enumerate(topics, 1):
        r = t.add_row().cells
        for j, v in enumerate([str(i), title, str(l), str(p), "0", "0", str(s)]): r[j].text = v
    d.add_paragraph("Adabiyotlar")
    for x in ["1. Mankiw N.G. Principles of Economics. Cengage, 2021.", "2. Statistika: darslik. — T.: Iqtisodiyot, 2023.", "3. Ekonometrika asoslari. — T.: ISFT, 2024."]:
        d.add_paragraph(x)
    b = io.BytesIO(); d.save(b); return b.getvalue()

# ---------------------------------------------------------------------------------------------
print("— 0. Kirishsiz so'rov, sahifa fayllari")
ok(httpx.get(B + "/api/syllabus/board").status_code == 401, "kirishsiz /api/syllabus/board → 401")
idx = httpx.get(B + "/").text
ok('data-v="syllabus"' in idx and 'id="v-syllabus"' in idx and 'src="syllabus.js"' in idx, "index.html: menyu, bo'lim va skript ulangan")
ok(httpx.get(B + "/syllabus.js").status_code == 200 and httpx.get(B + "/syllabus.css").status_code == 200, "syllabus.js va syllabus.css beriladi")
ok(one("SELECT COUNT(*) FROM syl_ref WHERE sample=1")[0] >= 60, "tayanch OTM katalogi (namuna) to'ldirilgan")
ok(q("SELECT DISTINCT status FROM syl_items") and {r[0] for r in q("SELECT DISTINCT status FROM syl_items")} >= {"tasdiqlangan", "qaytarilgan", "jarayonda", "tekshiruvda", "kelishuvda", "soralgan"},
   "demo holat: barcha bosqichlardagi sillabuslar bor")

print("\n— 1. RBAC: kim nimani ko'radi")
C = {u: S(u) for u in (AK, PRO, REK, KAF4, KAF2, TCH, BUX)}
tot = one("SELECT COUNT(*) FROM syl_items")[0]
for u in (AK, PRO, REK):
    d = C[u].get("/api/syllabus/board").json()
    ok(d["counts"]["total"] == tot, f"#{u}: butun institut — {tot} ta sillabus")
d = C[KAF4].get("/api/syllabus/board").json()
ok(d["counts"]["total"] == one("SELECT COUNT(*) FROM syl_items WHERE department_id=4")[0] and all(i["department_id"] == 4 for i in d["items"]), "kafedra mudiri (kaf4): faqat o'z kafedrasi")
d = C[KAF2].get("/api/syllabus/board").json()
ok(all(i["department_id"] == 2 for i in d["items"]), "kafedra mudiri (Biznes boshqaruvi): faqat o'z kafedrasi")
tid15 = one("SELECT teacher_id FROM users WHERE id=?", (TCH,))[0]
d = C[TCH].get("/api/syllabus/board").json()
ok(d["counts"]["total"] == one("SELECT COUNT(*) FROM syl_items WHERE teacher_id=?", (tid15,))[0] and all(i["teacher_id"] == tid15 for i in d["items"]), "o'qituvchi: faqat o'ziga biriktirilgan fanlar")
r = C[BUX].get("/api/syllabus/board"); ok(r.status_code == 403, "buxgalteriya → 403")
other = one("SELECT id FROM syl_items WHERE department_id!=4 LIMIT 1")[0]
ok(C[KAF4].get(f"/api/syllabus/items/{other}").status_code == 404, "kafedra mudiri boshqa kafedra sillabusini ocholmaydi (404)")
ok(C[TCH].get(f"/api/syllabus/items/{other}").status_code == 404, "o'qituvchi boshqa sillabusni ocholmaydi (404)")
ok(C[KAF4].get("/api/syllabus/catalog").status_code == 403, "kafedra mudiri sillabus so'ray olmaydi (katalog 403)")
ok(C[TCH].get("/api/syllabus/tasks").status_code == 403, "o'qituvchi kafedra so'rovlarini ko'rmaydi (403)")
ok(C[TCH].get("/api/syllabus/load?dept=4").status_code == 403, "o'qituvchi yuklama kalkulyatorini ochmaydi (403)")
ok(C[KAF4].get("/api/syllabus/load?dept=2").status_code == 403, "kafedra mudiri boshqa kafedra yuklamasini ochmaydi (403)")
ok(C[KAF4].get("/api/syllabus/load?dept=4").status_code == 200, "kafedra mudiri o'z kafedrasi yuklamasini ko'radi")
m = C[REK].get("/api/syllabus/meta").json()
ok(not m["can"]["request"] and not m["can"]["load_save"] and not m["can"]["tasks_create"], "rektor: faqat ko'rish (so'rash/saqlash/so'rov yo'q)")

print("\n— 2. To'liq oqim: so'rash → biriktirish → yuklash → tekshiruv → qaytarish → qayta topshirish → tasdiq")
a0 = one("SELECT MAX(id) FROM audit_log")[0]
cat = C[AK].get("/api/syllabus/catalog?dept=8").json()["pairs"]
cat = [p for p in cat if p["department_id"] == 8] or [p for p in C[AK].get("/api/syllabus/catalog").json()["pairs"] if p["subject"] not in ("Ingliz tili",)]
if not cat:   # barcha juftliklar so'ralgan — oldingi yugurishdan qolgan bo'lsa ham test o'z elementini yarata olishi uchun
    print("  (so'ralmagan fan qolmagan — test to'xtatildi)"); sys.exit(1)
pair = cat[0]
# 8-kafedra (Fundamental iqtisodiy fanlar) uchun so'ralmagan fan bo'lmasa — istalgan kafedra; kafedra mudiri foydalanuvchisini topamiz
dep = pair["department_id"]
head = one("SELECT id FROM users WHERE role='kafedra' AND department_id=?", (dep,))[0]
CH = S(head)
due = (CLK.today() + __import__("datetime").timedelta(days=10)).isoformat()
r = C[KAF4].post("/api/syllabus/request", json={"pairs": [{"subject": pair["subject"], "department_id": dep}], "due": due})
ok(r.status_code == 403, "kafedra mudiri sillabus so'ray olmaydi (403)")
r = C[AK].post("/api/syllabus/request", json={"pairs": [{"subject": pair["subject"], "department_id": dep}], "due": "2020-01-01"})
ok(r.status_code == 400, "o'tgan muddat bilan so'rov rad etiladi (400)")
r = C[AK].post("/api/syllabus/request", json={"pairs": [{"subject": pair["subject"], "department_id": dep}], "due": due, "note": "TEST: avtomatik test"})
ok(r.status_code == 200 and len(r.json()["created"]) == 1, f"Akademik bo'lim «{pair['subject']}» ({pair['department']}) sillabusini so'radi")
IID = r.json()["created"][0]
TASK_ID = None
DOCREG = []
try:
    r = C[AK].post("/api/syllabus/request", json={"pairs": [{"subject": pair["subject"], "department_id": dep}], "due": due})
    ok(r.status_code == 400, "takroriy so'rov yaratilmaydi")
    d = CH.get(f"/api/syllabus/items/{IID}").json()
    ok(d["item"]["status"] == "soralgan" and "assign" in d["actions"] and d.get("teachers"), "kafedra mudiri: «o'qituvchi biriktirish» amali va o'qituvchilar ro'yxati")
    ok(C[AK].get(f"/api/syllabus/items/{IID}").json()["actions"] == ["due", "remind"], "Akademik bo'lim: so'ralgan bosqichda faqat muddat/eslatma")
    mw = CH.get("/api/mywork").json()["items"]
    ok(any(it["source"] == "sillabus" and (it["link"].get("item") == IID or it["link"].get("status") == "soralgan") for it in mw), "«Mening vazifalarim»: kafedra mudirida biriktirish ishi paydo bo'ldi")
    tch = d["teachers"][0]["id"]
    r = C[AK].post(f"/api/syllabus/items/{IID}/assign", json={"teacher_id": tch}); ok(r.status_code == 403, "Akademik bo'lim o'qituvchini o'zi biriktirmaydi (403)")
    bad_t = one("SELECT id FROM teachers WHERE department_id!=? LIMIT 1", (dep,))[0]
    ok(CH.post(f"/api/syllabus/items/{IID}/assign", json={"teacher_id": bad_t}).status_code == 400, "boshqa kafedra o'qituvchisini biriktirib bo'lmaydi")
    ok(CH.post(f"/api/syllabus/items/{IID}/assign", json={"teacher_id": tch}).status_code == 200, "kafedra mudiri o'qituvchini biriktirdi")
    d = CH.get(f"/api/syllabus/items/{IID}").json()
    ok(d["item"]["status"] == "jarayonda" and {"edit", "submit"} <= set(d["actions"]), "holat: tayyorlanmoqda; kafedra mudiri ham tahrirlay oladi (o'qituvchi akkauntsiz bo'lsa)")
    ok(C[AK].put(f"/api/syllabus/items/{IID}/draft", json={"content": {"topics": []}}).status_code == 403, "Akademik bo'lim sillabus matnini tahrirlay olmaydi")
    # DOCX yuklash — jadvaldan mavzular ajratiladi
    refs = one("SELECT topics FROM syl_ref WHERE subject=? ORDER BY id LIMIT 1", (pair["subject"],))
    core = json.loads(refs[0]) if refs else [f"{pair['subject']}: {i}-mavzu" for i in range(1, 11)]
    norm = d["norm"]
    n = len(core)
    def spread(total): base = (total // 2 // n) * 2; rest = total - base * n; return [base + (2 if i < rest // 2 else 0) for i in range(n)]
    L, P, M = spread(norm["lecture"]), spread(norm["practice"] + norm["seminar"]), spread(norm["self"])
    bad = core[:-3] + ["Hujayra tuzilishi va funksiyalari"]
    blob = make_docx([(t, L[i % n], P[i % n], M[i % n]) for i, t in enumerate(bad)])
    r = CH.post(f"/api/syllabus/items/{IID}/upload", params={"name": "sillabus.docx"}, content=blob)
    ok(r.status_code == 200 and r.json()["found"] == len(bad), f"DOCX yuklandi: {r.json().get('found')} ta mavzu jadvaldan ajratildi")
    ok(r.json()["literature"] == 3, "DOCX: adabiyotlar ro'yxati ajratildi (3 ta)")
    chk = r.json()["check"]
    ok("Hujayra tuzilishi va funksiyalari" in chk["relevance"]["flagged"] if refs else True, "tekshiruv (a): begona mavzu «fanga mos emas» deb belgilandi")
    if refs:
        ok(chk["reference"]["available"] and chk["reference"]["sample"] and chk["reference"]["coverage"] < 100 and len(chk["reference"]["missing"]) >= 3,
           f"tekshiruv (b): tayanch OTM qamrovi {chk['reference']['coverage']}%, {len(chk['reference']['missing'])} ta yetishmayotgan mavzu (namuna katalog)")
    ok(not chk["hours"]["ok"], "tekshiruv (c): soatlar me'yorga mos emas (3 mavzu tushirilgan)")
    exe = CH.post(f"/api/syllabus/items/{IID}/upload", params={"name": "virus.docx"}, content=b"MZ\x90\x00 not a docx")
    ok(exe.status_code == 415, "nomi o'zgartirilgan bajariluvchi / buzuq fayl rad etildi (415)")
    ok(CH.post(f"/api/syllabus/items/{IID}/upload", params={"name": "x.exe"}, content=b"abc").status_code == 415, "DOCX/PDF dan boshqa tur rad etildi")
    ok(CH.get(f"/api/syllabus/items/{IID}/file").status_code == 200, "yuklangan faylni qayta yuklab olish mumkin")
    # topshirish v1
    r = CH.post(f"/api/syllabus/items/{IID}/submit", json={})
    ok(r.status_code == 200 and r.json()["version"] == 1 and r.json()["check"]["summary"]["level"] == "bad", "1-versiya topshirildi; tekshiruv darajasi — kamchilik")
    ok(CH.post(f"/api/syllabus/items/{IID}/submit", json={}).status_code == 403, "tekshiruvdagi sillabusni qayta topshirib bo'lmaydi (403)")
    ok(CH.post(f"/api/syllabus/items/{IID}/review", json={"action": "yuborish"}).status_code == 403, "kafedra mudiri tekshiruv bosqichida qaror qabul qilmaydi")
    mw = C[AK].get("/api/mywork").json()["items"]
    ok(any(it["source"] == "sillabus" and it["kind"] == "tekshiruv" for it in mw), "«Mening vazifalarim»: Akademik bo'limda tekshiruv ishi bor")
    ok(C[AK].post(f"/api/syllabus/items/{IID}/review", json={"action": "qaytarish", "comment": ""}).status_code == 400, "izohsiz qaytarish rad etiladi (400)")
    ok(C[AK].post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash"}).status_code == 400, "tekshiruvdan to'g'ridan-to'g'ri ma'qullash yo'q (avval kelishuvga)")
    r = C[AK].post(f"/api/syllabus/items/{IID}/review", json={"action": "qaytarish", "comment": "TEST: begona mavzuni olib tashlang, yetishmayotgan mavzularni kiriting."})
    ok(r.status_code == 200 and r.json()["status"] == "qaytarilgan", "Akademik bo'lim izoh bilan qaytardi")
    ns = CH.get("/api/notifications").json()["items"]
    ok(any(n["kind"] == "sillabus" and "qaytarildi" in n["title"] for n in ns), "bildirishnoma: kafedrada «Sillabus qaytarildi»")
    # tuzatish v2 — form orqali
    good = [{"week": i + 1, "title": t, "lecture": L[i], "practice": P[i] if norm["practice"] else 0, "seminar": P[i] if not norm["practice"] else 0, "lab": 0, "self": M[i]} for i, t in enumerate(core)]
    if norm["lab"]:
        for i, g in enumerate(good): g["lab"] = spread(norm["lab"])[i]
    content = {"topics": good, "literature": ["Manba 1, 2023", "Manba 2, 2024", "Manba 3, 2025"], "assessment": {"joriy": 20, "oraliq": 30, "yakuniy": 50}, "goals": "TEST"}
    r = CH.put(f"/api/syllabus/items/{IID}/draft", json={"content": content})
    ok(r.status_code == 200 and r.json()["check"]["hours"]["ok"], f"qoralama saqlandi; soatlar me'yorga mos ({r.json()['check']['hours']['total_plan']} = {norm['total']})")
    if refs: ok(r.json()["check"]["reference"]["unis"][0]["coverage"] == 100 and not r.json()["check"]["relevance"]["flagged"], "tuzatilgan versiya: asosiy tayanch OTM qamrovi 100%, begona mavzu yo'q")
    r = CH.post(f"/api/syllabus/items/{IID}/submit", json={"comment": "Izohlar bo'yicha tuzatildi"})
    ok(r.status_code == 200 and r.json()["version"] == 2, "2-versiya topshirildi")
    vs = C[AK].get(f"/api/syllabus/items/{IID}").json()["versions"]
    ok([v["version"] for v in vs] == [2, 1] and vs[1]["has_file"], "versiyalar saqlanadi (v1 — fayl bilan, v2 — forma)")
    v1 = C[AK].get(f"/api/syllabus/items/{IID}/versions/1").json()
    ok(any(t["title"] == "Hujayra tuzilishi va funksiyalari" for t in v1["content"]["topics"]), "1-versiya mazmuni o'zgarmagan holda ko'rinadi")
    chk = C[AK].post(f"/api/syllabus/items/{IID}/check", json={"ai": True}).json()
    ok(chk["check"]["relevance"]["method"] in ("heuristic", "ai") and (chk["check"]["relevance"]["method"] == "ai" or chk["note"]), "AI tekshiruvi: mahalliy AI bo'lmasa — evristik natija va izoh")
    # kelishuv zanjiri
    ok(C[AK].post(f"/api/syllabus/items/{IID}/review", json={"action": "yuborish", "comment": "Mos"}).json()["status"] == "kelishuvda", "Akademik bo'lim → kelishuvga yubordi")
    ok(C[PRO].post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash"}).status_code == 403, "prorektor kafedra bosqichida tasdiqlay olmaydi (403)")
    ok(C[KAF2 if dep != 2 else KAF4].post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash"}).status_code in (403, 404), "boshqa kafedra mudiri ma'qullay olmaydi")
    ok(CH.post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash"}).json()["status"] == "kelishuvda", "kafedra mudiri ma'qulladi → Akademik bo'lim bosqichi")
    ok(one("SELECT stage FROM syl_items WHERE id=?", (IID,))[0] == "akademik", "bosqich: akademik")
    ok(C[AK].post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash"}).json()["status"] == "kelishuvda", "Akademik bo'lim ma'qulladi → prorektor bosqichi")
    mw = C[PRO].get("/api/mywork").json()["items"]
    ok(any(it["source"] == "sillabus" and (it["link"].get("item") == IID or it["count"]) for it in mw), "«Mening vazifalarim»: prorektorda tasdiq ishi bor")
    ok(C[REK].post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash"}).status_code == 403, "rektor (faqat ko'rish) tasdiqlay olmaydi")
    ok(C[PRO].post(f"/api/syllabus/items/{IID}/review", json={"action": "maqullash", "comment": "Tasdiqlandi"}).json()["status"] == "tasdiqlangan", "o'quv ishlari prorektori tasdiqladi")
    it = C[AK].get(f"/api/syllabus/items/{IID}").json()
    acts = [h["action"] for h in reversed(it["history"])]
    ok(acts[0] == "so'raldi" and acts[-1] == "tasdiqlandi" and sum(a.startswith("qaytarildi") for a in acts) == 1 and len(acts) >= 9, f"tarix to'liq: {len(acts)} ta voqea")
    ok(it["actions"] == [], "tasdiqlangan sillabusda amal qolmadi")
    for uid, act in ((AK, "%sillabus so'raldi%"), (head, "%o'qituvchi biriktirildi%"), (head, "%sillabus topshirildi%"), (AK, "%sillabus qaytarildi%"),
                     (head, "%sillabus ma'qullandi%"), (PRO, "%sillabus tasdiqlandi%"), (head, "%fayl rad etildi%"), (KAF4, "%sillabus so'rash%")):
        ok(audit_has(uid, act, a0), f"audit: #{uid} «{act.strip('%')}»")
    ok(one("SELECT 1 FROM audit_log WHERE id>? AND user_id=? AND resource='syllabus' AND allowed=0", (a0, KAF4)) is not None, "audit: rad etilgan urinish (allowed=0) yozilgan")

    print("\n— 3. Yuklama kalkulyatori")
    L0 = C[AK].get("/api/syllabus/load?dept=4").json()
    s = L0["summary"]
    ok(s["total"] > 0 and abs(sum(t["total"] for t in L0["teachers"]) - s["total"]) < 1, f"kafedra jami = o'qituvchilar yig'indisi ({s['total']} soat)")
    ok(abs(sum(r["total"] for r in L0["rows"]) - s["total"]) < 1, "kafedra jami = fanlar yig'indisi")
    ok(s["current"] == one("SELECT SUM(load_hours) FROM teachers WHERE department_id=4")[0], "joriy yuklama teachers.load_hours bilan bir xil")
    ok(L0["load_norm"] == 840 and all(abs(t["stavka"] - round(t["total"] / 840, 2)) < 0.011 for t in L0["teachers"]), "stavka = hisob / LOAD_NORM (documents.py)")
    row = next(r for r in L0["rows"] if r["hours"]["lecture"] > 0)
    calc = C[AK].post("/api/syllabus/load/calc", json={"department_id": 4, "settings": L0["settings"], "rows": {row["subject"]: {"streams": 1}}}).json()
    r1 = next(r for r in calc["rows"] if r["subject"] == row["subject"])
    ok(r1["streams"] == 1 and r1["totals"]["lecture"] < row["totals"]["lecture"], f"potoklar 1 ga tushirilsa ma'ruza soati kamayadi ({row['totals']['lecture']} → {r1['totals']['lecture']})")
    calc2 = C[AK].post("/api/syllabus/load/calc", json={"department_id": 4, "settings": {**L0["settings"], "k_sirtqi": 1.0}, "rows": {}}).json()
    ok(calc2["summary"]["total"] >= s["total"], "sirtqi koeffitsiyenti 1 bo'lsa yuklama oshadi")
    x = C[AK].post("/api/syllabus/load/export", json={"department_id": 4, "settings": L0["settings"], "rows": {}, "fmt": "xlsx"})
    ok(x.status_code == 200 and zipfile.ZipFile(io.BytesIO(x.content)).namelist() and x.content[:2] == b"PK", "XLSX eksport (to'g'ri xlsx arxivi)")
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(x.content)); ok({"Fanlar", "O'qituvchilar"} <= set(wb.sheetnames), "XLSX: «Fanlar» va «O'qituvchilar» varaqlari")
    w = C[AK].post("/api/syllabus/load/export", json={"department_id": 4, "settings": L0["settings"], "rows": {}, "fmt": "docx"}).json()
    DOCREG.append(w.get("regs", [""])[0])
    ok(w.get("ok") and w["regs"][0].startswith("OY-"), f"DOCX: Hujjatlar markazidagi «O'quv yuklama taqsimoti» hujjati {w['regs'][0]} sifatida ro'yxatga olindi")
    f = C[AK].get(f"/api/docs/file/{w['file']}")
    from docx import Document
    txt = "\n".join(p.text for p in Document(io.BytesIO(f.content)).paragraphs)
    ok(f.status_code == 200 and "hisob-kitob" in txt and "O'QUV YUKLAMA TAQSIMOTI" in txt, "DOCX ichida mavjud jadval + kalkulyator hisob-kitobi bo'limi (g_load kengaytirildi)")
    ok(C[REK].post("/api/syllabus/load/export", json={"department_id": 4, "fmt": "docx"}).status_code == 403, "rektor DOCX loyihalamaydi (Hujjatlar markazi roli yo'q) — 403")
    ok(C[KAF4].post("/api/syllabus/load/save", json={"department_id": 4, "settings": {}, "rows": {}}).status_code == 403, "kafedra mudiri rejani saqlamaydi (faqat Akademik bo'lim)")
    old = one("SELECT params FROM syl_load_plans WHERE department_id=4")
    ok(C[AK].post("/api/syllabus/load/save", json={"department_id": 4, "settings": {"potok_max": 3}, "rows": {}}).status_code == 200, "Akademik bo'lim yuklama rejasini saqladi")

    print("\n— 4. Kafedra so'rovlari: javob → qaytarish → qayta javob → qabul")
    ok(C[KAF4].post("/api/syllabus/tasks", json={"kind": "yuklama", "title": "TEST so'rov", "due": due, "departments": [4]}).status_code == 403, "kafedra so'rov yubora olmaydi (403)")
    r = C[AK].post("/api/syllabus/tasks", json={"kind": "sillabus", "title": "TEST: sillabuslar ro'yxatini yangilang", "body": "test", "due": due, "departments": [2, 4]})
    ok(r.status_code == 200, "Akademik bo'lim 2 ta kafedraga so'rov yubordi"); TASK_ID = r.json()["id"]
    t4 = C[KAF4].get(f"/api/syllabus/tasks/{TASK_ID}").json()
    ok(len(t4["units"]) == 1 and t4["units"][0]["department_id"] == 4 and t4["units"][0]["can_submit"], "kaf4 faqat o'z qismini ko'radi va javob bera oladi")
    U4 = t4["units"][0]["id"]
    U2 = one("SELECT id FROM syl_task_units WHERE task_id=? AND department_id=2", (TASK_ID,))[0]
    ok(C[KAF4].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U2}/submit", json={"text": "begona"}).status_code == 404, "boshqa kafedra nomidan javob berib bo'lmaydi")
    # yagona topshiriqlar modeli: har bir kafedra qatori — topshiriq (directives), «Mening vazifalarim»ga topshiriq sifatida keladi
    D4 = t4["units"][0].get("directive") and t4["units"][0]["directive"]["id"]
    ok(bool(D4) and one("SELECT src, unit, issuer_unit, origin FROM tasks WHERE id=?", (D4,)) == (f"syl:{TASK_ID}", "kaf4", "akademik", "topshiriq"),
       "kafedra qatori topshiriqqa bog'langan (src=syl:<id>, Akademik bo'lim → kaf4)")
    D2 = one("SELECT directive_id FROM syl_task_units WHERE id=?", (U2,))[0]
    ok(C[KAF4].get(f"/api/dir/{D4}").status_code == 200 and C[KAF4].get(f"/api/dir/{D2}").status_code == 403, "kaf4 o'z topshirig'ini ochadi, kaf2 nikini — yo'q (403)")
    mw = C[KAF4].get("/api/mywork").json()["items"]
    ok(any(it["link"] == {"view": "tasks", "directive": D4} for it in mw), "«Mening vazifalarim»: so'rov topshiriq sifatida (aniq havola)")
    ok(not any(it["source"] == "sillabus" and it["link"].get("task") == TASK_ID for it in mw), "so'rov ikki marta sanalmaydi (sillabus manbasida takror yo'q)")
    ok(C[KAF4].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/file", params={"name": "javob.docx"}, content=make_docx([("Buxgalteriya balansi", 2, 2, 4)])).status_code == 200, "kafedra javobga DOCX ilova qildi")
    ok(C[KAF4].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/submit", json={"text": "Ro'yxat ilova qilindi"}).status_code == 200, "kafedra javob yubordi")
    ok(one("SELECT status, review FROM tasks WHERE id=?", (D4,)) == ("bajarildi", "kutilmoqda"), "topshiriq: bajarildi, natija qabul kutmoqda")
    ok(any(it["link"] == {"view": "tasks", "directive": D4} for it in C[AK].get("/api/mywork").json()["items"]), "Akademik bo'lim «Mening vazifalarim»: natijani ko'rib chiqish (aniq havola)")
    ok(C[KAF4].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/submit", json={"text": "yana"}).status_code == 403, "ko'rib chiqilayotgan javobni qayta yuborib bo'lmaydi")
    ok(C[KAF4].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/review", json={"action": "qabul"}).status_code == 403, "kafedra o'z javobini qabul qila olmaydi")
    ok(C[AK].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/review", json={"action": "qayta", "comment": ""}).status_code == 400, "izohsiz qaytarish rad etiladi")
    ok(C[AK].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/review", json={"action": "qayta", "comment": "TEST: ikki fan yetishmaydi"}).status_code == 200, "Akademik bo'lim qayta ishlashga qaytardi")
    ok(any("Qayta ishlashga" in n["title"] and n["link"] == {"view": "tasks", "directive": D4} for n in C[KAF4].get("/api/notifications").json()["items"]),
       "bildirishnoma: kafedrada «Qayta ishlashga qaytarildi» (topshiriqqa aniq havola)")
    # 2-raund — «Majlislar va topshiriqlar» oynasidan (topshiriq orqali): so'rov qatori avtomatik sinxronlanadi
    ok(C[KAF4].post(f"/api/dir/{D4}/status", json={"status": "bajarildi", "result": "Tuzatildi"}).status_code == 200, "kafedra qayta javobni topshiriq orqali yubordi (2-raund)")
    ok(C[AK].get(f"/api/syllabus/tasks/{TASK_ID}").json()["units"][[x["id"] for x in C[AK].get(f"/api/syllabus/tasks/{TASK_ID}").json()["units"]].index(U4)]["status"] == "topshirildi",
       "so'rov qatori topshiriqdan sinxronlandi: ko'rib chiqilmoqda")
    ok(C[AK].post(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/review", json={"action": "qabul", "comment": "OK"}).status_code == 200, "Akademik bo'lim qabul qildi")
    ok(one("SELECT review FROM tasks WHERE id=?", (D4,)) == ("qabul",), "topshiriq natijasi qabul qilindi (bitta holat)")
    t = C[AK].get(f"/api/syllabus/tasks/{TASK_ID}").json()
    u = next(x for x in t["units"] if x["id"] == U4)
    ok(u["status"] == "qabul" and u["round"] == 2 and [h["action"] for h in reversed(u["history"])] ==
       ["so'rov yuborildi", "javob yuborildi", "qayta ishlashga qaytarildi", "javob yuborildi", "qabul qilindi"], "so'rov tarixi to'liq saqlandi (2 raund)")
    ok(C[AK].get(f"/api/syllabus/tasks/{TASK_ID}/units/{U4}/file").status_code == 200, "Akademik bo'lim ilova faylni yuklab oladi")
finally:
    # test yaratgan yozuvlarni tozalash (demo holat saqlanadi)
    con = sqlite3.connect(DB, timeout=30)
    files = [r[0] for r in con.execute("SELECT file_path FROM syl_versions WHERE item_id=? AND file_path IS NOT NULL", (IID,))]
    files += [json.loads(r[0] or "{}").get("file", {}).get("path") for r in con.execute("SELECT draft FROM syl_items WHERE id=?", (IID,))]
    con.execute("DELETE FROM syl_versions WHERE item_id=?", (IID,)); con.execute("DELETE FROM syl_log WHERE ref_type='syl' AND ref_id=?", (IID,))
    con.execute("DELETE FROM syl_items WHERE id=?", (IID,))
    if TASK_ID:
        for (uid_, fp) in con.execute("SELECT id, file_path FROM syl_task_units WHERE task_id=?", (TASK_ID,)).fetchall():
            files.append(fp); con.execute("DELETE FROM syl_log WHERE ref_type='task' AND ref_id=?", (uid_,))
        for (did,) in con.execute("SELECT id FROM tasks WHERE src=?", (f"syl:{TASK_ID}",)).fetchall():
            for tb in ("task_log", "task_msgs"): con.execute(f"DELETE FROM {tb} WHERE task_id=?", (did,))
            con.execute("DELETE FROM tasks WHERE id=? OR parent_id=?", (did, did))
        con.execute("DELETE FROM syl_task_units WHERE task_id=?", (TASK_ID,)); con.execute("DELETE FROM syl_tasks WHERE id=?", (TASK_ID,))
    if DOCREG:
        for (fn,) in con.execute("SELECT file FROM documents WHERE reg_no=?", (DOCREG[0],)).fetchall():
            try: (Path(os.environ.get("ISFT_CORE_DATA_DIR") or ROOT / "data") / "docs" / fn).unlink()
            except OSError: pass
        con.execute("DELETE FROM documents WHERE reg_no=?", (DOCREG[0],))
    if "old" in dir() and old: con.execute("UPDATE syl_load_plans SET params=? WHERE department_id=4", old)
    con.commit(); con.close()
    for fp in files:
        if fp:
            try: (Path(os.environ.get("ISFT_CORE_DATA_DIR") or ROOT / "data") / "syllabus" / fp).unlink()
            except OSError: pass
print("\n— 5. Tozalash")
ok(one("SELECT 1 FROM syl_items WHERE id=?", (IID,)) is None, "test sillabusi o'chirildi — demo holat o'zgarmadi")
print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
