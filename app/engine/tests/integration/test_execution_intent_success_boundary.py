from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import asyncpg
from fastapi import HTTPException
import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.main import (
    _order_update_db_hydration_enabled_from_env,
    ingest_order_update,
    services,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.engine.tests.integration.db_config import TestDatabaseConfig


@asynccontextmanager
async def _initialized_adapter(
    config: TestDatabaseConfig,
) -> AsyncIterator[TimescaleDBAdapter]:
    adapter = TimescaleDBAdapter(
        host=config.host,
        port=config.port,
        database=config.database,
        username=config.username,
        password=config.password,
    )
    await adapter.initialize()
    try:
        yield adapter
    finally:
        await adapter.close()


async def _connect(config: TestDatabaseConfig) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=config.host,
        port=config.port,
        user=config.username,
        password=config.password,
        database=config.database,
    )


class _AcknowledgingBus:
    async def publish_and_wait(self, event: object, priority: int = 0) -> bool:
        _ = (event, priority)
        return True


async def _seed_submitting_intent(
    conn: asyncpg.Connection,
    *,
    venue: str,
    idempotency_key: str,
    state: str = "SUBMITTING",
) -> None:
    await conn.execute(
        """
        INSERT INTO execution_intents (
            idempotency_key,
            decision_id,
            signal_id,
            venue,
            symbol,
            request_hash,
            request_payload,
            state
        ) VALUES ($1, $2, $3, $4, 'BTCUSDT', $5, '{}'::jsonb, $6)
        """,
        idempotency_key,
        uuid4(),
        f"signal-{idempotency_key}",
        venue,
        "a" * 64,
        state,
    )


def _order_row(*, venue: str, client_order_id: str, side: str = "BUY") -> dict[str, object]:
    return {
        "client_order_id": client_order_id,
        "venue": venue,
        "symbol": "BTCUSDT",
        "side": side,
        "type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "status": "NEW",
    }


