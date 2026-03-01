-- 028_equity_samples_source_timestamp.sql: Track upstream timestamps for equity samples

ALTER TABLE equity_samples
    ADD COLUMN IF NOT EXISTS source_timestamp TIMESTAMPTZ;
