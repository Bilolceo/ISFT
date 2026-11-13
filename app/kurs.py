"""«Kurs muharriri» — Masofaviy ta'lim bo'limi uchun bloklardan kurs yig'ish (Articulate Rise 360 o'rniga, docs/kurs.md).

Nima uchun: bo'lim darslarni Rise 360'da (yiliga ≈ $2000) bloklardan yig'adi — sarlavha, matn, rasm, akkordeon, kartochkalar, «Davom etish»
tugmasi, bilimni tekshirish savollari, yakuniy test. Bu modul o'sha ishni ISFT Core ichida, o'z uslubimizda bajaradi:

  1. Ma'lumot modeli (ku_*): kurs (nomi, tavsif, muqova, urg'u rangi — xavfsiz palitradan, muallif, ixtiyoriy masofaviy kurs bog'lanishi,
     holat qoralama → ko'rib chiqishda → tasdiqlangan, versiyalar), darslar (tartibli; turi blocks | quiz; test sozlamalari), bloklar
     (tartibli; tur + JSON — har tur serverda tozalanadi, HTML maydonlari paket.sanitize orqali), fayllar (rasm / video / audio / subtitr /
     ilova — DATA_DIR/kurs ostida, hajm chegarasi, turi birinchi baytlardan). Versiyalar: oxirgi KEEP_VERSIONS ta surat + tasdiqlanganlar, tiklash.
  2. Avtosaqlash: har dars o'z «rev» raqamiga ega (kurs sozlamalari va tartibi — kursniki); eski rev bilan kelgan saqlash — 409 (ziddiyat).
  3. Pleyer (app/kurs_player/ + paket_player/lms.js — LMS adapterlari umumiy): muqova, yon menyu, darslar, «Davom etish» bilan bosqichlash,
     bilimni tekshirish, test (savollar banki, o'tish foizi, urinishlar, aralashtirish), qidiruv. Ko'rish (preview) va eksport — bitta pleyer.
  4. Eksport: SCORM 1.2, SCORM 2004 4-nashr, xAPI (tincan.xml — kurs, darslar va test savollari faoliyatlari), oddiy HTML — paket.py
     manifestlari, deterministik zip va validate_zip (window.KURS tekshiruvchisi shu yerda ro'yxatga olinadi).
  5. Rise importi: Rise eksporti (.zip: xAPI / SCORM / web) → runtime-data.js → qoralama kurs (darslar, bloklar, test, rasmlar). Noma'lum
     bloklar — «import qilinmadi: <tur>» izohli matn bloki. Zip bombasi / yo'l hujumi himoyasi, hajm chegaralari, oqim bilan yuklash.
     Sifat hisoboti (har qanday kurs uchun): to'g'ri javob doim bir o'rinda / eng uzun variant, alt matnsiz rasmlar, inglizcha yorliqlar,
     test qamrovi darslar bo'yicha, bitta to'g'ri javobli «bir nechta javob» savollari; bir bosishli tuzatishlar (aralashtirish, yorliqlar).

Ruxsat (rbac.KURS, har yozish audit jurnalida):
  masofaviy, masofaviy_xodim — barcha kurslar: tahrirlash, eksport, tasdiqlash / qaytarish, import;
  oqituvchi — o'z kurslari (muallif yoki bog'langan masofaviy kurs o'qituvchisi): tahrirlash, eksport, ko'rib chiqishga yuborish, import;
  rektor, prorektor_oquv — faqat jamlangan sonlar (tahrirlash va kurs tarkibi yo'q).
"""
from __future__ import annotations
import base64, hashlib, hmac, html, io, json, math, os, re, secrets, threading, time, zipfile
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from . import clock, db, rbac
from . import paket as PK
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/kurs"
RES = rbac.KURS

HEAD, STAFF, TEACH = "masofaviy", "masofaviy_xodim", "oqituvchi"
DEPT = (HEAD, STAFF)
LEAD = ("rektor", "prorektor_oquv")
AUTHORS = DEPT + (TEACH,)
ALL = AUTHORS + LEAD

PLAYER_DIR = Path(__file__).resolve().parent / "kurs_player"     # testlarda almashtiriladi
STORE: Path | None = None                                         # None → <DATA_DIR>/kurs

STATUS = {"qoralama": "Qoralama", "korib_chiqishda": "Ko'rib chiqishda", "tasdiqlangan": "Tasdiqlangan"}
MODES = {"xapi": "xAPI (Tin Can) — NEXTID", "scorm12": "SCORM 1.2", "scorm2004": "SCORM 2004 (4-nashr)", "none": "Oddiy HTML (LMS'siz)"}
COMPLETION = {"view": "Darslar ko'rilganda", "quiz": "Test topshirilganda", "view_and_quiz": "Darslar ko'rilganda va test topshirilganda",
              "view_or_quiz": "Darslar ko'rilganda yoki test topshirilganda"}
REVEAL = {"always": "Har doim (javobdan keyin)", "pass": "Faqat test topshirilganda", "never": "Ko'rsatilmaydi"}
# Urg'u ranglari — oq matn bilan kontrast ≥ 4.5:1 (WCAG AA), ISFT qirmizisi birinchi
PALETTE = {"#870037": "ISFT qirmizi", "#00575B": "Moviy-yashil", "#1D4ED8": "Ko'k", "#4338CA": "Indigo", "#15803D": "Yashil",
           "#C2410C": "To'q sariq", "#7E22CE": "Binafsha", "#334155": "Grafit"}
DEFAULT_ACCENT = "#870037"
LABELS = {"start": "Kursni boshlash", "resume": "Davom ettirish", "continue": "Davom etish", "next_lesson": "Keyingi dars",
          "prev_lesson": "Oldingi dars", "lesson": "Dars", "lessons": "Darslar", "quiz": "Test", "quiz_start": "Testni boshlash",
          "submit": "Javobni tekshirish", "next_question": "Keyingi savol", "retry": "Qayta urinish", "result": "Natija", "search": "Qidirish",
          "complete_hint": "Davom etish uchun yuqoridagi topshiriqlarni bajaring", "menu": "Mundarija", "progress": "bajarildi",
          "passed": "Test topshirildi", "failed": "Test topshirilmadi", "correct": "To'g'ri", "incorrect": "Noto'g'ri", "finish": "Kurs yakunlandi"}
SETTINGS = {"sidebar": True, "lesson_count": True, "sequential": False, "search": True, "completion": "view", "view_pct": 100, "mode": "xapi"}
QUIZ = {"pass_pct": 80, "attempts": 0, "shuffle": True, "randomize": False, "draw": 0, "reveal": "always", "intro": ""}

MAX_LESSONS = 60
MAX_BLOCKS = 250                       # bitta darsda
MAX_HTML = 20_000                      # bitta HTML maydon (belgi)
MAX_IMAGE = 15 * 1024 * 1024
MAX_AUDIO = 50 * 1024 * 1024
MAX_FILE = 50 * 1024 * 1024
MAX_VTT = 2 * 1024 * 1024
KEEP_VERSIONS = 30
KEEP_EXPORTS = 3
AUTO_SNAPSHOT_SEC = 10 * 60            # avtosaqlashda avtomatik versiya — eng ko'pi bilan shuncha vaqtda bir marta
ACTIVITY_BASE = "https://isft.uz/xapi/kurs"
IMPORT_MAX = 400 * 1024 * 1024         # Rise eksporti (.zip) — ISFT_CORE_KURS_IMPORT_MB bilan o'zgartiriladi
IMPORT_MAX_FILES = 5000
IMPORT_MAX_TOTAL = 1024 * 1024 * 1024  # ochilgan umumiy hajm
IMPORT_MAX_ENTRY = 400 * 1024 * 1024
IMPORT_MAX_DATA = 60 * 1024 * 1024     # runtime-data.js
IMPORT_RATIO = 100
IMPORT_RATIO_FROM = 2 * 1024 * 1024

def _env_mb(name: str, default: int) -> int:
    try: return max(1, int(os.getenv(name, str(default)))) * 1024 * 1024
    except ValueError: return default * 1024 * 1024
def import_max() -> int: return _env_mb("ISFT_CORE_KURS_IMPORT_MB", IMPORT_MAX // (1024 * 1024))

SCHEMA = """
CREATE TABLE IF NOT EXISTS ku_courses(id INTEGER PRIMARY KEY, title TEXT, description TEXT DEFAULT '', cover_asset INT, cover_alt TEXT DEFAULT '',
  accent TEXT, settings TEXT, labels TEXT, author_id INT, author_name TEXT, dl_course_id INT, status TEXT DEFAULT 'qoralama', status_note TEXT DEFAULT '',
  rev INT DEFAULT 1, created_at TEXT, updated_at TEXT, updated_by TEXT, submitted_at TEXT, approved_by INT, approved_name TEXT, approved_at TEXT,
  approved_version INT, src TEXT DEFAULT '', import_report TEXT, deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_ku_c ON ku_courses(deleted, status);
CREATE TABLE IF NOT EXISTS ku_lessons(id INTEGER PRIMARY KEY, course_id INT, uid TEXT, pos INT, type TEXT DEFAULT 'blocks', title TEXT, settings TEXT,
  rev INT DEFAULT 1, updated_at TEXT, updated_by TEXT, deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_ku_l ON ku_lessons(course_id, deleted, pos);
CREATE TABLE IF NOT EXISTS ku_blocks(id INTEGER PRIMARY KEY, lesson_id INT, uid TEXT, pos INT, type TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS ix_ku_b ON ku_blocks(lesson_id, pos);
CREATE TABLE IF NOT EXISTS ku_assets(id INTEGER PRIMARY KEY, course_id INT, kind TEXT, ext TEXT, name TEXT, path TEXT, size INT, sha256 TEXT, meta TEXT,
  user_id INT, user_name TEXT, ts TEXT, deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_ku_a ON ku_assets(course_id, deleted);
CREATE TABLE IF NOT EXISTS ku_versions(id INTEGER PRIMARY KEY, course_id INT, no INT, ts TEXT, user_id INT, user_name TEXT, kind TEXT, note TEXT,
  data TEXT, size INT);
CREATE INDEX IF NOT EXISTS ix_ku_v ON ku_versions(course_id, no);
CREATE TABLE IF NOT EXISTS ku_exports(id INTEGER PRIMARY KEY, course_id INT, mode TEXT, rev TEXT, file TEXT, size INT, sha256 TEXT, validation TEXT,
  ts TEXT, user_id INT, user_name TEXT);
CREATE INDEX IF NOT EXISTS ix_ku_e ON ku_exports(course_id, mode);
CREATE TABLE IF NOT EXISTS ku_log(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, user_name TEXT, course_id INT, action TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_ku_log ON ku_log(course_id);
CREATE TABLE IF NOT EXISTS ku_meta(k TEXT PRIMARY KEY, v TEXT);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def store() -> Path: return STORE or (Path(db.DATA_DIR) / "kurs")
def player_ok() -> bool: return (PLAYER_DIR / "index.html").is_file() and (PK.PLAYER_DIR / "lms.js").is_file()
def _uid(prefix="b") -> str: return prefix + secrets.token_hex(5)
_UID_RX = re.compile(r"^[a-z][a-z0-9]{5,23}$")


# =============================================================================================
# Sxema, bog'lash
# =============================================================================================
def _cols(con, table: str) -> set:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def migrate(con) -> dict:
    """Idempotent: jadvallar (SCHEMA) va keyin qo'shilgan ustunlar."""
    con.executescript(SCHEMA)
    out = {"columns": []}
    for t, col, ddl in (("ku_courses", "cover_alt", "TEXT DEFAULT ''"), ("ku_assets", "ext", "TEXT")):
        if col not in _cols(con, t):
            con.execute(f"ALTER TABLE {t} ADD COLUMN {col} {ddl}"); out["columns"].append(f"{t}.{col}")
    con.commit()
    return out

def init(con):
    try:
        migrate(con)
    except Exception as e:
        print("kurs.init:", e); return
    try:
        if db.one(con, "SELECT 1 x FROM users WHERE role='masofaviy'"): seed(con)
    except Exception as e:      # namuna ma'lumot ilovani to'xtatmasin
        print("kurs seed:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


# =============================================================================================
# Bloklar: turlar ro'yxati va server tomonda tozalash
# =============================================================================================
CATEGORIES = {"matn": "Matn", "media": "Media", "interaktiv": "Interaktiv", "bilim": "Bilimni tekshirish", "tuzilma": "Tuzilma"}
BLOCKS = {   # tur: (nomi, toifa, qisqa tavsif)
    "heading": ("Sarlavha", "matn", "Bo'lim sarlavhasi"),
    "paragraph": ("Matn", "matn", "Oddiy paragraf"),
    "heading_paragraph": ("Sarlavha va matn", "matn", "Sarlavha ostida paragraf"),
    "quote": ("Iqtibos / urg'u", "matn", "Iqtibos yoki ajratilgan fikr"),
    "list": ("Ro'yxat", "matn", "Raqamli, belgili yoki belgilash ro'yxati"),
    "table": ("Jadval", "matn", "Qator va ustunlar"),
    "image": ("Rasm", "media", "Markazda, to'liq kenglik, katta yoki tasma"),
    "image_text": ("Rasm va matn", "media", "Rasm yonida matn"),
    "gallery": ("Galereya", "media", "Rasmlar to'ri yoki karusel"),
    "video": ("Video", "media", "Video fayl (subtitr bilan) yoki YouTube"),
    "audio": ("Audio", "media", "Audio fayl va matni"),
    "attachment": ("Fayl", "media", "Yuklab olinadigan fayl"),
    "labeled_graphic": ("Belgili rasm", "media", "Rasm ustida bosiladigan nuqtalar"),
    "accordion": ("Akkordeon", "interaktiv", "Ochiladigan bo'limlar"),
    "tabs": ("Yorliqlar", "interaktiv", "Yorliqlarga bo'lingan matn"),
    "flashcards": ("Kartochkalar", "interaktiv", "Aylanadigan kartochkalar"),
    "process": ("Jarayon", "interaktiv", "Qadam-baqadam jarayon"),
    "timeline": ("Vaqt chizig'i", "interaktiv", "Sanalar bo'yicha voqealar"),
    "sorting": ("Saralash", "interaktiv", "Elementlarni toifalarga ajratish"),
    "matching": ("Moslashtirish", "interaktiv", "Juftlarni topish"),
    "knowledge": ("Bilimni tekshirish", "bilim", "Bitta / bir nechta javob, to'g'ri-noto'g'ri, bo'sh joy"),
    "divider": ("Ajratgich", "tuzilma", "Chiziq yoki bo'sh joy"),
    "continue": ("«Davom etish» tugmasi", "tuzilma", "Qolgan qismni yashiradi"),
    "button": ("Tugma / havola", "tuzilma", "Tashqi havolaga tugma"),
    "question": ("Test savoli", "bilim", "Yakuniy test savoli"),
}
LESSON_BLOCKS = [k for k in BLOCKS if k != "question"]
INTERACTIVE = ("accordion", "tabs", "flashcards", "process", "sorting", "matching", "knowledge", "labeled_graphic")   # «Davom etish» talabi
Q_KINDS = {"single": "Bitta javob", "multiple": "Bir nechta javob", "truefalse": "To'g'ri / noto'g'ri", "fill": "Bo'sh joyni to'ldirish"}
TF = ["To'g'ri", "Noto'g'ri"]
ASSET_KINDS = {"image": "Rasm", "video": "Video", "audio": "Audio", "vtt": "Subtitr", "file": "Fayl"}
FILE_EXTS = ("pdf", "docx", "pptx", "xlsx")

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
def _line(v, n: int = 300) -> str:
    """Bir qatorli oddiy matn: boshqaruv belgilari va ortiqcha bo'shliqlar olib tashlanadi."""
    return re.sub(r"\s+", " ", _CTRL.sub("", str(v if v is not None else ""))).strip()[:n]
def _text(v, n: int = 2000) -> str:
    """Ko'p qatorli oddiy matn (qator ko'chishlari saqlanadi)."""
    s = _CTRL.sub("", str(v if v is not None else "")).replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(re.sub(r"[ \t]+", " ", x).strip() for x in s.split("\n"))).strip()[:n]
_IMG_TAG = re.compile(r"</?(?:img|figure|figcaption)\b[^>]*>", re.I)
def _html(v, n: int = MAX_HTML) -> str:
    """HTML maydon: paket.sanitize (oq ro'yxat) + rasm teglari olib tashlanadi (rasmlar — alohida blok); bo'sh <p></p> — bo'sh satr."""
    s = PK.sanitize(str(v if v is not None else "")[:n])
    s = _IMG_TAG.sub("", s).strip()
    return "" if re.fullmatch(r"(?:<p>\s*(?:<br>)?\s*</p>|<br>|\s)*", s) else s
def _plain(h: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h or ""))).strip()
def _b(v, d=False) -> bool: return d if v is None else bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "ha", "yes", "on")
def _i(v, lo: int, hi: int, d: int) -> int:
    try: return max(lo, min(hi, int(v)))
    except (TypeError, ValueError): return d
def _f(v, lo: float, hi: float, d: float) -> float:
    try:
        x = float(v)
        return d if math.isnan(x) else round(max(lo, min(hi, x)), 2)
    except (TypeError, ValueError): return d
def _pick(v, allowed, d):
    return v if v in allowed else d
def _lst(v, n: int) -> list:
    return [x for x in v if isinstance(x, dict)][:n] if isinstance(v, list) else []

class _Assets:
    """Kursning fayllari {id: qator} — blok tozalashda asset havolasini tekshirish uchun (begona kurs fayli yoki noto'g'ri tur — None)."""
    def __init__(self, cid: int | None):
        self.rows = {r["id"]: r for r in db.rows(_con, "SELECT * FROM ku_assets WHERE course_id=? AND deleted=0", (cid,))} if cid else {}
    def ok(self, aid, *kinds) -> int | None:
        try: aid = int(aid)
        except (TypeError, ValueError): return None
        r = self.rows.get(aid)
        return aid if r and (not kinds or r["kind"] in kinds) else None

def _qclean(d: dict) -> dict:
    """Savol (bilimni tekshirish bloki va test savoli): kind, question, answers[{text, correct, feedback}], accept[], feedback_correct/_wrong."""
    kind = _pick(d.get("kind"), Q_KINDS, "single")
    out = {"kind": kind, "question": _text(d.get("question"), 1000), "answers": [], "accept": [],
           "feedback_correct": _text(d.get("feedback_correct"), 1000), "feedback_wrong": _text(d.get("feedback_wrong"), 1000)}
    if kind == "fill":
        out["accept"] = [a for a in (_line(x, 200) for x in (d.get("accept") if isinstance(d.get("accept"), list) else [])[:50]) if a][:10]
        return out
    ans = [{"text": _line(a.get("text"), 500), "correct": _b(a.get("correct")), "feedback": _text(a.get("feedback"), 1000)} for a in _lst(d.get("answers"), 10)]
    if kind == "truefalse":
        c0 = ans[0]["correct"] if ans else True
        fb = [a["feedback"] for a in ans[:2]] + ["", ""]
        ans = [{"text": TF[0], "correct": bool(c0), "feedback": fb[0]}, {"text": TF[1], "correct": not c0, "feedback": fb[1]}]
    elif kind == "single":
        first = next((i for i, a in enumerate(ans) if a["correct"]), None)
        for i, a in enumerate(ans): a["correct"] = i == first
    out["answers"] = ans
    return out

