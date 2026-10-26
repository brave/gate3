from app.api.common.models import Chain

# Default slippage percentage for providers that do not support automatic
# slippage computation
DEFAULT_SLIPPAGE_PERCENTAGE = "0.5"

# Chains temporarily excluded from swap/bridge routing entirely.
# Kill switch, not a capability check: providers may still support
# pairs on a listed chain. See is_swap_disabled_chain in
# app/api/swap/utils.py.
SWAP_DISABLED_CHAINS: frozenset[Chain] = frozenset()
