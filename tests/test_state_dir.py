"""Writable state must live outside a read-only install dir (plan Task 2.3).

Run:  python -m pytest tests/test_state_dir.py -q
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402


def test_state_dir_is_writable_and_outside_the_install():
    d = pathlib.Path(config.state_dir())
    assert d.exists() and os.access(d, os.W_OK)
    assert not str(d).startswith(config.BASE_DIR), "state must not sit inside the app folder"


def test_state_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HADES_STATE_DIR", str(tmp_path / "state"))
    d = pathlib.Path(config.state_dir())
    assert d == tmp_path / "state" and d.exists()


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
