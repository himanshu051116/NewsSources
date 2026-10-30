from __future__ import annotations

import json
from urllib.parse import urljoin

SPECIALIZED_AUTHORITY_ADAPTER_VERSION = "specialized-authority-adapters-v1"


def ckan_candidate_urls(body: bytes, *, base_url: str, max_results: int) -> list[str]:
    """Extract dataset/resource URLs from a CKAN ``package_search`` response."""
    payload = _load_json(body)
    if not isinstance(payload, dict) or payload.get("success") is False:
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    packages = result.get("results")
    if not isinstance(packages, list):
        return []
    found: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        _append_url(found, package.get("url"), base_url=base_url)
        name = package.get("name")
        if isinstance(name, str) and name.strip():
            _append_url(found, f"/dataset/{name.strip()}", base_url=base_url)
        resources = package.get("resources")
        if isinstance(resources, list):
            for resource in resources:
                if not isinstance(resource, dict):
                    continue
                _append_url(found, resource.get("url"), base_url=base_url)
                _append_url(found, resource.get("url_type"), base_url=base_url)
                if len(found) >= max_results:
                    return found[:max_results]
        if len(found) >= max_results:
            return found[:max_results]
    return found[:max_results]


def socrata_candidate_urls(body: bytes, *, max_results: int) -> list[str]:
    """Extract canonical dataset/API URLs from a Socrata discovery response."""
    payload = _load_json(body)
    rows: object
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        rows = payload["results"]
    elif isinstance(payload, list):
        rows = payload
    else:
        return []
    found: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        resource = row.get("resource")
        metadata = row.get("metadata")
        permalink = row.get("permalink")
        _append_absolute(found, permalink)
        if isinstance(resource, dict):
            _append_absolute(found, resource.get("permalink"))
            domain = resource.get("domain")
            identifier = resource.get("id")
            if isinstance(domain, str) and isinstance(identifier, str):
                _append_absolute(found, f"https://{domain}/resource/{identifier}.json")
        if isinstance(metadata, dict):
            _append_absolute(found, metadata.get("permalink"))
        if len(found) >= max_results:
            break
    return found[:max_results]


def configured_json_candidate_urls(
    body: bytes,
    *,
    base_url: str,
    candidate_fields: tuple[str, ...],
    max_results: int,
) -> list[str]:
    """Extract URLs only from explicitly configured field names.

    Unlike the generic recursive JSON URL finder, this prevents unrelated URL-valued fields
    from being mistaken for official evidence documents.
    """
    payload = _load_json(body)
    if payload is None:
        return []
    allowed_fields = {item.strip() for item in candidate_fields if item.strip()}
    if not allowed_fields:
        return []
    found: list[str] = []

    def visit(value: object) -> None:
        if len(found) >= max_results:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if key in allowed_fields and isinstance(child, str):
                    _append_url(found, child, base_url=base_url)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return found[:max_results]


def _load_json(body: bytes) -> object | None:
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def _append_url(found: list[str], value: object, *, base_url: str) -> None:
    if not isinstance(value, str) or not value.strip():
        return
    candidate = urljoin(base_url, value.strip())
    _append_absolute(found, candidate)


def _append_absolute(found: list[str], value: object) -> None:
    if not isinstance(value, str):
        return
    candidate = value.strip()
    if not candidate.startswith(("http://", "https://")):
        return
    if candidate not in found:
        found.append(candidate)