def clean_block(btype: str, d, A: _Assets) -> dict:
    """Blok ma'lumoti → xavfsiz, me'yorlangan shakl. Noto'g'ri qiymatlar standartga keltiriladi (avtosaqlash yarim tayyor blokni ham saqlaydi);
    tekshiruv natijasi — block_issues(). Noma'lum tur — 400."""
    if btype not in BLOCKS: raise HTTPException(400, f"Noma'lum blok turi: {str(btype)[:40]!r}")
    d = d if isinstance(d, dict) else {}
    img = lambda k="asset": A.ok(d.get(k), "image")
    items = lambda n, f: [f(x) for x in _lst(d.get("items"), n)]
    th = lambda x: {"title": _line(x.get("title"), 200), "html": _html(x.get("html"))}
    if btype == "heading": return {"text": _line(d.get("text"), 300), "level": _i(d.get("level"), 2, 3, 2)}
    if btype == "paragraph": return {"html": _html(d.get("html"))}
    if btype == "heading_paragraph": return {"heading": _line(d.get("heading"), 300), "html": _html(d.get("html"))}
    if btype == "quote": return {"text": _text(d.get("text"), 1000), "cite": _line(d.get("cite"), 200), "style": _pick(d.get("style"), ("quote", "impact"), "quote")}
    if btype == "list":
        return {"style": _pick(d.get("style"), ("numbered", "bulleted", "checkbox"), "bulleted"),
                "items": [_html(x, 4000) for x in (d.get("items") if isinstance(d.get("items"), list) else [])[:50]]}
    if btype == "table":
        rows = [[_line(c, 500) for c in (r if isinstance(r, list) else [])[:8]] for r in (d.get("rows") if isinstance(d.get("rows"), list) else [])[:50]]
        w = max([len(r) for r in rows] + [0])
        return {"header": _b(d.get("header"), True), "caption": _line(d.get("caption"), 300), "rows": [r + [""] * (w - len(r)) for r in rows]}
    if btype == "image":
        return {"asset": img(), "alt": _line(d.get("alt"), 300), "caption": _line(d.get("caption"), 500),
                "layout": _pick(d.get("layout"), ("centered", "full", "hero", "banner"), "centered")}
    if btype == "image_text":
        return {"asset": img(), "alt": _line(d.get("alt"), 300), "html": _html(d.get("html")), "side": _pick(d.get("side"), ("left", "right"), "left")}
    if btype == "gallery":
        return {"style": _pick(d.get("style"), ("grid", "carousel"), "grid"),
                "items": items(30, lambda x: {"asset": A.ok(x.get("asset"), "image"), "alt": _line(x.get("alt"), 300), "caption": _line(x.get("caption"), 300)})}
    if btype == "video":
        yt = None
        if d.get("youtube"):
            pv = PK.parse_video(str(d.get("youtube"))[:500])
            yt = pv.get("video_id") if pv.get("ok") and pv.get("provider") == "youtube" else None
            start = pv.get("start", 0) if yt else 0
        else:
            start = 0
        yid = yt or (str(d.get("yt_id") or "") if PK.YT_ID.match(str(d.get("yt_id") or "")) else None)
        caps = []
        for c_ in _lst(d.get("captions"), 5):
            a = A.ok(c_.get("asset"), "vtt")
            lang = str(c_.get("lang") or "uz").lower()
            if a and re.fullmatch(r"[a-z]{2,3}", lang): caps.append({"asset": a, "lang": lang, "label": _line(c_.get("label"), 40) or PK.SUB_LANGS.get(lang, lang)})
        return {"source": _pick(d.get("source"), ("file", "youtube"), "youtube" if yid and not d.get("asset") else "file"),
                "asset": A.ok(d.get("asset"), "video"), "poster": img("poster"), "captions": caps,
                "yt_id": yid, "yt_start": start if yt else _i(d.get("yt_start"), 0, 86400, 0), "title": _line(d.get("title"), 200), "caption": _line(d.get("caption"), 500)}
    if btype == "audio": return {"asset": A.ok(d.get("asset"), "audio"), "title": _line(d.get("title"), 200), "transcript": _text(d.get("transcript"), 20000)}
    if btype == "attachment": return {"asset": A.ok(d.get("asset"), "file", "image", "audio"), "title": _line(d.get("title"), 200), "desc": _text(d.get("desc"), 500)}
    if btype == "labeled_graphic":
        return {"asset": img(), "alt": _line(d.get("alt"), 300),
                "markers": [{"x": _f(m.get("x"), 0, 100, 50), "y": _f(m.get("y"), 0, 100, 50), "title": _line(m.get("title"), 200), "html": _html(m.get("html"), 4000)}
                            for m in _lst(d.get("markers"), 20)]}
    if btype == "accordion": return {"items": items(30, th)}
    if btype == "tabs": return {"items": items(12, th)}
    if btype == "flashcards":
        return {"style": _pick(d.get("style"), ("grid", "stack"), "grid"),
                "cards": [{"front": _text(c_.get("front"), 600), "back": _text(c_.get("back"), 1200)} for c_ in _lst(d.get("cards"), 40)]}
    if btype == "process": return {"items": items(20, th)}
    if btype == "timeline": return {"items": items(40, lambda x: {"date": _line(x.get("date"), 60), **th(x)})}
    if btype == "sorting":
        cats = [_line(x, 120) for x in (d.get("categories") if isinstance(d.get("categories"), list) else [])[:6]]
        return {"title": _line(d.get("title"), 300), "categories": cats,
                "items": items(30, lambda x: {"text": _line(x.get("text"), 200), "cat": _i(x.get("cat"), 0, max(0, len(cats) - 1), 0)})}
    if btype == "matching":
        return {"title": _line(d.get("title"), 300), "pairs": [{"left": _line(p.get("left"), 200), "right": _line(p.get("right"), 200)} for p in _lst(d.get("pairs"), 12)]}
    if btype == "knowledge": return {**_qclean(d), "retry": _b(d.get("retry"), True)}
    if btype == "question": return _qclean(d)
    if btype == "divider": return {"style": _pick(d.get("style"), ("line", "dots", "space"), "line")}
    if btype == "continue":
        return {"label": _line(d.get("label"), 60) or LABELS["continue"], "require": _pick(d.get("require"), ("none", "interactions"), "none"),
                "hint": _line(d.get("hint"), 200)}
    if btype == "button":
        url = PK.safe_href(str(d.get("url") or "")[:1000]) or ""
        return {"label": _line(d.get("label"), 80), "url": url, "text": _text(d.get("text"), 500)}
    raise HTTPException(400, "Blok turi")   # pragma: no cover

def default_block(btype: str) -> dict:
    """Yangi blok uchun boshlang'ich (Uzbek) matnlar — muharrir «+» bosilganda."""
    D = {"heading": {"text": "Yangi sarlavha", "level": 2}, "paragraph": {"html": ""}, "heading_paragraph": {"heading": "Sarlavha", "html": ""},
         "quote": {"text": "", "cite": "", "style": "quote"}, "list": {"style": "bulleted", "items": ["", ""]},
         "table": {"header": True, "caption": "", "rows": [["Ustun 1", "Ustun 2"], ["", ""]]},
         "accordion": {"items": [{"title": "1-bo'lim", "html": ""}, {"title": "2-bo'lim", "html": ""}]},
         "tabs": {"items": [{"title": "1-yorliq", "html": ""}, {"title": "2-yorliq", "html": ""}]},
         "flashcards": {"style": "grid", "cards": [{"front": "", "back": ""}, {"front": "", "back": ""}]},
         "process": {"items": [{"title": "1-qadam", "html": ""}, {"title": "2-qadam", "html": ""}]},
         "timeline": {"items": [{"date": "", "title": "", "html": ""}, {"date": "", "title": "", "html": ""}]},
         "sorting": {"title": "Elementlarni toifalarga ajrating", "categories": ["1-toifa", "2-toifa"], "items": [{"text": "", "cat": 0}, {"text": "", "cat": 1}]},
         "matching": {"title": "Mos juftlarni toping", "pairs": [{"left": "", "right": ""}, {"left": "", "right": ""}]},
         "knowledge": {"kind": "single", "question": "", "answers": [{"text": "", "correct": True}, {"text": "", "correct": False}, {"text": "", "correct": False}], "retry": True},
         "question": {"kind": "single", "question": "", "answers": [{"text": "", "correct": True}, {"text": "", "correct": False}, {"text": "", "correct": False}]},
         "continue": {"label": LABELS["continue"], "require": "none"}, "button": {"label": "Ochish", "url": "", "text": ""}}
    return clean_block(btype, D.get(btype, {}), _Assets(None))

def block_issues(btype: str, d: dict) -> list[tuple[str, str]]:
    """[(daraja, matn)] — «xato» eksportni to'xtatadi, «ogoh» — faqat eslatma (muharrir va sifat hisobotida)."""
    E, W = "xato", "ogoh"
    out = []
    req = lambda cond, msg, lvl=E: out.append((lvl, msg)) if not cond else None
    if btype == "heading": req(d["text"], "Sarlavha bo'sh")
    elif btype == "paragraph": req(d["html"], "Matn bo'sh", W)
    elif btype == "heading_paragraph": req(d["heading"] or d["html"], "Sarlavha va matn bo'sh", W)
    elif btype == "quote": req(d["text"], "Iqtibos matni bo'sh")
    elif btype == "list": req(any(d["items"]), "Ro'yxat bo'sh")
    elif btype == "table": req(any(any(c for c in r) for r in d["rows"]), "Jadval bo'sh")
    elif btype in ("image", "image_text", "labeled_graphic"):
        req(d["asset"], "Rasm tanlanmagan")
        req(d["alt"], "Rasm uchun muqobil matn (alt) yozilmagan — ko'zi ojiz talabalar uchun kerak", W)
        if btype == "labeled_graphic": req(d["markers"], "Rasmda belgi (nuqta) yo'q")
    elif btype == "gallery":
        req(any(x["asset"] for x in d["items"]), "Galereyada rasm yo'q")
        req(all(x["alt"] for x in d["items"] if x["asset"]), "Galereyadagi rasmlar uchun muqobil matn (alt) yozilmagan", W)
    elif btype == "video":
        req(d["asset"] if d["source"] == "file" else d["yt_id"], "Video fayl yuklanmagan" if d["source"] == "file" else "YouTube havolasi kiritilmagan")
        if d["source"] == "file" and d["asset"]: req(d["captions"], "Video uchun subtitr (.vtt) yo'q", W)
    elif btype == "audio": req(d["asset"], "Audio fayl yuklanmagan")
    elif btype == "attachment": req(d["asset"], "Fayl yuklanmagan")
    elif btype in ("accordion", "tabs", "process", "timeline"):
        req(d["items"], "Bandlar yo'q"); req(all(x["title"] or x["html"] for x in d["items"]), "Bo'sh band bor", W)
    elif btype == "flashcards": req(d["cards"] and all(c["front"] and c["back"] for c in d["cards"]), "Kartochkaning old yoki orqa tomoni bo'sh")
    elif btype == "sorting":
        req(len([c for c in d["categories"] if c]) >= 2, "Kamida 2 ta toifa kerak")
        req(d["items"] and all(x["text"] for x in d["items"]), "Saralanadigan elementlar bo'sh")
    elif btype == "matching": req(len(d["pairs"]) >= 2 and all(p["left"] and p["right"] for p in d["pairs"]), "Kamida 2 ta to'liq juft kerak")
    elif btype in ("knowledge", "question"):
        req(d["question"], "Savol matni bo'sh")
        if d["kind"] == "fill": req(d["accept"], "To'g'ri javob(lar) kiritilmagan")
        else:
            req(len(d["answers"]) >= 2 and all(a["text"] for a in d["answers"]), "Kamida 2 ta javob varianti kerak (bo'sh variant bor)")
            nc = sum(a["correct"] for a in d["answers"])
            req(nc >= 1, "To'g'ri javob belgilanmagan")
            if d["kind"] == "multiple": req(nc >= 2, "«Bir nechta javob» savolida bitta to'g'ri javob — «Bitta javob» turini tanlang", W)
    elif btype == "button": req(d["url"], "Havola (https://…) kiritilmagan")
    return out


# =============================================================================================
# Ruxsat va ko'lam
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"kurs: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Kurs muharriri: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def _tid(c: Ctx) -> int: return int(c.user.get("teacher_id") or 0)

def scope(c: Ctx, alias="k") -> tuple[str, tuple]:
    """O'qituvchi: o'zi muallif bo'lgan yoki o'zi o'qitadigan masofaviy kursga bog'langan kurslar; bo'lim — hammasi."""
    if c.role.key == TEACH:
        return (f"({alias}.author_id=? OR {alias}.dl_course_id IN (SELECT id FROM dl_courses WHERE teacher_id=? AND teacher_id>0))",
                (int(c.user["id"]), _tid(c)))
    if c.role.key in DEPT: return "1=1", ()
    return "0=1", ()

def _course(c: Ctx, cid: int, write: bool = False) -> dict:
    sw, sa = scope(c)
    r = db.one(_con, f"SELECT * FROM ku_courses k WHERE k.id=? AND k.deleted=0 AND {sw}", (int(cid), *sa))
    if not r:
        if db.one(_con, "SELECT 1 x FROM ku_courses WHERE id=? AND deleted=0", (int(cid),)):
            rbac.audit(_con, c, "kurs: begona kurs", RES, False, f"kurs #{cid}")
            raise AccessDenied("⛔ Bu kurs sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
        raise HTTPException(404, "Kurs topilmadi")
    if write and c.role.key not in AUTHORS:
        rbac.audit(_con, c, "kurs: tahrirlash rad etildi", RES, False, f"kurs #{cid}")
        raise AccessDenied("⛔ Kursni tahrirlash uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")
    return r

def _lesson(c: Ctx, lid: int, write: bool = False) -> tuple[dict, dict]:
    l = db.one(_con, "SELECT * FROM ku_lessons WHERE id=? AND deleted=0", (int(lid),))
    if not l: raise HTTPException(404, "Dars topilmadi")
    return l, _course(c, l["course_id"], write)

def _log(c: Ctx | None, cid, action: str, note: str = ""):
    u = c.user if c else {"id": None, "full_name": "Tizim"}
    _con.execute("INSERT INTO ku_log(ts,user_id,user_name,course_id,action,note) VALUES(?,?,?,?,?,?)",
                 (_now(), u.get("id"), u.get("full_name"), cid, action, (note or "")[:500]))

def _audit(c: Ctx, action: str, detail: str):
    rbac.audit(_con, c, f"kurs: {action}", RES, True, detail)


# =============================================================================================
# Sozlamalar (kurs, test), yorliqlar, urg'u rangi
# =============================================================================================
def _jload(s, d):
    try: v = json.loads(s) if s else d
    except (TypeError, ValueError): return d
    return v if isinstance(v, type(d)) else d

def clean_settings(s, base: dict | None = None) -> dict:
    s = s if isinstance(s, dict) else {}
    out = dict(base or SETTINGS)
    for k in ("sidebar", "lesson_count", "sequential", "search"):
        if k in s: out[k] = _b(s[k])
    if s.get("completion") in COMPLETION: out["completion"] = s["completion"]
    if "view_pct" in s: out["view_pct"] = _i(s["view_pct"], 10, 100, out["view_pct"])
    if s.get("mode") in MODES: out["mode"] = s["mode"]
    return out

def clean_quiz(s, base: dict | None = None) -> dict:
    s = s if isinstance(s, dict) else {}
    out = dict(base or QUIZ)
    if "pass_pct" in s: out["pass_pct"] = _i(s["pass_pct"], 0, 100, out["pass_pct"])
    if "attempts" in s: out["attempts"] = _i(s["attempts"], 0, 20, out["attempts"])
    if "draw" in s: out["draw"] = _i(s["draw"], 0, 200, out["draw"])
    for k in ("shuffle", "randomize"):
        if k in s: out[k] = _b(s[k])
    if s.get("reveal") in REVEAL: out["reveal"] = s["reveal"]
    if "intro" in s: out["intro"] = _text(s["intro"], 1000)
    return out

def clean_labels(v) -> dict:
    v = v if isinstance(v, dict) else {}
    return {k: t for k in LABELS if (t := _line(v.get(k), 80))}

def clean_accent(v) -> str:
    v = str(v or "").strip().upper()
    for k in PALETTE:
        if k.upper() == v: return k
    return DEFAULT_ACCENT

def nearest_accent(hexv: str) -> str:
    """Tashqi rang (masalan Rise colorAccent) → palitradagi eng yaqin rang (RGB masofasi)."""
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(hexv or "").strip())
    if not m: return DEFAULT_ACCENT
    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    a = rgb(m[1])
    return min(PALETTE, key=lambda k: sum((x - y) ** 2 for x, y in zip(a, rgb(k[1:]))))


# =============================================================================================
# Kurslar, darslar, bloklar
# =============================================================================================
def _lessons(cid: int) -> list[dict]:
    return db.rows(_con, "SELECT * FROM ku_lessons WHERE course_id=? AND deleted=0 ORDER BY pos, id", (int(cid),))

def _blocks(lid: int) -> list[dict]:
    return [{"id": r["uid"], "type": r["type"], "data": _jload(r["data"], {})} for r in db.rows(_con, "SELECT * FROM ku_blocks WHERE lesson_id=? ORDER BY pos, id", (int(lid),))]

def _nblocks(cid: int) -> dict:
    return {r["lesson_id"]: r["n"] for r in db.rows(_con, "SELECT b.lesson_id, COUNT(*) n FROM ku_blocks b JOIN ku_lessons l ON l.id=b.lesson_id "
                                                    "WHERE l.course_id=? AND l.deleted=0 GROUP BY b.lesson_id", (int(cid),))}

def _asset_url(aid) -> str | None: return f"{P}/assets/{int(aid)}" if aid else None

def course_row(r: dict, n_lessons: int | None = None) -> dict:
    return {"id": r["id"], "title": r["title"], "status": r["status"], "status_label": STATUS.get(r["status"], r["status"]), "status_note": r["status_note"] or "",
            "author_id": r["author_id"], "author_name": r["author_name"], "dl_course_id": r["dl_course_id"], "accent": clean_accent(r["accent"]),
            "cover": _asset_url(r["cover_asset"]), "updated_at": r["updated_at"], "updated_by": r["updated_by"], "created_at": r["created_at"],
            "src": r["src"] or "", "rev": r["rev"], "lessons": n_lessons}

