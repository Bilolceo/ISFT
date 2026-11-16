"""Kurs muharriri (app/kurs.py, app/kurs_player, static/kurs.js) — ruxsatlar (o'qituvchi begona kursga kira olmaydi, rahbariyat — faqat jamlangan
sonlar), har bir blok turini tozalash va tekshirish (XSS urinishlari), avtosaqlash ziddiyati (rev → 409, force), versiyalar va tiklash,
ko'rib chiqish oqimi, fayllar (rasm, noto'g'ri tur, begona kurs), ko'rish (imzolangan yo'l, CSP), eksport — SCORM 1.2 / SCORM 2004 / xAPI /
HTML (validate_zip, tincan.xml faoliyatlari, deterministiklik), test baholash qoidasi, Test bankdan savollar, Rise importi (sintetik namuna
tests/fixtures/rise_sample + haqiqiy eksport papkasi bo'lsa), import zip xavfsizligi (yo'l hujumi, zip bombasi, noto'g'ri fayl), sifat
hisoboti raqamlari va bir bosishli tuzatishlar. Brauzer (PW va CHROME berilganda): tools/kurs_player_check.js (pleyer, mock LMS) va
tools/kurs_editor_check.js (muharrir).

Ishga tushirish:  python tests/run_all.py --only kurs   (yoki ISFT_TEST_URL=… ISFT_CORE_DB=… .venv/bin/python tests/test_kurs.py)
Haqiqiy Rise eksporti: ISFT_RISE_DIR (standart ~/Desktop/xalqaro-munosabatlar-tarixi-va-nazariyalari-xapi-TewydUpU) — yo'q bo'lsa o'tkaziladi.
DIQQAT: bazani o'zgartiradi (kurslar yaratiladi) — PRODUCTION'da ishlatilmaydi.
"""
import hashlib, io, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
FIX = ROOT / "tests" / "fixtures" / "rise_sample"
REAL = Path(os.environ.get("ISFT_RISE_DIR") or Path.home() / "Desktop" / "xalqaro-munosabatlar-tarixi-va-nazariyalari-xapi-TewydUpU")
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
def zip_dir(d: Path, extra: dict | None = None) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.name != ".DS_Store": z.write(p, p.relative_to(d).as_posix())
        for k, v in (extra or {}).items(): z.writestr(k, v)
    return bio.getvalue()
def png(w=64, h=48, color=(135, 0, 55)) -> bytes:
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, "PNG"); return b.getvalue()
P = "/api/kurs"

from app import kurs as K, paket as PK   # sof funksiyalar (tozalash, baholash, sifat, validator) — baza talab qilmaydi

head, staff, teach, rek, pro, bux = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "oqituvchi", "rektor", "prorektor_oquv", "buxgalteriya"))
teach_uid, head_uid = uid("oqituvchi"), uid("masofaviy")
teach_tid = q("SELECT teacher_id FROM users WHERE id=?", (teach_uid,))[0]["teacher_id"]
own_dl = q("SELECT id FROM dl_courses WHERE teacher_id=? ORDER BY id LIMIT 1", (teach_tid,))
other_dl = q("SELECT id FROM dl_courses WHERE teacher_id<>? ORDER BY id LIMIT 1", (teach_tid,))[0]["id"]

# =============================================================================================
print("== 1. Ruxsatlar va ko'lam")
m = head.get(P + "/meta").json()
ok(m["caps"]["write"] and m["caps"]["approve"] and m["caps"]["import"] and len(m["blocks"]) == len(K.BLOCKS) and set(m["categories"]) == set(K.CATEGORIES),
   f"Bo'lim boshlig'i: tahrirlash, tasdiqlash, import; blok kutubxonasi ({len(m['blocks'])} tur)")
mt = teach.get(P + "/meta").json()
ok(mt["caps"]["write"] and not mt["caps"]["approve"] and mt["scope"] == "O'z kurslaringiz", "O'qituvchi: tahrirlaydi, tasdiqlamaydi; ko'lam — o'z kurslari")
mr = rek.get(P + "/meta").json()
ok(mr["caps"]["summary_only"] and not mr["caps"]["write"] and "blocks" not in mr, "Rektor: faqat jamlangan sonlar (blok kutubxonasi yo'q)")
sm = rek.get(P + "/summary").json()
ok(set(sm) >= {"courses", "by_status", "lessons", "blocks", "imported", "exports"} and "items" not in sm and not any(isinstance(v, list) for v in sm.values()),
   f"Rektor jamlangan ko'rsatkichlari (kurs nomlarisiz): {sm['courses']} kurs")
ok(pro.get(P + "/summary").status_code == 200 and pro.get(P + "/courses").status_code == 403, "O'quv prorektori: jamlangan sonlar 200, kurslar ro'yxati 403")
ok(rek.get(P + "/courses").status_code == 403 and rek.post(P + "/courses", json={"title": "x"}).status_code == 403, "Rektor kurs ko'rmaydi va yaratmaydi (403)")
ok(bux.get(P + "/meta").status_code == 403 and bux.get(P + "/summary").status_code == 403, "Buxgalteriya — ruxsat yo'q (403)")
hc = head.post(P + "/courses", json={"title": "Bo'lim kursi (sinov)"}).json()["id"]
hco = head.get(f"{P}/courses/{hc}").json()
hl = hco["lessons_list"][0]["id"]
ok(teach.get(f"{P}/courses/{hc}").status_code == 403 and teach.get(f"{P}/lessons/{hl}").status_code == 403, "O'qituvchi begona (bo'lim) kursini ochmaydi (403)")
ok(teach.post(f"{P}/lessons/{hl}", json={"rev": 1, "blocks": []}).status_code == 403 and teach.post(f"{P}/courses/{hc}/lessons", json={}).status_code == 403
   and teach.post(f"{P}/courses/{hc}/export", json={"mode": "xapi"}).status_code == 403 and teach.get(f"{P}/courses/{hc}/preview-url").status_code == 403,
   "O'qituvchi begona kursni tahrirlamaydi, dars qo'shmaydi, eksport va ko'rish qilmaydi (403)")
ok(rek.get(f"{P}/courses/{hc}").status_code == 403 and rek.post(f"{P}/lessons/{hl}", json={"rev": 1, "blocks": []}).status_code == 403, "Rektor kurs tarkibini ko'rmaydi va tahrirlamaydi (403)")
ok(teach.post(P + "/courses", json={"title": "x", "dl_course_id": other_dl}).status_code == 403, "O'qituvchi o'zi o'qitmaydigan masofaviy kursga bog'lay olmaydi (403)")
tc = teach.post(P + "/courses", json={"title": "O'qituvchi kursi (sinov)", "dl_course_id": own_dl[0]["id"] if own_dl else None}).json()["id"]
tl = teach.get(P + "/courses").json()
ok(any(x["id"] == tc for x in tl["items"]) and not any(x["id"] == hc for x in tl["items"]), "O'qituvchi ro'yxatida — faqat o'z kurslari")
ok(head.get(f"{P}/courses/{tc}").status_code == 200 and any(x["id"] == tc for x in staff.get(P + "/courses").json()["items"]), "Bo'lim (boshliq, xodim) o'qituvchi kursini ko'radi")
if own_dl:
    lc = head.post(P + "/courses", json={"title": "Bo'lim yaratgan, o'qituvchi faniga bog'langan", "dl_course_id": own_dl[0]["id"]}).json()["id"]
    ok(teach.get(f"{P}/courses/{lc}").status_code == 200, "O'qituvchi o'zi o'qitadigan masofaviy kursga bog'langan kursni ko'radi")
if own_dl:   # kafedra mudiri («Dars tayyorlash» birlashuvi, app/dars.py): o'z kafedrasi fanlariga bog'langan kurslarni faqat ko'radi va izoh qoldiradi
    dep = q("SELECT department_id FROM dl_courses WHERE id=?", (own_dl[0]["id"],))[0]["department_id"]
    kr = q("SELECT id FROM users WHERE role='kafedra' AND active=1 AND department_id=? ORDER BY id LIMIT 1", (dep,))
    if kr:
        kaf = S(kr[0]["id"])
        km = kaf.get(P + "/meta").json()
        kl = kaf.get(P + "/courses").json()["items"]
        ok(not km["caps"]["write"] and km["caps"]["review"] and "blocks" in km and {x["id"] for x in kl} >= {tc, lc} and hc not in {x["id"] for x in kl},
           "Kafedra: faqat ko'rish va izoh — o'z kafedrasi fanlariga bog'langan kurslar ro'yxatda, bog'lanmagani yo'q")
        ok(kaf.get(f"{P}/courses/{lc}").status_code == 200 and kaf.get(f"{P}/courses/{hc}").status_code == 403, "Kafedra: bog'langan kursni ochadi (200), begonasini — 403")
        kls = kaf.get(f"{P}/courses/{lc}").json()["lessons_list"][0]["id"]
        ok(kaf.post(f"{P}/lessons/{kls}", json={"rev": 1, "blocks": []}).status_code == 403 and kaf.post(f"{P}/courses/{lc}/export", json={"mode": "xapi"}).status_code == 403
           and kaf.post(f"{P}/courses/{lc}/action", json={"action": "approve"}).status_code == 403, "Kafedra: tahrirlash, eksport va tasdiqlash — 403")
den = q("SELECT COUNT(*) n FROM audit_log WHERE resource='kurs' AND allowed=0")[0]["n"]
ok(den >= 8 and q("SELECT COUNT(*) n FROM audit_log WHERE resource='kurs' AND allowed=1")[0]["n"] > 0, f"Rad etilgan va ruxsat berilgan so'rovlar audit jurnalida ({den} ta rad)")

# =============================================================================================
print("== 2. Bloklar: har bir tur — tozalash, tekshiruv, XSS")
A0 = K._Assets(None)
XSS = ('<p onclick="x()">Salom <b>dunyo</b><script>alert(1)</script><img src=x onerror=alert(1)><a href="javascript:alert(1)">yomon</a>'
       '<a href="https://isft.uz" onmouseover="x">yaxshi</a><iframe src="//evil"></iframe><svg onload=alert(1)></svg><style>*{}</style></p>')
for t in K.BLOCKS:
    d = K.default_block(t)
    again = K.clean_block(t, d, A0)
    ok(isinstance(d, dict) and again == d and isinstance(K.block_issues(t, d), list), f"{t}: standart blok barqaror tozalanadi, tekshiruv ishlaydi")
