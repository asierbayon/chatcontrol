import argparse
import os
import sys
from pathlib import Path

from chatcontrol_exposure import __version__
from chatcontrol_exposure.analyze import prepare_analysis
from chatcontrol_exposure.dataset import load_dataset
from chatcontrol_exposure.errors import ExposureError
from chatcontrol_exposure.identity import normalize_own_addresses
from chatcontrol_exposure.imap_source import fetch_imap_headers
from chatcontrol_exposure.mx import MxResolver
from chatcontrol_exposure.parse import load_mbox
from chatcontrol_exposure.report import render_json, render_markdown, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatcontrol-exposure",
        description=(
            "Report how much of a mailbox's correspondence is addressed to "
            "providers that document voluntary CSAM scanning. Only From, To, "
            "Cc, Bcc, and Date are read. Message bodies are not stored. "
            "The only network use is DNS MX lookup, and --offline skips that."
        ),
    )
    parser.add_argument("mbox", nargs="?", help="Path to an mbox file")
    parser.add_argument("--imap", metavar="HOST", help="Read headers from this IMAP host")
    parser.add_argument("--imap-user", help="IMAP username. Defaults to CHATCONTROL_IMAP_USER.")
    parser.add_argument(
        "--imap-password",
        help="IMAP password. Prefer CHATCONTROL_IMAP_PASSWORD so it stays out of the shell history.",
    )
    parser.add_argument("--imap-port", type=int, default=993, help="IMAPS port (default: 993)")
    parser.add_argument(
        "--imap-mailbox",
        action="append",
        dest="imap_mailboxes",
        help="Mailbox to open read-only. Repeat for more than one. Default: INBOX",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not query DNS. Use the on-disk MX cache and the bundled fallback map.",
    )
    parser.add_argument("--cache", type=Path, help="MX cache file. Default: XDG cache directory")
    parser.add_argument("--me", action="append", dest="me", help="One of your own addresses. Repeatable.")
    parser.add_argument("--top", type=int, default=15, help="How many contacts to list (default: 15)")
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument("--json", action="store_true", help="Write a JSON report to stdout")
    format_group.add_argument("--markdown", action="store_true", help="Write a Markdown report to stdout")
    privacy_group = parser.add_mutually_exclusive_group()
    privacy_group.add_argument(
        "--redact",
        action="store_true",
        help="Replace the local part of every address with *** and keep the domain",
    )
    privacy_group.add_argument(
        "--hash-addresses",
        action="store_true",
        help="Replace each address with the first 12 hex characters of its SHA-256",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _address_mode(args: argparse.Namespace) -> str:
    if args.hash_addresses:
        return "hash"
    if args.redact:
        return "redact"
    return "plain"


def _load_messages(args: argparse.Namespace):
    messages = []
    if args.mbox:
        messages.extend(load_mbox(Path(args.mbox)))
    if args.imap:
        user = args.imap_user or os.environ.get("CHATCONTROL_IMAP_USER")
        password = args.imap_password
        if password is None:
            password = os.environ.get("CHATCONTROL_IMAP_PASSWORD")
        if not user:
            raise ExposureError("IMAP needs --imap-user or CHATCONTROL_IMAP_USER.")
        if not password:
            raise ExposureError("IMAP needs --imap-password or CHATCONTROL_IMAP_PASSWORD.")
        messages.extend(
            fetch_imap_headers(
                args.imap,
                user,
                password,
                port=args.imap_port,
                mailboxes=args.imap_mailboxes,
            )
        )
    if not args.mbox and not args.imap:
        raise ExposureError("Pass an mbox file, --imap, or both.")
    return messages


def run(args: argparse.Namespace) -> int:
    if args.top < 0:
        raise ExposureError("--top must be zero or greater.")
    messages = _load_messages(args)
    own = None
    if args.me:
        own = normalize_own_addresses(args.me)
        if not own:
            raise ExposureError("--me needs at least one valid email address.")
    dataset = load_dataset()
    resolver = MxResolver(offline=args.offline, cache_path=args.cache)
    analysis = prepare_analysis(
        messages,
        own_addresses=own,
        dataset=dataset,
        resolver=resolver,
    )
    mode = _address_mode(args)
    if args.json:
        text = render_json(analysis, address_mode=mode, top=args.top)
    elif args.markdown:
        text = render_markdown(analysis, address_mode=mode, top=args.top)
    else:
        text = render_text(analysis, address_mode=mode, top=args.top)
    sys.stdout.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except ExposureError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
