"""The BM25 + RRF branch must still run end to end (plan Task 0.9).

`search_chunks_simple` and `search_chunks_detailed` had zero callers and were deleted.
The hybrid path stays — it is the documented opt-in for the reranker work — but it was
only kept alive by tests of its own helpers, so this exercises the real dispatch with
the model, index and metadata faked out.

Run:  python -m pytest tests/test_hybrid_path.py -q
"""
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402
import rag_chat as rc  # noqa: E402


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return np.ones((len(texts), 4), dtype="float32")


class _FakeIndex:
    def search(self, q, k):
        return np.array([[0.9, 0.5]], dtype="float32"), np.array([[1, 0]])


_META = [
    {"text": "a function is a reusable block of code", "start": 10, "end": 20, "part": 0},
    {"text": "csv files hold rows of data", "start": 500, "end": 520, "part": 0},
]


def test_hybrid_mode_runs_and_returns_candidates(monkeypatch):
    monkeypatch.setattr(config, "RETRIEVE_MODE", "hybrid")
    monkeypatch.setattr(config, "RERANK_ENABLED", False)
    monkeypatch.setattr(rc, "get_model", lambda: _FakeModel())
    monkeypatch.setattr(rc, "get_index", lambda: _FakeIndex())
    monkeypatch.setattr(rc, "get_metadata", lambda: _META)
    monkeypatch.setattr(rc, "_bm25", None, raising=False)          # no cross-test cache
    monkeypatch.setattr(rc, "_bm25_profile", None, raising=False)

    out = rc._search_with_scores("what is a function", 2)

    assert out, "hybrid retrieval returned nothing"
    assert all({"text", "score", "label", "meta"} <= set(c) for c in out)
    assert out[0]["text"].startswith("a function")


def test_dense_mode_still_works_without_bm25(monkeypatch):
    monkeypatch.setattr(config, "RETRIEVE_MODE", "dense")
    monkeypatch.setattr(config, "RERANK_ENABLED", False)
    monkeypatch.setattr(rc, "get_model", lambda: _FakeModel())
    monkeypatch.setattr(rc, "get_index", lambda: _FakeIndex())
    monkeypatch.setattr(rc, "get_metadata", lambda: _META)

    out = rc._search_with_scores("what is a function", 2)

    assert [c["text"] for c in out] == [_META[1]["text"], _META[0]["text"]]  # dense order kept


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
