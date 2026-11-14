"""«Dars tayyorlash» — birlashgan bo'lim: shablon bo'yicha avtomatik yig'ish (app/paket.py) + bloklar muharriri (app/kurs.py). docs/dars.md.

Nima uchun: NEXTID'da har fan sahifasida, masalan, 45 ta dars bor — L1–L15 ma'ruza va A1–A30 amaliy (har ma'ruza mavzusiga ikkita amaliy), har biri
alohida paket. Avval «Dars tayyorlash» (shablon bo'yicha yig'ish) va «Kurs muharriri» (Rise kabi bloklar) ikki alohida bo'lim edi; endi bitta joy:

  1. Fan → NEXTID darslar to'ri (L/A kodlari, har darsda holat: material, video, paket, ko'rib chiqish, tasdiq, ochiq izohlar). Har darsda ikki
     amal: «Avtomatik yig'ish (shablon)» (paket.build_topic) va «Muharrirda tahrirlash» — paket mazmuni (muqova, video, reja, rasm/jadvalli matn,
     xulosalar, slaydlar, mashqlar, test, o'z-o'zini baholash) Kurs muharriri bloklariga o'tkaziladi (ds_links — ikki tomonlama bog'lanish;
     eksport uchun qaysi manba ustun — «authority»: paket | kurs).
  2. Fan shabloni (skelet): bir bosishda L1..Ln + A1..A(k·n) (mavzular ro'yxatidan nomlar, k — sozlanadi) va har dars uchun kafedra shabloni
     bo'yicha bloklar. Shablon (ds_templates) — dars turi bo'yicha bloklar tartibi, masofaviy bo'lim tahrirlaydi, versiyalanadi. «Shablonni
     qo'llash»: shablon bloklari (uid «tp<kalit><nn><hex>») qayta tartiblanadi/qo'shiladi/olib tashlanadi, MUALLIF bloklari (boshqa uid) va
     shablon bloklaridagi muallif mazmuni saqlanadi; avval ko'rib chiqish (farq + sonlar), keyin hammasiga. Ommaviy qayta yig'ish / eksport —
     fon ishi (jarayon ko'rsatiladi), natija — zip ichida zip'lar yoki har dars alohida.
  3. AI: hujjatdan dars — .docx/.pdf/.txt (paket.docx_lecture / taqdimot_extract: rasm va jadvallar bilan) → Claude (claude_client.call_json,
     qat'iy sxema) → bloklar. Saqlashdan oldingi QAT'IY tekshiruvlar (deterministik, testlangan): javob o'rinlari aralashtirilib teng
     taqsimlanadi; to'g'ri javob tizimli ravishda eng uzun bo'lmasin (belgilanadi + chalg'ituvchilar bir marta qayta so'raladi); har bir bo'lim
     kamida bitta savol bilan qamralgan; faqat o'zbek lotin yozuvi (kirill → lotin transliteratsiya, inglizcha qoldiqlar tashlanadi);
     o'ylab topilgan fakt yo'q — har paragraf manbadan iqtibos keltiradi va u manbada bo'lishi, raqamlari manbada uchrashi shart.
     Kalitsiz — o'zbekcha xato (503), soxta natija yo'q. Tokenlar ds_ai jadvalida (tb_gen kabi). Claude'ga faqat kurs/mavzu nomi va ma'ruza matni.
  4. Izohlar (ko'rib chiqish): blokka biriktirilgan (ds_comments), tarmoqli, hal qilish / qayta ochish, muallifni eslatish; to'xtatuvchi
     (blocking) ochiq izoh bo'lsa ko'rib chiqishga yuborish va tasdiqlash to'xtaydi (sabab bilan aylanib o'tish — audit + ds_overrides).
     Bildirishnoma — «Mening vazifalarim» (paket.pending orqali).

Ruxsat: rbac.PAKET resursi (har so'rov audit jurnalida). Bo'lim (masofaviy, masofaviy_xodim) — hammasi, shablon tahriri; o'qituvchi — o'z fanlari;
kafedra mudiri — o'z kafedrasi fanlari: ko'rish va izoh (o'z kafedrasi kurslarida to'xtatuvchi izoh ham); rektor/prorektor — 403 (jamlangan
ko'rsatkichlar «Holat» yorlig'ida).
"""
from __future__ import annotations
import hashlib, html, io, json, math, os, re, secrets, shutil, threading, time, zipfile
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import clock, db, rbac
from . import paket as PK
from . import kurs as KU
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
P = "/api/dars"
RES = rbac.PAKET

