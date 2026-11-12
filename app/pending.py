"""Kutilayotgan ishlar — yagona manba (modullar bo'yicha adapterlar).

Har bir funksiya `(c: Ctx, I) -> list[dict]` — I = mywork._item (bir xil element ko'rinishi). Element qo'shimcha
`sign: True` belgisini olishi mumkin: rahbar imzosi yoki tasdig'ini kutayotgan ish («Imzo papkasi»).
«Mening vazifalarim» (app/mywork.py), qo'ng'iroqcha (app/extras.py) va bosh sahifadagi «Sizdan kutilmoqda» bloki
shu manbadan o'qiydi. Har bir adapter faqat o'qiydi (audit yozmaydi) va o'z modulining ruxsat qoidasiga amal qiladi.
"""
import datetime as dt
from . import clock, db

_con = None

def bind(con):
    global _con
    _con = con

def _one(sql, a=()):
    r = db.one(_con, sql, a)
    return (r or {}).get("n") or 0

def _today(): return clock.today()
def _fmt(n): return f"{int(n):,}".replace(",", " ")

# ---------------------------------------------------------------------------------------------
def moliya(c, I) -> list:
    k, out = c.role.key, []
    if k == "buxgalteriya":
        r = db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s, MIN(line_date) d FROM fin_bank_lines WHERE status='aniqlanmagan'")
        if r and r["n"]:
            old = _one("SELECT COUNT(*) n FROM fin_bank_lines WHERE status='aniqlanmagan' AND line_date<?", ((_today() - dt.timedelta(days=3)).isoformat(),))
            out.append(I("moliya", "bank", "fin-bank", f"Aniqlanmagan to'lovlar: {r['n']} ta · {_fmt(r['s'])} so'm",
                         "Bank ko'chirmasidagi cheklar — talabani tasdiqlang" + (f" · {old} tasi 3 kundan eski" if old else ""), None,
                         {"view": "moliya", "tab": "bank"}, "bolimga", "aniqlanmagan", "high" if old else "mid", r["n"], icon="money"))
    if k == "prorektor_moliya":
        for e in db.rows(_con, "SELECT id, category, amount, payee, created_at FROM fin_expenses WHERE status='kutilmoqda' ORDER BY id"):
            it = I("moliya", "xarajat", f"fin-exp{e['id']}", f"Xarajat tasdig'i: {e['category']} — {_fmt(e['amount'])} so'm",
                   f"{e['payee'] or ''} · kiritilgan {str(e['created_at'])[:10]}", None, {"view": "moliya", "tab": "expenses"}, "menga", "kutilmoqda", "mid", icon="money")
            it["sign"] = True; out.append(it)
    return out

