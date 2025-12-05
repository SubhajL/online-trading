"""Tests for topic to EventType mapping in event bus."""

import pytest

from app.engine.bus import TOPIC_TO_EVENT_TYPE
from app.engine.models import EventType

# Complete expected mapping from topic to EventType
EXPECTED_TOPIC_MAPPINGS: dict[str, EventType] = {
    "candles.v1": EventType.CANDLE_UPDATE,
    "features.v1": EventType.FEATURES_CALCULATED,
    "smc_events.v1": EventType.SMC_SIGNAL,
    "zones.v1": EventType.SMC_SIGNAL,
    "signals_raw.v1": EventType.RETEST_SIGNAL,
    "decision.v1": EventType.TRADING_DECISION,
    "order_update.v1": EventType.ORDER_PLACED,
    "regime.v1": EventType.REGIME_UPDATE,
    "news_window.v1": EventType.NEWS_ALERT,
    "funding_window.v1": EventType.FUNDING_ALERT,
}


class TestTopicToEventTypeMapping:
    """Tests for TOPIC_TO_EVENT_TYPE completeness and correctness."""

    @pytest.mark.parametrize(
        ("topic", "expected_event_type"),
        list(EXPECTED_TOPIC_MAPPINGS.items()),
    )
    def test_topic_maps_to_correct_event_type(
        self,
        topic: str,
        expected_event_type: EventType,
    ) -> None:
        """Each topic maps to the correct EventType value."""
        assert TOPIC_TO_EVENT_TYPE.get(topic) == expected_event_type

    def test_unknown_topic_returns_none(self) -> None:
        """Unrecognized topic returns None from dict.get."""
        assert TOPIC_TO_EVENT_TYPE.get("unknown.v1") is None

    def test_mapping_count_matches_expected(self) -> None:
        """Mapping has exactly the expected number of entries."""
        expected_count = len(EXPECTED_TOPIC_MAPPINGS)
        actual_count = len(TOPIC_TO_EVENT_TYPE)
        assert actual_count == expected_count, (
            f"Expected {expected_count} mappings, got {actual_count}"
        )

    def test_no_extra_mappings_beyond_expected(self) -> None:
        """No unexpected topics exist in the mapping."""
        extra_topics = set(TOPIC_TO_EVENT_TYPE.keys()) - set(EXPECTED_TOPIC_MAPPINGS.keys())
        assert not extra_topics, f"Unexpected topics in mapping: {extra_topics}"

    def test_no_missing_mappings_from_expected(self) -> None:
        """All expected topics exist in the mapping."""
        missing_topics = set(EXPECTED_TOPIC_MAPPINGS.keys()) - set(TOPIC_TO_EVENT_TYPE.keys())
        assert not missing_topics, f"Missing topics from mapping: {missing_topics}"
