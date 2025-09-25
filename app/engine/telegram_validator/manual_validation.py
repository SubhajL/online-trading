"""
Manual Telegram Signal Validation

For cases where you copy-paste signals from Telegram for validation.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from .telegram_signal_validator import TelegramSignalValidator, SignalParser


class ManualSignalValidator:
    """Validate signals you manually copy from Telegram"""

    def __init__(self, system_api):
        self.validator = TelegramSignalValidator({}, system_api)
        self.results = []

    async def validate_pasted_signal(self, message_text: str, source: str = "Manual") -> dict:
        """
        Validate a signal you copied from Telegram

        Args:
            message_text: The copied message text
            source: Name of the Telegram group/channel

        Returns:
            Validation results dictionary
        """
        # Parse the signal
        signal = SignalParser.parse_message(
            message_text,
            source,
            message_id=0  # No ID for manual
        )

        if not signal:
            return {
                "error": "Could not parse signal from message",
                "message": message_text
            }

        # Validate against your system
        result = await self.validator.validate_signal(signal)
        self.results.append(result)

        return {
            "parsed_signal": {
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry": str(signal.entry_price),
                "stop_loss": str(signal.stop_loss),
                "take_profits": [str(tp) for tp in signal.take_profits],
                "reasoning": signal.reasoning
            },
            "validation": {
                "overall_score": result.overall_score,
                "direction_match": result.direction_match,
                "entry_match": result.entry_within_tolerance,
                "sl_match": result.sl_within_tolerance,
                "smc_pattern_match": result.smc_pattern_match,
                "our_signal": result.our_signal
            },
            "recommendation": self._get_recommendation(result)
        }

    def _get_recommendation(self, result) -> str:
        """Get trading recommendation based on validation"""
        if result.overall_score >= 80:
            return "HIGH CONFIDENCE - Signals strongly align"
        elif result.overall_score >= 60:
            return "MODERATE - Partial alignment, verify key levels"
        elif result.overall_score >= 40:
            return "LOW - Significant differences, use caution"
        else:
            return "MISMATCH - Signals don't align, investigate why"

    def get_validation_summary(self) -> dict:
        """Get summary of all validated signals"""
        if not self.results:
            return {"message": "No signals validated yet"}

        return {
            "total_validated": len(self.results),
            "average_score": sum(r.overall_score for r in self.results) / len(self.results),
            "high_confidence": sum(1 for r in self.results if r.overall_score >= 80),
            "direction_accuracy": sum(1 for r in self.results if r.direction_match) / len(self.results) * 100
        }


# Example usage script
async def validate_telegram_signals():
    """Example of validating Telegram signals"""

    # Your system's API
    from app.engine import TradingSystemAPI
    system_api = TradingSystemAPI()

    validator = ManualSignalValidator(system_api)

    # Example Telegram messages to validate
    telegram_messages = [
        """
        🔥 BTCUSDT LONG 🔥
        Entry: 52000
        SL: 51000
        TP1: 53000
        TP2: 54000
        TP3: 55000

        Reason: 4H BOS confirmed, retest of broken resistance
        """,

        """
        ETHUSDT
        SELL Signal
        Entry Zone: 3250-3280
        Stop Loss: 3350
        Take Profit: 3150, 3050, 2950

        Daily Order Block rejection
        """,

        """
        💎 Premium Signal 💎
        $SOL - SOLUSDT

        BUY NOW @ 98.50

        Targets:
        🎯 102
        🎯 105
        🎯 110

        Stop Loss: 95

        4H CHOCH + FVG fill
        """
    ]

    # Validate each message
    for i, msg in enumerate(telegram_messages, 1):
        print(f"\n{'='*50}")
        print(f"Validating Signal {i}")
        print(f"{'='*50}")

        result = await validator.validate_pasted_signal(msg, "Premium SMC Signals")

        print(f"Parsed: {result['parsed_signal']['symbol']} {result['parsed_signal']['direction']}")
        print(f"Score: {result['validation']['overall_score']}%")
        print(f"Recommendation: {result['recommendation']}")

        if result['validation']['our_signal']:
            print(f"Our system: {result['validation']['our_signal']['direction']} at {result['validation']['our_signal']['entry']}")
        else:
            print("Our system: No signal")

    # Final summary
    print(f"\n{'='*50}")
    print("VALIDATION SUMMARY")
    print(f"{'='*50}")
    summary = validator.get_validation_summary()
    print(f"Total signals: {summary['total_validated']}")
    print(f"Average score: {summary['average_score']:.1f}%")
    print(f"High confidence: {summary['high_confidence']}")
    print(f"Direction accuracy: {summary['direction_accuracy']:.1f}%")


if __name__ == '__main__':
    asyncio.run(validate_telegram_signals())