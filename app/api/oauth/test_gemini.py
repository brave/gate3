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


def test_gemini_auth_redirect():
    """Test Gemini sandbox auth endpoint redirects correctly."""
    params = {
        "scope": (
            "balances:read,history:read,crypto:send,account:read,"
            "payments:create,payments:send,"
        ),
        "redirect_uri": "rewards://gemini/authorization",
        "state": "test_state_123",
        "response_type": "code",
    }

    response = client.get(
        "/api/oauth/gemini/sandbox/auth",
        params=params,
        follow_redirects=False,
    )

    assert response.status_code == 302

    # Build expected params: sent params + client_id injected
    expected_params = params.copy()
    expected_params["client_id"] = "test_gemini_sandbox_client_id"

    # Assert redirect URL matches expected
    assert_redirect(
        actual_redirect_url=response.headers["location"],
        expected_base_url="https://oauth.sandbox.gemini.test/auth",
        expected_params=expected_params,
    )


# ========================================
# Token Endpoint Tests
# ========================================


@respx.mock
def test_gemini_token_exchange_success():
    """Test successful token exchange - validates request forwarding and response."""
    # Mock Gemini token endpoint
    route = respx.post("https://oauth.sandbox.gemini.test/auth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "aaaaa",
                "expires_in": 83370,
                "scope": "sample:scope",
                "refresh_token": "bbbbb",
                "token_type": "Bearer",
            },
        )
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/gemini/sandbox/token",
        json={
            "grant_type": "authorization_code",
            "code": "46553A9E3D57D70F960EA26D95183D8CBB026283D92CBC7C54665408DA7DF398",
            "redirect_uri": "1234567890",
        },
    )

    # Verify response is correct
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "aaaaa"
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 83370

    # Verify request was forwarded to upstream
    assert route.called, "Request was not forwarded to Gemini"
    request = route.calls.last.request

    # Verify credentials were injected in request body
    body = json.loads(request.content)
    assert body["client_id"] == "test_gemini_sandbox_client_id", (
        "client_id not injected"
    )
    assert body["client_secret"] == "test_gemini_sandbox_secret", (
        "client_secret not injected"
    )

    # Verify original request parameters were forwarded
    assert body["grant_type"] == "authorization_code", "grant_type not forwarded"
    expected_code = "46553A9E3D57D70F960EA26D95183D8CBB026283D92CBC7C54665408DA7DF398"
    assert body["code"] == expected_code, "code not forwarded"
    assert body["redirect_uri"] == "1234567890", "redirect_uri not forwarded"


@respx.mock
def test_gemini_token_exchange_error():
    """Test token exchange with server error."""
    # Mock Gemini token endpoint with error response
    respx.post("https://oauth.sandbox.gemini.test/auth/token").mock(
        return_value=httpx.Response(418)
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/gemini/sandbox/token",
        json={
            "grant_type": "authorization_code",
            "code": "test_code",
            "redirect_uri": "test_uri",
        },
    )

    # Should forward the error status code
    assert response.status_code == 418
