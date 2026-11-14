"""Kontent paketlari moduli (app/paket.py) — ruxsatlar, YouTube havolalari, HTML tozalash, ma'ruza matni → reja va HTML, PPTX tahlili,
manbalar (HTTP), yig'ish (har bir tur: SCORM 1.2 / SCORM 2004 / xAPI / oddiy) + validate_zip + manifestlar (ElementTree), deterministik zip,
versiyalar, kurs paketi, ko'rish (preview) yo'li, yuklab olish nomi, avtomatik joylash, qamrov (SQL bilan), «Mening vazifalarim».
NEXTID (kontrakt v2): darslar ro'yxati (L/A/S/Lab/MT) tahlili, migratsiya idempotentligi, Word rasmlari (izoh bilan) / jadvallar / adabiyotlar,
figure/img tozalash, PDF → slayd rasmlari (pypdfium2), shablon bloklari tartibi va bo'lim sarlavhalari, reflect / keypoints, AI xulosalar
(claude_client.call_json jarayon ichida almashtiriladi — serverda AI chaqirilmaydi), har tur uchun validate_zip, dars bo'yicha fayl nomlari.
Rise 360 (kontrakt v3): video fayl (oqim bilan yuklash, 413, noto'g'ri tur), SRT → WebVTT jadvali (BOM, UTF-16, cp1251, xato yozuvlar), ko'rishda
HTTP Range (206 / Content-Range / oxirgi n bayt / 416), muqova, mashqlar (CRUD, tekshiruv, ruxsatlar), «MASHQ VA TOPSHIRIQLAR» bo'limi tartibi,
Word'dagi «Savollar» → topshiriq, slayd izohi/audiosi, AI mashqlar (soxta Claude, iqtibos filtri), validate_zip salbiy holatlari, deterministiklik.

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_paket.py
   (yoki hammasi toza muhitda: python tests/run_all.py --only paket)
DIQQAT: lokal bazani o'zgartiradi (manbalar, video havolalar, paketlar) — PRODUCTION'da ishlatilmaydi.
Yig'ish jarayon ichida (bazaning vaqtinchalik nusxasida) soxta pleyer bilan ham tekshiriladi (paket.PLAYER_DIR / STORE almashtiriladi);
server orqali yig'ish — app/paket_player/index.html mavjud bo'lsa.
"""
import asyncio, io, json, os, re, sqlite3, sys, tempfile, zipfile, xml.etree.ElementTree as ET
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
mikro_teacher = (q("SELECT full_name FROM teachers WHERE id=?", (mikro["teacher_id"],)) or [{"full_name": ""}])[0]["full_name"] or ""
kaf8 = S(uid("kafedra", "AND department_id=?", (mikro["department_id"],)))
own = q("SELECT * FROM dl_courses WHERE teacher_id=? ORDER BY subject='Innovatsion iqtisodiyot' DESC, id LIMIT 1", (teach_tid,))[0]
other_dept = q("SELECT * FROM dl_courses WHERE department_id!=? ORDER BY id LIMIT 1", (kaf_dept,))[0]

# =============================================================================================
print("== 1. Ruxsatlar va ko'lam")
m = head.get(P + "/meta").json()
ok(m["tabs"] == ["fanlar", "qamrov", "mavzular", "joylash", "sozlama"] and m["caps"]["approve"] and m["caps"]["settings"], "Bo'lim boshlig'i: 4 bo'lim, tasdiqlash va sozlamalar")
ms = staff.get(P + "/meta").json()
ok(ms["caps"]["approve"] and ms["caps"]["settings"] and ms["caps"]["build"], "Bo'lim xodimi: yig'ish, tasdiqlash, sozlamalar")
mt = teach.get(P + "/meta").json()
ok(mt["caps"]["build"] and not mt["caps"]["approve"] and not mt["caps"]["settings"] and mt["tabs"] == ["fanlar", "mavzular"] and mt["tab_labels"]["mavzular"] == "Darslarim",
   "O'qituvchi: tayyorlaydi, tasdiqlamaydi; yorliqlar — «Fanlar» va «Darslarim» (Holat / Ommaviy / Sozlamalar yo'q)")
