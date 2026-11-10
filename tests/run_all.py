#!/usr/bin/env python3
"""Barcha testlarni toza, vaqtinchalik muhitda ishga tushirish (lokal va CI uchun bir xil).

  1) vaqtinchalik data katalogi  2) `python -m app.seed`  3) uvicorn bo'sh portda  4) /healthz kutish
  5) tests/test_*.py — o'qiydigan to'plamlar avval, bazani ko'p o'zgartiradiganlari oxirida  6) natijalar jadvali
  7) server to'xtatiladi; biror to'plam yiqilsa chiqish kodi 1.

Misollar:
  python tests/run_all.py                         # hammasi
  python tests/run_all.py --only reyting,flows    # tanlanganlari (nom: test_ va .py siz)
  python tests/run_all.py --keep                  # vaqtinchalik katalog o'chirilmaydi (loglar uchun)
  python tests/run_all.py --data-dir /tmp/isft    # shu katalogda (bo'sh bo'lsa seed qilinadi; --reseed — majburan)
  python tests/run_all.py --fake-today 2026-11-04 # "bugun"ni qotirish (ISFT_CORE_FAKE_TODAY)

Muhit: ISFT_CORE_DATA_DIR / ISFT_CORE_DB / ISFT_CORE_FILES_DIR / ISFT_CORE_STAFFABS_DIR / ISFT_CORE_SECRETS_DIR — server, seed va
testlarga bir xil beriladi; ISFT_TEST_URL — testlar uchun server manzili. LLM (Ollama) standart holda o'chiriladi (CI bilan bir xil,
natija deterministik); --llm bilan mavjud sozlama qoldiriladi.
"""
import argparse, os, shutil, signal, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
PY = sys.executable

# Tartib: avval faqat o'qiydigan/o'zini tozalaydigan to'plamlar, keyin bazani ko'proq o'zgartiradiganlar.
# talabalar_markazi — oxirida: qoidalar dvigatelini (OPS.evaluate) qayta ishlatadi va demo holatini o'zgartiradi.
ORDER = ["ruxsatlar", "regressiya", "registrar", "reyting", "flows", "portal", "mywork", "topshiriq_bolimlar", "topshiriq_vakolat",
         "syllabus", "orders", "staffabs", "accounts", "majlis_qarori", "facecam", "hikvision"]
LAST = ["talabalar_markazi"]
SUITE_TIMEOUT = int(os.getenv("ISFT_TEST_SUITE_TIMEOUT", "900"))


