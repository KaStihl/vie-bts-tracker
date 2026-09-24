# VIE ⇄ BTS Aviation Tracker

A public data pipeline tracking monthly passenger traffic at Vienna (VIE) and
Bratislava (BTS) airports, built to examine how low-cost carrier capacity has
shifted between the two following Austria's aviation tax and Wizz Air's exit
from Vienna in March 2026.



---

## What this is

Official airports publish traffic figures, but nobody was tracking VIE and
BTS side by side, month over month, from primary sources. This project does
that automatically, and publishes both the dashboard and the full pipeline
that builds it.

**Every number on the dashboard traces back to one of:**
- Official monthly press releases (Vienna Airport investor relations, Bratislava Airport press)
- Official annual reports (Bratislava Airport)
- Real aircraft movement data ([OpenSky Network](https://opensky-network.org))

No estimates, no scraping of third-party aggregators.

## Architecture

```
Press releases / annual reports (PDF)  ──┐
OpenSky Network (aircraft movements)   ──┼──▶  Supabase (Postgres)  ──▶  Power BI
Airport reference data (OurAirports)   ──┘
```

| Component | What it does | Runs |
|---|---|---|
| `scraper/vie_scraper.py` | Parses Vienna Airport monthly traffic press releases | Weekly |
| `scraper/bts_scraper.py` | Parses Bratislava Airport monthly press releases + annual stats page | Weekly |
| `scraper/bts_annual_report_scraper.py` | Parses BTS annual report PDF (historical monthly backfill) | Ad hoc, ~yearly |
| `scraper/opensky_scraper.py` | Captures aircraft departures via OpenSky API | Hourly |
| `scraper/opensky_arrivals.py` | Captures aircraft arrivals (batch-processed by OpenSky, ~24h delay) | Daily |
| `scraper/opensky_backfill.py` | Resolves flight destinations after landing | Daily |
| `scraper/load_airports_reference.py` | Loads ICAO airport code → name/city/country reference data | One-time |

All scheduled jobs run on GitHub Actions (see `.github/workflows/`) and write
directly to a shared Supabase (Postgres) database. Power BI connects to that
database live.

## Data quality notes

- **Vienna monthly figures**: parsed automatically from consistent press
  release headlines. Some historical headlines use inconsistent phrasing and
  are intentionally skipped rather than guessed at.
- **Bratislava monthly figures**: BTS press releases are free-text, not
  templated. The scraper attempts to infer the reported month automatically
  from the article text; where it can't do so unambiguously, the figure is
  flagged for manual review before being marked verified.
- **Carrier-level data** (which airline, which route) comes from OpenSky
  Network aircraft movements, not from passenger counts. This part of the
  dataset is new (collection started September 2026) and still shallow —
  it will appear on the dashboard once it has enough history to be
  meaningful.

## Running it yourself

```bash
pip install -r requirements.txt
```

Set the following as environment variables (or GitHub Actions secrets):

| Variable | Used for |
|---|---|
| `SUPABASE_CONNECTION_STRING` | Postgres connection (all scrapers) |
| `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET` | OpenSky API (create at [opensky-network.org](https://opensky-network.org), Account → API Client) |

Database schema: see the `*_schema.sql` files in `scraper/`.

```bash
python -m scraper.main                    # VIE/BTS monthly press releases
python -m scraper.opensky_scraper         # hourly departure capture
python -m scraper.opensky_arrivals        # daily arrival capture
python -m scraper.opensky_backfill        # daily destination resolution
```

## License / reuse

Code is provided as-is for reference and transparency. The underlying data
belongs to the original publishers (Vienna Airport, Bratislava Airport,
OpenSky Network) — check their respective terms before reusing the data
itself.

## Questions / found an error in the data?

Open an issue on this repo, or reach out via [fkconsult.eu](https://fkconsult.eu).
