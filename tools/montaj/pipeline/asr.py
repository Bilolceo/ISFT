"""3-qadam: faster-whisper bilan nutqni matnga aylantirish (so'z vaqtlari, VAD, uz → avto zaxira).

Natija keshlanadi (~/.cache/isft-montaj/asr), shuning uchun bir xil yozuvni qayta ishlash tez.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .common import log, CancelToken, NO_CANCEL

CACHE_DIR = Path(os.environ.get("MONTAJ_CACHE", Path.home() / ".cache" / "isft-montaj")) / "asr"
_MODELS: dict = {}

# Whisper uz ni ko'pincha tr/kk/ru deb aniqlaydi — bu tillar o'zbek nutqi uchun "uz" bilan qoldiriladi.
_UZ_LIKE = {"uz", "tr", "kk", "ky", "tk", "az", "tt", "ba"}


def _file_hash(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _try_load(name: str, device: str):
    from faster_whisper import WhisperModel
    kw = dict(device=device, compute_type="float16" if device == "mps" else "int8", cpu_threads=os.cpu_count() or 4)
    try:  # avval faqat lokal kesh (studiyada internet bo'lmasligi mumkin)
        return WhisperModel(name, local_files_only=True, **kw)
    except Exception as e:
        if device == "mps":
            raise
        log.debug("lokal model topilmadi (%s) — yuklab olinadi", e)
        return WhisperModel(name, **kw)


def get_model(name: str, device: str = "auto"):
    """device: auto (Apple GPU / MPS, bo'lmasa CPU int8), mps yoki cpu.

    O'lchov (M4, large-v3): MPS float16 ≈ 0.22× real vaqt, CPU int8 ≈ 1.8× real vaqt."""
    key = (name, device)
    if key not in _MODELS:
        t0 = time.perf_counter()
        order = ["mps", "cpu"] if device == "auto" else [device]
        err = None
        for dev in order:
            try:
                _MODELS[key] = (_try_load(name, dev), dev)
                break
            except Exception as e:
                err = e
                log.info("Whisper %s qurilmasida yuklanmadi: %s", dev, str(e).splitlines()[0][:160])
        if key not in _MODELS:
            raise err
        log.info("Whisper modeli yuklandi: %s / %s (%.1f s)", name, _MODELS[key][1], time.perf_counter() - t0)
    return _MODELS[key][0]


def transcribe(wav: Path, *, model: str = "large-v3", language: str = "uz", prompt: str | None = None,
               use_cache: bool = True, on_progress=None, cancel: CancelToken = NO_CANCEL,
               multilingual: bool = False, device: str = "auto") -> dict:
    """Qaytaradi: {language, language_prob, duration, segments:[{start,end,text,avg_logprob,no_speech_prob,
    words:[{start,end,word,prob}]}], confidence}"""
    key = hashlib.sha1(f"{_file_hash(wav)}|{model}|{language}|{prompt or ''}|{multilingual}|v2".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.exists():
        log.info("Transkripsiya keshdan olindi (%s)", cache_file.name[:12])
        return json.loads(cache_file.read_text())

    from faster_whisper.audio import decode_audio
    m = get_model(model, device)
    audio = decode_audio(str(wav), sampling_rate=16000)
    duration = len(audio) / 16000.0

    lang = None if language == "auto" else language
    detected, det_prob = None, 0.0
    try:
        detected, det_prob, _ = m.detect_language(audio, vad_filter=True, language_detection_segments=3)
    except Exception as e:  # eski faster-whisper versiyalari
        log.debug("detect_language ishlamadi: %s", e)
    if language == "uz" and detected and detected not in _UZ_LIKE and det_prob >= 0.8:
        # Aniq rus yoki ingliz nutqi — o'sha til bilan tanimiz (zaxira)
        log.info("Til avtomatik aniqlandi: %s (%.2f) — uz o'rniga ishlatiladi", detected, det_prob)
        lang = detected
    elif language == "auto":
        lang = None
    log.info("Nutq tanish: model=%s til=%s (aniqlangan: %s %.2f), %.0f s audio", model, lang or "avto",
             detected, det_prob, duration)

    seg_iter, info = m.transcribe(
        audio, language=lang, beam_size=5, word_timestamps=True, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
        condition_on_previous_text=False, initial_prompt=prompt or None,
        multilingual=multilingual, temperature=[0.0, 0.2, 0.4],
    )
    segs = []
    for s in seg_iter:
        cancel.check()
        words = [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip(),
                  "prob": round(float(w.probability), 3)} for w in (s.words or []) if w.word.strip()]
        segs.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
                     "avg_logprob": round(s.avg_logprob, 3), "no_speech_prob": round(s.no_speech_prob, 3),
                     "words": words})
        if on_progress and duration:
            on_progress(min(1.0, s.end / duration))
    res = {"language": info.language, "language_prob": round(float(info.language_probability), 3),
           "detected_language": detected, "duration": round(duration, 3), "model": model, "segments": segs}
    res["confidence"] = confidence(res)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(res, ensure_ascii=False))
    return res


def all_words(tr: dict) -> list[dict]:
    return [w for s in tr.get("segments", []) for w in s.get("words", [])]


def confidence(tr: dict) -> float:
    """So'z ehtimolliklarining davomiylik bo'yicha o'rtachasi (0..1)."""
    num = den = 0.0
    for w in all_words(tr):
        d = max(0.05, w["end"] - w["start"])
        num += w["prob"] * d
        den += d
    return round(num / den, 3) if den else 0.0
