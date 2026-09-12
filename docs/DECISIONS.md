# Decisions

Append-only. Newest at the top. Never edit an old entry — if it stops being
true, add a new one that supersedes it and say so.

The point is to stop a fresh agent from "fixing" something you chose
deliberately. If a choice would look wrong without context, it belongs here.

---

## 2026-09-12 — Job kind 5600 is a deliberate unregistered extension, not an error

**Context.** NIP-90 reserves 5000-5999 for job requests, but specific numbers
are individually registered in nostr-protocol/data-vending-machines. Checked
the live registry (via `gh api repos/nostr-protocol/data-vending-machines
/contents/kinds`): 5000 Text Extraction, 5001 Summarization, 5002 Translation,
5050 Text Generation, 5100 Image Generation, 5200-5202 video, 5250 TTS, 5300
Content Discovery, 5400 Event Count, 5500 Malware Scanning, 5900-5970 various.
Nothing covers "audit a Bitcoin script/PSBT for vulnerabilities."

**Decision.** Use kind 5600 for the job request (unclaimed, sits after
Malware Scanning), kind 6600 for the result (request kind + 1000, per spec),
kind 7000 for feedback (shared across all job types per spec — not
reassigned).

**Why not 5002 (as originally drafted) or 5500.** 5002 is already Translation
— publishing unrelated audit jobs under it on a public relay would collide
with real translation DVMs listening on the same relay. 5500 (Malware
Scanning) is thematically adjacent but a different job semantically (file
malware scan vs. script logic audit) — reusing it would misrepresent what the
job actually does to anyone else parsing the kind.

**Consequences.** This is an unregistered extension. If judges or reviewers
check the kind against the public registry, the README must say so explicitly
rather than imply it's a recognized kind. If this project continues past the
hackathon, propose 5600 upstream via PR to data-vending-machines instead of
just squatting on it silently.

---

## 2026-09-12 — Cashu redemption goes through the `cashu` library, never raw HTTP

**Context.** An earlier draft of the build plan called for decoding a Cashu
token and POSTing it straight to a mint's `/v1/swap` endpoint with `httpx`.
NUT-03 swap actually requires generating new blinded messages and unblinding
the mint's signatures (BDHKE — real elliptic-curve crypto), not a bare token
string in a POST body. Hand-rolling that inside a hackathon time budget is
exactly where "looks correct" and "is correct" diverge silently.

**Decision.** Redemption goes through the `cashu` (Nutshell) package, which
already implements the blinding/unblinding math, via `cashu_gate.py` as a
thin wrapper (library or CLI subprocess) — not direct REST calls.

**Why not raw REST.** It would either fail outright (missing blinded
messages in the request) or, worse, appear to succeed while not actually
validating the token cryptographically — a silent security hole in the one
part of the project ("payment gates the AI") that's supposed to prove the
Machine Money use case.

**Consequences.** `cashu` is a hard dependency, not optional. See the version
pin below for why the version matters too.

---

## 2026-09-12 — Python pinned to 3.11 for this project; `cashu` pinned to 0.19.2

**Context.** The system's default Python is 3.14.6 (via `py -0p`). Installing
`cashu==0.20.3` (the latest at the time) failed on both 3.14 and a fresh 3.11
venv with `Could not find a version that satisfies the requirement
breez-sdk-spark<0.16.0,>=0.15.0` — that dependency range simply isn't
published/buildable for this platform at all right now, independent of
Python version. Confirmed via PyPI JSON that `cashu==0.19.2` has no
`breez-sdk-spark` dependency at all (that integration was added in 0.20.x).

**Decision.** Pin `cashu==0.19.2` in requirements.txt. Use a Python 3.11 venv
for this project (a `uv`-managed 3.11.15 interpreter was already present on
this machine at
`C:\Users\kj638\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe`)
rather than the system 3.14, since `cashu`'s own metadata still caps at
3.10-3.14 but the broken dependency makes 3.14 a moot point anyway — 3.11 is
the safer, more-tested target for this stack.

**Why not upgrade past 0.19.2 later without checking.** A newer `cashu`
release may fix the `breez-sdk-spark` availability, or may not — re-verify
with `pip install` in a scratch venv before bumping the pin, don't assume a
newer version number means it installs cleanly here.

**Consequences.** `requirements.txt` and the venv setup instructions in
`docs/VERIFY.md` must both reference Python 3.11, not whatever `python`
resolves to on a given machine.

---

## 2026-09-12 — nostr-sdk notification stream: subscribed events arrive as MESSAGE, not NEW_EVENT

