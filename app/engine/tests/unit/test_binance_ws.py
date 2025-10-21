"""
Unit tests for Binance WebSocket client URL construction
"""

import pytest

from app.engine.ingest.binance_ws import build_combined_stream_url


class TestBuildCombinedStreamUrl:
    """Tests for WebSocket URL construction"""

    def test_single_stream_creates_valid_url(self) -> None:
        base_url = "wss://stream.binance.com:9443/ws/"
        streams = ["btcusdt@kline_1m"]

        result = build_combined_stream_url(base_url, streams)

        assert result == "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m"

    def test_multiple_streams_joined_with_slash(self) -> None:
        base_url = "wss://stream.binance.com:9443/ws/"
        streams = ["btcusdt@kline_1m", "ethusdt@kline_5m", "bnbusdt@ticker"]

        result = build_combined_stream_url(base_url, streams)

        assert result == "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/ethusdt@kline_5m/bnbusdt@ticker"

    def test_testnet_host_preserved(self) -> None:
        base_url = "wss://testnet.binance.vision/ws/"
        streams = ["btcusdt@kline_15m"]

        result = build_combined_stream_url(base_url, streams)

        assert result.startswith("wss://testnet.binance.vision/stream?streams=")
        assert "btcusdt@kline_15m" in result

    def test_uses_stream_endpoint_with_query_parameter(self) -> None:
        base_url = "wss://stream.binance.com:9443/ws/"
        streams = ["btcusdt@kline_1h"]

        result = build_combined_stream_url(base_url, streams)

        assert "/stream?streams=" in result
        assert "/ws/" not in result.split("stream")[1]

    def test_empty_streams_returns_base_stream_url(self) -> None:
        base_url = "wss://stream.binance.com:9443/ws/"
        streams = []

        result = build_combined_stream_url(base_url, streams)

        assert result == "wss://stream.binance.com:9443/stream?streams="

    def test_preserves_port_in_url(self) -> None:
        base_url = "wss://stream.binance.com:9443/ws/"
        streams = ["btcusdt@kline_1m"]

        result = build_combined_stream_url(base_url, streams)

        assert ":9443" in result

    def test_handles_url_without_trailing_slash(self) -> None:
        base_url = "wss://testnet.binance.vision/ws"
        streams = ["btcusdt@kline_5m"]

        result = build_combined_stream_url(base_url, streams)

        assert result == "wss://testnet.binance.vision/stream?streams=btcusdt@kline_5m"

    def test_stream_order_preserved(self) -> None:
        base_url = "wss://stream.binance.com:9443/ws/"
        streams = ["zzz@kline_1m", "aaa@kline_5m", "mmm@ticker"]

        result = build_combined_stream_url(base_url, streams)

        assert result == "wss://stream.binance.com:9443/stream?streams=zzz@kline_1m/aaa@kline_5m/mmm@ticker"
