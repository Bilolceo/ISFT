"""«Kontent paketlari» — Masofaviy ta'lim bo'limi uchun mavzu bo'yicha SCORM / xAPI paket yig'uvchi (docs/paket.md). 3-bosqich.

Nima uchun: bo'lim har bir mavzu uchun Articulate'da (yiliga ≈ $2000) bitta paket yig'adi — ma'ruza matni (reja bilan), taqdimot bloki,
YouTube video havolasi va test; xAPI zip qilib LMS'ga yuklaydi. Bu modul o'sha ishni o'zimizda bajaradi:

  1. Manbalar (mavzu bo'yicha, aniq ustuvorlik bilan — gather()):
     ma'ruza matni  — shu yerda yuklangan .docx/.pdf/.txt (pk_assets, purpose='matn') > Test bank mavzu matni (tb_sources, oxirgisi);
                      matn → tuzilgan HTML (sarlavhalar, ro'yxatlar, jadval) + «Reja» bloki (structure_text, sanitize — server tomonda);
     taqdimot       — yuklangan .pptx (python-pptx: slayd sarlavhasi, bandlar, izohlar, ichidagi rasmlar) > «Taqdimot» modulidagi deck
                      (pres_decks) > PNG/JPG slayd rasmlari to'plami; .pdf — brauzerda ochiladigan nusxa; asl .pptx — yuklab olish uchun;
     video          — shu yerda kiritilgan havola (pk_topics.video_url) > kontent monitoringidagi videodars havolasi (dl_items, kind='video');
                      YouTube (watch / youtu.be / shorts / embed / live, t=) → video bloki; boshqa http(s) havola → havola (matn bloki);
     test           — Test bankdagi TASDIQLANGAN savollar (tb_questions); hammasi yoki N ta (deterministik tanlov), aralashtirish, o'tish foizi, urinishlar.
  2. Yig'ish (build_zip — deterministik: tartiblangan yozuvlar, qotirilgan vaqt): pleyer fayllari (app/paket_player/), content.js
     (window.PAKET = {...};), content.json, assets/…, manifest: SCORM 1.2 (imsmanifest.xml), SCORM 2004 4th (imsmanifest.xml), xAPI (tincan.xml)
     yoki oddiy HTML (none). «Kurs paketi» — bitta SCORM/xAPI manifestda har mavzu alohida SCO (o'z papkasida).
  3. Tekshiruv (validate_zip) har yig'ishdan keyin: manifest o'qiladi, identifikatorlar yagona, har bir href/file zip ichida, ishga tushirish
     fayli bor, content.js JSON, mutlaq / «..» yo'llar yo'q, YouTube iframe'dan boshqa tashqi skript yo'q.
  4. Saqlash: <DATA_DIR>/paket/… (doimiy disk); mavzu boshiga oxirgi 3 versiya (+ tasdiqlangani); ko'rish (preview) — qat'iy CSP bilan.

Ruxsat (modul jadvali, har bir so'rov audit jurnalida — rbac.PAKET):
  masofaviy, masofaviy_xodim — barcha kurslar: manba, yig'ish, tasdiqlash / qaytarish, umumiy sozlamalar;
  oqituvchi — o'z kurslari: manba yuklash, yig'ish, ko'rish, yuklab olish;  kafedra — o'z kafedrasi kurslari: ko'rish, yuklab olish;
  rektor, prorektor_oquv — faqat jamlangan qamrov.
"""
from __future__ import annotations
import datetime as dt, hashlib, hmac, html, io, json, os, random, re, secrets, shutil, threading, time, unicodedata, zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote
from xml.sax.saxutils import escape as _xesc, quoteattr as _xattr
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/paket"
RES = rbac.PAKET

HEAD, STAFF = "masofaviy", "masofaviy_xodim"
DEPT = (HEAD, STAFF)                      # bo'lim: hamma kurslar, tasdiqlash, sozlamalar
LEAD = ("rektor", "prorektor_oquv")       # rahbariyat: faqat jamlangan qamrov
KAF, TEACH = "kafedra", "oqituvchi"
ALL = DEPT + LEAD + (KAF, TEACH)
WORK = DEPT + (KAF, TEACH)                # paketlarni ko'radi, yuklab oladi
AUTHORS = DEPT + (TEACH,)                 # manba, yig'ish

PLAYER_DIR = Path(__file__).resolve().parent / "paket_player"   # pleyer (boshqa ish oqimi) — testlarda jarayon ichida almashtiriladi
STORE: Path | None = None                                        # None → <DATA_DIR>/paket (testlarda almashtiriladi)

MODES = {"scorm12": "SCORM 1.2", "scorm2004": "SCORM 2004 (4-nashr)", "xapi": "xAPI (Tin Can)", "none": "Oddiy HTML (LMS'siz)"}
COMPLETION = {"view_all": "Barcha bloklar ko'rilganda", "quiz_pass": "Test topshirilganda", "view_and_quiz": "Ko'rilganda va test topshirilganda"}
STATUS = {"qoralama": "Qoralama", "tayyor": "Tayyor (tasdiq kutilmoqda)", "tasdiqlandi": "Tasdiqlandi"}
BLOCKS = {"plan": "Reja", "text": "Ma'ruza matni", "slides": "Taqdimot", "video": "Videodars", "files": "Qo'shimcha fayllar", "quiz": "Test"}
REQUIRED = ("text", "slides", "video", "quiz")    # «tayyor» bo'lishi uchun (sozlamada yoqilganlari)
DEFAULTS = {"mode": "scorm12", "completion": "view_and_quiz", "mastery": 60, "quiz_n": 0, "shuffle": True, "attempts": 0,
            "show_feedback": True, "blocks": {k: True for k in BLOCKS}}