HEAD, STAFF, KAF, TEACH = "masofaviy", "masofaviy_xodim", "kafedra", "oqituvchi"
DEPT = (HEAD, STAFF)
AUTHORS = DEPT + (TEACH,)
REVIEWERS = DEPT + (KAF,)
WORK = DEPT + (KAF, TEACH)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ds_templates(id INTEGER PRIMARY KEY, tkey TEXT, department_id INT DEFAULT 0, version INT, name TEXT, layout TEXT, note TEXT,
  user_id INT, user_name TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS ix_ds_tpl ON ds_templates(tkey, version);
CREATE TABLE IF NOT EXISTS ds_links(dl_course_id INT, lkey INT, ku_course_id INT, authority TEXT DEFAULT 'kurs', tpl_id INT, src TEXT,
  created_at TEXT, created_by TEXT, updated_at TEXT, PRIMARY KEY(dl_course_id, lkey));
CREATE INDEX IF NOT EXISTS ix_ds_links_k ON ds_links(ku_course_id);
CREATE TABLE IF NOT EXISTS ds_comments(id INTEGER PRIMARY KEY, course_id INT, lesson_id INT, block_uid TEXT, parent_id INT, user_id INT, user_name TEXT,
  role TEXT, text TEXT, blocking INT DEFAULT 0, mention_author INT DEFAULT 0, status TEXT DEFAULT 'ochiq', ts TEXT, resolved_by TEXT, resolved_at TEXT,
  deleted INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_ds_cm ON ds_comments(course_id, status);
CREATE TABLE IF NOT EXISTS ds_overrides(id INTEGER PRIMARY KEY, course_id INT, kind TEXT, action TEXT, reason TEXT, open_blocking INT, user_id INT, user_name TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS ds_jobs(id INTEGER PRIMARY KEY, dl_course_id INT, action TEXT, mode TEXT, status TEXT, total INT, done INT, ok INT, failed INT,
  result TEXT, file TEXT, user_id INT, user_name TEXT, ts TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS ds_ai(id INTEGER PRIMARY KEY, course_id INT, user_id INT, day TEXT, ts TEXT, model TEXT, ok INT, ms INT, err TEXT,
  in_tok INT, out_tok INT, n_calls INT, stats TEXT);
CREATE INDEX IF NOT EXISTS ix_ds_ai ON ds_ai(user_id, day);
"""

def _now(): return clock.now().replace(microsecond=0).isoformat(timespec="seconds")
def _j(s, d):
    try: v = json.loads(s) if s else d
    except (TypeError, ValueError): return d
    return v if isinstance(v, type(d)) else d

def init(con):
    try:
        con.executescript(SCHEMA); con.commit()
        seed_templates(con)
    except Exception as e:
        print("dars.init:", repr(e))

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=WORK, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"dars: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Dars tayyorlash: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def _audit(c: Ctx, action: str, detail: str = ""):
    rbac.audit(_con, c, f"dars: {action}", RES, True, detail)


# =============================================================================================
# 1. Shablon (kafedra shabloni): dars turi bo'yicha bloklar tartibi — versiyalanadi
# =============================================================================================
SLOT_KINDS = {
    "cover": "Muqova (dars sarlavhasi)", "section": "Bo'lim sarlavhasi", "video": "Videodars", "plan": "Reja", "text": "Ma'ruza matni (rasm, jadval)",
    "keypoints": "Asosiy xulosalar", "refs": "Adabiyotlar", "slides": "Taqdimot", "files": "Qo'shimcha fayllar", "flashcards": "Kartochkalar",
    "exercises": "Moslashtirish / saralash", "assignment": "Topshiriq", "reflect": "O'z-o'zini baholash", "continue": "«Davom etish» tugmasi",
    "divider": "Ajratgich", "quiz": "Yakuniy test (alohida test darsi)"}
STATIC = ("section", "continue", "divider")          # mazmuni shablondan — qayta qo'llashda shablon matni yangilanadi
LTYPES = {"maruza": "Ma'ruza (L)", "amaliy": "Amaliy mashg'ulot (A)"}
_KEY_RX = re.compile(r"^[a-z]{2,14}$")
MAX_ITEMS = 40

def _it(kind, key=None, text=""):
    d = {"key": key or kind, "kind": kind}
    if kind == "section": d["text"] = text
    return d
DEFAULT_LAYOUT = {
    "maruza": [_it("cover"), _it("section", "secvideo", "VIDEODARS"), _it("video"), _it("section", "sectext", "MA'RUZA MATNI"), _it("plan"), _it("text"),
               _it("keypoints"), _it("refs"), _it("section", "secslides", "DARS TAQDIMOTI"), _it("slides"), _it("files"),
               _it("section", "secpractice", "MASHQ VA TOPSHIRIQLAR"), _it("flashcards"), _it("exercises"), _it("assignment"), _it("reflect"), _it("quiz")],
    "amaliy": [_it("cover"), _it("section", "secvideo", "VIDEODARS"), _it("video"), _it("section", "sectask", "AMALIY MASHG'ULOT"), _it("plan"), _it("text"),
               _it("files"), _it("section", "secpractice", "MASHQ VA TOPSHIRIQLAR"), _it("flashcards"), _it("exercises"), _it("assignment"), _it("reflect"), _it("quiz")]}

def ltype_of(kind: str) -> str:
    return "maruza" if kind == "maruza" else "amaliy"

def clean_layout(v) -> dict:
    """Shablon tartibi → me'yorlangan {maruza: [...], amaliy: [...]}. Kalit — [a-z]{2,14}, tur ichida yagona (berilmasa turidan, takrorda harf qo'shiladi);
    noma'lum tur — 400; test (quiz) — ko'pi bilan bitta."""
    if not isinstance(v, dict): raise HTTPException(400, "Shablon tuzilishi noto'g'ri")
    out = {}
    for lt in LTYPES:
        items = v.get(lt)
        if items is None: items = DEFAULT_LAYOUT[lt]
        if not isinstance(items, list) or not items: raise HTTPException(400, f"«{LTYPES[lt]}» uchun bloklar ro'yxati bo'sh")
        if len(items) > MAX_ITEMS: raise HTTPException(400, f"Bitta dars turida {MAX_ITEMS} tadan ortiq shablon bloki bo'lmaydi")
        seen, res = set(), []
        for i, it in enumerate(items, 1):
            if not isinstance(it, dict) or it.get("kind") not in SLOT_KINDS: raise HTTPException(400, f"{LTYPES[lt]}: {i}-band — blok turi noma'lum")
            kind = it["kind"]
            key = str(it.get("key") or "").strip().lower()
            if not _KEY_RX.match(key): key = {"section": "sec", "continue": "cont", "divider": "div"}.get(kind, kind)
            base, n = key[:12], 0
            while key in seen:
                key = base + "abcdefghijklmnopqrstuvwxyz"[n % 26] * (1 + n // 26); n += 1
            seen.add(key)
            d = {"key": key, "kind": kind}
            if kind == "section":
                d["text"] = re.sub(r"\s+", " ", str(it.get("text") or "")).strip()[:120] or "BO'LIM"
            res.append(d)
        if sum(1 for x in res if x["kind"] == "quiz") > 1: raise HTTPException(400, f"{LTYPES[lt]}: yakuniy test bitta bo'ladi")
        out[lt] = res
    return out

def tpl_row(r: dict | None) -> dict | None:
    if not r: return None
    return {"id": r["id"], "tkey": r["tkey"], "department_id": r["department_id"], "version": r["version"], "name": r["name"],
            "layout": _j(r["layout"], {}), "note": r["note"] or "", "by": r["user_name"], "ts": r["ts"]}

def seed_templates(con):
    if db.one(con, "SELECT 1 x FROM ds_templates WHERE tkey='global'"): return
    con.execute("INSERT INTO ds_templates(tkey,department_id,version,name,layout,note,user_name,ts) VALUES('global',0,1,?,?,?,?,?)",
                ("Kafedra shabloni (standart)", json.dumps(DEFAULT_LAYOUT, ensure_ascii=False), "Rise 360 «qadamlar» shabloni asosida", "Tizim", _now()))
    con.commit()

def template_by_id(tid) -> dict | None:
    return tpl_row(db.one(_con, "SELECT * FROM ds_templates WHERE id=?", (int(tid or 0),))) if tid else None

def template_for(department_id) -> dict:
    """Kafedraning oxirgi versiyasi, bo'lmasa — umumiy shablonning oxirgi versiyasi."""
    r = None
    if department_id: r = db.one(_con, "SELECT * FROM ds_templates WHERE tkey=? ORDER BY version DESC LIMIT 1", (f"dep:{int(department_id)}",))
    r = r or db.one(_con, "SELECT * FROM ds_templates WHERE tkey='global' ORDER BY version DESC LIMIT 1")
    return tpl_row(r) or {"id": 0, "tkey": "global", "department_id": 0, "version": 0, "name": "Standart", "layout": DEFAULT_LAYOUT, "note": "", "by": "", "ts": ""}

def templates_list(c: Ctx) -> dict:
    deps = {r["id"]: r["name"] for r in db.rows(_con, "SELECT id, name FROM departments")}
    rows = db.rows(_con, "SELECT * FROM ds_templates ORDER BY tkey, version DESC")
    latest, hist = {}, {}
    for r in rows:
        hist.setdefault(r["tkey"], []).append({"id": r["id"], "version": r["version"], "ts": r["ts"], "by": r["user_name"], "note": r["note"] or ""})
        latest.setdefault(r["tkey"], r)
    if c.role.key == KAF: latest = {k: v for k, v in latest.items() if k in ("global", f"dep:{int(c.user.get('department_id') or 0)}")}
    return {"items": [{**tpl_row(r), "department": deps.get(r["department_id"]) if r["department_id"] else "Barcha kafedralar",
                       "versions": hist[k][:20]} for k, r in latest.items()],
            "kinds": SLOT_KINDS, "ltypes": LTYPES, "static": list(STATIC), "default": DEFAULT_LAYOUT,
            "departments": [{"id": k, "name": v} for k, v in sorted(deps.items(), key=lambda x: x[1] or "")], "can_edit": c.role.key in DEPT}

def save_template(c: Ctx, department_id: int, name: str, layout, note: str = "") -> dict:
    if c.role.key not in DEPT:
        rbac.audit(_con, c, "dars: shablon tahriri rad etildi", RES, False, f"dep {department_id}")
        raise AccessDenied("⛔ Kafedra shablonini faqat Masofaviy ta'lim bo'limi tahrirlaydi. So'rov audit jurnaliga yozildi.")
    dep = int(department_id or 0)
    if dep and not db.one(_con, "SELECT 1 x FROM departments WHERE id=?", (dep,)): raise HTTPException(400, "Kafedra topilmadi")
    lay = clean_layout(layout)
    tkey = f"dep:{dep}" if dep else "global"
    with _lock:
        cur = db.one(_con, "SELECT * FROM ds_templates WHERE tkey=? ORDER BY version DESC LIMIT 1", (tkey,))
        if cur and _j(cur["layout"], {}) == lay and (cur["name"] or "") == (name or cur["name"] or ""):
            return {"ok": True, "unchanged": True, "template": tpl_row(cur)}
        ver = (cur["version"] if cur else 0) + 1
        tid = _con.execute("INSERT INTO ds_templates(tkey,department_id,version,name,layout,note,user_id,user_name,ts) VALUES(?,?,?,?,?,?,?,?,?)",
                           (tkey, dep, ver, re.sub(r"\s+", " ", str(name or "")).strip()[:120] or "Kafedra shabloni", json.dumps(lay, ensure_ascii=False),
                            str(note or "")[:300], c.user["id"], c.user["full_name"], _now())).lastrowid
        _con.commit()
    _audit(c, "shablon saqlandi", f"{tkey} · v{ver}")
    return {"ok": True, "unchanged": False, "template": template_by_id(tid)}


# --- shablon bloklari: uid «tp<kalit><nn><hex4>» (kurs._UID_RX ga mos) ------------------------------------------------------------
_TPL_RX = re.compile(r"^tp([a-z]{2,14})(\d{2})[0-9a-f]{4}$")
QUIZ_LESSON_PREFIX = "tpquiz"

def tpl_uid(key: str, n: int = 0) -> str: return f"tp{key}{n % 100:02d}{secrets.token_hex(2)}"
def tpl_key(uid: str) -> str | None:
    m = _TPL_RX.match(str(uid or ""))
    return m[1] if m else None

def _clean(t: str, d: dict) -> dict: return KU.clean_block(t, d, KU._Assets(None))

def placeholder(item: dict, heading: str = "") -> list[tuple[str, dict]]:
    """Shablon bandi uchun bo'sh (to'ldirilishi kerak) bloklar. Video / ro'yxat kabi bo'sh bloklar «xato» beradi — to'ldirilmaguncha eksport bo'lmaydi."""
    k = item["kind"]
    if k == "section": return [("heading", {"text": item.get("text") or "BO'LIM", "level": 2})]
    if k == "continue": return [("continue", {"label": KU.LABELS["continue"], "require": "none"})]
    if k == "divider": return [("divider", {"style": "line"})]
    if k == "cover": return [("heading", {"text": heading or "Dars", "level": 2})]
    if k == "video": return [("video", {"source": "youtube"})]
    if k == "plan": return [("list", {"style": "numbered", "items": [""]})]
    if k == "text": return [("paragraph", {"html": ""})]
    if k == "keypoints": return [("list", {"style": "bulleted", "items": [""]})]
    if k == "refs": return [("list", {"style": "numbered", "items": [""]})]
    if k == "slides": return [("gallery", {"style": "carousel", "items": []})]
    if k == "files": return [("attachment", {"title": "Qo'shimcha fayl"})]
    if k == "flashcards": return [("flashcards", {"style": "grid", "cards": [{"front": "", "back": ""}, {"front": "", "back": ""}]})]
    if k == "exercises": return [("matching", {"title": "Mos juftlarni toping", "pairs": [{"left": "", "right": ""}, {"left": "", "right": ""}]})]
    if k == "assignment": return [("heading_paragraph", {"heading": PK.ASSIGNMENT["title"], "html": f"<p>{html.escape(PK.ASSIGNMENT['text'])}</p>"})]
    if k == "reflect": return [("heading_paragraph", {"heading": PK.REFLECT["title"], "html": f"<p>{html.escape(PK.REFLECT['question'])}</p>"}),
                               ("list", {"style": "checkbox", "items": [html.escape(o["text"]) for o in PK.REFLECT["options"]]})]
    return []

def _items(layout: dict, lt: str) -> list[dict]:
    return list((layout or {}).get(lt) or DEFAULT_LAYOUT[lt])

def _same(a: dict, b: dict) -> bool: return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)

def reapply(blocks: list[dict], old_items: list[dict], new_items: list[dict], heading: str = "") -> tuple[list[dict], dict]:
    """Shablonni qayta qo'llash (sof funksiya, bazasiz). blocks — [{"id", "type", "data"}] (darsning hozirgi bloklari, tozalangan).
    Qoidalar: muallif bloklari (uid shablonniki emas) o'z «langari» (oldidagi eng yaqin shablon bandi) bilan birga ko'chadi, mazmuni o'zgarmaydi;
    shablon bandi qolgan bo'lsa — mazmuni saqlanadi (statik band — sarlavha/ajratgich — matni shablondan yangilanadi); yangi band — bo'sh blok
    qo'shiladi; olib tashlangan band — bo'sh (o'zgartirilmagan) bo'lsa o'chiriladi, muallif to'ldirgan bo'lsa MUALLIF blokiga aylanadi (yo'qolmaydi).
    → (yangi bloklar, farq {added, removed, updated, kept, moved, author, detached, quiz: "add"|"remove"|None, changed})."""
    old_keys = [x["key"] for x in old_items]
    new_by = {x["key"]: x for x in new_items}
    old_by = {x["key"]: x for x in old_items}
    groups, order, anchors = {}, [], {}            # shablon bandi → bloklar; bandlarning hozirgi tartibi; langar → muallif bloklari
    cur = None
    diff = {"added": 0, "removed": 0, "updated": 0, "kept": 0, "moved": 0, "author": 0, "detached": 0, "quiz": None}
    for b in blocks:
        k = tpl_key(b["id"])
        if k is not None:
            if k not in groups: order.append(k)
            groups.setdefault(k, []).append(b); cur = k
        else:
            anchors.setdefault(cur, []).append(b); diff["author"] += 1
    # olib tashlangan bandlar: bo'sh bo'lsa — o'chadi; mazmunli — muallif blokiga (langari — o'z o'rni)
    for k in list(order):
        if k in new_by: continue
        item = old_by.get(k) or {"kind": "section" if k.startswith("sec") else k, "key": k}
        ph = [(t, _clean(t, d)) for t, d in placeholder(item, heading)]
        keep = []
        for i, b in enumerate(groups[k]):
            empty = i < len(ph) and b["type"] == ph[i][0] and _same(b["data"], ph[i][1])
            if item.get("kind") in STATIC or empty: diff["removed"] += 1
            else:
                keep.append({"id": KU._uid(), "type": b["type"], "data": b["data"]}); diff["detached"] += 1
        anchors.setdefault(k, [])[:0] = keep        # o'z langari ostida, shu langardagi muallif bloklaridan oldin
    # langari yo'qolgan muallif bloklari — eski tartibdagi eng yaqin saqlangan oldingi bandga
    def resolve(k):
        while k is not None and k not in new_by:
            i = order.index(k) if k in order else -1
            k = order[i - 1] if i > 0 else None
        return k
    moved_anchor = {}
    for k in list(anchors):
        r = resolve(k)
        if r != k: moved_anchor.setdefault(r, []).extend(anchors.pop(k))
    for r, bl in moved_anchor.items(): anchors.setdefault(r, []).extend(bl)
    out = list(anchors.get(None, []))
    kept_order = []
    for item in new_items:
        k = item["key"]
        if item["kind"] == "quiz": continue
        if k in groups:
            kept_order.append(k)
            if item["kind"] in STATIC:
                ph = placeholder(item, heading)
                for i, b in enumerate(groups[k]):
                    if i < len(ph):
                        nd = _clean(ph[i][0], ph[i][1])
                        if b["type"] != ph[i][0] or not _same(b["data"], nd): diff["updated"] += 1
                        out.append({"id": b["id"], "type": ph[i][0], "data": nd})
                    else: diff["removed"] += 1
            else:
                out.extend(groups[k]); diff["kept"] += len(groups[k])
        elif k not in old_keys:
            for i, (t, d) in enumerate(placeholder(item, heading)):
                out.append({"id": tpl_uid(k, i), "type": t, "data": _clean(t, d)}); diff["added"] += 1
        out.extend(anchors.get(k, []))
    prev = [k for k in order if k in kept_order]
    diff["moved"] = sum(1 for a, b in zip(prev, kept_order) if a != b)
    was_q, now_q = any(x["kind"] == "quiz" for x in old_items), any(x["kind"] == "quiz" for x in new_items)
    diff["quiz"] = "add" if now_q and not was_q else "remove" if was_q and not now_q else None
    diff["changed"] = bool(diff["added"] or diff["removed"] or diff["updated"] or diff["moved"] or diff["detached"] or diff["quiz"]
                           or [b["id"] for b in out] != [b["id"] for b in blocks])
    return out, diff


# =============================================================================================
# 2. Paket → Kurs muharriri (bloklar) — muqova, video, reja, matn (rasm/jadval), xulosalar, slaydlar, mashqlar, test, o'z-o'zini baholash
# =============================================================================================
def split_html(h: str) -> list[dict]:
    """Tozalangan ma'ruza HTML'i → yuqori darajadagi qismlar: {"t": "h2"|"h3", "text"} | {"t": "fig", "src", "caption"} |
    {"t": "table", "rows", "caption"} | {"t": "html", "html"} (ketma-ket p/ul/ol/blockquote/h4 birlashtiriladi)."""
    from lxml import html as LH
    out, buf = [], []
    def flush():
        if buf: out.append({"t": "html", "html": "".join(buf)}); buf.clear()
    if not (h or "").strip(): return out
    try: els = LH.fragments_fromstring(h)
    except Exception: return [{"t": "html", "html": h}]
    for el in els:
        if isinstance(el, str):
            if el.strip(): buf.append(f"<p>{html.escape(el.strip())}</p>")
            continue
        tag = (el.tag or "").lower() if isinstance(el.tag, str) else ""
        if tag in ("h2", "h3"):
            flush(); out.append({"t": tag, "text": re.sub(r"\s+", " ", el.text_content()).strip()})
        elif tag == "figure":
            flush()
            img = el.find(".//img")
            cap = el.find(".//figcaption")
            out.append({"t": "fig", "src": img.get("src") if img is not None else "", "alt": img.get("alt") if img is not None else "",
                        "caption": re.sub(r"\s+", " ", cap.text_content()).strip() if cap is not None else ""})
        elif tag == "table":
            flush()
            rows = [[re.sub(r"\s+", " ", td.text_content()).strip() for td in tr if isinstance(td.tag, str) and td.tag.lower() in ("td", "th")] for tr in el.iter("tr")]
            cap = el.find(".//caption")
            out.append({"t": "table", "rows": [r for r in rows if r], "caption": cap.text_content().strip() if cap is not None else "",
                        "header": el.find(".//th") is not None or el.find(".//thead") is not None})
        else:
            buf.append(LH.tostring(el, encoding="unicode", with_tail=False))
        tail = el.tail if not isinstance(el, str) else None
        if tail and tail.strip(): buf.append(f"<p>{html.escape(tail.strip())}</p>")
    flush()
    return out

def _chunk_html(h: str, n: int = 15000) -> list[str]:
    """Juda uzun HTML (kurs.MAX_HTML) — paragraf chegarasida bo'laklarga."""
    if len(h) <= n: return [h]
    parts = re.split(r"(?<=</p>)|(?<=</ul>)|(?<=</ol>)|(?<=</blockquote>)", h)
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) > n: out.append(cur); cur = ""
        cur += p
    if cur: out.append(cur)
    return out

class _Copier:
    """Paket fayllari → kurs fayllari (ku_assets). Bir xil manba bir marta ko'chiriladi."""
    def __init__(self, c: Ctx | None, kcid: int, files: dict):
        self.c, self.kcid, self.files, self.done = c, kcid, files, {}
    def _src(self, rel):
        v = self.files.get(rel)
        if v is None: return None
        if isinstance(v, PK.BigFile): return Path(v.path)
        return v if isinstance(v, (bytes, bytearray)) else Path(v)
    def image(self, rel: str, name: str = "") -> int | None:
        if rel in self.done: return self.done[rel]
        src = self._src(rel)
        if src is None: return None
        try:
            raw = bytes(src) if isinstance(src, (bytes, bytearray)) else src.read_bytes()
            data, ext, meta = KU.image_from_bytes(raw)
        except Exception:
            return None
        aid = KU._save_asset(self.c, self.kcid, "image", ext, name or Path(rel).name, data=data, meta=meta)
        self.done[rel] = aid; return aid
    def file(self, rel: str, kind: str, name: str = "") -> int | None:
        if rel in self.done: return self.done[rel]
        src = self._src(rel)
        if src is None or (isinstance(src, Path) and not src.is_file()): return None
        ext = Path(rel).suffix.lstrip(".").lower() or "bin"
        if isinstance(src, (bytes, bytearray)):
            aid = KU._save_asset(self.c, self.kcid, kind, ext, name or Path(rel).name, data=bytes(src))
        else:
            tmpd = KU.store() / "tmp"; tmpd.mkdir(parents=True, exist_ok=True)
            tmp = tmpd / f"cp_{secrets.token_hex(6)}.{ext}"
            PK._link_or_copy(src, tmp)
            aid = KU._save_asset(self.c, self.kcid, kind, ext, name or Path(rel).name, tmp=tmp, size=src.stat().st_size, sha=PK._file_sha(src))
        self.done[rel] = aid; return aid

def _p(text: str) -> str: return f"<p>{html.escape(str(text or ''))}</p>"

def blocks_from_gather(g: dict, cp: _Copier | None) -> dict:
    """paket.gather() natijasi → {"slots": {tur: [(blok turi, ma'lumot)]}, "quiz": [savol ma'lumoti], "quiz_settings": {...}, "cover": asset|None,
    "counts": {...}}. cp=None — fayllarsiz (sinov: faqat tuzilma)."""
    content, files = g["content"], g["files"]
    S, counts = {}, {"figures": 0, "tables": 0, "paragraphs": 0, "slides": 0, "questions": 0, "exercises": 0, "plan": 0, "keypoints": 0}
    add = lambda k, t, d: S.setdefault(k, []).append((t, d))
    les = g["lesson"]
    heading = PK._lesson_heading(les)
    cover = None
    if content.get("cover"):
        add("cover", "heading", {"text": heading, "level": 2})
        if content["cover"].get("image") and cp: cover = cp.image(content["cover"]["image"], "muqova.jpg")
        if cover: add("cover", "image", {"asset": cover, "alt": f"Dars muqovasi: {les['title']}"[:300], "layout": "hero"})
    quiz, qset = [], None
    for b in content["blocks"]:
        t = b["type"]
        if t == "video":
            if b.get("provider") == "youtube":
                add("video", "video", {"source": "youtube", "youtube": b.get("url") or f"https://youtu.be/{b['video_id']}", "title": b.get("title") or "Videodars"})
            else:
                aid = cp.file(b["src"], "video") if cp else None
                caps = [{"asset": cp.file(x["src"], "vtt", f"subtitr.{x['lang']}.vtt"), "lang": x["lang"], "label": x["label"]} for x in b.get("captions") or []] if cp else []
                add("video", "video", {"source": "file", "asset": aid, "poster": cp.image(b["poster"], "poster.jpg") if cp and b.get("poster") else None,
                                       "captions": caps, "title": b.get("title") or "Videodars"})
        elif t == "text" and b.get("title") == "Videodars":
            add("video", "paragraph", {"html": b["html"]})
        elif t == "plan":
            add("plan", "heading", {"text": b.get("heading") or b.get("title") or "Reja", "level": 2})
            add("plan", "list", {"style": "numbered", "items": [html.escape(x) for x in b["items"]]}); counts["plan"] = len(b["items"])
        elif t == "text":
            for part in split_html(b["html"]):
                if part["t"] in ("h2", "h3"): add("text", "heading", {"text": part["text"], "level": 2 if part["t"] == "h2" else 3})
                elif part["t"] == "fig":
                    aid = cp.image(part["src"]) if cp else None
                    add("text", "image", {"asset": aid, "alt": (part["caption"] or part["alt"] or "Rasm")[:300], "caption": part["caption"], "layout": "centered"})
                    counts["figures"] += 1
                elif part["t"] == "table":
                    add("text", "table", {"header": part["header"], "caption": part["caption"], "rows": part["rows"]}); counts["tables"] += 1
                else:
                    for ch in _chunk_html(part["html"]): add("text", "paragraph", {"html": ch}); counts["paragraphs"] += 1
        elif t == "keypoints":
            add("keypoints", "heading", {"text": b.get("title") or "Asosiy xulosalar", "level": 3})
            add("keypoints", "list", {"style": "bulleted", "items": [html.escape(x) for x in b["items"]]}); counts["keypoints"] = len(b["items"])
        elif t == "refs":
            add("refs", "heading", {"text": b.get("title") or "Foydalanilgan adabiyotlar", "level": 3})
            add("refs", "list", {"style": "numbered", "items": [html.escape(x) for x in b["items"]]})
        elif t == "slides":
            sl = b.get("slides") or []
            imgs = [s for s in sl if s.get("image")]
            if imgs and len(imgs) == len(sl):
                items = []
                for i, s in enumerate(sl, 1):
                    aid = cp.image(s["image"], f"slayd_{i}.jpg") if cp else None
                    items.append({"asset": aid, "alt": (s.get("title") or f"{i}-slayd")[:300], "caption": (s.get("caption") or s.get("title") or f"{i}-slayd")[:300]})
                add("slides", "gallery", {"style": "carousel", "items": items})
            elif sl:
                add("slides", "accordion", {"items": [{"title": (s.get("title") or f"{i}-slayd")[:200],
                                                       "html": "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in s.get("bullets") or []) + "</ul>" if s.get("bullets") else _p(s.get("caption") or "")}
                                                      for i, s in enumerate(sl, 1)]})
            counts["slides"] = len(sl)
            for rel, nm in ((b.get("file"), "Taqdimot (.pptx)"), (b.get("pdf"), "Taqdimot (.pdf)")):
                if rel: add("slides", "attachment", {"asset": cp.file(rel, "file", Path(rel).name) if cp else None, "title": nm})
        elif t == "file":
            add("files", "attachment", {"asset": cp.file(b["href"], "file", Path(b["href"]).name) if cp else None, "title": b.get("title") or "Fayl"})
        elif t == "flashcards":
            add("flashcards", "flashcards", {"style": "grid", "cards": [{"front": x.get("front", ""), "back": x.get("back", "")} for x in b.get("cards") or []]})
        elif t == "quiz":
            qset = {"pass_pct": int(b.get("pass_pct") or 60), "shuffle": bool(b.get("shuffle", True)), "attempts": int(b.get("attempts") or 0)}
            for q in b.get("questions") or []:
                if q["type"] == "match":
                    add("exercises", "matching", {"title": q.get("stem") or "", "pairs": q.get("pairs") or []}); counts["exercises"] += 1
                elif q["type"] == "sort":
                    cats = q.get("categories") or []
                    add("exercises", "sorting", {"title": q.get("stem") or "", "categories": [x.get("title", "") for x in cats],
                                                 "items": [{"text": it.get("text", "") if isinstance(it, dict) else str(it), "cat": ci} for ci, x in enumerate(cats) for it in x.get("items") or []]})
                    counts["exercises"] += 1
                elif q["type"] == "fill":
                    quiz.append({"kind": "fill", "question": q["stem"], "accept": [str(a) for a in q.get("answers") or []], "feedback_correct": q.get("explanation") or ""})
                elif q["type"] == "tf":
                    quiz.append({"kind": "truefalse", "question": q["stem"], "answers": [{"text": KU.TF[0], "correct": 0 in q["correct"]}],
                                 "feedback_correct": q.get("explanation") or ""})
                else:
                    cs = set(q.get("correct") or [])
                    quiz.append({"kind": "multiple" if len(cs) > 1 else "single", "question": q["stem"],
                                 "answers": [{"text": str(o), "correct": i in cs} for i, o in enumerate(q.get("options") or [])], "feedback_correct": q.get("explanation") or ""})
            counts["questions"] = len(quiz)
        elif t == "assignment":
            add("assignment", "heading_paragraph", {"heading": b.get("title") or "Topshiriq", "html": _p(b.get("text"))})
            add("assignment", "list", {"style": "numbered", "items": [html.escape(x) for x in b.get("questions") or []]})
        elif t == "reflect":
            add("reflect", "heading_paragraph", {"heading": b.get("title") or "O'z-o'zini baholash", "html": _p(b.get("question"))})
            add("reflect", "list", {"style": "checkbox", "items": [html.escape(o.get("text", "")) for o in b.get("options") or []]})
    return {"slots": S, "quiz": quiz, "quiz_settings": qset, "cover": cover, "counts": counts}

def assemble(items: list[dict], slots: dict | None, heading: str, fill_empty: bool) -> list[dict]:
    """Shablon tartibi + bandlar mazmuni → darsning bloklari (uid — shablonniki). fill_empty=True — mazmuni yo'q band uchun bo'sh blok (skelet)."""
    out = []
    for item in items:
        if item["kind"] == "quiz": continue
        k = item["key"]
        got = (slots or {}).get(item["kind"]) if item["kind"] not in STATIC else None
        src = got if got else (placeholder(item, heading) if (fill_empty or item["kind"] in STATIC) else [])
        for i, (t, d) in enumerate(src): out.append({"id": tpl_uid(k, i), "type": t, "data": d})
    return out

def _link(dl_cid: int, key: int) -> dict | None:
    r = db.one(_con, "SELECT l.*, k.status ku_status, k.title ku_title, k.rev ku_rev FROM ds_links l JOIN ku_courses k ON k.id=l.ku_course_id "
                     "WHERE l.dl_course_id=? AND l.lkey=? AND k.deleted=0", (int(dl_cid), int(key)))
    return r

def link_of_kurs(kcid: int) -> dict | None:
    r = db.one(_con, "SELECT * FROM ds_links WHERE ku_course_id=?", (int(kcid),))
    if not r: return None
    co = db.one(_con, "SELECT id, subject, direction, course, topics FROM dl_courses WHERE id=?", (r["dl_course_id"],))
    code = PK.lesson_code(r["lkey"])
    return {"dl_course_id": r["dl_course_id"], "lkey": r["lkey"], "code": code, "authority": r["authority"], "src": r["src"],
            "subject": (co or {}).get("subject"), "tpl_id": r["tpl_id"]}

def _write_lesson_blocks(lid: int, blocks: list[dict], A) -> None:
    _con.execute("DELETE FROM ku_blocks WHERE lesson_id=?", (lid,))
    for i, b in enumerate(blocks[:KU.MAX_BLOCKS], 1):
        _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)",
                     (lid, b["id"], i, b["type"], json.dumps(KU.clean_block(b["type"], b["data"], A), ensure_ascii=False)))

