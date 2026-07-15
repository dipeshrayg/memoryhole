"""HTML -> normalized article text. Normalization is aggressive so cosmetic
HTML churn (ads, timestamps, share widgets) never registers as an edit."""

import re
import unicodedata

import trafilatura

MAX_TEXT = 200_000  # chars; giant-page cap

# Lines that are boilerplate even when extractors let them through.
_NOISE = re.compile(
    r"^(published|updated|last (modified|updated)|posted|share (this|on)|advertisement"
    r"|related articles?|read more|sign up|subscribe|follow us|image (source|caption)"
    r"|getty images|\d+ min read)\b",
    re.IGNORECASE,
)
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line and not _NOISE.match(line):
            lines.append(line)
    return "\n".join(lines)[:MAX_TEXT]


def extract(html: str, url: str | None = None) -> dict | None:
    """Return {"title", "text"} or None if no article content was found."""
    text = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=False, favor_precision=True
    )
    title = None
    meta = trafilatura.extract_metadata(html)
    if meta:
        title = meta.title
    if not text:
        try:
            from readability import Document

            doc = Document(html)
            title = title or doc.short_title()
            text = re.sub(r"<[^>]+>", "\n", doc.summary())
            text = re.sub(r"&\w+;", " ", text)
        except Exception:
            return None
    if not text:
        return None
    text = normalize(text)
    if len(text) < 200:  # teaser/paywall/empty shell — not worth tracking
        return None
    return {"title": normalize(title or "").replace("\n", " "), "text": text}
