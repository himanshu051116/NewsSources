import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from newsintel.domain.acquisition.models import (
    DiscoveredItem,
    DiscoveryChannelType,
)

ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
JSON_FEED_VERSIONS = {
    "https://jsonfeed.org/version/1",
    "https://jsonfeed.org/version/1.1",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: Element, names: set[str]) -> str | None:
    for child in element:
        if _local_name(child.tag) in names and child.text:
            value = str(child.text).strip()
            if value:
                return value
    return None


def _atom_link(entry: Element) -> str | None:
    fallback: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href_value = child.attrib.get("href")
        href = str(href_value) if href_value is not None else None
        if not href:
            continue
        rel = child.attrib.get("rel", "alternate")
        if rel == "alternate":
            return href
        fallback = fallback or href
    return fallback


def parse_feed(xml: str | bytes, channel_url: str) -> list[DiscoveredItem]:
    """Parse RSS/RDF or Atom into the common discovery item contract."""
    root = ElementTree.fromstring(xml)
    root_name = _local_name(root.tag)
    discovered_at = datetime.now(UTC)

    if root_name in {"rss", "rdf"}:
        items = [element for element in root.iter() if _local_name(element.tag) == "item"]
        return [
            DiscoveredItem(
                external_id=_child_text(item, {"guid", "id"}),
                url=_child_text(item, {"link"}) or "",
                title=_child_text(item, {"title"}),
                published_at_raw=_child_text(
                    item,
                    {"pubdate", "published", "date"},
                ),
                channel_type=DiscoveryChannelType.RSS,
                channel_url=channel_url,
                discovered_at=discovered_at,
            )
            for item in items
            if _child_text(item, {"link"})
        ]

    if root_name == "feed" or root.tag == f"{{{ATOM_NAMESPACE}}}feed":
        entries = [element for element in root if _local_name(element.tag) == "entry"]
        output: list[DiscoveredItem] = []
        for entry in entries:
            link = _atom_link(entry)
            if not link:
                continue
            output.append(
                DiscoveredItem(
                    external_id=_child_text(entry, {"id"}),
                    url=link,
                    title=_child_text(entry, {"title"}),
                    published_at_raw=_child_text(entry, {"published"}),
                    channel_type=DiscoveryChannelType.ATOM,
                    channel_url=channel_url,
                    discovered_at=discovered_at,
                )
            )
        return output

    raise ValueError(f"unsupported feed root element: {root_name}")


def parse_json_feed(payload: str | bytes, channel_url: str) -> list[DiscoveredItem]:
    """Parse JSON Feed 1.0/1.1 without adding a third-party parser dependency."""
    if isinstance(payload, bytes):
        text = payload.decode("utf-8-sig")
    else:
        text = payload
    document: Any = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError("JSON Feed root must be an object")
    version = document.get("version")
    if version not in JSON_FEED_VERSIONS:
        raise ValueError(f"unsupported JSON Feed version: {version!r}")
    raw_items = document.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("JSON Feed items must be an array")

    discovered_at = datetime.now(UTC)
    output: list[DiscoveredItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        url_value = raw_item.get("url") or raw_item.get("external_url")
        if not isinstance(url_value, str) or not url_value.strip():
            continue
        external_id = raw_item.get("id")
        title = raw_item.get("title")
        published_at = raw_item.get("date_published")
        metadata: dict[str, str] = {}
        language = raw_item.get("language") or document.get("language")
        if isinstance(language, str) and language.strip():
            metadata["language"] = language.strip()
        output.append(
            DiscoveredItem(
                external_id=(
                    str(external_id).strip()
                    if external_id is not None and str(external_id).strip()
                    else None
                ),
                url=url_value.strip(),
                title=title.strip() if isinstance(title, str) and title.strip() else None,
                published_at_raw=(
                    published_at.strip()
                    if isinstance(published_at, str) and published_at.strip()
                    else None
                ),
                channel_type=DiscoveryChannelType.JSON_FEED,
                channel_url=channel_url,
                discovered_at=discovered_at,
                metadata=metadata,
            )
        )
    return output


def parse_feed_payload(payload: str | bytes, channel_url: str) -> list[DiscoveredItem]:
    """Auto-detect XML syndication feeds and JSON Feed."""
    raw = payload.encode() if isinstance(payload, str) else payload
    if raw.lstrip().startswith(b"{"):
        return parse_json_feed(payload, channel_url)
    return parse_feed(payload, channel_url)


def parse_feed_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def discover_websub_links(xml: str | bytes) -> tuple[tuple[str, ...], str | None]:
    root = ElementTree.fromstring(xml)
    hubs: list[str] = []
    self_url: str | None = None
    for element in root.iter():
        if _local_name(element.tag) != "link":
            continue
        rel = element.attrib.get("rel", "").lower()
        href = element.attrib.get("href")
        if not href:
            continue
        if rel == "hub":
            hubs.append(href)
        elif rel == "self":
            self_url = href
    return tuple(dict.fromkeys(hubs)), self_url
