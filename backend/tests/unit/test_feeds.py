from newsintel.adapters.collectors.feeds import (
    discover_websub_links,
    parse_feed,
    parse_feed_datetime,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType


def test_parses_rss_items() -> None:
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>story-1</guid>
        <title>Story One</title>
        <link>https://example.com/story-1</link>
        <pubDate>Wed, 25 Jun 2026 10:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""

    items = parse_feed(xml, "https://example.com/rss")

    assert len(items) == 1
    assert items[0].external_id == "story-1"
    assert items[0].channel_type is DiscoveryChannelType.RSS
    assert parse_feed_datetime(items[0].published_at_raw).isoformat() == (
        "2026-06-25T10:00:00+00:00"
    )


def test_parses_atom_and_discovers_websub() -> None:
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <link rel="self" href="https://example.com/feed"/>
      <link rel="hub" href="https://hub.example.net"/>
      <entry>
        <id>tag:example.com,2026:1</id>
        <title>Atom Story</title>
        <link rel="alternate" href="https://example.com/atom-story"/>
        <updated>2026-06-25T10:00:00Z</updated>
      </entry>
    </feed>"""

    items = parse_feed(xml, "https://example.com/feed")
    hubs, self_url = discover_websub_links(xml)

    assert items[0].channel_type is DiscoveryChannelType.ATOM
    assert hubs == ("https://hub.example.net",)
    assert self_url == "https://example.com/feed"



def test_parses_json_feed_11() -> None:
    from newsintel.adapters.collectors.feeds import parse_json_feed

    payload = '''{
      "version": "https://jsonfeed.org/version/1.1",
      "title": "Example",
      "language": "en",
      "items": [{
        "id": "story-1",
        "url": "https://example.com/news/story-one-today",
        "title": "Story One",
        "date_published": "2026-08-13T00:30:00Z"
      }]
    }'''

    items = parse_json_feed(payload, "https://example.com/feed.json")

    assert len(items) == 1
    assert items[0].external_id == "story-1"
    assert items[0].channel_type is DiscoveryChannelType.JSON_FEED
    assert items[0].metadata["language"] == "en"


def test_feed_modification_dates_are_not_publication_dates():
    from newsintel.adapters.collectors.feeds import parse_json_feed

    atom = '<feed><entry><link href="https://example.com/news/report"/><updated>2026-10-30T10:00:00Z</updated><published>2021-10-01T10:00:00Z</published></entry></feed>'
    assert parse_feed(atom, "https://example.com/feed")[0].published_at_raw == "2021-10-01T10:00:00Z"
    assert parse_feed(atom.replace('<published>2021-10-01T10:00:00Z</published>', ''),
                      "https://example.com/feed")[0].published_at_raw is None
    payload = '{"version":"https://jsonfeed.org/version/1.1","items":[{"id":"1","url":"https://example.com/news/report","date_modified":"2026-10-30T10:00:00Z"}]}'
    assert parse_json_feed(payload, "https://example.com/feed")[0].published_at_raw is None
