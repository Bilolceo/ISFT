"""Kurs muharriri: «AI bilan tahrirlash» (app/kurs_ai.py, POST /api/kurs/lessons/{lid}/ai-question) — ruxsatlar (403), deterministik ✅ tahlili
(kalitsiz ham ishlaydi: 503 + tuzilma), soxta Claude (faqat shu jarayon ichida, bazaning vaqtinchalik nusxasida): har variant izohi, javobni taxmin
qilish (answer_guessed), ✅ ni AI o'zgartirsa tiklanishi, yaroqsiz AI javobi rad etilishi, tur majburlash, kunlik cheklov, audit va ku_ai jadvali.

Ishga tushirish:  python tests/run_all.py --only kurs_ai   (yoki ISFT_TEST_URL=… ISFT_CORE_DB=… .venv/bin/python tests/test_kurs_ai.py)
DIQQAT: bazani o'zgartiradi (kurslar yaratiladi) — PRODUCTION'da ishlatilmaydi. Server tomonda haqiqiy Anthropic API chaqirilmaydi.
"""
import json, os, re, sqlite3, sys, tempfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def uid(role):
    r = q("SELECT id FROM users WHERE role=? AND active=1 ORDER BY id LIMIT 1", (role,)); assert r, f"{role} akkaunti yo'q"; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=600)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
P = "/api/kurs"
WORD = """3. Startap qanday kompaniya hisoblanadi?
A) Davlat unitar korxonasi
B) Tez o‘sishga yo‘naltirilgan yangi kompaniya ✅
C) Faqat eksport bilan shug‘ullanadigan firma
D) Yirik xolding tarkibidagi bo‘linma"""
PLAIN = """Startap qanday kompaniya hisoblanadi?
A) Davlat unitar korxonasi
B) Tez o'sishga yo'naltirilgan yangi kompaniya
C) Faqat eksport bilan shug'ullanadigan firma
D) Yirik xolding tarkibidagi bo'linma"""

head, teach, rek, kaf = (S(uid(r)) for r in ("masofaviy", "oqituvchi", "rektor", "kafedra"))
teach_uid = uid("oqituvchi")

# =============================================================================================
print("== 1. HTTP: ruxsatlar va kalitsiz holat")
tc = teach.post(P + "/courses", json={"title": "AI savol sinovi (o'qituvchi)"}).json()["id"]
tl = teach.get(f"{P}/courses/{tc}").json()["lessons_list"][0]["id"]
hc = head.post(P + "/courses", json={"title": "AI savol sinovi (bo'lim)"}).json()["id"]
hl = head.get(f"{P}/courses/{hc}").json()["lessons_list"][0]["id"]
ok(teach.post(f"{P}/lessons/{hl}/ai-question", json={"text": WORD}).status_code == 403, "O'qituvchi begona kursda AI savol so'rolmaydi (403)")
ok(rek.post(f"{P}/lessons/{hl}/ai-question", json={"text": WORD}).status_code == 403 and kaf.post(f"{P}/lessons/{hl}/ai-question", json={"text": WORD}).status_code == 403,
   "Rektor va kafedra mudiri — 403 (faqat muallif / bo'lim)")
ok(head.post(f"{P}/lessons/999999/ai-question", json={"text": WORD}).status_code == 404, "Mavjud bo'lmagan dars — 404")
ok(teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": ""}).status_code == 400 and teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": "x" * 7000}).status_code == 400,
   "Bo'sh yoki juda uzun matn — 400")
