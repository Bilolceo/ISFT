"""«Taqdimot» — o'qituvchi uchun ISFT shablonida taqdimot tayyorlash (docs/taqdimot.md).

Oqim: material (.docx / .pdf / .txt yoki matn) → reja (AI: Claude yoki AI siz — shablon) → o'qituvchi rejani tahrirlaydi
(slaydlar tartibi, matn, qo'shish/o'chirish) → .pptx (app/taqdimot_render.py) → yuklab olish. «Mening taqdimotlarim» — tarix.
Kafedra mudiri o'z kafedrasi o'qituvchilarining taqdimotlarini ko'radi va yuklab oladi.

AI: Anthropic Claude API (rasmiy `anthropic` SDK). Kalit FAQAT muhit o'zgaruvchisidan: ANTHROPIC_API_KEY (Railway → Variables).
Model: ISFT_CORE_PRES_MODEL (standart claude-opus-5-5). Claude'ga faqat yuklangan material yuboriladi — talabalar ma'lumoti emas.
Kalit bo'lmasa — AI siz: reja hujjat tuzilmasidan (sarlavhalar, xatboshilar, ro'yxatlar, rasmlar) qoidaga ko'ra tuziladi.
ISFT_CORE_PRES_FAKE=1 — testlar uchun soxta AI (tarmoqqa chiqmaydi).
Cheklovlar: fayl ≤ 20 MB, faqat .docx/.pdf/.txt (sehrli baytlar bo'yicha), kuniga ISFT_CORE_PRES_DAILY (20) ta reja generatsiyasi.
Ruxsat: oqituvchi va kafedra (kafedra — o'z kafedrasi taqdimotlarini ko'radi); boshqa rollar — 403. Har bir murojaat audit jurnalida.

DARS BILAN BOG'LASH (docs/taqdimot.md «Dars kodi va yuborish»): taqdimot fan/mavzu matni bilan emas, DARS tanlanib yaratiladi — kurs → yo'nalish → fan → dars
(faqat o'qituvchining O'Z yuklamasi: dl_courses.teacher_id; faqat L va A darslari). Dars kodi — paket.lesson_unique_code: `2_ATT_dasturiyinjiniring_L2`.
Tayyor taqdimot «Studiyaga va masofaviy bo'limga yuborish» tugmasi bilan BITTA amalda ikkala tomonga ketadi: `pres_sends` — dars kodi bo'yicha VERSIYALAR
(v1, v2 …; eski versiyalar fayli bilan tarixda qoladi), pptx (va LibreOffice bo'lsa PDF) saqlanadi, darsning paketiga (pk_assets) ham qo'yiladi,
studiya (st_plan, st_log) va masofaviy bo'lim «Mening vazifalarim» orqali xabar oladi (studio.mywork_items). Bog'lanmagan eski taqdimotlar buzilmaydi —
«Darsni belgilash» (POST /decks/{id}/lesson) bilan keyin bog'lanadi.
"""
from __future__ import annotations
import base64, hashlib, io, json, os, re, shutil, sqlite3, threading, time
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from . import clock, db, rbac
from . import taqdimot_extract as EX
from . import taqdimot_render as RD
from . import taqdimot_slides as TS
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = db.TxLock(lambda: _con)      # RLock + blokdan istisno bilan chiqsa — rollback (ochiq yozish tranzaksiyasi butun serverni qulflamasin)
RES = rbac.PRESENT
P = "/api/taqdimot"

MAX_BYTES = 20 * 1024 * 1024
MAX_CHARS = 60000                 # Claude'ga yuboriladigan material (belgi)
MAX_AI_IMAGES = 8                 # AI ko'rishi uchun yuboriladigan rasmlar
MAX_SLIDES = 40
ROLES = {"oqituvchi": "own", "kafedra": "dept"}
SLIDE_TYPES = [t for t in RD.TYPES if t != "title"]


def daily_limit() -> int:
    try:
        return max(1, int(os.getenv("ISFT_CORE_PRES_DAILY", "20")))
    except ValueError:
        return 20


def model_name() -> str:
    return os.getenv("ISFT_CORE_PRES_MODEL", "claude-opus-5-5").strip() or "claude-opus-5-5"


def engine() -> str:
    if os.getenv("ISFT_CORE_PRES_FAKE", "").strip() in ("1", "true", "yes"):
        return "fake"
    return "claude" if os.getenv("ANTHROPIC_API_KEY", "").strip() else "shablon"


ENGINE_LABEL = {"claude": "AI: Claude", "shablon": "AI siz (shablon)", "fake": "Sinov rejimi (soxta AI)"}


def status() -> dict:
    e = engine()
    return {"engine": e, "label": ENGINE_LABEL[e], "model": model_name() if e == "claude" else None}


SCHEMA = """
CREATE TABLE IF NOT EXISTS pres_decks(id INTEGER PRIMARY KEY, user_id INT, user_name TEXT, dept_id INT, title TEXT, subject TEXT, topic_no TEXT,
  audience TEXT, target INT, source_name TEXT, source_kind TEXT, source_chars INT, truncated INT DEFAULT 0, images INT DEFAULT 0,
  outline TEXT, engine TEXT, model TEXT, status TEXT DEFAULT 'reja', slides INT, built_at TEXT, created_at TEXT, updated_at TEXT, deleted INT DEFAULT 0,
  course_id INT, lkey INT, lesson_code TEXT, sent_version INT DEFAULT 0, sent_at TEXT);
CREATE INDEX IF NOT EXISTS ix_pres_user ON pres_decks(user_id, deleted);
CREATE INDEX IF NOT EXISTS ix_pres_dept ON pres_decks(dept_id, deleted);
CREATE TABLE IF NOT EXISTS pres_gen(id INTEGER PRIMARY KEY, user_id INT, deck_id INT, day TEXT, at TEXT, engine TEXT, ok INT, ms INT, err TEXT,
  in_tok INT, out_tok INT);
CREATE INDEX IF NOT EXISTS ix_pres_gen ON pres_gen(user_id, day);
CREATE TABLE IF NOT EXISTS pres_sends(id INTEGER PRIMARY KEY, deck_id INT, course_id INT, lkey INT, code TEXT, version INT, title TEXT, slides INT,
  pptx_path TEXT, pdf_path TEXT, size INT, sha256 TEXT, note TEXT, sent_by INT, sent_by_name TEXT, sent_at TEXT,
  studio_ack_at TEXT, studio_ack_by TEXT, dept_ack_at TEXT, dept_ack_by TEXT, paket_asset_id INT, paket_error TEXT,
  UNIQUE(course_id, lkey, version));
CREATE INDEX IF NOT EXISTS ix_pres_sends ON pres_sends(course_id, lkey);
"""
_SEND_COLS = (("course_code", "TEXT"), ("outline", "TEXT"), ("png_count", "INT"))        # course_code — yuborilgan paytdagi fan kodi (id qayta ishlatilsa eski versiyalar ajratiladi); outline — shu versiya reja nusxasi (JSON); png_count — slides/NN.png soni (eski versiyalarda NULL = rasm yo'q)
_DECK_COLS = (("course_id", "INT"), ("lkey", "INT"), ("lesson_code", "TEXT"), ("sent_version", "INT DEFAULT 0"), ("sent_at", "TEXT"))


def init(con):
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(pres_decks)")}       # eski baza: dars bilan bog'lash ustunlari (ma'lumot saqlanadi)
    for col, typ in _DECK_COLS:
        if col not in have:
            con.execute(f"ALTER TABLE pres_decks ADD COLUMN {col} {typ}")
    con.execute("CREATE INDEX IF NOT EXISTS ix_pres_lesson ON pres_decks(course_id, lkey)")
    have = {r[1] for r in con.execute("PRAGMA table_info(pres_sends)")}
    for col, typ in _SEND_COLS:
        if col not in have:
            con.execute(f"ALTER TABLE pres_sends ADD COLUMN {col} {typ}")
    try:        # kurs o'chirilsa uning yuborilgan taqdimotlari yetim bo'ladi (id qayta ishlatilsa ham yangi kursga o'tib ketmaydi) — darhol, so'rovni kutmasdan
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dl_courses'").fetchone():
            con.execute("CREATE TRIGGER IF NOT EXISTS trg_dlc_pres_del AFTER DELETE ON dl_courses BEGIN UPDATE pres_sends SET course_id=-id WHERE course_id=OLD.id; END")
    except Exception as e:
        print("taqdimot.init trigger:", repr(e))
    try:        # eski yozuvlar: fan kodi saqlangan kodlar jadvalidan (paket.course_code_store — PK.init dan keyin to'ladi; yo'q bo'lsa — keyingi ishga tushirishda)
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_code_store'").fetchone():
            con.execute("""UPDATE pres_sends SET course_code=(SELECT code FROM course_code_store s WHERE s.course_id=pres_sends.course_id)
                           WHERE course_code IS NULL AND course_id>0""")
    except Exception as e:
        print("taqdimot.init course_code:", repr(e))
    con.commit()


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def root() -> Path:
    return Path(db.DATA_DIR) / "taqdimot"


def ddir(did: int) -> Path:
    return root() / str(int(did))


# ---- ko'p oqimli xavfsizlik ------------------------------------------------------------------
_locks_guard = threading.Lock()
_lesson_locks: dict = {}


def _lesson_lock(cid: int, lkey: int) -> threading.Lock:
    """Dars (course_id, lkey) bo'yicha jarayon ichidagi qulf: versiya hisobi + fayl + paketga qo'yish bitta butun amal (parallel /send da taqdimot yo'qolmasin)."""
    with _locks_guard:
        return _lesson_locks.setdefault((int(cid), int(lkey)), threading.Lock())


def _rollback() -> None:
    """Yozish tranzaksiyasi ochiq qolsa (xato / HTTPException yozishdan keyin) — oqimning ulanishi qulfni ushlab turadi va butun server «database is locked» beradi."""
    try:
        _con.rollback()
    except Exception:
        pass


# =============================================================================================
# Ruxsat
# =============================================================================================
def mode(c: Ctx):
    return ROLES.get(c.role.key) if c.channel == "web" else None


def guard(c: Ctx, action: str, detail: str = "") -> str:
    m = mode(c)
    rbac.audit(_con, c, f"taqdimot: {action}", RES, m is not None, detail)
    if not m:
        raise AccessDenied(f"⛔ Taqdimot tayyorlash faqat o'qituvchi va kafedra mudiri uchun. «{c.role.title}» lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")
    return m


def _dept(c: Ctx) -> int:
    u = c.user
    d = u.get("department_id")
    if not d and u.get("teacher_id"):
        r = db.one(_con, "SELECT department_id FROM teachers WHERE id=?", (u["teacher_id"],))
        d = r and r["department_id"]
    return int(d or 0)


