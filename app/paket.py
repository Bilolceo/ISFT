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

NEXTID (kontrakt v2): institut LMS'i — NEXTID.LMS (my.isft.uz), «Articulate» yorlig'ida darslar L (ma'ruza) va A (amaliy) … — paket dars bo'yicha
  (lessons(): standart L1..Ln + pk_lessons; ichki kalit L=N, A=1000+N, S=2000+N, Lab=3000+N, MT=4000+N; eski mavzu paketlari — L darslar),
  standart tur xAPI; kafedra shabloni: section → video → section → reja (heading) → matn (Word rasmlari/jadvallari) → keypoints → refs →
  section → slides (PDF → rasmlar, pypdfium2) → test → reflect; AI asosiy xulosalar (claude_client.call_json, iqtibos bilan tekshiriladi).

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

MODES = {"xapi": "xAPI (Tin Can) — NEXTID", "scorm12": "SCORM 1.2", "scorm2004": "SCORM 2004 (4-nashr)", "none": "Oddiy HTML (LMS'siz)"}
COMPLETION = {"view_all": "Barcha bloklar ko'rilganda", "quiz_pass": "Test topshirilganda", "view_and_quiz": "Ko'rilganda va test topshirilganda"}
STATUS = {"qoralama": "Qoralama", "tayyor": "Tayyor (tasdiq kutilmoqda)", "tasdiqlandi": "Tasdiqlandi"}
BLOCKS = {"sections": "Bo'lim sarlavhalari", "video": "Videodars", "plan": "Reja", "text": "Ma'ruza matni", "keypoints": "Asosiy xulosalar",
          "refs": "Foydalanilgan adabiyotlar", "slides": "Taqdimot", "files": "Qo'shimcha fayllar", "quiz": "Test", "reflect": "O'z-o'zini baholash"}
REQUIRED = ("text", "slides", "video", "quiz")    # «tayyor» bo'lishi uchun (sozlamada yoqilganlari)
LAYOUTS = {"steps": "Qadamlar (Articulate Rise kabi)", "scroll": "Bitta sahifa (aylantirish)"}
SECTIONS = {"video": "VIDEODARS", "text": "MA'RUZA MATNI", "slides": "DARS TAQDIMOTI"}   # kafedra shabloni — bo'lim sarlavhalari
REFLECT = {"title": "O'z-o'zini baholash", "question": "Darsni to'liq o'zlashtirdingizmi?",
           "options": [{"text": "Ha, albatta", "feedback": "Ajoyib! Keyingi darsga o'tishingiz mumkin."},
                       {"text": "Yo'q, to'liq o'zlashtirmadim", "feedback": "Ma'ruza matni va videodarsni qayta ko'rib chiqing."}]}
DEFAULTS = {"mode": "xapi", "completion": "view_and_quiz", "mastery": 60, "quiz_n": 0, "shuffle": True, "attempts": 0,
            "show_feedback": True, "blocks": {k: True for k in BLOCKS}, "layout": "steps", "sections": dict(SECTIONS), "reflect": REFLECT}
_OLD_DEFAULTS = {"mode": "scorm12", "completion": "view_and_quiz", "mastery": 60, "quiz_n": 0, "shuffle": True, "attempts": 0, "show_feedback": True}

# Darslar (NEXTID «Articulate» yorlig'i: «L1-1-dars: …», «A1- AMALIY MASHG'ULOT: …»). Ichki kalit (pk_*.topic_no ustuni) = asos + raqam:
# ma'ruza L1..L999 → 1..999 (eski «mavzu» paketlari o'zgarishsiz L darslar), amaliy A1 → 1001, seminar S1 → 2001, laboratoriya Lab1 → 3001, mustaqil MT1 → 4001.
KINDS = {"maruza": ("L", 0, "Ma'ruza", "Ma'ruzalar"), "amaliy": ("A", 1000, "Amaliy mashg'ulot", "Amaliy mashg'ulotlar"),
         "seminar": ("S", 2000, "Seminar", "Seminarlar"), "laboratoriya": ("Lab", 3000, "Laboratoriya ishi", "Laboratoriya ishlari"),
         "mustaqil": ("MT", 4000, "Mustaqil ta'lim", "Mustaqil ta'lim")}
MAX_LESSON_NO = 999

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
CREATE TABLE IF NOT EXISTS pk_lessons(course_id INT, lkey INT, kind TEXT, no INT, title TEXT, topic_ref INT, ts TEXT, user_name TEXT,
  deleted INT DEFAULT 0, src TEXT DEFAULT '', PRIMARY KEY(course_id, lkey));
CREATE TABLE IF NOT EXISTS pk_ai(id INTEGER PRIMARY KEY, course_id INT, topic_no INT, user_id INT, day TEXT, ts TEXT, kind TEXT, model TEXT,
  ok INT, ms INT, err TEXT, in_tok INT, out_tok INT, n_got INT, n_dropped INT);
CREATE INDEX IF NOT EXISTS ix_pk_ai ON pk_ai(user_id, day);
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
        migrate(con)
        con.execute("INSERT OR IGNORE INTO pk_meta(k,v) VALUES('defaults', ?)", (json.dumps(DEFAULTS),))
        con.commit()
    except Exception as e:
        print("paket.init:", e); return
    if not db.one(con, "SELECT 1 x FROM users"): return
    try:
        seed(con)
    except Exception as e:      # demo ma'lumot ilovani to'xtatmasin
        print("paket seed:", repr(e))

def _cols(con, table: str) -> set:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def migrate(con) -> dict:
    """Darslar modeli (NEXTID) — idempotent: necha marta chaqirilsa ham natija bir xil.
      1) pk_lessons, pk_ai jadvallari (SCHEMA); pk_topics.keypoints, pk_packages.lesson ustunlari (yo'q bo'lsa);
      2) mavjud mavzu paketlari — L darslar: pk_packages.lesson = 'L<N>' (kurs paketi — 'kurs'), faqat bo'sh qatorlarda;
      3) standart sozlama hech o'zgartirilmagan bo'lsa (eski DEFAULTS bilan bir xil) — paket turi xAPI (NEXTID), bir marta (pk_meta.nextid_v1)."""
    con.executescript(SCHEMA)
    out = {"columns": [], "packages": 0, "defaults": False}
    if "keypoints" not in _cols(con, "pk_topics"):
        con.execute("ALTER TABLE pk_topics ADD COLUMN keypoints TEXT"); out["columns"].append("pk_topics.keypoints")
    if "lesson" not in _cols(con, "pk_packages"):
        con.execute("ALTER TABLE pk_packages ADD COLUMN lesson TEXT"); out["columns"].append("pk_packages.lesson")
    out["packages"] = con.execute("""UPDATE pk_packages SET lesson = CASE WHEN topic_no=0 THEN 'kurs' ELSE 'L' || topic_no END
                                     WHERE (lesson IS NULL OR lesson='') AND topic_no BETWEEN 0 AND 999""").rowcount
    if not con.execute("SELECT 1 FROM pk_meta WHERE k='nextid_v1'").fetchone():
        r = con.execute("SELECT v FROM pk_meta WHERE k='defaults'").fetchone()
        if r:
            try: cur = json.loads(r[0])
            except (TypeError, ValueError): cur = {}
            if all(cur.get(k) == v for k, v in _OLD_DEFAULTS.items()):
                cur["mode"] = "xapi"
                con.execute("UPDATE pk_meta SET v=? WHERE k='defaults'", (json.dumps(cur),)); out["defaults"] = True
        con.execute("INSERT OR REPLACE INTO pk_meta(k,v) VALUES('nextid_v1', ?)", (_now(),))
    con.commit()
    return out

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
    if s.get("layout") in LAYOUTS: out["layout"] = s["layout"]
    if isinstance(s.get("sections"), dict):
        for k in SECTIONS:
            v = re.sub(r"\s+", " ", str(s["sections"].get(k) or "")).strip()[:80]
            if v: out["sections"][k] = v
    if isinstance(s.get("reflect"), dict):
        r = s["reflect"]
        for k, n in (("title", 80), ("question", 300)):
            v = re.sub(r"\s+", " ", str(r.get(k) or "")).strip()[:n]
            if v: out["reflect"][k] = v
        if isinstance(r.get("options"), list):
            opts = []
            for o in r["options"][:4]:
                if not isinstance(o, dict): continue
                t = re.sub(r"\s+", " ", str(o.get("text") or "")).strip()[:120]
                if t: opts.append({"text": t, "feedback": re.sub(r"\s+", " ", str(o.get("feedback") or "")).strip()[:500]})
            if len(opts) >= 2: out["reflect"]["options"] = opts
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

_BULK_RX = re.compile(r"^\s*(?:(lab|mt|l|a|s)\s*)?(\d{1,3})\s*(?:[:.)\-–—]|\s)\s*(\S+)\s*$", re.I)

def parse_bulk(text: str, n_topics: int, valid_keys=None) -> list[dict]:
    """«Avtomatik joylash»: har qatorda havola (ketma-ket L1..Ln) yoki «N: havola» / «A3: havola» (dars kodi).
    → [{line, topic_no (dars kaliti), code, url, ok, error, video}]"""
    valid = set(valid_keys) if valid_keys is not None else set(range(1, n_topics + 1))
    out, nxt = [], 1
    for i, raw in enumerate((text or "").replace("\r", "").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"): continue
        m = _BULK_RX.match(line)
        if m and not YT_ID.match(line):
            kind = _PREFIX_KIND.get((m.group(1) or "l").lower(), "maruza")
            no, url = lesson_key(kind, int(m.group(2))), m.group(3)
        else:
            no, url = nxt, line.split()[0]
        r = {"line": i, "topic_no": no, "code": lesson_code(no), "url": url}
        v = parse_video(url)
        if no not in valid:
            r.update(ok=False, error=f"Mavzu raqami 1–{n_topics} oralig'ida bo'lishi kerak" if no < 1000 else
                     f"{lesson_code(no)} darsi yo'q — avval «Darslar ro'yxati»ga qo'shing")
        elif not v["ok"]: r.update(ok=False, error=v["error"])
        else: r.update(ok=True, error="", video=v)
        out.append(r)
        if no < 1000: nxt = no + 1
    seen = {}
    for r in out:
        if r.get("ok"):
            if r["topic_no"] in seen:
                seen[r["topic_no"]].update(ok=False, error="Shu mavzuga keyingi qatorda boshqa havola berilgan (oxirgisi olinadi)")
            seen[r["topic_no"]] = r
    return out


# =============================================================================================
# Darslar: L (ma'ruza), A (amaliy), S (seminar), Lab (laboratoriya), MT (mustaqil ta'lim) — NEXTID nomlari
# =============================================================================================
_PREFIX_KIND = {"l": "maruza", "a": "amaliy", "s": "seminar", "lab": "laboratoriya", "mt": "mustaqil"}
_KIND_ORDER = list(KINDS)

def lesson_key(kind: str, no: int) -> int: return KINDS[kind][1] + int(no)

def split_key(key: int) -> tuple[str, int]:
    key = int(key)
    kind = _KIND_ORDER[key // 1000] if 0 <= key // 1000 < len(_KIND_ORDER) else "maruza"
    return kind, key - KINDS[kind][1]

def lesson_code(key: int) -> str:
    kind, no = split_key(key)
    return f"{KINDS[kind][0]}{no}"

def lesson_file_code(key: int) -> str:
    kind, no = split_key(key)
    return f"{KINDS[kind][0]}{no:02d}"

_KIND_WORDS = (r"amaliy\s+mashg'ulot(?:i)?|amaliy\s+ish(?:i)?|amaliy|seminar(?:\s+mashg'ulot(?:i)?)?|laboratoriya(?:\s+ishi|\s+mashg'uloti)?|"
               r"mustaqil\s+ta'lim|mustaqil\s+ish|ma'ruza|maruza")
_LESSON_RX = re.compile(r"^\s*(?:[-•*]\s*)?(lab|mt|l|a|s)\s*\.?\s*(\d{1,3})(?!\d)\s*(?:[-–—.:)]\s*)?(?:\d{1,3}\s*-\s*dars\b\s*)?"
                        rf"(?:(?:{_KIND_WORDS})\s*(?:[:\-–—.]|$)\s*)?[:\-–—.]?\s*(.*)$", re.I)
_LTOPIC_RX = re.compile(r"\s*(?:\((\d{1,3})\s*-?\s*mavzu\)|\[(\d{1,3})\]|\s[|#→]\s*(\d{1,3}))\s*$", re.I)

def parse_lessons(text: str) -> list[dict]:
    """NEXTID uslubidagi dars nomlari ro'yxati (har qatorda bitta) → [{line, raw, ok, error, key, code, kind, no, title, topic}].
    «L1-1-dars: NOM», «A1- AMALIY MASHG'ULOT: NOM», «A2- Amaliy: NOM», «S1 …», «Lab1 …», «MT1 …»; ixtiyoriy mavzu bog'lanishi
    oxirida: «(3-mavzu)», «[3]», « | 3», « # 3». Bo'sh va «#» bilan boshlangan qatorlar e'tiborsiz. Bir kod ikki marta — oxirgisi olinadi."""
    out = []
    for i, raw in enumerate((text or "").replace("\r", "").split("\n"), 1):
        line = raw.translate(_APOS).strip()
        if not line or line.startswith("#"): continue
        r = {"line": i, "raw": raw.strip()[:300], "ok": False, "error": ""}
        m = _LESSON_RX.match(line)
        if not m:
            r["error"] = "Dars kodi topilmadi (L1, A1, S1, Lab1, MT1 …)"; out.append(r); continue
        kind = _PREFIX_KIND[m.group(1).lower()]
        no = int(m.group(2))
        title, topic = m.group(3).strip(), None
        tm = _LTOPIC_RX.search(title)
        if tm:
            topic = int(next(g for g in tm.groups() if g)); title = title[:tm.start()].strip()
        title = re.sub(r"\s+", " ", title).strip(" -–—:.")[:300]
        r.update(key=lesson_key(kind, no) if 1 <= no <= MAX_LESSON_NO else None, code=f"{KINDS[kind][0]}{no}", kind=kind, no=no, title=title, topic=topic)
        if not 1 <= no <= MAX_LESSON_NO: r["error"] = "Dars raqami 1–999 oralig'ida bo'lishi kerak"
        elif not title: r["error"] = "Dars nomi bo'sh"
        else: r["ok"] = True
        out.append(r)
    seen = {}
    for r in out:
        if r["ok"]:
            if r["key"] in seen: seen[r["key"]].update(ok=False, error=f"{r['code']} keyingi qatorda qayta berilgan (oxirgisi olinadi)")
            seen[r["key"]] = r
    return out


# =============================================================================================
# HTML tozalash (server tomonda, oq ro'yxat)
# =============================================================================================
ALLOWED_TAGS = {"h2", "h3", "h4", "p", "ul", "ol", "li", "strong", "em", "b", "i", "u", "blockquote", "table", "thead", "tbody", "tr", "th", "td",
                "br", "sup", "sub", "code", "pre", "a", "figure", "figcaption", "img"}
# Mazmuni bilan tashlanadigan teglar (ichidagi matn ham ko'rinmaydi): skript/uslub, xom matnli (textarea, title, xmp…), o'rnatilgan
# kontent va SVG/MathML. Bo'sh (void) teglar (embed, frame, param …) bu yerda emas — ular yopilmaydi, «skip» rejimiga kirmasdan tashlanadi.
_DROP_TAGS = {"script", "style", "iframe", "object", "noscript", "template", "svg", "math", "textarea", "title", "head", "xmp", "plaintext",
              "noembed", "noframes", "frameset", "applet", "xml", "video", "audio", "canvas"}
_RECOVER = {"textarea", "title", "xmp"}   # yopilmay qolsa — hujjat oxirida ichidagi matni (escape qilingan) qaytariladi
# Faqat tegning o'zi tashlanadi, ichidagi matn qoladi (oq ro'yxatdan tashqari boshqa teglar ham shunday): button, form, select, label …
_MAP_TAGS = {"h1": "h2", "h5": "h4", "h6": "h4"}
_VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr", "col", "area", "base", "param", "track", "embed", "frame", "keygen", "basefont",
         "bgsound", "image"}

_ASSET_SRC_RX = re.compile(r"^assets/[A-Za-z0-9_\-][A-Za-z0-9_\-./]{0,200}$")

def safe_src(v: str) -> str | None:
    """<img src> — faqat paket ichidagi nisbiy yo'l «assets/…» (http(s), data:, javascript:, «/», «..», «//», «\\», % — rad etiladi)."""
    v = html.unescape(v or "")
    if re.search(r"[\x00-\x20\x7f]", v) or not _ASSET_SRC_RX.match(v): return None
    if any(p in ("", "..", ".") for p in v.split("/")): return None
    return v

def _img_tag(attrs) -> str | None:
    a = dict(attrs)
    src = safe_src(a.get("src") or "")
    if not src: return None
    alt = re.sub(r"\s+", " ", a.get("alt") or "").strip()[:300]
    return f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">'

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
        if tag == "img":                            # faqat nisbiy «assets/…» rasm (src + alt), boshqa atributlar tashlanadi
            t = _img_tag(attrs)
            if t: self.out.append(t)
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
        elif tag == "img" and not self.skip: self.handle_starttag(tag, attrs)
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
            if tag == "img" and k == "src" and safe_src(v or ""): continue
            if tag == "img" and k == "alt": continue
            self.bad = f"<{tag} {k}>"; return
        if tag == "img" and not any(k == "src" for k, _ in attrs): self.bad = "<img> (src yo'q)"
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
_IMG_RX = re.compile(r"^\[RASM \d+\]$")                       # Test bank / taqdimot_extract belgisi — rasm faylisiz, tashlanadi
_FIG_RX = re.compile(r"^\[RASM:\s*([A-Za-z0-9_\-]{1,80}\.(?:png|jpg))\s*\]$", re.I)    # paket rasmi: assets/img/<fayl>
_TBL_RX = re.compile(r"^\[JADVAL:\s*(\d{1,4})\s*\]$")
CAPTION_RX = re.compile(r"^(?:\d+(?:\.\d+)*\s*-?\s*(?:rasm|расм|рисунок)\b|(?:rasm|расм|рисунок|рис\.)\s*(?:\d+(?:\.\d+)*\s*[.:\-–—)]?|[.:\-–—]))", re.I)
_REFS_RX = re.compile(r"^(?:#{1,6}\s*)?(?:\d{1,2}[.)]?\s+)?((?:foydalanilgan|asosiy|qo'shimcha|tavsiya\s+etiladigan|tavsiya\s+etilgan)\s+"
                      r"(?:adabiyotlar|manbalar)(?:\s+va\s+manbalar)?(?:\s+ro'yxati)?|adabiyotlar(?:\s+ro'yxati)?|литература|"
                      r"(?:список\s+)?(?:использованной\s+|рекомендуемой\s+)?литературы|фойдаланилган\s+адабиётлар(?:\s+рўйхати)?)\s*[:.]?\s*(.*)$", re.I)
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
    """Qatorlar → tokenlar. «Reja:» ro'yxati ichidagi qatorlar (birinchi bo'sh qator/sarlavhagacha; bo'sh qatordan keyin ham — raqami
    rejaning keyingi raqami bo'lsa yoki belgili band) adabiyotlar sarlavhasi deb olinmaydi: «3. Foydalanilgan adabiyotlar» — reja bandi."""
    out = []
    # reja bo'limi holati (structure_text dagi reja qoidalari bilan bir xil): ichidamizmi; oxirgi raqam; bandlar soni; bo'sh qatordan keyinmi;
    # bandlar turi — None / "list" (raqamli/belgili) / "plain" (oddiy qisqa qatorlar)
    plan, plan_last, plan_n, gap, pkind = False, 0, 0, False, None
    for raw in str(text or "").translate(_APOS).replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            if plan and plan_n: gap = True
            out.append(("blank", "")); continue
        in_plan = False
        if plan:
            m1, mb = _OL1_RX.match(line), _BUL_RX.match(line)
            if _MD_RX.match(line) or _PLAN_RX.match(line) or _FIG_RX.match(line) or _TBL_RX.match(line) or plan_n >= 20: pass
            elif m1 and pkind != "plain":
                k_ = int(m1.group(1))
                if k_ > plan_last and (not gap or k_ == plan_last + 1): in_plan = True; plan_last = k_
            elif mb and pkind != "plain": in_plan = True
            elif not m1 and not mb and not gap and pkind != "list" and len(line) <= 120 and not line.endswith(".") and plan_n < 12:
                in_plan = True
            if in_plan: plan_n += 1; gap = False; pkind = pkind or ("plain" if not (m1 or mb) else "list")
            else: plan = False
        if _IMG_RX.match(line): continue
        m = _FIG_RX.match(line)
        if m: out.append(("img", m.group(1))); continue
        m = _TBL_RX.match(line)
        if m: out.append(("tbl", m.group(1))); continue
        m = None if in_plan else _REFS_RX.match(line)
        if m and len(line) <= 2000 and (not m.group(2) or re.match(r"^(?:\d{1,2}[.)]|[-•*–])\s", m.group(2))):
            out.append(("refs", m.group(2).strip())); continue
        if not in_plan and _PLAN_RX.match(line) and len(line) <= 400:
            rest = _PLAN_RX.match(line).group(2).strip()
            out.append(("plan", rest))
            nums = re.findall(r"(?:^|\s)(\d{1,2})[.)]\s", " " + rest)
            plan, plan_last, plan_n, gap, pkind = True, int(nums[-1]) if nums else 0, (len(nums) or (1 if rest else 0)), False, ("list" if nums else None)
            continue
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

def _ref_item(t: str) -> str:
    t = re.sub(r"^\s*(?:\d{1,3}[.)]?|[-•*–—▪●◦►])\s+", "", t.strip())
    return t.strip().rstrip(";,").strip()

# adabiyotlar ro'yxatidan keyin keladigan bo'limlar — ro'yxat shu yerda tugaydi, qolgani matnga qaytadi
_REFS_STOP_RX = re.compile(r"^(?:#{1,6}\s*)?(?:\d{1,2}[.)]\s*)?(?:nazorat\s+(?:savollari|uchun\s+savollar)|savollar|test\s+savollari|topshiriqlar|"
                           r"amaliy\s+topshiriq\w*|mustaqil\s+(?:ish|ta'lim)\w*(?:\s+uchun\s+topshiriqlar)?|glossariy|atamalar\s+lug'ati|"
                           r"tayanch\s+(?:so'z|ibora|tushuncha)\w*|ilova\w*|контрольные\s+вопросы|вопросы(?:\s+для\s+самоконтроля)?|задания|глоссарий|"
                           r"назорат\s+саволлари|саволлар|топшириқлар)\b", re.I)

def _refs_stop(line: str) -> bool:
    """Adabiyotlar ro'yxatini tugatadigan qator: ma'lum bo'lim nomi yoki sarlavhasimon qisqa «…:» qatori."""
    line = line.strip()
    if _REFS_STOP_RX.match(line) and len(line) <= 120: return True
    return line.endswith(":") and len(line) <= 80 and len(line.split()) <= 8

def _refs_split(toks: list) -> tuple[list, list]:
    """«Foydalanilgan adabiyotlar» sarlavhasi va undan keyingi ro'yxat → (qolgan tokenlar, adabiyotlar).
    Ro'yxat tugaydi: sarlavha (raqamsiz), reja, rasm/jadval, ma'lum bo'lim («Nazorat savollari», «Savollar», «Topshiriqlar», «Glossariy» …)
    yoki sarlavhasimon «…:» qatori, raqamli/belgili ro'yxatdan keyin bo'sh qatordan so'ng kelgan oddiy matn. Ro'yxat bandi emas, lekin
    raqamli ro'yxat ichida bo'sh qatorsiz kelgan qator — oldingi bandning davomi; raqamsiz ro'yxatda har qator — band. Tugagan joydan keyingi
    hamma narsa matnga (asosiy matndan keyin) qaytadi. Ikkinchi adabiyotlar sarlavhasi («Qo'shimcha adabiyotlar») — ro'yxat davom etadi."""
    i = next((k for k, t in enumerate(toks) if t[0] == "refs"), None)
    if i is None: return toks, []
    items, numbered, prev_blank, j = [], False, True, i + 1
    def inline(rest):
        nonlocal numbered
        if not rest: return
        items.extend([_ref_item(x) for x in re.split(r"\s*(?:^|\s)\d{1,2}[.)]\s+", " " + rest) if _ref_item(x)] if re.search(r"\d[.)]\s", rest) else [_ref_item(rest)])
        numbered = True
    inline(toks[i][1])
    while j < len(toks):
        t = toks[j]
        if t[0] == "blank": prev_blank = True; j += 1; continue
        if t[0] == "refs": inline(t[1]); prev_blank = False; j += 1; continue
        if t[0] in ("plan", "img", "tbl") or (t[0] == "h" and not (t[1][:1].isdigit())): break
        line = t[1]
        if t[0] in ("t", "h") and _refs_stop(line): break
        if t[0] in ("ul", "ol", "ol1", "num"):
            items.append(_ref_item(line)); numbered = numbered or t[0] != "ul"
        elif items and numbered and prev_blank:
            break                                                 # ro'yxatdan keyin bo'sh qator va oddiy matn — matn davom etadi
        elif t[0] == "h":
            items.append(_ref_item(line))
        elif items and numbered:
            items[-1] = (items[-1] + " " + line).strip()
        else:
            items.append(_ref_item(line))
        prev_blank = False; j += 1
    return toks[:i] + toks[j:], [x[:600] for x in items if x][:80]

def _fig_html(fn: str, media: dict, caption: str = "") -> str:
    im = (media or {}).get("images", {}).get(fn)
    if im is None: return ""
    cap = re.sub(r"\s+", " ", caption or im.get("caption") or "").strip()[:400]
    alt = re.sub(r"^\s*\d+(?:\.\d+)*\s*-?\s*rasm\s*[.:\-–—]?\s*", "", cap, flags=re.I) or im.get("alt") or "Rasm"
    return (f'<figure><img src="assets/img/{fn}" alt="{html.escape(alt[:200], quote=True)}">' +
            (f"<figcaption>{html.escape(cap, quote=False)}</figcaption>" if cap else "") + "</figure>")

def _table_html(rows: list) -> str:
    rows = [[re.sub(r"\s+", " ", str(c or "")).strip()[:2000] for c in r] for r in (rows or []) if isinstance(r, list) and any(str(c or "").strip() for c in r)]
    if not rows: return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows[:400]]
    head, body = (rows[0], rows[1:]) if len(rows) > 1 else (None, rows)
    return ("<table>" + (f"<thead><tr>{''.join(f'<th>{_inline(c)}</th>' for c in head)}</tr></thead>" if head else "") +
            "<tbody>" + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")

def structure_text(text: str, topic_title: str = "", media: dict | None = None) -> dict:
    """Matn (oddiy, «# sarlavha / - band» belgili yoki docx'dan) → {"plan", "html", "explicit_plan", "refs", "images"}.
    media — {"images": {fayl: {"caption", "alt"}}, "tables": {"N": [[katak, …], …]}}: «[RASM:fayl]» → <figure>, «[JADVAL:N]» → <table>.
    «Foydalanilgan adabiyotlar» bo'limi matndan olinib, alohida «refs» ro'yxati bo'ladi."""
    toks, refs = _refs_split(_tokens(text))
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
                if u[0] in ("img", "tbl"): break
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
    # sarlavha darajalari: mavzu nomi (1-daraja) olib tashlangach eng yuqori daraja h2 bo'lsin (pleyer «qadamlar»ni h2 bo'yicha bo'ladi)
    lv = [t[2] for t in body if t[0] == "h"]
    if lv and min(lv) > 1:
        sh = min(lv) - 1
        body = [("h", t[1], t[2] - sh) if t[0] == "h" else t for t in body]
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
    headings, used_imgs, skip_cap = [], [], set()
    for idx, t in enumerate(body):
        k = t[0]
        if idx in skip_cap: continue
        if k == "blank": flush_p(); continue
        if k in ("img", "tbl"):
            flush_p(); flush_l()
            if k == "tbl":
                parts.append(_table_html(((media or {}).get("tables") or {}).get(str(t[1])))); continue
            cap = ""
            nx = next((x for x in range(idx + 1, len(body)) if body[x][0] != "blank"), None)
            if nx is not None and body[nx][0] == "t" and CAPTION_RX.match(body[nx][1]) and len(body[nx][1]) <= 300:
                cap = body[nx][1]; skip_cap.add(nx)
            fig = _fig_html(t[1], media, cap)
            if fig: parts.append(fig); used_imgs.append(t[1])
            continue
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
    return {"plan": plan[:20], "html": sanitize("".join(parts)), "explicit_plan": explicit, "refs": refs, "images": used_imgs}


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

def _titles(cid: int) -> dict:
    return {r["topic_no"]: (r["t"] or "").strip() for r in db.rows(_con, "SELECT topic_no, MAX(topic) t FROM dl_items WHERE course_id=? GROUP BY topic_no", (cid,))}

def _topic_title(cid: int, no: int, titles=None) -> str:
    t = (titles if titles is not None else _titles(cid)).get(no)
    return t or f"{lesson_code(no)}"

def _mk_lesson(key: int, r: dict | None, default: bool, topic_title: str | None) -> dict:
    kind, no = split_key(key)
    live = bool(r and not r.get("deleted"))
    custom = r.get("title") if live else None
    title = custom or (topic_title if kind == "maruza" else None) or (f"{lesson_code(no)}" if kind == "maruza" else f"{no}-{KINDS[kind][2].lower()}")
    return {"key": key, "code": f"{KINDS[kind][0]}{no}", "kind": kind, "kind_label": KINDS[kind][2], "no": no, "title": title,
            "topic": r.get("topic_ref") if live else None, "default": default, "custom": live}

def lessons(cid: int, co: dict | None = None, titles: dict | None = None) -> list[dict]:
    """Kurs darslari: standart L1..Ln (n — kursdagi mavzular, nomi dl_items'dan) + pk_lessons'dagi qo'shimchalar (A/S/Lab/MT, n dan katta L)
    va L nomini almashtirishlar. Tartib: tur (L, A, S, Lab, MT), keyin raqam."""
    co = co or db.one(_con, "SELECT id, topics FROM dl_courses WHERE id=?", (cid,)) or {"topics": 0}
    n = int(co.get("topics") or 15)
    titles = titles if titles is not None else _titles(cid)
    rows = {r["lkey"]: r for r in db.rows(_con, "SELECT * FROM pk_lessons WHERE course_id=?", (cid,))}
    out = [_mk_lesson(no, rows.get(no), True, titles.get(no)) for no in range(1, n + 1)]
    for key, r in rows.items():
        if r.get("deleted") or (1 <= key <= n): continue
        out.append(_mk_lesson(key, r, False, titles.get(split_key(key)[1]) if split_key(key)[0] == "maruza" else None))
    out.sort(key=lambda x: (_KIND_ORDER.index(x["kind"]), x["no"]))
    return out

def source_topic(l: dict) -> int | None:
    """Dars manbalari zaxirasi (Test bank matni/savollari, kontent monitoringi videosi) qaysi mavzudan olinadi: bog'langan mavzu (topic_ref)
    bo'lsa — o'sha; aks holda L dars — o'z raqami; A/S/Lab/MT (bog'lanmagan) — yo'q."""
    if l.get("topic"):
        try: return int(l["topic"])
        except (TypeError, ValueError): return None
    return l["no"] if l["kind"] == "maruza" else None

def lesson_keys_all() -> dict:
    """{kurs: [dars kalitlari]} — butun institut bo'yicha (qamrov uchun, nomlarsiz, tez)."""
    extra = {}
    for r in db.rows(_con, "SELECT course_id, lkey FROM pk_lessons WHERE deleted=0"): extra.setdefault(r["course_id"], set()).add(r["lkey"])
    out = {}
    for co in db.rows(_con, "SELECT id, topics FROM dl_courses"):
        n = int(co["topics"] or 15)
        out[co["id"]] = sorted(set(range(1, n + 1)) | extra.get(co["id"], set()), key=lambda k: (k // 1000, k))
    return out

def lesson_info(co: dict, key: int, titles=None) -> dict:
    """Bitta dars (lessons() ni qayta qurmasdan): pk_lessons qatori va (L uchun) dl_items'dagi mavzu nomi — to'g'ridan-to'g'ri so'rov."""
    try: key = int(key)
    except (TypeError, ValueError): key = -1
    kind, no = split_key(key) if key > 0 else ("maruza", 0)
    n = int(co.get("topics") or 15)
    r = db.one(_con, "SELECT * FROM pk_lessons WHERE course_id=? AND lkey=?", (co["id"], key)) if key > 0 else None
    default = kind == "maruza" and 1 <= key <= n
    if key <= 0 or not 1 <= no <= MAX_LESSON_NO or not (default or (r and not r.get("deleted"))):
        raise HTTPException(400, "Dars (mavzu) raqami noto'g'ri — bunday dars kursda yo'q")
    tt = None
    if kind == "maruza":
        if titles is not None: tt = titles.get(no)
        else:
            t_ = db.one(_con, "SELECT MAX(topic) t FROM dl_items WHERE course_id=? AND topic_no=?", (co["id"], no))
            tt = ((t_ or {}).get("t") or "").strip() or None
    return _mk_lesson(key, r, default, tt)

def _check_topic(co: dict, no: int) -> dict:
    return lesson_info(co, no)

def _lesson_of(cid: int, no: int) -> dict:
    co = db.one(_con, "SELECT id, topics FROM dl_courses WHERE id=?", (cid,))
    if not co: raise HTTPException(404, "Kurs topilmadi")
    return lesson_info(co, no)

def _lesson_heading(l: dict) -> str:
    if l["kind"] == "maruza": return f"{l['no']}-MAVZU: {l['title'].upper()}"
    return f"{l['no']}-{KINDS[l['kind']][2].upper()}: {l['title']}"

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

# --- Word (.docx) → belgilangan matn + rasmlar (hujjat tartibida, izohi bilan) + jadvallar -------------------------------
DOCX_MAX_IMAGES = 80
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_VML = "urn:schemas-microsoft-com:vml"

def _w_on(el, W=_W) -> bool:
    """OOXML yoqish/o'chirish belgisi (<w:b/>, <w:b w:val="0"/> …): val yo'q yoki 1/true/on — yoqilgan."""
    v = (el.get(f"{{{W}}}val") or "").strip().lower()
    return v not in ("0", "false", "off", "none")

def docx_lecture(raw: bytes) -> dict:
    """Word → {"text": belgilangan matn («# sarlavha», «- band», «[RASM:fayl]», «[JADVAL:N]»), "images": {fayl: {"data", "caption"}},
    "tables": {"N": [[katak]]}}. Rasm izohi — rasmdan keyingi (bo'lmasa oldingi) «1.1-rasm. …» / «Rasm 2. …» paragrafi (matndan olinadi).
    Rasmlar ≤ 1600 px (_norm_image), nomi — sha256 dan (bir xil rasm bir marta). Zip/rasm bombasi tekshiruvi chaqiruvchida (_zip_guard)."""
    from lxml import etree
    from PIL import Image
    from . import taqdimot_extract as EX
    W, R = _W, _RNS
    z = zipfile.ZipFile(io.BytesIO(raw))
    doc = etree.fromstring(z.read("word/document.xml"))
    rels = {}
    if "word/_rels/document.xml.rels" in z.namelist():
        for r in etree.fromstring(z.read("word/_rels/document.xml.rels")): rels[r.get("Id")] = r.get("Target")
    styles, sbold, sbase = {}, {}, {}
    if "word/styles.xml" in z.namelist():
        for st in etree.fromstring(z.read("word/styles.xml")).iter(f"{{{W}}}style"):
            nm = st.find(f"{{{W}}}name")
            sid = st.get(f"{{{W}}}styleId")
            styles[sid] = ((nm.get(f"{{{W}}}val") if nm is not None else "") or "").lower()
            b = st.find(f"{{{W}}}rPr/{{{W}}}b")
            if b is not None: sbold[sid] = _w_on(b, W)
            bo = st.find(f"{{{W}}}basedOn")
            if bo is not None: sbase[sid] = bo.get(f"{{{W}}}val")
    def style_bold(sid):       # belgi uslubi (rStyle) — basedOn zanjiri bo'yicha (oddiy meros)
        seen = set()
        while sid and sid not in seen:
            if sid in sbold: return sbold[sid]
            seen.add(sid); sid = sbase.get(sid)
        return False
    def run_bold(rpr):
        if rpr is None: return False
        b = rpr.find(f"{{{W}}}b")
        if b is not None: return _w_on(b, W)            # <w:b w:val="0|false|off"/> — qalin EMAS
        rs = rpr.find(f"{{{W}}}rStyle")
        return style_bold(rs.get(f"{{{W}}}val")) if rs is not None else False
    images, order = {}, 0
    def image(rid):
        nonlocal order
        t = rels.get(rid)
        if not t or len(images) >= DOCX_MAX_IMAGES or re.match(r"^[a-z]+:", t, re.I): return None
        path = (t.lstrip("/") if t.startswith("/") else ("word/" + t)).replace("word/../", "")
        try: data = z.read(path)
        except KeyError: return None
        r = _norm_image(data, strict=True)
        if not r: return None
        w, h = Image.open(io.BytesIO(r[0])).size
        if min(w, h) < 48: return None                       # ikonka, chiziq, belgi
        fn = f"{_sha(r[0])[:20]}.{r[1]}"
        images.setdefault(fn, {"data": r[0], "caption": ""})
        return fn
    def ln(node): return etree.QName(node).localname if isinstance(node.tag, str) else ""
    def para(pel):
        txt, imgs, bold_all, any_run = [], [], True, False
        for node in pel.iter():
            tag = ln(node)
            par = node.getparent()
            if tag == "oMath" and par is not None and ln(par) != "oMathPara": txt.append(" " + EX.omml(node) + " ")
            elif tag == "oMathPara": txt.append(" " + " ".join(EX.omml(x) for x in node if ln(x) == "oMath") + " ")
            elif tag == "t" and par is not None and ln(par) == "r" and etree.QName(par).namespace == W:
                if any(ln(x) == "oMath" for x in node.iterancestors()): continue
                txt.append(node.text or ""); any_run = True
                rpr = par.find(f"{{{W}}}rPr")
                if (node.text or "").strip() and not run_bold(rpr): bold_all = False
            elif tag in ("tab", "br") and etree.QName(node).namespace == W: txt.append(" ")
            elif tag == "blip":
                fn = image(node.get(f"{{{R}}}embed"))
                if fn: imgs.append(fn)
            elif tag == "imagedata" and etree.QName(node).namespace == _VML:
                fn = image(node.get(f"{{{R}}}id"))
                if fn: imgs.append(fn)
        text = re.sub(r"\s+", " ", "".join(txt)).strip()
        ppr = pel.find(f"{{{W}}}pPr")
        style, lvl, is_list = "", None, False
        if ppr is not None:
            ps = ppr.find(f"{{{W}}}pStyle")
            if ps is not None: style = styles.get(ps.get(f"{{{W}}}val"), (ps.get(f"{{{W}}}val") or "").lower())
            ol = ppr.find(f"{{{W}}}outlineLvl")
            if ol is not None:
                try: lvl = int(ol.get(f"{{{W}}}val") or 0) + 1
                except ValueError: lvl = None
            is_list = ppr.find(f"{{{W}}}numPr") is not None
        mh = re.search(r"(heading|заголовок|sarlavha)\s*(\d)", style)
        if mh: lvl = int(mh.group(2))
        elif style in ("title", "название"): lvl = 1
        if lvl is None and text and any_run and bold_all and len(text) <= 120 and not text.endswith((".", ",", ";")) and not CAPTION_RX.match(text): lvl = 2
        return text, lvl, is_list or "list" in style, imgs
    blocks, tables = [], {}
    body = doc.find(f"{{{W}}}body")
    def walk(parent):
        for el in parent:
            tag = ln(el)
            if tag == "sdt":
                c = el.find(f"{{{W}}}sdtContent")
                if c is not None: walk(c)
            elif tag == "p":
                text, lvl, is_list, imgs = para(el)
                if imgs and text and CAPTION_RX.match(text) and len(text) <= 300:     # rasm va izohi bitta paragrafda
                    for fn in imgs[:-1]: blocks.append(["img", fn])
                    blocks.append(["img", imgs[-1], text]); continue
                if text: blocks.append(["h", text, lvl] if lvl and lvl <= 3 else ["li" if is_list else "p", text])
                for fn in imgs: blocks.append(["img", fn])
            elif tag == "tbl":
                rows = []
                for tr in el.iter(f"{{{W}}}tr"):
                    cells = []
                    for tc in tr.findall(f"{{{W}}}tc"):
                        cells.append(" ".join(x for x in (para(pp)[0] for pp in tc.iter(f"{{{W}}}p")) if x))   # jadval ichidagi rasm — olinmaydi
                    if any(cells): rows.append(cells)
                if not rows: continue
                if len(rows) == 1 and len(rows[0]) == 1: blocks.append(["p", rows[0][0]]); continue   # bitta katak — oddiy matn
                n = str(len(tables) + 1); tables[n] = rows; blocks.append(["tbl", n])
    walk(body)
    # rasm izohlari: keyingi, bo'lmasa oldingi «N-rasm …» paragrafi
    drop = set()
    for i, b in enumerate(blocks):
        if b[0] != "img": continue
        if len(b) > 2: images[b[1]]["caption"] = images[b[1]]["caption"] or b[2]; continue
        for j in (i + 1, i - 1):
            if 0 <= j < len(blocks) and j not in drop and blocks[j][0] == "p" and CAPTION_RX.match(blocks[j][1]) and len(blocks[j][1]) <= 300:
                if not images[b[1]]["caption"]: images[b[1]]["caption"] = blocks[j][1]
                drop.add(j); break
    lines = []
    for i, b in enumerate(blocks):
        if i in drop: continue
        if b[0] == "h": lines.append("#" * max(1, min(3, b[2])) + " " + b[1])
        elif b[0] == "li": lines.append("- " + b[1])
        elif b[0] == "p": lines.append(b[1])
        elif b[0] == "img" and b[1] in images: lines.append(f"[RASM:{b[1]}]")
        elif b[0] == "tbl": lines.append(f"[JADVAL:{b[1]}]")
    used = {b[1] for i, b in enumerate(blocks) if b[0] == "img" and i not in drop}
    return {"text": "\n".join(lines), "images": {k: v for k, v in images.items() if k in used}, "tables": tables}

def _plain(text: str) -> str:
    """Belgilarsiz matn (AI va iqtibos tekshiruvi uchun): «[RASM:…]» / «[JADVAL:N]» qatorlari olib tashlanadi."""
    return "\n".join(l for l in str(text or "").split("\n") if not (_FIG_RX.match(l.strip()) or _TBL_RX.match(l.strip()) or _IMG_RX.match(l.strip())))

def _save_image_asset(c: Ctx | None, cid: int, no: int, fn: str, data: bytes, meta: dict, src="") -> int:
    ex = db.one(_con, "SELECT id FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='rasm' AND name=? AND deleted=0", (cid, no, fn))
    if ex and _apath(db.one(_con, "SELECT * FROM pk_assets WHERE id=?", (ex["id"],))).is_file(): return ex["id"]
    return _save_asset(c, cid, no, "rasm", fn.rsplit(".", 1)[-1], fn, data, meta, src)

def upload_text(c: Ctx, cid: int, no: int, raw: bytes | None, text: str | None, name: str) -> dict:
    """Ma'ruza matni: .docx (matn + rasmlar izohi bilan + jadvallar) / .pdf / .txt (faqat matn) yoki joylashtirilgan matn
    → pk_assets (purpose='matn', meta.text — belgilangan matn; meta.images / meta.tables — .docx dan)."""
    from . import taqdimot_extract as EX
    co = _course(c, cid, write=True); l = _check_topic(co, no)
    media = {"images": {}, "tables": {}}
    imgs = {}
    if raw is not None:
        _read_upload_guard(raw)
        if raw[:4] == b"PK\x03\x04":
            _zip_guard(raw); _ooxml_image_guard(raw, "word/media/")   # .docx: zip/rasm bombasi — tahlildan oldin
        try:
            kind = EX.sniff(raw)
            if kind == "docx":
                try: dx = docx_lecture(raw)
                except HTTPException: raise
                except Exception: raise EX.BadFile("Word faylni o'qib bo'lmadi (fayl buzilgan yoki .docx emas)")
                txt = dx["text"]; trunc = len(txt) > MAX_TEXT_CHARS; txt = txt[:MAX_TEXT_CHARS]
                imgs = {fn: v for fn, v in dx["images"].items() if f"[RASM:{fn}]" in txt}
                media = {"images": {fn: {"caption": v["caption"]} for fn, v in imgs.items()}, "tables": dx["tables"]}
            else:
                ex = EX.extract(raw, kind, None)
                txt, trunc = EX.as_text([b for b in ex["blocks"] if b.get("k") != "img"], MAX_TEXT_CHARS)
        except EX.BadFile as e:
            rbac.audit(_con, c, "paket: matn rad etildi", RES, False, f"{name[:60]} · {e}")
            raise HTTPException(415, str(e))
    else:
        txt = (text or "").strip(); kind = "txt"; name = name or "matn.txt"
        trunc = len(txt) > MAX_TEXT_CHARS; txt = txt[:MAX_TEXT_CHARS]
        raw = txt.encode("utf-8")
    if len(_plain(txt)) < 100: raise HTTPException(400, f"Ma'ruza matni juda qisqa ({len(_plain(txt))} belgi)")
    st = structure_text(txt, l["title"], media)
    aid = _save_asset(c, cid, no, "matn", kind, name, raw, {"text": txt, "chars": len(txt), "truncated": bool(trunc), "plan": st["plan"],
                                                           "images": media["images"], "tables": media["tables"], "refs": len(st["refs"])})
    for fn, v in imgs.items():
        _save_image_asset(c, cid, no, fn, v["data"], {"caption": v["caption"], "src": "docx", "text_asset": aid})
    with _lock: _log(c, cid, no, "matn yuklandi", f"{name[:80]} · {len(txt)} belgi · {len(imgs)} rasm · {len(media['tables'])} jadval"); _con.commit()
    rbac.audit(_con, c, "paket: ma'ruza matni yuklandi", RES, True, f"kurs #{cid} · {l['code']} · {name[:60]} · {len(txt)} belgi")
    return {"ok": True, "id": aid, "chars": len(txt), "truncated": bool(trunc), "plan": st["plan"], "images": len(imgs),
            "tables": len(media["tables"]), "refs": len(st["refs"])}

def upload_image(c: Ctx, cid: int, no: int, raw: bytes, name: str, caption: str = "") -> dict:
    """Darsning «rasmlar»iga qo'lda rasm (.png/.jpg): matnda «[RASM:fayl]» qatori bilan joylanadi; havola qilinmaganlari matn oxirida."""
    co = _course(c, cid, write=True); l = _check_topic(co, no)
    _read_upload_guard(raw)
    if _sniff_asset(raw) not in ("png", "jpg"): raise HTTPException(415, "Rasm: .png yoki .jpg")
    r = _norm_image(raw, strict=True)
    if not r: raise HTTPException(415, "Rasmni o'qib bo'lmadi yoki juda kichik")
    fn = f"{_sha(r[0])[:20]}.{r[1]}"
    caption = re.sub(r"\s+", " ", caption or "").strip()[:300]
    aid = _save_image_asset(c, cid, no, fn, r[0], {"caption": caption, "src": "manual", "orig": name[:160]})
    with _lock:
        a = db.one(_con, "SELECT meta FROM pk_assets WHERE id=?", (aid,))
        m = json.loads(a["meta"] or "{}"); m.update(caption=caption or m.get("caption", ""), src="manual")
        _con.execute("UPDATE pk_assets SET meta=? WHERE id=?", (json.dumps(m, ensure_ascii=False), aid))
        _log(c, cid, no, "rasm yuklandi", f"{name[:80]} → {fn}"); _con.commit()
    rbac.audit(_con, c, "paket: rasm yuklandi", RES, True, f"kurs #{cid} · {l['code']} · {fn}")
    return {"ok": True, "id": aid, "file": fn, "marker": f"[RASM:{fn}]", "caption": caption}

# --- PDF taqdimot → slayd rasmlari (pypdfium2) -------------------------------------------------------------------------
PDF_MAX_PAGES = 120
PDF_PX = 1600                       # sahifa kengligi (px)
PDF_MAX_TOTAL_PX = 250_000_000      # barcha sahifalar yig'indisi — «rasm bombasi» himoyasi

_PDFIUM_LOCK = threading.Lock()     # PDFium thread-safe emas: pypdfium2 bilan har qanday ish (ochish, chizish, yopish) — faqat shu qulf ostida

def render_pdf(raw: bytes) -> dict:
    """PDF → {"pages": n, "images": [jpeg baytlari], "truncated": bool}. Har sahifa ~1600 px kenglikda; ko'pi bilan PDF_MAX_PAGES sahifa,
    sahifa ≤ IMG_MAX_PIXELS, umumiy ≤ PDF_MAX_TOTAL_PX (oshsa — qolgan sahifalar chizilmaydi, truncated).
    Butun ish _PDFIUM_LOCK ostida (PDFium bir vaqtda faqat bitta oqimda). Sahifani o'lchash/chizishdagi har qanday xato → 415."""
    import pypdfium2 as pdfium
    with _PDFIUM_LOCK:
        try:
            doc = pdfium.PdfDocument(raw)
        except Exception:
            raise HTTPException(415, "PDF faylni o'qib bo'lmadi (buzilgan yoki parol bilan himoyalangan)")
        out, total, trunc = [], 0, False
        try:
            n = len(doc)
            if not n: raise HTTPException(415, "PDF faylda sahifa yo'q")
            for i in range(min(n, PDF_MAX_PAGES)):
                page = doc[i]
                try:
                    w, h = page.get_width(), page.get_height()
                    if w <= 0 or h <= 0: continue
                    scale = min(PDF_PX / w, (PDF_PX * 3) / h)
                    px = int(w * scale) * int(h * scale)
                    if px > IMG_MAX_PIXELS: continue
                    if total + px > PDF_MAX_TOTAL_PX: trunc = True; break
                    total += px
                    im = page.render(scale=scale).to_pil().convert("RGB")
                    bio = io.BytesIO(); im.save(bio, "JPEG", quality=84, optimize=True); out.append(bio.getvalue())
                finally:
                    page.close()
            trunc = trunc or n > PDF_MAX_PAGES
        except HTTPException:
            raise
        except Exception as e:      # pdfium.PdfiumError, MemoryError, PIL xatolari …
            raise HTTPException(415, f"PDF sahifalarini rasmga aylantirib bo'lmadi (fayl buzilgan yoki qo'llab-quvvatlanmaydi: {type(e).__name__})")
        finally:
            doc.close()
    if not out: raise HTTPException(415, "PDF sahifalarini rasmga aylantirib bo'lmadi")
    return {"pages": n, "images": out, "truncated": trunc}

def _retire_taqdimot(c: Ctx | None, cid: int, no: int, kind: str, keep: int) -> int:
    """Yangi taqdimot (.pdf yoki .pptx) yuklanganda shu darsning o'sha turdagi eski taqdimotlari «almashtirildi» (deleted=2) — paketga
    kirmaydi va ro'yxatda ko'rinmaydi; fayllari diskda qoladi (eski paket versiyalari o'z zipida to'liq, fayl kerak bo'lsa tiklash mumkin)."""
    with _lock:
        n = _con.execute("UPDATE pk_assets SET deleted=2 WHERE course_id=? AND topic_no=? AND purpose='taqdimot' AND kind=? AND deleted=0 AND id<>?",
                         (cid, no, kind, keep)).rowcount
        if n: _log(c, cid, no, "taqdimot almashtirildi", f"{n} ta eski .{kind}")
        _con.commit()
    return n

def upload_slides(c: Ctx, cid: int, no: int, raw: bytes, name: str) -> dict:
    """Taqdimot: .pptx (tahlil + rasmlar) / .pdf (har sahifa → slayd rasmi, pypdfium2) / .png / .jpg (slayd rasmlari to'plami)."""
    co = _course(c, cid, write=True); l = _check_topic(co, no)
    _read_upload_guard(raw)
    kind = _sniff_asset(raw)
    if kind == "ole": raise HTTPException(415, "Eski .ppt formati qabul qilinmaydi — PowerPoint'da «.pptx» qilib saqlang")
    if kind not in ("pptx", "pdf", "png", "jpg"):
        raise HTTPException(415, "Taqdimot uchun .pptx, .pdf yoki slayd rasmlari (.png, .jpg) qabul qilinadi")
    meta, imgs, parsed, pdf = {}, {}, None, None
    if kind == "pptx":
        parsed = parse_pptx(raw, None, imgs)      # bir marta: avval tekshiruv (buzilgan fayl saqlanmasin), rasmlar xotirada
        meta = {"count": parsed["count"]}
    elif kind == "pdf":
        try:
            pdf = render_pdf(raw)
        except HTTPException as e:
            rbac.audit(_con, c, "paket: PDF taqdimot rad etildi", RES, False, f"kurs #{cid} · {l['code']} · {name[:60]} · {e.detail}"[:300])
            raise
        for i, b in enumerate(pdf["images"], 1): imgs[f"p{i}.jpg"] = b
        meta = {"pages": pdf["pages"], "rendered": len(pdf["images"]), "truncated": pdf["truncated"], "images": list(imgs)}
    else:
        r = _norm_image(raw, strict=True)
        if not r: raise HTTPException(415, "Rasmni o'qib bo'lmadi yoki juda kichik")
        raw, kind = r
    purpose = "slayd" if kind in ("png", "jpg") else "taqdimot"
    aid = _save_asset(c, cid, no, purpose, kind, name, raw, meta)
    if purpose == "taqdimot":
        _retire_taqdimot(c, cid, no, kind, aid)
    if kind in ("pptx", "pdf"):
        a = db.one(_con, "SELECT * FROM pk_assets WHERE id=?", (aid,))
        if imgs:
            d = _img_dir(a); d.mkdir(parents=True, exist_ok=True)
            for fn, b in imgs.items(): (d / fn).write_bytes(b)
        if kind == "pptx":
            with _lock:
                _con.execute("UPDATE pk_assets SET meta=? WHERE id=?", (json.dumps({"count": parsed["count"], "slides": parsed["slides"]}, ensure_ascii=False), aid))
                _con.commit()
            meta = {"count": parsed["count"], "images": sum(1 for s in parsed["slides"] if s["image"])}
        else:
            meta = {"pages": pdf["pages"], "count": len(pdf["images"]), "images": len(pdf["images"]), "truncated": pdf["truncated"]}
    with _lock: _log(c, cid, no, "taqdimot yuklandi", f"{name[:80]} · {kind}"); _con.commit()
    rbac.audit(_con, c, "paket: taqdimot yuklandi", RES, True, f"kurs #{cid} · {l['code']} · {name[:60]} · {kind}")
    return {"ok": True, "id": aid, "kind": kind, **meta}

FILE_KINDS = ("pdf", "docx", "pptx", "xlsx", "png", "jpg")

def upload_file(c: Ctx, cid: int, no: int, raw: bytes, name: str) -> dict:
    co = _course(c, cid, write=True); _check_topic(co, no)
    _read_upload_guard(raw)
    kind = _sniff_asset(raw)
    if kind not in FILE_KINDS: raise HTTPException(415, "Qo'shimcha fayl: .pdf, .docx, .pptx, .xlsx, .png, .jpg")
    aid = _save_asset(c, cid, no, "fayl", kind, name, raw, {})
    with _lock: _log(c, cid, no, "fayl yuklandi", name[:80]); _con.commit()
    rbac.audit(_con, c, "paket: qo'shimcha fayl", RES, True, f"kurs #{cid} · {lesson_code(no)} · {name[:60]}")
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

def _src_topic(cid: int, no: int, les: dict | None) -> int | None:
    return source_topic(les if les is not None else _lesson_of(cid, no))

def _text_source(cid: int, no: int, les: dict | None = None) -> dict | None:
    """Ma'ruza matni: darsning o'zi uchun yuklangan > Test bank mavzu matni (dars bog'langan mavzu — source_topic)."""
    a = _latest_asset(cid, no, "matn")
    if a:
        m = json.loads(a["meta"] or "{}")
        return {"src": "paket", "name": a["name"], "kind": a["kind"], "text": m.get("text") or "", "chars": m.get("chars") or 0, "ts": a["ts"],
                "by": _short(a["user_name"]), "asset": a, "demo": a["src"] == "demo", "images": m.get("images") or {}, "tables": m.get("tables") or {}}
    tno = _src_topic(cid, no, les)
    if not tno: return None         # Test bank — mavzu bo'yicha; bog'lanmagan A/S/Lab/MT darslari uchun zaxira manba yo'q
    if db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_sources'"):
        s = db.one(_con, "SELECT * FROM tb_sources WHERE course_id=? AND topic_no=? ORDER BY id DESC LIMIT 1", (cid, tno))
        if s: return {"src": "testbank", "name": s["name"], "kind": s["kind"], "text": s["text"] or "", "chars": s["chars"], "ts": s["ts"],
                      "by": _short(s["user_name"]), "asset": None, "demo": s["src"] == "demo", "images": {}, "tables": {}}
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

def _video_source(cid: int, no: int, les: dict | None = None) -> dict | None:
    """Video: darsga kiritilgan havola > kontent monitoringidagi videodars (dars bog'langan mavzu — source_topic)."""
    tr = _topic_row(cid, no)
    if tr.get("video_url"):
        v = parse_video(tr["video_url"]); return {"src": "paket", "raw": tr["video_url"], "demo": tr.get("src") == "demo", **v}
    tno = _src_topic(cid, no, les)
    if not tno: return None
    it = db.one(_con, "SELECT url FROM dl_items WHERE course_id=? AND topic_no=? AND kind='video' AND url IS NOT NULL AND url!='' ORDER BY id DESC LIMIT 1", (cid, tno))
    if it:
        v = parse_video(it["url"]); return {"src": "monitoring", "raw": it["url"], "demo": False, **v}
    return None

def _quiz_rows(cid: int, no: int, les: dict | None = None) -> list[dict]:
    """Test: Test bankdagi tasdiqlangan savollar — dars bog'langan mavzu (source_topic) bo'yicha."""
    tno = _src_topic(cid, no, les)
    if not tno: return []
    if not db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_questions'"): return []
    return db.rows(_con, "SELECT * FROM tb_questions WHERE course_id=? AND topic_no=? AND status='tasdiqlandi' AND deleted=0 ORDER BY id", (cid, tno))

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

def _lesson_images(cid: int, no: int) -> dict:
    """Darsning rasmlari {fayl: {"path", "caption", "src" (docx|manual), "id"}} — oxirgi yuklangani (diskda borlari)."""
    out = {}
    for a in db.rows(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='rasm' AND deleted=0 ORDER BY id", (cid, no)):
        if not _apath(a).is_file(): continue
        m = json.loads(a["meta"] or "{}")
        out[a["name"]] = {"path": _apath(a), "caption": m.get("caption") or "", "src": m.get("src") or "manual", "id": a["id"]}
    return out

def keypoints_state(cid: int, no: int) -> dict:
    try: return json.loads(_topic_row(cid, no).get("keypoints") or "{}") or {}
    except ValueError: return {}

def _pdf_slides(pdf: dict) -> list[str]:
    """PDF taqdimotdan chizilgan sahifa rasmlari (diskda borlari, tartibda)."""
    m = json.loads(pdf["meta"] or "{}")
    d = _img_dir(pdf)
    return [fn for fn in (m.get("images") or []) if (d / fn).is_file()]

def gather(cid: int, no: int, co: dict | None = None, settings: dict | None = None, les: dict | None = None) -> dict:
    """Dars manbalari → {"content" (built/id/v dan tashqari), "files": {zip yo'li: Path|bytes}, "ready": {...}, "settings", "lesson"}.
    Bloklar tartibi (kafedra shabloni): bo'lim «VIDEODARS» → video → bo'lim «MA'RUZA MATNI» → reja (sarlavha bilan) → matn → asosiy xulosalar
    → adabiyotlar → bo'lim «DARS TAQDIMOTI» → taqdimot → qo'shimcha fayllar → test → o'z-o'zini baholash. Manbasi yo'q blok (va bo'limi) tushadi."""
    co = co or db.one(_con, "SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id "
                            "LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.id=?", (cid,))
    if not co: raise HTTPException(404, "Kurs topilmadi")
    les = les or lesson_info(co, no)
    st = settings or topic_settings(cid, no)[0]
    on, sec = st["blocks"], st["sections"]
    title = les["title"]
    files: dict[str, object] = {}
    ready = {}
    # matn, rasmlar, jadvallar, reja, adabiyotlar
    ts = _text_source(cid, no, les)
    limgs = _lesson_images(cid, no)
    media = {"images": {fn: {"caption": ((ts or {}).get("images") or {}).get(fn, {}).get("caption") or v["caption"]} for fn, v in limgs.items()},
             "tables": (ts or {}).get("tables") or {}}
    stx = structure_text(ts["text"], title, media) if ts else {"plan": [], "html": "", "explicit_plan": False, "refs": [], "images": []}
    html_text = stx["html"]
    used = list(stx["images"])
    extra_figs = [fn for fn, v in limgs.items() if v["src"] == "manual" and fn not in used]   # qo'lda yuklangan, matnda havolasi yo'q — matn oxirida
    if extra_figs and (html_text or not ts):
        html_text += sanitize("".join(_fig_html(fn, media) for fn in extra_figs)); used += extra_figs
    ready["text"] = {"ok": bool(ts and stx["html"]), "src": ts["src"] if ts else None, "name": ts["name"] if ts else None,
                     "chars": ts["chars"] if ts else 0, "ts": ts["ts"] if ts else None, "by": ts["by"] if ts else None, "demo": bool(ts and ts["demo"])}
    ready["plan"] = {"ok": bool(stx["plan"]), "n": len(stx["plan"]), "explicit": stx["explicit_plan"], "items": stx["plan"], "heading": _lesson_heading(les)}
    ready["images"] = {"ok": bool(used), "n": len(used), "uploaded": len(limgs), "manual": sum(1 for v in limgs.values() if v["src"] == "manual"),
                       "tables": html_text.count("<table>")}
    ready["refs"] = {"ok": bool(stx["refs"]), "n": len(stx["refs"]), "items": stx["refs"]}
    kp = keypoints_state(cid, no)
    kp_items = [str(x) for x in ((kp.get("approved") or {}).get("items") or []) if str(x).strip()]
    ready["keypoints"] = {"ok": bool(kp_items), "n": len(kp_items), "draft": len(((kp.get("draft") or {}).get("items") or []))}
    # taqdimot: PDF sahifa rasmlari (aniq ko'rinish) > .pptx (matn + eng katta rasm) > «Taqdimot» moduli > slayd rasmlari.
    # Eng oxirgi yuklangani hal qiladi: .pptx PDF'dan KEYIN yuklangan bo'lsa — PDF eskirgan (boshqa/oldingi taqdimot), ishlatilmaydi.
    pptx = _latest_asset(cid, no, "taqdimot", ("pptx",))
    pdf = _latest_asset(cid, no, "taqdimot", ("pdf",))
    if pptx and pdf and pptx["id"] > pdf["id"]: pdf = None
    tr = _topic_row(cid, no)
    slides, ssrc, file_path = [], None, None
    pslides = []
    if pptx:
        m = json.loads(pptx["meta"] or "{}")
        idir = _img_dir(pptx)
        for i, sl in enumerate(m.get("slides") or [], 1):
            img = None
            if sl.get("image") and (idir / sl["image"]).is_file():
                ext = sl["image"].rsplit(".", 1)[-1]
                img = (f"assets/slides/s{i}.{ext}", idir / sl["image"])
            pslides.append({"title": sl.get("title") or "", "bullets": list(sl.get("bullets") or []), "notes": sl.get("notes") or "", "image": img})
        file_path = _apath(pptx)
    pdf_imgs = _pdf_slides(pdf) if pdf else []
    if pdf_imgs:
        same = len(pslides) == len(pdf_imgs)          # .pptx va PDF — bitta taqdimot: sarlavha/izohlar .pptx dan
        for i, fn in enumerate(pdf_imgs, 1):
            pth = f"assets/slides/p{i}.jpg"; files[pth] = _img_dir(pdf) / fn
            src_s = pslides[i - 1] if same else {}
            slides.append({"title": src_s.get("title") or "", "bullets": list(src_s.get("bullets") or []), "notes": src_s.get("notes") or "", "image": pth})
        ssrc = "pdf"
    elif pslides:
        for sl in pslides:
            if sl["image"]: files[sl["image"][0]] = sl["image"][1]
            slides.append({**sl, "image": sl["image"][0] if sl["image"] else None})
        ssrc = "pptx"
    deck = None
    if not slides and tr.get("deck_id"):
        dsl, dpptx, deck = _deck_slides(int(tr["deck_id"]))
        if dsl:
            slides, ssrc = dsl, "deck"
            if dpptx and not file_path: file_path = dpptx
    if not slides:
        imgs = _image_slides(cid, no)
        for i, a in enumerate(imgs, 1):
            pth = f"assets/slides/s{i}.{a['kind']}"; files[pth] = _apath(a)
            slides.append({"title": "", "bullets": [], "notes": "", "image": pth})
        if imgs: ssrc = "images"
    if not ssrc and pdf: ssrc = "pdf"
    display = "images" if slides and all(x["image"] for x in slides) else "text"
    sb = {"type": "slides", "title": "Taqdimot", "display": display, "slides": slides, "file": None, "pdf": None}
    if file_path: sb["file"] = "assets/taqdimot.pptx"; files["assets/taqdimot.pptx"] = file_path
    if pdf: sb["pdf"] = "assets/taqdimot.pdf"; files["assets/taqdimot.pdf"] = _apath(pdf)
    has_slides = bool(slides or sb["file"] or sb["pdf"])
    ready["slides"] = {"ok": has_slides, "src": ssrc, "n": len(slides), "file": bool(sb["file"]), "pdf": bool(sb["pdf"]), "display": display,
                       "images": sum(1 for x in slides if x["image"]), "deck_id": tr.get("deck_id"), "deck_title": deck["title"] if deck else None,
                       "pdf_pages": json.loads(pdf["meta"] or "{}").get("pages") if pdf else None}
    if not (on["slides"] and has_slides):
        for k in [k for k in files if k.startswith("assets/slides/") or k in ("assets/taqdimot.pptx", "assets/taqdimot.pdf")]: files.pop(k)
    # video
    v = _video_source(cid, no, les)
    ready["video"] = {"ok": bool(v and v["ok"]), "src": v["src"] if v else None, "url": (v.get("url") or v.get("raw")) if v else None,
                      "provider": v.get("provider") if v else None, "video_id": v.get("video_id") if v else None,
                      "error": v.get("error") if v and not v["ok"] else None, "demo": bool(v and v.get("demo"))}
    # qo'shimcha fayllar (+ asl ma'ruza fayli)
    extra = db.rows(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='fayl' AND deleted=0 ORDER BY id", (cid, no))
    extra = [a for a in extra if _apath(a).is_file()]
    if ts and ts["asset"] and ts["asset"]["kind"] in ("docx", "pdf") and _apath(ts["asset"]).is_file(): extra = [{**ts["asset"], "name": "Ma'ruza matni (asl fayl)." + ts["asset"]["kind"]}] + extra
    used_names, fblocks = set(), []
    for a in extra:
        stem = _ascii(Path(a["name"]).stem, 40).lower()
        nm = f"assets/files/{stem}.{a['kind']}"
        k = 2
        while nm in used_names: nm = f"assets/files/{stem}_{k}.{a['kind']}"; k += 1
        used_names.add(nm)
        fblocks.append(({"type": "file", "title": Path(a["name"]).stem[:160] or "Fayl", "href": nm, "size": int(a["size"] or 0)}, nm, _apath(a)))
    ready["files"] = {"ok": bool(fblocks), "n": len(fblocks)}
    # test
    rows = _quiz_rows(cid, no, les)
    picked = _pick_questions(rows, st["quiz_n"], cid, no)
    ready["quiz"] = {"ok": bool(rows), "approved": len(rows), "used": len(picked)}
    rf = st["reflect"]
    ready["reflect"] = {"ok": bool(on.get("reflect")), "question": rf["question"]}
    # bloklar — shablon tartibida
    blocks = []
    def section(key, group):
        if not group: return
        if on.get("sections"): blocks.append({"type": "section", "title": sec[key]})
        blocks.extend(group)
    vg = []
    if on["video"] and v and v["ok"]:
        if v["provider"] == "youtube":
            vg.append({"type": "video", "title": "Videodars", "provider": "youtube", "video_id": v["video_id"], "url": v["url"], "start": v["start"]})
        else:
            vg.append({"type": "text", "title": "Videodars", "html": sanitize(
                f'<p>Videodars tashqi saytda joylashgan:</p><p><a href="{html.escape(v["url"], quote=True)}">{html.escape(v["url"])}</a></p>')})
    section("video", vg)
    tg = []
    if on["plan"] and stx["plan"]: tg.append({"type": "plan", "title": "Reja", "heading": _lesson_heading(les), "items": stx["plan"]})
    if on["text"] and html_text: tg.append({"type": "text", "title": "Ma'ruza matni", "html": html_text})
    if on.get("keypoints") and kp_items: tg.append({"type": "keypoints", "title": "Asosiy xulosalar", "items": kp_items})
    if on.get("refs") and stx["refs"]: tg.append({"type": "refs", "title": "Foydalanilgan adabiyotlar", "items": stx["refs"]})
    section("text", tg)
    if on["text"] and html_text:
        for fn in used:
            if fn in limgs: files[f"assets/img/{fn}"] = limgs[fn]["path"]
    section("slides", [sb] if on["slides"] and has_slides else [])
    if on["files"]:
        for b_, nm, pth in fblocks: blocks.append(b_); files[nm] = pth
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
    content_blocks = [b_ for b_ in blocks if b_["type"] != "section"]
    if on.get("reflect") and content_blocks:
        blocks.append({"type": "reflect", "title": rf["title"], "question": rf["question"], "options": [dict(o) for o in rf["options"]]})
    blocks = [{"id": f"b{i}", **b_} for i, b_ in enumerate(blocks, 1)]
    has_quiz = any(b_["type"] == "quiz" for b_ in blocks)
    completion = st["completion"] if has_quiz else "view_all"
    activity = f"{ACTIVITY_BASE}/{int(cid)}/{int(no)}" if les["kind"] == "maruza" else f"{ACTIVITY_BASE}/{int(cid)}/{les['code']}"
    content = {"v": 1, "title": title, "lang": "uz", "layout": st["layout"],
               "course": {"subject": co["subject"] or "", "direction": co["direction"] or "", "course": int(co["course"] or 0),
                          "kafedra": co.get("dept") or "", "teacher": _short(co.get("teacher") or "")},
               "topic": {"no": int(les["no"]), "title": title},
               "lesson": {"code": les["code"], "kind": les["kind"], "no": int(les["no"]), "title": title},
               "brand": {"name": "ISFT", "full": _brand_full(), "color": BRAND_COLOR, "logo": "assets/logo.png"},
               "blocks": blocks,
               "tracking": {"mode": st["mode"], "completion": completion, "mastery": st["mastery"], "activity_id": activity}}
    logo = _logo_path()
    if logo: files["assets/logo.png"] = logo
    else: content["brand"]["logo"] = None
    req = [k for k in REQUIRED if on.get(k)]
    ready["complete"] = all(ready[k]["ok"] for k in req)
    ready["missing"] = [k for k in req if not ready[k]["ok"]]
    ready["blocks"] = len(blocks)
    ready["buildable"] = any(b_["type"] in ("text", "slides", "video", "file") for b_ in blocks)
    return {"content": content, "files": files, "ready": ready, "settings": st, "course": co, "lesson": les}

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
                                                 "description": f"{c.get('subject', '')} · {(content.get('lesson') or {}).get('code') or str((content.get('topic') or {}).get('no', '')) + '-mavzu'}",
                                                 "launch": "index.html"}]).encode("utf-8")
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
BLOCK_TYPES = {"section", "plan", "text", "keypoints", "refs", "slides", "video", "file", "quiz", "reflect"}
_IMG_SRC_RX = re.compile(r"<img\b[^>]*\ssrc=\"([^\"]*)\"", re.I)

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
    if c.get("layout") not in (None, "steps", "scroll"): errors.append(f"{where}: layout noto'g'ri")
    for k in ("id", "title", "blocks", "tracking", "course", "topic", "brand"):
        if k not in c: errors.append(f"{where}: «{k}» yo'q")
    refs = []
    if (c.get("brand") or {}).get("logo"): refs.append(c["brand"]["logo"])
    ids = set()
    for b in c.get("blocks") or []:
        if b.get("type") not in BLOCK_TYPES: errors.append(f"{where}: noma'lum blok turi {b.get('type')!r}")
        if b.get("id") in ids: errors.append(f"{where}: blok id takrorlangan {b.get('id')}")
        ids.add(b.get("id"))
        if b.get("type") == "text":
            if (bad := html_unsafe(b.get("html") or "")): errors.append(f"{where}: matn blokida xavfli HTML ({bad})")
            refs += [html.unescape(x) for x in _IMG_SRC_RX.findall(b.get("html") or "")]
        if b.get("type") == "section" and not str(b.get("title") or "").strip(): errors.append(f"{where}: bo'lim sarlavhasi bo'sh")
        if b.get("type") in ("refs", "keypoints") and not (isinstance(b.get("items"), list) and all(isinstance(x, str) for x in b["items"]) and b["items"]):
            errors.append(f"{where}: {b.get('type')} bloki — items (matnlar ro'yxati) kerak")
        if b.get("type") == "reflect" and not (isinstance(b.get("options"), list) and len(b["options"]) >= 2 and str(b.get("question") or "").strip()):
            errors.append(f"{where}: reflect bloki — savol va kamida 2 javob kerak")
        if b.get("type") == "slides" and b.get("display") not in (None, "images", "text"): errors.append(f"{where}: slides.display noto'g'ri")
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
                          sha256,validation,readiness,src,lesson) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (cid, no, version, mode, status, json.dumps(settings), fp, _now(), c.user["id"] if c else None,
                        c.user["full_name"] if c else "Tizim", str(Path("packages") / str(cid) / str(no) / fn), len(data), _sha(data),
                        json.dumps(val, ensure_ascii=False), json.dumps(ready, ensure_ascii=False), src, lesson_code(no) if no else "kurs")).lastrowid
    return pid

def _build_settings(cid: int, no: int, mode: str | None) -> dict:
    st = topic_settings(cid, no)[0]
    if mode:
        if mode not in MODES: raise HTTPException(400, "Paket turi noma'lum")
        st["mode"] = mode
    return st

def build_topic(c: Ctx | None, cid: int, no: int, mode: str | None = None, force: bool = False, src: str = "",
                co: dict | None = None, les: dict | None = None, pre: tuple | None = None) -> dict:
    """Mavzu paketini yig'ish → {ok, package, unchanged, validation}. c=None — tizim (demo).
    co / les / pre=(sozlama, gather natijasi) — ommaviy yig'ishda tayyor holda beriladi (kurs, dars va manbalar qayta hisoblanmaydi)."""
    if co is None:
        co = _course(c, cid, write=True) if c else db.one(_con, "SELECT c.*, d.name dept, t.full_name teacher FROM dl_courses c LEFT JOIN departments d "
                                                             "ON d.id=c.department_id LEFT JOIN teachers t ON t.id=c.teacher_id WHERE c.id=?", (cid,))
    if not co: raise HTTPException(404, "Kurs topilmadi")
    les = les or _check_topic(co, no)
    st, g = pre if pre else (None, None)
    if g is None:
        st = _build_settings(cid, no, mode)
        g = gather(cid, no, co, st, les)
    if not g["ready"]["buildable"]:
        raise HTTPException(400, "Paket uchun kamida bitta kontent bloki kerak: ma'ruza matni, taqdimot yoki video")
    les = g["lesson"]
    pf = player_files()
    fp = _fingerprint(g["content"], g["files"], st["mode"], pf)
    with _lock:
        last = db.one(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC LIMIT 1", (cid, no))
        same = db.one(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? AND mode=? ORDER BY version DESC LIMIT 1", (cid, no, st["mode"]))
        if same and not force and same["content_hash"] == fp and (store() / same["file"]).is_file():   # shu tur bo'yicha (boshqa tur yig'ilgan bo'lsa ham)
            return {"ok": True, "unchanged": True, "package": pack_row(same)}
        version = (last["version"] if last else 0) + 1
        content = {"v": 1, "id": f"isft-{int(cid)}-{int(no)}-v{version}", **{k: v for k, v in g["content"].items() if k != "v"}, "built": _now()}
        content = {k: content[k] for k in ("v", "id", "title", "lang", "layout", "course", "topic", "lesson", "brand", "built", "blocks", "tracking")}
        data = build_zip(content, g["files"], st["mode"])
        val = validate_zip(data)
        if not val["ok"]:
            _log(c, cid, no, "yig'ish xatosi", "; ".join(val["errors"])[:400]); _con.commit()
            if c: rbac.audit(_con, c, "paket: tekshiruvdan o'tmadi", RES, True, f"kurs #{cid} · {lesson_code(no)} · {val['errors'][:2]}")
            raise HTTPException(422, "Paket tekshiruvdan o'tmadi: " + "; ".join(val["errors"][:3]))
        status = "tayyor" if g["ready"]["complete"] else "qoralama"
        pid = _store_package(c, cid, no, data, st["mode"], status, st, fp, val, {k: (v["ok"] if isinstance(v, dict) else v) for k, v in g["ready"].items()},
                             version, src)
        _log(c, cid, no, "yig'ildi", f"v{version} · {MODES[st['mode']]} · {status}", pid)
        _prune(cid, no)
        _con.commit()
    if c: rbac.audit(_con, c, "paket: yig'ildi", RES, True, f"kurs #{cid} · {lesson_code(no)} · v{version} · {st['mode']} · {len(data)} bayt")
    return {"ok": True, "unchanged": False, "package": pack_row(db.one(_con, "SELECT * FROM pk_packages WHERE id=?", (pid,))), "validation": val}

def build_course(c: Ctx, cid: int, mode: str = "scorm12", only_approved: bool = False) -> dict:
    """«Kurs paketi»: bitta manifest, har dars — alohida SCO (o'z papkasida: L — tNN/, A — aNN/, S — sNN/, Lab — labNN/, MT — mtNN/).
    Darslar — oxirgi tasdiqlangan (yoki oxirgi) dars paketidan; tartib: L, A, S, Lab, MT."""
    co = _course(c, cid, write=True)
    if mode not in ("scorm12", "scorm2004", "xapi"): raise HTTPException(400, "Kurs paketi: SCORM 1.2, SCORM 2004 yoki xAPI")
    entries, scos, acts, used = {}, [], [], []
    for les in lessons(cid, co):
        no = les["key"]
        rows = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC", (cid, no))
        pick = next((r for r in rows if r["status"] == "tasdiqlandi"), None) or (None if only_approved else (rows[0] if rows else None))
        if not pick or not (store() / pick["file"]).is_file(): continue
        pre = f"t{les['no']:02d}/" if les["kind"] == "maruza" else f"{KINDS[les['kind']][0].lower()}{les['no']:02d}/"
        with zipfile.ZipFile(store() / pick["file"]) as z:
            for nm in z.namelist():
                if nm.endswith("/") or nm in ("imsmanifest.xml", "tincan.xml"): continue
                entries[pre + nm] = z.read(nm)
        t = entries[pre + "content.js"].decode("utf-8")
        cj = json.loads(t[len("window.PAKET = "):-1])
        cj["tracking"]["mode"] = mode
        entries[pre + "content.js"] = content_js(cj)
        entries[pre + "content.json"] = json.dumps(cj, ensure_ascii=False, indent=1).encode("utf-8")
        title = f"{les['code']}. {cj.get('title') or ''}"
        scos.append({"ident": f"SCO-{les['code']}", "title": title, "href": pre + "index.html", "prefix": pre, "mastery": _sco_mastery(cj)})
        acts.append({"id": cj["tracking"]["activity_id"], "name": title, "description": co["subject"] or "", "launch": pre + "index.html"})
        used.append({"no": no, "code": les["code"], "version": pick["version"], "status": pick["status"]})
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
            "readiness": json.loads(r["readiness"] or "{}"), "settings": json.loads(r["settings"] or "{}"),
            "lesson": r.get("lesson") or (lesson_code(r["topic_no"]) if r["topic_no"] else "kurs")}

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
    """ISFT_<fan>_<dars kodi>_<tur>.zip — L01 (ma'ruza), A01 (amaliy), S01, Lab01, MT01; kurs paketi — «kurs». NEXTID'dagi L/A nomlariga mos."""
    return f"ISFT_{_ascii(co['subject'], 50)}_{'kurs' if not no else lesson_file_code(int(no))}_{mode}.zip"


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

def preview_redirect(c: Ctx, pid: int, path: str, query: str = "") -> Response:
    """Imzolangan yo'lga 302; so'rov qatori (masalan «?preview=1» — pleyer «Ko'rish rejimi» bannerini ko'rsatadi) saqlanadi."""
    _package(c, pid)                                     # ko'lam (begona kurs — 403 + audit)
    path = _preview_path(c, pid, path)
    q = "&".join(x for x in (query or "").split("&") if re.fullmatch(r"[A-Za-z0-9_]{1,30}=[A-Za-z0-9_.\-]{0,60}", x))[:300]
    return RedirectResponse(f"{P}/pv/{preview_token(pid, c.user['id'])}/{quote(path, safe='/')}" + (f"?{q}" if q else ""), 302,
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
    """{(cid, no): {"text", "slides", "video", "quiz"}} — butun institut bo'yicha, tez (matn tahlilisiz).
    Zaxira manbalar (Test bank matni/savollari, monitoring videosi) — mavzu bo'yicha; mavzuga bog'langan (topic_ref) darslarga ham o'tadi (gather kabi)."""
    out = {}
    def mark(k, cid, no):
        out.setdefault((cid, no), {"text": False, "slides": False, "video": False, "quiz": False})[k] = True
    has = lambda t: bool(db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)))
    tb_text = {(r["course_id"], r["topic_no"]) for r in db.rows(_con, "SELECT DISTINCT course_id, topic_no FROM tb_sources")} if has("tb_sources") else set()
    tb_quiz = ({(r["course_id"], r["topic_no"]) for r in db.rows(_con, "SELECT DISTINCT course_id, topic_no FROM tb_questions WHERE status='tasdiqlandi' AND deleted=0")}
               if has("tb_questions") else set())
    mon = {}
    for r in db.rows(_con, "SELECT course_id, topic_no, url FROM dl_items WHERE kind='video' AND url IS NOT NULL AND url!=''"): mon[(r["course_id"], r["topic_no"])] = r["url"]
    # dars → manba mavzusi: L — o'zi (bog'lanmagan bo'lsa); bog'langan dars — topic_ref; boshqalari — yo'q
    link = {}
    for r in db.rows(_con, "SELECT course_id, lkey, topic_ref, deleted FROM pk_lessons"):
        if r["deleted"]: continue
        if r["topic_ref"]: link[(r["course_id"], r["lkey"])] = (r["course_id"], int(r["topic_ref"]))
        elif r["lkey"] >= 1000: link[(r["course_id"], r["lkey"])] = None
    src = lambda k: link[k] if k in link else (k if k[1] < 1000 else None)
    keys = tb_text | set(mon) | tb_quiz | set(link)
    vids = {}
    for k in keys:
        t_ = src(k)
        if t_ is None: continue
        if t_ in tb_text: mark("text", *k)
        if t_ in tb_quiz: mark("quiz", *k)
        if t_ in mon: vids[k] = mon[t_]
    for r in db.rows(_con, "SELECT DISTINCT course_id, topic_no, purpose FROM pk_assets WHERE deleted=0 AND purpose IN ('matn','taqdimot','slayd')"):
        mark("text" if r["purpose"] == "matn" else "slides", r["course_id"], r["topic_no"])
    for r in db.rows(_con, "SELECT course_id, topic_no, video_url, deck_id FROM pk_topics"):
        if r["video_url"]: vids[(r["course_id"], r["topic_no"])] = r["video_url"]
        if r["deck_id"]: mark("slides", r["course_id"], r["topic_no"])
    for k, u in vids.items():
        if parse_video(u)["ok"]: mark("video", *k)
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
    rd, pk, lk = readiness_map(), _pkg_map(), lesson_keys_all()
    out = []
    for co in courses:
        keys = lk.get(co["id"]) or list(range(1, int(co["topics"] or 15) + 1))
        row = {**co, "teacher": _short(co["teacher"]), "built": 0, "approved": 0, "waiting": 0, "text": 0, "slides": 0, "video": 0, "quiz": 0, "full": 0,
               "lessons": len(keys), "by_kind": {}}
        for no in keys:
            kind = split_key(no)[0]
            row["by_kind"][kind] = row["by_kind"].get(kind, 0) + 1
            r = rd.get((co["id"], no)) or {}
            for k in ("text", "slides", "video", "quiz"): row[k] += bool(r.get(k))
            row["full"] += all(r.get(k) for k in ("text", "slides", "video", "quiz"))
            p_ = pk.get((co["id"], no))
            if p_:
                row["built"] += 1; row["approved"] += p_["approved"]
                row["waiting"] += p_["last"]["status"] == "tayyor"
        n = len(keys)
        row["pct"] = _pct(row["approved"], n); row["built_pct"] = _pct(row["built"], n)
        row["started"] = bool(row["built"] or row["text"] or row["slides"] or row["quiz"])
        out.append(row)
    return out

def coverage(c: Ctx) -> dict:
    """Qamrov — darslar bo'yicha (L + A/S/Lab/MT). «topics» — darslar soni (eski nom saqlangan), «by_kind» — tur bo'yicha."""
    rows = course_rows(c)
    F = ("built", "approved", "waiting", "text", "slides", "video", "quiz", "full")
    def agg(key, label):
        out = {}
        for r in rows:
            a = out.setdefault(key(r), {**label(r), "courses": 0, "started": 0, "topics": 0, **{f: 0 for f in F}})
            a["courses"] += 1; a["started"] += r["started"]; a["topics"] += r["lessons"]
            for f in F: a[f] += r[f]
        for a in out.values(): a["pct"] = _pct(a["approved"], a["topics"]); a["built_pct"] = _pct(a["built"], a["topics"])
        return sorted(out.values(), key=lambda a: (a["built_pct"] or 0, -a["topics"]))
    tot = {"courses": len(rows), "started": sum(r["started"] for r in rows), "topics": sum(r["lessons"] for r in rows), "by_kind": {}}
    for r in rows:
        for k, v in r["by_kind"].items(): tot["by_kind"][k] = tot["by_kind"].get(k, 0) + v
    for f in F: tot[f] = sum(r[f] for r in rows)
    tot["pct"] = _pct(tot["approved"], tot["topics"]); tot["built_pct"] = _pct(tot["built"], tot["topics"])
    return {"total": tot,
            "departments": agg(lambda r: r["department_id"], lambda r: {"department_id": r["department_id"], "name": r["dept"] or "—"}),
            "teachers": agg(lambda r: r["teacher_id"], lambda r: {"teacher_id": r["teacher_id"], "name": r["teacher"] or "—", "dept": r["dept"]}) if c.role.key != TEACH else []}

def course_view(c: Ctx, cid: int) -> dict:
    co = _course(c, cid)
    rd, pk = readiness_map(), _pkg_map()
    topics = []
    for l in lessons(cid, co):
        no = l["key"]
        r = rd.get((cid, no)) or {}
        p_ = pk.get((cid, no))
        topics.append({**l, "no": no, "lesson_no": l["no"], **{k: bool(r.get(k)) for k in ("text", "slides", "video", "quiz")},
                       "last": {"id": p_["last"]["id"], "version": p_["last"]["version"], "status": p_["last"]["status"], "mode": p_["last"]["mode"],
                                "built_at": p_["last"]["built_at"]} if p_ else None, "approved": bool(p_ and p_["approved"])})
    k = c.role.key
    own = k in DEPT or (k == TEACH and co.get("teacher_id") == _teacher_id(c))
    cp = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=0 ORDER BY version DESC", (cid,))
    return {"course": {"id": co["id"], "subject": co["subject"], "direction": co["direction"], "course": co["course"], "dept": co["dept"],
                       "teacher": _short(co["teacher"]), "topics": int(co["topics"] or 15), "lessons": len(topics)},
            "topics": topics, "kinds": {k_: {"prefix": v[0], "label": v[2], "plural": v[3]} for k_, v in KINDS.items()},
            "course_packages": [pack_row(r) for r in cp], "can": {"write": own, "approve": k in DEPT}}

def topic_view(c: Ctx, cid: int, no: int) -> dict:
    co = _course(c, cid); les = _check_topic(co, no)
    st, over = topic_settings(cid, no)
    g = gather(cid, no, co, st, les)
    ts = _text_source(cid, no, les)
    text_html = next((b["html"] for b in g["content"]["blocks"] if b["type"] == "text" and b["title"] == "Ma'ruza matni"), "")
    if not text_html and ts: text_html = structure_text(ts["text"], g["content"]["title"])["html"]
    text_html = text_html.replace('src="assets/img/', f'src="{P}/courses/{int(cid)}/topics/{int(no)}/img/')    # ilovada ko'rish uchun
    assets = db.rows(_con, "SELECT id, purpose, kind, name, size, ts, user_name, src, meta FROM pk_assets WHERE course_id=? AND topic_no=? AND deleted=0 ORDER BY id DESC", (cid, no))
    pk = db.rows(_con, "SELECT * FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC", (cid, no))
    slides_b = next((b for b in g["content"]["blocks"] if b["type"] == "slides"), None)
    quiz_b = next((b for b in g["content"]["blocks"] if b["type"] == "quiz"), None)
    k = c.role.key
    own = k in DEPT or (k == TEACH and co.get("teacher_id") == _teacher_id(c))
    kp = keypoints_state(cid, no)
    alist = []
    for a in assets:
        m = json.loads(a.pop("meta") or "{}")
        if a["purpose"] == "rasm" and m.get("src") == "docx": continue          # Word ichidagi rasmlar — «Rasmlar» bo'limida soni ko'rsatiladi
        a.update(user_name=_short(a["user_name"]), demo=a["src"] == "demo")
        if a["purpose"] == "rasm": a.update(caption=m.get("caption") or "", marker=f"[RASM:{a['name']}]")
        alist.append(a)
    return {"course": {"id": co["id"], "subject": co["subject"], "direction": co["direction"], "course": co["course"], "topics": int(co["topics"] or 15)},
            "topic": {"no": no, "title": g["content"]["title"]}, "lesson": les, "ready": g["ready"], "settings": st, "override": over,
            "text_html": text_html[:150_000], "plan": g["ready"]["plan"]["items"], "heading": g["ready"]["plan"]["heading"], "refs": g["ready"]["refs"]["items"],
            "slides": [{"title": s_["title"], "bullets": s_["bullets"][:6], "notes": bool(s_["notes"]), "image": bool(s_["image"])} for s_ in (slides_b or {}).get("slides", [])[:60]],
            "quiz_preview": [{"type": q_["type"], "stem": q_["stem"]} for q_ in (quiz_b or {}).get("questions", [])[:50]],
            "assets": alist, "keypoints": {"draft": kp.get("draft") or None, "approved": kp.get("approved") or None, "ai": CC_has_key()},
            "packages": [pack_row(r) for r in pk], "decks": decks_for(c, co) if own else [],
            "blocks": [{"type": b["type"], "title": b["title"]} for b in g["content"]["blocks"]], "layout": g["content"]["layout"],
            "file_name": download_name(co, no, st["mode"]),
            "can": {"write": own, "approve": k in DEPT}}

def lesson_image(c: Ctx, cid: int, no: int, fn: str) -> Response:
    """Ilovada ma'ruza matnini ko'rish uchun dars rasmi (ko'lam tekshiriladi)."""
    co = _course(c, cid); _check_topic(co, no)
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}\.(png|jpg)", fn or ""): raise HTTPException(400, "Fayl nomi noto'g'ri")
    a = db.one(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='rasm' AND name=? AND deleted=0 ORDER BY id DESC LIMIT 1", (cid, no, fn))
    if not a or not _apath(a).is_file(): raise HTTPException(404, "Rasm topilmadi")
    return FileResponse(_apath(a), media_type=_CT[fn.rsplit(".", 1)[-1]], headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"})


# =============================================================================================
# Darslar ro'yxati (NEXTID nomlari) — bo'lim / o'qituvchi
# =============================================================================================
def save_lessons(c: Ctx, cid: int, text: str, apply: bool) -> dict:
    """Ommaviy joylashtirilgan dars nomlari → tekshirish (apply=False) yoki saqlash. L — nomini almashtiradi (n dan katta L — yangi dars),
    A/S/Lab/MT — yangi dars yoki nomi/bog'lanishi yangilanadi. Mavzu bog'lanishi 1..n oralig'ida bo'lishi kerak."""
    co = _course(c, cid, write=True)
    n = int(co["topics"] or 15)
    rows = parse_lessons(text)
    for r in rows:
        if r["ok"] and r.get("topic") and not 1 <= r["topic"] <= n: r.update(ok=False, error=f"Mavzu bog'lanishi 1–{n} oralig'ida bo'lishi kerak")
    good = [r for r in rows if r["ok"]]
    if len(good) > 400: raise HTTPException(400, "Bir martada ko'pi bilan 400 ta dars")
    existing = {l["key"] for l in lessons(cid, co)}
    for r in rows: r["new"] = bool(r["ok"] and r["key"] not in existing)
    if apply and good:
        with _lock:
            for r in good:
                _con.execute("""INSERT INTO pk_lessons(course_id,lkey,kind,no,title,topic_ref,ts,user_name,deleted) VALUES(?,?,?,?,?,?,?,?,0)
                                ON CONFLICT(course_id,lkey) DO UPDATE SET title=excluded.title, topic_ref=excluded.topic_ref, ts=excluded.ts,
                                user_name=excluded.user_name, deleted=0""",
                             (cid, r["key"], r["kind"], r["no"], r["title"], r.get("topic"), _now(), c.user["full_name"]))
            _log(c, cid, None, "darslar ro'yxati", f"{len(good)} ta"); _con.commit()
        rbac.audit(_con, c, "paket: darslar ro'yxati saqlandi", RES, True, f"kurs #{cid} · {len(good)} ta")
    return {"ok": True, "applied": bool(apply and good), "saved": len(good) if apply else 0, "errors": sum(1 for r in rows if not r["ok"]),
            "rows": [{k: r.get(k) for k in ("line", "raw", "ok", "error", "code", "kind", "no", "title", "topic", "new")} for r in rows],
            "lessons": lessons(cid, co)}

def delete_lesson(c: Ctx, cid: int, no: int) -> dict:
    """Qo'shilgan darsni o'chirish (standart L1..Ln o'chirilmaydi — faqat nomi standartga qaytadi). Manbalar va paketlar saqlanib qoladi."""
    co = _course(c, cid, write=True); les = _check_topic(co, no)
    with _lock:
        if les["default"]: _con.execute("DELETE FROM pk_lessons WHERE course_id=? AND lkey=?", (cid, no))
        else: _con.execute("UPDATE pk_lessons SET deleted=1, ts=?, user_name=? WHERE course_id=? AND lkey=?", (_now(), c.user["full_name"], cid, no))
        _log(c, cid, no, "dars o'chirildi" if not les["default"] else "dars nomi standartga qaytdi", les["code"]); _con.commit()
    rbac.audit(_con, c, "paket: dars o'chirildi", RES, True, f"kurs #{cid} · {les['code']}")
    return {"ok": True, "lessons": lessons(cid, co)}


# =============================================================================================
# AI: asosiy xulosalar (faqat dars matni yuboriladi — talaba ma'lumoti yo'q; o'qituvchi tahrirlab tasdiqlaydi)
# =============================================================================================
def CC_has_key() -> bool:
    from . import claude_client as CC
    return CC.has_key()

def pk_model() -> str: return os.getenv("ISFT_CORE_PK_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5"
def pk_daily() -> int:
    try: return max(1, int(os.getenv("ISFT_CORE_PK_DAILY", "30")))
    except ValueError: return 30

KP_MAX_CHARS = 60_000
KP_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["points"],
             "properties": {"points": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "quote"],
                                                                  "properties": {"text": {"type": "string"}, "quote": {"type": "string"}}}}}}
