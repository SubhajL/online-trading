"""
Thai Language Signal Parser for SMC Signals

Specialized parser for Thai SMC trading signals.
"""

from datetime import UTC, datetime
from decimal import Decimal
import re

from .telegram_signal_validator import SignalParser, TelegramSignal


class ThaiSignalParser(SignalParser):
    """Parser for Thai language trading signals"""

    # Thai keywords mapping
    THAI_MAPPINGS = {
        "direction": {
            "ซื้อ": "BUY",
            "ขาย": "SELL",
            "SELL": "SELL",
            "BUY": "BUY",
            "LONG": "BUY",
            "SHORT": "SELL",
        },
        "fields": {
            "สัญญาณ": "signal",
            "สินทรัพย์": "symbol",
            "กรอบเวลา": "timeframe",
            "คำแนะนำ": "recommendation",
            "ราคาเปิด": "entry",
            "ราคาเข้า": "entry",
            "เป้าหมาย": "tp",
            "ตัดขาดทุน": "sl",
            "SL": "sl",
            "TP": "tp",
        },
        "timeframes": {
            "H1": "1H",
            "H4": "4H",
            "D1": "1D",
            "W1": "1W",
            "M1": "1M",
            "1ชั่วโมง": "1H",
            "4ชั่วโมง": "4H",
            "รายวัน": "1D",
        },
    }

    @classmethod
    def parse_thai_signal(
        cls, text: str, source: str = "Thai SMC Group",
    ) -> TelegramSignal | None:
        """
        Parse Thai language signal

        Expected format from image:
        - สัญญาณ : SELL
        - สินทรัพย์ : USDJPY
        - กรอบเวลา : H1
        - คำแนะนำ : ตราจุด Trade Set-up
        """

        # Extract components using regex
        patterns = {
            "direction": re.compile(r"สัญญาณ\s*[:：]\s*(\w+)", re.IGNORECASE),
            "symbol": re.compile(r"สินทรัพย์\s*[:：]\s*(\w+)", re.IGNORECASE),
            "timeframe": re.compile(r"กรอบเวลา\s*[:：]\s*(\w+)", re.IGNORECASE),
            "entry": re.compile(
                r"(?:ราคาเข้า|ราคาเปิด|Entry)\s*[:：]\s*([\d.]+)", re.IGNORECASE,
            ),
            "sl": re.compile(
                r"(?:ตัดขาดทุน|SL|Stop Loss)\s*[:：]\s*([\d.]+)", re.IGNORECASE,
            ),
            "tp": re.compile(
                r"(?:เป้าหมาย|TP|Target)\s*[:：]\s*([\d.,\s]+)", re.IGNORECASE,
            ),
        }

        extracted = {}
        for field, pattern in patterns.items():
            match = pattern.search(text)
            if match:
                extracted[field] = match.group(1).strip()

        # Check required fields
        if not all(k in extracted for k in ["direction", "symbol"]):
            return None

        # Process direction
        direction = extracted["direction"].upper()
        if direction in cls.THAI_MAPPINGS["direction"]:
            direction = cls.THAI_MAPPINGS["direction"][direction]
        else:
            # Try to find Thai direction in text
            for thai, eng in cls.THAI_MAPPINGS["direction"].items():
                if thai in text:
                    direction = eng
                    break

        # Process symbol - ensure it ends with USDT for crypto
        symbol = extracted["symbol"].upper()
        if not symbol.endswith("USDT") and not any(
            currency in symbol for currency in ["USD", "EUR", "GBP", "JPY"]
        ):
            symbol += "USDT"

        # Process timeframe
        timeframe = extracted.get("timeframe", "H4").upper()
        if timeframe in cls.THAI_MAPPINGS["timeframes"]:
            timeframe = cls.THAI_MAPPINGS["timeframes"][timeframe]

        # Build reasoning from Thai text
        reasoning = f"SMC Signal {timeframe}"
        if "MM" in text:
            reasoning += " - Money Management"
        if "Trade Set-up" in text or "ตราจุด Trade Set-up" in text:
            reasoning += " - Trade Setup Confirmed"

        # Create signal
        try:
            entry_price = Decimal(extracted.get("entry", "0"))
            stop_loss = Decimal(extracted.get("sl", "0"))

            # Parse TPs
            take_profits = []
            if "tp" in extracted:
                tp_values = re.findall(r"[\d.]+", extracted["tp"])
                take_profits = [Decimal(tp) for tp in tp_values]

            # If no entry price but we have a chart, might need manual entry
            if entry_price == 0:
                reasoning += " - Manual entry required"

            return TelegramSignal(
                timestamp=datetime.now(UTC),
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profits=take_profits,
                reasoning=reasoning,
                source=source,
                message_id=0,
                raw_text=text,
            )

        except (ValueError, Exception) as e:
            print(f"Error parsing Thai signal: {e}")
            return None


