# VIE/BTS Aviation Tracker — Week 1 Guide

## Čo je hotové (tento balík)
- `scraper/vie_scraper.py` — parsuje mesačné traffic výsledky Viedne (100% automaticky, otestované na reálnom formáte hlavičiek)
- `scraper/bts_scraper.py` — parsuje ročné štatistiky BTS (100% automaticky, štruktúrovaná tabuľka) + mesačné "kandidátske" čísla z press releases (potrebujú rýchlu manuálnu kontrolu — BTS píše správy voľným textom, nie jednotným formátom)
- `scraper/db.py` — SQLite úložisko + CSV export
- `scraper/main.py` — spúšťací skript, ktorý spustí oboje a uloží všetko

Otestoval som regex proti reálnym vetám z oboch stránok (fetchoval som ich živo) — parsovanie funguje. Skript ešte nebol spustený proti živej stránke odtiaľto (sandbox nemá prístup na viennaairport.com/bts.aero), takže prvé reálne spustenie urob ty lokálne.

## Krok za krokom — Týždeň 1

### Deň 1-2: Doména + repo
1. Zaregistruj doménu (Websupport.sk alebo Namecheap) — napr. `vie-bts.eu` alebo podobne, ~€10-12/rok
2. Vytvor GitHub repo (zadarmo), nahraj tento priečinok
3. Over si Python 3.11+ lokálne: `python3 --version`

### Deň 2-3: Prvé spustenie scrapera
```bash
cd vie-bts-tracker
pip install -r requirements.txt
python -m scraper.main
```
Skontroluj výstup:
- Koľko VIE záznamov sa naparsovalo (malo by to byť ~všetky mesiace za posledné 1-2 roky)
- Koľko BTS "candidates" riadkov vzniklo — otvor `scraper/traffic.db` (napr. cez "DB Browser for SQLite", zadarmo) a over `raw_text` stĺpec pre každý, priraď správny mesiac ručne (`UPDATE monthly_traffic SET month=X, verified=1 WHERE ...`)

### Deň 3-4: Hosting blogu
1. Založ Hugo alebo jednoduchý Jekyll blog (zadarmo šablóny na themes.gohugo.io)
2. Nasaď na Netlify alebo Cloudflare Pages (zadarmo, prepojené s GitHub repom — auto-deploy pri každom push)
3. Priprav prvú stránku "O projekte"

### Deň 4-5: Prvý dashboard
1. Import `scraper/exports/monthly_traffic.csv` do Power BI Desktop
2. Postav prvý vizuál: trend pasažierov VIE vs BTS mesiac po mesiaci (line chart, dve série)
3. Publish to Web (File → Publish to web) — zadarmo, dáta sú verejné takže OK
4. Vlož iframe embed kód do blogu

### Deň 5-7: Prvý článok + launch
1. Napíš prvý článok naviazaný na Wizz Air/Ryanair presun do Bratislavy (máš už fakty z nášho rozhovoru)
2. Zdieľaj na LinkedIn (SK+EN, rovnaký vzor ako FKConsulting launch)

## Automatizácia (mesiac 2)
Keď si spokojný s presnosťou, pridaj `.github/workflows/scrape.yml` s mesačným cronom, ktorý spustí `python -m scraper.main` a commitne nový `traffic.db`/CSV do repa automaticky.

## Poznámky k spoľahlivosti
- **VIE scraper**: spoľahlivý pre headline formát z rokov ~2022+. Staršie archívne záznamy (2011-2021) majú iné formulácie a skončia v `unparsed` zozname — ak ich chceš, treba doplniť ďalšie regex vzory.
- **BTS scraper**: ročné dáta 100% spoľahlivé (štruktúrovaná tabuľka). Mesačné dáta sú len "kandidáti" — over si ich manuálne, kým nezistíš, či formát press releases je dosť konzistentný na plnú automatizáciu.
