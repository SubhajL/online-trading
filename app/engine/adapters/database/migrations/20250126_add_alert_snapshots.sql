-- Migration: Add alert_snapshots table for storing chart images
-- Created: 2025-01-26

CREATE TABLE IF NOT EXISTS alert_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id VARCHAR(255) NOT NULL UNIQUE,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    image_path TEXT NOT NULL,
    meta JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for quick lookups by signal_id
CREATE INDEX idx_alert_snapshots_signal_id ON alert_snapshots(signal_id);

-- Index for cleanup queries
CREATE INDEX idx_alert_snapshots_created_at ON alert_snapshots(created_at);

COMMENT ON TABLE alert_snapshots IS 'Stores chart snapshot images for trading signals';
COMMENT ON COLUMN alert_snapshots.signal_id IS 'Unique identifier from the trading engine';
COMMENT ON COLUMN alert_snapshots.image_path IS 'Local filesystem path to PNG image';
COMMENT ON COLUMN alert_snapshots.meta IS 'JSON metadata including entry, SL, TP, reasons';