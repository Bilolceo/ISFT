"""«Ortda qolganlar» — LRS statementlari asosida masofaviy kurslarda ortda qolayotgan talabalar (docs/lrs.md).

Manba: app/lrs.py (lrs_progress — talaba × dars jamlanmasi, lrs_statements — savollar javobi). Hisob — app/lrs_analytics.py (sof funksiyalar).

Kutilgan progress taqvim bo'yicha: kurs darslari (lrs_plan yoki «Dars tayyorlash» darslari / kurs muharriri darslari) semestr haftalariga teng
taqsimlanadi, har hafta boshida chiqariladi; joriy haftaning darslari hali talab qilinmaydi (grace_weeks). Qoidalar (chegaralar — lrs_policy,
bo'lim boshlig'i o'zgartiradi): taqvimdan ≥ N dars ortda, bitta testdan ≥ N marta o'tolmagan, ≥ N kun faolliksiz, umuman boshlamagan.

Kim nimani ko'radi (har so'rov audit jurnalida, resurs «lrs»):
  masofaviy, masofaviy_xodim — barcha masofaviy talabalar (ism, HEMIS ID, guruh), amallar: tyutorga biriktirish (Topshiriqlar tizimida vazifa),
                               eslatma (Talabalar markazi xabarlar navbati — SMS/Telegram, cheklov va jurnal bilan), «bog'lanildi» belgisi;
                               chegaralarni faqat bo'lim boshlig'i o'zgartiradi;
  tyutor                     — faqat o'z guruhlari (rbac.student_scope) va unga biriktirilgan talabalar; eslatma, «bog'lanildi»;
  oqituvchi                  — o'z kurslari: jamlangan ko'rsatkichlar, savollar tahlili; ro'yxatda faqat ism (o'z guruhlari, rbac ko'lami), kontakt yo'q;
  kafedra                    — o'z kafedrasi kurslari: faqat jamlangan sonlar va savollar tahlili;
  rektor, prorektor_oquv     — faqat jamlangan sonlar.
"""
from __future__ import annotations
import datetime as dt, json, threading, time
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock, db, rbac, lrs as L, lrs_analytics as LA
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
_lock = threading.Lock()
P = "/api/ortda"
RES = "lrs"

HEAD, STAFF = "masofaviy", "masofaviy_xodim"
DEPT = (HEAD, STAFF)
LEAD = ("rektor", "prorektor_oquv")
TUT, TEACH, KAF = "tyutor", "oqituvchi", "kafedra"
ALL = DEPT + LEAD + (TUT, TEACH, KAF)
LIST_ROLES = DEPT + (TUT, TEACH)          # individual qatorlar
ACT_ROLES = DEPT + (TUT,)                 # eslatma, «bog'lanildi»
QUESTION_ROLES = DEPT + (TEACH, KAF)      # savollar tahlili (kurs mualliflari)
CHANNELS = {"telegram": "Telegram", "sms": "SMS"}


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def C(request: Request) -> Ctx: return _ctx(request)

def guard(c: Ctx, action: str, roles=ALL, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"ortda qolganlar: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Ortda qolganlar: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")

def _now() -> dt.datetime: return clock.now().replace(microsecond=0)
def _iso(t) -> str: return t.isoformat(timespec="seconds")
def _short(n): return (n or "").split(":", 1)[1].strip() if ":" in (n or "") else (n or "")
def _tid(c: Ctx) -> int: return int(c.user.get("teacher_id") or 0)


# =============================================================================================
# Kurslar katalogi, darslar, ro'yxatdagi talabalar
# =============================================================================================
def _semester_start() -> dt.date:
    from . import academic_rules as AR
    return dt.date.fromisoformat(AR.term_dates(AR.CURRENT_SEMESTER)[0])

def _course_rows() -> list[dict]:
    """LRS ma'lumoti yoki rejasi bor kurslar (paket — dl:<id>, kurs muharriri — ku:<id>)."""
    # kuzatiladigan kurslar: LRS ma'lumoti yoki rejasi bor, yoki ISFT Core orqali kamida bir marta ishga tushirilgan (token berilgan).
    # Faqat eksport qilingan (hali hech kim ochmagan) kurs ro'yxatga kirmaydi — aks holda butun guruh «boshlamagan» bo'lib ko'rinardi.
    refs = {r["c"] for r in db.rows(_con, """SELECT DISTINCT course_ref c FROM lrs_progress UNION SELECT course_ref FROM lrs_plan
                                             UNION SELECT DISTINCT course_ref FROM lrs_tokens""") if r["c"]}
    dl_ids = [int(r.split(":")[1]) for r in refs if r.startswith("dl:")]
    ku_ids = [int(r.split(":")[1]) for r in refs if r.startswith("ku:")]
    out = []
    if dl_ids:
        for r in db.rows(_con, f"""SELECT c.*, d.name dept FROM dl_courses c LEFT JOIN departments d ON d.id=c.department_id
                                   WHERE c.id IN ({','.join('?' * len(dl_ids))})""", dl_ids):
            out.append({"ref": f"dl:{r['id']}", "kind": "dl", "title": r["subject"], "sub": f"{r['direction']} · {r['course']}-kurs", "subject": r["subject"],
                        "direction": r["direction"], "course": r["course"], "teacher_id": r["teacher_id"], "department_id": r["department_id"],
                        "dept": r["dept"], "dl_id": r["id"], "author_id": None})
    if ku_ids:
        for r in db.rows(_con, f"""SELECT k.*, c.direction, c.course, c.teacher_id, c.department_id, c.subject, d.name dept FROM ku_courses k
                                   LEFT JOIN dl_courses c ON c.id=k.dl_course_id LEFT JOIN departments d ON d.id=c.department_id
                                   WHERE k.id IN ({','.join('?' * len(ku_ids))}) AND k.deleted=0""", ku_ids):
            out.append({"ref": f"ku:{r['id']}", "kind": "ku", "title": r["title"], "sub": "Kurs muharriri" + (f" · {r['direction']} · {r['course']}-kurs" if r["direction"] else ""),
                        "subject": r["subject"], "direction": r["direction"], "course": r["course"], "teacher_id": r["teacher_id"],
                        "department_id": r["department_id"], "dept": r["dept"], "dl_id": r["dl_course_id"], "author_id": r["author_id"], "ku_id": r["id"]})
    out.sort(key=lambda x: (x["title"] or "", x["sub"] or ""))
    return out

