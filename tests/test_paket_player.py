"""O'quv paket pleyeri (app/paket_player) — statik tekshiruvlar + (ixtiyoriy) brauzerdagi muvofiqlik sinovi.

Ishga tushirish:  .venv/bin/python tests/test_paket_player.py
   (yoki: python tests/run_all.py --only paket_player — server kerak emas, ISFT_TEST_URL e'tiborsiz qoldiriladi)
Brauzer sinovi (SCORM 1.2 / SCORM 2004 / xAPI / NEXTID-mustaqil / ko'rish rejimi, qadamlar, kontrakt v3 bloklari — muqova, fayl-video,
match/sort, kartochkalar, topshiriq — 390px, qorong'i rejim) faqat PW va CHROME berilganda:
   PW=/path/node_modules/playwright-core CHROME=/path/to/chrome .venv/bin/python tests/test_paket_player.py
   (skrinshotlar: OUT muhit o'zgaruvchisi; tools/paket_player_check.js ga qarang)
"""
import json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PL = ROOT / "app" / "paket_player"
FX = ROOT / "tests" / "fixtures" / "paket_sample"
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)

# =============================================================================================
print("== 1. Pleyer fayllari va hajm")
files = [p for p in PL.rglob("*") if p.is_file() and p.name != ".DS_Store"]
names = {str(p.relative_to(PL)) for p in files}
ok({"index.html", "player.js", "player.css", "lms.js"} <= names, "index.html, player.js, player.css, lms.js (LMS adapterlari — kurs pleyeri bilan umumiy) mavjud")
size = sum(p.stat().st_size for p in files)
ok(size <= 560 * 1024, f"Pleyer hajmi {size / 1024:.1f} KB ≤ 560 KB (Manrope + Lato + Merriweather shriftlari bilan)")
ok(all(p.suffix in {".html", ".js", ".css", ".woff2"} or p.name == "OFL.txt" for p in files), "Faqat html/js/css/woff2 fayllar (+ shrift litsenziyasi OFL.txt): " + ", ".join(sorted(names)))

html = (PL / "index.html").read_text(encoding="utf-8")
pjs = (PL / "player.js").read_text(encoding="utf-8")
ljs = (PL / "lms.js").read_text(encoding="utf-8")
js = pjs + "\n" + ljs          # standartlar kalit so'zlari — ikkala faylda (adapterlar lms.js da)
css = (PL / "player.css").read_text(encoding="utf-8") + "".join(p.read_text(encoding="utf-8") for p in PL.rglob("*.css") if p.name != "player.css")
srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', html)
ok(srcs == ["content.js", "lms.js", "a11y.js", "player.js"], f"index.html: content.js, lms.js (LMS adapterlari), a11y.js (imlo normallashtiruvchisi), keyin player.js ({srcs})")
ajs = (PL / "a11y.js").read_text(encoding="utf-8")
ok("speechSynthesis" not in ajs and "localStorage" not in ajs and "a11y-b" not in ajs and "panel" not in ajs.split("*/", 1)[1] and not re.search(r"https?://", ajs.split("*/", 1)[1]), "a11y.js: ovozli o'qish (Tinglash) va «Aa» qulaylik paneli olib tashlangan; localStorage yo'q, tashqi manzilsiz")
ok("\\u02bb" in ajs and "MutationObserver" in ajs and all(t in ajs for t in ("SCRIPT", "TEXTAREA", "CODE", "PRE", "MATH")) and "uz: uz" in ajs,
   "a11y.js: oʻ/gʻ (U+02BB) ko'rinish normallashtiruvchisi — MutationObserver, script/style/textarea/code/pre/MathML chiqarib tashlangan")
ok("Nimalar qoldi?" in pjs and "'aria-controls': 'r-left'" in pjs and "'aria-expanded': 'false'" in pjs and "e.key === 'Escape' && !R.left.hidden" in pjs and "ta qadam qoldi" in pjs,
   "player.js: pastki tasma — qisqa holat («N ta qadam qoldi»), «Nimalar qoldi?» (aria-expanded, Esc)")
