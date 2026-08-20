"""
One-time loader for a reference table of airport ICAO codes -> name, city,
country. Lets you turn raw codes like "EDDF" (found in
carrier_movements.other_airport) into something readable ("Frankfurt Airport,
Frankfurt, Germany") via a JOIN in Power BI, instead of memorizing ICAO codes.

Source: OurAirports (via the davidmegginson/ourairports-data GitHub mirror),
a free, public-domain, community-maintained dataset updated nightly -- the
standard reference for this kind of lookup. No API key, no scraping, just a
direct CSV download.

This is REFERENCE data, not something that changes often -- run this ONCE
(or rarely, e.g. once a year to refresh), NOT on a recurring schedule. Safe
to re-run any time -- upserts by icao_code, so re-running just refreshes
existing rows rather than duplicating.

Loads ALL airport types (large/medium/small/heliport/seaplane_base/closed) --
filtering by relevance is left to Power Query at report time rather than
baked in here, since the full table is only ~85k small rows (negligible on
Supabase's free tier) and this way nothing has to be re-run if you later
want a type you excluded up front.

Requires: pip install requests psycopg2-binary pycountry
"""

import csv
import io
import requests
import pycountry

AIRPORTS_CSV_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


def country_name(iso_code: str) -> str:
    if not iso_code:
        return ""
    country = pycountry.countries.get(alpha_2=iso_code)
    return country.name if country else iso_code  # fall back to raw code if unrecognized


def load_and_filter() -> list[dict]:
    resp = requests.get(AIRPORTS_CSV_URL, timeout=60)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []
    for row in reader:
        icao = (row.get("ident") or "").strip()
        if not icao:
            continue

        lat = row.get("latitude_deg")
        lon = row.get("longitude_deg")
        country_code = (row.get("iso_country") or "").strip()

        rows.append({
            "icao_code": icao,
            "iata_code": (row.get("iata_code") or "").strip() or None,
            "name": (row.get("name") or "").strip(),
            "city": (row.get("municipality") or "").strip(),
            "country_code": country_code,
            "country": country_name(country_code),
            "airport_type": (row.get("type") or "").strip(),
            "latitude": float(lat) if lat else None,
            "longitude": float(lon) if lon else None,
        })
    return rows


def save_to_supabase(rows: list[dict], connection_string: str) -> int:
    import psycopg2
    import psycopg2.extras

    if not rows:
        return 0

    conn = psycopg2.connect(connection_string)
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO airports
                    (icao_code, iata_code, name, city, country, country_code, airport_type, latitude, longitude)
                VALUES %s
                ON CONFLICT (icao_code) DO UPDATE SET
                    iata_code = excluded.iata_code,
                    name = excluded.name,
                    city = excluded.city,
                    country = excluded.country,
                    country_code = excluded.country_code,
                    airport_type = excluded.airport_type,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude
                """,
                [
                    (r["icao_code"], r["iata_code"], r["name"], r["city"],
                     r["country"], r["country_code"], r["airport_type"], r["latitude"], r["longitude"])
                    for r in rows
                ],
            )
            inserted = cur.rowcount
        conn.commit()
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    import os

    supabase_conn_string = os.environ.get("SUPABASE_CONNECTION_STRING")
    if not supabase_conn_string:
        raise SystemExit("Set SUPABASE_CONNECTION_STRING first.")

    print("Downloading airport reference data...")
    rows = load_and_filter()
    print(f"Filtered to {len(rows)} large/medium airports worldwide.")

    inserted = save_to_supabase(rows, supabase_conn_string)
    print(f"Loaded/updated {inserted} airports into Supabase.")

    # Quick sanity check on the two we already care about
    for r in rows:
        if r["icao_code"] in ("EDDF", "LOWW", "LZIB"):
            print(" ", r)
