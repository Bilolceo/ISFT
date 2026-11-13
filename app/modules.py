"""Bo'limlar (modullar) kaliti — qaysi bo'lim menyuda va panelda ko'rinishini belgilaydigan YAGONA manba.

Nega: mahsulot juda katta bo'lib ketgan edi (rektor menyusida 32 band, deyarli hammasi namuna ma'lumotda). Egasi (mas'ul bo'lim)
va haqiqiy ma'lumot manbai yo'q bo'limlar O'CHIRILMAYDI — YASHIRILADI: kod, jadvallar va API joyida qoladi, bitta kalit bilan
qayta yoqiladi.

MUHIM: bu — mahsulot kaliti, XAVFSIZLIK CHEGARASI EMAS. O'chirilgan bo'limning API'si ishlayveradi (ruxsatni avvalgidek app/rbac.py
va modulning o'zi tekshiradi); kalit faqat menyu, panel kartalari, bildirishnomalar, «Mening vazifalarim» va qidiruvni boshqaradi.

Ustuvorlik (yuqoridan pastga):
  1) ISFT_CORE_MODULES muhit o'zgaruvchisi — vergul bilan: "+moliya,-testbank" (belgisiz nom = yoqish). Deploy uchun; sahifadan
     o'zgartirib bo'lmaydi (sahifada «muhit sozlamasi» deb ko'rsatiladi).
  2) baza (module_switch jadvali) — «Bo'limlar» sahifasida AT bo'limi boshlig'i yoki rektor o'zgartirgan qiymat.
  3) quyidagi standart qiymat (MODULES).

Boshqa kalitlar (shu faylda o'qiladi):
  ISFT_CORE_CAM_SIM=1               — kamera simulyatori (fon so'rovchisi, avtomatik nosozlik arizalari, «Kameralar» KPI). Standart: o'chiq.
  ISFT_CORE_REAL_DATA=1             — «Namuna ma'lumot — haqiqiy tizimlar hali ulanmagan» tasmasi va belgilari ko'rsatilmaydi.
  ISFT_CORE_SHOW_DEMO_PASSWORD=1    — kirish sahifasida sinov paroli va xodimlar ismi ko'rsatiladi (faqat namoyish uchun).
Batafsil: docs/modullar.md
"""
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from . import clock, db, rbac

NO_OWNER = "egasi va haqiqiy ma'lumot manbai yo'q"

# kalit = menyudagi bo'lim (static/index.html data-v). lock=True — o'chirib bo'lmaydi (tizim ishlashi uchun kerak).
# soft=True — kalit faqat MENYU bandini boshqaradi: sahifaning o'zi boshqa joydan ochiladi (panel ichidagi suhbat, vazifadagi havola).
# needs — yoqishdan oldin nima kerak (mas'ul bo'lim + ma'lumot manbai) — docs/modullar.md bilan bir xil.
def _m(key, title, desc, on, needs="", lock=False, soft=False, group="asosiy"):
    return {"key": key, "title": title, "desc": desc, "default": bool(on), "needs": needs, "lock": lock, "soft": soft, "group": group}

