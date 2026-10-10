# Power BI report: VIE-BTS.pbix

## Files

| Path | What |
|---|---|
| `VIE-BTS.pbix` | the report (source of truth; the text files below are readable snapshots / helpers) |
| `model/` | the semantic model as **TMDL** text, exported from the open report. Diff this in git to see model changes; it is not meant to be edited by hand |
| `powerquery/` | ready-to-paste Power Query for the REST data source (see "Switch the data source") |
| `tools/model-fixes-2026-10.ps1` | the script that applied the October-2026 model fixes through the Desktop's local Analysis Services port |
| `tools/patch_report.py` | idempotent patcher for report-layer text/visual fixes inside the `.pbix` |
| `fnSupabase.m` | the first draft of the REST function (superseded by `powerquery/fnSupabase.m`) |

## Model

```
Airport (VIE, BTS) 1 --> * public monthly_traffic   --> DateTable (date table)
                   1 --> * public annual_traffic
                   1 --> * public carrier_movements --> DateTable
public airports  1 --> * public carrier_movements   (origin ICAO active, other_airport inactive)
Meausre  = measure container (typo kept on purpose, see below)      Query = refresh timestamp
```

### Fixed in October 2026

| # | Problem | Fix |
|---|---|---|
| 1 | `monthly_traffic` and `annual_traffic` were related to `airports` on `VIE`/`BTS` = `icao_code` (`LOWW`/`LZIB`): the join matched **0 rows** | removed; new `Airport` dimension related on the short code |
| 2 | `Date` = `DATE(year, month, 1)`: rows with an unresolved month became `DATE(y, 0, 1)` = **December of the previous year**, adding phantom spikes (e.g. BTS Dec-2024 showed +273,807) | blank date when the month is NULL |
| 3 | `[WoW %]` divided by 100 twice (showed 0.10 % instead of 10.3 %) | fixed |
| 4 | `[YoY Change PAX %]` summed percentages and was blank for every month without a published %, e.g. all of BTS 2019-2024 | uses the airport's published % for one month; otherwise computes it from the same month a year earlier; never sums percentages. Cross-checked: computed Jun-2024 13.9 % vs published "14 %", Aug-2024 3.3 % vs "three percent" |
| 5 | `[Rozdiel v trende]` was `ABS(BTS - VIE) / 100` formatted as %, from different months when one airport published later | signed gap in **percentage points**, same month for both airports |
| 6 | Cards "Latest" could compare different months silently | added `[VIE Latest Month]`, `[BTS Latest Month]` |
| 7 | No view of how complete the OpenSky data is | `[Capture Coverage %]` (≈47 % in Oct 2026), `[Departure Hours With Data]`, `[Last Movement Captured]` |
| 8 | `DateTable` not marked as date table; `rows`, `rows2`, `rows3` junk measures; unused `_num` column; id/year/% columns summing by default; technical columns visible | cleaned up; percent columns formatted as literal `%` |

**Rename `Meausre` -> `_Measures` in Power BI Desktop** (Model view). It is a typo, but report
visuals reference the name, and only Desktop can rename it *and* update the visuals.

### Re-applying / auditing

`tools/model-fixes-2026-10.ps1 -Port <n>` is idempotent. Port: Desktop must have the report
open; `Get-NetTCPConnection -State Listen -OwningProcess (Get-Process msmdsrv).Id`.
Re-export the TMDL snapshot after model changes and commit it.

## Switch the data source to the Supabase REST API (fixes the stale "Last refresh")

The Power BI **service** cannot validate Supabase's private CA when connecting to Postgres, so
scheduled refresh fails and the published report keeps showing old data (on 10 Oct 2026 the
latest movement was 28 Sep, "Last refresh" 2 Oct). The REST API has a normal certificate.

Prerequisite: run `scraper/supabase_public_read.sql` once in the Supabase SQL editor
(read-only RLS policies for the `anon` role).

In Power BI Desktop -> **Transform data**:

