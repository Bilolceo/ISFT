"""AI tutor — xodimlar uchun API (/api/tutor/*, «Ortda qolganlar» → «AI tutor» yorlig'i, static/tutor_admin.js).

Ruxsat (har so'rov audit jurnalida, resurs «lrs»):
  masofaviy (bo'lim boshlig'i) — pilot yoqish/o'chirish, rejim (hammaga / tajriba), kunlik cheklov; masofaviy, masofaviy_xodim — hamma
  pilotlar: statistika, eng ko'p so'ralgan savollar, jurnal, shikoyatlar, o'qituvchiga savollar, indeksni qayta qurish, «tutor bilan» eksport;
  oqituvchi — FAQAT o'z kurslari (dl_courses.teacher_id yoki muharrir kursi muallifi): statistika, savollar, jurnal, javob yozish;
  rektor, prorektor_oquv — faqat jamlangan sonlar va tajriba taqqoslash (jurnal va savol matnlari yo'q).
Jurnalda talaba ismi yo'q — taxallus (T-xxxxxx). «Eng ko'p so'ralgan savollar» — o'xshash savollar guruhlanadi, kamida 2 xil talaba so'ragan
guruhlargina ko'rsatiladi (bitta talabani tanib bo'lmasin).
"""
from __future__ import annotations
import io, json, secrets, zipfile
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from . import clock, db, rbac, tutor as TU, tutor_index as TI, tutor_llm as LLM, tutor_text as TT
from .rbac import Ctx, AccessDenied

router = APIRouter()
P = "/api/tutor"
RES = "lrs"
HEAD, STAFF, TEACH = "masofaviy", "masofaviy_xodim", "oqituvchi"
DEPT = (HEAD, STAFF)
LEAD = ("rektor", "prorektor_oquv")
VIEW = DEPT + LEAD + (TEACH,)
LOGS = DEPT + (TEACH,)


def C(request: Request) -> Ctx: return TU._ctx(request)


