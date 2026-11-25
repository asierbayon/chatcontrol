import json
from collections import defaultdict

from chatcontrol_exposure.analyze import (
    exposed_message_indexes,
    message_has_unknown,
    scanning_contacts,
    unknown_contacts,
)
from chatcontrol_exposure.models import Analysis, ContactStats, Provider
from chatcontrol_exposure.privacy import display_address


def percent(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return round(100.0 * part / whole, 1)


def _count(n: int, singular: str) -> str:
    word = singular if n == 1 else singular + "s"
    return f"{n} {word}"


def _claim_word(value: bool | str) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _provider_rows(analysis: Analysis) -> list[dict]:
    buckets: dict[str, dict] = {}
    for contact in analysis.contacts:
        provider = contact.provider
        if provider is None:
            continue
        row = buckets.get(provider.id)
        if row is None:
            row = {
                "id": provider.id,
                "name": provider.name,
                "provider": provider,
                "contacts": 0,
                "messages": 0,
            }
            buckets[provider.id] = row
        row["contacts"] += 1
        row["messages"] += contact.messages
    rows = list(buckets.values())
    rows.sort(key=lambda item: (-item["messages"], item["name"]))
    return rows


def _recommendations(analysis: Analysis) -> list[str]:
    total_messages = len(analysis.messages)
    total_contacts = len(analysis.contacts)
    exposed_indexes = exposed_message_indexes(analysis)
    exposed_messages = len(exposed_indexes)
    exposed_people = scanning_contacts(analysis)
    unknown_people = unknown_contacts(analysis)
    unknown_message_count = 0
    for index in range(total_messages):
        if index in set(exposed_indexes):
            continue
        if message_has_unknown(analysis, index):
            unknown_message_count += 1
    lines: list[str] = []
    if analysis.own_address_source == "undetected":
        lines.append(
            "No own address could be told apart from correspondents. "
            "Pass --me for each of your addresses and run the report again. "
            "Until then, every address is counted as a correspondent and sent versus received is not reliable."
        )
    if total_messages == 0:
        lines.append("The mailbox has no messages, so there is no exposure share to report.")
        return lines
    lines.append(
        f"{percent(exposed_messages, total_messages)}% of messages "
        f"({exposed_messages} of {total_messages}) and "
        f"{percent(len(exposed_people), total_contacts)}% of contacts "
        f"({len(exposed_people)} of {total_contacts}) are with a provider whose "
        "documentation says it voluntarily scans for child sexual abuse material. "
        "Messages and contacts whose scanning status is unknown are not included in that share."
    )
    volume: dict[str, int] = defaultdict(int)
    for contact in exposed_people:
        provider = contact.provider
        if provider is None:
            continue
        volume[provider.name] += contact.messages
    if volume:
        ranked = sorted(volume.items(), key=lambda item: (-item[1], item[0]))
        parts = [f"{name} ({_count(count, 'message')})" for name, count in ranked]
        lines.append(
            "Contact-message volume at those providers: " + "; ".join(parts) + "."
        )
    if exposed_people:
        top = max(exposed_people, key=lambda item: (item.messages, item.address))
        remaining = len(exposed_message_indexes(analysis, skip_address=top.address))
        delta = exposed_messages - remaining
        lines.append(
            f"The highest-volume contact at a scanning provider is on "
            f"{_count(top.messages, 'message')}. If that correspondence moved to a "
            "provider that does not document voluntary scanning, and every other "
            f"contact stayed put, exposed messages would go from {exposed_messages} "
            f"to {remaining} ({_count(delta, 'message')} fewer)."
        )
    lines.append(
        f"{_count(unknown_message_count, 'message')} "
        f"{'is' if unknown_message_count == 1 else 'are'} not counted as exposed "
        f"and still involve a provider with unknown scanning status "
        f"({_count(len(unknown_people), 'contact')})."
    )
    lines.append(
        "This counts where messages were addressed. It does not show that any "
        "particular message was scanned. Mail delivered to a provider is processed "
        "on that provider's systems even when your own provider encrypts mail "
        "between its own users."
    )
    return lines


def _contact_dict(contact: ContactStats, mode: str) -> dict:
    provider = contact.provider
    scanning = False if provider is None else provider.scans
    return {
        "address": display_address(contact.address, mode),
        "provider_id": None if provider is None else provider.id,
        "provider": None if provider is None else provider.name,
        "sent": contact.sent,
        "received": contact.received,
        "messages": contact.messages,
        "exposed": scanning,
        "known_voluntary_scanning": None
        if provider is None
        else provider.known_voluntary_scanning.value,
    }


def _provider_dict(row: dict) -> dict:
    provider: Provider = row["provider"]
    return {
        "id": provider.id,
        "name": provider.name,
        "jurisdiction": provider.jurisdiction.as_dict(),
        "e2e_by_default": provider.e2e_by_default.as_dict(),
        "known_voluntary_scanning": provider.known_voluntary_scanning.as_dict(),
        "notes": provider.notes,
        "contacts": row["contacts"],
        "messages": row["messages"],
        "exposed": provider.scans,
    }


def report_dict(analysis: Analysis, *, address_mode: str, top: int) -> dict:
    total_messages = len(analysis.messages)
    total_contacts = len(analysis.contacts)
    exposed_messages = len(exposed_message_indexes(analysis))
    exposed_people = scanning_contacts(analysis)
    unknown_people = unknown_contacts(analysis)
    rows = _provider_rows(analysis)
    top_contacts = analysis.contacts[:top]
    return {
        "messages": total_messages,
        "contacts": total_contacts,
        "own_addresses": [display_address(address, address_mode) for address in analysis.own_addresses],
        "own_address_source": analysis.own_address_source,
        "address_display": address_mode,
        "bodies_read": False,
        "telemetry": False,
        "exposed": {
            "messages": exposed_messages,
            "messages_percent": percent(exposed_messages, total_messages),
            "contacts": len(exposed_people),
            "contacts_percent": percent(len(exposed_people), total_contacts),
        },
        "unknown_scanning": {
            "messages": sum(
                1
                for index in range(total_messages)
                if index not in set(exposed_message_indexes(analysis))
                and message_has_unknown(analysis, index)
            ),
            "contacts": len(unknown_people),
        },
        "by_provider": [_provider_dict(row) for row in rows],
        "top_contacts": [_contact_dict(contact, address_mode) for contact in top_contacts],
        "recommendations": _recommendations(analysis),
    }


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    def format_row(cells: list[str]) -> str:
        padded = [cell.ljust(widths[index]) for index, cell in enumerate(cells)]
        return "  ".join(padded).rstrip()

    lines = [format_row(headers), format_row(["-" * width for width in widths])]
    lines.extend(format_row(row) for row in rows)
    return "\n".join(lines)


def render_text(analysis: Analysis, *, address_mode: str, top: int) -> str:
    payload = report_dict(analysis, address_mode=address_mode, top=top)
    exposed = payload["exposed"]
    unknown = payload["unknown_scanning"]
    own = ", ".join(payload["own_addresses"]) if payload["own_addresses"] else "(none)"
    lines = [
        "chatcontrol-exposure",
        f"Messages: {payload['messages']}    Contacts: {payload['contacts']}",
        f"Own addresses ({payload['own_address_source']}): {own}",
        "",
        "Exposed to providers that document voluntary CSAM scanning",
        (
            f"  Messages: {exposed['messages']} ({exposed['messages_percent']}%)"
            f"    Contacts: {exposed['contacts']} ({exposed['contacts_percent']}%)"
        ),
        (
            "Unknown scanning status, not counted as exposed: "
            f"{unknown['messages']} messages, {unknown['contacts']} contacts"
        ),
        "",
        "Providers",
    ]
    provider_rows = []
    for row in payload["by_provider"]:
        provider_rows.append(
            [
                row["name"],
                str(row["jurisdiction"]["value"]),
                _claim_word(row["e2e_by_default"]["value"]),
                _claim_word(row["known_voluntary_scanning"]["value"]),
                str(row["contacts"]),
                str(row["messages"]),
            ]
        )
    if not provider_rows:
        lines.append("  (no correspondents)")
    else:
        lines.append(
            _table(
                ["Provider", "Jurisdiction", "E2E", "Scanning", "Contacts", "Messages"],
                provider_rows,
            )
        )
    lines.extend(["", "Top contacts"])
    contact_rows = []
    for contact in payload["top_contacts"]:
        contact_rows.append(
            [
                contact["address"],
                contact["provider"] or "",
                str(contact["sent"]),
                str(contact["received"]),
                str(contact["messages"]),
                _claim_word(contact["known_voluntary_scanning"]),
            ]
        )
    if not contact_rows:
        lines.append("  (none)")
    else:
        lines.append(
            _table(
                ["Address", "Provider", "Sent", "Received", "Messages", "Scanning"],
                contact_rows,
            )
        )
    lines.extend(["", "Recommendations"])
    for paragraph in payload["recommendations"]:
        lines.append(f"- {paragraph}")
    lines.append("")
    return "\n".join(lines)


def render_json(analysis: Analysis, *, address_mode: str, top: int) -> str:
    payload = report_dict(analysis, address_mode=address_mode, top=top)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_markdown(analysis: Analysis, *, address_mode: str, top: int) -> str:
    payload = report_dict(analysis, address_mode=address_mode, top=top)
    exposed = payload["exposed"]
    unknown = payload["unknown_scanning"]
    own = ", ".join(payload["own_addresses"]) if payload["own_addresses"] else "(none)"
    lines = [
        "# chatcontrol-exposure",
        "",
        f"- Messages: {payload['messages']}",
        f"- Contacts: {payload['contacts']}",
        f"- Own addresses ({payload['own_address_source']}): {own}",
        (
            f"- Exposed messages: {exposed['messages']} ({exposed['messages_percent']}%)"
        ),
        (
            f"- Exposed contacts: {exposed['contacts']} ({exposed['contacts_percent']}%)"
        ),
        (
            "- Unknown scanning status, not counted as exposed: "
            f"{unknown['messages']} messages, {unknown['contacts']} contacts"
        ),
        "",
        "## Providers",
        "",
        "| Provider | Jurisdiction | E2E by default | Voluntary scanning | Contacts | Messages |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["by_provider"]:
        lines.append(
            "| {name} | {jurisdiction} | {e2e} | {scanning} | {contacts} | {messages} |".format(
                name=_md(row["name"]),
                jurisdiction=_md(str(row["jurisdiction"]["value"])),
                e2e=_claim_word(row["e2e_by_default"]["value"]),
                scanning=_claim_word(row["known_voluntary_scanning"]["value"]),
                contacts=row["contacts"],
                messages=row["messages"],
            )
        )
    if not payload["by_provider"]:
        lines.append("| (none) | | | | | |")
    lines.extend(
        [
            "",
            "## Top contacts",
            "",
            "| Address | Provider | Sent | Received | Messages | Scanning |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for contact in payload["top_contacts"]:
        lines.append(
            "| {address} | {provider} | {sent} | {received} | {messages} | {scanning} |".format(
                address=_md(contact["address"]),
                provider=_md(contact["provider"] or ""),
                sent=contact["sent"],
                received=contact["received"],
                messages=contact["messages"],
                scanning=_claim_word(contact["known_voluntary_scanning"]),
            )
        )
    if not payload["top_contacts"]:
        lines.append("| (none) | | | | | |")
    lines.extend(["", "## Recommendations", ""])
    for paragraph in payload["recommendations"]:
        lines.append(f"- {paragraph}")
    lines.extend(["", "## Claim sources", ""])
    for row in payload["by_provider"]:
        lines.append(f"### {row['name']}")
        lines.append("")
        for label, key in (
            ("Jurisdiction", "jurisdiction"),
            ("E2E by default", "e2e_by_default"),
            ("Voluntary scanning", "known_voluntary_scanning"),
        ):
            claim = row[key]
            sources = ", ".join(claim["sources"]) if claim["sources"] else "(none)"
            lines.append(f"- {label}: {_claim_word(claim['value'])}. {claim['detail']} Sources: {sources}")
        if row["notes"]:
            lines.append(f"- Notes: {row['notes']}")
        lines.append("")
    return "\n".join(lines)


def _md(value: str) -> str:
    return value.replace("|", "\\|")
