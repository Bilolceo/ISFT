"""HEMIS almashinuvi — sof funksiyalar (bazasiz): fayl o'qish, sarlavhalarni tanish (ustun xaritasi), qiymatlarni normallashtirish,
kirill/lotin ism-sharif solishtirish. Batafsil: docs/hemis.md.

HEMIS rasmiy eksport formati hujjatlashtirilmagan (bizda yo'q), shuning uchun o'quvchi «bag'rikeng»:
  * .xlsx (birinchi varaq) yoki .csv (; , yoki TAB; UTF-8 / UTF-8 BOM / cp1251);
  * sarlavha qatori birinchi 15 qator ichidan topiladi (tepada hisobot nomi, sana va h.k. bo'lishi mumkin);
  * sarlavhalar o'zbek (lotin va kirill), rus va ingliz tillarida — normallashtirilib (kirill → lotin, tutuq belgilari, bo'shliqlar
    olib tashlanadi) ALIASES bilan solishtiriladi; topilmaganini foydalanuvchi qo'lda moslaydi va «profil» sifatida saqlaydi;
  * F.I.Sh. bitta ustunda yoki Familiya / Ism / Otasining ismi alohida ustunlarda bo'lishi mumkin;
  * HEMIS ID Excel'da son bo'lib kelishi mumkin (3525966527469.0, 3.525966527469E12) — matnga keltiriladi;
  * JShShIR / pasport ustunlari ATAYLAB o'qilmaydi (bizga kerak emas — shaxsiy ma'lumot bazaga tushmasin).
"""
from __future__ import annotations
import csv, io, re, unicodedata

# =============================================================================================
# Kirill → lotin (o'zbek), tutuq belgilari
# =============================================================================================
APOS = "ʻʼ'`‘’ʹ′´"          # o‘, g‘ va tutuq belgisining turli yozilishi
_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'",
        "ҳ": "h", "і": "i"}
_VOW = set("aeiouаеёиоуэюяўы")


def has_cyr(s: str) -> bool:
    return bool(re.search(r"[Ѐ-ӿ]", s or ""))


def translit(s: str) -> str:
    """O'zbek kirill → lotin (rasmiy jadvalga yaqin): «е» so'z boshida va unlidan keyin — «ye», ц → ts. Lotin matn o'zgarmaydi
    (faqat tutuq belgilari bitta «'» ga keltiriladi)."""
    s = unicodedata.normalize("NFC", str(s or ""))
    out, prev = [], ""
    for ch in s:
        lo = ch.lower()
        if lo in _CYR:
            t = _CYR[lo]
            if lo == "е" and (not prev or not prev.isalpha() or prev.lower() in _VOW): t = "ye"
            if ch.isupper() and t: t = t[0].upper() + t[1:]
            out.append(t)
        elif ch in APOS:
            out.append("'")
        else:
            out.append(ch)
        prev = ch
    return "".join(out)


def clean_spaces(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace(" ", " ")).strip()


def display_name(s) -> str:
    """Ko'rsatish uchun: lotinga o'tkazilgan, bo'shliqlari tozalangan, tutuq belgisi bitta «'»."""
    return clean_spaces(translit(s))


_PATRO = {"ogli": "ogli", "ugli": "ogli", "ogly": "ogli", "oglu": "ogli", "qizi": "kizi", "kizi": "kizi", "kyzy": "kizi", "kizi'": "kizi"}


