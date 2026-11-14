"""«Dars tayyorlash» — birlashgan bo'lim (app/dars.py, static/dars.js; paket.py + kurs.py bilan): menyu va taxallus (go("kurs")), ruxsatlar,
paket → muharrir o'tkazish aniqligi (reja, matn rasm/jadval bilan, slaydlar, video, test, ikki tomonlama bog'lanish), fan skeleti (15 mavzu → 15 L + 30 A),
kafedra shabloni (versiyalar) va «Shablonni qo'llash» (muallif bloklari saqlanadi, oldin farq), ommaviy yig'ish/eksport (fon ishi, zip ichida zip),
AI: hujjatdan dars — soxta claude_client bilan sifat to'siqlari (o'rinlar teng, «eng uzun javob» belgisi + chalg'ituvchilar qayta, bo'limlar qamrovi,
kirill → lotin, iqtibossiz/o'ylab topilgan paragraf rad etiladi), kalitsiz — 503; blok izohlari (tarmoq, hal qilish / qayta ochish, muallifni eslatish,
bildirishnoma) va tasdiq to'sig'i (sabab bilan aylanib o'tish — audit). Brauzer (PW va CHROME berilganda): tools/dars_check.js.

Ishga tushirish:  python tests/run_all.py --only dars
DIQQAT: bazani o'zgartiradi — PRODUCTION'da ishlatilmaydi.
"""
import io, json, os, re, shutil, sqlite3, subprocess, sys, time, zipfile
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
def S(u):
    c = httpx.Client(base_url=B, timeout=600)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
def uid(role, **w):
    sql, a = "SELECT id FROM users WHERE role=? AND active=1", [role]
    for k, v in w.items(): sql += f" AND {k}=?"; a.append(v)
    r = q(sql + " ORDER BY id LIMIT 1", a); assert r, f"{role} {w} yo'q"; return r[0]["id"]

from app import dars as D, kurs as K, paket as PK   # sof funksiyalar — baza talab qilmaydi

# =============================================================================================
print("== 1. Sof funksiyalar: transliteratsiya, inglizcha qoldiq, o'rinlar, eng uzun javob")
for cyr, lat in (("Ўзбекистон Республикаси", "O'zbekiston Respublikasi"), ("Ғалаба", "G'alaba"), ("Шаҳар", "Shahar"), ("ЮНЕСКО", "YUNESKO"),
                 ("Ер ва юлдузлар", "Yer va yulduzlar"), ("иқтисодиёт", "iqtisodiyot"), ("Тошкент шаҳри, 2024 йил", "Toshkent shahri, 2024 yil"),
                 ("маълумот", "ma'lumot"), ("Чорва", "Chorva"), ("цех", "tsex"), ("Lotin matn o'zgarmaydi", "Lotin matn o'zgarmaydi")):
    ok(D.translit(cyr) == lat, f"Kirill → lotin: «{cyr}» → «{D.translit(cyr)}»")
ok(not D.has_cyrillic(D.translit("Бозор иқтисодиёти ва рақобат")), "Transliteratsiyadan keyin kirill harfi qolmaydi")
ok(D.is_english("The market is a place where buyers and sellers meet") and not D.is_english("Bozor — xaridor va sotuvchi uchrashadigan joy"), "Inglizcha qoldiq aniqlanadi, o'zbekcha matn — yo'q")
qs = [{"question": f"Savol {i}", "answers": [{"text": f"variant {j}", "correct": j == 1} for j in range(4)]} for i in range(12)]
D.balance(qs, "seed")
pos = D.positions(qs)
ok(sorted(pos) == ["A", "B", "C", "D"] and max(pos.values()) - min(pos.values()) <= 1, f"To'g'ri javob o'rinlari teng taqsimlandi: {pos}")
ok(json.dumps(D.balance(json.loads(json.dumps(qs)), "seed")) == json.dumps(D.balance(json.loads(json.dumps(qs)), "seed")), "Aralashtirish deterministik (bir xil seed → bir xil tartib)")
ok(D.correct_longest({"answers": [{"text": "qisqa", "correct": False}, {"text": "juda uzun to'g'ri javob matni", "correct": True}, {"text": "o'rta javob", "correct": False}]})
   and not D.correct_longest({"answers": [{"text": "bir xil uzun", "correct": True}, {"text": "bir xil uzun!", "correct": False}]}), "«To'g'ri javob eng uzun» aniqlanadi (teng — yo'q)")
src = "Bozor iqtisodiyoti 1991 yildan boshlab joriy etildi. Raqobat narxlarni pasaytiradi va sifatni oshiradi."
ok(D.cited("Bozor iqtisodiyoti 1991 yilda boshlangan.", "Bozor iqtisodiyoti 1991 yildan boshlab joriy etildi", src), "Iqtibos manbada bor, raqam manbada — qabul")
ok(not D.cited("Bozor iqtisodiyoti 1995 yilda boshlangan.", "Bozor iqtisodiyoti 1991 yildan boshlab joriy etildi", src), "O'ylab topilgan raqam (1995) — rad")
ok(not D.cited("Monopoliya foydali.", "Monopoliya iste'molchilar uchun foydali hisoblanadi", src), "Manbada yo'q iqtibos — rad")

# =============================================================================================
print("== 2. Shablonni qayta qo'llash (sof): muallif bloklari va mazmun saqlanadi")
old_items = D.clean_layout(D.DEFAULT_LAYOUT)["maruza"]
blocks = [{"id": b["id"], "type": b["type"], "data": K.clean_block(b["type"], b["data"], K._Assets(None))} for b in D.assemble(old_items, None, "1-MAVZU: SINOV", fill_empty=True)]
text_i = next(i for i, b in enumerate(blocks) if D.tpl_key(b["id"]) == "text")
blocks[text_i]["data"] = {"html": "<p>Muallif yozgan ma'ruza matni</p>"}
refs_i = next(i for i, b in enumerate(blocks) if D.tpl_key(b["id"]) == "refs")
author = {"id": "bauthor001", "type": "paragraph", "data": {"html": "<p>Muallif qo'shgan blok</p>"}}
blocks.insert(text_i + 1, author)
kp_i = next(i for i, b in enumerate(blocks) if D.tpl_key(b["id"]) == "keypoints")
blocks[kp_i]["data"] = K.clean_block("list", {"style": "bulleted", "items": ["To'ldirilgan xulosa"]}, K._Assets(None))
new_items = [dict(x) for x in old_items if x["key"] not in ("refs", "keypoints")]
for x in new_items:
    if x["key"] == "sectext": x["text"] = "MA'RUZA MATNI VA RASMLAR"