def _new_lesson(kcid: int, uid: str, pos: int, ltype: str, title: str, settings: dict | None, by: str) -> int:
    return _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,?,?,?,?,1,?,?)",
                        (kcid, uid, pos, ltype, title[:200], json.dumps(settings or ({**KU.QUIZ} if ltype == "quiz" else {})), _now(), by)).lastrowid

def _create_linked(c: Ctx, co: dict, les: dict, tpl: dict, src: str, built: dict | None = None) -> dict:
    """Bog'langan kurs yaratiladi: asosiy dars (shablon bo'yicha) + (shablonda bo'lsa) yakuniy test darsi. built — blocks_from_gather natijasi."""
    lt = ltype_of(les["kind"])
    items = _items(tpl["layout"], lt)
    heading = PK._lesson_heading(les)
    title = f"{les['code']}. {les['title']}"
    kcid = KU.create_course(c, title, f"<p>{html.escape(co.get('subject') or '')}</p>", dl_course_id=co["id"], src="dars", first_lesson=False)["id"]
    if built is None: built = {"slots": {}, "quiz": [], "quiz_settings": None, "cover": None, "counts": {}}
    elif callable(built): built = built(kcid)
    blocks = assemble(items, built["slots"], heading, fill_empty=src == "skelet")
    with KU._lock:
        A = KU._Assets(kcid)
        lid = _new_lesson(kcid, KU._uid("l"), 1, "blocks", les["title"] or les["code"], None, c.user["full_name"])
        _write_lesson_blocks(lid, blocks, A)
        qlid = None
        if any(x["kind"] == "quiz" for x in items) and (src == "skelet" or built["quiz"]):
            qs = {**KU.QUIZ, **{k: v for k, v in (built.get("quiz_settings") or {}).items() if k in KU.QUIZ}}
            qlid = _new_lesson(kcid, QUIZ_LESSON_PREFIX + secrets.token_hex(3), 2, "quiz", "Yakuniy test", KU.clean_quiz(qs), c.user["full_name"])
            _write_lesson_blocks(qlid, [{"id": KU._uid(), "type": "question", "data": q} for q in built["quiz"]], A)
        if built.get("cover"): _con.execute("UPDATE ku_courses SET cover_asset=?, cover_alt=? WHERE id=?", (built["cover"], f"Dars muqovasi: {les['title']}"[:300], kcid))
        _con.execute("""INSERT INTO ds_links(dl_course_id,lkey,ku_course_id,authority,tpl_id,src,created_at,created_by,updated_at) VALUES(?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(dl_course_id,lkey) DO UPDATE SET ku_course_id=excluded.ku_course_id, authority=excluded.authority, tpl_id=excluded.tpl_id,
                        src=excluded.src, updated_at=excluded.updated_at""",
                     (co["id"], les["key"], kcid, "kurs" if src != "skelet" else "paket", tpl["id"], src, _now(), c.user["full_name"], _now()))
        KU._log(c, kcid, "Dars tayyorlash", {"paket": "paketdan o'tkazildi", "skelet": "fan shablonidan yaratildi"}.get(src, src) + f" · {les['code']}")
        _con.commit()
    KU.snapshot(c, kcid, "import", f"Dars tayyorlash: {les['code']} ({'paketdan' if src == 'paket' else 'shablondan'})")
    return {"ku_course_id": kcid, "lesson_id": lid, "quiz_lesson_id": qlid, "blocks": len(blocks), "counts": built.get("counts") or {}}