def safe(h): return h is not None and PK.html_unsafe(h) is None and not re.search(r"script|onerror|onclick|onload|javascript|iframe|<svg|<img|<style", h, re.I)
cp = K.clean_block("paragraph", {"html": XSS}, A0)
ok(safe(cp["html"]) and "<b>dunyo</b>" in cp["html"] and 'href="https://isft.uz"' in cp["html"] and 'rel="noopener noreferrer"' in cp["html"], f"paragraph: XSS olib tashlandi, formatlash va https havola qoldi: {cp['html'][:120]}")
for t, d, get in (("heading_paragraph", {"heading": "<b>H</b>", "html": XSS}, lambda x: [x["html"]]),
                  ("list", {"items": [XSS, XSS]}, lambda x: x["items"]), ("accordion", {"items": [{"title": "<i>t</i>", "html": XSS}]}, lambda x: [i["html"] for i in x["items"]]),
                  ("tabs", {"items": [{"title": "t", "html": XSS}]}, lambda x: [i["html"] for i in x["items"]]),
                  ("process", {"items": [{"title": "t", "html": XSS}]}, lambda x: [i["html"] for i in x["items"]]),
                  ("timeline", {"items": [{"date": "1990", "title": "t", "html": XSS}]}, lambda x: [i["html"] for i in x["items"]]),
                  ("image_text", {"html": XSS}, lambda x: [x["html"]]), ("labeled_graphic", {"markers": [{"x": 150, "y": -5, "title": "m", "html": XSS}]}, lambda x: [m["html"] for m in x["markers"]])):
    c = K.clean_block(t, d, A0)
    ok(all(safe(h) for h in get(c)), f"{t}: HTML maydonlari tozalangan")
ok(K.clean_block("heading_paragraph", {"heading": "<b>H</b><script>x</script>"}, A0)["heading"] == "<b>H</b><script>x</script>"[:300].replace("\x00", ""), "Oddiy matn maydoni HTML sifatida emas, matn sifatida saqlanadi (pleyer escape qiladi)")
lg = K.clean_block("labeled_graphic", {"markers": [{"x": 150, "y": -5}] * 25}, A0)
ok(len(lg["markers"]) == 20 and lg["markers"][0]["x"] == 100 and lg["markers"][0]["y"] == 0, "labeled_graphic: belgilar 0–100% oralig'ida, ko'pi bilan 20 ta")
ok(K.clean_block("button", {"label": "Ochish", "url": "javascript:alert(1)"}, A0)["url"] == "" and K.clean_block("button", {"url": "https://isft.uz/a"}, A0)["url"] == "https://isft.uz/a"
   and ("xato", "Havola (https://…) kiritilmagan") in K.block_issues("button", K.clean_block("button", {"url": "data:text/html,x"}, A0)), "button: faqat http(s) havola; javascript:/data: — rad")
vy = K.clean_block("video", {"source": "youtube", "youtube": "https://youtu.be/dQw4w9WgXcQ?t=42"}, A0)
ok(vy["yt_id"] == "dQw4w9WgXcQ" and vy["yt_start"] == 42 and K.clean_block("video", {"source": "youtube", "youtube": "https://evil.com/watch?v=dQw4w9WgXcQ"}, A0)["yt_id"] is None,
   "video: YouTube havolasi → ID + boshlanish; boshqa domen — rad")
ok(K.clean_block("video", {"source": "file", "asset": 999999}, A0)["asset"] is None and K.clean_block("image", {"asset": "1; DROP"}, A0)["asset"] is None, "Asset: begona/mavjud bo'lmagan fayl id — None")
kn = K.clean_block("knowledge", {"kind": "single", "question": "S?", "answers": [{"text": "a", "correct": True}, {"text": "b", "correct": True}]}, A0)
ok([a["correct"] for a in kn["answers"]] == [True, False], "knowledge (bitta javob): ikkita to'g'ri belgilansa — faqat birinchisi")
tf = K.clean_block("knowledge", {"kind": "truefalse", "question": "S?", "answers": [{"text": "x", "correct": False}]}, A0)
ok([a["text"] for a in tf["answers"]] == K.TF and [a["correct"] for a in tf["answers"]] == [False, True], "knowledge (to'g'ri/noto'g'ri): variantlar me'yorlanadi")
mr1 = K.clean_block("question", {"kind": "multiple", "question": "S?", "answers": [{"text": "a", "correct": True}, {"text": "b"}]}, A0)
ok(("ogoh", "«Bir nechta javob» savolida bitta to'g'ri javob — «Bitta javob» turini tanlang") in K.block_issues("question", mr1), "«Bir nechta javob» + bitta to'g'ri — ogohlantirish")
ok(("xato", "To'g'ri javob belgilanmagan") in K.block_issues("question", K.clean_block("question", {"question": "S?", "answers": [{"text": "a"}, {"text": "b"}]}, A0)), "To'g'ri javobsiz savol — xato")
fl = K.clean_block("question", {"kind": "fill", "question": "S?", "accept": ["  bozor ", "", "x" * 300] + ["y"] * 20}, A0)
ok(fl["accept"][0] == "bozor" and len(fl["accept"]) == 10 and len(fl["accept"][1]) == 200 and fl["answers"] == [], "fill: javoblar tozalanadi, ≤10 ta, ≤200 belgi")
so = K.clean_block("sorting", {"categories": ["A", "B"], "items": [{"text": "x", "cat": 7}, {"text": "y", "cat": -2}]}, A0)
ok([i["cat"] for i in so["items"]] == [1, 0] and ("xato", "Kamida 2 ta toifa kerak") in K.block_issues("sorting", K.clean_block("sorting", {"categories": ["A"]}, A0)), "sorting: toifa indeksi chegaralanadi, kamida 2 toifa")
ok(("xato", "Kamida 2 ta to'liq juft kerak") in K.block_issues("matching", K.clean_block("matching", {"pairs": [{"left": "a", "right": ""}]}, A0)), "matching: kamida 2 ta to'liq juft")
tb = K.clean_block("table", {"rows": [["a", "b", "c"]] + [["x"]] * 70}, A0)
ok(len(tb["rows"]) == 50 and all(len(r) == 3 for r in tb["rows"]), "table: ≤50 qator, qatorlar bir xil kenglikka keltiriladi")
ok(K.clean_block("heading", {"text": "x" * 500, "level": 9}, A0) == {"text": "x" * 300, "level": 3}, "heading: uzunlik va daraja chegaralangan")
ok(("ogoh", "Rasm uchun muqobil matn (alt) yozilmagan — ko'zi ojiz talabalar uchun kerak") in K.block_issues("image", {"asset": 1, "alt": "", "caption": "", "layout": "hero"}), "image: alt bo'sh — ogohlantirish")
try: K.clean_block("hotspot", {}, A0); ok(False, "Noma'lum blok turi qabul qilindi")
except PK.HTTPException as e: ok(e.status_code == 400, "Noma'lum blok turi — 400")
# HTTP orqali saqlash
L = head.get(f"{P}/lessons/{hl}").json()
r = head.post(f"{P}/lessons/{hl}", json={"rev": L["rev"], "title": "Birinchi dars", "blocks": [{"id": "bxss000001", "type": "paragraph", "data": {"html": XSS}},
                                                                                         {"type": "heading", "data": {"text": "Sarlavha"}}]})
ok(r.status_code == 200 and safe(r.json()["blocks"][0]["data"]["html"]) and r.json()["blocks"][0]["id"] == "bxss000001" and K._UID_RX.match(r.json()["blocks"][1]["id"]),
   "HTTP saqlash: HTML serverda tozalanadi; blok id saqlanadi / yaratiladi")
stored = q("SELECT data FROM ku_blocks b JOIN ku_lessons l ON l.id=b.lesson_id WHERE l.id=? ORDER BY b.pos", (hl,))
ok(stored and safe(json.loads(stored[0]["data"])["html"]), "Bazada ham tozalangan HTML")
rv = r.json()["rev"]
ok(head.post(f"{P}/lessons/{hl}", json={"rev": rv, "blocks": [{"type": "hotspot", "data": {}}]}).status_code == 400, "Noma'lum turdagi blok — 400")
ok(head.post(f"{P}/lessons/{hl}", json={"rev": rv, "blocks": [{"type": "question", "data": {}}]}).status_code == 400, "Oddiy darsda «question» bloki — 400")
ok(head.post(f"{P}/lessons/{hl}", json={"rev": rv, "blocks": "x"}).status_code == 400 and head.post(f"{P}/lessons/{hl}", content=b"{bad json").status_code == 400, "Noto'g'ri tana — 400")
ok(head.post(f"{P}/lessons/{hl}", json={"rev": rv, "blocks": [{"type": "paragraph", "data": {}}] * (K.MAX_BLOCKS + 1)}).status_code == 400, f"{K.MAX_BLOCKS} tadan ortiq blok — 400")

# =============================================================================================
print("== 3. Avtosaqlash ziddiyati (rev)")
r1 = head.post(f"{P}/lessons/{hl}", json={"rev": rv, "title": "Birinchi dars", "blocks": [{"type": "paragraph", "data": {"html": "<p>A oyna</p>"}}]})
ok(r1.status_code == 200 and r1.json()["rev"] == rv + 1, "Joriy rev bilan saqlash — 200, rev +1")
r2 = staff.post(f"{P}/lessons/{hl}", json={"rev": rv, "blocks": [{"type": "paragraph", "data": {"html": "<p>B oyna</p>"}}]})
det = r2.json().get("detail") or {}
ok(r2.status_code == 409 and det.get("conflict") and det.get("rev") == rv + 1 and "Oxirgi holatni" in det.get("message", ""), "Eski rev bilan saqlash — 409 (ziddiyat, joriy rev va kim o'zgartirgani)")
ok("A oyna" in head.get(f"{P}/lessons/{hl}").json()["blocks"][0]["data"]["html"], "Ziddiyatda hech narsa yozilmadi")
nv = len(head.get(f"{P}/courses/{hc}/versions").json()["items"])
r3 = staff.post(f"{P}/lessons/{hl}", json={"rev": rv, "force": True, "blocks": [{"type": "paragraph", "data": {"html": "<p>B oyna</p>"}}]})
vs = head.get(f"{P}/courses/{hc}/versions").json()["items"]
ok(r3.status_code == 200 and "B oyna" in r3.json()["blocks"][0]["data"]["html"] and len(vs) > nv and any("ziddiyatda" in (v["note"] or "") for v in vs),
   "force — ustidan yoziladi, oldingi holat versiya sifatida saqlanadi")
