"""O'quv dasturlari (sillabus) moduli uchun namuna ma'lumotlar: tayanch OTM mavzular katalogi va joriy semestr demo holati.

Ishga tushirish (mavjud bazada, qayta seed'siz):  .venv/bin/python -m app.seed_syllabus [--force]
  * Idempotent: syl_items bo'sh bo'lmasa hech narsa qilinmaydi (--force — modul jadvallarini tozalab qayta to'ldiradi).
  * app/seed.py oxirida ham chaqiriladi; app/syllabus.init() — jadvallar bo'sh bo'lsa server ishga tushganda avtomatik.

DIQQAT: TAYANCH OTM KATALOGI — NAMUNA (SUN'IY) MA'LUMOT. Bu ro'yxatlar ko'rsatilgan universitetlarning rasmiy fan dasturlaridan
olinmagan; ular solishtirish funksiyasini sinash uchun tuzilgan. Haqiqiy foydalanishda Akademik bo'lim tayanch OTMlarning
tasdiqlangan sillabuslaridan mavzularni kiritadi (syl_ref jadvali).
"""
import datetime as dt, json, random, sys
from . import clock
from . import db

# Soha → tayanch OTMlar (namuna). Har bir fan uchun A — asosiy ro'yxat, B — 2 mavzusi tushirilgan + o'ziga xos qo'shimcha mavzular.
UNIS = {
    "iqt": ("TDIU — Toshkent davlat iqtisodiyot universiteti", "TMI — Toshkent moliya instituti"),
    "biz": ("TDIU — Toshkent davlat iqtisodiyot universiteti", "WIUT — Toshkentdagi Westminster xalqaro universiteti"),
    "it": ("TATU — Muhammad al-Xorazmiy nomidagi TATU", "Inha — Toshkentdagi Inha universiteti"),
    "ped": ("TDPU — Nizomiy nomidagi TDPU", "O'zMU — Mirzo Ulug'bek nomidagi O'zMU"),
    "til": ("O'zDJTU — O'zbekiston davlat jahon tillari universiteti", "SamDCHTI — Samarqand davlat chet tillar instituti"),
    "gum": ("O'zMU — Mirzo Ulug'bek nomidagi O'zMU", "JIDU — Jahon iqtisodiyoti va diplomatiya universiteti"),
}