**Context.** First draft of `nostr_core.listen()` filtered on
`notif.is_new_event()`, which never fired for events delivered via an active
subscription — the round-trip self-test published a note and never saw it
come back, even though the relay was, in fact, echoing it. Verified with a
raw debug script logging every notification: subscribed events arrive as
`ClientNotification.MESSAGE(relay_url, message)` wrapping a
`RelayMessage`, which — via `.as_enum()` — turns out to be an
`EVENT_MSG(subscription_id, event)` variant. `NEW_EVENT` notifications appear
to be tied to events being written to an attached `NostrDatabase`, which this
client doesn't configure.

**Decision.** `nostr_core.listen()` unwraps
`notif.message.as_enum().is_event_msg()` to get the real `Event`, not
`notif.is_new_event()`.

**Why this wasn't obvious from the docs.** The PyPI page and top-level
package don't document notification shapes; this was only found by
instrumenting a live subscription and logging every raw notification that
came back from `wss://relay.damus.io`.

**Consequences.** Any future code reading from `client.notifications()`
directly (bypassing `nostr_core.listen()`) needs to unwrap the same way, or
it will silently receive nothing for subscribed events.

---

## 2026-09-12 — always pass `and_wait` to `client.connect()`

**Context.** `Client.connect()` defaults to not waiting for relay connections
to actually establish before returning. Calling `subscribe`/`send_event`
immediately after an un-awaited `connect()` can silently no-op if the
websocket handshake hasn't finished yet — this was the first (wrong) theory
for the round-trip failure above, before the MESSAGE/NEW_EVENT issue was
found underneath it. `Duration` (the type `and_wait` expects) isn't exported
from the top-level `nostr_sdk` package — it maps to `datetime.timedelta`
under the hood (confirmed via `nostr_sdk.nostr_sdk.Duration is datetime.timedelta`).

**Decision.** `nostr_core.make_client()` always calls
`client.connect(and_wait=timedelta(seconds=8))`, never bare `connect()`.

**Why not just add a manual sleep after connect().** A fixed sleep either
wastes time when relays connect fast or isn't long enough when they're slow;
`and_wait` blocks exactly until connected (or the timeout), which is what we
actually want.

**Consequences.** Any new code that builds its own `Client()` instead of
using `nostr_core.make_client()` needs to remember this too.

---

## 2026-09-12 — dedup events by id in `nostr_core.listen()`, not per-script

**Context.** Running the Step 2 checkpoint live (agent + requester against both
default relays) showed the requester receiving the same feedback event 4
times for one job, and the agent's own log showed it received the same job
request twice. Root cause: with two relays configured, a published event
gets echoed back once per relay the subscriber is connected to, so a
single logical event surfaces as N notifications where N = number of relays
that saw it.

**Decision.** `nostr_core.listen()` tracks seen event ids in a set and
silently drops repeats, so every caller (agent.py, requester.py, anything
added later) gets each event exactly once without repeating this logic.

**Why not dedup separately in agent.py/requester.py.** Every consumer of
`listen()` would need the same set-tracking code; putting it in one place
means new scripts get correct behavior by default instead of having to
remember this gotcha.