def course_list(c: Ctx, q: str = "", status: str = "") -> dict:
    sw, sa = scope(c)
    rows = db.rows(_con, f"""SELECT k.*, (SELECT COUNT(*) FROM ku_lessons l WHERE l.course_id=k.id AND l.deleted=0) nl FROM ku_courses k
                             WHERE k.deleted=0 AND {sw} ORDER BY k.updated_at DESC, k.id DESC""", sa)
    if status in STATUS: rows = [r for r in rows if r["status"] == status]
    if q.strip():
        ql = q.lower().strip()
        rows = [r for r in rows if ql in f"{r['title']} {r['author_name']}".lower()]
    dl = {}
    ids = sorted({r["dl_course_id"] for r in rows if r["dl_course_id"]})
    if ids:
        for d in db.rows(_con, f"SELECT id, subject FROM dl_courses WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)): dl[d["id"]] = d["subject"]
    items = [{**course_row(r, r["nl"]), "dl_subject": dl.get(r["dl_course_id"])} for r in rows]
    counts = {k: sum(1 for r in items if r["status"] == k) for k in STATUS}
    return {"items": items, "total": len(items), "counts": counts}

def summary(c: Ctx) -> dict:
    """Jamlangan sonlar (rahbariyat): kurslar holati, darslar, bloklar, import va eksportlar — kurs nomlari va tarkibisiz."""
    n = lambda sql, a=(): (db.one(_con, sql, a) or {}).get("n") or 0
    by = {k: n("SELECT COUNT(*) n FROM ku_courses WHERE deleted=0 AND status=?", (k,)) for k in STATUS}
    return {"courses": sum(by.values()), "by_status": by, "status_labels": STATUS,
            "lessons": n("SELECT COUNT(*) n FROM ku_lessons l JOIN ku_courses k ON k.id=l.course_id WHERE l.deleted=0 AND k.deleted=0"),
            "blocks": n("SELECT COUNT(*) n FROM ku_blocks b JOIN ku_lessons l ON l.id=b.lesson_id JOIN ku_courses k ON k.id=l.course_id WHERE l.deleted=0 AND k.deleted=0"),
            "imported": n("SELECT COUNT(*) n FROM ku_courses WHERE deleted=0 AND src='rise'"),
            "exports": n("SELECT COUNT(*) n FROM ku_exports"), "authors": n("SELECT COUNT(DISTINCT author_id) n FROM ku_courses WHERE deleted=0")}

def _check_dl(c: Ctx, dl_course_id) -> int | None:
    if not dl_course_id: return None
    r = db.one(_con, "SELECT id, teacher_id FROM dl_courses WHERE id=?", (int(dl_course_id),))
    if not r: raise HTTPException(400, "Masofaviy kurs topilmadi")
    if c.role.key == TEACH and int(r["teacher_id"] or 0) != _tid(c):
        rbac.audit(_con, c, "kurs: begona masofaviy kursga bog'lash", RES, False, f"dl #{dl_course_id}")
        raise AccessDenied("⛔ Faqat o'zingiz o'qitadigan masofaviy kursga bog'lash mumkin. So'rov audit jurnaliga yozildi.")
    return r["id"]

def dl_options(c: Ctx) -> list[dict]:
    w, a = ("WHERE c.teacher_id=?", (_tid(c),)) if c.role.key == TEACH else ("", ())
    return db.rows(_con, f"SELECT c.id, c.subject, c.direction, c.course, t.full_name teacher FROM dl_courses c LEFT JOIN teachers t ON t.id=c.teacher_id {w} "
                         "ORDER BY c.subject, c.id LIMIT 600", a)

def create_course(c: Ctx, title: str, description: str = "", dl_course_id=None, src: str = "", first_lesson: bool = True) -> dict:
    title = _line(title, 200) or "Nomsiz kurs"
    dl = _check_dl(c, dl_course_id)
    with _lock:
        now = _now()
        cid = _con.execute("""INSERT INTO ku_courses(title,description,accent,settings,labels,author_id,author_name,dl_course_id,status,rev,created_at,updated_at,updated_by,src)
                              VALUES(?,?,?,?,?,?,?,?,'qoralama',1,?,?,?,?)""",
                           (title, _html(description, 4000), DEFAULT_ACCENT, json.dumps(SETTINGS), "{}", c.user["id"], c.user["full_name"], dl, now, now,
                            c.user["full_name"], src)).lastrowid
        if first_lesson:
            _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,1,'blocks','1-dars','{}',1,?,?)",
                         (cid, _uid("l"), now, c.user["full_name"]))
        _log(c, cid, "kurs yaratildi", title); _con.commit()
    _audit(c, "kurs yaratildi", f"kurs #{cid} · {title[:80]}")
    return {"ok": True, "id": cid}

def _bump(cid: int, c: Ctx | None, content: bool = True, rev: bool = True):
    """Kurs o'zgardi: rev (tartib/sozlama), updated_*; tasdiqlangan kurs o'zgarsa — qoralamaga qaytadi (o'qituvchi tahriri ko'rib chiqishdagini ham)."""
    co = db.one(_con, "SELECT status FROM ku_courses WHERE id=?", (cid,))
    st, note = co["status"], None
    if content and (st == "tasdiqlangan" or (st == "korib_chiqishda" and c is not None and c.role.key not in DEPT)):
        st, note = "qoralama", "Tasdiq/ko'rib chiqishdan keyin o'zgartirildi — qayta yuborish kerak"
    _con.execute(f"UPDATE ku_courses SET updated_at=?, updated_by=?, status=?{', rev=rev+1' if rev else ''}{', status_note=?' if note else ''} WHERE id=?",
                 (_now(), c.user["full_name"] if c else "Tizim", st, *((note,) if note else ()), cid))
    if note: _log(c, cid, "holat: qoralama", note)

def _conflict(kind: str, cur_rev: int, by: str, at: str):
    raise HTTPException(409, {"message": f"{kind} boshqa oynada yoki boshqa foydalanuvchi tomonidan o'zgartirilgan ({by or '—'}, {at or '—'}). "
                                         "Oxirgi holatni yuklang yoki o'zgarishlaringizni ustidan yozing.", "conflict": True, "rev": cur_rev, "by": by, "at": at})

def course_view(c: Ctx, cid: int) -> dict:
    co = _course(c, cid)
    nb = _nblocks(cid)
    ls = []
    for l in _lessons(cid):
        q = clean_quiz(_jload(l["settings"], {})) if l["type"] == "quiz" else None
        ls.append({"id": l["id"], "uid": l["uid"], "type": l["type"], "title": l["title"], "rev": l["rev"], "blocks": nb.get(l["id"], 0), "quiz": q})
    dl = db.one(_con, "SELECT id, subject, direction, course FROM dl_courses WHERE id=?", (co["dl_course_id"],)) if co["dl_course_id"] else None
    ex = db.rows(_con, "SELECT id, mode, size, ts, user_name, validation, rev FROM ku_exports WHERE course_id=? ORDER BY id DESC LIMIT 8", (cid,))
    return {**course_row(co, len(ls)), "description": co["description"] or "", "cover_asset": co["cover_asset"], "cover_alt": co["cover_alt"] or "",
            "settings": clean_settings(_jload(co["settings"], {})), "labels": clean_labels(_jload(co["labels"], {})), "lessons_list": ls, "dl": dl,
            "approved_at": co["approved_at"], "approved_name": co["approved_name"], "submitted_at": co["submitted_at"],
            "import_report": _jload(co["import_report"], None) if co["src"] == "rise" else None,
            "exports": [{**e, "validation": {"ok": _jload(e["validation"], {}).get("ok")}} for e in ex],
            "caps": {"write": c.role.key in AUTHORS, "approve": c.role.key in DEPT, "submit": c.role.key in AUTHORS and co["status"] == "qoralama",
                     "delete": c.role.key in DEPT or (co["author_id"] == c.user["id"] and co["status"] == "qoralama")},
            "log": db.rows(_con, "SELECT ts, user_name, action, note FROM ku_log WHERE course_id=? ORDER BY id DESC LIMIT 30", (cid,))}

def update_course(c: Ctx, cid: int, body: dict) -> dict:
    co = _course(c, cid, write=True)
    rev = body.get("rev")
    if rev is not None and int(rev) != co["rev"]: _conflict("Kurs sozlamalari", co["rev"], co["updated_by"], co["updated_at"])
    A = _Assets(cid)
    upd = {}
    if "title" in body: upd["title"] = _line(body["title"], 200) or co["title"]
    if "description" in body: upd["description"] = _html(body["description"], 4000)
    if "accent" in body: upd["accent"] = clean_accent(body["accent"])
    if "cover_asset" in body: upd["cover_asset"] = A.ok(body["cover_asset"], "image")
    if "cover_alt" in body: upd["cover_alt"] = _line(body["cover_alt"], 300)
    if "settings" in body: upd["settings"] = json.dumps(clean_settings(body["settings"], clean_settings(_jload(co["settings"], {}))))
    if "labels" in body: upd["labels"] = json.dumps(clean_labels(body["labels"]), ensure_ascii=False)
    if "dl_course_id" in body: upd["dl_course_id"] = _check_dl(c, body["dl_course_id"])
    with _lock:
        if upd:
            _con.execute(f"UPDATE ku_courses SET {', '.join(k + '=?' for k in upd)} WHERE id=?", (*upd.values(), cid))
            _bump(cid, c)
            _log(c, cid, "kurs sozlamalari", ", ".join(upd)[:200])
        _con.commit()
    _audit(c, "kurs sozlamalari", f"kurs #{cid} · {', '.join(upd)[:120]}")
    return course_view(c, cid)

def delete_course(c: Ctx, cid: int) -> dict:
    co = _course(c, cid, write=True)
    if not (c.role.key in DEPT or (co["author_id"] == c.user["id"] and co["status"] == "qoralama")):
        rbac.audit(_con, c, "kurs: o'chirish rad etildi", RES, False, f"kurs #{cid}")
        raise AccessDenied("⛔ Kursni faqat muallif (qoralama holatida) yoki Masofaviy ta'lim bo'limi o'chiradi.")
    with _lock:
        _con.execute("UPDATE ku_courses SET deleted=1, updated_at=?, updated_by=? WHERE id=?", (_now(), c.user["full_name"], cid))
        _log(c, cid, "kurs o'chirildi"); _con.commit()
    _audit(c, "kurs o'chirildi", f"kurs #{cid} · {co['title'][:80]}")
    return {"ok": True}

def add_lesson(c: Ctx, cid: int, ltype: str = "blocks", title: str = "", after: int | None = None) -> dict:
    co = _course(c, cid, write=True)
    ltype = "quiz" if ltype == "quiz" else "blocks"
    ls = _lessons(cid)
    if len(ls) >= MAX_LESSONS: raise HTTPException(400, f"Kursda {MAX_LESSONS} tadan ortiq dars bo'lmaydi")
    title = _line(title, 200) or ("Yakuniy test" if ltype == "quiz" else f"{len(ls) + 1}-dars")
    ids = [l["id"] for l in ls]
    pos = ids.index(after) + 1 if after in ids else len(ids)
    with _lock:
        lid = _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                           (cid, _uid("l"), 0, ltype, title, json.dumps(QUIZ) if ltype == "quiz" else "{}", _now(), c.user["full_name"])).lastrowid
        ids.insert(pos, lid)
        for i, x in enumerate(ids, 1): _con.execute("UPDATE ku_lessons SET pos=? WHERE id=?", (i, x))
        _bump(cid, c); _log(c, cid, "dars qo'shildi", title); _con.commit()
    _audit(c, "dars qo'shildi", f"kurs #{cid} · {title[:80]}")
    return {"ok": True, "id": lid, "course": course_view(c, cid)}

def reorder_lessons(c: Ctx, cid: int, order: list, rev=None) -> dict:
    co = _course(c, cid, write=True)
    if rev is not None and int(rev) != co["rev"]: _conflict("Darslar tartibi", co["rev"], co["updated_by"], co["updated_at"])
    ids = [l["id"] for l in _lessons(cid)]
    try: order = [int(x) for x in order]
    except (TypeError, ValueError): raise HTTPException(400, "Tartib noto'g'ri")
    if sorted(order) != sorted(ids): raise HTTPException(400, "Tartib kursdagi darslarga mos emas — sahifani yangilang")
    with _lock:
        for i, x in enumerate(order, 1): _con.execute("UPDATE ku_lessons SET pos=? WHERE id=?", (i, x))
        _bump(cid, c); _log(c, cid, "darslar tartibi"); _con.commit()
    _audit(c, "darslar tartibi", f"kurs #{cid}")
    return course_view(c, cid)

def delete_lesson(c: Ctx, lid: int) -> dict:
    l, co = _lesson(c, lid, write=True)
    snapshot(c, co["id"], "auto", f"«{l['title']}» darsi o'chirilishidan oldin")
    with _lock:
        _con.execute("UPDATE ku_lessons SET deleted=1, updated_at=?, updated_by=? WHERE id=?", (_now(), c.user["full_name"], lid))
        _bump(co["id"], c); _log(c, co["id"], "dars o'chirildi", l["title"]); _con.commit()
    _audit(c, "dars o'chirildi", f"kurs #{co['id']} · {l['title'][:80]}")
    return course_view(c, co["id"])

def duplicate_lesson(c: Ctx, lid: int) -> dict:
    l, co = _lesson(c, lid, write=True)
    r = add_lesson(c, co["id"], l["type"], f"{l['title']} (nusxa)"[:200], after=lid)
    with _lock:
        _con.execute("UPDATE ku_lessons SET settings=? WHERE id=?", (l["settings"], r["id"]))
        for i, b in enumerate(_blocks(lid), 1):
            _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)", (r["id"], _uid(), i, b["type"], json.dumps(b["data"], ensure_ascii=False)))
        _con.commit()
    return {"ok": True, "id": r["id"], "course": course_view(c, co["id"])}

def lesson_view(c: Ctx, lid: int) -> dict:
    l, co = _lesson(c, lid)
    bl = _blocks(lid)
    return {"id": l["id"], "uid": l["uid"], "course_id": co["id"], "type": l["type"], "title": l["title"], "rev": l["rev"],
            "updated_at": l["updated_at"], "updated_by": l["updated_by"], "quiz": clean_quiz(_jload(l["settings"], {})) if l["type"] == "quiz" else None,
            "blocks": [{**b, "issues": [{"level": a, "msg": m} for a, m in block_issues(b["type"], b["data"])]} for b in bl],
            "status": co["status"], "course_rev": co["rev"]}

def save_lesson(c: Ctx, lid: int, body: dict) -> dict:
    """Avtosaqlash: darsning to'liq holati (nom, test sozlamasi, bloklar). rev mos kelmasa — 409 (ziddiyat), hech narsa yozilmaydi.
    force=True — ziddiyatda foydalanuvchi o'z nusxasini ustidan yozishni tanladi (eski holat avval versiya sifatida saqlanadi)."""
    l, co = _lesson(c, lid, write=True)
    rev, force = body.get("rev"), bool(body.get("force"))
    if not force and (rev is None or int(rev) != l["rev"]): _conflict("Dars", l["rev"], l["updated_by"], l["updated_at"])
    raw = body.get("blocks")
    if not isinstance(raw, list): raise HTTPException(400, "Bloklar ro'yxati kerak")
    if len(raw) > MAX_BLOCKS: raise HTTPException(400, f"Darsda {MAX_BLOCKS} tadan ortiq blok bo'lmaydi")
    A = _Assets(co["id"])
    allowed = ("question",) if l["type"] == "quiz" else tuple(LESSON_BLOCKS)
    seen, out = set(), []
    for i, b in enumerate(raw, 1):
        if not isinstance(b, dict): raise HTTPException(400, f"{i}-blok noto'g'ri")
        t = b.get("type")
        if t not in allowed:
            raise HTTPException(400, f"{i}-blok: «{str(t)[:30]}» turi {'test darsida' if l['type'] == 'quiz' else 'oddiy darsda'} ishlatilmaydi")
        uid = str(b.get("id") or "")
        if not _UID_RX.match(uid) or uid in seen: uid = _uid()
        seen.add(uid)
        out.append((uid, t, clean_block(t, b.get("data"), A)))
    title = _line(body.get("title"), 200) if "title" in body else l["title"]
    settings = json.dumps(clean_quiz(body.get("quiz"), clean_quiz(_jload(l["settings"], {})))) if l["type"] == "quiz" and "quiz" in body else l["settings"]
    if force and rev is not None and int(rev) != l["rev"]: snapshot(c, co["id"], "auto", f"«{l['title']}» — ziddiyatda ustidan yozishdan oldin")
    with _lock:
        _con.execute("DELETE FROM ku_blocks WHERE lesson_id=?", (lid,))
        for i, (uid, t, d) in enumerate(out, 1):
            _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)", (lid, uid, i, t, json.dumps(d, ensure_ascii=False)))
        _con.execute("UPDATE ku_lessons SET title=?, settings=?, rev=rev+1, updated_at=?, updated_by=? WHERE id=?",
                     (title or l["title"], settings, _now(), c.user["full_name"], lid))
        _bump(co["id"], c, rev=title != l["title"])
        _con.commit()
    last = db.one(_con, "SELECT ts FROM ku_versions WHERE course_id=? ORDER BY id DESC LIMIT 1", (co["id"],))
    if not last or (clock.now().replace(tzinfo=None) - _parse_ts(last["ts"])).total_seconds() > AUTO_SNAPSHOT_SEC:
        snapshot(c, co["id"], "auto", "Avtomatik saqlash")
    _audit(c, "dars saqlandi", f"kurs #{co['id']} · dars #{lid} · {len(out)} blok")
    return {"ok": True, **lesson_view(c, lid)}

def _parse_ts(s: str):
    import datetime as dt
    try: return dt.datetime.fromisoformat(s).replace(tzinfo=None)
    except (TypeError, ValueError): return dt.datetime(2000, 1, 1)


# =============================================================================================
# Fayllar (rasm, video, audio, subtitr, ilova) — DATA_DIR/kurs/assets/<kurs>/<id>.<ext>
# =============================================================================================
def _sniff_image(head: bytes) -> str | None:
    if head[:8] == b"\x89PNG\r\n\x1a\n": return "png"
    if head[:3] == b"\xff\xd8\xff": return "jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"): return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return "webp"
    return None

def _apath(a: dict) -> Path: return store() / a["path"]

def _save_asset(c: Ctx | None, cid: int, kind: str, ext: str, name: str, data: bytes | None = None, tmp: Path | None = None,
                size: int = 0, sha: str = "", meta: dict | None = None) -> int:
    d = store() / "assets" / str(int(cid)); d.mkdir(parents=True, exist_ok=True)
    with _lock:
        aid = _con.execute("INSERT INTO ku_assets(course_id,kind,ext,name,path,size,sha256,meta,user_id,user_name,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (cid, kind, ext, _line(name, 160) or kind, "", len(data) if data is not None else size,
                            hashlib.sha256(data).hexdigest() if data is not None else sha, json.dumps(meta or {}, ensure_ascii=False),
                            c.user["id"] if c else None, c.user["full_name"] if c else "Tizim", _now())).lastrowid
        rel = Path("assets") / str(int(cid)) / f"{aid}.{ext}"
        if data is not None: (store() / rel).write_bytes(data)
        else: os.replace(tmp, store() / rel)
        _con.execute("UPDATE ku_assets SET path=? WHERE id=?", (str(rel), aid))
        _con.commit()
    return aid

