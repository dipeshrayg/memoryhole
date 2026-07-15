import os
from pathlib import Path

import pytest

os.environ["MEMORYHOLE_NO_EMBED"] = "1"  # tests must be deterministic and offline

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


def make_edit(old_text, new_text, old_title="Same headline", new_title=None):
    """Build an edit record and run the real diff over it."""
    from memoryhole.diffing import signals, word_diff

    edit = {
        "id": "test", "old_text": old_text, "new_text": new_text,
        "old_title": old_title, "new_title": new_title or old_title,
    }
    edit["hunks"] = word_diff(old_text, new_text)
    edit["signals"] = signals(edit, edit["hunks"])
    return edit
