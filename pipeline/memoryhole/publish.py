"""Build data/derived/site.json — the only file the frontend reads for the
feed, stats, and health footer. Full hunks stay in the per-edit JSON files,
which the site imports at build time for the diff pages."""

import json
from collections import defaultdict

from .store import Store, now_iso

FEED_LIMIT = 200
SEVERITY_RANK = {"NARRATIVE": 3, "FACTUAL": 2, "MINOR": 1, "COSMETIC": 0}


def summarize(edit: dict) -> str:
    """First changed snippet, for feed previews."""
    for h in edit.get("hunks", []):
        for tag, text in h["ops"]:
            if tag != "eq" and text.strip():
                prefix = "deleted: " if tag == "del" else "added: "
                return prefix + (text[:157] + "..." if len(text) > 160 else text)
    return ""


def run_publish(store: Store) -> dict:
    edits = [e for e in store.edits() if "severity" in e]
    edits.sort(key=lambda e: (e["date"], SEVERITY_RANK[e["severity"]], e["detected_at"]),
               reverse=True)

    feed = [
        {k: e[k] for k in ("id", "date", "detected_at", "url", "domain", "source",
                           "severity", "score", "old_title", "new_title", "lang")}
        | {"summary": summarize(e)}
        for e in edits[:FEED_LIMIT]
    ]

    by_domain: dict[str, dict] = defaultdict(
        lambda: {"tracked": 0, "edits_total": 0, "last_edit": None,
                 "by_severity": dict.fromkeys(SEVERITY_RANK, 0)}
    )
    for meta in store.index.values():
        d = by_domain[meta["domain"]]
        d["tracked"] += 1
        d.setdefault("source", meta["source"])
    for e in edits:
        d = by_domain[e["domain"]]
        d["edits_total"] += 1
        d["by_severity"][e["severity"]] += 1
        d["last_edit"] = max(d["last_edit"] or "", e["detected_at"])

    health_path = store.derived / "health.json"
    health = json.loads(health_path.read_text(encoding="utf-8")) if health_path.exists() else {}
    health["total_edits"] = len(edits)

    site = {
        "generated_at": now_iso(),
        "edits": feed,
        "sources": [
            {"domain": k} | v for k, v in sorted(by_domain.items())
        ],
        "health": health,
    }
    store.write_derived("site.json", site)
    store.write_derived("health.json", health)
    return site
