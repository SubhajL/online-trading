from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_global_exception_handler_redacts_internal_details() -> None:
    from app.engine.main import global_exception_handler

    response = await global_exception_handler(None, RuntimeError("database password leaked"))
    body = json.loads(response.body)

    assert response.status_code == 500
    assert body["error"] == "Internal server error"
    assert body["message"] == "An unexpected error occurred"
    assert "password" not in body["message"].lower()
