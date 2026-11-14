"""Birlik sinovlari: to'ldiruvchilar, dubllar, sukunat birlashtirish, so'z ichida kesmaslik, slayd moslash,
VTT qayta vaqtlash, boblar, hisobot sxemasi.

Ishga tushirish: ~/.local/montaj-venv/bin/python -m unittest discover -s tools/montaj/tests -p 'test_unit.py' -v
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import captions, chapters, edl as E, slides as S, graphics as G  # noqa: E402
from pipeline.run import TEMPLATES  # noqa: E402
from pipeline.common import FPS, uz_typography, fmt_ts  # noqa: E402


def mk_words(spec: list[tuple[str, float, float]]) -> list[dict]:
    return [{"word": w, "start": a, "end": b, "prob": 0.95} for w, a, b in spec]


def sentence(text: str, t0: float, wdur: float = 0.3, gap: float = 0.05):
    out, t = [], t0
    for w in text.split():
        out.append((w, round(t, 3), round(t + wdur, 3)))
        t += wdur + gap
    return out, t - gap


def script(parts: list) -> tuple[list[dict], float]:
    """parts: [("matn", pauza_keyin), ...] → so'zlar, oxirgi vaqt."""
    spec, t = [], 0.5
    for text, pause in parts:
        ws, t = sentence(text, t)
        spec += ws
        t += pause
    return mk_words(spec), t


def overlaps(cuts, a, b, reason=None):
    return any(c["start"] < b and c["end"] > a and (reason is None or c["reason"] == reason) for c in cuts)


class FillerTests(unittest.TestCase):
    def test_filler_words(self):
        for w in ["ee", "Eee...", "hmm", "Mmm,", "um", "uh", "э", "ээ", "Ну", "ммм", "eeh"]:
            self.assertTrue(E.is_filler(w), w)
        for w in ["bu", "endi", "model", "a", "the", "erkin", "hamma", "uchun", "мы"]:
            self.assertFalse(E.is_filler(w), w)

    def test_filler_only_segment_cut(self):
        words, end = script([("Bugun biz relyatsion modelni o'rganamiz.", 0.5), ("Eee... hmm...", 0.5),
                             ("Jadval qatorlar va ustunlardan iborat.", 0.5)])
        res = E.build_edl(words, [], end + 1)
        f = [w for w in words if E.is_filler(w["word"])]
        self.assertTrue(overlaps(res["cuts"], f[0]["start"], f[-1]["end"], "filler"), res["cuts"])
        # kesish to'ldiruvchilarni to'liq qamrab oladi
        c = next(c for c in res["cuts"] if c["reason"] == "filler")
        self.assertLessEqual(c["start"], f[0]["start"])
        self.assertGreaterEqual(c["end"], f[-1]["end"])

    def test_attached_filler_not_cut(self):
        # pauzasiz yopishgan "ee" — kesilmaydi (toza kesish imkonsiz)
        words = mk_words([("bu", 0.5, 0.7), ("ee", 0.72, 0.9), ("model", 0.92, 1.3)])
        res = E.build_edl(words, [], 2.0)
        self.assertFalse(overlaps(res["cuts"], 0.72, 0.9, "filler"))