def name_key(s) -> str:
    """Ism-sharifni SOLISHTIRISH kaliti (kirill/lotin, rus va o'zbek imlosi farqlariga chidamli):
    kirill → lotin; kichik harf; tutuq belgilari olib tashlanadi (o'/g' → o/g); ҳ/х → x (rus kirillida «Х» = o'zbek «H»), қ/q → k;
    «ye» → «e», «yo» → «e», «ts» → «s», ikki harf → bitta; o'g'li/угли/оглы → ogli; so'zlar tartibi ahamiyatsiz (Familiya Ism ↔ Ism Familiya).
    Bir xil kalit — bitta odam (faqat yozuv farqi), farqli kalit — haqiqiy farq (Farqlar navbatiga)."""
    t = translit(s).lower()
    t = re.sub(r"[" + re.escape(APOS) + r"\-.,]", "", t)
    t = t.replace("sh", "\x01").replace("ch", "\x02").replace("h", "x").replace("\x01", "sh").replace("\x02", "ch").replace("q", "k").replace("ye", "e").replace("yo", "e").replace("ts", "s")
    t = re.sub(r"(.)\1+", r"\1", t)
    words = [_PATRO.get(w, w) for w in re.findall(r"[a-z]+", t)]
    return " ".join(sorted(w for w in words if w))


def norm_header(s) -> str:
    t = translit(s).lower()
    t = t.replace("№", "n").replace("#", "n")
    return re.sub(r"[^a-z0-9]", "", t)


# =============================================================================================
# Maydonlar va sarlavha variantlari (o'zbek lotin/kirill, rus, ingliz)
# =============================================================================================
ENTITIES = {
    "students": "Talabalar", "groups": "Guruhlar", "teachers": "O'qituvchilar va xodimlar", "load": "O'quv yuklamasi", "grades": "Baholar",
}
FIELDS = {   # maydon: (nomi, majburiymi)
    "students": {"hemis_id": ("HEMIS ID", 1), "full_name": ("F.I.Sh.", 1), "last_name": ("Familiya", 0), "first_name": ("Ism", 0),
                 "middle_name": ("Otasining ismi", 0), "group": ("Guruh", 1), "direction": ("Yo'nalish", 0), "course": ("Kurs", 0),
                 "study_form": ("Ta'lim shakli", 0), "status": ("Holat", 0), "citizenship": ("Fuqarolik", 0), "level": ("Ta'lim bosqichi", 0),
                 "payment_type": ("To'lov shakli", 0), "faculty": ("Fakultet", 0)},
    "groups": {"hemis_id": ("Guruh HEMIS ID", 0), "group": ("Guruh", 1), "direction": ("Yo'nalish", 0), "course": ("Kurs", 0),
               "study_form": ("Ta'lim shakli", 0), "level": ("Ta'lim bosqichi", 0), "faculty": ("Fakultet", 0)},
    "teachers": {"hemis_id": ("Xodim HEMIS ID", 0), "full_name": ("F.I.Sh.", 1), "last_name": ("Familiya", 0), "first_name": ("Ism", 0),
                 "middle_name": ("Otasining ismi", 0), "department": ("Kafedra", 0), "position": ("Lavozim", 0), "degree": ("Ilmiy daraja", 0)},
    "load": {"teacher_hemis_id": ("O'qituvchi HEMIS ID", 0), "teacher": ("O'qituvchi", 0), "group": ("Guruh", 1), "subject": ("Fan", 1),
             "hours": ("Soat", 0), "training": ("Mashg'ulot turi", 0)},
    "grades": {"hemis_id": ("Talaba HEMIS ID", 1), "full_name": ("F.I.Sh.", 0), "subject": ("Fan", 1), "semester": ("Semestr", 1),
               "score": ("Ball", 1)},
}
REQUIRED_ANY = {"students": [("full_name", "last_name")], "teachers": [("full_name", "last_name")], "load": [("teacher", "teacher_hemis_id")]}

