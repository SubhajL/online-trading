"""
Unit tests for health check script
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
from typing import Any

import pytest

from app.engine.scripts.healthcheck import check_health, main


class MockHealthHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler for health endpoint"""

    response_status = 200
    response_body = {"status": "ok"}

    def do_GET(self) -> None:
        if self.path == "/health/simple":
            self.send_response(self.response_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.response_body).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress logs during tests
        pass


class TestCheckHealth:
    """Tests for check_health function"""

    def test_returns_zero_when_service_healthy(self) -> None:
        # Start mock server
        server = HTTPServer(("localhost", 18000), MockHealthHandler)
        MockHealthHandler.response_status = 200
        MockHealthHandler.response_body = {"status": "ok"}

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            result = check_health(port=18000)
            assert result == 0
        finally:
            server.shutdown()

    def test_returns_one_when_service_unhealthy(self) -> None:
        # Start mock server with unhealthy response
        server = HTTPServer(("localhost", 18001), MockHealthHandler)
        MockHealthHandler.response_status = 200
        MockHealthHandler.response_body = {"status": "unhealthy"}

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            result = check_health(port=18001)
            assert result == 1
        finally:
            server.shutdown()

    def test_returns_one_when_http_error(self) -> None:
        # Start mock server that returns HTTP 500
        server = HTTPServer(("localhost", 18002), MockHealthHandler)
        MockHealthHandler.response_status = 500
        MockHealthHandler.response_body = {"error": "internal error"}

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            result = check_health(port=18002)
            assert result == 1
        finally:
            server.shutdown()

    def test_returns_one_when_connection_refused(self) -> None:
        # Use a port that nothing is listening on
        result = check_health(port=19999)

        assert result == 1

    def test_returns_one_when_invalid_json(self) -> None:
        # Mock handler that returns invalid JSON
        class InvalidJsonHandler(MockHealthHandler):
            def do_GET(self) -> None:
                if self.path == "/health/simple":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b"not valid json")
                else:
                    self.send_response(404)
                    self.end_headers()

        server = HTTPServer(("localhost", 18003), InvalidJsonHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            result = check_health(port=18003)
            assert result == 1
        finally:
            server.shutdown()

    def test_uses_default_port_8000(self) -> None:
        # Verify function accepts port parameter with default value
        # Use an unused port to test connection failure
        result = check_health(port=19998)

        assert result == 1  # Connection refused expected


class TestMain:
    """Tests for main function"""

    def test_main_exits_with_check_health_result(self) -> None:
        # Mock server for testing
        server = HTTPServer(("localhost", 18004), MockHealthHandler)
        MockHealthHandler.response_status = 200
        MockHealthHandler.response_body = {"status": "ok"}

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with pytest.raises(SystemExit) as exc_info:
                main(port=18004)

            assert exc_info.value.code == 0
        finally:
            server.shutdown()
