"""
Run this to refresh VIE/BTS monthly passenger data. Writes directly to
Supabase (Postgres) -- see db.py. Requires SUPABASE_CONNECTION_STRING set.

    python -m scraper.main

Exits non-zero when a source returns nothing at all, so that a changed website
layout fails the GitHub Actions run (and sends the usual failure e-mail)
instead of silently leaving the dashboard stale.
"""

import os
import sys
from datetime import date
from pathlib import Path

from . import vie_scraper, bts_scraper, eurostat_monthly, db


def run() -> None:
    conn = db.get_connection()
    problems: list[str] = []

    print("=== Vienna Airport (VIE) ===")
    vie_records, vie_unparsed = vie_scraper.scrape()
    if vie_records:
        db.upsert_vie_monthly(conn, vie_records)
    else:
        problems.append("Vienna scraper returned 0 monthly records (page layout changed?)")
    print(f"Stored {len(vie_records)} VIE monthly records "
          f"({len(vie_unparsed)} non-monthly or rounded-figure headlines skipped).")

    print("\n=== Bratislava Airport (BTS) ===")
    annual = bts_scraper.scrape_annual_stats()
    if annual:
        db.upsert_bts_annual(conn, [a.__dict__ for a in annual])
    else:
        problems.append("BTS annual statistics table not found (page layout changed?)")
    print(f"Stored {len(annual)} BTS annual records.")

    this_year = date.today().year
    all_candidates = []
    for yr in range(this_year - 2, this_year + 1):
        yr_candidates = bts_scraper.scrape_news_candidates(year=yr)
        print(f"  Year {yr}: found {len(yr_candidates)} monthly press releases.")
        all_candidates.extend(c.__dict__ for c in yr_candidates)

    if all_candidates:
        resolved_count, unresolved_count = db.insert_bts_candidates(conn, all_candidates)
        print(f"  {resolved_count} stored as verified (clear month found)")
        print(f"  {unresolved_count} ambiguous -> verified=0 for manual review")
        if unresolved_count:
            print("--> In Supabase: SELECT * FROM monthly_traffic WHERE airport_code='BTS' AND verified=0,")
            print("    read raw_text, then UPDATE month and verified=1.")
    else:
        problems.append("BTS press-release scraper returned 0 monthly figures (page layout changed?)")

    print("\n=== Eurostat monthly (fills months the airports did not publish) ===")
    try:
        euro = eurostat_monthly.scrape()
    except Exception as exc:  # network / API change: report, but do not lose the other sources
        euro = []
        problems.append(f"Eurostat request failed: {exc}")
    if euro:
        db.upsert_eurostat_monthly(conn, euro)
        print(f"Stored {len(euro)} Eurostat monthly records.")
    elif not any("Eurostat" in p for p in problems):
        problems.append("Eurostat returned 0 monthly records (dataset changed?)")

    if os.environ.get("EXPORT_CSV") == "1":
        export_dir = Path(__file__).parent / "exports"
        db.export_csv(conn, export_dir)
        print(f"\nCSV exports written to {export_dir}/")

    conn.close()

    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
