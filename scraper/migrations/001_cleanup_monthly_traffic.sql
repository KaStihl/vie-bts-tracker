-- One-off cleanup + guard for monthly_traffic. Run once in the Supabase SQL Editor.
-- Review the SELECTs first; every statement is idempotent.
--
-- Background: the old BTS parser stored cumulative figures as if they were monthly
-- candidates (month NULL, verified 0). With month NULL the dashboard's
-- DATE(year, month, 1) landed them in December of the previous year and drew
-- phantom spikes (e.g. 273,807 = Q1-2025 total, 1,948,008 = 2024 annual total).

-- 0. What is currently unresolved?
SELECT id, airport_code, year, month, passengers, yoy_change_pct, verified, left(raw_text, 90) AS raw
FROM monthly_traffic
WHERE month IS NULL OR verified = 0
ORDER BY airport_code, year, passengers;

-- 1. Remove the known phantom cumulative rows.
DELETE FROM monthly_traffic
WHERE airport_code = 'BTS'
  AND month IS NULL
  AND verified = 0
  AND passengers IN (273807, 1948008);

-- 2. Remove duplicate unresolved candidates (keep the oldest of each).
DELETE FROM monthly_traffic a
USING monthly_traffic b
WHERE a.month IS NULL AND b.month IS NULL
  AND a.airport_code = b.airport_code
  AND a.passengers = b.passengers
  AND a.id > b.id;

-- 3. Stop unresolved candidates from piling up again (NULLs are distinct in a
--    plain UNIQUE constraint, so it cannot do this).
CREATE UNIQUE INDEX IF NOT EXISTS monthly_traffic_unresolved_uniq
    ON monthly_traffic (airport_code, year, passengers)
    WHERE month IS NULL;

-- 4. Optional, manual: the 16 Sep 2025 BTS release names several months
--    ("In May, June, July, and now also in August ...") so it cannot be resolved
--    automatically, but the 355,658 figure is August 2025 (August 2026 was
--    625,742 = +76 %  ->  625,742 / 1.76 = 355,535, consistent).
-- UPDATE monthly_traffic
--    SET month = 8, verified = 1
--  WHERE airport_code = 'BTS' AND year = 2025 AND passengers = 355658 AND month IS NULL;