@pytest.mark.asyncio
async def test_ack_commit_rolls_back_all_projection_rows_when_any_leg_fails(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"ack-rollback-{uuid4()}"
    valid_client_order_id = f"valid-{uuid4()}"
    invalid_client_order_id = f"invalid-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            with pytest.raises(asyncpg.CheckViolationError):
                await adapter.commit_execution_ack(
                    idempotency_key,
                    venue=venue,
                    response_payload={"bracket_order_id": "bracket-rollback"},
                    order_rows=[
                        _order_row(
                            venue=venue,
                            client_order_id=valid_client_order_id,
                        ),
                        _order_row(
                            venue=venue,
                            client_order_id=invalid_client_order_id,
                            side="HOLD",
                        ),
                    ],
                    deliveries=[
                        {
                            "delivery_kind": "SNAPSHOT",
                            "delivery_payload": {"signalId": idempotency_key},
                        },
                        {
                            "delivery_kind": "ORDER_PLACED",
                            "delivery_payload": {"event_type": "order_placed"},
                        },
                    ],
                )

        rows = await conn.fetch(
            """
            SELECT client_order_id
            FROM orders
            WHERE venue = $1 AND client_order_id = ANY($2::text[])
            """,
            venue,
            [valid_client_order_id, invalid_client_order_id],
        )
        intent = await conn.fetchrow(
            """
            SELECT state, response_payload
            FROM execution_intents
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )
        deliveries = await conn.fetch(
            """
            SELECT delivery_kind
            FROM execution_success_deliveries
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )

        assert rows == []
        assert dict(intent) == {"state": "SUBMITTING", "response_payload": None}
        assert deliveries == []
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = ANY($2::text[])",
            venue,
            [valid_client_order_id, invalid_client_order_id],
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_ack_commit_persists_orders_ack_and_deliveries_atomically(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"ack-success-{uuid4()}"
    client_order_ids = [f"entry-{uuid4()}", f"tp-{uuid4()}"]
    response_payload = {"bracket_order_id": "bracket-success"}
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            assert await adapter.commit_execution_ack(
                idempotency_key,
                venue=venue,
                response_payload=response_payload,
                order_rows=[
                    _order_row(venue=venue, client_order_id=client_order_ids[0]),
                    _order_row(venue=venue, client_order_id=client_order_ids[1]),
                ],
                deliveries=[
                    {
                        "delivery_kind": "SNAPSHOT",
                        "delivery_payload": {"signalId": idempotency_key},
                    },
                    {
                        "delivery_kind": "ORDER_PLACED",
                        "delivery_payload": {"event_type": "order_placed"},
                    },
                ],
            )

        orders = await conn.fetch(
            """
            SELECT client_order_id
            FROM orders
            WHERE venue = $1 AND client_order_id = ANY($2::text[])
            ORDER BY client_order_id
            """,
            venue,
            client_order_ids,
        )
        intent = await conn.fetchrow(
            """
            SELECT state, response_payload
            FROM execution_intents
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )
        deliveries = await conn.fetch(
            """
            SELECT delivery_kind, state
            FROM execution_success_deliveries
            WHERE venue = $1 AND idempotency_key = $2
            ORDER BY delivery_kind
            """,
            venue,
            idempotency_key,
        )

        assert [row["client_order_id"] for row in orders] == sorted(client_order_ids)
        assert intent["state"] == "ACKNOWLEDGED"
        assert json.loads(intent["response_payload"]) == response_payload
        assert [dict(row) for row in deliveries] == [
            {"delivery_kind": "ORDER_PLACED", "state": "PENDING"},
            {"delivery_kind": "SNAPSHOT", "state": "PENDING"},
        ]
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = ANY($2::text[])",
            venue,
            client_order_ids,
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_concurrent_delivery_claim_has_one_winner(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"delivery-race-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
            state="ACKNOWLEDGED",
        )
        await conn.execute(
            """
            INSERT INTO execution_success_deliveries (
                venue, idempotency_key, delivery_kind, state, delivery_payload
            ) VALUES ($1, $2, 'ORDER_PLACED', 'PENDING', '{"event_type":"order_placed"}'::jsonb)
            """,
            venue,
            idempotency_key,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            claims = await asyncio.gather(
                adapter.claim_execution_success_delivery(
                    idempotency_key,
                    venue=venue,
                ),
                adapter.claim_execution_success_delivery(
                    idempotency_key,
                    venue=venue,
                ),
            )

        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0]["delivery_kind"] == "ORDER_PLACED"
        assert isinstance(winners[0]["lease_token"], str)
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_concurrent_incomplete_intent_recovery_claim_has_one_lease_winner(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"intent-recovery-race-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
            state="AMBIGUOUS",
        )
        await conn.execute(
            """
            UPDATE execution_intents
            SET updated_at = NOW() - INTERVAL '5 minutes'
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            claims = await asyncio.gather(
                adapter.claim_next_execution_intent_recovery(venue=venue),
                adapter.claim_next_execution_intent_recovery(venue=venue),
            )

        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0]["idempotency_key"] == idempotency_key
        assert winners[0]["state"] == "AMBIGUOUS"
        assert isinstance(winners[0]["request_payload"], dict)

        row = await conn.fetchrow(
            """
            SELECT recovery_attempts, recovery_lease_expires_at
            FROM execution_intents
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )
        assert row["recovery_attempts"] == 1
        assert row["recovery_lease_expires_at"] > datetime.now(UTC)
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_incomplete_intent_outside_active_venue_blocks_until_resolved(
    test_database_config: TestDatabaseConfig,
) -> None:
    inactive_venue = "SPOT"
    active_venue = "USD_M"
    idempotency_key = f"inactive-venue-intent-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=inactive_venue,
            idempotency_key=idempotency_key,
            state="AMBIGUOUS",
        )

        async with _initialized_adapter(test_database_config) as adapter:
            assert await adapter.has_incomplete_execution_intent_outside_venue(active_venue)

            await conn.execute(
                """
                UPDATE execution_intents
                SET state = 'REJECTED'
                WHERE venue = $1 AND idempotency_key = $2
                """,
                inactive_venue,
                idempotency_key,
            )

            assert not await adapter.has_incomplete_execution_intent_outside_venue(active_venue)
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            inactive_venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_expired_delivery_lease_is_reclaimable(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"delivery-expired-{uuid4()}"
    expired_lease = "expired-lease"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
            state="ACKNOWLEDGED",
        )
        await conn.execute(
            """
            INSERT INTO execution_success_deliveries (
                venue,
                idempotency_key,
                delivery_kind,
                state,
                attempts,
                lease_token,
                lease_expires_at,
                delivery_payload
            ) VALUES (
                $1, $2, 'ORDER_PLACED', 'DELIVERING', 1, $3, $4,
                '{"event_type":"order_placed"}'::jsonb
            )
            """,
            venue,
            idempotency_key,
            expired_lease,
            datetime.now(UTC) - timedelta(seconds=1),
        )

        async with _initialized_adapter(test_database_config) as adapter:
            claim = await adapter.claim_execution_success_delivery(
                idempotency_key,
                venue=venue,
            )

        row = await conn.fetchrow(
            """
            SELECT state, attempts, lease_token, lease_expires_at
            FROM execution_success_deliveries
            WHERE venue = $1 AND idempotency_key = $2 AND delivery_kind = 'ORDER_PLACED'
            """,
            venue,
            idempotency_key,
        )
        assert claim is not None
        assert claim["delivery_kind"] == "ORDER_PLACED"
        assert claim["lease_token"] != expired_lease
        assert dict(row) == {
            "state": "DELIVERING",
            "attempts": 2,
            "lease_token": claim["lease_token"],
            "lease_expires_at": row["lease_expires_at"],
        }
        assert row["lease_expires_at"] > datetime.now(UTC)
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_stale_delivery_lease_cannot_complete_reclaimed_work(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"delivery-stale-{uuid4()}"
    stale_lease = "stale-lease"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
            state="ACKNOWLEDGED",
        )
        await conn.execute(
            """
            INSERT INTO execution_success_deliveries (
                venue,
                idempotency_key,
                delivery_kind,
                state,
                attempts,
                lease_token,
                lease_expires_at,
                delivery_payload
            ) VALUES (
                $1, $2, 'ORDER_PLACED', 'DELIVERING', 1, $3, $4,
                '{"event_type":"order_placed"}'::jsonb
            )
            """,
            venue,
            idempotency_key,
            stale_lease,
            datetime.now(UTC) - timedelta(seconds=1),
        )

        async with _initialized_adapter(test_database_config) as adapter:
            claim = await adapter.claim_execution_success_delivery(
                idempotency_key,
                venue=venue,
            )
            assert claim is not None
            active_lease = claim["lease_token"]
            assert isinstance(active_lease, str)
            assert active_lease != stale_lease

            with pytest.raises(RuntimeError, match="lease"):
                await adapter.complete_execution_success_delivery(
                    idempotency_key,
                    venue=venue,
                    delivery_kind="ORDER_PLACED",
                    lease_token=stale_lease,
                )

            row = await conn.fetchrow(
                """
                SELECT state, lease_token, delivered_at
                FROM execution_success_deliveries
                WHERE venue = $1
                  AND idempotency_key = $2
                  AND delivery_kind = 'ORDER_PLACED'
                """,
                venue,
                idempotency_key,
            )
            assert dict(row) == {
                "state": "DELIVERING",
                "lease_token": active_lease,
                "delivered_at": None,
            }

            await adapter.complete_execution_success_delivery(
                idempotency_key,
                venue=venue,
                delivery_kind="ORDER_PLACED",
                lease_token=active_lease,
            )

        row = await conn.fetchrow(
            """
            SELECT state, lease_token, delivered_at
            FROM execution_success_deliveries
            WHERE venue = $1
              AND idempotency_key = $2
              AND delivery_kind = 'ORDER_PLACED'
            """,
            venue,
            idempotency_key,
        )
        assert row["state"] == "DELIVERED"
        assert row["lease_token"] is None
        assert row["delivered_at"] is not None
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_ack_commit_rejects_divergent_existing_order_identity(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"ack-conflict-{uuid4()}"
    client_order_id = f"conflict-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
        )
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type,
                quantity, price, status, created_at
            ) VALUES ($1, $2, 'ETHUSDT', 'SELL', 'LIMIT', 0.002, 4000, 'NEW', NOW())
            """,
            client_order_id,
            venue,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            with pytest.raises(RuntimeError, match="identity"):
                await adapter.commit_execution_ack(
                    idempotency_key,
                    venue=venue,
                    response_payload={"bracket_order_id": "bracket-conflict"},
                    order_rows=[
                        _order_row(
                            venue=venue,
                            client_order_id=client_order_id,
                        ),
                    ],
                    deliveries=[
                        {
                            "delivery_kind": "ORDER_PLACED",
                            "delivery_payload": {"event_type": "order_placed"},
                        },
                    ],
                )

        order = await conn.fetchrow(
            """
            SELECT symbol, side, type, quantity, price
            FROM orders
            WHERE venue = $1 AND client_order_id = $2
            """,
            venue,
            client_order_id,
        )
        intent = await conn.fetchrow(
            """
            SELECT state, response_payload
            FROM execution_intents
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )
        deliveries = await conn.fetch(
            """
            SELECT delivery_kind
            FROM execution_success_deliveries
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )

        assert dict(order) == {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "LIMIT",
            "quantity": Decimal("0.00200000"),
            "price": Decimal("4000.00000000"),
        }
        assert dict(intent) == {"state": "SUBMITTING", "response_payload": None}
        assert deliveries == []
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_migration_036_backfills_legacy_acknowledgements_and_is_rerunnable(
    test_database_config: TestDatabaseConfig,
) -> None:
    migration_sql = (
        Path(__file__).parents[4] / "db/migrations/036_execution_success_delivery.sql"
    ).read_text()
    acknowledged_key = f"legacy-ack-{uuid4()}"
    prepared_key = f"legacy-prepared-{uuid4()}"
    conn = await _connect(test_database_config)
    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute("DROP TABLE execution_success_deliveries")
        await _seed_submitting_intent(
            conn,
            venue="SPOT",
            idempotency_key=acknowledged_key,
            state="ACKNOWLEDGED",
        )
        await _seed_submitting_intent(
            conn,
            venue="USD_M",
            idempotency_key=prepared_key,
            state="PREPARED",
        )

        await conn.execute(migration_sql)
        await conn.execute(migration_sql)

        rows = await conn.fetch(
            """
            SELECT venue, idempotency_key, delivery_kind, state, attempts, delivery_payload
            FROM execution_success_deliveries
            WHERE idempotency_key = ANY($1::text[])
            ORDER BY venue, idempotency_key, delivery_kind
            """,
            [acknowledged_key, prepared_key],
        )
        assert [dict(row) for row in rows] == [
            {
                "venue": "SPOT",
                "idempotency_key": acknowledged_key,
                "delivery_kind": "ORDER_PLACED",
                "state": "DELIVERED",
                "attempts": 0,
                "delivery_payload": None,
            },
        ]
    finally:
        await transaction.rollback()
        await conn.close()


@pytest.mark.asyncio
async def test_failed_oldest_delivery_is_deferred_so_another_key_can_progress(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    poison_key = f"delivery-poison-{uuid4()}"
    healthy_key = f"delivery-healthy-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=poison_key,
            state="ACKNOWLEDGED",
        )
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=healthy_key,
            state="ACKNOWLEDGED",
        )
        await conn.execute(
            """
            INSERT INTO execution_success_deliveries (
                venue, idempotency_key, delivery_kind, state,
                delivery_payload, created_at, next_attempt_at
            ) VALUES
                ($1, $2, 'SNAPSHOT', 'PENDING', '{}'::jsonb, NOW() - INTERVAL '2 minutes', NOW()),
                ($1, $3, 'ORDER_PLACED', 'PENDING', '{}'::jsonb, NOW() - INTERVAL '1 minute', NOW())
            """,
            venue,
            poison_key,
            healthy_key,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            poison_claim = await adapter.claim_next_execution_success_delivery(venue=venue)
            assert poison_claim is not None
            assert poison_claim["idempotency_key"] == poison_key
            await adapter.fail_execution_success_delivery(
                poison_key,
                venue=venue,
                delivery_kind="SNAPSHOT",
                lease_token=poison_claim["lease_token"],
                error_message="permanent BFF failure",
            )

            poison_retry = await conn.fetchrow(
                """
                SELECT attempts, next_attempt_at, updated_at
                FROM execution_success_deliveries
                WHERE venue = $1 AND idempotency_key = $2 AND delivery_kind = 'SNAPSHOT'
                """,
                venue,
                poison_key,
            )
            assert poison_retry["attempts"] == 1
            assert poison_retry["next_attempt_at"] > poison_retry["updated_at"]

            healthy_claim = await adapter.claim_next_execution_success_delivery(venue=venue)
            assert healthy_claim is not None
            assert healthy_claim["idempotency_key"] == healthy_key
            assert healthy_claim["delivery_kind"] == "ORDER_PLACED"
            await adapter.complete_execution_success_delivery(
                healthy_key,
                venue=venue,
                delivery_kind="ORDER_PLACED",
                lease_token=healthy_claim["lease_token"],
            )

            await conn.execute(
                """
                UPDATE execution_success_deliveries
                SET next_attempt_at = NOW() - INTERVAL '1 second'
                WHERE venue = $1 AND idempotency_key = $2 AND delivery_kind = 'SNAPSHOT'
                """,
                venue,
                poison_key,
            )
            second_claim = await adapter.claim_next_execution_success_delivery(venue=venue)
            assert second_claim is not None
            assert second_claim["idempotency_key"] == poison_key
            await adapter.fail_execution_success_delivery(
                poison_key,
                venue=venue,
                delivery_kind="SNAPSHOT",
                lease_token=second_claim["lease_token"],
                error_message="permanent BFF failure",
            )
            second_retry = await conn.fetchrow(
                """
                SELECT attempts, next_attempt_at - updated_at AS retry_delay
                FROM execution_success_deliveries
                WHERE venue = $1 AND idempotency_key = $2 AND delivery_kind = 'SNAPSHOT'
                """,
                venue,
                poison_key,
            )
            assert second_retry["attempts"] == 2
            assert second_retry["retry_delay"] > timedelta(seconds=1.5)
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = ANY($2::text[])",
            venue,
            [poison_key, healthy_key],
        )
        await conn.close()


@pytest.mark.asyncio
async def test_ack_adoption_enriches_missing_setup_provenance(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"ack-provenance-{uuid4()}"
    client_order_id = f"provenance-{uuid4()}"
    decision_id = uuid4()
    zone = {"zone_id": "zone-new", "zone_type": "ORDER_BLOCK"}
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(conn, venue=venue, idempotency_key=idempotency_key)
        await conn.execute(
            """
            INSERT INTO trading_decisions (
                decision_id, timestamp, symbol, action, confidence, reasoning, venue
            ) VALUES ($1, NOW(), 'BTCUSDT', 'BUY', 0.8, 'provenance fixture', $2)
            """,
            decision_id,
            venue,
        )
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type,
                quantity, price, status, created_at
            ) VALUES ($1, $2, 'BTCUSDT', 'BUY', 'LIMIT', 0.001, 50000, 'NEW', NOW())
            """,
            client_order_id,
            venue,
        )
        incoming = _order_row(venue=venue, client_order_id=client_order_id)
        incoming.update(
            decision_id=str(decision_id),
            signal_id=idempotency_key,
            timeframe="15m",
            zone=zone,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            assert await adapter.commit_execution_ack(
                idempotency_key,
                venue=venue,
                response_payload={"bracket_order_id": "bracket-provenance"},
                order_rows=[incoming],
                deliveries=[
                    {
                        "delivery_kind": "ORDER_PLACED",
                        "delivery_payload": {"event_type": "order_placed"},
                    },
                ],
            )

        row = await conn.fetchrow(
            """
            SELECT decision_id, signal_id, timeframe, zone
            FROM orders WHERE venue = $1 AND client_order_id = $2
            """,
            venue,
            client_order_id,
        )
        assert row["decision_id"] == decision_id
        assert row["signal_id"] == idempotency_key
        assert row["timeframe"] == "15m"
        assert json.loads(row["zone"]) == zone
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.execute(
            "DELETE FROM trading_decisions WHERE decision_id = $1",
            decision_id,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_ack_adoption_rejects_conflicting_setup_provenance(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"ack-provenance-conflict-{uuid4()}"
    client_order_id = f"provenance-conflict-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(conn, venue=venue, idempotency_key=idempotency_key)
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type,
                quantity, price, status, created_at, timeframe, zone
            ) VALUES (
                $1, $2, 'BTCUSDT', 'BUY', 'LIMIT', 0.001, 50000, 'NEW', NOW(),
                '5m', '{"zone_id":"zone-old","zone_type":"ORDER_BLOCK"}'::jsonb
            )
            """,
            client_order_id,
            venue,
        )
        incoming = _order_row(venue=venue, client_order_id=client_order_id)
        incoming.update(
            timeframe="15m",
            zone={"zone_id": "zone-new", "zone_type": "ORDER_BLOCK"},
        )

        async with _initialized_adapter(test_database_config) as adapter:
            with pytest.raises(RuntimeError, match="identity"):
                await adapter.commit_execution_ack(
                    idempotency_key,
                    venue=venue,
                    response_payload={"bracket_order_id": "bracket-provenance-conflict"},
                    order_rows=[incoming],
                    deliveries=[
                        {
                            "delivery_kind": "ORDER_PLACED",
                            "delivery_payload": {"event_type": "order_placed"},
                        },
                    ],
                )

        intent_state = await conn.fetchval(
            """
            SELECT state FROM execution_intents
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
        )
        assert intent_state == "SUBMITTING"
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_concurrent_global_claims_preserve_snapshot_dependency_and_progress(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    dependent_key = f"delivery-dependent-{uuid4()}"
    unrelated_key = f"delivery-unrelated-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=dependent_key,
            state="ACKNOWLEDGED",
        )
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=unrelated_key,
            state="ACKNOWLEDGED",
        )
        await conn.execute(
            """
            INSERT INTO execution_success_deliveries (
                venue, idempotency_key, delivery_kind, state,
                delivery_payload, next_attempt_at, created_at
            ) VALUES
                ($1, $2, 'SNAPSHOT', 'PENDING', '{}'::jsonb, NOW(), NOW()),
                ($1, $2, 'ORDER_PLACED', 'PENDING', '{}'::jsonb, NOW(), NOW()),
                ($1, $3, 'ORDER_PLACED', 'PENDING', '{}'::jsonb, NOW(), NOW())
            """,
            venue,
            dependent_key,
            unrelated_key,
        )

        async with _initialized_adapter(test_database_config) as adapter:
            claims = await asyncio.gather(
                adapter.claim_next_execution_success_delivery(venue=venue),
                adapter.claim_next_execution_success_delivery(venue=venue),
                adapter.claim_next_execution_success_delivery(venue=venue),
            )
            claimed = [claim for claim in claims if claim is not None]
            assert {(claim["idempotency_key"], claim["delivery_kind"]) for claim in claimed} == {
                (dependent_key, "SNAPSHOT"),
                (unrelated_key, "ORDER_PLACED"),
            }

            dependent_snapshot = next(
                claim for claim in claimed if claim["idempotency_key"] == dependent_key
            )
            await adapter.complete_execution_success_delivery(
                dependent_key,
                venue=venue,
                delivery_kind="SNAPSHOT",
                lease_token=dependent_snapshot["lease_token"],
            )

            dependent_order = await adapter.claim_next_execution_success_delivery(venue=venue)
            assert dependent_order is not None
            assert (
                dependent_order["idempotency_key"],
                dependent_order["delivery_kind"],
            ) == (dependent_key, "ORDER_PLACED")
    finally:
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = ANY($2::text[])",
            venue,
            [dependent_key, unrelated_key],
        )
        await conn.close()


@pytest.mark.asyncio
async def test_stop_market_webhook_projection_is_adopted_by_ack(
    test_database_config: TestDatabaseConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    venue = "USD_M"
    idempotency_key = f"ack-stop-market-{uuid4()}"
    client_order_id = f"stop-market-{uuid4()}"
    event_id = uuid4()
    aggregate_id = f"{venue}:{client_order_id}"
    conn = await _connect(test_database_config)
    previous_services = dict(services)
    monkeypatch.setenv("ALLOW_LEGACY_ORDER_UPDATES", "true")
    _order_update_db_hydration_enabled_from_env.cache_clear()
    services.clear()
    try:
        await _seed_submitting_intent(conn, venue=venue, idempotency_key=idempotency_key)
        async with _initialized_adapter(test_database_config) as adapter:
            services.update(database=adapter, event_bus=_AcknowledgingBus())
            payload = {
                "event_type": "order_update.v1",
                "venue": venue,
                "symbol": "BTCUSDT",
                "order_id": 123,
                "client_order_id": client_order_id,
                "status": "NEW",
                "side": "SELL",
                "order_type": "STOP_MARKET",
                "price": "49000",
                "quantity": "0.001",
                "executed_qty": "0",
                "update_time": datetime.now(UTC).isoformat(),
            }
            response = await ingest_order_update(
                {
                    "event_id": str(event_id),
                    "aggregate_id": aggregate_id,
                    "sequence": 1,
                    "event_version": 1,
                    "event_type": "order_update.v1",
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "payload": payload,
                }
            )
            assert response == {"status": "ok"}

            assert await adapter.commit_execution_ack(
                idempotency_key,
                venue=venue,
                response_payload={"bracket_order_id": "bracket-stop-market"},
                order_rows=[
                    {
                        "client_order_id": client_order_id,
                        "venue": venue,
                        "symbol": "BTCUSDT",
                        "side": "SELL",
                        "type": "STOP_LOSS",
                        "quantity": "0.001",
                        "price": None,
                        "stop_price": "49000",
                        "status": "NEW",
                    },
                ],
                deliveries=[
                    {
                        "delivery_kind": "ORDER_PLACED",
                        "delivery_payload": {"event_type": "order_placed"},
                    },
                ],
            )

        row = await conn.fetchrow(
            """
            SELECT type, price, stop_price, status
            FROM orders WHERE venue = $1 AND client_order_id = $2
            """,
            venue,
            client_order_id,
        )
        assert dict(row) == {
            "type": "STOP_LOSS",
            "price": None,
            "stop_price": Decimal("49000"),
            "status": "NEW",
        }
    finally:
        services.clear()
        services.update(previous_services)
        _order_update_db_hydration_enabled_from_env.cache_clear()
        await conn.execute(
            "DELETE FROM engine_order_update_inbox WHERE aggregate_id = $1",
            aggregate_id,
        )
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_ack_projection_adopts_first_exchange_id_and_rejects_second_owner(
    test_database_config: TestDatabaseConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    venue = "USD_M"
    idempotency_key = f"ack-exchange-owner-{uuid4()}"
    client_order_id = f"ack-exchange-owner-{uuid4()}"
    aggregate_id = f"{venue}:{client_order_id}"
    first_event_id = uuid4()
    second_event_id = uuid4()
    conn = await _connect(test_database_config)
    previous_services = dict(services)
    monkeypatch.setenv("ALLOW_LEGACY_ORDER_UPDATES", "true")
    _order_update_db_hydration_enabled_from_env.cache_clear()
    services.clear()
    try:
        await _seed_submitting_intent(conn, venue=venue, idempotency_key=idempotency_key)
        async with _initialized_adapter(test_database_config) as adapter:
            assert await adapter.commit_execution_ack(
                idempotency_key,
                venue=venue,
                response_payload={"bracket_order_id": f"router-bracket-{uuid4()}"},
                order_rows=[_order_row(venue=venue, client_order_id=client_order_id)],
                deliveries=[
                    {
                        "delivery_kind": "ORDER_PLACED",
                        "delivery_payload": {"event_type": "order_placed"},
                    },
                ],
            )
            services.update(database=adapter, event_bus=_AcknowledgingBus())

            def envelope(
                event_id: object, sequence: int, exchange_order_id: int
            ) -> dict[str, object]:
                now = datetime.now(UTC).isoformat()
                return {
                    "event_id": str(event_id),
                    "aggregate_id": aggregate_id,
                    "sequence": sequence,
                    "event_version": 1,
                    "event_type": "order_update.v1",
                    "occurred_at": now,
                    "payload": {
                        "event_type": "order_update.v1",
                        "venue": venue,
                        "symbol": "BTCUSDT",
                        "order_id": exchange_order_id,
                        "client_order_id": client_order_id,
                        "status": "NEW",
                        "side": "BUY",
                        "order_type": "LIMIT",
                        "price": "50000",
                        "quantity": "0.001",
                        "executed_qty": "0",
                        "update_time": now,
                    },
                }

            assert await ingest_order_update(envelope(first_event_id, 1, 123)) == {"status": "ok"}
            with pytest.raises(HTTPException) as exc_info:
                await ingest_order_update(envelope(second_event_id, 2, 456))
            assert exc_info.value.status_code == 503

        row = await conn.fetchrow(
            """
            SELECT exchange_order_id, status, filled_quantity
            FROM orders WHERE venue = $1 AND client_order_id = $2
            """,
            venue,
            client_order_id,
        )
        assert dict(row) == {
            "exchange_order_id": "123",
            "status": "NEW",
            "filled_quantity": Decimal("0E-8"),
        }
        inbox_rows = await conn.fetch(
            """
            SELECT event_id, state FROM engine_order_update_inbox
            WHERE aggregate_id = $1 ORDER BY sequence
            """,
            aggregate_id,
        )
        assert [dict(row) for row in inbox_rows] == [
            {"event_id": first_event_id, "state": "PROCESSED"},
            {"event_id": second_event_id, "state": "FAILED"},
        ]
    finally:
        services.clear()
        services.update(previous_services)
        _order_update_db_hydration_enabled_from_env.cache_clear()
        await conn.execute(
            "DELETE FROM engine_order_update_inbox WHERE aggregate_id = $1",
            aggregate_id,
        )
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["CANCELED", "EXPIRED"])
async def test_order_update_inbox_accepts_newer_authoritative_full_fill_after_terminal_partial(
    test_database_config: TestDatabaseConfig,
    terminal_status: str,
) -> None:
    aggregate_id = f"SPOT:late-full-fill-{uuid4()}"
    event_ids = [uuid4(), uuid4(), uuid4()]
    observed_times = [
        "2026-03-21T20:04:00Z",
        "2026-03-21T20:05:00Z",
        "2026-03-21T20:06:00Z",
    ]
    statuses = ["PARTIALLY_FILLED", terminal_status, "FILLED"]
    executed_quantities = ["0.25", "0.25", "1"]
    conn = await _connect(test_database_config)
    try:
        async with _initialized_adapter(test_database_config) as adapter:
            for sequence, (event_id, status, executed_qty, update_time) in enumerate(
                zip(event_ids, statuses, executed_quantities, observed_times, strict=True),
                start=1,
            ):
                payload = {
                    "status": status,
                    "quantity": "1",
                    "executed_qty": executed_qty,
                    "update_time": update_time,
                }
                assert (
                    await adapter.claim_order_update_inbox(
                        event_id=str(event_id),
                        aggregate_id=aggregate_id,
                        sequence=sequence,
                        event_version=1,
                        payload=payload,
                        payload_hash=f"{sequence:064x}",
                    )
                    == "CLAIMED"
                )
                await adapter.complete_order_update_inbox(event_id=str(event_id))

        rows = await conn.fetch(
            """
            SELECT sequence, state
            FROM engine_order_update_inbox
            WHERE aggregate_id = $1
            ORDER BY sequence
            """,
            aggregate_id,
        )
        assert [dict(row) for row in rows] == [
            {"sequence": 1, "state": "PROCESSED"},
            {"sequence": 2, "state": "PROCESSED"},
            {"sequence": 3, "state": "PROCESSED"},
        ]
    finally:
        await conn.execute(
            "DELETE FROM engine_order_update_inbox WHERE aggregate_id = $1",
            aggregate_id,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_exchange_identity_migration_clears_only_router_bracket_placeholders(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "SPOT"
    idempotency_key = f"legacy-bracket-owner-{uuid4()}"
    placeholder_client_order_id = f"legacy-bracket-{uuid4()}"
    authoritative_client_order_id = f"authoritative-exchange-{uuid4()}"
    bracket_order_id = f"router-bracket-{uuid4()}"
    authoritative_exchange_order_id = f"exchange-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        await _seed_submitting_intent(
            conn,
            venue=venue,
            idempotency_key=idempotency_key,
            state="ACKNOWLEDGED",
        )
        await conn.execute(
            """
            UPDATE execution_intents
            SET response_payload = jsonb_build_object('bracket_order_id', $3::text)
            WHERE venue = $1 AND idempotency_key = $2
            """,
            venue,
            idempotency_key,
            bracket_order_id,
        )
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type, quantity, price,
                status, filled_quantity, exchange_order_id, created_at
            ) VALUES
                ($1, $3, 'BTCUSDT', 'BUY', 'LIMIT', 0.001, 50000,
                 'NEW', 0, $4, NOW()),
                ($2, $3, 'ETHUSDT', 'BUY', 'LIMIT', 0.01, 4000,
                 'NEW', 0, $5, NOW())
            """,
            placeholder_client_order_id,
            authoritative_client_order_id,
            venue,
            bracket_order_id,
            authoritative_exchange_order_id,
        )

        migration_path = (
            Path(__file__).parents[4]
            / "db"
            / "migrations"
            / "039_clear_router_bracket_exchange_ids.sql"
        )
        await conn.execute(migration_path.read_text())

        rows = await conn.fetch(
            """
            SELECT client_order_id, exchange_order_id
            FROM orders WHERE venue = $1 AND client_order_id = ANY($2::text[])
            ORDER BY client_order_id
            """,
            venue,
            [placeholder_client_order_id, authoritative_client_order_id],
        )
        assert {row["client_order_id"]: row["exchange_order_id"] for row in rows} == {
            placeholder_client_order_id: None,
            authoritative_client_order_id: authoritative_exchange_order_id,
        }
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = ANY($2::text[])",
            venue,
            [placeholder_client_order_id, authoritative_client_order_id],
        )
        await conn.execute(
            "DELETE FROM execution_intents WHERE venue = $1 AND idempotency_key = $2",
            venue,
            idempotency_key,
        )
        await conn.close()