def image_from_bytes(raw: bytes) -> tuple[bytes, str, dict]:
    """Rasm → (me'yorlangan baytlar, kengaytma, {w, h}): metama'lumot tashlanadi, ≤ 1600px, piksel bombasi — 413."""
    if not _sniff_image(raw[:16]): raise HTTPException(415, "Rasm .png, .jpg, .gif yoki .webp bo'lishi kerak")
    r = PK._norm_image(raw, strict=True)
    if not r: raise HTTPException(415, "Rasmni o'qib bo'lmadi yoki juda kichik (kamida 32×32 piksel)")
    data, ext = r
    from PIL import Image
    w, h = Image.open(io.BytesIO(data)).size
    return data, ext, {"w": w, "h": h}

def asset_row(a: dict) -> dict:
    return {"id": a["id"], "kind": a["kind"], "ext": a["ext"], "name": a["name"], "size": a["size"], "meta": _jload(a["meta"], {}), "url": _asset_url(a["id"]), "ts": a["ts"]}

def upload_bytes(c: Ctx, cid: int, kind: str, raw: bytes, name: str, lang: str = "uz") -> dict:
    """Kichik fayllar (rasm, subtitr, ilova) — tana xotirada (chegara oldindan tekshirilgan)."""
    _course(c, cid, write=True)
    if not raw: raise HTTPException(400, "Fayl bo'sh")
    if kind == "image":
        data, ext, meta = image_from_bytes(raw)
    elif kind == "vtt":
        v = PK.to_vtt(raw); data, ext, meta = v["vtt"].encode("utf-8"), "vtt", {"cues": v["cues"], "lang": (lang or "uz")[:3]}
    elif kind == "file":
        ext = PK._sniff_asset(raw)
        if ext not in FILE_EXTS + ("png", "jpg"): raise HTTPException(415, "Fayl turi qabul qilinmaydi — PDF, Word, PowerPoint, Excel yoki rasm bo'lsin")
        data, meta = raw, {}
    else:
        raise HTTPException(400, "Fayl turi noma'lum")
    aid = _save_asset(c, cid, kind, ext, name, data=data, meta=meta)
    with _lock: _log(c, cid, "fayl yuklandi", f"{ASSET_KINDS[kind]} · {name[:80]}"); _con.commit()
    _audit(c, "fayl yuklandi", f"kurs #{cid} · {kind} · {name[:60]} · {len(data)} bayt")
    return {"ok": True, **asset_row(db.one(_con, "SELECT * FROM ku_assets WHERE id=?", (aid,)))}

def upload_stream(c: Ctx, cid: int, kind: str, up: dict, name: str) -> dict:
    """Katta media (video / audio) — PK._stream_upload natijasi (diskda)."""
    try:
        _course(c, cid, write=True)
        aid = _save_asset(c, cid, kind, up["kind"], name, tmp=up["path"], size=up["size"], sha=up["sha256"])
    finally:
        Path(up["path"]).unlink(missing_ok=True)
    with _lock: _log(c, cid, "fayl yuklandi", f"{ASSET_KINDS[kind]} · {name[:80]} · {up['size'] // 1024} KB"); _con.commit()
    _audit(c, "fayl yuklandi", f"kurs #{cid} · {kind} · {name[:60]} · {up['size']} bayt")
    return {"ok": True, **asset_row(db.one(_con, "SELECT * FROM ku_assets WHERE id=?", (aid,)))}

def assets_list(c: Ctx, cid: int) -> list[dict]:
    _course(c, cid)
    return [asset_row(a) for a in db.rows(_con, "SELECT * FROM ku_assets WHERE course_id=? AND deleted=0 ORDER BY id DESC", (cid,))]

def serve_asset(c: Ctx, aid: int, rng: str | None) -> Response:
    a = db.one(_con, "SELECT * FROM ku_assets WHERE id=? AND deleted=0", (int(aid),))
    if not a: raise HTTPException(404, "Fayl topilmadi")
    _course(c, a["course_id"])
    f = _apath(a)
    if not f.is_file(): raise HTTPException(410, "Fayl diskda yo'q")
    ct = PK._CT.get(a["ext"], "application/octet-stream")
    hd = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300", "Content-Security-Policy": "default-src 'none'; sandbox"}
    if a["kind"] == "file":
        hd["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(PK._ascii(Path(a['name']).stem, 60) + '.' + a['ext'])}"
    return PK.range_response(f, ct, rng, hd)


# =============================================================================================
# Versiyalar
# =============================================================================================
def snapshot_data(cid: int) -> dict:
    co = db.one(_con, "SELECT * FROM ku_courses WHERE id=?", (cid,))
    return {"course": {k: co[k] for k in ("title", "description", "cover_asset", "cover_alt", "accent", "dl_course_id")} |
                      {"settings": _jload(co["settings"], {}), "labels": _jload(co["labels"], {})},
            "lessons": [{"uid": l["uid"], "type": l["type"], "title": l["title"], "settings": _jload(l["settings"], {}),
                         "blocks": [{"uid": b["id"], "type": b["type"], "data": b["data"]} for b in _blocks(l["id"])]} for l in _lessons(cid)]}

def snapshot(c: Ctx | None, cid: int, kind: str = "qo'lda", note: str = "") -> int:
    data = json.dumps(snapshot_data(cid), ensure_ascii=False)
    with _lock:
        no = (db.one(_con, "SELECT MAX(no) n FROM ku_versions WHERE course_id=?", (cid,)) or {}).get("n") or 0
        vid = _con.execute("INSERT INTO ku_versions(course_id,no,ts,user_id,user_name,kind,note,data,size) VALUES(?,?,?,?,?,?,?,?,?)",
                           (cid, no + 1, _now(), c.user["id"] if c else None, c.user["full_name"] if c else "Tizim", kind, _line(note, 200), data, len(data))).lastrowid
        keep = {r["id"] for r in db.rows(_con, "SELECT id FROM ku_versions WHERE course_id=? ORDER BY id DESC LIMIT ?", (cid, KEEP_VERSIONS))}
        appr = (db.one(_con, "SELECT approved_version v FROM ku_courses WHERE id=?", (cid,)) or {}).get("v")
        _con.execute(f"DELETE FROM ku_versions WHERE course_id=? AND kind<>'tasdiq' AND id NOT IN ({','.join('?' * len(keep))}) AND id<>?",
                     (cid, *keep, appr or 0))
        _con.commit()
    return vid

def versions(c: Ctx, cid: int) -> list[dict]:
    co = _course(c, cid)
    out = []
    for r in db.rows(_con, "SELECT id, no, ts, user_name, kind, note, size, data FROM ku_versions WHERE course_id=? ORDER BY id DESC", (cid,)):
        d = _jload(r.pop("data"), {})
        r.update(lessons=len(d.get("lessons") or []), blocks=sum(len(l.get("blocks") or []) for l in d.get("lessons") or []),
                 approved=r["id"] == co["approved_version"])
        out.append(r)
    return out

def save_version(c: Ctx, cid: int, note: str) -> dict:
    _course(c, cid, write=True)
    vid = snapshot(c, cid, "qo'lda", note or "Qo'lda saqlangan versiya")
    with _lock: _log(c, cid, "versiya saqlandi", note); _con.commit()
    _audit(c, "versiya saqlandi", f"kurs #{cid} · v#{vid}")
    return {"ok": True, "id": vid, "versions": versions(c, cid)}

def _apply_snapshot(c: Ctx | None, cid: int, data: dict):
    """Surat → kurs (_lock ostida, commit'siz). Darslar yangi qatorlar bilan qayta yoziladi (uid saqlanadi)."""
    A = _Assets(cid)
    co = data.get("course") or {}
    _con.execute("UPDATE ku_courses SET title=?, description=?, cover_asset=?, cover_alt=?, accent=?, settings=?, labels=? WHERE id=?",
                 (_line(co.get("title"), 200) or "Nomsiz kurs", _html(co.get("description"), 4000), A.ok(co.get("cover_asset"), "image"),
                  _line(co.get("cover_alt"), 300), clean_accent(co.get("accent")), json.dumps(clean_settings(co.get("settings"))),
                  json.dumps(clean_labels(co.get("labels")), ensure_ascii=False), cid))
    _con.execute("UPDATE ku_lessons SET deleted=1 WHERE course_id=? AND deleted=0", (cid,))
    for i, l in enumerate((data.get("lessons") or [])[:MAX_LESSONS], 1):
        lt = "quiz" if l.get("type") == "quiz" else "blocks"
        lid = _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                           (cid, l.get("uid") if _UID_RX.match(str(l.get("uid") or "")) else _uid("l"), i, lt, _line(l.get("title"), 200) or f"{i}-dars",
                            json.dumps(clean_quiz(l.get("settings"))) if lt == "quiz" else "{}", _now(), c.user["full_name"] if c else "Tizim")).lastrowid
        allowed = ("question",) if lt == "quiz" else tuple(LESSON_BLOCKS)
        for j, b in enumerate([b for b in (l.get("blocks") or []) if isinstance(b, dict) and b.get("type") in allowed][:MAX_BLOCKS], 1):
            _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)",
                         (lid, b.get("uid") if _UID_RX.match(str(b.get("uid") or "")) else _uid(), j, b["type"], json.dumps(clean_block(b["type"], b.get("data"), A), ensure_ascii=False)))

def restore_version(c: Ctx, cid: int, vid: int) -> dict:
    _course(c, cid, write=True)
    v = db.one(_con, "SELECT * FROM ku_versions WHERE id=? AND course_id=?", (int(vid), cid))
    if not v: raise HTTPException(404, "Versiya topilmadi")
    snapshot(c, cid, "auto", f"v{v['no']} tiklanishidan oldingi holat")
    with _lock:
        _apply_snapshot(c, cid, _jload(v["data"], {}))
        _bump(cid, c); _log(c, cid, "versiya tiklandi", f"v{v['no']} · {v['ts']}"); _con.commit()
    _audit(c, "versiya tiklandi", f"kurs #{cid} · v{v['no']}")
    return {"ok": True, "course": course_view(c, cid)}


# =============================================================================================
# Ko'rib chiqish: yuborish → tasdiqlash / qaytarish
# =============================================================================================
def course_issues(cid: int) -> dict:
    """Eksport / yuborishdan oldingi tekshiruv: {"errors": [...], "warnings": [...]} — har biri «Dars · blok: matn»."""
    errs, warns = [], []
    ls = _lessons(cid)
    if not ls: errs.append("Kursda dars yo'q")
    for n, l in enumerate(ls, 1):
        bl = _blocks(l["id"])
        if not bl: (errs if l["type"] == "quiz" else warns).append(f"{n}. {l['title']}: {'savollar yo`q' if l['type'] == 'quiz' else 'bo`sh dars'}".replace("`", "'"))
        for k, b in enumerate(bl, 1):
            for lvl, m in block_issues(b["type"], b["data"]):
                (errs if lvl == "xato" else warns).append(f"{n}. {l['title']} · {k}-blok ({BLOCKS[b['type']][0]}): {m}")
    return {"errors": errs, "warnings": warns}

def action(c: Ctx, cid: int, act: str, note: str = "") -> dict:
    co = _course(c, cid, write=True)
    note = _line(note, 500)
    if act == "submit":
        if co["status"] != "qoralama": raise HTTPException(400, "Kurs allaqachon ko'rib chiqishda yoki tasdiqlangan")
        iss = course_issues(cid)
        if iss["errors"]: raise HTTPException(400, {"message": f"Yuborishdan oldin {len(iss['errors'])} ta xatoni tuzating", "errors": iss["errors"][:30]})
        st, upd = "korib_chiqishda", {"submitted_at": _now(), "status_note": note}
    elif act in ("approve", "return"):
        if c.role.key not in DEPT:
            rbac.audit(_con, c, f"kurs: {act} rad etildi", RES, False, f"kurs #{cid}")
            raise AccessDenied("⛔ Kursni faqat Masofaviy ta'lim bo'limi tasdiqlaydi yoki qaytaradi. So'rov audit jurnaliga yozildi.")
        if act == "return":
            if co["status"] == "qoralama": raise HTTPException(400, "Kurs qoralama holatida")
            if not note: raise HTTPException(400, "Qaytarish sababini yozing")
            st, upd = "qoralama", {"status_note": note}
        else:
            if co["status"] == "tasdiqlangan": raise HTTPException(400, "Kurs allaqachon tasdiqlangan")
            iss = course_issues(cid)
            if iss["errors"]: raise HTTPException(400, {"message": f"Tasdiqlashdan oldin {len(iss['errors'])} ta xatoni tuzating", "errors": iss["errors"][:30]})
            vid = snapshot(c, cid, "tasdiq", note or "Tasdiqlangan versiya")
            st, upd = "tasdiqlangan", {"approved_by": c.user["id"], "approved_name": c.user["full_name"], "approved_at": _now(), "approved_version": vid, "status_note": note}
    else:
        raise HTTPException(400, "Amal noma'lum")
    with _lock:
        _con.execute(f"UPDATE ku_courses SET status=?, {', '.join(k + '=?' for k in upd)}, updated_at=?, updated_by=? WHERE id=?",
                     (st, *upd.values(), _now(), c.user["full_name"], cid))
        _log(c, cid, {"submit": "ko'rib chiqishga yuborildi", "approve": "tasdiqlandi", "return": "qaytarildi"}[act], note); _con.commit()
    _audit(c, {"submit": "ko'rib chiqishga yuborildi", "approve": "tasdiqlandi", "return": "qaytarildi"}[act], f"kurs #{cid} · {note[:80]}")
    return {"ok": True, "course": course_view(c, cid)}


# =============================================================================================
# Kontent (window.KURS) — ko'rish va eksport uchun YAGONA quruvchi
# =============================================================================================
_SUB = {"image": "img", "video": "video", "audio": "audio", "vtt": "video", "file": "files"}

def _asset_path(a: dict) -> str:
    return f"assets/{_SUB.get(a['kind'], 'files')}/{a['id']}-{PK._ascii(Path(a['name'] or '').stem, 40)}.{a['ext']}"

def build_content(cid: int, mode: str = "none") -> tuple[dict, dict]:
    """→ (content, files {zip yo'li: diskdagi fayl}). Asset id → «assets/<tur>/<id>-<nom>.<ext>». Video/audio — PK.BigFile (oqim bilan)."""
    co = db.one(_con, "SELECT * FROM ku_courses WHERE id=?", (int(cid),))
    rows = {r["id"]: r for r in db.rows(_con, "SELECT * FROM ku_assets WHERE course_id=? AND deleted=0", (cid,))}
    files: dict = {}
    def ref(aid):
        a = rows.get(aid) if aid else None
        if not a or not _apath(a).is_file(): return None
        p = _asset_path(a)
        files[p] = PK.BigFile(_apath(a), a["sha256"] or "", a["size"] or 0) if a["kind"] in ("video", "audio") else _apath(a)
        return p
    def conv(t: str, d: dict) -> dict:
        d = json.loads(json.dumps(d))
        if t in ("image", "image_text", "labeled_graphic"): d["src"] = ref(d.pop("asset", None))
        elif t == "gallery": d["items"] = [{"src": s, "alt": x["alt"], "caption": x["caption"]} for x in d["items"] if (s := ref(x.get("asset")))]
        elif t == "video":
            d["src"] = ref(d.pop("asset", None)) if d["source"] == "file" else None
            d["poster"] = ref(d.get("poster")) if d["source"] == "file" else None
            d["captions"] = [{"src": s, "lang": x["lang"], "label": x["label"]} for x in d["captions"] if (s := ref(x.get("asset")))] if d["source"] == "file" else []
            if d["source"] != "file": d.pop("asset", None)
        elif t == "audio": d["src"] = ref(d.pop("asset", None))
        elif t == "attachment":
            a = rows.get(d.get("asset"))
            d["src"] = ref(d.pop("asset", None))
            if a and d["src"]: d.update(name=a["name"], size=a["size"], ext=a["ext"])
        return d
    lessons, mastery = [], None
    for l in _lessons(cid):
        bl = _blocks(l["id"])
        if l["type"] == "quiz":
            qz = clean_quiz(_jload(l["settings"], {}))
            if mastery is None: mastery = qz["pass_pct"]
            lessons.append({"id": l["uid"], "type": "quiz", "title": l["title"], "quiz": qz,
                            "questions": [{"id": b["id"], **{k: v for k, v in b["data"].items()}} for b in bl]})
        else:
            lessons.append({"id": l["uid"], "type": "blocks", "title": l["title"], "blocks": [{"id": b["id"], "type": b["type"], **conv(b["type"], b["data"])} for b in bl]})
    st = clean_settings(_jload(co["settings"], {}))
    logo = PK._logo_path()
    if logo: files["assets/logo.png"] = logo
    cover = ref(co["cover_asset"])
    content = {"v": 1, "kind": "kurs", "id": f"isft-kurs-{cid}", "title": co["title"], "description": co["description"] or "", "lang": "uz",
               "accent": clean_accent(co["accent"]), "cover": {"src": cover, "alt": co["cover_alt"] or ""} if cover else None,
               "author": co["author_name"] or "", "brand": {"name": PK._brand_full(), "logo": "assets/logo.png" if logo else None},
               "settings": {k: st[k] for k in ("sidebar", "lesson_count", "sequential", "search")},
               "labels": {**LABELS, **clean_labels(_jload(co["labels"], {}))},
               "tracking": {"mode": mode, "activity_id": f"{ACTIVITY_BASE}/{int(cid)}", "completion": st["completion"], "view_pct": st["view_pct"],
                            "mastery": mastery if st["completion"] != "view" else None},
               "lessons": lessons}
    return content, files

def content_js(content: dict) -> bytes:
    j = json.dumps(content, ensure_ascii=False, separators=(",", ":")).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("</", "<\\/")
    return ("window.KURS = " + j + ";").encode("utf-8")

def player_files() -> dict:
    """Kurs pleyeri (app/kurs_player) + umumiy qismlar paket pleyeridan: lms.js (SCORM / xAPI adapterlari) va fonts/ (Manrope)."""
    out = PK.player_files(PLAYER_DIR)
    shared = PK.PLAYER_DIR
    if not (shared / "lms.js").is_file(): raise HTTPException(503, "Pleyerning umumiy qismi (app/paket_player/lms.js) topilmadi")
    out["lms.js"] = (shared / "lms.js").read_bytes()
    for f in sorted((shared / "fonts").glob("*")):
        if f.is_file() and not f.name.startswith("."): out[f"fonts/{f.name}"] = f.read_bytes()
    return out

_ACT = "http://adlnet.gov/expapi/activities/"

def _letters(n: int) -> list[str]: return [chr(97 + i) for i in range(n)]

def q_interaction(q: dict) -> dict:
    """Savol → xAPI/SCORM interaction ta'rifi (pleyer bilan bir xil): type, choices (asl tartibda a, b, c…), correct (naqshlar ro'yxati)."""
    if q["kind"] == "fill": return {"type": "fill-in", "choices": [], "correct": list(q["accept"])}   # har qabul qilinadigan javob — alohida naqsh (pleyer kabi)
    if q["kind"] == "truefalse": return {"type": "true-false", "choices": [], "correct": ["true" if q["answers"] and q["answers"][0]["correct"] else "false"]}
    ids = _letters(len(q["answers"]))
    return {"type": "choice", "choices": [a["text"] for a in q["answers"]], "correct": ["[,]".join(i for i, a in zip(ids, q["answers"]) if a["correct"])]}

