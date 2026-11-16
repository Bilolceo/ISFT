"""«Dars kartochkasi» — har dars uchun BITTA joy: unikal kod, kafedra, o'qituvchi, fan, dars, taqdimot (oxirgi versiya + tarix), montajlangan video (holati),
ma'ruza matni, qo'shimcha fayllar, jurnal (docs/studio.md «Dars kartochkasi», docs/taqdimot.md).

Zanjir: Taqdimot (o'qituvchi) → Studiya (syomka, montaj) → Masofaviy bo'lim. Hammasining kaliti — darsning (course_id, lkey) bog'lanishi (st_bookings, pk_*),
YANGI parallel identifikator yo'q: unikal kod `paket.lesson_unique_code` (`2_ATT_dasturiyinjiniring_L2`) shundan hisoblanadi.

«Dars yaratish» — mavjud paket / Konstruktor oqimini shu ma'lumotlar bilan to'ldiradi: taqdimot (yuborilgan oxirgi versiya) va montajlangan video darsning paketida
bo'lmasa — qo'yiladi (paket.upload_slides / paket.studio_set_video ilgaklari, qayta yozilmagan), dars Konstruktorga o'tkaziladi (dars.convert_lesson) va ochiladi.
«Hammasini ZIP qilib yuklab olish» — <kod>/taqdimot_vN.pptx (+ .pdf), video, matn, qo'shimcha fayllar, jurnal (meta.json).

Ruxsat (resurs rbac.PAKET, har so'rov audit jurnalida): ko'rish va yuklab olish — masofaviy, masofaviy_xodim, montaj_operator, o'qituvchi (o'z fani), kafedra (o'z kafedrasi);
«Dars yaratish» — faqat masofaviy va masofaviy_xodim. Rahbariyat va boshqalar — 403.
"""
from __future__ import annotations
import datetime as dt, json, os, re, shutil, tempfile, threading, zipfile
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from . import clock, db, rbac
from .rbac import Ctx, AccessDenied

router = APIRouter()
_con = None
_ctx = None
RES = rbac.PAKET
P = "/api/dars/card"
HEAD, STAFF, OPER, TEACH, KAF = "masofaviy", "masofaviy_xodim", "montaj_operator", "oqituvchi", "kafedra"
DEPT = (HEAD, STAFF)
VIEW = DEPT + (OPER, TEACH, KAF)
KINDS_OK = ("maruza", "amaliy")
MAX_ZIP_NOTE = 4000


def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn


def C(request: Request) -> Ctx:
    return _ctx(request)


def _PK():
    from . import paket as PK
    return PK


def _STU():
    from . import studio as STU
    return STU


def _TQ():
    from . import taqdimot as TQ
    return TQ


def guard(c: Ctx, action: str, roles=VIEW, detail: str = ""):
    ok = c.role.key in roles and c.channel == "web"
    rbac.audit(_con, c, f"dars kartochkasi: {action}", RES, ok, detail)
    if not ok:
        raise AccessDenied(f"⛔ Dars kartochkasi: {action} — '{c.role.title}' lavozimi uchun ruxsat yo'q. So'rov audit jurnaliga yozildi.")


def _lesson(c: Ctx, cid: int, lkey: int) -> tuple[dict, dict]:
    """Ko'lam: bo'lim va operator — hamma; o'qituvchi — o'z fani; kafedra — o'z kafedrasi (paket._course) — begona kurs 403 + audit."""
    PK = _PK()
    co = PK._course(c, cid)
    les = PK.lesson_info(co, int(lkey))
    if les["kind"] not in KINDS_OK:
        raise HTTPException(400, "Dars kartochkasi faqat ma'ruza (L) va amaliy (A) darslari uchun")
    return co, les


