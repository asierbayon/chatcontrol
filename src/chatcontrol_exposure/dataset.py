from pathlib import Path

import yaml

from chatcontrol_exposure.errors import ExposureError
from chatcontrol_exposure.models import Claim, Provider

DATA_DIR = Path(__file__).resolve().parent / "data"
PROVIDERS_YAML = DATA_DIR / "providers.yaml"
PROVIDERS_JSON = DATA_DIR / "providers.json"
MX_FALLBACK_JSON = DATA_DIR / "mx_fallback.json"

_REQUIRED_CLAIM_KEYS = ("value", "sources", "detail")


def _claim(raw: object, provider_id: str, field_name: str, *, text: bool = False) -> Claim:
    if not isinstance(raw, dict):
        raise ExposureError(f"{provider_id}.{field_name} must be a mapping")
    missing = [key for key in _REQUIRED_CLAIM_KEYS if key not in raw]
    if missing:
        joined = ", ".join(missing)
        raise ExposureError(f"{provider_id}.{field_name} is missing {joined}")
    value = raw["value"]
    if text:
        if not isinstance(value, str) or not value.strip():
            raise ExposureError(f"{provider_id}.{field_name} value must be text or unknown")
        value = value.strip()
    elif value not in (True, False, "unknown"):
        raise ExposureError(
            f"{provider_id}.{field_name} value must be true, false, or unknown"
        )
    sources_raw = raw["sources"]
    if not isinstance(sources_raw, list) or not all(isinstance(item, str) for item in sources_raw):
        raise ExposureError(f"{provider_id}.{field_name} sources must be a list of URLs")
    if value != "unknown" and not sources_raw:
        raise ExposureError(f"{provider_id}.{field_name} needs a source URL")
    for source in sources_raw:
        if not source.startswith("https://") and not source.startswith("http://"):
            raise ExposureError(f"{provider_id}.{field_name} has a non-URL source")
    detail = raw["detail"]
    if not isinstance(detail, str) or not detail.strip():
        raise ExposureError(f"{provider_id}.{field_name} needs a detail string")
    return Claim(value=value, sources=tuple(sources_raw), detail=detail.strip())


def _provider(raw: object) -> Provider:
    if not isinstance(raw, dict):
        raise ExposureError("Each provider entry must be a mapping")
    provider_id = raw.get("id")
    name = raw.get("name")
    patterns = raw.get("mx_patterns")
    if not isinstance(provider_id, str) or not provider_id:
        raise ExposureError("Provider id is missing")
    if not isinstance(name, str) or not name:
        raise ExposureError(f"{provider_id} is missing a name")
    if not isinstance(patterns, list) or not patterns or not all(isinstance(item, str) for item in patterns):
        raise ExposureError(f"{provider_id} needs mx_patterns")
    notes = raw.get("notes") or ""
    if not isinstance(notes, str):
        raise ExposureError(f"{provider_id} notes must be a string")
    return Provider(
        id=provider_id,
        name=name,
        mx_patterns=tuple(patterns),
        jurisdiction=_claim(raw.get("jurisdiction"), provider_id, "jurisdiction", text=True),
        e2e_by_default=_claim(raw.get("e2e_by_default"), provider_id, "e2e_by_default"),
        known_voluntary_scanning=_claim(
            raw.get("known_voluntary_scanning"),
            provider_id,
            "known_voluntary_scanning",
        ),
        notes=notes.strip(),
    )


def synthetic_provider(provider_id: str, name: str, detail: str) -> Provider:
    claim = Claim(value="unknown", sources=(), detail=detail)
    return Provider(
        id=provider_id,
        name=name,
        mx_patterns=(),
        jurisdiction=claim,
        e2e_by_default=claim,
        known_voluntary_scanning=claim,
    )


class Dataset:
    def __init__(self, providers: list[Provider]) -> None:
        self.providers = providers
        seen: set[str] = set()
        for provider in providers:
            if provider.id in seen:
                raise ExposureError(f"Duplicate provider id {provider.id}")
            seen.add(provider.id)
        self.unknown = synthetic_provider(
            "unknown",
            "Unknown",
            "No MX record was found, or the MX hostname matched no provider pattern. "
            "No scanning claim is made, and the contact is not counted as exposed.",
        )
        self.self_hosted = synthetic_provider(
            "self-hosted",
            "Self-hosted",
            "MX hostnames sit under the correspondent's own domain and matched no "
            "provider pattern. That is not evidence about scanning. Not counted as exposed.",
        )

    def by_id(self) -> dict[str, Provider]:
        found = {provider.id: provider for provider in self.providers}
        found[self.unknown.id] = self.unknown
        found[self.self_hosted.id] = self.self_hosted
        return found


def load_dataset(path: Path | None = None) -> Dataset:
    dataset_path = path or PROVIDERS_YAML
    try:
        raw = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExposureError(f"Could not read the provider dataset: {dataset_path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        raise ExposureError("Provider dataset must contain a providers list")
    providers = [_provider(item) for item in raw["providers"]]
    if not providers:
        raise ExposureError("Provider dataset is empty")
    return Dataset(providers)