**Consequences.** `listen()` is now stateful per call (a fresh `seen_ids` set
each time it's invoked) — don't call it twice concurrently over the same
stream expecting shared dedup state across the two calls.

---

## 2026-09-12 — pin `marshmallow<4` alongside `cashu`

**Context.** `pip install`ing the pinned requirements succeeded, but importing
`cashu.wallet.helpers` failed with
`AttributeError: module 'marshmallow' has no attribute '__version_info__'`.
`cashu` depends on `environs<10.0.0,>=9.5.0`, and `environs` 9.5.0 checks
`marshmallow.__version_info__` internally -- an attribute marshmallow 4.x
removed (keeping only `__version__` as a string). Neither `cashu` nor
`environs` pins marshmallow itself, so pip was free to resolve the newest
marshmallow (4.3.1), which is incompatible.

**Decision.** Add `marshmallow<4` to requirements.txt, resolved to 3.26.2.

**Why not wait for environs/cashu to fix it upstream.** This blocks every
import of the cashu package outright -- not a style issue, an install that
"succeeds" but is unusable. Pinning locally is the only thing that unblocks
this session now; revisit the pin if `environs` ships a marshmallow-4-aware
release later.

**Consequences.** If `cashu` or `environs` gets bumped later, re-check
whether `marshmallow<4` is still needed before dropping it.

---

## 2026-09-12 — Cashu redemption amount reported is the token's face value, not the post-fee kept amount

**Context.** Redeeming a real 64-sat testmint token via `cashu_gate.redeem_token`
printed `Received 62 sat` (the library's own log, reflecting a 2-sat mint fee
taken during the swap) while `RedemptionResult.amount_sat` reported 64 --
computed from `sum_proofs(token_obj.proofs)` on the *original* token, before
the swap. Confirmed again on two 21-sat tokens (library logged "Received 20
sat" while our result reported 21).

**Decision.** Keep reporting the original token's face value as
`amount_sat` -- that's the amount the *payer* committed to and the number
that should be compared against the job's advertised `amount` tag. The
mint's swap fee is an internal cost to the agent's own wallet balance, not
something that should make a job with a correctly-sized payment look
underpaid.

**Why not report the post-fee kept amount.** Doing so would make the
payment-verification threshold depend on a specific mint's fee schedule,
which can change and vary by mint -- irrelevant to whether the requester
actually paid what they said they'd pay.

**Consequences.** `agent.py`'s comparison of `redemption.amount_sat` against
the job's requested amount should use the face value; don't "fix" this to
use the wallet's post-swap balance delta.

---

## 2026-09-12 — mint allow-list, amount enforcement, and generic error messages (security review findings)

**Context.** Ran a security review (methodology from `.claude/commands/security-review.md`,
applied manually since this is a first commit with no `origin` to diff
against yet) against the whole initial codebase before pushing. It surfaced
two real, high-confidence findings, both rooted in the same gap: nothing
validated the Cashu token's `mint` field, which comes straight from an
untrusted Nostr event any pubkey can publish.

1. **SSRF + response echo.** `cashu_gate.redeem_token()` passed
   `token_obj.mint` straight to `Wallet.with_db()`/`receive()`, which makes
   real outbound HTTP requests to that URL before any proof validation. An
   attacker could point `mint` at an internal address (cloud metadata
   endpoint, localhost service) and the agent would call it. Worse, the raw
   exception text (which can carry a response body from whatever host
   answered) was returned as `RedemptionResult.error` and then republished
   verbatim into a *public* Nostr feedback event by `agent.py` — a read
   channel into internal network responses, visible to anyone watching the
   relay.
2. **Payment gate wasn't real authorization.** Nothing checked
   `redemption.amount_sat` against the job's advertised `amount` tag, and
   nothing restricted which mints were trusted. Anyone can run their own
   Cashu mint and have it "validate" its own self-issued tokens for any face
   value, so without a mint allow-list, "payment accepted" reduced to "a
   server the attacker controls says its own token is fine" — free unlimited
   LLM calls, defeating the entire Machine Money premise of this project.

**Decision.**
- `cashu_gate.py` now checks `token_obj.mint` against a `TRUSTED_MINTS`
  allow-list (default: just `https://testnut.cashu.space`, override via
  `CASHU_TRUSTED_MINTS`) *before* any network call — fixes both the SSRF and
  the self-issued-mint bypass.
- `cashu_gate.redeem_token()` no longer returns raw exception text; it
  returns one of three fixed strings ("invalid token", "untrusted mint",
  "redemption failed") so nothing from an arbitrary remote host can end up
  in a public feedback event's content.
- `agent.py` now compares `redemption.amount_sat * 1000` against the job's
  `amount` tag (millisats) and rejects with `payment-required` if the token
  paid less than advertised, so redemption succeeding is never sufficient on
  its own to authorize running the paid audit.

**Why not just document the mint-trust gap as a known limitation (as the
first draft of the README did) and move on.** That was fine for "we know
Cashu tokens name arbitrary mints" as a design note, but it understated the
actual severity: this wasn't just an edge case, it was an open SSRF
primitive plus a complete bypass of the project's one economic control,
both reachable by anyone who can publish a Nostr event (no auth needed).
Worth fixing before the repo goes public, not worth shipping as a caveat.

**Consequences.** Any new mint added later (e.g. a real production mint)
must be added to `CASHU_TRUSTED_MINTS` explicitly — there is deliberately no
"trust on first use" fallback. Verified post-fix: a valid token from an
untrusted mint is rejected before any redemption attempt; the same token
against a trusted mint still works; a validly-redeemed but underpaid token
is rejected with `payment-required` instead of proceeding to the audit.

---

## YYYY-MM-DD — <the decision, stated as a fact>

**Context.** What forced a choice.

**Decision.** What we picked.

**Why not the alternative.** The one that looks more obvious from outside —
this is the line that actually prevents the re-litigation.

**Consequences.** What this now constrains.

---
