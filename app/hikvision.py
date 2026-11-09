"""Hikvision ISAPI ulagichi (kamera yoki NVR) — FAQAT metama'lumot: odamlar soni va voqea turlari.

Tamoyillar:
  * Video, kadr va yuz tasvirlari olinmaydi. Voqealar oqimida keladigan rasm qismlari o'qiladi-yu, saqlanmasdan tashlab yuboriladi.
    Istisno — Kirish nazorati (Face ID, app/facecam.py, bayroq ISFT_CORE_FEATURE_FACE): yuz voqeasining fon rasmi kameradan
    alohida so'raladi va ko'pi bilan ISFT_CORE_FACE_KEEP_DAYS kun saqlanadi; yuzni solishtirishni kameraning o'zi bajaradi.
  * HTTP Digest (ISAPI standarti), ixtiyoriy HTTPS. Cheklangan ("Operator"/faqat o'qish) foydalanuvchi bilan ishlaydi.
  * Imkoniyatlar har bir model uchun alohida aniqlanadi (probe): qo'llamagan funksiya "yo'q" deb belgilanadi, xato bermaydi.
  * Tarmoq va avtorizatsiya xatolari tushunarli o'zbekcha xabarga o'giriladi (IsapiError).

Endpointlar (Hikvision ISAPI):
  GET  /ISAPI/System/deviceInfo                                   — model, proshivka, seriya
  GET  /ISAPI/System/time                                         — qurilma soati (NTP tekshiruvi uchun)
  GET  /ISAPI/System/Video/inputs/channels/{ch}/counting/capabilities — odam sanash qo'llanadimi
  POST /ISAPI/System/Video/inputs/channels/{ch}/counting/search   — kunlik kirdi/chiqdi statistikasi
  GET  /ISAPI/Event/triggers                                      — voqealar tizimi mavjudligi
  GET  /ISAPI/Event/notification/alertStream                      — uzluksiz voqealar oqimi (multipart, XML va JSON qismlar)
  GET/POST /ISAPI/Intelligent/FDLib?format=json                   — yuz kutubxonasi (faqat FEATURE_FACE=1, rozilik bergan shaxslar)
  POST /ISAPI/Intelligent/FDLib/FaceDataRecord?format=json        — kutubxonaga yozuv (FPID + yuz rasmi)
  PUT  /ISAPI/Intelligent/FDLib/FDSearch/Delete?format=json       — rozilik qaytarib olinganda yozuvni o'chirish
Testlash: tools/fake_hikvision.py emulyatori va tests/test_hikvision.py.
"""
import datetime as dt, re, xml.etree.ElementTree as ET
from collections import defaultdict
import httpx

class IsapiError(Exception):
    pass

class NotSupported(IsapiError):
    pass

def _tag(el): return el.tag.split("}")[-1]

def xml_map(text: str) -> dict:
    """XML'dan {teg: matn} (namespace'siz, oxirgi qiymat). Hikvision javoblari tekis tuzilgan."""
    root = ET.fromstring(text)
    return {_tag(el): (el.text or "").strip() for el in root.iter()}

def xml_ints(text: str, *names) -> dict:
    root = ET.fromstring(text)
    out = defaultdict(list)
    for el in root.iter():
        t = _tag(el)
        if t in names and el.text and el.text.strip().lstrip("-").isdigit():
            out[t].append(int(el.text.strip()))
    return out

