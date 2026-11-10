"""SQLite ulanishi va sxema. Barcha ma'lumot lokal faylda: data/jarvis.db"""
import sqlite3, threading
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("ISFT_CORE_DATA_DIR") or (Path(__file__).resolve().parent.parent / "data"))   # barcha fayllar (doimiy disk shu yerga ulanadi)
DB_PATH = Path(os.environ.get("ISFT_CORE_DB") or (DATA_DIR / "jarvis.db"))   # ISFT_CORE_DB — test/agent uchun alohida baza

SCHEMA = """
CREATE TABLE IF NOT EXISTS faculties(id INTEGER PRIMARY KEY, name TEXT, dean TEXT);
CREATE TABLE IF NOT EXISTS departments(id INTEGER PRIMARY KEY, faculty_id INT, name TEXT, head TEXT);
CREATE TABLE IF NOT EXISTS groups_(id INTEGER PRIMARY KEY, department_id INT, faculty_id INT, name TEXT, course INT, direction TEXT, level TEXT, form TEXT);
CREATE TABLE IF NOT EXISTS teachers(id INTEGER PRIMARY KEY, full_name TEXT, department_id INT, faculty_id INT, degree TEXT, position TEXT, load_hours INT, h_index INT);
CREATE TABLE IF NOT EXISTS teacher_groups(teacher_id INT, group_id INT, subject TEXT);
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, hemis_id TEXT, full_name TEXT, group_id INT, faculty_id INT,
  gender TEXT, region TEXT, payment_type TEXT, contract_amount INT, paid_amount INT, gpa REAL, attendance REAL,
  gpa_prev REAL, status TEXT, level TEXT, study_form TEXT);
CREATE TABLE IF NOT EXISTS grades(student_id INT, subject TEXT, teacher_id INT, score INT, semester INT);
CREATE TABLE IF NOT EXISTS publications(id INTEGER PRIMARY KEY, teacher_id INT, title TEXT, kind TEXT, year INT, citations INT);
CREATE TABLE IF NOT EXISTS grants(id INTEGER PRIMARY KEY, title TEXT, leader_id INT, funder TEXT, amount INT, status TEXT, year INT);
CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY, name TEXT, country TEXT, kind TEXT, signed TEXT, expires TEXT, status TEXT, students_exchanged INT);
CREATE TABLE IF NOT EXISTS applicants(id INTEGER PRIMARY KEY, direction TEXT, faculty_id INT, applied TEXT, status TEXT, score REAL, payment_type TEXT);
CREATE TABLE IF NOT EXISTS budget(id INTEGER PRIMARY KEY, month TEXT, category TEXT, planned INT, actual INT);
CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY, full_name TEXT, unit TEXT, position TEXT, salary INT, hired TEXT, passport TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, title TEXT, date TEXT, kind TEXT, participants INT);
CREATE TABLE IF NOT EXISTS dormitory(id INTEGER PRIMARY KEY, building TEXT, capacity INT, occupied INT);
CREATE TABLE IF NOT EXISTS appeals(id INTEGER PRIMARY KEY, date TEXT, category TEXT, text TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS masters(id INTEGER PRIMARY KEY, student_id INT, supervisor_id INT, topic TEXT, stage TEXT);
CREATE TABLE IF NOT EXISTS meetings(id INTEGER PRIMARY KEY, title TEXT, date TEXT, kind TEXT, transcript TEXT);
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, meeting_id INT, assignee TEXT, assignee_role TEXT, text TEXT, due TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, full_name TEXT, role TEXT, faculty_id INT, department_id INT,
  teacher_id INT, telegram_id INT, link_code TEXT, pin TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, reg_no TEXT UNIQUE, kind TEXT, title TEXT, holder TEXT, created_by INT,
  creator_role TEXT, created_at TEXT, status TEXT, verify_code TEXT UNIQUE, file TEXT, params TEXT, signed_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, user_name TEXT, role TEXT, channel TEXT,
  action TEXT, resource TEXT, allowed INT, detail TEXT);
"""

def _open() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con

class ThreadCon:
    """Har bir oqim (thread) uchun alohida SQLite ulanishi.
    FastAPI sinxron endpointlarni thread pool'da parallel bajaradi; bitta umumiy ulanish bir vaqtdagi so'rovlarda
    "cannot commit - no transaction is active" / "bad parameter or other API misuse" xatolarini berardi.
    Kod avvalgidek `con.execute(...)`, `con.commit()` deb ishlatadi — chaqiruv joriy oqim ulanishiga yo'naltiriladi."""
    def __init__(self):
        self._tl = threading.local()
    def _c(self) -> sqlite3.Connection:
        c = getattr(self._tl, "c", None)
        if c is None:
            c = self._tl.c = _open()
        return c
    def __getattr__(self, name):
        return getattr(self._c(), name)

def connect() -> ThreadCon:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return ThreadCon()

def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    from . import kadrlar as _K; con.executescript(_K.SCHEMA)   # hr_files — boshqa modullar bo'shatilgan xodimlarni chiqarib tashlaydi (seed ham)
    con.commit()

def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]

def one(con, sql, args=()):
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None
