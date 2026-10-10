"""
Builds the redesigned "Trend" page inside the Power BI project (PBIP) as plain PBIR JSON, and adds
the few DAX measures it needs to the semantic model (TMDL).

    python PBI/tools/build_trend_page.py            # from the repo root; close Desktop first

Why: the old page's whole layout (header, title, logo, washed-out panels, faded airport photo) was a
single 1.4 MB picture used as the page background, so the visuals could only be tweaked, never
restyled. The new page is native: solid page colour, white cards with soft shadows, real text.

The old page is kept (renamed "Trend (old design)" and hidden) so the two can be compared.
Idempotent: re-running replaces the generated page and does not duplicate measures.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PBI = Path(__file__).resolve().parents[1]
REPORT = PBI / "VIE-BTS.Report" / "definition"
MODEL_TABLE = PBI / "VIE-BTS.SemanticModel" / "definition" / "tables" / "Meausre.tmdl"
OLD_ID = "104c7970aaaebc19f569"
NEW_ID = "7e1d5a0c3b9f42a68d10"
OLD = REPORT / "pages" / OLD_ID
NEW = REPORT / "pages" / NEW_ID
SCHEMA_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"

# ---- palette
BG, CARD, NAVY, TEAL, GOLD = "#EEF2F6", "#FFFFFF", "#0F2A4A", "#2CA6A4", "#C9A648"
MUTED, GRID, BORDER, LIGHT_TEAL = "#5B6B7C", "#E3E8EE", "#C9D3DE", "#9FE0DB"
FONT_SEMI = "'''Segoe UI Semibold'', wf_segoe-ui_semibold, helvetica, arial, sans-serif'"
FONT = "'''Segoe UI'', wf_segoe-ui_normal, helvetica, arial, sans-serif'"


# ------------------------------------------------------------------ tiny PBIR helpers
def L(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def S(text: str) -> dict:
    return L("'" + text.replace("'", "''") + "'")


def D(n) -> dict:
    return L(f"{n}D")


def LONG(n) -> dict:
    return L(f"{n}L")


def B(flag: bool) -> dict:
    return L("true" if flag else "false")


def color(hex_: str) -> dict:
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{hex_}'"}}}}}


def measure_color(prop: str) -> dict:
    return {"solid": {"color": {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": "Meausre"}}, "Property": prop}}}}}


def vid(label: str) -> str:
    return hashlib.md5(f"vie-bts-trend-v2:{label}".encode()).hexdigest()[:20]


def measure_ref(prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "Meausre"}}, "Property": prop}}


def series_selector(code: str) -> dict:
    return {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": {"Column": {
        "Expression": {"SourceRef": {"Entity": "public monthly_traffic"}}, "Property": "airport_code"}},
        "Right": {"Literal": {"Value": f"'{code}'"}}}}}]}


def container(title=None, subtitle=None, bg=CARD, radius=12, shadow=True, title_color=NAVY,
              title_size=16, pad=12, title_align="left") -> dict:
    c: dict = {
        "background": [{"properties": {"show": B(bg is not None), "color": color(bg or CARD), "transparency": D(0)}}],
        "border": [{"properties": {"show": B(False), "radius": D(radius)}}],
        "dropShadow": [{"properties": {"show": B(shadow)}}],
        "visualHeader": [{"properties": {"show": B(False)}}],
        "padding": [{"properties": {"left": D(pad), "right": D(pad), "top": D(pad), "bottom": D(pad)}}],
    }
    if title:
        props = {"show": B(True), "titleWrap": B(True), "alignment": S(title_align), "fontSize": D(title_size),
                 "fontFamily": L(FONT_SEMI), "fontColor": color(title_color)}
        props["text"] = title if isinstance(title, dict) else S(title)
        c["title"] = [{"properties": props}]
    else:
        c["title"] = [{"properties": {"show": B(False)}}]
    if subtitle:
        c["subTitle"] = [{"properties": {"show": B(True), "text": S(subtitle), "fontSize": D(11),
                                         "fontColor": color(MUTED), "fontFamily": L(FONT)}}]
    return c


def visual(label, x, y, w, h, z, body: dict, cont: dict | None = None) -> tuple[str, dict]:
    name = vid(label)
    v = dict(body)
    if cont is not None:
        v["visualContainerObjects"] = cont
    v.setdefault("drillFilterOtherVisuals", True)
    return name, {"$schema": SCHEMA_VISUAL, "name": name,
                  "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
                  "visual": v}


def shape(label, x, y, w, h, z, fill, rounded=0, shadow=False):
    tile = "roundedRectangle" if rounded else "rectangle"
    shape_props = {"tileShape": S(tile)}
    if rounded:
        shape_props["roundEdge"] = LONG(rounded)
    body = {"visualType": "shape", "objects": {
        "shape": [{"properties": shape_props}],
        "rotation": [{"properties": {"shapeAngle": LONG(0)}}],
        "fill": [{"properties": {"fillColor": color(fill)}, "selector": {"id": "default"}}],
        "outline": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
    }}
    cont = {"dropShadow": [{"properties": {"show": B(shadow)}}]}
    return visual(label, x, y, w, h, z, body, cont)


def textbox(label, x, y, w, h, z, runs, align="left"):
    """runs: list of (text, size_pt, hex, bold)"""
    paragraphs = []
    for text, size, hex_, bold in runs:
        style = {"fontFamily": "Segoe UI Semibold" if bold else "Segoe UI", "fontSize": f"{size}pt", "color": hex_}
        if bold:
            style["fontWeight"] = "bold"
        paragraphs.append({"textRuns": [{"value": text, "textStyle": style}], "horizontalTextAlignment": align})
    body = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]}}
    return visual(label, x, y, w, h, z, body)


# ------------------------------------------------------------------ KPI cards (new card visual)
def kpi_card(label, x, y, w, h, z, fields, title, title_color, subtitle=None, headline=False):
    """fields: list of dicts {prop, name, kind: 'pax'|'pct'|'pp'|'text', color_measure?}"""
    projections, value_objs, label_objs = [], [], []
    for f in fields:
        projections.append({"field": measure_ref(f["prop"]), "queryRef": f"Meausre.{f['prop']}",
                            "nativeQueryRef": f["name"], "displayName": f["name"]})
        sel = {"metadata": f"Meausre.{f['prop']}"}
        vp = {"fontSize": D(f.get("size", 34)), "fontFamily": L(FONT_SEMI), "horizontalAlignment": S("left"),
              "fontColor": measure_color(f["color_measure"]) if f.get("color_measure") else color(f.get("hex", NAVY))}
        if f["kind"] == "pax":
            vp["labelDisplayUnits"] = D(1000000)
            vp["labelPrecision"] = LONG(2)
        value_objs.append({"properties": vp, "selector": sel})
        label_objs.append({"properties": {"show": B(not headline), "fontSize": D(11), "fontFamily": L(FONT),
                                          "fontColor": color(MUTED), "matchValueAlignment": B(True)}, "selector": sel})
    n = len(fields)
    objects = {
        "layout": [{"properties": {"style": S("Cards"), "columnCount": LONG(n), "rowCount": LONG(1), "autoGrid": B(False),
                                   "orientation": D(0), "calloutSize": D(0), "cellPadding": LONG(3), "showFixedSize": B(False)}},
                   {"properties": {"backgroundShow": B(False), "paddingUniform": LONG(2)}, "selector": {"id": "default"}}],
        "value": value_objs,
        "label": label_objs,
        "outline": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
        "divider": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
        "fillCustom": [{"properties": {"show": B(False)}}],
        "padding": [{"properties": {"paddingUniform": LONG(2)}, "selector": {"id": "default"}}],
        "accentBar": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
        "shadowCustom": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
    }
    body = {"visualType": "cardVisual", "query": {"queryState": {"Data": {"projections": projections}}}, "objects": objects}
    if headline:
        cont = container(None, bg=None, shadow=False, pad=0)
        cont["background"] = [{"properties": {"show": B(False)}}]
    else:
        cont = container(title, subtitle, title_color=title_color, title_size=13, pad=14)
    return visual(label, x, y, w, h, z, body, cont)


# ------------------------------------------------------------------ build
def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clone(old_visual_id: str) -> dict:
    return copy.deepcopy(load(OLD / "visuals" / old_visual_id / "visual.json"))


def place(label, data, x, y, w, h, z, cont=None):
    name = vid(label)
    data["name"] = name
    data["position"] = {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}
    data["$schema"] = SCHEMA_VISUAL
    if cont is not None:
        data["visual"]["visualContainerObjects"] = cont
    return name, data


def style_axis(props: dict, label_size=11):
    props.update({"labelColor": color(MUTED), "fontSize": D(label_size), "fontFamily": L(FONT)})


def build_yoy_chart(x, y, w, h, z):
    d = clone("61074bb9368815e24355")
    o = d["visual"]["objects"]
    o["trend"] = [{"properties": {"show": B(False)}}]                      # dashed linear trend: meaningless here
    for k in ("categoryAxis", "valueAxis"):
        style_axis(o[k][0]["properties"])
    o["categoryAxis"][0]["properties"]["gridlineShow"] = B(False)
    o["valueAxis"][0]["properties"].update({"gridlineShow": B(True), "gridlineColor": color(GRID),
                                           "gridlineStyle": S("dashed"), "gridlineThickness": D(1),
                                           "labelPrecision": LONG(0), "showAxisTitle": B(False)})
    o["layout"] = [{"properties": {"clusteredGapSize": D(55), "clusteredGapOverlaps": B(True)}}]
    # zero line only: no pink "Negative" zone, no overlapping label
    o["y1AxisReferenceLine"] = [{"properties": {
        "show": B(True), "displayName": S("0 %"), "lineColor": color("#8896A6"), "style": S("solid"), "width": D(1),
        "transparency": D(0), "position": S("back"), "shadeShow": B(False), "dataLabelShow": B(False)},
        "selector": {"id": "1"}}]
    ref = o["xAxisReferenceLine"][0]["properties"]
    ref.update({"displayName": S("Wizz Air opens BTS base"), "lineColor": color(GOLD), "style": S("dashed"), "width": D(2),
                "shadeShow": B(False), "dataLabelShow": B(True), "dataLabelColor": color(NAVY), "dataLabelText": S("Name")})
    o["legend"] = [{"properties": {"show": B(True), "position": S("TopRight"), "showTitle": B(False),
                                   "labelColor": color(NAVY), "fontSize": D(12), "fontFamily": L(FONT_SEMI)}}]
    o["dataPoint"] = [
        {"properties": {"fillTransparency": D(0), "borderShow": B(False)}},
        {"properties": {"fill": color(NAVY)}, "selector": series_selector("BTS")},
        {"properties": {"fill": color(TEAL)}, "selector": series_selector("VIE")},
        {"properties": {}, "selector": {"data": [{"roles": ["Series"]}], "hierarchyMatching": 1}},
    ]
    cont = container("Year-over-year growth in passengers",
                     "% change vs the same month last year  ·  Bratislava (navy) vs Vienna (teal)")
    return place("chart-yoy", d, x, y, w, h, z, cont)


def build_total_chart(x, y, w, h, z):
    d = clone("9e083f8b5bcc3aabd310")
    o = d["visual"]["objects"]
    for k in ("categoryAxis", "valueAxis"):
        style_axis(o[k][0]["properties"])
    o["categoryAxis"][0]["properties"]["gridlineShow"] = B(False)
    o["valueAxis"][0]["properties"].update({"gridlineShow": B(True), "gridlineColor": color(GRID), "gridlineStyle": S("dashed"),
                                           "labelDisplayUnits": D(1000000), "labelPrecision": LONG(1), "showAxisTitle": B(False)})
    o["lineStyles"] = [
        {"properties": {"areaShow": B(False), "lineChartType": S("linear"), "showMarker": B(True), "markerSize": D(5),
                        "strokeWidth": D(3), "strokeLineJoin": S("round")}},
        {"properties": {"strokeWidth": D(3), "markerColor": color(NAVY)}, "selector": series_selector("BTS")},
        {"properties": {"strokeWidth": D(3), "markerColor": color(TEAL)}, "selector": series_selector("VIE")},
    ]
    o["dataPoint"] = [
        {"properties": {"fill": color(NAVY)}, "selector": series_selector("BTS")},
        {"properties": {"fill": color(TEAL)}, "selector": series_selector("VIE")},
    ]
    o["legend"] = [{"properties": {"show": B(True), "position": S("TopRight"), "showTitle": B(False),
                                   "labelColor": color(NAVY), "fontSize": D(12), "fontFamily": L(FONT_SEMI)}}]
    o.pop("seriesLabels", None)
    cont = container("Passengers per month", "Monthly passengers handled; markers are the months the airports actually published")
    return place("chart-total", d, x, y, w, h, z, cont)


def build_slicer(src_id, label, title, x, y, w, h, z):
    d = clone(src_id)
    o = d["visual"]["objects"]
    o["dropdown"] = [{"properties": {"borderRadius": LONG(8), "borderColor": color(BORDER), "accentBarShow": B(False),
                                     "iconColor": color(NAVY)}}]
    o["items"] = [{"properties": {"fontColor": color(NAVY), "background": color(CARD), "fontSize": D(11), "fontFamily": L(FONT)}}]
    cont = {
        "background": [{"properties": {"show": B(False)}}],
        "border": [{"properties": {"show": B(False)}}],
        "title": [{"properties": {"show": B(True), "text": S(title), "fontSize": D(12), "fontFamily": L(FONT_SEMI),
                                  "fontColor": color(NAVY), "alignment": S("left"), "titleWrap": B(False)}}],
        "visualHeader": [{"properties": {"show": B(False)}}],
    }
    return place(label, d, x, y, w, h, z, cont)


def build_nav(x, y, w, h, z):
    d = clone("8d1c04f19ed3cad388c0")
    o = d["visual"]["objects"]
    o["text"] = [
        {"properties": {"fontColor": color(NAVY), "fontFamily": L(FONT_SEMI), "fontSize": D(12)}, "selector": {"id": "default"}},
        {"properties": {"fontColor": color(NAVY), "fontFamily": L(FONT_SEMI), "bold": B(True)}, "selector": {"id": "hover"}},
        {"properties": {"fontColor": color(CARD), "fontFamily": L(FONT_SEMI), "bold": B(True)}, "selector": {"id": "selected"}},
    ]
    o["fill"] = [
        {"properties": {"fillColor": color(LIGHT_TEAL)}, "selector": {"id": "press"}},
        {"properties": {"fillColor": color(LIGHT_TEAL)}, "selector": {"id": "hover"}},
        {"properties": {"fillColor": color(NAVY)}, "selector": {"id": "selected"}},
        {"properties": {"fillColor": color("#E6ECF2")}, "selector": {"id": "default"}},
    ]
    o["shape"] = [{"properties": {"roundEdge": LONG(10)}, "selector": {"id": "default"}}]
    return place("nav", d, x, y, w, h, z, {"visualHeader": [{"properties": {"show": B(False)}}]})


def build_clear_button(x, y, w, h, z):
    d = clone("b19ec9ab97ddc0150023")
    o = d["visual"]["objects"]
    o["text"] = [{"properties": {"show": B(True)}},
                 {"properties": {"text": S("Clear filters"), "horizontalAlignment": S("center"), "fontFamily": L(FONT_SEMI),
                                 "fontColor": color(TEAL), "fontSize": D(12), "bold": B(True), "bottomMargin": LONG(0)},
                  "selector": {"id": "default"}}]
    cont = d["visual"]["visualContainerObjects"]
    cont["border"] = [{"properties": {"show": B(True), "color": color(TEAL), "radius": D(10), "width": D(1)}}]
    cont["background"] = [{"properties": {"show": B(True), "color": color(CARD)}}]
    return place("clear", d, x, y, w, h, z, cont)


def build_last_refresh(x, y, w, h, z):
    d = clone("a83d6337a598c580a058")
    o = d["visual"]["objects"]
    o["value"] = [{"properties": {"fontSize": D(12), "fontFamily": L(FONT), "fontColor": color(MUTED),
                                  "horizontalAlignment": S("left")}, "selector": {"id": "default"}}]
    o["label"] = [{"properties": {"show": B(False)}, "selector": {"id": "default"}}]
    o["layout"] = [{"properties": {"style": S("Cards"), "columnCount": LONG(2), "rowCount": LONG(1), "autoGrid": B(False),
                                   "orientation": D(0), "calloutSize": D(0)}},
                   {"properties": {"backgroundShow": B(False)}, "selector": {"id": "default"}}]
    o.pop("cardCalloutArea", None)
    cont = container(None, bg=None, shadow=False, pad=0)
    cont["background"] = [{"properties": {"show": B(False)}}]
    return place("last-refresh", d, x, y, w, h, z, cont)


def write_measures() -> None:
    text = MODEL_TABLE.read_text(encoding="utf-8")
    if "measure Headline" in text:
        print("measures: already present")
        return

    def block(name, expr_lines, fmt=None, doc=None):
        out = ""
        if doc:
            out += f"\t/// {doc}\n"
        out += f"\tmeasure {name} =\n" + "".join(f"\t\t\t{l}\n" for l in expr_lines)
        if fmt:
            out += f"\t\tformatString: {fmt}\n"
        out += "\t\tdisplayFolder: report\n" + f"\t\tlineageTag: {uuid.uuid4()}\n\n"
        return out

    new = "".join([
        block("Headline", [
            'VAR _bts = [BTS Latest YoY]',
            'VAR _vie = [VIE Latest YoY]',
            'RETURN',
            '"Bratislava " & FORMAT(_bts, "+0%;-0%") & "   ·   Vienna " & FORMAT(_vie, "+0.0%;-0.0%") & "   year over year (latest month)"'],
            doc="One-line takeaway shown under the page title."),
        block("'VIE Card Title'", ['"VIENNA   ·   " & [VIE Latest Month]'], doc="Dynamic card title with the month shown."),
        block("'BTS Card Title'", ['"BRATISLAVA   ·   " & [BTS Latest Month]'], doc="Dynamic card title with the month shown."),
        block("'VIE YoY Color'", ['IF([VIE Latest YoY] < 0, "#B85C5C", "#2E8B57")'], doc="Red when Vienna shrinks, green when it grows."),
        block("'BTS YoY Color'", ['IF([BTS Latest YoY] < 0, "#B85C5C", "#2E8B57")'], doc="Red when Bratislava shrinks, green when it grows."),
    ])
    marker = "\t/// Distinct date+hour slots"
    assert marker in text, "insertion marker not found"
    text = text.replace(marker, new + marker, 1)

    # YoY on the cards: sign shown, and falls back to the computed value when no % was published
    for code in ("VIE", "BTS"):
        pattern = re.compile(rf"(measure '{code} Latest YoY' =\n)(.*?)(\t\tformatString: )([^\n]*)(\n)", re.S)
        m = pattern.search(text)
        assert m, f"{code} Latest YoY not found"
        body = (f'\t\t\tVAR _latest = CALCULATE(MAX(\'public monthly_traffic\'[Date]), \'public monthly_traffic\'[airport_code] = "{code}")\n'
                f'\t\t\tRETURN CALCULATE([YoY Change PAX %], \'public monthly_traffic\'[airport_code] = "{code}", \'public monthly_traffic\'[Date] = _latest)\n')
        text = text[:m.start()] + m.group(1) + body + m.group(3) + "+0.0%;-0.0%;0.0%" + m.group(5) + text[m.end():]
    MODEL_TABLE.write_text(text, encoding="utf-8")
    print("measures: added Headline, card titles, YoY colours; Latest YoY now signed + computed fallback")


def main() -> int:
    write_measures()

    if NEW.exists():
        for p in sorted(NEW.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        NEW.rmdir()

    out: dict[str, dict] = {}

    def add(pair):
        out[pair[0]] = pair[1]

    # header band, title, headline, brand
    add(shape("hdr", 0, 0, 1920, 112, 0, NAVY))
    add(textbox("title", 40, 12, 1300, 56, 1000, [("Vienna ⇄ Bratislava Aviation Tracker", 28, "#FFFFFF", True)]))
    add(kpi_card("headline", 40, 66, 1500, 40, 2000, [{"prop": "Headline", "name": "Headline", "kind": "text", "size": 16, "hex": LIGHT_TEAL}],
                 None, NAVY, headline=True))
    add(textbox("brand", 1500, 22, 380, 48, 3000, [("FK's LAB", 26, "#FFFFFF", True)], align="right"))
    add(textbox("brand2", 1500, 68, 380, 30, 3500, [("fkslab.com", 12, LIGHT_TEAL, False)], align="right"))

    # filter rail
    add(shape("rail", 24, 136, 208, 880, 4000, CARD, rounded=12, shadow=True))
    add(textbox("flt", 40, 148, 176, 28, 4100, [("FILTERS", 11, MUTED, True)]))
    add(build_slicer("c67e2fb2476b624d0bbb", "sl-airport", "Airport", 40, 182, 176, 68, 4200))
    add(build_slicer("76109c13ddd8312dd082", "sl-year", "Year", 40, 262, 176, 68, 4300))
    add(build_slicer("e40dc81a94e2d0a35d0b", "sl-month", "Month", 40, 342, 176, 68, 4400))
    add(build_clear_button(40, 426, 176, 40, 4500))
    add(textbox("pg", 40, 500, 176, 28, 4600, [("PAGES", 11, MUTED, True)]))
    add(build_nav(40, 530, 176, 150, 4700))

    # KPI row
    add(kpi_card("kpi-vie", 248, 136, 540, 132, 5000,
                 [{"prop": "VIE Latest Passengers", "name": "Passengers", "kind": "pax", "size": 34, "hex": NAVY},
                  {"prop": "VIE Latest YoY", "name": "vs same month last year", "kind": "pct", "size": 34, "color_measure": "VIE YoY Color"}],
                 {"expr": {"Measure": measure_ref("VIE Card Title")}}, TEAL))
    add(kpi_card("kpi-bts", 802, 136, 540, 132, 5100,
                 [{"prop": "BTS Latest Passengers", "name": "Passengers", "kind": "pax", "size": 34, "hex": NAVY},
                  {"prop": "BTS Latest YoY", "name": "vs same month last year", "kind": "pct", "size": 34, "color_measure": "BTS YoY Color"}],
                 {"expr": {"Measure": measure_ref("BTS Card Title")}}, NAVY))
    add(kpi_card("kpi-gap", 1356, 136, 540, 132, 5200,
                 [{"prop": "Rozdiel v trende", "name": "BTS growth minus VIE growth", "kind": "pp", "size": 34, "hex": GOLD}],
                 "GROWTH GAP", GOLD,
                 subtitle="Difference between the two growth rates, in percentage points (pp)"))

    # charts
    add(build_yoy_chart(248, 284, 880, 596, 6000))
    add(build_total_chart(1142, 284, 754, 596, 6100))

    # story + footer
    story = [("WHAT HAPPENED", 11, MUTED, True),
             ("14 Nov 2025: Wizz Air opens a base in Bratislava.  March 2026: Wizz Air ends its Vienna operations after Austria's aviation tax.  "
              "Since April 2026 Vienna is below last year's passenger numbers, while Bratislava keeps growing at double- and triple-digit rates.",
              13, NAVY, False)]
    name, data = textbox("story", 248, 894, 1648, 92, 7000, story)
    data["visual"]["visualContainerObjects"] = container(None, pad=14)
    out[name] = data
    add(textbox("src", 248, 1006, 1180, 40, 7100,
                [("Sources: Vienna Airport and Bratislava Airport press releases and annual reports · OpenSky Network · code on GitHub: KaStihl/vie-bts-tracker",
                  11, MUTED, False)]))
    add(textbox("lr-label", 1440, 1010, 190, 30, 7200, [("Last refresh (UTC):", 11, MUTED, False)], align="right"))
    add(build_last_refresh(1640, 1004, 256, 40, 7300))

    for name, data in out.items():
        dump(NEW / "visuals" / name / "visual.json", data)

    # page
    page = load(OLD / "page.json")
    page["name"] = NEW_ID
    page["displayName"] = "Trend"
    page["objects"] = {"background": [{"properties": {"color": color(BG), "transparency": D(0)}}]}
    dump(NEW / "page.json", page)

    # old page: keep, hide, rename
    old = load(OLD / "page.json")
    old["displayName"] = "Trend (old design)"
    old["visibility"] = "HiddenInViewMode"
    dump(OLD / "page.json", old)

    pages = load(REPORT / "pages" / "pages.json")
    order = [p for p in pages["pageOrder"] if p != NEW_ID]
    order.insert(1, NEW_ID)
    pages["pageOrder"] = order
    pages["activePageName"] = NEW_ID
    dump(REPORT / "pages" / "pages.json", pages)
    print(f"page '{NEW_ID}' written with {len(out)} visuals; old trend page hidden")
    return 0


if __name__ == "__main__":
    sys.exit(main())