_fcss = (PL / "fonts" / "fonts.css").read_text(encoding="utf-8")
ok(re.search(r'font-family:"ISFT Uz"[^}]*merriweather-latin\.woff2[^}]*unicode-range:U\+02BB-02BC', _fcss) and '"ISFT Uz"' in css and (PL / "fonts" / "merriweather-latin.woff2").is_file(),
   "fonts.css: ʻ (U+02BB) uchun «ISFT Uz» shrifti (Merriweather glifi), shrift ro'yxatida Lato / Manrope'dan keyin")
try:
    from fontTools.ttLib import TTFont
    ok(0x2BB in TTFont(str(PL / "fonts" / "merriweather-latin.woff2")).getBestCmap(), "merriweather-latin.woff2 da U+02BB glifi bor")
except ImportError:
    pass
ok(".r-left" in css and ".r-what" in css and ".a11y-b" not in css and ".r-a11y" not in css and "R.a11y" not in pjs, "player.css: «Nimalar qoldi?» oynasi; «Aa» tugmasi (CSS va kod) olib tashlangan")
ok('href="player.css"' in html and '<meta name="viewport"' in html and 'lang="uz"' in html, "index.html: player.css, viewport, lang=uz")
ok(not re.search(r'(src|href)="(/|[a-z]+:)', html), "index.html: faqat nisbiy manzillar")

print("== 2. Xavfsizlik va tashqi resurslar")
ALLOWED = re.compile(r"^https?://(www\.)?(youtube-nocookie\.com|youtube\.com|youtu\.be)(/|$)|^http://adlnet\.gov/expapi/|^https://w3id\.org/xapi/|^http://id\.tincanapi\.com/extension/|^http://www\.w3\.org/1998/Math/MathML$")   # w3id / tincanapi — kengaytma IRI, MathML — nomlar fazosi (identifikator, so'rov emas)
urls = re.findall(r"https?://[^\s'\"()<>]+", js + css + html)
bad = [u for u in urls if not ALLOWED.match(u)]
ok(not bad, f"Tashqi URL lar faqat YouTube, ADL / cmi5 / TinCan xAPI IRI va MathML nomlar fazosi ({len(urls)} ta topildi){': ' + ', '.join(bad[:5]) if bad else ''}")
ok(not re.search(r"\beval\s*\(|new\s+Function\s*\(|setTimeout\s*\(\s*['\"]|document\.write", js), "eval / new Function / satrli setTimeout / document.write yo'q")
ok(not re.search(r"@import|url\((['\"]?)(https?:|//)", css), "CSS da tashqi @import/url yo'q")
inner = re.findall(r"\.innerHTML\s*=\s*([^;]+)", js)
ok(not re.search(r"innerHTML|eval\s*\(|new\s+Function", ljs), "lms.js: innerHTML / eval yo'q")
ok(len(inner) == 1 and inner[0].strip().startswith("'<svg '"), f"innerHTML bitta joyda — staticSvg() ({len(inner)} joy)")
svg_args = re.findall(r"staticSvg\('[^']*', '[^']*', ([^)]+?)\)", js)
ok(len(svg_args) >= 2 and all(x.strip() in ("ICONS[name] || ''", "AVATAR") for x in svg_args) and js.count("staticSvg(") == len(svg_args) + 1,
   f"staticSvg() faqat statik ICONS / AVATAR bilan chaqiriladi ({svg_args})")