def kadrlar(c, I) -> list:
    k, out = c.role.key, []
    if k == "rektor":
        for v in db.rows(_con, "SELECT id, position, unit_key FROM hr_vacancies WHERE status='tasdiqda' ORDER BY id"):
            it = I("kadrlar", "vakansiya", f"hr-v{v['id']}", f"Vakansiya tasdig'i: {v['position']}", f"bo'lim: {v['unit_key']} · Kadrlar bo'limi",
                   None, {"view": "kadrlar", "tab": "hire"}, "menga", "tasdiqda", "mid", icon="idcard"); it["sign"] = True; out.append(it)
        for x in db.rows(_con, """SELECT k.id, k.full_name, v.position FROM hr_candidates k JOIN hr_vacancies v ON v.id=k.vacancy_id
                                  WHERE k.stage='tanlandi' ORDER BY k.id"""):
            it = I("kadrlar", "nomzod", f"hr-c{x['id']}", f"Nomzod tasdig'i: {x['full_name']}", f"{x['position']} · Kadrlar tanlagan",
                   None, {"view": "kadrlar", "tab": "hire"}, "menga", "tanlandi", "mid", icon="idcard"); it["sign"] = True; out.append(it)
    if k == "kadrlar":
        from . import kadrlar as KD
        try: q = KD.kpi(c, "full")
        except Exception: q = {}
        if q.get("contract_expired") or q.get("contract_30"):
            n = (q.get("contract_expired") or 0) + (q.get("contract_30") or 0)
            out.append(I("kadrlar", "shartnoma", "hr-contract", f"Mehnat shartnomalari: {q.get('contract_expired', 0)} ta muddati o'tgan, {q.get('contract_30', 0)} ta 30 kunda tugaydi",
                         "Uzaytiring yoki bo'shatishni rasmiylashtiring", None, {"view": "kadrlar", "tab": "home"}, "bolimga", "", "high" if q.get("contract_expired") else "mid", n, icon="idcard"))
        if q.get("attest_overdue"):
            out.append(I("kadrlar", "attestatsiya", "hr-attest", f"Attestatsiya muddati o'tgan: {q['attest_overdue']} ta xodim", "5 yillik muddat · jadvalga kiriting",
                         None, {"view": "kadrlar", "tab": "home"}, "bolimga", "", "mid", q["attest_overdue"], icon="idcard"))
        n = _one("SELECT COUNT(*) n FROM hr_vacancies WHERE status='taklif'")
        if n: out.append(I("kadrlar", "vakansiya", "hr-vprop", f"Bo'limlardan vakansiya takliflari: {n} ta", "Ko'rib chiqing va rektor tasdig'iga yuboring",
                           None, {"view": "kadrlar", "tab": "hire"}, "bolimga", "taklif", "mid", n, icon="idcard"))
        n = _one("SELECT COUNT(*) n FROM hr_candidates WHERE stage='tasdiqlandi'")
        if n: out.append(I("kadrlar", "nomzod", "hr-cord", f"Rektor tasdiqlagan nomzodlar: {n} ta — buyruq loyihasini tuzing", "Ishga qabul buyrug'i",
                           None, {"view": "kadrlar", "tab": "hire"}, "bolimga", "tasdiqlandi", "high", n, icon="idcard"))
        n = _one("SELECT COUNT(*) n FROM hr_dismissals WHERE status IN ('ariza','varaqa')")
        if n: out.append(I("kadrlar", "boshatish", "hr-dis", f"Bo'shatish jarayonida: {n} ta", "Topshirish varaqasi va buyruq",
                           None, {"view": "kadrlar", "tab": "dismiss"}, "bolimga", "", "mid", n, icon="idcard"))
    return out

def ilmiy(c, I) -> list:
    from . import ilmiy as IL
    out = []
    for a in IL.alerts(c):
        it = I("ilmiy", a.get("kind", "ilmiy"), f"il-{a.get('kind')}-{a.get('flag', '')}-{len(out)}", a["text"], "Ilmiy faoliyat", None,
               {"view": "ilmiy", "tab": a.get("tab")}, "menga", "", "mid", a.get("n"), icon="flask")
        if c.role.key == "prorektor_ilmiy" and a.get("kind") == "grants": it["sign"] = True
        out.append(it)
    return out

