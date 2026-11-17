"""«Nazorat markazi» (app/nazorat.py) — rektor faqat nazorat qiladi.

1. Birlik: eskalatsiya bosqichi (egasi → rahbari → rektor), hafta kaliti, dushanba 08:00 qoidasi, qoidaviy hisobot matni.
2. HTTP (jonli server): ruxsatlar (faqat rektor va prorektorlar; prorektor — o'z ko'lami), sohalar bo'yicha istisnolar (seed), egasi va
   rahbari, menyu (rektor ≤ 5 band, bo'limlar kaliti), qoidalar (faqat rektor, chegaralar), 4 amal (audit + Topshiriqlar tizimi):
   eslatish, muddat berish, qayta tayinlash / rahbariga ko'tarish, «Ko'rdim» (holat o'zgarsa qaytadi), imzo navbati (kelishish, imzolash,
   izoh bilan qaytarish), haftalik hisobot (rektor).
3. Jarayon ichida (bazaning nusxasi, soxta soat): sohalar bo'yicha aniqlash (+10 kun), eskalatsiya zanjiri vaqtlari va idempotentlik,
   haftalik hisobot — AI'siz zaxira matn, AI (mock) va unga shaxsiy ma'lumot ketmasligi, Telegram (mock; tokensiz — jim o'tkaziladi).

Ishga tushirish: python tests/run_all.py --only nazorat. DIQQAT: bazani o'zgartiradi (topshiriqlar, buyruqlar, qoidalar).
"""
import datetime as dt, json, os, re, shutil, sqlite3, sys, tempfile, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
DBP = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
PW = re.search(r'DEMO_PASSWORD = os.getenv\("ISFT_CORE_DEMO_PASSWORD", "([^"]+)"\)', (ROOT / "app" / "rbac.py").read_text()).group(1)
fails = []
def ok(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond: fails.append(msg)
def q(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, a).fetchall()]
    finally: con.close()
def w(sql, a=()):
    con = sqlite3.connect(DBP, timeout=30)
    try: con.execute(sql, a); con.commit()
    finally: con.close()