MODULES = [
    # ---- asosiy (standart: yoqilgan) ----
    _m("panel", "Boshqaruv paneli", "Bosh sahifa: sizdan kutilayotgan ishlar va lavozim ko'rsatkichlari.", 1, lock=True),
    _m("mywork", "Mening vazifalarim", "Barcha manbalardagi ishlar bitta ro'yxatda.", 1, lock=True),
    _m("tasks", "Majlislar va topshiriqlar", "Majlis bayonnomasi, qarorlar va topshiriqlar ijrosi.", 1, "Rektorat kotibi"),
    _m("portal", "Yozishmalar", "Bo'limlararo xatlar, fayllar va umumiy bazalar.", 1, "Devonxona"),
    _m("documents", "Hujjat chiqarish", "Ma'lumotnoma va boshqa hujjatlar, reyestr, QR tekshiruv.", 1, "Registrator ofisi"),
    _m("orders", "Buyruqlar", "Arizadan buyruq, kelishuv, rektor imzosi, reyestr.", 1, "Registrator ofisi, Kadrlar, Devonxona"),
    _m("ops", "Talabalar navbati", "Talabalar markazi: qoidalar bo'yicha holatlar va ijrochilar navbati.", 1, "Registrator ofisi · manba: HEMIS (hali ulanmagan)"),
    _m("masofaviy", "Masofaviy ta'lim", "LMS faolligi va o'quv kontenti monitoringi.", 1, "Masofaviy ta'lim bo'limi · manba: NEXTID LMS"),
    _m("testbank", "Test bank", "Mavzu testlari va oraliq nazorat banklari.", 1, "Masofaviy ta'lim bo'limi"),
    _m("paket", "Dars tayyorlash", "Bir ekranda dars: mavzu manbalari, taqdimot, video va test → SCORM / xAPI paket.", 1, "Masofaviy ta'lim bo'limi"),
    _m("kurs", "Kurs muharriri", "Bloklardan kurs (Articulate Rise o'rniga): darslar, interaktiv bloklar, test → xAPI / SCORM; Rise importi.", 1, "Masofaviy ta'lim bo'limi"),
    _m("studio", "Studiya", "Dars ishlab chiqarish: syomka bandi, AI montaj, YouTube va avtomatik paket — bitta oqim.", 1, "Masofaviy ta'lim bo'limi (studiya)"),
    _m("taqdimot", "Taqdimot", "O'qituvchi materialidan ISFT shablonida taqdimot.", 1, "Kafedralar"),
    _m("service", "Nosozliklar va murojaatlar", "QR orqali nosozlik arizalari va xarid so'rovlari; «Murojaatlar» yorlig'i — «Talabalar navbati», «Tadbir qatnashuvi» — «Yoshlar ishlari» yoqilganda.", 1, "Xo'jalik bo'limi, AT bo'limi, Xarid bo'limi"),
    # ---- tizim (faqat AT bo'limi boshlig'i menyusida) ----
    _m("accounts", "Akkauntlar", "Akkaunt yaratish, parolni tiklash, faolsizlantirish.", 1, lock=True, group="tizim"),
    _m("rbac", "Ruxsat darajalari", "Lavozimlar bo'yicha ruxsatlar jadvali.", 1, lock=True, group="tizim"),
    _m("audit", "Audit jurnali", "Kim, qachon, nimani so'ragani.", 1, lock=True, group="tizim"),
    _m("modullar", "Bo'limlar", "Shu sahifa: bo'limlarni yoqish va o'chirish.", 1, lock=True, group="tizim"),
    # ---- faqat menyu bandi (sahifa boshqa joydan ochiladi) ----
    _m("chat", "ISFT Core bilan suhbat", "Alohida menyu bandi. Panel ichidagi savol-javob oynasi baribir ishlaydi.", 1,
       "Alohida band kerak emas — suhbat paneldan ochiladi", soft=True, group="menyu"),
    _m("kiruvchi", "Kiruvchi xatlar", "Devonxona reyestri. Devonxona uchun doim ochiq; rezolyutsiya kutayotgan xat «Mening vazifalarim»dan ochiladi.", 0,
       "Devonxona (reyestrni yuritadi)", soft=True, group="menyu"),
    _m("reports", "Hisobotlar", "Tahliliy Word hisobotlar sahifasi. O'chiq bo'lsa — yuklab olish tugmalari panelda.", 0,
       "Alohida sahifa kerak emas — tugmalar panelda", group="menyu"),
    # ---- egasi va haqiqiy ma'lumot manbai yo'q (standart: o'chiq) ----
    _m("moliya", "Moliya", "To'lovlar reyestri, solishtirish, byudjet ijrosi.", 0, "Buxgalteriya · manba: 1C / bank ko'chirmalari", group="kutilmoqda"),
    _m("kadrlar", "Kadrlar", "Shaxsiy ish, ishga qabul, shtat jadvali.", 0, "Kadrlar bo'limi · manba: kadrlar bazasi", group="kutilmoqda"),
    _m("staffabs", "Xodimlar ta'tili", "Safar, ta'til, kasallik varaqasi va dars jadvaliga ta'siri.", 0, "Kadrlar bo'limi · manba: dars jadvali (HEMIS)", group="kutilmoqda"),
    _m("yoshlar", "Yoshlar ishlari", "Turar joy, ijara monitoringi, tadbirlar (shu jumladan «Tadbir qatnashuvi»).", 0, "Yoshlar ishlari bo'yicha prorektor", group="kutilmoqda"),
    _m("spaces", "Auditoriyalar", "Xonalar bandligi (kamera sanog'i).", 1, "Xo'jalik bo'limi · manba: o'rnatilgan Hikvision kameralari", group="kutilmoqda"),
    _m("cams", "Kameralar va xavfsizlik", "Xavfsizlik voqealari, kamera salomatligi, navbatlar, Face ID.", 1, "AT bo'limi · manba: o'rnatilgan Hikvision kameralari", group="kutilmoqda"),
    _m("syllabus", "O'quv dasturlari", "Sillabus oqimi va yuklama kalkulyatori.", 0, "Akademik faoliyat bo'limi", group="kutilmoqda"),
    _m("flows", "Akademik jarayonlar", "Sessiya, apellyatsiya, qayta o'qish, ko'chirish, bitiruv.", 0, "Registrator ofisi · manba: HEMIS", group="kutilmoqda"),
    _m("reyting", "Reyting", "Talabalar o'zlashtirish reytingi.", 0, "Registrator ofisi · manba: HEMIS baholari", group="kutilmoqda"),
    _m("amaliyot", "Amaliyot", "Amaliyot bazalari, biriktirish, kundalik.", 0, "Amaliyot bo'limi", group="kutilmoqda"),
    _m("ilmiy", "Ilmiy faoliyat", "Nashrlar, grantlar, magistrlik dissertatsiyalari.", 0, "Ilmiy bo'lim · manba: nashrlar bazasi", group="kutilmoqda"),
    _m("xalqaro", "Xalqaro hamkorlik", "Shartnomalar, mobillik, viza, delegatsiyalar.", 0, "Xalqaro bo'lim", group="kutilmoqda"),
    _m("rejalar", "KPI maqsadlari", "KPI maqsadlari va sifat amallari.", 0, "Strategik bo'lim, Sifat boshqarmasi", group="kutilmoqda"),
    _m("tekshiruv", "Ishlarni tekshirish", "Talaba ishlarini AI yordamida tekshirish.", 0, "Kafedralar · talaba ishlari uchun rozilik tartibi", group="kutilmoqda"),
    _m("qabul", "Qabul", "Abituriyentlar arizalari.", 0, "Qabul bo'limi · manba: qabul bazasi", group="kutilmoqda"),
    _m("docs", "Tarjima va shartnoma", "Xat tarjimasi, shartnoma bandlari tahlili.", 0, "Yuridik bo'lim, Xalqaro bo'lim", group="kutilmoqda"),
    _m("agents", "AI takliflari", "AI agentlar takliflari va kunlik brifing.", 1, "Rektorat · takliflarni kim tasdiqlashi belgilanmagan", group="kutilmoqda"),
]
BY_KEY = {m["key"]: m for m in MODULES}
EDITORS = ("it_head", "rektor")

