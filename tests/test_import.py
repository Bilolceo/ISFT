"""Tayyor testni Word'dan import (app/test_import.py, docs/paket.md — «Tayyor testni Word'dan import»).

1) Sof tahlil: ✅ / ✔ / ✓ / ☑ / ✔️, «(to'g'ri)», oxiridagi « *» / « +», boshidagi «*», «Javob: B» kaliti, qalin / rangli fon (Word), «A)» «A.» «a)»
   «(A)», kirillcha «А) Б) В)», bir qatordagi variantlar, raqamsiz savollar, Word avtomatik ro'yxati, ko'p javobli → multi, glossariy ajratgichlari
   va 2 ustunli jadval, «Savollar» → ochiq savollar, ogohlantirishlar, looks_like_test (ma'ruza matni testga aylanmaydi), AI izoh (soxta Claude).
2) Server: bo'lim xodimi namuna faylni (tests/fixtures/test_import/test.docx) darsga yuklaydi → /upload avtomatik «test» deb taniydi →
   Test bankda tasdiqlangan savollar (ko'p javobli — qtype «multi»), javobsizi — `needs_answer` (Test bankka tushmaydi), moslashtirish mashqi,
   topshiriq savollari → dars yig'iladi (xAPI) → content.json da test (multi — «multi» turi), moslashtirish va topshiriq. Qayta yuklash — almashtiradi.
   O'qituvchi — qoralama.
3) «To'g'ri javobni tanlang» (POST …/test/answers): tekshiruvlar (400/404/403/409), bitta va ko'p javob, o'tkazib yuborish, takroriy so'rov
   (dublikat yo'q), eskirgan yuklash, o'qituvchi (qoralama), Test bank multi (QC, Moodle/GIFT), paket → muharrir («multiple»).

Ishga tushirish:  .venv/bin/python tests/run_all.py --only test_import   (to'plam nomi: «import»)
"""
import io, json, os, re, sqlite3, sys, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures" / "test_import"
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)

from app import test_import as TI
from docx import Document

def docx_bytes(build) -> bytes:
    d = Document(); build(d); b = io.BytesIO(); d.save(b); return b.getvalue()

# =============================================================================================
print("== 1. Matn tahlili: belgilar va formatlar")
P = TI.parse_test_text
r = P("1. “O‘zbek tilining sohada qo‘llanilishi” fanining maqsadi nima?\nA) Tilning faqat shevalarini o‘rganish\n"
      "B) O‘zbek tilining turli sohalarda qo‘llanilishini o‘rgatish ✅\nC) Faqat badiiy matnlarni yozishni o‘rgatish\nD) Ingliz tilini o‘rganish\n\n"
      "2. O‘zbek tilida nechta uslub mavjud?\nA) 3\nB) 4\nC) 5 ✅\n")
q0, q1 = r["questions"]
ok(len(r["questions"]) == 2 and q0["correct"] == [1] and q1["correct"] == [2] and q0["qtype"] == "mcq", "Video namunasi: 2 savol, ✅ → to'g'ri javob")
ok(q0["options"][1] == "O‘zbek tilining turli sohalarda qo‘llanilishini o‘rgatish" and "‘" in q0["stem"], "✅ variant matnidan olib tashlandi; o‘/g‘ apostroflari saqlanadi")
for mark in ("✅", "✔", "✓", "☑", "✔️", "☑️", "(to'g'ri)", "(to‘g‘ri javob)", "(TO'G'RI)", "*", "+", "(+)", "(правильно)"):
    rr = P(f"1) Savol matni qanday bo'ladi?\na) birinchi\nb) ikkinchi {mark}\nc) uchinchi")
    ok(rr["questions"] and rr["questions"][0]["correct"] == [1] and rr["questions"][0]["options"][1] == "ikkinchi", f"Belgi {mark!r} → B to'g'ri, matndan olib tashlandi")
