"""Dars paketi: AVTOMATIK SUBTITR (Whisper) — yuklangan video faylga o'zbekcha (yoki boshqa tilda) .vtt yaratish.

Yangi texnologiya yo'q: kurs muharriridagi (app/kurs.py, «Subtitrlar») navbat va studiya montaj ishchisi (tools/montaj, ISFT_CORE_WORKER_TOKEN,
faster-whisper) QAYTA ISHLATILADI. Ishchi navbat bo'sh bo'lganda /api/montaj/kurs-captions/claim ni so'raydi — shu so'rov avval kurs vazifalarini,
keyin (shu modul orqali) paket vazifalarini beradi; media / progress / fail / result yo'llari ham o'sha (ishchi kodi O'ZGARMAGAN).
Paket vazifalari alohida jadvalda (pk_caption_jobs); ishchiga ularning raqami JOB_BASE (10^9) ga siljitilgan holda beriladi — kurs raqamlari bilan
to'qnashmaydi, yo'l-yo'lakay qaysi navbatga tegishli ekani raqamdan aniq.

Natija: server WebVTT ni tekshiradi (paket.to_vtt), darsning «subs» fayli (pk_assets, purpose='subs', meta: lang, label «O'zbekcha (avto)», from/auto=whisper)
sifatida saqlaydi → keyingi yig'ishda paketga video.<til>.vtt va content.json video.captions[] sifatida kiradi, pleyer <track> chizadi.
Qo'lda yuklangan subtitr hech qachon avtomatik bilan almashtirilmaydi. Ishchi (token) sozlanmagan bo'lsa — «unavailable» (hech narsa soxtalashtirilmaydi).

API (docs/paket.md «Avtomatik subtitr»):
  POST /api/paket/courses/{cid}/topics/{key}/captions/auto  {"lang": "uz"} → {ok, state, message, job_id?, existing?}
  GET  .../captions/auto?lang=uz → joriy holat (hech narsa yaratmaydi)
  state: queued | running | done | failed | exists | unavailable | none
"""
from __future__ import annotations
import hmac, json, secrets
from datetime import timedelta
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from . import clock, db, rbac
from . import paket as PK

JOB_BASE = 1_000_000_000          # ishchiga beriladigan raqam = JOB_BASE + pk_caption_jobs.id (kurs vazifalaridan ajratish uchun)
LEASE = 2 * 3600
ATTEMPTS = 3
STATE = {"navbatda": "queued", "ishlanmoqda": "running", "tayyor": "done", "xato": "failed", "bekor": "cancelled"}
ACTIVE = ("navbatda", "ishlanmoqda")
NO_WORKER = ("Avtomatik subtitr ishchisi (Whisper) bu serverda sozlanmagan — tayyor .srt / .vtt faylni yuklang "
             "yoki administratorga murojaat qiling (ISFT_CORE_WORKER_TOKEN va tools/montaj).")
NO_YT = "YouTube videosiga avtomatik subtitr qo'yib bo'lmaydi — .srt/.vtt yuklang"
NO_VIDEO = "Avtomatik subtitr uchun avval video fayl (.mp4 / .webm) yuklang"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pk_caption_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INT, topic_no INT, asset_id INT, lang TEXT, status TEXT,
  attempts INT DEFAULT 0, lease TEXT, lease_until TEXT, stage TEXT, pct REAL, error TEXT, subs_asset INT, cues INT, auto INT DEFAULT 0,
  user_id INT, user_name TEXT, created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS ix_pk_cj ON pk_caption_jobs(status, id);
