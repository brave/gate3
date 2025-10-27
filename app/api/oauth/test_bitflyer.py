import base64
import json

import httpx
import respx
from fastapi.testclient import TestClient

from app.api.oauth.test_helpers import assert_redirect
from app.main import app

client = TestClient(app)


# ========================================
# Auth Endpoint Tests
# ========================================


def test_bitflyer_auth_redirect():
    """Test Bitflyer sandbox auth endpoint redirects correctly."""
    params = {
        "scope": "assets create_deposit_id withdraw_to_deposit_id",
        "redirect_uri": "rewards://bitflyer/authorization",
        "state": "test_state_123",
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    }

    response = client.get(
        "/api/oauth/bitflyer/sandbox/auth",
        params=params,
        follow_redirects=False,
    )

    assert response.status_code == 302

    # Build expected params: sent params + client_id injected
    expected_params = params.copy()
    expected_params["client_id"] = "test_bitflyer_sandbox_client_id"

    # Assert redirect URL matches expected
    assert_redirect(
        actual_redirect_url=response.headers["location"],
        expected_base_url="https://oauth.sandbox.bitflyer.test/ex/OAuth/authorize",
        expected_params=expected_params,
    )


# ========================================
# Token Endpoint Tests
# ========================================


@respx.mock
def test_bitflyer_token_exchange_success():
    """Test successful token exchange - validates request forwarding and response."""
    # Mock Bitflyer token endpoint
    route = respx.post("https://oauth.sandbox.bitflyer.test/api/link/v1/token").mock(
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

    # Verify response is correct
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "bf_access_token"
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 7200

    # Verify request was forwarded to upstream
    assert route.called, "Request was not forwarded to Bitflyer"
    request = route.calls.last.request

    # Verify credentials were injected in request body
    body = json.loads(request.content)
    assert body["client_id"] == "test_bitflyer_sandbox_client_id", (
        "client_id not injected"
    )
    assert body["client_secret"] == "test_bitflyer_sandbox_secret", (
        "client_secret not injected"
    )

    # Verify Basic Auth header with expected value
    expected_auth = base64.b64encode(
        b"test_bitflyer_sandbox_client_id:test_bitflyer_sandbox_secret"
    ).decode("ascii")
    expected_header = f"Basic {expected_auth}"
    assert request.headers.get("authorization") == expected_header, (
        "Basic Auth header not set correctly"
    )

    # Verify original request parameters were forwarded
    assert body["grant_type"] == "authorization_code", "grant_type not forwarded"
    assert body["code"] == "bf_auth_code_123", "code not forwarded"
    assert body["redirect_uri"] == "rewards://bitflyer/authorization", (
        "redirect_uri not forwarded"
    )
    expected_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert body["code_verifier"] == expected_verifier, "code_verifier not forwarded"


@respx.mock
def test_bitflyer_token_exchange_error():
    """Test token exchange with server error."""
    # Mock Bitflyer token endpoint with error response
    respx.post("https://oauth.sandbox.bitflyer.test/api/link/v1/token").mock(
        return_value=httpx.Response(401)
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/bitflyer/sandbox/token",
        json={
            "grant_type": "authorization_code",
            "code": "test_code",
            "redirect_uri": "test_uri",
        },
    )

    # Should forward the error status code
    assert response.status_code == 401
