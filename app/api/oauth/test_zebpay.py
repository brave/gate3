import base64
import urllib.parse

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ========================================
# Auth Endpoint Tests
# ========================================


def test_zebpay_auth_redirect():
    """Test Zebpay sandbox auth endpoint redirects correctly."""
    response = client.get(
        "/api/oauth/zebpay/sandbox/auth",
        params={
            "returnUrl": "https://example.com/callback?state=xyz",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    # Verify redirect location with Zebpay-specific path
    redirect_url = response.headers["location"]
    assert redirect_url.startswith("https://oauth.sandbox.zebpay.test/account/login")
    assert "returnUrl=" in redirect_url

    # The returnUrl parameter should contain the client_id
    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert "returnUrl" in params

    return_url = params["returnUrl"][0]
    assert "client_id=test_zebpay_sandbox_client_id" in return_url
    assert "https://example.com/callback" in return_url
    assert "state=xyz" in return_url


# ========================================
# Token Endpoint Tests
# ========================================


@respx.mock
def test_zebpay_token_exchange_success():
    """Test successful token exchange - validates request forwarding and response."""
    # Mock Zebpay token endpoint (uses api_url)
    route = respx.post("https://api-sandbox.zebpay.test/api/connect/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "zebpay_access_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "zebpay_refresh_token",
            },
        )
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/zebpay/sandbox/token",
        data={  # Zebpay uses form-urlencoded
            "grant_type": "authorization_code",
            "code": "zebpay_auth_code_123",
        },
    )

    # Verify response is correct
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "zebpay_access_token"
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 3600

    # Verify request was forwarded to upstream
    assert route.called, "Request was not forwarded to Zebpay"
    request = route.calls.last.request

    # Verify credentials were injected via Basic Auth header (Zebpay-specific)
    expected_auth = base64.b64encode(
        b"test_zebpay_sandbox_client_id:test_zebpay_sandbox_secret"
    ).decode("ascii")
    expected_header = f"Basic {expected_auth}"
    assert request.headers.get("authorization") == expected_header, (
        "Basic Auth header not set correctly"
    )

    # Verify Content-Type header (Zebpay-specific)
    content_type = request.headers.get("content-type")
    assert content_type == "application/x-www-form-urlencoded", (
        "Content-Type not set correctly"
    )

    # Verify original request parameters were forwarded (form-urlencoded)
    body_str = request.content.decode("utf-8")
    assert "grant_type=authorization_code" in body_str, "grant_type not forwarded"
    assert "code=zebpay_auth_code_123" in body_str, "code not forwarded"


@respx.mock
def test_zebpay_token_exchange_error():
    """Test token exchange with server error."""
    # Mock Zebpay token endpoint with error response
    respx.post("https://api-sandbox.zebpay.test/api/connect/token").mock(
        return_value=httpx.Response(403)
    )

    # Make request to our proxy
    response = client.post(
        "/api/oauth/zebpay/sandbox/token",
        data={"grant_type": "authorization_code", "code": "invalid"},
    )

    # Should forward the error status code
    assert response.status_code == 403
