"""
Scraper for Vienna Airport (VIE) monthly traffic results.

Source: https://viennaairport.com/en/company/investor_relations/news/traffic_results_1

The page lists ~190 news items. Monthly traffic headlines look like

  "June 2026 Traffic Results: 4,039,311 passengers handled by the Flughafen Wien
   Group (+0.2%) and 2,832,434 passengers at Vienna Airport (-5.9%)"

but the wording drifts over the years ("Traffic result:", "Traffic results -",
"... and 2,109,407 by Vienna Airport", "Passengers in the Flughafen-Wien Group"),
and from 2023 backwards the headline carries no percentage at all. The parser
therefore requires only what matters -- a month/year at the start and exact
passenger counts for the Group and for Vienna Airport -- and treats the
percentages as optional (year-over-year change can be derived from the previous
year's month downstream).

Headlines with rounded counts ("2.0 million passengers") or without both exact
counts (quarterly / annual business results) are returned as unparsed.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional

from bs4 import BeautifulSoup

from .http_util import make_session

URL = "https://viennaairport.com/en/company/investor_relations/news/traffic_results_1"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

# A headline is monthly traffic only if it STARTS with "<Month> <Year>".
MONTH_YEAR_PATTERN = re.compile(
    r"^\s*(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)

PCT = r"\(\s*([+\-−][\d.]+)\s*%\s*\)"
NUM = r"(\d{1,3}(?:,\d{3})+)"
GROUP_NAME = r"Flughafen[\s-]+Wien[\s-]+Group"

# "<n> passengers [(+x%)] [handled] by|in [the] Flughafen Wien Group [(+x%)]"
GROUP_PATTERN = re.compile(
    NUM + r"\s*passengers\s*(?:" + PCT + r"\s*)?(?:handled\s+)?(?:by|in)\s+(?:the\s+)?" + GROUP_NAME + r"\s*(?:" + PCT + r")?",
    re.IGNORECASE,
)

# "<n> passengers at Vienna Airport [(x%)]"  /  "<n> by Vienna (International) Airport"
VIE_PATTERN = re.compile(
    r"(?:and\s+)?" + NUM + r"\s*(?:passengers\s+)?(?:at|by)\s+Vienna\s+(?:International\s+)?Airport\s*(?:" + PCT + r")?",
    re.IGNORECASE,
)


def _pct(raw: Optional[str]) -> Optional[float]:
    return float(raw.replace("−", "-")) if raw else None


@dataclass
class VieMonthlyRecord:
    airport_code: str
    year: int
    month: int
    passengers: int
    yoy_change_pct: Optional[float]
    group_passengers: Optional[int]
    group_yoy_pct: Optional[float]
    source_url: str
    raw_headline: str


def fetch_html(url: str = URL, session=None) -> str:
    session = session or make_session()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_headline(headline: str) -> Optional[VieMonthlyRecord]:
    """One monthly record from a headline, or None if it is not an exact monthly traffic headline."""
    my = MONTH_YEAR_PATTERN.search(headline)
    if not my:
        return None
    gm = GROUP_PATTERN.search(headline)
    vm = VIE_PATTERN.search(headline)
    if not (gm and vm):
        return None

    vie_passengers = int(vm.group(1).replace(",", ""))
    group_passengers = int(gm.group(1).replace(",", ""))
    # Sanity: Vienna Airport is always a strict subset of the Group.
    if not (0 < vie_passengers < group_passengers):
        return None

    return VieMonthlyRecord(
        airport_code="VIE",
        year=int(my.group("year")),
        month=MONTHS[my.group("month").lower()],
        passengers=vie_passengers,
        yoy_change_pct=_pct(vm.group(2)),
        group_passengers=group_passengers,
        group_yoy_pct=_pct(gm.group(2) or gm.group(3)),
        source_url=URL,
        raw_headline=headline,
    )


def parse(html: str) -> tuple[list[VieMonthlyRecord], list[str]]:
    """Returns (parsed_records, unparsed_headline_texts)."""
    soup = BeautifulSoup(html, "html.parser")
    full_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    item_pattern = re.compile(
        r"\d{2}/\d{2}/\d{4}\s*\|\s*IR-Traffic results\s*(.+?)more details", re.IGNORECASE
    )

    records: dict[tuple[int, int], VieMonthlyRecord] = {}
    unparsed: list[str] = []
    for headline in item_pattern.findall(full_text):
        headline = headline.strip()
        record = parse_headline(headline)
        if record is None:
            unparsed.append(headline)
        else:
            records.setdefault((record.year, record.month), record)  # newest item first wins

    return list(records.values()), unparsed


def scrape() -> tuple[list[dict], list[str]]:
    html = fetch_html()
    records, unparsed = parse(html)
    return [asdict(r) for r in records], unparsed


if __name__ == "__main__":
    recs, skipped = scrape()
    print(f"Parsed {len(recs)} monthly records, skipped {len(skipped)} non-monthly/rounded headlines.")
    for r in recs[:5]:
        print(r)
