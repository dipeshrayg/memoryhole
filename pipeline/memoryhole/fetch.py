"""Fetch tracked pages, snapshot extracted text, and record pending edits
when content changed since the last snapshot. One failing source never fails
the run: errors are logged into the health report and skipped."""

import logging
import time
import urllib.robotparser
from datetime import UTC, datetime
from urllib.parse import urlparse

import feedparser
import requests

from .config import Source
from .extract import extract
from .store import Store, content_hash, now_iso, url_id

log = logging.getLogger("memoryhole")
USER_AGENT = "MemoryHoleBot/1.0 (+https://github.com/dipeshrayg/memoryhole)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


def default_http_get(url: str) -> tuple[int, str]:
    """Return (status_code, body). Raises on transport errors."""
    r = _session.get(url, timeout=20)
    return r.status_code, r.text


def robots_allowed(url: str, http_get) -> bool:
    domain = urlparse(url).netloc
    if domain not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            status, body = http_get(f"{urlparse(url).scheme}://{domain}/robots.txt")
            if status == 200:
                rp.parse(body.splitlines())
                _robots[domain] = rp
            else:
                _robots[domain] = None  # no robots.txt -> allowed
        except Exception:
            _robots[domain] = None
    rp = _robots[domain]
    return rp is None or rp.can_fetch(USER_AGENT, url)


def polite_wait(domain: str, delay: float) -> None:
    elapsed = time.monotonic() - _last_hit.get(domain, 0)
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_hit[domain] = time.monotonic()


def detect_lang(text: str) -> str:
    try:
        from langdetect import detect

        return detect(text[:2000])
    except Exception:
        return "unknown"


def discover_from_rss(source: Source, http_get) -> list[tuple[str, str]]:
    """Return [(url, title)] for the newest entries of a feed."""
    polite_wait(source.domain, source.crawl_delay)
    status, body = http_get(source.rss)
    if status >= 400:
        raise RuntimeError(f"feed returned HTTP {status}")
    feed = feedparser.parse(body)
    if not feed.entries:
        raise RuntimeError("feed has no entries")
    out, seen = [], set()
    for e in feed.entries[: source.max_articles * 2]:
        link = (e.get("link") or "").split("#")[0].strip()
        if link and link not in seen:
            seen.add(link)
            out.append((link, e.get("title", "")))
        if len(out) >= source.max_articles:
            break
    return out


def check_page(store: Store, source: Source, url: str, http_get) -> str:
    """Fetch one page, update snapshot/index, record a pending edit if changed.
    Returns one of: 'new', 'unchanged', 'changed', 'retired', 'skipped'."""
    meta = store.index.get(url)
    if meta and meta.get("status") == "retired":
        return "skipped"
    if not robots_allowed(url, http_get):
        log.info("robots.txt disallows %s", url)
        return "skipped"
    polite_wait(urlparse(url).netloc, source.crawl_delay)
    status, body = http_get(url)
    if status in (404, 410):
        if meta:
            meta["status"] = "retired"
            return "retired"
        return "skipped"
    if status >= 400:
        raise RuntimeError(f"HTTP {status} for {url}")
    result = extract(body, url=url)
    if result is None:
        return "skipped"
    title, text = result["title"], result["text"]
    old_text = store.read_snapshot(url)
    if old_text is None or meta is None:
        store.write_snapshot(url, text)
        store.index[url] = {
            "id": url_id(url),
            "domain": urlparse(url).netloc,
            "source": source.name,
            "title": title,
            "lang": detect_lang(text),
            "hash": content_hash(title, text),
            "first_seen": now_iso(),
            "last_fetched": now_iso(),
            "status": "active",
        }
        return "new"
    meta["last_fetched"] = now_iso()
    new_hash = content_hash(title, text)
    if new_hash == meta["hash"]:
        return "unchanged"
    # Paywall/error guard: content collapsing to a stub is not an edit.
    if len(text) < 500 and len(text) < 0.4 * len(old_text):
        log.info("suspected paywall/stub for %s — ignoring", url)
        return "skipped"
    edit_id = f"{url_id(url)}-{meta['hash'][:8]}-{new_hash[:8]}"
    if not store.edit_path(edit_id).exists():  # idempotent across re-runs
        store.write_edit(
            {
                "id": edit_id,
                "url": url,
                "domain": meta["domain"],
                "source": source.name,
                "lang": meta.get("lang", "unknown"),
                "detected_at": now_iso(),
                "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "old_title": meta["title"],
                "new_title": title,
                "old_text": old_text,
                "new_text": text,
            }
        )
    store.write_snapshot(url, text)
    meta.update(title=title, hash=new_hash, last_changed=now_iso())
    return "changed"


def tracked_urls(store: Store, source: Source) -> list[str]:
    """Previously seen articles from this source still within their tracking window."""
    cutoff = datetime.now(UTC).timestamp() - source.track_days * 86400
    out = []
    for url, meta in store.index.items():
        if meta.get("source") != source.name or meta.get("status") != "active":
            continue
        first = datetime.strptime(meta["first_seen"], "%Y-%m-%dT%H:%M:%SZ")
        if first.replace(tzinfo=UTC).timestamp() >= cutoff:
            out.append(url)
    return out


def run_fetch(sources: list[Source], store: Store, http_get=default_http_get) -> dict:
    """Fetch every source. Returns a health report; never raises for one source."""
    started = time.monotonic()
    report = {"last_run": now_iso(), "sources": [], "articles_checked": 0, "edits_found": 0}
    for source in sources:
        entry = {"name": source.name, "ok": True, "checked": 0, "changed": 0, "error": None}
        try:
            if source.rss:
                known = set(store.index)
                queue = [
                    u for u, _ in discover_from_rss(source, http_get) if u not in known
                ] + tracked_urls(store, source)
            else:
                queue = [source.url]  # static pages are tracked forever
            for url in dict.fromkeys(queue):  # dedupe, keep order
                try:
                    outcome = check_page(store, source, url, http_get)
                except Exception as exc:
                    log.warning("page failed %s: %s", url, exc)
                    continue
                entry["checked"] += 1
                if outcome == "changed":
                    entry["changed"] += 1
        except Exception as exc:
            entry.update(ok=False, error=str(exc))
            log.warning("source failed %s: %s", source.name, exc)
        report["sources"].append(entry)
        report["articles_checked"] += entry["checked"]
        report["edits_found"] += entry["changed"]
        store.save_index()  # persist progress source-by-source
    report["duration_s"] = round(time.monotonic() - started, 1)
    store.write_derived("health.json", report)
    return report
