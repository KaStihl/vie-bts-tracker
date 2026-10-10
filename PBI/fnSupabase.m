// Power Query function: read a Supabase table through the REST API (PostgREST)
// with paging. Create a new blank query named  fnSupabase  (Advanced Editor)
// and paste everything below.
//
// Set ApiKey to the project's anon / publishable key
// (Supabase -> Project Settings -> API Keys). It is a read-only public key;
// access is limited by the RLS policies in scraper/supabase_public_read.sql.
(table as text, order as text) as table =>
let
    BaseUrl  = "https://xgvjeaymmmbffjltsgvi.supabase.co",
    ApiKey   = "PASTE_ANON_KEY_HERE",
    PageSize = 1000,

    Fetch = (offset as number) as list =>
        Json.Document(
            Web.Contents(
                BaseUrl,
                [
                    RelativePath = "rest/v1/" & table,
                    Query = [
                        select = "*",
                        order  = order,
                        limit  = Text.From(PageSize),
                        offset = Text.From(offset)
                    ],
                    Headers = [
                        apikey        = ApiKey,
                        Authorization = "Bearer " & ApiKey,
                        Accept        = "application/json"
                    ]
                ]
            )
        ),

    Pages = List.Generate(
        () => [off = 0, rows = Fetch(0)],
        each List.Count([rows]) > 0,
        each [
            off  = [off] + PageSize,
            rows = if List.Count([rows]) < PageSize then {} else Fetch([off] + PageSize)
        ],
        each [rows]
    ),

    All = List.Combine(Pages),
    Result = if List.Count(All) = 0 then #table({}, {}) else Table.FromRecords(All)
in
    Result

// ---------------------------------------------------------------------------
// Replace the Source step of each existing query with one of these:
//
//   monthly_traffic    ->  fnSupabase("monthly_traffic",   "airport_code,year,month")
//   annual_traffic     ->  fnSupabase("annual_traffic",    "airport_code,year")
//   carrier_movements  ->  fnSupabase("carrier_movements", "id")
//   airports           ->  fnSupabase("airports",          "icao_code")
//
// REST returns dates/timestamps as text (ISO 8601). Keep or re-add the
// "Changed Type" step so movement_time / scraped_at become datetime(zone).
// ---------------------------------------------------------------------------
