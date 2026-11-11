"""Kontent paketlari moduli (app/paket.py) — ruxsatlar, YouTube havolalari, HTML tozalash, ma'ruza matni → reja va HTML, PPTX tahlili,
manbalar (HTTP), yig'ish (har bir tur: SCORM 1.2 / SCORM 2004 / xAPI / oddiy) + validate_zip + manifestlar (ElementTree), deterministik zip,
versiyalar, kurs paketi, ko'rish (preview) yo'li, yuklab olish nomi, avtomatik joylash, qamrov (SQL bilan), «Mening vazifalarim».
NEXTID (kontrakt v2): darslar ro'yxati (L/A/S/Lab/MT) tahlili, migratsiya idempotentligi, Word rasmlari (izoh bilan) / jadvallar / adabiyotlar,
figure/img tozalash, PDF → slayd rasmlari (pypdfium2), shablon bloklari tartibi va bo'lim sarlavhalari, reflect / keypoints, AI xulosalar
(claude_client.call_json jarayon ichida almashtiriladi — serverda AI chaqirilmaydi), har tur uchun validate_zip, dars bo'yicha fayl nomlari.

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_paket.py
   (yoki hammasi toza muhitda: python tests/run_all.py --only paket)
DIQQAT: lokal bazani o'zgartiradi (manbalar, video havolalar, paketlar) — PRODUCTION'da ishlatilmaydi.
Yig'ish jarayon ichida (bazaning vaqtinchalik nusxasida) soxta pleyer bilan ham tekshiriladi (paket.PLAYER_DIR / STORE almashtiriladi);
server orqali yig'ish — app/paket_player/index.html mavjud bo'lsa.
"""
import io, json, os, re, sqlite3, sys, tempfile, zipfile, xml.etree.ElementTree as ET
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
P = "/api/paket"
SERVER_PLAYER = (ROOT / "app" / "paket_player" / "index.html").is_file()

from app import paket as PK   # sof funksiyalar (havola, tozalash, matn, pptx, manifest, validator) — baza talab qilmaydi

head, staff, rek, pro, kaf, teach, bux = (S(uid(r)) for r in ("masofaviy", "masofaviy_xodim", "rektor", "prorektor_oquv", "kafedra", "oqituvchi", "buxgalteriya"))
head_uid, teach_uid = uid("masofaviy"), uid("oqituvchi")
teach_tid = q("SELECT teacher_id FROM users WHERE id=?", (teach_uid,))[0]["teacher_id"]
kaf_dept = q("SELECT department_id FROM users WHERE id=?", (uid("kafedra"),))[0]["department_id"]
mikro = q("SELECT * FROM dl_courses WHERE subject='Mikroiqtisodiyot' ORDER BY id LIMIT 1")[0]
kaf8 = S(uid("kafedra", "AND department_id=?", (mikro["department_id"],)))
own = q("SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY subject='Innovatsion iqtisodiyot' DESC, id LIMIT 1", (teach_tid,))[0]
other_dept = q("SELECT * FROM dl_courses WHERE department_id!=? ORDER BY id LIMIT 1", (kaf_dept,))[0]

# =============================================================================================
print("== 1. Ruxsatlar va ko'lam")
m = head.get(P + "/meta").json()
ok(m["tabs"] == ["qamrov", "mavzular", "joylash", "sozlama"] and m["caps"]["approve"] and m["caps"]["settings"], "Bo'lim boshlig'i: 4 bo'lim, tasdiqlash va sozlamalar")
ms = staff.get(P + "/meta").json()
ok(ms["caps"]["approve"] and ms["caps"]["settings"] and ms["caps"]["build"], "Bo'lim xodimi: yig'ish, tasdiqlash, sozlamalar")
mt = teach.get(P + "/meta").json()
ok(mt["caps"]["build"] and not mt["caps"]["approve"] and not mt["caps"]["settings"] and "joylash" in mt["tabs"], "O'qituvchi: yig'adi, tasdiqlamaydi")
mk = kaf.get(P + "/meta").json()
ok(not mk["caps"]["write"] and mk["caps"]["download"] and mk["tabs"] == ["qamrov", "mavzular"], "Kafedra mudiri: ko'rish va yuklab olish")
mr = rek.get(P + "/meta").json()
ok(mr["tabs"] == ["qamrov"] and not mr["caps"]["view"], "Rektor: faqat jamlangan qamrov")
ok(pro.get(P + "/meta").json()["tabs"] == ["qamrov"], "O'quv prorektori: faqat jamlangan qamrov")
ok(rek.get(P + "/coverage").status_code == 200 and pro.get(P + "/coverage").status_code == 200, "Rahbariyat qamrovni ko'radi")
ok(rek.get(f"{P}/courses/{mikro['id']}").status_code == 403 and rek.get(P + "/courses").status_code == 403, "Rektor kurs va mavzularni ko'rmaydi (403)")
ok(rek.get(f"{P}/courses/{mikro['id']}/topics/1").status_code == 403, "Rektor mavzu manbalarini ko'rmaydi (403)")
ok(bux.get(P + "/meta").status_code == 403 and bux.get(P + "/coverage").status_code == 403, "Buxgalteriya — ruxsat yo'q (403)")
ok(teach.get(f"{P}/courses/{mikro['id']}").status_code == 403, "O'qituvchi begona kursni ochmaydi (403)")
ok(teach.post(f"{P}/courses/{mikro['id']}/topics/3/video", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).status_code == 403, "O'qituvchi begona kursga video qo'ymaydi (403)")
ok(kaf.get(f"{P}/courses/{other_dept['id']}").status_code == 403, "Kafedra mudiri boshqa kafedra kursini ochmaydi (403)")
ok(kaf8.get(f"{P}/courses/{mikro['id']}").status_code == 200 and kaf8.get(f"{P}/courses/{mikro['id']}/topics/1").status_code == 200, "Kafedra mudiri o'z kafedrasi kursini ko'radi")
ok(kaf8.post(f"{P}/courses/{mikro['id']}/topics/3/video", json={"url": "https://youtu.be/dQw4w9WgXcQ"}).status_code == 403 and
   kaf8.post(f"{P}/courses/{mikro['id']}/topics/1/build", json={}).status_code == 403, "Kafedra mudiri manba qo'sholmaydi va yig'olmaydi (403)")
ok(teach.post(P + "/settings", json={"mode": "xapi", "completion": "view_all"}).status_code == 403, "O'qituvchi umumiy sozlamani o'zgartirmaydi (403)")
tc = teach.get(P + "/courses?limit=400").json()
ok(tc["total"] > 0 and all(r["teacher_id"] == teach_tid for r in tc["items"]), f"O'qituvchi faqat o'z kurslarini ko'radi ({tc['total']} ta)")
kc = kaf.get(P + "/courses?limit=400").json()
ok(kc["total"] > 0 and all(r["department_id"] == kaf_dept for r in kc["items"]), f"Kafedra faqat o'z kafedrasi kurslarini ko'radi ({kc['total']} ta)")
ok(head.get(P + "/courses?limit=1").json()["total"] == q("SELECT COUNT(*) n FROM dl_courses")[0]["n"], "Bo'lim — barcha kurslar")
den = q("SELECT COUNT(*) n FROM audit_log WHERE resource='paket' AND allowed=0")[0]["n"]
ok(den >= 8, f"Rad etilgan so'rovlar audit jurnalida ({den} ta)")
ok(q("SELECT COUNT(*) n FROM audit_log WHERE resource='paket' AND allowed=1")[0]["n"] > 0, "Ruxsat berilgan so'rovlar ham audit jurnalida")
ok(m["demo"], "Namuna belgisi bor (Mikroiqtisodiyot 1–2-mavzular)")

# =============================================================================================
print("== 2. YouTube havolalari")
ID = "dQw4w9WgXcQ"
CASES = [
    (f"https://www.youtube.com/watch?v={ID}", "youtube", ID, 0),
    (f"https://youtube.com/watch?feature=share&v={ID}&t=90", "youtube", ID, 90),
    (f"https://m.youtube.com/watch?v={ID}&t=1m30s", "youtube", ID, 90),
    (f"https://youtu.be/{ID}", "youtube", ID, 0),
    (f"https://youtu.be/{ID}?t=42", "youtube", ID, 42),
    (f"https://www.youtube.com/shorts/{ID}", "youtube", ID, 0),
    (f"https://www.youtube.com/embed/{ID}?start=15", "youtube", ID, 15),
    (f"https://www.youtube-nocookie.com/embed/{ID}", "youtube", ID, 0),
    (f"https://www.youtube.com/live/{ID}", "youtube", ID, 0),
    (f"youtu.be/{ID}", "youtube", ID, 0),
    (ID, "youtube", ID, 0),
    (f"https://youtu.be/{ID}?t=1h2m3s", "youtube", ID, 3723),
    ("https://lms.isft.uz/video/12", "link", None, 0),
]
for url, prov, vid, start in CASES:
    r = PK.parse_video(url)
    ok(r["ok"] and r["provider"] == prov and r.get("video_id") == vid and r["start"] == start, f"{url} → {prov} {vid or ''} t={start}")
for bad in ("https://youtu.be/demo190x3", "https://www.youtube.com/watch?v=short", "https://www.youtube.com/playlist?list=PL123",
            "javascript:alert(1)", "ftp://example.com/v.mp4", "", "salom dunyo"):
    ok(not PK.parse_video(bad)["ok"], f"Noto'g'ri: {bad!r}")
ok(PK.parse_video(f"https://youtu.be/{ID}?t=30")["url"] == f"https://www.youtube.com/watch?v={ID}&t=30s", "Kanonik havola (watch?v=…&t=Ns)")
bl = PK.parse_bulk(f"https://youtu.be/{ID}\n\n# izoh\nhttps://youtu.be/aaaaaaaaaaa\n5: https://youtu.be/bbbbbbbbbbb\nhttps://youtu.be/xx\n20) https://youtu.be/ccccccccccc", 15)
ok([(r["topic_no"], r["ok"]) for r in bl] == [(1, True), (2, True), (5, True), (6, False), (20, False)], "Ommaviy ro'yxat: ketma-ket, «N: havola», xato ID, oraliqdan tashqari")
bl = PK.parse_bulk(f"A2: https://youtu.be/{ID}\nL3: https://youtu.be/aaaaaaaaaaa\nhttps://youtu.be/bbbbbbbbbbb\nA9: https://youtu.be/ccccccccccc", 15, list(range(1, 16)) + [1001, 1002])
ok([(r["code"], r["ok"]) for r in bl] == [("A2", True), ("L3", True), ("L4", True), ("A9", False)] and "A9" in bl[-1]["error"], "Ommaviy ro'yxat: dars kodlari (A2:, L3:), ketma-ketlik L bo'yicha, yo'q dars — xato")

print("== 2b. Darslar ro'yxati (NEXTID nomlari)")
LESSON_CASES = [
    ("L1-1-dars: AXBOROT TEXNOLOGIYALARI FANIGA KIRISH", ("L1", "maruza", 1, "AXBOROT TEXNOLOGIYALARI FANIGA KIRISH", None, 1)),
    ("L12-12-dars: Tarmoqlar", ("L12", "maruza", 12, "Tarmoqlar", None, 12)),
    ("A1- AMALIY MASHG'ULOT: Excel bilan ishlash", ("A1", "amaliy", 1, "Excel bilan ishlash", None, 1001)),
    ("A2- Amaliy: Word hujjatlari (3-mavzu)", ("A2", "amaliy", 2, "Word hujjatlari", 3, 1002)),
    ("A30- AMALIY MASHG‘ULOT: Ma’lumotlar bazasi", ("A30", "amaliy", 30, "Ma'lumotlar bazasi", None, 1030)),
    ("A3: Amaliy statistika asoslari", ("A3", "amaliy", 3, "Amaliy statistika asoslari", None, 1003)),
    ("S1 Seminar: Raqamli iqtisodiyot | 2", ("S1", "seminar", 1, "Raqamli iqtisodiyot", 2, 2001)),
    ("Lab1 - Laboratoriya ishi: Tarmoq sozlash [4]", ("Lab1", "laboratoriya", 1, "Tarmoq sozlash", 4, 3001)),
    ("MT2. Mustaqil ta'lim: Esse", ("MT2", "mustaqil", 2, "Esse", None, 4002)),
]
for line, (code, kind, no, title, topic, key) in LESSON_CASES:
    r = PK.parse_lessons(line)[0]
    ok(r["ok"] and (r["code"], r["kind"], r["no"], r["title"], r["topic"], r["key"]) == (code, kind, no, title, topic, key), f"{line!r} → {code} {kind} «{title}»{f' → {topic}-mavzu' if topic else ''}")
bad = PK.parse_lessons("# izoh\n\nSalom dunyo\nA1:\nL1000: katta\nA4: Birinchi\nA4: Ikkinchi")
ok([(r["ok"], bool(r["error"])) for r in bad] == [(False, True), (False, True), (False, True), (False, True), (True, False)] and bad[-1]["title"] == "Ikkinchi",
   "Noto'g'ri qatorlar: kodsiz, nomsiz, 1000+, takror (oxirgisi olinadi); izoh/bo'sh qatorlar e'tiborsiz")
ok([PK.lesson_code(k) for k in (1, 15, 1001, 2003, 3001, 4012)] == ["L1", "L15", "A1", "S3", "Lab1", "MT12"] and PK.lesson_file_code(1001) == "A01" and PK.split_key(3002) == ("laboratoriya", 2),
   "Dars kaliti ↔ kod: L1=1, A1=1001, S3=2003, Lab1=3001, MT12=4012")

# =============================================================================================
print("== 3. HTML tozalash (server tomonda)")
dirty = ('<p onclick="x()">Matn<img src=x onerror=alert(1)><a href="javascript:alert(1)">j</a> <a href=" https://isft.uz/a?b=1&c=2">ok</a>'
         '<script>bad()</script><style>p{color:red}</style><iframe src="https://evil"></iframe><h1>Sarlavha</h1><div><b>qalin</b></div>'
         '<a href="JaVaScRiPt:alert(2)">x</a><a href="data:text/html,1">d</a><svg><script>x</script></svg><ul><li>band')
