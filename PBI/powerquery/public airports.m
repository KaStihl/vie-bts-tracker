// Replace the whole query "public airports" with this.
// Only airports with an IATA code (every airport that has scheduled traffic) are fetched:
// ~9k rows instead of the full 86k OurAirports list, which would take 86 REST requests per refresh.
let
    Source = fnSupabase("airports", "icao_code", [iata_code = "not.is.null"]),
    Typed = Table.TransformColumnTypes(
        Source,
        {{"icao_code", type text}, {"iata_code", type text}, {"name", type text}, {"city", type text},
         {"country", type text}, {"country_code", type text}, {"airport_type", type text},
         {"latitude", type number}, {"longitude", type number}},
        "en-US"
    )
in
    Typed
