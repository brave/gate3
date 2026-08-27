"""Prometheus metrics for the NFT API: upstream Alchemy calls and what they return."""

from prometheus_client import Counter, Histogram

from .models import SimpleHashNFT

# Histogram buckets for upstream latency (in seconds)
DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

# Histogram buckets for items per batched call (tokens or asset ids)
BATCH_SIZE_BUCKETS = (1, 2, 5, 10, 20, 50, 100)

# Histogram buckets for NFTs per owner page; 0 counts wallets with nothing
OWNER_PAGE_BUCKETS = (0, 1, 2, 5, 10, 20, 50, 100)

# Upstream calls counter - one increment per Alchemy call, after transport retries
alchemy_nft_upstream_requests_total = Counter(
    "alchemy_nft_upstream_requests_total",
    "Total number of Alchemy NFT API calls",
    labelnames=["method", "network", "status"],
)

# Upstream duration histogram - wall time of one call including transport retries
alchemy_nft_upstream_duration_seconds = Histogram(
    "alchemy_nft_upstream_duration_seconds",
    "Response time for Alchemy NFT API calls",
    labelnames=["method", "network"],
    buckets=DURATION_BUCKETS,
)

# Batch size histogram - items requested per batched call
alchemy_nft_batch_size = Histogram(
    "alchemy_nft_batch_size",
    "Items requested per batched Alchemy NFT API call",
    labelnames=["method", "network"],
    buckets=BATCH_SIZE_BUCKETS,
)


# Owner page histogram - NFTs returned per chain page of an owner lookup, split
# by spam so real holdings can be told apart from airdrop noise
nft_owner_page_nfts = Histogram(
    "nft_owner_page_nfts",
    "NFTs returned per chain page of an owner lookup",
    labelnames=["network", "spam"],
    buckets=OWNER_PAGE_BUCKETS,
)


def record_upstream_request(
    *, method: str, network: str, status: str, duration: float
) -> None:
    """Record one Alchemy NFT API call.

    Args:
        method: Alchemy method name (getNFTsForOwner, getAssets, ...)
        network: Alchemy network id (eth-mainnet, solana-mainnet, ...)
        status: HTTP status code, or the exception class name for transport
                failures
        duration: Call wall time in seconds, including transport retries
    """
    alchemy_nft_upstream_requests_total.labels(
        method=method, network=network, status=status
    ).inc()
    alchemy_nft_upstream_duration_seconds.labels(
        method=method, network=network
    ).observe(duration)


def record_batch_size(*, method: str, network: str, size: int) -> None:
    """Record how many items a batched Alchemy NFT API call asks for."""
    alchemy_nft_batch_size.labels(method=method, network=network).observe(size)


def record_owner_page(*, network: str, nfts: list[SimpleHashNFT]) -> None:
    """Record how many spam and non-spam NFTs one owner page returned.

    Both series are observed for every page, so wallets holding nothing on a
    chain land in the zero bucket rather than vanishing from the histogram.
    """
    spam = sum(1 for nft in nfts if nft.collection.spam_score)
    nft_owner_page_nfts.labels(network=network, spam="true").observe(spam)
    nft_owner_page_nfts.labels(network=network, spam="false").observe(len(nfts) - spam)
