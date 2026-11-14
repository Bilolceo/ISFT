"""«Dars tayyorlash»: (A) Kurs muharriri ro'yxatida fan bo'yicha guruhlar (GET /api/kurs/courses — groups, standalone, fans, filtrlar, ko'lam) va
(B) paket → muharrir qayta sinxronlash (GET/POST /api/dars/subjects/{cid}/lessons/{key}/resync): paket o'zgarganda «Yangi fayllar bor»,
ko'rish sonlari, faqat shablon bloklari qo'shiladi / yangilanadi (uid'lar saqlanadi), muallif bloklari bayt-baayt o'zgarmaydi, muallif o'zgartirgan
shablon bandi tegilmaydi, versiya surati + rev + audit, bayroq o'chadi va yangi o'zgarishda qaytadi, qayta bosish — o'zgarishsiz, ruxsatlar (403).

Ishga tushirish:  python tests/run_all.py --only dars_resync
DIQQAT: bazani o'zgartiradi — PRODUCTION'da ishlatilmaydi.
"""
import io, json, os, re, sqlite3, sys
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

from app import dars as D, kurs as K   # sof funksiyalar — baza talab qilmaydi

# =============================================================================================
print("== 1. Sof funksiyalar: resync_actions / resync_apply — muallif bloklari tegilmaydi")
items = D.clean_layout(D.DEFAULT_LAYOUT)["maruza"]
A0 = K._Assets(None)
cl = lambda t, d: K.clean_block(t, d, A0)
blocks = [{"id": b["id"], "type": b["type"], "data": cl(b["type"], b["data"])}
          for b in D.assemble(items, {"text": [("paragraph", {"html": "<p>Eski matn</p>"})], "plan": [("heading", {"text": "Reja", "level": 2}), ("list", {"style": "numbered", "items": ["Bir"]})]},
                              "1-MAVZU", fill_empty=False)]
AUTH = {"id": "bmuallif77", "type": "paragraph", "data": {"html": "<p>Muallif bloki</p>"}}
ti = next(i for i, b in enumerate(blocks) if D.tpl_key(b["id"]) == "text")
blocks.insert(ti + 1, AUTH)
gh = lambda k: D._gh([b for b in blocks if D.tpl_key(b["id"]) == k])
rec = {"text": {"fp": "eski", "ed": gh("text")}, "plan": {"fp": "eski", "ed": "boshqa"}, "video": {"fp": None, "ed": gh("video")}}
fps = {"text": "yangi", "plan": "yangi", "video": "yangi", "files": "yangi"}
acts = D.resync_actions(blocks, items, fps, rec, "1-MAVZU")
ok(acts["text"] == "update" and acts["plan"] == "conflict" and acts["video"] == "fill" and acts["files"] == "fill" and acts["refs"] == "empty"
   and "secvideo" not in acts and "quiz" not in acts, f"Amallar: matn — update, reja (muallif o'zgartirgan) — conflict, video/fayllar — fill, bo'sh — empty: {acts}")
slots = {"text": [("paragraph", {"html": "<p>Yangi 1</p>"}), ("paragraph", {"html": "<p>Yangi 2</p>"})], "video": [("video", {"source": "youtube", "youtube": "https://youtu.be/dQw4w9WgXcQ"})],
         "files": [("attachment", {"title": "Fayl"})], "plan": [("list", {"style": "numbered", "items": ["X"]})]}
nb, diff = D.resync_apply(blocks, items, slots, acts)
ids = [b["id"] for b in nb]
old_text_id = blocks[ti]["id"]
ok(AUTH in nb and ids.count(AUTH["id"]) == 1, "Muallif bloki — aynan o'zi (uid va mazmun)")
ok(nb[ids.index(old_text_id)]["data"]["html"] == "<p>Yangi 1</p>" and D.tpl_key(nb[ids.index(old_text_id) + 1]["id"]) == "text"
   and nb[ids.index(old_text_id) + 1]["data"]["html"] == "<p>Yangi 2</p>" and ids.index(AUTH["id"]) == ids.index(old_text_id) + 2,
   "Matn bandi: o'sha uid joyida yangilandi, yetmagani shablon uid'i bilan ortidan qo'shildi (muallif bloki o'z joyida)")