def tincan_xml(content: dict) -> str:
    """tincan.xml: kurs (launch), har dars (module / assessment), test savollari va bilimni tekshirish bloklari (cmi.interaction)."""
    x, a = PK._xt, PK._xa
    act = content["tracking"]["activity_id"]
    def one(id_, typ, name, desc, launch=None, extra=""):
        return (f'    <activity id={a(id_)} type="{_ACT}{typ}">\n      <name lang="uz">{x(name)}</name>\n      <description lang="uz">{x(desc)}</description>\n'
                + (f'      <launch lang="uz">{x(launch)}</launch>\n' if launch else "") + extra + "    </activity>\n")
    def inter(q: dict) -> str:
        it = q_interaction(q)
        s = f"      <interactionType>{it['type']}</interactionType>\n"
        if it["correct"]: s += "      <correctResponsePatterns>\n" + "".join(f"        <correctResponsePattern>{x(p)}</correctResponsePattern>\n" for p in it["correct"]) + "      </correctResponsePatterns>\n"
        if it["choices"]:
            s += "      <choices>\n" + "".join(f'        <component>\n          <id>{i}</id>\n          <description lang="uz">{x(t)}</description>\n        </component>\n'
                                           for i, t in zip(_letters(len(it["choices"])), it["choices"])) + "      </choices>\n"
        return s
    body = one(act, "course", content["title"], _plain(content.get("description") or "")[:500] or content["title"], "index.html")
    for i, l in enumerate(content["lessons"], 1):
        lid = f"{act}/lesson/{l['id']}"
        body += one(lid, "assessment" if l["type"] == "quiz" else "module", l["title"], f"{i}-dars")
        qs = l.get("questions") if l["type"] == "quiz" else [b for b in l.get("blocks") or [] if b["type"] == "knowledge"]
        for k, q in enumerate(qs or [], 1):
            body += one(f"{lid}/q/{q['id']}", "cmi.interaction", f"{l['title']} — {k}-savol", q["question"][:500] or f"{k}-savol", extra=inter(q))
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<tincan xmlns="http://projecttincan.com/tincan.xsd">\n  <activities>\n{body}  </activities>\n</tincan>\n'

def package_entries(cid: int, mode: str) -> tuple[dict, dict]:
    if mode not in MODES: raise HTTPException(400, "Eksport turi noma'lum")
    content, files = build_content(cid, mode)
    entries = player_files()
    entries.update(files)
    entries["content.js"] = content_js(content)
    entries["content.json"] = json.dumps(content, ensure_ascii=False, indent=1).encode("utf-8")
    names = sorted(entries)
    ident = f"isft-kurs-{int(cid)}"
    sco = [{"ident": "SCO-1", "title": content["title"], "href": "index.html", "prefix": "", "mastery": content["tracking"]["mastery"]}]
    if mode == "scorm12": entries["imsmanifest.xml"] = PK.manifest_scorm12(ident, content["title"], sco, names).encode("utf-8")
    elif mode == "scorm2004": entries["imsmanifest.xml"] = PK.manifest_scorm2004(ident, content["title"], sco, names).encode("utf-8")
    elif mode == "xapi": entries["tincan.xml"] = tincan_xml(content).encode("utf-8")
    return entries, content

def build_zip_bytes(cid: int, mode: str) -> bytes:
    """Xotirada (testlar va kichik kurslar uchun) — deterministik: bir xil kurs holati → bir xil sha256."""
    return PK.zip_bytes(package_entries(cid, mode)[0])

def export_course(c: Ctx, cid: int, mode: str) -> dict:
    co = _course(c, cid, write=True)
    iss = course_issues(cid)
    if iss["errors"]: raise HTTPException(400, {"message": f"Eksportdan oldin {len(iss['errors'])} ta xatoni tuzating", "errors": iss["errors"][:30]})
    if not player_ok(): raise HTTPException(503, "Kurs pleyeri o'rnatilmagan (app/kurs_player) — administratorga murojaat qiling")
    entries, content = package_entries(cid, mode)
    d = store() / "exports" / str(int(cid))
    tmp = PK._emit(entries, d)
    try:
        val = PK.validate_zip(tmp)
        sha = PK._file_sha(tmp); size = tmp.stat().st_size
        with _lock:
            eid = _con.execute("INSERT INTO ku_exports(course_id,mode,rev,file,size,sha256,validation,ts,user_id,user_name) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (cid, mode, str(co["rev"]), "", size, sha, json.dumps(val, ensure_ascii=False), _now(), c.user["id"], c.user["full_name"])).lastrowid
            rel = Path("exports") / str(int(cid)) / f"{eid}_{mode}.zip"
            os.replace(tmp, store() / rel)
            _con.execute("UPDATE ku_exports SET file=? WHERE id=?", (str(rel), eid))
            old = db.rows(_con, "SELECT id, file FROM ku_exports WHERE course_id=? AND mode=? ORDER BY id DESC LIMIT -1 OFFSET ?", (cid, mode, KEEP_EXPORTS))
            for o in old:
                _con.execute("DELETE FROM ku_exports WHERE id=?", (o["id"],))
                if o["file"]: (store() / o["file"]).unlink(missing_ok=True)
            _log(c, cid, "eksport", f"{MODES[mode]} · {size // 1024} KB · {'tekshiruvdan o`tdi' if val['ok'] else 'XATO'}".replace("`", "'")); _con.commit()
    finally:
        tmp.unlink(missing_ok=True)
    _audit(c, "eksport", f"kurs #{cid} · {mode} · {size} bayt · {'ok' if val['ok'] else 'xato'}")
    return {"ok": val["ok"], "id": eid, "mode": mode, "size": size, "sha256": sha, "validation": val, "warnings": iss["warnings"][:50],
            "download": f"{P}/exports/{eid}/download", "filename": download_name(co, mode)}

def download_name(co: dict, mode: str) -> str:
    return f"ISFT_kurs_{PK._ascii(co['title'], 50)}_{mode}.zip"

def download_export(c: Ctx, eid: int) -> Response:
    e = db.one(_con, "SELECT * FROM ku_exports WHERE id=?", (int(eid),))
    if not e: raise HTTPException(404, "Eksport topilmadi")
    co = _course(c, e["course_id"], write=True)
    f = store() / e["file"]
    if not f.is_file(): raise HTTPException(410, "Eksport fayli saqlanmagan (eskirgan) — qayta eksport qiling")
    _audit(c, "eksport yuklab olindi", f"kurs #{co['id']} · {e['mode']}")
    return FileResponse(f, media_type="application/zip", filename=download_name(co, e["mode"]))


# --- validate_zip uchun window.KURS tekshiruvchisi (paket.CONTENT_KINDS) ----------------------------------------------
_HTML_KEYS = ("html",)
_SRC_RX = re.compile(r"^assets/[A-Za-z0-9_\-][A-Za-z0-9_\-./]{0,200}$")

def check_content(t: str, base: str, names: set, errors: list, where: str) -> dict | None:
    try: c = json.loads(t[len("window.KURS = "):-1])
    except ValueError as e:
        errors.append(f"{where}: JSON xato ({e})"); return None
    if c.get("v") != 1 or c.get("kind") != "kurs": errors.append(f"{where}: v/kind noto'g'ri")
    for k in ("id", "title", "lessons", "tracking", "labels"):
        if k not in c: errors.append(f"{where}: «{k}» yo'q")
    refs, lids, bids = [], set(), set()
    if (c.get("cover") or {}).get("src"): refs.append(c["cover"]["src"])
    if (c.get("brand") or {}).get("logo"): refs.append(c["brand"]["logo"])
    if PK.html_unsafe(c.get("description") or ""): errors.append(f"{where}: tavsifda xavfli HTML")
    if not isinstance(c.get("lessons"), list) or not c["lessons"]: errors.append(f"{where}: darslar yo'q")
    for l in c.get("lessons") or []:
        if not _UID_RX.match(str(l.get("id") or "")) or l["id"] in lids: errors.append(f"{where}: dars id noto'g'ri yoki takrorlangan {l.get('id')!r}")
        lids.add(l.get("id"))
        if l.get("type") == "quiz":
            if not l.get("questions"): errors.append(f"{where}: «{l.get('title')}» testida savol yo'q")
            items = [("question", q) for q in l.get("questions") or []]
        elif l.get("type") == "blocks":
            items = [(b.get("type"), b) for b in l.get("blocks") or []]
        else:
            errors.append(f"{where}: dars turi noma'lum {l.get('type')!r}"); continue
        for t_, b in items:
            if t_ not in BLOCKS: errors.append(f"{where}: noma'lum blok turi {t_!r}"); continue
            if b.get("id") in bids: errors.append(f"{where}: blok id takrorlangan {b.get('id')}")
            bids.add(b.get("id"))
            hs = [b.get("html")] + [x.get("html") for x in (b.get("items") or []) if isinstance(x, dict)] + [m.get("html") for m in b.get("markers") or []]
            hs += [x for x in (b.get("items") or []) if isinstance(x, str)]
            for h in hs:
                if h and (bad := PK.html_unsafe(h)): errors.append(f"{where}: {t_} blokida xavfli HTML ({bad})")
            for k in ("src", "poster"):
                if b.get(k): refs.append(b[k])
            refs += [x["src"] for x in b.get("captions") or [] if x.get("src")] + [x["src"] for x in (b.get("items") or []) if isinstance(x, dict) and x.get("src")]
            if t_ == "video" and b.get("source") == "youtube" and not PK.YT_ID.match(str(b.get("yt_id") or "")): errors.append(f"{where}: YouTube ID noto'g'ri")
            if t_ == "button" and b.get("url") and not PK.safe_href(b["url"]): errors.append(f"{where}: tugma havolasi xavfli")
            if t_ in ("knowledge", "question") and not (b.get("accept") if b.get("kind") == "fill" else any(a.get("correct") for a in b.get("answers") or [])):
                errors.append(f"{where}: savolda to'g'ri javob yo'q ({b.get('id')})")
    for r in refs:
        if not isinstance(r, str) or not _SRC_RX.match(r) or PK._bad_path(r): errors.append(f"{where}: noto'g'ri yo'l {r!r}"); continue
        if base + r not in names: errors.append(f"{where}: fayl yo'q {r}")
    return c

PK.CONTENT_KINDS["window.KURS = "] = check_content


# =============================================================================================
# Ko'rish (preview) — imzolangan yo'l, joriy (avtosaqlangan) holat, qat'iy CSP
# =============================================================================================
PV_TTL = 2 * 3600
_pv_cache: bytes | None = None

def _pv_key() -> bytes:
    global _pv_cache
    if _pv_cache is None:
        with _lock:
            _con.execute("INSERT OR IGNORE INTO ku_meta(k,v) VALUES('pv_key', ?)", (secrets.token_hex(32),)); _con.commit()
            _pv_cache = bytes.fromhex(db.one(_con, "SELECT v FROM ku_meta WHERE k='pv_key'")["v"])
    return _pv_cache

def preview_token(cid: int, uid: int, exp: int | None = None) -> str:
    msg = f"{int(cid)}.{int(uid)}.{int(exp or time.time() + PV_TTL)}"
    return msg + "." + hmac.new(_pv_key(), msg.encode(), hashlib.sha256).hexdigest()[:40]

def preview_url(c: Ctx, cid: int) -> dict:
    _course(c, cid)
    if not player_ok(): raise HTTPException(503, "Kurs pleyeri o'rnatilmagan (app/kurs_player)")
    return {"url": f"{P}/pv/{preview_token(cid, c.user['id'])}/index.html?preview=1"}

def preview_file(token: str, path: str, rng: str | None) -> Response:
    bad = HTTPException(403, "Ko'rish havolasi yaroqsiz yoki muddati o'tgan — oynani qayta oching")
    m = re.fullmatch(r"(\d{1,10})\.(\d{1,10})\.(\d{1,12})\.([0-9a-f]{40})", token or "")
    if not m: raise bad
    msg = f"{m[1]}.{m[2]}.{m[3]}"
    if not hmac.compare_digest(hmac.new(_pv_key(), msg.encode(), hashlib.sha256).hexdigest()[:40], m[4]) or int(m[3]) < time.time(): raise bad
    try: c = rbac.ctx_for(_con, int(m[2]))
    except AccessDenied: raise bad
    if c.user.get("active") == 0 or c.role.legacy or c.role.key not in AUTHORS: raise bad
    cid = int(m[1]); _course(c, cid)
    path = (path or "index.html").strip() or "index.html"
    if PK._bad_path(path) or "\x00" in path or "%" in path: raise HTTPException(400, "Yo'l noto'g'ri")
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    hd = {"Content-Security-Policy": PK.PREVIEW_CSP, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}
    ct = PK._CT.get(ext, "application/octet-stream")
    if path == "content.js":
        content, _ = build_content(cid, "none")
        return Response(content_js(content), media_type=ct, headers=hd)
    if path.startswith("assets/"):
        if path == "assets/logo.png" and (lp := PK._logo_path()): return PK.range_response(lp, ct, rng, hd)
        mm = re.fullmatch(r"assets/[a-z]+/(\d{1,10})-[A-Za-z0-9_\-]*\.([a-z0-9]{2,5})", path)
        a = db.one(_con, "SELECT * FROM ku_assets WHERE id=? AND course_id=? AND deleted=0", (int(mm[1]), cid)) if mm else None
        if not a or not _apath(a).is_file(): raise HTTPException(404, "Fayl topilmadi")
        if a["ext"] in PK._MEDIA_EXT or a["ext"] == "vtt": hd["Access-Control-Allow-Origin"] = "*"   # sandbox («null» origin) <video crossorigin> / <track>
        hd["Cache-Control"] = "private, max-age=300"
        return PK.range_response(_apath(a), PK._CT.get(a["ext"], ct), rng, hd)
    files = player_files()
    if path not in files: raise HTTPException(404, "Pleyer fayli topilmadi")
    return Response(files[path], media_type=ct, headers=hd)


# =============================================================================================
# Baholash (pleyer bilan bir xil qoida — testlar uchun ham)
# =============================================================================================
_APOS_T = str.maketrans({"ʻ": "'", "ʼ": "'", "‘": "'", "’": "'", "`": "'", "´": "'"})

def norm_answer(s: str) -> str:
    """Bo'sh joy javobini taqqoslash: katta-kichik harf, apostrof variantlari, ortiqcha bo'shliq va chetdagi tinish belgilari."""
    s = str(s or "").translate(_APOS_T).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^[\s.,;:!?\"«»()]+|[\s.,;:!?\"«»()]+$", "", s)

def grade(q: dict, resp) -> bool:
    """resp: single/multiple/truefalse — tanlangan javoblarning ASL indekslari ro'yxati; fill — matn. Hammasi yoki hech narsa."""
    if q["kind"] == "fill": return bool(q.get("accept")) and norm_answer(resp) in {norm_answer(a) for a in q["accept"]}
    want = {i for i, a in enumerate(q.get("answers") or []) if a.get("correct")}
    try: got = {int(x) for x in (resp or [])}
    except (TypeError, ValueError): return False
    if q["kind"] in ("single", "truefalse") and len(got) != 1: return False
    return bool(want) and got == want

def score_quiz(questions: list, responses: dict, pass_pct: int) -> dict:
    n = sum(1 for q in questions if grade(q, responses.get(q["id"])))
    pct = round(100 * n / len(questions)) if questions else 0
    return {"correct": n, "total": len(questions), "pct": pct, "passed": pct >= pass_pct}


# =============================================================================================
# Sifat hisoboti va bir bosishli tuzatishlar (har qanday kurs uchun; Rise importidan keyin avtomatik)
# =============================================================================================
EN_EXACT = {"continue", "quiz", "start", "start quiz", "next", "submit", "take again", "retake", "retry", "lesson", "correct", "incorrect", "flip",
            "complete the content above before moving on.", "click to flip", "start course", "resume course", "back", "results"}
EN_WORDS = {"the", "each", "to", "and", "of", "your", "you", "about", "learn", "explore", "click", "expand", "select", "drag", "card", "section", "tab",
            "this", "with", "test", "understanding", "below", "more", "main"}
EN_FIX = [(re.compile(r"^\s*continue\s*$", re.I), LABELS["continue"]), (re.compile(r"^\s*(?:start|take)\s+quiz\s*$|^\s*quiz\s*$", re.I), "Yakuniy test"),
          (re.compile(r"^\s*complete the content above before moving on\.?\s*$", re.I), LABELS["complete_hint"]),
          (re.compile(r"^\s*expand each tab\b.*$", re.I | re.S), "Har bir yorliqni ochib, mavzu bilan batafsil tanishing."),
          (re.compile(r"^\s*expand each\b.*$", re.I | re.S), "Har bir bo'limni ochib, mavzu bilan batafsil tanishing."),
          (re.compile(r"^\s*(?:click|tap) (?:on )?each card\b.*$|^\s*flip\b.*$", re.I | re.S), "Kartochkalarni bosib, orqa tomonini o'qing."),
          (re.compile(r"^\s*(?:drag|sort)\b.*$", re.I | re.S), "Elementlarni tegishli toifalarga joylashtiring."),
          (re.compile(r"^\s*test your understanding\b.*$", re.I | re.S), "Ushbu test kurs mavzulari bo'yicha bilimingizni tekshiradi."),
          (re.compile(r"^\s*(?:next|start)\s*$", re.I), LABELS["next_lesson"]), (re.compile(r"^\s*submit\s*$", re.I), LABELS["submit"])]

def is_english(t: str) -> bool:
    t = _plain(t).strip()
    if not t: return False
    if t.lower() in EN_EXACT: return True
    w = re.findall(r"[a-zA-Z]+", t.lower())
    return len(w) >= 4 and sum(x in EN_WORDS for x in w) >= 3 and not re.search(r"[ʻʼ‘’'][a-z]|o['ʻ‘]|g['ʻ‘]", t[:200])

def _fix_en(t: str) -> str:
    for rx, uz in EN_FIX:
        if rx.match(_plain(t)): return uz
    return t

def _stem(w: str) -> str: return w[:6]
_STOP = {"bilan", "uchun", "hamda", "ularning", "uning", "qaysi", "nima", "bo'lgan", "bo'ladi", "bu", "va", "esa", "ham", "kabi", "orqali", "asosiy",
         "xalqaro", "davlat", "davlatlar", "munosabatlar", "munosabatlarda", "tizimi", "tizim", "ta'sir"}

def _words(t: str) -> set:
    t = _plain(t).translate(_APOS_T).lower()
    return {_stem(w) for w in re.findall(r"[a-z'ʻ]{5,}", t) if w not in _STOP}

def _qtexts(b: dict) -> str:
    d = b["data"]
    return " ".join([d.get("question") or ""] + [a["text"] for a in d.get("answers") or [] if a.get("correct")] + list(d.get("accept") or []))

def _block_text(b: dict) -> str:
    d = b["data"]; out = []
    for k, v in d.items():
        if isinstance(v, str) and k not in ("style", "layout", "kind", "source", "side", "require", "url", "yt_id", "lang"): out.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str): out.append(x)
                elif isinstance(x, dict): out += [y for y in x.values() if isinstance(y, str)]
    return " ".join(out)

