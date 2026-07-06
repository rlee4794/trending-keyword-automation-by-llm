---
name: hk-fnb-step-06-present
description: >
  Step 6 of the HK F&B trending keyword pipeline.
  Reads the ranked weekly_fnb_trending.json from Step 5, updates the
  runs/latest symlink, and presents a summary table to the user.
  Pure read-and-present step — no data assembly.
---

# Step 6 — Present

**Pipeline position:** after Step 5 (Ranking). Final step.

## Purpose

Read the ranked output from Step 5, present a human-readable summary
table in the conversation, update the `runs/latest` symlink, and
reference the JSON file for downstream queries.

This step is **presentation only**. Step 5 already produced the complete
`weekly_fnb_trending.json`.

## Input

| File                                       | Source | Content                                                                 |
| ------------------------------------------ | ------ | ----------------------------------------------------------------------- |
| `runs/YYYY-MM-DD/weekly_fnb_trending.json` | Step 5 | Ranked keywords with scores, directions, platform metrics (schema v3.0) |

## Output

| Artifact                                                 | Content                            |
| -------------------------------------------------------- | ---------------------------------- |
| `runs/YYYY-MM-DD/weekly_fnb_trending.json`               | Full ranked output (JSON)          |
| `runs/YYYY-MM-DD/weekly_fnb_trending.csv`                | All keywords (CSV)                 |
| `runs/YYYY-MM-DD/weekly_fnb_trending_high_potential.csv` | High-potential keywords only (CSV) |
| `runs/latest` → `runs/YYYY-MM-DD`                        | Symlink updated                    |
| Conversation message                                     | Summary + ranking table            |

## Project Paths

| Path                                       | Purpose                               |
| ------------------------------------------ | ------------------------------------- |
| `runs/YYYY-MM-DD/weekly_fnb_trending.json` | Input: ranked keywords                |
| `runs/latest`                              | Symlink target (updated by this step) |

---

## Procedure

### 1. Read the JSON

```bash
python3 -c "
import json
with open('runs/YYYY-MM-DD/weekly_fnb_trending.json') as f:
    data = json.load(f)
keywords = data.get('keywords', [])
meta = data.get('meta', {})
print(f'TOTAL_KEYWORDS={len(keywords)}')
print(f'SCHEMA_VERSION={data.get(\"schema_version\")}')
print(f'GENERATED_AT={data.get(\"generated_at\")}')
print(f'PERIOD_CW_START={data.get(\"period\", {}).get(\"current_week\", {}).get(\"start\")}')
print(f'PERIOD_CW_END={data.get(\"period\", {}).get(\"current_week\", {}).get(\"end\")}')
print(f'PERIOD_CW_DAYS={data.get(\"period\", {}).get(\"current_week\", {}).get(\"days_with_data\")}')
print(f'PERIOD_PW_DAYS={data.get(\"period\", {}).get(\"previous_week\", {}).get(\"days_with_data\")}')
print(f'MODE={data.get(\"pipeline\", {}).get(\"mode\")}')
for kw in keywords:
    ig = kw.get('platforms', {}).get('instagram', {})
    goog = kw.get('platforms', {}).get('google', {})
    ig_eng = ig.get('engagement_raw')
    goog_vol = goog.get('volume')
    print(f'KW|{kw.get(\"rank\")}|{kw.get(\"display_name\")}|{kw.get(\"social_composite_score\")}|{kw.get(\"trend_direction\")}|{ig_eng}|{goog_vol}|{kw.get(\"category\", \"\")}|{kw.get(\"potential\", \"\")}')
"
```

Replace `YYYY-MM-DD` with the actual run date.

### 2. Export CSVs

Write two CSV files alongside the JSON:

```bash
python3 -c "
import json, csv

with open('runs/YYYY-MM-DD/weekly_fnb_trending.json') as f:
    data = json.load(f)

keywords = data.get('keywords', [])

# CSV 1: All keywords
fieldnames = ['rank', 'canonical_key', 'display_name', 'raw_representative', 'category', 'potential',
              'social_composite_score', 'trend_direction', 'platform_hits',
              'ig_score', 'ig_engagement_raw', 'ig_post_count', 'ig_previous_score',
              'goog_score', 'goog_volume', 'goog_previous_score']

with open('runs/YYYY-MM-DD/weekly_fnb_trending.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
    w.writeheader()
    for kw in keywords:
        ig = kw.get('platforms', {}).get('instagram', {})
        goog = kw.get('platforms', {}).get('google', {})
        row = {
            'rank': kw.get('rank'),
            'canonical_key': kw.get('canonical_key'),
            'display_name': kw.get('display_name'),
            'raw_representative': kw.get('raw_representative'),
            'category': kw.get('category'),
            'potential': kw.get('potential'),
            'social_composite_score': kw.get('social_composite_score'),
            'trend_direction': kw.get('trend_direction'),
            'platform_hits': kw.get('platform_hits'),
            'ig_score': ig.get('platform_score'),
            'ig_engagement_raw': ig.get('engagement_raw'),
            'ig_post_count': ig.get('post_count'),
            'ig_previous_score': ig.get('previous_score'),
            'goog_score': goog.get('platform_score'),
            'goog_volume': goog.get('volume'),
            'goog_previous_score': goog.get('previous_score'),
        }
        w.writerow(row)

# CSV 2: High-potential only
high_potential = [kw for kw in keywords if kw.get('potential') == 'high']
with open('runs/YYYY-MM-DD/weekly_fnb_trending_high_potential.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
    w.writeheader()
    for kw in high_potential:
        ig = kw.get('platforms', {}).get('instagram', {})
        goog = kw.get('platforms', {}).get('google', {})
        row = {
            'rank': kw.get('rank'),
            'canonical_key': kw.get('canonical_key'),
            'display_name': kw.get('display_name'),
            'raw_representative': kw.get('raw_representative'),
            'category': kw.get('category'),
            'potential': kw.get('potential'),
            'social_composite_score': kw.get('social_composite_score'),
            'trend_direction': kw.get('trend_direction'),
            'platform_hits': kw.get('platform_hits'),
            'ig_score': ig.get('platform_score'),
            'ig_engagement_raw': ig.get('engagement_raw'),
            'ig_post_count': ig.get('post_count'),
            'ig_previous_score': ig.get('previous_score'),
            'goog_score': goog.get('platform_score'),
            'goog_volume': goog.get('volume'),
            'goog_previous_score': goog.get('previous_score'),
        }
        w.writerow(row)

print(f'CSV all: {len(keywords)} rows')
print(f'CSV high-potential: {len(high_potential)} rows')
"
```

