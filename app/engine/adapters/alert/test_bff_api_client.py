"""Tests for BffApiClient - HTTP client for BFF API."""

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from app.engine.adapters.alert.bff_api_client import BffApiClient


class TestBffApiClientInit:
    """Tests for BffApiClient initialization."""

    def test_init_stores_base_url(self) -> None:
        """BffApiClient stores base_url from constructor."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        assert client._base_url == "http://localhost:8002"  # noqa: SLF001

    def test_init_stores_api_key(self) -> None:
        """BffApiClient stores api_key from constructor."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="secret-key")
        assert client._api_key == "secret-key"  # noqa: SLF001

    def test_init_session_is_none(self) -> None:
        """BffApiClient session is None before start."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        assert client._session is None  # noqa: SLF001


class TestBffApiClientLifecycle:
    """Tests for BffApiClient start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_session(self) -> None:
        """start() creates aiohttp ClientSession."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            assert client._session is not None  # noqa: SLF001
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_session(self) -> None:
        """stop() closes the aiohttp session."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        session = client._session  # noqa: SLF001
        await client.stop()
        assert client._session is None  # noqa: SLF001
        assert session.closed

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self) -> None:
        """stop() is safe to call without start()."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.stop()  # Should not raise


class TestBffApiClientPost:
    """Tests for BffApiClient.post() method."""

    @pytest.mark.asyncio
    async def test_post_sends_to_correct_url(self) -> None:
        """post() sends request to base_url + path."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"id": "123"})
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                return_value=mock_response,
            ) as mock_post:
                await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert call_args[0][0] == "http://localhost:8002/api/signals/alert"
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_includes_auth_header(self) -> None:
        """post() includes Authorization: Bearer header."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="secret-key")
        await client.start()
        try:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"id": "123"})
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                return_value=mock_response,
            ) as mock_post:
                await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                call_args = mock_post.call_args
                headers = call_args[1].get("headers", {})
                assert headers.get("Authorization") == "Bearer secret-key"
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_sends_json_payload(self) -> None:
        """post() sends payload as JSON body."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"id": "123"})
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            payload = {"symbol": "BTCUSDT", "side": "BUY"}
            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                return_value=mock_response,
            ) as mock_post:
                await client.post("/api/signals/alert", payload)
                call_args = mock_post.call_args
                assert call_args[1].get("json") == payload
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_returns_response_json(self) -> None:
        """post() returns parsed JSON response on success."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            expected = {"id": "signal-123", "status": "created"}
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=expected)
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                return_value=mock_response,
            ):
                result = await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                assert result == expected
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_returns_none_on_4xx_error(self) -> None:
        """post() returns None on 4xx HTTP error."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            mock_response = AsyncMock()
            mock_response.status = 400
            mock_response.text = AsyncMock(return_value="Bad Request")
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                return_value=mock_response,
            ):
                result = await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                assert result is None
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_returns_none_on_5xx_error(self) -> None:
        """post() returns None on 5xx HTTP error."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                return_value=mock_response,
            ):
                result = await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                assert result is None
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_returns_none_on_timeout(self) -> None:
        """post() returns None on request timeout."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                side_effect=TimeoutError(),
            ):
                result = await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                assert result is None
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_returns_none_on_connection_error(self) -> None:
        """post() returns None on connection error."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        await client.start()
        try:
            with patch.object(
                client._session,  # noqa: SLF001
                "post",
                side_effect=aiohttp.ClientError("Connection refused"),
            ):
                result = await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
                assert result is None
        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_post_returns_none_when_session_not_started(self) -> None:
        """post() returns None if session not started."""
        client = BffApiClient(base_url="http://localhost:8002", api_key="test-key")
        result = await client.post("/api/signals/alert", {"symbol": "BTCUSDT"})
        assert result is None
