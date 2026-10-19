"""Config sanity the first run depends on (plan Task 0.10 / G12).

Run:  python -m pytest tests/test_config.py -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config  # noqa: E402


def test_default_profile_has_a_youtube_url():
    """A default profile without a source URL hands a first-run user timestamps that
    cannot be clicked — og is the estimated-timestamp 18h set with no single video."""
    assert config.DEFAULT_PROFILE in config.YOUTUBE_URLS


def test_default_profile_is_available():
    assert config.DEFAULT_PROFILE in config.AVAILABLE_PROFILES


def test_every_available_profile_has_paths_to_existing_dirs():
    for name in config.AVAILABLE_PROFILES:
        p = config.profile_paths(name)
        assert p["INDEX_PATH"].startswith(config.BASE_DIR)
        assert p["METADATA_PATH"].startswith(config.BASE_DIR)


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