CREATE INDEX IF NOT EXISTS ix_pk_cj_t ON pk_caption_jobs(course_id, topic_no, id);
"""

def _db(): return PK._con
def _ensure() -> None:
    db.run_script(_db(), SCHEMA)

def worker_on() -> bool:
    from . import studio as STU
    return bool(STU.worker_token())

def _latest_video(cid: int, no: int) -> dict | None:
    return PK._latest_asset(cid, no, "video", PK.VIDEO_KINDS)

def _subs(cid: int, no: int) -> dict:
    """Darsning mavjud subtitrlari {til: (qator, meta)} (diskda borlari)."""
    out = {}
    for a in db.rows(_db(), "SELECT * FROM pk_assets WHERE course_id=? AND topic_no=? AND purpose='subs' AND deleted=0 ORDER BY id", (cid, no)):
        if PK._apath(a).is_file(): m = json.loads(a["meta"] or "{}"); out[m.get("lang") or "uz"] = (a, m)
    return out

def _view(j: dict | None) -> dict | None:
    if not j: return None
    st = STATE.get(j["status"], j["status"])
    msg = {"queued": "Subtitr navbatga qo'yildi — tayyor bo'lgach paketga avtomatik qo'shiladi (bir necha daqiqa).",
           "running": f"Subtitr yaratilmoqda… {int(j['pct'] or 0)}%" + (f" ({j['stage']})" if j["stage"] else ""),
           "done": (f"Subtitr tayyor ({j['cues']} yozuv) — keyingi yig'ishda paketga kiradi." if j["subs_asset"] else (j["error"] or "Tayyor")),
           "failed": f"Subtitr yaratilmadi: {j['error'] or 'noma`lum xato'}", "cancelled": j["error"] or "Vazifa bekor qilindi"}.get(st, st)
    return {"state": st, "message": msg, "job_id": j["id"], "lang": j["lang"], "pct": int(j["pct"] or 0), "stage": j["stage"] or "", "cues": j["cues"],
            "error": j["error"] or "", "auto": bool(j["auto"]), "updated_at": j["updated_at"]}

def job_status(cid: int, no: int, lang: str | None = None) -> dict | None:
    """Darsning (hozirgi video fayli uchun) oxirgi vazifasi — ready.video.captions_job. Vazifa yo'q bo'lsa None."""
    try:
        _ensure()
        va = _latest_video(cid, no)
        if not va: return None
        q, a = "SELECT * FROM pk_caption_jobs WHERE course_id=? AND topic_no=? AND asset_id=?", [cid, no, va["id"]]
        if lang: q += " AND lang=?"; a.append(lang)
        return _view(db.one(_db(), q + " AND status<>'bekor' ORDER BY id DESC LIMIT 1", a))
    except Exception as e:      # holat ko'rsatkichi darsni ochishni to'xtatmasin
        print("paket_captions.job_status:", repr(e)); return None

def _norm_lang(lang) -> str:
    lang = str(lang or "uz").strip().lower()
    if lang not in PK.SUB_LANGS: raise HTTPException(400, "Subtitr tili noma'lum (uz, ru, en, kk, tj)")
    return lang

# --------------------------------------------------------------------------------------------- foydalanuvchi tomoni
def request_auto(c, cid: int, no: int, lang: str = "uz", auto: bool = False) -> dict:
    """«Avtomatik subtitr (AI)»: video fayl bo'lsa — navbatga. Mavjud holatlar xato emas, aniq `state` bilan qaytariladi."""
    co = PK._course(c, cid, write=True); les = PK._check_topic(co, no)
    lang = _norm_lang(lang); _ensure()
    va = _latest_video(cid, no)
    if not va:
        v = PK._video_source(cid, no, les)
        yt = bool(v and v.get("ok") and v.get("provider") == "youtube")
        return {"ok": False, "state": "unavailable", "message": NO_YT if yt else NO_VIDEO, "reason": "youtube" if yt else "no_video"}
    if lang in _subs(cid, no):
        return {"ok": True, "state": "exists", "message": f"Bu tilda ({PK.SUB_LANGS[lang]}) subtitr allaqachon bor."}
    with PK._lock:
        j = db.one(_db(), "SELECT * FROM pk_caption_jobs WHERE course_id=? AND topic_no=? AND asset_id=? AND lang=? AND status IN ('navbatda','ishlanmoqda') ORDER BY id DESC LIMIT 1",
                   (cid, no, va["id"], lang))
        if j: return {"ok": True, "existing": True, **_view(j)}
        if not worker_on():
            return {"ok": False, "state": "unavailable", "message": NO_WORKER, "reason": "no_worker"}
        now = PK._now()
        jid = _db().execute("INSERT INTO pk_caption_jobs(course_id,topic_no,asset_id,lang,status,auto,user_id,user_name,created_at,updated_at) VALUES(?,?,?,?,'navbatda',?,?,?,?,?)",
                            (cid, no, va["id"], lang, 1 if auto else 0, c.user["id"], c.user["full_name"], now, now)).lastrowid
        PK._log(c, cid, no, "avto-subtitr navbatga", f"{va['name'][:80]} · {lang}" + (" · yuklashdan keyin" if auto else "")); _db().commit()
    rbac.audit(_db(), c, "paket: avto-subtitr navbatga", PK.RES, True, f"kurs #{cid} · {les['code']} · {lang} · vazifa #{jid}")
    return {"ok": True, "existing": False, **_view(db.one(_db(), "SELECT * FROM pk_caption_jobs WHERE id=?", (jid,)))}

