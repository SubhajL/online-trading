"""Tests for client order ID generation for idempotency."""

from uuid import UUID, uuid4

import pytest

from app.engine.decision.idempotency import (
    BINANCE_MAX_CLIENT_ORDER_ID_LENGTH,
    MAX_SUFFIX_LENGTH,
    InvalidSuffixError,
    generate_client_order_id,
)


class TestGenerateClientOrderId:
    """Tests for generate_client_order_id function."""

    def test_deterministic_same_inputs_produce_same_output(self) -> None:
        """Same decision_id and suffix produce identical client order IDs."""
        decision_id = UUID("12345678-1234-5678-1234-567812345678")
        suffix = "entry"

        result1 = generate_client_order_id(decision_id, suffix)
        result2 = generate_client_order_id(decision_id, suffix)

        assert result1 == result2

    def test_max_length_36_characters(self) -> None:
        """Client order ID never exceeds Binance 36 char limit."""
        decision_id = uuid4()

        result_no_suffix = generate_client_order_id(decision_id)
        result_with_suffix = generate_client_order_id(decision_id, "max-len-suffix1")

        assert len(result_no_suffix) <= BINANCE_MAX_CLIENT_ORDER_ID_LENGTH
        assert len(result_with_suffix) <= BINANCE_MAX_CLIENT_ORDER_ID_LENGTH

    def test_format_without_suffix(self) -> None:
        """Without suffix, format is eng-{id_short}."""
        decision_id = UUID("12345678-1234-5678-1234-567812345678")

        result = generate_client_order_id(decision_id)

        assert result.startswith("eng-")
        assert result == "eng-1234567812345678"

    def test_format_with_suffix(self) -> None:
        """With suffix, format is eng-{id_short}-{suffix}."""
        decision_id = UUID("12345678-1234-5678-1234-567812345678")
        suffix = "entry"

        result = generate_client_order_id(decision_id, suffix)

        assert result.startswith("eng-")
        assert "-entry" in result
        assert result == "eng-1234567812345678-entry"

    def test_unique_per_decision(self) -> None:
        """Different decision IDs produce different client order IDs."""
        decision_id_1 = uuid4()
        decision_id_2 = uuid4()
        suffix = "entry"

        result1 = generate_client_order_id(decision_id_1, suffix)
        result2 = generate_client_order_id(decision_id_2, suffix)

        assert result1 != result2

    def test_unique_per_suffix(self) -> None:
        """Same decision ID with different suffixes produce different IDs."""
        decision_id = uuid4()

        result_entry = generate_client_order_id(decision_id, "entry")
        result_sl = generate_client_order_id(decision_id, "sl")
        result_tp1 = generate_client_order_id(decision_id, "tp1")

        assert result_entry != result_sl
        assert result_sl != result_tp1
        assert result_entry != result_tp1

    def test_empty_suffix_same_as_no_suffix(self) -> None:
        """Empty string suffix behaves like no suffix."""
        decision_id = uuid4()

        result_empty = generate_client_order_id(decision_id, "")
        result_none = generate_client_order_id(decision_id)

        assert result_empty == result_none

    @pytest.mark.parametrize(
        "suffix",
        ["entry", "sl", "tp1", "tp2", "tp3", "close"],
    )
    def test_common_suffixes_produce_valid_ids(self, suffix: str) -> None:
        """Common trading suffixes produce valid client order IDs."""
        decision_id = uuid4()

        result = generate_client_order_id(decision_id, suffix)

        assert len(result) <= BINANCE_MAX_CLIENT_ORDER_ID_LENGTH
        assert result.startswith("eng-")
        assert suffix in result

    def test_suffix_too_long_raises_error(self) -> None:
        """Suffix exceeding max length raises InvalidSuffixError."""
        decision_id = uuid4()
        long_suffix = "x" * (MAX_SUFFIX_LENGTH + 1)

        with pytest.raises(InvalidSuffixError) as exc_info:
            generate_client_order_id(decision_id, long_suffix)

        assert "exceeds max length" in str(exc_info.value)

    def test_suffix_with_invalid_chars_raises_error(self) -> None:
        """Suffix with invalid characters raises InvalidSuffixError."""
        decision_id = uuid4()

        with pytest.raises(InvalidSuffixError) as exc_info:
            generate_client_order_id(decision_id, "has space")

        assert "invalid characters" in str(exc_info.value)

    @pytest.mark.parametrize(
        "invalid_suffix",
        ["has space", "has@symbol", "has.dot", "has/slash"],
    )
    def test_invalid_suffix_characters_rejected(self, invalid_suffix: str) -> None:
        """Various invalid characters in suffix are rejected."""
        decision_id = uuid4()

        with pytest.raises(InvalidSuffixError):
            generate_client_order_id(decision_id, invalid_suffix)

    @pytest.mark.parametrize(
        "valid_suffix",
        ["entry", "tp_1", "sl-main", "TP1", "close_all", "A1-b2_C3"],
    )
    def test_valid_suffix_characters_accepted(self, valid_suffix: str) -> None:
        """Alphanumeric, underscore, and hyphen are allowed in suffix."""
        decision_id = uuid4()

        result = generate_client_order_id(decision_id, valid_suffix)

        assert valid_suffix in result

    def test_max_length_suffix_works(self) -> None:
        """Suffix at exactly max length works correctly."""
        decision_id = uuid4()
        max_suffix = "x" * MAX_SUFFIX_LENGTH

        result = generate_client_order_id(decision_id, max_suffix)

        assert len(result) == BINANCE_MAX_CLIENT_ORDER_ID_LENGTH
        assert max_suffix in result
