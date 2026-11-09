"""Yuklanayotgan fayllar mazmunini tekshirish (portal va boshqa yuklash joylari uchun). Faqat stdlib, sof funksiyalar.

Tamoyillar:
  * Kengaytmaga ishonilmaydi: har bir tur uchun "sehrli baytlar" (magic bytes) va ichki tuzilma tekshiriladi —
    nomi o'zgartirilgan exe/skript, makrosli Office hujjat, OLE obyektli RTF, xavfli arxiv qabul qilinmaydi.
  * Ixtiyoriy antivirus: `ISFT_CORE_CLAMD` (host:port yoki unix soket yo'li) berilsa, fayl clamd'ga INSTREAM orqali yuboriladi.
    clamd ishlamasa: `ISFT_CORE_CLAMD_REQUIRED=1` bo'lsa fayl rad etiladi, aks holda scan="tekshirilmadi".
  * Natija: {"sha256", "mime", "scan": "toza"|"tekshirilmadi", "engine": "clamd"|None} yoki FileRejected(o'zbekcha xabar).
"""
import hashlib, io, mimetypes, os, socket, struct, zipfile

class FileRejected(ValueError):
    """Fayl qabul qilinmadi; str(e) — foydalanuvchiga ko'rsatiladigan o'zbekcha sabab."""

MIMES = {
    "pdf": "application/pdf", "doc": "application/msword", "xls": "application/vnd.ms-excel", "ppt": "application/vnd.ms-powerpoint",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text", "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "rtf": "application/rtf", "txt": "text/plain; charset=utf-8", "csv": "text/csv; charset=utf-8",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "zip": "application/zip",
}
EXEC_EXT = {"exe", "dll", "bat", "cmd", "com", "scr", "msi", "ps1", "vbs", "js", "jse", "wsf", "hta", "jar", "lnk", "sh", "apk"}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")          # oddiy arxiv / bo'sh arxiv
ZIP_MAX_TOTAL = 200 * 1024 * 1024                   # ochilgandagi umumiy hajm chegarasi
ZIP_MAX_RATIO = 100                                 # siqish nisbati chegarasi (zip-bomba)
ZIP_MAX_ENTRIES = 10000
CLAMD_TIMEOUT = 15
OOXML_MAIN = {"docx": "word/", "xlsx": "xl/", "pptx": "ppt/"}
ODF_MIME = {"odt": "application/vnd.oasis.opendocument.text", "ods": "application/vnd.oasis.opendocument.spreadsheet"}
TEXT_EXT = {"txt", "csv"}

def sniff_mime(ext: str) -> str:
    """Kengaytma bo'yicha xavfsiz MIME (noma'lum bo'lsa — application/octet-stream)."""
    ext = (ext or "").lower().lstrip(".")
    return MIMES.get(ext) or mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"

def _short(s: str, n: int = 120) -> str:
    s = "".join(ch if ch.isprintable() else "?" for ch in str(s))
    return s if len(s) <= n else s[:n] + "…"

def _mismatch(ext):
    return FileRejected(f"Fayl mazmuni «.{ext}» kengaytmasiga mos emas (nomi o'zgartirilgan yoki fayl buzilgan)")

MACRO_MSG = "Makrosli hujjatlar qabul qilinmaydi — faylni makrossiz formatda (.docx/.xlsx/.pptx) saqlab qayta yuklang"

# --------------------------------------------------------------------------------------------- umumiy
def _no_executable(ext: str, data: bytes):
    head = data[:4]
    is_pe = data[:2] == b"MZ"
    if is_pe and ext in TEXT_EXT:                    # "MZ,..." bilan boshlanadigan CSV bo'lishi mumkin — haqiqiy PE sarlavhasini qidiramiz
        off = int.from_bytes(data[60:64], "little") if len(data) >= 64 else 0
        is_pe = 64 <= off < len(data) - 4 and data[off:off + 4] == b"PE\0\0"
    if is_pe or head[:2] == b"#!" or head == b"\x7fELF":
        raise FileRejected("Fayl bajariladigan dastur yoki skript — bunday fayllar qabul qilinmaydi")

