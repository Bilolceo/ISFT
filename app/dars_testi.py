"""Dars oxiri testi — bir bosishda har darsdan keyin 3–5 savollik past xavfli test (retrieval practice) Test bankdan (docs/keyslar.md).

Nima uchun: tez-tez, past xavfli o'zini tekshirish (retrieval practice) meta-tahlillarda g ≈ 0,5–0,7 ta'sir ko'rsatadi. Har dars oxiridagi qisqa
test (urinishlar cheklanmagan, o'tish bali 60 %) talabaga o'zini sinash imkonini beradi, natija esa xAPI orqali LRS'ga (lrs_progress — ball,
urinishlar) va «Ortda qolganlar» / savollar tahliliga tushadi.

Qoidalar (deterministik, testlangan — allocate()):
  * savollar FAQAT Test bankdagi TASDIQLANGAN (status='tasdiqlandi', o'chirilmagan) savollar, o'sha darsning mavzusi bo'yicha;
  * bitta fan ichida savol takrorlanmaydi (darslar orasida dublikat yo'q — ku_autoquiz jurnali bo'yicha, o'chirilgan test darslari hisobga olinmaydi);
  * har darsga 3–5 ta: mavzuning bo'sh savollari shu mavzudagi darslarga teng bo'linadi; 3 tadan kam qolsa — dars o'tkazib yuboriladi (sabab bilan);
  * tartib aralashtirilgan (barqaror urug' — kurs va dars bo'yicha), test sozlamasida savollar va javoblar ham aralashtiriladi;
  * idempotent: testi bor dars qayta qo'shilmaydi. O'zgarishdan oldin kurs versiyasi saqlanadi (Versiyalar → tiklash).

Mavzu: «Dars tayyorlash» darsi (ds_links) — paket.source_topic (L — o'z raqami, A/S — bog'langan mavzu); bog'lanmagan kurs muharriri kursi —
masofaviy kursga bog'langan bo'lsa, n-chi bloklar darsi = n-mavzu.
Ruxsat: Kurs muharriri / Dars tayyorlash mualliflari (bo'lim — hammasi, o'qituvchi — o'z kurslari), audit jurnalida.
"""
from __future__ import annotations
import json, random, threading
from fastapi import APIRouter, Request, HTTPException
from . import clock, db, rbac
from .rbac import Ctx

router = APIRouter()
_con = None
_ctx = None
_lock = threading.RLock()
UID_PREFIX = "aq"
MIN_Q, MAX_Q = 3, 5
SETTINGS = {"pass_pct": 60, "attempts": 0, "shuffle": True, "randomize": True, "reveal": "always",
            "intro": "Qisqa o'z-o'zini tekshirish: 3–5 savol, urinishlar cheklanmagan. Maqsad — mavzuni esga olish va mustahkamlash."}

SCHEMA = """
CREATE TABLE IF NOT EXISTS ku_autoquiz(id INTEGER PRIMARY KEY, dl_course_id INT, ku_course_id INT, lesson_id INT, quiz_lesson_id INT, topic_no INT,
  tb_ids TEXT, ts TEXT, user_id INT, user_name TEXT);
CREATE INDEX IF NOT EXISTS ix_ku_aq ON ku_autoquiz(dl_course_id);
"""

def init(con):
    con.executescript(SCHEMA); con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