# ---------------------------------------------------------------------------------------------
# Voqealar: normallashtirish
# ---------------------------------------------------------------------------------------------
# Hikvision eventType (kichik harfda) → ISFT Core turi. None — saqlanmaydi (shovqin).
# Ustuvorlik va kimga borishi — app/camsec.py POLICY. Teg nomlari ISAPI hujjatlariga yaqin; haqiqiy proshivkada qayta tekshiriladi.
EVENT_KIND = {
    "linedetection": "chiziq_kesish", "fielddetection": "hududga_kirish", "regionentrance": "hududga_kirish",
    "regionexiting": "hududdan_chiqish", "loitering": "uzoq_turish", "peoplegathering": "toplanish", "running": "yugurish",
    "unattendedbaggage": "qarovsiz_buyum", "attendedbaggage": "buyum_olindi", "objectremoval": "buyum_olindi",
    "peoplecounting": "odam_soni", "regionpeoplecounting": "odam_soni",
    "videoloss": "video_yoqoldi", "shelteralarm": "kamera_yopildi", "tamperdetection": "kamera_yopildi",
    "scenechangedetection": "kamera_siljidi", "defocus": "kamera_siljidi",
    "firedetection": "yongin", "smokedetection": "tutun", "smokeandfiredetection": "yongin",
    "tma": "harorat", "tmpa": "harorat", "temperature": "harorat", "temperaturealarm": "harorat", "thermometry": "harorat",
    "personqueuedetection": "navbat", "queuemanagement": "navbat", "personqueuecounting": "navbat", "personqueuetime": "navbat",
    "vmd": "harakat",
}
# Biometrik / avtoraqam voqealari — bayroq ortida (standart holatda O'CHIQ, ZRU-547: alohida yozma rozilik kerak)
FACE_TYPES = {"facesnap", "facecapture", "facedetection", "facematch", "facesnapmatch", "facecontrast", "alarmresult", "accesscontrollerevent"}
ANPR_TYPES = {"anpr", "vehicledetection", "licenseplate"}
KIND_LABEL = {"chiziq_kesish": "Chiziq kesildi", "hududga_kirish": "Taqiqlangan hududga kirish", "hududdan_chiqish": "Hududdan chiqish",
              "uzoq_turish": "Uzoq turib qolish", "toplanish": "Odamlar to'planishi", "yugurish": "Yugurish",
              "qarovsiz_buyum": "Qarovsiz buyum", "buyum_olindi": "Buyum olib ketildi",
              "odam_soni": "Odamlar soni", "video_yoqoldi": "Tasvir yo'qoldi", "kamera_yopildi": "Kamera to'sib qo'yildi / buzildi",
              "kamera_siljidi": "Kamera siljidi / fokus buzildi", "olomon": "Olomon zichligi", "yongin": "Yong'in aniqlandi",
              "tutun": "Tutun aniqlandi", "harorat": "Harorat chegaradan oshdi", "navbat": "Navbat chegaradan oshdi",
              "harakat": "Harakat (qo'riqlanadigan hudud)", "sigim_oshdi": "Xona sig'imdan oshdi (110%+)",
              "xodim_keldi": "Xodim keldi (rozilik bergan)", "avtoraqam": "Xodim avtomobili"}

def normalize(ev: dict, keep_vmd: bool = False, face: bool = False, anpr: bool = False) -> dict | None:
    """Xom voqea → normallashtirilgan. Yurak urishi (videoloss inactive) va shovqin — None.
    VMD (oddiy harakat) faqat qo'riqlanadigan hududda (keep_vmd) saqlanadi. Yuz va avtoraqam — faqat bayroq yoqilganda."""
    raw = (ev.get("type") or "").strip()
    low = raw.lower()
    state = (ev.get("state") or "").lower()
    if low == "videoloss" and state != "active":
        return None                         # Hikvision oqimi har ~10 s shunday "yurak urishi" yuboradi
    if low in FACE_TYPES:
        if not face: return None            # FEATURE_FACE=0 — biometrik voqea umuman qayta ishlanmaydi
        # kirish terminali (xodim raqami) — eski "xodim_keldi"; yuzni solishtirish (FPID, o'xshashlik, ramka) — "yuz" (app/facecam.py)
        kind = "xodim_keldi" if low == "accesscontrollerevent" else "yuz"
    elif low in ANPR_TYPES:
        if not anpr: return None
        kind = "avtoraqam"
    else:
        kind = EVENT_KIND.get(low, "olomon" if "density" in low or "crowd" in low else f"boshqa:{low}" if low else None)
    if kind == "harakat" and not keep_vmd: return None
    if kind is None: return None
    out = {"kind": kind, "raw_type": raw, "state": state or "active", "channel": ev.get("channel"),
           "dev_ts": ev.get("ts"), "count": ev.get("count"), "desc": ev.get("desc"), "value": ev.get("value"),
           "wait_s": ev.get("wait_s"), "subject": ev.get("subject") if face or anpr else None}
    if kind == "yuz":                       # FPID (kutubxonadagi shaxs kodi — ism emas), o'xshashlik 0..1, yuz ramkasi 0..1, fon rasmi manzili
        out.update({k: ev.get(k) for k in ("fpid", "similarity", "rect", "bkg_url", "picture", "group")})
    return out

