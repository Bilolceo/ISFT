"""Talaba kartasi (360°) — bitta talaba haqidagi hamma narsa bir joyda.

GET /api/karta/{sid} — Talabalar markazi kartasi (student_ops.student_card: ko'lam, qoida va moliya cheklovlari o'sha yerda)
ustiga boshqa modullardagi bo'limlar qo'shiladi: buyruqlar, ko'chirish, hujjatlar, to'lovlar, amaliyot, turar joy, xalqaro,
apellyatsiya/qayta o'qish, talaba kabineti so'rovlari, reyting. Har bir bo'lim lavozimga qarab ko'rsatiladi; jadval yo'q bo'lsa — o'tkazib yuboriladi.
Ruxsat: talabalar markazining o'zi (rbac OPS + _view_guard): Registrator ofisi, akademik, O'quv prorektori — hammasi;
sirtqi — sirtqi talabalar; tyutor — o'z guruhlari; kafedra — kafedra guruhlari; imtihon — o'qish; buxgalteriya — faqat moliya;
call-markaz — cheklangan (navbatidagi talaba, ism/telefon/qo'ng'iroqlar).
"""
import json
from fastapi import APIRouter, Request
from . import db, rbac
from . import student_ops as SO

router = APIRouter()
_con = None
_ctx = None

def bind(con, ctx_fn):
    global _con, _ctx
    _con, _ctx = con, ctx_fn

FIN = ("talabalar", "registrator_xodim", "sirtqi", "buxgalteriya", "prorektor_oquv", "akademik")   # kontrakt va to'lovlar
ACTIONS = {   # «Nima qilmoqchisiz?» — kim nima qila oladi (har biri o'z modulidagi asl oqimni ochadi)
    "ruxsatnoma": ("talabalar", "registrator_xodim", "sirtqi"),
    "otrabotka": ("talabalar", "registrator_xodim", "tyutor", "sirtqi"),
    "malumotnoma": ("talabalar", "registrator_xodim", "tyutor", "sirtqi"),
    "buyruq": ("talabalar", "registrator_xodim", "sirtqi", "malumotlar_bazasi"),
    "qayta_oqish": ("talabalar", "registrator_xodim", "akademik", "kafedra", "sirtqi"),
    "apellyatsiya": ("talabalar", "registrator_xodim", "akademik", "imtihon", "kafedra"),
}

def _q(sql, args=()):
    try: return db.rows(_con, sql, args)
    except Exception: return []      # modul jadvali hali yaratilmagan bo'lishi mumkin

def card(c, sid: int) -> dict:
    k = c.role.key
    base = SO.student_card(c, sid)            # ko'lamni tekshiradi (AccessDenied)
    acad = k != "buxgalteriya"
    out = {"base": base, "role": k, "actions": [a for a, rs in ACTIONS.items() if k in rs]}
    s = db.one(_con, "SELECT study_form, payment_type, group_id FROM students WHERE id=?", (sid,)) or {}
    out["study_form"] = s.get("study_form")
    if acad:
        out["rating"] = (_q("SELECT semester, gpa, avg_score, r_group, n_group, r_course, n_course, attendance FROM rating_cache WHERE student_id=? ORDER BY semester DESC LIMIT 1", (sid,)) or [None])[0]
        out["current"] = _q("SELECT subject, oraliq, credits FROM grades WHERE student_id=? AND semester=1 ORDER BY subject", (sid,))
        out["appeals"] = _q("SELECT subject, status, filed_at, deadline, score_old, score_new FROM grade_appeals WHERE student_id=? ORDER BY id DESC", (sid,))
        out["restudy"] = _q("SELECT subject, credits, decision, amount, paid, deadline FROM restudy WHERE student_id=? ORDER BY id DESC", (sid,))
        out["orders"] = _q("""SELECT o.id, o.kind, o.title, o.status, o.reg_no, o.order_date FROM order_students os JOIN orders o ON o.id=os.order_id
                              WHERE os.student_id=? AND COALESCE(o.demo,0)=0 GROUP BY o.id ORDER BY COALESCE(o.order_date, o.created_at) DESC LIMIT 40""", (sid,))
        out["transfers"] = _q("SELECT kind, status, reason, created_at FROM transfers WHERE student_id=? ORDER BY id DESC", (sid,))
        out["changes"] = _q("SELECT ts, field, old, new, reg_no, user_name FROM student_changes WHERE student_id=? AND COALESCE(reverted,0)=0 ORDER BY id DESC LIMIT 30", (sid,))
        out["docs"] = _q("SELECT reg_no, kind, title, created_at, status FROM documents WHERE params LIKE ? ORDER BY id DESC LIMIT 40", (f'%"s:{int(sid)}"%',))
        out["practice"] = _q("""SELECT a.status, a.score, a.report_at, b.name base, p.title period, p.start, p.end FROM prac_assign a
                                LEFT JOIN prac_bases b ON b.id=a.base_id LEFT JOIN prac_periods p ON p.id=a.period_id WHERE a.student_id=? ORDER BY a.id DESC""", (sid,))
        out["dorm"] = {"residents": _q("""SELECT r.status, r.check_in, r.check_out, rm.number room, b.name building FROM yj_residents r
                                          LEFT JOIN yj_rooms rm ON rm.id=r.room_id LEFT JOIN yj_buildings b ON b.id=rm.building_id WHERE r.student_id=? ORDER BY r.id DESC""", (sid,)),
                       "applications": _q("SELECT status, score, submitted_at FROM yj_applications WHERE student_id=? ORDER BY id DESC", (sid,)),
                       "rental": _q("SELECT district, since, last_visit FROM yj_rentals WHERE student_id=?", (sid,))}
        out["intl"] = _q("SELECT status, total, rank, created_at, credit_status FROM intl_applications WHERE student_id=? ORDER BY id DESC", (sid,))
        out["requests"] = _q("SELECT kind, status, created_at, review_note, doc_reg FROM student_requests WHERE student_id=? ORDER BY id DESC LIMIT 30", (sid,))
    if k in FIN:
        out["payments"] = _q("""SELECT paid_on, amount, receipt_no, method, status FROM fin_payments WHERE student_id=? ORDER BY paid_on DESC, id DESC LIMIT 30""", (sid,))
        out["deferments"] = _q("SELECT until, note FROM contract_deferments WHERE student_id=? ORDER BY id DESC", (sid,))
    return out

@router.get("/api/karta/{sid}")
def api_card(sid: int, request: Request):
    c = _ctx(request)
    SO._view_guard(c, "talaba kartasi (360)")
    if c.role.key == "call_center":
        d = SO.api_student(sid, request)        # o'z navbatidagi talaba, minimal ma'lumot
        return {"base": d, "role": "call_center", "actions": [], "limited": True}
    rbac.audit(_con, c, "talaba kartasi (360)", SO.OPS, True, f"#{sid}")
    return card(c, sid)
