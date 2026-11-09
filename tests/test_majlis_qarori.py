import httpx, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
B = os.environ.get("ISFT_TEST_URL", "http://127.0.0.1:8000")
def S(uid):
    c = httpx.Client(base_url=B, timeout=300); r = c.post("/api/login", json={"user_id": uid, "password": "Isft2026"}); assert r.status_code == 200; return c
ok = lambda cond, msg: print(("✓ " if cond else "✗ XATO: ") + msg) or (cond or sys.exit(1))
kotib, ithead, itstaff, reg, rektor, buxg = S(20), S(21), S(22), S(17), S(2), S(11)
print(rektor.post("/api/dec/demo-reset").json())
cap = kotib.get("/api/dec/capabilities").json(); ok(cap["audio"] is False, "ovoz: o'chiq, demo transkript bor")
ok(ithead.post("/api/dec/draft", json={"title": "x", "transcript": cap["sample"]}).status_code == 403, "IT qoralama yarata olmaydi (403)")
d = kotib.post("/api/dec/draft", json={"title": "Rektorat tezkor yig'ilishi", "transcript": cap["sample"], "source": "demo"}).json()
print(d["extract_note"]); T = d["tasks"]
ok(len(T) == 2, "2 ta topshiriq"); it, rg = T
ok(it["unit"] == "it" and it["due_at"].endswith("T15:00") and it["assignee_stated"] is None, f"IT: bo'lim, 15:00, xodim aytilmagan ({it['due_text']})")
ok(rg["unit"] == "registrator" and rg["due_at"] is None and rg["depends_on"] == it["id"], f"Registrator: muddat aytilmagan, IT'ga bog'liq ({rg['dep_text']})")
ok(d["incident"] and "LMS" in d["incident"]["title"], f"Xizmat markazi hodisasiga bog'landi: {d['incident']['title']} ({d['incident']['n']} murojaat)")
ok(rektor.get(f"/api/dec/{d['id']}").status_code == 403, "Rektor qoralamani ko'rmaydi")
ok(ithead.get("/api/dec/list").json()["queue"]["tasks"] == [], "Qoralama IT navbatida yo'q")
# tahrir
e = kotib.put(f"/api/dec/{d['id']}", json={"title": d["title"], "minutes": d["minutes"] + "\nKotib: tahrir.", "tasks": [
    {"id": it["id"], "text": "LMS'ga kirish muammosini tekshirish va sababini aniqlash", "unit": "it", "assignee": "", "due_at": it["due_at"], "depends_on": None},
    {"id": rg["id"], "text": rg["text"], "unit": "registrator", "assignee": "", "due_at": None, "depends_on": it["id"]}]}).json()
