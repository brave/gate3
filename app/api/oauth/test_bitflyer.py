import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ========================================
# Auth Endpoint Tests
# ========================================


def test_bitflyer_auth_redirect():
    """Test Bitflyer sandbox auth endpoint redirects correctly."""
    response = client.get(
        "/api/oauth/bitflyer/sandbox/auth",
        params={
            "scope": "assets create_deposit_id withdraw_to_deposit_id",
            "redirect_uri": "rewards://bitflyer/authorization",
            "state": "test_state_123",
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    # Parse actual URL
    actual_url = response.headers["location"]
    actual_parsed = urlparse(actual_url)
    actual_params = parse_qs(actual_parsed.query)

    # Verify base URL
    expected_base = "https://sandbox.bitflyer.test/oauth/ex/OAuth/authorize"
    actual_base = f"{actual_parsed.scheme}://{actual_parsed.netloc}{actual_parsed.path}"
    assert actual_base == expected_base

    # Verify client_id is correctly injected
    assert actual_params["client_id"] == ["test_bitflyer_sandbox_client_id"]


# ========================================
# Token Endpoint Tests
# ========================================


@respx.mock
def test_bitflyer_token_exchange():
    """Test token exchange - verify client credentials are included."""
    # Mock Bitflyer token endpoint
    route = respx.post("https://sandbox.bitflyer.test/oauth/api/link/v1/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "bf_access_token",
                "token_type": "Bearer",
                "expires_in": 7200,
                "refresh_token": "bf_refresh_token",
            },
        )
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/bitflyer/sandbox/token",
        json={
            "grant_type": "authorization_code",
            "code": "bf_auth_code_123",
            "redirect_uri": "rewards://bitflyer/authorization",
            "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        },
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "bf_access_token"

    # Verify upstream request to Bitflyer
    request = route.calls.last.request

    # Verify credentials in JSON body
    request_body = json.loads(request.content)
    assert request_body["client_id"] == "test_bitflyer_sandbox_client_id"
    assert request_body["client_secret"] == "test_bitflyer_sandbox_secret"

    # Verify Basic Auth header with expected value
    expected_auth = base64.b64encode(
        b"test_bitflyer_sandbox_client_id:test_bitflyer_sandbox_secret"
    ).decode("ascii")
    expected_header = f"Basic {expected_auth}"
    assert request.headers.get("authorization") == expected_header
