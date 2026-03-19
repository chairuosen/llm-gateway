-- Migration: Add daily/weekly/monthly spending limits to api_keys table
-- Date: 2026-03-19

ALTER TABLE api_keys ADD COLUMN daily_cost_limit NUMERIC(10, 6) NULL;
ALTER TABLE api_keys ADD COLUMN weekly_cost_limit NUMERIC(10, 6) NULL;
ALTER TABLE api_keys ADD COLUMN monthly_cost_limit NUMERIC(10, 6) NULL;
