# Content plan: weekly blog + LinkedIn

One topic per week. Every topic is published twice from the same facts: a blog post on fkslab.com
(Slovak, with English and German versions like the existing posts) and a LinkedIn post that points to it.
Nothing in this folder is published; it is a draft for approval.

## Rhythm

| Week | Date | Topic | Blog slug | Status |
|---|---|---|---|---|
| 1 | Tue 13 Oct | I rebuilt the report (story + Eurostat gap fill) | `novy-report-vie-bts` | written (branch `article/report-redesign` in the blog repo) |
| 2 | Tue 20 Oct | Bratislava is now one passenger for every five in Vienna | `bratislava-vs-viedn-velkost` | draft below |
| 3 | Tue 27 Oct | More flights, not bigger planes | `lety-nie-vacsie-lietadla` | draft below |
| 4 | Tue 3 Nov | Cheaper tickets in Slovakia, and Vienna's answer (tax, layoffs) | `letenky-slovensko-viedn` | brief + draft below, numbers to verify |
| 5 | Tue 10 Nov | Bratislava turns into a scheduled airport (and a domestic route is back) | `bratislava-pravidelne-linky` | brief |
| 6 | Tue 17 Nov | Where Vienna and Bratislava fly: hub versus holiday airport | `trasy-viedn-bratislava` | brief |
| 7 | Tue 24 Nov | Wizz Air left Vienna: what a flight-tracking feed shows | `wizz-air-viedn-bratislava` | brief |
| 8 | Tue 1 Dec | Why my "hourly" job ran every five hours | `hodinovy-job-kazdych-5-hodin` | brief |
| 9 | Tue 8 Dec | Where 15.8 million AI tokens went (building this with Claude) | `kam-isli-tokeny` | brief, needs your OK |

When a new official monthly release appears (BTS/VIE), swap that week's topic for a short "data drop":
three numbers, one chart, link to the dashboard.

## How each pair is produced

1. Numbers come from the report's own sources (Supabase tables, Eurostat `avia_paoa` / `avia_par_*`). Every
   figure below can be reproduced; the source is named next to it.
2. Blog post first (3 languages), published Tuesday morning. LinkedIn post the same day, link in the first
   comment (LinkedIn tends to show posts with the link in the body to fewer people).
3. Three hashtags at most: `#PowerBI #DataViz #Aviation`.
4. LinkedIn drafts are given in Slovak and English; use the language of the audience you want to reach.

## Checked facts (Eurostat `avia_paoa`, passengers on board, 2026-10-11)

| Fact | Value |
|---|---|
| Size ratio BTS / VIE, July | 2019: 10.4 %, 2024: 9.8 %, 2025: 10.8 %, **2026: 19.6 %** |
| Size ratio BTS / VIE, January | 2025: 4.5 %, **2026: 9.9 %** |
| July 2026 against July 2019 | BTS **187 %**, VIE **100 %** |
| Jan-Jul passengers | BTS 2024: 1.06 M, 2025: 1.23 M, **2026: 2.57 M (2.08x)**; VIE 2025: 18.23 M, **2026: 17.70 M (-2.9 %)** |
| Flights in July (commercial passenger flights) | BTS 2025: 2,701, **2026: 4,310 (+60 %)**; VIE 2025: 22,519, **2026: 21,572 (-4 %)** |
| Passengers per flight in July | BTS 2019: 100, 2025: 133, **2026: 144**; VIE 2019: 129, 2025: 147, **2026: 147** |
| Scheduled share of BTS passengers, July | 2024: 51 %, 2025: 56 %, **2026: 76 %**; VIE 98-99 % |
| Extra-EU share of BTS passengers, July | 2024: 46 %, 2025: 45 %, **2026: 36 %**; VIE 35-36 % |
| Domestic share of BTS passengers, July | 2025: 0.0 %, **2026: 3.4 %** |
| Seasonality (July / January) | BTS 2024: 4.3x, **2026: 3.2x**; VIE 1.6-1.9x |
| Top routes 2024 (`avia_par_*`, passengers carried) | VIE: Frankfurt 1.03 M, London Heathrow 0.80 M, Amsterdam 0.78 M; BTS: Antalya 215 k, London Stansted 112 k, London Luton 96 k |
| July 2026 | BTS 619,902 (+72.7 %), VIE 3,163,309 (-4.7 %, Eurostat basis) |

