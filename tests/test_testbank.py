"""Test bank moduli (app/testbank.py) — ruxsatlar, sifat qoidalari (QC), mavzu matni, AI generatsiya (soxta Claude — faqat shu jarayon ichida),
ko'rib chiqish oqimi, oraliq taqsimoti, banklar va eksport (Moodle XML, GIFT, Aiken, .docx), qamrov.

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_testbank.py
   (yoki hammasi toza muhitda: python tests/run_all.py --only testbank)
DIQQAT: lokal bazani o'zgartiradi (savollar, manba matni, oraliq taqsimoti) — PRODUCTION'da ishlatilmaydi.
AI generatsiya serverda chaqirilmaydi: claude_client.call_json shu test jarayonida (bazaning vaqtinchalik nusxasida) almashtiriladi —
ilovada hech qanday «soxta AI» muhit o'zgaruvchisi yo'q.
"""
import io, json, math, os, re, sqlite3, sys, tempfile, xml.etree.ElementTree as ET
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
def uid(role, where="", args=()):
    r = q(f"SELECT id FROM users WHERE role=? {where} ORDER BY id LIMIT 1", (role, *args)); assert r, f"{role} akkaunti yo'q"; return r[0]["id"]
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
P = "/api/testbank"

from app import testbank as TB   # sof funksiyalar (QC, eksport) — baza talab qilmaydi

head, staff, rek, pro, kaf, teach, bux, cc = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "rektor", "prorektor_oquv", "kafedra", "oqituvchi", "buxgalteriya", "call_center"))
teach_uid = uid("oqituvchi")
teach_tid = q("SELECT teacher_id FROM users WHERE id=?", (teach_uid,))[0]["teacher_id"]
kaf_dept = q("SELECT department_id FROM users WHERE id=?", (uid("kafedra"),))[0]["department_id"]
mikro = q("SELECT * FROM dl_courses WHERE subject='Mikroiqtisodiyot' ORDER BY id LIMIT 1")[0]
kaf8 = S(uid("kafedra", "AND department_id=?", (mikro["department_id"],)))
own = q("SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY subject='Innovatsion iqtisodiyot' DESC, id LIMIT 1", (teach_tid,))[0]
other_dept = q("SELECT * FROM dl_courses WHERE department_id!=? ORDER BY id LIMIT 1", (kaf_dept,))[0]

# =============================================================================================
print("== 1. Ruxsatlar va ko'lam")
m = head.get(P + "/meta").json()
ok(m["tabs"] == ["qamrov", "mavzu", "bank", "sozlama"] and m["caps"]["review"] and m["caps"]["settings"], "Bo'lim boshlig'i: 4 bo'lim, tasdiqlash va sozlamalar")
ms = staff.get(P + "/meta").json()
ok(ms["caps"]["review"] and not ms["caps"]["settings"], "Bo'lim xodimi: tasdiqlaydi, umumiy sozlamani o'zgartirmaydi")
mt = teach.get(P + "/meta").json()
ok(mt["caps"]["generate"] and not mt["caps"]["review"] and "sozlama" in mt["tabs"], "O'qituvchi: generatsiya bor, tasdiqlash yo'q")
mk = kaf.get(P + "/meta").json()
ok(not mk["caps"]["write"] and mk["caps"]["questions"] and mk["tabs"] == ["qamrov", "mavzu", "bank"], "Kafedra mudiri: faqat ko'rish va eksport")
mr = rek.get(P + "/meta").json()
ok(mr["tabs"] == ["qamrov"] and not mr["caps"]["questions"], "Rektor: faqat jamlangan qamrov")
ok(pro.get(P + "/meta").json()["tabs"] == ["qamrov"], "O'quv prorektori: faqat jamlangan qamrov")
ok(m["demo"] and m["ai"]["on"] is False, "Namuna belgisi bor; testda AI kaliti yo'q")
ok(rek.get(f"{P}/courses/{mikro['id']}").status_code == 403 and rek.get(f"{P}/courses/{mikro['id']}/topics/1/questions").status_code == 403,
   "Rektor savollar matnini ko'rmaydi (403)")
ok(rek.get(f"{P}/courses/{mikro['id']}/export/xml").status_code == 403, "Rektor bank eksport qilolmaydi (403)")
ok(bux.get(P + "/meta").status_code == 403 and cc.get(P + "/coverage").status_code == 403, "Buxgalteriya va call-markaz — ruxsat yo'q (403)")
ok(teach.get(f"{P}/courses/{mikro['id']}").status_code == 403, "O'qituvchi begona kursni ochmaydi (403)")
ok(kaf.get(f"{P}/courses/{other_dept['id']}").status_code == 403, "Kafedra mudiri boshqa kafedra kursini ochmaydi (403)")
ok(kaf8.get(f"{P}/courses/{mikro['id']}").status_code == 200, "Kafedra mudiri o'z kafedrasi kursini ko'radi")
ok(kaf8.post(f"{P}/courses/{mikro['id']}/topics/4/questions", json={"qtype": "tf", "stem": "Bu sinov uchun yozilgan tasdiq jumla.", "correct": [0]}).status_code == 403,
   "Kafedra mudiri savol qo'sholmaydi (403)")