vi = next(i for i, b in enumerate(nb) if D.tpl_key(b["id"]) == "video")
ok(D.tpl_key(nb[vi - 1]["id"]) == "secvideo", "Bloki yo'q band (video) — shablon o'rnida (VIDEODARS sarlavhasidan keyin) qo'shildi")
ok([b for b in nb if D.tpl_key(b["id"]) == "plan"] == [b for b in blocks if D.tpl_key(b["id"]) == "plan"], "Muallif o'zgartirgan band (reja) — tegilmadi")
ok(diff["added"] == 3 and diff["updated"] == 1 and diff["removed"] == 0 and diff["author"] == 1, f"Farq: +{diff['added']} ~{diff['updated']} −{diff['removed']}, muallif {diff['author']}")
nb2, d2 = D.resync_apply(nb, items, slots, {k: "same" for k in acts})
ok(nb2 == nb and d2["added"] == d2["updated"] == 0, "Amal yo'q — bloklar o'zgarmaydi")

# =============================================================================================
head_u, teach_u = uid("masofaviy"), uid("oqituvchi")
head, teach, rek = S(head_u), S(teach_u), S(uid("rektor"))
tid = q("SELECT teacher_id FROM users WHERE id=?", (teach_u,))[0]["teacher_id"]
own = q("SELECT id, department_id, topics, subject FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 1", (tid,))[0]
kaf = S(uid("kafedra", department_id=own["department_id"]))
linked = {r["lkey"] for r in q("SELECT lkey FROM ds_links WHERE dl_course_id=?", (own["id"],))}
KEY = next(k for k in range(int(own["topics"] or 15), 0, -1) if k not in linked and k != 3)
CID = own["id"]
U = f"/api/dars/subjects/{CID}/lessons/{KEY}/resync"
print(f"== 2. Paket → muharrir: o'tkazish vaqtidagi holat yoziladi (fan #{CID}, L{KEY})")
T1 = """{n}-MAVZU: RAQAMLI IQTISODIYOT
Reja:
1. Raqamli iqtisodiyot tushunchasi
2. Raqamli platformalar

1. Raqamli iqtisodiyot tushunchasi
Raqamli iqtisodiyot — axborot texnologiyalariga asoslangan iqtisodiy faoliyat. Bu sohada ma'lumotlar asosiy resurs hisoblanadi.

2. Raqamli platformalar
Platformalar xaridor va sotuvchini bog'laydi. Masalan, onlayn do'konlar.
""".replace("{n}", str(KEY))
T2 = T1.replace("2. Raqamli platformalar\n\n", "2. Raqamli platformalar\n3. Raqamli to'lovlar\n\n", 1) + """
3. Raqamli to'lovlar
Raqamli to'lovlar naqd pulsiz hisob-kitobni tezlashtiradi. Bank kartalari va mobil ilovalar keng tarqalgan.
"""
ok(teach.post(f"/api/paket/courses/{CID}/topics/{KEY}/text/paste", json={"text": T1, "name": "matn.txt"}).status_code == 200, "O'qituvchi ma'ruza matnini kiritdi")
ok(teach.get(U).status_code == 404, "O'tkazilmagan dars — 404")
cv = teach.post(f"/api/dars/subjects/{CID}/lessons/{KEY}/convert").json()
KC = cv["ku_course_id"]
sy = q("SELECT * FROM ds_sync WHERE dl_course_id=? AND lkey=?", (CID, KEY))
ok(cv["created"] and sy and sy[0]["ku_course_id"] == KC and json.loads(sy[0]["slots"]).get("text", {}).get("fp"), f"O'tkazildi (ku #{KC}) va paket holati (ds_sync) yozildi")
r0 = teach.get(U).json()
ok(r0["tracked"] and not r0["pending"] and r0["add"] == 0 and r0["update"] == 0, "O'tkazishdan keyin darhol — «Yangi fayllar bor» yo'q")
lid = teach.get(f"/api/kurs/courses/{KC}").json()["lessons_list"][0]["id"]
L0 = teach.get(f"/api/kurs/lessons/{lid}").json()
bl = [{"id": b["id"], "type": b["type"], "data": b["data"]} for b in L0["blocks"]]
ti = max(i for i, b in enumerate(bl) if D.tpl_key(b["id"]) == "text")
AUTH1 = {"id": "bmuallifa1", "type": "paragraph", "data": {"html": "<p>Muallif qo'shimchasi — o'zgarmasligi shart</p>"}}
AUTH2 = {"id": "bmuallifa2", "type": "quote", "data": {"text": "Muallif iqtibosi", "author": "O'qituvchi"}}
bl.insert(ti + 1, AUTH1); bl.append(AUTH2)
pi = next(i for i, b in enumerate(bl) if D.tpl_key(b["id"]) == "plan" and b["type"] == "list")
bl[pi]["data"] = {**bl[pi]["data"], "items": ["Muallif tahrir qilgan reja bandi"]}
sv = teach.post(f"/api/kurs/lessons/{lid}", json={"rev": L0["rev"], "title": L0["title"], "blocks": bl})
ok(sv.status_code == 200, "Muharrirda: 2 ta muallif bloki qo'shildi, reja bandi qo'lda tahrirlandi (avtosaqlash)")
snap = lambda: {r["uid"]: r["data"] for r in q("SELECT uid, data FROM ku_blocks WHERE lesson_id=? AND uid IN (?,?)", (lid, AUTH1["id"], AUTH2["id"]))}
plan_row = lambda: q("SELECT data FROM ku_blocks WHERE lesson_id=? AND uid=?", (lid, bl[pi]["id"]))[0]["data"]
A_BEFORE, P_BEFORE = snap(), plan_row()
ok(len(A_BEFORE) == 2, "Muallif bloklari bazada")
r1 = teach.get(U).json()
ok(not r1["pending"], "Faqat muharrirdagi o'zgarish — paket bayrog'i yo'q")

