from scraper.eurostat_monthly import parse


def _payload(values):
    """Minimal JSON-stat: dims ... rep_airp (2) x time (3), all other dimensions size 1."""
    return {
        "id": ["freq", "unit", "tra_meas", "rep_airp", "schedule", "tra_cov", "time"],
        "size": [1, 1, 1, 2, 1, 1, 3],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}},
            "unit": {"category": {"index": {"PAS": 0}}},
            "tra_meas": {"category": {"index": {"PAS_BRD": 0}}},
            "rep_airp": {"category": {"index": {"AT_LOWW": 0, "SK_LZIB": 1}}},
            "schedule": {"category": {"index": {"TOTAL": 0}}},
            "tra_cov": {"category": {"index": {"TOTAL": 0}}},
            "time": {"category": {"index": {"2026-05": 0, "2026-06": 1, "2026-07": 2}}},
        },
        "value": values,
    }


def test_parse_maps_airports_and_skips_unpublished_months():
    # LOWW: May, Jun, (Jul missing)   LZIB: May, Jun, Jul
    brd = _payload({"0": 2_783_577, "1": 2_866_515, "3": 398_639, "4": 510_152, "5": 619_902})
    crd = _payload({"0": 2_741_265, "1": 2_840_661, "3": 398_591, "4": 509_446, "5": 619_285})
    rows = parse(brd, crd)
    got = {(r["airport_code"], r["year"], r["month"]): r["passengers"] for r in rows}
    assert got == {
        ("VIE", 2026, 5): 2_783_577, ("VIE", 2026, 6): 2_866_515,
        ("BTS", 2026, 5): 398_639, ("BTS", 2026, 6): 510_152, ("BTS", 2026, 7): 619_902,
    }
    assert ("VIE", 2026, 7) not in got
    bts_jul = next(r for r in rows if r["airport_code"] == "BTS" and r["month"] == 7)
    assert bts_jul["passengers_carried"] == 619_285


def test_zero_is_treated_as_not_published():
    rows = parse(_payload({"0": 0, "3": 5}), _payload({}))
    assert [(r["airport_code"], r["month"]) for r in rows] == [("BTS", 5)]
