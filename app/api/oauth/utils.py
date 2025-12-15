"""Shared utilities for OAuth providers."""

from starlette.datastructures import URL


def set_query_params(url: URL, **params: str) -> URL:
    """
    Set query parameters on a URL, replacing any existing values for those keys.

    Unlike include_query_params which adds params (potentially creating duplicates),
    this removes existing params with the same keys before adding the new values.

    Args:
        url: The URL to modify
        **params: Key-value pairs to set

    Returns:
        A new URL with the specified params set
    """
    return url.remove_query_params(keys=list(params.keys())).include_query_params(
        **params
    )