### 3. Update Symlink

```bash
ln -sfn runs/YYYY-MM-DD runs/latest
```

This makes `runs/latest/weekly_fnb_trending.json` always point to the
most recent run, enabling simple "show me this week's trends" queries.

### 4. Present Results

Format the output as follows:

#### Header

```
✅ Pipeline done. Output: `runs/YYYY-MM-DD/weekly_fnb_trending.json`
```

#### Funnel summary

Show the pipeline throughput if available in `meta`:

```
{total_candidates} candidates → {total_ranked} ranked
```

#### Ranking Table (Markdown)

**🔥 High-Potential Keywords** (`potential = "high"`)

Show these first — they are specific, interesting signals worth paying attention to.

| #   | Keyword | Score | Direction | IG Eng. | Google Vol. |
| --- | ------- | ----- | --------- | ------- | ----------- |
| 5   | 壽喜燒  | 0.55  | surging   | 210.3   | 62          |
| 12  | 酸辣粉  | 0.48  | active    | 142.5   | 0           |
| ... | ...     | ...   | ...       | ...     | ...         |

Then group remaining keywords by `category`:

**🍽️ F&B Concepts** (`category = "fnb"` or empty, `potential != "high"`)

| #   | Keyword | Score | Direction | IG Eng. | Google Vol. |
| --- | ------- | ----- | --------- | ------- | ----------- |
| 1   | Cafe    | 0.72  | active    | 142.5   | 62          |
| 2   | 日本菜  | 0.65  | new       | 98.3    | 0           |
| ... | ...     | ...   | ...       | ...     | ...         |

**📍 Restaurants & Venues** (`category = "poi"`)

| #   | Keyword | Score | Direction | IG Eng. | Google Vol. |
| --- | ------- | ----- | --------- | ------- | ----------- |
| 1   | 壽司郎  | 0.58  | surging   | 210.3   | 85          |
| ... | ...     | ...   | ...       | ...     | ...         |

**🗺️ Locations** (`category = "location"`)

| #   | Keyword  | Score | Direction | IG Eng. | Google Vol. |
| --- | -------- | ----- | --------- | ------- | ----------- |
| 1   | 諾士佛臺 | 0.42  | active    | 55.1    | 30          |
| ... | ...      | ...   | ...       | ...     | ...         |

If a category section has no keywords, skip it.
Within each section, maintain the global rank numbers.

Column definitions:

| Column      | JSON path                                       | Format           | Notes                                                           |
| ----------- | ----------------------------------------------- | ---------------- | --------------------------------------------------------------- |
| #           | `keywords[].rank`                               | integer          | 1-based, global                                                 |
| Keyword     | `keywords[].display_name`                       | string           |                                                                 |
| Score       | `keywords[].social_composite_score`             | float, 2 decimal |                                                                 |
| Direction   | `keywords[].trend_direction`                    | string           | new / surging / active / stable / declining / insufficient_data |
| IG Eng.     | `keywords[].platforms.instagram.engagement_raw` | float, 1 decimal | `-` if null or 0                                                |
| Google Vol. | `keywords[].platforms.google.volume`            | integer          | `-` if null or 0                                                |

Display all ranked keywords. If the list is long (>20), show the first 20
and note how many more exist.

#### JSON Reference

End with:

```
Full data: `runs/YYYY-MM-DD/weekly_fnb_trending.json`
```

### 5. Responding to Trend Queries

When the user asks about trends (e.g. "show this week's trends",
"latest ranking", "what's trending"), read `runs/latest/weekly_fnb_trending.json`
and present the same table format.

When the user asks about a specific date, read `runs/YYYY-MM-DD/weekly_fnb_trending.json`.

When the user asks about a keyword's history, read multiple JSON files
and compare `social_composite_score` and `trend_direction` across dates.

---

## Error Handling

| Scenario                           | Action                                                |
| ---------------------------------- | ----------------------------------------------------- |
| `weekly_fnb_trending.json` missing | Abort. Step 5 must complete first.                    |
| `keywords` array is empty          | Present "No keywords passed threshold" with metadata. |
| JSON parse fails                   | Abort. Report the error.                              |
| Symlink update fails               | Non-critical. Continue with presentation.             |

---

## Token Budget

| Item                    | Estimate       |
| ----------------------- | -------------- |
| JSON read (21 keywords) | ~3K tokens     |
| Table formatting        | ~1K tokens     |
| **Total**               | **~4K tokens** |

---

## Dependencies

- **Input from Step 5**: `runs/YYYY-MM-DD/weekly_fnb_trending.json`
