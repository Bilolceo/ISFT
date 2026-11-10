"""Demo (sun'iy) ma'lumotlar generatori. Haqiqiy shaxslarga aloqasi yo'q.
Ishga tushirish: python -m app.seed
Ichiga rektorga ko'rsatish uchun ataylab "hikoyalar" joylangan:
  * Xalqaro iqtisodiyot va moliya fakulteti 2-kursida o'zlashtirish keskin pasaygan
Tuzilma: ISFT rasmiy tashkiliy tuzilmasi (2024, 04.09.2024 tasdiqlangan) — fakultet, kafedra va yo'nalish nomlari.
  * Kontrakt qarzdorligi ~17%, ayrim guruhlarda yuqori
  * Kengash topshiriqlaridan 3 tasi muddati o'tgan
  * 2 ta xalqaro shartnoma 60 kun ichida tugaydi
  * Kommunal xarajatlar rejadan oshgan
"""
import random, datetime as dt
from . import db, academic_rules as AR
from .academic_rules import OTHER_UNIT_HEADS

R = random.Random(42)
TODAY = dt.date(2026, 11, 4)

MALE = ["Aziz","Bekzod","Jasur","Sardor","Otabek","Shoxrux","Doniyor","Javohir","Islom","Sherzod","Ulug'bek","Akmal",
        "Bobur","Diyorbek","Firdavs","Abdulloh","Muhammadali","Asadbek","Temur","Nodirbek","Sanjar","Elyor","Rustam","Kamron"]
FEMALE = ["Madina","Dilnoza","Sevara","Nilufar","Gulnoza","Zarina","Shahzoda","Malika","Mohinur","Kamola","Feruza","Nigora",
          "Sabina","Diyora","Munisa","Odina","Laylo","Mubina","Charos","Hilola","Barno","Rayhona","Sitora","Zilola"]
SURN = ["Karimov","Rahimov","Tursunov","Yusupov","Abdullayev","Ismoilov","Qodirov","Nazarov","Ergashev","Sobirov","Xolmatov",
        "Mirzayev","Aliyev","Hasanov","Usmonov","Jo'rayev","Saidov","Normatov","Toshpo'latov","Rashidov","Hamroyev","Bakirov"]
PATR_M = ["Anvar","Baxtiyor","Shavkat","Ravshan","Ilhom","Farhod","Komil","Murod","Odil","Erkin"]
REGIONS = ["Toshkent sh.","Toshkent vil.","Samarqand","Farg'ona","Andijon","Namangan","Qashqadaryo","Surxondaryo","Buxoro","Xorazm","Jizzax","Sirdaryo","Navoiy","Qoraqalpog'iston"]

def person(gender=None):
    g = gender or R.choice("MF")
    s = R.choice(SURN)
    if g == "M":
        return f"{s} {R.choice(MALE)} {R.choice(PATR_M)} o'g'li", g
    return f"{s}a {R.choice(FEMALE)} {R.choice(PATR_M)} qizi", g

def short(full):
    p = full.split()
    return f"{p[0]} {p[1][0]}."

# =====================================================================================================
# ISFT HAQIQIY PROFILI — ochiq manbalardan (2026-11-06 da o'qilgan). Shaxslar (talaba, o'qituvchi, xodim) — SUN'IY.
#   NQAAE pasporti: https://nqaae.uz/en/higher/303974882 (talabalar 26.06.2026, xodimlar 01.05.2026)
#   Narxlar va grantlar: https://isft.uz/en/faq ;  fakultet/yo'nalishlar: https://isft.uz/en/about/structure/faculty
#   Kafedralar: ISFT tashkiliy tuzilmasi (04.09.2024 tasdiqlangan)
#   Rahbarlar (rektor, prorektorlar, bo'limlar, kafedra mudirlari): institut bergan "Lavozim ism" ro'yxati (2026-11-07)
# "TAXMIN" deb belgilanganlar manbada yo'q — demo uchun qo'yilgan, institut bilan aniqlashtiriladi.
# =====================================================================================================
PROFILE = {
    # NQAAE: kunduzgi 8 956 / sirtqi 16 478 / masofaviy 3 769 = 29 203 (bakalavr 28 833 + magistr 370) — magistrlar kunduzgi ichida
    "students_by_form": {"kunduzgi": 8956 - 370, "sirtqi": 16478, "masofaviy": 3769},
    "master_students": 370, "teachers": 255, "degree_share": 0.24, "founded": 2016, "accepted_2026": 8184,
    "scopus_total": 62, "buildings": 5, "seats": 7500, "dormitories": 0, "grants_per_year": 300, "grants_social": 50,
    "bcv": 412_000,   # bazaviy hisoblash miqdori (isft.uz/en/faq)
    "tuition_bcv": {"kunduzgi_xalqaro": 50, "kunduzgi": 46, "masofaviy": 25, "magistr": 65,
                    "sirtqi": 25},   # sirtqi narxi saytda ko'rsatilmagan — TAXMIN: masofaviy bilan teng
    "family_discount": 0.10,        # oilada 2+ talaba — har biriga 10%
    "other_staff": 180,             # TAXMIN: professor-o'qituvchilardan tashqari xodimlar
}
FORM_GROUP = {"kunduzgi": ("", 25), "sirtqi": ("S", 32), "masofaviy": ("M", 40)}   # guruh nomi qo'shimchasi, o'rtacha hajmi (TAXMIN)
COURSE_W = [0.29, 0.27, 0.23, 0.21]   # 1-kurs ≈ 2026 qabul (8 184) / jami — TAXMIN taqsimot

# Fakultet → kafedra → bakalavr yo'nalishlari (saytdagi joriy ro'yxat; kafedralar — 2024 tuzilmasi). Vazn — mashhurlik (TAXMIN).
# Tartib muhim: 2-fakultet — "moliya" hikoyasi (2-kurs pasayishi), 4-kafedra — demo kafedra mudiri akkaunti.
FACULTIES = [
    ("Iqtisodiyot va axborot texnologiyalari", [
        ("Iqtisodiyot va kompyuter injiniringi", [("Iqtisodiyot", 1.4), ("Bank ishi va audit", 1.2), ("Menejment", 1.0), ("Marketing", 0.8),
                                                 ("Axborot tizimlari va texnologiyalari", 1.0), ("Axborot xavfsizligi", 0.6)])]),
    ("Xalqaro iqtisodiyot va moliya", [   # "xalqaro yo'nalishlar" — 50 BHM
        ("Biznes boshqaruvi", [("Biznes va menejment", 1.0)]),
        ("Menejment", [("Moliya sohasida boshqaruv", 1.0)]),
        ("Buxgalteriya hisobi", [("Buxgalteriya hisobi va moliya", 1.1)])]),
    ("Ijtimoiy-gumanitar fanlar va tillar", [
        # taqdimot (4-slayd): pedagogik yo'nalishlar — Psixologiya va pedagogika kafedrasida; Xalqaro munosabatlar va
        # mahalliy yo'nalishlarda 1-kursning ijtimoiy-gumanitar fanlari — Gumanitar va tabiiy fanlar kafedrasida
        ("Psixologiya va pedagogika", [("Pedagogika", 1.3), ("Psixologiya (faoliyat turlari bo'yicha)", 1.3), ("Boshlang'ich ta'lim", 1.4),
                                       ("Maktabgacha ta'lim", 1.2), ("Pedagogika va psixologiya", 0.6)]),
        ("Gumanitar va tabiiy fanlar", [("Xalqaro munosabatlar", 0.7)]),
        ("Filologiya va tillarni o'qitish", [("Xorijiy til va adabiyoti", 1.2), ("Filologiya va tillarni o'qitish (ingliz tili)", 1.0)])]),
]
INTL_FACULTY = 2
# Fakultetga biriktirilmagan (institut miqyosidagi) kafedra: o'z yo'nalishi yo'q, guruhlari yo'q. Ro'yxatda fakultet ko'rsatilmagan.
INSTITUTE_DEPTS = ["Fundamental iqtisodiy fanlar"]
FUND_SUBJECTS = {"Makroiqtisodiyot", "Mikroiqtisodiyot", "Ekonometrika", "Statistika"}   # TAXMIN: shu kafedra o'qitadigan fanlar
# Taqdimot (4-slayd): mahalliy yo'nalishlarda 1-kursning ijtimoiy-gumanitar fanlarini Gumanitar va tabiiy fanlar kafedrasi o'qitadi
HUM_DEPT, HUM_SUBJECT = "Gumanitar va tabiiy fanlar", "O'zbekiston tarixi"   # fan nomi — TAXMIN (namuna)
def subjects_for(key, course, level, fi):
    return SUBJECTS[key] + ([HUM_SUBJECT] if course == 1 and level == "bakalavr" and fi != INTL_FACULTY else [])