ALIASES = {
    "hemis_id": ["hemis id", "hemis_id", "hemis", "id", "talaba id", "talaba idsi", "talaba identifikatori", "student id", "id talaba",
                 "hemis identifikator", "ид", "ид студента", "идентификатор", "hemis raqami", "talaba hemis id", "xodim id", "xodim hemis id",
                 "guruh id", "guruh hemis id", "group id", "ид группы", "ид сотрудника", "employee id", "ҳемис ид", "талаба ид"],
    "teacher_hemis_id": ["oqituvchi id", "o'qituvchi hemis id", "oqituvchi hemis id", "xodim id", "ид преподавателя", "teacher id",
                         "ўқитувчи ид"],
    "full_name": ["f.i.sh", "f.i.sh.", "fish", "f i sh", "familiya ism sharif", "familiya ismi sharifi", "familiyasi ismi otasining ismi",
                  "talaba", "talaba fish", "talabaning f.i.sh.", "ф.и.ш.", "фиш", "ф.и.о.", "фио", "full name", "name", "фамилия имя отчество",
                  "xodim", "xodim fish", "o'qituvchi fish", "оқитувчи", "talaba f.i.sh.", "ism-sharif", "ism sharif"],
    "last_name": ["familiya", "familiyasi", "фамилия", "фамилияси", "last name", "surname"],
    "first_name": ["ism", "ismi", "имя", "исм", "исми", "first name"],
    "middle_name": ["otasining ismi", "sharifi", "sharif", "отчество", "отасининг исми", "middle name", "patronymic"],
    "group": ["guruh", "guruhi", "guruh nomi", "group", "группа", "гуруҳ", "гуруҳи", "akademik guruh", "академическая группа"],
    "direction": ["yo'nalish", "yonalish", "ta'lim yo'nalishi", "ta'lim yonalishi", "mutaxassislik", "направление", "направление подготовки",
                  "специальность", "йўналиш", "таълим йўналиши", "мутахассислик", "specialty", "speciality", "program"],
    "course": ["kurs", "курс", "bosqich", "o'quv kursi", "course", "year", "kursi"],
    "study_form": ["ta'lim shakli", "talim shakli", "o'qish shakli", "oqish shakli", "форма обучения", "таълим шакли", "shakl",
                   "education form", "study form", "form"],
    "status": ["holat", "holati", "talaba holati", "status", "статус", "ҳолат", "ҳолати", "состояние", "student status"],
    "citizenship": ["fuqarolik", "fuqaroligi", "гражданство", "фуқаролик", "фуқаролиги", "citizenship", "davlat", "mamlakat", "страна"],
    "level": ["ta'lim bosqichi", "talim bosqichi", "ta'lim turi", "daraja", "уровень", "уровень образования", "таълим босқичи",
              "education type", "level"],
    "payment_type": ["to'lov shakli", "tolov shakli", "to'lov turi", "форма оплаты", "тўлов шакли", "payment", "payment type",
                     "moliyalashtirish manbai"],
    "faculty": ["fakultet", "факультет", "faculty"],
    "department": ["kafedra", "кафедра", "bo'linma", "структурное подразделение", "подразделение", "department"],
    "position": ["lavozim", "lavozimi", "должность", "лавозим", "position"],
    "degree": ["ilmiy daraja", "ilmiy darajasi", "учёная степень", "ученая степень", "илмий даража", "degree", "academic degree"],
    "teacher": ["o'qituvchi", "oqituvchi", "преподаватель", "ўқитувчи", "teacher", "o'qituvchi f.i.sh.", "ф.и.о. преподавателя"],
    "subject": ["fan", "fan nomi", "fanlar", "дисциплина", "предмет", "фан", "фан номи", "subject", "course name", "o'quv fani"],
    "hours": ["soat", "soatlar", "yuklama", "yuklama soati", "часы", "кол-во часов", "соат", "hours", "auditoriya soati", "jami soat"],
    "training": ["mashg'ulot turi", "mashgulot turi", "вид занятия", "машғулот тури", "training type"],
    "semester": ["semestr", "семестр", "semester", "семестр обучения"],
    "score": ["ball", "baho", "балл", "оценка", "балл итого", "jami ball", "umumiy ball", "score", "grade", "yakuniy ball"],
}
# o'qilmaydigan (shaxsiy) ustunlar — foydalanuvchiga ko'rsatiladi
IGNORED = ["jshshir", "pinfl", "пинфл", "жшшир", "pasport", "passport", "паспорт", "pasport seriyasi", "telefon", "телефон", "phone",
           "manzil", "адрес", "address", "tug'ilgan sana", "дата рождения", "birth date"]
