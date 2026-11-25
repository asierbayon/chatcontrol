import imaplib

import pytest

from chatcontrol_exposure.errors import ExposureError
from chatcontrol_exposure.imap_source import HEADER_QUERY, fetch_imap_headers


class FakeImap:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.readonly = None
        self.mailbox = None
        self.queries = []
        self.logged_out = False

    def login(self, user, password):
        self.user = user
        self.password = password

    def select(self, mailbox, readonly=False):
        self.mailbox = mailbox
        self.readonly = readonly
        return "OK", [b"1"]

    def search(self, charset, criteria):
        return "OK", [b"1"]

    def fetch(self, message_id, query):
        self.queries.append(query)
        header = b"From: Bob <bob@gmail.com>\r\nTo: alice@example.org\r\n\r\n"
        descriptor = b"1 (BODY[HEADER.FIELDS (FROM TO CC BCC DATE)] {48}"
        return "OK", [(descriptor, header), b")"]

    def logout(self):
        self.logged_out = True


def test_imap_fetch_is_header_only_and_read_only():
    client = {}

    def factory(host, port):
        client["imap"] = FakeImap(host, port)
        return client["imap"]

    messages = fetch_imap_headers(
        "imap.example",
        "alice",
        "s3cret",
        mailboxes=["INBOX"],
        client_factory=factory,
    )
    imap = client["imap"]
    assert imap.readonly is True
    assert imap.mailbox == "INBOX"
    assert imap.queries == [HEADER_QUERY]
    assert imap.logged_out is True
    assert "BODY[]" not in HEADER_QUERY
    assert "PEEK" in HEADER_QUERY
    assert messages[0].from_addr == "bob@gmail.com"
    assert messages[0].recipients == ("alice@example.org",)
    assert "s3cret" not in repr(messages)


def test_imap_login_failure_does_not_repeat_the_server_text():
    def factory(host, port):
        class Broken(FakeImap):
            def login(self, user, password):
                raise imaplib.IMAP4.error(b"authentication failed for s3cret")

        return Broken(host, port)

    with pytest.raises(ExposureError) as caught:
        fetch_imap_headers("imap.example", "alice", "s3cret", client_factory=factory)
    assert str(caught.value) == "IMAP login failed."
    assert caught.value.__cause__ is None
    assert "s3cret" not in str(caught.value)
