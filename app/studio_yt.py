"""Studiya → YouTube: institut kanaliga «unlisted» (havola orqali) videoni yuklash (YouTube Data API v3, resumable upload). docs/studio.md

Yangi bog'liqlik yo'q — faqat httpx (sinxron mijoz; fon oqimida chaqiriladi). Testlarda HTTP soxtalashtiriladi: `TRANSPORT = httpx.MockTransport(...)`.

OAuth: client id / client secret / refresh token — app/secret_store'da (bazada EMAS). Hech qachon logga yozilmaydi va hech qaysi API'da
qaytarilmaydi: status() faqat «bor / yo'q» belgilarini beradi. Access token — faqat xotirada (≈1 soat), muddati tugasa yoki 401 kelsa yangilanadi.

Protokol (https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol):
  1) POST {UPLOAD_URL}?uploadType=resumable&part=snippet,status  (JSON metama'lumot, X-Upload-Content-Length/-Type) → 200 + Location (sessiya)
  2) PUT <sessiya> bo'laklab (Content-Range: bytes a-b/N; bo'lak 256 KiB ga karrali) → 308 (Range: bytes=0-k) … oxirgisi → 200/201 + video
  3) uzilsa: PUT <sessiya> «Content-Range: bytes */N» → 308 (qayerdan davom etish) yoki 200/201 (allaqachon tugagan); 404/410 — sessiya eskirgan
  4) holat: GET videos?part=status,processingDetails&id=… → uploadStatus: uploaded → processed (yoki failed / rejected)
Xatolar YTError(kind): quota (kunlik kvota — ertaga), auth (refresh token yaroqsiz — sozlamada yangilash), retry (5xx/429/tarmoq — keyinroq),
session (sessiya yo'qoldi — yangidan), fatal (boshqa 4xx — operator).
"""
from __future__ import annotations
import json, os, re, threading, time
from pathlib import Path
import httpx
from . import secret_store

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API = "https://www.googleapis.com/youtube/v3"
K_ID, K_SECRET, K_REFRESH = "youtube.client_id", "youtube.client_secret", "youtube.refresh_token"
KEYS = (K_ID, K_SECRET, K_REFRESH)
TRANSPORT = None                    # testlar: httpx.MockTransport — tarmoqqa chiqilmaydi
CHUNK_UNIT = 256 * 1024
_tok = {"v": None, "exp": 0.0}
_lock = threading.Lock()
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}


class YTError(Exception):
    def __init__(self, kind: str, message: str, status: int = 0, reason: str = ""):
        super().__init__(message)
        self.kind, self.message, self.status, self.reason = kind, message, status, reason