print("== 3. Paket o'zgardi (video havola, qo'shimcha fayl, matn) → «Yangi fayllar bor» va ko'rish sonlari")
def png(color=(20, 120, 160), size=(64, 48)):
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "PNG"); return b.getvalue()
ok(teach.post(f"/api/paket/courses/{CID}/topics/{KEY}/video", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).status_code == 200, "Video havola qo'shildi")
ok(teach.post(f"/api/paket/courses/{CID}/topics/{KEY}/files?name=jadval.png", content=png()).status_code == 200, "Qo'shimcha fayl yuklandi")
ok(teach.post(f"/api/paket/courses/{CID}/topics/{KEY}/text/paste", json={"text": T2, "name": "matn2.txt"}).status_code == 200, "Ma'ruza matni yangilandi (3-bo'lim)")
rev0 = q("SELECT rev FROM ku_courses WHERE id=?", (KC,))[0]["rev"]; lrev0 = q("SELECT rev FROM ku_lessons WHERE id=?", (lid,))[0]["rev"]
nver0 = q("SELECT COUNT(*) n FROM ku_versions WHERE course_id=?", (KC,))[0]["n"]
pv = teach.get(U).json()
sl = {s["kind"]: s for s in pv["slots"]}
ok(pv["pending"] and pv["author"] == 2, f"«Yangi fayllar bor»: {pv['add']} ta qo'shiladi, {pv['update']} ta yangilanadi, muallif bloklari {pv['author']}")
ok(sl.get("video", {}).get("add") == 1 and sl.get("files", {}).get("add") == 1, "Video va fayl bandlari — yangi bloklar (+1, +1)")
ok(sl.get("text", {}).get("action") == "update" and sl["text"]["update"] == 4 and sl["text"]["add"] == 2,
   f"Matn bandi (muharrirda o'zgartirilmagan) — 4 ta joyida yangilanadi, 2 ta qo'shiladi: {sl.get('text')}")
