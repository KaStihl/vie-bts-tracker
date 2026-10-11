<#
  VIE-BTS semantic model fixes (2026-10-10), applied to the model open in Power BI Desktop
  through its local Analysis Services port (Tabular Object Model). Metadata only:
  relationships, measures, column properties. Data queries (partitions) are NOT touched,
  because changing a partition's query clears its loaded data.

  Usage:  .\model-fixes-2026-10.ps1 -Port <port of msmdsrv>   (find it: Get-NetTCPConnection -OwningProcess (Get-Process msmdsrv).Id)
  Then save in Power BI Desktop (Ctrl+S).
#>
param([Parameter(Mandatory = $true)][int]$Port, [switch]$WhatIf)

$bin = "C:\Program Files\DAX Studio\bin"
Add-Type -Path "$bin\Microsoft.AnalysisServices.Core.dll"
Add-Type -Path "$bin\Microsoft.AnalysisServices.Tabular.Json.dll"
Add-Type -Path "$bin\Microsoft.AnalysisServices.Tabular.dll"
$T = "Microsoft.AnalysisServices.Tabular"

$server = New-Object "$T.Server"
$server.Connect("Data Source=localhost:$Port")
$db = $server.Databases[0]
$m = $db.Model
$log = New-Object System.Collections.Generic.List[string]
function Log($s) { $script:log.Add($s); Write-Host $s }

function Get-Tbl($name) { $t = $m.Tables.Find($name); if (-not $t) { throw "table '$name' not found" }; $t }
function Set-Measure($tbl, $name, $expr, $fmt, $folder, $desc) {
    $me = $tbl.Measures.Find($name)
    if (-not $me) {
        $me = New-Object "$T.Measure"; $me.Name = $name; $tbl.Measures.Add($me); Log "  + measure [$name]"
    } else { Log "  ~ measure [$name]" }
    $me.Expression = $expr
    if ($fmt)    { $me.FormatString = $fmt }
    if ($folder) { $me.DisplayFolder = $folder }
    if ($desc)   { $me.Description = $desc }
}
function Set-Col($tbl, $name, [hashtable]$p) {
    $c = $tbl.Columns.Find($name)
    if (-not $c) { Log "  ! column $($tbl.Name)[$name] not found, skipped"; return }
    foreach ($k in $p.Keys) { $c.$k = $p[$k] }
}

$mt  = Get-Tbl 'public monthly_traffic'
$at  = Get-Tbl 'public annual_traffic'
$cm  = Get-Tbl 'public carrier_movements'
$ap  = Get-Tbl 'public airports'
$ms  = Get-Tbl '_Measures'
$dt  = Get-Tbl 'DateTable'
$none = [Microsoft.AnalysisServices.Tabular.AggregateFunction]::None
$sumF = [Microsoft.AnalysisServices.Tabular.AggregateFunction]::Sum