cl = PK.sanitize(dirty)
ok("<script" not in cl.lower() and "onerror" not in cl and "onclick" not in cl and "javascript:" not in cl.lower() and "<img" not in cl, "script / on* / javascript: / img olib tashlandi")
ok("<style" not in cl and "color:red" not in cl and "<iframe" not in cl and "<svg" not in cl and "data:" not in cl, "style / iframe / svg / data: olib tashlandi")
ok('<a href="https://isft.uz/a?b=1&amp;c=2" rel="noopener noreferrer" target="_blank">ok</a>' in cl, "http(s) havola qoladi (rel=noopener)")
ok("<h2>Sarlavha</h2>" in cl and "<b>qalin</b>" in cl and cl.endswith("<ul><li>band</li></ul></p>"), "h1→h2, ruxsat etilgan teglar, yopilmagan teglar yopiladi")
ok(PK.sanitize("a < b & c") == "a &lt; b &amp; c", "Matn qochiriladi")
code_txt = PK.structure_text("Reja:\n1. JavaScript\n\n1. JavaScript\nTugma: <button onclick=\"f()\">, havola: javascript:void(0), <script>alert(1)</script>", "x")["html"]
ok(PK.html_unsafe(code_txt) is None and "onclick=" in code_txt and "&lt;script&gt;" in code_txt,
   "Kod haqidagi ma'ruza (onclick=, javascript:, <script> matn sifatida) — xavfsiz deb topiladi, paket rad etilmaydi")
# bo'sh (void) teglar «skip» rejimiga kirmaydi; button/form/select — teg tashlanadi, matn qoladi; yopilmagan textarea qolgan hujjatni yutmaydi
ok("keep me" in PK.sanitize('<p>a</p><embed src=x><p>keep me</p>') and "<p>k</p>" in PK.sanitize('<frame src=x><param name=a><p>k</p>'),
   "Void teglar (embed, frame, param) tashlanadi, keyingi matn saqlanadi")
ok(PK.sanitize('<button>Bos</button><p>x</p>') == 'Bos<p>x</p>' and "<p>x</p>" in PK.sanitize('<button>Bos<p>x</p>')
   and "after" in PK.sanitize('<select><option>o</option><p>after</p>') and "<b>b</b>" in PK.sanitize('<form><input value=1>t</form><b>b</b>'),
   "button / select / form — teg tashlanadi, ichidagi va keyingi matn qoladi (yopilmagan bo'lsa ham)")
ok("rest" in PK.sanitize('<textarea>abc<p>rest</p>') and PK.html_unsafe(PK.sanitize('<textarea>abc<p>rest<script>x</script>')) is None
   and PK.sanitize('<script>bad()</script><p>ok</p>') == '<p>ok</p>' and PK.sanitize('<script>bad()') == '',
   "Yopilmagan textarea — matni escape qilinib qaytadi; script/style mazmuni bilan tashlanadi")
fig = PK.sanitize('<figure><img src="assets/img/ab12.png" alt="Sxema" onerror="x()" width="9"><figcaption>1.1-rasm. Sxema</figcaption></figure><p>a<img src="assets/img/c.jpg"/></p>')
ok(fig == '<figure><img src="assets/img/ab12.png" alt="Sxema"><figcaption>1.1-rasm. Sxema</figcaption></figure><p>a<img src="assets/img/c.jpg" alt=""></p>' and PK.html_unsafe(fig) is None,
   "figure / figcaption / img (faqat nisbiy assets/…, src + alt) — saqlanadi, audit o'tadi")
for bad_src in ("http://evil.com/x.png", "https://isft.uz/x.png", "//evil.com/x.png", "data:image/png;base64,AAAA", "javascript:alert(1)", "JaVaScRiPt:x",
                "/assets/img/x.png", "assets/../../etc/passwd", "assets//x.png", "assets/img/a b.png", "assets\\x.png", "img/x.png", " assets/x.png", "assets/x.png%00"):
    cl_ = PK.sanitize(f'<img src="{bad_src}" alt="x">')
    ok("<img" not in cl_ and PK.html_unsafe(f'<img src="{bad_src}">') is not None, f"img src {bad_src!r} — olib tashlanadi, audit rad etadi")
ok(PK.html_unsafe('<img alt="x">') and PK.html_unsafe('<img src="assets/img/a.png" onload="x">') and PK.html_unsafe('<figure class="x"></figure>'),
   "Audit: src siz img, img on* atributi, figure atributi — rad etiladi")
ok(PK.html_unsafe('<p onclick="x">a</p>') and PK.html_unsafe("<script>a</script>") and PK.html_unsafe('<a href="javascript:1">x</a>')
   and PK.html_unsafe('<a href="https://isft.uz" rel="noopener noreferrer" target="_blank">x</a>') is None, "Haqiqiy xavfli teg/atributlar ushlanadi (HTML tahlili bilan)")

# =============================================================================================
print("== 4. Ma'ruza matni → reja va tuzilgan HTML")
LECT = """5-MAVZU: TALAB VA TAKLIF
Reja:
1. Talab tushunchasi
2. Taklif qonuni

3. Bozor muvozanati

1. Talab tushunchasi
Talab — iste'molchilar sotib olishga tayyor bo'lgan tovar miqdori. Bu jumla
keyingi qatorda davom etadi.
Talab omillari:
- daromad
- did va afzalliklar
1.1. Talab egri chizig'i
Egri chiziq pastga qarab egilgan.
2. Taklif qonuni
Narx oshsa, taklif ortadi. **Muhim** tushuncha.
- Narx | Miqdor
- 10 | 100
- 20 | 200
3. Bozor muvozanati
<script>alert(1)</script> Muvozanat narxi.
"""
st = PK.structure_text(LECT, "Talab va taklif")
ok(st["plan"] == ["Talab tushunchasi", "Taklif qonuni", "Bozor muvozanati"] and st["explicit_plan"], f"«Reja:» bo'limidan reja: {st['plan']}")
h = st["html"]
ok("<h2>Talab tushunchasi</h2>" in h and "<h3>Talab egri chizig'i</h3>" in h and "<h2>Bozor muvozanati</h2>" in h, "Raqamli sarlavhalar: 1. → h2, 1.1. → h3")
ok("TALAB VA TAKLIF" not in h, "Mavzu nomi qatori matndan olib tashlandi (pleyer o'zi ko'rsatadi)")
ok("<ul><li>daromad</li><li>did va afzalliklar</li></ul>" in h, "Ro'yxat")
ok("<table><thead><tr><th>Narx</th><th>Miqdor</th></tr></thead>" in h, "« | » bilan ajratilgan qatorlar → jadval")
ok("bu jumla keyingi qatorda davom etadi." in h.lower(), "Uzilgan qatorlar bitta paragrafga")
ok("<strong>Muhim</strong>" in h and "&lt;script&gt;" in h and "<script" not in h, "**qalin** → strong; matndagi teglar qochiriladi")
ok("<p><strong>Talab omillari:</strong></p>" in h, "Qisqa «…:» qatori — qalin izoh")
st2 = PK.structure_text("# Kirish\nMatn.\n# Asosiy qism\nMatn2.\n## Kichik\n- a\n- b\n# Xulosa\nOxiri.")
ok(st2["plan"] == ["Kirish", "Asosiy qism", "Xulosa"] and not st2["explicit_plan"], "Reja yo'q — sarlavhalardan (Test bank «#» belgilari)")
ok(PK.structure_text("Режа: 1. Бозор 2. Талаб 3. Таклиф\nMatn.")["plan"] == ["Бозор", "Талаб", "Таклиф"], "Kirill «Режа:» bir qatorda")
ok(PK.structure_text("Reja:\nKirish\nAsosiy tushunchalar\nXulosa\n\nKirish\nMatn bu yerda.")["plan"] == ["Kirish", "Asosiy tushunchalar", "Xulosa"], "Raqamsiz reja qatorlari")
ok(PK.structure_text("IQTISODIYOT ASOSLARI\nBirinchi paragraf.\nIKKINCHI BO'LIM\nIkkinchi paragraf.")["plan"] == ["IQTISODIYOT ASOSLARI", "IKKINCHI BO'LIM"], "KATTA HARFLI qatorlar — sarlavha")
ok(PK.structure_text("Faqat bitta paragraf matni.")["plan"] == [], "Sarlavhasiz matn — reja bo'sh")
ok("<ol><li>Yer</li><li>Mehnat</li></ol>" in PK.structure_text("Omillar:\n1. Yer\n2. Mehnat\nMatn davom etadi.")["html"], "Ketma-ket «1. 2.» — raqamli ro'yxat (sarlavha emas)")
MARK = """1-MAVZU: AXBOROT
Reja:
1. Kirish
2. Asosiy qism
1. Kirish
Birinchi paragraf matni shu yerda.
[RASM:abc123.png]
1.1-rasm. Mini cho'ntak kompyuteri
[JADVAL:1]
[RASM:yoq999.png]
2. Asosiy qism
Ikkinchi paragraf.
Foydalanilgan adabiyotlar ro'yxati
1. Karimov I. Iqtisodiyot. T., 2020.
2. Sobirov A. Informatika
asoslari. T., 2019.
"""
mst = PK.structure_text(MARK, "Axborot", {"images": {"abc123.png": {"caption": ""}}, "tables": {"1": [["Birlik", "Qiymat"], ["bayt", "8 bit"]]}})
ok('<figure><img src="assets/img/abc123.png" alt="Mini cho&#x27;ntak kompyuteri"><figcaption>1.1-rasm. Mini cho\'ntak kompyuteri</figcaption></figure>' in mst["html"]
   and mst["images"] == ["abc123.png"] and "yoq999" not in mst["html"], "«[RASM:fayl]» → figure (keyingi «1.1-rasm.» qatori — izoh); noma'lum rasm tashlanadi")
ok("<table><thead><tr><th>Birlik</th><th>Qiymat</th></tr></thead><tbody><tr><td>bayt</td><td>8 bit</td></tr></tbody></table>" in mst["html"], "«[JADVAL:N]» → table (thead + tbody)")
ok(mst["refs"] == ["Karimov I. Iqtisodiyot. T., 2020.", "Sobirov A. Informatika asoslari. T., 2019."] and "Karimov" not in mst["html"] and "adabiyot" not in mst["html"].lower(),
   f"«Foydalanilgan adabiyotlar ro'yxati» → refs (uzilgan qator qo'shildi), matndan olib tashlandi: {mst['refs']}")
ok(mst["plan"] == ["Kirish", "Asosiy qism"] and PK.html_unsafe(mst["html"]) is None, "Reja va xavfsiz HTML (rasm, jadval bilan)")
ok(PK.structure_text("Matn bu yerda.\nFoydalanilgan adabiyotlar ro'yxati 1. A kitob. 2. B kitob.")["refs"] == ["A kitob.", "B kitob."], "Bir qatorda: «… ro'yxati 1. … 2. …»")
r_ = PK.structure_text("# Kirish\nMatn.\n# Adabiyotlar\n- A kitob\n- B kitob\n# Ilova\nX matn.")
ok(r_["refs"] == ["A kitob", "B kitob"] and "<h2>Ilova</h2>" in r_["html"], "«# Adabiyotlar» sarlavhasi — keyingi sarlavhagacha")
ok(PK.structure_text("Литература:\n1. Иванов И. Экономика.\n")["refs"] == ["Иванов И. Экономика."] and
   PK.structure_text("Adabiyotlar ro'yxati shuni ko'rsatadiki, mavzu muhim.")["refs"] == [], "Kirill «Литература»; oddiy gap — refs emas")
# regressiya: reja bandi «3. Foydalanilgan adabiyotlar» adabiyotlar sarlavhasi emas (matnni yutib yubormasin)
RJ = ("Reja:\n1. Kirish\n2. Asosiy tushunchalar\n3. Foydalanilgan adabiyotlar\n\n1. Kirish\nIqtisodiyot fani jamiyatdagi resurslar taqsimotini o'rganadi.\n"
      "2. Asosiy tushunchalar\nTalab va taklif bozorning asosiy tushunchalaridir.\n\nFoydalanilgan adabiyotlar\n1. Karimov I. Iqtisodiyot. T., 2020.\n2. Smith A. Wealth of Nations. 1776.")
rj = PK.structure_text(RJ, "x")
ok(rj["plan"] == ["Kirish", "Asosiy tushunchalar", "Foydalanilgan adabiyotlar"] and rj["refs"] == ["Karimov I. Iqtisodiyot. T., 2020.", "Smith A. Wealth of Nations. 1776."]
   and "resurslar taqsimotini" in rj["html"] and "<h2>Asosiy tushunchalar</h2>" in rj["html"] and "Karimov" not in rj["html"],
   f"Reja bandi «3. Foydalanilgan adabiyotlar» — reja (3 band), matn joyida, refs — haqiqiy ro'yxat ({rj['plan']}, {len(rj['refs'])} ta)")
rj2 = PK.structure_text("Reja:\n1. Kirish\n2. Xulosa\n\n3. Foydalanilgan adabiyotlar\n\n1. Kirish\nMatn birinchi.\n2. Xulosa\nMatn ikkinchi.\n"
                        "3. Foydalanilgan adabiyotlar\n- Karimov I. Iqtisodiyot.", "x")
ok(rj2["plan"] == ["Kirish", "Xulosa", "Foydalanilgan adabiyotlar"] and rj2["refs"] == ["Karimov I. Iqtisodiyot."] and "Matn ikkinchi." in rj2["html"],
   "Bo'sh qatordan keyin rejaning davomi (3.) ham reja; matndagi «3. Foydalanilgan adabiyotlar» — adabiyotlar")
# regressiya: adabiyotlar ro'yxati «Nazorat savollari» da tugaydi, qolgani matnga qaytadi
rq = PK.structure_text("Asosiy matn shu yerda yozilgan.\n\nFoydalanilgan adabiyotlar\n1. Karimov I. Iqtisodiyot. T., 2020.\n2. Smith A. Wealth of Nations.\n"
                       "Nazorat savollari:\n1. Talab nima?\n2. Taklif nima?", "x")
ok(rq["refs"] == ["Karimov I. Iqtisodiyot. T., 2020.", "Smith A. Wealth of Nations."] and "Nazorat savollari" in rq["html"]
   and "<ol><li>Talab nima?</li><li>Taklif nima?</li></ol>" in rq["html"] and rq["html"].index("Asosiy matn") < rq["html"].index("Nazorat savollari"),
   f"Adabiyotlar «Nazorat savollari:» da tugaydi — savollar matnda (asosiy matndan keyin): {rq['refs']}")
rq2 = PK.structure_text("Matn.\nAdabiyotlar\n1. A kitob.\n2. B kitob.\n\nShu bilan ma'ruza yakunlanadi, keyingi mavzuga tayyorlaning.", "x")
ok(rq2["refs"] == ["A kitob.", "B kitob."] and "keyingi mavzuga" in rq2["html"], "Ro'yxatdan keyin bo'sh qator va oddiy matn — matnga qaytadi")
rq3 = PK.structure_text("Matn.\nAsosiy adabiyotlar\n1. A kitob.\nQo'shimcha adabiyotlar\n1. B kitob.\nGlossariy\nTalab — xohish.", "x")
ok(rq3["refs"] == ["A kitob.", "B kitob."] and "Glossariy" in rq3["html"] and "Talab — xohish." in rq3["html"], "«Asosiy» + «Qo'shimcha adabiyotlar» — bitta ro'yxat; «Glossariy» matnda")
ok([bool(PK.CAPTION_RX.match(x)) for x in ("1.1-rasm. Mini kompyuter", "2 - rasm Sxema", "Rasm 3. Grafik", "Рисунок 2. Схема", "Rasmda ko'rsatilgan", "Rasm bu")] ==
   [True, True, True, True, False, False], "Rasm izohi: «1.1-rasm.», «Rasm 3.», «Рисунок 2.»; «Rasmda …» — izoh emas")