_ALIAS_N = {norm_header(a): f for f, al in ALIASES.items() for a in al}
_IGN_N = {norm_header(a) for a in IGNORED}
# sarlavha ichida shu bo'laklar bo'lsa ham — shaxsiy ustun («Telefon raqami», «Tug'ilgan sanasi», «Yashash manzili», «E-mail», «Адрес проживания»)
_PII_PARTS = ("jshshir", "pinfl", "pasport", "passport", "telefon", "phone", "manzil", "adres", "address", "tugilgan", "birth", "rojden",
              "email", "pochta")


def is_pii(n: str) -> bool:
    """n — norm_header() natijasi."""
    return bool(n) and (n in _IGN_N or any(x in n for x in _PII_PARTS))


def auto_map(headers: list[str], entity: str, profile: dict | None = None) -> dict:
    """Sarlavhalar → maydonlar. Profil (saqlangan xarita: normallashgan sarlavha → maydon) birinchi, keyin variantlar ro'yxati.
    Qaytaradi: {"map": {ustun_indeksi: maydon}, "unmapped": [...], "ignored": [...], "missing": [...]}"""
    fields = FIELDS[entity]
    prof = {norm_header(k): v for k, v in (profile or {}).items()}
    used, m, unmapped, ignored = set(), {}, [], []
    for i, h in enumerate(headers):
        n = norm_header(h)
        if not n: continue
        f = prof.get(n)
        if f is None:
            f = _ALIAS_N.get(n)
            if f in ("hemis_id",) and entity == "load": f = "teacher_hemis_id"
            if f == "teacher" and entity in ("students", "teachers", "grades"): f = None
            if f == "teacher_hemis_id" and entity != "load": f = "hemis_id"
        if f == "":                       # profilda «e'tiborsiz» deb belgilangan
            ignored.append(h); continue
        if is_pii(n):
            ignored.append(h); continue
        if f and f in fields and f not in used:
            m[i] = f; used.add(f)
        else:
            unmapped.append(h)
    return {"map": m, "unmapped": unmapped, "ignored": ignored, "missing": missing_fields(entity, set(m.values()))}


def pii_cols(headers: list[str]) -> set[int]:
    """Shaxsiy ma'lumot ustunlari (JShShIR, pasport, telefon, manzil, tug'ilgan sana) — bazaga hatto ko'rib chiqish uchun ham yozilmaydi."""
    out = set()
    for i, h in enumerate(headers):
        if is_pii(norm_header(h)): out.add(i)
    return out


def strip_pii(rows: list[list[str]], header: int | None = None, scan: int = 15) -> list[list[str]]:
    """Sarlavha bo'lishi mumkin bo'lgan har bir qatordagi (birinchi `scan` qator) shaxsiy ustunlar — undan keyingi barcha qatorlarda
    bo'shatiladi. Keyin ustun xaritasi o'zgarib sarlavha boshqa qatorga ko'chsa ham, shaxsiy qiymat bazada qolmaydi."""
    out = [list(r) for r in rows]
    for i, r in enumerate(rows[:scan]):
        if i != header and header_score(r) < 2: continue          # ma'lumot qatori (masalan, ism «Manzila») sarlavha deb olinmaydi
        cols = pii_cols(r)
        if not cols: continue
        for j in range(i + 1, len(out)):
            out[j] = ["" if k in cols else v for k, v in enumerate(out[j])]
    return out


def missing_fields(entity: str, have: set) -> list[str]:
    out = []
    for f, (_, req) in FIELDS[entity].items():
        if not req or f in have: continue
        alts = [g for grp in REQUIRED_ANY.get(entity, []) if f in grp for g in grp]
        if alts and any(a in have for a in alts): continue
        out.append(f)
    return out


def header_score(cells) -> int:
    return sum(1 for c in cells if norm_header(c) in _ALIAS_N)


# =============================================================================================
# Fayl o'qish
# =============================================================================================
MAX_BYTES = 25 * 1024 * 1024
MAX_ROWS = 100_000
MAX_COLS = 300                         # varaqdagi soxta o'lcham (A1:XFD1048576) har qatorni 16 384 katakka to'ldirmasin
MAX_UNZIPPED = 200 * 1024 * 1024       # .xlsx ichidagi fayllar jami (zip bomba)
MAX_ENTRIES = 2000


