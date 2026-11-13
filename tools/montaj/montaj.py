#!/usr/bin/env python3
"""ISFT studiyasi uchun AI video-montaj dasturi.

CLI:
  ~/.local/montaj-venv/bin/python tools/montaj/montaj.py --input raw.mp4 [--slides deck.pdf] [--webcam cam.mp4] \
      --template maruza_slayd --subject "…" --code L3 --title "…" --teacher "…" \
      --plan "1. …" --plan "2. …" --out DIR [--model large-v3] [--dry-run] [--no-intro]

Worker (ISFT Core navbatidan ishlarni oladi):
  ISFT_CORE_WORKER_TOKEN=… montaj.py --worker --api https://core.example.uz

Batafsil: docs/montaj.md
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import run as R  # noqa: E402
from pipeline.common import MontajError  # noqa: E402
from pipeline.edl import EdlParams  # noqa: E402
from pipeline.graphics import Lesson  # noqa: E402


def setup_logging(verbose: bool = False, logfile: Path | None = None):
    handlers = [logging.StreamHandler(sys.stderr)]
    if logfile:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(logfile, encoding="utf-8"))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname).1s %(message)s", datefmt="%H:%M:%S", handlers=handlers,
                        force=True)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="montaj", description="ISFT ma'ruza videosi uchun avtomatik montaj")
    p.add_argument("--input", type=Path, help="xom studiya yozuvi (mp4/mov/mkv)")
    p.add_argument("--slides", type=Path, help="ma'ruza slaydlari (PDF)")
    p.add_argument("--webcam", type=Path, help="ekran shabloni uchun alohida veb-kamera fayli")
    p.add_argument("--webcam-offset", type=float, default=0.0,
                   help="veb-kamera ekran yozuvidan necha soniya kech boshlangan (manfiy — oldin)")
    p.add_argument("--template", default="maruza_slayd", choices=R.TEMPLATES)
    p.add_argument("--subject", default="", help="fan nomi")
    p.add_argument("--code", default="", help="dars kodi, masalan L3")
    p.add_argument("--title", default="", help="mavzu nomi")
    p.add_argument("--teacher", default="", help="o'qituvchi F.I.Sh.")
    p.add_argument("--plan", action="append", default=[], help="reja bandi (bir necha marta)")
    p.add_argument("--logo", type=Path, help="logo PNG (standart: static/brand/logo.png)")
    p.add_argument("--out", type=Path, help="natija papkasi")
    p.add_argument("--model", default="large-v3", help="faster-whisper modeli (standart large-v3)")
    p.add_argument("--device", default="auto", choices=["auto", "mps", "cpu"],
                   help="whisper qurilmasi: auto (Apple GPU, bo'lmasa CPU)")
    p.add_argument("--language", default="uz", help="nutq tili: uz (standart, aniq rus/ingliz bo'lsa avto), ru, en, auto")
    p.add_argument("--multilingual", action="store_true", help="aralash uz/ru nutq uchun har segmentda til aniqlash")
    p.add_argument("--dry-run", action="store_true", help="faqat EDL + hisobot (render yo'q)")
    p.add_argument("--no-intro", action="store_true")
    p.add_argument("--no-outro", action="store_true")
    p.add_argument("--burn-captions", action="store_true", help="subtitrlarni videoga yozish")
    p.add_argument("--encoder", default="auto", choices=["auto", "h264_videotoolbox", "libx264"])
    p.add_argument("--max-pause", type=float, default=1.0, help="bundan uzun sukunat kesiladi (s)")
    p.add_argument("--keep-pad", type=float, default=0.4, help="kesilgan pauza chetida qoldiriladigan vaqt (s)")
    p.add_argument("--conservative", action="store_true", help="faqat sukunatlarni kesish")
    p.add_argument("--no-cache", action="store_true", help="transkripsiya keshini ishlatmaslik")
    p.add_argument("--keep-work", action="store_true", help="oraliq fayllarni natija papkasida qoldirish")
    p.add_argument("-v", "--verbose", action="store_true")
    # worker
    p.add_argument("--worker", action="store_true", help="ISFT Core navbatidan ishlarni olish rejimi")
    p.add_argument("--api", help="ISFT Core manzili, masalan https://core.isft.uz")
    p.add_argument("--work-dir", type=Path, help="worker vaqtinchalik papkasi")
    p.add_argument("--once", action="store_true", help="worker: bitta ishni bajarib chiqish")
    p.add_argument("--poll-min", type=float, default=5.0)
    p.add_argument("--poll-max", type=float, default=60.0)
    return p


def config_from_args(a) -> R.Config:
    lesson = Lesson(subject=a.subject, code=a.code, title=a.title, teacher=a.teacher, plan=tuple(a.plan))
    return R.Config(input=a.input, out=a.out, template=a.template, lesson=lesson, slides=a.slides, webcam=a.webcam,
                    webcam_offset=a.webcam_offset, logo=a.logo, model=a.model, device=a.device, language=a.language,
                    multilingual=a.multilingual, dry_run=a.dry_run, intro=not a.no_intro, outro=not a.no_outro,
                    burn_captions=a.burn_captions, encoder=a.encoder,
                    edl=EdlParams(max_pause=a.max_pause, keep_pad=a.keep_pad, conservative=a.conservative),
                    use_cache=not a.no_cache, keep_work=a.keep_work)


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.worker:
        setup_logging(a.verbose)
        from pipeline import worker
        if not a.api:
            print("--api kerak", file=sys.stderr)
            return 2
        return worker.main(a)
    if not a.input or not a.out:
        print("--input va --out kerak (yoki --worker)", file=sys.stderr)
        return 2
    setup_logging(a.verbose, a.out / "montaj.log")
    try:
        rep = R.run(config_from_args(a), progress_cb=lambda st, pct, msg: logging.getLogger("montaj").debug(
            "progress %s %.0f%% %s", st, pct, msg))
    except MontajError as e:
        logging.getLogger("montaj").error("XATO: %s", e)
        return 1
    print(f"Tayyor: {a.out}  ({rep['duration_in']:.0f} s → {rep['duration_out']:.0f} s, "
          f"{len(rep['cuts'])} kesish, {len(rep['warnings'])} ogohlantirish)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
