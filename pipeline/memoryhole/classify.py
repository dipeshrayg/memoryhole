"""Severity classification: rule-based signals weighted together with local
semantic similarity (sentence-transformers). If LLM_API_KEY is set, an LLM
adjudicates borderline FACTUAL vs NARRATIVE calls; otherwise rules decide."""

import json
import logging
import os

log = logging.getLogger("memoryhole")

SEVERITIES = ["COSMETIC", "MINOR", "FACTUAL", "NARRATIVE"]
_model = None


def get_similarity_fn():
    """Return f(old_text, new_text) -> cosine similarity, or None when the
    local model is unavailable (rules still classify on their own)."""
    if os.environ.get("MEMORYHOLE_NO_EMBED"):
        return None
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:
            log.info("no embedding model (%s); using rules only", exc)
            return None

    def similarity(old: str, new: str) -> float:
        emb = _model.encode([old[:5000], new[:5000]], normalize_embeddings=True)
        return float(emb[0] @ emb[1])

    return similarity


def score_edit(edit: dict, similarity_fn=None) -> dict:
    """Return {"severity", "score", "similarity", "adjudicated_by"}."""
    s = edit["signals"]
    if s["cosmetic_only"]:
        return {"severity": "COSMETIC", "score": 0.0, "similarity": 1.0,
                "adjudicated_by": "rules"}

    sim = None
    if similarity_fn:
        try:
            sim = round(similarity_fn(edit["old_text"], edit["new_text"]), 4)
        except Exception as exc:
            log.warning("similarity failed for %s: %s", edit["id"], exc)
    # Semantic shift: 0 when texts mean the same, grows as similarity drops.
    # Without a model, change_ratio stands in (crude but directionally right).
    shift = max(0.0, (0.97 - sim) * 6) if sim is not None else min(1.0, s["change_ratio"] * 3)

    factual = 0.6 * bool(s["numbers_changed"]) + 0.5 * s["entities_swapped"]
    narrative = (
        0.7 * s["title_changed"]
        + 0.45 * min(s["blocks_added"] + s["blocks_removed"], 2)
        + 0.5 * min(s["quotes_deleted"], 2)
        + min(shift, 1.0)
    )
    score = round(max(factual, narrative), 3)

    if score < 0.35:
        severity = "MINOR" if s["change_ratio"] >= 0.002 else "COSMETIC"
    elif factual >= narrative:
        severity = "FACTUAL"
    else:
        severity = "NARRATIVE"

    result = {"severity": severity, "score": score,
              "similarity": sim, "adjudicated_by": "rules"}

    borderline = (
        severity in ("FACTUAL", "NARRATIVE")
        and abs(factual - narrative) < 0.15
        and factual > 0.3
        and narrative > 0.3
    )
    if borderline and os.environ.get("LLM_API_KEY"):
        verdict = llm_adjudicate(edit)
        if verdict:
            result.update(severity=verdict, adjudicated_by="llm")
    return result


def llm_adjudicate(edit: dict) -> str | None:
    """Ask an OpenAI-compatible endpoint (default: Groq free tier) whether a
    borderline edit is FACTUAL or NARRATIVE. Any failure -> None (rules win)."""
    import requests

    url = os.environ.get("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions")
    model = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
    changes = json.dumps(edit["hunks"][:5])[:4000]
    prompt = (
        "A published article was silently edited. FACTUAL means facts changed "
        "(numbers, names, dates). NARRATIVE means claims were added/removed or the "
        "framing/meaning shifted. Reply with exactly one word: FACTUAL or NARRATIVE.\n"
        f"Old headline: {edit['old_title']}\nNew headline: {edit['new_title']}\n"
        f"Changes: {changes}"
    )
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
            json={"model": model, "max_tokens": 5,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        r.raise_for_status()
        word = r.json()["choices"][0]["message"]["content"].strip().upper()
        return word if word in ("FACTUAL", "NARRATIVE") else None
    except Exception as exc:
        log.warning("LLM adjudication failed: %s", exc)
        return None


def run_classify(store) -> int:
    """Classify every edit record that has signals but no severity yet."""
    pending = [e for e in store.edits() if "signals" in e and "severity" not in e]
    if not pending:
        return 0
    similarity_fn = get_similarity_fn()
    for edit in pending:
        edit.update(score_edit(edit, similarity_fn))
        store.write_edit(edit)
    return len(pending)
