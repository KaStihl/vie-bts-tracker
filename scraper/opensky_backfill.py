"""
Backfill for carrier_movements.other_airport.

OpenSky can only report the OTHER end of a flight (destination for a
departure, origin for an arrival) after the flight has actually landed and
their system has had time to process/match it. Since opensky_scraper.py
captures movements ~1 hour after they happen, the flight is usually still
airborne at capture time, so other_airport is almost always NULL initially.

This script runs SEPARATELY from opensky_scraper.py (recommended: once/day,
not hourly -- there's no benefit to checking more often, since a flight
that landed 2 hours ago won't resolve any faster by checking again in 1).
It:
  1. Finds rows where other_airport IS NULL and the movement is old enough
     that the flight has almost certainly landed by now (BACKFILL_MIN_AGE_HOURS).
  2. Re-queries OpenSky's /flights/aircraft endpoint using the stored icao24
     and a time window around the original movement.
  3. Matches the correct flight by callsign, and updates the row if resolved.

Requires: pip install requests psycopg2-binary
"""

import time
import requests
from datetime import datetime, timedelta, timezone

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_BASE = "https://opensky-network.org/api"

BACKFILL_MIN_AGE_HOURS = 12   # only attempt movements at least this old
BACKFILL_MAX_AGE_DAYS = 7     # give up beyond this (older flights are
                               # unlikely to resolve, and it's not worth the
                               # API credits to keep re-checking indefinitely)
BATCH_LIMIT = 200             # cap how many NULL rows one run attempts,
                               # to keep daily credit usage predictable
SLEEP_BETWEEN_CALLS = 2


def get_access_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_flights_for_aircraft(token: str, icao24: str, begin: int, end: int) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/flights/aircraft",
        headers={"Authorization": f"Bearer {token}"},
        params={"icao24": icao24, "begin": begin, "end": end},
        timeout=60,
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()


def run_backfill(client_id: str, client_secret: str, connection_string: str) -> None:
    import psycopg2
    import psycopg2.extras

    token = get_access_token(client_id, client_secret)
    conn = psycopg2.connect(connection_string)

    now = datetime.now(timezone.utc)
    oldest_eligible = now - timedelta(days=BACKFILL_MAX_AGE_DAYS)
    newest_eligible = now - timedelta(hours=BACKFILL_MIN_AGE_HOURS)

    updated = 0
    checked = 0

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, icao24, callsign, direction, movement_time
                FROM carrier_movements
                WHERE other_airport IS NULL
                  AND icao24 IS NOT NULL AND icao24 != ''
                  AND movement_time BETWEEN %s AND %s
                ORDER BY movement_time
                LIMIT %s
                """,
                (oldest_eligible, newest_eligible, BATCH_LIMIT),
            )
            rows = cur.fetchall()

        print(f"Found {len(rows)} candidate rows to attempt backfill on.")

        with conn.cursor() as write_cur:
            for row in rows:
                checked += 1
                # Search a window around the original movement -- wide enough
                # for a long-haul flight, narrow enough to stay a cheap query.
                window_begin = int((row["movement_time"] - timedelta(hours=1)).timestamp())
                window_end = int((row["movement_time"] + timedelta(hours=8)).timestamp())

                flights = fetch_flights_for_aircraft(token, row["icao24"], window_begin, window_end)
                time.sleep(SLEEP_BETWEEN_CALLS)

                match = next(
                    (f for f in flights if (f.get("callsign") or "").strip() == (row["callsign"] or "").strip()),
                    None,
                )
                if not match:
                    continue

                other_airport = (
                    match.get("estArrivalAirport") if row["direction"] == "departure"
                    else match.get("estDepartureAirport")
                )
                if not other_airport:
                    continue  # still not resolved by OpenSky yet, try again on a later run

                write_cur.execute(
                    "UPDATE carrier_movements SET other_airport = %s WHERE id = %s",
                    (other_airport, row["id"]),
                )
                updated += 1

        conn.commit()
    finally:
        conn.close()

    print(f"Checked {checked} rows, updated {updated} with a resolved other_airport.")


if __name__ == "__main__":
    import os

    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")

    if not all([client_id, client_secret, supabase_conn_string]):
        raise SystemExit(
            "Set OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET, SUPABASE_CONNECTION_STRING first."
        )

    run_backfill(client_id, client_secret, supabase_conn_string)
