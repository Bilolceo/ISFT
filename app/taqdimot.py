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
"""
from __future__ import annotations
import base64, io, json, os, re, shutil, threading, time
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
from . import clock, db, rbac
from . import taqdimot_extract as EX
from . import taqdimot_render as RD
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
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
  outline TEXT, engine TEXT, model TEXT, status TEXT DEFAULT 'reja', slides INT, built_at TEXT, created_at TEXT, updated_at TEXT, deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_pres_user ON pres_decks(user_id, deleted);
CREATE INDEX IF NOT EXISTS ix_pres_dept ON pres_decks(dept_id, deleted);
CREATE TABLE IF NOT EXISTS pres_gen(id INTEGER PRIMARY KEY, user_id INT, deck_id INT, day TEXT, at TEXT, engine TEXT, ok INT, ms INT, err TEXT,
  in_tok INT, out_tok INT);
CREATE INDEX IF NOT EXISTS ix_pres_gen ON pres_gen(user_id, day);
"""


def init(con):
    con.executescript(SCHEMA)
    con.commit()


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def root() -> Path:
    return Path(db.DATA_DIR) / "taqdimot"


def ddir(did: int) -> Path:
    return root() / str(int(did))


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
    rbac.audit(_con, c, "taqdimot: begona taqdimot", RES, False, f"#{did}" + (" · tahrirlash" if write else ""))
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


def _sl(v, n=40, m=400):
    return [x for x in (_s(i, m) for i in (v or [])[:n] if not isinstance(i, (dict, list))) if x]