tc = teach.get(P + "/courses?limit=400").json()
ok(tc["total"] > 0 and all(r["teacher_id"] == teach_tid for r in tc["items"]), f"O'qituvchi faqat o'z kurslarini ko'radi ({tc['total']} ta)")
kc = kaf.get(P + "/courses?limit=400").json()
ok(kc["total"] > 0 and all(r["department_id"] == kaf_dept for r in kc["items"]), f"Kafedra faqat o'z kafedrasi kurslarini ko'radi ({kc['total']} ta)")
hc = head.get(P + "/courses?limit=1").json()
ok(hc["total"] == q("SELECT COUNT(*) n FROM dl_courses")[0]["n"], "Bo'lim — barcha kurslar (masofaviy kontent rejasidagi kurslar bilan bir xil)")
den = q("SELECT COUNT(*) n FROM audit_log WHERE resource='testbank' AND allowed=0")[0]["n"]
ok(den >= 7, f"Rad etilgan so'rovlar audit jurnalida ({den} ta)")
cv = head.get(f"{P}/courses/{mikro['id']}").json()
ok(len(cv["topics"]) == mikro["topics"] and cv["topics"][1]["title"] == q("SELECT topic FROM dl_items WHERE course_id=? AND topic_no=2 LIMIT 1", (mikro["id"],))[0]["topic"],
   "Mavzular ro'yxati masofaviy kontent rejasidan (dl_items) olinadi")

# =============================================================================================
print("== 2. Sifat qoidalari (har bir qoida: musbat / manfiy)")
SRC = "Talab qonuniga ko'ra, narx oshsa talab miqdori kamayadi. Muvozanat narxi P = 20 ga teng."
def mcq(opts, corr=(0,), stem="Talab qonuniga ko'ra narx oshsa nima bo'ladi?", **kw):
    return {"qtype": "mcq", "stem": stem, "options": list(opts), "correct": list(corr), **kw}
def codes(qd, src=None, others=()):
    return {(f["code"], f["sev"]) for f in TB.qc(qd, src, others)}
GOOD = mcq(["Talab miqdori kamayadi", "Talab miqdori ortadi", "Taklif miqdori kamayadi", "Hech narsa o'zgarmaydi"])
ok(codes(GOOD) == set(), "To'g'ri tuzilgan savol — belgisiz")
ok(("format", "block") in codes(mcq(["A javob", "B javob"])) and ("format", "block") in codes(mcq(["A", "", "C", "D"])), "format: 2 ta variant / bo'sh variant — bloklovchi")
ok(("format", "block") not in codes(GOOD), "format: 4 ta to'liq variant — belgisiz")
ok(("correct_count", "block") in codes(mcq(GOOD["options"], (0, 1))) and ("correct_count", "block") in codes(mcq(GOOD["options"], ())), "correct_count: 2 ta / 0 ta to'g'ri — bloklovchi")
ok(not any(c == "correct_count" for c, _ in codes(GOOD)), "correct_count: aynan 1 ta — belgisiz")
ok(("correct_range", "block") in codes(mcq(GOOD["options"], (4,))), "correct_range: 5-variant (4 ta bor) — bloklovchi")
ok(not any(c == "correct_range" for c, _ in codes(mcq(GOOD["options"], (3,)))), "correct_range: oxirgi variant — belgisiz")
ok(("dup_option", "block") in codes(mcq(["Talab kamayadi", "talab  kamayadi.", "Taklif ortadi", "Narx tushadi"])), "dup_option: bir xil variant (registr/bo'shliq farqi) — bloklovchi")
ok(("dup_option", "warn") in codes(mcq(["Mehnat va kapital", "Kapital va mehnat", "Yer va tadbirkorlik", "Faqat pul"])), "dup_option: so'zlar o'rni almashgan — ogohlantirish")
ok(not any(c == "dup_option" for c, _ in codes(GOOD)), "dup_option: farqli variantlar — belgisiz")
ok(("num_equiv", "block") in codes(mcq(["20", "20,0", "40", "60"])) and ("num_equiv", "block") in codes(mcq(["1/2", "0.5", "2", "5"])) and
   ("num_equiv", "block") in codes(mcq(["50%", "0,5", "25%", "75%"])) and ("num_equiv", "block") in codes(mcq(["1 000 so'm", "1000 so'm", "500 so'm", "2000 so'm"])),
   "num_equiv: 20 = 20,0; 1/2 = 0.5; 50% = 0,5; «1 000 so'm» = «1000 so'm» — bloklovchi")
ok(not any(c == "num_equiv" for c, _ in codes(mcq(["20", "40", "60", "80"]))) and not any(c == "num_equiv" for c, _ in codes(mcq(["5 kg", "5 so'm", "10 kg", "1 t"]))),
   "num_equiv: turli sonlar / turli birliklar — belgisiz")
ok(("all_none", "warn") in codes(mcq(["Talab kamayadi", "Taklif ortadi", "Narx tushadi", "Yuqoridagilarning barchasi"])) and
   ("all_none", "warn") in codes(mcq(["Talab kamayadi", "Taklif ortadi", "Narx tushadi", "Hech biri"])), "all_none: «barchasi» / «hech biri» — ogohlantirish")
ok(not any(c == "all_none" for c, _ in codes(GOOD)), "all_none: oddiy variantlar — belgisiz")
ok(("answer_in_stem", "warn") in codes(mcq(["Bozor muvozanati", "Taqchillik", "Ortiqcha taklif", "Monopoliya"], stem="Talab va taklif tengligi bozor muvozanati deyiladi. Bu nima?")),
   "answer_in_stem: to'g'ri javob savolda aynan bor — ogohlantirish")
