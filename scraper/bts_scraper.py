"""
Scraper for Bratislava Airport (BTS) monthly passenger statistics.

Source: https://www.bts.aero/en/airport/press/latest-news/?year={year}&page={page}

BTS press releases are free-form natural language, not a consistent template.
Most of them DO explicitly name the month they're reporting on somewhere in
the text (e.g. "In May, the airport achieved...", "During August, airport
staff handled..."), which lets us auto-resolve the common case. But some
don't (e.g. "In the ninth month of the year..." instead of "September"), and
the article's PUBLISH date is not reliable for inferring the month either
(confirmed: articles are typically published 2-4 weeks after the month they
report on, so "22.10.2025" was about September, not October).

Approach: extract candidate passenger/percentage figures as before, and
additionally scan the surrounding text for an explicit month name.
  - If exactly ONE distinct month name is found -> high confidence,
    auto-set verified=1 and the resolved month.
  - If ZERO or MULTIPLE different month names are found -> ambiguous,
    leave as an unverified candidate (verified=0, month=NULL) for manual
    review, same as before. We deliberately do NOT guess in this case.

Also grabs the static annual table from /en/airport/press/statistics/ for
yearly totals (2019-2025), which IS structured and fully reliable.
"""

import re
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE = "https://www.bts.aero/en/airport/press/latest-news/"
STATS_URL = "https://www.bts.aero/en/airport/press/statistics/"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FKConsultingBot/0.1; +https://fkconsulting.example)"}

# Looks for "<number> ... passengers ... <sign><number>% ... increase"
CANDIDATE_PATTERN = re.compile(
    r"(?P<pax>[\d]{2,3}(?:,\d{3})+)\s*(?:arriving and departing\s*)?passengers"
    r"(?P<middle>[^.]{0,80}?)"
    r"(?P<pct>\d{1,3})%\s*increase",
    re.IGNORECASE,
)

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def infer_month(text: str) -> Optional[int]:
    """
    Looks for an explicit month name in the given text. Returns the month
    number ONLY if exactly one distinct month is mentioned (high
    confidence) -- returns None if zero or multiple different months are
    found, since guessing among several mentioned months would be worse
    than just flagging it for a human to read.
    """
    text_lower = text.lower()
    found = set()
    for name, num in MONTH_NAMES.items():
        if re.search(rf"\b{name}\b", text_lower):
            found.add(num)
    if len(found) == 1:
        return found.pop()
    return None


@dataclass
class BtsCandidateRecord:
    airport_code: str
    published_date: str  # DD.MM.YYYY as shown on site
    title: str
    passengers_mentioned: int
    yoy_pct_mentioned: float
    article_url: str
    context_sentence: str
    inferred_month: Optional[int]  # set if exactly one month name was found nearby, else None


@dataclass
class BtsAnnualRecord:
    airport_code: str
    year: int
    scheduled: int
    nonscheduled: int
    other: int
    total: int


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def scrape_news_candidates(year: int = 2026, max_pages: int = 3) -> list[BtsCandidateRecord]:
    candidates: list[BtsCandidateRecord] = []

    for page in range(1, max_pages + 1):
        url = f"{BASE}?page={page}&year={year}"
        html = fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        blocks = re.split(r"(?=\d{2}\.\s*\d{2}\.\s*\d{4}\s*[–-])", text)

        for block in blocks:
            date_match = re.match(r"(\d{2}\.\s*\d{2}\.\s*\d{4})", block)
            if not date_match:
                continue
            m = CANDIDATE_PATTERN.search(block)
            if not m:
                continue

            title = block[:80].split("\n")[0]
            context = block[date_match.end():date_match.end() + 300].strip()

            candidates.append(
                BtsCandidateRecord(
                    airport_code="BTS",
                    published_date=date_match.group(1),
                    title=title,
                    passengers_mentioned=int(m.group("pax").replace(",", "")),
                    yoy_pct_mentioned=float(m.group("pct")),
                    article_url=url,
                    context_sentence=context,
                    inferred_month=infer_month(f"{title} {context}"),
                )
            )

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
    print(f"  {len(auto)} auto-resolved (single clear month name found)")
    print(f"  {len(manual)} still need manual review (ambiguous or no month name)")
    for c in candidates:
        print(asdict(c))
