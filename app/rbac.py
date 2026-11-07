"""JARVIS yadrosi: lavozimga asoslangan ruxsat nazorati (RBAC) va audit jurnali.
Har bir ma'lumot so'rovi shu yerdan o'tadi. Taklifnomaning 4-bo'limidagi jadval aynan shu yerda kodlangan."""
import datetime as dt
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

LABELS = {KPI: "Umumiy KPI", ACADEMIC: "O'zlashtirish va davomat", STUDENTS: "Talabalar kartochkasi", CONTRACTS: "Kontrakt to'lovlari",
          FINANCE: "Byudjet va xarajatlar", PAYROLL: "Ish haqi", HR: "Kadrlar shaxsiy ma'lumoti", SCIENCE: "Ilmiy faoliyat",
          INTL: "Xalqaro hamkorlik", ADMISSIONS: "Qabul", YOUTH: "Yoshlar va yotoqxona", MASTERS: "Magistratura",
          TASKS: "Majlis topshiriqlari", AUDIT: "Audit jurnali", REPORTS: "Hisobotlar",
          FACILITIES: "Xo'jalik nosozliklari", OPS: "Talabalar bilan ishlash markazi", REQUESTS: "Murojaatlar markazi", SPACES: "Auditoriyalar bandligi"}

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
    Role("prorektor_moliya", "Moliya-iqtisod ishlari bo'yicha prorektor", 2, R(KPI, FINANCE, CONTRACTS, PAYROLL, TASKS, REPORTS),
         aggregate_only=R(PAYROLL), deny_note="Talaba baholari, ilmiy faoliyat tafsilotlari"),
    Role("prorektor_yoshlar", "Yoshlar masalalari va ma'naviy-ma'rifiy ishlar bo'yicha birinchi prorektor", 2, R(KPI, YOUTH, TASKS, FACILITIES),
         deny_note="Moliyaviy ma'lumot, individual o'quv baholari"),
    Role("qabul", "Qabul komissiyasi", 3, R(ADMISSIONS, CONTRACTS, TASKS), aggregate_only=R(CONTRACTS)),
    Role("talabalar", "Akademik faoliyat va registrator departamenti", 3, R(STUDENTS, CONTRACTS, ACADEMIC, TASKS, REQUESTS, YOUTH, OPS)),
    Role("magistratura", "Magistratura bo'limi", 3, R(MASTERS, TASKS)),
    Role("xalqaro", "Xalqaro hamkorlik bo'limi", 3, R(INTL, TASKS)),
    Role("buxgalteriya", "Buxgalteriya bo'limi", 3, R(FINANCE, CONTRACTS, PAYROLL, TASKS), local_only=True),
    Role("kadrlar", "Kadrlar bo'limi", 3, R(HR, TASKS), local_only=True),
    Role("xojalik", "Xo'jalik va texnik bo'lim", 3, R(FACILITIES, TASKS, SPACES), deny_note="Talabalar, moliya va kadrlar ma'lumoti"),
    Role("prorektor_umumiy", "Umumiy masalalar bo'yicha prorektor", 2, R(KPI, TASKS, FACILITIES, REQUESTS, SPACES),
         deny_note="Talaba baholari, moliya va kadrlar ma'lumoti"),
    Role("prorektor_xalqaro", "Xalqaro aloqalar bo'yicha prorektor", 2, R(KPI, INTL, TASKS, REPORTS),
         deny_note="Talaba baholari, moliyaviy tafsilotlar"),
    Role("prorektor_raqam", "Raqamlashtirish va moliya masalalari bo'yicha prorektor", 2, R(KPI, FINANCE, TASKS, REQUESTS, SPACES, REPORTS),
         aggregate_only=R(FINANCE), deny_note="Talaba baholari, kadrlar shaxsiy ma'lumoti"),
    Role("kotib", "Rektorat kotibi", 1, R(TASKS), deny_note="Talabalar, moliya va kadrlar ma'lumoti — kotib faqat majlis materiallari bilan ishlaydi"),
    Role("it_head", "Axborot texnologiyalari bo'limi boshlig'i", 3, R(TASKS, REQUESTS), deny_note="Talabalar baholari, moliya va kadrlar ma'lumoti"),
    Role("it_staff", "Axborot texnologiyalari bo'limi muhandisi", 3, R(TASKS), deny_note="Faqat o'ziga biriktirilgan topshiriqlar"),
    Role("call_center", "Call-markaz operatori", 3, R(OPS), deny_note="Faqat o'z qo'ng'iroqlar navbati: talaba ismi, telefon va suhbat skripti"),
    Role("tyutor", "Tyutor", 4, R(OPS, ACADEMIC, STUDENTS), scope="fakultet", deny_note="Boshqa fakultet, moliya va kadrlar ma'lumoti"),
    Role("dekan", "Dekan", 4, R(ACADEMIC, STUDENTS, SCIENCE, TASKS, REPORTS, REQUESTS, OPS), scope="fakultet",
         deny_note="Boshqa fakultet, moliyaviy tafsilotlar"),
    Role("kafedra", "Kafedra mudiri", 4, R(ACADEMIC, STUDENTS, SCIENCE, TASKS), scope="kafedra",
         deny_note="Boshqa kafedra, moliya va kadrlar ma'lumoti"),
    Role("oqituvchi", "O'qituvchi", 4, R(ACADEMIC, STUDENTS, TASKS), scope="o'qituvchi",
         deny_note="Umumiy kafedra statistikasi, boshqa o'qituvchilar"),
]}

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
    con.execute("INSERT INTO audit_log(ts,user_id,user_name,role,channel,action,resource,allowed,detail) VALUES(?,?,?,?,?,?,?,?,?)",
                (dt.datetime.now().isoformat(timespec="seconds"), ctx.user["id"], ctx.user["full_name"], ctx.role.title,
                 ctx.channel, action, resource, int(allowed), detail[:300]))
    con.commit()

def require(con, ctx: Ctx, resource: str, action: str, detail: str = ""):
    ok = ctx.can(resource)
    audit(con, ctx, action, resource, ok, detail)
    if not ok:
        why = "Telegram kanali orqali bu ma'lumot uzatilmaydi (faqat mahalliy tarmoqda)" if (
            resource in ctx.role.allow and ctx.channel == "telegram") else f"'{ctx.role.title}' lavozimi uchun ruxsat yo'q"
        raise AccessDenied(f"⛔ {LABELS.get(resource, resource)}: {why}. So'rov audit jurnaliga yozildi.")

def matrix():
    return [{"key": r.key, "title": r.title, "level": r.level, "scope": r.scope, "local_only": r.local_only,
             "allow": sorted(r.allow), "aggregate_only": sorted(r.aggregate_only), "deny_note": r.deny_note} for r in ROLES.values()]
