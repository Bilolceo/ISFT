"""AI tutor — tasdiqlangan kurs materiali indeksi va qidiruv (app/tutor.py).

Manba — talabaga HAQIQATDA ochiladigan tasdiqlangan eksport (lrs.package_for(approved_only=True) bilan bir xil qoida):
  dl:<id> pilot — kursning tasdiqlangan paket darslari (har dars uchun eng so'nggi tasdiqlangan versiya) + ds_links orqali bog'langan,
                  muharrirda tasdiqlangan kurslar (ku:<id>);   ku:<id> pilot — o'sha kursning tasdiqlangan eksporti.
Zip ichidagi content.json o'qiladi: ma'ruza matni (sarlavhalar bo'yicha bo'limlar), reja, asosiy xulosalar, slaydlar (sarlavha, bandlar,
izohlar), video subtitrlari (WebVTT → transkript), kartochkalar, topshiriq matni; kurs muharriri bloklari. Bilimni tekshirish, test,
saralash/moslashtirish bloklari INDEKSGA KIRMAYDI (javoblar sizib chiqmasin) — ular «elementlar» (tu_items) sifatida faqat maslahat
rejimini aniqlash va javobni to'sish uchun saqlanadi; Test bank savollari (o'chirilmagan) ham shu ro'yxatda.
Parcha id barqaror: sha1(manba|dars|blok|tartib). Imzo (sig) — manba paketlari id'lari; o'zgarsa (tasdiq / yangi versiya) indeks qayta quriladi.
Qidiruv — BM25 (sof Python), joriy dars parchalari 1,3× ustun.
"""
from __future__ import annotations
import hashlib, json, math, re, threading, zipfile
from collections import Counter
from . import db, tutor_text as TT

_MEM: dict = {}            # pilot_ref → {"sig", "chunks", "df", "N", "avgdl", "vocab", "items"}
_mlock = threading.Lock()


def code_of(key: int) -> str:
    from . import paket as PK
    for pre, base, _, _ in sorted(PK.KINDS.values(), key=lambda x: -x[1]):
        if key > base: return f"{pre}{key - base}"
    return f"L{key}"


def sources(con, pilot_ref: str) -> list[dict]:
    """→ [{src, lesson, code, pkg, file}] — talabaga ochiladigan tasdiqlangan eksportlar."""
    from . import lrs as L, paket as PK, talaba_darslar as TD
    kind, _, cid = pilot_ref.partition(":")
    if not cid.isdigit(): return []
    out = []
    if kind == "dl":
        seen = set()
        for r in db.rows(con, """SELECT id, topic_no, file FROM pk_packages WHERE course_id=? AND status='tasdiqlandi' AND mode!='none' AND file IS NOT NULL
                                 AND file!='' ORDER BY topic_no, version DESC, id DESC""", (int(cid),)):
            if r["topic_no"] in seen: continue
            seen.add(r["topic_no"])
            f = PK.store() / r["file"]
            if f.is_file():
                code = code_of(int(r["topic_no"]))
                out.append({"src": pilot_ref, "lesson": code, "code": code, "pkg": f"pk{r['id']}", "file": f})
        for lkey, kid in sorted(TD._kurs_links(con, int(cid)).items()):
            pk = L.package_for(f"ku:{kid}", "", approved_only=True)
            if pk: out.append({"src": f"ku:{kid}", "lesson": "", "code": code_of(int(lkey)), "pkg": f"ku{pk['id']}", "file": pk["file"]})
    elif kind == "ku":
        pk = L.package_for(pilot_ref, "", approved_only=True)
        if pk: out.append({"src": pilot_ref, "lesson": "", "code": "", "pkg": f"ku{pk['id']}", "file": pk["file"]})
    return out


INDEX_V = 2               # bo'laklash qoidasi o'zgarsa oshiriladi — barcha indekslar qayta quriladi


def signature(srcs: list[dict]) -> str:
    return hashlib.sha1(json.dumps([INDEX_V] + sorted([s["src"], s["lesson"], s["pkg"]] for s in srcs)).encode()).hexdigest()[:16]


def _cid(*parts) -> str:
    return "c" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:11]


def _vtt(z: zipfile.ZipFile, path) -> str:
    try: raw = z.read(str(path)).decode("utf-8", "replace")
    except Exception: return ""
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("WEBVTT", "NOTE")) or "-->" in ln or ln.isdigit(): continue
        lines.append(re.sub(r"<[^>]+>", "", ln))
    return " ".join(lines)