ok("DOMParser" in js and "noopener" in js, "Kontent HTML DOMParser + oq ro'yxat sanitizeri orqali, havolalar rel=noopener")
glb = set(re.findall(r"\bW\.([A-Za-z_$][\w$]*)\s*=(?!=)", pjs))
ok(glb == {"ISFTPaket"}, f"player.js: global obyekt faqat window.ISFTPaket ({sorted(glb)})")
lglb = set(re.findall(r"\bW\.([A-Za-z_$][\w$]*)\s*=(?!=)", ljs))
ok(lglb == {"ISFTLms"} and ljs.lstrip().startswith("/*") and "'use strict'" in ljs[:3000], f"lms.js: IIFE + 'use strict', global faqat window.ISFTLms ({sorted(lglb)})")
ok("LMS.setLog(note)" in pjs and "W.ISFTLms" in pjs and "Pleyer fayli yetishmaydi" in pjs, "player.js adapterlarni window.ISFTLms dan oladi (lms.js yo'q bo'lsa — aniq xato)")
ok("opts.unit" in ljs and "'block'" in ljs and "opts.prefix" in ljs, "xAPI ichki faoliyat yo'li sozlanadi (paket — /block/, kurs — /lesson/), Preview kaliti prefiksi")
ok(js.lstrip().startswith("/*") and "'use strict'" in js[:4000], "IIFE + 'use strict'")

print("== 3. Standartlar (kalit elementlar)")
for k in ["cmi.core.lesson_status", "cmi.core.score.raw", "cmi.core.session_time", "cmi.core.exit", "cmi.suspend_data", "cmi.core.lesson_location",
          "LMSInitialize", "LMSCommit", "LMSFinish", "LMSGetLastError", "cmi.interactions."]:
    ok(k in js, f"SCORM 1.2: {k}")
for k in ["API_1484_11", "cmi.completion_status", "cmi.success_status", "cmi.score.scaled", "cmi.progress_measure", "cmi.location", "cmi.session_time",
          "Terminate", "learner_response", "timestamp"]:
    ok(k in js, f"SCORM 2004: {k}")
for k in ["X-Experience-API-Version", "'1.0.2'", "activities/state", "suspend_data", "bookmark", "cumulative_time", "language_preference", "isft-state", "keepalive",
          "?method=", "application/x-www-form-urlencoded", "statementId", "attempted", "progressed", "experienced", "answered", "passed", "failed", "registration"]:
    ok(k in js, f"xAPI (Rise / NEXTID moslik): {k}")
ok("initialized" not in ljs and "terminated" not in ljs and "'resumed'" not in ljs, "xAPI: Rise'da yo'q fe'llar (initialized / resumed / suspended / terminated) yuborilmaydi")
ok("Ko'rish rejimi" in js and "natija LMS'ga yuborilmaydi" in js and "localStorage" in js and "get('preview') === '1'" in js, "Ko'rish rejimi banneri faqat ?preview=1 da, localStorage")
ok("LMS bilan aloqa topilmadi" in js and "O'qituvchiga xabar bering." in js and "m === 'scorm12' || m === 'scorm2004'" in js,
   "SCORM paketi API'siz — «LMS bilan aloqa topilmadi» ogohlantirishi (xAPI/none — jim)")
ok("source: 'isft-paket'" in js and "W.parent.postMessage" in js and "W.parent === W" in js, "Ota oynaga postMessage (faqat iframe ichida)")
for k in ["'matching'", "[.]", "[,]", "source", "target", "id36("]:
    ok(k in js, f"Matching interaction (match/sort): {k}")
for k in ["'track'", "kind: 'subtitles'", "playsinline", "preload: 'metadata'", "playbackRate", "loadedmetadata", "timeupdate", "video: { block: b.id, watched: w }"]:
    ok(k in js, f"Fayl-video: {k}")
ok(all(k in js for k in ["cover:", "flashcards:", "assignment:", "matchWidget", "sortWidget", "pointerdown", "aria-pressed", "Javobni LMS'dagi «Vazifa yuklash» orqali yuboring"]),
   "Kontrakt v3 bloklari: muqova, kartochkalar, topshiriq, match/sort vidjetlari")