KP_SYSTEM = ("Siz oliy ta'lim muassasasi uchun ma'ruza matnidan asosiy xulosalar tayyorlaydigan metodistsiz. Faqat berilgan matnga tayaning — "
             "matnda yo'q fakt, raqam yoki ta'rif qo'shmang. Javob o'zbek tilida (lotin yozuvida).\n"
             "Qoidalar: 1) 4–7 ta asosiy xulosa, har biri 1–2 qisqa gap (≤ 220 belgi), talaba uchun tushunarli; 2) quote — xulosa asoslangan jumlani "
             "matndan AYNAN ko'chiring (o'zgartirmasdan, 1 jumla yoki uning bo'lagi, ≤ 300 belgi); 3) takrorlanmasin, mavzuning eng muhim g'oyalarini qamrasin.")

def ai_keypoints(c: Ctx, cid: int, no: int) -> dict:
    """«AI: asosiy xulosalar» — dars matni (faqat matn) → Claude (claude_client.call_json, qat'iy sxema) → 4–7 xulosa, har birida matndan iqtibos.
    Iqtibosi matnda topilmagan xulosa tashlanadi (testbank._quote_in). Natija — qoralama (pk_topics.keypoints.draft); paketga faqat tasdiqlangani kiradi."""
    from . import claude_client as CC, testbank as TB
    co = _course(c, cid, write=True); les = _check_topic(co, no)
    if not CC.has_key():
        rbac.audit(_con, c, "paket: AI xulosalar — AI ulanmagan", RES, True, f"kurs #{cid} · {les['code']}")
        raise HTTPException(503, "AI ulanmagan: asosiy xulosalar uchun ANTHROPIC_API_KEY sozlanmagan. Administratorga murojaat qiling. "
                                 "Xulosalarni hozircha qo'lda yozishingiz mumkin.")
    ts = _text_source(cid, no, les)
    if not ts or len(_plain(ts["text"]).strip()) < 200: raise HTTPException(400, "Avval ma'ruza matnini yuklang (kamida 200 belgi)")
    day = clock.today().isoformat()
    if db.one(_con, "SELECT COUNT(*) n FROM pk_ai WHERE user_id=? AND day=?", (c.user["id"], day))["n"] >= pk_daily():
        raise HTTPException(429, f"Kunlik cheklov: bir foydalanuvchi uchun kuniga {pk_daily()} ta AI so'rovi. Ertaga davom ettiring.")
    text = _plain(ts["text"])
    src_text = text[:KP_MAX_CHARS]
    prompt = (f"Dars: {les['code']} — {les['title']}\nFan: {co['subject']}\n"
              f"{'(Matn uzun — faqat boshlang`ich qismi berildi.)' if len(text) > KP_MAX_CHARS else ''}\n\nMA'RUZA MATNI:\n<<<\n{src_text}\n>>>\n\n"
              "Shu matn bo'yicha 4–7 ta asosiy xulosa va har biri uchun matndan aynan iqtibos qaytaring.")
    t0 = time.time(); err = None; info = {"in": 0, "out": 0, "model": pk_model()}; items, dropped = [], 0
    try:
        data, info = CC.call_json(model=pk_model(), system=KP_SYSTEM, content=[{"type": "text", "text": prompt}], schema=KP_SCHEMA,
                                  max_tokens=4000, effort="medium", timeout=180, what="asosiy xulosalar")
        for it in (data or {}).get("points") or []:
            t_ = re.sub(r"\s+", " ", str((it or {}).get("text") or "")).strip()[:300] if isinstance(it, dict) else ""
            q_ = re.sub(r"\s+", " ", str((it or {}).get("quote") or "")).strip()[:400] if isinstance(it, dict) else ""
            if t_ and q_ and TB._quote_in(q_, src_text) and t_.casefold() not in {x["text"].casefold() for x in items}: items.append({"text": t_, "quote": q_})
            else: dropped += 1
        items = items[:7]
        if not items: err = "AI matnga asoslangan xulosa qaytarmadi (iqtiboslar matnda topilmadi) — qayta urinib ko'ring yoki qo'lda yozing"
    except CC.AIError as e:
        err = str(e)
    except Exception as e:
        err = f"AI javobini qayta ishlab bo'lmadi: {type(e).__name__}"
    with _lock:
        _con.execute("INSERT INTO pk_ai(course_id,topic_no,user_id,day,ts,kind,model,ok,ms,err,in_tok,out_tok,n_got,n_dropped) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, no, c.user["id"], day, _now(), "keypoints", info.get("model"), 0 if err else 1, int((time.time() - t0) * 1000), err,
                      info.get("in", 0), info.get("out", 0), len(items), dropped))
        if not err:
            kp = keypoints_state(cid, no)
            kp["draft"] = {"items": items, "ts": _now(), "by": c.user["full_name"], "model": info.get("model"), "dropped": dropped, "src": "ai"}
            _con.execute("""INSERT INTO pk_topics(course_id,topic_no,keypoints,updated_at) VALUES(?,?,?,?)
                            ON CONFLICT(course_id,topic_no) DO UPDATE SET keypoints=excluded.keypoints, updated_at=excluded.updated_at""",
                         (cid, no, json.dumps(kp, ensure_ascii=False), _now()))
            _log(c, cid, no, "AI xulosalar (qoralama)", f"{len(items)} ta · tashlandi {dropped}")
        _con.commit()
    rbac.audit(_con, c, "paket: AI asosiy xulosalar", RES, True, f"kurs #{cid} · {les['code']} · {len(items)} ta · tashlandi {dropped}{' · xato' if err else ''}")
    if err: raise HTTPException(502, err)
    return {"ok": True, "draft": keypoints_state(cid, no).get("draft"), "dropped": dropped}

