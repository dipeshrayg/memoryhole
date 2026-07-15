"""Git-as-database storage. Snapshots are plain text files under
data/snapshots/<domain>/<id>.txt; metadata lives in index.json.
Derived artifacts (edit records, site.json, health.json) under data/derived/."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def content_hash(title: str, text: str) -> str:
    return hashlib.sha256(f"{title}\n{text}".encode()).hexdigest()[:16]


class Store:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir)
        self.snapshots = self.root / "snapshots"
        self.derived = self.root / "derived"
        self.edits_dir = self.derived / "edits"
        self.index_path = self.snapshots / "index.json"
        self.edits_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.index: dict = (
            json.loads(self.index_path.read_text(encoding="utf-8"))
            if self.index_path.exists()
            else {}
        )

    def save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self.index, indent=1, ensure_ascii=False), encoding="utf-8"
        )

    def snapshot_path(self, url: str) -> Path:
        return self.snapshots / urlparse(url).netloc / f"{url_id(url)}.txt"

    def read_snapshot(self, url: str) -> str | None:
        p = self.snapshot_path(url)
        # \r stripped defensively: a CRLF checkout must not cause phantom diffs
        return p.read_text(encoding="utf-8").replace("\r", "") if p.exists() else None

    def write_snapshot(self, url: str, text: str) -> None:
        p = self.snapshot_path(url)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def edit_path(self, edit_id: str) -> Path:
        return self.edits_dir / f"{edit_id}.json"

    def write_edit(self, edit: dict) -> None:
        self.edit_path(edit["id"]).write_text(
            json.dumps(edit, indent=1, ensure_ascii=False), encoding="utf-8"
        )

    def edits(self) -> list[dict]:
        return [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(self.edits_dir.glob("*.json"))
        ]

    def write_derived(self, name: str, obj: dict) -> None:
        (self.derived / name).write_text(
            json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8"
        )
