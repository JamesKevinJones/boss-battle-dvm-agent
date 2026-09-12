# Verification

Exact commands to prove this works, on a clean machine, in two terminals.

Rule: **don't report work as done without running these.** "It should work" is
not a result.

## Prerequisites

- **Python 3.11** specifically. `cashu`'s dependency tree does not currently
  install cleanly on 3.13+ (see docs/DECISIONS.md) -- check with
  `python --version` before creating the venv, and use a 3.11 interpreter
  (`py -3.11`, `python3.11`, or install one) if your default `python` is newer.
- An `ANTHROPIC_API_KEY` in your environment (`export ANTHROPIC_API_KEY=...`
  on macOS/Linux, `$env:ANTHROPIC_API_KEY = "..."` in PowerShell). Without it,
  Step 4 below still runs but the agent will report `status=error` with an
  authentication message instead of a real audit -- that's the SDK's own
  error, not a bug in this repo.
- Internet access: this project talks to public relays
  (`wss://relay.damus.io`, `wss://nos.lol`) and a public Cashu test mint
  (`https://testnut.cashu.space` -- a FakeWallet-backed mint made for testing;
  any Lightning invoice against it is auto-marked paid, so minting a test
  token costs nothing real).

## Install

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

## Get a test Cashu token to pay with

The agent only processes jobs that carry a valid Cashu token. Mint one for
free against the test mint:

```bash
.venv/Scripts/python.exe -c "
import asyncio
from cashu.wallet.wallet import Wallet

async def main():
    wallet = await Wallet.with_db('https://testnut.cashu.space', 'keys/cashu_wallet/funding', unit='sat')
    await wallet.load_mint()
    quote = await wallet.request_mint(100)
    proofs = await wallet.mint(100, quote.quote)
    print(await wallet.serialize_proofs(proofs))

asyncio.run(main())
"
```

This prints a `cashuB...` token string. Copy it for the `--token` argument
below.

## Run it (two terminals)

**Terminal 1 -- start the agent:**

```bash
.venv/Scripts/python.exe -u agent.py
```

Wait for `[agent] listening for job requests (5 min)...`. On its very first
run this also writes `keys/agent.npub`, which `requester.py` needs to find it.

**Terminal 2 -- submit a job:**

```bash
.venv/Scripts/python.exe -u requester.py \
  --input "OP_IF OP_2 <pubA> <pubB> <pubC> OP_3 OP_CHECKMULTISIG OP_ELSE OP_CHECKLOCKTIMEVERIFY OP_ENDIF" \
  --amount 1000 \
  --token "cashuB...(the token from the previous step)"
```

### Expected output

Terminal 2 (requester) should show, in order:

```
[requester] published job request <id>
[requester] waiting for feedback/result (60s)...
[requester] feedback: status=processing
[requester] --- result ---
<Markdown audit report, or an "audit failed" error line if ANTHROPIC_API_KEY isn't set>
```

Terminal 1 (agent) should show the matching sequence: job received, payment
accepted with the sat amount, `processing` feedback published, then either
the audit result or an `audit failed` error line.

### Also worth checking (already covered by earlier development, re-verify after any change)

- **No `--token` at all**: agent replies `status=payment-required`, no audit runs.
- **A garbage `--token`** (e.g. `--token notarealtoken`): agent replies
  `status=error` with an "invalid token" message.
- **The same valid token used twice**: the second use fails with a real
  mint-side "Token Already Spent" error -- this is the actual double-spend
  protection working, not a bug.

## Self-test (relay plumbing only, no payment/LLM)

```bash
.venv/Scripts/python.exe nostr_core.py
```

Should print a generated identity, publish a note, and confirm
`Round-trip OK: received back event <id>` within ~15 seconds.

## Known-failing / known limitations

- No mint allow-list: the agent trusts whatever mint a submitted token names.
  Fine against the known public test mint used here; not a production-safe
  default. See cashu_gate.py's docstring and docs/DECISIONS.md.
- Job kind `5600` is a deliberate, currently-unregistered NIP-90 extension
  (nothing in the official kind registry covers "audit a Bitcoin script") --
  see docs/DECISIONS.md for the full reasoning and the registry numbers
  checked.
- Requires Python 3.11 specifically; not yet re-tested against newer `cashu`
  releases that might lift that constraint (see docs/DECISIONS.md).
