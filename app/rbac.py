"""ISFT Core yadrosi: lavozimga asoslangan ruxsat nazorati (RBAC) va audit jurnali.
Har bir ma'lumot so'rovi shu yerdan o'tadi. Taklifnomaning 4-bo'limidagi jadval aynan shu yerda kodlangan."""
import datetime as dt, hashlib, hmac, os
from dataclasses import dataclass
from . import db

# Resurslar (ma'lumot turlari)
KPI = "kpi"                      # jamlangan umumiy ko'rsatkichlar
ACADEMIC = "academic"            # o'zlashtirish, davomat (jamlangan)
STUDENTS = "students"            # individual talaba kartochkalari
CONTRACTS = "contracts"          # kontrakt to'lovlari
FINANCE = "finance"              # byudjet, xarajatlar
PAYROLL = "payroll"              # ish haqi
HR = "hr"                        # xodimlar shaxsiy ma'lumoti
SCIENCE = "science"              # nashrlar, grantlar
INTL = "international"           # xalqaro hamkorlik
ADMISSIONS = "admissions"        # qabul
YOUTH = "youth"                  # tadbirlar, yotoqxona, murojaatlar
MASTERS = "masters"              # magistratura
TASKS = "tasks"                  # majlis topshiriqlari
AUDIT = "audit"                  # audit jurnali
REPORTS = "reports"              # rasmiy hisobot generatsiyasi
FACILITIES = "facilities"        # xona QR nosozliklari (xo'jalik)
REQUESTS = "requests"            # yagona murojaat kartasi va hodisalar
SPACES = "spaces"                # auditoriyalar bandligi (kamera — faqat son)
OPS = "ops"                      # talabalar bilan ishlash markazi (holatlar, call-markaz, otrabotka)
RATING = "rating"                # o'zlashtirish reytingi (app/reyting.py) — kirish moduldagi jadval bo'yicha, audit shu resursda
CHANCERY = "chancery"            # devonxona: buyruqlar reyestri (o'qish), jurnalga ro'yxatga olish, chiquvchi yozishmalar (app/orders.py)
PROCUREMENT = "procurement"      # xarid so'rovlari: xo'jalik nosozligidan xarid (app/service.py)
FLOWS = "flows"                  # talaba harakati: sessiya jadvali, apellyatsiya, qayta o'qish, ko'chirish, ISFT granti, bitiruv (app/academic_flows.py) — kirish moduldagi jadval bo'yicha

LABELS = {KPI: "Umumiy KPI", ACADEMIC: "O'zlashtirish va davomat", STUDENTS: "Talabalar kartochkasi", CONTRACTS: "Kontrakt to'lovlari",
          FINANCE: "Byudjet va xarajatlar", PAYROLL: "Ish haqi", HR: "Kadrlar shaxsiy ma'lumoti", SCIENCE: "Ilmiy faoliyat",
          INTL: "Xalqaro hamkorlik", ADMISSIONS: "Qabul", YOUTH: "Yoshlar va yotoqxona", MASTERS: "Magistratura",
          TASKS: "Majlis topshiriqlari", AUDIT: "Audit jurnali", REPORTS: "Hisobotlar",
          FACILITIES: "Xo'jalik nosozliklari", OPS: "Talabalar markazi", REQUESTS: "Murojaatlar va hodisalar", SPACES: "Auditoriyalar bandligi",
          RATING: "O'zlashtirish reytingi", CHANCERY: "Devonxona: buyruqlar reyestri va chiquvchi yozishmalar", PROCUREMENT: "Xarid so'rovlari",
          FLOWS: "Talaba harakati: sessiya, apellyatsiya, ko'chirish, ISFT granti, bitiruv"}

@dataclass(frozen=True)
class Role:
    key: str
    title: str
    level: int
    allow: frozenset
    scope: str = "institut"      # institut | fakultet | kafedra | o'qituvchi
    aggregate_only: frozenset = frozenset()   # faqat jamlangan ko'rinishda
    local_only: bool = False     # Telegram'ga chiqmaydi
    deny_note: str = ""
    legacy: bool = False         # bekor qilingan lavozim: hech qanday ruxsat yo'q, faqat eski yozuvlarni ko'rsatish uchun

def R(*a): return frozenset(a)

