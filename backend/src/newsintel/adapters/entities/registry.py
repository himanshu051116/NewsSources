from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote_plus, urlsplit

from newsintel.adapters.http.safe_fetcher import FetchRequest
from newsintel.domain.intelligence.entity_registry import RegistryCandidate

ENTITY_REGISTRY_ADAPTER_VERSION = "configured-entity-registry-adapter-v1"


@dataclass(frozen=True, slots=True)
class RegistrySearchResult:
    search_url: str
    response_sha256: str
    candidates: tuple[RegistryCandidate, ...]


async def search_configured_registry(
    fetcher,
    *,
    base_url: str,
    search_url_template: str,
    query: str,
    config: dict[str, object],
    max_results: int = 10,
) -> RegistrySearchResult:
    _validate_template(base_url, search_url_template)
    search_url = search_url_template.replace("{query}", quote_plus(query.strip()))
    host = urlsplit(base_url).hostname
    if not host:
        raise ValueError("registry base_url must contain a hostname")
    result = await fetcher.fetch(FetchRequest(search_url, allowed_domains=(host,)))
    if result.status_code < 200 or result.status_code >= 300:
        return RegistrySearchResult(search_url, result.body_sha256, ())
    payload = json.loads(result.body.decode("utf-8", errors="replace"))
    rows = _rows(payload, str(config.get("results_path") or ""))
    candidates: list[RegistryCandidate] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        external_id = _value(row, str(config.get("id_field") or "id"))
        label = _value(row, str(config.get("label_field") or "label"))
        if not isinstance(external_id, (str, int)) or not isinstance(label, str):
            continue
        aliases_value = _value(row, str(config.get("aliases_field") or "aliases"))
        aliases = tuple(str(item) for item in aliases_value if isinstance(item, (str, int))) if isinstance(aliases_value, list) else ()
        entity_type = _value(row, str(config.get("type_field") or "type"))
        country = _value(row, str(config.get("country_field") or "country"))
        canonical_url = _value(row, str(config.get("url_field") or "url"))
        candidates.append(
            RegistryCandidate(
                external_id=str(external_id),
                label=label,
                entity_type=str(entity_type) if entity_type is not None else None,
                aliases=aliases,
                country=str(country) if country is not None else None,
                canonical_url=str(canonical_url) if isinstance(canonical_url, str) else None,
            )
        )
        if len(candidates) >= max_results:
            break
    return RegistrySearchResult(search_url, result.body_sha256, tuple(candidates))


def _validate_template(base_url: str, template: str) -> None:
    if template.count("{query}") != 1:
        raise ValueError("registry search_url_template must contain exactly one {query} placeholder")
    base = urlsplit(base_url)
    target = urlsplit(template.replace("{query}", "test"))
    if base.scheme not in {"http", "https"} or not base.hostname:
        raise ValueError("registry base_url must be public HTTP(S)")
    if target.scheme not in {"http", "https"} or not target.hostname:
        raise ValueError("registry search template must be absolute HTTP(S)")
    if target.hostname.casefold().strip(".") != base.hostname.casefold().strip("."):
        raise ValueError("registry search template host must match base_url host")
    lowered = template.casefold()
    for key in ("api_key=", "apikey=", "access_token=", "token=", "secret=", "key="):
        if key in lowered:
            raise ValueError("registry search templates must not embed credentials in URLs")


def _rows(payload: object, path: str) -> list[object]:
    value = payload
    for part in [item for item in path.split(".") if item]:
        if not isinstance(value, dict):
            return []
        value = value.get(part)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _value(row: dict[str, object], path: str) -> object | None:
    value: object = row
    for part in [item for item in path.split(".") if item]:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def validate_registry_search_template(base_url: str, search_url_template: str) -> None:
    _validate_template(base_url, search_url_template)
