import hashlib
import json

from chatcontrol_exposure.analyze import prepare_analysis
from chatcontrol_exposure.dataset import load_dataset
from chatcontrol_exposure.mx import MxResolver
from chatcontrol_exposure.parse import load_mbox
from chatcontrol_exposure.privacy import display_address
from chatcontrol_exposure.report import render_json, render_markdown, render_text

from tests.conftest import FIXTURES


def _analysis(tmp_path, messages=None):
    dataset = load_dataset()
    resolver = MxResolver(offline=True, cache_path=tmp_path / "mx.json", lookup=lambda domain: [])
    loaded = messages if messages is not None else load_mbox(FIXTURES / "mixed.mbox")
    return prepare_analysis(loaded, own_addresses=None, dataset=dataset, resolver=resolver)


def test_mixed_mailbox_exposure_numbers(tmp_path):
    analysis = _analysis(tmp_path)
    assert analysis.own_addresses == ("alice@example.org",)
    assert analysis.own_address_source == "detected"
    payload = json.loads(render_json(analysis, address_mode="plain", top=15))
    assert payload["messages"] == 6
    assert payload["contacts"] == 9
    assert payload["exposed"]["messages"] == 4
    assert payload["exposed"]["messages_percent"] == 66.7
    assert payload["exposed"]["contacts"] == 3
    assert payload["exposed"]["contacts_percent"] == 33.3
    assert payload["unknown_scanning"]["contacts"] == 4
    assert payload["bodies_read"] is False
    assert payload["telemetry"] is False
    by_id = {row["id"]: row for row in payload["by_provider"]}
    assert by_id["google"]["exposed"] is True
    assert by_id["microsoft"]["exposed"] is True
    assert by_id["yahoo"]["exposed"] is True
    assert by_id["proton"]["known_voluntary_scanning"]["value"] is False
    assert by_id["apple"]["known_voluntary_scanning"]["value"] == "unknown"
    assert by_id["apple"]["exposed"] is False
    bob = next(contact for contact in payload["top_contacts"] if contact["address"] == "bob@gmail.com")
    assert bob["sent"] == 1
    assert bob["received"] == 1
    assert bob["exposed"] is True
    text = " ".join(payload["recommendations"])
    assert "not included in that share" in text
    assert "from 4 to 2" in text
    assert "BODYTOKEN" not in json.dumps(payload)


def test_redact_and_hash_hide_local_parts(tmp_path):
    analysis = _analysis(tmp_path)
    redacted = render_json(analysis, address_mode="redact", top=15)
    assert "bob@gmail.com" not in redacted
    assert "***@gmail.com" in redacted
    assert "***@example.org" in redacted
    hashed = json.loads(render_json(analysis, address_mode="hash", top=15))
    expected = hashlib.sha256(b"bob@gmail.com").hexdigest()[:12]
    addresses = [contact["address"] for contact in hashed["top_contacts"]]
    assert expected in addresses
    assert "bob@gmail.com" not in json.dumps(hashed)
    assert display_address("bob@gmail.com", "hash") == expected


def test_text_and_markdown_include_recommendations(tmp_path):
    analysis = _analysis(tmp_path)
    text = render_text(analysis, address_mode="plain", top=15)
    markdown = render_markdown(analysis, address_mode="plain", top=15)
    assert "Recommendations" in text
    assert "Google" in text
    assert "BODYTOKEN" not in text
    assert "## Recommendations" in markdown
    assert "https://support.google.com/mail/answer/10434152?hl=en" in markdown
    assert "not counted as exposed" in markdown


def test_flagged_own_address_overrides_detection(tmp_path):
    dataset = load_dataset()
    resolver = MxResolver(offline=True, cache_path=tmp_path / "mx.json")
    messages = load_mbox(FIXTURES / "mixed.mbox")
    analysis = prepare_analysis(
        messages,
        own_addresses=["bob@gmail.com"],
        dataset=dataset,
        resolver=resolver,
    )
    assert analysis.own_address_source == "flag"
    addresses = {contact.address for contact in analysis.contacts}
    assert "bob@gmail.com" not in addresses
    assert "alice@example.org" in addresses