class _B:
    """Bitta manba uchun parcha va elementlar yig'uvchi."""
    def __init__(self, src):
        self.src, self.chunks, self.items, self.susp = src, [], [], 0

    def add(self, lesson, block, sec, label, title, text, kind="matn"):
        text, n = TT.strip_injection(re.sub(r"(?<!\.)\.\.(?!\.)", ".", str(text or "")))
        self.susp += n
        title = TT.strip_injection(title or "")[0]
        for k, w in enumerate(TT.windows(text)):
            if len(TT.stems(w)) < 3: continue
            self.chunks.append({"id": _cid(self.src, lesson, block, sec, k), "src": self.src, "lesson": lesson, "block": block or "", "sec": sec,
                                "label": label, "title": title[:200], "text": w, "kind": kind})

    def item(self, lesson, iid, kind, stem, options, correct, tf=False):
        if not str(stem or "").strip(): return
        self.items.append({"src": self.src, "lesson": lesson, "id": str(iid), "kind": kind, "stem": TT.html_text(stem)[:1000],
                           "options": [str(o)[:300] for o in options or []][:10], "correct": [str(c)[:300] for c in correct or []][:10], "truefalse": tf})


def _paket(B: _B, content: dict, z, code: str):
    sec = 0
    for b in content.get("blocks") or []:
        t, bid = b.get("type"), b.get("id") or ""
        if t == "text":
            for h, body in TT.html_sections(b.get("html")):
                sec += 1; B.add(code, bid, sec, f"{code}, {sec}-bo'lim", h or b.get("title") or "", (h + ". " if h else "") + body)
        elif t == "plan":
            sec += 1; B.add(code, bid, sec, f"{code}, reja", "Reja", ". ".join([str(b.get("heading") or "")] + [TT.html_text(x if isinstance(x, str) else (x or {}).get("text")) for x in b.get("items") or []]))
        elif t == "keypoints":
            sec += 1; B.add(code, bid, sec, f"{code}, asosiy xulosalar", "Asosiy xulosalar",
                            ". ".join(TT.html_text(x if isinstance(x, str) else (x or {}).get("text")) for x in b.get("items") or []))
        elif t == "slides":
            for i, s in enumerate(b.get("slides") or [], 1):
                txt = ". ".join(x for x in [str(s.get("title") or ""), *[TT.html_text(y) for y in s.get("bullets") or []], str(s.get("notes") or ""), str(s.get("caption") or "")] if x)
                B.add(code, bid, 100 + i, f"{code}, {i}-slayd", s.get("title") or "Taqdimot", txt, "slayd")
        elif t == "video":
            for c in b.get("captions") or []:
                if isinstance(c, dict) and c.get("src") and (c.get("lang") or "uz") == "uz":
                    B.add(code, bid, 200, f"{code}, video", b.get("title") or "Videodars", _vtt(z, c["src"]), "video")
        elif t == "assignment":
            sec += 1; B.add(code, bid, sec, f"{code}, topshiriq", b.get("title") or "Topshiriq", TT.html_text(b.get("text")))
        elif t == "flashcards":
            sec += 1; B.add(code, bid, sec, f"{code}, kartochkalar", b.get("title") or "Kartochkalar",
                            ". ".join(f"{c.get('front', '')} — {c.get('back', '')}" for c in b.get("cards") or [] if isinstance(c, dict)))
        elif t == "quiz":
            for q in b.get("questions") or []:
                opts = q.get("options") or []
                corr = [opts[i] for i in q.get("correct") or [] if isinstance(i, int) and 0 <= i < len(opts)] + [str(a) for a in q.get("answers") or []]
                B.item(code, f"{bid}_{q.get('id')}", "quiz", q.get("stem"), opts, corr, q.get("type") == "tf")


_KU_SKIP = {"knowledge", "question", "sorting", "matching", "divider", "continue"}


def _ku_text(b: dict) -> str:
    t, H = b.get("type"), TT.html_text
    if t == "heading": return str(b.get("text") or "")
    if t in ("paragraph",): return H(b.get("html"))
    if t == "heading_paragraph": return f"{b.get('heading', '')}. {H(b.get('html'))}"
    if t == "quote": return f"{b.get('text', '')} {b.get('cite', '')}"
    if t == "list": return ". ".join(H(x) for x in b.get("items") or [])
    if t == "table": return ". ".join(" | ".join(map(str, r)) for r in b.get("rows") or [])
    if t in ("image", "gallery"): return " ".join([str(b.get("caption") or "")] + [str(x.get("caption") or "") for x in b.get("items") or [] if isinstance(x, dict)])
    if t == "image_text": return H(b.get("html"))
    if t == "audio": return f"{b.get('title', '')}. {b.get('transcript', '')}"
    if t == "attachment": return f"{b.get('title', '')}. {b.get('desc', '')}"
    if t == "labeled_graphic": return ". ".join(f"{m.get('title', '')}: {H(m.get('html'))}" for m in b.get("markers") or [])
    if t in ("accordion", "tabs", "process", "timeline"): return ". ".join(f"{x.get('date', '')} {x.get('title', '')}: {H(x.get('html'))}".strip() for x in b.get("items") or [])
    if t == "flashcards": return ". ".join(f"{c.get('front', '')} — {c.get('back', '')}" for c in b.get("cards") or [])
    if t == "button": return str(b.get("text") or "")
    if t == "video": return f"{b.get('title', '')}. {b.get('caption', '')}"
    return ""


