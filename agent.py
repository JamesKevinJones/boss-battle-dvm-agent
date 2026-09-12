"""agent.py -- the DVM: subscribes to job requests, gates on payment, runs the audit,
publishes results. Kind numbers are a deliberate unregistered NIP-90 extension --
see docs/DECISIONS.md.
"""

import asyncio
from pathlib import Path

from nostr_sdk import Event, Filter, Kind, Tag, Timestamp

import auditor
import cashu_gate
import nostr_core as core

JOB_REQUEST_KIND = 5600
JOB_RESULT_KIND = 6600
JOB_FEEDBACK_KIND = 7000

AGENT_KEY_FILE = "keys/agent.nsec"
AGENT_NPUB_FILE = "keys/agent.npub"


def publish_agent_npub(keys: core.Keys) -> None:
    """Write our public key where requester.py can find it (public info, not secret)."""
    path = Path(AGENT_NPUB_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(keys.public_key().to_bech32())


def tag_value(event: Event, tag_name: str) -> str | None:
    for tag in event.tags():
        vec = tag.to_vec()
        if vec and vec[0] == tag_name:
            return vec[1] if len(vec) > 1 else None
    return None


def extract_cashu_token(event: Event) -> str | None:
    """Custom tag ["payment", "cashu", "<token>"] -- see docs/DECISIONS.md on
    why NIP-90's bolt11-oriented amount tag doesn't cover Cashu payment."""
    for tag in event.tags():
        vec = tag.to_vec()
        if len(vec) >= 3 and vec[0] == "payment" and vec[1] == "cashu":
            return vec[2]
    return None


async def send_feedback(client, keys, request_event: Event, status: str, content: str = "") -> None:
    feedback = core.build_event(
        keys,
        JOB_FEEDBACK_KIND,
        content,
        tags=[
            Tag.event(request_event.id()),
            Tag.public_key(request_event.author()),
            Tag.parse(["status", status]),
        ],
    )
    await core.publish(client, feedback)
    print(f"[agent] published feedback: status={status}")


async def send_result(client, keys, request_event: Event, report_markdown: str) -> None:
    result = core.build_event(
        keys,
        JOB_RESULT_KIND,
        report_markdown,
        tags=[
            Tag.event(request_event.id()),
            Tag.public_key(request_event.author()),
        ],
    )
    await core.publish(client, result)
    print("[agent] published audit result")


async def handle_job(client, keys, request_event: Event) -> None:
    request_id = request_event.id()
    print(f"[agent] received job request {request_id.to_hex()} from {request_event.author().to_bech32()}")

    payload = tag_value(request_event, "i")
    print(f"[agent] job input: {payload!r}")

    token = extract_cashu_token(request_event)
    if token is None:
        print("[agent] no payment tag -- rejecting job")
        await send_feedback(client, keys, request_event, "payment-required")
        return

    redemption = await cashu_gate.redeem_token(token)
    if not redemption.ok:
        print(f"[agent] payment invalid: {redemption.error}")
        await send_feedback(client, keys, request_event, "error", f"payment rejected: {redemption.error}")
        return

    print(f"[agent] payment accepted: {redemption.amount_sat} sat")
    await send_feedback(client, keys, request_event, "processing")

    try:
        # anthropic's client is synchronous/blocking -- run it off the event
        # loop so it doesn't stall relay I/O (websocket pings, other jobs)
        # while the audit is in flight.
        report = await asyncio.to_thread(auditor.audit, payload or "")
    except Exception as e:
        print(f"[agent] audit failed: {e}")
        await send_feedback(client, keys, request_event, "error", f"audit failed: {e}")
        return

    await send_result(client, keys, request_event, report)


async def main() -> None:
    keys = core.load_or_create_keys(AGENT_KEY_FILE)
    publish_agent_npub(keys)
    print(f"[agent] pubkey: {keys.public_key().to_bech32()}")

    client = await core.make_client()

    # since=now: a relay replays its stored history to match a fresh subscription,
    # not just live events -- without this, every restart re-processes every
    # job ever sent to this agent since the beginning of time.
    filt = Filter().kind(Kind(JOB_REQUEST_KIND)).pubkey(keys.public_key()).since(Timestamp.now())
    await core.subscribe(client, filt)
    stream = core.open_notification_stream(client)

    print("[agent] listening for job requests (5 min)...")
    async for event in core.listen(stream, timeout_seconds=300):
        await handle_job(client, keys, event)

    await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