co = head.get(f"{P}/courses/{hc}").json()
ok(head.post(f"{P}/courses/{hc}/settings", json={"rev": co["rev"] - 1, "title": "x"}).status_code == 409, "Kurs sozlamalari: eski rev — 409")
ok(head.post(f"{P}/courses/{hc}/order", json={"order": [x["id"] for x in co["lessons_list"]], "rev": co["rev"] - 1}).status_code == 409, "Darslar tartibi: eski rev — 409")

# =============================================================================================
print("== 4. Versiyalar va tiklash")
cur = head.get(f"{P}/lessons/{hl}").json()
sv = head.post(f"{P}/courses/{hc}/versions", json={"note": "Toza holat"}).json()
vid = sv["id"]
head.post(f"{P}/lessons/{hl}", json={"rev": cur["rev"], "title": "O'zgargan dars", "blocks": [{"type": "heading", "data": {"text": "Yangi"}}]})
nl = head.post(f"{P}/courses/{hc}/lessons", json={"type": "quiz"}).json()
ok(len(nl["course"]["lessons_list"]) == 2 and nl["course"]["lessons_list"][1]["type"] == "quiz", "Test darsi qo'shildi")
rs = head.post(f"{P}/courses/{hc}/versions/{vid}/restore", json={}).json()
ls = rs["course"]["lessons_list"]
lb = head.get(f"{P}/lessons/{ls[0]['id']}").json()
ok(len(ls) == 1 and ls[0]["title"] == "Birinchi dars" and lb["blocks"][0]["type"] == "paragraph" and "B oyna" in lb["blocks"][0]["data"]["html"], "Tiklash: darslar va bloklar versiyadagi holatga qaytdi")
vs = head.get(f"{P}/courses/{hc}/versions").json()["items"]
pre = next((v for v in vs if "tiklanishidan oldingi" in (v["note"] or "")), None)
ok(pre is not None and pre["lessons"] == 2, "Tiklashdan oldingi holat (2 dars) ham versiya sifatida saqlandi")
ok(teach.post(f"{P}/courses/{hc}/versions/{vid}/restore", json={}).status_code == 403, "O'qituvchi begona kurs versiyasini tiklamaydi (403)")
hl = ls[0]["id"]

# =============================================================================================
print("== 5. Fayllar")
up = head.post(f"{P}/courses/{hc}/assets?kind=image&name=rasm.png", content=png(2400, 1200))
img = up.json()
ok(up.status_code == 200 and img["kind"] == "image" and img["meta"]["w"] == 1600 and img["ext"] == "png", "Rasm yuklandi va 1600px gacha kichraytirildi")
ok(head.post(f"{P}/courses/{hc}/assets?kind=image&name=x.png", content=b"<svg onload=alert(1)>" + b" " * 100).status_code == 415, "SVG / matn — rasm sifatida qabul qilinmaydi (415)")
ok(head.post(f"{P}/courses/{hc}/assets?kind=video&name=v.mp4", content=b"not a video" * 20).status_code == 415, "Video emas — 415 (tur birinchi baytlardan)")
ok(head.post(f"{P}/courses/{hc}/assets?kind=file&name=x.exe", content=b"MZ" + b"\x00" * 200).status_code == 415, "Ilova: .exe — 415")
vt = head.post(f"{P}/courses/{hc}/assets?kind=vtt&name=s.srt&lang=uz", content="1\n00:00:01,000 --> 00:00:02,000\nSalom\n".encode())
ok(vt.status_code == 200 and vt.json()["meta"]["cues"] == 1, "Subtitr (.srt → WebVTT) yuklandi")
ok(head.get(f"{P}/assets/{img['id']}").status_code == 200 and teach.get(f"{P}/assets/{img['id']}").status_code == 403, "Fayl: bo'lim ko'radi, begona o'qituvchi — 403")
ok(teach.post(f"{P}/courses/{hc}/assets?kind=image&name=x.png", content=png()).status_code == 403, "O'qituvchi begona kursga fayl yuklamaydi (403)")
# begona kurs fayliga havola blokda saqlanmaydi
timg = teach.post(f"{P}/courses/{tc}/assets?kind=image&name=t.png", content=png()).json()["id"]
L = head.get(f"{P}/lessons/{hl}").json()
r = head.post(f"{P}/lessons/{hl}", json={"rev": L["rev"], "blocks": L["blocks"] + [{"type": "image", "data": {"asset": timg, "alt": "x"}}, {"type": "image", "data": {"asset": img["id"], "alt": "Qizil to'rtburchak"}}]}).json()
ok(r["blocks"][-2]["data"]["asset"] is None and r["blocks"][-1]["data"]["asset"] == img["id"], "Boshqa kurs fayli blokka ulanmaydi (None), o'z fayli — ulanadi")

# =============================================================================================
print("== 6. Ko'rish (preview)")
pv = head.get(f"{P}/courses/{hc}/preview-url").json()["url"]
ok(re.fullmatch(r"/api/kurs/pv/\d+\.\d+\.\d+\.[0-9a-f]{40}/index\.html\?preview=1", pv) is not None, "Imzolangan ko'rish havolasi")
base = pv.split("index.html")[0]
pi = httpx.get(B + pv)
ok(pi.status_code == 200 and "script-src 'self'" in pi.headers.get("content-security-policy", "") and "sandbox" in pi.headers.get("content-security-policy", ""), "index.html — qat'iy CSP (sandbox, script-src 'self')")
cj = httpx.get(B + base + "content.js")
ok(cj.status_code == 200 and cj.text.startswith("window.KURS = ") and "B oyna" in cj.text and cj.headers.get("cache-control") == "no-store", "content.js — joriy (avtosaqlangan) holat, keshlanmaydi")
asrc = json.loads(cj.text[len("window.KURS = "):-1])["lessons"][0]["blocks"][-1]["src"]
ok(httpx.get(B + base + asrc).status_code == 200 and httpx.get(B + base + "assets/img/999999-x.png").status_code == 404, "Asset ko'rishda beriladi; yo'q fayl — 404")
ok(httpx.get(B + base + "lms.js").status_code == 200 and httpx.get(B + base + "player.js").status_code == 200, "Pleyer fayllari (player.js + umumiy lms.js)")
bad = re.sub(r"\.[0-9a-f]{40}/", "." + "0" * 40 + "/", pv)
ok(httpx.get(B + bad).status_code == 403 and httpx.get(B + base + "../../x").status_code in (400, 404), "Soxta imzo — 403; «..» yo'li — rad")

# =============================================================================================
print("== 7. Ko'rib chiqish oqimi")
ok(teach.post(f"{P}/courses/{hc}/action", json={"action": "approve"}).status_code == 403, "O'qituvchi tasdiqlay olmaydi (403)")
tlid = teach.get(f"{P}/courses/{tc}").json()["lessons_list"][0]["id"]
TL = teach.get(f"{P}/lessons/{tlid}").json()
teach.post(f"{P}/lessons/{tlid}", json={"rev": TL["rev"], "blocks": [{"type": "knowledge", "data": {"kind": "single", "question": "", "answers": [{"text": "a"}, {"text": "b"}]}}]})
r = teach.post(f"{P}/courses/{tc}/action", json={"action": "submit"})
ok(r.status_code == 400 and r.json()["detail"]["errors"], "Xatoli kurs (savol bo'sh) yuborilmaydi — 400 va xatolar ro'yxati")
TL = teach.get(f"{P}/lessons/{tlid}").json()
teach.post(f"{P}/lessons/{tlid}", json={"rev": TL["rev"], "blocks": [{"type": "knowledge", "data": {"kind": "single", "question": "2+2?", "answers": [{"text": "4", "correct": True}, {"text": "5"}]}}]})
r = teach.post(f"{P}/courses/{tc}/action", json={"action": "submit"})
ok(r.status_code == 200 and r.json()["course"]["status"] == "korib_chiqishda", "O'qituvchi kursni ko'rib chiqishga yubordi")
ok(head.post(f"{P}/courses/{tc}/action", json={"action": "return"}).status_code == 400, "Qaytarish sababsiz — 400")
TL = teach.get(f"{P}/lessons/{tlid}").json()
teach.post(f"{P}/lessons/{tlid}", json={"rev": TL["rev"], "title": "Tahrir", "blocks": TL["blocks"]})
ok(teach.get(f"{P}/courses/{tc}").json()["status"] == "qoralama", "Ko'rib chiqishdagi kursni o'qituvchi o'zgartirsa — qoralamaga qaytadi")
teach.post(f"{P}/courses/{tc}/action", json={"action": "submit"})
ra = head.post(f"{P}/courses/{tc}/action", json={"action": "approve", "note": "Yaxshi"}).json()["course"]
ok(ra["status"] == "tasdiqlangan" and ra["approved_name"] and any(v["approved"] for v in head.get(f"{P}/courses/{tc}/versions").json()["items"]), "Bo'lim tasdiqladi — tasdiqlangan versiya saqlandi")
TL = teach.get(f"{P}/lessons/{tlid}").json()
teach.post(f"{P}/lessons/{tlid}", json={"rev": TL["rev"], "blocks": TL["blocks"]})
c2 = teach.get(f"{P}/courses/{tc}").json()
ok(c2["status"] == "qoralama" and "qayta yuborish" in c2["status_note"], "Tasdiqlangan kurs o'zgartirilsa — qoralamaga qaytadi (izoh bilan)")

# =============================================================================================
print("== 8. Test baholash qoidasi (pleyer bilan bir xil)")
Q1 = {"id": "q1", "kind": "single", "answers": [{"text": "a"}, {"text": "b", "correct": True}]}
Q2 = {"id": "q2", "kind": "multiple", "answers": [{"text": "a", "correct": True}, {"text": "b"}, {"text": "c", "correct": True}]}
Q3 = {"id": "q3", "kind": "truefalse", "answers": [{"text": "To'g'ri", "correct": False}, {"text": "Noto'g'ri", "correct": True}]}
Q4 = {"id": "q4", "kind": "fill", "accept": ["O‘zbekiston", "UZ"]}
ok(K.grade(Q1, [1]) and not K.grade(Q1, [0]) and not K.grade(Q1, [0, 1]) and not K.grade(Q1, []), "Bitta javob: faqat to'g'ri variant; ikki tanlov — noto'g'ri")
ok(K.grade(Q2, [2, 0]) and not K.grade(Q2, [0]) and not K.grade(Q2, [0, 1, 2]), "Bir nechta javob: aynan to'g'ri to'plam (qisman — noto'g'ri)")
ok(K.grade(Q3, [1]) and not K.grade(Q3, [0]), "To'g'ri / noto'g'ri")
ok(K.grade(Q4, "  o'zbekiston. ") and K.grade(Q4, "OʻZBEKISTON") and K.grade(Q4, "«uz»") and not K.grade(Q4, "o zbekiston"), "Bo'sh joy: katta-kichik harf, apostrof variantlari, chetdagi tinish belgilari")
sc = K.score_quiz([Q1, Q2, Q3, Q4], {"q1": [1], "q2": [0, 2], "q3": [0], "q4": "uz"}, 75)
ok(sc == {"correct": 3, "total": 4, "pct": 75, "passed": True} and not K.score_quiz([Q1, Q2], {"q1": [1]}, 60)["passed"], f"Ball va o'tish chegarasi: {sc}")

