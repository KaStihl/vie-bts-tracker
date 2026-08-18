"""
Scraper for BTS annual report PDF (Vyrocna sprava).

Source: https://www.bts.aero/en/airport/press/annual-report/

Unlike the monthly press-release scraper (bts_scraper.py), this pulls a much
richer, cleanly structured table directly from the airport's own annual
report PDF:
  - "Table 2: Monthly Overview of Passenger Numbers" gives ~6 years of clean
    monthly data in ONE table, per report.

This is a far more reliable historical backfill source than parsing free-text
press releases. Use this once for the historical backfill, and re-run
roughly once/year when a new annual report is published to extend the
window (each new report re-publishes the trailing 6 years, so you don't need
to keep every past PDF -- just the latest one).

Validated: regex-extracted monthly figures for 2019-2024 sum exactly to the
airport's own published annual totals (see test in project notes). Not yet
tested against a LIVE pdfplumber extraction (sandbox has no network access
to bts.aero) -- run this for real and share output if numbers look off.

Requires: pip install pdfplumber requests beautifulsoup4
"""

import re
import io
from dataclasses import dataclass, asdict

import requests
import pdfplumber
from bs4 import BeautifulSoup

LISTING_URL = "https://www.bts.aero/en/airport/press/annual-report/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FKConsultingBot/0.1; +https://fkconsulting.example)"}

# Matches a year at the start of a data row, e.g. "2019 125 839 119 406 ... 2 290242"
YEAR_ROW_PATTERN = re.compile(r"^(20\d{2})\s+(.*)$")

# Captures ONE Slovak-formatted number that may have a single thousands-separator
# space, e.g. "839" or "125 839". Deliberately does NOT try to also grab a
# second separator group -- monthly BTS figures are all under 500,000, so one
# optional "\s\d{3}" group is enough and keeps the pattern unambiguous. The
# trailing annual TOTAL on the same line is intentionally NOT parsed here (it
# sometimes loses its internal space during text extraction, e.g. "2 290242"
# instead of "2 290 242" -- ambiguous to parse safely). We already get clean
# annual totals from bts_scraper.py's simpler annual stats page, so this
# scraper only needs the 12 monthly values.
NUMBER_TOKEN = r"\d{1,3}(?:\s\d{3})?"

REALISTIC_MIN = 0
REALISTIC_MAX = 500_000  # sanity ceiling for a single month at this airport


@dataclass
class BtsAnnualReportMonthly:
    airport_code: str
    year: int
    month: int
    passengers: int
    source_url: str


def find_latest_report_url() -> str:
    """Listing page shows reports newest-first; grab the first PDF link."""
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            return href if href.startswith("http") else f"https://www.bts.aero{href}"

    raise RuntimeError(
        "No PDF link found on annual report listing page -- site structure may have changed."
    )


def download_pdf(url: str) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


def parse_monthly_table(pdf_bytes: bytes) -> tuple[list[BtsAnnualReportMonthly], list[str]]:
    """
    Returns (records, warnings). Scans every page for year-shaped data rows
    rather than anchoring on a table heading, since heading wording/table
    numbering can shift between report years -- the row SHAPE (year followed
    by >=12 Slovak-formatted numbers) is what we key off.
    """
    records: list[BtsAnnualReportMonthly] = []
    warnings: list[str] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                m = YEAR_ROW_PATTERN.match(line)
                if not m:
                    continue

                year = int(m.group(1))
                if year < 2010 or year > 2030:
                    continue  # guard against stray 4-digit numbers matching

                rest = m.group(2)
                numbers = re.findall(NUMBER_TOKEN, rest)
                if len(numbers) < 12:
                    continue  # not a monthly data row

                month_values = numbers[:12]
                try:
                    parsed = [int(n.replace(" ", "").replace("\xa0", "")) for n in month_values]
                except ValueError:
                    warnings.append(f"[p{page_num}] Could not parse numbers on line: {line!r}")
                    continue

                if any(v > REALISTIC_MAX or v < REALISTIC_MIN for v in parsed):
                    warnings.append(
                        f"[p{page_num}] Suspicious value(s) for year {year}, skipped: {parsed}"
                    )
                    continue

                for month_idx, value in enumerate(parsed, start=1):
                    records.append(
                        BtsAnnualReportMonthly(
                            airport_code="BTS",
                            year=year,
                            month=month_idx,
                            passengers=value,
                            source_url=LISTING_URL,
                        )
                    )

    return records, warnings


def scrape() -> tuple[list[dict], list[str]]:
    pdf_url = find_latest_report_url()
    pdf_bytes = download_pdf(pdf_url)
    records, warnings = parse_monthly_table(pdf_bytes)
    return [asdict(r) for r in records], warnings


if __name__ == "__main__":
    recs, warns = scrape()
    print(f"Parsed {len(recs)} monthly records from BTS annual report PDF.")
    years_found = sorted(set(r["year"] for r in recs))
    print(f"Years covered: {years_found}")
    for r in recs[:15]:
        print(r)
    if warns:
        print("\n--- Warnings (review these) ---")
        for w in warns:
            print(w)
