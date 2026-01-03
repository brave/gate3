import re


def is_evm_address(address: str) -> bool:
    return bool(re.match(r"^0x[a-fA-F0-9]{40}$", address))


def is_solana_address(address: str) -> bool:
    # Solana addresses are typically 32-44 characters in base58.
    #
    # This is a simplified check and does not guarantee that the address is
    # valid.
    return bool(re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", address))


def is_address_equal(a: str | None, b: str | None) -> bool:
    """Case-insensitive address comparison."""
    return (a or "").lower() == (b or "").lower()
