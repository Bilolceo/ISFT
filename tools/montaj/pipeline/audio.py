"""2-qadam: audio tozalash (high-pass, afftdn, ikki bosqichli loudnorm −16 LUFS) va sukunat aniqlash."""
from __future__ import annotations

import json
import re
import wave
from pathlib import Path

import numpy as np

from .common import SR, run_ffmpeg, log, CancelToken, NO_CANCEL, MontajError

TARGET_I, TARGET_TP, TARGET_LRA = -16.0, -1.5, 11.0
PRE_CHAIN = "highpass=f=80,afftdn=nr=12:nf=-30:tn=1"


def _parse_loudnorm(stderr: str) -> dict:
    m = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)
    if not m:
        raise MontajError("loudnorm o'lchovini o'qib bo'lmadi")
    return json.loads(m[-1])


def clean_audio(src_wav: Path, out_wav: Path, cancel: CancelToken = NO_CANCEL) -> dict:
    """Tozalangan 48k mono WAV yaratadi. Qaytaradi: o'lchangan loudnorm qiymatlari."""
    err = run_ffmpeg(["-i", str(src_wav), "-af",
                      f"{PRE_CHAIN},loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
                      "-f", "null", "-"], cancel=cancel, desc="loudnorm 1-bosqich")
    m = _parse_loudnorm(err)
    log.info("Ovoz balandligi: %.1f LUFS (TP %.1f) → %.0f LUFS", float(m["input_i"]), float(m["input_tp"]), TARGET_I)
    if float(m["input_i"]) < -60:  # deyarli jim fayl — normallashtirish mumkin emas
        chain = PRE_CHAIN
    else:
        chain = (f"{PRE_CHAIN},loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
                 f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                 f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run_ffmpeg(["-i", str(src_wav), "-af", f"{chain},aresample={SR}", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
               cancel=cancel, desc="loudnorm 2-bosqich")
    return {k: m.get(k) for k in ("input_i", "input_tp", "input_lra", "input_thresh")}


def detect_silences(wav: Path, noise_db: float = -38.0, min_dur: float = 0.5,
                    cancel: CancelToken = NO_CANCEL) -> list[tuple[float, float]]:
    """ffmpeg silencedetect → [(boshlanish, tugash)]."""
    err = run_ffmpeg(["-i", str(wav), "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
                     cancel=cancel, desc="silencedetect")
    out, start = [], None
    for line in err.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    if start is not None:
        out.append((start, wav_duration(wav)))
    return out


def wav_duration(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def rms_envelope(wav: Path, hop: float = 0.02) -> np.ndarray:
    """Har `hop` soniyadagi RMS (dBFS). Katta fayllar uchun bo'laklab o'qiladi."""
    with wave.open(str(wav), "rb") as w:
        sr, n = w.getframerate(), w.getnframes()
        step = int(sr * hop)
        out = []
        chunk = step * 2000
        rem = b""
        while True:
            data = w.readframes(chunk)
            if not data:
                break
            a = np.frombuffer(rem + data, dtype=np.int16)
            usable = (len(a) // step) * step
            if usable:
                blk = a[:usable].astype(np.float32).reshape(-1, step) / 32768.0
                out.append(10 * np.log10(np.mean(blk * blk, axis=1) + 1e-10))
            rem = a[usable:].tobytes()
    return np.concatenate(out) if out else np.zeros(0)
