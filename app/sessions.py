"""Server tomonidagi sessiyalar va urinishlar cheklovi.

Cookie'da faqat tasodifiy token turadi, bazada esa uning SHA-256 xeshi saqlanadi:
- chiqish (logout) tokenni o'chiradi — nusxa olingan cookie ham ishlamay qoladi;
- parol o'zgarsa (sahifa, CLI reset-passwords yoki qayta seed) — eski sessiyalar avtomatik bekor bo'ladi (pw_tag);
- kalit jarayon xotirasida emas, bazada: server qayta ishga tushsa yoki bir nechta worker bo'lsa ham sessiya saqlanadi.
"""
import hashlib, secrets, sqlite3, threading, time

TTL = 12 * 3600
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INT NOT NULL, created REAL, expires REAL, pw_tag TEXT, ip TEXT);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
"""

def init(con):
    con.executescript(SCHEMA)
    if "ua" not in {r[1] for r in con.execute("PRAGMA table_info(sessions)")}:
        con.execute("ALTER TABLE sessions ADD COLUMN ua TEXT")
    con.commit()

def _h(tok: str) -> str: return hashlib.sha256(tok.encode()).hexdigest()
def pw_tag(pin) -> str: return hashlib.sha256(str(pin or "").encode()).hexdigest()[:16]

def device(ua: str) -> str:
    """User-Agent → «Chrome · macOS» kabi qisqa nom (faqat ko'rsatish uchun)."""
    ua = ua or ""
    if not ua: return "Noma'lum qurilma"
    b = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("YaBrowser", "Yandex"), ("Firefox/", "Firefox"),
                             ("Chrome/", "Chrome"), ("Safari/", "Safari"), ("python-httpx", "API mijoz"), ("curl/", "API mijoz")) if k in ua), "Brauzer")
    o = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
                             ("Mac OS X", "macOS"), ("Linux", "Linux")) if k in ua), "")
    return f"{b}, {o}" if o else b

def create(con, user: dict, ip: str = "", ua: str = "") -> str:
    tok, now = secrets.token_urlsafe(32), time.time()
    try:
        con.execute("DELETE FROM sessions WHERE expires<?", (now,))
    except sqlite3.OperationalError:     # baza qayta seed qilingan — jadval yo'q
        init(con)
    try:
        con.execute("INSERT INTO sessions(token,user_id,created,expires,pw_tag,ip,ua) VALUES(?,?,?,?,?,?,?)",
                    (_h(tok), user["id"], now, now + TTL, pw_tag(user["pin"]), ip[:64], (ua or "")[:300]))
    except sqlite3.OperationalError:
        init(con)
        con.execute("INSERT INTO sessions(token,user_id,created,expires,pw_tag,ip,ua) VALUES(?,?,?,?,?,?,?)",
                    (_h(tok), user["id"], now, now + TTL, pw_tag(user["pin"]), ip[:64], (ua or "")[:300]))
    con.commit()
    return tok

def resolve(con, tok) -> int | None:
    """Token → foydalanuvchi id (muddati o'tgan, chiqilgan yoki parol o'zgargan bo'lsa — None)."""
    if not tok or len(tok) > 128: return None
    try:
        r = con.execute("SELECT s.user_id, s.pw_tag, u.pin FROM sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.token=? AND s.expires>?", (_h(tok), time.time())).fetchone()
    except sqlite3.OperationalError:
        init(con); return None
    if not r or r[1] != pw_tag(r[2]): return None
    return r[0]

def revoke(con, tok):
    if not tok: return
    try:
        con.execute("DELETE FROM sessions WHERE token=?", (_h(tok),)); con.commit()
    except sqlite3.OperationalError:
        pass

def revoke_user(con, uid: int, keep_tok: str | None = None, new_pin: str | None = None) -> int:
    """Foydalanuvchining barcha sessiyalarini bekor qiladi; keep_tok (joriy brauzer) yangi parol bilan saqlanib qoladi."""
    try:
        n = con.execute("DELETE FROM sessions WHERE user_id=? AND token!=?", (uid, _h(keep_tok) if keep_tok else "")).rowcount
        if keep_tok and new_pin is not None:
            con.execute("UPDATE sessions SET pw_tag=? WHERE token=?", (pw_tag(new_pin), _h(keep_tok)))
        con.commit(); return n
    except sqlite3.OperationalError:
        return 0

def revoke_all(con):
    try:
        con.execute("DELETE FROM sessions"); con.commit()
    except sqlite3.OperationalError:
        pass


class Limiter:
    """Xato urinishlar cheklovi: `window` soniya ichida `limit` ta xato → blok (jarayon xotirasida)."""
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self._f: dict = {}
        self._lock = threading.Lock()

    def _live(self, key, now):
        f = [t for t in self._f.get(key, []) if now - t < self.window]
        if f: self._f[key] = f
        else: self._f.pop(key, None)
        return f

    def wait_min(self, key) -> int:
        """Blok bo'lsa — necha daqiqa kutish kerak, aks holda 0."""
        now = time.time()
        with self._lock:
            f = self._live(key, now)
        return max(1, int((self.window - (now - f[0])) // 60) + 1) if len(f) >= self.limit else 0

    def fail(self, key) -> int:
        """Xato urinishni qayd etadi; qolgan urinishlar sonini qaytaradi."""
        now = time.time()
        with self._lock:
            f = self._live(key, now); f.append(now); self._f[key] = f
            if len(self._f) > 10000:          # xotira cheksiz o'smasin
                for k in [k for k, v in self._f.items() if now - v[-1] >= self.window]: self._f.pop(k, None)
            return max(0, self.limit - len(f))

    def reset(self, key):
        with self._lock: self._f.pop(key, None)


# Kirish: bitta akkauntga 10 daqiqada 5 ta xato; bitta IP manzildan 10 daqiqada 20 ta xato
LOGIN_USER = Limiter(5, 600)
LOGIN_IP = Limiter(20, 600)