# =============================================================================================
print("== 9. Eksport: SCORM 1.2, SCORM 2004, xAPI, HTML")
demo = q("SELECT id FROM ku_courses WHERE src='demo' AND deleted=0 ORDER BY id LIMIT 1")
ok(bool(demo), "Namuna kurs (barcha blok turlari) mavjud")
dc = demo[0]["id"]
dco = head.get(f"{P}/courses/{dc}").json()
dtypes = {b["type"] for l in dco["lessons_list"] for b in head.get(f"{P}/lessons/{l['id']}").json()["blocks"]}
ok(dtypes >= (set(K.LESSON_BLOCKS) - {"video", "audio", "attachment"}) | {"question"}, f"Namuna kurs barcha blok turlarini o'z ichiga oladi (video/audio/fayl — media faylsiz): {len(dtypes)} tur")
TCN = "{http://projecttincan.com/tincan.xsd}"
zips = {}
for mode in ("scorm12", "scorm2004", "xapi", "none"):
    r = head.post(f"{P}/courses/{dc}/export", json={"mode": mode})
    e = r.json() if r.status_code == 200 else {}
    data = head.get(e.get("download", "/x")).content if e else b""
    zips[mode] = data
    v = PK.validate_zip(data) if data else {"ok": False, "errors": [r.text[:200]]}
    ok(r.status_code == 200 and e["validation"]["ok"] and v["ok"] and v["mode"] == mode and e["sha256"] == hashlib.sha256(data).hexdigest(),
       f"{mode}: eksport validate_zip dan o'tdi (serverda va qayta tekshiruvda), {len(data) // 1024} KB" + ("" if v["ok"] else f" — {v['errors'][:3]}"))
z = zipfile.ZipFile(io.BytesIO(zips["xapi"]))
names = set(z.namelist())
ok({"index.html", "player.js", "player.css", "lms.js", "content.js", "content.json", "tincan.xml"} <= names and any(n.startswith("fonts/") for n in names)
   and "imsmanifest.xml" not in names, "xAPI: pleyer, umumiy lms.js, shriftlar, content.js/json, tincan.xml")
ok({"scormdriver/indexAPI.html", "scormdriver/indexAPI.js"} <= names and "../index.html" in z.read("scormdriver/indexAPI.js").decode()
   and not any(n.startswith("scormdriver/") for m_ in ("scorm12", "scorm2004", "none") for n in zipfile.ZipFile(io.BytesIO(zips[m_])).namelist()),
   "xAPI: scormdriver/indexAPI.html → ../index.html (NEXTID launch yo'li, Rise kabi); SCORM/HTML eksportida yo'q")
root = ET.fromstring(z.read("tincan.xml")); acts = root.findall(f"{TCN}activities/{TCN}activity")
cont = json.loads(z.read("content.json"))
ok(acts[0].get("id") == f"https://isft.uz/xapi/kurs/{dc}" and acts[0].find(f"{TCN}launch").text == "scormdriver/indexAPI.html"
   and sum(1 for a in acts if a.get("type").endswith("/module")) == sum(1 for l in cont["lessons"] if l["type"] == "blocks")
   and any(a.get("type").endswith("/assessment") for a in acts)
   and sum(1 for a in acts if a.get("type").endswith("cmi.interaction")) == sum(len(l.get("questions") or []) for l in cont["lessons"]) + sum(1 for l in cont["lessons"] for b in l.get("blocks") or [] if b["type"] == "knowledge"),
   f"tincan.xml: kurs (launch), har dars (module/assessment), har savol va bilimni tekshirish — cmi.interaction ({len(acts)} faoliyat)")
inter = [a for a in acts if a.get("type").endswith("cmi.interaction")]
ok(all(a.get("id").startswith(f"https://isft.uz/xapi/kurs/{dc}/lesson/") and "/q/" in a.get("id") and a.find(f"{TCN}interactionType") is not None for a in inter)
   and any(a.find(f"{TCN}choices") is not None for a in inter), "Savol faoliyatlari: /lesson/<dars>/q/<savol>, interactionType, choices, correctResponsePattern")
ok(cont["v"] == 1 and cont["kind"] == "kurs" and cont["tracking"]["mode"] == "xapi" and cont["labels"]["continue"] == "Davom etish" and z.read("content.js").startswith(b"window.KURS = "),
   "content.js — window.KURS, o'zbekcha yorliqlar")
z12 = zipfile.ZipFile(io.BytesIO(zips["scorm12"])); m12 = z12.read("imsmanifest.xml").decode()
ok("<schemaversion>1.2</schemaversion>" in m12 and 'adlcp:scormtype="sco"' in m12 and "tincan.xml" not in z12.namelist(), "SCORM 1.2 manifest")
ok("2004 4th Edition" in zipfile.ZipFile(io.BytesIO(zips["scorm2004"])).read("imsmanifest.xml").decode(), "SCORM 2004 4-nashr manifest")
ok({"imsmanifest.xml", "tincan.xml"}.isdisjoint(zipfile.ZipFile(io.BytesIO(zips["none"])).namelist()), "Oddiy HTML — manifestsiz")
r2 = head.post(f"{P}/courses/{dc}/export", json={"mode": "xapi"}).json()
ok(r2["sha256"] == hashlib.sha256(zips["xapi"]).hexdigest(), "Deterministik: o'zgarishsiz qayta eksport — bir xil sha256")
# completion = quiz → SCORM mastery
co = head.get(f"{P}/courses/{dc}").json()
head.post(f"{P}/courses/{dc}/settings", json={"rev": co["rev"], "settings": {"completion": "view_and_quiz"}})
e12 = head.post(f"{P}/courses/{dc}/export", json={"mode": "scorm12"}).json()
m12 = zipfile.ZipFile(io.BytesIO(head.get(e12["download"]).content)).read("imsmanifest.xml").decode()
ok(e12["validation"]["ok"] and "<adlcp:masteryscore>80</adlcp:masteryscore>" in m12, "Yakunlash «ko'rilganda va test» — SCORM 1.2 masteryscore = testning o'tish bali")
co = head.get(f"{P}/courses/{dc}").json()
head.post(f"{P}/courses/{dc}/settings", json={"rev": co["rev"], "settings": {"completion": "view"}})
# xatoli kurs eksport qilinmaydi
ok(head.post(f"{P}/courses/{hc}/export", json={"mode": "xapi"}).status_code == 400, "Xatoli kurs (rasmsiz blok) eksport qilinmaydi — 400")
ok(head.post(f"{P}/courses/{dc}/export", json={"mode": "pdf"}).status_code == 400, "Noma'lum eksport turi — 400")
# validator: buzilgan kontent
zn = zipfile.ZipFile(io.BytesIO(zips["none"])); bad = {n: zn.read(n) for n in zn.namelist()}
cj = json.loads(bad["content.js"].decode()[len("window.KURS = "):-1])
cj["lessons"][0]["blocks"].append({"id": "bevil00001", "type": "paragraph", "html": "<p onclick=x>a</p>"})
cj["lessons"][0]["blocks"].append({"id": "bevil00002", "type": "image", "src": "../../etc/passwd", "alt": ""})
bad["content.js"] = ("window.KURS = " + json.dumps(cj) + ";").encode()
vb = PK.validate_zip(PK.zip_bytes(bad))
ok(not vb["ok"] and any("xavfli HTML" in x for x in vb["errors"]) and any("noto'g'ri yo'l" in x for x in vb["errors"]), "validate_zip (window.KURS): xavfli HTML va «..» yo'l aniqlanadi")

# =============================================================================================
print("== 10. Test bankdan savollar")
tbh = head.get(P + "/testbank").json()
tbt = teach.get(P + "/testbank").json()
tids = {r["id"] for r in q("SELECT id FROM dl_courses WHERE teacher_id=?", (teach_tid,))}
ok(len(tbh["items"]) > 0 and all(x["course_id"] in tids for x in tbt["items"]), f"Faqat tasdiqlangan savollar; o'qituvchi — o'z fanlari ({len(tbh['items'])} / {len(tbt['items'])})")
pick = {}
for r in q("SELECT id, qtype FROM tb_questions WHERE status='tasdiqlandi' AND deleted=0 ORDER BY id"): pick.setdefault(r["qtype"], r["id"])
cv = head.post(P + "/testbank/convert", json={"ids": list(pick.values())}).json()["questions"]
kinds = {next(k for k, v in pick.items() if v == x["tb_id"]): x["data"]["kind"] for x in cv}
ok(kinds.get("mcq") in ("single", "multiple") and kinds.get("tf", "truefalse") == "truefalse" and kinds.get("fill", "fill") == "fill"
   and all(not K.block_issues("question", x["data"]) or all(l == "ogoh" for l, _ in K.block_issues("question", x["data"])) for x in cv),
   f"Test bank → savol: mcq → {kinds.get('mcq')}, tf → truefalse, fill → fill; xatosiz")
draft = q("SELECT id FROM tb_questions WHERE status<>'tasdiqlandi' LIMIT 1")
ok(not draft or head.post(P + "/testbank/convert", json={"ids": [draft[0]["id"]]}).json()["questions"] == [], "Tasdiqlanmagan savol qo'shilmaydi")

# =============================================================================================
print("== 11. Rise importi: sintetik namuna (tests/fixtures/rise_sample)")
n0 = q("SELECT COUNT(*) n FROM ku_courses WHERE deleted=0")[0]["n"]
r = teach.post(P + "/import/rise?name=namuna.zip", content=zip_dir(FIX))
d = r.json(); R = d.get("report", {})
ok(r.status_code == 200 and R["lessons"] == 3 and R["quiz_lessons"] == 1 and R["questions"] == 3 and R["blocks"] == 21, f"Import: 3 dars, 1 test (3 savol), 21 blok ({R.get('blocks')})")
ok(R["by_type"] == {"accordion": 1, "continue": 2, "flashcards": 1, "heading": 1, "heading_paragraph": 1, "image": 2, "knowledge": 4, "list": 1, "paragraph": 3,
                    "process": 1, "question": 3, "quote": 1, "sorting": 1, "tabs": 1, "timeline": 1}, f"Bloklar turlari bo'yicha: {R['by_type']}")