def _num(m, *keys):
    for k in keys:
        v = (m.get(k) or "").strip()
        try: return float(v)
        except ValueError: pass
    return None

def parse_alert(xml_text: str) -> dict | None:
    try:
        m = xml_map(xml_text)
    except ET.ParseError:
        return None
    if "eventType" not in m: return None
    ch = m.get("channelID") or m.get("dynChannelID") or m.get("videoInputChannelID")
    cnt = next((int(m[k]) for k in ("peopleNum", "personCount", "regionPeopleNum", "currentPeopleNum", "queueLength", "personQueueNum",
                                    "queuePeopleNum") if m.get(k, "").isdigit()), None)
    wait = _num(m, "waitingTime", "waitTime", "averageWaitingTime")
    temp = _num(m, "maxTemperature", "currentTemperature", "temperature")
    # yuz/avtoraqam: rasm EMAS — faqat xodim raqami / avtoraqam matni (bayroq yoqilganda, ro'yxat bilan solishtiriladi)
    subj = m.get("employeeNoString") or m.get("licensePlate") or None
    out = {"type": m.get("eventType"), "state": m.get("eventState"), "channel": int(ch) if (ch or "").isdigit() else None,
           "ts": m.get("dateTime"), "desc": m.get("eventDescription"), "count": cnt, "wait_s": wait, "value": temp, "subject": subj}
    if (m.get("eventType") or "").lower() in FACE_TYPES:    # XML ko'rinishidagi yuz voqeasi (eski proshivkalar)
        out.update(fpid=m.get("FPID") or m.get("PID") or None, similarity=_sim(_num(m, "similarity", "maxsimilarity")),
                   rect=_rect({k: _num(m, k) for k in ("x", "y", "width", "height")}), bkg_url=m.get("bkgUrl") or m.get("backgroundImageURL") or None)
    return out

def _sim(v):
    """O'xshashlik: 0..1 yoki 0..100 → 0..1."""
    if v is None: return None
    return round(v / 100 if v > 1 else v, 4)

def _rect(r: dict):
    """faceRect {x, y, width, height}: 0..1 (JSON) yoki 0..1000 (ba'zi XML) → [x, y, w, h] 0..1."""
    try:
        v = [float(r.get(k)) for k in ("x", "y", "width", "height")]
    except (TypeError, ValueError):
        return None
    if max(v) > 1.0: v = [x / 1000 for x in v]
    return [round(min(1, max(0, x)), 4) for x in v]

def parse_json_alert(text: str) -> list:
    """JSON voqea (DeepinView `alarmResult` — yuzni kutubxona bilan solishtirish). Har bir yuz — alohida voqea, bitta `group` bilan.
    Maydonlar Hikvision ISAPI hujjatlariga taxminan yaqin; haqiqiy proshivkada qayta tekshiriladi (docs/hikvision.md, 13-bo'lim)."""
    import json
    try:
        o = json.loads(text)
    except ValueError:
        return []
    if not isinstance(o, dict) or "eventType" not in o: return []
    base = {"type": o.get("eventType"), "state": o.get("eventState"), "channel": o.get("channelID") if isinstance(o.get("channelID"), int) else None,
            "ts": o.get("dateTime"), "desc": o.get("eventDescription"), "count": None, "wait_s": None, "value": None, "subject": None}
    out = []
    for gi, res in enumerate(o.get("alarmResult") or o.get("faceCapture") or []):
        attrs = res.get("targetAttrs") or {}
        for f in res.get("faces") or []:
            best = None
            for idf in f.get("identify") or []:
                for c in idf.get("candidate") or []:
                    rf = c.get("reserve_field") or {}
                    s = _sim(c.get("similarity") if c.get("similarity") is not None else idf.get("maxsimilarity"))
                    if rf.get("FPID") and (best is None or (s or 0) > (best[1] or 0)): best = (rf["FPID"], s)
            out.append({**base, "fpid": best[0] if best else None, "similarity": best[1] if best else None,
                        "rect": _rect(f.get("faceRect") or {}), "bkg_url": attrs.get("bkgUrl"), "group": f"{o.get('dateTime')}#{gi}"})
    if not out and (o.get("eventType") or "").lower() not in FACE_TYPES:
        out.append(base)
    return out

