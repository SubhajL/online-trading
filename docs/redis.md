Redis — REDIS_URL and Preflight

Configuration
- Prefer a single URL in env: `REDIS_URL` (supports `redis://` and `rediss://`).
- TLS examples (Upstash): `REDIS_URL=rediss://default:<TOKEN>@<HOST>:6379/0`.
- Local dev: `REDIS_URL=redis://localhost:6379/0`.

Preflight
- `preflight.check_redis_connectivity()` prefers `REDIS_URL` and pings via `redis.from_url(...)`.
- Falls back to `REDIS_HOST`/`REDIS_PORT` only if `REDIS_URL` is absent.

Testing
- Unit (no network): `pytest -q app/engine/tests/unit/test_preflight_redis.py -m "not redis"`.
- Integration (requires running Redis): `pytest -q app/engine/tests/unit/test_preflight_redis.py -m redis`.
- The `redis` marker is defined in `app/engine/pytest.ini`.

