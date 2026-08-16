# Raw config from MetaMask eth-phishing-detect.
PHISHING_LIST_URL = (
    "https://raw.githubusercontent.com/MetaMask/eth-phishing-detect/"
    "main/src/config.json"
)

# Bump whenever the stored Redis shape changes so instances self-heal on boot.
PHISHING_SCHEMA_VERSION = "1"

# Hash-prefix length: first 4 bytes → 8 hex characters.
PREFIX_HEX_LENGTH = 8

# Reasonable upper bound; clients typically send 1–6, occasionally ~10–11.
MAX_PREFIXES_PER_REQUEST = 32
