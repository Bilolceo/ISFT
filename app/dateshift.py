"""Demo ma'lumotlarni bugungi sanaga ko'chirish.

Seed "hikoya"si (muddati o'tgan topshiriqlar, tugayotgan shartnomalar, majlislar) BASE = 2026-11-04 ga nisbatan yozilgan.
Seed oxirida barcha sanalar (bugun − BASE) kunga suriladi — shunda munosabatlar (masalan, "3 ta topshiriq muddati o'tgan",
"shartnoma 23 kundan keyin tugaydi") saqlanadi, lekin hamma narsa haqiqiy bugungi kunga bog'lanadi.
Majlis bayonnomalari matnidagi sanalar ham ("13.10.2026", "15-noyabrgacha") birga suriladi.
"""
import datetime as dt, re

BASE = dt.date(2026, 11, 4)
UZ_M = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

# (jadval, ustun) — seed'ning BASE ga bog'langan qismi. Xizmat markazi/kameralar allaqachon real vaqtda yaratiladi.
COLUMNS = [("appeals", "date"), ("meetings", "date"), ("tasks", "due"), ("events", "date"), ("partners", "signed"), ("partners", "expires"),
           ("applicants", "applied"), ("staff", "hired"), ("audit_log", "ts")]

def _year_for(month: int) -> int:
    return BASE.year if month >= 8 else BASE.year + 1     # matnlarda sentabr–dekabr 2026, keyingi oylar 2027

def shift_text(text: str, days: int) -> str:
    if not text or not days: return text
    def full(m):
        try: d = dt.date(int(m[3]), int(m[2]), int(m[1])) + dt.timedelta(days=days)
        except ValueError: return m[0]
        return f"{d.day:02d}.{d.month:02d}.{d.year}"
    def worded(m):
        mon = UZ_M.index(m[2].lower()) + 1
        try: d = dt.date(_year_for(mon), mon, int(m[1])) + dt.timedelta(days=days)
        except ValueError: return m[0]
        return f"{d.day}-{UZ_M[d.month - 1]}"
    text = re.sub(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", full, text)
    return re.sub(r"\b(\d{1,2})-(" + "|".join(UZ_M) + r")", worded, text, flags=re.I)

def shift_all(con, days: int) -> int:
    if not days: return 0
    n = f"{int(days):+d} days"
    for t, c in COLUMNS:
        con.execute(f"""UPDATE {t} SET {c} = CASE WHEN {c} LIKE '____-__-__T%' THEN strftime('%Y-%m-%dT%H:%M:%S', {c}, ?)
                                                  WHEN {c} LIKE '____-__-__%' THEN date({c}, ?) ELSE {c} END WHERE {c} IS NOT NULL""", (n, n))
    for mid, tr in con.execute("SELECT id, transcript FROM meetings").fetchall():
        con.execute("UPDATE meetings SET transcript=? WHERE id=?", (shift_text(tr, days), mid))
    for tid, tx in con.execute("SELECT id, text FROM tasks").fetchall():
        con.execute("UPDATE tasks SET text=? WHERE id=?", (shift_text(tx, days), tid))
    con.commit()
    return days
