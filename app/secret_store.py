"""Maxfiy ma'lumotlar ombori (kamera parollari va h.k.) — bazadan ALOHIDA.

Nega: SQLite bazasi zaxira nusxalarga, eksportlarga va tahlil skriptlariga tushadi; parol u yerda ochiq turmasligi kerak.

Rejimlar:
  * fernet  — `cryptography` o'rnatilgan bo'lsa: AES-128-CBC + HMAC (Fernet). Kalit: ISFT_CORE_SECRET_KEY muhit o'zgaruvchisi
              yoki data/secrets/master.key (0600, birinchi ishga tushishda yaratiladi). Kalit bazadan alohida saqlanishi shart.
  * file    — kutubxona yo'q bo'lsa: qiymatlar data/secrets/store.json da (0600, faqat server foydalanuvchisi o'qiydi).
              Bu shifrlash EMAS — faqat bazadan ajratish. `status()` buni ochiq aytadi; ishlab chiqarishda fernet rejimi talab qilinadi:
              .venv/bin/pip install cryptography
O'z kriptografiyamizni yozmaymiz.
"""
import base64, json, os, threading
from pathlib import Path

DIR = Path(os.getenv("ISFT_CORE_SECRETS_DIR", Path(__file__).resolve().parent.parent / "data" / "secrets"))
STORE = DIR / "store.json"
KEYFILE = DIR / "master.key"
_lock = threading.Lock()

try:
    from cryptography.fernet import Fernet, InvalidToken   # ixtiyoriy bog'liqlik
except Exception:   # pragma: no cover — kutubxona yo'q
    Fernet = None
    InvalidToken = Exception

def _ensure_dir():
    DIR.mkdir(parents=True, exist_ok=True)
    try: os.chmod(DIR, 0o700)
    except OSError: pass

def _write_private(path: Path, data: bytes):
    _ensure_dir()
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)   # atomar almashtirish
    os.chmod(path, 0o600)

def _fernet():
    if Fernet is None: return None
    k = os.getenv("ISFT_CORE_SECRET_KEY")
    if not k:
        if not KEYFILE.exists():
            _write_private(KEYFILE, Fernet.generate_key())
        k = KEYFILE.read_text().strip()
    return Fernet(k.encode() if isinstance(k, str) else k)

def mode() -> str:
    return "fernet" if Fernet is not None else "file"

def _load() -> dict:
    if not STORE.exists(): return {}
    try: return json.loads(STORE.read_text())
    except (OSError, ValueError): return {}

def put(name: str, value: str) -> None:
    with _lock:
        d = _load()
        f = _fernet()
        d[name] = {"m": "fernet", "v": f.encrypt(value.encode()).decode()} if f else {"m": "file", "v": base64.b64encode(value.encode()).decode()}
        _write_private(STORE, json.dumps(d).encode())

def get(name: str) -> str | None:
    d = _load().get(name)
    if not d: return None
    if d["m"] == "fernet":
        f = _fernet()
        if not f: raise RuntimeError("Sir fernet bilan shifrlangan, lekin `cryptography` o'rnatilmagan")
        try: return f.decrypt(d["v"].encode()).decode()
        except InvalidToken: raise RuntimeError("Sirni ochib bo'lmadi: kalit noto'g'ri (ISFT_CORE_SECRET_KEY / master.key)")
    return base64.b64decode(d["v"]).decode()

def delete(name: str) -> None:
    with _lock:
        d = _load()
        if d.pop(name, None) is not None:
            _write_private(STORE, json.dumps(d).encode())

def status() -> dict:
    return {"mode": mode(), "encrypted": mode() == "fernet",
            "note": "Shifrlangan (Fernet)" if mode() == "fernet" else
                    "Bazadan ajratilgan, lekin shifrlanmagan — `cryptography` o'rnatilishi kerak"}
