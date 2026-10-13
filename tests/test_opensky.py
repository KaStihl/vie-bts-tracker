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


# ---- capture window and credit reserve (OpenSky answered up to ~18 h on 2026-10-13, refuses 24 h)
import pytest

from scraper import opensky_scraper as core


def _flight(t):
    return {"icao24": "abc123", "callsign": "RYR1AB ", "firstSeen": t, "estArrivalAirport": "EGSS"}


def test_capture_looks_back_twelve_hours_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(core, "get_access_token", lambda *a: "tok")
    monkeypatch.setattr(core, "SLEEP_BETWEEN_CALLS", 0)
    monkeypatch.setattr(core, "fetch_window", lambda tok, icao, b, e, d, **kw: seen.append((e - b) // 60) or [])
    core.capture_recent("id", "secret")
    assert seen == [core.CAPTURE_WINDOW_MINUTES] * 2 and core.CAPTURE_WINDOW_MINUTES == 720


def test_capture_steps_down_when_the_window_is_refused(monkeypatch):
    seen = []

    def fake(tok, icao, b, e, d, **kw):
        minutes = (e - b) // 60
        seen.append(minutes)
        if minutes > 360:
            raise core.WindowTooOld("You cannot access historical flights")
        return [_flight(e - 100)]

    monkeypatch.setattr(core, "get_access_token", lambda *a: "tok")
    monkeypatch.setattr(core, "SLEEP_BETWEEN_CALLS", 0)
    monkeypatch.setattr(core, "fetch_window", fake)
    rows = core.capture_recent("id", "secret")
    assert seen == [720, 360, 720, 360] and len(rows) == 2


def test_credit_reserve(monkeypatch):
    monkeypatch.setattr(core, "credits_remaining", None)
    assert not core.credits_low()                       # unknown: keep going
    core.note_credits("5000")
    assert not core.credits_low()
    core.note_credits(str(core.CREDIT_RESERVE - 1))
    assert core.credits_low()
    core.note_credits("garbage")                        # a bad header must not reset the knowledge
    assert core.credits_low()


class _Resp:
    def __init__(self, status, headers=None, body=None, text=""):
        self.status_code, self.headers, self._body, self.text = status, headers or {}, body, text

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(dict(headers or {}))
        return self.responses.pop(0)


def test_capture_falls_back_to_the_anonymous_budget_when_the_account_is_exhausted(monkeypatch):
    sess = _Session([_Resp(429, {"X-Rate-Limit-Retry-After-Seconds": "3600"}), _Resp(200, body=[_flight(1)])])
    monkeypatch.setattr(core, "session", lambda: sess)
    out = core.fetch_window("tok", "LOWW", 0, 10, "departure", anonymous_fallback=True)
    assert out == [_flight(1)]
    assert sess.calls == [{"Authorization": "Bearer tok"}, {}]       # second call carries no token


def test_without_fallback_a_429_still_skips_the_run(monkeypatch):
    sess = _Session([_Resp(429)])
    monkeypatch.setattr(core, "session", lambda: sess)
    with pytest.raises(RuntimeError, match="RATE_LIMITED"):
        core.fetch_window("tok", "LOWW", 0, 10, "arrival")
    assert len(sess.calls) == 1


def test_anonymous_429_ends_the_run_too(monkeypatch):
    sess = _Session([_Resp(429), _Resp(429)])
    monkeypatch.setattr(core, "session", lambda: sess)
    with pytest.raises(RuntimeError, match="RATE_LIMITED"):
        core.fetch_window("tok", "LOWW", 0, 10, "departure", anonymous_fallback=True)