rr = P("1. Savol matni qanday bo'ladi?\n*A) birinchi\nB) ikkinchi\nC) uchinchi")
ok(rr["questions"][0]["correct"] == [0] and rr["questions"][0]["options"][0] == "birinchi", "Boshidagi «*A)» → A to'g'ri")
rr = P("1. Savol matni qanday bo'ladi?\n✅ C) birinchi\nA) ikkinchi\nB) uchinchi")
ok(rr["questions"][0]["correct"] == [0], "Boshidagi «✅ C)» → shu variant to'g'ri")
rr = P("1. Qaysi tillar C oilasiga kiradi?\nA) C++\nB) Python\nC) C# +")
ok(rr["questions"][0]["options"][0] == "C++" and rr["questions"][0]["correct"] == [2], "«C++» belgi deb olinmaydi (oldida bo'shliq yo'q); «C# +» — belgi")
rr = P("1. Savol matni qanday bo'ladi?\nA. bir\nB. ikki ✅\nC. uch\nD. to'rt")
ok(rr["questions"][0]["correct"] == [1] and len(rr["questions"][0]["options"]) == 4, "«A.» ko'rinishidagi variantlar")
rr = P("1. Savol matni qanday bo'ladi?\n(A) bir\n(B) ikki\n(C) uch ✓")
ok(rr["questions"][0]["correct"] == [2], "«(A)» ko'rinishidagi variantlar")
rr = P("1. Тил нима?\nА) товуш ✅\nБ) ранг\nВ) шакл\nГ) ҳажм")
ok(rr["questions"][0]["correct"] == [0] and len(rr["questions"][0]["options"]) == 4, "Kirillcha «А) Б) В) Г)»")
rr = P("1. Тил нима?\nа) товуш\nб) ранг ✅\nв) шакл")
ok(rr["questions"][0]["correct"] == [1], "Kirillcha kichik «а) б) в)»")
rr = P("Savol 3. Ikki karra ikki necha?\nA) 3  B) 4 ✅  C) 5  D) 6")
ok(rr["questions"][0]["options"] == ["3", "4", "5", "6"] and rr["questions"][0]["correct"] == [1], "Bir qatordagi variantlar («A) 3  B) 4 ✅  C) 5»)")
rr = P("Test\nIkki karra ikki necha?\nA) 3\nB) 4 ✅\nC) 5\nPoytaxt qaysi shahar\nA) Toshkent ✅\nB) Samarqand\nC) Buxoro")
ok(len(rr["questions"]) == 2 and rr["questions"][1]["stem"] == "Poytaxt qaysi shahar" and rr["questions"][1]["correct"] == [0], "Raqamsiz savollar («?» bilan yoki keyingi qatori A variant)")
rr = P("1. Uzun savol matni\nikkinchi qatorda davom etadi?\nA) bir\nB) ikki ✅\nC) uch")
ok(rr["questions"][0]["stem"] == "Uzun savol matni ikkinchi qatorda davom etadi?", "Ko'p qatorli savol matni birlashtiriladi")
rr = P("1. Qaysilar meva?\nA) olma ✅\nB) sabzi\nC) nok ✅\nD) kartoshka")
ok(rr["questions"][0]["qtype"] == "multi" and rr["questions"][0]["correct"] == [0, 2], "Ikki ✅ → qtype «multi», correct [0, 2]")
rr = P("1. Savol matni qanday bo'ladi?\nA) bir\nB) ikki\nC) uch\nJavob: C\nIzoh: chunki uchinchisi to'g'ri")
ok(rr["questions"][0]["correct"] == [2] and rr["questions"][0]["explanation"] == "chunki uchinchisi to'g'ri" and rr["questions"][0]["marked_by"] == "kalit", "«Javob: C» kaliti va «Izoh:» qatori")
rr = P("1. Savol matni qanday bo'ladi?\nA) bir\nB) ikki\nC) uch\n2. Keyingi savol nima bo'ladi?\nA) x ✅\nB) y")
ok(len(rr["questions"]) == 2 and rr["questions"][0]["correct"] == [] and any("1-savol" in w and "belgilanmagan" in w for w in rr["warnings"]),
   "Belgisiz savol saqlanadi (correct=[]) va ogohlantirish beriladi")
rr = P("1. Faqat bitta variant?\nA) bir ✅\n2. Normal savol nima?\nA) x ✅\nB) y")
ok(len(rr["questions"]) == 1 and any("bitta variant" in w for w in rr["warnings"]), "Bitta variantli savol tashlanadi (ogohlantirish)")

print("== 2. Glossariy va ochiq savollar")
rr = P("Glossariy\nolma - meva turlaridan biri\nnok — boshqa meva\nijtimoiy-iqtisodiy: murakkab tushuncha\n• gilos – qizil meva\n1. behi—sariq meva\nolma - takror\n"
       "Atamalar lug‘ati:\nuzum: shirin meva\n")
ok([g["term"] for g in rr["glossary"]] == ["olma", "nok", "ijtimoiy-iqtisodiy", "gilos", "behi", "uzum"] and rr["glossary"][0]["def"] == "meva turlaridan biri",
   "Glossariy: « - », « — », «: », « – », «—», belgi/raqamli qatorlar; chiziqchali so'z («ijtimoiy-iqtisodiy») buzilmaydi")
ok(any("takrorlangan" in w for w in rr["warnings"]), "Glossariy: takroriy atama — ogohlantirish")
rr = P("Savollar\n1. Til nima?\n2. Uslub nima va u\nqanday tasniflanadi?\n- Ish yuritish deganda nimani tushunasiz?\nNazorat savollari:\n1) Termin nima?")
ok(rr["open_questions"] == ["Til nima?", "Uslub nima va u qanday tasniflanadi?", "Ish yuritish deganda nimani tushunasiz?", "Termin nima?"] and not rr["questions"],
   "«Savollar» / «Nazorat savollari» → ochiq savollar (ko'p qatorli birlashadi)")
rr = P("Savollar\n1. Til nima?\n1. Qaysi biri to'g'ri?\nA) bir ✅\nB) ikki")
ok(rr["open_questions"] == ["Til nima?"] and len(rr["questions"]) == 1, "Savollar bo'limidan keyin sarlavhasiz test (raqam + A variant) — test rejimiga qaytadi")
rr = P("1. Test savoli nima?\nA) a ✅\nB) b\n2. Bu ochiq savolmi?\n3. Yana test savoli nima?\nA) c\nB) d ✅")
ok(len(rr["questions"]) == 2 and rr["open_questions"] == ["Bu ochiq savolmi?"], "Test ichidagi variantsiz savol — ochiq savol")

print("== 3. Word (.docx): qalin / rangli fon, avtomatik ro'yxat, jadval")
fx = TI.parse_test_docx((FIX / "test.docx").read_bytes())
qs = fx["questions"]
ok(len(qs) == 5 and [q["correct"] for q in qs] == [[1], [2], [1], [], [0, 2]] and [q["marked_by"] for q in qs] == ["belgi", "belgi", "format", "", "belgi"],
   f"Namuna fayl: 5 savol — ✅, (to‘g‘ri), faqat qalin, belgisiz, ✔️×2 ({[q['correct'] for q in qs]})")