# fan: (soha, qisqa standart tavsif, asosiy mavzular, B universitetidagi qo'shimcha mavzular)
CATALOG = {
    "Audit": ("iqt", "Moliyaviy hisobotlarni mustaqil tekshirish: audit standartlari, rejalashtirish, dalillar, ichki nazorat, auditorlik xulosasi.",
        ["Auditning mohiyati va turlari", "Auditorlik faoliyatini tartibga solish va xalqaro audit standartlari", "Auditorlik tekshiruvini rejalashtirish",
         "Muhimlik darajasi va auditorlik riski", "Auditorlik dalillari va ularni yig'ish usullari", "Ichki nazorat tizimini baholash",
         "Auditorlik tanlov usullari", "Pul mablag'lari va hisob-kitoblar auditi", "Asosiy vositalar va tovar-moddiy zaxiralar auditi",
         "Daromad va xarajatlar auditi", "Auditorlik hisoboti va xulosasi", "Ichki audit va auditor etikasi"],
        ["Kompyuterlashgan muhitda audit", "Soliq auditi asoslari"]),
    "Bank ishi": ("iqt", "Tijorat banklari faoliyati: passiv va aktiv operatsiyalar, kredit, hisob-kitoblar, bank riski va nazorat.",
        ["Bank tizimi va tijorat banklarining funksiyalari", "Bank resurslari va passiv operatsiyalar", "Depozit operatsiyalari",
         "Bank kapitali va uning yetarliligi", "Kredit operatsiyalari va kreditlash tamoyillari", "Kredit riskini baholash",
         "Naqd pulsiz hisob-kitoblar", "Valyuta operatsiyalari", "Bank likvidligini boshqarish", "Investitsiya operatsiyalari",
         "Bank riski va uni boshqarish", "Markaziy bank tomonidan bank nazorati"],
        ["Raqamli bank xizmatlari", "Islom banki asoslari"]),
    "Dasturlash asoslari": ("it", "Algoritmlash va dasturlash: o'zgaruvchilar, boshqaruv tuzilmalari, funksiyalar, massivlar, fayllar, OOP asoslari.",
        ["Algoritm tushunchasi va blok-sxemalar", "Dasturlash tili sintaksisi va o'zgaruvchilar", "Ma'lumot turlari va operatorlar",
         "Shart operatorlari", "Takrorlash operatorlari (sikllar)", "Funksiyalar va parametrlar", "Massivlar va ro'yxatlar",
         "Satrlar bilan ishlash", "Fayllar bilan ishlash", "Rekursiya", "Obyektga yo'naltirilgan dasturlash asoslari", "Xatolarni qayta ishlash va dasturni sozlash"],
        ["Saralash va qidirish algoritmlari", "Git va versiyalarni boshqarish"]),
    "Ingliz tili": ("til", "Umumiy va akademik ingliz tili: grammatika, leksika, tinglab tushunish, o'qish, yozish va gapirish ko'nikmalari (B1–B2).",
        ["Present tenses and daily routines", "Past tenses and narratives", "Future forms and plans", "Modal verbs and obligation",
         "Conditionals and hypothetical situations", "Passive voice in academic texts", "Reported speech", "Academic reading strategies",
         "Paragraph and essay writing", "Listening for gist and detail", "Presentations and public speaking", "Business correspondence and e-mails"],
        ["IELTS writing task 1: describing graphs", "Phrasal verbs in context"]),
    "Loyiha boshqaruvi": ("biz", "Loyiha hayot sikli, rejalashtirish, muddat va resurslar, byudjet, risklar, jamoa va loyihani yakunlash.",
        ["Loyiha tushunchasi va loyiha hayot sikli", "Loyiha tashabbusi va ustavi", "Loyiha ko'lamini rejalashtirish (WBS)",
         "Loyiha jadvali va tarmoq grafigi", "Kritik yo'l usuli", "Loyiha resurslarini rejalashtirish", "Loyiha byudjeti va xarajatlar nazorati",
         "Loyiha risklarini boshqarish", "Loyiha jamoasi va kommunikatsiyalar", "Loyiha sifatini boshqarish", "Agile va Scrum yondashuvlari",
         "Loyihani yakunlash va baholash"],
        ["Loyiha portfelini boshqarish", "Loyiha boshqaruvi dasturiy vositalari"]),
    "Ma'lumotlar bazasi": ("it", "Relyatsion ma'lumotlar bazalari: modellash, normallashtirish, SQL, tranzaksiyalar, indekslar va xavfsizlik.",
        ["Ma'lumotlar bazasi tushunchasi va MBBT", "Ma'lumotlar modellari", "ER-modellash", "Relyatsion model va kalitlar",
         "Normallashtirish va normal formalar", "SQL: ma'lumotlarni tanlash (SELECT)", "SQL: jadvallarni birlashtirish (JOIN)",
         "SQL: agregat funksiyalar va guruhlash", "Ma'lumotlarni o'zgartirish (INSERT, UPDATE, DELETE)", "Indekslar va so'rovlarni optimallashtirish",
         "Tranzaksiyalar va parallel ishlash", "Ma'lumotlar bazasi xavfsizligi va zaxira nusxa"],
        ["NoSQL ma'lumotlar bazalari", "Saqlanadigan protseduralar va triggerlar"]),
    "Marketing asoslari": ("biz", "Marketing kontseptsiyalari: bozor tadqiqoti, iste'molchi, segmentatsiya, marketing kompleksi (4P).",
        ["Marketingning mohiyati va kontseptsiyalari", "Marketing muhiti", "Marketing tadqiqotlari", "Iste'molchi xulqi",
         "Bozorni segmentatsiyalash", "Maqsadli bozor va pozitsiyalash", "Tovar siyosati", "Narx siyosati", "Taqsimot siyosati",
         "Marketing kommunikatsiyalari", "Brend va brendni boshqarish", "Marketing rejasi"],
        ["Raqamli marketing asoslari", "Xizmatlar marketingi"]),
    "Menejment asoslari": ("biz", "Boshqaruv nazariyasi va amaliyoti: rejalashtirish, tashkil etish, motivatsiya, nazorat, yetakchilik va qarorlar.",
        ["Menejmentning mohiyati va funksiyalari", "Boshqaruv nazariyalari evolyutsiyasi", "Tashkilot va uning muhiti",
         "Rejalashtirish va strategik boshqaruv", "Tashkiliy tuzilmalar", "Motivatsiya nazariyalari", "Nazorat funksiyasi",
         "Boshqaruv qarorlarini qabul qilish", "Yetakchilik va boshqaruv uslublari", "Kommunikatsiyalar menejmenti",
         "Guruh dinamikasi va nizolarni boshqarish", "Menejer etikasi va ijtimoiy mas'uliyat"],
        ["Vaqtni boshqarish", "O'zgarishlarni boshqarish"]),
    "Oliy matematika": ("iqt", "Iqtisodchilar uchun oliy matematika: chiziqli algebra, analitik geometriya, differensial va integral hisob.",
        ["Matritsalar va ular ustida amallar", "Determinantlar", "Chiziqli tenglamalar sistemasi", "Vektorlar algebrasi",
         "Tekislikdagi analitik geometriya", "Funksiya va limit", "Hosila va differensial", "Hosilaning iqtisodiy tatbiqlari",
         "Ko'p o'zgaruvchili funksiyalar", "Aniqmas integral", "Aniq integral va uning tatbiqlari", "Differensial tenglamalar"],
        ["Qatorlar", "Chiziqli dasturlash elementlari"]),
    "Pul va kredit": ("iqt", "Pul nazariyasi, pul muomalasi, inflyatsiya, kredit tizimi, banklar va pul-kredit siyosati.",
        ["Pulning kelib chiqishi va mohiyati", "Pulning funksiyalari", "Pul muomalasi va pul massasi", "Pul tizimi",
         "Inflyatsiya va uning turlari", "Kreditning mohiyati va shakllari", "Foiz stavkasi", "Kredit tizimi va banklar",
         "Markaziy bank va uning funksiyalari", "Pul-kredit siyosati", "Valyuta tizimi va valyuta kursi", "Xalqaro kredit munosabatlari"],
        ["Raqamli valyutalar", "Mikromoliya tashkilotlari"]),
    "Risk menejmenti": ("iqt", "Moliyaviy va operatsion risklarni aniqlash, baholash, boshqarish usullari va risk madaniyati.",
        ["Risk tushunchasi va tasnifi", "Risk menejmenti jarayoni", "Risklarni aniqlash usullari", "Risklarni sifat jihatidan baholash",
         "Risklarni miqdoriy baholash", "VaR usuli", "Kredit riski", "Bozor riski", "Likvidlik riski", "Operatsion risk",
         "Risklarni sug'urtalash va xejirlash", "Korporativ risk menejmenti tizimi"],
        ["Stress-testlash", "Bazel standartlari"]),
    "Tarmoqlar": ("it", "Kompyuter tarmoqlari: OSI va TCP/IP modellari, adreslash, marshrutlash, kommutatsiya, simsiz tarmoqlar va xavfsizlik.",
        ["Kompyuter tarmoqlari tushunchasi va topologiyalar", "OSI modeli", "TCP/IP protokollar steki", "Fizik qatlam va uzatish muhitlari",
         "Ethernet va kommutatorlar", "IP adreslash va qism tarmoqlar", "Marshrutlash asoslari", "Transport qatlami: TCP va UDP",
         "DNS va DHCP xizmatlari", "Simsiz tarmoqlar", "Virtual lokal tarmoqlar (VLAN)", "Tarmoq xavfsizligi asoslari"],
        ["IPv6 protokoli", "Tarmoqni monitoring qilish"]),
    "Biznesni rejalashtirish": ("biz", "Biznes-reja tuzish: bozor tahlili, marketing, ishlab chiqarish, moliyaviy reja, risklar va investitsiya.",
        ["Biznesni rejalashtirishning mohiyati", "Biznes-reja tuzilmasi", "Biznes g'oya va rezyume", "Bozor va raqobat tahlili",
         "Marketing rejasi", "Ishlab chiqarish rejasi", "Tashkiliy reja", "Moliyaviy reja", "Zararsizlik nuqtasi tahlili",
         "Investitsiya samaradorligi ko'rsatkichlari", "Biznes risklari", "Biznes-rejani taqdim etish"],
        ["Startap va venchur moliyalashtirish", "Biznes model kanvasi"]),
    "Marketing": ("biz", "Marketing strategiyasi va boshqaruvi: tadqiqot, segmentatsiya, marketing kompleksi, raqamli marketing va nazorat.",
        ["Marketing strategiyasining mohiyati", "Marketing axborot tizimi", "Bozor tadqiqoti", "Iste'molchi xulqi",
         "Segmentatsiya va pozitsiyalash", "Tovar va assortiment siyosati", "Narx strategiyalari", "Taqsimot kanallari",
         "Reklama va sotishni rag'batlantirish", "Raqamli marketing", "Xalqaro marketing", "Marketing nazorati"],
        ["Mijoz bilan munosabatlarni boshqarish (CRM)", "Brend kapitali"]),
    "FinTech asoslari": ("iqt", "Moliyaviy texnologiyalar: raqamli to'lovlar, blokcheyn, kraudfanding, robo-maslahatchilar, regulyativ texnologiyalar.",
        ["FinTech tushunchasi va rivojlanishi", "Raqamli to'lov tizimlari", "Elektron hamyonlar va mobil banking", "Blokcheyn texnologiyasi",
         "Kriptovalyutalar", "Kraudfanding va P2P kreditlash", "Robo-maslahatchilar", "Sun'iy intellekt moliyada", "InsurTech",
         "RegTech va SupTech", "FinTech risklari va kiberxavfsizlik", "FinTechni tartibga solish"],
        ["Ochiq banking va API", "Markaziy bank raqamli valyutasi"]),
    "Korporativ moliya": ("iqt", "Korxona moliyasini boshqarish: pulning vaqt qiymati, kapital qiymati, investitsiya qarorlari, kapital tuzilmasi, dividendlar.",
        ["Korporativ moliyaning mohiyati va maqsadlari", "Moliyaviy hisobotlar tahlili", "Pulning vaqt qiymati", "Risk va daromadlilik",
         "Obligatsiyalar va aksiyalarni baholash", "Kapital qiymati (WACC)", "Investitsiya loyihalarini baholash (NPV, IRR)",
         "Kapital tuzilmasi", "Dividend siyosati", "Aylanma kapitalni boshqarish", "Qisqa muddatli moliyalashtirish", "Qo'shilish va qo'shib olish"],
        ["Korporativ boshqaruv", "Opsionlar va real opsionlar"]),
    "Moliya": ("iqt", "Moliya tizimi: davlat moliyasi, byudjet, soliqlar, korxona moliyasi, moliya bozori va moliyaviy nazorat.",
        ["Moliyaning mohiyati va funksiyalari", "Moliya tizimi", "Moliyaviy siyosat", "Davlat byudjeti", "Soliqlar va soliq tizimi",
         "Davlat krediti va qarzi", "Byudjetdan tashqari jamg'armalar", "Korxonalar moliyasi", "Uy xo'jaliklari moliyasi",
         "Moliya bozori", "Sug'urta", "Moliyaviy nazorat"],
        ["Mahalliy moliya", "Xalqaro moliya"]),
    "Moliyaviy matematika": ("iqt", "Moliyaviy hisob-kitoblar: oddiy va murakkab foizlar, diskontlash, annuitetlar, kredit to'lovlari, obligatsiyalar.",
        ["Oddiy foizlar", "Murakkab foizlar", "Nominal va samarali foiz stavkalari", "Diskontlash", "Inflyatsiyani hisobga olish",
         "Pul oqimlari", "Annuitetlar", "Kreditni so'ndirish rejalari", "Obligatsiyalar daromadliligi", "Investitsiya loyihalarini baholash",
         "Lizing to'lovlarini hisoblash", "Moliyaviy ekvivalentlik"],
        ["Ipoteka kreditlari hisob-kitobi", "Sug'urta hisob-kitoblari"]),
    "Buxgalteriya hisobi": ("iqt", "Buxgalteriya hisobi nazariyasi va amaliyoti: hisobvaraqlar, ikki yoqlama yozuv, aktivlar, majburiyatlar, moliyaviy natija.",
        ["Buxgalteriya hisobining mohiyati va predmeti", "Buxgalteriya balansi", "Hisobvaraqlar va ikki yoqlama yozuv",
         "Hisobvaraqlar rejasi", "Birlamchi hujjatlar va hujjat aylanishi", "Pul mablag'lari hisobi", "Asosiy vositalar hisobi",
         "Tovar-moddiy zaxiralar hisobi", "Mehnat va ish haqi hisobi", "Ishlab chiqarish xarajatlari hisobi", "Daromadlar va moliyaviy natijalar hisobi",
         "Moliyaviy hisobot tuzish"],
        ["Nomoddiy aktivlar hisobi", "Inventarizatsiya"]),
    "Byudjet tizimi": ("iqt", "Davlat byudjeti tizimi: byudjet jarayoni, daromad va xarajatlar, byudjetlararo munosabatlar, g'aznachilik ijrosi.",
        ["Byudjet tizimi va tamoyillari", "Byudjet tasnifi", "Byudjet jarayoni", "Davlat byudjeti daromadlari", "Davlat byudjeti xarajatlari",
         "Byudjet taqchilligi va uni moliyalashtirish", "Byudjetlararo munosabatlar", "Mahalliy byudjetlar", "G'aznachilik ijrosi",
         "Byudjet tashkilotlari moliyasi", "Ochiq byudjet va fuqarolar ishtiroki", "Byudjet nazorati"],
        ["Dasturiy byudjetlashtirish", "O'rta muddatli byudjet rejalashtirish"]),
    "Moliyaviy hisobot (IFRS)": ("iqt", "Xalqaro moliyaviy hisobot standartlari: kontseptual asos, moliyaviy holat, foyda va zarar, pul oqimlari, asosiy standartlar.",
        ["IFRS kontseptual asosi", "Moliyaviy hisobot taqdimoti (IAS 1)", "Moliyaviy holat to'g'risidagi hisobot", "Foyda va zarar hamda boshqa umumlashgan daromad",
         "Pul oqimlari to'g'risidagi hisobot (IAS 7)", "Zaxiralar (IAS 2)", "Asosiy vositalar (IAS 16)", "Ijara (IFRS 16)",
         "Xaridorlar bilan shartnomalardan tushum (IFRS 15)", "Moliyaviy instrumentlar (IFRS 9)", "Aktivlarning qadrsizlanishi (IAS 36)",
         "Konsolidatsiyalangan moliyaviy hisobot"],
        ["Foyda solig'i (IAS 12)", "IFRSga birinchi marta o'tish (IFRS 1)"]),
    "Pedagogika": ("ped", "Pedagogika fanining nazariy asoslari: ta'lim va tarbiya jarayoni, didaktika, o'qitish metodlari, pedagogik texnologiyalar.",
        ["Pedagogikaning predmeti va vazifalari", "Pedagogika tarixi", "Shaxs rivojlanishi va tarbiya", "Ta'lim tizimi",
         "Didaktika asoslari", "O'qitish tamoyillari", "O'qitish metodlari", "Ta'limni tashkil etish shakllari", "Tarbiya nazariyasi",
         "Oila tarbiyasi", "Pedagogik texnologiyalar", "O'qituvchi kasbiy mahorati"],
        ["Inklyuziv ta'lim", "Pedagogik diagnostika"]),
    "Umumiy psixologiya": ("ped", "Psixika va ong: sezgi, idrok, diqqat, xotira, tafakkur, nutq, hissiyot, iroda va shaxs psixologiyasi.",
        ["Psixologiya fanining predmeti va metodlari", "Psixika va ong", "Faoliyat psixologiyasi", "Sezgi", "Idrok", "Diqqat",
         "Xotira", "Tafakkur", "Nutq", "Hissiyot va emotsiyalar", "Iroda", "Shaxs, temperament va xarakter"],
        ["Qobiliyatlar", "Tasavvur"]),
    "Didaktika": ("ped", "Ta'lim nazariyasi: ta'lim mazmuni, tamoyillari, metodlari, vositalari, shakllari va natijalarni baholash.",
        ["Didaktikaning predmeti va vazifalari", "Ta'lim jarayonining mohiyati", "Ta'lim mazmuni va davlat ta'lim standartlari",
         "O'qitish tamoyillari", "O'qitish metodlari", "O'qitish vositalari", "Dars va uning turlari", "Ta'limni tashkil etish shakllari",
         "Muammoli ta'lim", "Interfaol metodlar", "Bilimlarni nazorat qilish va baholash", "Ta'limda differensiatsiya va individuallashtirish"],
        ["Masofaviy ta'lim didaktikasi", "Dars tahlili"]),
    "Yosh psixologiyasi": ("ped", "Inson psixik rivojlanishining yosh davrlari: go'daklik, bolalik, o'smirlik, yoshlik, yetuklik va keksalik.",
        ["Yosh psixologiyasining predmeti va metodlari", "Psixik rivojlanish nazariyalari", "Yosh davrlari tasnifi", "Go'daklik davri",
         "Ilk bolalik davri", "Maktabgacha yosh davri", "Kichik maktab yoshi", "O'smirlik davri", "Ilk yoshlik davri",
         "Yetuklik davri", "Keksalik davri psixologiyasi", "Yosh inqirozlari"],
        ["Iqtidorli bolalar psixologiyasi", "Raqamli muhit va bola rivojlanishi"]),
    "O'zbekiston tarixi": ("gum", "O'zbekiston hududidagi davlatchilik va jamiyat tarixi: qadimgi davrdan mustaqillik va Yangi O'zbekistongacha.",
        ["O'zbekiston tarixi fanining predmeti va manbalari", "Qadimgi davlatchilik: Baqtriya, So'g'd, Xorazm", "Ahamoniylar va Aleksandr yurishlari",
         "Kushon podsholigi", "Arab xalifaligi davri", "Somoniylar va Qoraxoniylar", "Mo'g'ullar istilosi", "Amir Temur va Temuriylar davlati",
         "Xonliklar davri", "Rossiya imperiyasi mustamlakachiligi", "Sovet davri", "Mustaqil O'zbekiston va Yangi O'zbekiston islohotlari"],
        ["Jadidchilik harakati", "Buyuk ipak yo'li"]),
    "Xalqaro huquq": ("gum", "Xalqaro ommaviy huquq: manbalar, subyektlar, xalqaro shartnomalar, diplomatik huquq, inson huquqlari, nizolarni hal etish.",
        ["Xalqaro huquq tushunchasi va tizimi", "Xalqaro huquq manbalari", "Xalqaro huquq subyektlari", "Xalqaro huquqning asosiy tamoyillari",
         "Xalqaro shartnomalar huquqi", "Diplomatik va konsullik huquqi", "Xalqaro tashkilotlar huquqi", "Inson huquqlarining xalqaro himoyasi",
         "Xalqaro dengiz huquqi", "Xalqaro iqtisodiy huquq", "Xalqaro nizolarni tinch yo'l bilan hal etish", "Xalqaro javobgarlik"],
        ["Xalqaro gumanitar huquq", "Xalqaro jinoyat huquqi"]),
    "Diplomatiya tarixi": ("gum", "Diplomatiyaning paydo bo'lishi va rivojlanishi: qadimgi davrdan zamonaviy ko'p tomonlama diplomatiyagacha.",
        ["Diplomatiya tushunchasi va manbalari", "Qadimgi dunyo diplomatiyasi", "O'rta asrlar diplomatiyasi", "Amir Temur diplomatiyasi",
         "Vestfal tinchligi va yevropa diplomatiyasi", "Vena kongressi", "Birinchi jahon urushi va Versal tizimi", "Ikkinchi jahon urushi davri diplomatiyasi",
         "BMTning tashkil topishi", "Sovuq urush davri diplomatiyasi", "Ko'p tomonlama diplomatiya", "O'zbekiston tashqi siyosati va diplomatiyasi"],
        ["Iqtisodiy diplomatiya", "Raqamli diplomatiya"]),
    "Amaliy grammatika": ("til", "Ingliz tili amaliy grammatikasi: so'z turkumlari, zamonlar, modal fe'llar, gap tuzilishi va murakkab gaplar.",
        ["Nouns: number and case", "Articles", "Pronouns", "Adjectives and adverbs: degrees of comparison", "Present tense forms",
         "Past tense forms", "Future tense forms", "Perfect tenses", "Modal verbs", "Passive voice", "Non-finite forms of the verb", "Complex sentences"],
        ["Sequence of tenses", "Subjunctive mood"]),
    "Fonetika": ("til", "Ingliz tili fonetikasi: nutq tovushlari, unli va undoshlar, bo'g'in, urg'u, intonatsiya va transkripsiya.",
        ["Phonetics as a science", "Organs of speech", "Classification of English vowels", "Classification of English consonants",
         "Phonemes and allophones", "Phonetic transcription", "Syllable structure", "Word stress", "Sentence stress and rhythm",
         "Intonation patterns", "Connected speech: assimilation and elision", "Received Pronunciation and General American"],
        ["Phonetic styles", "Teaching pronunciation"]),
    "Leksikologiya": ("til", "Ingliz tili leksikologiyasi: so'z va ma'no, so'z yasalishi, frazeologiya, etimologiya, leksik qatlamlar.",
        ["Lexicology as a branch of linguistics", "The word as a basic unit", "Word meaning and semantic structure", "Polysemy and homonymy",
         "Synonyms and antonyms", "Morphological structure of words", "Word-formation: affixation", "Conversion and compounding",
         "Etymology of English vocabulary", "Phraseology", "Stylistic layers of vocabulary", "Lexicography"],
        ["Neologisms", "Variants of English"]),
    "Tarjima nazariyasi": ("til", "Tarjima nazariyasi: ekvivalentlik, tarjima transformatsiyalari, leksik va grammatik muammolar, tarjima turlari.",
        ["Tarjima nazariyasining predmeti", "Tarjima tarixi", "Tarjima turlari va tasnifi", "Ekvivalentlik va adekvatlik",
         "Tarjima birligi", "Leksik transformatsiyalar", "Grammatik transformatsiyalar", "Frazeologizmlar tarjimasi", "Realiyalar tarjimasi",
         "Badiiy tarjima", "Ilmiy-texnik tarjima", "Og'zaki va sinxron tarjima"],
        ["Mashina tarjimasi", "Tarjima tahriri"]),
    "Ekonometrika": ("iqt", "Iqtisodiy jarayonlarni statistik modellashtirish: regressiya, korrelyatsiya, multikollinearlik, vaqt qatorlari va prognoz.",
        ["Ekonometrikaning predmeti va modellari", "Juft korrelyatsiya", "Juft chiziqli regressiya", "Eng kichik kvadratlar usuli",
         "Regressiya parametrlarining ahamiyatliligi", "Ko'p omilli regressiya", "Multikollinearlik", "Geteroskedastiklik", "Avtokorrelyatsiya",
         "Soxta o'zgaruvchilar", "Vaqt qatorlari modellari", "Ekonometrik prognozlash"],
        ["Panel ma'lumotlar modellari", "Tenglamalar sistemasi"]),
    "Makroiqtisodiyot": ("iqt", "Milliy iqtisodiyot: YaIM, iqtisodiy o'sish, ishsizlik, inflyatsiya, fiskal va monetar siyosat, ochiq iqtisodiyot.",
        ["Makroiqtisodiyotning predmeti", "Milliy hisoblar tizimi va YaIM", "Yalpi talab va yalpi taklif", "Iste'mol, jamg'arma va investitsiyalar",
         "Multiplikator samarasi", "Iqtisodiy sikllar", "Ishsizlik", "Inflyatsiya", "Fiskal siyosat", "Pul bozori va monetar siyosat",
         "Iqtisodiy o'sish", "Ochiq iqtisodiyot va to'lov balansi"],
        ["IS-LM modeli", "Davlat qarzi"]),
    "Mikroiqtisodiyot": ("iqt", "Bozor mexanizmi: talab va taklif, iste'molchi va ishlab chiqaruvchi xulqi, bozor tuzilmalari, omillar bozori.",
        ["Mikroiqtisodiyotning predmeti", "Talab va taklif", "Bozor muvozanati", "Elastiklik", "Iste'molchi xulqi nazariyasi",
         "Ishlab chiqarish nazariyasi", "Ishlab chiqarish xarajatlari", "Mukammal raqobat", "Monopoliya", "Monopolistik raqobat va oligopoliya",
         "Ishlab chiqarish omillari bozori", "Bozor muvaffaqiyatsizliklari"],
        ["O'yinlar nazariyasi elementlari", "Axborot asimmetriyasi"]),
    "Statistika": ("iqt", "Statistik kuzatish va tahlil: guruhlash, o'rtacha va variatsiya ko'rsatkichlari, indekslar, tanlama, dinamika qatorlari.",
        ["Statistikaning predmeti va usullari", "Statistik kuzatish", "Statistik guruhlash", "Absolyut va nisbiy miqdorlar", "O'rtacha miqdorlar",
         "Variatsiya ko'rsatkichlari", "Tanlama kuzatish", "Dinamika qatorlari", "Indekslar", "Korrelyatsion tahlil",
         "Statistik grafiklar", "Ijtimoiy-iqtisodiy statistika ko'rsatkichlari"],
        ["Aholi statistikasi", "Milliy hisoblar statistikasi"]),
}