new_items.insert(3, {"key": "cont", "kind": "continue"})
plan = next(x for x in new_items if x["key"] == "plan"); new_items.remove(plan); new_items.insert(new_items.index(next(x for x in new_items if x["key"] == "text")) + 1, plan)
new_items = D.clean_layout({"maruza": new_items, "amaliy": D.DEFAULT_LAYOUT["amaliy"]})["maruza"]
nb, diff = D.reapply(blocks, old_items, new_items, "1-MAVZU: SINOV")
ids = [b["id"] for b in nb]
ok(author["id"] in ids and nb[ids.index(author["id"])]["data"] == author["data"], "Muallif bloki saqlandi (uid va mazmun o'zgarmagan)")
ok(ids.index(author["id"]) == ids.index(blocks[text_i]["id"]) + 1, "Muallif bloki o'z langari (matn bloki) ortidan ko'chdi")
ok(next(b for b in nb if D.tpl_key(b["id"]) == "text")["data"]["html"] == "<p>Muallif yozgan ma'ruza matni</p>", "Shablon blokidagi muallif mazmuni saqlandi")
ok(not any(D.tpl_key(b["id"]) == "refs" for b in nb) and diff["removed"] >= 1, "Olib tashlangan bo'sh band (adabiyotlar) o'chdi")
ok(any(b["type"] == "list" and b["data"]["items"] == ["To'ldirilgan xulosa"] and D.tpl_key(b["id"]) is None for b in nb) and diff["detached"] == 1,
   "Olib tashlangan, lekin to'ldirilgan band (xulosalar) — muallif blokiga aylandi (yo'qolmadi)")
ok(any(D.tpl_key(b["id"]) == "cont" and b["type"] == "continue" for b in nb) and diff["added"] == 1, "Yangi band («Davom etish») qo'shildi")
ok(any(b["type"] == "heading" and b["data"]["text"] == "MA'RUZA MATNI VA RASMLAR" for b in nb) and diff["updated"] == 1, "Statik band (bo'lim sarlavhasi) matni shablondan yangilandi")
ok(diff["moved"] >= 1 and diff["author"] == 1 and diff["changed"], f"Farq: {json.dumps({k: diff[k] for k in ('added', 'removed', 'updated', 'moved', 'author', 'detached')})}")
nb2, d2 = D.reapply(nb, new_items, new_items, "1-MAVZU: SINOV")
ok(not d2["changed"] and [b["id"] for b in nb2] == ids, "Bir xil shablonni qayta qo'llash — o'zgarishsiz (idempotent)")
try: D.clean_layout({"maruza": [{"kind": "noma'lum"}]}); ok(False, "Noma'lum band turi — 400")
except Exception as e: ok(getattr(e, "status_code", 0) == 400, "Noma'lum band turi — 400")

# =============================================================================================
print("== 3. AI: hujjatdan dars — soxta claude_client bilan sifat to'siqlari")
SECS = [{"sid": "S1", "title": "Bozor tushunchasi", "text": "Bozor — xaridor va sotuvchi o'rtasidagi ayirboshlash munosabatlari tizimi. Bozorda narx talab va taklif asosida shakllanadi."},
        {"sid": "S2", "title": "Raqobat", "text": "Raqobat ishlab chiqaruvchilarni sifatni oshirishga undaydi. Mukammal raqobatda firmalar soni ko'p bo'ladi."},
        {"sid": "S3", "title": "Monopoliya", "text": "Monopoliya — bozorda bitta sotuvchining hukmronligi. Monopolist narxni o'zi belgilashi mumkin."}]
def Q(sid, q, opts, ci, quote): return {"sid": sid, "question": q, "options": opts, "correct_index": ci, "explanation": "Izoh", "quote": quote}
LONG = ["Narx talab va taklif asosida bozorda shakllanadi", "Davlat", "Bank", "Soliq"]
main = {"title": "Бозор иқтисодиёти асослари", "sections": [
    {"sid": "S1", "paragraphs": [{"text": "Бозор — харидор ва сотувчи ўртасидаги айирбошлаш тизими.", "quote": "Bozor — xaridor va sotuvchi o'rtasidagi ayirboshlash munosabatlari tizimi"},
                                 {"text": "Bozorda narx 1995 yilda davlat tomonidan belgilangan.", "quote": "Bozorda narx talab va taklif asosida shakllanadi"},
                                 {"text": "Bozor juda qadimiy instituti hisoblanadi.", "quote": "Bozor eng qadimgi iqtisodiy institutdir va ming yillar davomida rivojlangan"},
                                 {"text": "The market is where buyers and sellers meet and the price is set.", "quote": "Bozorda narx talab va taklif asosida shakllanadi"}],
     "interactive": {"kind": "tabs", "items": [{"title": "Talab", "text": "Narx talab asosida shakllanadi.", "quote": "Bozorda narx talab va taklif asosida shakllanadi"},
                                               {"title": "Taklif", "text": "Narx taklif asosida ham shakllanadi.", "quote": "Bozorda narx talab va taklif asosida shakllanadi"}]},
     "checks": [Q("S1", "Bozorda narx qanday shakllanadi?", LONG, 0, "Bozorda narx talab va taklif asosida shakllanadi")]},
    {"sid": "S2", "paragraphs": [{"text": "Raqobat ishlab chiqaruvchilarni sifatni oshirishga undaydi.", "quote": "Raqobat ishlab chiqaruvchilarni sifatni oshirishga undaydi"}],
     "interactive": {"kind": "none", "items": []}, "checks": []},
    {"sid": "S3", "paragraphs": [{"text": "Monopoliyada bitta sotuvchi hukmron bo'ladi.", "quote": "Monopoliya — bozorda bitta sotuvchining hukmronligi"}],
     "interactive": {"kind": "none", "items": []}, "checks": []}],
  "flashcards": [{"term": "Монополия", "definition": "Bozorda bitta sotuvchining hukmronligi", "quote": "Monopoliya — bozorda bitta sotuvchining hukmronligi"},
                 {"term": "Raqobat", "definition": "Sifatni oshirishga undovchi kurash", "quote": "Raqobat ishlab chiqaruvchilarni sifatni oshirishga undaydi"},
                 {"term": "Oligopoliya", "definition": "Bir nechta yirik firma hukmronligi", "quote": "Oligopoliyada bir nechta yirik firma hukmron"}],
  "quiz": [Q("S2", "Raqobat ishlab chiqaruvchilarni nimaga undaydi?", ["Sifatni oshirishga undaydi va mahsulotni yaxshilaydi", "Narxni oshirish", "Ishni to'xtatish", "Soliqni kamaytirish"], 0,
             "Raqobat ishlab chiqaruvchilarni sifatni oshirishga undaydi"),
           Q("S2", "Mukammal raqobatda firmalar soni qanday?", ["Ko'p", "Bitta", "Ikkita", "Yo'q"], 0, "Mukammal raqobatda firmalar soni ko'p bo'ladi"),
           Q("S1", "Invented question?", ["A", "B", "C", "D"], 1, "Bu jumla manbada umuman yo'q va o'ylab topilgan"),
           Q("S1", "Bozor nima?", ["Ayirboshlash tizimi", "Faqat do'kon", "Faqat bank", "Faqat davlat"], 0, "Bozor — xaridor va sotuvchi o'rtasidagi ayirboshlash munosabatlari tizimi")]}
