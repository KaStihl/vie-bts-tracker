"""
Scraper for Bratislava Airport (BTS) monthly passenger statistics.

Source: https://www.bts.aero/en/airport/press/latest-news/?year={year}&page={page}

Unlike Vienna, BTS does not publish a single consistent monthly headline format --
press releases are written in free-form natural language (e.g. "handling more
than half a million passengers", "achieved another all-time monthly record,
handling 398,639 arriving and departing passengers... a 131% increase
year-on-year compared to May 2025"). Because of this, full automatic parsing is
NOT reliable. This scraper extracts CANDIDATE numbers (passenger count + YoY %)
plus the surrounding sentence, and flags them for a quick manual sanity-check
rather than pretending to be 100% automatic. In practice this takes ~2 minutes/month.

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

# Looks for "<number> ... passengers ... <sign><number>% ... year-on-year|compared"
CANDIDATE_PATTERN = re.compile(
    r"(?P<pax>[\d]{2,3}(?:,\d{3})+)\s*(?:arriving and departing\s*)?passengers"
    r"(?P<middle>[^.]{0,80}?)"
    r"(?P<pct>\d{1,3})%\s*increase",
    re.IGNORECASE,
)


@dataclass
class BtsCandidateRecord:
    airport_code: str
    published_date: str  # DD.MM.YYYY as shown on site, needs human check for which month it refers to
    title: str
    passengers_mentioned: int
    yoy_pct_mentioned: float
    article_url: str
    context_sentence: str


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

        # Each article is an <h2>/<h3>-style heading link followed by a date + summary paragraph.
        # We work off the raw text blocks since markup structure can shift between site updates.
        text = soup.get_text("\n", strip=True)

        # Split roughly on date markers "DD. MM. YYYY –"
        blocks = re.split(r"(?=\d{2}\.\s*\d{2}\.\s*\d{4}\s*[–-])", text)

        for block in blocks:
            date_match = re.match(r"(\d{2}\.\s*\d{2}\.\s*\d{4})", block)
            if not date_match:
                continue
            m = CANDIDATE_PATTERN.search(block)
            if not m:
                continue

            candidates.append(
                BtsCandidateRecord(
                    airport_code="BTS",
                    published_date=date_match.group(1),
                    title=block[:80].split("\n")[0],
                    passengers_mentioned=int(m.group("pax").replace(",", "")),
                    yoy_pct_mentioned=float(m.group("pct")),
                    article_url=url,
                    context_sentence=block[date_match.end():date_match.end() + 300].strip(),
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

    print("\nMonthly candidates (need quick manual review):")
    candidates = scrape_news_candidates(year=2026)
    for c in candidates:
        print(asdict(c))
