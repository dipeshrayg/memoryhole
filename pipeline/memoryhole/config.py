"""Load and validate sources.yaml."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

DEFAULTS = {"max_articles": 5, "track_days": 5, "crawl_delay": 2}


@dataclass(frozen=True)
class Source:
    name: str
    rss: str | None
    url: str | None
    max_articles: int
    track_days: int
    crawl_delay: float

    @property
    def domain(self) -> str:
        return urlparse(self.rss or self.url).netloc


def load_sources(path: str | Path) -> list[Source]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    defaults = {**DEFAULTS, **(raw.get("defaults") or {})}
    sources = []
    for entry in raw["sources"]:
        if not entry.get("rss") and not entry.get("url"):
            raise ValueError(f"source {entry.get('name')!r} needs an 'rss' or 'url' key")
        sources.append(
            Source(
                name=entry["name"],
                rss=entry.get("rss"),
                url=entry.get("url"),
                max_articles=int(entry.get("max_articles", defaults["max_articles"])),
                track_days=int(entry.get("track_days", defaults["track_days"])),
                crawl_delay=float(entry.get("crawl_delay", defaults["crawl_delay"])),
            )
        )
    return sources
