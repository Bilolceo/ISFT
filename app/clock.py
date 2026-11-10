"""Institut vaqti — yagona manba. Server qaysi zonada ishlashidan qat'i nazar (Railway — UTC) sanalar Toshkent bo'yicha.

  tz()      — ISFT_CORE_TZ (standart: Asia/Tashkent); tzdata topilmasa — doimiy UTC+5 (Toshkentda yozgi vaqt yo'q)
  now()     — mahalliy vaqt, tzinfo'siz (bazadagi vaqt belgilari shu ko'rinishda: ISO, zona ofsetisiz)
  today()   — mahalliy sana; HAR CHAQIRUVDA hisoblanadi (yarim tundan keyin yangi kun avtomatik)
  now_iso() — now() soniyagacha ISO matn

ISFT_CORE_FAKE_TODAY=YYYY-MM-DD — demo/test uchun "bugun"ni qotirish: sana shu kun, soat-daqiqa haqiqiy (mahalliy) vaqt.
Seed ham shu sanaga moslashadi (app/dateshift.py), shuning uchun server, seed va testlar bir xil qiymat bilan ishga tushirilishi kerak.
"""
import datetime as dt, logging, os

log = logging.getLogger("isft.clock")
UTC5 = dt.timezone(dt.timedelta(hours=5), "UZT")


def _load_tz():
    name = os.getenv("ISFT_CORE_TZ") or "Asia/Tashkent"
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:   # ZoneInfoNotFoundError (tzdata yo'q), ValueError (noto'g'ri nom)
        log.warning("vaqt zonasi topilmadi (%s) — UTC+5 (Toshkent) ishlatiladi", name)
        return UTC5


TZ = _load_tz()
_FAKE = {"raw": None, "date": None}


def tz():
    return TZ


def fake_today():
    """ISFT_CORE_FAKE_TODAY bo'yicha sana (yo'q yoki noto'g'ri bo'lsa None). Muhit o'zgaruvchisi har safar o'qiladi."""
    raw = (os.getenv("ISFT_CORE_FAKE_TODAY") or "").strip()
    if raw != _FAKE["raw"]:
        try:
            d = dt.date.fromisoformat(raw) if raw else None
        except ValueError:
            log.warning("ISFT_CORE_FAKE_TODAY noto'g'ri (%r) — e'tiborsiz qoldirildi", raw); d = None
        _FAKE.update(raw=raw, date=d)
    return _FAKE["date"]


def now() -> dt.datetime:
    t = dt.datetime.now(TZ).replace(tzinfo=None)
    f = fake_today()
    return dt.datetime.combine(f, t.time()) if f else t


def today() -> dt.date:
    return now().date()


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat(timespec="seconds")


def from_ts(ts: float) -> dt.datetime:
    """Unix vaqt (time.time()) → mahalliy (Toshkent) vaqt, tzinfo'siz. Haqiqiy vaqt: FAKE_TODAY ta'sir qilmaydi."""
    return dt.datetime.fromtimestamp(ts, TZ).replace(tzinfo=None)
