"""Keep live reporting ahead of dated sitemap archives."""
import calendar
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlsplit

CHANNEL_PRIORITY = {
    "rss": 0, "atom": 0, "json_feed": 0, "news_sitemap": 1,
    "homepage": 2, "category": 3, "section": 3, "listing": 3, "sitemap": 4,
}
MAX_MANUAL_CHANNELS_PER_PUBLISHER = 20
MAX_CHILD_SITEMAPS_PER_POLL = 30


def sitemap_period_end(url: str) -> datetime | None:
    """Exclusive end of an explicitly dated map, including month-wide archives."""
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    year = month = day = None
    try:
        if query.get("yyyy") and query.get("mm"):
            year, month = int(query["yyyy"][0]), int(query["mm"][0])
            day = int(query["dd"][0]) if query.get("dd") else None
        else:
            path = unquote(parsed.path).casefold()
            match = re.search(r"(?<!\d)(20\d{2})[-_/](\d{1,2})[-_/](\d{1,2})(?!\d)", path)
            if match:
                year, month, day = map(int, match.groups())
            else:
                match = re.search(r"(?<!\d)(\d{1,2})[-_/](\d{1,2})[-_/](20\d{2})(?!\d)", path)
                if match:
                    day, month, year = map(int, match.groups())
                else:
                    match = re.search(r"(?<!\d)(20\d{2})[-_/]([a-z]+)[-_/](\d{1,2})(?!\d)", path)
                    if match:
                        year_text, named_month, _page = match.groups()
                        month_names = {name.casefold(): number for number, name
                                       in enumerate(calendar.month_name) if name}
                        month = month_names.get(named_month)
                        year, day = int(year_text), None
                    else:
                        match = re.search(r"(?<!\d)(20\d{2})[-_/](\d{1,2})(?!\d)", path)
                        if match:
                            year, month = map(int, match.groups())
        if year is None or month is None:
            return None
        if day is None:
            day = calendar.monthrange(year, month)[1]
        return datetime(year, month, day, tzinfo=UTC) + timedelta(days=1)
    except (ValueError, IndexError):
        return None


def current_sitemap(url: str, now: datetime, window_hours: int = 48) -> bool:
    end = sitemap_period_end(url)
    return end is None or end >= now - timedelta(hours=window_hours)