calls = []
def fake(**kw):
    calls.append(kw)
    n = len(calls)
    assert all(s["title"] in kw["content"][0]["text"] or n > 1 for s in SECS)
    if n == 1: return main, {"in": 1200, "out": 900, "model": "claude-test"}
    if kw["schema"] is D.COVER_SCHEMA:
        return {"questions": [Q("S3", "Monopoliyada kim narxni belgilaydi?", ["Monopolist", "Xaridor", "Davlat banki", "Hech kim"], 0, "Monopolist narxni o'zi belgilashi mumkin")]}, {"in": 300, "out": 120, "model": "claude-test"}
    if kw["schema"] is D.DISTRACT_SCHEMA:
        txt = kw["content"][0]["text"]
        items = [{"id": m, "distractors": ["Narx davlat qarori bilan bozorda belgilanadi", "Narx bank foizi asosida bozorda shakllanadi", "Narx soliq stavkasi va bojlar asosida bozorda o'rnatiladi"]}
                 for m in re.findall(r"^(Q\d+)\. Savol: Bozorda narx", txt, re.M)]
        return {"items": items}, {"in": 200, "out": 80, "model": "claude-test"}
    raise AssertionError("kutilmagan chaqiruv")
res = D.build_lesson({"course": "Mikroiqtisodiyot", "topic": "Bozor", "model": "claude-test"}, SECS, fake, seed="t")
R = res["report"]
ok(len(calls) == 3 and calls[0]["schema"] is D.AI_SCHEMA and calls[1]["schema"] is D.COVER_SCHEMA and calls[2]["schema"] is D.DISTRACT_SCHEMA,
   f"Chaqiruvlar: asosiy → qamrov (S3 savolsiz edi) → chalg'ituvchilar (bir marta) — {len(calls)} ta")
sent = calls[0]["content"][0]["text"]
ok("Mikroiqtisodiyot" in sent and "Bozor" in sent and all(s["text"] in sent for s in SECS) and "@" not in sent and "talaba" not in sent.lower(),
   "Claude'ga faqat fan/mavzu nomi va ma'ruza matni yuborildi")
ok(res["usage"]["in"] == 1700 and res["usage"]["out"] == 1100 and R["calls"] == 3, f"Tokenlar yig'indisi: {res['usage']['in']} / {res['usage']['out']}")
P1 = [p["text"] for p in res["sections"]["S1"]["paras"]]
ok(P1 and P1[0] == "Bozor — xaridor va sotuvchi o'rtasidagi ayirboshlash tizimi." and not any(D.has_cyrillic(x) for x in P1) and R["cyrillic"] >= 2,
   f"Kirill paragraf lotinga o'girildi: «{P1[0] if P1 else ''}»")
ok(not any("1995" in x for x in P1) and not any("qadimiy" in x for x in P1) and R["p_uncited"] == 2, "Iqtibossiz / o'ylab topilgan raqamli paragraflar rad etildi (2 ta)")
ok(not any("market" in x for x in P1) and R["english"] >= 1, "Inglizcha paragraf tashlandi")
ok(res["title"] == "Bozor iqtisodiyoti asoslari" and res["flashcards"][0]["front"] == "Monopoliya" and len(res["flashcards"]) == 2, "Sarlavha va kartochka atamalari lotinda; manbasiz kartochka tashlandi")
ok(res["sections"]["S1"]["interactive"] and res["sections"]["S1"]["interactive"]["kind"] == "tabs", "Interaktiv blok (yorliqlar) — manbaga tayangan")
allq = [x for o in res["sections"].values() for x in o["checks"]] + res["quiz"]
cov = {x["sid"] for x in allq}
ok(cov == {"S1", "S2", "S3"} and R["coverage_retry"], f"Har bo'lim kamida bitta savol bilan qamralgan: {sorted(cov)}")
ok(not any(x["question"] == "Invented question?" for x in allq) and R["q_uncited"] >= 1, "Manbasiz savol tashlandi")
ok(R["longest_flagged"] == 3 and R["distractors_regenerated"] == 1, f"«To'g'ri javob eng uzun»: {R['longest_flagged']} ta belgilandi, chalg'ituvchilar bir marta qayta tuzildi ({R['distractors_regenerated']})")
fixed = next(x for x in allq if x["question"].startswith("Bozorda narx"))
ok(not fixed.get("flag_longest") and not D.correct_longest(fixed) and len(fixed["answers"]) == 4, "Qayta tuzilgan savolda to'g'ri javob endi eng uzun emas")
still = sorted(x["question"] for x in allq if x.get("flag_longest"))
ok(still == ["Bozor nima?", "Raqobat ishlab chiqaruvchilarni nimaga undaydi?"] and R["longest_after"] == 2, f"AI tuzatmagan savollar belgili qoldi (o'qituvchi ko'radi): {still}")
pos = D.positions(allq)
ok(max(pos.values()) - min(pos.values()) <= 1 and len(pos) >= 3, f"O'rinlar teng: {pos}")
calls.clear()
def fake2(**kw):
    calls.append(kw)
    if len(calls) == 1: return {**main, "quiz": []}, {"in": 10, "out": 10}
    return {"questions": []}, {"in": 5, "out": 5}
try:
    D.build_lesson({"topic": "x"}, SECS, fake2); ok(False, "Qamrov yetmasa — saqlanmaydi")
except D.GuardError as e:
    ok("S2" in str(e) and "S3" in str(e) and len(calls) == 2, f"Qamrov yetmadi (qayta so'rovdan keyin ham) — xato, saqlanmaydi: {str(e)[:80]}")

# =============================================================================================
print("== 4. Menyu: bitta «Dars tayyorlash» bandi, «Kurs muharriri» — taxallus")
idx = (ROOT / "static" / "index.html").read_text()
ok('data-v="paket"' in idx and 'data-v="kurs"' not in idx and 'id="v-kurs"' in idx and '<script src="dars.js"></script>' in idx,
   "index.html: menyuda bitta «Dars tayyorlash», muharrir ko'rinishi (v-kurs) va dars.js bor")
appjs = (ROOT / "static" / "app.js").read_text()
ok('MOD_ALIAS = {kurs: "paket"}' in appjs and "MOD_ALIAS[v] || v" in appjs, "app.js: go(\"kurs\") — menyuda «Dars tayyorlash» belgilanadi")
from app import modules as M
ok("kurs" not in M.BY_KEY and M.ALIASES.get("kurs") == "paket", "Bo'limlar kaliti: «kurs» alohida emas — «paket»ga ergashadi")
os.environ["ISFT_CORE_MODULES"] = "-paket"; ok(not M.on("kurs") and not M.on("paket"), "«Dars tayyorlash» o'chirilsa — muharrir ham o'chiq"); os.environ.pop("ISFT_CORE_MODULES")

