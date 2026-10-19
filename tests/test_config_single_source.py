"""Single source of truth for Ollama host + model name (plan Task 0.2).

Run:  python -m pytest tests/test_config_single_source.py -q
"""
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402


def test_no_duplicate_model_literal_outside_config_and_tests():
    """`llama3:8b` may live in config.py only. dev.py and server.py must interpolate it."""
    hits = []
    for p in pathlib.Path(config.BASE_DIR).glob("*.py"):
        if p.name in {"config.py", "checkup_timestamps.py"} or p.name.startswith("test_"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "llama3:8b" in line:
                hits.append(f"{p.name}:{i}")
    assert hits == [], f"duplicate model literal: {hits}"


def test_urls_derive_from_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9999")
    importlib.reload(config)
    try:
        assert config.OLLAMA_TAGS_URL == "http://127.0.0.1:9999/api/tags"
        assert config.OLLAMA_API_URL == "http://127.0.0.1:9999/api/generate"
    finally:
        monkeypatch.undo()
        importlib.reload(config)  # restore the default host for the rest of the session


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
