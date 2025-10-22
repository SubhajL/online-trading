Migrations — Contiguous-To-First-Gap

- Canonical strategy: only apply the longest contiguous sequence starting at `current_version + 1` and stop at the first gap. Missing historical files are ignored once the DB is ahead — no backfills or errors by default.
- Bootstrap: version `0` (`000_migration_version.sql`) is created automatically when `current_version == 0`.
- Deterministic: Files are applied in order; gaps do not break deploys once you’ve advanced beyond them.

Practical notes
- Add new files with the next integer version. Do not attempt to backfill old, missing versions if production is already past that point.
- If you must repair history for a new environment, create a new top-of-head repair migration, not a historical insert.

Testing
- Unit tests assert the planner returns `[start, start+1, ...]` up to the first gap.
- Integration tests should exercise applying a contiguous set on a fresh database and verify final version.

