"""Portal v2: uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_portal.py
Qayta ishga tushirish mumkin (qayta seed shart emas): test o'z yozishmalarini noyob mavzu bilan yaratadi va oxirida yopadi,
qoralama va shablonlarini o'chiradi. Demo yozishmalar faqat o'qiladi. Bazaga faqat o'qish rejimida murojaat qilinadi.
"""
import datetime as dt, hashlib, io, sqlite3, sys, time, zipfile
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "jarvis.db"
B = "http://127.0.0.1:8000"
PW = "Isft2026"

N = [0]
SOFT = []          # backend xatolari (test davom etadi, oxirida exit 1)

def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def soft(cond, msg):
    """Ma'lum backend xatosini tekshiradi: muvaffaqiyatsiz bo'lsa ham test davom etadi, oxirida natija 1."""
    N[0] += 1
    print(("✓ " if cond else "✗ BACKEND XATOSI: ") + msg)
    if not cond: SOFT.append(msg)

NOTES = []
def note(cond, msg):
    """Spetsifikatsiyadan chetlanish (muhokamali): natijaga ta'sir qilmaydi, oxirida ro'yxat chiqadi."""
    print(("✓ " if cond else "⚠ ESLATMA: ") + msg)
    if not cond: NOTES.append(msg)

def S(uid):
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/login", json={"user_id": uid, "password": PW})
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def lst(c, box="inbox", flt="all", q_="", offset=0, limit=100):
    r = c.get("/api/portal/threads", params={"box": box, "flt": flt, "q": q_, "offset": offset, "limit": limit})
    assert r.status_code == 200, f"threads {box}/{flt}/{q_!r}: {r.status_code} {r.text[:300]}"
    return r.json()

def all_items(c, box="inbox", flt="all", q_=""):
    out, off = [], 0
    while True:
        d = lst(c, box, flt, q_, off, 100)
        out += d["items"]; off += 100
        if off >= d["total"]: return out

def item(c, tid, box="inbox", flt="all", q_=""):
    return next((x for x in all_items(c, box, flt, q_) if x["id"] == tid), None)

def has(c, tid, box="inbox", flt="all", q_=""): return item(c, tid, box, flt, q_) is not None

def detail(c, tid):
    r = c.get(f"/api/portal/threads/{tid}"); assert r.status_code == 200, r.text[:300]; return r.json()

def rcp(d, unit): return next((r for r in d["recipients"] if r["unit"] == unit), None)

def post(c, path, body=None): return c.post(path, json=body if body is not None else {})

STAMP = time.strftime("%Y%m%d-%H%M%S")
U = str(int(time.time() * 1000))[-9:]          # noyob so'z qo'shimchasi (FTS uchun)
TODAY = dt.date.today()
D2, D3, YDAY = (TODAY + dt.timedelta(days=2)).isoformat(), (TODAY + dt.timedelta(days=3)).isoformat(), (TODAY - dt.timedelta(days=1)).isoformat()

rektor, pro, reg, cc, ithead, iteng, akad, sirtqi, buxg, kaf = (S(i) for i in (2, 3, 17, 23, 21, 22, 18, 27, 11, 31))
AUDIT0 = q("SELECT COALESCE(MAX(id),0) FROM audit_log")[0][0]
MY_THREADS, MY_DRAFTS, MY_TEMPLATES = [], [], []   # (client, id)

def new_thread(c, tag, to, due=None, body=None, **kw):
    r = post(c, "/api/portal/threads", {"subject": f"Portal v2 test {tag} {STAMP}", "body": body or f"Test xati {tag} ({STAMP}).",
                                        "to": to, "due": due, **kw})
    assert r.status_code == 200, r.text
    tid = r.json()["id"]; MY_THREADS.append(tid)
    return tid, r.json()["ref_no"]

def cleanup():
    print("\n— Tozalash —")
    for tid in MY_THREADS:
        st = q("SELECT status FROM portal_threads WHERE id=?", (tid,))
        if st and st[0][0] == "ochiq":
            r = post(akad, f"/api/portal/threads/{tid}/close", {"note": "test yakuni"})
            print(f"  yozishma #{tid} yopildi: {r.status_code}")
    for c, did in MY_DRAFTS:
        c.delete(f"/api/portal/drafts/{did}")
    for c, tid in MY_TEMPLATES:
        c.delete(f"/api/portal/templates/{tid}")
    for fid, uid in q("SELECT id, uploader_id FROM portal_files WHERE name LIKE ? ORDER BY version DESC", (f"%{U}%",)):
        c = {17: reg, 23: cc, 18: akad}.get(uid)
        if c: print(f"  test fayli #{fid} o'chirildi: {c.delete(f'/api/portal/files/{fid}').status_code}")
    left = [t for t in MY_THREADS if q("SELECT status FROM portal_threads WHERE id=?", (t,))[0][0] != "yopilgan"]
    print(f"  ochiq qolgan test yozishmalari: {left or 'yo‘q'}")