@pytest.mark.parametrize(
    ("field", "divergent_value"),
    [
        ("symbol", "ETHUSDT"),
        ("side", "SELL"),
        ("quantity", "0.002"),
        ("price", "50001"),
        ("order_id", 456),
    ],
)
@pytest.mark.asyncio
async def test_enveloped_order_update_rejects_immutable_identity_before_projection_mutation(
    test_database_config: TestDatabaseConfig,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    divergent_value: object,
) -> None:
    venue = "USD_M"
    client_order_id = f"identity-{field}-{uuid4()}"
    event_id = uuid4()
    aggregate_id = f"{venue}:{client_order_id}"
    conn = await _connect(test_database_config)
    previous_services = dict(services)
    monkeypatch.setenv("ALLOW_LEGACY_ORDER_UPDATES", "true")
    _order_update_db_hydration_enabled_from_env.cache_clear()
    services.clear()
    try:
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type, quantity, price,
                status, filled_quantity, exchange_order_id, created_at
            ) VALUES ($1, $2, 'BTCUSDT', 'BUY', 'LIMIT', 0.001, 50000,
                      'NEW', 0, '123', NOW())
            """,
            client_order_id,
            venue,
        )
        async with _initialized_adapter(test_database_config) as adapter:
            services.update(database=adapter, event_bus=_AcknowledgingBus())
            payload: dict[str, object] = {
                "event_type": "order_update.v1",
                "venue": venue,
                "symbol": "BTCUSDT",
                "order_id": 123,
                "client_order_id": client_order_id,
                "status": "NEW",
                "side": "BUY",
                "order_type": "LIMIT",
                "price": "50000",
                "quantity": "0.001",
                "executed_qty": "0",
                "update_time": datetime.now(UTC).isoformat(),
            }
            payload[field] = divergent_value

            with pytest.raises(HTTPException) as exc_info:
                await ingest_order_update(
                    {
                        "event_id": str(event_id),
                        "aggregate_id": aggregate_id,
                        "sequence": 1,
                        "event_version": 1,
                        "event_type": "order_update.v1",
                        "occurred_at": datetime.now(UTC).isoformat(),
                        "payload": payload,
                    }
                )

            assert exc_info.value.status_code == 503

        row = await conn.fetchrow(
            """
            SELECT symbol, side, type, quantity, price, stop_price, exchange_order_id,
                   status, filled_quantity
            FROM orders
            WHERE venue = $1 AND client_order_id = $2
            """,
            venue,
            client_order_id,
        )
        assert dict(row) == {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": Decimal("0.00100000"),
            "price": Decimal("50000.00000000"),
            "stop_price": None,
            "exchange_order_id": "123",
            "status": "NEW",
            "filled_quantity": Decimal("0E-8"),
        }
        inbox = await conn.fetchrow(
            "SELECT state FROM engine_order_update_inbox WHERE event_id = $1",
            event_id,
        )
        assert dict(inbox) == {"state": "FAILED"}
    finally:
        services.clear()
        services.update(previous_services)
        _order_update_db_hydration_enabled_from_env.cache_clear()
        await conn.execute(
            "DELETE FROM engine_order_update_inbox WHERE aggregate_id = $1",
            aggregate_id,
        )
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_enveloped_stop_update_rejects_divergent_stop_price_before_mutation(
    test_database_config: TestDatabaseConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    venue = "USD_M"
    client_order_id = f"identity-stop-{uuid4()}"
    event_id = uuid4()
    aggregate_id = f"{venue}:{client_order_id}"
    conn = await _connect(test_database_config)
    previous_services = dict(services)
    monkeypatch.setenv("ALLOW_LEGACY_ORDER_UPDATES", "true")
    _order_update_db_hydration_enabled_from_env.cache_clear()
    services.clear()
    try:
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type, quantity, stop_price,
                status, filled_quantity, exchange_order_id, created_at
            ) VALUES ($1, $2, 'BTCUSDT', 'SELL', 'STOP_LOSS', 0.001, 49000,
                      'NEW', 0, '123', NOW())
            """,
            client_order_id,
            venue,
        )
        async with _initialized_adapter(test_database_config) as adapter:
            services.update(database=adapter, event_bus=_AcknowledgingBus())
            with pytest.raises(HTTPException) as exc_info:
                await ingest_order_update(
                    {
                        "event_id": str(event_id),
                        "aggregate_id": aggregate_id,
                        "sequence": 1,
                        "event_version": 1,
                        "event_type": "order_update.v1",
                        "occurred_at": datetime.now(UTC).isoformat(),
                        "payload": {
                            "event_type": "order_update.v1",
                            "venue": venue,
                            "symbol": "BTCUSDT",
                            "order_id": 123,
                            "client_order_id": client_order_id,
                            "status": "NEW",
                            "side": "SELL",
                            "order_type": "STOP_MARKET",
                            "price": "49001",
                            "quantity": "0.001",
                            "executed_qty": "0",
                            "update_time": datetime.now(UTC).isoformat(),
                        },
                    }
                )

            assert exc_info.value.status_code == 503

        row = await conn.fetchrow(
            """
            SELECT type, price, stop_price, exchange_order_id, status
            FROM orders
            WHERE venue = $1 AND client_order_id = $2
            """,
            venue,
            client_order_id,
        )
        assert dict(row) == {
            "type": "STOP_LOSS",
            "price": None,
            "stop_price": Decimal("49000.00000000"),
            "exchange_order_id": "123",
            "status": "NEW",
        }
    finally:
        services.clear()
        services.update(previous_services)
        _order_update_db_hydration_enabled_from_env.cache_clear()
        await conn.execute(
            "DELETE FROM engine_order_update_inbox WHERE aggregate_id = $1",
            aggregate_id,
        )
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = $2",
            venue,
            client_order_id,
        )
        await conn.close()


