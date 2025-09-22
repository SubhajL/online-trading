"""
Base plugin interface for extending the trading engine.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import BaseEvent, Candle, TechnicalIndicators


class BasePlugin(ABC):
    """
    Abstract base class for trading engine plugins.
    """

    def __init__(self, name: str, config: dict[str, Any] | None = None):
        self.name = name
        self.config = config or {}
        self.enabled = True

    @property
    @abstractmethod
    def inputs(self) -> set[str]:
        """
        Define required input event types.
        Example: {"candles.15m", "indicators.macd", "smc.zones"}
        """

    @property
    @abstractmethod
    def outputs(self) -> set[str]:
        """
        Define output event types this plugin produces.
        """

    @abstractmethod
    async def on_event(self, event: BaseEvent) -> list[BaseEvent] | None:
        """
        Process an event and optionally return new events.
        """

    async def initialize(self) -> None:
        """
        Initialize the plugin (optional override).
        """

    async def cleanup(self) -> None:
        """
        Cleanup resources (optional override).
        """

    def validate_config(self) -> bool:
        """
        Validate plugin configuration (optional override).
        """
        return True


class IndicatorPlugin(BasePlugin):
    """
    Base class for custom indicator plugins.
    """

    @property
    def inputs(self) -> set[str]:
        return {"candles"}

    @property
    def outputs(self) -> set[str]:
        return {"custom_indicators"}

    @abstractmethod
    async def calculate(self, candle: Candle) -> dict[str, Any]:
        """
        Calculate custom indicators from candle data.
        """

    async def on_event(self, event: BaseEvent) -> list[BaseEvent] | None:
        """
        Process candle events and calculate indicators.
        """
        if event.event_type.value == "candle_update":
            candle = event.metadata.get("candle")
            if not isinstance(candle, Candle):
                return None
            indicators = await self.calculate(candle)
            if indicators:
                # Create custom indicator event
                return [
                    BaseEvent(
                        event_type=event.event_type,
                        timestamp=datetime.utcnow(),
                        symbol=event.symbol,
                        timeframe=event.timeframe,
                        metadata={"custom_indicators": indicators},
                    ),
                ]
        return None


class SignalPlugin(BasePlugin):
    """
    Base class for custom signal generation plugins.
    """

    @property
    def inputs(self) -> set[str]:
        return {"candles", "indicators"}

    @property
    def outputs(self) -> set[str]:
        return {"signals"}

    @abstractmethod
    async def generate_signal(
        self,
        candle: Candle,
        indicators: TechnicalIndicators,
    ) -> dict[str, Any] | None:
        """
        Generate trading signal from candle and indicators.
        """

    async def on_event(self, event: BaseEvent) -> list[BaseEvent] | None:
        """
        Process events and generate signals.
        """
        # Implementation would combine candle and indicator events
        # to generate trading signals
        return None
