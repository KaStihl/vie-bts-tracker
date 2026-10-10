"""
Data-freshness check for the Supabase tables. Run daily by
.github/workflows/healthcheck.yml; exits 1 (so GitHub e-mails the owner) when the
pipeline has silently stopped delivering.

    python -m scraper.healthcheck

Thresholds are intentionally loose -- the point is to catch "nothing has arrived
for a day", not to alert on normal jitter.
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

MAX_DEPARTURE_AGE = timedelta(hours=12)      # hourly job; GitHub cron often lags by several hours
MAX_ARRIVAL_AGE = timedelta(days=4)          # daily job captures day-2 and day-3
MAX_MONTHLY_AGE = timedelta(days=45)         # both airports publish roughly monthly
MIN_DAYTIME_COVERAGE = 0.60                  # share of 05-21 UTC hours (last 7 days) with a departure

ERROR, WARNING = "error", "warning"


@dataclass
class Stats:
    last_departure: Optional[datetime]
    last_arrival: Optional[datetime]
    last_vie_monthly_scrape: Optional[datetime]
    last_bts_monthly_scrape: Optional[datetime]
    daytime_hours_with_departures_7d: int
    unverified_monthly_rows: int


def evaluate(stats: Stats, now: datetime) -> list[tuple[str, str]]:
    """Pure function: Stats -> [(level, message)]. Empty list means healthy."""
    findings: list[tuple[str, str]] = []

    def stale(label: str, last: Optional[datetime], limit: timedelta, level: str = ERROR) -> None:
        if last is None:
            findings.append((level, f"{label}: no data at all"))
        elif now - last > limit:
            findings.append((level, f"{label}: last data {last:%Y-%m-%d %H:%M} UTC, "
                                    f"{(now - last).total_seconds() / 3600:.0f}h ago (limit {limit.total_seconds() / 3600:.0f}h)"))

    stale("Departures (hourly capture)", stats.last_departure, MAX_DEPARTURE_AGE)
    stale("Arrivals (daily capture)", stats.last_arrival, MAX_ARRIVAL_AGE)
    stale("VIE monthly traffic scrape", stats.last_vie_monthly_scrape, MAX_MONTHLY_AGE)
    stale("BTS monthly traffic scrape", stats.last_bts_monthly_scrape, MAX_MONTHLY_AGE)

    expected_hours = 7 * 17
    coverage = stats.daytime_hours_with_departures_7d / expected_hours
    if coverage < MIN_DAYTIME_COVERAGE:
        findings.append((WARNING,
                         f"Departure capture covers only {coverage:.0%} of daytime hours in the last 7 days "
                         f"(want >= {MIN_DAYTIME_COVERAGE:.0%}). GitHub's cron is probably throttling the hourly job -- "
                         f"set up the external trigger in docs/OPERATIONS.md."))

    if stats.unverified_monthly_rows:
        findings.append((WARNING, f"{stats.unverified_monthly_rows} monthly_traffic rows are unverified "
                                  f"(verified=0, month NULL): assign the month in Supabase or delete them."))
    return findings


def collect(connection_string: str) -> Stats:
    import psycopg2

    conn = psycopg2.connect(connection_string, connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(movement_time) FILTER (WHERE direction = 'departure'),
                       max(movement_time) FILTER (WHERE direction = 'arrival')
                FROM carrier_movements
                """
            )
            last_dep, last_arr = cur.fetchone()

            cur.execute(
                """
                SELECT max(scraped_at) FILTER (WHERE airport_code = 'VIE'),
                       max(scraped_at) FILTER (WHERE airport_code = 'BTS'),
                       count(*) FILTER (WHERE verified = 0)
                FROM monthly_traffic
                """
            )
            vie_scrape, bts_scrape, unverified = cur.fetchone()

            cur.execute(
                """
                SELECT count(DISTINCT date_trunc('hour', movement_time))
                FROM carrier_movements
                WHERE direction = 'departure'
                  AND movement_time > now() - interval '7 days'
                  AND extract(hour FROM movement_time AT TIME ZONE 'UTC') BETWEEN 5 AND 21
                """
            )
            (hours,) = cur.fetchone()
    finally:
        conn.close()

    def aware(dt: Optional[datetime]) -> Optional[datetime]:
        return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    return Stats(aware(last_dep), aware(last_arr), aware(vie_scrape), aware(bts_scrape), hours, unverified)


def main() -> int:
    connection_string = os.environ.get("SUPABASE_CONNECTION_STRING")
    if not connection_string:
        print("Set SUPABASE_CONNECTION_STRING first.", file=sys.stderr)
        return 2

    stats = collect(connection_string)
    print(stats)
    findings = evaluate(stats, datetime.now(timezone.utc))

    for level, message in findings:
        print(f"::{level}::{message}")      # GitHub Actions annotation
    if not findings:
        print("All checks passed.")
    return 1 if any(level == ERROR for level, _ in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