def courses_for(c: Ctx) -> list[dict]:
    rows = _course_rows()
    k = c.role.key
    if k in DEPT or k in LEAD: return rows
    if k == KAF: return [r for r in rows if r["department_id"] and r["department_id"] == int(c.user.get("department_id") or 0)]
    if k == TEACH:
        t, u = _tid(c), int(c.user["id"])
        return [r for r in rows if (t and r["teacher_id"] == t) or (r["author_id"] and r["author_id"] == u)]
    if k == TUT:
        sids = _tutor_students(c)
        if not sids: return []
        have = {r["c"] for r in db.rows(_con, f"SELECT DISTINCT course_ref c FROM lrs_progress WHERE student_id IN ({','.join(map(str, sids))})")}
        groups = {(r["direction"], r["course"]) for r in db.rows(_con, f"""SELECT DISTINCT g.direction, g.course FROM students s JOIN groups_ g ON g.id=s.group_id
                                                                           WHERE s.id IN ({','.join(map(str, sids))}) AND s.study_form='masofaviy'""")}
        return [r for r in rows if r["ref"] in have or (r["direction"], r["course"]) in groups]
    return []

def _course(c: Ctx, ref: str) -> dict:
    for r in courses_for(c):
        if r["ref"] == ref: return r
    if any(r["ref"] == ref for r in _course_rows()):
        rbac.audit(_con, c, "ortda qolganlar: begona kurs", RES, False, ref)
        raise AccessDenied("⛔ Bu kurs sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    raise HTTPException(404, "Kurs topilmadi")

def _plan(ref: str) -> dict | None:
    r = db.one(_con, "SELECT * FROM lrs_plan WHERE course_ref=?", (ref,))
    if not r: return None
    try: ls = json.loads(r["lessons"] or "[]")
    except ValueError: ls = []
    return {"lessons": [x for x in ls if isinstance(x, dict) and x.get("ref")], "weeks": r["weeks"], "start": r["start"], "src": r["src"]}

def lessons_of(co: dict) -> list[dict]:
    """Taqvim tartibidagi darslar: reja (lrs_plan) > «Dars tayyorlash» darslari (har tur o'z raqamlari bo'yicha semestrga teng yoyiladi) >
    kurs muharriri darslari. Statementlarda uchragan, lekin ro'yxatda yo'q darslar oxiriga qo'shiladi."""
    ref = co["ref"]
    pl = _plan(ref)
    if pl and pl["lessons"]: out = [{"ref": x["ref"], "title": x.get("title") or x["ref"]} for x in pl["lessons"]]
    elif co["kind"] == "dl":
        try:
            from . import paket as PK
            ls = PK.lessons(int(co["dl_id"]))
        except Exception:
            ls = [{"code": f"L{i}", "title": f"{i}-mavzu", "kind": "maruza", "no": i} for i in range(1, 16)]
        cnt = {}
        for l in ls: cnt[l["kind"]] = cnt.get(l["kind"], 0) + 1
        ls = sorted(ls, key=lambda l: ((l["no"] - 0.5) / max(1, cnt[l["kind"]]), l["code"]))
        out = [{"ref": l["code"], "title": l["title"]} for l in ls]
    else:
        out = [{"ref": r["uid"], "title": r["title"], "id": r["id"], "type": r["type"], "code": ("T" if r["type"] == "quiz" else "") + str(i)}
               for i, r in enumerate(db.rows(_con, "SELECT id, uid, title, type FROM ku_lessons WHERE course_id=? AND deleted=0 ORDER BY pos, id", (int(co["ku_id"]),)), 1)]
    have = {x["ref"] for x in out}
    for r in db.rows(_con, "SELECT DISTINCT lesson_ref r FROM lrs_progress WHERE course_ref=? AND lesson_ref!=''", (ref,)):
        if r["r"] not in have: out.append({"ref": r["r"], "title": r["r"]}); have.add(r["r"])
    for x in out: x.setdefault("code", x["ref"] if len(x["ref"]) <= 5 else "?")   # ekranda qisqa kod (L3, A12, 2, T3); kurs muharriri uid'i ko'rsatilmaydi
    return out

def calendar(co: dict) -> tuple[dt.date, int]:
    pl = _plan(co["ref"]) or {}
    pol = L.policy()
    try: start = dt.date.fromisoformat(pl.get("start") or "")
    except ValueError: start = _semester_start()
    return start, int(pl.get("weeks") or pol["weeks"])

def enrolled(co: dict) -> list[int]:
    """Kursdagi talabalar: masofaviy guruhlar (yo'nalish × kurs, faol). Bog'lanmagan kurs muharriri kursi — statement yuborganlar."""
    if co.get("direction") and co.get("course"):
        return [r["id"] for r in db.rows(_con, """SELECT s.id FROM students s JOIN groups_ g ON g.id=s.group_id WHERE s.study_form='masofaviy' AND s.status='faol'
                                                  AND g.form='masofaviy' AND g.direction=? AND g.course=?""", (co["direction"], co["course"]))]
    return [r["s"] for r in db.rows(_con, "SELECT DISTINCT student_id s FROM lrs_progress WHERE course_ref=?", (co["ref"],))]

def _tutor_students(c: Ctx) -> list[int]:
    """Tyutor: o'z guruhlari (rbac.student_scope) + unga biriktirilgan (ochiq) talabalar."""
    own = {r["id"] for r in db.rows(_con, f"SELECT s.id FROM students s WHERE {c.student_scope('s')}")}
    own |= {r["student_id"] for r in db.rows(_con, "SELECT student_id FROM lrs_actions WHERE kind='tyutor' AND tutor_user=? AND status='ochiq'", (c.user["id"],))}
    return sorted(own)

def visible_students(c: Ctx) -> set | None:
    """None — cheklovsiz (bo'lim, jamlangan rollar uchun hisob); aks holda talaba id'lari to'plami."""
    k = c.role.key
    if k in DEPT or k in LEAD or k == KAF: return None
    if k == TUT: return set(_tutor_students(c))
    if k == TEACH: return {r["id"] for r in db.rows(_con, f"SELECT s.id FROM students s WHERE {c.student_scope('s')}")}
    return set()


# =============================================================================================
# Hisob: talaba × kurs qatorlari (30 s kesh — LRS yangi statement olganda tozalanadi)
# =============================================================================================
_CACHE: dict = {}

def _stamp() -> tuple:
    r = db.one(_con, "SELECT MAX(updated) u, COUNT(*) n FROM lrs_progress") or {}
    p = tuple(sorted(L.policy().items()))
    return (r.get("u"), r.get("n"), p, clock.today().isoformat())

def course_rows(co: dict) -> list[dict]:
    """Kursdagi har bir talaba: bajarilgan / kutilgan darslar, kechikish, muvaffaqiyatsiz urinishlar, oxirgi faollik, vaqt, sabablar."""
    key = (co["ref"], _stamp())
    hit = _CACHE.get(co["ref"])
    if hit and hit[0] == key and time.time() - hit[1] < 30: return hit[2]
    pol = L.policy()
    today = clock.today()
    lessons = lessons_of(co)
    refs = [l["ref"] for l in lessons]
    codes = {l["ref"]: l["code"] for l in lessons}
    start, weeks = calendar(co)
    exp = LA.expected_done(len(refs), start, today, weeks, pol["grace_weeks"])
    rel = LA.released(len(refs), start, today, weeks)
    prog: dict = {}
    for r in db.rows(_con, "SELECT * FROM lrs_progress WHERE course_ref=?", (co["ref"],)):
        prog.setdefault(r["student_id"], {})[r["lesson_ref"]] = r
    sids = set(enrolled(co)) | set(prog)
    info = {r["id"]: r for r in db.rows(_con, f"""SELECT s.id, s.full_name, s.hemis_id, s.group_id, s.status, g.name grp, g.course, g.direction, g.faculty_id
                                                   FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id IN ({','.join(map(str, sids)) or '0'})""")}
    out = []
    for sid in sorted(sids):
        st = info.get(sid)
        if not st or st["status"] != "faol": continue
        pr = prog.get(sid, {})
        done = sum(1 for l in refs if (pr.get(l) or {}).get("status") in LA.DONE_ST)
        unpassed = [(v["fails"] or 0, l) for l, v in pr.items() if l and v["status"] != "otdi" and (v["fails"] or 0) > 0]
        mf, fl = max(unpassed) if unpassed else (0, None)
        fl = codes.get(fl, fl) if fl else None
        last = max((v["last_ts"] or "" for v in pr.values()), default="") or None
        di = (today - dt.date.fromisoformat(last[:10])).days if last else None
        tsum = sum(float(v["time_s"] or 0) for v in pr.values())
        scores = [v["best"] for l, v in pr.items() if l and v["best"] is not None]
        row = {"expected": exp, "done": done, "max_fails": mf, "fail_lesson": fl, "days_inactive": di, "started": bool(pr)}
        rs = LA.risk_reasons(row, pol)
        out.append({"student_id": sid, "full_name": st["full_name"], "hemis_id": st["hemis_id"], "group_id": st["group_id"], "grp": st["grp"],
                    "course_ref": co["ref"], "course": co["title"], "course_sub": co["sub"], "lessons": len(refs), "released": rel, "expected": exp,
                    "done": done, "lag": max(0, exp - done), "pct": round(100 * done / len(refs), 1) if refs else 0, "max_fails": mf, "fail_lesson": fl,
                    "fails": sum(int(v["fails"] or 0) for v in pr.values()), "last": last, "days_inactive": di, "time_min": round(tsum / 60),
                    "avg_score": round(sum(scores) / len(scores), 1) if scores else None, "reasons": rs, "risk": sum(x["sev"] for x in rs),
                    "level": LA.risk_level(rs), "demo": bool(pr) and all(v["src"] == "demo" for v in pr.values())})
    _CACHE[co["ref"]] = (key, time.time(), out)
    return out

def all_rows(c: Ctx, course: str = "") -> list[dict]:
    cos = courses_for(c)
    if course: cos = [x for x in cos if x["ref"] == course]
    vis = visible_students(c)
    rows = []
    for co in cos:
        rows += [r for r in course_rows(co) if vis is None or r["student_id"] in vis]
    return rows

def _actions_map(sids: list[int]) -> dict:
    if not sids: return {}
    out = {}
    for r in db.rows(_con, f"""SELECT student_id, course_ref, kind, MAX(ts) ts, COUNT(*) n FROM lrs_actions WHERE student_id IN ({','.join(map(str, sids))})
                               GROUP BY student_id, course_ref, kind"""):
        out.setdefault((r["student_id"], r["course_ref"]), {})[r["kind"]] = {"ts": r["ts"], "n": r["n"]}
    return out


# =============================================================================================
# Kurs analitikasi: voronka, darslar, savollar
# =============================================================================================
def course_view(c: Ctx, ref: str) -> dict:
    co = _course(c, ref)
    lessons = lessons_of(co)
    rows = course_rows(co)
    prog = db.rows(_con, "SELECT student_id, lesson_ref, status, best, attempts, fails, time_s FROM lrs_progress WHERE course_ref=? AND lesson_ref!=''", (ref,))
    alive = {r["student_id"] for r in rows}
    stmap = {(p["student_id"], p["lesson_ref"]): p["status"] for p in prog if p["student_id"] in alive}
    fun = LA.funnel([l["ref"] for l in lessons], stmap, len(rows))
    by = {}
    for p in prog:
        if p["student_id"] not in alive: continue
        b = by.setdefault(p["lesson_ref"], {"scores": [], "attempts": 0, "fails": 0, "time": 0.0})
        if p["best"] is not None: b["scores"].append(p["best"])
        b["attempts"] += p["attempts"] or 0; b["fails"] += p["fails"] or 0; b["time"] += p["time_s"] or 0
    for f, l in zip(fun, lessons):
        b = by.get(l["ref"]) or {"scores": [], "attempts": 0, "fails": 0, "time": 0.0}
        f.update(title=l["title"], code=l["code"], avg_score=round(sum(b["scores"]) / len(b["scores"]), 1) if b["scores"] else None, attempts=b["attempts"], fail_attempts=b["fails"],
                 avg_min=round(b["time"] / 60 / f["started"], 1) if f["started"] else None)
    start, weeks = calendar(co)
    today = clock.today()
    lv = {"yuqori": 0, "orta": 0}
    for r in rows:
        if r["level"] in lv: lv[r["level"]] += 1
    return {"course": _pub_course(co), "lessons": fun, "enrolled": len(rows), "week": LA.week_no(start, today), "weeks": weeks,
            "released": LA.released(len(lessons), start, today, weeks), "expected": LA.expected_done(len(lessons), start, today, weeks, L.policy()["grace_weeks"]),
            "at_risk": sum(1 for r in rows if r["reasons"]), "levels": lv, "reasons": _reason_counts(rows),
            "avg_done": round(sum(r["done"] for r in rows) / len(rows), 1) if rows else 0, "plan_demo": (_plan(ref) or {}).get("src") == "demo",
            "can_questions": c.role.key in QUESTION_ROLES}

def _pub_course(co: dict) -> dict:
    return {k: co.get(k) for k in ("ref", "kind", "title", "sub", "dept")}

def _reason_counts(rows) -> list[dict]:
    cnt = {}
    for r in rows:
        for x in r["reasons"]: cnt[x["code"]] = cnt.get(x["code"], 0) + 1
    return [{"code": k, "label": LA.REASONS.get(k, k), "n": v} for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])]

