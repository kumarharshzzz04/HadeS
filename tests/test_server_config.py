"""Env-overridable host/port/CORS (plan Task 0.4).

Run:  python -m pytest tests/test_server_config.py -q
"""
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server  # noqa: E402


def test_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv("HADES_CORS_ORIGINS", "http://127.0.0.1:1234")
    importlib.reload(server)
    try:
        assert server.ALLOWED_ORIGINS == ["http://127.0.0.1:1234"]
    finally:
        monkeypatch.undo()
        importlib.reload(server)


def test_cors_defaults_are_the_dev_ports(monkeypatch):
    monkeypatch.delenv("HADES_CORS_ORIGINS", raising=False)
    importlib.reload(server)
    try:
        assert server.ALLOWED_ORIGINS == [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]
    finally:
        importlib.reload(server)


def test_cors_list_is_trimmed_and_empties_dropped(monkeypatch):
    monkeypatch.setenv("HADES_CORS_ORIGINS", "http://a:1 , http://b:2 ,")
    importlib.reload(server)
    try:
        assert server.ALLOWED_ORIGINS == ["http://a:1", "http://b:2"]
    finally:
        monkeypatch.undo()
        importlib.reload(server)


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
