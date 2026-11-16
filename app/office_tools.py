"""Tashqi yordamchi dasturlar (ixtiyoriy): LibreOffice (eski .ppt / .doc → .pptx / .docx, .pptx → PDF — aniq slayd rasmlari uchun)
va Tesseract OCR (skaner qilingan ma'ruza sahifalari matni). Ikkalasi ham bo'lmasa — tegishli funksiya mavjud emas (available() = False),
platforma avvalgidek ishlaydi.

Sozlash (muhit o'zgaruvchilari):
    ISFT_CORE_SOFFICE   — soffice yo'li (aks holda PATH dagi soffice/libreoffice, macOS'da /Applications/LibreOffice.app)
    ISFT_CORE_TESSERACT — tesseract yo'li (aks holda PATH)
    ISFT_CORE_TESSDATA  — *.traineddata katalogi (o'zbekcha: uzb.traineddata — github.com/tesseract-ocr/tessdata_best)
    ISFT_CORE_OCR_LANG  — OCR tili (standart: «uzb», bo'lmasa «eng»)
    ISFT_CORE_OFFICE=0 / ISFT_CORE_OCR=0 — o'chirish (testlar bir xil natija bersin: tests/run_all.py shunday ishga tushiradi)
"""
from __future__ import annotations

import csv, functools, io, os, re, shutil, signal, subprocess, tempfile, threading
from pathlib import Path

_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
_LOCK = threading.Lock()          # soffice bir profilda parallel ishlamaydi — navbat bilan


class ToolError(RuntimeError):
    pass


def soffice() -> str | None:
    if os.environ.get("ISFT_CORE_OFFICE") == "0": return None
    p = os.environ.get("ISFT_CORE_SOFFICE")
    if p: return p if Path(p).is_file() else None
    for n in ("soffice", "libreoffice"):
        w = shutil.which(n)
        if w: return w
    return _MAC_SOFFICE if Path(_MAC_SOFFICE).is_file() else None


def tesseract() -> str | None:
    if os.environ.get("ISFT_CORE_OCR") == "0": return None
    p = os.environ.get("ISFT_CORE_TESSERACT")
    if p: return p if Path(p).is_file() else None
    return shutil.which("tesseract")


def _tess_env() -> dict:
    env = dict(os.environ)
    if os.environ.get("ISFT_CORE_TESSDATA"): env["TESSDATA_PREFIX"] = os.environ["ISFT_CORE_TESSDATA"]
    return env


@functools.lru_cache(maxsize=4)
def _langs_for(t: str, tessdata: str) -> tuple:
    try:
        out = subprocess.run([t, "--list-langs"], capture_output=True, text=True, timeout=20, env=_tess_env()).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    return tuple(l.strip() for l in out.splitlines()[1:] if l.strip())


def ocr_langs() -> list[str]:   # ro'yxat ish vaqtida o'zgarmaydi — bir marta so'raladi (har /meta so'rovida fork qilinmasin)
    t = tesseract()
    if not t: return []
    return list(_langs_for(t, os.environ.get("ISFT_CORE_TESSDATA", "")))


def ocr_lang() -> str | None:
    langs = ocr_langs()
    want = os.environ.get("ISFT_CORE_OCR_LANG")
    if want and all(x in langs for x in want.split("+")): return want
    for l in ("uzb", "eng"):
        if l in langs: return l
    return None


def available() -> dict:
    lang = ocr_lang() if tesseract() else None
    return {"office": bool(soffice()), "ocr": bool(lang), "ocr_lang": lang}


def _run_group(cmd: list, timeout: int):
    """Yangi sessiyada ishga tushiradi; muddat tugasa butun jarayon guruhi (soffice.bin ham) o'ldiriladi — yetim jarayonlar qolmasin."""
    kw = {"start_new_session": True} if os.name == "posix" else {}
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix": os.killpg(p.pid, signal.SIGKILL)
            else: p.kill()
        except OSError:
            pass
        p.communicate()
        raise
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def convert(raw: bytes, src_ext: str, to: str, timeout: int = 240) -> bytes:
    """LibreOffice bilan formatni o'girish (masalan «ppt» → «pptx», «pptx» → «pdf», «doc» → «docx»). Xato → ToolError."""
    exe = soffice()
    if not exe: raise ToolError("Serverda LibreOffice o'rnatilmagan")
    src_ext = re.sub(r"[^a-z0-9]", "", src_ext.lower())[:6] or "bin"
    to = re.sub(r"[^a-z0-9]", "", to.lower())[:6]
    with _LOCK, tempfile.TemporaryDirectory(prefix="isft-office-") as d:
        dp = Path(d)
        src = dp / f"in.{src_ext}"; src.write_bytes(raw)
        prof = dp / "profile"
        cmd = [exe, f"-env:UserInstallation={prof.as_uri()}", "--headless", "--norestore", "--nolockcheck", "--nodefault",
               "--convert-to", to, "--outdir", str(dp / "out"), str(src)]
        try:
            r = _run_group(cmd, timeout)
        except subprocess.TimeoutExpired:
            raise ToolError("Faylni o'girish juda uzoq davom etdi")
        except OSError as e:
            raise ToolError(f"LibreOffice ishga tushmadi ({e})")
        out = dp / "out" / f"in.{to}"
        if r.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            raise ToolError("Faylni o'girib bo'lmadi (buzilgan yoki parol bilan himoyalangan)")
        return out.read_bytes()


def ocr_image(img: bytes, lang: str | None = None, timeout: int = 120) -> str:
    """Bitta sahifa rasmi → ishonchli matn qatorlari. Past ishonchli / harfsiz qatorlar (formulalar, jadval chiziqlari) tushib qoladi —
    ularning o'rniga bitta «…» qatori; bunday qism matnda «[jadval / formula — sahifa rasmiga qarang]» bo'lib chiqadi."""
    exe = tesseract(); lang = lang or ocr_lang()
    if not exe or not lang: raise ToolError("Serverda OCR (Tesseract) o'rnatilmagan")
    with tempfile.TemporaryDirectory(prefix="isft-ocr-") as d:
        p = Path(d) / "page.img"; p.write_bytes(img)
        try:
            r = subprocess.run([exe, str(p), "-", "-l", lang, "--psm", "6", "tsv"], capture_output=True, text=True, timeout=timeout, env=_tess_env())
        except subprocess.TimeoutExpired:
            raise ToolError("OCR juda uzoq davom etdi")
        except OSError as e:
            raise ToolError(f"Tesseract ishga tushmadi ({e})")
    if r.returncode != 0: raise ToolError("OCR xatosi")
    lines: dict = {}
    for row in csv.DictReader(io.StringIO(r.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not (row.get("text") or "").strip(): continue
        try: conf = float(row["conf"])
        except (TypeError, ValueError): continue
        k = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        lines.setdefault(k, []).append((conf, row["text"]))
    keep: list[str] = []
    for k in sorted(lines):
        ws = lines[k]; txt = " ".join(w for _, w in ws); conf = sum(c for c, _ in ws) / len(ws)
        letters = txt.replace(" ", "")
        alpha = sum(ch.isalpha() for ch in letters) / max(1, len(letters))
        if conf >= 60 and alpha >= 0.6 and (len(ws) >= 2 or (len(txt) >= 3 and conf >= 80)): keep.append(txt)   # sarlavha va qisqa qatorlar ham saqlanadi
        elif keep and keep[-1] != "…": keep.append("…")
    t = "\n".join(keep).replace("`", "ʻ")
    t = re.sub(r"(\n…)+", "\n[jadval / formula — sahifa rasmiga qarang]", t)
    return t.strip("\n…").strip()
