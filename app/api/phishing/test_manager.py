from unittest.mock import patch

import fakeredis
import pytest
import respx
from httpx import Response

from app.api.phishing.constants import PHISHING_LIST_URL, PHISHING_SCHEMA_VERSION
from app.api.phishing.manager import PhishingManager


@pytest.fixture
def cache():
    redis_client = fakeredis.FakeAsyncRedis(decode_responses=True)

    with patch("app.api.phishing.manager.Cache") as mock_cache:
        mock_cache.get_client.return_value.__aenter__.return_value = redis_client
        mock_cache.get_client.return_value.__aexit__.return_value = None
        yield redis_client


class TestNormalizeAndHash:
    def test_normalize_lowercases_and_strips(self):
        assert PhishingManager.normalize("  Evil.COM/  ") == "evil.com"

    def test_hash_is_sha256_hex(self):
        full = PhishingManager.hash_entry("evil.com")
        assert len(full) == 64
        assert full == PhishingManager.hash_entry("evil.com")
        assert PhishingManager.prefix_of(full) == full[:8]


class TestExpandEntries:
    def test_apex_expansion_for_subdomain(self):
        expanded = PhishingManager.expand_entries("sub.evil.com")
        assert expanded == {"sub.evil.com", "evil.com"}

    def test_no_expansion_when_already_apex(self):
        assert PhishingManager.expand_entries("evil.com") == {"evil.com"}

    def test_shared_hosting_psl_does_not_over_expand(self):
        # vercel.app is on the PSL; tenant boundary is evil.vercel.app itself.
        assert PhishingManager.expand_entries("evil.vercel.app") == {"evil.vercel.app"}
        assert PhishingManager.expand_entries("foo.github.io") == {"foo.github.io"}

    def test_path_entries_are_not_apex_expanded(self):
        entry = "ipfs.io/ipfs/QmExample"
        assert PhishingManager.expand_entries(entry) == {"ipfs.io/ipfs/qmexample"}

    def test_empty_after_normalize_returns_empty(self):
        assert PhishingManager.expand_entries("   ///  ") == set()


class TestBuildPrefixMap:
    def test_buckets_by_prefix(self):
        prefix_map = PhishingManager.build_prefix_map(["evil.com", "sub.evil.com"])
        evil_hash = PhishingManager.hash_entry("evil.com")
        sub_hash = PhishingManager.hash_entry("sub.evil.com")

        assert evil_hash in prefix_map[evil_hash[:8]]
        assert sub_hash in prefix_map[sub_hash[:8]]
        # Apex expansion of sub.evil.com also contributes evil.com's hash.
        assert evil_hash in prefix_map[evil_hash[:8]]


class TestExtractBlocklist:
    def test_legacy_blacklist_shape(self):
        entries, version = PhishingManager._extract_blocklist(
            {"version": 2, "blacklist": ["a.com", "b.com"], "whitelist": ["c.com"]}
        )
        assert entries == ["a.com", "b.com"]
        assert version == "2"

    def test_blocklist_preferred(self):
        entries, version = PhishingManager._extract_blocklist(
            {"version": 3, "blocklist": ["new.com"], "blacklist": ["old.com"]}
        )
        assert entries == ["new.com"]
        assert version == "3"

    def test_multi_config_array(self):
        entries, version = PhishingManager._extract_blocklist(
            [
                {"name": "metamask", "version": 1, "blocklist": ["a.com"]},
                {"name": "other", "version": 2, "blacklist": ["b.com"]},
            ]
        )
        assert entries == ["a.com", "b.com"]
        assert version == "1,2"


@pytest.mark.asyncio
async def test_refresh_and_lookup(cache):
    config = {
        "version": 42,
        "blacklist": ["evil.com", "phish.example", "tenant.vercel.app"],
    }

    with respx.mock:
        respx.get(PHISHING_LIST_URL).mock(return_value=Response(200, json=config))
        result = await PhishingManager.refresh()

    assert result["version"] == "42"
    assert result["entry_count"] == 3
    assert result["hash_count"] >= 3

    evil_hash = PhishingManager.hash_entry("evil.com")
    prefix = evil_hash[:8]
    matches = await PhishingManager.lookup([prefix, "00000000"])
    assert evil_hash in matches[prefix]
    assert matches["00000000"] == []
    assert await PhishingManager.get_list_version() == "42"


@pytest.mark.asyncio
async def test_refresh_if_stale_reseeds_empty_store(cache):
    config = {"version": 1, "blacklist": ["evil.com"]}

    assert await PhishingManager.is_empty()

    with respx.mock:
        respx.get(PHISHING_LIST_URL).mock(return_value=Response(200, json=config))
        assert await PhishingManager.refresh_if_stale() is True

    assert not await PhishingManager.is_empty()
    stored = await cache.get(PhishingManager.schema_version_key)
    assert stored == PHISHING_SCHEMA_VERSION

    # Second call should no-op.
    assert await PhishingManager.refresh_if_stale() is False


@pytest.mark.asyncio
async def test_refresh_if_stale_skips_when_lock_held(cache):
    await cache.set(PhishingManager.reseed_lock_key, "1")
    # Empty store is stale, but lock prevents reseed.
    assert await PhishingManager.refresh_if_stale() is False
