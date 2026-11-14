"""HEMIS almashinuvi — reja (dry-run): HEMIS yozuvlari ↔ ISFT Core. Bazaga YOZMAYDI (faqat o'qiydi). Qo'llash — app/hemis.py.

Har bir reja: inserts (yangi yozuvlar), updates (ISFT Core'da bo'sh maydonni to'ldirish yoki auto_fields), diffs (Farqlar navbatiga),
equal (mos kelgan maydonlar — ochiq farqni «mos keldi» deb yopish uchun), missing («HEMIS'da topilmadi»), errors (ziddiyatli qatorlar).
Qator toifasi: ziddiyatli (xato yoki farq) > o'zgargan (avtomatik to'ldiriladi) > o'zgarmagan.
Ko'lam (scope): «qisman» — «topilmadi» faqat fayldagi birliklar ichida (talabalar — fayldagi guruhlar; guruhlar — fakultetlar;
xodimlar — kafedralar; yuklama — o'qituvchilar; baholar — talaba+semestr); «toliq» — butun institut (fayl to'liq eksport bo'lsa).
"""
from __future__ import annotations
import json
from . import db, hemis_map as HM

FIELD_T = {"full_name": "F.I.Sh.", "group": "Guruh", "study_form": "Ta'lim shakli", "status": "Holat", "citizenship": "Fuqarolik",
           "payment_type": "To'lov shakli", "course": "Kurs", "direction": "Yo'nalish", "level": "Ta'lim bosqichi", "department": "Kafedra",
           "position": "Lavozim", "degree": "Ilmiy daraja", "score": "Ball", "hemis_id": "HEMIS ID"}
ACTIVE = ("faol", "akademik ta'til")


def _j(v) -> str: return json.dumps(v, ensure_ascii=False, default=str)


def _plan0(entity):
    return {"entity": entity, "inserts": [], "updates": [], "diffs": [], "equal": [], "missing": [], "present": [], "errors": [],
            "spelling": 0, "cats": {"new": [], "changed": [], "conflict": []}, "unchanged": 0, "rows": 0}


def _err(pl, r, ref, label, msgs):
    pl["errors"].append({"row": r.get("_row"), "ref": ref, "label": label, "msgs": msgs})
    pl["cats"]["conflict"].append({"row": r.get("_row"), "ref": ref, "label": label, "why": "; ".join(msgs)})


def _finish_row(pl, ref, label, fields, diffs, row=None):
    if diffs:
        pl["cats"]["conflict"].append({"row": row, "ref": ref, "label": label,
                                       "why": "; ".join(f"{FIELD_T.get(d['field'], d['field'])}: {d['core_value'] or '—'} → {d['hemis_value'] or '—'}" for d in diffs)})
    elif fields:
        pl["cats"]["changed"].append({"row": row, "ref": ref, "label": label, "why": ", ".join(FIELD_T.get(f, f) for f in fields)})
    else:
        pl["unchanged"] += 1


def _cmp(pl, entity, ref, label, core_id, field, core_v, hem_v, auto, sets, diffs, col=None, set_v=None, can_set=True, core_key=None):
    """core_v / hem_v — solishtiriladigan ko'rinishdagi qiymatlar (None/'' = bo'sh). Bo'sh HEMIS qiymati e'tiborsiz."""
    if hem_v in (None, ""): return
    if core_v not in (None, "") and str(core_v) == str(hem_v):
        pl["equal"].append((entity, ref, field)); return
    if can_set and (core_v in (None, "") or field in auto):
        sets[col or field] = hem_v if set_v is None else set_v
        sets.setdefault("_fields", []).append(field)
        return
    diffs.append({"entity": entity, "ref": ref, "label": label, "core_id": core_id, "core_key": core_key, "field": field,
                  "core_value": "" if core_v is None else str(core_v), "hemis_value": str(hem_v)})


def _push(pl, tbl, rid, sets, before, idcol="id"):
    fields = sets.pop("_fields", [])
    if sets: pl["updates"].append({"tbl": tbl, "id": rid, "idcol": idcol, "set": sets, "before": {k: before.get(k) for k in sets}})
    return fields