class ReadError(ValueError):
    pass


def _cell(v) -> str:
    if v is None: return ""
    if isinstance(v, float):
        if v.is_integer(): return str(int(v))
        return repr(v)
    if hasattr(v, "isoformat"): return v.isoformat()[:10]
    return clean_spaces(v)


def read_rows(raw: bytes, name: str) -> list[list[str]]:
    """Xom qatorlar (matn). .xlsx — birinchi varaq; .csv/.txt — ajratgich avtomatik."""
    if len(raw) > MAX_BYTES: raise ReadError("Fayl 25 MB dan katta")
    low = (name or "").lower()
    if low.endswith(".xls"): raise ReadError("Eski .xls formati qabul qilinmaydi — HEMIS'dan .xlsx yoki .csv qilib eksport qiling")
    if low.endswith(".xlsx") or raw[:2] == b"PK":
        try:
            import openpyxl, zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                inf = z.infolist()
                if len(inf) > MAX_ENTRIES or sum(i.file_size for i in inf) > MAX_UNZIPPED:
                    raise ReadError("XLSX fayl ochilganda juda katta (siqilgan ma'lumot chegaradan oshdi)")
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            ws = wb.worksheets[0]
            out = []
            for r in ws.iter_rows(values_only=True, max_col=MAX_COLS):
                out.append([_cell(v) for v in r])
                if len(out) > MAX_ROWS + 20: raise ReadError(f"Qatorlar {MAX_ROWS} tadan ko'p")
            wb.close()
            return out
        except ReadError: raise
        except Exception as e:
            raise ReadError(f"XLSX faylni o'qib bo'lmadi: {str(e)[:120]}")
    try: txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError: txt = raw.decode("cp1251", errors="replace")
    first = "\n".join(txt.splitlines()[:20])
    delim = max([";", ",", "\t"], key=lambda d: first.count(d))
    out = [[clean_spaces(c) for c in r] for r in csv.reader(io.StringIO(txt), delimiter=delim)]
    if len(out) > MAX_ROWS + 20: raise ReadError(f"Qatorlar {MAX_ROWS} tadan ko'p")
    return out


def find_header(rows: list[list[str]], entity: str, profile: dict | None = None) -> int:
    """Sarlavha qatori: birinchi 15 qatordan eng ko'p maydon taniladigani (kamida 2)."""
    best, bi = 0, -1
    for i, r in enumerate(rows[:15]):
        s = len(auto_map(r, entity, profile)["map"])
        if s > best: best, bi = s, i
    if best < 2: raise ReadError("Sarlavha qatori topilmadi: ustun nomlari tanilmadi (kamida 2 ta). Ustunlarni qo'lda moslang yoki profil tanlang.")
    return bi


def parse(raw: bytes, name: str, entity: str, profile: dict | None = None, mapping: dict | None = None) -> dict:
    """Fayl → {headers, header_row, map, unmapped, ignored, missing, records: [{maydon: qiymat, "_row": n}]}.
    mapping — foydalanuvchi qo'lda bergan {sarlavha: maydon | ""} (profilning ustiga)."""
    if entity not in FIELDS: raise ReadError("Noma'lum tur")
    return parse_rows(read_rows(raw, name), entity, profile, mapping)


