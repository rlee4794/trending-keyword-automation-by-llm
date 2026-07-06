---
name: hk-fnb-step-05-ranking
description: >
  Step 5 of the HK F&B trending keyword pipeline.
  Accumulates 14 days of matched_groups.json, splits into two 7-day
  windows (current week vs previous week), aggregates per canonical key,
  computes per-window platform scores, compares to determine trend
  direction, ranks all keywords, and produces the weekly trending output.
---

# Step 5 — Ranking (Weekly Aggregate)

**Pipeline position:** after Step 4 (LLM Review), before Step 6 (Present).

## Purpose

Accumulates **14 days of `matched_groups.json`**, splits into two 7-day
windows, computes platform scores independently per window, compares to
determine trend direction, and ranks all keywords.

## Input

| File | Source | Content |
|------|--------|---------|
| `runs/{T-13}/matched_groups.json` … `runs/{T}/matched_groups.json` | Steps 3–4 | 14 days of matched canonical keys |
| `config/instagram_scoring.json` | Project asset | IG engagement weights |
| `config/google_scoring.json` | Project asset | Google scoring params |
| `config/ranking.json` | Project asset | Platform weights, bonus, direction thresholds |

## Output

`runs/YYYY-MM-DD/weekly_fnb_trending.json` (schema v3.0)

```json
{
  "schema_version": "3.0",
  "generated_at": "2026-07-02T17:00:00+08:00",
  "period": {
    "current_week": { "start": "...", "end": "...", "days_with_data": 7 },
    "previous_week": { "start": "...", "end": "...", "days_with_data": 6 }
  },
  "pipeline": { "mode": "live", "timezone": "Asia/Hong_Kong" },
  "keywords": [
    {
      "canonical_key": "sukiyaki",
      "display_name": "Sukiyaki",
      "raw_representative": "Sukiyaki",
      "category": "fnb",
      "potential": "high",
      "social_composite_score": 0.72,
      "trend_direction": "active",
      "platform_hits": 2,
      "rank": 1,
      "platforms": {
        "instagram": { "platform_score": 0.68, "engagement_raw": 142.5, "post_count": 44, "previous_score": 0.52 },
        "google": { "platform_score": 0.45, "volume": 62, "previous_score": 0.33 }
      }
    }
  ]
}
```

## Window Logic

Given target date T (default: yesterday):

```
current_week  = T-6  through T   (7 days)
previous_week = T-13 through T-7 (7 days)
```

For each date in the 14-day range, read `runs/{date}/matched_groups.json`.
Missing files are skipped; `days_with_data` reflects actual available days.

### Aggregation (per canonical_key, per window)

```
Per window:
  instagram: sum of current_volume, engagement_raw, record_count across all days
  google:    sum of current_volume, record_count across all days
  matched_terms: union across all days

Normalize:
  avg_post_engagement   = total_engagement / total_posts   (per-post average)
  avg_daily_volume      = total_volume / days_with_data
```

## Scoring Formulas

### Instagram — Average Per-Post Engagement

Weights from `config/instagram_scoring.json`: likes=1, comments=2, shares=4.

Per-post engagement (already computed by Step 3 in `engagement_raw`):

```
post_engagement = ln(likes + 1) + ln(comments×2 + 1) + ln(shares×4 + 1)
```

Platform score:

```
avg_post_engagement = total_engagement / total_posts
IG_score = ln(avg_post_engagement + 1) / ln(max_avg_post_engagement + 1)
```

Popular post boost (likes>1000 AND shares>500 → ×2.0) is already applied in Step 3.

### Google — Volume-Based

```
Google_score = ln(avg_daily_volume + 1) / ln(max_avg_daily_volume + 1)
```

Floor: `avg_daily_volume < min_volume_floor` → score=0.

### Composite Score (current week only)

```
composite = 0.6 × IG_score + 0.4 × Google_score + 0.1 × (platforms_with_data - 1)
```

Inclusion: `composite ≥ 0.10`.

## Trend Direction

Compare current vs previous week per platform, then take highest priority across platforms:

```
surging > new > active > declining > stable > insufficient_data
```

| Condition | Direction |
|-----------|-----------|
| `delta ≥ 0.1` AND `delta/prev ≥ 0.3` | surging |
| `delta > 0` but below surging | active |
| `delta ≤ -0.05` AND `|delta|/prev ≥ 0.2` | declining |
| Keyword not in previous week | new |
| Otherwise | stable |
| Either window < 2 days data | insufficient_data |

### Raw Term Selection

From `matched_terms`: prefer most platforms → prefer non-hashtag → fallback to `display_name`.

### Ranking

Sort by `composite_score` descending; ties by `display_name` alphabetically. Assign rank from 1.

## Procedure

```bash
python3 scripts/rank.py --date YYYY-MM-DD
```

This script handles all computation: window determination, accumulation,
scoring, direction, ranking, and output assembly. Reads config files
automatically. Writes `runs/YYYY-MM-DD/weekly_fnb_trending.json`.

## Edge Cases

| Scenario | Handling |
|----------|----------|
| < 14 days of data | Process available; `days_with_data` reflects reality |
| Either window < 2 days | All keywords → `insufficient_data` |
| Keyword in current week but not previous | `previous_score = null`, trend = `new` |
| Some dates missing | Skipped; normalize by actual day count |
| All 14 dates missing | Abort |
| All keywords below threshold | Empty `keywords: []` with metadata |

## Error Handling

| Scenario | Action |
|----------|--------|
| No `matched_groups.json` files found | Abort |
| Config files missing | Abort |
| Output directory not writable | Abort |

## Dependencies

- **Input**: `runs/{date}/matched_groups.json` (14 daily runs from Steps 3–4)
- **Config**: `config/instagram_scoring.json`, `config/google_scoring.json`, `config/ranking.json`
- **Output to Step 6**: `runs/YYYY-MM-DD/weekly_fnb_trending.json`
