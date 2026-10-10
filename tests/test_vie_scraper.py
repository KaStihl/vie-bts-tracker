import pytest

from scraper.vie_scraper import parse_headline


def test_modern_headline():
    r = parse_headline(
        "June 2026 Traffic Results: 4,039,311 passengers handled by the Flughafen Wien Group (+0.2%) "
        "and 2,832,434 passengers at Vienna Airport (-5.9%)"
    )
    assert (r.year, r.month, r.passengers, r.yoy_change_pct) == (2026, 6, 2_832_434, -5.9)
    assert (r.group_passengers, r.group_yoy_pct) == (4_039_311, 0.2)


def test_percentage_placed_before_the_group_name():
    r = parse_headline(
        "May 2026 Traffic Results: 3,912,644 passengers (+0.7%) handled by the Flughafen Wien Group "
        "and 2,743,817 passengers at Vienna Airport (-5.4%)"
    )
    assert (r.month, r.passengers, r.group_yoy_pct, r.yoy_change_pct) == (5, 2_743_817, 0.7, -5.4)


def test_singular_result_and_missing_the():
    # Skipped by the old regex ("Traffic result", "by Flughafen Wien Group").
    r = parse_headline(
        "June 2024 - Traffic result: 3,970,365 passengers (+8.4%) handled by Flughafen Wien Group and "
        "3,020,849 passengers at Vienna Airport (+6.5%) - 28th of June 2024 strongest travel day"
    )
    assert (r.year, r.month, r.passengers, r.yoy_change_pct) == (2024, 6, 3_020_849, 6.5)


def test_no_traffic_results_wording():
    r = parse_headline(
        "November 2024 – 2,936,271 passengers (+10.0%) handled by the Flughafen Wien Group and "
        "2,264,936 passengers at Vienna Airport (+7.4%)"
    )
    assert (r.month, r.passengers) == (11, 2_264_936)


def test_older_headline_without_percentages():
    r = parse_headline(
        "November 2023 Traffic Results: 2,669,896 passengers handled by the Flughafen Wien Group and "
        "2,109,407 by Vienna Airport – Ongoing strong passenger growth"
    )
    assert (r.year, r.month, r.passengers, r.yoy_change_pct, r.group_yoy_pct) == (2023, 11, 2_109_407, None, None)


@pytest.mark.parametrize("headline", [
    "September 2021 traffic results show slight upward trend: 2.0 million passengers handled by the "
    "Flughafen Wien Group and 1.6 million at Vienna Airport",
    "Flughafen Wien AG in the first half of 2026: Earnings improvement of 7.0% thanks to growth",
    "Vienna Airport sets new passenger records in 2025 with 43.4 million (Flughafen Wien Group)",
])
def test_non_monthly_or_rounded_headlines_are_skipped(headline):
    assert parse_headline(headline) is None
