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

Run this once/day (not hourly -- there's no benefit to checking more often).
Captures whole UTC calendar days (today-2 and today-3), so consecutive runs tile
the timeline exactly and a missed run is healed by the next one.

Reuses auth/callsign/save helpers from opensky_scraper.py to avoid duplicating
that logic -- only the capture window and direction differ.

Requires: pip install requests psycopg2-binary
"""

import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from . import opensky_scraper as core


# How many complete UTC days to (re)fetch per run. 2 means "the day before
# yesterday" plus the one before it: a missed or failed daily run is healed by
# the next one. Overlap is harmless (ON CONFLICT DO NOTHING) and costs two extra
# API calls per day.
DAYS_PER_RUN = int(os.environ.get("ARRIVAL_DAYS", "2"))


def utc_day_windows(now: datetime, days: int) -> list[tuple[int, int]]:
    """Complete UTC calendar days, ending at the day BEFORE yesterday.

    OpenSky only serves arrivals once their day has been batch-processed (>~24h
    old), so the newest day we ask for is today-2. Anchoring to midnight UTC --
    instead of "now minus 24h/48h", as before -- makes consecutive runs tile the
    timeline exactly: no gaps or overlaps however late the cron job starts.
    """
    today = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    windows = []
    for back in range(2, 2 + days):
        begin = today - timedelta(days=back)
        windows.append((int(begin.timestamp()), int((begin + timedelta(days=1)).timestamp()) - 1))
    return windows


def capture_arrivals(client_id: str, client_secret: str, now: datetime | None = None) -> list[dict]:
    """Captures arrivals for the last DAYS_PER_RUN fully processed UTC days."""
    token = core.get_access_token(client_id, client_secret)
    movements: list[core.Movement] = []
    now = now or datetime.now(timezone.utc)

    for begin, end in utc_day_windows(now, DAYS_PER_RUN):
        for our_code, icao in core.AIRPORTS.items():
            if core.credits_low():
                print(f"Stopping early: {core.credits_remaining} OpenSky credits left, keeping "
                      f"{core.CREDIT_RESERVE} in reserve for the departure capture.")
                return [asdict(m) for m in movements]
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


# Kept for backwards compatibility with anything that imported the old name.
capture_yesterday_arrivals = capture_arrivals


if __name__ == "__main__":
    import os

    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")

    if not client_id or not client_secret:
        raise SystemExit(
            "Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET environment variables first."
        )

    print(f"Capturing arrivals for the last {DAYS_PER_RUN} fully processed UTC days...")
    try:
        results = capture_arrivals(client_id, client_secret)
    except RuntimeError as e:
        if str(e) == "RATE_LIMITED":
            print("Skipped this run: daily OpenSky credit budget is temporarily exhausted "
                  "(shared across hourly/daily jobs on this account). Next scheduled run "
                  "will pick back up once credits reset.")
            raise SystemExit(0)  # exit cleanly, not a real failure
        raise
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
