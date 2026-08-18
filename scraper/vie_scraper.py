"""
Scraper for Vienna Airport (VIE) monthly traffic results.

Source: https://viennaairport.com/en/company/investor_relations/news/traffic_results_1

The page lists headline news items in a fairly consistent recent format, e.g.:
  "June 2026 Traffic Results: 4,039,311 passengers handled by the Flughafen Wien
   Group (+0.2%) and 2,832,434 passengers at Vienna Airport (-5.9%)"

Older archive entries (pre-2022) use inconsistent phrasing ("X% Rise in Passenger
Volume for..."), so this parser focuses on the modern pattern and SKIPS anything
it can't confidently parse rather than guessing. Skipped items are returned
separately so you can review/extend the regex later.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

URL = "https://viennaairport.com/en/company/investor_relations/news/traffic_results_1"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

MONTH_YEAR_PATTERN = re.compile(
    r"(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<year>\d{4})\s+Traffic Results",
    re.IGNORECASE,
)

GROUP_PATTERN = re.compile(
    r"([\d,]+)\s*passengers\s*(?:\(([+-][\d.]+)%\)\s*)?handled by the Flughafen Wien\s*Group\s*(?:\(([+-][\d.]+)%\))?",
    re.IGNORECASE,
)

VIE_PATTERN = re.compile(
    r"([\d,]+)\s*passengers at Vienna\s*Airport\s*(?:\(([+-][\d.]+)%\))?",
    re.IGNORECASE,
)


@dataclass
class VieMonthlyRecord:
    airport_code: str
    year: int
    month: int
    passengers: int
    yoy_change_pct: float
    group_passengers: Optional[int]
    group_yoy_pct: Optional[float]
    source_url: str
    raw_headline: str


def fetch_html(url: str = URL) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; FKConsultingBot/0.1; +https://fkconsulting.example)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse(html: str) -> tuple[list[VieMonthlyRecord], list[str]]:
    """Returns (parsed_records, unparsed_headline_texts)."""
    soup = BeautifulSoup(html, "html.parser")

    full_text = soup.get_text(" ", strip=True)
    full_text = re.sub(r"\s+", " ", full_text)

    item_pattern = re.compile(
        r"\d{2}/\d{2}/\d{4}\s*\|\s*IR-Traffic results\s*(.+?)more details", re.IGNORECASE
    )
    items = item_pattern.findall(full_text)

    records: list[VieMonthlyRecord] = []
    unparsed: list[str] = []

    for headline in items:
        headline = headline.strip()

        my = MONTH_YEAR_PATTERN.search(headline)
        gm = GROUP_PATTERN.search(headline)
        vm = VIE_PATTERN.search(headline)

        if not (my and gm and vm):
            unparsed.append(headline)
            continue

        group_pct = gm.group(2) or gm.group(3)
        vie_pct = vm.group(2)

        if group_pct is None or vie_pct is None:
            unparsed.append(headline)
            continue

        records.append(
            VieMonthlyRecord(
                airport_code="VIE",
                year=int(my.group("year")),
                month=MONTHS[my.group("month").lower()],
                passengers=int(vm.group(1).replace(",", "")),
                yoy_change_pct=float(vie_pct),
                group_passengers=int(gm.group(1).replace(",", "")),
                group_yoy_pct=float(group_pct),
                source_url=URL,
                raw_headline=headline,
            )
        )

    return records, unparsed


def scrape() -> tuple[list[dict], list[str]]:
    html = fetch_html()
    records, unparsed = parse(html)
    return [asdict(r) for r in records], unparsed


if __name__ == "__main__":
    recs, skipped = scrape()
    print(f"Parsed {len(recs)} monthly records, skipped {len(skipped)} unrecognized headlines.")
    for r in recs[:5]:
        print(r)
    if skipped:
        print("\n--- Skipped (review these regex patterns later) ---")
        for s in skipped[:5]:
            print(s)