Caveats to repeat in every post: Vienna's Eurostat count is 1-3 % above Flughafen Wien's own figure
(different counting basis); Bratislava's matches the airport to the passenger. Eurostat lags 5-10 weeks, and
route data (`avia_par_*`) was last updated in October 2025, so 2024 is the latest year there.
The OpenSky feed is partial (started 16 Aug 2026), so it supports shares, not counts.

---

## Week 2: Bratislava is now one passenger for every five in Vienna

**Blog (SK) title:** Bratislava je už päťkrát menšia než Viedeň. Ešte vlani bola desaťkrát
**Blog hook:** For years Bratislava was about a tenth of Vienna. In July 2026 it is a fifth.
**Chart:** line of BTS / VIE share by month since 2019 (Eurostat), dashed marker at Nov 2025 (Wizz Air base).
**New report visual (proposed):** "Size ratio" line on the Trend page.

**LinkedIn (SK)**

> Ešte vlani som v dátach videl desatinu. V júli 2026 je to pätina.
>
> Letisko Bratislava má dnes 19,6 % pasažierov letiska Viedeň. V júli 2025 to bolo 10,8 %, v júli 2019 10,4 %. Za desať rokov sa pomer takmer nehýbal, za jeden rok sa zdvojnásobil.
>
> Dva čísla, ktoré to vysvetľujú (Eurostat, júl 2026 oproti júlu 2019):
> • Bratislava: 187 % úrovne z roku 2019
> • Viedeň: 100 % (stojí na mieste)
>
> Za rok 2026 bola Bratislava od januára do júla na 2,57 mil. pasažierov, 2,08-násobok minulého roka. Viedeň je na 17,7 mil., o 2,9 % menej.
>
> Zdroj aj postup sú verejné. Report je živý, link v prvom komentári.
>
> #PowerBI #DataViz #Aviation

**LinkedIn (EN)**

> A year ago the data said one in ten. In July 2026 it says one in five.
>
> Bratislava Airport now handles 19.6 % of Vienna's passengers. In July 2025 it was 10.8 %, in July 2019 10.4 %. For years the ratio barely moved; in one year it doubled.
>
> Two numbers explain it (Eurostat, July 2026 vs July 2019):
> • Bratislava: 187 % of its 2019 level
> • Vienna: 100 %, standing still
>
> January to July 2026: Bratislava 2.57 M passengers, 2.08x last year. Vienna 17.7 M, down 2.9 %.
>
> Sources and method are public and the report is live. Link in the first comment.
>
> #PowerBI #DataViz #Aviation

---

## Week 3: More flights, not bigger planes

**Blog (SK) title:** Bratislava rastie letmi, nie väčšími lietadlami
**Hook:** July flights: Bratislava +60 %, Vienna -4 %. Passengers per flight are now equal (144 vs 147).
**Chart:** two small multiples (flights, passengers per flight), BTS and VIE, July of each year. Different scales,
so two charts, never one dual axis.

**LinkedIn (SK)**

> Rast Bratislavy nie sú väčšie lietadlá. Sú to ďalšie lety.
>
> Júl 2026 oproti júlu 2025 (Eurostat, komerčné osobné lety):
> • Bratislava: 4 310 letov, o 60 % viac (2 701)
> • Viedeň: 21 572 letov, o 4 % menej (22 519)
>
> Pasažierov na let: Bratislava 144, Viedeň 147. V roku 2019 to bolo 100 a 129. Bratislava dobehla Viedeň v tom, ako plné a veľké lietadlá lietajú, a pridáva k tomu frekvenciu.
>
> Pre mňa je to najlepší dôkaz, že ide o presun kapacity a nie o výkyv dopytu.
>
> Link na živý report v prvom komentári.
>
> #PowerBI #DataViz #Aviation

**LinkedIn (EN)**