def status(c, cid: int, no: int, lang: str = "uz") -> dict:
    co = PK._course(c, cid); les = PK._check_topic(co, no)
    lang = _norm_lang(lang); _ensure()
    va = _latest_video(cid, no)
    can = c.role.key in PK.AUTHORS and bool(va)
    base = {"worker": worker_on(), "can_request": can, "has_file": bool(va), "lang": lang}
    j = job_status(cid, no, lang)
    if lang in _subs(cid, no) and not (j and j["state"] in ("queued", "running")):
        return {"ok": True, "state": "exists", "message": f"Bu tilda ({PK.SUB_LANGS[lang]}) subtitr bor.", **base, "job": j}
    if j: return {"ok": True, **j, **base, "job": j}
    if not va:
        v = PK._video_source(cid, no, les)
        yt = bool(v and v.get("ok") and v.get("provider") == "youtube")
        return {"ok": True, "state": "unavailable", "message": NO_YT if yt else NO_VIDEO, **base, "job": None}
    return {"ok": True, "state": "none", "message": "" if base["worker"] else NO_WORKER, **base, "job": None}

def cancel(c, cid: int, no: int, lang: str = "uz") -> dict:
    PK._check_topic(PK._course(c, cid, write=True), no); _ensure()
    lang = _norm_lang(lang); n = 0
    with PK._lock:
        for j in db.rows(_db(), "SELECT * FROM pk_caption_jobs WHERE course_id=? AND topic_no=? AND lang=? AND status IN ('navbatda','ishlanmoqda','xato')", (cid, no, lang)):
            _db().execute("UPDATE pk_caption_jobs SET status='bekor', lease=NULL, lease_until=NULL, error='Bekor qilindi', updated_at=? WHERE id=?", (PK._now(), j["id"])); n += 1
        if n: PK._log(c, cid, no, "avto-subtitr bekor qilindi", lang); _db().commit()
    return {"ok": True, "cancelled": n}

def on_video_uploaded(c, cid: int, no: int) -> dict | None:
    """Mavzu sozlamasi auto_captions yoqilgan bo'lsa: video fayl yuklangach darhol navbatga. Xato yuklashni to'xtatmaydi.
    Avvalgi video uchun Whisper yaratgan subtitrlar eskirgan — olib tashlanadi (qo'lda yuklanganlari qoladi)."""
    try:
        if not PK.topic_settings(cid, no)[0].get("auto_captions"): return None
        PK._replace_assets(cid, no, "subs", 0, lambda m: m.get("auto") == "whisper")
        return request_auto(c, cid, no, "uz", auto=True)
    except HTTPException as e:
        return {"ok": False, "state": "unavailable", "message": str(e.detail)}
    except Exception as e:
        print("paket_captions.on_video_uploaded:", repr(e)); return None

