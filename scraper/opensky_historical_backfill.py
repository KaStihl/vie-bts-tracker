"""
One-time historical backfill of departures AND arrivals, back to
TARGET_START (Jan 1, 2024), for both VIE (LOWW) and BTS (LZIB).

Confirmed live (2026-08):
  - OpenSky partitions flight data by day; a single /flights/* query can span
    at most ~2 days ("You can only query across 2 partitions (days). Your
    query will naturally spill into the 3rd day."). So we must step
    backward in <=2-day windows, not one big range.
  - Both /flights/departure and /flights/arrival support real historical
    windows this way (narrow 1h windows tested successfully up to 180 days
    back for departures; arrivals are documented as available "from
    yesterday or earlier" -- same historical depth, just never "today").

RESUMABLE BY DESIGN: this script does NOT keep a separate progress file.
Instead, for each (airport, direction) combo it queries Supabase for the
OLDEST movement_time already stored, and walks backward from there. Run it
as many times as you like (e.g. once/day, or a few times in a row) -- each
run just continues where the last one stopped. No bookkeeping needed.

CREDIT SAFETY: checks the X-Rate-Limit-Remaining response header after every
call and stops cleanly (never mid-request) once remaining credits drop below
CREDIT_SAFETY_MARGIN, printing exactly how far it got so you know it's safe
to just run again later (e.g. tomorrow, once the daily allowance resets).

Requires: pip install requests psycopg2-binary
"""

import time
import requests
from datetime import datetime, timedelta, timezone
from dataclasses import asdict

from . import opensky_scraper as core

TARGET_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
WINDOW_DAYS = 2  # OpenSky's own partition limit -- confirmed live, don't raise this
# Generous margin: this account's daily credits are SHARED with the hourly
# capture, daily arrivals capture, and daily other_airport backfill jobs.
# Confirmed live that a low margin here starves those other jobs for the
# rest of the day (all fail with 429 once credits run out). 1500 leaves
# comfortable headroom -- the recurring jobs together use well under 500
# credits/day, this just avoids cutting it close.
CREDIT_SAFETY_MARGIN = 1500
SLEEP_BETWEEN_CALLS = 2


def fetch_window_with_credit_check(token: str, icao: str, begin: int, end: int, direction: str):
    """Like opensky_scraper.fetch_window, but also returns the remaining-credit count."""
    endpoint = "departure" if direction == "departure" else "arrival"
    url = f"{core.API_BASE}/flights/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"airport": icao, "begin": begin, "end": end}

    resp = requests.get(url, headers=headers, params=params, timeout=60)
    remaining_header = resp.headers.get("X-Rate-Limit-Remaining")
    remaining = int(remaining_header) if remaining_header is not None else None

    if resp.status_code == 404:
        return [], remaining
    resp.raise_for_status()
    return resp.json(), remaining


def get_earliest_stored(conn, airport_code: str, direction: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MIN(movement_time) FROM carrier_movements WHERE airport_code=%s AND direction=%s",
            (airport_code, direction),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else None


def run_historical_backfill(client_id: str, client_secret: str, connection_string: str) -> None:
    import psycopg2

    token = core.get_access_token(client_id, client_secret)
    conn = psycopg2.connect(connection_string)

    combos = [
        (our_code, icao, direction)
        for our_code, icao in core.AIRPORTS.items()
        for direction in ("departure", "arrival")
    ]

    stopped_early = False

    try:
        for our_code, icao, direction in combos:
            if stopped_early:
                break

            earliest = get_earliest_stored(conn, our_code, direction)
            # Arrivals can never include "today" -- if we have no data yet,
            # start the walk from yesterday, same boundary opensky_arrivals.py uses.
            if earliest:
                cursor_end = earliest
            elif direction == "arrival":
                cursor_end = datetime.now(timezone.utc) - timedelta(days=1)
            else:
                cursor_end = datetime.now(timezone.utc)

            print(f"\n=== {our_code} {direction}: resuming backward from {cursor_end.date()} ===")

            while cursor_end > TARGET_START:
                window_start = max(cursor_end - timedelta(days=WINDOW_DAYS), TARGET_START)

                flights, remaining = fetch_window_with_credit_check(
                    token, icao, int(window_start.timestamp()), int(cursor_end.timestamp()), direction
                )

                movements = []
                for f in flights:
                    callsign = (f.get("callsign") or "").strip()
                    ts = f["firstSeen"] if direction == "departure" else f["lastSeen"]
                    other_airport = (
                        f.get("estArrivalAirport") if direction == "departure"
                        else f.get("estDepartureAirport")
                    )
                    movements.append(asdict(core.Movement(
                        airport_code=our_code, icao=icao, direction=direction,
                        callsign=callsign, airline=core.resolve_airline(callsign),
                        other_airport=other_airport, icao24=f.get("icao24", ""),
                        movement_time=datetime.fromtimestamp(ts, tz=timezone.utc),
                        source_url=f"{core.API_BASE}/flights/{direction}?airport={icao}",
                    )))

                inserted = core.save_to_supabase(movements, connection_string)
                print(f"  {window_start.date()} -> {cursor_end.date()}: "
                      f"{len(flights)} flights, {inserted} new. Credits remaining: {remaining}")

                cursor_end = window_start
                time.sleep(SLEEP_BETWEEN_CALLS)

                if remaining is not None and remaining < CREDIT_SAFETY_MARGIN:
                    print(f"\nStopping: credits remaining ({remaining}) below safety margin "
                          f"({CREDIT_SAFETY_MARGIN}). Safe to just run this script again later "
                          f"(e.g. tomorrow) -- it will resume automatically from {window_start.date()}.")
                    stopped_early = True
                    break
    finally:
        conn.close()

    if not stopped_early:
        print("\nBackfill complete for all airport/direction combos -- reached", TARGET_START.date())


if __name__ == "__main__":
    import os

    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")

    if not all([client_id, client_secret, supabase_conn_string]):
        raise SystemExit(
            "Set OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET, SUPABASE_CONNECTION_STRING first."
        )

    run_historical_backfill(client_id, client_secret, supabase_conn_string)