def _resolve(c: Ctx, cid: int, lkey: int) -> tuple[dict, dict | None]:
    """Kartochka/ZIP uchun: dars kursda bo'lsa — (kurs, dars); dars keyin kursdan olib tashlangan bo'lsa-yu, tarixi (yuborilgan taqdimot / jurnal) saqlangan bo'lsa —
    (kurs, None) → «gone» holati (400 o'rniga tushunarli javob). Ko'lam tekshiruvi (begona kurs 403) odatdagidek."""
    PK = _PK()
    co = PK._course(c, cid)
    try:
        les = PK.lesson_info(co, int(lkey))
    except HTTPException as e:
        if e.status_code == 400 and (db.one(_con, "SELECT 1 x FROM pres_sends WHERE course_id=? AND lkey=?", (co["id"], int(lkey))) or
                                     db.one(_con, "SELECT 1 x FROM st_log WHERE course_id=? AND lkey=?", (co["id"], int(lkey))) or
                                     db.one(_con, "SELECT 1 x FROM pk_log WHERE course_id=? AND topic_no=?", (co["id"], int(lkey)))):
            return co, None
        raise
    if les["kind"] not in KINDS_OK:
        raise HTTPException(400, "Dars kartochkasi faqat ma'ruza (L) va amaliy (A) darslari uchun")
    return co, les


def _gone_ref(co: dict, lkey: int) -> dict:
    PK = _PK()
    code = PK.course_codes().get(co["id"]) or f"{co['id']}_XXX_fan"
    return {"course_id": co["id"], "lkey": int(lkey), "code": PK.lesson_code(int(lkey)), "full_code": PK.lesson_full_code(code, int(lkey)), "course_code": code,
            "title": "(dars kursdan olib tashlangan)", "untitled": True, "kind": PK.split_key(int(lkey))[0], "subject": co.get("subject") or "", "direction": co.get("direction") or "",
            "course": co.get("course"), "dept": co.get("dept") or "", "teacher": PK._short(co.get("teacher") or ""), "gone": True}


def _video_asset(cid: int, lkey: int) -> dict | None:
    return _PK()._latest_asset(cid, lkey, "video", _PK().VIDEO_KINDS)


def _last_job(cid: int, lkey: int) -> dict | None:
    return db.one(_con, "SELECT * FROM st_jobs WHERE course_id=? AND lkey=? AND status!='bekor' ORDER BY id DESC LIMIT 1", (cid, lkey))


def _video_state(co: dict, les: dict, ops: bool) -> dict:
    """Montajlangan video holati: Yo'q → Syomka belgilangan → Xom video → Montajda → Ko'rib chiqishda → Tasdiqlangan → Masofaviy bo'limga yuborilgan."""
    PK, cid, lkey = _PK(), co["id"], les["key"]
    job = _last_job(cid, lkey)
    asset = _video_asset(cid, lkey)
    tr = PK._topic_row(cid, lkey)
    yt = (tr.get("video_url") or "") if tr else ""
    sent = db.one(_con, "SELECT * FROM st_dept WHERE job_id=?", (job["id"],)) if job and job["status"] == "tasdiqlandi" else None
    bk = db.one(_con, "SELECT 1 x FROM st_bookings WHERE course_id=? AND lkey=? AND status='band'", (cid, lkey))
    raw = db.one(_con, "SELECT 1 x FROM st_raw WHERE course_id=? AND lkey=? AND deleted=0", (cid, lkey))
    if sent: key, label = "dept", "Masofaviy bo'limga yuborilgan"
    elif job and job["status"] == "tasdiqlandi": key, label = "tasdiqlandi", "Montaj tasdiqlangan (bo'limga yuborilmagan)"
    elif job and job["status"] == "tayyor": key, label = "korib", "Ko'rib chiqishda (operator)"
    elif job and job["status"] in ("navbatda", "ishlanmoqda", "operator"): key, label = "montaj", {"navbatda": "Montaj navbatida", "ishlanmoqda": "Montaj qilinmoqda", "operator": "Montaj xatosi — operator kerak"}[job["status"]]
    elif raw: key, label = "xom", "Xom video yuklangan (montajga yuborilmagan)"
    elif bk: key, label = "syomka", "Syomka belgilangan"
    elif asset or yt: key, label = "bor", "Video bor (studiyadan tashqari)"
    else: key, label = "yoq", "Video yo'q"
    rep = {}
    if job:
        try: rep = json.loads(job.get("report") or "{}") or {}
        except ValueError: rep = {}
    fl = _STU().dept_flags(cid).get((cid, lkey)) or {"dept_sent": False, "video_wait": False}
    out = {"dept_sent": fl["dept_sent"], "video_wait": fl["video_wait"],
           "state": key, "label": label, "job_id": job["id"] if job else None, "job_status": job["status"] if job else None, "has_file": bool(asset),
           "size": int(asset["size"] or 0) if asset else 0, "name": asset["name"] if asset else None, "youtube": yt or None,
           "duration": rep.get("duration_out"), "dept": _STU()._dept_row(sent) if sent else None}
    if ops and job and (_STU()._job_dir(job["id"]) / "video.mp4").is_file():
        out["media_url"] = f"/api/studio/jobs/{job['id']}/media/video"
    if asset and ops:
        out["file_url"] = f"{P}/{cid}/{lkey}/video"
    return out


