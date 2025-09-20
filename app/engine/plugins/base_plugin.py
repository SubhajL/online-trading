"""
Base plugin interface for extending the trading engine.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

from ..types import Candle, TechnicalIndicators, BaseEvent


class BasePlugin(ABC):
    """
    Abstract base class for trading engine plugins.
    """

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.enabled = True

    @property
    @abstractmethod
    def inputs(self) -> Set[str]:
        """
        Define required input event types.
        Example: {"candles.15m", "indicators.macd", "smc.zones"}
        """
        pass

    @property
    @abstractmethod
    def outputs(self) -> Set[str]:
        """
        Define output event types this plugin produces.
        """
        pass

    @abstractmethod
    async def on_event(self, event: BaseEvent) -> Optional[List[BaseEvent]]:
        """
        Process an event and optionally return new events.
        """
        pass

    async def initialize(self):
        """
        Initialize the plugin (optional override).
        """
        pass

    async def cleanup(self):
        """
        Cleanup resources (optional override).
        """
        pass

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
    def inputs(self) -> Set[str]:
        return {"candles"}

    @property
    def outputs(self) -> Set[str]:
        return {"custom_indicators"}

    @abstractmethod
    async def calculate(self, candle: Candle) -> Dict[str, Any]:
        """
        Calculate custom indicators from candle data.
        """
        pass

    async def on_event(self, event: BaseEvent) -> Optional[List[BaseEvent]]:
        """
        Process candle events and calculate indicators.
        """
        if event.event_type.value == "candle_update":
            indicators = await self.calculate(event.metadata.get("candle"))
            if indicators:
                # Create custom indicator event
                return [
                    BaseEvent(
                        event_type=event.event_type,
                        timestamp=datetime.utcnow(),
                        symbol=event.symbol,
                        timeframe=event.timeframe,
                        metadata={"custom_indicators": indicators},
                    )
                ]
        return None


class SignalPlugin(BasePlugin):
    """
    Base class for custom signal generation plugins.
    """

    @property
    def inputs(self) -> Set[str]:
        return {"candles", "indicators"}

    @property
    def outputs(self) -> Set[str]:
        return {"signals"}

    @abstractmethod
    async def generate_signal(
        self, candle: Candle, indicators: TechnicalIndicators
    ) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal from candle and indicators.
        """
        pass

    async def on_event(self, event: BaseEvent) -> Optional[List[BaseEvent]]:
        """
        Process events and generate signals.
        """
        # Implementation would combine candle and indicator events
        # to generate trading signals
        return None