def xalqaro(c, I) -> list:
    k, out = c.role.key, []
    if k == "rektor":
        for a in db.rows(_con, "SELECT id, partner_name, kind, country FROM intl_agreements WHERE status='imzoda' ORDER BY id"):
            it = I("xalqaro", "shartnoma", f"xq-s{a['id']}", f"Shartnoma imzosi: {a['partner_name']} ({a['country']})", f"{a['kind']} · yuridik ko'rikdan o'tgan",
                   None, {"view": "xalqaro", "tab": "agreements"}, "menga", "imzoda", "mid", icon="globe"); it["sign"] = True; out.append(it)
    if k == "yuridik":
        for a in db.rows(_con, "SELECT id, partner_name, kind, country FROM intl_agreements WHERE status='yuridik' ORDER BY id"):
            out.append(I("xalqaro", "shartnoma", f"xq-y{a['id']}", f"Yuridik ko'rik: {a['partner_name']} ({a['country']})", f"{a['kind']} · xulosangizni kutmoqda",
                         None, {"view": "xalqaro", "tab": "agreements"}, "menga", "yuridik", "mid", icon="globe"))
    if k == "akademik":
        n = _one("SELECT COUNT(*) n FROM intl_applications WHERE credit_status='kutilmoqda'")
        if n: out.append(I("xalqaro", "kredit", "xq-cr", f"Almashinuvdan qaytganlar — kreditni tan olish: {n} ta", "Xalqaro hamkorlik bo'limidan",
                           None, {"view": "xalqaro", "tab": "credits"}, "bolimga", "", "mid", n, icon="globe"))
    if k in ("xalqaro", "prorektor_ilmiy"):
        n = _one("SELECT COUNT(*) n FROM intl_applications WHERE status='ariza' AND eligible=1 AND interview IS NULL")
        if n: out.append(I("xalqaro", "ariza", "xq-app", f"Almashinuv arizalari — suhbat bahosi kutilmoqda: {n} ta", "Komissiya", None,
                           {"view": "xalqaro", "tab": "exchange"}, "bolimga", "", "mid", n, icon="globe"))
    if k == "xalqaro":
        from . import xalqaro as XQ
        for a in XQ.alerts(c):
            out.append(I("xalqaro", "muddat", f"xq-al{len(out)}", a["text"], "Hamkorlik shartnomasi", None, {"view": "xalqaro", "tab": "agreements"},
                         "bolimga", "", "mid", icon="globe"))
        n = _one("SELECT COUNT(*) n FROM intl_agreements WHERE status='qoralama'")
        if n: out.append(I("xalqaro", "shartnoma", "xq-dr", f"Shartnoma qoralamalari: {n} ta — yuridik ko'rikka yuboring", "", None,
                           {"view": "xalqaro", "tab": "agreements"}, "bolimga", "qoralama", None, n, icon="globe"))
    return out

def yoshlar(c, I) -> list:
    k, out = c.role.key, []
    if k == "prorektor_yoshlar":
        for e in db.rows(_con, "SELECT id, title, date FROM events WHERE status='tasdiqlashda' ORDER BY date"):
            it = I("yoshlar", "tadbir", f"yj-e{e['id']}", f"Tadbir tasdig'i: {e['title']}", f"o'tkazilish sanasi {e['date']}", e["date"],
                   {"view": "yoshlar", "tab": "tadbirlar"}, "menga", "tasdiqlashda", "mid", icon="gift"); it["sign"] = True; out.append(it)
    if k in ("manaviyat", "komendant", "prorektor_yoshlar"):
        n = _one("SELECT COUNT(*) n FROM yj_applications WHERE status='yangi' AND verified=0")
        if n: out.append(I("yoshlar", "ariza", "yj-a", f"Turar joy arizalari — hujjat tekshiruvi: {n} ta", "Imtiyoz toifasi tasdiqlanmagan", None,
                           {"view": "yoshlar", "tab": "arizalar"}, "bolimga", "yangi", "mid", n, icon="gift"))
        n = _one("SELECT COUNT(*) n FROM yj_residents WHERE status='band' AND reserved_at<?", ((_today() - dt.timedelta(days=7)).isoformat(),))
        if n: out.append(I("yoshlar", "bron", "yj-r", f"7 kundan ortiq joylashmagan bronlar: {n} ta", "Bekor qilib navbatdagiga bering", None,
                           {"view": "yoshlar", "tab": "joylar"}, "bolimga", "", "high", n, icon="gift"))
    return out

def amaliyot(c, I) -> list:
    from . import amaliyot as AM
    m = AM.mode(c)
    if m not in ("full", "kafedra", "oqituvchi"): return []
    a = AM.alerts(c); out = []
    for f, n in (a.get("counts") or {}).items():
        if not n or (m == "oqituvchi" and f != "baholanmagan"): continue
        out.append(I("amaliyot", f, f"am-{f}", f"Amaliyot — {AM.FLAG_TITLES.get(f, f)}: {n} ta talaba", "Amaliyot bo'limi", None,
                     {"view": "amaliyot", "tab": "ogohlantirish"}, "bolimga" if m == "full" else "menga", "", "high" if f == "hisobot_kechikdi" else "mid", n, icon="pin"))
    if m == "full" and a.get("agreements"):
        out.append(I("amaliyot", "shartnoma", "am-agr", f"Amaliyot bazalari: {len(a['agreements'])} ta shartnoma tugayapti yoki tugagan", "", None,
                     {"view": "amaliyot", "tab": "bazalar"}, "bolimga", "", "mid", len(a["agreements"]), icon="pin"))
    return out