# =============================================================================================
# Sof taqsimot (bazasiz — birlik testlari shu yerni tekshiradi)
# =============================================================================================
def allocate(lessons: list[tuple], pool: dict, used: set, seed: str = "") -> tuple[dict, dict]:
    """lessons — [(dars kaliti, mavzu|None)] tartibda; pool — {mavzu: [tasdiqlangan savol id'lari]}; used — allaqachon ishlatilgan id'lar.
    → ({dars: [id…] (3–5, aralashtirilgan)}, {dars: o'tkazib yuborish sababi}). Dublikat yo'q: har id ko'pi bilan bir darsga."""
    out, skip = {}, {}
    by_topic: dict = {}
    for key, t in lessons:
        if t is None: skip[key] = "Darsning mavzusi aniqlanmadi (Test bank mavzu bo'yicha)"; continue
        by_topic.setdefault(t, []).append(key)
    taken = set(used)
    for t, keys in by_topic.items():
        free = sorted({int(x) for x in pool.get(t, [])} - taken)
        random.Random(f"{seed}|t{t}").shuffle(free)
        left = len(keys)
        for key in keys:
            k = min(MAX_Q, max(MIN_Q, len(free) // left))       # teng bo'lish; yetmasa — avvalgi darslarga kamida 3 tadan
            left -= 1
            if len(free) < MIN_Q:
                skip[key] = f"Mavzu bo'yicha tasdiqlangan bo'sh savollar yetarli emas ({len(free)} ta, kamida {MIN_Q} ta kerak)"
                continue
            pick, free = free[:k], free[k:]
            random.Random(f"{seed}|{key}").shuffle(pick)
            out[key] = pick
            taken |= set(pick)
    return out, skip


# =============================================================================================
# Bazadagi holat
# =============================================================================================
def _pool(dl_cid: int, topics: set) -> dict:
    if not topics or not db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_questions'"): return {}
    out: dict = {}
    for r in db.rows(_con, f"""SELECT id, topic_no FROM tb_questions WHERE course_id=? AND status='tasdiqlandi' AND deleted=0
                               AND topic_no IN ({','.join('?' * len(topics))})""", (int(dl_cid), *sorted(topics))):
        out.setdefault(r["topic_no"], []).append(r["id"])
    return out

def _used(dl_cid: int) -> set:
    """Shu fanda dars oxiri testlarida ishlatilgan savollar (test darsi o'chirilgan bo'lsa — bo'sh)."""
    out = set()
    for r in db.rows(_con, """SELECT a.tb_ids FROM ku_autoquiz a JOIN ku_lessons l ON l.id=a.quiz_lesson_id AND l.deleted=0
                              JOIN ku_courses k ON k.id=l.course_id AND k.deleted=0 WHERE a.dl_course_id=?""", (int(dl_cid),)):
        try: out |= {int(x) for x in json.loads(r["tb_ids"] or "[]")}
        except (ValueError, TypeError): pass
    return out

def _has_quiz(lesson_id: int) -> bool:
    return bool(db.one(_con, """SELECT 1 x FROM ku_autoquiz a JOIN ku_lessons l ON l.id=a.quiz_lesson_id AND l.deleted=0 WHERE a.lesson_id=?""", (int(lesson_id),)))

def _targets(kcid: int) -> tuple[int | None, list[tuple]]:
    """(fan id, [(dars id, mavzu)]) — kursning bloklar darslari va ularning Test bank mavzusi."""
    from . import paket as PK
    co = db.one(_con, "SELECT id, dl_course_id FROM ku_courses WHERE id=?", (int(kcid),))
    ls = db.rows(_con, "SELECT id, uid, title FROM ku_lessons WHERE course_id=? AND deleted=0 AND type='blocks' ORDER BY pos, id", (int(kcid),))
    link = db.one(_con, "SELECT dl_course_id, lkey FROM ds_links WHERE ku_course_id=?", (int(kcid),)) if \
        db.one(_con, "SELECT name FROM sqlite_master WHERE type='table' AND name='ds_links'") else None
    if link:                                  # «Dars tayyorlash» darsi: bitta NEXTID darsi — barcha bloklar darslari shu mavzu
        dco = db.one(_con, "SELECT id, topics, subject FROM dl_courses WHERE id=?", (link["dl_course_id"],))
        try: t = PK.source_topic(PK.lesson_info(dco, link["lkey"])) if dco else None
        except HTTPException: t = None
        return link["dl_course_id"], [(l["id"], t) for l in ls]
    dl = (co or {}).get("dl_course_id")
    if not dl: return None, [(l["id"], None) for l in ls]
    n = int((db.one(_con, "SELECT topics FROM dl_courses WHERE id=?", (dl,)) or {}).get("topics") or 15)
    return dl, [(l["id"], i if i <= n else None) for i, l in enumerate(ls, 1)]


# =============================================================================================
# Qo'shish
# =============================================================================================
def _apply(c: Ctx, kcid: int, plan: dict, dl_cid: int, topics: dict) -> list[dict]:
    """plan {dars id: [tb id]} → har darsdan keyin test darsi (uid «aq…»). Chaqiruvchi _lock ostida, commit — chaqiruvchida."""
    from . import kurs as KU
    if not plan: return []
    ids = [l["id"] for l in KU._lessons(kcid)]
    if len(ids) + len(plan) > KU.MAX_LESSONS:
        raise HTTPException(400, f"Kursda {KU.MAX_LESSONS} tadan ortiq dars bo'lmaydi ({len(ids)} + {len(plan)} test)")
    conv = {q["tb_id"]: q["data"] for q in KU.testbank_convert(c, [x for v in plan.values() for x in v])["questions"]}
    now = clock.now().replace(microsecond=0).isoformat(timespec="seconds")
    titles = {l["id"]: l["title"] for l in KU._lessons(kcid)}
    out = []
    for lid, qids in plan.items():
        qids = [x for x in qids if x in conv]               # ko'lamdan tashqari yoki shu orada tasdiqdan chiqqan — tushiriladi
        if len(qids) < MIN_Q: continue
        title = f"{titles.get(lid) or 'Dars'} — o'zini tekshirish"[:200]
        qlid = _con.execute("INSERT INTO ku_lessons(course_id,uid,pos,type,title,settings,rev,updated_at,updated_by) VALUES(?,?,0,'quiz',?,?,1,?,?)",
                            (kcid, KU._uid(UID_PREFIX), title, json.dumps(KU.clean_quiz(SETTINGS)), now, c.user["full_name"])).lastrowid
        for k, q in enumerate(qids, 1):
            _con.execute("INSERT INTO ku_blocks(lesson_id,uid,pos,type,data) VALUES(?,?,?,?,?)",
                         (qlid, KU._uid("q"), k, "question", json.dumps(conv[q], ensure_ascii=False)))
        ids.insert(ids.index(lid) + 1, qlid)
        _con.execute("""INSERT INTO ku_autoquiz(dl_course_id,ku_course_id,lesson_id,quiz_lesson_id,topic_no,tb_ids,ts,user_id,user_name)
                        VALUES(?,?,?,?,?,?,?,?,?)""", (dl_cid, kcid, lid, qlid, topics.get(lid), json.dumps(qids), now, c.user["id"], c.user["full_name"]))
        out.append({"lesson_id": lid, "lesson": titles.get(lid), "quiz_lesson_id": qlid, "questions": len(qids), "topic": topics.get(lid)})
    for i, x in enumerate(ids, 1): _con.execute("UPDATE ku_lessons SET pos=? WHERE id=?", (i, x))
    return out

def add_to_course(c: Ctx, kcid: int) -> dict:
    """Kurs muharriri: kursning har bloklar darsidan keyin test (testi yo'q darslarga)."""
    from . import kurs as KU
    KU._course(c, kcid, write=True)
    dl_cid, lessons = _targets(kcid)
    if not dl_cid: raise HTTPException(400, "Kurs masofaviy fanga bog'lanmagan — Test bank savollarini tanlash uchun «Sozlamalar»da fanni tanlang")
    with _lock:
        todo = [(lid, t) for lid, t in lessons if not _has_quiz(lid)]
        have = [lid for lid, _ in lessons if _has_quiz(lid)]
        plan, skip = allocate(todo, _pool(dl_cid, {t for _, t in todo if t}), _used(dl_cid), seed=f"ku{kcid}")
        if plan: KU.snapshot(c, kcid, "avto", "Dars oxiri testlari qo'shilishidan oldin")
        added = _apply(c, kcid, plan, dl_cid, dict(lessons))
        if added:
            KU._bump(kcid, c); KU._log(c, kcid, "dars oxiri testlari", f"{len(added)} ta test, {sum(a['questions'] for a in added)} savol")
        _con.commit()
    names = {l["id"]: l["title"] for l in KU._lessons(kcid)}
    rbac.audit(_con, c, "kurs: dars oxiri testlari", KU.RES, True, f"kurs #{kcid} · {len(added)} ta test · {len(skip)} o'tkazildi")
    return {"ok": True, "added": added, "skipped": [{"lesson_id": k, "lesson": names.get(k), "reason": v} for k, v in skip.items()],
            "already": len(have), "course": KU.course_view(c, kcid)}

def add_to_subject(c: Ctx, dl_cid: int) -> dict:
    """Dars tayyorlash: fanning muharrirga o'tkazilgan barcha darslari (ds_links) — savollar butun fan bo'yicha takrorlanmaydi."""
    from . import kurs as KU, paket as PK
    PK._course(c, dl_cid, write=True)
    links = db.rows(_con, """SELECT l.ku_course_id FROM ds_links l JOIN ku_courses k ON k.id=l.ku_course_id AND k.deleted=0 WHERE l.dl_course_id=?
                             ORDER BY l.lkey""", (int(dl_cid),))
    if not links: raise HTTPException(400, "Fanda muharrirga o'tkazilgan dars yo'q — avval «Fan skeleti» yoki «Muharrirda tahrirlash»")
    added, skipped, already = [], [], 0
    with _lock:
        alls = []
        for ln in links:
            KU._course(c, ln["ku_course_id"], write=True)
            _, ls = _targets(ln["ku_course_id"])
            alls += [(ln["ku_course_id"], lid, t) for lid, t in ls]
        todo = [(lid, t) for _, lid, t in alls if not _has_quiz(lid)]
        already = len(alls) - len(todo)
        plan, skip = allocate(todo, _pool(dl_cid, {t for _, t in todo if t}), _used(dl_cid), seed=f"dl{dl_cid}")
        owner = {lid: kc for kc, lid, _ in alls}
        topics = {lid: t for _, lid, t in alls}
        for kc in sorted({owner[l] for l in plan}):
            sub = {l: v for l, v in plan.items() if owner[l] == kc}
            KU.snapshot(c, kc, "avto", "Dars oxiri testi qo'shilishidan oldin")
            a = _apply(c, kc, sub, dl_cid, topics)
            if a:
                KU._bump(kc, c); KU._log(c, kc, "dars oxiri testi", f"{sum(x['questions'] for x in a)} savol")
            added += [{**x, "course_id": kc} for x in a]
        _con.commit()
    names = {r["id"]: r["title"] for r in db.rows(_con, f"SELECT id, title FROM ku_lessons WHERE id IN ({','.join(str(x) for x in skip) or '0'})")}
    skipped = [{"lesson_id": k, "course_id": owner.get(k), "lesson": names.get(k), "reason": v} for k, v in skip.items()]
    rbac.audit(_con, c, "dars: dars oxiri testlari", rbac.PAKET, True, f"fan #{dl_cid} · {len(added)} ta test · {len(skipped)} o'tkazildi")
    return {"ok": True, "added": added, "skipped": skipped, "already": already}


# =============================================================================================
# HTTP
# =============================================================================================
def C(request: Request) -> Ctx: return _ctx(request)

@router.post("/api/kurs/courses/{cid}/dars-testlari")
def api_course(cid: int, request: Request):
    from . import kurs as KU
    c = C(request); KU.guard(c, "dars oxiri testlari", KU.AUTHORS, f"kurs #{cid}")
    return add_to_course(c, cid)

@router.post("/api/dars/subjects/{dl_cid}/dars-testlari")
def api_subject(dl_cid: int, request: Request):
    from . import dars as DS
    c = C(request); DS.guard(c, "dars oxiri testlari", DS.AUTHORS, f"fan #{dl_cid}")
    return add_to_subject(c, dl_cid)
