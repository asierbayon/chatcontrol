import hashlib


def display_address(address: str, mode: str) -> str:
    if mode == "plain":
        return address
    if mode == "redact":
        _local, domain = address.split("@", 1)
        return f"***@{domain}"
    if mode == "hash":
        digest = hashlib.sha256(address.encode("utf-8")).hexdigest()
        return digest[:12]
    raise ValueError(f"Unknown address display mode: {mode}")