def save_keypoints(c: Ctx, cid: int, no: int, items: list, approve: bool, clear: bool = False) -> dict:
    """O'qituvchi xulosalarni tahrirlaydi: approve=True — paketga kiradi (tasdiqlangan), aks holda qoralama; clear — ikkalasi o'chiriladi."""
    co = _course(c, cid, write=True); les = _check_topic(co, no)
    clean = []
    for x in items or []:
        t_ = re.sub(r"\s+", " ", str(x.get("text") if isinstance(x, dict) else x or "")).strip()[:300]
        if t_ and t_ not in clean: clean.append(t_)
    if len(clean) > 12: raise HTTPException(400, "Ko'pi bilan 12 ta xulosa")
    kp = {} if clear else keypoints_state(cid, no)
    if not clear:
        if approve:
            if not clean: raise HTTPException(400, "Tasdiqlash uchun kamida bitta xulosa yozing")
            kp["approved"] = {"items": clean, "ts": _now(), "by": c.user["full_name"]}; kp.pop("draft", None)
        else:
            old = {i["text"]: i.get("quote", "") for i in ((kp.get("draft") or {}).get("items") or [])}
            kp["draft"] = {**(kp.get("draft") or {}), "items": [{"text": t_, "quote": old.get(t_, "")} for t_ in clean], "ts": _now(), "by": c.user["full_name"]}
    with _lock:
        _con.execute("""INSERT INTO pk_topics(course_id,topic_no,keypoints,updated_at) VALUES(?,?,?,?)
                        ON CONFLICT(course_id,topic_no) DO UPDATE SET keypoints=excluded.keypoints, updated_at=excluded.updated_at""",
                     (cid, no, json.dumps(kp, ensure_ascii=False), _now()))
        _log(c, cid, no, "xulosalar", "o'chirildi" if clear else ("tasdiqlandi" if approve else "qoralama") + f" · {len(clean)} ta"); _con.commit()
    return {"ok": True, "keypoints": kp, "code": les["code"]}