def groups_idx(con):
    gs = db.rows(con, "SELECT id, name, hemis_id, course, direction, level, form, faculty_id FROM groups_")
    return {HM.group_key(g["name"]): g for g in gs}, {g["id"]: g for g in gs}, {g["hemis_id"]: g for g in gs if g.get("hemis_id")}


def teachers_idx(con):
    ts = db.rows(con, """SELECT t.id, t.hemis_id, t.full_name, t.position, t.degree, t.department_id, t.faculty_id, d.name dept FROM teachers t
                         LEFT JOIN departments d ON d.id=t.department_id""")
    by_name = {}
    for t in ts: by_name.setdefault(HM.name_key(t["full_name"]), []).append(t)
    return ts, {t["hemis_id"]: t for t in ts if t.get("hemis_id")}, by_name


# =============================================================================================
def plan_students(con, recs, scope, auto) -> dict:
    pl = _plan0("students")
    gk_idx, gid_idx, _ = groups_idx(con)
    core = {}
    for s in db.rows(con, """SELECT id, hemis_id, full_name, group_id, faculty_id, status, study_form, citizenship, payment_type FROM students
                             WHERE hemis_id IS NOT NULL AND hemis_id!='' ORDER BY id"""):
        core.setdefault(s["hemis_id"], s)
    seen, touched, file_groups, gdone = set(), set(), set(), set()
    for r in recs:
        pl["rows"] += 1
        hid, name = HM.hemis_id(r.get("hemis_id")), HM.display_name(r.get("full_name"))
        gk = HM.group_key(r.get("group")); g = gk_idx.get(gk)
        if gk: file_groups.add(gk)
        if hid: touched.add(hid)
        errs, h = [], {}
        if not hid: errs.append("HEMIS ID bo'sh")
        elif hid in seen: errs.append("HEMIS ID faylda takrorlangan")
        if not name: errs.append("F.I.Sh. bo'sh")
        for f, fn in (("study_form", HM.form), ("status", HM.status), ("citizenship", HM.citizenship), ("payment_type", HM.payment)):
            raw = r.get(f, "")
            h[f] = fn(raw) if raw else None
            if raw and h[f] is None: errs.append(f"{FIELD_T[f]}: «{raw}» tanilmadi")
        if errs: _err(pl, r, hid, name, errs); continue
        seen.add(hid); pl["present"].append(hid)
        if g:                                   # guruh darajasidagi farqlar (kurs, yo'nalish) — guruh bo'yicha bir marta
            for f, hv in (("course", HM.course(r.get("course"))), ("direction", HM.display_name(r.get("direction")) or None)):
                if hv is None or (g["id"], f) in gdone: continue
                gdone.add((g["id"], f))
                same = (g[f] == hv) if f == "course" else (HM.subject_key(g[f]) == HM.subject_key(hv))
                if same: pl["equal"].append(("groups", g["name"], f))
                elif g[f] in (None, ""):
                    pl["updates"].append({"tbl": "groups_", "id": g["id"], "idcol": "id", "set": {f: hv}, "before": {f: g[f]}})
                else:
                    pl["diffs"].append({"entity": "groups", "ref": g["name"], "label": g["name"], "core_id": g["id"], "core_key": None,
                                        "field": f, "core_value": str(g[f]), "hemis_value": str(hv)})
        s = core.get(hid)
        if not s:
            if not g: _err(pl, r, hid, name, [f"Guruh «{r.get('group') or '—'}» ISFT Core'da yo'q — avval Guruhlar faylini import qiling"]); continue
            vals = {"hemis_id": hid, "full_name": name, "group_id": g["id"], "faculty_id": g["faculty_id"], "status": h["status"] or "faol",
                    "level": g["level"], "study_form": h["study_form"] or g["form"], "citizenship": h["citizenship"] or "UZ",
                    "payment_type": h["payment_type"]}
            pl["inserts"].append({"tbl": "students", "values": vals, "ref": hid, "label": name})
            pl["cats"]["new"].append({"row": r["_row"], "ref": hid, "label": name, "why": g["name"]})
            continue
        sets, diffs = {}, []
        if HM.name_key(s["full_name"]) == HM.name_key(name):
            pl["equal"].append(("students", hid, "full_name"))
            if HM.clean_spaces(s["full_name"]) != name: pl["spelling"] += 1
        else:
            _cmp(pl, "students", hid, name, s["id"], "full_name", s["full_name"], name, auto, sets, diffs)
        cg = gid_idx.get(s["group_id"]) or {}
        if gk:
            if HM.group_key(cg.get("name")) == gk: pl["equal"].append(("students", hid, "group"))
            else:
                _cmp(pl, "students", hid, name, s["id"], "group", cg.get("name"), g["name"] if g else HM.clean_spaces(r.get("group")).upper(),
                     auto, sets, diffs, col="group_id", set_v=g["id"] if g else None, can_set=bool(g))
                if "group_id" in sets: sets["faculty_id"] = g["faculty_id"]
        for f in ("study_form", "status", "payment_type"):
            _cmp(pl, "students", hid, name, s["id"], f, s[f], h[f], auto, sets, diffs)
        _cmp(pl, "students", hid, name, s["id"], "citizenship", s["citizenship"] or "UZ", h["citizenship"], auto, sets, diffs)
        fields = _push(pl, "students", s["id"], sets, s)
        pl["diffs"] += diffs
        _finish_row(pl, hid, name, fields, diffs, r["_row"])
    q = f"""SELECT s.id, s.hemis_id, s.full_name, g.name grp FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
            WHERE s.status IN {ACTIVE} AND s.hemis_id IS NOT NULL AND s.hemis_id!=''"""
    for s in db.rows(con, q):
        if s["hemis_id"] in touched: continue
        if scope != "toliq" and HM.group_key(s["grp"]) not in file_groups: continue
        pl["missing"].append({"entity": "students", "core_id": s["id"], "ref": s["hemis_id"], "label": f"{s['full_name']} · {s['grp'] or '—'}"})
    return pl


