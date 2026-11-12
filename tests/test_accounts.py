import os
"""Akkauntlar boshqaruvi (app/accounts.py): uchidan-uchigacha HTTP testlar (server http://127.0.0.1:8000 da ishlab turishi kerak).

Ishga tushirish:  .venv/bin/python tests/test_accounts.py
Qayta ishga tushirish mumkin (qayta seed shart emas): test o'z akkauntini «TEST-AKK» prefiksli nom bilan yaratadi, oxirida API orqali
faolsizlantiradi va bazadan o'chiradi (faqat shu prefiksli va accounts.py yaratgan — created_by bo'lgan — yozuvlar). Demo akkauntlar
o'zgarmaydi: kirish ro'yxati (/api/users) test oldidagi bilan bir xil ekani oxirida tekshiriladi. Audit yozuvlari tarix sifatida qoladi.
Bazaga yozish faqat: test akkauntini tozalash va Telegram'ni uzishni tekshirish uchun test akkauntiga soxta telegram_id qo'yish.
Eslatma: test 6 ta noto'g'ri kirish urinishini qiladi (IP cheklovi 10 daqiqada 20 ta) — ketma-ket ko'p marta ishga tushirmang.
"""
import hashlib, re, sqlite3, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db")
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
PW = "Isft2026"
PREFIX = "TEST-AKK"
IT, REKTOR = 21, 2

N = [0]
def ok(cond, msg):
    N[0] += 1
    print(("✓ " if cond else "✗ XATO: ") + msg)
    if not cond: sys.exit(1)

def login(uid, pw=PW):
    c = httpx.Client(base_url=B, timeout=60)
    r = c.post("/api/login", json={"user_id": uid, "password": pw})
    return c, r

def S(uid, pw=PW):
    c, r = login(uid, pw)
    assert r.status_code == 200, f"login {uid}: {r.status_code} {r.text}"
    return c

def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try: return con.execute(sql, args).fetchall()
    finally: con.close()

def w(sql, args=()):
    con = sqlite3.connect(DB, timeout=30)
    try:
        n = con.execute(sql, args).rowcount; con.commit(); return n
    finally: con.close()

def cleanup():
    ids = [r[0] for r in q(f"SELECT id FROM users WHERE full_name LIKE '{PREFIX}%' AND created_by IS NOT NULL")]
    for i in ids:
        w("DELETE FROM sessions WHERE user_id=?", (i,))
        w(f"DELETE FROM users WHERE id=? AND full_name LIKE '{PREFIX}%' AND created_by IS NOT NULL", (i,))
    return len(ids)

def audit_has(action, uid_tag, allowed=1, user_id=None):
    sql = "SELECT 1 FROM audit_log WHERE resource='accounts' AND action=? AND allowed=? AND detail LIKE ?"
    args = [action, allowed, f"%{uid_tag}%"]
    if user_id: sql += " AND user_id=?"; args.append(user_id)
    return bool(q(sql, args))

