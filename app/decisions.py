"""Majlis qarori → topshiriqlar → bo'lim navbati → ijro → rektor nazorati.

Oqim:
  1) Kotib majlis materialini beradi (demo transkript yoki qo'lda matn; ovozdan matn — lokal STT o'rnatilmaguncha o'chiq).
  2) ISFT Core bayonnoma qoralamasi va topshiriqlar QORALAMASINI tuzadi. Bo'lim, mas'ul xodim, muddat va bog'liqlik
     faqat matnda AYTILGAN bo'lsa to'ldiriladi — har bir maydon kod bilan manba gapdan qayta tekshiriladi.
     Aytilmagan maydon bo'sh qoladi ("aytilmagan"), o'ylab topilmaydi.
  3) Kotib tahrirlaydi va tasdiqlaydi → topshiriqlar bo'limlar navbatiga tushadi. Tasdiqlash idempotent:
     qoralama → tasdiqlangan o'tishi bitta atomar UPDATE bilan, qayta bosish yangi topshiriq yaratmaydi.
  4) Bo'lim rahbari xodimga biriktiradi; ijrochi holat va natijani kiritadi; bog'langan topshiriqlar bitta chatda yozishadi.
     Bog'liq topshiriq oldingisi bajarilmaguncha yakunlanmaydi (server tekshiradi).
  5) Rektor panelida qaror va har bir topshiriqning mas'uli, holati, natijasi — aynan `tasks` jadvalidan.

Saqlash: mavjud SQLite bazasi (`meetings`, `tasks` jadvallari kengaytirilgan + `task_msgs`, `task_log`).
Tashqi servisga hech narsa yuborilmaydi: AI — lokal Ollama, qolgani kod.
"""
import datetime as dt, json, re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from . import clock
from . import db, rbac, academic_rules as AR
from .rbac import Ctx, AccessDenied, TASKS

router = APIRouter()
_con = None
_ctx = None

# ---------------------------------------------------------------------------------------------
# Bo'limlar (topshiriq navbatlari). key: (nomi, rahbar roli, matndagi atamalar — regex, katta-kichik harf muhim)
# ---------------------------------------------------------------------------------------------
UNITS = {
    # nomlar — ISFT rasmiy tashkiliy tuzilmasidan (2024); majlisdagi og'zaki atamalar ("IT", "registrator") ham taniladi
    "it":           ("Axborot texnologiyalari bo'limi", "it_head", [r"\bIT\b", r"(?i)axborot texnologiyalari bo'lim"]),
    # Registrator ofisi, Akademik faoliyatni boshqarish, Sirtqi va Ma'lumotlar bazasi bo'limlari: vazifalar va belgilar — app/academic_rules.py (6-slayd)
    "registrator":  (AR.REGISTRAR_UNIT, "talabalar", [r"(?i)\bregistrator(?!\W*(?:ma'lumotlar )?bazas)"] + AR.UNIT_PATTERNS[AR.REGISTRAR_UNIT]),
    "akademik":     (AR.ACADEMIC_UNIT, "akademik", [r"(?i)akademik faoliyat"] + AR.UNIT_PATTERNS[AR.ACADEMIC_UNIT]),
    "sirtqi":       (AR.SIRTQI_UNIT, "sirtqi", AR.UNIT_PATTERNS[AR.SIRTQI_UNIT]),
    "malumotlar_bazasi": (AR.DB_UNIT, "malumotlar_bazasi", AR.UNIT_PATTERNS[AR.DB_UNIT]),
    "imtihon":      ("Imtihon bo'limi", "imtihon", [r"(?i)imtihon bo'lim"]),
    "xojalik":      ("Xo'jalik va texnik bo'lim", "xojalik", [r"(?i)xo'jalik"]),
    "buxgalteriya": ("Buxgalteriya bo'limi", "buxgalteriya", [r"(?i)buxgalteriya"]),
    "qabul":        ("Qabul komissiyasi", "qabul", [r"(?i)qabul (?:bo'lim|komissiya)"]),
    "xalqaro":      ("Xalqaro hamkorlik bo'limi", "xalqaro", [r"(?i)xalqaro (?:aloqalar|hamkorlik) bo'lim"]),
    "kadrlar":      ("Kadrlar bo'limi", "kadrlar", [r"(?i)kadrlar bo'lim"]),
    "magistratura": ("Magistratura bo'limi", "magistratura", [r"(?i)magistratura bo'lim"]),
}
UNIT_OF_ROLE = {"it_staff": "it", **{v[1]: k for k, v in UNITS.items()}}   # eski (rolga asoslangan) xarita — faqat agent_hub uchun qoldirildi

# ---------------------------------------------------------------------------------------------
# Yagona bo'limlar reestri: topshiriq navbatlari = Portal `org_units` (app/portal.py) — HAMMASI (rahbariyat, bo'limlar,
# fakultet tyutorlari, kafedralar). Rahbar — org_units.head_user, xodimlar — users.unit (portal.members), kurator — org_units.curator.
# Saqlash kaliti (tasks.unit): yuqoridagi 12 ta tarixiy bo'lim uchun ESKI kalit saqlanadi, qolganlari — org_units kaliti.
#   Yagona farq: "registrator" (topshiriqlar) ↔ "talabalar" (Portal, Registrator ofisi). Bazadagi eski yozuvlar, UI
#   (t.unit === "registrator") va testlar shu kalitga tayanadi — shuning uchun qiymatlar ko'chirilmaydi: rahbar/xodim/kuratorni
#   aniqlashda chegarada org_key() bilan Portal kalitiga o'giriladi, Portal kalitidan task_key() bilan qaytariladi.
# ---------------------------------------------------------------------------------------------
ORG_ALIAS = {"registrator": "talabalar"}              # topshiriq kaliti → org_units kaliti
TASK_ALIAS = {v: k for k, v in ORG_ALIAS.items()}     # org_units kaliti → topshiriq kaliti
def org_key(unit): return ORG_ALIAS.get(unit, unit) if unit else None
def task_key(org): return TASK_ALIAS.get(org, org) if org else None

# Majlisdagi qisqa og'zaki shakllar (nomdan avtomatik yasaladiganlariga qo'shimcha). Kalit — org_units kaliti; katta-kichik harf farqsiz.
SHORT_FORMS = {
    "ilmiy_bolim": [r"ilmiy (?:tadqiqotlar )?bo'lim"],
    "devonxona": [r"\bdevonxona"],
    "marketing": [r"\bmarketing"],
    "xarid": [r"\bxarid(?:lar)? bo'lim"],
    "amaliyot": [r"\bamaliyot bo'lim"],
    "sifat": [r"sifatni ta'minlash"],
    "strategik": [r"\bstrategik (?:rivojlanish )?bo'lim"],
    "yuridik": [r"\byuridik bo'lim"],
    # institutda dekan lavozimi yo'q (Yevropa modeli): eski matnlardagi "dekan/dekanat" — fakultet darajasidagi vazifa → Registrator ofisi
    "talabalar": [r"\bdekan\w*"],
    "prorektor_oquv": [r"o'quv ishlari(?: bo'yicha)? prorektor"],
    "prorektor_ilmiy": [r"ilmiy ishlar(?: va innovatsiyalar)?(?: bo'yicha)? prorektor"],
    "prorektor_moliya": [r"moliya(?:[- ]iqtisod(?:iy)?)?(?: ishlari)?(?: bo'yicha)? prorektor"],
    "prorektor_yoshlar": [r"yoshlar(?: masalalari)?(?: va ma'naviy-ma'rifiy ishlar)?(?: bo'yicha)?(?: birinchi)? prorektor"],
}
# matndan avtomatik tanilmaydi ("rektoratga hisobot bersin" — ijrochi rektorat emas); kerak bo'lsa kotib tahrirda tanlaydi
NO_AUTO = {"rektorat", "kengash"}

def _name_pats(u) -> list[str]:
    """Bo'lim nomidan tanish belgilari: to'liq nom; "<kafedra> kafedrasi"; "<fakultet> (fakulteti) tyutor(lar)i"; "<nom> bo'limi"."""
    n = _n(u["name"]).strip()
    esc = lambda s: re.escape(s).replace(r"\ ", r"\s+")
    pats = [esc(n)]
    if u["group"] == "kafedra" and n.lower().endswith(" kafedrasi"):
        pats.append(esc(n[:-len(" kafedrasi")]) + r"\s+kafedra")
    elif u["group"] == "fakultet":
        core = re.sub(r"\s+fakulteti(?:\s+tyutorlari)?$", "", n, flags=re.I)
        pats += [esc(core) + r"(?:\s+fakulteti?)?\s+tyutor"]
    elif u["group"] == "bolim":
        m = re.match(r"(.+?)\s+bo'limi?$", n, re.I)
        if m: pats.append(esc(m.group(1)) + r"\s+bo'lim")
    return ["(?i)" + p for p in pats]

