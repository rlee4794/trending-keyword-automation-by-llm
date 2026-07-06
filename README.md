# Trending Keyword Automation By LLM

HK F&B social media trending keyword discovery and ranking pipeline.
Runs daily via OpenClaw agent-driven pipeline: fetches Google Trends +
Instagram (hashtags + curated foodie accounts) data via Apify, extracts
and filters F&B keywords, normalizes against a canonical mapping,
reviews unmatched terms via LLM, then ranks and presents weekly trends.

## Architecture

The pipeline is **OpenClaw agent-driven** — the agent orchestrates each
step by reading skill files, executing shell/Python scripts, and
performing LLM classification where needed. No monolithic Python CLI.

```
skills/SKILL.md          ← Main entry point
├── skills/01-fetch/        Step 1: Apify fetch + normalize
├── skills/02a-extract-keywords/  Step 2A: IG keyword extraction (LLM)
├── skills/02b-filter-fnb/        Step 2B: F&B binary filter (LLM)
├── skills/03-normalize/          Step 3: Exact-match normalization
├── skills/04-review/             Step 4: LLM review of unmatched terms
├── skills/05-ranking/            Step 5: Weekly ranking (14-day window)
└── skills/06-present/            Step 6: Present results
```

## Data Sources

| Source | Method | Actor / Details |
|--------|--------|-----------------|
| Google Trends | Apify | `data_xplorer~google-trends-trending-now` |
| IG Hashtags | Apify | 4 hashtags: #hkfood, #hkfoodie, #香港美食, #相機食先 |
| IG Users | Apify | 10 curated HK foodie accounts (see config) |
| Threads | Config only | Actor configured, not yet wired into pipeline |

## Key Assets

| Path | Purpose | Size |
|------|---------|------|
| `data/mappings/canonical_mapping.csv` | Core mapping table (6 columns: canonical_key, match_value, display_term, enriched_description, category, potential) | ~1,134 rows |
| `scripts/apify_fetch.sh` | Apify actor runner (trigger → poll → download) | Shell |
| `scripts/normalize_raw.py` | Apify raw → pipeline format + cross-day dedup + age filter | Python |
| `scripts/exact_match.py` | Deterministic canonical mapping lookup | Python |
| `scripts/backfill_descriptions.py` | One-shot enriched_description backfill | Python |
| `config/apify_actors_v1.json` | Apify actor IDs and input templates | JSON |
| `config/social_listening_v1.json` | Platform seeds, weights, thresholds | JSON |
| `config/instagram_scoring.json` | IG engagement weights and log-normalisation params | JSON |
| `config/google_scoring.json` | Google scoring params | JSON |
| `config/ranking.json` | Platform weights, bonus, trend direction thresholds | JSON |

## Pipeline Steps

### Step 1 — Fetch
15 parallel Apify actor runs (1 Google Trends + 4 IG hashtags + 10 IG users),
then `normalize_raw.py` merges and normalizes into `google_raw.json` and
`instagram_raw.json` with cross-day dedup (6-day lookback) and 30-day age filter.

### Step 2A — Extract Keywords (LLM)
Extracts up to 8 F&B keywords per Instagram caption. Batch size: 100 posts.
Resume-safe: skips already-processed records on restart.

### Step 2B — Filter F&B (LLM)
Binary classification of all candidate terms (Google + Instagram) as F&B or
non-F&B. Fail-open: keeps all terms if classification fails.

### Step 3 — Normalize (Exact Match)
Deterministic lookup against `canonical_mapping.csv`. Matched terms grouped
by canonical key. Unmatched terms queued for Step 4. Zero LLM tokens.

### Step 4 — LLM Review
Batch classification of unmatched terms (75/batch): CREATE (new concept),
MERGE (alias for existing key), or DISCARD (noise). Expands mapping, then
re-normalizes to produce final `matched_groups.json`.

### Step 5 — Ranking
Accumulates 14 days of `matched_groups.json`, splits into current-week
(T-6…T) and previous-week (T-13…T-7) windows, computes per-window platform
scores, compares to determine trend direction, ranks by composite score.

**Scoring:** Instagram 60% + Google 40% + 0.1 dual-platform bonus.
**Threshold:** composite score ≥ 0.10 for inclusion.

### Step 6 — Present
Reads `weekly_fnb_trending.json`, updates `runs/latest` symlink, exports
CSV files, presents formatted summary.

## Output

| Artifact | Path |
|----------|------|
| Weekly ranked JSON | `runs/YYYY-MM-DD/weekly_fnb_trending.json` (schema v3.0) |
| Full CSV | `runs/YYYY-MM-DD/weekly_fnb_trending.csv` |
| High-potential CSV | `runs/YYYY-MM-DD/weekly_fnb_trending_high_potential.csv` |
| Latest symlink | `runs/latest` → `runs/YYYY-MM-DD` |

## Current Status

| Metric | Value |
|--------|-------|
| Latest run | 2026-07-05 |
| Accumulated runs | 11 days (2026-06-23 → 2026-07-05) |
| Keywords ranked | 242 |
| Score range | 0.10 – 0.73 |
| Canonical mapping | 1,134 rows |
| Trend directions | Mostly `new` (cold start — previous-week window still filling) |

## Environment

| Variable | Required | Purpose |
|----------|----------|---------|
| `APIFY_TOKEN` | Yes (live mode) | Apify API authentication |

## Quick Reference

| User says | Action |
|-----------|--------|
| "run trending pipeline" | Full live run (Steps 1–6) |
| "show this week's trends" | Read `runs/latest/weekly_fnb_trending.json` |
| "run for 2026-06-20" | Live run for a specific date |