1. **Manage parameters -> New parameters** (type Text, required):
   * `SupabaseUrl` = `https://xgvjeaymmmbffjltsgvi.supabase.co`
   * `SupabaseAnonKey` = the **anon / publishable** key (Supabase -> Project Settings -> API).
     It is a public key, but keep it out of git: it lives only in the parameter.
2. New blank query `fnSupabase` -> Advanced Editor -> paste `powerquery/fnSupabase.m`.
3. For each of `public monthly_traffic`, `public annual_traffic`, `public carrier_movements`,
   `public airports`, and `Query`: open **Advanced Editor** and replace the whole query with the
   matching file in `powerquery/`. Output columns keep their names, so measures and visuals
   keep working. When asked for credentials choose **Anonymous**.
4. **Close & Apply**, check the numbers, **Save**.
5. Publish, then in the service: dataset -> Settings -> **Scheduled refresh** (daily is plenty;
   data credentials: Anonymous; privacy level: Public). The key can be rotated there under
   "Parameters" without republishing.

What the new queries also change: `monthly_traffic` only loads rows with a resolved month and
`verified = 1`; `carrier_movements` times are converted to UTC so `Hour` means the same in
Desktop and in the service; `airports` loads only airports with an IATA code (~9k rows instead
of 86k, which would need 86 REST calls per refresh).

> I could not run these queries against the live API (the anon key is not in the repo), so the
> first Desktop refresh is the test. If the REST row cap bites (default 1,000 rows per request),
> raise **Max rows** in Supabase -> Settings -> API and increase `PageSize` in `fnSupabase`.

## Report design (Power BI Project, `VIE-BTS.pbip`)

Open **`VIE-BTS.pbip`** (not the `.pbix`). A Power BI Project stores the report (`VIE-BTS.Report`, PBIR JSON)
and the model (`VIE-BTS.SemanticModel`, TMDL) as plain text, so changes show up as git diffs and can be made
outside Desktop. The `.pbix` is kept only as the previous snapshot.

| Home | Trend | Source |
|---|---|---|
| ![Home](../docs/screenshots/home.png) | ![Trend](../docs/screenshots/trend.png) | ![Source](../docs/screenshots/source.png) |

Why the old report looked dull: each page's *entire layout* (header, title, logo, washed-out panels, faded
airport photo) was ONE 1.4 MB picture used as the page background, with the visuals laid over it. The new
pages are native: solid page colour, white cards with soft shadows, a real header, KPI cards per airport (value,
signed change in red/green, month shown), restyled charts (no linear trend line, no pink "Negative" zone, no
smoothing, linear instead of log axis) and a short accurate "What happened" text instead of the smart-narrative
box that summed percentages ("falling by 727 %").

The old pages are still in the report, renamed "... (old design)" and hidden.

### Generating / changing the pages

The pages are generated, not hand-drawn, so the design is reviewable and repeatable:

```
python PBI/tools/build_trend_page.py     # DAX measures for the report + the Trend page
python PBI/tools/build_info_pages.py     # Home and Source pages (optional arg: page id to open first)
```

Close Desktop first. Both scripts only write text files; every file is valid against Microsoft's PBIR JSON
schemas (checked when they were written). Desktop is the final judge, so after a change open the project
and look.

Lessons from getting it to load (so nobody has to rediscover them):
* **A visual title/subtitle bound to a measure (`title.text = Measure`) makes Desktop fail with "Failed to load
  the report".** Titles are static; dynamic values (month, change) are callouts inside the card.
* Editing the `.pbix` archive from outside Desktop did not work (Desktop rejected two differently rebuilt
  archives as corrupted even though the content was schema-valid); that is why the project uses `.pbip`.
  `tools/patch_report.py` is kept only for reference.
* Windows path length (260 chars) bites when copying the project into deep folders.
* Keep local-only files out of git: `.pbi/cache.abf` (data cache) and `.pbi/localSettings.json`.

Known leftovers: the hidden work-in-progress pages ("BTS Operations (WIP)" references a measure that no longer
exists, `Ryanair Share Trend Check`; "Carrier Analysis (WIP)").
