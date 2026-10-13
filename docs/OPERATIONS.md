# Operations runbook

How the pipeline is scheduled, how to tell when it is unhealthy, and the few manual
steps it needs.

## Jobs

| Workflow | Schedule (UTC) | Writes | Notes |
|---|---|---|---|
| `opensky-capture.yml` | hourly, minute 7 | `carrier_movements` (departures) | **Needs the external trigger below** |
| `opensky-arrivals.yml` | daily 04:45 | `carrier_movements` (arrivals) | whole UTC days today-2, today-3 |
| `opensky-backfill.yml` | daily 03:30 | `carrier_movements.other_airport` | one API call per aircraft-day |
| `scrape.yml` | Mondays 06:00 | `monthly_traffic`, `annual_traffic` | fails if a source returns nothing |
| `healthcheck.yml` | daily 08:15 | nothing | fails when data is stale |
| `tests.yml` | push / PR | nothing | pytest |

Every job has a `timeout-minutes`, a `concurrency` group (no overlapping runs) and
read-only `GITHUB_TOKEN` permissions. All can be started by hand
(Actions -> workflow -> *Run workflow*).

## Capture window (since 13 Oct 2026) and the optional hourly trigger

Each capture run now looks back **12 hours** (`OPENSKY_CAPTURE_MINUTES`), because OpenSky answers windows of up to
about 18 hours (24 hours is refused with 403). So the throttled GitHub cron no longer loses departures, and the
external trigger below is **optional**: it only makes the data fresher, it is not needed for completeness. The
arrivals and backfill jobs stop when fewer than 1000 credits are left (`OPENSKY_CREDIT_RESERVE`) so the capture always
has credits. Departures from before the change (11-13 Oct) are lost: the window cannot reach back further.

## Reliable hourly capture (optional, ~5 minutes)