def harakat(c, I) -> list:
    from . import academic_flows as AF
    m = AF.mode(c)
    if m not in ("full", "kafedra", "imtihon", "sirtqi", "bux"): return []
    meta = AF.meta(c); out = []
    T = {"apellyatsiya": "Apellyatsiyalar — qaror kutilmoqda", "qayta": "Qayta o'qish — qaror kutilmoqda" if m != "bux" else "Qayta o'qish — to'lanmagan",
         "kochirish": "Ko'chirish / tiklash arizalari"}
    for t in meta.get("tabs", []):
        if t["key"] in T and t.get("count"):
            out.append(I("harakat", t["key"], f"af-{t['key']}", f"{T[t['key']]}: {t['count']} ta", "Talaba harakati", None,
                         {"view": "flows", "tab": t["key"]}, "bolimga", "", "high" if t["key"] == "apellyatsiya" else "mid", t["count"], icon="cap"))
    return out

def tekshiruv(c, I) -> list:
    if c.role.key not in ("oqituvchi", "kafedra"): return []
    r = db.one(_con, """SELECT COUNT(*) n, COUNT(DISTINCT w.batch_id) b FROM chk_works w JOIN chk_batches b ON b.id=w.batch_id
                        WHERE b.user_id=? AND COALESCE(b.deleted,0)=0 AND COALESCE(w.deleted,0)=0 AND w.status IN ('tekshirildi','qolda')""", (c.user["id"],))
    if not r or not r["n"]: return []
    return [I("tekshiruv", "ish", "chk", f"Tekshirilgan ishlar — tasdiqlashingiz kerak: {r['n']} ta", f"{r['b']} ta tekshiruvda · AI taklifi yoki qo'lda", None,
              {"view": "tekshiruv"}, "menga", "", "mid", r["n"], icon="check")]

def talaba(c, I) -> list:
    from . import student_portal as SP
    unit = SP.STAFF_UNIT.get(c.role.key)
    if not unit: return []
    r = db.one(_con, f"SELECT COUNT(*) n, MIN(r.created_at) d {SP.REQ_FROM} WHERE {SP._scope_sql(unit)} AND r.status='yangi'")
    if not r or not r["n"]: return []
    return [I("talaba", "sorov", "stu-req", f"Talaba kabinetidan so'rovlar: {r['n']} ta", f"ma'lumotnoma, uzrli sabab va boshqalar · eng eskisi {str(r['d'])[:10]}",
              None, {"view": "talaba_xodim", "href": "/talaba/xodim"}, "bolimga", "yangi", "mid", r["n"], icon="user")]

def _simple(mod_name, src_key):
    """W5 modullari (devon, qabul, rejalar, it_requests) — {kind,title,sub,due,view,src,sign} → mywork elementi."""
    def fn(c, I) -> list:
        import importlib
        M = importlib.import_module(f".{mod_name}", __package__)
        out = []
        for i, x in enumerate(M.pending(c) or []):
            it = I(src_key, x.get("kind") or "ish", f"{src_key}-{x.get('id', i)}", x.get("title") or "", x.get("sub") or "", x.get("due"),
                   {k: v for k, v in (("view", x.get("view")), ("tab", x.get("tab")), ("href", x.get("href"))) if v}, "menga", "", None, None, icon="inbox")
            if x.get("sign"): it["sign"] = True
            out.append(it)
        return out
    return fn

ADAPTERS = [("devon", _simple("devon", "devon")), ("qabul", _simple("qabul", "qabul")), ("rejalar", _simple("rejalar", "rejalar")),
            ("it_req", _simple("it_requests", "it_req")),
            ("moliya", moliya), ("kadrlar", kadrlar), ("ilmiy", ilmiy), ("xalqaro", xalqaro), ("yoshlar", yoshlar),
            ("amaliyot", amaliyot), ("harakat", harakat), ("tekshiruv", tekshiruv), ("talaba", talaba),
            ("masofaviy", _simple("masofaviy", "masofaviy")), ("testbank", _simple("testbank", "testbank")),
            ("paket", _simple("paket", "paket"))]

