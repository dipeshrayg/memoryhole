"""Build data/derived/site.json — the only file the frontend reads for the
feed, stats, filters, and health footer. Full hunks stay in the per-edit
JSON files, which the site imports at build time for the diff pages."""

import json
from collections import defaultdict

from .store import Store, now_iso

FEED_LIMIT = 400
SEVERITY_RANK = {"NARRATIVE": 3, "FACTUAL": 2, "MINOR": 1, "COSMETIC": 0}
FEED_FIELDS = ("id", "date", "detected_at", "url", "domain", "source",
               "country", "category", "severity", "score", "old_title",
               "new_title", "lang")


def summarize(edit: dict) -> str:
    """First changed snippet, for feed previews."""
    for h in edit.get("hunks", []):
        for tag, text in h["ops"]:
            if tag != "eq" and text.strip():
                prefix = "deleted: " if tag == "del" else "added: "
                return prefix + (text[:157] + "..." if len(text) > 160 else text)
    return ""


def _aggregate(edits: list[dict], store: Store, key: str) -> dict[str, dict]:
    """Roll up tracked-page and edit counts by index meta's `key` field
    (domain or source name)."""
    out: dict[str, dict] = defaultdict(
        lambda: {"tracked": 0, "edits_total": 0, "last_edit": None,
                 "domain": None, "source": None, "country": "Global", "category": "world",
                 "by_severity": dict.fromkeys(SEVERITY_RANK, 0)}
    )
    for meta in store.index.values():
        d = out[meta[key]]
        d["tracked"] += 1
        d["domain"] = meta["domain"]
        d["source"] = meta["source"]
        d["country"] = meta.get("country", "Global")
        d["category"] = meta.get("category", "world")
    for e in edits:
        d = out[e[key]]
        d["edits_total"] += 1
        d["by_severity"][e["severity"]] += 1
        d["last_edit"] = max(d["last_edit"] or "", e["detected_at"])
    return out


def run_publish(store: Store) -> dict:
    edits = [e for e in store.edits() if "severity" in e]
    edits.sort(key=lambda e: (e["date"], SEVERITY_RANK[e["severity"]], e["detected_at"]),
               reverse=True)

    # country/category default for edit records written before those fields existed
    feed = [
        {k: e[k] for k in FEED_FIELDS if k not in ("country", "category")}
        | {"country": e.get("country", "Global"), "category": e.get("category", "world"),
           "summary": summarize(e),
           "market_figures_changed": e.get("signals", {}).get("market_figures_changed", [])}
        for e in edits[:FEED_LIMIT]
    ]

    # Keyed by domain: exactly one row per distinct article domain, so
    # /source/[domain]/ generates one static page per domain. Multiple
    # configured sources can share a domain (e.g. every BBC section feed
    # resolves articles to www.bbc.co.uk) — this view intentionally merges
    # them into one "this outlet" page.
    by_domain = _aggregate(edits, store, "domain")
    sources = [{"domain": k} | v for k, v in sorted(by_domain.items())]

    # Keyed by source name: one row per configured source, even when several
    # share a domain — this is what the filter dropdown and homepage table
    # need, since category/country are properties of the source, not the
    # domain (BBC News is "world", BBC Business is "finance", same domain).
    by_source = _aggregate(edits, store, "source")
    source_list = [{"name": k} | v for k, v in sorted(by_source.items())]

    # Full option sets for the filter UI, drawn from every tracked source —
    # not just ones with edits today — so a quiet category still shows up.
    facets = {
        "countries": sorted({s["country"] for s in source_list}),
        "categories": sorted({s["category"] for s in source_list}),
        "sources": sorted({s["name"] for s in source_list}),
        "severities": ["NARRATIVE", "FACTUAL", "MINOR", "COSMETIC"],
    }

    health_path = store.derived / "health.json"
    health = json.loads(health_path.read_text(encoding="utf-8")) if health_path.exists() else {}
    health["total_edits"] = len(edits)

    site = {
        "generated_at": now_iso(),
        "edits": feed,
        "sources": sources,
        "source_list": source_list,
        "facets": facets,
        "health": health,
    }
    store.write_derived("site.json", site)
    store.write_derived("health.json", health)
    return site
