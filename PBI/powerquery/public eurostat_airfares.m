// New query "public eurostat_airfares": airfare price index (Eurostat HICP, passenger transport by air) per country.
// Filled by scraper/eurostat_airfares.py in the weekly scrape.
let
    // the table is created by the weekly scrape; until then the Prices page is simply empty
    Source = try fnSupabase("eurostat_airfares", "geo,year,month", null)
        otherwise #table({"geo", "year", "month", "annual_rate_pct", "index_2025"}, {}),
    Typed = Table.TransformColumnTypes(
        Source,
        {{"geo", type text}, {"year", Int64.Type}, {"month", Int64.Type}, {"annual_rate_pct", type number}, {"index_2025", type number}},
        "en-US"
    ),
    Columns = Table.SelectColumns(Typed, {"geo", "year", "month", "annual_rate_pct", "index_2025"})
in
    Columns