ok(not any(c == "answer_in_stem" for c, _ in codes(GOOD)), "answer_in_stem: javob savolda yo'q — belgisiz")
ok(("longest_correct", "warn") in codes(mcq(["O'ngga siljiydi, chunki har bir narxda ko'proq tovar taklif qilinadi", "Chapga siljiydi", "O'zgarmaydi", "Pastga egiladi"])),
   "longest_correct: to'g'ri javob sezilarli uzun — ogohlantirish")
ok(not any(c == "longest_correct" for c, _ in codes(GOOD)), "longest_correct: uzunliklar teng — belgisiz")
ok(("short_stem", "warn") in codes(mcq(GOOD["options"], stem="Talab?")), "short_stem: «Talab?» — ogohlantirish")
ok(not any(c == "short_stem" for c, _ in codes(GOOD)), "short_stem: to'liq savol — belgisiz")
FILL = {"qtype": "fill", "stem": "Taklif qonuniga ko'ra narx oshganda taklif miqdori ____.", "answers": ["ortadi"]}
ok(codes(FILL) == set(), "fill: to'g'ri tuzilgan — belgisiz")
ok(("answer_leak", "block") in codes({**FILL, "stem": "Narx oshganda taklif ortadi, ya'ni taklif ____."}), "answer_leak: javob savolda bor — bloklovchi")
ok(("no_blank", "warn") in codes({**FILL, "stem": "Taklif qonuniga ko'ra narx oshganda taklif miqdori nima bo'ladi?"}), "no_blank: «____» yo'q — ogohlantirish")
ok(("format", "block") in codes({**FILL, "answers": []}), "fill: javobsiz — bloklovchi")
TF = {"qtype": "tf", "stem": "Narx oshsa talab miqdori kamayadi.", "options": TB.TF_OPTIONS, "correct": [0]}
ok(codes(TF) == set() and ("correct_count", "block") in codes({**TF, "correct": []}), "tf: to'g'ri — belgisiz; javobsiz — bloklovchi")
ok(("dup_question", "warn") in codes(GOOD, None, [(7, "Talab qonuniga ko'ra, narx oshsa nima bo'ladi?")]), "dup_question: kursda o'xshash savol — ogohlantirish")
ok(not any(c == "dup_question" for c, _ in codes(GOOD, None, [(7, "Monopoliya qanday bozor tuzilmasi hisoblanadi?")])), "dup_question: boshqa savol — belgisiz")
ok(("quote_missing", "warn") in codes({**GOOD, "source_quote": "Narx oshsa talab ham oshadi."}, SRC) and ("quote_missing", "warn") in codes(GOOD, SRC),
   "quote_missing: matnda yo'q iqtibos / iqtibossiz — ogohlantirish")
ok(not any(c == "quote_missing" for c, _ in codes({**GOOD, "source_quote": "talab qonuniga ko‘ra narx oshsa — talab miqdori kamayadi"}, SRC)) and
   not any(c == "quote_missing" for c, _ in codes({**GOOD, "source_quote": "Talab qonuniga ko'ra … talab miqdori kamayadi."}, SRC)),
   "quote_missing: tinish belgisi/apostrof farqi va «…» bilan qisqartirilgan iqtibos — topiladi")
ok(not TB.blocking([{"sev": "warn"}]) and TB.blocking([{"sev": "warn"}, {"sev": "block"}]), "blocking(): faqat bloklovchi belgi to'xtatadi")
pt, pd = TB.plan_counts(10, ["mcq", "tf", "fill"], {"oson": 30, "orta": 50, "qiyin": 20})
ok(sum(pt.values()) == 10 and pt["mcq"] >= pt["tf"] and sum(pd.values()) == 10 and pd == {"oson": 3, "orta": 5, "qiyin": 2}, f"Taqsimot: turlar {pt}, qiyinlik {pd}")

# =============================================================================================
print("== 3. Mavzu matni (manba)")
TOPIC = 3
LONG = ("Innovatsion iqtisodiyot bilimlarga asoslangan iqtisodiyotdir. Unda raqobatbardoshlik asosan yangi texnologiyalar va g'oyalarni tez joriy etish bilan belgilanadi. "
        "Texnologik park — ilmiy tashkilotlar, universitetlar va kompaniyalarni bir hududda birlashtiruvchi infratuzilma. "
        "Startap — tez o'sishga yo'naltirilgan yangi tashkil etilgan kompaniya bo'lib, u odatda venchur investitsiyalar hisobiga moliyalashtiriladi. "
        "Intellektual mulk huquqlari ixtirochilarga o'z ishlanmalaridan foyda olish imkonini beradi va innovatsiyalarni rag'batlantiradi. <b>&]]> ~=#{}:")