head_u, staff_u, teach_u = uid("masofaviy"), uid("masofaviy_xodim"), uid("oqituvchi")
head, staff, teach = S(head_u), S(staff_u), S(teach_u)
rek, bux = S(uid("rektor")), S(uid("buxgalteriya"))
tid = q("SELECT teacher_id FROM users WHERE id=?", (teach_u,))[0]["teacher_id"]
own = q("SELECT id, department_id, topics FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 1", (tid,))[0]
other = q("SELECT id, department_id FROM dl_courses WHERE teacher_id<>? AND department_id<>? ORDER BY id LIMIT 1", (tid, own["department_id"]))[0]
demo = q("SELECT DISTINCT course_id id FROM pk_assets WHERE src='demo' AND deleted=0 ORDER BY course_id LIMIT 1")[0]["id"]
kaf_own = S(uid("kafedra", department_id=own["department_id"]))
m = head.get("/api/paket/meta").json()
ok(m["tabs"][0] == "fanlar" and m["tab_labels"]["fanlar"] == "Fanlar", "Paket meta: kirish yorlig'i — «Fanlar»")
ok(teach.get("/api/paket/meta").json()["tabs"] == ["fanlar", "mavzular"], "O'qituvchi: «Fanlar» va «Darslarim»")

print("== 5. Ruxsatlar")
ok(head.get(f"/api/dars/subjects/{demo}").status_code == 200 and staff.get(f"/api/dars/subjects/{demo}").status_code == 200, "Bo'lim: istalgan fan to'ri (200)")
ok(teach.get(f"/api/dars/subjects/{own['id']}").status_code == 200 and teach.get(f"/api/dars/subjects/{other['id']}").status_code == 403, "O'qituvchi: o'z fani 200, begona — 403")
ok(kaf_own.get(f"/api/dars/subjects/{own['id']}").status_code == 200 and kaf_own.get(f"/api/dars/subjects/{other['id']}").status_code == 403, "Kafedra: o'z kafedrasi fani 200, boshqasi 403")
ok(kaf_own.post(f"/api/dars/subjects/{own['id']}/lessons/1/convert").status_code == 403 and kaf_own.post(f"/api/dars/subjects/{own['id']}/skeleton", json={"apply": True}).status_code == 403,
   "Kafedra: muharrirga o'tkazish va skelet — 403 (faqat ko'radi va izoh qoldiradi)")
ok(rek.get(f"/api/dars/subjects/{demo}").status_code == 403 and bux.get("/api/dars/meta").status_code == 403, "Rektor (fan to'ri) va buxgalteriya — 403")
ok(teach.post("/api/dars/templates", json={"layout": D.DEFAULT_LAYOUT}).status_code == 403 and kaf_own.post("/api/dars/templates", json={"layout": D.DEFAULT_LAYOUT}).status_code == 403,
   "Kafedra shablonini o'qituvchi va kafedra mudiri tahrirlay olmaydi (403)")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE resource='paket' AND action LIKE 'dars:%' AND allowed=0")[0]["n"] >= 4, "Rad etilgan so'rovlar audit jurnalida")

# =============================================================================================
print("== 6. Paket → muharrir: o'tkazish aniqligi va ikki tomonlama bog'lanish")
# demo dars (1): matn + .pptx taqdimot + video havola + Test bank savollari
tv = head.get(f"/api/paket/courses/{demo}/topics/1").json()
cv = head.post(f"/api/dars/subjects/{demo}/lessons/1/convert").json()
kc = cv["ku_course_id"]
co = head.get(f"/api/kurs/courses/{kc}").json()
L = {l["type"]: l for l in co["lessons_list"]}
bl = head.get(f"/api/kurs/lessons/{L['blocks']['id']}").json()["blocks"]
keys = [D.tpl_key(b["id"]) for b in bl]
ok(cv["created"] and all(keys) and co["dars"]["linked"] and co["dars"]["code"] == "L1" and co["dars"]["authority"] == "kurs",
   f"Muharrir kursi yaratildi (#{kc}): {len(bl)} ta shablon bloki, bog'lanish L1, eksport manbai — muharrir")
plan_b = next(b for b in bl if keys[bl.index(b)] == "plan" and b["type"] == "list")
ok(plan_b["data"]["items"] and len(plan_b["data"]["items"]) == len(tv["plan"]), f"Reja: {len(tv['plan'])} band")
vid = next((b for b in bl if b["type"] == "video"), None)
ok(vid and vid["data"]["yt_id"] == tv["ready"]["video"]["video_id"], f"Video: YouTube {tv['ready']['video']['video_id']}")
sl = next((b for b in bl if keys[bl.index(b)] == "slides" and b["type"] in ("gallery", "accordion")), None)
ok(sl and len(sl["data"]["items"]) == tv["ready"]["slides"]["n"], f"Taqdimot: {tv['ready']['slides']['n']} slayd ({sl and sl['type']})")
ok(any(b["type"] == "paragraph" and keys[bl.index(b)] == "text" for b in bl), "Ma'ruza matni — matn bloklari")
qn = head.get(f"/api/kurs/lessons/{L['quiz']['id']}").json()["blocks"] if "quiz" in L else []
ok(len(qn) == tv["ready"]["quiz"]["used"] and all(b["type"] == "question" for b in qn), f"Yakuniy test: {len(qn)} savol (paketdagi bilan bir xil)")
order = [k for k in dict.fromkeys(keys)]
want = [x["key"] for x in D.clean_layout(D.DEFAULT_LAYOUT)["maruza"] if x["key"] in order]
ok(order == want, "Bloklar kafedra shabloni tartibida")
tv2 = head.get(f"/api/paket/courses/{demo}/topics/1").json()
ok(tv2["kurs_link"] and tv2["kurs_link"]["id"] == kc and tv2["kurs_link"]["authority"] == "kurs", "Paket dars panelida — muharrir nusxasi havolasi (ikki tomonlama)")
cv2 = head.post(f"/api/dars/subjects/{demo}/lessons/1/convert").json()
ok(not cv2["created"] and cv2["ku_course_id"] == kc, "Qayta bosish — o'sha kurs ochiladi (dublikat yo'q)")
ok(teach.post(f"/api/dars/subjects/{demo}/lessons/2/convert").status_code == 403, "O'qituvchi begona fan darsini o'tkaza olmaydi (403)")
# Word (rasm + jadval) → o'qituvchining o'z darsi
def png(color=(139, 0, 51), size=(320, 200)):
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "PNG"); return b.getvalue()
def rich_docx():
    import docx
    from docx.shared import Inches
    d = docx.Document()
    d.add_heading("3-MAVZU: AXBOROT TEXNOLOGIYALARI", 1)
    d.add_paragraph("Reja:")
    for x in ("Kompyuter turlari", "O'lchov birliklari"): d.add_paragraph(x, style="List Number")
    d.add_heading("1. Kompyuter turlari", 2)
    d.add_paragraph("Kompyuterlar o'lchami va vazifasiga ko'ra bir necha turga bo'linadi. Eng kichigi — cho'ntak kompyuteri. " * 3)
    d.add_picture(io.BytesIO(png()), width=Inches(3)); d.add_paragraph("1.1-rasm. Mini cho'ntak kompyuteri")
    d.add_heading("2. O'lchov birliklari", 2)
    d.add_paragraph("Axborot o'lchov birliklari jadvalda keltirilgan. Bayt — sakkiz bitdan iborat asosiy o'lchov birligi.")
    t = d.add_table(rows=3, cols=2)
    for i, (a_, b_) in enumerate((("Birlik", "Qiymati"), ("1 bayt", "8 bit"), ("1 KB", "1024 bayt"))): t.cell(i, 0).text, t.cell(i, 1).text = a_, b_
    bio = io.BytesIO(); d.save(bio); return bio.getvalue()
