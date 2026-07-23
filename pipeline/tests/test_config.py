import pytest

from memoryhole.config import load_sources


def write(tmp_path, yaml_text):
    p = tmp_path / "sources.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return p


def test_country_and_category_default(tmp_path):
    path = write(tmp_path, """
sources:
  - name: Example
    rss: https://example.com/feed.xml
""")
    [source] = load_sources(path)
    assert source.country == "Global"
    assert source.category == "world"


def test_country_and_category_explicit(tmp_path):
    path = write(tmp_path, """
sources:
  - name: Example Markets
    rss: https://example.com/markets.xml
    country: Japan
    category: finance
""")
    [source] = load_sources(path)
    assert source.country == "Japan"
    assert source.category == "finance"


def test_unknown_category_rejected(tmp_path):
    path = write(tmp_path, """
sources:
  - name: Example
    rss: https://example.com/feed.xml
    category: gossip
""")
    with pytest.raises(ValueError, match="unknown category"):
        load_sources(path)
