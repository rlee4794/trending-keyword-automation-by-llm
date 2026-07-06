---
name: hk-fnb-trending
description: >
  HK F&B social media trending keyword discovery and ranking pipeline.
  Triggered by: "run trending pipeline", "hk food trends", "weekly fnb keywords",
  "跑趨勢關鍵字", "香港餐飲趨勢".
---

# HK F&B Trending Keyword Pipeline

Daily social media trending keyword pipeline for Hong Kong F&B.
Discovers, normalizes, and ranks trending food concepts from Google Trends
and Instagram (hashtags + curated foodie accounts).

## Quick Reference

| User says | Action |
|-----------|--------|
| "run trending pipeline" | Full live run (Steps 1–6) |
| "show this week's trends" | Read `runs/latest/weekly_fnb_trending.json` |
| "run for 2026-06-20" | Live run for specific date |

## Pipeline Flow

```
Step 1: Fetch      → Apify (Google + IG hashtags + IG users) → normalize_raw.py
Step 2A: Extract   → LLM extraction from IG captions (100/batch)
Step 2B: Filter    → LLM binary F&B classification
Step 3: Normalize  → exact_match.py (deterministic, zero LLM)
Step 4: Review     → LLM batch classify unmatched → merge → re-normalize
Step 5: Ranking    → rank.py (14-day window, scoring, comparison)
Step 6: Present    → present.py (CSV export + symlink + table)
```

Each step has its own `skills/0N-name/SKILL.md` with full procedure.

## Shared Configuration

- **Date**: default to yesterday (`date -d "yesterday" +%Y-%m-%d`)
- **Timezone**: `Asia/Hong_Kong`
- **Token**: `APIFY_TOKEN` env var required for live mode
- **Scripts**: `scripts/apify_fetch.sh`, `scripts/normalize_raw.py`, `scripts/exact_match.py`, `scripts/rank.py`, `scripts/review.py`, `scripts/present.py`

## Data Flow

```
config/apify_actors_v1.json ──→ apify_fetch.sh ──→ runs/{date}/raw/_apify/*.json
config/social_listening_v1.json ──→ normalize_raw.py ──→ runs/{date}/raw/{google,instagram}_raw.json
                                                                              │
                                          ┌─────────────────────────────────────┘
                                          ├── Step 2A: LLM extract ──→ runs/{date}/extracted/instagram_keywords.json
                                          └── Step 2B: LLM filter ──→ runs/{date}/filtered/{google,instagram}_filtered.json
                                                                                      │
                                              ┌─────────────────────────────────────────┘
                                              └── Step 3: exact_match.py ──→ matched_groups.json + unmatched_review_queue.csv
                                                                                          │
                                                  ┌─────────────────────────────────────────┘
                                                  ├── Step 4: LLM review → merge → exact_match.py --skip-unmatched
                                                  └── Step 5: rank.py ──→ weekly_fnb_trending.json
                                                                                  │
                                                                                  └── Step 6: present.py
```

## Token Optimization

Steps 2A and 4 use `sessions_spawn(task=..., thinking="low")` for LLM classification
batches. These tasks need pattern matching and classification, not deep reasoning.
`thinking=low` saves ~68K tokens per run vs `thinking=medium`.

## Key Assets

| Path | Purpose |
|------|---------|
| `data/mappings/canonical_mapping.csv` | Core mapping (canonical_key, match_value, display_term, enriched_description, category, potential) |
| `config/apify_actors_v1.json` | Apify actor IDs and input templates |
| `config/social_listening_v1.json` | Platform seeds and weights |
| `config/instagram_scoring.json` | IG engagement weights and log-normalisation params |
| `config/google_scoring.json` | Google scoring params |
| `config/ranking.json` | Platform weights, bonus, direction thresholds |

## Environment

| Variable | Purpose |
|----------|---------|
| `APIFY_TOKEN` | Apify API authentication (required for live mode) |
