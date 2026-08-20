"""
Supabase (Postgres) storage layer for VIE/BTS traffic data.

Replaces the earlier local-SQLite version -- data already migrated via
migrate_to_supabase.py. Function names/signatures kept the same as before so
vie_scraper.py, bts_scraper.py, and run_annual_pdf_backfill.py don't need to
change, only how the connection is obtained and how rows are written.

Requires SUPABASE_CONNECTION_STRING as an environment variable (the same one
already used for OpenSky's scripts, and already set as a GitHub Actions secret).
"""

import os
import csv
from pathlib import Path

import psycopg2
import psycopg2.extras


def get_connection():
    conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")
    if not conn_string:
        raise SystemExit("Set SUPABASE_CONNECTION_STRING first.")
    return psycopg2.connect(conn_string)


def upsert_vie_monthly(conn, records: list[dict]) -> None:
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO monthly_traffic
                (airport_code, year, month, passengers, yoy_change_pct,
                 group_passengers, group_yoy_pct, verified, source_url, raw_text)
            VALUES %s
            ON CONFLICT (airport_code, year, month) DO UPDATE SET
                passengers = excluded.passengers,
                yoy_change_pct = excluded.yoy_change_pct,
                group_passengers = excluded.group_passengers,
                group_yoy_pct = excluded.group_yoy_pct,
                scraped_at = NOW()
            """,
            [
                (r["airport_code"], r["year"], r["month"], r["passengers"],
                 r["yoy_change_pct"], r["group_passengers"], r["group_yoy_pct"],
                 1, r["source_url"], r["raw_headline"])
                for r in records
            ],
        )
    conn.commit()


def insert_bts_candidates(conn, records: list[dict]) -> None:
    # If bts_scraper.py's infer_month() found exactly one clear month name
    # in the article text, we trust it and write directly with verified=1 --
    # via proper ON CONFLICT upsert, so re-running the scraper for the same
    # year is now idempotent for these (no more duplicate rows).
    #
    # If no single clear month was found, fall back to the original
    # behavior: verified=0, month=NULL, left for manual review in Supabase.
    # NOTE: for these NULL-month rows, the UNIQUE(airport_code,year,month)
    # constraint doesn't catch duplicates (Postgres treats every NULL as
    # distinct) -- re-running can still insert the same unresolved candidate
    # again. Harmless, just something to dedupe manually before UPDATE-ing.
    resolved = []
    unresolved = []
    for r in records:
        row = {
            "airport_code": r["airport_code"],
            "year": int(r["published_date"][-4:]),
            "passengers": r["passengers_mentioned"],
            "yoy_change_pct": r["yoy_pct_mentioned"],
            "source_url": r["article_url"],
            "raw_text": f"{r['title']} | {r['context_sentence']}",
        }
        if r.get("inferred_month") is not None:
            row["month"] = r["inferred_month"]
            resolved.append(row)
        else:
            unresolved.append(row)

    with conn.cursor() as cur:
        if resolved:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO monthly_traffic
                    (airport_code, year, month, passengers, yoy_change_pct, verified, source_url, raw_text)
                VALUES %s
                ON CONFLICT (airport_code, year, month) DO UPDATE SET
                    passengers = excluded.passengers,
                    yoy_change_pct = excluded.yoy_change_pct,
                    verified = 1,
                    source_url = excluded.source_url,
                    raw_text = excluded.raw_text,
                    scraped_at = NOW()
                """,
                [
                    (r["airport_code"], r["year"], r["month"], r["passengers"],
                     r["yoy_change_pct"], 1, r["source_url"], r["raw_text"])
                    for r in resolved
                ],
            )
        for row in unresolved:
            cur.execute(
                """
                INSERT INTO monthly_traffic
                    (airport_code, year, month, passengers, yoy_change_pct, verified, source_url, raw_text)
                VALUES (%(airport_code)s, %(year)s, NULL, %(passengers)s, %(yoy_change_pct)s, 0, %(source_url)s, %(raw_text)s)
                """,
                row,
            )
    conn.commit()
    return len(resolved), len(unresolved)


def upsert_bts_annual(conn, records: list[dict]) -> None:
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO annual_traffic (airport_code, year, scheduled, nonscheduled, other, total)
            VALUES %s
            ON CONFLICT (airport_code, year) DO UPDATE SET
                scheduled = excluded.scheduled,
                nonscheduled = excluded.nonscheduled,
                other = excluded.other,
                total = excluded.total,
                scraped_at = NOW()
            """,
            [
                (r["airport_code"], r["year"], r["scheduled"], r["nonscheduled"], r["other"], r["total"])
                for r in records
            ],
        )
    conn.commit()


def upsert_annual_report_monthly(conn, records: list[dict]) -> None:
    """Used by run_annual_pdf_backfill.py (BTS annual report PDF -> monthly_traffic)."""
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO monthly_traffic
                (airport_code, year, month, passengers, verified, source_url, raw_text)
            VALUES %s
            ON CONFLICT (airport_code, year, month) DO UPDATE SET
                passengers = excluded.passengers,
                verified = 1,
                source_url = excluded.source_url,
                scraped_at = NOW()
            """,
            [
                (r["airport_code"], r["year"], r["month"], r["passengers"], 1, r["source_url"], "z výročnej správy PDF")
                for r in records
            ],
        )
    conn.commit()


def export_csv(conn, out_dir) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = [
        ("monthly_traffic", "monthly_traffic.csv", "airport_code, year, month"),
        ("annual_traffic", "annual_traffic.csv", "airport_code, year"),
    ]
    for table, filename, order_by in tables:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
            cols = [d.name for d in cur.description]
            with open(out_dir / filename, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(cols)
                writer.writerows(cur.fetchall())