# Ism-shariflar — institut ro'yxatidan (tartib: familiya, ism, otasining ismi).
# Institutda dekan lavozimi yo'q (Yevropa modeli): fakultet darajasidagi vazifalarni Registrator ofisi boshlig'i bajaradi.
LEADERS = {
    "rektor": "G'ulomov Ibroxim Rustam o'g'li",
    "prorektor_yoshlar": "Narkuziyeva Zulxumor Meliboyevna",
    "prorektor_oquv": "Temirov Anvar Amir o'g'li",
    "prorektor_ilmiy": "Azizov Tuxtamish A'zamovich",
    "prorektor_moliya": "Sharipov Asliddin Fazlitdin o'g'li",
}
DEPT_HEADS = {
    "Iqtisodiyot va kompyuter injiniringi": "Mavlonov Nurali Sherali o'g'li",
    "Biznes boshqaruvi": "Uktamov Xusniddin Faxriddinovich",
    "Menejment": "Usmonov Adxamjon A'zamjonovich",
    "Buxgalteriya hisobi": "Xalilov Sherzod Axmatovich",
    "Psixologiya va pedagogika": "Abdusamatov Xasanboy Usmonjon o'g'li",
    "Gumanitar va tabiiy fanlar": "Xidirov Mustafo Toyirqulovich",
    "Filologiya va tillarni o'qitish": "Najmitdinova Gulnozaxon Baxtiyorovna",
    "Fundamental iqtisodiy fanlar": "Qarshiyev Daniyar Eshpulatovich",
}
# Bo'limlar rahbarlari (institut ro'yxati, "Lavozim ism" hujjati). Avvalgi "Akademik faoliyat va registrator departamenti"
# ikkiga bo'lingan: Registrator ofisi va Akademik faoliyatni boshqarish bo'limi.
UNIT_HEADS = {
    "Registrator ofisi": "Baratov Ma'rufbek Baxodir o'g'li",
    "Akademik faoliyatni boshqarish bo'limi": "Bo'tayev Xurshid",
    "Imtihon bo'limi": "Zafarbek Ilkhamovich",
    "Magistratura bo'limi": "Manukyan Feruza",
    "Ilmiy tadqiqotlar, innovatsiyalar va ilmiy-pedagogik kadrlar tayyorlash bo'limi": "Bahodirova Gulnoz",
    "Amaliyot bo'limi": "Suhrob Bahodirovich",
}
# Magistratura (isft.uz/en/applicants/master): dastur → kafedra raqami (FACULTIES tartibida, 1 dan)
MASTERS = [("Davlat moliyaviy nazorati va auditi", 4), ("Pedagogika", 5), ("Xorijiy til va adabiyoti", 7)]
GROUP_CODE = {"Iqtisodiyot": "IQT", "Bank ishi va audit": "BIA", "Menejment": "MEN", "Marketing": "MRK", "Axborot tizimlari va texnologiyalari": "ATT",
              "Axborot xavfsizligi": "AXV", "Xalqaro munosabatlar": "XM", "Biznes va menejment": "BM", "Moliya sohasida boshqaruv": "MSB",
              "Buxgalteriya hisobi va moliya": "BHM", "Pedagogika": "PED", "Psixologiya (faoliyat turlari bo'yicha)": "PSX", "Pedagogika va psixologiya": "PP", "Boshlang'ich ta'lim": "BT", "Maktabgacha ta'lim": "MT",
              "Xorijiy til va adabiyoti": "XTA", "Filologiya va tillarni o'qitish (ingliz tili)": "FIL",
              "Davlat moliyaviy nazorati va auditi": "MAG-DMN", }
SUBJECTS = {
    "Iqtisodiyot": ["Makroiqtisodiyot","Ekonometrika","Statistika","Iqtisodiy tarix","Ingliz tili"],
    "Bank ishi va audit": ["Bank ishi","Pul va kredit","Risk menejmenti","Audit","Ingliz tili"],
    "Menejment": ["Menejment asoslari","Tashkiliy xulq","Statistika","Loyiha boshqaruvi","Ingliz tili"],
    "Marketing": ["Marketing asoslari","Iste'molchi xulqi","Raqamli marketing","Statistika","Ingliz tili"],
    "Axborot tizimlari va texnologiyalari": ["Dasturlash asoslari","Ma'lumotlar bazasi","Tarmoqlar","Oliy matematika","Ingliz tili"],
    "Axborot xavfsizligi": ["Kriptografiya asoslari","Tarmoq xavfsizligi","Operatsion tizimlar","Oliy matematika","Ingliz tili"],
    "Xalqaro munosabatlar": ["Xalqaro munosabatlar nazariyasi","Diplomatiya tarixi","Xalqaro huquq","Mikroiqtisodiyot","Ingliz tili"],
    "Biznes va menejment": ["Menejment asoslari","Biznesni rejalashtirish","Marketing","Statistika","Ingliz tili"],
    "Moliya sohasida boshqaruv": ["Moliya","Korporativ moliya","FinTech asoslari","Moliyaviy matematika","Ingliz tili"],
    "Buxgalteriya hisobi va moliya": ["Buxgalteriya hisobi","Korporativ moliya","Moliyaviy matematika","Moliyaviy hisobot (IFRS)","Ingliz tili"],
    "Pedagogika": ["Umumiy pedagogika","Didaktika","Pedagogik mahorat","Ta'lim texnologiyalari","Ingliz tili"],
    "Psixologiya (faoliyat turlari bo'yicha)": ["Umumiy psixologiya","Ijtimoiy psixologiya","Yosh psixologiyasi","Statistika","Ingliz tili"],
    "Pedagogika va psixologiya": ["Pedagogika nazariyasi","Pedagogik psixologiya","Tarbiya metodikasi","Psixodiagnostika","Ingliz tili"],
    "Boshlang'ich ta'lim": ["Boshlang'ich ta'lim metodikasi","Ona tili","Matematika o'qitish metodikasi","Pedagogika","Ingliz tili"],
    "Maktabgacha ta'lim": ["Maktabgacha pedagogika","Bolalar psixologiyasi","Nutq o'stirish","Pedagogika","Ingliz tili"],
    "Xorijiy til va adabiyoti": ["Amaliy grammatika","Fonetika","Adabiyot tarixi","Tarjima nazariyasi","Ikkinchi xorijiy til"],
    "Filologiya va tillarni o'qitish (ingliz tili)": ["Amaliy grammatika","Til o'qitish metodikasi","Leksikologiya","Tarjima amaliyoti","Akademik yozuv"],
    "Davlat moliyaviy nazorati va auditi": ["Davlat moliyaviy nazorati","Davlat auditi standartlari","Byudjet tizimi","Ilmiy tadqiqot metodologiyasi"],
    "Pedagogika (magistratura)": ["Pedagogik tadqiqot metodlari","Oliy ta'lim pedagogikasi","Ta'lim menejmenti","Ilmiy tadqiqot metodologiyasi"],
    "Xorijiy til va adabiyoti (magistratura)": ["Qiyosiy tilshunoslik","Adabiy tahlil","Diskurs tahlili","Ilmiy tadqiqot metodologiyasi"],
}
# =====================================================================================================
# O'QUV REJASI (curriculum): har yo'nalish × daraja uchun semestrlar bo'yicha TURLI fanlar va kreditlar (har semestr 30 kredit,
# bakalavr 8 semestr = 240, magistr 4 semestr = 120). Yuqoridagi SUBJECTS — yo'nalishning tayanch fanlari (o'quv dasturlari moduli
# katalogidagi nomlar): ular toq (kuzgi) semestrlarga joylanadi — joriy semestrda (1, 3, 5, 7) o'qitiladi. Qolgan o'rinlar —
# yo'nalish oilasi fanlari va yo'nalishga xos qo'shimcha fanlar. TAXMIN (demo): institutning haqiqiy o'quv rejasi emas.
# =====================================================================================================
FAMILY = {"Iqtisodiyot": "econ", "Bank ishi va audit": "econ", "Menejment": "econ", "Marketing": "econ", "Biznes va menejment": "econ",
          "Moliya sohasida boshqaruv": "econ", "Buxgalteriya hisobi va moliya": "econ", "Axborot tizimlari va texnologiyalari": "it",
          "Axborot xavfsizligi": "it", "Xalqaro munosabatlar": "xm", "Pedagogika": "ped", "Psixologiya (faoliyat turlari bo'yicha)": "ped",
          "Pedagogika va psixologiya": "ped", "Boshlang'ich ta'lim": "ped", "Maktabgacha ta'lim": "ped",
          "Xorijiy til va adabiyoti": "lang", "Filologiya va tillarni o'qitish (ingliz tili)": "lang"}
