-- Add extra_query_params column to service_providers table
-- Used to append custom URL query parameters to upstream requests (e.g. {"beta": "true"})

-- For SQLite
ALTER TABLE service_providers ADD COLUMN extra_query_params JSON DEFAULT NULL;

-- For PostgreSQL (uncomment if using PostgreSQL)
-- ALTER TABLE service_providers ADD COLUMN extra_query_params JSONB DEFAULT NULL;
