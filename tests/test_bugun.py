import os
"""Bosh sahifa «Bugun» (GET /api/bugun, app/pending.py bugun()), «Mening vazifalarim» (GET /api/mywork), qo'ng'iroqcha
(GET /api/notifications, app/extras.py) va GET /api/me: uchidan-uchigacha HTTP testlar (server ishlab turishi kerak).

Ishga tushirish:  ISFT_TEST_URL=http://127.0.0.1:8000 ISFT_CORE_DB=data/jarvis.db .venv/bin/python tests/test_bugun.py
Qamrov: users jadvalidagi HAR BIR faol lavozim (bittadan xodim) — to'rtala API 200 va to'g'ri shakl; mywork elementining manbai
app/mywork.py SOURCES da va havolasi (view yoki href) bor; hech bir manba yiqilmagan (partial bo'sh); /api/bugun ichidagi ro'yxat va
hisoblagichlar /api/mywork bilan bir xil; «Bugun» ko'rsatkichlari mywork manbalari va bazadagi qiymatlar bilan mos (kesishgan joylarda);
qo'ng'iroqchadagi yangi modul yozuvlari mywork'dagi o'sha ish; Rektorning «Imzo papkasi» (sign) faqat rektor imzosi/tasdig'ini
kutayotgan ishlar va ularning hammasi.
Faqat o'qiydi (qo'ng'iroqchani «o'qildi» qilmaydi).
"""
import datetime as dt, sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import clock as CLK                 # noqa: E402
from app.mywork import SOURCES               # noqa: E402  — manbalar ro'yxati (yagona joy)
from app.pending import ADAPTERS             # noqa: E402
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
N = [0]
TODAY = CLK.today().isoformat()
PD_KEYS = {k for k, _ in ADAPTERS}           # app/pending.py adapterlari (qo'ng'iroqchada kind = adapter kaliti = mywork manbasi)

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def q1(sql, args=()):
    r = q(sql, args); return r[0][0] if r else None