@pytest.mark.asyncio
async def test_exchange_order_identifier_is_unique_within_venue_and_symbol(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "USD_M"
    first_client_order_id = f"exchange-owner-a-{uuid4()}"
    second_client_order_id = f"exchange-owner-b-{uuid4()}"
    conflicting_client_order_id = f"exchange-owner-c-{uuid4()}"
    exchange_order_id = f"exchange-unique-{uuid4()}"
    conn = await _connect(test_database_config)
    try:
        migration_sql = (
            Path(__file__).parents[4] / "db/migrations/038_order_exchange_identity.sql"
        ).read_text()
        await conn.execute(migration_sql)
        await conn.execute(migration_sql)
        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type, quantity, price,
                status, filled_quantity, exchange_order_id, created_at
            ) VALUES ($1, $2, 'BTCUSDT', 'BUY', 'LIMIT', 0.001, 50000,
                      'NEW', 0, $3, NOW())
            """,
            first_client_order_id,
            venue,
            exchange_order_id,
        )

        await conn.execute(
            """
            INSERT INTO orders (
                client_order_id, venue, symbol, side, type, quantity, price,
                status, filled_quantity, exchange_order_id, created_at
            ) VALUES ($1, $2, 'ETHUSDT', 'SELL', 'LIMIT', 0.001, 3000,
                      'NEW', 0, $3, NOW())
            """,
            second_client_order_id,
            venue,
            exchange_order_id,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO orders (
                    client_order_id, venue, symbol, side, type, quantity, price,
                    status, filled_quantity, exchange_order_id, created_at
                ) VALUES ($1, $2, 'BTCUSDT', 'SELL', 'LIMIT', 0.001, 50010,
                          'NEW', 0, $3, NOW())
                """,
                conflicting_client_order_id,
                venue,
                exchange_order_id,
            )
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = ANY($2::text[])",
            venue,
            [first_client_order_id, second_client_order_id, conflicting_client_order_id],
        )
        await conn.close()


