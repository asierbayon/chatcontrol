from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from chatcontrol_exposure.errors import ExposureError
from chatcontrol_exposure.models import HeaderMessage


def normalize_address(raw: str) -> str | None:
    text = raw.strip().lower()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    if "@" not in text:
        return None
    local, domain = text.rsplit("@", 1)
    local = local.strip()
    domain = domain.strip().rstrip(".")
    if not local or not domain:
        return None
    if any(char.isspace() or char in "<>(),;:\"[]" for char in local + domain):
        return None
    try:
        domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return f"{local}@{domain}"


def domain_of(address: str) -> str:
    return address.rsplit("@", 1)[1]


def _addresses(value: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for _name, raw in getaddresses([value]):
        address = normalize_address(raw)
        if address is None or address in seen:
            continue
        seen.add(address)
        found.append(address)
    return found


def _date_text(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    return parsed.isoformat()


def parse_header_block(raw: bytes) -> HeaderMessage:
    message = BytesParser(policy=default).parsebytes(raw)
    from_addresses = _addresses(str(message.get("from") or ""))
    recipients: list[str] = []
    seen: set[str] = set()
    for field in ("to", "cc", "bcc"):
        for address in _addresses(str(message.get(field) or "")):
            if address in seen:
                continue
            seen.add(address)
            recipients.append(address)
    return HeaderMessage(
        from_addr=from_addresses[0] if from_addresses else None,
        recipients=tuple(recipients),
        date=_date_text(str(message["date"]) if message["date"] is not None else None),
    )


def iter_mbox_headers(path: Path):
    """Yield header records from an mbox file.

    The reader keeps header lines only. Body lines are scanned so the next
    message can be found, and they are not stored.
    """

    try:
        handle = path.open("rb")
    except OSError as exc:
        raise ExposureError(f"Could not read mbox file: {path}") from exc
    with handle:
        header_lines: list[bytes] = []
        in_headers = False
        started = False
        for line in handle:
            if line.startswith(b"From "):
                if started and header_lines:
                    yield parse_header_block(b"".join(header_lines))
                header_lines = []
                in_headers = True
                started = True
                continue
            if not in_headers:
                continue
            if line in (b"\n", b"\r\n"):
                in_headers = False
                continue
            header_lines.append(line)
        if header_lines:
            yield parse_header_block(b"".join(header_lines))


def load_mbox(path: Path) -> list[HeaderMessage]:
    return list(iter_mbox_headers(path))