ok(m["tab_labels"] == {"fanlar": "Fanlar", "qamrov": "Holat", "mavzular": "Darslar", "joylash": "Ommaviy", "sozlama": "Sozlamalar"} and m["title"] == "Dars tayyorlash", "Bo'lim yorliqlari: Holat, Darslar, Ommaviy, Sozlamalar")
mk = kaf.get(P + "/meta").json()
ok(not mk["caps"]["write"] and mk["caps"]["download"] and mk["tabs"] == ["fanlar", "qamrov", "mavzular"], "Kafedra mudiri: ko'rish va yuklab olish")
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
print("== 5b. Rise 360: media turi, SRT → WebVTT, HTTP Range, mashq tekshiruvi, «Savollar» bo'limi")
MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + bytes(range(256)) * 600          # video emas — faqat sarlavhasi to'g'ri (mavjudlik / bayt tekshiruvi uchun)
WEBM = b"\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f\x42\x86\x81\x01\x42\xf7\x81\x01\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x84webm" + b"\0" * 4000
MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"\xff\xfb\x90\x00" * 800
WAV = b"RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x08\x00\x00" + b"\0" * 2048
SNIFF = [(MP4, "mp4"), (WEBM, "webm"), (MP3, "mp3"), (b"\xff\xfb\x90\x00" * 20, "mp3"), (WAV, "wav"), (b"OggS\x00\x02" + b"\0" * 60, "ogg"), (b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00", "m4a"),
         (b"\x1a\x45\xdf\xa3" + b"\x00" * 20 + b"matroska" + b"\0" * 40, None), (b"\xff\xfe" + "salom".encode("utf-16-le"), None), (b"\xff\xd8\xff\xe0JFIF", None),
         (b"MZ\x90\x00", None), (b"%PDF-1.4", None), (b"<html>", None), (b"", None)]
for head_, want in SNIFF:
    ok(PK.sniff_media(head_[:64]) == want, f"sniff_media: {head_[:12]!r} → {want}")
SRT = "1\n00:00:01,000 --> 00:00:04,500\nSalom, <font color=\"red\">hurmatli</font> talabalar!\n\n2\n00:00:05,000 --> 00:00:09,250\n<i>Bugungi mavzu</i> —\nyozuv tarixi {\\an8}\n\n3\n00:01:02,5 --> 01:00:03,000\nXayr\n"
VTT_OUT = ("WEBVTT\n\n00:00:01.000 --> 00:00:04.500\nSalom, hurmatli talabalar!\n\n00:00:05.000 --> 00:00:09.250\n<i>Bugungi mavzu</i> —\nyozuv tarixi\n\n"
           "00:01:02.500 --> 01:00:03.000\nXayr\n")
RU = "1\n00:00:01,000 --> 00:00:02,000\nПривет, студенты!\n"
VTT_CASES = [
    ("SRT (UTF-8)", SRT.encode("utf-8"), VTT_OUT, 3, "srt"),
    ("SRT (UTF-8 BOM, CRLF)", b"\xef\xbb\xbf" + SRT.replace("\n", "\r\n").encode("utf-8"), VTT_OUT, 3, "srt"),
    ("SRT (UTF-16 LE BOM)", SRT.encode("utf-16"), VTT_OUT, 3, "srt"),
    ("SRT (UTF-16 BE BOM)", b"\xfe\xff" + SRT.encode("utf-16-be"), VTT_OUT, 3, "srt"),
    ("SRT (cp1251, kirill)", RU.encode("cp1251"), "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nПривет, студенты!\n", 1, "srt"),
    ("SRT (UTF-8, kirill)", RU.encode("utf-8"), "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nПривет, студенты!\n", 1, "srt"),
    ("SRT: raqamsiz, tartibsiz yozuvlar — vaqt bo'yicha tartiblanadi", b"00:00:05,000 --> 00:00:06,000\nIkkinchi\n\n00:00:01,000 --> 00:00:02,000\nBirinchi\n",
     "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nBirinchi\n\n00:00:05.000 --> 00:00:06.000\nIkkinchi\n", 2, "srt"),
    ("VTT: sarlavha, NOTE, STYLE, identifikator, sozlamalar, soatsiz vaqt", "WEBVTT - Dars\nKind: captions\n\nNOTE bu izoh\nikki qator\n\nSTYLE\n::cue { color: red }\n\nkirish\n00:01.000 --> 00:02.500 align:start position:10%\n<v Ali>O'zbekcha</v> <b>matn</b>\n\n00:00:03.000 --> 00:00:04.000\n\n".encode(),
     "WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nO'zbekcha <b>matn</b>\n", 1, "vtt"),
]
for name_, raw_, want, n_, src_ in VTT_CASES:
    r = PK.to_vtt(raw_)
    ok(r["vtt"] == want and r["cues"] == n_ and r["src"] == src_, f"to_vtt: {name_} → {n_} yozuv ({r['vtt'][:40]!r}…)" if r["vtt"] == want else f"to_vtt: {name_}: {r['vtt']!r}")
ok(PK.to_vtt(SRT.encode())["end"] == 3603000 and PK.to_vtt(PK.to_vtt(SRT.encode())["vtt"].encode())["vtt"] == VTT_OUT, "to_vtt: natija — yaroqli WebVTT (qayta o'qilganda o'zgarmaydi), oxirgi vaqt ms")
BAD_SUBS = [("tugash ≤ boshlanish", b"1\n00:00:05,000 --> 00:00:04,000\nx\n", "2-qator"), ("tugash = boshlanish", b"00:00:05,000 --> 00:00:05,000\nx\n", "1-qator"),
            ("vaqt formati («->»)", b"1\n00:00:05,000 -> 00:00:06,000\nx\n", "1-qator"), ("millisekundsiz", b"1\n00:00:05 --> 00:00:06\nx\n", "2-qator"),
            ("daqiqa 61", b"1\n00:61:00,000 --> 00:62:00,000\nx\n", "2-qator"), ("ikkinchi yozuv buzilgan (qator raqami)", b"1\n00:00:01,000 --> 00:00:02,000\na\n\n2\nbuzilgan vaqt\nb\n", "5-qator"),
            ("yozuvsiz matn", b"salom dunyo\n", "1-qator"), ("bo'sh fayl", b"", "topilmadi"), ("faqat sarlavha", b"WEBVTT\n\n", "topilmadi"),
            ("ikkilik fayl", b"\x00\x01\x02\x03PK\x03\x04", ""), ("yozuvlar juda ko'p", ("00:00:01,000 --> 00:00:02,000\nx\n\n" * (PK.MAX_CUES + 1)).encode(), "ko'p")]
for name_, raw_, frag in BAD_SUBS:
    try: PK.to_vtt(raw_); ok(False, f"to_vtt: {name_} — o'tib ketdi")
    except PK.HTTPException as e: ok(e.status_code == 400 and frag in e.detail, f"to_vtt: {name_} — 400 ({e.detail[:60]})")
RANGES = [("bytes=0-99", (0, 99)), ("bytes=0-", (0, 999)), ("bytes=500-", (500, 999)), ("bytes=-100", (900, 999)), ("bytes=-5000", (0, 999)), ("bytes=990-5000", (990, 999)),
          (" bytes = 10 - 20 ", (10, 20)), ("bytes=999-999", (999, 999)), ("bytes=1000-", None), ("bytes=5-2", None), ("bytes=-0", None), ("bytes=-", None), ("bytes=abc", None),
          ("items=0-5", None), ("bytes=0-1,5-9", None), ("", None), ("bytes=1-2-3", None)]
for h_, want in RANGES:
    ok(PK.parse_range(h_, 1000) == want, f"parse_range({h_!r}, 1000) → {want}")
ok(PK.parse_range("bytes=0-", 0) is None, "parse_range: bo'sh fayl — qondirib bo'lmaydi")
P2 = [{"left": "Bayt", "right": "8 bit"}, {"left": "Kilobayt", "right": "1024 bayt"}]
C2 = [{"title": "Kiritish", "items": ["Klaviatura", "Sichqoncha"]}, {"title": "Chiqarish", "items": ["Monitor"]}]
x = PK.clean_exercise("match", {"stem": "  Mos   juftni toping ", "pairs": P2 + [{"left": "", "right": " "}], "explanation": "Izoh"})
ok(x == {"title": "Mos juftni toping", "data": {"pairs": P2}, "explanation": "Izoh"}, "clean_exercise: match — bo'sh juft tashlanadi, bo'shliqlar me'yorlanadi")
ok(PK.clean_exercise("sort", {"categories": C2 + [{"title": "", "items": []}]}) == {"title": "Elementlarni toifalarga ajrating", "data": {"categories": C2}, "explanation": ""}
   and PK.clean_exercise("flashcards", {"cards": [{"front": "CPU", "back": "Protsessor"}]}) == {"title": "Kartochkalar", "data": {"cards": [{"front": "CPU", "back": "Protsessor"}]}, "explanation": ""},
   "clean_exercise: sort va flashcards — standart sarlavha, bo'sh toifa tashlanadi")
ok(len(PK.clean_exercise("match", {"pairs": [{"left": "a" * 500, "right": "1"}, {"left": "b", "right": "2" * 500}]})["data"]["pairs"][0]["left"]) == 200
   and len(PK.clean_exercise("flashcards", {"title": "t" * 200, "cards": [{"front": "f" * 999, "back": "b" * 999}]})["data"]["cards"][0]["back"]) == 500, "clean_exercise: uzunlik chegaralari (kesiladi)")
pr = lambda n: [{"left": f"L{i}", "right": f"R{i}"} for i in range(n)]
BAD_EX = [("match", {"pairs": pr(1)}, "2 tadan 8"), ("match", {"pairs": pr(9)}, "2 tadan 8"), ("match", {"pairs": []}, "2 tadan 8"),
          ("match", {"pairs": pr(2) + [{"left": "l0", "right": "x"}]}, "chap"), ("match", {"pairs": pr(2) + [{"left": "x", "right": "R1"}]}, "o'ng"),
          ("match", {"pairs": pr(2) + [{"left": "yarim", "right": ""}]}, "ikkala"), ("match", {"pairs": "abc"}, "2 tadan 8"),
          ("sort", {"categories": C2[:1]}, "2 tadan 4"), ("sort", {"categories": [{"title": f"T{i}", "items": [f"e{i}"]} for i in range(5)]}, "2 tadan 4"),
          ("sort", {"categories": C2[:1] + [{"title": "Bo'sh", "items": []}]}, "1 tadan 8"), ("sort", {"categories": C2[:1] + [{"title": "Ko'p", "items": [f"e{i}" for i in range(9)]}]}, "1 tadan 8"),
          ("sort", {"categories": C2[:1] + [{"title": "B", "items": ["klaviatura"]}]}, "takrorlanmasin"), ("sort", {"categories": C2[:1] + [{"title": "kiritish", "items": ["x"]}]}, "toifa nomlari"),
          ("sort", {"categories": C2[:1] + [{"title": "", "items": ["x"]}]}, "nomi bo'sh"),
          ("flashcards", {"cards": []}, "1 tadan 40"), ("flashcards", {"cards": [{"front": f"f{i}", "back": "b"} for i in range(41)]}, "1 tadan 40"),
          ("flashcards", {"cards": [{"front": "f", "back": ""}]}, "old va orqa"), ("hotspot", {}, "noma'lum"), ("", {}, "noma'lum")]
for kind_, d_, frag in BAD_EX:
    try: PK.clean_exercise(kind_, d_); ok(False, f"clean_exercise: {kind_} {frag} — o'tib ketdi")
    except PK.HTTPException as e: ok(e.status_code == 400 and frag in e.detail, f"clean_exercise: {kind_ or '—'} — 400 ({e.detail[:70]})")
ok(PK.clean_exercise("match", {"pairs": pr(8)})["data"]["pairs"] == pr(8) and len(PK.clean_exercise("flashcards", {"cards": [{"front": f"f{i}", "back": "b"} for i in range(40)]})["data"]["cards"]) == 40
   and len(PK.clean_exercise("sort", {"categories": [{"title": f"T{i}", "items": [f"e{i}{j}" for j in range(8)]} for i in range(4)]})["data"]["categories"]) == 4, "clean_exercise: chegaradagi qiymatlar (8 juft, 40 kartochka, 4×8) qabul qilinadi")
QTXT = ("Reja:\n1. Yozuv tarixi\n2. Savollar\n3. Xulosa\n\n1. Yozuv tarixi\nYozuv insoniyatning eng muhim kashfiyotlaridan biridir. U axborotni saqlash imkonini berdi.\n\n"
        "Savollar\n1. Yozuv nima?\n2. Alifbo qachon paydo bo'lgan\nva uni kim yaratgan?\n3. Mixxat qayerda qo'llangan?\n\nFoydalanilgan adabiyotlar\n1. Karimov A. Yozuv tarixi. T., 2020.\n\n"
        "Mustaqil ish topshiriqlari: 1) Esse yozing. 2) Jadval tuzing.\n")
sa = PK.structure_text(QTXT, "", None, assign=True); s0 = PK.structure_text(QTXT)
ok(sa["questions"] == ["Yozuv nima?", "Alifbo qachon paydo bo'lgan va uni kim yaratgan?", "Mixxat qayerda qo'llangan?", "Esse yozing.", "Jadval tuzing."]
   and "Yozuv nima?" not in sa["html"] and "Savollar" not in sa["html"] and "Esse" not in sa["html"] and sa["refs"] == ["Karimov A. Yozuv tarixi. T., 2020."] and sa["plan"] == ["Yozuv tarixi", "Savollar", "Xulosa"],
   f"«Savollar» va «Mustaqil ish topshiriqlari» ro'yxati matndan olinadi (uzilgan qator — bandning davomi); reja bandi «2. Savollar» va adabiyotlar joyida ({sa['questions']})")
ok(s0["questions"] == [] and "Yozuv nima?" in s0["html"] and s0["refs"] == sa["refs"] and s0["plan"] == sa["plan"], "assign=False (standart) — savollar matnda qoladi (eski xatti-harakat)")
HEADS = ["Savollar", "SAVOLLAR:", "Nazorat savollari", "Nazorat uchun savollar:", "# Nazorat savollari", "5. Nazorat savollari", "Topshiriqlar", "Mustaqil ish topshiriqlari", "Mustaqil ish uchun topshiriqlar:",
         "Savol va topshiriqlar", "Takrorlash uchun savollar", "Nazorat savollari va topshiriqlar", "Контрольные вопросы", "Назорат саволлари"]
for h_ in HEADS:
    r = PK.structure_text(f"Kirish matni. Bu yerda oddiy gap bor.\n\n{h_}\n1. Birinchi savol?\n2. Ikkinchi savol?\n\nXotima matni shu yerda davom etadi.", "", None, assign=True)
    ok(r["questions"] == ["Birinchi savol?", "Ikkinchi savol?"] and "savol?" not in r["html"] and "Xotima matni" in r["html"] and "Kirish matni" in r["html"], f"Savollar sarlavhasi: {h_!r}")
r = PK.structure_text("Kirish matni bu yerda.\n\nNazorat savollari\nYozuv nima?\nAlifbo nima?\nBu esa oddiy gap.\n\nSavollar\n\nDavomi bor.\n\nTopshiriqlar: bugun yo'q.", "", None, assign=True)
ok(r["questions"] == ["Yozuv nima?", "Alifbo nima?"] and "Bu esa oddiy gap." in r["html"] and "<p>Savollar</p>" in r["html"] and "Topshiriqlar: bugun yo'q." in r["html"],
   "Raqamsiz ro'yxat — faqat «?» bilan tugaydigan qatorlar; ro'yxatsiz «Savollar» sarlavhasi va oddiy «Topshiriqlar: …» gapi matnda qoladi")
# ro'yxat chegarasi: faqat ketma-ket bandlar; bo'sh qatordan keyin — faqat raqamlash davom etsa (ko'rib chiqish topilmalari)
r = PK.structure_text("Kirish matni bu yerda.\n\nNazorat savollari\n1. Yozuv nima?\n2. Alifbo nima?\n\n1.2. Yozuvning rivojlanishi\nYozuv asta-sekin rivojlangan. Bu bo'lim ma'ruzaning davomi.\n\n"
                      "3. Xulosa\nYozuv — sivilizatsiya asosi.", "", None, assign=True)
ok(r["questions"] == ["Yozuv nima?", "Alifbo nima?"] and "Yozuvning rivojlanishi" in r["html"] and "Yozuv asta-sekin rivojlangan." in r["html"] and "Xulosa" in r["html"] and "sivilizatsiya asosi" in r["html"]
   and not r["q_warn"], f"Savollar ro'yxati bo'sh qator + «1.2. …» bo'lim sarlavhasida tugaydi — keyingi bo'limlar matnda qoladi ({r['questions']})")
r = PK.structure_text("Matn boshi shu yerda.\n\nSavollar\n1. Birinchi savol?\n2. Ikkinchi savol?\n\nKeyingi mavzuda biz alifbolarni ko'rib chiqamiz\nva ularning turlarini o'rganamiz.\n\n"
                      "- Lotin alifbosi\n- Kirill alifbosi\n\n1. Yangi ro'yxat boshi\n2. Yangi ro'yxat davomi", "", None, assign=True)
ok(r["questions"] == ["Birinchi savol?", "Ikkinchi savol?"] and "Keyingi mavzuda biz alifbolarni" in r["html"] and "<li>Lotin alifbosi</li>" in r["html"] and "Yangi ro'yxat boshi" in r["html"],
   "Bo'sh qatordan keyingi oddiy paragraf, belgili ro'yxat va «1.» dan qayta boshlangan ro'yxat — savol emas (matnda qoladi)")
r = PK.structure_text("Matn.\n\nSavollar\n\n1. Bir?\n\n2. Ikki?\n\n3. Uch?\n\n\n4. Ikki bo'sh qatordan keyin — boshqa ro'yxat\n\nNazorat savollari\n\n5. Xulosa va tavsiyalar\nOddiy matn.", "", None, assign=True)
ok(r["questions"] == ["Bir?", "Ikki?", "Uch?"] and "Ikki bo'sh qatordan keyin" in r["html"] and "Nazorat savollari" in r["html"] and "Xulosa va tavsiyalar" in r["html"],
   "Bandlar orasida bitta bo'sh qator — raqamlash davom etsa ro'yxat davom etadi; ikki bo'sh qator yoki sarlavhadan keyin «5. …» — tugaydi")
# hech narsa jimgina tashlanmaydi: chegaradan (60) ortig'i va juda uzun band matnda qoladi + ogohlantirish
r = PK.structure_text("Matn.\n\nSavollar\n" + "\n".join(f"{i}. Savol {i}?" for i in range(1, 71)), "", None, assign=True)
ok(PK.ASSIGN_MAX == 60 and r["questions"] == [f"Savol {i}?" for i in range(1, 61)] and r["q_warn"] == {"over": 10} and all(f"<li>Savol {i}?</li>" in r["html"] for i in range(61, 71)) and "Savol 60?" not in r["html"],
   "Savollar — ko'pi bilan 60 ta; ortiqcha 10 tasi tashlanmaydi — matnda qoladi, ogohlantirish {'over': 10}")
r = PK.structure_text("Matn.\n\nSavollar\n1. Qisqa savol?\n2. " + "Uzun topshiriq matni " * 30 + "tugadi.\n3. Keyingi savol?", "", None, assign=True)
ok(r["questions"] == ["Qisqa savol?"] and r["q_warn"] == {"long": 1} and r["html"].count("Uzun topshiriq matni") == 30 and "tugadi." in r["html"] and "Keyingi savol?" in r["html"],
   "Juda uzun band (> 500 belgi) kesilmaydi: shu banddan boshlab ro'yxat matnda qoladi, ogohlantirish {'long': 1}")
r = PK.structure_text("Matn.\n\nTopshiriqlar: 1) " + "juda uzun topshiriq " * 30 + "2) Ikkinchi.", "", None, assign=True)
ok(r["questions"] == [] and r["q_warn"] == {"long": 1} and r["html"].count("juda uzun topshiriq") == 30 and "Topshiriqlar" in r["html"], "Sarlavha qatoridagi juda uzun band — bo'lim butunicha matnda qoladi (savollar yo'q, ogohlantirish)")
ok(PK.structure_text(QTXT, "", None, assign=True)["q_warn"] == {} and PK.structure_text(QTXT)["q_warn"] == {}, "Oddiy holatda ogohlantirish yo'q")
# to_vtt: sarlavha qat'iy o'qiladi (birinchi yozuv yo'qolmaydi), faqat haqiqiy teglar olinadi
VTT2 = [("VTT: sarlavhadan keyin bo'sh qatorsiz birinchi yozuv", "WEBVTT\n00:00:01.000 --> 00:00:02.000\nBirinchi\n\n00:00:03.000 --> 00:00:04.000\nIkkinchi\n",
         "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nBirinchi\n\n00:00:03.000 --> 00:00:04.000\nIkkinchi\n", 2),
        ("VTT: nomli sarlavha + sarlavha qatorlari, bo'sh qatorsiz", "WEBVTT - 3-dars subtitrlari\nKind: captions\nLanguage: uz\n00:01.000 --> 00:02.000\nBirinchi\n\n2\n00:03.000 --> 00:04.000\nIkkinchi\n",
         "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nBirinchi\n\n00:00:03.000 --> 00:00:04.000\nIkkinchi\n", 2),
        ("VTT: sarlavha + bo'sh qator + identifikatorli yozuv", "WEBVTT\n\nkirish\n00:00:01.000 --> 00:00:02.000\nBirinchi\n", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nBirinchi\n", 1),
        ("VTT: matndagi «<» va «>» saqlanadi, haqiqiy teglar olinadi", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nAgar a < b va c > d bo'lsa, <c.sariq>x</c> <v Ali Valiyev>y</v> <i>z</i> <00:00:01.500>w <font size=\"3\">q</font> 2 < 3\n",
         "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nAgar a &lt; b va c &gt; d bo'lsa, x y <i>z</i> w q 2 &lt; 3\n", 1)]
for name_, raw_, want, n_ in VTT2:
    r = PK.to_vtt(raw_.encode())
    ok(r["vtt"] == want and r["cues"] == n_ and r["src"] == "vtt" and PK.to_vtt(r["vtt"].encode())["vtt"] == want, f"to_vtt: {name_}" + ("" if r["vtt"] == want else f": {r['vtt']!r}"))
ok(PK.to_vtt("1\n00:00:01,000 --> 00:00:02,000\nx < y, <b>qalin</b>, <font color=red>rang</font>\n".encode())["vtt"] == "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nx &lt; y, <b>qalin</b>, rang\n",
   "to_vtt (SRT): «x < y» saqlanadi, <font> olinadi")
try: PK.to_vtt(b"WEBVTTX\n\n00:00:01.000 --> 00:00:02.000\nx\n"); ok(False, "«WEBVTTX» sarlavha deb qabul qilindi")
except PK.HTTPException as e: ok(e.status_code == 400 and "1-qator" in e.detail, "to_vtt: «WEBVTTX…» — WebVTT sarlavhasi emas (400, 1-qator)")
ok(PK.package_max(False) == 200 * 1024 * 1024 and PK.package_max(True) == 500 * 1024 * 1024 and PK.video_max() == 200 * 1024 * 1024, "Chegaralar: video 200 MB, paket 200 MB (video fayl bilan 500 MB)")
os.environ["ISFT_CORE_PK_PACKAGE_MB"], os.environ["ISFT_CORE_PK_VIDEO_MB"] = "700", "64"
ok(PK.package_max(True) == 700 * 1024 * 1024 and PK.package_max(False) == 200 * 1024 * 1024 and PK.video_max() == 64 * 1024 * 1024, "Chegaralar muhitdan: ISFT_CORE_PK_PACKAGE_MB, ISFT_CORE_PK_VIDEO_MB")
os.environ.pop("ISFT_CORE_PK_PACKAGE_MB"); os.environ.pop("ISFT_CORE_PK_VIDEO_MB")

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
ok("kurs_link" in tv and tv["kurs_link"] is None, "Dars muharrirga o'tkazilmagan — muharrir havolasi yo'q (kurs_link=None; «Muharrirda tahrirlash» — app/dars.py)")
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
def make_rich_docx(savollar=False) -> bytes:
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
    if savollar:      # bo'lim Word'dan ko'chiradigan «Savollar» ro'yxati — paketda «Topshiriq» blokiga o'tadi
        d.add_paragraph("Savollar")
        for x in ("Kompyuter nima?", "Bayt necha bitdan iborat?", "Axborot texnologiyalari qayerda qo'llaniladi?"): d.add_paragraph(x, style="List Number")
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
RICH, PDF3, TASKDOC = make_rich_docx(), make_pdf(3), make_rich_docx(savollar=True)
TASK_Q = ["Kompyuter nima?", "Bayt necha bitdan iborat?", "Axborot texnologiyalari qayerda qo'llaniladi?"]
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
    ok(r.status_code == 503 and "AI ulanmagan — administratorga murojaat qiling" in r.json()["detail"] and "ANTHROPIC" not in r.json()["detail"], "AI xulosalar: kalit yo'q — 503 (aniq xabar, texnik nomsiz)")
ok(kaf.post(f"{P}/courses/{C1}/topics/{A1}/keypoints/ai").status_code == 403 and kaf.post(f"{P}/courses/{C1}/topics/{A1}/keypoints", json={"items": ["x"], "approve": True}).status_code == 403,
   "AI / xulosalar: kafedra mudiri — 403")
r = teach.post(f"{P}/courses/{C1}/topics/{A1}/keypoints", json={"items": ["Kompyuterlar turlarga bo'linadi.", "Bayt — 8 bit."], "approve": True})
ok(r.status_code == 200 and r.json()["keypoints"]["approved"]["items"] == ["Kompyuterlar turlarga bo'linadi.", "Bayt — 8 bit."], "Xulosalar qo'lda yozildi va tasdiqlandi")
tv = teach.get(f"{P}/courses/{C1}/topics/{A1}").json()
ok([b_["type"] for b_ in tv["blocks"]] == ["section", "plan", "text", "keypoints", "refs", "section", "slides", "file", "reflect"],
   f"A1 bloklari shablon tartibida: {[b_['type'] for b_ in tv['blocks']]}")

# =============================================================================================
print("== 6c. Rise 360 (HTTP): video fayl, subtitr, muqova, mashqlar, topshiriq, slayd audiosi")
SRV_STORE = Path(os.environ.get("ISFT_CORE_DATA_DIR") or DBP.parent) / "paket"
R6 = 6
vb = f"{P}/courses/{C1}/topics/{R6}"
view6 = lambda: teach.get(vb).json()
den0 = q("SELECT COUNT(*) n FROM audit_log WHERE resource='paket' AND allowed=0")[0]["n"]
r = teach.post(vb + "/video/file", params={"name": "6-dars videosi.mp4"}, content=MP4)
ok(r.status_code == 200 and r.json()["kind"] == "mp4" and r.json()["size"] == len(MP4), f"Video fayl (.mp4) yuklandi ({r.status_code} {r.text[:100]})")
va = q("SELECT * FROM pk_assets WHERE id=?", (r.json()["id"],))[0]
ok(va["purpose"] == "video" and va["kind"] == "mp4" and va["sha256"] == PK._sha(MP4) and va["size"] == len(MP4) and (SRV_STORE / va["path"]).read_bytes() == MP4,
   "Video diskda: hajm va sha256 (oqim bilan hisoblangan) asl fayl bilan bir xil")
r = teach.post(vb + "/video/file", params={"name": "yangi.webm"}, content=(x for x in [WEBM[:10], WEBM[10:50], WEBM[50:]]))
ok(r.status_code == 200 and r.json()["kind"] == "webm" and q("SELECT deleted FROM pk_assets WHERE id=?", (va["id"],))[0]["deleted"] == 2 and not (SRV_STORE / va["path"]).exists(),
   "Chunked (Content-Length'siz) .webm — tur bo'laklar chegarasidan qat'i nazar aniqlanadi; eski video «almashtirildi» va diskdan o'chirildi")
for nm_, body_, why in (("virus.mp4", b"MZ\x90\x00" + b"\0" * 500, "exe (.mp4 nomi bilan)"), ("kino.mkv", b"\x1a\x45\xdf\xa3" + b"\0" * 20 + b"matroska" + b"\0" * 300, "Matroska (.mkv)"),
                         ("hujjat.mp4", b"%PDF-1.4\n" + b"x" * 300, "PDF"), ("audio.mp4", b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00" + b"\0" * 300, "M4A audio"), ("qisqa.mp4", b"\x00\x00", "2 bayt")):
    ok(teach.post(vb + "/video/file", params={"name": nm_}, content=body_).status_code == 415, f"Video emas — 415: {why}")
ok(teach.post(vb + "/video/file", params={"name": "bosh.mp4"}, content=b"").status_code == 400, "Bo'sh video — 400")
ok(teach.post(f"{P}/courses/{mikro['id']}/topics/3/video/file", params={"name": "x.mp4"}, content=MP4).status_code == 403 and kaf.post(vb + "/video/file", params={"name": "x.mp4"}, content=MP4).status_code == 403
   and rek.post(vb + "/video/file", params={"name": "x.mp4"}, content=MP4).status_code == 403 and teach.post(f"{P}/courses/{C1}/topics/999/video/file", params={"name": "x.mp4"}, content=MP4).status_code == 400,
   "Video fayl: begona kurs / kafedra / rektor — 403 (tana o'qilmasdan), yo'q dars — 400")
def vchunks(total, size=1024 * 1024):
    yield MP4[:64] + b"\0" * (size - 64); sent = size
    while sent < total:
        n = min(size, total - sent); sent += n; yield b"\0" * n
try: code = teach.post(vb + "/video/file", params={"name": "katta.mp4"}, content=vchunks(PK.video_max() + 2 * 1024 * 1024)).status_code
except httpx.HTTPError as e: code = f"uzildi ({type(e).__name__})"
ok(code == 413 or str(code).startswith("uzildi"), f"Video {PK.video_max() // 1048576 + 2} MB (chunked) — chegarada 413 ({code})")
import time as _time
_time.sleep(0.3)
ok(not list((SRV_STORE / "tmp").glob("*")) and len(q("SELECT id FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='video' AND deleted=0", (C1, R6))) == 1
   and not q("SELECT id FROM pk_assets WHERE course_id=? AND name IN ('virus.mp4','kino.mkv','hujjat.mp4','audio.mp4','katta.mp4','bosh.mp4','qisqa.mp4')", (C1,)),
   "Rad etilgan / chegaradan oshgan videolar saqlanmadi, vaqtinchalik fayllar o'chirildi")
teach.post(vb + "/video/file", params={"name": "6-dars videosi.mp4"}, content=MP4)
tv = view6()
ok(tv["ready"]["video"]["ok"] and tv["ready"]["video"]["provider"] == "file" and tv["ready"]["video"]["src"] == "fayl" and tv["ready"]["video"]["file"]["kind"] == "mp4" and not tv["ready"]["video"]["both"],
   "Tayyorgarlik: video — yuklangan fayl")
teach.post(vb + "/video", json={"url": f"https://youtu.be/{ID}"})
tv = view6()
ok(tv["ready"]["video"]["both"] and tv["ready"]["video"]["provider"] == "file" and tv["settings"]["video_source"] == "file" and next(b_ for b_ in tv["blocks"] if b_["type"] == "video"),
   "Fayl va YouTube ikkalasi bor — standart: fayl")
teach.post(vb + "/settings", json={"video_source": "youtube"})
tv = view6()
ok(tv["ready"]["video"]["provider"] == "youtube" and tv["ready"]["video"]["video_id"] == ID and tv["override"] == {"video_source": "youtube"}, "Dars sozlamasi video_source=youtube — YouTube havola tanlanadi")
teach.post(vb + "/settings", json={"reset": True}); teach.post(vb + "/video", json={"url": ""})
# subtitrlar
r = teach.post(vb + "/video/captions", params={"name": "dars.srt", "lang": "uz"}, content=SRT.encode("utf-8"))
ok(r.status_code == 200 and r.json()["cues"] == 3 and r.json()["converted"] and r.json()["lang"] == "uz" and r.json()["label"] == "O'zbekcha", f"Subtitr .srt → WebVTT ({r.text[:120]})")
sub1 = r.json()["id"]
ok(teach.get(f"{P}/assets/{sub1}").text == VTT_OUT, "Saqlangan subtitr — me'yorlangan WebVTT")
r = teach.post(vb + "/video/captions", params={"name": "rus.srt", "lang": "ru"}, content=RU.encode("cp1251"))
ok(r.status_code == 200 and r.json()["label"] == "Ruscha" and "Привет, студенты!" in teach.get(f"{P}/assets/{r.json()['id']}").text, "Subtitr cp1251 (kirill) — to'g'ri o'qildi")
r = teach.post(vb + "/video/captions", params={"name": "dars2.vtt", "lang": "uz", "label": "O'zbek tili"}, content=VTT_OUT.encode())
ok(r.status_code == 200 and not r.json()["converted"] and r.json()["label"] == "O'zbek tili" and q("SELECT deleted FROM pk_assets WHERE id=?", (sub1,))[0]["deleted"] == 2,
   "Shu tildagi yangi subtitr (.vtt) eskisini almashtiradi")
r = teach.post(vb + "/video/captions", params={"name": "buzuq.srt"}, content=b"1\n00:00:05,000 --> 00:00:04,000\nx\n")
ok(r.status_code == 400 and "2-qator" in r.json()["detail"] and q("SELECT allowed FROM audit_log WHERE action='paket: subtitr rad etildi' ORDER BY id DESC LIMIT 1")[0]["allowed"] == 0,
   f"Buzilgan subtitr — 400, qator raqami bilan, audit jurnalida ({r.json().get('detail', '')[:60]})")
ok(teach.post(vb + "/video/captions", params={"name": "x.srt", "lang": "u1"}, content=SRT.encode()).status_code == 400 and
   teach.post(vb + "/video/captions", params={"name": "katta.srt"}, content=b"x" * (PK.MAX_SUBS + 10)).status_code == 413 and
   kaf.post(vb + "/video/captions", params={"name": "x.srt"}, content=SRT.encode()).status_code == 403, "Subtitr: noto'g'ri til kodi — 400, 2 MB dan katta — 413, kafedra — 403")
BIGPNG = png_bytes((139, 0, 51), (2400, 1350))
r = teach.post(vb + "/video/poster", params={"name": "poster.png"}, content=BIGPNG)
ok(r.status_code == 200 and teach.post(vb + "/video/poster", params={"name": "x.png"}, content=MP4).status_code == 415, "Video posteri yuklandi; rasm emas — 415")
tv = view6()
ok([c_["lang"] for c_ in tv["ready"]["video"]["captions"]] == ["uz", "ru"] and tv["ready"]["video"]["captions"][0]["label"] == "O'zbek tili" and tv["ready"]["video"]["poster"], "Tayyorgarlik: subtitrlar (uz, ru) va poster")
# muqova
teach_name = PK._short(q("SELECT full_name FROM teachers WHERE id=?", (teach_tid,))[0]["full_name"])
tv = view6()
ok(tv["ready"]["cover"]["ok"] and tv["ready"]["cover"]["author"] == teach_name and not tv["ready"]["cover"]["custom"] and teach_name, f"Muqova: muallif — standart holda kurs o'qituvchisi ({teach_name})")
r = teach.post(vb + "/cover", params={"name": "muqova.png"}, content=BIGPNG)
cim = _I.open(io.BytesIO(teach.get(f"{P}/assets/{r.json()['id']}").content))
ok(r.status_code == 200 and cim.format == "JPEG" and cim.size == (1920, 1080) and view6()["ready"]["cover"]["src"] == "dars", f"Dars muqovasi: JPEG, ≤ 1920 px ({cim.size})")
lesson_cover = r.json()["id"]
r = teach.post(f"{P}/courses/{C1}/cover", params={"name": "kurs.png"}, content=png_bytes((0, 90, 140), (800, 450)))
ok(r.status_code == 200 and teach.get(f"{P}/courses/{C1}").json()["media"]["muqova"] == r.json()["id"] and view6()["ready"]["cover"]["src"] == "dars" and
   teach.get(f"{P}/courses/{C1}/topics/{T}").json()["ready"]["cover"]["src"] == "kurs", "Kurs muqovasi: boshqa darslarda ishlatiladi; dars muqovasi ustun")
ok(teach.post(f"{P}/assets/{lesson_cover}/delete").status_code == 200 and view6()["ready"]["cover"]["src"] == "kurs", "Dars muqovasi olib tashlansa — kurs muqovasi")
ok(teach.post(P + "/settings/cover", params={"name": "s.png"}, content=BIGPNG).status_code == 403 and kaf.post(f"{P}/courses/{C1}/cover", params={"name": "k.png"}, content=BIGPNG).status_code == 403
   and teach.post(f"{P}/courses/{mikro['id']}/cover", params={"name": "k.png"}, content=BIGPNG).status_code == 403, "Standart muqova — faqat bo'lim; kurs muqovasi — kafedra / begona o'qituvchi 403")
r = head.post(P + "/settings/cover", params={"name": "standart.jpg"}, content=png_bytes((20, 20, 20), (1280, 720)))
dc = r.json().get("id")
ok(r.status_code == 200 and head.get(P + "/meta").json()["default_cover"] == dc and head.get(f"{P}/courses/{mikro['id']}/topics/3").json()["ready"]["cover"] == {**head.get(f"{P}/courses/{mikro['id']}/topics/3").json()["ready"]["cover"], "src": "standart", "image": dc},
   "Bo'lim standart muqovasi (Sozlamalar) — o'z muqovasi yo'q kurslarda ishlatiladi")
ok(teach.get(f"{P}/assets/{dc}").status_code == 200 and teach.post(f"{P}/assets/{dc}/delete").status_code == 403 and rek.get(f"{P}/assets/{dc}").status_code == 403, "Standart muqova: o'qituvchi ko'radi, o'chira olmaydi (403); rektor — 403")
ok(teach.post(vb + "/cover", params={"name": "bomba.png"}, content=png_header(9000, 9000)).status_code == 413 and teach.post(vb + "/cover", params={"name": "x.png"}, content=b"%PDF-1.4 x").status_code == 415
   and teach.post(vb + "/cover", params={"name": "x.png"}, content=png_bytes((1, 1, 1), (16, 16))).status_code == 415, "Muqova: 81 Mpx — 413, rasm emas / juda kichik — 415 (mavjud rasm himoyalari)")
r = teach.post(vb + "/cover/meta", json={"author": "  Dots.   A. Valiyev "})
ok(r.status_code == 200 and r.json() == {"ok": True, "author": "Dots. A. Valiyev", "custom": True} and view6()["ready"]["cover"]["author"] == "Dots. A. Valiyev", "Muqova muallifi tahrirlandi")
ok(teach.post(vb + "/cover/meta", json={"author": None}).json() == {"ok": True, "author": teach_name, "custom": False} and kaf.post(vb + "/cover/meta", json={"author": "x"}).status_code == 403,
   "Muallif standartga qaytdi; kafedra — 403")
r = teach.post(f"{P}/courses/{C1}/avatar", params={"name": "ustoz.png"}, content=png_bytes((90, 60, 30), (900, 1200)))
aim = _I.open(io.BytesIO(teach.get(f"{P}/assets/{r.json()['id']}").content))
ok(r.status_code == 200 and aim.format == "JPEG" and max(aim.size) == 512 and teach.get(f"{P}/courses/{C1}").json()["media"]["avatar"] == r.json()["id"]
   and teach.post(f"{P}/courses/{mikro['id']}/avatar", params={"name": "u.png"}, content=BIGPNG).status_code == 403, f"O'qituvchi rasmi (kurs bo'yicha): JPEG ≤ 512 px ({aim.size}); begona kurs — 403")
# mashqlar: CRUD, tekshiruv, ruxsatlar
r = teach.post(vb + "/exercises", json={"kind": "match", "stem": "Birliklarni moslang", "pairs": P2, "explanation": "1 bayt = 8 bit"})
e_match = r.json()["exercise"]
ok(r.status_code == 200 and e_match["kind"] == "match" and e_match["status"] == "faol" and e_match["pairs"] == P2 and e_match["title"] == "Birliklarni moslang" and not e_match["ai"], "Mashq: moslashtirish qo'shildi (faol)")
e_sort = teach.post(vb + "/exercises", json={"kind": "sort", "categories": C2}).json()["exercise"]
e_fc = teach.post(vb + "/exercises", json={"kind": "flashcards", "title": "Atamalar", "cards": [{"front": "CPU", "back": "Markaziy protsessor"}, {"front": "RAM", "back": "Tezkor xotira"}]}).json()["exercise"]
e_tmp = teach.post(vb + "/exercises", json={"kind": "flashcards", "cards": [{"front": "x", "back": "y"}]}).json()["exercise"]
ls = teach.get(vb + "/exercises").json()
ok([x_["id"] for x_ in ls["exercises"]] == [e_match["id"], e_sort["id"], e_fc["id"], e_tmp["id"]] and ls["kinds"] == PK.EX_KINDS and e_sort["categories"] == C2 and e_fc["title"] == "Atamalar", "Mashqlar ro'yxati (qo'shilgan tartibda): moslashtirish, saralash, kartochkalar")
for body_, why in (({"kind": "match", "pairs": P2[:1]}, "1 juft"), ({"kind": "match", "pairs": P2 + [{"left": "bayt", "right": "x"}]}, "takroriy chap tomon"), ({"kind": "sort", "categories": C2[:1]}, "1 toifa"),
                   ({"kind": "sort", "categories": C2 + [{"title": "Boshqa", "items": ["Monitor"]}]}, "element ikki toifada"), ({"kind": "flashcards", "cards": []}, "kartochkasiz"),
                   ({"kind": "krossvord", "pairs": P2}, "noma'lum tur"), ({"pairs": P2}, "tursiz")):
    ok(teach.post(vb + "/exercises", json=body_).status_code == 400, f"Mashq tekshiruvi — 400: {why}")
ok(teach.post(vb + "/exercises", json={"kind": "match", "pairs": [{"left": "x"}] * 50}).status_code == 422 and len(teach.get(vb + "/exercises").json()["exercises"]) == 4, "Juda uzun ro'yxat — 422; yaroqsiz mashqlar saqlanmadi")
r = teach.post(f"{P}/exercises/{e_match['id']}", json={"kind": "sort", "stem": "Birliklarni toping", "pairs": pr(3)})
ok(r.status_code == 200 and r.json()["exercise"]["title"] == "Birliklarni toping" and r.json()["exercise"]["kind"] == "match" and len(r.json()["exercise"]["pairs"]) == 3 and r.json()["exercise"]["explanation"] == "",
   "Mashq tahrirlandi (turi o'zgarmaydi)")
ok(teach.post(f"{P}/exercises/{e_match['id']}", json={"pairs": pr(1)}).status_code == 400 and len(teach.get(vb + "/exercises").json()["exercises"][0]["pairs"]) == 3, "Tahrirlashda ham tekshiruv (400) — eski holat saqlanadi")
ok(teach.post(f"{P}/exercises/{e_tmp['id']}/delete").status_code == 200 and teach.post(f"{P}/exercises/{e_tmp['id']}/delete").status_code == 404 and teach.post(f"{P}/exercises/999999", json={"pairs": P2}).status_code == 404
   and len(teach.get(vb + "/exercises").json()["exercises"]) == 3, "Mashq o'chirildi; yo'q mashq — 404")
mb = f"{P}/courses/{mikro['id']}/topics/3"
r = head.post(mb + "/exercises", json={"kind": "match", "pairs": P2})
e_h = r.json()["exercise"]["id"]
ok(r.status_code == 200 and staff.post(f"{P}/exercises/{e_match['id']}", json={"stem": "Bo'lim tahriri", "pairs": pr(2)}).json()["exercise"]["title"] == "Bo'lim tahriri", "Bo'lim (boshliq, xodim) istalgan kursda mashq qo'shadi va o'qituvchinikini tahrirlaydi")
ok(kaf8.get(mb + "/exercises").status_code == 200 and [x_["id"] for x_ in kaf8.get(mb + "/exercises").json()["exercises"]] == [e_h] and len(kaf8.get(mb).json()["exercises"]) == 1, "Kafedra mudiri o'z kafedrasi mashqlarini ko'radi")
ok(kaf8.post(mb + "/exercises", json={"kind": "match", "pairs": P2}).status_code == 403 and kaf8.post(f"{P}/exercises/{e_h}", json={"pairs": P2}).status_code == 403
   and kaf8.post(f"{P}/exercises/{e_h}/delete").status_code == 403 and kaf8.post(mb + "/exercises/ai", json={}).status_code == 403, "Kafedra mudiri: qo'shish / tahrirlash / o'chirish / AI — 403")
ok(teach.get(mb + "/exercises").status_code == 403 and teach.post(mb + "/exercises", json={"kind": "match", "pairs": P2}).status_code == 403 and teach.post(f"{P}/exercises/{e_h}", json={"pairs": P2}).status_code == 403
   and teach.post(f"{P}/exercises/{e_h}/delete").status_code == 403 and teach.post(mb + "/exercises/ai", json={}).status_code == 403, "O'qituvchi: begona kurs mashqlari — ko'rish ham, o'zgartirish ham 403")
ok(rek.get(mb + "/exercises").status_code == 403 and rek.post(mb + "/exercises", json={"kind": "match", "pairs": P2}).status_code == 403 and pro.get(vb + "/exercises").status_code == 403
   and bux.get(mb + "/exercises").status_code == 403 and (kaf_dept == mikro["department_id"] or kaf.get(mb + "/exercises").status_code == 403), "Rektor / prorektor / buxgalteriya / boshqa kafedra — mashqlar 403")
ok(len(head.get(mb + "/exercises").json()["exercises"]) == 1 and q("SELECT COUNT(*) n FROM audit_log WHERE resource='paket' AND allowed=0")[0]["n"] >= den0 + 20, "Rad etilgan urinishlar hech narsani o'zgartirmadi va audit jurnalida")
if not os.environ.get("ANTHROPIC_API_KEY"):
    r = teach.post(vb + "/exercises/ai", json={"sort": True})
    ok(r.status_code == 503 and "AI ulanmagan — administratorga" in r.json()["detail"] and "ANTHROPIC" not in r.json()["detail"] and "qo'lda" in r.json()["detail"], "AI mashqlar: kalit yo'q — 503 (aniq xabar, texnik nomsiz)")
# topshiriq: Word'dagi «Savollar» ro'yxati
r = teach.post(vb + "/text", params={"name": "6-mavzu.docx"}, content=TASKDOC)
tv = view6(); ag = tv["ready"]["assignment"]
ok(r.status_code == 200 and r.json()["refs"] == 2 and ag["ok"] and ag["items"] == TASK_Q and ag["src"] == "matn" and not ag["manual"] and ag["found"] == 3 and ag["text"] == PK.ASSIGNMENT["text"] and ag["avatar"],
   f"Word'dagi «Savollar» ro'yxati → topshiriq savollari ({ag['items']})")
ok("Kompyuter nima?" not in tv["text_html"] and ">Savollar<" not in tv["text_html"] and tv["refs"] == ["Karimov I. Informatika asoslari. T.: Fan, 2020.", "Sobirov A. Axborot texnologiyalari. T., 2019."]
   and tv["text_html"].count("<figure>") == 2, "Savollar matn blokidan olindi; adabiyotlar va rasmlar joyida")
r = teach.post(vb + "/assignment", json={"questions": ["1. Qo'lda yozilgan savol?", "  ", "- Ikkinchi topshiriq", "Ikkinchi topshiriq"]})
ok(r.status_code == 200 and r.json()["questions"] == ["Qo'lda yozilgan savol?", "Ikkinchi topshiriq"] and view6()["ready"]["assignment"]["src"] == "manual" and view6()["ready"]["assignment"]["found"] == 3
   and all(f"<li>{q_}</li>" in view6()["text_html"] for q_ in TASK_Q) and ">Savollar<" in view6()["text_html"],
   "Topshiriq savollari qo'lda (raqam/belgi olinadi, takror va bo'sh tashlanadi); matndagi «Savollar» ro'yxati ishlatilmagani uchun ma'ruza matnida qoladi")
teach.post(vb + "/assignment", json={"questions": []})
ok(not view6()["ready"]["assignment"]["ok"] and all(b_["type"] != "assignment" for b_ in view6()["blocks"]) and all(f"<li>{q_}</li>" in view6()["text_html"] for q_ in TASK_Q),
   "Bo'sh ro'yxat (qo'lda) — topshiriq bloki bo'lmaydi; matndagi «Savollar» yo'qolmaydi (matnda qoladi)")
ok(teach.post(vb + "/assignment", json={"questions": None}).json()["manual"] is False and view6()["ready"]["assignment"]["items"] == TASK_Q and
   "Kompyuter nima?" not in view6()["text_html"] and
   teach.post(vb + "/assignment", json={"questions": [f"Savol {i}?" for i in range(61)]}).status_code == 400 and kaf.post(vb + "/assignment", json={"questions": ["x"]}).status_code == 403,
   "Avtomatik rejimga qaytdi (matndan — ro'yxat yana matndan olinadi); 61 ta savol — 400; kafedra — 403")
r = teach.post(vb + "/assignment", json={"questions": ["Qisqa savol?", "u" * 501]})
ok(r.status_code == 400 and "500" in r.json()["detail"] and view6()["ready"]["assignment"]["items"] == TASK_Q and view6()["ready"]["assignment"]["warnings"] == [] and view6()["ready"]["assignment"]["max"] == 60,
   "Qo'lda kiritilgan juda uzun savol kesilmaydi — 400; ro'yxat o'zgarmadi")
# slayd izohi va audiosi
teach.post(vb + "/slides", params={"name": "taqdimot.pptx"}, content=PPTX)
r = teach.post(vb + "/slides/1/audio", params={"name": "1-slayd.mp3"}, content=MP3)
au1 = r.json().get("id")
ok(r.status_code == 200 and r.json()["kind"] == "mp3" and r.json()["slide"] == 1 and teach.post(vb + "/slides/2/audio", params={"name": "2.wav"}, content=WAV).json()["kind"] == "wav", "Slayd audiosi: .mp3 va .wav (turi baytlardan)")
r = teach.post(vb + "/slides/1/audio", params={"name": "nomi-mp3.mp3"}, content=b"OggS\x00\x02" + b"\0" * 500)
ok(r.status_code == 200 and r.json()["kind"] == "ogg" and q("SELECT deleted FROM pk_assets WHERE id=?", (au1,))[0]["deleted"] == 2, "Kengaytma emas, tarkib hal qiladi (.mp3 nomli Ogg → ogg); yangi audio eskisini almashtiradi")
for nm_, body_, st_, why in (("rasm.mp3", png_bytes((1, 2, 3)), 415, "PNG"), ("exe.mp3", b"MZ\x90\x00" + b"\0" * 100, 415, "exe"), ("video.mp3", WEBM, 415, "WebM video"), ("bosh.mp3", b"", 400, "bo'sh")):
    ok(teach.post(vb + "/slides/1/audio", params={"name": nm_}, content=body_).status_code == st_, f"Audio emas — {st_}: {why}")
ok(teach.post(vb + "/slides/0/audio", params={"name": "a.mp3"}, content=MP3).status_code == 400 and teach.post(vb + "/slides/999/audio", params={"name": "a.mp3"}, content=MP3).status_code == 400
   and kaf.post(vb + "/slides/1/audio", params={"name": "a.mp3"}, content=MP3).status_code == 403, "Slayd raqami noto'g'ri — 400; kafedra — 403")
try: code = teach.post(vb + "/slides/1/audio", params={"name": "katta.mp3"}, content=(x for x in [MP3] + [b"\0" * 1048576] * 21)).status_code
except httpx.HTTPError as e: code = f"uzildi ({type(e).__name__})"
ok(code == 413 or str(code).startswith("uzildi"), f"Audio 21 MB — 413 ({code})")
r = teach.post(vb + "/slides/meta", json={"captions": {"1": "  Birinchi   slayd izohi ", "2": " "}})
ok(r.status_code == 200 and r.json()["captions"] == {"1": "Birinchi slayd izohi"} and teach.post(vb + "/slides/meta", json={"captions": {"x": "a"}}).status_code == 400
   and teach.post(vb + "/slides/meta", json={"captions": {"0": "a"}}).status_code == 400 and kaf.post(vb + "/slides/meta", json={"captions": {"1": "a"}}).status_code == 403, "Slayd izohlari saqlandi (bo'sh — olinadi); noto'g'ri raqam — 400; kafedra — 403")
tv = view6()
ok(tv["slides"][0]["caption"] == "Birinchi slayd izohi" and tv["slides"][0]["audio"] and tv["slides"][1]["audio"] and not tv["slides"][1]["caption"] and tv["ready"]["slides"]["audio"] == 2
   and tv["ready"]["slides"]["captions"] == 1 and tv["slide_audio"]["1"]["kind"] == "ogg", "Dars ko'rinishi: slayd izohi va audiosi")
# bloklar tartibi: «MASHQ VA TOPSHIRIQLAR» bo'limi
types6 = [b_["type"] for b_ in tv["blocks"]]
ok(types6 == ["section", "video", "section", "plan", "text", "refs", "section", "slides", "file", "section", "flashcards", "quiz", "assignment", "reflect"]
   and [b_["title"] for b_ in tv["blocks"] if b_["type"] == "section"] == ["VIDEODARS", "MA'RUZA MATNI", "DARS TAQDIMOTI", "MASHQ VA TOPSHIRIQLAR"], f"Bloklar tartibi (v3): {types6}")
ok([x_["type"] for x_ in tv["quiz_preview"]][-2:] == ["match", "sort"] and tv["ready"]["quiz"]["ok"] and tv["ready"]["quiz"]["exercises"] == 2 and tv["ready"]["exercises"] == {"ok": True, "n": 3, "draft": 0, "match": 1, "sort": 1, "flashcards": 1},
   "Moslashtirish va saralash — test blokida, Test bank savollaridan keyin; kartochkalar — alohida blok")
teach.post(vb + "/settings", json={"sections": {"practice": "MASHQLAR"}, "blocks": {"flashcards": False, "assignment": False, "cover": False}, "assignment": {"text": "Bajaring"}})
tv = view6()
ok([b_["title"] for b_ in tv["blocks"] if b_["type"] == "section"][-1] == "MASHQLAR" and not {"flashcards", "assignment"} & {b_["type"] for b_ in tv["blocks"]} and "Kompyuter nima?" in tv["text_html"]
   and not tv["ready"]["cover"]["ok"] and tv["settings"]["assignment"] == {**PK.ASSIGNMENT, "text": "Bajaring"},
   "Dars sozlamasi: bo'lim nomi, kartochkalar / topshiriq / muqova o'chirildi — «Savollar» matnga qaytdi")
teach.post(vb + "/settings", json={"blocks": {"quiz": False, "flashcards": False, "assignment": False}})
ok("MASHQ VA TOPSHIRIQLAR" not in [b_["title"] for b_ in view6()["blocks"]] and view6()["blocks"][-1]["type"] == "reflect", "Bo'sh guruh — «MASHQ VA TOPSHIRIQLAR» bo'limi ham chiqmaydi")
teach.post(vb + "/settings", json={"reset": True})
t5 = teach.get(f"{P}/courses/{C1}/topics/{T + 1}").json()
ok(("MASHQ VA TOPSHIRIQLAR" in [b_["title"] for b_ in t5["blocks"]]) == bool({"quiz", "flashcards", "assignment"} & {b_["type"] for b_ in t5["blocks"]}), "Mashq/test/topshiriq yo'q darsda bo'lim sarlavhasi yo'q")
m2 = head.get(P + "/meta").json(); d0 = m2["defaults"]
ok(d0["assignment"] == PK.ASSIGNMENT and d0["sections"]["practice"] == "MASHQ VA TOPSHIRIQLAR" and d0["video_source"] == "file" and all(d0["blocks"][k_] for k_ in ("cover", "flashcards", "assignment"))
   and m2["limits"]["video_mb"] == PK.video_max() // 1048576 and m2["limits"]["package_video_mb"] == 500 and m2["limits"]["audio_mb"] == 20 and set(m2["ex_kinds"]) == {"match", "sort", "flashcards"},
   "Standart sozlamalar (v3): topshiriq matni/imzosi, bo'lim nomi, video manbasi, yangi bloklar yoqilgan; chegaralar")
r = head.post(P + "/settings", json={**d0, "assignment": {"text": "PDF qilib yuklang", "author": ""}, "sections": {**d0["sections"], "practice": "AMALIYOT"}})
ok(r.status_code == 200 and r.json()["defaults"]["assignment"] == {**PK.ASSIGNMENT, "text": "PDF qilib yuklang"} and r.json()["defaults"]["sections"]["practice"] == "AMALIYOT"
   and view6()["ready"]["assignment"]["text"] == "PDF qilib yuklang" and head.post(P + "/settings", json={**d0, "video_source": "vimeo"}).status_code == 400, "Sozlamalar: topshiriq shabloni va bo'lim nomi (bo'sh qiymat — standart qoladi); noto'g'ri video manbasi — 400")
ok(head.post(P + "/settings", json=d0).json()["defaults"] == d0, "Standart sozlamalar tiklandi")

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
    ok(o1["columns"] == ["pk_topics.keypoints", "pk_topics.extra", "pk_packages.lesson", "pk_packages.src_sig"] and o1["packages"] == 2 and o1["defaults"] and o2 == {"columns": [], "packages": 0, "defaults": False}
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
    ok(types == ["section", "video", "section", "plan", "text", "section", "slides", "section", "quiz", "assignment", "reflect"] and [b["id"] for b in cj["blocks"]] == [f"b{i}" for i in range(1, len(types) + 1)],
       f"Bloklar tartibi (kafedra shabloni, v3) va id: {types}")
    ok([b["title"] for b in cj["blocks"] if b["type"] == "section"] == ["VIDEODARS", "MA'RUZA MATNI", "DARS TAQDIMOTI", "MASHQ VA TOPSHIRIQLAR"],
       "Bo'lim sarlavhalari: VIDEODARS, MA'RUZA MATNI, DARS TAQDIMOTI, MASHQ VA TOPSHIRIQLAR")
    asb_ = next(b for b in cj["blocks"] if b["type"] == "assignment")
    ok(asb_ == {"id": asb_["id"], "type": "assignment", "title": "Topshiriq", "text": "Quyidagi topshiriqni bajarib PDF shaklda LMS platformasiga joylang",
                "author": "Sizning professor-o'qituvchingiz", "avatar": None, "questions": ["Mikroiqtisodiyot nimani o'rganadi?", "Muqobil xarajat deganda nimani tushunasiz?"]}
       and "Nazorat savollari" not in next(b for b in cj["blocks"] if b["type"] == "text")["html"],
       "Topshiriq bloki: namuna matndagi «Nazorat savollari» ro'yxati matndan olinib, savollar sifatida ko'chdi (standart matn va imzo)")
    ok(cj["cover"] == {"image": "assets/cover.jpg" if "assets/cover.jpg" in names else None, "author": PK._short(mikro_teacher)} and list(cj)[:6] == ["v", "id", "title", "lang", "layout", "cover"],
       f"Kontrakt v3: cover {{image, author — kurs o'qituvchisi F.I.Sh.}} ({cj['cover']})")
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
        except PK.HTTPException as e: ok(e.status_code == 503 and "AI ulanmagan" in e.detail and "ANTHROPIC" not in e.detail, "AI kalitsiz — 503, o'zbekcha aniq xabar")
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
    ok([b["type"] for b in ca["blocks"]] == ["section", "plan", "text", "keypoints", "refs", "section", "slides", "file", "section", "quiz", "reflect"]
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
    # --- Rise 360 (kontrakt v3), jarayon ichida: L3 — video fayl (oqim), subtitr, muqova, mashqlar, AI mashqlar, topshiriq, slayd audiosi
    L3 = 3
    VID = MP4 + bytes(range(256)) * 9000                                  # ≈ 2,4 MB, deterministik
    tmpd = PK.store() / "tmp"
    class _Req:      # oqimli tana: har bo'lakdan oldin diskdagi vaqtinchalik fayl hajmini yozib boradi (oldingi bo'laklar diskka yozilganmi)
        def __init__(self, chunks, headers=None): self.chunks, self.headers, self.n, self.seen = chunks, headers or {}, 0, []
        async def stream(self):
            for ch in self.chunks:
                parts = list(tmpd.glob("up_*.part")) if tmpd.is_dir() else []
                self.seen.append(parts[0].stat().st_size if parts else 0)
                self.n += 1; yield ch
    def stream_up(chunks, headers=None, kinds=PK.VIDEO_KINDS):
        rq = _Req(chunks, headers)
        try: return asyncio.run(PK._stream_upload(rq, PK.video_max(), kinds, "Video: .mp4 yoki .webm")), rq
        except PK.HTTPException as e: return e, rq
    CH = 256 * 1024
    up, rq = stream_up([VID[i:i + CH] for i in range(0, len(VID), CH)])
    sent = [sum(len(c_) for c_ in rq.chunks[:i]) for i in range(len(rq.chunks))]
    ok(isinstance(up, dict) and up["kind"] == "mp4" and up["size"] == len(VID) and up["sha256"] == PK._sha(VID) and up["path"].read_bytes() == VID
       and all(rq.seen[i] >= sent[i] - 65536 for i in range(len(sent))) and rq.seen[-1] > len(VID) // 2,
       f"_stream_upload: tana bo'laklab DISKKA yoziladi (har bo'lakdan oldin oldingilari faylda: {rq.seen[1]}, {rq.seen[2]}, … {rq.seen[-1]} bayt), sha256 yo'l-yo'lakay")
    r = PK.upload_video(hctx, MID, L3, up, "3-dars.mp4")
    va_ = dict(dst.execute("SELECT * FROM pk_assets WHERE id=?", (r["id"],)).fetchone())
    ok(not up["path"].exists() and not list(tmpd.glob("*")) and (PK.store() / va_["path"]).read_bytes() == VID and va_["sha256"] == PK._sha(VID), "Video fayl joyiga ko'chirildi (os.replace), vaqtinchalik fayl qolmadi")
    e_, rq = stream_up([VID[:10], VID[10:30], VID[30:70], VID[70:]])
    ok(isinstance(e_, dict) and e_["kind"] == "mp4", "_stream_upload: tur birinchi 64 baytdan — kichik bo'laklarda ham"); e_["path"].unlink()
    def endless(first):
        yield first
        while True: yield b"\0" * CH
    os.environ["ISFT_CORE_PK_VIDEO_MB"] = "1"
    e_, rq = stream_up(endless(VID[:CH]))
    ok(getattr(e_, "status_code", 0) == 413 and rq.n == 5 and not list(tmpd.glob("*")), f"_stream_upload: cheksiz oqim chegarada (1 MB) to'xtatildi — 413, {rq.n} bo'lak o'qildi, vaqtinchalik fayl o'chirildi")
    e_, rq = stream_up([VID], {"content-length": str(5 * 1024 * 1024)})
    ok(getattr(e_, "status_code", 0) == 413 and rq.n == 0, "_stream_upload: Content-Length chegaradan katta — tana o'qilmasdan 413")
    os.environ.pop("ISFT_CORE_PK_VIDEO_MB")
    e_, rq = stream_up(endless(b"MZ\x90\x00" + b"\0" * 200))
    ok(getattr(e_, "status_code", 0) == 415 and rq.n == 1 and not list(tmpd.glob("*")), "_stream_upload: noto'g'ri tur — 415 birinchi bo'lakdayoq (qolgan tana o'qilmaydi)")
    e_, rq = stream_up([])
    ok(getattr(e_, "status_code", 0) == 400, "_stream_upload: bo'sh tana — 400")
    try: PK.upload_video(tctx, MID, L3, stream_up([VID])[0], "x.mp4"); ok(False, "o'qituvchi begona kursga video yukladi")
    except RB.AccessDenied: ok(not list(tmpd.glob("*")), "upload_video: begona kurs — rad etildi, vaqtinchalik fayl o'chirildi")
    # manbalar: Word («Savollar» bilan), subtitrlar, poster, muqova ustuvorligi, o'qituvchi rasmi, taqdimot + slayd audiosi/izohi
    dst.execute("UPDATE pk_assets SET deleted=1 WHERE purpose IN ('muqova','avatar')"); dst.commit()
    PK.upload_text(hctx, MID, L3, TASKDOC, None, "3-mavzu.docx")
    PK.upload_subs(hctx, MID, L3, SRT.encode("utf-16"), "dars.srt", "uz"); PK.upload_subs(hctx, MID, L3, RU.encode("cp1251"), "rus.srt", "ru")
    PK.upload_slot_image(hctx, "poster", MID, L3, png_bytes((10, 10, 60), (1280, 720)), "poster.png")
    g0 = PK.gather(MID, L3)
    ok(g0["content"]["cover"] == {"image": None, "author": PK._short(mikro_teacher)} and "assets/cover.jpg" not in g0["files"] and g0["ready"]["cover"]["src"] is None, "Muqova rasmi yo'q — cover.image = null (pleyer brend rangida chizadi)")
    try: PK.upload_slot_image(tctx, "muqova", 0, 0, BIGPNG, "s.png"); ok(False, "o'qituvchi standart muqovani o'zgartirdi")
    except RB.AccessDenied: ok(True, "Standart muqova: o'qituvchi — rad etildi")
    cov_ids = [PK.upload_slot_image(hctx, "muqova", c_, n_, png_bytes(col, (1600, 900)), "m.png")["id"] for c_, n_, col in ((0, 0, (10, 10, 10)), (MID, 0, (0, 90, 140)), (MID, L3, (139, 0, 51)))]
    ok(PK.gather(MID, 2)["ready"]["cover"]["src"] == "kurs" and PK.gather(MID, L3)["ready"]["cover"] == {"ok": True, "image": cov_ids[2], "src": "dars", "author": PK._short(mikro_teacher), "custom": False}
       and PK._cover_source(own["id"], 1)[1] == "standart", "Muqova ustuvorligi: dars > kurs > bo'lim standarti")
    PK.set_cover_meta(hctx, MID, L3, "Prof. N. Karimova")
    av_id = PK.upload_slot_image(hctx, "avatar", MID, 0, png_bytes((90, 60, 30), (600, 600)), "ustoz.png")["id"]
    PK.upload_slides(hctx, MID, L3, PPTX, "taqdimot.pptx")
    PK.upload_slide_audio(hctx, MID, L3, 2, MP3, "2-slayd.mp3"); PK.set_slide_captions(hctx, MID, L3, {"1": "Kirish slaydi", "2": "Rasmli slayd"})
    for bad_n in (0, 201):
        try: PK.upload_slide_audio(hctx, MID, L3, bad_n, MP3, "x.mp3"); ok(False, "noto'g'ri slayd raqami o'tdi")
        except PK.HTTPException as e: ok(e.status_code == 400, f"Slayd audiosi: {bad_n}-slayd — 400")
    # mashqlar: qo'lda + ruxsat + chegara
    xm = PK.save_exercise(hctx, MID, L3, "match", {"stem": "Birliklarni moslang", "pairs": P2, "explanation": "1 bayt = 8 bit"})["exercise"]
    xs = PK.save_exercise(hctx, MID, L3, "sort", {"categories": C2})["exercise"]
    xf = PK.save_exercise(hctx, MID, L3, "flashcards", {"title": "Atamalar", "cards": [{"front": "CPU", "back": "Markaziy protsessor"}]})["exercise"]
    for fn_, why in ((lambda: PK.save_exercise(tctx, MID, L3, "match", {"pairs": P2}), "qo'shish"), (lambda: PK.save_exercise(tctx, 0, 0, "", {"pairs": P2}, xm["id"]), "tahrirlash"),
                     (lambda: PK.delete_exercise(tctx, xm["id"]), "o'chirish"), (lambda: PK.exercise_list(tctx, MID, L3), "ko'rish"), (lambda: PK.ai_exercises(tctx, MID, L3), "AI")):
        try: fn_(); ok(False, f"o'qituvchi begona kurs mashqi: {why}")
        except RB.AccessDenied: ok(True, f"Mashqlar: o'qituvchi begona kursda — {why} rad etildi")
    saved_max = PK.MAX_EXERCISES; PK.MAX_EXERCISES = 3
    try: PK.save_exercise(hctx, MID, L3, "match", {"pairs": P2}); ok(False, "mashqlar chegarasi ishlamadi")
    except PK.HTTPException as e: ok(e.status_code == 400 and "ko'pi bilan 3" in e.detail, "Bitta darsda mashqlar soni chegaralangan (MAX_EXERCISES) — 400")
    PK.MAX_EXERCISES = saved_max
    # AI: mashqlar (soxta Claude) — iqtibosi matnda yo'q band tashlanadi; natija qoralama
    calls_x = []
    AIX = {"pairs": [{"left": "Bayt", "right": "Sakkiz bitdan iborat o'lchov birligi", "quote": "Bayt — sakkiz bitdan iborat asosiy o'lchov birligi"},
                     {"left": "Cho'ntak kompyuteri", "right": "Eng kichik kompyuter", "quote": "Eng kichigi — cho'ntak kompyuteri"},
                     {"left": "Kvant kompyuteri", "right": "1950-yilda yaratilgan", "quote": "Kvant kompyuterlari 1950-yilda yaratilgan"},            # matnda yo'q
                     {"left": "bayt", "right": "Takroriy chap tomon", "quote": "Bayt — sakkiz bitdan iborat asosiy o'lchov birligi"},               # takror
                     {"left": "Axborot texnologiyalari", "right": "Zamonaviy jamiyatning asosi", "quote": "Axborot texnologiyalari zamonaviy jamiyatning asosidir"},
                     {"left": "", "right": "Bo'sh", "quote": "Bayt — sakkiz bitdan"}],
           "cards": [{"front": "Bayt necha bit?", "back": "Sakkiz bit", "quote": "Bayt — sakkiz bitdan iborat"},
                     {"front": "Kompyuterlar nimaga ko'ra turlarga bo'linadi?", "back": "O'lchami va vazifasiga ko'ra", "quote": "Kompyuterlar o'lchami va vazifasiga ko'ra bir necha turga bo'linadi"},
                     {"front": "Internet qachon paydo bo'lgan?", "back": "1969-yilda", "quote": "Internet 1969-yilda paydo bo'lgan"}],                        # matnda yo'q
           "categories": [{"title": "O'lchov birliklari", "items": [{"text": "Bayt", "quote": "Bayt — sakkiz bitdan iborat"}, {"text": "Gigabayt", "quote": "Gigabayt — ming megabayt"}]},     # 2-si matnda yo'q
                          {"title": "Kompyuter turlari", "items": [{"text": "Cho'ntak kompyuteri", "quote": "Eng kichigi — cho'ntak kompyuteri"}]},
                          {"title": "Bo'sh toifa", "items": [{"text": "Superkompyuter", "quote": "Superkompyuterlar eng tezkor"}]}]}                           # hammasi matnda yo'q
    def fake_ex(**kw):
        calls_x.append(kw); return json.loads(json.dumps(AIX)), {"in": 1500, "out": 600, "model": kw["model"]}
    saved_cc = (CC.call_json, CC.has_key)
    try:
        CC.has_key = lambda: False
        try: PK.ai_exercises(hctx, MID, L3); ok(False, "kalitsiz AI chaqirildi")
        except PK.HTTPException as e: ok(e.status_code == 503 and "AI ulanmagan" in e.detail and "ANTHROPIC" not in e.detail, "AI mashqlar kalitsiz — 503")
        CC.has_key = lambda: True; CC.call_json = fake_ex
        os.environ["ISFT_CORE_PK_MODEL"] = "claude-test-model"
        r = PK.ai_exercises(hctx, MID, L3, sort=True)
        os.environ.pop("ISFT_CORE_PK_MODEL")
        kinds_ = {x_["kind"]: x_ for x_ in r["exercises"]}
        ok(list(kinds_) == ["match", "flashcards", "sort"] and all(x_["status"] == "qoralama" and x_["ai"] for x_ in r["exercises"]), "AI mashqlar: moslashtirish + kartochkalar + saralash — QORALAMA (src=ai)")
        ok([p_["left"] for p_ in kinds_["match"]["pairs"]] == ["Bayt", "Cho'ntak kompyuteri", "Axborot texnologiyalari"] and [c_["front"] for c_ in kinds_["flashcards"]["cards"]] == ["Bayt necha bit?", "Kompyuterlar nimaga ko'ra turlarga bo'linadi?"]
           and kinds_["sort"]["categories"] == [{"title": "O'lchov birliklari", "items": ["Bayt"]}, {"title": "Kompyuter turlari", "items": ["Cho'ntak kompyuteri"]}] and r["dropped"] == 6,
           f"Iqtibos filtri: matnda yo'q juft / kartochka / element, takror va bo'sh band tashlandi ({r['dropped']} ta)")
        ok(len(kinds_["match"]["quotes"]) == 3 and kinds_["match"]["quotes"][0]["quote"].startswith("Bayt — sakkiz") and "quote" not in kinds_["match"]["pairs"][0], "Iqtiboslar qoralamada saqlanadi (muharrirda ko'rinadi), juftlarning o'zida emas")
        kw = calls_x[-1]; sent = kw["content"][0]["text"]
        ok(kw["model"] == "claude-test-model" and kw["schema"] == PK.EX_SCHEMA and kw["schema"]["additionalProperties"] is False and set(kw["schema"]["required"]) == {"pairs", "cards", "categories"}
           and kw["schema"]["properties"]["pairs"]["items"]["required"] == ["left", "right", "quote"] and kw["schema"]["properties"]["pairs"]["items"]["additionalProperties"] is False,
           "AI so'rovi: model — ISFT_CORE_PK_MODEL, qat'iy sxema (additionalProperties=false, quote majburiy)")
        ok("Bayt — sakkiz bitdan" in sent and "[RASM:" not in sent and "[JADVAL:" not in sent and "kerak" in sent.split(">>>")[-1] and not re.search(r"talaba|student|baho|ism", sent.split("MA'RUZA MATNI:")[0], re.I),
           "AI so'rovi: faqat dars matni (belgilarsiz), talaba ma'lumotisiz; saralash so'ralgan")
        gq = next(b for b in PK.gather(MID, L3)["content"]["blocks"] if b["type"] == "quiz")
        ok([x_["id"] for x_ in gq["questions"]][-2:] == [f"x{xm['id']}", f"x{xs['id']}"] and PK.gather(MID, L3)["ready"]["exercises"]["draft"] == 3 and
           sum(1 for b in PK.gather(MID, L3)["content"]["blocks"] if b["type"] == "flashcards") == 1, "AI qoralamalari paketga kirmaydi (saqlanmaguncha)")
        r2 = PK.ai_exercises(hctx, MID, L3)                       # saralashsiz; oldingi AI qoralamalari almashtiriladi
        ok([x_["kind"] for x_ in r2["exercises"]] == ["match", "flashcards"] and r2["dropped"] == 4 and "kerak emas" in calls_x[-1]["content"][0]["text"]
           and dst.execute("SELECT COUNT(*) FROM pk_exercises WHERE course_id=? AND topic_no=? AND status='qoralama' AND deleted=0", (MID, L3)).fetchone()[0] == 2,
           "AI mashqlar (saralashsiz): categories e'tiborsiz; oldingi AI qoralamalari almashtirildi")
        xa = PK.save_exercise(hctx, 0, 0, "", {"stem": "Atamani ta'rifi bilan moslang", "pairs": r2["exercises"][0]["pairs"], "status": "faol"}, r2["exercises"][0]["id"])["exercise"]
        ok(xa["status"] == "faol" and xa["ai"] and f"x{xa['id']}" in [x_["id"] for x_ in next(b for b in PK.gather(MID, L3)["content"]["blocks"] if b["type"] == "quiz")["questions"]],
           "O'qituvchi/bo'lim tahrirlab saqlagach AI mashq «faol» — paketga kiradi")
        ai_rows = dst.execute("SELECT kind, ok, n_got, n_dropped, model FROM pk_ai WHERE course_id=? AND topic_no=? ORDER BY id", (MID, L3)).fetchall()
        ok([tuple(x_) for x_ in ai_rows] == [("exercises", 1, 3, 6, "claude-test-model"), ("exercises", 1, 2, 4, "claude-opus-5-5")], "AI jurnali (pk_ai): tur, natija, tashlanganlar, model")
        def none_grounded(**kw): return {"pairs": [{"left": "A", "right": "B", "quote": "matnda yo'q jumla"}], "cards": [], "categories": []}, {"in": 1, "out": 1, "model": kw["model"]}
        CC.call_json = none_grounded
        try: PK.ai_exercises(hctx, MID, L3); ok(False, "asossiz AI javobi qabul qilindi")
        except PK.HTTPException as e: ok(e.status_code == 502 and "asoslangan" in e.detail and dst.execute("SELECT COUNT(*) FROM pk_exercises WHERE course_id=? AND topic_no=? AND status='qoralama' AND deleted=0", (MID, L3)).fetchone()[0] == 1,
                                         "Hech bir band matnga asoslanmagan — 502, mavjud qoralama saqlanib qoladi")
        CC.call_json = boom
        try: PK.ai_exercises(hctx, MID, L3); ok(False, "AI xatosi yutildi")
        except PK.HTTPException as e: ok(e.status_code == 502 and "band" in e.detail, "AI xatosi — 502")
        # MAX_EXERCISES — AI uchun ham (save_exercise bilan bir xil chegara): joy yo'q bo'lsa 400, AI chaqirilmaydi, qoralamalar joyida
        live_n = dst.execute("SELECT COUNT(*) FROM pk_exercises WHERE course_id=? AND topic_no=? AND deleted=0 AND NOT (status='qoralama' AND src='ai')", (MID, L3)).fetchone()[0]
        drafts_n = lambda: dst.execute("SELECT COUNT(*) FROM pk_exercises WHERE course_id=? AND topic_no=? AND deleted=0 AND status='qoralama'", (MID, L3)).fetchone()[0]
        CC.call_json = fake_ex; nc_, nd_, nai_ = len(calls_x), drafts_n(), dst.execute("SELECT COUNT(*) FROM pk_ai").fetchone()[0]
        saved_max = PK.MAX_EXERCISES
        try:
            for lim_, sort_ in ((live_n, False), (live_n + 1, False), (live_n + 2, True)):
                PK.MAX_EXERCISES = lim_
                try: PK.ai_exercises(hctx, MID, L3, sort=sort_); ok(False, f"AI mashqlar chegaradan oshdi (MAX={lim_})")
                except PK.HTTPException as e:
                    ok(e.status_code == 400 and f"ko'pi bilan {lim_} ta mashq" in e.detail and len(calls_x) == nc_ and drafts_n() == nd_ and dst.execute("SELECT COUNT(*) FROM pk_ai").fetchone()[0] == nai_,
                       f"AI mashqlar: darsda {live_n} ta mashq, chegara {lim_}{' (saralash bilan)' if sort_ else ''} — 400, AI chaqirilmadi, mavjud qoralamalar joyida ({e.detail[:60]}…)")
            PK.MAX_EXERCISES = live_n + 2; CC.call_json = boom
            try: PK.ai_exercises(hctx, MID, L3); ok(False, "AI xatosi yutildi")
            except PK.HTTPException as e: ok(e.status_code == 502, "AI mashqlar: joy yetarli bo'lsa (chegara = mavjud + 2) chegara tekshiruvidan o'tadi — AI chaqiriladi")
        finally:
            PK.MAX_EXERCISES = saved_max
        os.environ["ISFT_CORE_PK_DAILY"] = "1"
        try: PK.ai_exercises(hctx, MID, L3); ok(False, "kunlik cheklov ishlamadi")
        except PK.HTTPException as e: ok(e.status_code == 429, "AI mashqlar: kunlik cheklov (xulosalar bilan umumiy) — 429")
        os.environ.pop("ISFT_CORE_PK_DAILY", None)
    finally:
        CC.call_json, CC.has_key = saved_cc
    # bloklar tartibi va kontrakt v3 maydonlari
    g3 = PK.gather(MID, L3); c3 = g3["content"]; t3 = [b["type"] for b in c3["blocks"]]
    ok(t3 == ["section", "video", "section", "plan", "text", "refs", "section", "slides", "file", "section", "flashcards", "quiz", "assignment", "reflect"]
       and [b["title"] for b in c3["blocks"] if b["type"] == "section"][-1] == "MASHQ VA TOPSHIRIQLAR" and [b["id"] for b in c3["blocks"]] == [f"b{i}" for i in range(1, len(t3) + 1)],
       f"Bloklar tartibi (v3): … → bo'lim «MASHQ VA TOPSHIRIQLAR» → kartochkalar → test → topshiriq → o'z-o'zini baholash ({t3})")
    by3 = {b["type"]: b for b in c3["blocks"]}
    ok(c3["cover"] == {"image": "assets/cover.jpg", "author": "Prof. N. Karimova"} and Path(g3["files"]["assets/cover.jpg"]).read_bytes() == (PK.store() / dst.execute("SELECT path FROM pk_assets WHERE id=?", (cov_ids[2],)).fetchone()[0]).read_bytes(),
       "cover: {image: assets/cover.jpg (dars muqovasi), author — tahrirlangan}")
    ok(by3["video"] == {"id": "b2", "type": "video", "title": "Videodars", "provider": "file", "src": "assets/video/video.mp4", "poster": "assets/video/video.jpg",
                        "captions": [{"lang": "uz", "label": "O'zbekcha", "src": "assets/video/video.uz.vtt"}, {"lang": "ru", "label": "Ruscha", "src": "assets/video/video.ru.vtt"}]}
       and isinstance(g3["files"]["assets/video/video.mp4"], PK.BigFile) and g3["files"]["assets/video/video.mp4"].sha256 == PK._sha(VID), "video bloki (fayl): provider=file, src, poster, captions[uz, ru]; fayl — BigFile (xotiraga o'qilmaydi)")
    ok([(s_.get("caption"), s_.get("audio")) for s_ in by3["slides"]["slides"]] == [("Kirish slaydi", None), ("Rasmli slayd", "assets/audio/s2.mp3")] and "audio" not in by3["slides"]["slides"][0], "slides[]: caption va audio (faqat borlarida)")
    ok(by3["flashcards"] == {"id": by3["flashcards"]["id"], "type": "flashcards", "title": "Atamalar", "cards": [{"front": "CPU", "back": "Markaziy protsessor"}]}, "flashcards bloki: {title, cards[{front, back}]}")
    qx = {x_["id"]: x_ for x_ in by3["quiz"]["questions"]}
    ok(qx[f"x{xm['id']}"] == {"id": f"x{xm['id']}", "type": "match", "stem": "Birliklarni moslang", "pairs": P2, "explanation": "1 bayt = 8 bit"}
       and qx[f"x{xs['id']}"] == {"id": f"x{xs['id']}", "type": "sort", "stem": "Elementlarni toifalarga ajrating", "categories": C2, "explanation": ""}
       and [x_["id"] for x_ in by3["quiz"]["questions"]][-3:] == [f"x{xm['id']}", f"x{xs['id']}", f"x{xa['id']}"] and all(x_["id"][0] == "q" for x_ in by3["quiz"]["questions"][:-4]) and c3["tracking"]["completion"] == "view_and_quiz",
       f"quiz.questions: match {{pairs}} va sort {{categories}} — Test bank savollaridan keyin; test bor — yakunlash view_and_quiz")
    ok(by3["assignment"] == {"id": by3["assignment"]["id"], "type": "assignment", "title": "Topshiriq", "text": PK.ASSIGNMENT["text"], "author": PK.ASSIGNMENT["author"], "avatar": "assets/img/avatar.jpg", "questions": TASK_Q}
       and "Kompyuter nima?" not in by3["text"]["html"] and by3["refs"]["items"][0].startswith("Karimov"), "assignment bloki: Word'dagi «Savollar» → questions, o'qituvchi rasmi; savollar matn blokidan olingan")
    PK.set_topic_settings(hctx, MID, L3, {"video_source": "youtube"}); PK.set_video(hctx, MID, L3, f"https://youtu.be/{ID}")
    gy = PK.gather(MID, L3)
    ok(next(b for b in gy["content"]["blocks"] if b["type"] == "video")["provider"] == "youtube" and not any(k_.startswith("assets/video/") for k_ in gy["files"]), "video_source=youtube: fayl va subtitrlar paketga kirmaydi")
    PK.set_topic_settings(hctx, MID, L3, {}, reset=True); PK.set_video(hctx, MID, L3, "")
    # yig'ish: har tur — validate_zip, video ZIP_STORED, diskka oqim bilan
    z3 = {}
    for mode in ("xapi", "scorm12", "scorm2004", "none"):
        r = PK.build_topic(hctx, MID, L3, mode)
        prow = dict(dst.execute("SELECT * FROM pk_packages WHERE id=?", (r["package"]["id"],)).fetchone()); pf_ = PK.store() / prow["file"]
        z3[mode] = pf_.read_bytes()
        ok(r["validation"]["ok"] and r["package"]["status"] == "tayyor" and prow["size"] == len(z3[mode]) and prow["sha256"] == PK._sha(z3[mode]) and not list(pf_.parent.glob("*.tmp")),
           f"L3 {mode}: video faylli paket yig'ildi, validate_zip o'tdi ({len(z3[mode]) // 1024} KB); hajm/sha256 fayl bilan mos, vaqtinchalik fayl qolmadi{'' if r['validation']['ok'] else r['validation']['errors']}")
    zn = zipfile.ZipFile(io.BytesIO(z3["none"])); n3 = set(zn.namelist())
    ok({"assets/video/video.mp4", "assets/video/video.jpg", "assets/video/video.uz.vtt", "assets/video/video.ru.vtt", "assets/audio/s2.mp3", "assets/cover.jpg", "assets/img/avatar.jpg"} <= n3
       and zn.read("assets/video/video.mp4") == VID and zn.read("assets/video/video.uz.vtt").decode() == VTT_OUT and zn.read("assets/audio/s2.mp3") == MP3, "Zip: video, poster, subtitrlar, audio, muqova, o'qituvchi rasmi — o'z yo'llarida, baytlari asl bilan bir xil")
    ok(all(zn.getinfo(n_).compress_type == zipfile.ZIP_STORED for n_ in ("assets/video/video.mp4", "assets/audio/s2.mp3", "assets/cover.jpg")) and zn.getinfo("assets/video/video.uz.vtt").compress_type == zipfile.ZIP_DEFLATED
       and zn.getinfo("assets/video/video.mp4").compress_size == len(VID), "Video va audio zipda ZIP_STORED (qayta siqilmaydi); subtitr — siqilgan")
    cj3 = json.loads(zn.read("content.json"))
    ok(list(cj3) == ["v", "id", "title", "lang", "layout", "cover", "course", "topic", "lesson", "brand", "built", "blocks", "tracking"] and cj3["v"] == 1, "content.json kalitlari tartibi (cover — ixtiyoriy, v = 1)")
    cont = {"v": 1, "id": "isft-test-v3", **{k: v for k, v in g3["content"].items() if k != "v"}, "built": "2026-11-11T10:00:00"}
    b1, b2 = PK.build_zip(cont, g3["files"], "scorm12"), PK.build_zip(json.loads(json.dumps(cont)), dict(g3["files"]), "scorm12")
    d1, d2 = PK.build_zip(cont, g3["files"], "scorm12", out_dir=tmp / "det"), PK.build_zip(cont, g3["files"], "scorm12", out_dir=tmp / "det")
    ok(PK._sha(b1) == PK._sha(b2) and isinstance(d1, Path) and d1 != d2 and PK._file_sha(d1) == PK._file_sha(d2) == PK._sha(b1),
       f"Deterministik (video fayl bilan ham): xotirada va diskka oqim bilan yozilgan zip — bir xil sha256 ({PK._sha(b1)[:12]}…)")
    ok(PK.validate_zip(d1)["ok"] and PK.validate_zip(d1)["size"] == len(b1), "validate_zip diskdagi zipni ham tekshiradi (Path — xotiraga o'qimasdan)"); d1.unlink(); d2.unlink()
    ok(PK.build_topic(hctx, MID, L3, "xapi")["unchanged"], "Video faylli dars: manba o'zgarmasa qayta yig'ilmaydi (barmoq izi — saqlangan sha256 bo'yicha)")
    # ko'rish: media uchun HTTP Range
    pid3 = dst.execute("SELECT id FROM pk_packages WHERE course_id=? AND topic_no=? AND mode='xapi' ORDER BY version DESC", (MID, L3)).fetchone()[0]
    def pbody(resp):
        async def rd():
            out_ = b""
            async for ch in resp.body_iterator: out_ += ch if isinstance(ch, bytes) else ch.encode()
            return out_
        return asyncio.run(rd())
    N = len(VID); vp = "assets/video/video.mp4"
    for rng_, a_, b_ in (("bytes=0-99", 0, 99), ("bytes=100-", 100, N - 1), ("bytes=-64", N - 64, N - 1), (f"bytes={N - 10}-{N + 500}", N - 10, N - 1), ("bytes=0-0", 0, 0), (f"bytes=-{N * 3}", 0, N - 1)):
        x = PK.preview_file(hctx, pid3, vp, rng_)
        ok(x.status_code == 206 and x.headers["content-range"] == f"bytes {a_}-{b_}/{N}" and x.headers["content-length"] == str(b_ - a_ + 1) and x.headers["accept-ranges"] == "bytes"
           and x.media_type == "video/mp4" and pbody(x) == VID[a_:b_ + 1], f"Preview Range {rng_!r} → 206, Content-Range bytes {a_}-{b_}/{N}, tana mos")
    for rng_ in (f"bytes={N}-", "bytes=50-10", "bytes=-0", "bytes=abc", "bytes=0-10,20-30", "pages=1-2"):
        x = PK.preview_file(hctx, pid3, vp, rng_)
        ok(x.status_code == 416 and x.headers["content-range"] == f"bytes */{N}" and not x.body, f"Preview Range {rng_!r} → 416 (Content-Range: bytes */{N})")
    x = PK.preview_file(hctx, pid3, vp)
    ok(x.status_code == 200 and x.headers["accept-ranges"] == "bytes" and x.headers["content-length"] == str(N) and "content-range" not in x.headers and type(x).__name__ == "StreamingResponse"
       and pbody(x) == VID and "media-src 'self'" in x.headers["content-security-policy"] and x.headers["access-control-allow-origin"] == "*", "Preview: Range'siz — 200, oqim bilan (StreamingResponse), CSP media-src 'self'")
    _orig_read = zipfile.ZipFile.read; _reads = []
    zipfile.ZipFile.read = lambda self, name, pwd=None: (_reads.append(name), _orig_read(self, name, pwd))[1]
    try: PK.preview_file(hctx, pid3, vp, "bytes=0-9"); PK.preview_file(hctx, pid3, "assets/audio/s2.mp3"); PK.preview_file(hctx, pid3, "index.html")
    finally: zipfile.ZipFile.read = _orig_read
    ok(_reads == [zn.getinfo("index.html")] or [getattr(n_, "filename", n_) for n_ in _reads] == ["index.html"], "Preview: media zip ichidan xotiraga o'qilmaydi (ZipFile.read chaqirilmaydi) — faqat kichik fayllar")
    x = PK.preview_file(hctx, pid3, "assets/video/video.uz.vtt", "bytes=0-5")
    ok(x.status_code == 200 and x.media_type.startswith("text/vtt") and x.body.decode() == VTT_OUT and x.headers["access-control-allow-origin"] == "*" and
       pbody(PK.preview_file(hctx, pid3, "assets/audio/s2.mp3", "bytes=3-9")) == MP3[3:10] and "access-control-allow-origin" not in PK.preview_file(hctx, pid3, "content.js").headers,
       "Preview: subtitr (text/vtt, siqilgan — to'liq), audio Range bilan; CORS sarlavhasi faqat media/subtitrda")
    # validate_zip — salbiy holatlar (v3)
    def tamper3(fn, cfn=None):
        ent = {n_: zn.read(n_) for n_ in zn.namelist()}
        if fn: fn(ent)
        if cfn:
            cc_ = json.loads(ent["content.json"]); cfn(cc_, {b["type"]: b for b in cc_["blocks"]}); ent["content.js"] = PK.content_js(cc_)
        return PK.validate_zip(PK.zip_bytes(ent))
    ok(tamper3(None)["ok"], "Validator: o'zgartirilmagan nusxa o'tadi")
    for path_, why in (("assets/video/video.mp4", "video fayl"), ("assets/video/video.ru.vtt", "subtitr"), ("assets/video/video.jpg", "poster"), ("assets/audio/s2.mp3", "slayd audiosi"),
                       ("assets/cover.jpg", "muqova"), ("assets/img/avatar.jpg", "o'qituvchi rasmi")):
        v = tamper3(lambda e, p_=path_: e.pop(p_))
        ok(not v["ok"] and any(f"fayl yo'q {path_}" in x_ for x_ in v["errors"]), f"Validator: {why} zip ichida yo'q — xato ({path_})")
    BADC = [(lambda c_, b: b["video"].update(provider="vimeo"), "provider noma'lum", "noma'lum video provider"), (lambda c_, b: b["video"].update(src="../video.mp4"), "video fayl yo'li", "video yo'li «..»"),
            (lambda c_, b: b["video"].update(src="https://evil.com/v.mp4"), "video fayl yo'li", "tashqi video havolasi"), (lambda c_, b: b["video"]["captions"][0].update(lang="O'zbek"), "subtitr", "subtitr til kodi"),
            (lambda c_, b: b["video"]["captions"][0].update(src="assets/video/x.srt"), "subtitr", "subtitr .vtt emas"), (lambda c_, b: b["slides"]["slides"][1].update(audio="assets/audio/yoq.mp3"), "yoq.mp3", "audio havolasi"),
            (lambda c_, b: c_.update(cover="assets/cover.jpg"), "cover", "cover obyekt emas"), (lambda c_, b: c_["cover"].update(image="assets/yoq.jpg"), "yoq.jpg", "cover.image"),
            (lambda c_, b: b["quiz"]["questions"][-1].update(pairs=P2[:1]), "(match)", "match — 1 juft"), (lambda c_, b: [x_ for x_ in b["quiz"]["questions"] if x_["type"] == "sort"][0].update(categories=[{"title": "A", "items": []}, {"title": "B", "items": ["x"]}]), "(sort)", "sort — bo'sh toifa"),
            (lambda c_, b: b["flashcards"].update(cards=[{"front": "x", "back": ""}]), "flashcards", "kartochka orqasi bo'sh"), (lambda c_, b: b["assignment"].update(questions=[]), "assignment", "topshiriq savolsiz"),
            (lambda c_, b: b["assignment"].update(avatar="assets/img/yoq.jpg"), "yoq.jpg", "avatar havolasi"), (lambda c_, b: b["flashcards"].update(type="hotspot3d"), "noma'lum blok turi", "noma'lum blok")]
    for cfn_, frag, why in BADC:
        v = tamper3(None, cfn_)
        ok(not v["ok"] and any(frag in x_ for x_ in v["errors"]), f"Validator: {why} — xato" + ("" if not v["ok"] else " (o'tib ketdi)"))
    saved_mp = PK.MAX_PACKAGE; PK.MAX_PACKAGE = 1024 * 1024
    try:
        v1 = PK.validate_zip(z3["none"]); v2 = tamper3(lambda e: (e.pop("assets/video/video.mp4"), e.__setitem__("assets/files/katta.pdf", VID)))
        ok(v1["ok"] and any("MB dan katta" in x_ for x_ in v2["errors"]), "Paket chegarasi: video fayl bor paket — ISFT_CORE_PK_PACKAGE_MB (500 MB), videosiz — eski chegara")
    finally: PK.MAX_PACKAGE = saved_mp
    saved_pm = PK.package_max; PK.package_max = lambda video=False: 1024 * 1024
    try: PK.build_topic(hctx, MID, L3, "none", force=True); ok(False, "chegaradan katta paket yig'ildi")
    except PK.HTTPException as e: ok(e.status_code == 413 and "oshadi" in e.detail and not list((PK.store() / "packages" / str(MID) / str(L3)).glob("*.tmp")), "Video bilan paket chegaradan oshsa — yig'ishdan oldin 413, vaqtinchalik fayl yo'q")
    finally: PK.package_max = saved_pm
    saved_sf = PK.STREAM_FROM; PK.STREAM_FROM = 256 * 1024       # kurs paketi: katta (siqilmagan) ichki fayl xotiraga o'qilmaydi — ZipMember orqali oqim bilan
    try:
        rc = PK.build_course(hctx, MID, "xapi")
        kz3 = zipfile.ZipFile(PK.store() / dst.execute("SELECT file FROM pk_packages WHERE id=?", (rc["package"]["id"],)).fetchone()[0])
        ok(rc["validation"]["ok"] and rc["validation"]["scos"] == 4 and kz3.read("t03/assets/video/video.mp4") == VID and kz3.getinfo("t03/assets/video/video.mp4").compress_type == zipfile.ZIP_STORED
           and json.loads(kz3.read("t03/content.json"))["cover"]["image"] == "assets/cover.jpg", "Kurs paketi: video faylli dars (t03) oqim bilan ko'chirildi, 4 ta SCO, validate_zip o'tdi")
    finally: PK.STREAM_FROM = saved_sf
    # haqiqiy pleyer bilan uchidan-uchigacha (brauzer: PW va CHROME berilganda)
    if (saved[0] / "index.html").is_file():
        PK.PLAYER_DIR = saved[0]
        integ = tmp / "integ"
        PK.upload_text(hctx, MID, 1, TASKDOC, None, "1-mavzu.docx")       # brauzerda rasm, jadval, adabiyotlar, xulosalar, topshiriq («Savollar») ham ko'rinsin
        PK.save_keypoints(hctx, MID, 1, ["Kompyuterlar turlarga bo'linadi.", "Bayt — 8 bit."], approve=True)
        PK.upload_slides(hctx, MID, 1, make_pdf(4), "taqdimot.pdf")       # .pptx (4 slayd) + PDF (4 bet) — galereya, sarlavhalar .pptx dan
        sl1 = next(b for b in PK.gather(MID, 1)["content"]["blocks"] if b["type"] == "slides")
        ok(sl1["display"] == "images" and sl1["slides"][0]["title"] == "Iqtisodiyot fani predmeti" and sl1["file"] == "assets/taqdimot.pptx",
           "Bir xil taqdimotning .pptx va PDF'i: PDF rasmlari + .pptx sarlavha/izohlari, .pptx yuklab olish uchun")
        # Rise 360 (v3): video fayl + subtitr + poster, muqova, mashqlar (moslashtirish, saralash, kartochkalar), slayd izohi va audiosi
        PK.upload_video(hctx, MID, 1, stream_up([VID])[0], "1-dars.mp4"); PK.upload_subs(hctx, MID, 1, SRT.encode(), "dars.srt", "uz")
        PK.upload_slot_image(hctx, "poster", MID, 1, png_bytes((10, 10, 60), (1280, 720)), "poster.png"); PK.upload_slot_image(hctx, "muqova", MID, 1, png_bytes((139, 0, 51), (1600, 900)), "muqova.png")
        PK.save_exercise(hctx, MID, 1, "match", {"stem": "Birliklarni moslang", "pairs": P2 + [{"left": "Megabayt", "right": "1024 kilobayt"}]})
        PK.save_exercise(hctx, MID, 1, "sort", {"categories": C2}); PK.save_exercise(hctx, MID, 1, "flashcards", {"title": "Atamalar", "cards": [{"front": "CPU", "back": "Markaziy protsessor"}, {"front": "RAM", "back": "Tezkor xotira"}]})
        PK.upload_slide_audio(hctx, MID, 1, 1, MP3, "1-slayd.mp3"); PK.set_slide_captions(hctx, MID, 1, {"1": "Kirish slaydi izohi"})
        t1 = [b["type"] for b in PK.gather(MID, 1)["content"]["blocks"]]
        ok(t1 == ["section", "video", "section", "plan", "text", "keypoints", "refs", "section", "slides", "file", "section", "flashcards", "quiz", "assignment", "reflect"], f"Brauzer sinovi uchun L1 — barcha v3 bloklari: {t1}")
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
    # ================= ko'rib chiqish topilmalari (regressiya) =================
    import hashlib, time as _time
    # (1) amaliy dars: matn manbasi faqat topshiriqlar ro'yxati — «matn bor», paket yig'iladi va «tayyor» bo'ladi; bo'sh matn bloki chiqmaydi
    ONLYQ = ["Talab egri chizig'ini chizing.", "Taklif jadvalini tuzing.", "Muvozanat narxini toping."]
    PK.upload_text(hctx, MID, A8, None, "Topshiriqlar\n" + "\n".join(f"{i}. {x_}" for i, x_ in enumerate(ONLYQ, 1)), "a8-topshiriq.txt")
    PK.set_topic_settings(hctx, MID, A8, {"blocks": {"slides": False, "video": False, "quiz": False, "files": False}})
    g8 = PK.gather(MID, A8); t8 = [b["type"] for b in g8["content"]["blocks"]]; r8 = g8["ready"]
    ok(r8["text"]["ok"] and r8["text"]["only_assignment"] and r8["complete"] and r8["missing"] == [] and r8["buildable"] and "text" not in t8 and t8.count("assignment") == 1
       and next(b for b in g8["content"]["blocks"] if b["type"] == "assignment")["questions"] == ONLYQ and r8["assignment"]["src"] == "matn",
       f"Faqat topshiriqlar ro'yxatidan iborat matn: tayyorgarlikda «matn bor», to'liq, yig'sa bo'ladi; bo'sh matn bloki yo'q ({t8})")
    fs_calls = []; _ofs = PK._file_sha; PK._file_sha = lambda p_: (fs_calls.append(Path(p_).name), _ofs(p_))[1]
    try: b8 = PK.build_topic(hctx, MID, A8, "xapi", force=True)
    finally: PK._file_sha = _ofs
    p8 = dict(dst.execute("SELECT * FROM pk_packages WHERE id=?", (b8["package"]["id"],)).fetchone())
    ok(b8["validation"]["ok"] and b8["package"]["status"] == "tayyor" and [b["type"] for b in json.loads(zipfile.ZipFile(PK.store() / p8["file"]).read("content.json"))["blocks"] if b["type"] != "section"] == ["assignment", "reflect"],
       f"…paket yig'ildi (400 emas), validate_zip o'tdi, holat «tayyor»{'' if b8['validation']['ok'] else b8['validation']['errors']}")
    ok(sum(1 for n_ in fs_calls if n_.startswith("build_")) == 1 and p8["sha256"] == _ofs(PK.store() / p8["file"]) and p8["size"] == (PK.store() / p8["file"]).stat().st_size
       and not list((PK.store() / p8["file"]).parent.glob("*.tmp")), "Tayyor zip bir marta (oqim bilan) xeshlanadi; hajm/sha256 fayl bilan mos; vaqtinchalik fayl qolmadi")
    # (5) qo'lda ro'yxat saqlangan (bo'sh ham) yoki blok o'chirilgan — matndagi «Topshiriqlar» ro'yxati matnda qoladi; faqat ishlatilganda matndan olinadi
    li8 = lambda g_: [x_ for x_ in ONLYQ if f"<li>{x_}</li>" in next((b["html"] for b in g_["content"]["blocks"] if b["type"] == "text"), "")]
    PK.set_assignment(hctx, MID, A8, ["Qo'lda savol?"]); gm = PK.gather(MID, A8)
    ok(li8(gm) == ONLYQ and next(b for b in gm["content"]["blocks"] if b["type"] == "assignment")["questions"] == ["Qo'lda savol?"] and gm["ready"]["assignment"]["found"] == 3
       and gm["ready"]["text"]["ok"] and not gm["ready"]["text"]["only_assignment"], "Qo'lda savollar saqlangan: matndagi ro'yxat ma'ruza matnida qoladi (topshiriqda — qo'lda kiritilgani); «matnda topildi: 3»")
    PK.set_assignment(hctx, MID, A8, []); ge = PK.gather(MID, A8)
    ok(li8(ge) == ONLYQ and all(b["type"] != "assignment" for b in ge["content"]["blocks"]) and ge["ready"]["text"]["ok"] and ge["ready"]["buildable"] and "Topshiriqlar" in PK.topic_view(hctx, MID, A8)["text_html"],
       "Bo'sh qo'lda ro'yxat (topshiriq bloki yo'q): «Topshiriqlar» ro'yxati yo'qolmaydi — ma'ruza matnida")
    PK.set_assignment(hctx, MID, A8, None)
    PK.set_topic_settings(hctx, MID, A8, {"blocks": {"slides": False, "video": False, "quiz": False, "files": False, "assignment": False}}); go_ = PK.gather(MID, A8)
    ok(li8(go_) == ONLYQ and all(b["type"] != "assignment" for b in go_["content"]["blocks"]), "Topshiriq bloki o'chirilgan: ro'yxat matnda qoladi")
    PK.set_topic_settings(hctx, MID, A8, {"blocks": {"slides": False, "video": False, "quiz": False, "files": False}}); ga = PK.gather(MID, A8)
    ok(li8(ga) == [] and next(b for b in ga["content"]["blocks"] if b["type"] == "assignment")["questions"] == ONLYQ and ga["ready"]["assignment"]["warnings"] == [], "Avtomatik rejim: ro'yxat matndan olinib topshiriq blokida ko'rsatiladi")
    # (4) chegaradan ortiq savollar — matnda qoladi, tayyorgarlik panelida ogohlantirish
    PK.upload_text(hctx, MID, A8, None, "Kirish matni shu yerda turadi.\n\nSavollar\n" + "\n".join(f"{i}. Savol {i}?" for i in range(1, 71)), "a8-kop.txt")
    gw = PK.gather(MID, A8); aw = gw["ready"]["assignment"]; hw = next(b["html"] for b in gw["content"]["blocks"] if b["type"] == "text")
    ok(aw["n"] == 60 and aw["max"] == 60 and len(aw["warnings"]) == 1 and "60 tadan ko'p" in aw["warnings"][0] and "10 tasi" in aw["warnings"][0] and "<li>Savol 61?</li>" in hw and "<li>Savol 70?</li>" in hw and "Savol 60?" not in hw,
       f"70 ta savol: 60 tasi topshiriqda, 10 tasi matnda qoladi, tayyorgarlikda ogohlantirish («{aw['warnings'][0][:50] if aw['warnings'] else ''}…»)")
    PK.set_assignment(hctx, MID, A8, ["Bitta savol?"])
    ok(PK.gather(MID, A8)["ready"]["assignment"]["warnings"] == [] and PK.gather(MID, A8)["ready"]["assignment"]["found"] == 60, "Qo'lda ro'yxat ishlatilganda matn bo'yicha ogohlantirish ko'rsatilmaydi")
    PK.set_assignment(hctx, MID, A8, None)
    # (3) yig'ish: manba fayllar xotiraga o'qilmaydi (Path — oqim bilan), natija avvalgi (xotirada o'qib yozish) bilan bir xil
    g3b = PK.gather(MID, L3); pf9 = PK.player_files()
    cont9 = {"v": 1, "id": "isft-test-rev", **{k: v for k, v in g3b["content"].items() if k != "v"}, "built": "2026-11-11T10:00:00"}
    src9 = {str(v.path if isinstance(v, PK.BigFile) else v) for v in g3b["files"].values() if not isinstance(v, (bytes, bytearray))}
    reads9 = []; _orb = Path.read_bytes; Path.read_bytes = lambda self: (reads9.append(str(self)), _orb(self))[1]
    try:
        fp9 = PK._fingerprint(g3b["content"], g3b["files"], "xapi", pf9)
        z9 = PK.build_zip(cont9, g3b["files"], "xapi", out_dir=tmp / "noread")
    finally: Path.read_bytes = _orb
    ok(isinstance(z9, Path) and len(src9) >= 6 and not (set(reads9) & src9), f"build_zip / _fingerprint: {len(src9)} ta manba fayl (video, audio, slaydlar, .pptx …) read_bytes bilan xotiraga o'qilmaydi")
    mem9 = {k: (v if isinstance(v, (bytes, bytearray, PK.BigFile)) else Path(v).read_bytes()) for k, v in g3b["files"].items()}
    h9 = hashlib.sha256(); h9.update(b"xapi"); h9.update(json.dumps(g3b["content"], sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for k in sorted(mem9): h9.update(k.encode()); h9.update((mem9[k].sha256 if isinstance(mem9[k], PK.BigFile) else PK._sha(mem9[k])).encode())
    for k in sorted(pf9): h9.update(k.encode()); h9.update(PK._sha(pf9[k]).encode())
    ok(fp9 == h9.hexdigest() and PK._file_sha(z9) == PK._sha(PK.build_zip(cont9, mem9, "xapi")) == PK._sha(PK.build_zip(cont9, g3b["files"], "xapi")),
       "Deterministiklik saqlandi: barmoq izi va zip sha256 — fayllar xotiraga o'qib yozilgandagi bilan bir xil")
    z9.unlink()
    # (3) paket chegarasi zip yozilishidan OLDIN tekshiriladi — 413 (o'zbekcha), hech narsa yozilmaydi
    saved_mp, _zw, zcalls = PK.package_max, PK.zip_write, []
    PK.zip_write = lambda *a, **kw: (zcalls.append(1), _zw(*a, **kw))[1]
    n_pk = dst.execute("SELECT COUNT(*) FROM pk_packages").fetchone()[0]
    try:
        PK.package_max = lambda video=False: 2000
        try: PK.build_topic(hctx, MID, 1, "xapi", force=True); ok(False, "chegaradan katta paket yig'ildi")
        except PK.HTTPException as e:
            ok(e.status_code == 413 and "MB dan oshadi" in e.detail and ("kamaytiring" in e.detail or "kichraytiring" in e.detail) and not zcalls and not list(PK._pkg_dir(MID, 1).glob("build_*.tmp"))
               and dst.execute("SELECT COUNT(*) FROM pk_packages").fetchone()[0] == n_pk, f"Paket chegarasi: zip yozilmasdan oldin 413 ({e.detail[:70]}…), vaqtinchalik fayl ham, paket yozuvi ham yo'q")
    finally:
        PK.package_max, PK.zip_write = saved_mp, _zw
    try: PK._size_guard({"index.html": b"x", "assets/video/video.mp4": PK.BigFile(tmp / "yoq.mp4", "0" * 64, PK.package_max(True) + 1)}); ok(False, "katta video o'tdi")
    except PK.HTTPException as e: ok(e.status_code == 413 and "videoni kichraytiring" in e.detail, "Paket chegarasi (video fayl bilan): 413 — «videoni kichraytiring…»")
    PK._size_guard({"content.json": PK.ZipMember(tmp / "yoq.zip", "content.json", PK.MAX_PACKAGE + 10), "assets/a.jpg": b"x" * 1000})
    ok(True, "_size_guard: siqiladigan (matnli) yozuvlar hajmi oldindan hisobga olinmaydi — yolg'on 413 yo'q (yakuniy hajmni validate_zip tekshiradi)")
    # (3) slayd audiolari: bitta dars bo'yicha jami chegara
    saved_at = PK.MAX_AUDIO_TOTAL; n_au = dst.execute("SELECT COUNT(*) FROM pk_assets WHERE purpose='audio' AND deleted=0").fetchone()[0]
    try:
        PK.MAX_AUDIO_TOTAL = len(MP3) * 2 - 1
        try: PK.upload_slide_audio(hctx, MID, L3, 3, MP3, "3-slayd.mp3"); ok(False, "audio jami chegarasi ishlamadi")
        except PK.HTTPException as e: ok(e.status_code == 413 and "jami" in e.detail and dst.execute("SELECT COUNT(*) FROM pk_assets WHERE purpose='audio' AND deleted=0").fetchone()[0] == n_au,
                                         f"Slayd audiolari jami chegarasi (MAX_AUDIO_TOTAL): 413 ({e.detail[:60]}…), fayl saqlanmadi")
        ok(PK.upload_slide_audio(hctx, MID, L3, 2, MP3, "2-slayd-yangi.mp3")["ok"] and 2 in PK._slide_audio(MID, L3), "…shu slaydning audiosini almashtirish mumkin (eski fayl hisobga kirmaydi)")
    finally:
        PK.MAX_AUDIO_TOTAL = saved_at
    ok(PK.MAX_AUDIO_TOTAL == 150 * 1024 * 1024, "MAX_AUDIO_TOTAL — 150 MB")
    # vaqtinchalik fayllar: 6 soatdan eski up_*.part / build_*.tmp o'chiriladi (init da)
    td_, pd_ = PK.store() / "tmp", PK._pkg_dir(MID, 1); td_.mkdir(parents=True, exist_ok=True)
    old_t = [td_ / "up_eski.part", pd_ / "build_eski.tmp", pd_ / "v99_xapi.zip.tmp"]; new_t = [td_ / "up_yangi.part", pd_ / "build_yangi.tmp"]
    for f_ in old_t + new_t: f_.write_bytes(b"x" * 10)
    for f_ in old_t: os.utime(f_, (_time.time() - 7 * 3600,) * 2)
    zips_ = sorted(x_.name for x_ in pd_.glob("*.zip"))
    n_sw = PK.sweep_tmp()
    ok(n_sw == 3 and not any(f_.exists() for f_ in old_t) and all(f_.exists() for f_ in new_t) and sorted(x_.name for x_ in pd_.glob("*.zip")) == zips_ and zips_ and PK.sweep_tmp() == 0,
       f"sweep_tmp: 6 soatdan eski up_*.part / build_*.tmp / *.zip.tmp o'chirildi ({n_sw} ta); yangilari va paketlar joyida")
    for f_ in new_t: f_.unlink()
    PK.init(dst)
    ok(True, "init(): sweep_tmp bilan — xatosiz")
    # kurs paketi: tayyor zip bir marta xeshlanadi (barmoq izi = sha256)
    fs_calls.clear(); PK._file_sha = lambda p_: (fs_calls.append(Path(p_).name), _ofs(p_))[1]
    try: rc9 = PK.build_course(hctx, MID, "scorm12")
    finally: PK._file_sha = _ofs
    pc9 = dst.execute("SELECT content_hash, sha256, file FROM pk_packages WHERE id=?", (rc9["package"]["id"],)).fetchone()
    ok(len(fs_calls) == 1 and fs_calls[0].startswith("build_") and pc9[0] == pc9[1] == _ofs(PK.store() / pc9[2]) and rc9["validation"]["ok"], "Kurs paketi: tayyor zip bir marta xeshlanadi (content_hash = sha256), fayl bilan mos")
    # (7) ilova UI (static/paket.js): slayd izohlari oynasi — audio yuklash/olib tashlash yozilgan izohlarni yo'qotmaydi
    pjs = (ROOT / "static" / "paket.js").read_text(encoding="utf-8")
    ok("PK.capDraft = {base, caps}" in pjs and "capVal(i + 1, s.caption)" in pjs and pjs.count("await reopen()") == 2 and 'bg.remove(); await pkTopicPanel(el); $("#pkSe")?.click()' not in pjs,
       "paket.js: audio yuklash/olib tashlashda yozilgan (saqlanmagan) izohlar yangi oynaga ko'chiriladi (PK.capDraft)")
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
    # Rise 360: video faylli dars — server orqali yig'ish, yuklab olish va ko'rishda HTTP Range (imzolangan yo'l)
    r = teach.post(f"{P}/courses/{C1}/topics/{R6}/build", json={"mode": "xapi"})
    ok(r.status_code == 200 and r.json()["package"]["valid"], f"HTTP: video faylli dars (L{R6}) yig'ildi ({r.status_code} {r.text[:160]})")
    if r.status_code == 200:
        p6 = r.json()["package"]
        d6 = teach.get(f"{P}/packages/{p6['id']}/download"); z6 = zipfile.ZipFile(io.BytesIO(d6.content)); c6 = json.loads(z6.read("content.json")); b6 = {b_["type"]: b_ for b_ in c6["blocks"]}
        ok(PK.validate_zip(d6.content)["ok"] and z6.read("assets/video/video.mp4") == MP4 and z6.getinfo("assets/video/video.mp4").compress_type == zipfile.ZIP_STORED
           and b6["video"]["provider"] == "file" and [c_["lang"] for c_ in b6["video"]["captions"]] == ["uz", "ru"] and all(c_["src"] in z6.namelist() for c_ in b6["video"]["captions"])
           and b6["video"]["poster"] in z6.namelist(), "HTTP paket: video (ZIP_STORED), subtitrlar va poster zip ichida")
        ok(c6["cover"] == {"image": "assets/cover.jpg", "author": teach_name} and "assets/cover.jpg" in z6.namelist() and b6["assignment"]["questions"] == TASK_Q and b6["assignment"]["avatar"] == "assets/img/avatar.jpg"
           and [x_["type"] for x_ in b6["quiz"]["questions"]][-2:] == ["match", "sort"] and b6["flashcards"]["title"] == "Atamalar" and b6["slides"]["slides"][0]["caption"] == "Birinchi slayd izohi"
           and b6["slides"]["slides"][0]["audio"] == "assets/audio/s1.ogg" and b6["slides"]["slides"][1]["audio"] == "assets/audio/s2.wav" and {"assets/audio/s1.ogg", "assets/audio/s2.wav"} <= set(z6.namelist()),
           "HTTP paket: muqova (kurs rasmi, muallif), topshiriq (Word'dagi savollar + o'qituvchi rasmi), mashqlar, slayd izohi/audiosi")
        loc6 = teach.get(f"{P}/packages/{p6['id']}/preview/index.html").headers.get("location", ""); vurl = loc6.rsplit("/", 1)[0] + "/assets/video/video.mp4"
        anon = httpx.Client(base_url=B, timeout=60); N6 = len(MP4)
        for rng_, a_, b_ in (("bytes=0-99", 0, 99), ("bytes=1000-", 1000, N6 - 1), ("bytes=-128", N6 - 128, N6 - 1)):
            x = anon.get(vurl, headers={"Range": rng_})
            ok(x.status_code == 206 and x.headers["content-range"] == f"bytes {a_}-{b_}/{N6}" and x.content == MP4[a_:b_ + 1] and x.headers["content-type"] == "video/mp4" and x.headers["accept-ranges"] == "bytes",
               f"HTTP preview Range {rng_!r} → 206 Content-Range bytes {a_}-{b_}/{N6}")
        x = anon.get(vurl, headers={"Range": f"bytes={N6}-"}); y = anon.get(vurl, headers={"Range": "bytes=9-3"}); w = anon.get(vurl)
        ok(x.status_code == 416 and x.headers["content-range"] == f"bytes */{N6}" and y.status_code == 416 and w.status_code == 200 and w.content == MP4 and w.headers["accept-ranges"] == "bytes"
           and "media-src 'self'" in w.headers["content-security-policy"] and "sandbox" in w.headers["content-security-policy"], "HTTP preview: qondirib bo'lmaydigan / noto'g'ri Range — 416; Range'siz — 200 (CSP media-src 'self', sandbox)")
        x = anon.get(loc6.rsplit("/", 1)[0] + "/assets/video/video.ru.vtt")
        ok(x.status_code == 200 and x.headers["content-type"].startswith("text/vtt") and "Привет, студенты!" in x.text and anon.get(vurl.replace(f"/{p6['id']}.", f"/{p6['id'] + 1}."), headers={"Range": "bytes=0-9"}).status_code == 403,
           "HTTP preview: subtitr text/vtt; soxta token bilan media — 403")
        anon.close()
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
quiz = {k for k in LES if srcof(k) in qz} | (pairs("SELECT course_id, topic_no FROM pk_exercises WHERE deleted=0 AND status='faol' AND kind IN ('match','sort')") & LES)
text = {k for k in LES if srcof(k) in tbs} | (pairs("SELECT course_id, topic_no FROM pk_assets WHERE purpose='matn' AND deleted=0") & LES)
ok(t["topics"] == len(LES) and t["courses"] == q("SELECT COUNT(*) n FROM dl_courses")[0]["n"] and t["by_kind"].get("amaliy", 0) >= 2,
   f"Jami darslar: {t['topics']} (L + qo'shilgan A/S/…: {t['by_kind']})")
ok(t["built"] == len(valid) and t["approved"] == len(appr), f"Yig'ilgan {t['built']} / tasdiqlangan {t['approved']} — SQL bilan bir xil")
ok(t["quiz"] == len(quiz) and t["text"] == len(text), f"Test {t['quiz']} / matn {t['text']} — SQL bilan bir xil")
exs_sql = pairs("SELECT course_id, topic_no FROM pk_exercises WHERE deleted=0 AND status='faol'") & LES
ok(t["exercises"] == len(exs_sql) > 0 and rek.get(P + "/coverage").json()["total"]["exercises"] == len(exs_sql), f"Mashqli darslar {t['exercises']} — SQL bilan bir xil; rektor faqat jamlangan sonni ko'radi")
ok(sum(d["topics"] for d in cv["departments"]) == t["topics"] and sum(d["built"] for d in cv["departments"]) == t["built"], "Kafedralar yig'indisi = jami")
ok(cv["teachers"] and sum(x["topics"] for x in cv["teachers"]) == t["topics"], "O'qituvchilar yig'indisi = jami")
ct = teach.get(P + "/coverage").json()
ok(ct["total"]["courses"] == q("SELECT COUNT(*) n FROM dl_courses WHERE teacher_id=?", (teach_tid,))[0]["n"] and ct["teachers"] == [], "O'qituvchi qamrovi — faqat o'z kurslari")
ck = kaf.get(P + "/coverage").json()
ok(ck["total"]["courses"] == q("SELECT COUNT(*) n FROM dl_courses WHERE department_id=?", (kaf_dept,))[0]["n"], "Kafedra qamrovi — faqat o'z kafedrasi")
cvv = teach.get(f"{P}/courses/{C1}").json()
t4 = next(x for x in cvv["topics"] if x["no"] == T)
ok(t4["text"] and t4["slides"] and t4["video"], "Kurs ko'rinishida mavzu tayyorgarligi (M/T/V)")

# =============================================================================================
print("== 10. «Dars tayyorlash»: dars nomi, bitta yuklash nuqtasi, yuborish, monitoring, eskirgan versiya, navbat")
# (a) nom Word/matn sarlavhasidan — sof funksiya
for txt_, want_ in [("3-MAVZU: RAQAMLI IQTISODIYOT ASOSLARI\nReja:\n1. a", "RAQAMLI IQTISODIYOT ASOSLARI"), ("Mavzu: Pul nazariyasi\nMatn", "Pul nazariyasi"),
                    ("# 2-ma'ruza. Talab va taklif", "Talab va taklif"), ("Kirish\n\nMAVZU 5:\nBozor muvozanati\nReja", "Bozor muvozanati"),
                    ("Reja:\n1. Mavzu tanlash", ""), ("1-AMALIY MASHG'ULOT: Excel", "Excel"), ("Oddiy matn. Mavzu: bu yerda emas " * 3, "")]:
    ok(PK.doc_title(txt_) == want_, f"doc_title: {txt_[:34]!r} → {want_!r}")
N1, N2 = 12, 13
U = f"{P}/courses/{C1}/topics/{N1}"
syl = q("SELECT MAX(topic) t FROM dl_items WHERE course_id=? AND topic_no=?", (C1, N1))[0]["t"] or ""
v0 = teach.get(U).json()
ok(v0["topic"]["title"] != f"L{N1}" and (v0["lesson"]["untitled"] and v0["topic"]["title"] == f"{N1}-mavzu" or v0["topic"]["title"]) and v0["state"] == "bosh",
   f"Nomi yo'q dars: «{v0['topic']['title']}» (dars kodi nom o'rnida takrorlanmaydi), holat — Bo'sh")
ok(v0["ready"]["plan"]["heading"] in (f"{N1}-MAVZU", f"{N1}-MAVZU: {v0['topic']['title'].upper()}") and "L12" not in v0["ready"]["plan"]["heading"], "Reja sarlavhasi: «12-MAVZU» (kod / nom takrorisiz)")
# (b) bitta yuklash nuqtasi: tur tarkibidan aniqlanadi
BODY = ("12-MAVZU: PUL NAZARIYASI ASOSLARI\nReja:\n1. Pul tushunchasi\n2. Pul funksiyalari\n\n1. Pul tushunchasi\n" + "Pul — umumiy ekvivalent vazifasini bajaruvchi maxsus tovar. " * 8 +
        "\n2. Pul funksiyalari\n" + "Pul qiymat o'lchovi, muomala va to'lov vositasi hisoblanadi. " * 8)
r = teach.post(U + "/upload", params={"name": "maruza12.txt"}, content=BODY.encode("utf-8"))
ok(r.status_code == 200 and r.json()["as"] == "matn" and r.json()["title_set"] and r.json()["title"] == "PUL NAZARIYASI ASOSLARI" and len(r.json()["plan"]) >= 2,
   f"/upload: .txt → ma'ruza matni; nom sarlavhadan avtomatik ({r.status_code} {r.text[:120]})")
v1 = teach.get(U).json()
ok(v1["topic"]["title"] == "PUL NAZARIYASI ASOSLARI" and v1["lesson"]["title_src"] == "word" and not v1["lesson"]["untitled"] and v1["ready"]["plan"]["heading"] == "12-MAVZU: PUL NAZARIYASI ASOSLARI",
   "Dars nomi yuklangan matn sarlavhasidan olindi (title_src=word)")
ok(next(x for x in teach.get(f"{P}/courses/{C1}").json()["topics"] if x["no"] == N1)["title"] == "PUL NAZARIYASI ASOSLARI", "Darslar ro'yxatida ham haqiqiy nom")
tbs_ = teach.get(f"/api/testbank/courses/{C1}/topics/{N1}/source").json()["source"]
ok(tbs_ and tbs_["origin"] == "paket" and "umumiy ekvivalent" in tbs_["text"] and "[RASM" not in tbs_["text"], "Test bank shu yerda yuklangan ma'ruza matnini ko'radi (bitta yuklash)")
tbt_ = next(x for x in teach.get(f"/api/testbank/courses/{C1}").json()["topics"] if x["no"] == N1)
ok(tbt_["label"] == "PUL NAZARIYASI ASOSLARI" and tbt_["source"] and tbt_["source"]["origin"] == "paket", "Test bankda mavzu nomi va matn manbai — bir xil")
r = teach.post(U + "/title", json={"title": "  Pul   nazariyasi (qo'lda) "})
ok(r.status_code == 200 and r.json()["lesson"]["title"] == "Pul nazariyasi (qo'lda)" and r.json()["lesson"]["title_src"] == "qolda", "Qo'lda kiritilgan nom ustun")
ok(teach.post(U + "/title", json={"title": ""}).json()["lesson"]["title"] == "PUL NAZARIYASI ASOSLARI", "Bo'sh nom — avtomatik nomga (Word sarlavhasi) qaytadi")
ok(kaf8.post(U + "/title", json={"title": "x"}).status_code == 403 and rek.post(U + "/title", json={"title": "x"}).status_code == 403, "Nomni kafedra / rektor o'zgartira olmaydi (403)")
from PIL import Image as _Im
def _img(fmt, size=(800, 450), color=(20, 60, 120)):
    b_ = io.BytesIO(); _Im.new("RGB", size, color).save(b_, fmt); return b_.getvalue()
PDF2 = io.BytesIO(); _Im.new("RGB", (800, 450), (200, 30, 30)).save(PDF2, "PDF", save_all=True, append_images=[_Im.new("RGB", (800, 450), (30, 200, 30))]); PDF2 = PDF2.getvalue()
r = teach.post(U + "/upload", params={"name": "slaydlar.docx"}, content=PDF2)       # kengaytma yolg'on — tarkib PDF
ok(r.status_code == 200 and r.json()["as"] == "taqdimot" and r.json()["kind"] == "pdf" and r.json()["count"] == 2, f"/upload: PDF → taqdimot (kengaytmaga emas, tarkibga qaraladi) ({r.status_code} {r.text[:100]})")
r = teach.post(U + "/upload", params={"name": "rasm.png"}, content=_img("PNG"))
ok(r.status_code == 409 and r.json()["detail"]["ambiguous"] and set(r.json()["detail"]["choices"]) >= {"muqova", "rasm", "slayd"}, "/upload: rasm — noaniq (409 + tanlovlar: muqova / matn rasmi / slayd)")
r = teach.post(U + "/upload", params={"name": "rasm.png", "as": "muqova"}, content=_img("PNG"))
ok(r.status_code == 200 and r.json()["as"] == "muqova" and teach.get(U).json()["ready"]["cover"]["src"] == "dars", "/upload?as=muqova: rasm → dars muqovasi")
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41" + b"\x00" * 4096
r = teach.post(U + "/upload", params={"name": "dars.bin"}, content=MP4)
ok(r.status_code == 200 and r.json()["as"] == "video" and r.json()["kind"] == "mp4" and teach.get(U).json()["ready"]["video"]["provider"] == "file", "/upload: mp4 (ftyp) → video fayl")
r = teach.post(U + "/upload", params={"name": "dars.srt"}, content="1\n00:00:01,000 --> 00:00:03,000\nSalom\n".encode())
ok(r.status_code == 200 and r.json()["as"] == "subs" and r.json()["cues"] == 1, "/upload: .srt → subtitr")
r = teach.post(U + "/upload", params={"name": "virus.docx"}, content=b"MZ\x90\x00\x03" + os.urandom(600))
ok(r.status_code == 415 and "qabul qilinmaydi" in r.json()["detail"] and "Word" in r.json()["detail"], "/upload: noma'lum tur — 415, o'zbekcha tushunarli xabar")
ok(teach.post(U + "/upload", params={"name": "eski.doc"}, content=b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600).status_code == 415, "/upload: eski .doc/.ppt — 415")
ok(teach.post(U + "/upload", params={"name": "a.mp3"}, content=b"ID3\x03\x00\x00" + b"\x00" * 600).status_code == 415, "/upload: audio — 415 (slayd audiosi alohida joyda)")
ok(teach.post(U + "/upload", params={"name": "x.pdf", "as": "video"}, content=PDF2).status_code == 415 and teach.post(U + "/upload", params={"name": "x.pdf", "as": "zzz"}, content=PDF2).status_code == 400,
   "/upload: maqsadga mos bo'lmagan tur — 415; noma'lum maqsad — 400")
ok(teach.post(U + "/upload", params={"name": "bosh.txt"}, content=b"").status_code == 400, "/upload: bo'sh fayl — 400")
def _big(n):
    yield b"%PDF-1.4\n" + b"0" * 55
    for _ in range(n // (1024 * 1024)): yield b"0" * (1024 * 1024)
r = teach.post(U + "/upload", params={"name": "katta.pdf"}, content=_big(PK.MAX_ASSET + 2 * 1024 * 1024))
ok(r.status_code == 413 and "50 MB" in r.json()["detail"] and not list((DBP.parent / "paket" / "tmp").glob("up_*.part")),
   "/upload: video bo'lmagan fayl uchun chegara o'zgarmagan (50 MB) — 413, vaqtinchalik fayl qolmaydi")
ok(kaf8.post(U + "/upload", params={"name": "a.txt"}, content=BODY.encode()).status_code == 403 and rek.post(U + "/upload", params={"name": "a.txt"}, content=BODY.encode()).status_code == 403
   and teach.post(f"{P}/courses/{mikro['id']}/topics/1/upload", params={"name": "a.txt"}, content=BODY.encode()).status_code == 403, "/upload: kafedra, rektor va begona kurs — 403")
# (c) Tayyorlash: asosiy uch qism bor (test ixtiyoriy) → bo'limga yuboriladi
if SERVER_PLAYER:
    mon0 = {r_["kind"]: r_ for r_ in q("SELECT * FROM dl_items WHERE course_id=? AND topic_no=?", (C1, N1))}
    vr = teach.get(U).json()["ready"]
    ok(vr["sendable"] and vr["core_missing"] == [] and (vr["complete"] or vr["missing"] == ["quiz"]), "Matn + taqdimot + video bor: yuborishga tayyor (test — ixtiyoriy)")
    b1 = teach.post(U + "/build", json={}).json()
    ok(b1["ok"] and b1["package"]["status"] == "tayyor" and b1["package"]["version"] == 1, "Tayyorlash → v1, holat «tasdiq kutilmoqda» (testsiz ham)")
    z1 = zipfile.ZipFile(io.BytesIO(teach.get(f"{P}/packages/{b1['package']['id']}/download").content))
    tc = z1.read("tincan.xml").decode() if "tincan.xml" in z1.namelist() else ""
    cj1 = json.loads(z1.read("content.json"))
    ok("index.html" in z1.namelist() and "<name lang=\"uz\">PUL NAZARIYASI ASOSLARI</name>" in tc and cj1["title"] == "PUL NAZARIYASI ASOSLARI" and cj1["lesson"]["code"] == "L12",
       "Zip: index.html + tincan.xml; <name> — haqiqiy dars nomi (kod emas)")
    v2 = teach.get(U).json()
    ok(v2["state"] == "kutilmoqda" and not v2["stale"] and not v2["changed"] and v2["nextid"] is None, "Dars holati: Tasdiq kutilmoqda; NEXTID versiyasi hali yo'q")
    rows_ = head.get(f"{P}/courses", params={"only": "waiting", "limit": 400}).json()["items"]
    row_ = next(x for x in rows_ if x["id"] == C1)
    wl = sorted(x["no"] for x in head.get(f"{P}/courses/{C1}").json()["topics"] if x["state"] == "kutilmoqda")
    ok(row_["waiting_no"] == wl[0] and N1 in wl, f"Kurslar ro'yxati: «Ochish» tasdiq kutayotgan darsni ochadi (waiting_no={row_['waiting_no']}, L1 emas)")
    qu = head.get(P + "/queue").json()
    ok(any(x["kind"] == "kutilmoqda" and x["course_id"] == C1 and x["no"] == N1 and x["title"] == "PUL NAZARIYASI ASOSLARI" for x in qu["items"]) and qu["waiting"] >= 1,
       "Bo'lim navbati: tasdiq kutayotgan dars nomi bilan")
    ok(rek.get(P + "/queue").status_code == 403 and all(x["course_id"] in {c_["id"] for c_ in q("SELECT id FROM dl_courses WHERE teacher_id=?", (teach_tid,))} for x in teach.get(P + "/queue").json()["items"]),
       "Navbat: rektor — 403; o'qituvchi — faqat o'z kurslari")
    ok(teach.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "approve"}).status_code == 403, "O'qituvchi tasdiqlay olmaydi (403)")
    # (d) qaytarilganda monitoring o'zgarmaydi
    head.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "reject", "note": "Sinov: qaytarish"})
    mon1 = {r_["kind"]: r_ for r_ in q("SELECT * FROM dl_items WHERE course_id=? AND topic_no=?", (C1, N1))}
    ok(all(mon1[k_]["status"] == mon0[k_]["status"] and mon1[k_]["src"] == mon0[k_]["src"] for k_ in mon0), "Qaytarilgan paket monitoringni o'zgartirmaydi")
    ok(teach.get(U).json()["state"] == "tayyorlanmoqda" and next(x for x in teach.get(f"{P}/courses/{C1}").json()["topics"] if x["no"] == N1)["returned"], "Qaytarilgan dars: «Tayyorlanmoqda» + qaytarilgan belgisi")
    # qaytarilgan dars o'zgarishsiz qayta yuborilmaydi: na shu versiyani «submit», na majburiy qayta yig'ish (force) bilan
    r = teach.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "submit"})
    ok(r.status_code == 409 and "o'zgartirilmagan" in r.json()["detail"] and "Sinov: qaytarish" in r.json()["detail"]
       and q("SELECT status FROM pk_packages WHERE id=?", (b1['package']['id'],))[0]["status"] == "qoralama",
       f"Qaytarilgan dars o'zgarishsiz qayta yuborilmaydi — 409, sababi bilan ({r.status_code})")
    bf = teach.post(U + "/build", json={"force": True}).json()
    ok(bf["package"]["status"] == "qoralama" and teach.post(f"{P}/packages/{bf['package']['id']}/action", json={"action": "submit"}).status_code == 409,
       "Majburiy qayta yig'ish (o'sha mazmun) — avtomatik yuborilmaydi, «submit» ham 409")
    ok(kaf8.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "submit"}).status_code == 403, "Kafedra yubora olmaydi (403)")
    teach.post(U + "/upload", params={"name": "maruza12.txt"}, content=(BODY + "\nTuzatildi: bo'lim izohiga ko'ra misol qo'shildi.").encode("utf-8"))
    b1 = teach.post(U + "/build", json={}).json()
    if b1["package"]["status"] != "tayyor":
        b1["package"] = teach.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "submit"}).json()["package"]
    ok(b1["package"]["status"] == "tayyor" and b1["package"]["version"] == 3, f"Material tuzatildi → qayta tayyorlandi (v{b1['package']['version']}), bo'limga yuborildi")
    # (e) tasdiqlash → monitoringdagi shu mavzuning paketda BOR materiallari yopiladi
    logs0 = q("SELECT COUNT(*) n FROM dl_log WHERE item_id IN (SELECT id FROM dl_items WHERE course_id=? AND topic_no=?)", (C1, N1))[0]["n"]
    ra = head.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "approve"}).json()
    mon2 = {r_["kind"]: r_ for r_ in q("SELECT * FROM dl_items WHERE course_id=? AND topic_no=?", (C1, N1))}
    open0 = [k_ for k_ in ("maruza", "taqdimot", "video") if mon0[k_]["status"] != "tasdiqlandi"]
    ok(ra["ok"] and ra["monitoring"] == len(open0) and all(mon2[k_]["status"] == "tasdiqlandi" for k_ in ("maruza", "taqdimot", "video"))
       and all(mon2[k_]["src"] == "paket" and mon2[k_]["checked_at"] and mon2[k_]["uploaded_at"] for k_ in open0),
       f"Tasdiqlandi → monitoringda ma'ruza, taqdimot, video yopildi (src=paket): {len(open0)} ta")
    ok(mon2["test"]["status"] == mon0["test"]["status"] or vr["quiz"]["ok"], "Paketda test yo'q — monitoringdagi «test» o'zgarmadi")
    lg_ = q("SELECT l.action, l.note FROM dl_log l JOIN dl_items i ON i.id=l.item_id WHERE i.course_id=? AND i.topic_no=? ORDER BY l.id DESC LIMIT 1", (C1, N1))
    logs1 = q("SELECT COUNT(*) n FROM dl_log WHERE item_id IN (SELECT id FROM dl_items WHERE course_id=? AND topic_no=?)", (C1, N1))[0]["n"]
    ok(logs1 - logs0 == len(open0) and (not open0 or (lg_[0]["action"] == "tasdiqlandi" and "L12 v3" in lg_[0]["note"])), "Monitoring tarixida yozuv: «Dars tayyorlash: L12 v3 tasdiqlandi»")
    mine_ = teach.get("/api/masofaviy/items", params={"due": "overdue", "limit": 300}).json()["items"]
    ok(not any(x["topic_no"] == N1 and x["kind"] in ("maruza", "taqdimot", "video") and x["subject"] == own["subject"] and x["direction"] == own["direction"] for x in mine_),
       "O'qituvchining «muddati o'tgan» ro'yxatida bu materiallar yo'q")
    v3 = teach.get(U).json()
    ok(v3["state"] == "tasdiqlangan" and v3["nextid"]["version"] == 3 and not v3["stale"], "Dars: Tasdiqlangan; «NEXTID uchun: v3»")
    # (f) tasdiqdan keyin manba o'zgardi → «eskirgan»
    teach.post(U + "/upload", params={"name": "maruza12b.txt"}, content=(BODY + "\nQo'shimcha xatboshi: pul massasi va inflyatsiya o'zaro bog'liq. " * 3).encode("utf-8"))
    v4 = teach.get(U).json()
    ok(v4["stale"] and v4["changed"] and v4["nextid"]["version"] == 3 and next(x for x in teach.get(f"{P}/courses/{C1}").json()["topics"] if x["no"] == N1)["stale"],
       "Tasdiqdan keyin fayl almashtirildi → «Tasdiqlangan versiya eskirgan» (dars va ro'yxatda)")
    ok(any(x["kind"] == "eskirgan" and x["course_id"] == C1 and x["no"] == N1 for x in head.get(P + "/queue").json()["items"])
       and any(x["kind"] == "eskirgan" and x["no"] == N1 for x in teach.get(P + "/queue").json()["items"]), "Eskirgan dars bo'lim navbatida va o'qituvchida ko'rinadi")
    b2 = teach.post(U + "/build", json={}).json()
    v5 = teach.get(U).json()
    ok(b2["package"]["version"] == 4 and v5["state"] == "kutilmoqda" and not v5["stale"] and not v5["changed"] and v5["nextid"]["version"] == 3,
       "Qayta tayyorlandi: v4 tasdiq kutmoqda, eskirgan belgisi yo'q, NEXTID uchun hozircha v3")
    # (g) tasdiqlangan versiya qaytarilsa — paket orqali yopilgan materiallar qaytadi
    rr = head.post(f"{P}/packages/{b1['package']['id']}/action", json={"action": "reject", "note": "Sinov: tasdiq bekor"}).json()
    mon3 = {r_["kind"]: r_ for r_ in q("SELECT * FROM dl_items WHERE course_id=? AND topic_no=?", (C1, N1))}
    ok(rr["monitoring"] == len(open0) and all(mon3[k_]["status"] == "qaytarildi" for k_ in open0), "Tasdiqlangan paket qaytarildi → paket orqali yopilgan materiallar «qaytarildi»")
    head.post(f"{P}/packages/{b2['package']['id']}/action", json={"action": "approve"})
    ok(all(r_["status"] == "tasdiqlandi" for r_ in q("SELECT status FROM dl_items WHERE course_id=? AND topic_no=? AND kind IN ('maruza','taqdimot','video')", (C1, N1))), "v4 tasdiqlandi → materiallar yana yopildi")
    # (h) to'liq bo'lmagan dars: qoralama → o'qituvchi «shu holicha yuborish»
    U2 = f"{P}/courses/{C1}/topics/{N2}"
    teach.post(U2 + "/upload", params={"name": "m13.txt"}, content=BODY.replace("12-MAVZU", "13-MAVZU").encode("utf-8"))
    b3 = teach.post(U2 + "/build", json={}).json()
    v6 = teach.get(U2).json()
    ok(b3["package"]["status"] == "qoralama" and set(v6["ready"]["core_missing"]) == {"slides", "video"} and v6["state"] == "tayyorlanmoqda", "Faqat matn: qoralama (yetishmaydi: taqdimot, video) — bo'limga o'zi ketmaydi")
    ok(head.post(f"{P}/packages/{b3['package']['id']}/action", json={"action": "approve"}).status_code == 409, "Yuborilmagan darsni tasdiqlab bo'lmaydi (409)")
    ok(teach.post(f"{P}/packages/{b3['package']['id']}/action", json={"action": "submit"}).json()["package"]["status"] == "tayyor", "«Shu holicha yuborish» → tasdiq kutilmoqda")
    head.post(f"{P}/packages/{b3['package']['id']}/action", json={"action": "approve"})
    m13 = {r_["kind"]: r_["status"] for r_ in q("SELECT kind, status FROM dl_items WHERE course_id=? AND topic_no=?", (C1, N2))}
    ok(m13["maruza"] == "tasdiqlandi" and all(m13[k_] != "tasdiqlandi" or q("SELECT src FROM dl_items WHERE course_id=? AND topic_no=? AND kind=?", (C1, N2, k_))[0]["src"] != "paket" for k_ in ("taqdimot", "video", "test")),
       "Monitoring: faqat paketda bor qism (ma'ruza) yopildi — taqdimot/video/test paket orqali yopilmadi")
# (i) UI matni: texnik atamalar o'qituvchiga ko'rinmaydi
pjs2 = (ROOT / "static" / "paket.js").read_text(encoding="utf-8")
body_ = re.sub(r"/\*.*?\*/", "", pjs2, flags=re.S)
ok(not re.search(r"postMessage|\bLRS\b|\bSCO\b|WebVTT|\[RASM|manifest|pleyer|ANTHROPIC|Paketni yig'ish|Avtomatik joylash|Ommaviy yig'ish", body_) and "Tayyorlash" in pjs2 and "Kengaytirilgan sozlamalar" in pjs2
   and 'id="pkAny"' in pjs2 and "Yuklab olish (.zip)" in pjs2, "paket.js: texnik atamalarsiz; bitta yuklash maydoni, «Tayyorlash», «Kengaytirilgan sozlamalar»")

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi:"); [print("  -", f) for f in fails]; sys.exit(1)
print("Hammasi o'tdi ✓")