# =============================================================================================
# Avtomatik joylash: video havolalar va ommaviy yig'ish
# =============================================================================================
def bulk_videos(c: Ctx, cid: int, text: str, apply: bool) -> dict:
    co = _course(c, cid, write=True)
    ls = {l["key"]: l for l in lessons(cid, co)}
    rows = parse_bulk(text, int(co["topics"] or 15), ls.keys())
    good = [r for r in rows if r.get("ok")]
    if apply and good:
        with _lock:
            for r in good:
                _con.execute("""INSERT INTO pk_topics(course_id,topic_no,video_url,video_at,video_by,updated_at) VALUES(?,?,?,?,?,?)
                                ON CONFLICT(course_id,topic_no) DO UPDATE SET video_url=excluded.video_url, video_at=excluded.video_at,
                                video_by=excluded.video_by, updated_at=excluded.updated_at, src=''""",
                             (cid, r["topic_no"], r["video"]["url"], _now(), c.user["full_name"], _now()))
            _log(c, cid, None, "videolar (ommaviy)", f"{len(good)} ta dars"); _con.commit()
        rbac.audit(_con, c, "paket: videolar joylandi", RES, True, f"kurs #{cid} · {len(good)} ta")
    return {"ok": True, "applied": bool(apply and good), "assigned": len(good) if apply else 0, "errors": sum(1 for r in rows if not r.get("ok")),
            "rows": [{"line": r["line"], "topic_no": r["topic_no"], "code": r["code"], "title": ls[r["topic_no"]]["title"] if r["topic_no"] in ls else "",
                      "url": r["url"], "ok": bool(r.get("ok")), "error": r.get("error") or "", "video_id": (r.get("video") or {}).get("video_id"),
                      "provider": (r.get("video") or {}).get("provider")} for r in rows]}