class AlertStreamParser:
    """alertStream baytlaridan XML voqealarni ajratadi. Multipart chegaralariga tayanmaydi (modellar orasida farq qiladi):
    <EventNotificationAlert ...>...</EventNotificationAlert> bloklarini qidiradi; orasidagi hamma narsa (JPEG va h.k.) tashlanadi."""
    START, END = b"<EventNotificationAlert", b"</EventNotificationAlert>"
    JSON_HDR = b"application/json"      # DeepinView yuz voqealari (alarmResult) JSON qism sifatida keladi
    MAX_BUF = 2_000_000

    def __init__(self):
        self.buf = b""
        self.dropped_bytes = 0

    @staticmethod
    def _json_end(buf: bytes, b: int) -> int:
        """buf[b] == '{' — mos yopuvchi '}' dan keyingi indeks (satrlar ichidagi qavslar hisobga olinmaydi); to'liq kelmagan bo'lsa -1."""
        depth, ins, esc = 0, False, False
        for i in range(b, len(buf)):
            ch = buf[i]
            if ins:
                if esc: esc = False
                elif ch == 0x5C: esc = True
                elif ch == 0x22: ins = False
                continue
            if ch == 0x22: ins = True
            elif ch == 0x7B: depth += 1
            elif ch == 0x7D:
                depth -= 1
                if depth == 0: return i + 1
        return -1

    def feed(self, chunk: bytes) -> list:
        self.buf += chunk
        out = []
        while True:
            s = self.buf.find(self.START)
            j = self.buf.find(self.JSON_HDR)
            if j >= 0 and (s < 0 or j < s):        # JSON qism: Content-Type sarlavhasidan keyingi birinchi { ... }
                b = self.buf.find(b"{", j)
                e = self._json_end(self.buf, b) if b >= 0 else -1
                if e < 0:
                    if j: self.dropped_bytes += j; self.buf = self.buf[j:]
                    if len(self.buf) > self.MAX_BUF: self.dropped_bytes += len(self.buf); self.buf = b""
                    break
                self.dropped_bytes += b
                part = self.buf[b:e]
                self.buf = self.buf[e:]
                out += parse_json_alert(part.decode("utf-8", "replace"))
                continue
            if s < 0:
                keep = len(self.START) - 1          # boshlanish tegi bo'linib kelishi mumkin
                self.dropped_bytes += max(0, len(self.buf) - keep)
                self.buf = self.buf[-keep:]
                break
            e = self.buf.find(self.END, s)
            if e < 0:
                if s: self.dropped_bytes += s; self.buf = self.buf[s:]
                if len(self.buf) > self.MAX_BUF:     # buzilgan oqim — xotira to'lmasin
                    self.dropped_bytes += len(self.buf); self.buf = b""
                break
            self.dropped_bytes += s
            part = self.buf[s:e + len(self.END)]
            self.buf = self.buf[e + len(self.END):]
            ev = parse_alert(part.decode("utf-8", "replace"))
            if ev: out.append(ev)
        return out