# =============================================================================================
print("== 5. PPTX tahlili (python-pptx, rasm bilan)")
def make_pptx(n_pic=True, title2="Ikkinchi slayd") -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    from PIL import Image
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1]); s.shapes.title.text = "Birinchi slayd"
    tf = s.placeholders[1].text_frame; tf.text = "Band A"; p = tf.add_paragraph(); p.text = "Band B"; p.level = 1
    s.notes_slide.notes_text_frame.text = "Ma'ruzachi izohi"
    s2 = prs.slides.add_slide(prs.slide_layouts[5]); s2.shapes.title.text = title2
    if n_pic:
        im = Image.new("RGB", (300, 200), (139, 0, 51)); bio = io.BytesIO(); im.save(bio, "PNG")
        s2.shapes.add_picture(io.BytesIO(bio.getvalue()), Inches(1), Inches(2), width=Inches(4))
    tb = s2.shapes.add_table(2, 2, Inches(5), Inches(2), Inches(4), Inches(1)).table
    tb.cell(0, 0).text, tb.cell(0, 1).text, tb.cell(1, 0).text, tb.cell(1, 1).text = "Narx", "Miqdor", "10", "100"
    out = io.BytesIO(); prs.save(out); return out.getvalue()
PPTX = make_pptx()
tmpd = Path(tempfile.mkdtemp(prefix="pkt-"))
pp = PK.parse_pptx(PPTX, tmpd / "img")
s1, s2 = pp["slides"]
ok(pp["count"] == 2 and s1["title"] == "Birinchi slayd" and s1["bullets"][0] == "Band A" and "Band B" in s1["bullets"][1], "Slayd sarlavhasi va bandlari")
ok(s1["notes"] == "Ma'ruzachi izohi", "Ma'ruzachi izohlari (notes)")
ok(s2["image"] == "s2.png" and (tmpd / "img" / "s2.png").is_file() and s1["image"] is None, "Ichidagi rasm ajratildi (assets/slides/s2.png)")
ok("Narx | Miqdor" in s2["bullets"], "Jadval qatorlari matnga")
try: PK.parse_pptx(b"PK\x03\x04 bu pptx emas"); ok(False, "buzilgan pptx o'tdi")
except PK.HTTPException as e: ok(e.status_code == 415, "Buzilgan .pptx — 415")
# zip / rasm bombalari — tahlildan OLDIN rad etiladi (413)
def with_entry(raw: bytes, name: str, data: bytes) -> bytes:
    bio = io.BytesIO(); bio.write(raw)
    with zipfile.ZipFile(bio, "a", zipfile.ZIP_DEFLATED) as z: z.writestr(name, data)
    return bio.getvalue()
BOMB = with_entry(PPTX, "ppt/media/bomb.bin", b"\0" * (40 * 1024 * 1024))   # 40 MB nol → ~40 KB (≈1000:1)
ok(len(BOMB) < 200_000, f"Sinov: yuqori siqish nisbatli .pptx ({len(BOMB)} bayt, ichida 40 MB)")
for fn, nm in ((lambda: PK.parse_pptx(BOMB), "parse_pptx"), (lambda: PK._sniff_asset(BOMB), "_sniff_asset")):
    try: fn(); ok(False, f"zip bombasi o'tdi ({nm})")
    except PK.HTTPException as e: ok(e.status_code == 413 and "siqilgan" in e.detail, f"Zip bombasi ({nm}) — 413: {e.detail}")
bio = io.BytesIO()
with zipfile.ZipFile(bio, "w", zipfile.ZIP_STORED) as z:
    for i in range(PK.ZIP_MAX_FILES + 1): z.writestr(f"x/{i}", b"")
try: PK._zip_guard(bio.getvalue()); ok(False, "ko'p qismli zip o'tdi")
except PK.HTTPException as e: ok(e.status_code == 413, f"Juda ko'p ichki fayl ({PK.ZIP_MAX_FILES + 1}) — 413")
def png_header(w: int, h: int) -> bytes:   # faqat sarlavha (dekodlanmaydi) — o'lchami katta «rasm bombasi»
    import struct, zlib
    ch = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + ch(b"IDAT", zlib.compress(b"\0" * 64)) + ch(b"IEND", b"")
for w, h in ((8000, 8000), (30000, 30000)):
    try: PK._norm_image(png_header(w, h), strict=True); ok(False, f"{w}×{h} PNG o'tdi")
    except PK.HTTPException as e: ok(e.status_code == 413 and "megapiksel" in e.detail, f"{w}×{h} PNG (dekodlanmasdan) — 413")
ok(PK._norm_image(png_header(8000, 8000)) is None, "PPTX ichidagi katta rasm — o'tkazib yuboriladi (None)")
ok(PK._sniff_asset(PPTX) == "pptx" and PK._sniff_asset(b"%PDF-1.4") == "pdf" and PK._sniff_asset(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1xx") == "ole", "Fayl turi sehrli baytlar bo'yicha")

# =============================================================================================
print("== 6. Manbalar (HTTP)")
C1 = own["id"]   # o'qituvchining o'z kursi
T = 4
r = teach.post(f"{P}/courses/{C1}/topics/{T}/text/paste", json={"text": LECT * 2})
ok(r.status_code == 200 and r.json()["plan"] == ["Talab tushunchasi", "Taklif qonuni", "Bozor muvozanati"], f"Matn joylashtirildi, reja ajratildi ({r.status_code})")
def make_docx() -> bytes:
    import docx
    d = docx.Document(); d.add_heading("Mavzu: Bozor", 1); d.add_paragraph("Reja:")
    for x in ("Bozor tushunchasi", "Bozor turlari"): d.add_paragraph(x, style="List Number")
    d.add_heading("1. Bozor tushunchasi", 2); d.add_paragraph("Bozor — xaridor va sotuvchi uchrashadigan joy. " * 6)
    d.add_heading("2. Bozor turlari", 2); d.add_paragraph("Raqobatli va monopol bozorlar mavjud. " * 6)
    bio = io.BytesIO(); d.save(bio); return bio.getvalue()
r = teach.post(f"{P}/courses/{C1}/topics/{T + 1}/text", params={"name": "bozor.docx"}, content=make_docx())
ok(r.status_code == 200 and r.json()["plan"] == ["Bozor tushunchasi", "Bozor turlari"], f"Word (.docx) yuklandi, reja: {r.json().get('plan') if r.status_code == 200 else r.text[:120]}")
ok(teach.post(f"{P}/courses/{C1}/topics/{T}/text", params={"name": "x.exe"}, content=b"MZ\x00\x00binary").status_code == 415, "Noto'g'ri fayl — 415")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/slides", params={"name": "taqdimot.pptx"}, content=PPTX)
ok(r.status_code == 200 and r.json()["kind"] == "pptx" and r.json()["count"] == 2 and r.json()["images"] == 1, f"PPTX yuklandi va tahlil qilindi ({r.text[:120]})")
ok(teach.post(f"{P}/courses/{C1}/topics/{T}/slides", params={"name": "eski.ppt"}, content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100).status_code == 415, "Eski .ppt — 415")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/slides", params={"name": "bomba.pptx"}, content=BOMB)
ok(r.status_code == 413 and "siqilgan" in r.json().get("detail", ""), f"HTTP: zip bombali .pptx — 413 ({r.status_code})")
ok(teach.post(f"{P}/courses/{C1}/topics/{T}/files", params={"name": "bomba.pptx"}, content=BOMB).status_code == 413, "HTTP: qo'shimcha fayl sifatida ham — 413")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/text", params={"name": "bomba.docx"}, content=with_entry(make_docx(), "word/media/bomb.bin", b"\0" * (40 * 1024 * 1024)))
ok(r.status_code == 413, f"HTTP: zip bombali .docx (ma'ruza matni) — 413 ({r.status_code})")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/text", params={"name": "rasm.docx"}, content=with_entry(make_docx(), "word/media/image9.png", png_header(9000, 9000)))
ok(r.status_code == 413 and "megapiksel" in r.json().get("detail", ""), f"HTTP: .docx ichida 81 Mpx rasm — 413 ({r.status_code})")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/slides", params={"name": "katta.png"}, content=png_header(9000, 9000))
ok(r.status_code == 413 and "megapiksel" in r.json().get("detail", ""), f"HTTP: 9000×9000 PNG slayd — 413 ({r.status_code})")
def chunks(total, size=1024 * 1024):   # Content-Length'siz (Transfer-Encoding: chunked) tana
    sent = 0
    while sent < total:
        n = min(size, total - sent); sent += n; yield b"\0" * n
try:
    r = teach.post(f"{P}/courses/{C1}/topics/{T}/files", params={"name": "katta.bin"}, content=chunks(PK.MAX_ASSET + 3 * 1024 * 1024))
    code = r.status_code
except httpx.HTTPError as e:   # server 413 ni yuborib ulanishni yopsa — mijoz yozishda uzilishi mumkin
    code = f"uzildi ({type(e).__name__})"
ok(code == 413 or str(code).startswith("uzildi"), f"HTTP: Content-Length'siz (chunked) {PK.MAX_ASSET // 1048576 + 3} MB tana — 413 ({code})")
class _EndlessReq:   # cheksiz oqim (Content-Length yo'q): _read_body chegarada to'xtashi va qolganini o'qimasligi kerak
    headers = {}
    def __init__(self): self.n = 0
    async def stream(self):
        while True:
            self.n += 1; yield b"\0" * (1024 * 1024)
import asyncio
er = _EndlessReq()
try: asyncio.run(PK._read_body(er)); ok(False, "cheksiz oqim o'qildi")
except PK.HTTPException as e: ok(e.status_code == 413 and er.n == PK.MAX_ASSET // (1024 * 1024) + 1, f"_read_body: cheksiz chunked oqim chegarada (≈{er.n} MB) to'xtatildi — 413")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/files", params={"name": "kichik.pdf"}, content=(x for x in [b"%PDF-1.4\n", b"%%EOF\n"]))
ok(r.status_code == 200, f"HTTP: kichik chunked yuklash ishlaydi ({r.status_code})")
if r.status_code == 200: teach.post(f"{P}/assets/{r.json()['id']}/delete")
ok(not q("SELECT id FROM pk_assets WHERE course_id=? AND name IN ('bomba.pptx','bomba.docx','rasm.docx','katta.png','katta.bin')", (C1,)), "Rad etilgan fayllar saqlanmadi")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/video", json={"url": f"https://youtu.be/{ID}?t=12"})
ok(r.status_code == 200 and r.json()["url"] == f"https://www.youtube.com/watch?v={ID}&t=12s", "Video havola saqlandi (kanonik)")
ok(teach.post(f"{P}/courses/{C1}/topics/{T}/video", json={"url": "https://youtu.be/xyz"}).status_code == 400, "Noto'g'ri YouTube ID — 400")
tv = teach.get(f"{P}/courses/{C1}/topics/{T}").json()
ok(tv["ready"]["text"]["ok"] and tv["ready"]["text"]["src"] == "paket" and tv["ready"]["slides"]["src"] == "pptx" and tv["ready"]["video"]["video_id"] == ID,
   "Tayyorgarlik: matn (shu yerda), taqdimot (.pptx), video")
ok(tv["plan"] == ["Talab tushunchasi", "Taklif qonuni", "Bozor muvozanati"] and "<h2>" in tv["text_html"] and "<script" not in tv["text_html"], "Mavzu ko'rinishida reja va tozalangan HTML")
ok(len(tv["slides"]) == 2 and tv["slides"][1]["image"], "Slaydlar ro'yxati")
mk_r = kaf8.get(f"{P}/courses/{mikro['id']}/topics/1").json()
ok(mk_r["ready"]["text"]["demo"] and mk_r["ready"]["plan"]["explicit"] and mk_r["ready"]["slides"]["src"] == "pptx" and mk_r["ready"]["quiz"]["approved"] > 0,
   "Namuna mavzu: matn (reja bilan), taqdimot, Test bankdagi tasdiqlangan savollar")
# avtomatik joylash
LINKS = f"https://youtu.be/{ID}\nhttps://www.youtube.com/watch?v=aaaaaaaaaaa\n7: https://youtu.be/bbbbbbbbbbb\nhttps://youtu.be/bad"
r = teach.post(f"{P}/courses/{C1}/bulk/videos", json={"text": LINKS, "apply": False}).json()
ok([(x["topic_no"], x["ok"]) for x in r["rows"]] == [(1, True), (2, True), (7, True), (8, False)] and not r["applied"], "Avtomatik joylash: tekshirish (saqlanmaydi)")
before = q("SELECT COUNT(*) n FROM pk_topics WHERE course_id=? AND video_url IS NOT NULL", (C1,))[0]["n"]
r = teach.post(f"{P}/courses/{C1}/bulk/videos", json={"text": LINKS, "apply": True}).json()
vids = {x["topic_no"]: x["video_url"] for x in q("SELECT topic_no, video_url FROM pk_topics WHERE course_id=?", (C1,))}
ok(r["assigned"] == 3 and vids.get(1) == f"https://www.youtube.com/watch?v={ID}" and vids.get(2) == "https://www.youtube.com/watch?v=aaaaaaaaaaa"
   and vids.get(7) == "https://www.youtube.com/watch?v=bbbbbbbbbbb" and not vids.get(8), f"Avtomatik joylash: 3 ta mavzuga saqlandi (oldin {before})")
ok(kaf.post(f"{P}/courses/{C1}/bulk/videos", json={"text": LINKS, "apply": True}).status_code == 403, "Kafedra mudiri ommaviy joylay olmaydi (403)")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/settings", json={"mode": "scorm2004", "quiz_n": 3, "mastery": 70}).json()
ok(r["settings"]["mode"] == "scorm2004" and r["settings"]["quiz_n"] == 3 and r["override"].get("mastery") == 70, "Mavzu sozlamasi saqlandi (standartdan farqi)")
r = teach.post(f"{P}/courses/{C1}/topics/{T}/settings", json={"reset": True}).json()
ok(r["override"] == {} and r["settings"]["mode"] == m["defaults"]["mode"], "Standartga qaytarildi")

# =============================================================================================
print("== 6b. Darslar (L/A), Word rasmlari, PDF slaydlar, xulosalar (HTTP)")
def png_bytes(color, size=(480, 320)) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, color); d = ImageDraw.Draw(im)
    if min(size) > 60: d.rectangle([20, 20, size[0] - 20, size[1] - 20], outline="white", width=6)
    bio = io.BytesIO(); im.save(bio, "PNG"); return bio.getvalue()
def make_rich_docx() -> bytes:
    """Word: sarlavha, reja, 2 rasm (1-izohi keyin, 2-izohi oldin), jadval, «Foydalanilgan adabiyotlar» ro'yxati, ikonka (tashlanadi)."""
    import docx
    from docx.shared import Inches
    d = docx.Document()
    d.add_heading("1-MAVZU: AXBOROT TEXNOLOGIYALARI", 1)
    d.add_paragraph("Reja:")
    for x in ("Kompyuter turlari", "Axborot o'lchov birliklari", "Xulosa"): d.add_paragraph(x, style="List Number")
    d.add_heading("1. Kompyuter turlari", 2)
    d.add_paragraph("Kompyuterlar o'lchami va vazifasiga ko'ra bir necha turga bo'linadi. Eng kichigi — cho'ntak kompyuteri. " * 3)
    d.add_picture(io.BytesIO(png_bytes((139, 0, 51))), width=Inches(3))
    d.add_paragraph("1.1-rasm. Mini cho'ntak kompyuteri")
    d.add_picture(io.BytesIO(png_bytes((0, 0, 0), (20, 20))), width=Inches(0.2))      # ikonka — tashlanadi
    d.add_heading("2. Axborot o'lchov birliklari", 2)
    d.add_paragraph("Axborot o'lchov birliklari jadvalda keltirilgan. Bayt — sakkiz bitdan iborat asosiy o'lchov birligi.")
    t = d.add_table(rows=3, cols=2)
    for i, (a_, b_) in enumerate((("Birlik", "Qiymati"), ("1 bayt", "8 bit"), ("1 KB", "1024 bayt"))):
        t.cell(i, 0).text, t.cell(i, 1).text = a_, b_
    d.add_paragraph("1.2-rasm. Axborot uzatish sxemasi")
    d.add_picture(io.BytesIO(png_bytes((0, 90, 140))), width=Inches(3))
    d.add_heading("3. Xulosa", 2)
    d.add_paragraph("Axborot texnologiyalari zamonaviy jamiyatning asosidir va har bir sohada qo'llaniladi.")
    d.add_paragraph("Foydalanilgan adabiyotlar ro'yxati")
    for x in ("Karimov I. Informatika asoslari. T.: Fan, 2020.", "Sobirov A. Axborot texnologiyalari. T., 2019."): d.add_paragraph(x, style="List Number")
    bio = io.BytesIO(); d.save(bio); return bio.getvalue()
def make_pdf(n=3) -> bytes:
    from PIL import Image, ImageDraw
    pages = []
    for i in range(n):
        im = Image.new("RGB", (960, 540), (255, 255, 255)); dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 960, 80], fill=(139, 0, 51)); dr.text((40, 200), f"Slayd {i + 1}", fill=(0, 0, 0)); pages.append(im)
    bio = io.BytesIO(); pages[0].save(bio, "PDF", save_all=True, append_images=pages[1:]); return bio.getvalue()