def guard(c: Ctx, action: str, roles=VIEW, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(TU._con, c, f"AI tutor: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ AI tutor: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")


def _title(ref: str) -> dict:
    kind, _, cid = ref.partition(":")
    if kind == "dl":
        r = db.one(TU._con, "SELECT subject, direction, course, teacher_id FROM dl_courses WHERE id=?", (int(cid),)) or {}
        return {"title": r.get("subject") or ref, "sub": f"{r.get('direction', '')} · {r.get('course', '')}-kurs", "teacher_id": r.get("teacher_id"), "author_id": None}
    r = db.one(TU._con, """SELECT k.title, k.author_id, c.teacher_id FROM ku_courses k LEFT JOIN dl_courses c ON c.id=k.dl_course_id WHERE k.id=?""", (int(cid),)) or {}
    return {"title": r.get("title") or ref, "sub": "Kurs muharriri", "teacher_id": r.get("teacher_id"), "author_id": r.get("author_id")}


def scope(c: Ctx) -> set | None:
    """None — barcha pilotlar; aks holda ko'rinadigan pilot kurslar to'plami (o'qituvchi — o'z kurslari)."""
    if c.role.key in DEPT + LEAD: return None
    tid, uid = int(c.user.get("teacher_id") or 0), int(c.user["id"])
    out = set()
    for ref in TU.pilots():
        t = _title(ref)
        if (tid and t["teacher_id"] == tid) or (t["author_id"] and t["author_id"] == uid): out.add(ref)
    return out


def _pilot(c: Ctx, ref: str) -> dict:
    p = TU.pilots().get(ref)
    if not p: raise HTTPException(404, "Pilot kurs topilmadi")
    sc = scope(c)
    if sc is not None and ref not in sc:
        rbac.audit(TU._con, c, "AI tutor: begona kurs", RES, False, ref)
        raise AccessDenied("⛔ Bu kurs sizning ko'lamingizda emas. So'rov audit jurnaliga yozildi.")
    return p


def candidates() -> list[dict]:
    """Pilot uchun tanlanadigan kurslar: tasdiqlangan paket darsi yoki bog'langan tasdiqlangan muharrir kursi bor masofaviy kurslar + tasdiqlangan muharrir kurslari."""
    con = TU._con
    ids = {r["c"] for r in db.rows(con, "SELECT DISTINCT course_id c FROM pk_packages WHERE status='tasdiqlandi' AND mode!='none'")}
    try: ids |= {r["c"] for r in db.rows(con, "SELECT DISTINCT dl_course_id c FROM ds_links WHERE authority='kurs'")}
    except Exception: pass
    out = [{"ref": f"dl:{i}", **_title(f"dl:{i}")} for i in sorted(x for x in ids if x)]
    out += [{"ref": f"ku:{r['id']}", **_title(f"ku:{r['id']}")} for r in db.rows(con, "SELECT id FROM ku_courses WHERE status='tasdiqlangan' AND deleted=0 ORDER BY id")]
    return out


def pilot_row(ref: str, p: dict) -> dict:
    ix = db.one(TU._con, "SELECT * FROM tu_index WHERE pilot_ref=?", (ref,)) or {}
    n = db.one(TU._con, "SELECT COUNT(*) n, COUNT(DISTINCT student_id) s FROM tu_log WHERE pilot_ref=? AND mode IN ('javob','maslahat','topilmadi','rad')", (ref,)) or {}
    groups = {"tajriba": 0, "nazorat": 0}
    if p["mode"] == "tajriba":
        from . import tajriba as TJ
        for g in _groups(ref): groups[TJ.arm("tutor:" + ref, p["salt"] or "", g)] += 1
    return {"ref": ref, **_title(ref), "enabled": bool(p["enabled"]), "mode": p["mode"], "daily_limit": p["daily_limit"], "started_at": p["started_at"],
            "updated_at": p["updated_at"], "updated_by": p["updated_by"], "index": {k: ix.get(k) for k in ("built_at", "n_chunks", "n_items", "n_suspicious", "n_lessons")},
            "questions": n.get("n") or 0, "students": n.get("s") or 0, "groups": groups}


def _groups(ref: str) -> list[int]:
    return sorted({r["g"] for r in db.rows(TU._con, f"SELECT DISTINCT group_id g FROM students WHERE id IN ({','.join(map(str, _enrolled(ref))) or '0'})") if r["g"]})


def _enrolled(ref: str) -> list[int]:
    from . import ortda as ORT
    kind, _, cid = ref.partition(":")
    if kind == "dl":
        r = db.one(TU._con, "SELECT direction, course FROM dl_courses WHERE id=?", (int(cid),)) or {}
        return ORT.enrolled({"ref": ref, **r})
    dls = [r["c"] for r in db.rows(TU._con, "SELECT dl_course_id c FROM ds_links WHERE ku_course_id=? AND authority='kurs'", (int(cid),))]
    if dls:
        out = set()
        for d in dls: out |= set(_enrolled(f"dl:{d}"))
        return sorted(out)
    try:
        from . import isft_ready as RDY
        i = RDY.info(TU._con)
        if i and i["id"] == int(cid): return ORT.enrolled({"ref": ref, "ready": True})
    except Exception:
        pass
    return ORT.enrolled({"ref": ref})


# =============================================================================================
# Hisob-kitob
# =============================================================================================
def stats(ref: str) -> dict:
    con = TU._con
    rows = db.rows(con, "SELECT mode, COUNT(*) n, SUM(tok_in) i, SUM(tok_out) o, SUM(cost) c, SUM(dropped) d, SUM(flagged) f, SUM(injection) j FROM tu_log WHERE pilot_ref=? GROUP BY mode", (ref,))
    by = {r["mode"]: r["n"] for r in rows}
    tot = sum(by.get(k, 0) for k in TU.COUNTED)
    s = db.one(con, "SELECT COUNT(DISTINCT student_id) s, COUNT(DISTINCT day) d FROM tu_log WHERE pilot_ref=?", (ref,)) or {}
    return {"questions": tot, "by_mode": by, "students": s.get("s") or 0, "days": s.get("d") or 0,
            "not_found_pct": round(100 * by.get("topilmadi", 0) / tot, 1) if tot else None,
            "tokens_in": sum(r["i"] or 0 for r in rows), "tokens_out": sum(r["o"] or 0 for r in rows), "cost_usd": round(sum(r["c"] or 0 for r in rows), 4),
            "dropped": sum(r["d"] or 0 for r in rows), "flagged": sum(r["f"] or 0 for r in rows), "injection": sum(r["j"] or 0 for r in rows),
            "teacher_open": (db.one(con, "SELECT COUNT(*) n FROM tu_teacher_q WHERE pilot_ref=? AND status='ochiq'", (ref,)) or {}).get("n") or 0}


def top_questions(ref: str, limit: int = 15, min_students: int = 2) -> list[dict]:
    """O'xshash savollar guruhi (o'zaklar Jaccard ≥ 0,5). Faqat ≥ min_students xil talaba so'ragan guruhlar — anonim."""
    rows = db.rows(TU._con, "SELECT student_id, question, mode, lesson_ref FROM tu_log WHERE pilot_ref=? AND mode IN ('javob','maslahat','topilmadi') ORDER BY id DESC LIMIT 3000", (ref,))
    cl = []
    for r in rows:
        st = set(TT.stems(r["question"]))
        if not st: continue
        best = None
        for g in cl:
            j = len(st & g["st"]) / len(st | g["st"])
            if j >= 0.5 and (not best or j > best[0]): best = (j, g)
        if best:
            g = best[1]; g["n"] += 1; g["s"].add(r["student_id"]); g["nf"] += r["mode"] == "topilmadi"; g["lessons"].add(r["lesson_ref"])
            if len(r["question"]) < len(g["q"]): g["q"] = r["question"]
        else:
            cl.append({"st": st, "q": r["question"], "n": 1, "s": {r["student_id"]}, "nf": int(r["mode"] == "topilmadi"), "lessons": {r["lesson_ref"]}})
    out = [{"question": TT.scrub(g["q"])[:300], "count": g["n"], "students": len(g["s"]), "not_found": g["nf"],
            "lessons": sorted(x for x in g["lessons"] if x)[:5]} for g in cl if len(g["s"]) >= min_students]
    out.sort(key=lambda x: (-x["students"], -x["count"]))
    return out[:limit]


def compare(ref: str) -> dict:
    """Tajriba qo'llari bo'yicha natija: talaba — bitta kuzatuv; y — kamida bitta test/darsdan o'tgan (lrs_progress «otdi»), lessons — yakunlangan
    darslar, o'rtacha eng yaxshi ball; tutor savollari soni. Taqqoslash — app/tajriba.compare (guruhlar darajasida 95 % oraliq)."""
    from . import tajriba as TJ, lrs_analytics as LA
    p = TU.pilots()[ref]
    refs = [ref] + [s["src"] for s in TI.sources(TU._con, ref) if s["src"] != ref]
    sids = _enrolled(ref)
    if not sids: return {"mode": p["mode"], "rows": 0, "result": TJ.compare([]), "score": {}, "usage": {}}
    ph = ",".join("?" * len(refs))
    grp = {r["id"]: r["group_id"] for r in db.rows(TU._con, f"SELECT id, group_id FROM students WHERE id IN ({','.join(map(str, sids))})")}
    prog: dict = {}
    for r in db.rows(TU._con, f"SELECT student_id, status, best FROM lrs_progress WHERE course_ref IN ({ph}) AND student_id IN ({','.join(map(str, sids))})", refs):
        prog.setdefault(r["student_id"], []).append(r)
    use = {r["s"]: r["n"] for r in db.rows(TU._con, "SELECT student_id s, COUNT(*) n FROM tu_log WHERE pilot_ref=? AND mode IN ('javob','maslahat','topilmadi') GROUP BY student_id", (ref,))}
    rows, score, usage = [], {}, {}
    for sid in sids:
        g = grp.get(sid)
        a = TJ.arm("tutor:" + ref, p["salt"] or "", g) if p["mode"] == "tajriba" else "hammasi"
        pr = prog.get(sid, [])
        rows.append({"group": g, "arm": a, "y": int(any(x["status"] == "otdi" for x in pr)), "lessons": sum(1 for x in pr if x["status"] in LA.DONE_ST)})
        bs = [x["best"] for x in pr if x["best"] is not None]
        if bs: score.setdefault(a, []).append(sum(bs) / len(bs))
        usage.setdefault(a, [0, 0]); usage[a][0] += 1; usage[a][1] += use.get(sid, 0)
    res = TJ.compare(rows)
    if p["mode"] != "tajriba": res["caveats"] = ["Rejim «hammaga» — taqqoslash guruhi yo'q, ta'sirni baholab bo'lmaydi."] + res["caveats"]
    return {"mode": p["mode"], "rows": len(rows), "result": res, "score": {k: round(sum(v) / len(v), 1) for k, v in score.items()},
            "usage": {k: {"students": v[0], "questions": v[1], "per_student": round(v[1] / v[0], 2) if v[0] else 0} for k, v in usage.items()}}


def export_with_tutor(ref: str) -> tuple[bytes, str]:
    """Ixtiyoriy: pilot muharrir kursining tasdiqlangan xAPI eksporti + tutor skripti (tutor/tutor.js). Skript faqat ISFT Core LRS launch
    parametrlari (endpoint + auth) bo'lsa ishlaydi va o'sha endpoint'ga (…/xapi/tutor/) launch tokeni bilan murojaat qiladi."""
    srcs = [s for s in TI.sources(TU._con, ref) if s["src"].startswith("ku:")]
    if not srcs: raise HTTPException(400, "Bu pilotda tasdiqlangan muharrir kursi eksporti yo'q")
    s = srcs[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(s["file"]) as zi, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zo:
        if "tincan.xml" not in zi.namelist(): raise HTTPException(400, "Tutor faqat xAPI eksport bilan ishlaydi (ISFT Core LRS launch tokeni kerak)")
        for n in zi.namelist():
            data = zi.read(n)
            if n == "index.html":
                tag = b'<link rel="stylesheet" href="tutor/tutor.css"><script src="tutor/tutor.js" defer></script>'
                i = data.rfind(b"</body>"); data = data[:i] + tag + data[i:] if i >= 0 else data + tag
            zo.writestr(zi.getinfo(n), data)
        for f in ("tutor.js", "tutor.css"):
            zo.writestr(f"tutor/{f}", (TU.PLAYER_DIR / f).read_bytes())
    return buf.getvalue(), f"{s['src'].replace(':', '-')}_xapi_tutor.zip"


# =============================================================================================
# HTTP
# =============================================================================================
@router.get(P + "/meta")
def api_meta(request: Request):
    c = C(request); guard(c, "ko'rish")
    sc = scope(c)
    ok, why = LLM.available()
    k = c.role.key
    pl = [pilot_row(r, p) for r, p in TU.pilots().items() if sc is None or r in sc]
    return {"role": k, "provider": LLM.provider(), "provider_label": LLM.PROVIDERS[LLM.provider()], "model": LLM.model_name(), "available": ok, "reason": why,
            "caps": {"edit": k == HEAD, "reindex": k in DEPT, "logs": k in LOGS, "reply": k in LOGS, "export": k in DEPT},
            "modes": TU.MODES, "pilots": pl, "candidates": candidates() if k == HEAD else [], "default_limit": TU.DEFAULT_LIMIT}


class PilotIn(BaseModel):
    course_ref: str = Field(..., max_length=20)
    enabled: bool = True
    mode: str = "all"
    daily_limit: int = TU.DEFAULT_LIMIT


@router.post(P + "/pilots")
def api_pilot(body: PilotIn, request: Request):
    c = C(request); guard(c, "pilot sozlamasi", (HEAD,), f"{body.course_ref} {body.enabled} {body.mode}")
    ref = body.course_ref
    if ref not in {x["ref"] for x in candidates()} and ref not in TU.pilots(): raise HTTPException(400, "Kurs pilot uchun mos emas (tasdiqlangan material yo'q)")
    if body.mode not in TU.MODES: raise HTTPException(400, "Rejim noma'lum")
    lim = max(1, min(200, int(body.daily_limit)))
    old = TU.pilots().get(ref)
    now = TU._iso()
    with TU._lock:
        if old:
            new_salt = old["salt"] if old["mode"] == body.mode else secrets.token_hex(4)
            TU._con.execute("UPDATE tu_pilots SET enabled=?, mode=?, salt=?, daily_limit=?, started_at=?, updated_at=?, updated_by=? WHERE course_ref=?",
                            (int(body.enabled), body.mode, new_salt, lim, old["started_at"] if new_salt == old["salt"] and old["started_at"] else now, now,
                             c.user["full_name"], ref))
        else:
            TU._con.execute("INSERT INTO tu_pilots(course_ref,enabled,mode,salt,daily_limit,started_at,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)",
                            (ref, int(body.enabled), body.mode, secrets.token_hex(4), lim, now, now, c.user["full_name"]))
        TU._con.commit()
    ix = TI.build(TU._con, ref) if body.enabled else None
    try:
        from . import lrs as L
        L.invalidate_launch()
    except Exception: pass
    return {"ok": True, "pilot": pilot_row(ref, TU.pilots()[ref]), "index": ix}


@router.post(P + "/pilots/reindex")
def api_reindex(request: Request, ref: str):
    c = C(request); guard(c, "indeksni qayta qurish", DEPT, ref); _pilot(c, ref)
    return {"ok": True, "index": TI.build(TU._con, ref)}


@router.get(P + "/stats")
def api_stats(request: Request, ref: str):
    c = C(request); guard(c, "statistika", VIEW, ref); _pilot(c, ref)
    out = {"stats": stats(ref), "compare": compare(ref)}
    if c.role.key in LOGS: out["top"] = top_questions(ref)
    return out


@router.get(P + "/log")
def api_log(request: Request, ref: str, flagged: bool = False, limit: int = 100, offset: int = 0):
    c = C(request); guard(c, "jurnal", LOGS, ref); _pilot(c, ref)
    rows = db.rows(TU._con, f"""SELECT id, ts, student_id, lesson_ref, item_id, arm, mode, question, answer, cites, provider, model, tok_in, tok_out, cost, dropped,
                                injection, flagged, flag_note FROM tu_log WHERE pilot_ref=? {"AND flagged=1" if flagged else ""} ORDER BY id DESC LIMIT ? OFFSET ?""",
                   (ref, max(1, min(500, limit)), max(0, offset)))
    for r in rows:
        r["student"] = TU.pseudo(r.pop("student_id"))
        r["cites"] = [x.get("label") for x in json.loads(r["cites"] or "[]")]
    return {"items": rows}


@router.get(P + "/questions")
def api_questions(request: Request, ref: str, status: str = "ochiq"):
    c = C(request); guard(c, "o'qituvchiga savollar", LOGS, ref); _pilot(c, ref)
    rows = db.rows(TU._con, f"""SELECT q.id, q.ts, q.student_id, q.question, q.status, q.reply, q.reply_by, q.reply_ts, l.answer, l.lesson_ref FROM tu_teacher_q q
                                LEFT JOIN tu_log l ON l.id=q.log_id WHERE q.pilot_ref=? {"AND q.status=?" if status in ("ochiq", "javob") else ""} ORDER BY q.id DESC LIMIT 200""",
                   (ref, status) if status in ("ochiq", "javob") else (ref,))
    for r in rows: r["student"] = TU.pseudo(r.pop("student_id"))
    return {"items": rows}


class ReplyIn(BaseModel):
    reply: str = Field(..., min_length=2, max_length=2000)


@router.post(P + "/questions/{qid}/reply")
def api_reply(qid: int, body: ReplyIn, request: Request):
    c = C(request)
    q = db.one(TU._con, "SELECT * FROM tu_teacher_q WHERE id=?", (qid,))
    guard(c, "savolga javob", LOGS, f"#{qid}")
    if not q: raise HTTPException(404, "Savol topilmadi")
    _pilot(c, q["pilot_ref"])
    with TU._lock:
        TU._con.execute("UPDATE tu_teacher_q SET status='javob', reply=?, reply_by=?, reply_ts=? WHERE id=?",
                        (TT.clean_out(body.reply)[:2000], c.user["full_name"], TU._iso(), qid)); TU._con.commit()
    return {"ok": True}


@router.get(P + "/pilots/export")
def api_export(request: Request, ref: str):
    c = C(request); guard(c, "tutor bilan eksport", DEPT, ref); _pilot(c, ref)
    data, name = export_with_tutor(ref)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
