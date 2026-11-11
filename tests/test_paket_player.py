"""O'quv paket pleyeri (app/paket_player) — statik tekshiruvlar + (ixtiyoriy) brauzerdagi muvofiqlik sinovi.

Ishga tushirish:  .venv/bin/python tests/test_paket_player.py
   (yoki: python tests/run_all.py --only paket_player — server kerak emas, ISFT_TEST_URL e'tiborsiz qoldiriladi)
Brauzer sinovi (SCORM 1.2 / SCORM 2004 / xAPI / ko'rish rejimi, 390px, qorong'i rejim) faqat PW va CHROME berilganda:
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
ok({"index.html", "player.js", "player.css"} <= names, "index.html, player.js, player.css mavjud")
size = sum(p.stat().st_size for p in files)
ok(size < 150 * 1024, f"Pleyer hajmi {size / 1024:.1f} KB < 150 KB (shriftlar bilan)")
ok(all(p.suffix in {".html", ".js", ".css", ".woff2"} for p in files), "Faqat html/js/css/woff2 fayllar: " + ", ".join(sorted(names)))

html = (PL / "index.html").read_text(encoding="utf-8")
js = (PL / "player.js").read_text(encoding="utf-8")
css = (PL / "player.css").read_text(encoding="utf-8") + "".join(p.read_text(encoding="utf-8") for p in PL.rglob("*.css") if p.name != "player.css")
srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', html)
ok(srcs == ["content.js", "player.js"], f"index.html avval content.js, keyin player.js ni yuklaydi ({srcs})")
ok('href="player.css"' in html and '<meta name="viewport"' in html and 'lang="uz"' in html, "index.html: player.css, viewport, lang=uz")
ok(not re.search(r'(src|href)="(/|[a-z]+:)', html), "index.html: faqat nisbiy manzillar")

print("== 2. Xavfsizlik va tashqi resurslar")
ALLOWED = re.compile(r"^https?://(www\.)?(youtube-nocookie\.com|youtube\.com|youtu\.be)(/|$)|^http://adlnet\.gov/expapi/")
urls = re.findall(r"https?://[^\s'\"()<>]+", js + css + html)
bad = [u for u in urls if not ALLOWED.match(u)]
ok(not bad, f"Tashqi URL lar faqat YouTube va ADL xAPI IRI ({len(urls)} ta topildi){': ' + ', '.join(bad[:5]) if bad else ''}")
ok(not re.search(r"\beval\s*\(|new\s+Function\s*\(|setTimeout\s*\(\s*['\"]|document\.write", js), "eval / new Function / satrli setTimeout / document.write yo'q")
ok(not re.search(r"@import|url\((['\"]?)(https?:|//)", css), "CSS da tashqi @import/url yo'q")
inner = re.findall(r"\.innerHTML\s*=\s*([^;]+)", js)
ok(len(inner) == 1 and "ICONS" in inner[0], f"innerHTML faqat statik SVG ikonalar uchun ({len(inner)} joy)")
ok("DOMParser" in js and "noopener" in js, "Kontent HTML DOMParser + oq ro'yxat sanitizeri orqali, havolalar rel=noopener")
glb = set(re.findall(r"\bW\.([A-Za-z_$][\w$]*)\s*=(?!=)", js))
ok(glb == {"ISFTPaket"}, f"Global obyekt faqat window.ISFTPaket ({sorted(glb)})")
ok(js.lstrip().startswith("/*") and "'use strict'" in js[:2000], "IIFE + 'use strict'")

print("== 3. Standartlar (kalit elementlar)")
for k in ["cmi.core.lesson_status", "cmi.core.score.raw", "cmi.core.session_time", "cmi.core.exit", "cmi.suspend_data", "cmi.core.lesson_location",
          "LMSInitialize", "LMSCommit", "LMSFinish", "LMSGetLastError", "cmi.interactions."]:
    ok(k in js, f"SCORM 1.2: {k}")
for k in ["API_1484_11", "cmi.completion_status", "cmi.success_status", "cmi.score.scaled", "cmi.progress_measure", "cmi.location", "cmi.session_time",
          "Terminate", "learner_response", "timestamp"]:
    ok(k in js, f"SCORM 2004: {k}")
for k in ["X-Experience-API-Version", "1.0.3", "activities/state", "isft-state", "keepalive", "initialized", "experienced", "answered", "passed", "failed", "completed", "terminated", "registration"]:
    ok(k in js, f"xAPI: {k}")
ok("Ko'rish rejimi" in js and "natija LMS'ga yuborilmaydi" in js and "localStorage" in js, "Ko'rish rejimi banneri va localStorage")
ok("prefers-color-scheme:dark" in css.replace(" ", "") and "@media print" in css and "prefers-reduced-motion" in css and ":focus-visible" in css,
   "CSS: qorong'i rejim, chop etish, reduced-motion, focus-visible")

print("== 4. Namuna paket (tests/fixtures/paket_sample)")
cj = json.loads((FX / "content.json").read_text(encoding="utf-8"))
cjs = (FX / "content.js").read_text(encoding="utf-8").strip()
ok(cjs.startswith("window.PAKET = ") and cjs.endswith(";"), "content.js = «window.PAKET = {...};»")
ok(json.loads(cjs[len("window.PAKET = "):-1]) == cj, "content.js va content.json bir xil")
ok(cj.get("v") == 1 and re.match(r"^isft-\d+-\d+-v\d+$", cj["id"]) and cj["tracking"]["mode"] in ("scorm12", "scorm2004", "xapi", "none"), "Kontrakt: v, id, tracking.mode")
types = [b["type"] for b in cj["blocks"]]
ok({"plan", "text", "slides", "video", "file", "quiz"} <= set(types), f"Barcha blok turlari bor (+ noma'lum tur sinovi uchun): {types}")
refs = [cj["brand"]["logo"]] + [s.get("image") for b in cj["blocks"] if b["type"] == "slides" for s in b["slides"]] + \
       [b.get(k) for b in cj["blocks"] for k in ("file", "pdf", "href")]
refs = [r for r in refs if r]
ok(all((FX / r).is_file() for r in refs), f"Paketdagi barcha asset havolalari mavjud ({len(refs)} ta)")

print("== 5. JS sintaksisi")
node = shutil.which("node")
if node:
    for f in [PL / "player.js", ROOT / "tools" / "paket_player_check.js", FX / "content.js"]:
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

print()
if fails:
    print(f"XATO: {len(fails)} ta tekshiruv o'tmadi"); sys.exit(1)
print("Hammasi o'tdi")
