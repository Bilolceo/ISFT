import os
"""Kadrlar bo'limi (app/kadrlar.py): uchidan-uchigacha HTTP testlar (server ISFT_TEST_URL yoki http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_kadrlar.py
Qayta ishga tushirish mumkin: test o'z vakansiyasi, nomzodi va bo'shatish jarayonini yaratadi, oxirida izini bazadan tozalaydi
(test belgisi bor vakansiya/nomzod/xodim/buyruq/Portal xatlari; bo'shatilgan xodimning shaxsiy ishi «faol»ga qaytariladi). Demo yozuvlar faqat o'qiladi.
"""
import datetime as dt, json, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
TAG = f"[test {time.strftime('%Y%m%d-%H%M%S')}]"
N = [0]
STATE = {"dis_staff": None, "renew": None, "train": None, "plan": None}

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
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

kadr, rektor, kaf4, teacher, buxg = (S(i) for i in (12, 2, 14, 15, 11))
AUDIT0 = q("SELECT COALESCE(MAX(id),0) FROM audit_log")[0][0]
today = dt.date.fromisoformat(kadr.get("/api/me").json()["today"])

def cleanup():
    print("\n— Tozalash —")
    con = sqlite3.connect(DB, timeout=30)
    try:
        like = f"%{TAG}%"
        sids = [r[0] for r in con.execute("SELECT staff_id FROM hr_candidates WHERE full_name LIKE ? AND staff_id IS NOT NULL", (like,))]
        for sid in sids:
            name = con.execute("SELECT full_name FROM staff WHERE id=?", (sid,)).fetchone()
            con.execute("DELETE FROM hr_files WHERE staff_id=?", (sid,)); con.execute("DELETE FROM hr_contract_log WHERE staff_id=?", (sid,))
            con.execute("DELETE FROM staff WHERE id=?", (sid,))
            if name: con.execute("DELETE FROM teachers WHERE full_name=?", (name[0],))
        vids = [r[0] for r in con.execute("SELECT id FROM hr_vacancies WHERE requirements LIKE ?", (like,))]
        con.execute("DELETE FROM hr_candidates WHERE full_name LIKE ? OR vacancy_id IN (%s)" % ",".join("?" * len(vids) or "0"), (like, *vids))
        con.execute("DELETE FROM hr_vacancies WHERE requirements LIKE ?", (like,))
        tids = [r[0] for r in con.execute("SELECT it_thread_id FROM hr_dismissals WHERE reason LIKE ? AND it_thread_id IS NOT NULL", (like,))]
        if STATE["dis_staff"]:
            sid = STATE["dis_staff"]
            con.execute("UPDATE hr_files SET status='faol', dismissed_on=NULL WHERE staff_id=?", (sid,))
            con.execute("DELETE FROM hr_dismissals WHERE staff_id=? AND reason LIKE ?", (sid, like))
            con.execute("DELETE FROM hr_contract_log WHERE staff_id=? AND action LIKE 'bekor%'", (sid,))
        if STATE["renew"]:
            sid, old = STATE["renew"]
            con.execute("UPDATE hr_files SET contract_type=?, contract_no=?, contract_start=?, contract_end=? WHERE staff_id=?", (*old, sid))
            con.execute("DELETE FROM hr_contract_log WHERE staff_id=? AND note LIKE ?", (sid, like))
        if STATE["train"]:
            sid, old = STATE["train"]
            con.execute("UPDATE hr_files SET last_attest=? WHERE staff_id=?", (old, sid))
            con.execute("DELETE FROM hr_trainings WHERE staff_id=? AND note LIKE ?", (sid, like))
        if STATE["plan"]:
            pid, old = STATE["plan"]; con.execute("UPDATE hr_positions SET plan=? WHERE id=?", (old, pid))
        oids = [r[0] for r in con.execute("SELECT id FROM orders WHERE kind IN ('xodim_qabul','xodim_boshatish') AND params LIKE ?", (like,))]
        for oid in oids:
            for t in ("order_log", "order_students", "order_versions", "order_files"):
                try: con.execute(f"DELETE FROM {t} WHERE order_id=?", (oid,))
                except sqlite3.OperationalError: pass
            vc = con.execute("SELECT verify_code FROM orders WHERE id=?", (oid,)).fetchone()
            if vc and vc[0]:
                try: con.execute("DELETE FROM documents WHERE verify_code=?", (vc[0],))
                except sqlite3.OperationalError: pass
            con.execute("DELETE FROM orders WHERE id=?", (oid,))
        tids += [r[0] for r in con.execute("SELECT id FROM portal_threads WHERE subject LIKE ?", (like,))]
        for tid in tids:
            for t in ("portal_recipients", "portal_msgs", "portal_user_reads", "portal_hidden"):
                try: con.execute(f"DELETE FROM {t} WHERE thread_id=?", (tid,))
                except sqlite3.OperationalError: pass
            con.execute("DELETE FROM portal_threads WHERE id=?", (tid,))
        con.commit()
        print(f"  tozalandi: xodim {len(sids)}, vakansiya {len(vids)}, buyruq {len(oids)}, Portal xati {len(tids)}")
    finally:
        con.close()