# ---------------------------------------------------------------------------------------------
# Mijoz
# ---------------------------------------------------------------------------------------------
class HikClient:
    def __init__(self, host: str, username: str, password: str, *, scheme: str = "http", port: int | None = None,
                 verify: bool = False, timeout: float = 8.0, transport=None):
        if scheme not in ("http", "https"): raise ValueError("scheme")
        self.base = f"{scheme}://{host}" + (f":{int(port)}" if port else "")
        self.auth = httpx.DigestAuth(username or "", password or "")
        # verify=False: kameralar odatda o'z-o'zidan imzolangan sertifikat bilan keladi; ichki VLAN'da ishlaydi.
        self.kw = dict(base_url=self.base, auth=self.auth, timeout=timeout, verify=verify)
        if transport is not None: self.kw["transport"] = transport

    def _client(self, **extra):
        return httpx.AsyncClient(**{**self.kw, **extra})

    @staticmethod
    def _check(r: httpx.Response, what: str):
        if r.status_code == 401: raise IsapiError("Login yoki parol noto'g'ri (ketma-ket xatolarda kamera IP'ni vaqtincha bloklaydi)")
        if r.status_code == 403: raise IsapiError(f"{what}: foydalanuvchida ruxsat yo'q yoki funksiya o'chirilgan")
        if r.status_code == 404: raise NotSupported(f"{what}: bu model qo'llamaydi")
        if r.status_code >= 400: raise IsapiError(f"{what}: qurilma {r.status_code} qaytardi")

    async def _req(self, method, path, what, **kw) -> httpx.Response:
        try:
            async with self._client() as c:
                r = await c.request(method, path, **kw)
        except httpx.ConnectError: raise IsapiError("Ulanib bo'lmadi: IP manzil, tarmoq yoki firewall'ni tekshiring")
        except httpx.TimeoutException: raise IsapiError("Ulanib bo'lmadi: qurilma javob bermadi (timeout) — IP manzil, tarmoq yoki firewall'ni tekshiring")
        except httpx.HTTPError as e: raise IsapiError(f"Tarmoq xatosi: {e.__class__.__name__}")
        self._check(r, what)
        return r

    async def device_info(self) -> dict:
        m = xml_map((await self._req("GET", "/ISAPI/System/deviceInfo", "Qurilma ma'lumoti")).text)
        return {"model": m.get("model", ""), "firmware": m.get("firmwareVersion", ""), "firmware_date": m.get("firmwareReleasedDate", ""),
                "name": m.get("deviceName", ""), "serial": m.get("serialNumber", ""), "type": m.get("deviceType", "")}

    async def device_time(self) -> dt.datetime | None:
        m = xml_map((await self._req("GET", "/ISAPI/System/time", "Qurilma vaqti")).text)
        lt = m.get("localTime")
        if not lt: return None
        try: return dt.datetime.fromisoformat(lt.replace("Z", "+00:00"))
        except ValueError: return None

    async def supports(self, path: str, what: str) -> bool | None:
        """True/False — aniq; None — tekshirib bo'lmadi (masalan, ruxsat yo'q)."""
        try:
            await self._req("GET", path, what); return True
        except NotSupported:
            return False
        except IsapiError as e:
            if "ruxsat" in str(e): return None
            raise

    async def probe(self, channel: int = 1, occ_path: str = "") -> dict:
        info = await self.device_info()
        skew = None
        try:
            t = await self.device_time()
            if t:
                now = dt.datetime.now(t.tzinfo) if t.tzinfo else dt.datetime.now()
                skew = int((t - now).total_seconds())
        except NotSupported:
            pass
        caps = {"device": info, "clock_skew_s": skew,
                "counting": await self.supports(f"/ISAPI/System/Video/inputs/channels/{channel}/counting/capabilities", "Odam sanash"),
                "region_counting": (await self.supports(occ_path.format(ch=channel), "Hudud bo'yicha sanash")) if occ_path else None,
                "events": await self.supports("/ISAPI/Event/triggers", "Voqealar"),
                "checked_at": dt.datetime.now().isoformat(timespec="seconds")}
        caps["warnings"] = warnings(caps)
        return caps

    async def count(self, channel: int = 1, occ_path: str = "") -> int:
        """Xonadagi odamlar soni: hudud bo'yicha sanash (bo'lsa) yoki bugungi kirdi − chiqdi."""
        if occ_path:
            v = xml_ints((await self._req("GET", occ_path.format(ch=channel), "Hudud bo'yicha sanash")).text,
                         "personCount", "regionPeopleNum", "peopleNum", "currentPeopleNum")
            for k in ("personCount", "regionPeopleNum", "currentPeopleNum", "peopleNum"):
                if v.get(k): return max(0, v[k][-1])
            raise IsapiError("Javobda odamlar soni topilmadi")
        today = dt.date.today().isoformat()
        body = ('<?xml version="1.0" encoding="UTF-8"?><CountingStatisticsDescription version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
                f'<reportType>daily</reportType><timeSpanList><timeSpan><startTime>{today}T00:00:00</startTime>'
                f'<endTime>{today}T23:59:59</endTime></timeSpan></timeSpanList></CountingStatisticsDescription>')
        try:
            r = await self._req("POST", f"/ISAPI/System/Video/inputs/channels/{channel}/counting/search", "Odam sanash",
                                content=body, headers={"Content-Type": "application/xml"})
        except NotSupported:
            raise IsapiError("Kamerada odam sanash (People Counting) funksiyasi yo'q yoki yoqilmagan")
        v = xml_ints(r.text, "enterCount", "exitCount")
        if not v.get("enterCount"): raise IsapiError("Kamera kirish/chiqish statistikasini qaytarmadi")
        return max(0, sum(v["enterCount"]) - sum(v.get("exitCount", [0])))

    async def queue_status(self, channel: int = 1, path: str = "/ISAPI/Intelligent/channels/{ch}/queueManagement/status") -> dict:
        """Navbat uzunligi va kutish vaqti (DeepinView/AcuSense navbat boshqaruvi). Yo'l modelga bog'liq — ISFT_CORE_CAM_QUEUE_PATH."""
        try:
            r = await self._req("GET", path.format(ch=channel), "Navbat holati")
        except NotSupported:
            raise IsapiError("Kamerada navbat boshqaruvi (Queue Management) yo'q yoki yoqilmagan")
        m = xml_map(r.text)
        n = _num(m, "queueLength", "personQueueNum", "queuePeopleNum")
        if n is None: raise IsapiError("Javobda navbat uzunligi topilmadi")
        w = _num(m, "waitingTime", "waitTime", "averageWaitingTime")
        return {"length": int(n), "wait_s": int(w) if w is not None else None}

    async def alert_stream(self, stats: dict | None = None):
        """Uzluksiz voqealar oqimi. Har bir XML voqeani (xom) qaytaradi; rasm qismlari tashlanadi.
        Ulanish uzilsa — generator tugaydi (qayta ulanish chaqiruvchida, backoff bilan)."""
        p = AlertStreamParser()
        try:
            async with self._client(timeout=httpx.Timeout(10.0, read=90.0)) as c:
                async with c.stream("GET", "/ISAPI/Event/notification/alertStream") as r:
                    self._check(r, "Voqealar oqimi")
                    async for chunk in r.aiter_bytes():
                        for ev in p.feed(chunk):
                            yield ev
                        if stats is not None: stats["dropped_bytes"] = p.dropped_bytes
        except httpx.ConnectError: raise IsapiError("Voqealar oqimi: ulanib bo'lmadi")
        except httpx.TimeoutException: raise IsapiError("Voqealar oqimi: 90 s davomida ma'lumot kelmadi")
        except httpx.HTTPError as e: raise IsapiError(f"Voqealar oqimi uzildi: {e.__class__.__name__}")

    # ---------------- Yuz kutubxonasi (FDLib) — faqat yozma rozilik bergan shaxslar; kameraga ism emas, faqat FPID yuboriladi ----------------
    FDLIB = "/ISAPI/Intelligent/FDLib"

    async def fdlib_ensure(self, name: str = "ISFT_Kirish") -> str:
        """Yuz kutubxonasi (FDLib) bor bo'lsa — FDID, yo'q bo'lsa yaratadi. Kamera "face picture library"ni qo'llamasa — NotSupported."""
        r = await self._req("GET", f"{self.FDLIB}?format=json", "Yuz kutubxonasi")
        try: libs = r.json().get("FDLib") or []
        except ValueError: libs = []
        for lib in libs:
            if lib.get("name") == name: return str(lib.get("FDID"))
        r = await self._req("POST", f"{self.FDLIB}?format=json", "Yuz kutubxonasini yaratish",
                            json={"faceLibType": "blackFD", "name": name, "customInfo": "ISFT Core: faqat yozma roziligi bor shaxslar"})
        try: return str(r.json().get("FDID"))
        except ValueError: raise IsapiError("Yuz kutubxonasi yaratildi, lekin FDID qaytmadi")

    async def fdlib_add(self, fdid: str, fpid: str, jpeg: bytes) -> bool:
        """Yozuv qo'shish: POST /ISAPI/Intelligent/FDLib/FaceDataRecord?format=json (multipart: FaceDataRecord JSON + img).
        name maydoniga FPID yoziladi — kamerada ism saqlanmaydi (shaxs FPID orqali faqat ISFT Core bazasida aniqlanadi)."""
        import json as _json
        rec = {"faceLibType": "blackFD", "FDID": str(fdid), "FPID": fpid, "name": fpid}
        await self._req("POST", f"{self.FDLIB}/FaceDataRecord?format=json", "Yuz yozuvini qo'shish",
                        files={"FaceDataRecord": (None, _json.dumps(rec), "application/json"), "img": ("face.jpg", jpeg, "image/jpeg")})
        return True

    async def fdlib_delete(self, fdid: str, fpids: list) -> bool:
        """Rozilik qaytarib olinganda: PUT /ISAPI/Intelligent/FDLib/FDSearch/Delete?format=json&FDID=..&faceLibType=blackFD."""
        await self._req("PUT", f"{self.FDLIB}/FDSearch/Delete?format=json&FDID={fdid}&faceLibType=blackFD", "Yuz yozuvini o'chirish",
                        json={"FPID": [{"value": x} for x in fpids]})
        return True

    async def fetch_picture(self, url: str, max_bytes: int = 3_000_000) -> bytes | None:
        """Voqeadagi fon rasmi (bkgUrl). Faqat shu kameraning o'z manzilidan (SSRF'dan himoya) — yo'l qismi olinadi."""
        from urllib.parse import urlsplit
        u = urlsplit(url or "")
        if not u.path.startswith("/"): return None
        try:
            r = await self._req("GET", u.path + (f"?{u.query}" if u.query else ""), "Voqea rasmi")
        except NotSupported:
            return None
        b = r.content
        return b if b[:2] == b"\xff\xd8" and len(b) <= max_bytes else None