# =============================================================================================
# «Bugun» — lavozimning o'z sohasidagi 2–4 ko'rsatkichi (bosh sahifa). Institut ko'rsatkichlari — faqat rektor va kengash.
# Har bir element: {label, value, sub, tone: ""|"bad"|"warn"|"good", link}
# =============================================================================================
def _k(label, value, sub="", tone="", link=None): return {"label": label, "value": value, "sub": sub, "tone": tone, "link": link}

def _mw_count(c, src):
    from . import mywork as MW
    try: return sum(1 for it in MW.collect(c)["items"] if it["source"] == src)
    except Exception: return 0

def _contract_pct():
    r = db.one(_con, "SELECT COALESCE(SUM(contract_amount),0) t, COALESCE(SUM(paid_amount),0) p FROM students WHERE status='faol' AND COALESCE(contract_amount,0)>0")
    return (round(100 * r["p"] / r["t"], 1), r["t"] - r["p"]) if r and r["t"] else (None, 0)

def _bank(): return db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM fin_bank_lines WHERE status='aniqlanmagan'") or {"n": 0, "s": 0}

def _mln(v): return f"{v / 1e6:,.1f} mln".replace(",", " ")

def bugun(c) -> list:
    k = c.role.key
    td = _today().isoformat()
    out = []
    try:
        if k in ("buxgalteriya", "prorektor_moliya"):
            b = _bank()
            if k == "prorektor_moliya":
                n = _one("SELECT COUNT(*) n FROM fin_expenses WHERE status='kutilmoqda'")
                out.append(_k("Tasdiq kutayotgan xarajatlar", n, "50 mln dan katta yoki moddadan oshgan", "warn" if n else "good", {"view": "moliya", "tab": "expenses"}))
            out.append(_k("Aniqlanmagan to'lovlar", b["n"], f"{_fmt(b['s'])} so'm · talabaga bog'lang", "bad" if b["n"] else "good", {"view": "moliya", "tab": "bank"}))
            r = db.one(_con, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) s FROM fin_payments WHERE paid_on=? AND COALESCE(status,'faol')!='storno'", (td,)) if k == "buxgalteriya" else None
            if r is not None: out.append(_k("Bugun kiritilgan to'lovlar", r["n"], f"{_fmt(r['s'])} so'm", "", {"view": "moliya", "tab": "payments"}))
            pct, debt = _contract_pct()
            if pct is not None: out.append(_k("Kontrakt tushumi", f"{pct}%", f"qarz {_mln(debt)} so'm", "warn" if pct < 85 else "", {"view": "moliya"}))
        elif k == "kadrlar":
            from . import kadrlar as KD
            q = KD.kpi(c, "full")
            out += [_k("Shartnoma muddati o'tgan", q["contract_expired"], f"30 kunda tugaydi: {q['contract_30']}", "bad" if q["contract_expired"] else "good", {"view": "kadrlar", "tab": "home"}),
                    _k("Attestatsiya muddati o'tgan", q["attest_overdue"], f"90 kun ichida: {q['attest_soon']}", "warn" if q["attest_overdue"] else "", {"view": "kadrlar", "tab": "home"}),
                    _k("Ochiq vakansiyalar", q["vacancies_open"], f"rektor tasdig'ida: {q['vacancies_pending']} · bo'lim taklifi: {q['vacancies_proposed']}", "", {"view": "kadrlar", "tab": "hire"}),
                    _k("Xodimlar (shtat)", q["headcount"], f"bo'sh stavka: {q['vacant_rates']}", "", {"view": "kadrlar", "tab": "staffing"})]
        elif k in ("prorektor_yoshlar", "manaviyat", "komendant"):
            cap = _one("SELECT COALESCE(SUM(rm.beds),0) n FROM yj_rooms rm JOIN yj_buildings b ON b.id=rm.building_id WHERE COALESCE(b.active,1)=1")
            live = _one("SELECT COUNT(*) n FROM yj_residents WHERE status IN ('band','yashaydi')")
            q = _one("SELECT COUNT(*) n FROM yj_applications WHERE status IN ('yangi','navbatda')")
            debt = _one("SELECT COALESCE(SUM(amount-paid),0) n FROM yj_charges WHERE due<? AND paid<amount", (td,))
            out += [_k("Turar joy bandligi", f"{round(100 * live / cap) if cap else 0}%", f"{live} / {cap} o'rin", "", {"view": "yoshlar", "tab": "joylar"}),
                    _k("Navbatda", q, "ariza · imtiyoz ballari bo'yicha", "warn" if q else "", {"view": "yoshlar", "tab": "arizalar"}),
                    _k("Turar joy qarzi", _mln(debt), "muddati o'tgan to'lovlar", "warn" if debt else "", {"view": "yoshlar", "tab": "tolov"})]
            if k != "komendant":
                n = _one("SELECT COUNT(*) n FROM events WHERE status='tasdiqlashda'")
                out.append(_k("Tadbirlar tasdig'ida", n, "", "warn" if n and k == "prorektor_yoshlar" else "", {"view": "yoshlar", "tab": "tadbirlar"}))
        elif k in ("oqituvchi", "kafedra"):
            r = db.one(_con, """SELECT COUNT(*) n FROM chk_works w JOIN chk_batches b ON b.id=w.batch_id WHERE b.user_id=? AND COALESCE(b.deleted,0)=0
                                AND COALESCE(w.deleted,0)=0 AND w.status IN ('tekshirildi','qolda')""", (c.user["id"],))
            out.append(_k("Tasdiqlanadigan ishlar", r["n"] if r else 0, "Ishlarni tekshirish", "warn" if r and r["n"] else "", {"view": "tekshiruv"}))
            out.append(_k("O'quv dasturlari", _mw_count(c, "sillabus"), "sizdan harakat kutilmoqda", "", {"view": "syllabus"}))
            from . import amaliyot as AMm
            try: am = AMm.alerts(c)["counts"].get("baholanmagan", 0)
            except Exception: am = 0
            out.append(_k("Amaliyot — baholanmagan", am, "7 kundan ortiq", "warn" if am else "", {"view": "amaliyot", "tab": "ogohlantirish"}))
            from . import ilmiy as ILm
            pubs = sum(a.get("n") or 0 for a in ILm.alerts(c) if a.get("kind") == "pubs")
            out.append(_k("Nashr arizalari", pubs, "tekshiruv yoki tuzatish kutmoqda" if k == "kafedra" else "qaytarilgan", "warn" if pubs else "", {"view": "ilmiy", "tab": "nashrlar"}))
        elif k == "tyutor":
            from . import student_ops as SO
            w = c.student_scope("s")
            m = SO.risk_metrics(_con, w)
            g = _one(f"SELECT COUNT(*) n FROM tutor_groups WHERE user_id={int(c.user['id'])}")
            out += [_k("Mening guruhlarim", g, f"{m['students']} faol talaba", "", {"view": "ops"}),
                    _k("O'qishda xavf", m["at_risk"]["n"], "o'z guruhlaringizda", "bad" if m["at_risk"]["n"] else "good", {"view": "ops"}),
                    _k("Akademik qarzdorlar", m["debtors"]["n"], "o'z guruhlaringizda", "warn" if m["debtors"]["n"] else "", {"view": "reyting"})]
            n = _one(f"""SELECT COUNT(*) n FROM yj_rentals x JOIN students s ON s.id=x.student_id WHERE s.status='faol' AND {w}
                         AND (x.last_visit IS NULL OR x.last_visit<?)""", ((_today() - dt.timedelta(days=90)).isoformat(),))
            out.append(_k("Ijara — tashrif kerak", n, "90 kundan beri tashrif yo'q", "warn" if n else "", {"view": "yoshlar", "tab": "ijara"}))
        elif k in ("imtihon", "akademik", "talabalar", "registrator_xodim", "sirtqi"):
            from . import academic_flows as AF
            if AF.mode(c):
                for t in AF.meta(c).get("tabs", []):
                    if t["key"] in ("apellyatsiya", "qayta", "kochirish", "sessiya") and t.get("count") is not None:
                        out.append(_k(t["title"], t["count"], "ochiq" if t["key"] != "sessiya" else "joriy sessiyalar", "warn" if t["key"] == "apellyatsiya" and t["count"] else "",
                                      {"view": "flows", "tab": t["key"]}))
            if k in ("talabalar", "registrator_xodim", "sirtqi"):
                from . import student_portal as SP
                u = SP.STAFF_UNIT.get(k)
                n = _one(f"SELECT COUNT(*) n {SP.REQ_FROM} WHERE {SP._scope_sql(u)} AND r.status='yangi'") if u else 0
                out.insert(0, _k("Talaba kabinetidan so'rovlar", n, "ko'rib chiqilmagan", "warn" if n else "good", {"view": "talaba_xodim", "href": "/talaba/xodim"}))
            if k == "akademik":   # 4 ta joydan biri — kesishda (out[:4]) tushib qolmasin
                n = _one("SELECT COUNT(*) n FROM intl_applications WHERE credit_status='kutilmoqda'")
                out.insert(min(3, len(out)), _k("Kreditni tan olish", n, "almashinuvdan qaytganlar", "warn" if n else "", {"view": "xalqaro", "tab": "credits"}))
            out = out[:4]
        elif k == "amaliyot":
            from . import amaliyot as AMm
            a = AMm.alerts(c)
            cn = a.get("counts", {})
            out += [_k("Hisobot muddati o'tgan", cn.get("hisobot_kechikdi", 0), "talaba", "bad" if cn.get("hisobot_kechikdi") else "good", {"view": "amaliyot", "tab": "ogohlantirish"}),
                    _k("Baholanmagan", cn.get("baholanmagan", 0), "7 kundan ortiq", "warn" if cn.get("baholanmagan") else "", {"view": "amaliyot", "tab": "ogohlantirish"}),
                    _k("Biriktirilmagan talabalar", sum(u["n"] for u in a.get("unassigned", [])), "joriy davrlarda", "warn" if a.get("unassigned") else "", {"view": "amaliyot"}),
                    _k("Baza shartnomalari", len(a.get("agreements", [])), "tugayapti yoki tugagan", "warn" if a.get("agreements") else "", {"view": "amaliyot", "tab": "bazalar"})]
        elif k in ("ilmiy_bolim", "magistratura", "prorektor_ilmiy"):
            from . import ilmiy as ILm
            for a in ILm.alerts(c)[:4]:
                out.append(_k(a["text"].split(" ta ", 1)[-1][:60].capitalize() if " ta " in a["text"] else a["text"][:60], a.get("n") or 0, "Ilmiy faoliyat", "warn",
                              {"view": "ilmiy", "tab": a.get("tab")}))
            if k == "prorektor_ilmiy":
                n = _one("SELECT COUNT(*) n FROM intl_agreements WHERE status='faol'")
                out.append(_k("Faol xalqaro shartnomalar", n, "Xalqaro hamkorlik", "", {"view": "xalqaro"}))
            out = out[:4]
        elif k in ("masofaviy", "masofaviy_xodim"):
            from . import masofaviy as DLm
            out = DLm.bugun(c)
        elif k in ("xalqaro", "yuridik"):
            st = {r["status"]: r["n"] for r in db.rows(_con, "SELECT status, COUNT(*) n FROM intl_agreements GROUP BY status")}
            if k == "yuridik":
                out.append(_k("Yuridik ko'rikda", st.get("yuridik", 0), "xulosangizni kutmoqda", "warn" if st.get("yuridik") else "good", {"view": "xalqaro", "tab": "agreements"}))
            else:
                out += [_k("Faol shartnomalar", st.get("faol", 0), f"imzoda: {st.get('imzoda', 0)} · yuridikda: {st.get('yuridik', 0)}", "", {"view": "xalqaro", "tab": "agreements"}),
                        _k("Chet elda", _one("SELECT COUNT(*) n FROM intl_applications WHERE status='ketdi'"), "almashinuvdagi talabalar", "", {"view": "xalqaro", "tab": "exchange"}),
                        _k("Suhbat kutayotgan arizalar", _one("SELECT COUNT(*) n FROM intl_applications WHERE status='ariza' AND eligible=1 AND interview IS NULL"), "", "", {"view": "xalqaro", "tab": "exchange"})]
    except Exception as e:
        print("pending.bugun:", k, repr(e))
    return out
