"""
Builds the redesigned "Home" and "Source" pages (native PBIR, same look as the new "Trend" page).

    python PBI/tools/build_trend_page.py      # first (measures + Trend page)
    python PBI/tools/build_info_pages.py      # then this

Both old pages were a baked background picture plus one big text box; they are kept, renamed
"... (old design)" and hidden. Idempotent. Close Desktop before running.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_trend_page as t  # noqa: E402  (shared helpers and palette)

HOME_ID, SRC_ID = "3a9c61d2e8b74f05a1c7", "b5f20e7a4d9c43168e3a"
OLD_HOME, OLD_SRC = "24f8598d534d69b83d11", "4c36a70600de705ca9cd"
LINK = "#1B6E9C"


def rich_textbox(label, x, y, w, h, z, paras, pad=24):
    paragraphs = []
    for p in paras:
        runs = []
        for text, size, hex_, bold, *rest in p["runs"]:
            style = {"fontFamily": "Segoe UI Semibold" if bold else "Segoe UI", "fontSize": f"{size}pt", "color": hex_}
            if bold:
                style["fontWeight"] = "bold"
            run = {"value": text, "textStyle": style}
            if rest and rest[0]:
                run["url"] = rest[0]
            runs.append(run)
        para = {"textRuns": runs}
        if p.get("bullet"):
            para.update({"listType": "bullet", "indent": 1})
        paragraphs.append(para)
    body = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]}}
    return t.visual(label, x, y, w, h, z, body, t.container(None, pad=pad))


def P(text, size=15, hex_=t.NAVY, bold=False, bullet=False):
    return {"runs": [(text, size, hex_, bold)], "bullet": bullet}


def LINKP(label, text, url):
    return {"runs": [(label, 14, t.NAVY, True), (text, 14, LINK, False, url)], "bullet": True}


GAP = P(" ", 6)


def frame(prefix, subtitle):
    """Header band + left navigation rail + footer shared by the info pages."""
    out = {}

    def add(pair):
        out[pair[0]] = pair[1]

    L = lambda s: f"{prefix}-{s}"  # noqa: E731
    add(t.shape(L("hdr"), 0, 0, 1920, 112, 0, t.NAVY))
    add(t.textbox(L("title"), 40, 8, 1300, 64, 1000, [("Vienna ⇄ Bratislava Aviation Tracker", 28, "#FFFFFF", True)]))
    add(t.textbox(L("sub"), 40, 68, 1400, 40, 2000, [(subtitle, 16, t.LIGHT_TEAL, False)]))
    add(t.textbox(L("brand"), 1500, 14, 380, 58, 3000, [("FK's LAB", 26, "#FFFFFF", True)], align="right"))
    add(t.textbox(L("brand2"), 1500, 68, 380, 36, 3500, [("fkslab.com", 12, t.LIGHT_TEAL, False)], align="right"))
    add(t.shape(L("rail"), 24, 136, 208, 862, 4000, t.CARD, rounded=12, shadow=True))
    add(t.textbox(L("pg"), 40, 144, 176, 38, 4600, [("PAGES", 11, t.MUTED, True)]))
    nav_name, nav = t.build_nav(40, 186, 176, 130, 4700)
    nav["name"] = t.vid(L("nav")); out[nav["name"]] = nav
    add(t.textbox(L("src"), 248, 1010, 1100, 42, 7100,
                  [("Sources: Vienna Airport and Bratislava Airport press releases and annual reports · OpenSky Network · code on GitHub: KaStihl/vie-bts-tracker",
                    11, t.MUTED, False)]))
    add(t.textbox(L("lrl"), 1370, 1012, 190, 38, 7200, [("Last refresh (UTC):", 11, t.MUTED, False)], align="right"))
    lr_name, lr = t.build_last_refresh(1566, 1008, 330, 46, 7300)
    lr["name"] = t.vid(L("lr")); out[lr["name"]] = lr
    return out


def write_page(page_id, display_name, visuals):
    page = t.load(t.OLD / "page.json")
    page["name"] = page_id
    page["displayName"] = display_name
    page.pop("visibility", None)
    page.pop("filterConfig", None)
    page["objects"] = {"background": [{"properties": {"color": t.color(t.BG), "transparency": t.D(0)}}]}
    root = t.REPORT / "pages" / page_id
    t.dump(root / "page.json", page)
    for name, data in visuals.items():
        t.dump(root / "visuals" / name / "visual.json", data)
    for f in (root / "visuals").glob("*/visual.json"):
        if f.parent.name not in visuals:
            f.unlink()


def home():
    v = frame("home", "Monthly passenger traffic  ·  Air route intelligence")
    about = [
        P("ABOUT THIS DASHBOARD", 11, t.MUTED, True), GAP,
        P("This dashboard tracks how low-cost carrier capacity has shifted between Vienna (VIE) and Bratislava (BTS) airports, "
          "following Austria's aviation tax and Wizz Air's exit from Vienna in March 2026.", 19),
        GAP,
        P("It is for anyone following the Vienna–Bratislava aviation story, and for a look at how the underlying data pipeline is built: "
          "a public case study in BI and data engineering with official sources, verified data and a transparent methodology.", 16, t.MUTED),
        GAP,
        P("Data comes from official press releases and annual reports of both airports, not from estimates. It is collected automatically "
          "and reviewed by hand where the sources are less structured.", 16, t.MUTED),
        GAP,
        P("Airline-level data (who flies where) comes from real aircraft movements via the OpenSky Network. That history is still short and "
          "incomplete, so airline views are not published yet.", 16, t.MUTED),
    ]
    for lbl, x, fields, title, col, sub in (
        ("home-kpi-vie", 248,
         [{"prop": "VIE Latest Passengers", "name": "Passengers", "kind": "pax", "size": 32, "hex": t.NAVY},
          {"prop": "VIE Latest YoY", "name": "vs same month last year", "kind": "pct", "size": 32, "color_measure": "VIE YoY Color"},
          {"prop": "VIE Latest Month", "name": "Latest month", "kind": "text", "size": 20, "hex": t.MUTED}], "VIENNA", t.TEAL, None),
        ("home-kpi-bts", 802,
         [{"prop": "BTS Latest Passengers", "name": "Passengers", "kind": "pax", "size": 32, "hex": t.NAVY},
          {"prop": "BTS Latest YoY", "name": "vs same month last year", "kind": "pct", "size": 32, "color_measure": "BTS YoY Color"},
          {"prop": "BTS Latest Month", "name": "Latest month", "kind": "text", "size": 20, "hex": t.MUTED}], "BRATISLAVA", t.NAVY, None),
        ("home-kpi-gap", 1356,
         [{"prop": "Rozdiel v trende", "name": "BTS minus VIE", "kind": "pp", "size": 28, "hex": t.GOLD}],
         "GROWTH GAP", t.GOLD, "Difference between the two growth rates, in percentage points (pp)"),
    ):
        n, d = t.kpi_card(lbl, x, 136, 540, 156, 5000, fields, title, col, subtitle=sub); v[n] = d
    n, d = rich_textbox("home-about", 248, 308, 1648, 380, 5100, about, pad=28); v[n] = d
    howto = [
        P("HOW TO READ THE TREND PAGE", 11, t.MUTED, True), GAP,
        P("Year-over-year change (YoY): % change compared with the same month a year earlier.", 16, bullet=True),
        P("Growth gap: Bratislava's growth rate minus Vienna's, in percentage points (pp). Example: +76 % and −7 % is a gap of 83 pp.", 16, bullet=True),
        P("Months an airport did not publish are left blank, never filled in or smoothed.", 16, bullet=True),
    ]
    n, d = rich_textbox("home-how", 248, 704, 1648, 226, 5200, howto, pad=28); v[n] = d
    return v


def source():
    v = frame("src", "Where the numbers come from")
    body = [
        P("SOURCES", 11, t.MUTED, True), GAP,
        LINKP("Vienna Airport: ", "monthly traffic results (investor relations)",
              "https://viennaairport.com/en/company/investor_relations/news/traffic_results_1"),
        GAP,
        LINKP("Bratislava Airport: ", "press releases", "https://www.bts.aero/en/airport/press/latest-news/"),
        GAP,
        LINKP("Bratislava Airport: ", "annual reports", "https://www.bts.aero/en/airport/press/annual-report/"),
        GAP,
        LINKP("OpenSky Network: ", "aircraft movement data", "https://opensky-network.org/"),
        GAP,
        LINKP("Source code and methodology: ", "github.com/KaStihl/vie-bts-tracker", "https://github.com/KaStihl/vie-bts-tracker"),
        GAP, GAP,
        P("DATA NOTES", 11, t.MUTED, True), GAP,
        P("Vienna does not publish a monthly figure for every month, and Bratislava's press releases are free text. A month that cannot be "
          "read reliably is left out rather than guessed.", 15, t.MUTED),
        GAP,
        P("OpenSky movement data started in mid-August 2026 and has gaps. Use it for shares between airlines, not for absolute counts.", 15, t.MUTED),
    ]
    n, d = rich_textbox("src-body", 248, 136, 1648, 500, 5000, body, pad=28); v[n] = d
    return v


def main() -> int:
    write_page(HOME_ID, "Home", home())
    write_page(SRC_ID, "Source", source())
    for old_id, name in ((OLD_HOME, "Home (old design)"), (OLD_SRC, "Source (old design)")):
        path = t.REPORT / "pages" / old_id / "page.json"
        data = t.load(path)
        data["displayName"] = name
        data["visibility"] = "HiddenInViewMode"
        t.dump(path, data)

    pages = t.load(t.REPORT / "pages" / "pages.json")
    first = [HOME_ID, t.NEW_ID, SRC_ID]
    pages["pageOrder"] = first + [p for p in pages["pageOrder"] if p not in first]
    pages["activePageName"] = sys.argv[1] if len(sys.argv) > 1 else HOME_ID
    t.dump(t.REPORT / "pages" / "pages.json", pages)
    print("Home and Source pages written; old ones hidden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