ROLES = {r.key: r for r in [
    Role("kengash", "Kuzatuv kengashi", 1, R(KPI, ACADEMIC, FINANCE, CONTRACTS, SCIENCE, INTL, ADMISSIONS, TASKS, REPORTS, SPACES),
         aggregate_only=R(ACADEMIC, FINANCE, CONTRACTS), deny_note="Shaxsiy ma'lumotlar va kunlik operativ tafsilotlar"),
    Role("rektor", "Rektor", 1, R(KPI, ACADEMIC, STUDENTS, CONTRACTS, FINANCE, PAYROLL, SCIENCE, INTL, ADMISSIONS, YOUTH, MASTERS, TASKS, AUDIT, REPORTS, FACILITIES, REQUESTS, SPACES, OPS),
         aggregate_only=R(STUDENTS, PAYROLL, OPS), deny_note="Xom hujjatlar, individual kartochkalar (maxsus so'rovsiz), xodimlar shaxsiy ma'lumoti"),
    Role("prorektor_oquv", "O'quv ishlari bo'yicha prorektor", 2, R(KPI, ACADEMIC, STUDENTS, ADMISSIONS, MASTERS, TASKS, REPORTS, REQUESTS, SPACES, OPS),
         deny_note="Moliyaviy hisobotlar, xodimlar maoshi"),
    Role("prorektor_ilmiy", "Ilmiy ishlar va innovatsiyalar bo'yicha prorektor", 2, R(KPI, SCIENCE, INTL, MASTERS, TASKS, REPORTS),
         deny_note="Talaba baholari, moliyaviy tafsilotlar"),
    # tuzilma (04.09.2024): Buxgalteriya, Xarid, Marketing, Xo'jalik va texnik bo'lim — moliya-iqtisod prorektori kuratorligida
    Role("prorektor_moliya", "Moliya-iqtisod ishlari bo'yicha prorektor", 2, R(KPI, FINANCE, CONTRACTS, PAYROLL, TASKS, REPORTS, FACILITIES, SPACES, ADMISSIONS, PROCUREMENT),
         aggregate_only=R(PAYROLL), deny_note="Talaba baholari, ilmiy faoliyat tafsilotlari"),
    # tadbirlar (Majlislar zali to'lishi — kamera signali shu yerga keladi) va talabalar bilan ishlash — jamlangan ko'rinishda
    Role("prorektor_yoshlar", "Yoshlar masalalari va ma'naviy-ma'rifiy ishlar bo'yicha birinchi prorektor", 2, R(KPI, YOUTH, TASKS, FACILITIES, SPACES, OPS, REPORTS),
         aggregate_only=R(OPS), deny_note="Moliyaviy ma'lumot, individual o'quv baholari"),
    Role("qabul", "Qabul komissiyasi", 3, R(ADMISSIONS, CONTRACTS, TASKS), aggregate_only=R(CONTRACTS)),
    Role("talabalar", "Registrator ofisi", 3, R(STUDENTS, CONTRACTS, ACADEMIC, TASKS, REQUESTS, YOUTH, OPS)),
    Role("akademik", "Akademik faoliyatni boshqarish bo'limi", 3, R(ACADEMIC, STUDENTS, TASKS, REQUESTS, OPS, SPACES),   # dars jadvali → auditoriyalar fondi
         deny_note="Moliya va kadrlar ma'lumoti"),
    # Sirtqi bo'lim va Ma'lumotlar bazasi bo'limi — vazifalari app/academic_rules.py (DUTIES) da
    Role("sirtqi", "Sirtqi bo'lim", 3, R(ACADEMIC, STUDENTS, TASKS, REQUESTS, OPS), deny_note="Moliya va kadrlar ma'lumoti, institut kontrakt jamlanmasi · Talabalar markazi — faqat sirtqi talabalar (registrator vazifalari; kontrakt — o'qish)"),
    Role("malumotlar_bazasi", "Ma'lumotlar bazasi bo'limi", 3, R(KPI, ACADEMIC, STUDENTS, TASKS),
         deny_note="Moliya, kontrakt va kadrlar ma'lumoti"),
    Role("imtihon", "Imtihon bo'limi", 3, R(ACADEMIC, STUDENTS, TASKS, OPS), deny_note="Moliya, kontrakt va kadrlar ma'lumoti · Talabalar markazi — o'zlashtirish va otrabotka"),
    Role("amaliyot", "Amaliyot bo'limi", 3, R(STUDENTS, TASKS), deny_note="Baholar tafsiloti, moliya va kadrlar ma'lumoti"),
    Role("magistratura", "Magistratura bo'limi", 3, R(MASTERS, TASKS)),
    Role("xalqaro", "Xalqaro hamkorlik bo'limi", 3, R(INTL, TASKS)),
    Role("buxgalteriya", "Buxgalteriya bo'limi", 3, R(FINANCE, CONTRACTS, PAYROLL, TASKS, OPS), local_only=True,
         deny_note="Talabalar markazi — faqat kontrakt holatlari (baholar va davomatsiz)"),
    Role("kadrlar", "Kadrlar bo'limi", 3, R(HR, TASKS), local_only=True),
    Role("xojalik", "Xo'jalik va texnik bo'lim", 3, R(FACILITIES, TASKS, SPACES, PROCUREMENT), deny_note="Talabalar, moliya va kadrlar ma'lumoti"),
    Role("ilmiy_bolim", "Ilmiy tadqiqotlar, innovatsiyalar va ilmiy-pedagogik kadrlar tayyorlash bo'limi", 3, R(SCIENCE, MASTERS, TASKS),
         deny_note="Talaba baholari, moliya va kadrlar ma'lumoti"),
    Role("kotib", "Rektorat kotibi", 1, R(TASKS), deny_note="Talabalar, moliya va kadrlar ma'lumoti — kotib faqat majlis materiallari bilan ishlaydi"),
    Role("it_head", "Axborot texnologiyalari bo'limi boshlig'i", 3, R(TASKS, REQUESTS, SPACES), deny_note="Talabalar baholari, moliya va kadrlar ma'lumoti · kameralar — faqat texnik holat"),
    # murojaatlar — faqat AT bo'limi navbati va o'ziga biriktirilganlari (app/service.py UNIT_ONLY); umumiy hodisa xabarini yubormaydi
    Role("it_staff", "Axborot texnologiyalari bo'limi muhandisi", 3, R(TASKS, REQUESTS),
         deny_note="Faqat o'ziga biriktirilgan topshiriqlar · murojaatlar — AT bo'limi navbati va o'ziga biriktirilganlari"),
    # Registrator ofisi oddiy xodimi (bo'lim a'zosi, rahbar emas — app/directives.py demo akkaunti)
    Role("registrator_xodim", "Registrator ofisi xodimi", 3, R(STUDENTS, ACADEMIC, TASKS, OPS),
         deny_note="Moliya va kadrlar ma'lumoti · topshiriqlar — faqat o'ziga berilganlari"),
    Role("call_center", "Call-markaz operatori", 3, R(OPS), deny_note="Faqat o'z qo'ng'iroqlar navbati: talaba ismi, telefon va suhbat skripti"),
    # Tashkiliy tuzilmadagi (04.09.2024) qolgan bo'limlar — asosan Portal (bo'limlararo xat) va majlis topshiriqlari uchun; eng kam ruxsat tamoyili
    Role("strategik", "Strategik bo'lim", 3, R(KPI, REPORTS, TASKS), deny_note="Shaxsiy ma'lumotlar, moliya va kadrlar tafsiloti"),
    Role("sifat", "Sifatni ta'minlash boshqarmasi", 3, R(KPI, ACADEMIC, REPORTS, TASKS), aggregate_only=R(ACADEMIC),
         deny_note="Talabalar shaxsiy ma'lumoti, moliya va kadrlar tafsiloti — faqat jamlangan ko'rsatkichlar"),
    # shartnomalar ekspertizasi: xalqaro/hamkorlik shartnomalari reyestri (faqat o'qish) va «Tarjima va shartnoma» tekshiruvi
    Role("yuridik", "Yuridik bo'lim", 3, R(INTL, TASKS), deny_note="Talabalar, moliya va kadrlar ma'lumoti — hujjatlar Portal orqali so'raladi"),
    # buyruqlar reyestri (o'qish, imzolanganini jurnalga olish) va chiquvchi yozishmalar jurnali; talabalar bazasi, moliya, kadrlar — yo'q
    Role("devonxona", "Devonxona", 3, R(TASKS, CHANCERY), deny_note="Talabalar bazasi, moliya va kadrlar ma'lumoti · buyruqlar — faqat reyestr (o'qish va ro'yxatga olish)"),
    Role("marketing", "Marketing bo'limi", 3, R(ADMISSIONS, TASKS), deny_note="Talabalar shaxsiy ma'lumoti, moliya va kadrlar tafsiloti"),
    Role("xarid", "Xarid bo'limi", 3, R(TASKS, PROCUREMENT), deny_note="Talabalar va kadrlar ma'lumoti · nosozliklar — faqat xarid so'rovlari"),
    Role("tyutor", "Tyutor", 4, R(OPS, ACADEMIC, STUDENTS), scope="fakultet", deny_note="Boshqa fakultet, moliya va kadrlar ma'lumoti"),
    Role("kafedra", "Kafedra mudiri", 4, R(ACADEMIC, STUDENTS, SCIENCE, TASKS, OPS, REPORTS), scope="kafedra",
         deny_note="Boshqa kafedra, moliya va kadrlar ma'lumoti · Talabalar markazi — o'z kafedrasi, o'quv holatlari (o'qish)"),
    Role("oqituvchi", "O'qituvchi", 4, R(ACADEMIC, STUDENTS, TASKS), scope="o'qituvchi",
         deny_note="Umumiy kafedra statistikasi, boshqa o'qituvchilar"),
]}

