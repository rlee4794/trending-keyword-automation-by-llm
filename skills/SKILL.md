---
name: hk-fnb-trending
description: >
  HK F&B social media trending keyword discovery and ranking pipeline.
  Runs daily: fetches Google Trends + Instagram data via Apify, extracts
  and filters F&B keywords, normalizes against a canonical mapping,
  reviews unmatched terms via LLM, then ranks and presents weekly trends.

  Triggered by: "run trending pipeline", "hk food trends", "weekly fnb keywords",
  "trending keywords", "run social listening", "跑趨勢關鍵字", "香港餐飲趨勢",
  or any request about HK F&B trending data.
---

# HK F&B Trending Keyword Pipeline

Daily social media trending keyword pipeline for Hong Kong F&B (Food & Beverage).
Discovers, normalizes, and ranks trending food concepts from Google Trends
and Instagram hashtags.

## Quick Reference

| User says | Action |
|---|---|
| "run trending pipeline" / "run fnb trending" | Full live mode (default) |
| "show this week's trends" / "latest ranking" | Read and present `runs/latest/weekly_fnb_trending.json` |
| "run for 2026-06-20" | Live mode for a specific date |

## Project Root

```
PROJECT_ROOT = skills/../
```

All sub-skill paths are relative to `skills/` under the project root.
The main entry point is `skills/SKILL.md` (this file).

## Shared Configuration

### Date Logic