r = teach.post(f"{P}/courses/{own['id']}/topics/{TOPIC}/source/text", json={"text": "Juda qisqa matn."})
ok(r.status_code == 400 and "qisqa" in r.json().get("detail", ""), "Qisqa matn rad etiladi (400)")
r = teach.post(f"{P}/courses/{own['id']}/topics/{TOPIC}/source/text", json={"text": LONG, "name": "3-mavzu.txt"})
ok(r.status_code == 200 and r.json()["chars"] == len(LONG), "Matn joylashtirildi va saqlandi")
from docx import Document
bio = io.BytesIO(); d = Document(); d.add_heading("4-mavzu. Innovatsion faoliyat", 1)
for _ in range(4): d.add_paragraph(LONG.split("<b>")[0])
d.save(bio)
r = teach.post(f"{P}/courses/{own['id']}/topics/4/source?name=4-mavzu.docx", content=bio.getvalue())
ok(r.status_code == 200 and r.json()["kind"] == "docx" and r.json()["chars"] > 500, f"Word (.docx) fayldan matn olindi ({r.json().get('chars')} belgi)")
r = teach.post(f"{P}/courses/{own['id']}/topics/5/source?name=x.exe", content=b"MZ\x00\x00" + b"\x00" * 500)
ok(r.status_code == 415, "Noma'lum fayl turi rad etiladi (415)")
ok(teach.post(f"{P}/courses/{mikro['id']}/topics/5/source/text", json={"text": LONG}).status_code == 403, "Begona kursga matn yuklab bo'lmaydi (403)")
sv = teach.get(f"{P}/courses/{own['id']}/topics/{TOPIC}/source").json()["source"]
ok(sv and sv["text"] == LONG and not sv["demo"], "Saqlangan matn qaytadi")

print("== 4. AI generatsiya: serverda kalit yo'q → aniq o'zbekcha xato (soxta generatsiya yo'q)")
n0 = q("SELECT COUNT(*) n FROM tb_questions")[0]["n"]
r = teach.post(f"{P}/courses/{own['id']}/generate", json={"topics": [TOPIC], "n": 5, "types": ["mcq"]})
ok(r.status_code == 503 and "AI ulanmagan" in r.json().get("detail", "") and "ANTHROPIC_API_KEY" in r.json()["detail"], "Kalitsiz: 503 «AI ulanmagan … ANTHROPIC_API_KEY»")
ok(q("SELECT COUNT(*) n FROM tb_questions")[0]["n"] == n0, "Kalitsiz hech qanday savol yaratilmaydi")
ok(kaf.post(f"{P}/courses/{own['id']}/generate", json={"topics": [TOPIC], "n": 5}).status_code == 403, "Kafedra mudiri generatsiya qilolmaydi (403)")
ok(teach.post(f"{P}/courses/{own['id']}/generate", json={"topics": [TOPIC], "n": 99}).status_code == 422, "Savollar soni chegarasi (≤ 30)")
src_tb = (ROOT / "app" / "testbank.py").read_text()
ok("FAKE" not in src_tb and "ISFT_CORE_TB_FAKE" not in src_tb, "testbank.py da soxta AI rejimi (muhit o'zgaruvchisi) yo'q")

print("== 5. AI generatsiya: soxta Claude (shu test jarayonida, bazaning vaqtinchalik nusxasida)")
tmp = Path(tempfile.mkdtemp(prefix="tbgen-")) / "copy.db"
srcc = sqlite3.connect(DBP); dst = sqlite3.connect(tmp, check_same_thread=False); srcc.backup(dst); srcc.close()
dst.row_factory = sqlite3.Row
from app import claude_client as CC, rbac as RB
TB.init(dst); TB.bind(dst, None)
calls = []
def fake_call_json(**kw):
    calls.append(kw)
    txt = kw["content"][0]["text"]
    items = [{"type": "mcq", "stem": "Startap qanday kompaniya hisoblanadi?", "options": ["Tez o'sishga yo'naltirilgan yangi kompaniya", "Davlat unitar korxonasi",
              "Faqat eksport bilan shug'ullanadigan firma", "Yirik xolding tarkibidagi bo'linma"], "correct_index": 0, "answers": [],
              "explanation": "Matnda shunday ta'rif berilgan.", "difficulty": "oson", "bloom": "eslash",
              "source_quote": "Startap — tez o'sishga yo'naltirilgan yangi tashkil etilgan kompaniya"},
             {"type": "tf", "stem": "Intellektual mulk huquqlari innovatsiyalarni rag'batlantiradi.", "options": [], "correct_index": 0, "answers": [],
              "explanation": "Matnda aytilgan.", "difficulty": "oson", "bloom": "tushunish", "source_quote": "innovatsiyalarni rag'batlantiradi"},
             {"type": "fill", "stem": "Startaplar odatda ____ investitsiyalar hisobiga moliyalashtiriladi.", "options": [], "correct_index": -1, "answers": ["venchur"],
              "explanation": "", "difficulty": "orta", "bloom": "eslash", "source_quote": "venchur investitsiyalar hisobiga moliyalashtiriladi"},
             {"type": "mcq", "stem": "Texnologik park nimani birlashtiradi?", "options": ["Universitetlar", "Universitetlar", "Banklar", "Bozorlar"], "correct_index": 7,
              "answers": [], "explanation": "", "difficulty": "qiyin", "bloom": "tahlil", "source_quote": "Bu jumla matnda yo'q"},
             {"type": "nonsense", "stem": "", "options": [], "correct_index": 0, "answers": [], "explanation": "", "difficulty": "oson", "bloom": "eslash", "source_quote": ""}]
    return {"questions": items}, {"in": 1234, "out": 567, "model": kw["model"]}