def bulk_build(c: Ctx, cid: int, topics: list[int] | None, mode: str | None, only_complete: bool) -> dict:
    """Ommaviy yig'ish. topics None yoki [] — kursning barcha darslari (orqaga moslik). Darslar ro'yxati bir marta quriladi,
    har dars manbalari bir marta yig'iladi (gather → build_topic'ga beriladi)."""
    co = _course(c, cid, write=True)
    if mode and mode not in MODES: raise HTTPException(400, "Paket turi noma'lum")
    ls = {l["key"]: l for l in lessons(cid, co)}
    want = {int(t) for t in topics} if topics else None
    nos = [k for k in ls if want is None or k in want]
    res = []
    for no in nos:
        code = ls[no]["code"]
        try:
            st = _build_settings(cid, no, mode)
            g = gather(cid, no, co, st, ls[no])
            if not g["ready"]["buildable"]: res.append({"no": no, "code": code, "ok": False, "skipped": True, "error": "manba yo'q"}); continue
            if only_complete and not g["ready"]["complete"]:
                res.append({"no": no, "code": code, "ok": False, "skipped": True, "error": "to'liq emas: " + ", ".join(BLOCKS[k] for k in g["ready"]["missing"])}); continue
            r = build_topic(c, cid, no, mode, co=co, les=ls[no], pre=(st, g))
            res.append({"no": no, "code": code, "ok": True, "unchanged": r["unchanged"], "version": r["package"]["version"], "status": r["package"]["status"]})
        except HTTPException as e:
            res.append({"no": no, "code": code, "ok": False, "error": str(e.detail)})
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
            "layouts": LAYOUTS, "sections": SECTIONS, "reflect_default": REFLECT,
            "kinds": {k: {"prefix": v[0], "label": v[2], "plural": v[3]} for k, v in KINDS.items()}, "ai": CC_has_key() and k in AUTHORS,
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
    c = C(request); guard(c, "mavzu", WORK, f"kurs #{cid} · {lesson_code(no)}")
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
    c = C(request); guard(c, "ma'ruza matni yuklash", AUTHORS, f"kurs #{cid} · {lesson_code(no)} · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_text, c, cid, no, raw, None, name[:160])

class TextIn(BaseModel):
    text: str = Field(..., max_length=MAX_TEXT_CHARS * 2)
    name: str = Field("", max_length=160)

@router.post(P + "/courses/{cid}/topics/{no}/text/paste")
def api_text_paste(cid: int, no: int, body: TextIn, request: Request):
    c = C(request); guard(c, "ma'ruza matni (matn)", AUTHORS, f"kurs #{cid} · {lesson_code(no)}")
    return upload_text(c, cid, no, None, body.text, body.name or f"{lesson_code(no)} matni.txt")

@router.post(P + "/courses/{cid}/topics/{no}/slides")
async def api_slides_upload(cid: int, no: int, request: Request, name: str = "taqdimot"):
    c = C(request); guard(c, "taqdimot yuklash", AUTHORS, f"kurs #{cid} · {lesson_code(no)} · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_slides, c, cid, no, raw, name[:160])

@router.post(P + "/courses/{cid}/topics/{no}/files")
async def api_file_upload(cid: int, no: int, request: Request, name: str = "fayl"):
    c = C(request); guard(c, "qo'shimcha fayl yuklash", AUTHORS, f"kurs #{cid} · {lesson_code(no)} · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_file, c, cid, no, raw, name[:160])

@router.post(P + "/courses/{cid}/topics/{no}/images")
async def api_image_upload(cid: int, no: int, request: Request, name: str = "rasm", caption: str = ""):
    c = C(request); guard(c, "rasm yuklash", AUTHORS, f"kurs #{cid} · {lesson_code(no)} · {name[:60]}")
    raw = await _read_body(request)
    return await run_in_threadpool(upload_image, c, cid, no, raw, name[:160], caption[:300])

@router.get(P + "/courses/{cid}/topics/{no}/img/{fn}")
def api_lesson_image(cid: int, no: int, fn: str, request: Request):
    c = C(request); guard(c, "dars rasmi", WORK, f"kurs #{cid} · {lesson_code(no)} · {fn[:40]}")
    return lesson_image(c, cid, no, fn)

class LessonsIn(BaseModel):
    text: str = Field(..., max_length=100_000)
    apply: bool = False

@router.get(P + "/courses/{cid}/lessons")
def api_lessons(cid: int, request: Request):
    c = C(request); guard(c, "darslar", WORK, f"kurs #{cid}")
    co = _course(c, cid)
    return {"lessons": lessons(cid, co)}

@router.post(P + "/courses/{cid}/lessons")
def api_lessons_save(cid: int, body: LessonsIn, request: Request):
    c = C(request); guard(c, "darslar ro'yxati", AUTHORS, f"kurs #{cid} · {'saqlash' if body.apply else 'tekshirish'}")
    return save_lessons(c, cid, body.text, body.apply)

@router.post(P + "/courses/{cid}/lessons/{no}/delete")
def api_lesson_delete(cid: int, no: int, request: Request):
    c = C(request); guard(c, "darsni o'chirish", AUTHORS, f"kurs #{cid} · {lesson_code(no)}")
    return delete_lesson(c, cid, no)

class KeypointsIn(BaseModel):
    items: list = Field(default_factory=list, max_length=40)
    approve: bool = False
    clear: bool = False

@router.post(P + "/courses/{cid}/topics/{no}/keypoints/ai")
async def api_keypoints_ai(cid: int, no: int, request: Request):
    c = C(request); guard(c, "AI: asosiy xulosalar", AUTHORS, f"kurs #{cid} · {lesson_code(no)}")
    return await run_in_threadpool(ai_keypoints, c, cid, no)

@router.post(P + "/courses/{cid}/topics/{no}/keypoints")
def api_keypoints(cid: int, no: int, body: KeypointsIn, request: Request):
    c = C(request); guard(c, "asosiy xulosalar", AUTHORS, f"kurs #{cid} · {lesson_code(no)}")
    return save_keypoints(c, cid, no, body.items, body.approve, body.clear)

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
    c = C(request); guard(c, "video havola", AUTHORS, f"kurs #{cid} · {lesson_code(no)}")
    return set_video(c, cid, no, body.url)

class DeckIn(BaseModel):
    deck_id: int = 0

@router.post(P + "/courses/{cid}/topics/{no}/deck")
def api_deck(cid: int, no: int, body: DeckIn, request: Request):
    c = C(request); guard(c, "taqdimot (modul) biriktirish", AUTHORS, f"kurs #{cid} · {lesson_code(no)} · deck #{body.deck_id}")
    return set_deck(c, cid, no, body.deck_id)

class SettingsIn(BaseModel):
    layout: str | None = None
    sections: dict | None = None
    reflect: dict | None = None
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
    c = C(request); guard(c, "mavzu sozlamasi", AUTHORS, f"kurs #{cid} · {lesson_code(no)}")
    s = {k: v for k, v in body.model_dump().items() if v is not None and k != "reset"}
    return set_topic_settings(c, cid, no, s, body.reset)

class BuildIn(BaseModel):
    mode: str | None = None
    force: bool = False

@router.post(P + "/courses/{cid}/topics/{no}/build")
async def api_build(cid: int, no: int, body: BuildIn, request: Request):
    c = C(request); guard(c, "paket yig'ish", AUTHORS, f"kurs #{cid} · {lesson_code(no)} · {body.mode or ''}")
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
    return preview_redirect(c, pid, path, request.url.query)

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
    layout: str = "steps"
    sections: dict = {}
    reflect: dict = {}
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
    if body.mode not in MODES or body.completion not in COMPLETION or body.layout not in LAYOUTS: raise HTTPException(400, "Sozlama qiymati noto'g'ri")
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
        # namuna darslar ro'yxati (NEXTID uslubi): 2 ta amaliy mashg'ulot — bir marta
        if not db.one(con, "SELECT 1 x FROM pk_meta WHERE k='seed_lessons_v1'"):
            now = _now()
            for no, t, ref in ((1, "Talab va taklif grafiklarini chizish", 1), (2, "Muqobil xarajatni hisoblash", 2)):
                con.execute("""INSERT INTO pk_lessons(course_id,lkey,kind,no,title,topic_ref,ts,user_name,src) VALUES(?,?,?,?,?,?,?,?,'demo')
                               ON CONFLICT(course_id,lkey) DO NOTHING""", (co["id"], lesson_key("amaliy", no), "amaliy", no, t, ref, now, "Namuna (demo)"))
            con.execute("INSERT OR REPLACE INTO pk_meta(k,v) VALUES('seed_lessons_v1', ?)", (now,)); con.commit()
        # namuna paket — pleyer paydo bo'lganda bir marta (idempotent)
        if player_ok() and not db.one(con, "SELECT 1 x FROM pk_packages WHERE src='demo' LIMIT 1") and not db.one(con, "SELECT 1 x FROM pk_meta WHERE k='demo_pkg'"):
            try:
                build_topic(None, co["id"], 1, "scorm12", src="demo")
                con.execute("INSERT OR REPLACE INTO pk_meta(k,v) VALUES('demo_pkg', ?)", (_now(),)); con.commit()
            except HTTPException as e:
                print("paket demo build:", e.detail)
    finally:
        _con = saved