def main():
    # ============================================================== 1. Bo'limlar
    print("— 1. Bo'limlar —")
    u17, u23 = reg.get("/api/portal/units").json(), cc.get("/api/portal/units").json()
    ok(u17["me"] == "talabalar" and u23["me"] == "talabalar", "17 va 23 — talabalar bo'limi")
    ok(u17["is_head"] is True and u23["is_head"] is False, "is_head: 17 rahbar, 23 rahbar emas")
    ok(len(u17["members"]) == 2 and {m["id"] for m in u17["members"]} == {17, 23}, "talabalar a'zolari: 2 ta (17, 23)")
    ok(next(m for m in u17["members"] if m["id"] == 17)["head"] and next(m for m in u23["members"] if m["id"] == 23)["me"], "members: head/me belgilari")
    ok(any(x["key"] == "sirtqi" for x in u17["units"]) and {"xat", "sorov"} <= set(u17["kinds"]), "units ro'yxati va kinds")
    for c, uid, lead in ((rektor, 2, True), (pro, 3, True), (reg, 17, False), (cc, 23, False), (ithead, 21, False), (iteng, 22, False),
                         (akad, 18, False), (sirtqi, 27, False), (buxg, 11, False), (kaf, 31, False)):
        u = c.get("/api/portal/units").json()
        ok(u["can_resolve"] is lead and u["leader"] is lead, f"user {uid}: can_resolve/leader = {lead}")
        ok(not u["curated"] if uid not in (3, 4, 5) else bool(u["curated"]), f"user {uid}: curated ({len(u['curated'])})")
    cu = set(pro.get("/api/portal/units").json()["curated"])
    ok({"akademik", "talabalar", "sirtqi", "amaliyot"} <= cu and not {"imtihon", "kadrlar", "qabul"} & cu, "prorektor_oquv kuratorligi 2024 tuzilmasi bo'yicha (imtihon, kadrlar — rektorga bevosita)")

    # ============================================================== 2. Xodim bo'yicha o'qilmagan
    print("— 2. Xodim bo'yicha o'qilmagan —")
    body1 = f"Talabalar ma'lumotlarini yangilash. Kalit so'z zarbulmasal{U}. Oshxona: sho'rva{U} tayyor."
    T1, REF1 = new_thread(akad, "T1", ["talabalar"], due=D2, body=body1)
    ok(post(akad, "/api/portal/threads", {"subject": "x", "body": "x", "to": ["akademik"]}).status_code == 400, "faqat o'z bo'limiga xat: 400")
    ok(post(akad, "/api/portal/threads", {"subject": " ", "body": "x", "to": ["talabalar"]}).status_code == 400, "mavzusiz xat: 400")
    ok(post(akad, "/api/portal/threads", {"subject": "x", "body": "x", "to": ["nomalum"]}).status_code == 400, "noma'lum bo'lim: 400")
    for c, n in ((reg, 17), (cc, 23)):
        it = item(c, T1, "inbox", "unread")
        ok(it is not None and it["unread"] and it["my_status"] == "yangi" and it["role"] == "to", f"{n}: T1 kiruvchida o'qilmagan, holat yangi")
    detail(reg, T1)
    it23 = item(cc, T1, "inbox", "unread")
    ok(it23 is not None and it23["unread"], "17 ochgandan keyin 23 uchun T1 hali o'qilmagan")
    ok(not has(reg, T1, "inbox", "unread") and item(reg, T1)["unread"] is False, "17 uchun endi o'qilgan")
    d = detail(reg, T1); r = rcp(d, "talabalar")
    ok(r["status"] == "o'qilgan" and (r["read_by"] or "").startswith("Baratov"), f"qabul qiluvchi holati o'qilgan, read_by = {r['read_by']}")
    ok([x["name"] for x in r["readers"]] == ["Baratov M."], f"o'qiganlar ro'yxati faqat 17: {r['readers']}")
    ok(d["role"] == "to" and d["perms"]["can_assign"] and not d["perms"]["can_take"], "17: role=to, can_assign (rahbar), can_take yo'q")
    sent18 = item(akad, T1, "sent")
    ok(sent18 is not None and sent18["unread"] is False and sent18["role"] == "from", "18 yuborganlar: T1 o'qilmagan emas (o'z xati)")

    # ============================================================== 3. Ijrochi tayinlash
    print("— 3. Ijrochi tayinlash —")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 17}).status_code == 403, "23 boshqa xodimga (17) tayinlay olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T1}/assign", {"user_id": 18}).status_code == 403, "yuboruvchi bo'lim ijrochi tayinlay olmaydi (403)")
    p23 = detail(cc, T1)["perms"]
    ok(p23["can_take"] and not p23["can_assign"], "23: can_take bor, can_assign yo'q")
    r = post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23})
    ok(r.status_code == 200 and r.json()["assignee"] == "Rahimova N.", "23 xatni o'z ijrosiga oldi")
    m = item(cc, T1, "inbox", "mine")
    ok(m is not None and m["assigned_to_me"] and m["assignee_name"] == "Rahimova N.", "23: flt=mine da T1, assigned_to_me")
    ok(not has(reg, T1, "inbox", "mine"), "17: flt=mine da T1 yo'q")
    ok(cc.get("/api/portal/units").status_code == 200 and lst(cc)["counts"]["assigned_to_me"] >= 1, "23: counts.assigned_to_me >= 1")
    # 13-band (qisman): menga biriktirilgan, muddati yaqin xat — eslatma va bildirishnoma
    rem = cc.get("/api/portal/reminders").json()["items"]
    rr = next((x for x in rem if x["thread_id"] == T1), None)
    ok(rr is not None and rr["who"] == "menga" and rr["kind"] == "yaqin" and rr["days_left"] == 2 and rr["due"] == D2,
       f"23 eslatmalari: T1 who=menga, kind=yaqin, 2 kun ({rr})")
    nt = cc.get("/api/notifications").json()
    ok(isinstance(nt["items"], list) and all({"id", "kind", "title", "ts", "link"} <= set(x) for x in nt["items"]), "/api/notifications tuzilmasi")
    ni = next((x for x in nt["items"] if x["id"] == f"pm{T1}"), None)
    ok(ni is not None and ni["kind"] == "xat_muddat" and ni["link"] == {"view": "portal", "thread": T1}, "23 bildirishnomalarida T1 muddat eslatmasi")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": None}).status_code == 200, "23 o'z ijrosidan bo'shatdi (user_id=null)")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 200, "23 qayta oldi")
    r = post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 17})
    ok(r.status_code == 200 and r.json()["assignee"] == "Baratov M.", "17 (rahbar) ijrochini o'ziga o'zgartirdi")
    d = detail(reg, T1)
    ok(rcp(d, "talabalar")["assignee_id"] == 17 and rcp(d, "talabalar")["assignee_name"] == "Baratov M.", "detail: assignee_id=17")
    ok(not has(cc, T1, "inbox", "mine") and has(reg, T1, "inbox", "mine"), "flt=mine: endi 17 da, 23 da emas")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 409, "23 boshqa ijrochidagi xatni ola olmaydi (409)")
    ok(post(cc, f"/api/portal/threads/{T1}/assign", {"user_id": None}).status_code == 403, "23 boshqaning ijrochiligini olib tashlay olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 11}).status_code == 400, "17 boshqa bo'lim xodimiga tayinlay olmaydi (400)")
    ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 999999}).status_code == 400, "mavjud bo'lmagan xodim (400)")
    s18 = item(akad, T1, "sent")
    ok(s18["unread"] is False and not has(akad, T1, "sent", "unread"), "tizim yozuvlari (tayinlash) 18 uchun o'qilmagan qilmaydi")
    tz = [x for x in detail(akad, T1)["messages"] if x["kind"] == "tizim"]
    ok(len(tz) >= 4 and not any(x["new"] for x in tz), f"detail: {len(tz)} ta tizim yozuvi, 'new' emas")

    # ============================================================== 4. Yo'naltirish
    print("— 4. Yo'naltirish —")
    ok(post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["akademik"], "note": "x"}).status_code == 400, "yuboruvchi bo'limga yo'naltirish rad (400)")
    ok(post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["talabalar"], "note": "x"}).status_code == 400, "o'z bo'limiga yo'naltirish rad (400)")
    ok(post(buxg, f"/api/portal/threads/{T1}/forward", {"units": ["sirtqi"]}).status_code == 403, "qabul qilmagan bo'lim yo'naltira olmaydi (403)")
    r = post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["sirtqi"], "note": f"Sirtqi bo'lim talabalari bo'yicha ({STAMP})"})
    ok(r.status_code == 200 and r.json()["units"] == ["sirtqi"], "17 → sirtqi yo'naltirdi")
    d = detail(reg, T1); rt, rs = rcp(d, "talabalar"), rcp(d, "sirtqi")
    ok(rt["status"] == "yo'naltirilgan" and rt["forwarded_to"] == ["Sirtqi bo'lim"], "17 holati yo'naltirilgan, forwarded_to = Sirtqi bo'lim")
    ok(rs and rs["status"] == "yangi" and rs["via"] == "yonaltirish" and rs["fwd_from"] == "Registrator ofisi", "sirtqi: yangi, via yonaltirish, fwd_from Registrator ofisi")
    s = item(sirtqi, T1)
    ok(s is not None and s["my_status"] == "yangi" and s["unread"], "27 kiruvchida T1 (yangi, o'qilmagan)")
    ok(not d["perms"]["can_forward"], "17: endi can_forward yo'q")
    ok(post(reg, f"/api/portal/threads/{T1}/forward", {"units": ["buxgalteriya"]}).status_code == 409, "qayta yo'naltirish 409")
    fm = [x for x in d["messages"] if (x.get("meta") or {}).get("forward")]
    ok(len(fm) == 1 and fm[0]["kind"] == "xat" and "Sirtqi bo'lim" in fm[0]["body"], "yo'naltirish xabari yozishmada")
    ok(item(akad, T1, "sent")["unread"] is True, "yo'naltirish izohi 18 uchun yangi xabar (o'qilmagan)")
    ok(not has(reg, T1, "inbox", "pending") and has(sirtqi, T1, "inbox", "pending"), "flt=pending: 17 da yo'q, 27 da bor")

    # ============================================================== 5. Rezolyutsiya
    print("— 5. Rezolyutsiya —")
    T2, REF2 = new_thread(akad, "T2 rezolyutsiya", ["talabalar"], body=f"Rezolyutsiya uchun xat ({STAMP}).")
    ok(post(reg, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["buxgalteriya"]}).status_code == 403, "17 rezolyutsiya qo'ya olmaydi (403)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["akademik"]}).status_code == 400, "yuboruvchi (akademik) ijrochi bo'la olmaydi (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": []}).status_code == 400, "ijrochisiz rezolyutsiya (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": " ", "units": ["buxgalteriya"]}).status_code == 400, "matnsiz rezolyutsiya (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["talabalar", "buxgalteriya"], "lead": "buxgalteriya", "due": YDAY}).status_code == 400,
       "o'tgan muddat (400)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": "x", "units": ["buxgalteriya"], "due": "31-12-2026"}).status_code == 400, "noto'g'ri sana (400)")
    ok(not detail(rektor, T2)["resolutions"], "rad etilgan urinishlar rezolyutsiya yaratmadi")
    RTXT = f"Ko'rib chiqib, 3 kun ichida taklif kiritilsin ({STAMP})"
    r = post(rektor, f"/api/portal/threads/{T2}/resolve", {"text": RTXT, "units": ["talabalar", "buxgalteriya"], "lead": "buxgalteriya", "due": D3})
    ok(r.status_code == 200 and r.json()["id"], "rektor rezolyutsiya qo'ydi (talabalar + buxgalteriya, mas'ul buxgalteriya, +3 kun)")
    RID = r.json()["id"]
    d = detail(rektor, T2); z = d["resolutions"]
    ok(len(z) == 1 and z[0]["state"] == "nazoratda" and z[0]["lead_unit"] == "buxgalteriya" and z[0]["due"] == D3 and z[0]["text"] == RTXT,
       "rezolyutsiya kartasi: nazoratda, mas'ul buxgalteriya, muddat")
    ok([x["unit"] for x in z[0]["units"]] == ["talabalar", "buxgalteriya"] and z[0]["can_close"], "ijrochilar ro'yxati, can_close (muallif)")
    ok(d["role"] == "watch" and {"unit": "rektorat", "name": "Rektorat"} in d["watchers"], "rektorat kuzatuvchi (role=watch)")
    rm = [x for x in d["messages"] if x["kind"] == "rezolyutsiya"]
    ok(len(rm) == 1 and rm[0]["meta"]["res_id"] == RID and "Buxgalteriya" in rm[0]["body"], "rezolyutsiya xabari (kind=rezolyutsiya)")
    rb = rcp(d, "buxgalteriya")
    ok(rb["via"] == "rezolyutsiya" and rb["lead"] and rb["due"] == D3 and rb["status"] == "yangi", "buxgalteriya: via rezolyutsiya, lead, due")
    ok(rcp(d, "talabalar")["due"] == D3 and not rcp(d, "talabalar")["lead"], "talabalar: shaxsiy muddat D3, lead emas")
    bi = item(buxg, T2)
    ok(bi is not None and bi["due"] == D3 and bi["my_status"] == "yangi" and bi["resolution"] and bi["unread"], "11 kiruvchida T2 (due D3, resolution belgisi)")
    ri = item(rektor, T2, "control")
    ok(ri is not None and ri["role"] == "watch", "rektor nazorat qutisida T2")
    ok(lst(rektor, "control")["counts"]["control"] >= 1, "counts.control >= 1")
    ok(post(pro, f"/api/portal/threads/{T2}/resolutions/{RID}/close").status_code == 403, "prorektor_oquv rektor rezolyutsiyasini yecha olmaydi (403)")
    ok(not detail(pro, T2)["resolutions"][0]["can_close"], "prorektor uchun can_close=false")
    ok(post(reg, f"/api/portal/threads/{T2}/reply", {"body": "Registrator: taklif tayyor."}).status_code == 200, "17 javob berdi")
    ok(detail(rektor, T2)["resolutions"][0]["state"] == "nazoratda", "bitta ijrochi javobidan keyin hali nazoratda")
    ok(post(buxg, f"/api/portal/threads/{T2}/reply", {"body": "Buxgalteriya: hisob-kitob ilova qilindi."}).status_code == 200, "11 javob berdi")
    z = detail(rektor, T2)["resolutions"][0]
    ok(z["state"] == "bajarildi" and all(x["status"] == "javob berilgan" for x in z["units"]), "ikkala ijrochi javob berdi → bajarildi")
    ok(post(pro, f"/api/portal/threads/{T2}/resolutions/{RID}/close").status_code == 403, "prorektor_oquv yecha olmaydi (bajarilgandan keyin ham 403)")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolutions/{RID}/close").status_code == 200, "rektor nazoratdan yechdi")
    z = detail(rektor, T2)["resolutions"][0]
    ok(z["state"] == "yechilgan" and not z["can_close"], "holat yechilgan")
    ok(post(rektor, f"/api/portal/threads/{T2}/resolutions/999999/close").status_code == 404, "mavjud bo'lmagan rezolyutsiya (404)")

    # ============================================================== 6. Yopish / qayta ochish / arxiv
    print("— 6. Yopish, qayta ochish, arxiv —")
    ok(post(reg, f"/api/portal/threads/{T1}/close", {"note": "x"}).status_code == 403, "17 (qabul qiluvchi) yopa olmaydi (403)")
    ok(post(sirtqi, f"/api/portal/threads/{T1}/close", {"note": "x"}).status_code == 403, "27 yopa olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T1}/reopen").status_code == 403, "17 ochiq yozishmani 'qayta ocha' olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T1}/close", {"note": "Masala hal qilindi"}).status_code == 200, "18 (yuboruvchi) yopdi")
    d = detail(akad, T1)
    ok(d["status"] == "yopilgan" and d["close_note"] == "Masala hal qilindi" and d["closed_by"] and d["perms"]["can_reopen"] and not d["perms"]["can_reply"],
       "holat yopilgan, close_note, can_reopen")
    ok(post(reg, f"/api/portal/threads/{T1}/reply", {"body": "x"}).status_code == 409, "yopilgan yozishmaga javob 409")
    ok(post(reg, f"/api/portal/threads/{T1}/assign", {"user_id": 23}).status_code == 409, "yopilgan yozishmada tayinlash 409")
    ok(post(akad, f"/api/portal/threads/{T1}/close", {"note": ""}).status_code == 409, "qayta yopish 409")
    for c, n in ((akad, 18), (reg, 17), (cc, 23), (sirtqi, 27)):
        ok(has(c, T1, "archive"), f"{n}: arxivda T1")
    ok(not has(reg, T1) and not has(sirtqi, T1) and not has(akad, T1, "sent"), "kiruvchi/yuborilganlarda T1 yo'q")
    ok(not has(buxg, T1, "archive"), "ishtirokchi bo'lmagan 11 arxivida yo'q")
    ok(post(reg, f"/api/portal/threads/{T1}/reopen").status_code == 403, "17 qayta ocha olmaydi (403)")
    ok(post(akad, f"/api/portal/threads/{T1}/reopen").status_code == 200, "18 qayta ochdi")
    ok(detail(akad, T1)["status"] == "ochiq" and has(reg, T1) and has(akad, T1, "sent") and not has(reg, T1, "archive"), "qayta ochildi: kiruvchida, arxivda emas")
    ok(post(akad, f"/api/portal/threads/{T1}/reopen").status_code == 409, "ochiq yozishmani qayta ochish 409")
    ok(post(buxg, f"/api/portal/threads/{T1}/archive", {"on": True}).status_code == 403, "ishtirokchi bo'lmagan arxivlay olmaydi (403)")
    ok(post(reg, f"/api/portal/threads/{T1}/archive", {"on": True}).json()["archived"] is True, "17 shaxsiy arxivga oldi")
    ok(not has(reg, T1) and has(reg, T1, "archive") and item(reg, T1, "archive")["archived"], "17: kiruvchida yo'q, arxivda (archived=true)")
    ok(has(cc, T1) and not has(cc, T1, "archive"), "23 uchun kiruvchida qoladi (shaxsiy arxiv)")
    ok(detail(reg, T1)["perms"]["archived"], "17 detail: perms.archived")
    ok(post(cc, f"/api/portal/threads/{T1}/archive", {"on": True}).status_code == 200 and not has(cc, T1), "23 arxivladi")
    ok(post(cc, f"/api/portal/threads/{T1}/archive", {"on": False}).status_code == 200 and has(cc, T1), "23 arxivdan qaytardi (on=false)")
    ok(post(akad, f"/api/portal/threads/{T1}/reply", {"body": f"Qo'shimcha ma'lumot ({STAMP})."}).status_code == 200, "18 yangi javob yozdi")
    it = item(reg, T1)
    ok(it is not None and it["archived"] is False and it["unread"], "yangi javob 17 uchun arxivdan qaytardi (o'qilmagan)")

    # ============================================================== 7. Qutilar RBAC
    print("— 7. Qutilar RBAC —")
    for box in ("all", "control", "area"):
        ok(reg.get("/api/portal/threads", params={"box": box}).status_code == 403, f"17: box={box} → 403")
    ok(rektor.get("/api/portal/threads", params={"box": "area"}).status_code == 403, "rektor: box=area → 403 (kuratorlik yo'q)")
    ok(rektor.get("/api/portal/threads", params={"box": "all"}).status_code == 200, "rektor: box=all → 200")
    a3 = pro.get("/api/portal/threads", params={"box": "area"})
    ok(a3.status_code == 200 and a3.json()["counts"].get("area_pending") is not None, "prorektor_oquv: box=area → 200, area_pending bor")
    ok(any(x["id"] == T1 for x in all_items(pro, "area")), "prorektor_oquv area: T1 (akademik → talabalar) ko'rinadi")
    ok(reg.get("/api/portal/threads", params={"box": "nomalum"}).status_code == 400, "noto'g'ri quti 400")
    ok(buxg.get(f"/api/portal/threads/{T1}").status_code == 403, "ishtirokchi bo'lmagan bo'lim yozishmani ocha olmaydi (403)")
    ok(pro.get(f"/api/portal/threads/{T1}").status_code == 200, "prorektor (rahbariyat) ochadi")
    ok(post(buxg, f"/api/portal/threads/{T1}/reply", {"body": "x"}).status_code == 403, "begona bo'lim javob yoza olmaydi (403)")

    # ============================================================== 8. Sahifalash va hisoblagichlar
    print("— 8. Sahifalash va hisoblagichlar —")
    tot = lst(rektor, "all", limit=1)["total"]
    real = q("SELECT COUNT(*) FROM portal_threads")[0][0]
    ok(tot == real, f"box=all total = COUNT(*) ({tot} = {real})")
    p1, p2, p10 = (lst(rektor, "all", offset=o, limit=l)["items"] for o, l in ((0, 5), (5, 5), (0, 10)))
    i1, i2, i10 = [x["id"] for x in p1], [x["id"] for x in p2], [x["id"] for x in p10]
    ok(len(i1) == 5 and len(i2) == 5 and not set(i1) & set(i2), "limit=5: sahifalar kesishmaydi")
    ok(i1 + i2 == i10, "1- va 2-sahifa = limit=10 ning birinchi 10 tasi (tartib bilan)")
    lp = lst(rektor, "all", offset=10**6, limit=5)
    ok(lp["items"] == [] and lp["total"] == real, "chegaradan tashqari offset: bo'sh, total saqlanadi")
    ok(lst(rektor, "all", limit=1000)["limit"] == 100 and lst(rektor, "all", offset=-5)["offset"] == 0, "limit ≤ 100, offset ≥ 0")
    for c, n in ((reg, 17), (cc, 23), (buxg, 11), (sirtqi, 27)):
        cn = lst(c, limit=1)["counts"]
        ok(cn["inbox_pending"] == lst(c, "inbox", "pending", limit=1)["total"], f"{n}: counts.inbox_pending = inbox&pending total ({cn['inbox_pending']})")
        ok(cn["inbox"] == lst(c, "inbox", limit=1)["total"], f"{n}: counts.inbox = inbox total ({cn['inbox']})")
        ok(cn["archive"] == lst(c, "archive", limit=1)["total"], f"{n}: counts.archive = archive total ({cn['archive']})")
        ok(cn["sent"] == lst(c, "sent", limit=1)["total"], f"{n}: counts.sent = sent total ({cn['sent']})")
        ok(cn["inbox_unread"] == lst(c, "inbox", "unread", limit=1)["total"], f"{n}: counts.inbox_unread = inbox&unread total ({cn['inbox_unread']})")
        ok(cn["sent_unread"] == lst(c, "sent", "unread", limit=1)["total"], f"{n}: counts.sent_unread = sent&unread total ({cn['sent_unread']})")
        ok(cn["my_overdue"] == lst(c, "inbox", "overdue", limit=1)["total"], f"{n}: counts.my_overdue = inbox&overdue total ({cn['my_overdue']})")
    rc = lst(rektor, limit=1)["counts"]
    ok(rc["all"] == real and rc["leader"] is True, "rektor counts.all = COUNT(*)")
    # Shaxsiy arxivdagi javob kutilayotgan xat: kiruvchida ko'rinmaydi — hisoblagich ham uni sanamasligi kerak
    T4, _ = new_thread(akad, "T4 arxiv-hisob", ["talabalar"])
    ok(post(reg, f"/api/portal/threads/{T4}/archive", {"on": True}).status_code == 200, "17 kutilayotgan T4 ni shaxsiy arxivga oldi")
    cn = lst(reg, limit=1)["counts"]; pt = lst(reg, "inbox", "pending", limit=1)["total"]
    soft(cn["inbox_pending"] == pt, f"17: arxivlangan kutilayotgan xat bilan counts.inbox_pending ({cn['inbox_pending']}) = inbox&pending total ({pt})")
    ok(post(reg, f"/api/portal/threads/{T4}/archive", {"on": False}).status_code == 200, "17 T4 ni arxivdan qaytardi")

    # ============================================================== 9. Qidiruv
    print("— 9. Qidiruv —")
    r = lst(rektor, "all", q_=f"zarbulmasal{U}")
    ok([x["id"] for x in r["items"]] == [T1] and r["total"] == 1, "FTS: matndagi noyob so'z bo'yicha (faqat T1)")
    ok(has(rektor, T1, "all", q_=f"zarbulmas"), "FTS: prefiks bo'yicha")
    ok(has(rektor, T1, "all", q_=f"ZARBULMASAL{U}"), "FTS: katta harf bilan")
    for v in ("ʻ", "’", "'", "‘"):
        r = lst(rektor, "all", q_=f"sho{v}rva{U}")
        ok([x["id"] for x in r["items"]] == [T1], f"FTS: apostrof varianti sho{v}rva{U}")
    ok(has(rektor, T1, "all", q_=REF1) and has(akad, T1, "sent", q_=REF1), f"ref_no bo'yicha ({REF1})")
    ok(has(rektor, T2, "all", q_=REF2), f"ref_no bo'yicha ({REF2})")
    ok(has(akad, T1, "sent", q_="Sirtqi bo'lim") and has(akad, T1, "sent", q_="Sirtqi boʻlim"), "bo'lim nomi bo'yicha (Sirtqi bo'lim, ʻ varianti)")
    ok(has(buxg, T2, "inbox", q_=f"hisob-kitob"), "javob matni bo'yicha (11: hisob-kitob)")
    ok(has(rektor, T1, "all", q_=f"Portal v2 test T1 {STAMP}"), "mavzu bo'yicha")
    r = lst(rektor, "all", q_=f"qwzxvjk{U}")
    ok(r["total"] == 0 and r["items"] == [], "mantiqsiz so'z: bo'sh")
    for s_ in ('"', '*', 'AND', '(', ')', 'OR NOT', '"zarbulmasal', "a\"b*c(", "NEAR(x y)", "'", "%", "_", "\\", "-", "^", "x:y", "{}", "''; DROP TABLE x;--"):
        r = rektor.get("/api/portal/threads", params={"box": "all", "q": s_})
        ok(r.status_code == 200 and "items" in r.json(), f"maxsus belgi q={s_!r}: 200, SQL xatosi yo'q")
    ok(reg.get("/api/portal/threads", params={"box": "inbox", "q": f"zarbulmasal{U}"}).json()["total"] == 1, "17 kiruvchida qidiruv ishlaydi")
    ok(buxg.get("/api/portal/threads", params={"box": "inbox", "q": f"zarbulmasal{U}"}).json()["total"] == 0, "qidiruv RBAC: 11 T1 ni topmaydi")

    # ============================================================== 10. Qoralamalar
    print("— 10. Qoralamalar —")
    n0 = lst(akad, limit=1)["counts"]["drafts"]
    r = akad.put("/api/portal/drafts", json={"subject": f"Qoralama {STAMP}", "body": "birinchi", "to": ["talabalar", "nomalum"], "kind": "sorov", "due": D3})
    ok(r.status_code == 200 and r.json()["ok"] and r.json()["id"], "PUT: qoralama yaratildi")
    DID = r.json()["id"]; MY_DRAFTS.append((akad, DID))
    dl = akad.get("/api/portal/drafts").json(); dd = next((x for x in dl if x["id"] == DID), None)
    ok(dd and dd["to"] == ["talabalar"] and dd["kind"] == "sorov" and dd["due"] == D3, "GET: ro'yxatda, noma'lum bo'lim tashlab yuborildi")
    ok(lst(akad, limit=1)["counts"]["drafts"] == n0 + 1, "counts.drafts +1")
    r = akad.put("/api/portal/drafts", json={"id": DID, "subject": f"Qoralama {STAMP} (tahrir)", "body": "ikkinchi", "to": ["talabalar"]})
    ok(r.status_code == 200 and r.json()["id"] == DID, "PUT: shu id yangilandi")
    dd = next(x for x in akad.get("/api/portal/drafts").json() if x["id"] == DID)
    ok(dd["body"] == "ikkinchi" and dd["subject"].endswith("(tahrir)") and sum(x["id"] == DID for x in akad.get("/api/portal/drafts").json()) == 1, "yangilangan, dublikat yo'q")
    ok(not any(x["id"] == DID for x in reg.get("/api/portal/drafts").json()), "boshqa xodim qoralamani ko'rmaydi")
    ok(reg.put("/api/portal/drafts", json={"id": DID, "subject": "hack"}).status_code == 404, "boshqa xodim qoralamani tahrirlay olmaydi (404)")
    ok(reg.delete(f"/api/portal/drafts/{DID}").status_code == 404, "boshqa xodim qoralamani o'chira olmaydi (404)")
    T3, _ = new_thread(akad, "T3 qoralamadan", ["talabalar"], draft_id=DID)
    detail(reg, T3)
    ok(post(cc, f"/api/portal/threads/{T3}/reply", {"body": f"Hamkasb javobi ({STAMP})"}).status_code == 200, "23 T3 ga javob yozdi")
    # dizayn: "o'qilmagan" = boshqa BO'LIMdan kelgan yangi xabar (hamkasb javobi — "bizniki", kiruvchi emas); o'qilganlik esa xodim bo'yicha
    ok(item(reg, T3)["unread"] is False, "hamkasb (23) javobi 17 uchun kiruvchi xat hisoblanmaydi (o'qilmagan emas)")
    ok(not any(x["id"] == DID for x in akad.get("/api/portal/drafts").json()), "draft_id bilan yuborilganda qoralama o'chdi")
    ok(lst(akad, limit=1)["counts"]["drafts"] == n0, "counts.drafts qaytdi")
    ok(akad.delete(f"/api/portal/drafts/{DID}").status_code == 404, "o'chgan qoralamani o'chirish 404")
    r = reg.put("/api/portal/drafts", json={"subject": f"Q2 {STAMP}"}); D2ID = r.json()["id"]; MY_DRAFTS.append((reg, D2ID))
    T5, _ = new_thread(akad, "T5 begona draft_id", ["talabalar"], draft_id=D2ID)
    ok(any(x["id"] == D2ID for x in reg.get("/api/portal/drafts").json()), "boshqaning draft_id si bilan yuborish uning qoralamasini o'chirmaydi")
    ok(reg.delete(f"/api/portal/drafts/{D2ID}").status_code == 200, "egasi o'chirdi")
    ok(akad.put("/api/portal/drafts", json={"subject": "x", "due": "bugun"}).status_code == 400, "noto'g'ri sana 400")

    # ============================================================== 11. Shablonlar
    print("— 11. Shablonlar —")
    r = post(akad, "/api/portal/templates", {"title": f"Test shablon {STAMP}", "subject": "So'rov: {bolim}", "body": "Sana {sana}, muddat {muddat}",
                                             "kind": "sorov", "due_days": 5, "to": ["talabalar"]})
    ok(r.status_code == 200 and r.json()["id"], "18: akademik bo'limi uchun shablon yaratildi")
    TPL = r.json()["id"]; MY_TEMPLATES.append((akad, TPL))
    tl = akad.get("/api/portal/templates").json(); t = next((x for x in tl if x["id"] == TPL), None)
    ok(t and t["scope"] == "bolim" and t["mine"] and t["uses"] == 0 and t["due_days"] == 5 and t["to"] == ["talabalar"], "18 ro'yxatida: bolim, mine, uses=0")
    ok(not any(x["id"] == TPL for x in reg.get("/api/portal/templates").json()), "17 (boshqa bo'lim) ko'rmaydi")
    ok(reg.delete(f"/api/portal/templates/{TPL}").status_code == 403, "17 o'chira olmaydi (403)")
    ok(post(reg, f"/api/portal/templates/{TPL}/use").status_code == 200, "begona bo'lim /use: 200 (jim)")
    ok(next(x for x in akad.get("/api/portal/templates").json() if x["id"] == TPL)["uses"] == 0, "begona bo'lim /use hisoblagichni oshirmaydi")
    ok(post(akad, f"/api/portal/templates/{TPL}/use").status_code == 200, "18 /use")
    post(akad, f"/api/portal/templates/{TPL}/use")
    ok(next(x for x in akad.get("/api/portal/templates").json() if x["id"] == TPL)["uses"] == 2, "uses = 2")
    inst = {r_[0] for r_ in q("SELECT id FROM portal_templates WHERE owner_unit='*'")}
    for c, n in ((reg, 17), (sirtqi, 27), (kaf, 31), (rektor, 2), (iteng, 22)):
        tl = c.get("/api/portal/templates").json()
        ok(inst and inst <= {x["id"] for x in tl if x["scope"] == "institut" and not x["mine"]}, f"{n}: institut shablonlari ko'rinadi ({len(inst)})")
    ok(akad.delete(f"/api/portal/templates/{min(inst)}").status_code == 403, "institut shablonini bo'lim o'chira olmaydi (403)")
    ok(post(akad, "/api/portal/templates", {"title": " ", "body": "x"}).status_code == 400, "nomsiz shablon 400")
    ok(post(akad, "/api/portal/templates", {"title": "x"}).status_code == 400, "bo'sh shablon 400")
    ok(akad.delete(f"/api/portal/templates/{TPL}").status_code == 200, "18 o'z shablonini o'chirdi")
    MY_TEMPLATES.clear()
    ok(akad.delete(f"/api/portal/templates/{TPL}").status_code == 404, "qayta o'chirish 404")

    # ============================================================== 12. Fayllar
    print("— 12. Fayllar —")
    up = lambda c, name, data, cat="Boshqa": c.post("/api/portal/files", params={"name": name, "category": cat}, content=data)
    TXT = f"Portal test fayli {STAMP}\nO'zbekcha matn: sho'rva, ta'lim.\n".encode()
    r = up(reg, f"portal_test_{U}.txt", TXT)
    ok(r.status_code == 200 and r.json()["ok"] and r.json()["scan"] in ("toza", "tekshirilmadi"), f"to'g'ri .txt yuklandi (scan={r.json().get('scan')})")
    FID = r.json()["id"]
    row = q("SELECT sha256, mime, stored, size, owner_unit, category FROM portal_files WHERE id=?", (FID,))[0]
    ok(row[0] == hashlib.sha256(TXT).hexdigest(), "sha256 ustuni saqlandi va to'g'ri")
    ok(row[1].startswith("text/plain") and row[3] == len(TXT) and row[4] == "talabalar" and row[5] == "Boshqa", "mime, hajm, bo'lim, toifa")
    ok("/" not in row[2] and ".." not in row[2] and row[2].endswith(".txt") and len(row[2]) == 36, "diskdagi nom tasodifiy (uuid.txt)")
    dl = reg.get(f"/api/portal/files/{FID}/download")
    ok(dl.status_code == 200 and dl.content == TXT, "yuklab olish: mazmun bir xil")
    ok(dl.headers.get("x-content-type-options") == "nosniff", "X-Content-Type-Options: nosniff")
    ok("no-store" in dl.headers.get("cache-control", ""), "Cache-Control: no-store")
    ok(buxg.get(f"/api/portal/files/{FID}/download").status_code == 403, "ulashilmagan bo'lim yuklab ola olmaydi (403)")
    ok(cc.get(f"/api/portal/files/{FID}/download").status_code == 200, "o'z bo'limi xodimi (23) yuklab oladi")
    exe = b"MZ\x90\x00" + b"\x00" * 56 + (64).to_bytes(4, "little") + b"PE\x00\x00" + b"\x00" * 200
    r = up(reg, f"hisobot_{U}.pdf", exe)
    ok(r.status_code == 415, f"exe → .pdf nomi bilan: 415 ({r.json().get('detail', '')[:60]})")
    ok(up(reg, f"skript_{U}.txt", b"#!/bin/sh\nrm -rf /\n").status_code == 415, "shebang skript .txt: 415")
    ok(up(reg, f"soxta_{U}.pdf", b"bu pdf emas").status_code == 415, "soxta .pdf (magic yo'q): 415")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/vbaProject.bin", b"\x00VBA")
    r = up(reg, f"makros_{U}.docx", buf.getvalue())
    ok(r.status_code == 415 and "akros" in r.json().get("detail", ""), "vbaProject.bin li docx: 415 (makros)")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z: z.writestr("ichki/virus.exe", b"MZ")
    ok(up(reg, f"arxiv_{U}.zip", buf.getvalue()).status_code == 415, "ichida .exe bor zip: 415")
    ok(up(reg, f"bad_{U}.exe", b"hello").status_code == 400, ".exe kengaytma: 400")
    ok(up(reg, f"bosh_{U}.txt", b"").status_code == 400, "bo'sh fayl: 400")
    r = up(reg, f"../../x_{U}.txt", b"path traversal test\n")
    ok(r.status_code == 200 and r.json()["name"] == f"x_{U}.txt", f"'../../x_{U}.txt' → nom tozalandi: {r.json().get('name')}")
    FID2 = r.json()["id"]
    st = q("SELECT name, stored FROM portal_files WHERE id=?", (FID2,))[0]
    files_dir = ROOT / "data" / "portal_files"
    ok(st[0] == f"x_{U}.txt" and "/" not in st[1] and not (ROOT.parent / f"x_{U}.txt").exists() and not (ROOT / f"x_{U}.txt").exists(),
       "bazada xavfsiz nom, fayl papkadan tashqariga yozilmadi")
    if files_dir.is_dir(): ok((files_dir / st[1]).is_file(), "fayl portal_files ichida")
    r = up(reg, f"..\\..\\win_{U}.txt", b"win\n")
    ok(r.status_code == 200 and r.json()["name"] == f"win_{U}.txt", "Windows yo'li (..\\..\\) ham tozalandi")
    rl = rektor.get("/api/portal/files").json()
    ok(any(x["id"] == FID for x in rl["items"]), "rektor (rahbariyat) faylni ko'radi")
    ok(not any(x["id"] == FID for x in buxg.get("/api/portal/files").json()["items"]), "11 ro'yxatida yo'q")
    au = q("SELECT COUNT(*) FROM audit_log WHERE id>? AND resource='portal' AND action='portal: fayl rad etildi' AND allowed=0", (AUDIT0,))[0][0]
    ok(au >= 4, f"rad etilgan yuklashlar auditda ({au})")

    # ============================================================== 13. Eslatmalar
    print("— 13. Eslatmalar —")
    rem = iteng.get("/api/portal/reminders").json()
    ok(isinstance(rem.get("items"), list) and all({"thread_id", "ref_no", "subject", "due", "days_left", "kind", "who"} <= set(x) for x in rem["items"]),
       "reminders tuzilmasi")
    lim = (TODAY + dt.timedelta(days=2)).isoformat()
    exp = q("""SELECT t.id FROM portal_recipients r JOIN portal_threads t ON t.id=r.thread_id WHERE r.unit='it' AND r.assignee=22 AND t.status='ochiq'
               AND r.status IN ('yangi','o''qilgan') AND COALESCE(NULLIF(r.due,''), NULLIF(t.due,'')) <= ?""", (lim,))
    if exp:
        got = {x["thread_id"] for x in rem["items"] if x["who"] == "menga"}
        ok({e[0] for e in exp} <= got, f"22: biriktirilgan LMS xati who=menga ({sorted(got)})")
        ok(all(x["kind"] in ("bugun", "ertaga", "otgan", "yaqin") for x in rem["items"]), "kind qiymatlari to'g'ri")
    else:
        print("  (22 ga biriktirilgan, muddati yaqin xat demo bazada yo'q — faqat tuzilma tekshirildi)")
    nt = cc.get("/api/notifications").json()
    ok("items" in nt and "unread" in nt and all(isinstance(x["title"], str) for x in nt["items"]), "23 /api/notifications tuzilmasi")
    rem23 = {x["thread_id"] for x in cc.get("/api/portal/reminders").json()["items"] if x["who"] == "menga"}
    nids = {x["id"] for x in nt["items"]}
    ok(all(f"pm{t_}" in nids for t_ in rem23), f"23: har bir 'menga' eslatmasi bildirishnomada ({sorted(rem23)})")
    rr = reg.get("/api/portal/reminders").json()["items"]
    ok(all(x["who"] in ("menga", "bolimga", "yuborgan", "nazorat") for x in rr), "17 eslatmalari: who qiymatlari to'g'ri")

    # ============================================================== 14. Audit
    print("— 14. Audit —")
    rows = q("SELECT action, detail, allowed, user_id FROM audit_log WHERE id>? AND resource='portal'", (AUDIT0,))
    def seen(action, ref, uid=None, allowed=1):
        return any(a == action and ref in (dt_ or "") and al == allowed and (uid is None or u_ == uid) for a, dt_, al, u_ in rows)
    ok(seen("portal: rezolyutsiya qo'yildi", REF2, 2), "audit: rezolyutsiya qo'yildi (rektor)")
    ok(seen("portal: rezolyutsiya nazoratdan yechildi", REF2, 2), "audit: rezolyutsiya nazoratdan yechildi")
    ok(seen("portal: ijrochi tayinlandi", REF1, 23) and seen("portal: ijrochi tayinlandi", REF1, 17), "audit: ijrochi tayinlandi (23 va 17)")
    ok(seen("portal: xat yo'naltirildi", REF1, 17), "audit: xat yo'naltirildi")
    ok(seen("portal: yozishma yopildi", REF1, 18) and seen("portal: yozishma qayta ochildi", REF1, 18), "audit: yopildi / qayta ochildi")
    ok(seen("portal: xat yuborildi", REF1, 18), "audit: xat yuborildi")
    ok(seen("portal: rezolyutsiya", REF2, 17, 0), "audit: 17 ning rezolyutsiya urinishi rad (allowed=0)")
    ok(seen("portal: yozishmani yopish", REF1, 17, 0), "audit: 17 ning yopish urinishi rad (allowed=0)")
    ok(seen("portal: yozishmani ochish", f"{REF1}", 11, 0), "audit: 11 ning begona yozishmani ochishi rad (allowed=0)")
    ok(any(a == "portal: fayl yuklab olindi" and al == 1 for a, _, al, _u in rows), "audit: fayl yuklab olindi")
    ok(any(a.startswith("portal: all qutisi") and al == 0 and u_ == 17 for a, _, al, u_ in rows), "audit: 17 ning box=all urinishi rad")

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
    print(f"\nJami tekshiruvlar: {N[0]}" + (f" · backend xatolari: {len(SOFT)}" if SOFT else " · hammasi o'tdi"))
    for s_ in SOFT: print("  ✗", s_)
    for s_ in NOTES: print("  ⚠", s_)
    sys.exit(1 if SOFT else 0)