# Bekor qilingan lavozimlar. Institutda dekan lavozimi yo'q (Yevropa modeli): fakultet darajasidagi vazifalarni Registrator
# ofisi (rol "talabalar") bajaradi, fakultet tyutorlari qoladi. Kalit faqat eski yozuvlar (audit jurnali, users #13 — faolsizlantirilgan)
# to'g'ri ko'rinishi uchun saqlanadi: ruxsatlar bo'sh, ruxsatlar jadvalida (matrix), akkaunt yaratishda va kirish ro'yxatida yo'q.
LEGACY_ROLES = {r.key: r for r in [
    Role("dekan", "Dekan (lavozim bekor qilingan)", 4, R(), scope="fakultet", legacy=True,
         deny_note="Lavozim bekor qilingan — fakultet darajasidagi vazifalar Registrator ofisida"),
]}
ROLES.update(LEGACY_ROLES)
ACTIVE_ROLES = {k: r for k, r in ROLES.items() if not r.legacy}

# Telegram orqali hech qachon xom holda chiqmaydigan resurslar
TELEGRAM_BLOCKED = R(PAYROLL, HR)
TELEGRAM_AGGREGATE = R(FINANCE, STUDENTS)

class AccessDenied(Exception):
    pass

@dataclass
class Ctx:
    user: dict
    role: Role
    channel: str = "web"   # web | telegram

    @property
    def title(self) -> str:
        """Foydalanuvchining aniq lavozimi ("Registrator ofisi: …" → "Registrator ofisi"); bo'lmasa rol nomi."""
        n = self.user.get("full_name") or ""
        return n.split(":")[0].strip() if ":" in n else self.role.title

    def can(self, resource: str) -> bool:
        if resource not in self.role.allow:
            return False
        if self.channel == "telegram" and (self.role.local_only or resource in TELEGRAM_BLOCKED):
            return False
        return True

    def aggregate_only(self, resource: str) -> bool:
        return resource in self.role.aggregate_only or (self.channel == "telegram" and resource in TELEGRAM_AGGREGATE)

    # Ko'lam filtrlari: SQL sharti qaytaradi
    def student_scope(self, alias="s"):
        sc = self.role.scope
        if sc == "fakultet":
            return f"{alias}.faculty_id = {int(self.user['faculty_id'])}"
        if sc == "kafedra":
            return f"{alias}.group_id IN (SELECT id FROM groups_ WHERE department_id={int(self.user['department_id'])})"
        if sc == "o'qituvchi":
            return f"{alias}.group_id IN (SELECT group_id FROM teacher_groups WHERE teacher_id={int(self.user['teacher_id'])})"
        return "1=1"

    def teacher_scope(self, alias="t"):
        sc = self.role.scope
        if sc == "fakultet":
            return f"{alias}.faculty_id = {int(self.user['faculty_id'])}"
        if sc == "kafedra":
            return f"{alias}.department_id = {int(self.user['department_id'])}"
        if sc == "o'qituvchi":
            return f"{alias}.id = {int(self.user['teacher_id'])}"
        return "1=1"

    def scope_label(self, con):
        sc = self.role.scope
        if sc == "fakultet":
            return db.one(con, "SELECT name FROM faculties WHERE id=?", (self.user["faculty_id"],))["name"] + " fakulteti"
        if sc == "kafedra":
            return db.one(con, "SELECT name FROM departments WHERE id=?", (self.user["department_id"],))["name"] + " kafedrasi"
        if sc == "o'qituvchi":
            return "O'z guruhlari"
        return "Butun institut"

