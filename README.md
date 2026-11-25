# chatcontrol-exposure

A local, offline-first command line tool that shows how much of a person's real email correspondence is addressed to providers that document voluntary scanning for child sexual abuse material.

It reads **only** `From`, `To`, `Cc`, `Bcc`, and `Date`. It does not read or store message bodies. It sends nothing off the machine except DNS MX lookups, and `--offline` skips those too. There is no telemetry.

## Why this exists

[Regulation (EU) 2026/1881](https://eur-lex.europa.eu/eli/reg/2026/1881/oj/eng) is a temporary, voluntary derogation from the confidentiality rules in the ePrivacy Directive. It applies until **3 April 2028**. It lets providers of number-independent interpersonal communications, including webmail, choose to scan for child sexual abuse material. It does not require them to, and it does not apply to communications that are end-to-end encrypted. The earlier instrument, Regulation (EU) 2021/1232, had expired on 3 April 2026. Background written for a general audience: [exitchatcontrol.org](https://exitchatcontrol.org/).

The derogation is not proof that any particular provider scans. This tool counts a correspondent as exposed only when that provider's own documentation says it does. Everyone else stays in a separate unknown bucket.

Mail to a Gmail or Outlook address is processed by that provider even if you send it from Proton or Tuta. Those services encrypt mail between their own users. They cannot encrypt a message a scanning provider receives in the clear.

## Install

Python 3.11 or newer.

```bash
pipx install .
chatcontrol-exposure --help
```

From a checkout, for development:

```bash
pip install -e ".[dev]"
pytest
```

## Usage

mbox file, offline, table on the terminal:

```bash
chatcontrol-exposure archive.mbox --offline
```

Your own addresses, if the mailbox does not make them obvious:

```bash
chatcontrol-exposure archive.mbox --offline --me you@example.org --me you@work.example
```

JSON or Markdown:

```bash
chatcontrol-exposure archive.mbox --offline --json
chatcontrol-exposure archive.mbox --offline --markdown
```

Hide addresses. `--redact` keeps the domain (`***@gmail.com`). `--hash-addresses` prints the first 12 hex characters of SHA-256 of the full address. The hash is unsalted, so the same address always looks the same, and a guessable address can be checked against it. The two flags cannot be combined.

```bash
chatcontrol-exposure archive.mbox --offline --redact
chatcontrol-exposure archive.mbox --offline --hash-addresses
```

### IMAP

Read-only IMAPS. The tool sends `BODY.PEEK[HEADER.FIELDS (FROM TO CC BCC DATE)]`, which does not set the seen flag and does not request the body. Put the password in the environment so it does not land in your shell history. It is not written to the report.

```bash
export CHATCONTROL_IMAP_USER='you@example.org'
export CHATCONTROL_IMAP_PASSWORD='…'
chatcontrol-exposure --imap imap.example.org --imap-mailbox INBOX --imap-mailbox Sent --offline
```

`--imap-password` exists for scripts. Prefer the environment variable. Sent mail is often a separate mailbox; pass it if you want outgoing correspondence included. You can pass an mbox file and `--imap` together. The messages are merged.

### Offline mode

MX hostnames are cached for 14 days under `${XDG_CACHE_HOME:-~/.cache}/chatcontrol-exposure/mx-cache.json`. The cache stores domains and mail-exchanger hostnames, not addresses.

`--offline` does not query DNS. It uses that cache, then the bundled map in `src/chatcontrol_exposure/data/mx_fallback.json`. A domain in neither place is reported as unknown, not as exposed. `--cache` points at a different cache file.

## How a message is counted

The tool guesses your addresses when one address appears on at least half of the messages and no other address ties it. An inbox-only export and a sent-mail export both work if there are at least three messages. A tie is left unresolved. Pass `--me` whenever you have more than one address, or when the guess is wrong. `--me` replaces the guess.

Someone you sent mail to is counted as sent. On mail you did not send, the sender and the other recipients are counted as received. Your own addresses are not contacts.

A **contact** is exposed when their provider's `known_voluntary_scanning` value is `true`. A **message** is exposed when at least one correspondent on it is. Unknown and self-hosted providers are reported separately and are not counted as exposed. A backup MX at a known provider counts as that provider, because mail can be delivered there.

The recommendation section uses those counts: the share of messages and contacts at providers that document voluntary scanning, which providers make up that volume, and how the exposed-message count would change if the single highest-volume contact in that group moved to a provider that does not document voluntary scanning.

## Dataset

Canonical file: `src/chatcontrol_exposure/data/providers.yaml`. `providers.json` is the same document in JSON. Tests fail if they drift.

Each provider has:

| Field | Meaning |
| --- | --- |
| `id`, `name` | Stable id and label used in reports |
| `mx_patterns` | Host patterns. `*.google.com` matches one or more labels, so `smtp.google.com` matches and `google.com` does not |
| `jurisdiction` | Where the provider says it is established |
| `e2e_by_default` | Whether mail between that provider's own users is end-to-end encrypted without an extra step |
| `known_voluntary_scanning` | Whether the provider's own pages say it voluntarily scans communications for CSAM |
| `notes` | Classification notes. Not a counted claim |

Each of the three claims is an object:

```yaml
known_voluntary_scanning:
  value: true          # true, false, or "unknown"
  sources:
    - "https://example.com/the-page-you-fetched"
  detail: >
    Short quotation or paraphrase of what that page actually says.
```

`true` or `false` requires at least one `http` or `https` source. `unknown` means the fetched pages did not establish the claim. Do not fill unknown from the fact that the EU derogation exists, from a news article about a different product, or from a guess.

Snapshot checked on 2026-11-25:

| Provider | Jurisdiction | E2E by default | Voluntary scanning |
| --- | --- | --- | --- |
| Google | United States | no | yes |
| Microsoft | United States | no | yes |
| Yahoo | United States | no | yes |
| Apple (iCloud Mail) | United States | no | unknown |
| GMX / WEB.DE (and mail.com MX) | Germany | no | unknown |
| Proton | Switzerland | yes, between Proton users | no |
| Tuta | Germany | yes, between Tuta users | no |
| Fastmail | Australia | no | unknown |
| mailbox.org | Germany | no | unknown |
| Posteo | Germany | no | unknown |

Apple's privacy policy mentions scanning uploaded content for child sexual exploitation material and does not say that includes iCloud Mail, so scanning stays unknown. GMX documents virus scanning, not CSAM scanning. Fastmail, mailbox.org, and Posteo document spam or malware filtering and do not state a CSAM scanning practice. Proton and Tuta state that they cannot read stored mail; mail they hand off to another provider is still counted on that provider.

Self-hosted means every MX hostname is under the correspondent's own domain and none matched a pattern. That is not a claim about scanning.

## Contributing a provider

1. Fetch the provider's own page for each claim you want to set to `true` or `false`. Legal notice or terms for jurisdiction, a security page for encryption, a transparency report or product help page for scanning.
2. Add an entry to `providers.yaml`. If you cannot verify a field, set it to `"unknown"`.
3. Add `mx_patterns` that match the provider's mail exchangers, and add an example domain to `mx_fallback.json` so `--offline` can classify it. Patterns are matched against MX hostnames, not against the email domain.
4. Regenerate the JSON copy:

   ```bash
   python -c 'import json,yaml,pathlib; p=pathlib.Path("src/chatcontrol_exposure/data/providers.yaml"); pathlib.Path("src/chatcontrol_exposure/data/providers.json").write_text(json.dumps(yaml.safe_load(p.read_text()), indent=2, ensure_ascii=False)+"\n")'
   ```

5. Add or adjust a classification test if the new pattern could collide with an existing one.
6. Run `pytest`.

## Privacy

- Bodies, subjects, and attachments are not parsed into the report.
- The mbox reader keeps header lines and discards the rest.
- IMAP is read-only and limited to five header fields.
- DNS queries, when enabled, are for the correspondent's domain only.
- Reports go to stdout. Redact or hash them before you share them.
- The MX cache on disk lists domains you looked up.

## Limitations

- Header delivery is not the same thing as a scan of a particular message. The report counts where mail was addressed.
- Own-address detection fails on ties and on mailboxes smaller than three messages. Use `--me`.
- Bcc is usually absent from mail you received.
- An MX hostname can be a gateway in front of a different host. Backup MX records count as that provider.
- The dataset is a snapshot of public pages. It is not legal advice, and it will go stale.
- `--offline` only knows domains in the cache or the bundled map.
- The address hash is unsalted and truncated. It hides addresses from a casual reading, not from someone who can guess them.

## Development

```bash
pip install -e ".[dev]"
pytest
```

GitHub Actions runs pytest on Python 3.11 and 3.12.

## License

MIT. See [LICENSE](LICENSE).
