"""AI tutor — matn yordamchilari (app/tutor.py): me'yorlash, o'zak (stem), HTML → matn, bo'laklash, in'ektsiya naqshlari,
javobni tekshirish (har jumla iqtibos qilingan parcha bilan kesishishi shart) va maslahat rejimida javob sizib chiqishini to'sish.

Sof funksiyalar — bazaga murojaat yo'q (testlarda to'g'ridan-to'g'ri chaqiriladi).
"""
from __future__ import annotations
import html as _html, re
from html.parser import HTMLParser

NOT_FOUND = "Bu savolga kurs materialida javob topilmadi."

_APOS = re.compile(r"[ʻʼ‘’`´ʹ]")
STOP = set("""va bilan uchun bu shu u ular bir ham esa yoki lekin ammo chunki agar deb kabi qanday nima nimaga nega qaysi qachon qayerda kim necha nechta
haqida bo'lib bo'ladi bo'lgan bo'lsa edi emas mi mu da dan ga ni ning men sen siz biz menga sizga iltimos ayting aytib tushuntiring tushuntir degani
nedir demak demakdir hisoblanadi ataladi deyiladi tushuniladi qiladi qilish qilinadi beradi ekan ekanini yozing yoz hamda yana juda eng har hech o'z ushbu mana the a an is are of and to in what how why which bo'yicha orqali kerak mumkin""".split())


def norm(s) -> str:
    """Kichik harf, apostrof turlari bitta, kirill → lotin."""
    s = str(s or "")
    try:
        from .dars import translit
        s = translit(s)
    except Exception:
        pass
    return _APOS.sub("'", s.lower())


def words(s) -> list[str]:
    return [w.strip("'") for w in re.findall(r"[a-z0-9'ʻ]+", norm(s)) if w.strip("'")]


def stem(w: str) -> str:
    return w[:6]


def stems(s) -> list[str]:
    return [stem(w) for w in words(s) if w not in STOP and (len(w) >= 3 or w.isdigit())]


# ---------------------------------------------------------------- HTML → matn
class _TX(HTMLParser):
    BLOCK = {"p", "li", "br", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "blockquote", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.skip += 1
        elif tag in self.BLOCK: self.out.append("\n")
        elif tag in ("td", "th"): self.out.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK: self.out.append("\n")

    def handle_data(self, d):
        if not self.skip: self.out.append(d)


def html_text(h) -> str:
    p = _TX()
    try:
        p.feed(str(h or "")); p.close()
    except Exception:
        return re.sub(r"<[^>]*>", " ", str(h or ""))
    t = "".join(p.out)
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\s*\n\s*", "\n", t).strip()


def html_sections(h) -> list[tuple[str, str]]:
    """HTML → [(sarlavha | "", matn)] — h1–h4 sarlavhalari bo'yicha bo'linadi."""
    parts = re.split(r"<h[1-4][^>]*>(.*?)</h[1-4]>", str(h or ""), flags=re.S | re.I)
    out = []
    if html_text(parts[0]): out.append(("", html_text(parts[0])))
    for i in range(1, len(parts), 2):
        t, body = html_text(parts[i]), html_text(parts[i + 1] if i + 1 < len(parts) else "")
        if t or body: out.append((t, body))
    return out


def sentences(t: str) -> list[str]:
    t = re.sub(r"\s+", " ", str(t or "")).strip()
    return [x.strip() for x in re.split(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЎҚҒҲO'G'0-9«\"(])|\n+", t) if x.strip()]


def windows(t: str, max_words: int = 110) -> list[str]:
    """Matn → ~max_words so'zli bo'laklar (jumla chegarasida)."""
    out, cur, n = [], [], 0
    for s in sentences(t):
        k = len(s.split())
        if cur and n + k > max_words:
            out.append(" ".join(cur)); cur, n = [], 0
        cur.append(s); n += k
    if cur: out.append(" ".join(cur))
    return out


# ---------------------------------------------------------------- in'ektsiya va javob so'rash naqshlari
INJ = re.compile(
    r"\b(ignore|disregard|forget|override)\b[^.?!\n]{0,40}\b(instruction|prompt|rule|previous|above)s?"
    r"|system\s*prompt|\byou\s+are\s+now\b|\bact\s+as\b|jailbreak|developer\s+mode|\bDAN\b"
    r"|oldingi\s+(barcha\s+)?(ko'rsatma|buyruq|qoida)|(ko'rsatma|qoida|buyruq)\w*\s+(unut|e'tiborsiz|bekor|buz)"
    r"|\b(siz|sen)\s+endi\b|\bendi\s+(siz|sen)\b|tizim\s+(ko'rsatma|so'rov)|<\s*/?\s*(material|savol|system|topshiriq)\b", re.I)
ANSWER_SEEK = re.compile(r"(to'g'ri\s+)?javob(i|ni|lar|larni)?\s+(qaysi|nima|ayt|ber|yoz|ko'rsat)|qaysi\s+variant|\b[a-f]\s+variant(mi)?\b"
                         r"|javobini\s+(ayt|ber|yoz)|testning\s+javob", re.I)


def injection(s) -> bool:
    return bool(INJ.search(norm(s)))


def strip_injection(text: str) -> tuple[str, int]:
    """Matndan buyruqqa o'xshash jumlalar olib tashlanadi → (toza matn, olib tashlanganlar soni)."""
    keep, n = [], 0
    for s in sentences(text):
        if injection(s): n += 1
        else: keep.append(s)
    return " ".join(keep), n


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
_LONGNUM = re.compile(r"\b\d{5,}\b")


def scrub(text: str, names: list[str] = ()) -> str:
    """Shaxsiy ma'lumot: email, telefon, uzun raqamlar (HEMIS ID) va talabaning o'z ism-familiyasi → belgilar."""
    t = _EMAIL.sub("[email]", str(text or ""))
    t = _PHONE.sub("[telefon]", t)
    t = _LONGNUM.sub("[raqam]", t)
    for n in names or ():
        for part in str(n or "").split():
            if len(part) >= 3: t = re.sub(rf"\b{re.escape(part)}\b", "[ism]", t, flags=re.I)
    return t


# ---------------------------------------------------------------- javobni tekshirish
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_URL = re.compile(r"https?://|www\.|\]\(|<[a-z/!]", re.I)
_EN = {"the", "is", "are", "of", "and", "to", "in", "that", "this", "with", "for", "it", "be", "as", "on", "by"}


def clean_out(s) -> str:
    """Model jumlasi → toza matn: HTML teglar va boshqaruv belgilari olib tashlanadi, kirill → lotin, uzunlik chegarasi."""
    s = _html.unescape(str(s or ""))
    s = re.sub(r"<[^>]*>", " ", s)
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f<>]", " ", s)
    try:
        from .dars import translit
        s = translit(s)
    except Exception:
        pass
    return re.sub(r"\s+", " ", s).strip()[:500]