ok("crossorigin: 'anonymous'" not in js and "crossorigin: opaqueHttp() ? 'anonymous' : null" in js and "String(W.origin) === 'null' && /^https?:$/.test(W.location.protocol)" in js,
   "Fayl-video: crossorigin faqat sandboxed ko'rishda (opaque origin + http/https) — file:// va same-origin'da qo'yilmaydi")
ok("c.cover.author == null ? null" in js and "a != null ? a : str(C.course.teacher)" in js and "cv.author ||" not in js and "C.cover.author ||" not in js,
   "Muqova: author === '' — muallifsiz; course.teacher'ga faqat null/undefined bo'lsa qaytadi (muqova va chop etish)")
ok(re.search(r"function typing\(t\) \{[^}]*form\.qform,fieldset\.q,\.m-slot,\.m-tile,\.m-bank,\.s-card,\.s-drop,\.fc-grid,\.fc'", js) is not None,
   "Global ← → / PageUp / PageDown: test formasi, match/sort vidjetlari va kartochkalar ichida ishlamaydi")
ok(js.count("/^(tf|fill|match|sort|multi)$/.test(q.type)") == 2 and "q.type === 'multi' || (q.type === 'mcq' && q.correct.length > 1)" in js
   and "(q.type === 'mcq' || q.type === 'multi') ? shuffled" in js,
   "Test: «multi» savol turi (belgilash katakchalari, variantlar aralashadi) + eski mcq (correct ≥ 2) orqaga mos; baholash — «hammasi va faqat shular» (brauzer: tools/paket_player_check.js «multi»)")
ok("e.pointerType === 'touch'" in js and "ondragstart" not in js, "Sudrash — faqat sichqoncha/pero uchun qo'shimcha (sensor va klaviaturada bosib tanlash)")
ok("prefers-color-scheme:dark" in css.replace(" ", "") and "@media print" in css and "prefers-reduced-motion" in css and ":focus-visible" in css,
   "CSS: qorong'i rejim, chop etish, reduced-motion, focus-visible")

print("== 4. Namuna paket (tests/fixtures/paket_sample)")
cj = json.loads((FX / "content.json").read_text(encoding="utf-8"))
cjs = (FX / "content.js").read_text(encoding="utf-8").strip()
ok(cjs.startswith("window.PAKET = ") and cjs.endswith(";"), "content.js = «window.PAKET = {...};»")
ok(json.loads(cjs[len("window.PAKET = "):-1]) == cj, "content.js va content.json bir xil")
ok(cj.get("v") == 1 and re.match(r"^isft-\d+-\d+-v\d+$", cj["id"]) and cj["tracking"]["mode"] in ("scorm12", "scorm2004", "xapi", "none"), "Kontrakt: v, id, tracking.mode")
ok(cj.get("layout") == "steps" and cj.get("lesson", {}).get("code") == "L1", "Kontrakt v2: layout=steps, lesson")
ok(isinstance(cj.get("cover"), dict) and cj["cover"].get("image") == "assets/cover.jpg" and cj["cover"].get("author"), "Kontrakt v3: cover {image, author}")
types = [b["type"] for b in cj["blocks"]]
ok({"plan", "text", "slides", "video", "file", "quiz", "section", "refs", "keypoints", "reflect", "flashcards", "assignment", "hotspot"} <= set(types), f"Barcha blok turlari bor (+ noma'lum tur sinovi uchun): {types}")
ok(any(b["type"] == "plan" and b.get("heading") for b in cj["blocks"]) and any(b["type"] == "slides" and b.get("display") == "images" for b in cj["blocks"]), "plan.heading va slides.display=images")
vf = next((b for b in cj["blocks"] if b["type"] == "video" and b.get("provider") == "file"), {})
ok(vf.get("src", "").endswith(".mp4") and vf.get("poster") and any(c.get("src", "").endswith(".vtt") for c in vf.get("captions", []))
   and any(b["type"] == "video" and b.get("provider") == "youtube" for b in cj["blocks"]), "Kontrakt v3: fayl-video (src, poster, captions) + YouTube video")
