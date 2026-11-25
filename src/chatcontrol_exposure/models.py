from dataclasses import dataclass, field


@dataclass(frozen=True)
class Claim:
    value: bool | str
    sources: tuple[str, ...]
    detail: str

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "sources": list(self.sources),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    mx_patterns: tuple[str, ...]
    jurisdiction: Claim
    e2e_by_default: Claim
    known_voluntary_scanning: Claim
    notes: str = ""

    @property
    def scans(self) -> bool:
        return self.known_voluntary_scanning.value is True


@dataclass(frozen=True)
class HeaderMessage:
    """Headers from one message. Bodies are never stored."""

    from_addr: str | None
    recipients: tuple[str, ...]
    date: str | None


@dataclass
class ContactStats:
    address: str
    sent: int = 0
    received: int = 0
    provider: Provider | None = None
    mx_hosts: tuple[str, ...] = ()

    @property
    def messages(self) -> int:
        return self.sent + self.received


@dataclass
class Analysis:
    own_addresses: tuple[str, ...]
    own_address_source: str
    messages: list[HeaderMessage]
    message_contacts: list[tuple[str, ...]]
    message_sent: list[bool]
    contacts: list[ContactStats] = field(default_factory=list)