POOL = {
    "econ": ["Oliy matematika", "Iqtisodiyot nazariyasi", "Informatika va axborot texnologiyalari", "Mikroiqtisodiyot", "Moliya",
             "Buxgalteriya hisobi asoslari", "Menejment nazariyasi", "Marketing nazariyasi", "Soliqlar va soliqqa tortish", "Xalqaro iqtisodiyot",
             "Investitsiyalar", "Iqtisodiy tahlil", "Biznes huquqi", "Raqamli iqtisodiyot", "Tadbirkorlik asoslari", "Moliyaviy bozorlar",
             "Sug'urta ishi", "Mehnat iqtisodiyoti", "Davlat moliyasi", "Logistika", "Innovatsion iqtisodiyot", "Biznes etikasi",
             "Korxona iqtisodiyoti", "Narx siyosati", "Iqtisodiy xavfsizlik", "Yashil iqtisodiyot", "Elektron tijorat"],
    "it": ["Oliy matematika", "Diskret matematika", "Informatika asoslari", "Algoritmlar va ma'lumotlar tuzilmasi", "Obyektga yo'naltirilgan dasturlash",
           "Kompyuter arxitekturasi", "Ehtimollar nazariyasi va statistika", "Mobil ilovalar", "Sun'iy intellekt asoslari", "Bulutli texnologiyalar",
           "Tizimli tahlil", "IT loyihalarini boshqarish", "Kompyuter grafikasi", "Raqamli iqtisodiyot", "IT huquqi va etikasi",
           "Parallel hisoblash", "Inson-kompyuter interfeysi", "Ma'lumotlarni vizuallashtirish", "Mashinali o'qitish", "Tarmoq dasturlash",
           "Axborot tizimlari arxitekturasi", "Dasturiy ta'minot sifati", "Raqamli signallarni qayta ishlash", "Blokcheyn texnologiyalari",
           "DevOps asoslari", "Kiberfizik tizimlar", "Raqamli transformatsiya"],
    "ped": ["Pedagogika tarixi", "Psixologiya asoslari", "Anatomiya va fiziologiya", "Informatika va axborot texnologiyalari", "Inklyuziv ta'lim asoslari",
            "Ta'lim texnologiyalari", "Tarbiyaviy ishlar metodikasi", "Maxsus pedagogika", "Kasbiy etika", "Ta'limda raqamli texnologiyalar",
            "Qiyosiy pedagogika", "Ijtimoiy pedagogika", "Pedagogik tadqiqot metodlari", "Ta'lim sifatini baholash", "Valeologiya",
            "Ekologik tarbiya", "Ma'naviyat asoslari", "Pedagogik mahorat asoslari", "Rivojlanish psixologiyasi", "Ta'lim huquqi",
            "Media savodxonlik", "Oila psixologiyasi", "Bolalar huquqlari", "Ta'limda STEAM yondashuvi", "Pedagogik amaliyot", "Mentorlik asoslari",
            "Umumiy didaktika"],
    "lang": ["Kirish tilshunosligi", "Nutq amaliyoti", "Yozuv amaliyoti", "Tinglab tushunish", "Lotin tili", "Matn tahlili",
             "Diskurs tahlili", "Ingliz adabiyoti", "Amerika adabiyoti", "Sotsiolingvistika", "Psixolingvistika", "Kognitiv tilshunoslik",
             "Biznes ingliz tili", "Qiyosiy tipologiya", "Pragmatika", "Leksikografiya", "Semantika", "Til o'qitishda baholash",
             "Ingliz tili tarixi", "Badiiy tarjima", "Kasbiy muloqot", "Ommaviy nutq", "Media matnlari tahlili", "Til korpuslari",
             "Madaniyatlararo muloqot", "Ikkinchi xorijiy til (amaliy kurs)", "Ilmiy matn tarjimasi"],
    "xm": ["Siyosatshunoslik", "Jahon tarixi", "Xalqaro munosabatlar tarixi", "Davlat va huquq nazariyasi", "Jahon iqtisodiyoti",
           "Konstitutsiyaviy huquq", "Xalqaro xavfsizlik", "Markaziy Osiyo xalqaro munosabatlarda", "Xalqaro iqtisodiy munosabatlar",
           "Mojarolarni hal qilish", "Xalqaro jurnalistika", "Global boshqaruv", "Xalqaro migratsiya", "Konsullik xizmati",
           "Ikkinchi xorijiy til", "Ommaviy diplomatiya", "Siyosiy tahlil usullari", "Xalqaro integratsiya", "Energetika diplomatiyasi",
           "Xalqaro ekologik huquq", "Inson huquqlari", "Xalqaro savdo huquqi", "Diplomatik yozishmalar", "Mintaqashunoslik", "Xalqaro muzokaralar",
           "Raqamli diplomatiya", "Xalqaro biznes muhiti"],
}
EXTRA = {
    "Iqtisodiyot": ["Iqtisodiy siyosat", "Mintaqaviy iqtisodiyot", "Iqtisodiy prognozlash", "Institutsional iqtisodiyot"],
    "Bank ishi va audit": ["Bank operatsiyalari", "Kredit tahlili", "Xalqaro bank ishi", "Ichki audit"],
    "Menejment": ["Inson resurslarini boshqarish", "Operatsion menejment", "Strategik menejment", "Boshqaruv qarorlari"],
    "Marketing": ["Marketing tadqiqotlari", "Brend menejmenti", "Reklama va PR", "Savdo menejmenti"],
    "Axborot tizimlari va texnologiyalari": ["Veb-dasturlash", "Dasturiy injiniring", "Ma'lumotlar tahlili", "Axborot tizimlarini loyihalash"],
    "Axborot xavfsizligi": ["Kriptografik protokollar", "Kompyuter kriminalistikasi", "Xavfsizlik auditi", "Zararli dasturlar tahlili"],
    "Xalqaro munosabatlar": ["Xalqaro tashkilotlar", "Geosiyosat", "Tashqi siyosat tahlili", "Diplomatik protokol"],
    "Biznes va menejment": ["Biznes strategiyasi", "Xalqaro biznes", "Korporativ boshqaruv", "Loyiha boshqaruvi"],
    "Moliya sohasida boshqaruv": ["Moliyaviy menejment", "Investitsion tahlil", "Moliyaviy risklar", "Bank ishi"],
    "Buxgalteriya hisobi va moliya": ["Boshqaruv hisobi", "Soliq hisobi", "Moliyaviy tahlil", "Audit"],
    "Pedagogika": ["Pedagogik texnologiyalar", "Tarbiya nazariyasi", "Ta'lim menejmenti", "Pedagogik diagnostika"],
    "Psixologiya (faoliyat turlari bo'yicha)": ["Psixodiagnostika", "Klinik psixologiya asoslari", "Psixologik maslahat", "Mehnat psixologiyasi"],
    "Pedagogika va psixologiya": ["Ijtimoiy psixologiya", "Pedagogik konfliktologiya", "Psixologik-pedagogik korreksiya", "Oila pedagogikasi"],
    "Boshlang'ich ta'lim": ["O'qish savodxonligi metodikasi", "Tabiatshunoslik o'qitish metodikasi", "Boshlang'ich sinflarda tarbiya", "Inklyuziv ta'lim"],
    "Maktabgacha ta'lim": ["Bolalar adabiyoti", "Maktabgacha ta'lim metodikasi", "O'yin pedagogikasi", "Maktabgacha yoshda jismoniy tarbiya"],
    "Xorijiy til va adabiyoti": ["Nazariy grammatika", "Stilistika", "Mamlakatshunoslik", "Til tarixi"],
    "Filologiya va tillarni o'qitish (ingliz tili)": ["Fonetika va fonologiya", "Kompyuter lingvistikasi", "Lingvokulturologiya", "Sinxron tarjima"],
    "Davlat moliyaviy nazorati va auditi": ["Moliyaviy nazorat metodologiyasi", "Ichki nazorat tizimlari", "Davlat xaridlari auditi", "Soliq nazorati"],
    "Pedagogika (magistratura)": ["Ta'lim siyosati", "Pedagogik innovatsiyalar", "Oliy ta'limda baholash", "Ta'lim sifatini boshqarish"],
    "Xorijiy til va adabiyoti (magistratura)": ["Kognitiv tilshunoslik", "Qiyosiy adabiyotshunoslik", "Tarjimashunoslik", "Korpus lingvistikasi"],
}
MASTER_POOL = ["Akademik yozuv va nashr etish", "Ilmiy tadqiqotlarda statistik usullar", "Xorijiy tilda ilmiy muloqot", "Oliy ta'lim pedagogikasi",
               "Innovatsion menejment", "Mutaxassislik bo'yicha ilmiy seminar", "Ilmiy-tadqiqot ishi (1-bosqich)", "Ilmiy-tadqiqot ishi (2-bosqich)"]
