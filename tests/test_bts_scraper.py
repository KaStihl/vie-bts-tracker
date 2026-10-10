"""Regression tests for the BTS press-release parser.

The sentences are shortened versions of real bts.aero releases (2024-2026); the
figures are the real ones. Each case documents a bug the old parser had.
"""
import pytest

from scraper.bts_scraper import data_year, extract_monthly_figure, infer_month


def test_monthly_figure_with_growth_in_same_sentence():
    f = extract_monthly_figure(
        "– M. R. Štefánik Airport Bratislava began 2026 with a historic triple-digit increase in "
        "passenger numbers. In January, the airport handled a total of 195,110 passengers, "
        "representing a 127% increase compared to January 2025, when 86,000 passengers were handled."
    )
    assert (f.passengers, f.yoy_pct, f.month, f.approximate) == (195_110, 127.0, 1, False)


def test_growth_in_following_sentence():
    f = extract_monthly_figure(
        "– Bratislava Airport recorded the busiest month in its history in August, handling a total "
        "of 625,742 arriving and departing passengers. This represents a 76% increase compared to last year."
    )
    assert (f.passengers, f.yoy_pct, f.month) == (625_742, 76.0, 8)


def test_growth_is_optional():
    f = extract_monthly_figure(
        "– M. R. Štefánik Airport handled a total of 147,441 passengers on arrivals and departures "
        "in the month of April. At the same time, air cargo transport grew."
    )
    assert (f.passengers, f.yoy_pct, f.month) == (147_441, None, 4)


def test_ordinal_month_name():
    f = extract_monthly_figure(
        "– In the seventh month of the year, M. R. Štefánik Airport processed a total of 327,686 "
        "passengers on departures and arrivals. That is a 7% increase compared to last year."
    )
    assert (f.passengers, f.month) == (327_686, 7)


def test_percentage_before_the_count():
    f = extract_monthly_figure(
        "– M. R. Štefánik Airport recorded a remarkable 69% year-on-year increase in passenger "
        "numbers in November. A total of 163,949 passengers were handled."
    )
    assert (f.passengers, f.yoy_pct, f.month) == (163_949, 69.0, 11)


def test_decrease_is_negative():
    f = extract_monthly_figure(
        "– In March the airport handled 120,345 passengers, a 5% decrease compared to last year."
    )
    assert f.yoy_pct == -5.0


def test_quarter_total_is_not_a_month():
    # The old parser stored this Q1-2025 total as a monthly row (the 273,807 spike).
    assert extract_monthly_figure(
        "– BTS handled a total of 273,807 passengers on arrivals and departures from January to "
        "the end of March. In the first quarter, the airport recorded a 14% increase."
    ) is None


def test_annual_total_is_not_a_month():
    # ... and this 2024 annual total (1,948,008) was the other phantom row.
    assert extract_monthly_figure(
        "– M. R. Štefánik Airport processed a total of 1,948,008 passengers on arrivals and "
        "departures in 2024, a 7% increase compared to the previous year."
    ) is None


def test_year_to_date_milestone_is_not_a_month():
    assert extract_monthly_figure(
        "– Since the beginning of the year, M. R. Štefánik Airport has handled over 1,000,000 "
        "passengers on arrivals and departures."
    ) is None


@pytest.mark.parametrize("lead", [
    "– M. R. Štefánik Airport handled more than 360,000 passengers in the fourth month of the year.",
    "– Bratislava airport processed a record 246,000 travellers in June, an increase of 14 percent.",
])
def test_rounded_counts_are_flagged_approximate(lead):
    assert extract_monthly_figure(lead).approximate is True


def test_ambiguous_months_stay_unresolved():
    f = extract_monthly_figure(
        "– In May, June, July, and now also in August, the airport recorded the highest monthly "
        "passenger numbers in its history. During August, 355,658 passengers were handled."
    )
    assert f.month is None


def test_next_headline_after_more_link_does_not_leak_in():
    # The listing appends the NEXT article's title after "More..."; its word
    # "millionth" used to veto this valid June-2026 figure.
    f = extract_monthly_figure(
        "– The airport reached a major milestone in June, handling more than half a million "
        "passengers in a single month. During the month, the airport welcomed 510,152 passengers, "
        "an 81% increase compared with June 2025, when it handled approximately 281,000 passengers. "
        "More... Airport welcomes its millionth passenger three months earlier than last year"
    )
    assert (f.passengers, f.yoy_pct, f.month) == (510_152, 81.0, 6)


def test_may_the_verb_is_not_the_month():
    assert infer_month("The airport may handle 200,345 passengers") is None
    assert infer_month("In May the airport handled it") == 5


@pytest.mark.parametrize("month,published,expected", [
    (1, "20. 02. 2026", 2026),    # January figure published in February
    (11, "12. 12. 2025", 2025),
    (12, "14. 01. 2025", 2024),   # December figure published the next January
    (6, "10. 07. 2026", 2026),
])
def test_data_year_comes_from_the_publication_date(month, published, expected):
    assert data_year(month, published) == expected
