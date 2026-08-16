import hashlib
import logging
import time
from collections import defaultdict
from typing import Any

from publicsuffixlist import PublicSuffixList

from app.api.phishing.constants import (
    PHISHING_LIST_URL,
    PHISHING_SCHEMA_VERSION,
    PREFIX_HEX_LENGTH,
)
from app.api.phishing.metrics import (
    phishing_ingest_total,
    phishing_list_entries,
    phishing_list_hashes,
    phishing_refresh_duration_seconds,
)
from app.core.cache import Cache
from app.core.http import create_http_client

logger = logging.getLogger(__name__)

# Shared PSL instance; the bundled list is sufficient and avoids per-request I/O.
_psl = PublicSuffixList()


class PhishingManager:
    key_prefix = "phish:prefix"
    schema_version_key = "phish_meta:schema_version"
    list_version_key = "phish_meta:list_version"
    entry_count_key = "phish_meta:entry_count"
    hash_count_key = "phish_meta:hash_count"
    reseed_lock_key = "phish_meta:reseed_lock"

    @staticmethod
    def normalize(entry: str) -> str:
        """Lowercase and strip trailing slashes / whitespace."""
        return entry.strip().lower().rstrip("/")

    @staticmethod
    def hash_entry(normalized: str) -> str:
        """Return the full 64-hex SHA-256 of a normalized entry."""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def prefix_of(cls, full_hash: str) -> str:
        return full_hash[:PREFIX_HEX_LENGTH]

    @classmethod
    def _prefix_key(cls, prefix: str) -> str:
        return f"{cls.key_prefix}:{prefix.lower()}"

    @classmethod
    def expand_entries(cls, entry: str) -> set[str]:
        """Normalize an entry and optionally add its PSL-bounded apex.

        Path-containing entries are hashed as-is (no apex expansion). Shared-
        hosting platforms on the PSL (e.g. vercel.app) never expand past the
        tenant boundary because privatesuffix equals the listed host.
        """
        normalized = cls.normalize(entry)
        if not normalized:
            return set()

        results = {normalized}

        # Path entries: hash as-is; path expansion is client-side.
        if "/" in normalized:
            return results

        apex = _psl.privatesuffix(normalized)
        if apex and apex != normalized:
            results.add(apex)

        return results

    @classmethod
    def build_prefix_map(cls, entries: list[str]) -> dict[str, set[str]]:
        """Map 8-hex prefixes → full SHA-256 hashes for all expanded entries."""
        prefix_map: dict[str, set[str]] = defaultdict(set)
        for entry in entries:
            for candidate in cls.expand_entries(entry):
                full_hash = cls.hash_entry(candidate)
                prefix_map[cls.prefix_of(full_hash)].add(full_hash)
        return prefix_map

    @classmethod
    def _extract_blocklist(cls, payload: Any) -> tuple[list[str], str]:
        """Pull blocklist entries + version from config.json (old or new shape)."""
        if isinstance(payload, list):
            entries: list[str] = []
            versions: list[str] = []
            for cfg in payload:
                if not isinstance(cfg, dict):
                    continue
                entries.extend(cls._blocklist_from_dict(cfg))
                if "version" in cfg:
                    versions.append(str(cfg["version"]))
            version = ",".join(versions) if versions else "unknown"
            return entries, version

        if isinstance(payload, dict):
            entries = cls._blocklist_from_dict(payload)
            version = str(payload.get("version", "unknown"))
            return entries, version

        raise ValueError("Unexpected eth-phishing-detect config shape")

    @staticmethod
    def _blocklist_from_dict(cfg: dict[str, Any]) -> list[str]:
        # Live config still uses "blacklist"; newer format uses "blocklist".
        raw = cfg.get("blocklist")
        if raw is None:
            raw = cfg.get("blacklist")
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, str)]

    @classmethod
    async def fetch_blocklist(cls) -> tuple[list[str], str]:
        async with create_http_client(timeout=60.0) as client:
            response = await client.get(PHISHING_LIST_URL)
            response.raise_for_status()
            payload = response.json()
        return cls._extract_blocklist(payload)

    @classmethod
    async def refresh(cls) -> dict[str, Any]:
        """Clear and re-ingest the phishing hash index atomically."""
        started = time.perf_counter()
        try:
            entries, list_version = await cls.fetch_blocklist()
            prefix_map = cls.build_prefix_map(entries)
            hash_count = sum(len(hashes) for hashes in prefix_map.values())

            async with Cache.get_client() as redis_client:
                pipe = redis_client.pipeline()
                await cls._clear_prefix_keys(pipe)

                for prefix, hashes in prefix_map.items():
                    if hashes:
                        pipe.sadd(cls._prefix_key(prefix), *hashes)

                pipe.set(cls.schema_version_key, PHISHING_SCHEMA_VERSION)
                pipe.set(cls.list_version_key, list_version)
                pipe.set(cls.entry_count_key, str(len(entries)))
                pipe.set(cls.hash_count_key, str(hash_count))
                await pipe.execute()

            phishing_list_entries.set(len(entries))
            phishing_list_hashes.set(hash_count)
            phishing_ingest_total.labels(status="success").inc()

            logger.info(
                "Phishing list refreshed: version=%s entries=%d hashes=%d prefixes=%d",
                list_version,
                len(entries),
                hash_count,
                len(prefix_map),
            )
            return {
                "version": list_version,
                "entry_count": len(entries),
                "hash_count": hash_count,
                "prefix_count": len(prefix_map),
            }
        except Exception:
            phishing_ingest_total.labels(status="error").inc()
            logger.exception("Failed to refresh phishing list")
            raise
        finally:
            phishing_refresh_duration_seconds.observe(time.perf_counter() - started)

    @classmethod
    async def _clear_prefix_keys(cls, pipe) -> None:
        async with Cache.get_client() as redis_client:
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor, match=f"{cls.key_prefix}:*", count=1_000
                )
                for key in keys:
                    pipe.delete(key)
                if cursor == 0:
                    break

    @classmethod
    async def is_empty(cls) -> bool:
        async with Cache.get_client() as redis_client:
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor, match=f"{cls.key_prefix}:*", count=100
                )
                if keys:
                    return False
                if cursor == 0:
                    return True

    @classmethod
    async def _is_stale(cls) -> bool:
        if await cls.is_empty():
            return True

        async with Cache.get_client() as redis_client:
            stored = await redis_client.get(cls.schema_version_key)
        if isinstance(stored, bytes):
            stored = stored.decode()
        return stored != PHISHING_SCHEMA_VERSION

    @classmethod
    async def refresh_if_stale(cls) -> bool:
        """Reseed on cold start / schema bump. Returns True if this instance reseeds."""
        if not await cls._is_stale():
            return False

        async with Cache.get_client() as redis_client:
            acquired = await redis_client.set(cls.reseed_lock_key, "1", nx=True, ex=300)
        if not acquired:
            return False

        await cls.refresh()
        return True

    @classmethod
    async def get_list_version(cls) -> str:
        async with Cache.get_client() as redis_client:
            version = await redis_client.get(cls.list_version_key)
        if isinstance(version, bytes):
            version = version.decode()
        return version or "unknown"

    @classmethod
    async def lookup(cls, prefixes: list[str]) -> dict[str, list[str]]:
        """Return all full hashes sharing each submitted 8-hex prefix."""
        if not prefixes:
            return {}

        async with Cache.get_client() as redis_client:
            pipe = redis_client.pipeline()
            for prefix in prefixes:
                pipe.smembers(cls._prefix_key(prefix))
            results = await pipe.execute()

        matches: dict[str, list[str]] = {}
        for prefix, members in zip(prefixes, results):
            hashes = sorted(
                m.decode() if isinstance(m, bytes) else m for m in (members or [])
            )
            matches[prefix.lower()] = hashes
        return matches
