"""Tests for serving the SPA, including deployments that have no UI build.

`frontend/dist` is a gitignored build artifact, so an app deployed without
`npm run build` ships the API and no UI. That case must return an actionable
page instead of FastAPI's default `{"detail":"Not Found"}`, which reads as a
broken deployment rather than a missing build step.
"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

app_module = pytest.importorskip("app")

MISSING = "does-not-exist"


def _built_dist(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<html>console</html>")
    (dist / "robots.txt").write_text("hello")
    return dist


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.mark.parametrize("path", ["/", "/dashboard", "/index.html"])
def test_missing_build_returns_actionable_page(client, monkeypatch, tmp_path, path):
    monkeypatch.setattr(app_module, "STATIC_DIR", tmp_path / MISSING)

    res = client.get(path)

    assert res.status_code == 503
    assert "text/html" in res.headers["content-type"]
    assert res.text.strip() != '{"detail":"Not Found"}'
    # The page must name the fix, not just the failure.
    assert "npm run build" in res.text


def test_built_frontend_is_served(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "STATIC_DIR", _built_dist(tmp_path))

    assert client.get("/").text == "<html>console</html>"
    assert client.get("/robots.txt").text == "hello"
    # Unknown paths fall back to index.html so the SPA can route them client-side.
    assert client.get("/branches").text == "<html>console</html>"


@pytest.mark.parametrize("built", [True, False])
def test_unknown_api_route_stays_a_json_404(client, monkeypatch, tmp_path, built):
    static = _built_dist(tmp_path) if built else tmp_path / MISSING
    monkeypatch.setattr(app_module, "STATIC_DIR", static)

    res = client.get("/api/definitely-not-a-route")

    assert res.status_code == 404
    assert res.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("built", [True, False])
def test_health_reports_whether_the_ui_was_built(client, monkeypatch, tmp_path, built):
    # /api/health is how a facilitator confirms a deployment included the UI.
    static = _built_dist(tmp_path) if built else tmp_path / MISSING
    monkeypatch.setattr(app_module, "STATIC_DIR", static)

    res = client.get("/api/health", headers={"x-forwarded-email": "jane@example.com"})

    assert res.status_code == 200
    assert res.json()["frontend_built"] is built