_REG = {"sig": None, "val": None}
def registry() -> dict:
    """topshiriq kaliti → {key, org, name, group, curator, pats}; tartib — Portal tartibi (Rahbariyat, Bo'limlar, Fakultet tyutorlari, Kafedralar)."""
    from . import portal as PT
    us = PT.units(_con)
    if _REG["sig"] is us: return _REG["val"]     # portal.units() 60 s keshlaydi — o'sha ro'yxat bo'lsa qayta yasalmaydi
    out = {}
    for u in us:
        k = task_key(u["key"])
        leg = UNITS.get(k)
        pats = list(leg[2]) if leg else []       # eski belgilar (academic_rules va h.k.) saqlanadi
        if u["key"] not in NO_AUTO:
            pats += _name_pats(u) + ["(?i)" + p for p in SHORT_FORMS.get(u["key"], [])]
        out[k] = {"key": k, "org": u["key"], "name": u["name"], "group": u["group"], "curator": u.get("curator"),
                  "pats": [re.compile(p) for p in pats]}
    for k, (name, _, pats) in UNITS.items():     # org_units da hali bo'lmasa ham eski kalitlar ishlayveradi
        out.setdefault(k, {"key": k, "org": org_key(k), "name": name, "group": "bolim", "curator": None, "pats": [re.compile(p) for p in pats]})
    _REG.update(sig=us, val=out)
    return out

def unit_name(k):
    x = registry().get(k) if k else None
    return x["name"] if x else None

def unit_list():
    """Tanlash ro'yxatlari uchun: Portal tartibida, guruh bilan (rahbariyat / bolim / fakultet / kafedra)."""
    from . import portal as PT
    gname = dict(PT.GROUPS)
    return [{"key": k, "org": x["org"], "name": x["name"], "group": x["group"], "group_name": gname.get(x["group"], x["group"])}
            for k, x in registry().items()]

def _head_role(k):
    """tasks.assignee_role — faqat ma'lumot uchun (ruxsatlar bo'lim va org_units.head_user bo'yicha tekshiriladi)."""
    if not k: return None
    if k in UNITS: return UNITS[k][1]
    from . import portal as PT
    h = PT.head_user(_con, org_key(k))
    r = db.one(_con, "SELECT role FROM users WHERE id=?", (h,)) if h else None
    return r["role"] if r else None

LEADERS = ("rektor", "kengash")            # qarorlarni to'liq ko'radi (o'qish)
SECRETARY = "kotib"

# Demo uchun yangi akkauntlar (sun'iy ism-shariflar). parol — rbac.DEMO_PASSWORD, boshqa demo akkauntlar kabi.
DEMO_USERS = [
    ("Rektorat kotibi: Hamidova Malika Shavkat qizi", "kotib"),
    ("Axborot texnologiyalari bo'limi boshlig'i: Sobirov Akmal Rustam o'g'li", "it_head"),
    ("Axborot texnologiyalari bo'limi muhandisi: Nazarov Sardor Ilhom o'g'li", "it_staff"),
    # Registrator — mavjud "Registrator ofisi" akkaunti (talabalar roli)
]

def _now(): return clock.now().replace(microsecond=0)
def _iso(t): return t.isoformat(timespec="seconds")

def _add_cols(con, table, cols):
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, typ in cols:
        if name not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")

def init(con):
    global _con
    if _con is None: _con = con     # bind() dan oldin (agent_hub.init skanerlari) ham ishlashi uchun — main.py: DEC.init birinchi chaqiriladi
    _add_cols(con, "meetings", [("status", "TEXT"), ("minutes", "TEXT"), ("source", "TEXT"), ("created_by", "INT"),
                                ("created_at", "TEXT"), ("confirmed_at", "TEXT"), ("confirmed_by", "INT"), ("incident_id", "INT"),
                                ("extract_note", "TEXT")])
    _add_cols(con, "tasks", [("unit", "TEXT"), ("assignee_user", "INT"), ("due_at", "TEXT"), ("due_text", "TEXT"),
                             ("depends_on", "INT"), ("dep_text", "TEXT"), ("evidence", "TEXT"), ("pos", "INT"),
                             ("result", "TEXT"), ("result_at", "TEXT"), ("result_by", "INT"), ("updated_at", "TEXT")])
    con.executescript("""
    CREATE TABLE IF NOT EXISTS task_msgs(id INTEGER PRIMARY KEY, task_id INT, ts TEXT, user_id INT, user_name TEXT, role TEXT, text TEXT);
    CREATE TABLE IF NOT EXISTS task_log(id INTEGER PRIMARY KEY, task_id INT, ts TEXT, user_id INT, user_name TEXT, action TEXT, detail TEXT);
    CREATE INDEX IF NOT EXISTS ix_task_msgs ON task_msgs(task_id);
    CREATE INDEX IF NOT EXISTS ix_task_log ON task_log(task_id);
    """)
    _add_cols(con, "tasks", [("review", "TEXT"), ("review_note", "TEXT"), ("review_at", "TEXT"), ("review_by", "INT")])   # qabul/qaytarish (directives bilan umumiy)
    cleanup_junk(con)
    have = {r[0] for r in con.execute("SELECT role FROM users").fetchall()}
    if have:   # bo'sh baza (seed boshlanishi) emas
        for name, role in DEMO_USERS:
            if role not in have:
                con.execute("INSERT INTO users(full_name,role,pin) VALUES(?,?,?)", (name, role, rbac.hash_password(rbac.DEMO_PASSWORD)))
    con.commit()

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

def cleanup_junk(con) -> int:
    """tests/test_regressiya.py avvalgi versiyalari qoldirgan sinov majlisi ("Test", matn "t": "x"/"y" topshiriqlari) — idempotent o'chiriladi."""
    ids = [r[0] for r in con.execute("SELECT id FROM meetings WHERE title='Test' AND transcript='t'").fetchall()]
    if not ids: return 0
    q = ",".join(map(str, ids))
    tids = [r[0] for r in con.execute(f"SELECT id FROM tasks WHERE meeting_id IN ({q})").fetchall()]
    if tids:
        tq = ",".join(map(str, tids))
        for tb in ("task_msgs", "task_log"):
            try: con.execute(f"DELETE FROM {tb} WHERE task_id IN ({tq})")
            except Exception: pass
        con.execute(f"DELETE FROM tasks WHERE id IN ({tq})")
    con.execute(f"DELETE FROM meetings WHERE id IN ({q})")
    con.commit()
    return len(ids)

# ---------------------------------------------------------------------------------------------
# Eski (bo'limsiz) majlis topshiriqlari → yagona oqim. Avval /api/meetings orqali kiritilgan topshiriqlar faqat rol bo'yicha
# yozilgan va «Bajarildi» tugmasi bilan (rektor/kengash ham boshqaning topshirig'ini) natijasiz yopilardi. Endi har biri bo'limga
# (Portal org_units) bog'lanadi, majlis «arxiv» manbali qaror sifatida ochiladi: holatni faqat ijrochi (bo'lim rahbari yoki
# biriktirilgan xodim) natija bilan yakunlaydi, rektor qabul qiladi yoki qaytaradi. main.py dagi eski /api/tasks/{id}/status
# bo'limli topshiriqni rad etadi — shuning uchun ko'chirishdan keyin bitta yakunlash oqimi qoladi. Idempotent.
# ---------------------------------------------------------------------------------------------
LEGACY_SOURCE = "arxiv"

def _legacy_target(t, heads_role: dict) -> str | None:
    role = t.get("assignee_role") or ""
    if role in MULTI_UNIT_ROLES:
        lu = legacy_unit(t)
        if lu: return task_key(lu)
    if role not in MULTI_UNIT_ROLES:
        cands = _units_in(t.get("assignee") or "")
        if cands: return cands[0]
    ks = [k for k, r in heads_role.items() if r == role]
    if len(ks) == 1: return task_key(ks[0])
    if role in UNIT_OF_ROLE: return UNIT_OF_ROLE[role]
    return "rektorat" if "rektorat" in registry() else None