# ---------------------------------------------------------------- 1. relationships
Log "1. Relationships"
foreach ($r in @($m.Relationships)) {
    if ($r.ToTable.Name -eq 'public airports' -and $r.FromColumn.Name -eq 'airport_code' -and
        ($r.FromTable.Name -in 'public monthly_traffic', 'public annual_traffic')) {
        Log "  - removed broken $($r.FromTable.Name)[airport_code] -> airports[icao_code] (VIE/BTS never equal ICAO codes: matched 0 rows)"
        $m.Relationships.Remove($r) | Out-Null
    }
}
if (-not $m.Tables.Find('Airport')) {
    $air = New-Object "$T.Table"; $air.Name = 'Airport'
    $air.Description = "The two airports being compared. Related to monthly, annual and movement facts on the short code (VIE/BTS) so one Airport filter drives every page."
    $part = New-Object "$T.Partition"; $part.Name = 'Airport'
    $src = New-Object "$T.CalculatedPartitionSource"
    # The script file is ASCII on purpose (Windows PowerShell 5.1 reads BOM-less files as ANSI and
    # would corrupt non-ASCII letters), so the accented name is assembled from code points.
    $stefanik = 'M. R. ' + [char]0x0160 + 'tef' + [char]0x00E1 + 'nik Airport'
    $src.Expression = @'
DATATABLE(
    "Airport Code", STRING,
    "ICAO", STRING,
    "Airport", STRING,
    "City", STRING,
    "Country", STRING,
    {
        { "VIE", "LOWW", "Vienna International Airport", "Vienna", "Austria" },
        { "BTS", "LZIB", "__SN__", "Bratislava", "Slovakia" }
    }
)
'@.Replace('__SN__', $stefanik)
    $part.Source = $src; $air.Partitions.Add($part)
    foreach ($n in 'Airport Code', 'ICAO', 'Airport', 'City', 'Country') {
        $c = New-Object "$T.CalculatedTableColumn"; $c.Name = $n
        $c.DataType = [Microsoft.AnalysisServices.Tabular.DataType]::String
        $c.SourceColumn = "[$n]"; $c.SummarizeBy = $none
        $air.Columns.Add($c)
    }
    $m.Tables.Add($air)
    Log "  + calculated table 'Airport'"
}
$air = Get-Tbl 'Airport'
foreach ($fact in @($mt, $at, $cm)) {
    $exists = $m.Relationships | Where-Object { $_.FromTable.Name -eq $fact.Name -and $_.ToTable.Name -eq 'Airport' }
    if (-not $exists) {
        $rel = New-Object "$T.SingleColumnRelationship"
        $rel.Name = [guid]::NewGuid().ToString()
        $rel.FromColumn = $fact.Columns.Find('airport_code')
        $rel.ToColumn = $air.Columns.Find('Airport Code')
        $rel.FromCardinality = [Microsoft.AnalysisServices.Tabular.RelationshipEndCardinality]::Many
        $rel.ToCardinality = [Microsoft.AnalysisServices.Tabular.RelationshipEndCardinality]::One
        $rel.CrossFilteringBehavior = [Microsoft.AnalysisServices.Tabular.CrossFilteringBehavior]::OneDirection
        $m.Relationships.Add($rel)
        Log "  + relationship $($fact.Name)[airport_code] -> Airport[Airport Code]"
    }
}

# ---------------------------------------------------------------- 2. calculated columns
Log "2. Calculated columns"
$dateCol = $mt.Columns.Find('Date')
$dateCol.Expression = "IF(ISBLANK('public monthly_traffic'[month_number]), BLANK(), DATE('public monthly_traffic'[year], 'public monthly_traffic'[month_number], 1))"
Log "  ~ monthly_traffic[Date]: unresolved rows (month NULL) no longer collapse onto December of the previous year (DATE(y,0,1))"
$num = $cm.Columns.Find('_num')
if ($num) { $cm.Columns.Remove($num) | Out-Null; Log "  - removed unused calculated column carrier_movements[_num]" }

# ---------------------------------------------------------------- 3. measures
Log "3. Measures"
foreach ($x in @(@($ap, 'rows'), @($cm, 'rows2'), @($mt, 'rows3'))) {
    $me = $x[0].Measures.Find($x[1]); if ($me) { $x[0].Measures.Remove($me) | Out-Null; Log "  - removed auto-generated measure [$($x[1])]" }
}