# Demo sillabuslarga "begona" mavzu sifatida qo'shiladigan boshqa soha mavzulari (mavzular mosligi tekshiruvini ko'rsatish uchun)
FOREIGN = ["Hujayra tuzilishi va funksiyalari", "Fotosintez jarayoni", "Qadimgi Yunon dramaturgiyasi", "Futbol o'yini qoidalari",
           "Organik kimyo asoslari", "Kvant mexanikasi elementlari"]

def ref_rows():
    """CATALOG → syl_ref yozuvlari: har fan uchun 2 ta tayanch OTM (namuna)."""
    out = []
    for subj, (field, desc, core, extra) in CATALOG.items():
        a, b = UNIS[field]
        out.append((subj, a, json.dumps(core, ensure_ascii=False), desc))
        bl = [t for i, t in enumerate(core) if i not in (3, 8)] + list(extra)
        out.append((subj, b, json.dumps(bl, ensure_ascii=False), desc))
    return out

# ---------------------------------------------------------------------------------------------
# demo holat
# ---------------------------------------------------------------------------------------------
REVIEW_NOTES = {
    "relevance": "«{t}» mavzusi fan mazmuniga mos emas — olib tashlang yoki fan bo'yicha mavzu bilan almashtiring.",
    "missing": "Tayanch OTM dasturidagi «{t}» mavzusi yo'q — kiritish tavsiya etiladi.",
    "hours": "Soatlar o'quv reja me'yoriga mos emas: {t}. Taqsimotni tuzating.",
    "lit": "Adabiyotlar ro'yxatini so'nggi 5 yil nashrlari bilan to'ldiring (kamida 2 ta xorijiy manba).",
}

