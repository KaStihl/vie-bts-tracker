// Replace the whole query "public monthly_traffic" with this (Advanced Editor).
// Same output columns as before (so measures and visuals keep working), but:
//   * only rows with a resolved month AND verified = 1: unresolved press-release candidates
//     (month NULL) used to leak into the report and draw phantom spikes
//   * dates are built from numbers, not from culture-dependent text
let
    Source = fnSupabase("monthly_traffic", "airport_code,year,month", null),
    Typed = Table.TransformColumnTypes(
        Source,
        {{"id", Int64.Type}, {"airport_code", type text}, {"year", Int64.Type}, {"month", Int64.Type},
         {"passengers", Int64.Type}, {"yoy_change_pct", type number}, {"group_passengers", Int64.Type},
         {"group_yoy_pct", type number}, {"verified", Int64.Type}, {"source_url", type text}, {"raw_text", type text}},
        "en-US"
    ),
    Published = Table.SelectRows(Typed, each [month] <> null and [verified] = 1),
    Scraped = Table.TransformColumns(
        Published,
        {{"scraped_at", each if _ = null then null else DateTimeZone.RemoveZone(DateTimeZone.SwitchZone(DateTimeZone.FromText(_), 0)), type datetime}}
    ),
    Renamed = Table.RenameColumns(Scraped, {{"month", "month_number"}}),
    MonthHelper = Table.AddColumn(Renamed, "Month_helper", each #date([year], [month_number], 1), type date),
    MonthName = Table.AddColumn(MonthHelper, "Month Name", each Date.MonthName([Month_helper], "en-US"), type text)
in
    MonthName