def convert_lesson(c: Ctx, dl_cid: int, key: int) -> dict:
    """«Muharrirda tahrirlash»: avtomatik yig'ilgan dars (paket.gather) → Kurs muharriri kursi. Bog'langan bo'lsa — o'sha kurs qaytadi."""
    co = PK._course(c, dl_cid, write=True); les = PK._check_topic(co, key)
    ex = _link(dl_cid, key)
    if ex: return {"ok": True, "created": False, "ku_course_id": ex["ku_course_id"], "authority": ex["authority"]}
    st = PK.topic_settings(dl_cid, key)[0]
    g = PK.gather(dl_cid, key, co, st, les)
    tpl = template_for(co.get("department_id"))
    r = _create_linked(c, co, les, tpl, "paket", built=lambda kcid: blocks_from_gather(g, _Copier(c, kcid, g["files"])))
    _audit(c, "paket muharrirga o'tkazildi", f"kurs #{dl_cid} · {les['code']} → ku #{r['ku_course_id']} · {r['blocks']} blok")
    return {"ok": True, "created": True, "authority": "kurs", **r}

def set_authority(c: Ctx, dl_cid: int, key: int, authority: str) -> dict:
    PK._course(c, dl_cid, write=True)
    if authority not in ("paket", "kurs"): raise HTTPException(400, "Manba: paket yoki kurs")
    if not _link(dl_cid, key): raise HTTPException(404, "Dars muharrirga o'tkazilmagan")
    with _lock:
        _con.execute("UPDATE ds_links SET authority=?, updated_at=? WHERE dl_course_id=? AND lkey=?", (authority, _now(), dl_cid, key)); _con.commit()
    _audit(c, "eksport manbai", f"kurs #{dl_cid} · {PK.lesson_code(key)} → {authority}")
    return {"ok": True, "authority": authority}


# =============================================================================================
# 3. Fan: NEXTID darslar to'ri, skelet, shablonni qo'llash
# =============================================================================================
def _open_comments(kids: list[int]) -> dict:
    if not kids: return {}
    rows = db.rows(_con, f"""SELECT course_id, COUNT(*) n, SUM(blocking) b FROM ds_comments WHERE status='ochiq' AND deleted=0 AND parent_id IS NULL
                             AND course_id IN ({','.join('?' * len(kids))}) GROUP BY course_id""", tuple(kids))
    return {r["course_id"]: {"open": r["n"], "blocking": r["b"] or 0} for r in rows}

def subject_view(c: Ctx, dl_cid: int) -> dict:
    co = PK._course(c, dl_cid)
    rd, pk = PK.readiness_map([dl_cid]), PK._pkg_map(dl_cid)
    links = {r["lkey"]: r for r in db.rows(_con, "SELECT l.*, k.status ku_status, k.deleted kd FROM ds_links l JOIN ku_courses k ON k.id=l.ku_course_id "
                                                  "WHERE l.dl_course_id=?", (dl_cid,)) if not r["kd"]}
    cm = _open_comments([r["ku_course_id"] for r in links.values()])
    exports = {r["course_id"]: r for r in db.rows(_con, f"""SELECT course_id, MAX(id) id, MAX(ts) ts FROM ku_exports WHERE course_id IN
                                                          ({','.join('?' * len(links)) or 'NULL'}) GROUP BY course_id""", tuple(r["ku_course_id"] for r in links.values()))} if links else {}
    out = []
    for l in PK.lessons(dl_cid, co):
        no = l["key"]; r = rd.get((dl_cid, no)) or {}; p_ = pk.get((dl_cid, no)); ln = links.get(no)
        auth = ln["authority"] if ln else "paket"
        ku_st = ln["ku_status"] if ln else None
        review = (bool(p_ and p_["last"]["status"] == "tayyor") if auth == "paket" else ku_st == "korib_chiqishda")
        approved = (bool(p_ and p_["approved"]) if auth == "paket" else ku_st == "tasdiqlangan")
        out.append({"key": no, "code": l["code"], "kind": l["kind"], "no": l["no"], "title": l["title"], "untitled": l["untitled"], "topic": l.get("topic"),
                    "material": bool(r.get("text") or r.get("slides")), "text": bool(r.get("text")), "slides": bool(r.get("slides")), "video": bool(r.get("video")),
                    "quiz": bool(r.get("quiz") or r.get("exercises")),
                    "package": {"id": p_["last"]["id"], "version": p_["last"]["version"], "status": p_["last"]["status"]} if p_ else None,
                    "export": {"id": exports[ln["ku_course_id"]]["id"], "ts": exports[ln["ku_course_id"]]["ts"]} if ln and ln["ku_course_id"] in exports else None,
                    "review": review, "approved": approved, "authority": auth,
                    "kurs": {"id": ln["ku_course_id"], "status": ku_st, "src": ln["src"], "tpl_id": ln["tpl_id"]} if ln else None,
                    "comments": cm.get(ln["ku_course_id"], {"open": 0, "blocking": 0}) if ln else {"open": 0, "blocking": 0}})
    k = c.role.key
    own = k in DEPT or (k == TEACH and co.get("teacher_id") == PK._teacher_id(c))
    tpl = template_for(co.get("department_id"))
    n = int(co["topics"] or 15)
    return {"course": {"id": co["id"], "subject": co["subject"], "direction": co["direction"], "course": co["course"], "dept": co.get("dept"),
                       "department_id": co.get("department_id"), "teacher": PK._short(co.get("teacher") or ""), "topics": n},
            "lessons": out, "template": {"id": tpl["id"], "version": tpl["version"], "name": tpl["name"], "tkey": tpl["tkey"]},
            "counts": {"L": sum(1 for x in out if x["kind"] == "maruza"), "A": sum(1 for x in out if x["kind"] == "amaliy"), "linked": len(links),
                       "approved": sum(1 for x in out if x["approved"]), "review": sum(1 for x in out if x["review"]),
                       "blocking": sum(x["comments"]["blocking"] for x in out)},
            "can": {"write": own, "approve": k in DEPT, "review": k in REVIEWERS, "template": k in DEPT}, "modes": PK.MODES}

def skeleton(c: Ctx, dl_cid: int, ratio: int = 2, apply: bool = True, with_kurs: bool = True) -> dict:
    """Fan skeleti: L1..Ln (mavzular ro'yxatidan — tasdiqlangan sillabus > kontent monitoringi) + A1..A(ratio·n) (har mavzuga ratio ta amaliy,
    «(N-mavzu)» bog'lanishi bilan) va (with_kurs) har dars uchun kafedra shabloni bo'yicha bloklar. Mavjud nomlar va bog'langan kurslar o'zgarmaydi."""
    co = PK._course(c, dl_cid, write=True)
    try: ratio = int(ratio)
    except (TypeError, ValueError): raise HTTPException(400, "Nisbat butun son bo'lsin")
    if not 0 <= ratio <= 4: raise HTTPException(400, "Har mavzuga amaliy mashg'ulotlar soni 0–4")
    n = int(co["topics"] or 15)
    titles = PK._titles(dl_cid, co.get("subject"))
    plan = [{"code": f"L{i}", "key": i, "kind": "maruza", "title": titles.get(i) or f"{i}-mavzu", "topic": i} for i in range(1, n + 1)]
    for i in range(1, ratio * n + 1):
        t = (i - 1) // ratio + 1
        part = f" ({(i - 1) % ratio + 1}-qism)" if ratio > 1 else ""
        plan.append({"code": f"A{i}", "key": PK.lesson_key("amaliy", i), "kind": "amaliy", "title": (titles.get(t) or f"{t}-mavzu") + part, "topic": t})
    existing = {r["lkey"]: r for r in db.rows(_con, "SELECT * FROM pk_lessons WHERE course_id=?", (dl_cid,))}
    linked = {r["lkey"] for r in db.rows(_con, "SELECT l.lkey FROM ds_links l JOIN ku_courses k ON k.id=l.ku_course_id WHERE l.dl_course_id=? AND k.deleted=0", (dl_cid,))}
    for p in plan:
        e = existing.get(p["key"])
        p["exists"] = p["kind"] == "maruza" or bool(e and not e["deleted"])
        p["linked"] = p["key"] in linked
    res = {"ok": True, "applied": False, "ratio": ratio, "L": n, "A": ratio * n, "plan": plan,
           "new_lessons": sum(1 for p in plan if not p["exists"]), "new_courses": sum(1 for p in plan if not p["linked"]) if with_kurs else 0, "created": 0}
    if not apply: return res
    with PK._lock:
        for p in plan:
            if p["kind"] == "amaliy" and not p["exists"]:
                _con.execute("""INSERT INTO pk_lessons(course_id,lkey,kind,no,title,topic_ref,ts,user_name,deleted,src) VALUES(?,?,?,?,?,?,?,?,0,'skelet')
                                ON CONFLICT(course_id,lkey) DO UPDATE SET deleted=0, ts=excluded.ts, user_name=excluded.user_name""",
                             (dl_cid, p["key"], "amaliy", int(p["code"][1:]), p["title"][:200], p["topic"], _now(), c.user["full_name"]))
        PK._log(c, dl_cid, None, "fan skeleti", f"L{n} + A{ratio * n}"); _con.commit()
    created = 0
    if with_kurs:
        tpl = template_for(co.get("department_id"))
        ls = {l["key"]: l for l in PK.lessons(dl_cid, co)}
        for p in plan:
            if p["linked"] or p["key"] not in ls: continue
            _create_linked(c, co, ls[p["key"]], tpl, "skelet"); created += 1
    res.update(applied=True, created=created)
    _audit(c, "fan skeleti", f"kurs #{dl_cid} · L{n} + A{ratio * n} · {created} ta muharrir kursi")
    return res

def _main_lesson(kcid: int) -> dict | None:
    return db.one(_con, "SELECT * FROM ku_lessons WHERE course_id=? AND deleted=0 AND type='blocks' ORDER BY pos, id LIMIT 1", (kcid,))

def _quiz_lesson(kcid: int) -> dict | None:
    return db.one(_con, "SELECT * FROM ku_lessons WHERE course_id=? AND deleted=0 AND type='quiz' AND uid LIKE ? ORDER BY pos, id LIMIT 1", (kcid, QUIZ_LESSON_PREFIX + "%"))

def apply_template(c: Ctx, dl_cid: int, tpl_id: int | None = None, preview: bool = True) -> dict:
    """«Shablonni qo'llash»: fan darslarining (bog'langan muharrir kurslari) shablon bloklari yangi shablonga moslanadi — muallif bloklari va mazmuni
    saqlanadi. preview=True — faqat farq (har dars + jami); aks holda har kurs oldin versiyaga saqlanadi va yoziladi."""
    co = PK._course(c, dl_cid, write=True)
    new = template_by_id(tpl_id) if tpl_id else template_for(co.get("department_id"))
    if not new: raise HTTPException(404, "Shablon topilmadi")
    if new["tkey"] not in ("global", f"dep:{int(co.get('department_id') or 0)}"): raise HTTPException(400, "Bu shablon boshqa kafedraniki")
    ls = {l["key"]: l for l in PK.lessons(dl_cid, co)}
    links = db.rows(_con, "SELECT l.* FROM ds_links l JOIN ku_courses k ON k.id=l.ku_course_id WHERE l.dl_course_id=? AND k.deleted=0 ORDER BY l.lkey", (dl_cid,))
    tot = {"lessons": 0, "changed": 0, "added": 0, "removed": 0, "updated": 0, "kept": 0, "moved": 0, "author": 0, "detached": 0, "quiz_add": 0, "quiz_remove": 0}
    rows = []
    for ln in links:
        les = ls.get(ln["lkey"])
        if not les: continue
        lt = ltype_of(les["kind"])
        old = template_by_id(ln["tpl_id"]) or {"layout": DEFAULT_LAYOUT}
        main = _main_lesson(ln["ku_course_id"])
        if not main: continue
        cur = KU._blocks(main["id"])
        heading = PK._lesson_heading(les)
        nb, diff = reapply(cur, _items(old["layout"], lt), _items(new["layout"], lt), heading)
        tot["lessons"] += 1; tot["changed"] += bool(diff["changed"] or ln["tpl_id"] != new["id"])
        for k_ in ("added", "removed", "updated", "kept", "moved", "author", "detached"): tot[k_] += diff[k_]
        if diff["quiz"] == "add": tot["quiz_add"] += 1
        if diff["quiz"] == "remove": tot["quiz_remove"] += 1
        rows.append({"key": les["key"], "code": les["code"], "title": les["title"], "ku_course_id": ln["ku_course_id"], **diff})
        if preview or not (diff["changed"] or ln["tpl_id"] != new["id"]): continue
        kcid = ln["ku_course_id"]
        KU.snapshot(c, kcid, "auto", f"Shablon qo'llashdan oldin (v{new['version']})")
        with KU._lock:
            A = KU._Assets(kcid)
            _write_lesson_blocks(main["id"], nb, A)
            _con.execute("UPDATE ku_lessons SET rev=rev+1, updated_at=?, updated_by=? WHERE id=?", (_now(), c.user["full_name"], main["id"]))
            q = _quiz_lesson(kcid)
            if diff["quiz"] == "add" and not q:
                pos = (db.one(_con, "SELECT MAX(pos) m FROM ku_lessons WHERE course_id=? AND deleted=0", (kcid,)) or {}).get("m") or 1
                _new_lesson(kcid, QUIZ_LESSON_PREFIX + secrets.token_hex(3), pos + 1, "quiz", "Yakuniy test", None, c.user["full_name"])
            elif diff["quiz"] == "remove" and q and not db.one(_con, "SELECT 1 x FROM ku_blocks WHERE lesson_id=?", (q["id"],)):
                _con.execute("UPDATE ku_lessons SET deleted=1 WHERE id=?", (q["id"],))
            _con.execute("UPDATE ds_links SET tpl_id=?, updated_at=? WHERE dl_course_id=? AND lkey=?", (new["id"], _now(), dl_cid, ln["lkey"]))
            KU._bump(kcid, c)
            KU._log(c, kcid, "shablon qo'llandi", f"v{new['version']} · +{diff['added']} −{diff['removed']} ~{diff['updated']} · muallif bloklari {diff['author']}")
            _con.commit()
    if not preview: _audit(c, "shablon qo'llandi", f"kurs #{dl_cid} · shablon #{new['id']} v{new['version']} · {tot['changed']} dars")
    return {"ok": True, "applied": not preview, "template": {"id": new["id"], "version": new["version"], "name": new["name"]}, "total": tot, "lessons": rows}


