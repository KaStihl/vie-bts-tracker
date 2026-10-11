"""
Draft a LinkedIn / blog post from the newest data and write it as a GitHub issue body for review.

Run after the weekly scrape (see .github/workflows/scrape.yml). It never posts anything: it only prepares
text with the fresh numbers, and a human edits, checks and publishes it (see docs/content-plan/).

    python -m scraper.draft_post --out draft.md --title-file title.txt

Writes nothing (and exits 0) when there is no data. The title names the newest month and the airports that
have published it, so the workflow opens one issue per new release and does not repeat itself.
"""

from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from typing import Optional

MONTHS_SK = ["január", "február", "marec", "apríl", "máj", "jún", "júl", "august", "september", "október",
             "november", "december"]
REPORT_URL = "https://fkslab.com/dashboard/"
SOURCES = {
    "BTS": "https://www.bts.aero/en/airport/press/latest-news/",
    "VIE": "https://viennaairport.com/en/company/investor_relations/news/traffic_results_1",
}


@dataclass
class Figures:
    year: int
    month: int
    bts: Optional[dict]          # {"passengers": int, "yoy": float | None} or None
    vie: Optional[dict]
    gap_pp: Optional[float]
    size_ratio: Optional[float]
    fares: Optional[dict]        # {"year", "month", "SK": rate, "AT": rate} or None


# ---------------------------------------------------------------- number formatting
def fmt_int(n: int, lang: str) -> str:
    s = f"{n:,}"
    return s.replace(",", " ") if lang == "sk" else s


def fmt_pct(x: float, lang: str, digits: int = 1) -> str:
    s = f"{x:+.{digits}f}"
    s = s.replace("-", "−") if lang == "sk" else s
    return (s.replace(".", ",") + " %") if lang == "sk" else s + " %"