# --------------------------------------------------------------------------------------------- ishchi tomoni
def _wauth(request: Request, action: str):
    from . import studio as STU
    return STU.worker_auth(request, f"paket subtitr: {action}")

def owns(jid: int) -> bool:
    return int(jid) >= JOB_BASE

def _requeue(now_iso: str) -> None:
    for j in db.rows(_db(), "SELECT * FROM pk_caption_jobs WHERE status='ishlanmoqda' AND lease_until<?", (now_iso,)):
        st, err = ("navbatda", None) if (j["attempts"] or 0) < ATTEMPTS else ("xato", "Ishchi javob bermadi (muddat o'tdi)")
        _db().execute("UPDATE pk_caption_jobs SET status=?, error=COALESCE(?, error), lease=NULL, lease_until=NULL, updated_at=? WHERE id=?", (st, err, now_iso, j["id"]))
    _db().commit()

def claim(request: Request) -> dict | None:
    from . import kurs as K
    wc = _wauth(request, "claim"); _ensure()
    now = clock.now().replace(microsecond=0)
    with PK._lock:
        _requeue(now.isoformat(timespec="seconds"))
        while True:
            j = db.one(_db(), "SELECT * FROM pk_caption_jobs WHERE status='navbatda' ORDER BY id LIMIT 1")
            if not j: return None
            va = _latest_video(j["course_id"], j["topic_no"])
            if not va or va["id"] != j["asset_id"]:
                _db().execute("UPDATE pk_caption_jobs SET status='bekor', error='Video almashtirildi yoki o''chirildi', updated_at=? WHERE id=?", (PK._now(), j["id"])); _db().commit()
                continue
            lease = secrets.token_hex(8)
            _db().execute("UPDATE pk_caption_jobs SET status='ishlanmoqda', attempts=COALESCE(attempts,0)+1, lease=?, lease_until=?, stage='boshlandi', pct=0, updated_at=? WHERE id=?",
                          (lease, (now + timedelta(seconds=LEASE)).isoformat(timespec="seconds"), PK._now(), j["id"]))
            PK._log(None, j["course_id"], j["topic_no"], "avto-subtitr: ishchi oldi", f"#{j['id']} · {j['lang']}"); _db().commit()
            break
    rbac.audit(_db(), wc, "paket subtitr: claim", PK.RES, True, f"#{j['id']} · kurs #{j['course_id']} · dars {j['topic_no']} · video #{va['id']}")
    wid = JOB_BASE + j["id"]
    return {"job_id": wid, "kind": "captions", "lease": lease, "lang": j["lang"], "media_url": f"{K.W_CAP}/{wid}/media", "media_ext": "." + va["kind"],
            "name": (va["name"] or "")[:160], "course_id": j["course_id"]}

def _active(wid: int, lease: str | None) -> dict:
    j = db.one(_db(), "SELECT * FROM pk_caption_jobs WHERE id=?", (int(wid) - JOB_BASE,))
    if not j: raise HTTPException(404, "Vazifa topilmadi")
    if j["status"] != "ishlanmoqda": raise HTTPException(410, f"Vazifa faol emas ({j['status']})")
    if lease is not None and j["lease"] and not hmac.compare_digest(str(lease), j["lease"]): raise HTTPException(409, "Lease eskirgan")
    return j

