import base64

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.oauth.test_helpers import assert_redirect
from app.main import app

client = TestClient(app)


# ========================================
# Auth Endpoint Tests
# ========================================


@pytest.mark.parametrize(
    "input_redirect_uri",
    ["rewards://uphold/authorization", "https://example.com/other"],
)
def test_uphold_auth_redirect(input_redirect_uri):
    """Test Uphold auth always uses the allowed redirect_uri."""
    params = {
        "response_type": "code",
        "scope": "accounts:read",
        "state": "uphold_state_789",
        "redirect_uri": input_redirect_uri,
    }

    response = client.get(
        "/api/oauth/uphold/sandbox/auth",
        params=params,
        follow_redirects=False,
    )

    assert response.status_code == 302

    # redirect_uri is always set to the allowed value
    expected_params = {**params, "redirect_uri": "rewards://uphold/authorization"}
    assert_redirect(
        actual_redirect_url=response.headers["location"],
        expected_base_url="https://oauth.sandbox.uphold.test/authorize/test_uphold_sandbox_client_id",
        expected_params=expected_params,
    )


# ========================================
# Token Endpoint Tests
# ========================================


@respx.mock
def test_uphold_token_exchange_success():
    """Test successful token exchange - validates request forwarding and response."""
    # Mock Uphold token endpoint (uses api_url, not oauth_url)
    route = respx.post("https://api-sandbox.uphold.test/api/oauth2/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "uphold_access_token",
                "token_type": "bearer",
                "expires_in": 7776000,
            },
        )
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/uphold/sandbox/token",
        data={  # Uphold uses form-urlencoded
            "grant_type": "authorization_code",
            "code": "uphold_auth_code_123",
        },
    )

    # Verify response is correct
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "uphold_access_token"
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 7776000

    # Verify request was forwarded to upstream
    assert route.called, "Request was not forwarded to Uphold"
    request = route.calls.last.request

    # Verify credentials were injected via Basic Auth header (Uphold-specific)
    expected_auth = base64.b64encode(
        b"test_uphold_sandbox_client_id:test_uphold_sandbox_secret"
    ).decode("ascii")
    expected_header = f"Basic {expected_auth}"
    assert request.headers.get("authorization") == expected_header, (
        "Basic Auth header not set correctly"
    )

    # Verify original request parameters were forwarded (form-urlencoded)
    body_str = request.content.decode("utf-8")
    assert "grant_type=authorization_code" in body_str, "grant_type not forwarded"
    assert "code=uphold_auth_code_123" in body_str, "code not forwarded"


@respx.mock
def test_uphold_token_exchange_error():
    """Test token exchange with server error."""
    # Mock Uphold token endpoint with error response
    respx.post("https://api-sandbox.uphold.test/api/oauth2/token").mock(
        return_value=httpx.Response(401)
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/uphold/sandbox/token",
        data={"grant_type": "authorization_code", "code": "invalid"},
    )

    # Should forward the error status code
    assert response.status_code == 401
