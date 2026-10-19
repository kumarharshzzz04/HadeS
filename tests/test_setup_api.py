"""First-run setup API (plan Batch 1, tasks 1.1-1.3, 1.5).

Run:  python -m pytest tests/test_setup_api.py -q
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402
import ollama_locator as ol  # noqa: E402
import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _tags(models, version="0.40.4"):
    return {"version": version, "models": [{"name": n} for n in models]}


def _fake_response(lines, ok=True, status_code=200):
    class R:
        def __init__(self):
            self.ok = ok
            self.status_code = status_code

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self, decode_unicode=True):
            return iter(lines)

    return R()


# ── status ────────────────────────────────────────────────────────────────────

def test_not_installed_anywhere(monkeypatch):
    monkeypatch.setattr(ol, "tags", lambda timeout=2.0: None)
    monkeypatch.setattr(ol, "port_conflict", lambda: False)
    monkeypatch.setattr(ol, "find_exe", lambda: None)
    s = ol.status()
    assert s["ollama_installed"] is False
    assert s["ollama_running"] is False
    assert s["model_present"] is False


def test_installed_but_stopped(monkeypatch, tmp_path):
    fake = tmp_path / "ollama.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(ol, "tags", lambda timeout=2.0: None)
    monkeypatch.setattr(ol, "port_conflict", lambda: False)
    monkeypatch.setattr(ol, "find_exe", lambda: str(fake))
    s = ol.status()
    assert s["ollama_installed"] is True and s["ollama_running"] is False


def test_prefix_match_is_not_a_match(monkeypatch):
    """llama3:latest must NOT count as llama3:8b present (review focus #3)."""
    monkeypatch.setattr(ol, "tags", lambda timeout=2.0: _tags(["llama3:latest"]))
    monkeypatch.setattr(ol, "find_exe", lambda: "x")
    monkeypatch.setattr(config, "OLLAMA_MODEL_NAME", "llama3:8b")
    assert ol.status()["model_present"] is False


def test_exact_tag_matches(monkeypatch):
    monkeypatch.setattr(ol, "tags", lambda timeout=2.0: _tags(["llama3:8b"]))
    monkeypatch.setattr(ol, "find_exe", lambda: "x")
    monkeypatch.setattr(config, "OLLAMA_MODEL_NAME", "llama3:8b")
    assert ol.status()["model_present"] is True


def test_port_conflict_when_something_else_owns_11434(monkeypatch):
    class R:
        ok = True

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(ol.requests, "get", lambda *a, **k: R())
    assert ol.port_conflict() is True


# ── start ─────────────────────────────────────────────────────────────────────

def test_start_is_idempotent_when_running(monkeypatch):
    monkeypatch.setattr(ol, "tags", lambda timeout=2.0: _tags([]))
    assert ol.start() == {"started": False, "error": None, "already_running": True}


def test_start_reports_not_installed(monkeypatch):
    monkeypatch.setattr(ol, "tags", lambda timeout=2.0: None)
    monkeypatch.setattr(ol, "find_exe", lambda: None)
    r = ol.start()
    assert r["started"] is False and "not installed" in r["error"]


# ── pull ──────────────────────────────────────────────────────────────────────

def test_pull_streams_progress_then_done(monkeypatch):
    lines = [
        json.dumps({"status": "pulling manifest"}),
        json.dumps({"status": "downloading", "completed": 10, "total": 100}),
        json.dumps({"status": "success"}),
    ]
    monkeypatch.setattr(ol.requests, "post", lambda *a, **k: _fake_response(lines))
    evts = list(ol.pull_events("llama3:8b"))
    assert evts[0]["status"] == "pulling manifest"
    assert any(e.get("total") for e in evts)
    assert evts[-1]["done"] is True


def test_pull_error_is_surfaced_not_swallowed(monkeypatch):
    lines = [json.dumps({"error": "model 'nope/x:1b' not found"})]
    monkeypatch.setattr(ol.requests, "post", lambda *a, **k: _fake_response(lines))
    evts = list(ol.pull_events("nope/x:1b"))
    assert "error" in evts[-1]


def test_pull_http_error_is_surfaced(monkeypatch):
    monkeypatch.setattr(ol.requests, "post", lambda *a, **k: _fake_response([], ok=False, status_code=500))
    evts = list(ol.pull_events("x"))
    assert "error" in evts[-1]


# ── routes ────────────────────────────────────────────────────────────────────

def test_setup_status_route_offers_models(monkeypatch):
    monkeypatch.setattr(server.ollama_locator, "status", lambda: {
        "ollama_running": True, "ollama_installed": True, "exe": "x", "version": "0.40.4",
        "model_present": True, "model_name": "llama3:8b", "models": ["llama3:8b"],
        "port_conflict": False,
    })
    r = TestClient(server.app).get("/api/setup/status")
    assert r.status_code == 200
    assert {m["name"] for m in r.json()["offered"]} == {"llama3.2:3b", "llama3:8b"}


def test_select_model_applies_and_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("HADES_STATE_DIR", str(tmp_path))
    original = config.OLLAMA_MODEL_NAME
    try:
        r = TestClient(server.app).post("/api/setup/select", json={"model": "llama3.2:3b"})
        assert r.status_code == 200
        assert config.OLLAMA_MODEL_NAME == "llama3.2:3b"          # effective now
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["model"] == "llama3.2:3b"                     # remembered next launch
    finally:
        config.OLLAMA_MODEL_NAME = original


def test_empty_model_name_is_rejected():
    r = TestClient(server.app).post("/api/setup/select", json={"model": "   "})
    assert r.status_code == 400


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