def migrate_legacy(con=None) -> int:
    con = con or _con
    if con is None or _con is None: return 0
    # server starti tartibi: Portal tuzilmasi (org_units) va topshiriqlar kengaytmasi (directives.init → tasks.origin) hali yo'q bo'lsa —
    # keyingi chaqiruvda (ular tayyor bo'lgach) bajariladi
    if not db.one(con, "SELECT 1 x FROM sqlite_master WHERE type='table' AND name='org_units'"): return 0
    if "origin" not in {r[1] for r in con.execute("PRAGMA table_info(tasks)").fetchall()}: return 0
    rows = db.rows(con, """SELECT t.* FROM tasks t JOIN meetings m ON m.id=t.meeting_id
                           WHERE t.unit IS NULL AND t.status!='qoralama' AND COALESCE(t.origin,'')!='topshiriq'""")
    if not rows: return 0
    heads_role = {r["key"]: r["role"] for r in db.rows(con, "SELECT o.key, u.role FROM org_units o JOIN users u ON u.id=o.head_user")}
    now, n, mids = _iso(_now()), 0, set()
    for t in rows:
        unit = _legacy_target(t, heads_role)
        if not unit: continue
        who = None
        if t.get("assignee_role") == "oqituvchi":      # o'qituvchi — bo'lim rahbari emas: shu kafedradagi yagona o'qituvchi akkaunti bo'lsa, unga biriktiriladi
            us = db.rows(con, "SELECT id FROM users WHERE role='oqituvchi' AND unit=? AND COALESCE(active,1)=1", (org_key(unit),))
            if len(us) == 1: who = us[0]["id"]
        st = t["status"] if t["status"] in ("yangi", "jarayonda", "bajarildi") else "yangi"
        # eski "mas'ul" matni — lavozim/bo'lim nomi (masalan, "Talabalar bilan ishlash bo'limi"), shaxs emas: endi bo'lim (unit) manba;
        # matn tarixga yoziladi, ekranda bo'lim nomi va biriktirilgan xodim ko'rsatiladi
        con.execute("""UPDATE tasks SET unit=?, assignee_user=COALESCE(assignee_user, ?), assignee=CASE WHEN ? IS NULL THEN '' ELSE assignee END,
                       status=?, due_at=COALESCE(due_at, due),
                       review=CASE WHEN ?='bajarildi' THEN COALESCE(review,'qabul') ELSE review END, updated_at=COALESCE(updated_at, ?) WHERE id=? AND unit IS NULL""",
                    (unit, who, who, st, st, now, t["id"]))
        con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                    (t["id"], now, 0, "ISFT Core", "yagona ijro oqimiga o'tkazildi",
                     f"{unit_name(unit) or unit} navbatiga · avvalgi mas'ul: {t.get('assignee') or '—'} · avvalgi holat: {t['status']}"))
        mids.add(t["meeting_id"]); n += 1
    if mids:
        q = ",".join(map(str, mids))
        con.execute(f"""UPDATE meetings SET source=?, status='tasdiqlangan', confirmed_at=COALESCE(confirmed_at, date)
                        WHERE id IN ({q}) AND source IS NULL""", (LEGACY_SOURCE,))
    con.commit()
    return n

def legacy_pending() -> bool:
    if not _con or "origin" not in {r[1] for r in _con.execute("PRAGMA table_info(tasks)").fetchall()}: return False   # directives.init hali o'tmagan
    return bool(_con.execute("""SELECT 1 FROM tasks WHERE unit IS NULL AND meeting_id IS NOT NULL AND status!='qoralama'
                                         AND COALESCE(origin,'')!='topshiriq' LIMIT 1""").fetchone())

def ensure_migrated():
    try:
        if legacy_pending(): migrate_legacy(_con)
    except Exception as e:
        print("decisions.migrate_legacy:", repr(e))

# ---------------------------------------------------------------------------------------------
# Ruxsatlar
# ---------------------------------------------------------------------------------------------
def unit_of(c: Ctx):
    """Foydalanuvchining bo'limi (Portal: users.unit) — topshiriq kaliti ko'rinishida."""
    from . import portal as PT
    return task_key(PT.my_unit(c))

def is_head(c: Ctx, unit):
    from . import portal as PT
    return bool(unit) and PT.head_user(_con, org_key(unit)) == c.user["id"]

def curated_units(c: Ctx) -> set:
    """Prorektor kuratorlik qiladigan bo'limlar (org_units.curator) — ularning topshiriqlarini faqat o'qiydi."""
    if not c.role.key.startswith("prorektor_"): return set()
    return {k for k, x in registry().items() if x["curator"] == c.role.key}

# Eski (bo'limsiz, unit IS NULL) topshiriqlar rol bo'yicha yozilgan; bir xil rol bir nechta kafedra/fakultetda bor —
# bunday topshiriqning bo'limi mas'ul matnidagi kafedra/fakultet nomidan aniqlanadi ("Kafedra mudiri (Buxgalteriya hisobi)").
MULTI_UNIT_ROLES = {"kafedra": "kafedra", "oqituvchi": "kafedra", "tyutor": "fakultet"}

def _core(name: str) -> str:
    n = _n(name or "").strip()
    return re.sub(r"\s+(?:kafedrasi|fakulteti(?:\s+tyutorlari)?)$", "", n, flags=re.I)

def legacy_unit(t) -> str | None:
    """Bo'limsiz eski topshiriq ko'p bo'limli rolga yozilgan bo'lsa — mas'ul matnidan bo'lim (org kaliti); aniqlanmasa None."""
    grp = MULTI_UNIT_ROLES.get(t.get("assignee_role") or "")
    if not grp or t.get("unit"): return None
    hay = _n(t.get("assignee") or "").lower()
    hits = [x["org"] for x in registry().values() if x["group"] == grp and _core(x["name"]).lower() in hay]
    return hits[0] if len(hits) == 1 else None

def legacy_mine(c: Ctx, t) -> bool:
    """Bo'limsiz eski topshiriq shu foydalanuvchiga tegishlimi: rol mos va (bo'limi aniqlansa) bo'lim ham mos."""
    if t.get("unit") or t.get("assignee_role") != c.role.key: return False
    lu = legacy_unit(t)
    if not lu: return True
    from . import portal as PT
    return PT.my_unit(c) == lu

def _linked_ids(t) -> set:
    """Topshiriq va unga bog'langan (oldingi/keyingi) topshiriqlar."""
    ids = {t["id"]}
    if t.get("depends_on"): ids.add(t["depends_on"])
    for r in _con.execute("SELECT id FROM tasks WHERE depends_on=?", (t["id"],)).fetchall(): ids.add(r[0])
    return ids

def can_view(c: Ctx, t) -> bool:
    if t["status"] == "qoralama": return c.role.key == SECRETARY
    if c.role.key in LEADERS or c.role.key == SECRETARY: return True
    u = unit_of(c)
    if t.get("assignee_user") == c.user["id"]: return True
    if u and t.get("unit") == u: return True          # bo'lim xodimlari o'z bo'limi topshiriqlarini ko'radi
    if t.get("unit") and t["unit"] in curated_units(c): return True   # kurator prorektor — faqat o'qish
    # bog'langan topshiriq (masalan, Registrator IT natijasini ko'radi)
    if u:
        for i in _linked_ids(t):
            o = db.one(_con, "SELECT unit FROM tasks WHERE id=?", (i,))
            if o and o["unit"] == u: return True
    return legacy_mine(c, t)     # bo'limli topshiriq rol bo'yicha ko'rinmaydi (bir xil rol — turli kafedralarda)

def can_act(c: Ctx, t) -> bool:
    """Holat/natija kiritish: bo'lim rahbari yoki biriktirilgan xodim."""
    if t["status"] == "qoralama" or not t.get("unit"): return False
    return is_head(c, t["unit"]) or t.get("assignee_user") == c.user["id"]

REVIEWERS = ("rektor",)     # majlis topshirig'i natijasini qabul qiladi / qaytaradi (kuzatuv kengashi — faqat ko'radi)

def can_review(c: Ctx, t) -> bool:
    """Majlis topshirig'i natijasini qabul qilish/qaytarish: rektor; o'z natijasini o'zi qabul qilmaydi."""
    return (t.get("meeting_id") is not None and (t.get("origin") or "") != "topshiriq" and t["status"] == "bajarildi"
            and t.get("review") == "kutilmoqda" and c.role.key in REVIEWERS and t.get("result_by") != c.user["id"])

def can_chat(c: Ctx, t) -> bool:
    if t["status"] == "qoralama": return False
    if c.role.key == SECRETARY: return True
    u = unit_of(c)
    if not u: return False
    return any((db.one(_con, "SELECT unit FROM tasks WHERE id=?", (i,)) or {}).get("unit") == u for i in _linked_ids(t))

