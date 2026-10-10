-- Read-only public access for Power BI via the Supabase REST API.
--
-- Why: the Power BI cloud service cannot validate Supabase's private CA
-- ("Supabase Root 2021 CA") when connecting to Postgres directly, so scheduled
-- refresh fails. The REST API (https://<ref>.supabase.co/rest/v1/...) uses a
-- publicly trusted certificate, so Power BI reads the data through it instead.
--
-- Run once in the Supabase SQL Editor.
--
-- Safety notes
--   * Only SELECT is granted to the anon role, only on the four tables below.
--   * The scrapers connect with SUPABASE_CONNECTION_STRING as the `postgres`
--     role, which bypasses RLS, so enabling RLS does not affect them.
--   * Everything exposed here is already public (official press releases,
--     aircraft movements, reference airport list).

alter table public.monthly_traffic   enable row level security;
alter table public.annual_traffic    enable row level security;
alter table public.carrier_movements enable row level security;
alter table public.airports          enable row level security;

drop policy if exists "public read monthly_traffic"   on public.monthly_traffic;
drop policy if exists "public read annual_traffic"    on public.annual_traffic;
drop policy if exists "public read carrier_movements" on public.carrier_movements;
drop policy if exists "public read airports"          on public.airports;

create policy "public read monthly_traffic"   on public.monthly_traffic   for select to anon using (true);
create policy "public read annual_traffic"    on public.annual_traffic    for select to anon using (true);
create policy "public read carrier_movements" on public.carrier_movements for select to anon using (true);
create policy "public read airports"          on public.airports          for select to anon using (true);

-- Belt and braces: make sure anon/authenticated can never write these tables.
revoke insert, update, delete, truncate on
  public.monthly_traffic, public.annual_traffic,
  public.carrier_movements, public.airports
from anon, authenticated;

-- Optional (Supabase Dashboard -> Project Settings -> API -> "Max rows"):
-- raise it from 1000 to e.g. 50000 to make large tables load with fewer requests.
