# Testlar (jonli server bilan)

Server ishlab turganda (`./run.sh`, :8000) ishga tushiriladi. Testlar bazani o'zgartiradi — keyin qayta seed qiling.

```bash
.venv/bin/python tests/test_regressiya.py          # umumiy RBAC, panel, hujjatlar
.venv/bin/python tests/test_majlis_qarori.py       # kotib → bo'limlar → rektor oqimi
.venv/bin/python tests/test_talabalar_markazi.py   # qoidalar dvigateli, call-markaz, tyutor, otrabotka
.venv/bin/python -m app.seed                       # demo holatini tiklash (server qayta ishga tushiriladi)
```