> Bratislava's growth isn't bigger planes. It's more flights.
>
> July 2026 vs July 2025 (Eurostat, commercial passenger flights):
> • Bratislava: 4,310 flights, up 60 % (2,701)
> • Vienna: 21,572 flights, down 4 % (22,519)
>
> Passengers per flight: Bratislava 144, Vienna 147. In 2019 it was 100 and 129. Bratislava has caught up on how full its planes are and adds frequency on top.
>
> To me that's the clearest evidence that this is capacity moving, not a blip in demand.
>
> Link to the live report in the first comment.
>
> #PowerBI #DataViz #Aviation

---

## Week 4: Cheaper tickets in Slovakia, and Vienna's answer

Researched 11 Oct 2026 from news coverage (links at the end). **Update 11 Oct:** the Slovakia/Belgium fare figures
were checked against Eurostat (`prc_hicp_minr`, item CP0733) and match: SK -53.0 / -48.2 / -45.1 % (Apr-Jun 2026),
then -43.6 % (Jul) and -61.2 % (Aug); Austria +22.3 / +15.6 / +6.8 % (Jun-Aug); BE +41.5 / +33.8 / +28.7 % (Apr-Jun).
The news figures about Vienna (tax, layoffs, forecast) are still unverified: check them at the original source.

* Hook: Slovakia had the steepest airfare drop in the EU in spring 2026: year over year **-53 % in April,
  -48 % in May, -45 % in June**, while Belgium, with its departure tax, saw fares **rise 29 to 42 %**
  (EUalive, 24 Jul 2026, citing Eurostat). Both numbers are the article's, not mine.
* Caveat to include: an airfare index is noisy. In Eurostat's 2025 series Slovakia swings between -22.8 %
  (Apr) and +32.9 % (Jun) and +40.1 % (Nov), so one month proves nothing; the three-month run is the story.
  To check: Eurostat `prc_hicp_manr`, COICOP `CP0733` (passenger transport by air), geo SK / AT / BE; the
  version I could query ends in December 2025, so the 2026 months must be confirmed from the current release.
* Vienna's side (facts to quote with the source): Austrian tax EUR 12 per departing passenger, EUR 30 on flights
  up to 350 km; airport management wants it abolished and says Bratislava's costs are a third lower; the
  finance ministry has no plan to cut it; Vienna Airport lowered its 2026 forecast to below 30 million
  passengers and announced about 200 job cuts; Ryanair pulled 5 aircraft out of Vienna.
* Our own data to tie it together: July 2026 flights BTS +60 % / VIE -4 %, Bratislava 619,902 passengers
  (+72.7 %), Vienna 3,163,309 (-4.7 %, Eurostat basis).
* Open question for the post (say it plainly): is the fare gap permanent? EUalive argues it is temporary
  because EU rules (ETS, ReFuelEU) raise costs. This is an opinion; present it as one.
* Possible report visual: airfare index SK vs AT, 2025 to date, once 2026 data is available.

**LinkedIn (SK), draft: fill in the checked numbers**

> Keď lacné letecké spoločnosti odídu z jedného letiska, ceny letenky sa v susednej krajine pohnú.
>
> Podľa Eurostatu (cez EUalive) boli letenky na Slovensku v apríli 2026 medziročne o 53 % lacnejšie, v máji o 48 % a v júni o 45 %. Najväčší pokles v EÚ. V Belgicku s odletovou daňou ceny stúpli o 29 až 42 %.
>
> Medzitým Viedeň: daň 12 € na odlietajúceho pasažiera, Wizz Air preč, Ryanair stiahol 5 lietadiel, prognóza pod 30 mil. pasažierov a približne 200 prepúšťaní.
>
> Moje dáta: júl 2026 má Bratislava 619 902 pasažierov (+72,7 %), Viedeň 3 163 309 (−4,7 %).
>
> Jeden mesiac cien o ničom nehovorí, preto sledujem trojmesačný trend. Zdroje a postup v prvom komentári.
>
> #PowerBI #DataViz #Aviation

**LinkedIn (EN), draft**