saved = (CC.call_json, CC.has_key)
try:
    CC.has_key = lambda: True
    CC.call_json = fake_call_json
    tctx = RB.ctx_for(dst, teach_uid)
    res = TB.generate(tctx, own["id"], [TOPIC], 5, ["mcq", "tf", "fill"], {"oson": 40, "orta": 40, "qiyin": 20})
    ok(res["created"] == 4 and res["results"][0]["dropped"] == 1, f"4 ta savol yaratildi, 1 ta yaroqsiz tashlandi ({res['created']})")
    kw = calls[0]
    ok(kw["model"] == "claude-opus-5-5" and kw["schema"] is TB.GEN_SCHEMA and kw["schema"]["properties"]["questions"]["items"]["additionalProperties"] is False,
       "Model claude-opus-5-5 (ISFT_CORE_TB_MODEL), qat'iy JSON sxema")
    body = kw["content"][0]["text"]
    ok("<manba>" in body and LONG[:60] in body and own["subject"] in body, "So'rovda faqat kurs, mavzu va mavzu matni")
    stud = [r["full_name"] for r in q("SELECT full_name FROM students LIMIT 50")]
    ok(not any(n and n in body for n in stud) and "hemis" not in body.lower(), "So'rovda talabalar ma'lumoti yo'q")
    ok("o'zbek" in kw["system"].lower() and "source_quote" in kw["system"] and "FAQAT manba" in kw["system"], "Tizim ko'rsatmasi: o'zbekcha, faqat manba, iqtibos")
    rows = [dict(r) for r in dst.execute("SELECT * FROM tb_questions WHERE gen_id IS NOT NULL ORDER BY id")]
    ok(len(rows) == 4 and all(r["status"] == "qoralama" and r["engine"] == "claude" and r["author_id"] == teach_uid for r in rows), "AI savollari — qoralama, muallif o'qituvchi")
    bad = rows[3]; fl = {f["code"] for f in json.loads(bad["flags"])}
    ok(bad["blocking"] == 1 and {"dup_option", "correct_range", "quote_missing"} <= fl, f"Yomon AI savoli QC'da bloklandi: {sorted(fl)}")
    ok(all(r["blocking"] == 0 for r in rows[:3]), "Yaxshi AI savollari bloklanmagan")
    tf = rows[1]
    ok(json.loads(tf["options"]) == TB.TF_OPTIONS and json.loads(tf["correct"]) == [0], "To'g'ri/noto'g'ri savol variantlari me'yorlandi")
    g = dict(dst.execute("SELECT * FROM tb_gen ORDER BY id DESC LIMIT 1").fetchone())
    ok(g["ok"] == 1 and g["in_tok"] == 1234 and g["out_tok"] == 567 and g["n_got"] == 4, "Token sarfi tb_gen jadvalida")
    def boom(**kw): raise CC.AIError("AI xizmati hozir band (so'rovlar cheklovi).")
    CC.call_json = boom
    try: TB.generate(tctx, own["id"], [TOPIC], 3, ["mcq"], {}); ok(False, "AI xatosi 502 bermadi")
    except TB.HTTPException as e: ok(e.status_code == 502 and "band" in str(e.detail), "AI xatosi — 502 va o'zbekcha matn")
    try: TB.generate(tctx, own["id"], [7], 3, ["mcq"], {}); ok(False, "matnsiz mavzu o'tdi")
    except TB.HTTPException as e: ok(e.status_code == 400 and "matni yuklanmagan" in e.detail, "Matni yo'q mavzu — 400")
    CC.has_key = lambda: False
    try: TB.generate(tctx, own["id"], [TOPIC], 3, ["mcq"], {}); ok(False, "kalitsiz o'tdi")
    except TB.HTTPException as e: ok(e.status_code == 503, "Kalitsiz — 503 (jarayon ichida ham)")
    CC.has_key = lambda: True
    try: TB.generate(tctx, mikro["id"], [1], 3, ["mcq"], {}); ok(False, "begona kurs o'tdi")
    except RB.AccessDenied: ok(True, "Begona kursga generatsiya — rad etildi")
finally:
    CC.call_json, CC.has_key = saved
    TB.bind(None, None); dst.close()

# =============================================================================================
print("== 6. Ko'rib chiqish oqimi")
def make(c, cid, no, **kw):
    body = {"qtype": "mcq", "stem": "Texnologik park qanday infratuzilma hisoblanadi?", "options": ["Ilmiy tashkilot va kompaniyalar majmuasi",
            "Faqat savdo markazlari majmuasi", "Davlat boshqaruv organlari tizimi", "Qishloq xo'jaligi korxonalari"], "correct": [0], "difficulty": "orta", "bloom": "tushunish",
            "explanation": "Matnga ko'ra.", "source_quote": "ilmiy tashkilotlar, universitetlar va kompaniyalarni bir hududda birlashtiruvchi infratuzilma"}
    body.update(kw)
    return c.post(f"{P}/courses/{cid}/topics/{no}/questions", json=body)