class RetakeTests(unittest.TestCase):
    def test_full_duplicate_keeps_last(self):
        words, end = script([("Relyatsion model jadvallardan iborat.", 0.6),
                             ("Relyatsion model jadvallardan iborat bo'ladi.", 0.6),
                             ("Keyingi mavzu SQL.", 0.5)])
        res = E.build_edl(words, [], end)
        first = words[0]["start"], words[3]["end"]
        second = words[4]["start"], words[8]["end"]
        self.assertTrue(overlaps(res["cuts"], *first, "retake"))
        self.assertFalse(overlaps(res["cuts"], *second))

    def test_false_start_prefix(self):
        words, end = script([("Tashqi kalit bir jadvalni", 1.0),
                             ("Tashqi kalit bir jadvalni boshqa jadval bilan bog'laydi.", 0.6)])
        res = E.build_edl(words, [], end)
        self.assertTrue(overlaps(res["cuts"], words[0]["start"], words[3]["end"], "retake"))
        self.assertFalse(overlaps(res["cuts"], words[4]["start"], words[-1]["end"]))

    def test_similar_but_different_sentences_kept(self):
        words, end = script([("Birlamchi kalit takrorlanmas bo'lishi kerak.", 0.6),
                             ("Tashqi kalit esa boshqa jadvalga ishora qiladi.", 0.6)])
        res = E.build_edl(words, [], end)
        self.assertFalse(any(c["reason"] == "retake" for c in res["cuts"]))

    def test_chain_of_retakes(self):
        words, end = script([("Indeks qidiruvni tezlashtiradi.", 0.6), ("Indeks qidiruvni tezlashtiradi.", 0.6),
                             ("Indeks qidiruvni ancha tezlashtiradi.", 0.6)])
        res = E.build_edl(words, [], end)
        last = words[6]["start"], words[-1]["end"]
        self.assertFalse(overlaps(res["cuts"], *last))
        self.assertTrue(overlaps(res["cuts"], words[0]["start"], words[2]["end"]))
        self.assertTrue(overlaps(res["cuts"], words[3]["start"], words[5]["end"]))

    def test_explicit_cue_standalone(self):
        words, end = script([("Bugun SQL haqida gaplashamiz.", 0.5), ("Indeks bu jadvalning", 0.7),
                             ("Qaytadan.", 0.7), ("Indeks bu qidiruvni tezlashtiruvchi tuzilma.", 0.5)])
        res = E.build_edl(words, [], end)
        idx = [w["word"] for w in words].index("Qaytadan.")
        self.assertTrue(overlaps(res["cuts"], words[4]["start"], words[idx]["end"], "retake_cue"))
        self.assertFalse(overlaps(res["cuts"], words[0]["start"], words[3]["end"]))  # oldingi to'liq gap qoladi
        self.assertFalse(overlaps(res["cuts"], words[idx + 1]["start"], words[-1]["end"]))

    def test_cue_glued_to_sentence(self):
        # whisper signalni oldingi gapga yopishtirib yuborgan holat
        words, end = script([("The JOIN operation is the slowest part of STOP.", 0.4),
                             ("Again, the JOIN operation combines rows from two tables.", 0.5)])
        res = E.build_edl(words, [], end)
        again = [w["word"] for w in words].index("Again,")
        self.assertTrue(overlaps(res["cuts"], words[0]["start"], words[again]["end"], "retake_cue"))
        self.assertFalse(overlaps(res["cuts"], words[again + 1]["start"], words[-1]["end"]))

    def test_natural_stop_not_cut(self):
        words, end = script([("The process will stop.", 0.4), ("Then we read the next row.", 0.5)])
        res = E.build_edl(words, [], end)
        self.assertFalse(any(c["reason"].startswith("retake") for c in res["cuts"]))

    def test_yana_bir_bor_natural(self):
        words, end = script([("Bu muhim qoida.", 0.4), ("Yana bir bor ta'kidlayman kalit takrorlanmaydi.", 0.5)])
        res = E.build_edl(words, [], end)
        self.assertFalse(any(c["reason"].startswith("retake") for c in res["cuts"]))


