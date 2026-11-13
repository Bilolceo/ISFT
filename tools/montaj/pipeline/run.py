"""Butun quvur (pipeline): 1–9 qadamlar ketma-ketligi, vaqt o'lchovlari, ogohlantirishlar, natija fayllari."""
from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import asr, audio, captions, chapters, compose, edl as E, graphics as G, probe as P, slides as S
from .common import (FPS, MontajError, Timings, log, write_json, fmt_ts, CancelToken, NO_CANCEL)

TEMPLATES = ("maruza_slayd", "faqat_oqituvchi", "ekran")
LOW_CONF_WARNING = "Nutq aniqligi past — operator tekshirsin"
SHORT_WARNING = "Chiqish videosi kirishning 40% idan qisqa — kesishlarni operator tekshirsin"

# (bosqich, boshlanish %, tugash %)
STAGES = {"tayyorlash": (0, 3), "audio": (3, 8), "nutq": (8, 45), "tahrir": (45, 47), "slayd": (47, 50),
          "render": (50, 97), "yakun": (97, 100)}


@dataclass
class Config:
    input: Path
    out: Path
    template: str = "maruza_slayd"
    lesson: G.Lesson = field(default_factory=G.Lesson)
    slides: Path | None = None
    webcam: Path | None = None
    webcam_offset: float = 0.0
    logo: Path | None = None
    model: str = "large-v3"
    device: str = "auto"
    language: str = "uz"
    multilingual: bool = False
    dry_run: bool = False
    intro: bool = True
    outro: bool = True
    burn_captions: bool = False
    encoder: str = "auto"
    min_confidence: float = 0.55
    edl: E.EdlParams = field(default_factory=E.EdlParams)
    use_cache: bool = True
    keep_work: bool = False
    min_slide_dwell: float = 6.0


class Progress:
    def __init__(self, cb=None):
        self.cb = cb

    def __call__(self, stage: str, frac: float = 0.0, msg: str = ""):
        if not self.cb:
            return
        a, b = STAGES.get(stage, (0, 100))
        self.cb(stage, round(a + (b - a) * max(0.0, min(1.0, frac)), 1), msg)


def quality_warnings(duration_in: float, main_duration: float) -> list[str]:
    """Sifat nazorati: kesishdan keyingi asosiy qism kirishning 40% idan qisqa bo'lsa — ogohlantirish."""
    return [SHORT_WARNING] if main_duration < 0.4 * duration_in else []


def asr_prompt(lesson: G.Lesson, page_texts: list[str]) -> str:
    parts = [lesson.subject, lesson.title] + [chapters.clean_plan_item(p) for p in lesson.plan]
    if page_texts:
        parts += [S.page_heading(t) for t in page_texts[:12]]
    s = ". ".join(p for p in parts if p)
    return s[:600]


