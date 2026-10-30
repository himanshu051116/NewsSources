from __future__ import annotations

from urllib.parse import urlsplit

AUTHORITY_MATCHER_VERSION = "evidence-authority-domain-v1"


def normalized_host(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        host = (urlsplit(candidate).hostname or "").lower().strip(".")
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_domains(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        host = normalized_host(value)
        if host and host not in result:
            result.append(host)
    return result


def authority_matches_source(*, source_url: str, allowed_domains: list[str]) -> bool:
    host = normalized_host(source_url)
    if not host:
        return False
    for domain in normalize_domains(allowed_domains):
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False
