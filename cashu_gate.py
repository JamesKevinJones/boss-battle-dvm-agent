"""cashu_gate.py -- Cashu e-cash payment gating for the DVM.

Redemption goes through the `cashu` (Nutshell) library, which implements the
NUT-03 blind-signature math (BDHKE) needed to actually claim a token --
never construct a raw mint HTTP call for this. See docs/DECISIONS.md.

Security note (found in review, fixed here -- see docs/DECISIONS.md): a
Cashu token's `mint` field names an arbitrary URL, and it comes from an
untrusted Nostr event that any pubkey can publish. Without an allow-list,
redeeming a token means making outbound HTTP requests to whatever host an
attacker names (SSRF), and "payment accepted" reduces to "a mint the
attacker also controls says its own token is good" -- no real economic
gate at all. TRUSTED_MINTS is checked before any network call.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from cashu.core.helpers import sum_proofs
from cashu.wallet.helpers import deserialize_token_from_string, receive
from cashu.wallet.wallet import Wallet

WALLET_DB_DIR = "keys/cashu_wallet/agent"

# Only ever talk to mints on this list -- exact scheme+host match. Override
# with a comma-separated CASHU_TRUSTED_MINTS env var to add e.g. a production
# mint; never remove the check entirely (see the module docstring above).
TRUSTED_MINTS = frozenset(
    m.strip().rstrip("/")
    for m in os.environ.get("CASHU_TRUSTED_MINTS", "https://testnut.cashu.space").split(",")
    if m.strip()
)


@dataclass
class RedemptionResult:
    ok: bool
    amount_sat: int
    error: str | None = None


def _is_trusted_mint(url: str) -> bool:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/") in TRUSTED_MINTS


async def redeem_token(token_str: str) -> RedemptionResult:
    """Decode and redeem a Cashu token, claiming it immediately at its mint so
    it can't be spent again elsewhere. Returns ok=False (never raises) on any
    failure -- invalid token, untrusted mint, unreachable mint, or
    already-spent proofs.
    """
    try:
        token_obj = deserialize_token_from_string(token_str)
    except Exception:
        return RedemptionResult(ok=False, amount_sat=0, error="invalid token")

    if not _is_trusted_mint(token_obj.mint):
        return RedemptionResult(ok=False, amount_sat=0, error="untrusted mint")

    try:
        wallet = await Wallet.with_db(token_obj.mint, WALLET_DB_DIR, unit=token_obj.unit or "sat")
        await receive(wallet, token_obj)
    except Exception:
        # Deliberately not returning str(e) here: it can carry a raw response
        # body from whatever host the mint URL pointed at, and this result
        # gets echoed into a public Nostr feedback event by agent.py.
        return RedemptionResult(ok=False, amount_sat=0, error="redemption failed")

    return RedemptionResult(ok=True, amount_sat=sum_proofs(token_obj.proofs))
