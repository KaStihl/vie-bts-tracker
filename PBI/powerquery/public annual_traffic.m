// Replace the whole query "public annual_traffic" with this.
let
    Source = fnSupabase("annual_traffic", "airport_code,year", null),
    Typed = Table.TransformColumnTypes(
        Source,
        {{"id", Int64.Type}, {"airport_code", type text}, {"year", Int64.Type}, {"scheduled", Int64.Type},
         {"nonscheduled", Int64.Type}, {"other", Int64.Type}, {"total", Int64.Type}},
        "en-US"
    ),
    Scraped = Table.TransformColumns(
        Typed,
        {{"scraped_at", each if _ = null then null else DateTimeZone.RemoveZone(DateTimeZone.SwitchZone(DateTimeZone.FromText(_), 0)), type datetime}}
    )
in
    Scraped
