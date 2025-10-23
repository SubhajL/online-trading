"""
Manual Thai Signal Validation Tool

Since you can't screenshot or forward from the Telegram group,
this tool helps you quickly input and validate signals.
"""

import asyncio
from datetime import datetime

from .telegram_signal_validator import TelegramSignalValidator
from .thai_signal_parser import (
    ThaiSignalValidator,
    parse_mixed_thai_english,
)


class ManualThaiSignalValidator:
    """Manual validation tool for Thai SMC signals"""

    def __init__(self, system_api):
        self.system_api = system_api
        self.validator = TelegramSignalValidator({}, system_api)
        self.thai_helper = ThaiSignalValidator()
        self.validation_log = []

    async def validate_thai_signal(self, manual_input: str) -> dict:
        """
        Validate manually typed Thai signal

        Input can be:
        1. Full Thai format copied from Telegram
        2. Quick format: USDJPY SELL 150.50 151.00 150.00,149.50 H1
        3. Mixed Thai/English
        """

        # Try parsing as quick format first
        if " " in manual_input and len(manual_input.split()) >= 5:
            quick_result = self.thai_helper.parse_quick_format(manual_input)
            if quick_result and quick_result["parsed"]:
                signal = quick_result["parsed"]
            else:
                # Try regular parsing
                signal = parse_mixed_thai_english(manual_input)
        else:
            # Full text parsing
            signal = parse_mixed_thai_english(manual_input)

        if not signal:
            return {
                "error": "ไม่สามารถแปลงสัญญาณได้ (Could not parse signal)",
                "suggestion": "Please use format: SYMBOL DIRECTION ENTRY SL TP1,TP2 TIMEFRAME",
                "template": self.thai_helper.get_input_template(),
            }

        # Validate against your system
        validation_result = await self.validator.validate_signal(signal)

        # Log for history
        self.validation_log.append({
            "time": datetime.now(),
            "signal": signal,
            "result": validation_result,
        })

        # Prepare response
        return {
            "parsed": {
                "symbol": signal.symbol,
                "direction": signal.direction,
                "entry": str(signal.entry_price) if signal.entry_price > 0 else "Manual entry needed",
                "sl": str(signal.stop_loss) if signal.stop_loss > 0 else "Not specified",
                "tps": [str(tp) for tp in signal.take_profits],
                "timeframe": signal.reasoning.split()[2] if "Signal" in signal.reasoning else "H4",
            },
            "validation": {
                "score": validation_result.overall_score,
                "match": "✅" if validation_result.overall_score >= 70 else "❌",
                "details": {
                    "ทิศทาง (Direction)": "✅" if validation_result.direction_match else "❌",
                    "ราคาเข้า (Entry)": "✅" if validation_result.entry_within_tolerance else "❌",
                    "Stop Loss": "✅" if validation_result.sl_within_tolerance else "❌",
                    "SMC Pattern": "✅" if validation_result.smc_pattern_match else "❌",
                },
            },
            "recommendation": self._get_thai_recommendation(validation_result.overall_score),
            "your_system": self._format_system_signal(validation_result.our_signal),
        }

    def _get_thai_recommendation(self, score: float) -> dict:
        """Get recommendation in Thai and English"""
        if score >= 80:
            return {
                "thai": "✅ ความเชื่อมั่นสูง - สัญญาณตรงกัน",
                "english": "HIGH CONFIDENCE - Signals align",
                "action": "Safe to follow",
            }
        if score >= 60:
            return {
                "thai": "⚠️ ความเชื่อมั่นปานกลาง - ตรวจสอบระดับสำคัญ",
                "english": "MODERATE - Verify key levels",
                "action": "Double-check entry/SL",
            }
        return {
            "thai": "❌ ไม่ตรงกัน - ระวัง",
            "english": "MISMATCH - Use caution",
            "action": "Wait for better setup",
        }

    def _format_system_signal(self, our_signal: dict) -> dict:
        """Format your system's signal for comparison"""
        if not our_signal:
            return {
                "status": "ไม่มีสัญญาณ (No signal)",
                "reason": "Your system has no signal at this time",
            }

        return {
            "status": "มีสัญญาณ (Has signal)",
            "direction": our_signal.get("direction"),
            "entry": str(our_signal.get("entry", "N/A")),
            "sl": str(our_signal.get("stop_loss", "N/A")),
            "confidence": our_signal.get("confidence", "N/A"),
        }

    def get_quick_input_guide(self) -> str:
        """Get guide for quick input"""
        return """
        🚀 QUICK INPUT GUIDE 🚀

        Format: SYMBOL DIRECTION ENTRY SL TP1,TP2,TP3 TIMEFRAME

        Examples:
        - BTCUSDT BUY 42000 41000 43000,44000,45000 H4
        - EURUSD SELL 1.0950 1.1000 1.0900,1.0850 H1
        - USDJPY SELL 150.50 151.00 150.00,149.50 H1

        Thai Signal? Just copy the text and paste!
        สัญญาณ : SELL
        สินทรัพย์ : USDJPY
        ...
        """

    def get_validation_summary(self) -> dict:
        """Get summary of today's validations"""
        today_logs = [
            log for log in self.validation_log
            if log["time"].date() == datetime.now().date()
        ]

        if not today_logs:
            return {"message": "No validations today"}

        total = len(today_logs)
        high_confidence = sum(1 for log in today_logs if log["result"].overall_score >= 80)
        avg_score = sum(log["result"].overall_score for log in today_logs) / total

        return {
            "วันนี้ (Today)": {
                "signals_checked": total,
                "high_confidence": high_confidence,
                "average_score": f"{avg_score:.1f}%",
                "match_rate": f"{high_confidence / total * 100:.0f}%",
            },
            "recent_signals": [
                {
                    "time": log["time"].strftime("%H:%M"),
                    "symbol": log["signal"].symbol,
                    "direction": log["signal"].direction,
                    "score": f"{log['result'].overall_score}%",
                }
                for log in today_logs[-5:]  # Last 5 signals
            ],
        }