def _log(t_id, c: Ctx, action, detail=""):
    _con.execute("INSERT INTO task_log(task_id,ts,user_id,user_name,action,detail) VALUES(?,?,?,?,?,?)",
                 (t_id, _iso(_now()), c.user["id"], c.user["full_name"], action, detail[:500]))

def _guard(c: Ctx, action, detail=""):
    rbac.require(_con, c, TASKS, action, detail)

# ---------------------------------------------------------------------------------------------
# Demo transkript (sun'iy). Ovozdan olinmagan — UI'da shunday belgilanadi.
# ---------------------------------------------------------------------------------------------
UZ_M = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

def demo_transcript(today: dt.date) -> str:
    d = f"{today.day}-{UZ_M[today.month - 1]} {today.year}-yil"
    return f"""Rektorat tezkor yig'ilishi, {d}, soat 10:30.
Qatnashdilar: rektor, o'quv ishlari bo'yicha prorektor, moliya-iqtisod ishlari bo'yicha prorektor, Axborot texnologiyalari bo'limi boshlig'i, Registrator ofisi boshlig'i, rektorat kotibi.
Kun tartibi: talabalarning LMS platformasiga kira olmayotgani.
O'quv ishlari bo'yicha prorektor: kecha kechqurundan beri talabalar LMS'ga kira olmayapti, «Murojaatlar va nosozliklar»ga shu mavzuda bir nechta murojaat tushgan. Ertaga oraliq nazorat topshiriqlari LMS orqali yuklanishi kerak.
Axborot texnologiyalari bo'limi boshlig'i: muammo kirish (autentifikatsiya) qismida bo'lishi mumkin, aniq sababni tekshiruvdan keyin aytamiz.
Rektor: talabalar noaniqlikda qolmasin. Qaror: LMS'ga kirish muammosini IT bo'limi bugun soat 15:00 gacha tekshirsin. Registrator esa IT'dan natija kelgach, talabalarga xabar tayyorlasin.
Rektor: yig'ilish yopildi."""

# ---------------------------------------------------------------------------------------------
# Ajratish: qaror gaplari → topshiriq qoralamalari. Har bir maydon manba gapdan KOD bilan olinadi.
# ---------------------------------------------------------------------------------------------
def _n(t): return re.sub(r"[ʻʼ‘’`´]", "'", t or "")

SENT_SPLIT = re.compile(r"(?<!\s[A-Z]\.)(?<=[.!?])\s+")   # "Karimov A. bilan" — bosh harfdan keyin bo'linmaydi
# buyruq mayli: "tekshirsin", "tayyorlasin"; inkor ("qolmasin") — istak, topshiriq emas
IMPERATIVE = re.compile(r"\w+(?<!ma)(?:sin|sinlar|silar)\b[.!]?\s*$|\w+(?<!ma)(?:sin|sinlar)\b[,.]", re.I)
SPEAKER = re.compile(r"^\s*([A-ZÀ-ÿ][A-Za-zÀ-ÿ' .\-]{1,60}?):\s*")   # raqamsiz: "soat 9:30" so'zlovchi emas
DECISION_LEAD = re.compile(r"^(?:qaror\s*[:—–-]\s*|qaror qilindi\s*[:—–-]?\s*)", re.I)
DEP_CUE = re.compile(r"(?P<cue>[\w']+(?:dan|tan)\s+(?:natija(?:si)?\s+)?(?:kelgach|keyin|so'ng|olingach)|natija(?:si)?\s+kelgach|[\w']+\s+(?:bajarilgach|tugagach|yakunlangach))", re.I)
PERSON = re.compile(r"\b([A-Z][a-z']+(?:ov|ova|ev|eva|iy|aya|yev|yeva))\s+([A-Z]\.|[A-Z][a-z']+)")
HOUR = r"soat\s*(?P<h>\d{1,2})[:.](?P<m>\d{2})"

def _parse_due(s: str, today: dt.date):
    """Muddat faqat gapda aniq aytilgan bo'lsa. (due_at ISO, due_text — gapdagi aynan ifoda)."""
    t = _n(s)
    m = re.search(rf"(?P<day>bugun|ertaga|indinga)?\s*(?:{HOUR})\s*(?:gacha|ga)?", t, re.I)
    if m and m.group("h"):
        add = {"ertaga": 1, "indinga": 2}.get((m.group("day") or "").lower(), 0)
        d = today + dt.timedelta(days=add)
        h, mi = int(m["h"]), int(m["m"])
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{d.isoformat()}T{h:02d}:{mi:02d}", m.group(0).strip()
    m = re.search(r"(?P<day>bugun|ertaga|indinga)(?:\s+(?:kun\s+)?oxirigacha|\s*gacha)?", t, re.I)
    if m and re.search(r"gacha|oxirigacha", m.group(0), re.I):
        d = today + dt.timedelta(days={"bugun": 0, "ertaga": 1, "indinga": 2}[m["day"].lower()])
        return d.isoformat(), m.group(0).strip()
    m = re.search(r"\b(?P<d>\d{1,2})\.(?P<mo>\d{1,2})(?:\.(?P<y>\d{4}))?\b(?:\s*gacha)?", t)
    if m:
        try:
            d = dt.date(int(m["y"] or today.year), int(m["mo"]), int(m["d"]))
            if not m["y"] and d < today - dt.timedelta(days=60): d = d.replace(year=d.year + 1)
            return d.isoformat(), m.group(0).strip()
        except ValueError:
            pass
    m = re.search(r"\b(?P<d>\d{1,2})-(?P<mon>" + "|".join(UZ_M) + r")(?:gacha)?", t, re.I)
    if m:
        mon = UZ_M.index(m["mon"].lower()) + 1
        try:
            d = dt.date(today.year, mon, int(m["d"]))
            if d < today - dt.timedelta(days=60): d = d.replace(year=d.year + 1)
            return d.isoformat(), m.group(0).strip()
        except ValueError:
            pass
    m = re.search(r"\b(?P<n>bir|ikki|uch|\d+)\s+(?P<u>hafta|kun)\s+ichida", t, re.I)
    if m:
        n = {"bir": 1, "ikki": 2, "uch": 3}.get(m["n"].lower()) or int(m["n"])
        return (today + dt.timedelta(days=n * (7 if m["u"].lower() == "hafta" else 1))).isoformat(), m.group(0).strip()
    return None, None

def _units_in(s: str):
    """Gapda tilga olingan bo'limlar, paydo bo'lish tartibida. Bir joyda bir nechta belgi mos kelsa — eng uzuni
    ("Buxgalteriya hisobi kafedrasi" → kafedra, "buxgalteriya" emas); ustma-ust tushgan qisqaroq moslik tashlanadi."""
    t = _n(s)
    spans = []
    for k, x in registry().items():
        for p in x["pats"]:
            for m in p.finditer(t):
                if m.end() > m.start(): spans.append((m.start(), -(m.end() - m.start()), m.end(), k))
    taken, order = [], []
    for st, _, en, k in sorted(spans):
        if any(st < e and en > b for b, e in taken): continue
        taken.append((st, en))
        if k not in order: order.append(k)
    return order

def _clean(sent: str) -> str:
    s = SPEAKER.sub("", sent.strip(), count=1)
    s = re.sub(r"^.*?\bqaror\s*[:—–-]\s*", "", s, flags=re.I) if re.search(r"\bqaror\s*[:—–-]", s, re.I) else s
    return s.strip()

def _candidates(transcript: str):
    """Topshiriq bo'lishi mumkin bo'lgan gaplar: buyruq mayli (-sin) va bo'lim/shaxs tilga olingan."""
    out = []
    for line in _n(transcript).splitlines():
        sp = SPEAKER.match(line)
        body = line[sp.end():] if sp else line
        for sent in SENT_SPLIT.split(body):
            s = _clean(sent)
            if not s or not IMPERATIVE.search(s): continue
            # bo'lim/xodim aytilmagan bo'lsa ham band tushib qolmaydi — "aytilmagan" deb ko'rsatiladi, kotib to'ldiradi
            out.append(s)
    return out