MAX_ASSET = 50 * 1024 * 1024       # bitta fayl
MAX_PACKAGE = 200 * 1024 * 1024    # tayyor paket
MAX_TEXT_CHARS = 200_000
MAX_SLIDES = 200
KEEP_VERSIONS = 3
IMG_MAX_PX = 1600
IMG_MAX_PIXELS = 40_000_000          # rasm (dekodlashdan oldin o'lcham tekshiriladi) — «rasm bombasi» himoyasi
ZIP_MAX_TOTAL = 300 * 1024 * 1024    # OOXML (.pptx/.docx/.xlsx) ichidagi fayllarning ochilgan umumiy hajmi
ZIP_MAX_ENTRY = 150 * 1024 * 1024    # bitta ichki fayl (ochilgan)
ZIP_MAX_FILES = 5000                 # ichki fayllar soni
ZIP_MAX_RATIO = 100                  # siqish nisbati — «zip bombasi» himoyasi (ZIP_RATIO_FROM dan katta ichki fayllar uchun:
ZIP_RATIO_FROM = 5 * 1024 * 1024     #   kichik XML/bir rangli rasm tabiiy ravishda kuchli siqiladi)
FIXED_TS = (1980, 1, 1, 0, 0, 0)   # zip yozuvlari vaqti (deterministik)
ACTIVITY_BASE = "https://isft.uz/xapi/paket"
BRAND_COLOR = "#8B0033"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pk_packages(id INTEGER PRIMARY KEY, course_id INT, topic_no INT, version INT, mode TEXT, status TEXT DEFAULT 'tayyor',
  settings TEXT, content_hash TEXT, built_at TEXT, built_by INT, built_by_name TEXT, file TEXT, size INT, sha256 TEXT, validation TEXT, error TEXT,
  readiness TEXT, approved_by INT, approved_name TEXT, approved_at TEXT, note TEXT, src TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_pk_pkg ON pk_packages(course_id, topic_no, version);
CREATE INDEX IF NOT EXISTS ix_pk_pkg_st ON pk_packages(status);
CREATE TABLE IF NOT EXISTS pk_assets(id INTEGER PRIMARY KEY, course_id INT, topic_no INT, purpose TEXT, kind TEXT, name TEXT, path TEXT, size INT,
  sha256 TEXT, meta TEXT, user_id INT, user_name TEXT, ts TEXT, src TEXT DEFAULT '', deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_pk_assets ON pk_assets(course_id, topic_no, deleted);
CREATE TABLE IF NOT EXISTS pk_topics(course_id INT, topic_no INT, video_url TEXT, video_at TEXT, video_by TEXT, deck_id INT, settings TEXT,
  updated_at TEXT, src TEXT DEFAULT '', PRIMARY KEY(course_id, topic_no));
CREATE TABLE IF NOT EXISTS pk_log(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, user_name TEXT, course_id INT, topic_no INT, package_id INT,
  action TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_pk_log ON pk_log(course_id, topic_no);
CREATE TABLE IF NOT EXISTS pk_meta(k TEXT PRIMARY KEY, v TEXT);
"""


def _now(): return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def _short(name): return (name or "").split(":", 1)[1].strip() if ":" in (name or "") else (name or "")
def _pct(a, b): return round(100.0 * a / b, 1) if b else None
def _sha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def store() -> Path: return STORE or (Path(db.DATA_DIR) / "paket")
def player_ok() -> bool: return (PLAYER_DIR / "index.html").is_file()


# =============================================================================================
# Sxema, bog'lash
# =============================================================================================
def init(con):
    try:
        con.executescript(SCHEMA)
        con.execute("INSERT OR IGNORE INTO pk_meta(k,v) VALUES('defaults', ?)", (json.dumps(DEFAULTS),))
        con.commit()
    except Exception as e:
        print("paket.init:", e); return
    if not db.one(con, "SELECT 1 x FROM users"): return
    try:
        seed(con)
    except Exception as e:      # demo ma'lumot ilovani to'xtatmasin
        print("paket seed:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


# =============================================================================================
# Sozlamalar
# =============================================================================================
def _clean_settings(s: dict, base: dict) -> dict:
    s = s if isinstance(s, dict) else {}
    out = json.loads(json.dumps(base))
    if s.get("mode") in MODES: out["mode"] = s["mode"]
    if s.get("completion") in COMPLETION: out["completion"] = s["completion"]
    for k, lo, hi in (("mastery", 0, 100), ("quiz_n", 0, 200), ("attempts", 0, 20)):
        if k in s:
            try: out[k] = max(lo, min(hi, int(s[k])))
            except (TypeError, ValueError): pass
    for k in ("shuffle", "show_feedback"):
        if k in s: out[k] = bool(s[k])
    if isinstance(s.get("blocks"), dict):
        for k in BLOCKS:
            if k in s["blocks"]: out["blocks"][k] = bool(s["blocks"][k])
    return out

def defaults(con=None) -> dict:
    r = db.one(con or _con, "SELECT v FROM pk_meta WHERE k='defaults'")
    try: return _clean_settings(json.loads(r["v"]) if r else {}, DEFAULTS)
    except (TypeError, ValueError): return json.loads(json.dumps(DEFAULTS))

def _topic_row(cid: int, no: int) -> dict:
    return db.one(_con, "SELECT * FROM pk_topics WHERE course_id=? AND topic_no=?", (cid, no)) or {}

def topic_settings(cid: int, no: int) -> tuple[dict, dict]:
    """(amaldagi sozlama, mavzu uchun o'zgartirilganlari)."""
    tr = _topic_row(cid, no)
    try: over = json.loads(tr.get("settings") or "{}")
    except ValueError: over = {}
    return _clean_settings(over, defaults()), over


# =============================================================================================
# YouTube / havola
# =============================================================================================
YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "youtu.be"}
_T_RX = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")

def _parse_t(v: str) -> int:
    v = (v or "").strip().lower()
    if not v: return 0
    if v.isdigit(): return int(v)
    m = _T_RX.match(v)
    if not m or not any(m.groups()): return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s

def parse_video(url: str) -> dict:
    """Havola → {ok, provider: youtube|link, video_id, url, start} yoki {ok: False, error}."""
    s = (url or "").strip()
    if not s: return {"ok": False, "error": "Havola bo'sh"}
    if YT_ID.match(s):
        return {"ok": True, "provider": "youtube", "video_id": s, "url": f"https://www.youtube.com/watch?v={s}", "start": 0}
    if not re.match(r"^https?://", s, re.I):
        if re.match(r"^(www\.|m\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/", s, re.I): s = "https://" + s
        else: return {"ok": False, "error": "Havola http:// yoki https:// bilan boshlanishi kerak"}
    try: u = urlsplit(s)
    except ValueError: return {"ok": False, "error": "Havola noto'g'ri"}
    host = (u.hostname or "").lower()
    if not host or " " in s: return {"ok": False, "error": "Havola noto'g'ri"}
    h = host[4:] if host.startswith("www.") else host
    if h in YT_HOSTS:
        qs = parse_qs(u.query)
        parts = [p for p in u.path.split("/") if p]
        vid = ""
        if h == "youtu.be": vid = parts[0] if parts else ""
        elif parts[:1] == ["watch"]: vid = (qs.get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v", "e"): vid = parts[1]
        elif parts[:1] == ["playlist"]: return {"ok": False, "error": "Bu pleylist — alohida video havolasini bering"}
        if not YT_ID.match(vid or ""):
            return {"ok": False, "error": "YouTube video ID noto'g'ri (11 belgidan iborat bo'lishi kerak)"}
        frag = parse_qs(u.fragment) if "=" in (u.fragment or "") else {}
        start = _parse_t((qs.get("t") or qs.get("start") or frag.get("t") or [""])[0])
        return {"ok": True, "provider": "youtube", "video_id": vid, "start": start,
                "url": f"https://www.youtube.com/watch?v={vid}" + (f"&t={start}s" if start else "")}
    if u.scheme.lower() not in ("http", "https"): return {"ok": False, "error": "Faqat http(s) havola"}
    return {"ok": True, "provider": "link", "video_id": None, "url": s, "start": 0}

_BULK_RX = re.compile(r"^\s*(\d{1,3})\s*(?:[:.)\-–—]|\s)\s*(\S+)\s*$")

def parse_bulk(text: str, n_topics: int) -> list[dict]:
    """«Avtomatik joylash»: har qatorda havola (ketma-ket 1..n) yoki «N: havola». → [{line, topic_no, url, ok, error, video}]"""
    out, nxt = [], 1
    for i, raw in enumerate((text or "").replace("\r", "").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"): continue
        m = _BULK_RX.match(line)
        if m and not YT_ID.match(line):
            no, url = int(m.group(1)), m.group(2)
        else:
            no, url = nxt, line.split()[0]
        r = {"line": i, "topic_no": no, "url": url}
        v = parse_video(url)
        if not 1 <= no <= n_topics: r.update(ok=False, error=f"Mavzu raqami 1–{n_topics} oralig'ida bo'lishi kerak")
        elif not v["ok"]: r.update(ok=False, error=v["error"])
        else: r.update(ok=True, error="", video=v)
        out.append(r)
        nxt = no + 1
    seen = {}
    for r in out:
        if r.get("ok"):
            if r["topic_no"] in seen:
                seen[r["topic_no"]].update(ok=False, error="Shu mavzuga keyingi qatorda boshqa havola berilgan (oxirgisi olinadi)")
            seen[r["topic_no"]] = r
    return out


# =============================================================================================
# HTML tozalash (server tomonda, oq ro'yxat)
# =============================================================================================
ALLOWED_TAGS = {"h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "em", "b", "i", "u", "blockquote", "table", "thead", "tbody", "tr", "th", "td",
                "br", "sup", "sub", "code", "pre", "a"}
# Mazmuni bilan tashlanadigan teglar (ichidagi matn ham ko'rinmaydi): skript/uslub, xom matnli (textarea, title, xmp…), o'rnatilgan
# kontent va SVG/MathML. Bo'sh (void) teglar (embed, frame, param …) bu yerda emas — ular yopilmaydi, «skip» rejimiga kirmasdan tashlanadi.
_DROP_TAGS = {"script", "style", "iframe", "object", "noscript", "template", "svg", "math", "textarea", "title", "head", "xmp", "plaintext",
              "noembed", "noframes", "frameset", "applet", "xml", "video", "audio", "canvas"}
_RECOVER = {"textarea", "title", "xmp"}   # yopilmay qolsa — hujjat oxirida ichidagi matni (escape qilingan) qaytariladi
# Faqat tegning o'zi tashlanadi, ichidagi matn qoladi (oq ro'yxatdan tashqari boshqa teglar ham shunday): button, form, select, label …
_MAP_TAGS = {"h1": "h2", "h5": "h4", "h6": "h4"}
_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col", "area", "base", "param", "track", "embed", "frame", "keygen", "basefont",
         "bgsound", "image"}

def safe_href(v: str) -> str | None:
    v = re.sub(r"[\x00-\x20\x7f]", "", html.unescape(v or ""))
    return v if re.match(r"^https?://[^/\\]", v, re.I) else None

class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip, self.skip_n, self.held = [], [], None, 0, []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip:
            if tag == self.skip: self.skip_n += 1
            return
        if tag in _VOID: return                     # yopilmaydi — «skip» rejimiga kirmaydi (aks holda qolgan matn yo'qolardi)
        if tag in _DROP_TAGS:
            self.skip, self.skip_n, self.held = tag, 1, []; return
        tag = _MAP_TAGS.get(tag, tag)
        if tag not in ALLOWED_TAGS: return
        if tag == "br": self.out.append("<br>"); return
        if tag == "a":
            href = safe_href(dict(attrs).get("href") or "")
            if not href: return
            self.out.append(f'<a href="{html.escape(href, quote=True)}" rel="noopener noreferrer" target="_blank">')
        else:
            self.out.append(f"<{tag}>")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag == "br" and not self.skip: self.out.append("<br>")
        elif tag not in _VOID and tag not in _DROP_TAGS: self.handle_starttag(tag, attrs); self.handle_endtag(tag)   # <script/> — tashlanadi, skip yo'q

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip:
            if tag == self.skip:
                self.skip_n -= 1
                if self.skip_n <= 0: self.skip, self.skip_n = None, 0
            return
        tag = _MAP_TAGS.get(tag, tag)
        if tag not in self.stack: return
        while self.stack:
            t = self.stack.pop(); self.out.append(f"</{t}>")
            if t == tag: break

    def handle_data(self, data):
        if not self.skip: self.out.append(html.escape(data, quote=False))
        elif self.skip in _RECOVER: self.held.append(data)

    def result(self) -> str:
        if self.skip in _RECOVER and self.held:   # yopilmagan <textarea>/<title> qolgan hujjatni yutib yubormasin — matn sifatida
            self.out.append(html.escape("".join(self.held), quote=False))
        self.skip, self.skip_n, self.held = None, 0, []
        while self.stack: self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out)

class _Audit(HTMLParser):
    """Tayyor HTML'ni haqiqiy teglar bo'yicha tekshiradi (matndagi «onerror=», «javascript:» so'zlari — xavf emas, ular escape qilingan)."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.bad = None
    def handle_starttag(self, tag, attrs):
        if self.bad: return
        if tag not in ALLOWED_TAGS: self.bad = f"<{tag}>"; return
        for k, v in attrs:
            if tag == "a" and k == "href" and safe_href(v or ""): continue
            if tag == "a" and (k, v) in (("rel", "noopener noreferrer"), ("target", "_blank")): continue
            self.bad = f"<{tag} {k}>"; return
    handle_startendtag = handle_starttag

def html_unsafe(s: str) -> str | None:
    """None — xavfsiz; aks holda birinchi ruxsat etilmagan teg/atribut."""
    a = _Audit(); a.feed(str(s or "")); a.close()
    return a.bad

def sanitize(s: str) -> str:
    p = _Sanitizer()
    p.feed(str(s or "")); p.close()
    return p.result()


# =============================================================================================
# Ma'ruza matni → tuzilgan HTML + reja
# =============================================================================================
_APOS = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "´": "'", " ": " "})
_PLAN_RX = re.compile(r"^(?:#{1,6}\s*)?(?:ma'ruza\s+|mavzu\s+|dars\s+)?(reja|режа|план|reja\s*\(\s*plan\s*\))\s*[:.]?\s*(.*)$", re.I)
_BUL_RX = re.compile(r"^[-•*–—▪●◦►]\s+(.+)$")
_OL1_RX = re.compile(r"^(\d{1,2})[.)]\s+(.+)$")
_OLN_RX = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+(.+)$")
_MD_RX = re.compile(r"^(#{1,6})\s+(.+)$")
_IMG_RX = re.compile(r"^\[RASM \d+\]$")
_TITLE_RX = re.compile(r"^\d+\s*[-–]?\s*(mavzu|ma'ruza)\b", re.I)
_END_P = (".", "!", "?", "…", ":", ";", "»", '"', "”", ")")

def _inline(t: str) -> str:
    t = html.escape(t, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)

def _is_caps(line: str) -> bool:
    letters = [ch for ch in line if ch.isalpha()]
    return len(letters) >= 3 and all(ch.isupper() for ch in letters) and len(line) <= 90

def _clean_item(t: str) -> str:
    t = re.sub(r"^\s*(?:\d{1,2}(?:\.\d{1,2})*[.)]?|[-•*–—▪●◦►])\s+", "", t.strip())
    return t.strip().rstrip(";,.").strip()

def _tokens(text: str) -> list[tuple]:
    out = []
    for raw in str(text or "").translate(_APOS).replace("\r", "").split("\n"):
        line = raw.strip()
        if not line: out.append(("blank", "")); continue
        if _IMG_RX.match(line): continue
        if _PLAN_RX.match(line) and len(line) <= 400:
            out.append(("plan", _PLAN_RX.match(line).group(2).strip())); continue
        m = _MD_RX.match(line)
        if m: out.append(("h", m.group(2).strip(), min(3, len(m.group(1))))); continue
        m = _BUL_RX.match(line)
        if m: out.append(("ul", m.group(1).strip())); continue
        m = _OLN_RX.match(line)
        if m: out.append(("num", m.group(2).strip(), m.group(1).count(".") + 1)); continue
        m = _OL1_RX.match(line)
        if m: out.append(("ol1" if line[len(m.group(1))] == "." else "ol", m.group(2).strip(), int(m.group(1)))); continue
        if _is_caps(line): out.append(("h", line, 1)); continue
        out.append(("t", line))
    return out

def structure_text(text: str, topic_title: str = "") -> dict:
    """Matn (oddiy, «# sarlavha / - band» belgili yoki docx'dan) → {"plan": [...], "html": str, "explicit_plan": bool}."""
    toks = _tokens(text)
    nonblank = [i for i, t in enumerate(toks) if t[0] != "blank"]
    def nb(i, step):
        j = i + step
        while 0 <= j < len(toks) and toks[j][0] == "blank": j += step
        return toks[j] if 0 <= j < len(toks) else None
    # 1-o'tish: «N.» qatorlari — sarlavha yoki ro'yxat
    res = []
    for i, t in enumerate(toks):
        if t[0] == "ol1":
            p, n = nb(i, -1), nb(i, 1)
            run = (p is not None and p[0] == "ol1" and p[2] == t[2] - 1) or (n is not None and n[0] == "ol1" and n[2] == t[2] + 1)
            heading = not run and len(t[1]) <= 90 and not t[1].endswith(_END_P[:-1]) and (n is None or n[0] in ("t", "h", "num"))
            res.append(("h", t[1], 1) if heading else ("ol", t[1], t[2]))
        elif t[0] == "num":
            res.append(("h", t[1], min(3, t[2])) if len(t[1]) <= 120 and len(t[1].split()) <= 16 else ("ol", t[1]))
        else:
            res.append(t)
    # 2-o'tish: reja bo'limi
    plan, explicit, body, i = [], False, [], 0
    while i < len(res):
        t = res[i]
        if t[0] == "plan" and not explicit:
            explicit = True
            rest = t[1]
            if rest:
                items = [x for x in re.split(r"\s*(?:^|\s)\d{1,2}[.)]\s+", " " + rest) if x.strip()] if re.search(r"\d[.)]\s", rest) else [rest]
                plan += [_clean_item(x) for x in items if _clean_item(x)]
            i += 1
            plain, last_no = None, 0
            while i < len(res) and len(plan) < 20:
                u = res[i]
                if u[0] == "blank":
                    nx = next((x for x in res[i + 1:] if x[0] != "blank"), None)
                    cont = nx is not None and (nx[0] == "ul" or (nx[0] == "ol" and (len(nx) < 3 or nx[2] > last_no)))
                    if not plan or (cont and plain is not True): i += 1; continue
                    break
                if u[0] in ("ul", "ol") and plain is not True:
                    if u[0] == "ol" and len(u) > 2:
                        if u[2] <= last_no: break
                        last_no = u[2]
                    plan.append(_clean_item(u[1])); plain = False; i += 1; continue
                if u[0] == "t" and plain is not False and len(u[1]) <= 120 and not u[1].endswith(".") and len(plan) < 12:
                    plan.append(_clean_item(u[1])); plain = True; i += 1; continue
                break
            plan = [p for p in plan if p]
            continue
        body.append(t); i += 1
    # sarlavha mavzu nomining o'zi bo'lsa — HTMLdan olib tashlanadi (pleyer nomni o'zi ko'rsatadi)
    tt = (topic_title or "").translate(_APOS).strip().casefold()
    first = next((k for k, t in enumerate(body) if t[0] != "blank"), None)
    if first is not None and body[first][0] == "h" and (body[first][1].strip().casefold() == tt or _TITLE_RX.match(body[first][1])):
        body.pop(first)
    # HTML
    parts, para, lst = [], [], None
    def flush_p():
        if para: parts.append("<p>" + _inline(" ".join(para)) + "</p>"); para.clear()
    def flush_l():
        nonlocal lst
        if not lst: return
        kind, items = lst
        cells = [re.split(r"\s+\|\s+", x) for x in items]
        if kind == "ul" and len(items) >= 2 and all(len(c) >= 2 for c in cells) and len({len(c) for c in cells}) == 1:
            parts.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells[0]) + "</tr></thead><tbody>" +
                         "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:]) + "</tbody></table>")
        else:
            parts.append(f"<{kind}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{kind}>")
        lst = None
    headings = []
    for t in body:
        k = t[0]
        if k == "blank": flush_p(); continue
        if k in ("ul", "ol"):
            flush_p()
            if lst and lst[0] != k: flush_l()
            if not lst: lst = (k, [])
            lst[1].append(t[1]); continue
        flush_l()
        if k == "h":
            flush_p()
            lvl = max(1, min(3, t[2]))
            parts.append(f"<h{lvl + 1}>{_inline(t[1])}</h{lvl + 1}>")
            headings.append((lvl, _clean_item(t[1])))
            continue
        if k == "plan":   # ikkinchi «Reja» qatori — oddiy matn
            flush_p(); parts.append(f"<p><strong>Reja:</strong> {_inline(t[1])}</p>"); continue
        line = t[1]
        if len(line) <= 70 and line.endswith(":") and len(line.split()) <= 8 and not para:
            parts.append(f"<p><strong>{_inline(line)}</strong></p>"); continue
        para.append(line)
        if line.endswith(_END_P): flush_p()
    flush_p(); flush_l()
    if not explicit:
        top = [h for l, h in headings if l == 1 and h]
        plan = top if len(top) >= 2 else [h for l, h in headings if l <= 2 and h]
        if len(plan) < 2: plan = []
    return {"plan": plan[:20], "html": sanitize("".join(parts)), "explicit_plan": explicit}


# =============================================================================================
# PPTX / rasmlar
# =============================================================================================
def _too_big(w: int, h: int) -> bool: return w * h > IMG_MAX_PIXELS or max(w, h) > 30000

def _norm_image(data: bytes, strict: bool = False) -> tuple[bytes, str] | None:
    """Rasm → (png/jpg baytlari, kengaytma); juda kichik yoki buzilgan — None. Metama'lumot tashlanadi, ≤ IMG_MAX_PX.
    O'lcham dekodlashdan OLDIN (sarlavhadan) tekshiriladi: IMG_MAX_PIXELS dan katta — strict bo'lsa 413, aks holda None (PPTX ichidagi rasm o'tkaziladi)."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))       # dangasa: faqat sarlavha o'qiladi
        big = _too_big(*im.size)
    except Image.DecompressionBombError:
        big = True
    except Exception:
        return None
    if big:
        if strict: raise HTTPException(413, f"Rasm o'lchami juda katta — {IMG_MAX_PIXELS // 1_000_000} megapikseldan oshmasin")
        return None
    try:
        im.load()
    except Exception:
        return None
    w, h = im.size
    if w < 32 or h < 32: return None
    png = im.mode in ("RGBA", "LA", "P") or (im.format or "").upper() in ("PNG", "GIF", "BMP")
    im = im.convert("RGBA" if png else "RGB")
    if max(w, h) > IMG_MAX_PX: im.thumbnail((IMG_MAX_PX, IMG_MAX_PX))
    bio = io.BytesIO()
    if png: im.save(bio, "PNG", optimize=True); return bio.getvalue(), "png"
    im.save(bio, "JPEG", quality=86); return bio.getvalue(), "jpg"

def _shape_texts(shape, out: list):
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for s in shape.shapes: _shape_texts(s, out)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells: out.append(" | ".join(cells))
        return
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        for p in shape.text_frame.paragraphs:
            t = "".join(r.text for r in p.runs).strip() or (p.text or "").strip()
            if t: out.append(("  " * min(p.level, 3)) + t if p.level else t)

def _shape_pictures(shape, out: list):
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for s in shape.shapes: _shape_pictures(s, out)
        return
    try:
        img = shape.image
    except Exception:
        return
    try: area = int(shape.width or 0) * int(shape.height or 0)
    except Exception: area = 0
    out.append((area, img.blob))

def parse_pptx(raw: bytes, img_dir: Path | None = None, images: dict | None = None) -> dict:
    """PPTX → {"slides": [{title, bullets, notes, image(fayl nomi|None)}], "count"}. Har slayddagi eng katta rasm img_dir/sN.png|jpg ga
    (yoki images lug'atiga {nom: baytlar} — fayl hali saqlanmagan bo'lsa)."""
    from pptx import Presentation
    _zip_guard(raw)
    try:
        prs = Presentation(io.BytesIO(raw))
    except Exception:
        raise HTTPException(415, "PowerPoint (.pptx) faylini o'qib bo'lmadi — fayl buzilgan yoki eski .ppt formatida (PowerPoint'da .pptx qilib saqlang)")
    slides = []
    for n, sl in enumerate(prs.slides, 1):
        if n > MAX_SLIDES: break
        title = ""
        try:
            if sl.shapes.title is not None: title = (sl.shapes.title.text or "").strip()
        except Exception:
            title = ""
        texts, pics = [], []
        for sh in sl.shapes:
            try:
                if sl.shapes.title is not None and sh.shape_id == sl.shapes.title.shape_id: continue
            except Exception:
                pass
            _shape_texts(sh, texts); _shape_pictures(sh, pics)
        if not title and texts: title = texts.pop(0).strip()
        notes = ""
        try:
            if sl.has_notes_slide: notes = (sl.notes_slide.notes_text_frame.text or "").strip()
        except Exception:
            notes = ""
        image = None
        for _, blob in sorted(pics, key=lambda x: -x[0]):
            r = _norm_image(blob)
            if r:
                image = f"s{n}.{r[1]}"
                if img_dir is not None:
                    img_dir.mkdir(parents=True, exist_ok=True); (img_dir / image).write_bytes(r[0])
                if images is not None: images[image] = r[0]
                break
        slides.append({"title": re.sub(r"\s+", " ", title)[:300], "bullets": [b[:600] for b in texts[:30]], "notes": notes[:4000], "image": image})
    if not slides: raise HTTPException(400, "Taqdimotda slayd yo'q")
    return {"slides": slides, "count": len(slides)}


# =============================================================================================
# Ruxsat va ko'lam
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"paket: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Kontent paketlari: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def _teacher_id(c: Ctx): return int(c.user.get("teacher_id") or 0)

def scope(c: Ctx, alias="c") -> tuple[str, tuple]:
    k = c.role.key
    if k == KAF: return f"{alias}.department_id=?", (int(c.user.get("department_id") or 0),)
    if k == TEACH: return f"{alias}.teacher_id=?", (_teacher_id(c),)
    return "1=1", ()

def _course(c: Ctx, cid: int, write=False) -> dict:
    sw, sa = scope(c)
    r = db.one(_con, f"""SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id
                         LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.id=? AND {sw}""", (int(cid), *sa))
    if not r:
        if db.one(_con, "SELECT 1 x FROM dl_courses WHERE id=?", (int(cid),)):
            rbac.audit(_con, c, "paket: begona kurs", RES, False, f"kurs #{cid}")
            raise AccessDenied("⛔ Bu kurs sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
        raise HTTPException(404, "Kurs topilmadi")
    if write and c.role.key not in AUTHORS:
        rbac.audit(_con, c, "paket: tahrirlash rad etildi", RES, False, f"kurs #{cid}")
        raise AccessDenied("⛔ Kafedra mudiri paketlarni faqat ko'radi va yuklab oladi — manba va yig'ish o'qituvchi va Masofaviy ta'lim bo'limida. So'rov audit jurnaliga yozildi.")
    return r

def _check_topic(co: dict, no: int):
    if not 1 <= int(no) <= int(co["topics"] or 15): raise HTTPException(400, "Mavzu raqami noto'g'ri")

def _titles(cid: int) -> dict:
    return {r["topic_no"]: (r["t"] or "").strip() for r in db.rows(_con, "SELECT topic_no, MAX(topic) t FROM dl_items WHERE course_id=? GROUP BY topic_no", (cid,))}

def _topic_title(cid: int, no: int, titles=None) -> str:
    t = (titles if titles is not None else _titles(cid)).get(no)
    return t or f"{no}-mavzu"

def _log(c: Ctx | None, cid, no, action, note="", pid=None):
    u = c.user if c else {"id": None, "full_name": "Tizim"}
    _con.execute("INSERT INTO pk_log(ts,user_id,user_name,course_id,topic_no,package_id,action,note) VALUES(?,?,?,?,?,?,?,?)",
                 (_now(), u.get("id"), u.get("full_name"), cid, no, pid, action, (note or "")[:500]))


# =============================================================================================
# Fayllar (manbalar)
# =============================================================================================
def _ascii(s: str, n=60) -> str:
    s = str(s or "")
    cyr = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ", ["a", "b", "v", "g", "d", "e", "yo", "j", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                                                            "u", "f", "x", "ts", "ch", "sh", "sh", "", "i", "", "e", "yu", "ya", "o", "q", "g", "h"]))
    s = "".join((cyr[ch.lower()].capitalize() if ch.isupper() else cyr[ch.lower()]) if ch.lower() in cyr else ch for ch in s)
    s = unicodedata.normalize("NFKD", s.translate(_APOS).replace("'", "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:n] or "fayl"

def _zip_guard(raw: bytes) -> None:
    """OOXML (zip) tahlilidan OLDIN — markaziy katalog bo'yicha (ochmasdan): fayllar soni, har birining va umumiy ochilgan hajm,
    siqish nisbati. Python zipfile e'lon qilingan file_size dan ortiq o'qimaydi, shuning uchun bu chegaralar ishonchli.
    Buzilgan zip — bu yerda o'tkaziladi (keyingi tahlil 415 qaytaradi)."""
    if raw[:2] != b"PK": return
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z: infos = z.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, EOFError):
        return
    if len(infos) > ZIP_MAX_FILES: raise HTTPException(413, f"Fayl ichida juda ko'p qism ({len(infos)} > {ZIP_MAX_FILES}) — fayl buzilgan yoki xavfli")
    total = 0
    for i in infos:
        total += i.file_size
        if i.file_size > ZIP_MAX_ENTRY or total > ZIP_MAX_TOTAL:
            raise HTTPException(413, f"Fayl ochilganda juda katta (>{ZIP_MAX_TOTAL // (1024 * 1024)} MB) — rasmlarni siqib qayta saqlang")
        if i.file_size > ZIP_RATIO_FROM and i.file_size > ZIP_MAX_RATIO * max(1, i.compress_size):
            raise HTTPException(413, "Fayl ichidagi ma'lumot g'ayritabiiy siqilgan (zip bombasi belgisi) — fayl qabul qilinmadi")

def _ooxml_image_guard(raw: bytes, prefix: str) -> None:
    """Word/PowerPoint ichidagi rasmlar o'lchami (faqat sarlavha o'qiladi) — dekodlashdan oldin; katta bo'lsa 413."""
    from PIL import Image
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for i in z.infolist():
                if not i.filename.startswith(prefix) or i.file_size < 64: continue
                try:
                    with z.open(i) as f: big = _too_big(*Image.open(io.BytesIO(f.read(min(i.file_size, 2 * 1024 * 1024)))).size)
                except Image.DecompressionBombError:
                    big = True
                except Exception:
                    continue
                if big: raise HTTPException(413, f"Fayl ichidagi rasm o'lchami juda katta — {IMG_MAX_PIXELS // 1_000_000} megapikseldan oshmasin")
    except zipfile.BadZipFile:
        return

def _sniff_asset(raw: bytes) -> str:
    if raw[:5] == b"%PDF-": return "pdf"
    if raw[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if raw[:3] == b"\xff\xd8\xff": return "jpg"
    if raw[:4] == b"PK\x03\x04":
        _zip_guard(raw)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return "other"
        if "ppt/presentation.xml" in names: return "pptx"
        if "word/document.xml" in names: return "docx"
        if "xl/workbook.xml" in names: return "xlsx"
        return "zip"
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": return "ole"
    return "other"

def _asset_dir(cid: int, no: int) -> Path:
    return store() / "assets" / str(int(cid)) / str(int(no))

def _save_asset(c: Ctx | None, cid: int, no: int, purpose: str, kind: str, name: str, raw: bytes, meta: dict, src="") -> int:
    d = _asset_dir(cid, no); d.mkdir(parents=True, exist_ok=True)
    with _lock:
        aid = _con.execute("""INSERT INTO pk_assets(course_id,topic_no,purpose,kind,name,path,size,sha256,meta,user_id,user_name,ts,src)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (cid, no, purpose, kind, name[:160], "", len(raw), _sha(raw), json.dumps(meta, ensure_ascii=False),
                            c.user["id"] if c else None, c.user["full_name"] if c else "Tizim", _now(), src)).lastrowid
        fn = f"{aid}_{_ascii(Path(name).stem, 40)}.{kind if kind not in ('other', 'zip', 'ole') else 'bin'}"
        (d / fn).write_bytes(raw)
        _con.execute("UPDATE pk_assets SET path=? WHERE id=?", (str(Path("assets") / str(cid) / str(no) / fn), aid))
        _con.commit()
    return aid

def _apath(a: dict) -> Path: return store() / a["path"]
def _img_dir(a: dict) -> Path: return store() / "assets" / str(a["course_id"]) / str(a["topic_no"]) / f"{a['id']}_img"

def _read_upload_guard(raw: bytes):
    if not raw: raise HTTPException(400, "Fayl bo'sh")
    if len(raw) > MAX_ASSET: raise HTTPException(413, f"Fayl hajmi {MAX_ASSET // (1024 * 1024)} MB dan oshmasin")

def upload_text(c: Ctx, cid: int, no: int, raw: bytes | None, text: str | None, name: str) -> dict:
    """Ma'ruza matni: .docx / .pdf / .txt yoki joylashtirilgan matn → pk_assets (purpose='matn', meta.text — belgilangan matn)."""
    from . import taqdimot_extract as EX
    co = _course(c, cid, write=True); _check_topic(co, no)
    if raw is not None:
        _read_upload_guard(raw)
        if raw[:4] == b"PK\x03\x04":
            _zip_guard(raw); _ooxml_image_guard(raw, "word/media/")   # .docx: zip/rasm bombasi — tahlildan oldin
        try:
            kind = EX.sniff(raw)
            ex = EX.extract(raw, kind, None)
        except EX.BadFile as e:
            rbac.audit(_con, c, "paket: matn rad etildi", RES, False, f"{name[:60]} · {e}")
            raise HTTPException(415, str(e))
        txt, trunc = EX.as_text([b for b in ex["blocks"] if b.get("k") != "img"], MAX_TEXT_CHARS)
    else:
        txt = (text or "").strip(); kind = "txt"; name = name or "matn.txt"
        trunc = len(txt) > MAX_TEXT_CHARS; txt = txt[:MAX_TEXT_CHARS]
        raw = txt.encode("utf-8")
    if len(txt) < 100: raise HTTPException(400, f"Ma'ruza matni juda qisqa ({len(txt)} belgi)")
    st = structure_text(txt, _topic_title(cid, no))
    aid = _save_asset(c, cid, no, "matn", kind, name, raw, {"text": txt, "chars": len(txt), "truncated": bool(trunc), "plan": st["plan"]})
    with _lock: _log(c, cid, no, "matn yuklandi", f"{name[:80]} · {len(txt)} belgi"); _con.commit()
    rbac.audit(_con, c, "paket: ma'ruza matni yuklandi", RES, True, f"kurs #{cid} · {no}-mavzu · {name[:60]} · {len(txt)} belgi")
    return {"ok": True, "id": aid, "chars": len(txt), "truncated": bool(trunc), "plan": st["plan"]}

def upload_slides(c: Ctx, cid: int, no: int, raw: bytes, name: str) -> dict:
    """Taqdimot: .pptx (tahlil + rasmlar) / .pdf / .png / .jpg (slayd rasmlari to'plami)."""
    co = _course(c, cid, write=True); _check_topic(co, no)
    _read_upload_guard(raw)
    kind = _sniff_asset(raw)
    if kind == "ole": raise HTTPException(415, "Eski .ppt formati qabul qilinmaydi — PowerPoint'da «.pptx» qilib saqlang")
    if kind not in ("pptx", "pdf", "png", "jpg"):
        raise HTTPException(415, "Taqdimot uchun .pptx, .pdf yoki slayd rasmlari (.png, .jpg) qabul qilinadi")
    meta, imgs, parsed = {}, {}, None
    if kind == "pptx":
        parsed = parse_pptx(raw, None, imgs)      # bir marta: avval tekshiruv (buzilgan fayl saqlanmasin), rasmlar xotirada
        meta = {"count": parsed["count"]}
    elif kind == "pdf":
        try:
            from pypdf import PdfReader
            meta = {"pages": len(PdfReader(io.BytesIO(raw)).pages)}
        except Exception:
            raise HTTPException(415, "PDF faylni o'qib bo'lmadi")
    else:
        r = _norm_image(raw, strict=True)
        if not r: raise HTTPException(415, "Rasmni o'qib bo'lmadi yoki juda kichik")
        raw, kind = r
    purpose = "slayd" if kind in ("png", "jpg") else "taqdimot"
    aid = _save_asset(c, cid, no, purpose, kind, name, raw, meta)
    if kind == "pptx":
        a = db.one(_con, "SELECT * FROM pk_assets WHERE id=?", (aid,))
        if imgs:
            d = _img_dir(a); d.mkdir(parents=True, exist_ok=True)
            for fn, b in imgs.items(): (d / fn).write_bytes(b)
        with _lock:
            _con.execute("UPDATE pk_assets SET meta=? WHERE id=?", (json.dumps({"count": parsed["count"], "slides": parsed["slides"]}, ensure_ascii=False), aid))
            _con.commit()
        meta = {"count": parsed["count"], "images": sum(1 for s in parsed["slides"] if s["image"])}
    with _lock: _log(c, cid, no, "taqdimot yuklandi", f"{name[:80]} · {kind}"); _con.commit()
    rbac.audit(_con, c, "paket: taqdimot yuklandi", RES, True, f"kurs #{cid} · {no}-mavzu · {name[:60]} · {kind}")
    return {"ok": True, "id": aid, "kind": kind, **meta}

FILE_KINDS = ("pdf", "docx", "pptx", "xlsx", "png", "jpg")

def upload_file(c: Ctx, cid: int, no: int, raw: bytes, name: str) -> dict:
    co = _course(c, cid, write=True); _check_topic(co, no)
    _read_upload_guard(raw)
    kind = _sniff_asset(raw)
    if kind not in FILE_KINDS: raise HTTPException(415, "Qo'shimcha fayl: .pdf, .docx, .pptx, .xlsx, .png, .jpg")
    aid = _save_asset(c, cid, no, "fayl", kind, name, raw, {})
    with _lock: _log(c, cid, no, "fayl yuklandi", name[:80]); _con.commit()
    rbac.audit(_con, c, "paket: qo'shimcha fayl", RES, True, f"kurs #{cid} · {no}-mavzu · {name[:60]}")
    return {"ok": True, "id": aid, "kind": kind}

def _asset(c: Ctx, aid: int, write=False) -> tuple[dict, dict]:
    a = db.one(_con, "SELECT * FROM pk_assets WHERE id=? AND deleted=0", (int(aid),))
    if not a: raise HTTPException(404, "Fayl topilmadi")
    return a, _course(c, a["course_id"], write)

def delete_asset(c: Ctx, aid: int) -> dict:
    a, _ = _asset(c, aid, write=True)
    with _lock:
        _con.execute("UPDATE pk_assets SET deleted=1 WHERE id=?", (a["id"],))
        _log(c, a["course_id"], a["topic_no"], "fayl o'chirildi", a["name"]); _con.commit()
    try:
        _apath(a).unlink(missing_ok=True); shutil.rmtree(_img_dir(a), ignore_errors=True)
    except OSError:
        pass
    return {"ok": True}

def set_video(c: Ctx, cid: int, no: int, url: str) -> dict:
    co = _course(c, cid, write=True); _check_topic(co, no)
    url = (url or "").strip()
    if url:
        v = parse_video(url)
        if not v["ok"]: raise HTTPException(400, v["error"])
        url = v["url"]
    with _lock:
        _con.execute("""INSERT INTO pk_topics(course_id,topic_no,video_url,video_at,video_by,updated_at) VALUES(?,?,?,?,?,?)
                        ON CONFLICT(course_id,topic_no) DO UPDATE SET video_url=excluded.video_url, video_at=excluded.video_at,
                        video_by=excluded.video_by, updated_at=excluded.updated_at, src=''""",
                     (cid, no, url or None, _now(), c.user["full_name"], _now()))
        _log(c, cid, no, "video", url or "o'chirildi"); _con.commit()
    return {"ok": True, "url": url or None, "video": parse_video(url) if url else None}

def set_deck(c: Ctx, cid: int, no: int, deck_id: int) -> dict:
    co = _course(c, cid, write=True); _check_topic(co, no)
    if deck_id:
        if not any(d["id"] == deck_id for d in decks_for(c, co)): raise HTTPException(404, "Taqdimot topilmadi yoki sizga tegishli emas")
    with _lock:
        _con.execute("""INSERT INTO pk_topics(course_id,topic_no,deck_id,updated_at) VALUES(?,?,?,?)
                        ON CONFLICT(course_id,topic_no) DO UPDATE SET deck_id=excluded.deck_id, updated_at=excluded.updated_at""",
                     (cid, no, deck_id or None, _now()))
        _log(c, cid, no, "taqdimot (modul)", f"deck #{deck_id}" if deck_id else "uzildi"); _con.commit()
    return {"ok": True, "deck_id": deck_id or None}

def set_topic_settings(c: Ctx, cid: int, no: int, s: dict, reset=False) -> dict:
    co = _course(c, cid, write=True); _check_topic(co, no)
    base = defaults()
    eff = _clean_settings(s, base)
    over = {} if reset else {k: v for k, v in eff.items() if v != base.get(k)}
    with _lock:
        _con.execute("""INSERT INTO pk_topics(course_id,topic_no,settings,updated_at) VALUES(?,?,?,?)
                        ON CONFLICT(course_id,topic_no) DO UPDATE SET settings=excluded.settings, updated_at=excluded.updated_at""",
                     (cid, no, json.dumps(over), _now()))
        _log(c, cid, no, "sozlama", json.dumps(over)[:300]); _con.commit()
    return {"ok": True, "settings": topic_settings(cid, no)[0], "override": over}

def decks_for(c: Ctx, co: dict) -> list[dict]:
    """«Taqdimot» modulidagi decklar: o'qituvchi — o'ziniki; bo'lim — kurs o'qituvchisiniki."""
    if not db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='pres_decks'"): return []
    if c.role.key == TEACH: uids = [c.user["id"]]
    else: uids = [r["id"] for r in db.rows(_con, "SELECT id FROM users WHERE teacher_id=?", (co.get("teacher_id") or -1,))]
    if not uids: return []
    return db.rows(_con, f"""SELECT id, title, subject, topic_no, slides, status, updated_at FROM pres_decks WHERE deleted=0 AND outline IS NOT NULL
                             AND user_id IN ({','.join('?' * len(uids))}) ORDER BY updated_at DESC LIMIT 60""", uids)


# =============================================================================================
# Manbalarni yig'ish (gather) va tayyorgarlik
# =============================================================================================
def _latest_asset(cid, no, purpose, kinds=None) -> dict | None:
    """Oxirgi yuklangan fayl (diskda mavjudi; ma'ruza matni — matni bazada bo'lgani uchun fayl shart emas)."""
    w, a = "course_id=? AND topic_no=? AND purpose=? AND deleted=0", [cid, no, purpose]
    if kinds: w += f" AND kind IN ({','.join('?' * len(kinds))})"; a += list(kinds)
    for r in db.rows(_con, f"SELECT * FROM pk_assets WHERE {w} ORDER BY id DESC LIMIT 20", a):
        if purpose == "matn" or _apath(r).is_file(): return r
    return None

def _text_source(cid: int, no: int) -> dict | None:
    a = _latest_asset(cid, no, "matn")
    if a:
        m = json.loads(a["meta"] or "{}")
        return {"src": "paket", "name": a["name"], "kind": a["kind"], "text": m.get("text") or "", "chars": m.get("chars") or 0, "ts": a["ts"],
                "by": _short(a["user_name"]), "asset": a, "demo": a["src"] == "demo"}
    if db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_sources'"):
        s = db.one(_con, "SELECT * FROM tb_sources WHERE course_id=? AND topic_no=? ORDER BY id DESC LIMIT 1", (cid, no))
        if s: return {"src": "testbank", "name": s["name"], "kind": s["kind"], "text": s["text"] or "", "chars": s["chars"], "ts": s["ts"],
                      "by": _short(s["user_name"]), "asset": None, "demo": s["src"] == "demo"}
    return None

def _deck_slides(deck_id: int) -> tuple[list, Path | None, dict | None]:
    from . import taqdimot as TQ
    d = db.one(_con, "SELECT * FROM pres_decks WHERE id=? AND deleted=0", (deck_id,)) if deck_id else None
    if not d or not d["outline"]: return [], None, None
    try: o = json.loads(d["outline"])
    except ValueError: return [], None, d
    out = []
    for s in o.get("slides") or []:
        b = []
        if s.get("text"): b.append(s["text"])
        if s.get("highlight"): b.append(s["highlight"])
        b += list(s.get("bullets") or [])
        for col in s.get("columns") or []: b.append(f"**{col.get('title', '')}**: " + "; ".join(col.get("bullets") or []))
        for st in s.get("steps") or []: b.append(f"{st.get('title', '')} — {st.get('text', '')}".strip(" —"))
        for cd in s.get("cards") or []: b.append(f"{cd.get('title', '')}: {cd.get('text', '')}".strip(": "))
        if s.get("answer"): b.append("Javob: " + s["answer"])
        out.append({"title": (s.get("title") or "")[:300], "bullets": [re.sub(r"\*\*(.+?)\*\*", r"\1", x)[:600] for x in b if x][:30],
                    "notes": (s.get("notes") or "")[:4000], "image": None})
    pptx = TQ.ddir(deck_id) / "taqdimot.pptx"
    return out, (pptx if pptx.is_file() else None), d

def _video_source(cid: int, no: int) -> dict | None:
    tr = _topic_row(cid, no)
    if tr.get("video_url"):
        v = parse_video(tr["video_url"]); return {"src": "paket", "raw": tr["video_url"], "demo": tr.get("src") == "demo", **v}
    it = db.one(_con, "SELECT url FROM dl_items WHERE course_id=? AND topic_no=? AND kind='video' AND url IS NOT NULL AND url!='' ORDER BY id DESC LIMIT 1", (cid, no))
    if it:
        v = parse_video(it["url"]); return {"src": "monitoring", "raw": it["url"], "demo": False, **v}
    return None

def _quiz_rows(cid: int, no: int) -> list[dict]:
    if not db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_questions'"): return []
    return db.rows(_con, "SELECT * FROM tb_questions WHERE course_id=? AND topic_no=? AND status='tasdiqlandi' AND deleted=0 ORDER BY id", (cid, no))

TF_OPTIONS = ["To'g'ri", "Noto'g'ri"]

def _tf_correct(opts: list, corr: list) -> int:
    """To'g'ri/noto'g'ri savolning javobi: 0 — «to'g'ri», 1 — «noto'g'ri» (variant matni bo'yicha; matn noma'lum bo'lsa indeks)."""
    try: i = int((corr or [0])[0])
    except (TypeError, ValueError): i = 0
    txt = str(opts[i] if 0 <= i < len(opts or []) else "").translate(_APOS).strip().lower()
    if txt in ("to'g'ri", "togri", "true", "ha", "верно", "правда"): return 0
    if txt in ("noto'g'ri", "notogri", "false", "yo'q", "неверно", "ложь"): return 1
    return 0 if i == 0 else 1

def _pick_questions(rows: list, n: int, cid: int, no: int) -> list:
    if not n or n >= len(rows): return rows
    rnd = random.Random(f"isft-paket-{cid}-{no}-{n}-{len(rows)}")    # deterministik: manba o'zgarmasa — o'sha savollar
    return sorted(rnd.sample(rows, n), key=lambda r: r["id"])

def _image_slides(cid, no) -> list[dict]:
    imgs = [a for a in db.rows(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='slayd' AND deleted=0", (cid, no)) if _apath(a).is_file()]
    key = lambda a: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", a["name"] or "")] + [a["id"]]
    return sorted(imgs, key=key)

def gather(cid: int, no: int, co: dict | None = None, settings: dict | None = None) -> dict:
    """Mavzu manbalari → {"content" (built/id/v dan tashqari), "files": {zip yo'li: Path|bytes}, "ready": {...}, "settings"}."""
    co = co or db.one(_con, "SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id "
                            "LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.id=?", (cid,))
    if not co: raise HTTPException(404, "Kurs topilmadi")
    st = settings or topic_settings(cid, no)[0]
    on = st["blocks"]
    title = _topic_title(cid, no)
    files: dict[str, object] = {}
    blocks, ready = [], {}
    # matn va reja
    ts = _text_source(cid, no)
    stx = structure_text(ts["text"], title) if ts else {"plan": [], "html": "", "explicit_plan": False}
    ready["text"] = {"ok": bool(ts and stx["html"]), "src": ts["src"] if ts else None, "name": ts["name"] if ts else None,
                     "chars": ts["chars"] if ts else 0, "ts": ts["ts"] if ts else None, "by": ts["by"] if ts else None, "demo": bool(ts and ts["demo"])}
    ready["plan"] = {"ok": bool(stx["plan"]), "n": len(stx["plan"]), "explicit": stx["explicit_plan"], "items": stx["plan"]}
    if on["plan"] and stx["plan"]: blocks.append({"type": "plan", "title": "Reja", "items": stx["plan"]})
    if on["text"] and stx["html"]: blocks.append({"type": "text", "title": "Ma'ruza matni", "html": stx["html"]})
    # taqdimot
    pptx = _latest_asset(cid, no, "taqdimot", ("pptx",))
    pdf = _latest_asset(cid, no, "taqdimot", ("pdf",))
    tr = _topic_row(cid, no)
    slides, ssrc, file_path = [], None, None
    if pptx:
        m = json.loads(pptx["meta"] or "{}")
        idir = _img_dir(pptx)
        for i, s in enumerate(m.get("slides") or [], 1):
            img = None
            if s.get("image") and (idir / s["image"]).is_file():
                ext = s["image"].rsplit(".", 1)[-1]
                img = f"assets/slides/s{i}.{ext}"; files[img] = idir / s["image"]
            slides.append({"title": s.get("title") or "", "bullets": list(s.get("bullets") or []), "notes": s.get("notes") or "", "image": img})
        ssrc, file_path = "pptx", _apath(pptx)
    deck = None
    if not slides and tr.get("deck_id"):
        dsl, dpptx, deck = _deck_slides(int(tr["deck_id"]))
        if dsl:
            slides, ssrc = dsl, "deck"
            if dpptx and not file_path: file_path = dpptx
    if not slides:
        imgs = _image_slides(cid, no)
        for i, a in enumerate(imgs, 1):
            p = f"assets/slides/s{i}.{a['kind']}"; files[p] = _apath(a)
            slides.append({"title": "", "bullets": [], "notes": "", "image": p})
        if imgs: ssrc = "images"
    if not ssrc and pdf: ssrc = "pdf"
    sb = {"type": "slides", "title": "Taqdimot", "slides": slides, "file": None, "pdf": None}
    if file_path: sb["file"] = "assets/taqdimot.pptx"; files["assets/taqdimot.pptx"] = file_path
    if pdf: sb["pdf"] = "assets/taqdimot.pdf"; files["assets/taqdimot.pdf"] = _apath(pdf)
    has_slides = bool(slides or sb["file"] or sb["pdf"])
    ready["slides"] = {"ok": has_slides, "src": ssrc, "n": len(slides), "file": bool(sb["file"]), "pdf": bool(sb["pdf"]),
                       "images": sum(1 for s in slides if s["image"]), "deck_id": tr.get("deck_id"), "deck_title": deck["title"] if deck else None}
    if on["slides"] and has_slides: blocks.append(sb)
    else:
        for k in [k for k in files if k.startswith("assets/slides/") or k in ("assets/taqdimot.pptx", "assets/taqdimot.pdf")]: files.pop(k)
    # video
    v = _video_source(cid, no)
    ready["video"] = {"ok": bool(v and v["ok"]), "src": v["src"] if v else None, "url": (v.get("url") or v.get("raw")) if v else None,
                      "provider": v.get("provider") if v else None, "video_id": v.get("video_id") if v else None,
                      "error": v.get("error") if v and not v["ok"] else None, "demo": bool(v and v.get("demo"))}
    if on["video"] and v and v["ok"]:
        if v["provider"] == "youtube":
            blocks.append({"type": "video", "title": "Videodars", "provider": "youtube", "video_id": v["video_id"], "url": v["url"], "start": v["start"]})
        else:
            blocks.append({"type": "text", "title": "Videodars", "html": sanitize(
                f'<p>Videodars tashqi saytda joylashgan:</p><p><a href="{html.escape(v["url"], quote=True)}">{html.escape(v["url"])}</a></p>')})
    # qo'shimcha fayllar (+ asl ma'ruza fayli)
    extra = db.rows(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='fayl' AND deleted=0 ORDER BY id", (cid, no))
    extra = [a for a in extra if _apath(a).is_file()]
    if ts and ts["asset"] and ts["asset"]["kind"] in ("docx", "pdf") and _apath(ts["asset"]).is_file(): extra = [{**ts["asset"], "name": "Ma'ruza matni (asl fayl)." + ts["asset"]["kind"]}] + extra
    used = set()
    fblocks = []
    for a in extra:
        stem = _ascii(Path(a["name"]).stem, 40).lower()
        nm = f"assets/files/{stem}.{a['kind']}"
        k = 2
        while nm in used: nm = f"assets/files/{stem}_{k}.{a['kind']}"; k += 1
        used.add(nm)
        fblocks.append(({"type": "file", "title": Path(a["name"]).stem[:160] or "Fayl", "href": nm, "size": int(a["size"] or 0)}, nm, _apath(a)))
    ready["files"] = {"ok": bool(fblocks), "n": len(fblocks)}
    if on["files"]:
        for b, nm, p in fblocks: blocks.append(b); files[nm] = p
    # test
    rows = _quiz_rows(cid, no)
    picked = _pick_questions(rows, st["quiz_n"], cid, no)
    ready["quiz"] = {"ok": bool(rows), "approved": len(rows), "used": len(picked)}
    if on["quiz"] and picked:
        qs = []
        for r in picked:
            opts = json.loads(r["options"] or "[]"); corr = json.loads(r["correct"] or "[]"); ans = json.loads(r["answers"] or "[]")
            if r["qtype"] == "tf":     # kontrakt: har doim ["To'g'ri", "Noto'g'ri"], [0] — to'g'ri, [1] — noto'g'ri (bazada qanday saqlangan bo'lmasin)
                opts, corr = list(TF_OPTIONS), [_tf_correct(opts, corr)]
            qs.append({"id": f"q{r['id']}", "type": r["qtype"] if r["qtype"] in ("mcq", "tf", "fill") else "mcq", "stem": r["stem"] or "",
                       "options": opts if r["qtype"] != "fill" else [], "correct": [int(x) for x in corr] if r["qtype"] != "fill" else [],
                       "answers": ans if r["qtype"] == "fill" else [], "explanation": r["explanation"] or ""})
        blocks.append({"type": "quiz", "title": "Test", "pass_pct": st["mastery"], "shuffle": st["shuffle"], "attempts": st["attempts"],
                       "show_feedback": st["show_feedback"], "questions": qs})
    blocks = [{"id": f"b{i}", **b} for i, b in enumerate(blocks, 1)]
    has_quiz = any(b["type"] == "quiz" for b in blocks)
    completion = st["completion"] if has_quiz else "view_all"
    content = {"v": 1, "title": title, "lang": "uz",
               "course": {"subject": co["subject"] or "", "direction": co["direction"] or "", "course": int(co["course"] or 0),
                          "kafedra": co.get("dept") or "", "teacher": _short(co.get("teacher") or "")},
               "topic": {"no": int(no), "title": title},
               "brand": {"name": "ISFT", "full": _brand_full(), "color": BRAND_COLOR, "logo": "assets/logo.png"},
               "blocks": blocks,
               "tracking": {"mode": st["mode"], "completion": completion, "mastery": st["mastery"], "activity_id": f"{ACTIVITY_BASE}/{int(cid)}/{int(no)}"}}
    logo = _logo_path()
    if logo: files["assets/logo.png"] = logo
    else: content["brand"]["logo"] = None
    req = [k for k in REQUIRED if on.get(k)]
    ready["complete"] = all(ready[k]["ok"] for k in req)
    ready["missing"] = [k for k in req if not ready[k]["ok"]]
    ready["blocks"] = len(blocks)
    ready["buildable"] = any(b["type"] in ("text", "slides", "video", "file") for b in blocks)
    return {"content": content, "files": files, "ready": ready, "settings": st, "course": co}

def _brand_full() -> str:
    from . import brand as BR
    return BR.INST.get("full_en") or BR.INST.get("uz") or "ISFT"

def _logo_path() -> Path | None:
    from . import brand as BR
    for p in (BR.BRAND_DIR / "logo.png", BR.BRAND_DIR / "logo-sm.png"):
        if p.is_file(): return p
    return None


# =============================================================================================
# Manifestlar va zip (deterministik)
# =============================================================================================
def _xa(s) -> str: return _xattr(str(s if s is not None else ""))
def _xt(s) -> str: return _xesc(str(s if s is not None else ""))

def content_js(content: dict) -> bytes:
    j = json.dumps(content, ensure_ascii=False, separators=(",", ":")).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return ("window.PAKET = " + j + ";").encode("utf-8")

def _sco_list(scos: list[dict], files: list[str]) -> dict:
    """scos: [{"ident", "title", "href", "prefix", "mastery"|None}] → {prefix: [fayllar]}"""
    out = {}
    for s in scos:
        pre = s["prefix"]
        out[s["ident"]] = sorted(f for f in files if (f.startswith(pre) if pre else True) and f not in ("imsmanifest.xml", "tincan.xml"))
    return out

def manifest_scorm12(ident: str, title: str, scos: list[dict], files: list[str]) -> str:
    fl = _sco_list(scos, files)
    items, res = [], []
    for i, s in enumerate(scos, 1):
        ms = f"\n        <adlcp:masteryscore>{int(s['mastery'])}</adlcp:masteryscore>" if s.get("mastery") is not None else ""
        items.append(f'      <item identifier="ITEM-{i}" identifierref="RES-{i}" isvisible="true">\n        <title>{_xt(s["title"])}</title>{ms}\n      </item>')
        res.append(f'    <resource identifier="RES-{i}" type="webcontent" adlcp:scormtype="sco" href={_xa(s["href"])}>\n' +
                   "".join(f"      <file href={_xa(f)}/>\n" for f in fl[s["ident"]]) + "    </resource>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier={_xa(ident)} version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd http://www.imsglobal.org/xsd/imsmd_rootv1p2p1 imsmd_rootv1p2p1.xsd http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-1">
    <organization identifier="ORG-1">
      <title>{_xt(title)}</title>
{chr(10).join(items)}
    </organization>
  </organizations>
  <resources>
{chr(10).join(res)}
  </resources>
</manifest>
"""

def manifest_scorm2004(ident: str, title: str, scos: list[dict], files: list[str]) -> str:
    fl = _sco_list(scos, files)
    items, res = [], []
    for i, s in enumerate(scos, 1):
        obj = ""
        if s.get("mastery") is not None:
            obj = (f'\n          <imsss:objectives>\n            <imsss:primaryObjective objectiveID="PRIMARYOBJ-{i}" satisfiedByMeasure="true">\n'
                   f'              <imsss:minNormalizedMeasure>{max(0, min(100, int(s["mastery"]))) / 100:.2f}</imsss:minNormalizedMeasure>\n'
                   f'            </imsss:primaryObjective>\n          </imsss:objectives>')
        items.append(f'      <item identifier="ITEM-{i}" identifierref="RES-{i}" isvisible="true">\n        <title>{_xt(s["title"])}</title>\n'
                     f'        <imsss:sequencing>{obj}\n          <imsss:deliveryControls completionSetByContent="true" objectiveSetByContent="true"/>\n'
                     f'        </imsss:sequencing>\n      </item>')
        res.append(f'    <resource identifier="RES-{i}" type="webcontent" adlcp:scormType="sco" href={_xa(s["href"])}>\n' +
                   "".join(f"      <file href={_xa(f)}/>\n" for f in fl[s["ident"]]) + "    </resource>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier={_xa(ident)} version="1"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
  xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"
  xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"
  xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd http://www.adlnet.org/xsd/adlseq_v1p3 adlseq_v1p3.xsd http://www.adlnet.org/xsd/adlnav_v1p3 adlnav_v1p3.xsd http://www.imsglobal.org/xsd/imsss imsss_v1p0.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
  </metadata>
  <organizations default="ORG-1">
    <organization identifier="ORG-1" adlseq:objectivesGlobalToSystem="false">
      <title>{_xt(title)}</title>
{chr(10).join(items)}
      <imsss:sequencing>
        <imsss:controlMode choice="true" flow="true"/>
      </imsss:sequencing>
    </organization>
  </organizations>
  <resources>
{chr(10).join(res)}
  </resources>
</manifest>
"""

def manifest_tincan(acts: list[dict]) -> str:
    """acts: [{"id", "name", "description", "launch"}]"""
    body = "".join(f"""    <activity id={_xa(a['id'])} type="http://adlnet.gov/expapi/activities/course">
      <name lang="uz">{_xt(a['name'])}</name>
      <description lang="uz">{_xt(a['description'])}</description>
      <launch lang="uz">{_xt(a['launch'])}</launch>
    </activity>
""" for a in acts)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<tincan xmlns="http://projecttincan.com/tincan.xsd">
  <activities>
{body}  </activities>
</tincan>
"""

_STORED_EXT = (".png", ".jpg", ".jpeg", ".gif", ".pptx", ".docx", ".xlsx", ".pdf", ".zip", ".woff", ".woff2", ".mp4", ".webp")

def zip_bytes(entries: dict[str, bytes]) -> bytes:
    """Deterministik zip: tartiblangan yozuvlar, qotirilgan vaqt va atributlar."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        for name in sorted(entries):
            zi = zipfile.ZipInfo(name, date_time=FIXED_TS)
            zi.create_system = 3
            zi.external_attr = 0o100644 << 16
            zi.compress_type = zipfile.ZIP_STORED if name.lower().endswith(_STORED_EXT) else zipfile.ZIP_DEFLATED
            z.writestr(zi, entries[name], compresslevel=6 if zi.compress_type == zipfile.ZIP_DEFLATED else None)
    return bio.getvalue()

def player_files(player_dir: Path | None = None) -> dict[str, bytes]:
    pd = Path(player_dir or PLAYER_DIR)
    if not (pd / "index.html").is_file():
        raise HTTPException(503, "Paket pleyeri topilmadi (app/paket_player/index.html) — administratorga murojaat qiling")
    out = {}
    for p in sorted(pd.rglob("*")):
        rel = p.relative_to(pd).as_posix()
        if not p.is_file() or any(part.startswith(".") or part == "__pycache__" for part in rel.split("/")): continue
        if rel in ("content.js", "content.json", "imsmanifest.xml", "tincan.xml"): continue
        out[rel] = p.read_bytes()
    return out

def _read(v) -> bytes: return v if isinstance(v, (bytes, bytearray)) else Path(v).read_bytes()

def _sco_mastery(content: dict):
    t = content.get("tracking") or {}
    return t.get("mastery") if t.get("completion") in ("quiz_pass", "view_and_quiz") and any(b.get("type") == "quiz" for b in content.get("blocks") or []) else None

def build_zip(content: dict, files: dict, mode: str, player_dir: Path | None = None) -> bytes:
    """Bitta mavzu paketi (bayt). Bir xil kirish → bir xil sha256."""
    entries = dict(player_files(player_dir))
    for k, v in files.items(): entries[k] = _read(v)
    content = json.loads(json.dumps(content))
    content.setdefault("tracking", {})["mode"] = mode
    entries["content.js"] = content_js(content)
    entries["content.json"] = json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8")
    ident = re.sub(r"[^A-Za-z0-9_.-]", "-", content.get("id") or "isft-paket")
    names = sorted(entries)
    sco = [{"ident": "SCO-1", "title": content.get("title") or "Mavzu", "href": "index.html", "prefix": "", "mastery": _sco_mastery(content)}]
    if mode == "scorm12": entries["imsmanifest.xml"] = manifest_scorm12(ident, content.get("title") or "", sco, names).encode("utf-8")
    elif mode == "scorm2004": entries["imsmanifest.xml"] = manifest_scorm2004(ident, content.get("title") or "", sco, names).encode("utf-8")
    elif mode == "xapi":
        c = content.get("course") or {}
        entries["tincan.xml"] = manifest_tincan([{"id": content["tracking"]["activity_id"], "name": content.get("title") or "",
                                                 "description": f"{c.get('subject', '')} · {(content.get('topic') or {}).get('no', '')}-mavzu", "launch": "index.html"}]).encode("utf-8")
    elif mode != "none": raise HTTPException(400, "Paket turi noma'lum")
    return zip_bytes(entries)


# =============================================================================================
# Tekshiruv (validator)
# =============================================================================================
_NS12 = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"
_NS04 = "http://www.imsglobal.org/xsd/imscp_v1p1"
_ADL12 = "http://www.adlnet.org/xsd/adlcp_rootv1p2"
_ADL04 = "http://www.adlnet.org/xsd/adlcp_v1p3"
_TC = "http://projecttincan.com/tincan.xsd"
_EXT_SCRIPT_OK = re.compile(r"^https://(www\.)?(youtube\.com|youtube-nocookie\.com)/", re.I)
BLOCK_TYPES = {"plan", "text", "slides", "video", "file", "quiz"}

def _bad_path(n: str) -> bool:
    return n.startswith("/") or "\\" in n or re.match(r"^[A-Za-z]:", n) is not None or any(p in ("..",) for p in n.split("/"))

def _check_content(raw: bytes, base: str, names: set, errors: list, where: str) -> dict | None:
    t = raw.decode("utf-8", "replace").strip()
    if not t.startswith("window.PAKET = ") or not t.endswith(";"):
        errors.append(f"{where}: «window.PAKET = {{...}};» ko'rinishida emas"); return None
    try: c = json.loads(t[len("window.PAKET = "):-1])
    except ValueError as e:
        errors.append(f"{where}: JSON xato ({e})"); return None
    if c.get("v") != 1: errors.append(f"{where}: v != 1")
    for k in ("id", "title", "blocks", "tracking", "course", "topic", "brand"):
        if k not in c: errors.append(f"{where}: «{k}» yo'q")
    refs = []
    if (c.get("brand") or {}).get("logo"): refs.append(c["brand"]["logo"])
    ids = set()
    for b in c.get("blocks") or []:
        if b.get("type") not in BLOCK_TYPES: errors.append(f"{where}: noma'lum blok turi {b.get('type')!r}")
        if b.get("id") in ids: errors.append(f"{where}: blok id takrorlangan {b.get('id')}")
        ids.add(b.get("id"))
        if b.get("type") == "text" and (bad := html_unsafe(b.get("html") or "")):
            errors.append(f"{where}: matn blokida xavfli HTML ({bad})")
        if b.get("type") == "slides":
            refs += [s["image"] for s in b.get("slides") or [] if s.get("image")]
            refs += [b[k] for k in ("file", "pdf") if b.get(k)]
        if b.get("type") == "file": refs.append(b.get("href") or "")
        if b.get("type") == "video" and b.get("provider") == "youtube" and not YT_ID.match(b.get("video_id") or ""):
            errors.append(f"{where}: video ID noto'g'ri")
    for r in refs:
        if not r or _bad_path(r) or re.match(r"^[a-z]+:", r, re.I): errors.append(f"{where}: noto'g'ri yo'l {r!r}"); continue
        if base + r not in names: errors.append(f"{where}: fayl yo'q {r}")
    return c

def validate_zip(data: bytes) -> dict:
    """Paketni tekshirish → {"ok", "errors", "warnings", "mode", "files", "size", "scos"}."""
    errors, warns, root = [], [], None
    out = {"ok": False, "errors": errors, "warnings": warns, "mode": None, "files": 0, "size": len(data), "scos": 0}
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        errors.append("Zip fayl emas"); return out
    with z:
        infos = z.infolist()
        names = {i.filename for i in infos if not i.filename.endswith("/")}
        out["files"] = len(names)
        for n in names:
            if _bad_path(n): errors.append(f"Mutlaq yoki «..» yo'l: {n}")
        if len(data) > MAX_PACKAGE: errors.append(f"Paket hajmi {MAX_PACKAGE // (1024 * 1024)} MB dan katta")
        launches = []
        if "imsmanifest.xml" in names:
            try: root = ET.fromstring(z.read("imsmanifest.xml"))
            except ET.ParseError as e:
                errors.append(f"imsmanifest.xml o'qilmadi: {e}"); root = None
            if root is not None:
                ns = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
                if ns == _NS12: out["mode"], adl, attr = "scorm12", _ADL12, "scormtype"
                elif ns == _NS04: out["mode"], adl, attr = "scorm2004", _ADL04, "scormType"
                else: errors.append(f"imsmanifest.xml: noma'lum nomlar fazosi {ns!r}"); adl = attr = None
                if adl:
                    sv = root.find(f"{{{ns}}}metadata/{{{ns}}}schemaversion")
                    want = "1.2" if out["mode"] == "scorm12" else "2004 4th Edition"
                    if sv is None or (sv.text or "").strip() != want: errors.append(f"schemaversion «{want}» emas")
                    idents = [e.get("identifier") for e in root.iter() if e.get("identifier") is not None]
                    if len(idents) != len(set(idents)): errors.append("Identifikatorlar takrorlangan")
                    for i in idents:
                        if not re.match(r"^[A-Za-z_][A-Za-z0-9_.\-]*$", i or ""): errors.append(f"Identifikator noto'g'ri: {i!r}")
                    res = {r.get("identifier"): r for r in root.iter(f"{{{ns}}}resource")}
                    orgs = root.find(f"{{{ns}}}organizations")
                    if orgs is None or not orgs.findall(f"{{{ns}}}organization"): errors.append("organization yo'q")
                    elif orgs.get("default") not in {o.get("identifier") for o in orgs.findall(f"{{{ns}}}organization")}:
                        errors.append("organizations@default mos emas")
                    listed = set()
                    for it in root.iter(f"{{{ns}}}item"):
                        ref = it.get("identifierref")
                        if ref and ref not in res: errors.append(f"item {it.get('identifier')}: resurs {ref} yo'q")
                    for rid, r in res.items():
                        href = r.get("href")
                        st = r.get(f"{{{adl}}}{attr}")
                        if st not in ("sco", "asset"): errors.append(f"{rid}: adlcp:{attr} yo'q")
                        if href:
                            if href not in names: errors.append(f"{rid}: href {href} zip ichida yo'q")
                            if st == "sco": launches.append(href)
                        for f in r.findall(f"{{{ns}}}file"):
                            fh = f.get("href") or ""
                            listed.add(fh)
                            if _bad_path(fh): errors.append(f"Noto'g'ri file href: {fh}")
                            elif fh not in names: errors.append(f"{rid}: file {fh} zip ichida yo'q")
                    missing = sorted(n for n in names if n not in listed and n != "imsmanifest.xml")
                    if missing: errors.append(f"Manifestda ko'rsatilmagan fayllar: {', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}")
                    out["scos"] = len(launches)
        elif "tincan.xml" in names:
            out["mode"] = "xapi"
            try: root = ET.fromstring(z.read("tincan.xml"))
            except ET.ParseError as e:
                errors.append(f"tincan.xml o'qilmadi: {e}"); root = None
            if root is not None:
                acts = root.findall(f"{{{_TC}}}activities/{{{_TC}}}activity")
                if not acts: errors.append("tincan.xml: activity yo'q")
                ids = [a.get("id") for a in acts]
                if len(ids) != len(set(ids)): errors.append("tincan.xml: activity id takrorlangan")
                for a in acts:
                    if not re.match(r"^https?://", a.get("id") or ""): errors.append("tincan.xml: activity id IRI emas")
                    la = a.find(f"{{{_TC}}}launch")
                    if la is None or not (la.text or "").strip(): errors.append("tincan.xml: launch yo'q")
                    else:
                        launches.append(la.text.strip())
                        if la.text.strip() not in names: errors.append(f"tincan.xml: launch {la.text.strip()} zip ichida yo'q")
                out["scos"] = len(acts)
                out["activities"] = ids
        else:
            out["mode"] = "none"
            launches.append("index.html")
            if "index.html" not in names: errors.append("index.html yo'q")
        if not launches: errors.append("Ishga tushirish fayli yo'q")
        # content.js — har bir ishga tushirish papkasida
        acts_by_base = {}
        for la in launches:
            base = la.rsplit("/", 1)[0] + "/" if "/" in la else ""
            cj = base + "content.js"
            if cj not in names: errors.append(f"{cj} yo'q"); continue
            c = _check_content(z.read(cj), base, names, errors, cj)
            if c: acts_by_base[base] = c
        if out["mode"] == "xapi" and root is not None:
            want = {(c.get("tracking") or {}).get("activity_id") for c in acts_by_base.values()}
            if set(out.get("activities") or []) != want: errors.append("tincan.xml activity id content.js dagi tracking.activity_id bilan mos emas")
        for c in acts_by_base.values():
            m = (c.get("tracking") or {}).get("mode")
            if out["mode"] and m != out["mode"]: errors.append(f"content.js tracking.mode={m!r}, paket — {out['mode']}")
        # tashqi skriptlar
        for n in names:
            if n.lower().endswith((".html", ".htm")):
                t = z.read(n).decode("utf-8", "replace")
                for src in re.findall(r"<script[^>]*\ssrc\s*=\s*[\"']?([^\"'\s>]+)", t, re.I):
                    if re.match(r"^(https?:)?//", src, re.I) and not _EXT_SCRIPT_OK.match(src): errors.append(f"{n}: tashqi skript {src}")
                for href in re.findall(r"<link[^>]*\shref\s*=\s*[\"']?([^\"'\s>]+)", t, re.I):
                    if re.match(r"^(https?:)?//", href, re.I): warns.append(f"{n}: tashqi resurs {href}")
    out["ok"] = not errors
    return out


# =============================================================================================
# Yig'ish (mavzu), versiyalar
# =============================================================================================
def _fingerprint(content: dict, files: dict, mode: str, pf: dict) -> str:
    h = hashlib.sha256()
    h.update(mode.encode()); h.update(json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for k in sorted(files): h.update(k.encode()); h.update(_sha(_read(files[k])).encode())
    for k in sorted(pf): h.update(k.encode()); h.update(_sha(pf[k]).encode())
    return h.hexdigest()

def _pkg_dir(cid: int, no: int) -> Path: return store() / "packages" / str(int(cid)) / str(int(no))

def _prune(cid: int, no: int):
    """Har bir paket turi (SCORM 1.2 / 2004 / xAPI / oddiy) bo'yicha alohida oxirgi KEEP_VERSIONS ta + tasdiqlangan(lar) saqlanadi:
    uch turni ketma-ket yig'ish birinchisini o'chirib yubormasin."""
    rows = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC", (cid, no))
    keep, per = set(), {}
    for r in rows:
        if per.get(r["mode"], 0) < KEEP_VERSIONS: keep.add(r["id"]); per[r["mode"]] = per.get(r["mode"], 0) + 1
    for m in {r["mode"] for r in rows}:
        appr = next((r for r in rows if r["mode"] == m and r["status"] == "tasdiqlandi"), None)
        if appr: keep.add(appr["id"])
    for r in rows:
        if r["id"] in keep: continue
        try: (store() / r["file"]).unlink(missing_ok=True)
        except OSError: pass
        _con.execute("DELETE FROM pk_packages WHERE id=?", (r["id"],))

def _store_package(c: Ctx | None, cid: int, no: int, data: bytes, mode: str, status: str, settings: dict, fp: str, val: dict, ready: dict,
                   version: int, src="") -> int:
    d = _pkg_dir(cid, no); d.mkdir(parents=True, exist_ok=True)
    fn = f"v{version}_{mode}.zip"
    tmp = d / (fn + ".tmp"); tmp.write_bytes(data); os.replace(tmp, d / fn)
    pid = _con.execute("""INSERT INTO pk_packages(course_id,topic_no,version,mode,status,settings,content_hash,built_at,built_by,built_by_name,file,size,
                          sha256,validation,readiness,src) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (cid, no, version, mode, status, json.dumps(settings), fp, _now(), c.user["id"] if c else None,
                        c.user["full_name"] if c else "Tizim", str(Path("packages") / str(cid) / str(no) / fn), len(data), _sha(data),
                        json.dumps(val, ensure_ascii=False), json.dumps(ready, ensure_ascii=False), src)).lastrowid
    return pid

def build_topic(c: Ctx | None, cid: int, no: int, mode: str | None = None, force: bool = False, src: str = "") -> dict:
    """Mavzu paketini yig'ish → {ok, package, unchanged, validation}. c=None — tizim (demo)."""
    co = _course(c, cid, write=True) if c else db.one(_con, "SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d "
                                                         "ON d.id=c.department_id LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.id=?", (cid,))
    if not co: raise HTTPException(404, "Kurs topilmadi")
    _check_topic(co, no)
    st = topic_settings(cid, no)[0]
    if mode:
        if mode not in MODES: raise HTTPException(400, "Paket turi noma'lum")
        st["mode"] = mode
    g = gather(cid, no, co, st)
    if not g["ready"]["buildable"]:
        raise HTTPException(400, "Paket uchun kamida bitta kontent bloki kerak: ma'ruza matni, taqdimot yoki video")
    pf = player_files()
    fp = _fingerprint(g["content"], g["files"], st["mode"], pf)
    with _lock:
        last = db.one(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC LIMIT 1", (cid, no))
        same = db.one(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? AND mode=? ORDER BY version DESC LIMIT 1", (cid, no, st["mode"]))
        if same and not force and same["content_hash"] == fp and (store() / same["file"]).is_file():   # shu tur bo'yicha (boshqa tur yig'ilgan bo'lsa ham)
            return {"ok": True, "unchanged": True, "package": pack_row(same)}
        version = (last["version"] if last else 0) + 1
        content = {"v": 1, "id": f"isft-{int(cid)}-{int(no)}-v{version}", **{k: v for k, v in g["content"].items() if k != "v"}, "built": _now()}
        content = {k: content[k] for k in ("v", "id", "title", "lang", "course", "topic", "brand", "built", "blocks", "tracking")}
        data = build_zip(content, g["files"], st["mode"])
        val = validate_zip(data)
        if not val["ok"]:
            _log(c, cid, no, "yig'ish xatosi", "; ".join(val["errors"])[:400]); _con.commit()
            if c: rbac.audit(_con, c, "paket: tekshiruvdan o'tmadi", RES, True, f"kurs #{cid} · {no}-mavzu · {val['errors'][:2]}")
            raise HTTPException(422, "Paket tekshiruvdan o'tmadi: " + "; ".join(val["errors"][:3]))
        status = "tayyor" if g["ready"]["complete"] else "qoralama"
        pid = _store_package(c, cid, no, data, st["mode"], status, st, fp, val, {k: (v["ok"] if isinstance(v, dict) else v) for k, v in g["ready"].items()},
                             version, src)
        _log(c, cid, no, "yig'ildi", f"v{version} · {MODES[st['mode']]} · {status}", pid)
        _prune(cid, no)
        _con.commit()
    if c: rbac.audit(_con, c, "paket: yig'ildi", RES, True, f"kurs #{cid} · {no}-mavzu · v{version} · {st['mode']} · {len(data)} bayt")
    return {"ok": True, "unchanged": False, "package": pack_row(db.one(_con, "SELECT * FROM pk_packages WHERE id=?", (pid,))), "validation": val}

def build_course(c: Ctx, cid: int, mode: str = "scorm12", only_approved: bool = False) -> dict:
    """«Kurs paketi»: bitta manifest, har mavzu — alohida SCO (tNN/ papkasida). Mavzular — oxirgi tasdiqlangan (yoki oxirgi) mavzu paketidan."""
    co = _course(c, cid, write=True)
    if mode not in ("scorm12", "scorm2004", "xapi"): raise HTTPException(400, "Kurs paketi: SCORM 1.2, SCORM 2004 yoki xAPI")
    n = int(co["topics"] or 15)
    entries, scos, acts, used = {}, [], [], []
    for no in range(1, n + 1):
        rows = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC", (cid, no))
        pick = next((r for r in rows if r["status"] == "tasdiqlandi"), None) or (None if only_approved else (rows[0] if rows else None))
        if not pick or not (store() / pick["file"]).is_file(): continue
        pre = f"t{no:02d}/"
        with zipfile.ZipFile(store() / pick["file"]) as z:
            for nm in z.namelist():
                if nm.endswith("/") or nm in ("imsmanifest.xml", "tincan.xml"): continue
                entries[pre + nm] = z.read(nm)
        t = entries[pre + "content.js"].decode("utf-8")
        cj = json.loads(t[len("window.PAKET = "):-1])
        cj["tracking"]["mode"] = mode
        entries[pre + "content.js"] = content_js(cj)
        entries[pre + "content.json"] = json.dumps(cj, ensure_ascii=False, indent=1).encode("utf-8")
        title = f"{no}. {cj.get('title') or ''}"
        scos.append({"ident": f"SCO-{no}", "title": title, "href": pre + "index.html", "prefix": pre, "mastery": _sco_mastery(cj)})
        acts.append({"id": cj["tracking"]["activity_id"], "name": title, "description": co["subject"] or "", "launch": pre + "index.html"})
        used.append({"no": no, "version": pick["version"], "status": pick["status"]})
    if not scos: raise HTTPException(400, "Kursda yig'ilgan mavzu paketi yo'q" + (" (tasdiqlangan)" if only_approved else ""))
    title = f"{co['subject']} ({co['direction']}, {co['course']}-kurs)"
    with _lock:
        last = db.one(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=0 ORDER BY version DESC LIMIT 1", (cid,))
        version = (last["version"] if last else 0) + 1
        ident = f"isft-{int(cid)}-kurs-v{version}"
        names = sorted(entries)
        if mode == "scorm12": entries["imsmanifest.xml"] = manifest_scorm12(ident, title, scos, names).encode("utf-8")
        elif mode == "scorm2004": entries["imsmanifest.xml"] = manifest_scorm2004(ident, title, scos, names).encode("utf-8")
        else: entries["tincan.xml"] = manifest_tincan(acts).encode("utf-8")
        data = zip_bytes(entries)
        val = validate_zip(data)
        if not val["ok"]: raise HTTPException(500, "Kurs paketi tekshiruvdan o'tmadi: " + "; ".join(val["errors"][:3]))
        pid = _store_package(c, cid, 0, data, mode, "tayyor", {"mode": mode, "only_approved": only_approved, "topics": used}, _sha(data), val,
                             {"topics": len(used)}, version)
        _log(c, cid, 0, "kurs paketi", f"v{version} · {mode} · {len(used)} mavzu", pid)
        _prune(cid, 0)
        _con.commit()
    rbac.audit(_con, c, "paket: kurs paketi", RES, True, f"kurs #{cid} · {mode} · {len(used)} mavzu")
    return {"ok": True, "package": pack_row(db.one(_con, "SELECT * FROM pk_packages WHERE id=?", (pid,))), "topics": used, "validation": val}

def pack_row(r: dict) -> dict:
    if not r: return None
    v = json.loads(r["validation"] or "{}")
    return {"id": r["id"], "course_id": r["course_id"], "topic_no": r["topic_no"], "version": r["version"], "mode": r["mode"], "mode_label": MODES.get(r["mode"], r["mode"]),
            "status": r["status"], "built_at": r["built_at"], "by": _short(r["built_by_name"]), "size": r["size"], "sha256": r["sha256"],
            "approved_name": _short(r["approved_name"]), "approved_at": r["approved_at"], "note": r["note"], "demo": r["src"] == "demo",
            "valid": bool(v.get("ok")), "warnings": v.get("warnings") or [], "files": v.get("files"),
            "readiness": json.loads(r["readiness"] or "{}"), "settings": json.loads(r["settings"] or "{}")}

def _package(c: Ctx, pid: int) -> tuple[dict, dict]:
    r = db.one(_con, "SELECT * FROM pk_packages WHERE id=?", (int(pid),))
    if not r: raise HTTPException(404, "Paket topilmadi")
    return r, _course(c, r["course_id"])

def package_action(c: Ctx, pid: int, action: str, note: str = "") -> dict:
    r, co = _package(c, pid)
    if action == "approve":
        if r["status"] != "tayyor": raise HTTPException(409, "Faqat «tayyor» paket tasdiqlanadi (manbalar to'liq bo'lishi kerak)")
        with _lock:
            _con.execute("UPDATE pk_packages SET status='tasdiqlandi', approved_by=?, approved_name=?, approved_at=?, note=NULL WHERE id=?",
                         (c.user["id"], c.user["full_name"], _now(), r["id"]))
            _log(c, r["course_id"], r["topic_no"], "tasdiqlandi", f"v{r['version']}", r["id"]); _con.commit()
    elif action == "reject":
        if len(note.strip()) < 3: raise HTTPException(400, "Qaytarish sababini yozing")
        with _lock:
            _con.execute("UPDATE pk_packages SET status='qoralama', note=?, approved_by=NULL, approved_name=NULL, approved_at=NULL WHERE id=?", (note.strip()[:500], r["id"]))
            _log(c, r["course_id"], r["topic_no"], "qaytarildi", note, r["id"]); _con.commit()
    else:
        raise HTTPException(400, "Amal noma'lum")
    return {"ok": True, "package": pack_row(db.one(_con, "SELECT * FROM pk_packages WHERE id=?", (r["id"],)))}

def download_name(co: dict, no: int, mode: str) -> str:
    return f"ISFT_{_ascii(co['subject'], 50)}_{'kurs' if not no else '%02d' % int(no)}_{mode}.zip"


# =============================================================================================
# Ko'rish (preview) — saqlangan zip ichidan, qat'iy CSP bilan
# =============================================================================================
# sandbox (allow-same-origin YO'Q): paket ilova origin'idan ajratiladi (opaque origin "null") — iframe'da ham, «yangi oynada» ochilganda ham
# sessiya cookie, /api va ota sahifa DOM'iga kira olmaydi. Pleyerga faqat o'z skripti kerak ('self'); YouTube — faqat frame-src (nocookie embed).
PREVIEW_CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://i.ytimg.com; "
               "font-src 'self' data:; media-src 'self'; connect-src 'none'; frame-src https://www.youtube-nocookie.com; object-src 'none'; "
               "base-uri 'none'; form-action 'none'; frame-ancestors 'self'; "
               "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms")
_CT = {"html": "text/html; charset=utf-8", "htm": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8",
       "json": "application/json; charset=utf-8", "xml": "application/xml; charset=utf-8", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
       "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp", "ico": "image/x-icon", "pdf": "application/pdf", "woff": "font/woff", "woff2": "font/woff2",
       "txt": "text/plain; charset=utf-8", "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
       "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

# Sandbox'dagi (opaque origin) hujjatning ichki so'rovlari (content.js, player.js, rasmlar) SameSite sessiya cookie'sini yubormaydi —
# shuning uchun ko'rish cookie bilan ochiladi (ruxsat + audit), so'ng qisqa muddatli imzolangan yo'lga yo'naltiriladi:
#   /api/paket/packages/{pid}/preview/<yo'l>  →  302  →  /api/paket/pv/<pid.uid.muddat.imzo>/<yo'l>
# Token faqat shu paket va shu foydalanuvchi uchun (HMAC, kalit pk_meta'da), har so'rovda foydalanuvchi faolligi va ko'lami qayta tekshiriladi.
PV_TTL = 2 * 3600
_pv_key_cache: bytes | None = None

def _pv_key() -> bytes:
    global _pv_key_cache
    if _pv_key_cache is None:
        with _lock:
            _con.execute("INSERT OR IGNORE INTO pk_meta(k,v) VALUES('pv_key', ?)", (secrets.token_hex(32),)); _con.commit()
            _pv_key_cache = bytes.fromhex(db.one(_con, "SELECT v FROM pk_meta WHERE k='pv_key'")["v"])
    return _pv_key_cache

def preview_token(pid: int, uid: int, exp: int | None = None) -> str:
    msg = f"{int(pid)}.{int(uid)}.{int(exp or time.time() + PV_TTL)}"
    return msg + "." + hmac.new(_pv_key(), msg.encode(), hashlib.sha256).hexdigest()[:40]

def preview_ctx(token: str) -> tuple[Ctx, int]:
    bad = HTTPException(403, "Ko'rish havolasi yaroqsiz yoki muddati o'tgan — paketni qayta oching")
    m = re.fullmatch(r"(\d{1,10})\.(\d{1,10})\.(\d{1,12})\.([0-9a-f]{40})", token or "")
    if not m: raise bad
    msg = f"{m[1]}.{m[2]}.{m[3]}"
    if not hmac.compare_digest(hmac.new(_pv_key(), msg.encode(), hashlib.sha256).hexdigest()[:40], m[4]) or int(m[3]) < time.time(): raise bad
    try: c = rbac.ctx_for(_con, int(m[2]))
    except AccessDenied: raise bad
    if c.user.get("active") == 0 or c.role.legacy or c.role.key not in WORK: raise bad
    return c, int(m[1])

def _preview_path(c: Ctx, pid: int, path: str) -> str:
    path = (path or "index.html").strip() or "index.html"
    if path.endswith("/"): path += "index.html"
    if _bad_path(path) or "\x00" in path or "%" in path:
        rbac.audit(_con, c, "paket: noto'g'ri preview yo'li", RES, False, f"#{pid} · {path[:80]}")
        raise HTTPException(400, "Yo'l noto'g'ri")
    return path

def preview_redirect(c: Ctx, pid: int, path: str) -> Response:
    _package(c, pid)                                     # ko'lam (begona kurs — 403 + audit)
    path = _preview_path(c, pid, path)
    return RedirectResponse(f"{P}/pv/{preview_token(pid, c.user['id'])}/{quote(path, safe='/')}", 302,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

def preview_file(c: Ctx, pid: int, path: str) -> Response:
    r, _ = _package(c, pid)
    path = _preview_path(c, pid, path)
    f = store() / r["file"]
    if not f.is_file(): raise HTTPException(410, "Paket fayli saqlanmagan (eski versiya o'chirilgan)")
    with zipfile.ZipFile(f) as z:
        try: data = z.read(path)
        except KeyError: raise HTTPException(404, "Paket ichida bunday fayl yo'q")
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return Response(data, media_type=_CT.get(ext, "application/octet-stream"),
                    headers={"Content-Security-Policy": PREVIEW_CSP, "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60",
                             "Referrer-Policy": "no-referrer"})


# =============================================================================================
# Qamrov va kurs ko'rinishi
# =============================================================================================
def readiness_map() -> dict:
    """{(cid, no): {"text", "slides", "video", "quiz"}} — butun institut bo'yicha, tez (matn tahlilisiz)."""
    out = {}
    def mark(k, cid, no):
        out.setdefault((cid, no), {"text": False, "slides": False, "video": False, "quiz": False})[k] = True
    has = lambda t: bool(db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)))
    if has("tb_sources"):
        for r in db.rows(_con, "SELECT DISTINCT course_id, topic_no FROM tb_sources"): mark("text", r["course_id"], r["topic_no"])
    for r in db.rows(_con, "SELECT DISTINCT course_id, topic_no, purpose FROM pk_assets WHERE deleted=0 AND purpose IN ('matn','taqdimot','slayd')"):
        mark("text" if r["purpose"] == "matn" else "slides", r["course_id"], r["topic_no"])
    vids = {}
    for r in db.rows(_con, "SELECT course_id, topic_no, url FROM dl_items WHERE kind='video' AND url IS NOT NULL AND url!=''"): vids[(r["course_id"], r["topic_no"])] = r["url"]
    for r in db.rows(_con, "SELECT course_id, topic_no, video_url, deck_id FROM pk_topics"):
        if r["video_url"]: vids[(r["course_id"], r["topic_no"])] = r["video_url"]
        if r["deck_id"]: mark("slides", r["course_id"], r["topic_no"])
    for k, u in vids.items():
        if parse_video(u)["ok"]: mark("video", *k)
    if has("tb_questions"):
        for r in db.rows(_con, "SELECT DISTINCT course_id, topic_no FROM tb_questions WHERE status='tasdiqlandi' AND deleted=0"): mark("quiz", r["course_id"], r["topic_no"])
    return out

def _pkg_map() -> dict:
    """{(cid, no): {"built": oxirgi versiya qatori, "approved": bool}} (topic_no > 0)."""
    out = {}
    for r in db.rows(_con, "SELECT id, course_id, topic_no, version, status, mode, built_at FROM pk_packages WHERE topic_no>0 ORDER BY version"):
        k = (r["course_id"], r["topic_no"])
        e = out.setdefault(k, {"last": None, "approved": False})
        e["last"] = r
        if r["status"] == "tasdiqlandi": e["approved"] = True
    return out

def course_rows(c: Ctx) -> list[dict]:
    sw, sa = scope(c)
    courses = db.rows(_con, f"""SELECT c.id, c.subject, c.direction, c.course, c.department_id, c.teacher_id, c.topics, d.name dept, t.full_name teacher
                                FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id LEFT JOIN teachers t ON t.id=c.teacher_id WHERE {sw}""", sa)
    rd, pk = readiness_map(), _pkg_map()
    out = []
    for co in courses:
        n = int(co["topics"] or 15)
        row = {**co, "teacher": _short(co["teacher"]), "built": 0, "approved": 0, "waiting": 0, "text": 0, "slides": 0, "video": 0, "quiz": 0, "full": 0}
        for no in range(1, n + 1):
            r = rd.get((co["id"], no)) or {}
            for k in ("text", "slides", "video", "quiz"): row[k] += bool(r.get(k))
            row["full"] += all(r.get(k) for k in ("text", "slides", "video", "quiz"))
            p = pk.get((co["id"], no))
            if p:
                row["built"] += 1; row["approved"] += p["approved"]
                row["waiting"] += p["last"]["status"] == "tayyor"
        row["pct"] = _pct(row["approved"], n); row["built_pct"] = _pct(row["built"], n)
        row["started"] = bool(row["built"] or row["text"] or row["slides"] or row["quiz"])
        out.append(row)
    return out

def coverage(c: Ctx) -> dict:
    rows = course_rows(c)
    F = ("built", "approved", "waiting", "text", "slides", "video", "quiz", "full")
    def agg(key, label):
        out = {}
        for r in rows:
            a = out.setdefault(key(r), {**label(r), "courses": 0, "started": 0, "topics": 0, **{f: 0 for f in F}})
            a["courses"] += 1; a["started"] += r["started"]; a["topics"] += int(r["topics"] or 15)
            for f in F: a[f] += r[f]
        for a in out.values(): a["pct"] = _pct(a["approved"], a["topics"]); a["built_pct"] = _pct(a["built"], a["topics"])
        return sorted(out.values(), key=lambda a: (a["built_pct"] or 0, -a["topics"]))
    tot = {"courses": len(rows), "started": sum(r["started"] for r in rows), "topics": sum(int(r["topics"] or 15) for r in rows)}
    for f in F: tot[f] = sum(r[f] for r in rows)
    tot["pct"] = _pct(tot["approved"], tot["topics"]); tot["built_pct"] = _pct(tot["built"], tot["topics"])
    return {"total": tot,
            "departments": agg(lambda r: r["department_id"], lambda r: {"department_id": r["department_id"], "name": r["dept"] or "—"}),
            "teachers": agg(lambda r: r["teacher_id"], lambda r: {"teacher_id": r["teacher_id"], "name": r["teacher"] or "—", "dept": r["dept"]}) if c.role.key != TEACH else []}

def course_view(c: Ctx, cid: int) -> dict:
    co = _course(c, cid)
    n = int(co["topics"] or 15)
    rd, pk = readiness_map(), _pkg_map()
    titles = _titles(cid)
    topics = []
    for no in range(1, n + 1):
        r = rd.get((cid, no)) or {}
        p = pk.get((cid, no))
        topics.append({"no": no, "title": _topic_title(cid, no, titles), **{k: bool(r.get(k)) for k in ("text", "slides", "video", "quiz")},
                       "last": {"id": p["last"]["id"], "version": p["last"]["version"], "status": p["last"]["status"], "mode": p["last"]["mode"],
                                "built_at": p["last"]["built_at"]} if p else None, "approved": bool(p and p["approved"])})
    k = c.role.key
    own = k in DEPT or (k == TEACH and co.get("teacher_id") == _teacher_id(c))
    cp = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=0 ORDER BY version DESC", (cid,))
    return {"course": {"id": co["id"], "subject": co["subject"], "direction": co["direction"], "course": co["course"], "dept": co["dept"],
                       "teacher": _short(co["teacher"]), "topics": n},
            "topics": topics, "course_packages": [pack_row(r) for r in cp], "can": {"write": own, "approve": k in DEPT}}

def topic_view(c: Ctx, cid: int, no: int) -> dict:
    co = _course(c, cid); _check_topic(co, no)
    st, over = topic_settings(cid, no)
    g = gather(cid, no, co, st)
    ts = _text_source(cid, no)
    text_html = next((b["html"] for b in g["content"]["blocks"] if b["type"] == "text" and b["title"] == "Ma'ruza matni"), "")
    if not text_html and ts: text_html = structure_text(ts["text"], g["content"]["title"])["html"]
    assets = db.rows(_con, "SELECT id, purpose, kind, name, size, ts, user_name, src FROM pk_assets WHERE course_id=? AND topic_no=? AND deleted=0 ORDER BY id DESC", (cid, no))
    pk = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC", (cid, no))
    slides_b = next((b for b in g["content"]["blocks"] if b["type"] == "slides"), None)
    quiz_b = next((b for b in g["content"]["blocks"] if b["type"] == "quiz"), None)
    k = c.role.key
    own = k in DEPT or (k == TEACH and co.get("teacher_id") == _teacher_id(c))
    return {"course": {"id": co["id"], "subject": co["subject"], "direction": co["direction"], "course": co["course"], "topics": int(co["topics"] or 15)},
            "topic": {"no": no, "title": g["content"]["title"]}, "ready": g["ready"], "settings": st, "override": over,
            "text_html": text_html[:150_000], "plan": g["ready"]["plan"]["items"],
            "slides": [{"title": s["title"], "bullets": s["bullets"][:6], "notes": bool(s["notes"]), "image": bool(s["image"])} for s in (slides_b or {}).get("slides", [])[:60]],
            "quiz_preview": [{"type": q["type"], "stem": q["stem"]} for q in (quiz_b or {}).get("questions", [])[:50]],
            "assets": [{**a, "user_name": _short(a["user_name"]), "demo": a["src"] == "demo"} for a in assets],
            "packages": [pack_row(r) for r in pk], "decks": decks_for(c, co) if own else [],
            "blocks": [{"type": b["type"], "title": b["title"]} for b in g["content"]["blocks"]],
            "can": {"write": own, "approve": k in DEPT}}


# =============================================================================================
# Avtomatik joylash: video havolalar va ommaviy yig'ish
# =============================================================================================
def bulk_videos(c: Ctx, cid: int, text: str, apply: bool) -> dict:
    co = _course(c, cid, write=True)
    rows = parse_bulk(text, int(co["topics"] or 15))
    good = [r for r in rows if r.get("ok")]
    if apply and good:
        with _lock:
            for r in good:
                _con.execute("""INSERT INTO pk_topics(course_id,topic_no,video_url,video_at,video_by,updated_at) VALUES(?,?,?,?,?,?)
                                ON CONFLICT(course_id,topic_no) DO UPDATE SET video_url=excluded.video_url, video_at=excluded.video_at,
                                video_by=excluded.video_by, updated_at=excluded.updated_at, src=''""",
                             (cid, r["topic_no"], r["video"]["url"], _now(), c.user["full_name"], _now()))
            _log(c, cid, None, "videolar (ommaviy)", f"{len(good)} ta mavzu"); _con.commit()
        rbac.audit(_con, c, "paket: videolar joylandi", RES, True, f"kurs #{cid} · {len(good)} ta")
    titles = _titles(cid)
    return {"ok": True, "applied": bool(apply and good), "assigned": len(good) if apply else 0, "errors": sum(1 for r in rows if not r.get("ok")),
            "rows": [{"line": r["line"], "topic_no": r["topic_no"], "title": _topic_title(cid, r["topic_no"], titles) if 1 <= r["topic_no"] <= int(co["topics"] or 15) else "",
                      "url": r["url"], "ok": bool(r.get("ok")), "error": r.get("error") or "", "video_id": (r.get("video") or {}).get("video_id"),
                      "provider": (r.get("video") or {}).get("provider")} for r in rows]}

def bulk_build(c: Ctx, cid: int, topics: list[int] | None, mode: str | None, only_complete: bool) -> dict:
    co = _course(c, cid, write=True)
    n = int(co["topics"] or 15)
    nos = sorted({int(t) for t in (topics or range(1, n + 1)) if 1 <= int(t) <= n})
    res = []
    for no in nos:
        try:
            g = gather(cid, no, co)
            if not g["ready"]["buildable"]: res.append({"no": no, "ok": False, "skipped": True, "error": "manba yo'q"}); continue
            if only_complete and not g["ready"]["complete"]:
                res.append({"no": no, "ok": False, "skipped": True, "error": "to'liq emas: " + ", ".join(BLOCKS[k] for k in g["ready"]["missing"])}); continue
            r = build_topic(c, cid, no, mode)
            res.append({"no": no, "ok": True, "unchanged": r["unchanged"], "version": r["package"]["version"], "status": r["package"]["status"]})
        except HTTPException as e:
            res.append({"no": no, "ok": False, "error": str(e.detail)})
    return {"ok": True, "built": sum(1 for r in res if r["ok"] and not r.get("unchanged")), "unchanged": sum(1 for r in res if r.get("unchanged")),
            "skipped": sum(1 for r in res if r.get("skipped")), "failed": sum(1 for r in res if not r["ok"] and not r.get("skipped")), "results": res}


# =============================================================================================
# «Mening vazifalarim» (app/pending.py)
# =============================================================================================
def pending(c: Ctx) -> list[dict]:
    k = c.role.key
    out = []
    try:
        if k in DEPT:
            r = db.one(_con, """SELECT COUNT(*) n, COUNT(DISTINCT p.course_id) nc FROM pk_packages p WHERE p.topic_no>0 AND p.status='tayyor'
                                AND p.version=(SELECT MAX(version) FROM pk_packages x WHERE x.course_id=p.course_id AND x.topic_no=p.topic_no)""")
            if r and r["n"]:
                out.append({"id": "approve", "kind": "ish", "title": f"Kontent paketlari: tasdiqni kutayotgan paketlar — {r['n']} ta",
                            "sub": f"{r['nc']} ta kursda · ko'rib, tasdiqlash yoki qaytarish kerak", "view": "paket", "tab": "mavzular"})
        elif k == TEACH and _teacher_id(c):
            r = db.one(_con, """SELECT COUNT(*) n FROM pk_packages p JOIN dl_courses c ON c.id=p.course_id WHERE c.teacher_id=? AND p.topic_no>0
                                AND p.status='qoralama' AND p.note IS NOT NULL
                                AND p.version=(SELECT MAX(version) FROM pk_packages x WHERE x.course_id=p.course_id AND x.topic_no=p.topic_no)""", (_teacher_id(c),))
            if r and r["n"]:
                out.append({"id": "returned", "kind": "ish", "title": f"Kontent paketlari: qaytarilgan paketlar — {r['n']} ta",
                            "sub": "izohni ko'rib, manbani tuzating va qayta yig'ing", "view": "paket", "tab": "mavzular"})
    except Exception as e:
        print("paket.pending:", repr(e))
    return out


# =============================================================================================
# API
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi")
    k = c.role.key
    tabs = ["qamrov", "mavzular", "joylash", "sozlama"] if k in AUTHORS else ["qamrov", "mavzular"] if k == KAF else ["qamrov"]
    sw, sa = scope(c)
    demo = bool(db.one(_con, f"""SELECT 1 x FROM dl_courses c WHERE {sw} AND (EXISTS(SELECT 1 FROM pk_packages p WHERE p.course_id=c.id AND p.src='demo')
                                 OR EXISTS(SELECT 1 FROM pk_assets a WHERE a.course_id=c.id AND a.src='demo' AND a.deleted=0)) LIMIT 1""", sa))
    return {"role": k, "tabs": tabs, "today": clock.today().isoformat(), "demo": demo, "player": player_ok(),
            "modes": MODES, "completion": COMPLETION, "status": STATUS, "blocks": BLOCKS, "required": list(REQUIRED), "defaults": defaults(),
            "limits": {"asset_mb": MAX_ASSET // (1024 * 1024), "package_mb": MAX_PACKAGE // (1024 * 1024), "keep": KEEP_VERSIONS},
            "caps": {"write": k in AUTHORS, "build": k in AUTHORS, "approve": k in DEPT, "settings": k in DEPT, "view": k in WORK, "download": k in WORK},
            "scope": ("O'z kafedrangiz kurslari (ko'rish va yuklab olish)" if k == KAF else "O'z kurslaringiz" if k == TEACH else
                      "Jamlangan qamrov" if k in LEAD else "Masofaviy ta'lim — barcha kurslar")}

@router.get(P + "/coverage")
def api_coverage(request: Request):
    c = C(request); guard(c, "qamrov")
    return coverage(c)

@router.get(P + "/courses")
def api_courses(request: Request, q: str = "", department_id: int = 0, teacher_id: int = 0, only: str = "", offset: int = 0, limit: int = 50):
    c = C(request); guard(c, "kurslar ro'yxati", WORK, f"{q[:30]}/{department_id}/{only}")
    rows = course_rows(c)
    if department_id: rows = [r for r in rows if r["department_id"] == department_id]
    if teacher_id: rows = [r for r in rows if r["teacher_id"] == teacher_id]
    if only == "started": rows = [r for r in rows if r["started"]]
    elif only == "waiting": rows = [r for r in rows if r["waiting"]]
    elif only == "empty": rows = [r for r in rows if not r["started"]]
    if q:
        ql = q.lower().strip()
        rows = [r for r in rows if ql in f"{r['subject']} {r['direction']} {r['teacher']} {r['dept']}".lower()]
    rows.sort(key=lambda r: (not r["started"], -r["waiting"], r["subject"] or "", r["direction"] or "", r["course"] or 0))
    limit = max(1, min(400, limit))
    return {"total": len(rows), "items": rows[max(0, offset):max(0, offset) + limit]}

@router.get(P + "/courses/{cid}")
def api_course(cid: int, request: Request):
    c = C(request); guard(c, "kurs", WORK, f"kurs #{cid}")
    return course_view(c, cid)

@router.get(P + "/courses/{cid}/topics/{no}")
def api_topic(cid: int, no: int, request: Request):
    c = C(request); guard(c, "mavzu", WORK, f"kurs #{cid} · {no}-mavzu")
    return topic_view(c, cid, no)

def _len_guard(request: Request):
    try: n = int(request.headers.get("content-length") or 0)
    except ValueError: n = 0
    if n > MAX_ASSET: raise HTTPException(413, f"Fayl hajmi {MAX_ASSET // (1024 * 1024)} MB dan oshmasin")

async def _read_body(request: Request, limit: int = MAX_ASSET) -> bytes:
    """Yuklangan fayl tanasi — oqim bilan, hisoblagich bilan: Content-Length bo'lmasa (chunked) yoki yolg'on bo'lsa ham
    chegaradan oshgan zahoti 413 (butun tana xotiraga o'qilmaydi)."""
    _len_guard(request)
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit: raise HTTPException(413, f"Fayl hajmi {limit // (1024 * 1024)} MB dan oshmasin")
    return bytes(buf)

@router.post(P + "/courses/{cid}/topics/{no}/text")
async def api_text_upload(cid: int, no: int, request: Request, name: str = "material"):
    c = C(request); guard(c, "ma'ruza matni yuklash", AUTHORS, f"kurs #{cid} · {no}-mavzu · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_text, c, cid, no, raw, None, name[:160])

class TextIn(BaseModel):
    text: str = Field(..., max_length=MAX_TEXT_CHARS * 2)
    name: str = Field("", max_length=160)

@router.post(P + "/courses/{cid}/topics/{no}/text/paste")
def api_text_paste(cid: int, no: int, body: TextIn, request: Request):
    c = C(request); guard(c, "ma'ruza matni (matn)", AUTHORS, f"kurs #{cid} · {no}-mavzu")
    return upload_text(c, cid, no, None, body.text, body.name or f"{no}-mavzu matni.txt")

@router.post(P + "/courses/{cid}/topics/{no}/slides")
async def api_slides_upload(cid: int, no: int, request: Request, name: str = "taqdimot"):
    c = C(request); guard(c, "taqdimot yuklash", AUTHORS, f"kurs #{cid} · {no}-mavzu · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_slides, c, cid, no, raw, name[:160])

@router.post(P + "/courses/{cid}/topics/{no}/files")
async def api_file_upload(cid: int, no: int, request: Request, name: str = "fayl"):
    c = C(request); guard(c, "qo'shimcha fayl yuklash", AUTHORS, f"kurs #{cid} · {no}-mavzu · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_file, c, cid, no, raw, name[:160])

@router.get(P + "/assets/{aid}")
def api_asset(aid: int, request: Request):
    c = C(request); guard(c, "manba faylini yuklab olish", WORK, f"#{aid}")
    a, _ = _asset(c, aid)
    p = _apath(a)
    if not p.is_file(): raise HTTPException(410, "Fayl saqlanmagan")
    ext = a["kind"] if a["kind"] in _CT else "bin"
    return FileResponse(p, media_type=_CT.get(ext, "application/octet-stream"), filename=f"{_ascii(Path(a['name']).stem)}.{ext}")

@router.post(P + "/assets/{aid}/delete")
def api_asset_delete(aid: int, request: Request):
    c = C(request); guard(c, "manba faylini o'chirish", AUTHORS, f"#{aid}")
    return delete_asset(c, aid)

class VideoIn(BaseModel):
    url: str = Field("", max_length=1000)

@router.post(P + "/courses/{cid}/topics/{no}/video")
def api_video(cid: int, no: int, body: VideoIn, request: Request):
    c = C(request); guard(c, "video havola", AUTHORS, f"kurs #{cid} · {no}-mavzu")
    return set_video(c, cid, no, body.url)

class DeckIn(BaseModel):
    deck_id: int = 0

@router.post(P + "/courses/{cid}/topics/{no}/deck")
def api_deck(cid: int, no: int, body: DeckIn, request: Request):
    c = C(request); guard(c, "taqdimot (modul) biriktirish", AUTHORS, f"kurs #{cid} · {no}-mavzu · deck #{body.deck_id}")
    return set_deck(c, cid, no, body.deck_id)

class SettingsIn(BaseModel):
    mode: str | None = None
    completion: str | None = None
    mastery: int | None = Field(None, ge=0, le=100)
    quiz_n: int | None = Field(None, ge=0, le=200)
    shuffle: bool | None = None
    attempts: int | None = Field(None, ge=0, le=20)
    show_feedback: bool | None = None
    blocks: dict | None = None
    reset: bool = False

@router.post(P + "/courses/{cid}/topics/{no}/settings")
def api_topic_settings(cid: int, no: int, body: SettingsIn, request: Request):
    c = C(request); guard(c, "mavzu sozlamasi", AUTHORS, f"kurs #{cid} · {no}-mavzu")
    s = {k: v for k, v in body.model_dump().items() if v is not None and k != "reset"}
    return set_topic_settings(c, cid, no, s, body.reset)

class BuildIn(BaseModel):
    mode: str | None = None
    force: bool = False

@router.post(P + "/courses/{cid}/topics/{no}/build")
async def api_build(cid: int, no: int, body: BuildIn, request: Request):
    c = C(request); guard(c, "paket yig'ish", AUTHORS, f"kurs #{cid} · {no}-mavzu · {body.mode or ''}")
    return await run_in_threadpool(build_topic, c, cid, no, body.mode, body.force)

class BulkVideoIn(BaseModel):
    text: str = Field(..., max_length=100_000)
    apply: bool = False

@router.post(P + "/courses/{cid}/bulk/videos")
def api_bulk_videos(cid: int, body: BulkVideoIn, request: Request):
    c = C(request); guard(c, "videolarni avtomatik joylash", AUTHORS, f"kurs #{cid} · {'saqlash' if body.apply else 'tekshirish'}")
    return bulk_videos(c, cid, body.text, body.apply)

class BulkBuildIn(BaseModel):
    topics: list[int] | None = None
    mode: str | None = None
    only_complete: bool = False

@router.post(P + "/courses/{cid}/bulk/build")
async def api_bulk_build(cid: int, body: BulkBuildIn, request: Request):
    c = C(request); guard(c, "ommaviy yig'ish", AUTHORS, f"kurs #{cid}")
    if body.mode and body.mode not in MODES: raise HTTPException(400, "Paket turi noma'lum")
    return await run_in_threadpool(bulk_build, c, cid, body.topics, body.mode, body.only_complete)

class CourseIn(BaseModel):
    mode: str = "scorm12"
    only_approved: bool = False

@router.post(P + "/courses/{cid}/course-package")
async def api_course_package(cid: int, body: CourseIn, request: Request):
    c = C(request); guard(c, "kurs paketi", AUTHORS, f"kurs #{cid} · {body.mode}")
    return await run_in_threadpool(build_course, c, cid, body.mode, body.only_approved)

@router.get(P + "/packages/{pid}")
def api_package(pid: int, request: Request):
    c = C(request); guard(c, "paket", WORK, f"#{pid}")
    r, _ = _package(c, pid)
    out = pack_row(r)
    out["validation"] = json.loads(r["validation"] or "{}")
    out["log"] = db.rows(_con, "SELECT ts, user_name, action, note FROM pk_log WHERE package_id=? ORDER BY id", (r["id"],))
    return out

@router.get(P + "/packages/{pid}/download")
def api_download(pid: int, request: Request):
    c = C(request); guard(c, "paketni yuklab olish", WORK, f"#{pid}")
    r, co = _package(c, pid)
    f = store() / r["file"]
    if not f.is_file(): raise HTTPException(410, "Paket fayli saqlanmagan (eski versiya o'chirilgan)")
    return FileResponse(f, media_type="application/zip", filename=download_name(co, r["topic_no"], r["mode"]))

@router.get(P + "/packages/{pid}/preview/{path:path}")
def api_preview(pid: int, path: str, request: Request):
    c = C(request); guard(c, "paketni ko'rish", WORK, f"#{pid} · {path[:60]}")
    return preview_redirect(c, pid, path)

@router.get(P + "/pv/{token}/{path:path}")
def api_preview_signed(token: str, path: str):
    """Ko'rish fayllari — imzolangan yo'l orqali (cookie'siz; sandbox iframe ichki so'rovlari uchun)."""
    c, pid = preview_ctx(token)
    return preview_file(c, pid, path)

class ActIn(BaseModel):
    action: str
    note: str = Field("", max_length=500)

@router.post(P + "/packages/{pid}/action")
def api_package_action(pid: int, body: ActIn, request: Request):
    c = C(request); guard(c, {"approve": "paketni tasdiqlash", "reject": "paketni qaytarish"}.get(body.action, "paket amali"), DEPT, f"#{pid} {body.action}")
    return package_action(c, pid, body.action, body.note)

class DefaultsIn(BaseModel):
    mode: str
    completion: str
    mastery: int = Field(60, ge=0, le=100)
    quiz_n: int = Field(0, ge=0, le=200)
    shuffle: bool = True
    attempts: int = Field(0, ge=0, le=20)
    show_feedback: bool = True
    blocks: dict = {}

@router.post(P + "/settings")
def api_settings(body: DefaultsIn, request: Request):
    c = C(request); guard(c, "umumiy sozlamalar", DEPT)
    if body.mode not in MODES or body.completion not in COMPLETION: raise HTTPException(400, "Sozlama qiymati noto'g'ri")
    s = _clean_settings(body.model_dump(), DEFAULTS)
    with _lock:
        _con.execute("INSERT OR REPLACE INTO pk_meta(k,v) VALUES('defaults', ?)", (json.dumps(s),)); _con.commit()
    return {"ok": True, "defaults": defaults()}


# =============================================================================================
# Demo (namuna) — sun'iy, aniq belgilangan; init() da bir marta (pk_meta.seed_v1)
# =============================================================================================
DEMO_VIDEO = "https://www.youtube.com/watch?v=ISFTdemo001"     # NAMUNA: mavjud bo'lmagan video ID (format to'g'ri) — haqiqiy havola bilan almashtiring
DEMO_SLIDES = [
    ("Iqtisodiyot fani predmeti", ["Mikroiqtisodiyot — alohida subyektlar xatti-harakati", "Makroiqtisodiyot — milliy iqtisodiyot ko'rsatkichlari",
                                   "Asosiy muammo: cheklangan resurslar va cheksiz ehtiyojlar"], "Namuna slayd (demo). Talabalarga fan predmetini tushuntiring."),
    ("Muqobil xarajat", ["Tanlangan variant uchun voz kechilgan eng yaxshi muqobil qiymati", "Har bir tanlovning yashirin narxi bor"], "Kundalik hayotdan misol keltiring."),
    ("Ishlab chiqarish imkoniyatlari egri chizig'i", ["Ikki tovarning maksimal kombinatsiyalari", "Ichkaridagi nuqta — resurslardan to'liq foydalanilmaydi",
                                                      "Tashqaridagi nuqta — erishib bo'lmaydi"], "Chizmani bosqichma-bosqich tushuntiring."),
    ("Ishlab chiqarish omillari", ["Yer", "Mehnat", "Kapital", "Tadbirkorlik qobiliyati"], ""),
]

DEMO_LECTURE = """1-MAVZU: IQTISODIYOT NAZARIYASI FANINING PREDMETI VA USLUBLARI
Reja:
1. Mikro- va makroiqtisodiyot
2. Cheklangan resurslar va tanlov muammosi
3. Ishlab chiqarish imkoniyatlari egri chizig'i
4. Pozitiv va normativ tahlil

1. Mikro- va makroiqtisodiyot
Mikroiqtisodiyot alohida iqtisodiy subyektlar — iste'molchilar, firmalar va tarmoqlarning xatti-harakatini o'rganadi.
Makroiqtisodiyot esa butun milliy iqtisodiyotni, ya'ni yalpi ichki mahsulot, inflyatsiya va ishsizlik kabi umumiy ko'rsatkichlarni tahlil qiladi.

2. Cheklangan resurslar va tanlov muammosi
Iqtisodiyotning asosiy muammosi — **cheklangan resurslar** va cheksiz ehtiyojlar o'rtasidagi ziddiyatdir. Bu muammo tanlov zaruratini keltirib chiqaradi.
Muqobil xarajat — tanlangan variant uchun voz kechilgan eng yaxshi muqobilning qiymatidir.
Ishlab chiqarish omillari:
- yer;
- mehnat;
- kapital;
- tadbirkorlik qobiliyati.

3. Ishlab chiqarish imkoniyatlari egri chizig'i
Egri chiziq berilgan resurslar va texnologiya sharoitida ikki tovarni ishlab chiqarishning maksimal kombinatsiyalarini ko'rsatadi.
- Nuqta | Ma'nosi
- Egri chiziqda | Resurslardan to'liq foydalaniladi
- Ichkarida | Resurslardan to'liq foydalanilmaydi
- Tashqarida | Mavjud resurslar bilan erishib bo'lmaydi

4. Pozitiv va normativ tahlil
Pozitiv iqtisodiy tahlil «nima bor?» degan savolga javob beradi, normativ tahlil esa «nima bo'lishi kerak?» degan savolga javob beradi.

Nazorat savollari:
1) Mikroiqtisodiyot nimani o'rganadi?
2) Muqobil xarajat deganda nimani tushunasiz?
(Namuna ma'ruza matni — demo.)
"""

def demo_pptx() -> bytes:
    """Kichik sun'iy taqdimot (python-pptx) — 4 slayd, izohlar va bitta rasm (PIL chizma). NAMUNA."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from PIL import Image, ImageDraw
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    im = Image.new("RGB", (640, 420), "white"); d = ImageDraw.Draw(im)
    d.line([(60, 380), (600, 380)], fill="black", width=3); d.line([(60, 380), (60, 30)], fill="black", width=3)
    d.arc([(-480, -320), (560, 380)], 270, 360, fill=(139, 0, 51), width=6)
    d.ellipse([(250, 250), (266, 266)], fill=(0, 120, 120)); d.ellipse([(480, 90), (496, 106)], fill=(200, 120, 0))
    bio = io.BytesIO(); im.save(bio, "PNG"); pic = bio.getvalue()
    for i, (title, bullets, notes) in enumerate(DEMO_SLIDES):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = title
        tf = s.placeholders[1].text_frame
        tf.text = bullets[0]
        for b in bullets[1:]: tf.add_paragraph().text = b
        if i == 2:
            s.placeholders[1].width = Inches(6.2)
            s.shapes.add_picture(io.BytesIO(pic), Inches(7), Inches(1.8), width=Inches(5.6))
        if notes: s.notes_slide.notes_text_frame.text = notes
    out = io.BytesIO(); prs.save(out)
    return out.getvalue()

def seed(con, force=False):
    """Namuna: «Mikroiqtisodiyot» 1–2-mavzular — Test bank namuna matni va savollari + sun'iy PPTX + namuna video havola; 1-mavzu paketi (pleyer bo'lsa)."""
    global _con
    saved = _con
    _con = con
    try:
        co = db.one(con, "SELECT * FROM dl_courses WHERE subject='Mikroiqtisodiyot' ORDER BY id LIMIT 1") \
            if db.one(con, "SELECT name FROM sqlite_master WHERE type='table' AND name='dl_courses'") else None
        if not co: return
        if force or not db.one(con, "SELECT 1 x FROM pk_meta WHERE k='seed_v1'"):
            if force:
                con.execute("DELETE FROM pk_assets WHERE src='demo'"); con.execute("DELETE FROM pk_topics WHERE src='demo'")
            now = _now()
            for no in (1, 2):
                con.execute("""INSERT INTO pk_topics(course_id,topic_no,video_url,video_at,video_by,updated_at,src) VALUES(?,?,?,?,?,?,'demo')
                               ON CONFLICT(course_id,topic_no) DO NOTHING""", (co["id"], no, DEMO_VIDEO, now, "Namuna (demo)", now))
            txt = DEMO_LECTURE.strip()
            _save_asset(None, co["id"], 1, "matn", "txt", "Namuna ma'ruza matni — 1-mavzu (demo).txt", txt.encode("utf-8"),
                        {"text": txt, "chars": len(txt), "truncated": False, "plan": structure_text(txt)["plan"]}, src="demo")
            raw = demo_pptx()
            aid = _save_asset(None, co["id"], 1, "taqdimot", "pptx", "Namuna taqdimot — 1-mavzu (demo).pptx", raw, {}, src="demo")
            a = db.one(con, "SELECT * FROM pk_assets WHERE id=?", (aid,))
            parsed = parse_pptx(raw, _img_dir(a))
            con.execute("UPDATE pk_assets SET meta=? WHERE id=?", (json.dumps({"count": parsed["count"], "slides": parsed["slides"]}, ensure_ascii=False), aid))
            con.execute("INSERT OR REPLACE INTO pk_meta(k,v) VALUES('seed_v1', ?)", (now,))
            con.commit()
        # namuna paket — pleyer paydo bo'lganda bir marta (idempotent)
        if player_ok() and not db.one(con, "SELECT 1 x FROM pk_packages WHERE src='demo' LIMIT 1") and not db.one(con, "SELECT 1 x FROM pk_meta WHERE k='demo_pkg'"):
            try:
                build_topic(None, co["id"], 1, "scorm12", src="demo")
                con.execute("INSERT OR REPLACE INTO pk_meta(k,v) VALUES('demo_pkg', ?)", (_now(),)); con.commit()
            except HTTPException as e:
                print("paket demo build:", e.detail)
    finally:
        _con = saved