def media(request: Request, wid: int) -> Response:
    _wauth(request, "media")
    j = _active(wid, None)
    a = db.one(_db(), "SELECT * FROM pk_assets WHERE id=? AND deleted=0", (j["asset_id"],))
    if not a or not PK._apath(a).is_file(): raise HTTPException(410, "Video fayli yo'q")
    return PK.range_response(PK._apath(a), PK._CT.get(a["kind"], "application/octet-stream"), request.headers.get("range"),
                             {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

def progress(request: Request, wid: int, stage: str, pct) -> dict:
    _wauth(request, "progress")
    j = _active(wid, request.headers.get("x-worker-lease"))
    until = (clock.now().replace(microsecond=0) + timedelta(seconds=LEASE)).isoformat(timespec="seconds")
    try: p = max(0.0, min(100.0, float(pct)))
    except (TypeError, ValueError): p = 0.0
    with PK._lock:
        _db().execute("UPDATE pk_caption_jobs SET stage=?, pct=?, lease_until=?, updated_at=? WHERE id=?", (str(stage or "")[:40], p, until, PK._now(), j["id"])); _db().commit()
    return {"ok": True}

def fail(request: Request, wid: int, error: str) -> dict:
    wc = _wauth(request, "fail")
    j = _active(wid, request.headers.get("x-worker-lease"))
    err = (str(error or "").strip() or "Noma'lum xato")[:1000]
    with PK._lock:
        _db().execute("UPDATE pk_caption_jobs SET status='xato', error=?, lease=NULL, lease_until=NULL, updated_at=? WHERE id=?", (err, PK._now(), j["id"]))
        PK._log(None, j["course_id"], j["topic_no"], "avto-subtitr: xato", f"#{j['id']} · {err[:150]}"); _db().commit()
    rbac.audit(_db(), wc, "paket subtitr: fail", PK.RES, True, f"#{j['id']}")
    return {"ok": True}

def result(request: Request, wid: int, raw: bytes) -> dict:
    """Ishchi natijasi (WebVTT) → tekshiriladi (paket.to_vtt) → darsning «subs» fayli. Idempotent: vazifa bir marta qabul qilinadi (qayta — 410)."""
    wc = _wauth(request, "result")
    j = _active(wid, request.headers.get("x-worker-lease"))
    if len(raw) > PK.MAX_SUBS: raise HTTPException(413, "Subtitr fayli juda katta")
    v = PK.to_vtt(raw)                                                    # buzilgan VTT — 400 (vazifa ochiq qoladi, ishchi fail yuboradi)
    cid, no, lang = j["course_id"], j["topic_no"], j["lang"]
    with PK._lock:
        j = _active(wid, request.headers.get("x-worker-lease"))           # qulf ostida qayta tekshirish (parallel natija)
        va = _latest_video(cid, no)
        now = PK._now()
        if not va or va["id"] != j["asset_id"]:
            _db().execute("UPDATE pk_caption_jobs SET status='bekor', lease=NULL, lease_until=NULL, error='Video almashtirildi — subtitr qo''shilmadi', updated_at=? WHERE id=?", (now, j["id"]))
            _db().commit(); raise HTTPException(410, "Video almashtirilgan — natija qabul qilinmadi")
        cur = _subs(cid, no).get(lang)
        if cur and cur[1].get("auto") != "whisper":
            _db().execute("UPDATE pk_caption_jobs SET status='tayyor', subs_asset=NULL, cues=?, stage='tayyor', pct=100, lease=NULL, lease_until=NULL, error=?, updated_at=? WHERE id=?",
                          (v["cues"], "Qo'lda yuklangan subtitr bor — avtomatik subtitr qo'shilmadi", now, j["id"])); _db().commit()
            return {"ok": True, "skipped": True, "cues": v["cues"]}
        stem = Path(va["name"] or "video").stem[:80]
        aid = PK._save_asset(None, cid, no, "subs", "vtt", f"{stem}-{lang}-whisper.vtt", v["vtt"].encode("utf-8"),
                             {"lang": lang, "label": f"{PK.SUB_LANGS.get(lang, lang)} (avto)", "cues": v["cues"], "from": "whisper", "auto": "whisper", "job": j["id"]})
        PK._replace_assets(cid, no, "subs", aid, lambda m: m.get("lang") == lang)
        _db().execute("UPDATE pk_caption_jobs SET status='tayyor', subs_asset=?, cues=?, stage='tayyor', pct=100, lease=NULL, lease_until=NULL, error=NULL, updated_at=? WHERE id=?",
                      (aid, v["cues"], now, j["id"]))
        PK._log(None, cid, no, "avto-subtitr tayyor", f"#{j['id']} · {lang} · {v['cues']} yozuv"); _db().commit()
    rbac.audit(_db(), wc, "paket subtitr: result", PK.RES, True, f"#{j['id']} · {v['cues']} yozuv")
    return {"ok": True, "asset": aid, "cues": v["cues"]}

# --------------------------------------------------------------------------------------------- kurs ishchi yo'llariga ulanish
_installed = False

def install() -> bool:
    """kurs.py dagi ishchi funksiyalarini o'rab oladi: raqam JOB_BASE dan katta bo'lsa — paket vazifasi; claim — avval kurs, bo'sh bo'lsa paket.
    kurs.py (va ishchi) o'zgarmaydi; idempotent."""
    global _installed
    if _installed: return True
    try: from . import kurs as K
    except Exception as e:
        print("paket_captions.install:", repr(e)); return False
    o_claim, o_media, o_prog, o_fail, o_res = K.cap_claim, K.cap_media, K.cap_progress, K.cap_fail, K.cap_result
    def w_claim(request):
        r = o_claim(request)
        return r if r is not None else claim(request)
    def w_media(request, jid): return media(request, jid) if owns(jid) else o_media(request, jid)
    def w_prog(request, jid, stage, pct): return progress(request, jid, stage, pct) if owns(jid) else o_prog(request, jid, stage, pct)
    def w_fail(request, jid, error): return fail(request, jid, error) if owns(jid) else o_fail(request, jid, error)
    def w_res(request, jid, raw): return result(request, jid, raw) if owns(jid) else o_res(request, jid, raw)
    K.cap_claim, K.cap_media, K.cap_progress, K.cap_fail, K.cap_result = w_claim, w_media, w_prog, w_fail, w_res
    _installed = True
    return True

def init(con) -> None:
    """paket.init dan: jadval va kurs ishchi yo'llariga ulanish (xato ilovani to'xtatmaydi)."""
    try:
        con.executescript(SCHEMA); con.commit()
        install()
    except Exception as e:
        print("paket_captions.init:", repr(e))

# --------------------------------------------------------------------------------------------- HTTP
class CapAutoIn(BaseModel):
    lang: str = "uz"

@PK.router.post(PK.P + "/courses/{cid}/topics/{no}/captions/auto")
def api_captions_auto(cid: int, no: int, request: Request, body: CapAutoIn | None = None):
    lang = (body.lang if body else "uz")[:8]
    c = PK.C(request); PK.guard(c, "avtomatik subtitr", PK.AUTHORS, f"kurs #{cid} · {PK.lesson_code(no)} · {lang}")
    return request_auto(c, cid, no, lang)

@PK.router.get(PK.P + "/courses/{cid}/topics/{no}/captions/auto")
def api_captions_status(cid: int, no: int, request: Request, lang: str = "uz"):
    c = PK.C(request); PK.guard(c, "avtomatik subtitr holati", PK.WORK, f"kurs #{cid} · {PK.lesson_code(no)}")
    return status(c, cid, no, lang[:8])

@PK.router.post(PK.P + "/courses/{cid}/topics/{no}/captions/auto/cancel")
def api_captions_cancel(cid: int, no: int, request: Request, body: CapAutoIn | None = None):
    lang = (body.lang if body else "uz")[:8]
    c = PK.C(request); PK.guard(c, "avtomatik subtitrni bekor qilish", PK.AUTHORS, f"kurs #{cid} · {PK.lesson_code(no)} · {lang}")
    return cancel(c, cid, no, lang)
