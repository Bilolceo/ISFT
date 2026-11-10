import os
"""Majlis topshiriqlari — yagona bo'limlar reestri (Portal org_units): Yuridik bo'lim, kafedra, Amaliyot bo'limi, Devonxona.

Ishga tushirish (server http://127.0.0.1:8000 da ishlab turishi kerak):  .venv/bin/python tests/test_topshiriq_bolimlar.py
Qayta ishga tushirsa bo'ladi: boshida va oxirida test yaratgan qaror (sarlavha «… (test)») bazadan o'chiriladi va eski topshiriqqa
kiritilgan sinov o'zgarishlari asl holiga qaytariladi (demo vositalari — /api/dec/demo-reset — oddiy rejimda o'chiq, 403).
"""
import sqlite3, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
N = [0]

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def S(uid):
    c = httpx.Client(base_url=B, timeout=120)
    r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def one(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchone()
    finally: con.close()

# 2 rektor, 1 kengash, 3 o'quv prorektori, 5 moliya prorektori, 20 kotib, 21 IT boshlig'i, 11 buxgalteriya,
# 39 Yuridik bo'lim, 31 Biznes boshqaruvi kafedrasi (kaf2), 14 Buxgalteriya hisobi kafedrasi (kaf4), 15 o'qituvchi (kaf4),
# 29 Amaliyot bo'limi, 40 Devonxona, 17 Registrator ofisi boshlig'i (institutda dekan lavozimi yo'q — fakultet darajasidagi vazifalar unda)
U = {k: S(k) for k in (2, 1, 3, 5, 20, 21, 11, 39, 31, 14, 15, 29, 40, 17)}
rektor, kotib = U[2], U[20]
TEST_TITLE = "Amaliyot shartnomalari (test)"

def cleanup():
    con = sqlite3.connect(DB, timeout=30)
    try:
        for (mid,) in con.execute("SELECT id FROM meetings WHERE title=? AND source IN ('demo','manual')", (TEST_TITLE,)).fetchall():
            ids = [r[0] for r in con.execute("SELECT id FROM tasks WHERE meeting_id=?", (mid,))]
            if ids:
                q = ",".join(map(str, ids))
                con.execute(f"DELETE FROM task_msgs WHERE task_id IN ({q})"); con.execute(f"DELETE FROM task_log WHERE task_id IN ({q})")
                con.execute(f"DELETE FROM tasks WHERE id IN ({q})")
            con.execute("DELETE FROM meetings WHERE id=?", (mid,))
        con.commit()
    finally: con.close()

cleanup()
ok(rektor.post("/api/dec/demo-reset").status_code == 403, "demo vositalari o'chiq: «Demoni qayta boshlash» 403 (ISFT_CORE_DEMO_TOOLS=1 emas)")
ok(rektor.get("/api/dec/capabilities").json().get("demo_tools") is False, "capabilities: demo_tools=false — tugma ko'rsatilmaydi")
RESTORE = []

try:
    # --- 1. bo'limlar reestri ---------------------------------------------------------------
    us = kotib.get("/api/dec/units").json()["units"]
    keys = {u["key"] for u in us}
    ok({"yuridik", "amaliyot", "kaf2", "fak2", "devonxona", "prorektor_oquv", "it", "registrator"} <= keys and "talabalar" not in keys,
       f"GET /api/dec/units: {len(us)} ta bo'lim (Portal org_units), Registrator — eski 'registrator' kaliti bilan")
    ok([g for g in dict.fromkeys(u["group_name"] for u in us)] == ["Rahbariyat", "Bo'limlar", "Fakultet tyutorlari", "Kafedralar"],
       "bo'limlar guruhlangan: Rahbariyat / Bo'limlar / Fakultet tyutorlari / Kafedralar")
    ok(all(u["name"].endswith("fakulteti tyutorlari") for u in us if u["key"].startswith("fak")), "fakultet bo'limlari: «<fakultet> fakulteti tyutorlari» (dekanat yo'q)")
    ok(one("SELECT COUNT(*) FROM org_units")[0] == len(us), "reestrdagi bo'limlar soni = org_units soni")

    # --- 2. transkriptdan qoralama ----------------------------------------------------------
    TR = """Rektorat yig'ilishi, amaliyot masalalari.
Qatnashdilar: rektor, o'quv ishlari bo'yicha prorektor, Yuridik bo'lim, Amaliyot bo'limi, Biznes boshqaruvi kafedrasi mudiri.
Kun tartibi: talabalar amaliyoti shartnomalari.
Rektor: Qaror: Yuridik bo‘lim amaliyot shartnomalari namunasini 3 kun ichida ko'rib chiqsin.
Rektor: Biznes boshqaruvi kafedrasi amaliyot dasturini yangilasin.
Rektor: Amaliyot bo'limi Yuridik bo'limdan natija kelgach, shartnomalarni korxonalarga yuborsin.
Rektor: Shartnomalar reyestri yuritilsin va saqlansin.
Rektor: yig'ilish yopildi."""
    d = kotib.post("/api/dec/draft", json={"title": TEST_TITLE, "transcript": TR, "source": "manual"}).json()
    T = d["tasks"]
    ok(len(T) == 4, f"4 ta topshiriq ajratildi ({[t['unit'] for t in T]})")
    yu, kf, am, rs = T
    ok(yu["unit"] == "yuridik" and yu["unit_name"] == "Yuridik bo'lim" and yu["due_at"], "1: Yuridik bo'lim (ʻ/‘ apostrof normallashtirildi), muddat «3 kun ichida»")
    ok(kf["unit"] == "kaf2" and kf["unit_name"] == "Biznes boshqaruvi kafedrasi", "2: Biznes boshqaruvi kafedrasi (kaf2)")
    ok(am["unit"] == "amaliyot" and am["depends_on"] == yu["id"], f"3: Amaliyot bo'limi, Yuridik natijasiga bog'liq ({am['dep_text']})")
    ok(rs["unit"] is None, "4: bo'lim aytilmagan — bo'sh qoldi")
    ok(any(u["key"] == "kaf2" and u["group_name"] == "Kafedralar" for u in d["units"]), "tahrir oynasi bo'limlari — guruh bilan")
    ok(U[39].get(f"/api/dec/{d['id']}").status_code == 403, "Yuridik bo'lim qoralamani ko'rmaydi")
    ok(kotib.post(f"/api/dec/{d['id']}/confirm").status_code == 400, "bo'limsiz band bilan tasdiqlab bo'lmaydi (400)")

    def put(unit4):
        return kotib.put(f"/api/dec/{d['id']}", json={"title": d["title"], "minutes": d["minutes"], "tasks": [
            {"id": t["id"], "text": t["text"], "unit": unit4 if t["id"] == rs["id"] else t["unit"], "assignee": "",
             "due_at": t["due_at"], "depends_on": t["depends_on"]} for t in T]})
    ok(put("bunday_yoq").status_code == 400, "noma'lum bo'lim kaliti rad etildi (400)")
    e = put("talabalar").json()
    ok([t for t in e["tasks"] if t["id"] == rs["id"]][0]["unit"] == "registrator", "Portal kaliti 'talabalar' → saqlanadigan kalit 'registrator' (alias)")
    e = put("devonxona").json()
    ok([t for t in e["tasks"] if t["id"] == rs["id"]][0]["unit_name"] == "Devonxona", "kotib tahrirda 4-bandga Devonxonani tanladi")
    c1 = kotib.post(f"/api/dec/{d['id']}/confirm").json()
    ok(c1["already"] is False, "tasdiqlandi — bo'limlar navbatiga yuborildi")
    ok(one("SELECT COUNT(*) FROM task_log WHERE task_id IN (?,?,?,?) AND action='tasdiqlandi' AND detail LIKE '%navbatiga yuborildi'",
           (yu["id"], kf["id"], am["id"], rs["id"]))[0] == 4, "tasdiqlash audit tarixida (task_log)")

    # --- 3. navbatlar -----------------------------------------------------------------------
    def queue(uid): return U[uid].get("/api/dec/list").json()["queue"]
    for uid, tid, name in ((39, yu["id"], "Yuridik bo'lim"), (31, kf["id"], "Biznes boshqaruvi kafedrasi"), (29, am["id"], "Amaliyot bo'limi"), (40, rs["id"], "Devonxona")):
        q = queue(uid)
        # navbatda boshqa manbadagi topshiriqlar ham bo'lishi mumkin (kafedra so'rovlari — directives, eski majlis topshiriqlari — arxiv)
        mt = [t["id"] for t in q["tasks"] if q and t.get("meeting_id") == d["id"]] if q else []
        ok(q and q["head"] and q["unit_name"] == name and mt == [tid], f"#{uid} {name} rahbari navbatida shu qarordan 1 ta topshiriq")
    ok(not any(t["id"] == kf["id"] for t in (queue(14) or {"tasks": []})["tasks"]), "boshqa kafedra (kaf4) navbatida kaf2 topshirig'i yo'q")

    # --- 4. ijro va ruxsatlar ------------------------------------------------------------------
    up = lambda uid, tid, **b: U[uid].post(f"/api/dec/task/{tid}/update", json=b)
    ok(up(21, yu["id"], status="jarayonda").status_code == 403, "IT boshlig'i Yuridik topshirig'ini o'zgartira olmaydi (403)")
    ok(up(31, yu["id"], status="jarayonda").status_code == 403, "kafedra Yuridik topshirig'ini o'zgartira olmaydi (403)")
    ok(up(14, kf["id"], status="jarayonda").status_code == 403, "kaf4 mudiri kaf2 topshirig'ini o'zgartira olmaydi (403)")
    ok(up(3, kf["id"], status="jarayonda").status_code == 403, "kurator prorektor faqat o'qiydi (403)")
    ok(U[14].post(f"/api/dec/task/{kf['id']}/assign", json={"user_id": 14}).status_code == 403, "kaf4 mudiri kaf2 topshirig'ini biriktira olmaydi (403)")
    ok(U[31].post(f"/api/dec/task/{kf['id']}/assign", json={"user_id": 15}).status_code == 400, "kaf2 mudiri boshqa kafedra o'qituvchisiga biriktira olmaydi (400)")
    ok(U[31].post(f"/api/dec/task/{kf['id']}/assign", json={"user_id": 31}).json()["ok"], "kaf2 mudiri o'ziga biriktirdi")
    ok(up(39, yu["id"], status="jarayonda").json()["ok"], "Yuridik bo'lim: ish boshlandi")
    ok(up(31, kf["id"], status="jarayonda", result="Dastur loyihasi tayyorlanmoqda").json()["ok"], "kafedra: oraliq natija")
    ok(up(29, am["id"], status="bajarildi", result="yuborildi").status_code == 409, "Amaliyot Yuridik natijasisiz yakunlay olmaydi (409)")
    ok(up(39, yu["id"], status="bajarildi", result="Shartnoma namunasi ko'rib chiqildi, 2 ta band tuzatildi.").json()["ok"], "Yuridik bo'lim yakunladi")
    ok(up(29, am["id"], status="bajarildi", result="Shartnomalar 12 ta korxonaga yuborildi.").json()["ok"], "Amaliyot bo'limi yakunladi")
    ok(up(40, rs["id"], status="jarayonda").json()["ok"], "Devonxona: ish boshlandi")
    ok(U[29].post(f"/api/dec/task/{am['id']}/msg", json={"text": "Rahmat, yubordik."}).json()["ok"], "Amaliyot bo'limi bog'langan chatga yozdi")
    ok(U[31].post(f"/api/dec/task/{am['id']}/msg", json={"text": "x"}).status_code == 403, "begona bo'lim chatga yoza olmaydi (403)")

    # --- 5. ko'rinish ---------------------------------------------------------------------------
    for uid, who in ((2, "rektor"), (1, "kengash"), (20, "kotib")):
        full = U[uid].get(f"/api/dec/{d['id']}").json()
        ok(len(full["tasks"]) == 4, f"{who} barcha 4 topshiriqni ko'radi")
    full = rektor.get(f"/api/dec/{d['id']}").json()
    ok([t["status"] for t in full["tasks"]] == ["bajarildi", "jarayonda", "bajarildi", "jarayonda"], "rektor: holatlar aynan tasks jadvalidan")
    ok(U[11].get(f"/api/dec/{d['id']}").status_code == 403, "buxgalteriya (aloqasi yo'q) qarorni ko'rmaydi")
    ok(U[5].get(f"/api/dec/{d['id']}").status_code == 403, "moliya prorektori (kuratorligida bunday bo'lim yo'q) ko'rmaydi")
    pv = U[3].get(f"/api/dec/{d['id']}").json()
    ok({t["unit"] for t in pv["tasks"]} == {"kaf2", "amaliyot"} and not any(t["can_act"] for t in pv["tasks"]),
       "o'quv prorektori kuratorlik bo'limlari (kafedra, Amaliyot) topshiriqlarini faqat o'qiydi")
    kv = U[31].get(f"/api/dec/{d['id']}").json()
    ok([t["id"] for t in kv["tasks"]] == [kf["id"]] and kv["tasks"][0]["can_act"], "kaf2 mudiri faqat o'z topshirig'ini ko'radi va bajaradi")
    av = U[29].get(f"/api/dec/{d['id']}").json()
    ok({t["id"] for t in av["tasks"]} == {yu["id"], am["id"]}, "Amaliyot o'z va bog'liq Yuridik topshirig'ini ko'radi")
    ok(U[14].get(f"/api/dec/{d['id']}").status_code == 403, "kaf4 mudiri kaf2 qarorini ko'rmaydi")

    # «mine» (bildirishnomalar, «Mening vazifalarim» manbai) — bo'lim bo'yicha
    def sec(uid): return {t["id"]: t for t in U[uid].get("/api/section/tasks").json()["tasks"]}
    s31, s14 = sec(31), sec(14)
    ok(s31.get(kf["id"], {}).get("mine") and kf["id"] not in s14, "kaf2 topshirig'i — kaf2 mudiriga 'mine', kaf4 mudiriga ko'rinmaydi")
    s39 = sec(39)
    ok(s39.get(yu["id"], {}).get("mine") and kf["id"] not in s39, "Yuridik bo'lim ro'yxatida o'z topshirig'i ('mine'), kafedraniki yo'q")
    ok(sec(40)[rs["id"]]["mine"], "Devonxona: o'z topshirig'i 'mine'")
    s3 = sec(3)
    ok(kf["id"] in s3 and not s3[kf["id"]]["mine"] and yu["id"] not in s3, "o'quv prorektori: kuratorlik topshirig'i ro'yxatda, lekin 'mine' emas")

    # --- 6. eski majlis topshiriqlari — yagona oqimga o'tkazilgan (bo'lim bo'yicha, «arxiv» manbali qaror) ----------
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    ARX = "meeting_id IN (SELECT id FROM meetings WHERE source='arxiv')"
    ok(con.execute("SELECT COUNT(*) FROM tasks WHERE unit IS NULL AND meeting_id IS NOT NULL AND status!='qoralama'").fetchone()[0] == 0,
       "bo'limsiz (eski) majlis topshirig'i qolmadi — hammasi yagona oqimda")
    leg_k4 = {r[0] for r in con.execute(f"SELECT id FROM tasks WHERE {ARX} AND unit='kaf4' AND assignee_role IN ('kafedra','oqituvchi') AND status!='qoralama'")}
    leg_k4_head = {r[0] for r in con.execute(f"SELECT id FROM tasks WHERE {ARX} AND unit='kaf4' AND assignee_role='kafedra' AND status!='qoralama'")}
    leg_k4_t = {r[0] for r in con.execute(f"SELECT id FROM tasks WHERE {ARX} AND unit='kaf4' AND assignee_role='oqituvchi' AND status!='qoralama'")}
    leg_dekan = con.execute("SELECT COUNT(*) FROM tasks WHERE assignee_role='dekan'").fetchone()[0]
    leg_f2 = {r[0] for r in con.execute(f"SELECT id FROM tasks WHERE {ARX} AND assignee_role='talabalar' AND (text LIKE '%Xalqaro iqtisodiyot va moliya%' OR text LIKE '%ota-onalari bilan uchrashuv%') AND status!='qoralama'")}
    ok(one("SELECT COUNT(*) FROM tasks t JOIN meetings m ON m.id=t.meeting_id WHERE m.title='Test' AND m.transcript='t'")[0] == 0,
       "sinov qoldig'i («Test» majlisi, «x» topshirig'i — Moliya fakulteti dekani) bazada yo'q")
    con.close()
    ok(bool(leg_k4_head), f"bazada kaf4 ning eski topshiriqlari bor: {sorted(leg_k4)}")
    ok(not (leg_k4 & set(s31)), "kaf2 mudiri (#31) kaf4 ning eski topshiriqlarini ko'rmaydi")
    ok(leg_k4_head <= {i for i, t in s14.items() if t["mine"]}, "kaf4 mudiri (#14) o'z kafedrasi topshiriqlarini ko'radi ('mine')")
    s15 = sec(15)
    ok(leg_k4_t <= {i for i, t in s15.items() if t["mine"]} and not (leg_k4_head & {i for i, t in s15.items() if t["mine"]}),
       "kaf4 o'qituvchisi (#15) o'qituvchi topshiriqlarini ko'radi, mudirnikini 'mine' deb olmaydi")
    ok(leg_dekan == 0, "bazada dekanga yozilgan topshiriq yo'q (dekan lavozimi yo'q)")
    ok(leg_f2 and leg_f2 <= {i for i, t in sec(17).items() if t["mine"]}, f"fakultet darajasidagi eski topshiriqlar — Registrator ofisi boshlig'ida ('mine'): {sorted(leg_f2)}")
    ns31 = {n["id"] for n in U[31].get("/api/notifications").json()["items"]}
    ok(not any(n[2:].isdigit() and int(n[2:]) in leg_k4 for n in ns31 if n.startswith(("to", "tn"))), "kaf2 mudiri bildirishnomalarida kaf4 topshiriqlari yo'q")
    open_k4 = sorted(i for i in leg_k4_head if one("SELECT status FROM tasks WHERE id=?", (i,))[0] != "bajarildi")
    ok(bool(open_k4), f"kaf4 ning ochiq eski topshirig'i bor: {open_k4}")
    T = open_k4[0]
    RESTORE.append((T, one("SELECT status, result, result_at, result_by, review, review_note, review_at, review_by, updated_at, assignee_user, assignee FROM tasks WHERE id=?", (T,))))
    for uid, who in ((31, "kaf2 mudiri"), (2, "rektor"), (1, "kengash"), (14, "kaf4 mudirining o'zi")):
        ok(U[uid].post(f"/api/tasks/{T}/status", json={"status": "bajarildi"}).status_code == 403,
           f"{who}: eski bir bosishli «Bajarildi» (/api/tasks/…/status) ishlamaydi (403)")
    ok(up(2, T, status="bajarildi", result="boshqa birov").status_code == 403, "rektor boshqaning topshirig'ini yakunlay olmaydi (403)")
    ok(up(1, T, status="bajarildi", result="x").status_code == 403, "kengash boshqaning topshirig'ini yakunlay olmaydi (403)")
    ok(up(14, T, status="bajarildi").status_code == 400, "ijrochi natijasiz yakunlay olmaydi (400)")
    ok(up(14, T, status="bajarildi", result="Jadval tuzildi va kafedra majlisida tasdiqlandi.").json()["ok"], "kaf4 mudiri (ijrochi) natija bilan yakunladi")
    ok(one("SELECT status, review FROM tasks WHERE id=?", (T,)) == ("bajarildi", "kutilmoqda"), "natija rektor qabulini kutmoqda")
    rv = lambda uid, **b: U[uid].post(f"/api/dec/task/{T}/review", json=b)
    ok(rv(1, decision="qabul").status_code == 403 and rv(14, decision="qabul").status_code == 403, "kengash va ijrochining o'zi qabul qila olmaydi (403)")
    ok(any(it["link"] == {"view": "tasks", "meeting": one("SELECT meeting_id FROM tasks WHERE id=?", (T,))[0], "task": T} for it in rektor.get("/api/mywork").json()["items"]),
       "rektor «Mening vazifalarim»: natijani ko'rib chiqish — aniq topshiriqqa havola")
    ok(rv(2, decision="qaytarish").status_code == 400, "izohsiz qaytarish rad etiladi (400)")
    ok(rv(2, decision="qaytarish", note="Jadvalga xona raqamlarini qo'shing").json()["ok"], "rektor qayta ishlashga qaytardi")
    ok(one("SELECT status, review FROM tasks WHERE id=?", (T,)) == ("jarayonda", "qaytarildi"), "holat: jarayonda · qaytarildi")
    ok(any("Qayta ishlashga" in n["title"] and n["link"].get("task") == T for n in U[14].get("/api/notifications").json()["items"]), "ijrochiga bildirishnoma (aniq havola)")
    ok(up(14, T, status="bajarildi", result="Xona raqamlari qo'shildi.").json()["ok"] and rv(2, decision="qabul").json()["ok"], "qayta yakunlandi va rektor qabul qildi")
    lr = rektor.get("/api/section/tasks").json()["tasks"]
    ok(leg_k4 <= {t["id"] for t in lr} and kf["id"] in {t["id"] for t in lr}, "rektor barcha topshiriqlarni ko'radi")
finally:
    cleanup()
    if RESTORE:
        con = sqlite3.connect(DB, timeout=30)
        for T, row in RESTORE:
            con.execute("""UPDATE tasks SET status=?, result=?, result_at=?, result_by=?, review=?, review_note=?, review_at=?, review_by=?, updated_at=?,
                           assignee_user=?, assignee=? WHERE id=?""", (*row, T))
            con.execute("DELETE FROM task_log WHERE task_id=? AND ts >= (SELECT COALESCE(MAX(ts),'') FROM task_log WHERE task_id=? AND action='yagona ijro oqimiga o''tkazildi')"
                        " AND action!='yagona ijro oqimiga o''tkazildi'", (T, T))
        con.commit(); con.close()

print(f"\nHAMMASI O'TDI: {N[0]} ta tekshiruv.")
