"""
Patch the report layer of VIE-BTS.pbix (PBIR format) without opening Power BI Desktop.

    python PBI/tools/patch_report.py PBI/VIE-BTS.pbix --out PBI/VIE-BTS.patched.pbix   # recommended
    python PBI/tools/patch_report.py PBI/VIE-BTS.pbix                                  # in place (backup first)

Open the --out file in Power BI Desktop first; replace VIE-BTS.pbix only once it loads.

IMPORTANT: close Power BI Desktop (after saving!) before running this on the real file;
Desktop would otherwise overwrite the patched report when it saves.

Only properties that are matched by name/text are touched, every edit is reported, and the
script is idempotent (running it twice changes nothing the second time). The DataModel,
credentials and every other file inside the .pbix are copied byte for byte: the archive is
rewritten at byte level (original local headers and compressed data are kept; only the changed
entries and their central-directory records are updated), and JSON keeps its original float
spelling. A first version re-wrote the archive with Python's zipfile and produced a file that
Power BI Desktop rejected as corrupted.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import sys
import zipfile
import zlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- what to change
TEXT_REPLACEMENTS = [
    # (exact text in a text run, replacement)
    ('This section will be added once it has enough depth to be meaningful."',
     "This section will be added once it has enough depth to be meaningful."),
    ("OpenSky: https://https://opensky-network.org/", "OpenSky: https://opensky-network.org/"),
    ("Last Refresh :", "Last refresh (UTC):"),
]
# Replace a whole run when it STARTS with this text.
TEXT_PREFIX_REPLACEMENTS = [
    ('NOTE: "Wizz Air ended operations at Vienna',
     "Wizz Air opened a base in Bratislava on 14 November 2025 and ended its Vienna operations in "
     "March 2026 (Austrian aviation tax). Vienna's year-over-year change turns negative from "
     "April 2026, while Bratislava keeps growing at double- and triple-digit rates."),
]
# Card captions: measure property -> caption shown on the card
CARD_CAPTIONS = {
    "Rozdiel v trende": "Growth gap (pp)",
    "VIE Latest Passengers": "VIE PAX (latest month)",
    "BTS Latest Passengers": "BTS PAX (latest month)",
    "VIE Latest YoY": "VIE YoY % (latest month)",
    "BTS Latest YoY": "BTS YoY % (latest month)",
}
PAGE_RENAMES = {
    "Duplicate of Page 3": "Carrier Analysis (WIP)",
    "BTS Overview": "BTS Operations (WIP)",
}
YOY_CHART_TITLE = "YoY of PAX by Airport in %"
TOTAL_PAX_CHART_TITLE = "Total PAX by Airport"


def literal(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def container_title(visual: dict):
    for t in visual.get("visual", {}).get("visualContainerObjects", {}).get("title", []):
        text = t.get("properties", {}).get("text")
        if text:
            return text["expr"]["Literal"]["Value"].strip("'")
    return None


def walk_text_runs(node, fn):
    """Call fn(run_dict) for every {'value': ...} text run anywhere in the tree."""
    if isinstance(node, dict):
        if isinstance(node.get("value"), str) and ("textStyle" in node or "textRuns" not in node and "paragraphs" not in node):
            fn(node)
        for v in node.values():
            walk_text_runs(v, fn)
    elif isinstance(node, list):
        for v in node:
            walk_text_runs(v, fn)


def patch_visual(path: str, data: dict, report: list) -> bool:
    changed = False
    visual = data.get("visual", {})
    vtype = visual.get("visualType")

    # --- text boxes
    if vtype == "textbox":
        def fix(run):
            nonlocal changed
            for old, new in TEXT_REPLACEMENTS:
                if run["value"] == old:
                    run["value"] = new; changed = True; report.append(f"text: '{old[:40]}...' -> '{new[:40]}...' ({path})")
            if "https://https://" in run["value"]:
                run["value"] = run["value"].replace("https://https://", "https://"); changed = True
                report.append(f"text: doubled https:// fixed ({path})")
            # a hyperlink run whose visible text is a URL must point at that URL
            if run["value"].startswith("https://opensky-network.org") and run.get("url") != run["value"]:
                run["url"] = run["value"]; changed = True
                report.append(f"link: OpenSky link pointed at '{str(run.get('url'))[:30]}', now at the OpenSky site ({path})")
        walk_text_runs(visual.get("objects", {}), fix)

        # paragraphs whose text is split over several runs (a bold "NOTE: " + the sentence)
        def fix_paragraphs(node):
            nonlocal changed
            if isinstance(node, dict):
                runs = node.get("textRuns")
                if isinstance(runs, list) and runs and all(isinstance(r, dict) and isinstance(r.get("value"), str) for r in runs):
                    joined = "".join(r["value"] for r in runs)
                    for prefix, new in TEXT_PREFIX_REPLACEMENTS:
                        if joined.startswith(prefix):
                            runs[-1]["value"] = new
                            for r in runs[:-1]:
                                if r["value"].strip().upper() != "NOTE:":
                                    r["value"] = ""
                            changed = True; report.append(f"text: note rewritten to match the data ({path})")
                for v in node.values():
                    fix_paragraphs(v)
            elif isinstance(node, list):
                for v in node:
                    fix_paragraphs(v)
        fix_paragraphs(visual.get("objects", {}))

    # --- card captions
    for role in visual.get("query", {}).get("queryState", {}).values():
        for p in role.get("projections", []):
            prop = p.get("field", {}).get("Measure", {}).get("Property")
            caption = CARD_CAPTIONS.get(prop)
            if vtype == "cardVisual" and caption and (p.get("displayName") != caption or p.get("nativeQueryRef") != caption):
                p["displayName"] = caption; p["nativeQueryRef"] = caption; changed = True
                report.append(f"card caption: {prop} -> '{caption}' ({path})")

    title = container_title(data)
    objects = visual.get("objects", {})

    # --- YoY chart: drop the dashed linear trend line (meaningless across two airports)
    if vtype == "lineClusteredColumnComboChart" and title == YOY_CHART_TITLE:
        for t in objects.get("trend", []):
            props = t.setdefault("properties", {})
            if props.get("show", {}).get("expr", {}).get("Literal", {}).get("Value") != "false":
                props["show"] = literal("false"); changed = True
                report.append(f"chart '{title}': trend line off ({path})")

    # --- Total PAX line chart: straight segments + markers. 'smooth' (cardinal) interpolation
    #     invents values between the months an airport actually published.
    if vtype == "lineChart" and title == TOTAL_PAX_CHART_TITLE:
        styles = objects.setdefault("lineStyles", [{"properties": {}}])
        for style in styles:
            if "selector" in style:
                continue
            props = style.setdefault("properties", {})
            if props.get("lineChartType", {}).get("expr", {}).get("Literal", {}).get("Value") != "'linear'":
                props["lineChartType"] = literal("'linear'"); changed = True
                report.append(f"chart '{title}': smooth curve -> straight segments ({path})")
            if props.get("showMarker", {}).get("expr", {}).get("Literal", {}).get("Value") != "true":
                props["showMarker"] = literal("true"); changed = True
                report.append(f"chart '{title}': markers on ({path})")
    return changed


def patch_page(path: str, data: dict, report: list) -> bool:
    new = PAGE_RENAMES.get(data.get("displayName"))
    if new:
        report.append(f"page: '{data['displayName']}' -> '{new}'")
        data["displayName"] = new
        return True
    return False


_FLOAT_MARK = "@@FLOAT:"


def loads(raw: bytes):
    """Parse JSON but keep every float's ORIGINAL spelling (Desktop writes 64.666666666666671,
    Python would print 64.66666666666667): floats become marker strings, restored by dumps()."""
    return json.loads(raw.decode("utf-8-sig"), parse_float=lambda lit: f"{_FLOAT_MARK}{lit}@@")


def dumps(data) -> bytes:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = re.sub(r'"@@FLOAT:([^"@]+)@@"', lambda m: m.group(1), text)
    return text.encode("utf-8")


def rewrite_zip(src: Path, dst: Path, replacements: dict[str, bytes]) -> None:
    """Copy `src` to `dst` changing ONLY the entries in `replacements`.

    Every other entry keeps its original local header and compressed bytes, and the central
    directory is the original one with just the changed entries' CRC/sizes/offsets updated.
    (Re-writing the archive with Python's zipfile changed header fields on every entry, and
    Power BI Desktop refused the result as corrupted.)
    """
    data = src.read_bytes()
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        cd_start = z.start_dir
    assert all(i.flag_bits & 0x08 == 0 for i in infos), "data descriptors not supported"

    out = bytearray()
    new_meta = {}  # name -> (crc, comp_size, size, new_offset)
    for i in infos:  # archive order == offset order
        off = i.header_offset
        name_len, extra_len = struct.unpack_from("<HH", data, off + 26)
        header = bytearray(data[off: off + 30 + name_len + extra_len])
        body_start = off + len(header)
        new_offset = len(out)
        if i.filename in replacements:
            raw = replacements[i.filename]
            comp = zlib.compressobj(6, zlib.DEFLATED, -15)
            body = comp.compress(raw) + comp.flush()
            assert i.compress_type == zipfile.ZIP_DEFLATED
            crc = zlib.crc32(raw) & 0xFFFFFFFF
            struct.pack_into("<III", header, 14, crc, len(body), len(raw))
            new_meta[i.filename] = (crc, len(body), len(raw), new_offset)
        else:
            body = data[body_start: body_start + i.compress_size]
            new_meta[i.filename] = (i.CRC, i.compress_size, i.file_size, new_offset)
        out += header + body

    new_cd_start = len(out)
    pos = cd_start
    names_in_order = [i.filename for i in infos]
    for name in names_in_order:
        sig, = struct.unpack_from("<I", data, pos)
        assert sig == 0x02014B50
        n, e, c = struct.unpack_from("<HHH", data, pos + 28)
        rec = bytearray(data[pos: pos + 46 + n + e + c])
        assert rec[46: 46 + n].decode("utf-8") == name
        crc, comp_size, size, offset = new_meta[name]
        struct.pack_into("<III", rec, 16, crc, comp_size, size)
        struct.pack_into("<I", rec, 42, offset)
        out += rec
        pos += len(rec)
    eocd = bytearray(data[pos:])  # end-of-central-directory record (+ comment)
    assert struct.unpack_from("<I", eocd, 0)[0] == 0x06054B50
    struct.pack_into("<II", eocd, 12, pos - cd_start, new_cd_start)  # cd size, cd offset
    out += eocd
    dst.write_bytes(bytes(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pbix", type=Path)
    ap.add_argument("--out", type=Path, help="write here instead of patching in place")
    args = ap.parse_args()

    src = args.pbix
    target = args.out or src
    if target == src:
        backup = src.with_name(src.stem + ".before-patch.pbix.bak")
        shutil.copy2(src, backup)
        print(f"backup: {backup}")
    tmp = target.with_name(target.name + ".tmp")

    report: list[str] = []
    replacements: dict[str, bytes] = {}
    with zipfile.ZipFile(src) as zin:
        for name in zin.namelist():
            if name.startswith("Report/definition/pages/") and name.endswith(".json") and not name.endswith("pages.json"):
                raw = zin.read(name)
                data = loads(raw)
                changed = patch_visual(name, data, report) if name.endswith("visual.json") else patch_page(name, data, report)
                if changed:
                    replacements[name] = dumps(data)

    rewrite_zip(src, tmp, replacements)

    # verify: same entries and headers, identical bytes except the patched ones, JSON parses
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(tmp) as b:
        assert a.namelist() == b.namelist(), "entry list changed"
        for ia in a.infolist():
            ib = b.getinfo(ia.filename)
            for f in ("compress_type", "flag_bits", "create_system", "create_version", "extract_version",
                      "external_attr", "internal_attr", "date_time", "extra"):
                assert getattr(ia, f) == getattr(ib, f), f"header field {f} changed on {ia.filename}"
            if ia.filename not in replacements:
                assert a.read(ia.filename) == b.read(ia.filename), f"unexpected change in {ia.filename}"
            elif ia.filename.endswith(".json"):
                json.loads(b.read(ia.filename))
        assert b.testzip() is None

    tmp.replace(target)
    print("\n".join(report) if report else "nothing to change (already patched)")
    print(f"\n{len(replacements)} file(s) patched -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
