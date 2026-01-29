"""
Telegram Signal Validator

Validates external SMC signals from Telegram groups against your system's analysis.
This helps verify your SMC implementation accuracy.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import logging
import re

from telethon import TelegramClient, events
from telethon.tl.types import Message

logger = logging.getLogger(__name__)


@dataclass
class TelegramSignal:
    """External signal from Telegram group"""

    timestamp: datetime
    symbol: str
    direction: str  # BUY/SELL
    entry_price: Decimal
    stop_loss: Decimal
    take_profits: list[Decimal]
    reasoning: str  # e.g., "BOS on 4H", "Retest of daily OB"
    source: str  # Group/channel name
    message_id: int
    raw_text: str


@dataclass
class ValidationResult:
    """Result of comparing external signal with our system"""

    telegram_signal: TelegramSignal
    our_signal: dict | None  # Your system's signal at same time

    # Validation metrics
    direction_match: bool
    entry_within_tolerance: bool
    sl_within_tolerance: bool
    tp_within_tolerance: bool
    timing_difference_seconds: int

    # SMC validation
    smc_pattern_match: bool  # e.g., both detected BOS
    zone_match: bool  # Both identified same OB/FVG

    overall_score: float  # 0-100%


class SignalParser:
    """Parse various Telegram signal formats"""

    # Common signal patterns
    PATTERNS = {
        "basic": re.compile(
            r"(?P<symbol>\w+USDT?)\s+"
            r"(?P<direction>BUY|SELL|LONG|SHORT)\s+"
            r"Entry:\s*(?P<entry>[\d.]+)\s+"
            r"SL:\s*(?P<sl>[\d.]+)\s+"
            r"TP:\s*(?P<tp>[\d.,\s]+)",
            re.IGNORECASE | re.MULTILINE,
        ),
        "smc_style": re.compile(
            r"(?P<symbol>\w+)\s+"
            r"(?P<pattern>BOS|CHOCH|OB|FVG|POI)\s+"
            r"(?P<timeframe>\d+[HM])\s+"
            r"(?P<direction>Bullish|Bearish|Buy|Sell)",
            re.IGNORECASE,
        ),
        "with_reasoning": re.compile(
            r"Signal:\s*(?P<symbol>\w+USDT?)\s+"
            r"(?P<direction>\w+)\s+"
            r"Reason:\s*(?P<reason>[^\n]+)",
            re.IGNORECASE,
        ),
    }

    @staticmethod
    def parse_message(
        message: str,
        source: str,
        message_id: int,
    ) -> TelegramSignal | None:
        """Parse Telegram message into structured signal"""

        # Try each pattern
        for pattern_name, pattern in SignalParser.PATTERNS.items():
            match = pattern.search(message)
            if match:
                data = match.groupdict()

                # Extract components
                symbol = data.get("symbol", "").upper()
                if not symbol.endswith("USDT"):
                    symbol += "USDT"

                direction = SignalParser._normalize_direction(
                    data.get("direction", ""),
                )

                # Parse prices
                try:
                    entry = Decimal(data.get("entry", "0"))
                    sl = Decimal(data.get("sl", "0"))

                    # Parse multiple TPs
                    tp_str = data.get("tp", "0")
                    tps = [Decimal(tp.strip()) for tp in re.findall(r"[\d.]+", tp_str)]

                    # Extract reasoning
                    reasoning = data.get("reason", "")
                    if not reasoning and "pattern" in data:
                        reasoning = f"{data['pattern']} on {data.get('timeframe', '')}"

                    return TelegramSignal(
                        timestamp=datetime.now(UTC),
                        symbol=symbol,
                        direction=direction,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profits=tps,
                        reasoning=reasoning,
                        source=source,
                        message_id=message_id,
                        raw_text=message,
                    )

                except (ValueError, InvalidOperation):
                    logger.warning(f"Failed to parse prices from: {message}")

        return None

    @staticmethod
    def _normalize_direction(direction: str) -> str:
        """Normalize direction to BUY/SELL"""
        direction = direction.upper()
        if direction in ["BUY", "LONG", "BULLISH"]:
            return "BUY"
        if direction in ["SELL", "SHORT", "BEARISH"]:
            return "SELL"
        return direction


class TelegramSignalValidator:
    """Validate external signals against your system"""

    def __init__(self, config: dict, system_api):
        self.config = config
        self.system_api = system_api  # Your trading system's API

        # Tolerance settings
        self.entry_tolerance = Decimal("0.002")  # 0.2%
        self.sl_tolerance = Decimal("0.005")  # 0.5%
        self.tp_tolerance = Decimal("0.01")  # 1%
        self.time_window = 300  # 5 minutes

        # Telegram client (if monitoring live)
        self.telegram_client = None

        # Validation history
        self.validation_history: list[ValidationResult] = []

    async def setup_telegram_monitor(self, api_id: int, api_hash: str, phone: str):
        """Setup live Telegram monitoring"""
        self.telegram_client = TelegramClient("signal_validator", api_id, api_hash)
        await self.telegram_client.start(phone)

        # Monitor specific groups/channels
        @self.telegram_client.on(
            events.NewMessage(chats=self.config["telegram_channels"]),
        )
        async def handle_new_message(event):
            await self.process_telegram_message(event.message)

    async def process_telegram_message(self, message: Message):
        """Process incoming Telegram message"""
        # Parse signal
        signal = SignalParser.parse_message(
            message.text,
            message.chat.title or str(message.chat_id),
            message.id,
        )

        if signal:
            logger.info(f"Parsed signal: {signal.symbol} {signal.direction}")

            # Validate against our system
            result = await self.validate_signal(signal)

            # Store result
            self.validation_history.append(result)

            # Alert if significant mismatch
            if result.overall_score < 50:
                await self.alert_mismatch(result)

    async def validate_signal(
        self,
        telegram_signal: TelegramSignal,
    ) -> ValidationResult:
        """Validate external signal against your system"""

        # Get your system's analysis for same symbol/time
        our_analysis = await self.system_api.get_current_analysis(
            symbol=telegram_signal.symbol,
            timeframe=self._extract_timeframe(telegram_signal.reasoning),
            timestamp=telegram_signal.timestamp,
        )

        # Find matching signal from your system
        our_signal = self._find_matching_signal(
            our_analysis,
            telegram_signal.timestamp,
        )

        if not our_signal:
            # No signal from our system at this time
            return ValidationResult(
                telegram_signal=telegram_signal,
                our_signal=None,
                direction_match=False,
                entry_within_tolerance=False,
                sl_within_tolerance=False,
                tp_within_tolerance=False,
                timing_difference_seconds=0,
                smc_pattern_match=False,
                zone_match=False,
                overall_score=0.0,
            )

        # Compare signals
        direction_match = telegram_signal.direction == our_signal["direction"]

        entry_diff = (
            abs(telegram_signal.entry_price - our_signal["entry"]) / telegram_signal.entry_price
        )
        entry_match = entry_diff <= self.entry_tolerance

        sl_diff = (
            abs(telegram_signal.stop_loss - our_signal["stop_loss"]) / telegram_signal.stop_loss
        )
        sl_match = sl_diff <= self.sl_tolerance

        # Check if at least one TP matches
        tp_match = any(
            abs(tp - our_tp) / tp <= self.tp_tolerance
            for tp in telegram_signal.take_profits
            for our_tp in our_signal.get("take_profits", [])
        )

        timing_diff = abs(
            (telegram_signal.timestamp - our_signal["timestamp"]).total_seconds(),
        )

        # SMC pattern matching
        smc_match = self._check_smc_pattern_match(
            telegram_signal.reasoning,
            our_signal.get("smc_patterns", []),
        )

        zone_match = self._check_zone_match(
            telegram_signal,
            our_signal.get("zones", []),
        )

        # Calculate overall score
        score = self._calculate_validation_score(
            direction_match,
            entry_match,
            sl_match,
            tp_match,
            timing_diff <= self.time_window,
            smc_match,
            zone_match,
        )

        return ValidationResult(
            telegram_signal=telegram_signal,
            our_signal=our_signal,
            direction_match=direction_match,
            entry_within_tolerance=entry_match,
            sl_within_tolerance=sl_match,
            tp_within_tolerance=tp_match,
            timing_difference_seconds=int(timing_diff),
            smc_pattern_match=smc_match,
            zone_match=zone_match,
            overall_score=score,
        )

    def _extract_timeframe(self, reasoning: str) -> str:
        """Extract timeframe from reasoning text"""
        # Look for patterns like "4H", "1H", "15M"
        match = re.search(r"(\d+[HM])", reasoning, re.IGNORECASE)
        return match.group(1) if match else "4H"  # Default to 4H

    def _find_matching_signal(
        self,
        our_analysis: dict,
        timestamp: datetime,
    ) -> dict | None:
        """Find signal from our system near the timestamp"""
        if not our_analysis or "signals" not in our_analysis:
            return None

        # Find signal within time window
        for signal in our_analysis["signals"]:
            signal_time = signal["timestamp"]
            if abs((timestamp - signal_time).total_seconds()) <= self.time_window:
                return signal

        return None

    def _check_smc_pattern_match(
        self,
        telegram_reasoning: str,
        our_patterns: list[str],
    ) -> bool:
        """Check if SMC patterns match"""
        telegram_reasoning = telegram_reasoning.upper()

        # Common SMC patterns
        patterns = ["BOS", "CHOCH", "OB", "FVG", "POI", "FLIP", "RETEST"]

        telegram_patterns = [p for p in patterns if p in telegram_reasoning]
        our_patterns_upper = [p.upper() for p in our_patterns]

        # Check for overlap
        return bool(set(telegram_patterns) & set(our_patterns_upper))

    def _check_zone_match(
        self,
        telegram_signal: TelegramSignal,
        our_zones: list[dict],
    ) -> bool:
        """Check if entry is near same supply/demand zone"""
        for zone in our_zones:
            zone_high = Decimal(str(zone["high"]))
            zone_low = Decimal(str(zone["low"]))

            # Check if entry is within or near zone
            buffer = (zone_high - zone_low) * Decimal("0.2")  # 20% buffer

            if (zone_low - buffer) <= telegram_signal.entry_price <= (zone_high + buffer):
                return True

        return False

    def _calculate_validation_score(
        self,
        direction_match: bool,
        entry_match: bool,
        sl_match: bool,
        tp_match: bool,
        timing_match: bool,
        smc_match: bool,
        zone_match: bool,
    ) -> float:
        """Calculate overall validation score"""
        weights = {
            "direction": 30,
            "entry": 20,
            "sl": 15,
            "tp": 10,
            "timing": 10,
            "smc": 10,
            "zone": 5,
        }

        score = 0
        if direction_match:
            score += weights["direction"]
        if entry_match:
            score += weights["entry"]
        if sl_match:
            score += weights["sl"]
        if tp_match:
            score += weights["tp"]
        if timing_match:
            score += weights["timing"]
        if smc_match:
            score += weights["smc"]
        if zone_match:
            score += weights["zone"]

        return score

    async def alert_mismatch(self, result: ValidationResult):
        """Alert when signals significantly mismatch"""
        logger.warning(
            f"Signal mismatch! Score: {result.overall_score}%\n"
            f"Telegram: {result.telegram_signal.symbol} {result.telegram_signal.direction}\n"
            f"Our system: {'No signal' if not result.our_signal else result.our_signal['direction']}",
        )

    def generate_validation_report(self) -> dict:
        """Generate validation statistics"""
        if not self.validation_history:
            return {"message": "No validation data yet"}

        total = len(self.validation_history)

        # Calculate metrics
        direction_matches = sum(1 for r in self.validation_history if r.direction_match)
        entry_matches = sum(1 for r in self.validation_history if r.entry_within_tolerance)
        high_scores = sum(1 for r in self.validation_history if r.overall_score >= 70)

        avg_score = sum(r.overall_score for r in self.validation_history) / total

        # Pattern analysis
        smc_matches = sum(1 for r in self.validation_history if r.smc_pattern_match)
        zone_matches = sum(1 for r in self.validation_history if r.zone_match)

        return {
            "total_signals": total,
            "accuracy": {
                "direction_match_rate": direction_matches / total * 100,
                "entry_match_rate": entry_matches / total * 100,
                "high_score_rate": high_scores / total * 100,
                "average_score": avg_score,
            },
            "smc_validation": {
                "pattern_match_rate": smc_matches / total * 100,
                "zone_match_rate": zone_matches / total * 100,
            },
            "timing": {
                "avg_delay_seconds": sum(
                    r.timing_difference_seconds for r in self.validation_history
                )
                / total,
            },
        }


# Usage example
async def main():
    # Config for validation
    config = {
        "telegram_channels": ["@your_smc_channel", "@another_signal_group"],
        "validation_mode": "live",  # or 'historical'
    }

    # Your system's API
    from app.engine import TradingSystemAPI

    system_api = TradingSystemAPI()

    # Create validator
    validator = TelegramSignalValidator(config, system_api)

    # For live monitoring (requires Telegram API credentials)
    # await validator.setup_telegram_monitor(
    #     api_id=123456,
    #     api_hash='your_api_hash',
    #     phone='+1234567890'
    # )

    # Or validate historical signals manually
    test_signal = TelegramSignal(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        direction="BUY",
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profits=[Decimal(51000), Decimal(52000)],
        reasoning="BOS on 4H, retest of daily OB",
        source="SMC Signals Group",
        message_id=12345,
        raw_text="BTCUSDT BUY Entry: 50000 SL: 49000 TP: 51000, 52000",
    )

    result = await validator.validate_signal(test_signal)
    print(f"Validation score: {result.overall_score}%")

    # Generate report
    report = validator.generate_validation_report()
    print(f"Overall accuracy: {report['accuracy']['average_score']:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
