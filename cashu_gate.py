"""cashu_gate.py -- Cashu e-cash payment gating for the DVM.

Redemption goes through the `cashu` (Nutshell) library, which implements the
NUT-03 blind-signature math (BDHKE) needed to actually claim a token --
never construct a raw mint HTTP call for this. See docs/DECISIONS.md.

Known limitation: trusts whatever mint a token names, with no allow-list --
acceptable for a hackathon demo against a known public mint, not for
production use with untrusted tokens. See README.
"""

from dataclasses import dataclass

from cashu.core.helpers import sum_proofs
from cashu.wallet.helpers import deserialize_token_from_string, receive
from cashu.wallet.wallet import Wallet

WALLET_DB_DIR = "keys/cashu_wallet/agent"


@dataclass
class RedemptionResult:
    ok: bool
    amount_sat: int
    error: str | None = None


async def redeem_token(token_str: str) -> RedemptionResult:
    """Decode and redeem a Cashu token, claiming it immediately at its mint so
    it can't be spent again elsewhere. Returns ok=False (never raises) on any
    failure -- invalid token, unreachable mint, or already-spent proofs.
    """
    try:
        token_obj = deserialize_token_from_string(token_str)
    except Exception as e:
        return RedemptionResult(ok=False, amount_sat=0, error=f"invalid token: {e}")

    try:
        wallet = await Wallet.with_db(token_obj.mint, WALLET_DB_DIR, unit=token_obj.unit or "sat")
        await receive(wallet, token_obj)
    except Exception as e:
        return RedemptionResult(ok=False, amount_sat=0, error=str(e))

    return RedemptionResult(ok=True, amount_sat=sum_proofs(token_obj.proofs))