def main():
    # ============================================================== 1. Rollar va menyu
    print("— 1. Rollar va menyu —")
    modes = {u: S(u).get("/api/hr/meta").json()["mode"] for u in (12, 2, 14, 15, 17, 11)}
    ok(modes[12] == "full" and modes[2] == "rektor" and modes[14] == "head" and modes[15] == "own", f"rejimlar: {modes}")
    ok(modes[17] == "head", "Registrator ofisi boshlig'i — bo'lim rahbari rejimida")
    js, html = httpx.get(f"{B}/app.js").text, httpx.get(f"{B}/index.html").text
    ok('data-v="kadrlar"' in html and "kadrlar.js" in html and 'id="v-kadrlar"' in html, "index.html: menyu, ko'rinish va skript")
    ok("renderKadrlar" in js and "kadrlarNav" in js, "app.js: go() va menyu ulangan")
    ok("kadrlarProfile" in httpx.get(f"{B}/extras.js").text, "extras.js: profil oynasida o'z shaxsiy ishi")

    # ============================================================== 2. Ko'rinish (RBAC)
    print("— 2. Ko'rinish —")
    for c, n in ((rektor, "rektor"), (teacher, "o'qituvchi")):
        ok(c.get("/api/hr/staff").status_code == 403, f"{n}: xodimlar ro'yxati 403")
    bx = buxg.get("/api/hr/staff").json()["items"]
    ok(bx and {x["unit_key"] for x in bx} == {"buxgalteriya"}, f"Buxgalteriya boshlig'i: faqat o'z bo'limi ({len(bx)} ta)")
    ok(teacher.get("/api/hr/summary").status_code == 403, "o'qituvchi: jamlanma 403")
    s = rektor.get("/api/hr/summary").json()
    ok(s["kpi"]["headcount"] > 400 and s["by_unit"] and "name" in s["by_unit"][0], f"rektor: jamlanma ({s['kpi']['headcount']} xodim, {len(s['by_unit'])} bo'linma)")
    a = rektor.get("/api/hr/alerts").json()
    ok(a["aggregate"] and "contracts" not in a, "rektor: ogohlantirishlar faqat jamlangan (ismsiz)")
    L = kaf4.get("/api/hr/staff").json()["items"]
    ok(L and all(x["unit_key"] == "kaf4" for x in L), f"kafedra mudiri: faqat o'z kafedrasi ({len(L)} ta)")
    ok(all("education" not in x and "contract_no" not in x and "contract_days" not in x["flags"] for x in L), "kafedra mudiri: shaxsiy ma'lumot va sanalarsiz")
    ok(kaf4.get(f"/api/hr/staff/{L[0]['id']}").status_code == 403, "kafedra mudiri: shaxsiy ish tafsiloti 403")
    full = kadr.get("/api/hr/staff", params={"limit": 500}).json()
    ok(full["total"] > 400 and "contract_no" in full["items"][0], f"kadrlar: barcha shaxsiy ishlar ({full['total']})")
    me = teacher.get("/api/hr/me").json()
    ok(me["found"] and "contract_no" not in me, f"o'qituvchi: o'z shaxsiy ishi (o'qish uchun): {me.get('name')}")
    ok(teacher.get(f"/api/hr/staff/{me['id']}").status_code == 200, "o'qituvchi: o'z shaxsiy ishini ochadi")
    other = next(x["id"] for x in full["items"] if x["id"] != me["id"])
    ok(teacher.get(f"/api/hr/staff/{other}").status_code == 403, "o'qituvchi: boshqa xodimning shaxsiy ishi 403")
    fl = kadr.get("/api/hr/staff", params={"flag": "contract:d30|expired", "limit": 500}).json()["items"]
    ok(fl and all(x["flags"]["contract"] in ("d30", "expired") for x in fl), f"filtr: shartnoma 30 kun / o'tgan ({len(fl)})")
    al = kadr.get("/api/hr/alerts").json()
    ok(al["contracts"] and all(x["flags"]["contract"] in ("d30", "d60", "expired") for x in al["contracts"]), "ogohlantirish: shartnoma muddatlari (30/60 kun)")
    ok(all(x["flags"]["attest"] in ("overdue", "none", "soon") for x in al["attest"]), "ogohlantirish: attestatsiya")

    # ============================================================== 3. Shartnoma, attestatsiya, tahrir
    print("— 3. Shartnoma va attestatsiya —")
    x = next(i for i in al["contracts"] if i["flags"]["contract"] != "expired")
    f0 = q("SELECT contract_type, contract_no, contract_start, contract_end, last_attest FROM hr_files WHERE staff_id=?", (x["id"],))[0]
    STATE["renew"] = (x["id"], f0[:4]); STATE["train"] = (x["id"], f0[4])
    ok(kaf4.post(f"/api/hr/staff/{x['id']}/renew", json={"new_end": str(today + dt.timedelta(days=400))}).status_code == 403, "kafedra mudiri: uzaytirish 403")
    ok(kadr.post(f"/api/hr/staff/{x['id']}/renew", json={"new_end": str(today - dt.timedelta(days=1))}).status_code == 400, "o'tgan sana — 400")
    ok(kadr.post(f"/api/hr/staff/{x['id']}/renew", json={"new_end": str(today + dt.timedelta(days=365 * 6))}).status_code == 400, "5 yildan ortiq — 400")
    r = kadr.post(f"/api/hr/staff/{x['id']}/renew", json={"new_end": str(today + dt.timedelta(days=730)), "note": TAG})
    ok(r.status_code == 200, f"shartnoma uzaytirildi: {r.json()}")
    d = kadr.get(f"/api/hr/staff/{x['id']}").json()
    ok(d["flags"].get("contract") is None and d["contract_log"][0]["action"] == "uzaytirildi", "uzaytirilgach ogohlantirish yo'qoldi, tarixda yozuv")
    ok(kadr.post(f"/api/hr/staff/{x['id']}/training", json={"kind": "attestatsiya", "done_on": str(today + dt.timedelta(days=3))}).status_code == 400, "kelajak sana — 400")
    r = kadr.post(f"/api/hr/staff/{x['id']}/training", json={"kind": "attestatsiya", "done_on": str(today), "result": "lavozimga mos", "note": TAG})
    ok(r.status_code == 200 and r.json()["next_due"].startswith(str(today.year + 5)), f"attestatsiya qayd etildi, keyingisi {r.json().get('next_due')}")
    ok(kadr.get(f"/api/hr/staff/{x['id']}").json()["flags"]["attest"] is None, "attestatsiya belgisi tozalandi")

    # ============================================================== 4. Shtat jadvali
    print("— 4. Shtat jadvali —")
    st = kadr.get("/api/hr/staffing").json()
    ok(st["items"] and abs(st["total"]["plan"] - st["total"]["fact"] - st["total"]["vacant"]) < 30, f"shtat: reja {st['total']['plan']} · amalda {st['total']['fact']} · bo'sh {st['total']['vacant']}")
    hs = kaf4.get("/api/hr/staffing").json()
    ok(hs["items"] and all(i["unit_key"] == "kaf4" for i in hs["items"]), "kafedra mudiri: faqat o'z kafedrasi shtati")
    row = next(i for i in st["items"] if i["id"])
    STATE["plan"] = (row["id"], row["plan"])
    ok(rektor.post("/api/hr/staffing", json={"unit_key": row["unit_key"], "position": row["position"], "plan": row["plan"] + 1}).status_code == 403, "rektor: shtatni o'zgartirish 403")
    ok(kadr.post("/api/hr/staffing", json={"unit_key": row["unit_key"], "position": row["position"], "plan": row["plan"] + 1}).status_code == 200, "kadrlar: shtat o'zgartirildi")
    ok(abs(kadr.get("/api/hr/staffing").json()["total"]["plan"] - st["total"]["plan"] - 1) < 0.01, "jami reja +1 stavka")

    # ============================================================== 5. Ishga qabul: taklif → rektor → nomzod → rektor → buyruq → imzo → AT so'rovi
    print("— 5. Ishga qabul —")
    r = kaf4.post("/api/hr/vacancies", json={"position": "Assistent", "rate": 1, "requirements": f"Magistr {TAG}"})
    ok(r.status_code == 200 and r.json()["status"] == "taklif", "kafedra mudiri: vakansiya taklifi")
    V = r.json()["id"]
    ok(kaf4.post("/api/hr/vacancies", json={"unit_key": "buxgalteriya", "position": "X", "requirements": TAG}).status_code == 403, "kafedra mudiri: boshqa bo'limga 403")
    ok(rektor.post(f"/api/hr/vacancies/{V}/decide", json={"decision": "approve"}).status_code == 409, "taklif hali rektorga yuborilmagan — 409")
    ok(kadr.post(f"/api/hr/vacancies/{V}/submit").status_code == 200, "kadrlar: rektorga yuborildi")
    ok(kadr.post(f"/api/hr/vacancies/{V}/decide", json={"decision": "approve"}).status_code == 403, "kadrlar: tasdiqlash 403")
    ok(kadr.post(f"/api/hr/vacancies/{V}/candidates", json={"full_name": f"Sinov Nomzod {TAG}"}).status_code == 409, "tasdiqlanmagan vakansiyaga nomzod — 409")
    ok(rektor.post(f"/api/hr/vacancies/{V}/decide", json={"decision": "reject"}).status_code == 400, "rad — sababsiz 400")
    ok(rektor.post(f"/api/hr/vacancies/{V}/decide", json={"decision": "approve"}).status_code == 200, "rektor: vakansiya tasdiqlandi")
    K = kadr.post(f"/api/hr/vacancies/{V}/candidates", json={"full_name": f"Sinov Nomzod {TAG}", "education": "Oliy (magistr)", "degree": "PhD"}).json()["id"]
    K2 = kadr.post(f"/api/hr/vacancies/{V}/candidates", json={"full_name": f"Ikkinchi Nomzod {TAG}"}).json()["id"]
    ok(kadr.post(f"/api/hr/candidates/{K}/stage", json={"stage": "tanlandi"}).status_code == 409, "arizadan to'g'ri «tanlandi»ga — 409")
    for stg in ("suhbat", "tanlandi"):
        ok(kadr.post(f"/api/hr/candidates/{K}/stage", json={"stage": stg}).status_code == 200, f"nomzod: {stg}")
    kadr.post(f"/api/hr/candidates/{K2}/stage", json={"stage": "suhbat"})
    ok(kadr.post(f"/api/hr/candidates/{K2}/stage", json={"stage": "tanlandi"}).status_code == 409, "ikkinchi nomzodni tanlab bo'lmaydi — 409")
    ok(kadr.post(f"/api/hr/candidates/{K}/order", json={"date_from": str(today)}).status_code == 409, "rektor tasdig'isiz buyruq — 409")
    vs = rektor.get("/api/hr/vacancies").json()["items"]
    ok(any(k["id"] == K and k["stage"] == "tanlandi" for v in vs for k in v["candidates"]), "rektor: nomzod tasdiq navbatida ko'rinadi")
    ok(rektor.post(f"/api/hr/candidates/{K}/decide", json={"decision": "approve"}).status_code == 200, "rektor: nomzod tasdiqlandi")
    ok(kadr.post(f"/api/hr/candidates/{K}/order", json={"date_from": str(today), "contract_end": str(today + dt.timedelta(days=365 * 6))}).status_code == 400, "shartnoma 5 yildan ortiq — 400")
    r = kadr.post(f"/api/hr/candidates/{K}/order", json={"date_from": str(today + dt.timedelta(days=1)), "contract_type": "muddatli"})
    ok(r.status_code == 200 and r.json()["order"]["raw"] == "loyiha", f"buyruq loyihasi: {r.json().get('order')}")
    O = r.json()["order"]["id"]
    od = kadr.get(f"/api/orders/{O}").json()
    ok(od["order"]["kind"] == "xodim_qabul" and od["order"]["params"]["candidate_id"] == K, "«Buyruqlar»da xodim_qabul loyihasi (nomzod bog'langan)")
    meta_k = [x["key"] for x in kadr.get("/api/orders/meta").json()["kinds"]]
    ok("xodim_qabul" not in meta_k and "xodim_boshatish" not in meta_k and "xodim_tatil" in meta_k, "«Buyruqlar» qo'lda yaratish ro'yxatida qabul/bo'shatish yo'q")
    ok(kadr.post("/api/orders", json={"kind": "xodim_qabul", "params": {}}).status_code == 400, "qabul buyrug'ini qo'lda yaratish — 400")
    ok(kadr.post(f"/api/hr/candidates/{K}/it-request").status_code == 409, "imzodan oldin AT so'rovi — 409")
    ok(kadr.post(f"/api/orders/{O}/submit").status_code == 200, "kadrlar: buyruq imzoga yuborildi")
    ok(rektor.post(f"/api/orders/{O}/sign").status_code == 200, "rektor: buyruq imzolandi")
    vs = kadr.get("/api/hr/vacancies").json()["items"]
    v = next(v for v in vs if v["id"] == V); k = next(k for k in v["candidates"] if k["id"] == K)
    ok(k["stage"] == "qabul_qilindi" and k["staff_id"], f"imzodan keyin: nomzod ishga qabul qilindi (xodim #{k['staff_id']})")
    ok(v["status"] == "yopilgan", "vakansiya yopildi")
    nf = kadr.get(f"/api/hr/staff/{k['staff_id']}").json()
    ok(nf["unit_key"] == "kaf4" and nf["status"] == "faol" and nf["contract_end"] and nf["contract_log"], "yangi shaxsiy ish: kafedra, shartnoma va tarix")
    ok(q("SELECT department_id FROM teachers WHERE full_name=?", (f"Sinov Nomzod {TAG}",))[0][0] == 4, "o'qituvchilar ro'yxatiga qo'shildi (kafedra 4)")
    r = kadr.post(f"/api/hr/candidates/{K}/it-request")
    ok(r.status_code == 200 and r.json()["thread"]["ref_no"], f"AT bo'limiga akkaunt so'rovi: {r.json().get('thread')}")
    tid = r.json()["thread"]["id"]
    ok(q("SELECT unit FROM portal_recipients WHERE thread_id=?", (tid,)) == [("it",)], "Portal: qabul qiluvchi — AT bo'limi")
    ok(kadr.post(f"/api/hr/candidates/{K}/it-request").status_code == 409, "takroriy so'rov — 409")

    # ============================================================== 6. Ishdan bo'shatish
    print("— 6. Ishdan bo'shatish —")
    busy = {r[0] for r in q("SELECT staff_id FROM hr_dismissals WHERE status IN ('ariza','varaqa','buyruq')")}
    sid = next(i["id"] for i in full["items"] if i["id"] not in busy and i["id"] != x["id"] and i["status"] == "faol")
    STATE["dis_staff"] = sid
    body = {"staff_id": sid, "reason": f"O'z xohishiga ko'ra {TAG}", "last_day": str(today + dt.timedelta(days=14))}
    ok(kaf4.post("/api/hr/dismissals", json=body).status_code == 403, "kafedra mudiri: bo'shatish 403")
    ok(kadr.post("/api/hr/dismissals", json={**body, "last_day": str(today - dt.timedelta(days=30)), "app_date": str(today)}).status_code == 400, "oxirgi kun arizadan oldin — 400")
    r = kadr.post("/api/hr/dismissals", json=body); ok(r.status_code == 200, "ariza qayd etildi")
    D = r.json()["id"]
    ok(kadr.post("/api/hr/dismissals", json=body).status_code == 409, "ikkinchi ochiq jarayon — 409")
    r = kadr.post(f"/api/hr/dismissals/{D}/order")
    ok(r.status_code == 409 and "varaqasi" in r.json().get("detail", ""), "varaqa to'liq emas — buyruq 409")
    r = kadr.post(f"/api/hr/dismissals/{D}/it-request")
    ok(r.status_code == 200, "AT bo'limiga bloklash so'rovi yuborildi")
    for it in ("accounts", "property", "library", "docs", "finance"):
        r = kadr.post(f"/api/hr/dismissals/{D}/check", json={"item": it, "done": True})
    ok(r.json()["done"] == 5, "topshirish varaqasi to'liq (5/5)")
    r = kadr.post(f"/api/hr/dismissals/{D}/order"); ok(r.status_code == 200, f"bo'shatish buyrug'i loyihasi: {r.json().get('order')}")
    O2 = r.json()["order"]["id"]
    ok(kadr.post(f"/api/hr/dismissals/{D}/check", json={"item": "docs", "done": False}).status_code == 409, "buyruqdan keyin varaqa o'zgarmaydi — 409")
    ok(kadr.post(f"/api/hr/dismissals/{D}/cancel").status_code == 409, "buyruqdan keyin bekor qilish — 409")
    kadr.post(f"/api/orders/{O2}/submit"); ok(rektor.post(f"/api/orders/{O2}/sign").status_code == 200, "rektor: bo'shatish buyrug'i imzolandi")
    fd = kadr.get(f"/api/hr/staff/{sid}").json()
    ok(fd["status"] == "boshatilgan" and fd["dismissed_on"] == body["last_day"], "imzodan keyin shaxsiy ish «bo'shatilgan»")
    ok(sid not in {i["id"] for i in kadr.get("/api/hr/staff", params={"limit": 500}).json()["items"]}, "faol xodimlar ro'yxatidan chiqdi")
    ok(kadr.post(f"/api/hr/staff/{sid}/renew", json={"new_end": str(today + dt.timedelta(days=300))}).status_code == 409, "bo'shatilgan xodim shartnomasi — 409")

    # ============================================================== 7. Audit
    print("— 7. Audit —")
    acts = q("SELECT action, allowed FROM audit_log WHERE id>? AND resource='hr'", (AUDIT0,))
    ok(any(a.startswith("kadrlar: shartnoma uzaytirildi") for a, _ in acts) and any(not al for _, al in acts), f"audit: {len(acts)} ta yozuv (rad etilganlari ham)")
    ok(any("nomzod tasdiqlandi" in a for a, _ in acts) and any("AT bo'limiga" in a for a, _ in acts), "audit: tasdiq va AT so'rovlari")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
    print(f"\nHAMMASI O'TDI: {N[0]} ta tekshiruv.")
