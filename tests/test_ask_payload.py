"""`validation` must not cost anything unless switched on (plan Task 0.7).

The field was never read by any frontend version, so the default is now off.
Both halves are checked: the payload key disappears AND validate_grounding is
never called. Flipping the flag on must restore both.

Run:  python -m pytest tests/test_ask_payload.py -q
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402
import rag_chat  # noqa: E402
import server  # noqa: E402

_DETAIL = {"label": "L", "text": "ctx text", "start": 1.0, "end": 2.0, "part": 0,
           "youtube_url": None, "score": 0.9, "cluster_size": 1}
_CURATED = {"context": "ctx text", "main": [dict(_DETAIL)], "also": [], "labels": [],
            "details": [], "main_context": "ctx text", "clusters": []}


def test_default_flag_is_off():
    assert config.GROUNDING_VALIDATION is False


def _run_ask(monkeypatch, flag):
    """Drive server.ask() with the RAG core stubbed — no Ollama, no models."""
    monkeypatch.setattr(config, "GROUNDING_VALIDATION", flag)
    monkeypatch.setattr(rag_chat, "search_chunks_curated", lambda q, *a, **k: _CURATED)
    monkeypatch.setattr(rag_chat, "ask_llm_stream", lambda p: iter(["Hello", " world"]))
    monkeypatch.setattr(rag_chat, "curated_confidence", lambda curated: 1.0)
    calls = []
    monkeypatch.setattr(rag_chat, "validate_grounding",
                        lambda answer, cited: calls.append(answer) or {"passed": True})

    resp = server.ask(server.AskRequest(question="q", profile=None, history=[]))

    async def drain():
        return "".join([chunk async for chunk in resp.body_iterator])

    body = asyncio.run(drain())
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    return events[-1], calls


def test_payload_has_no_validation_and_never_calls_it(monkeypatch):
    final, calls = _run_ask(monkeypatch, False)
    assert final["type"] == "final"
    assert "validation" not in final
    assert calls == []


def test_flag_on_restores_the_field_and_the_call(monkeypatch):
    final, calls = _run_ask(monkeypatch, True)
    assert "validation" in final
    assert calls == ["Hello world"]


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
