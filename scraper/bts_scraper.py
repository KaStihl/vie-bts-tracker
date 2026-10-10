"""
Scraper for Bratislava Airport (BTS) monthly passenger statistics.

Source: https://www.bts.aero/en/airport/press/latest-news/?year={year}&page={page}

BTS press releases are free-form natural language, not a consistent template.
extract_monthly_figure() turns one article into at most one MONTHLY passenger
figure, and is deliberately conservative -- it returns None rather than guess:

  * Cumulative / annual figures are rejected ("from January to the end of
    March", "first quarter", "in 2024 ... a total of", "one-millionth
    passenger"). Earlier versions stored these as monthly rows (e.g. the
    Q1-2025 total of 273,807 and the 2024 annual total of 1,948,008), which
    produced phantom spikes in the dashboard.
  * Rounded counts ("more than 360,000", "246,000") are ignored: they are not
    the airport's real count.
  * The growth percentage is OPTIONAL. Many releases only give the count; the
    year-over-year change can be derived downstream from last year's month.
  * The month must be unambiguous: exactly one distinct month name or ordinal
    ("the ninth month of the year") in the article lead. Otherwise the figure is
    kept as an unverified candidate for manual review.
  * The DATA year is derived from the publication date: a release is published
    after the month it reports on, so if the month is not earlier than the
    publication month it belongs to the previous year (a January release about
    December is December of last year, not of the current year).

Also grabs the static annual table from /en/airport/press/statistics/ for
yearly totals, which IS structured and fully reliable.
"""

import re
import time
from dataclasses import dataclass, asdict
from typing import Optional

from bs4 import BeautifulSoup

from .http_util import make_session

BASE = "https://www.bts.aero/en/airport/press/latest-news/"
STATS_URL = "https://www.bts.aero/en/airport/press/statistics/"

MONTH_NAMES = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
ORDINAL_MONTHS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}

_MONTH_ALT = "|".join(MONTH_NAMES)
LEAD_CHARS = 900  # the headline figure is always in the first paragraph

# A count with thousands separators: "625,742", "1 948 008", "163 949".
COUNT_RE = re.compile(r"(?<![\d,.])(\d{1,3}(?:[,  ]\d{3})+)(?![\d])")
# The count must be talking about passengers.
PASSENGER_NEAR_RE = re.compile(r"passenger|traveller|travelers|travellers", re.IGNORECASE)
APPROX_BEFORE_RE = re.compile(
    r"(more than|over|around|approximately|approx\.?|nearly|almost|about|exceeding|up to|at least)\s*$",
    re.IGNORECASE,
)

# Anything that makes the figure a total over several months or a whole year.
CUMULATIVE_RE = re.compile(
    rf"from\s+(?:{_MONTH_ALT})\s+(?:to|until|through)\b"
    r"|first\s+(?:quarter|half|three months|four months|\w+\s+months)"
    r"|since the beginning of the year|year[- ]to[- ]date|since the start of the year"
    r"|summer months|winter months|\bmillionth\b"
    r"|\bin\s+20\d{2}\b"                      # "... in 2024" => annual
    r"|closed\s+20\d{2}|the (?:whole|entire) year",
    re.IGNORECASE,
)

PCT_AFTER_RE = re.compile(
    r"(?P<num>\d{1,3}(?:[.,]\d+)?)\s*(?:%|percent)\s*(?:year[- ]on[- ]year\s+)?(?P<word>increase|growth|rise|decrease|decline|drop|fall)",
    re.IGNORECASE,
)
PCT_BEFORE_RE = re.compile(
    r"(?P<word>increase|growth|rise|decrease|decline|drop|fall)\s+of\s+(?P<num>\d{1,3}(?:[.,]\d+)?)\s*(?:%|percent)",
    re.IGNORECASE,
)
NEGATIVE_WORDS = {"decrease", "decline", "drop", "fall"}


@dataclass
class MonthlyFigure:
    passengers: int
    yoy_pct: Optional[float]
    month: Optional[int]
    approximate: bool


def _months_in(text: str) -> set[int]:
    """Month numbers named in `text` (capitalised names only, so the verb 'may' is ignored)
    plus ordinal forms such as 'the ninth month of the year'."""
    found = {MONTH_NAMES[m] for m in re.findall(rf"\b({_MONTH_ALT})\b", text)}
    for word, num in ORDINAL_MONTHS.items():
        if re.search(rf"\b{word}\s+month\b", text, re.IGNORECASE):
            found.add(num)
    return found


def infer_month(text: str) -> Optional[int]:
    """The month number if exactly one distinct month is referred to, else None."""
    found = _months_in(text)
    return found.pop() if len(found) == 1 else None


def data_year(month: int, published_day_month_year: str) -> int:
    """Year the figure belongs to, from the publication date ('DD. MM. YYYY').
    Releases come out after the month they describe, so month >= publication
    month means the previous calendar year."""
    parts = re.findall(r"\d+", published_day_month_year)
    pub_month, pub_year = int(parts[1]), int(parts[2])
    return pub_year if month < pub_month else pub_year - 1


