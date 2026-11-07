"""Hikvision ISAPI ulagichi (kamera yoki NVR) — FAQAT metama'lumot: odamlar soni va voqea turlari.

Tamoyillar:
  * Video, kadr va yuz tasvirlari olinmaydi. Voqealar oqimida keladigan rasm qismlari o'qiladi-yu, saqlanmasdan tashlab yuboriladi.
  * HTTP Digest (ISAPI standarti), ixtiyoriy HTTPS. Cheklangan ("Operator"/faqat o'qish) foydalanuvchi bilan ishlaydi.
  * Imkoniyatlar har bir model uchun alohida aniqlanadi (probe): qo'llamagan funksiya "yo'q" deb belgilanadi, xato bermaydi.
  * Tarmoq va avtorizatsiya xatolari tushunarli o'zbekcha xabarga o'giriladi (IsapiError).

Endpointlar (Hikvision ISAPI):
  GET  /ISAPI/System/deviceInfo                                   — model, proshivka, seriya
  GET  /ISAPI/System/time                                         — qurilma soati (NTP tekshiruvi uchun)
  GET  /ISAPI/System/Video/inputs/channels/{ch}/counting/capabilities — odam sanash qo'llanadimi
  POST /ISAPI/System/Video/inputs/channels/{ch}/counting/search   — kunlik kirdi/chiqdi statistikasi
  GET  /ISAPI/Event/triggers                                      — voqealar tizimi mavjudligi
  GET  /ISAPI/Event/notification/alertStream                      — uzluksiz voqealar oqimi (multipart, XML qismlar)
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
# Hikvision eventType → JARVIS turi. None — saqlanmaydi (shovqin).
EVENT_KIND = {
    "linedetection": "chiziq_kesish", "fielddetection": "hududga_kirish", "regionentrance": "hududga_kirish",
    "regionexiting": "hududdan_chiqish", "peoplecounting": "odam_soni", "regionpeoplecounting": "odam_soni",
    "videoloss": "video_yoqoldi", "shelteralarm": "kamera_yopildi", "tamperdetection": "kamera_yopildi",
    "scenechangedetection": "kamera_siljidi", "defocus": "kamera_siljidi", "vmd": None,
}
KIND_LABEL = {"chiziq_kesish": "Chiziq kesildi", "hududga_kirish": "Hududga kirish", "hududdan_chiqish": "Hududdan chiqish",
              "odam_soni": "Odamlar soni", "video_yoqoldi": "Tasvir yo'qoldi", "kamera_yopildi": "Kamera yopildi / buzildi",
              "kamera_siljidi": "Kamera siljidi / fokus", "olomon": "Olomon zichligi"}

def normalize(ev: dict) -> dict | None:
    """Xom voqea → normallashtirilgan. Yurak urishi (videoloss inactive) va shovqin (VMD) — None."""
    raw = (ev.get("type") or "").strip()
    low = raw.lower()
    state = (ev.get("state") or "").lower()
    if low == "videoloss" and state != "active":
        return None                         # Hikvision oqimi har ~10 s shunday "yurak urishi" yuboradi
    kind = EVENT_KIND.get(low, "olomon" if "density" in low or "crowd" in low else f"boshqa:{low}" if low else None)
    if kind is None: return None
    return {"kind": kind, "raw_type": raw, "state": state or "active", "channel": ev.get("channel"),
            "dev_ts": ev.get("ts"), "count": ev.get("count"), "desc": ev.get("desc")}

def parse_alert(xml_text: str) -> dict | None:
    try:
        m = xml_map(xml_text)
    except ET.ParseError:
        return None
    if "eventType" not in m: return None
    ch = m.get("channelID") or m.get("dynChannelID") or m.get("videoInputChannelID")
    cnt = next((int(m[k]) for k in ("peopleNum", "personCount", "regionPeopleNum", "currentPeopleNum") if m.get(k, "").isdigit()), None)
    return {"type": m.get("eventType"), "state": m.get("eventState"), "channel": int(ch) if (ch or "").isdigit() else None,
            "ts": m.get("dateTime"), "desc": m.get("eventDescription"), "count": cnt}

class AlertStreamParser:
    """alertStream baytlaridan XML voqealarni ajratadi. Multipart chegaralariga tayanmaydi (modellar orasida farq qiladi):
    <EventNotificationAlert ...>...</EventNotificationAlert> bloklarini qidiradi; orasidagi hamma narsa (JPEG va h.k.) tashlanadi."""
    START, END = b"<EventNotificationAlert", b"</EventNotificationAlert>"
    MAX_BUF = 2_000_000

    def __init__(self):
        self.buf = b""
        self.dropped_bytes = 0

    def feed(self, chunk: bytes) -> list:
        self.buf += chunk
        out = []
        while True:
            s = self.buf.find(self.START)
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

def warnings(caps: dict) -> list:
    w = []
    sk = caps.get("clock_skew_s")
    if sk is not None and abs(sk) > 120:
        w.append(f"Qurilma soati serverdan {abs(sk) // 60} daqiqa {'oldinda' if sk > 0 else 'orqada'} — NTP sozlansin (sanash hisobotlari siljiydi)")
    if caps.get("counting") is False and not caps.get("region_counting"):
        w.append("Odam sanash funksiyasi yo'q yoki yoqilmagan — bandlik o'lchanmaydi")
    if caps.get("events") is False:
        w.append("Voqealar tizimi mavjud emas — faqat davriy so'rov ishlaydi")
    d = re.sub(r"\D", "", (caps.get("device") or {}).get("firmware_date", ""))   # "build 210628" yoki "20210628"
    ym = (2000 + int(d[:2]), int(d[2:4])) if len(d) == 6 else (int(d[:4]), int(d[4:6])) if len(d) == 8 else None
    if ym and ym < (2021, 9):
        w.append("Proshivka 2021-sentabrdan eski — CVE-2021-36260 zaifligi bo'lishi mumkin, yangilansin")
    return w
