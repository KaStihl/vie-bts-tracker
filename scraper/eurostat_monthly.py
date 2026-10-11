"""
Monthly passengers per airport from Eurostat (dataset avia_paoa, free, no key).

Why: both airports publish monthly figures only irregularly in press releases (Vienna skips e.g. April,
July, October, December in most years; Bratislava's news archive is patchy, 2025 has a single month).
Eurostat has every month for both airports, about 5-10 weeks after the month ends.

Which measure: "passengers on board" (PAS_BRD, arrivals + departures, scheduled + non-scheduled).
  * Bratislava: identical to the airport's own press-release counts (Jan 195,110, May 398,639,
    Jun 510,152, Aug 2026 625,742 - checked to the passenger), so the rows are interchangeable.
  * Vienna: 1-3 % ABOVE the airport's own "passengers handled" (different counting basis), so
    these rows are only used to fill months Vienna did not publish and are flagged as Eurostat.

Stored in its own table (eurostat_monthly) so the verified press-release rows are never touched;
Power BI combines them (official first, Eurostat only for months without an official figure).
"""

from __future__ import annotations

from typing import Optional

from .http_util import make_session

URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/avia_paoa"
AIRPORTS = {"AT_LOWW": "VIE", "SK_LZIB": "BTS"}
SINCE = "2019-01"


def _series(payload: dict, airport: str) -> dict[str, Optional[int]]:
    """JSON-stat -> {'2026-07': 3163309, ...} for one airport (all other dimensions have size 1)."""
    dims = payload["id"]
    sizes = payload["size"]
    cats = {d: payload["dimension"][d]["category"]["index"] for d in dims}
    if airport not in cats["rep_airp"]:
        return {}
    values = payload.get("value", {})
    out: dict[str, Optional[int]] = {}
    for period, t_idx in cats["time"].items():
        # row-major position over all dimensions; every dimension except rep_airp and time has size 1
        pos = 0
        for d, size in zip(dims, sizes):
            idx = {"rep_airp": cats["rep_airp"][airport], "time": t_idx}.get(d, 0)
            pos = pos * size + idx
        v = values.get(str(pos))
        out[period] = int(v) if v is not None else None
    return out


def parse(payload_brd: dict, payload_crd: dict) -> list[dict]:
    rows = []
    for code, airport in AIRPORTS.items():
        brd = _series(payload_brd, code)
        crd = _series(payload_crd, code)
        for period, pax in brd.items():
            if not pax:           # not published yet (None) or 0
                continue
            year, month = (int(x) for x in period.split("-"))
            rows.append({"airport_code": airport, "year": year, "month": month,
                         "passengers": pax, "passengers_carried": crd.get(period)})
    rows.sort(key=lambda r: (r["airport_code"], r["year"], r["month"]))
    return rows


def _fetch(session, measure: str) -> dict:
    r = session.get(URL, params={
        "format": "JSON", "lang": "EN", "freq": "M", "unit": "PAS", "tra_meas": measure,
        "schedule": "TOTAL", "tra_cov": "TOTAL", "sinceTimePeriod": SINCE,
        "rep_airp": list(AIRPORTS),
    }, timeout=60)
    r.raise_for_status()
    return r.json()


def scrape(session=None) -> list[dict]:
    session = session or make_session()
    return parse(_fetch(session, "PAS_BRD"), _fetch(session, "PAS_CRD"))