Set-Measure $ms 'WoW %' "DIVIDE([Total Movements] - [Movements Previous Week], [Movements Previous Week])" '0.00%;-0.00%;0.00%' 'time_intelligence' `
    "Week-over-week change in captured movements. (Was divided by 100 a second time, so it showed 1/100 of the real value.)"

Set-Measure $ms 'YoY Change PAX %' @'
VAR _rows = COUNTROWS('public monthly_traffic')
VAR _reported = SUM('public monthly_traffic'[yoy_change_pct])
VAR _current = SUM('public monthly_traffic'[passengers])
VAR _month = SELECTEDVALUE('public monthly_traffic'[Date])
VAR _lastYear =
    IF(
        NOT ISBLANK(_month),
        CALCULATE(
            SUM('public monthly_traffic'[passengers]),
            REMOVEFILTERS(DateTable),
            REMOVEFILTERS('public monthly_traffic'[Date]),
            'public monthly_traffic'[Date] = EDATE(_month, -12)
        )
    )
RETURN
    IF(
        _rows = 1 && NOT ISBLANK(_reported),
        _reported / 100,
        IF(NOT ISBLANK(_current) && _lastYear > 0, DIVIDE(_current - _lastYear, _lastYear))
    )
'@ '0.00%;-0.00%;0.00%' 'monthly_traffic' `
    "Year-over-year passenger change for one month. Uses the % published by the airport; where the release gave none (BTS 2019-2024, most VIE 2023 headlines) it is computed from the same month a year earlier. Never sums percentages."

Set-Measure $ms 'VIE Latest Month' @'
VAR _latest = CALCULATE(MAX('public monthly_traffic'[Date]), 'public monthly_traffic'[airport_code] = "VIE")
RETURN FORMAT(_latest, "mmm yyyy")
'@ $null 'monthly_traffic' "Month of the newest Vienna figure - show it under the card so readers know which month is compared."
Set-Measure $ms 'BTS Latest Month' @'
VAR _latest = CALCULATE(MAX('public monthly_traffic'[Date]), 'public monthly_traffic'[airport_code] = "BTS")
RETURN FORMAT(_latest, "mmm yyyy")
'@ $null 'monthly_traffic' "Month of the newest Bratislava figure."

Set-Measure $ms 'Rozdiel v trende' @'
-- BTS growth minus VIE growth, in percentage points, for the newest month BOTH airports have.
VAR _vie = CALCULATE(MAX('public monthly_traffic'[Date]), 'public monthly_traffic'[airport_code] = "VIE", NOT ISBLANK('public monthly_traffic'[yoy_change_pct]))
VAR _bts = CALCULATE(MAX('public monthly_traffic'[Date]), 'public monthly_traffic'[airport_code] = "BTS", NOT ISBLANK('public monthly_traffic'[yoy_change_pct]))
VAR _common = MIN(_vie, _bts)
VAR _vieYoY = CALCULATE(SUM('public monthly_traffic'[yoy_change_pct]), 'public monthly_traffic'[airport_code] = "VIE", 'public monthly_traffic'[Date] = _common)
VAR _btsYoY = CALCULATE(SUM('public monthly_traffic'[yoy_change_pct]), 'public monthly_traffic'[airport_code] = "BTS", 'public monthly_traffic'[Date] = _common)
RETURN IF(NOT ISBLANK(_vieYoY) && NOT ISBLANK(_btsYoY), _btsYoY - _vieYoY)
'@ '+0.0" pp";-0.0" pp";0.0" pp"' 'monthly_traffic' `
    "Growth gap BTS minus VIE in PERCENTAGE POINTS (not %), same month for both airports. Signed: no longer hides the case where Vienna outgrows Bratislava (was ABS()). Name kept because report visuals reference it."

Set-Measure $ms 'Departure Hours With Data' @'
COUNTROWS(
    SUMMARIZE(
        FILTER(
            'public carrier_movements',
            'public carrier_movements'[direction] = "departure"
                && 'public carrier_movements'[Hour] >= 5
                && 'public carrier_movements'[Hour] <= 21
        ),
        'public carrier_movements'[Date],
        'public carrier_movements'[Hour]
    )
)
'@ '0' 'data_quality' "Distinct date+hour slots (05:00-21:59, assumed UTC) that contain at least one captured departure."
Set-Measure $ms 'Capture Coverage %' @'
VAR _days = DATEDIFF(MIN('public carrier_movements'[Date]), MAX('public carrier_movements'[Date]), DAY) + 1
RETURN DIVIDE([Departure Hours With Data], _days * 17)
'@ '0%' 'data_quality' "Share of daytime hours (17 per day) with at least one captured departure. Far below 100% means the hourly OpenSky job missed runs (movements in the gaps are lost for good), so absolute movement counts are UNDERCOUNTED; shares between airlines are still usable."
Set-Measure $ms 'Last Movement Captured' "MAX('public carrier_movements'[movement_time])" 'dd mmm yyyy hh:mm' 'data_quality' "Timestamp of the newest captured movement - tells readers how fresh the carrier data is."