LANG_TRACK = ["Ingliz tili", "Akademik ingliz tili", "Kasbiy ingliz tili"]     # 1–3-semestr (til yo'nalishlaridan tashqari)
GEN_LOCAL = ["O'zbekiston tarixi", "Falsafa"]                                 # mahalliy yo'nalishlar: Gumanitar va tabiiy fanlar kafedrasi
GEN_INTL = ["Tanqidiy fikrlash (Critical Thinking)", "Tadqiqot ko'nikmalari (Study Skills)"]   # xalqaro yo'nalishlar
HUM_SUBJECTS = set(GEN_LOCAL)
CREDIT_PAT = {5: [(6, 6, 6, 6, 6), (8, 6, 6, 5, 5), (7, 7, 6, 5, 5)]}
FINAL_B = [("Malakaviy amaliyot", 12), ("Bitiruv malakaviy ishi", 12)]
FINAL_M = [("Ilmiy-tadqiqot ishi va ilmiy-pedagogik amaliyot", 12), ("Magistrlik dissertatsiyasi", 18)]

def curriculum(direction, level, fi):
    """[[(fan, kredit), ...] × semestr] — 1-semestrdan boshlab. Har semestr 30 kredit, yo'nalish ichida fanlar takrorlanmaydi."""
    key = f"{direction} (magistratura)" if level == "magistr" and f"{direction} (magistratura)" in SUBJECTS else direction
    own = [x for x in SUBJECTS[key] if x not in LANG_TRACK]
    extra = EXTRA.get(key, [])
    if level == "magistr":
        n, slots, place = 4, [5, 5, 5, 0], [1, 3, 1, 3]
        fill = MASTER_POOL[:2] + [x for p in zip(extra, MASTER_POOL[2:]) for x in p] + MASTER_POOL[2 + len(extra):]
        fixed = {i: [] for i in range(1, 5)}
    else:
        fam = FAMILY[direction]
        n, slots, place = 8, [5] * 7 + [3], [3, 5, 7, 1]
        pool = POOL[fam]
        fill = pool[:6] + [x for p in zip(extra, pool[6:]) for x in p] + pool[6 + len(extra):]
        fixed = {i: [] for i in range(1, 9)}
        gen = GEN_INTL if fi == INTL_FACULTY else GEN_LOCAL
        fixed[1].append(gen[0]); fixed[2].append(gen[1])
        if fam != "lang":
            for i, x in enumerate(LANG_TRACK, 1): fixed[i].append(x)
    for i, x in enumerate(own): fixed[place[i % len(place)]].append(x)
    used = {x for v in fixed.values() for x in v}
    fill = [x for x in dict.fromkeys(fill) if x not in used]
    out = []
    for k in range(1, n + 1):
        subj = list(fixed[k])
        if level != "magistr" and k == 8: subj = []
        while len(subj) < slots[k - 1] - (2 if level != "magistr" and k == 8 else 0) or (level != "magistr" and k == 8 and len(subj) < 1):
            subj.append(fill.pop(0))
        if level == "magistr" and k == 4:
            out.append(list(FINAL_M)); continue
        if level != "magistr" and k == 8:
            out.append(list(FINAL_B) + [(subj[0], 6)]); continue
        pat = CREDIT_PAT[5][(k - 1) % 3] if len(subj) == 5 else None
        if not pat:
            base = 30 // len(subj); pat = [base] * len(subj); pat[0] += 30 - base * len(subj)
        out.append(list(zip(subj, pat)))
    return out

# Hamkorlar: isft.uz'da ro'yxat e'lon qilinmagan — haqiqiy universitet nomlari ishlatilmaydi (yolg'on hamkorlik ko'rinmasin). NAMUNA.
COUNTRIES = [(f"Hamkor OTM — {c} (namuna)", c) for c in ["Buyuk Britaniya", "Polsha", "Latviya", "Janubiy Koreya", "Turkiya", "Avstriya",
             "Malayziya", "Litva", "Qozog'iston", "Xitoy", "Ispaniya", "Germaniya"]]

def _split(sc):
    """Demo yakuniy ball → (oraliq, yakuniy). Oraliq < 12 bo'lsa talaba yakuniyga kiritilmagan (yakuniy None, jami = oraliq)."""
    if sc >= AR.PASS:
        lo, hi = max(AR.ORALIQ_MIN, sc - AR.YAKUNIY_MAX), min(AR.ORALIQ_MAX, sc - AR.YAKUNIY_MIN)
        o = max(lo, min(hi, round(sc * 0.3 + _RS.uniform(-3, 3))))
        return o, sc - o
    o = max(0, min(AR.ORALIQ_MAX, sc, round(sc * 0.33 + _RS.uniform(-3, 3))))
    return (o, None) if o < AR.ORALIQ_MIN else (o, sc - o)

_RS = random.Random(7)
OLD_GRADE_ROWS = 0   # eski modeldagi joriy semestr baholari soni — seed_extra R ketma-ketligini saqlash uchun