def _editor_link(co: dict, item_ref: str, lesson_ref: str) -> dict | None:
    """Kurs muharririda savol bloki: {view: kurs, cid, lid, block}. Paket (Test bank savoli) — Dars tayyorlash darsi."""
    if co["kind"] == "ku":
        l = db.one(_con, "SELECT id FROM ku_lessons WHERE course_id=? AND uid=? AND deleted=0", (int(co["ku_id"]), lesson_ref))
        if not l: return None
        q = (item_ref or "").split("/")[-1]
        b = db.one(_con, "SELECT uid FROM ku_blocks WHERE lesson_id=? AND uid=?", (l["id"], q))
        return {"view": "kurs", "cid": int(co["ku_id"]), "lid": l["id"], "block": b["uid"] if b else None}
    from . import lrs as LL
    key = LL.code_to_key(lesson_ref)
    return {"view": "paket", "cid": int(co["dl_id"]), "no": key} if key is not None else None

def questions_view(c: Ctx, ref: str, lesson: str = "") -> dict:
    co = _course(c, ref)
    alive = {r["student_id"] for r in course_rows(co)}
    w, a = ["course_ref=?", "verb='answered'", "voided=0"], [ref]
    if lesson: w.append("lesson_ref=?"); a.append(lesson)
    ans = [{"student": r["student_id"], "item": r["activity"], "ts": r["ts"], "seq": i, "success": r["success"], "response": r["response"], "lesson": r["lesson_ref"],
            "item_ref": r["item_ref"]}
           for i, r in enumerate(db.rows(_con, f"SELECT student_id, activity, ts, success, response, lesson_ref, item_ref FROM lrs_statements WHERE {' AND '.join(w)} ORDER BY ts, stored", a))
           if r["student_id"] in alive]
    # har dars testi alohida to'plam (farqlash indeksi — o'sha test ichidagi boshqa savollar bo'yicha)
    by_lesson: dict = {}
    for x in ans: by_lesson.setdefault(x["lesson"], []).append(x)
    meta = {r["id"]: r for r in db.rows(_con, "SELECT * FROM lrs_activities WHERE course_ref=?", (ref,))}
    lm = {l["ref"]: l for l in lessons_of(co)}
    titles = {k: v["title"] for k, v in lm.items()}
    out = []
    for les, xs in by_lesson.items():
        st = LA.item_stats(xs)
        iref = {x["item"]: x["item_ref"] for x in xs}
        for it, s in st.items():
            m = meta.get(it) or {}
            try: ch = {str(x["id"]): x["text"] for x in json.loads(m.get("choices") or "[]")}
            except (ValueError, TypeError, KeyError): ch = {}
            tw = s["top_wrong"]
            tw_text = " + ".join(ch.get(p, p) for p in tw.split("[,]")) if tw else None
            out.append({"activity": it, "lesson": les, "lesson_code": (lm.get(les) or {}).get("code") or les, "lesson_title": titles.get(les, les),"name": m.get("name") or (iref.get(it) or it).split("/")[-1],
                        "text": m.get("description") or "", "itype": m.get("itype"), **s, "wrong_pct": round(100 * (1 - s["p"]), 1) if s["p"] is not None else None,
                        "top_wrong_text": tw_text, "link": _editor_link(co, iref.get(it) or "", les)})
    out.sort(key=lambda x: (x["p"] if x["p"] is not None else 2, -x["n"]))
    return {"course": _pub_course(co), "items": out[:400], "total": len(out), "min_n": 10,
            "note": "Qiyinlik (p) — birinchi urinishda to'g'ri javob bergan talabalar ulushi; farqlash (D) — o'sha testdagi boshqa savollar bo'yicha "
                    "kuchli va kuchsiz 27 % guruhlar farqi (≥ 10 javobda). D < 0,2 — savol bilganni bilmaganidan yaxshi ajratmaydi."}


