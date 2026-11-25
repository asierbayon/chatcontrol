import json

import pytest

from chatcontrol_exposure.cli import main

from tests.conftest import FIXTURES


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    output = capsys.readouterr().out
    assert "--offline" in output
    assert "--imap" in output
    assert "--redact" in output
    assert "--hash-addresses" in output


def test_missing_input_fails(capsys):
    assert main([]) == 1
    assert "mbox" in capsys.readouterr().err.lower()


def test_cli_offline_json_matches_the_mixed_mailbox(capsys):
    code = main(
        [
            str(FIXTURES / "mixed.mbox"),
            "--offline",
            "--json",
            "--me",
            "alice@example.org",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exposed"]["messages"] == 4
    assert payload["own_address_source"] == "flag"
    assert "BODYTOKEN" not in json.dumps(payload)


def test_cli_redact_markdown(capsys):
    code = main([str(FIXTURES / "mixed.mbox"), "--offline", "--markdown", "--redact"])
    assert code == 0
    output = capsys.readouterr().out
    assert "***@gmail.com" in output
    assert "bob@gmail.com" not in output
    assert "## Recommendations" in output


def test_json_and_markdown_are_exclusive():
    with pytest.raises(SystemExit) as caught:
        main([str(FIXTURES / "mixed.mbox"), "--json", "--markdown"])
    assert caught.value.code == 2


def test_imap_password_comes_from_the_environment_and_is_not_printed(monkeypatch, capsys):
    captured = {}

    def fake_fetch(host, user, password, **kwargs):
        captured["host"] = host
        captured["user"] = user
        captured["password"] = password
        captured["mailboxes"] = kwargs["mailboxes"]
        return []

    monkeypatch.setattr("chatcontrol_exposure.cli.fetch_imap_headers", fake_fetch)
    monkeypatch.setenv("CHATCONTROL_IMAP_PASSWORD", "s3cret-value")
    code = main(
        ["--imap", "imap.example", "--imap-user", "alice", "--offline", "--json", "--me", "alice@example.org"]
    )
    assert code == 0
    assert captured == {
        "host": "imap.example",
        "user": "alice",
        "password": "s3cret-value",
        "mailboxes": None,
    }
    rendered = capsys.readouterr()
    assert "s3cret-value" not in rendered.out
    assert "s3cret-value" not in rendered.err