ok(e["tasks"][0]["text"].startswith("LMS'ga kirish muammosini tekshirish") and e["tasks"][0]["due_text"], "Kotib matnni tahrir qildi, muddat ifodasi saqlandi")
# tasdiq x2
c1 = kotib.post(f"/api/dec/{d['id']}/confirm").json(); c2 = kotib.post(f"/api/dec/{d['id']}/confirm").json()
ok(c1["already"] is False and c2["already"] is True, "Qayta tasdiqlash: already=True")
import sqlite3; n = sqlite3.connect(str(Path(os.environ.get("ISFT_CORE_DB") or ROOT / "data" / "jarvis.db"))).execute("SELECT COUNT(*) FROM tasks WHERE meeting_id=?", (d["id"],)).fetchone()[0]
ok(n == 2, f"Bazada dublikat yo'q (2 ta)")
ok(kotib.put(f"/api/dec/{d['id']}", json={"title": "x", "minutes": "", "tasks": []}).status_code == 409, "Tasdiqlangandan keyin tahrir yo'q (409)")
# navbat
q = ithead.get("/api/dec/list").json()["queue"]; ok(len(q["tasks"]) == 1 and q["tasks"][0]["status"] == "yangi", "IT navbatida 1 ta yangi topshiriq")
ok(itstaff.get("/api/dec/list").json()["queue"]["tasks"] == [], "IT muhandisi hali ko'rmaydi (biriktirilmagan)")
ok(reg.post(f"/api/dec/task/{it['id']}/assign", json={"user_id": 20}).status_code == 403, "Registrator IT topshirig'ini biriktira olmaydi")
ok(ithead.post(f"/api/dec/task/{it['id']}/assign", json={"user_id": 20}).status_code == 400, "IT boshlig'i boshqa bo'lim xodimiga biriktira olmaydi")
ok(ithead.post(f"/api/dec/task/{it['id']}/assign", json={"user_id": 22}).json()["ok"], "IT boshlig'i → IT muhandisiga biriktirdi")
ok(len(itstaff.get("/api/dec/list").json()["queue"]["tasks"]) == 1, "IT muhandisi navbatida ko'rinadi")
# registrator bloklangan
ok(reg.post(f"/api/dec/task/{rg['id']}/update", json={"status": "bajarildi", "result": "xabar"}).status_code == 409, "Registrator IT natijasisiz yakunlay olmaydi (409)")
ok(buxg.post(f"/api/dec/task/{it['id']}/update", json={"status": "jarayonda"}).status_code == 403, "Begona bo'lim holatni o'zgartira olmaydi")
ok(buxg.get(f"/api/dec/{d['id']}").status_code == 403, "Begona bo'lim qarorni ko'rmaydi")
ok(rektor.post(f"/api/tasks/{it['id']}/status", json={"status": "bajarildi"}).status_code == 403, "Eski API orqali ham chetlab o'tib bo'lmaydi")
# chat
ok(reg.post(f"/api/dec/task/{rg['id']}/msg", json={"text": "Natija chiqishi bilan yozib qo'ying, xabarni tayyorlab turaman."}).json()["ok"], "Registrator chatga yozdi")
ok(itstaff.post(f"/api/dec/task/{it['id']}/msg", json={"text": "Tekshiryapman, 14:30 gacha aytaman."}).json()["ok"], "IT muhandisi chatga yozdi")
ok(buxg.post(f"/api/dec/task/{it['id']}/msg", json={"text": "x"}).status_code == 403, "Begona chatga yoza olmaydi")
ok(rektor.post(f"/api/dec/task/{it['id']}/msg", json={"text": "x"}).status_code == 403, "Rektor chatni faqat o'qiydi")
ok(itstaff.post(f"/api/dec/task/{it['id']}/update", json={"status": "jarayonda"}).json()["ok"], "IT: ish boshlandi")
R = "Sabab: kirish serveridagi SSL sertifikat muddati tugagan. Sertifikat yangilandi, 13:40 dan LMS'ga kirish tiklandi. 20 ta test akkaunt bilan tekshirildi."
ok(itstaff.post(f"/api/dec/task/{it['id']}/update", json={"status": "bajarildi", "result": R}).json()["ok"], "IT natijani kiritdi va yakunladi")
rv = reg.get(f"/api/dec/{d['id']}").json(); rgt = [t for t in rv["tasks"] if t["id"] == rg["id"]][0]
ok(rgt["dep"]["result"] == R and not rgt["blocked"], "Registrator IT natijasini ko'radi, bloк ochildi")
ok(len(rv["msgs"]) == 2, "Registrator bog'langan chatni ko'radi (2 xabar)")
N = "Hurmatli talabalar! LMS platformasiga kirishdagi uzilish bartaraf etildi: kirish 13:40 dan tiklandi. Oraliq nazorat topshiriqlarini odatdagidek yuklashingiz mumkin."
ok(reg.post(f"/api/dec/task/{rg['id']}/update", json={"status": "bajarildi", "result": N, "notify_incident": True}).json()["ok"], "Registrator yakunladi va hodisa bo'yicha xabar yubordi")
# rektor
lst = rektor.get("/api/dec/list").json()["decisions"]; dd = [x for x in lst if x["id"] == d["id"]][0]
ok(all(t["status"] == "bajarildi" for t in dd["tasks"]) and dd["tasks"][0]["result"] == R, "Rektor ro'yxatida holat va natija aynan tasks jadvalidan")
full = rektor.get(f"/api/dec/{d['id']}").json()
ok(full["tasks"][0]["assignee_name"].startswith("Nazarov") and full["incident"]["notified_at"], f"Rektor: mas'ul {full['tasks'][0]['assignee_name']}, hodisa xabari yuborilgan")
ok(len(full["log"]) >= 6, f"Tarix: {len(full['log'])} yozuv")
dash = rektor.get("/api/dashboard").json()
ok(not any("LMS" in a["text"] and "xabar berilmagan" in a["text"] for a in dash["alerts"]), "Rektor ogohlantirishidan 'talabalarga xabar berilmagan' yo'qoldi")
print("\nHAMMASI O'TDI")