ok("plan" not in sl and pv["conflict"] == 1 and pv["conflicts"] == ["Reja"], "Reja (muallif tahrirlagan) — tegilmaydi (ziddiyat sifatida ko'rsatiladi)")
ok(pv["add"] == 4 and pv["update"] == 4 and pv["remove"] == 0, f"Jami: +{pv['add']} ~{pv['update']} −{pv['remove']}")
pv2 = teach.post(U, json={"preview": True}).json()
ok(pv2["add"] == pv["add"] and pv2["update"] == pv["update"] and not pv2["applied"], "POST preview — o'sha sonlar, qo'llanmadi")
ok(q("SELECT rev FROM ku_lessons WHERE id=?", (lid,))[0]["rev"] == lrev0 and q("SELECT COUNT(*) n FROM ku_versions WHERE course_id=?", (KC,))[0]["n"] == nver0,
   "Ko'rishda baza o'zgarmadi")

print("== 4. Ruxsatlar: o'tkazish bilan bir xil")
ok(kaf.get(U).status_code == 403 and kaf.post(U, json={"preview": False}).status_code == 403, "Kafedra — 403 (ko'rish va qo'shish)")
ok(rek.post(U, json={"preview": False}).status_code == 403, "Rektor — 403")
oth = q("SELECT l.dl_course_id c, l.lkey k FROM ds_links l JOIN dl_courses d ON d.id=l.dl_course_id WHERE d.teacher_id<>? ORDER BY l.dl_course_id LIMIT 1", (tid,))
if oth: ok(teach.post(f"/api/dars/subjects/{oth[0]['c']}/lessons/{oth[0]['k']}/resync", json={"preview": False}).status_code == 403, "O'qituvchi — begona fan darsi 403")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'dars: paketdan yangilash%' AND allowed=0")[0]["n"] >= 2, "Rad etilgan so'rovlar audit jurnalida")
ok(q("SELECT rev FROM ku_lessons WHERE id=?", (lid,))[0]["rev"] == lrev0, "Rad etilganda dars o'zgarmadi")

print("== 5. «Muharrirga qo'shish»: versiya surati, rev, audit; muallif bloklari bayt-baayt o'zgarmagan")
ap = teach.post(U, json={"preview": False}).json()
ok(ap["applied"] and ap["add"] == 4 and ap["update"] == 4, f"Qo'llandi: +{ap['add']} ~{ap['update']}")
ok(q("SELECT COUNT(*) n FROM ku_versions WHERE course_id=?", (KC,))[0]["n"] == nver0 + 1
   and q("SELECT note FROM ku_versions WHERE course_id=? ORDER BY id DESC LIMIT 1", (KC,))[0]["note"].startswith("Paketdan yangilashdan oldin"), "Oldin versiya surati saqlandi")
ok(q("SELECT rev FROM ku_courses WHERE id=?", (KC,))[0]["rev"] == rev0 + 1 and q("SELECT rev FROM ku_lessons WHERE id=?", (lid,))[0]["rev"] == lrev0 + 1, "Kurs va dars rev oshdi")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE action='dars: paketdan muharrirga qo''shildi' AND allowed=1")[0]["n"] >= 1, "Audit jurnalida")
ok(snap() == A_BEFORE, "Muallif bloklari (bazadagi JSON) — bayt-baayt bir xil")
ok(plan_row() == P_BEFORE, "Muallif tahrirlagan reja bandi — bayt-baayt bir xil")
after = teach.get(f"/api/kurs/lessons/{lid}").json()["blocks"]
aid = [b["id"] for b in after]
vb = [b for b in after if D.tpl_key(b["id"]) == "video"]
fb = [b for b in after if D.tpl_key(b["id"]) == "files"]
tb = [b for b in after if D.tpl_key(b["id"]) == "text"]
ok(len(vb) == 1 and vb[0]["type"] == "video" and vb[0]["data"].get("yt_id") == "dQw4w9WgXcQ", "Video bloki qo'shildi (shablon uid'i bilan)")
ok(len(fb) == 1 and fb[0]["type"] == "attachment" and fb[0]["data"].get("asset") and teach.get(f"/api/kurs/assets/{fb[0]['data']['asset']}").status_code == 200,
   "Fayl bloki — fayl muharrir kursiga ko'chirildi")