def extract_monthly_figure(lead: str) -> Optional[MonthlyFigure]:
    """Extract one monthly passenger figure from an article lead, or None."""
    # The listing page appends the NEXT article's headline after each "More..."
    # link; cut the teaser there so that headline cannot leak into this one.
    lead = re.split(r"More\.\.\.", lead, maxsplit=1)[0]
    text = re.sub(r"\s+", " ", lead[:LEAD_CHARS]).strip()

    if CUMULATIVE_RE.search(text):
        return None

    count_match = None
    for m in COUNT_RE.finditer(text):
        window = text[max(0, m.start() - 60): m.end() + 60]
        if PASSENGER_NEAR_RE.search(window):
            count_match = m
            break
    if count_match is None:
        return None

    passengers = int(re.sub(r"[,  ]", "", count_match.group(1)))
    if passengers < 10_000:
        return None
    # "more than 360,000" or a round "246,000": a rounded figure, not the real count.
    approximate = passengers % 1000 == 0 or bool(
        APPROX_BEFORE_RE.search(text[max(0, count_match.start() - 20): count_match.start()])
    )

    yoy = None
    for regex in (PCT_AFTER_RE, PCT_BEFORE_RE):
        pm = regex.search(text)
        if pm:
            value = float(pm.group("num").replace(",", "."))
            if value <= 1000:
                yoy = -value if pm.group("word").lower() in NEGATIVE_WORDS else value
                break

    return MonthlyFigure(passengers=passengers, yoy_pct=yoy, month=infer_month(text), approximate=approximate)


@dataclass
class BtsCandidateRecord:
    airport_code: str
    published_date: str            # DD. MM. YYYY as shown on the site
    title: str
    passengers_mentioned: int
    yoy_pct_mentioned: Optional[float]
    article_url: str
    context_sentence: str
    inferred_month: Optional[int]  # None => ambiguous, needs manual review
    data_year: Optional[int]       # year the figure belongs to (None when month unknown)


@dataclass
class BtsAnnualRecord:
    airport_code: str
    year: int
    scheduled: int
    nonscheduled: int
    other: int
    total: int


def fetch(url: str, session=None) -> str:
    session = session or make_session()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_news_page(html: str, url: str) -> list[BtsCandidateRecord]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    blocks = re.split(r"(?=\d{2}\.\s*\d{2}\.\s*\d{4}\s*[–-])", text)

    records: list[BtsCandidateRecord] = []
    for block in blocks:
        date_match = re.match(r"(\d{2}\.\s*\d{2}\.\s*\d{4})", block)
        if not date_match:
            continue
        lead = block[date_match.end():]
        figure = extract_monthly_figure(lead)
        if figure is None or figure.approximate:
            continue
        published = date_match.group(1)
        records.append(
            BtsCandidateRecord(
                airport_code="BTS",
                published_date=published,
                title=lead.lstrip(" –-\n")[:80].split("\n")[0],
                passengers_mentioned=figure.passengers,
                yoy_pct_mentioned=figure.yoy_pct,
                article_url=url,
                context_sentence=re.sub(r"\s+", " ", lead[:300]).strip(),
                inferred_month=figure.month,
                data_year=data_year(figure.month, published) if figure.month else None,
            )
        )
    return records


def scrape_news_candidates(year: int = 2026, max_pages: int = 4) -> list[BtsCandidateRecord]:
    session = make_session()
    candidates: list[BtsCandidateRecord] = []
    seen: set[tuple[str, int]] = set()  # the site repeats the last page when paging past the end

    for page in range(1, max_pages + 1):
        url = f"{BASE}?page={page}&year={year}"
        page_records = parse_news_page(fetch(url, session), url)
        new = [r for r in page_records if (r.published_date, r.passengers_mentioned) not in seen]
        for r in new:
            seen.add((r.published_date, r.passengers_mentioned))
        candidates.extend(new)
        time.sleep(1)  # be polite to a small airport website
    return candidates


def scrape_annual_stats() -> list[BtsAnnualRecord]:
    html = fetch(STATS_URL)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    records: list[BtsAnnualRecord] = []
    rows = table.find_all("tr")
    for row in rows[1:]:  # skip header
        cells = [c.get_text(strip=True).replace("\xa0", " ") for c in row.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 5:
            continue
        try:
            year = int(re.sub(r"\D", "", cells[0]))
            scheduled = int(cells[1].replace(" ", "").replace(",", ""))
            nonscheduled = int(cells[2].replace(" ", "").replace(",", ""))
            other = int(cells[3].replace(" ", "").replace(",", ""))
            total = int(cells[4].replace(" ", "").replace(",", ""))
        except ValueError:
            continue

        records.append(
            BtsAnnualRecord(
                airport_code="BTS",
                year=year,
                scheduled=scheduled,
                nonscheduled=nonscheduled,
                other=other,
                total=total,
            )
        )

    return records


if __name__ == "__main__":
    annual = scrape_annual_stats()
    print(f"Annual records: {len(annual)}")
    for a in annual:
        print(asdict(a))

    print("\nMonthly candidates:")
    candidates = scrape_news_candidates(year=2026)
    auto = [c for c in candidates if c.inferred_month is not None]
    manual = [c for c in candidates if c.inferred_month is None]
    print(f"  {len(auto)} auto-resolved, {len(manual)} need manual review")
    for c in candidates:
        print(asdict(c))
