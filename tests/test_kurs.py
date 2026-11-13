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
root = ET.fromstring(z.read("tincan.xml")); acts = root.findall(f"{TCN}activities/{TCN}activity")
cont = json.loads(z.read("content.json"))
ok(acts[0].get("id") == f"https://isft.uz/xapi/kurs/{dc}" and acts[0].find(f"{TCN}launch").text == "index.html"
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
ok({i["fix"] for i in Qr["issues"] if i["fix"]} == {"shuffle", "labels", "mr_single"}, "Tuzatish takliflari: aralashtirish, yorliqlar, savol turi")
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
print("== 14. Brauzer: pleyer (mock LMS) va muharrir")
pwj, chrome, node = os.environ.get("PW"), os.environ.get("CHROME"), shutil.which("node")
if node:
    for f in ("app/kurs_player/player.js", "app/paket_player/lms.js", "static/kurs.js", "tools/kurs_player_check.js", "tools/kurs_editor_check.js"):
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
        env.update(B=B, KU_UID=str(head_uid), KU_PW=PW, KU_CID=str(dc), KU_QCID=str(ic))
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