Default target date is **yesterday** (today's data is incomplete):

```bash
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)
```

If the user specifies a date, use that instead. Pass `TARGET_DATE` to every step.

### Output Directory

```
runs/YYYY-MM-DD/
├── raw/                    ← Step 1
├── extracted/              ← Step 2A
├── filtered/               ← Step 2B
├── matched_groups.json     ← Step 3 (prelim) → Step 4 (final)
├── unmatched_review_queue.csv  ← Step 3 → Step 4
├── batch_decisions/        ← Step 4
└── weekly_fnb_trending.json ← Step 5
```

### Key Assets

| Path | Purpose |
|---|---|
| `data/mappings/canonical_mapping.csv` | Core mapping table (6 columns: canonical_key, match_value, display_term, enriched_description, category, potential) |
| `config/apify_actors_v1.json` | Apify actor IDs and input templates |
| `config/instagram_scoring.json` | IG engagement weights and scoring params |
| `config/google_scoring.json` | Google volume scoring params |
| `config/ranking.json` | Platform weights, bonus, composite threshold |
| `scripts/apify_fetch.sh` | Apify actor runner |
| `scripts/normalize_raw.py` | Raw data normalizer |
| `scripts/exact_match.py` | Exact-match normalizer |
| `scripts/backfill_descriptions.py` | One-shot description backfill |

### Environment

| Variable | Required | Purpose |
|---|---|---|
| `APIFY_TOKEN` | Yes (live mode) | Apify API authentication |

---

## Pipeline Steps

Run steps in order. Read each sub-skill's SKILL.md for detailed instructions.

### Step 1 — Fetch

**Skill:** `skills/01-fetch/SKILL.md`

Fetches raw data from Apify (Google Trends + Instagram hashtags),
then normalizes into pipeline standard format.

```
Output: runs/YYYY-MM-DD/raw/google_raw.json
        runs/YYYY-MM-DD/raw/instagram_raw.json
```

### Step 2A — Extract Keywords

**Skill:** `skills/02a-extract-keywords/SKILL.md`

Extracts F&B keywords from Instagram post captions using LLM.
Adds `extracted_keywords` field to each record.

```
Input:  runs/YYYY-MM-DD/raw/instagram_raw.json
Output: runs/YYYY-MM-DD/extracted/instagram_keywords.json
```

### Step 2B — Filter F&B

**Skill:** `skills/02b-filter-fnb/SKILL.md`

Filters Google Trends terms and Instagram extracted keywords to
keep only F&B-related content.

```
Input:  runs/YYYY-MM-DD/raw/google_raw.json
        runs/YYYY-MM-DD/extracted/instagram_keywords.json
Output: runs/YYYY-MM-DD/filtered/google_filtered.json
        runs/YYYY-MM-DD/filtered/instagram_filtered.json
```

### Step 3 — Normalize (Exact Match)

**Skill:** `skills/03-normalize/SKILL.md`

Deterministic exact-match lookup against `canonical_mapping.csv`.
Groups matched terms by canonical key, writes unmatched terms to
review queue.

```
Input:  runs/YYYY-MM-DD/filtered/*.json
        data/mappings/canonical_mapping.csv
Output: runs/YYYY-MM-DD/matched_groups.json (preliminary)
        runs/YYYY-MM-DD/unmatched_review_queue.csv
```

**Decision point:** If `unmatched_review_queue.csv` has 0 pending rows,
skip Step 4 and go directly to Step 5.

### Step 4 — LLM Review

**Skill:** `skills/04-review/SKILL.md`

Agent-driven batch classification of unmatched terms (75 terms/batch).
Classifies each as CREATE / MERGE / DISCARD, expands canonical mapping,
then re-normalizes to produce final matched groups.

```
Input:  runs/YYYY-MM-DD/unmatched_review_queue.csv
        data/mappings/canonical_mapping.csv
Output: data/mappings/canonical_mapping.csv (updated)
        runs/YYYY-MM-DD/matched_groups.json (final)
        runs/YYYY-MM-DD/batch_decisions/
```

### Step 5 — Ranking (Weekly Aggregate)

**Skill:** `skills/05-ranking/SKILL.md`

Accumulates 14 days of `matched_groups.json`, splits into current-week
(T-6…T) and previous-week (T-13…T-7) windows, aggregates per canonical
key, computes per-window platform scores, compares to determine true
week-over-week trend direction, ranks, and filters.

```
Input:  runs/{T-13}/matched_groups.json … runs/{T}/matched_groups.json (14 files)
        config/instagram_scoring.json
        config/google_scoring.json
        config/ranking.json
Output: runs/YYYY-MM-DD/weekly_fnb_trending.json (schema v3.0)
```

**Cold start:** First 13 days of pipeline operation, Step 5 has < 14 days
of accumulated data. All keywords get `trend_direction = "insufficient_data"`
until both windows have ≥ 2 days of data. Ranking still works normally.

### Step 6 — Present

**Skill:** `skills/06-present/SKILL.md`

Reads the ranked output from Step 5, presents a Markdown summary table
in the conversation, and updates the `runs/latest` symlink.

```
Input:  runs/YYYY-MM-DD/weekly_fnb_trending.json
Output: runs/latest → runs/YYYY-MM-DD (symlink)
        Formatted output to user
```

---

## Execution Notes

### Step Order

Steps MUST run in order: 1 → 2A → 2B → 3 → 4 → 5 → 6.

Steps 2A and 2B are independent of each other (different inputs) and
could theoretically run in parallel, but 2B depends on 2A's output
for Instagram. Run sequentially for simplicity.

### Resume / Idempotency

- **Step 1**: Re-running overwrites raw files. Safe to re-run if Apify
  actors are still available.
- **Step 2A**: Checks `instagram_keywords.json` for existing records,
  resumes from last processed index.
- **Step 2B**: Overwrites filtered files. Idempotent.
- **Step 3**: Overwrites `matched_groups.json` and `unmatched_review_queue.csv`.
  If re-running after Step 4 modified the mapping, results will differ.
- **Step 4**: Checks `review_status` in queue. Only processes `pending` rows.
  Safe to resume after interruption. Merge step is idempotent (match_value dedup).
- **Step 5**: Overwrites `weekly_fnb_trending.json`. Idempotent. Reads
  14 days of `matched_groups.json` — re-running after a missing day
  is backfilled will produce different (more complete) results.

### Error Propagation

| Step fails | Action |
|---|---|
| Step 1 (Apify) | Abort. No data to process. |
| Step 2A (extract) | Continue with empty Instagram keywords. |
| Step 2B (filter) | Abort. Cannot normalize unfiltered data. |
| Step 3 (normalize) | Abort. Required for all downstream steps. |
| Step 4 (review) | If review fails after some batches, partial results are saved. Resume later. If cannot run at all, continue with preliminary matched_groups.json from Step 3. |
| Step 5 (ranking) | Abort if < 2 days of data in either window and no keywords pass threshold. Partial data produces results with `insufficient_data` trend direction. |
| Step 6 (present) | Non-critical. Results are saved, can present later. |

### First-Time Setup

Before the first live run:

1. **Backfill descriptions**: Run `scripts/backfill_descriptions.py` to
   add `enriched_description` to existing canonical keys. This is a one-time
   operation that upgrades `canonical_mapping.csv` from 3 to 4 columns and
   generates descriptions for all existing keys.

   ```bash
   # Phase 1: prepare
   python3 scripts/backfill_descriptions.py prepare \
     --mapping data/mappings/canonical_mapping.csv \
     --batch-size 75

   # Phase 2: Agent processes each batch file in /tmp/backfill_batches/
   # (see script output for instructions)

   # Phase 3: apply
   python3 scripts/backfill_descriptions.py apply \
     --mapping data/mappings/canonical_mapping.csv \
     --results-dir /tmp/backfill_batches
   ```

2. **Verify APIFY_TOKEN**: Ensure `APIFY_TOKEN` is set in the environment.

3. **Run pipeline**: "run trending pipeline"

---

## Dependencies

- **External API**: Apify (requires `APIFY_TOKEN`)
- **Scripts**: `scripts/apify_fetch.sh`, `scripts/normalize_raw.py`, `scripts/exact_match.py`
- **Config**: `config/instagram_scoring.json`, `config/google_scoring.json`, `config/ranking.json`, `config/apify_actors_v1.json`
- **Data**: `data/mappings/canonical_mapping.csv`
- **Sub-skills**: `skills/01-fetch/`, `skills/02a-extract-keywords/`, `skills/02b-filter-fnb/`, `skills/03-normalize/`, `skills/04-review/`, `skills/05-ranking/`