old_text_ids = [b["id"] for b in bl if D.tpl_key(b["id"]) == "text"]
ok(len(tb) == 6 and [b["id"] for b in tb][:4] == old_text_ids and any("Raqamli to'lovlar" in json.dumps(b["data"], ensure_ascii=False) for b in tb),
   "Matn bandi: eski uid'lar joyida yangilandi, yangi bo'lim qo'shildi")
ok(aid.index(AUTH1["id"]) > aid.index(old_text_ids[-1]) and aid[-1] == AUTH2["id"], "Muallif bloklari o'z joyida (langar ortida, oxirida)")
r2 = teach.get(U).json()
ok(not r2["pending"] and r2["tracked"], "Bayroq o'chdi")
ap2 = teach.post(U, json={"preview": False}).json()
ok(not ap2["applied"] and ap2["add"] == 0 and ap2["update"] == 0 and q("SELECT rev FROM ku_lessons WHERE id=?", (lid,))[0]["rev"] == lrev0 + 1
   and q("SELECT COUNT(*) n FROM ku_versions WHERE course_id=?", (KC,))[0]["n"] == nver0 + 1, "Qayta bosish — o'zgarishsiz (rev va versiyalar o'sha)")

print("== 6. Yangi o'zgarish — bayroq qaytadi")
ok(teach.post(f"/api/paket/courses/{CID}/topics/{KEY}/files?name=sxema.png", content=png((200, 80, 40))).status_code == 200, "Yana bitta fayl yuklandi")
r3 = teach.get(U).json()
s3 = {s["kind"]: s for s in r3["slots"]}
ok(r3["pending"] and list(s3) == ["files"] and s3["files"]["update"] == 1 and s3["files"]["add"] == 1, f"«Yangi fayllar bor» qaytdi — faqat fayllar bandi: {s3.get('files')}")
ap3 = teach.post(U, json={"preview": False}).json()
ok(ap3["applied"] and snap() == A_BEFORE and len([b for b in teach.get(f"/api/kurs/lessons/{lid}").json()["blocks"] if D.tpl_key(b["id"]) == "files"]) == 2,
   "Qo'shildi: 2 ta fayl bloki, muallif bloklari yana o'zgarmagan")
tv = teach.get(f"/api/paket/courses/{CID}/topics/{KEY}").json()
ok(tv["kurs_link"] and tv["kurs_link"]["id"] == KC and not teach.get(U).json()["pending"], "Dars paneli: muharrir havolasi, bayroq yo'q")
js = (ROOT / "static" / "dars.js").read_text()
ok("Yangi fayllar bor" in js and "Muharrirga qo'shish" in js and "/resync" in js, "dars.js: dars panelida «Yangi fayllar bor» / «Muharrirga qo'shish»")

# =============================================================================================
print("== 7. Kurs muharriri ro'yxati: fan bo'yicha guruhlar, «Mustaqil kurslar», filtr, ko'lam")
fan2 = q("""SELECT c.id, c.subject, c.topics, c.department_id FROM dl_courses c WHERE c.topics BETWEEN 3 AND 20 AND c.teacher_id<>?
            AND c.id NOT IN (SELECT dl_course_id FROM ds_links) AND c.id NOT IN (SELECT course_id FROM pk_lessons) ORDER BY c.id LIMIT 1""", (tid,))[0]