# --------------------------------------------------------------------------------------------- ZIP asosidagi turlar
def _open_zip(ext: str, data: bytes) -> zipfile.ZipFile:
    if data[:8] == OLE_MAGIC and ext in OOXML_MAIN:
        raise FileRejected("Parol bilan himoyalangan hujjatni tekshirib bo'lmaydi — parolni olib tashlab qayta yuklang")
    if data[:4] not in ZIP_MAGIC: raise _mismatch(ext)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = z.infolist()
    except (zipfile.BadZipFile, ValueError, EOFError, OSError):
        raise FileRejected(f"Fayl buzilgan: «.{ext}» arxiv tuzilmasi o'qilmadi")
    if len(infos) > ZIP_MAX_ENTRIES: raise FileRejected("Arxivda fayllar soni juda ko'p — qabul qilinmadi")
    total = sum(i.file_size for i in infos)
    if total > ZIP_MAX_TOTAL or total > ZIP_MAX_RATIO * max(len(data), 1):
        raise FileRejected("Arxiv ochilganda juda katta hajm egallaydi (zip-bomba belgisi) — qabul qilinmadi")
    for i in infos:
        if i.flag_bits & 0x1:
            raise FileRejected("Parol bilan himoyalangan arxiv/hujjatlar qabul qilinmaydi (ichini tekshirib bo'lmaydi)")
        n = i.filename.replace("\\", "/")
        if n.startswith("/") or (len(n) > 1 and n[1] == ":") or ".." in n.split("/"):
            raise FileRejected(f"Arxiv ichida xavfli yo'l bor: {_short(i.filename)}")
    return z

def _read_small(z: zipfile.ZipFile, name: str, limit: int = 1 << 20) -> bytes:
    with z.open(name) as f: return f.read(limit)

def _check_ooxml(ext: str, data: bytes):
    z = _open_zip(ext, data)
    names = z.namelist()
    if "[Content_Types].xml" not in names or not any(n.startswith(OOXML_MAIN[ext]) for n in names): raise _mismatch(ext)
    if any(n.lower().rsplit("/", 1)[-1] == "vbaproject.bin" for n in names): raise FileRejected(MACRO_MSG)
    if b"macroenabled" in _read_small(z, "[Content_Types].xml").lower(): raise FileRejected(MACRO_MSG)

def _check_odf(ext: str, data: bytes):
    z = _open_zip(ext, data)
    if "mimetype" not in z.namelist() or _read_small(z, "mimetype", 200).strip() != ODF_MIME[ext].encode(): raise _mismatch(ext)
    if any(n.startswith(("Basic/", "Scripts/")) for n in z.namelist()): raise FileRejected(MACRO_MSG)

def _check_zip(ext: str, data: bytes):
    z = _open_zip(ext, data)
    for n in z.namelist():
        base = n.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        if "." in base and base.rsplit(".", 1)[-1].lower() in EXEC_EXT:
            raise FileRejected(f"Arxiv ichida ruxsat etilmagan fayl bor: {_short(n)}")

# --------------------------------------------------------------------------------------------- OLE2 (doc/xls/ppt)
_VBA_NAMES = [s.encode("utf-16le") for s in ("VBA", "Macros", "_VBA_PROJECT_CUR", "_VBA_PROJECT", "PROJECTwm")]

def _ole_has_vba(data: bytes) -> bool:
    if "_VBA_PROJECT".encode("utf-16le") in data: return True
    for nm in _VBA_NAMES:                            # katalog yozuvi: 128 baytga tekislangan, nom UTF-16LE + NUL, 64-baytda nom uzunligi
        pat, start = nm + b"\0\0", 0
        while (o := data.find(pat, start)) != -1:
            start = o + 1
            if o % 128 == 0 and o + 66 <= len(data) and int.from_bytes(data[o + 64:o + 66], "little") == len(pat): return True
    return False

def _check_ole(ext: str, data: bytes):
    if data[:8] != OLE_MAGIC: raise _mismatch(ext)
    if _ole_has_vba(data): raise FileRejected(MACRO_MSG)