class SilenceTests(unittest.TestCase):
    def test_long_silence_cut_with_padding(self):
        words, _ = script([("Birinchi gap.", 3.0), ("Ikkinchi gap.", 0.3)])
        s0 = words[1]["end"]
        s1 = words[2]["start"]
        res = E.build_edl(words, [(s0, s1)], s1 + 1.0)
        c = next(c for c in res["cuts"] if c["start"] > s0 - 0.01 and c["end"] < s1 + 0.01)
        self.assertAlmostEqual(c["start"] - s0, 0.4, delta=1.0 / FPS + 0.01)
        self.assertAlmostEqual(s1 - c["end"], 0.4, delta=1.0 / FPS + 0.01)

    def test_short_silence_kept(self):
        words, _ = script([("Birinchi gap.", 0.8), ("Ikkinchi gap.", 0.3)])
        res = E.build_edl(words, [(words[1]["end"], words[2]["start"])], 5.0)
        self.assertFalse(overlaps(res["cuts"], words[1]["end"] + 0.1, words[2]["start"] - 0.1))

    def test_merge_and_tiny_keep(self):
        cuts = E.merge_cuts([{"start": 1, "end": 2, "reason": "silence"}, {"start": 1.5, "end": 3, "reason": "filler"},
                             {"start": 3.02, "end": 4, "reason": "silence"}])
        self.assertEqual(len(cuts), 1)
        self.assertEqual(cuts[0]["reason"], "filler")
        self.assertEqual((cuts[0]["start"], cuts[0]["end"]), (1, 4))
        # orada so'zsiz 0.3 s bo'lak qolsa — yutib yuboriladi
        words = mk_words([("a1", 0.2, 0.6), ("b2", 6.0, 6.4)])
        res = E.build_edl(words, [(0.8, 3.0), (3.3, 5.6)], 7.0)
        mids = [c for c in res["cuts"] if c["start"] < 3.1 < c["end"]]
        self.assertTrue(mids, res["cuts"])

    def test_conservative_mode_only_silence(self):
        words, end = script([("Indeks qidiruvni tezlashtiradi.", 0.6), ("Indeks qidiruvni tezlashtiradi.", 2.5),
                             ("Eee.", 0.5), ("Oxiri.", 0.2)])
        sil = [(words[5]["end"], words[6]["start"])]
        res = E.build_edl(words, sil, end, E.EdlParams(conservative=True))
        self.assertTrue(all(c["reason"] == "silence" for c in res["cuts"]))
        self.assertTrue(res["cuts"])


class NeverInsideWordTests(unittest.TestCase):
    def test_random_transcripts(self):
        import random
        rnd = random.Random(7)
        vocab = "bu model jadval kalit indeks so'rov ee hmm qator ustun stop qaytadan".split()
        for trial in range(60):
            spec, t = [], rnd.uniform(0, 1)
            for _ in range(rnd.randint(5, 60)):
                d = rnd.uniform(0.08, 0.7)
                spec.append((rnd.choice(vocab) + rnd.choice(["", "", ".", ","]), round(t, 3), round(t + d, 3)))
                t += d + rnd.choice([0.0, 0.01, 0.05, 0.2, 0.6, 1.3, 2.5])
            words = mk_words(spec)
            dur = t + rnd.uniform(0, 3)
            sil = [(words[i]["end"], words[i + 1]["start"]) for i in range(len(words) - 1)
                   if words[i + 1]["start"] - words[i]["end"] > 0.5]
            res = E.build_edl(words, sil, dur)
            for c in res["cuts"]:
                for b in (c["start"], c["end"]):
                    w = E.inside_word(b, words)
                    if w is not None:  # faqat bo'shliqsiz so'zlar chegarasida, 1 kadrdan kam
                        self.assertLess(min(b - w["start"], w["end"] - b), 1.0 / FPS, (trial, c, b, w))
                    self.assertAlmostEqual(b * FPS, round(b * FPS), places=2)  # kadr to'rida
            # saqlangan bo'laklar kesishmaydi va tartibli
            ks = res["keeps"]
            for (a1, b1), (a2, b2) in zip(ks, ks[1:]):
                self.assertLessEqual(b1, a2 + 1e-9)


class TimeMapTests(unittest.TestCase):
    def test_map(self):
        tm = E.TimeMap([(0, 2), (5, 7)], offset=3.9)
        self.assertAlmostEqual(tm.to_out(1), 4.9)
        self.assertIsNone(tm.to_out(3))
        self.assertAlmostEqual(tm.to_out(6), 3.9 + 3)
        self.assertAlmostEqual(tm.to_out_clamped(3), 3.9 + 2)
        self.assertAlmostEqual(tm.main_duration, 4)