RICH = rich_docx()
r = teach.post(f"/api/paket/courses/{own['id']}/topics/3/upload?name=maruza3.docx", content=RICH)
ok(r.status_code == 200, f"O'qituvchi Word yukladi (3-dars): {r.status_code}")
cvt = teach.post(f"/api/dars/subjects/{own['id']}/lessons/3/convert").json()
kct = cvt["ku_course_id"]
cot = teach.get(f"/api/kurs/courses/{kct}").json()
blt = teach.get(f"/api/kurs/lessons/{cot['lessons_list'][0]['id']}").json()["blocks"]
imgs = [b for b in blt if b["type"] == "image" and D.tpl_key(b["id"]) == "text"]
tbls = [b for b in blt if b["type"] == "table"]
ok(len(imgs) == 1 and imgs[0]["data"]["asset"] and imgs[0]["data"]["caption"].startswith("1.1-rasm") and imgs[0]["data"]["alt"], "Word rasmi → rasm bloki (fayl ko'chirildi, izoh va alt bilan)")
ok(len(tbls) == 1 and tbls[0]["data"]["rows"][1] == ["1 bayt", "8 bit"] and cvt["counts"]["tables"] == 1 and cvt["counts"]["figures"] == 1, "Word jadvali → jadval bloki (qatorlar aynan)")
ok(any(b["type"] == "heading" and "Kompyuter turlari" in b["data"]["text"] for b in blt), "Matndagi bo'lim sarlavhalari — sarlavha bloklari")
ok(teach.get(f"/api/kurs/assets/{imgs[0]['data']['asset']}").status_code == 200, "Ko'chirilgan rasm muharrirda ochiladi")

# =============================================================================================
print("== 7. Fan skeleti: 15 mavzu → 15 L + 30 A, kafedra shabloni bo'yicha bloklar")
sk = q("""SELECT c.id, c.department_id FROM dl_courses c WHERE c.topics=15 AND c.id NOT IN (SELECT course_id FROM pk_lessons) AND c.id NOT IN (?, ?, ?)
          AND c.department_id IN (SELECT department_id FROM users WHERE role='kafedra') ORDER BY c.id LIMIT 1""", (demo, own["id"], other["id"]))[0]
SK = sk["id"]
pv = head.post(f"/api/dars/subjects/{SK}/skeleton", json={"ratio": 2, "apply": False}).json()
ok(pv["L"] == 15 and pv["A"] == 30 and len(pv["plan"]) == 45 and pv["new_lessons"] == 30 and not pv["applied"], "Ko'rish: 15 L + 30 A, 30 ta yangi dars, hali saqlanmadi")
ok(q("SELECT COUNT(*) n FROM pk_lessons WHERE course_id=?", (SK,))[0]["n"] == 0, "Ko'rishda baza o'zgarmadi")
ap = head.post(f"/api/dars/subjects/{SK}/skeleton", json={"ratio": 2, "apply": True}).json()
sv = head.get(f"/api/dars/subjects/{SK}").json()
codes = [l["code"] for l in sv["lessons"]]
ok(ap["created"] == 45 and sv["counts"]["L"] == 15 and sv["counts"]["A"] == 30 and sv["counts"]["linked"] == 45, f"Saqlandi: {sv['counts']['L']} L + {sv['counts']['A']} A, muharrirda {sv['counts']['linked']} ta dars")
ok(codes[:3] == ["L1", "L2", "L3"] and codes[15:18] == ["A1", "A2", "A3"] and codes[-1] == "A30", "NEXTID kodlari: L1..L15, A1..A30")
a1, a2 = (next(l for l in sv["lessons"] if l["code"] == c_) for c_ in ("A1", "A2"))
l1 = next(l for l in sv["lessons"] if l["code"] == "L1")
ok(a1["topic"] == 1 and a2["topic"] == 1 and next(l for l in sv["lessons"] if l["code"] == "A3")["topic"] == 2 and a1["title"].startswith(l1["title"]) and "(1-qism)" in a1["title"],
   f"Amaliy mashg'ulotlar mavzuga bog'langan (A1, A2 → 1-mavzu; A3 → 2-mavzu): «{a1['title']}»")
kl1 = l1["kurs"]["id"]
b1 = head.get(f"/api/kurs/lessons/{head.get(f'/api/kurs/courses/{kl1}').json()['lessons_list'][0]['id']}").json()["blocks"]
ok([D.tpl_key(b["id"]) for b in b1][:3] == ["cover", "secvideo", "video"] and any(b["type"] == "video" for b in b1), "Skelet darsi — shablon bloklari (muqova, VIDEODARS, video …)")
ka1 = a1["kurs"]["id"]
ba1 = head.get(f"/api/kurs/lessons/{head.get(f'/api/kurs/courses/{ka1}').json()['lessons_list'][0]['id']}").json()["blocks"]
ok(any(b["type"] == "heading" and b["data"]["text"] == "AMALIY MASHG'ULOT" for b in ba1) and not any(D.tpl_key(b["id"]) == "keypoints" for b in ba1), "Amaliy dars — amaliy shablon bo'yicha")
ap2 = head.post(f"/api/dars/subjects/{SK}/skeleton", json={"ratio": 2, "apply": True}).json()
ok(ap2["created"] == 0 and q("SELECT COUNT(*) n FROM pk_lessons WHERE course_id=? AND deleted=0", (SK,))[0]["n"] == 30, "Qayta bosish — dublikat yo'q (idempotent)")