ok(qs[4]["qtype"] == "multi" and qs[4]["stem"] == "Ish yuritish hujjatlariga qaysilar kiradi?", "Word «List Number» (avtomatik raqam) savoli o'qildi, ko'p javobli → multi")
ok(len(fx["glossary"]) == 4 and fx["glossary"][2] == {"term": "Ariza", "def": "biror iltimos bilan rasmiy murojaat qilish hujjati"} and len(fx["open_questions"]) == 3,
   "Namuna fayl: glossariy 4 atama, 3 ochiq savol")
ok(len(fx["warnings"]) == 1 and "4-savol" in fx["warnings"][0], "Namuna fayl: bitta ogohlantirish (4-savol javobsiz)")
ok(TI.parse_test_file((FIX / "test.txt").read_bytes())["questions"][2]["correct"] == [1], "test.txt (✓ belgisi) — o'sha natija")

def _hl(d):
    d.add_paragraph("1. Rangli fon bilan belgilangan savol nima?")
    for j, t in enumerate(["bir", "ikki", "uch"]):
        r_ = d.add_paragraph().add_run(f"{'ABC'[j]}) {t}")
        if j == 2:
            from docx.enum.text import WD_COLOR_INDEX
            r_.font.highlight_color = WD_COLOR_INDEX.YELLOW
    d.add_paragraph("2. Hammasi qalin bo'lsa-chi?")
    for j, t in enumerate(["bir", "ikki"]): d.add_paragraph().add_run(f"{'AB'[j]}) {t}").bold = True
    tb = d.add_table(rows=3, cols=2)
    for i_, (a, b_) in enumerate([("Atama", "Ta'rif"), ("olma", "meva"), ("sabzi", "sabzavot")]):
        tb.cell(i_, 0).text, tb.cell(i_, 1).text = a, b_
hx = TI.parse_test_docx(docx_bytes(_hl))
ok(hx["questions"][0]["correct"] == [2] and hx["questions"][0]["marked_by"] == "format", "Word: sariq fon (highlight) → to'g'ri javob")
ok(hx["questions"][1]["correct"] == [] , "Word: hamma variant qalin — belgi emas (javobsiz)")
ok(hx["glossary"] == [{"term": "olma", "def": "meva"}, {"term": "sabzi", "def": "sabzavot"}], "Word: 2 ustunli jadval → glossariy (sarlavha qatori tashlanadi)")

print("== 4. Aniqlash: test fayli yoki ma'ruza matni")
ok(TI.looks_like_test((FIX / "test.docx").read_bytes()) and TI.looks_like_test((FIX / "test.txt").read_bytes()), "Namuna fayllar — test")
def _lecture(d):
    d.add_heading("3-MAVZU: PUL NAZARIYASI", 1)
    for k in range(12): d.add_paragraph("Pul — umumiy ekvivalent vazifasini bajaruvchi maxsus tovar bo'lib, iqtisodiyotda muhim o'rin tutadi. " * 3)
    d.add_paragraph("Test savollari")
    for k in range(2):
        d.add_paragraph(f"{k + 1}. Pul nima?"); d.add_paragraph("A) tovar ✅"); d.add_paragraph("B) xizmat")
    d.add_paragraph("Savollar"); d.add_paragraph("1. Pul funksiyalari nimalar?")
ok(not TI.looks_like_test(docx_bytes(_lecture)), "Ma'ruza matni (oxirida 2 ta test savoli bilan) — test emas")
ok(not TI.looks_like_test(b"1. Bir savol?\nA) a \xe2\x9c\x85\nB) b\n"), "Bitta savol — test emas (kamida 2 ta belgilangan)")
ok(not TI.looks_like_test(b"1. Savol?\nA) a\nB) b\n2. Savol?\nA) c\nB) d\n"), "Belgisiz savollar — avtomatik test deb olinmaydi")
ok(not TI.looks_like_test(b"PK\x03\x04garbage") and not TI.looks_like_test(b"%PDF-1.4 garbage"), "Buzilgan fayl — xatosiz «test emas»")
try: TI.parse_test_file(b"\x00\x01\x02" * 50); ok(False, "Ikkilik fayl — ValueError")
except ValueError: ok(True, "Ikkilik fayl — ValueError (o'zbekcha)")

print("== 5. AI izoh (soxta Claude — tarmoq yo'q)")
seen = {}
def fake_call(**kw):
    seen.update(kw)
    return {"items": [{"n": 1, "explanation": "Fan tilning sohalarda qo'llanishini o'rgatadi.", "option_feedback": ["Shevalar — tor soha.", "To'g'ri.", "Faqat badiiy emas.", "Boshqa til."]},
                      {"n": 2, "explanation": "x", "option_feedback": ["juda", "kam"]},     # variantlar soniga teng emas — tashlanadi
                      {"n": 9, "explanation": "y", "option_feedback": []}]}, {"in": 10, "out": 20, "model": "fake"}
