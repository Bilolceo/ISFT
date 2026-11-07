# Hikvision kameralari — ulanish qo'llanmasi (v0.1, 2026-11-06)

## Nima olinadi
Faqat metama'lumot: odamlar soni (kirdi − chiqdi yoki hudud bo'yicha sanash) va voqea turlari.
Video oqim, kadr va yuz tasvirlari **olinmaydi va saqlanmaydi** — voqealar oqimidagi rasm qismlari o'qiladi-yu, tashlab yuboriladi.

## Kod
| Fayl | Vazifasi |
|---|---|
| `app/hikvision.py` | ISAPI mijozi: Digest, HTTPS, imkoniyatlarni aniqlash (probe), soat farqi, odam sanash, voqealar oqimi parseri, normallashtirish, ogohlantirishlar |
| `app/secret_store.py` | Kamera parollari bazadan alohida (Fernet — `cryptography` o'rnatilsa; aks holda 0600 fayl) |
| `app/occupancy.py` | So'rovchi (60 s), ketma-ket xato → Xizmat markazida nosozlik arizasi (tiklanganda avtomatik yopiladi), voqealar tinglovchilari (backoff bilan qayta ulanish), tungi kirish ogohlantirishi |
| `tools/fake_hikvision.py` | ISAPI emulyatori (ishlab chiqish va test uchun) |
| `tests/test_hikvision.py` | 40+ tekshiruv: parser, Digest, xatolar, probe, sanash, oqim, migratsiya, arizalar, voqealar, tinglovchi |

## Haqiqiy kamerani ulash
1. AT bo'limidan: alohida "Operator" (faqat o'qish) foydalanuvchi, ISAPI yoqilgan, server → kamera VLAN firewall ruxsati, NTP.
2. **Xo'jalik va texnik bo'lim** akkaunti → Auditoriyalar → "+ Hikvision kamerani ulash": xona, IP, port, foydalanuvchi, parol;
   kerak bo'lsa "Voqealar oqimi" va "Ish vaqtidan tashqari kirishni kuzatish".
3. Saqlash bilan birga **probe** ishlaydi: model, proshivka, odam sanash bormi, voqealar bormi, soat farqi. Ogohlantirishlar ro'yxatda ko'rinadi.
4. Pilot: 2–3 xonada kamera soni bilan qo'lda sanashni solishtirish (maqsad: ±2 kishi).

Sozlamalar (muhit o'zgaruvchilari): `JARVIS_CAM_POLL` (60), `JARVIS_CAM_OFFLINE_FAILS` (3), `JARVIS_WORK_HOURS` ("07:30-20:00"),
`JARVIS_CAM_OCC_PATH` (hudud bo'yicha sanash endpointi, modelga bog'liq), `JARVIS_SECRET_KEY` / `data/secrets/master.key`.

## Emulyator bilan sinash
```bash
.venv/bin/python -m uvicorn tools.fake_hikvision:app --host 127.0.0.1 --port 18090   # login: jarvis / Test-Pass-123
.venv/bin/python tests/test_hikvision.py                                             # jonli bazaga tegmaydi
```

## Haqiqiy qurilmada TEKSHIRILMAGAN (emulyator Hikvision hujjatiga yaqin, lekin modellar farq qiladi)
- `counting/capabilities` va `counting/search` javob tuzilmasi aniq modelda.
- Hudud bo'yicha sanash endpointi (`JARVIS_CAM_OCC_PATH`) — modelga qarab tanlanadi.
- alertStream'dagi voqea nomlari (masalan, olomon zichligi voqeasining aniq `eventType` nomi).
- HikCentral Professional OpenAPI ulagichi — hali yozilmagan (institutda HikCentral borligi aniqlangach).

## Xavfsizlik ro'yxati
- [ ] `.venv/bin/pip install cryptography` — parollar shifrlanadi (hozir: bazadan ajratilgan, 0600 fayl, lekin shifrlanmagan).
- [ ] `data/secrets/` zaxira nusxalarga bazadan alohida, cheklangan kirish bilan.
- [ ] Kameralar proshivkasi 2021-09 dan yangi (CVE-2021-36260); Hik-Connect bulut o'chiq; internetga port ochilmagan.
- [ ] Yuz aniqlash ishlatilmaydi (biometrik ma'lumot — O'RQ-547; yurist xulosasisiz yoqilmaydi).