def _deck(c: Ctx, did: int, write=False) -> dict:
    d = db.one(_con, "SELECT * FROM pres_decks WHERE id=? AND deleted=0", (int(did),))
    if not d:
        raise HTTPException(404, "Taqdimot topilmadi")
    own = d["user_id"] == c.user["id"]
    if own:
        return d
    if not write and mode(c) == "dept" and d["dept_id"] and d["dept_id"] == _dept(c):
        return d
    rbac.audit_deny(_con, c, "taqdimot: begona taqdimot", RES, f"#{did}" + (" · tahrirlash" if write else ""))
    same_dept = mode(c) == "dept" and d["dept_id"] and d["dept_id"] == _dept(c)
    raise AccessDenied("⛔ " + ("Kafedra mudiri o'qituvchi taqdimotini faqat ko'radi va yuklab oladi — tahrirlash muallifga" if same_dept
                              else "Bu taqdimot sizniki emas") + ". So'rov audit jurnaliga yozildi.")


def _bad(msg, code=400):
    raise HTTPException(code, msg)


# =============================================================================================
# Kunlik cheklov
# =============================================================================================
def used_today(uid: int) -> int:
    return db.one(_con, "SELECT COUNT(*) n FROM pres_gen WHERE user_id=? AND day=?", (uid, clock.today().isoformat()))["n"]


def _check_limit(c: Ctx):
    if used_today(c.user["id"]) >= daily_limit():
        rbac.audit(_con, c, "taqdimot: kunlik cheklov", RES, False, f"{daily_limit()} ta")
        _bad(f"Bugungi cheklov tugadi: kuniga {daily_limit()} ta taqdimot rejasi. Ertaga qayta urinib ko'ring.", 429)


# =============================================================================================
# Reja (outline) — sxema va normallashtirish
# =============================================================================================
def _s(v, n=600):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


_AP = "['ʻʼ‘’`´]"
_TOPIC_WORD = rf"(?:mavzu|ma{_AP}?ruza|maruza|мавзу|маъруза|тема|лекция)"
_TOPIC_PFX = re.compile(rf"^\s*(?:\d{{1,3}}\s*[-–.]?\s*{_TOPIC_WORD}|{_TOPIC_WORD}\s*(?:№|#)?\s*\d{{1,3}})\s*[:.\-–—]?\s*", re.I)
_TOPIC_NO = re.compile(rf"^\s*(?:(\d{{1,3}})\s*[-–.]?\s*{_TOPIC_WORD}|{_TOPIC_WORD}\s*(?:№|#)?\s*(\d{{1,3}}))(?!\d)", re.I)


def strip_topic_prefix(t) -> str:
    """«7-MAVZU: Differensial tenglamalar» → «Differensial tenglamalar» (titul slaydda raqam o'zi qo'shiladi — mavzu nomi ikki marta raqamlanmasin).
    Faqat «7-MAVZU» bo'lsa — bo'sh satr (nom emas)."""
    t = _s(t, 300)
    m = _TOPIC_PFX.match(t)
    rest = t[m.end():].strip(" .:;–—-") if m else t
    return t if m and rest.lower() == "nomsiz" else rest        # «7-mavzu — nomsiz» — nomsiz dars sarlavhasi, o'zgarmaydi


def doc_topic_no(blocks) -> int | None:
    """Hujjat boshidagi «N-MAVZU» (yoki «Mavzu N») sarlavhasidan mavzu raqami: birinchi 14 ta bo'sh bo'lmagan blok ichida; topilmasa — None."""
    n = 0
    for b in blocks or []:
        if b.get("k") not in ("h", "p"):
            continue
        t = (b.get("t") or "").strip()
        if not t:
            continue
        m = _TOPIC_NO.match(t.replace("**", ""))
        if m:
            return int(m.group(1) or m.group(2))
        n += 1
        if n >= 14:
            break
    return None


def _sl(v, n=40, m=400):
    return [x for x in (_s(i, m) for i in (v or [])[:n] if not isinstance(i, (dict, list))) if x]


def normalize(o: dict, n_images: int) -> dict:
    o = o if isinstance(o, dict) else {}
    out = {"subject": _s(o.get("subject"), 120), "topic_no": _s(o.get("topic_no"), 20), "title": strip_topic_prefix(_s(o.get("title"), 200)) or "Mavzu",
           "subtitle": _s(o.get("subtitle"), 200), "slides": []}
    for s in (o.get("slides") or [])[:MAX_SLIDES * 2]:
        if not isinstance(s, dict):
            continue
        t = s.get("type") if s.get("type") in RD.TYPES else "theory"
        if t == "title":
            continue
        img = s.get("image")
        try:
            img = int(img or 0)
        except (TypeError, ValueError):
            img = 0
        x = {"type": t, "title": _s(s.get("title"), 140), "text": _s(s.get("text"), 1500), "highlight": _s(s.get("highlight"), 300),
             "subheading": _s(s.get("subheading"), 140), "bullets": _sl(s.get("bullets"), 14, 400),
             "columns": [{"title": _s(cl.get("title"), 80), "bullets": _sl(cl.get("bullets"), 8, 300)} for cl in (s.get("columns") or [])[:2] if isinstance(cl, dict)],
             "steps": [{"title": _s(st.get("title"), 80), "text": _s(st.get("text"), 400)} for st in (s.get("steps") or [])[:10] if isinstance(st, dict)],
             "answer": _s(s.get("answer"), 200), "check": _sl(s.get("check"), 4, 200), "note": _s(s.get("note"), 400),
             "cards": [{"title": _s(cd.get("title"), 80), "text": _s(cd.get("text"), 500)} for cd in (s.get("cards") or [])[:9] if isinstance(cd, dict)],
             "image": img if 1 <= img <= n_images else 0, "caption": _s(s.get("caption"), 200), "notes": _s(s.get("notes"), 3000)}
        if t == "image" and not x["image"]:     # rasm yo'q — izoh matnga aylanadi
            x["type"] = "theory"
            if not x["text"]: x["text"] = x["caption"]
        has = any(x[k] for k in ("text", "highlight", "bullets", "columns", "steps", "answer", "cards", "image"))
        if has or t == "plan":
            out["slides"].append(x)
        if len(out["slides"]) >= MAX_SLIDES:
            break
    if not any(s["type"] not in ("plan",) for s in out["slides"]):
        raise ValueError("Rejada slayd yo'q")
    return out


SLIDE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["type", "title", "text", "highlight", "subheading", "bullets", "columns", "steps", "answer", "check", "note", "cards", "image", "caption", "notes"],
    "properties": {
        "type": {"type": "string", "enum": SLIDE_TYPES},
        "title": {"type": "string"}, "text": {"type": "string"}, "highlight": {"type": "string"}, "subheading": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "columns": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "bullets"],
                                               "properties": {"title": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}}}}},
        "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "text"],
                                             "properties": {"title": {"type": "string"}, "text": {"type": "string"}}}},
        "answer": {"type": "string"}, "check": {"type": "array", "items": {"type": "string"}}, "note": {"type": "string"},
        "cards": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["title", "text"],
                                             "properties": {"title": {"type": "string"}, "text": {"type": "string"}}}},
        "image": {"type": "integer"}, "caption": {"type": "string"}, "notes": {"type": "string"},
    },
}
OUTLINE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["subject", "topic_no", "title", "subtitle", "slides"],
    "properties": {"subject": {"type": "string"}, "topic_no": {"type": "string"}, "title": {"type": "string"}, "subtitle": {"type": "string"},
                   "slides": {"type": "array", "items": SLIDE_SCHEMA}},
}

SYSTEM = """You prepare university lecture slide decks for ISFT (International School of Finance Technology and Science, Tashkent).
The teacher uploads lecture material; you turn it into a slide plan that a renderer will draw in the official ISFT template.
Write every slide text in Uzbek (Latin script, o‘ and g‘ with the ‘ sign), academically precise and concise. Keep terminology from the material.
Use only facts from the material; you may restructure, condense and add didactic elements (questions, tasks, summary) derived from it.

Plan structure (slide count follows the content — never pad, never cram):
1. One "plan" slide: 5–8 short items (the lecture outline).
2. Theory: "definition" (key definition in `text`, optionally a key formula/statement in `highlight`, then `subheading` + `bullets`),
   "theory" (short `text` + `bullets`, optional `highlight`), "two_column" (comparison: `columns` with 2 items), "steps" (algorithm/procedure: `steps`).
   One idea per slide. Vary layouts.
3. Worked examples (if the material has problems/cases): one "example" slide each — `text` is the condition, `steps` 3–5 solution steps,
   `answer` the result, `check` 2–4 verification points, optional `note` (typical mistake / remark).
4. Images: the material contains markers [RASM n]. Put a relevant image on an "image" slide (`image` = n, `caption`, optional 2–4 `bullets`).
   Use only image numbers that exist. Do not invent images. image = 0 when there is none.
5. "tasks": independent work, `cards` (title + text), at most 3 cards per slide.
6. "questions": 5–8 control questions in `bullets`.
7. "summary": 4–6 `cards` (title + one sentence).
8. "references": numbered literature in `bullets` (author in **bold**), only if the material lists sources.
Formatting inside strings: **bold** for key terms; formulas in $...$ with ^{...} for superscripts and _{...} for subscripts (e.g. $x^{2} + y_{1}$).
Limits per slide: bullets ≤ 6 (each ≤ 160 characters), text ≤ 450 characters, steps ≤ 5. Split long topics into more slides instead.
`notes`: 2–4 sentences of speaker notes for the teacher. Unused fields: empty string / empty array / 0.
Top-level: subject (course name), topic_no (lecture number if known, else ""), title (topic), subtitle (one line)."""


def _material_prompt(text: str, truncated: bool, images: list, meta: dict) -> str:
    lines = [f"Fan (kurs): {meta.get('subject') or '—'}", f"Mavzu raqami: {meta.get('topic_no') or '—'}", f"Mavzu nomi (o'qituvchi kiritgan): {meta.get('title') or '—'}"]
    if meta.get("target"):
        lines.append(f"Taxminiy slaydlar soni: {meta['target']} (kontentga qarab ±3)")
    if meta.get("audience"):
        lines.append(f"O'qituvchi izohi / auditoriya: {meta['audience']}")
    if images:
        lines.append("Materialdagi rasmlar: " + "; ".join(f"[RASM {i['n']}] {i.get('ctx') or ''}".strip() for i in images))
    if truncated:
        lines.append("Eslatma: material juda uzun, faqat birinchi qismi berilgan.")
    return "\n".join(lines) + "\n\n<material>\n" + text + "\n</material>\n\nReturn the slide plan."


def _img_blocks(images: list, img_dir: Path) -> list:
    from PIL import Image
    out = []
    for im in images[:MAX_AI_IMAGES]:
        p = img_dir / im["file"]
        try:
            pic = Image.open(p)
            pic.thumbnail((768, 768))
            if pic.mode not in ("RGB", "L"):
                pic = pic.convert("RGB")
            buf = io.BytesIO(); pic.save(buf, "JPEG", quality=80)
            out.append({"type": "text", "text": f"[RASM {im['n']}]"})
            out.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(buf.getvalue()).decode()}})
        except Exception:
            continue
    return out


from .claude_client import AIError   # noqa: E402  (umumiy mijoz — app/claude_client.py)


def claude_outline(text: str, truncated: bool, images: list, img_dir: Path, meta: dict) -> tuple[dict, dict]:
    from . import claude_client as CC
    content = _img_blocks(images, img_dir) + [{"type": "text", "text": _material_prompt(text, truncated, images, meta)}]
    data, info = CC.call_json(model=model_name(), system=SYSTEM, content=content, schema=OUTLINE_SCHEMA, max_tokens=32000, what="reja")
    return data, info