def quality_from(data: dict) -> dict:
    """data — snapshot_data() shakli. → raqamlar va muammolar ro'yxati (fix: "shuffle" | "labels" | "mr_single")."""
    ls = data.get("lessons") or []
    def pos_stats(qs):
        pos, longest, n = {}, 0, 0
        for d in qs:
            ans = d.get("answers") or []
            ci = [i for i, a in enumerate(ans) if a.get("correct")]
            if d.get("kind") not in ("single", "multiple") or len(ci) != 1 or len(ans) < 2: continue
            n += 1; i = ci[0]
            L = chr(65 + i); pos[L] = pos.get(L, 0) + 1
            lens = [len(a.get("text") or "") for a in ans]
            if lens[i] >= max(lens): longest += 1
        top = max(pos.items(), key=lambda x: x[1]) if pos else (None, 0)
        return {"total": n, "positions": dict(sorted(pos.items())), "top_pos": top[0], "top_n": top[1], "longest": longest,
                "flag_pos": n >= 4 and top[1] / n > 0.5, "flag_long": n >= 4 and longest / n > 0.5}
    kcs = [b["data"] for l in ls if l["type"] == "blocks" for b in l["blocks"] if b["type"] == "knowledge"]
    qqs = [b["data"] for l in ls if l["type"] == "quiz" for b in l["blocks"] if b["type"] == "question"]
    kc, qz = pos_stats(kcs), pos_stats(qqs)
    # rasmlar va alt matn
    imgs, no_alt, where_alt = 0, 0, []
    for n_, l in enumerate(ls, 1):
        for k, b in enumerate(l["blocks"], 1):
            d = b["data"]
            pairs = [(d.get("asset"), d.get("alt"))] if b["type"] in ("image", "image_text", "labeled_graphic") else \
                    [(x.get("asset"), x.get("alt")) for x in d.get("items") or []] if b["type"] == "gallery" else []
            for a, alt in pairs:
                if not a: continue
                imgs += 1
                if not (alt or "").strip(): no_alt += 1; where_alt.append(f"{n_}. {l['title']} · {k}-blok")
    co = data.get("course") or {}
    cover_no_alt = bool(co.get("cover_asset")) and not (co.get("cover_alt") or "").strip()
    # inglizcha yorliqlar
    en = []
    def chk(t, where):
        if t and is_english(t): en.append({"where": where, "text": _plain(t)[:120]})
    for n_, l in enumerate(ls, 1):
        chk(l["title"], f"{n_}-dars nomi")
        if l["type"] == "quiz": chk((l.get("settings") or {}).get("intro"), f"{n_}. {l['title']} · test kirish matni")
        for k, b in enumerate(l["blocks"], 1):
            d, w = b["data"], f"{n_}. {l['title']} · {k}-blok ({BLOCKS.get(b['type'], (b['type'],))[0]})"
            if b["type"] == "continue":
                if is_english(d.get("label") or "") or is_english(d.get("hint") or ""):
                    en.append({"where": w, "text": " / ".join(x for x in (d.get("label"), d.get("hint")) if x and is_english(x))[:120]})
            elif b["type"] in ("paragraph", "heading", "heading_paragraph", "button", "quote"):
                for f in ("html", "text", "heading", "label"):
                    if d.get(f): chk(d[f], w)
    # test qamrovi darslar bo'yicha (so'zlar o'xshashligi: savol + to'g'ri javob ↔ dars matni, IDF og'irlik bilan)
    bl = [(i, l) for i, l in enumerate(ls, 1) if l["type"] == "blocks"]
    lw = {i: _words(l["title"] + " " + " ".join(_block_text(b) for b in l["blocks"])) for i, l in bl}
    df = {}
    for s in lw.values():
        for w in s: df[w] = df.get(w, 0) + 1
    nL = max(1, len(lw))
    cover = {i: 0 for i, _ in bl}
    unmatched = 0
    for l in ls:
        if l["type"] != "quiz": continue
        for b in l["blocks"]:
            qw = _words(_qtexts(b))
            sc = {i: sum(math.log(1 + nL / df[w]) for w in qw & s) for i, s in lw.items()}
            best = max(sc.items(), key=lambda x: x[1]) if sc else (None, 0)
            if best[0] is None or best[1] < 2.0: unmatched += 1
            else: cover[best[0]] += 1
    covered = [i for i in cover if cover[i]]
    uncovered = [{"no": i, "title": l["title"]} for i, l in bl if not cover[i]]
    mr_single = sum(1 for l in ls for b in l["blocks"] if b["type"] in ("knowledge", "question") and b["data"].get("kind") == "multiple"
                    and sum(1 for a in b["data"].get("answers") or [] if a.get("correct")) <= 1)
    has_quiz = any(l["type"] == "quiz" for l in ls)
    quiz_shuffle_off = [l["title"] for l in ls if l["type"] == "quiz" and not (l.get("settings") or {}).get("shuffle", True)]
    def rng(xs):
        if not xs: return "—"
        xs, parts, s = sorted(xs), [], None
        for i, x in enumerate(xs):
            if s is None: s = x
            if i == len(xs) - 1 or xs[i + 1] != x + 1: parts.append(f"{s}–{x}" if x != s else str(s)); s = None
        return ", ".join(parts)
    issues = []
    add = lambda lvl, title, detail, fix=None: issues.append({"level": lvl, "title": title, "detail": detail, "fix": fix})
    for nm, st in (("Bilimni tekshirish savollari", kc), ("Yakuniy test savollari", qz)):
        if st["flag_pos"]: add("bad", f"{nm}: to'g'ri javob ko'pincha bir xil o'rinda", f"{st['top_n']}/{st['total']} ta savolda to'g'ri javob «{st['top_pos']}» o'rnida — talaba javobni taxmin qila oladi.", "shuffle")
        if st["flag_long"]: add("warn", f"{nm}: to'g'ri javob ko'pincha eng uzun variant", f"{st['longest']}/{st['total']} ta savolda to'g'ri javob eng uzun (yoki teng eng uzun) variant. Noto'g'ri variantlarni ham batafsilroq yozing — bu qo'lda tuzatiladi.")
    if quiz_shuffle_off: add("warn", "Testda javoblar aralashtirilmaydi", ", ".join(quiz_shuffle_off), "shuffle")
    if no_alt: add("bad", "Rasmlar uchun muqobil matn (alt) yo'q", f"{no_alt}/{imgs} ta rasm alt matnsiz — ko'zi ojiz talabalar ekran o'quvchisida rasmni «eshitmaydi». Har bir rasm blokida «Muqobil matn» maydonini to'ldiring.")
    if cover_no_alt: add("warn", "Muqova rasmi uchun alt matn yo'q", "Kurs sozlamalarida muqova rasmiga qisqa tavsif yozing.")
    if en: add("bad", "Inglizcha qolgan yorliqlar", f"{len(en)} ta joyda inglizcha matn (masalan: «{en[0]['text'][:60]}»).", "labels")
    if has_quiz and uncovered: add("warn", "Test hamma darslarni qamramaydi", f"Test savollari {rng(covered)}-darslarni qamraydi; savolsiz darslar: {', '.join(str(u['no']) for u in uncovered[:20])}.")
    if mr_single: add("warn", "«Bir nechta javob» savolida bitta to'g'ri javob", f"{mr_single} ta savol — «Bitta javob» turiga o'tkazish kerak.", "mr_single")
    if not issues: add("ok", "Muammo topilmadi", "Asosiy sifat tekshiruvlaridan o'tdi.")
    return {"knowledge": kc, "quiz": qz, "images": {"total": imgs, "missing_alt": no_alt, "where": where_alt[:60], "cover_missing_alt": cover_no_alt},
            "english": en[:200], "english_count": len(en),
            "coverage": {"quiz_questions": len(qqs), "lessons": [{"no": i, "title": l["title"], "questions": cover[i]} for i, l in bl],
                         "covered": rng(covered), "uncovered": uncovered, "unmatched": unmatched},
            "mr_single": mr_single, "issues": issues}

def quality(c: Ctx, cid: int) -> dict:
    _course(c, cid)
    return quality_from(snapshot_data(cid))

def _balanced(answers: list, target: int, seed: str) -> list:
    """Javoblarni qayta tartiblash: (birinchi) to'g'ri javob target o'ringa, qolganlari — deterministik aralash."""
    import random as _r
    rnd = _r.Random(hashlib.sha256(seed.encode()).hexdigest())
    ci = next((i for i, a in enumerate(answers) if a.get("correct")), 0)
    rest = [a for i, a in enumerate(answers) if i != ci]
    rnd.shuffle(rest)
    target = target % len(answers)
    return rest[:target] + [answers[ci]] + rest[target:]

def apply_fix(c: Ctx, cid: int, fix: str) -> dict:
    """Bir bosishli tuzatishlar (avval versiya saqlanadi):
       shuffle   — to'g'ri javob o'rinlari teng taqsimlanadi (aylanma, deterministik), testlarda «aralashtirish» yoqiladi;
       labels    — standart inglizcha yorliqlar o'zbekchaga ( «Continue» → «Davom etish», «Quiz» → «Yakuniy test» …);
       mr_single — bitta to'g'ri javobli «bir nechta javob» savollari «bitta javob» turiga."""
    _course(c, cid, write=True)
    if fix not in ("shuffle", "labels", "mr_single"): raise HTTPException(400, "Tuzatish turi noma'lum")
    snapshot(c, cid, "auto", {"shuffle": "Javoblarni aralashtirishdan oldin", "labels": "Yorliqlarni tarjima qilishdan oldin", "mr_single": "Savol turini o'zgartirishdan oldin"}[fix])
    changed, k = 0, 0
    with _lock:
        for l in _lessons(cid):
            st = _jload(l["settings"], {})
            new_title = l["title"]
            if fix == "labels" and is_english(l["title"]): new_title = _fix_en(l["title"])
            if fix == "labels" and l["type"] == "quiz" and is_english(st.get("intro") or ""): st["intro"] = _fix_en(st["intro"]); changed += 1
            if fix == "shuffle" and l["type"] == "quiz" and not st.get("shuffle", True): st["shuffle"] = True; changed += 1
            if new_title != l["title"]: changed += 1
            for b in db.rows(_con, "SELECT * FROM ku_blocks WHERE lesson_id=? ORDER BY pos, id", (l["id"],)):
                d = _jload(b["data"], {}); old = json.dumps(d, sort_keys=True)
                if fix == "shuffle" and b["type"] in ("knowledge", "question") and d.get("kind") == "single" and len(d.get("answers") or []) >= 2:
                    d["answers"] = _balanced(d["answers"], k, b["uid"]); k += 1
                elif fix == "labels":
                    if b["type"] == "continue":
                        if is_english(d.get("label") or ""): d["label"] = _fix_en(d["label"])
                        if is_english(d.get("hint") or ""): d["hint"] = _fix_en(d["hint"])
                    elif b["type"] in ("paragraph", "heading_paragraph") and is_english(d.get("html") or ""):
                        d["html"] = f"<p>{html.escape(_fix_en(d['html']))}</p>" if _fix_en(d["html"]) != d["html"] else d["html"]
                    elif b["type"] in ("heading", "button", "quote"):
                        for f in ("text", "label"):
                            if is_english(d.get(f) or ""): d[f] = _fix_en(d[f])
                elif fix == "mr_single" and b["type"] in ("knowledge", "question") and d.get("kind") == "multiple" and sum(1 for a in d.get("answers") or [] if a.get("correct")) <= 1:
                    d["kind"] = "single"
                if json.dumps(d, sort_keys=True) != old:
                    _con.execute("UPDATE ku_blocks SET data=? WHERE id=?", (json.dumps(clean_block(b["type"], d, _Assets(cid)), ensure_ascii=False), b["id"])); changed += 1
            _con.execute("UPDATE ku_lessons SET title=?, settings=?, rev=rev+1, updated_at=?, updated_by=? WHERE id=?",
                         (new_title, json.dumps(st, ensure_ascii=False) if l["type"] == "quiz" else l["settings"], _now(), c.user["full_name"], l["id"]))
        _bump(cid, c); _log(c, cid, "sifat tuzatishi", f"{fix} · {changed} ta o'zgarish"); _con.commit()
    _audit(c, "sifat tuzatishi", f"kurs #{cid} · {fix} · {changed}")
    return {"ok": True, "fix": fix, "changed": changed, "quality": quality_from(snapshot_data(cid)), "course": course_view(c, cid)}


# =============================================================================================
# Rise 360 importi (.zip: xAPI / SCORM / web eksport) → qoralama kurs
# =============================================================================================
_JSONP_RX = re.compile(rb'__jsonp\(\s*["\']runtime-data\.js["\']\s*,\s*["\']([A-Za-z0-9+/=_\-\s]+)["\']\s*\)')
_DESER_RX = re.compile(rb'deserialize\(\s*["\']([A-Za-z0-9+/=_\-]+)["\']\s*\)')

def zip_guard(z: zipfile.ZipFile) -> list:
    """Import zipi — ochishdan OLDIN markaziy katalog bo'yicha: fayllar soni, har birining va umumiy ochilgan hajm, siqish nisbati (bomba),
    xavfli yo'llar (mutlaq, «..», «\\», disk harfi, boshqaruv belgilari) — 400/413. Python zipfile e'lon qilingan hajmdan ortiq o'qimaydi."""
    infos = z.infolist()
    if len(infos) > IMPORT_MAX_FILES: raise HTTPException(413, f"Arxivda juda ko'p fayl ({len(infos)} > {IMPORT_MAX_FILES})")
    total = 0
    for i in infos:
        n = i.filename
        if n.startswith(("/", "\\")) or "\\" in n or re.match(r"^[A-Za-z]:", n) or ".." in n.split("/") or _CTRL.search(n) or "\x00" in n:
            raise HTTPException(400, f"Arxivda xavfli fayl yo'li bor ({n[:80]!r}) — import qilinmadi")
        total += i.file_size
        if i.file_size > IMPORT_MAX_ENTRY or total > IMPORT_MAX_TOTAL:
            raise HTTPException(413, f"Arxiv ochilganda juda katta (>{IMPORT_MAX_TOTAL // (1024 * 1024)} MB)")
        if i.file_size > IMPORT_RATIO_FROM and i.file_size > IMPORT_RATIO * max(1, i.compress_size):
            raise HTTPException(413, "Arxiv ichidagi ma'lumot g'ayritabiiy siqilgan (zip bombasi belgisi) — import qilinmadi")
    return infos

def read_rise(z: zipfile.ZipFile) -> tuple[dict, str, str]:
    """→ (Rise JSON, kontent katalogi (masalan «scormcontent/»), eksport formati)."""
    names = [i.filename for i in z.infolist() if not i.filename.endswith("/")]
    fmt = "xAPI" if any(n.endswith("tincan.xml") for n in names) else "SCORM" if any(n.endswith("imsmanifest.xml") for n in names) else "Web"
    cands = sorted([n for n in names if n.endswith("runtime-data.js")], key=lambda n: (n.count("/"), n))
    cands += sorted([n for n in names if n.endswith("index.html") and ("scormcontent" in n or "content" in n or n.count("/") <= 1)], key=lambda n: (n.count("/"), n))
    for n in cands:
        info = z.getinfo(n)
        if info.file_size > IMPORT_MAX_DATA: continue
        raw = z.read(n)
        m = _JSONP_RX.search(raw) or _DESER_RX.search(raw)
        if not m: continue
        try:
            b = re.sub(rb"\s+", b"", m[1])
            dec = base64.b64decode(b + b"=" * (-len(b) % 4), altchars=b"-_" if b"-" in b or b"_" in b else None)
            data = json.loads(dec.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("course"), dict):
            return data, (n.rsplit("/", 1)[0] + "/" if "/" in n else ""), fmt
    raise HTTPException(415, "Bu Rise 360 eksporti emas: runtime-data.js (kurs ma'lumoti) topilmadi. Rise'da «Export → xAPI / SCORM / Web» bilan olingan .zip yuklang.")