class SlideAlignTests(unittest.TestCase):
    PAGES = ["Kirish. Ma'lumotlar bazasi fani haqida umumiy tushuncha",
             "Relyatsion model: jadvallar, qatorlar, ustunlar, birlamchi kalit",
             "SQL so'rovlari: SELECT, WHERE filtrlash, JOIN birlashtirish",
             "Indekslar va unumdorlik: qidiruv tezligi, qo'shimcha xarajat"]

    def units(self, texts, step=8.0):
        return [{"start": i * step, "end": i * step + step - 0.5, "text": t} for i, t in enumerate(texts)]

    def test_monotonic_alignment(self):
        texts = ["Assalomu alaykum, bugun ma'lumotlar bazasi fani bo'yicha umumiy tushuncha beramiz",
                 "Fan haqida qisqacha kirish",
                 "Relyatsion model jadvallardan iborat", "Har jadvalda qatorlar va ustunlar bor",
                 "Birlamchi kalit har qatorni aniqlaydi",
                 "Endi SQL so'rovlariga o'tamiz", "SELECT ma'lumot o'qiydi, WHERE filtrlash qiladi",
                 "JOIN ikki jadvalni birlashtirish uchun", "Indekslar qidiruv tezligini oshiradi",
                 "Lekin indekslar qo'shimcha xarajat va unumdorlik masalasi"]
        spans, warns = S.sync_slides(self.units(texts), self.PAGES, 80.0, min_dwell=6.0)
        seq = [s for _, _, s in spans]
        self.assertEqual(seq, [0, 1, 2, 3], spans)
        self.assertAlmostEqual(spans[1][0], 16 - 0.3, delta=0.01)
        self.assertAlmostEqual(spans[2][0], 40 - 0.3, delta=0.01)
        self.assertEqual(spans[-1][1], 80.0)

    def test_small_backtrack_allowed(self):
        texts = ["Relyatsion model jadvallar", "qatorlar ustunlar birlamchi kalit",
                 "SQL so'rovlari SELECT WHERE", "SELECT WHERE filtrlash JOIN",
                 "relyatsion model jadvallar qatorlar ustunlar birlamchi kalit yana bir bor",
                 "jadvallar qatorlar ustunlar birlamchi kalit eslatma",
                 "SQL JOIN birlashtirish", "SQL so'rovlari WHERE"]
        spans, _ = S.sync_slides(self.units(texts, 10.0), self.PAGES, 80.0, min_dwell=6.0)
        seq = [s for _, _, s in spans]
        self.assertEqual(seq, [1, 2, 1, 2], spans)

    def test_min_dwell(self):
        out = S.enforce_dwell([(0, 10, 0), (10, 12, 1), (12, 30, 2)], 6.0)
        self.assertEqual([s for *_, s in out], [0, 2])
        self.assertEqual(out[-1][1], 30)

    def test_no_text_pdf_evenly(self):
        spans, warns = S.sync_slides(self.units(["a b c"]), ["", "", ""], 30.0)
        self.assertEqual([round(a) for a, _, _ in spans], [0, 10, 20])
        self.assertTrue(warns)

    def test_unrelated_speech_no_slide(self):
        texts = ["ob-havo bugun juda issiq", "futbol o'yini qiziqarli bo'ldi", "kecha konsertga bordik",
                 "do'stlar bilan choy ichdik", "musiqa yoqimli edi", "Relyatsion model jadvallar qatorlar",
                 "ustunlar birlamchi kalit", "birlamchi kalit jadvallar"]
        spans, _ = S.sync_slides(self.units(texts, 10.0), self.PAGES, 80.0, min_dwell=6.0)
        self.assertEqual(spans[0][2], -1, spans)
        self.assertEqual(spans[-1][2], 1)