def ctx_for(con, user_id: int, channel="web") -> Ctx:
    u = db.one(con, "SELECT * FROM users WHERE id=?", (user_id,))
    if not u:
        raise AccessDenied("Foydalanuvchi topilmadi")
    return Ctx(u, ROLES[u["role"]], channel)

def audit(con, ctx: Ctx, action: str, resource: str, allowed: bool, detail: str = ""):
    cur = con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                      (dt.datetime.now().isoformat(timespec="seconds"), ctx.user["id"], ctx.user["full_name"], ctx.title,
                       ctx.channel, action, resource, int(allowed), detail[:300]))
    con.commit()
    return cur.lastrowid

def require(con, ctx: Ctx, resource: str, action: str, detail: str = ""):
    ok = ctx.can(resource)
    audit(con, ctx, action, resource, ok, detail)
    if not ok:
        why = "Telegram kanali orqali bu ma'lumot uzatilmaydi (faqat mahalliy tarmoqda)" if (
            resource in ctx.role.allow and ctx.channel == "telegram") else f"'{ctx.role.title}' lavozimi uchun ruxsat yo'q"
        raise AccessDenied(f"⛔ {LABELS.get(resource, resource)}: {why}. So'rov audit jurnaliga yozildi.")

def matrix():
    return [{"key": r.key, "title": r.title, "level": r.level, "scope": r.scope, "local_only": r.local_only,
             "allow": sorted(r.allow), "aggregate_only": sorted(r.aggregate_only), "deny_note": r.deny_note} for r in ACTIVE_ROLES.values()]