# --------------------------------------------------------------------------------------------- boshqalar
def _check_rtf(ext: str, data: bytes):
    if not data.startswith(b"{\\rtf"): raise _mismatch(ext)
    low = data.lower()
    if b"\\objdata" in low or b"\\object" in low:
        raise FileRejected("RTF hujjat ichida joylashtirilgan obyekt (OLE) bor — xavfsizlik sababli qabul qilinmaydi")

def _magic(sig: bytes):
    def chk(ext, data):
        if not data.startswith(sig): raise _mismatch(ext)
    return chk

def _check_text(ext: str, data: bytes):
    if b"\0" in data:
        raise FileRejected(f"Matn fayli ichida ikkilik (binary) ma'lumot bor — .{ext} sifatida qabul qilinmaydi (UTF-8 da saqlang)")
    try: data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try: data.decode("cp1251")
        except UnicodeDecodeError: raise FileRejected("Matn fayli kodirovkasi aniqlanmadi — UTF-8 da saqlab qayta yuklang")

CHECKS = {
    "pdf": _magic(b"%PDF-"), "png": _magic(b"\x89PNG\r\n\x1a\n"), "jpg": _magic(b"\xff\xd8\xff"), "jpeg": _magic(b"\xff\xd8\xff"),
    "docx": _check_ooxml, "xlsx": _check_ooxml, "pptx": _check_ooxml, "odt": _check_odf, "ods": _check_odf,
    "doc": _check_ole, "xls": _check_ole, "ppt": _check_ole, "rtf": _check_rtf, "zip": _check_zip, "txt": _check_text, "csv": _check_text,
}

# --------------------------------------------------------------------------------------------- ClamAV (clamd INSTREAM)
def _clamd_addr(spec: str):
    spec = spec.strip()
    if spec.startswith(("/", ".")) or ":" not in spec: return socket.AF_UNIX, spec
    host, port = spec.rsplit(":", 1)
    return socket.AF_INET, (host.strip("[]") or "127.0.0.1", int(port))

def clamd_scan(data: bytes, spec: str, timeout: float = CLAMD_TIMEOUT) -> str:
    """clamd javobini qaytaradi (masalan "stream: OK"). Ulanish/protokol xatosida OSError."""
    fam, addr = _clamd_addr(spec)
    with socket.socket(fam, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(addr)
        s.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), 1 << 16):
            chunk = data[i:i + (1 << 16)]
            s.sendall(struct.pack("!I", len(chunk)) + chunk)
        s.sendall(struct.pack("!I", 0))
        buf = b""
        while b"\0" not in buf and len(buf) < 4096:
            part = s.recv(4096)
            if not part: break
            buf += part
    return buf.split(b"\0", 1)[0].decode("utf-8", "replace").strip()

def _antivirus(data: bytes) -> tuple[str, str | None]:
    spec = os.getenv("ISFT_CORE_CLAMD", "").strip()
    if not spec: return "tekshirilmadi", None
    try:
        reply = clamd_scan(data, spec)
    except (OSError, ValueError):
        reply = ""
    if reply.endswith("FOUND"):
        sig = reply.split(":", 1)[-1].rsplit("FOUND", 1)[0].strip() or "noma'lum"
        raise FileRejected(f"Faylda zararli dastur aniqlandi: {_short(sig)}")
    if reply.endswith(": OK"): return "toza", "clamd"
    if os.getenv("ISFT_CORE_CLAMD_REQUIRED", "").strip() == "1":
        raise FileRejected("Antivirus tekshiruvi ishlamayapti — fayl qabul qilinmadi")
    return "tekshirilmadi", None

# --------------------------------------------------------------------------------------------- asosiy kirish
def inspect(name: str, ext: str, data: bytes) -> dict:
    """Fayl mazmunini tekshiradi. Qabul qilinsa — {"sha256","mime","scan","engine"}; aks holda FileRejected."""
    ext = (ext or "").lower().lstrip(".")
    if not data: raise FileRejected("Fayl bo'sh")
    chk = CHECKS.get(ext)
    if chk is None: raise FileRejected(f"«.{_short(ext, 20)}» turidagi fayllar qabul qilinmaydi")
    _no_executable(ext, data)
    chk(ext, data)
    scan, engine = _antivirus(data)
    return {"sha256": hashlib.sha256(data).hexdigest(), "mime": sniff_mime(ext), "scan": scan, "engine": engine}