RICH, PDF3 = make_rich_docx(), make_pdf(3)
dx = PK.docx_lecture(RICH)
ok(len(dx["images"]) == 2 and [v["caption"] for v in dx["images"].values()] == ["1.1-rasm. Mini cho'ntak kompyuteri", "1.2-rasm. Axborot uzatish sxemasi"],
   f"Word: 2 rasm hujjat tartibida, izohlari (keyingi va oldingi paragraf); ikonka tashlandi ({len(dx['images'])})")
ok(dx["tables"] == {"1": [["Birlik", "Qiymati"], ["1 bayt", "8 bit"], ["1 KB", "1024 bayt"]]}, "Word: jadval qatorlari/kataklari saqlandi")
order = [l for l in dx["text"].split("\n") if l.startswith("[")]
ok(len(order) == 3 and order[0].startswith("[RASM:") and order[1] == "[JADVAL:1]" and order[2].startswith("[RASM:") and "rasm." not in dx["text"],
   f"Word: rasm → jadval → rasm tartibi, izoh paragraflari matndan olindi ({order})")
ok(all(re.fullmatch(r"[0-9a-f]{20}\.png", fn) for fn in dx["images"]), "Rasm nomi — sha256 (assets/img/<hash>.png)")
from PIL import Image as _I
big = io.BytesIO(); _I.new("RGB", (3200, 2000), (10, 120, 60)).save(big, "PNG")
ok(max(_I.open(io.BytesIO(PK._norm_image(big.getvalue())[0])).size) == 1600, "Katta rasm 1600 px gacha kichraytiriladi")
# regressiya: <w:b w:val="0"/> (qalin EMAS) — qisqa qator paragraf bo'lib qoladi; <w:b/> va qalin belgi uslubi (rStyle) — sarlavha
def make_bold_docx() -> bytes:
    import docx
    from docx.enum.style import WD_STYLE_TYPE
    d = docx.Document()
    st = d.styles.add_style("QalinBelgi", WD_STYLE_TYPE.CHARACTER); st.font.bold = True
    p_ = d.add_paragraph(); r_ = p_.add_run("Qalin emas qisqa qator"); r_.bold = False
    p_ = d.add_paragraph(); r_ = p_.add_run("Haqiqiy qalin sarlavha"); r_.bold = True
    p_ = d.add_paragraph(); r_ = p_.add_run("Uslubdan qalin sarlavha"); r_.style = st
    p_ = d.add_paragraph(); r_ = p_.add_run("Uslubi qalin, lekin o'chirilgan"); r_.style = st; r_.bold = False
    d.add_paragraph("Oddiy uzun paragraf matni shu yerda davom etadi va nuqta bilan tugaydi.")
    bio = io.BytesIO(); d.save(bio); return bio.getvalue()
BD = make_bold_docx()
with zipfile.ZipFile(io.BytesIO(BD)) as z_: _dx = z_.read("word/document.xml").decode()
bl = PK.docx_lecture(BD)["text"].split("\n")
ok('w:val="0"' in _dx and bl[:4] == ["Qalin emas qisqa qator", "## Haqiqiy qalin sarlavha", "## Uslubdan qalin sarlavha", "Uslubi qalin, lekin o'chirilgan"],
   f"Word: <w:b w:val=\"0\"/> — paragraf; <w:b/> va qalin rStyle — sarlavha ({bl[:4]})")
# PDF: pdfium qulfi va sahifani chizishdagi xato → 415
import pypdfium2 as _pdfium, threading as _th
_orig_render, _orig_gw = _pdfium.PdfPage.render, _pdfium.PdfPage.get_width
_locked = []
def _spy_render(self, *a, **kw): _locked.append(PK._PDFIUM_LOCK.locked()); return _orig_render(self, *a, **kw)
_pdfium.PdfPage.render = _spy_render
try:
    _res, _errs = [], []
    def _rp():
        try: _res.append(len(PK.render_pdf(make_pdf(3))["images"]))
        except Exception as e: _errs.append(repr(e))
    _ts = [_th.Thread(target=_rp) for _ in range(4)]
    [t_.start() for t_ in _ts]; [t_.join() for t_ in _ts]
    ok(_res == [3, 3, 3, 3] and not _errs and _locked and all(_locked), f"render_pdf: 4 oqimda parallel — hammasi 3 sahifa, chizish doim _PDFIUM_LOCK ostida ({_res}, {_errs[:1]})")
    def _bad_render(self, *a, **kw): raise _pdfium.PdfiumError("Failed to render page")
    _pdfium.PdfPage.render = _bad_render
    try: PK.render_pdf(make_pdf(2)); ok(False, "chizish xatosi yutildi")
    except PK.HTTPException as e: ok(e.status_code == 415 and "rasmga aylantirib bo'lmadi" in e.detail and not PK._PDFIUM_LOCK.locked(), f"Sahifani chizishda pdfium xatosi → 415 ({e.detail[:70]}…), qulf bo'shatildi")
    _pdfium.PdfPage.get_width = lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    try: PK.render_pdf(make_pdf(1)); ok(False, "get_width xatosi yutildi")
    except PK.HTTPException as e: ok(e.status_code == 415, "Sahifa o'lchamini o'qishdagi xato → 415")
finally:
    _pdfium.PdfPage.render, _pdfium.PdfPage.get_width = _orig_render, _orig_gw
# HTTP: darslar ro'yxati
LTXT = "A1- AMALIY MASHG'ULOT: Excel bilan ishlash (2-mavzu)\nA2- Amaliy: Word hujjatlari\nS1 Seminar: Muhokama\nnoto'g'ri qator"
r = teach.post(f"{P}/courses/{C1}/lessons", json={"text": LTXT, "apply": False}).json()
ok([(x["code"], x["ok"]) for x in r["rows"]] == [("A1", True), ("A2", True), ("S1", True), (None, False)] and not r["applied"], "HTTP: darslar ro'yxati — tekshirish (saqlanmaydi)")
ok(kaf.post(f"{P}/courses/{C1}/lessons", json={"text": LTXT, "apply": True}).status_code == 403 and rek.get(f"{P}/courses/{C1}/lessons").status_code == 403
   and teach.post(f"{P}/courses/{mikro['id']}/lessons", json={"text": LTXT, "apply": True}).status_code == 403, "Darslar ro'yxati: kafedra/rektor/begona o'qituvchi — 403")
r = teach.post(f"{P}/courses/{C1}/lessons", json={"text": LTXT, "apply": True}).json()
codes = [x["code"] for x in r["lessons"]]
ok(r["saved"] == 3 and {"A1", "A2", "S1"} <= set(codes) and codes.index("L1") < codes.index("A1") < codes.index("S1") and
   next(x for x in r["lessons"] if x["code"] == "A1")["topic"] == 2, "HTTP: darslar saqlandi (L…, A1, A2, S1 tartibda; A1 → 2-mavzu)")
cv_ = teach.get(f"{P}/courses/{C1}").json()
ok(any(t_["code"] == "A2" and t_["no"] == 1002 and t_["kind"] == "amaliy" for t_ in cv_["topics"]) and cv_["course"]["lessons"] == len(cv_["topics"]), "Kurs ko'rinishida A darslar (kalit 1002)")
ok(teach.get(f"{P}/courses/{C1}/topics/1009").status_code == 400, "Yo'q dars (A9) — 400")
A1 = 1001
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/text", params={"name": "amaliy1.docx"}, content=RICH)
ok(r.status_code == 200 and r.json()["images"] == 2 and r.json()["tables"] == 1 and r.json()["refs"] == 2 and r.json()["plan"] == ["Kompyuter turlari", "Axborot o'lchov birliklari", "Xulosa"],
   f"HTTP: A1 ga Word — 2 rasm, 1 jadval, 2 adabiyot, reja ({r.text[:160]})")
ok(len(q("SELECT id FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='rasm' AND deleted=0", (C1, A1))) == 2, "Rasmlar pk_assets'da (purpose='rasm')")
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
ok(tv["lesson"]["code"] == "A1" and tv["heading"] == "1-AMALIY MASHG'ULOT: Excel bilan ishlash" and tv["ready"]["images"]["n"] == 2 and tv["ready"]["refs"]["n"] == 2
   and tv["text_html"].count("<figure>") == 2 and "<table>" in tv["text_html"] and tv["file_name"].endswith("_A01_" + tv["settings"]["mode"] + ".zip"),
   "Dars ko'rinishi: sarlavha, 2 rasm, jadval, adabiyotlar, fayl nomi …_A01_…")
im_url = re.search(r'src="(/api/paket/courses/[^"]+/img/[0-9a-f]{20}\.png)"', tv["text_html"])
ok(im_url and teach.get(im_url.group(1)).status_code == 200 and teach.get(im_url.group(1)).headers["content-type"] == "image/png" and rek.get(im_url.group(1)).status_code == 403,
   "Ilovada rasm ko'rinadi (ko'lam bilan; rektor — 403)")
ok(not any(a_["purpose"] == "rasm" for a_ in tv["assets"]), "Word ichidagi rasmlar fayllar ro'yxatini to'ldirmaydi")
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/images", params={"name": "sxema.png", "caption": "1.3-rasm. Qo'lda yuklangan sxema"}, content=png_bytes((200, 120, 0)))
ok(r.status_code == 200 and r.json()["marker"].startswith("[RASM:") and r.json()["caption"].startswith("1.3-rasm"), f"HTTP: qo'lda rasm — {r.json().get('marker')}")
ok(teach.post(f"{P}/courses/{C1}/topics/{A1}/images", params={"name": "x.pdf"}, content=b"%PDF-1.4 x").status_code == 415, "Rasm emas — 415")
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
ok(tv["text_html"].count("<figure>") == 3 and "Qo'lda yuklangan sxema" in tv["text_html"] and any(a_["purpose"] == "rasm" and a_.get("marker") for a_ in tv["assets"]),
   "Qo'lda yuklangan (havolasiz) rasm matn oxirida; fayllar ro'yxatida marker bilan")
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/slides", params={"name": "taqdimot.pdf"}, content=PDF3)
ok(r.status_code == 200 and r.json()["kind"] == "pdf" and r.json()["count"] == 3 and r.json()["images"] == 3, f"HTTP: PDF taqdimot → 3 slayd rasmi ({r.text[:120]})")
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
ok(tv["ready"]["slides"]["src"] == "pdf" and tv["ready"]["slides"]["display"] == "images" and tv["ready"]["slides"]["n"] == 3, "Tayyorgarlik: slaydlar PDF rasmlaridan (display=images)")
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/slides", params={"name": "taqdimot.pptx"}, content=PPTX)
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
ok(tv["ready"]["slides"]["src"] == "pptx" and tv["ready"]["slides"]["file"] and not tv["ready"]["slides"]["pdf"],
   f"PDF'dan KEYIN .pptx yuklandi — .pptx ishlatiladi, eskirgan PDF rasmlari/fayli paketga kirmaydi ({tv['ready']['slides']['src']})")
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/slides", params={"name": "taqdimot2.pdf"}, content=PDF3)
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
pdfs = q("SELECT deleted FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND kind='pdf' ORDER BY id", (C1, A1))
ok(tv["ready"]["slides"]["src"] == "pdf" and tv["ready"]["slides"]["file"] and tv["ready"]["slides"]["pdf"] and tv["ready"]["slides"]["n"] == 3
   and [x["deleted"] for x in pdfs][-2:] == [2, 0] and sum(1 for a_ in tv["assets"] if a_["purpose"] == "taqdimot" and a_["kind"] == "pdf") == 1,
   "PPTX'dan keyin PDF — PDF rasmlari ustun, .pptx yuklab olish uchun; eski PDF «almashtirildi» (deleted=2, ro'yxatda yo'q)")