# ---------- Parollar ----------
DEMO_PASSWORD = os.getenv("ISFT_CORE_DEMO_PASSWORD", "Isft2026")   # sinov rejimi: barcha demo akkauntlar uchun

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 120_000)
    return f"pbkdf2${salt.hex()}${h.hex()}"

def check_password(stored: str | None, pw: str) -> bool:
    if not stored or not pw: return False
    if stored.startswith("pbkdf2$"):
        _, salt, h = stored.split("$")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000).hex(), h)
    return hmac.compare_digest(str(stored).encode(), pw.encode())   # eski (ochiq) yozuv — keyingi kirishda xeshga o'tkaziladi

_PATR = ("ovich", "evich", "ovna", "evna")

def polite_name(full_name: str) -> str | None:
    """Hurmat bilan murojaat: ism + otasining ismi ("G'ulomov Ibroxim Rustam o'g'li" → "Ibroxim Rustamovich").
    Shaxs ismi yo'q (bo'lim akkaunti) bo'lsa — None."""
    if ":" not in (full_name or ""): return None
    p = full_name.split(":", 1)[1].split()
    if len(p) >= 4 and p[-1].lower().replace("ʻ", "'").replace("’", "'") in ("o'g'li", "qizi"):
        ota = p[2]; male = p[-1].lower() != "qizi"
        suf = ("yevich" if male else "yevna") if ota[-1].lower() in "aeiou" else ("ovich" if male else "ovna")
        return f"{p[1]} {ota}{suf}"
    if len(p) >= 3 and p[2].lower().endswith(_PATR): return f"{p[1]} {p[2]}"
    if len(p) == 2: return " ".join(p) if p[1].lower().endswith(_PATR) else p[1]
    return p[1] if len(p) >= 2 else p[0] if p else None

def greeting(u: dict) -> str:
    """Panel sarlavhasi: "Rektor Ibroxim Rustamovich"; boshqalar — hurmatli ism; shaxssiz bo'lim akkaunti — lavozim."""
    title, name = user_title(u), polite_name(u.get("full_name") or "")
    if not name: return title
    return f"{title} {name}" if u.get("role") == "rektor" else name

def user_title(u: dict) -> str:
    n = u.get("full_name") or ""
    return n.split(":")[0].strip() if ":" in n else ROLES[u["role"]].title
