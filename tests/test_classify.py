from datetime import datetime, timezone

import pytest

from chatcontrol_exposure.classify import classify_hosts, hostname_matches, match_provider
from chatcontrol_exposure.dataset import load_dataset
from chatcontrol_exposure.mx import MxResolver


@pytest.fixture(scope="module")
def dataset():
    return load_dataset()


@pytest.mark.parametrize(
    ("host", "provider_id"),
    [
        ("gmail-smtp-in.l.google.com", "google"),
        ("smtp.google.com", "google"),
        ("alt1.aspmx.l.google.com", "google"),
        ("outlook-com.olc.protection.outlook.com", "microsoft"),
        ("example-com.mail.protection.outlook.com", "microsoft"),
        ("mta5.am0.yahoodns.net", "yahoo"),
        ("mx-aol.mail.gm0.yahoodns.net", "yahoo"),
        ("mx01.mail.icloud.com", "apple"),
        ("mx00.emig.gmx.net", "gmx"),
        ("mx-ha02.web.de", "gmx"),
        ("mx00.mail.com", "gmx"),
        ("mail.protonmail.ch", "proton"),
        ("mailsec.protonmail.ch", "proton"),
        ("mail.tutanota.de", "tuta"),
        ("in1-smtp.messagingengine.com", "fastmail"),
        ("mx1.mailbox.org", "mailboxorg"),
        ("mx01.posteo.de", "posteo"),
    ],
)
def test_mx_patterns(dataset, host, provider_id):
    provider = match_provider(dataset, host)
    assert provider is not None
    assert provider.id == provider_id


def test_pattern_does_not_match_the_apex():
    assert hostname_matches("*.google.com", "smtp.google.com")
    assert not hostname_matches("*.google.com", "google.com")
    assert not hostname_matches("*.mail.com", "gmail.com")


def test_backup_provider_mx_counts_as_that_provider(dataset):
    provider = classify_hosts(
        dataset,
        "example.org",
        [(10, "mail.example.org"), (20, "gmail-smtp-in.l.google.com")],
    )
    assert provider.id == "google"


def test_better_preference_provider_wins(dataset):
    provider = classify_hosts(
        dataset,
        "example.org",
        [(10, "smtp.google.com"), (20, "outlook-com.olc.protection.outlook.com")],
    )
    assert provider.id == "google"


def test_later_record_can_still_match_a_provider(dataset):
    provider = classify_hosts(
        dataset,
        "example.org",
        [(10, "mx.unknown-provider.test"), (20, "smtp.google.com")],
    )
    assert provider.id == "google"


def test_self_hosted_and_unknown(dataset):
    hosted = classify_hosts(dataset, "example.org", [(10, "mail.example.org")])
    unknown = classify_hosts(dataset, "example.org", [(10, "mx.unknown-provider.test")])
    empty = classify_hosts(dataset, "example.org", [])
    assert hosted.id == "self-hosted"
    assert unknown.id == "unknown"
    assert empty.id == "unknown"
    assert hosted.scans is False
    assert unknown.scans is False


def test_offline_resolver_uses_fallback_and_does_not_query_dns(dataset, tmp_path):
    def explode(domain: str):
        raise AssertionError(f"DNS lookup attempted for {domain}")

    resolver = MxResolver(
        offline=True,
        cache_path=tmp_path / "mx.json",
        lookup=explode,
    )
    gmail = resolver.resolve("gmail.com")
    assert any(host.endswith(".google.com") for _preference, host in gmail)
    assert classify_hosts(dataset, "gmail.com", gmail).id == "google"
    assert resolver.resolve("nosuch.invalid") == []
    outlook = resolver.resolve("outlook.com")
    assert classify_hosts(dataset, "outlook.com", outlook).id == "microsoft"


def test_online_cache_stores_domains_only(tmp_path):
    calls = []

    def lookup(domain: str):
        calls.append(domain)
        return [(10, "smtp.google.com")]

    cache_path = tmp_path / "cache" / "mx.json"
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    resolver = MxResolver(offline=False, cache_path=cache_path, lookup=lookup, now=now, fallback={})
    assert resolver.resolve("Example.COM")[0][1] == "smtp.google.com"
    assert calls == ["example.com"]
    text = cache_path.read_text(encoding="utf-8")
    assert "example.com" in text
    assert "@" not in text
    cached = MxResolver(offline=True, cache_path=cache_path, lookup=lookup, now=now, fallback={})
    assert cached.resolve("example.com")[0][1] == "smtp.google.com"
    assert calls == ["example.com"]
