import re
import time

from fastapi import APIRouter, HTTPException, Query

from app.api.common.models import Tags
from app.api.phishing.constants import MAX_PREFIXES_PER_REQUEST, PREFIX_HEX_LENGTH
from app.api.phishing.manager import PhishingManager
from app.api.phishing.metrics import (
    phishing_lookup_duration_seconds,
    phishing_lookup_prefixes,
    phishing_lookup_requests_total,
)
from app.api.phishing.models import PhishingLookupResponse, PhishingRefreshResponse

router = APIRouter(prefix="/api/phishing", tags=[Tags.PHISHING])

_PREFIX_RE = re.compile(rf"^[0-9a-fA-F]{{{PREFIX_HEX_LENGTH}}}$")


def _parse_prefixes(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise HTTPException(
            status_code=400, detail="At least one hash prefix is required"
        )
    if len(parts) > MAX_PREFIXES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_PREFIXES_PER_REQUEST} prefixes allowed per request",
        )

    invalid = [p for p in parts if not _PREFIX_RE.fullmatch(p)]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Malformed prefix(es): each must be exactly {PREFIX_HEX_LENGTH} "
                f"hex characters; got {invalid}"
            ),
        )

    # Preserve request order but dedupe for Redis round-trips.
    seen: set[str] = set()
    ordered: list[str] = []
    for prefix in parts:
        lower = prefix.lower()
        if lower not in seen:
            seen.add(lower)
            ordered.append(lower)
    return ordered


@router.get("/v1/lookup", response_model=PhishingLookupResponse)
async def lookup_hashes(
    prefixes: str = Query(
        ...,
        description=(
            "Comma-separated 8-hex-char SHA-256 prefixes "
            "(first 4 bytes of each candidate hash)"
        ),
        examples=["ab12cd34,ef567890"],
    ),
):
    """Return all full hashes sharing each submitted prefix (k-anonymity lookup)."""
    started = time.perf_counter()
    status = "success"
    try:
        parsed = _parse_prefixes(prefixes)
        phishing_lookup_prefixes.observe(len(parsed))
        matches = await PhishingManager.lookup(parsed)
        version = await PhishingManager.get_list_version()
        return PhishingLookupResponse(version=version, matches=matches)
    except HTTPException:
        status = "error"
        raise
    except Exception as e:
        status = "error"
        raise HTTPException(
            status_code=500, detail=f"Failed to lookup phishing hashes: {e}"
        ) from e
    finally:
        phishing_lookup_requests_total.labels(status=status).inc()
        phishing_lookup_duration_seconds.observe(time.perf_counter() - started)


@router.get("/v1/_admin/refresh", response_model=PhishingRefreshResponse)
async def admin_refresh_phishing_list():
    try:
        result = await PhishingManager.refresh()
        return PhishingRefreshResponse(
            status="success",
            message="Phishing list refreshed successfully",
            version=result["version"],
            entry_count=result["entry_count"],
            hash_count=result["hash_count"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to refresh phishing list: {e}"
        ) from e