def chunk_size() -> int:
    """ISFT_CORE_YT_CHUNK_MB (standart 8) — 256 KiB ga karrali qilib yaxlitlanadi."""
    try: mb = float(os.getenv("ISFT_CORE_YT_CHUNK_MB", "8"))
    except ValueError: mb = 8
    return max(1, int(mb * 1024 * 1024) // CHUNK_UNIT) * CHUNK_UNIT


def daily_cap() -> int:
    """ISFT_CORE_YT_DAILY — bir kunda boshlanadigan yuklashlar (standart 6: har biri ≈1600 kvota birligi, kunlik kvota 10 000)."""
    try: return max(0, int(os.getenv("ISFT_CORE_YT_DAILY", "6")))
    except ValueError: return 6


def privacy() -> str:
    p = (os.getenv("ISFT_CORE_YT_PRIVACY") or "unlisted").strip().lower()
    return p if p in ("unlisted", "private", "public") else "unlisted"


# ---------------------------------------------------------------------------------------------
# Sirlar (secret_store) — qiymatlar tashqariga chiqmaydi
# ---------------------------------------------------------------------------------------------
def _get(k: str) -> str:
    try: return (secret_store.get(k) or "").strip()
    except Exception: return ""

def configured() -> bool:
    if os.getenv("ISFT_CORE_YT_OFF", "").strip().lower() in ("1", "true", "yes", "ha"): return False
    return all(_get(k) for k in KEYS)

def status() -> dict:
    """Faqat belgilar: qaysi sir saqlangan (qiymat emas)."""
    have = {k: bool(_get(k)) for k in KEYS}
    return {"configured": configured(), "client_id": have[K_ID], "client_secret": have[K_SECRET], "refresh_token": have[K_REFRESH],
            "store": secret_store.status()["note"], "encrypted": secret_store.status()["encrypted"], "privacy": privacy(),
            "daily_cap": daily_cap(), "off_env": os.getenv("ISFT_CORE_YT_OFF", "").strip().lower() in ("1", "true", "yes", "ha")}

_ID_RX = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{5,120}\.apps\.googleusercontent\.com$")

def save(client_id: str = "", client_secret: str = "", refresh_token: str = "") -> list[str]:
    """Bo'sh bo'lmagan maydonlargina yangilanadi. → o'zgargan maydonlar nomi (qiymatlarsiz)."""
    ch = []
    client_id, client_secret, refresh_token = (x.strip() if isinstance(x, str) else "" for x in (client_id, client_secret, refresh_token))
    if client_id:
        if not _ID_RX.match(client_id): raise ValueError("Client ID ko'rinishi noto'g'ri (…apps.googleusercontent.com bilan tugaydi)")
        secret_store.put(K_ID, client_id); ch.append("client_id")
    if client_secret:
        if not re.fullmatch(r"[\x21-\x7e]{8,200}", client_secret): raise ValueError("Client secret ko'rinishi noto'g'ri")
        secret_store.put(K_SECRET, client_secret); ch.append("client_secret")
    if refresh_token:
        if not re.fullmatch(r"[\x21-\x7e]{20,1024}", refresh_token): raise ValueError("Refresh token ko'rinishi noto'g'ri")
        secret_store.put(K_REFRESH, refresh_token); ch.append("refresh_token")
    if ch: reset_token()
    return ch

def clear() -> None:
    for k in KEYS: secret_store.delete(k)
    reset_token()

def reset_token() -> None:
    with _lock: _tok.update(v=None, exp=0.0)


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
def client() -> httpx.Client:
    return httpx.Client(transport=TRANSPORT, timeout=httpx.Timeout(60.0, read=300.0, write=300.0), follow_redirects=False)

def _reason(r: httpx.Response) -> tuple[str, str]:
    """Google xato javobidan (sabab, qisqa matn) — matnda token yo'q (javob tanasi Google'niki)."""
    try: d = r.json()
    except ValueError: return "", ""
    e = d.get("error") if isinstance(d, dict) else None
    if isinstance(e, str): return e, str(d.get("error_description") or "")[:200]
    if isinstance(e, dict):
        errs = e.get("errors") or []
        rs = errs[0].get("reason") if errs and isinstance(errs[0], dict) else ""
        return str(rs or e.get("status") or ""), str(e.get("message") or "")[:200]
    return "", ""

def classify(r: httpx.Response, what: str) -> YTError:
    reason, msg = _reason(r)
    s = r.status_code
    if s in (429, 500, 502, 503, 504):
        return YTError("retry", f"{what}: YouTube vaqtincha javob bermadi (HTTP {s}) — keyinroq qayta uriniladi", s, reason)
    if s == 403 and reason in QUOTA_REASONS:
        return YTError("quota", f"{what}: YouTube kunlik kvotasi tugadi ({reason}) — ertaga avtomatik davom etadi", s, reason)
    if s == 401:
        return YTError("auth", f"{what}: YouTube ruxsat bermadi (401) — OAuth sozlamasini tekshiring", s, reason)
    if s == 403:
        hint = {"forbidden": "kanalga yuklash huquqi yo'q", "youtubeSignupRequired": "akkauntda YouTube kanali ochilmagan",
                "insufficientPermissions": "refresh token youtube.upload ruxsati bilan olinmagan"}.get(reason, msg or "ruxsat yo'q")
        return YTError("fatal", f"{what}: YouTube rad etdi (403 · {reason or 'forbidden'}) — {hint}", s, reason)
    if s in (404, 410):
        return YTError("session", f"{what}: yuklash sessiyasi topilmadi (HTTP {s}) — yangidan boshlanadi", s, reason)
    return YTError("fatal", f"{what}: YouTube xatosi (HTTP {s}{' · ' + reason if reason else ''}){' — ' + msg if msg else ''}", s, reason)

def access_token(cl: httpx.Client, force: bool = False) -> str:
    """Refresh token → access token (xotirada, muddatidan 60 s oldin yangilanadi)."""
    with _lock:
        if not force and _tok["v"] and _tok["exp"] - 60 > time.time(): return _tok["v"]
    cid, sec, rt = (_get(k) for k in KEYS)
    if not (cid and sec and rt): raise YTError("auth", "YouTube sozlanmagan: client id, client secret va refresh token kerak")
    try:
        r = cl.post(TOKEN_URL, data={"grant_type": "refresh_token", "client_id": cid, "client_secret": sec, "refresh_token": rt})
    except httpx.HTTPError as e:
        raise YTError("retry", f"Google'ga ulanib bo'lmadi (token): {type(e).__name__}")
    if r.status_code != 200:
        reason, _ = _reason(r)
        if reason in ("invalid_grant", "invalid_client", "unauthorized_client"):
            raise YTError("auth", {"invalid_grant": "Refresh token yaroqsiz yoki bekor qilingan (ilova «Testing» holatida token 7 kunda eskiradi) — "
                                                    "Sozlamalarda yangi refresh token kiriting",
                                   "invalid_client": "Client ID yoki client secret noto'g'ri — Sozlamalarni tekshiring",
                                   "unauthorized_client": "Bu OAuth mijozi refresh token ishlatishi mumkin emas — mijoz turini tekshiring"}[reason],
                          r.status_code, reason)
        if r.status_code >= 500: raise YTError("retry", f"Google token xizmati vaqtincha ishlamayapti (HTTP {r.status_code})", r.status_code)
        raise YTError("auth", f"Access token olinmadi (HTTP {r.status_code}{' · ' + reason if reason else ''})", r.status_code, reason)
    d = r.json()
    with _lock:
        _tok.update(v=d.get("access_token"), exp=time.time() + float(d.get("expires_in") or 3600))
        return _tok["v"]

def _authed(cl: httpx.Client, method: str, url: str, what: str, **kw) -> httpx.Response:
    """Bearer bilan so'rov; 401 bo'lsa token bir marta yangilanib qayta yuboriladi."""
    for i in range(2):
        h = dict(kw.pop("headers", None) or {}) if i == 0 else h
        h["Authorization"] = "Bearer " + access_token(cl, force=bool(i))
        try: r = cl.request(method, url, headers=h, **kw)
        except httpx.HTTPError as e:
            raise YTError("retry", f"{what}: YouTube'ga ulanib bo'lmadi ({type(e).__name__}) — keyinroq qayta uriniladi")
        if r.status_code != 401: return r
    return r


# ---------------------------------------------------------------------------------------------
# Resumable upload
# ---------------------------------------------------------------------------------------------
def start_session(cl: httpx.Client, meta: dict, size: int, ctype: str = "video/mp4") -> str:
    r = _authed(cl, "POST", UPLOAD_URL, "Yuklashni boshlash", params={"uploadType": "resumable", "part": "snippet,status"},
                headers={"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Length": str(int(size)), "X-Upload-Content-Type": ctype},
                content=json.dumps(meta, ensure_ascii=False).encode("utf-8"))
    if r.status_code not in (200, 201): raise classify(r, "Yuklashni boshlash")
    loc = r.headers.get("Location") or r.headers.get("location")
    if not loc or not loc.startswith("https://"): raise YTError("retry", "YouTube yuklash sessiyasi manzilini bermadi")
    return loc

def _range_end(r: httpx.Response) -> int:
    """308 javobidagi «Range: bytes=0-k» → keyingi bayt (k+1); sarlavha yo'q — 0."""
    m = re.match(r"bytes=0-(\d+)", r.headers.get("Range") or r.headers.get("range") or "")
    return int(m.group(1)) + 1 if m else 0

def query_offset(cl: httpx.Client, session: str, size: int) -> tuple[int, dict | None]:
    """Uzilgan yuklash: serverda qancha bayt borligi. → (keyingi bayt, None) yoki (size, video) — allaqachon tugagan."""
    r = _authed(cl, "PUT", session, "Yuklash holati", headers={"Content-Range": f"bytes */{int(size)}", "Content-Length": "0"}, content=b"")
    if r.status_code == 308: return _range_end(r), None
    if r.status_code in (200, 201): return int(size), r.json()
    raise classify(r, "Yuklash holati")

def upload(cl: httpx.Client, session: str, path: Path, size: int, offset: int = 0, chunk: int | None = None, on_chunk=None) -> dict:
    """offset dan boshlab bo'laklab yuboradi; har bo'lakdan keyin on_chunk(yangi offset). → YouTube video resursi (id, status …)."""
    chunk = chunk or chunk_size()
    with open(path, "rb") as f:
        while True:
            f.seek(offset)
            data = f.read(chunk if offset + chunk < size else size - offset)
            end = offset + len(data) - 1
            r = _authed(cl, "PUT", session, "Video bo'lagi", headers={"Content-Range": f"bytes {offset}-{end}/{int(size)}", "Content-Type": "video/mp4"},
                        content=data)
            if r.status_code in (200, 201):
                if on_chunk: on_chunk(int(size))
                return r.json()
            if r.status_code != 308: raise classify(r, "Video bo'lagi")
            nxt = _range_end(r)
            if nxt <= offset and data:              # server bo'lakni qabul qilmadi — qayta urinish (cheksiz aylanmasin)
                raise YTError("retry", "YouTube bo'lakni qabul qilmadi — keyinroq davom etadi")
            offset = nxt
            if on_chunk: on_chunk(offset)
            if offset >= size: raise YTError("retry", "YouTube yakuniy javobni bermadi — holat keyinroq tekshiriladi")

def video_status(cl: httpx.Client, vid: str) -> dict | None:
    r = _authed(cl, "GET", f"{API}/videos", "Video holati", params={"part": "status,processingDetails", "id": vid})
    if r.status_code != 200: raise classify(r, "Video holati")
    items = r.json().get("items") or []
    return items[0] if items else None

def channel(cl: httpx.Client) -> dict:
    """Ulanishni tekshirish: token olinadi va kanal nomi o'qiladi (youtube.upload ruxsati kanalni o'qishga yetmasa — faqat token natijasi)."""
    access_token(cl, force=True)
    r = _authed(cl, "GET", f"{API}/channels", "Kanal", params={"part": "snippet", "mine": "true"})
    if r.status_code == 200:
        it = (r.json().get("items") or [{}])[0]
        return {"ok": True, "channel": (it.get("snippet") or {}).get("title") or "", "channel_id": it.get("id") or ""}
    if r.status_code == 403: return {"ok": True, "channel": "", "note": "Token ishlaydi; kanal nomini o'qish uchun ruxsat yo'q (faqat youtube.upload) — bu normal"}
    raise classify(r, "Kanal")


# ---------------------------------------------------------------------------------------------
# Metama'lumot: sarlavha, tavsif (reja + bo'limlar), teglar
# ---------------------------------------------------------------------------------------------
def _clean(s: str) -> str:
    return re.sub(r"[<>]", "", re.sub(r"\s+", " ", str(s or ""))).strip()

def ts_label(sec: float) -> str:
    s = max(0, int(sec or 0))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"

def chapters_text(chapters: list) -> list[str]:
    """YouTube bo'limlari: birinchisi 0:00, kamida 3 ta, har biri ≥ 10 s — shart bajarilmasa bo'limlar yozilmaydi (YouTube baribir ko'rsatmaydi)."""
    ch = []
    for c in chapters or []:
        try: t = float(c.get("start") or 0)
        except (TypeError, ValueError, AttributeError): continue
        title = _clean(c.get("title"))[:80]
        if title: ch.append((t, title))
    ch.sort()
    if not ch: return []
    if ch[0][0] > 0: ch[0] = (0.0, ch[0][1])
    ok = len(ch) >= 3 and all(b[0] - a[0] >= 10 for a, b in zip(ch, ch[1:]))
    return [f"{ts_label(t)} {title}" for t, title in ch] if ok else []

def metadata(lesson: dict, chapters: list | None = None) -> dict:
    """Sarlavha: «{fan} · {L1}: {mavzu}» (≤100 belgi); tavsif: reja + bo'limlar (≤5000 bayt); teglar (jami ≤500 belgi); toifa 27 (Ta'lim)."""
    title = _clean(f"{lesson.get('subject') or ''} · {lesson.get('code') or ''}: {lesson.get('title') or ''}")
    if len(title) > 100: title = title[:99].rstrip() + "…"
    lines = [_clean(f"{lesson.get('subject') or ''} — {lesson.get('code') or ''}: {lesson.get('title') or ''}")]
    if lesson.get("teacher"): lines.append(_clean(f"O'qituvchi: {lesson['teacher']}"))
    plan = [_clean(x) for x in (lesson.get("plan") or []) if _clean(x)]
    if plan: lines += ["", "Reja:"] + [f"{i}. {x[:200]}" for i, x in enumerate(plan[:30], 1)]
    ch = chapters_text(chapters or [])
    if ch: lines += ["", "Bo'limlar:"] + ch
    lines += ["", "ISFT — masofaviy ta'lim"]
    desc = "\n".join(lines)
    while len(desc.encode("utf-8")) > 4900: desc = desc[:-200]
    tags, total = [], 0
    for t in (lesson.get("subject"), "ISFT", "masofaviy ta'lim", lesson.get("code"), lesson.get("dept")):
        t = _clean(t)[:60]
        if t and t not in tags and total + len(t) + 2 <= 480: tags.append(t); total += len(t) + 2
    return {"snippet": {"title": title or "ISFT videodars", "description": desc, "tags": tags, "categoryId": "27", "defaultLanguage": "uz",
                        "defaultAudioLanguage": "uz"},
            "status": {"privacyStatus": privacy(), "selfDeclaredMadeForKids": False, "embeddable": True}}
