from datetime import datetime, timezone

from scraper.opensky_arrivals import utc_day_windows
from scraper.opensky_backfill import group_rows, match_flight


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_arrival_windows_do_not_drift_with_cron_delay():
    on_time = utc_day_windows(utc(2026, 10, 10, 4, 45), 2)
    late = utc_day_windows(utc(2026, 10, 10, 11, 20), 2)   # GitHub delayed the job by hours
    assert on_time == late


def test_arrival_windows_are_whole_utc_days_ending_two_days_back():
    (b1, e1), (b0, e0) = utc_day_windows(utc(2026, 10, 10, 4, 45), 2)
    assert datetime.fromtimestamp(b1, timezone.utc) == utc(2026, 10, 8)
    assert datetime.fromtimestamp(e1, timezone.utc) == utc(2026, 10, 8, 23, 59, 59)
    assert datetime.fromtimestamp(b0, timezone.utc) == utc(2026, 10, 7)


def test_consecutive_days_tile_without_gaps():
    day1 = utc_day_windows(utc(2026, 10, 10, 5), 1)[0]
    day2 = utc_day_windows(utc(2026, 10, 11, 5), 1)[0]
    assert day2[0] == day1[1] + 1


def row(icao24, callsign, direction, when, id_=1):
    return {"id": id_, "icao24": icao24, "callsign": callsign, "direction": direction, "movement_time": when}


def test_match_requires_callsign_and_time():
    when = utc(2026, 10, 1, 10, 0)
    flights = [
        {"callsign": "RYR1AB ", "firstSeen": int(when.timestamp()) + 60, "estArrivalAirport": "EGSS"},
        {"callsign": "RYR1AB", "firstSeen": int(when.timestamp()) + 6 * 3600, "estArrivalAirport": "LEMD"},
        {"callsign": "WZZ99", "firstSeen": int(when.timestamp()), "estArrivalAirport": "EPWA"},
    ]
    m = match_flight(flights, row("abc", "RYR1AB", "departure", when))
    assert m["estArrivalAirport"] == "EGSS"          # the later leg with the same callsign is not picked


def test_match_uses_last_seen_for_arrivals():
    when = utc(2026, 10, 1, 10, 0)
    flights = [{"callsign": "AUA1", "firstSeen": 0, "lastSeen": int(when.timestamp()), "estDepartureAirport": "LOWW"}]
    assert match_flight(flights, row("abc", "AUA1", "arrival", when))["estDepartureAirport"] == "LOWW"


def test_no_match_outside_tolerance():
    when = utc(2026, 10, 1, 10, 0)
    flights = [{"callsign": "X1", "firstSeen": int(when.timestamp()) + 3600}]
    assert match_flight(flights, row("abc", "X1", "departure", when)) is None


def test_groups_are_per_aircraft_day_newest_first():
    rows = [
        row("a", "C1", "departure", utc(2026, 10, 1, 8), 1),
        row("a", "C2", "departure", utc(2026, 10, 1, 15), 2),   # same aircraft+day -> same group
        row("b", "C3", "departure", utc(2026, 10, 3, 9), 3),
        row("a", "C4", "departure", utc(2026, 10, 2, 9), 4),
    ]
    groups = group_rows(rows)
    assert [sorted(r["id"] for r in g) for g in groups] == [[3], [4], [1, 2]]
