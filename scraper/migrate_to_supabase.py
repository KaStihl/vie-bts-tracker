"""
One-time migration: copies existing data from local traffic.db (SQLite) into
Supabase (Postgres). Run this ONCE, after creating the tables via
monthly_traffic_schema.sql, and BEFORE switching db.py/main.py over to the
new Postgres-based version.

Safe to re-run: upserts by the same unique keys as the live schema, so
re-running just refreshes rows rather than duplicating.

Requires: pip install psycopg2-binary
"""

import sqlite3


def migrate(sqlite_path: str, connection_string: str) -> None:
    import psycopg2
    import psycopg2.extras

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(connection_string)

    try:
        # --- monthly_traffic ---
        rows = sqlite_conn.execute("SELECT * FROM monthly_traffic").fetchall()
        print(f"Migrating {len(rows)} rows from monthly_traffic...")

        with pg_conn.cursor() as cur:
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
                    verified = excluded.verified,
                    source_url = excluded.source_url,
                    raw_text = excluded.raw_text
                """,
                [
                    (r["airport_code"], r["year"], r["month"], r["passengers"],
                     r["yoy_change_pct"], r["group_passengers"], r["group_yoy_pct"],
                     r["verified"], r["source_url"], r["raw_text"])
                    for r in rows
                ],
            )
        pg_conn.commit()
        print("  Done.")

        # --- annual_traffic ---
        rows2 = sqlite_conn.execute("SELECT * FROM annual_traffic").fetchall()
        print(f"Migrating {len(rows2)} rows from annual_traffic...")

        with pg_conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO annual_traffic
                    (airport_code, year, scheduled, nonscheduled, other, total)
                VALUES %s
                ON CONFLICT (airport_code, year) DO UPDATE SET
                    scheduled = excluded.scheduled,
                    nonscheduled = excluded.nonscheduled,
                    other = excluded.other,
                    total = excluded.total
                """,
                [
                    (r["airport_code"], r["year"], r["scheduled"],
                     r["nonscheduled"], r["other"], r["total"])
                    for r in rows2
                ],
            )
        pg_conn.commit()
        print("  Done.")

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    import os

    conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")
    if not conn_string:
        raise SystemExit("Set SUPABASE_CONNECTION_STRING first.")

    migrate("scraper/traffic.db", conn_string)
    print("\nMigration complete. Verify row counts in Supabase before proceeding.")
