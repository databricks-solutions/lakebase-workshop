"""Tests for Data API tenant-safety helpers."""

import pytest
from fastapi import HTTPException

# Skips cleanly if DB drivers aren't installed in the local env (CI installs them).
routes_data_api = pytest.importorskip("backend.routes_data_api")


def test_normalize_url_canonicalizes():
    n = routes_data_api._normalize_url
    base = "https://Proj.Region.databricks.com/data-api/v1"
    assert n(base + "/") == n(base)
    assert n(base + "?select=*") == n(base)
    assert n(base).startswith("https://proj.region.databricks.com")


def test_assert_matches_resolved_requires_resolution():
    with pytest.raises(HTTPException) as exc:
        routes_data_api._assert_matches_resolved("https://x.databricks.com/a", None)
    assert exc.value.status_code == 400


def test_assert_matches_resolved_rejects_mismatch():
    resolved = routes_data_api._normalize_url("https://mine.databricks.com/data-api/v1")
    with pytest.raises(HTTPException) as exc:
        routes_data_api._assert_matches_resolved(
            "https://someone-else.databricks.com/data-api/v1", resolved
        )
    assert exc.value.status_code == 403


def test_assert_matches_resolved_accepts_match_and_empty():
    resolved = routes_data_api._normalize_url("https://mine.databricks.com/data-api/v1")
    # Exact match (with a trailing slash) is accepted.
    assert routes_data_api._assert_matches_resolved(
        "https://mine.databricks.com/data-api/v1/", resolved
    ) == resolved
    # Empty client URL falls back to the trusted resolved endpoint.
    assert routes_data_api._assert_matches_resolved("", resolved) == resolved