# =============================================================================================
# 3b. Ommaviy qayta yig'ish / eksport — fon ishi, jarayon ko'rsatiladi; natija: zip ichida zip'lar
# =============================================================================================
_JOBS: dict[int, dict] = {}

def _job_dir() -> Path:
    d = PK.store() / "dars_jobs"; d.mkdir(parents=True, exist_ok=True); return d

def start_bulk(c: Ctx, dl_cid: int, mode: str = "xapi", keys: list | None = None, sync: bool = False) -> dict:
    co = PK._course(c, dl_cid, write=True)
    if mode not in PK.MODES: raise HTTPException(400, "Paket turi noma'lum")
    ls = PK.lessons(dl_cid, co)
    want = {int(k) for k in keys} if keys else None
    ls = [l for l in ls if want is None or l["key"] in want]
    if not ls: raise HTTPException(400, "Darslar yo'q")
    with _lock:
        jid = _con.execute("INSERT INTO ds_jobs(dl_course_id,action,mode,status,total,done,ok,failed,user_id,user_name,ts) VALUES(?,?,?,?,?,0,0,0,?,?,?)",
                           (dl_cid, "bulk", mode, "ishlamoqda", len(ls), c.user["id"], c.user["full_name"], _now())).lastrowid
        _con.commit()
    _JOBS[jid] = {"id": jid, "status": "ishlamoqda", "total": len(ls), "done": 0, "ok": 0, "failed": 0, "current": "", "results": [], "file": None, "user_id": c.user["id"],
                  "dl_course_id": dl_cid}
    _audit(c, "ommaviy yig'ish boshlandi", f"kurs #{dl_cid} · {len(ls)} dars · {mode}")
    if sync: _run_bulk(jid, c, co, ls, mode)
    else: threading.Thread(target=_run_bulk, args=(jid, c, co, ls, mode), daemon=True, name=f"dars-bulk-{jid}").start()
    return job_view(c, jid)

def _run_bulk(jid: int, c: Ctx, co: dict, ls: list, mode: str):
    J = _JOBS[jid]
    files = []
    for l in ls:
        J["current"] = l["code"]
        ln = _link(co["id"], l["key"])
        res = {"key": l["key"], "code": l["code"], "title": l["title"], "source": ln["authority"] if ln else "paket"}
        try:
            if ln and ln["authority"] == "kurs":
                r = KU.export_course(c, ln["ku_course_id"], mode)
                e = db.one(_con, "SELECT file FROM ku_exports WHERE id=?", (r["id"],))
                f = KU.store() / e["file"]
                res.update(ok=bool(r["ok"]), download=r["download"], size=r["size"])
            else:
                r = PK.build_topic(c, co["id"], l["key"], mode, co=co, les=l)
                f = PK.store() / db.one(_con, "SELECT file FROM pk_packages WHERE id=?", (r["package"]["id"],))["file"]
                res.update(ok=True, unchanged=r["unchanged"], version=r["package"]["version"], download=f"{PK.P}/packages/{r['package']['id']}/download", size=r["package"]["size"])
            if f.is_file(): files.append((PK.download_name(co, l["key"], mode), f))
        except HTTPException as e:
            d = e.detail
            res.update(ok=False, error=d if isinstance(d, str) else (d or {}).get("message") or "xato")
        except Exception as e:   # bitta dars xatosi qolganlarini to'xtatmasin
            res.update(ok=False, error=f"Kutilmagan xato: {type(e).__name__}")
        J["results"].append(res); J["done"] += 1
        J["ok" if res.get("ok") else "failed"] += 1
    out = None
    if files:
        out = _job_dir() / f"job_{jid}.zip"
        tmp = out.with_suffix(".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for nm, f in files:
                zi = zipfile.ZipInfo(nm, date_time=PK.FIXED_TS); zi.compress_type = zipfile.ZIP_STORED
                with z.open(zi, "w", force_zip64=True) as w, open(f, "rb") as r_:
                    shutil.copyfileobj(r_, w, 1024 * 1024)
        os.replace(tmp, out)
    J.update(status="tayyor", current="", file=str(out) if out else None)
    try:
        with _lock:
            _con.execute("UPDATE ds_jobs SET status=?, done=?, ok=?, failed=?, result=?, file=?, finished_at=? WHERE id=?",
                         ("tayyor", J["done"], J["ok"], J["failed"], json.dumps(J["results"], ensure_ascii=False), J["file"], _now(), jid))
            _con.commit()
    except Exception as e:
        print("dars job:", repr(e))

def job_view(c: Ctx, jid: int) -> dict:
    J = _JOBS.get(int(jid))
    if not J:
        r = db.one(_con, "SELECT * FROM ds_jobs WHERE id=?", (int(jid),))
        if not r: raise HTTPException(404, "Ish topilmadi")
        J = {"id": r["id"], "status": r["status"] if r["finished_at"] else "uzildi", "total": r["total"], "done": r["done"], "ok": r["ok"], "failed": r["failed"],
             "current": "", "results": _j(r["result"], []), "file": r["file"], "user_id": r["user_id"], "dl_course_id": r["dl_course_id"]}
    PK._course(c, J["dl_course_id"])
    if J["user_id"] != c.user["id"] and c.role.key not in DEPT: raise AccessDenied("⛔ Bu ish sizniki emas")
    return {k: J[k] for k in ("id", "status", "total", "done", "ok", "failed", "current", "results")} | {
        "pct": round(100 * J["done"] / J["total"]) if J["total"] else 100, "download": f"{P}/jobs/{J['id']}/download" if J.get("file") else None}

def job_file(c: Ctx, jid: int) -> FileResponse:
    v = job_view(c, jid)
    J = _JOBS.get(int(jid)) or {"file": (db.one(_con, "SELECT file FROM ds_jobs WHERE id=?", (int(jid),)) or {}).get("file")}
    if not v["download"] or not J.get("file") or not Path(J["file"]).is_file(): raise HTTPException(410, "Fayl tayyor emas yoki eskirgan")
    dl = J.get("dl_course_id") or (db.one(_con, "SELECT dl_course_id FROM ds_jobs WHERE id=?", (int(jid),)) or {}).get("dl_course_id")
    co = db.one(_con, "SELECT subject FROM dl_courses WHERE id=?", (dl,)) or {"subject": "fan"}
    _audit(c, "ommaviy zip yuklab olindi", f"ish #{jid}")
    return FileResponse(J["file"], media_type="application/zip", filename=f"ISFT_{PK._ascii(co['subject'], 50)}_darslar.zip")


# =============================================================================================
# 4. Izohlar (ko'rib chiqish) — blokka biriktirilgan, tarmoqli; to'xtatuvchi izohlar tasdiqni to'xtatadi
# =============================================================================================
MAX_COMMENT = 2000

def _ku_course(c: Ctx, kcid: int) -> dict:
    return KU._course(c, kcid)

def _can_review(c: Ctx, co: dict) -> bool:
    return c.role.key in DEPT or (c.role.key == KAF and bool(co.get("dl_course_id")) and bool(db.one(
        _con, "SELECT 1 x FROM dl_courses WHERE id=? AND department_id=?", (co["dl_course_id"], int(c.user.get("department_id") or 0)))))

def _is_author(c: Ctx, co: dict) -> bool:
    if c.role.key != TEACH: return False
    if co["author_id"] == c.user["id"]: return True
    return bool(co.get("dl_course_id") and db.one(_con, "SELECT 1 x FROM dl_courses WHERE id=? AND teacher_id=? AND teacher_id>0", (co["dl_course_id"], PK._teacher_id(c))))

def comments(c: Ctx, kcid: int) -> dict:
    co = _ku_course(c, kcid)
    rows = db.rows(_con, "SELECT * FROM ds_comments WHERE course_id=? AND deleted=0 ORDER BY id", (kcid,))
    th, by = [], {}
    for r in rows:
        x = {"id": r["id"], "lesson_id": r["lesson_id"], "block_uid": r["block_uid"], "user": r["user_name"], "role": r["role"], "text": r["text"],
             "blocking": bool(r["blocking"]), "mention_author": bool(r["mention_author"]), "status": r["status"], "ts": r["ts"],
             "resolved_by": r["resolved_by"], "resolved_at": r["resolved_at"], "mine": r["user_id"] == c.user["id"], "replies": []}
        by[r["id"]] = x
        if r["parent_id"] and r["parent_id"] in by: by[r["parent_id"]]["replies"].append(x)
        else: th.append(x)
    rv = _can_review(c, co)
    return {"items": th, "open": sum(1 for t in th if t["status"] == "ochiq"), "blocking": sum(1 for t in th if t["status"] == "ochiq" and t["blocking"]),
            "by_block": {u: sum(1 for t in th if t["block_uid"] == u and t["status"] == "ochiq") for u in {t["block_uid"] for t in th}},
            "can": {"comment": rv or _is_author(c, co) or c.role.key in DEPT, "blocking": rv, "resolve_blocking": rv}}

def add_comment(c: Ctx, kcid: int, body: dict) -> dict:
    co = _ku_course(c, kcid)
    rv, au = _can_review(c, co), _is_author(c, co)
    if not (rv or au):
        rbac.audit(_con, c, "dars: izoh rad etildi", RES, False, f"ku #{kcid}")
        raise AccessDenied("⛔ Izohni faqat ko'rib chiquvchi (bo'lim, kafedra) yoki kurs muallifi qoldiradi.")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(body.get("text") or "")).strip()[:MAX_COMMENT]
    if len(text) < 2: raise HTTPException(400, "Izoh matnini yozing")
    parent = body.get("parent_id")
    if parent:
        pr = db.one(_con, "SELECT * FROM ds_comments WHERE id=? AND course_id=? AND deleted=0 AND parent_id IS NULL", (int(parent), kcid))
        if not pr: raise HTTPException(404, "Izoh topilmadi")
        lid, buid, blocking, mention = pr["lesson_id"], pr["block_uid"], 0, 0
    else:
        lid = int(body.get("lesson_id") or 0)
        if not db.one(_con, "SELECT 1 x FROM ku_lessons WHERE id=? AND course_id=? AND deleted=0", (lid, kcid)): raise HTTPException(400, "Dars topilmadi")
        buid = str(body.get("block_uid") or "")
        if buid and not db.one(_con, "SELECT 1 x FROM ku_blocks WHERE lesson_id=? AND uid=?", (lid, buid)): raise HTTPException(400, "Blok topilmadi (dars saqlanganini tekshiring)")
        blocking = 1 if body.get("blocking") else 0
        if blocking and not rv: raise AccessDenied("⛔ To'xtatuvchi izohni faqat ko'rib chiquvchi (bo'lim, kafedra) qo'yadi.")
        mention = 1 if body.get("mention_author") else 0
    with _lock:
        cid_ = _con.execute("INSERT INTO ds_comments(course_id,lesson_id,block_uid,parent_id,user_id,user_name,role,text,blocking,mention_author,status,ts) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,'ochiq',?)", (kcid, lid, buid, int(parent) if parent else None, c.user["id"], c.user["full_name"],
                                                                        c.role.key, text, blocking, mention, _now())).lastrowid
        if parent: _con.execute("UPDATE ds_comments SET status='ochiq', resolved_by=NULL, resolved_at=NULL WHERE id=? AND status='ochiq'", (int(parent),))
        KU._log(c, kcid, "izoh" + (" (to'xtatuvchi)" if blocking else ""), text[:120]); _con.commit()
    _audit(c, "izoh qo'shildi", f"ku #{kcid} · #{cid_}{' · to`xtatuvchi' if blocking else ''}{' · muallif eslatildi' if mention else ''}".replace("`", "'"))
    return {"ok": True, "id": cid_, **comments(c, kcid)}