def _users(con):
    ak = db.one(con, "SELECT id, full_name FROM users WHERE role='akademik' ORDER BY id LIMIT 1")
    pr = db.one(con, "SELECT id, full_name FROM users WHERE role='prorektor_oquv' ORDER BY id LIMIT 1")
    heads = {r["department_id"]: r for r in db.rows(con, "SELECT id, full_name, department_id FROM users WHERE role='kafedra' ORDER BY id")}
    return ak, pr, heads

def run(con, force: bool = False) -> dict:
    from . import syllabus as SY
    SY.init_tables(con)
    if not db.one(con, "SELECT 1 x FROM users"):
        return {"skipped": "users bo'sh"}
    # tayanch OTM katalogi har doim yangilanadi (idempotent)
    con.execute("DELETE FROM syl_ref")
    con.executemany("INSERT INTO syl_ref(subject, university, topics, description, sample) VALUES(?,?,?,?,1)", ref_rows())
    con.commit()
    if db.one(con, "SELECT 1 x FROM syl_items") and not force:
        return {"skipped": "syl_items allaqachon to'ldirilgan"}
    if not db.one(con, "SELECT 1 x FROM users WHERE role='kafedra'"):
        return {"skipped": "kafedra akkauntlari hali yo'q — server ishga tushganda (syllabus.init) to'ldiriladi"}
    for t in ("syl_items", "syl_versions", "syl_log", "syl_tasks", "syl_task_units", "syl_load_plans"):
        con.execute(f"DELETE FROM {t}")
    con.commit()
    R = random.Random(2026)
    today = SY.today()
    ak, pr, heads = _users(con)
    if not ak or not pr or not heads:
        # app/seed.py ichida: kafedra mudirlari akkauntlari main.py ishga tushganda yaratiladi — demo holat o'shanda (syllabus.init) to'ldiriladi
        con.commit()
        return {"skipped": "akademik/prorektor/kafedra akkauntlari hali yo'q — server ishga tushganda to'ldiriladi"}
    pairs = [p for p in SY.subject_pairs(con) if p["subject"] in CATALOG]
    # o'qituvchi #109 (demo o'qituvchi akkaunti) — kaf4 fanlari: qaytarilgan / jarayonda / tasdiqlangan
    fixed = {("Buxgalteriya hisobi", 4): ("qaytarilgan", 109), ("Moliyaviy hisobot (IFRS)", 4): ("jarayonda", 109),
             ("Moliyaviy matematika", 4): ("tasdiqlangan", 109), ("Byudjet tizimi", 4): ("soralgan", None),
             ("Korporativ moliya", 4): ("kelishuv:kafedra", None), ("Ingliz tili", 4): ("tekshiruvda", None)}
    plan = (["tasdiqlangan"] * 11 + ["kelishuv:kafedra"] * 2 + ["kelishuv:akademik"] * 2 + ["kelishuv:prorektor"] * 3 +
            ["tekshiruvda"] * 6 + ["qaytarilgan"] * 5 + ["jarayonda"] * 7 + ["soralgan"] * 4)
    R.shuffle(plan)
    req_at = dt.datetime.combine(today - dt.timedelta(days=58), dt.time(10, 15))
    stats = {}
    k = 0
    for p in pairs:
        key = (p["subject"], p["department_id"])
        if key in fixed:
            st, tid = fixed[key]
        else:
            st, tid = plan[k % len(plan)], None; k += 1
        stage = None
        if st.startswith("kelishuv:"):
            st, stage = "kelishuvda", st.split(":")[1]
        if st != "soralgan" and not tid:
            tid = p["lead_teacher"]
        overdue = st in ("soralgan", "jarayonda", "qaytarilgan") and R.random() < 0.45 and key not in fixed
        if st in ("tasdiqlangan", "kelishuvda", "tekshiruvda"):
            due = today - dt.timedelta(days=R.randint(5, 30))
        elif overdue:
            due = today - dt.timedelta(days=R.randint(2, 16))
        else:
            due = today + dt.timedelta(days=R.randint(3, 18))
        if key == ("Moliyaviy hisobot (IFRS)", 4): due = today + dt.timedelta(days=5)
        if key == ("Buxgalteriya hisobi", 4): due = today + dt.timedelta(days=3)
        if key == ("Byudjet tizimi", 4): due = today - dt.timedelta(days=4)
        iid = SY.create_item(con, p, due.isoformat(), ak, note="Joriy semestr uchun fan dasturi (sillabus) tayyorlansin.", ts=req_at + dt.timedelta(minutes=k))
        clock = [req_at + dt.timedelta(days=R.randint(1, 4), hours=R.randint(0, 5))]
        if st in ("tekshiruvda", "kelishuvda", "qaytarilgan"):   # hali yakunlanmagan ish — oxirgi voqealar yaqin kunlarda
            clock = [dt.datetime.combine(today - dt.timedelta(days=R.randint(11, 16)), dt.time(9, 0))]
        def tick(days_lo=1, days_hi=5):
            clock[0] = clock[0] + dt.timedelta(days=R.randint(days_lo, days_hi), hours=R.randint(1, 6), minutes=R.randint(0, 59))
            lim = dt.datetime.combine(today, dt.time(9, 0)) - dt.timedelta(hours=R.randint(1, 30))
            if clock[0] > lim: clock[0] = lim
            return clock[0].isoformat(timespec="seconds")
        head = heads.get(p["department_id"]) or ak
        if st == "soralgan":
            stats[st] = stats.get(st, 0) + 1; continue
        SY.seed_assign(con, iid, tid, head, tick(1, 3))
        field = CATALOG[p["subject"]][0]
        core = CATALOG[p["subject"]][2]
        if st == "jarayonda":
            if R.random() < 0.5:   # qisman to'ldirilgan qoralama
                SY.seed_draft(con, iid, _content(R, p, core, "draft", field))
            stats[st] = stats.get(st, 0) + 1; continue
        # birinchi versiya topshirildi
        scen = "returned" if st == "qaytarilgan" else R.choice(["good", "good", "minor"])
        SY.seed_submit(con, iid, _content(R, p, core, scen, field), tid, head, tick(4, 12))
        if st == "qaytarilgan":
            item = db.one(con, "SELECT * FROM syl_items WHERE id=?", (iid,))
            chk = SY.latest_check(con, item)
            SY.seed_review(con, iid, ak, "qaytarish", _comment(chk), tick(1, 3))
            if key == ("Buxgalteriya hisobi", 4) or R.random() < 0.3:
                # ikkinchi raund: tuzatib qayta topshirilgan va yana qaytarilgan (versiyalar tarixi)
                if key != ("Buxgalteriya hisobi", 4):
                    SY.seed_submit(con, iid, _content(R, p, core, "minor", field), tid, head, tick(1, 3))
                    SY.seed_review(con, iid, ak, "qaytarish", REVIEW_NOTES["lit"], tick(1, 2))
            stats[st] = stats.get(st, 0) + 1; continue
        if st == "tekshiruvda":
            stats[st] = stats.get(st, 0) + 1; continue
        # tekshiruvdan o'tdi → kelishuv: kafedra → akademik → prorektor
        if scen == "minor" and R.random() < 0.5:
            SY.seed_review(con, iid, ak, "qaytarish", REVIEW_NOTES["lit"], tick(1, 2))
            SY.seed_submit(con, iid, _content(R, p, core, "good", field), tid, head, tick(1, 3))
        SY.seed_review(con, iid, ak, "yuborish", "Mavzular va soatlar o'quv rejaga mos. Kafedra kelishuviga yuborildi.", tick(1, 3))
        if stage == "kafedra": stats["kelishuv:kafedra"] = stats.get("kelishuv:kafedra", 0) + 1; continue
        SY.seed_review(con, iid, head, "maqullash", "Kafedra yig'ilishida ko'rib chiqildi va ma'qullandi.", tick(1, 3))
        if stage == "akademik": stats["kelishuv:akademik"] = stats.get("kelishuv:akademik", 0) + 1; continue
        SY.seed_review(con, iid, ak, "maqullash", "", tick(1, 2))
        if stage == "prorektor": stats["kelishuv:prorektor"] = stats.get("kelishuv:prorektor", 0) + 1; continue
        SY.seed_review(con, iid, pr, "maqullash", "Tasdiqlandi.", tick(1, 2))
        stats["tasdiqlangan"] = stats.get("tasdiqlangan", 0) + 1
    con.commit()
    _seed_tasks(con, R, today, ak, heads)
    _seed_load_plan(con, ak)
    con.commit()
    stats["items"] = db.one(con, "SELECT COUNT(*) n FROM syl_items")["n"]
    stats["ref"] = db.one(con, "SELECT COUNT(*) n FROM syl_ref")["n"]
    return stats

