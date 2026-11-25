import imaplib

from chatcontrol_exposure.errors import ExposureError
from chatcontrol_exposure.models import HeaderMessage
from chatcontrol_exposure.parse import parse_header_block

HEADER_QUERY = "(BODY.PEEK[HEADER.FIELDS (FROM TO CC BCC DATE)])"


def header_blobs(fetched: object) -> list[bytes]:
    blobs: list[bytes] = []
    if not isinstance(fetched, (list, tuple)):
        return blobs
    for part in fetched:
        if not isinstance(part, tuple):
            continue
        for piece in part:
            if not isinstance(piece, (bytes, bytearray)):
                continue
            if b"\n" not in piece and b"\r" not in piece:
                continue
            blobs.append(bytes(piece))
    return blobs


def fetch_imap_headers(
    host: str,
    user: str,
    password: str,
    *,
    port: int = 993,
    mailboxes: list[str] | None = None,
    client_factory=None,
) -> list[HeaderMessage]:
    """Read From, To, Cc, Bcc, and Date over IMAP. The mailbox is read-only.

    BODY.PEEK does not set the seen flag. The message body is not requested.
    """

    selected = mailboxes or ["INBOX"]
    factory = client_factory or imaplib.IMAP4_SSL
    try:
        client = factory(host, port)
    except OSError as exc:
        raise ExposureError(f"Could not connect to IMAP host {host}.") from exc
    try:
        try:
            client.login(user, password)
        except imaplib.IMAP4.error:
            raise ExposureError("IMAP login failed.") from None
        messages: list[HeaderMessage] = []
        for mailbox in selected:
            try:
                status, _data = client.select(mailbox, readonly=True)
            except imaplib.IMAP4.error:
                raise ExposureError(f"Could not open mailbox {mailbox} read-only.") from None
            if status != "OK":
                raise ExposureError(f"Could not open mailbox {mailbox} read-only.")
            try:
                status, data = client.search(None, "ALL")
            except imaplib.IMAP4.error:
                raise ExposureError(f"Could not list messages in {mailbox}.") from None
            if status != "OK" or not data or not data[0]:
                continue
            for message_id in data[0].split():
                try:
                    status, fetched = client.fetch(message_id, HEADER_QUERY)
                except imaplib.IMAP4.error:
                    raise ExposureError("Could not fetch message headers.") from None
                if status != "OK":
                    continue
                for blob in header_blobs(fetched):
                    messages.append(parse_header_block(blob))
        return messages
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
