"""requester.py -- CLI demo client: submit a Bitcoin script/PSBT audit job to the
DVM agent and wait for feedback/result. Run agent.py first (at least once) so it
publishes its pubkey to keys/agent.npub.
"""

import argparse
import asyncio
from pathlib import Path

from nostr_sdk import Event, Filter, Kind, PublicKey, Tag, Timestamp

import nostr_core as core

JOB_REQUEST_KIND = 5600
JOB_RESULT_KIND = 6600
JOB_FEEDBACK_KIND = 7000

REQUESTER_KEY_FILE = "keys/requester.nsec"
AGENT_NPUB_FILE = "keys/agent.npub"


def load_agent_pubkey() -> PublicKey:
    path = Path(AGENT_NPUB_FILE)
    if not path.exists():
        raise SystemExit(
            f"{AGENT_NPUB_FILE} not found -- start agent.py at least once first, "
            "it publishes its pubkey there on startup."
        )
    return PublicKey.parse(path.read_text().strip())


def tag_value(event: Event, tag_name: str) -> str | None:
    for tag in event.tags():
        vec = tag.to_vec()
        if vec and vec[0] == tag_name:
            return vec[1] if len(vec) > 1 else None
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a Bitcoin script/PSBT audit job to the DVM agent.")
    parser.add_argument("--input", required=True, help="The Bitcoin Script, miniscript, or PSBT text to audit.")
    parser.add_argument("--amount", default="1000", help="Millisats to advertise as the job's amount tag.")
    parser.add_argument("--token", default=None, help="Cashu token (cashuA.../cashuB...) to pay for the job.")
    args = parser.parse_args()

    keys = core.load_or_create_keys(REQUESTER_KEY_FILE)
    agent_pubkey = load_agent_pubkey()
    print(f"[requester] my pubkey: {keys.public_key().to_bech32()}")
    print(f"[requester] agent pubkey: {agent_pubkey.to_bech32()}")

    client = await core.make_client()

    # Subscribe (and open the stream) for feedback/results addressed to us,
    # BEFORE publishing the job -- see nostr_core.open_notification_stream.
    # since=now: see agent.py -- a fresh subscription otherwise replays a relay's
    # entire matching history, not just events from this run.
    filt = (
        Filter()
        .kinds([Kind(JOB_RESULT_KIND), Kind(JOB_FEEDBACK_KIND)])
        .pubkey(keys.public_key())
        .since(Timestamp.now())
    )
    await core.subscribe(client, filt)
    stream = core.open_notification_stream(client)
    await asyncio.sleep(1)

    tags = [
        Tag.parse(["i", args.input, "text"]),
        Tag.public_key(agent_pubkey),
        Tag.parse(["amount", args.amount]),
    ]
    if args.token:
        tags.append(Tag.parse(["payment", "cashu", args.token]))
    job = core.build_event(keys, JOB_REQUEST_KIND, "", tags=tags)
    await core.publish(client, job)
    job_id = job.id().to_hex()
    print(f"[requester] published job request {job_id}")

    print("[requester] waiting for feedback/result (60s)...")
    async for event in core.listen(stream, timeout_seconds=60):
        if tag_value(event, "e") != job_id:
            continue
        if event.kind().as_u16() == JOB_FEEDBACK_KIND:
            status = tag_value(event, "status")
            print(f"[requester] feedback: status={status}")
            if status in ("payment-required", "error"):
                if event.content():
                    print(f"[requester]   {event.content()}")
                break
        elif event.kind().as_u16() == JOB_RESULT_KIND:
            print("[requester] --- result ---")
            print(event.content())
            break

    await client.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
