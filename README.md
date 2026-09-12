# Nostr DVM Bitcoin Script Auditor

**Author:** Kevin Jones

**Demo video:** _TODO -- recorded closer to the 05 Oct submission freeze, per
the hackathon's own guidance to record it "before the last night," not this
early in the build._

Built for Bitshala's BOSS Battle hackathon, **Machine Money** track
("Democratizing AI Usage" problem statement).

## The problem

Bitcoin Script, miniscript, and PSBT bugs are easy to introduce and hard to
self-review -- wrong multisig thresholds, unhandled `OP_IF` branches,
malleability, locktime misuse. Getting a second pair of eyes on a script
today means either finding a Bitcoin dev to ask, or trusting a hosted AI tool
that sees your script in plaintext and bills you through a bank card and an
account it can tie back to you.

## The approach

A Nostr **Data Vending Machine** (NIP-90): a job-request/job-result protocol
over Nostr relays. The requester publishes a script/PSBT as a job request,
attaches a **Cashu e-cash token** as payment, and a listening DVM agent:

1. verifies and redeems the token at its mint (real cryptographic
   double-spend protection -- not a bare API call, see below),
2. runs the audit through an LLM scoped specifically to Bitcoin-script
   footguns (not a generic "summarize anything" wrapper),
3. publishes the signed result back to the relay.

No account, no bank card, no central server between requester and agent --
just Nostr keypairs (cryptographic identity), a public relay (no
intermediary), and Cashu sats (bearer e-cash, unlinkable between mint and
spender by the mint's own blind-signature design).

```
requester.py                    relay (wss://...)              agent.py
  |  publish kind:5600 job  ---------->  |
  |  (script/PSBT + Cashu token)         |  <---- subscribe kind:5600
  |                                       |         |
  |                                       |   redeem Cashu token at mint
  |                                       |   run LLM audit (Anthropic API)
  |                                       |         |
  |  <---- kind:6600 result ------------  |  <------+
  |  <---- kind:7000 feedback ----------  |  (payment-required / processing / error)
```

## What's finished

- Nostr identity, relay connect, event build/sign/publish/subscribe
  (`nostr_core.py`) -- verified with a live NIP-01 round-trip self-test.
- Full NIP-90 job dispatch: job request -> `processing`/`payment-required`/
  `error` feedback -> signed result, verified end to end against two public
  relays.
- Real Cashu payment gating (`cashu_gate.py`): decodes a token, redeems it via
  the `cashu` library (which implements the actual NUT-03 blinding math, not
  a stubbed HTTP call), rejects missing/invalid/already-spent tokens.
  Verified against a live public test mint, including a real double-spend
  rejection from the mint itself.
- LLM audit worker (`auditor.py`) scoped to a fixed checklist: multisig
  threshold errors, preimage exposure, unhandled `OP_IF`/`OP_ELSE`,
  malleability, locktime misuse, oversized witness data. Wired into the
  agent; failure path (e.g. missing API key) verified to degrade to a clean
  `error` feedback event rather than crashing the agent process.

## What's not finished yet

- The actual audit *output* (real LLM responses on real vulnerable scripts)
  is wired but not yet demonstrated end-to-end in this README -- needs an
  `ANTHROPIC_API_KEY` in the environment to run, see docs/VERIFY.md.
- No mint allow-list -- the agent trusts whatever mint a token names. Fine
  for a demo against one known test mint; a real deployment would need a
  configured trusted-mint list.
- Requester is a CLI only, deliberately -- this project targets Machine
  Money, where use case is the test, not Freedom Stack, where UI/UX is
  decisive. See docs/DECISIONS.md if that scope call changes later.
- Job kind `5600` is a proposed, currently-unregistered NIP-90 extension
  (checked the live kind registry -- nothing existing covers this job type).
  Not yet proposed upstream to nostr-protocol/data-vending-machines.

## Setup and run

See **docs/VERIFY.md** for exact, copy-pasteable commands (venv setup,
minting a free test payment token, running both scripts, and the expected
output at each step) -- written to be followed on a machine that has never
touched this repo before.

Short version:

```bash
python -m venv .venv                      # Python 3.11 specifically, see docs/DECISIONS.md
.venv/Scripts/python.exe -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=...              # needed for the actual audit step
.venv/Scripts/python.exe -u agent.py       # terminal 1
.venv/Scripts/python.exe -u requester.py --input "<script>" --amount 1000 --token "<cashu token>"   # terminal 2
```

## Known limitations

See "What's not finished yet" above, plus the full reasoning behind every
non-obvious choice (the Cashu payment-tag extension, the kind-5600 choice,
the Python/dependency pinning, the multi-relay dedup and history-replay
fixes found while building this) in **docs/DECISIONS.md**.

## License

MIT -- see LICENSE.