def _build(sentences, today):
    tasks = []
    for i, s in enumerate(sentences):
        units = _units_in(s)
        dep = DEP_CUE.search(s)
        unit = units[0] if units else None
        due_at, due_text = _parse_due(s, today)
        person = PERSON.search(s)
        dep_on, dep_text = None, None
        if dep:
            dep_text = dep.group(0).strip()
            other = [u for u in _units_in(dep_text) if u != unit] or [u for u in units[1:] if u != unit]
            for j in range(len(tasks) - 1, -1, -1):
                if other and tasks[j]["unit"] == other[0]:
                    dep_on = j; break
        tasks.append({"text": s.rstrip(), "unit": unit, "assignee": person.group(0) if person else None,
                      "due_at": due_at, "due_text": due_text, "depends_on": dep_on, "dep_text": dep_text, "evidence": s})
    return tasks

def _minutes(title, transcript, tasks, discussion=None):
    t = _n(transcript)
    pick = lambda key: next((l.split(":", 1)[1].strip() for l in t.splitlines() if l.lower().startswith(key)), "")
    first = t.strip().splitlines()[0] if t.strip() else title
    lines = [f"BAYONNOMA (qoralama)", first, ""]
    if pick("qatnashdilar"): lines.append(f"Qatnashdilar: {pick('qatnashdilar')}")
    if pick("kun tartibi"): lines.append(f"Kun tartibi: {pick('kun tartibi')}")
    lines += ["", "Muhokama:"]
    if discussion:
        lines.append(discussion.strip())
    else:
        for l in t.splitlines()[1:]:
            sp = SPEAKER.match(l)
            if sp and not l.lower().startswith(("qatnashdilar", "kun tartibi")) and not any(x["evidence"] in _n(l) for x in tasks):
                lines.append(f"— {sp.group(1)}: {l[sp.end():].strip()}")
    lines += ["", "Qaror:"]
    for i, x in enumerate(tasks, 1):
        lines.append(f"{i}. {x['text']}")
    return "\n".join(lines)

async def extract(transcript: str, title: str, today: dt.date):
    """Natija: (tasks, minutes, note). AI bo'lsa — qaror gaplarini tanlash va muhokama xulosasi; maydonlar baribir kod bilan."""
    from . import ai
    rule = _candidates(transcript)
    note = "Lokal AI ishlamayapti — qoidaga asoslangan tahlil: qaror gaplari, bo'lim, muddat va bog'liqlik matndan kod bilan olindi"
    discussion, chosen = None, rule
    if await ai.llm_available():
        try:
            raw = await ai.llm_once([{"role": "system", "content":
                "Sen rektorat kotibining yordamchisisan. Senga majlis yozuvi beriladi. "
                "Majlisda kimgadir topshirilgan har bir ishni ALOHIDA band qilib, manba gapni matndan AYNAN ko'chirib ber (o'zgartirmasdan). "
                "Bitta gapda ikki bo'limga ikki xil ish berilgan bo'lsa ham alohida yoz. Ism, sana yoki muddat qo'shma. "
                'Faqat JSON: {"decisions":[{"quote":"..."}]}'},
                {"role": "user", "content": transcript[:6000]}], fmt="json", max_tokens=400)
            j = json.loads(raw)
            norm_t = re.sub(r"\s+", " ", _n(transcript))
            quotes = []
            for d in j.get("decisions", []):
                for part in SENT_SPLIT.split(re.sub(r"\s+", " ", _n(str(d.get("quote", "")))).strip()):
                    q = _clean(part)
                    # AI keltirgan gap matnda aynan bo'lishi shart — aks holda tashlanadi (o'ylab topilgan band o'tmaydi)
                    if len(q) > 12 and q.rstrip(".") in norm_t and IMPERATIVE.search(q):
                        quotes.append(q)
            # AI va qoida natijalarini birlashtiramiz (takrorsiz, matndagi tartibda)
            merged = []
            for q in quotes + rule:
                key = q.rstrip(". ").lower()
                if not any(key in m.lower() or m.rstrip(". ").lower() in key for m in merged):
                    merged.append(q)
            merged.sort(key=lambda q: norm_t.find(q.rstrip(".")))
            if merged: chosen = merged
            # Eslatma: AI'ga muhokama xulosasini ham yozdirib ko'rdik — sinovda matnda yo'q da'volar qo'shdi.
            # Shuning uchun muhokama so'zlovchilar gaplaridan aynan olinadi.
            note = (f"Lokal AI ({ai.MODEL}) qaror gaplarini aniqladi ({len(quotes)} ta, matndan aynan tekshirildi); "
                    "bo'lim, mas'ul, muddat va bog'liqlik manba gapdan kod bilan olindi; muhokama so'zlovchilar gaplaridan ko'chirildi")
        except Exception:
            pass
    tasks = _build(chosen, today)
    return tasks, _minutes(title, transcript, tasks, discussion), note

# ---------------------------------------------------------------------------------------------
# O'qish: qaror kartasi
# ---------------------------------------------------------------------------------------------
def _uname(uid):
    if not uid: return None
    u = db.one(_con, "SELECT full_name FROM users WHERE id=?", (uid,))
    return u["full_name"] if u else None

def _short(name):
    return name.split(":", 1)[1].strip() if name and ":" in name else name

def task_view(c: Ctx, t, by_id=None):
    now = _now()
    due = t.get("due_at") or t.get("due")
    overdue = False
    if due and t["status"] != "bajarildi":
        try:
            dd = dt.datetime.fromisoformat(due) if "T" in due else dt.datetime.combine(dt.date.fromisoformat(due), dt.time(23, 59))
            overdue = dd < now
        except ValueError:
            pass
    dep = by_id.get(t["depends_on"]) if (by_id and t.get("depends_on")) else (db.one(_con, "SELECT * FROM tasks WHERE id=?", (t["depends_on"],)) if t.get("depends_on") else None)
    v = {k: t.get(k) for k in ("id", "meeting_id", "text", "unit", "status", "due_at", "due_text", "dep_text", "evidence", "result", "result_at", "updated_at", "pos")}
    v.update({"due": due, "unit_name": unit_name(t.get("unit")),
              "assignee_user": t.get("assignee_user"), "assignee_name": _short(_uname(t.get("assignee_user"))) or (t.get("assignee") or None),
              "assignee_stated": t.get("assignee") or None,
              "result_by": _short(_uname(t.get("result_by"))), "overdue": overdue,
              "depends_on": t.get("depends_on"),
              "dep": {"id": dep["id"], "pos": dep.get("pos"), "unit_name": unit_name(dep.get("unit")) or "", "status": dep["status"],
                      "result": dep.get("result") if can_view(c, dep) else None} if dep else None,
              "blocked": bool(dep and dep["status"] != "bajarildi"),
              "can_act": can_act(c, t), "can_assign": is_head(c, t.get("unit")) and t["status"] not in ("qoralama", "bajarildi"),
              "can_chat": can_chat(c, t), "review": t.get("review"), "review_note": t.get("review_note"), "review_at": t.get("review_at"),
              "review_by": _short(_uname(t.get("review_by"))), "can_review": can_review(c, t)})
    return v

def decision(c: Ctx, mid: int, audit=True):
    ensure_migrated()
    m = db.one(_con, "SELECT * FROM meetings WHERE id=?", (mid,))
    if not m or not m.get("source"): raise HTTPException(404, "Qaror topilmadi")
    ts = db.rows(_con, "SELECT * FROM tasks WHERE meeting_id=? ORDER BY pos, id", (mid,))
    visible = [t for t in ts if can_view(c, t)]
    if not visible and not (c.role.key == SECRETARY):
        raise AccessDenied("⛔ Bu qaror bo'yicha sizga tegishli topshiriq yo'q.")
    if audit: rbac.audit(_con, c, "majlis qarorini ko'rish", TASKS, True, f"#{mid}")
    by_id = {t["id"]: t for t in ts}
    tasks = [task_view(c, t, by_id) for t in visible]
    ids = [t["id"] for t in visible]
    chat_ids = sorted({i for t in visible if can_chat(c, t) or c.role.key in LEADERS for i in _linked_ids(t)} & set(ids)) if ids else []
    msgs = db.rows(_con, f"SELECT * FROM task_msgs WHERE task_id IN ({','.join(map(str, chat_ids))}) ORDER BY id") if chat_ids else []
    log = db.rows(_con, f"SELECT * FROM task_log WHERE task_id IN ({','.join(map(str, ids))}) ORDER BY id") if ids else []
    inc = db.one(_con, "SELECT id, title, status, notified_at, notice, (SELECT COUNT(*) FROM requests r WHERE r.incident_id=incidents.id) n FROM incidents WHERE id=?",
                 (m["incident_id"],)) if m.get("incident_id") else None
    for x in msgs: x["user_short"] = _short(x["user_name"])
    for x in log: x["user_short"] = _short(x["user_name"])
    return {"id": m["id"], "title": m["title"], "date": m["date"], "status": m["status"], "source": m["source"],
            "minutes": m["minutes"], "transcript": m["transcript"] if c.role.key in (SECRETARY, *LEADERS) else None,
            "extract_note": m.get("extract_note"),
            "created_at": m.get("created_at"), "confirmed_at": m.get("confirmed_at"), "confirmed_by": _short(_uname(m.get("confirmed_by"))),
            "incident": inc, "tasks": tasks, "msgs": msgs, "log": log,
            "can_edit": c.role.key == SECRETARY and m["status"] == "qoralama",
            "units": unit_list(),
            "staff": _staff_for(c)}

