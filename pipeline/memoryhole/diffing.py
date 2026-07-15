"""Word-level diff between two snapshots, plus rule-based signals the
classifier consumes (number changes, entity swaps, quote deletions, block
adds/removes, headline changes)."""

import re
from difflib import SequenceMatcher

CONTEXT = 12  # words of context around each change
BLOCK = 30  # contiguous words that count as an added/removed paragraph

_NUM = re.compile(r"\d(?:[\d,.]*\d)?")  # ends on a digit: "2,027" yes, "2027." no
_QUOTE = re.compile(r'"[^"]{20,}"')
# Two+ capitalized words in a row ≈ a named entity (heuristic, no NER model).
_ENTITY = re.compile(r"\b(?:[A-Z][a-z]+ ){1,3}[A-Z][a-z]+\b")


def word_diff(old: str, new: str) -> list[dict]:
    """Return hunks: [{"ops": [[tag, text], ...]}] where tag is eq|del|ins.
    Equal runs longer than 2*CONTEXT words are trimmed to context, closing
    the current hunk and opening the next."""
    a, b = old.split(), new.split()
    hunks: list[dict] = []
    ops: list[list[str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            run = a[i1:i2]
            if len(run) > 2 * CONTEXT:
                if ops:
                    ops.append(["eq", " ".join(run[:CONTEXT])])
                    hunks.append({"ops": ops})
                    ops = []
                ops.append(["eq", " ".join(run[-CONTEXT:])])
            else:
                ops.append(["eq", " ".join(run)])
        else:
            if tag in ("replace", "delete"):
                ops.append(["del", " ".join(a[i1:i2])])
            if tag in ("replace", "insert"):
                ops.append(["ins", " ".join(b[j1:j2])])
    if any(op[0] != "eq" for op in ops):
        hunks.append({"ops": ops})
    # First hunk may start with a leading full-length equal run; trim it.
    for h in hunks:
        if h["ops"] and h["ops"][0][0] == "eq":
            words = h["ops"][0][1].split()
            h["ops"][0][1] = " ".join(words[-CONTEXT:])
    return hunks


def signals(edit: dict, hunks: list[dict]) -> dict:
    deleted = " ".join(t for h in hunks for tag, t in h["ops"] if tag == "del")
    inserted = " ".join(t for h in hunks for tag, t in h["ops"] if tag == "ins")
    old_words = edit["old_text"].split()
    changed = len(deleted.split()) + len(inserted.split())

    # Cosmetic check: identical after stripping everything but letters/digits.
    strip = re.compile(r"[^\w]+", re.UNICODE)
    cosmetic = strip.sub("", edit["old_text"]).lower() == strip.sub(
        "", edit["new_text"]
    ).lower() and strip.sub("", edit["old_title"]).lower() == strip.sub(
        "", edit["new_title"]
    ).lower()

    old_nums, new_nums = set(_NUM.findall(deleted)), set(_NUM.findall(inserted))
    del_entities = set(_ENTITY.findall(deleted)) - set(_ENTITY.findall(inserted))
    ins_entities = set(_ENTITY.findall(inserted)) - set(_ENTITY.findall(deleted))
    blocks_removed = sum(
        1 for h in hunks for tag, t in h["ops"] if tag == "del" and len(t.split()) >= BLOCK
    )
    blocks_added = sum(
        1 for h in hunks for tag, t in h["ops"] if tag == "ins" and len(t.split()) >= BLOCK
    )
    title_changed = strip.sub("", edit["old_title"]).lower() != strip.sub(
        "", edit["new_title"]
    ).lower()

    return {
        "cosmetic_only": cosmetic,
        "change_ratio": round(changed / max(len(old_words), 1), 4),
        "numbers_changed": sorted(old_nums ^ new_nums)[:20],
        "entities_swapped": bool(del_entities and ins_entities),
        "quotes_deleted": len(_QUOTE.findall(deleted)),
        "blocks_added": blocks_added,
        "blocks_removed": blocks_removed,
        "title_changed": title_changed,
    }


def run_diff(store) -> int:
    """Compute hunks+signals for every edit record that lacks them."""
    done = 0
    for edit in store.edits():
        if "hunks" in edit:
            continue
        hunks = word_diff(edit["old_text"], edit["new_text"])
        edit["hunks"] = hunks
        edit["signals"] = signals(edit, hunks)
        store.write_edit(edit)
        done += 1
    return done