qz = next(b for b in cj["blocks"] if b["type"] == "quiz")
ok({q["type"] for q in qz["questions"]} == {"mcq", "tf", "fill", "match", "sort"}
   and all(len(q["pairs"]) >= 2 for q in qz["questions"] if q["type"] == "match")
   and all(len(q["categories"]) >= 2 for q in qz["questions"] if q["type"] == "sort"), "Kontrakt v3: test — mcq, tf, fill, match (pairs), sort (categories)")
sl = next(b for b in cj["blocks"] if b["type"] == "slides")["slides"]
ok(any(x.get("caption") for x in sl) and any(x.get("audio") for x in sl), "Kontrakt v3: slides[].caption va .audio")
fc = next(b for b in cj["blocks"] if b["type"] == "flashcards"); asg = next(b for b in cj["blocks"] if b["type"] == "assignment")
ok(len(fc["cards"]) >= 3 and asg.get("text") and asg.get("author") and len(asg.get("questions", [])) >= 2 and "avatar" in asg
   and any(b["type"] == "section" and b["title"] == "MASHQ VA TOPSHIRIQLAR" for b in cj["blocks"]), "Kontrakt v3: flashcards, assignment, «MASHQ VA TOPSHIRIQLAR» bo'limi")
txt = next(b["html"] for b in cj["blocks"] if b["type"] == "text")
ok("<figure>" in txt and "<figcaption>" in txt and 'src="http://evil"' in txt and 'src="data:' in txt and "java\tscript:" in txt, "Matnda figure/figcaption va hujum satrlari (http/data/java\\tscript rasmlar)")
refs = [cj["brand"]["logo"]] + [s.get("image") for b in cj["blocks"] if b["type"] == "slides" for s in b["slides"]] + \
       [b.get(k) for b in cj["blocks"] for k in ("file", "pdf", "href", "poster", "avatar")] + re.findall(r'src="(assets/[^"]+)"', txt) + \
       [cj["cover"]["image"], vf.get("src")] + [c["src"] for c in vf.get("captions", [])] + [x.get("audio") for x in sl]
refs = [r for r in refs if r and r.startswith("assets/")]   # tashqi/xavfli manzillar — ataylab qo'shilgan hujum satrlari
ok(all((FX / r).is_file() for r in refs), f"Paketdagi barcha asset havolalari mavjud ({len(refs)} ta)")

print("== 5. JS sintaksisi")
node = shutil.which("node")
if node:
    for f in [PL / "player.js", PL / "lms.js", ROOT / "tools" / "paket_player_check.js", ROOT / "tools" / "nextid_parity_check.js", FX / "content.js"]:
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        ok(r.returncode == 0, f"node --check {f.relative_to(ROOT)}" + ("" if r.returncode == 0 else ": " + r.stderr.strip()[:200]))
else:
    print("  – node topilmadi — sintaksis tekshiruvi o'tkazib yuborildi")

print("== 6. Brauzerdagi muvofiqlik sinovi (Playwright)")
pw, chrome = os.environ.get("PW"), os.environ.get("CHROME")
if not (pw and chrome and node):
    print("  – PW/CHROME berilmagan — o'tkazib yuborildi")