def plan_groups(con, recs, scope, auto) -> dict:
    pl = _plan0("groups")
    gk_idx, _, gh_idx = groups_idx(con)
    facs = {HM.subject_key(f["name"]): f["id"] for f in db.rows(con, "SELECT id, name FROM faculties")}
    seen, file_facs, present = set(), set(), set()
    for r in recs:
        pl["rows"] += 1
        name = HM.clean_spaces(HM.translit(r.get("group"))).upper(); gk = HM.group_key(name); hid = HM.hemis_id(r.get("hemis_id"))
        h = {"course": HM.course(r.get("course")), "direction": HM.display_name(r.get("direction")) or None,
             "level": HM.level(r.get("level")) if r.get("level") else None, "form": HM.form(r.get("study_form")) if r.get("study_form") else None}
        fid = facs.get(HM.subject_key(r.get("faculty"))) if r.get("faculty") else None
        errs = []
        if not gk: errs.append("Guruh nomi bo'sh")
        elif gk in seen: errs.append("Guruh faylda takrorlangan")
        if r.get("study_form") and not h["form"]: errs.append(f"Ta'lim shakli: «{r['study_form']}» tanilmadi")
        if r.get("level") and not h["level"]: errs.append(f"Ta'lim bosqichi: «{r['level']}» tanilmadi")
        if r.get("faculty") and not fid: errs.append(f"Fakultet «{r['faculty']}» ISFT Core'da yo'q")
        if errs: _err(pl, r, name, name, errs); continue
        seen.add(gk)
        if fid: file_facs.add(fid)
        g = (gh_idx.get(hid) if hid else None) or gk_idx.get(gk)
        if not g:
            pl["inserts"].append({"tbl": "groups_", "values": {"name": name, "hemis_id": hid or None, "course": h["course"], "direction": h["direction"],
                                                               "level": h["level"] or "bakalavr", "form": h["form"] or "kunduzgi", "faculty_id": fid},
                                  "ref": name, "label": name})
            pl["cats"]["new"].append({"row": r["_row"], "ref": name, "label": name, "why": h["direction"] or ""}); continue
        ref = g["name"]; present.add(g["id"]); pl["present"].append(ref)
        sets, diffs = {}, []
        if hid and not g.get("hemis_id"): sets["hemis_id"] = hid; sets["_fields"] = ["hemis_id"]
        _cmp(pl, "groups", ref, ref, g["id"], "course", g["course"], h["course"], auto, sets, diffs)
        dv = h["direction"]
        if dv and g["direction"] and HM.subject_key(dv) == HM.subject_key(g["direction"]): pl["equal"].append(("groups", ref, "direction"))
        else: _cmp(pl, "groups", ref, ref, g["id"], "direction", g["direction"], dv, auto, sets, diffs)
        _cmp(pl, "groups", ref, ref, g["id"], "level", g["level"], h["level"], auto, sets, diffs)
        _cmp(pl, "groups", ref, ref, g["id"], "study_form", g["form"], h["form"], auto, sets, diffs, col="form")
        fields = _push(pl, "groups_", g["id"], sets, g)
        pl["diffs"] += diffs
        _finish_row(pl, ref, ref, fields, diffs, r["_row"])
    if scope == "toliq" or file_facs:
        for g in db.rows(con, f"SELECT id, name, faculty_id FROM groups_ WHERE id IN (SELECT DISTINCT group_id FROM students WHERE status IN {ACTIVE})"):
            if g["id"] in present: continue
            if scope != "toliq" and g["faculty_id"] not in file_facs: continue
            pl["missing"].append({"entity": "groups", "core_id": g["id"], "ref": g["name"], "label": g["name"]})
    return pl


