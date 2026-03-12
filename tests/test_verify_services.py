from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


def _load_verify_services_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "verify_services.py"
    spec = importlib.util.spec_from_file_location("verify_services", script_path)
    assert spec is not None
    assert spec.loader is not None

    for name in ("psycopg2", "redis", "aiohttp"):
        sys.modules.setdefault(name, types.ModuleType(name))

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_ports_checks_loopback_only(monkeypatch):
    module = _load_verify_services_module()
    bind_calls: list[tuple[str, int]] = []

    class _FakeSocket:
        def bind(self, addr):
            bind_calls.append(addr)

        def close(self):
            return None

        def connect_ex(self, addr):
            return 1

    socket_module = types.SimpleNamespace(
        AF_INET=1,
        SOCK_STREAM=1,
        socket=lambda *_: _FakeSocket(),
    )
    monkeypatch.setitem(sys.modules, "socket", socket_module)

    verifier = module.ServiceVerifier()
    verifier.verify_ports()

    assert bind_calls
    assert all(host == "127.0.0.1" for host, _port in bind_calls)
