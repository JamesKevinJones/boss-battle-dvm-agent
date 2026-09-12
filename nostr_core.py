"""Shared Nostr helpers: keypair storage, relay client, event build/sign, publish/listen.

Both agent.py and requester.py import this instead of talking to nostr-sdk directly.
"""

import asyncio
from datetime import timedelta
from pathlib import Path

from nostr_sdk import Client, Event, EventBuilder, Filter, Keys, Kind, RelayUrl, ReqTarget, Tag

CONNECT_TIMEOUT = timedelta(seconds=8)

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
]


def load_or_create_keys(key_file: str) -> Keys:
    """Load an nsec from key_file, generating and persisting one on first run."""
    path = Path(key_file)
    if path.exists():
        return Keys.parse(path.read_text().strip())

    keys = Keys.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(keys.secret_key().to_bech32())
    return keys


async def make_client(relays: list[str] | None = None) -> Client:
    """Build a Client connected to the given relays (defaults to DEFAULT_RELAYS)."""
    client = Client()
    for url in relays or DEFAULT_RELAYS:
        await client.add_relay(RelayUrl.parse(url))
    # and_wait matters: without it, connect() returns before the websocket
    # handshake finishes, and a subscribe/publish issued right after can be
    # silently dropped because no relay is actually connected yet.
    await client.connect(and_wait=CONNECT_TIMEOUT)
    return client


def build_event(keys: Keys, kind: int, content: str, tags: list[Tag] | None = None) -> Event:
    """Build and sign an event of the given kind/content/tags."""
    builder = EventBuilder(Kind(kind), content)
    if tags:
        builder = builder.tags(tags)
    return builder.finalize(keys)


async def publish(client: Client, event: Event) -> None:
    await client.send_event(event)


async def subscribe(client: Client, filter_: Filter) -> None:
    """Register a subscription; use listen() afterwards to consume matching events."""
    await client.subscribe(ReqTarget.auto([filter_]))


def open_notification_stream(client: Client):
    """Open the notification stream now. Call this BEFORE publishing anything you
    expect to see echoed back — the stream only carries events from the moment
    it's opened, so opening it late silently misses events the relay already sent.
    """
    return client.notifications()


async def listen(stream, timeout_seconds: float = 30.0):
    """Yield Events from an already-open notification stream (see open_notification_stream),
    until timeout_seconds pass with no new event.

    Events matched by a subscription arrive wrapped as a raw relay protocol
    message (ClientNotification.MESSAGE -> RelayMessageEnum.EVENT_MSG), not as
    ClientNotification.NEW_EVENT -- that variant only fires for events that get
    written to an attached NostrDatabase, which this client doesn't use.

    With multiple relays (see DEFAULT_RELAYS), the same event is typically
    delivered once per relay that has it -- deduplicated here by event id so
    callers see each event exactly once.
    """
    seen_ids: set[str] = set()
    while True:
        try:
            notif = await asyncio.wait_for(stream.next(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return
        if notif is None:
            return
        if not notif.is_message():
            continue
        relay_msg = notif.message.as_enum()
        if not relay_msg.is_event_msg():
            continue
        event = relay_msg.event
        event_id = event.id().to_hex()
        if event_id in seen_ids:
            continue
        seen_ids.add(event_id)
        yield event


async def _self_test() -> None:
    """NIP-01 round-trip check: publish a kind:1 note, then see it come back from the relay."""
    keys = load_or_create_keys("keys/selftest.nsec")
    print(f"Test identity: {keys.public_key().to_bech32()}")

    client = await make_client()

    filt = Filter().author(keys.public_key()).kind(Kind(1)).limit(10)
    await subscribe(client, filt)
    stream = open_notification_stream(client)  # open BEFORE publishing, see docstring
    await asyncio.sleep(1)  # let the relay register the subscription before we publish

    note = build_event(keys, 1, "nostr_core self-test round-trip")
    await publish(client, note)
    note_id = note.id().to_hex()
    print(f"Published event id: {note_id}")

    print("Waiting for it to come back from the relay...")
    seen = False
    async for event in listen(stream, timeout_seconds=15):
        if event.id().to_hex() == note_id:
            print(f"Round-trip OK: received back event {event.id().to_hex()}")
            seen = True
            break

    if not seen:
        print("Round-trip FAILED: did not see the event come back within 15s")

    await client.shutdown()


if __name__ == "__main__":
    asyncio.run(_self_test())
