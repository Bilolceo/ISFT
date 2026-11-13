"""Worker rejimi: ISFT Core navbatidan montaj ishlarini olib bajaradi (faqat standart kutubxona — urllib).

Shartnoma (ISFT Core tomonida amalga oshirilgan):
  POST /api/montaj/jobs/claim            → 200 {job_id, template, lesson{...}, lease, raw_url, slides_url|null, logo_url} | 204
  POST /api/montaj/jobs/{id}/progress    {"stage","pct","message"}
  POST /api/montaj/jobs/{id}/result      multipart: video (mp4), captions (vtt), thumbnail (jpg), report (json)
  POST /api/montaj/jobs/{id}/fail        {"error"}
Sarlavha: X-Worker-Token: $ISFT_CORE_WORKER_TOKEN. Yuklab olish URL'lari imzolangan, Range qo'llab-quvvatlanadi.
Claim javobida «lease» bo'lsa — progress/result/fail'ga X-Worker-Lease sarlavhasi bilan qaytariladi (eskirgan lease → 409 → ish bekor).

Signal: 1-SIGINT — joriy ish tugagach chiqish; 2-SIGINT yoki SIGTERM — joriy ishni to'xtatish, /fail, chiqish.
"""
from __future__ import annotations

import http.client
import json
import os
import random
import shutil
import signal
import socket
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from . import run as R
from .common import CancelToken, Cancelled, MontajError, log
from .graphics import Lesson

UA = "isft-montaj-worker/1.0"
CHUNK = 1 << 20


class HttpError(Exception):
    def __init__(self, status, body=""):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


