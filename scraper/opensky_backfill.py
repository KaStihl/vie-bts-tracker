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
  2. Groups those rows by aircraft (icao24) and UTC day, and makes ONE
     /flights/aircraft call per group -- an aircraft flies several legs a day, so
     this resolves several rows per API credit spent.
  3. Matches each row to its flight by callsign AND timestamp (firstSeen for a
     departure, lastSeen for an arrival), and updates the row if resolved.

Requires: pip install requests psycopg2-binary
"""

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import opensky_scraper as core

BACKFILL_MIN_AGE_HOURS = 12   # only attempt movements at least this old
BACKFILL_MAX_AGE_DAYS = 7     # give up beyond this (older flights are
                               # unlikely to resolve, and it's not worth the
                               # API credits to keep re-checking indefinitely)
# Cap on API calls (aircraft-days) per run, to keep daily credit usage
# predictable and leave headroom for the hourly capture job sharing the same
# account's daily budget. Override with BACKFILL_MAX_CALLS.
MAX_API_CALLS = int(os.environ.get("BACKFILL_MAX_CALLS", "150"))
MATCH_TOLERANCE_SECONDS = 300
SLEEP_BETWEEN_CALLS = 2


def fetch_flights_for_aircraft(token: str, icao24: str, begin: int, end: int) -> list[dict]:
    resp = core.session().get(
        f"{core.API_BASE}/flights/aircraft",
        headers={"Authorization": f"Bearer {token}"},
        params={"icao24": icao24, "begin": begin, "end": end},
        timeout=60,
    )
    core.note_credits(resp.headers.get("X-Rate-Limit-Remaining"))
    if resp.status_code == 429:
        print(f"  HTTP 429 {core._describe_429(resp)}")
    if resp.status_code == 404:
        return []
    if resp.status_code == 429:
        raise RuntimeError("RATE_LIMITED")
    resp.raise_for_status()
    return resp.json()


def group_rows(rows: list[dict]) -> list[list[dict]]:
    """Group rows by (aircraft, UTC day); newest groups first so that recent data completes
    first and unresolvable old rows sink to the back instead of starving everything else."""
    groups: dict[tuple[str, object], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["icao24"], row["movement_time"].astimezone(timezone.utc).date())].append(row)
    return sorted(groups.values(), key=lambda g: max(r["movement_time"] for r in g), reverse=True)


def match_flight(flights: list[dict], row: dict) -> dict | None:
    """The flight in `flights` that is this row's movement: same callsign and the
    expected timestamp within MATCH_TOLERANCE_SECONDS (closest wins)."""
    key = "firstSeen" if row["direction"] == "departure" else "lastSeen"
    callsign = (row["callsign"] or "").strip().upper()
    target = row["movement_time"].timestamp()
    best, best_delta = None, MATCH_TOLERANCE_SECONDS + 1
    for f in flights:
        if (f.get("callsign") or "").strip().upper() != callsign or f.get(key) is None:
            continue
        delta = abs(f[key] - target)
        if delta < best_delta:
            best, best_delta = f, delta
    return best


def resolve_other_airport(flight: dict, direction: str) -> str | None:
    return flight.get("estArrivalAirport") if direction == "departure" else flight.get("estDepartureAirport")


def run_backfill(client_id: str, client_secret: str, connection_string: str) -> None:
    import psycopg2
    import psycopg2.extras

    token = core.get_access_token(client_id, client_secret)
    conn = psycopg2.connect(connection_string)

    now = datetime.now(timezone.utc)
    oldest_eligible = now - timedelta(days=BACKFILL_MAX_AGE_DAYS)
    newest_eligible = now - timedelta(hours=BACKFILL_MIN_AGE_HOURS)

    updated = 0
    calls = 0
    rows_seen = 0

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, icao24, callsign, direction, movement_time
                FROM carrier_movements
                WHERE other_airport IS NULL
                  AND icao24 IS NOT NULL AND icao24 != ''
                  AND movement_time BETWEEN %s AND %s
                """,
                (oldest_eligible, newest_eligible),
            )
            rows = cur.fetchall()

        groups = group_rows(rows)
        print(f"Found {len(rows)} unresolved rows in {len(groups)} aircraft-days "
              f"(will make at most {MAX_API_CALLS} API calls).")

        for group in groups[:MAX_API_CALLS]:
            if core.credits_low():
                print(f"Stopping early: {core.credits_remaining} OpenSky credits left, keeping "
                      f"{core.CREDIT_RESERVE} in reserve for the departure capture.")
                break
            times = [r["movement_time"] for r in group]
            window_begin = int((min(times) - timedelta(hours=1)).timestamp())
            window_end = int((max(times) + timedelta(hours=8)).timestamp())

            try:
                flights = fetch_flights_for_aircraft(token, group[0]["icao24"], window_begin, window_end)
            except RuntimeError as e:
                if str(e) == "RATE_LIMITED":
                    print("\n" + f"Stopping early: daily credit budget exhausted after {calls} calls. "
                          f"Progress so far is saved; the next scheduled run continues from here.")
                    break
                raise
            calls += 1
            rows_seen += len(group)
            if calls == 1 or calls % 25 == 0:
                print(f"  [call {calls}: credits remaining {core.credits_remaining}]")
            time.sleep(SLEEP_BETWEEN_CALLS)

            with conn.cursor() as write_cur:
                for row in group:
                    match = match_flight(flights, row)
                    other_airport = resolve_other_airport(match, row["direction"]) if match else None
                    if not other_airport:
                        continue  # not resolved by OpenSky (yet); a later run may try again
                    write_cur.execute(
                        "UPDATE carrier_movements SET other_airport = %s WHERE id = %s",
                        (other_airport, row["id"]),
                    )
                    updated += 1
            conn.commit()  # per group: a crash or timeout later does not lose earlier progress
    finally:
        conn.close()

    print(f"Made {calls} API calls covering {rows_seen} rows; resolved other_airport for {updated}.")


if __name__ == "__main__":
    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")

    if not all([client_id, client_secret, supabase_conn_string]):
        raise SystemExit(
            "Set OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET, SUPABASE_CONNECTION_STRING first."
        )

    run_backfill(client_id, client_secret, supabase_conn_string)
