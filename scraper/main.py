"""
Run this monthly (manually first, then via GitHub Actions cron once stable).

    python -m scraper.main

Outputs:
  - scraper/traffic.db          (SQLite, source of truth)
  - scraper/exports/*.csv       (for Power BI import while you set up a
                                  proper connection, or as a permanent
                                  lightweight data source)
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
        print(f"WARNING: {len(vie_unparsed)} VIE headlines did not match the regex pattern:")
        for u in vie_unparsed[:5]:
            print(f"  - {u}")

    print("\n=== Bratislava Airport (BTS) ===")
    annual = bts_scraper.scrape_annual_stats()
    db.upsert_bts_annual(conn, [a.__dict__ for a in annual])
    print(f"Stored {len(annual)} BTS annual records.")

    candidates = bts_scraper.scrape_news_candidates(year=2026)
    db.insert_bts_candidates(conn, [c.__dict__ for c in candidates])
    print(f"Stored {len(candidates)} BTS monthly CANDIDATES (verified=0, month=NULL).")
    print("--> Open traffic.db and manually confirm/assign the month for each")
    print("    candidate row by reading raw_text, then UPDATE verified=1 and set month.")

    export_dir = Path(__file__).parent / "exports"
    db.export_csv(conn, export_dir)
    print(f"\nCSV exports written to {export_dir}/")

    conn.close()


if __name__ == "__main__":
    run()
