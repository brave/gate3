import base64
import urllib.parse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ========================================
# Auth Endpoint Tests
# ========================================


def _parse_zebpay_redirect(response) -> tuple[str, dict]:
    """Parse Zebpay redirect response and extract returnUrl params."""
    assert response.status_code == 302
    redirect_url = response.headers["location"]
    assert redirect_url.startswith("https://oauth.sandbox.zebpay.test/account/login")

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    assert "returnUrl" in params

    return_url = params["returnUrl"][0]
    return_url_parsed = urllib.parse.urlparse(return_url)
    return_url_params = urllib.parse.parse_qs(return_url_parsed.query)

    return return_url, return_url_params


@pytest.mark.parametrize(
    "input_redirect_uri",
    ["rewards://zebpay/authorization", "https://example.com/other"],
)
def test_zebpay_auth_redirect(input_redirect_uri):
    """Test Zebpay auth always uses the allowed redirect_uri."""
    response = client.get(
        "/api/oauth/zebpay/sandbox/auth",
        params={
            "returnUrl": f"https://oauth.sandbox.zebpay.test/connect/authorize/callback?state=xyz&redirect_uri={input_redirect_uri}",
        },
        follow_redirects=False,
    )

    return_url, return_url_params = _parse_zebpay_redirect(response)

    # The returnUrl parameter should contain the client_id and allowed redirect_uri
    assert return_url.startswith(
        "https://oauth.sandbox.zebpay.test/connect/authorize/callback"
    )
    assert return_url_params["state"] == ["xyz"]
    assert return_url_params["client_id"] == ["test_zebpay_sandbox_client_id"]
    assert return_url_params["redirect_uri"] == ["rewards://zebpay/authorization"]


@pytest.mark.parametrize(
    "malicious_return_url",
    [
        "https://evil.example.com/steal?cb=https://another.evil/",
        "javascript:alert(1)",
    ],
)
def test_zebpay_auth_rejects_open_redirect_attempt(malicious_return_url):
    """Ensure auth endpoint does not allow user-controlled returnUrl hosts."""
    response = client.get(
        "/api/oauth/zebpay/sandbox/auth",
        params={"returnUrl": malicious_return_url},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid returnUrl parameter"

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