SKEW_WARN_S = 60

def _dur(s: int) -> str:
    return f"{s} soniya" if s < 120 else f"{s // 60} daqiqa"

def fw_too_old(fw_date: str) -> bool:
    d = re.sub(r"\D", "", fw_date or "")   # "build 210628" yoki "20210628"
    ym = (2000 + int(d[:2]), int(d[2:4])) if len(d) == 6 else (int(d[:4]), int(d[4:6])) if len(d) == 8 else None
    return bool(ym and ym < (2021, 9))

def warnings(caps: dict) -> list:
    w = []
    sk = caps.get("clock_skew_s")
    if sk is not None and abs(sk) > SKEW_WARN_S:
        w.append(f"Qurilma soati serverdan {_dur(abs(sk))} {'oldinda' if sk > 0 else 'orqada'} — NTP sozlansin (voqealar server vaqti bilan yoziladi, "
                 "lekin kamera hisobotlari siljiydi)")
    if caps.get("counting") is False and not caps.get("region_counting"):
        w.append("Odam sanash funksiyasi yo'q yoki yoqilmagan — bandlik o'lchanmaydi")
    if caps.get("events") is False:
        w.append("Voqealar tizimi mavjud emas — faqat davriy so'rov ishlaydi")
    if fw_too_old((caps.get("device") or {}).get("firmware_date", "")):
        w.append("Proshivka 2021-sentabrdan eski — CVE-2021-36260 zaifligi bo'lishi mumkin, yangilansin")
    return w
