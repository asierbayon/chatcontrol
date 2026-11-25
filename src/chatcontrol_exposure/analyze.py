from chatcontrol_exposure.classify import classify_hosts
from chatcontrol_exposure.dataset import Dataset
from chatcontrol_exposure.identity import build_contacts, detect_own_addresses
from chatcontrol_exposure.models import Analysis, ContactStats, HeaderMessage, Provider
from chatcontrol_exposure.mx import MxResolver
from chatcontrol_exposure.parse import domain_of


def prepare_analysis(
    messages: list[HeaderMessage],
    *,
    own_addresses: list[str] | None,
    dataset: Dataset,
    resolver: MxResolver,
) -> Analysis:
    if own_addresses is None:
        detected = detect_own_addresses(messages)
        source = "detected" if detected else "undetected"
        own = detected
    else:
        source = "flag"
        own = list(own_addresses)
    message_contacts, message_sent, contacts = build_contacts(messages, own)
    domains: dict[str, tuple[Provider, tuple[str, ...]]] = {}
    for contact in contacts:
        domain = domain_of(contact.address)
        if domain not in domains:
            records = resolver.resolve(domain)
            provider = classify_hosts(dataset, domain, records)
            hosts = tuple(host for _preference, host in records)
            domains[domain] = (provider, hosts)
        provider, hosts = domains[domain]
        contact.provider = provider
        contact.mx_hosts = hosts
    return Analysis(
        own_addresses=tuple(own),
        own_address_source=source,
        messages=messages,
        message_contacts=message_contacts,
        message_sent=message_sent,
        contacts=contacts,
    )


def _provider(contact: ContactStats) -> Provider:
    if contact.provider is None:
        raise RuntimeError(f"Contact {contact.address} has no provider")
    return contact.provider


def exposed_message_indexes(analysis: Analysis, skip_address: str | None = None) -> list[int]:
    indexes: list[int] = []
    for index, parties in enumerate(analysis.message_contacts):
        for address in parties:
            if address == skip_address:
                continue
            contact = _contact_map(analysis)[address]
            if _provider(contact).scans:
                indexes.append(index)
                break
    return indexes


def _contact_map(analysis: Analysis) -> dict[str, ContactStats]:
    return {contact.address: contact for contact in analysis.contacts}


def scanning_contacts(analysis: Analysis) -> list[ContactStats]:
    return [contact for contact in analysis.contacts if _provider(contact).scans]


def unknown_contacts(analysis: Analysis) -> list[ContactStats]:
    return [
        contact
        for contact in analysis.contacts
        if _provider(contact).known_voluntary_scanning.value == "unknown"
    ]


def message_has_unknown(analysis: Analysis, index: int) -> bool:
    contacts = _contact_map(analysis)
    for address in analysis.message_contacts[index]:
        if _provider(contacts[address]).known_voluntary_scanning.value == "unknown":
            return True
    return False