def parse_rows(rows: list[list[str]], entity: str, profile: dict | None = None, mapping: dict | None = None) -> dict:
    """Xom qatorlardan (read_rows) — parse() bilan bir xil natija (qayta moslashda fayl qayta o'qilmaydi)."""
    if not rows: raise ReadError("Fayl bo'sh")
    prof = {**(profile or {}), **(mapping or {})}
    hi = find_header(rows, entity, prof)
    headers = rows[hi]
    am = auto_map(headers, entity, prof)
    recs = []
    for n, r in enumerate(rows[hi + 1:], start=hi + 2):
        if not any(c for c in r): continue
        rec = {"_row": n}
        for i, f in am["map"].items():
            rec[f] = r[i] if i < len(r) else ""
        if "full_name" not in rec and any(k in rec for k in ("last_name", "first_name")):
            rec["full_name"] = clean_spaces(" ".join(rec.get(k, "") for k in ("last_name", "first_name", "middle_name")))
        if all(not v for k, v in rec.items() if k != "_row"): continue
        recs.append(rec)
    if len(recs) > MAX_ROWS: raise ReadError(f"Qatorlar {MAX_ROWS} tadan ko'p")
    return {"headers": headers, "header_row": hi + 1, "map": {headers[i]: f for i, f in am["map"].items()}, "unmapped": am["unmapped"],
            "ignored": am["ignored"], "missing": am["missing"], "records": recs}


# =============================================================================================
# Qiymatlarni normallashtirish (HEMIS yozuvi → ISFT Core qiymati)
# =============================================================================================
def hemis_id(v) -> str:
    s = clean_spaces(v).replace(" ", "")
    if re.fullmatch(r"\d+(\.0+)?", s): return s.split(".")[0]
    m = re.fullmatch(r"(\d)(?:\.(\d+))?[eE]\+?(\d+)", s)           # 3.525966527469E12
    if m:
        digits = m.group(1) + (m.group(2) or ""); exp = int(m.group(3))
        if exp >= len(digits) - 1: return digits + "0" * (exp - len(digits) + 1)
    return s


def group_key(v) -> str:
    return re.sub(r"[\s_]+", "", translit(v).upper()).replace("—", "-").replace("–", "-")


def subject_key(v) -> str:
    return re.sub(r"[^a-z0-9]", "", translit(v).lower().replace("'", ""))


def course(v) -> int | None:
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else None


def _k(v) -> str:
    return re.sub(r"[^a-z]", "", translit(v).lower().replace("'", ""))


FORMS = {"kunduzgi": "kunduzgi", "ochnaya": "kunduzgi", "ochnaa": "kunduzgi", "fulltime": "kunduzgi", "kunduzi": "kunduzgi",
         "sirtqi": "sirtqi", "zaochnaya": "sirtqi", "parttime": "sirtqi", "sirtki": "sirtqi",
         "masofaviy": "masofaviy", "masofaviytalim": "masofaviy", "distansionnaya": "masofaviy", "distantsionnaya": "masofaviy",
         "distance": "masofaviy", "onlayn": "masofaviy", "masofadan": "masofaviy",
         "kechki": "kechki", "vechernyaya": "kechki", "evening": "kechki", "ikkinchioliy": "ikkinchi oliy", "maxsussirtqi": "sirtqi"}
STATUSES = {"oqimoqda": "faol", "obuchayetsya": "faol", "faol": "faol", "obuchaetsya": "faol", "active": "faol", "talaba": "faol", "oqiydi": "faol",
            "akademiktatil": "akademik ta'til", "akademtatil": "akademik ta'til", "akademicheskiyotpusk": "akademik ta'til",
            "akademotpusk": "akademik ta'til", "academicleave": "akademik ta'til",
            "chetlashtirilgan": "chetlashtirilgan", "chetlashtirildi": "chetlashtirilgan", "otchislen": "chetlashtirilgan",
            "expelled": "chetlashtirilgan", "safdanchiqarilgan": "chetlashtirilgan",
            "bitirgan": "bitirgan", "bitiruvchi": "bitirgan", "vipusknik": "bitirgan", "vypusknik": "bitirgan", "graduated": "bitirgan",
            "kochirilgan": "ko'chirilgan", "perevedyon": "ko'chirilgan", "pereveden": "ko'chirilgan", "transferred": "ko'chirilgan"}
LEVELS = {"bakalavr": "bakalavr", "bakalavriat": "bakalavr", "bachelor": "bakalavr", "magistr": "magistr", "magistratura": "magistr",
          "magistrant": "magistr", "master": "magistr"}