else:
    env = dict(os.environ)
    r = subprocess.run([node, str(ROOT / "tools" / "paket_player_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    for ln in out.splitlines():   # harness natijalari shu to'plam natijalariga aylanadi (run_all ✓/✗ ni sanaydi)
        s = ln.strip()
        if ln.startswith("=="): print("  " + ln)
        elif s.startswith("✓"): ok(True, "[brauzer] " + s[1:].strip())
        elif s.startswith("✗"): ok(False, "[brauzer] " + s[1:].strip())
    ok(r.returncode == 0, f"Muvofiqlik sinovi chiqish kodi 0 ({r.returncode})" + ("" if r.returncode == 0 else ":\n" + "\n".join(out.splitlines()[-15:])))

print("== 7. NEXTID (Articulate Rise) bilan simdagi moslik — app.paket.build_zip paketi, NEXTID launch'i, boshqa domendagi soxta LRS")
# Namuna paketdan haqiqiy yig'uvchi (build_zip, xAPI) bilan paket: scormdriver/indexAPI.html orqali «endpoint=…&auth=Bearer …&actor={"name":9424693}»
# bilan ochiladi; so'rovlar ketma-ketligi Rise yozuvi bilan solishtiriladi (tools/nextid_parity_check.js; docs/paket.md «Kuzatuv»).
import tempfile, zipfile, io
sys.path.insert(0, str(ROOT))
from app import paket as PK
pc = json.loads(json.dumps(cj))
pc["blocks"] = [b for b in pc["blocks"] if b["type"] in PK.BLOCK_TYPES]
for b in pc["blocks"]:
    if b["type"] == "text": b["html"] = "<h2>Kirish</h2><p>Matritsa — sonlar jadvali.</p><h2>Amallar</h2><p>Qo'shish va ko'paytirish.</p>"
    if b["type"] == "quiz": b["questions"] = [x for x in b["questions"] if x["type"] in ("mcq", "tf", "fill")]
    if b["type"] == "refs": b["items"] = [x for x in b["items"] if isinstance(x, str)]            # hujum satrlari / obyekt bandlar — pleyer sinoviniki
    if b["type"] == "flashcards": b["cards"] = [x for x in b["cards"] if str(x.get("front") or "").strip() and str(x.get("back") or "").strip()]
    if b["type"] == "video" and b.get("captions"): b["captions"] = [x for x in b["captions"] if str(x["src"]).startswith("assets/")]
pc.update(layout="rise")    # standart NEXTID ko'rinishi: ↓, «davom etish» tugmalari, bloklar oxirigacha aylantiriladi (tools/nextid_parity_check.js)
pc["tracking"].update(completion="view_all", activity_id="https://isft.uz/xapi/paket/12/5")
pfiles = {str(p_.relative_to(FX)): p_.read_bytes() for p_ in (FX / "assets").rglob("*") if p_.is_file()}
pzip = PK.build_zip(pc, pfiles, "xapi", player_dir=PL)
pv = PK.validate_zip(pzip)
pz = zipfile.ZipFile(io.BytesIO(pzip))
ok(pv["ok"] and "scormdriver/indexAPI.html" in pz.namelist() and b"<launch lang=\"uz\">scormdriver/indexAPI.html</launch>" in pz.read("tincan.xml"),
   f"build_zip (xAPI): tekshiruvdan o'tdi, tincan.xml launch — scormdriver/indexAPI.html ({pv['errors'][:2]})")
if not (pw and chrome and node):
    print("  – PW/CHROME berilmagan — brauzer qismi o'tkazib yuborildi")
else:
    pdir = Path(tempfile.mkdtemp(prefix="nextid-parity-")); pz.extractall(pdir)
    env = dict(os.environ, PKG_DIR=str(pdir), QUIZ=json.dumps(next(b for b in pc["blocks"] if b["type"] == "quiz")))
    r = subprocess.run([node, str(ROOT / "tools" / "nextid_parity_check.js")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    for ln in out.splitlines():
        s_ = ln.strip()
        if ln.startswith("=="): print("  " + ln)
        elif s_.startswith("✓"): ok(True, "[NEXTID] " + s_[1:].strip())
        elif s_.startswith("✗"): ok(False, "[NEXTID] " + s_[1:].strip())
        elif s_.startswith("»"): print("    " + s_)
    ok(r.returncode == 0, f"tools/nextid_parity_check.js chiqish kodi 0 ({r.returncode})" + ("" if r.returncode == 0 else ":\n" + "\n".join(out.splitlines()[-15:])))
    shutil.rmtree(pdir, ignore_errors=True)

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
