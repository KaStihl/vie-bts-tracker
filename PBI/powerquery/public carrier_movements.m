// Replace the whole query "public carrier_movements" with this.
// movement_time is converted to UTC wall-clock time, so the Hour / Date columns mean the same
// thing in Power BI Desktop (CEST) and in the service (UTC).
let
    Source = fnSupabase("carrier_movements", "id", null),
    Typed = Table.TransformColumnTypes(
        Source,
        {{"id", Int64.Type}, {"airport_code", type text}, {"icao", type text}, {"direction", type text},
         {"callsign", type text}, {"airline", type text}, {"other_airport", type text}, {"icao24", type text},
         {"source_url", type text}},
        "en-US"
    ),
    ToUtc = (t as any) as nullable datetime =>
        if t = null then null else DateTimeZone.RemoveZone(DateTimeZone.SwitchZone(DateTimeZone.FromText(t), 0)),
    Times = Table.TransformColumns(Typed, {{"movement_time", ToUtc, type datetime}, {"scraped_at", ToUtc, type datetime}}),
    MonthName = Table.AddColumn(Times, "Month Name", each Date.MonthName([movement_time], "en-US"), type text),
    Month = Table.AddColumn(MonthName, "Month", each Date.Month([movement_time]), Int64.Type),
    Year = Table.AddColumn(Month, "Year", each Date.Year([movement_time]), Int64.Type),
    Quarter = Table.AddColumn(Year, "Quarter", each Date.QuarterOfYear([movement_time]), Int64.Type),
    WeekOfMonth = Table.AddColumn(Quarter, "Week of Month", each Date.WeekOfMonth([movement_time]), Int64.Type),
    DayName = Table.AddColumn(WeekOfMonth, "Day Name", each Date.DayOfWeekName([movement_time], "en-US"), type text),
    Day = Table.AddColumn(DayName, "Day", each Date.Day([movement_time]), Int64.Type),
    Hour = Table.AddColumn(Day, "Hour", each Time.Hour([movement_time]), Int64.Type),
    Minute = Table.AddColumn(Hour, "Minute", each Time.Minute([movement_time]), Int64.Type),
    TimeCol = Table.AddColumn(Minute, "Time", each DateTime.Time([movement_time]), type time),
    DayOfWeek = Table.AddColumn(TimeCol, "Day of Week", each Date.DayOfWeek([movement_time]), Int64.Type)
in
    DayOfWeek