PAYMENTS = {"grant": "grant", "davlatgranti": "grant", "byudjet": "grant", "budjet": "grant", "budget": "grant",
            "kontrakt": "kontrakt", "tolovkontrakt": "kontrakt", "tolovshartnoma": "kontrakt", "platnoe": "kontrakt", "kontraktasosida": "kontrakt",
            "contract": "kontrakt"}
COUNTRY_ISO = {"uzbekiston": "UZ", "ozbekiston": "UZ", "ozbekistonrespublikasi": "UZ", "ozbekistonrespublikasifukarosi": "UZ",
               "ozbekistonfukarosi": "UZ", "uzbekistan": "UZ", "respublikauzbekistan": "UZ", "grajdaninruz": "UZ", "grajdaninuzbekistana": "UZ",
               "uz": "UZ", "uzb": "UZ", "qozogiston": "KZ", "qirgiziston": "KG", "kazakstan": "KZ", "kazaxstan": "KZ", "kazakhstan": "KZ", "kz": "KZ", "tojikiston": "TJ", "tadjikistan": "TJ",
               "tajikistan": "TJ", "tj": "TJ", "kirgiziston": "KG", "kirgizstan": "KG", "kyrgyzstan": "KG", "kg": "KG", "turkmaniston": "TM",
               "turkmenistan": "TM", "tm": "TM", "afgoniston": "AF", "afganistan": "AF", "afghanistan": "AF", "af": "AF", "rossiya": "RU",
               "russia": "RU", "rossiyskayafederatsiya": "RU", "ru": "RU", "turkiya": "TR", "turtsiya": "TR", "turkey": "TR", "tr": "TR",
               "koreya": "KR", "koreyarespublikasi": "KR", "koreya respublikasi": "KR", "korea": "KR", "kr": "KR", "hindiston": "IN",
               "xindiston": "IN", "india": "IN", "indiya": "IN", "in": "IN", "xitoy": "CN", "kitay": "CN", "china": "CN", "cn": "CN",
               "fukaroligiyokshaxs": "NONE", "fuqaroligiyoqshaxs": "NONE", "bezgrajdanstva": "NONE", "litsobezgrajdanstva": "NONE",
               "stateless": "NONE"}


def form(v) -> str | None:
    k = _k(v)
    if not k: return None
    if k in FORMS: return FORMS[k]
    for a, b in FORMS.items():
        if k.startswith(a): return b
    return None


def status(v) -> str | None:
    k = _k(v)
    if not k: return None
    if k in STATUSES: return STATUSES[k]
    for a, b in STATUSES.items():
        if a in k: return b
    return None


def level(v) -> str | None:
    k = _k(v)
    if not k: return None
    for a, b in LEVELS.items():
        if k.startswith(a): return b
    return None


def payment(v) -> str | None:
    k = _k(v)
    if not k: return None
    for a, b in PAYMENTS.items():
        if k.startswith(a): return b
    return None


def citizenship(v) -> str | None:
    """«O'zbekiston Respublikasi fuqarosi» / «Гражданин РУз» / «UZ» → UZ; «Xorijiy fuqaro» (davlatsiz) — tanilmaydi (None, xato sifatida)."""
    raw = clean_spaces(v)
    if not raw: return None
    if re.fullmatch(r"[A-Za-z]{2}", raw): return raw.upper()
    k = _k(raw).replace("fuq", "fuk")
    if k in COUNTRY_ISO: return COUNTRY_ISO[k]
    for a, b in COUNTRY_ISO.items():
        if len(a) > 3 and k.startswith(a): return b
    if "ozbekiston" in k or "uzbekistan" in k or "ruz" == k[-3:]: return "UZ"
    if "xorij" in k or "inostran" in k or "foreign" in k: return "XX"        # xorijiy fuqaro, davlati ko'rsatilmagan
    return None


def score(v) -> float | None:
    s = clean_spaces(v).replace(",", ".")
    try: x = float(s)
    except ValueError: return None
    return x if 0 <= x <= 100 else None
