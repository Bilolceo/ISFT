"""6-qadam: kompozitsiya — bitta ffmpeg o'tishida kesish + maket + grafika + intro/outro + kodlash.

Sinxronlik kafolati: video avval 30 fps ga keltiriladi, audio esa 1600 namunali (=1 kadr) bo'laklarga
bo'linadi; kesish chegaralari 1/30 s to'rida bo'lgani uchun `select` va `aselect` aynan bir xil
kadrlarni tanlaydi — kesishlar ko'p bo'lsa ham audio/video siljimaydi.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from . import graphics as G
from .common import (W, H, FPS, SR, SAMPLES_PER_FRAME, FFMPEG, run_ffmpeg, log, CancelToken, NO_CANCEL,
                     MontajError)
from .probe import MediaInfo

INTRO_DUR = 4.5
OUTRO_DUR = 3.5
XFADE = 0.6
LOWER_THIRD_AT = (0.8, 6.8)  # asosiy qism vaqtida (intro'dan keyingi birinchi 6 s)
BANNER_DUR = 2.4
PAPER_HEX = "0xFAF7F8"
MAROON_HEX = "0x870037"

_ENCODER_CACHE: dict = {}


def pick_encoder(prefer: str = "auto") -> str:
    """h264_videotoolbox (Mac, tez) yoki libx264 (zaxira)."""
    if prefer in ("libx264", "h264_videotoolbox"):
        return prefer
    if "enc" not in _ENCODER_CACHE:
        enc = "libx264"
        try:
            r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "color=c=black:s=256x144:d=0.2", "-c:v", "h264_videotoolbox", "-f", "null", "-"],
                               capture_output=True, timeout=30)
            if r.returncode == 0:
                enc = "h264_videotoolbox"
        except Exception:
            pass
        _ENCODER_CACHE["enc"] = enc
        log.info("Video kodlovchi: %s", enc)
    return _ENCODER_CACHE["enc"]


def encoder_args(enc: str) -> list[str]:
    if enc == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-b:v", "5M", "-maxrate", "8M",
                "-bufsize", "10M", "-g", "60"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-profile:v", "high", "-g", "60"]


def select_expr(keeps: list[tuple[float, float]], shift: float = 0.0) -> str:
    """Saqlanadigan bo'laklar uchun ffmpeg ifodasi. Ko'p bo'lakda — muvozanatli if(lt(t,…)) daraxti
    (har kadrda O(log n) baholash; 90 daqiqalik ma'ruzada yuzlab bo'lak bo'lishi mumkin)."""
    iv = [(a - shift - 0.001, b - shift - 0.002) for a, b in keeps]
    if not iv:
        return "0"

    def node(lo, hi):
        if hi - lo <= 4:
            return "+".join(f"between(t,{a:.4f},{b:.4f})" for a, b in iv[lo:hi])
        mid = (lo + hi) // 2
        return f"if(lt(t,{iv[mid][0]:.4f}),{node(lo, mid)},{node(mid, hi)})"
    return node(0, len(iv))


@dataclass
class Overlay:
    png: Path
    t0: float        # asosiy qism vaqtida
    dur: float
    x: int
    y: int


@dataclass
class RenderJob:
    template: str
    raw: MediaInfo
    clean_wav: Path
    keeps: list
    work: Path
    out: Path
    lesson: G.Lesson
    logo: Path | None = None
    webcam: MediaInfo | None = None
    webcam_offset: float = 0.0
    slide_spans: list = field(default_factory=list)   # [(start,end,slayd)] asosiy qism vaqtida
    slide_cards: list = field(default_factory=list)   # sahifa indeksi → karta PNG
    chapters_main: list = field(default_factory=list)  # [(asosiy vaqt, indeks, nomi)]
    intro: bool = True
    outro: bool = True
    ass: Path | None = None
    encoder: str = "auto"

    @property
    def main_duration(self) -> float:
        return round(sum(round((b - a) * FPS) for a, b in self.keeps) / FPS, 4)

    @property
    def main_offset(self) -> float:
        return INTRO_DUR - XFADE if self.intro else 0.0

    @property
    def total(self) -> float:
        t = self.main_offset + self.main_duration
        if self.outro:
            t += OUTRO_DUR - XFADE
        return round(t, 4)


class Graph:
    def __init__(self):
        self.inputs: list[list[str]] = []
        self.lines: list[str] = []

    def inp(self, *args) -> int:
        self.inputs.append(list(args))
        return len(self.inputs) - 1

    def img(self, path: Path, dur: float, rate: int = 1) -> int:
        return self.inp("-framerate", str(rate), "-loop", "1", "-t", f"{dur:.3f}", "-i", str(path))

    def add(self, s: str):
        self.lines.append(s)


def subject_crop(info: MediaInfo, tw: int, th: int) -> str:
    """O'qituvchi joylashgan joy atrofida tw:th nisbatli kesish (harakat xaritasi bo'yicha)."""
    from .probe import subject_center
    iw, ih = info.width, info.height
    if iw / ih > tw / th:
        cw, ch = int(ih * tw / th) // 2 * 2, ih
    else:
        cw, ch = iw, int(iw * th / tw) // 2 * 2
    cx, cy = subject_center(info.path)
    x = int(min(max(cx * iw - cw / 2, 0), iw - cw)) // 2 * 2
    y = int(min(max(cy * ih - ch * 0.45, 0), ih - ch)) // 2 * 2
    return f"crop={cw}:{ch}:{x}:{y}"


def _ffq(p) -> str:
    """ffconcat uchun qo'shtirnoqli yo'l (apostrofli papka nomlari, masalan "Ma'lumotlar")."""
    return "'" + str(p).replace("'", "'\\''") + "'"


def _fill_frame(g: Graph, src: str, out: str, info: MediaInfo, blur_bg: bool = True):
    """Har qanday nisbatdagi videoni 1920×1080 ga: 16:9 ga yaqin bo'lsa — kesib to'ldirish,
    aks holda xiralashtirilgan fon ustida to'liq ko'rinish."""
    ar = (info.width / info.height) if info.height else 16 / 9
    if abs(ar - 16 / 9) < 0.08 or not blur_bg:
        g.add(f"[{src}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[{out}]")
    else:
        g.add(f"[{src}]split=2[{out}_a][{out}_b]")
        g.add(f"[{out}_a]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,boxblur=20:2,"
              f"scale={W}:{H},setsar=1[{out}_bg]")
        g.add(f"[{out}_b]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[{out}_fg]")
        g.add(f"[{out}_bg][{out}_fg]overlay=(W-w)/2:(H-h)/2[{out}]")


def build_graph(job: RenderJob) -> tuple[Graph, list[str]]:
    g = Graph()
    T = job.main_duration
    sel = select_expr(job.keeps)
    work = job.work
    i_raw = g.inp("-i", job.raw.path)
    i_wav = g.inp("-i", str(job.clean_wav))

    # --- kesilgan asosiy video oqimi
    g.add(f"[{i_raw}:v]setpts=PTS-STARTPTS,fps={FPS},select='{sel}',setpts=N/{FPS}/TB,format=yuv420p[vsel]")

    tpl = job.template
    if tpl == "maruza_slayd" and job.slide_spans and any(s >= 0 for _, _, s in job.slide_spans):
        canvas = G.slide_canvas(job.lesson, job.logo)
        canvas.save(work / "canvas.png")
        G.teacher_mask().save(work / "teacher_mask.png")
        G.teacher_label(job.lesson).save(work / "teacher_label.png")
        # slayd kartalari ketma-ketligi (concat demuxer)
        lines = ["ffconcat version 1.0"]
        last_card = None
        for a, b, s in job.slide_spans:
            card = job.slide_cards[s] if s >= 0 else (last_card or job.slide_cards[0])
            last_card = card
            lines += [f"file {_ffq(card)}", f"duration {max(0.04, b - a):.4f}"]
        lines += [f"file {_ffq(last_card)}"]
        (work / "slides.ffconcat").write_text("\n".join(lines) + "\n")
        i_can = g.img(work / "canvas.png", T)
        i_sl = g.inp("-f", "concat", "-safe", "0", "-i", str(work / "slides.ffconcat"))
        i_mask = g.inp("-i", str(work / "teacher_mask.png"))
        i_lab = g.inp("-i", str(work / "teacher_label.png"))
        x0, y0, x1, y1 = G.Geo.TEACH
        tw, th = x1 - x0 - 12, y1 - y0 - 12
        g.add("[vsel]split=2[vt1][vt2]")
        _fill_frame(g, "vt1", "full", job.raw)
        g.add(f"[vt2]{subject_crop(job.raw, tw, th)},scale={tw}:{th},setsar=1,format=rgba[tsm]")
        g.add(f"[{i_mask}:v]format=gray,scale={tw}:{th}[tmask]")
        g.add("[tsm][tmask]alphamerge[tround]")
        g.add(f"[{i_can}:v]fps={FPS},format=yuv420p[can]")
        g.add(f"[{i_sl}:v]fps={FPS},format=yuv420p[sl]")
        g.add(f"[can][sl]overlay={G.Geo.SLIDE[0]}:{G.Geo.SLIDE[1]}:eof_action=repeat[c1]")
        g.add(f"[c1][tround]overlay={x0 + 6}:{y0 + 6}:eof_action=repeat[c2]")
        with Image.open(work / "teacher_label.png") as im:
            lab_h = im.height
        g.add(f"[c2][{i_lab}:v]overlay={x0 + 6 + 20 - 40}:{y1 - 6 - 20 - lab_h + 40}[lay]")
        on = "+".join(f"between(t,{a:.3f},{b - 0.001:.3f})" for a, b, s in job.slide_spans if s >= 0)
        g.add(f"[full][lay]overlay=0:0:enable='{on}'[m0]")
    elif tpl == "ekran":
        g.add(f"[vsel]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x1A1216,"
              f"setsar=1[scr]")
        if job.webcam:
            pf = G.pip_frame()
            pf.save(work / "pip_frame.png")
            G.pip_mask().save(work / "pip_mask.png")
            i_cam = g.inp("-i", job.webcam.path)
            i_pf = g.inp("-i", str(work / "pip_frame.png"))
            i_pm = g.inp("-i", str(work / "pip_mask.png"))
            x0, y0, x1, y1 = G.Geo.PIP
            pw, ph = x1 - x0 - 10, y1 - y0 - 10
            off = job.webcam_offset
            pre = ""
            if off > 0:
                pre = f"tpad=start_duration={off:.3f}:start_mode=clone,"
            elif off < 0:
                pre = f"trim=start={-off:.3f},setpts=PTS-STARTPTS,"
            g.add(f"[{i_cam}:v]setpts=PTS-STARTPTS,{pre}fps={FPS},select='{sel}',setpts=N/{FPS}/TB,"
                  f"{subject_crop(job.webcam, pw, ph)},scale={pw}:{ph},setsar=1,format=rgba[cam]")
            g.add(f"[{i_pm}:v]format=gray,scale={pw}:{ph}[pmask]")
            g.add("[cam][pmask]alphamerge[camr]")
            g.add(f"[scr][{i_pf}:v]overlay={x0 - 60}:{y0 - 60}[s1]")
            g.add(f"[s1][camr]overlay={x0 + 5}:{y0 + 5}:eof_action=pass[m0]")
        else:
            g.add("[scr]null[m0]")
    else:  # faqat_oqituvchi (yoki slaydsiz maruza_slayd)
        _fill_frame(g, "vsel", "m0", job.raw)

    # --- umumiy qatlamlar: pastki chiziq, suv belgisi, lower-third, bob bannerlari, subtitr
    g.add(f"[m0]drawbox=x=0:y=ih-{G.Geo.BAR_H}:w=iw:h={G.Geo.BAR_H}:color={MAROON_HEX}:t=fill[m1]")
    G.watermark(job.logo).save(work / "watermark.png")
    i_wm = g.inp("-i", str(work / "watermark.png"))
    with Image.open(work / "watermark.png") as im:
        wm_size = im.size
    # joy — G.watermark_xy: o'qituvchi/kamera sohasini (PiP, o'qituvchi ramkasi) hech qachon yopmaydi
    if tpl == "maruza_slayd" and job.slide_spans:  # slayd paytida sarlavha qatori bilan bir chiziqda
        on_s = "+".join(f"between(t,{a:.3f},{b - 0.001:.3f})" for a, b, s in job.slide_spans if s >= 0) or "0"
        (xa, ya), (xb, yb) = G.watermark_xy(tpl, wm_size, True), G.watermark_xy(tpl, wm_size, False)
        g.add(f"[m1][{i_wm}:v]overlay=x='if({on_s},{xa},{xb})':y='if({on_s},{ya},{yb})':eval=frame[m2]")
    else:
        wx, wy = G.watermark_xy(tpl, wm_size, False)
        g.add(f"[m1][{i_wm}:v]overlay={wx}:{wy}[m2]")
    cur = "m2"
    for k, ov in enumerate(overlays_for(job)):
        idx = g.img(ov.png, ov.dur, rate=2)
        g.add(f"[{idx}:v]fps={FPS},format=rgba,fade=t=in:st=0:d=0.35:alpha=1,"
              f"fade=t=out:st={ov.dur - 0.4:.3f}:d=0.4:alpha=1,setpts=PTS+{ov.t0:.3f}/TB[ov{k}]")
        g.add(f"[{cur}][ov{k}]overlay={ov.x}:{ov.y}:eof_action=pass[mo{k}]")
        cur = f"mo{k}"
    if job.ass:
        p = str(job.ass).replace("'", r"\'").replace(":", r"\:")
        fd = "/System/Library/Fonts/Supplemental"
        g.add(f"[{cur}]subtitles=filename='{p}':fontsdir='{fd}'[msub]")
        cur = "msub"
    g.add(f"[{cur}]trim=duration={T:.4f},fps={FPS},settb=1/{FPS},format=yuv420p,setsar=1[main]")

    # --- intro / outro
    vlast = "main"
    if job.intro:
        bg, fg = G.intro_layers(job.lesson, job.logo)
        bg.save(work / "intro_bg.png")
        fg.save(work / "intro_fg.png")
        ib, ifg = g.img(work / "intro_bg.png", INTRO_DUR), g.img(work / "intro_fg.png", INTRO_DUR, rate=1)
        g.add(f"[{ifg}:v]fps={FPS},format=rgba,fade=t=in:st=0.5:d=0.9:alpha=1[ifg]")
        g.add(f"[{ib}:v]fps={FPS},format=rgba[ibg]")
        g.add(f"[ibg][ifg]overlay=x=0:y='if(lt(t,0.5),28,if(lt(t,1.4),28*(1-(t-0.5)/0.9),0))':eval=frame,"
              f"fade=t=in:st=0:d=0.6:color={PAPER_HEX},trim=duration={INTRO_DUR},fps={FPS},settb=1/{FPS},"
              f"format=yuv420p,setsar=1[intro]")
        g.add(f"[intro][main]xfade=transition=fade:duration={XFADE}:offset={INTRO_DUR - XFADE:.4f}[vi]")
        vlast = "vi"
    if job.outro:
        bg, fg = G.outro_layers(job.lesson, job.logo)
        bg.save(work / "outro_bg.png")
        fg.save(work / "outro_fg.png")
        ob, ofg = g.img(work / "outro_bg.png", OUTRO_DUR), g.img(work / "outro_fg.png", OUTRO_DUR)
        g.add(f"[{ofg}:v]fps={FPS},format=rgba,fade=t=in:st=0.4:d=0.8:alpha=1[ofg]")
        g.add(f"[{ob}:v]fps={FPS},format=rgba[obg]")
        g.add(f"[obg][ofg]overlay=0:0,fade=t=out:st={OUTRO_DUR - 0.7:.2f}:d=0.7,trim=duration={OUTRO_DUR},"
              f"fps={FPS},settb=1/{FPS},format=yuv420p,setsar=1[outro]")
        before = (job.main_offset + T) if job.intro else T
        g.add(f"[{vlast}][outro]xfade=transition=fade:duration={XFADE}:offset={before - XFADE:.4f}[vo]")
        vlast = "vo"
    g.add(f"[{vlast}]format=yuv420p[vout]")

    # --- audio: bir xil kadr to'rida kesish
    off_ms = int(round(job.main_offset * 1000))
    g.add(f"[{i_wav}:a]asetnsamples=n={SAMPLES_PER_FRAME}:p=1,aselect='{sel}',asetpts=N/SR/TB,"
          f"afade=t=in:d=0.12,afade=t=out:st={max(0.0, T - 0.5):.3f}:d=0.5,"
          f"adelay={off_ms}:all=1,apad,atrim=0:{job.total:.4f},aresample={SR},"
          f"pan=stereo|c0=c0|c1=c0[aout]")
    return g, ["-map", "[vout]", "-map", "[aout]"]


def overlays_for(job: RenderJob) -> list[Overlay]:
    """Lower-third (boshida) + har bob boshida banner. Joylashuv maketga bog'liq."""
    work = job.work
    pad = G.OVERLAY_PAD
    out = []

    def slide_on(t):
        return any(a <= t < b and s >= 0 for a, b, s in job.slide_spans) if job.template == "maruza_slayd" else False

    def pos(img: Image.Image, t: float) -> tuple[int, int]:
        h = img.height - 2 * pad
        if slide_on(t):
            if job.ass:  # pastda subtitr — slayd yuqori chetiga
                return G.Geo.SLIDE[0] + 32 - pad, G.Geo.SLIDE[1] + 28 - pad
            return G.Geo.SLIDE[0] + 32 - pad, G.Geo.SLIDE[3] - h // 2 - pad  # slayd pastki chetiga "minib" turadi
        return 72 - pad, H - 150 - h - pad

    T = job.main_duration
    a, b = LOWER_THIRD_AT
    if job.lesson.teacher and T > b + 1:
        lt = G.lower_third(job.lesson.teacher, job.lesson.subject)
        lt.save(work / "lower_third.png")
        out.append(Overlay(work / "lower_third.png", a, b - a, *pos(lt, a + 1)))
    for t, idx, title in job.chapters_main:
        if t < b + 0.5:  # lower-third bilan to'qnashmasin
            t = b + 0.5
        if t + BANNER_DUR > T - 1:
            continue
        bn = G.chapter_banner(idx, title)
        p = work / f"banner_{idx}.png"
        bn.save(p)
        out.append(Overlay(p, t + 0.3, BANNER_DUR, *pos(bn, t + 1)))
    return out


def render(job: RenderJob, *, cancel: CancelToken = NO_CANCEL, on_progress=None) -> Path:
    if not job.keeps:
        raise MontajError("Kesishdan keyin hech narsa qolmadi")
    enc = pick_encoder(job.encoder)
    g, maps = build_graph(job)
    script = job.work / "graph.txt"
    script.write_text(";\n".join(g.lines))
    args = []
    for i in g.inputs:
        args += i
    args += ["-/filter_complex", str(script), *maps, *encoder_args(enc), "-pix_fmt", "yuv420p", "-r", str(FPS),
             "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-movflags", "+faststart",
             "-metadata", f"title={job.lesson.code_title}", "-t", f"{job.total:.3f}", str(job.out)]
    log.info("Render: %s shabloni, %.1f s chiqish, %d bo'lak, kodlovchi %s", job.template, job.total,
             len(job.keeps), enc)
    try:
        run_ffmpeg(args, cancel=cancel, total=job.total, on_progress=on_progress, desc="render")
    except MontajError as e:
        if enc == "h264_videotoolbox" and "Cancel" not in type(e).__name__:
            log.warning("VideoToolbox xatosi — libx264 bilan qayta urinish")
            job.encoder = "libx264"
            args[args.index("-c:v"):args.index("-c:v") + len(encoder_args(enc))] = encoder_args("libx264")
            run_ffmpeg(args, cancel=cancel, total=job.total, on_progress=on_progress, desc="render (libx264)")
        else:
            raise
    return job.out


def extract_frame(video: Path, t: float, out_png: Path):
    run_ffmpeg(["-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1", str(out_png)], desc="kadr olish")
    return out_png