class CaptionTests(unittest.TestCase):
    def test_retime_after_cuts_and_vtt(self):
        words = mk_words([("Bugun", 1.0, 1.3), ("SQL", 1.35, 1.7), ("o'rganamiz.", 1.75, 2.3),
                          ("kesilgan", 4.0, 4.5),
                          ("Indeks", 10.0, 10.4), ("qidiruvni", 10.45, 11.0), ("tezlashtiradi.", 11.05, 11.8)])
        tm = E.TimeMap([(0.5, 3.0), (9.5, 12.5)], offset=3.9)
        cues = captions.build_cues(words, tm)
        self.assertEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0]["start"], 3.9 + 0.5, places=3)
        self.assertAlmostEqual(cues[1]["start"], 3.9 + 2.5 + 0.5, places=3)
        self.assertNotIn("kesilgan", " ".join(c["text"] for c in cues))
        self.assertIn("oʻrganamiz", cues[0]["lines"][0])
        vtt = captions.to_vtt(cues)
        self.assert_valid_vtt(vtt)

    def test_line_limits(self):
        long = " ".join(["so'z%02d" % i for i in range(80)])
        spec, t = [], 0.0
        for w in long.split():
            spec.append((w, t, t + 0.25))
            t += 0.3
        cues = captions.build_cues(mk_words(spec), E.TimeMap([(0, t + 1)]))
        for c in cues:
            self.assertLessEqual(len(c["lines"]), 2)
            for l in c["lines"]:
                self.assertLessEqual(len(l), 42)
            self.assertLessEqual(c["end"] - c["start"], 6.5)
        self.assert_valid_vtt(captions.to_vtt(cues))

    def assert_valid_vtt(self, vtt: str):
        self.assertTrue(vtt.startswith("WEBVTT\n"))
        prev = -1.0
        for m in re.finditer(r"(\d\d):(\d\d):(\d\d)\.(\d{3}) --> (\d\d):(\d\d):(\d\d)\.(\d{3})", vtt):
            g = [int(x) for x in m.groups()]
            a = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            b = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            self.assertLess(a, b)
            self.assertGreaterEqual(a, prev)
            prev = b
        self.assertGreater(prev, 0)

    def test_ass(self):
        cues = [{"start": 5.0, "end": 7.0, "lines": ["Salom", "dunyo"]}]
        ass = captions.to_ass(cues, offset=3.9)
        self.assertIn("Dialogue: 0,0:00:01.10,0:00:03.10,Default,,0,0,0,,Salom\\Ndunyo", ass)


class ChapterTests(unittest.TestCase):
    def test_chapters_from_slides(self):
        pages = ["Kirish", "Relyatsion model\njadvallar", "SQL so'rovlari\nSELECT", "Indekslar"]
        spans = [(0, 12, 0), (12, 40, 1), (40, 70, 2), (70, 100, 3)]
        plan = ["1. Relyatsion model", "2. SQL so'rovlari", "3. Indekslar"]
        times = chapters.find_chapter_times(plan, 100, [], spans, pages)
        self.assertEqual(times, [12, 40, 70])
        chs = chapters.build_chapters(plan, times, 3.9, 100)
        self.assertEqual(chs[0], {"start": 0.0, "title": "Kirish"})
        self.assertEqual([c["start"] for c in chs[1:]], [15.9, 43.9, 73.9])

    def test_chapters_from_transcript_and_interpolation(self):
        units = [{"start": i * 10.0, "end": i * 10 + 9, "text": t} for i, t in enumerate(
            ["salom", "bugun relyatsion bazalar", "relyatsion model haqida", "jadval", "jadval", "jadval", "jadval",
             "indekslar va unumdorlik", "indeks", "xulosa"])]
        plan = ["Relyatsion model", "Normalizatsiya qoidalari", "Indekslar va unumdorlik"]
        times = chapters.find_chapter_times(plan, 100, units)
        self.assertEqual(times[0], 20.0)
        self.assertEqual(times[2], 70.0)
        self.assertAlmostEqual(times[1], 45.0)  # interpolyatsiya

    def test_overview_sentence_not_used(self):
        units = [{"start": i * 10.0, "end": i * 10 + 9, "text": t} for i, t in enumerate(
            ["bugun relyatsion model, SQL so'rovlari va indekslar haqida gaplashamiz", "salom",
             "avval relyatsion model haqida", "jadval", "endi SQL so'rovlari", "select", "nihoyat indekslar", "x"])]
        plan = ["Relyatsion model", "SQL so'rovlari", "Indekslar"]
        self.assertEqual(chapters.find_chapter_times(plan, 80, units), [20.0, 40.0, 60.0])

    def test_min_gap_and_first_at_zero(self):
        chs = chapters.build_chapters(["A", "B"], [1.0, 3.0], 0.0, 200)
        self.assertEqual(chs[0], {"start": 0.0, "title": "A"})
        self.assertEqual(chs[1]["start"], 10.0)

    def test_youtube_format(self):
        self.assertEqual(fmt_ts(83.4), "01:23")
        self.assertEqual(fmt_ts(3723), "1:02:03")