sk = head.post(f"/api/dars/subjects/{fan2['id']}/skeleton", json={"ratio": 0, "apply": True}).json()
N = int(fan2["topics"])
ok(sk["applied"] and sk["created"] == N, f"Fan skeleti (faqat L): {N} ta muharrir kursi")
solo = head.post("/api/kurs/courses", json={"title": "Mustaqil sinov kursi (guruhsiz)"}).json()
d = head.get("/api/kurs/courses").json()
G = {g["dl_course_id"]: g for g in d["groups"]}
g2 = G.get(fan2["id"])
by = {it["id"]: it for it in d["items"]}
ok(g2 and g2["n"] == N and g2["subject"] == fan2["subject"] and sum(g2["counts"].values()) == N, f"Fan guruhi: «{fan2['subject']}» — {N} ta kurs, holatlar soni")
ok(g2 and [by[i]["dars"]["code"] for i in g2["ids"]] == [f"L{i}" for i in range(1, N + 1)], "Guruh ichida dars kodi tartibida (L1..Ln)")
ok(solo["id"] in d["standalone"] and not any(solo["id"] in g["ids"] for g in d["groups"]) and by[solo["id"]]["dars"] is None, "Bog'lanmagan kurs — «Mustaqil kurslar»da")
ok(set(d["standalone"]) | {i for g in d["groups"] for i in g["ids"]} == set(by) and len(d["items"]) == d["total"], "Har kurs aynan bitta joyda (guruh yoki mustaqil)")
ok(any(f["dl_course_id"] == fan2["id"] and f["n"] == N for f in d["fans"]) and CID in G and KC in G[CID]["ids"], "Fanlar ro'yxati (filtr uchun) va o'tkazilgan dars ham o'z fani guruhida")
df = head.get(f"/api/kurs/courses?fan={fan2['id']}").json()
ok([g["dl_course_id"] for g in df["groups"]] == [fan2["id"]] and df["total"] == N and not df["standalone"] and len(df["fans"]) == len(d["fans"]),
   "Filtr: bitta fan — faqat shu guruh (fanlar ro'yxati to'liq qoladi)")
dq = head.get("/api/kurs/courses", params={"q": fan2["subject"][:12]}).json()
ok(any(g["dl_course_id"] == fan2["id"] and g["n"] == N for g in dq["groups"]), f"Qidiruv fan nomi bo'yicha («{fan2['subject'][:12]}») — guruh to'liq")
dn = head.get("/api/kurs/courses", params={"q": "Mustaqil sinov kursi"}).json()
ok(dn["standalone"] == [solo["id"]] and not dn["groups"], "Qidiruv kurs nomi bo'yicha — faqat mos kurs")
ds = head.get("/api/kurs/courses?status=tasdiqlangan").json()
ok(all(by[i]["status"] == "tasdiqlangan" for g in ds["groups"] for i in g["ids"]), "Holat filtri guruhlarda ham amal qiladi")
dt = teach.get("/api/kurs/courses").json()
ok(fan2["id"] not in {g["dl_course_id"] for g in dt["groups"]} and CID in {g["dl_course_id"] for g in dt["groups"]} and solo["id"] not in {it["id"] for it in dt["items"]},
   "O'qituvchi: faqat o'z ko'lami (begona fan guruhi va boshqa muallif kursi ko'rinmaydi)")
kf = S(uid("kafedra", department_id=fan2["department_id"])) if fan2["department_id"] else None
if kf:
    dk = kf.get("/api/kurs/courses").json()
    ok(fan2["id"] in {g["dl_course_id"] for g in dk["groups"]} and all(it["dl_course_id"] for it in dk["items"]), "Kafedra: o'z kafedrasi fani guruhi ko'rinadi (ko'lam o'zgarmagan)")
ok(rek.get("/api/kurs/courses").status_code == 403, "Rektor — ro'yxat 403 (faqat jamlangan sonlar)")
kjs = (ROOT / "static" / "kurs.js").read_text()
ok("Mustaqil kurslar" in kjs and "localStorage" in kjs and "kuGroupsHtml" in kjs, "kurs.js: guruhlar, «Mustaqil kurslar», yig'ish holati localStorage'da")

print()
if fails:
    print(f"XATO: {len(fails)} ta"); [print("  -", f) for f in fails]; sys.exit(1)
print("Hammasi o'tdi ✓")