def main():
    T0 = time.strftime("%Y-%m-%dT%H:%M:%S")
    n = cleanup()
    if n: print(f"  (oldingi ishga tushirishdan qolgan {n} ta test akkaunti tozalandi)")
    anon = httpx.Client(base_url=B, timeout=30)
    login_list0 = [u["id"] for u in anon.get("/api/users").json()]

    # ---------- statik: menyu va ko'rinish ----------
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    ok('data-v="accounts"' in html and 'id="v-accounts"' in html and 'src="accounts.js"' in html, "index.html: menyu, bo'lim va skript ulangan")
    ok("renderAccounts" in js and '["accounts", "rbac", "audit"].forEach' in js and 'ME.role_key !== "it_head"' in js, "app.js: ko'rinish xaritasi; tizim sahifalari menyuda faqat AT bo'limi boshlig'ida")
    ok(anon.get("/api/accounts").status_code == 401, "kirmagan foydalanuvchi: 401")

    # ---------- ruxsatlar ----------
    for uid in (17, 11):
        c = S(uid)
        ok(c.get("/api/accounts").status_code == 403, f"#{uid}: ro'yxat 403")
        ok(c.post("/api/accounts", json={"position": f"{PREFIX} x", "role": "yuridik"}).status_code == 403, f"#{uid}: yaratish 403")
        ok(c.post(f"/api/accounts/{IT}/reset-password").status_code == 403, f"#{uid}: parol tiklash 403")
    ok(bool(q("SELECT 1 FROM audit_log WHERE resource='accounts' AND allowed=0 AND user_id=17 AND ts>=?", (T0,))), "audit: #17 urinishi rad (allowed=0)")

    rk = S(REKTOR)
    r = rk.get("/api/accounts"); d = r.json()
    ok(r.status_code == 200 and d["can_edit"] is False and d["demo"] is False and len(d["items"]) >= 40, "rektor: ro'yxat 200, can_edit=False")
    ok(all("link_code" not in i and "can" not in i for i in d["items"]), "rektor: Telegram kodlari va amal huquqlari berilmaydi")
    ok(rk.post("/api/accounts", json={"position": f"{PREFIX} rektor", "role": "yuridik"}).status_code == 403, "rektor: yaratish 403")
    for a in ("reset-password", "revoke", "deactivate", "unlock", "unlink-telegram"):
        ok(rk.post(f"/api/accounts/39/{a}").status_code == 403, f"rektor: {a} 403")
    ok(rk.post("/api/accounts/39/update", json={"person": "X"}).status_code == 403, "rektor: tahrirlash 403")
    ok(bool(q("SELECT 1 FROM audit_log WHERE resource='accounts' AND allowed=0 AND user_id=? AND ts>=?", (REKTOR, T0))), "audit: rektorning o'zgartirish urinishi rad")

    # ---------- it_head: yaratish ----------
    it = S(IT)
    d = it.get("/api/accounts").json()
    ok(d["can_edit"] is True and all("can" in i for i in d["items"]), "it_head: ro'yxat, can_edit=True")
    assign = {x["key"] for x in d["roles"] if x["assignable"]}
    ok(not assign & {"rektor", "kengash", "it_head", "kotib", "prorektor_oquv", "prorektor_moliya", "oqituvchi"} and "yuridik" in assign,
       "tayinlanadigan rollar: rahbariyat, it_head, o'qituvchi yo'q")
    me = next(i for i in d["items"] if i["id"] == IT)
    ok(me["self"] and me["can"]["status"] is False and me["can"]["reset"] is False, "o'z akkaunti: holat va parol tiklash yopiq")

    for bad in ("rektor", "it_head", "prorektor_oquv", "kengash", "kotib", "oqituvchi"):
        r = it.post("/api/accounts", json={"position": f"{PREFIX} escalate", "role": bad})
        ok(r.status_code == 403, f"yaratish rol={bad}: 403")
    ok(not q(f"SELECT 1 FROM users WHERE full_name LIKE '{PREFIX} escalate%'"), "imtiyozli akkaunt yaratilmadi")
    r = it.post("/api/accounts", json={"position": "", "role": "yuridik"}); ok(r.status_code == 400 and r.json()["detail"]["field"] == "position", "lavozim nomisiz: 400")
    r = it.post("/api/accounts", json={"position": f"{PREFIX} tyutor", "role": "tyutor", "unit": "yuridik"}); ok(r.status_code == 400 and r.json()["detail"]["field"] == "unit", "tyutor + bo'lim (fakultet emas): 400")
    r = it.post("/api/accounts", json={"position": f"{PREFIX} dekan", "role": "dekan", "unit": "fak2"}); ok(r.status_code == 400 and r.json()["detail"]["field"] == "role", "dekan lavozimi bekor qilingan: 400 (role)")
    ok("dekan" not in {x["key"] for x in d["roles"]}, "rollar ro'yxatida dekan yo'q")
    u13 = next((i for i in d["items"] if i["id"] == 13), None)
    ok(u13 is not None and u13["active"] is False, "#13 (sobiq dekan) — ro'yxatda, faol emas")
    r = it.post("/api/accounts/13/activate"); ok(r.status_code == 400, f"#13 ni faollashtirib bo'lmaydi (lavozim bekor qilingan): {r.status_code}")
    r = it.post("/api/accounts", json={"position": f"{PREFIX} x", "role": "yuridik", "unit": "yoq_bolim"}); ok(r.status_code == 400, "noma'lum bo'lim: 400")

    stamp = time.strftime("%H%M%S")
    r = it.post("/api/accounts", json={"position": f"{PREFIX} Yuridik bo'lim mutaxassisi {stamp}", "person": "Testov Test Testovich", "role": "yuridik"})
    ok(r.status_code == 200, f"yaratildi: {r.status_code} {r.text[:200]}")
    cr = r.json(); tid, pw1 = cr["id"], cr["password"]
    ok(r.headers.get("cache-control") == "no-store", "parol javobi keshlanmaydi (no-store)")
    ok(re.fullmatch(r"[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}", pw1) and re.search(r"\d", pw1) and re.search(r"[A-Za-z]", pw1), "vaqtinchalik parol: 3×4, harf va raqam")
    row = q("SELECT full_name, role, unit, pin, active, created_by, link_code FROM users WHERE id=?", (tid,))[0]
    ok(row[1] == "yuridik" and row[2] == "yuridik" and row[4] == 1 and row[5] == IT, "bazada: rol, bo'lim (users.unit), faol, created_by")
    ok(row[3].startswith("pbkdf2$") and pw1 not in row[3], "bazada faqat parol xeshi")
    ok(row[6] == cr["link_code"] and row[6].startswith("AKK"), "Telegram ulash kodi yaratildi")
    item = next(i for i in it.get("/api/accounts").json()["items"] if i["id"] == tid)
    ok(item["unit_name"] and item["active"] and item["last_login"] is None and item["can"]["edit"], "ro'yxatda: bo'lim nomi, faol, hali kirmagan")
    ok(tid in [u["id"] for u in anon.get("/api/users").json()], "kirish ro'yxatida ko'rinadi")

    # ---------- kirish va parolni tiklash ----------
    t1 = S(tid, pw1)
    ok(t1.get("/api/me").status_code == 200, "vaqtinchalik parol bilan kirildi")
    r = it.post(f"/api/accounts/{tid}/reset-password"); pw2 = r.json().get("password")
    ok(r.status_code == 200 and pw2 and pw2 != pw1 and r.json()["revoked"] >= 1, "parol tiklandi, sessiyalar yopildi")
    ok(t1.get("/api/me").status_code == 401, "eski sessiya endi ishlamaydi")
    ok(login(tid, pw1)[1].status_code == 401, "eski parol ishlamaydi")
    t2 = S(tid, pw2)
    ok(t2.get("/api/me").status_code == 200, "yangi vaqtinchalik parol ishlaydi")
    item = next(i for i in it.get("/api/accounts").json()["items"] if i["id"] == tid)
    ok(item["last_login"] and item["sessions"] >= 1, "oxirgi kirish va ochiq sessiyalar ko'rinadi")

    # ---------- tahrirlash va imtiyoz oshirish ----------
    r = it.post(f"/api/accounts/{tid}/update", json={"role": "marketing", "unit": "marketing", "person": "Testov Test"})
    ok(r.status_code == 200 and r.json()["changed"], "tahrirlandi: rol marketing, ism")
    ok(q("SELECT role, unit, full_name FROM users WHERE id=?", (tid,))[0][:2] == ("marketing", "marketing"), "bazada: rol va bo'lim yangilandi")
    ok(t2.get("/api/me").status_code == 401, "rol o'zgargach eski sessiya yopildi")
    for bad in ("rektor", "it_head", "prorektor_moliya", "kengash"):
        r = it.post(f"/api/accounts/{tid}/update", json={"role": bad})
        ok(r.status_code in (400, 403), f"rolni {bad} ga o'zgartirish rad: {r.status_code}")
    ok(q("SELECT role FROM users WHERE id=?", (tid,))[0][0] == "marketing", "rol o'zgarmadi")
    ok(it.post(f"/api/accounts/{REKTOR}/update", json={"person": "Boshqa"}).status_code == 403, "rektor akkauntini tahrirlash rad")
    ok(it.post(f"/api/accounts/{IT}/update", json={"role": "yuridik"}).status_code == 403, "o'z rolini o'zgartirish rad")
    ok(q("SELECT role FROM users WHERE id=?", (IT,))[0][0] == "it_head", "it_head roli o'zgarmadi")
    ok(audit_has("akkauntlar: rolni o'zgartirish", f"#{tid}", 0, IT), "audit: imtiyoz oshirish urinishi rad yozildi")

    # ---------- o'ziga va himoyalangan akkauntlarga cheklovlar ----------
    ok(it.post(f"/api/accounts/{IT}/deactivate").status_code == 403, "o'zini faolsizlantirish rad")
    ok(it.post(f"/api/accounts/{IT}/reset-password").status_code == 403, "o'z parolini bu yerda tiklash rad")
    ok(it.post(f"/api/accounts/{REKTOR}/deactivate").status_code == 403, "rektorni faolsizlantirish rad (faqat CLI)")
    ok(q("SELECT active FROM users WHERE id IN (?,?)", (IT, REKTOR)) == [(1,), (1,)], "it_head va rektor faol")
    ok(it.get("/api/me").status_code == 200, "it_head sessiyasi ishlayapti")

    # ---------- sessiyalarni yopish, blok, Telegram, sinov paroli ----------
    t3 = S(tid, pw2)
    r = it.post(f"/api/accounts/{tid}/revoke")
    ok(r.status_code == 200 and r.json()["revoked"] >= 1 and t3.get("/api/me").status_code == 401, "sessiyalar yopildi")
    for _ in range(5): login(tid, "noto'g'ri-parol-1")
    ok(login(tid, pw2)[1].status_code == 429, "5 ta xato urinishdan keyin akkaunt bloklandi (429)")
    item = next(i for i in it.get("/api/accounts").json()["items"] if i["id"] == tid)
    ok(item["locked_min"] > 0 and item["can"]["unlock"], "ro'yxatda: bloklangan")
    ok(it.post(f"/api/accounts/{tid}/unlock").status_code == 200, "blokdan chiqarildi")
    ok(login(tid, pw2)[1].status_code == 200, "blokdan keyin kirish mumkin")
    w("UPDATE users SET telegram_id=-424242 WHERE id=? AND full_name LIKE ?", (tid, f"{PREFIX}%"))
    ok(next(i for i in it.get("/api/accounts").json()["items"] if i["id"] == tid)["telegram"], "Telegram ulangan ko'rinadi")
    ok(it.post(f"/api/accounts/{tid}/unlink-telegram").status_code == 200 and q("SELECT telegram_id FROM users WHERE id=?", (tid,))[0][0] is None, "Telegram uzildi")
    demo = it.get("/api/accounts").json()["demo"]
    if demo:
        ok(it.post(f"/api/accounts/{tid}/demo-password").status_code == 200 and login(tid, PW)[1].status_code == 200, "sinov paroli tiklandi (sinov rejimi)")
        pw_now = PW
    else:
        ok(it.post(f"/api/accounts/{tid}/demo-password").status_code == 400, "sinov rejimi o'chiq: sinov paroli rad")
        pw_now = pw2

    # ---------- faolsizlantirish ----------
    t4 = S(tid, pw_now)
    ok(t4.get("/api/me").status_code == 200, "faolsizlantirishdan oldin sessiya ishlaydi")
    r = it.post(f"/api/accounts/{tid}/deactivate")
    ok(r.status_code == 200 and q("SELECT active FROM users WHERE id=?", (tid,))[0][0] == 0, "faolsizlantirildi (active=0)")
    ok(t4.get("/api/me").status_code == 401 and t4.get("/api/mywork").status_code == 401, "mavjud sessiya ishlamay qoldi")
    # sessiya yozuvi o'chirilmagan holat (masalan, boshqa worker yaratgan) ham ishlamasligi kerak: to'g'ri token qo'lda qo'yiladi
    tok = "test-akk-" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:24]
    pin = q("SELECT pin FROM users WHERE id=?", (tid,))[0][0]
    w("INSERT INTO sessions(token,user_id,created,expires,pw_tag,ip) VALUES(?,?,?,?,?,?)",
      (hashlib.sha256(tok.encode()).hexdigest(), tid, time.time(), time.time() + 300, hashlib.sha256(str(pin).encode()).hexdigest()[:16], "test"))
    raw = httpx.Client(base_url=B, timeout=30, cookies={"sid": tok})
    r = raw.get("/api/me")
    ok(r.status_code == 401 and "faol emas" in r.text, "faol bo'lmagan akkauntning yaroqli tokeni ham rad (main.ctx)")
    r = login(tid, pw_now)[1]
    ok(r.status_code in (401, 403) and "faol" in r.text, f"to'g'ri parol bilan ham kirish rad: {r.status_code}")
    ok(tid not in [u["id"] for u in anon.get("/api/users").json()], "kirish ro'yxatidan yashirildi")
    item = next(i for i in it.get("/api/accounts").json()["items"] if i["id"] == tid)
    ok(item["active"] is False, "akkauntlar ro'yxatida: faol emas")
    ok(bool(q("SELECT 1 FROM audit_log WHERE user_id=? AND action='tizimga kirish' AND allowed=0 AND detail LIKE '%faol emas%'", (tid,))), "audit: faol bo'lmagan akkauntning kirish urinishi")

    r = it.post(f"/api/accounts/{tid}/activate")
    ok(r.status_code == 200 and q("SELECT active FROM users WHERE id=?", (tid,))[0][0] == 1, "qayta faollashtirildi")
    ok(raw.get("/api/me").status_code == 200, "o'sha token faollashtirilgach ishlaydi (demak rad faqat holat sababli edi)")
    t5 = S(tid, pw_now)
    ok(t5.get("/api/me").status_code == 200 and tid in [u["id"] for u in anon.get("/api/users").json()], "yana kira oladi va ro'yxatda")

    # ---------- audit ----------
    for a in ("akkauntlar: yaratildi", "akkauntlar: parol tiklandi", "akkauntlar: tahrirlandi", "akkauntlar: sessiyalar yopildi",
              "akkauntlar: blokdan chiqarildi", "akkauntlar: Telegram uzildi", "akkauntlar: faolsizlantirildi", "akkauntlar: faollashtirildi"):
        ok(audit_has(a, f"#{tid}", 1, IT), f"audit: {a}")
    ok(audit_has("akkauntlar: faolsizlantirish", f"#{IT}", 0, IT), "audit: o'zini faolsizlantirish urinishi rad")
    ok(audit_has("akkauntlar: faolsizlantirish", f"#{REKTOR}", 0, IT), "audit: rektorni faolsizlantirish urinishi rad")
    ok(not q("SELECT 1 FROM audit_log WHERE resource='accounts' AND ts>=? AND (detail LIKE ? OR detail LIKE ?)", (T0, f"%{pw1}%", f"%{pw2}%")),
       "audit jurnalida parol ochiq holda yo'q")

    # ---------- tozalash ----------
    ok(it.post(f"/api/accounts/{tid}/deactivate").status_code == 200, "test akkaunti faolsizlantirildi")
    ok(cleanup() == 1 and not q("SELECT 1 FROM users WHERE id=?", (tid,)), "test akkaunti bazadan o'chirildi (prefiks bilan himoyalangan)")
    ok([u["id"] for u in anon.get("/api/users").json()] == login_list0, "kirish ro'yxati test oldidagi bilan bir xil")
    print(f"\nHammasi o'tdi: {N[0]} ta tekshiruv.")

if __name__ == "__main__":
    main()
