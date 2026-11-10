"""Claude API — umumiy mijoz (app/taqdimot.py, app/tekshiruv.py).

Kalit FAQAT muhit o'zgaruvchisidan: ANTHROPIC_API_KEY (Railway → Variables). Kodda, faylda, logda kalit saqlanmaydi.
call_json() — tuzilgan (JSON sxemali) javob; xatolar o'zbekcha AIError ga aylantiriladi.
"""
from __future__ import annotations
import base64, io, json, os


class AIError(Exception):
    pass


def has_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def image_block(path_or_bytes, max_px: int = 1568, quality: int = 82) -> dict | None:
    """Rasm → Claude image bloki (JPEG, uzun tomoni ≤ max_px). O'qib bo'lmasa — None."""
    from PIL import Image
    try:
        pic = Image.open(io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes)
        pic.thumbnail((max_px, max_px))
        if pic.mode not in ("RGB", "L"):
            pic = pic.convert("RGB")
        buf = io.BytesIO(); pic.save(buf, "JPEG", quality=quality)
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(buf.getvalue()).decode()}}
    except Exception:
        return None


def call_json(*, model: str, system: str, content: list, schema: dict, max_tokens: int = 16000, effort: str = "medium",
              timeout: float = 300.0, what: str = "javob") -> tuple[dict, dict]:
    """Bitta so'rov → (JSON ma'lumot, {"in", "out", "model"}). Xatoda — AIError (o'zbekcha matn)."""
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise AIError("AI ulanmagan (ANTHROPIC_API_KEY yo'q). Administratorga murojaat qiling.")
    client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=2)
    req = dict(model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": content}],
               output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})
    try:
        try:
            with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **req) as st:
                msg = st.get_final_message()
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower():
                raise
            with client.messages.stream(**req) as st:      # zaxira modeli qo'llab-quvvatlanmasa — oddiy so'rov
                msg = st.get_final_message()
    except anthropic.AuthenticationError:
        raise AIError("AI kaliti noto'g'ri yoki bekor qilingan (ANTHROPIC_API_KEY). Administratorga murojaat qiling.")
    except anthropic.PermissionDeniedError:
        raise AIError("AI kalitiga bu model uchun ruxsat yo'q. Administratorga murojaat qiling.")
    except anthropic.RateLimitError:
        raise AIError("AI xizmati hozir band (so'rovlar cheklovi). Bir necha daqiqadan keyin qayta urinib ko'ring.")
    except anthropic.APITimeoutError:
        raise AIError("AI javobi kechikdi. Materialni qisqartirib yoki keyinroq qayta urinib ko'ring.")
    except anthropic.APIConnectionError:
        raise AIError("AI xizmatiga ulanib bo'lmadi (internet). Keyinroq qayta urinib ko'ring.")
    except anthropic.BadRequestError as e:
        raise AIError(f"AI so'rovni qabul qilmadi: {str(getattr(e, 'message', e))[:160]}")
    except anthropic.APIStatusError as e:
        raise AIError(f"AI xizmatida xatolik ({e.status_code}). Keyinroq qayta urinib ko'ring.")
    if msg.stop_reason == "refusal":
        raise AIError(f"AI bu material bo'yicha {what} berishni rad etdi.")
    if msg.stop_reason == "max_tokens":
        raise AIError(f"Material juda katta — {what} to'liq chiqmadi.")
    txt = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "")
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        raise AIError("AI javobini o'qib bo'lmadi. Qayta urinib ko'ring.")
    u = getattr(msg, "usage", None)
    return data, {"in": getattr(u, "input_tokens", 0) or 0, "out": getattr(u, "output_tokens", 0) or 0, "model": getattr(msg, "model", model)}
