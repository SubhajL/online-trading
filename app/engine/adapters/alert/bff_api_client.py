"""HTTP client for BFF API."""

from http import HTTPStatus
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class BffApiClient:
    """Async HTTP client for posting to BFF API endpoints."""

    def __init__(self, base_url: str, token: str) -> None:
        """Initialize client with base URL and bearer token.

        Args:
            base_url: BFF base URL (e.g., http://localhost:8002)
            token: Token for Authorization header (Bearer)
        """
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Create aiohttp session. Must be called before post()."""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
            logger.info("BffApiClient session started")

    async def stop(self) -> None:
        """Close aiohttp session."""
        if self._session is not None:
            await self._session.close()
            self._session = None
            logger.info("BffApiClient session stopped")

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST JSON payload to BFF endpoint.

        Args:
            path: API path (e.g., /api/signals/alert)
            payload: JSON-serializable dict to send

        Returns:
            Parsed JSON response on success, None on error.
        """
        if self._session is None:
            logger.warning("BffApiClient: session not started, call start() first")
            return None

        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}

        try:
            async with self._session.post(url, json=payload, headers=headers) as resp:
                if resp.status >= HTTPStatus.BAD_REQUEST:
                    error_text = await resp.text()
                    logger.error(
                        "BffApiClient POST %s failed: %d %s",
                        path,
                        resp.status,
                        error_text[:200],
                    )
                    return None
                return await resp.json()
        except TimeoutError:
            logger.warning("BffApiClient POST %s timed out", path)
            return None
        except aiohttp.ClientError:
            logger.exception("BffApiClient POST %s error", path)
            return None