class _RiseImporter:
    def __init__(self, c: Ctx, cid: int, z: zipfile.ZipFile, base: str):
        self.c, self.cid, self.z, self.base = c, cid, z, base
        self.names = {i.filename for i in z.infolist()}
        self.cache: dict = {}
        self.img = {"imported": 0, "missing": 0, "failed": 0}
        self.media = {"imported": 0, "missing": 0}
        self.rise: dict = {}
        self.ours: dict = {}
        self.unmapped: dict = {}

    def _member(self, name: str) -> str | None:
        name = str(name or "").split("?")[0]
        if not name or name.startswith(("http:", "https:", "//")): return None
        for cand in (self.base + "assets/" + name, self.base + "assets/" + name.rsplit("/", 1)[-1], self.base + name):
            if cand in self.names: return cand
        return None

    def image(self, media) -> int | None:
        im = (media or {}).get("image") if isinstance(media, dict) else None
        if not isinstance(im, dict): return None
        keys = [im.get("crushedKey") if im.get("useCrushedKey") else None, im.get("key"), im.get("crushedKey"), im.get("src")]
        m = next((x for k in keys if k and (x := self._member(k))), None)
        if not m: self.img["missing"] += 1; return None
        if m in self.cache: return self.cache[m]
        info = self.z.getinfo(m)
        aid = None
        if info.file_size <= MAX_IMAGE:
            try:
                data, ext, meta = image_from_bytes(self.z.read(m))
                aid = _save_asset(self.c, self.cid, "image", ext, m.rsplit("/", 1)[-1], data=data, meta=meta)
                self.img["imported"] += 1
            except HTTPException:
                self.img["failed"] += 1
        else:
            self.img["failed"] += 1
        self.cache[m] = aid
        return aid

    def stream_media(self, media, kind: str) -> int | None:
        mm = (media or {}).get(kind) if isinstance(media, dict) else None
        if not isinstance(mm, dict): return None
        m = next((x for k in (mm.get("crushedKey"), mm.get("key"), mm.get("src")) if k and (x := self._member(k))), None)
        if not m: self.media["missing"] += 1; return None
        info = self.z.getinfo(m)
        if info.file_size > (PK.video_max() if kind == "video" else MAX_AUDIO): self.media["missing"] += 1; return None
        with self.z.open(m) as f: head = f.read(64)
        ext = PK.sniff_media(head)
        if not ext or (kind == "video" and ext not in PK.VIDEO_KINDS) or (kind == "audio" and ext not in PK.AUDIO_KINDS): self.media["missing"] += 1; return None
        d = store() / "tmp"; d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"imp_{secrets.token_hex(6)}.part"
        h = hashlib.sha256()
        try:
            with self.z.open(m) as src, open(tmp, "wb") as dst:
                while chunk := src.read(1024 * 1024): h.update(chunk); dst.write(chunk)
            aid = _save_asset(self.c, self.cid, kind, ext, m.rsplit("/", 1)[-1], tmp=tmp, size=info.file_size, sha=h.hexdigest())
        finally:
            tmp.unlink(missing_ok=True)
        self.media["imported"] += 1
        return aid

    def _q(self, it: dict, quiz: bool) -> tuple[str, dict] | None:
        """Rise savoli (MULTIPLE_CHOICE / MULTIPLE_RESPONSE / FILL_IN_THE_BLANK / MATCHING) → (tur, ma'lumot)."""
        t = str(it.get("type") or "").upper()
        corr = set(it.get("corrects") or []) | ({it["correct"]} if isinstance(it.get("correct"), str) else set())
        fb_ok, fb_no = _text(it.get("feedbackCorrect"), 1000), _text(it.get("feedbackIncorrect"), 1000)
        if t == "FILL_IN_THE_BLANK":
            return "fill", {"kind": "fill", "question": _text(_plain(it.get("title")), 1000), "accept": [_plain(a.get("title")) for a in it.get("answers") or [] if isinstance(a, dict)],
                            "feedback_correct": fb_ok, "feedback_wrong": fb_no}
        if t == "MATCHING":
            if quiz: return None
            return "matching", {"title": _plain(it.get("title")), "pairs": [{"left": _plain(a.get("title")), "right": _plain(a.get("matchTitle") or a.get("match"))}
                                                                          for a in it.get("answers") or [] if isinstance(a, dict)]}
        if t not in ("MULTIPLE_CHOICE", "MULTIPLE_RESPONSE"): return None
        ans = [{"text": _plain(a.get("title")), "correct": bool(a.get("correct")) or a.get("id") in corr, "feedback": _text(_plain(a.get("feedback")), 1000)}
               for a in it.get("answers") or [] if isinstance(a, dict)]
        kind = "multiple" if t == "MULTIPLE_RESPONSE" or sum(a["correct"] for a in ans) > 1 else "single"
        tf = kind == "single" and len(ans) == 2 and {norm_answer(a["text"]) for a in ans} <= {"true", "false", "to'g'ri", "noto'g'ri", "rost", "yolg'on", "ha", "yo'q"}
        return kind, {"kind": "truefalse" if tf else kind, "question": _text(_plain(it.get("title")), 1000), "answers": ans,
                      "feedback_correct": fb_ok, "feedback_wrong": fb_no}

    def block(self, it: dict) -> list[tuple[str, dict]]:
        """Rise bloki → [(bizning tur, ma'lumot)] (bo'sh — tashlanadi). Noma'lum — «import qilinmadi» izohli matn bloki."""
        t, fam, var = str(it.get("type") or ""), str(it.get("family") or ""), str(it.get("variant") or "")
        key = f"{t}/{var or fam}"
        self.rise[key] = self.rise.get(key, 0) + 1
        items = [x for x in it.get("items") or [] if isinstance(x, dict)]
        out: list = []
        if t == "text":
            for x in items:
                h, p = _line(_plain(x.get("heading")), 300), x.get("paragraph") or ""
                if fam == "impact" or "impact" in var: out.append(("quote", {"text": _plain(p) or h, "style": "impact"}))
                elif fam == "quote" or "quote" in var: out.append(("quote", {"text": _plain(p), "cite": _plain(x.get("name") or x.get("attribution")), "style": "quote"}))
                elif h and _plain(p): out.append(("heading_paragraph", {"heading": h, "html": p}))
                elif h: out.append(("heading", {"text": h, "level": 3 if "sub" in var else 2}))
                elif _plain(p): out.append(("paragraph", {"html": p}))
        elif t == "list":
            st = "numbered" if "number" in var else "checkbox" if "check" in var else "bulleted"
            out.append(("list", {"style": st, "items": [x.get("paragraph") or "" for x in items]}))
        elif t == "image":
            for x in items:
                aid = self.image(x.get("media"))
                alt = _line((((x.get("media") or {}).get("image") or {}).get("altText")) or x.get("altText") or "", 300)
                if "aside" in var or var == "text":
                    out.append(("image_text", {"asset": aid, "alt": alt, "html": x.get("paragraph") or "", "side": "right" if "right" in var else "left"}))
                else:
                    lay = "hero" if var == "hero" else "banner" if var == "banner" else "full" if "full" in var else "hero" if "overlay" in var else "centered"
                    out.append(("image", {"asset": aid, "alt": alt, "caption": _plain(x.get("caption") or (x.get("paragraph") if "overlay" in var else "")), "layout": lay}))
        elif t == "gallery":
            out.append(("gallery", {"style": "carousel" if "carousel" in var else "grid",
                                    "items": [{"asset": self.image(x.get("media")), "alt": _line(((x.get("media") or {}).get("image") or {}).get("altText") or "", 300),
                                               "caption": _plain(x.get("caption"))} for x in items]}))
        elif t == "multimedia":
            for x in items:
                md = x.get("media") or {}
                if "video" in md: out.append(("video", {"source": "file", "asset": self.stream_media(md, "video"), "title": _plain(x.get("title")), "caption": _plain(x.get("caption"))}))
                elif "audio" in md: out.append(("audio", {"asset": self.stream_media(md, "audio"), "title": _plain(x.get("title")), "transcript": _plain(x.get("description"))}))
                elif "embed" in md and (u := PK.parse_video(str((md["embed"] or {}).get("src") or (md["embed"] or {}).get("url") or ""))) and u.get("ok"):
                    out.append(("video", {"source": "youtube", "yt_id": u.get("video_id"), "yt_start": u.get("start", 0)}) if u["provider"] == "youtube"
                               else ("button", {"label": "Ochish", "url": u.get("url"), "text": _plain(x.get("title"))}))
        elif t == "interactive" and var in ("accordion", "tabs"):
            out.append((var, {"items": [{"title": _plain(x.get("title")), "html": x.get("description") or ""} for x in items]}))
        elif t == "interactive" and fam == "flashcard":
            side = lambda s: _plain((s or {}).get("description")) if isinstance(s, dict) else _plain(s)
            out.append(("flashcards", {"style": "stack" if "stack" in var else "grid", "cards": [{"front": side(x.get("front")), "back": side(x.get("back"))} for x in items]}))
        elif t == "interactive" and var == "process":
            xs = [x for x in items if not x.get("isHidden")]
            xs = [x for x in xs if x.get("type") == "intro"] + [x for x in xs if x.get("type") not in ("intro", "summary")] + [x for x in xs if x.get("type") == "summary"]
            out.append(("process", {"items": [{"title": _plain(x.get("title")), "html": x.get("description") or ""} for x in xs]}))
        elif t == "interactive" and var == "timeline":
            out.append(("timeline", {"items": [{"date": _plain(x.get("date")), "title": _plain(x.get("title")), "html": x.get("description") or ""} for x in items]}))
        elif t == "interactive" and var == "sorting":
            piles = [p for p in it.get("piles") or [] if isinstance(p, dict)]
            ix = {p.get("id"): i for i, p in enumerate(piles)}
            out.append(("sorting", {"title": "Elementlarni toifalarga ajrating", "categories": [_plain(p.get("title")) for p in piles],
                                    "items": [{"text": _plain(x.get("title")), "cat": ix.get(x.get("pileId"), 0)} for x in items]}))
        elif t == "interactive" and "labeled" in var:
            aid = self.image(it.get("media") or (items[0].get("media") if items and items[0].get("media") else None))
            out.append(("labeled_graphic", {"asset": aid, "alt": "", "markers": [{"x": _f(x.get("x"), 0, 100, 50), "y": _f(x.get("y"), 0, 100, 50),
                                                                                  "title": _plain(x.get("title")), "html": x.get("description") or ""} for x in items if "x" in x]}))
        elif t == "knowledgeCheck":
            for x in items:
                r = self._q(x, quiz=False)
                if r is None: break
                out.append((r[0] if r[0] == "matching" else "knowledge", {**r[1], "retry": True} if r[0] != "matching" else r[1]))
        elif t == "divider":
            if fam == "continue" or var == "continue":
                x = items[0] if items else {}
                out.append(("continue", {"label": _plain(x.get("title")) or LABELS["continue"], "hint": _plain(x.get("completeHint")),
                                         "require": "interactions" if str(x.get("type") or "") in ("complete", "completeBlocks", "blocks") else "none"}))
            else:
                out.append(("divider", {"style": "space" if "spac" in var else "dots" if "number" in var else "line"}))
        elif t in ("buttons", "button") or fam in ("buttons", "button"):
            for x in items:
                u = PK.safe_href(str(x.get("destination") or x.get("href") or x.get("url") or x.get("link") or ""))
                if u: out.append(("button", {"label": _plain(x.get("buttonText") or x.get("title")) or "Ochish", "url": u, "text": _plain(x.get("paragraph") or x.get("description"))}))
        if not out or (t == "knowledgeCheck" and len(out) < len(items)):
            self.unmapped[key] = self.unmapped.get(key, 0) + 1
            texts = []
            def grab(o, depth=0):
                if depth > 4: return
                if isinstance(o, dict):
                    for k_ in ("heading", "title", "paragraph", "description", "caption"):
                        if isinstance(o.get(k_), str) and _plain(o[k_]): texts.append(_plain(o[k_]))
                    for v in o.values():
                        if isinstance(v, (list, dict)): grab(v, depth + 1)
                elif isinstance(o, list):
                    for v in o: grab(v, depth + 1)
            grab(items)
            body = "".join(f"<p>{html.escape(x[:2000])}</p>" for x in texts[:20])
            out = [("paragraph", {"html": f"<p><strong>import qilinmadi: {html.escape(key)}</strong></p>{body}"})]
        for tt, _ in out: self.ours[tt] = self.ours.get(tt, 0) + 1
        return out

def import_rise(c: Ctx, path: Path, name: str = "") -> dict:
    """Rise eksporti (.zip, diskda) → yangi qoralama kurs. → {course_id, report, quality}."""
    try: z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError): raise HTTPException(415, "Fayl zip arxiv emas")
    with z:
        zip_guard(z)
        data, base, fmt = read_rise(z)
        rc = data["course"]
        theme = rc.get("theme") if isinstance(rc.get("theme"), dict) else {}
        r = create_course(c, _plain(rc.get("title")) or Path(name).stem or "Rise kursi", rc.get("description") or "", src="rise", first_lesson=False)
        cid = r["id"]
        imp = _RiseImporter(c, cid, z, base)
        n_lessons = n_quiz = n_questions = skipped_sections = 0
        A = None
        try:
            cover = imp.image((rc.get("coverImage") or {}).get("media")) or (imp.image({"image": {"key": theme.get("coverImage")}}) if theme.get("coverImage") else None)
            pos = 0
            lessons_out = []
            for rl in [x for x in rc.get("lessons") or [] if isinstance(x, dict) and not x.get("deleted")][:MAX_LESSONS]:
                lt = str(rl.get("type") or "blocks")
                if lt == "section": skipped_sections += 1; imp.unmapped["lesson/section"] = imp.unmapped.get("lesson/section", 0) + 1; continue
                if lt == "quiz":
                    qs = []
                    for it in rl.get("items") or []:
                        if not isinstance(it, dict): continue
                        key = f"quiz/{it.get('type')}"
                        imp.rise[key] = imp.rise.get(key, 0) + 1
                        rq = imp._q(it, quiz=True)
                        if rq: qs.append(("question", rq[1])); imp.ours["question"] = imp.ours.get("question", 0) + 1
                        else: imp.unmapped[key] = imp.unmapped.get(key, 0) + 1
                    st = rl.get("settings") if isinstance(rl.get("settings"), dict) else {}
                    rc_ = st.get("retryCount")
                    q = {"pass_pct": _i(st.get("passingScore"), 0, 100, 80), "attempts": 0 if rc_ in (None, -1) else _i(int(rc_) + 1, 1, 20, 0),
                         "shuffle": bool(st.get("shuffleAnswerChoices", False)), "randomize": bool(st.get("randomizeQuestionOrder", False)),
                         "reveal": "never" if st.get("revealAnswers") in ("none", False) else "pass" if st.get("revealAnswers") == "passed" else "always",
                         "intro": _plain(rl.get("description"))}
                    lessons_out.append(("quiz", _plain(rl.get("title")) or "Test", clean_quiz(q), qs)); n_quiz += 1; n_questions += len(qs)
                else:
                    bl = []
                    for it in rl.get("items") or []:
                        if isinstance(it, dict): bl += imp.block(it)
                    lessons_out.append(("blocks", _plain(rl.get("title")) or f"{len(lessons_out) + 1}-dars", {}, bl[:MAX_BLOCKS])); n_lessons += 1
            A = _Assets(cid)
            with _lock:
                for lt, title, st, bl in lessons_out:
                    pos += 1
                    lid = _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                                       (cid, _uid("l"), pos, lt, title[:200], json.dumps(st, ensure_ascii=False) if lt == "quiz" else "{}", _now(), c.user["full_name"])).lastrowid
                    for j, (bt, d) in enumerate(bl, 1):
                        _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)", (lid, _uid(), j, bt, json.dumps(clean_block(bt, d, A), ensure_ascii=False)))
                st = clean_settings({"sidebar": theme.get("navigation", True) is not False and str(theme.get("navigationType") or "SIDEBAR").upper() != "NONE",
                                     "lesson_count": theme.get("showLessonCount", True), "sequential": bool(theme.get("navigationRestricted")),
                                     "search": theme.get("allowSearch", True)})
                report = {"source": _line(name, 160), "format": fmt, "title": _plain(rc.get("title")), "lessons": n_lessons, "quiz_lessons": n_quiz,
                          "questions": n_questions, "blocks": sum(imp.ours.values()) - imp.ours.get("question", 0), "by_type": dict(sorted(imp.ours.items())),
                          "rise_types": dict(sorted(imp.rise.items())), "unmapped": dict(sorted(imp.unmapped.items())), "unmapped_total": sum(imp.unmapped.values()),
                          "images": imp.img, "media": imp.media, "sections_skipped": skipped_sections,
                          "accent_from": _line(theme.get("colorAccent"), 10), "ts": _now()}
                _con.execute("UPDATE ku_courses SET cover_asset=?, accent=?, settings=?, import_report=? WHERE id=?",
                             (cover, nearest_accent(theme.get("colorAccent") or ""), json.dumps(st), json.dumps(report, ensure_ascii=False), cid))
                _log(c, cid, "Rise importi", f"{name[:80]} · {n_lessons} dars, {n_quiz} test, {report['blocks']} blok, {report['unmapped_total']} import qilinmadi")
                _con.commit()
        except BaseException:
            with _lock:
                _con.rollback()
                _con.execute("UPDATE ku_courses SET deleted=1 WHERE id=?", (cid,)); _con.commit()
            raise
    snapshot(c, cid, "import", f"Rise importi: {name[:80]}")
    _audit(c, "Rise importi", f"kurs #{cid} · {name[:60]} · {report['lessons']} dars · {report['unmapped_total']} import qilinmadi")
    return {"ok": True, "course_id": cid, "report": report, "quality": quality_from(snapshot_data(cid))}


# =============================================================================================
# Test bank → savollar (faqat TASDIQLANGAN; o'qituvchi — o'z masofaviy kurslari)
# =============================================================================================
def _tb_ok() -> bool: return bool(db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_questions'"))

def testbank_list(c: Ctx, q: str = "", dl_course_id: int = 0, topic: int = 0) -> dict:
    if not _tb_ok(): return {"items": [], "courses": []}
    w, a = ["t.status='tasdiqlandi'", "t.deleted=0"], []
    if c.role.key == TEACH: w.append("d.teacher_id=?"); a.append(_tid(c))
    if dl_course_id: w.append("t.course_id=?"); a.append(int(dl_course_id))
    if topic: w.append("t.topic_no=?"); a.append(int(topic))
    if q.strip(): w.append("LOWER(t.stem) LIKE ?"); a.append(f"%{q.strip().lower()[:80]}%")
    rows = db.rows(_con, f"""SELECT t.id, t.course_id, t.topic_no, t.qtype, t.stem, t.options, t.correct, t.answers, d.subject FROM tb_questions t
                             JOIN dl_courses d ON d.id=t.course_id WHERE {' AND '.join(w)} ORDER BY d.subject, t.topic_no, t.id LIMIT 300""", tuple(a))
    cw, ca = ("WHERE d.teacher_id=?", (_tid(c),)) if c.role.key == TEACH else ("", ())
    courses = db.rows(_con, f"""SELECT d.id, d.subject, COUNT(t.id) n FROM dl_courses d JOIN tb_questions t ON t.course_id=d.id AND t.status='tasdiqlandi' AND t.deleted=0
                                {cw} GROUP BY d.id ORDER BY d.subject LIMIT 400""", ca)
    return {"items": [{"id": r["id"], "course_id": r["course_id"], "subject": r["subject"], "topic_no": r["topic_no"], "qtype": r["qtype"], "stem": r["stem"],
                       "options": _jload(r["options"], [])} for r in rows], "courses": courses}

def testbank_convert(c: Ctx, ids: list) -> dict:
    if not _tb_ok(): return {"questions": []}
    try: ids = [int(x) for x in ids][:100]
    except (TypeError, ValueError): raise HTTPException(400, "Savollar ro'yxati noto'g'ri")
    if not ids: return {"questions": []}
    w, a = [f"t.id IN ({','.join('?' * len(ids))})", "t.status='tasdiqlandi'", "t.deleted=0"], list(ids)
    if c.role.key == TEACH: w.append("d.teacher_id=?"); a.append(_tid(c))
    out = []
    for r in db.rows(_con, f"SELECT t.* FROM tb_questions t JOIN dl_courses d ON d.id=t.course_id WHERE {' AND '.join(w)} ORDER BY t.id", tuple(a)):
        opts, corr, ans = _jload(r["options"], []), _jload(r["correct"], []), _jload(r["answers"], [])
        if r["qtype"] == "fill": d = {"kind": "fill", "question": r["stem"], "accept": [str(x) for x in ans]}
        elif r["qtype"] == "tf":
            ok0 = PK._tf_correct(opts, corr) == 0
            d = {"kind": "truefalse", "question": r["stem"], "answers": [{"text": TF[0], "correct": ok0}, {"text": TF[1], "correct": not ok0}]}
        else:
            cs = {int(x) for x in corr if str(x).lstrip("-").isdigit()}
            d = {"kind": "multiple" if len(cs) > 1 else "single", "question": r["stem"], "answers": [{"text": str(o), "correct": i in cs} for i, o in enumerate(opts)]}
        d["feedback_correct"] = r["explanation"] or ""
        out.append({"tb_id": r["id"], "data": clean_block("question", d, _Assets(None))})
    _audit(c, "Test bankdan savollar", f"{len(out)} ta")
    return {"questions": out}


# =============================================================================================
# Namuna kurs (demo) — barcha blok turlari bitta joyda
# =============================================================================================
def _demo_png(w=960, h=540, c1=(135, 0, 55), c2=(0, 87, 91)) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), c1); dr = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h; dr.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    for i in range(6): dr.ellipse([w * i / 6 + 20, h * .55 - 40 * (i % 3), w * i / 6 + 120, h * .55 + 60 - 40 * (i % 3)], outline=(255, 255, 255), width=3)
    bio = io.BytesIO(); im.save(bio, "PNG"); return bio.getvalue()

