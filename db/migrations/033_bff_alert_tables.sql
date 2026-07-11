-- BFF-owned TypeORM tables that no migration created (synchronize=false, so
-- they only ever existed in dev DBs from an old schema-sync run). A fresh DB
-- crashed the BFF on the first live decision event: INSERT INTO "alerts"
-- failed with 42P01. Column names/quoting match the TypeORM entities exactly
-- (app/bff/src/alerts/entities/alert.entity.ts,
--  app/bff/src/database/entities/alert-snapshot.entity.ts).

DO $$ BEGIN
    CREATE TYPE alerts_type_enum AS ENUM ('order', 'position', 'decision', 'smc', 'error', 'info');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE alerts_priority_enum AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS alerts (
    "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "type" alerts_type_enum NOT NULL,
    "priority" alerts_priority_enum NOT NULL,
    "title" CHARACTER VARYING NOT NULL,
    "message" TEXT NOT NULL,
    "data" JSONB,
    "read" BOOLEAN NOT NULL DEFAULT FALSE,
    "createdAt" TIMESTAMP NOT NULL DEFAULT NOW(),
    "updatedAt" TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts ("createdAt" DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_read ON alerts ("read") WHERE "read" = FALSE;

CREATE TABLE IF NOT EXISTS alert_snapshots (
    "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "signal_id" CHARACTER VARYING NOT NULL UNIQUE,
    "symbol" CHARACTER VARYING NOT NULL,
    "timeframe" CHARACTER VARYING NOT NULL,
    "image_path" CHARACTER VARYING NOT NULL,
    "meta" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alert_snapshots_created_at ON alert_snapshots ("created_at" DESC);