def run():
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    con = db.connect(); db.init(con)
    c = con.cursor()

    # --- tuzilma: fakultet → kafedra → yo'nalish × ta'lim shakli × kurs → guruhlar ---
    P = PROFILE
    dept_rows = []   # (did, fi, [(direction, weight)])
    former_dean = {}
    for fi, (fname, depts) in enumerate(FACULTIES, 1):
        former_dean[fi], _ = person("M" if fi != 3 else "F")   # tasodifiy ketma-ketlik (va id'lar) o'zgarmasligi uchun chaqiriladi
        c.execute("INSERT INTO faculties VALUES(?,?,?)", (fi, fname, None))   # faculties.dean — bo'sh (dekan lavozimi yo'q)
        for dname, directions in depts:
            head = DEPT_HEADS.get(dname) or person()[0]
            c.execute("INSERT INTO departments(faculty_id,name,head) VALUES(?,?,?)", (fi, dname, head))
            dept_rows.append((c.lastrowid, fi, directions))
    inst_dept_ids = set()
    for dname in INSTITUTE_DEPTS:   # oxirida — mavjud kafedra id'lari (1–7) o'zgarmaydi
        c.execute("INSERT INTO departments(faculty_id,name,head) VALUES(?,?,?)", (None, dname, DEPT_HEADS.get(dname) or person()[0]))
        dept_rows.append((c.lastrowid, None, [])); inst_dept_ids.add(c.lastrowid)
    wsum = sum(w for _, _, ds in dept_rows for _, w in ds)
    group_rows = []   # (gid, did, fi, course, direction, form, size)
    for did, fi, directions in dept_rows:
        for d, w in directions:
            code = GROUP_CODE.get(d, "G")
            for form, total in P["students_by_form"].items():
                suffix, size = FORM_GROUP[form]
                for course in range(1, 5):
                    n = round(total * w / wsum * COURSE_W[course - 1])
                    k = max(1, round(n / size))
                    for gi in range(1, k + 1):
                        cnt = n // k + (1 if gi <= n % k else 0)
                        if cnt <= 0: continue
                        name = f"{code}-{AR.intake_year(course) % 100:02d}{suffix}{gi:02d}"   # qabul yili: 1-kurs — 26, 4-kurs — 23
                        c.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,?)",
                                  (did, fi, name, course, d, "bakalavr", form))
                        group_rows.append((c.lastrowid, did, fi, course, d, form, cnt, "bakalavr"))
    # magistratura: 370 talaba, 3 dastur, 2 kurs, kunduzgi
    for prog, dept_no in MASTERS:
        did, fi, _ = dept_rows[dept_no - 1]
        per_course = P["master_students"] // len(MASTERS) // 2
        for course in (1, 2):
            k = max(1, round(per_course / 22))
            for gi in range(1, k + 1):
                cnt = per_course // k + (1 if gi <= per_course % k else 0)
                code = GROUP_CODE.get(prog, "MAG-" + "".join(w[0] for w in prog.split()[:2]).upper())
                c.execute("INSERT INTO groups_(department_id,faculty_id,name,course,direction,level,form) VALUES(?,?,?,?,?,?,?)",
                          (did, fi, f"{code}-{AR.intake_year(course) % 100:02d}{gi:02d}", course, prog, "magistr", "kunduzgi"))
                group_rows.append((c.lastrowid, did, fi, course, prog, "kunduzgi", cnt, "magistr"))

    # --- o'qituvchilar: jami 255, kafedralar bo'yicha guruhlar ulushiga qarab; ilmiy darajalilar ~24% (NQAAE) ---
    load = {did: sum(1 for g in group_rows if g[1] == did) for did, _, _ in dept_rows}
    tot = sum(load.values())
    alloc = {did: max(10, round(P["teachers"] * load[did] / tot)) for did in load}
    while sum(alloc.values()) > P["teachers"]: alloc[max(alloc, key=alloc.get)] -= 1
    while sum(alloc.values()) < P["teachers"]: alloc[max(alloc, key=alloc.get)] += 1
    teachers = []
    for did, fi, _ in dept_rows:
        head = db.one(con, "SELECT head FROM departments WHERE id=?", (did,))["head"]
        for k in range(alloc[did]):
            nm = head if k == 0 else person()[0]
            deg = R.choice(["PhD", "DSc"]) if k == 0 else R.choices(["PhD", "DSc", "—", "Magistr"], [20, 4, 30, 46])[0]
            pos = "Kafedra mudiri" if k == 0 else R.choice(["Dotsent", "Katta o'qituvchi", "Professor"]) if deg in ("PhD", "DSc") else R.choice(["Katta o'qituvchi", "Assistent", "Assistent"])
            c.execute("INSERT INTO teachers(full_name,department_id,faculty_id,degree,position,load_hours,h_index) VALUES(?,?,?,?,?,?,?)",
                      (nm, did, fi, deg, pos, R.randint(560, 980), R.choice([0, 0, 1, 1, 2, 3, 4, 5, 7]) if deg in ("PhD", "DSc") else R.choice([0, 0, 1])))
            teachers.append((c.lastrowid, did, fi))
    # o'quv rejasi (curriculum): yo'nalish × daraja × semestr → fanlar va kreditlar
    AR.ensure_schema(con)
    from . import student_ops as OPS
    con.executescript(OPS.SCHEMA)   # student_leaves — akademik ta'til davri baholar yaratilishidan oldin kerak
    RA = random.Random(20261110)    # akademik tarix uchun alohida ketma-ketlik: R (va undan keyingi demo ma'lumotlar) o'zgarmaydi
    plans = {}
    for did, fi, directions in dept_rows:
        for d, _ in directions:
            plans[(d, "bakalavr")] = curriculum(d, "bakalavr", fi)
    for prog, dept_no in MASTERS:
        plans[(prog, "magistr")] = curriculum(prog, "magistr", dept_rows[dept_no - 1][1])
    c.executemany("INSERT INTO curriculum(direction,level,sem_no,subject,credits) VALUES(?,?,?,?,?)",
                  [(d, lv, k, subj, cr) for (d, lv), sems in plans.items() for k, sem in enumerate(sems, 1) for subj, cr in sem])
    # o'qituvchi-guruh-fan (JORIY semestr fanlari). Avvalgi tasodifiy ketma-ketlik saqlanadi: R har guruhda eski fanlar soni bo'yicha
    # chaqiriladi, o'qituvchi esa yangi o'quv rejasidagi fan uchun RA bilan tanlanadi.
    tg = {}
    fund_teachers = [t for t in teachers if t[1] in inst_dept_ids]   # umumiy iqtisodiy fanlarni institut kafedrasi o'qitadi
    hum_id = next(did for did, _, _ in dept_rows if db.one(con, "SELECT name FROM departments WHERE id=?", (did,))["name"] == HUM_DEPT)
    hum_teachers = [t for t in teachers if t[1] == hum_id]
    skey = lambda d, level: f"{d} (magistratura)" if level == "magistr" and f"{d} (magistratura)" in SUBJECTS else d
    def pool_for(subj, did):
        return (fund_teachers if subj in FUND_SUBJECTS and fund_teachers else hum_teachers if subj in HUM_SUBJECTS
                else [t for t in teachers if t[1] == did])
    def teacher_for(gid, did, subj):
        if (gid, subj) not in tg: tg[(gid, subj)] = RA.choice(pool_for(subj, did))[0]
        return tg[(gid, subj)]
    for gid, did, fi, course, d, form, cnt, level in group_rows:
        key = skey(d, level)
        dept_teachers = [t for t in teachers if t[1] == did]
        for subj in subjects_for(key, course, level, fi):   # faqat R ketma-ketligi uchun (eski fanlar ro'yxati)
            R.choice(fund_teachers if subj in FUND_SUBJECTS and fund_teachers else hum_teachers if subj == HUM_SUBJECT else dept_teachers)
        for subj, _ in plans[(d, level)][AR.sem_no(course, AR.CURRENT_SEMESTER) - 1]:
            c.execute("INSERT INTO teacher_groups VALUES(?,?,?)", (teacher_for(gid, did, subj), gid, subj))

    # --- talabalar: 29 203 (NQAAE), shakli bo'yicha; narx — BHM × koeffitsiyent (isft.uz) ---
    bcv, tb = P["bcv"], P["tuition_bcv"]
    sid = 0
    day_pool = {}   # kurs → kunduzgi bakalavr talabalar (grant taqsimoti uchun)
    global OLD_GRADE_ROWS
    OLD_GRADE_ROWS = 0
    grade_rows, attempt_rows, leave_rows = [], [], []
    real_today = dt.date.today()
    for gid, did, fi, course, d, form, cnt, level in group_rows:
        key = skey(d, level)
        if level == "magistr": price = tb["magistr"] * bcv
        elif form == "kunduzgi": price = (tb["kunduzgi_xalqaro"] if fi == INTL_FACULTY else tb["kunduzgi"]) * bcv
        else: price = tb[form] * bcv
        for _ in range(cnt):
            sid += 1
            nm, g = person()
            amount = price
            if R.random() < 0.04: amount = int(price * (1 - P["family_discount"]))   # oilaviy chegirma
            # 100 ballik ball institut shkalasida (o'tish 40, «5» — 65+; app/academic_rules.py): o'rtacha ~58 («4», C).
            # Fanlar bo'yicha: ~28% «5», ~47% «4», ~17% «3», ~7% o'zlashtirmagan.
            base = R.gauss(58, 9)
            # HIKOYA: Xalqaro iqtisodiyot va moliya fakulteti 2-kurs keskin pasaygan
            drop = 11 if (fi == 2 and course == 2) else R.uniform(-2, 3)
            gpa = max(20, min(97, base - drop))
            prev = max(24, min(97, base + R.uniform(-2, 2)))
            if form == "masofaviy": att = None                     # masofaviy — auditoriya davomati yo'q
            elif form == "sirtqi": att = max(50, min(100, R.gauss(91, 6) - (12 if gpa < 40 else 0)))   # sessiya davomati
            else: att = max(40, min(100, R.gauss(88, 7) - (9 if (fi == 2 and course == 2) else 0) - (12 if gpa < 40 else 0)))
            paid_ratio = R.choices([1, 0.75, 0.5, 0.25, 0], [72, 10, 9, 5, 4])[0]
            if fi == 2 and course == 2 and R.random() < .15: paid_ratio = 0.25
            status = "faol" if R.random() > 0.01 else "akademik ta'til"
            c.execute("""INSERT INTO students(hemis_id,full_name,group_id,faculty_id,gender,region,payment_type,contract_amount,
                      paid_amount,gpa,attendance,gpa_prev,status,level,study_form) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (f"3{R.randint(10**11, 10**12-1)}", nm, gid, fi, g, R.choice(REGIONS), "kontrakt", amount, int(amount * paid_ratio),
                       round(gpa, 1), round(att, 1) if att is not None else None, round(prev, 1), status, level, form))
            if form == "kunduzgi" and level == "bakalavr": day_pool.setdefault(course, []).append((sid, gpa))
            for subj in subjects_for(key, course, level, fi):   # faqat R ketma-ketligi uchun (eski «bitta semestr» baholari)
                R.gauss(gpa, 8); OLD_GRADE_ROWS += 1
            # --- akademik tarix (RA): o'tgan semestrlar — yakuniy ball (oraliq + yakuniy), joriy semestr — faqat oraliq nazorat ---
            leave = None
            if status == "akademik ta'til":
                k = len(leave_rows)
                end = real_today + dt.timedelta(days=[12, 26, -9][k] if k < 3 else RA.randint(-40, 200))   # birinchi uchtasi — ogohlantirish oynasida
                start = end - dt.timedelta(days=RA.choice([182, 270, 365]))
                leave = (start.isoformat(), end.isoformat())
                leave_rows.append((sid, "akademik", leave[0], leave[1], f"TH-{start.year % 100}/{RA.randint(100, 999)}"))
            # HIKOYA: Xalqaro iqtisodiyot va moliya 2-kurs — 1-semestr (2025-26 kuzgi) yaxshi (prev), 2-semestrda keskin pasaygan (gpa),
            # joriy semestr oraliq nazoratida ham past
            ability = {AR.CURRENT_SEMESTER: gpa + RA.gauss(0, 2), 0: gpa, -1: prev}
            for t in range(AR.CURRENT_SEMESTER, AR.OLDEST_SEMESTER - 1, -1):
                n = AR.sem_no(course, t)
                if n < 1: break
                if leave:
                    a0, a1 = AR.term_dates(t)
                    if leave[0] <= a1 and leave[1] >= a0: continue   # ta'til davridagi semestrda baho yo'q
                ab = ability.get(t, base + RA.uniform(-3, 3))
                for subj, cr in plans[(d, level)][n - 1]:
                    tid = teacher_for(gid, did, subj)
                    if t == AR.CURRENT_SEMESTER:
                        o = max(0, min(AR.ORALIQ_MAX, round(RA.gauss(ab * 0.31, 2.2))))
                        grade_rows.append((sid, subj, tid, None, t, o, None, cr, n, 1)); continue
                    sc = max(8, min(100, round(RA.gauss(ab, 8))))
                    o, y = _split(sc)
                    first = o + (y or 0)
                    if first >= AR.PASS or RA.random() > (0.65 if t == 0 else 0.95):   # o'tgan yoki qarz yopilmagan
                        grade_rows.append((sid, subj, tid, first, t, o, y, cr, n, 1)); continue
                    # qayta topshirish (yozgi / keyingi semestr): yangi urinish hisobga olinadi, asl urinish tarixda qoladi
                    o2 = o if o >= AR.ORALIQ_MIN else RA.randint(AR.ORALIQ_MIN, 20)
                    y2 = RA.randint(AR.YAKUNIY_MIN, 45); s2 = o2 + y2
                    when = (dt.date.fromisoformat(AR.term_dates(t)[1]) + dt.timedelta(days=RA.randint(20, 75))).isoformat()
                    grade_rows.append((sid, subj, tid, s2, t, o2, y2, cr, n, 2))
                    attempt_rows.append((sid, subj, t, 1, "asosiy", o, y, first, AR.term_dates(t)[1], 0, None))
                    attempt_rows.append((sid, subj, t, 2, "qayta topshirish", o2, y2, s2, when, 1, None))
    c.executemany("""INSERT INTO grades(student_id,subject,teacher_id,score,semester,oraliq,yakuniy,credits,sem_no,attempts)
                     VALUES(?,?,?,?,?,?,?,?,?,?)""", grade_rows)
    c.executemany("""INSERT INTO grade_attempts(student_id,subject,semester,attempt,kind,oraliq,yakuniy,score,at,counted,retake_id)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""", attempt_rows)
    c.executemany("INSERT INTO student_leaves(student_id,kind,start,end,order_no) VALUES(?,?,?,?,?)", leave_rows)
    AR.refresh_student_metrics(con)   # students.gpa / gpa_prev — baholardan (o'rtacha ball (100), oxirgi ikki yakunlangan semestr)
    # grantlar: har yili 300 (250 umumiy tanlov — eng yuqori natija, 50 ijtimoiy) — faqat kunduzgi bakalavr (isft.uz/en/faq)
    for course, pool in day_pool.items():
        top = [s for s, _ in sorted(pool, key=lambda x: -x[1])[:P["grants_per_year"] - P["grants_social"]]]
        rest = [s for s, _ in pool if s not in set(top)]
        social = R.sample(rest, min(P["grants_social"], len(rest)))
        c.executemany("UPDATE students SET payment_type='grant', contract_amount=0, paid_amount=0 WHERE id=?", [(s,) for s in top + social])
    # magistrlar dissertatsiyasi
    for s in db.rows(con, "SELECT id, faculty_id FROM students WHERE level='magistr'"):
        sup = R.choice([t for t in teachers if t[2] == s["faculty_id"]])[0]
        c.execute("INSERT INTO masters(student_id,supervisor_id,topic,stage) VALUES(?,?,?,?)",
                  (s["id"], sup, R.choice(["Raqamli to'lov tizimlarining rivojlanishi","Kichik biznesni moliyalashtirish",
                   "Bank risklarini baholash modellari","Ta'limda sun'iy intellekt","Soliq ma'muriyatchiligini raqamlashtirish",
                   "IFRS ga o'tish muammolari","E-tijorat bozorining tahlili"]),
                   R.choices(["Mavzu tasdiqlangan","1-bob tayyor","2-bob tayyor","Dastlabki himoya"], [30, 35, 25, 10])[0]))

    # --- ilmiy faoliyat ---
    for t, did, fi in teachers:
        for _ in range(R.choices([0, 1, 2, 3, 4, 6], [25, 25, 20, 15, 10, 5])[0]):
            kind = R.choices(["Scopus","Web of Science","OAK jurnali","Konferensiya tezisi"], [11, 2, 45, 42])[0]   # Scopus jami ~62 (NQAAE)
            c.execute("INSERT INTO publications(teacher_id,title,kind,year,citations) VALUES(?,?,?,?,?)",
                      (t, R.choice(["Raqamli iqtisodiyotda","O'zbekiston bank sektorida","Oliy ta'limda","Kichik biznesda","Moliyaviy bozorlarda"]) + " " +
                       R.choice(["innovatsion yondashuvlar","risklarni boshqarish","raqamli transformatsiya","samaradorlikni baholash","barqaror rivojlanish"]),
                       kind, R.choice([2024, 2025, 2025, 2026, 2026, 2026]), R.randint(0, 25) if kind in ("Scopus","Web of Science") else 0))
    for i in range(14):
        t = R.choice(teachers)[0]
        c.execute("INSERT INTO grants(title,leader_id,funder,amount,status,year) VALUES(?,?,?,?,?,?)",
                  (R.choice(["Raqamli ta'lim platformasi","Moliyaviy savodxonlik","Yashil iqtisodiyot","AI asosida kredit skoring","Mintaqaviy innovatsiyalar"]) + " loyihasi",
                   t, R.choice(["Innovatsion rivojlanish agentligi","Erasmus+","Xalqaro hamkor","Vazirlik"]),
                   R.choice([150, 280, 400, 650, 900]) * 1_000_000, R.choices(["bajarilmoqda","ariza berilgan","yakunlangan","rad etilgan"], [5, 4, 3, 2])[0],
                   R.choice([2025, 2026])))

    # --- xalqaro ---
    for i, (n, cn) in enumerate(COUNTRIES):
        signed = TODAY - dt.timedelta(days=R.randint(300, 1400))
        exp = signed + dt.timedelta(days=R.choice([1095, 1825]))
        if i in (2, 5): exp = TODAY + dt.timedelta(days=R.choice([23, 47]))  # HIKOYA: tez orada tugaydi
        st = "faol" if exp > TODAY else "muddati tugagan"
        c.execute("INSERT INTO partners(name,country,kind,signed,expires,status,students_exchanged) VALUES(?,?,?,?,?,?,?)",
                  (n, cn, R.choice(["Akademik almashinuv","Qo'shma dastur (2+2)","Ilmiy hamkorlik","Erasmus+ KA171"]),
                   signed.isoformat(), exp.isoformat(), st, R.randint(0, 14)))

    # --- qabul (2026) ---
    # 2026 qabul: talaba bo'lganlar = 8 184 (NQAAE accepted_count); ariza berganlar soni — TAXMIN (~1,65 baravar)
    dirs = [(d, fi, w) for (_, fi, ds) in dept_rows for d, w in ds]
    n_acc = P["accepted_2026"]; n_all = int(n_acc * 1.65)
    stats = ["talaba bo'ldi"] * n_acc + R.choices(["tavsiya etildi", "rad etildi", "hujjat topshirdi"], [10, 55, 35], k=n_all - n_acc)
    R.shuffle(stats)
    for st in stats:
        d, fi, _ = R.choices(dirs, [w for _, _, w in dirs])[0]
        day = dt.date(2026, 6, 1) + dt.timedelta(days=min(121, int(abs(R.gauss(45, 25)))))   # qabul: 1 iyun – 30 sentabr (mentalaba.uz)
        c.execute("INSERT INTO applicants(direction,faculty_id,applied,status,score,payment_type) VALUES(?,?,?,?,?,?)",
                  (d, fi, day.isoformat(), st, round(R.uniform(55, 189), 1), R.choices(["kontrakt","grant"], [90, 10])[0]))

    # --- moliya ---
    # TAXMIN (ochiq manbada yo'q): 255 o'qituvchi + ~180 xodim ish haqi, 5 o'quv binosi kommunal xarajati
    cats = {"Ish haqi": 4_600_000_000, "Kommunal xizmatlar": 520_000_000, "Ilmiy faoliyat": 250_000_000,
            "Xo'jalik va ta'mir": 600_000_000, "IT va uskunalar": 380_000_000, "Xalqaro faoliyat": 150_000_000, "Talabalar tadbirlari": 200_000_000}
    for m in range(1, 11):
        for cat, plan in cats.items():
            k = R.uniform(0.86, 1.04)
            if cat == "Kommunal xizmatlar" and m >= 8: k = R.uniform(1.18, 1.31)  # HIKOYA
            c.execute("INSERT INTO budget(month,category,planned,actual) VALUES(?,?,?,?)", (f"2026-{m:02d}", cat, plan, int(plan * k)))

    # --- kadrlar (shaxsiy ma'lumot — faqat kadrlar bo'limiga) ---
    units = ["Rektorat","Buxgalteriya bo'limi","Kadrlar bo'limi","Registrator ofisi","Akademik faoliyatni boshqarish bo'limi","Marketing bo'limi","Xalqaro hamkorlik bo'limi",
             "Xo'jalik va texnik bo'lim","Axborot texnologiyalari bo'limi","Axborot-resurs markazi","Devonxona","Yuridik bo'lim",
             "Imtihon bo'limi","Magistratura bo'limi","Amaliyot bo'limi","Ilmiy tadqiqotlar, innovatsiyalar va ilmiy-pedagogik kadrlar tayyorlash bo'limi"]
    # bo'lim rahbarlari (institut ro'yxati); Registrator ofisi va Akademik faoliyatni boshqarish — departament tarkibida
    for u, nm in UNIT_HEADS.items():
        parent = u
        pos = "Bo'lim boshlig'i"
        c.execute("INSERT INTO staff(full_name,unit,position,salary,hired,passport) VALUES(?,?,?,?,?,?)",
                  (nm, parent, pos, R.choice([12, 14, 16]) * 1_000_000, (TODAY - dt.timedelta(days=R.randint(400, 3000))).isoformat(), f"AD{R.randint(1000000, 9999999)}"))
    # Sirtqi bo'lim va Ma'lumotlar bazasi bo'limi — alohida bo'limlar (akademik qoidalar taqdimoti). Tasodifiy son ishlatilmaydi —
    # keyingi demo ma'lumotlar (hikoyalar) o'zgarmasligi uchun.
    for i, (unit, nm) in enumerate(OTHER_UNIT_HEADS.items()):
        c.execute("INSERT INTO staff(full_name,unit,position,salary,hired,passport) VALUES(?,?,?,?,?,?)",
                  (nm, unit, "Bo'lim boshlig'i", 12_000_000, (TODAY - dt.timedelta(days=900 + 370 * i)).isoformat(), f"AD{4810233 + 77 * i}"))
    for t, did, fi in teachers:
        nm = db.one(con, "SELECT full_name, position FROM teachers WHERE id=?", (t,))
        c.execute("INSERT INTO staff(full_name,unit,position,salary,hired,passport) VALUES(?,?,?,?,?,?)",
                  (nm["full_name"], "Professor-o'qituvchi", nm["position"], R.choice([7, 8, 9, 11, 13, 16]) * 1_000_000,
                   (TODAY - dt.timedelta(days=R.randint(100, 3000))).isoformat(), f"AD{R.randint(1000000, 9999999)}"))
    for _ in range(P["other_staff"]):
        nm, _ = person(); u = R.choice(units)
        c.execute("INSERT INTO staff(full_name,unit,position,salary,hired,passport) VALUES(?,?,?,?,?,?)",
                  (nm, u, R.choice(["Bosh mutaxassis","Mutaxassis","Bo'lim boshlig'i","Inspektor"]), R.choice([5, 6, 7, 9, 12]) * 1_000_000,
                   (TODAY - dt.timedelta(days=R.randint(100, 3000))).isoformat(), f"AD{R.randint(1000000, 9999999)}"))

    # --- yoshlar ---
    for t in ["Ma'naviyat soati: Yangi O'zbekiston","Intellektual o'yin \"Zakovat\"","Sport musobaqasi: mini-futbol","Kitobxonlik tanlovi",
              "Volontyorlik aksiyasi","Startap-tashabbuslar haftaligi","Karyera kuni (Career Day)","Debat klubi finali","Bayram konserti"]:
        c.execute("INSERT INTO events(title,date,kind,participants) VALUES(?,?,?,?)",
                  (t, (TODAY - dt.timedelta(days=R.randint(1, 60))).isoformat(), R.choice(["ma'naviy","sport","intellektual","karyera"]), R.randint(40, 420)))
    # yotoqxona: NQAAE pasportiga ko'ra institutda yotoqxona YO'Q — jadval bo'sh qoladi
    for cat, txt in [("Turar joy (ijara)","Institut yaqinida arzon ijara uy topish qiyin"),("O'quv jarayoni","Dars jadvali tez-tez o'zgaradi"),
                     ("Ovqatlanish","Oshxonada navbat juda uzun"),("Transport","Qibraydan Toshkentga qatnov avtobusi kam"),("O'quv jarayoni","Kutubxona shanba kuni yopiq"),
                     ("Boshqa","Sport zalga yozilish qiyin"),("O'quv jarayoni","HEMIS da baho kech chiqyapti"),("O'quv binosi","Isitish tizimi ishlamayapti (2-o'quv binosi)")]:
        c.execute("INSERT INTO appeals(date,category,text,status) VALUES(?,?,?,?)",
                  ((TODAY - dt.timedelta(days=R.randint(0, 30))).isoformat(), cat, txt, R.choice(["yangi","ko'rib chiqilmoqda","hal qilindi"])))

    # --- majlislar va topshiriqlar ---
    meetings = [
        ("Institut Kengashi yig'ilishi №3", "2026-09-28", "Kengash"),
        ("Rektorat yig'ilishi", "2026-10-13", "Rektorat"),
        ("Rektorat yig'ilishi", "2026-10-27", "Rektorat"),
    ]
    task_seed = [
        (0, "Registrator ofisi", "talabalar", "Xalqaro iqtisodiyot va moliya fakulteti 2-kurs talabalari o'zlashtirishi bo'yicha tahliliy ma'lumotnoma tayyorlash", "2026-10-15", "bajarilmagan"),
        (0, "O'quv ishlari prorektori", "prorektor_oquv", "Akkreditatsiya uchun o'quv dasturlarini yangilash rejasini tasdiqlash", "2026-10-20", "bajarilmagan"),
        (0, "Moliya-iqtisod prorektori", "prorektor_moliya", "Kontrakt qarzdorligi bo'yicha guruhlar kesimida reja ishlab chiqish", "2026-10-25", "bajarildi"),
        (1, "Xalqaro aloqalar bo'limi", "xalqaro", "Muddati tugayotgan hamkorlik shartnomalarini uzaytirish xatlarini yuborish", "2026-10-30", "bajarilmagan"),
        (1, "Ilmiy ishlar prorektori", "prorektor_ilmiy", "Scopus maqolalar rejasini kafedralar kesimida taqsimlash", "2026-11-10", "jarayonda"),
        (1, "Yoshlar ishlari prorektori", "prorektor_yoshlar", "2-bino isitish tizimi bo'yicha murojaatni hal qilish", "2026-11-06", "jarayonda"),
        (2, "Qabul bo'limi", "qabul", "2027 qabul kampaniyasi uchun marketing rejasini taqdim etish", "2026-11-20", "jarayonda"),
        (2, "Registrator ofisi", "talabalar", "Qarzdor talabalar bilan individual suhbatlar o'tkazish", "2026-11-15", "jarayonda"),
        (2, "Buxgalteriya", "buxgalteriya", "Kommunal xarajatlar oshishi sabablarini tahlil qilish", "2026-11-12", "jarayonda"),
    ]
    for i, (t, d, k) in enumerate(meetings, 1):
        c.execute("INSERT INTO meetings(title,date,kind,transcript) VALUES(?,?,?,?)", (t, d, k, ""))
    for mi, who, role, text, due, st in task_seed:
        c.execute("INSERT INTO tasks(meeting_id,assignee,assignee_role,text,due,status) VALUES(?,?,?,?,?,?)", (mi + 1, who, role, text, due, st))

    # --- foydalanuvchilar (demo rollar) ---
    def tid_of(dept_id):
        return db.one(con, "SELECT id, full_name FROM teachers WHERE department_id=? AND position!='Kafedra mudiri' LIMIT 1", (dept_id,))
    dept4 = db.one(con, "SELECT * FROM departments WHERE id=4")
    t = tid_of(4)
    UH_MAG, UH_AKA = UNIT_HEADS["Magistratura bo'limi"], UNIT_HEADS["Akademik faoliyatni boshqarish bo'limi"]
    UH_ILM = UNIT_HEADS["Ilmiy tadqiqotlar, innovatsiyalar va ilmiy-pedagogik kadrlar tayyorlash bo'limi"]
    from .rbac import hash_password, DEMO_PASSWORD
    PW = hash_password(DEMO_PASSWORD)   # demo: barcha akkauntlar uchun bitta parol (xeshlangan)
    users = [
        ("Kuzatuv kengashi a'zosi", "kengash", None, None, None, "KENGASH"),
        (f"Rektor: {LEADERS['rektor']}", "rektor", None, None, None, "REKTOR"),
        (f"O'quv ishlari bo'yicha prorektor: {LEADERS['prorektor_oquv']}", "prorektor_oquv", None, None, None, "OQUV"),
        (f"Ilmiy ishlar va innovatsiyalar bo'yicha prorektor: {LEADERS['prorektor_ilmiy']}", "prorektor_ilmiy", None, None, None, "ILMIY"),
        (f"Moliya-iqtisod ishlari bo'yicha prorektor: {LEADERS['prorektor_moliya']}", "prorektor_moliya", None, None, None, "MOLIYA"),
        (f"Yoshlar masalalari va ma'naviy-ma'rifiy ishlar bo'yicha birinchi prorektor: {LEADERS['prorektor_yoshlar']}", "prorektor_yoshlar", None, None, None, "YOSHLAR"),
        ("Qabul komissiyasi", "qabul", None, None, None, "QABUL"),
        (f"Imtihon bo'limi: {UNIT_HEADS['Imtihon bo\'limi']}", "imtihon", None, None, None, "IMTIHON"),   # id 8 (avval umumiy departament akkaunti edi)
        (f"Magistratura bo'limi: {UH_MAG}", "magistratura", None, None, None, "MAGISTR"),
        ("Xalqaro hamkorlik bo'limi", "xalqaro", None, None, None, "XALQARO"),
        ("Buxgalteriya bo'limi", "buxgalteriya", None, None, None, "BUXGALTER"),
        ("Kadrlar bo'limi", "kadrlar", None, None, None, "KADR"),
        # id 13 — sobiq "Dekan" demo akkaunti: lavozim bekor qilingan, akkaunt faolsizlantirilgan (accounts.retire_legacy);
        # keyingi id'lar o'zgarmasligi uchun qator saqlanadi
        (f"Dekan (lavozim bekor qilingan): {former_dean[2]}", "dekan", 2, None, None, "DEKAN"),
        (f"{dept4['name']} kafedrasi mudiri: {dept4['head']}", "kafedra", 2, 4, None, "KAFEDRA"),
        (f"O'qituvchi: {t['full_name']}", "oqituvchi", 2, 4, t["id"], "USTOZ"),
        ("Xo'jalik va texnik bo'lim", "xojalik", None, None, None, "XOJALIK"),
        # departament tarkibidagi bo'limlar va ilmiy bo'lim (id'lar 17–19: keyingi demo akkauntlar id'si o'zgarmasligi uchun shu yerda)
        (f"Registrator ofisi: {UNIT_HEADS['Registrator ofisi']}", "talabalar", None, None, None, "REGOFIS"),
        (f"Akademik faoliyatni boshqarish bo'limi: {UH_AKA}", "akademik", None, None, None, "AKADEM"),
        (f"Ilmiy tadqiqotlar, innovatsiyalar va ilmiy-pedagogik kadrlar tayyorlash bo'limi: {UH_ILM}", "ilmiy_bolim", None, None, None, "ILMIYBO"),
    ]
    for nm, role, f, d, tid, code in users:
        c.execute("INSERT INTO users(full_name,role,faculty_id,department_id,teacher_id,link_code,pin) VALUES(?,?,?,?,?,?,?)",
                  (nm, role, f, d, tid, code, PW))
    from . import seed_extra
    seed_extra.run(con, R, TODAY, teachers, old_rows=OLD_GRADE_ROWS)
    con.commit()
    from . import dateshift   # hikoya 2026-11-04 ga nisbatan yozilgan — hammasini bugungi sanaga suramiz
    print("Sanalar surildi:", dateshift.shift_all(con, (dt.date.today() - TODAY).days), "kun")
    from . import seed_service
    seed_service.run(con, R)
    from . import seed_occupancy
    seed_occupancy.run(con, R)
    # --- Hujjatlar markazi: demo uchun tayyor hujjatlar (fayllari bilan) ---
    import shutil
    from . import documents as D, rbac
    shutil.rmtree(D.OUT, ignore_errors=True)
    base = "http://localhost:8000/"
    def as_(uid): return rbac.ctx_for(con, uid)
    reg, rect, kadr, xal, mol, kaf = as_(17), as_(2), as_(12), as_(10), as_(5), as_(14)   # 17 — Registrator ofisi boshlig'i
    st = D.lookup(con, reg, "student", "")[:4]
    grp = [g for g in D.lookup(con, reg, "group") if "-25" in g["label"]][0]["id"]   # 2-kurs (2025 qabul) guruhi
    for x in st[:3]: D.issue(con, reg, "study_cert", {"target": f"s:{x['id']}", "purpose": R.choice(D.PURPOSES[:5])}, base)
    D.issue(con, reg, "study_cert", {"target": f"s:{st[3]['id']}", "lang": "en"}, base)
    D.issue(con, reg, "transcript", {"target": f"s:{st[0]['id']}"}, base)
    D.issue(con, reg, "exam_sheet", {"group": grp, "subject": "*"}, base)
    D.issue(con, reg, "debtors_list", {}, base)
    D.issue(con, mol, "debt_letter", {"target": f"g:{grp}"}, base)
    D.issue(con, kaf, "load", {"department": 4}, base)
    D.issue(con, rect, "minutes", {"meeting": 5}, base)
    D.issue(con, rect, "exec_notice", {"task": "*"}, base)
    stf = D.lookup(con, kadr, "staff", "")[0]["id"]
    D.issue(con, kadr, "work_cert", {"staff": stf, "with_salary": True}, base)
    D.issue(con, kadr, "leave_order", {"staff": D.lookup(con, kadr, "staff", "")[5]["id"], "start": "2026-12-01"}, base)
    D.issue(con, xal, "invitation", {"guest": "Dr. A. Namuna (sun'iy)", "guest_org": "Hamkor OTM — Latviya (namuna)", "country": "Latvia",
            "purpose_en": "a guest lecture series on FinTech and joint summer school planning", "start": "2027-02-10", "end": "2027-02-17"}, base)
    con.execute("UPDATE documents SET created_at = strftime('%Y-%m-%dT%H:%M:%S', created_at, '-' || (abs(random()) % 12 + 1) || ' days', '-' || (abs(random()) % 300) || ' minutes') WHERE status!='loyiha'")
    con.commit()
    from . import decisions   # majlis qarori oqimi: jadval kengaytmalari va demo akkauntlar (kotib, IT, Registrator)
    decisions.init(con)
    from . import student_ops   # talabalar markazi: telefonlar, to'lov jadvali, dars qoldirishlar, ta'tillar, otrabotkalar (sun'iy)
    student_ops.init(con)
    student_ops.evaluate(con)
    from . import seed_syllabus   # O'quv dasturlari: tayanch OTM katalogi (namuna); demo holat kafedra akkauntlari paydo bo'lgach (syllabus.init)
    seed_syllabus.run(con)
    # Sirtqi bo'lim va Ma'lumotlar bazasi bo'limi (taqdimot). Oxirida qo'shiladi — mavjud demo akkauntlar id'si o'zgarmaydi.
    for unit, role in (("Sirtqi bo'lim", "sirtqi"), ("Ma'lumotlar bazasi bo'limi", "malumotlar_bazasi")):
        con.execute("INSERT INTO users(full_name,role,pin) VALUES(?,?,?)", (f"{unit} boshlig'i: {OTHER_UNIT_HEADS[unit]}", role, PW))
    con.commit()
    from . import registrar   # Registrator ofisi: otrabotka muddatlari (yashil/sariq/qizil), skanlar, kontrakt muddati uzaytirish (sun'iy; idempotent)
    registrar.init(con)
    from . import staff_absence   # Xodimlar ta'tili: safar, ta'til, kasallik varaqasi, o'rinbosarlar (joriy va keyingi 2 hafta + o'tgan oylar; idempotent)
    staff_absence.init(con)
    from . import orders   # Buyruqlar: reyestr (qabul, kursga o'tkazish, ta'til) + ataylab nomuvofiqliklar, namuna arizalar, demo loyihalar (idempotent)
    orders.init(con, fresh=True)
    from . import accounts   # bekor qilingan lavozim (dekan, #13) — akkaunt faolsizlantiriladi (startda ham, idempotent)
    print("Faolsizlantirildi (bekor qilingan lavozim):", accounts.retire_legacy(con))
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ["faculties","departments","groups_","teachers","students","grades","publications","grants","partners","applicants","budget","staff","events","appeals","meetings","tasks","users","documents","audit_log","rooms","tickets","requests","incidents","event_checkin","schedule","cameras","occupancy","cam_events","cam_queue"]}
    print("Seed tayyor:", counts)

if __name__ == "__main__":
    run()