SCHEMA = """CREATE TABLE IF NOT EXISTS module_switch(key TEXT PRIMARY KEY, enabled INT NOT NULL, updated_at TEXT, updated_by TEXT);"""

_con = None
_ctx = None
_cache = None        # {key: bool} — bazadagi qiymatlar (bitta jarayon; set() yangilaydi)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "ha")


def env_overrides() -> dict:
    """ISFT_CORE_MODULES="+moliya,-testbank,reyting" → {"moliya": True, "testbank": False, "reyting": True}. Noma'lum nomlar tashlanadi."""
    out = {}
    for part in os.getenv("ISFT_CORE_MODULES", "").replace(";", ",").split(","):
        p = part.strip()
        if not p: continue
        on = not p.startswith("-")
        k = p.lstrip("+-").strip().lower()
        if k in BY_KEY and not BY_KEY[k]["lock"]: out[k] = on
    return out


def init(con):
    """Idempotent: jadval yaratiladi; eskirgan (reestrda yo'q) kalitlar tozalanadi. Standart qiymatlar jadvalga YOZILMAYDI —
    jadvalda faqat sahifadan o'zgartirilganlari turadi (standart o'zgarsa, tegilmagan bo'limlar yangi standartni oladi)."""
    global _con, _cache
    _con = con
    con.executescript(SCHEMA)
    con.execute(f"DELETE FROM module_switch WHERE key NOT IN ({','.join('?' * len(BY_KEY))})", tuple(BY_KEY))
    con.commit()
    _cache = None