def _kurs(B: _B, content: dict, z, code: str):
    for pos, l in enumerate(content.get("lessons") or [], 1):
        lid = l.get("id") or ""
        pre = f"{code} · " if code else ""
        if l.get("type") == "quiz":
            for q in l.get("questions") or []:
                ans = q.get("answers") or []
                B.item(lid, q.get("id"), "quiz", q.get("question"), [a.get("text") for a in ans], [a.get("text") for a in ans if a.get("correct")] + list(q.get("accept") or []),
                       q.get("kind") == "truefalse")
            continue
        sec, buf, head, hb = 0, [], l.get("title") or "", ""
        def flush():
            if buf: B.add(lid, hb, max(sec, 1), f"{pre}{pos}-dars, {max(sec, 1)}-bo'lim", head, " ".join(buf))
        for b in l.get("blocks") or []:
            t = b.get("type")
            if t == "knowledge":
                ans = b.get("answers") or []
                B.item(lid, b.get("id"), "knowledge", b.get("question"), [a.get("text") for a in ans], [a.get("text") for a in ans if a.get("correct")] + list(b.get("accept") or []),
                       b.get("kind") == "truefalse")
                continue
            if t in _KU_SKIP: continue
            if t in ("heading", "heading_paragraph") or not hb:
                flush(); buf = []; sec += 1; hb = b.get("id") or ""
                head = str(b.get("text") or b.get("heading") or l.get("title") or "")
            if t == "video":
                for c in b.get("captions") or []:
                    if isinstance(c, dict) and c.get("src"): buf.append(_vtt(z, c["src"]))
            txt = _ku_text(b)
            if txt.strip(): buf.append(txt.strip().rstrip(".") + ".")
        flush()


