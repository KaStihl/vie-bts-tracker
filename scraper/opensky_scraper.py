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

IMPORTANT, window size (checked live): in 2026-08 /flights/departure only accepted roughly the last HOUR; on
2026-10-13 it answered windows of up to ~18 hours (62 LOWW departures in 12 h) and refused 24 hours with 403
"You cannot access historical flights". Retroactive backfill beyond that still needs Trino access (gatekept, not
pursued here). So each run looks back CAPTURE_WINDOW_MINUTES (default 12 h, env OPENSKY_CAPTURE_MINUTES), which
makes the job tolerant of GitHub's irregular "hourly" cron: any overlap is harmless, deduplicated by the UNIQUE
constraint in supabase_schema.sql (ON CONFLICT DO NOTHING). If the limit shrinks again the run steps down to
smaller windows by itself.

Requires: pip install requests psycopg2-binary
"""

import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone

from .http_util import RETRY_SERVER_ERRORS_ONLY, make_session

_SESSION = None


def session():
    """Shared requests session: retries 5xx/connection errors with backoff, but NOT 429
    (OpenSky's 429 means the daily credit budget is spent -- see fetch_window)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = make_session(retry_statuses=RETRY_SERVER_ERRORS_ONLY)
    return _SESSION

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

# Capture window per run. GitHub's "hourly" cron really runs every 4-8 hours, so a window of one hour loses most
# departures. Checked live on 2026-10-13: /flights/departure returns windows of up to ~18 hours (a 24-hour window
# answers 403 "You cannot access historical flights"), so each run now looks back 12 hours. Overlaps are harmless
# (ON CONFLICT DO NOTHING). If the API ever narrows the limit again, the run steps down to a smaller window.
CAPTURE_WINDOW_MINUTES = int(os.environ.get("OPENSKY_CAPTURE_MINUTES", "720"))
FALLBACK_WINDOWS_MINUTES = (360, 120, 65)
SLEEP_BETWEEN_CALLS = 2  # seconds, be polite to a free shared API

# The daily credit budget is shared by the capture, arrivals and backfill jobs. The two daily jobs stop when fewer
# than this many credits remain, so the capture (which must not miss anything) always has some left.
CREDIT_RESERVE = int(os.environ.get("OPENSKY_CREDIT_RESERVE", "1000"))
credits_remaining: int | None = None     # last X-Rate-Limit-Remaining seen


def credits_low() -> bool:
    return credits_remaining is not None and credits_remaining < CREDIT_RESERVE


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
    resp = session().post(
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


class WindowTooOld(RuntimeError):
    """The API refuses this window as 'historical'; retry with a shorter one."""


def note_credits(value) -> None:
    global credits_remaining
    try:
        credits_remaining = int(value)
    except (TypeError, ValueError):
        pass


def _describe_429(resp) -> str:
    """What OpenSky says about the limit: the headers tell when the credits come back."""
    keys = ("X-Rate-Limit-Remaining", "X-Rate-Limit-Retry-After-Seconds", "Retry-After")
    seen = {k: resp.headers.get(k) for k in keys if resp.headers.get(k) is not None}
    return f"HTTP 429 {seen or '(no rate-limit headers)'} {resp.text.strip()[:120]!r}"


def fetch_window(
    token: str | None, icao: str, begin: int, end: int, direction: str, anonymous_fallback: bool = False
) -> list[dict]:
    """token=None calls the API anonymously (OpenSky allows that with a small daily budget).
    anonymous_fallback: when the account's credits are exhausted (429), try once without the token."""
    endpoint = "departure" if direction == "departure" else "arrival"
    url = f"{API_BASE}/flights/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    params = {"airport": icao, "begin": begin, "end": end}

    resp = session().get(url, headers=headers, params=params, timeout=60)
    remaining = resp.headers.get("X-Rate-Limit-Remaining")
    if remaining is not None:
        print(f"  [credits remaining: {remaining}]")
        note_credits(remaining)
    if resp.status_code == 429:
        print(f"  {'anonymous ' if not token else ''}{_describe_429(resp)}")
        if token and anonymous_fallback:
            print("  account credits exhausted: trying the anonymous budget for this call")
            return fetch_window(None, icao, begin, end, direction)
        # Daily credit budget exhausted (shared across all scripts on this account). Not a bug: this run is
        # skipped and a later one catches up.
        raise RuntimeError("RATE_LIMITED")
    if resp.status_code == 404:
        return []  # no flights in this window -- normal, not an error
    if resp.status_code == 403 and "historical" in resp.text.lower():
        raise WindowTooOld(resp.text.strip()[:120])
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
    windows = [CAPTURE_WINDOW_MINUTES] + [m for m in FALLBACK_WINDOWS_MINUTES if m < CAPTURE_WINDOW_MINUTES]

    for our_code, icao in AIRPORTS.items():
        for i, minutes in enumerate(windows):
            try:
                flights = fetch_window(token, icao, now - minutes * 60, now, "departure", anonymous_fallback=True)
                break
            except WindowTooOld as e:
                if i == len(windows) - 1:
                    raise
                print(f"  window of {minutes} min refused ({e}); trying {windows[i + 1]} min")
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

    print(f"Capturing the last {CAPTURE_WINDOW_MINUTES} minutes of VIE/BTS DEPARTURES...")
    try:
        results = capture_recent(client_id, client_secret)
    except RuntimeError as e:
        if str(e) == "RATE_LIMITED":
            print("Skipped this run: daily OpenSky credit budget is temporarily exhausted "
                  "(shared across hourly/daily jobs on this account). Next scheduled run "
                  "will pick back up once credits reset.")
            raise SystemExit(0)  # exit cleanly, not a real failure
        raise
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