def _stored() -> dict:
    global _cache
    if _cache is None:
        if _con is None: return {}           # server tashqarisida (testlar, CLI): faqat standart + muhit
        try:
            _cache = {r["key"]: bool(r["enabled"]) for r in db.rows(_con, "SELECT key, enabled FROM module_switch")}
        except Exception:
            return {}
    return _cache


def state() -> dict:
    """{kalit: yoqilganmi} — hamma bo'limlar uchun."""
    st, env = _stored(), env_overrides()
    return {m["key"]: True if m["lock"] else env.get(m["key"], st.get(m["key"], m["default"])) for m in MODULES}


def on(key: str) -> bool:
    m = BY_KEY.get(key)
    if not m: return True                    # reestrda yo'q bo'lim — kalitga bog'lanmagan
    if m["lock"]: return True
    env = env_overrides()
    if key in env: return env[key]
    return _stored().get(key, m["default"])


def listing() -> list:
    st, env = state(), env_overrides()
    return [{**m, "enabled": st[m["key"]], "env": m["key"] in env,
             "why_off": "" if st[m["key"]] else (m["needs"] if m["soft"] or m["group"] == "menyu" else NO_OWNER)} for m in MODULES]


def set_enabled(con, c: rbac.Ctx, key: str, enabled: bool) -> dict:
    global _cache
    m = BY_KEY.get(key)
    if c.role.key not in EDITORS:
        rbac.audit(con, c, "bo'limni yoqish/o'chirish", "modullar", False, key)
        raise rbac.AccessDenied("⛔ Bo'limlarni faqat AT bo'limi boshlig'i yoki rektor yoqadi/o'chiradi.")
    if not m: raise HTTPException(404, "Bunday bo'lim yo'q")
    if m["lock"]: raise HTTPException(400, "Bu bo'lim tizim ishlashi uchun kerak — o'chirib bo'lmaydi")
    if key in env_overrides():
        raise HTTPException(409, "Bu bo'lim server sozlamasi (ISFT_CORE_MODULES) bilan belgilangan — sahifadan o'zgartirib bo'lmaydi")
    con.execute("INSERT INTO module_switch(key,enabled,updated_at,updated_by) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (key, int(bool(enabled)), clock.now().replace(microsecond=0).isoformat(), c.title))
    con.commit()
    _cache = None
    rbac.audit(con, c, "bo'lim yoqildi" if enabled else "bo'lim o'chirildi", "modullar", True, f"{key} — {m['title']}")
    return {"ok": True, "key": key, "enabled": bool(enabled), "modules": state()}


# ---- boshqa kalitlar ----
def cam_sim() -> bool:
    """Kamera simulyatori (namuna kameralar, fon so'rovchisi, avtomatik arizalar). Standart: o'chiq."""
    return _truthy("ISFT_CORE_CAM_SIM")

def cams_on() -> bool:
    return on("cams") or on("spaces")

def cam_sim_active() -> bool:
    return cam_sim() and cams_on()

def real_data() -> bool:
    return _truthy("ISFT_CORE_REAL_DATA")

def show_demo_password() -> bool:
    return _truthy("ISFT_CORE_SHOW_DEMO_PASSWORD") and not _truthy("ISFT_CORE_HIDE_DEMO_HINT")

def sample(system: str = "HEMIS") -> str:
    """Ma'lumot manbai yorlig'i: integratsiya yo'q ekan, «Manba: HEMIS» deb yozilmaydi."""
    return system if real_data() else f"Namuna ma'lumot ({system} ulanmagan)"

def flags() -> dict:
    return {"real_data": real_data(), "cam_sim": cam_sim(), "demo_login": show_demo_password()}


# ---- HTTP ----
router = APIRouter()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

class SwitchIn(BaseModel):
    enabled: bool

@router.get("/api/modules")
def api_modules(request: Request):
    """Hamma kirgan foydalanuvchi: {modules: {kalit: bool}}. AT boshlig'i va rektor: + to'liq ro'yxat (tavsif, sabab)."""
    c = _ctx(request)
    out = {"modules": state(), "flags": flags(), "can_edit": c.role.key in EDITORS}
    if c.role.key in EDITORS:
        out["list"] = listing(); out["no_owner"] = NO_OWNER
    return out

@router.post("/api/modules/{key}")
def api_module_set(key: str, body: SwitchIn, request: Request):
    return set_enabled(_con, _ctx(request), key, body.enabled)
