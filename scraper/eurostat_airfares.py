"""
Airfare price index per country from Eurostat (HICP, ECOICOP ver.2, item CP0733 "Passenger transport by air").

Why: the story behind the passenger numbers is cheaper tickets in Slovakia after the low-cost airlines moved
from Vienna to Bratislava. Eurostat publishes the annual rate of change of airfares for every EU country about
two weeks after the month ends (dataset prc_hicp_minr, free, no key).

Checked 2026-10-11 against a news article that quoted Eurostat: Slovakia -53.0 % (Apr 2026), -48.2 % (May),
-45.1 % (Jun); Belgium +41.5 %, +33.8 %, +28.7 %. Later months: Slovakia -43.6 % (Jul), -61.2 % (Aug).

Caveats worth keeping next to every chart: this is a price index of airfares in a country's consumer basket, not
only of flights from one airport; it is very volatile month to month (Slovakia 2025: -22.8 % in April,
+32.9 % in June, +40.1 % in November), so read runs of months, not single ones.
"""

from __future__ import annotations

from typing import Optional

from .http_util import make_session

URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr"
ITEM = "CP0733"                                    # passenger transport by air
GEOS = ["SK", "AT", "CZ", "HU", "BE", "EU27_2020"]
SINCE = "2024-01"


def _series(payload: dict, geo: str) -> dict[str, Optional[float]]:
    """JSON-stat -> {'2026-08': -61.2, ...}; every dimension except geo and time has size 1."""
    dims, sizes = payload["id"], payload["size"]
    cats = {d: payload["dimension"][d]["category"]["index"] for d in dims}
    if geo not in cats["geo"]:
        return {}
    values = payload.get("value", {})
    out: dict[str, Optional[float]] = {}
    for period, t_idx in cats["time"].items():
        pos = 0
        for d, size in zip(dims, sizes):
            idx = {"geo": cats["geo"][geo], "time": t_idx}.get(d, 0)
            pos = pos * size + idx
        v = values.get(str(pos))
        out[period] = float(v) if v is not None else None
    return out


def parse(payload_rate: dict, payload_index: dict) -> list[dict]:
    rows = []
    for geo in GEOS:
        rate = _series(payload_rate, geo)
        index = _series(payload_index, geo)
        for period, r in rate.items():
            if r is None:                      # month not published yet
                continue
            year, month = (int(x) for x in period.split("-"))
            rows.append({"geo": geo, "year": year, "month": month,
                         "annual_rate_pct": r, "index_2025": index.get(period)})
    rows.sort(key=lambda r: (r["geo"], r["year"], r["month"]))
    return rows


def _fetch(session, unit: str) -> dict:
    r = session.get(URL, params={"format": "JSON", "lang": "EN", "coicop18": ITEM, "unit": unit,
                                 "geo": GEOS, "sinceTimePeriod": SINCE}, timeout=60)
    r.raise_for_status()
    return r.json()


def scrape(session=None) -> list[dict]:
    session = session or make_session()
    return parse(_fetch(session, "RCH_A"), _fetch(session, "I25"))
