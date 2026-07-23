from memoryhole.extract import MAX_TEXT, extract, normalize


def test_normalize_kills_cosmetic_churn():
    assert normalize("Hello  “world”…\n\n  spaced   out ") == 'Hello "world"...\nspaced out'
    assert normalize("Real line here\nPublished 08:14, 14 July 2026\nAdvertisement — buy now") \
        == "Real line here"


def test_normalize_kills_embed_consent_placeholders():
    text = ("Real reporting stays.\n"
            "To display this content from YouTube, you must enable advertisement "
            "tracking and audience measurement.\n"
            "One of your browser extensions seems to be blocking this.\n"
            "More real reporting.")
    assert normalize(text) == "Real reporting stays.\nMore real reporting."


def test_normalize_kills_geo_block_placeholder():
    text = ("Real reporting stays.\n"
            "This content is not available in your location. There was an error.\n"
            "More real reporting.")
    assert normalize(text) == "Real reporting stays.\nMore real reporting."


def test_normalize_caps_giant_pages():
    assert len(normalize("word " * 100_000)) == MAX_TEXT


def test_boilerplate_churn_is_not_an_edit(fixture_html):
    """Fixture pair differs only in nav/ads/footer/timestamp — same extraction."""
    a = extract(fixture_html("article_v1.html"), url="https://example.com/storm")
    b = extract(fixture_html("article_v1_churn.html"), url="https://example.com/storm")
    assert a and b
    assert a["text"] == b["text"]
    assert a["title"] == b["title"]


def test_extraction_rejects_stubs():
    assert extract("<html><body><p>too short</p></body></html>") is None