# =============================================================================================
print("== 8. Kafedra shabloni (versiya) va «Shablonni qo'llash»: muallif bloklari saqlanadi")
lid1 = head.get(f"/api/kurs/courses/{kl1}").json()["lessons_list"][0]["id"]
L1 = head.get(f"/api/kurs/lessons/{lid1}").json()
bl1 = [{"id": b["id"], "type": b["type"], "data": b["data"]} for b in L1["blocks"]]
vi = next(i for i, b in enumerate(bl1) if b["type"] == "video")
bl1[vi]["data"] = {**bl1[vi]["data"], "source": "youtube", "youtube": "https://youtu.be/dQw4w9WgXcQ"}
ti = next(i for i, b in enumerate(bl1) if D.tpl_key(b["id"]) == "text")
bl1[ti]["data"] = {"html": "<p>Muallif to'ldirgan matn</p>"}
AUTH = {"id": "bmuallif01", "type": "paragraph", "data": {"html": "<p>MUALLIF BLOKI — saqlanishi shart</p>"}}
bl1.insert(vi + 1, AUTH)
sv_ = head.post(f"/api/kurs/lessons/{lid1}", json={"rev": L1["rev"], "title": L1["title"], "blocks": bl1})
ok(sv_.status_code == 200, "Muallif bloki qo'shildi va matn to'ldirildi (avtosaqlash)")
T = head.get("/api/dars/templates").json()
lay = json.loads(json.dumps(T["default"]))
lay["maruza"] = [x for x in lay["maruza"] if x["key"] not in ("refs",)]
lay["maruza"].insert(2, {"kind": "continue", "key": "cont"})
for x in lay["maruza"]:
    if x["key"] == "secvideo": x["text"] = "VIDEO DARS"
ts = head.post("/api/dars/templates", json={"department_id": sk["department_id"], "name": "Kafedra shabloni v2", "layout": lay, "note": "sinov"}).json()
ok(ts["ok"] and ts["template"]["version"] == 1 and ts["template"]["tkey"] == f"dep:{sk['department_id']}", "Bo'lim kafedra shablonini saqladi (kafedra uchun v1)")
lay["maruza"].append({"kind": "divider", "key": "div"})
ts2 = head.post("/api/dars/templates", json={"department_id": sk["department_id"], "name": "Kafedra shabloni v2", "layout": lay, "note": "ajratgich"}).json()
ok(ts2["template"]["version"] == 2 and len(head.get("/api/dars/templates").json()["items"][0]["versions"]) >= 1, "Har saqlash — yangi versiya (v2), tarix saqlanadi")
nv = head.post(f"/api/dars/subjects/{SK}/template/apply", json={"template_id": ts2["template"]["id"], "preview": True}).json()
t_ = nv["total"]
ok(not nv["applied"] and t_["lessons"] == 45 and t_["changed"] == 45 and t_["added"] == 30 and t_["removed"] == 15 and t_["updated"] == 15 and t_["author"] == 1,
   f"Ko'rish (farq): {t_['changed']}/{t_['lessons']} dars, +{t_['added']} −{t_['removed']} ~{t_['updated']}, muallif bloklari {t_['author']}")
ok(head.get(f"/api/kurs/lessons/{lid1}").json()["rev"] == L1["rev"] + 1, "Ko'rishda darslar o'zgarmadi")
ok(teach.post(f"/api/dars/subjects/{SK}/template/apply", json={"preview": True}).status_code == 403, "Begona fanga o'qituvchi shablon qo'llay olmaydi (403)")
ap_ = head.post(f"/api/dars/subjects/{SK}/template/apply", json={"template_id": ts2["template"]["id"], "preview": False}).json()
after = head.get(f"/api/kurs/lessons/{lid1}").json()["blocks"]
ids_ = [b["id"] for b in after]
ok(ap_["applied"] and AUTH["id"] in ids_ and next(b for b in after if b["id"] == AUTH["id"])["data"]["html"] == AUTH["data"]["html"], "Qo'llandi: muallif bloki joyida va o'zgarmagan")
vb = next(b for b in after if b["type"] == "video")
ok(vb["data"]["yt_id"] == "dQw4w9WgXcQ" and next(b for b in after if D.tpl_key(b["id"]) == "text")["data"]["html"] == "<p>Muallif to'ldirgan matn</p>",
   "Shablon bloklaridagi muallif mazmuni (video havola, matn) saqlandi")
ok(ids_.index(AUTH["id"]) == ids_.index(vb["id"]) + 1, "Muallif bloki o'z langari (video) ortida")
ok(not any(D.tpl_key(b["id"]) == "refs" for b in after) and any(D.tpl_key(b["id"]) == "cont" for b in after) and any(D.tpl_key(b["id"]) == "div" for b in after)
   and any(b["type"] == "heading" and b["data"]["text"] == "VIDEO DARS" for b in after), "Shablon o'zgarishlari: adabiyotlar olindi, «Davom etish» va ajratgich qo'shildi, sarlavha yangilandi")
ok(q("SELECT COUNT(*) n FROM ku_versions WHERE course_id=? AND note LIKE 'Shablon qo%'", (kl1,))[0]["n"] == 1, "Qo'llashdan oldin versiya saqlandi (tiklash mumkin)")
nv2 = head.post(f"/api/dars/subjects/{SK}/template/apply", json={"template_id": ts2["template"]["id"], "preview": True}).json()
ok(nv2["total"]["changed"] == 0, "Qayta ko'rish — o'zgarish yo'q")

# =============================================================================================
print("== 9. Ommaviy yig'ish / eksport — fon ishi, jarayon, zip ichida zip")
# boshqa to'plamlar namunasi (demo fan) o'zgarmasin — skelet fanida: L1 — Word yuklangan (shablon/paket), L2 — muharrir (bo'sh bloklar — xato), L3 — manbasiz
ok(head.post(f"/api/paket/courses/{SK}/topics/1/upload?name=maruza1.docx", content=RICH).status_code == 200, "Skelet fanining L1 darsiga Word yuklandi")
head.post(f"/api/dars/subjects/{SK}/lessons/2/authority", json={"authority": "kurs"})
jb = head.post(f"/api/dars/subjects/{SK}/bulk", json={"mode": "xapi", "keys": [1, 2, 3]}).json()
ok(jb["total"] == 3 and jb["status"] in ("ishlamoqda", "tayyor"), f"Ish boshlandi: #{jb['id']} ({jb['total']} dars)")
for _ in range(240):
    j = head.get(f"/api/dars/jobs/{jb['id']}").json()
    if j["status"] == "tayyor": break
    time.sleep(0.5)
res_ = {r["code"]: r for r in j["results"]}
ok(j["status"] == "tayyor" and j["pct"] == 100 and j["done"] == 3 and j["ok"] == 1 and j["failed"] == 2, f"Jarayon: {j['done']}/{j['total']} · ok {j['ok']} · xato {j['failed']}")
ok(res_["L1"]["source"] == "paket" and res_["L1"]["ok"] and res_["L2"]["source"] == "kurs" and not res_["L2"]["ok"] and "xato" in res_["L2"]["error"].lower(),
   f"L1 — shablon (paket) dan yig'ildi; L2 — muharrirdan, to'ldirilmagan bloklar — tushunarli xato: «{res_['L2'].get('error', '')[:60]}»")
