"""CLI: memoryhole fetch|diff|classify|publish|run-all"""

import argparse
import logging
import sys

from .classify import run_classify
from .config import load_sources
from .diffing import run_diff
from .fetch import run_fetch
from .publish import run_publish
from .store import Store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="memoryhole")
    parser.add_argument("command",
                        choices=["fetch", "diff", "classify", "publish", "run-all"])
    parser.add_argument("--data", default="data", help="data directory (default: data)")
    parser.add_argument("--config", default="sources.yaml")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    store = Store(args.data)

    if args.command in ("fetch", "run-all"):
        report = run_fetch(load_sources(args.config), store)
        ok = sum(1 for s in report["sources"] if s["ok"])
        print(f"fetch: {report['articles_checked']} pages checked, "
              f"{report['edits_found']} changed, "
              f"{ok}/{len(report['sources'])} sources ok, {report['duration_s']}s")
    if args.command in ("diff", "run-all"):
        print(f"diff: {run_diff(store)} edits diffed")
    if args.command in ("classify", "run-all"):
        print(f"classify: {run_classify(store)} edits classified")
    if args.command in ("publish", "run-all"):
        site = run_publish(store)
        print(f"publish: site.json with {len(site['edits'])} edits, "
              f"{len(site['sources'])} sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