def uid(role):
    r = q("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,)); assert r, f"{role} akkaunti yo'q"; return r[0]["id"]
def head(unit): return (q("SELECT head_user FROM org_units WHERE key=?", (unit,)) or [{}])[0].get("head_user")
def S(u):
    c = httpx.Client(base_url=B, timeout=300)
    r = c.post("/api/login", json={"user_id": u, "password": PW}); assert r.status_code == 200, f"login {u}: {r.text}"
    return c
def items(d, red_only=False):
    out = []
    for a in d["areas"]:
        out += [dict(x, _red=True) for x in a["items"]]
        if not red_only: out += [dict(x, _red=False) for x in a["lower"]]
    return {x["key"]: x for x in out}
def audit_after(aid, action):
    return q("SELECT * FROM audit_log WHERE id>? AND action=? ORDER BY id", (aid, action))
def last_audit(): return (q("SELECT MAX(id) m FROM audit_log") or [{"m": 0}])[0]["m"] or 0

# =============================================================================================
print("== 1. Birlik: eskalatsiya bosqichi, hafta, hisobot matni")
from app import nazorat as NZ0   # noqa: E402 — faqat sof funksiyalar (baza ulanmagan)
R0 = {k: v[0] for k, v in NZ0.RULES.items()}
t0 = dt.datetime(2026, 11, 2, 9, 0)
ok([NZ0.stage_of(t0, t0 + dt.timedelta(days=d), R0) for d in (0, 1.9, 2, 3.9, 4, 30)] == [0, 0, 1, 1, 2, 2],
   "Bosqich: 0–2 kun egasida, 2–4 kun rahbarida, 4+ kun — rektorda (standart 2 + 2)")
ok([NZ0.stage_of(t0, t0 + dt.timedelta(days=d), R0, head_is_rektor=True) for d in (1, 2, 3)] == [0, 2, 2],
   "Rahbari rektorning o'zi bo'lsa — egasidan to'g'ri rektorga (oraliq bosqich yo'q)")
R1 = dict(R0, owner_days=0, head_days=0)
ok(NZ0.stage_of(t0, t0, R1) == 2, "Oyna 0 kun — darhol rektorga")
ok(NZ0.week_key(dt.date(2026, 11, 16)) == "2026-W47" and NZ0.week_key(dt.date(2026, 11, 22)) == "2026-W47", "Hafta kaliti ISO (dushanba–yakshanba)")
ok(not NZ0.brief_due(dt.datetime(2026, 11, 16, 7, 59)) and NZ0.brief_due(dt.datetime(2026, 11, 16, 8, 0)) and NZ0.brief_due(dt.datetime(2026, 11, 17, 3, 0)),
   "Haftalik hisobot: dushanba 08:00 dan (07:59 — hali emas; seshanba — o'tkazib yuborilgani tayyorlanadi)")
st = {"hafta": "2026-W47", "imzo_navbati": 2, "imzo_eng_eski_kun": 4,
      "sohalar": {"ijro": {"nomi": "Ijro", "ochiq": 3, "rektorda": 2, "rahbarda": 1, "yangi_hafta": 1, "yopildi_hafta": 2, "eng_eski_kun": 9, "otgan_hafta_ochiq": 5},
                  "hujjat": {"nomi": "Hujjatlar", "ochiq": 0, "rektorda": 0, "rahbarda": 0, "yangi_hafta": 0, "yopildi_hafta": 0, "eng_eski_kun": 0, "otgan_hafta_ochiq": 0}}}
L1, D1 = NZ0.fallback_text(st)
L2, D2 = NZ0.fallback_text(json.loads(json.dumps(st)))
ok(5 <= len(L1) <= 8 and len(D1) == 3 and (L1, D1) == (L2, D2), f"Qoidaviy matn: {len(L1)} qator, 3 qaror, deterministik")
ok(any("Yaxshilandi" in x and "2 ta yopildi" in x for x in L1) and any("To'xtab qoldi" in x for x in L1) and "Imzo navbatidagi 2" in D1[0],
   "Matnda: nima yaxshilandi, nima to'xtadi; 1-qaror — imzo navbati")

# =============================================================================================
print("== 2. HTTP: ruxsatlar va ko'lam")
REK, PRO, PRO_I = uid("rektor"), uid("prorektor_oquv"), uid("prorektor_ilmiy")
rek, pro, proi = S(REK), S(PRO), S(PRO_I)
REG, KAF, KENG, MAS = uid("talabalar"), uid("kafedra"), uid("kengash"), uid("masofaviy")
a0 = last_audit()
for u, name in ((REG, "Registrator ofisi"), (KAF, "Kafedra mudiri"), (KENG, "Kuzatuv kengashi")):
    c = S(u)
    ok(c.get("/api/nazorat").status_code == 403 and c.get("/api/nazorat/imzo").status_code == 403 and c.post("/api/nazorat/act", json={"key": "task:1", "action": "korildi"}).status_code == 403,
       f"{name}: Nazorat markazi, imzo navbati va amallar — 403")
    ok(c.get("/api/nazorat/meta").json()["menu"]["items"] == [], f"{name}: menyuga qo'shimcha band yo'q")
ok(len(q("SELECT 1 FROM audit_log WHERE id>? AND action LIKE 'nazorat:%' AND allowed=0", (a0,))) >= 3, "Rad etilgan so'rovlar audit jurnalida (allowed=0)")
ok(proi.get("/api/nazorat/hafta").status_code == 403 and pro.post("/api/nazorat/rules", json={"rules": {"owner_days": 1}}).status_code == 403,
   "Prorektor: haftalik hisobot va qoidalarni o'zgartirish — 403 (faqat rektor)")

D = rek.get("/api/nazorat").json()
I = items(D)
areas = {a["key"]: a for a in D["areas"]}
ok(set(areas) == {"ijro", "oquv", "talabalar", "hujjat"}, f"Rektor: kuzatiladigan sohalar — o'chirilgan bo'limlar (moliya, kadrlar) yo'q: {sorted(areas)}")
ok(all(a["status"] in ("red", "amber", "green") for a in D["areas"]) and all(not a["items"] and not a["lower"] for a in D["areas"] if a["status"] == "green"),
   "Yashil soha — bitta qator (ichida istisno yo'q)")

# ijro: kutilgan topshiriqlar — muddatidan ≥ 3 kun o'tgan, bajarilmagan (zanjirda — eng quyi)
now = dt.datetime.fromisoformat(D["now"])
def due_of(t):
    v = t["due_at"] or t["due"]
    return dt.datetime.fromisoformat(v[:19]) if "T" in v else dt.datetime.combine(dt.date.fromisoformat(v[:10]), dt.time(23, 59))
rows = q("""SELECT t.* FROM tasks t LEFT JOIN meetings m ON m.id=t.meeting_id WHERE t.status NOT IN ('bajarildi','qoralama')
            AND (t.meeting_id IS NULL OR COALESCE(m.status,'')!='qoralama') AND COALESCE(t.due_at, t.due) IS NOT NULL""")
late = {t["id"]: t for t in rows if (now - due_of(t)).total_seconds() / 86400 >= 3}
par = {t["parent_id"] for t in late.values() if t.get("parent_id")}
exp = {f"task:{i}" for i in late if i not in par}
got = {k for k in I if k.startswith("task:")}
ok(exp and got == exp, f"Ijro: muddatidan ≥ 3 kun o'tgan topshiriqlar aniqlandi ({len(got)} ta: {sorted(got)[:6]})")
t1 = next((I[k] for k in sorted(got, key=lambda k: -I[k]["age_days"])), None)
tt = q("SELECT * FROM tasks WHERE id=?", (t1["task_id"],))[0]
org = {"registrator": "talabalar"}.get(tt["unit"], tt["unit"])
exp_owner = tt["assignee_user"] or head(org)
ok(t1["owner"]["id"] == exp_owner and t1["owner"]["position"] and t1["since"] and "kechikmoqda" in t1["why"],
   f"Egasi: {t1['owner']['position']} — {t1['owner']['name']} (ijrochi yoki bo'lim rahbari); qachondan, nega qizil")
ok(t1["stage"] == 2 and t1["_red"] and t1["stage_label"] == "Rektorda", f"Eng eski topshiriq ({t1['age_days']} kun) — rektorgacha yetgan (qizil)")
ok(all((x["stage"] == 2) == x["_red"] for x in I.values()), "Rektor uchun qizil = faqat 3-bosqichdagilar; qolganlari «rahbarlar hal qilmoqda»")
# oquv: guruhlar bo'yicha ortda qolganlar (jamlangan), talabalar: faolsizlar tyutor bo'yicha
grp = [x for k, x in I.items() if k.startswith("grp:")]
ok(grp and all("talaba" in x["title"] and x["aggregate"] and x["unit"] == "masofaviy" for x in grp), f"O'quv jarayoni: guruhlarda ortda qolganlar — {len(grp)} ta guruh (jamlangan son)")
tut = [x for k, x in I.items() if k.startswith("tut:")]
ok(tut and all("faolsiz" in x["title"] for x in tut), f"Talabalar: 7+ kun faolsizlar tyutor bo'yicha — {len(tut)} ta")
ok(all(not re.search(r"\b\d{12,}\b", x["title"] + x["why"]) for x in grp + tut), "Jamlangan istisnolarda talaba ismi/HEMIS ID yo'q")
mh = head("masofaviy")
ok(all(x["owner"]["id"] == mh or q("SELECT 1 FROM users WHERE id=? AND role='tyutor'", (x["owner"]["id"],)) for x in grp),
   "Guruh istisnosi egasi — guruh tyutori, bo'lmasa Masofaviy ta'lim bo'limi boshlig'i")
ok(all((x["head"] or {}).get("id") == PRO for x in grp if x["owner"]["id"] == mh), "Bo'lim boshlig'ining rahbari — kurator (o'quv ishlari prorektori)")

# prorektor ko'lami
DP = pro.get("/api/nazorat").json(); IP = items(DP)
DI = proi.get("/api/nazorat").json(); II = items(DI)
cur_o = {r["key"] for r in q("SELECT key FROM org_units WHERE curator='prorektor_oquv'")} | {"prorektor_oquv"}
ok(DP["scope"] != D["scope"] and all(x["unit"] in cur_o or PRO in (x["owner"]["id"], (x["head"] or {}).get("id")) for x in IP.values()),
   f"O'quv prorektori: faqat vakolatidagi bo'limlar ({len(IP)} ta)")
ok(set(IP) | set(II) <= set(I) and not (set(II) & {k for k in IP if k.startswith("grp:")}), f"Ilmiy prorektor masofaviy guruhlarni ko'rmaydi ({len(II)} ta)")

# =============================================================================================
print("== 3. Menyu va bo'limlar kaliti")
M = rek.get("/api/nazorat/meta").json()["menu"]
ok(not M["lean"] and M["items"] == ["panel", "nazorat", "imzo", "haftalik"] and not M["home"],
   f"Rektor menyusi: Boshqaruv paneli birinchi, so'ng Nazorat markazi, Imzo navbati, Haftalik hisobot; ixcham emas; bosh sahifa — panel ({M['items']})")
MP = pro.get("/api/nazorat/meta").json()["menu"]
ok(not MP["lean"] and MP["items"] == ["nazorat", "imzo"], "Prorektor: to'liq menyu + Nazorat markazi va Imzo navbati")
r = rek.post("/api/modules/chat", json={"enabled": False})
M2 = rek.get("/api/nazorat/meta").json()["menu"]
ok(r.status_code == 200 and M2["items"] == ["panel", "nazorat", "imzo", "haftalik"], f"«Suhbat» o'chirilsa — rektor menyusining boshi o'zgarmaydi ({M2['items']})")
rek.post("/api/modules/chat", json={"enabled": True})
rek.post("/api/modules/nazorat", json={"enabled": False})
M3 = rek.get("/api/nazorat/meta").json()["menu"]
ok(not M3["lean"] and M3["items"] == [] and rek.get("/api/nazorat").status_code == 404, "«Nazorat markazi» o'chirilsa — oddiy menyu, API 404")
rek.post("/api/modules/nazorat", json={"enabled": True})
ok(rek.get("/api/nazorat").status_code == 200, "Qayta yoqildi")

# =============================================================================================
print("== 4. Qoidalar (rektor)")
rv = {x["key"]: x for x in rek.get("/api/nazorat/rules").json()["rules"]}
ok(rv["task_overdue_days"]["value"] == 3 and rv["student_inactive_days"]["value"] == 7 and rv["review_wait_days"]["value"] == 5,
   "Standart: topshiriq ≥ 3 kun, talaba 7 kun faolsiz, tasdiq 5 kun")
ok(rek.post("/api/nazorat/rules", json={"rules": {"owner_days": 99}}).status_code == 400 and rek.post("/api/nazorat/rules", json={"rules": {"yoq": 1}}).status_code == 400,
   "Chegaradan tashqari / noma'lum qoida — 400")
r_bad = rek.post("/api/nazorat/rules", json={"rules": {"task_overdue_days": 5, "owner_days": 99}})
rv2 = {x["key"]: x["value"] for x in rek.get("/api/nazorat/rules").json()["rules"]}
ok(r_bad.status_code == 400 and rv2["task_overdue_days"] == 3 and not q("SELECT 1 FROM nz_rules WHERE k='task_overdue_days' AND v=5"),
   "Bitta qiymat xato — hech biri yozilmaydi (avval hammasi tekshiriladi, keyin bitta tranzaksiya)")
mx = max(x["age_days"] for x in I.values() if x["key"].startswith("task:"))
a1 = last_audit()
r = rek.post("/api/nazorat/rules", json={"rules": {"task_overdue_days": 30}})
I30 = items(rek.get("/api/nazorat").json())
ok(r.status_code == 200 and not any(k.startswith("task:") and I[k]["age_days"] + 3 < 30 for k in I30), "Chegara 30 kun — yangi topshiriqlar istisno emas")
ok(audit_after(a1, "nazorat: qoidalar o'zgartirildi"), "Qoida o'zgarishi audit jurnalida")
ok(any("task_overdue_days: 3 → 30" in (x["detail"] or "") for x in audit_after(a1, "nazorat: qoidalar o'zgartirildi")), "Auditda eski → yangi qiymat")
rek.post("/api/nazorat/rules", json={"rules": {"task_overdue_days": 3}})

# =============================================================================================
print("== 5. To'rt amal")
tasks_keys = sorted([k for k in I if k.startswith("task:")], key=lambda k: -I[k]["age_days"])
# --- Ko'rdim: yashiriladi, holat o'zgarsa qaytadi; boshqa foydalanuvchiga ta'sir qilmaydi
KA = tasks_keys[-1]
a1 = last_audit()
r = rek.post("/api/nazorat/act", json={"key": KA, "action": "korildi"})
Dk = rek.get("/api/nazorat").json()
ok(r.status_code == 200 and KA not in items(Dk) and Dk["counts"]["acked"] >= 1, f"«Ko'rdim»: {KA} yashirildi (ko'rilgan: {Dk['counts']['acked']})")
ok(audit_after(a1, "nazorat: ko'rdim"), "«Ko'rdim» audit jurnalida")
tid = int(KA.split(":")[1])
st0 = q("SELECT status FROM tasks WHERE id=?", (tid,))[0]["status"]
w("UPDATE tasks SET status=? WHERE id=?", ("jarayonda" if st0 == "yangi" else "yangi", tid))
ok(KA in items(rek.get("/api/nazorat").json()), "Holat o'zgardi (topshiriq holati) — istisno qaytib chiqdi")
w("UPDATE tasks SET status=? WHERE id=?", (st0, tid))

# --- Eslatish (agregat istisno — «Nazorat» topshirig'i yaratiladi)
G = grp[0]["key"]
a1 = last_audit()
n0 = len(q("SELECT 1 FROM nz_notes WHERE user_id=? AND title LIKE 'Eslatma:%'", (I[G]["owner"]["id"],)))
r = rek.post("/api/nazorat/act", json={"key": G, "action": "eslatish", "note": "Juma kunigacha reja"})
d = r.json()
tk = q("SELECT * FROM tasks WHERE id=?", (d.get("task_id"),))
ok(r.status_code == 200 and tk and tk[0]["src"] == f"nz:{G}" and tk[0]["origin"] == "topshiriq" and tk[0]["issuer_user"] == REK,
   f"Eslatish: Topshiriqlar tizimida «Nazorat» topshirig'i #{d.get('task_id')} (src=nz:{G})")
ok(q("SELECT 1 FROM task_msgs WHERE task_id=? AND text LIKE 'Eslatma%'", (d["task_id"],)) and q("SELECT 1 FROM task_log WHERE task_id=? AND action='eslatma yuborildi'", (d["task_id"],)),
   "Eslatma topshiriq chatida va tarixida")
ok(len(q("SELECT 1 FROM nz_notes WHERE user_id=? AND title LIKE 'Eslatma:%'", (I[G]["owner"]["id"],))) == n0 + 1 and audit_after(a1, "nazorat: eslatish"), "Egasiga bildirishnoma, audit jurnali")
own = S(I[G]["owner"]["id"])
ok(any(x["title"].startswith("Eslatma:") for x in own.get("/api/notifications").json()["items"]), "Egasining qo'ng'iroqchasida «Eslatma: …»")
r2 = rek.post("/api/nazorat/act", json={"key": G, "action": "eslatish"})
ok(r2.json().get("task_id") == d["task_id"], "Ikkinchi eslatma — o'sha topshiriqqa (yangisi yaratilmaydi)")

# --- Muddat berish (topshiriq istisnosi): o'tgan sana / izohsiz — 400; to'g'ri — topshiriq muddati o'zgaradi, istisno yo'qoladi
KM = tasks_keys[0]; tm = int(KM.split(":")[1])
ok(rek.post("/api/nazorat/act", json={"key": KM, "action": "muddat", "due": (now.date() - dt.timedelta(days=1)).isoformat(), "note": "x"}).status_code == 400
   and rek.post("/api/nazorat/act", json={"key": KM, "action": "muddat", "due": (now.date() + dt.timedelta(days=5)).isoformat(), "note": ""}).status_code == 400,
   "Muddat: o'tgan sana yoki izohsiz — 400")
nd = (now.date() + dt.timedelta(days=5)).isoformat()
a1 = last_audit()
r = rek.post("/api/nazorat/act", json={"key": KM, "action": "muddat", "due": nd, "note": "Akkreditatsiya hujjatlari kechikdi"})
t = q("SELECT * FROM tasks WHERE id=?", (tm,))[0]
ok(r.status_code == 200 and t["due"] == nd and t["due_at"].startswith(nd) and q("SELECT 1 FROM task_log WHERE task_id=? AND action=\"muddat o'zgartirildi\"", (tm,)),
   f"Muddat berildi: topshiriq #{tm} muddati {nd}, tarixda yozuv")
ok(KM not in items(rek.get("/api/nazorat").json()) and audit_after(a1, "nazorat: muddat berish"), "Istisno yopildi (muddat o'tmagan), audit jurnalida")
ok(q("SELECT status FROM nz_items WHERE key=?", (KM,))[0]["status"] == "closed", "nz_items: yopilgan")

# --- Muddat berish (agregat): yangi muddatgacha «kutishda»
G2 = grp[1]["key"] if len(grp) > 1 else None
if G2:
    r = rek.post("/api/nazorat/act", json={"key": G2, "action": "muddat", "due": nd, "note": "Tyutorlar bilan reja"})
    Ds = rek.get("/api/nazorat").json()
    ok(r.status_code == 200 and G2 not in items(Ds) and Ds["counts"]["snoozed"] >= 1 and q("SELECT due FROM tasks WHERE src=?", (f"nz:{G2}",))[0]["due"] == nd,
       "Agregat istisnoga muddat — «Nazorat» topshirig'i muddati, istisno shu muddatgacha kutishda")

# --- Qayta tayinlash (boshqa bo'limga): topshiriq bo'limi o'zgaradi, egasi — yangi bo'lim rahbari, eskalatsiya soati qaytadan
KR = next((k for k in tasks_keys[1:] if k != KA), None) or KA
tr = int(KR.split(":")[1])
ak = head("akademik")
a1 = last_audit()
ok(rek.post("/api/nazorat/act", json={"key": KR, "action": "tayinlash", "unit": "yoq_bolim"}).status_code == 400, "Noma'lum bo'lim — 400")
ok(rek.post("/api/nazorat/act", json={"key": KR, "action": "tayinlash"}).status_code == 400, "Mas'ul tanlanmagan — 400")
r = rek.post("/api/nazorat/act", json={"key": KR, "action": "tayinlash", "unit": "akademik", "note": "Akademik bo'lim olib boradi"})
t = q("SELECT * FROM tasks WHERE id=?", (tr,))[0]
I2 = items(rek.get("/api/nazorat").json())
ok(r.status_code == 200 and t["unit"] == "akademik" and q("SELECT 1 FROM task_log WHERE task_id=? AND action='qayta tayinlandi'", (tr,)), f"Qayta tayinlandi: #{tr} → Akademik bo'lim")
ok(KR in I2 and I2[KR]["owner"]["id"] == ak and I2[KR]["stage"] == 0 and not I2[KR]["_red"], "Yangi egasi — Akademik bo'lim boshlig'i; eskalatsiya soati qaytadan (egasida)")
ok(q("SELECT 1 FROM nz_notes WHERE user_id=? AND item_key=?", (ak, KR)) and audit_after(a1, "nazorat: qayta tayinlash"), "Yangi egasiga bildirishnoma; audit")
# prorektor — vakolatidan tashqari bo'limga tayinlay olmaydi (directives.authorize)
pk = next((k for k, x in IP.items() if k.startswith("tut:")), None)
if pk:
    nt0 = q("SELECT COUNT(*) n FROM tasks WHERE src=?", (f"nz:{pk}",))[0]["n"]; tmax = q("SELECT MAX(id) m FROM tasks")[0]["m"]
    ok(pro.post("/api/nazorat/act", json={"key": pk, "action": "tayinlash", "unit": "buxgalteriya"}).status_code == 403, "Prorektor: vakolatidan tashqari bo'limga — 403")
    ok(q("SELECT COUNT(*) n FROM tasks WHERE src=?", (f"nz:{pk}",))[0]["n"] == nt0 and q("SELECT MAX(id) m FROM tasks")[0]["m"] == tmax,
       "Rad etilgan qayta tayinlash — «Nazorat» topshirig'i yaratilmadi (avval tekshiruv, yetim yozuv yo'q)")
    ok(proi.post("/api/nazorat/act", json={"key": pk, "action": "eslatish"}).status_code == 403, "Ilmiy prorektor: ko'lamidan tashqari istisno — 403")
# rahbariga ko'tarish (agregat)
TK = tut[0]["key"]
hd = I[TK]["head"]["id"] if I[TK]["head"] else None
r = rek.post("/api/nazorat/act", json={"key": TK, "action": "tayinlash", "to_head": True})
tk = q("SELECT * FROM tasks WHERE src=?", (f"nz:{TK}",))
I3 = items(rek.get("/api/nazorat").json())
ok(r.status_code == 200 and tk and tk[0]["assignee_user"] == hd and TK in I3 and I3[TK]["owner"]["id"] == hd, f"Rahbariga ko'tarildi: {TK} → {r.json().get('to')}")

# =============================================================================================
print("== 6. Imzo navbati")
reg = S(REG)
sid = [x["id"] for x in q("SELECT id FROM students WHERE status='faol' ORDER BY id DESC LIMIT 2")]
mk = []
for s in sid:
    r = reg.post("/api/orders", json={"kind": "hayfsan", "students": [{"student_id": s}], "params": {"reason": "Nazorat markazi testi"}, "note": "test"})
    if r.status_code == 200:
        oid = r.json()["id"]
        if reg.post(f"/api/orders/{oid}/submit").status_code == 200: mk.append(oid)
ok(len(mk) == 2, f"Ikki buyruq loyihasi imzoga yuborildi: {mk}")
Sp = pro.get("/api/nazorat/imzo").json()
mine = [x for x in Sp["items"] if x["ref"] in mk]
ok(len(mine) == 2 and all(x["actions"].get("approve") == "Kelishish" for x in mine), "Prorektor navbatida — «Kelishish»")
a1 = last_audit()
r = pro.post(f"/api/nazorat/imzo/order/{mk[0]}", json={"decision": "approve"})
ok(r.status_code == 200 and q("SELECT status FROM orders WHERE id=?", (mk[0],))[0]["status"] == "kelishilgan", "Prorektor kelishdi → «kelishilgan»")
ok(reg.post(f"/api/nazorat/imzo/order/{mk[1]}", json={"decision": "approve"}).status_code == 403, "Registrator imzo navbatidan qaror qila olmaydi — 403")
Sr = rek.get("/api/nazorat/imzo").json()
sinces = [x["since"] for x in Sr["items"] if x["since"]]
ok(Sr["count"] == len(Sr["items"]) and sinces == sorted(sinces) and all(x["ref"] in [y["ref"] for y in Sr["items"]] for x in mine),
   f"Rektor navbati: {Sr['count']} ta, eng eskisi birinchi")
ok(Sr["count"] == rek.get("/api/nazorat").json()["sign_count"], "Nazorat markazidagi son = imzo navbati soni (belgi)")
r = rek.post(f"/api/nazorat/imzo/order/{mk[0]}", json={"decision": "approve"})
o = q("SELECT * FROM orders WHERE id=?", (mk[0],))[0]
ok(r.status_code == 200 and o["status"] == "imzolangan" and o["reg_no"] and o["signed_by"] == REK, f"Rektor imzoladi: {o['reg_no']}")
ok(rek.post(f"/api/nazorat/imzo/order/{mk[1]}", json={"decision": "return", "note": ""}).status_code == 400, "Qaytarish izohsiz — 400")
r = rek.post(f"/api/nazorat/imzo/order/{mk[1]}", json={"decision": "return", "note": "Asos hujjat ilova qilinmagan"})
o = q("SELECT * FROM orders WHERE id=?", (mk[1],))[0]
ok(r.status_code == 200 and o["status"] == "loyiha" and o["returned_note"] == "Asos hujjat ilova qilinmagan", "Izoh bilan qaytarildi → «loyiha»")
ok(len(audit_after(a1, "nazorat: imzo navbati")) >= 3 and audit_after(a1, "buyruqlar: buyruq imzolandi"), "Qarorlar audit jurnalida (nazorat + buyruqlar)")
ok(not [x for x in rek.get("/api/nazorat/imzo").json()["items"] if x["ref"] in mk], "Qaror qilinganlar navbatdan chiqdi")
ok(rek.post("/api/nazorat/imzo/kadrlar/1", json={"decision": "approve"}).status_code == 400, "Boshqa turdagi hujjat — o'z bo'limida («Ochish»), 400")

# =============================================================================================
print("== 7. Haftalik hisobot (HTTP)")
r = rek.post("/api/nazorat/hafta")
b = r.json()
ok(r.status_code == 200 and b["source"] == "qoida" and 5 <= len(b["lines"]) <= 8 and len(b["decisions"]) == 3, f"Hozir tayyorlash: kalitsiz — qoidaviy matn ({len(b['lines'])} qator, 3 qaror)")
h = rek.get("/api/nazorat/hafta").json()
ok(h["latest"]["week"] == b["week"] and h["next"].endswith("T08:00") and dt.date.fromisoformat(h["next"][:10]).weekday() == 0 and not h["telegram"],
   f"Sahifa: oxirgi hisobot, keyingisi dushanba 08:00 ({h['next']}); Telegram tokeni yo'q")
ok(any(x["title"].startswith("Haftalik hisobot tayyor") for x in rek.get("/api/notifications").json()["items"]), "Rektor qo'ng'iroqchasida «Haftalik hisobot tayyor»")

# =============================================================================================
print("== 8. Jarayon ichida: soxta soat, eskalatsiya zanjiri, hisobot (AI va Telegram — mock)")
tmp = Path(tempfile.mkdtemp(prefix="nz-test-"))
src = sqlite3.connect(DBP, timeout=30); dst = sqlite3.connect(tmp / "jarvis.db")
src.backup(dst); src.close(); dst.close()
os.environ.update(ISFT_CORE_DATA_DIR=str(tmp), ISFT_CORE_DB=str(tmp / "jarvis.db"), ISFT_CORE_FILES_DIR=str(tmp / "portal_files"),
                  ISFT_CORE_STAFFABS_DIR=str(tmp / "staffabs_files"), ISFT_CORE_SECRETS_DIR=str(tmp / "secrets"))
os.environ.pop("ANTHROPIC_API_KEY", None); os.environ.pop("TELEGRAM_BOT_TOKEN", None)
for m in [k for k in sys.modules if k == "app" or k.startswith("app.")]: del sys.modules[m]
import io, contextlib   # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    from app import main as MAIN   # noqa: E402 — butun ilova nusxa baza ustida (startup vazifalari ishga tushmaydi)
from app import nazorat as NZ, db as DB, rbac as RB   # noqa: E402
con = MAIN.con
NOW = dt.datetime.combine(dt.date.fromisoformat(D["now"][:10]), dt.time(10, 0))
base = {x["key"] for x in NZ.scan(con, NOW)}
later = {x["key"] for x in NZ.scan(con, NOW + dt.timedelta(days=10))}
ok({k for k in later if k.startswith("task:")} > {k for k in base if k.startswith("task:")}, f"Soxta soat +10 kun: ko'proq topshiriq istisno ({len(base)} → {len(later)})")
NZ.scan(con, NOW)

# eskalatsiya: yangi topshiriq — Akademik bo'limga, muddati 3 kun + 1 soat oldin o'tgan
ak_h = DB.one(con, "SELECT head_user FROM org_units WHERE key='akademik'")["head_user"]
pro_id = DB.one(con, "SELECT id FROM users WHERE role='prorektor_oquv' ORDER BY id")["id"]
rek_id = DB.one(con, "SELECT id FROM users WHERE role='rektor' ORDER BY id")["id"]
due = NOW - dt.timedelta(days=3, hours=1)
con.execute("""INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,due_at,status,unit,pos,updated_at,origin,issuer_user,issuer_unit,priority,created_at)
               VALUES(NULL,'','akademik','Eskalatsiya sinovi topshirig''i',?,?,'yangi','akademik',0,?,'topshiriq',?,'rektorat','oddiy',?)""",
            (due.date().isoformat(), due.isoformat(timespec="minutes"), NOW.isoformat(), rek_id, NOW.isoformat()))
con.commit()
ET = DB.one(con, "SELECT MAX(id) m FROM tasks")["m"]; EK = f"task:{ET}"
notes = lambda uid: DB.one(con, "SELECT COUNT(*) n FROM nz_notes WHERE item_key=? AND user_id=?", (EK, uid))["n"]
def at(h):
    x = {i["key"]: i for i in NZ.scan(con, NOW + dt.timedelta(hours=h))}[EK]
    return x["stage"], x["chain"]
s0, ch = at(0)
ok(s0 == 0 and ch == [ak_h, pro_id, rek_id] and notes(ak_h) == 1 and notes(pro_id) == 0, "Paydo bo'ldi: egasida (bo'lim boshlig'i), zanjir — boshliq → kurator prorektor → rektor; egasiga 1 bildirishnoma")
at(1); at(2)
ok(notes(ak_h) == 1, "Takror skan — yangi bildirishnoma yo'q (idempotent)")
ok(at(46)[0] == 0 and notes(pro_id) == 0, "47 soat (paydo bo'lganidan): hali egasida")
ok(at(50)[0] == 1 and notes(pro_id) == 1 and notes(rek_id) == 0, "2 kundan keyin — rahbarida (prorektorga bildirishnoma), rektorga hali yo'q")
rctx = RB.ctx_for(con, rek_id); pctx = RB.ctx_for(con, pro_id)
x50 = {i["key"]: i for i in NZ.scan(con, NOW + dt.timedelta(hours=50))}[EK]
ok(not NZ._red(rctx, x50, NZ._curated(rctx)) and NZ._red(pctx, x50, NZ._curated(pctx)), "Rahbar bosqichida: prorektorda qizil, rektorda — yo'q")
ok(at(94)[0] == 1 and notes(rek_id) == 0, "95 soat: hali rahbarida")
s2, _ = at(97)
x97 = {i["key"]: i for i in NZ.scan(con, NOW + dt.timedelta(hours=97))}[EK]
ok(s2 == 2 and notes(rek_id) == 1 and NZ._red(rctx, x97, set()), "Rahbar oynasi o'tgach — rektorga yetdi (bitta bildirishnoma, qizil)")
at(120)
ok(notes(rek_id) == 1 and notes(pro_id) == 1 and notes(ak_h) == 1, "Keyingi skanlar — takroriy bildirishnoma yo'q")
# rektorga bevosita bo'ysunuvchi bo'lim (kurator yo'q): egasidan to'g'ri rektorga
kd_h = DB.one(con, "SELECT head_user FROM org_units WHERE key='kadrlar'")["head_user"]
con.execute("UPDATE tasks SET unit='kadrlar', assignee_user=NULL WHERE id=?", (ET,)); con.commit()
con.execute("UPDATE nz_items SET reset_at=?, notified_level=-1 WHERE key=?", (NOW.isoformat(), EK)); con.commit()
x = {i["key"]: i for i in NZ.scan(con, NOW + dt.timedelta(hours=1))}[EK]
y = {i["key"]: i for i in NZ.scan(con, NOW + dt.timedelta(hours=49))}[EK]
ok(x["chain"] == [kd_h, rek_id, rek_id] and x["stage"] == 0 and y["stage"] == 2, "Kuratorsiz bo'lim: egasi → (rahbari = rektor) → 2 kundan keyin rektorda")
# topshiriq bajarilsa — istisno yopiladi
con.execute("UPDATE tasks SET status='bajarildi' WHERE id=?", (ET,)); con.commit()
NZ.scan(con, NOW + dt.timedelta(hours=50))
ok(DB.one(con, "SELECT status FROM nz_items WHERE key=?", (EK,))["status"] == "closed", "Topshiriq bajarildi — istisno yopildi")

# haftalik hisobot: AI'siz, AI (mock), xato AI, shaxsiy ma'lumot yo'qligi, Telegram (mock)
MON = NOW - dt.timedelta(days=NOW.weekday()) + dt.timedelta(days=7)
MON = dt.datetime.combine(MON.date(), dt.time(8, 5))
ok(NZ.weekly_due(con, MON - dt.timedelta(minutes=10)) is None or MON.weekday() != 0, "Dushanba 07:55 — hali hisobot yo'q")
b0 = NZ.weekly_due(con, MON)
ok(b0 and b0["source"] == "qoida" and 5 <= len(b0["lines"]) <= 8 and len(b0["decisions"]) == 3 and b0["week"] == NZ.week_key(MON.date()),
   f"Dushanba 08:05 — hisobot tayyorlandi (kalitsiz: qoidaviy, {len(b0['lines'])} qator)")
ok(NZ.weekly_due(con, MON + dt.timedelta(minutes=10)) is None, "Shu hafta qayta tayyorlanmaydi (idempotent)")
ok(DB.one(con, "SELECT COUNT(*) n FROM nz_notes WHERE user_id=? AND kind='hisobot'", (rek_id,))["n"] >= 1, "Ilovada: rektorga bildirishnoma")
seen = []
def fake_ai(stats):
    seen.append(json.dumps(stats, ensure_ascii=False))
    return ([f"AI qatori {i}" for i in range(1, 7)], ["Qaror A", "Qaror B", "Qaror C"])
b1 = NZ.make_brief(con, MON, force=True, ai_fn=fake_ai)
ok(b1["source"] == "ai" and b1["lines"][0] == "AI qatori 1" and b1["decisions"] == ["Qaror A", "Qaror B", "Qaror C"], "AI (mock): qat'iy JSON — 6 qator, 3 qaror")
payload = seen[0] if seen else ""
names = [r["full_name"].split(":")[-1].strip().split()[0] for r in DB.rows(con, "SELECT full_name FROM users WHERE full_name LIKE '%:%'")]
titles = [r["text"][:25] for r in DB.rows(con, "SELECT text FROM tasks WHERE status!='bajarildi' LIMIT 50")]
stud = [r["full_name"].split()[0] for r in DB.rows(con, "SELECT full_name FROM students LIMIT 200")]
leak = [n for n in names + titles + stud if len(n) > 3 and n in payload]
ok(payload and not leak and not re.search(r"\d{9,}", payload), f"AI'ga faqat jamlangan sonlar: ism, topshiriq matni, talaba yo'q ({len(payload)} belgi)")
ok(set(json.loads(payload)) == {"hafta", "sohalar", "imzo_navbati", "imzo_eng_eski_kun"}, "AI so'rovi kalitlari: hafta, sohalar, imzo navbati")
def bad_ai(stats): raise RuntimeError("AI xizmati javob bermadi")
b2 = NZ.make_brief(con, MON, force=True, ai_fn=bad_ai)
ok(b2["source"] == "qoida" and len(b2["lines"]) >= 5, "AI xatosi — qoidaviy matn (hisobot baribir chiqadi)")
b3 = NZ.make_brief(con, MON, force=True, ai_fn=lambda s: (["faqat bitta"], ["x"]))
ok(b3["source"] == "qoida", "AI javobi talabga mos emas (5–8 qator / 3 qaror) — qoidaviy matn")
# Telegram: rektor botga ulangan (parol izi mos) — mock orqali yuboriladi
u = DB.one(con, "SELECT * FROM users WHERE id=?", (rek_id,))
if "tg_pin_fp" not in {r[1] for r in con.execute("PRAGMA table_info(users)")}:   # ustunni bot (app/bot.py) birinchi ulanishda qo'shadi
    con.execute("ALTER TABLE users ADD COLUMN tg_pin_fp TEXT"); con.commit()
con.execute("UPDATE users SET telegram_id=?, tg_pin_fp=? WHERE id=?", (777001, RB.pin_fp(u["pin"]), rek_id)); con.commit()
sent = []
b4 = NZ.make_brief(con, MON, force=True, use_ai=False, tg_fn=lambda chat, text: (sent.append((chat, text)) or True, "yuborildi"))
ok(len(sent) == 1 and sent[0][0] == 777001 and "Haftalik nazorat hisoboti" in sent[0][1] and "Kerakli qarorlar" in sent[0][1] and b4["telegram"][0]["ok"],
   "Telegram (mock): rektorga bitta xabar — qatorlar va kerakli qarorlar")
b5 = NZ.make_brief(con, MON, force=True, use_ai=False)
ok(b5["telegram"] and not b5["telegram"][0]["ok"] and "TELEGRAM_BOT_TOKEN" in b5["telegram"][0]["note"], "Tokensiz: Telegram jim o'tkaziladi (xato emas, sababi yoziladi)")
con.execute("UPDATE users SET tg_pin_fp='eski' WHERE id=?", (rek_id,)); con.commit()
sent.clear()
NZ.make_brief(con, MON, force=True, use_ai=False, tg_fn=lambda chat, text: (sent.append(chat) or True, "ok"))
ok(not sent, "Parol o'zgargan (ulanish eskirgan) — Telegram'ga yuborilmaydi")

# ko'rinishlar keshi: overview/item — oxirgi skan natijasi (yangi bo'lsa); faqat ko'rish yozmaydi; amal — bitta skan
import threading   # noqa: E402
calls = []
_det = NZ.detect
NZ.detect = lambda *a, **k: (calls.append(1), _det(*a, **k))[1]
NZ.invalidate()
tc = con.total_changes
NZ.overview(rctx); NZ.overview(rctx); NZ.overview(pctx)
ok(len(calls) == 1 and con.total_changes == tc, f"Ko'rinish: 3 ta overview — 1 ta aniqlash (kesh), bazaga yozuv yo'q ({len(calls)} ta, {con.total_changes - tc} o'zgarish)")
gk = next((x["key"] for x in NZ.latest() if x["kind"] != "topshiriq"), None)
calls.clear()
if gk:
    NZ.act_remind(rctx, gk, "kesh sinovi")
    NZ.overview(rctx)
    ok(len(calls) == 1, f"Amal (eslatish) + keyingi overview — jami 1 ta skan ({len(calls)})")
else:
    ok(False, "Agregat istisno topilmadi (kesh sinovi)")
NZ.detect = _det
# haftalik hisobot: AI so'rovi qulfdan tashqarida; bir vaqtda ikki marta tayyorlanmaydi
ai_calls, free = [], []
def slow_ai(stats):
    ai_calls.append(1)
    t = threading.Thread(target=lambda: free.append(NZ._lock.acquire(timeout=1) and (NZ._lock.release() or True))); t.start(); t.join()
    time.sleep(0.5)
    return ([f"AI {i}" for i in range(1, 7)], ["Q1", "Q2", "Q3"])
outs = []
th = [threading.Thread(target=lambda: outs.append(NZ.make_brief(con, MON, force=True, ai_fn=slow_ai, tg_fn=lambda c_, t_: (True, "ok")))) for _ in range(2)]
for t in th: t.start()
for t in th: t.join()
ok(len(ai_calls) == 1 and sorted(o is None for o in outs) == [False, True] and free == [True],
   f"Hisobot: parallel ikki so'rov — AI bir marta ({len(ai_calls)}), ikkinchisi «tayyorlanmoqda»; AI paytida qulf bo'sh ({free})")
try: shutil.rmtree(tmp, ignore_errors=True)
except Exception: pass

print()
print(f"Natija: {'HAMMASI O‘TDI' if not fails else f'{len(fails)} ta xato'}")
sys.exit(1 if fails else 0)
