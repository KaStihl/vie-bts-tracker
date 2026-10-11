"""
Builds the report pages (Home, Trend, Source) as native PBIR JSON in the Power BI project, plus the DAX
measures they need and the background pictures.

    pip install pillow
    python PBI/tools/build_report.py [page-id-to-open-first]      # close Desktop first

Design rules (from the dataviz / design-critique / accessibility checks):
  * dark "glass" cards on a generated route-network background (tools/make_backgrounds.py), brand logo in the header
  * series colours validated with the dataviz palette validator on the card surface (dark mode):
        Bratislava #2CA6A4 (brand teal)   Vienna #BC862B (brand gold, darkened to pass the lightness band)
    -> CVD distance 15, normal-vision distance 19, contrast >= 3:1
  * text never wears a series colour (a thin accent bar above each card carries identity)
  * text contrast on the card (#0F2742): white 15:1, soft 10:1, muted 6.9:1, green 8.6:1, red 6.0:1  (WCAG AA)
  * KPI cards show the latest month, the year-over-year change AND the previous release with its change
  * charts have alt text; legends present; recessive dashed grid; no dual axes, no trend line, linear axis

Findings from loading in Desktop that this script respects:
  * a visual title bound to a measure breaks report loading -> titles are static, dynamic values are callouts
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

PBI = Path(__file__).resolve().parents[1]
REPORT = PBI / "VIE-BTS.Report" / "definition"
RESOURCES = PBI / "VIE-BTS.Report" / "StaticResources" / "RegisteredResources"
MODEL_TABLE = PBI / "VIE-BTS.SemanticModel" / "definition" / "tables" / "_Measures.tmdl"
OLD_TREND = REPORT / "pages" / "104c7970aaaebc19f569"          # source of the cloned slicers / nav / button / charts
HOME_ID, TREND_ID, SRC_ID = "3a9c61d2e8b74f05a1c7", "7e1d5a0c3b9f42a68d10", "b5f20e7a4d9c43168e3a"
SCHEMA_VISUAL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"

# ---- palette (all validated, see module docstring)
CARD, BORDER, BOX, BOX_BORDER = "#0F2742", "#26496F", "#14335A", "#2F5683"
WHITE, SOFT, MUTED, GRID = "#FFFFFF", "#C9D6E3", "#9DB2C8", "#2A4A6B"
BTS, VIE = "#2CA6A4", "#BC862B"
POS, NEG, ACCENT = "#3DDC97", "#FF7B7B", "#8FE3DC"
FONT_SEMI = "'''Segoe UI Semibold'', wf_segoe-ui_semibold, helvetica, arial, sans-serif'"
FONT = "'''Segoe UI'', wf_segoe-ui_normal, helvetica, arial, sans-serif'"
GLASS = 14   # card transparency in %


# ------------------------------------------------------------------ PBIR helpers
def L(v): return {"expr": {"Literal": {"Value": v}}}
def S(text): return L("'" + text.replace("'", "''") + "'")
def D(n): return L(f"{n}D")
def LONG(n): return L(f"{n}L")
def B(flag): return L("true" if flag else "false")
def color(h): return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{h}'"}}}}}
def measure_ref(prop): return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": prop}}
def measure_color(prop): return {"solid": {"color": {"expr": measure_ref(prop)}}}
def vid(label): return hashlib.md5(f"vie-bts-v3:{label}".encode()).hexdigest()[:20]


def series_selector(code):
    return {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": {"Column": {
        "Expression": {"SourceRef": {"Entity": "public monthly_traffic"}}, "Property": "airport_code"}},
        "Right": {"Literal": {"Value": f"'{code}'"}}}}}]}


def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def container(title=None, subtitle=None, bg=True, border=True, pad=14, alt=None, title_size=14):
    c = {
        "background": [{"properties": {"show": B(bg), "color": color(CARD), "transparency": D(GLASS)}}],
        "border": [{"properties": {"show": B(border), "color": color(BORDER), "radius": D(14), "width": D(1)}}],
        "dropShadow": [{"properties": {"show": B(False)}}],
        "visualHeader": [{"properties": {"show": B(False)}}],
        "padding": [{"properties": {"left": D(pad), "right": D(pad), "top": D(pad), "bottom": D(pad)}}],
    }
    if title:
        c["title"] = [{"properties": {"show": B(True), "text": S(title), "titleWrap": B(True), "alignment": S("left"),
                                      "fontSize": D(title_size), "fontFamily": L(FONT_SEMI), "fontColor": color(WHITE)}}]
    else:
        c["title"] = [{"properties": {"show": B(False)}}]
    if subtitle:
        c["subTitle"] = [{"properties": {"show": B(True), "text": S(subtitle), "fontSize": D(11),
                                         "fontColor": color(MUTED), "fontFamily": L(FONT)}}]
    if alt:
        c["general"] = [{"properties": {"altText": S(alt)}}]
    return c


def visual(label, x, y, w, h, z, body, cont=None):
    name = vid(label)
    v = dict(body)
    if cont is not None:
        v["visualContainerObjects"] = cont
    v.setdefault("drillFilterOtherVisuals", True)
    return name, {"$schema": SCHEMA_VISUAL, "name": name,
                  "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": v}


def shape(label, x, y, w, h, z, fill, rounded=0, border=None):
    """Solid-fill shape. (Fill transparency and a shape outline made the shape disappear in Desktop; the card
    border is drawn by the visual container instead, like on charts and cards.)"""
    props = {"tileShape": S("roundedRectangle" if rounded else "rectangle")}
    if rounded:
        props["roundEdge"] = LONG(rounded)
    body = {"visualType": "shape", "objects": {
        "shape": [{"properties": props}], "rotation": [{"properties": {"shapeAngle": LONG(0)}}],
        "fill": [{"properties": {"fillColor": color(fill)}, "selector": {"id": "default"}}],
        "outline": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}]}}
    cont = {"dropShadow": [{"properties": {"show": B(False)}}]}
    if border:
        cont["border"] = [{"properties": {"show": B(True), "color": color(border), "radius": D(14), "width": D(1)}}]
    return visual(label, x, y, w, h, z, body, cont)


def glass(label, x, y, w, h, z):
    return shape(label, x, y, w, h, z, "#0E2540", rounded=14, border=BORDER)


def accent(label, x, y, w, z, hex_):
    return shape(label, x + 16, y, w - 32, 4, z, hex_)


def rich_textbox(label, x, y, w, h, z, paras, align="left"):
    """paras: [{runs:[(text,size,hex,bold[,url])], bullet:bool}]"""
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
        para = {"textRuns": runs, "horizontalTextAlignment": p.get("align", align)}
        if p.get("bullet"):
            para.update({"listType": "bullet", "indent": 1})
        paragraphs.append(para)
    body = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]}}
    return visual(label, x, y, w, h, z, body)


def textbox(label, x, y, w, h, z, runs, align="left"):
    return rich_textbox(label, x, y, w, h, z, [{"runs": [r]} for r in runs], align)


def P(text, size=15, hex_=SOFT, bold=False, bullet=False, url=None):
    return {"runs": [(text, size, hex_, bold, url)], "bullet": bullet}


GAP = P(" ", 5)


# ------------------------------------------------------------------ KPI card (new card visual)
def kpi_card(label, x, y, w, h, z, fields, title, subtitle=None, cols=3, rows=2, alt=None):
    projections, value_objs, label_objs = [], [], []
    for f in fields:
        projections.append({"field": measure_ref(f["prop"]), "queryRef": f"_Measures.{f['prop']}",
                            "nativeQueryRef": f["name"], "displayName": f["name"]})
        sel = {"metadata": f"_Measures.{f['prop']}"}
        vp = {"fontSize": D(f.get("size", 32)), "fontFamily": L(FONT_SEMI), "horizontalAlignment": S(f.get("align", "left")),
              "fontColor": measure_color(f["color_measure"]) if f.get("color_measure") else color(f.get("hex", WHITE))}
        if f["kind"] == "pax":
            vp["labelDisplayUnits"] = D(1000000)
            vp["labelPrecision"] = LONG(2)
        value_objs.append({"properties": vp, "selector": sel})
        label_objs.append({"properties": {"show": B(not f.get("nolabel")), "fontSize": D(11), "fontFamily": L(FONT),
                                          "fontColor": color(MUTED), "matchValueAlignment": B(True)}, "selector": sel})
    objects = {
        "layout": [{"properties": {"style": S("Cards"), "columnCount": LONG(cols), "rowCount": LONG(rows), "autoGrid": B(False),
                                   "orientation": D(0), "calloutSize": D(0), "cellPadding": LONG(3), "showFixedSize": B(False)}},
                   {"properties": {"backgroundShow": B(False), "paddingUniform": LONG(2)}, "selector": {"id": "default"}}],
        "value": value_objs, "label": label_objs,
        "outline": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
        "divider": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
        "fillCustom": [{"properties": {"show": B(False)}}],
        "padding": [{"properties": {"paddingUniform": LONG(2)}, "selector": {"id": "default"}}],
        "accentBar": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
        "shadowCustom": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
    }
    body = {"visualType": "cardVisual", "query": {"queryState": {"Data": {"projections": projections}}}, "objects": objects}
    return visual(label, x, y, w, h, z, body, container(title, subtitle, pad=16, alt=alt, title_size=13))


def text_card(label, x, y, w, h, z, prop, size, hex_, align="left"):
    """A single text measure with no card chrome (headline under the title, refresh stamp in the footer)."""
    body = {"visualType": "cardVisual", "query": {"queryState": {"Data": {"projections": [
        {"field": measure_ref(prop), "queryRef": f"_Measures.{prop}", "nativeQueryRef": prop, "displayName": prop}]}}},
        "objects": {
            "layout": [{"properties": {"style": S("Cards"), "columnCount": LONG(1), "rowCount": LONG(1), "autoGrid": B(False),
                                       "orientation": D(0), "calloutSize": D(0)}},
                       {"properties": {"backgroundShow": B(False), "paddingUniform": LONG(0)}, "selector": {"id": "default"}}],
            "value": [{"properties": {"fontSize": D(size), "fontFamily": L(FONT_SEMI if size > 13 else FONT),
                                      "horizontalAlignment": S(align), "fontColor": color(hex_)}, "selector": {"id": "default"}}],
            "label": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
            "outline": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
            "divider": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
            "fillCustom": [{"properties": {"show": B(False)}}],
            "padding": [{"properties": {"paddingUniform": LONG(0)}, "selector": {"id": "default"}}],
            "accentBar": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}],
            "shadowCustom": [{"properties": {"show": B(False)}, "selector": {"id": "default"}}]}}
    cont = container(None, bg=False, border=False, pad=0)
    return visual(label, x, y, w, h, z, body, cont)


# ------------------------------------------------------------------ cloned, restyled visuals
def clone(old_id):
    return copy.deepcopy(load(OLD_TREND / "visuals" / old_id / "visual.json"))


def place(label, data, x, y, w, h, z, cont=None):
    data["name"] = vid(label)
    data["position"] = {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}
    data["$schema"] = SCHEMA_VISUAL
    if cont is not None:
        data["visual"]["visualContainerObjects"] = cont
    return data["name"], data


def axis(props):
    props.update({"labelColor": color(MUTED), "fontSize": D(11), "fontFamily": L(FONT)})


def legend():
    return [{"properties": {"show": B(True), "position": S("TopRight"), "showTitle": B(False),
                            "labelColor": color(WHITE), "fontSize": D(12), "fontFamily": L(FONT_SEMI)}}]


def yoy_chart(code, name, hex_, x, y, w, h, z, first):
    """One year-over-year chart per airport. Separate charts = separate axes (Vienna's -8 % stays readable next to
    Bratislava's +150 %); growth and decline are two measures so the decline can be red (a chart with a legend
    field, or a measure-driven fill, is not recoloured by Desktop)."""
    d = clone("61074bb9368815e24355")
    d["visual"]["visualType"] = "lineStackedColumnComboChart"
    o = d["visual"]["objects"]
    o["trend"] = [{"properties": {"show": B(False)}}]
    for k in ("categoryAxis", "valueAxis"):
        axis(o[k][0]["properties"])
    o["categoryAxis"][0]["properties"]["gridlineShow"] = B(False)
    o["categoryAxis"][0]["properties"]["show"] = B(not first)          # dates only under the lower chart
    o["valueAxis"][0]["properties"].update({"gridlineShow": B(True), "gridlineColor": color(GRID), "gridlineStyle": S("dashed"),
                                           "gridlineThickness": D(1), "labelPrecision": LONG(0), "showAxisTitle": B(False)})
    o["layout"] = [{"properties": {"clusteredGapSize": D(40)}}]
    o["y1AxisReferenceLine"] = [{"properties": {"show": B(True), "displayName": S("0 %"), "lineColor": color("#6F89A6"),
                                                "style": S("solid"), "width": D(1), "transparency": D(0), "position": S("back"),
                                                "shadeShow": B(False), "dataLabelShow": B(False)}, "selector": {"id": "1"}}]
    ref = o["xAxisReferenceLine"][0]["properties"]
    ref.update({"displayName": S("Wizz Air opens BTS base"), "lineColor": color(SOFT), "style": S("dashed"), "width": D(2),
                "shadeShow": B(False), "dataLabelShow": B(first), "dataLabelColor": color(WHITE), "dataLabelText": S("Name")})
    o["legend"] = [{"properties": {"show": B(False)}}]
    qs = d["visual"]["query"]
    qs["queryState"].pop("Series", None)
    qs.pop("sortDefinition", None)
    qs["queryState"]["Y"]["projections"] = [
        {"field": measure_ref(f"{code} YoY Up"), "queryRef": f"_Measures.{code} YoY Up", "nativeQueryRef": "Growth", "displayName": "Growth"},
        {"field": measure_ref(f"{code} YoY Down"), "queryRef": f"_Measures.{code} YoY Down", "nativeQueryRef": "Decline", "displayName": "Decline"}]
    o["dataPoint"] = [{"properties": {"fillTransparency": D(0), "borderShow": B(False)}},
                      {"properties": {"fill": color(hex_)}, "selector": {"metadata": f"_Measures.{code} YoY Up"}},
                      {"properties": {"fill": color(NEG)}, "selector": {"metadata": f"_Measures.{code} YoY Down"}}]
    title = f"{name}: year-over-year growth"
    sub = ("% change vs the same month last year  ·  red = decline  ·  dashed line: Wizz Air opens its Bratislava base" if first
           else "% change vs the same month last year  ·  red = decline")
    cont = container(title, sub, pad=14, title_size=15,
                     alt=f"Column chart: year-over-year change in monthly passengers at {name} since January 2024; declines are red.")
    return place(f"chart-yoy-{code}", d, x, y, w, h, z, cont)


def total_chart(x, y, w, h, z):
    d = clone("9e083f8b5bcc3aabd310")
    o = d["visual"]["objects"]
    for k in ("categoryAxis", "valueAxis"):
        axis(o[k][0]["properties"])
    o["categoryAxis"][0]["properties"]["gridlineShow"] = B(False)
    o["valueAxis"][0]["properties"].update({"gridlineShow": B(True), "gridlineColor": color(GRID), "gridlineStyle": S("dashed"),
                                           "labelDisplayUnits": D(1000000), "labelPrecision": LONG(1), "showAxisTitle": B(False),
                                           "logAxisScale": B(False)})
    o["lineStyles"] = [
        {"properties": {"areaShow": B(False), "lineChartType": S("linear"), "showMarker": B(True), "markerSize": D(7),
                        "strokeWidth": D(2), "strokeLineJoin": S("round")}},
        {"properties": {"strokeWidth": D(2), "markerColor": color(BTS)}, "selector": series_selector("BTS")},
        {"properties": {"strokeWidth": D(2), "markerColor": color(VIE)}, "selector": series_selector("VIE")}]
    o["dataPoint"] = [{"properties": {"fill": color(BTS)}, "selector": series_selector("BTS")},
                      {"properties": {"fill": color(VIE)}, "selector": series_selector("VIE")}]
    o["legend"] = legend()
    o.pop("seriesLabels", None)
    cont = container("Passengers per month", "Each marker is a month with data (airport release, else Eurostat)  ·  linear scale", pad=16, title_size=16,
                     alt="Line chart: monthly passengers at Vienna (about 2 to 3 million) and Bratislava (0.1 to 0.6 million) since January 2024.")
    return place("chart-total", d, x, y, w, h, z, cont)


def slicer(src_id, label, title, x, y, w, h, z):
    d = clone(src_id)
    o = d["visual"]["objects"]
    o["dropdown"] = [{"properties": {"borderRadius": LONG(8), "borderColor": color(BOX_BORDER), "accentBarShow": B(False), "iconColor": color(WHITE)}}]
    o["items"] = [{"properties": {"fontColor": color(WHITE), "background": color(BOX), "fontSize": D(11), "fontFamily": L(FONT)}}]
    cont = {"background": [{"properties": {"show": B(False)}}], "border": [{"properties": {"show": B(False)}}],
            "title": [{"properties": {"show": B(True), "text": S(title), "fontSize": D(12), "fontFamily": L(FONT_SEMI),
                                      "fontColor": color(WHITE), "alignment": S("left"), "titleWrap": B(False)}}],
            "visualHeader": [{"properties": {"show": B(False)}}]}
    return place(label, d, x, y, w, h, z, cont)


def nav(label, x, y, w, h, z):
    d = clone("8d1c04f19ed3cad388c0")
    o = d["visual"]["objects"]
    o["text"] = [{"properties": {"fontColor": color(WHITE), "fontFamily": L(FONT_SEMI), "fontSize": D(12)}, "selector": {"id": "default"}},
                 {"properties": {"fontColor": color(WHITE), "fontFamily": L(FONT_SEMI), "bold": B(True)}, "selector": {"id": "hover"}},
                 {"properties": {"fontColor": color("#06203A"), "fontFamily": L(FONT_SEMI), "bold": B(True)}, "selector": {"id": "selected"}}]
    o["fill"] = [{"properties": {"fillColor": color("#1D4A78")}, "selector": {"id": "press"}},
                 {"properties": {"fillColor": color("#1D4A78")}, "selector": {"id": "hover"}},
                 {"properties": {"fillColor": color(BTS)}, "selector": {"id": "selected"}},
                 {"properties": {"fillColor": color(BOX)}, "selector": {"id": "default"}}]
    o["shape"] = [{"properties": {"roundEdge": LONG(10)}, "selector": {"id": "default"}}]
    return place(label, d, x, y, w, h, z, {"visualHeader": [{"properties": {"show": B(False)}}]})


def clear_button(label, x, y, w, h, z):
    d = clone("b19ec9ab97ddc0150023")
    o = d["visual"]["objects"]
    o["text"] = [{"properties": {"show": B(True)}},
                 {"properties": {"text": S("Clear filters"), "horizontalAlignment": S("center"), "fontFamily": L(FONT_SEMI),
                                 "fontColor": color(ACCENT), "fontSize": D(12), "bold": B(True), "bottomMargin": LONG(0)},
                  "selector": {"id": "default"}}]
    cont = d["visual"]["visualContainerObjects"]
    cont["border"] = [{"properties": {"show": B(True), "color": color(BTS), "radius": D(10), "width": D(1)}}]
    cont["background"] = [{"properties": {"show": B(False)}}]
    return place(label, d, x, y, w, h, z, cont)


# ------------------------------------------------------------------ shared page parts
def header(prefix, subtitle=None, headline=False):
    out = {}

    def add(pair): out[pair[0]] = pair[1]

    add(textbox(f"{prefix}-title", 40, 8, 1300, 66, 1000, [("Vienna ⇄ Bratislava Aviation Tracker", 30, WHITE, True)]))
    if headline:
        add(text_card(f"{prefix}-headline", 40, 68, 1500, 34, 2000, "Headline", 16, ACCENT))
    else:
        add(textbox(f"{prefix}-sub", 40, 66, 1500, 38, 2000, [(subtitle, 16, ACCENT, False)]))
    return out


def rail(prefix, with_filters):
    out = {}

    def add(pair): out[pair[0]] = pair[1]

    add(glass(f"{prefix}-rail", 24, 124, 200, 854, 4000))
    if with_filters:
        add(textbox(f"{prefix}-flt", 40, 134, 168, 36, 4100, [("FILTERS", 11, MUTED, True)]))
        add(slicer("c67e2fb2476b624d0bbb", f"{prefix}-sl1", "Airport", 40, 172, 168, 68, 4200))
        add(slicer("76109c13ddd8312dd082", f"{prefix}-sl2", "Year", 40, 252, 168, 68, 4300))
        add(slicer("e40dc81a94e2d0a35d0b", f"{prefix}-sl3", "Month", 40, 332, 168, 68, 4400))
        add(clear_button(f"{prefix}-clr", 40, 416, 168, 40, 4500))
        add(textbox(f"{prefix}-pg", 40, 482, 168, 36, 4600, [("PAGES", 11, MUTED, True)]))
        add(nav(f"{prefix}-nav", 40, 518, 168, 130, 4700))
    else:
        add(textbox(f"{prefix}-pg", 40, 134, 168, 36, 4600, [("PAGES", 11, MUTED, True)]))
        add(nav(f"{prefix}-nav", 40, 172, 168, 130, 4700))
    return out


def footer(prefix):
    out = {}

    def add(pair): out[pair[0]] = pair[1]

    add(textbox(f"{prefix}-src", 240, 1006, 1250, 44, 7100,
                [("Sources: Vienna Airport and Bratislava Airport press releases and annual reports · Eurostat · OpenSky Network · open source: github.com/KaStihl/vie-bts-tracker",
                  11, MUTED, False)]))
    add(text_card(f"{prefix}-refresh", 1500, 1006, 396, 36, 7200, "Refresh Label", 12, MUTED, align="right"))
    return out


# ------------------------------------------------------------------ pages
def trend():
    v = {}

    def add(pair): v[pair[0]] = pair[1]

    v.update(header("t", headline=True))
    v.update(rail("t", True))

    def airport_fields(code):
        return [{"prop": f"{code} Latest Passengers", "name": "Passengers", "kind": "pax", "size": 32, "hex": WHITE},
                {"prop": f"{code} Latest YoY", "name": "vs same month last year", "kind": "pct", "size": 32, "color_measure": f"{code} YoY Color"},
                {"prop": f"{code} Latest Month", "name": "Latest month", "kind": "text", "size": 20, "hex": SOFT},
                {"prop": f"{code} Prev Passengers", "name": "Previous release", "kind": "pax", "size": 22, "hex": SOFT},
                {"prop": f"{code} MoM", "name": "Change vs previous release", "kind": "pct", "size": 22, "color_measure": f"{code} MoM Color"},
                {"prop": f"{code} Prev Month", "name": "Previous month", "kind": "text", "size": 16, "hex": MUTED}]

    add(accent("t-bar-vie", 240, 124, 592, 5150, VIE))
    add(kpi_card("t-kpi-vie", 240, 124, 592, 244, 5100, airport_fields("VIE"), "VIENNA",
                 alt="Vienna Airport: passengers in the latest month, change versus the same month last year and versus the previous release."))
    add(accent("t-bar-bts", 844, 124, 592, 5350, BTS))
    add(kpi_card("t-kpi-bts", 844, 124, 592, 244, 5300, airport_fields("BTS"), "BRATISLAVA",
                 alt="Bratislava Airport: passengers in the latest month, change versus the same month last year and versus the previous release."))
    add(accent("t-bar-gap", 1448, 124, 448, 5550, MUTED))
    add(kpi_card("t-kpi-gap", 1448, 124, 448, 244, 5500,
                 [{"prop": "Rozdiel v trende", "name": "Growth gap", "kind": "pp", "size": 30, "hex": WHITE},
                  {"prop": "Size Ratio", "name": "Size of Vienna vs Bratislava", "kind": "text", "size": 20, "hex": SOFT}],
                 "GROWTH GAP", subtitle="BTS minus VIE growth, in percentage points (pp)", cols=1, rows=2,
                 alt="Growth gap between Bratislava and Vienna in percentage points, and how many times larger Vienna is."))
    add(yoy_chart("BTS", "Bratislava", BTS, 240, 382, 900, 244, 6000, True))
    add(yoy_chart("VIE", "Vienna", VIE, 240, 634, 900, 240, 6050, False))
    add(total_chart(1152, 382, 744, 492, 6100))

    # timeline strip
    add(glass("t-story", 240, 886, 1656, 96, 7000))
    cols = [(262, "14 NOV 2025", "Wizz Air opens a base in Bratislava."),
            (822, "MARCH 2026", "Wizz Air ends its Vienna operations after Austria's aviation tax."),
            (1382, "SINCE APRIL 2026", "Vienna runs below last year's passenger numbers; Bratislava keeps growing at double- and triple-digit rates.")]
    for i, (x, date, text) in enumerate(cols):
        add(shape(f"t-dot{i}", x, 902, 4, 66, 7050, SOFT))
        add(rich_textbox(f"t-ms{i}", x + 20, 898, 500, 80, 7060,
                         [P(date, 11, WHITE, True), P(text, 13, SOFT)]))
    v.update(footer("t"))
    return v


def home():
    v = {}

    def add(pair): v[pair[0]] = pair[1]

    v.update(header("h", subtitle="Monthly passenger traffic  ·  Air route intelligence"))
    v.update(rail("h", False))
    # hero
    add(glass("h-hero", 240, 124, 1656, 230, 5000))
    add(rich_textbox("h-hero-t", 272, 138, 1590, 206, 5100, [
        P("WHO IS WINNING THE PASSENGERS?", 11, MUTED, True),
        P("Vienna vs Bratislava after Austria's aviation tax", 34, WHITE, True),
        GAP,
        P("This dashboard tracks how low-cost carrier capacity has shifted between Vienna (VIE) and Bratislava (BTS) airports, following "
          "Austria's aviation tax and Wizz Air's exit from Vienna in March 2026.", 16, SOFT),
        GAP,
        P("It is also a public case study in BI and data engineering: official sources, verified data and a transparent methodology.", 14, MUTED)]))
    # three tiles
    tiles = [(240, "WHAT IT SHOWS", [P("Monthly passengers at both airports, year-over-year growth and the gap between them, from official sources. Eurostat fills months an airport did not publish.", 15, SOFT)]),
             (798, "HOW TO READ IT", [P("YoY: change versus the same month a year earlier.", 13, SOFT, bullet=True),
                                      P("pp (percentage points): difference between two growth rates, e.g. +76 % and −7 % is 83 pp.", 13, SOFT, bullet=True),
                                      P("A month tagged Eurostat was not published by the airport; its growth is computed within Eurostat.", 13, SOFT, bullet=True)]),
             (1356, "DATA QUALITY", [P("Collected automatically and checked by hand where the sources are less structured. Airline-level flight data "
                                       "(OpenSky) is still short and incomplete, so it is not shown yet.", 15, SOFT)])]
    for i, (x, head, body) in enumerate(tiles):
        add(glass(f"h-tile{i}", x, 368, 540, 196, 5200))
        add(rich_textbox(f"h-tile{i}-t", x + 22, 378, 496, 180, 5300, [P(head, 11, MUTED, True), GAP] + body))
    # pipeline
    add(glass("h-pipe", 240, 578, 1656, 400, 5400))
    add(textbox("h-pipe-h", 272, 590, 700, 34, 5500, [("HOW IT WORKS", 11, MUTED, True)]))
    boxes = [(272, "Official sources", "Airport press releases, annual reports, Eurostat and OpenSky flight data"),
             (698, "Automated scrapers", "Python jobs on GitHub Actions: hourly, daily and weekly"),
             (1124, "Supabase", "Postgres database with read-only public access"),
             (1550, "Power BI", "This report, refreshed from the database")]
    for i, (x, head, body) in enumerate(boxes):
        add(shape(f"h-box{i}", x, 650, 330, 190, 5600, BOX, rounded=14, border=BOX_BORDER))
        add(rich_textbox(f"h-box{i}-t", x + 18, 666, 294, 160, 5700, [P(head, 18, WHITE, True), GAP, P(body, 13, SOFT)]))
    add(textbox("h-pipe-f", 272, 872, 1560, 60, 5800,
                [("The whole pipeline is open source and runs without a server of its own: github.com/KaStihl/vie-bts-tracker", 13, MUTED, False)]))
    v.update(footer("h"))
    return v


def source():
    v = {}

    def add(pair): v[pair[0]] = pair[1]

    v.update(header("s", subtitle="Where the numbers come from"))
    v.update(rail("s", False))
    cards = [
        ("MONTHLY  ·  OFFICIAL", "Vienna Airport", "Traffic results by Flughafen Wien AG investor relations: passengers for the Group and for Vienna Airport.",
         "viennaairport.com › investor relations › traffic results", "https://viennaairport.com/en/company/investor_relations/news/traffic_results_1"),
        ("MONTHLY  ·  OFFICIAL", "Bratislava Airport: press releases", "Free-text monthly releases. Figures are extracted automatically and checked.",
         "bts.aero › press › latest news", "https://www.bts.aero/en/airport/press/latest-news/"),
        ("YEARLY  ·  OFFICIAL", "Bratislava Airport: annual reports", "Monthly passengers for 2019–2024 from the annual report tables.",
         "bts.aero › press › annual reports", "https://www.bts.aero/en/airport/press/annual-report/"),
        ("FLIGHT DATA", "OpenSky Network", "Aircraft movements at LOWW and LZIB by airline callsign. Collection started in mid-August 2026.",
         "opensky-network.org", "https://opensky-network.org/"),
        ("OPEN SOURCE", "Code and methodology", "The whole pipeline is public: scrapers, schedules, database schema and this report.",
         "github.com/KaStihl/vie-bts-tracker", "https://github.com/KaStihl/vie-bts-tracker"),
        ("MONTHLY  ·  GAP FILLER", "Eurostat", "Fills months an airport did not publish. Bratislava matches the airport's count; Vienna is 1–3 % higher.",
         "ec.europa.eu › eurostat › avia_paoa", "https://ec.europa.eu/eurostat/databrowser/view/avia_paoa/"),
    ]
    for i, (kind, name, desc, link, url) in enumerate(cards):
        x, y = 240 + (i % 3) * 558, 124 + (i // 3) * 244
        add(glass(f"s-c{i}", x, y, 540, 230, 5000))
        paras = [P(kind, 11, MUTED, True), GAP, P(name, 19, WHITE, True), GAP, P(desc, 13, SOFT)]
        if link:
            paras += [GAP, P(link, 13, ACCENT, False, url=url)]
        add(rich_textbox(f"s-c{i}-t", x + 22, y + 14, 496, 204, 5100, paras))
    add(glass("s-notes", 240, 612, 1656, 310, 5200))
    add(rich_textbox("s-notes-t", 262, 626, 1612, 284, 5300, [
        P("DATA NOTES", 11, MUTED, True), GAP,
        P("Vienna skips several months a year and Bratislava's press releases are free text. Months an airport did not publish are filled from Eurostat and tagged as such; a month nobody published is left out, never guessed.", 15, SOFT, bullet=True),
        GAP,
        P("Year-over-year change uses the percentage the airport published; where it gave none (and for Eurostat months) it is computed from the same month a year earlier in the same source.", 15, SOFT, bullet=True),
        GAP,
        P("OpenSky movement data started in mid-August 2026 and has gaps: use it for shares between airlines, not for absolute counts.", 15, SOFT, bullet=True),
        GAP,
        P("The data belongs to the original publishers (airports, Eurostat, OpenSky). Check their terms before reusing it.", 15, SOFT, bullet=True)]))
    v.update(footer("s"))
    return v


# ------------------------------------------------------------------ model: measures
MEASURES = {
    "Headline": (["VAR _bts = [BTS Latest YoY]", "VAR _vie = [VIE Latest YoY]", "RETURN",
                  '"Bratislava " & FORMAT(_bts, "+0%;-0%") & "   ·   Vienna " & FORMAT(_vie, "+0.0%;-0.0%") & "   year over year (latest month)"'],
                 None, "One-line takeaway under the page title."),
    "Refresh Label": (["\"Last refresh (UTC):  \" & FORMAT(MAX('Query'[Column1]), \"d mmm yyyy  ·  HH:mm\")"], None,
                      "Footer stamp: when the model was last refreshed, in one piece."),
    "Size Ratio": (['"Vienna is " & FORMAT(DIVIDE([VIE Latest Passengers], [BTS Latest Passengers]), "0.0") & "x larger"'], None,
                   "How many times larger Vienna is than Bratislava in the latest month."),
}
for _code, _name, _col in (("VIE", "Vienna", VIE), ("BTS", "Bratislava", BTS)):
    MEASURES[f"{_code} YoY"] = ([f"CALCULATE([YoY Change PAX %], KEEPFILTERS('public monthly_traffic'[airport_code] = \"{_code}\"))"],
                                "0.00%;-0.00%;0.00%", f"{_name}: year-over-year change per month, still filtered by the Airport slicer (one measure per airport so each can be coloured by sign).")
    MEASURES[f"{_code} YoY Up"] = ([f'VAR _v = [{_code} YoY]', 'RETURN IF(_v >= 0, _v)'], "0.00%;-0.00%;0.00%",
                                   f"{_name}: the growth months (blank otherwise), so growth and decline can be coloured differently.")
    MEASURES[f"{_code} YoY Down"] = ([f'VAR _v = [{_code} YoY]', 'RETURN IF(_v < 0, _v)'], "0.00%;-0.00%;0.00%",
                                     f"{_name}: the decline months (blank otherwise).")
    _prev = (f'VAR _l = CALCULATE(MAX(\'public monthly_traffic\'[Date]), \'public monthly_traffic\'[airport_code] = "{_code}")\n'
             f'VAR _p = CALCULATE(MAX(\'public monthly_traffic\'[Date]), \'public monthly_traffic\'[airport_code] = "{_code}", \'public monthly_traffic\'[Date] < _l)')
    MEASURES[f"{_code} Prev Passengers"] = (_prev.split("\n") + [
        f'RETURN CALCULATE(SUM(\'public monthly_traffic\'[passengers]), \'public monthly_traffic\'[airport_code] = "{_code}", \'public monthly_traffic\'[Date] = _p)'],
        "0", f"{_name}: passengers in the previous release (the newest month before the latest one that was published).")
    MEASURES[f"{_code} Prev Month"] = (_prev.split("\n") + ['RETURN FORMAT(_p, "mmm yyyy")'], None, f"{_name}: month of the previous release.")
    MEASURES[f"{_code} MoM"] = ([f"DIVIDE([{_code} Latest Passengers] - [{_code} Prev Passengers], [{_code} Prev Passengers])"],
                                "+0.0%;-0.0%;0.0%", f"{_name}: change versus the previous release.")
    MEASURES[f"{_code} MoM Color"] = ([f'IF([{_code} MoM] < 0, "{NEG}", "{POS}")'], None, "Red when down, green when up (text colour, AA contrast on the card).")


def write_measures():
    text = MODEL_TABLE.read_text(encoding="utf-8")
    marker = "\t/// Distinct date+hour slots"
    assert marker in text
    added = []
    for name, (expr, fmt, doc) in MEASURES.items():
        quoted = f"'{name}'" if " " in name else name
        if f"measure {quoted} =" in text:
            continue
        block = f"\t/// {doc}\n\tmeasure {quoted} =\n" + "".join(f"\t\t\t{line}\n" for line in expr)
        if fmt:
            block += f"\t\tformatString: {fmt}\n"
        block += f"\t\tdisplayFolder: report\n\t\tlineageTag: {uuid.uuid4()}\n\n"
        text = text.replace(marker, block + marker, 1)
        added.append(name)
    # status colours: validated text colours on the dark card
    for code in ("VIE", "BTS"):
        text = re.sub(rf'(measure \'{code} YoY Color\' =\n\t\t\tIF\(\[{code} Latest YoY\] < 0, )"#[0-9A-Fa-f]{{6}}", "#[0-9A-Fa-f]{{6}}"\)',
                      rf'\1"{NEG}", "{POS}")', text)
    MODEL_TABLE.write_text(text, encoding="utf-8")
    print("measures added:", ", ".join(added) if added else "none (already present)")


# ------------------------------------------------------------------ resources + pages
def register_backgrounds(main_png: Path, home_png: Path) -> dict[str, str]:
    RESOURCES.mkdir(parents=True, exist_ok=True)
    names = {}
    for key, src in (("main", main_png), ("home", home_png)):
        item = f"bg_{key}{int(hashlib.md5(src.read_bytes()).hexdigest()[:12], 16) % 10**15}.png"
        for old in RESOURCES.glob(f"bg_{key}*.png"):
            try:
                old.unlink()
            except OSError:
                pass
        shutil.copy2(src, RESOURCES / item)
        names[key] = item
    rj = load(REPORT / "report.json")
    for pkg in rj["resourcePackages"]:
        if pkg["name"] == "RegisteredResources":
            pkg["items"] = [i for i in pkg["items"] if not i["name"].startswith(("bg_main", "bg_home"))]
            for item in names.values():
                pkg["items"].append({"name": item, "path": item, "type": "Image"})
    dump(REPORT / "report.json", rj)
    return names


def page_json(page_id, name, bg_item, template):
    page = load(template)
    page["name"], page["displayName"] = page_id, name
    page.pop("visibility", None)
    page.pop("filterConfig", None) if page_id != TREND_ID else None
    page["objects"] = {"background": [{"properties": {
        "image": {"image": {"name": S(bg_item), "url": {"expr": {"ResourcePackageItem": {
            "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": bg_item}}}, "scaling": S("Normal")}},
        "transparency": D(0)}}]}
    return page


def write_page(page_id, name, bg_item, visuals, template):
    root = REPORT / "pages" / page_id
    dump(root / "page.json", page_json(page_id, name, bg_item, template))
    for n, data in visuals.items():
        dump(root / "visuals" / n / "visual.json", data)
    for f in (root / "visuals").glob("*/visual.json"):          # drop visuals of earlier designs
        if f.parent.name not in visuals:
            f.unlink()
            try:
                f.parent.rmdir()
            except OSError:
                pass


def main() -> int:
    import make_backgrounds

    here = PBI
    logo = next(p for p in (here.parent.parent / "vie-bts-blog" / "assets" / "logo" / "fk-lab-logo.png", here / "assets" / "fk-lab-logo.png") if p.exists())
    art = make_backgrounds.make(here / "_art", logo, [(602, 696, 745), (1028, 1122, 745), (1454, 1548, 745)])
    names = register_backgrounds(art["main"], art["home"])
    write_measures()

    trend_template = REPORT / "pages" / TREND_ID / "page.json"          # keeps the date filter (2024 onwards)
    # templates: the trend page keeps its page-level filter; others start without
    base_tpl = load(trend_template)
    tmp = REPORT / "pages" / "_tpl.json"
    dump(tmp, base_tpl)
    write_page(HOME_ID, "Home", names["home"], home(), tmp)
    write_page(TREND_ID, "Trend", names["main"], trend(), tmp)
    write_page(SRC_ID, "Source", names["main"], source(), tmp)
    tmp.unlink()

    pages = load(REPORT / "pages" / "pages.json")
    first = [HOME_ID, TREND_ID, SRC_ID]
    pages["pageOrder"] = first + [p for p in pages["pageOrder"] if p not in first]
    pages["activePageName"] = sys.argv[1] if len(sys.argv) > 1 else HOME_ID
    dump(REPORT / "pages" / "pages.json", pages)
    print("pages written:", {"home": len(home()), "trend": len(trend()), "source": len(source())})
    return 0


if __name__ == "__main__":
    sys.exit(main())
