from datetime import datetime, timedelta, timezone

from scraper.healthcheck import ERROR, WARNING, Stats, evaluate

NOW = datetime(2026, 10, 10, 8, 15, tzinfo=timezone.utc)


def healthy(**overrides) -> Stats:
    base = dict(
        last_departure=NOW - timedelta(hours=2),
        last_arrival=NOW - timedelta(days=2),
        last_vie_monthly_scrape=NOW - timedelta(days=3),
        last_bts_monthly_scrape=NOW - timedelta(days=3),
        daytime_hours_with_departures_7d=100,
        unverified_monthly_rows=0,
    )
    base.update(overrides)
    return Stats(**base)


def test_healthy_pipeline_has_no_findings():
    assert evaluate(healthy(), NOW) == []


def test_stale_departures_is_an_error():
    findings = evaluate(healthy(last_departure=NOW - timedelta(hours=30)), NOW)
    assert [level for level, _ in findings] == [ERROR]
    assert "Departures" in findings[0][1]


def test_empty_table_is_an_error():
    findings = evaluate(healthy(last_arrival=None), NOW)
    assert findings[0][0] == ERROR and "no data" in findings[0][1]


def test_low_capture_coverage_is_only_a_warning():
    findings = evaluate(healthy(daytime_hours_with_departures_7d=40), NOW)
    assert [level for level, _ in findings] == [WARNING]
    assert "throttling" in findings[0][1]


def test_unverified_rows_warn():
    findings = evaluate(healthy(unverified_monthly_rows=2), NOW)
    assert [level for level, _ in findings] == [WARNING]
