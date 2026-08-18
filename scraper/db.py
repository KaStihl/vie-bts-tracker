"""
Lightweight SQLite storage for VIE/BTS traffic data.

Kept deliberately simple for MVP -- a single file DB is enough for this data
volume (a few hundred rows/year). Power BI can connect to it directly via the
built-in SQLite connector (or ODBC driver), or you can export to CSV/XLSX for
a first pass.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "traffic.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS monthly_traffic (
    airport_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER,               -- NULL when only a candidate/unverified figure exists
    passengers INTEGER NOT NULL,
    yoy_change_pct REAL,
    group_passengers INTEGER,    -- Flughafen Wien Group total, VIE only
    group_yoy_pct REAL,
    verified INTEGER DEFAULT 1,  -- 0 = needs manual review (BTS candidates)
    source_url TEXT,
    raw_text TEXT,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (airport_code, year, month)
);

CREATE TABLE IF NOT EXISTS annual_traffic (
    airport_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    scheduled INTEGER,
    nonscheduled INTEGER,
    other INTEGER,
    total INTEGER NOT NULL,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (airport_code, year)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def upsert_vie_monthly(conn: sqlite3.Connection, records: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO monthly_traffic
            (airport_code, year, month, passengers, yoy_change_pct,
             group_passengers, group_yoy_pct, verified, source_url, raw_text)
        VALUES (:airport_code, :year, :month, :passengers, :yoy_change_pct,
                :group_passengers, :group_yoy_pct, 1, :source_url, :raw_headline)
        ON CONFLICT(airport_code, year, month) DO UPDATE SET
            passengers=excluded.passengers,
            yoy_change_pct=excluded.yoy_change_pct,
            group_passengers=excluded.group_passengers,
            group_yoy_pct=excluded.group_yoy_pct,
            scraped_at=CURRENT_TIMESTAMP
        """,
        records,
    )
    conn.commit()


def insert_bts_candidates(conn: sqlite3.Connection, records: list[dict]) -> None:
    # Candidates go in with verified=0 and month=NULL (month must be confirmed
    # by a human reading context_sentence, then promoted with a manual UPDATE).
    rows = [
        {
            "airport_code": r["airport_code"],
            "year": int(r["published_date"][-4:]),
            "passengers": r["passengers_mentioned"],
            "yoy_change_pct": r["yoy_pct_mentioned"],
            "source_url": r["article_url"],
            "raw_text": f"{r['title']} | {r['context_sentence']}",
        }
        for r in records
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO monthly_traffic
            (airport_code, year, month, passengers, yoy_change_pct, verified, source_url, raw_text)
        VALUES (:airport_code, :year, NULL, :passengers, :yoy_change_pct, 0, :source_url, :raw_text)
        """,
        rows,
    )
    conn.commit()


def upsert_bts_annual(conn: sqlite3.Connection, records: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO annual_traffic (airport_code, year, scheduled, nonscheduled, other, total)
        VALUES (:airport_code, :year, :scheduled, :nonscheduled, :other, :total)
        ON CONFLICT(airport_code, year) DO UPDATE SET
            scheduled=excluded.scheduled,
            nonscheduled=excluded.nonscheduled,
            other=excluded.other,
            total=excluded.total,
            scraped_at=CURRENT_TIMESTAMP
        """,
        records,
    )
    conn.commit()


def export_csv(conn: sqlite3.Connection, out_dir: Path) -> None:
    import csv

    out_dir.mkdir(parents=True, exist_ok=True)

    for table, filename in [("monthly_traffic", "monthly_traffic.csv"), ("annual_traffic", "annual_traffic.csv")]:
        cur = conn.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        with open(out_dir / filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            writer.writerows(cur.fetchall())