# ---------------------------------------------------------------- 4. column hygiene
Log "4. Column properties"
foreach ($n in 'id', 'year', 'month_number', 'verified', 'yoy_change_pct', 'group_yoy_pct') { Set-Col $mt $n @{ SummarizeBy = $none } }
Set-Col $mt 'yoy_change_pct'   @{ FormatString = '0.0"%"'; Description = "Year-over-year change as published, in percent units (-5.9 means -5.9 %). Use the [YoY Change PAX %] measure for display." }
Set-Col $mt 'group_yoy_pct'    @{ FormatString = '0.0"%"' }
Set-Col $mt 'group_passengers' @{ FormatString = '#,0' }
Set-Col $mt 'passengers'       @{ FormatString = '#,0' }
Set-Col $mt 'Date'             @{ FormatString = 'mmm yyyy'; Description = 'First day of the reported month (blank for unresolved rows). Axis labels read like Jan 2026.' }
foreach ($n in 'id', 'source_url', 'raw_text', 'scraped_at', 'Month_helper', 'verified') { Set-Col $mt $n @{ IsHidden = $true } }
foreach ($n in 'id', 'year') { Set-Col $at $n @{ SummarizeBy = $none } }
foreach ($n in 'id', 'scraped_at') { Set-Col $at $n @{ IsHidden = $true } }
foreach ($n in 'id', 'Month', 'Year', 'Quarter', 'Week of Month', 'Day', 'Hour', 'Minute', 'Day of Week') { Set-Col $cm $n @{ SummarizeBy = $none } }
foreach ($n in 'id', 'source_url', 'scraped_at', 'icao24', 'Month', 'Year', 'Quarter', 'Week of Month', 'Day', 'Minute', 'Day of Week', 'Time') { Set-Col $cm $n @{ IsHidden = $true } }
Set-Col $ap 'latitude'  @{ SummarizeBy = $none; DataCategory = 'Latitude' }
Set-Col $ap 'longitude' @{ SummarizeBy = $none; DataCategory = 'Longitude' }
foreach ($n in 'Year', 'Month Number', 'Week Number') { Set-Col $dt $n @{ SummarizeBy = $none } }
Log "  ~ summarisation off for keys/years/percent columns, technical columns hidden, percent columns formatted as literal %"

# ---------------------------------------------------------------- 5. date table + descriptions
Log "5. Date table"
$dt.DataCategory = 'Time'
$dt.Columns.Find('Date').IsKey = $true
Log "  ~ DateTable marked as the model's date table (time-intelligence functions need it)"
$dt.Description = "Calendar spanning the monthly and movement data. Marked as date table."
$ms.Description = "Measure container. NOTE: the name is a typo of 'Measures' but report visuals reference it - rename it in Power BI Desktop (Model view), which updates visuals automatically."
$cm.Description = "OpenSky aircraft movements captured for LOWW/LZIB. Coverage is partial (see [Capture Coverage %])."
$mt.Description = "Official monthly passenger counts from airport press releases (VIE) and press releases / annual report (BTS)."
$at.Description = "Official annual passenger totals."
$ap.Description = "OurAirports reference list (ICAO code -> name/city/country); used for movement destinations."

if ($WhatIf) { Log "WhatIf: no changes saved"; $server.Disconnect(); return }
$m.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Calculate)
$res = $m.SaveChanges()
Log "Saved to the open model (in memory). Now press Ctrl+S in Power BI Desktop."
$server.Disconnect()
