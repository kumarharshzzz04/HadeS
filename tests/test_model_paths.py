"""Portable model-directory resolution (plan Task 0.1).

Run:  python -m pytest tests/test_model_paths.py -q
      python tests/test_model_paths.py
"""
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
import rag_chat as rc  # noqa: E402


def test_source_has_no_hardcoded_user_path(monkeypatch):
    """The A1 literal (`C:/Users/kingh/...`) shipped in rag_chat.py — it must be gone."""
    src = pathlib.Path(rc.__file__).read_text(encoding="utf-8")
    assert "kingh" not in src


def test_search_roots_are_env_app_then_home(monkeypatch):
    monkeypatch.delenv("HADES_MODEL_DIR", raising=False)
    roots = rc._model_search_roots()
    assert pathlib.Path(config.BASE_DIR) / "models" in roots
    assert roots[-1] == pathlib.Path.home() / ".cache/huggingface/hub"


def test_env_dir_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("HADES_MODEL_DIR", str(tmp_path))
    assert rc._model_search_roots()[0] == tmp_path


def test_local_snapshot_finds_bundled_models_dir(monkeypatch, tmp_path):
    """A snapshot laid out like the HF hub cache under $HADES_MODEL_DIR is found."""
    snap = tmp_path / f"models--sentence-transformers--{config.EMBEDDING_MODEL_NAME}" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "model.safetensors").write_bytes(b"")
    monkeypatch.setenv("HADES_MODEL_DIR", str(tmp_path))
    assert rc._local_snapshot() == str(snap)


if __name__ == "__main__":
    # Single runner = pytest. A hand-maintained list is what silently skipped a test in
    # test_retrieval.py (plan G19), and these tests need pytest's monkeypatch/tmp_path.
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