def has_table(t): return bool(q("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)))

def J(r, code=200):
    assert r.status_code == code, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text[:400]}"
    return r.json()

def uid(role):
    return q1("SELECT id FROM users WHERE role=? AND COALESCE(active,1)=1 ORDER BY id LIMIT 1", (role,))

def by_id(items, iid): return next((it for it in items if it["id"] == iid), None)
def cnt(items, iid):
    it = by_id(items, iid); return (it.get("count") or 1) if it else 0

# ---------------------------------------------------------------------------------------------
print("— 0. Kirishsiz")
for p in ("/api/bugun", "/api/mywork", "/api/notifications", "/api/me"):
    ok(httpx.get(B + p).status_code == 401, f"kirishsiz {p} → 401")

ROLES = [(r, u) for r, u in q("SELECT role, MIN(id) FROM users WHERE COALESCE(active,1)=1 GROUP BY role ORDER BY role")]
ok(len(ROLES) >= 25, f"users jadvalida {len(ROLES)} ta faol lavozim")
D = {}

print("\n— 1. Har bir lavozim: to'rtala API 200 va javob shakli")
MW_KEYS = {"id", "source", "kind", "title", "sub", "due", "overdue", "priority", "status", "who", "link", "bucket", "sign", "days"}
NT_KEYS = {"id", "kind", "icon", "level", "title", "sub", "ts", "link", "unread"}
KP_KEYS = {"label", "value", "sub", "tone", "link"}
for role, u in ROLES:
    c = S(u)
    rs = {p: c.get(p) for p in ("/api/me", "/api/mywork", "/api/bugun", "/api/notifications")}
    ok(all(r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json") for r in rs.values()),
       f"{role} #{u}: /api/me, /api/mywork, /api/bugun, /api/notifications → 200 JSON")
    me, mw, bg, nt = (rs[p].json() for p in ("/api/me", "/api/mywork", "/api/bugun", "/api/notifications"))
    D[role] = (u, c, me, mw, bg, nt)
    # /api/me
    ok(me["id"] == u and me["role_key"] == role and me["today"] == TODAY and isinstance(me["allow"], list) and me["name"], f"{role}: /api/me — id, lavozim, bugungi sana")
    # /api/mywork
    its = mw["items"]
    ok(mw["partial"] == [], f"{role}: mywork — hech bir manba yiqilmadi (partial={mw['partial']})")
    ok(all(MW_KEYS <= set(it) for it in its), f"{role}: mywork — {len(its)} ta element to'liq shaklda")
    bad = [it["id"] for it in its if it["source"] not in SOURCES]
    ok(not bad, f"{role}: har bir elementning manbasi app/mywork.py SOURCES da {bad[:3]}")
    bad = [it["id"] for it in its if not (isinstance(it["link"], dict) and (it["link"].get("view") or it["link"].get("href")))]
    ok(not bad, f"{role}: har bir elementda havola (view yoki href) {bad[:3]}")
    ok(len({it["id"] for it in its}) == len(its), f"{role}: mywork id'lari takrorlanmaydi")
    cn = mw["counts"]
    ok(cn["total"] == len(its) and cn["badge"] == len(its) and cn["sign"] == sum(bool(it["sign"]) for it in its)
       and all(cn["by_source"].get(s, 0) == sum(it["source"] == s for it in its) for s in SOURCES), f"{role}: mywork hisoblagichlari (jami {cn['total']}, imzo {cn['sign']})")
    ok(all(isinstance(it["sign"], bool) for it in its), f"{role}: sign — mantiqiy qiymat")
    # /api/bugun = mywork'ning boshi + ko'rsatkichlar
    ok(set(bg) == {"items", "counts", "kpis", "institute"} and bg["institute"] == (role in ("rektor", "kengash")), f"{role}: /api/bugun shakli (institut ko'rsatkichlari: {bg['institute']})")
    ok([it["id"] for it in bg["items"]] == [it["id"] for it in its[:5]], f"{role}: «Sizdan kutilmoqda» = mywork'ning eng yaqin 5 tasi")
    ok({k: v for k, v in bg["counts"].items()} == cn, f"{role}: /api/bugun hisoblagichlari = /api/mywork hisoblagichlari")
    ok(isinstance(bg["kpis"], list) and len(bg["kpis"]) <= 4 and all(KP_KEYS <= set(k) for k in bg["kpis"]), f"{role}: {len(bg['kpis'])} ta ko'rsatkich (≤4), shakli to'g'ri")
    ok(all(k["tone"] in ("", "bad", "warn", "good") and isinstance(k["link"], dict) and (k["link"].get("view") or k["link"].get("href")) and k["label"]
           and isinstance(k["value"], (int, float, str)) for k in bg["kpis"]), f"{role}: ko'rsatkich rangi va havolasi")
    # /api/notifications
    ni = nt["items"]
    ok(set(nt) >= {"items", "unread", "seen_at", "now"} and len(ni) <= 40 and all(NT_KEYS <= set(x) for x in ni), f"{role}: qo'ng'iroqcha — {len(ni)} ta yozuv (≤40), shakli to'g'ri")
    ok(nt["unread"] == sum(bool(x["unread"]) for x in ni), f"{role}: o'qilmaganlar soni = {nt['unread']}")
    ok(all(x["level"] in ("bad", "warn", "info") and isinstance(x["link"], dict) and (x["link"].get("view") or x["link"].get("href")) for x in ni),
       f"{role}: qo'ng'iroqcha — daraja va havola")
    ok([x["ts"] for x in ni] == sorted((x["ts"] for x in ni), reverse=True) and all(x["ts"] <= nt["now"] for x in ni), f"{role}: qo'ng'iroqcha — yangisi tepada, kelajak vaqti yo'q")
    # qo'ng'iroqchadagi yangi modul yozuvlari (app/pending.py) = mywork'dagi o'sha ish
    pdn = [x for x in ni if x["kind"] in PD_KEYS]
    miss = [x["id"] for x in pdn if not (by_id(its, x["id"]) and by_id(its, x["id"])["title"] == x["title"] and by_id(its, x["id"])["source"] == x["kind"])]
    ok(not miss, f"{role}: qo'ng'iroqchadagi {len(pdn)} ta modul yozuvi «Mening vazifalarim»da ham bor {miss[:3]}")
    if len(ni) < 40:   # kesilmagan bo'lsa — mywork'dagi modul ishlari qo'ng'iroqchada ham (qo'ng'iroqcha har adapterdan 6 tagacha oladi)
        want = []
        for k in PD_KEYS:
            ids = [it["id"] for it in its if it["source"] == k]
            if len(ids) <= 6: want += ids
        lost = [i for i in want if not by_id(ni, i)]
        ok(not lost, f"{role}: mywork'dagi modul ishlari qo'ng'iroqchada ham ko'rinadi {lost[:3]}")
    sg = [x for x in ni if x["kind"] in PD_KEYS and by_id(its, x["id"]) and by_id(its, x["id"])["sign"]]
    ok(all(x["level"] in ("warn", "bad") for x in sg), f"{role}: imzo kutayotgan ishlar qo'ng'iroqchada ajralib turadi ({len(sg)})")

# ---------------------------------------------------------------------------------------------
print("\n— 2. «Bugun» ko'rsatkichlari: mywork va baza bilan mos")
def kp(role):
    return {k["label"]: k for k in D[role][4]["kpis"]}
def items(role): return D[role][3]["items"]
EXPECT = {"buxgalteriya": ["Aniqlanmagan to'lovlar", "Bugun kiritilgan to'lovlar", "Kontrakt tushumi"],
          "prorektor_moliya": ["Tasdiq kutayotgan xarajatlar", "Aniqlanmagan to'lovlar", "Kontrakt tushumi"],
          "kadrlar": ["Shartnoma muddati o'tgan", "Attestatsiya muddati o'tgan", "Ochiq vakansiyalar", "Xodimlar (shtat)"],
          "prorektor_yoshlar": ["Turar joy bandligi", "Navbatda", "Turar joy qarzi", "Tadbirlar tasdig'ida"],
          "manaviyat": ["Turar joy bandligi", "Navbatda", "Turar joy qarzi", "Tadbirlar tasdig'ida"],
          "komendant": ["Turar joy bandligi", "Navbatda", "Turar joy qarzi"],
          "oqituvchi": ["Tasdiqlanadigan ishlar", "O'quv dasturlari", "Amaliyot — baholanmagan", "Nashr arizalari"],
          "kafedra": ["Tasdiqlanadigan ishlar", "O'quv dasturlari", "Amaliyot — baholanmagan", "Nashr arizalari"],
          "tyutor": ["Mening guruhlarim", "O'qishda xavf", "Akademik qarzdorlar", "Ijara — tashrif kerak"],
          "amaliyot": ["Hisobot muddati o'tgan", "Baholanmagan", "Biriktirilmagan talabalar", "Baza shartnomalari"],
          "xalqaro": ["Faol shartnomalar", "Chet elda", "Suhbat kutayotgan arizalar"], "yuridik": ["Yuridik ko'rikda"]}
for role, labels in EXPECT.items():
    if role in D:   # to'liq ro'yxat — bugun() ichidagi xato (except bilan yutilgan) ko'rsatkichlarni yo'qotmagan
        ok([k["label"] for k in D[role][4]["kpis"]] == labels, f"{role}: ko'rsatkichlar to'liq — {', '.join(labels)}")
KPI_ROLES = set(EXPECT) | {"imtihon", "akademik", "talabalar", "registrator_xodim", "sirtqi", "ilmiy_bolim", "magistratura", "prorektor_ilmiy"}
for role in D:
    if role not in KPI_ROLES:
        ok(D[role][4]["kpis"] == [], f"{role}: o'z sohasida ko'rsatkich yo'q — bo'sh ro'yxat")

# moliya
bank_n = q1("SELECT COUNT(*) FROM fin_bank_lines WHERE status='aniqlanmagan'")
for role in ("buxgalteriya", "prorektor_moliya"):
    k = kp(role)
    ok(k["Aniqlanmagan to'lovlar"]["value"] == bank_n, f"{role}: aniqlanmagan to'lovlar = bazada {bank_n}")
    ok(cnt(items(role), "fin-bank") == (bank_n if role == "buxgalteriya" else 0), f"{role}: mywork «Aniqlanmagan to'lovlar» qatori soni mos")
    t, p = q("SELECT COALESCE(SUM(contract_amount),0), COALESCE(SUM(paid_amount),0) FROM students WHERE status='faol' AND COALESCE(contract_amount,0)>0")[0]
    ok(k["Kontrakt tushumi"]["value"] == f"{round(100 * p / t, 1)}%", f"{role}: kontrakt tushumi = {round(100 * p / t, 1)}%")
ok(kp("buxgalteriya")["Bugun kiritilgan to'lovlar"]["value"] == q1("SELECT COUNT(*) FROM fin_payments WHERE paid_on=? AND COALESCE(status,'faol')!='storno'", (TODAY,)),
   "buxgalteriya: bugun kiritilgan to'lovlar = bazada")
n = q1("SELECT COUNT(*) FROM fin_expenses WHERE status='kutilmoqda'")
ok(kp("prorektor_moliya")["Tasdiq kutayotgan xarajatlar"]["value"] == n == sum(it["id"].startswith("fin-exp") for it in items("prorektor_moliya")),
   f"prorektor_moliya: tasdiq kutayotgan xarajatlar = mywork qatorlari = {n}")
# kadrlar
k = kp("kadrlar")
v = (k["Shartnoma muddati o'tgan"]["value"] or 0) + int(k["Shartnoma muddati o'tgan"]["sub"].split(":")[-1])
ok(cnt(items("kadrlar"), "hr-contract") == v, f"kadrlar: shartnomalar (o'tgan + 30 kunda) = mywork qatori ({v})")
ok(cnt(items("kadrlar"), "hr-attest") == k["Attestatsiya muddati o'tgan"]["value"], "kadrlar: attestatsiya = mywork qatori")
# yoshlar
cap = q1("SELECT COALESCE(SUM(rm.beds),0) FROM yj_rooms rm JOIN yj_buildings b ON b.id=rm.building_id WHERE COALESCE(b.active,1)=1")
live = q1("SELECT COUNT(*) FROM yj_residents WHERE status IN ('band','yashaydi')")
for role in ("prorektor_yoshlar", "manaviyat", "komendant"):
    k = kp(role)
    ok(k["Turar joy bandligi"]["value"] == f"{round(100 * live / cap) if cap else 0}%" and k["Turar joy bandligi"]["sub"] == f"{live} / {cap} o'rin", f"{role}: bandlik {live}/{cap}")
    ok(k["Navbatda"]["value"] == q1("SELECT COUNT(*) FROM yj_applications WHERE status IN ('yangi','navbatda')"), f"{role}: navbatdagi arizalar = bazada")
    if role != "komendant":
        ok(k["Tadbirlar tasdig'ida"]["value"] == q1("SELECT COUNT(*) FROM events WHERE status='tasdiqlashda'"), f"{role}: tasdiqdagi tadbirlar = bazada")
ok(kp("prorektor_yoshlar")["Tadbirlar tasdig'ida"]["value"] == sum(it["id"].startswith("yj-e") for it in items("prorektor_yoshlar")),
   "prorektor_yoshlar: tasdiqdagi tadbirlar = mywork imzo qatorlari")
# o'qituvchi / kafedra
for role in ("oqituvchi", "kafedra"):
    k, its = kp(role), items(role)
    ok(k["Tasdiqlanadigan ishlar"]["value"] == cnt(its, "chk"), f"{role}: tasdiqlanadigan ishlar = mywork «Ishlarni tekshirish» ({cnt(its, 'chk')})")
    ok(k["O'quv dasturlari"]["value"] == sum(it["source"] == "sillabus" for it in its), f"{role}: o'quv dasturlari = mywork sillabus qatorlari")
    ok(k["Amaliyot — baholanmagan"]["value"] == cnt(its, "am-baholanmagan"), f"{role}: amaliyot baholanmagan = mywork qatori")
# tyutor
u = D["tyutor"][0]; k = kp("tyutor")
ok(k["Mening guruhlarim"]["value"] == q1("SELECT COUNT(*) FROM tutor_groups WHERE user_id=?", (u,)), "tyutor: guruhlar soni = bazada")
# amaliyot bo'limi
k, its = kp("amaliyot"), items("amaliyot")
ok(k["Hisobot muddati o'tgan"]["value"] == cnt(its, "am-hisobot_kechikdi") and k["Baholanmagan"]["value"] == cnt(its, "am-baholanmagan"),
   "amaliyot: kechikkan hisobot va baholanmagan = mywork qatorlari")
ok(k["Baza shartnomalari"]["value"] == cnt(its, "am-agr"), "amaliyot: tugayotgan baza shartnomalari = mywork qatori")
# xalqaro / yuridik
ok(kp("xalqaro")["Suhbat kutayotgan arizalar"]["value"] == cnt(items("xalqaro"), "xq-app"), "xalqaro: suhbat kutayotgan arizalar = mywork qatori")
ok(kp("xalqaro")["Faol shartnomalar"]["value"] == q1("SELECT COUNT(*) FROM intl_agreements WHERE status='faol'"), "xalqaro: faol shartnomalar = bazada")
ok(kp("yuridik")["Yuridik ko'rikda"]["value"] == sum(it["id"].startswith("xq-y") for it in items("yuridik")) == q1("SELECT COUNT(*) FROM intl_agreements WHERE status='yuridik'"),
   "yuridik: ko'rikdagi shartnomalar = mywork qatorlari = bazada")
# Talaba harakati (flows) va talaba so'rovlari
for role in ("imtihon", "akademik", "talabalar", "registrator_xodim", "sirtqi"):
    if role not in D: continue
    ks, its = D[role][4]["kpis"], items(role)
    ok(1 <= len(ks) <= 4, f"{role}: {len(ks)} ta ko'rsatkich")
    for k in ks:
        tab = k["link"].get("tab")
        if k["link"].get("view") == "flows" and tab in ("apellyatsiya", "qayta", "kochirish"):
            ok(k["value"] == cnt(its, f"af-{tab}"), f"{role}: «{k['label']}» {k['value']} = mywork «Talaba harakati» qatori")
        if k["label"] == "Talaba kabinetidan so'rovlar":
            ok(k["value"] == cnt(its, "stu-req"), f"{role}: talaba so'rovlari {k['value']} = mywork qatori")
ka = kp("akademik")
ok("Kreditni tan olish" in ka, "akademik: «Kreditni tan olish» ko'rsatkichi 4 talik chegarada tushib qolmagan")
ok(ka["Kreditni tan olish"]["value"] == cnt(items("akademik"), "xq-cr") == q1("SELECT COUNT(*) FROM intl_applications WHERE credit_status='kutilmoqda'"),
   "akademik: kredit tan olish = mywork qatori = bazada")
for role in ("talabalar", "registrator_xodim", "sirtqi"):
    ok(D[role][4]["kpis"][0]["label"] == "Talaba kabinetidan so'rovlar", f"{role}: birinchi ko'rsatkich — talaba kabineti so'rovlari")
# ilmiy
for role in ("ilmiy_bolim", "magistratura", "prorektor_ilmiy"):
    if role not in D: continue
    its = [it for it in items(role) if it["source"] == "ilmiy"]
    for k in D[role][4]["kpis"]:
        if k["link"].get("view") != "ilmiy": continue
        ok(any(it["link"].get("tab") == k["link"].get("tab") and (it.get("count") or 0) == k["value"] for it in its),
           f"{role}: «{k['label']}» {k['value']} — mywork'da shu bo'lim va son bilan qator bor")

# ---------------------------------------------------------------------------------------------
print("\n— 3. Rektor «Imzo papkasi»: faqat rektor imzosi/tasdig'ini kutayotganlar — va hammasi")
ru, rc, *_ = D["rektor"]
its = D["rektor"][3]["items"]
sg = [it for it in its if it["sign"]]
print(f"  rektor: {len(sg)} ta imzo ishi — " + ", ".join(sorted({f'{it['source']}/{it['kind']}' for it in sg})))
SIGN_WORDS = ("imzo", "tasdi", "rezolyutsiya", "kelishuv")

def rector_sign_ok(it):
    s, k, i = it["source"], it["kind"], it["id"]
    if s == "buyruq":
        return k == "imzo" and q1("SELECT status FROM orders WHERE id=?", (it["link"]["order"],)) in ("yuborilgan", "kelishilgan")
    if s == "kadrlar" and i.startswith("hr-v"):
        return q1("SELECT status FROM hr_vacancies WHERE id=?", (int(i[4:]),)) == "tasdiqda"
    if s == "kadrlar" and i.startswith("hr-c"):
        return q1("SELECT stage FROM hr_candidates WHERE id=?", (int(i[4:]),)) == "tanlandi"
    if s == "xalqaro":
        return i.startswith("xq-s") and q1("SELECT status FROM intl_agreements WHERE id=?", (int(i[4:]),)) == "imzoda"
    if s == "devon":
        r = q("SELECT status, resolver_role FROM in_letters WHERE id=?", (int(i.split("-", 1)[1]),))
        return bool(r) and r[0] == ("royxatda", "rektor")
    if s in ("qabul", "rejalar", "it_req"):   # W5 modullari: imzo/tasdiq so'zi bo'lishi shart
        return any(w in (it["title"] + " " + it["kind"]).lower() for w in SIGN_WORDS)
    return False

bad = [f"{it['source']}/{it['kind']}/{it['id']}" for it in sg if not rector_sign_ok(it)]
ok(not bad, f"Rektor: imzo papkasidagi har bir ish haqiqatan rektor imzosini kutmoqda {bad[:4]}")
ok(not any(it["source"] in ("majlis", "portal", "markaz", "murojaat", "xodim", "agent", "sillabus", "moliya", "yoshlar", "ilmiy", "amaliyot",
                            "harakat", "tekshiruv", "talaba") for it in sg), "Rektor: topshiriq, xat, murojaat, AI taklifi va boshqa bo'lim tasdiqlari imzo papkasida emas")
ok(not any(it["source"] == "buyruq" and it["kind"] == "kelishuv" for it in its), "Rektor: «kelishuv» (o'quv prorektori bosqichi) rektor ro'yxatida yo'q")
ok(D["rektor"][3]["counts"]["sign"] == len(sg), f"Rektor: counts.sign = {len(sg)}")
# to'liqlik: rektor imzosini kutayotgan har bir obyekt imzo papkasida
want = {f"ori{r[0]}" for r in q("SELECT id FROM orders WHERE status IN ('yuborilgan','kelishilgan')")}
ok(want == {it["id"] for it in sg if it["source"] == "buyruq"}, f"Rektor: imzoga yuborilgan barcha buyruqlar papkada ({len(want)})")
if has_table("hr_vacancies"):
    want = {f"hr-v{r[0]}" for r in q("SELECT id FROM hr_vacancies WHERE status='tasdiqda'")} | {f"hr-c{r[0]}" for r in q("SELECT id FROM hr_candidates WHERE stage='tanlandi'")}
    ok(want == {it["id"] for it in sg if it["source"] == "kadrlar"}, f"Rektor: tasdiqdagi vakansiya va tanlangan nomzodlar papkada ({len(want)})")
want = {f"xq-s{r[0]}" for r in q("SELECT id FROM intl_agreements WHERE status='imzoda'")}
ok(want == {it["id"] for it in sg if it["source"] == "xalqaro"}, f"Rektor: imzodagi xalqaro shartnomalar papkada ({len(want)})")
if has_table("in_letters"):
    want = {f"devon-{r[0]}" for r in q("SELECT id FROM in_letters WHERE status='royxatda' AND resolver_role='rektor' ORDER BY in_date LIMIT 30")}
    ok(want == {it["id"] for it in sg if it["source"] == "devon"}, f"Rektor: rezolyutsiya kutayotgan kiruvchi xatlar papkada ({len(want)})")
nt = D["rektor"][5]["items"]
ok(all(x["level"] in ("warn", "bad") for x in nt if x["kind"] in PD_KEYS and by_id(sg, x["id"])), "Rektor: qo'ng'iroqchada imzo ishlari ogohlantirish darajasida")
# boshqa lavozimlarda imzo belgisi faqat o'z tasdig'i uchun
ALLOWED_SIGN = {"prorektor_oquv": {("buyruq", "kelishuv"), ("devon", "kiruvchi")}, "prorektor_moliya": {("moliya", "xarajat")},
                "prorektor_yoshlar": {("yoshlar", "tadbir"), ("devon", "kiruvchi")}, "prorektor_ilmiy": {("ilmiy", "grants"), ("devon", "kiruvchi")}}
for role, (u, c, me, mw, bg, nt) in D.items():
    if role == "rektor": continue
    s = {(it["source"], it["kind"]) for it in mw["items"] if it["sign"]}
    extra = {x for x in s if x not in ALLOWED_SIGN.get(role, set()) and x[0] not in ("qabul", "rejalar", "it_req")}
    ok(not extra, f"{role}: imzo belgisi faqat o'z tasdig'idagi ishlarda {sorted(extra)[:3]}")
for it in D["prorektor_oquv"][3]["items"]:
    if it["source"] == "buyruq" and it["kind"] == "kelishuv":
        ok(it["sign"] and q1("SELECT status FROM orders WHERE id=?", (it["link"]["order"],)) == "yuborilgan", f"prorektor_oquv: kelishuv {it['id']} — prorektor kelishuvini kutmoqda")

print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")
