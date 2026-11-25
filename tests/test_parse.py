from email.utils import parsedate_to_datetime

from chatcontrol_exposure.parse import load_mbox, normalize_address, parse_header_block

from tests.conftest import FIXTURES


def test_normalize_address_lowercases_and_strips_display_noise():
    assert normalize_address("  Alice <Alice@Example.ORG>  ") is None
    assert normalize_address("Alice@Example.ORG") == "alice@example.org"


def test_folded_headers_and_bcc_are_kept_without_the_body():
    raw = (
        b"From: Alice <alice@example.org>\n"
        b"To: bob@gmail.com,\n"
        b" cara@proton.me\n"
        b"Bcc: Gina <gina@tuta.com>\n"
        b"Date: Tue, 24 Nov 2026 10:00:00 +0000\n"
        b"\n"
        b"BODYTOKEN-do-not-leak\n"
    )
    message = parse_header_block(raw)
    assert message.from_addr == "alice@example.org"
    assert message.recipients == ("bob@gmail.com", "cara@proton.me", "gina@tuta.com")
    assert message.date == parsedate_to_datetime("Tue, 24 Nov 2026 10:00:00 +0000").isoformat()
    assert "BODYTOKEN" not in repr(message)


def test_mbox_loader_reads_six_headers_and_drops_bodies(mixed_mbox):
    messages = load_mbox(mixed_mbox)
    assert len(messages) == 6
    assert messages[0].recipients[:2] == ("bob@gmail.com", "cara@proton.me")
    assert messages[3].recipients == ("frank@fastmail.com", "gina@tuta.com")
    blob = "\n".join(repr(message) for message in messages)
    assert "BODYTOKEN" not in blob
    assert "do-not-leak" not in blob


def test_inbox_and_sent_fixtures_load():
    assert len(load_mbox(FIXTURES / "inbox_only.mbox")) == 3
    assert len(load_mbox(FIXTURES / "sent_only.mbox")) == 3
    assert len(load_mbox(FIXTURES / "tie.mbox")) == 4
