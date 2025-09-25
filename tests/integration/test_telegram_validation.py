"""
Integration tests for Telegram signal validation
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.engine.telegram_validator import (
    TelegramSignalValidator,
    TelegramSignal,
    SignalParser
)


class MockSystemAPI:
    """Mock your trading system API for testing"""

    def __init__(self):
        self.mock_signals = []

    async def get_current_analysis(self, symbol, timeframe, timestamp):
        """Return mock analysis"""
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'signals': self.mock_signals,
            'smc_patterns': ['BOS', 'OB'],
            'zones': [
                {'high': 52000, 'low': 51500, 'type': 'demand'},
                {'high': 48000, 'low': 47500, 'type': 'supply'}
            ]
        }

    def add_mock_signal(self, signal):
        self.mock_signals.append(signal)


class TestSignalParser:
    """Test signal parsing from various formats"""

    def test_parse_basic_format(self):
        """Test parsing basic signal format"""
        message = """
        BTCUSDT BUY
        Entry: 50000
        SL: 49000
        TP: 51000, 52000
        """

        signal = SignalParser.parse_message(message, "Test Group", 123)

        assert signal is not None
        assert signal.symbol == "BTCUSDT"
        assert signal.direction == "BUY"
        assert signal.entry_price == Decimal('50000')
        assert signal.stop_loss == Decimal('49000')
        assert signal.take_profits == [Decimal('51000'), Decimal('52000')]

    def test_parse_smc_format(self):
        """Test parsing SMC-style signals"""
        message = """
        ETHUSDT BOS 4H Bullish
        Entry Zone: 3200-3250
        """

        signal = SignalParser.parse_message(message, "SMC Group", 456)

        assert signal is not None
        assert signal.symbol == "ETHUSDT"
        assert signal.direction == "BUY"
        assert "BOS" in signal.reasoning
        assert "4H" in signal.reasoning

    def test_parse_with_emojis(self):
        """Test parsing signals with emojis"""
        message = """
        🔥 SOLUSDT SHORT 🔥
        Entry: 100
        SL: 105
        TP: 95, 90, 85

        Reason: Daily resistance + 4H CHOCH
        """

        signal = SignalParser.parse_message(message, "Premium Signals", 789)

        assert signal is not None
        assert signal.symbol == "SOLUSDT"
        assert signal.direction == "SELL"
        assert signal.entry_price == Decimal('100')
        assert len(signal.take_profits) == 3

    def test_normalize_direction(self):
        """Test direction normalization"""
        assert SignalParser._normalize_direction("LONG") == "BUY"
        assert SignalParser._normalize_direction("SHORT") == "SELL"
        assert SignalParser._normalize_direction("bullish") == "BUY"
        assert SignalParser._normalize_direction("bearish") == "SELL"


@pytest.mark.asyncio
class TestTelegramSignalValidator:
    """Test signal validation logic"""

    async def test_perfect_match_validation(self):
        """Test validation when signals perfectly match"""
        # Setup mock API
        mock_api = MockSystemAPI()
        validator = TelegramSignalValidator({}, mock_api)

        # Add matching signal to mock
        now = datetime.now(timezone.utc)
        mock_api.add_mock_signal({
            'timestamp': now,
            'direction': 'BUY',
            'entry': Decimal('50000'),
            'stop_loss': Decimal('49000'),
            'take_profits': [Decimal('51000'), Decimal('52000')],
            'smc_patterns': ['BOS', 'OB'],
            'zones': [{'high': 50100, 'low': 49900, 'type': 'demand'}]
        })

        # Create Telegram signal
        telegram_signal = TelegramSignal(
            timestamp=now,
            symbol='BTCUSDT',
            direction='BUY',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            take_profits=[Decimal('51000'), Decimal('52000')],
            reasoning='BOS on 4H',
            source='Test Group',
            message_id=123,
            raw_text='test'
        )

        # Validate
        result = await validator.validate_signal(telegram_signal)

        assert result.direction_match is True
        assert result.entry_within_tolerance is True
        assert result.sl_within_tolerance is True
        assert result.tp_within_tolerance is True
        assert result.smc_pattern_match is True
        assert result.overall_score >= 90

    async def test_partial_match_validation(self):
        """Test validation with partial matches"""
        mock_api = MockSystemAPI()
        validator = TelegramSignalValidator({}, mock_api)

        now = datetime.now(timezone.utc)
        mock_api.add_mock_signal({
            'timestamp': now,
            'direction': 'BUY',
            'entry': Decimal('50100'),  # Slightly different
            'stop_loss': Decimal('49100'),  # Different SL
            'take_profits': [Decimal('51000'), Decimal('52500')],
            'smc_patterns': ['CHOCH'],  # Different pattern
        })

        telegram_signal = TelegramSignal(
            timestamp=now,
            symbol='BTCUSDT',
            direction='BUY',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            take_profits=[Decimal('51000'), Decimal('52000')],
            reasoning='BOS on 4H',
            source='Test Group',
            message_id=123,
            raw_text='test'
        )

        result = await validator.validate_signal(telegram_signal)

        assert result.direction_match is True
        assert result.entry_within_tolerance is True  # Within 0.2%
        assert result.sl_within_tolerance is False  # Exceeds 0.5%
        assert result.tp_within_tolerance is True  # At least one matches
        assert result.smc_pattern_match is False  # Different patterns
        assert 50 <= result.overall_score <= 80

    async def test_no_match_validation(self):
        """Test validation when no signal from our system"""
        mock_api = MockSystemAPI()
        validator = TelegramSignalValidator({}, mock_api)

        # No signals in mock API

        telegram_signal = TelegramSignal(
            timestamp=datetime.now(timezone.utc),
            symbol='BTCUSDT',
            direction='BUY',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            take_profits=[Decimal('51000')],
            reasoning='Random signal',
            source='Test Group',
            message_id=123,
            raw_text='test'
        )

        result = await validator.validate_signal(telegram_signal)

        assert result.our_signal is None
        assert result.overall_score == 0
        assert result.direction_match is False

    async def test_timing_window(self):
        """Test signal matching within time window"""
        mock_api = MockSystemAPI()
        validator = TelegramSignalValidator({}, mock_api)
        validator.time_window = 300  # 5 minutes

        now = datetime.now(timezone.utc)

        # Add signal 3 minutes ago
        mock_api.add_mock_signal({
            'timestamp': now - timedelta(minutes=3),
            'direction': 'BUY',
            'entry': Decimal('50000'),
            'stop_loss': Decimal('49000'),
            'take_profits': [Decimal('51000')],
        })

        telegram_signal = TelegramSignal(
            timestamp=now,
            symbol='BTCUSDT',
            direction='BUY',
            entry_price=Decimal('50000'),
            stop_loss=Decimal('49000'),
            take_profits=[Decimal('51000')],
            reasoning='test',
            source='Test Group',
            message_id=123,
            raw_text='test'
        )

        result = await validator.validate_signal(telegram_signal)

        assert result.our_signal is not None
        assert result.timing_difference_seconds == 180  # 3 minutes

    def test_smc_pattern_matching(self):
        """Test SMC pattern detection"""
        validator = TelegramSignalValidator({}, None)

        # Test exact match
        assert validator._check_smc_pattern_match(
            "BOS on 4H timeframe",
            ['BOS', 'OB']
        ) is True

        # Test case insensitive
        assert validator._check_smc_pattern_match(
            "choch detected",
            ['CHOCH', 'FVG']
        ) is True

        # Test no match
        assert validator._check_smc_pattern_match(
            "Random text",
            ['BOS', 'CHOCH']
        ) is False

        # Test multiple patterns
        assert validator._check_smc_pattern_match(
            "BOS after CHOCH with OB retest",
            ['BOS', 'FVG']
        ) is True

    def test_validation_scoring(self):
        """Test score calculation"""
        validator = TelegramSignalValidator({}, None)

        # Perfect match
        score = validator._calculate_validation_score(
            direction_match=True,
            entry_match=True,
            sl_match=True,
            tp_match=True,
            timing_match=True,
            smc_match=True,
            zone_match=True
        )
        assert score == 100

        # Only direction matches
        score = validator._calculate_validation_score(
            direction_match=True,
            entry_match=False,
            sl_match=False,
            tp_match=False,
            timing_match=False,
            smc_match=False,
            zone_match=False
        )
        assert score == 30  # Direction weight

        # Partial match
        score = validator._calculate_validation_score(
            direction_match=True,  # 30
            entry_match=True,      # 20
            sl_match=False,
            tp_match=True,         # 10
            timing_match=True,     # 10
            smc_match=False,
            zone_match=False
        )
        assert score == 70

    async def test_validation_report(self):
        """Test report generation"""
        mock_api = MockSystemAPI()
        validator = TelegramSignalValidator({}, mock_api)

        # Add some validation results
        for i in range(5):
            telegram_signal = TelegramSignal(
                timestamp=datetime.now(timezone.utc),
                symbol='BTCUSDT',
                direction='BUY' if i % 2 == 0 else 'SELL',
                entry_price=Decimal('50000'),
                stop_loss=Decimal('49000'),
                take_profits=[Decimal('51000')],
                reasoning='Test signal',
                source='Test Group',
                message_id=i,
                raw_text=f'test {i}'
            )

            # Add matching signal for some
            if i < 3:
                mock_api.mock_signals = [{
                    'timestamp': telegram_signal.timestamp,
                    'direction': telegram_signal.direction,
                    'entry': telegram_signal.entry_price,
                    'stop_loss': telegram_signal.stop_loss,
                    'take_profits': telegram_signal.take_profits,
                }]
            else:
                mock_api.mock_signals = []

            result = await validator.validate_signal(telegram_signal)
            validator.validation_history.append(result)

        # Generate report
        report = validator.generate_validation_report()

        assert report['total_signals'] == 5
        assert 'direction_match_rate' in report['accuracy']
        assert 'average_score' in report['accuracy']
        assert report['accuracy']['average_score'] > 0


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])