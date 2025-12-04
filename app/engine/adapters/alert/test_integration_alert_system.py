import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator
from app.engine.adapters.alert.alert_formatter import AlertFormatter
from app.engine.adapters.alert.line import LineAlertAdapter
from app.engine.adapters.alert.telegram import TelegramAlertAdapter
from app.engine.models import Position, SMCSignalEvent, TradingDecisionEvent
from app.engine.paper.broker import OrderUpdate


class TestAlertSystemIntegration:
    """End-to-end integration tests for the alert system"""

    @pytest.fixture
    def formatter(self) -> Any:
        return AlertFormatter()

    @pytest.fixture
    def deduplicator(self) -> Any:
        return AlertDeduplicator(ttl_seconds=60)

    @pytest.fixture
    def telegram_adapter(self, formatter: Any, deduplicator: Any) -> Any:
        return TelegramAlertAdapter(
            bot_token="test-telegram-token",
            chat_id="test-chat-id",
            formatter=formatter,
            deduplicator=deduplicator,
        )

    @pytest.fixture
    def line_adapter(self, formatter: Any, deduplicator: Any) -> Any:
        return LineAlertAdapter(
            access_token="test-line-token",
            formatter=formatter,
            deduplicator=deduplicator,
        )

    @pytest.fixture
    def alert_system(self, telegram_adapter: Any, line_adapter: Any) -> Any:
        """Mock alert system that can send to multiple platforms"""

        class AlertSystem:
            def __init__(self, adapters: Any) -> None:
                self.adapters = adapters
                self.sent_alerts = []

            async def send_alert(self, event: Any) -> None:
                """Send alert to all configured adapters"""
                tasks = []
                for adapter in self.adapters:
                    tasks.append(adapter.send_alert(event))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                self.sent_alerts.append(
                    {
                        "event": event,
                        "results": results,
                        "timestamp": datetime.now(UTC),
                    }
                )

        return AlertSystem([telegram_adapter, line_adapter])

    @pytest.mark.asyncio
    async def test_full_trading_flow_alerts(self, alert_system: Any) -> None:
        """Test alerts through a complete trading flow"""
        # 1. Trading signal
        decision = TradingTradingDecisionEvent(
            symbol="BTCUSDT",
            action="BUY",
            quantity=0.01,
            venue="SPOT",
            type="MARKET",
            confidence=0.85,
            timestamp=datetime.now(UTC),
        )

        # 2. Order placed
        order_new = OrderUpdate(
            order_id="ORD-001",
            symbol="BTCUSDT",
            side="BUY",
            status="NEW",
            quantity=0.01,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        # 3. Order filled
        order_filled = OrderUpdate(
            order_id="ORD-001",
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            quantity=0.01,
            executed_qty=0.01,
            executed_price=45000.0,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        # 4. Position update
        position = Position(
            symbol="BTCUSDT",
            side="LONG",
            quantity=0.01,
            entry_price=45000.0,
            current_price=45500.0,
            venue="SPOT",
            pnl=5.0,
            pnl_percent=1.11,
            timestamp=datetime.now(UTC),
        )

        # Mock the adapter sends
        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                loop = asyncio.get_event_loop()
                mock_telegram.return_value = loop.create_future()
                mock_telegram.return_value.set_result({"ok": True})
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                # Send alerts through the flow
                await alert_system.send_alert(decision)
                await alert_system.send_alert(order_new)
                await alert_system.send_alert(order_filled)
                await alert_system.send_alert(position)

                # Verify all platforms received all alerts
                assert mock_telegram.call_count == 4
                assert mock_line.call_count == 4

                # Verify alert progression makes sense
                assert len(alert_system.sent_alerts) == 4

    @pytest.mark.asyncio
    async def test_multi_platform_failure_handling(self, alert_system: Any) -> None:
        """Test system continues when one platform fails"""
        order = OrderUpdate(
            order_id="FAIL-001",
            symbol="ETHUSDT",
            side="SELL",
            status="NEW",
            quantity=1.0,
            venue="USD_M",
            timestamp=datetime.now(UTC),
        )

        # Mock Telegram fails but LINE succeeds
        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                mock_telegram.side_effect = Exception("Telegram API error")
                loop = asyncio.get_event_loop()
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                results = await alert_system.send_alert(order)

                # One failure, one success
                assert len(results) == 2
                assert isinstance(results[0], Exception)
                assert results[1] is None  # Success returns None

                # LINE should still be called despite Telegram failure
                mock_line.assert_called_once()

    @pytest.mark.asyncio
    async def test_smc_event_alerts(self, alert_system: Any) -> None:
        """Test Smart Money Concept event alerts"""
        smc_events = [
            SMCSignalEvent(
                symbol="BTCUSDT",
                timeframe="15m",
                event_type="CHOCH",
                direction="bullish",
                price=45000.0,
                timestamp=datetime.now(UTC),
            ),
            SMCSignalEvent(
                symbol="BTCUSDT",
                timeframe="15m",
                event_type="BOS",
                direction="bullish",
                price=45500.0,
                timestamp=datetime.now(UTC),
            ),
            SMCSignalEvent(
                symbol="BTCUSDT",
                timeframe="15m",
                event_type="ORDER_BLOCK",
                zone_type="demand",
                price_from=44800.0,
                price_to=44900.0,
                timestamp=datetime.now(UTC),
            ),
        ]

        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                loop = asyncio.get_event_loop()
                mock_telegram.return_value = loop.create_future()
                mock_telegram.return_value.set_result({"ok": True})
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                for event in smc_events:
                    await alert_system.send_alert(event)

                # Each event to each platform
                assert mock_telegram.call_count == 3
                assert mock_line.call_count == 3

                # Check formatting includes SMC terminology
                telegram_messages = [
                    call[0][0] for call in mock_telegram.call_args_list
                ]
                assert any("CHOCH" in msg for msg in telegram_messages)
                assert any("BOS" in msg for msg in telegram_messages)
                assert any(
                    "ORDER BLOCK" in msg or "Order Block" in msg
                    for msg in telegram_messages
                )

    @pytest.mark.asyncio
    async def test_alert_storm_protection(self, alert_system: Any) -> None:
        """Test protection against alert storms"""
        # Generate 50 similar orders in quick succession
        orders = []
        for i in range(50):
            orders.append(
                OrderUpdate(
                    order_id=f"STORM-{i}",
                    symbol="BTCUSDT",
                    side="BUY",
                    status="NEW",
                    quantity=0.001,
                    venue="SPOT",
                    timestamp=datetime.now(UTC),
                )
            )

        sent_count = 0
        blocked_count = 0

        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                loop = asyncio.get_event_loop()
                mock_telegram.return_value = loop.create_future()
                mock_telegram.return_value.set_result({"ok": True})
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                # Send all orders rapidly
                for order in orders:
                    try:
                        await alert_system.send_alert(order)
                        sent_count += 1
                    except Exception:
                        blocked_count += 1

                # Should have some rate limiting in effect
                # Not all 50 should go through immediately
                assert mock_telegram.call_count < 50
                assert mock_line.call_count < 50

    @pytest.mark.asyncio
    async def test_critical_alert_priority(self, alert_system: Any) -> None:
        """Test critical alerts get priority"""
        # Normal alert
        normal_order = OrderUpdate(
            order_id="NORMAL-001",
            symbol="DOGEUSDT",
            side="BUY",
            status="NEW",
            quantity=1000.0,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        # Critical alert - large position stop loss hit
        critical_position = Position(
            symbol="BTCUSDT",
            side="LONG",
            quantity=1.0,
            entry_price=50000.0,
            current_price=47500.0,
            venue="USD_M",
            pnl=-2500.0,
            pnl_percent=-5.0,
            stop_loss_hit=True,
            timestamp=datetime.now(UTC),
        )

        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                loop = asyncio.get_event_loop()
                mock_telegram.return_value = loop.create_future()
                mock_telegram.return_value.set_result({"ok": True})
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                # Send both alerts
                await alert_system.send_alert(normal_order)
                await alert_system.send_alert(critical_position)

                # Both should be sent
                assert mock_telegram.call_count == 2
                assert mock_line.call_count == 2

                # Critical alert should have special formatting
                critical_messages = [
                    call[0][0]
                    for call in mock_telegram.call_args_list
                    if "2500" in call[0][0] or "STOP LOSS" in call[0][0].upper()
                ]
                assert len(critical_messages) >= 1

    @pytest.mark.asyncio
    async def test_alert_recovery_after_downtime(self, alert_system: Any) -> None:
        """Test alert system recovers after platform downtime"""
        order = OrderUpdate(
            order_id="RECOVERY-001",
            symbol="ETHUSDT",
            side="BUY",
            status="FILLED",
            quantity=2.0,
            executed_qty=2.0,
            executed_price=2500.0,
            venue="USD_M",
            timestamp=datetime.now(UTC),
        )

        call_count = 0

        async def mock_send_with_recovery(message: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Service unavailable")

        with patch.object(
            alert_system.adapters[0],
            "_send_telegram_message",
            side_effect=mock_send_with_recovery,
        ):
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                loop = asyncio.get_event_loop()
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                # First attempt might fail
                results1 = await alert_system.send_alert(order)
                assert isinstance(results1[0], Exception)

                # System should recover on retry
                with patch.object(alert_system.adapters[0], "retry_count", 3):
                    with patch.object(alert_system.adapters[0], "retry_delay", 0.01):
                        # This attempt should eventually succeed
                        results2 = await alert_system.send_alert(order)

                        # LINE should work throughout
                        assert mock_line.call_count >= 1

    @pytest.mark.asyncio
    async def test_daily_summary_generation(self, alert_system: Any) -> None:
        """Test daily summary alert generation"""
        # Simulate a day's worth of trading
        daily_events = []

        # Morning trades
        for i in range(5):
            daily_events.append(
                OrderUpdate(
                    order_id=f"MORNING-{i}",
                    symbol="BTCUSDT",
                    side="BUY" if i % 2 == 0 else "SELL",
                    status="FILLED",
                    quantity=0.01,
                    executed_qty=0.01,
                    executed_price=45000.0 + i * 100,
                    venue="SPOT",
                    timestamp=datetime.now(UTC),
                )
            )

        # Afternoon positions
        daily_events.append(
            Position(
                symbol="ETHUSDT",
                side="LONG",
                quantity=1.0,
                entry_price=2400.0,
                current_price=2450.0,
                venue="SPOT",
                pnl=50.0,
                pnl_percent=2.08,
                timestamp=datetime.now(UTC),
            )
        )

        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                loop = asyncio.get_event_loop()
                mock_telegram.return_value = loop.create_future()
                mock_telegram.return_value.set_result({"ok": True})
                mock_line.return_value = loop.create_future()
                mock_line.return_value.set_result({"status": 200})

                # Send all daily events
                for event in daily_events:
                    await alert_system.send_alert(event)

                # Generate and send daily summary
                summary = {
                    "total_trades": 5,
                    "winning_trades": 3,
                    "total_pnl": 150.75,
                    "win_rate": 0.60,
                    "date": datetime.now(UTC).date(),
                }

                summary_msg = alert_system.adapters[0].formatter.format_daily_summary(
                    summary
                )
                await alert_system.adapters[0]._send_telegram_message(summary_msg)
                await alert_system.adapters[1]._send_line_message(summary_msg)

                # Verify summary was sent
                summary_calls = [
                    call
                    for call in mock_telegram.call_args_list
                    if "Daily Trading Summary" in call[0][0]
                ]
                assert len(summary_calls) == 1

    @pytest.mark.asyncio
    async def test_concurrent_alert_handling(self, alert_system: Any) -> None:
        """Test handling multiple concurrent alerts"""
        # Different event types arriving simultaneously
        events = [
            OrderUpdate(
                order_id="CONC-001",
                symbol="BTCUSDT",
                side="BUY",
                status="NEW",
                quantity=0.1,
                venue="USD_M",
                timestamp=datetime.now(UTC),
            ),
            Position(
                symbol="ETHUSDT",
                side="SHORT",
                quantity=5.0,
                entry_price=2500.0,
                current_price=2480.0,
                venue="USD_M",
                pnl=100.0,
                pnl_percent=0.8,
                timestamp=datetime.now(UTC),
            ),
            TradingDecisionEvent(
                symbol="BNBUSDT",
                action="SELL",
                quantity=10.0,
                venue="SPOT",
                type="LIMIT",
                price=320.0,
                confidence=0.88,
                timestamp=datetime.now(UTC),
            ),
        ]

        with patch.object(
            alert_system.adapters[0], "_send_telegram_message"
        ) as mock_telegram:
            with patch.object(
                alert_system.adapters[1], "_send_line_message"
            ) as mock_line:
                # Add delay to simulate network latency
                async def delayed_telegram_send(msg: Any) -> None:
                    await asyncio.sleep(0.1)

                async def delayed_line_send(msg: Any) -> None:
                    await asyncio.sleep(0.05)

                mock_telegram.side_effect = delayed_telegram_send
                mock_line.side_effect = delayed_line_send

                # Send all alerts concurrently
                tasks = [alert_system.send_alert(event) for event in events]
                results = await asyncio.gather(*tasks)

                # All should complete successfully
                assert len(results) == 3
                assert mock_telegram.call_count == 3
                assert mock_line.call_count == 3

                # Verify no alerts were lost
                assert len(alert_system.sent_alerts) == 3
