"""1-qadam: kirish faylini tekshirish (fps, o'lcham, burilish, audio) va 48k mono tahlil nusxasi."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from .common import MontajError, SR, run_ffmpeg, log, CancelToken, NO_CANCEL


@dataclass
class MediaInfo:
    path: str
    duration: float
    has_video: bool
    width: int = 0          # burilish hisobga olingan (ko'rinadigan) o'lcham
    height: int = 0
    fps: float = 0.0
    rotation: int = 0
    video_start: float = 0.0
    video_duration: float = 0.0
    has_audio: bool = False
    audio_rate: int = 0
    audio_channels: int = 0
    audio_start: float = 0.0

    def to_dict(self):
        return asdict(self)


def probe(path: str | Path) -> MediaInfo:
    import av

    path = str(path)
    if not Path(path).exists():
        raise MontajError(f"Fayl topilmadi: {path}")
    try:
        c = av.open(path)
    except Exception as e:
        raise MontajError(f"Faylni ochib bo'lmadi ({path}): {e}")
    try:
        dur = float(c.duration / 1e6) if c.duration else 0.0
        info = MediaInfo(path=path, duration=dur, has_video=False)
        vs = next((s for s in c.streams if s.type == "video" and not _is_cover(s)), None)
        if vs is not None:
            info.has_video = True
            w, h = vs.codec_context.width, vs.codec_context.height
            rate = vs.average_rate or vs.guessed_rate or vs.base_rate
            info.fps = float(rate) if rate else 0.0
            info.video_start = float(vs.start_time * vs.time_base) if vs.start_time is not None else 0.0
            rot = 0
            try:  # PyAV ≥13: kadrdagi display matrix
                for frame in c.decode(vs):
                    rot = int(round(getattr(frame, "rotation", 0) or 0))
                    break
            except Exception:
                pass
            if not rot:
                try:
                    rot = int(vs.metadata.get("rotate", 0))
                except Exception:
                    rot = 0
            info.rotation = rot % 360
            if info.rotation in (90, 270):
                w, h = h, w
            info.width, info.height = w, h
            if vs.duration:
                info.video_duration = float(vs.duration * vs.time_base)
            if not dur and info.video_duration:
                info.duration = info.video_duration
        aud = next((s for s in c.streams if s.type == "audio"), None)
        if aud is not None:
            info.has_audio = True
            info.audio_rate = aud.codec_context.sample_rate or 0
            info.audio_channels = aud.codec_context.channels if hasattr(aud.codec_context, "channels") else 0
            info.audio_start = float(aud.start_time * aud.time_base) if aud.start_time is not None else 0.0
    finally:
        c.close()
    if info.duration <= 0:
        raise MontajError("Faylning davomiyligini aniqlab bo'lmadi")
    log.info("Kirish: %s — %.1f s, %dx%d @ %.2f fps, burilish %d°, audio=%s",
             Path(path).name, info.duration, info.width, info.height, info.fps, info.rotation, info.has_audio)
    return info


def _is_cover(s) -> bool:
    try:
        return bool(s.disposition & 0x400)  # attached_pic
    except Exception:
        return False


def extract_analysis_audio(info: MediaInfo, out_wav: Path, cancel: CancelToken = NO_CANCEL) -> Path:
    """Audio → 48 kHz mono WAV. Video bilan sinxronlik uchun audio boshlanish siljishi tuzatiladi."""
    if not info.has_audio:
        raise MontajError("Kirish faylida audio yo'q")
    off = info.audio_start - (info.video_start if info.has_video else info.audio_start)
    af = []
    if off > 0.005:      # audio videodan kechroq boshlanadi → boshiga sukunat
        af.append(f"adelay={int(off * 1000)}:all=1")
    elif off < -0.005:   # audio oldinroq → ortiqchasini kesamiz
        af.append(f"atrim=start={-off:.3f},asetpts=PTS-STARTPTS")
    af.append(f"aresample={SR}")
    run_ffmpeg(["-i", info.path, "-map", "0:a:0", "-vn", "-af", ",".join(af), "-ac", "1",
                "-c:a", "pcm_s16le", "-t", f"{info.duration:.3f}", str(out_wav)],
               cancel=cancel, desc="audio ajratish")
    return out_wav


_CENTER_CACHE: dict = {}


def subject_center(path: str, samples: int = 32) -> tuple[float, float]:
    """Kadrdagi harakatlanuvchi obyekt (o'qituvchi) markazi (0..1, 0..1).

    Usul: bir necha kadr olinadi, mediana fon hisoblanadi, |kadr − fon| xaritasi to'planadi.
    Harakat sezilmasa — (0.5, 0.5)."""
    if path in _CENTER_CACHE:
        return _CENTER_CACHE[path]
    import av
    import numpy as np
    res = (0.5, 0.5)
    try:
        c = av.open(path)
        vs = c.streams.video[0]
        dur = float(c.duration / 1e6) if c.duration else 0
        frames = []
        for k in range(samples):
            t = dur * (k + 0.5) / samples
            c.seek(int(t / vs.time_base), stream=vs, any_frame=False, backward=True)
            for fr in c.decode(vs):
                frames.append(fr.to_ndarray(width=160, height=90, format="gray").astype(np.float32))
                break
        c.close()
        if len(frames) >= 6:
            st = np.stack(frames)
            bg = np.median(st, axis=0)
            heat = np.abs(st - bg).mean(axis=0)
            heat = np.where(heat > np.percentile(heat, 80), heat, 0)
            tot = heat.sum()
            if tot > 1e-3 and heat.max() > 4.0:
                ys, xs = np.mgrid[0:heat.shape[0], 0:heat.shape[1]]
                cx = float((heat * xs).sum() / tot / heat.shape[1])
                cy = float((heat * ys).sum() / tot / heat.shape[0])
                res = (min(max(cx, 0.15), 0.85), min(max(cy, 0.2), 0.8))
    except Exception as e:
        log.debug("subject_center: %s", e)
    log.info("O'qituvchi joylashuvi (harakat xaritasi): x=%.2f y=%.2f", *res)
    _CENTER_CACHE[path] = res
    return res