class Api:
    def __init__(self, base: str, token: str, timeout: float = 60.0):
        self.base = base.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout
        self.host = urllib.parse.urlsplit(self.base).netloc

    def url(self, path: str) -> str:
        return urllib.parse.urljoin(self.base, path.lstrip("/") if not path.startswith("http") else path)

    def _headers(self, url: str, extra=None) -> dict:
        h = {"User-Agent": UA}
        if urllib.parse.urlsplit(url).netloc == self.host:  # tokenni begona hostga yubormaymiz
            h["X-Worker-Token"] = self.token
        h.update(extra or {})
        return h

    def request(self, method: str, path: str, *, json_body=None, data=None, headers=None, timeout=None):
        url = self.url(path)
        hdr = self._headers(url, headers)
        body = data
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode()
            hdr["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw and "json" in (r.headers.get("Content-Type") or "") else raw)
        except urllib.error.HTTPError as e:
            raise HttpError(e.code, e.read().decode(errors="replace"))

    # -------------------------------------------------------------- shartnoma
    def claim(self) -> dict | None:
        st, body = self.request("POST", "/api/montaj/jobs/claim", json_body={})
        if st == 204 or not body:
            return None
        if isinstance(body, (bytes, bytearray)):
            body = json.loads(body)
        return body

    @staticmethod
    def _lease(lease) -> dict:
        return {"X-Worker-Lease": str(lease)} if lease else {}

    def progress(self, job_id, stage, pct, message="", lease=None):
        return self.request("POST", f"/api/montaj/jobs/{job_id}/progress",
                            json_body={"stage": stage, "pct": pct, "message": message}, headers=self._lease(lease), timeout=20)

    def fail(self, job_id, error: str, lease=None):
        return self.request("POST", f"/api/montaj/jobs/{job_id}/fail", json_body={"error": error[:4000]},
                            headers=self._lease(lease))

    def result(self, job_id, files: dict, lease=None):
        mp = Multipart(files)
        return self.request("POST", f"/api/montaj/jobs/{job_id}/result", data=mp,
                            headers={"Content-Type": mp.content_type, "Content-Length": str(mp.length), **self._lease(lease)},
                            timeout=600)

    # -------------------------------------------------------------- yuklab olish (Range bilan davom ettirish)
    def download(self, url: str, dest: Path, cancel: CancelToken, retries: int = 6) -> Path:
        url = self.url(url)
        part = dest.with_suffix(dest.suffix + ".part")
        for attempt in range(retries):
            cancel.check()
            have = part.stat().st_size if part.exists() else 0
            hdr = self._headers(url, {"Range": f"bytes={have}-"} if have else None)
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=self.timeout) as r:
                    if have and r.status == 200:  # server Range'ni e'tiborsiz qoldirdi — boshidan
                        have = 0
                    total = None
                    cr = r.headers.get("Content-Range")
                    if cr and "/" in cr and cr.split("/")[-1].isdigit():
                        total = int(cr.split("/")[-1])
                    elif r.headers.get("Content-Length"):
                        total = have + int(r.headers["Content-Length"])
                    with open(part, "ab" if have else "wb") as f:
                        while True:
                            cancel.check()
                            b = r.read(CHUNK)
                            if not b:
                                break
                            f.write(b)
                size = part.stat().st_size
                if total is not None and size < total:
                    raise IOError(f"to'liq yuklanmadi: {size}/{total}")
                part.rename(dest)
                log.info("Yuklandi: %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
                return dest
            except urllib.error.HTTPError as e:
                if e.code == 416 and part.exists():  # allaqachon to'liq
                    part.rename(dest)
                    return dest
                if 400 <= e.code < 500 and e.code not in (408, 429):
                    raise MontajError(f"Yuklab bo'lmadi ({e.code}): {url.split('?')[0]}")
                err = e
            except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as e:
                err = e
            wait = min(60, 2 ** attempt + random.random())
            log.warning("Yuklash uzildi (%s) — %.0f s dan keyin davom ettiriladi", err, wait)
            time.sleep(wait)
        raise MontajError(f"Yuklab bo'lmadi: {url.split('?')[0]}")


class Multipart:
    """Katta fayllarni xotiraga o'qimasdan multipart/form-data sifatida oqim bilan yuborish."""

    def __init__(self, files: dict):
        self.boundary = "----isftmontaj" + uuid.uuid4().hex
        self.content_type = f"multipart/form-data; boundary={self.boundary}"
        self.parts: list = []
        for name, (path, ctype) in files.items():
            path = Path(path)
            head = (f"--{self.boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                    f"filename=\"{path.name}\"\r\nContent-Type: {ctype}\r\n\r\n").encode()
            self.parts += [head, path, b"\r\n"]
        self.parts.append(f"--{self.boundary}--\r\n".encode())
        self.length = sum(p.stat().st_size if isinstance(p, Path) else len(p) for p in self.parts)
        self._i = 0
        self._fh = None
        self._buf = b""

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = 1 << 62
        out = bytearray()
        while len(out) < n and self._i < len(self.parts):
            p = self.parts[self._i]
            if isinstance(p, Path):
                if self._fh is None:
                    self._fh = open(p, "rb")
                b = self._fh.read(min(n - len(out), CHUNK))
                if not b:
                    self._fh.close()
                    self._fh = None
                    self._i += 1
                    continue
                out += b
            else:
                if not self._buf:
                    self._buf = p
                take = self._buf[: n - len(out)]
                out += take
                self._buf = self._buf[len(take):]
                if not self._buf:
                    self._i += 1
        return bytes(out)


# ---------------------------------------------------------------- asosiy tsikl
class Worker:
    def __init__(self, api: Api, work_dir: Path | None = None, poll_min=5.0, poll_max=60.0, model="large-v3",
                 sleep=time.sleep, device="auto", cfg_overrides: dict | None = None):
        self.api = api
        self.work_dir = Path(work_dir) if work_dir else Path(tempfile.gettempdir()) / "isft-montaj-worker"
        self.poll_min, self.poll_max = poll_min, poll_max
        self.model = model
        self.device = device
        self.cfg_overrides = cfg_overrides or {}
        self.stop = False
        self.cancel = CancelToken()
        self.sleep = sleep
        self.current_job = None

    def install_signals(self):
        def on_int(sig, frm):
            if self.stop or sig == signal.SIGTERM:
                log.warning("To'xtatish: joriy ish bekor qilinmoqda")
                self.stop = True
                self.cancel.cancel()
            else:
                log.warning("To'xtatish so'raldi — joriy ish tugagach chiqiladi (yana Ctrl+C — darhol)")
                self.stop = True
        signal.signal(signal.SIGINT, on_int)
        signal.signal(signal.SIGTERM, on_int)

    def loop(self, once: bool = False) -> int:
        delay = self.poll_min
        log.info("Worker ishga tushdi: %s (%s)", self.api.base, socket.gethostname())
        while not self.stop:
            try:
                job = self.api.claim()
            except Exception as e:
                log.warning("claim xatosi: %s", e)
                job = None
                delay = min(self.poll_max, delay * 2)
            if job:
                delay = self.poll_min
                self.process(job)
                if once:
                    break
                continue
            if once:
                break
            # navbat bo'sh — asta-sekin uzayadigan kutish (stop'ni tez sezish uchun bo'laklab)
            end = time.monotonic() + delay
            while not self.stop and time.monotonic() < end:
                self.sleep(min(0.5, end - time.monotonic()))
            delay = min(self.poll_max, delay * 1.5)
        log.info("Worker to'xtadi")
        return 0

    def process(self, job: dict):
        jid = job["job_id"]
        lease = job.get("lease")  # yangi server: lease identifikatori (eski serverda yo'q — sarlavha yuborilmaydi)
        self.current_job = jid
        self.cancel = CancelToken()
        tmp = Path(tempfile.mkdtemp(prefix=f"job_{jid}_", dir=self._ensure_dir()))
        last = {"t": 0.0, "stage": None}

        def progress(stage, pct, msg=""):
            now = time.monotonic()
            if stage == last["stage"] and now - last["t"] < 3:
                return
            last.update(t=now, stage=stage)
            try:
                self.api.progress(jid, stage, pct, msg, lease=lease)
            except HttpError as e:
                if e.status in (404, 409, 410):  # server ishni bekor qilgan
                    log.warning("Server ishni bekor qildi (%s)", e.status)
                    self.cancel.cancel()
                else:
                    log.warning("progress xatosi: %s", e)
            except Exception as e:
                log.warning("progress xatosi: %s", e)

        try:
            log.info("Ish #%s: %s / %s", jid, job.get("template"), (job.get("lesson") or {}).get("title"))
            progress("yuklash", 0, "Fayllar yuklanmoqda")
            raw_name = Path(urllib.parse.urlsplit(job["raw_url"]).path).name or "raw.mp4"
            raw = self.api.download(job["raw_url"], tmp / ("raw" + (Path(raw_name).suffix or ".mp4")), self.cancel)
            slides = None
            if job.get("slides_url"):
                slides = self.api.download(job["slides_url"], tmp / "slides.pdf", self.cancel)
            logo = None
            if job.get("logo_url"):
                try:
                    logo = self.api.download(job["logo_url"], tmp / "logo.png", self.cancel, retries=2)
                except Exception as e:
                    log.warning("Logo yuklanmadi (%s) — standart logo ishlatiladi", e)
            L = job.get("lesson") or {}
            plan = L.get("plan") or []
            plan = [p if isinstance(p, str) else (p.get("title") or p.get("text") or "") for p in plan]
            lesson = Lesson(subject=L.get("subject") or "", code=L.get("code") or "", title=L.get("title") or "",
                            teacher=L.get("teacher") or "", plan=tuple(p for p in plan if p), kind=L.get("kind") or "")
            out = tmp / "out"
            cfg = R.Config(input=raw, out=out, template=job.get("template") or "maruza_slayd", lesson=lesson,
                           slides=slides, logo=logo, model=self.model, device=self.device,
                           **self.cfg_overrides)
            # foizlar: yuklash 0–2, quvur 2–97, natijani yuborish 97–99 (100 — server tomonida)
            R.run(cfg, progress_cb=lambda st, pct, msg: progress(st, round(2 + pct * 0.95, 1), msg),
                  cancel=self.cancel)
            progress("yuborish", 97, "Natija yuborilmoqda")
            files = {"video": (out / "final.mp4", "video/mp4"), "captions": (out / "captions.vtt", "text/vtt"),
                     "thumbnail": (out / "thumbnail.jpg", "image/jpeg"),
                     "report": (out / "report.json", "application/json")}
            for attempt in range(4):
                try:
                    self.api.result(jid, files, lease=lease)
                    break
                except HttpError as e:
                    if 400 <= e.status < 500:
                        raise
                    if attempt == 3:
                        raise
                except Exception:
                    if attempt == 3:
                        raise
                time.sleep(5 * (attempt + 1))
            log.info("Ish #%s yakunlandi", jid)
        except Exception as e:
            if isinstance(e, Cancelled):
                msg = "Worker to'xtatildi yoki ish bekor qilindi"
            elif isinstance(e, MontajError):
                msg = str(e)
            else:
                msg = f"{type(e).__name__}: {e}"
                log.error(traceback.format_exc())
            log.error("Ish #%s xato: %s", jid, msg)
            try:
                self.api.fail(jid, msg, lease=lease)
            except Exception as e2:
                log.error("fail yuborilmadi: %s", e2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.current_job = None

    def _ensure_dir(self) -> Path:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        return self.work_dir


def main(args) -> int:
    token = os.environ.get("ISFT_CORE_WORKER_TOKEN", "")
    if not token:
        log.error("ISFT_CORE_WORKER_TOKEN o'rnatilmagan")
        return 2
    w = Worker(Api(args.api, token), args.work_dir, args.poll_min, args.poll_max, model=args.model,
               device=args.device)
    w.install_signals()
    return w.loop(once=args.once)
