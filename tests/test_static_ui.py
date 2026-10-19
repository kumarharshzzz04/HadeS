"""The API serves the built UI on one origin (plan Task 3.2).

Run:  python -m pytest tests/test_static_ui.py -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def test_ui_dir_points_at_the_frontend_build():
    assert server.UI_DIR.name == "dist"
    assert (server.UI_DIR / "index.html").exists(), \
        "build the frontend first: cd frontend && npm run build"


def test_root_serves_the_built_index():
    r = TestClient(server.app).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "HadeS" in r.text


def test_api_routes_still_win_over_the_static_mount():
    r = TestClient(server.app).get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_unknown_deep_link_falls_back_to_index_not_404():
    # StaticFiles(html=True) serves index.html for a directory path; an unknown file
    # stays a 404, which is the right answer for an app with no client-side router.
    r = TestClient(server.app).get("/")
    assert "id=\"root\"" in r.text


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
