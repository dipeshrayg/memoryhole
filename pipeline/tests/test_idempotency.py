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
                max_articles=5, track_days=5, crawl_delay=0,
                country="Testland", category="world")


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

    # Country/category flow from the source config into the edit and facets.
    assert site["edits"][0]["country"] == "Testland"
    assert site["edits"][0]["category"] == "world"
    assert site["facets"]["countries"] == ["Testland"]
    assert site["facets"]["categories"] == ["world"]
    assert site["facets"]["sources"] == ["Example"]
    assert site["facets"]["severities"] == ["NARRATIVE", "FACTUAL", "MINOR", "COSMETIC"]


def test_sources_sharing_a_domain_are_not_collapsed(tmp_path):
    """Two configured sources whose articles resolve to the same domain (like
    every BBC section feed landing on www.bbc.co.uk) must still appear as two
    distinct rows in source_list/facets — only the domain-keyed routing view
    is allowed to merge them."""
    news = Source(name="Example News", rss="https://example.com/news.xml", url=None,
                  max_articles=5, track_days=5, crawl_delay=0,
                  country="Testland", category="world")
    markets = Source(name="Example Markets", rss="https://example.com/markets.xml", url=None,
                     max_articles=5, track_days=5, crawl_delay=0,
                     country="Testland", category="finance")

    def http_get(url):
        if url.endswith("robots.txt"):
            return 404, ""
        if url.endswith("news.xml"):
            return 200, """<rss version="2.0"><channel><title>N</title>
                <item><title>A</title><link>https://example.com/a</link></item>
                </channel></rss>"""
        if url.endswith("markets.xml"):
            return 200, """<rss version="2.0"><channel><title>M</title>
                <item><title>B</title><link>https://example.com/b</link></item>
                </channel></rss>"""
        return 200, (FIXTURES / "article_v1.html").read_text(encoding="utf-8")

    store = Store(tmp_path)
    run_fetch([news, markets], store, http_get)
    run_diff(store)
    run_classify(store)
    site = run_publish(store)

    assert sorted(site["facets"]["sources"]) == ["Example Markets", "Example News"]
    assert sorted(site["facets"]["categories"]) == ["finance", "world"]
    assert len(site["source_list"]) == 2
    # The domain-keyed view (routing for /source/[domain]/) does merge them.
    assert len(site["sources"]) == 1
    assert site["sources"][0]["domain"] == "example.com"
    assert site["sources"][0]["tracked"] == 2


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
