"""
Runs the BTS annual report PDF scraper (bts_annual_report_scraper.py) and
writes the results into the same monthly_traffic table used by the regular
VIE/BTS press-release scrapers.

Standalone from main.py deliberately -- a new annual report only comes out
roughly once/year, so this doesn't need to run every regular scrape cycle.
Run it now for the initial 2019-2024 backfill, then again whenever BTS
publishes a new annual report (check https://www.bts.aero/en/airport/press/annual-report/).

Safe to re-run: upserts by (airport_code, year, month), so re-running just
refreshes existing rows rather than duplicating.

Run: python -m scraper.run_annual_pdf_backfill
"""

from . import bts_annual_report_scraper, db


def run() -> None:
    conn = db.get_connection()

    print("Scraping BTS annual report PDF...")
    records, warnings = bts_annual_report_scraper.scrape()
    print(f"Parsed {len(records)} monthly records from annual report PDF.")

    if warnings:
        print(f"\n{len(warnings)} warnings (review these):")
        for w in warnings[:10]:
            print(" ", w)

    db.upsert_annual_report_monthly(conn, records)
    print(f"Upserted {len(records)} rows into monthly_traffic.")

    conn.close()


if __name__ == "__main__":
    run()
