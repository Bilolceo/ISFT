"""Portal fayllari va yozishmalarining zaxira nusxasi (backup), tiklash (restore) va yaxlitlik tekshiruvi (verify).

Ishlatish:
  .venv/bin/python -m app.portal_backup backup OUT.zip       — bitta ZIP: manifest.json + db/<jadval>.json + files/<stored>
  .venv/bin/python -m app.portal_backup restore IN.zip [--force]
  .venv/bin/python -m app.portal_backup verify [--fix]

Tamoyillar:
  * Ma'lumotlar bazasidan izchil nusxa olinadi (sqlite backup API → vaqtinchalik fayl), keyin jadvallar JSON'ga yoziladi.
  * Tiklash: portal jadvallari bo'sh bo'lmasa — faqat --force bilan; qatorlar INSERT OR REPLACE, ustunlar joriy sxema bilan kesishtiriladi;
    fayllar portal.FILES ichiga yoziladi, sha256 bo'lsa — tekshiriladi. Arxivdan faqat portal_files'da qayd etilgan nomlar olinadi.
  * Tekshiruv: yo'q fayl, hajm/sha256 nomuvofiqligi, bazada qayd etilmagan (yetim) fayllar. --fix faqat yo'q sha256 ni hisoblab yozadi,
    hech narsani o'chirmaydi. Muammo topilsa — chiqish kodi 1.
"""
import argparse, base64, datetime as dt, hashlib, json, os, re, sqlite3, sys, tempfile, zipfile
from pathlib import Path

TABLES = ["portal_threads", "portal_recipients", "portal_msgs", "portal_reads", "portal_user_reads", "portal_attach", "portal_files",
          "portal_shares", "portal_resolutions", "portal_watchers", "portal_drafts", "portal_templates", "portal_hidden", "org_units"]
FORMAT = "isft-portal-backup"
SAFE_STORED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")

def _files_dir() -> Path:
    from app import portal
    return Path(portal.FILES)

def _con():
    from app import db
    return db.connect()

def _q(name: str) -> str: return '"' + name.replace('"', '""') + '"'
def _safe(stored) -> bool: return bool(stored) and bool(SAFE_STORED.match(str(stored))) and ".." not in str(stored)
def _tables(con) -> set[str]: return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def _cols(con, t) -> list[str]: return [r[1] for r in con.execute(f"PRAGMA table_info({_q(t)})")]
def _mb(n) -> str: return f"{n / (1024 * 1024):.1f} MB"

def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def _enc(v):
    return {"$b64": base64.b64encode(v).decode()} if isinstance(v, (bytes, bytearray, memoryview)) else v

def _dec(v):
    return base64.b64decode(v["$b64"]) if isinstance(v, dict) and "$b64" in v else v

# --------------------------------------------------------------------------------------------- backup
def backup(out: str) -> int:
    files = _files_dir(); out = Path(out)
    with tempfile.TemporaryDirectory(prefix="portal-bk-") as tmp:
        snap = sqlite3.connect(Path(tmp) / "snap.db")
        con = _con()
        try: con.backup(snap)                      # izchil nusxa: yozuvlar davom etsa ham bir lahzalik holat
        finally: con.close()
        snap.row_factory = sqlite3.Row
        have = _tables(snap)
        tmp_out = out.with_name(out.name + ".part")
        counts, missing, nfiles, nbytes = {}, [], 0, 0
        with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for t in TABLES:
                if t not in have: continue
                cols = _cols(snap, t)
                rows = [[_enc(v) for v in r] for r in snap.execute(f"SELECT * FROM {_q(t)}")]
                counts[t] = len(rows)
                z.writestr(f"db/{t}.json", json.dumps({"table": t, "columns": cols, "rows": rows}, ensure_ascii=False))
            if "portal_files" in have:
                for r in snap.execute("SELECT id, stored FROM portal_files ORDER BY id"):
                    p = files / str(r["stored"])
                    if not _safe(r["stored"]) or not p.is_file():
                        missing.append(r["stored"]); continue
                    z.write(p, f"files/{r['stored']}")
                    nfiles += 1; nbytes += p.stat().st_size
            manifest = {"format": FORMAT, "version": 1, "created_at": dt.datetime.now().isoformat(timespec="seconds"),
                        "files": nfiles, "bytes": nbytes, "missing": missing, "tables": counts,
                        "sqlite": sqlite3.sqlite_version, "python": sys.version.split()[0]}
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        snap.close()
        os.replace(tmp_out, out)
    print(f"Zaxira tayyor: {out} — {len(counts)} ta jadval ({sum(counts.values())} qator), {nfiles} ta fayl ({_mb(nbytes)}), "
          f"arxiv hajmi {_mb(out.stat().st_size)}")
    if missing: print(f"Diqqat: {len(missing)} ta fayl diskda topilmadi va zaxiraga kirmadi: {', '.join(map(str, missing[:10]))}")
    return 0