> When low-cost airlines leave one airport, fares move in the neighbouring country.
>
> According to Eurostat (via EUalive), airfares in Slovakia were 53 % lower year over year in April 2026, 48 % lower in May and 45 % lower in June. The biggest drop in the EU. In Belgium, with its departure tax, fares rose 29 to 42 %.
>
> Meanwhile in Vienna: EUR 12 tax per departing passenger, Wizz Air gone, Ryanair pulled 5 aircraft, forecast below 30 million passengers, about 200 job cuts.
>
> My data: July 2026, Bratislava 619,902 passengers (+72.7 %), Vienna 3,163,309 (-4.7 %).
>
> One month of prices proves nothing, so I look at the three-month run. Sources and method in the first comment.
>
> #PowerBI #DataViz #Aviation

**Sources:** [EUalive, 24 Jul 2026](https://eualive.net/slovakia-records-steepest-drop-in-air-fares-in-the-eu-as-low-cost-carriers-flee-vienna/);
[ORF, airport board wants the tax gone](https://orf.at/stories/3444629/);
[aviation.direct, Vienna outlook 2026](https://aviation.direct/en/Vienna-Airport:-record-year-2025-and-outlook-for-a-challenging-business-year-2026);
[TASR, Wizz Air base opening 14 Nov 2025](https://www.tasr.sk/tasr-clanok/TASR:2025111400000346).

---

## Week 5 (brief): Bratislava turns into a scheduled airport

* Hook: scheduled share of BTS passengers 51 % (Jul 2024) -> 56 % -> **76 %** (Jul 2026); Vienna 98-99 %.
* Supporting: extra-EU share fell from 46 % to 36 % (more EU low-cost, fewer Turkey/Egypt charters);
  seasonality July/January fell from 4.3x to 3.2x, so the airport depends less on the summer.
* Story: **domestic flights are back**: national share of BTS passengers 0.0 % -> 3.4 % in July 2026
  (and the OpenSky feed shows Kosice, LZKZ, as the second most frequent destination after Antalya).
  Check the route and operator before writing it.
* Chart: stacked share by traffic type for BTS, one panel per July.

## Week 6 (brief): hub versus holiday airport

* Hook: Vienna's top routes are the big hubs (Frankfurt 1.03 M, London Heathrow 0.80 M, Amsterdam 0.78 M,
  Zurich 0.75 M); Bratislava's are leisure (Antalya 215 k, London Stansted 112 k, London Luton 96 k, Bergamo 90 k).
* Source: Eurostat `avia_par_at` / `avia_par_sk`, 2024 (latest published). Say clearly that it is 2024.
* Chart: two horizontal bar charts, top 10 each, different scales, same colours as the report.
* New report page idea: "Routes" with the top 10 per airport.

## Week 7 (brief): Wizz Air left Vienna

* Hook: in 8 weeks of OpenSky capture (16 Aug to 11 Oct 2026) there is **1** Wizz Air movement at Vienna
  and **654** at Bratislava (Ryanair: 2,174 at Vienna, 758 at Bratislava; Austrian: 7,919 at Vienna).
* Caveat in the first paragraph: the feed is partial and only tags selected airlines by callsign; use it for
  shares, not totals.
* Pair it with the March 2026 timeline event and the Eurostat flights numbers from week 3.

## Week 8 (brief): why my "hourly" job ran every five hours

* Hook: I measured GitHub Actions' cron on this repo (19 Aug to 10 Oct 2026): "hourly" ran about every 5 hours,
  so departures from a feed that only remembers the last hour were lost for good.
* Fix: external trigger (a Netlify scheduled function calling `workflow_dispatch`), health check that warns
  when coverage of daytime hours drops. Include the before/after coverage once a week of data exists.
* Audience: data engineers. Good for LinkedIn comments.

## Week 9 (brief, needs your OK): where 15.8 million tokens went

* Hook: a month of building this with an AI assistant cost about 15.8 M effective input tokens over 231 steps.
  58 % was re-reading the earlier conversation, 25 % running commands, 11 % instructions.
* Lesson: one conversation per phase is cheaper than one endless thread; screenshots and long scripts are the
  expensive parts.
* This is about your own tooling and costs, so publish it only if you want to; it is not about the airports.