@pytest.mark.asyncio
async def test_order_update_exchange_identity_owner_is_scoped_by_symbol(
    test_database_config: TestDatabaseConfig,
) -> None:
    venue = "USD_M"
    exchange_order_id = f"exchange-symbol-scope-{uuid4()}"
    client_order_ids = [f"btc-owner-{uuid4()}", f"eth-owner-{uuid4()}"]
    conn = await _connect(test_database_config)
    try:
        migration_sql = (
            Path(__file__).parents[4] / "db/migrations/038_order_exchange_identity.sql"
        ).read_text()
        await conn.execute(migration_sql)
        await conn.execute(migration_sql)
        async with _initialized_adapter(test_database_config) as adapter:
            for client_order_id, symbol, price in (
                (client_order_ids[0], "BTCUSDT", "50000"),
                (client_order_ids[1], "ETHUSDT", "3000"),
            ):
                assert await adapter.upsert_order_update(
                    {
                        "client_order_id": client_order_id,
                        "venue": venue,
                        "symbol": symbol,
                        "side": "BUY",
                        "type": "LIMIT",
                        "quantity": "0.001",
                        "price": price,
                        "status": "NEW",
                        "filled_quantity": "0",
                        "exchange_order_id": exchange_order_id,
                        "last_update_time": datetime.now(UTC),
                    }
                )

        rows = await conn.fetch(
            """
            SELECT symbol, exchange_order_id
            FROM orders
            WHERE venue = $1 AND client_order_id = ANY($2::text[])
            ORDER BY symbol
            """,
            venue,
            client_order_ids,
        )
        assert [dict(row) for row in rows] == [
            {"symbol": "BTCUSDT", "exchange_order_id": exchange_order_id},
            {"symbol": "ETHUSDT", "exchange_order_id": exchange_order_id},
        ]
    finally:
        await conn.execute(
            "DELETE FROM orders WHERE venue = $1 AND client_order_id = ANY($2::text[])",
            venue,
            client_order_ids,
        )
        await conn.close()