def discover():
    found = sorted(p.stem[5:] for p in TESTS.glob("test_*.py"))
    known = [s for s in ORDER if s in found]
    tail = [s for s in LAST if s in found]
    extra = [s for s in found if s not in ORDER and s not in LAST]   # yangi to'plamlar — ma'lum tartibdan keyin, LAST'dan oldin
    return known + extra + tail


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_health(url, proc, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def env_for(data: Path, args):
    e = dict(os.environ)
    e.update(ISFT_CORE_DATA_DIR=str(data), ISFT_CORE_DB=str(data / "jarvis.db"), ISFT_CORE_FILES_DIR=str(data / "portal_files"),
             ISFT_CORE_STAFFABS_DIR=str(data / "staffabs_files"), ISFT_CORE_SECRETS_DIR=str(data / "secrets"),
             PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    e.setdefault("ISFT_CORE_TZ", "Asia/Tashkent")
    e.pop("TELEGRAM_BOT_TOKEN", None)            # testda bot ishga tushmasin
    for k in ("ISFT_CORE_DEMO_TOOLS", "ISFT_CORE_PRES_FAKE", "ISFT_CORE_PRES_DAILY", "ISFT_CORE_CHECK_FAKE", "ISFT_CORE_CHECK_DAILY", "ISFT_CORE_CHECK_SYNC"):   # testlar standart (prod) sozlamani kutadi
        e.pop(k, None)
    if not args.llm:
        e["ISFT_CORE_LLM_URL"] = "http://127.0.0.1:9"   # LLM yo'q — qoidaviy zaxira javoblar (CI bilan bir xil)
        e.pop("ISFT_CORE_LLM_API", None); e.pop("ISFT_CORE_LLM_KEY", None)
        e.pop("ANTHROPIC_API_KEY", None)                # Taqdimot: Claude chaqirilmaydi — AI siz (shablon) rejim sinovdan o'tadi
    if args.fake_today:
        e["ISFT_CORE_FAKE_TODAY"] = args.fake_today
    return e


def tail(text, n=25):
    lines = text.rstrip().splitlines()
    return "\n".join(lines[-n:])


def main():
    ap = argparse.ArgumentParser(description="ISFT Core: barcha testlar vaqtinchalik muhitda")
    ap.add_argument("--only", help="vergul bilan: reyting,flows (test_ va .py siz)")
    ap.add_argument("--skip", help="vergul bilan: chiqarib tashlanadigan to'plamlar")
    ap.add_argument("--data-dir", help="vaqtinchalik katalog o'rniga shu katalog (o'chirilmaydi)")
    ap.add_argument("--reseed", action="store_true", help="--data-dir da baza bo'lsa ham qayta seed qilish")
    ap.add_argument("--keep", action="store_true", help="vaqtinchalik katalog va loglarni o'chirmaslik")
    ap.add_argument("--port", type=int, default=0, help="server porti (standart: bo'sh port)")
    ap.add_argument("--fake-today", help="ISFT_CORE_FAKE_TODAY=YYYY-MM-DD (seed, server, testlar uchun)")
    ap.add_argument("--llm", action="store_true", help="LLM sozlamasini o'chirmaslik (Ollama ishlayotgan bo'lsa ishlatiladi)")
    ap.add_argument("--list", action="store_true", help="to'plamlar ro'yxati va chiqish")
    args = ap.parse_args()

    suites = discover()
    if args.list:
        print("\n".join(suites)); return 0
    if args.only:
        want = [s.strip().removeprefix("test_").removesuffix(".py") for s in args.only.split(",") if s.strip()]
        bad = [s for s in want if s not in suites]
        if bad:
            print("Noma'lum to'plam:", ", ".join(bad), "· mavjud:", ", ".join(suites)); return 2
        suites = [s for s in suites if s in want]
    if args.skip:
        sk = {s.strip().removeprefix("test_").removesuffix(".py") for s in args.skip.split(",")}
        suites = [s for s in suites if s not in sk]

    own_tmp = not args.data_dir
    data = Path(args.data_dir).resolve() if args.data_dir else Path(tempfile.mkdtemp(prefix="isft-test-"))
    data.mkdir(parents=True, exist_ok=True)
    logs = data / "_testlogs"; logs.mkdir(exist_ok=True)
    env = env_for(data, args)
    T0 = time.time()
    print(f"Ma'lumotlar: {data}\nPython: {PY}")

    # --- seed ---
    if args.reseed or not (data / "jarvis.db").exists():
        print("Seed: python -m app.seed ...", flush=True)
        t = time.time()
        r = subprocess.run([PY, "-m", "app.seed"], cwd=ROOT, env=env, capture_output=True, text=True)
        (logs / "seed.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        if r.returncode != 0:
            print(tail(r.stdout + r.stderr, 40)); print("SEED XATO"); return 1
        print(f"Seed tayyor: {time.time() - t:.0f} s", flush=True)

    # --- server ---
    port = args.port or free_port()
    url = f"http://127.0.0.1:{port}"
    env["ISFT_TEST_URL"] = url
    slog = open(logs / "server.log", "w", encoding="utf-8")
    srv = subprocess.Popen([PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env,
                           stdout=slog, stderr=subprocess.STDOUT, start_new_session=True)
    results = []
    try:
        if not wait_health(url, srv, 180):
            slog.flush(); print(tail((logs / "server.log").read_text(encoding="utf-8"), 40)); print("SERVER ISHGA TUSHMADI"); return 1
        print(f"Server: {url}\n", flush=True)
        for s in suites:
            t = time.time()
            try:
                r = subprocess.run([PY, str(TESTS / f"test_{s}.py")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=SUITE_TIMEOUT)
                out, code = r.stdout + r.stderr, r.returncode
            except subprocess.TimeoutExpired as e:
                out = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + f"\nTIMEOUT {SUITE_TIMEOUT} s"
                code = -1
            (logs / f"test_{s}.log").write_text(out, encoding="utf-8")
            n_ok = sum(1 for ln in out.splitlines() if ln.lstrip().startswith("✓"))
            n_bad = sum(1 for ln in out.splitlines() if ln.lstrip().startswith("✗"))
            passed = code == 0 and n_bad == 0
            results.append((s, passed, n_ok, n_bad, time.time() - t, code))
            print(f"{'OK  ' if passed else 'XATO'} {s:<22} {n_ok:>4} ✓ {n_bad:>3} ✗  {time.time() - t:6.1f} s", flush=True)
            if not passed:
                print("  " + tail(out).replace("\n", "\n  "), flush=True)
            if srv.poll() is not None:
                print("Server to'xtab qoldi!"); break
    finally:
        if srv.poll() is None:
            try: os.killpg(srv.pid, signal.SIGTERM)
            except Exception: srv.terminate()
            try: srv.wait(15)
            except subprocess.TimeoutExpired:
                try: os.killpg(srv.pid, signal.SIGKILL)
                except Exception: srv.kill()
        slog.close()

    # --- jadval ---
    fails = [r for r in results if not r[1]]
    skipped = [s for s in suites if s not in {r[0] for r in results}]
    w = max([len(r[0]) for r in results] + [8])
    print("\n" + "=" * (w + 40))
    print(f"{'To`plam':<{w}}  Natija  {'✓':>5}  {'✗':>3}  {'Vaqt':>8}")
    print("-" * (w + 40))
    for s, ok, n_ok, n_bad, sec, code in results:
        print(f"{s:<{w}}  {'OK' if ok else 'XATO':<6}  {n_ok:>5}  {n_bad:>3}  {sec:7.1f}s" + ("" if ok else f"  (kod {code})"))
    for s in skipped:
        print(f"{s:<{w}}  {'—':<6}  ishga tushmadi")
    print("-" * (w + 40))
    total = time.time() - T0
    print(f"Jami: {len(results) - len(fails)}/{len(suites)} to'plam o'tdi · {sum(r[2] for r in results)} tekshiruv · {total / 60:.1f} daqiqa")
    if fails or skipped:
        print(f"Loglar: {logs}")
    if own_tmp and not args.keep and not fails and not skipped:
        shutil.rmtree(data, ignore_errors=True)
    elif own_tmp:
        print(f"Vaqtinchalik katalog saqlandi: {data}")
    return 1 if fails or skipped else 0


if __name__ == "__main__":
    sys.exit(main())
