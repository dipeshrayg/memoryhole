"""Re-running any stage on the same day must not duplicate data."""

from pathlib import Path

from memoryhole.classify import run_classify
from memoryhole.config import Source
from memoryhole.diffing import run_diff
from memoryhole.fetch import run_fetch
from memoryhole.publish import run_publish
from memoryhole.store import Store

FIXTURES = Path(__file__).parent / "fixtures"

FEED = """<rss version="2.0"><channel><title>Example</title>
<item><title>Storm Delia</title><link>https://example.com/storm</link></item>
</channel></rss>"""

SOURCE = Source(name="Example", rss="https://example.com/feed.xml", url=None,
                max_articles=5, track_days=5, crawl_delay=0)


def serve(pages):
    def http_get(url):
        if url.endswith("robots.txt"):
            return 404, ""
        if url.endswith("feed.xml"):
            return 200, FEED
        return 200, (FIXTURES / pages["https://example.com/storm"]).read_text(encoding="utf-8")

    return http_get


def run_all(store, http_get):
    run_fetch([SOURCE], store, http_get)
    run_diff(store)
    run_classify(store)
    return run_publish(store)


def test_pipeline_idempotent_and_detects_mutation(tmp_path):
    store = Store(tmp_path)
    pages = {"https://example.com/storm": "article_v1.html"}

    # First run: baseline snapshot, no edits.
    site = run_all(store, serve(pages))
    assert store.snapshot_path("https://example.com/storm").exists()
    assert site["edits"] == []

    # Second identical run: nothing new.
    site = run_all(store, serve(pages))
    assert site["edits"] == []
    assert len(store.edits()) == 0

    # Publisher silently changes a number.
    pages["https://example.com/storm"] = "article_v2_number.html"
    site = run_all(store, serve(pages))
    assert len(site["edits"]) == 1
    assert site["edits"][0]["severity"] == "FACTUAL"

    # Re-running against the same mutated content: still exactly one edit.
    site = run_all(store, serve(pages))
    assert len(store.edits()) == 1
    assert len(site["edits"]) == 1

    # Health report reflects the run.
    assert site["health"]["sources"][0]["ok"] is True
    assert site["health"]["total_edits"] == 1


def test_dead_page_is_retired(tmp_path):
    store = Store(tmp_path)
    pages = {"https://example.com/storm": "article_v1.html"}
    run_all(store, serve(pages))

    def gone(url):
        if url.endswith(("robots.txt",)):
            return 404, ""
        if url.endswith("feed.xml"):
            return 200, FEED
        return 404, ""

    run_all(store, gone)
    assert store.index["https://example.com/storm"]["status"] == "retired"


def test_failing_feed_does_not_fail_run(tmp_path):
    store = Store(tmp_path)

    def broken(url):
        raise ConnectionError("dns failure")

    report = run_fetch([SOURCE], store, broken)
    assert report["sources"][0]["ok"] is False
    assert "dns failure" in report["sources"][0]["error"]