def seed(con, force: bool = False):
    if not force and db.one(con, "SELECT 1 x FROM ku_courses WHERE src='demo'"): return
    u = db.one(con, "SELECT * FROM users WHERE role='masofaviy' ORDER BY id LIMIT 1")
    if not u: return
    global _con
    prev, _con = _con, con
    try:
        c = Ctx(u, rbac.ROLES[u["role"]])
        cid = create_course(c, "Namuna: Kurs muharriri imkoniyatlari", "<p>Bu namuna kurs «Kurs muharriri» bloklarini ko'rsatadi: matn, rasm, akkordeon, "
                            "kartochkalar, saralash, bilimni tekshirish va yakuniy test.</p>", src="demo", first_lesson=False)["id"]
        img = _save_asset(c, cid, "image", "png", "namuna.png", data=_demo_png(), meta={"w": 960, "h": 540})
        A = _Assets(cid)
        L = [("blocks", "Kirish", [
                ("heading_paragraph", {"heading": "Kursga xush kelibsiz", "html": "<p>Kurs muharriri darsni <strong>bloklardan</strong> yig'adi: har bir blok — sarlavha, matn, rasm yoki mashq.</p>"}),
                ("list", {"style": "numbered", "items": ["<p>Darslarni chap tomonda tartiblang</p>", "<p>«+» tugmasi bilan blok qo'shing</p>", "<p>Ko'rish oynasida tekshiring</p>"]}),
                ("image", {"asset": img, "alt": "Qirmizi va moviy-yashil rangli mavhum fon", "caption": "Namuna rasm", "layout": "centered"}),
                ("quote", {"text": "Yaxshi dars — qisqa, aniq va mashqli.", "style": "impact"}),
                ("accordion", {"items": [{"title": "Blok nima?", "html": "<p>Darsning bitta qismi.</p>"}, {"title": "Avtosaqlash", "html": "<p>Har o'zgarish o'zi saqlanadi.</p>"}]}),
                ("continue", {"label": "Davom etish", "require": "interactions"}),
                ("tabs", {"items": [{"title": "Matn", "html": "<p>Sarlavha, paragraf, ro'yxat, jadval.</p>"}, {"title": "Media", "html": "<p>Rasm, video, audio, fayl.</p>"}]}),
                ("knowledge", {"kind": "single", "question": "Darsga yangi blok qaysi tugma bilan qo'shiladi?", "answers": [
                    {"text": "«Eksport»", "correct": False, "feedback": "Eksport tayyor kursni yuklab olish uchun."},
                    {"text": "«+» tugmasi", "correct": True, "feedback": "To'g'ri — bloklar orasidagi «+»."},
                    {"text": "«Versiyalar»", "correct": False, "feedback": "Versiyalar — oldingi holatni tiklash uchun."}]}),
             ]),
             ("blocks", "Interaktiv mashqlar", [
                ("flashcards", {"style": "grid", "cards": [{"front": "SCORM", "back": "LMS bilan aloqa standarti"}, {"front": "xAPI", "back": "NEXTID ishlatadigan zamonaviy standart"}]}),
                ("process", {"items": [{"title": "Yarating", "html": "<p>Yangi kurs va darslar.</p>"}, {"title": "To'ldiring", "html": "<p>Bloklar qo'shing.</p>"}, {"title": "Eksport", "html": "<p>xAPI .zip — NEXTID'ga.</p>"}]}),
                ("timeline", {"items": [{"date": "1-hafta", "title": "Reja", "html": "<p>Mavzular ro'yxati.</p>"}, {"date": "2-hafta", "title": "Kontent", "html": "<p>Darslar yig'iladi.</p>"}]}),
                ("sorting", {"title": "Fayl turlarini ajrating", "categories": ["Rasm", "Video"], "items": [{"text": "PNG", "cat": 0}, {"text": "MP4", "cat": 1}, {"text": "JPG", "cat": 0}]}),
                ("matching", {"title": "Juftlarni toping", "pairs": [{"left": "SCORM 1.2", "right": "imsmanifest.xml"}, {"left": "xAPI", "right": "tincan.xml"}]}),
                ("knowledge", {"kind": "multiple", "question": "Qaysilari media bloklar?", "answers": [{"text": "Rasm", "correct": True}, {"text": "Video", "correct": True}, {"text": "Akkordeon", "correct": False}]}),
                ("knowledge", {"kind": "truefalse", "question": "Avtosaqlash ziddiyatni aniqlaydi.", "answers": [{"text": "To'g'ri", "correct": True}]}),
                ("knowledge", {"kind": "fill", "question": "NEXTID qaysi standartni ishlatadi? (4 harf)", "accept": ["xAPI"]}),
                ("table", {"header": True, "rows": [["Tur", "Fayl"], ["SCORM 1.2", "imsmanifest.xml"], ["xAPI", "tincan.xml"]]}),
                ("divider", {"style": "line"}),
                ("button", {"label": "ISFT sayti", "url": "https://isft.uz", "text": "Institut haqida batafsil"}),
                ("heading", {"text": "Media bloklar", "level": 2}),
                ("paragraph", {"html": "<p>Rasm va matn, galereya va belgili rasm — talaba bosib o'rganadi.</p>"}),
                ("image_text", {"asset": img, "alt": "Mavhum rangli fon", "html": "<p>Rasm yonidagi matn: asosiy fikrni qisqa yozing.</p>", "side": "right"}),
                ("gallery", {"style": "grid", "items": [{"asset": img, "alt": "Birinchi namuna rasm", "caption": "1-rasm"}, {"asset": img, "alt": "Ikkinchi namuna rasm", "caption": "2-rasm"}]}),
                ("labeled_graphic", {"asset": img, "alt": "Belgilar bilan rasm", "markers": [{"x": 25, "y": 40, "title": "Chap", "html": "<p>Chap qism.</p>"}, {"x": 70, "y": 60, "title": "O'ng", "html": "<p>O'ng qism.</p>"}]}),
             ]),
             ("quiz", "Yakuniy test", [
                ("question", {"kind": "single", "question": "Kurs muharriri qaysi dasturni almashtiradi?", "answers": [{"text": "Articulate Rise 360", "correct": True}, {"text": "Microsoft Word", "correct": False}, {"text": "Telegram", "correct": False}]}),
                ("question", {"kind": "truefalse", "question": "Kursni SCORM 2004 formatida ham eksport qilish mumkin.", "answers": [{"text": "To'g'ri", "correct": True}]}),
                ("question", {"kind": "multiple", "question": "Qaysilari interaktiv bloklar?", "answers": [{"text": "Kartochkalar", "correct": True}, {"text": "Saralash", "correct": True}, {"text": "Ajratgich", "correct": False}]}),
                ("question", {"kind": "fill", "question": "Talabalar uchun LMS: … (6 harf)", "accept": ["NEXTID"]}),
             ])]
        with _lock:
            for i, (lt, title, bl) in enumerate(L, 1):
                lid = con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                                  (cid, _uid("l"), i, lt, title, json.dumps(QUIZ) if lt == "quiz" else "{}", _now(), "Tizim")).lastrowid
                for j, (bt, d) in enumerate(bl, 1):
                    con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)", (lid, _uid(), j, bt, json.dumps(clean_block(bt, d, A), ensure_ascii=False)))
            con.execute("UPDATE ku_courses SET cover_asset=?, cover_alt=? WHERE id=?", (img, "Mavhum rangli fon", cid))
            con.commit()
    finally:
        _con = prev


# =============================================================================================
# API
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi")
    k = c.role.key
    out = {"role": k, "title": "Kurs muharriri", "status": STATUS,
           "caps": {"write": k in AUTHORS, "approve": k in DEPT, "import": k in AUTHORS, "summary_only": k in LEAD},
           "scope": "Masofaviy ta'lim — barcha kurslar" if k in DEPT else "O'z kurslaringiz" if k == TEACH else "Jamlangan ko'rsatkichlar", "player": player_ok()}
    if k in AUTHORS:
        out.update(blocks={t: {"label": v[0], "cat": v[1], "desc": v[2], "default": default_block(t)} for t, v in BLOCKS.items()}, categories=CATEGORIES,
                   lesson_blocks=LESSON_BLOCKS, palette=PALETTE, modes=MODES, completion=COMPLETION, reveal=REVEAL, labels=LABELS, settings=SETTINGS, quiz=QUIZ,
                   q_kinds=Q_KINDS, sub_langs=PK.SUB_LANGS, asset_kinds=ASSET_KINDS, dl_courses=dl_options(c),
                   limits={"image_mb": MAX_IMAGE // 1048576, "video_mb": PK.video_max() // 1048576, "audio_mb": MAX_AUDIO // 1048576, "file_mb": MAX_FILE // 1048576,
                           "vtt_mb": MAX_VTT // 1048576, "import_mb": import_max() // 1048576, "lessons": MAX_LESSONS, "blocks": MAX_BLOCKS, "versions": KEEP_VERSIONS})
    return out

@router.get(P + "/summary")
def api_summary(request: Request):
    c = C(request); guard(c, "jamlangan ko'rsatkichlar")
    return summary(c)

@router.get(P + "/courses")
def api_courses(request: Request, q: str = "", status: str = ""):
    c = C(request); guard(c, "kurslar ro'yxati", AUTHORS, f"{q[:30]}/{status}")
    return course_list(c, q, status)

class CourseIn(BaseModel):
    title: str = Field("", max_length=300)
    description: str = Field("", max_length=8000)
    dl_course_id: int | None = None

@router.post(P + "/courses")
def api_course_new(body: CourseIn, request: Request):
    c = C(request); guard(c, "kurs yaratish", AUTHORS, body.title[:60])
    return create_course(c, body.title, body.description, body.dl_course_id)

@router.get(P + "/courses/{cid}")
def api_course(cid: int, request: Request):
    c = C(request); guard(c, "kurs", AUTHORS, f"kurs #{cid}")
    return course_view(c, cid)

@router.post(P + "/courses/{cid}/settings")
async def api_course_settings(cid: int, request: Request):
    c = C(request); guard(c, "kurs sozlamalari", AUTHORS, f"kurs #{cid}")
    body = await _json(request, 64 * 1024)
    return update_course(c, cid, body)

@router.post(P + "/courses/{cid}/delete")
def api_course_delete(cid: int, request: Request):
    c = C(request); guard(c, "kursni o'chirish", AUTHORS, f"kurs #{cid}")
    return delete_course(c, cid)

class LessonNewIn(BaseModel):
    type: str = "blocks"
    title: str = Field("", max_length=300)
    after: int | None = None

@router.post(P + "/courses/{cid}/lessons")
def api_lesson_new(cid: int, body: LessonNewIn, request: Request):
    c = C(request); guard(c, "dars qo'shish", AUTHORS, f"kurs #{cid}")
    return add_lesson(c, cid, body.type, body.title, body.after)

class OrderIn(BaseModel):
    order: list[int]
    rev: int | None = None

@router.post(P + "/courses/{cid}/order")
def api_order(cid: int, body: OrderIn, request: Request):
    c = C(request); guard(c, "darslar tartibi", AUTHORS, f"kurs #{cid}")
    return reorder_lessons(c, cid, body.order, body.rev)

@router.get(P + "/courses/{cid}/issues")
def api_issues(cid: int, request: Request):
    c = C(request); guard(c, "tekshiruv", AUTHORS, f"kurs #{cid}")
    _course(c, cid)
    return course_issues(cid)

@router.get(P + "/lessons/{lid}")
def api_lesson(lid: int, request: Request):
    c = C(request); guard(c, "dars", AUTHORS, f"dars #{lid}")
    return lesson_view(c, lid)

async def _json(request: Request, limit: int) -> dict:
    raw = await PK._read_body(request, limit)
    try: d = json.loads(raw or b"{}")
    except ValueError: raise HTTPException(400, "JSON noto'g'ri")
    if not isinstance(d, dict): raise HTTPException(400, "JSON obyekt kerak")
    return d

@router.post(P + "/lessons/{lid}")
async def api_lesson_save(lid: int, request: Request):
    c = C(request); guard(c, "dars saqlash", AUTHORS, f"dars #{lid}")
    body = await _json(request, 8 * 1024 * 1024)
    return save_lesson(c, lid, body)

@router.post(P + "/lessons/{lid}/delete")
def api_lesson_delete(lid: int, request: Request):
    c = C(request); guard(c, "darsni o'chirish", AUTHORS, f"dars #{lid}")
    return delete_lesson(c, lid)

@router.post(P + "/lessons/{lid}/duplicate")
def api_lesson_dup(lid: int, request: Request):
    c = C(request); guard(c, "darsdan nusxa", AUTHORS, f"dars #{lid}")
    return duplicate_lesson(c, lid)

@router.get(P + "/courses/{cid}/assets")
def api_assets(cid: int, request: Request):
    c = C(request); guard(c, "fayllar", AUTHORS, f"kurs #{cid}")
    return {"items": assets_list(c, cid)}

_LIMITS = {"image": MAX_IMAGE, "vtt": MAX_VTT, "file": MAX_FILE}

@router.post(P + "/courses/{cid}/assets")
async def api_asset_upload(cid: int, request: Request, kind: str = "image", name: str = "fayl", lang: str = "uz"):
    """Bitta fayl (tana — faylning o'zi). Ruxsat va ko'lam tana o'qilishidan OLDIN; video/audio — diskka oqim bilan, tur birinchi baytlardan."""
    c = C(request); guard(c, "fayl yuklash", AUTHORS, f"kurs #{cid} · {kind} · {name[:60]}")
    if kind not in ASSET_KINDS: raise HTTPException(400, "Fayl turi noma'lum")
    _course(c, cid, write=True)
    if kind in ("video", "audio"):
        lim = PK.video_max() if kind == "video" else MAX_AUDIO
        up = await PK._stream_upload(request, lim, PK.VIDEO_KINDS if kind == "video" else PK.AUDIO_KINDS,
                                     "Video .mp4 yoki .webm bo'lishi kerak" if kind == "video" else "Audio .mp3, .m4a, .ogg yoki .wav bo'lishi kerak",
                                     tmp_dir=store() / "tmp", prefix="ku_")
        return await run_in_threadpool(upload_stream, c, cid, kind, up, name)
    raw = await PK._read_body(request, _LIMITS[kind])
    return await run_in_threadpool(upload_bytes, c, cid, kind, raw, name, lang)

@router.get(P + "/assets/{aid}")
def api_asset(aid: int, request: Request):
    c = C(request); guard(c, "fayl", AUTHORS, f"#{aid}")
    return serve_asset(c, aid, request.headers.get("range"))

@router.get(P + "/courses/{cid}/versions")
def api_versions(cid: int, request: Request):
    c = C(request); guard(c, "versiyalar", AUTHORS, f"kurs #{cid}")
    return {"items": versions(c, cid), "keep": KEEP_VERSIONS}

class NoteIn(BaseModel):
    note: str = Field("", max_length=500)

@router.post(P + "/courses/{cid}/versions")
def api_version_save(cid: int, body: NoteIn, request: Request):
    c = C(request); guard(c, "versiya saqlash", AUTHORS, f"kurs #{cid}")
    return save_version(c, cid, body.note)

@router.post(P + "/courses/{cid}/versions/{vid}/restore")
def api_version_restore(cid: int, vid: int, request: Request):
    c = C(request); guard(c, "versiyani tiklash", AUTHORS, f"kurs #{cid} · v#{vid}")
    return restore_version(c, cid, vid)

class ActIn(BaseModel):
    action: str
    note: str = Field("", max_length=500)

@router.post(P + "/courses/{cid}/action")
def api_action(cid: int, body: ActIn, request: Request):
    c = C(request)
    guard(c, {"submit": "ko'rib chiqishga yuborish", "approve": "kursni tasdiqlash", "return": "kursni qaytarish"}.get(body.action, "kurs amali"),
          AUTHORS if body.action == "submit" else DEPT, f"kurs #{cid} · {body.action}")
    return action(c, cid, body.action, body.note)

class ExportIn(BaseModel):
    mode: str = "xapi"

@router.post(P + "/courses/{cid}/export")
async def api_export(cid: int, body: ExportIn, request: Request):
    c = C(request); guard(c, "eksport", AUTHORS, f"kurs #{cid} · {body.mode}")
    return await run_in_threadpool(export_course, c, cid, body.mode)

@router.get(P + "/exports/{eid}/download")
def api_export_download(eid: int, request: Request):
    c = C(request); guard(c, "eksportni yuklab olish", AUTHORS, f"#{eid}")
    return download_export(c, eid)

@router.get(P + "/courses/{cid}/preview-url")
def api_preview_url(cid: int, request: Request):
    c = C(request); guard(c, "ko'rish", AUTHORS, f"kurs #{cid}")
    return preview_url(c, cid)

@router.get(P + "/pv/{token}/{path:path}")
def api_preview_file(token: str, path: str, request: Request):
    """Ko'rish fayllari — imzolangan yo'l orqali (sandbox iframe ichki so'rovlari cookie'siz). Media — HTTP Range bilan."""
    return preview_file(token, path, request.headers.get("range"))

@router.get(P + "/courses/{cid}/quality")
def api_quality(cid: int, request: Request):
    c = C(request); guard(c, "sifat hisoboti", AUTHORS, f"kurs #{cid}")
    return quality(c, cid)

class FixIn(BaseModel):
    fix: str

@router.post(P + "/courses/{cid}/fix")
def api_fix(cid: int, body: FixIn, request: Request):
    c = C(request); guard(c, "sifat tuzatishi", AUTHORS, f"kurs #{cid} · {body.fix}")
    return apply_fix(c, cid, body.fix)

@router.post(P + "/import/rise")
async def api_import_rise(request: Request, name: str = "rise.zip"):
    """Rise eksporti (.zip) — tana diskka oqim bilan (hajm yo'l-yo'lakay sanaladi), keyin zip markaziy katalogi tekshiriladi."""
    c = C(request); guard(c, "Rise importi", AUTHORS, name[:80])
    lim = import_max()
    up = await PK._stream_upload(request, lim, ("zip",), "Rise eksporti .zip arxiv bo'lishi kerak", sniff=lambda h: "zip" if h[:4] == b"PK\x03\x04" else None,
                                 tmp_dir=store() / "tmp", prefix="imp_", too_big=f"Arxiv hajmi {lim // 1048576} MB dan oshmasin")
    try:
        return await run_in_threadpool(import_rise, c, Path(up["path"]), name)
    finally:
        Path(up["path"]).unlink(missing_ok=True)

@router.get(P + "/testbank")
def api_testbank(request: Request, q: str = "", course_id: int = 0, topic: int = 0):
    c = C(request); guard(c, "Test bank savollari", AUTHORS, f"{course_id}/{topic}")
    return testbank_list(c, q, course_id, topic)

class TbIn(BaseModel):
    ids: list[int]

@router.post(P + "/testbank/convert")
def api_testbank_convert(body: TbIn, request: Request):
    c = C(request); guard(c, "Test bankdan qo'shish", AUTHORS, f"{len(body.ids)} ta")
    return testbank_convert(c, body.ids)
