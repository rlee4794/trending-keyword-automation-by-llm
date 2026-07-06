---
name: hk-fnb-step-06-present
description: >
  Step 6 of the HK F&B trending keyword pipeline.
  Reads the ranked weekly_fnb_trending.json from Step 5, exports CSVs,
  updates runs/latest symlink, and presents a summary table.
---

# Step 6 — Present

**Pipeline position:** after Step 5 (Ranking). Final step.

## Purpose

Read ranked output, export CSVs, update symlink, present summary table.

## Input

| File | Source | Content |
|------|--------|---------|
| `runs/YYYY-MM-DD/weekly_fnb_trending.json` | Step 5 | Ranked keywords (schema v3.0) |

## Output

| Artifact | Content |
|----------|---------|
| `runs/YYYY-MM-DD/weekly_fnb_trending.csv` | All keywords (CSV) |
| `runs/YYYY-MM-DD/weekly_fnb_trending_high_potential.csv` | High-potential only (CSV) |
| `runs/latest` → `runs/YYYY-MM-DD` | Symlink updated |
| Conversation message | Summary + ranking table |

## Procedure

### 1. Read and Export

```bash
python3 scripts/present.py read runs/YYYY-MM-DD
python3 scripts/present.py export runs/YYYY-MM-DD
ln -sfn runs/YYYY-MM-DD runs/latest
```

### 2. Present Results

Parse the `KW|` lines from `read` output and format into a table.

#### Header

```
✅ Pipeline done. Output: `runs/YYYY-MM-DD/weekly_fnb_trending.json`
```

#### Ranking Table

Group by `potential` and `category`:

**🔥 High-Potential** (`potential = "high"`) — show first.

**🍽️ F&B Concepts** (`category = "fnb"` or empty, `potential != "high"`)

**📍 Restaurants & Venues** (`category = "poi"`)

**🗺️ Locations** (`category = "location"`)

| # | Keyword | Score | Direction | IG Eng. | Google Vol. |
|---|---------|-------|-----------|---------|-------------|
| 1 | Cafe | 0.72 | active | 142.5 | 62 |

Columns: `rank`, `display_term`, `social_composite_score` (2dp), `trend_direction`,
`platforms.instagram.engagement_raw` (1dp), `platforms.google.volume` (integer).
Show `-` for null/zero values.

Display all keywords. If >20, show first 20 and note the rest.

### 3. Query Responses

- "show this week's trends" → read `runs/latest/weekly_fnb_trending.json`
- "trends for YYYY-MM-DD" → read `runs/YYYY-MM-DD/weekly_fnb_trending.json`
- Keyword history → compare across multiple dates

## Error Handling

| Scenario | Action |
|----------|--------|
| JSON missing | Abort |
| `keywords` empty | Present "No keywords passed threshold" |
| Symlink update fails | Non-critical, continue |