def _dist(total, n):
    """total soatni n mavzuga juft sonlarda taqsimlash (2 soatlik juftliklar)."""
    if n <= 0 or total <= 0: return [0] * max(n, 0)
    pairs = total // 2; base = pairs // n; rem = pairs - base * n
    return [2 * (base + (1 if i < rem else 0)) for i in range(n)]

def _content(R, p, core, scen, field):
    from . import syllabus as SY
    norm = SY.norm_for(p["subject"], p.get("field"))
    topics = list(core)
    if scen == "draft":
        topics = topics[: R.randint(5, 8)]
    elif scen == "minor":
        drop = R.sample(range(2, len(topics)), 1)
        topics = [t for i, t in enumerate(topics) if i not in drop]
    elif scen == "returned":
        drop = R.sample(range(2, len(topics)), 3)
        topics = [t for i, t in enumerate(topics) if i not in drop]
        topics.insert(R.randint(4, len(topics) - 1), R.choice(FOREIGN))
        topics.append(R.choice([f for f in FOREIGN if f not in topics]))
    n = len(topics)
    shift = -4 if scen == "returned" else 0          # qaytarilgan: ma'ruza soati me'yordan kam
    L, P, S, B = _dist(max(0, norm["lecture"] + shift), n), _dist(norm["practice"], n), _dist(norm["seminar"], n), _dist(norm["lab"], n)
    M = _dist(norm["self"] + (8 if scen == "returned" else 0), n)
    rows = [{"week": i + 1, "title": t, "lecture": L[i], "practice": P[i], "seminar": S[i], "lab": B[i], "self": M[i]} for i, t in enumerate(topics)]
    lit = {"iqt": ["Mankiw N.G. Principles of Economics. 9th ed. Cengage, 2021.", "Brealey R., Myers S., Allen F. Principles of Corporate Finance. McGraw-Hill, 2022.",
                   f"«{p['subject']}» fanidan o'quv qo'llanma. — T.: ISFT nashriyoti, 2024.", "O'zbekiston Respublikasi qonun hujjatlari ma'lumotlari milliy bazasi — lex.uz"],
           "biz": ["Kotler Ph., Keller K. Marketing Management. 16th ed. Pearson, 2022.", "Robbins S., Coulter M. Management. 15th ed. Pearson, 2021.",
                   f"«{p['subject']}» fanidan o'quv qo'llanma. — T.: ISFT nashriyoti, 2024."],
           "it": ["Silberschatz A. Database System Concepts. 7th ed. McGraw-Hill, 2020.", "Kurose J., Ross K. Computer Networking. 8th ed. Pearson, 2021.",
                  f"«{p['subject']}» fanidan laboratoriya ishlari to'plami. — T.: ISFT, 2025."],
           "ped": ["Pedagogika: darslik. — T.: O'qituvchi, 2021.", "Myers D. Psychology. 13th ed. Worth, 2021.", f"«{p['subject']}» fanidan o'quv qo'llanma. — T.: ISFT, 2024."],
           "til": ["Murphy R. English Grammar in Use. 5th ed. CUP, 2019.", "Oxford Advanced Learner's Dictionary. OUP, 2020.", f"«{p['subject']}» bo'yicha mashqlar to'plami. — T.: ISFT, 2025."],
           "gum": ["O'zbekiston tarixi: darslik. — T.: O'zbekiston, 2022.", "Shaw M. International Law. 9th ed. CUP, 2021.", f"«{p['subject']}» fanidan o'quv qo'llanma. — T.: ISFT, 2024."]}[field]
    if scen == "returned": lit = lit[:1]
    asm = {"joriy": 20, "oraliq": 30, "yakuniy": 50} if scen != "returned" else {"joriy": 20, "oraliq": 30, "yakuniy": 40}
    goal = f"Talabalarda «{p['subject']}» fani bo'yicha nazariy bilim va amaliy ko'nikmalarni shakllantirish."
    return {"topics": rows, "literature": lit, "assessment": asm, "goals": goal if scen != "draft" else ""}

