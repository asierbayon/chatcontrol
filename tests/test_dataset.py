import json

import yaml

from chatcontrol_exposure.dataset import PROVIDERS_JSON, PROVIDERS_YAML, load_dataset


def test_yaml_and_json_datasets_match():
    yaml_raw = yaml.safe_load(PROVIDERS_YAML.read_text(encoding="utf-8"))
    json_raw = json.loads(PROVIDERS_JSON.read_text(encoding="utf-8"))
    assert json_raw == yaml_raw


def test_claims_are_sourced_and_scanning_bucket_is_limited():
    dataset = load_dataset()
    scanning = set()
    encrypted = set()
    for provider in dataset.providers:
        for field_name in ("jurisdiction", "e2e_by_default", "known_voluntary_scanning"):
            claim = getattr(provider, field_name)
            assert claim.detail
            if claim.value != "unknown":
                assert claim.sources
            for source in claim.sources:
                assert source.startswith("https://")
        if provider.known_voluntary_scanning.value is True:
            scanning.add(provider.id)
        if provider.e2e_by_default.value is True:
            encrypted.add(provider.id)
    assert scanning == {"google", "microsoft", "yahoo"}
    assert encrypted == {"proton", "tuta"}
    apple = next(provider for provider in dataset.providers if provider.id == "apple")
    assert apple.known_voluntary_scanning.value == "unknown"
    assert apple.e2e_by_default.value is False
    assert dataset.unknown.scans is False
    assert dataset.self_hosted.scans is False


def test_package_source_does_not_fetch_mail_or_phone_home():
    root = PROVIDERS_YAML.parents[1]
    banned = ("import urllib", "import requests", "import httpx", "BODY.PEEK[TEXT]", "RFC822")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} contains {token}"
