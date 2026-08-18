"""
Daily capture of ARRIVALS at LOWW (Vienna) and LZIB (Bratislava).

Split out from opensky_scraper.py (which handles departures, hourly) because
arrivals behave differently on OpenSky's side -- confirmed live (2026-08):
/flights/arrival consistently 404s for "now" or "last hour" windows, but
succeeds for windows more than ~24h old. This matches OpenSky's own docs:
"Flights are updated by a batch process at night, i.e., only flights from
the previous day or earlier are available." Departures don't have this
restriction (derivable as soon as an aircraft climbs away), which is why
opensky_scraper.py's hourly departure capture works fine.

Run this once/day (not hourly -- there's no benefit to checking more often,
since "yesterday" doesn't change until tomorrow). Captures a fixed 24-hour
window shifted 24-48h behind "now", which lines up with a daily cron to give
continuous day-over-day coverage without gaps.

Reuses auth/callsign/save helpers from opensky_scraper.py to avoid duplicating
that logic -- only the capture window and direction differ.

Requires: pip install requests psycopg2-binary
"""

import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from . import opensky_scraper as core


def capture_yesterday_arrivals(client_id: str, client_secret: str) -> list[dict]:
    """
    Captures arrivals for the 24h window from 48h ago to 24h ago -- safely
    inside OpenSky's "batch processed, available" zone for both airports.
    """
    token = core.get_access_token(client_id, client_secret)
    movements: list[core.Movement] = []

    now = int(time.time())
    begin = now - 48 * 3600
    end = now - 24 * 3600

    for our_code, icao in core.AIRPORTS.items():
        flights = core.fetch_window(token, icao, begin, end, "arrival")
        for f in flights:
            callsign = (f.get("callsign") or "").strip()
            movements.append(
                core.Movement(
                    airport_code=our_code,
                    icao=icao,
                    direction="arrival",
                    callsign=callsign,
                    airline=core.resolve_airline(callsign),
                    other_airport=f.get("estDepartureAirport"),
                    icao24=f.get("icao24", ""),
                    movement_time=datetime.fromtimestamp(f["lastSeen"], tz=timezone.utc),
                    source_url=f"{core.API_BASE}/flights/arrival?airport={icao}",
                )
            )
        time.sleep(core.SLEEP_BETWEEN_CALLS)

    return [asdict(m) for m in movements]


if __name__ == "__main__":
    import os

    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")

    if not client_id or not client_secret:
        raise SystemExit(
            "Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET environment variables first."
        )

    print("Capturing arrivals for the window 48h-24h ago...")
    results = capture_yesterday_arrivals(client_id, client_secret)
    print(f"Fetched {len(results)} arrivals.")

    from collections import Counter
    print("By airline:", dict(Counter(m["airline"] for m in results)))
    print("By airport:", dict(Counter(m["airport_code"] for m in results)))

    for m in results[:5]:
        print(m)

    if supabase_conn_string:
        inserted = core.save_to_supabase(results, supabase_conn_string)
        print(f"\nInserted {inserted} new rows into Supabase (duplicates skipped).")
    else:
        print("\nSUPABASE_CONNECTION_STRING not set -- skipped DB write, printed results only.")
