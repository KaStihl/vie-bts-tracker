from scraper.eurostat_airfares import parse


def _payload(values):
    """Minimal JSON-stat: geo (2) x time (3); freq / unit / coicop18 have size 1."""
    return {
        "id": ["freq", "unit", "coicop18", "geo", "time"],
        "size": [1, 1, 1, 2, 3],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}},
            "unit": {"category": {"index": {"RCH_A": 0}}},
            "coicop18": {"category": {"index": {"CP0733": 0}}},
            "geo": {"category": {"index": {"SK": 0, "AT": 1}}},
            "time": {"category": {"index": {"2026-06": 0, "2026-07": 1, "2026-08": 2}}},
        },
        "value": values,
    }


def test_parse_maps_countries_and_skips_unpublished_months():
    # SK: Jun, Jul, Aug   AT: Jun, Jul (Aug not published)
    rate = _payload({"0": -45.1, "1": -43.6, "2": -61.2, "3": 22.3, "4": 15.6})
    index = _payload({"0": 58.79, "1": 53.7, "2": 67.09, "3": 119.1, "4": 111.52})
    rows = parse(rate, index)
    got = {(r["geo"], r["year"], r["month"]): r["annual_rate_pct"] for r in rows}
    assert got == {("SK", 2026, 6): -45.1, ("SK", 2026, 7): -43.6, ("SK", 2026, 8): -61.2,
                   ("AT", 2026, 6): 22.3, ("AT", 2026, 7): 15.6}
    assert next(r for r in rows if r["geo"] == "AT" and r["month"] == 7)["index_2025"] == 111.52


def test_unlisted_country_is_ignored():
    rows = parse(_payload({"0": 1.0}), _payload({}))
    assert [(r["geo"], r["month"]) for r in rows] == [("SK", 6)]