def _staff_for(c: Ctx):
    """Rahbar biriktira oladigan xodimlar — Portal bo'yicha shu bo'lim a'zolari (portal.members)."""
    from . import portal as PT
    u = unit_of(c)
    if not u or not is_head(c, u): return []
    ok = org_key(u)
    roles = {r["id"]: r["role"] for r in db.rows(_con, "SELECT id, role FROM users WHERE unit=?", (ok,))}
    return [{"id": x["id"], "name": x["name"], "role": x["position"] or (rbac.ROLES[roles[x["id"]]].title if roles.get(x["id"]) in rbac.ROLES else "")}
            for x in PT.members(_con, ok)]

def summary_list(c: Ctx):
    """Qarorlar ro'yxati (rektor paneli va topshiriqlar bo'limi uchun)."""
    ensure_migrated()
    rows = db.rows(_con, "SELECT * FROM meetings WHERE source IS NOT NULL ORDER BY id DESC LIMIT 20")
    out = []
    for m in rows:
        ts = db.rows(_con, "SELECT * FROM tasks WHERE meeting_id=? ORDER BY pos, id", (m["id"],))
        by_id = {t["id"]: t for t in ts}
        vis = [t for t in ts if can_view(c, t)]
        if m["status"] == "qoralama" and c.role.key != SECRETARY: continue
        if not vis and c.role.key != SECRETARY: continue
        out.append({"id": m["id"], "title": m["title"], "date": m["date"], "status": m["status"], "source": m["source"],
                    "confirmed_at": m.get("confirmed_at"),
                    "tasks": [task_view(c, t, by_id) for t in vis]})
    return out

def queue(c: Ctx):
    """Bo'lim navbati: o'z bo'limi topshiriqlari (rahbar) yoki o'ziga biriktirilganlar (xodim)."""
    u = unit_of(c)
    if not u or u not in registry(): return None
    head = is_head(c, u)
    if head:
        ts = db.rows(_con, "SELECT * FROM tasks WHERE unit=? AND status!='qoralama' ORDER BY CASE status WHEN 'bajarildi' THEN 1 ELSE 0 END, id DESC", (u,))
    else:
        ts = db.rows(_con, "SELECT * FROM tasks WHERE assignee_user=? AND unit IS NOT NULL AND status!='qoralama' ORDER BY CASE status WHEN 'bajarildi' THEN 1 ELSE 0 END, id DESC", (c.user["id"],))
    # rahbariyat va kotib: bo'sh navbat kartasi ko'rsatilmaydi (ular qarorlarni umumiy ro'yxatda ko'radi)
    if not ts and (c.role.key in LEADERS or c.role.key == SECRETARY or c.role.key.startswith("prorektor_")): return None
    out = []
    for t in ts:
        v = task_view(c, t)
        m = db.one(_con, "SELECT title, date FROM meetings WHERE id=?", (t["meeting_id"],))
        v["meeting"] = m["title"] if m else ""; v["meeting_date"] = m["date"] if m else ""
        if t.get("origin") == "topshiriq":     # majlisdan tashqari topshiriq (app/directives.py): kim bergani, taqsimlash holati
            from . import directives as DIR
            v.update(DIR.queue_extra(c, t))
        out.append(v)
    name = unit_name(u)
    return {"unit": u, "unit_name": name, "head": head, "tasks": out, "staff": _staff_for(c),
            "duties": [d for d in AR.UNIT_DUTIES.get(UNITS[u][0] if u in UNITS else name, []) if not d.startswith("talabalar murojaatlari:")]}

# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------
def C(request: Request) -> Ctx: return _ctx(request)

def _secretary(c: Ctx):
    if c.role.key != SECRETARY:
        raise AccessDenied("⛔ Majlis materiali va bayonnomani rektorat kotibi kiritadi va tasdiqlaydi.")

def demo_tools() -> bool:
    """«Demoni qayta boshlash» kabi demo vositalari — faqat ISFT_CORE_DEMO_TOOLS=1 bo'lsa (oddiy ish rejimida yashirin va 403)."""
    import os
    return os.getenv("ISFT_CORE_DEMO_TOOLS", "") == "1"

@router.get("/api/dec/capabilities")
def capabilities(request: Request):
    C(request)
    return {"audio": False,
            "audio_note": "Ovozdan matnga o'tkazish (lokal STT, masalan whisper.cpp) bu serverda o'rnatilmagan. "
                          "Demo uchun namunaviy transkript ishlatiladi; ovoz tashqi servisga yuborilmaydi.",
            "sample": demo_transcript(clock.today()), "demo_tools": demo_tools()}

@router.get("/api/dec/units")
def units_(request: Request):
    """Topshiriq bo'limlari — Portal org_units bilan bitta reestr (guruhlangan: Rahbariyat / Bo'limlar / Fakultet tyutorlari / Kafedralar)."""
    c = C(request); _guard(c, "topshiriq bo'limlari ro'yxati")
    from . import portal as PT
    return {"units": unit_list(), "groups": [{"key": k, "name": n} for k, n in PT.GROUPS]}

class DraftIn(BaseModel):
    title: str = Field(..., max_length=200)
    transcript: str = Field(..., max_length=20000)
    source: str = "demo"