r = make(teach, own["id"], TOPIC)
qa = r.json()
ok(r.status_code == 200 and qa["status"] == "qoralama" and qa["flags"] == [] and qa["can"]["submit"], "O'qituvchi savol qo'shdi: qoralama, belgisiz")
ok(make(teach, mikro["id"], 1).status_code == 403, "O'qituvchi begona kursga savol qo'sholmaydi (403)")
ok(teach.post(f"{P}/questions/{qa['id']}/action", json={"action": "approve"}).status_code == 403, "O'qituvchi tasdiqlay olmaydi (403)")
ok(staff.post(f"{P}/questions/{qa['id']}/action", json={"action": "approve"}).status_code == 409, "Qoralama to'g'ridan-to'g'ri tasdiqlanmaydi (409)")
ok(teach.post(f"{P}/questions/{qa['id']}/action", json={"action": "submit"}).json()["status"] == "tekshiruvda", "Tekshiruvga yuborildi")
ok(staff.post(f"{P}/questions/{qa['id']}/action", json={"action": "reject"}).status_code == 400, "Rad etish sababsiz — 400")
ok(staff.post(f"{P}/questions/{qa['id']}/action", json={"action": "reject", "note": "Variantlar juda oson"}).json()["status"] == "rad_etildi", "Bo'lim xodimi rad etdi (sabab bilan)")
mw = teach.get("/api/mywork").json()
ok(any(i["source"] == "testbank" and "rad etilgan" in i["title"] for i in mw["items"]), "O'qituvchining «Mening vazifalarim»ida rad etilgan savollar")
r = teach.put(f"{P}/questions/{qa['id']}", json={**{k: qa[k] for k in ("qtype", "options", "correct", "answers", "explanation", "difficulty", "bloom", "source_quote")},
                                                 "stem": "Texnologik park qanday infratuzilma hisoblanadi va nimalarni birlashtiradi?",
                                                 "options": ["Ilmiy tashkilotlar va kompaniyalarni", "Faqat savdo markazlarini", "Davlat organlarini", "Fermer xo'jaliklarini"]})
ok(r.status_code == 200 and r.json()["status"] == "qoralama", "Tahrirlangan savol qoralamaga qaytdi")
teach.post(f"{P}/questions/{qa['id']}/action", json={"action": "submit"})
ok(head.get("/api/mywork").json() and any(i["source"] == "testbank" for i in head.get("/api/mywork").json()["items"]), "Bo'lim boshlig'ida «tekshiruvni kutayotgan savollar»")
ok(head.post(f"{P}/questions/{qa['id']}/action", json={"action": "approve"}).json()["status"] == "tasdiqlandi", "Bo'lim boshlig'i tasdiqladi")
ok(teach.put(f"{P}/questions/{qa['id']}", json={"qtype": "tf", "stem": "Tasdiqlangan savolni o'zgartirish urinishi.", "correct": [0]}).status_code == 409,
   "Tasdiqlangan savolni o'qituvchi tahrirlay olmaydi (409)")
ok(teach.post(f"{P}/questions/{qa['id']}/delete").status_code == 409, "Tasdiqlangan savolni o'qituvchi o'chira olmaydi (409)")
lg = teach.get(f"{P}/questions/{qa['id']}/log").json()["items"]
ok([x["action"] for x in lg] == ["yaratildi", "tekshiruvga yuborildi", "rad etildi", "tahrirlandi", "tekshiruvga yuborildi", "tasdiqlandi"], "Tarix: barcha bosqichlar yozilgan")
qb = make(teach, own["id"], TOPIC, stem="Startap qanday moliyalashtiriladi odatda?", options=["Venchur investitsiya", "Davlat byudjeti", "Kredit", "Grant"], correct=[0, 1]).json()
ok(qb["blocking"] and any(f["code"] == "correct_count" for f in qb["flags"]) and not qb["can"]["submit"], "Ikki to'g'ri javobli savol — bloklovchi belgi")
ok(teach.post(f"{P}/questions/{qb['id']}/action", json={"action": "submit"}).status_code == 409, "Bloklovchi belgili savol tekshiruvga yuborilmaydi (409)")
rb = teach.post(f"{P}/courses/{own['id']}/bulk", json={"action": "submit", "ids": [qb["id"]]}).json()
ok(rb["done"] == 0 and rb["skipped"] and rb["skipped"][0]["id"] == qb["id"], "Ommaviy yuborishda bloklangan savol o'tkazib yuborildi")
ok(teach.post(f"{P}/questions/{qb['id']}/delete").json()["ok"], "O'qituvchi o'z qoralamasini o'chirdi")
demo_rev = q("SELECT id FROM tb_questions WHERE course_id=? AND status='tekshiruvda' AND deleted=0", (mikro["id"],))
rb = staff.post(f"{P}/courses/{mikro['id']}/bulk", json={"action": "approve", "ids": [x["id"] for x in demo_rev]}).json()
qm = {x["id"] for x in q(f"SELECT id FROM tb_questions WHERE id IN ({','.join(str(x['id']) for x in demo_rev) or 0}) AND flags LIKE '%quote_missing%'")}
ok(rb["done"] == len(demo_rev) - len(qm) and len(demo_rev) > 0, f"Bo'lim xodimi tekshiruvdagilarni ommaviy tasdiqladi ({rb['done']}, iqtibossiz {len(qm)} ta — o'tkazildi)")
ok({x["id"] for x in rb["skipped"]} == qm, "Ommaviy tasdiqlashda iqtibosi manbada topilmagan savollar o'tkazib yuboriladi (alohida tekshiriladi)")
ok(teach.post(f"{P}/courses/{mikro['id']}/bulk", json={"action": "approve", "ids": [1]}).status_code == 403, "O'qituvchi ommaviy tasdiqlay olmaydi (403)")

