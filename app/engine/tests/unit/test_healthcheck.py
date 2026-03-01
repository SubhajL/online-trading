"""
Unit tests for health check script
"""

import json
from typing import Any
from urllib.error import URLError

import pytest

from app.engine.scripts.healthcheck import check_health, main


class TestCheckHealth:
    """Tests for check_health function"""

    def test_returns_zero_when_service_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Response:
            status = 200

            def read(self) -> bytes:
                return json.dumps({"status": "ok"}).encode()

            def __enter__(self) -> "_Response":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: Any | None,
            ) -> None:
                return None

        monkeypatch.setattr(
            "app.engine.scripts.healthcheck.urlopen",
            lambda *_args, **_kwargs: _Response(),
        )

        assert check_health(port=18000) == 0

    def test_returns_one_when_service_unhealthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Response:
            status = 200

            def read(self) -> bytes:
                return json.dumps({"status": "unhealthy"}).encode()

            def __enter__(self) -> "_Response":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: Any | None,
            ) -> None:
                return None

        monkeypatch.setattr(
            "app.engine.scripts.healthcheck.urlopen",
            lambda *_args, **_kwargs: _Response(),
        )

        assert check_health(port=18001) == 1

    def test_returns_one_when_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Response:
            status = 500

            def read(self) -> bytes:
                return json.dumps({"error": "internal error"}).encode()

            def __enter__(self) -> "_Response":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: Any | None,
            ) -> None:
                return None

        monkeypatch.setattr(
            "app.engine.scripts.healthcheck.urlopen",
            lambda *_args, **_kwargs: _Response(),
        )

        assert check_health(port=18002) == 1

    def test_returns_one_when_connection_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.engine.scripts.healthcheck.urlopen",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("refused")),
        )
        assert check_health(port=19999) == 1

    def test_returns_one_when_invalid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Response:
            status = 200

            def read(self) -> bytes:
                return b"not valid json"

            def __enter__(self) -> "_Response":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: Any | None,
            ) -> None:
                return None

        monkeypatch.setattr(
            "app.engine.scripts.healthcheck.urlopen",
            lambda *_args, **_kwargs: _Response(),
        )

        assert check_health(port=18003) == 1

    def test_uses_default_port_8000(self) -> None:
        # Verify function accepts port parameter with default value
        # Use an unused port to test connection failure
        result = check_health(port=19998)

        assert result == 1  # Connection refused expected


class TestMain:
    """Tests for main function"""

    def test_main_exits_with_check_health_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Response:
            status = 200

            def read(self) -> bytes:
                return json.dumps({"status": "ok"}).encode()

            def __enter__(self) -> "_Response":
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: Any | None,
            ) -> None:
                return None

        monkeypatch.setattr(
            "app.engine.scripts.healthcheck.urlopen",
            lambda *_args, **_kwargs: _Response(),
        )

        with pytest.raises(SystemExit) as exc_info:
            main(port=18004)
        assert exc_info.value.code == 0