def plan_teachers(con, recs, scope, auto) -> dict:
    pl = _plan0("teachers")
    ts, by_h, by_n = teachers_idx(con)
    deps = {HM.subject_key(d["name"]): d for d in db.rows(con, "SELECT id, name, faculty_id FROM departments")}
    seen, file_deps, touched = set(), set(), set()
    for r in recs:
        pl["rows"] += 1
        hid, name = HM.hemis_id(r.get("hemis_id")), HM.display_name(r.get("full_name"))
        dep = deps.get(HM.subject_key(r.get("department"))) if r.get("department") else None
        key = hid or HM.name_key(name)
        errs = []
        if not name: errs.append("F.I.Sh. bo'sh")
        elif key in seen: errs.append("Xodim faylda takrorlangan")
        if r.get("department") and not dep: errs.append(f"Kafedra «{r['department']}» ISFT Core'da yo'q")
        t = by_h.get(hid) if hid else None
        if not t and name and not errs:
            cand = [x for x in by_n.get(HM.name_key(name), []) if not (hid and x.get("hemis_id") and x["hemis_id"] != hid)]
            if len(cand) > 1: errs.append("ISFT Core'da shu ismli bir nechta xodim — HEMIS ID bilan aniqlang")
            elif cand: t = cand[0]
        if errs: _err(pl, r, hid or name, name, errs); continue
        seen.add(key)
        if dep: file_deps.add(dep["id"])
        pos, deg = HM.clean_spaces(r.get("position")) or None, HM.clean_spaces(r.get("degree")) or None
        if not t:
            pl["inserts"].append({"tbl": "teachers", "values": {"full_name": name, "hemis_id": hid or None, "department_id": dep["id"] if dep else None,
                                                                "faculty_id": dep["faculty_id"] if dep else None, "position": pos, "degree": deg},
                                  "ref": hid or name, "label": name})
            pl["cats"]["new"].append({"row": r["_row"], "ref": hid or name, "label": name, "why": dep["name"] if dep else ""}); continue
        touched.add(t["id"]); ref = t.get("hemis_id") or hid or t["full_name"]
        pl["present"].append(ref)
        if t.get("hemis_id") != ref or not t.get("hemis_id"): pl["present"].append(t["full_name"])
        sets, diffs = {}, []
        if hid and not t.get("hemis_id"): sets["hemis_id"] = hid; sets["_fields"] = ["hemis_id"]
        if HM.name_key(t["full_name"]) == HM.name_key(name):
            pl["equal"].append(("teachers", ref, "full_name"))
            if HM.clean_spaces(t["full_name"]) != name: pl["spelling"] += 1
        else: _cmp(pl, "teachers", ref, name, t["id"], "full_name", t["full_name"], name, auto, sets, diffs)
        if dep:
            if t["department_id"] == dep["id"]: pl["equal"].append(("teachers", ref, "department"))
            else:
                _cmp(pl, "teachers", ref, name, t["id"], "department", t["dept"], dep["name"], auto, sets, diffs, col="department_id", set_v=dep["id"])
                if "department_id" in sets: sets["faculty_id"] = dep["faculty_id"]
        _cmp(pl, "teachers", ref, name, t["id"], "position", t["position"], pos, auto, sets, diffs)
        _cmp(pl, "teachers", ref, name, t["id"], "degree", t["degree"], deg, auto, sets, diffs)
        fields = _push(pl, "teachers", t["id"], sets, t)
        pl["diffs"] += diffs
        _finish_row(pl, ref, name, fields, diffs, r["_row"])
    if scope == "toliq" or file_deps:
        for t in ts:
            if t["id"] in touched: continue
            if scope != "toliq" and t["department_id"] not in file_deps: continue
            pl["missing"].append({"entity": "teachers", "core_id": t["id"], "ref": t.get("hemis_id") or t["full_name"],
                                  "label": f"{t['full_name']} · {t['dept'] or '—'}"})
    return pl


