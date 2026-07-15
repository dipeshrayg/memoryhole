# Architecture

## Design principles

- **Git-as-database.** Normalized article text lives as plain files under
  `data/snapshots/<domain>/<url-hash>.txt`, committed daily by the Action. Git history
  is the full archive; no external storage. Metadata (URL → id, title, content hash,
  first/last seen, language, status) lives in `data/snapshots/index.json`.
- **Everything derived is a file.** `data/derived/edits/*.json` (one per detected edit),
  `data/derived/site.json` (everything the frontend needs), `data/derived/health.json`
  (machine-readable run status). The frontend never fetches at runtime.
- **Idempotent stages.** Each CLI stage picks up exactly the work the previous stage
  left and skips what is already done. Edit IDs are `urlhash-oldhash-newhash`, so
  re-running a day can never duplicate an edit.
- **One failing source never fails the run.** Every source and every page fetch is
  individually try/except-ed; failures land in `health.json` and the run continues.

## Pipeline stages (`pipeline/memoryhole/`)

| Stage | Module | In | Out |
|---|---|---|---|
| `fetch` | `fetch.py` | sources.yaml, index.json | snapshots, pending edit records (old+new text), health.json |
| `diff` | `diffing.py` | edit records without `hunks` | word-level hunks + rule signals |
| `classify` | `classify.py` | edit records without `severity` | severity, score, similarity |
| `publish` | `publish.py` | classified edits + index | site.json, health.json |

`run-all` chains the four. Each stage is a pure function over the `Store`
(`store.py`), which is the only component that touches the filesystem.

### Fetch details

- URLs are discovered from RSS feeds (`max_articles` newest per run). Each adopted
  article is re-checked daily for `track_days` days after first seen (articles
  stabilize; unbounded re-checking would grow the run forever). Static `url:` sources
  are re-checked forever.
- robots.txt honored per domain (`urllib.robotparser`), honest User-Agent, ≥2s
  between requests to the same domain, 20s timeout.
- 404/410 → article marked `retired` (kept in the archive, no longer fetched).
- Extraction: trafilatura (`favor_precision`), fallback readability-lxml. Normalization
  (NFKC, quote/dash folding, whitespace collapse, boilerplate-line removal, 200KB cap)
  makes snapshots immune to cosmetic HTML churn.
- Pages whose text collapses to a stub (< 500 chars and < 40% of previous length) are
  ignored as suspected paywalls/errors, not treated as edits.
- Content is compared by hash of (title + text); an edit record captures both old and
  new text at detection time, so the diff stage needs no git archaeology.

### Severity model

Rule signals from the word diff — numbers changed, entity swaps (capitalized-sequence
heuristic), quote deletions, ≥30-word blocks added/removed, headline changes — are
weighted into `factual` and `narrative` scores. Semantic similarity (local
sentence-transformers all-MiniLM-L6-v2, cosine of full-text embeddings) feeds the
narrative score; when the model is unavailable the change ratio stands in.

- normalized-identical text → `COSMETIC`
- `max(factual, narrative) < 0.35` → `MINOR` (or `COSMETIC` for near-zero change)
- otherwise the larger of the two wins → `FACTUAL` / `NARRATIVE`

The classifier is pluggable: if `LLM_API_KEY` is set, borderline FACTUAL-vs-NARRATIVE
cases (scores within 0.15) are adjudicated by an OpenAI-compatible endpoint
(default: Groq free tier, override with `LLM_API_URL`/`LLM_MODEL`). Any LLM failure
falls back to the rule verdict. Set `MEMORYHOLE_NO_EMBED=1` to skip the local model
(used by tests).

## Frontend (`site/`)

Astro, fully static, zero client-side JS. Reads `data/derived/site.json` and the
per-edit JSONs at **build time** only. Pages: `/` (feed grouped by day, ranked by
severity; per-source table), `/edit/[id]` (side-by-side word diff: red strikethrough
deletions, green insertions; signal table), `/source/[domain]` (per-outlet stats and
history), `/about` (methodology), `/rss.xml` (NARRATIVE + FACTUAL edits). Dark mode
via `prefers-color-scheme`. `SITE_URL`/`BASE_PATH` env vars set by the workflow make
project-page URLs work.

## Automation (`.github/workflows/`)

- **daily.yml** — 06:00 UTC cron + manual dispatch. checkout → pip/HF caches →
  `memoryhole run-all` → commit `data/` (`[skip ci]`) → `astro build` → deploy to
  Pages. A concurrency group prevents overlapping runs.
- **ci.yml** — PRs and pushes: ruff, pytest, astro build. CI installs the pipeline
  *without* the ML extra (tests are rule-based and offline), keeping CI ~1 minute.
