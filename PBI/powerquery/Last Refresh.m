// Replace the query "Query" (rename it "Last Refresh" if you like; Date/Time columns keep their names).
// DateTime.LocalNow() is the refresh time in the machine's local zone: UTC in the Power BI
// service. Use UTC explicitly so Desktop and service agree, and label the card "(UTC)".
let
    Now = DateTimeZone.RemoveZone(DateTimeZone.UtcNow()),
    Table = #table(type table [Column1 = datetime], {{Now}}),
    InsertedDate = Table.AddColumn(Table, "Date", each DateTime.Date([Column1]), type date),
    InsertedTime = Table.AddColumn(InsertedDate, "Time", each DateTime.Time([Column1]), type time)
in
    InsertedTime
