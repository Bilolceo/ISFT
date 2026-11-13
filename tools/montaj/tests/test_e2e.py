"""To'liq sinov: sintetik ma'ruza (say + pauzalar + to'ldiruvchi + dubl + signal) uchala shablonda.

Ishga tushirish (≈2–3 daqiqa birinchi marta, keyin transkripsiya keshdan):
  ~/.local/montaj-venv/bin/python -m unittest discover -s tools/montaj/tests -p 'test_e2e.py' -v
Kadrlar (ko'zdan kechirish uchun): SCRATCH/e2e/<shablon>/frames/*.jpg
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from pipeline import run as R, probe as P, edl as E, compose  # noqa: E402
from pipeline.common import FFMPEG  # noqa: E402
from pipeline.edl import EdlParams  # noqa: E402
from pipeline.graphics import Lesson  # noqa: E402
from test_unit import validate_report  # noqa: E402

OUT = fixtures.SCRATCH / "e2e"
LESSON = Lesson(subject="Ma'lumotlar bazasi", code="L3", title="Relyatsion model va SQL so'rovlari",
                teacher="Karimova Dilnoza O'tkirovna", plan=tuple(fixtures.PLAN))


def frame(video: Path, t: float, out: Path, scale: str = "1280:-1"):
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    "-vf", f"scale={scale}", str(out)], check=True)
    return out


def gray_small(video: Path, t: float):
    import numpy as np
    r = subprocess.run([FFMPEG, "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=192:108,format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(108, 192).astype(float)


def stream_durations(path: Path) -> dict:
    import av
    out = {}
    with av.open(str(path)) as c:
        for s in c.streams:
            if s.duration:
                out[s.type] = float(s.duration * s.time_base)
    return out


class E2E(unittest.TestCase):
    meta: dict = {}
    results: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.meta = fixtures.make_all()
        OUT.mkdir(parents=True, exist_ok=True)
        m = cls.meta
        jobs = {
            "maruza_slayd": dict(input=Path(m["teacher"]), slides=Path(m["slides"])),
            "faqat_oqituvchi": dict(input=Path(m["teacher"])),
            "ekran": dict(input=Path(m.get("screen") or m["teacher"]), webcam=Path(m["teacher"])),
        }
        for tpl, kw in jobs.items():
            out = OUT / tpl
            cfg = R.Config(out=out, template=tpl, lesson=LESSON, **kw)
            rep = R.run(cfg)
            cls.results[tpl] = (out, rep)

    # ------------------------------------------------------------------ yordamchi
    def covered(self, cuts, a, b) -> float:
        tot = sum(max(0.0, min(b, c["end"]) - max(a, c["start"])) for c in cuts)
        return tot / max(1e-6, b - a)

    def test_outputs_and_schema(self):
        for tpl, (out, rep) in self.results.items():
            with self.subTest(tpl=tpl):
                for f in ["final.mp4", "captions.vtt", "thumbnail.jpg", "report.json", "youtube_chapters.txt"]:
                    self.assertTrue((out / f).exists() and (out / f).stat().st_size > 0, f)
                validate_report(self, json.loads((out / "report.json").read_text()))
                info = P.probe(out / "final.mp4")
                self.assertEqual((info.width, info.height), (1920, 1080))
                self.assertAlmostEqual(info.fps, 30.0, delta=0.01)
                self.assertGreater(rep["duration_out"], 0.4 * rep["duration_in"])
                self.assertLess(rep["duration_out"], rep["duration_in"] + 8)
                self.assertAlmostEqual(info.duration, rep["duration_out"], delta=0.3)
                d = stream_durations(out / "final.mp4")
                self.assertAlmostEqual(d["video"], d["audio"], delta=0.12, msg=d)  # A/V bir xil uzunlikda
                yt = (out / "youtube_chapters.txt").read_text().splitlines()
                self.assertTrue(yt[0].startswith("00:00 "))

    def test_cuts_match_inserted_defects(self):
        tl = self.meta["timeline"]
        for tpl, (out, rep) in self.results.items():
            cuts = rep["cuts"]
            with self.subTest(tpl=tpl):
                for seg in tl:
                    a, b = seg["start"], seg["end"]
                    cov = self.covered(cuts, a, b)
                    if seg["kind"] == "sil" and b - a >= 2.0:
                        self.assertGreater(cov, 0.45, f"uzun pauza kesilmadi: {seg}")
                    elif seg["kind"] in ("filler", "retake_a", "cue", "cue_prev"):
                        self.assertGreater(cov, 0.8, f"kesilmadi: {seg} cov={cov:.2f}")
                    elif seg["kind"] == "say":
                        self.assertLess(cov, 0.05, f"kerakli nutq kesildi: {seg} cov={cov:.2f}")
                reasons = {c["reason"] for c in cuts}
                self.assertTrue({"silence", "retake", "retake_cue"} <= reasons, reasons)
                self.assertTrue({"filler", "noise"} & reasons, reasons)

    def test_slide_changes(self):
        out, rep = self.results["maruza_slayd"]
        sc = rep["slide_changes"]
        self.assertEqual([s["slide"] for s in sc], [1, 2, 3, 4])
        ts = [s["t"] for s in sc]
        self.assertEqual(ts, sorted(ts))
        # slayd 2 "relational model" haqidagi gapdan oldin, slayd 4 "indexes" gapi atrofida
        edl = json.loads((out / "edl.json").read_text())
        tm = E.TimeMap([tuple(k) for k in edl["keeps"]], edl["main_offset"])
        tl = {s["text"]: s for s in self.meta["timeline"]}
        t_rel = tm.to_out_clamped(tl["First, let us talk about the relational model."]["start"])
        t_idx = tm.to_out_clamped(tl["Finally, we will discuss indexes and performance."]["start"])
        self.assertLess(abs(ts[1] - t_rel), 4.0, (ts, t_rel))
        self.assertLess(abs(ts[3] - t_idx), 4.0, (ts, t_idx))
        self.assertEqual(rep["chapters"][1]["title"], "Relational model")

    def test_chapters(self):
        for tpl, (out, rep) in self.results.items():
            with self.subTest(tpl=tpl):
                ch = rep["chapters"]
                titles = [c["title"] for c in ch]
                self.assertEqual(titles[-3:], ["Relational model", "SQL queries", "Indexes and performance"])
                st = [c["start"] for c in ch]
                self.assertEqual(st[0], 0.0)
                for a, b in zip(st, st[1:]):
                    self.assertGreaterEqual(b - a, 10.0 - 1e-6)

    def test_captions_vtt(self):
        for tpl, (out, rep) in self.results.items():
            with self.subTest(tpl=tpl):
                vtt = (out / "captions.vtt").read_text()
                self.assertTrue(vtt.startswith("WEBVTT"))
                blocks = [b for b in vtt.strip().split("\n\n")[1:] if b.strip()]
                self.assertGreater(len(blocks), 10)
                prev = 0.0
                for b in blocks:
                    lines = b.splitlines()
                    m = re.match(r"(\d\d):(\d\d):(\d\d\.\d{3}) --> (\d\d):(\d\d):(\d\d\.\d{3})", lines[1])
                    self.assertIsNotNone(m, b)
                    a = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
                    e = int(m[4]) * 3600 + int(m[5]) * 60 + float(m[6])
                    self.assertLess(a, e)
                    self.assertGreaterEqual(a, prev - 1e-3)
                    self.assertLessEqual(e, rep["duration_out"] + 0.01)
                    prev = e
                    self.assertLessEqual(len(lines) - 2, 2)
                    for ln in lines[2:]:
                        self.assertLessEqual(len(ln), 42)
                text = " ".join(vtt.split())
                self.assertNotIn("slowest", text)  # signal bilan kesilgan gap subtitrda yo'q
                self.assertEqual(text.count("Remember to practice"), 1)  # dublning faqat biri

    def test_video_mapping_follows_edl(self):
        """faqat_oqituvchi: chiqishdagi kadr xom videoning EDL bo'yicha mos vaqtidagi kadriga o'xshash."""
        out, rep = self.results["faqat_oqituvchi"]
        edl = json.loads((out / "edl.json").read_text())
        keeps = [tuple(k) for k in edl["keeps"]]
        off = edl["main_offset"]
        tm = E.TimeMap(keeps, off)
        raw = Path(self.meta["teacher"])
        checked = 0
        for a, b in keeps:
            if b - a < 3:
                continue
            t_in = a + (b - a) / 2
            t_out = tm.to_out(t_in)
            fo = gray_small(out / "final.mp4", t_out)[30:100, 40:150]  # markaz (siluet), yozuvlardan tashqari
            d_ok = abs(fo - gray_small(raw, t_in)[30:100, 40:150]).mean()
            d_bad = min(abs(fo - gray_small(raw, t_in + dt)[30:100, 40:150]).mean() for dt in (-2.0, 2.0))
            self.assertLess(d_ok, d_bad, (t_in, t_out, d_ok, d_bad))
            checked += 1
        self.assertGreaterEqual(checked, 3)

    def test_review_frames(self):
        """Dizaynni ko'zdan kechirish uchun kadrlar: intro, lower-third, slayd, bob banneri, outro."""
        for tpl, (out, rep) in self.results.items():
            fr = out / "frames"
            fr.mkdir(exist_ok=True)
            ch = rep["chapters"]
            pts = {"intro": 2.5, "lower_third": 6.5, "mid": rep["duration_out"] * 0.55,
                   "banner": ch[2]["start"] + 1.2 if len(ch) > 2 else 20, "outro": rep["duration_out"] - 1.5}
            for name, t in pts.items():
                p = frame(out / "final.mp4", t, fr / f"{name}.jpg")
                self.assertTrue(p.exists())


class DryRunAndGuards(unittest.TestCase):
    def test_dry_run_and_low_confidence(self):
        m = fixtures.make_all()
        out = OUT / "dry_lowconf"
        cfg = R.Config(input=Path(m["teacher"]), out=out, template="maruza_slayd", slides=Path(m["slides"]),
                       lesson=LESSON, dry_run=True, min_confidence=1.01)  # ishonch chegarasi sun'iy oshirildi
        rep = R.run(cfg)
        self.assertFalse((out / "final.mp4").exists())
        validate_report(self, rep)
        self.assertIn(R.LOW_CONF_WARNING, rep["warnings"])
        self.assertTrue(rep["cuts"])
        self.assertTrue(all(c["reason"] == "silence" for c in rep["cuts"]))

    def test_short_output_warning(self):
        self.assertEqual(R.quality_warnings(100, 39.9), [R.SHORT_WARNING])
        self.assertEqual(R.quality_warnings(100, 40.0), [])


if __name__ == "__main__":
    unittest.main()
