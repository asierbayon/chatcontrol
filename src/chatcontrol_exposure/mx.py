import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dns.exception
import dns.resolver

from chatcontrol_exposure.dataset import MX_FALLBACK_JSON
from chatcontrol_exposure.errors import ExposureError

CACHE_TTL = timedelta(days=14)


def default_cache_path() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "chatcontrol-exposure" / "mx-cache.json"


def dns_lookup(domain: str, timeout: float = 5.0) -> list[tuple[int, str]]:
    """Resolve MX hostnames for a domain. The local-part is never queried."""

    resolver = dns.resolver.Resolver()
    resolver.lifetime = timeout
    try:
        answer = resolver.resolve(domain, "MX")
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.exception.Timeout,
        dns.exception.DNSException,
    ):
        return []
    records: list[tuple[int, str]] = []
    for item in answer:
        host = str(item.exchange).rstrip(".").lower()
        if not host:
            continue
        records.append((int(item.preference), host))
    records.sort()
    return records


def load_fallback(path: Path | None = None) -> dict[str, list[tuple[int, str]]]:
    fallback_path = path or MX_FALLBACK_JSON
    try:
        raw = json.loads(fallback_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExposureError(f"Could not read the MX fallback map: {fallback_path}") from exc
    domains = raw.get("domains") if isinstance(raw, dict) else None
    if not isinstance(domains, dict):
        raise ExposureError("MX fallback map is missing domains")
    parsed: dict[str, list[tuple[int, str]]] = {}
    for domain, hosts in domains.items():
        if not isinstance(domain, str) or not isinstance(hosts, list):
            continue
        records = []
        for host in hosts:
            if isinstance(host, str) and host.strip():
                records.append((10, host.strip().lower().rstrip(".")))
        parsed[domain.lower()] = records
    return parsed


class MxResolver:
    """Resolve MX hostnames with an on-disk cache and a bundled fallback.

    ``--offline`` never opens a DNS socket. It reads the cache, then the
    bundled map. Online lookups query the domain only.
    """

    def __init__(
        self,
        *,
        offline: bool = False,
        cache_path: Path | None = None,
        lookup=None,
        fallback: dict[str, list[tuple[int, str]]] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.offline = offline
        self.cache_path = cache_path if cache_path is not None else default_cache_path()
        self._lookup = lookup if lookup is not None else dns_lookup
        self._fallback = fallback if fallback is not None else load_fallback()
        self._now = now or datetime.now(timezone.utc)
        self._cache = self._read_cache()

    def resolve(self, domain: str) -> list[tuple[int, str]]:
        key = domain.lower().rstrip(".")
        cached = self._cache.get(key)
        if cached is not None and (self.offline or not self._expired(cached["fetched_at"])):
            return list(cached["records"])
        if self.offline:
            return list(self._fallback.get(key, []))
        records = self._lookup(key)
        if records:
            self._store(key, records)
            return records
        if cached is not None:
            return list(cached["records"])
        return list(self._fallback.get(key, []))

    def _expired(self, fetched_at: str) -> bool:
        try:
            stamp = datetime.fromisoformat(fetched_at)
        except ValueError:
            return True
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return self._now - stamp > CACHE_TTL

    def _read_cache(self) -> dict:
        if not self.cache_path.is_file():
            return {}
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, dict):
            return {}
        parsed = {}
        for domain, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            hosts = entry.get("mx")
            fetched_at = entry.get("fetched_at")
            if not isinstance(hosts, list) or not isinstance(fetched_at, str):
                continue
            records = []
            for item in hosts:
                if not isinstance(item, dict):
                    continue
                host = item.get("host")
                preference = item.get("preference")
                if isinstance(host, str) and isinstance(preference, int):
                    records.append((preference, host.lower().rstrip(".")))
            parsed[domain.lower()] = {"fetched_at": fetched_at, "records": records}
        return parsed

    def _store(self, domain: str, records: list[tuple[int, str]]) -> None:
        self._cache[domain] = {
            "fetched_at": self._now.isoformat(),
            "records": records,
        }
        payload = {
            "version": 1,
            "entries": {
                key: {
                    "fetched_at": value["fetched_at"],
                    "mx": [
                        {"preference": preference, "host": host}
                        for preference, host in value["records"]
                    ],
                }
                for key, value in sorted(self._cache.items())
            },
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