def month_en(month: int, year: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def month_sk(month: int, year: int) -> str:
    return f"{MONTHS_SK[month - 1]} {year}"


# ---------------------------------------------------------------- the data -> figures
def build_figures(official: list[dict], fares: Optional[list[dict]] = None) -> Optional[Figures]:
    """official: verified press-release rows (airport_code, year, month, passengers, yoy_change_pct)."""
    rows = [r for r in official if r.get("month")]
    if not rows:
        return None
    year, month = max((r["year"], r["month"]) for r in rows)
    pick = {r["airport_code"]: r for r in rows if (r["year"], r["month"]) == (year, month)}

    def fig(code):
        r = pick.get(code)
        if not r:
            return None
        yoy = r.get("yoy_change_pct")
        if yoy is None:                       # derive from the same month a year earlier, same source
            prev = next((p for p in rows if p["airport_code"] == code and (p["year"], p["month"]) == (year - 1, month)), None)
            if prev and prev["passengers"]:
                yoy = round((r["passengers"] / prev["passengers"] - 1) * 100, 1)
        return {"passengers": r["passengers"], "yoy": float(yoy) if yoy is not None else None}

    bts, vie = fig("BTS"), fig("VIE")
    gap = ratio = None
    if bts and vie:
        if bts["yoy"] is not None and vie["yoy"] is not None:
            gap = round(bts["yoy"] - vie["yoy"], 1)
        if bts["passengers"]:
            ratio = round(vie["passengers"] / bts["passengers"], 1)
    fare = None
    if fares:
        ym = max((r["year"], r["month"]) for r in fares)
        rates = {r["geo"]: float(r["annual_rate_pct"]) for r in fares if (r["year"], r["month"]) == ym}
        if "SK" in rates:
            fare = {"year": ym[0], "month": ym[1], **{k: rates[k] for k in ("SK", "AT", "EU27_2020") if k in rates}}
    return Figures(year, month, bts, vie, gap, ratio, fare)


def title_for(f: Figures) -> str:
    who = " + ".join(c for c, v in (("BTS", f.bts), ("VIE", f.vie)) if v)
    return f"Draft post: {month_en(f.month, f.year)} ({who})"


# ---------------------------------------------------------------- the text
def _line(name: str, d: Optional[dict], lang: str, unit: str) -> Optional[str]:
    if not d:
        return None
    s = name + ": " + fmt_int(d["passengers"], lang) + " " + unit
    if d["yoy"] is not None:
        s += " (" + fmt_pct(d["yoy"], lang) + ")"
    return s


def linkedin(f: Figures, lang: str) -> str:
    sk = lang == "sk"
    dec = "," if sk else "."
    if sk:
        head = "Údaje za " + month_sk(f.month, f.year) + ": [DOPLŇ jednu vetu: čo je na nich prekvapivé?]"
        names, unit = ("Bratislava", "Viedeň"), "pasažierov"
    else:
        head = "Figures for " + month_en(f.month, f.year) + ": [ADD one sentence: what is surprising about them?]"
        names, unit = ("Bratislava", "Vienna"), "passengers"
    parts = [head, ""]
    for line in (_line(names[0], f.bts, lang, unit), _line(names[1], f.vie, lang, unit)):
        if line:
            parts.append("• " + line)
    if f.gap_pp is not None:
        gap = ("%.1f" % abs(f.gap_pp)).replace(".", dec)
        parts.append(("• Rozdiel v rastoch: " if sk else "• Growth gap: ") + gap + " pp")
    if f.size_ratio is not None:
        ratio = str(f.size_ratio).replace(".", dec)
        parts.append("• " + (("Viedeň je " + ratio + "-krát väčšia.") if sk else ("Vienna is " + ratio + "x larger.")))
    if f.fares:
        label = month_sk(f.fares["month"], f.fares["year"]) if sk else month_en(f.fares["month"], f.fares["year"])
        txt = ("Ceny letenky (Eurostat, " + label + "): Slovensko " if sk else "Airfares (Eurostat, " + label + "): Slovakia ")
        txt += fmt_pct(f.fares["SK"], lang)
        if f.fares.get("AT") is not None:
            txt += (", Rakúsko " if sk else ", Austria ") + fmt_pct(f.fares["AT"], lang)
        parts.append("• " + txt)
    parts += ["", "[DOPLŇ tvoj vlastný komentár]" if sk else "[ADD your own comment]", "",
              "Zdroje a živý report v prvom komentári." if sk else "Sources and the live report in the first comment.",
              "", "#PowerBI #DataViz #Aviation"]
    return "\n".join(parts)


def issue_body(f: Figures) -> str:
    rows = []
    for name, code, d in (("Bratislava (BTS)", "BTS", f.bts), ("Vienna (VIE)", "VIE", f.vie)):
        if d:
            yoy = "n/a" if d["yoy"] is None else fmt_pct(d["yoy"], "en")
            rows.append(f"| {name} | {fmt_int(d['passengers'], 'en')} | {yoy} | [{code} release]({SOURCES[code]}) |")
    table = "\n".join(rows)
    return f"""Automatic draft after the weekly scrape. **Nothing has been posted.** Edit the `[...]` parts, check every
number against its source, then publish yourself.

## Numbers ({month_en(f.month, f.year)})

| Airport | Passengers | Year over year | Source |
|---|---|---|---|
{table}

Vienna's figure is the airport's own release. The size ratio and the growth gap use the two airports' own releases.

## LinkedIn (SK)

```
{linkedin(f, 'sk')}
```

## LinkedIn (EN)

```
{linkedin(f, 'en')}
```

## Checklist

- [ ] Every number matches the airport release linked above (Vienna and Bratislava count differently from Eurostat)
- [ ] Replaced the `[...]` placeholders and added my own comment
- [ ] Refreshed and published the Power BI report so the dashboard shows the same month: {REPORT_URL}
- [ ] Image attached (screenshot of the Trend page)
- [ ] Link in the **first comment**, not in the post
- [ ] Blog post written or skipped (content plan: `docs/content-plan/` on branch `content-drafts`)
- [ ] Posted, then close this issue
"""


# ---------------------------------------------------------------- CLI
def _load(conn):
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT airport_code, year, month, passengers, yoy_change_pct FROM monthly_traffic "
                    "WHERE verified = 1 AND month IS NOT NULL")
        official = [dict(r) for r in cur.fetchall()]
        try:
            cur.execute("SELECT geo, year, month, annual_rate_pct FROM public.eurostat_airfares")
            fares = [dict(r) for r in cur.fetchall()]
        except Exception:                    # table not created yet
            conn.rollback()
            fares = []
    return official, fares


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="draft.md")
    ap.add_argument("--title-file", default="title.txt")
    args = ap.parse_args(argv)
    from . import db
    conn = db.get_connection()
    official, fares = _load(conn)
    conn.close()
    f = build_figures(official, fares)
    if not f:
        print("No monthly data, no draft.")
        return 0
    title = title_for(f)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(issue_body(f))
    with open(args.title_file, "w", encoding="utf-8") as fh:
        fh.write(title)
    print(title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
