from app.api.common.models import Chain

# Default slippage percentage for providers that do not support automatic
# slippage computation
DEFAULT_SLIPPAGE_PERCENTAGE = "0.5"

# Chains temporarily excluded from swap/bridge routing entirely.
#
# Zcash is disabled because Brave Wallet currently sends a shielded-only
# unified address (u1...) as the swap recipient. Bridge providers honour
# whatever recipient they are given, so the payout lands in a shielded pool the
# wallet cannot scan: the funds arrive, but are invisible to the user.
#
# Re-enable by removing Chain.ZCASH here, once brave-core ships (and uplifts)
# the fix that sends a transparent recipient. Pair that with a
# recipient/refund_to validation guard that rejects shielded addresses, so
# shielded support doesn't come back accidentally before Ironwood ships.
SWAP_DISABLED_CHAINS: frozenset[Chain] = frozenset({Chain.ZCASH})