def set_comment_status(c: Ctx, comment_id: int, resolve: bool) -> dict:
    r = db.one(_con, "SELECT * FROM ds_comments WHERE id=? AND deleted=0 AND parent_id IS NULL", (int(comment_id),))
    if not r: raise HTTPException(404, "Izoh topilmadi")
    co = _ku_course(c, r["course_id"])
    rv = _can_review(c, co)
    if not (rv or (not r["blocking"] and (_is_author(c, co) or r["user_id"] == c.user["id"]))):
        rbac.audit(_con, c, "dars: izoh holati rad etildi", RES, False, f"#{comment_id}")
        raise AccessDenied("⛔ To'xtatuvchi izohni faqat ko'rib chiquvchi (bo'lim, kafedra) hal qiladi yoki qayta ochadi.")
    with _lock:
        if resolve: _con.execute("UPDATE ds_comments SET status='hal', resolved_by=?, resolved_at=? WHERE id=?", (c.user["full_name"], _now(), r["id"]))
        else: _con.execute("UPDATE ds_comments SET status='ochiq', resolved_by=NULL, resolved_at=NULL WHERE id=?", (r["id"],))
        KU._log(c, r["course_id"], "izoh hal qilindi" if resolve else "izoh qayta ochildi", f"#{r['id']}"); _con.commit()
    _audit(c, "izoh hal qilindi" if resolve else "izoh qayta ochildi", f"ku #{r['course_id']} · #{r['id']}")
    return {"ok": True, **comments(c, r["course_id"])}

def blocking_open(kcid: int) -> int:
    return (db.one(_con, "SELECT COUNT(*) n FROM ds_comments WHERE course_id=? AND status='ochiq' AND blocking=1 AND deleted=0 AND parent_id IS NULL",
                   (int(kcid),)) or {}).get("n") or 0

def gate(c: Ctx, kcid: int, action: str, override: str = "") -> int:
    """Ko'rib chiqishga yuborish / tasdiqlash: ochiq to'xtatuvchi izohlar 0 bo'lishi kerak. override (sabab, ≥ 10 belgi) — o'tkaziladi, audit +
    ds_overrides. → ochiq to'xtatuvchi izohlar soni (o'tkazilganda)."""
    try: n = blocking_open(kcid)
    except Exception: return 0      # jadval yo'q (eski baza) — to'siq yo'q
    if not n: return 0
    reason = re.sub(r"\s+", " ", str(override or "")).strip()
    if len(reason) < 10:
        raise HTTPException(409, {"message": f"{n} ta ochiq to'xtatuvchi izoh bor — avval hal qiling yoki sababini yozib aylanib o'ting (kamida 10 belgi)",
                                  "blocking": n, "gate": True})
    with _lock:
        _con.execute("INSERT INTO ds_overrides(course_id,kind,action,reason,open_blocking,user_id,user_name,ts) VALUES(?,?,?,?,?,?,?,?)",
                     (int(kcid), "izoh", action, reason[:500], n, c.user["id"], c.user["full_name"], _now()))
        KU._log(c, kcid, "izohlar to'sig'i aylanib o'tildi", f"{action} · {n} ta · {reason[:200]}"); _con.commit()
    rbac.audit(_con, c, "dars: izohlar to'sig'i aylanib o'tildi", RES, True, f"ku #{kcid} · {action} · {n} ta ochiq · sabab: {reason[:120]}")
    return n

def gate_package(c: Ctx, dl_cid: int, key: int, action: str, override: str = "") -> int:
    """Paket (shablon bo'yicha yig'ilgan) darsi muharrirga bog'langan bo'lsa — o'sha kursdagi to'xtatuvchi izohlar ham to'sadi."""
    try: ln = _link(dl_cid, key)
    except Exception: return 0
    return gate(c, ln["ku_course_id"], f"paket {action}", override) if ln else 0

def pending_items(c: Ctx) -> list[dict]:
    """«Mening vazifalarim» / qo'ng'iroqcha: o'qituvchiga — o'z kurslaridagi ochiq to'xtatuvchi yoki o'zini eslatgan izohlar;
    bo'limga — muallif javob bergan (oxirgi yozuv muallifniki) ochiq to'xtatuvchi izohlar."""
    k, out = c.role.key, []
    if k == TEACH:
        sw, sa = KU.scope(c)
        r = db.one(_con, f"""SELECT COUNT(*) n, SUM(m.blocking) b, COUNT(DISTINCT m.course_id) nc FROM ds_comments m JOIN ku_courses k ON k.id=m.course_id
                             WHERE m.status='ochiq' AND m.deleted=0 AND m.parent_id IS NULL AND (m.blocking=1 OR m.mention_author=1) AND k.deleted=0 AND {sw}""", sa)
        if r and r["n"]:
            out.append({"id": "izohlar", "kind": "ish", "title": f"Dars tayyorlash: ko'rib chiquvchi izohlari — {r['n']} ta" + (f" ({r['b']} ta to'xtatuvchi)" if r["b"] else ""),
                        "sub": f"{r['nc']} ta darsda · muharrirda «Izohlar» panelini oching", "view": "kurs"})
    elif k in DEPT:
        r = db.one(_con, """SELECT COUNT(*) n FROM ds_comments m WHERE m.status='ochiq' AND m.blocking=1 AND m.deleted=0 AND m.parent_id IS NULL
                            AND EXISTS(SELECT 1 FROM ds_comments x WHERE x.parent_id=m.id AND x.deleted=0 AND x.role='oqituvchi'
                                       AND x.id=(SELECT MAX(id) FROM ds_comments y WHERE y.parent_id=m.id AND y.deleted=0))""")
        if r and r["n"]:
            out.append({"id": "izoh_javob", "kind": "ish", "title": f"Dars tayyorlash: muallif javob bergan to'xtatuvchi izohlar — {r['n']} ta",
                        "sub": "tekshirib, hal qiling yoki qayta oching", "view": "paket"})
    return out


# =============================================================================================
# 5. AI: hujjatdan dars — sof tekshiruvlar (deterministik, testlangan) + Claude chaqiruvi
# =============================================================================================
_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i",
        "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h"}
_VOW = set("аеёиоуэюяўы")
_CYR_RX = re.compile(r"[Ѐ-ӿ]")

def has_cyrillic(s: str) -> bool: return bool(_CYR_RX.search(s or ""))

def translit(s: str) -> str:
    """O'zbek kirill → lotin (rasmiy qoidalar): ш → sh, ч → ch, ғ → g', ў → o', қ → q, ҳ → h, ё/ю/я → yo/yu/ya, е — so'z boshida va unli/ъ/ь
    dan keyin «ye», aks holda «e»; ц → ts; ь — tushiriladi. Katta harf: «Ш» → «Sh» (keyingi harf ham katta bo'lsa — «SH»)."""
    s = str(s or "")
    if not has_cyrillic(s): return s
    out = []
    for i, ch in enumerate(s):
        low = ch.lower()
        prev = s[i - 1].lower() if i > 0 else ""
        if low == "е":
            v = "ye" if (not prev or not prev.isalpha() or prev in _VOW or prev in "ъь") else "e"
        elif low in _CYR:
            v = _CYR[low]
        else:
            out.append(ch); continue
        if ch != low and v:
            nxt = s[i + 1] if i + 1 < len(s) else ""
            pv = s[i - 1] if i > 0 else ""
            v = v.upper() if len(v) > 1 and ((nxt.isalpha() and nxt.isupper()) or (pv.isalpha() and pv.isupper() and not nxt.isalpha())) else v[0].upper() + v[1:]
        out.append(v)
    return "".join(out)

_EN_STOP = {"the", "and", "of", "is", "are", "to", "in", "for", "with", "this", "that", "on", "by", "as", "be", "an", "it", "from", "which", "or",
            "was", "were", "has", "have", "can", "will", "these", "those", "their", "its", "at", "not", "but", "into", "also", "such", "between"}

def is_english(s: str) -> bool:
    """Inglizcha qoldiq: kamida 4 so'z va ulardan ≥ 25 % — inglizcha yordamchi so'zlar."""
    ws = re.findall(r"[A-Za-z']+", str(s or "").lower())
    if len(ws) < 4: return False
    return sum(1 for w in ws if w in _EN_STOP) / len(ws) >= 0.25

def fix_text(s: str) -> str:
    return re.sub(r"\s+", " ", translit(str(s or ""))).strip()

_NUM_RX = re.compile(r"\d+(?:[.,]\d+)?")

def numbers_ok(text: str, source: str) -> bool:
    """Paragrafdagi har bir son manbada ham bor (o'ylab topilgan raqam yo'q)."""
    src = {n.replace(",", ".") for n in _NUM_RX.findall(source or "")}
    return all(n.replace(",", ".") in src for n in _NUM_RX.findall(text or ""))

def cited(text: str, quote: str, source: str) -> bool:
    """Paragraf manbaga tayanadi: iqtibos manbada aynan bor (testbank._quote_in) va paragrafdagi raqamlar manbada uchraydi."""
    from . import testbank as TB
    q = re.sub(r"\s+", " ", str(quote or "")).strip()
    return bool(q) and len(q) >= 12 and TB._quote_in(q, source) and numbers_ok(text, source)

def correct_longest(q: dict) -> bool:
    """To'g'ri javob boshqa barcha variantlardan qat'iy uzunroq."""
    a = q["answers"]
    ci = next((i for i, x in enumerate(a) if x["correct"]), None)
    if ci is None or len(a) < 2: return False
    lc = len(a[ci]["text"])
    return all(lc > len(x["text"]) for i, x in enumerate(a) if i != ci)

def balance(questions: list[dict], seed: str = "") -> list[dict]:
    """To'g'ri javob o'rinlari teng taqsimlanadi (aylanma: k-savol → k mod n o'rni; tartib — seed bo'yicha deterministik aralash),
    chalg'ituvchilar ham deterministik aralashtiriladi. Savollar joyida o'zgaradi va qaytariladi."""
    import random as _r
    order = list(range(len(questions)))
    _r.Random(hashlib.sha256(("o:" + seed).encode()).hexdigest()).shuffle(order)
    for k, qi in enumerate(order):
        q = questions[qi]
        a = q["answers"]
        if len(a) < 2: continue
        ci = next((i for i, x in enumerate(a) if x["correct"]), 0)
        rest = [x for i, x in enumerate(a) if i != ci]
        _r.Random(hashlib.sha256(f"{seed}:{qi}:{q['question']}".encode()).hexdigest()).shuffle(rest)
        t = k % len(a)
        q["answers"] = rest[:t] + [a[ci]] + rest[t:]
    return questions

def positions(questions: list[dict]) -> dict:
    out = {}
    for q in questions:
        ci = next((i for i, x in enumerate(q["answers"]) if x["correct"]), None)
        if ci is not None: out["ABCDEF"[ci]] = out.get("ABCDEF"[ci], 0) + 1
    return dict(sorted(out.items()))

class GuardError(Exception):
    pass

_Q = {"type": "object", "additionalProperties": False, "required": ["sid", "question", "options", "correct_index", "explanation", "quote"],
      "properties": {"sid": {"type": "string"}, "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
                     "correct_index": {"type": "integer"}, "explanation": {"type": "string"}, "quote": {"type": "string"}}}
_TQ = {"type": "object", "additionalProperties": False, "required": ["title", "text", "quote"],
       "properties": {"title": {"type": "string"}, "text": {"type": "string"}, "quote": {"type": "string"}}}
AI_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title", "sections", "flashcards", "quiz"], "properties": {
    "title": {"type": "string"},
    "sections": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["sid", "paragraphs", "interactive", "checks"], "properties": {
        "sid": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "quote"],
                                                  "properties": {"text": {"type": "string"}, "quote": {"type": "string"}}}},
        "interactive": {"type": "object", "additionalProperties": False, "required": ["kind", "items"],
                        "properties": {"kind": {"type": "string", "enum": ["none", "accordion", "tabs"]}, "items": {"type": "array", "items": _TQ}}},
        "checks": {"type": "array", "items": _Q}}}},
    "flashcards": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["term", "definition", "quote"],
                                              "properties": {"term": {"type": "string"}, "definition": {"type": "string"}, "quote": {"type": "string"}}}},
    "quiz": {"type": "array", "items": _Q}}}
COVER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["questions"], "properties": {"questions": {"type": "array", "items": _Q}}}
DISTRACT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["id", "distractors"],
    "properties": {"id": {"type": "string"}, "distractors": {"type": "array", "items": {"type": "string"}}}}}}}
AI_SYSTEM = ("Siz oliy ta'lim muassasasi uchun ma'ruza matnidan interaktiv onlayn dars tayyorlaydigan metodistsiz. FAQAT berilgan matnga tayaning — "
             "matnda yo'q fakt, raqam, sana, ism yoki ta'rif qo'shmang. Hamma matn o'zbek tilida, LOTIN yozuvida (kirill va inglizcha ishlatmang).\n"
             "Qoidalar: 1) har bir bo'lim (sid — [S1], [S2] …) uchun 1–4 qisqa paragraf: mazmunni aniq, talabaga tushunarli qayta bayon qiling; "
             "har paragraf uchun quote — matndan AYNAN ko'chirilgan jumla yoki uning bo'lagi (≥ 12 belgi, o'zgartirmasdan); "
             "2) interactive — tabiiy bo'lsa (bosqichlar, turlar, taqqoslash) accordion yoki tabs, aks holda kind=none; "
             "3) checks — bo'lim oxirida 0–2 bilimni tekshirish savoli; quiz — yakuniy test, HAR BIR bo'limdan kamida bitta savol (sid ko'rsating); "
             "savolda 4 ta variant, bittasi to'g'ri (correct_index), chalg'ituvchilar ishonarli va to'g'ri javob bilan TAXMINAN BIR XIL UZUNLIKDA; "
             "quote — javob asoslangan jumla matndan aynan; 4) flashcards — matndagi 3–10 ta muhim atama va ta'rifi (quote bilan).")

