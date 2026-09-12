# Project State

> Updated at the end of every session, by whichever agent was driving.
> Keep it under a page. This is a baton, not a diary.

**Last updated:** 2026-09-12 by claude-code

## Where things stand

The full 5-step Nostr DVM pipeline runs end to end and every step has been
verified live against real infrastructure, not mocked: Nostr identity + relay
round-trip (`nostr_core.py`), NIP-90 job dispatch (`agent.py`/`requester.py`),
real Cashu payment gating against a public test mint with a genuine
double-spend rejection (`cashu_gate.py`), and an LLM audit worker wired in
with a verified graceful-failure path (`auditor.py`). A user with Python 3.11
and an `ANTHROPIC_API_KEY` can run both scripts today and get a real audited
result back over Nostr, paid in e-cash.

## In progress

- [ ] Nothing actively half-written. The next work is verification-with-a-
      real-key and submission polish, not new code.

## The exact next step

Set `ANTHROPIC_API_KEY` in the environment and re-run the docs/VERIFY.md flow
end to end to see a real audit report (not just the graceful-error path,
which is all that's been confirmed so far since no key was available in the
build session). Then start on the Week 3/4 items from the broader hackathon
plan: git init + first public commit, Devfolio registration if not already
done, and the weekly work-summary email update.

## Open questions

- Whether to propose kind 5600 upstream to nostr-protocol/data-vending-machines
  now or after the hackathon — not blocking, just undecided.
- Whether the audit's fixed vulnerability checklist (in auditor.py's system
  prompt) should expand once real sample scripts are tried against it.

## Known traps

- **Python must be 3.11**, not whatever `python` resolves to by default —
  `cashu==0.20.3`+ pulls in `breez-sdk-spark`, which has no installable
  build here at all. Pinned to `cashu==0.19.2` instead. See docs/DECISIONS.md.
- **`marshmallow` must be `<4`** — installs fine at any version, but v4 broke
  an internal `environs` check that `cashu` imports transitively, so the
  package looks installed and then crashes on `import cashu.wallet.helpers`.
- **Always pass `and_wait` to `client.connect()`** in nostr-sdk, and always
  call `client.notifications()` *before* publishing anything you expect
  echoed back — both are silent-failure traps, not exceptions. See
  docs/DECISIONS.md for the full explanation of each.
- **Background python processes on this Windows machine did not reliably die
  from the task-runner's own stop command** during development — verify with
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` filtered by
  command line before assuming a stopped background run is actually gone,
  especially before re-testing something stateful like relay subscriptions.