def build(con, pilot_ref: str, srcs: list[dict] | None = None) -> dict:
    """Indeksni quradi va tu_chunks / tu_items / tu_index ga yozadi. → {"chunks", "items", "suspicious", "lessons"}."""
    srcs = sources(con, pilot_ref) if srcs is None else srcs
    chunks, items, susp, lessons = [], [], 0, set()
    for s in srcs:
        B = _B(s["src"])
        try:
            with zipfile.ZipFile(s["file"]) as z:
                content = json.loads(z.read("content.json"))
                (_kurs if s["src"].startswith("ku:") else _paket)(B, content, z, s["code"])
        except Exception:
            continue
        chunks += B.chunks; items += B.items; susp += B.susp
        lessons |= {(c["src"], c["lesson"]) for c in B.chunks}
    try:       # Test bank savollari (o'chirilmagan; oraliq/yakuniy banklar ham) — faqat maslahat rejimini aniqlash uchun
        if pilot_ref.startswith("dl:"):
            for r in db.rows(con, "SELECT id, qtype, stem, options, correct, answers FROM tb_questions WHERE course_id=? AND deleted=0", (int(pilot_ref[3:]),)):
                opts = json.loads(r["options"] or "[]"); corr = json.loads(r["correct"] or "[]"); ans = json.loads(r["answers"] or "[]")
                items.append({"src": "tb", "lesson": "", "id": f"tb{r['id']}", "kind": "bank", "stem": str(r["stem"] or "")[:1000], "options": [str(o) for o in opts][:10],
                              "correct": [str(opts[i]) for i in corr if isinstance(i, int) and 0 <= i < len(opts)] + [str(a) for a in ans], "truefalse": r["qtype"] == "tf"})
    except Exception:
        pass
    sig = signature(srcs)
    from . import clock
    with _mlock:
        con.execute("DELETE FROM tu_chunks WHERE pilot_ref=?", (pilot_ref,))
        con.execute("DELETE FROM tu_items WHERE pilot_ref=?", (pilot_ref,))
        seen = set()
        for i, c in enumerate(chunks):
            if c["id"] in seen: continue
            seen.add(c["id"])
            con.execute("INSERT INTO tu_chunks(pilot_ref,id,src_ref,lesson_ref,block_id,sec,label,title,text,kind,pos) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (pilot_ref, c["id"], c["src"], c["lesson"], c["block"], c["sec"], c["label"], c["title"], c["text"], c["kind"], i))
        for it in items:
            con.execute("INSERT OR REPLACE INTO tu_items(pilot_ref,src_ref,lesson_ref,item_id,kind,stem,data) VALUES(?,?,?,?,?,?,?)",
                        (pilot_ref, it["src"], it["lesson"], it["id"], it["kind"], it["stem"],
                         json.dumps({"options": it["options"], "correct": it["correct"], "truefalse": it["truefalse"]}, ensure_ascii=False)))
        con.execute("INSERT OR REPLACE INTO tu_index(pilot_ref,sig,built_at,n_chunks,n_items,n_suspicious,n_lessons) VALUES(?,?,?,?,?,?,?)",
                    (pilot_ref, sig, clock.now().replace(microsecond=0).isoformat(timespec="seconds"), len(seen), len(items), susp, len(lessons)))
        con.commit()
        _MEM.pop(pilot_ref, None)
    return {"chunks": len(seen), "items": len(items), "suspicious": susp, "lessons": len(lessons), "sig": sig}


def load(con, pilot_ref: str) -> dict:
    """Xotiradagi indeks (imzo o'zgarsa — qayta quriladi)."""
    srcs = sources(con, pilot_ref)
    sig = signature(srcs)
    m = _MEM.get(pilot_ref)
    if m and m["sig"] == sig: return m
    row = db.one(con, "SELECT sig FROM tu_index WHERE pilot_ref=?", (pilot_ref,))
    if not row or row["sig"] != sig: build(con, pilot_ref, srcs)
    chunks = db.rows(con, "SELECT * FROM tu_chunks WHERE pilot_ref=? ORDER BY pos", (pilot_ref,))
    df = Counter()
    for c in chunks:
        c["tf"] = Counter(TT.stems(f"{c['title']} {c['text']}"))
        c["len"] = sum(c["tf"].values()) or 1
        df.update(c["tf"].keys())
    items = []
    for r in db.rows(con, "SELECT * FROM tu_items WHERE pilot_ref=?", (pilot_ref,)):
        d = json.loads(r["data"] or "{}")
        items.append({"src": r["src_ref"], "lesson": r["lesson_ref"], "id": r["item_id"], "kind": r["kind"], "stem": r["stem"], **d, "st": set(TT.stems(r["stem"]))})
    m = {"sig": sig, "chunks": chunks, "df": df, "N": len(chunks), "avgdl": (sum(c["len"] for c in chunks) / len(chunks)) if chunks else 1.0,
         "vocab": set(df), "items": items}
    with _mlock: _MEM[pilot_ref] = m
    return m


def search(m: dict, q: str, prefer: tuple | None = None, k: int = 5, k1: float = 1.5, b: float = 0.75) -> list[tuple[float, dict]]:
    qs = TT.stems(q)
    if not qs or not m["N"]: return []
    out = []
    for c in m["chunks"]:
        s = 0.0
        for w in set(qs):
            f = c["tf"].get(w, 0)
            if not f: continue
            n = m["df"][w]
            idf = math.log(1 + (m["N"] - n + 0.5) / (n + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * c["len"] / m["avgdl"]))
        if s > 0:
            if prefer and (c["src_ref"], c["lesson_ref"]) == prefer: s *= 1.3
            out.append((s, c))
    out.sort(key=lambda x: -x[0])
    return out[:k]


def coverage(m: dict, q: str) -> float:
    qs = set(TT.stems(q))
    if not qs: return 0.0
    hit = sum(1 for w in qs if w in m["vocab"] or (len(w) >= 4 and any(v.startswith(w) or w.startswith(v) for v in m["vocab"] if len(v) >= 4)))
    return hit / len(qs)


def match_item(m: dict, q: str, need: float = 0.6) -> dict | None:
    """Talaba savoli test / bilimni tekshirish / Test bank savoliga mos keladimi (savol o'zaklarining ≥ need ulushi)."""
    qs = set(TT.stems(q))
    best, bs = None, 0.0
    for it in m["items"]:
        st = it["st"]
        if len(st) < 3: continue
        r = len(st & qs) / len(st)
        if r > bs: best, bs = it, r
    return best if bs >= need else None


def item_by_id(m: dict, src: str, iid: str) -> dict | None:
    return next((it for it in m["items"] if it["id"] == str(iid) and it["src"] == src), None)