ok(R["unmapped"] == {"interactive/scenario": 1, "lesson/section": 1} and R["images"] == {"imported": 3, "missing": 0, "failed": 0} and R["format"] == "xAPI",
   "Import qilinmaganlar (ssenariy, bo'lim sarlavhasi), 3 ta rasm, format xAPI")
ic = d["course_id"]
ic_v = teach.get(f"{P}/courses/{ic}").json()
ok(ic_v["src"] == "rise" and ic_v["author_id"] == teach_uid and ic_v["status"] == "qoralama" and ic_v["accent"] == "#C2410C" and ic_v["cover"], "Qoralama kurs: muallif — import qilgan o'qituvchi, urg'u rangi palitraga (#ff631e → #C2410C), muqova")
blocks1 = teach.get(f"{P}/lessons/{ic_v['lessons_list'][0]['id']}").json()["blocks"]
un = [b for b in blocks1 if b["type"] == "paragraph" and "import qilinmadi: interactive/scenario" in b["data"]["html"]]
ok(len(un) == 1 and "Sotuvchi bilan suhbat" in un[0]["data"]["html"], "Noma'lum blok — «import qilinmadi: interactive/scenario» izohli matn bloki (matni bilan)")
ok(all("<script" not in json.dumps(b["data"]) for b in blocks1) and next(b for b in blocks1 if b["type"] == "heading_paragraph")["data"]["html"].startswith("<p>Bozor"), "Import HTML'i tozalangan")
quiz = teach.get(f"{P}/lessons/{ic_v['lessons_list'][3]['id']}").json()
ok(quiz["type"] == "quiz" and quiz["quiz"]["pass_pct"] == 70 and quiz["quiz"]["attempts"] == 2 and quiz["quiz"]["shuffle"] is False
   and [b["data"]["kind"] for b in quiz["blocks"]] == ["single", "multiple", "fill"] and quiz["blocks"][2]["data"]["accept"] == ["bozor"], "Test: o'tish 70%, 2 urinish, savol turlari, bo'sh joy javobi")
Qr = d["quality"]
ok(Qr["knowledge"]["total"] == 4 and Qr["knowledge"]["positions"] == {"B": 4} and Qr["knowledge"]["longest"] == 4 and Qr["knowledge"]["flag_pos"],
   "Sifat: bilimni tekshirish — 4/4 to'g'ri javob «B» o'rnida, 4/4 eng uzun")
ok(Qr["images"]["total"] == 2 and Qr["images"]["missing_alt"] == 2 and Qr["images"]["cover_missing_alt"], "Sifat: 2/2 rasm alt matnsiz, muqova alt'siz")
ok(Qr["english_count"] == 5 and {e["text"] for e in Qr["english"]} >= {"Quiz", "Expand each tab to explore the main ideas of this lesson."}, f"Sifat: {Qr['english_count']} ta inglizcha yorliq (Continue, Quiz, Expand each…)")
ok(Qr["coverage"]["covered"] == "1–2" and [u["no"] for u in Qr["coverage"]["uncovered"]] == [3] and Qr["mr_single"] == 1, "Sifat: test 1–2-darslarni qamraydi (3-dars savolsiz), 1 ta «bir nechta javob»da bitta to'g'ri")
fx_set = {i["fix"] for i in Qr["issues"] if i["fix"]}
ok(fx_set >= {"shuffle", "labels", "mr_single"} and fx_set <= set(K.FIXES) and all(i.get("group") == "a11y" for i in Qr["issues"] if i["fix"] in fx_set - {"shuffle", "labels", "mr_single"}),
   f"Tuzatish takliflari: aralashtirish, yorliqlar, savol turi (+ qulaylik: {sorted(fx_set - {'shuffle', 'labels', 'mr_single'})})")
f1 = teach.post(f"{P}/courses/{ic}/fix", json={"fix": "shuffle"}).json()["quality"]
ok(max(f1["knowledge"]["positions"].values()) <= 2 and not f1["knowledge"]["flag_pos"] and all(teach.get(f"{P}/lessons/{ic_v['lessons_list'][3]['id']}").json()["quiz"]["shuffle"] for _ in [0]),
   f"«Aralashtirish»: to'g'ri javob o'rinlari teng taqsimlandi {f1['knowledge']['positions']}, testda aralashtirish yoqildi")
f2 = teach.post(f"{P}/courses/{ic}/fix", json={"fix": "labels"}).json()
ok(f2["quality"]["english_count"] == 0 and any(l["title"] == "Yakuniy test" for l in f2["course"]["lessons_list"]), "«Yorliqlarni tarjima»: inglizcha qolmadi, «Quiz» → «Yakuniy test»")
cont_b = [b for l in teach.get(f"{P}/courses/{ic}").json()["lessons_list"] if l["type"] == "blocks" for b in teach.get(f"{P}/lessons/{l['id']}").json()["blocks"] if b["type"] == "continue"]
ok(cont_b and all(b["data"]["label"] == "Davom etish" and b["data"]["hint"] == K.LABELS["complete_hint"] for b in cont_b), "«Continue» → «Davom etish», eslatma o'zbekcha")
f3 = teach.post(f"{P}/courses/{ic}/fix", json={"fix": "mr_single"}).json()["quality"]
ok(f3["mr_single"] == 0 and len(teach.get(f"{P}/courses/{ic}/versions").json()["items"]) >= 4, "«Bitta javob»ga o'tkazish; har tuzatishdan oldin versiya saqlandi")
ok(head.post(f"{P}/courses/{ic}/fix", json={"fix": "x"}).status_code == 400, "Noma'lum tuzatish — 400")
for lid in [l["id"] for l in teach.get(f"{P}/courses/{ic}").json()["lessons_list"]]:   # import qilinmagan blok va alt'siz rasmlar — eksport uchun to'ldiriladi
    L = teach.get(f"{P}/lessons/{lid}").json()
    for b in L["blocks"]:
        if b["type"] == "image": b["data"]["alt"] = "Namuna rasm"
    teach.post(f"{P}/lessons/{lid}", json={"rev": L["rev"], "blocks": L["blocks"]})
ex = teach.post(f"{P}/courses/{ic}/export", json={"mode": "xapi"}).json()
ok(ex.get("validation", {}).get("ok"), "Import qilingan kurs xAPI eksporti validate_zip dan o'tdi")
ok(q("SELECT COUNT(*) n FROM ku_courses WHERE deleted=0")[0]["n"] == n0 + 1, "Bitta kurs yaratildi")

print("== 12. Import xavfsizligi")
n0 = q("SELECT COUNT(*) n FROM ku_courses")[0]["n"]
r = head.post(P + "/import/rise?name=t.zip", content=zip_dir(FIX, {"../evil.txt": "x"}))
ok(r.status_code == 400 and "xavfli" in r.json()["detail"], "Yo'l hujumi («../evil.txt») — 400")
r = head.post(P + "/import/rise?name=t.zip", content=zip_dir(FIX, {"/etc/passwd": "x"}))
ok(r.status_code == 400, "Mutlaq yo'l («/etc/passwd») — 400")
r = head.post(P + "/import/rise?name=t.zip", content=zip_dir(FIX, {"scormcontent\\..\\x.js": "x"}))
ok(r.status_code == 400, "Teskari chiziqli yo'l — 400")
bomb = io.BytesIO()
with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zb: zb.writestr("scormcontent/assets/bomb.bin", b"\0" * (40 * 1024 * 1024))
r = head.post(P + "/import/rise?name=b.zip", content=bomb.getvalue())
ok(r.status_code == 413 and "bomba" in r.json()["detail"], f"Zip bombasi (40 MB nol, {len(bomb.getvalue()) // 1024} KB siqilgan) — 413")
ok(head.post(P + "/import/rise?name=x.zip", content=b"%PDF-1.4 " + b"x" * 200).status_code == 415, "Zip emas — 415")
r = head.post(P + "/import/rise?name=x.zip", content=zip_dir(FIX / "scormcontent" / "assets"))
ok(r.status_code == 415 and "runtime-data.js" in r.json()["detail"], "runtime-data.js yo'q zip — 415 (tushunarli xabar)")
ok(head.post(P + "/import/rise?name=x.zip", content=b"PK\x03\x04" + b"\x00" * 100).status_code == 415, "Buzilgan zip — 415")
ok(rek.post(P + "/import/rise?name=x.zip", content=zip_dir(FIX)).status_code == 403, "Rektor import qilmaydi (403)")
ok(q("SELECT COUNT(*) n FROM ku_courses")[0]["n"] == n0, "Rad etilgan importlardan kurs yaratilmadi")
leftover = list((Path(os.environ.get("ISFT_CORE_DATA_DIR") or DBP.parent) / "kurs" / "tmp").glob("imp_*"))
ok(not leftover, f"Vaqtinchalik import fayllari o'chirildi ({len(leftover)})")

print("== 13. Rise importi: haqiqiy eksport papkasi")
if not (REAL / "scormcontent" / "runtime-data.js").is_file():
    print(f"  – {REAL} topilmadi — o'tkazib yuborildi")
else:
    r = head.post(P + "/import/rise?name=xalqaro.zip", content=zip_dir(REAL))
    d = r.json(); R = d.get("report", {}); Qr = d.get("quality", {})
    print("    hisobot:", json.dumps({k: R.get(k) for k in ("lessons", "quiz_lessons", "questions", "blocks", "by_type", "unmapped", "images")}, ensure_ascii=False))
    ok(r.status_code == 200 and R["lessons"] == 13 and R["quiz_lessons"] == 1 and R["questions"] == 8 and R["unmapped_total"] == 0 and R["images"]["imported"] == 48,
       f"Haqiqiy kurs: 13 dars, 1 test (8 savol), {R.get('blocks')} blok, import qilinmagan 0, 48 rasm")
    ok(Qr["knowledge"]["total"] == 104 and Qr["knowledge"]["positions"].get("B") == 87 and Qr["knowledge"]["longest"] == 88, "Sifat: 87/104 to'g'ri javob «B» o'rnida, 88/104 eng uzun")
    ok(Qr["images"]["missing_alt"] == 47 and Qr["images"]["total"] == 47 and Qr["english_count"] >= 29 and Qr["mr_single"] == 2, f"Sifat: 47/47 rasm alt'siz, {Qr['english_count']} inglizcha yorliq, 2 ta «bir nechta javob»da bitta to'g'ri")
    cov = {l["no"] for l in Qr["coverage"]["lessons"] if l["questions"]}
    ok(cov and cov <= {1, 2, 3, 4, 5} and {u["no"] for u in Qr["coverage"]["uncovered"]} >= set(range(6, 14)), f"Test qamrovi: {Qr['coverage']['covered']}-darslar (6–13-darslar savolsiz)")

