"""Kurs videolari uchun subtitr navbati (ISFT Core /api/montaj/kurs-captions) — worker tomoni, jarayon ichidagi soxta API bilan.

Tekshiriladi: montaj navbati bo'sh → subtitr claim → video yuklab olinadi (token sarlavhasi bilan) → audio ajratish → nutq tanish
(faster-whisper o'rniga soxta natija — model kerak emas) → WebVTT → /result (lease sarlavhasi); xato yo'li → /fail; eski server (404) —
subtitr navbati shu sessiyada qayta so'ralmaydi. Og'ir fixture'lar (ffmpeg bilan video yasash) talab qilinmaydi.

Ishga tushirish: ~/.local/montaj-venv/bin/python -m unittest tools/montaj/tests/test_captions_worker.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import worker as Wk  # noqa: E402
from pipeline import asr, common  # noqa: E402

TOKEN = "cap-token"


class Core:
    def __init__(self, cap_jobs, captions_supported=True):
        self.cap_jobs = list(cap_jobs)
        self.supported = captions_supported
        self.posts, self.results, self.fails, self.gets = [], {}, {}, []
        core = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", ct="application/json"):
                self.send_response(code)
                if body:
                    self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                core.gets.append((self.path, self.headers.get("X-Worker-Token")))
                if self.headers.get("X-Worker-Token") != TOKEN:
                    return self._send(401, b'{"detail":"token"}')
                if self.path.startswith("/api/montaj/kurs-captions/") and self.path.endswith("/media"):
                    return self._send(200, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000, "video/mp4")
                return self._send(404, b'{"detail":"yo\'q"}')

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                core.posts.append((self.path, self.headers.get("X-Worker-Lease")))
                if self.headers.get("X-Worker-Token") != TOKEN:
                    return self._send(401, b'{"detail":"token"}')
                if self.path == "/api/montaj/jobs/claim":
                    return self._send(204)
                if not self.path.startswith("/api/montaj/kurs-captions/") or not core.supported:
                    return self._send(404, b'{"detail":"Not Found"}')
                if self.path.endswith("/claim"):
                    return self._send(200, json.dumps(core.cap_jobs.pop(0)).encode()) if core.cap_jobs else self._send(204)
                jid = self.path.split("/")[4]
                if self.path.endswith("/result"):
                    core.results[jid] = (self.headers.get("Content-Type"), body)
                elif self.path.endswith("/fail"):
                    core.fails[jid] = json.loads(body)
                return self._send(200, b'{"ok":true}')

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


def cap_job(jid, lang="uz"):
    return {"job_id": jid, "kind": "captions", "lease": "ab12cd34ef56ab78", "lang": lang, "media_url": f"/api/montaj/kurs-captions/{jid}/media",
            "media_ext": ".mp4", "name": "dars.mp4", "course_id": 3}


FAKE_TR = {"duration": 6.0, "segments": [{"start": 0.2, "end": 5.4, "text": "Assalomu alaykum. Bugun ma'lumotlar bazasini o'rganamiz.", "words": [
    {"start": 0.2, "end": 0.7, "word": "Assalomu", "prob": 0.9}, {"start": 0.75, "end": 1.2, "word": "alaykum.", "prob": 0.9},
    {"start": 1.6, "end": 2.0, "word": "Bugun", "prob": 0.9}, {"start": 2.05, "end": 2.9, "word": "ma'lumotlar", "prob": 0.9},
    {"start": 2.95, "end": 3.6, "word": "bazasini", "prob": 0.9}, {"start": 3.65, "end": 5.4, "word": "o'rganamiz.", "prob": 0.9}]}]}


class CaptionsWorkerTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="capw_"))
        self.calls = {"ffmpeg": [], "asr": []}
        self._ff, self._tr = common.run_ffmpeg, asr.transcribe

        def fake_ffmpeg(args, **kw):
            self.calls["ffmpeg"].append(args)
            Path(args[-1]).write_bytes(b"RIFF....WAVE")
            return ""

        def fake_transcribe(wav, **kw):
            self.calls["asr"].append(kw)
            if kw.get("language") == "ru":
                return {"duration": 3.0, "segments": []}
            for f in (0.5, 1.0):
                kw["on_progress"](f)
            return FAKE_TR
        common.run_ffmpeg, asr.transcribe = fake_ffmpeg, fake_transcribe

    def tearDown(self):
        common.run_ffmpeg, asr.transcribe = self._ff, self._tr
        shutil.rmtree(self.work, ignore_errors=True)

    def test_caption_cycle_and_fail(self):
        core = Core([cap_job("5"), cap_job("6", "ru")])
        try:
            w = Wk.Worker(Wk.Api(core.url, TOKEN), self.work, poll_min=0.01, poll_max=0.02, sleep=lambda s: None)
            w.loop(once=True)
            self.assertIn("5", core.results, core.fails)
            ct, vtt = core.results["5"]
            self.assertTrue(ct.startswith("text/vtt"))
            text = vtt.decode()
            self.assertTrue(text.startswith("WEBVTT"), text)
            self.assertIn("Assalomu alaykum.", text)
            self.assertRegex(text, r"00:00:00\.\d{3} --> 00:00:0\d\.\d{3}")
            self.assertEqual(self.calls["asr"][0]["language"], "uz")
            self.assertIn("16000", self.calls["ffmpeg"][0])
            # media — token bilan; progress/result — lease bilan
            self.assertTrue(any(p.endswith("/5/media") and t == TOKEN for p, t in core.gets))
            leased = [lz for p, lz in core.posts if "/kurs-captions/5/" in p]
            self.assertTrue(leased and all(lz == "ab12cd34ef56ab78" for lz in leased), core.posts)
            # 2-ish: nutq topilmadi → /fail (tushunarli xabar)
            w.loop(once=True)
            self.assertIn("6", core.fails)
            self.assertIn("nutq topilmadi", core.fails["6"]["error"])
            self.assertEqual(list(self.work.glob("cap_*")), [])
        finally:
            core.close()

    def test_old_server_404(self):
        core = Core([], captions_supported=False)
        try:
            w = Wk.Worker(Wk.Api(core.url, TOKEN), self.work, poll_min=0.01, poll_max=0.02, sleep=lambda s: None)
            w.loop(once=True)
            self.assertFalse(w.captions_on)
            n = len(core.posts)
            w.loop(once=True)
            self.assertEqual([p for p, _ in core.posts[n:]], ["/api/montaj/jobs/claim"])   # subtitr navbati qayta so'ralmadi
        finally:
            core.close()


if __name__ == "__main__":
    unittest.main()