# =============================================================================================
# Amallar: tyutorga biriktirish, eslatma, «bog'lanildi»
# =============================================================================================
def _student_in_scope(c: Ctx, sid: int) -> dict:
    s = db.one(_con, """SELECT s.id, s.full_name, s.phone, s.hemis_id, s.group_id, s.faculty_id, s.study_form, g.name grp FROM students s
                        LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?""", (int(sid),))
    if not s: raise HTTPException(404, "Talaba topilmadi")
    vis = visible_students(c)
    ok = (s["study_form"] == "masofaviy" or db.one(_con, "SELECT 1 x FROM lrs_progress WHERE student_id=?", (sid,))) if vis is None else sid in vis
    if not ok:
        rbac.audit(_con, c, "ortda qolganlar: begona talaba", RES, False, f"talaba #{sid}")
        raise AccessDenied("⛔ Bu talaba sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    return s

def _log(c: Ctx, sid: int, ref: str, kind: str, note: str = "", tutor: int | None = None, task: int | None = None, notice: int | None = None) -> int:
    return _con.execute("""INSERT INTO lrs_actions(ts,student_id,course_ref,kind,user_id,user_name,tutor_user,task_id,notice_id,note) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (_iso(_now()), sid, ref, kind, c.user["id"], c.user["full_name"], tutor, task, notice, (note or "")[:500])).lastrowid

def tutors_for(sid: int) -> list[dict]:
    """Tyutor nomzodlari: talaba guruhining tyutori (tutor_groups) birinchi, keyin talaba fakultetining faol tyutorlari."""
    s = db.one(_con, "SELECT s.group_id, s.faculty_id, g.faculty_id gf FROM students s LEFT JOIN groups_ g ON g.id=s.group_id WHERE s.id=?", (sid,)) or {}
    own = db.one(_con, "SELECT user_id FROM tutor_groups WHERE group_id=?", (s.get("group_id") or 0,))
    fac = s.get("faculty_id") or s.get("gf") or 0
    rows = db.rows(_con, "SELECT id, full_name, faculty_id FROM users WHERE role='tyutor' AND COALESCE(active,1)!=0 ORDER BY (faculty_id=?) DESC, id", (fac,))
    out = []
    for r in rows:
        out.append({"id": r["id"], "name": _short(r["full_name"]) or r["full_name"], "group_tutor": bool(own and own["user_id"] == r["id"]),
                    "same_faculty": r["faculty_id"] == fac})
    out.sort(key=lambda x: (not x["group_tutor"], not x["same_faculty"], x["id"]))
    return out

def assign(c: Ctx, sid: int, ref: str, tutor: int, note: str = "") -> dict:
    """Topshiriqlar tizimida (app/directives.py) tyutorga vazifa: talaba, kurs, sabablar; muddat — 3 ish kuni. «Mening vazifalarim»da chiqadi."""
    from . import directives as DIR, decisions as DEC, portal as PT, mywork as MW
    s = _student_in_scope(c, sid)
    co = _course(c, ref)
    tu = db.one(_con, "SELECT * FROM users WHERE id=? AND role='tyutor' AND COALESCE(active,1)!=0", (int(tutor),))
    if not tu: raise HTTPException(400, "Tyutor topilmadi")
    row = next((r for r in course_rows(co) if r["student_id"] == sid), None)
    why = "; ".join(x["label"] for x in (row or {}).get("reasons", [])) or "o'qituvchi/bo'lim kuzatuvi"
    due = clock.today() + dt.timedelta(days=3)
    while due.weekday() >= 5: due += dt.timedelta(days=1)
    title = f"Masofaviy ta'lim: ortda qolgan talaba bilan bog'laning — {s['full_name']} ({s['grp'] or ''})"
    body = (f"Kurs: {co['title']} ({co['sub']}).\nSabab: {why}.\n"
            + (f"Progress: {row['done']}/{row['expected']} kutilgan dars, oxirgi faollik: {(row['last'] or '—')[:10]}.\n" if row else "")
            + (f"Izoh: {note.strip()}\n" if note.strip() else "")
            + "Talaba bilan bog'laning, sababini aniqlang va natijani shu topshiriqqa yozing.")
    with _lock:
        tid = DIR._insert(_con, c.user["id"], DEC.unit_of(c), None, title, body, DEC.task_key(PT.unit_key(tu)), tu["id"], f"{due.isoformat()}T18:00",
                          "muhim" if row and row["level"] == "yuqori" else "oddiy", "Talaba bilan suhbat natijasi va keyingi qadam", None, None)
        aid = _log(c, sid, ref, "tyutor", note, tutor=tu["id"], task=tid)
        _con.execute("UPDATE tasks SET src=? WHERE id=?", (f"lrs:{aid}", tid))
        DEC._log(tid, c, "topshiriq berildi", f"{_short(tu['full_name'])} · Ortda qolganlar")
        _con.commit()
    try: MW.invalidate(tu["id"])
    except Exception: pass
    rbac.audit(_con, c, "ortda qolganlar: tyutorga biriktirildi", RES, True, f"talaba #{sid} · {ref} → tyutor #{tu['id']} · topshiriq #{tid}")
    return {"ok": True, "task_id": tid, "tutor": _short(tu["full_name"]), "due": due.isoformat()}

_REMIND_DAY: dict = {}

def remind(c: Ctx, sid: int, ref: str, channel: str = "telegram") -> dict:
    """Eslatma — Talabalar markazining xabarlar navbatiga (ops_notices; SMS/Telegram shlyuzi ulanganda yuboriladi). Cheklov: bitta talabaga
    `remind_cooldown_days` kunda bir marta (kurs farqi yo'q), bitta xodim kuniga `remind_daily_max` ta. Har biri lrs_actions va audit jurnalida."""
    if channel not in CHANNELS: raise HTTPException(400, "Kanal: telegram yoki sms")
    s = _student_in_scope(c, sid)
    co = _course(c, ref)
    pol = L.policy()
    since = _iso(_now() - dt.timedelta(days=pol["remind_cooldown_days"]))
    last = db.one(_con, "SELECT MAX(ts) t FROM lrs_actions WHERE student_id=? AND kind='eslatma' AND ts>=?", (sid, since))
    if last and last["t"]:
        rbac.audit(_con, c, "ortda qolganlar: eslatma cheklovi", RES, False, f"talaba #{sid} · oxirgi {last['t']}")
        raise HTTPException(429, f"Bu talabaga {last['t'][:10]} kuni eslatma yuborilgan — keyingisi {pol['remind_cooldown_days']} kundan keyin")
    day = clock.today().isoformat()
    n_today = db.one(_con, "SELECT COUNT(*) n FROM lrs_actions WHERE user_id=? AND kind='eslatma' AND ts>=?", (c.user["id"], day))["n"]
    if n_today >= pol["remind_daily_max"]: raise HTTPException(429, f"Bugungi eslatmalar chegarasi ({pol['remind_daily_max']} ta) tugadi")
    if channel == "sms" and not s["phone"]: raise HTTPException(400, "Talabaning telefon raqami yo'q — Telegram kanalini tanlang")
    row = next((r for r in course_rows(co) if r["student_id"] == sid), None)
    nxt = _next_lesson(co, sid)
    link = None
    if nxt and L.package_for(ref, nxt["ref"] if co["kind"] == "dl" else ""):
        link = "/xapi/l/" + L.make_link(sid, ref, nxt["ref"] if co["kind"] == "dl" else "")
    name = (s["full_name"].split() + [""])[1] or s["full_name"]
    text = (f"Hurmatli {name}! ISFT masofaviy ta'lim: «{co['title']}» kursida "
            + (f"{row['lag']} ta dars ortda qoldingiz ({row['done']}/{row['expected']}). " if row and row["lag"] else "darslaringizni davom ettiring. ")
            + (f"Keyingi dars: {nxt['title']}. " if nxt else "") + (f"Havola: {link}" if link else "Savollar bo'lsa — tyutoringizga murojaat qiling."))
    with _lock:
        nid = _con.execute("INSERT INTO ops_notices(ts,channel,task_id,case_id,student_id,phone,text,status,user_id) VALUES(?,?,?,?,?,?,?,?,?)",
                           (_iso(_now()), channel, None, None, sid, s["phone"] if channel == "sms" else None, text[:900], "navbatda", c.user["id"])).lastrowid
        _log(c, sid, ref, "eslatma", f"{CHANNELS[channel]} · navbatda", notice=nid)
        _con.commit()
    rbac.audit(_con, c, "ortda qolganlar: eslatma", RES, True, f"talaba #{sid} · {ref} · {channel} · xabar #{nid}")
    return {"ok": True, "notice_id": nid, "channel": CHANNELS[channel], "text": text, "link": link,
            "gateway": f"{CHANNELS[channel]} shlyuzi ulanmagan (demo): xabar chiqish navbatiga yozildi va ulanganda yuboriladi."}

def _next_lesson(co: dict, sid: int) -> dict | None:
    pr = {r["lesson_ref"]: r["status"] for r in db.rows(_con, "SELECT lesson_ref, status FROM lrs_progress WHERE student_id=? AND course_ref=?", (sid, co["ref"]))}
    for l in lessons_of(co):
        if pr.get(l["ref"]) not in LA.DONE_ST: return l
    return None

def contacted(c: Ctx, sid: int, ref: str, note: str = "") -> dict:
    _student_in_scope(c, sid)
    _course(c, ref)
    with _lock:
        aid = _log(c, sid, ref, "boglanildi", note)
        # tyutor o'ziga biriktirilgan ishni «bog'lanildi» deb belgilasa — biriktirma yopiladi (topshiriqni o'zi Topshiriqlar sahifasida yakunlaydi)
        if c.role.key == TUT:
            _con.execute("UPDATE lrs_actions SET status='yopildi' WHERE kind='tyutor' AND student_id=? AND course_ref=? AND tutor_user=? AND status='ochiq'",
                         (sid, ref, c.user["id"]))
        _con.commit()
    rbac.audit(_con, c, "ortda qolganlar: bog'lanildi", RES, True, f"talaba #{sid} · {ref}")
    return {"ok": True, "id": aid}


# =============================================================================================
# HTTP
# =============================================================================================
def _caps(c: Ctx) -> dict:
    k = c.role.key
    return {"list": k in LIST_ROLES, "names": k in LIST_ROLES, "hemis": k in DEPT, "assign": k in DEPT, "remind": k in ACT_ROLES, "contacted": k in ACT_ROLES,
            "policy": k == HEAD, "questions": k in QUESTION_ROLES, "aggregate_only": k not in LIST_ROLES, "launch": k in DEPT}

@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "ko'rish")
    cos = courses_for(c)
    pol = L.policy()
    start = _semester_start()
    scope = {HEAD: "Barcha masofaviy talabalar", STAFF: "Barcha masofaviy talabalar", TUT: "Biriktirilgan guruhlar va sizga biriktirilgan talabalar",
             TEACH: "O'z kurslaringiz", KAF: "Kafedra kurslari (jamlangan)", "rektor": "Institut (jamlangan)", "prorektor_oquv": "Institut (jamlangan)"}[c.role.key]
    na = {r["c"]: r["n"] for r in db.rows(_con, "SELECT course_ref c, COUNT(*) n FROM lrs_statements WHERE verb='answered' AND voided=0 GROUP BY course_ref")}
    dq = max(cos, key=lambda x: na.get(x["ref"], 0))["ref"] if cos else ""
    return {"role": c.role.key, "scope": scope, "caps": _caps(c), "courses": [_pub_course(x) for x in cos], "default_q": dq, "policy": pol,
            "policy_meta": [{"k": k, "label": lb, "min": lo, "max": hi} for k, _, lb, (lo, hi) in LA.POLICY], "reasons": LA.REASONS,
            "today": clock.today().isoformat(), "week": LA.week_no(start, clock.today()), "source": L.source(), "channels": CHANNELS}

@router.get(P + "/summary")
def api_summary(request: Request, course: str = ""):
    """Jamlangan sonlar (hamma rollar): kurslar bo'yicha talabalar, xavf ostida, sabablar, o'rtacha bajarilgan — ism yo'q."""
    c = C(request); guard(c, "jamlangan ko'rsatkichlar", detail=course)
    rows = all_rows(c, course)
    by = {}
    for r in rows:
        b = by.setdefault(r["course_ref"], {"ref": r["course_ref"], "title": r["course"], "sub": r["course_sub"], "students": 0, "at_risk": 0, "high": 0,
                                            "done": 0, "expected": r["expected"], "lessons": r["lessons"], "reasons": {}})
        b["students"] += 1; b["done"] += r["done"]
        if r["reasons"]: b["at_risk"] += 1
        if r["level"] == "yuqori": b["high"] += 1
        for x in r["reasons"]: b["reasons"][x["code"]] = b["reasons"].get(x["code"], 0) + 1
    out = []
    for b in by.values():
        b["avg_done"] = round(b.pop("done") / b["students"], 1) if b["students"] else 0
        b["risk_pct"] = round(100 * b["at_risk"] / b["students"], 1) if b["students"] else 0
        out.append(b)
    out.sort(key=lambda x: -x["risk_pct"])
    return {"courses": out, "students": len(rows), "at_risk": sum(1 for r in rows if r["reasons"]), "high": sum(1 for r in rows if r["level"] == "yuqori"),
            "reasons": _reason_counts(rows), "demo": bool(rows) and all(r["demo"] for r in rows if r["done"] or r["last"])}

@router.get(P + "/list")
def api_list(request: Request, course: str = "", reason: str = "", level: str = "", q: str = "", group: int = 0, only_risk: bool = True,
             offset: int = 0, limit: int = 50):
    c = C(request); guard(c, "ro'yxat", LIST_ROLES, f"{course} {reason}".strip())
    rows = all_rows(c, course)
    if only_risk: rows = [r for r in rows if r["reasons"]]
    if reason: rows = [r for r in rows if any(x["code"] == reason for x in r["reasons"])]
    if level: rows = [r for r in rows if r["level"] == level]
    if group: rows = [r for r in rows if r["group_id"] == group]
    if q:
        ql = q.lower().strip()
        rows = [r for r in rows if ql in (r["full_name"] or "").lower() or ql in (r["grp"] or "").lower() or (c.role.key in DEPT and ql in str(r["hemis_id"] or ""))]
    rows.sort(key=lambda r: (-r["risk"], -r["lag"], r["full_name"] or ""))
    total = len(rows)
    page = rows[max(0, offset): max(0, offset) + max(1, min(200, limit))]
    acts = _actions_map([r["student_id"] for r in page])
    hemis = c.role.key in DEPT
    items = []
    for r in page:
        it = {k: r[k] for k in ("student_id", "full_name", "grp", "group_id", "course_ref", "course", "course_sub", "lessons", "released", "expected", "done", "lag",
                                "pct", "max_fails", "fail_lesson", "fails", "last", "days_inactive", "time_min", "avg_score", "reasons", "risk", "level", "demo")}
        if hemis: it["hemis_id"] = r["hemis_id"]
        a = acts.get((r["student_id"], r["course_ref"]), {})
        it["actions"] = {k: v for k, v in a.items()}
        items.append(it)
    groups = sorted({(r["group_id"], r["grp"]) for r in all_rows(c, course) if r["group_id"]}, key=lambda x: x[1] or "")
    return {"items": items, "total": total, "offset": offset, "groups": [{"id": g, "name": n} for g, n in groups][:300]}

@router.get(P + "/student/{sid}")
def api_student(sid: int, request: Request, course: str = ""):
    c = C(request); guard(c, "talaba darslari", LIST_ROLES, f"talaba #{sid} · {course}")
    s = _student_in_scope(c, sid)
    co = _course(c, course)
    pr = {r["lesson_ref"]: r for r in db.rows(_con, "SELECT * FROM lrs_progress WHERE student_id=? AND course_ref=?", (sid, course))}
    start, weeks = calendar(co)
    ls = lessons_of(co)
    today = clock.today()
    out = []
    for i, l in enumerate(ls):
        p = pr.get(l["ref"]) or {}
        rel_week = next((w for w in range(1, weeks + 1) if LA.released(len(ls), start, start + dt.timedelta(weeks=w - 1), weeks) > i), None)
        out.append({"ref": l["ref"], "code": l["code"], "title": l["title"], "status": p.get("status") or "boshlanmagan", "status_label": LA.STATUS.get(p.get("status") or "boshlanmagan"),
                    "pct": p.get("pct") or 0, "score": p.get("score"), "best": p.get("best"), "attempts": p.get("attempts") or 0, "fails": p.get("fails") or 0,
                    "time_min": round((p.get("time_s") or 0) / 60), "last": p.get("last_ts"), "week": rel_week,
                    "released": bool(rel_week and start + dt.timedelta(weeks=rel_week - 1) <= today)})
    row = next((r for r in course_rows(co) if r["student_id"] == sid), None)
    acts = db.rows(_con, "SELECT ts, kind, user_name, note, task_id, tutor_user FROM lrs_actions WHERE student_id=? ORDER BY id DESC LIMIT 30", (sid,))
    for a in acts: a["user_name"] = _short(a["user_name"]) or a["user_name"]
    st = {"id": s["id"], "full_name": s["full_name"], "grp": s["grp"]}
    if c.role.key in DEPT: st["hemis_id"] = s["hemis_id"]
    return {"student": st, "course": _pub_course(co), "lessons": out, "row": row and {k: row[k] for k in ("done", "expected", "lag", "reasons", "level", "last", "time_min")},
            "actions": acts if c.role.key in ACT_ROLES else [], "tutors": tutors_for(sid)[:40] if c.role.key in DEPT else []}

@router.get(P + "/course")
def api_course(request: Request, ref: str):
    c = C(request); guard(c, "kurs analitikasi", detail=ref)
    return course_view(c, ref)

@router.get(P + "/questions")
def api_questions(request: Request, ref: str, lesson: str = ""):
    c = C(request); guard(c, "savollar tahlili", QUESTION_ROLES, ref)
    return questions_view(c, ref, lesson)

class ActIn(BaseModel):
    student_id: int
    course_ref: str = Field(..., max_length=20)
    note: str = Field("", max_length=500)
    tutor_id: int = 0
    channel: str = "telegram"

@router.post(P + "/assign")
def api_assign(body: ActIn, request: Request):
    c = C(request); guard(c, "tyutorga biriktirish", DEPT, f"talaba #{body.student_id}")
    if not body.tutor_id: raise HTTPException(400, "Tyutorni tanlang")
    return assign(c, body.student_id, body.course_ref, body.tutor_id, body.note)

@router.post(P + "/remind")
def api_remind(body: ActIn, request: Request):
    c = C(request); guard(c, "eslatma", ACT_ROLES, f"talaba #{body.student_id}")
    return remind(c, body.student_id, body.course_ref, body.channel)

@router.post(P + "/contacted")
def api_contacted(body: ActIn, request: Request):
    c = C(request); guard(c, "bog'lanildi", ACT_ROLES, f"talaba #{body.student_id}")
    return contacted(c, body.student_id, body.course_ref, body.note)

@router.post(P + "/policy")
def api_policy(body: dict, request: Request):
    c = C(request); guard(c, "chegaralarni o'zgartirish", (HEAD,))
    lim = {k: (lo, hi) for k, _, _, (lo, hi) in LA.POLICY}
    ch = []
    with _lock:
        for k, v in (body or {}).items():
            if k not in lim: raise HTTPException(400, f"Noma'lum chegara: {k}")
            try: v = int(v)
            except (TypeError, ValueError): raise HTTPException(400, f"{k}: butun son kerak")
            lo, hi = lim[k]
            if not lo <= v <= hi: raise HTTPException(400, f"{k}: {lo}–{hi} oralig'ida bo'lishi kerak")
            _con.execute("INSERT OR REPLACE INTO lrs_policy(k,v) VALUES(?,?)", (k, v)); ch.append(f"{k}={v}")
        _con.commit()
    _CACHE.clear()
    rbac.audit(_con, c, "ortda qolganlar: chegaralar", RES, True, ", ".join(ch))
    return {"ok": True, "policy": L.policy()}
