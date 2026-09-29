"""Shared utilities for OAuth providers."""

import json
import math
from typing import Any, NoReturn

from fastapi import HTTPException, Request
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


def _reject_non_finite(constant: str) -> NoReturn:
    raise ValueError(f"Non-finite JSON number: {constant}")


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        _reject_non_finite(value)
    return number


async def read_json_object(request: Request) -> dict[str, Any]:
    """
    Parse the request body as a JSON object.

    Non-finite numbers (NaN, Infinity, 1e1000) are rejected: Python's decoder
    accepts them, but httpx refuses to serialize them when forwarding.

    Raises:
        HTTPException: 400 if the body is not valid JSON or not a JSON object
    """
    try:
        body = json.loads(
            await request.body(),
            parse_constant=_reject_non_finite,
            parse_float=_parse_finite_float,
        )
    except ValueError as e:  # JSONDecodeError, UnicodeDecodeError, non-finite
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    return body