@router.post("/api/dec/draft")
async def create_draft(body: DraftIn, request: Request):
    c = C(request); _guard(c, "majlis materialini ISFT Core'ga berish", body.title); _secretary(c)
    if body.source not in ("demo", "manual"): raise HTTPException(400, "Noto'g'ri manba")
    if not body.transcript.strip(): raise HTTPException(400, "Majlis matni bo'sh")
    today = clock.today()
    tasks, minutes, note = await extract(body.transcript, body.title, today)
    now = _iso(_now())
    # bog'liq hodisa: Xizmat markazidagi ochiq hodisa mavzusi qarorda tilga olingan bo'lsa
    inc = None
    for i in db.rows(_con, "SELECT id, topic FROM incidents WHERE status!='hal qilindi'"):
        if i["topic"] and re.search(rf"\b{re.escape(i['topic'])}", " ".join(x["text"] for x in tasks), re.I):
            inc = i["id"]; break
    cur = _con.execute("INSERT INTO meetings(title,date,kind,transcript,status,minutes,source,created_by,created_at,incident_id,extract_note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (body.title.strip()[:200], today.isoformat(), "Rektorat", body.transcript, "qoralama", minutes, body.source, c.user["id"], now, inc, note))
    mid = cur.lastrowid
    ids = []
    for i, t in enumerate(tasks):
        r = _con.execute("""INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,due_at,due_text,status,unit,depends_on,dep_text,evidence,pos,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (mid, t["assignee"] or "", _head_role(t["unit"]), t["text"][:500],
                          (t["due_at"] or "")[:10] or None, t["due_at"], t["due_text"], "qoralama", t["unit"], None, t["dep_text"], t["evidence"][:500], i + 1, now))
        ids.append(r.lastrowid)
    for i, t in enumerate(tasks):
        if t["depends_on"] is not None:
            _con.execute("UPDATE tasks SET depends_on=? WHERE id=?", (ids[t["depends_on"]], ids[i]))
    _con.commit()
    return decision(c, mid, audit=False)

@router.get("/api/dec/list")
def list_(request: Request):
    c = C(request); _guard(c, "majlis qarorlari ro'yxati")
    return {"decisions": summary_list(c), "queue": queue(c), "role": c.role.key}

@router.get("/api/dec/{mid}")
def get_(mid: int, request: Request):
    c = C(request); _guard(c, "majlis qarorini ko'rish", f"#{mid}")
    return decision(c, mid, audit=False)

class TaskEdit(BaseModel):
    id: int
    text: str = Field(..., max_length=500)
    unit: str | None = None
    assignee: str | None = Field(None, max_length=120)
    due_at: str | None = None
    depends_on: int | None = None

class DraftEdit(BaseModel):
    title: str = Field(..., max_length=200)
    minutes: str = Field("", max_length=20000)
    tasks: list[TaskEdit]
    remove: list[int] = []

def _valid_due(v):
    if not v: return None
    try:
        return dt.datetime.fromisoformat(v).isoformat(timespec="minutes") if "T" in v else dt.date.fromisoformat(v).isoformat()
    except ValueError:
        raise HTTPException(400, "Muddat formati noto'g'ri")

@router.put("/api/dec/{mid}")
def edit_draft(mid: int, body: DraftEdit, request: Request):
    c = C(request); _guard(c, "bayonnoma qoralamasini tahrirlash", f"#{mid}"); _secretary(c)
    m = db.one(_con, "SELECT * FROM meetings WHERE id=?", (mid,))
    if not m or not m.get("source"): raise HTTPException(404)
    if m["status"] != "qoralama": raise HTTPException(409, "Qaror allaqachon tasdiqlangan — tahrirlab bo'lmaydi")
    own = {r["id"] for r in db.rows(_con, "SELECT id FROM tasks WHERE meeting_id=?", (mid,))}
    reg = registry()
    for t in body.tasks:
        if t.id not in own: raise HTTPException(400, "Topshiriq bu qarorga tegishli emas")
        if t.unit: t.unit = task_key(t.unit)       # Portal kaliti ("talabalar") ham qabul qilinadi → "registrator"
        if t.unit and t.unit not in reg: raise HTTPException(400, "Noma'lum bo'lim")
        if t.depends_on and (t.depends_on not in own or t.depends_on == t.id): raise HTTPException(400, "Bog'liqlik noto'g'ri")
    now = _iso(_now())
    for rid in body.remove:
        if rid in own:
            _con.execute("DELETE FROM tasks WHERE id=? AND status='qoralama'", (rid,))
            _con.execute("UPDATE tasks SET depends_on=NULL WHERE depends_on=?", (rid,))
    for t in body.tasks:
        if t.id in body.remove: continue
        due = _valid_due(t.due_at)
        _con.execute("""UPDATE tasks SET text=?, unit=?, assignee_role=?, assignee=?, due_at=?, due=?, depends_on=?, updated_at=?,
                        due_text=CASE WHEN COALESCE(due_at,'')=COALESCE(?,'') THEN due_text ELSE NULL END
                        WHERE id=? AND status='qoralama'""",
                     (t.text.strip(), t.unit, _head_role(t.unit), (t.assignee or "").strip(), due, (due or "")[:10] or None,
                      t.depends_on, now, due, t.id))
    _con.execute("UPDATE meetings SET title=?, minutes=? WHERE id=? AND status='qoralama'", (body.title.strip(), body.minutes, mid))
    _con.commit()
    return decision(c, mid, audit=False)

@router.post("/api/dec/{mid}/confirm")
def confirm(mid: int, request: Request):
    c = C(request); _guard(c, "bayonnomani tasdiqlash", f"#{mid}"); _secretary(c)
    m = db.one(_con, "SELECT * FROM meetings WHERE id=?", (mid,))
    if not m or not m.get("source"): raise HTTPException(404)
    if m["status"] == "qoralama":
        bad = db.rows(_con, "SELECT pos FROM tasks WHERE meeting_id=? AND (unit IS NULL OR trim(text)='')", (mid,))
        if bad: raise HTTPException(400, f"{', '.join(str(b['pos']) for b in bad)}-topshiriqda bo'lim tanlanmagan — navbatga yuborib bo'lmaydi")
        if not db.one(_con, "SELECT 1 x FROM tasks WHERE meeting_id=?", (mid,)): raise HTTPException(400, "Topshiriq yo'q")
    now = _iso(_now())
    # Atomar o'tish: faqat qoralama bo'lsa. Qayta bosilsa rowcount=0 — hech narsa yaratilmaydi.
    cur = _con.execute("UPDATE meetings SET status='tasdiqlangan', confirmed_at=?, confirmed_by=? WHERE id=? AND status='qoralama'", (now, c.user["id"], mid))
    if cur.rowcount == 0:
        _con.commit()
        return {"ok": True, "already": True, "decision": decision(c, mid, audit=False)}
    for t in db.rows(_con, "SELECT id, unit FROM tasks WHERE meeting_id=? AND status='qoralama'", (mid,)):
        _con.execute("UPDATE tasks SET status='yangi', updated_at=? WHERE id=?", (now, t["id"]))
        _log(t["id"], c, "tasdiqlandi", f"{unit_name(t['unit']) or t['unit']} navbatiga yuborildi")
    _con.commit()
    return {"ok": True, "already": False, "decision": decision(c, mid, audit=False)}

@router.delete("/api/dec/{mid}")
def drop_draft(mid: int, request: Request):
    c = C(request); _guard(c, "qoralamani o'chirish", f"#{mid}"); _secretary(c)
    m = db.one(_con, "SELECT status FROM meetings WHERE id=? AND source IS NOT NULL", (mid,))
    if not m: raise HTTPException(404)
    if m["status"] != "qoralama": raise HTTPException(409, "Tasdiqlangan qarorni o'chirib bo'lmaydi")
    _con.execute("DELETE FROM tasks WHERE meeting_id=? AND status='qoralama'", (mid,))
    _con.execute("DELETE FROM meetings WHERE id=?", (mid,)); _con.commit()
    return {"ok": True}

def _task(tid):
    t = db.one(_con, "SELECT * FROM tasks WHERE id=?", (tid,))
    if not t or not t.get("unit"): raise HTTPException(404, "Topshiriq topilmadi")
    return t

class Assign(BaseModel):
    user_id: int

@router.post("/api/dec/task/{tid}/assign")
def assign(tid: int, body: Assign, request: Request):
    c = C(request); _guard(c, "topshiriqni xodimga biriktirish", f"#{tid}")
    t = _task(tid)
    if not is_head(c, t["unit"]): raise AccessDenied("⛔ Topshiriqni faqat shu bo'lim rahbari biriktiradi.")
    if t["status"] in ("qoralama", "bajarildi"): raise HTTPException(409, "Bu holatda biriktirib bo'lmaydi")
    from . import portal as PT
    u = db.one(_con, "SELECT * FROM users WHERE id=?", (body.user_id,))
    if not u or PT.unit_key(u) != org_key(t["unit"]): raise HTTPException(400, "Xodim bu bo'limda emas")   # faqat shu bo'lim a'zosi (users.unit)
    if t.get("assignee_user") == u["id"]: return {"ok": True, "same": True}
    _con.execute("UPDATE tasks SET assignee_user=?, assignee=?, updated_at=? WHERE id=?", (u["id"], _short(u["full_name"]), _iso(_now()), tid))
    _log(tid, c, "biriktirildi", _short(u["full_name"]))
    _con.commit(); return {"ok": True}

class Update(BaseModel):
    status: str
    result: str | None = Field(None, max_length=3000)
    notify_incident: bool = False

@router.post("/api/dec/task/{tid}/update")
def update(tid: int, body: Update, request: Request):
    c = C(request); _guard(c, "topshiriq holatini yangilash", f"#{tid} → {body.status}")
    t = _task(tid)
    if t.get("origin") == "topshiriq":         # ierarxik topshiriq — qabul/qaytarish oqimi bilan (app/directives.py)
        from . import directives as DIR
        return DIR.set_status(c, tid, DIR.StatusIn(status=body.status, result=body.result))
    if not can_act(c, t): raise AccessDenied("⛔ Holatni faqat bo'lim rahbari yoki biriktirilgan xodim yangilaydi.")
    if body.status not in ("jarayonda", "bajarildi"): raise HTTPException(400, "Noto'g'ri holat")
    if t["status"] == "bajarildi": raise HTTPException(409, "Topshiriq allaqachon yakunlangan")
    res = (body.result or "").strip()
    now = _iso(_now())
    if body.status == "bajarildi" and not res: raise HTTPException(400, "Yakunlash uchun natijani yozing")   # yozishdan oldin (yarim tranzaksiya qolmasin)
    if not t.get("assignee_user"):   # rahbar o'zi bajarayotgan bo'lsa — ijrochi sifatida o'zi yoziladi
        _con.execute("UPDATE tasks SET assignee_user=?, assignee=? WHERE id=?", (c.user["id"], _short(c.user["full_name"]), tid))
        _log(tid, c, "o'zi ijroga oldi")
    if body.status == "bajarildi":
        if not res: raise HTTPException(400, "Yakunlash uchun natijani yozing")
        if t.get("depends_on"):
            d = db.one(_con, "SELECT status, unit FROM tasks WHERE id=?", (t["depends_on"],))
            if d and d["status"] != "bajarildi":
                raise HTTPException(409, f"Avval bog'liq topshiriq ({unit_name(d['unit']) or 'oldingi'}) natijasi kiritilishi kerak")
        rv = "qabul" if c.role.key in REVIEWERS else "kutilmoqda"     # rektor o'zi bajargan bo'lsa — qabul kutilmaydi
        _con.execute("""UPDATE tasks SET status='bajarildi', result=?, result_at=?, result_by=?, updated_at=?, review=?, review_note=NULL
                        WHERE id=? AND status!='bajarildi'""", (res, now, c.user["id"], now, rv, tid))
        _log(tid, c, "yakunlandi", res[:200])
        if body.notify_incident:
            m = db.one(_con, "SELECT incident_id FROM meetings WHERE id=?", (t["meeting_id"],))
            if m and m["incident_id"]:
                from . import service as SV
                n = SV.notify_incident(_con, m["incident_id"], res)
                _log(tid, c, "talabalarga yuborildi", f"Murojaatlar va nosozliklar hodisasi #{m['incident_id']}: {n} ta murojaatga javob")
    else:
        if res and res != (t.get("result") or ""):
            _con.execute("UPDATE tasks SET result=?, result_by=?, result_at=? WHERE id=?", (res, c.user["id"], now, tid))
            _log(tid, c, "oraliq natija", res[:200])
        if t["status"] != "jarayonda":
            _con.execute("UPDATE tasks SET status='jarayonda', updated_at=? WHERE id=?", (now, tid))
            _log(tid, c, "ish boshlandi")
        else:
            _con.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, tid))
    _con.commit(); return {"ok": True}

class ReviewIn(BaseModel):
    decision: str                 # qabul | qaytarish
    note: str = Field("", max_length=2000)

@router.post("/api/dec/task/{tid}/review")
def review(tid: int, body: ReviewIn, request: Request):
    """Majlis topshirig'i natijasini qabul qilish yoki izoh bilan qayta ishlashga qaytarish (directives bilan bir xil oqim)."""
    c = C(request); _guard(c, "topshiriq natijasini ko'rib chiqish", f"#{tid} → {body.decision}")
    t = _task(tid)
    if t.get("origin") == "topshiriq":
        from . import directives as DIR
        return DIR.do_review(c, tid, body.decision, body.note)
    if c.role.key not in REVIEWERS:
        rbac.audit(_con, c, "topshiriq natijasini ko'rib chiqish", TASKS, False, f"#{tid}")
        raise AccessDenied("⛔ Majlis topshirig'i natijasini rektor qabul qiladi yoki qaytaradi. So'rov audit jurnaliga yozildi.")
    if t["status"] != "bajarildi" or t.get("review") != "kutilmoqda": raise HTTPException(409, "Natija hali yuborilmagan yoki allaqachon ko'rib chiqilgan")
    if t.get("result_by") == c.user["id"]: raise HTTPException(409, "O'z natijangizni o'zingiz qabul qila olmaysiz")
    now, note = _iso(_now()), body.note.strip()
    if body.decision == "qabul":
        _con.execute("UPDATE tasks SET review='qabul', review_note=?, review_at=?, review_by=?, updated_at=? WHERE id=?", (note or None, now, c.user["id"], now, tid))
        _log(tid, c, "qabul qilindi", note)
    elif body.decision == "qaytarish":
        if not note: raise HTTPException(400, "Qaytarish sababini yozing")
        _con.execute("""UPDATE tasks SET status='jarayonda', review='qaytarildi', review_note=?, review_at=?, review_by=?, updated_at=? WHERE id=?""",
                     (note, now, c.user["id"], now, tid))
        _log(tid, c, "qayta ishlashga qaytarildi", note)
    else:
        raise HTTPException(400, "Noto'g'ri qaror")
    _con.commit()
    return {"ok": True}

def review_rows(c: Ctx) -> list[dict]:
    """Majlis topshiriqlari: natijasi qabulimni kutayotganlar (rektor) va menga qaytarilganlar (ijrochi) — mywork/bildirishnomalar uchun."""
    out = []
    if c.role.key in REVIEWERS:
        out += [dict(t, _kind="review") for t in db.rows(_con, """SELECT t.*, m.title meeting FROM tasks t JOIN meetings m ON m.id=t.meeting_id
                     WHERE t.status='bajarildi' AND t.review='kutilmoqda' AND COALESCE(t.origin,'')!='topshiriq' AND COALESCE(t.result_by,0)!=?
                     ORDER BY t.result_at""", (c.user["id"],))]
    for t in db.rows(_con, """SELECT t.*, m.title meeting FROM tasks t JOIN meetings m ON m.id=t.meeting_id
                              WHERE t.review='qaytarildi' AND t.status!='bajarildi' AND COALESCE(t.origin,'')!='topshiriq' AND t.unit IS NOT NULL"""):
        if can_act(c, t): out.append(dict(t, _kind="returned"))
    return out

def task_link(t) -> dict:
    return {"view": "tasks", "meeting": t["meeting_id"], "task": t["id"]}

class Msg(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)

@router.post("/api/dec/task/{tid}/msg")
def post_msg(tid: int, body: Msg, request: Request):
    c = C(request); _guard(c, "topshiriq chatiga yozish", f"#{tid}")
    t = _task(tid)
    if not can_chat(c, t): raise AccessDenied("⛔ Bu chatga faqat bog'langan topshiriqlar ijrochilari va kotib yozadi.")
    txt = body.text.strip()
    if not txt: raise HTTPException(400, "Bo'sh xabar")
    # xabar foydalanuvchining o'z bo'limi topshirig'iga yoziladi (zanjir ichida)
    u = unit_of(c)
    target = next((i for i in sorted(_linked_ids(t)) if u and (db.one(_con, "SELECT unit FROM tasks WHERE id=?", (i,)) or {}).get("unit") == u), tid)
    _con.execute("INSERT INTO task_msgs(task_id,ts,user_id,user_name,role,text) VALUES(?,?,?,?,?,?)",
                 (target, _iso(_now()), c.user["id"], c.user["full_name"], c.role.title, txt))
    _con.commit(); return {"ok": True}

@router.post("/api/dec/demo-reset")
def demo_reset(request: Request):
    """Demoni boshlang'ich holatga qaytarish: shu oqimda yaratilgan qarorlar va LMS hodisasi xabari."""
    c = C(request)
    if not demo_tools():
        rbac.audit(_con, c, "demo ssenariysini qayta boshlash", TASKS, False, "demo vositalari o'chiq")
        raise AccessDenied("⛔ Demo vositalari o'chirilgan (ISFT_CORE_DEMO_TOOLS=1 emas). So'rov audit jurnaliga yozildi.")
    if c.role.key not in (SECRETARY, "rektor"): raise AccessDenied("⛔ Demoni faqat kotib yoki rektor qayta boshlaydi.")
    rbac.audit(_con, c, "demo ssenariysini qayta boshlash", TASKS, True)
    ms = db.rows(_con, "SELECT id, incident_id FROM meetings WHERE source IN ('demo','manual')")   # arxiv (eski majlislar) o'chirilmaydi
    for m in ms:
        ids = [r["id"] for r in db.rows(_con, "SELECT id FROM tasks WHERE meeting_id=?", (m["id"],))]
        notices = [r["detail"] for r in db.rows(_con, f"SELECT detail FROM task_log WHERE action='talabalarga yuborildi' AND task_id IN ({','.join(map(str, ids)) or '0'})")]
        if m["incident_id"] and notices:
            inc = db.one(_con, "SELECT notice FROM incidents WHERE id=?", (m["incident_id"],))
            if inc and inc["notice"]:
                _con.execute("UPDATE requests SET status='yangi', answer=NULL WHERE incident_id=? AND answer=?", (m["incident_id"], inc["notice"]))
            _con.execute("UPDATE incidents SET notice=NULL, notified_at=NULL WHERE id=?", (m["incident_id"],))
        if ids:
            q = ",".join(map(str, ids))
            _con.execute(f"DELETE FROM task_msgs WHERE task_id IN ({q})"); _con.execute(f"DELETE FROM task_log WHERE task_id IN ({q})")
            _con.execute(f"DELETE FROM tasks WHERE id IN ({q})")
        _con.execute("DELETE FROM meetings WHERE id=?", (m["id"],))
    _con.commit()
    return {"ok": True, "removed": len(ms)}