ok(not res_["L3"]["ok"] and res_["L3"]["error"], f"Manbasiz dars o'tkazib yuborildi: «{res_['L3'].get('error', '')[:60]}»")
zr = head.get(j["download"])
zz = zipfile.ZipFile(io.BytesIO(zr.content)) if zr.status_code == 200 else None
names = zz.namelist() if zz else []
ok(zz and len(names) == 1 and all(n.endswith(".zip") for n in names) and "_L01_" in names[0], f"Zip ichida zip: {names}")
inner = zipfile.ZipFile(io.BytesIO(zz.read(names[0]))) if zz and names else None
ok(inner and "tincan.xml" in inner.namelist() and "content.js" in inner.namelist(), "Ichki zip — NEXTID xAPI paketi (tincan.xml, content.js)")
ok(res_["L1"].get("download") and head.get(res_["L1"]["download"]).status_code == 200, "Har darsni alohida yuklab olish havolasi ishlaydi")
ok(teach.get(f"/api/dars/jobs/{jb['id']}").status_code == 403, "Boshqa foydalanuvchi ishini o'qituvchi ko'rmaydi (403)")
sa = head.post(f"/api/dars/subjects/{demo}/lessons/1/authority", json={"authority": "paket"}).json()
ok(sa["authority"] == "paket" and head.get(f"/api/kurs/courses/{kc}").json()["dars"]["authority"] == "paket", "Eksport manbai almashtirildi (muharrir → shablon), kursda ko'rinadi")
head.post(f"/api/dars/subjects/{demo}/lessons/1/authority", json={"authority": "kurs"})

# =============================================================================================
print("== 10. Izohlar: blokka biriktirilgan, tarmoqli; to'xtatuvchi izoh tasdiqni to'xtatadi")
tl = teach.get(f"/api/kurs/lessons/{cot['lessons_list'][0]['id']}").json()
bu = next(b["id"] for b in tl["blocks"] if b["type"] == "table")
c1 = head.post(f"/api/dars/kurs/{kct}/comments", json={"lesson_id": tl["id"], "block_uid": bu, "text": "Jadval sarlavhasini qo'shing", "blocking": True, "mention_author": True}).json()
ok(c1["ok"] and c1["open"] == 1 and c1["blocking"] == 1 and c1["by_block"].get(bu) == 1, "Bo'lim to'xtatuvchi izoh qoldirdi (blokka, muallif eslatildi)")
ok(kaf_own.get(f"/api/kurs/courses/{kct}").status_code == 200 and kaf_own.get(f"/api/kurs/lessons/{tl['id']}").status_code == 200, "Kafedra o'z kafedrasi darsini muharrirda ko'radi")
ok(kaf_own.post(f"/api/kurs/lessons/{tl['id']}", json={"rev": tl["rev"], "blocks": []}).status_code == 403, "Kafedra tahrirlay olmaydi (403)")
ck = kaf_own.post(f"/api/dars/kurs/{kct}/comments", json={"lesson_id": tl["id"], "block_uid": bu, "text": "Kafedra: manbani ko'rsating", "blocking": True})
ok(ck.status_code == 200 and ck.json()["blocking"] == 2, "Kafedra o'z kafedrasi kursiga to'xtatuvchi izoh qoldiradi")
kaf_oth = S(uid("kafedra", department_id=other["department_id"]))
ok(kaf_oth.get(f"/api/dars/kurs/{kct}/comments").status_code == 403 and kaf_oth.post(f"/api/dars/kurs/{kct}/comments", json={"lesson_id": tl["id"], "text": "x y"}).status_code == 403,
   "Boshqa kafedra — izohlarni ko'rmaydi va yozmaydi (403)")
ok(teach.post(f"/api/dars/kurs/{kct}/comments", json={"lesson_id": tl["id"], "block_uid": bu, "text": "To'xtatuvchi", "blocking": True}).status_code == 403, "Muallif to'xtatuvchi izoh qo'ya olmaydi (403)")
ok(head.post(f"/api/dars/kurs/{kct}/comments", json={"lesson_id": tl["id"], "block_uid": "bnoexist01", "text": "Blok yo'q"}).status_code == 400, "Mavjud bo'lmagan blokka izoh — 400")
tc = teach.get(f"/api/dars/kurs/{kct}/comments").json()
th1 = next(t for t in tc["items"] if t["id"] == c1["id"])
rp = teach.post(f"/api/dars/kurs/{kct}/comments", json={"parent_id": th1["id"], "text": "Tuzatdim — sarlavha qo'shildi"}).json()
ok(rp["ok"] and len(next(t for t in rp["items"] if t["id"] == th1["id"])["replies"]) == 1, "Muallif tarmoqda javob yozdi")
mw = teach.get("/api/mywork").json()
ok(any("izoh" in (it.get("title") or "").lower() for it in mw.get("items", [])), "Muallifga bildirishnoma («Mening vazifalarim»): ko'rib chiquvchi izohlari")
mh = head.get("/api/mywork").json()
ok(any("javob bergan" in (it.get("title") or "") for it in mh.get("items", [])), "Bo'limga: muallif javob bergan to'xtatuvchi izohlar")
ok(teach.post(f"/api/dars/comments/{th1['id']}/resolve").status_code == 403, "Muallif to'xtatuvchi izohni o'zi hal qila olmaydi (403)")
g = teach.post(f"/api/kurs/courses/{kct}/action", json={"action": "submit"})
ok(g.status_code == 409 and g.json()["detail"]["gate"] and g.json()["detail"]["blocking"] == 2, "Ko'rib chiqishga yuborish — 2 ta ochiq to'xtatuvchi izoh: 409")
ok(teach.post(f"/api/kurs/courses/{kct}/action", json={"action": "submit", "override": "qisqa"}).status_code == 409, "Qisqa sabab (< 10 belgi) — rad")
# yuborish uchun kurs xatosiz bo'lsin: bo'sh shablon bloklarini olib tashlaymiz (muallif tahriri)
tl = teach.get(f"/api/kurs/lessons/{tl['id']}").json()
good = [{"id": b["id"], "type": b["type"], "data": b["data"]} for b in tl["blocks"] if not any(i["level"] == "xato" for i in b["issues"])]
teach.post(f"/api/kurs/lessons/{tl['id']}", json={"rev": tl["rev"], "title": tl["title"], "blocks": good})
for l_ in teach.get(f"/api/kurs/courses/{kct}").json()["lessons_list"][1:]:
    if not l_["blocks"]: teach.post(f"/api/kurs/lessons/{l_['id']}/delete")
