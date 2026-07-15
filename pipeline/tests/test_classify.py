"""End-to-end regression tests: fixture HTML -> extract -> diff -> classify.
Rules-only (no embedding model), so verdicts are deterministic."""

from conftest import make_edit

from memoryhole.classify import score_edit
from memoryhole.extract import extract

BASE = ("The city council approved the housing plan on Tuesday after a debate "
        "lasting four hours. Residents raised concerns about traffic congestion "
        "near the proposed site. The mayor said construction could begin in "
        "spring and promised a further consultation before any demolition work "
        "starts on the eastern side of the district.") * 2


def classify_fixture_pair(fixture_html, old_name, new_name):
    old = extract(fixture_html(old_name), url="https://example.com/storm")
    new = extract(fixture_html(new_name), url="https://example.com/storm")
    edit = make_edit(old["text"], new["text"], old["title"], new["title"])
    return score_edit(edit)


def test_changed_number_is_factual(fixture_html):
    result = classify_fixture_pair(fixture_html, "article_v1.html", "article_v2_number.html")
    assert result["severity"] == "FACTUAL"


def test_deleted_paragraph_is_narrative(fixture_html):
    result = classify_fixture_pair(fixture_html, "article_v1.html", "article_v3_paradel.html")
    assert result["severity"] == "NARRATIVE"


def test_punctuation_only_is_cosmetic():
    edit = make_edit(BASE, BASE.replace("Tuesday after", "Tuesday, after"))
    result = score_edit(edit)
    assert result["severity"] == "COSMETIC"
    assert edit["signals"]["cosmetic_only"]


def test_rewording_is_minor():
    edit = make_edit(BASE, BASE.replace("said construction", "stated construction"))
    assert score_edit(edit)["severity"] == "MINOR"


def test_headline_change_is_narrative():
    edit = make_edit(BASE, BASE, old_title="Minister denies wrongdoing",
                     new_title="Minister under investigation")
    assert score_edit(edit)["severity"] == "NARRATIVE"


def test_block_deletion_is_narrative():
    para = (" Opposition members walked out of the chamber in protest before the "
            "final vote was recorded, calling the consultation process a sham and "
            "demanding the entire planning framework be reviewed by an independent "
            "panel next year.")
    edit = make_edit(BASE + para, BASE)
    assert score_edit(edit)["severity"] == "NARRATIVE"
