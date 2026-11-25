from chatcontrol_exposure.identity import build_contacts, detect_own_addresses
from chatcontrol_exposure.parse import load_mbox

from tests.conftest import FIXTURES


def test_detects_owner_of_a_mixed_mailbox():
    messages = load_mbox(FIXTURES / "mixed.mbox")
    assert detect_own_addresses(messages) == ["alice@example.org"]


def test_detects_owner_of_inbox_only_and_sent_only():
    inbox = load_mbox(FIXTURES / "inbox_only.mbox")
    sent = load_mbox(FIXTURES / "sent_only.mbox")
    assert detect_own_addresses(inbox) == ["alice@example.org"]
    assert detect_own_addresses(sent) == ["alice@example.org"]


def test_tie_is_left_unresolved():
    messages = load_mbox(FIXTURES / "tie.mbox")
    assert detect_own_addresses(messages) == []


def test_sent_and_received_counts_skip_own_addresses():
    messages = load_mbox(FIXTURES / "mixed.mbox")
    _parties, sent_flags, contacts = build_contacts(messages, ["alice@example.org"])
    by_address = {contact.address: contact for contact in contacts}
    assert sent_flags == [True, False, False, True, True, False]
    assert by_address["bob@gmail.com"].sent == 1
    assert by_address["bob@gmail.com"].received == 1
    assert by_address["cara@proton.me"].sent == 1
    assert by_address["erin@posteo.de"].received == 1
    assert by_address["gina@tuta.com"].sent == 1
    assert by_address["judy@gmx.de"].received == 1
    assert "alice@example.org" not in by_address
    assert len(contacts) == 9