# =============================================================================================
# AI siz: hujjat tuzilmasidan reja
# =============================================================================================
SPECIAL = [(re.compile(r"adabiyot|manba|references|литератур", re.I), "references"),
           (re.compile(r"nazorat savol|savollar|questions|вопрос", re.I), "questions"),
           (re.compile(r"topshiriq|mashq|mustaqil|vazifa|задан", re.I), "tasks"),
           (re.compile(r"xulosa|conclusion|заключ|вывод", re.I), "summary")]


CAP_RX = re.compile(r"^\s*(\d{1,3}\s*[-–]?\s*(rasm|chizma|jadval|diagramma)|(rasm|chizma|figure|fig\.|рис)\s*\.?\s*\d)", re.I)


def _sentences(t: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-ZА-ЯЎҚҒҲO‘G‘0-9«\"(])", t) if x.strip()]


def _short(t: str, n=220) -> str:
    t = t.strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def rule_outline(ex: dict, meta: dict) -> dict:
    blocks = ex["blocks"]
    images = {i["n"]: i for i in ex["images"]}
    sections, cur = [], {"h": "", "items": []}
    for b in blocks:
        if b["k"] == "h" and (b.get("lvl") or 1) <= 2:
            if cur["h"] or cur["items"]:
                sections.append(cur)
            cur = {"h": b["t"], "items": []}
        else:
            cur["items"].append(b)
    if cur["h"] or cur["items"]:
        sections.append(cur)
    title = meta.get("title") or ""
    if not title and sections and sections[0]["h"] and len(sections[0]["h"]) <= 140:
        cand = strip_topic_prefix(sections[0]["h"])       # «7-MAVZU: Nom» → «Nom»; faqat «7-MAVZU» — nom emas
        if cand:
            title = cand
            if not sections[0]["items"]:
                sections = sections[1:]
    title = title or meta.get("title_fallback") or "Mavzu"
    slides = []
    for sec in sections:
        h = _short(sec["h"] or "Asosiy tushunchalar", 120)
        kind = next((k for rx, k in SPECIAL if rx.search(sec["h"] or "")), None)
        caps, skip = {}, set()
        for j, it in enumerate(sec["items"]):          # rasm ostidagi «1-rasm. …» — rasm izohi, matn emas
            nxt = sec["items"][j + 1] if j + 1 < len(sec["items"]) else None
            if it["k"] == "img" and nxt and nxt["k"] == "p" and CAP_RX.match(nxt["t"]) and len(nxt["t"]) <= 200:
                caps[it["img"]] = nxt["t"]; skip.add(j + 1)
        texts = [i for j, i in enumerate(sec["items"]) if i["k"] in ("p", "li") and j not in skip]
        imgs = [i["img"] for i in sec["items"] if i["k"] == "img"]
        if kind == "references":
            slides.append({"type": "references", "title": "Foydalanilgan adabiyotlar", "bullets": [_short(i["t"], 300) for i in texts][:14]})
            continue
        if kind == "questions":
            qs = [_short(i["t"], 200) for i in texts if i["t"]]
            if qs: slides.append({"type": "questions", "title": "Nazorat savollari", "bullets": qs[:14]})
            continue
        if kind == "tasks":
            cards = [{"title": f"{n + 1}-topshiriq", "text": _short(i["t"], 400)} for n, i in enumerate(texts)]
            if cards: slides.append({"type": "tasks", "title": h, "cards": cards[:9]})
            continue
        if kind == "summary":
            cards = []
            for i in texts:
                words = i["t"].split()
                cards.append({"title": " ".join(words[:3]).rstrip(",.:;"), "text": _short(i["t"], 200)})
            if cards: slides.append({"type": "summary", "title": "Xulosa", "cards": cards[:6]})
            continue
        paras = [i["t"] for i in texts if i["k"] == "p"]
        lis = [_short(i["t"]) for i in texts if i["k"] == "li"]
        intro = _short(paras[0], 450) if paras else ""
        bullets = list(lis)
        for p in paras[1:]:
            bullets += [_short(s) for s in _sentences(p)]
        if paras and len(paras[0]) > 450:
            bullets = [_short(s) for s in _sentences(paras[0][len(intro.rstrip("…")):])] + bullets
        bullets = [b for b in bullets if len(b) > 3]
        chunk = 6
        parts = [bullets[i:i + chunk] for i in range(0, len(bullets), chunk)] or [[]]
        for k, part in enumerate(parts):
            if not part and not (intro and k == 0):
                continue
            slides.append({"type": "theory", "title": h + (f" ({k + 1})" if len(parts) > 1 else ""), "text": intro if k == 0 else "", "bullets": part})
        for n in imgs:
            if n in images:
                slides.append({"type": "image", "title": h, "image": n, "caption": _short(caps.get(n) or "", 160)})
    plan = [s["title"] for s in slides if s["type"] in ("theory", "definition") and not re.search(r"\(\d+\)$", s["title"])]
    plan = list(dict.fromkeys(plan))[:7] or [s["title"] for s in slides][:7]
    return {"subject": meta.get("subject") or "", "topic_no": meta.get("topic_no") or "", "title": title, "subtitle": "",
            "slides": [{"type": "plan", "title": "Reja", "bullets": plan}] + slides}


def fake_outline(ex: dict, meta: dict) -> dict:
    """Testlar uchun soxta AI: barcha slayd turlari, kontent slaydlari soni = target (bo'lsa)."""
    paras = [b["t"] for b in ex["blocks"] if b["k"] in ("p", "li")] or ["Material"]
    target = int(meta.get("target") or 10)
    imgs = [i["n"] for i in ex["images"]]
    pool = []
    pool.append({"type": "definition", "title": "Asosiy ta'rif", "text": "**Ta'rif.** " + _short(paras[0], 300), "highlight": "$E = mc^{2}$",
                 "subheading": "Muhim jihatlar", "bullets": [_short(p, 120) for p in paras[1:4]] or ["Birinchi jihat"], "notes": "Ta'rifni misol bilan tushuntiring."})
    pool.append({"type": "two_column", "title": "Taqqoslash", "columns": [{"title": "Birinchi", "bullets": ["A xususiyat", "B xususiyat"]},
                                                                           {"title": "Ikkinchi", "bullets": ["C xususiyat", "D xususiyat"]}]})
    pool.append({"type": "steps", "title": "Algoritm", "steps": [{"title": "1-qadam:", "text": "Shartni yozamiz"}, {"title": "2-qadam:", "text": "Hisoblaymiz"}]})
    pool.append({"type": "example", "title": "1-misol", "text": "$x^{2} = 4$ tenglamani yeching.", "steps": [{"title": "Ildiz:", "text": "x = ±2"}],
                 "answer": "$x = ±2$", "check": ["$2^{2} = 4$"], "note": "Manfiy ildizni unutmang."})
    for n in imgs:
        pool.append({"type": "image", "title": f"{n}-rasm", "image": n, "caption": f"{n}-rasm", "bullets": ["Rasm izohi"]})
    pool.append({"type": "tasks", "title": "Mustaqil topshiriqlar", "cards": [{"title": "1-topshiriq", "text": "Mashqni bajaring."}]})
    pool.append({"type": "questions", "title": "Nazorat savollari", "bullets": ["Birinchi savol?", "Ikkinchi savol?", "Uchinchi savol?"]})
    pool.append({"type": "summary", "title": "Xulosa", "cards": [{"title": "Asosiy g'oya", "text": "Qisqa xulosa."}, {"title": "Natija", "text": "Ikkinchi xulosa."}]})
    pool.append({"type": "references", "title": "Foydalanilgan adabiyotlar", "bullets": ["**Muallif A.** Darslik. — T.: 2024."]})
    i = 0
    while len(pool) < target:      # kontent slaydlari soni ≈ target (asosiy turlar doim qoladi)
        i += 1
        pool.insert(1, {"type": "theory", "title": f"Nazariya ({i})", "text": _short(paras[i % len(paras)], 300), "bullets": [_short(p, 100) for p in paras[:3]]})
    return {"subject": meta.get("subject") or "Sinov fani", "topic_no": meta.get("topic_no") or "1", "title": meta.get("title") or "Sinov mavzusi",
            "subtitle": "Soxta AI rejasi", "slides": [{"type": "plan", "title": "Reja", "bullets": [s["title"] for s in pool[:7]]}] + pool}


# =============================================================================================
# Generatsiya
# =============================================================================================
def _ex_load(did: int) -> dict:
    p = ddir(did) / "material.json"
    return json.loads(p.read_text(encoding="utf-8"))


