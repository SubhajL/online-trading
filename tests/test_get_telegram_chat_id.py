from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "get_telegram_chat_id.py"
    )
    spec = importlib.util.spec_from_file_location("get_telegram_chat_id", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_requires_telegram_bot_token_env(monkeypatch, capsys):
    module = _load_script_module()
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert module.main() == 1

    captured = capsys.readouterr()
    assert "Please set TELEGRAM_BOT_TOKEN" in captured.out


def test_get_updates_uses_provided_bot_token(monkeypatch):
    module = _load_script_module()
    requested = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self, *_args, **_kwargs):
            return b'{\"ok\": false, \"result\": []}'

    def fake_get(url):
        requested["url"] = url
        return _Response()

    monkeypatch.setattr(module, "urlopen", fake_get)

    module.get_updates("test-token")

    assert requested["url"] == "https://api.telegram.org/bottest-token/getUpdates"