def english(s) -> bool:
    ws = re.findall(r"[a-z']+", str(s or "").lower())
    return len(ws) >= 4 and sum(w in _EN for w in ws) / len(ws) >= 0.25


def supported(sent: str, texts: list[str], need: float = 0.6) -> bool:
    """Jumla iqtibos qilingan parcha(lar)ga tayanadi: mazmunli o'zaklarning ≥ need ulushi parchada bor va har bir son parchada uchraydi."""
    ss = set(stems(sent))
    if not ss: return False
    cs = set()
    for t in texts: cs |= set(stems(t))
    hit = sum(1 for w in ss if w in cs or (len(w) >= 3 and any(c.startswith(w) or (len(c) >= 3 and w.startswith(c)) for c in cs)))
    if hit / len(ss) < need or (len(ss) >= 3 and hit < 2): return False
    src = {n.replace(",", ".") for t in texts for n in _NUM.findall(t)}
    return all(n.replace(",", ".") in src for n in _NUM.findall(sent))


_LEAK = re.compile(r"to'g'ri\s+(javob|variant)|javob(i)?\s*(:|—|–|-|\bbu\b|\bshu\b)|\bvariant\s*[a-f]\b|(^|\s)[a-f]\s*\)|\b[a-f]\s*-?\s*variant|\bjavobingiz\s+to'g'ri", re.I)
_TF = re.compile(r"\b(to'g'ri|noto'g'ri|rost|yolg'on|xato)\b", re.I)


def leaks(sent: str, item: dict | None) -> bool:
    """Maslahat rejimi: jumla javobni (harf, «to'g'ri javob», javob matni yoki uning mazmuni) oshkor qiladimi."""
    s = norm(sent)
    if _LEAK.search(s): return True
    if not item: return False
    opts = [norm(o) for o in item.get("options") or []]
    if item.get("truefalse") or (len(opts) == 2 and {"to'g'ri", "noto'g'ri"} <= set(o.strip() for o in opts)):
        if _TF.search(s): return True
    ss = set(stems(s))
    def covered(st):      # javob/variant o'zaklari jumlada (qo'shimchalar bilan ham: «foiz» ↔ «foizga»)
        return all(w in ss or any(x.startswith(w) or (len(x) >= 3 and w.startswith(x)) for x in ss) for w in st)
    # to'g'ri javob ham, chalg'ituvchi variantlar ham: variant matnini takrorlash — variantlarni chiqarib tashlashga yordam beradi
    for a in list(item.get("correct") or []) + [o for o in item.get("options") or [] if norm(o).strip() not in ("to'g'ri", "noto'g'ri")]:
        a = norm(a).strip(" .")
        if not a: continue
        if len(a) >= 3 and a in s: return True
        if len(a) < 3 and re.search(rf"(^|[^a-z0-9]){re.escape(a)}([^a-z0-9]|$)", s): return True
        ast = set(stems(a))
        if len(ast) >= 2 and covered(ast): return True
    return False


def verify(data: dict, chunks: dict, mode: str, item: dict | None = None) -> tuple[list[dict], int, str]:
    """Model javobi → (saqlangan jumlalar [{text, cites}], olib tashlanganlar soni, holat).
    chunks: {mahalliy id ("c1") → {"text": ...}}. Har faktik jumla iqtibos qilingan parcha bilan kesishishi shart; maslahat rejimida
    «?» bilan tugaydigan yo'naltiruvchi savollar iqtibossiz ham bo'lishi mumkin, lekin javobni oshkor qilmasligi kerak."""
    st = str((data or {}).get("status") or "")
    raw = (data or {}).get("sentences") if isinstance((data or {}).get("sentences"), list) else []
    kept, dropped = [], 0
    for x in raw[:8]:
        if not isinstance(x, dict): dropped += 1; continue
        t = clean_out(x.get("text"))
        src = [str(c) for c in (x.get("sources") if isinstance(x.get("sources"), list) else []) if str(c) in chunks][:4]
        if not t: continue
        bad = bool(_URL.search(t)) or injection(t) or english(t)
        if not bad and mode == "maslahat" and leaks(t, item): bad = True
        if not bad:
            guiding = mode == "maslahat" and t.endswith("?")
            if not guiding and not (src and supported(t, [chunks[c]["text"] for c in src])): bad = True
        if bad: dropped += 1; continue
        kept.append({"text": t, "cites": src})
    return kept, dropped, st