def _vq(it: dict, sids: set, src: str, stats: dict) -> dict | None:
    """AI savoli → kurs savoli (single) yoki None (tashlanadi): matn lotinga, 3–6 noyob variant, to'g'ri indeks, iqtibos manbada, inglizcha emas."""
    if not isinstance(it, dict): return None
    q = fix_text(it.get("question"))[:1000]
    opts = [fix_text(o)[:500] for o in (it.get("options") or []) if isinstance(o, str)]
    ci = it.get("correct_index")
    if any(has_cyrillic(str(x)) for x in [it.get("question"), *(it.get("options") or [])]): stats["cyrillic"] += 1
    if not q or not isinstance(ci, int) or not 0 <= ci < len(opts) or not 3 <= len(opts) <= 6 or any(not o for o in opts) \
            or len({o.casefold() for o in opts}) != len(opts):
        stats["q_dropped"] += 1; return None
    if is_english(q) or any(is_english(o) for o in opts): stats["english"] += 1; stats["q_dropped"] += 1; return None
    quote = str(it.get("quote") or "")
    from . import testbank as TB
    if not quote.strip() or not TB._quote_in(re.sub(r"\s+", " ", quote).strip(), src): stats["q_uncited"] += 1; stats["q_dropped"] += 1; return None
    sid = str(it.get("sid") or "").strip().strip("[]")
    return {"sid": sid if sid in sids else None, "kind": "single", "question": q,
            "answers": [{"text": o, "correct": i == ci, "feedback": ""} for i, o in enumerate(opts)],
            "feedback_correct": fix_text(it.get("explanation"))[:1000], "quote": quote}

def build_lesson(meta: dict, secs: list[dict], call, seed: str = "") -> dict:
    """AI dars rejasi (sof — chaqiruv tashqaridan beriladi; testlarda soxta call). secs — [{"sid", "title", "text"}] (manba bo'limlari).
    → {"title", "sections": {sid: {"paras": [...], "interactive", "checks": [...]}}, "flashcards", "quiz", "report", "usage"}.
    Xato (qamrov yetmadi, matn yo'q) — GuardError; AI xatosi — claude_client.AIError (chaqiruvchida)."""
    sids = {s["sid"] for s in secs}
    src = "\n".join(f"{s['title']}\n{s['text']}" for s in secs)
    stats = {"paragraphs": 0, "p_dropped": 0, "p_uncited": 0, "english": 0, "cyrillic": 0, "q_dropped": 0, "q_uncited": 0, "interactive": 0,
             "flashcards": 0, "calls": 0, "longest_flagged": 0, "longest_after": 0, "distractors_regenerated": 0, "coverage_retry": False}
    usage = {"in": 0, "out": 0, "model": meta.get("model")}
    def run(system, prompt, schema, what, max_tokens=16000):
        data, info = call(model=meta.get("model") or "claude-opus-5-5", system=system, content=[{"type": "text", "text": prompt}], schema=schema,
                          max_tokens=max_tokens, effort="medium", timeout=300, what=what)
        stats["calls"] += 1; usage["in"] += int(info.get("in") or 0); usage["out"] += int(info.get("out") or 0); usage["model"] = info.get("model") or usage["model"]
        return data or {}
    body = "\n\n".join(f"## [{s['sid']}] {s['title']}\n{s['text']}" for s in secs)
    prompt = (f"Fan: {meta.get('course') or '—'}\nMavzu: {meta.get('topic') or '—'}\n\nMA'RUZA MATNI (bo'limlarga bo'lingan):\n<<<\n{body}\n>>>\n\n"
              "Shu matndan interaktiv dars tuzing (sxema bo'yicha).")
    data = run(AI_SYSTEM, prompt, AI_SCHEMA, "dars")
    out = {s["sid"]: {"paras": [], "interactive": None, "checks": []} for s in secs}
    for s in data.get("sections") or []:
        if not isinstance(s, dict): continue
        sid = str(s.get("sid") or "").strip().strip("[]")
        if sid not in out: continue
        for p in s.get("paragraphs") or []:
            if not isinstance(p, dict): continue
            raw = str(p.get("text") or "")
            if has_cyrillic(raw): stats["cyrillic"] += 1
            t = fix_text(raw)[:3000]
            if not t: continue
            if is_english(t): stats["english"] += 1; stats["p_dropped"] += 1; continue
            if not cited(t, p.get("quote"), src): stats["p_uncited"] += 1; stats["p_dropped"] += 1; continue
            out[sid]["paras"].append({"text": t, "quote": re.sub(r"\s+", " ", str(p.get("quote"))).strip()}); stats["paragraphs"] += 1
        it = s.get("interactive") or {}
        if isinstance(it, dict) and it.get("kind") in ("accordion", "tabs"):
            items = []
            for x in it.get("items") or []:
                if not isinstance(x, dict): continue
                tt, tx = fix_text(x.get("title"))[:200], fix_text(x.get("text"))[:3000]
                if tt and tx and not is_english(tx) and cited(tx, x.get("quote"), src): items.append({"title": tt, "text": tx})
            if len(items) >= 2: out[sid]["interactive"] = {"kind": it["kind"], "items": items[:12]}; stats["interactive"] += 1
        for q in s.get("checks") or []:
            v = _vq({**q, "sid": sid} if isinstance(q, dict) else q, sids, src, stats)
            if v: out[sid]["checks"].append(v)
    cards = []
    for f in data.get("flashcards") or []:
        if not isinstance(f, dict): continue
        if has_cyrillic(str(f.get("term")) + str(f.get("definition"))): stats["cyrillic"] += 1
        tm, df = fix_text(f.get("term"))[:200], fix_text(f.get("definition"))[:600]
        if tm and df and not is_english(df) and cited(df, f.get("quote"), src) and tm.casefold() not in {c_["front"].casefold() for c_ in cards}:
            cards.append({"front": tm, "back": df})
    stats["flashcards"] = len(cards)
    quiz = [v for v in (_vq(q, sids, src, stats) for q in data.get("quiz") or []) if v]
    if not any(o["paras"] for o in out.values()) and not quiz:
        raise GuardError("AI matnga asoslangan mazmun qaytarmadi (iqtiboslar manbada topilmadi) — qayta urinib ko'ring")
    # --- qamrov: har bo'lim kamida bitta savol bilan (bilimni tekshirish yoki yakuniy test)
    def uncovered():
        cov = {q["sid"] for q in quiz if q["sid"]} | {sid for sid, o in out.items() if o["checks"]}
        return [s for s in secs if s["sid"] not in cov]
    miss = uncovered()
    if miss:
        stats["coverage_retry"] = True
        p2 = (f"Fan: {meta.get('course') or '—'}\nMavzu: {meta.get('topic') or '—'}\n\nQuyidagi bo'limlar uchun yakuniy testga savollar kerak — har bo'limga 1–2 ta "
              "(4 variant, bittasi to'g'ri, variantlar uzunligi taxminan teng, quote — matndan aynan):\n<<<\n"
              + "\n\n".join(f"## [{s['sid']}] {s['title']}\n{s['text']}" for s in miss) + "\n>>>")
        d2 = run(AI_SYSTEM, p2, COVER_SCHEMA, "qamrov savollari", 6000)
        quiz += [v for v in (_vq(q, sids, src, stats) for q in d2.get("questions") or []) if v]
        miss = uncovered()
        if miss: raise GuardError("Savol bilan qamralmagan bo'limlar: " + "; ".join(f"{s['sid']} «{s['title'][:60]}»" for s in miss))
    # --- to'g'ri javob eng uzun bo'lmasin: belgilanadi va chalg'ituvchilar BIR MARTA qayta so'raladi
    allq = [q for o in out.values() for q in o["checks"]] + quiz
    flagged = [q for q in allq if correct_longest(q)]
    stats["longest_flagged"] = len(flagged)
    if flagged:
        ids = {f"Q{i + 1}": q for i, q in enumerate(flagged)}
        p3 = ("Quyidagi test savollarida to'g'ri javob boshqa variantlardan sezilarli uzun — bu taxmin qilishni osonlashtiradi. Har savol uchun "
              "to'g'ri javob bilan TAXMINAN BIR XIL UZUNLIKDAGI, matnga mos, lekin noto'g'ri chalg'ituvchilar yozing (soni — avvalgidek). "
              "To'g'ri javobni o'zgartirmang. O'zbek lotin yozuvida.\n\n" + "\n\n".join(
                  f"{k}. Savol: {q['question']}\nTo'g'ri javob: {next(a['text'] for a in q['answers'] if a['correct'])}\n"
                  f"Chalg'ituvchilar soni: {len(q['answers']) - 1}" for k, q in ids.items()))
        d3 = run(AI_SYSTEM, p3, DISTRACT_SCHEMA, "chalg'ituvchilar", 4000)
        for it in d3.get("items") or []:
            q = ids.get(str((it or {}).get("id") or "").strip()) if isinstance(it, dict) else None
            if not q: continue
            corr = next(a for a in q["answers"] if a["correct"])
            ds = [fix_text(x)[:500] for x in it.get("distractors") or [] if isinstance(x, str)]
            ds = [x for x in ds if x and x.casefold() != corr["text"].casefold() and not is_english(x)]
            if len(ds) == len(q["answers"]) - 1 and len({x.casefold() for x in ds}) == len(ds):
                q["answers"] = [corr] + [{"text": x, "correct": False, "feedback": ""} for x in ds]; stats["distractors_regenerated"] += 1
        for q in allq:
            if correct_longest(q): q["flag_longest"] = True
        stats["longest_after"] = sum(1 for q in allq if q.get("flag_longest"))
    balance(allq, seed or meta.get("topic") or "")
    title = fix_text(data.get("title"))[:200] or meta.get("topic") or "Dars"
    rep = {**stats, "sections": len(secs), "questions": len(quiz), "checks": sum(len(o["checks"]) for o in out.values()), "positions": positions(allq),
           "longest_share": round(stats["longest_after"] / len(allq), 2) if allq else 0.0}
    return {"title": title, "sections": out, "flashcards": cards, "quiz": quiz, "report": rep, "usage": usage}

# --- manba: hujjat → bo'limlar (sarlavha, matn, rasm, jadval) --------------------------------------------------------------------
AI_MAX_CHARS = 60_000
AI_MAX_BYTES = 50 * 1024 * 1024

