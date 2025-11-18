"""Shared test utilities for OAuth provider tests."""

from urllib.parse import parse_qs, urlencode, urlparse


def assert_redirect(
    actual_redirect_url: str,
    expected_base_url: str,
    expected_params: dict[str, str],
) -> None:
    """
    Assert that a redirect URL matches expected base URL and query params.

    Args:
        actual_redirect_url: The actual redirect URL from the response
        expected_base_url: Expected base URL (scheme + netloc + path)
        expected_params: Expected query parameters as a dict

    Example:
        assert_redirect(
            actual_redirect_url=response.headers["location"],
            expected_base_url="https://oauth.provider.test/authorize",
            expected_params={
                "client_id": "test_client_id",
                "scope": "read write",
                "state": "abc123",
            }
        )
    """
    # Build expected URL
    expected_url = f"{expected_base_url}?{urlencode(expected_params)}"

    # Parse both URLs
    expected_parsed = urlparse(expected_url)
    actual_parsed = urlparse(actual_redirect_url)

    # Assert base URL matches (scheme, netloc, path)
    assert actual_parsed[:3] == expected_parsed[:3], (
        f"Base URL mismatch:\n"
        f"  Expected: {expected_parsed.scheme}://{expected_parsed.netloc}{expected_parsed.path}\n"
        f"  Actual:   {actual_parsed.scheme}://{actual_parsed.netloc}{actual_parsed.path}"
    )

    # Assert query params match
    expected_params_parsed = parse_qs(expected_parsed.query)
    actual_params_parsed = parse_qs(actual_parsed.query)
    assert actual_params_parsed == expected_params_parsed, (
        f"Query params mismatch:\n"
        f"  Expected: {expected_params_parsed}\n"
        f"  Actual:   {actual_params_parsed}"
    )
