# Demo ma'lumotlar: manbalar va taxminlar (2026-11-06)

Seed (`app/seed.py`, `PROFILE`) ISFT'ning **ochiq manbalardagi** ko'rsatkichlariga moslangan. **Barcha shaxslar** (talaba, o'qituvchi,
xodim, dekan) — sun'iy. Rahbariyatning haqiqiy ism-familiyalari ataylab ishlatilmagan: sun'iy ma'lumotda ularga "muddati o'tgan topshiriq"
kabi narsalar yozilib qolmasligi uchun.

## Manbadan olinganlar
| Ko'rsatkich | Qiymat | Manba |
|---|---|---|
| Talabalar | 29 203: kunduzgi 8 956 (magistr 370 shu ichida), sirtqi 16 478, masofaviy 3 769 | NQAAE pasporti (26.06.2026) — nqaae.uz/en/higher/303974882 |
| Professor-o'qituvchilar | 255, ilmiy darajalilar 24% | NQAAE (01.05.2026) |
| 2026 qabul | 8 184 talaba bo'ldi | NQAAE |
| Scopus maqolalar | 62 | NQAAE |
| O'quv binolari | 5 ta, 7 500 o'rin; yotoqxona — yo'q | NQAAE |
| Kontrakt | BHM 412 000; kunduzgi xalqaro 50 BHM (20,6 mln), boshqa 46 BHM (18,95 mln), masofaviy 25 BHM (10,3 mln), magistr 65 BHM (26,78 mln); oilaviy chegirma 10% | isft.uz/en/faq |
| Grantlar | yiliga 300 (250 tanlov + 50 ijtimoiy), faqat kunduzgi | isft.uz/en/faq |
| Fakultet, yo'nalishlar | 3 bakalavr fakulteti, 16 yo'nalish | isft.uz/en/about/structure/faculty |
| Kafedralar | 7 ta | isft.uz/en/about/structure/kafedra |
| Magistratura | Davlat moliyaviy nazorati va auditi, Pedagogika, Xorijiy til va adabiyoti | isft.uz/en/applicants/master |
| Qabul davri | 1 iyun – 30 sentabr | mentalaba.uz |

## TAXMIN (manbada yo'q — institut bilan aniqlashtiriladi)
- Sirtqi ta'lim narxi (masofaviy bilan teng deb olingan).
- Yo'nalishlar bo'yicha talabalar taqsimoti, kurslar ulushi, guruh hajmi.
- Ariza berganlar soni (~13 500), byudjet moddalari, 180 nafar boshqa xodim, bino nomlari va xonalar ro'yxati.
- **Hamkor universitetlar**: saytda ro'yxat e'lon qilinmagan — "Hamkor OTM — <davlat> (namuna)" deb ko'rsatilgan, haqiqiy nomlar ishlatilmagan.
- Samarqand filiali alohida modellashtirilmagan (NQAAE raqamlari umumiy bo'lishi mumkin).
- Baholar, davomat, kontrakt to'lovlari, murojaatlar va "hikoyalar" (2-kurs pasayishi, LMS uzilishi) — sun'iy.

## Rahbarlar ro'yxati (2026-11-07)
Rektor, prorektorlar, bo'lim boshliqlari va kafedra mudirlarining ism-shariflari institut bergan "Lavozim ism" ro'yxatidan olingan
(`app/seed.py`: `LEADERS`, `DEPT_HEADS`, `UNIT_HEADS`). Dekanlar va boshqa barcha xodim/talaba/o'qituvchilar — sun'iy.
- Prorektorlar 4 nafar (ro'yxat bo'yicha); 2024 tuzilmasidagi Umumiy masalalar, Xalqaro aloqalar, Raqamlashtirish prorektorlari olib tashlandi.
- Akademik faoliyat va registrator departamenti: Akademik faoliyatni muvofiqlashtirish bo'limi + Registrator ofisi (departament rahbari ko'rsatilmagan).
- "Fundamental iqtisodiy fanlar" kafedrasi — fakultetga biriktirilmagan; Statistika, Mikro/Makroiqtisodiyot, Ekonometrika fanlarini o'qitadi (TAXMIN).
