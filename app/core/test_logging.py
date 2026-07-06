import logging

from app.core.logging import (
    CondenseSensitiveQueryParamsFilter,
    condense_sensitive_query_params,
    condense_value,
    install_access_log_sanitizer,
)

EVM_ADDRESS = "0x1234567890123456789012345678901234567890"
SOLANA_ADDRESS = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"


def test_condense_value_shortens_evm_address():
    assert condense_value(EVM_ADDRESS) == "0x1234...7890"


def test_condense_value_shortens_solana_address():
    assert condense_value(SOLANA_ADDRESS) == "9xQe...VFin"


def test_condense_value_leaves_short_values_unchanged():
    assert condense_value("0xabcd") == "0xabcd"
    assert condense_value("") == ""


def test_condenses_wallet_addresses_param():
    path = (
        f"/simplehash/api/v0/nfts/owners?wallet_addresses={EVM_ADDRESS}&chains=ethereum"
    )
    assert (
        condense_sensitive_query_params(path)
        == "/simplehash/api/v0/nfts/owners?wallet_addresses=0x1234...7890&chains=ethereum"
    )


def test_condenses_wallet_address_and_recipient():
    path = f"/api/nft/v1/getNFTsForOwner?wallet_address={EVM_ADDRESS}&chains=eth.0x1"
    assert (
        condense_sensitive_query_params(path)
        == "/api/nft/v1/getNFTsForOwner?wallet_address=0x1234...7890&chains=eth.0x1"
    )

    path = f"/api/swap/v1/quote?source_coin=ETH&recipient={EVM_ADDRESS}"
    assert (
        condense_sensitive_query_params(path)
        == "/api/swap/v1/quote?source_coin=ETH&recipient=0x1234...7890"
    )


def test_preserves_non_sensitive_params_verbatim():
    path = "/api/nft?chains=ethereum,polygon,solana&cursor=page123"
    assert condense_sensitive_query_params(path) == path


def test_no_query_string_is_unchanged():
    assert condense_sensitive_query_params("/healthz") == "/healthz"


def test_empty_sensitive_value_is_unchanged():
    path = "/simplehash/api/v0/nfts/owners?wallet_addresses=&chains=ethereum"
    assert condense_sensitive_query_params(path) == path


def test_condenses_repeated_sensitive_params():
    path = f"/nfts/owners?wallet_addresses={EVM_ADDRESS}&wallet_addresses={SOLANA_ADDRESS}&chains=eth"
    assert (
        condense_sensitive_query_params(path)
        == "/nfts/owners?wallet_addresses=0x1234...7890&wallet_addresses=9xQe...VFin&chains=eth"
    )


def _access_record(full_path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %s',
        args=("127.0.0.1:1234", "GET", full_path, "1.1", 200),
        exc_info=None,
    )


def test_filter_rewrites_access_record_args():
    record = _access_record(
        f"/simplehash/api/v0/nfts/owners?wallet_addresses={EVM_ADDRESS}&chains=ethereum"
    )

    assert CondenseSensitiveQueryParamsFilter().filter(record) is True

    args = record.args
    assert isinstance(args, tuple)
    assert args[2] == (
        "/simplehash/api/v0/nfts/owners?wallet_addresses=0x1234...7890&chains=ethereum"
    )
    formatted = record.getMessage()
    assert EVM_ADDRESS not in formatted
    assert "0x1234...7890" in formatted


def test_filter_leaves_non_access_records_untouched():
    record = logging.LogRecord(
        name="app.main",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=f"wallet_addresses={EVM_ADDRESS}",
        args=None,
        exc_info=None,
    )

    assert CondenseSensitiveQueryParamsFilter().filter(record) is True
    assert record.args is None


def test_install_is_idempotent():
    access_logger = logging.getLogger("uvicorn.access")
    original = list(access_logger.filters)
    try:
        access_logger.filters = []
        install_access_log_sanitizer()
        install_access_log_sanitizer()
        matching = [
            f
            for f in access_logger.filters
            if isinstance(f, CondenseSensitiveQueryParamsFilter)
        ]
        assert len(matching) == 1
    finally:
        access_logger.filters = original