def normalize(o: dict, n_images: int) -> dict:
    o = o if isinstance(o, dict) else {}
    out = {"subject": _s(o.get("subject"), 120), "topic_no": _s(o.get("topic_no"), 20), "title": _s(o.get("title"), 200) or "Mavzu",
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
        title = sections[0]["h"]
        if not sections[0]["items"]:
            sections = sections[1:]
    title = title or meta.get("source_stem") or "Mavzu"
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
            if meta.get(k): outline[k] = _s(meta[k], 200)
    except AIError as e:
        err = str(e)
    except ValueError as e:
        err = f"Reja tuzilmadi: {e}"
    ms = int((time.time() - t0) * 1000)
    with _lock:
        _con.execute("INSERT INTO pres_gen(user_id,deck_id,day,at,engine,ok,ms,err,in_tok,out_tok) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (c.user["id"], did, clock.today().isoformat(), clock.now_iso(), eng, 0 if err else 1, ms, err, info.get("in"), info.get("out")))
        if not err:
            _con.execute("UPDATE pres_decks SET outline=?, engine=?, model=?, status='reja', title=?, subject=?, topic_no=?, updated_at=? WHERE id=?",
                         (json.dumps(outline, ensure_ascii=False), eng, info.get("model"), outline["title"], outline["subject"], outline["topic_no"],
                          clock.now_iso(), did))
        _con.commit()
    rbac.audit(_con, c, "taqdimot: reja tuzildi" if not err else "taqdimot: reja xatosi", RES, True,
               f"#{did} · {ENGINE_LABEL[eng]} · {ms} ms" + (f" · {err[:120]}" if err else ""))
    if err:
        _bad(err, 502 if eng == "claude" else 400)
    return view(c, did)


def create(c: Ctx, raw: bytes | None, text: str | None, name: str, meta: dict) -> dict:
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
    with _lock:
        did = _con.execute("""INSERT INTO pres_decks(user_id,user_name,dept_id,title,subject,topic_no,audience,target,source_name,source_kind,
                              status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (c.user["id"], c.user["full_name"], _dept(c), meta.get("title") or Path(name).stem[:120], meta.get("subject"),
                            meta.get("topic_no"), meta.get("audience"), meta.get("target"), name[:160], kind, "yangi", now, now)).lastrowid
        _con.commit()
    d = ddir(did)
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"manba.{kind}").write_bytes(raw)
        ex = EX.extract(raw, kind, d / "img")
    except EX.BadFile as e:
        shutil.rmtree(d, ignore_errors=True)
        with _lock:
            _con.execute("UPDATE pres_decks SET deleted=1 WHERE id=?", (did,)); _con.commit()
        rbac.audit(_con, c, "taqdimot: material o'qilmadi", RES, False, f"{name[:60]} · {e}")
        _bad(str(e), 415)
    (d / "material.json").write_text(json.dumps(ex, ensure_ascii=False), encoding="utf-8")
    _, trunc = EX.as_text(ex["blocks"], MAX_CHARS)
    with _lock:
        _con.execute("UPDATE pres_decks SET source_chars=?, truncated=?, images=? WHERE id=?", (ex["chars"], int(trunc), len(ex["images"]), did))
        _con.commit()
    rbac.audit(_con, c, "taqdimot: material yuklandi", RES, True, f"#{did} · {name[:60]} · {kind} · {ex['chars']} belgi · {len(ex['images'])} rasm")
    meta = {**meta, "source_stem": Path(name).stem}
    return generate(c, did, meta)


def view(c: Ctx, did: int) -> dict:
    d = _deck(c, did)
    out = {k: d[k] for k in ("id", "title", "subject", "topic_no", "audience", "target", "source_name", "source_kind", "source_chars", "truncated",
                             "images", "engine", "model", "status", "slides", "built_at", "created_at", "updated_at", "user_name")}
    out["engine_label"] = ENGINE_LABEL.get(d["engine"] or "", "—")
    out["outline"] = json.loads(d["outline"]) if d["outline"] else None
    out["mine"] = d["user_id"] == c.user["id"]
    out["can_edit"] = out["mine"]
    if out["outline"]:
        out["pages"] = len(RD.plan_pages(out["outline"])) + 3      # titul + reja + kontent + rahmat
    try:
        ex = _ex_load(did)
        out["image_list"] = [{"n": i["n"], "w": i["w"], "h": i["h"], "ctx": i.get("ctx", "")} for i in ex["images"]]
    except Exception:
        out["image_list"] = []
    return out


def save_outline(c: Ctx, did: int, outline: dict) -> dict:
    d = _deck(c, did, write=True)
    try:
        o = normalize(outline, d["images"] or 0)
    except ValueError as e:
        _bad(str(e))
    with _lock:
        _con.execute("UPDATE pres_decks SET outline=?, title=?, subject=?, topic_no=?, status='reja', updated_at=? WHERE id=?",
                     (json.dumps(o, ensure_ascii=False), o["title"], o["subject"], o["topic_no"], clock.now_iso(), did))
        _con.commit()
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
    with _lock:
        _con.execute("UPDATE pres_decks SET status='tayyor', slides=?, built_at=?, updated_at=? WHERE id=?", (r["slides"], clock.now_iso(), clock.now_iso(), did))
        _con.commit()
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
    items = [{k: r[k] for k in ("id", "title", "subject", "topic_no", "source_name", "source_kind", "engine", "status", "slides", "created_at", "updated_at", "user_name")}
             | {"engine_label": ENGINE_LABEL.get(r["engine"] or "", "—")} for r in rows]
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
            "subjects": subjects, "types": {t: TYPE_LABEL[t] for t in SLIDE_TYPES}}


TYPE_LABEL = {"plan": "Reja", "definition": "Ta'rif", "theory": "Nazariya", "two_column": "Ikki ustun", "steps": "Qadamlar", "example": "Ishlangan misol",
              "image": "Rasm", "tasks": "Topshiriqlar", "questions": "Nazorat savollari", "summary": "Xulosa", "references": "Adabiyotlar"}


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
    return {"subject": _s(q.get("subject"), 120), "topic_no": _s(q.get("topic_no"), 20), "title": _s(q.get("title"), 200),
            "audience": _s(q.get("audience"), 500), "target": t}


@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi"); return meta(c)


@router.post(P + "/decks")
async def api_upload(request: Request, name: str = "material", subject: str = "", topic_no: str = "", title: str = "", slides: str = "", audience: str = ""):
    c = C(request); guard(c, "material yuklash", name[:60])
    raw = await request.body()
    return await run_in_threadpool(create, c, raw, None, name[:160], _meta_from(locals()))


class TextIn(BaseModel):
    text: str
    subject: str = ""
    topic_no: str = ""
    title: str = ""
    slides: int | None = None
    audience: str = ""


@router.post(P + "/decks/text")
async def api_text(request: Request, body: TextIn):
    c = C(request); guard(c, "matndan taqdimot")
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
    c = C(request); guard(c, "reja saqlash", f"#{did}"); return save_outline(c, did, body.outline)


class RegenIn(BaseModel):
    slides: int | None = None
    audience: str = ""


@router.post(P + "/decks/{did}/regenerate")
async def api_regen(request: Request, did: int, body: RegenIn):
    c = C(request); guard(c, "rejani qayta tuzish", f"#{did}")
    d = _deck(c, did, write=True)
    _check_limit(c)
    m = _meta_from({"subject": d["subject"], "topic_no": d["topic_no"], "title": d["title"], "slides": body.slides if body.slides is not None else d["target"],
                    "audience": body.audience or d["audience"]})
    with _lock:
        _con.execute("UPDATE pres_decks SET target=?, audience=? WHERE id=?", (m["target"], m["audience"], did)); _con.commit()
    return await run_in_threadpool(generate, c, did, m)


@router.post(P + "/decks/{did}/build")
async def api_build(request: Request, did: int):
    c = C(request); guard(c, "pptx yaratish", f"#{did}")
    return await run_in_threadpool(build, c, did)


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
    with _lock:
        _con.execute("UPDATE pres_decks SET deleted=1, updated_at=? WHERE id=?", (clock.now_iso(), did)); _con.commit()
    shutil.rmtree(ddir(did), ignore_errors=True)
    return {"ok": True}
