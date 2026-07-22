from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_lookup_returns_matches(client):
    with (
        patch(
            "app.api.phishing.routes.PhishingManager.lookup",
            new=AsyncMock(
                return_value={
                    "ab12cd34": ["ab12cd34" + "0" * 56],
                    "ef567890": [],
                }
            ),
        ),
        patch(
            "app.api.phishing.routes.PhishingManager.get_list_version",
            new=AsyncMock(return_value="42"),
        ),
    ):
        response = client.get(
            "/api/phishing/v1/lookup",
            params={"prefixes": "ab12cd34,ef567890"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "42"
    assert body["matches"]["ab12cd34"] == ["ab12cd34" + "0" * 56]
    assert body["matches"]["ef567890"] == []


def test_lookup_rejects_malformed_prefix(client):
    response = client.get(
        "/api/phishing/v1/lookup",
        params={"prefixes": "ab12cd34,short"},
    )
    assert response.status_code == 400
    assert "Malformed" in response.json()["detail"]


def test_lookup_rejects_non_hex_prefix(client):
    response = client.get(
        "/api/phishing/v1/lookup",
        params={"prefixes": "ghijklmn"},
    )
    assert response.status_code == 400


def test_lookup_rejects_empty_prefixes(client):
    response = client.get(
        "/api/phishing/v1/lookup",
        params={"prefixes": " , , "},
    )
    assert response.status_code == 400


def test_admin_refresh_success(client):
    with patch(
        "app.api.phishing.routes.PhishingManager.refresh",
        new=AsyncMock(
            return_value={
                "version": "7",
                "entry_count": 100,
                "hash_count": 120,
                "prefix_count": 90,
            }
        ),
    ):
        response = client.get("/api/phishing/v1/_admin/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["version"] == "7"
    assert body["entryCount"] == 100
    assert body["hashCount"] == 120