def run(cfg: Config, progress_cb=None, cancel: CancelToken = NO_CANCEL) -> dict:
    if cfg.template not in TEMPLATES:
        raise MontajError(f"Noma'lum shablon: {cfg.template} (mavjud: {', '.join(TEMPLATES)})")
    t_start = time.perf_counter()
    tm = Timings()
    prog = Progress(progress_cb)
    warnings: list[str] = []
    out = Path(cfg.out)
    out.mkdir(parents=True, exist_ok=True)
    # oraliq fayllar doim tizim temp'ida (yo'lda apostrof bo'lmasin — ffmpeg filtr yo'llari uchun)
    work = Path(tempfile.mkdtemp(prefix="montaj_"))
    lesson = cfg.lesson.norm()
    try:
        # 1) tekshirish va tahlil nusxasi
        prog("tayyorlash", 0, "Fayl tekshirilmoqda")
        with tm.step("1_tekshirish"):
            raw = P.probe(cfg.input)
            if not raw.has_video:
                raise MontajError("Kirish faylida video yo'q")
            cam = P.probe(cfg.webcam) if cfg.webcam else None
            audio_src = raw
            if not raw.has_audio:
                if cam and cam.has_audio:
                    audio_src = cam
                    warnings.append("Asosiy faylda audio yo'q — veb-kamera audiosi ishlatildi")
                else:
                    raise MontajError("Audio topilmadi")
            an_wav = P.extract_analysis_audio(audio_src, work / "analysis.wav", cancel)
        cancel.check()

        # 2) audio tozalash
        prog("audio", 0, "Audio tozalanmoqda")
        with tm.step("2_audio"):
            clean_wav = work / "clean.wav"
            audio.clean_audio(an_wav, clean_wav, cancel)
            silences = audio.detect_silences(clean_wav, cancel=cancel)
        prog("audio", 1)

        page_texts: list[str] = []
        if cfg.slides:
            page_texts = S.read_pdf(cfg.slides)

        # 3) nutqni tanish
        prog("nutq", 0, "Nutq matnga aylantirilmoqda")
        with tm.step("3_nutq"):
            tr = asr.transcribe(clean_wav, model=cfg.model, language=cfg.language,
                                prompt=asr_prompt(lesson, page_texts), use_cache=cfg.use_cache,
                                on_progress=lambda f: prog("nutq", f), cancel=cancel, multilingual=cfg.multilingual,
                                device=cfg.device)
        write_json(out / "transcript.json", tr)
        words = E.refine_words(asr.all_words(tr), audio.rms_envelope(clean_wav, 0.02), 0.02)
        conf = tr.get("confidence", 0.0)
        log.info("Transkripsiya: %d so'z, til %s, ishonch %.2f", len(words), tr.get("language"), conf)
        params = E.EdlParams(**vars(cfg.edl))
        if conf < cfg.min_confidence or len(words) < 3:
            params.conservative = True
            warnings.append(LOW_CONF_WARNING)

        # 4) EDL
        prog("tahrir", 0, "Kesishlar hisoblanmoqda")
        with tm.step("4_edl"):
            # eng qisqa oqim bo'yicha (konteyner davomiyligi oqimlardan uzun bo'lishi mumkin)
            dur_edl = min(d for d in (raw.duration, raw.video_duration or 1e12, audio.wav_duration(clean_wav)) if d)
            edl = E.build_edl(words, silences, dur_edl, params)
        keeps = edl["keeps"]
        rj = compose.RenderJob(template=cfg.template, raw=raw, clean_wav=clean_wav, keeps=keeps, work=work,
                               out=out / "final.mp4", lesson=lesson, logo=cfg.logo, webcam=cam,
                               webcam_offset=cfg.webcam_offset, intro=cfg.intro, outro=cfg.outro,
                               encoder=cfg.encoder)
        T = rj.main_duration
        tmap_main = E.TimeMap(keeps, 0.0)
        tmap_out = E.TimeMap(keeps, rj.main_offset)
        warnings += quality_warnings(raw.duration, T)
        reasons = {}
        for c in edl["cuts"]:
            reasons[c["reason"]] = reasons.get(c["reason"], 0) + 1
        log.info("EDL: %d kesish %s, %.1f s → %.1f s", len(edl["cuts"]), reasons, raw.duration, T)

        # asosiy qism vaqtidagi gaplar (slayd va bob moslash uchun)
        kept_words = [w for w in words if tmap_main.word_kept(w)]
        units_main = []
        for u in E.build_units(kept_words, params.unit_gap):
            a, b = tmap_main.to_out(u.start), tmap_main.to_out(u.end)
            if a is not None and b is not None:
                units_main.append({"start": a, "end": b, "text": u.text})

        # 5) slayd sinxronizatsiyasi
        prog("slayd", 0, "Slaydlar moslanmoqda")
        spans: list = []
        with tm.step("5_slayd"):
            if cfg.slides and cfg.template == "maruza_slayd":
                spans, sw = S.sync_slides(units_main, page_texts, T, cfg.min_slide_dwell)
                warnings += sw
                if not cfg.dry_run:
                    canvas = G.slide_canvas(lesson, cfg.logo)
                    x0, y0, x1, y1 = G.Geo.SLIDE
                    imgs = S.render_pages(cfg.slides, work, (x1 - x0, y1 - y0))
                    cards = []
                    for i, im in enumerate(imgs):
                        p = work / f"slide_{i:03d}.png"
                        G.slide_card(im, canvas).save(p)
                        cards.append(p)
                    rj.slide_cards = cards
            elif cfg.slides:
                warnings.append(f"Slaydlar '{cfg.template}' shablonida ko'rsatilmaydi (faqat boblar uchun ishlatildi)")
            rj.slide_spans = spans
        slide_changes = [{"t": round(rj.main_offset + a, 2), "slide": (s + 1 if s >= 0 else None)}
                         for a, _, s in spans]

        # 6a) boblar
        plan = [p for p in lesson.plan if chapters.clean_plan_item(p)]
        times = chapters.find_chapter_times(plan, T, units_main, spans or None, page_texts or None)
        chs = chapters.build_chapters(plan, times, rj.main_offset, T)
        clean_plan = [chapters.clean_plan_item(p) for p in plan]
        rj.chapters_main = [(c["start"] - rj.main_offset, clean_plan.index(c["title"]) + 1, c["title"])
                            for c in chs if c["title"] in clean_plan and c["start"] > 0]

        # 7) subtitrlar
        cues = captions.build_cues(words, tmap_out)
        (out / "captions.vtt").write_text(captions.to_vtt(cues), encoding="utf-8")
        if cfg.burn_captions and not cfg.dry_run:
            if cfg.template == "maruza_slayd" and spans:
                ass = captions.to_ass(cues, offset=rj.main_offset, margin_l=64, margin_r=1920 - G.Geo.SLIDE[2],
                                      margin_v=22, size=34)
            else:
                ass = captions.to_ass(cues, offset=rj.main_offset, margin_l=240, margin_r=240, margin_v=64)
            (work / "captions.ass").write_text(ass, encoding="utf-8")
            rj.ass = work / "captions.ass"

        # 8) render
        duration_out = rj.total
        if not cfg.dry_run:
            prog("render", 0, "Video yig'ilmoqda")
            with tm.step("6_render"):
                compose.render(rj, cancel=cancel, on_progress=lambda f: prog("render", f))
            with tm.step("8_miniatyura"):
                real = P.probe(out / "final.mp4").duration
                if abs(real - rj.total) > 0.5:
                    warnings.append(f"Chiqish davomiyligi kutilganidan farq qiladi: {real:.1f} s / {rj.total:.1f} s")
                duration_out = real
                t_th = (chs[1]["start"] + 4) if len(chs) > 1 else rj.main_offset + T * 0.3
                t_th = min(max(t_th, rj.main_offset + 1), rj.main_offset + T - 1)
                fr = compose.extract_frame(out / "final.mp4", t_th, work / "thumb_src.png")
                from PIL import Image
                G.thumbnail(Image.open(fr), lesson, cfg.logo).save(out / "thumbnail.jpg", quality=90)

        # 9) hisobot
        prog("yakun", 0.5, "Hisobot yozilmoqda")
        tm.data["jami"] = round(time.perf_counter() - t_start, 2)
        report = {
            "duration_in": round(raw.duration, 2),
            "duration_out": round(duration_out, 2),
            "cuts": [{"start": round(c["start"], 2), "end": round(c["end"], 2), "reason": c["reason"]}
                     for c in edl["cuts"]],
            "chapters": [{"start": round(c["start"], 2), "title": c["title"]} for c in chs],
            "slide_changes": slide_changes,
            "warnings": warnings,
            "timings": tm.data,
        }
        write_json(out / "report.json", report)
        write_json(out / "edl.json", {**edl, "confidence": conf, "language": tr.get("language"),
                                      "main_offset": rj.main_offset, "main_duration": T,
                                      "template": cfg.template, "input": raw.to_dict()})
        (out / "youtube_chapters.txt").write_text(
            "\n".join(f"{fmt_ts(c['start'])} {c['title']}" for c in chs) + "\n", encoding="utf-8")
        prog("yakun", 1, "Tayyor")
        log.info("Tayyor: %s (%.1f s → %.1f s, %d kesish, %.0f s ishlov)", out, raw.duration, duration_out,
                 len(edl["cuts"]), tm.data["jami"])
        for w in warnings:
            log.warning("⚠ %s", w)
        return report
    finally:
        if cfg.keep_work:
            shutil.copytree(work, out / "work", dirs_exist_ok=True)
        shutil.rmtree(work, ignore_errors=True)