class WatermarkLayoutTests(unittest.TestCase):
    """Suv belgisi (logo) hech bir shablonda o'qituvchi/kamera sohasini (ekran — PiP) yopmasligi kerak."""

    SIZES = [(88, 66), (40, 66), (300, 66), (700, 66)]   # standart logo, tor, keng va juda keng logolar (balandlik — WATERMARK_H)

    def test_no_overlap_all_templates(self):
        self.assertEqual(set(TEMPLATES), {"maruza_slayd", "faqat_oqituvchi", "ekran"})
        for tpl in TEMPLATES:
            for slide_on in (False, True):
                for size in self.SIZES:
                    x, y = G.watermark_xy(tpl, size, slide_on)
                    r = (x, y, x + size[0], y + size[1])
                    with self.subTest(tpl=tpl, slide_on=slide_on, size=size):
                        self.assertTrue(0 <= r[0] and r[2] <= G.W and 0 <= r[1] and r[3] <= G.H - G.Geo.BAR_H, r)
                        for cam in G.camera_rects(tpl, slide_on):
                            self.assertFalse(G.rects_overlap(r, cam, G.WM_GAP), f"{tpl}: logo {r} ↔ kamera {cam}")

    def test_ekran_pip_opposite_corner(self):
        x, y = G.watermark_xy("ekran", G.watermark().size)
        self.assertFalse(G.rects_overlap((x, y, x + 88, y + 66), G.Geo.PIP))
        self.assertLess(x, G.Geo.PIP[0]); self.assertLess(y, G.Geo.PIP[1])   # PiP past-o'ngda → logo yuqori-chapda
        self.assertEqual(G.camera_rects("ekran"), [G.Geo.PIP])

    def test_rects_overlap(self):
        self.assertTrue(G.rects_overlap((0, 0, 10, 10), (5, 5, 15, 15)))
        self.assertFalse(G.rects_overlap((0, 0, 10, 10), (10, 0, 20, 10)))
        self.assertTrue(G.rects_overlap((0, 0, 10, 10), (20, 0, 30, 10), gap=11))


class ReportSchemaTests(unittest.TestCase):
    def test_validator(self):
        rep = {"duration_in": 10.0, "duration_out": 8.0, "cuts": [{"start": 1.0, "end": 2.0, "reason": "silence"}],
               "chapters": [{"start": 0.0, "title": "Kirish"}], "slide_changes": [{"t": 3.9, "slide": 1}],
               "warnings": [], "timings": {"jami": 1.0}}
        validate_report(self, rep)

    def test_uz_typography(self):
        self.assertEqual(uz_typography("O'zbekiston ta'lim g'oya"), "Oʻzbekiston ta’lim gʻoya")


def validate_report(tc: unittest.TestCase, rep: dict):
    tc.assertEqual(list(rep.keys()), ["duration_in", "duration_out", "cuts", "chapters", "slide_changes",
                                      "warnings", "timings"])
    tc.assertIsInstance(rep["duration_in"], (int, float))
    tc.assertIsInstance(rep["duration_out"], (int, float))
    for c in rep["cuts"]:
        tc.assertEqual(set(c), {"start", "end", "reason"})
        tc.assertLess(c["start"], c["end"])
        tc.assertIn(c["reason"], E.REASON_PRIORITY)
    for c in rep["chapters"]:
        tc.assertEqual(set(c), {"start", "title"})
    tc.assertEqual(rep["chapters"][0]["start"], 0.0)
    for s in rep["slide_changes"]:
        tc.assertEqual(set(s), {"t", "slide"})
        tc.assertTrue(s["slide"] is None or (isinstance(s["slide"], int) and s["slide"] >= 1))
    ts = [s["t"] for s in rep["slide_changes"]]
    tc.assertEqual(ts, sorted(ts))
    tc.assertIsInstance(rep["warnings"], list)
    tc.assertIsInstance(rep["timings"], dict)


if __name__ == "__main__":
    unittest.main()