fbk, info = TI.ai_feedback(qs, "O'zbek tili", "1-mavzu", call=fake_call)
txt = seen["content"][0]["text"]
ok(set(fbk) == {0, 1} and fbk[0]["option_feedback"][1] == "To'g'ri." and fbk[1]["option_feedback"] == [] and info["model"] == "fake",
   "AI izoh: indekslar savollarga bog'landi; variantlar soni mos kelmasa — variant izohlari tashlanadi; noto'g'ri n — e'tiborsiz")
ok("[TO'G'RI]" in txt and "Ilmiy uslubning asosiy belgisi" not in txt and seen["schema"] == TI.AI_SCHEMA, "AI'ga faqat javobi belgilangan savollar va variantlar yuboriladi (javobsizi — yo'q)")
ok(TI._explanation("", fbk[0], qs[0]["options"], [1]) == "Fan tilning sohalarda qo'llanishini o'rgatadi. A: Shevalar — tor soha. C: Faqat badiiy emas. D: Boshqa til.",
   "Izoh matni: umumiy izoh + noto'g'ri variantlar izohi; fayldagi izoh ustun")

# =============================================================================================
print("== 6. Server: yuklash → Test bank, mashq, topshiriq → yig'ish (xAPI)")
def q(sql, a=()):
    con = sqlite3.connect(DBP); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def x(sql, a=()):
    con = sqlite3.connect(DBP)
    try: con.execute(sql, a); con.commit()
    finally: con.close()
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
def uid(role): return q("SELECT id FROM users WHERE role=? ORDER BY id LIMIT 1", (role,))[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
API = "/api/paket"
staff, teach, kaf = S(uid("masofaviy_xodim")), S(uid("oqituvchi")), S(uid("kafedra"))
teach_tid = q("SELECT teacher_id FROM users WHERE id=?", (uid("oqituvchi"),))[0]["teacher_id"]
own = q("SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY id DESC LIMIT 1", (teach_tid,))[0]
co = q("SELECT * FROM dl_courses WHERE subject!='Mikroiqtisodiyot' AND (teacher_id IS NULL OR teacher_id!=?) AND topics>=4 ORDER BY id DESC LIMIT 1", (teach_tid,))[0]
CID, NO = co["id"], int(co["topics"])                # ma'ruza darsi L{n} (kalit = n) → Test bank mavzusi n
U = f"{API}/courses/{CID}/topics/{NO}"
RAW = (FIX / "test.docx").read_bytes()
STEMS = [q_["stem"] for q_ in qs]
OPEN = fx["open_questions"]
try:
    r = staff.post(U + "/upload", params={"name": "namuna_test.docx"}, content=RAW)
    j = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and j.get("as") == "test" and j.get("label") == "Test (Word, ✅ belgili)", f"/upload: Word test avtomatik «test» deb tanildi ({r.status_code} {r.text[:160]})")
    ok({k: j.get(k) for k in ("questions", "without_answer", "multi", "approved", "draft", "saved", "glossary", "exercises", "open_questions", "replaced", "topic_no")}
       == {"questions": 5, "without_answer": 1, "multi": 1, "approved": 4, "draft": 0, "saved": 4, "glossary": 4, "exercises": 1, "open_questions": 3, "replaced": 0, "topic_no": NO},
       f"Javob: 5 savol (4 tasdiqlangan; javobsizi Test bankka tushmadi), 1 ko'p javobli, 4 atama → 1 mashq, 3 ochiq savol ({ {k: j.get(k) for k in ('approved', 'draft', 'exercises', 'replaced')} })")
    na = j.get("needs_answer") or []
    ok(len(na) == 1 and na[0]["i"] == 3 and na[0]["n"] == 4 and na[0]["stem"] == STEMS[3] and na[0]["options"] == qs[3]["options"] and re.fullmatch(r"[0-9a-f]{16}", j.get("upload_id") or "")
       and j.get("no_answer_ids") == [] and j.get("ai") is False and j.get("explanations") == 0, "needs_answer: javobsiz savol (i, stem, options) + upload_id; AI ulanmagan — izoh yo'q (soxta matn yo'q)")
    ok(any("belgilanmagan" in w for w in j["warnings"]), "Ogohlantirish: javobsiz savol «To'g'ri javobni tanlang» oynasida belgilanadi")
    rows = q("SELECT * FROM tb_questions WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0 ORDER BY id", (CID, NO))
    ok([r_["stem"] for r_ in rows] == [s_ for i_, s_ in enumerate(STEMS) if i_ != 3] and [r_["status"] for r_ in rows] == ["tasdiqlandi"] * 4
       and all(r_["engine"] == "import" for r_ in rows) and [r_["qtype"] for r_ in rows] == ["mcq", "mcq", "mcq", "multi"] and json.loads(rows[3]["correct"]) == [0, 2]
       and all(r_["blocking"] == 0 for r_ in rows),
       "Test bank: src=import, bo'lim yuklagani — tasdiqlangan; ko'p javobli — qtype «multi» (bloklanmagan); javobsizi — Test bankda yo'q")
    exs = q("SELECT * FROM pk_exercises WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0", (CID, NO))
    ok(len(exs) == 1 and exs[0]["kind"] == "match" and exs[0]["status"] == "faol" and len(json.loads(exs[0]["data"])["pairs"]) == 4, "Glossariy → faol moslashtirish mashqi (4 juft)")
    v = staff.get(U).json()
    ok(v["ready"]["assignment"]["n"] == 3 and v["ready"]["assignment"]["src"] == "manual" and v["ready"]["quiz"]["approved"] >= 4 and v["ready"]["quiz"]["pending"] == 1,
       "Dars holati: topshiriq 3 savol, test tayyor, 1 savol javob kutmoqda (pending)")
    pj = staff.get(U + "/test/pending").json()
    ok(pj["upload_id"] == j["upload_id"] and pj["needs_answer"] == na and pj["file"] == "namuna_test.docx", "GET …/test/pending: kutayotgan savollar upload_id bilan (oynani qayta ochish uchun)")
    UP1 = j["upload_id"]
    # qayta yuklash — almashtiriladi
    r = staff.post(U + "/upload", params={"name": "namuna_test.docx"}, content=RAW)
    ok(r.status_code == 200 and r.json()["replaced"] == 4 and len(q("SELECT id FROM tb_questions WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0", (CID, NO))) == 4
       and len(q("SELECT id FROM pk_exercises WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0", (CID, NO))) == 1, "Qayta yuklash — oldingi import almashtirildi (dublikat yo'q)")
    # yig'ish
    b = staff.post(U + "/build", json={"mode": "xapi"})
    ok(b.status_code == 200 and b.json()["package"]["valid"], f"Dars yig'ildi (xAPI) ({b.status_code} {b.text[:200]})")
    if b.status_code == 200:
        d = staff.get(f"{API}/packages/{b.json()['package']['id']}/download")
        cj = json.loads(zipfile.ZipFile(io.BytesIO(d.content)).read("content.json"))
        bl = {x_["type"]: x_ for x_ in cj["blocks"]}
        qz = {x_.get("stem"): x_ for x_ in bl["quiz"]["questions"]}
        ok(all(s in qz for i, s in enumerate(STEMS) if i != 3) and STEMS[3] not in qz, "content.json: 4 ta tasdiqlangan savol testda, javobsizi yo'q")
        ok(qz[STEMS[0]]["correct"] == [1] and qz[STEMS[0]]["options"][1] == "O‘zbek tilining turli sohalarda qo‘llanilishini o‘rgatish"
           and qz[STEMS[2]]["correct"] == [1] and qz[STEMS[2]]["type"] == "mcq" and qz[STEMS[4]]["type"] == "multi" and qz[STEMS[4]]["correct"] == [0, 2],
           "content.json: to'g'ri javoblar (✅, qalin); ko'p javobli savol — type «multi», correct [0, 2]")
        mt = [x_ for x_ in bl["quiz"]["questions"] if x_["type"] == "match"]
        ok(len(mt) == 1 and {p_["left"] for p_ in mt[0]["pairs"]} == {"Uslub", "Termin", "Ariza", "Dalolatnoma"}, "content.json: glossariydan moslashtirish mashqi")
        ok(bl.get("assignment", {}).get("questions") == OPEN, "content.json: topshiriq — «Savollar» bo'limidagi 3 ta ochiq savol")
    # as=test — majburan; ma'ruza Word fayli test sifatida — savol topilmasa 400
    r = staff.post(U + "/upload", params={"name": "test.txt", "as": "test"}, content=(FIX / "test.txt").read_bytes())
    ok(r.status_code == 200 and r.json()["as"] == "test" and r.json()["kind"] == "txt" and r.json()["replaced"] == 4, "as=test: .txt fayl ham import qilinadi")
    r = staff.post(U + "/upload", params={"name": "maruza.docx", "as": "test"}, content=docx_bytes(lambda d_: [d_.add_paragraph("Oddiy ma'ruza matni. " * 20) for _ in range(3)]))
    ok(r.status_code == 400 and "topilmadi" in r.json()["detail"], "as=test, lekin savol yo'q — 400 va namuna bilan tushuntirish")
    r = staff.post(U + "/upload", params={"name": "maruza.docx"}, content=docx_bytes(_lecture))
    ok(r.status_code == 200 and r.json()["as"] == "matn", "Ma'ruza Word fayli (oxirida test bilan) — avvalgidek ma'ruza matni")
    # ruxsatlar
    ok(kaf.post(U + "/upload", params={"name": "t.docx"}, content=RAW).status_code == 403, "Kafedra mudiri test import qilolmaydi (403)")
    ok(teach.post(U + "/upload", params={"name": "t.docx"}, content=RAW).status_code == 403, "O'qituvchi begona kursga import qilolmaydi (403)")
    # o'qituvchi — o'z kursi: qoralama
    TN = int(own["topics"])
    r = teach.post(f"{API}/courses/{own['id']}/topics/{TN}/upload", params={"name": "t.docx"}, content=RAW)
    ok(r.status_code == 200 and r.json()["approved"] == 0 and r.json()["draft"] == 4 and len(r.json()["needs_answer"]) == 1 and any("qoralama" in w for w in r.json()["warnings"]),
       f"O'qituvchi yuklagan savollar — qoralama (bo'lim tasdiqlaydi) ({r.status_code} {r.text[:120]})")
    ok(all(r_["status"] == "qoralama" for r_ in q("SELECT status FROM tb_questions WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0", (own["id"], TN)))
       , "Test bank: o'qituvchi importi — hammasi qoralama")
    # =========================================================================================
    print("== 7. «To'g'ri javobni tanlang»: POST …/test/answers (bir va ko'p javob, o'tkazish, tekshiruvlar, idempotentlik) + multi qatlamlari")
    def up_test(cl=staff, cid=CID, no=NO, content=RAW):
        r_ = cl.post(f"{API}/courses/{cid}/topics/{no}/upload", params={"name": "namuna_test.docx"}, content=content)
        assert r_.status_code == 200, r_.text
        return r_.json()
    def bank_rows(cid=CID, no=NO):
        return q("SELECT * FROM tb_questions WHERE course_id=? AND topic_no=? AND src='import' AND deleted=0 ORDER BY id", (cid, no))
    def post_ans(body, cl=staff, cid=CID, no=NO):
        return cl.post(f"{API}/courses/{cid}/topics/{no}/test/answers", json=body)
    j = up_test(); UP = j["upload_id"]; n0 = len(bank_rows())
    ok(n0 == 4 and (staff.post(f"{API}/courses/{CID}/topics/{NO}/test/answers", json={"upload_id": UP1, "answers": [{"i": 3, "correct": [1]}]}).status_code == 409),
       "Eskirgan upload_id (yangi fayl yuklangan) — 409, hech narsa yozilmaydi")
    bad = [({"i": 3, "correct": []}, "bo'sh javob"), ({"i": 3}, "javob ham, skip ham yo'q"), ({"i": 9, "correct": [0]}, "noma'lum savol indeksi"),
           ({"i": 0, "correct": [0]}, "javobi bor (kutmayotgan) savol indeksi"), ({"i": 3, "correct": [7]}, "variant oralig'idan tashqari"),
           ({"i": 3, "correct": [-1]}, "manfiy variant"), ({"i": 3, "correct": [0, 1, 2, 3]}, "hamma variant to'g'ri"), ({"i": 3, "correct": ["1"]}, "variant — son emas"),
           ({"i": True, "correct": [0]}, "indeks — bool"), ({"i": "3", "correct": [0]}, "indeks — matn")]
    res_bad = [(why, post_ans({"upload_id": UP, "answers": [a]}).status_code) for a, why in bad]
    ok(all(c_ == 400 for _, c_ in res_bad), f"Noto'g'ri javoblar — 400 ({', '.join(f'{w}: {c_}' for w, c_ in res_bad if c_ != 400) or 'hammasi'})")
    ok(post_ans({"upload_id": UP, "answers": []}).status_code == 400 and post_ans({"upload_id": UP, "answers": [{"i": 3, "correct": [1]}, {"i": 3, "skip": True}]}).status_code == 400,
       "Bo'sh ro'yxat va takroriy indeks — 400")
    ok(post_ans({"upload_id": "x" * 16, "answers": [{"i": 3, "correct": [1]}]}).status_code == 404 and post_ans({"upload_id": UP, "answers": [{"i": 3, "correct": [1]}]}, no=NO - 1).status_code in (404, 400),
       "Noma'lum upload_id — 404; boshqa dars uchun upload_id ishlamaydi")
    ok(len(bank_rows()) == n0 and staff.get(U + "/test/pending").json()["upload_id"] == UP, "Xato so'rovlardan keyin Test bank o'zgarmadi, savol hali kutmoqda")
    ok(kaf.post(f"{API}/courses/{CID}/topics/{NO}/test/answers", json={"upload_id": UP, "answers": [{"i": 3, "correct": [1]}]}).status_code == 403
       and teach.post(f"{API}/courses/{CID}/topics/{NO}/test/answers", json={"upload_id": UP, "answers": [{"i": 3, "correct": [1]}]}).status_code == 403
       and kaf.get(U + "/test/pending").status_code == 403, "Kafedra va begona kurs o'qituvchisi javob belgilay olmaydi (403)")
    A1 = {"upload_id": UP, "answers": [{"i": 3, "correct": [1]}]}
    r = post_ans(A1); a1 = r.json() if r.status_code == 200 else {}
    rows = bank_rows(); last = rows[-1] if rows else {}
    ok(r.status_code == 200 and a1["saved"] == 1 and a1["answered"] == 1 and a1["skipped"] == 0 and a1["approved"] == 1 and a1["remaining"] == 0 and a1["needs_answer"] == [] and a1["already"] == 0
       and len(rows) == n0 + 1 and last["stem"] == STEMS[3] and last["qtype"] == "mcq" and json.loads(last["correct"]) == [1] and last["status"] == "tasdiqlandi" and last["blocking"] == 0
       and last["src"] == "import" and last["engine"] == "import", f"Bitta javob: Test bankka tasdiqlangan «mcq» sifatida qo'shildi ({r.status_code} {r.text[:150]})")
    r = post_ans(A1); a2 = r.json() if r.status_code == 200 else {}
    ok(r.status_code == 200 and a2["saved"] == 0 and a2["already"] == 1 and len(bank_rows()) == n0 + 1, "Takroriy so'rov (idempotent): 200, dublikat yaratilmadi (already=1)")
    ok(post_ans({"upload_id": UP, "answers": [{"i": 3, "correct": [0, 2]}]}).json()["already"] == 1 and len(bank_rows()) == n0 + 1
       and json.loads(bank_rows()[-1]["correct"]) == [1], "Allaqachon belgilangan savolni boshqa javob bilan qayta yuborish — e'tiborsiz (birinchisi qoladi)")
    ok(staff.get(U + "/test/pending").json()["needs_answer"] == [] and staff.get(U).json()["ready"]["quiz"]["pending"] == 0, "Hammasi belgilangach: pending bo'sh")
    al = q("SELECT * FROM audit_log WHERE action='paket: test javoblari belgilandi' AND detail LIKE '%belgilandi 1 (%' ORDER BY id LIMIT 1")
    ok(al and al[0]["allowed"] == 1 and al[0]["role"], "Audit: «paket: test javoblari belgilandi» yozildi")
    # --- ko'p javob (checkbox)
    j = up_test(); UP = j["upload_id"]
    r = post_ans({"upload_id": UP, "answers": [{"i": 3, "correct": [2, 0, 2]}]}); m1 = r.json() if r.status_code == 200 else {}
    last = bank_rows()[-1]
    ok(r.status_code == 200 and m1["multi"] == 1 and last["qtype"] == "multi" and json.loads(last["correct"]) == [0, 2] and last["status"] == "tasdiqlandi" and last["blocking"] == 0,
       "Ikki variant belgilandi → «multi» (correct [0, 2], tartiblangan, noyob), tasdiqlangan")
    # --- o'tkazib yuborish: javobsiz qoralama (Test bankda keyin tanlanadi)
    j = up_test(); UP = j["upload_id"]; n0 = len(bank_rows())
    r = post_ans({"upload_id": UP, "answers": [{"i": 3, "skip": True}]}); s1 = r.json() if r.status_code == 200 else {}
    last = bank_rows()[-1]
    ok(r.status_code == 200 and s1["skipped"] == 1 and s1["answered"] == 0 and s1["remaining"] == 0 and len(bank_rows()) == n0 + 1 and last["status"] == "qoralama"
       and json.loads(last["correct"]) == [] and last["blocking"] == 1 and s1["no_answer_ids"] == [last["id"]],
       "O'tkazib yuborish — javobsiz qoralama sifatida Test bankka tushadi (bloklovchi belgi), id qaytadi")
    # --- bir qismi: qolgani kutadi (fixture: 3 ta javobsiz)
    fx3 = docx_bytes(lambda d_: [d_.add_paragraph(t_) for t_ in (
        "1. Birinchi savol matni qanday bo'ladi?", "A) bir ✅", "B) ikki", "C) uch",
        "2. Ikkinchi savol matni qanday bo'ladi?", "A) bir", "B) ikki ✅", "C) uch",
        "3. Uchinchi javobsiz savol matni nima?", "A) bir", "B) ikki", "C) uch",
        "4. To'rtinchi javobsiz savol matni nima?", "A) bir", "B) ikki", "C) uch", "D) to'rt",
        "5. Beshinchi javobsiz savol matni nima?", "A) bir", "B) ikki", "C) uch")])
    j = up_test(content=fx3); UP = j["upload_id"]
    ok(j["questions"] == 5 and j["saved"] == 2 and [x_["i"] for x_ in j["needs_answer"]] == [2, 3, 4] and len(bank_rows()) == 2, "Beshta savoldan 2 tasi saqlandi, 3 tasi (i = 2, 3, 4) kutmoqda")
    r = post_ans({"upload_id": UP, "answers": [{"i": 2, "correct": [0]}, {"i": 3, "correct": [1, 3]}]}); p1 = r.json()
    ok(r.status_code == 200 and p1["saved"] == 2 and p1["remaining"] == 1 and [x_["i"] for x_ in p1["needs_answer"]] == [4] and len(bank_rows()) == 4
       and [r_["qtype"] for r_ in bank_rows()] == ["mcq", "mcq", "mcq", "multi"], "Qisman: 2 tasi belgilandi (mcq + multi), 1 tasi kutishda qoldi")
    ok(staff.get(U + "/test/pending").json()["needs_answer"][0]["i"] == 4 and staff.get(U).json()["ready"]["quiz"]["pending"] == 1, "pending: 1 ta (i=4) — oyna qayta ochilganda ko'rinadi")
    r = post_ans({"upload_id": UP, "answers": [{"i": 2, "correct": [0]}, {"i": 4, "skip": True}]}); p2 = r.json()
    ok(r.status_code == 200 and p2["already"] == 1 and p2["skipped"] == 1 and p2["remaining"] == 0 and len(bank_rows()) == 5, "Qolgani o'tkazildi; avval belgilangani qayta sanalmadi (already=1)")
    # --- o'qituvchi (o'z kursi): qoralama
    TN = int(own["topics"])
    jt = up_test(teach, own["id"], TN)
    rt = post_ans({"upload_id": jt["upload_id"], "answers": [{"i": 3, "correct": [1]}]}, teach, own["id"], TN)
    lt = bank_rows(own["id"], TN)[-1] if rt.status_code == 200 else {}
    ok(rt.status_code == 200 and rt.json()["approved"] == 0 and lt.get("status") == "qoralama" and lt.get("blocking") == 0 and json.loads(lt.get("correct") or "[]") == [1],
       f"O'qituvchi belgilagan savol — qoralama (bo'lim tasdiqlaydi), xatosiz ({rt.status_code} {rt.text[:100]})")
    j = up_test(); post_ans({"upload_id": j["upload_id"], "answers": [{"i": 3, "correct": [1]}]})     # namuna qayta: Test bankda tasdiqlangan multi bor
    # --- Test bank: multi QC va eksport
    from app import testbank as TB
    mq = {"qtype": "multi", "stem": "Qaysilar meva hisoblanadi bu yerda?", "options": ["olma", "sabzi", "nok", "kartoshka"], "correct": [0, 2]}
    codes = lambda **kw: [f["code"] for f in TB.qc({**mq, **kw})]
    ok(codes() == [] and codes(correct=[0]) == ["correct_count"] and codes(correct=[]) == ["correct_count"] and codes(correct=[0, 1, 2, 3]) == ["correct_count"]
       and "correct_range" in codes(correct=[0, 9]), "Test bank QC: multi — kamida 2 ta, hammasi emas; oraliq tekshiriladi")
    ok(TB.qc({**mq, "qtype": "mcq"})[0]["code"] == "correct_count" and "multi" in TB.QTYPES and "multi" not in TB.GEN_TYPES, "mcq'da 2 ta to'g'ri — hamon bloklovchi; «multi» turi bor, AI generatsiyasida yo'q (Claude sxemasi bitta indeks)")
    ex = staff.get(f"/api/testbank/courses/{CID}/export/xml", params={"part": f"t{NO}"})
    xml = ex.text if ex.status_code == 200 else ""
    mb = xml.split(STEMS[4])[-1].split("</question>")[0] if STEMS[4] in xml else ""
    ok("<single>false</single>" in mb and mb.count('fraction="50"') == 2 and mb.count('fraction="-50"') == 2, "Moodle XML: ko'p javobli — single=false, to'g'rilari +50%, noto'g'rilari −50%")
    gf = staff.get(f"/api/testbank/courses/{CID}/export/gift", params={"part": f"t{NO}"}).text
    ok("~%50%" in gf and "~%-50%" in gf, "GIFT: ko'p javobli — ~%50% / ~%-50%")
    ak = staff.get(f"/api/testbank/courses/{CID}/export/aiken", params={"part": f"t{NO}"})
    ok(ak.status_code == 200 and STEMS[4] not in ak.text and int(ak.headers.get("X-Skipped", "0")) >= 1, "Aiken: ko'p javobli savol o'tkazib yuboriladi (X-Skipped)")
    # --- paket → muharrir (dars.py): multi → «multiple», mcq → «single»
    cvr = staff.post(f"/api/dars/subjects/{CID}/lessons/{NO}/convert")
    if cvr.status_code == 200:
        kco = staff.get(f"/api/kurs/courses/{cvr.json()['ku_course_id']}").json()
        ql = next((l_ for l_ in kco["lessons_list"] if l_["type"] == "quiz"), None)
        kb = staff.get(f"/api/kurs/lessons/{ql['id']}").json()["blocks"] if ql else []
        kinds = {b_["data"]["question"]: b_["data"]["kind"] for b_ in kb if b_["type"] == "question"}
        ok(kinds.get(STEMS[4]) == "multiple" and kinds.get(STEMS[0]) == "single" and sum(1 for a_ in next(b_ for b_ in kb if b_["data"]["question"] == STEMS[4])["data"]["answers"] if a_["correct"]) == 2,
           f"paket → muharrir: ko'p javobli savol «Bir nechta javob» (multiple, 2 ta to'g'ri), bir javobli — single ({kinds.get(STEMS[4])})")
    else:
        ok(False, f"paket → muharrir o'tkazish ishlamadi ({cvr.status_code} {cvr.text[:150]})")
    # --- brauzer: eski «Dars tayyorlash» ekrani (static/paket.js) — javobsiz savollar oynasi (konstruktor oynasi — tests/test_konstruktor.py)
    import shutil, subprocess
    node, pwj, chrome = shutil.which("node"), os.environ.get("PW"), os.environ.get("CHROME")
    if not (node and pwj and chrome):
        print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
    else:
        env = dict(os.environ, B=B, KX_UID=str(uid("masofaviy_xodim")), KX_PW=PW, KX_CID=str(CID), KX_KEY=str(NO), KX_TEST=str(FIX / "test.docx"),
                   OUT=os.environ.get("KX_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_paket_answers"))
        rr = subprocess.run([node, str(ROOT / "tools" / "paket_answers_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        nb = 0
        for ln in (rr.stdout + rr.stderr).splitlines():
            s_ = ln.strip()
            if s_.startswith("✓"): ok(True, "[brauzer] " + s_[1:].strip()); nb += 1
            elif s_.startswith("✗"): ok(False, "[brauzer] " + s_[1:].strip())
        ok(rr.returncode == 0 and nb >= 16, f"tools/paket_answers_check.js: kod 0, {nb} ta tekshiruv ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-10:])))
finally:
    # boshqa to'plamlar (testbank, paket) sanoqlariga ta'sir qilmasin — import izlari olib tashlanadi
    for cid_, no_ in ((CID, NO), (own["id"], int(own["topics"]))):
        x("UPDATE tb_questions SET deleted=1 WHERE course_id=? AND topic_no=? AND src='import'", (cid_, no_))
        x("UPDATE pk_exercises SET deleted=1 WHERE course_id=? AND topic_no=? AND src='import'", (cid_, no_))
        x("UPDATE pk_assets SET deleted=1 WHERE course_id=? AND topic_no=? AND purpose='matn' AND name='maruza.docx'", (cid_, no_))
        tr = q("SELECT extra FROM pk_topics WHERE course_id=? AND topic_no=?", (cid_, no_))
        if tr and tr[0]["extra"]:
            e = json.loads(tr[0]["extra"]); e.pop("questions", None)
            x("UPDATE pk_topics SET extra=? WHERE course_id=? AND topic_no=?", (json.dumps(e, ensure_ascii=False), cid_, no_))

print(f"\n{'XATO: ' + str(len(fails)) if fails else 'HAMMASI OK'}")
for f in fails: print("  -", f)
sys.exit(1 if fails else 0)
