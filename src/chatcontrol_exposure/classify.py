from chatcontrol_exposure.dataset import Dataset
from chatcontrol_exposure.models import Provider


def hostname_matches(pattern: str, host: str) -> bool:
    """Match an MX hostname against a dataset pattern.

    A leading ``*.`` matches one or more labels. ``*.google.com`` matches
    ``smtp.google.com`` and ``alt1.gmail-smtp-in.l.google.com`` and does not
    match ``google.com`` itself.
    """

    normalized_pattern = pattern.lower().rstrip(".")
    normalized_host = host.lower().rstrip(".")
    if normalized_pattern.startswith("*."):
        suffix = normalized_pattern[1:]
        return normalized_host.endswith(suffix) and normalized_host != suffix[1:]
    return normalized_host == normalized_pattern


def match_provider(dataset: Dataset, host: str) -> Provider | None:
    best: Provider | None = None
    best_length = -1
    for provider in dataset.providers:
        for pattern in provider.mx_patterns:
            if not hostname_matches(pattern, host):
                continue
            pattern_length = len(pattern)
            if best is None or pattern_length > best_length or (
                pattern_length == best_length and provider.id < best.id
            ):
                best = provider
                best_length = pattern_length
    return best


def is_self_hosted(domain: str, hosts: list[str]) -> bool:
    if not hosts:
        return False
    normalized_domain = domain.lower().rstrip(".")
    for host in hosts:
        normalized_host = host.lower().rstrip(".")
        under_domain = normalized_host == normalized_domain or normalized_host.endswith(
            "." + normalized_domain
        )
        if not under_domain:
            return False
    return True


def classify_hosts(dataset: Dataset, domain: str, records: list[tuple[int, str]]) -> Provider:
    """Classify a domain from MX records.

    Records are ``(preference, hostname)`` pairs. They are tried best
    preference first. The first hostname that matches a provider wins, so a
    backup MX at a known provider still counts as that provider. If none
    match and every hostname is under ``domain``, the result is self-hosted.
    Otherwise it is unknown.
    """

    if not records:
        return dataset.unknown
    ordered = sorted(records, key=lambda item: (item[0], item[1]))
    for _preference, host in ordered:
        provider = match_provider(dataset, host)
        if provider is not None:
            return provider
    hosts = [host for _preference, host in ordered]
    if is_self_hosted(domain, hosts):
        return dataset.self_hosted
    return dataset.unknown
