"""
Scraper for aircraft DEPARTURES by airline at LOWW (Vienna) and LZIB
(Bratislava), using OpenSky Network's REST API.

ARRIVALS are handled separately in opensky_arrivals.py -- confirmed live
(2026-08) that OpenSky's /flights/arrival endpoint only returns data for
windows more than ~24h old (batch-processed overnight), while /flights/
departure works for recent windows. See opensky_arrivals.py docstring for
details.

Unlike the passenger-count scrapers, this does NOT give you passenger totals --
it gives MOVEMENT COUNTS per airline (via callsign prefix), which is what lets
you show carrier-level capacity shifts (e.g. "Wizz Air departures from VIE
dropped from X/week to 0, while BTS departures rose from Y to Z in the same
window") -- something passenger totals alone can't prove.

Auth: requires a free OpenSky account + API client (client_id/client_secret),
created at https://opensky-network.org under Account -> API Client.
Uses the OAuth2 client-credentials flow (old username/password Basic Auth was
retired March 2026).

IMPORTANT, confirmed live against the real API (2026-08): /flights/departure
and /flights/arrival now only accept a time window within roughly the last
HOUR -- older docs describing a 7-day historical window are out of date.
This means NO retroactive backfill is possible without applying for Trino
access (gatekept, institutional-focused, not pursued here). Instead, this
script is designed to run FREQUENTLY (roughly hourly, via GitHub Actions
cron) and accumulate its own history going forward from whenever it's first
deployed. Each run captures a window slightly LONGER than the cron interval
(65 min for an hourly job) so a late/missed run doesn't leave a gap -- any
overlap is harmless, deduplicated by the UNIQUE constraint in
supabase_schema.sql (ON CONFLICT DO NOTHING).

Requires: pip install requests psycopg2-binary
"""

import time
import requests
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_BASE = "https://opensky-network.org/api"

AIRPORTS = {
    "VIE": "LOWW",
    "BTS": "LZIB",
}

# Callsign ICAO prefixes -> airline. Extend this as needed (e.g. add "LDA" for
# Lauda if you want to track it separately from Ryanair's main "RYR" prefix).
CALLSIGN_TO_AIRLINE = {
    "RYR": "Ryanair",
    "WZZ": "Wizz Air",
    "AUA": "Austrian Airlines",
    "EWG": "Eurowings",
    "LDA": "Lauda",
}

# Capture window per run. Set longer than your actual cron interval (e.g. 65
# min for an hourly cron) so a late run doesn't leave a gap -- confirmed live
# that ~60 min is the max the API accepts, so don't push this much higher.
CAPTURE_WINDOW_MINUTES = 65
SLEEP_BETWEEN_CALLS = 2  # seconds, be polite to a free shared API


@dataclass
class Movement:
    airport_code: str  # our short code, VIE or BTS
    icao: str           # LOWW or LZIB
    direction: str       # "departure" or "arrival"
    callsign: str
    airline: str         # resolved from callsign prefix, or "OTHER"
    other_airport: str | None  # the OTHER end of the flight (destination for
                                # departures, origin for arrivals). None if
                                # OpenSky couldn't identify it.
    icao24: str           # aircraft transponder address
    movement_time: datetime  # proper UTC datetime, not raw unix seconds
    source_url: str


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


def resolve_airline(callsign: str) -> str:
    if not callsign:
        return "UNKNOWN"
    prefix = callsign.strip()[:3].upper()
    return CALLSIGN_TO_AIRLINE.get(prefix, "OTHER")


def fetch_window(
    token: str, icao: str, begin: int, end: int, direction: str
) -> list[dict]:
    endpoint = "departure" if direction == "departure" else "arrival"
    url = f"{API_BASE}/flights/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"airport": icao, "begin": begin, "end": end}

    resp = requests.get(url, headers=headers, params=params, timeout=60)
    if resp.status_code == 404:
        return []  # no flights in this window -- normal, not an error
    resp.raise_for_status()
    return resp.json()