ov = teach.post(f"/api/kurs/courses/{kct}/action", json={"action": "submit", "override": "Kafedra yig'ilishida kelishildi — muddat tugayapti"})
ok(ov.status_code == 200 and ov.json()["course"]["status"] == "korib_chiqishda", f"Sabab bilan aylanib o'tildi — ko'rib chiqishda ({ov.status_code} {ov.text[:120] if ov.status_code != 200 else ''})")
ok(q("SELECT COUNT(*) n FROM ds_overrides WHERE course_id=? AND action='submit' AND open_blocking=2", (kct,))[0]["n"] == 1
   and q("SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'dars: izohlar to%' AND detail LIKE ?", (f"ku #{kct}%",))[0]["n"] == 1, "Aylanib o'tish ds_overrides va audit jurnalida")
ap1 = head.post(f"/api/kurs/courses/{kct}/action", json={"action": "approve"})
ok(ap1.status_code == 409, "Tasdiqlash ham to'xtaydi (ochiq to'xtatuvchi izohlar)")
for t in head.get(f"/api/dars/kurs/{kct}/comments").json()["items"]:
    head.post(f"/api/dars/comments/{t['id']}/resolve")
cc = head.get(f"/api/dars/kurs/{kct}/comments").json()
ok(cc["open"] == 0 and all(t["status"] == "hal" and t["resolved_by"] for t in cc["items"]), "Bo'lim izohlarni hal qildi")
ro = head.post(f"/api/dars/comments/{th1['id']}/reopen").json()
ok(ro["open"] == 1 and ro["blocking"] == 1, "Qayta ochildi — to'siq qaytdi")
ok(head.post(f"/api/kurs/courses/{kct}/action", json={"action": "approve"}).status_code == 409, "Qayta ochilgan izoh — tasdiq yana to'xtaydi")
head.post(f"/api/dars/comments/{th1['id']}/resolve")
ap2_ = head.post(f"/api/kurs/courses/{kct}/action", json={"action": "approve"})
ok(ap2_.status_code == 200 and ap2_.json()["course"]["status"] == "tasdiqlangan", "Hamma izoh hal qilingach — tasdiqlandi")
nb_ = teach.post(f"/api/dars/kurs/{kct}/comments", json={"lesson_id": tl["id"], "text": "Oddiy izoh (to'xtatuvchi emas)"}).json()
mine = next(t for t in nb_["items"] if t["text"].startswith("Oddiy izoh"))
ok(not mine["blocking"] and teach.post(f"/api/dars/comments/{mine['id']}/resolve").status_code == 200, "Muallif oddiy izohni o'zi hal qiladi")
# paket tasdig'i ham: muharrir nusxasidagi to'xtatuvchi izoh
pid = q("SELECT id FROM pk_packages WHERE course_id=? AND topic_no=1 ORDER BY version DESC LIMIT 1", (SK,))[0]["id"]
lk = head.get(f"/api/kurs/courses/{kl1}").json()["lessons_list"][0]
lkb = head.get(f"/api/kurs/lessons/{lk['id']}").json()["blocks"][0]["id"]
head.post(f"/api/dars/kurs/{kl1}/comments", json={"lesson_id": lk["id"], "block_uid": lkb, "text": "Muqova rasmini almashtiring", "blocking": True})
sb = head.post(f"/api/paket/packages/{pid}/action", json={"action": "submit"})
ok(sb.status_code == 409 and sb.json()["detail"]["gate"], "Paketni bo'limga yuborish: muharrir nusxasida to'xtatuvchi izoh — 409")
head.post(f"/api/paket/packages/{pid}/action", json={"action": "submit", "override": "Sinov: paketni yuborish uchun sabab"})
pa = head.post(f"/api/paket/packages/{pid}/action", json={"action": "approve"})
ok(pa.status_code == 409 and pa.json()["detail"]["gate"], "Paket tasdig'i: muharrir nusxasida to'xtatuvchi izoh — 409")
pa2 = head.post(f"/api/paket/packages/{pid}/action", json={"action": "approve", "override": "Rahbariyat ko'rsatmasi bilan tasdiqlanmoqda"})
ok(pa2.status_code == 200 and pa2.json()["package"]["status"] == "tasdiqlandi", "Sabab bilan — tasdiqlandi (audit)")
for t in head.get(f"/api/dars/kurs/{kl1}/comments").json()["items"]:      # keyingi to'plamlar uchun ochiq to'xtatuvchi izoh qoldirilmaydi
    head.post(f"/api/dars/comments/{t['id']}/resolve")

# =============================================================================================
print("== 11. AI: hujjatdan dars — kalitsiz va ruxsat")
n0 = len(head.get(f"/api/kurs/courses/{kct}").json()["lessons_list"])
r = teach.post(f"/api/dars/kurs/{kct}/ai-lesson?name=maruza.docx", content=RICH)
ok(r.status_code == 503 and "AI ulanmagan" in r.json()["detail"] and "administrator" in r.json()["detail"], f"Kalitsiz — 503, o'zbekcha: «{r.json()['detail'][:60]}…»")
ok(len(head.get(f"/api/kurs/courses/{kct}").json()["lessons_list"]) == n0 and q("SELECT COUNT(*) n FROM ds_ai")[0]["n"] == 0, "Soxta natija yo'q: dars qo'shilmadi")
ok(kaf_own.post(f"/api/dars/kurs/{kct}/ai-lesson?name=x.docx", content=RICH).status_code == 403 and rek.post(f"/api/dars/kurs/{kct}/ai-lesson", content=b"x").status_code == 403, "Kafedra va rektor — 403")
src_ = D.source_sections(RICH, "maruza3")
ok([s_["title"] for s_ in src_["sections"]][:2] == ["1. Kompyuter turlari", "2. O'lchov birliklari"] and any(p_["t"] == "fig" for p_ in src_["sections"][0]["parts"])
   and any(p_["t"] == "table" for p_ in src_["sections"][1]["parts"]) and len(src_["images"]) == 1, "Manba: Word → bo'limlar (sarlavha bo'yicha), rasm va jadval bilan")

# =============================================================================================
print("== 12. Brauzer: birlashgan ekran va izohlar paneli")
pwj, chrome, node = os.environ.get("PW"), os.environ.get("CHROME"), shutil.which("node")
if node:
    for f in ("static/dars.js", "static/kurs.js", "static/paket.js", "tools/dars_check.js"):
        rr = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
        ok(rr.returncode == 0, f"node --check {f}" + ("" if rr.returncode == 0 else ": " + rr.stderr.strip()[:200]))
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    env = dict(os.environ, B=B, DS_UID=str(head_u), DS_PW=PW, DS_CID=str(demo), DS_KCID=str(kc), OUT=os.environ.get("DS_OUT") or str(Path(os.environ.get("TMPDIR", "/tmp")) / "isft_dars"))
    rr = subprocess.run([node, str(ROOT / "tools" / "dars_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    for ln in (rr.stdout + rr.stderr).splitlines():
        s = ln.strip()
        if s.startswith("✓"): ok(True, "[brauzer] " + s[1:].strip())
        elif s.startswith("✗"): ok(False, "[brauzer] " + s[1:].strip())
    ok(rr.returncode == 0, f"tools/dars_check.js chiqish kodi 0 ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-12:])))

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
