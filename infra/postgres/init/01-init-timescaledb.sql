-- Enable TimescaleDB extension
-- This must be run as superuser and will enable TimescaleDB for the current database
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Show TimescaleDB version info
SELECT default_version, installed_version FROM pg_available_extensions WHERE name = 'timescaledb';

-- Grant necessary permissions
GRANT CREATE ON SCHEMA public TO trading_user;
GRANT USAGE ON SCHEMA public TO trading_user;