# =============================================================================================
print("== 7. Oraliq taqsimoti va banklar")
n = mikro["topics"]; k0 = math.ceil(n / 2)
cv = head.get(f"{P}/courses/{mikro['id']}").json()
ok(cv["course"]["split"] == k0 == cv["course"]["split_default"], f"Standart: 1-oraliq = 1..{k0} (ceil({n}/2))")
ok(all(t["oraliq"] == (1 if t["no"] <= k0 else 2) for t in cv["topics"]), "Mavzular oraliqlarga to'g'ri ajratilgan")
appr = lambda lo, hi: q("SELECT COUNT(*) n FROM tb_questions WHERE course_id=? AND deleted=0 AND status='tasdiqlandi' AND topic_no BETWEEN ? AND ?", (mikro["id"], lo, hi))[0]["n"]
b1 = kaf8.get(f"{P}/courses/{mikro['id']}/bank?part=o1").json(); b2 = kaf8.get(f"{P}/courses/{mikro['id']}/bank?part=o2").json()
ok(len(b1["questions"]) == appr(1, k0) and len(b2["questions"]) == appr(k0 + 1, n) and len(b2["questions"]) > 0, f"1-oraliq banki {len(b1['questions'])} ta, 2-oraliq {len(b2['questions'])} ta (faqat tasdiqlangan)")
ok(all(x["status"] == "tasdiqlandi" for x in b1["questions"] + b2["questions"]), "Bankda faqat tasdiqlangan savollar")
ok(not any(x["topic_no"] == 3 for x in b1["questions"]), "Qoralama savollari (3-mavzu) bankka kirmagan")
bt = head.get(f"{P}/courses/{mikro['id']}/bank?part=t9").json()
ok(bt["questions"] and all(x["topic_no"] == 9 for x in bt["questions"]), "Mavzu testi (9-mavzu)")
ok(head.get(f"{P}/courses/{mikro['id']}/bank?part=x1").status_code == 400, "Noto'g'ri bank turi — 400")
ok(teach.post(f"{P}/courses/{mikro['id']}/split", json={"oraliq1_to": 9}).status_code == 403, "O'qituvchi begona kurs taqsimotini o'zgartirolmaydi (403)")
ok(head.post(f"{P}/courses/{mikro['id']}/split", json={"oraliq1_to": n}).status_code == 400, "1-oraliq barcha mavzularni qamrab ololmaydi (400)")
ok(head.post(f"{P}/courses/{mikro['id']}/split", json={"oraliq1_to": 9}).json()["split"] == 9, "Taqsimot o'zgartirildi: 1..9")
b1b = head.get(f"{P}/courses/{mikro['id']}/bank?part=o1").json()
ok(len(b1b["questions"]) == appr(1, 9) and any(x["topic_no"] == 9 for x in b1b["questions"]), "9-mavzu endi 1-oraliq bankida")
ok(teach.post(f"{P}/courses/{own['id']}/split", json={"oraliq1_to": 7}).json()["ok"], "O'qituvchi o'z kursi taqsimotini o'zgartiradi")
head.post(f"{P}/courses/{mikro['id']}/split", json={"oraliq1_to": k0})

print("== 8. Eksport")
xr = kaf8.get(f"{P}/courses/{mikro['id']}/export/xml?part=all")
ok(xr.status_code == 200 and "attachment" in xr.headers.get("content-disposition", "") and xr.headers["content-type"].startswith("application/xml"), "Moodle XML yuklab olinadi")
root = ET.fromstring(xr.content)
qq = [x for x in root.findall("question") if x.get("type") != "category"]
cats = [x.find("category/text").text for x in root.findall("question") if x.get("type") == "category"]
ok(root.tag == "quiz" and len(qq) == appr(1, n), f"XML to'g'ri (ElementTree), {len(qq)} ta savol = tasdiqlanganlar")
ok(all(c.startswith("$course$/top/Mikroiqtisodiyot (") and ("/1-oraliq/" in c or "/2-oraliq/" in c) for c in cats) and any("/2-oraliq/09-mavzu" in c for c in cats),
   "Kategoriyalar: fan / oraliq / mavzu")
types = {x.get("type") for x in qq}
ok(types == {"multichoice", "truefalse", "shortanswer"}, f"Savol turlari: {sorted(types)}")
mc = next(x for x in qq if x.get("type") == "multichoice")
ok(mc.find("single").text == "true" and sum(1 for a in mc.findall("answer") if a.get("fraction") == "100") == 1, "Bir javobli: aynan bitta 100% javob")
ok("<![CDATA[" in xr.text, "Matnlar CDATA ichida")
# maxsus belgilar: o'z kursida tasdiqlangan savol
qs = make(teach, own["id"], TOPIC, stem="Qaysi belgi <b> & \"]]>\" ~=#{}: bilan yozilgan savol matni to'g'ri eksport qilinadi?",
          options=["A < B & C", "]]> belgisi", "~ = # { } :", "Oddiy javob matni"], correct=[0], source_quote="").json()
teach.post(f"{P}/questions/{qs['id']}/action", json={"action": "submit"}); head.post(f"{P}/questions/{qs['id']}/action", json={"action": "approve"})
x2 = teach.get(f"{P}/courses/{own['id']}/export/xml?part=t{TOPIC}")
r2 = ET.fromstring(x2.content)
qx = next(x for x in r2.findall("question") if x.find("idnumber") is not None and x.find("idnumber").text == f"ISFT-TB-{qs['id']}")
ok(qx.find("questiontext/text").text == "Qaysi belgi &lt;b&gt; &amp; \"]]&gt;\" ~=#{}: bilan yozilgan savol matni to'g'ri eksport qilinadi?",
   "XML: <, &, ]]> to'g'ri qochirilgan (CDATA + HTML) va qayta o'qiladi")
