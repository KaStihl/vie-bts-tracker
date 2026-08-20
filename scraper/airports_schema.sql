-- Reference table: ICAO airport code -> name, city, country.
-- Run this once in Supabase SQL Editor before running load_airports_reference.py.

CREATE TABLE IF NOT EXISTS airports (
    icao_code TEXT PRIMARY KEY,
    iata_code TEXT,
    name TEXT,
    city TEXT,
    country TEXT,
    country_code TEXT,
    airport_type TEXT,  -- large_airport / medium_airport / small_airport / heliport / seaplane_base / closed
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION
);