def plan_load(con, recs, scope, auto) -> dict:
    pl = _plan0("load")
    ts, by_h, by_n = teachers_idx(con)
    tid_idx = {t["id"]: t for t in ts}
    gk_idx, gid_idx, _ = groups_idx(con)
    core = {}
    for x in db.rows(con, "SELECT rowid rid, teacher_id, group_id, subject FROM teacher_groups"):
        core.setdefault((x["teacher_id"], x["group_id"], HM.subject_key(x["subject"])), x)
    seen, file_t, hours = set(), set(), 0.0
    for r in recs:
        pl["rows"] += 1
        thid, tname = HM.hemis_id(r.get("teacher_hemis_id")), HM.display_name(r.get("teacher"))
        t, errs = (by_h.get(thid) if thid else None), []
        if not t and tname:
            cand = by_n.get(HM.name_key(tname), [])
            if len(cand) == 1: t = cand[0]
            elif len(cand) > 1: errs.append("O'qituvchi ismi bir nechta xodimga mos — HEMIS ID kerak")
        g = gk_idx.get(HM.group_key(r.get("group")))
        subj = HM.clean_spaces(r.get("subject"))
        label = f"{(t or {}).get('full_name') or tname or thid} — {r.get('group') or '—'} — {subj or '—'}"
        if not t and not errs: errs.append("O'qituvchi ISFT Core'da topilmadi — avval Xodimlar faylini import qiling")
        if not g: errs.append(f"Guruh «{r.get('group') or '—'}» ISFT Core'da yo'q")
        if not subj: errs.append("Fan bo'sh")
        if errs: _err(pl, r, label, label, errs); continue
        k = (t["id"], g["id"], HM.subject_key(subj))
        if k in seen: _err(pl, r, label, label, ["Yuklama qatori faylda takrorlangan"]); continue
        seen.add(k); file_t.add(t["id"])
        try: hours += float(str(r.get("hours") or 0).replace(",", "."))
        except ValueError: pass
        ref = f"{t['id']}|{g['id']}|{k[2]}"
        if k in core: pl["unchanged"] += 1; pl["present"].append(ref); continue
        pl["inserts"].append({"tbl": "teacher_groups", "values": {"teacher_id": t["id"], "group_id": g["id"], "subject": subj}, "ref": ref, "label": label})
        pl["cats"]["new"].append({"row": r["_row"], "ref": ref, "label": label, "why": f"{r.get('hours') or ''} soat" if r.get("hours") else ""})
    for k, x in core.items():
        if k in seen: continue
        if scope != "toliq" and k[0] not in file_t: continue
        t, g = tid_idx.get(k[0]) or {}, gid_idx.get(k[1]) or {}
        pl["missing"].append({"entity": "load", "core_id": x["rid"], "ref": f"{k[0]}|{k[1]}|{k[2]}",
                              "label": f"{t.get('full_name') or '#' + str(k[0])} — {g.get('name') or '#' + str(k[1])} — {x['subject']}"})
    pl["hours"] = round(hours, 1)
    return pl