def capture_recent(client_id: str, client_secret: str) -> list[dict]:
    """
    Captures the last CAPTURE_WINDOW_MINUTES of DEPARTURES for VIE and BTS.
    Designed to be run frequently (roughly hourly).

    NOTE: arrivals are deliberately NOT attempted here -- confirmed live that
    OpenSky's /flights/arrival endpoint 404s for any "recent" window (batch
    processed overnight, only available from ~24h+ old). See
    opensky_arrivals.py for the separate daily arrivals capture.
    """
    token = get_access_token(client_id, client_secret)
    movements: list[Movement] = []

    now = int(time.time())
    begin = now - CAPTURE_WINDOW_MINUTES * 60

    for our_code, icao in AIRPORTS.items():
        flights = fetch_window(token, icao, begin, now, "departure")
        for f in flights:
            callsign = (f.get("callsign") or "").strip()
            other_airport = f.get("estArrivalAirport")
            movements.append(
                Movement(
                    airport_code=our_code,
                    icao=icao,
                    direction="departure",
                    callsign=callsign,
                    airline=resolve_airline(callsign),
                    other_airport=other_airport,
                    icao24=f.get("icao24", ""),
                    movement_time=datetime.fromtimestamp(f["firstSeen"], tz=timezone.utc),
                    source_url=f"{API_BASE}/flights/departure?airport={icao}",
                )
            )
        time.sleep(SLEEP_BETWEEN_CALLS)

    return [asdict(m) for m in movements]


def save_to_supabase(records: list[dict], connection_string: str) -> int:
    """
    Bulk-inserts movement records into Supabase (Postgres). Idempotent via
    ON CONFLICT DO NOTHING against the UNIQUE constraint defined in
    supabase_schema.sql -- safe to re-run over an overlapping window.

    Returns the number of rows actually inserted (duplicates don't count).
    """
    import psycopg2
    import psycopg2.extras

    if not records:
        return 0

    conn = psycopg2.connect(connection_string)
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO carrier_movements
                    (airport_code, icao, direction, callsign, airline,
                     other_airport, icao24, movement_time, source_url)
                VALUES %s
                ON CONFLICT (icao, direction, callsign, movement_time) DO NOTHING
                """,
                [
                    (
                        r["airport_code"],
                        r["icao"],
                        r["direction"],
                        r["callsign"],
                        r["airline"],
                        r["other_airport"],
                        r["icao24"],
                        r["movement_time"],
                        r["source_url"],
                    )
                    for r in records
                ],
            )
            inserted = cur.rowcount
        conn.commit()
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    import os

    client_id = os.environ.get("OPENSKY_CLIENT_ID")
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET")
    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")

    if not client_id or not client_secret:
        raise SystemExit(
            "Set OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET environment variables first.\n"
            "PowerShell: $env:OPENSKY_CLIENT_ID='...'; $env:OPENSKY_CLIENT_SECRET='...'"
        )

    print(f"Capturing last {CAPTURE_WINDOW_MINUTES} minutes of VIE/BTS DEPARTURES...")
    results = capture_recent(client_id, client_secret)
    print(f"Fetched {len(results)} departures.")

    from collections import Counter
    by_airline = Counter(m["airline"] for m in results)
    by_airport = Counter(m["airport_code"] for m in results)
    print("By airline:", dict(by_airline))
    print("By airport:", dict(by_airport))

    for m in results[:5]:
        print(m)

    if supabase_conn_string:
        inserted = save_to_supabase(results, supabase_conn_string)
        print(f"\nInserted {inserted} new rows into Supabase (duplicates skipped).")
    else:
        print("\nSUPABASE_CONNECTION_STRING not set -- skipped DB write, printed results only.")
        print("Set it to actually save: $env:SUPABASE_CONNECTION_STRING='postgresql://...'")
