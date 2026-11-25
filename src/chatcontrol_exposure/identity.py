from collections import Counter
from math import ceil

from chatcontrol_exposure.models import ContactStats, HeaderMessage
from chatcontrol_exposure.parse import normalize_address


def detect_own_addresses(messages: list[HeaderMessage]) -> list[str]:
    """Guess mailbox owner addresses from header frequency.

    The owner of a sent folder is the From address on most messages. The owner
    of an inbox is the recipient on most messages. Both show up on more
    messages than any single correspondent. Fewer than three messages is too
    little to guess. A tie is left unresolved so the caller can pass ``--me``.
    """

    if len(messages) < 3:
        return []
    presence: Counter[str] = Counter()
    from_counts: Counter[str] = Counter()
    for message in messages:
        seen: set[str] = set()
        if message.from_addr:
            from_counts[message.from_addr] += 1
            seen.add(message.from_addr)
        seen.update(message.recipients)
        for address in seen:
            presence[address] += 1
    if not presence:
        return []
    total = len(messages)
    top = max(presence.values())
    if top < ceil(total * 0.5):
        return []
    leaders = [address for address, count in presence.items() if count == top]
    if len(leaders) == 1:
        return leaders
    from_top = max(from_counts[address] for address in leaders)
    narrowed = [address for address in leaders if from_counts[address] == from_top]
    if len(narrowed) == 1:
        return narrowed
    return []


def normalize_own_addresses(raw_addresses: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in raw_addresses:
        address = normalize_address(raw)
        if address is None or address in seen:
            continue
        seen.add(address)
        found.append(address)
    return found


def build_contacts(
    messages: list[HeaderMessage],
    own_addresses: list[str],
) -> tuple[list[tuple[str, ...]], list[bool], list[ContactStats]]:
    """Split each message into sent or received and tally correspondents.

    A message you sent counts as sent for every recipient other than you.
    A message someone else sent counts as received for the sender and for
    every other recipient other than you.
    """

    own = set(own_addresses)
    stats: dict[str, ContactStats] = {}
    message_contacts: list[tuple[str, ...]] = []
    message_sent: list[bool] = []
    for message in messages:
        sent = message.from_addr is not None and message.from_addr in own
        parties: list[str] = []
        seen: set[str] = set()
        candidates: list[str | None] = [message.from_addr, *message.recipients]
        for address in candidates:
            if address is None or address in own or address in seen:
                continue
            seen.add(address)
            parties.append(address)
        message_contacts.append(tuple(parties))
        message_sent.append(sent)
        for address in parties:
            contact = stats.get(address)
            if contact is None:
                contact = ContactStats(address=address)
                stats[address] = contact
            if sent:
                contact.sent += 1
                continue
            contact.received += 1
    ordered = sorted(stats.values(), key=lambda item: (-item.messages, item.address))
    return message_contacts, message_sent, ordered