def plan_grades(con, recs, scope, auto) -> dict:
    pl = _plan0("grades")
    hids = sorted({HM.hemis_id(r.get("hemis_id")) for r in recs} - {""})
    st = {}
    for i in range(0, len(hids), 900):
        ch = hids[i:i + 900]
        for s in db.rows(con, f"""SELECT s.id, s.hemis_id, s.full_name, g.course FROM students s LEFT JOIN groups_ g ON g.id=s.group_id
                                  WHERE s.hemis_id IN ({','.join('?' * len(ch))}) ORDER BY s.id""", ch):
            st.setdefault(s["hemis_id"], s)
    core, ids = {}, [s["id"] for s in st.values()]
    for i in range(0, len(ids), 900):
        ch = ids[i:i + 900]
        for x in db.rows(con, f"SELECT rowid rid, student_id, subject, score, sem_no, semester FROM grades WHERE student_id IN ({','.join('?' * len(ch))})", ch):
            core.setdefault((x["student_id"], HM.subject_key(x["subject"]), x["sem_no"]), x)
    seen, pairs = set(), set()
    for r in recs:
        pl["rows"] += 1
        hid, subj = HM.hemis_id(r.get("hemis_id")), HM.clean_spaces(r.get("subject"))
        sem, sc = HM.course(r.get("semester")), HM.score(r.get("score"))
        s = st.get(hid)
        label = f"{(s or {}).get('full_name') or HM.display_name(r.get('full_name')) or hid} — {subj} — {sem or '?'}-semestr"
        errs = []
        if not s: errs.append("Talaba (HEMIS ID) ISFT Core'da topilmadi")
        if not subj: errs.append("Fan bo'sh")
        if not sem or not 1 <= sem <= 12: errs.append("Semestr noto'g'ri")
        if sc is None and HM.clean_spaces(r.get("score")): errs.append(f"Ball «{r.get('score')}» noto'g'ri (0–100)")
        ref = f"{hid}|{subj}|{sem}"
        if errs: _err(pl, r, ref, label, errs); continue
        k = (s["id"], HM.subject_key(subj), sem)
        if k in seen: _err(pl, r, ref, label, ["Baho faylda takrorlangan"]); continue
        seen.add(k); pairs.add((s["id"], sem))
        x = core.get(k)
        if not x:
            code = sem - 2 * int(s["course"] or 1) + 2          # academic_rules: sem_no = 2·kurs − 2 + kod
            pl["inserts"].append({"tbl": "grades", "values": {"student_id": s["id"], "subject": subj, "score": sc, "sem_no": sem, "semester": code},
                                  "ref": ref, "label": label})
            pl["cats"]["new"].append({"row": r["_row"], "ref": ref, "label": label, "why": "" if sc is None else num(sc)}); continue
        pl["present"].append(ref)
        sets, diffs = {}, []
        _cmp(pl, "grades", ref, label, s["id"], "score", None if x["score"] is None else num(x["score"]), None if sc is None else num(sc),
             auto, sets, diffs, set_v=sc, core_key=_j({"rowid": x["rid"]}))
        fields = _push(pl, "grades", x["rid"], sets, x, idcol="rowid")
        pl["diffs"] += diffs
        _finish_row(pl, ref, label, fields, diffs, r["_row"])
    by_id = {s["id"]: s for s in st.values()}
    studs = {p[0] for p in pairs}
    for k, x in core.items():
        if k in seen: continue
        if scope != "toliq" and (k[0], k[2]) not in pairs: continue
        if scope == "toliq" and k[0] not in studs: continue
        s = by_id.get(k[0]) or {}
        pl["missing"].append({"entity": "grades", "core_id": x["rid"], "ref": f"{s.get('hemis_id')}|{x['subject']}|{x['sem_no']}",
                              "label": f"{s.get('full_name')} — {x['subject']} — {x['sem_no']}-semestr"})
    return pl


def num(v) -> str:
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:.1f}"


PLANNERS = {"students": plan_students, "groups": plan_groups, "teachers": plan_teachers, "load": plan_load, "grades": plan_grades}


def plan(con, entity: str, recs: list[dict], scope: str = "qisman", auto=()) -> dict:
    return PLANNERS[entity](con, recs, scope, set(auto or ()))


def counts(pl) -> dict:
    c = pl["cats"]
    return {"rows": pl["rows"], "new": len(c["new"]), "changed": len(c["changed"]), "unchanged": pl["unchanged"],
            "conflicting": len(c["conflict"]), "missing": len(pl["missing"]), "diffs": len(pl["diffs"]), "errors": len(pl["errors"]),
            "spelling": pl["spelling"], "updates": len(pl["updates"]), "inserts": len(pl["inserts"])}