def generate(c: Ctx, did: int, meta: dict) -> dict:
    """Material → reja (AI / AI siz). Kunlik cheklov hisoblanadi (muvaffaqiyatsiz AI urinish ham)."""
    ex = _ex_load(did)
    eng = engine()
    t0 = time.time()
    info = {"in": 0, "out": 0, "model": None}
    err = None
    try:
        if eng == "claude":
            text, trunc = EX.as_text(ex["blocks"], MAX_CHARS)
            raw, info = claude_outline(text, trunc, ex["images"], ddir(did) / "img", meta)
        elif eng == "fake":
            raw = fake_outline(ex, meta)
        else:
            raw = rule_outline(ex, meta)
        outline = normalize(raw, len(ex["images"]))
        for k in ("subject", "topic_no", "title"):   # o'qituvchi kiritgan qiymat ustun
            if meta.get(k): outline[k] = (strip_topic_prefix(meta[k]) or outline[k]) if k == "title" else _s(meta[k], 200)
        if not meta.get("title"):                    # «Mavzu nomi» bo'sh: matn sarlavhasi → dars nomi → «N-mavzu — nomsiz»; hech qachon fayl nomi («matn»)
            if outline["title"].strip().lower() in ("", "mavzu", "sinov mavzusi", "matn", (meta.get("source_stem") or "\0").lower()):
                outline["title"] = meta.get("title_fallback") or "Nomsiz taqdimot"
    except AIError as e:
        err = str(e)
    except ValueError as e:
        err = f"Reja tuzilmadi: {e}"
    ms = int((time.time() - t0) * 1000)
    try:
        with _lock:
            _con.execute("INSERT INTO pres_gen(user_id,deck_id,day,at,engine,ok,ms,err,in_tok,out_tok) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (c.user["id"], did, clock.today().isoformat(), clock.now_iso(), eng, 0 if err else 1, ms, err, info.get("in"), info.get("out")))
            if not err:
                _con.execute("UPDATE pres_decks SET outline=?, engine=?, model=?, status='reja', title=?, subject=?, topic_no=?, updated_at=? WHERE id=?",
                             (json.dumps(outline, ensure_ascii=False), eng, info.get("model"), outline["title"], outline["subject"], outline["topic_no"],
                              clock.now_iso(), did))
            _con.commit()
    except BaseException:
        _rollback(); raise
    rbac.audit(_con, c, "taqdimot: reja tuzildi" if not err else "taqdimot: reja xatosi", RES, True,
               f"#{did} · {ENGINE_LABEL[eng]} · {ms} ms" + (f" · {err[:120]}" if err else ""))
    if err:
        _bad(err, 502 if eng == "claude" else 400)
    return view(c, did)


def _drop_deck(did: int) -> None:
    """Yaratish yarim yo'lda to'xtadi: qator «o'chirilgan», papka tozalanadi (tranzaksiya ochiq qolmaydi)."""
    shutil.rmtree(ddir(did), ignore_errors=True)
    try:
        with _lock:
            _con.execute("UPDATE pres_decks SET deleted=1 WHERE id=?", (did,)); _con.commit()
    except BaseException:
        _rollback()


def create(c: Ctx, raw: bytes | None, text: str | None, name: str, meta: dict) -> dict:
    meta = _bind_meta(c, meta)               # dars tanlangan bo'lsa: fan/mavzu raqami darsdan olinadi (qo'lda yozilmaydi), ko'lam tekshiriladi
    if raw is not None:
        if not raw:
            _bad("Fayl bo'sh")
        if len(raw) > MAX_BYTES:
            _bad("Fayl hajmi 20 MB dan oshmasin", 413)
        try:
            kind = EX.sniff(raw)
        except EX.BadFile as e:
            rbac.audit(_con, c, "taqdimot: fayl rad etildi", RES, False, f"{name[:60]} · {e}")
            _bad(str(e), 415)
    else:
        text = (text or "").strip()
        if len(text) < 40:
            _bad("Matn juda qisqa — kamida bir necha gap yozing")
        if len(text.encode("utf-8")) > MAX_BYTES:
            _bad("Matn hajmi 20 MB dan oshmasin", 413)
        raw, kind, name = text.encode("utf-8"), "txt", name or "matn.txt"
    _check_limit(c)
    now = clock.now_iso()
    title0 = strip_topic_prefix(meta.get("title") or "") or meta.get("title_fallback") or "Nomsiz taqdimot"      # fayl nomi («matn») sarlavha bo'lmaydi
    try:
        with _lock:
            did = _con.execute("""INSERT INTO pres_decks(user_id,user_name,dept_id,title,subject,topic_no,audience,target,source_name,source_kind,
                                  status,created_at,updated_at,course_id,lkey,lesson_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (c.user["id"], c.user["full_name"], _dept(c), title0, meta.get("subject"),
                                meta.get("topic_no"), meta.get("audience"), meta.get("target"), name[:160], kind, "yangi", now, now,
                                meta.get("course_id"), meta.get("lkey"), meta.get("lesson_code"))).lastrowid
            _con.commit()
    except BaseException:
        _rollback(); raise
    d = ddir(did)
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"manba.{kind}").write_bytes(raw)
        ex = EX.extract(raw, kind, d / "img")
        (d / "material.json").write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
        _, trunc = EX.as_text(ex["blocks"], MAX_CHARS)
        with _lock:
            _con.execute("UPDATE pres_decks SET source_chars=?, truncated=?, images=? WHERE id=?", (ex["chars"], int(trunc), len(ex["images"]), did))
            _con.commit()
    except EX.BadFile as e:
        _rollback(); _drop_deck(did)
        rbac.audit(_con, c, "taqdimot: material o'qilmadi", RES, False, f"{name[:60]} · {e}")
        _bad(str(e), 415)
    except BaseException:
        _rollback(); _drop_deck(did); raise
    rbac.audit(_con, c, "taqdimot: material yuklandi", RES, True, f"#{did} · {name[:60]} · {kind} · {ex['chars']} belgi · {len(ex['images'])} rasm")
    meta = {**meta, "source_stem": Path(name).stem}
    out = generate(c, did, meta)
    if meta.get("course_id"):                # shu darsga ikkinchi taqdimot — bloklanmaydi, UI ogohlantiradi
        out["existing"] = [{"id": r["id"], "title": r["title"] or ""} for r in db.rows(
            _con, "SELECT id, title FROM pres_decks WHERE user_id=? AND course_id=? AND lkey=? AND deleted=0 AND id!=? ORDER BY id DESC LIMIT 10",
            (c.user["id"], meta["course_id"], meta["lkey"], did))]
    else:
        out["existing"] = []
    return out


def _scope_ok(c: Ctx, d: dict) -> bool:
    """Chaqiruvchi shu taqdimot darsining HOZIRGI kursiga egami (o'qituvchi — hozirgi o'qituvchi; kafedra — hozirgi kafedra)? Kurs boshqa o'qituvchiga o'tsa —
    eski o'qituvchi yangisining versiyalarini, izohini va ismini ko'rmaydi va yuklab ololmaydi."""
    if not d.get("course_id"):
        return False
    co = db.one(_con, "SELECT teacher_id, department_id FROM dl_courses WHERE id=?", (d["course_id"],))
    if not co:
        return False
    m = mode(c)
    if m == "own":
        return bool(_tid(c)) and co["teacher_id"] == _tid(c)
    if m == "dept":
        return bool(co["department_id"]) and co["department_id"] == _dept(c)
    return False


def _lesson_sent(cid, lkey) -> dict:
    """DARS bo'yicha oxirgi yuborilgan versiya (qaysi taqdimot orqali yuborilganidan qat'i nazar) — versiya raqami dars bo'yicha hisoblanadi."""
    r = db.one(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? ORDER BY version DESC LIMIT 1", (int(cid or 0), int(lkey or 0))) if cid and lkey else None
    if not r:
        return {"lesson_sent_version": None, "lesson_sent_deck_id": None, "lesson_sent_deck_title": None, "lesson_sent_at": None}
    t = db.one(_con, "SELECT title FROM pres_decks WHERE id=? AND deleted=0", (r["deck_id"],))
    return {"lesson_sent_version": r["version"], "lesson_sent_deck_id": r["deck_id"], "lesson_sent_deck_title": (t or {}).get("title") or r["title"] or "",
            "lesson_sent_at": r["sent_at"]}


def _decks_of(uid: int, cid, lkey) -> list[dict]:
    if not cid or not lkey:
        return []
    return [{"id": r["id"], "title": r["title"] or ""} for r in db.rows(
        _con, "SELECT id, title FROM pres_decks WHERE user_id=? AND course_id=? AND lkey=? AND deleted=0 ORDER BY id DESC LIMIT 20", (int(uid), int(cid), int(lkey)))]


def _pptx_info(d: dict) -> dict | None:
    f = ddir(d["id"]) / "taqdimot.pptx"
    if not f.is_file():
        return None
    return {"filename": file_name(d), "size": f.stat().st_size, "built_at": d.get("built_at")}


def _last_send_info(r: dict) -> dict:
    return {"version": r["version"], "at": r["sent_at"], "size": r["size"], "filename": f"{r['code']}_taqdimot_v{r['version']}.pptx",
            "sha256_short": (r["sha256"] or "")[:8], "deck_id": r["deck_id"]}


def view(c: Ctx, did: int) -> dict:
    d = _deck(c, did)
    out = {k: d[k] for k in ("id", "title", "subject", "topic_no", "audience", "target", "source_name", "source_kind", "source_chars", "truncated",
                             "images", "engine", "model", "status", "slides", "built_at", "created_at", "updated_at", "user_name")}
    out["engine_label"] = ENGINE_LABEL.get(d["engine"] or "", "—")
    out["outline"] = json.loads(d["outline"]) if d["outline"] else None
    scope = _scope_ok(c, d)
    out["lesson"] = lesson_view(d, scope)
    if out["lesson"] is not None and scope:
        out["lesson"].update(_lesson_sent(d["course_id"], d["lkey"]))
        out["lesson"]["decks"] = _decks_of(d["user_id"], d["course_id"], d["lkey"])
    out["sent_version"], out["sent_at"] = int(d.get("sent_version") or 0), d.get("sent_at")
    out["sends"] = deck_sends(c, d, scope) if out["lesson"] else []
    out["mine"] = d["user_id"] == c.user["id"]
    out["can_edit"] = out["mine"]
    out["pptx"] = _pptx_info(d)
    mine_last = db.one(_con, "SELECT * FROM pres_sends WHERE deck_id=? ORDER BY version DESC LIMIT 1", (d["id"],)) if (scope or out["mine"]) else None
    lesson_last = db.one(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? ORDER BY version DESC LIMIT 1", (d["course_id"], d["lkey"])) \
        if scope and d.get("course_id") and d.get("lkey") else None
    out["last_send"] = _last_send_info(lesson_last) if lesson_last else (_last_send_info(mine_last) if mine_last else None)
    out["changed_since_send"] = False
    if mine_last:           # oxirgi yuborilgandan keyin reja tahrirlangan yoki PPTX qayta yaratilgan (fayl farqi)
        f = ddir(did) / "taqdimot.pptx"
        out["changed_since_send"] = d["status"] != "tayyor" or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != mine_last["sha256"]
    try:
        ex = _ex_load(did)
        out["doc_topic_no"] = doc_topic_no(ex["blocks"])
        out["image_list"] = [{"n": i["n"], "w": i["w"], "h": i["h"], "ctx": i.get("ctx", "")} for i in ex["images"]]
    except Exception:
        out["image_list"], out["doc_topic_no"] = [], None
    if out["outline"]:
        out["pages"] = len(RD.plan_pages(out["outline"])) + 3      # titul + reja + kontent + rahmat
    return out


def deck_sends(c: Ctx, d: dict, scope: bool | None = None) -> list[dict]:
    """Taqdimotning ko'rinadigan yuborilgan versiyalari. Hozirgi kurs egasi (ko'lam ichida): shu taqdimot VA shu muallifning boshqa taqdimotlari orqali
    yuborilganlar; ko'lamdan chiqqan (kurs boshqaga o'tgan): faqat o'zining shu taqdimotdan yuborganlari."""
    if not d.get("course_id") or not d.get("lkey"):
        return []
    scope = _scope_ok(c, d) if scope is None else scope
    if scope:
        rows = db.rows(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? AND (deck_id=? OR sent_by=?) ORDER BY version DESC LIMIT 50",
                       (d["course_id"], d["lkey"], d["id"], d["user_id"]))
    else:
        rows = db.rows(_con, "SELECT * FROM pres_sends WHERE deck_id=? AND sent_by=? ORDER BY version DESC LIMIT 50", (d["id"], c.user["id"]))
    return [_send_pub(r) for r in rows]


def save_outline(c: Ctx, did: int, outline: dict) -> dict:
    d = _deck(c, did, write=True)
    try:
        o = normalize(outline, d["images"] or 0)
    except ValueError as e:
        _bad(str(e))
    if d.get("course_id") and d.get("lkey"):      # darsga bog'langan: fan nomi va mavzu raqami SERVER tomonida darsdan majburlanadi (qo'lda o'zgartirib bo'lmaydi)
        try:
            co = _PK()._course_row(d["course_id"]); les = _PK().lesson_info(co, d["lkey"])
            o["subject"] = (co["subject"] or "")[:120]
            o["topic_no"] = str(les["no"]) if les["kind"] == "maruza" else str(les.get("topic") or "")
        except HTTPException:                      # dars o'chirilgan — saqlangan qiymat (deckdagi) qoladi
            o["subject"], o["topic_no"] = d["subject"] or o["subject"], d["topic_no"] or o["topic_no"]
    try:
        with _lock:
            _con.execute("UPDATE pres_decks SET outline=?, title=?, subject=?, topic_no=?, status='reja', updated_at=? WHERE id=?",
                         (json.dumps(o, ensure_ascii=False), o["title"], o["subject"], o["topic_no"], clock.now_iso(), did))
            _con.commit()
    except BaseException:
        _rollback(); raise
    rbac.audit(_con, c, "taqdimot: reja tahrirlandi", RES, True, f"#{did} · {len(o['slides'])} slayd")
    return view(c, did)


def build(c: Ctx, did: int) -> dict:
    d = _deck(c, did, write=True)
    if not d["outline"]:
        _bad("Avval reja tuzilsin")
    o = json.loads(d["outline"])
    out = ddir(did) / "taqdimot.pptx"
    try:
        r = RD.render(o, out, ddir(did) / "img")
    except Exception as e:
        rbac.audit(_con, c, "taqdimot: pptx xatosi", RES, True, f"#{did} · {type(e).__name__}: {str(e)[:120]}")
        _bad("Taqdimot faylini yaratib bo'lmadi. Rejani tekshirib, qayta urinib ko'ring.", 500)
    try:
        with _lock:
            _con.execute("UPDATE pres_decks SET status='tayyor', slides=?, built_at=?, updated_at=? WHERE id=?", (r["slides"], clock.now_iso(), clock.now_iso(), did))
            _con.commit()
    except BaseException:
        _rollback(); raise
    rbac.audit(_con, c, "taqdimot: pptx yaratildi", RES, True, f"#{did} · {r['slides']} slayd")
    return view(c, did)


def file_name(d: dict) -> str:
    base = re.sub(r"[^\w\- ]+", "", f"{d['topic_no'] + '-mavzu ' if d['topic_no'] else ''}{d['title'] or 'taqdimot'}", flags=re.U).strip() or "taqdimot"
    return base[:80] + ".pptx"


def listing(c: Ctx, scope: str) -> dict:
    m = mode(c)
    if scope == "dept" and m == "dept":
        rows = db.rows(_con, "SELECT * FROM pres_decks WHERE deleted=0 AND dept_id=? AND user_id!=? ORDER BY id DESC LIMIT 200", (_dept(c), c.user["id"]))
    else:
        rows = db.rows(_con, "SELECT * FROM pres_decks WHERE deleted=0 AND user_id=? ORDER BY id DESC LIMIT 200", (c.user["id"],))
    items = [{k: r[k] for k in ("id", "title", "subject", "topic_no", "source_name", "source_kind", "engine", "status", "slides", "created_at", "updated_at", "user_name",
                                "course_id", "lkey", "lesson_code")}
             | {"engine_label": ENGINE_LABEL.get(r["engine"] or "", "—"), "sent_version": int(r.get("sent_version") or 0)} for r in rows]
    return {"items": items, "scope": "dept" if scope == "dept" and m == "dept" else "mine"}


def meta(c: Ctx) -> dict:
    u = c.user
    subjects = []
    if u.get("teacher_id"):
        subjects = [r["subject"] for r in db.rows(_con, "SELECT DISTINCT subject FROM teacher_groups WHERE teacher_id=? ORDER BY subject", (u["teacher_id"],))]
    if not subjects:
        try:
            subjects = [r["subject"] for r in db.rows(_con, "SELECT DISTINCT subject FROM syl_items WHERE department_id=? ORDER BY subject LIMIT 80", (_dept(c),))]
        except Exception:
            subjects = []
    return {**status(), "mode": mode(c), "limit": daily_limit(), "used": used_today(u["id"]), "max_mb": MAX_BYTES // (1024 * 1024),
            "subjects": subjects, "types": {t: TYPE_LABEL[t] for t in SLIDE_TYPES}, "teacher": bool(_tid(c)), "can_send": bool(_tid(c)) and mode(c) is not None}


TYPE_LABEL = {"plan": "Reja", "definition": "Ta'rif", "theory": "Nazariya", "two_column": "Ikki ustun", "steps": "Qadamlar", "example": "Ishlangan misol",
              "image": "Rasm", "tasks": "Topshiriqlar", "questions": "Nazorat savollari", "summary": "Xulosa", "references": "Adabiyotlar"}


# =============================================================================================
# Dars bilan bog'lash (kurs → yo'nalish → fan → dars) va «Studiyaga va masofaviy bo'limga yuborish»
# =============================================================================================
LESSON_KINDS = ("maruza", "amaliy")      # studiyada faqat L va A darslari tayyorlanadi (studio.KINDS_OK)
OPER, HEADS = "montaj_operator", ("masofaviy", "masofaviy_xodim")


def _PK():
    from . import paket as PK
    return PK


def _tid(c: Ctx) -> int:
    return int(c.user.get("teacher_id") or 0)


def sends_root() -> Path:
    return root() / "sends"


def send_dir(cid: int, lkey: int, ver: int) -> Path:
    return sends_root() / f"{int(cid)}_{int(lkey)}" / f"v{int(ver)}"


def _own_course(c: Ctx, cid: int, action: str) -> dict:
    """Faqat o'qituvchining O'Z yuklamasidagi fan (dl_courses.teacher_id == uning teacher_id). Boshqa fan — 403 + audit."""
    co = _PK()._course_row(cid)           # yo'q bo'lsa — 404
    tid = _tid(c)
    if not tid or co["teacher_id"] != tid:
        rbac.audit_deny(_con, c, f"taqdimot: begona fan ({action})", RES, f"kurs #{cid}")
        raise AccessDenied("⛔ Bu fan sizning yuklamangizda emas — taqdimot faqat o'z fanlaringiz darslariga bog'lanadi va yuboriladi. So'rov audit jurnaliga yozildi.")
    return co


def _lesson_of(co: dict, lkey: int) -> dict:
    les = _PK().lesson_info(co, int(lkey))          # dars kursda yo'q — 400
    if les["kind"] not in LESSON_KINDS:
        _bad("Taqdimot faqat ma'ruza (L) va amaliy (A) darsiga bog'lanadi")
    return les


def lesson_ref(co: dict, les: dict, codes: dict | None = None) -> dict:
    """Dars kartochkasining umumiy boshi: unikal kod, kafedra, o'qituvchi, fan, dars (Taqdimot, Studiya va Masofaviy bo'lim uchun BITTA ko'rinish)."""
    PK = _PK()
    codes = codes if codes is not None else PK.course_codes()
    return {"course_id": co["id"], "lkey": les["key"], "code": les["code"], "full_code": PK.lesson_unique_code(co["id"], les["key"], codes),
            "course_code": codes.get(co["id"]), "title": les["title"], "untitled": bool(les.get("untitled")), "kind": les["kind"],
            "subject": co.get("subject") or "", "direction": co.get("direction") or "", "course": co.get("course"), "dept": co.get("dept") or "",
            "teacher": PK._short(co.get("teacher") or "")}


def _bind_meta(c: Ctx, meta: dict) -> dict:
    """Dars tanlangan bo'lsa: ko'lam tekshiriladi, fan va mavzu raqami darsdan olinadi. Tanlanmagan bo'lsa — eski usul (bog'lanmagan)."""
    cid, lkey = int(meta.get("course_id") or 0), int(meta.get("lkey") or 0)
    if not cid and not lkey:
        return {**meta, "course_id": None, "lkey": None, "lesson_code": None}
    if not (cid and lkey):
        _bad("Darsni to'liq tanlang: kurs va dars")
    co = _own_course(c, cid, "taqdimot yaratish")
    les = _lesson_of(co, lkey)
    ref = lesson_ref(co, les)
    fb = les["title"] if not les.get("untitled") else (f"{les['no']}-mavzu — nomsiz" if les["kind"] == "maruza" else f"{les['no']}-{les.get('kind_label', 'dars').lower()} — nomsiz")
    return {**meta, "course_id": cid, "lkey": les["key"], "lesson_code": ref["full_code"], "subject": (co["subject"] or "")[:120],
            "topic_no": str(les["no"]) if les["kind"] == "maruza" else str(les.get("topic") or ""), "title_fallback": fb}


def lesson_view(d: dict, scope: bool = True) -> dict | None:
    if not d.get("course_id") or not d.get("lkey"):
        return None
    if not scope:                        # kurs boshqa o'qituvchiga o'tgan (yoki ko'lamdan tashqari): yangi o'qituvchining ismi/fan ma'lumoti ko'rsatilmaydi
        return {"course_id": d["course_id"], "lkey": d["lkey"], "full_code": d.get("lesson_code") or "", "code": "", "title": "", "subject": d.get("subject") or "",
                "direction": "", "course": None, "dept": "", "teacher": "", "moved": True}
    try:
        co = _PK()._course_row(d["course_id"])
        return lesson_ref(co, _PK().lesson_info(co, d["lkey"]))
    except HTTPException:                  # kurs yoki dars keyin o'chirilgan — kod saqlangan nusxadan
        return {"course_id": d["course_id"], "lkey": d["lkey"], "full_code": d.get("lesson_code") or "", "code": "", "title": "", "subject": d.get("subject") or "",
                "direction": "", "course": None, "dept": "", "teacher": "", "gone": True}


def my_lessons(c: Ctx) -> dict:
    """«Darsni tanlash» uchun: o'qituvchining O'Z fanlari (kurs 1–4 → yo'nalish → fan) va ularning L/A darslari — unikal kodlari bilan.
    Qatorlar /api/paket/courses bilan bir xil maydonlar (id, subject, direction, course, code, dir_code, dept, teacher) — umumiy tanlagich (static/lesson_picker.js)."""
    PK, tid = _PK(), _tid(c)
    cos = PK.course_rows_where("c.teacher_id=?", (tid,)) if tid else []
    codes = PK.course_codes()
    cids = [co["id"] for co in cos]
    inq = ",".join("?" * len(cids)) or "NULL"
    sent = {(r["course_id"], r["lkey"]): r for r in db.rows(
        _con, f"""SELECT s.course_id, s.lkey, s.version, s.deck_id, s.title, s.sent_at, (SELECT d.title FROM pres_decks d WHERE d.id=s.deck_id AND d.deleted=0) dtitle
                  FROM pres_sends s WHERE s.course_id IN ({inq}) AND s.version=(SELECT MAX(x.version) FROM pres_sends x WHERE x.course_id=s.course_id AND x.lkey=s.lkey)""", tuple(cids))}
    decks: dict = {}
    for r in db.rows(_con, f"SELECT id, title, course_id, lkey FROM pres_decks WHERE user_id=? AND deleted=0 AND course_id IN ({inq}) ORDER BY id DESC", (c.user["id"], *cids)):
        decks.setdefault((r["course_id"], r["lkey"]), []).append({"id": r["id"], "title": r["title"] or ""})
    items = []
    for co in cos:
        ls = []
        for les in PK.lessons(co["id"], co):
            if les["kind"] not in LESSON_KINDS:
                continue
            sd = sent.get((co["id"], les["key"]))
            ls.append({"key": les["key"], "code": les["code"], "kind": les["kind"], "title": les["title"], "untitled": bool(les.get("untitled")),
                       "full_code": PK.lesson_unique_code(co["id"], les["key"], codes), "sent_version": sd["version"] if sd else 0,
                       "lesson_sent_version": sd["version"] if sd else None, "lesson_sent_deck_id": sd["deck_id"] if sd else None,
                       "lesson_sent_deck_title": ((sd["dtitle"] or sd["title"] or "") if sd else None), "lesson_sent_at": sd["sent_at"] if sd else None,
                       "decks": decks.get((co["id"], les["key"]), [])})
        items.append({"id": co["id"], "subject": co["subject"], "direction": co.get("direction") or "", "course": co.get("course"), "semester": co.get("semester"),
                      "code": codes.get(co["id"]), "dir_code": PK.dir_abbr(co.get("direction")), "dept": co.get("dept") or "", "teacher": PK._short(co.get("teacher") or ""),
                      "lessons": ls})
    return {"items": items, "total": len(items)}


def assign_lesson(c: Ctx, did: int, cid: int, lkey: int) -> dict:
    """«Darsni belgilash»: mavjud (bog'lanmagan) taqdimotni darsga bog'lash. Yuborilgan taqdimotning darsi almashtirilmaydi."""
    d = _deck(c, did, write=True)
    if int(d.get("sent_version") or 0):
        _bad("Bu taqdimot allaqachon yuborilgan — darsini o'zgartirib bo'lmaydi", 409)
    meta = _bind_meta(c, {"course_id": cid, "lkey": lkey})
    if not meta["course_id"]:
        _bad("Darsni tanlang")
    changed = (d["subject"] or "") != meta["subject"] or (d["topic_no"] or "") != meta["topic_no"]
    o = json.loads(d["outline"]) if d["outline"] else None
    try:
        with _lock:
            if o is not None:
                o["subject"], o["topic_no"] = meta["subject"], meta["topic_no"]
            status_ = "reja" if (changed and d["status"] == "tayyor") else d["status"]     # titul o'zgardi — PPTX qayta yaratilsin
            _con.execute("UPDATE pres_decks SET course_id=?, lkey=?, lesson_code=?, subject=?, topic_no=?, outline=?, status=?, updated_at=? WHERE id=?",
                         (meta["course_id"], meta["lkey"], meta["lesson_code"], meta["subject"], meta["topic_no"],
                          json.dumps(o, ensure_ascii=False) if o is not None else d["outline"], status_, clock.now_iso(), did))
            _con.commit()
    except BaseException:
        _rollback(); raise
    rbac.audit(_con, c, "taqdimot: dars belgilandi", RES, True, f"#{did} · {meta['lesson_code']}")
    return view(c, did)


# ---- yuborilgan versiyalar --------------------------------------------------------------------
def _send_pub(r: dict) -> dict:
    return {"id": r["id"], "version": r["version"], "code": r["code"], "title": r["title"], "slides": r["slides"], "size": r["size"], "note": r["note"] or "",
            "sent_at": r["sent_at"], "sent_by": (r["sent_by_name"] or "").split(":")[-1].strip(), "deck_id": r["deck_id"], "has_pdf": bool(r["pdf_path"]), "png": int(r.get("png_count") or 0),
            "studio_seen": bool(r["studio_ack_at"]), "dept_seen": bool(r["dept_ack_at"]), "paket_ok": not r["paket_error"]}


def sends_public(cid, lkey, limit: int = 50) -> list[dict]:
    """Darsning yuborilgan taqdimot versiyalari (yangisi birinchi). Fayl yo'llari tashqariga chiqmaydi."""
    if not cid or not lkey:
        return []
    return [_send_pub(r) for r in db.rows(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? ORDER BY version DESC LIMIT ?", (int(cid), int(lkey), limit))]


def latest_sends(keys=None) -> dict:
    """{(course_id, lkey): oxirgi yuborilgan versiya (_send_pub)} — studiya ro'yxatlari uchun bitta so'rov."""
    rows = db.rows(_con, "SELECT * FROM pres_sends s WHERE s.course_id>0 AND version=(SELECT MAX(version) FROM pres_sends x WHERE x.course_id=s.course_id AND x.lkey=s.lkey)")
    out = {(r["course_id"], r["lkey"]): _send_pub(r) for r in rows}
    return out if keys is None else {k: v for k, v in out.items() if k in set(keys)}


def send_file(cid: int, lkey: int, ver: int, kind: str) -> tuple[dict, Path | None]:
    r = db.one(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? AND version=?", (int(cid), int(lkey), int(ver)))
    if not r:
        raise HTTPException(404, "Taqdimot versiyasi topilmadi")
    rel = r["pptx_path"] if kind == "pptx" else r["pdf_path"] if kind == "pdf" else None
    if kind not in ("pptx", "pdf"):
        raise HTTPException(400, "Fayl turi: pptx yoki pdf")
    f = root() / rel if rel else None
    return r, (f if f and f.is_file() else None)


def serve_send(cid: int, lkey: int, ver: int, kind: str):
    r, f = send_file(cid, lkey, ver, kind)
    if not f:
        raise HTTPException(404, "Bu versiyaning PDF nusxasi yo'q (eski yuborilgan versiya — taqdimotni qayta yuboring)" if kind == "pdf" else "Fayl diskda topilmadi")
    mt = "application/pdf" if kind == "pdf" else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return FileResponse(str(f), filename=f"{r['code']}_taqdimot_v{r['version']}.{kind}", media_type=mt,
                        content_disposition_type="inline" if kind == "pdf" else "attachment", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


def make_slides(outline: dict, images_dir: Path, out_dir: Path) -> tuple[bytes, int]:
    """Taqdimot rejasidan slayd rasmlari (out_dir/slides/NN.png) va PDF baytlari — LibreOffice'siz, Pillow (app/taqdimot_slides.py). Xatoda yarim fayllar o'chiriladi."""
    sd = out_dir / "slides"
    try:
        r = TS.render_deck(outline, images_dir, sd)
        if not r["slides"] or not r["pdf"]:
            raise RuntimeError("slayd chizilmadi")
        return r["pdf"], int(r["slides"])
    except BaseException:
        shutil.rmtree(sd, ignore_errors=True)
        raise


def slide_file(cid: int, lkey: int, ver: int, n: int) -> tuple[dict, Path | None]:
    r = db.one(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? AND version=?", (int(cid), int(lkey), int(ver)))
    if not r:
        raise HTTPException(404, "Taqdimot versiyasi topilmadi")
    cnt = int(r.get("png_count") or 0)
    if not cnt or not (1 <= int(n) <= cnt):
        return r, None
    f = send_dir(r["course_id"], r["lkey"], r["version"]) / "slides" / f"{int(n):02d}.png"
    return r, (f if f.is_file() else None)


def serve_slide(cid: int, lkey: int, ver: int, n: int):
    r, f = slide_file(cid, lkey, ver, n)
    if not f:
        raise HTTPException(404, "Bu versiyaning slayd rasmi yo'q (eski yuborilgan versiya yoki slayd raqami noto'g'ri)")
    return FileResponse(str(f), media_type="image/png", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


def ack(c: Ctx, cid: int, lkey: int) -> None:
    """Operator (studiya) yoki bo'lim xodimi dars tafsilotini ochdi — shu darsning yuborilgan taqdimotlari «ko'rildi» (xabar o'chadi)."""
    k = c.role.key
    col = "studio" if k == OPER else "dept" if k in HEADS else None
    if not col:
        return
    try:
        with _lock:
            n = _con.execute(f"UPDATE pres_sends SET {col}_ack_at=?, {col}_ack_by=? WHERE course_id=? AND lkey=? AND {col}_ack_at IS NULL",
                             (clock.now_iso(), c.user["full_name"], int(cid), int(lkey))).rowcount
            _con.commit()
    except BaseException:
        _rollback(); raise
    if n:
        try:
            from . import studio as STU
            STU._mw_invalidate()
        except Exception:
            pass


def mywork_items(c: Ctx, I) -> list:
    """«Mening vazifalarim» / qo'ng'iroqcha (studio.mywork_items orqali): yangi yuborilgan taqdimot — studiya operatoriga va Masofaviy bo'limga
    (har birida o'z «ko'rildi» belgisi: tafsilot ochilgach xabar o'chadi)."""
    k = c.role.key
    col = "studio" if k == OPER else "dept" if k in HEADS else None
    if not col:
        return []
    rows = db.rows(_con, f"""SELECT s.* FROM pres_sends s WHERE s.{col}_ack_at IS NULL AND s.course_id>0
                             AND s.version=(SELECT MAX(version) FROM pres_sends x WHERE x.course_id=s.course_id AND x.lkey=s.lkey) ORDER BY s.id DESC LIMIT 30""")
    out = []

    def fresh(it):          # muddat berilmaydi (yuborilgan vaqt muddat emas — yangi xabar darrov «Muddati o'tdi» bo'lib qolmasin); «Yangi» belgisi — fresh
        it["fresh"] = True
        return it

    for r in rows[:6]:
        sub = f"{r['title'] or ''} · {r['slides'] or '?'} slayd · {(r['sent_by_name'] or '').split(':')[-1].strip()} · yuborildi: {(r['sent_at'] or '')[:16].replace('T', ' ')}"
        if col == "studio":
            out.append(fresh(I("studio", "taqdimot", f"st-pr{r['id']}", f"Yangi taqdimot: {r['code']} · v{r['version']}", sub + " · syomkaga tayyorlang", None,
                               {"view": "studio", "tab": "darslar", "card": {"cid": r["course_id"], "lkey": r["lkey"]}}, "bolimga", "yuborildi", "mid", icon="file")))
        else:
            out.append(fresh(I("studio", "taqdimot", f"st-pr{r['id']}", f"Taqdimot yuborildi: {r['code']} · v{r['version']}", sub + " · dars kartochkasida", None,
                               {"view": "paket", "tab": "fanlar", "card": {"cid": r["course_id"], "lkey": r["lkey"]}}, "bolimga", "yuborildi", "mid", icon="file")))
    if len(rows) > 6:
        out.append(fresh(I("studio", "taqdimot", f"st-pr-more-{col}", f"Yangi taqdimotlar: yana {len(rows) - 6} ta", "Dars kartochkalarini oching", None,
                           {"view": "studio" if col == "studio" else "paket", "tab": "darslar" if col == "studio" else "fanlar"}, "bolimga", "", "mid", len(rows) - 6, icon="file")))
    return out


DUP_SECONDS = 30      # bir xil fayl, bir xil foydalanuvchi — shu muddat ichida takror bosish yangi versiya yaratmaydi


def _bullets_of(sl: dict, k: int = 8) -> list[str]:
    """Reja slaydidan syomka uchun qisqa bandlar (≤ k): ro'yxat, ustunlar, qadamlar, kartochkalar, matn, javob."""
    out = [x for x in (sl.get("bullets") or []) if x]
    for cl in sl.get("columns") or []:
        out += ([f"{cl.get('title')}:"] if cl.get("title") else []) + [x for x in cl.get("bullets") or [] if x]
    for st in sl.get("steps") or []:
        out.append(f"{st.get('title') or ''} {st.get('text') or ''}".strip())
    for cd in sl.get("cards") or []:
        out.append(f"{cd.get('title') or ''}: {cd.get('text') or ''}".strip(": "))
    if not out and sl.get("text"):
        out.append(sl["text"])
    for key, lab in (("highlight", ""), ("answer", "Javob: "), ("note", "Eslatma: ")):
        if sl.get(key):
            out.append(lab + sl[key])
    return [re.sub(r"\s+", " ", re.sub(r"\*\*", "", x)).strip()[:240] for x in out if x][:k]


def outline_snapshot(o: dict | None, fallback_title: str = "") -> dict:
    """Yuborilgan versiya paytidagi reja: {title, slides:[{n, kind, title, bullets(≤8), notes}]} — n PPTX slayd raqamiga mos (titul 1, reja 2, kontent 3 dan)."""
    if not o:
        return {"title": fallback_title, "slides": []}
    title = o.get("title") or fallback_title
    top = [x for x in (o.get("subject"), f"{o['topic_no']}-mavzu" if o.get("topic_no") else "", o.get("subtitle")) if x]
    slides = [{"n": 1, "kind": "title", "title": title, "bullets": top[:8], "notes": ""},
              {"n": 2, "kind": "plan", "title": "Reja", "bullets": [str(x)[:240] for x in RD.plan_items(o)][:8], "notes": ""}]
    n = 3
    for sl in o.get("slides") or []:
        if (sl.get("type") or "") in ("title", "plan"):
            continue
        try:
            pages = max(1, len(RD.paginate(sl)))
        except Exception:
            pages = 1
        slides.append({"n": n, "kind": sl.get("type") or "theory", "title": sl.get("title") or "", "bullets": _bullets_of(sl), "notes": sl.get("notes") or ""})
        n += pages
    return {"title": title, "slides": slides}


def send_outline(r: dict) -> dict:
    """Yuborilgan versiya rejasi: saqlangan nusxa; eski yozuv (nusxa yo'q) — yuborilgan PPTX'dan, bo'lmasa taqdimotning rejasidan; bo'lmasa — bo'sh slaydlar."""
    if r.get("outline"):
        try:
            o = json.loads(r["outline"])
            if isinstance(o, dict) and isinstance(o.get("slides"), list):
                return o
        except ValueError:
            pass
    f = root() / r["pptx_path"] if r.get("pptx_path") else None
    if f and f.is_file():
        try:
            ps = _PK().parse_pptx(f.read_bytes(), None, {})
            sl = [{"n": i, "kind": "title" if i == 1 else "slide", "title": x.get("title") or "", "bullets": [str(b)[:240] for b in (x.get("bullets") or [])][:8],
                   "notes": x.get("notes") or ""} for i, x in enumerate(ps["slides"], 1)]
            if sl:
                return {"title": r.get("title") or "", "slides": sl}
        except Exception:
            pass
    d = db.one(_con, "SELECT outline, title FROM pres_decks WHERE id=? AND deleted=0", (r["deck_id"],)) if r.get("deck_id") else None
    if d and d["outline"]:
        try:
            return outline_snapshot(json.loads(d["outline"]), r.get("title") or "")
        except Exception:
            pass
    return {"title": r.get("title") or "", "slides": []}


def _age(ts, now) -> float:
    try:
        import datetime as _dt
        return (now.replace(tzinfo=None) - _dt.datetime.fromisoformat(str(ts)[:19])).total_seconds()
    except (TypeError, ValueError):
        return 1e9


def send(c: Ctx, did: int, note: str = "") -> dict:
    """«Studiyaga va masofaviy bo'limga yuborish» — BITTA amal: yangi versiya (dars kodi o'zgarmaydi, versiya DARS bo'yicha oshadi), fayllar saqlanadi, darsning
    paketiga qo'yiladi, studiya va bo'limga xabar ketadi. Faqat o'qituvchining O'Z fani darsi; boshqa fan — 403 + audit.
    Butun jarayon (versiya hisobi + fayl + paketga qo'yish + eskisini almashtirish) DARS bo'yicha qulf ostida: parallel /send da taqdimot paketda yo'qolmaydi
    va yolg'on muvaffaqiyat bo'lmaydi. Bir xil fayl, bir xil foydalanuvchi, <30 s — takror bosish: yangi versiya yaratilmaydi ({unchanged: true, version})."""
    d = _deck(c, did, write=True)
    if not d["course_id"] or not d["lkey"]:
        _bad("Avval darsni tanlang («Darsni belgilash») — kod shu darsdan olinadi")
    co = _own_course(c, d["course_id"], "yuborish")
    les = _lesson_of(co, d["lkey"])
    if d["status"] != "tayyor" or not (ddir(did) / "taqdimot.pptx").is_file():
        _bad("Avval «PPTX yaratish» — tayyor taqdimotni yuborasiz")
    ref = lesson_ref(co, les)
    with _lesson_lock(co["id"], les["key"]):
        return _send_locked(c, did, co, les, ref, _s(note, 400))


def _send_locked(c: Ctx, did: int, co: dict, les: dict, ref: dict, note: str) -> dict:
    PK = _PK()
    d = _deck(c, did, write=True)                                   # qulfni kutganda holat o'zgargan bo'lishi mumkin
    pptx = ddir(did) / "taqdimot.pptx"
    if d["status"] != "tayyor" or not pptx.is_file() or d["course_id"] != co["id"] or d["lkey"] != les["key"]:
        _bad("Taqdimot holati o'zgargan — sahifani yangilab, qayta urinib ko'ring", 409)
    code, cid, lkey = ref["full_code"], co["id"], les["key"]
    raw = pptx.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    now_dt, now = clock.now(), clock.now_iso()
    prev = db.one(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? AND sent_by=? ORDER BY version DESC LIMIT 1", (cid, lkey, c.user["id"]))
    if prev and prev["sha256"] == sha and _age(prev["sent_at"], now_dt) < DUP_SECONDS:
        rbac.audit(_con, c, "taqdimot: takror yuborish (o'zgarmagan fayl)", RES, True, f"#{did} · {code} · v{prev['version']}")
        out = view(c, did)
        out["send"] = _send_pub(prev)
        out["version"], out["unchanged"], out["paket_error"] = prev["version"], True, prev["paket_error"]
        return out
    ccode = PK.course_codes().get(cid)
    snap = json.dumps(outline_snapshot(json.loads(d["outline"]) if d["outline"] else None, d["title"] or ""), ensure_ascii=False)
    fd = None
    try:
        with _lock:
            if ccode:       # kurs id qayta ishlatilgan bo'lsa — boshqa fanning eski versiyalari yangi kursga meros bo'lmaydi
                _con.execute("UPDATE pres_sends SET course_id=-id WHERE course_id=? AND lkey=? AND course_code IS NOT NULL AND course_code!=?", (cid, lkey, ccode))
            ver = int((db.one(_con, "SELECT MAX(version) v FROM pres_sends WHERE course_id=? AND lkey=?", (cid, lkey)) or {}).get("v") or 0) + 1
            fd = send_dir(cid, lkey, ver)
            fd.mkdir(parents=True, exist_ok=True)
            (fd / "taqdimot.pptx").write_bytes(raw)
            rel = str((fd / "taqdimot.pptx").relative_to(root()))
            sid = _con.execute("""INSERT INTO pres_sends(deck_id,course_id,lkey,code,version,title,slides,pptx_path,size,sha256,note,sent_by,sent_by_name,sent_at,course_code,outline)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (did, cid, lkey, code, ver, (d["title"] or "")[:200], d["slides"], rel, len(raw), sha, note or None,
                                c.user["id"], c.user["full_name"], now, ccode, snap)).lastrowid
            _con.execute("UPDATE pres_decks SET sent_version=?, sent_at=?, updated_at=? WHERE id=?", (ver, now, now, did))
            _con.commit()
    except BaseException as e:
        _rollback()
        if fd is not None:
            shutil.rmtree(fd, ignore_errors=True)
        if isinstance(e, sqlite3.IntegrityError):
            _bad("Bu versiya hozirgina yuborildi — sahifani yangilab, qayta urinib ko'ring", 409)
        raise
    # slayd rasmlari (PNG) va PDF — outline'dan Pillow bilan (LibreOffice kerak emas). Xato bo'lsa yuborish bekor bo'lmaydi: rasm yo'q — avvalgi xulq.
    from . import office_tools as OT
    own_pdf, png_n, slides_err, lo = None, 0, None, bool(OT.soffice())
    try:
        t0 = time.time()
        own_pdf, png_n = make_slides(json.loads(d["outline"]), ddir(did) / "img", fd)
        print(f"taqdimot.send: {png_n} slayd PNG/PDF chizildi, {time.time() - t0:.1f} s")
    except Exception as e:
        slides_err = f"{type(e).__name__}: {e}"[:200]
        print("taqdimot.send → slaydlar:", slides_err)
    # darsning paketiga (pk_assets, purpose='taqdimot'): slaydlar paketga, PDF — montajda slayd sifatida. Xato bo'lsa yuborish bekor bo'lmaydi.
    # PDF: serverda LibreOffice bo'lsa — u (asl ko'rinish, paket.upload_slides o'zi chizadi); bo'lmasa — bizning Pillow PDF (pdf_raw).
    paket_err, pdf_rel, paket_id = None, None, None
    try:
        r = PK.upload_slides(c, cid, lkey, raw, f"{code}_taqdimot_v{ver}.pptx", pdf_raw=None if lo else own_pdf)
        if r.get("pdf_id") and lo:
            a = db.one(PK._con, "SELECT * FROM pk_assets WHERE id=?", (r["pdf_id"],))
            if a and PK._apath(a).is_file():
                shutil.copyfile(PK._apath(a), send_dir(cid, lkey, ver) / "taqdimot.pdf")
                pdf_rel = str((send_dir(cid, lkey, ver) / "taqdimot.pdf").relative_to(root()))
        with PK._lock:
            try:
                PK._con.execute("""INSERT INTO pk_topics(course_id,topic_no,deck_id,updated_at) VALUES(?,?,?,?)
                                   ON CONFLICT(course_id,topic_no) DO UPDATE SET deck_id=excluded.deck_id, updated_at=excluded.updated_at""", (cid, lkey, did, now))
                PK._log(c, cid, lkey, "taqdimot: studiya va bo'limga yuborildi", f"v{ver} · {d['slides'] or '?'} slayd · {d['title'] or ''}"[:300]); PK._con.commit()
            except BaseException:
                _rollback(); raise
        paket_id = r.get("id")
        if not PK._latest_asset(cid, lkey, "taqdimot", ("pptx", "pdf")):
            paket_err = "Taqdimot paketda ko'rinmadi — dars kartochkasidan «Dars yaratish» orqali qayta qo'yiladi"
    except HTTPException as e:
        _rollback(); paket_err, paket_id = str(e.detail)[:300], None
    except Exception as e:                                       # kutilmagan xato yuborishni yiqitmasin
        _rollback(); paket_err, paket_id = f"{type(e).__name__}: {e}"[:300], None
    if own_pdf and not pdf_rel:                                  # LibreOffice yo'q (yoki PDF chizolmadi) — bizning PDF; paket xatosidan qat'i nazar saqlanadi
        try:
            (fd / "taqdimot.pdf").write_bytes(own_pdf)
            pdf_rel = str((fd / "taqdimot.pdf").relative_to(root()))
        except OSError as e:
            print("taqdimot.send → pdf yozilmadi:", repr(e))
    try:
        with _lock:
            _con.execute("UPDATE pres_sends SET pdf_path=?, paket_asset_id=?, paket_error=?, png_count=? WHERE id=?", (pdf_rel, paket_id, paket_err, png_n or None, sid)); _con.commit()
    except BaseException:
        _rollback(); raise
    try:
        from . import studio as STU
        STU.on_presentation(c, cid, lkey, code, ver, d["title"] or "", d["slides"] or 0)      # studiya rejasi + jurnal + xabar
    except Exception as e:
        _rollback()
        print("taqdimot.send → studiya:", repr(e))
    rbac.audit(_con, c, "taqdimot: studiyaga va bo'limga yuborildi", RES, True, f"#{did} · {code} · v{ver}" + (f" · paket: {paket_err}" if paket_err else "") + (f" · slaydlar: {slides_err}" if slides_err else ""))
    out = view(c, did)
    out["send"] = _send_pub(db.one(_con, "SELECT * FROM pres_sends WHERE id=?", (sid,)))
    out["version"], out["unchanged"], out["paket_error"], out["slides_error"] = ver, False, paket_err, slides_err
    return out


# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx:
    return _ctx(request)


def _meta_from(q: dict) -> dict:
    t = q.get("slides")
    try:
        t = max(5, min(MAX_SLIDES, int(t))) if t not in (None, "", "0", 0) else None
    except (TypeError, ValueError):
        t = None
    def _i(v):
        try: return int(v or 0)
        except (TypeError, ValueError): return 0
    return {"subject": _s(q.get("subject"), 120), "topic_no": _s(q.get("topic_no"), 20), "title": _s(q.get("title"), 200),
            "audience": _s(q.get("audience"), 500), "target": t, "course_id": _i(q.get("course_id")), "lkey": _i(q.get("lkey"))}


def _begin(request: Request, action: str, detail: str = "") -> Ctx:
    """Kirish tekshiruvi (sessiya + ruxsat + audit) — DB ishlari uchun oqimda (threadpool) bajariladi: qulf bo'lsa event loop qotmaydi."""
    c = C(request)
    guard(c, action, detail)
    return c


async def _read_limited(request: Request, limit: int) -> bytes:
    """Yuklangan tana — oqim bilan: Content-Length oldindan tekshiriladi (limitdan katta — 413, tana o'qilmaydi); Content-Length bo'lmasa yoki yolg'on bo'lsa ham
    chegaradan oshgan zahoti to'xtatiladi (xotira to'lmaydi)."""
    try:
        n = int(request.headers.get("content-length") or 0)
    except ValueError:
        n = 0
    if n > limit:
        raise HTTPException(413, f"Fayl hajmi {limit // (1024 * 1024)} MB dan oshmasin")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(413, f"Fayl hajmi {limit // (1024 * 1024)} MB dan oshmasin")
    return bytes(buf)


def _small_body(request: Request, limit: int = 2 * 1024 * 1024) -> None:
    """JSON so'rovlar (reja, izoh, dars) kichik: Content-Length juda katta bo'lsa — rad."""
    try:
        n = int(request.headers.get("content-length") or 0)
    except ValueError:
        n = 0
    if n > limit:
        raise HTTPException(413, "So'rov hajmi juda katta")


@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi"); return meta(c)


@router.post(P + "/decks")
async def api_upload(request: Request, name: str = "material", subject: str = "", topic_no: str = "", title: str = "", slides: str = "", audience: str = "",
                     course_id: int = 0, lkey: int = 0):
    c = await run_in_threadpool(_begin, request, "material yuklash", name[:60])         # ruxsat — tana o'qilishidan OLDIN (ruxsatsiz foydalanuvchi 20 MB yubormaydi)
    raw = await _read_limited(request, MAX_BYTES)
    return await run_in_threadpool(create, c, raw, None, name[:160], _meta_from(locals()))


class TextIn(BaseModel):
    text: str
    subject: str = ""
    topic_no: str = ""
    title: str = ""
    slides: int | None = None
    audience: str = ""
    course_id: int = 0
    lkey: int = 0


@router.post(P + "/decks/text")
async def api_text(request: Request):
    c = await run_in_threadpool(_begin, request, "matndan taqdimot")
    raw = await _read_limited(request, MAX_BYTES + 64 * 1024)
    try:
        body = TextIn.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "So'rov noto'g'ri: «text» maydoni kerak")
    return await run_in_threadpool(create, c, None, body.text, "matn.txt", _meta_from(body.model_dump()))


@router.get(P + "/decks")
def api_list(request: Request, scope: str = "mine"):
    c = C(request); guard(c, "taqdimotlar ro'yxati", scope[:10]); return listing(c, scope)


@router.get(P + "/decks/{did}")
def api_view(request: Request, did: int):
    c = C(request); guard(c, "taqdimot ko'rildi", f"#{did}"); return view(c, did)


class OutlineIn(BaseModel):
    outline: dict


@router.post(P + "/decks/{did}/outline")
def api_save(request: Request, did: int, body: OutlineIn):
    _small_body(request, 5 * 1024 * 1024)
    c = C(request); guard(c, "reja saqlash", f"#{did}"); return save_outline(c, did, body.outline)


class RegenIn(BaseModel):
    slides: int | None = None
    audience: str = ""


@router.post(P + "/decks/{did}/regenerate")
def api_regen(request: Request, did: int, body: RegenIn):
    _small_body(request)
    c = C(request); guard(c, "rejani qayta tuzish", f"#{did}")
    d = _deck(c, did, write=True)
    _check_limit(c)
    m = _meta_from({"subject": d["subject"], "topic_no": d["topic_no"], "title": d["title"], "slides": body.slides if body.slides is not None else d["target"],
                    "audience": body.audience or d["audience"]})
    try:
        with _lock:
            _con.execute("UPDATE pres_decks SET target=?, audience=? WHERE id=?", (m["target"], m["audience"], did)); _con.commit()
    except BaseException:
        _rollback(); raise
    return generate(c, did, m)


@router.post(P + "/decks/{did}/build")
def api_build(request: Request, did: int):
    c = C(request); guard(c, "pptx yaratish", f"#{did}")
    return build(c, did)


@router.get(P + "/decks/{did}/download")
def api_download(request: Request, did: int):
    c = C(request); guard(c, "pptx yuklab olish", f"#{did}")
    d = _deck(c, did)
    f = ddir(did) / "taqdimot.pptx"
    if d["status"] != "tayyor" or not f.exists():
        _bad("Taqdimot fayli hali yaratilmagan", 404)
    return FileResponse(str(f), filename=file_name(d), media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


@router.get(P + "/decks/{did}/img/{n}")
def api_img(request: Request, did: int, n: int):
    c = C(request)
    if mode(c) is None:
        guard(c, "rasm")
    _deck(c, did)
    for ext, mt in (("png", "image/png"), ("jpg", "image/jpeg")):
        f = ddir(did) / "img" / f"img{int(n)}.{ext}"
        if f.exists():
            return FileResponse(str(f), media_type=mt)
    raise HTTPException(404, "Rasm topilmadi")


@router.post(P + "/decks/{did}/delete")
def api_delete(request: Request, did: int):
    c = C(request); guard(c, "taqdimot o'chirildi", f"#{did}")
    _deck(c, did, write=True)
    try:
        with _lock:
            _con.execute("UPDATE pres_decks SET deleted=1, updated_at=? WHERE id=?", (clock.now_iso(), did)); _con.commit()
    except BaseException:
        _rollback(); raise
    shutil.rmtree(ddir(did), ignore_errors=True)
    return {"ok": True}


class LessonIn(BaseModel):
    course_id: int
    lkey: int


class SendIn(BaseModel):
    note: str = ""


@router.get(P + "/lessons")
def api_lessons(request: Request):
    c = C(request); guard(c, "darslar ro'yxati"); return my_lessons(c)


@router.post(P + "/decks/{did}/lesson")
def api_lesson(request: Request, did: int, body: LessonIn):
    c = C(request); guard(c, "darsni belgilash", f"#{did} · kurs #{body.course_id} · {body.lkey}"); return assign_lesson(c, did, body.course_id, body.lkey)


@router.post(P + "/decks/{did}/send")
def api_send(request: Request, did: int, body: SendIn):
    """Sinxron `def` — FastAPI uni oqimlar havzasida bajaradi: baza qulfi bo'lsa ham event loop (butun server) qotmaydi."""
    _small_body(request)
    c = C(request); guard(c, "studiyaga va bo'limga yuborish", f"#{did}")
    return send(c, did, body.note)


def _send_gate(c: Ctx, did: int, ver: int, what: str):
    """Yuborilgan versiya faylini olish ruxsati (pptx / pdf / slayd rasmi uchun bir xil): taqdimot egasi yoki o'z kafedra mudiri; darsning HOZIRGI kursiga ega bo'lish
    va versiya shu taqdimotniki (yoki shu muallifning boshqasidan) bo'lishi shart (IDOR). → (taqdimot, versiya yozuvi)."""
    d = _deck(c, did)
    if not d["course_id"] or not d["lkey"]:
        raise HTTPException(404, "Taqdimot darsga bog'lanmagan")
    if not _scope_ok(c, d):
        rbac.audit_deny(_con, c, "taqdimot: begona dars versiyasi", RES, f"#{did} · v{ver}")
        raise AccessDenied("⛔ Bu dars endi sizning yuklamangizda emas — yuborilgan versiyalarni yuklab olish mumkin emas. So'rov audit jurnaliga yozildi.")
    r = db.one(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? AND version=?", (d["course_id"], d["lkey"], int(ver)))
    if r and r["deck_id"] != did and r["sent_by"] != d["user_id"]:
        rbac.audit_deny(_con, c, "taqdimot: begona versiya", RES, f"#{did} · v{ver}")
        raise HTTPException(404, "Taqdimot versiyasi topilmadi")
    return d, r


@router.get(P + "/decks/{did}/sends/{ver}/slides/{n}.png")
def api_send_slide(request: Request, did: int, ver: int, n: int):
    """Yuborilgan versiyaning n-slaydi (PNG, 1600×900). Ruxsat — pdf/pptx bilan bir xil; har rasm uchun audit yozilmaydi (faqat rad etish)."""
    c = C(request)
    if not mode(c):
        guard(c, "slayd rasmini ochish", f"#{did} · v{ver} · {n}")        # ruxsat yo'q — audit + 403
    d, _r = _send_gate(c, did, ver, "slayd")
    return serve_slide(d["course_id"], d["lkey"], ver, n)


@router.get(P + "/decks/{did}/sends/{ver}/{kind}")
def api_send_file(request: Request, did: int, ver: int, kind: str):
    """Yuborilgan versiyani yuklab olish. Versiya shu taqdimotniki (yoki shu muallifning boshqa taqdimotidan yuborilgan) bo'lishi va chaqiruvchi shu darsning
    HOZIRGI kursiga ega (yoki kafedra ko'lamida) bo'lishi shart — kurs boshqaga o'tsa eski o'qituvchi yangisining versiyalarini ololmaydi (IDOR)."""
    c = C(request); guard(c, "yuborilgan versiyani yuklab olish", f"#{did} · v{ver} · {kind}")
    d, _r = _send_gate(c, did, ver, kind)
    return serve_send(d["course_id"], d["lkey"], ver, kind)
