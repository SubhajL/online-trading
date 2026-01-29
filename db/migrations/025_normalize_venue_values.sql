-- 025_normalize_venue_values.sql: Normalize venue strings to canonical values
--
-- Canonical venue values across this system are:
-- - SPOT
-- - USD_M
--
-- Historical rows written by earlier router/engine code used 'spot'/'futures'.
-- Normalize those to keep risk/exposure queries consistent.

UPDATE balances SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE balances SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE candles SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE candles SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE indicators SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE indicators SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE swings SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE swings SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE smc_events SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE smc_events SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE zones SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE zones SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE orders SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE orders SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE positions SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE positions SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE fills SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE fills SET venue = 'USD_M' WHERE venue = 'futures';

UPDATE trading_decisions SET venue = 'SPOT' WHERE venue = 'spot';
UPDATE trading_decisions SET venue = 'USD_M' WHERE venue = 'futures';