ok(teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": WORD, "qtype": "zzz"}).status_code == 400, "Noma'lum savol turi — 400")
n_ai0 = q("SELECT COUNT(*) n FROM ku_ai")[0]["n"]
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": WORD})
j = r.json()
ok(r.status_code == 503 and "AI ulanmagan" in j["detail"] and "ANTHROPIC" not in j["detail"], "Kalitsiz — 503 va o'zbekcha aniq xabar")
b = (j.get("block") or {}).get("data") or {}
ok(j.get("ai") is False and j.get("parsed") is True and b.get("kind") == "single" and b["question"].startswith("Startap qanday")
   and [a["correct"] for a in b["answers"]] == [False, True, False, False] and not any(a["feedback"] for a in b["answers"]),
   "Kalitsiz ham ✅ dan tuzilma qaytadi: savol, 4 variant, to'g'ri javob B, izohsiz (ai=false)")
ok(not any(i["level"] == "xato" for i in j["issues"]) and j["block"]["type"] == "knowledge", "Dars (blocks) — «knowledge» bloki, tuzilmada xato yo'q")
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": "Bu faqat oddiy gap, savol emas"})
ok(r.status_code == 503 and r.json().get("block") is None and "✅" in r.json()["detail"], "Savol emas va kalit yo'q — 503, tuzilmasiz, ✅ yo'riqnomasi")
ok(q("SELECT COUNT(*) n FROM ku_ai")[0]["n"] == n_ai0, "Kalitsiz so'rovlar kunlik cheklovga sanalmaydi")
aud = q("SELECT allowed, action FROM audit_log WHERE action LIKE 'kurs: AI%' ORDER BY id DESC LIMIT 40")
ok(any(a["action"].startswith("kurs: AI savol — AI ulanmagan") for a in aud) and any(a["allowed"] == 0 and a["action"] == "kurs: AI bilan savol" for a in aud), "Audit: AI ulanmagan yozuvi va rad etilgan so'rov yozuvi")
# fill / tf aniq tur (deterministik yo'l: variantli savolni bo'sh joy sifatida so'rash — AI kerak)
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": WORD, "qtype": "fill"})
ok(r.status_code == 503 and r.json().get("block") is None, "«Bo'sh joy» so'rovi variantli savolni o'zgartirmaydi (kalitsiz — tuzilmasiz)")
tfq = "Startap yangi kompaniya hisoblanadi.\nA) To'g'ri ✅\nB) Noto'g'ri"
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": tfq, "qtype": "tf"}).json()
ok(r["block"]["data"]["kind"] == "truefalse" and [a["correct"] for a in r["block"]["data"]["answers"]] == [True, False], "To'g'ri/Noto'g'ri variantlari — «truefalse» (deterministik)")
tfq2 = "Startap yangi kompaniya hisoblanadi.\nA) Noto'g'ri\nB) To'g'ri ✅"
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": tfq2}).json()
ok(r["block"]["data"]["kind"] == "truefalse" and [a["text"] for a in r["block"]["data"]["answers"]] == ["To'g'ri", "Noto'g'ri"]
   and [a["correct"] for a in r["block"]["data"]["answers"]] == [True, False], "Teskari tartibli «Noto'g'ri / To'g'ri ✅» me'yorlanadi (To'g'ri birinchi)")
two = "1. Birinchi savol nima?\nA) bir ✅\nB) ikki\n2. Ikkinchi savol nima?\nA) uch\nB) to'rt ✅"
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": two}).json()
ok(r["more"] == 1 and r["block"]["data"]["question"].startswith("Birinchi") and any("2 ta savol" in w for w in r["warnings"]), "Bir nechta savol — birinchisi olinadi, ogohlantirish")
mu = "Quyidagilardan davlat organlarini tanlang?\nA) Vazirlar Mahkamasi ✅\nB) Tijorat banki\nC) Senat ✅"
r = teach.post(f"{P}/lessons/{tl}/ai-question", json={"text": mu}).json()
ok(r["block"]["data"]["kind"] == "multiple" and [a["correct"] for a in r["block"]["data"]["answers"]] == [True, False, True], "Ikki ✅ — «Bir nechta javob»")

# =============================================================================================
print("== 2. Jarayon ichida: soxta Claude (bazaning vaqtinchalik nusxasi)")
tmp = Path(tempfile.mkdtemp(prefix="kuai-"))
srcc = sqlite3.connect(DBP); dst = sqlite3.connect(tmp / "copy.db", check_same_thread=False); srcc.backup(dst); srcc.close()
dst.row_factory = sqlite3.Row
from app import claude_client as CC, rbac as RB, kurs as K, kurs_ai as KA
K.migrate(dst)
saved_cc = (CC.call_json, CC.has_key)
saved_k = (K._con, K._ctx)
calls = []
OUT = {}
def fake(**kw):
    calls.append(kw)
    v = OUT["v"]
    if isinstance(v, Exception): raise v
    return v, {"in": 321, "out": 123, "model": kw["model"]}
GOOD = {"kind": "single", "question": "Startap qanday kompaniya hisoblanadi?",
        "options": [{"text": "Davlat unitar korxonasi", "correct": False, "feedback": "Startap davlat korxonasi emas."},
                    {"text": "Tez o'sishga yo'naltirilgan yangi kompaniya", "correct": True, "feedback": "To'g'ri: startap — tez o'sishga mo'ljallangan yangi kompaniya."},
                    {"text": "Faqat eksport bilan shug'ullanadigan firma", "correct": False, "feedback": "Startap faoliyati eksport bilan cheklanmaydi."},
                    {"text": "Yirik xolding tarkibidagi bo'linma", "correct": False, "feedback": "Startap odatda mustaqil yangi kompaniya."}],
        "accept": [], "feedback_correct": "Startap — tez o'sishga yo'naltirilgan yangi kompaniya.", "feedback_wrong": "Startap ta'rifini takrorlang.", "answer_guessed": False}
def variant(**ch):
    d = json.loads(json.dumps(GOOD)); d.update(ch); return d
try:
    K.bind(dst, None); CC.has_key = lambda: True; CC.call_json = fake
    tctx = RB.ctx_for(dst, teach_uid)
    lid = dst.execute("SELECT id FROM ku_lessons WHERE course_id=? ORDER BY id LIMIT 1", (tc,)).fetchone()[0]
    OUT["v"] = GOOD
    code, res = KA.ai_question(tctx, lid, {"text": WORD})
    d = res["block"]["data"]
    ok(code == 200 and res["ai"] is True and res["parsed"] is True and res["answer_guessed"] is False, "✅ li savol + AI: 200, ai=true, javob taxmin emas")
    ok(all(a["feedback"] for a in d["answers"]) and d["feedback_correct"] and d["feedback_wrong"], "HAR BIR variantga izoh + umumiy izohlar (kurs blok shaklida)")
    ok([a["correct"] for a in d["answers"]] == [False, True, False, False] and d["kind"] == "single", "To'g'ri javob — B (✅ bilan bir xil)")
    ok(K.clean_block("knowledge", d, K._Assets(None))["answers"] == d["answers"] and not [i for i in res["issues"] if i["level"] == "xato"],
       "Blok kurs.clean_block'dan o'tgan (qayta tozalash natijani o'zgartirmaydi), xato yo'q")
    kw = calls[-1]
    sent = kw["content"][0]["text"]
    ok(kw["model"] == "claude-opus-5-5" and kw["schema"] is KA.SCHEMA and kw["schema"]["additionalProperties"] is False
       and kw["schema"]["properties"]["options"]["items"]["required"] == ["text", "correct", "feedback"], "AI so'rovi: model, qat'iy JSON sxema")
    ok("<savol>" in sent and "Startap qanday" in sent and "[TO`G`RI]" in sent and "MA'LUMOT" in kw["system"] and "o'ylab topmang" in kw["system"], "So'rovda savol + avtomatik tahlil; tizim: matn — ma'lumot, fakt o'ylab topmaslik")
    stud = [r_["full_name"] for r_ in dst.execute("SELECT full_name FROM students LIMIT 50")]
    ok(not any(n and n in sent for n in stud) and "hemis" not in sent.lower(), "So'rovda talabalar ma'lumoti yo'q")
    row = dict(dst.execute("SELECT * FROM ku_ai ORDER BY id DESC LIMIT 1").fetchone())
    ok(row["ok"] == 1 and row["in_tok"] == 321 and row["out_tok"] == 123 and row["user_id"] == teach_uid and row["guessed"] == 0 and row["course_id"] == tc, "ku_ai: token sarfi, foydalanuvchi, kurs")
    ok(res["quota"]["used"] == 1 and res["quota"]["limit"] == 100, "Kunlik cheklov holati qaytadi (1 / 100)")
    a = dst.execute("SELECT action, detail FROM audit_log WHERE action='kurs: AI savol' ORDER BY id DESC LIMIT 1").fetchone()
    ok(a and f"dars #{lid}" in a["detail"], "Audit jurnali: «kurs: AI savol»")
    ok(not dst.execute("SELECT 1 FROM ku_blocks WHERE data LIKE '%Startap qanday%'").fetchone(), "Endpoint bazaga blok YOZMAYDI (faqat ko'rsatadi)")

    # ✅ yo'q → AI to'g'ri javobni tanlaydi → answer_guessed
    OUT["v"] = variant(answer_guessed=False)
    code, res = KA.ai_question(tctx, lid, {"text": PLAIN})
    ok(code == 200 and res["answer_guessed"] is True and res["parsed"] is True, "✅ siz savol: AI javobni topdi → answer_guessed=true (AI «false» desa ham)")
    ok(dst.execute("SELECT guessed FROM ku_ai ORDER BY id DESC LIMIT 1").fetchone()[0] == 1, "ku_ai.guessed = 1")
    # ko'rsatma bilan boshidan yaratish (matnsiz variantlar)
    OUT["v"] = variant()
    code, res = KA.ai_question(tctx, lid, {"text": "", "hint": "Startap haqida bitta savol tuz"})
    ok(code == 200 and res["parsed"] is False and res["answer_guessed"] is True and "Startap haqida" in calls[-1]["content"][0]["text"], "Faqat ko'rsatma: yangi savol, parsed=false, javob taxmin")
    # ✅ ni AI o'zgartirsa — tiklanadi
    wrong = variant(); 
    for i_, o in enumerate(wrong["options"]): o["correct"] = i_ == 0
    OUT["v"] = wrong
    code, res = KA.ai_question(tctx, lid, {"text": WORD})
    ok(code == 200 and [a["correct"] for a in res["block"]["data"]["answers"]] == [False, True, False, False] and any("tiklandi" in w for w in res["warnings"]) and res["answer_guessed"] is False,
       "AI ✅ ni o'zgartirdi — o'qituvchi belgisi tiklandi + ogohlantirish")
    # tozalangan variant matni, uzun izoh qirqiladi
    cl = variant(); cl["options"][0]["feedback"] = "x" * 900
    OUT["v"] = cl
    code, res = KA.ai_question(tctx, lid, {"text": WORD})
    ok(code == 200 and all(len(a["feedback"]) <= 300 for a in res["block"]["data"]["answers"]), "Variant izohi ≤ 300 belgi")

    # to'g'ri/noto'g'ri, bo'sh joy, bir nechta javob (AI)
    TFV = {"kind": "truefalse", "question": "Startap yangi kompaniya hisoblanadi.", "options": [
        {"text": "Noto'g'ri", "correct": False, "feedback": "Aksincha."}, {"text": "To'g'ri", "correct": True, "feedback": "Ha."}],
        "accept": [], "feedback_correct": "Ha.", "feedback_wrong": "", "answer_guessed": True}
    OUT["v"] = TFV
    code, res = KA.ai_question(tctx, lid, {"text": "Startap yangi kompaniya hisoblanadi — to'g'rimi?", "qtype": "tf"})
    d = res["block"]["data"]
    ok(code == 200 and d["kind"] == "truefalse" and [a["text"] for a in d["answers"]] == ["To'g'ri", "Noto'g'ri"] and [a["correct"] for a in d["answers"]] == [True, False]
       and d["answers"][0]["feedback"] == "Ha." and res["answer_guessed"] is True, "To'g'ri/Noto'g'ri: tartib me'yorlandi, izohlar o'rnida")
    ok("tf" in calls[-1]["content"][0]["text"] or "truefalse" in calls[-1]["content"][0]["text"], "So'ralgan tur AI so'roviga yuboriladi")
    FILL = {"kind": "fill", "question": "Startaplar odatda ____ investitsiyalar hisobiga moliyalashtiriladi.", "options": [], "accept": ["venchur", "Venchur"],
            "feedback_correct": "Venchur investitsiyalari.", "feedback_wrong": "", "answer_guessed": True}
    OUT["v"] = FILL
    code, res = KA.ai_question(tctx, lid, {"text": "Startaplar odatda ... investitsiyalar hisobiga moliyalashtiriladi. Javob: venchur", "qtype": "fill"})
    ok(code == 200 and res["block"]["data"]["kind"] == "fill" and res["block"]["data"]["accept"] == ["venchur"], "Bo'sh joy: javoblar takrorsiz (katta-kichik harf farqi)")
    MULTI = variant(kind="multiple", question="Davlat organlarini tanlang?", options=[
        {"text": "Vazirlar Mahkamasi", "correct": True, "feedback": "Ijro hokimiyati organi."}, {"text": "Tijorat banki", "correct": False, "feedback": "Xususiy tashkilot."},
        {"text": "Senat", "correct": True, "feedback": "Qonun chiqaruvchi organ palatasi."}])
    OUT["v"] = MULTI
    code, res = KA.ai_question(tctx, lid, {"text": mu})
    ok(code == 200 and res["block"]["data"]["kind"] == "multiple" and sum(a["correct"] for a in res["block"]["data"]["answers"]) == 2, "Bir nechta javob: 2 ta to'g'ri")
    OUT["v"] = variant(kind="multiple", options=[dict(o, correct=(i_ == 1)) for i_, o in enumerate(GOOD["options"])])
    code, res = KA.ai_question(tctx, lid, {"text": PLAIN})
    ok(code == 200 and res["block"]["data"]["kind"] == "single" and any("Bitta javob" in w for w in res["warnings"]), "«multiple» lekin bitta to'g'ri — «Bitta javob»ga o'tkaziladi")
    # quiz darsi — «question» bloki
    qid = dst.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                      (tc, "lq0000000001", 9, "quiz", "Test", "{}", K._now(), "t")).lastrowid
    OUT["v"] = GOOD
    code, res = KA.ai_question(tctx, qid, {"text": WORD})
    ok(code == 200 and res["block"]["type"] == "question", "Test darsida natija — «question» bloki")

    # yaroqsiz AI javoblari rad etiladi (502 + ✅ dan tuzilma)
    n_row = dst.execute("SELECT COUNT(*) FROM ku_ai").fetchone()[0]
    BAD = {
        "1 ta variant": variant(options=GOOD["options"][:1]),
        "9 ta variant": variant(options=[{"text": f"V{i_}", "correct": i_ == 0, "feedback": "x"} for i_ in range(9)]),
        "takroriy variant": variant(options=[dict(GOOD["options"][1]), dict(GOOD["options"][1]), GOOD["options"][2], GOOD["options"][3]]),
        "bo'sh variant": variant(options=[dict(GOOD["options"][0], text=" "), *GOOD["options"][1:]]),
        "variantlar soni o'zgargan": variant(options=GOOD["options"][:3]),
        "noma'lum tur": variant(kind="essay"),
        "bo'sh savol": variant(question=" "),
        "obyekt emas": ["x"],
        "tf — begona variantlar": variant(kind="truefalse", options=[{"text": "Rost", "correct": True, "feedback": ""}, {"text": "Yolg'on", "correct": False, "feedback": ""}]),
        "fill — javobsiz": variant(kind="fill", options=[], accept=[" ", ""]),
        "variantli savol fill sifatida": variant(kind="fill", options=[], accept=["B"]),
    }
    for name, v in BAD.items():
        OUT["v"] = v
        code, res = KA.ai_question(tctx, lid, {"text": WORD})
        ok(code == 502 and "yaroqsiz" in res["detail"] and res["ai"] is False and res["block"]["data"]["answers"][1]["correct"] is True and "✅" in res["detail"], f"Yaroqsiz AI javobi rad: {name} → 502 + ✅ dan tuzilma")
    for name, v in {"to'g'ri javob yo'q": variant(options=[dict(o, correct=False) for o in GOOD["options"]]),
                    "bitta javobli savolda 2 ta to'g'ri": variant(options=[dict(o, correct=i_ < 2) for i_, o in enumerate(GOOD["options"])])}.items():
        OUT["v"] = v                                                       # ✅ siz savol: AI javobi mantiqsiz bo'lsa — rad
        code, res = KA.ai_question(tctx, lid, {"text": PLAIN})
        ok(code == 502 and "yaroqsiz" in res["detail"] and res["answer_missing"] is True, f"Yaroqsiz AI javobi rad (✅ siz savol): {name} → 502")
        OUT["v"] = v                                                       # ✅ li savol: o'qituvchi belgisi ustun — AI xatosi tuzatiladi
        code, res = KA.ai_question(tctx, lid, {"text": WORD})
        ok(code == 200 and [a["correct"] for a in res["block"]["data"]["answers"]] == [False, True, False, False], f"✅ li savolda AI xatosi tuzatiladi: {name}")
    ok(dst.execute("SELECT COUNT(*) FROM ku_ai WHERE ok=0 AND err LIKE 'AI javobi yaroqsiz%'").fetchone()[0] == len(BAD) + 2 and dst.execute("SELECT COUNT(*) FROM ku_ai").fetchone()[0] == n_row + len(BAD) + 4,
       "Rad etilgan so'rovlar ku_ai da ok=0 va sababi bilan")
    OUT["v"] = variant(kind="single")
    code, res = KA.ai_question(tctx, lid, {"text": WORD, "qtype": "tf"})
    ok(code == 502 and "yaroqsiz" in res["detail"], "So'ralgan tur (tf) bilan mos kelmasa — rad")
    OUT["v"] = CC.AIError("AI xizmati hozir band (so'rovlar cheklovi).")
    code, res = KA.ai_question(tctx, lid, {"text": PLAIN})
    ok(code == 502 and "band" in res["detail"] and res["block"] and res["ai"] is False, "AI xatosi — 502, o'zbekcha matn, ✅siz bo'lsa ham tuzilma (javobsiz)")
    ok(res.get("answer_missing") is True, "✅siz tuzilmada answer_missing=true (to'g'ri javobni o'zi belgilaydi)")
    OUT["v"] = RuntimeError("kutilmagan")
    code, res = KA.ai_question(tctx, lid, {"text": WORD})
    ok(code == 502 and "RuntimeError" in res["detail"], "Kutilmagan xato — 502 (ilova yiqilmaydi)")
    # kalit yo'q (jarayon ichida ham)
    CC.has_key = lambda: False
    n_calls = len(calls)
    code, res = KA.ai_question(tctx, lid, {"text": WORD})
    ok(code == 503 and res["block"] and res["ai"] is False and len(calls) == n_calls, "Kalitsiz — AI chaqirilmaydi, 503 + tuzilma")
    CC.has_key = lambda: True
    # begona kurs — rad
    hlid = dst.execute("SELECT id FROM ku_lessons WHERE course_id=? ORDER BY id LIMIT 1", (hc,)).fetchone()[0]
    try: KA.ai_question(tctx, hlid, {"text": WORD}); ok(False, "begona kursga AI savol o'tdi")
    except RB.AccessDenied: ok(True, "Begona kurs darsi — AccessDenied")
    # kunlik cheklov
    os.environ["ISFT_CORE_KURS_AI_DAILY"] = "1"
    n_calls = len(calls); OUT["v"] = GOOD
    try: KA.ai_question(tctx, lid, {"text": WORD}); ok(False, "kunlik cheklov ishlamadi")
    except KA.HTTPException as e: ok(e.status_code == 429 and "Kunlik cheklov" in e.detail and len(calls) == n_calls, "Kunlik cheklov (ISFT_CORE_KURS_AI_DAILY) — 429, AI chaqirilmadi")
    os.environ["ISFT_CORE_KURS_AI_DAILY"] = "100000"
    # eskirgan «jarayonda» qatori cheklovga sanalmaydi
    dst.execute("DELETE FROM ku_ai"); dst.execute("INSERT INTO ku_ai(user_id,day,ts,ok,err) VALUES(?,?,?,0,'jarayonda')", (teach_uid, KA.clock.today().isoformat(), "2000-01-01T00:00:00"))
    os.environ["ISFT_CORE_KURS_AI_DAILY"] = "1"
    code, res = KA.ai_question(tctx, lid, {"text": WORD})
    ok(code == 200, "Yiqilgan (eskirgan «jarayonda») so'rov cheklovga sanalmaydi")
finally:
    os.environ.pop("ISFT_CORE_KURS_AI_DAILY", None)
    CC.call_json, CC.has_key = saved_cc
    K._con, K._ctx = saved_k
    dst.close()

src = (ROOT / "app" / "kurs_ai.py").read_text()
ok("FAKE" not in src and "ISFT_CORE_KURS_AI_FAKE" not in src, "kurs_ai.py da soxta AI rejimi (muhit o'zgaruvchisi) yo'q")
print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