def source_sections(raw: bytes, title: str = "") -> dict:
    """Hujjat (.docx — rasm/jadvallar bilan; .pdf / .txt — matn) → {"sections": [{"sid", "title", "text", "parts"}], "plan", "images": {fayl: baytlar}}.
    Bo'limlar — h2 sarlavhalar bo'yicha (bo'lmasa h3, bo'lmasa bitta bo'lim)."""
    from . import taqdimot_extract as EX
    if not raw: raise HTTPException(400, "Fayl bo'sh")
    PK._read_upload_guard(raw)
    images = {}
    try:
        kind = EX.sniff(raw)
        if kind == "docx":
            PK._zip_guard(raw); PK._ooxml_image_guard(raw, "word/media/")
            try: dx = PK.docx_lecture(raw)
            except HTTPException: raise
            except Exception: raise EX.BadFile("Word faylni o'qib bo'lmadi (fayl buzilgan yoki .docx emas)")
            txt = dx["text"][:PK.MAX_TEXT_CHARS]
            images = {fn: v["data"] for fn, v in dx["images"].items() if f"[RASM:{fn}]" in txt}
            media = {"images": {fn: {"caption": v["caption"]} for fn, v in dx["images"].items()}, "tables": dx["tables"]}
        else:
            ex = EX.extract(raw, kind, None)
            txt, _ = EX.as_text([b for b in ex["blocks"] if b.get("k") != "img"], PK.MAX_TEXT_CHARS)
            media = {"images": {}, "tables": {}}
    except EX.BadFile as e:
        raise HTTPException(415, str(e))
    if len(PK._plain(txt)) < 200: raise HTTPException(400, "Hujjatda matn juda kam (kamida 200 belgi kerak)")
    stx = PK.structure_text(txt, title, media)
    parts = split_html(stx["html"])
    lvl = "h2" if any(p["t"] == "h2" for p in parts) else "h3" if any(p["t"] == "h3" for p in parts) else None
    secs, cur = [], None
    def new(t):
        s = {"sid": f"S{len(secs) + 1}", "title": t, "parts": []}; secs.append(s); return s
    for p in parts:
        if lvl and p["t"] == lvl: cur = new(translit(p["text"])[:200] or f"{len(secs) + 1}-bo'lim"); continue
        if cur is None: cur = new(translit(title) or "Kirish")
        cur["parts"].append(p)
    from lxml import html as LH
    def plain(p):
        if p["t"] == "html":
            try: return re.sub(r"\s+", " ", LH.fromstring(f"<div>{p['html']}</div>").text_content()).strip()
            except Exception: return re.sub(r"<[^>]+>", " ", p["html"])
        if p["t"] == "table": return "\n".join(" | ".join(r) for r in p["rows"])
        if p["t"] in ("h2", "h3"): return p["text"]
        return p.get("caption") or ""
    for s in secs: s["text"] = "\n".join(x for x in (plain(p) for p in s["parts"]) if x)
    secs = [s for s in secs if s["text"].strip() or any(p["t"] in ("fig", "table") for p in s["parts"])]
    for i, s in enumerate(secs, 1): s["sid"] = f"S{i}"
    total = 0
    for s in secs:                                   # AI'ga yuboriladigan matn chegarasi (bo'limlar soni saqlanadi, matni qisqaradi)
        room = max(400, AI_MAX_CHARS // max(1, len(secs)))
        s["ai_text"] = s["text"][:room]; total += len(s["ai_text"])
    return {"sections": secs, "plan": stx["plan"], "images": images, "truncated": any(len(s["text"]) > len(s["ai_text"]) for s in secs)}

def ai_daily() -> int: return PK.pk_daily()

def ai_lesson(c: Ctx, kcid: int, raw: bytes, name: str, call=None) -> dict:
    """«AI: hujjatdan dars» — kursga yangi dars (bloklar) + yakuniy test qo'shiladi. Kalitsiz — 503 (hech narsa yaratilmaydi)."""
    from . import claude_client as CC
    co = KU._course(c, kcid, write=True)
    if call is None:
        if not CC.has_key():
            rbac.audit(_con, c, "dars: AI hujjatdan dars — AI ulanmagan", RES, True, f"ku #{kcid}")
            raise HTTPException(503, "AI ulanmagan — administratorga murojaat qiling. Darsni hozircha bloklardan qo'lda yig'ishingiz mumkin.")
        call = CC.call_json
    day = clock.today().isoformat()
    if (db.one(_con, "SELECT COUNT(*) n FROM ds_ai WHERE user_id=? AND day=?", (c.user["id"], day)) or {}).get("n", 0) >= ai_daily():
        raise HTTPException(429, f"Kunlik cheklov: bir foydalanuvchi uchun kuniga {ai_daily()} ta AI so'rovi. Ertaga davom ettiring.")
    topic = re.sub(r"\.(docx|pdf|txt)$", "", Path(name or "dars").name, flags=re.I)[:160]
    src = source_sections(raw, topic)
    secs = [{"sid": s["sid"], "title": s["title"], "text": s["ai_text"]} for s in src["sections"]]
    if not secs: raise HTTPException(400, "Hujjatda bo'limlar topilmadi")
    ln = link_of_kurs(kcid)
    meta = {"course": (ln or {}).get("subject") or co["title"], "topic": topic, "model": PK.pk_model()}
    t0 = time.time(); err = None; plan = None; code = 502
    try:
        plan = build_lesson(meta, secs, call, seed=f"{kcid}:{topic}")
    except GuardError as e:
        err, code = str(e), 422
    except CC.AIError as e:
        err = str(e)
    except Exception as e:
        err = f"AI javobini qayta ishlab bo'lmadi: {type(e).__name__}"
    usage = (plan or {}).get("usage") or {"in": 0, "out": 0, "model": meta["model"]}
    with _lock:
        _con.execute("INSERT INTO ds_ai(course_id,user_id,day,ts,model,ok,ms,err,in_tok,out_tok,n_calls,stats) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (kcid, c.user["id"], day, _now(), usage.get("model"), 0 if err else 1, int((time.time() - t0) * 1000), err, usage.get("in", 0),
                      usage.get("out", 0), (plan or {}).get("report", {}).get("calls", 0), json.dumps((plan or {}).get("report") or {}, ensure_ascii=False)))
        _con.commit()
    rbac.audit(_con, c, "dars: AI hujjatdan dars", RES, True, f"ku #{kcid} · {name[:60]} · {len(secs)} bo'lim{' · xato' if err else ''}")
    if err: raise HTTPException(code, err)
    # bloklar
    blocks, imgs = [], {}
    def B(t, d): blocks.append({"id": KU._uid(), "type": t, "data": d})
    if src["plan"]:
        B("heading", {"text": "Reja", "level": 2}); B("list", {"style": "numbered", "items": [html.escape(translit(x)) for x in src["plan"]]})
    with KU._lock:
        for s in src["sections"]:
            o = plan["sections"].get(s["sid"]) or {"paras": [], "interactive": None, "checks": []}
            B("heading", {"text": s["title"], "level": 2})
            for p in o["paras"]: B("paragraph", {"html": _p(p["text"])})
            for part in s["parts"]:
                if part["t"] == "fig":
                    fn = part["src"].rsplit("/", 1)[-1]
                    if fn in src["images"] and fn not in imgs:
                        try:
                            data, ext, m_ = KU.image_from_bytes(src["images"][fn])
                            imgs[fn] = KU._save_asset(c, kcid, "image", ext, fn, data=data, meta=m_)
                        except HTTPException: continue
                    if fn in imgs: B("image", {"asset": imgs[fn], "alt": translit(part["caption"] or "Rasm")[:300], "caption": translit(part["caption"])[:500], "layout": "centered"})
                elif part["t"] == "table":
                    B("table", {"header": part["header"], "caption": translit(part["caption"]), "rows": [[translit(x) for x in r] for r in part["rows"]]})
            if o["interactive"]:
                B(o["interactive"]["kind"], {"items": [{"title": x["title"], "html": _p(x["text"])} for x in o["interactive"]["items"]]})
            for q in o["checks"]:
                B("knowledge", {k_: v for k_, v in q.items() if k_ not in ("sid", "quote", "flag_longest")} | {"retry": True})
            if o["checks"]: B("continue", {"label": KU.LABELS["continue"], "require": "interactions"})
        if len(plan["flashcards"]) >= 2:
            B("heading", {"text": "Asosiy atamalar", "level": 2}); B("flashcards", {"style": "grid", "cards": plan["flashcards"][:40]})
        A = KU._Assets(kcid)
        pos = (db.one(_con, "SELECT MAX(pos) m FROM ku_lessons WHERE course_id=? AND deleted=0", (kcid,)) or {}).get("m") or 0
        lid = _new_lesson(kcid, KU._uid("l"), pos + 1, "blocks", plan["title"], None, c.user["full_name"])
        _write_lesson_blocks(lid, blocks, A)
        qlid = None
        if plan["quiz"]:
            qlid = _new_lesson(kcid, KU._uid("l"), pos + 2, "quiz", f"Yakuniy test: {plan['title']}"[:200], None, c.user["full_name"])
            _write_lesson_blocks(qlid, [{"id": KU._uid(), "type": "question", "data": {k_: v for k_, v in q.items() if k_ not in ("sid", "quote", "flag_longest")}}
                                        for q in plan["quiz"]], A)
        KU._bump(kcid, c)
        KU._log(c, kcid, "AI: hujjatdan dars", f"{name[:80]} · {len(blocks)} blok · {len(plan['quiz'])} savol"); _con.commit()
    KU.snapshot(c, kcid, "import", f"AI: hujjatdan dars ({name[:60]})")
    return {"ok": True, "lesson_id": lid, "quiz_lesson_id": qlid, "blocks": len(blocks), "report": plan["report"],
            "flagged": [q["question"] for q in [x for o in plan["sections"].values() for x in o["checks"]] + plan["quiz"] if q.get("flag_longest")],
            "tokens": {"in": usage.get("in", 0), "out": usage.get("out", 0)}, "course": KU.course_view(c, kcid)}


# =============================================================================================
# API
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "bo'lim ochildi")
    k = c.role.key
    return {"role": k, "caps": {"write": k in AUTHORS, "review": k in REVIEWERS, "template": k in DEPT, "approve": k in DEPT, "ai": k in AUTHORS},
            "kinds": SLOT_KINDS, "ltypes": LTYPES, "modes": PK.MODES, "ai": PK.CC_has_key() and k in AUTHORS}

@router.get(P + "/subjects/{cid}")
def api_subject(cid: int, request: Request):
    c = C(request); guard(c, "fan", WORK, f"kurs #{cid}")
    return subject_view(c, cid)

class SkelIn(BaseModel):
    ratio: int = 2
    apply: bool = False
    with_kurs: bool = True

@router.post(P + "/subjects/{cid}/skeleton")
def api_skeleton(cid: int, body: SkelIn, request: Request):
    c = C(request); guard(c, "fan skeleti", AUTHORS, f"kurs #{cid} · {body.ratio} · {'saqlash' if body.apply else 'ko`rish'}".replace("`", "'"))
    return skeleton(c, cid, body.ratio, body.apply, body.with_kurs)

@router.post(P + "/subjects/{cid}/lessons/{key}/convert")
def api_convert(cid: int, key: int, request: Request):
    c = C(request); guard(c, "muharrirga o'tkazish", AUTHORS, f"kurs #{cid} · {PK.lesson_code(key)}")
    return convert_lesson(c, cid, key)

class AuthIn(BaseModel):
    authority: str

@router.post(P + "/subjects/{cid}/lessons/{key}/authority")
def api_authority(cid: int, key: int, body: AuthIn, request: Request):
    c = C(request); guard(c, "eksport manbai", AUTHORS, f"kurs #{cid} · {PK.lesson_code(key)} · {body.authority}")
    return set_authority(c, cid, key, body.authority)

class ApplyIn(BaseModel):
    template_id: int = 0
    preview: bool = True

@router.post(P + "/subjects/{cid}/template/apply")
def api_apply(cid: int, body: ApplyIn, request: Request):
    c = C(request); guard(c, "shablonni qo'llash", AUTHORS, f"kurs #{cid} · #{body.template_id} · {'ko`rish' if body.preview else 'qo`llash'}".replace("`", "'"))
    return apply_template(c, cid, body.template_id or None, body.preview)

class BulkIn(BaseModel):
    mode: str = "xapi"
    keys: list[int] = []

@router.post(P + "/subjects/{cid}/bulk")
def api_bulk(cid: int, body: BulkIn, request: Request):
    c = C(request); guard(c, "ommaviy yig'ish", AUTHORS, f"kurs #{cid} · {body.mode} · {len(body.keys) or 'hammasi'}")
    return start_bulk(c, cid, body.mode, body.keys or None)

@router.get(P + "/jobs/{jid}")
def api_job(jid: int, request: Request):
    c = C(request); guard(c, "ish holati", AUTHORS, f"#{jid}")
    return job_view(c, jid)

@router.get(P + "/jobs/{jid}/download")
def api_job_dl(jid: int, request: Request):
    c = C(request); guard(c, "ommaviy zip", AUTHORS, f"#{jid}")
    return job_file(c, jid)

@router.get(P + "/templates")
def api_templates(request: Request):
    c = C(request); guard(c, "shablonlar", WORK)
    return templates_list(c)

class TplIn(BaseModel):
    department_id: int = 0
    name: str = Field("", max_length=120)
    layout: dict
    note: str = Field("", max_length=300)

@router.post(P + "/templates")
def api_template_save(body: TplIn, request: Request):
    c = C(request); guard(c, "shablon saqlash", DEPT, f"dep {body.department_id}")
    return save_template(c, body.department_id, body.name, body.layout, body.note)

@router.get(P + "/kurs/{kcid}/comments")
def api_comments(kcid: int, request: Request):
    c = C(request); guard(c, "izohlar", WORK, f"ku #{kcid}")
    return comments(c, kcid)

class CommentIn(BaseModel):
    lesson_id: int = 0
    block_uid: str = Field("", max_length=40)
    text: str = Field("", max_length=MAX_COMMENT)
    blocking: bool = False
    mention_author: bool = False
    parent_id: int | None = None

@router.post(P + "/kurs/{kcid}/comments")
def api_comment_add(kcid: int, body: CommentIn, request: Request):
    c = C(request); guard(c, "izoh qo'shish", WORK, f"ku #{kcid}")
    return add_comment(c, kcid, body.model_dump())

@router.post(P + "/comments/{mid}/resolve")
def api_comment_resolve(mid: int, request: Request):
    c = C(request); guard(c, "izohni hal qilish", WORK, f"#{mid}")
    return set_comment_status(c, mid, True)

@router.post(P + "/comments/{mid}/reopen")
def api_comment_reopen(mid: int, request: Request):
    c = C(request); guard(c, "izohni qayta ochish", WORK, f"#{mid}")
    return set_comment_status(c, mid, False)

@router.get(P + "/kurs/{kcid}/link")
def api_kurs_link(kcid: int, request: Request):
    c = C(request); guard(c, "bog'lanish", WORK, f"ku #{kcid}")
    KU._course(c, kcid)
    return {"link": link_of_kurs(kcid), "blocking": blocking_open(kcid)}

@router.post(P + "/kurs/{kcid}/ai-lesson")
async def api_ai_lesson(kcid: int, request: Request, name: str = "dars.docx"):
    c = C(request); guard(c, "AI: hujjatdan dars", AUTHORS, f"ku #{kcid} · {name[:60]}")
    from . import claude_client as CC
    if not CC.has_key():         # tana o'qilmasdan — kalit yo'q
        await run_in_threadpool(KU._course, c, kcid, True)
        rbac.audit(_con, c, "dars: AI hujjatdan dars — AI ulanmagan", RES, True, f"ku #{kcid}")
        raise HTTPException(503, "AI ulanmagan — administratorga murojaat qiling. Darsni hozircha bloklardan qo'lda yig'ishingiz mumkin.")
    raw = await PK._read_body(request, AI_MAX_BYTES)
    return await run_in_threadpool(ai_lesson, c, kcid, raw, name)
