# boss-battle-dvm-agent

A Nostr DVM (NIP-90) that audits Bitcoin Script / miniscript / PSBT snippets
for common vulnerabilities, paid via Cashu e-cash tokens attached to the job
request. Built for Bitshala's BOSS Battle hackathon, Machine Money track
("Democratizing AI Usage"). Two standalone scripts: `agent.py` (the DVM,
listens for jobs, gates on payment, runs the audit) and `requester.py` (CLI
demo client that submits a job and waits for the result).

## Stack

- Language / runtime: Python 3.11 (pinned — see docs/DECISIONS.md, `cashu`
  does not install on 3.13+ as of this writing)
- Nostr: `nostr-sdk` 0.45.1 (rust-nostr Python bindings, alpha — API can break
  between versions, keep pinned)
- Ecash: `cashu` (Nutshell) 0.19.2, driven via its library/CLI, never raw
  mint HTTP calls (see docs/DECISIONS.md)
- AI: `anthropic` Python SDK
- No web framework, no database — both scripts are long-running CLI processes
  talking to public Nostr relays and a public Cashu testmint

## Layout

```
nostr_core.py     # shared: keys, relay client, event build/sign, publish/listen
agent.py          # the DVM: subscribe, payment-gate, audit, publish result
requester.py      # CLI client: submit a job, attach payment, wait for result
cashu_gate.py     # Cashu token redemption via the cashu library (Step 3)
keys/             # generated nsec files, gitignored — never commit these
docs/VERIFY.md    # exact run commands for a clean-machine reproduction
```

## Rules

1. Never hand-roll Cashu swap/redemption crypto — always go through the
   `cashu` package. See docs/DECISIONS.md.
2. Any new Nostr job kind must be checked against the live
   nostr-protocol/data-vending-machines registry before use — don't assume a
   kind number is free from memory.
3. No AI/Claude attribution anywhere in code, comments, commits, or docs —
   sole author is the human maintainer.
4. Run `docs/VERIFY.md` end to end before calling a step done.
5. Don't add dependencies without checking they actually install in the
   pinned Python 3.11 venv first (see docs/DECISIONS.md for why).

## Read these too

- `docs/STATE.md` — where we stopped, what's next
- `docs/DECISIONS.md` — why things are the way they are
- `docs/VERIFY.md` — how to prove a change works

## Don't touch

- `keys/*.nsec` — generated locally per machine, gitignored, never regenerate
  someone else's on purpose.