def _comment(chk) -> str:
    parts = []
    rel = chk.get("relevance") or {}
    for t in (rel.get("flagged") or [])[:2]: parts.append(REVIEW_NOTES["relevance"].format(t=t))
    ref = chk.get("reference") or {}
    for t in (ref.get("missing") or [])[:2]: parts.append(REVIEW_NOTES["missing"].format(t=t))
    bad = [f"{r['label'].lower()} {r['plan']} soat (me'yor {r['norm']})" for r in (chk.get("hours") or {}).get("rows", []) if not r["ok"]]
    if bad: parts.append(REVIEW_NOTES["hours"].format(t="; ".join(bad[:2])))
    asm = chk.get("assessment") or {}
    if asm and not asm.get("ok"): parts.append(f"Baholash ulushlari yig'indisi {asm.get('sum')}% — 100% bo'lishi kerak.")
    return "\n".join(parts) or REVIEW_NOTES["lit"]

def _seed_tasks(con, R, today, ak, heads):
    from . import syllabus as SY
    deps = [d["id"] for d in db.rows(con, "SELECT id FROM departments ORDER BY id")]
    base = dt.datetime.combine(today, dt.time(9, 30))
    def ts(days, h=0): return (base - dt.timedelta(days=days, hours=h)).isoformat(timespec="seconds")
    t1 = SY.create_task(con, ak, "yuklama", "Bahorgi semestr uchun o'quv yuklama rejasini topshirish",
                        "Kafedra o'qituvchilari kesimida 2026-2027 o'quv yili bahorgi semestr yuklama rejasini (fan, guruhlar, potoklar, soatlar) "
                        "ilova qiling. Yuklama kalkulyatoridagi me'yorlardan foydalaning.", (today + dt.timedelta(days=5)).isoformat(), deps, ts(9))
    plan = {1: "topshirildi", 2: "qabul", 3: "qayta", 4: "yangi", 5: "topshirildi", 6: "qabul", 7: "yangi", 8: "topshirildi"}
    for d in deps:
        st = plan.get(d, "yangi")
        u = db.one(con, "SELECT id FROM syl_task_units WHERE task_id=? AND department_id=?", (t1, d))["id"]
        h = heads.get(d)
        if st == "yangi" or not h: continue
        SY.seed_task_submit(con, u, h, f"Yuklama rejasi ilova qilindi: {R.randint(9, 24)} nafar o'qituvchi, jami {R.randint(9, 19) * 1000 + R.randint(0, 999)} soat.", ts(R.randint(3, 6), R.randint(1, 5)))
        if st == "qabul": SY.seed_task_review(con, u, ak, "qabul", "Qabul qilindi.", ts(2, R.randint(1, 5)))
        if st == "qayta": SY.seed_task_review(con, u, ak, "qayta", "Potoklar soni guruhlar bilan mos emas (ma'ruza soatlari ikki marta hisoblangan). Qayta hisoblab yuboring.", ts(2, 2))
    t2 = SY.create_task(con, ak, "sillabus", "Sillabuslarni yangi o'quv rejaga moslashtirish (kredit soatlari)",
                        "Yangi o'quv rejaga ko'ra kredit soatlari o'zgargan fanlar sillabuslarini yangilang va qisqa ma'lumotnoma yuboring.",
                        (today - dt.timedelta(days=3)).isoformat(), [1, 4, 8], ts(16))
    for d, st in ((1, "qabul"), (4, "round2"), (8, "yangi")):
        u = db.one(con, "SELECT id FROM syl_task_units WHERE task_id=? AND department_id=?", (t2, d))["id"]
        h = heads.get(d)
        if st == "yangi" or not h: continue
        SY.seed_task_submit(con, u, h, "12 ta fan sillabusi yangilandi, ro'yxat ilova qilindi.", ts(10))
        if st == "qabul": SY.seed_task_review(con, u, ak, "qabul", "Rahmat, qabul qilindi.", ts(8))
        else:
            SY.seed_task_review(con, u, ak, "qayta", "Ro'yxatda «Byudjet tizimi» va «Moliyaviy hisobot (IFRS)» fanlari yo'q. To'ldiring.", ts(8))
            SY.seed_task_submit(con, u, h, "Ikki fan qo'shildi: Byudjet tizimi, Moliyaviy hisobot (IFRS). Yangilangan ro'yxat ilova qilindi.", ts(1, 3))
    SY.create_task(con, ak, "dastur", "Tayanch OTM fan dasturlari bilan solishtirma jadval",
                   "Kafedra fanlari bo'yicha tayanch OTM (TDIU, WIUT) dasturlari bilan mavzular solishtirmasini tayyorlang.",
                   (today + dt.timedelta(days=12)).isoformat(), [2, 3], ts(1))

def _seed_load_plan(con, ak):
    """Buxgalteriya hisobi kafedrasi uchun saqlangan yuklama rejasi (potok chegarasi 3)."""
    con.execute("INSERT OR REPLACE INTO syl_load_plans(department_id, params, updated_at, updated_by) VALUES(?,?,?,?)",
                (4, json.dumps({"settings": {"potok_max": 3}, "rows": {}}, ensure_ascii=False), clock.now().isoformat(timespec="seconds"), ak["id"]))

if __name__ == "__main__":
    from .db import connect
    c = connect()
    print(run(c, force="--force" in sys.argv))