ok([a.find("text").text for a in qx.findall("answer")][:2] == ["A &lt; B &amp; C", "]]&gt; belgisi"], "XML: variantlardagi maxsus belgilar")
gr = teach.get(f"{P}/courses/{own['id']}/export/gift?part=t{TOPIC}")
gt = gr.text
ok(gr.status_code == 200 and "$CATEGORY: $course$/top/" in gt and f"::TB{qs['id']}::" in gt, "GIFT: kategoriya va savol nomi")
ok("=A < B & C" in gt and "~\\~ \\= \\# \\{ \\} \\:" in gt and "\\~\\=\\#\\{\\}\\:" in gt, "GIFT: ~ = # { } : qochirilgan (savol va variantlarda)")
ok(TB.gift_escape("a~b=c#d{e}f:g\\h\nI") == "a\\~b\\=c\\#d\\{e\\}f\\:g\\\\h\\nI", "gift_escape(): barcha maxsus belgilar va qator ko'chishi")
gm = head.get(f"{P}/courses/{mikro['id']}/export/gift?part=all").text
blocks = [b for b in gm.split("\n\n") if b.strip().startswith("::TB")]
ok(len(blocks) == appr(1, n) and all(b.count("{") - b.count("\\{") == 1 for b in blocks), "GIFT: har bir savolda bitta javob bloki")
ar = head.get(f"{P}/courses/{mikro['id']}/export/aiken?part=all")
at = ar.text
n_mcq = q("SELECT COUNT(*) n FROM tb_questions WHERE course_id=? AND deleted=0 AND status='tasdiqlandi' AND qtype='mcq'", (mikro["id"],))[0]["n"]
ok(at.count("ANSWER: ") == n_mcq and int(ar.headers["x-skipped"]) == appr(1, n) - n_mcq, f"Aiken: faqat bir javobli ({n_mcq} ta), qolganlari o'tkazib yuborildi")
ok(all(re.fullmatch(r"ANSWER: [A-F]", ln) for ln in at.splitlines() if ln.startswith("ANSWER")) and "\n\n" in at, "Aiken: «ANSWER: X» formati")
dr = kaf8.get(f"{P}/courses/{mikro['id']}/export/docx?part=o1")
ok(dr.status_code == 200 and dr.content[:2] == b"PK", "Word (.docx) yuklab olinadi")
doc = Document(io.BytesIO(dr.content)); txt = "\n".join(p.text for p in doc.paragraphs)
ok("TEST BANKI" in txt and "JAVOBLAR KALITI" in txt and len(doc.tables[-1].rows) == len(b1["questions"]) + 1, "Word: savollar va javoblar kaliti jadvali")
ok(head.get(f"{P}/courses/{mikro['id']}/export/pdf").status_code == 404, "Noma'lum format — 404")

print("== 9. Qamrov")
cov = head.get(P + "/coverage").json()
t = cov["total"]
ok(t["approved"] == q("SELECT COUNT(*) n FROM tb_questions WHERE deleted=0 AND status='tasdiqlandi'")[0]["n"], "Tasdiqlanganlar soni SQL bilan mos")
ok(sum(d["approved"] for d in cov["departments"]) == t["approved"] and sum(d["topics"] for d in cov["departments"]) == t["topics"], "Kafedralar yig'indisi = jami")
ok(t["topics"] == q("SELECT SUM(topics) n FROM dl_courses")[0]["n"], "Jami mavzular — kontent rejasi bilan bir xil")
mrow = next(r for r in head.get(P + "/courses?q=Mikroiqtisodiyot").json()["items"] if r["id"] == mikro["id"])
ok(mrow["covered"] >= 1 and mrow["o1_covered"] >= 1 and mrow["started"], f"Mikroiqtisodiyot: {mrow['covered']} mavzu qamrab olingan (≥ {cov['min_q']} tasdiqlangan)")
rc = rek.get(P + "/coverage").json()
ok(rc["total"]["approved"] == t["approved"] and rc["ai"] is None, "Rektor: jamlangan raqamlar bir xil, AI sarfi ko'rinmaydi")
ok(kaf.get(P + "/coverage").json()["total"]["courses"] == kc["total"], "Kafedra qamrovi — faqat o'z kafedrasi")
ok(staff.post(P + "/settings", json={"min_q": 5}).status_code == 403 and head.post(P + "/settings", json={"min_q": 12}).json()["min_q"] == 12, "«Qamrab olingan» chegarasi — faqat bo'lim boshlig'i")
ok(head.get(P + "/coverage").json()["total"]["covered"] <= t["covered"], "Chegara oshsa qamrov kamayadi yoki o'zgarmaydi")
head.post(P + "/settings", json={"min_q": 10})

print("== 10. Sahifa fayllari")
idx = httpx.get(B + "/index.html").text; js = httpx.get(B + "/app.js").text
ok('data-v="testbank"' in idx and 'id="v-testbank"' in idx and 'src="testbank.js"' in idx, "index.html: menyu, bo'lim va skript ulangan")
ok('a[data-v="testbank"]' in js and httpx.get(B + "/testbank.js").status_code == 200 and httpx.get(B + "/testbank.css").status_code == 200, "app.js: menyu ko'rinishi; testbank.js/css mavjud")

print()
if fails:
    print(f"XATO: {len(fails)} ta"); [print("  -", f) for f in fails]; sys.exit(1)
print("Hammasi o'tdi")
