from scraper.draft_post import build_figures, issue_body, linkedin, title_for

OFFICIAL = [
    {"airport_code": "BTS", "year": 2026, "month": 8, "passengers": 625_742, "yoy_change_pct": 76},
    {"airport_code": "VIE", "year": 2026, "month": 8, "passengers": 3_172_284, "yoy_change_pct": -6.9},
    {"airport_code": "BTS", "year": 2026, "month": 6, "passengers": 510_152, "yoy_change_pct": 81},
    {"airport_code": "VIE", "year": 2026, "month": 6, "passengers": 2_832_434, "yoy_change_pct": -5.9},
]
FARES = [
    {"geo": "SK", "year": 2026, "month": 8, "annual_rate_pct": -61.2},
    {"geo": "AT", "year": 2026, "month": 8, "annual_rate_pct": 6.8},
    {"geo": "SK", "year": 2026, "month": 7, "annual_rate_pct": -43.6},
]


def test_latest_month_gap_and_ratio():
    f = build_figures(OFFICIAL, FARES)
    assert (f.year, f.month) == (2026, 8)
    assert f.gap_pp == 82.9
    assert f.size_ratio == 5.1
    assert title_for(f) == "Draft post: August 2026 (BTS + VIE)"


def test_title_lists_only_airports_that_published():
    f = build_figures(OFFICIAL[:1] + OFFICIAL[2:], None)      # Vienna has no August yet
    assert title_for(f) == "Draft post: August 2026 (BTS)"
    assert f.vie is None and f.gap_pp is None and f.size_ratio is None


def test_missing_yoy_is_derived_from_same_month_last_year():
    rows = [{"airport_code": "BTS", "year": 2026, "month": 8, "passengers": 200, "yoy_change_pct": None},
            {"airport_code": "BTS", "year": 2025, "month": 8, "passengers": 100, "yoy_change_pct": None}]
    assert build_figures(rows).bts["yoy"] == 100.0


def test_texts_use_the_right_number_format_and_placeholders():
    f = build_figures(OFFICIAL, FARES)
    sk, en = linkedin(f, "sk"), linkedin(f, "en")
    assert "625 742" in sk and "+76,0 %" in sk and "−6,9 %" in sk and "Viedeň je 5,1-krát väčšia." in sk
    assert "625,742" in en and "+76.0 %" in en and "Vienna is 5.1x larger." in en
    assert "Slovensko −61,2 %" in sk and "Slovakia -61.2 %" in en
    assert "[DOPLŇ" in sk and "[ADD" in en
    body = issue_body(f)
    assert "Nothing has been posted" in body and "first comment" in body


def test_no_data_no_draft():
    assert build_figures([], None) is None
