"""Prometheus metrics for phishing list ingestion and lookup."""

from prometheus_client import Counter, Gauge, Histogram

DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

phishing_ingest_total = Counter(
    "phishing_ingest_total",
    "Phishing list ingestion attempts",
    labelnames=["status"],
)

phishing_list_entries = Gauge(
    "phishing_list_entries",
    "Number of source blocklist entries from the last successful ingest",
)

phishing_list_hashes = Gauge(
    "phishing_list_hashes",
    "Number of unique full hashes stored after the last successful ingest",
)

phishing_refresh_duration_seconds = Histogram(
    "phishing_refresh_duration_seconds",
    "Duration of phishing list refresh operations",
    buckets=DURATION_BUCKETS,
)

phishing_lookup_requests_total = Counter(
    "phishing_lookup_requests_total",
    "Phishing hash-prefix lookup requests",
    labelnames=["status"],
)

phishing_lookup_duration_seconds = Histogram(
    "phishing_lookup_duration_seconds",
    "Duration of phishing hash-prefix lookups",
    buckets=DURATION_BUCKETS,
)

phishing_lookup_prefixes = Histogram(
    "phishing_lookup_prefixes",
    "Number of hash prefixes per lookup request",
    buckets=(1, 2, 4, 6, 8, 11, 16, 32),
)