ok(teach.post(f"{P}/courses/{C1}/topics/{A1}/slides", params={"name": "buzuq.pdf"}, content=b"%PDF-1.4\nbuzilgan").status_code == 415, "Buzilgan PDF — 415")
if not os.environ.get("ANTHROPIC_API_KEY"):
    r = teach.post(f"{P}/courses/{C1}/topics/{A1}/keypoints/ai")
    ok(r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"], "AI xulosalar: kalit yo'q — 503 (aniq xabar)")
ok(kaf.post(f"{P}/courses/{C1}/topics/{A1}/keypoints/ai").status_code == 403 and kaf.post(f"{P}/courses/{C1}/topics/{A1}/keypoints", json={"items": ["x"], "approve": True}).status_code == 403,
   "AI / xulosalar: kafedra mudiri — 403")
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/keypoints", json={"items": ["Kompyuterlar turlarga bo'linadi.", "Bayt — 8 bit."], "approve": True})
ok(r.status_code == 200 and r.json()["keypoints"]["approved"]["items"] == ["Kompyuterlar turlarga bo'linadi.", "Bayt — 8 bit."], "Xulosalar qo'lda yozildi va tasdiqlandi")
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
ok([b_["type"] for b_ in tv["blocks"]] == ["section", "plan", "text", "keypoints", "refs", "section", "slides", "file", "reflect"],
   f"A1 bloklari shablon tartibida: {[b_['type'] for b_ in tv['blocks']]}")

# =============================================================================================
print("== 7. Yig'ish (jarayon ichida: bazaning nusxasi + soxta pleyer)")
from app import rbac as RB
tmp = Path(tempfile.mkdtemp(prefix="pkbuild-"))
srcc = sqlite3.connect(DBP); dst = sqlite3.connect(tmp / "copy.db", check_same_thread=False); srcc.backup(dst); srcc.close()
dst.row_factory = sqlite3.Row
import shutil
srv_store = Path(os.environ.get("ISFT_CORE_DATA_DIR") or DBP.parent) / "paket"     # server fayllari (namuna .pptx) — nusxada ham bo'lsin
if srv_store.is_dir(): shutil.copytree(srv_store, tmp / "store")
fake = tmp / "player"; (fake / "css").mkdir(parents=True)
(fake / "index.html").write_text('<!doctype html><html><head><link rel="stylesheet" href="css/p.css"></head><body><div id="app"></div>'
                                 '<script src="content.js"></script><script src="player.js"></script></body></html>')
(fake / "player.js").write_text("/* soxta pleyer */ console.log(window.PAKET.id);")
(fake / "css" / "p.css").write_text("body{margin:0}")
(fake / ".DS_Store").write_text("x"); (fake / "content.js").write_text("window.PAKET = {};")   # e'tiborsiz qoldirilishi kerak
saved = (PK.PLAYER_DIR, PK.STORE, PK._con, PK._ctx)
try:
    PK.PLAYER_DIR, PK.STORE = fake, tmp / "store"
    PK.bind(dst, None)
    hctx = RB.ctx_for(dst, head_uid); tctx = RB.ctx_for(dst, teach_uid)
    MID = mikro["id"]
    # migratsiya — idempotent (ikkinchi marta hech narsa o'zgarmaydi)
    snap = lambda: (dst.execute("SELECT COUNT(*), COUNT(lesson), GROUP_CONCAT(lesson) FROM pk_packages").fetchone()[:], dst.execute("SELECT COUNT(*) FROM pk_lessons").fetchone()[0],
                    dst.execute("SELECT v FROM pk_meta WHERE k='defaults'").fetchone()[0])
    dst.execute("UPDATE pk_packages SET lesson=NULL WHERE id IN (SELECT id FROM pk_packages ORDER BY id LIMIT 3)"); dst.commit()
    m1 = PK.migrate(dst); s1 = snap(); m2 = PK.migrate(dst); s2 = snap()
    ok(s1 == s2 and m2["packages"] == 0 and m2["columns"] == [] and not m2["defaults"] and s1[0][0] == s1[0][1], f"Migratsiya idempotent: 1-marta {m1['packages']} qator, 2-marta 0; barcha paketlarda lesson ustuni")
    ok(all(re.fullmatch(r"L\d+|kurs", x[0]) for x in dst.execute("SELECT lesson FROM pk_packages WHERE topic_no<1000")), "Eski mavzu paketlari — L darslar (lesson='L<N>', kurs paketi — 'kurs')")
    tmpm = sqlite3.connect(":memory:"); tmpm.executescript(PK.SCHEMA)          # 3-bosqich sxemasi (lesson/keypoints ustunlarisiz)
    tmpm.executescript("INSERT INTO pk_packages(course_id,topic_no,version) VALUES(1,3,1),(1,0,1);")
    tmpm.execute("INSERT INTO pk_meta VALUES('defaults', ?)", (json.dumps({**PK._OLD_DEFAULTS, "blocks": {}}),))
    o1 = PK.migrate(tmpm); o2 = PK.migrate(tmpm)
    ok(o1["columns"] == ["pk_topics.keypoints", "pk_packages.lesson"] and o1["packages"] == 2 and o1["defaults"] and o2 == {"columns": [], "packages": 0, "defaults": False}
       and [r_[0] for r_ in tmpm.execute("SELECT lesson FROM pk_packages ORDER BY id")] == ["L3", "kurs"] and json.loads(tmpm.execute("SELECT v FROM pk_meta WHERE k='defaults'").fetchone()[0])["mode"] == "xapi",
       "Eski sxemadan migratsiya: ustunlar qo'shildi, L3/kurs, o'zgartirilmagan standart → xAPI; qayta — o'zgarishsiz")
    tmpm.close()
    zips = {}
    for mode in ("scorm12", "scorm2004", "xapi", "none"):
        r = PK.build_topic(hctx, MID, 1, mode)
        p = r["package"]
        data = (PK.store() / dst.execute("SELECT file FROM pk_packages WHERE id=?", (p["id"],)).fetchone()[0]).read_bytes()
        zips[mode] = data
        v = PK.validate_zip(data)
        ok(v["ok"] and v["mode"] == mode and p["mode"] == mode and p["status"] == "tayyor", f"{mode}: yig'ildi va validate_zip o'tdi ({v['files']} fayl, {p['size']} bayt){'' if v['ok'] else v['errors']}")
    z = zipfile.ZipFile(io.BytesIO(zips["scorm12"]))
    names = set(z.namelist())
    ok({"index.html", "player.js", "css/p.css", "content.js", "content.json", "assets/logo.png", "imsmanifest.xml", "assets/taqdimot.pptx"} <= names, "Zip ildizi: pleyer, content.js/json, assets, manifest")
    ok(".DS_Store" not in names and z.read("content.js").startswith(b"window.PAKET = {") and z.read("content.js").endswith(b"};"), "Pleyer papkasidagi yashirin fayl va eski content.js olinmaydi")
    cj = json.loads(z.read("content.js").decode()[len("window.PAKET = "):-1])
    ok(cj == json.loads(z.read("content.json")), "content.js va content.json bir xil JSON")
    ok(cj["v"] == 1 and re.fullmatch(rf"isft-{MID}-1-v\d+", cj["id"]) and cj["lang"] == "uz" and cj["topic"]["no"] == 1 and cj["course"]["subject"] == "Mikroiqtisodiyot"
       and cj["brand"]["logo"] == "assets/logo.png" and cj["brand"]["color"] == "#8B0033", "Kontrakt: v, id, lang, course, topic, brand")
    types = [b["type"] for b in cj["blocks"]]
    ok(types == ["section", "video", "section", "plan", "text", "section", "slides", "quiz", "reflect"] and [b["id"] for b in cj["blocks"]] == [f"b{i}" for i in range(1, len(types) + 1)],
       f"Bloklar tartibi (kafedra shabloni) va id: {types}")
    ok([b["title"] for b in cj["blocks"] if b["type"] == "section"] == ["VIDEODARS", "MA'RUZA MATNI", "DARS TAQDIMOTI"], "Bo'lim sarlavhalari: VIDEODARS, MA'RUZA MATNI, DARS TAQDIMOTI")
    pb_ = next(b for b in cj["blocks"] if b["type"] == "plan")
    ok(pb_["heading"].startswith("1-MAVZU: ") and pb_["heading"] == pb_["heading"].upper() and len(pb_["items"]) == 4, f"Reja bloki: heading «{pb_['heading'][:40]}…» + 4 band")
    rb_ = cj["blocks"][-1]
    ok(rb_["question"] == "Darsni to'liq o'zlashtirdingizmi?" and [o["text"] for o in rb_["options"]] == ["Ha, albatta", "Yo'q, to'liq o'zlashtirmadim"]
       and rb_["options"][1]["feedback"] == "Ma'ruza matni va videodarsni qayta ko'rib chiqing.", "Reflect bloki (baholanmaydi): savol, 2 javob, izohlar")
    ok(cj["layout"] == "steps" and cj["lesson"] == {"code": "L1", "kind": "maruza", "no": 1, "title": cj["title"]} and cj["topic"]["no"] == 1, "Kontrakt v2: layout=steps, lesson {code L1, kind maruza}, topic saqlangan")
    sb = next(b for b in cj["blocks"] if b["type"] == "slides")
    ok(sb["file"] == "assets/taqdimot.pptx" and sb["pdf"] is None and len(sb["slides"]) == 4 and sb["display"] == "text" and all(s["image"] is None or s["image"] in names for s in sb["slides"]), "Slaydlar bloki: .pptx fayl, rasm yo'llari zip ichida")
    vb = next(b for b in cj["blocks"] if b["type"] == "video")
    ok(vb["provider"] == "youtube" and vb["video_id"] == "ISFTdemo001" and vb["start"] == 0, "Video bloki (namuna ID)")
    qb = next(b for b in cj["blocks"] if b["type"] == "quiz")
    apprn = dst.execute("SELECT COUNT(*) FROM tb_questions WHERE course_id=? AND topic_no=1 AND status='tasdiqlandi' AND deleted=0", (MID,)).fetchone()[0]
    ok(len(qb["questions"]) == apprn and all(re.fullmatch(r"q\d+", x["id"]) and x["type"] in ("mcq", "tf", "fill") for x in qb["questions"]) and qb["pass_pct"] == 60,
       f"Test bloki: faqat tasdiqlangan savollar ({apprn} ta)")
    ok(cj["tracking"] == {"mode": "scorm12", "completion": "view_and_quiz", "mastery": 60, "activity_id": f"https://isft.uz/xapi/paket/{MID}/1"}, "tracking")
    tb_ = next(b for b in cj["blocks"] if b["type"] == "text")
    ok("<script" not in tb_["html"] and "<h2>" in tb_["html"], "Matn bloki — tozalangan HTML")
    # SCORM 1.2 manifest
    NS = {"c": "http://www.imsproject.org/xsd/imscp_rootv1p1p2", "a": "http://www.adlnet.org/xsd/adlcp_rootv1p2"}
    root = ET.fromstring(z.read("imsmanifest.xml"))
    ok(root.find("c:metadata/c:schema", NS).text == "ADL SCORM" and root.find("c:metadata/c:schemaversion", NS).text == "1.2", "SCORM 1.2: schema / schemaversion")
    item = root.find("c:organizations/c:organization/c:item", NS); res = root.find("c:resources/c:resource", NS)
    ok(root.find("c:organizations", NS).get("default") == root.find("c:organizations/c:organization", NS).get("identifier"), "SCORM 1.2: organizations@default")
    ok(item.get("identifierref") == res.get("identifier") and res.get("{%s}scormtype" % NS["a"]) == "sco" and res.get("href") == "index.html", "SCORM 1.2: item → resource (sco, index.html)")
    ok(item.find("a:masteryscore", NS).text == "60", "SCORM 1.2: adlcp:masteryscore")
    listed = {f.get("href") for f in res.findall("c:file", NS)}
    ok(listed == names - {"imsmanifest.xml"}, "SCORM 1.2: barcha fayllar <file> da")
    # SCORM 2004
    z4 = zipfile.ZipFile(io.BytesIO(zips["scorm2004"]))
    N4 = {"c": "http://www.imsglobal.org/xsd/imscp_v1p1", "a": "http://www.adlnet.org/xsd/adlcp_v1p3", "s": "http://www.imsglobal.org/xsd/imsss"}
    r4 = ET.fromstring(z4.read("imsmanifest.xml"))
    ok(r4.find("c:metadata/c:schemaversion", N4).text == "2004 4th Edition", "SCORM 2004: schemaversion «2004 4th Edition»")
    res4 = r4.find("c:resources/c:resource", N4); it4 = r4.find("c:organizations/c:organization/c:item", N4)
    ok(res4.get("{%s}scormType" % N4["a"]) == "sco" and it4.find("s:sequencing/s:deliveryControls", N4) is not None, "SCORM 2004: adlcp:scormType=sco, imsss:deliveryControls")
    mm = it4.find("s:sequencing/s:objectives/s:primaryObjective/s:minNormalizedMeasure", N4)
    ok(mm is not None and mm.text == "0.60" and r4.find("c:organizations/c:organization/s:sequencing/s:controlMode", N4).get("flow") == "true", "SCORM 2004: minNormalizedMeasure 0.60, controlMode")
    ok({f.get("href") for f in res4.findall("c:file", N4)} == set(z4.namelist()) - {"imsmanifest.xml"}, "SCORM 2004: barcha fayllar <file> da")
    # xAPI
    zx = zipfile.ZipFile(io.BytesIO(zips["xapi"]))
    TC = {"t": "http://projecttincan.com/tincan.xsd"}
    rx = ET.fromstring(zx.read("tincan.xml")); act = rx.find("t:activities/t:activity", TC)
    ok(act.get("id") == f"https://isft.uz/xapi/paket/{MID}/1" and act.find("t:launch", TC).text == "index.html" and act.find("t:name", TC).get("lang") == "uz",
       "xAPI: tincan.xml activity id = tracking.activity_id, launch index.html, lang uz")
    ok("imsmanifest.xml" not in zx.namelist() and "tincan.xml" not in zipfile.ZipFile(io.BytesIO(zips["none"])).namelist(), "xAPI — faqat tincan.xml; oddiy HTML — manifestsiz")
    # deterministik
    g = PK.gather(MID, 1)
    content = {"v": 1, "id": "isft-test-v1", **{k: v for k, v in g["content"].items() if k != "v"}, "built": "2026-11-11T10:00:00"}
    a1, a2 = PK.build_zip(content, g["files"], "scorm12"), PK.build_zip(json.loads(json.dumps(content)), dict(g["files"]), "scorm12")
    ok(PK._sha(a1) == PK._sha(a2), f"Deterministik: bir xil kirish → bir xil sha256 ({PK._sha(a1)[:12]}…)")
    ok(all(zi.date_time == (1980, 1, 1, 0, 0, 0) for zi in zipfile.ZipFile(io.BytesIO(a1)).infolist()) and
       zipfile.ZipFile(io.BytesIO(a1)).namelist() == sorted(zipfile.ZipFile(io.BytesIO(a1)).namelist()), "Zip yozuvlari tartiblangan, vaqti qotirilgan")
    r = PK.build_topic(hctx, MID, 1, "none")
    ok(r["unchanged"], "Manba o'zgarmasa qayta yig'ish yangi versiya yaratmaydi")
    # versiyalar: oxirgi 3 ta (+ tasdiqlangani)
    PK.package_action(hctx, dst.execute("SELECT id FROM pk_packages WHERE course_id=? AND topic_no=1 ORDER BY version DESC", (MID,)).fetchone()[0], "approve")
    for i in range(4): PK.build_topic(hctx, MID, 1, "xapi", force=True)
    vers = [dict(x) for x in dst.execute("SELECT version, mode, status, file FROM pk_packages WHERE course_id=? AND topic_no=1 ORDER BY version", (MID,))]
    xv = [v["version"] for v in vers if v["mode"] == "xapi"]
    mx = max(xv)
    ok(xv[-3:] == [mx - 2, mx - 1, mx] and len(xv) == 3 and any(v["status"] == "tasdiqlandi" for v in vers),
       f"Versiyalar: har bir tur bo'yicha oxirgi 3 ta + tasdiqlangani saqlanadi (xAPI: {xv})")
    ok({"scorm12", "scorm2004", "none"} <= {v["mode"] for v in vers}, "Bir turni ko'p yig'ish boshqa turlarning paketlarini o'chirmaydi")
    files = sorted(p.name for p in (PK.store() / "packages" / str(MID) / "1").glob("*.zip"))
    ok(len(files) == len(vers) and all((PK.store() / v["file"]).is_file() for v in vers), f"Eski versiya fayllari o'chirildi ({len(files)} ta qoldi)")
    r = PK.build_topic(hctx, MID, 1, "scorm12")
    ok(r["unchanged"] and r["package"]["mode"] == "scorm12", "Boshqa tur yig'ilgandan keyin ham o'zgarishsiz qayta yig'ish — o'sha turdagi mavjud versiya")
    # o'qituvchi: begona kurs / tasdiqlash
    try: PK.build_topic(tctx, MID, 1); ok(False, "o'qituvchi begona kursni yig'di")
    except RB.AccessDenied: ok(True, "O'qituvchi begona kurs paketini yig'olmaydi")
    # shablon sozlamasi: bo'lim nomlari, layout, reflect o'chirish (dars bo'yicha)
    PK.set_topic_settings(hctx, MID, 2, {"layout": "scroll", "sections": {"video": "VIDEO DARS"}, "blocks": {"reflect": False, "sections": True},
                                         "reflect": {"question": "Tushundingizmi?", "options": [{"text": "Ha"}]}})
    g2 = PK.gather(MID, 2)["content"]
    ok(g2["layout"] == "scroll" and g2["blocks"][0] == {"id": "b1", "type": "section", "title": "VIDEO DARS"} and all(b["type"] != "reflect" for b in g2["blocks"]),
       "Dars sozlamasi: layout=scroll, bo'lim nomi o'zgardi, reflect o'chirildi (1 javobli reflect — e'tiborsiz)")
    PK.set_topic_settings(hctx, MID, 2, {"blocks": {"sections": False}}, reset=True)
    PK.set_topic_settings(hctx, MID, 2, {"blocks": {"sections": False, "reflect": True}})
    ok(all(b["type"] != "section" for b in PK.gather(MID, 2)["content"]["blocks"]), "Bo'lim sarlavhalari o'chirilishi mumkin")
    PK.set_topic_settings(hctx, MID, 2, {}, reset=True)
    # amaliy dars (A1 — namuna ro'yxatdan): Word (rasmlar, jadval, adabiyotlar), PDF slaydlar, AI xulosalar (soxta Claude)
    from app import claude_client as CC
    AK = 1001
    ok(any(l_["code"] == "A1" and l_["topic"] == 1 for l_ in PK.lessons(MID)), "Namuna: Mikroiqtisodiyot A1, A2 (NEXTID uslubi)")
    PK.upload_text(hctx, MID, AK, RICH, None, "amaliy1.docx")
    PK.upload_slides(hctx, MID, AK, PDF3, "taqdimot.pdf")
    src_txt = PK._plain(PK._text_source(MID, AK)["text"])
    calls = []
    def fake_call_json(**kw):
        calls.append(kw)
        return {"points": [{"text": "Kompyuterlar o'lchami va vazifasiga ko'ra turlarga bo'linadi.", "quote": "Kompyuterlar o'lchami va vazifasiga ko'ra bir necha turga bo'linadi"},
                           {"text": "Bayt sakkiz bitdan iborat.", "quote": "Bayt — sakkiz bitdan iborat asosiy o'lchov birligi"},
                           {"text": "Kvant kompyuterlari 1950-yilda yaratilgan.", "quote": "Kvant kompyuterlari 1950-yilda yaratilgan"},     # matnda yo'q — tashlanadi
                           {"text": "Axborot texnologiyalari jamiyat asosidir.", "quote": "Axborot texnologiyalari zamonaviy jamiyatning asosidir"},
                           {"text": "Bo'sh iqtibos", "quote": ""}]}, {"in": 1200, "out": 300, "model": "claude-opus-5-5"}
    saved_cc = (CC.call_json, CC.has_key)
    try:
        CC.has_key = lambda: False
        try: PK.ai_keypoints(hctx, MID, AK); ok(False, "kalitsiz AI chaqirildi")
        except PK.HTTPException as e: ok(e.status_code == 503 and "ANTHROPIC_API_KEY" in e.detail, "AI kalitsiz — 503, o'zbekcha aniq xabar")
        CC.has_key = lambda: True; CC.call_json = fake_call_json
        r = PK.ai_keypoints(hctx, MID, AK)
        ok([i["text"] for i in r["draft"]["items"]] == ["Kompyuterlar o'lchami va vazifasiga ko'ra turlarga bo'linadi.", "Bayt sakkiz bitdan iborat.", "Axborot texnologiyalari jamiyat asosidir."]
           and r["dropped"] == 2, f"AI xulosalar: matnda topilmagan iqtibosli 2 ta band tashlandi ({r['dropped']})")
        kw = calls[-1]
        sent = kw["content"][0]["text"]
        ok(kw["model"] == "claude-opus-5-5" and kw["schema"]["properties"]["points"]["items"]["required"] == ["text", "quote"] and kw["schema"]["additionalProperties"] is False
           and "Bayt — sakkiz bitdan" in sent and "[RASM:" not in sent and "[JADVAL:" not in sent, "AI so'rovi: model, qat'iy sxema; faqat dars matni (belgilarsiz) yuboriladi")
        ok(not re.search(r"talaba|student|baho|ism", sent.split("MA'RUZA MATNI:")[0], re.I), "AI so'roviga talaba ma'lumoti qo'shilmaydi")
        ok(all(b["type"] != "keypoints" for b in PK.gather(MID, AK)["content"]["blocks"]), "Qoralama xulosa paketga kirmaydi (tasdiq kerak)")
        PK.save_keypoints(hctx, MID, AK, [i["text"] for i in r["draft"]["items"]][:2] + ["O'qituvchi qo'shgan xulosa."], approve=True)
        def boom(**kw): raise CC.AIError("AI xizmati hozir band (so'rovlar cheklovi).")
        CC.call_json = boom
        try: PK.ai_keypoints(hctx, MID, AK); ok(False, "AI xatosi yutildi")
        except PK.HTTPException as e: ok(e.status_code == 502 and "band" in e.detail, "AI xatosi — 502, tasdiqlangan xulosalar saqlanib qoladi")
        os.environ["ISFT_CORE_PK_DAILY"] = "1"
        try: PK.ai_keypoints(hctx, MID, AK); ok(False, "kunlik cheklov ishlamadi")
        except PK.HTTPException as e: ok(e.status_code == 429, "Kunlik cheklov (ISFT_CORE_PK_DAILY) — 429")
        os.environ.pop("ISFT_CORE_PK_DAILY", None)
    finally:
        CC.call_json, CC.has_key = saved_cc
    ga = PK.gather(MID, AK)
    ca = ga["content"]
    ok([b["type"] for b in ca["blocks"]] == ["section", "plan", "text", "keypoints", "refs", "section", "slides", "file", "quiz", "reflect"]
       and ga["ready"]["quiz"]["approved"] == dst.execute("SELECT COUNT(*) FROM tb_questions WHERE course_id=? AND topic_no=1 AND status='tasdiqlandi' AND deleted=0", (MID,)).fetchone()[0] > 0,
       f"A1 (1-mavzuga bog'langan) bloklari — test 1-mavzu savollaridan: {[b['type'] for b in ca['blocks']]}")
    kb = next(b for b in ca["blocks"] if b["type"] == "keypoints"); rfb = next(b for b in ca["blocks"] if b["type"] == "refs")
    ok(kb["items"][-1] == "O'qituvchi qo'shgan xulosa." and len(kb["items"]) == 3 and rfb["items"] == ["Karimov I. Informatika asoslari. T.: Fan, 2020.", "Sobirov A. Axborot texnologiyalari. T., 2019."],
       "keypoints (tasdiqlangan, tahrirlangan) va refs bloklari")
    ok(ca["lesson"] == {"code": "A1", "kind": "amaliy", "no": 1, "title": ca["title"]} and ca["tracking"]["activity_id"] == f"https://isft.uz/xapi/paket/{MID}/A1"
       and next(b for b in ca["blocks"] if b["type"] == "plan")["heading"].startswith("1-AMALIY MASHG'ULOT: "), "A1: lesson, activity_id …/A1, reja sarlavhasi")
    slb = next(b for b in ca["blocks"] if b["type"] == "slides")
    ok(slb["display"] == "images" and [x_["image"] for x_ in slb["slides"]] == ["assets/slides/p1.jpg", "assets/slides/p2.jpg", "assets/slides/p3.jpg"] and slb["pdf"] == "assets/taqdimot.pdf",
       "PDF → slayd rasmlari (pypdfium2): display=images, 3 ta p*.jpg")
    _I2 = _I.open(Path(ga["files"]["assets/slides/p1.jpg"])); ok(_I2.size[0] == 1600 and _I2.format == "JPEG", f"Slayd rasmi ~1600 px kenglikda ({_I2.size})")
    for mode in ("xapi", "scorm12", "scorm2004", "none"):
        r = PK.build_topic(hctx, MID, AK, mode)
        data = (PK.store() / dst.execute("SELECT file FROM pk_packages WHERE id=?", (r["package"]["id"],)).fetchone()[0]).read_bytes()
        v = PK.validate_zip(data)
        za = zipfile.ZipFile(io.BytesIO(data)); cja = json.loads(za.read("content.json"))
        tbx = next(b for b in cja["blocks"] if b["type"] == "text")
        imgs_ = re.findall(r'<img src="(assets/img/[0-9a-f]{20}\.png)"', tbx["html"])
        ok(v["ok"] and len(imgs_) == 2 and all(x_ in za.namelist() for x_ in imgs_) and tbx["html"].count("<figcaption>") == 2 and "<table>" in tbx["html"]
           and PK.html_unsafe(tbx["html"]) is None and r["package"]["lesson"] == "A1", f"A1 {mode}: validate_zip o'tdi, 2 rasm zip ichida, izohlar, jadval{'' if v['ok'] else v['errors']}")
        if mode == "xapi":
            ok("index.html" in za.namelist() and "tincan.xml" in za.namelist() and "imsmanifest.xml" not in za.namelist()
               and ET.fromstring(za.read("tincan.xml")).find("{http://projecttincan.com/tincan.xsd}activities/{http://projecttincan.com/tincan.xsd}activity").get("id").endswith("/A1"),
               "NEXTID (xAPI): zip ildizida index.html + tincan.xml, activity …/A1")
    zt = PK.zip_bytes({**{n_: zipfile.ZipFile(io.BytesIO(data)).read(n_) for n_ in zipfile.ZipFile(io.BytesIO(data)).namelist()}})
    bad_c = json.loads(zipfile.ZipFile(io.BytesIO(zt)).read("content.json"))
    for b in bad_c["blocks"]:
        if b["type"] == "text" and b["title"] == "Ma'ruza matni": b["html"] += '<img src="assets/img/yoq.png" alt="">'
    ent = {n_: zipfile.ZipFile(io.BytesIO(zt)).read(n_) for n_ in zipfile.ZipFile(io.BytesIO(zt)).namelist()}; ent["content.js"] = PK.content_js(bad_c)
    v = PK.validate_zip(PK.zip_bytes(ent))
    ok(not v["ok"] and any("assets/img/yoq.png" in x_ for x_ in v["errors"]), "Validator: matndagi rasm zip ichida yo'q — xato")
    for b in bad_c["blocks"]:
        if b["type"] == "text" and b["title"] == "Ma'ruza matni": b["html"] = '<p>x</p><img src="https://evil.com/x.png">'
    ent["content.js"] = PK.content_js(bad_c)
    ok(not PK.validate_zip(PK.zip_bytes(ent))["ok"], "Validator: tashqi rasm (http) — xavfli HTML")
    ok(PK.download_name(mikro, AK, "xapi") == "ISFT_Mikroiqtisodiyot_A01_xapi.zip" and PK.download_name(mikro, 3002, "scorm12") == "ISFT_Mikroiqtisodiyot_Lab02_scorm12.zip",
       "Fayl nomi: ISFT_<fan>_A01_xapi.zip, …_Lab02_…")
    # kurs paketi
    PK.build_topic(hctx, MID, 2, "scorm12")
    for mode in ("scorm12", "scorm2004", "xapi"):
        r = PK.build_course(hctx, MID, mode)
        ok(r["validation"]["ok"] and r["validation"]["scos"] == 3 and r["package"]["topic_no"] == 0, f"Kurs paketi ({mode}): 3 ta SCO (L1, L2, A1), validate_zip o'tdi")
    kz = zipfile.ZipFile(PK.store() / dst.execute("SELECT file FROM pk_packages WHERE course_id=? AND topic_no=0 AND mode='scorm2004' ORDER BY version DESC", (MID,)).fetchone()[0])
    kr = ET.fromstring(kz.read("imsmanifest.xml"))
    hrefs = [x.get("href") for x in kr.iter("{http://www.imsglobal.org/xsd/imscp_v1p1}resource")]
    ok(hrefs == ["t01/index.html", "t02/index.html", "a01/index.html"] and json.loads(kz.read("t02/content.json"))["tracking"]["mode"] == "scorm2004",
       f"Kurs paketi: har dars o'z papkasida (t01, t02, a01), tracking.mode qayta yozildi ({hrefs})")
    r = PK.build_course(hctx, MID, "scorm12", only_approved=True)
    ok(r["topics"] == [{"no": 1, "code": "L1", "version": r["topics"][0]["version"], "status": "tasdiqlandi"}], "Kurs paketi: faqat tasdiqlangan darslar")
    # validator — buzilgan paketlar
    def tamper(fn):
        zin = zipfile.ZipFile(io.BytesIO(zips["scorm12"])); ent = {n: zin.read(n) for n in zin.namelist()}; fn(ent); return PK.zip_bytes(ent)
    v = PK.validate_zip(tamper(lambda e: e.pop("player.js")))
    ok(not v["ok"] and any("player.js" in x for x in v["errors"]), "Validator: manifestdagi fayl yo'q")
    v = PK.validate_zip(tamper(lambda e: e.__setitem__("../evil.txt", b"x")))
    ok(not v["ok"] and any(".." in x for x in v["errors"]), "Validator: «..» yo'l")
    v = PK.validate_zip(tamper(lambda e: e.__setitem__("index.html", e["index.html"].replace(b"</body>", b'<script src="https://cdn.evil.com/x.js"></script></body>'))))
    ok(not v["ok"] and any("tashqi skript" in x for x in v["errors"]), "Validator: tashqi skript")
    v = PK.validate_zip(tamper(lambda e: e.__setitem__("index.html", e["index.html"].replace(b"</body>", b'<script src="https://www.youtube.com/iframe_api"></script></body>'))))
    ok(not any("tashqi skript" in x for x in v["errors"]), "Validator: YouTube iframe API ruxsat")
    v = PK.validate_zip(tamper(lambda e: e.__setitem__("content.js", b"var x = 1;")))
    ok(not v["ok"] and any("content.js" in x for x in v["errors"]), "Validator: content.js shakli")
    v = PK.validate_zip(tamper(lambda e: e.__setitem__("imsmanifest.xml", e["imsmanifest.xml"].replace(b'identifier="RES-1"', b'identifier="ITEM-1"'))))
    ok(not v["ok"] and any("takror" in x for x in v["errors"]), "Validator: takroriy identifikator")
    v = PK.validate_zip(tamper(lambda e: e.__setitem__("content.js", e["content.js"].replace(b"assets/logo.png", b"assets/yoq.png"))))
    ok(not v["ok"] and any("yoq.png" in x for x in v["errors"]), "Validator: content.js dagi asset zip ichida yo'q")
    ok(not PK.validate_zip(b"bu zip emas")["ok"], "Validator: zip emas")
    # XML qochirish
    co_x = PK.manifest_scorm12("ISFT-1", 'A & B <"c">', [{"ident": "S", "title": "T & <x>", "href": "index.html", "prefix": "", "mastery": None}], ["index.html"])
    ok(ET.fromstring(co_x).find("{http://www.imsproject.org/xsd/imscp_rootv1p1p2}organizations/{http://www.imsproject.org/xsd/imscp_rootv1p1p2}organization/"
                               "{http://www.imsproject.org/xsd/imscp_rootv1p1p2}title").text == 'A & B <"c">', "Manifest: XML qochirish")
    # ko'rish (preview) — yo'l xavfsizligi va CSP
    pid = dst.execute("SELECT id FROM pk_packages WHERE course_id=? AND topic_no=1 ORDER BY version DESC", (MID,)).fetchone()[0]
    resp = PK.preview_file(hctx, pid, "index.html")
    ok(resp.status_code == 200 and "frame-src" in resp.headers["content-security-policy"] and "youtube-nocookie.com" in resp.headers["content-security-policy"]
       and "default-src 'none'" in resp.headers["content-security-policy"] and resp.headers["x-content-type-options"] == "nosniff", "Preview: qat'iy CSP (youtube-nocookie ruxsat)")
    csp = resp.headers["content-security-policy"]
    sb = next((d.strip() for d in csp.split(";") if d.strip().startswith("sandbox")), "")
    ok(sb.split()[0] == "sandbox" and "allow-scripts" in sb and "allow-same-origin" not in csp, f"Preview: CSP sandbox, allow-same-origin YO'Q ({sb})")
    sc = next(d.strip() for d in csp.split(";") if d.strip().startswith("script-src"))
    ok(sc == "script-src 'self'" and "frame-src https://www.youtube-nocookie.com" in csp, f"Preview: script-src faqat 'self', YouTube — faqat frame-src ({sc})")
    ok("sandbox" in PK.preview_file(hctx, pid, "content.js").headers["content-security-policy"], "Preview: har bir javobda (yangi oynada ochilsa ham) sandbox")
    rr = PK.preview_redirect(hctx, pid, "index.html"); tk = rr.headers["location"].split("/")[-2]
    c_, p_ = PK.preview_ctx(tk)
    ok(rr.status_code == 302 and p_ == pid and c_.user["id"] == head_uid, "Imzolangan token: paket va foydalanuvchi tiklanadi")
    for bad_tok, why in ((PK.preview_token(pid, head_uid, exp=1), "muddati o'tgan"), (tk[:-1] + ("0" if tk[-1] != "0" else "1"), "imzo buzilgan"),
                         (PK.preview_token(pid, uid("rektor")), "rektor (WORK emas)")):
        try: PK.preview_ctx(bad_tok); ok(False, f"token o'tdi: {why}")
        except PK.HTTPException as e: ok(e.status_code == 403, f"Imzolangan token rad etildi: {why} — 403")
    foreign = dst.execute("SELECT p.id FROM pk_packages p JOIN dl_courses c ON c.id=p.course_id WHERE c.teacher_id!=? ORDER BY p.id LIMIT 1", (teach_tid,)).fetchone()
    if foreign:
        tc, tp = PK.preview_ctx(PK.preview_token(foreign[0], teach_uid))
        try: PK.preview_file(tc, tp, "index.html"); ok(False, "begona paket token bilan ochildi")
        except RB.AccessDenied: ok(True, "Token bilan ham ko'lam qayta tekshiriladi: o'qituvchi begona kurs paketini ocholmaydi")
    for bad in ("../../etc/passwd", "/etc/passwd", "assets/../../copy.db", "..\\x", "C:/win.ini"):
        try: PK.preview_file(hctx, pid, bad); ok(False, f"preview {bad} o'tdi")
        except PK.HTTPException as e: ok(e.status_code == 400, f"Preview: {bad!r} — 400")
    try: PK.preview_file(hctx, pid, "yoq.html"); ok(False, "yo'q fayl")
    except PK.HTTPException as e: ok(e.status_code == 404, "Preview: zip ichida yo'q fayl — 404")
    ok(PK.download_name(mikro, 5, "scorm12") == "ISFT_Mikroiqtisodiyot_L05_scorm12.zip" and PK.download_name({"subject": "Iqtisodiyotda o'yinlar nazariyasi"}, 0, "xapi") ==
       "ISFT_Iqtisodiyotda_oyinlar_nazariyasi_kurs_xapi.zip" and PK.download_name({"subject": "Бизнес-план"}, 1, "scorm2004") == "ISFT_Biznes_plan_L01_scorm2004.zip",
       "Yuklab olish nomi: ISFT_<fan>_<dars kodi L01/A01>_<tur>.zip (ASCII)")
    # to'g'ri / noto'g'ri savol — har doim ["To'g'ri", "Noto'g'ri"], [0] = to'g'ri (bazada teskari saqlangan bo'lsa ham)
    tfq = dst.execute("SELECT id FROM tb_questions WHERE course_id=? AND topic_no=1 AND qtype='tf' AND status='tasdiqlandi' AND deleted=0 LIMIT 1", (MID,)).fetchone()
    ok(PK._tf_correct(["Noto'g'ri", "To'g'ri"], [1]) == 0 and PK._tf_correct(["Noto‘g‘ri", "To‘g‘ri"], [0]) == 1 and PK._tf_correct(PK.TF_OPTIONS, [1]) == 1,
       "tf: javob variant matni bo'yicha me'yorlanadi")
    if tfq:
        dst.execute("UPDATE tb_questions SET options=?, correct=? WHERE id=?", (json.dumps(["Noto'g'ri", "To'g'ri"]), "[1]", tfq[0]))
        qq = next(x for x in next(b for b in PK.gather(MID, 1)["content"]["blocks"] if b["type"] == "quiz")["questions"] if x["id"] == f"q{tfq[0]}")
        ok(qq["options"] == ["To'g'ri", "Noto'g'ri"] and qq["correct"] == [0], "tf: teskari saqlangan savol paketda [\"To'g'ri\",\"Noto'g'ri\"] / [0]")
        dst.execute("UPDATE tb_questions SET options=?, correct=? WHERE id=?", (json.dumps(PK.TF_OPTIONS), "[0]", tfq[0]))
    # haqiqiy pleyer bilan uchidan-uchigacha (brauzer: PW va CHROME berilganda)
    if (saved[0] / "index.html").is_file():
        PK.PLAYER_DIR = saved[0]
        integ = tmp / "integ"
        PK.upload_text(hctx, MID, 1, RICH, None, "1-mavzu.docx")          # brauzerda rasm, jadval, adabiyotlar, xulosalar ham ko'rinsin
        PK.save_keypoints(hctx, MID, 1, ["Kompyuterlar turlarga bo'linadi.", "Bayt — 8 bit."], approve=True)
        PK.upload_slides(hctx, MID, 1, make_pdf(4), "taqdimot.pdf")       # .pptx (4 slayd) + PDF (4 bet) — galereya, sarlavhalar .pptx dan
        sl1 = next(b for b in PK.gather(MID, 1)["content"]["blocks"] if b["type"] == "slides")
        ok(sl1["display"] == "images" and sl1["slides"][0]["title"] == "Iqtisodiyot fani predmeti" and sl1["file"] == "assets/taqdimot.pptx",
           "Bir xil taqdimotning .pptx va PDF'i: PDF rasmlari + .pptx sarlavha/izohlari, .pptx yuklab olish uchun")
        for mode in ("scorm12", "scorm2004", "xapi"):
            r = PK.build_topic(hctx, MID, 1, mode, force=True)
            ok(r["validation"]["ok"], f"Haqiqiy pleyer bilan {mode} paketi validate_zip dan o'tdi")
            zipfile.ZipFile(PK.store() / dst.execute("SELECT file FROM pk_packages WHERE id=?", (r["package"]["id"],)).fetchone()[0]).extractall(integ / mode)
        PK.PLAYER_DIR = fake
        if os.environ.get("PW") and os.environ.get("CHROME"):
            import subprocess
            pr = subprocess.run(["node", str(ROOT / "tools" / "paket_build_check.js"), str(integ)], capture_output=True, text=True, timeout=600)
            print("\n".join("  " + x for x in pr.stdout.strip().splitlines()[-40:]))
            ok(pr.returncode == 0, "Brauzer: haqiqiy paket mock LMS'da — barcha bloklar, test, holat/ball, konsol xatosiz (tools/paket_build_check.js)")
        else:
            print("  · brauzer sinovi o'tkazib yuborildi (PW va CHROME muhit o'zgaruvchilari berilmagan)")
    # --- dars → manba mavzusi (topic_ref): zaxira matn / video / test bog'langan mavzudan; o'z manbalari ustun
    PK.save_lessons(hctx, MID, "A7- Amaliy: Bog'langan dars (2-mavzu)\nA8- Amaliy: Bog'lanmagan dars", True)
    A7, A8 = 1007, 1008
    dst.execute("UPDATE dl_items SET url='https://youtu.be/dQw4w9WgXcQ' WHERE course_id=? AND topic_no=2 AND kind='video'", (MID,)); dst.commit()
    q2 = dst.execute("SELECT COUNT(*) FROM tb_questions WHERE course_id=? AND topic_no=2 AND status='tasdiqlandi' AND deleted=0", (MID,)).fetchone()[0]
    l7 = PK.lesson_info(mikro, A7)
    ok(l7["topic"] == 2 and PK.source_topic(l7) == 2 and PK.source_topic(PK.lesson_info(mikro, A8)) is None and PK.source_topic(PK.lesson_info(mikro, 3)) == 3,
       "source_topic: bog'langan → topic_ref, L → o'z raqami, bog'lanmagan A → yo'q")
    g7 = PK.gather(MID, A7)
    ok(q2 > 0 and g7["ready"]["quiz"]["approved"] == q2 and any(b["type"] == "quiz" for b in g7["content"]["blocks"]), f"A7 (2-mavzu): Test bank 2-mavzu tasdiqlangan savollari ({q2} ta)")
    ok(g7["ready"]["video"]["src"] == "monitoring" and g7["ready"]["video"]["video_id"] == "dQw4w9WgXcQ" and g7["ready"]["text"]["src"] == "testbank",
       "A7: o'z manbasi yo'q — kontent monitoringi videosi va Test bank matni 2-mavzudan")
    g8 = PK.gather(MID, A8)
    ok(not g8["ready"]["quiz"]["approved"] and not g8["ready"]["video"]["ok"] and not g8["ready"]["text"]["ok"], "A8 (bog'lanmagan): zaxira manba yo'q")
    rd_ = PK.readiness_map()
    ok(rd_.get((MID, A7), {}).get("quiz") and rd_.get((MID, A7), {}).get("video") and rd_.get((MID, A7), {}).get("text") and not any((rd_.get((MID, A8)) or {}).values()),
       "Qamrov (readiness_map) bog'lanishni hisobga oladi: A7 — test/video/matn bor, A8 — yo'q")
    PK.set_video(hctx, MID, A7, "https://youtu.be/aaaaaaaaaaa")
    PK.upload_text(hctx, MID, A7, None, "Amaliy mashg'ulotning o'z matni. Talabalar talab egri chizig'ini chizadi va taklif bilan solishtiradi. " * 2, "a7.txt")
    g7 = PK.gather(MID, A7)
    ok(g7["ready"]["video"]["src"] == "paket" and g7["ready"]["video"]["video_id"] == "aaaaaaaaaaa" and g7["ready"]["text"]["src"] == "paket" and g7["ready"]["quiz"]["approved"] == q2,
       "A7: o'z videosi va matni ustun (zaxira emas), test — 2-mavzudan")
    # --- taqdimot manbasi: eng oxirgi yuklangan; eski taqdimot (o'sha tur) «almashtirildi»
    PK.upload_slides(hctx, MID, A7, PPTX, "t1.pptx"); PK.upload_slides(hctx, MID, A7, PDF3, "t1.pdf")
    g7 = PK.gather(MID, A7)
    ok(g7["ready"]["slides"]["src"] == "pdf" and "assets/taqdimot.pdf" in g7["files"] and "assets/taqdimot.pptx" in g7["files"], ".pptx → .pdf: PDF rasmlari, .pptx yuklab olish uchun")
    PK.upload_slides(hctx, MID, A7, PPTX, "t2.pptx")
    g7 = PK.gather(MID, A7)
    tq = dst.execute("SELECT name, deleted, path FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot' ORDER BY id", (MID, A7)).fetchall()
    ok(g7["ready"]["slides"]["src"] == "pptx" and not g7["ready"]["slides"]["pdf"] and "assets/taqdimot.pdf" not in g7["files"]
       and not any(k_.startswith("assets/slides/p") for k_ in g7["files"]), ".pdf → .pptx: .pptx ishlatiladi, eskirgan PDF rasmlari va fayli paketga kirmaydi")
    ok([(x_[0], x_[1]) for x_ in tq] == [("t1.pptx", 2), ("t1.pdf", 0), ("t2.pptx", 0)] and (PK.store() / tq[0][2]).is_file(),
       "Yangi .pptx — eski .pptx «almashtirildi» (deleted=2, fayl diskda qoladi); PDF (boshqa tur) tegilmaydi")
    # --- PDF chizish xatosi → 415 + audit
    _pdfium.PdfPage.render = _bad_render
    try:
        try: PK.upload_slides(hctx, MID, A8, PDF3, "buzuq.pdf"); ok(False, "chizish xatosi yutildi")
        except PK.HTTPException as e:
            au = dst.execute("SELECT allowed, detail FROM audit_log WHERE action='paket: PDF taqdimot rad etildi' ORDER BY id DESC LIMIT 1").fetchone()
            ok(e.status_code == 415 and au and au[0] == 0 and "buzuq.pdf" in au[1] and not dst.execute("SELECT 1 FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='taqdimot'", (MID, A8)).fetchone(),
               "PDF chizishda xato — 415, audit jurnalida (rad etildi), fayl saqlanmadi")
    finally:
        _pdfium.PdfPage.render = _orig_render
    # --- ommaviy yig'ish: topics None / [] — barcha darslar; darslar ro'yxati bir marta quriladi
    calls_l = []
    _orig_lessons = PK.lessons
    PK.lessons = lambda *a, **kw: (calls_l.append(1), _orig_lessons(*a, **kw))[1]
    try:
        allk = [l_["key"] for l_ in _orig_lessons(MID)]
        b0 = PK.bulk_build(hctx, MID, None, None, True); n0 = len(calls_l)
        b1 = PK.bulk_build(hctx, MID, [], None, True); n1 = len(calls_l) - n0
        b2 = PK.bulk_build(hctx, MID, [A7], "xapi", False)
        ok([r_["no"] for r_ in b0["results"]] == allk and [r_["no"] for r_ in b1["results"]] == allk and [r_["no"] for r_ in b2["results"]] == [A7] and b2["results"][0]["ok"],
           f"bulk_build: topics None va [] — barcha {len(allk)} dars (orqaga moslik); [A7] — faqat A7")
        ok(n0 == 1 and n1 == 1, f"bulk_build: lessons() bir marta ({n0}, {n1})")
        calls_l.clear()
        PK.gather(MID, A7); PK.build_topic(hctx, MID, A7, "scorm12"); PK.lesson_info(mikro, A7)
        ok(not calls_l, f"gather / build_topic / lesson_info — lessons() ni qayta qurmaydi ({len(calls_l)})")
    finally:
        PK.lessons = _orig_lessons
    try: PK.lesson_info(mikro, 1099); ok(False, "yo'q dars topildi")
    except PK.HTTPException as e: ok(e.status_code == 400, "lesson_info: yo'q dars (A99) — 400")
    ok(PK.lesson_info(mikro, 1) == next(l_ for l_ in PK.lessons(MID) if l_["key"] == 1) and PK.lesson_info(mikro, A7) == next(l_ for l_ in PK.lessons(MID) if l_["key"] == A7),
       "lesson_info (to'g'ridan-to'g'ri so'rov) == lessons() dagi yozuv")
    # pending
    pend = PK.pending(hctx)
    ok(any(x["id"] == "approve" and x["view"] == "paket" for x in pend) or not dst.execute("SELECT 1 FROM pk_packages WHERE status='tayyor'").fetchone(), "«Mening vazifalarim»: tasdiq kutayotgan paketlar (bo'lim)")
finally:
    PK.PLAYER_DIR, PK.STORE = saved[0], saved[1]
    PK.bind(saved[2], saved[3]); dst.close()

# =============================================================================================
print("== 8. Yig'ish (HTTP, server pleyeri bilan)")
if not SERVER_PLAYER:
    print("  · app/paket_player/index.html hali yo'q — server orqali yig'ish o'tkazib yuborildi (jarayon ichida tekshirildi)")
    r = teach.post(f"{P}/courses/{C1}/topics/{T}/build", json={})
    ok(r.status_code == 503 and "pleyer" in r.json()["detail"].lower(), "Pleyersiz yig'ish — 503 va aniq xabar")
else:
    r = teach.post(f"{P}/courses/{C1}/topics/{T}/build", json={"mode": "scorm12"})
    ok(r.status_code == 200, f"O'qituvchi o'z mavzusini yig'di ({r.status_code} {r.text[:200]})")
    if r.status_code == 200:
        pk_ = r.json()["package"]
        d = teach.get(f"{P}/packages/{pk_['id']}/download")
        ok(d.status_code == 200 and PK.validate_zip(d.content)["ok"] and f'filename="ISFT_{PK._ascii(own["subject"], 50)}_L{T:02d}_scorm12.zip"' in d.headers.get("content-disposition", ""),
           "Yuklab olish: zip tekshiruvdan o'tadi, fayl nomi to'g'ri")
        pv0 = teach.get(f"{P}/packages/{pk_['id']}/preview/index.html")
        loc = pv0.headers.get("location", "")
        ok(pv0.status_code == 302 and re.fullmatch(rf"{P}/pv/{pk_['id']}\.{teach_uid}\.\d+\.[0-9a-f]{{40}}/index\.html", loc) is not None,
           f"Preview: cookie bilan ochiladi → imzolangan yo'lga 302 ({loc[:60]}…)")
        pvq = teach.get(f"{P}/packages/{pk_['id']}/preview/index.html?preview=1&x=<s>")
        ok(pvq.status_code == 302 and pvq.headers.get("location", "").endswith("/index.html?preview=1"), "Preview: «?preview=1» imzolangan yo'lga o'tkaziladi (xavfli parametrlar tashlanadi)")
        anon = httpx.Client(base_url=B, timeout=60)   # sandbox (opaque origin) ichki so'rovlari cookie yubormaydi
        pv = anon.get(loc)
        ok(pv.status_code == 200 and "default-src 'none'" in pv.headers.get("content-security-policy", "") and "sandbox allow-scripts" in pv.headers.get("content-security-policy", ""),
           "Preview: imzolangan yo'l cookie'siz ishlaydi, index.html CSP sandbox bilan")
        pj = anon.get(loc.rsplit("/", 1)[0] + "/content.js")
        ok(pj.status_code == 200 and pj.text.startswith("window.PAKET = "), "Preview: content.js (nisbiy yo'l imzolangan prefiks ostida)")
        tok = loc.split("/")[-2]; pid_, uid_, exp_, sig_ = tok.split(".")
        forged = [f"{pid_}.{uid_}.{int(exp_) + 999}.{sig_}", f"{pid_}.{uid('masofaviy')}.{exp_}.{sig_}", f"{int(pid_) + 1}.{uid_}.{exp_}.{sig_}",
                  f"{pid_}.{uid_}.{exp_}.{'0' * 40}", "abc", f"{pid_}.{uid_}.1.{sig_}"]
        ok(all(anon.get(f"{P}/pv/{t_}/index.html").status_code == 403 for t_ in forged), "Preview: soxta/o'zgartirilgan/muddati o'tgan token — 403")
        ok(anon.get(f"{P}/packages/{pk_['id']}/preview/index.html").status_code == 401, "Preview: cookie'siz asosiy yo'l — 401")
        ok(anon.get(loc.rsplit("/", 1)[0] + "/../../../etc/passwd").status_code in (400, 404) and anon.get(loc.rsplit("/", 1)[0] + "/..%2F..%2Fx").status_code in (400, 404),
           "Preview (imzolangan): «..» — rad etildi")
        anon.close()
        ok(teach.get(f"{P}/packages/{pk_['id']}/preview/..%2F..%2Fcopy.db").status_code in (400, 404) and
           teach.get(f"{P}/packages/{pk_['id']}/preview/%2E%2E/%2E%2E/etc/passwd").status_code in (400, 404), "Preview: kodlangan «..» — rad etildi")
        ok(teach.post(f"{P}/packages/{pk_['id']}/action", json={"action": "approve"}).status_code == 403, "O'qituvchi tasdiqlay olmaydi (403)")
        ok(rek.get(f"{P}/packages/{pk_['id']}/download").status_code == 403, "Rektor paketni yuklab ololmaydi (403)")
        ok(kaf.get(f"{P}/packages/{pk_['id']}/download").status_code == (200 if own["department_id"] == kaf_dept else 403), "Kafedra — faqat o'z kafedrasi paketi")
        r2 = teach.post(f"{P}/courses/{C1}/topics/{T}/build", json={"mode": "scorm12"}).json()
        ok(r2["unchanged"] and r2["package"]["id"] == pk_["id"], "HTTP: o'zgarishsiz qayta yig'ish — o'sha versiya")
        if pk_["status"] == "tayyor":
            a = staff.post(f"{P}/packages/{pk_['id']}/action", json={"action": "approve"})
            ok(a.status_code == 200 and a.json()["package"]["status"] == "tasdiqlandi", "Bo'lim xodimi tasdiqladi")
        rj = head.post(f"{P}/packages/{pk_['id']}/action", json={"action": "reject", "note": ""})
        ok(rj.status_code == 400, "Qaytarish sababsiz — 400")
        rj = head.post(f"{P}/packages/{pk_['id']}/action", json={"action": "reject", "note": "Video boshqa mavzuga tegishli"})
        ok(rj.status_code == 200 and rj.json()["package"]["status"] == "qoralama", "Bo'lim qaytardi (qoralama, izoh bilan)")
        mw = teach.get("/api/mywork").json()
        ok(any(it["source"] == "paket" for it in mw["items"]), "O'qituvchining «Mening vazifalarim» ida qaytarilgan paket")
    bb = teach.post(f"{P}/courses/{C1}/bulk/build", json={"only_complete": False}).json()
    ok(bb["ok"] and bb["built"] + bb["unchanged"] >= 1 and bb["failed"] == 0, f"Ommaviy yig'ish: {bb['built']} yig'ildi, {bb['unchanged']} o'zgarmagan, {bb['skipped']} o'tkazildi")

# =============================================================================================
print("== 9. Qamrov (SQL bilan solishtirish)")
cv = head.get(P + "/coverage").json()
t = cv["total"]
pairs = lambda sql: {(r["course_id"], r["topic_no"]) for r in q(sql)}
LES = {(c_["id"], k_) for c_ in q("SELECT id, COALESCE(topics,15) n FROM dl_courses") for k_ in range(1, c_["n"] + 1)} | \
      {(r["course_id"], r["lkey"]) for r in q("SELECT course_id, lkey FROM pk_lessons WHERE deleted=0")}
valid = pairs("SELECT course_id, topic_no FROM pk_packages WHERE topic_no>0") & LES
appr = pairs("SELECT course_id, topic_no FROM pk_packages WHERE status='tasdiqlandi' AND topic_no>0") & LES
# zaxira manbalar mavzu bo'yicha: dars → bog'langan mavzu (topic_ref), L — o'zi, bog'lanmagan A/S/… — yo'q
LINK = {(r["course_id"], r["lkey"]): ((r["course_id"], r["topic_ref"]) if r["topic_ref"] else None) for r in q("SELECT course_id, lkey, topic_ref FROM pk_lessons WHERE deleted=0")
        if r["topic_ref"] or r["lkey"] >= 1000}
srcof = lambda k: LINK[k] if k in LINK else (k if k[1] < 1000 else None)
qz = pairs("SELECT DISTINCT course_id, topic_no FROM tb_questions WHERE status='tasdiqlandi' AND deleted=0")
tbs = pairs("SELECT course_id, topic_no FROM tb_sources")
quiz = {k for k in LES if srcof(k) in qz}
text = {k for k in LES if srcof(k) in tbs} | (pairs("SELECT course_id, topic_no FROM pk_assets WHERE purpose='matn' AND deleted=0") & LES)
ok(t["topics"] == len(LES) and t["courses"] == q("SELECT COUNT(*) n FROM dl_courses")[0]["n"] and t["by_kind"].get("amaliy", 0) >= 2,
   f"Jami darslar: {t['topics']} (L + qo'shilgan A/S/…: {t['by_kind']})")
ok(t["built"] == len(valid) and t["approved"] == len(appr), f"Yig'ilgan {t['built']} / tasdiqlangan {t['approved']} — SQL bilan bir xil")
ok(t["quiz"] == len(quiz) and t["text"] == len(text), f"Test {t['quiz']} / matn {t['text']} — SQL bilan bir xil")
ok(sum(d["topics"] for d in cv["departments"]) == t["topics"] and sum(d["built"] for d in cv["departments"]) == t["built"], "Kafedralar yig'indisi = jami")
ok(cv["teachers"] and sum(x["topics"] for x in cv["teachers"]) == t["topics"], "O'qituvchilar yig'indisi = jami")
ct = teach.get(P + "/coverage").json()
ok(ct["total"]["courses"] == q("SELECT COUNT(*) n FROM dl_courses WHERE teacher_id=?", (teach_tid,))[0]["n"] and ct["teachers"] == [], "O'qituvchi qamrovi — faqat o'z kurslari")
ck = kaf.get(P + "/coverage").json()
ok(ck["total"]["courses"] == q("SELECT COUNT(*) n FROM dl_courses WHERE department_id=?", (kaf_dept,))[0]["n"], "Kafedra qamrovi — faqat o'z kafedrasi")
cvv = teach.get(f"{P}/courses/{C1}").json()
t4 = next(x for x in cvv["topics"] if x["no"] == T)
ok(t4["text"] and t4["slides"] and t4["video"], "Kurs ko'rinishida mavzu tayyorgarligi (M/T/V)")

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi:"); [print("  -", f) for f in fails]; sys.exit(1)
print("Hammasi o'tdi ✓")