class ThaiSignalTemplate:
    """Templates for common Thai signal formats"""

    @staticmethod
    def create_input_template() -> str:
        """Create a template for manual input"""
        return """
📊 Thai Signal Input Template 📊

สัญญาณ : [SELL/BUY]
สินทรัพย์ : [USDJPY/BTCUSDT/etc]
กรอบเวลา : [H1/H4/D1]

ราคาเข้า : [Entry price]
ตัดขาดทุน : [Stop loss]
เป้าหมาย : [TP1, TP2, TP3]

คำแนะนำ : [Additional notes]
---
Example:
สัญญาณ : SELL
สินทรัพย์ : USDJPY
กรอบเวลา : H1

ราคาเข้า : 150.50
ตัดขาดทุน : 151.00
เป้าหมาย : 150.00, 149.50, 149.00
"""

    @staticmethod
    def quick_input_format() -> str:
        """Simplified format for quick input"""
        return """
Quick Format:
SYMBOL DIRECTION ENTRY SL TP1,TP2,TP3 TIMEFRAME

Example:
USDJPY SELL 150.50 151.00 150.00,149.50,149.00 H1
"""


def parse_mixed_thai_english(text: str) -> TelegramSignal | None:
    """
    Parse signals that mix Thai and English
    Like: "🚨SMC Hybrid Signal🚨"
    """
    # First try Thai parser
    signal = ThaiSignalParser.parse_thai_signal(text)

    if not signal:
        # Fall back to English parser
        signal = SignalParser.parse_message(text, "Thai SMC Hybrid", 0)

    return signal


# Manual validation helper
class ThaiSignalValidator:
    """Helper for validating Thai signals"""

    def __init__(self):
        self.templates = ThaiSignalTemplate()

    def get_input_template(self) -> str:
        """Get template for manual signal input"""
        return self.templates.create_input_template()

    def parse_quick_format(self, quick_input: str) -> dict | None:
        """
        Parse quick format: USDJPY SELL 150.50 151.00 150.00,149.50 H1
        """
        parts = quick_input.strip().split()

        if len(parts) < 6:
            return None

        try:
            symbol = parts[0]
            direction = parts[1]
            entry = parts[2]
            sl = parts[3]
            tps = parts[4].split(",")
            timeframe = parts[5]

            # Format as Thai signal
            thai_format = f"""
            สัญญาณ : {direction}
            สินทรัพย์ : {symbol}
            กรอบเวลา : {timeframe}
            ราคาเข้า : {entry}
            ตัดขาดทุน : {sl}
            เป้าหมาย : {", ".join(tps)}
            """

            return {
                "formatted_text": thai_format,
                "parsed": ThaiSignalParser.parse_thai_signal(thai_format),
            }

        except Exception as e:
            print(f"Error parsing quick format: {e}")
            return None


# Example usage
if __name__ == "__main__":
    # Test with the visible signal from image
    test_signal = """
    🚨AI-Gal-i Bot / Captain Trading🚨

    ⚠️ตรวจพบสัญญาณเข้าเทรด⚠️

    🚨SMC Hybrid Signal🚨

    📉สัญญาณ : SELL
    💰สินทรัพย์ : USDJPY
    ⏰กรอบเวลา : H1

    ⛔ คำแนะนำ : ตราจุด Trade Set-up
    ก่อนเทรดและบริหารความเสี่ยง MM
    เสมอ✅

    👤Jarvis Bot / Captain Trading
    """

    # Parse the signal
    signal = ThaiSignalParser.parse_thai_signal(test_signal)

    if signal:
        print("Parsed Signal:")
        print(f"Symbol: {signal.symbol}")
        print(f"Direction: {signal.direction}")
        print("Timeframe: H1")
        print(f"Reasoning: {signal.reasoning}")
    else:
        print("Could not parse signal")

    # Test quick format
    validator = ThaiSignalValidator()
    quick = validator.parse_quick_format(
        "USDJPY SELL 150.50 151.00 150.00,149.50,149.00 H1",
    )
    if quick:
        print("\nQuick format parsed:")
        print(quick["formatted_text"])
