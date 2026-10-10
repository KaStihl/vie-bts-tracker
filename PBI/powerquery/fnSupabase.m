// Power Query function: read one Supabase table through the REST API (PostgREST), paged.
//
// Why REST: the Power BI service cannot validate Supabase's private CA when it connects to
// Postgres directly, so scheduled refresh failed. The REST endpoint uses a publicly trusted
// certificate. Access is read-only for the `anon` role (see scraper/supabase_public_read.sql).
//
// Create a blank query named  fnSupabase  (Home -> Transform data -> New Source -> Blank Query
// -> Advanced Editor) and paste everything below. It needs two parameters, see README.md:
//     SupabaseUrl      e.g. "https://xgvjeaymmmbffjltsgvi.supabase.co"
//     SupabaseAnonKey  the project's anon / publishable key (Supabase -> Project Settings -> API)
//
// table   : table name
// order   : PostgREST order clause, MUST be stable so pages do not overlap, e.g. "id"
// filters : record of PostgREST filters, e.g. [iata_code = "not.is.null"]  (null = none)
(table as text, order as text, filters as nullable record) as table =>
let
    PageSize = 1000,   // raise to 10000+ after raising "Max rows" in Supabase -> Settings -> API

    BaseQuery = [select = "*", order = order, limit = Text.From(PageSize)],
    Fetch = (offset as number) as list =>
        Json.Document(
            Web.Contents(
                SupabaseUrl,
                [
                    RelativePath = "rest/v1/" & table,
                    Query = Record.Combine({BaseQuery, if filters = null then [] else filters, [offset = Text.From(offset)]}),
                    Headers = [
                        apikey        = SupabaseAnonKey,
                        Authorization = "Bearer " & SupabaseAnonKey,
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
