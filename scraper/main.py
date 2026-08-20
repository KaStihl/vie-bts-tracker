"""
Run this to refresh VIE/BTS monthly passenger data. Writes directly to
Supabase (Postgres) -- see db.py. Requires SUPABASE_CONNECTION_STRING set.

    python -m scraper.main
"""

from pathlib import Path
from . import vie_scraper, bts_scraper, db


def run() -> None:
    conn = db.get_connection()

    print("=== Vienna Airport (VIE) ===")
    vie_records, vie_unparsed = vie_scraper.scrape()
    db.upsert_vie_monthly(conn, vie_records)
    print(f"Stored {len(vie_records)} VIE monthly records.")
    if vie_unparsed:
        print(f"({len(vie_unparsed)} non-monthly VIE headlines skipped, as expected -- "
              f"quarterly/annual business results, not monthly traffic figures.)")

    print("\n=== Bratislava Airport (BTS) ===")
    annual = bts_scraper.scrape_annual_stats()
    db.upsert_bts_annual(conn, [a.__dict__ for a in annual])
    print(f"Stored {len(annual)} BTS annual records.")

    all_candidates = []
    for yr in [2024, 2025, 2026]:
        yr_candidates = bts_scraper.scrape_news_candidates(year=yr)
        print(f"  Year {yr}: found {len(yr_candidates)} candidate press releases.")
        all_candidates.extend(c.__dict__ for c in yr_candidates)

    resolved_count, unresolved_count = db.insert_bts_candidates(conn, all_candidates)
    print(f"Stored {len(all_candidates)} BTS monthly candidates total:")
    print(f"  {resolved_count} auto-resolved (clear month name found -> verified=1 directly)")
    print(f"  {unresolved_count} need manual review (ambiguous/no month name -> verified=0)")
    if unresolved_count:
        print("--> In Supabase, check monthly_traffic WHERE airport_code='BTS' AND verified=0,")
        print("    read raw_text, then UPDATE month and verified=1 for each.")

    export_dir = Path(__file__).parent / "exports"
    db.export_csv(conn, export_dir)
    print(f"\nCSV exports written to {export_dir}/ (optional -- Power BI can also connect "
          f"directly to Supabase now instead of importing these).")

    conn.close()


if __name__ == "__main__":
    run()
