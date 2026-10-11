// Replace the whole query "public monthly_traffic" with this (Advanced Editor).
// Same output columns as before (so measures and visuals keep working) plus a "source" column:
//   * official rows: press-release months with verified = 1 (unresolved candidates, month NULL, are dropped)
//   * Eurostat rows (table eurostat_monthly, see scraper/eurostat_monthly.py) ONLY for months without an
//     official figure. Their year-over-year change is computed inside Eurostat's own series, so it never
//     mixes counting bases. Bratislava's Eurostat count equals the airport's own; Vienna's is 1-3 % higher.
//   * dates are built from numbers, not from culture-dependent text
let
    ToUtc = (t as any) as nullable datetime =>
        if t = null then null else DateTimeZone.RemoveZone(DateTimeZone.SwitchZone(DateTimeZone.FromText(t), 0)),

    // ---- official press-release rows ----
    Source = fnSupabase("monthly_traffic", "airport_code,year,month", null),
    Typed = Table.TransformColumnTypes(
        Source,
        {{"id", Int64.Type}, {"airport_code", type text}, {"year", Int64.Type}, {"month", Int64.Type},
         {"passengers", Int64.Type}, {"yoy_change_pct", type number}, {"group_passengers", Int64.Type},
         {"group_yoy_pct", type number}, {"verified", Int64.Type}, {"source_url", type text}, {"raw_text", type text}},
        "en-US"
    ),
    Published = Table.SelectRows(Typed, each [month] <> null and [verified] = 1),
    Scraped = Table.TransformColumns(Published, {{"scraped_at", ToUtc, type datetime}}),
    Renamed = Table.RenameColumns(Scraped, {{"month", "month_number"}}),
    Official = Table.AddColumn(Renamed, "source", each "Press release", type text),

    // ---- Eurostat rows for the gaps ----
    // the table is created by the first scraper run; until then the report just shows the official months
    EuroRaw = try fnSupabase("eurostat_monthly", "airport_code,year,month", null)
        otherwise #table({"airport_code", "year", "month", "passengers", "scraped_at"}, {}),
    EuroTyped = Table.TransformColumnTypes(
        EuroRaw,
        {{"airport_code", type text}, {"year", Int64.Type}, {"month", Int64.Type}, {"passengers", Int64.Type}},
        "en-US"
    ),
    EuroPrev = Table.RenameColumns(
        Table.TransformColumns(
            Table.SelectColumns(EuroTyped, {"airport_code", "year", "month", "passengers"}),
            {{"year", each _ + 1, Int64.Type}}
        ),
        {{"passengers", "prev_passengers"}}
    ),
    EuroJoined = Table.ExpandTableColumn(
        Table.NestedJoin(EuroTyped, {"airport_code", "year", "month"}, EuroPrev, {"airport_code", "year", "month"}, "p", JoinKind.LeftOuter),
        "p", {"prev_passengers"}
    ),
    EuroYoy = Table.AddColumn(
        EuroJoined, "yoy_change_pct",
        each if [prev_passengers] = null or [prev_passengers] = 0 then null else Number.Round(([passengers] / [prev_passengers] - 1) * 100, 1),
        type number
    ),
    EuroRenamed = Table.RenameColumns(EuroYoy, {{"month", "month_number"}}),
    EuroGaps = Table.RemoveColumns(
        Table.NestedJoin(EuroRenamed, {"airport_code", "year", "month_number"}, Official, {"airport_code", "year", "month_number"}, "o", JoinKind.LeftAnti),
        {"prev_passengers"}
    ),
    EuroScraped = Table.RemoveColumns(Table.TransformColumns(EuroGaps, {{"scraped_at", ToUtc, type datetime}}), {"passengers_carried"}, MissingField.Ignore),
    EuroId = Table.AddColumn(EuroScraped, "id", each null, Int64.Type),
    EuroGroupPax = Table.AddColumn(EuroId, "group_passengers", each null, Int64.Type),
    EuroGroupYoy = Table.AddColumn(EuroGroupPax, "group_yoy_pct", each null, type number),
    EuroVerified = Table.AddColumn(EuroGroupYoy, "verified", each 1, Int64.Type),
    EuroUrl = Table.AddColumn(EuroVerified, "source_url", each "https://ec.europa.eu/eurostat/databrowser/view/avia_paoa/", type text),
    EuroText = Table.AddColumn(EuroUrl, "raw_text", each "Eurostat avia_paoa: passengers on board (month not published by the airport)", type text),
    Euro = Table.AddColumn(EuroText, "source", each "Eurostat", type text),

    // ---- combine ----
    Combined = Table.Combine({Official, Euro}),
    MonthHelper = Table.AddColumn(Combined, "Month_helper", each #date([year], [month_number], 1), type date),
    MonthName = Table.AddColumn(MonthHelper, "Month Name", each Date.MonthName([Month_helper], "en-US"), type text)
in
    MonthName
