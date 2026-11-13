"""Worker rejimi sinovi: jarayon ichidagi soxta ISFT Core API (http.server).

Tekshiriladi: claim → Range bilan yuklab olish (birinchi urinishda aloqa uziladi → davom ettirish) →
progress → multipart natija; xato yo'li (/fail); 204 bo'lganda kutish; token sarlavhasi.
"""
from __future__ import annotations

import email.parser
import email.policy
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from pipeline import worker as Wk  # noqa: E402

TOKEN = "test-token-123"


class MockCore:
    def __init__(self, files: dict, jobs: list):
        self.files = files            # url yo'li → Path
        self.jobs = list(jobs)
        self.progress: list = []
        self.results: dict = {}
        self.fails: dict = {}
        self.range_requests: list = []
        self.leases: list = []        # (yo'l, X-Worker-Lease) — har POST
        self.dropped = set()
        self.bad_token = 0
        self.result_delay = 0.0       # natija javobini kechiktirish (uzoq yuklash taqlidi — parallel progress ping'lari)
        core = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj=None):
                body = json.dumps(obj).encode() if obj is not None else b""
                self.send_response(code)
                if obj is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _auth(self):
                if self.headers.get("X-Worker-Token") != TOKEN:
                    core.bad_token += 1
                    self._json(401, {"error": "token"})
                    return False
                return True

            def do_GET(self):
                path = self.path.split("?")[0]
                f = core.files.get(path)
                if not f:
                    return self._json(404, {"error": "yo'q"})
                data = f.read_bytes()
                rng = self.headers.get("Range")
                start = 0
                if rng:
                    core.range_requests.append((path, rng))
                    start = int(rng.split("=")[1].split("-")[0])
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(data) - start))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                if path not in core.dropped and len(data) > 100_000:
                    # birinchi so'rovda yarmini yuborib aloqani uzamiz
                    core.dropped.add(path)
                    self.wfile.write(data[start:start + (len(data) - start) // 2])
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.wfile.write(data[start:])

            def do_POST(self):
                if not self._auth():
                    return
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                p = self.path
                core.leases.append((p, self.headers.get("X-Worker-Lease")))
                if p == "/api/montaj/jobs/claim":
                    if core.jobs:
                        return self._json(200, core.jobs.pop(0))
                    return self._json(204)
                jid = p.split("/")[4]
                if p.endswith("/progress"):
                    core.progress.append((jid, json.loads(body)))
                    return self._json(200, {"ok": True})
                if p.endswith("/fail"):
                    core.fails[jid] = json.loads(body)
                    return self._json(200, {"ok": True})
                if p.endswith("/result"):
                    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
                        b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
                    parts = {}
                    for part in msg.iter_parts():
                        name = part.get_param("name", header="content-disposition")
                        parts[name] = (part.get_filename(), part.get_content_type(), part.get_payload(decode=True))
                    core.results[jid] = parts
                    if core.result_delay:
                        import time as _t
                        _t.sleep(core.result_delay)
                    return self._json(200, {"ok": True})
                return self._json(404)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def job(jid, raw="/files/raw.mp4?sig=abc", slides="/files/slides.pdf?sig=def"):
    return {"job_id": jid, "template": "maruza_slayd",
            "lesson": {"course_id": 7, "no": 3, "code": "L3", "kind": "maruza",
                       "title": "Relyatsion model va SQL so'rovlari", "subject": "Ma'lumotlar bazasi",
                       "teacher": "Karimova Dilnoza O'tkirovna", "plan": list(fixtures.PLAN)},
            "raw_url": raw, "slides_url": slides, "logo_url": "/files/logo.png?sig=x"}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.meta = fixtures.make_all()
        from pipeline.common import DEFAULT_LOGO
        # j1 — eski server kabi raw_ext'siz, imzolangan havola nomida «kengaytma» yo'q (17.raw.<muddat>.<imzo>): kengaytma baytlardan
        self.core = MockCore({"/files/raw.mp4": Path(self.meta["teacher"]), "/files/17.raw.1763030000.deadbeef": Path(self.meta["teacher"]),
                              "/files/slides.pdf": Path(self.meta["slides"]), "/files/logo.png": DEFAULT_LOGO},
                             [{**job("j1", raw="/files/17.raw.1763030000.deadbeef"), "lease": "aa11bb22cc33dd44"},
                              job("j2", raw="/files/missing.mp4?sig=zzz", slides=None)])
        self.work = fixtures.SCRATCH / "worker_work"

    def tearDown(self):
        self.core.close()

    def test_full_cycle_and_fail_path(self):
        sleeps = []
        w = Wk.Worker(Wk.Api(self.core.url, TOKEN), self.work, poll_min=0.01, poll_max=0.02,
                      sleep=lambda s: sleeps.append(s))
        w.upload_ping_s = 0.1
        self.core.result_delay = 0.6
        inputs = []
        orig_run = Wk.R.run

        def run_spy(cfg, **kw):
            inputs.append(Path(cfg.input))
            return orig_run(cfg, **kw)
        Wk.R.run = run_spy
        # 1-ish: muvaffaqiyatli
        try:
            w.loop(once=True)
        finally:
            Wk.R.run = orig_run
        # xom video kengaytmasi imzolangan havola nomidan («.deadbeef») emas — baytlardan (ftyp → .mp4)
        self.assertEqual([x.suffix for x in inputs], [".mp4"], inputs)
        self.assertIn("j1", self.core.results, self.core.fails)
        parts = self.core.results["j1"]
        self.assertEqual(set(parts), {"video", "captions", "thumbnail", "report"})
        self.assertEqual(parts["video"][1], "video/mp4")
        self.assertGreater(len(parts["video"][2]), 100_000)
        self.assertTrue(parts["captions"][2].startswith(b"WEBVTT"))
        self.assertEqual(parts["thumbnail"][2][:2], b"\xff\xd8")  # JPEG
        rep = json.loads(parts["report"][2])
        self.assertEqual(list(rep), ["duration_in", "duration_out", "cuts", "chapters", "slide_changes",
                                     "warnings", "timings"])
        # Range bilan davom ettirildi
        self.assertTrue(any(p == "/files/17.raw.1763030000.deadbeef" and r.startswith("bytes=") and r != "bytes=0-"
                            for p, r in self.core.range_requests), self.core.range_requests)
        # progress: bosqichlar va foiz o'sib boradi
        pr = [p for j, p in self.core.progress if j == "j1"]
        stages = [p["stage"] for p in pr]
        for st in ["yuklash", "nutq", "render", "yuborish"]:
            self.assertIn(st, stages)
        pcts = [p["pct"] for p in pr if p["stage"] != "yuklash"]
        self.assertEqual(pcts, sorted(pcts))
        # natija yuborilayotganda: oldin majburiy ping («yuborish», 97), uzoq yuklashda parallel oqimdan yana ping'lar (lease uzaytiriladi)
        sends = [p for p in pr if p["stage"] == "yuborish"]
        self.assertGreaterEqual(len(sends), 3, sends)
        self.assertTrue(all(p["pct"] == 97 for p in sends))
        self.assertTrue(all(set(p) == {"stage", "pct", "message"} for p in pr))
        # vaqtinchalik fayllar tozalangan
        self.assertEqual(list(self.work.glob("job_j1_*")), [])

        # 2-ish: xom fayl yo'q → /fail
        w.loop(once=True)
        self.assertIn("j2", self.core.fails)
        self.assertIn("Yuklab bo'lmadi", self.core.fails["j2"]["error"])
        self.assertNotIn("j2", self.core.results)

        # lease: j1 (server bergan) — progress/result'da X-Worker-Lease; j2 (eski server, lease yo'q) — sarlavhasiz
        j1 = [lz for pth, lz in self.core.leases if "/jobs/j1/" in pth]
        self.assertTrue(j1 and all(lz == "aa11bb22cc33dd44" for lz in j1), self.core.leases)
        self.assertTrue(any(pth.endswith("/j1/result") for pth, _ in self.core.leases))
        j2 = [lz for pth, lz in self.core.leases if "/jobs/j2/" in pth]
        self.assertTrue(j2 and all(lz is None for lz in j2), self.core.leases)

        # navbat bo'sh → 204 → once rejimida chiqadi
        self.assertEqual(w.loop(once=True), 0)
        self.assertEqual(self.core.bad_token, 0)

    def test_bad_token_and_backoff(self):
        sleeps = []
        w = Wk.Worker(Wk.Api(self.core.url, "noto'g'ri"), self.work, poll_min=0.01, poll_max=0.05,
                      sleep=lambda s: sleeps.append(s))
        calls = {"n": 0}
        orig = w.api.claim

        def claim():
            calls["n"] += 1
            if calls["n"] >= 4:
                w.stop = True
            return orig()
        w.api.claim = claim
        w.loop()
        self.assertGreaterEqual(self.core.bad_token, 3)
        self.assertNotIn("j1", self.core.results)

    def test_raw_suffix(self):
        """Xom video kengaytmasi: raw_ext (server) → Content-Type / Content-Disposition → baytlar → .mp4; token nomidan EMAS."""
        from email.message import Message

        def hdr(**kw):
            m = Message()
            for k, v in kw.items():
                m[k.replace("_", "-")] = v
            return m
        mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"
        mov = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00"
        mkv = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01" + b"matroska"
        webm = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01" + b"webm"
        self.assertEqual(Wk.raw_suffix({"raw_ext": ".mov"}, hdr(Content_Type="video/mp4"), mp4), ".mov")
        self.assertEqual(Wk.raw_suffix({"raw_ext": "MKV"}), ".mkv")
        self.assertEqual(Wk.raw_suffix({"raw_ext": ".exe"}, None, webm), ".webm")          # yaroqsiz raw_ext — e'tiborsiz
        self.assertEqual(Wk.raw_suffix({}, hdr(Content_Type="video/quicktime"), mp4), ".mov")
        self.assertEqual(Wk.raw_suffix({}, hdr(Content_Type="application/octet-stream",
                                               Content_Disposition='attachment; filename="dars 3.MKV"'), mp4), ".mkv")
        self.assertEqual(Wk.raw_suffix({}, hdr(Content_Type="application/octet-stream"), mov), ".mov")
        self.assertEqual(Wk.raw_suffix({}, None, mkv), ".mkv")
        self.assertEqual(Wk.raw_suffix({}, None, b"\x00" * 64), ".mp4")
        self.assertEqual(Wk.raw_suffix({"raw_url": "/api/montaj/files/17.raw.1763030000.9f2c4a1b7e30d685.abc"}, None, b""), ".mp4")

    def test_multipart_stream(self):
        tmp = fixtures.SCRATCH / "mp_test.bin"
        tmp.write_bytes(os.urandom(3 * Wk.CHUNK + 17))
        mp = Wk.Multipart({"video": (tmp, "video/mp4"), "report": (tmp, "application/json")})
        data = b""
        while True:
            b = mp.read(65536)
            if not b:
                break
            data += b
        self.assertEqual(len(data), mp.length)
        self.assertTrue(data.endswith(f"--{mp.boundary}--\r\n".encode()))


if __name__ == "__main__":
    unittest.main()
