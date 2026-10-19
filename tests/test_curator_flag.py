"""Curator switch (plan Task 0.8): off by default, and off really skips the LLM.

Run:  python -m pytest tests/test_curator_flag.py -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402
import rag_chat as rc  # noqa: E402


def _cands():
    """Three candidates far enough apart in time to become three clusters."""
    return [
        {"text": "we define a function with def and a body", "score": 0.90, "label": "L1",
         "start": 10.0, "end": 40.0, "part": 0, "youtube_url": None},
        {"text": "pip installs packages from PyPI", "score": 0.55, "label": "L2",
         "start": 900.0, "end": 940.0, "part": 0, "youtube_url": None},
        {"text": "strings are sequences of characters", "score": 0.50, "label": "L3",
         "start": 1800.0, "end": 1840.0, "part": 0, "youtube_url": None},
    ]


def test_flag_exists_and_defaults_off():
    assert config.LLM_CURATOR_ENABLED is False


def test_use_llm_false_never_calls_the_llm(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("ask_llm was called with the curator disabled")

    monkeypatch.setattr(rc, "ask_llm", boom)
    monkeypatch.setattr(rc, "_search_with_scores", lambda q, k=None: _cands())

    out = rc.search_chunks_curated("what are functions", use_llm=False)

    assert out["main"] and out["context"]


def test_use_llm_true_does_ask_the_llm(monkeypatch):
    calls = []
    monkeypatch.setattr(rc, "ask_llm", lambda prompt: calls.append(prompt) or '{"main": [0, 1]}')
    monkeypatch.setattr(rc, "_search_with_scores", lambda q, k=None: _cands())

    rc.search_chunks_curated("what are functions", use_llm=True)

    assert calls, "curator on must still ask the LLM"


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