# Interactive CLI for manual validation
async def interactive_validator():
    """Interactive command-line validator"""
    print("""
    📱 Thai Signal Validator - Manual Input Mode 📱

    Since you can't screenshot the Telegram group,
    just type what you see!

    Options:
    1. Quick format: SYMBOL DIR ENTRY SL TP1,TP2 TF
    2. Copy Thai text directly
    3. Type 'help' for examples
    4. Type 'summary' for today's results
    5. Type 'quit' to exit
    """)

    # Mock system API for demo
    from app.engine import TradingSystemAPI
    system_api = TradingSystemAPI()

    validator = ManualThaiSignalValidator(system_api)

    while True:
        print("\n" + "="*50)
        user_input = input("Enter signal (or command): ").strip()

        if user_input.lower() == "quit":
            break
        if user_input.lower() == "help":
            print(validator.get_quick_input_guide())
            continue
        if user_input.lower() == "summary":
            summary = validator.get_validation_summary()
            print(f"\nToday's Summary: {summary}")
            continue

        # Validate the signal
        try:
            result = await validator.validate_thai_signal(user_input)

            if "error" in result:
                print(f"\n❌ Error: {result['error']}")
                print(f"💡 Suggestion: {result['suggestion']}")
            else:
                print("\n✅ Parsed Signal:")
                print(f"   Symbol: {result['parsed']['symbol']}")
                print(f"   Direction: {result['parsed']['direction']}")
                print(f"   Entry: {result['parsed']['entry']}")
                print(f"   SL: {result['parsed']['sl']}")
                print(f"   TPs: {', '.join(result['parsed']['tps'])}")

                print(f"\n📊 Validation Score: {result['validation']['score']}%")
                print(f"   Recommendation: {result['recommendation']['thai']}")
                print(f"   ({result['recommendation']['english']})")
                print(f"   Action: {result['recommendation']['action']}")

                print("\n🤖 Your System:")
                print(f"   Status: {result['your_system']['status']}")
                if result["your_system"].get("direction"):
                    print(f"   Direction: {result['your_system']['direction']}")
                    print(f"   Entry: {result['your_system']['entry']}")

        except Exception as e:
            print(f"Error processing: {e}")


# Quick validation function for scripts
async def quick_validate(signal_text: str):
    """Quick validation for use in scripts"""
    from app.engine import TradingSystemAPI
    system_api = TradingSystemAPI()

    validator = ManualThaiSignalValidator(system_api)
    result = await validator.validate_thai_signal(signal_text)

    return result


if __name__ == "__main__":
    # Run interactive validator
    asyncio.run(interactive_validator())
