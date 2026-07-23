from conftest import make_edit

from memoryhole.diffing import word_diff

BASE = ("The city council approved the housing plan on Tuesday after a debate "
        "lasting four hours. Residents raised concerns about traffic. "
        "The mayor said construction could begin in 2027.") * 3


def test_word_diff_finds_replacement():
    hunks = word_diff("alpha beta gamma delta", "alpha beta GAMMA delta")
    ops = [op for h in hunks for op in h["ops"]]
    assert ["del", "gamma"] in ops and ["ins", "GAMMA"] in ops


def test_word_diff_trims_context():
    old = " ".join(f"w{i}" for i in range(100))
    new = old.replace("w50", "CHANGED")
    hunks = word_diff(old, new)
    assert len(hunks) == 1
    eq_words = sum(len(t.split()) for tag, t in hunks[0]["ops"] if tag == "eq")
    assert eq_words <= 24  # 12 words context either side, not all 99


def test_identical_texts_produce_no_hunks():
    assert word_diff(BASE, BASE) == []


def test_number_change_signal():
    edit = make_edit(BASE, BASE.replace("2027", "2029"))
    assert "2027" in edit["signals"]["numbers_changed"]
    assert "2029" in edit["signals"]["numbers_changed"]


def test_quote_deletion_signal():
    quoted = BASE + ' "This decision will haunt this chamber for a decade to come," she said.'
    edit = make_edit(quoted, BASE)
    assert edit["signals"]["quotes_deleted"] == 1


def test_block_removal_signal():
    para = ("A completely separate closing paragraph with enough words to cross the "
            "block threshold because it keeps going on and on about procedural details "
            "for more than thirty words in total overall.")
    edit = make_edit(BASE + " " + para, BASE)
    assert edit["signals"]["blocks_removed"] == 1
    assert edit["signals"]["blocks_added"] == 0


def test_market_figure_signal_currency():
    edit = make_edit(BASE + " Gold closed at $1,200 an ounce.",
                      BASE + " Gold closed at $1,350 an ounce.")
    figures = edit["signals"]["market_figures_changed"]
    assert "$1,200" in figures and "$1,350" in figures


def test_market_figure_signal_percent():
    edit = make_edit(BASE + " The central bank held rates at 3.5%.",
                      BASE + " The central bank held rates at 4.1%.")
    figures = edit["signals"]["market_figures_changed"]
    assert "3.5%" in figures and "4.1%" in figures


def test_plain_year_is_not_a_market_figure():
    edit = make_edit(BASE, BASE.replace("2027", "2029"))
    assert edit["signals"]["market_figures_changed"] == []