GitHub's `schedule:` trigger is best-effort. Measured on this repo between
19 Aug and 10 Oct 2026, the "hourly" capture ran about **once every 5 hours**, and
OpenSky only returns the last ~hour of departures, so every skipped run is
departures lost for good. (The health check reports this as *"Departure capture
covers only N% of daytime hours"*.)

Fix: let an external scheduler call `workflow_dispatch` every hour. The cron in the
workflow stays as a harmless fallback; `concurrency` prevents double runs.

1. **Create a token** - GitHub -> Settings -> Developer settings -> Fine-grained
   personal access tokens -> *Generate new token*:
   * Repository access: **Only select repositories** -> `KaStihl/vie-bts-tracker`
   * Permissions -> Repository -> **Actions: Read and write** (nothing else)
   * Expiration: 1 year (put the renewal date in your calendar)
2. **Trigger (recommended): Netlify scheduled function.** It already exists in the blog repo
   (`KaStihl/fkslab-blog`, `netlify/functions/trigger-opensky-capture.mjs`, runs at minute 7).
   Netlify -> Site configuration -> Environment variables -> add `GH_DISPATCH_TOKEN` = the token
   from step 1, then trigger a deploy. Check Netlify -> Logs -> Functions for "opensky-capture dispatched".
   **Alternative:** create a free job at [cron-job.org](https://cron-job.org)**:
   * URL: `https://api.github.com/repos/KaStihl/vie-bts-tracker/actions/workflows/opensky-capture.yml/dispatches`
   * Schedule: every hour at minute 7
   * Request method: `POST`
   * Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
     `X-GitHub-Api-Version: 2022-11-28`
   * Body: `{"ref":"main"}`
   * Success = HTTP **204**. Turn on "notify on failure".
3. Check after a day: Actions -> *Hourly OpenSky capture* should show ~24 runs per day,
   and the next health check should stop warning about coverage.

Alternatives with the same effect: a Cloudflare Worker with a Cron Trigger doing the
same `fetch()` POST, or Supabase `pg_cron` + `pg_net` calling the same URL. Never put
the token in the repository.

## Automatic post drafts (LinkedIn + blog)

After every weekly scrape the workflow runs `python -m scraper.draft_post`. It writes a draft (Slovak and English
LinkedIn text with the newest numbers, a checklist) and opens it as a **GitHub issue labelled `content-draft`**.
It never posts anything. One issue per new release: the title is `Draft post: <Month Year> (BTS | VIE | BTS + VIE)`,
so a second issue appears when the other airport publishes the same month, and reruns do not duplicate.

Workflow: open the issue -> replace the `[...]` placeholders and add your own comment -> check each number against
the linked release -> publish the report -> post on LinkedIn (link in the first comment) -> close the issue.
The content plan and longer drafts live on branch `content-drafts` (`docs/content-plan/`).

Next step (not built): post the approved text automatically through the LinkedIn API or Buffer. The LinkedIn token
lasts about 60 days and has to be created by the account owner; keep the approval step.

## Supabase

* Scrapers connect with `SUPABASE_CONNECTION_STRING` (the `postgres` role, bypasses RLS).
* Power BI reads through the REST API with the **anon** key under the read-only RLS
  policies in `scraper/supabase_public_read.sql` (run once). The anon key is public
  by design; the policies are what protect the data. Do not commit it anyway - it is
  stored as a Power Query parameter, see `PBI/README.md`.
* `scraper/migrations/001_cleanup_monthly_traffic.sql` removes the phantom cumulative
  rows the old BTS parser stored and adds a unique index so they cannot pile up again.
  Run it once in the SQL Editor (it starts with a read-only `SELECT` so you can
  review).
* In the Supabase dashboard run **Advisors -> Security** once and confirm there are
  no "RLS disabled" warnings for public tables.

## When something is red

| Symptom | Likely cause | Action |
|---|---|---|
| `Data health check` fails: departures stale | external trigger stopped / token expired | check cron-job.org, renew token |
| `... covers only N% of daytime hours` (warning) | still relying on GitHub's cron | do the setup above |
| `Weekly traffic scrape` fails: "returned 0 ..." | an airport changed its page | run `python -m scraper.vie_scraper` / `bts_scraper` locally, adjust regex, add a test |
| Backfill/arrivals log "daily credit budget exhausted" | OpenSky credits used up | harmless; resumes next day. Lower `max_calls` if frequent |
| Power BI shows old "Last refresh" | scheduled refresh failing | see `PBI/README.md` |

## Local development

```bash
python -m venv venv && venv/Scripts/activate      # keep the venv OUT of OneDrive if you can
pip install -r requirements-dev.txt
python -m pytest -q
```

Note: bts.aero sits behind Cloudflare and challenges generic user agents; the
scrapers send `FKsLabBot/1.0 (+https://fkslab.com)` (see `scraper/http_util.py`),
which is accepted. Don't change it without testing both airport sites.
(https://cron-job.org)**:
   * URL: `https://api.github.com/repos/KaStihl/vie-bts-tracker/actions/workflows/opensky-capture.yml/dispatches`
   * Schedule: every hour at minute 7
   * Request method: `POST`
   * Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
     `X-GitHub-Api-Version: 2022-11-28`
   * Body: `{"ref":"main"}`
   * Success = HTTP **204**. Turn on "notify on failure".
3. Check after a day: Actions -> *Hourly OpenSky capture* should show ~24 runs per day,
   and the next health check should stop warning about coverage.

Alternatives with the same effect: a Cloudflare Worker with a Cron Trigger doing the
same `fetch()` POST, or Supabase `pg_cron` + `pg_net` calling the same URL. Never put
the token in the repository.

## Supabase

* Scrapers connect with `SUPABASE_CONNECTION_STRING` (the `postgres` role, bypasses RLS).
* Power BI reads through the REST API with the **anon** key under the read-only RLS
  policies in `scraper/supabase_public_read.sql` (run once). The anon key is public
  by design; the policies are what protect the data. Do not commit it anyway - it is
  stored as a Power Query parameter, see `PBI/README.md`.
* `scraper/migrations/001_cleanup_monthly_traffic.sql` removes the phantom cumulative
  rows the old BTS parser stored and adds a unique index so they cannot pile up again.
  Run it once in the SQL Editor (it starts with a read-only `SELECT` so you can
  review).
* In the Supabase dashboard run **Advisors -> Security** once and confirm there are
  no "RLS disabled" warnings for public tables.

## When something is red

| Symptom | Likely cause | Action |
|---|---|---|
| `Data health check` fails: departures stale | external trigger stopped / token expired | check cron-job.org, renew token |
| `... covers only N% of daytime hours` (warning) | still relying on GitHub's cron | do the setup above |
| `Weekly traffic scrape` fails: "returned 0 ..." | an airport changed its page | run `python -m scraper.vie_scraper` / `bts_scraper` locally, adjust regex, add a test |
| Backfill/arrivals log "daily credit budget exhausted" | OpenSky credits used up | harmless; resumes next day. Lower `max_calls` if frequent |
| Power BI shows old "Last refresh" | scheduled refresh failing | see `PBI/README.md` |

## Local development

```bash
python -m venv venv && venv/Scripts/activate      # keep the venv OUT of OneDrive if you can
pip install -r requirements-dev.txt
python -m pytest -q
```

Note: bts.aero sits behind Cloudflare and challenges generic user agents; the
scrapers send `FKsLabBot/1.0 (+https://fkslab.com)` (see `scraper/http_util.py`),
which is accepted. Don't change it without testing both airport sites.