# =============================================================================================
print("== 13a. Qulaylik qoidalari (sof funksiyalar, har qoida uchun fixture)")
def mkpdf(text: str) -> bytes:
    """Kichik haqiqiy PDF: matnli (BT … Tj) yoki faqat chizma (skaner o'xshatmasi — matn qatlamisiz)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"]
    cs = (b"BT /F1 18 Tf 20 100 Td (%s) Tj ET" % text.encode()) if text else b"0 0 1 rg 10 10 100 100 re f"
    objs += [b"<< /Length %d >>\nstream\n" % len(cs) + cs + b"\nendstream", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1): offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out); out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
def a11y(blocks, course=None, pdf=None):
    data = {"course": {"accent": "#870037", "settings": {}, "cover_asset": None, **(course or {})},
            "lessons": [{"uid": "lx", "type": "blocks", "title": "Dars", "blocks": [{"uid": k + 1, "type": t, "data": d} for k, (t, d) in enumerate(blocks)]}]}
    return {r["key"]: r for r in K.a11y_from(data, pdf)["rules"]}
long_p = "<p>" + " ".join(["so'z"] * 320) + "</p>"
CASES = [   # (qoida, muammoli bloklar, to'g'ri bloklar)
    ("alt", [("image", {"asset": 1, "alt": ""})], [("image", {"asset": 1, "alt": "Bino surati"})]),
    ("headings", [("heading", {"text": "Ichki", "level": 3})], [("heading", {"text": "Bo'lim", "level": 2}), ("heading", {"text": "Ichki", "level": 3})]),
    ("headings", [("paragraph", {"html": "<h2>A</h2><h4>B</h4>"})], [("paragraph", {"html": "<h2>A</h2><h3>B</h3>"})]),
    ("links", [("paragraph", {"html": '<p><a href="https://lex.uz">bu yerga bosing</a></p>'})], [("paragraph", {"html": '<p><a href="https://lex.uz">Konstitutsiya matni (lex.uz)</a></p>'})]),
    ("links", [("paragraph", {"html": '<p><a href="https://lex.uz">https://lex.uz/docs/1</a></p>'})], [("button", {"label": "Mehnat kodeksini ochish", "url": "https://lex.uz"})]),
    ("links", [("button", {"label": "Batafsil", "url": "https://lex.uz"})], [("button", {"label": "Batafsil", "url": ""})]),
    ("tables", [("table", {"header": False, "rows": [["a", "b"], ["1", "2"]]})], [("table", {"header": True, "rows": [["a", "b"], ["1", "2"]]})]),
    ("tables", [("paragraph", {"html": "<table><tr><td>a</td></tr></table>"})], [("paragraph", {"html": "<table><tr><th>a</th></tr></table>"})]),
    ("captions", [("video", {"source": "file", "asset": 7, "captions": []})], [("video", {"source": "file", "asset": 7, "captions": [{"asset": 8, "lang": "uz"}]}), ("video", {"source": "youtube", "yt_id": "dQw4w9WgXcQ", "captions": []})]),
    ("transcript", [("audio", {"asset": 9, "transcript": ""})], [("audio", {"asset": 9, "transcript": "Audio matni"})]),
    ("long_text", [("paragraph", {"html": long_p})], [("heading", {"text": "1-qism", "level": 2}), ("paragraph", {"html": "<p>" + " ".join(["matn"] * 200) + "</p>"}),
                                                     ("heading", {"text": "2-qism", "level": 2}), ("paragraph", {"html": "<p>" + " ".join(["matn"] * 200) + "</p>"})]),
    ("long_text", [("paragraph", {"html": "<p>" + " ".join(["a"] * 200) + "</p>"}), ("list", {"items": ["<p>" + " ".join(["b"] * 150) + "</p>"]})], [("paragraph", {"html": "<p>qisqa</p>"})]),
    ("kbd", [("tabs", {"items": [{"title": "A", "html": ""}]})], [("paragraph", {"html": "<p>x</p>"})]),
    ("pdf", [("attachment", {"asset": 11, "title": "Skan"})], [("attachment", {"asset": 12, "title": "Matnli"})]),
]
for key, bad_b, good_b in CASES:
    rb, rg = a11y(bad_b, pdf={11: False, 12: True})[key], a11y(good_b, pdf={11: False, 12: True})[key]
    ok(rb["level"] in ("bad", "warn") and rb["count"] >= 1 and rb["hint"] and rg["level"] == "ok" and rg["count"] == 0,
       f"Qoida «{key}»: muammoli fixture topildi ({rb['where'][0] if rb['where'] else '—'}), to'g'ri fixture o'tdi")
ok(a11y([("tabs", {"items": [{"title": "A", "html": ""}]})], {"settings": {"kbd_hints": True}})["kbd"]["level"] == "ok", "Klaviatura ko'rsatmalari yoqilgan kurs — «kbd» o'tdi")
cc_bad, cc_good = a11y([], {"accent": "#F59E0B"})["contrast"], a11y([], {"accent": "#870037"})["contrast"]
ok(cc_bad["level"] == "bad" and cc_bad["fix"] == "accent" and cc_bad["contrast"]["min"] < 4.5 and cc_good["level"] == "ok", f"Kontrast: #F59E0B — {cc_bad['contrast']['min']}:1 (xato, tuzatish «accent»), #870037 — o'tdi")
ok(all(K.accent_contrast(h)["ok"] for h in K.PALETTE), "Palitradagi barcha urg'u ranglari: oq matn, havola (oq/kulrang fon) va qorong'i rejim havolasi ≥ 4,5:1")
ok(K.contrast("#000000", "#ffffff") == 21.0 and K.contrast("#777777", "#ffffff") < 4.5 < K.contrast("#767676", "#ffffff") + 0.01, "WCAG kontrast formulasi (21:1; #767676 chegarasi)")
ok(all(K.bad_link_text(t) for t in ("Bu yerga bosing!", "batafsil", "  Click here ", "https://isft.uz/x", "ko‘proq", "")) and not any(K.bad_link_text(t) for t in ("Talabalar uchun qo'llanma (PDF)", "Mehnat kodeksi")),
   "Havola matni: «bu yerga bosing», «batafsil», yalang'och URL — yomon; ma'noli matn — yaxshi")
ok(K.block_levels("heading_paragraph", {"heading": "A", "html": "<h3>b</h3><h1>c</h1>"}) == [2, 3, 2] and K.block_levels("heading", {"text": "", "level": 3}) == [], "Sarlavha darajalari (h1 → h2; bo'sh sarlavha hisobga olinmaydi)")
tmpd = Path(tempfile.mkdtemp(prefix="kurs-a11y-"))
(tmpd / "t.pdf").write_bytes(mkpdf("Salom dunyo")); (tmpd / "s.pdf").write_bytes(mkpdf(""))
ok(K.pdf_text_layer(tmpd / "t.pdf") is True and K.pdf_text_layer(tmpd / "s.pdf") is False, "PDF matn qatlami: matnli PDF — bor, faqat chizma (skaner) — yo'q")
shutil.rmtree(tmpd, ignore_errors=True)
Qf = K.quality_from({"course": {"accent": "#870037", "settings": {}}, "lessons": [{"uid": "l", "type": "blocks", "title": "D", "blocks": [{"uid": 1, "type": "paragraph", "data": {"html": "<p>Salom</p>"}}]}]})
ok(Qf["a11y"]["passed"] == Qf["a11y"]["total"] == 10 and [i["level"] for i in Qf["issues"]] == ["ok"], "Toza kurs: 10/10 qulaylik qoidasi, «Muammo topilmadi»")

print("== 13b. Qulaylik: kursda tekshiruv va bir bosishli tuzatishlar (server orqali)")
ac = head.post(P + "/courses", json={"title": "Qulaylik sinovi"}).json()["id"]
acl = head.get(f"{P}/courses/{ac}").json()["lessons_list"][0]["id"]
vid = head.post(f"{P}/courses/{ac}/assets?kind=video&name=dars-video.mp4", content=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 4000)
ok(vid.status_code == 200 and vid.json()["kind"] == "video", f"Video yuklandi ({vid.status_code})")
vid = vid.json()["id"]
pdf_s = head.post(f"{P}/courses/{ac}/assets?kind=file&name=skan.pdf", content=mkpdf("")).json()["id"]
pdf_t = head.post(f"{P}/courses/{ac}/assets?kind=file&name=matn.pdf", content=mkpdf("Ma'ruza matni")).json()["id"]
AL = head.get(f"{P}/lessons/{acl}").json()
ABL = [{"type": "heading", "data": {"text": "Ichki bo'lim", "level": 3}},
       {"type": "paragraph", "data": {"html": long_p.replace("</p>", ' <a href="https://lex.uz">bu yerga bosing</a></p>')}},
       {"type": "table", "data": {"header": False, "caption": "Jadval", "rows": [["Ustun", "Qiymat"], ["a", "1"]]}},
       {"type": "video", "data": {"source": "file", "asset": vid, "title": "Kirish videosi", "captions": []}},
       {"type": "tabs", "data": {"items": [{"title": "A", "html": "<p>a</p>"}, {"title": "B", "html": "<p>b</p>"}]}},
       {"type": "attachment", "data": {"asset": pdf_s, "title": "Skanerlangan qo'llanma"}},
       {"type": "attachment", "data": {"asset": pdf_t, "title": "Matnli qo'llanma"}}]
r = head.post(f"{P}/lessons/{acl}", json={"rev": AL["rev"], "blocks": ABL})
ok(r.status_code == 200, f"Qulaylik muammolari bor dars saqlandi ({r.status_code})")
AQ = head.get(f"{P}/courses/{ac}/quality").json()
R_ = {x["key"]: x for x in AQ["a11y"]["rules"]}
ok({k for k, v in R_.items() if v["level"] != "ok"} == {"headings", "links", "tables", "captions", "long_text", "kbd", "pdf"} and R_["pdf"]["count"] == 1,
   f"Server hisobot: buzilgan qoidalar — {sorted(k for k, v in R_.items() if v['level'] != 'ok')} (matnli PDF o'tdi, skanerlangani — yo'q)")
ok(R_["captions"]["items"] and R_["captions"]["items"][0]["asset"] == vid and R_["captions"]["action"] == "captions", "Subtitrsiz video — «Subtitr yaratish» uchun video id bilan")
ok(json.loads(q("SELECT meta FROM ku_assets WHERE id=?", (pdf_s,))[0]["meta"]).get("text_layer") is False, "PDF matn qatlami natijasi fayl meta'sida keshlandi")
ai = [i for i in AQ["issues"] if i.get("group") == "a11y"]
ok(len(ai) == 7 and {i["fix"] for i in ai if i["fix"]} == {"headings", "table_header", "kbd_hints"} and all(i["detail"] for i in ai), "Sifat hisobotida 7 ta qulaylik muammosi, 3 tasida bir bosishli tuzatish")
nv = len(head.get(f"{P}/courses/{ac}/versions").json()["items"])
f_h = head.post(f"{P}/courses/{ac}/fix", json={"fix": "headings"}).json()
f_t = head.post(f"{P}/courses/{ac}/fix", json={"fix": "table_header"}).json()
f_k = head.post(f"{P}/courses/{ac}/fix", json={"fix": "kbd_hints"}).json()
f_a = head.post(f"{P}/courses/{ac}/fix", json={"fix": "accent"}).json()
AB = head.get(f"{P}/lessons/{acl}").json()["blocks"]
RA = {x["key"]: x["level"] for x in f_k["quality"]["a11y"]["rules"]}
ok(f_h["changed"] >= 1 and AB[0]["data"]["level"] == 2 and RA["headings"] == "ok", "«Sarlavha darajalarini tuzatish»: H3 → H2, qoida o'tdi")
ok(f_t["changed"] >= 1 and AB[2]["data"]["header"] is True and RA["tables"] == "ok", "«Sarlavha qatorini yoqish»: jadvalda birinchi qator sarlavha, qoida o'tdi")
ok(f_k["changed"] == 1 and f_k["course"]["settings"]["kbd_hints"] is True and RA["kbd"] == "ok", "«Klaviatura ko'rsatmalari»: kurs sozlamasi yoqildi, qoida o'tdi")
ok(f_a["changed"] == 0 and len(head.get(f"{P}/courses/{ac}/versions").json()["items"]) >= nv + 4, "Kontrast joyida — «accent» hech narsani o'zgartirmaydi; har tuzatishdan oldin versiya")
ok(teach.post(f"{P}/courses/{ac}/fix", json={"fix": "headings"}).status_code == 403 and rek.get(f"{P}/courses/{ac}/quality").status_code == 403, "Begona o'qituvchi tuzata olmaydi, rektor hisobotni ko'rmaydi (403)")
cj = httpx.get(B + head.get(f"{P}/courses/{ac}/preview-url").json()["url"].split("index.html")[0] + "content.js").text
ok('"kbd_hints":true' in cj, "Pleyer kontentida settings.kbd_hints = true")
names_x = set(zipfile.ZipFile(io.BytesIO(zips["xapi"])).namelist())
ok("a11y.js" in names_x and '<script src="a11y.js">' in zipfile.ZipFile(io.BytesIO(zips["xapi"])).read("index.html").decode(), "Eksport: a11y.js (qulaylik paneli, ovozli o'qish) pleyer bilan birga")

print("== 13c. Subtitr: yozuvlar muharriri (VTT) va avtomatik subtitr navbati")
vtt0 = head.post(f"{P}/courses/{ac}/assets?kind=vtt&name=kirish.vtt&lang=uz", content="WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nAssalomu alaykum\n\n00:00:04.000 --> 00:00:06.000\na < b & c\n".encode()).json()
cu = head.get(f"{P}/assets/{vtt0['id']}/cues").json()
ok(cu["lang"] == "uz" and [c["start"] for c in cu["cues"]] == [1.0, 4.0] and cu["cues"][1]["text"] == "a < b & c", "VTT → yozuvlar ro'yxati (vaqtlar soniyada, matn HTML-belgisiz)")
sv = head.post(f"{P}/courses/{ac}/vtt", json={"asset": vtt0["id"], "lang": "uz", "cues": [{"start": 0.5, "end": 3.5, "text": "Assalomu alaykum, talabalar!"}, {"start": 4, "end": 6.25, "text": "a < b"}]}).json()
cu2 = head.get(f"{P}/assets/{sv['id']}/cues").json()["cues"]
ok(sv["kind"] == "vtt" and sv["id"] != vtt0["id"] and cu2[0] == {"start": 0.5, "end": 3.5, "text": "Assalomu alaykum, talabalar!"} and cu2[1]["end"] == 6.25,
   "Tahrirlangan yozuvlar → yangi VTT fayl (eski fayl o'zgarmaydi — versiyalar uchun)")
ok(head.get(f"{P}/assets/{vtt0['id']}/cues").json()["cues"][0]["text"] == "Assalomu alaykum", "Asl VTT fayl o'zgarmagan")
r1 = head.post(f"{P}/courses/{ac}/vtt", json={"lang": "uz", "cues": [{"start": 3, "end": 2, "text": "x"}]})
r2 = head.post(f"{P}/courses/{ac}/vtt", json={"lang": "uz", "cues": [{"start": 1, "end": 2, "text": " "}]})
ok(r1.status_code == 400 and r2.status_code == 400 and head.post(f"{P}/courses/{ac}/vtt", json={"lang": "uz", "cues": []}).status_code == 400, "Noto'g'ri vaqt, bo'sh matn, bo'sh ro'yxat — 400")
ok(teach.post(f"{P}/courses/{ac}/vtt", json={"lang": "uz", "cues": [{"start": 1, "end": 2, "text": "x"}]}).status_code == 403 and teach.get(f"{P}/assets/{vtt0['id']}/cues").status_code == 403,
   "Begona o'qituvchi subtitrni o'qimaydi va yozmaydi (403)")
cr = head.post(f"{P}/courses/{ac}/captions", json={"asset": vid, "lang": "uz"}).json()
ok(cr["job"]["status"] == "navbatda" and cr["existing"] is False and cr["job"]["asset"] == vid and isinstance(cr["worker"], bool), "«Subtitr yaratish» (masofaviy ta'lim bo'limi): vazifa navbatga qo'yildi")
ok(head.post(f"{P}/courses/{ac}/captions", json={"asset": vid, "lang": "uz"}).json()["existing"] is True, "Shu video + til uchun ikkinchi so'rov — mavjud vazifa qaytariladi")
ok(head.post(f"{P}/courses/{ac}/captions", json={"asset": pdf_s, "lang": "uz"}).status_code == 404 and head.post(f"{P}/courses/{ac}/captions", json={"asset": vid, "lang": "xx"}).status_code == 400,
   "Video bo'lmagan fayl — 404, noma'lum til — 400")
tcid = q("SELECT id FROM ku_courses WHERE author_id=? AND deleted=0 ORDER BY id LIMIT 1", (teach_uid,))[0]["id"]
ok(teach.post(f"{P}/courses/{tcid}/captions", json={"asset": vid, "lang": "uz"}).status_code == 403, "O'qituvchi Whisper navbatiga qo'ymaydi (faqat masofaviy ta'lim bo'limi) — 403")
cl = head.get(f"{P}/courses/{ac}/captions").json()
ok(cl["can_request"] and cl["items"][0]["asset"] == vid and "docs/kurs.md" in cl["manual"], "Navbat ro'yxati, qo'lda yo'l izohi")
if not os.environ.get("ISFT_CORE_WORKER_TOKEN"):
    ok(httpx.post(B + "/api/montaj/kurs-captions/claim", headers={"X-Worker-Token": "x"}).status_code == 503, "Ishchi tokeni sozlanmagan — claim 503 («worker o'chiq»)")
ok(head.post(f"{P}/captions/{cl['items'][0]['id']}/cancel").status_code == 200 and head.get(f"{P}/courses/{ac}/captions").json()["items"][0]["status"] == "bekor", "Vazifani bekor qilish")
AL = head.get(f"{P}/lessons/{acl}").json()
for b in AL["blocks"]:
    if b["type"] == "video": b["data"]["captions"] = [{"asset": sv["id"], "lang": "uz", "label": "O'zbekcha"}]
head.post(f"{P}/lessons/{acl}", json={"rev": AL["rev"], "blocks": AL["blocks"]})
ok(next(x for x in head.get(f"{P}/courses/{ac}/quality").json()["a11y"]["rules"] if x["key"] == "captions")["level"] == "ok", "Subtitr ulangach «Videolar uchun subtitr» qoidasi o'tdi")

print("== 13d. Subtitr ishchisi (jarayon ichida: bazaning nusxasi, ISFT_CORE_WORKER_TOKEN)")
WORKER_SCRIPT = r'''
import contextlib, io, json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ["ROOT"])
with contextlib.redirect_stdout(io.StringIO()):
    from app import main as APP
from fastapi.testclient import TestClient
from app import kurs as K, db as DB
TOKEN = os.environ["ISFT_CORE_WORKER_TOKEN"]; P = "/api/kurs"; W = "/api/montaj/kurs-captions"
def ok(c, m): print(("✓ " if c else "✗ ") + m)
assert str(K.store()).startswith(os.environ["ISFT_CORE_DATA_DIR"]), "nusxa emas"
H = TestClient(APP.app, base_url="http://testserver")
assert H.post("/api/login", json={"user_id": int(os.environ["HEAD_UID"]), "password": os.environ["PWD"]}).status_code == 200
WC = TestClient(APP.app, base_url="http://testserver"); WH = {"X-Worker-Token": TOKEN}
APP.con.execute("UPDATE ku_caption_jobs SET status='bekor' WHERE status IN ('navbatda','ishlanmoqda')"); APP.con.commit()
cid = H.post(P + "/courses", json={"title": "Subtitr ishchisi"}).json()["id"]
lid = H.get(f"{P}/courses/{cid}").json()["lessons_list"][0]["id"]
vid = H.post(f"{P}/courses/{cid}/assets?kind=video&name=v.mp4", content=b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x01" * 3000).json()["id"]
L = H.get(f"{P}/lessons/{lid}").json()
r = H.post(f"{P}/lessons/{lid}", json={"rev": L["rev"], "blocks": [{"type": "video", "data": {"source": "file", "asset": vid, "captions": []}},
                                                                    {"type": "video", "data": {"source": "file", "asset": vid, "captions": []}}]})
rev0 = r.json()["rev"]
ok(WC.post(W + "/claim").status_code == 401 and WC.post(W + "/claim", headers={"X-Worker-Token": TOKEN + "x"}).status_code == 401, "Tokensiz / noto'g'ri token — 401")
ok(WC.post(W + "/claim", headers=WH).status_code == 204, "Navbat bo'sh — 204")
ok(H.post(W + "/claim").status_code == 401, "Sessiya cookie ishchi tokeni o'rnini bosmaydi (401)")
j = H.post(f"{P}/courses/{cid}/captions", json={"asset": vid, "lang": "uz"}).json()["job"]
c = WC.post(W + "/claim", headers=WH).json()
ok(c["job_id"] == j["id"] and c["lang"] == "uz" and len(c["lease"]) == 16 and c["media_url"] == f"{W}/{j['id']}/media", "claim: vazifa, til, lease, video havolasi")
m = WC.get(c["media_url"], headers={**WH, "Range": "bytes=4-11"})
ok(m.status_code == 206 and m.content == b"ftypmp42" and WC.get(c["media_url"]).status_code == 401, "Video — token bilan, Range (206); tokensiz — 401")
ok(WC.post(f"{W}/{j['id']}/progress", headers={**WH, "X-Worker-Lease": "0" * 16}, json={"stage": "nutq", "pct": 40}).status_code == 409, "Eskirgan lease — 409")
ok(WC.post(f"{W}/{j['id']}/progress", headers={**WH, "X-Worker-Lease": c["lease"]}, json={"stage": "nutq", "pct": 40}).status_code == 200
   and H.get(f"{P}/courses/{cid}/captions").json()["items"][0]["pct"] == 40, "progress: bosqich va foiz muharrirda ko'rinadi")
ok(WC.post(f"{W}/{j['id']}/result", headers={**WH, "X-Worker-Lease": c["lease"], "Content-Type": "text/vtt"}, content=b"not a vtt").status_code == 400, "Buzilgan VTT — 400 (vazifa ochiq qoladi)")
vtt = "WEBVTT\n\n1\n00:00:00.200 --> 00:00:02.000\nAssalomu alaykum.\n\n2\n00:00:02.100 --> 00:00:04.000\nBugun ma'lumotlar bazasi.\n"
rr = WC.post(f"{W}/{j['id']}/result", headers={**WH, "X-Worker-Lease": c["lease"], "Content-Type": "text/vtt"}, content=vtt.encode())
ok(rr.status_code == 200 and rr.json()["cues"] == 2 and rr.json()["attached"] == 2, f"result: 2 yozuv, shu videoli 2 ta blokka ulandi ({rr.text[:120]})")
L2 = H.get(f"{P}/lessons/{lid}").json()
caps = [b["data"]["captions"] for b in L2["blocks"]]
ok(all(len(x) == 1 and x[0]["lang"] == "uz" and x[0]["asset"] == rr.json()["asset"] and "(avto)" in x[0]["label"] for x in caps) and L2["rev"] > rev0,
   "Bloklarda «O'zbekcha (avto)» subtitr; dars rev oshdi (ochiq muharrir ziddiyatni ko'radi)")
cu = H.get(f"{P}/assets/{rr.json()['asset']}/cues").json()
ok(cu["auto"] == "whisper" and cu["cues"][0]["text"] == "Assalomu alaykum.", "Whisper subtitri yozuvlar muharririda (auto=whisper)")
jl = H.get(f"{P}/courses/{cid}/captions").json()
ok(jl["items"][0]["status"] == "tayyor" and jl["items"][0]["cues"] == 2 and jl["worker"] is True, "Vazifa — «Tayyor», ishchi yoqilgan")
q = K.quality(K.rbac.ctx_for(APP.con, int(os.environ["HEAD_UID"])), cid)
ok(next(r for r in q["a11y"]["rules"] if r["key"] == "captions")["level"] == "ok", "Sifat hisoboti: subtitr qoidasi o'tdi")
ok(WC.post(f"{W}/{j['id']}/result", headers={**WH, "X-Worker-Lease": c["lease"]}, content=vtt.encode()).status_code == 410, "Tugagan vazifaga qayta natija — 410")
j2 = H.post(f"{P}/courses/{cid}/captions", json={"asset": vid, "lang": "ru"}).json()["job"]
c2 = WC.post(W + "/claim", headers=WH).json()
ok(WC.post(f"{W}/{j2['id']}/fail", headers={**WH, "X-Worker-Lease": c2["lease"]}, json={"error": "Videoda nutq topilmadi"}).status_code == 200
   and H.get(f"{P}/courses/{cid}/captions").json()["items"][0]["error"] == "Videoda nutq topilmadi", "fail: xato matni muharrirda")
au = DB.rows(APP.con, "SELECT COUNT(*) n FROM audit_log WHERE action LIKE 'kurs subtitr:%'")[0]["n"]
ok(au >= 4, f"Ishchi amallari audit jurnalida ({au})")
'''
wtmp = Path(tempfile.mkdtemp(prefix="kurs-wk-"))
try:
    s_, d_ = sqlite3.connect(DBP), sqlite3.connect(wtmp / "jarvis.db"); s_.backup(d_); s_.close(); d_.close()
    wenv = dict(os.environ, ROOT=str(ROOT), ISFT_CORE_DATA_DIR=str(wtmp), ISFT_CORE_DB=str(wtmp / "jarvis.db"), ISFT_CORE_SECRETS_DIR=str(wtmp / "secrets"),
                ISFT_CORE_FILES_DIR=str(wtmp / "portal_files"), ISFT_CORE_STAFFABS_DIR=str(wtmp / "staffabs_files"), ISFT_CORE_WORKER_TOKEN="kurs-ishchi-" + os.urandom(6).hex(),
                HEAD_UID=str(head_uid), PWD=PW)
    rr = subprocess.run([sys.executable, "-c", WORKER_SCRIPT], cwd=str(wtmp), env=wenv, capture_output=True, text=True, timeout=300)
    lines = [ln.strip() for ln in rr.stdout.splitlines() if ln.strip()[:1] in ("✓", "✗")]
    for ln in lines: ok(ln.startswith("✓"), "[ishchi] " + ln[1:].strip())
    ok(rr.returncode == 0 and len(lines) >= 15, f"Ishchi sinovi jarayoni ({rr.returncode}, {len(lines)} tekshiruv)" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-10:])))
finally:
    shutil.rmtree(wtmp, ignore_errors=True)

# =============================================================================================
print("== 13e. «AI bilan tahrirlash» (to'liq sinov — tests/test_kurs_ai.py): bog'lanish va variant izohi modeli")
kjs = (ROOT / "static" / "kurs.js").read_text()
ok(all(x in kjs for x in ("kuAiOpen", 'data-act="ai"', 'aria-label="AI bilan tahrirlash"', "/ai-question", "AI tuzdi — to'g'ri javobni tekshiring", 'data-act="qai"')), "kurs.js: AI tugmasi (aria-label), «AI bilan savol» (tez qo'shish), eslatma, endpoint")
fb = K.clean_block("knowledge", {"kind": "single", "question": "S?", "answers": [{"text": "a", "correct": True, "feedback": "Nega to'g'ri"}, {"text": "b", "feedback": "Nega noto'g'ri <script>x</script>"}],
                                 "feedback_correct": "Umumiy", "feedback_wrong": "Takrorlang"}, K._Assets(None))
ok(fb["answers"][0]["feedback"] == "Nega to'g'ri" and fb["answers"][1]["feedback"].startswith("Nega noto'g'ri") and fb["feedback_correct"] == "Umumiy", "Har variant izohi (answers[i].feedback) va umumiy izohlar modelda saqlanadi")
ok("afb" in (ROOT / "app" / "kurs_player" / "player.js").read_text(), "Pleyer: tanlangan variant izohi ko'rsatiladi (afb)")
ok(q("SELECT name FROM sqlite_master WHERE type='table' AND name='ku_ai'") and head.post(f"{P}/lessons/{hl}/ai-question", json={"text": "1. Savol?\nA) bir ✅\nB) ikki"}).status_code in (200, 503, 502),
   "ku_ai jadvali bor; /lessons/{id}/ai-question endpointi javob beradi (kalitsiz — 503 + tuzilma)")

print("== 14. Brauzer: pleyer (mock LMS) va muharrir")
pwj, chrome, node = os.environ.get("PW"), os.environ.get("CHROME"), shutil.which("node")
if node:
    for f in ("app/kurs_player/player.js", "app/paket_player/lms.js", "static/kurs.js", "tools/kurs_player_check.js", "tools/kurs_editor_check.js", "tools/kurs_ai_check.js"):
        if (ROOT / f).is_file():
            rr = subprocess.run([node, "--check", str(ROOT / f)], capture_output=True, text=True)
            ok(rr.returncode == 0, f"node --check {f}" + ("" if rr.returncode == 0 else ": " + rr.stderr.strip()[:200]))
if not (pwj and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer sinovi o'tkazib yuborildi")
else:
    tmp = Path(tempfile.mkdtemp(prefix="kurs-pl-"))
    try:
        for mode in ("scorm12", "scorm2004", "xapi"):
            zipfile.ZipFile(io.BytesIO(zips[mode])).extractall(tmp / mode)
        out = os.environ.get("OUT") or str(tmp / "shots")
        env = dict(os.environ, OUT=out)
        rr = subprocess.run([node, str(ROOT / "tools" / "kurs_player_check.js"), str(tmp)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        for ln in (rr.stdout + rr.stderr).splitlines():
            s = ln.strip()
            if s.startswith("✓"): ok(True, "[pleyer] " + s[1:].strip())
            elif s.startswith("✗"): ok(False, "[pleyer] " + s[1:].strip())
        ok(rr.returncode == 0, f"tools/kurs_player_check.js chiqish kodi 0 ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-12:])))
        env.update(B=B, KU_UID=str(head_uid), KU_PW=PW, KU_CID=str(dc), KU_QCID=str(ic), KU_ACID=str(ac))
        rr = subprocess.run([node, str(ROOT / "tools" / "kurs_editor_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
        for ln in (rr.stdout + rr.stderr).splitlines():
            s = ln.strip()
            if s.startswith("✓"): ok(True, "[muharrir] " + s[1:].strip())
            elif s.startswith("✗"): ok(False, "[muharrir] " + s[1:].strip())
        ok(rr.returncode == 0, f"tools/kurs_editor_check.js chiqish kodi 0 ({rr.returncode})" + ("" if rr.returncode == 0 else ":\n" + "\n".join((rr.stdout + rr.stderr).splitlines()[-12:])))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