# --------------------------------------------------------------------------------------------- restore
def restore(src: str, force: bool = False) -> int:
    files = _files_dir()
    try: z = zipfile.ZipFile(src)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"Arxiv ochilmadi: {e}"); return 1
    with z:
        names = set(z.namelist())
        try: manifest = json.loads(z.read("manifest.json"))
        except (KeyError, ValueError): manifest = {}
        if manifest.get("format") != FORMAT:
            print("Bu portal zaxira arxivi emas (manifest.json topilmadi yoki formati boshqa)"); return 1
        dumps = {t: json.loads(z.read(f"db/{t}.json")) for t in TABLES if f"db/{t}.json" in names}
        con = _con()
        try:
            have = _tables(con)
            busy = [t for t in TABLES if t != "org_units" and t in have and con.execute(f"SELECT COUNT(*) FROM {_q(t)}").fetchone()[0]]
            if busy and not force:
                print(f"Tiklash to'xtatildi: portal jadvallari bo'sh emas ({', '.join(busy)}). Ustiga yozish uchun --force qo'shing.")
                return 2
            problems, written, skipped = [], 0, 0
            files.mkdir(parents=True, exist_ok=True)
            fd = dumps.get("portal_files")
            if fd:
                ci = {c: i for i, c in enumerate(fd["columns"])}
                for row in fd["rows"]:
                    stored = row[ci["stored"]] if "stored" in ci else None
                    if not _safe(stored):
                        problems.append(f"xavfli fayl nomi: {stored!r}"); continue
                    entry = f"files/{stored}"
                    if entry not in names:
                        problems.append(f"arxivda yo'q: {stored}"); continue
                    data = z.read(entry)
                    want = row[ci["sha256"]] if "sha256" in ci else None
                    if want and hashlib.sha256(data).hexdigest() != want:
                        problems.append(f"sha256 mos emas (yozilmadi): {stored}"); continue
                    dst = files / stored
                    if dst.is_file() and dst.stat().st_size == len(data) and _sha(dst) == hashlib.sha256(data).hexdigest():
                        skipped += 1; continue
                    tmpf = files / f".{stored}.restore"
                    tmpf.write_bytes(data); os.replace(tmpf, dst); written += 1
            nrows = {}
            try:
                for t, d in dumps.items():
                    if t not in have:
                        print(f"  {t}: joriy bazada yo'q — o'tkazib yuborildi"); continue
                    cur = set(_cols(con, t))
                    idx = [(i, c) for i, c in enumerate(d["columns"]) if c in cur]
                    if not idx: continue
                    sql = f"INSERT OR REPLACE INTO {_q(t)}({','.join(_q(c) for _, c in idx)}) VALUES({','.join('?' * len(idx))})"
                    con.executemany(sql, ([_dec(r[i]) for i, _ in idx] for r in d["rows"]))
                    nrows[t] = len(d["rows"])
                con.commit()
            except Exception:
                con.rollback(); raise
        finally:
            con.close()
    print(f"Tiklandi: {len(nrows)} ta jadval ({sum(nrows.values())} qator), {written} ta fayl yozildi, {skipped} tasi allaqachon bor edi "
          f"(zaxira sanasi: {manifest.get('created_at', '?')})")
    for p in problems[:20]: print("  muammo:", p)
    if problems: print(f"Muammolar: {len(problems)} ta")
    return 1 if problems else 0

# --------------------------------------------------------------------------------------------- verify
def verify(fix: bool = False) -> int:
    files = _files_dir()
    con = _con()
    try:
        if "portal_files" not in _tables(con):
            print("portal_files jadvali yo'q — tekshiradigan narsa yo'q"); return 0
        has_sha = "sha256" in _cols(con, "portal_files")
        rows = con.execute(f"SELECT id, stored, size{', sha256' if has_sha else ''} FROM portal_files ORDER BY id").fetchall()
        missing, size_bad, sha_bad, no_sha, fixed = [], [], [], 0, 0
        for r in rows:
            fid, stored, size = r[0], r[1], r[2]
            sha = r[3] if has_sha else None
            p = files / str(stored)
            if not _safe(stored) or not p.is_file():
                missing.append(f"#{fid} {stored}"); continue
            real = p.stat().st_size
            if size is not None and int(size) != real:
                size_bad.append(f"#{fid} {stored} (bazada {size}, diskda {real})"); continue
            if sha:
                if _sha(p) != sha: sha_bad.append(f"#{fid} {stored}")
            elif has_sha:
                if fix:
                    con.execute("UPDATE portal_files SET sha256=? WHERE id=?", (_sha(p), fid)); fixed += 1
                else: no_sha += 1
        if fixed: con.commit()
        known = {str(r[1]) for r in rows}
        orphans = sorted(f.name for f in files.iterdir() if f.is_file() and not f.name.startswith(".") and f.name not in known) if files.is_dir() else []
    finally:
        con.close()
    print(f"Tekshirildi: {len(rows)} ta yozuv, papka: {files}")
    for title, items in (("Diskda yo'q", missing), ("Hajmi mos emas", size_bad), ("sha256 mos emas", sha_bad), ("Yetim fayl (bazada qayd yo'q)", orphans)):
        if items:
            print(f"  {title}: {len(items)} ta")
            for x in items[:10]: print("    -", x)
    if not has_sha: print("  Eslatma: portal_files jadvalida sha256 ustuni yo'q — xesh tekshiruvi o'tkazilmadi")
    if no_sha: print(f"  sha256 hisoblanmagan: {no_sha} ta (--fix bilan yozib qo'yish mumkin)")
    if fixed: print(f"  sha256 yozildi: {fixed} ta")
    bad = len(missing) + len(size_bad) + len(sha_bad) + len(orphans)
    print("Natija: muammo topilmadi" if not bad else f"Natija: {bad} ta muammo")
    return 1 if bad else 0

# --------------------------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.portal_backup", description="Portal fayllari: zaxira, tiklash, tekshiruv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup", help="zaxira ZIP yaratish"); b.add_argument("out")
    r = sub.add_parser("restore", help="ZIP'dan tiklash"); r.add_argument("src"); r.add_argument("--force", action="store_true")
    v = sub.add_parser("verify", help="fayllar yaxlitligini tekshirish"); v.add_argument("--fix", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "backup": return backup(a.out)
    if a.cmd == "restore": return restore(a.src, a.force)
    return verify(a.fix)

if __name__ == "__main__":
    sys.exit(main())