def _text_info(cid: int, lkey: int, les: dict) -> dict:
    PK = _PK()
    ts = PK._text_source(cid, lkey, les)
    if not ts or not (ts.get("text") or "").strip():
        return {"has": False}
    plain = PK._plain(ts["text"])
    return {"has": True, "src": ts["src"], "name": ts.get("name"), "kind": ts.get("kind"), "chars": len(plain), "by": ts.get("by"), "ts": ts.get("ts"),
            "preview": re.sub(r"\s+", " ", plain).strip()[:500], "file": bool(ts.get("asset")), "url": f"{P}/{cid}/{lkey}/text"}


def _extra_files(cid: int, lkey: int) -> list[dict]:
    PK = _PK()
    return [{"id": a["id"], "name": a["name"], "kind": a["kind"], "size": a["size"], "ts": a["ts"]} for a in
            db.rows(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='fayl' AND deleted=0 ORDER BY id", (cid, lkey)) if PK._apath(a).is_file()]


def _log(cid: int, lkey: int, limit: int = 120) -> list[dict]:
    st = db.rows(_con, "SELECT ts, action, note, user_name FROM st_log WHERE course_id=? AND lkey=? ORDER BY id DESC LIMIT ?", (cid, lkey, limit))
    pk = db.rows(_con, "SELECT ts, action, note, user_name FROM pk_log WHERE course_id=? AND topic_no=? ORDER BY id DESC LIMIT ?", (cid, lkey, limit))
    return sorted([{**x, "src": "studiya", "user_name": _PK()._short(x["user_name"])} for x in st] + [{**x, "src": "paket", "user_name": _PK()._short(x["user_name"])} for x in pk],
                  key=lambda x: x["ts"] or "", reverse=True)[:limit]


def _gone_card(c: Ctx, co: dict, lkey: int) -> dict:
    """Dars kursdan olib tashlangan: tarix (yuborilgan taqdimotlar, jurnal) ko'rinadi, tahrirlash amallari yo'q."""
    TQ = _TQ()
    sends = TQ.sends_public(co["id"], int(lkey))
    for s_ in sends:
        s_["url_pptx"] = f"{P}/{co['id']}/{int(lkey)}/taqdimot/{s_['version']}/pptx"
        s_["url_pdf"] = f"{P}/{co['id']}/{int(lkey)}/taqdimot/{s_['version']}/pdf" if s_["has_pdf"] else None
    return {"gone": True, "message": "Bu dars kursdan olib tashlangan — yuborilgan taqdimotlar va jurnal tarixi saqlangan.", "ref": _gone_ref(co, lkey), "state": None,
            "taqdimot": {"latest": sends[0] if sends else None, "history": sends, "in_paket": False, "paket_name": None},
            "video": {"state": "yoq", "label": "Dars olib tashlangan", "job_id": None, "job_status": None, "has_file": False, "size": 0, "name": None, "youtube": None,
                      "duration": None, "dept": None, "dept_sent": False, "video_wait": False},
            "text": {"has": False}, "files": [], "package": None, "linked": None, "log": _log(co["id"], int(lkey)),
            "caps": {"create": False, "zip": True, "upload": False, "video_view": False}}


def card(c: Ctx, cid: int, lkey: int) -> dict:
    PK, TQ, STU = _PK(), _TQ(), _STU()
    co, les = _resolve(c, cid, lkey)
    if les is None:
        return _gone_card(c, co, lkey)
    ops = c.role.key in DEPT + (OPER,)
    ref = TQ.lesson_ref(co, les)
    sends = TQ.sends_public(co["id"], les["key"])
    for s in sends:
        s["url_pptx"] = f"{P}/{co['id']}/{les['key']}/taqdimot/{s['version']}/pptx"
        s["url_pdf"] = f"{P}/{co['id']}/{les['key']}/taqdimot/{s['version']}/pdf" if s["has_pdf"] else None
    st = STU.states([co], {co["id"]: {les["key"]}})
    pkg = db.one(_con, "SELECT version, status, built_at, approved_at FROM pk_packages WHERE course_id=? AND topic_no=? ORDER BY version DESC LIMIT 1", (co["id"], les["key"]))
    link = db.one(_con, "SELECT ku_course_id, authority FROM ds_links WHERE dl_course_id=? AND lkey=?", (co["id"], les["key"])) if PK._has_table("ds_links") else None
    pres_asset = PK._latest_asset(co["id"], les["key"], "taqdimot", ("pptx", "pdf"))
    if c.role.key in DEPT + (OPER,):
        STU.ack_lesson(c, co["id"], les["key"])                  # tafsilot ochildi — «yangi taqdimot / video» xabari «ko'rildi»
    return {"ref": ref, "state": st[0] if st else None,
            "taqdimot": {"latest": sends[0] if sends else None, "history": sends, "in_paket": bool(pres_asset), "paket_name": pres_asset["name"] if pres_asset else None},
            "video": _video_state(co, les, ops), "text": _text_info(co["id"], les["key"], les), "files": _extra_files(co["id"], les["key"]),
            "package": dict(pkg) if pkg else None, "linked": dict(link) if link else None, "log": _log(co["id"], les["key"]),
            "caps": {"create": c.role.key in DEPT, "zip": True, "upload": c.role.key in DEPT, "video_view": ops}}


# ---- «Dars yaratish» ---------------------------------------------------------------------------
def create(c: Ctx, cid: int, lkey: int) -> dict:
    """Kartochkadagi ma'lumotlar bilan mavjud paket / Konstruktor oqimini to'ldiradi: taqdimot va montajlangan video darsning paketida bo'lmasa qo'yiladi
    (ilgaklar — paket.upload_slides, paket.studio_set_video), dars Konstruktorga o'tkaziladi (yoki mavjud nusxa yangilanadi). Konstruktorni ochish — UI'da."""
    from . import dars as DRS
    co, les = _lesson(c, cid, lkey)
    with DRS.link_lock(co["id"], les["key"]):              # dars bo'yicha qulf: parallel «Dars yaratish» — bitta kurs, qolganlari shu kursni qaytaradi (idempotent)
        return _create_locked(c, co, les)


def _create_locked(c: Ctx, co: dict, les: dict) -> dict:
    PK, TQ, STU = _PK(), _TQ(), _STU()
    from . import dars as DRS
    cid, lkey = co["id"], les["key"]
    ref = TQ.lesson_ref(co, les)
    filled, missing, notes = {}, [], []
    sends = db.rows(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? ORDER BY version DESC LIMIT 1", (cid, lkey))
    if PK._latest_asset(cid, lkey, "taqdimot", ("pptx", "pdf")):
        filled["taqdimot"] = False                                # paketda bor — tegilmaydi (xodim yangiroq faylni qo'lda yuklagan bo'lishi mumkin)
    elif sends:
        r, f = TQ.send_file(cid, lkey, sends[0]["version"], "pptx")
        if f:
            try:
                PK.upload_slides(c, cid, lkey, f.read_bytes(), f"{ref['full_code']}_taqdimot_v{r['version']}.pptx")
                filled["taqdimot"] = True; notes.append(f"taqdimot v{r['version']} paketga qo'yildi")
            except HTTPException as e:
                missing.append("taqdimot"); notes.append(f"taqdimot qo'yilmadi: {e.detail}")
        else:
            missing.append("taqdimot")
    else:
        missing.append("taqdimot")
    if _video_asset(cid, lkey) or (PK._topic_row(cid, lkey) or {}).get("video_url"):
        filled["video"] = False
    else:
        job = db.one(_con, "SELECT * FROM st_jobs WHERE course_id=? AND lkey=? AND status='tasdiqlandi' ORDER BY id DESC LIMIT 1", (cid, lkey))
        d = STU._job_dir(job["id"]) if job else None
        if d and (d / "video.mp4").is_file():
            try:
                cap = (d / "captions.vtt").read_bytes() if (d / "captions.vtt").is_file() else None
                thumb = (d / "thumb.jpg").read_bytes() if (d / "thumb.jpg").is_file() else None
                PK.studio_set_video(c, cid, lkey, d / "video.mp4", cap, thumb, name=f"{les['code']} studiya montaji #{job['id']}")
                filled["video"] = True; notes.append(f"montajlangan video (#{job['id']}) paketga qo'yildi")
            except HTTPException as e:
                missing.append("video"); notes.append(f"video qo'yilmadi: {e.detail}")
        else:
            missing.append("video")
    if not _text_info(cid, lkey, les)["has"]:
        missing.append("matn")
    link = DRS._link(cid, lkey)
    if link:
        rs = None
        try:
            rs = DRS.resync(c, cid, lkey, preview=False)
        except HTTPException as e:
            notes.append(f"muharrirni yangilab bo'lmadi: {e.detail}")
        conv = {"ok": True, "created": False, "ku_course_id": link["ku_course_id"], "authority": link["authority"], "resync": rs}
    else:
        conv = DRS.convert_lesson(c, cid, lkey)
    with PK._lock:
        PK._log(c, cid, lkey, "dars kartochkasi: Dars yaratish", f"{ref['full_code']} · " + ("; ".join(notes) or "ma'lumotlar paketda bor")[:250]); PK._con.commit()
    rbac.audit(_con, c, "dars kartochkasi: dars yaratildi", RES, True, f"{ref['full_code']} · to'ldirildi: {','.join(k for k, v in filled.items() if v) or '—'} · yetishmaydi: {','.join(missing) or '—'}")
    return {"ok": True, "code": ref["full_code"], "filled": filled, "missing": missing, "notes": notes, "ku_course_id": conv.get("ku_course_id"),
            "created": bool(conv.get("created")), "open": {"cid": cid, "lkey": lkey}}


# ---- fayllar va ZIP ----------------------------------------------------------------------------
def text_file(c: Ctx, cid: int, lkey: int):
    PK = _PK()
    co, les = _lesson(c, cid, lkey)
    ts = PK._text_source(co["id"], les["key"], les)
    if not ts or not (ts.get("text") or "").strip():
        raise HTTPException(404, "Ma'ruza matni yo'q")
    a = ts.get("asset")
    code = _TQ().lesson_ref(co, les)["full_code"]
    if a and PK._apath(a).is_file():
        return FileResponse(str(PK._apath(a)), filename=f"{code}_matn.{a['kind']}", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
    tmp = Path(tempfile.mkdtemp(prefix="isft_matn_")) / "matn.txt"
    tmp.write_text(PK._plain(ts["text"]), encoding="utf-8")
    return FileResponse(str(tmp), filename=f"{code}_matn.txt", media_type="text/plain; charset=utf-8", background=BackgroundTask(shutil.rmtree, str(tmp.parent), True))


def video_file(c: Ctx, cid: int, lkey: int, rng: str | None):
    PK = _PK()
    co, les = _lesson(c, cid, lkey)
    a = _video_asset(co["id"], les["key"])
    if not a:
        raise HTTPException(404, "Darsda video fayl yo'q")
    ct = "video/webm" if a["kind"] == "webm" else "video/mp4"
    return PK.range_response(PK._apath(a), ct, rng, {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}, chunk=512 * 1024)


def safe_name(name: str, fid) -> str:
    """Qo'shimcha fayl nomi: faqat xavfsiz belgilar, boshidagi/oxiridagi nuqta va bo'shliq olib tashlanadi, bo'sh yoki «.» / «..» — «fayl_<id>»; 120 belgidan
    uzun bo'lsa kengaytma saqlanib kesiladi."""
    n = re.sub(r"[^\w.\- ]+", "_", str(name or ""), flags=re.U).strip(". ")
    if n in ("", ".", ".."):
        return f"fayl_{fid}"
    if len(n) > 120:
        root, ext = os.path.splitext(n)
        ext = ext[:12]
        n = root[:max(1, 120 - len(ext))] + ext
        n = n.strip(". ") or f"fayl_{fid}"
    return n


def zip_file(c: Ctx, cid: int, lkey: int):
    """Kartochka ichidagi hamma narsa — bitta .zip (ZIP_STORED: video siqilmaydi): <kod>/<kod>_taqdimot_vN.pptx (+ .pdf), <kod>_video.mp4, <kod>_matn.*, qoshimcha/,
    eski_versiyalar/<kod>_taqdimot_vK.pptx, meta.json (fayl nomlari bilan mos). Siyosat: VIDEO faqat video havolasini ko'ra oladigan rollarga (bo'lim, operator) —
    o'qituvchi va kafedra ZIP'ida video yo'q (meta.json: video «ruxsat yo'q»). Dars kursdan olib tashlangan bo'lsa — tarix (taqdimotlar, jurnal) ZIP'i."""
    PK, TQ = _PK(), _TQ()
    co, les = _resolve(c, cid, lkey)
    cid = co["id"]
    ref = TQ.lesson_ref(co, les) if les else _gone_ref(co, lkey)
    lkey = les["key"] if les else int(lkey)
    ops = c.role.key in DEPT + (OPER,)
    code = ref["full_code"]
    tmp_root = Path(db.DATA_DIR) / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp(prefix="isft_zip_", dir=str(tmp_root)))
    z = d / f"{code}.zip"
    meta = {"kod": code, "dars": {"kod": ref["code"], "nomi": ref["title"]}, "fan": ref["subject"], "kafedra": ref["dept"], "oqituvchi": ref["teacher"],
            "yonalish": ref["direction"], "kurs": ref["course"], "yaratildi": clock.now_iso(), "fayllar": [], "taqdimot_versiyalari": [], "video": "yo'q"}
    if les is None:
        meta["holat"] = "dars kursdan olib tashlangan — faqat tarix"
    names = set()

    def put(zf, src: Path, arc: str):
        arc = f"{code}/{arc}"
        while arc in names:
            base, ext = os.path.splitext(arc); arc = f"{base}_1{ext}"
        names.add(arc); zf.write(src, arc); meta["fayllar"].append({"nom": arc[len(code) + 1:], "hajm": src.stat().st_size})
        return arc[len(code) + 1:]

    try:
        with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            rows = db.rows(_con, "SELECT * FROM pres_sends WHERE course_id=? AND lkey=? ORDER BY version DESC", (cid, lkey))
            for i, r in enumerate(rows):
                meta["taqdimot_versiyalari"].append({"versiya": r["version"], "sana": r["sent_at"], "yuborgan": (r["sent_by_name"] or "").split(":")[-1].strip(), "slaydlar": r["slides"],
                                                     "sarlavha": r["title"], "fayl": f"{code}_taqdimot_v{r['version']}.pptx" if i == 0 else f"eski_versiyalar/{code}_taqdimot_v{r['version']}.pptx"})
                for kind in ("pptx", "pdf"):
                    _, f = TQ.send_file(cid, lkey, r["version"], kind) if (r["pptx_path"] if kind == "pptx" else r["pdf_path"]) else (r, None)
                    if f: put(zf, f, (f"{code}_taqdimot_v{r['version']}.{kind}" if i == 0 else f"eski_versiyalar/{code}_taqdimot_v{r['version']}.{kind}"))
            if les is not None:
                a = _video_asset(cid, lkey)
                if a and ops:
                    meta["video"] = put(zf, PK._apath(a), f"{code}_video.{a['kind']}")
                elif a:
                    meta["video"] = "ruxsat yo'q"
                ts = PK._text_source(cid, lkey, les)
                if ts and (ts.get("text") or "").strip():
                    ta = ts.get("asset")
                    if ta and PK._apath(ta).is_file():
                        put(zf, PK._apath(ta), f"{code}_matn.{ta['kind']}")
                    else:
                        tp = d / "matn.txt"; tp.write_text(PK._plain(ts["text"]), encoding="utf-8"); put(zf, tp, f"{code}_matn.txt")
                for fa in db.rows(_con, "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='fayl' AND deleted=0 ORDER BY id", (cid, lkey)):
                    if PK._apath(fa).is_file():
                        put(zf, PK._apath(fa), "qoshimcha/" + safe_name(fa["name"], fa["id"]))
                tr = PK._topic_row(cid, lkey) or {}
                if tr.get("video_url"):
                    if ops: meta["video_havola"] = tr["video_url"]
                    elif meta["video"] == "yo'q": meta["video"] = "ruxsat yo'q"
            meta["jurnal"] = [{"vaqt": x["ts"], "amal": x["action"], "izoh": x["note"], "kim": x["user_name"], "manba": x["src"]} for x in _log(cid, lkey, 200)]
            zf.writestr(f"{code}/meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return FileResponse(str(z), filename=f"{code}.zip", media_type="application/zip", background=BackgroundTask(shutil.rmtree, str(d), True),
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


# =============================================================================================
# HTTP
# =============================================================================================
@router.get(P + "/{cid}/{lkey}")
def api_card(cid: int, lkey: int, request: Request):
    c = C(request); guard(c, "ko'rish", detail=f"kurs #{cid} · {lkey}")
    return card(c, cid, lkey)


@router.post(P + "/{cid}/{lkey}/create")
def api_create(cid: int, lkey: int, request: Request):
    """Sinxron `def` — oqimlar havzasida bajariladi (guard/DB event loop'ni to'smaydi)."""
    c = C(request); guard(c, "dars yaratish", DEPT, f"kurs #{cid} · {lkey}")
    return create(c, cid, lkey)


@router.get(P + "/{cid}/{lkey}/taqdimot/{ver}/{kind}")
def api_card_pres(cid: int, lkey: int, ver: int, kind: str, request: Request):
    c = C(request); guard(c, "taqdimotni yuklab olish", detail=f"kurs #{cid} · {lkey} · v{ver} · {kind}")
    co, les = _resolve(c, cid, lkey)
    if les is not None:
        _STU().ack_lesson(c, co["id"], les["key"])
    return _TQ().serve_send(co["id"], les["key"] if les else int(lkey), ver, kind)


@router.get(P + "/{cid}/{lkey}/video")
def api_card_video(cid: int, lkey: int, request: Request):
    c = C(request); rng = request.headers.get("range")
    if not rng or rng.replace(" ", "").startswith("bytes=0-"):
        guard(c, "videoni yuklab olish", DEPT + (OPER,), f"kurs #{cid} · {lkey}")
    elif c.role.key not in DEPT + (OPER,):
        guard(c, "videoni yuklab olish", DEPT + (OPER,), f"kurs #{cid} · {lkey}")
    return video_file(c, cid, lkey, rng)


@router.get(P + "/{cid}/{lkey}/text")
def api_card_text(cid: int, lkey: int, request: Request):
    c = C(request); guard(c, "matnni yuklab olish", detail=f"kurs #{cid} · {lkey}")
    return text_file(c, cid, lkey)


@router.get(P + "/{cid}/{lkey}/zip")
def api_card_zip(cid: int, lkey: int, request: Request):
    c = C(request); guard(c, "ZIP yuklab olish", detail=f"kurs #{cid} · {lkey}")
    return zip_file(c, cid, lkey)
