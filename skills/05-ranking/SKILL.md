---
name: hk-fnb-step-05-ranking
description: >
  Step 5 of the HK F&B trending keyword pipeline.
  Accumulates 14 days of matched_groups.json, splits into two 7-day
  windows (current week vs previous week), aggregates per canonical key,
  computes per-window platform scores, compares to determine trend
  direction, ranks all keywords, and produces the weekly trending output.

  All computation is Agent-driven. The Agent uses short Python one-liners
  for log/float ops (via python3 -c) and writes the output JSON — no
  standalone Python scripts needed.
---

# Step 5 — Ranking (Weekly Aggregate)

**Pipeline position:** after Step 4 (LLM Review), before Step 6 (Present).

## Purpose

Instead of comparing against a previous pipeline run, this step accumulates
**14 days of `matched_groups.json`** (one per daily run), splits them into two
7-day windows, aggregates per canonical key within each window, computes
platform scores independently for each window, then compares the two windows
to determine true week-over-week trend direction.

## Input

| File                                                               | Source            | Content                                            |
| ------------------------------------------------------------------ | ----------------- | -------------------------------------------------- |
| `runs/{T-13}/matched_groups.json` … `runs/{T}/matched_groups.json` | Steps 3–4 (daily) | 14 days of matched canonical keys                  |
| `config/instagram_scoring.json`                                    | Project asset     | IG engagement weights and log normalisation params |
| `config/google_scoring.json`                                       | Project asset     | Google scoring params                              |
| `config/ranking.json`                                              | Project asset     | Platform weights, bonus, direction thresholds      |

## Output

`runs/YYYY-MM-DD/weekly_fnb_trending.json`

```json
{
  "schema_version": "3.0",
  "generated_at": "2026-07-02T17:00:00+08:00",
  "period": {
    "current_week": {
      "start": "2026-06-26T00:00:00+08:00",
      "end": "2026-07-02T23:59:59+08:00",
      "days_with_data": 7
    },
    "previous_week": {
      "start": "2026-06-19T00:00:00+08:00",
      "end": "2026-06-25T23:59:59+08:00",
      "days_with_data": 6
    }
  },
  "pipeline": {
    "mode": "live",
    "timezone": "Asia/Hong_Kong"
  },
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
        "instagram": {
          "platform_score": 0.68,
          "engagement_raw": 142.5,
          "post_count": 44,
          "previous_score": 0.52
        },
        "google": {
          "platform_score": 0.45,
          "volume": 62,
          "previous_score": 0.33
        }
      }
    }
  ]
}
```

**Key changes from schema v2.0:**

- `period` now contains `current_week` and `previous_week` with `days_with_data`
- `previous_score` is computed from the previous-week window aggregate, not from a prior pipeline run
- New trend direction: `insufficient_data` (when either window has < 2 days of data)

---

## Window Logic

### Date Ranges

Given target date T (default: yesterday):

```
current_week  = T-6  through T   (7 days)
previous_week = T-13 through T-7 (7 days)
```

### Accumulation

For each date in the 14-day range, read `runs/{date}/matched_groups.json`.
If the file is missing or empty, skip that date (it counts as 0 `days_with_data`).

### Aggregation (per canonical_key, per window)

For each canonical key found in any day's `matched_groups.json`:

```
Per window:
  instagram:
    total_volume      = sum of current_volume across all days
    total_engagement  = sum of engagement_raw across all days
    total_posts       = sum of record_count across all days
    merged_engagement_details = concatenate engagement_details from all days
    merged_matched_terms      = union of matched_terms from all days
  google:
    total_volume      = sum of current_volume across all days
    total_records     = sum of record_count across all days
```

Then normalize by day count:

```
avg_daily_volume      = total_volume      / days_with_data
avg_daily_engagement  = total_engagement  / days_with_data
avg_daily_posts       = total_posts       / days_with_data
```

This ensures fair comparison between windows even when some days are missing.

---

## Scoring Formulas

Scoring runs **independently for each window**. The formulas are identical;
only the input data differs.

### Instagram — Engagement-Based

Weights from `config/instagram_scoring.json`:

```
w_likes    = 1
w_comments = 2
w_shares   = 4
```

Per-post engagement (natural log):

```
post_engagement = ln(w_likes × likes + 1)
                + ln(w_comments × comments + 1)
                + ln(w_shares × shares + 1)
```

**Popular post boost** (applied in Step 3, configured in `instagram_scoring.json`):
posts where `likes > threshold_likes` AND `shares > threshold_shares` get their
`post_engagement` multiplied by `weight_multiplier` (default 2.0×). This rewards
viral content without discarding non-viral signal.

The boosted `post_engagement` is already reflected in `engagement_raw` by the
time Step 5 reads `matched_groups.json`. Each `engagement_detail` includes a
`popular` boolean flag for traceability.

Total keyword engagement = sum of `post_engagement` across all posts
matching that canonical key **within this window**.

Platform score (log-normalised across all keywords in this window):

```
IG_platform_score = ln(engagement_raw + 1) / ln(max_engagement_raw + 1)
```

where `max_engagement_raw` is the highest `engagement_raw` across ALL
canonical keys **in this window**.

If a keyword has no Instagram data in this window, `platform_score = 0`.

### Google Trends — Volume-Based

`avg_daily_volume` is the average daily search volume across the window.

Platform score (log-normalised across all keywords in this window):

```
Google_platform_score = ln(avg_daily_volume + 1) / ln(max_avg_daily_volume + 1)
```

where `max_avg_daily_volume` is the highest `avg_daily_volume` across ALL
canonical keys for the Google platform **in this window**.

If `avg_daily_volume < min_volume_floor` (from `config/google_scoring.json`),
treat as `platform_score = 0`.

If a keyword has no Google data in this window, `platform_score = 0`.

### Composite Score

From `config/ranking.json`:

```
platform_weights:
  instagram = 0.6
  google    = 0.4

dual_platform_bonus = 0.1  (additive, per extra platform)
```

Composite score is computed on the **current week** window only:

```
extra_platforms  = platforms_with_data_in_current_week - 1
composite_score  = (0.6 × IG_score_current) + (0.4 × Google_score_current)
                 + (0.1 × extra_platforms)
```

- Single platform (IG only): max = 0.6
- Single platform (Google only): max = 0.4
- Dual platform: max = 1.1

### Inclusion Threshold

Only keywords with `composite_score ≥ 0.10` are included in the output.
Keywords below this threshold are discarded (noise filtering).

---

## Trend Direction

Compare `current_week` platform score against `previous_week` platform score.
**Both are computed from accumulated matched_groups.json data within this run** —
no cross-run dependency.

### Data Sufficiency Check (applied first)

For each keyword, check both windows:

```
If current_week.days_with_data  < 2  OR  previous_week.days_with_data < 2
  → trend_direction = "insufficient_data"
  → skip per-platform direction computation
```

### Per-Platform Direction

For each platform independently:

| Condition                                        | Direction |
| ------------------------------------------------ | --------- | ----------------------- | ----------- |
| Keyword not present in previous week at all      | `new`     |
| `delta ≥ 0.1` AND `delta / previous_score ≥ 0.3` | `surging` |
| `delta > 0` but does not meet surging thresholds | `active`  |
| `delta ≤ -0.05` AND `                            | delta     | / previous_score ≥ 0.2` | `declining` |
| Otherwise                                        | `stable`  |

Where `delta = current_score - previous_score`.

### Keyword-Level Direction

The keyword-level `trend_direction` is the **highest-priority** direction
across all its platforms, using this priority order:

```
surging > new > active > declining > stable > insufficient_data
```

Simply pick the platform direction with the highest priority.
Example: IG=new + Google=active → `new` (because new > active).
Example: IG=surging + Google=declining → `surging`.
All platforms `insufficient_data` → `insufficient_data`.

### Raw Term

Select the best surface term from the merged `matched_terms` across the
**current week** window.

Priority rules (in order):

1. **Most platforms seen** — count how many platforms the term appears on
2. **Prefer non-hashtag** — a plain term beats a `#hashtag` form
3. **Fall back to `display_name`** — if no matched_terms exist

### Rank

Sort all included keywords by `social_composite_score` descending.
Assign `rank` starting from 1.

If two keywords have the same composite score, sort by `display_name`
alphabetically for deterministic ordering.

---

## Project Paths

All paths are relative to the project root.

| Path                                       | Purpose                             |
| ------------------------------------------ | ----------------------------------- |
| `runs/{date}/matched_groups.json`          | Input: 14 days of matched groups    |
| `config/instagram_scoring.json`            | IG engagement weights               |
| `config/google_scoring.json`               | Google scoring params               |
| `config/ranking.json`                      | Platform weights, bonus, thresholds |
| `runs/YYYY-MM-DD/weekly_fnb_trending.json` | Output: ranked keywords             |

---

## Procedure

### 1. Load Configuration

Read all three config files:

```bash
cat config/instagram_scoring.json
cat config/google_scoring.json
cat config/ranking.json
```

Note the values:

- `engagement_weights`: likes/comments/shares multipliers
- `platform_weights`: IG and Google weight
- `dual_platform_bonus`: additive bonus per extra platform
- `composite_score_threshold`: minimum score to be included (default 0.10)
- `trend_direction.surging`: `min_absolute_delta`, `min_relative_delta`
- `trend_direction.declining`: `min_absolute_delta`, `min_relative_delta`

### 2. Determine Target Date and Windows

Default to **yesterday** (same date as Step 1):

```bash
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)
```

Compute the 14-day window:

```bash
python3 -c "
from datetime import date, timedelta

T = date.today() - timedelta(days=1)  # yesterday

current_week  = [(T - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
previous_week = [(T - timedelta(days=i)).isoformat() for i in range(13, 6, -1)]

print(f'TARGET_DATE={T.isoformat()}')
print(f'CURRENT_WEEK_START={current_week[0]}')
print(f'CURRENT_WEEK_END={current_week[-1]}')
print(f'PREVIOUS_WEEK_START={previous_week[0]}')
print(f'PREVIOUS_WEEK_END={previous_week[-1]}')
print(f'ALL_DATES={\" \".join(previous_week + current_week)}')
"
```

### 3. Accumulate matched_groups.json Across 14 Days

```bash
python3 -c "
import json, os
from collections import defaultdict

ALL_DATES = 'PREVIOUS_WEEK_DATES CURRENT_WEEK_DATES'.split()
# e.g. ['2026-06-19', '2026-06-20', ..., '2026-07-02']

# Determine window membership
T = 'TARGET_DATE'
cw_start_idx = 7  # previous_week has 7 dates, current_week starts at index 7

# Accumulate: window -> canonical_key -> platform -> fields
windows = {
    'current_week':  {'days_with_data': 0, 'keys': defaultdict(lambda: defaultdict(dict))},
    'previous_week': {'days_with_data': 0, 'keys': defaultdict(lambda: defaultdict(dict))},
}

for i, date_str in enumerate(ALL_DATES):
    path = f'runs/{date_str}/matched_groups.json'
    if not os.path.exists(path):
        continue

    window = 'current_week' if i >= 7 else 'previous_week'
    windows[window]['days_with_data'] += 1

    with open(path) as f:
        data = json.load(f)

    for ck, v in data.items():
        wk = windows[window]['keys'][ck]
        wk['display_name'] = v.get('display_name', ck)
        wk['enriched_description'] = v.get('enriched_description', '')
        wk['category'] = v.get('category', '')
        wk['potential'] = v.get('potential', '')

        # Merge matched_terms
        if 'matched_terms' not in wk:
            wk['matched_terms'] = {}
        for term, tinfo in v.get('matched_terms', {}).items():
            if term not in wk['matched_terms']:
                wk['matched_terms'][term] = {'platforms': [], 'is_hashtag': tinfo.get('is_hashtag', False)}
            for p in tinfo.get('platforms', []):
                if p not in wk['matched_terms'][term]['platforms']:
                    wk['matched_terms'][term]['platforms'].append(p)

        # Aggregate Instagram
        ig = v.get('platforms', {}).get('instagram', {})
        if ig:
            if 'instagram' not in wk:
                wk['instagram'] = {'current_volume': 0, 'record_count': 0, 'engagement_raw': 0, 'engagement_details': []}
            wk['instagram']['current_volume'] += ig.get('current_volume', 0) or 0
            wk['instagram']['record_count'] += ig.get('record_count', 0) or 0
            wk['instagram']['engagement_raw'] += ig.get('engagement_raw', 0) or 0
            wk['instagram']['engagement_details'].extend(ig.get('engagement_details', []))

        # Aggregate Google
        goog = v.get('platforms', {}).get('google', {})
        if goog:
            if 'google' not in wk:
                wk['google'] = {'current_volume': 0, 'record_count': 0}
            wk['google']['current_volume'] += goog.get('current_volume', 0) or 0
            wk['google']['record_count'] += goog.get('record_count', 0) or 0

# Print summary
for wname in ['current_week', 'previous_week']:
    w = windows[wname]
    print(f'{wname}: days_with_data={w[\"days_with_data\"]}, keys={len(w[\"keys\"])}')
    if w['keys']:
        # Show top 3 keys by engagement for preview
        items = []
        for ck, wk in w['keys'].items():
            eng = wk.get('instagram', {}).get('engagement_raw', 0) or 0
            vol = wk.get('google', {}).get('current_volume', 0) or 0
            items.append((ck, eng, vol))
        items.sort(key=lambda x: -x[1])
        for ck, eng, vol in items[:3]:
            print(f'  {ck}: IG_eng={eng:.1f} Google_vol={vol}')

# Write accumulated data for next step
with open('/tmp/step5_accumulated.json', 'w') as f:
    json.dump(windows, f, ensure_ascii=False, indent=2)
print('Accumulated data written to /tmp/step5_accumulated.json')
"
```

### 4. Compute Per-Window Platform Scores

Run scoring independently for each window. This script reads the accumulated
data from step 3 and the config files.

```bash
python3 -c "
import json, math

with open('/tmp/step5_accumulated.json') as f:
    windows = json.load(f)

with open('config/google_scoring.json') as f:
    gcfg = json.load(f)
min_vol_floor = gcfg.get('min_volume_floor', 50)

with open('config/ranking.json') as f:
    rcfg = json.load(f)
ig_w = rcfg['platform_weights']['instagram']
goog_w = rcfg['platform_weights']['google']
bonus = rcfg['dual_platform_bonus']
threshold = rcfg.get('composite_score_threshold', 0.10)

# Score each window independently
scores = {}

for wname in ['current_week', 'previous_week']:
    w = windows[wname]
    days = w['days_with_data']
    scores[wname] = {}

    if days == 0:
        continue

    # Find global maxes for this window (after normalizing by day count)
    max_eng = 0
    max_vol = 0
    for ck, wk in w['keys'].items():
        ig = wk.get('instagram', {})
        goog = wk.get('google', {})
        eng = (ig.get('engagement_raw', 0) or 0) / days
        vol = (goog.get('current_volume', 0) or 0) / days
        if eng > max_eng: max_eng = eng
        if vol > max_vol: max_vol = vol

    # Score each key in this window
    for ck, wk in w['keys'].items():
        ig = wk.get('instagram', {})
        goog = wk.get('google', {})

        eng_raw = (ig.get('engagement_raw', 0) or 0) / days
        ig_score = math.log(eng_raw + 1) / math.log(max_eng + 1) if max_eng > 0 and eng_raw > 0 else 0

        vol = (goog.get('current_volume', 0) or 0) / days
        if vol < min_vol_floor or max_vol == 0:
            goog_score = 0
        else:
            goog_score = math.log(vol + 1) / math.log(max_vol + 1)

        scores[wname][ck] = {
            'display_name': wk.get('display_name', ck),
            'category': wk.get('category', ''),
            'potential': wk.get('potential', ''),
            'ig_score': round(ig_score, 4),
            'goog_score': round(goog_score, 4),
            'ig_eng_raw': round(eng_raw, 1),
            'goog_vol': round(vol, 1),
            'ig_post_count': (ig.get('record_count', 0) or 0),
            'matched_terms': wk.get('matched_terms', {}),
            'platforms_with_data': (1 if ig_score > 0 else 0) + (1 if goog_score > 0 else 0),
        }

    print(f'{wname}: days={days}, max_eng={max_eng:.1f}, max_vol={max_vol:.1f}, scored={len(scores[wname])} keys')

# Write scores for next step
with open('/tmp/step5_scores.json', 'w') as f:
    json.dump(scores, f, ensure_ascii=False, indent=2)
print('Scores written to /tmp/step5_scores.json')
"
```

### 5. Compute Trend Direction

Compare current_week scores against previous_week scores:

```bash
python3 -c "
import json

with open('/tmp/step5_scores.json') as f:
    scores = json.load(f)

with open('/tmp/step5_accumulated.json') as f:
    windows = json.load(f)

with open('config/ranking.json') as f:
    rcfg = json.load(f)
surging_abs = rcfg['trend_direction']['surging']['min_absolute_delta']
surging_rel = rcfg['trend_direction']['surging']['min_relative_delta']
decl_abs = rcfg['trend_direction']['declining']['min_absolute_delta']
decl_rel = rcfg['trend_direction']['declining']['min_relative_delta']

cw = scores.get('current_week', {})
pw = scores.get('previous_week', {})
cw_days = windows['current_week']['days_with_data']
pw_days = windows['previous_week']['days_with_data']

DIR_PRIORITY = {'surging': 6, 'new': 5, 'active': 4, 'declining': 3, 'stable': 2, 'insufficient_data': 1}

# Collect all canonical keys (union of both windows)
all_keys = set(cw.keys()) | set(pw.keys())

for ck in sorted(all_keys):
    cw_score = cw.get(ck, {})
    pw_score = pw.get(ck, {})

    # Data sufficiency check
    if cw_days < 2 or pw_days < 2:
        direction = 'insufficient_data'
        ig_dir = goog_dir = 'insufficient_data'
    elif not pw_score:
        # Keyword not in previous week at all
        direction = 'new'
        ig_dir = goog_dir = 'new'
    else:
        # Per-platform direction
        def platform_dir(this_s, prev_s):
            if prev_s is None or prev_s == 0:
                return 'new'
            delta = this_s - prev_s
            if delta >= surging_abs and delta / prev_s >= surging_rel:
                return 'surging'
            elif delta > 0:
                return 'active'
            elif delta <= -decl_abs and abs(delta) / prev_s >= decl_rel:
                return 'declining'
            else:
                return 'stable'

        ig_dir = platform_dir(cw_score.get('ig_score', 0), pw_score.get('ig_score'))
        goog_dir = platform_dir(cw_score.get('goog_score', 0), pw_score.get('goog_score'))

        # Overall: highest priority across platforms
        direction = max(ig_dir, goog_dir, key=lambda d: DIR_PRIORITY[d])

    # Composite score (current week only)
    ig_s = cw_score.get('ig_score', 0)
    goog_s = cw_score.get('goog_score', 0)
    platforms_hit = cw_score.get('platforms_with_data', 0)
    extra = max(0, platforms_hit - 1)

    with open('config/ranking.json') as f:
        rcfg2 = json.load(f)
    ig_w2 = rcfg2['platform_weights']['instagram']
    goog_w2 = rcfg2['platform_weights']['google']
    bonus2 = rcfg2['dual_platform_bonus']
    composite = round(ig_w2 * ig_s + goog_w2 * goog_s + bonus2 * extra, 4)

    display = cw_score.get('display_name', ck) or pw_score.get('display_name', ck)

    print(f'{ck}|{display}|{ig_s}|{goog_s}|{composite}|{platforms_hit}|{direction}|{ig_dir}|{goog_dir}|{cw_score.get(\"ig_eng_raw\",0)}|{cw_score.get(\"goog_vol\",0)}|{pw_score.get(\"ig_score\",0)}|{pw_score.get(\"goog_score\",0)}|{cw_score.get(\"ig_post_count\",0)}')
"
```

Each line:

```
canonical_key|display_name|ig_score|goog_score|composite|platform_hits|trend_direction|ig_dir|goog_dir|ig_eng_raw|goog_vol|prev_ig_score|prev_goog_score|ig_post_count
```

### 6. Select Raw Term

For each canonical key, inspect `matched_terms` from the current-week scores.
Apply selection rules:

1. Count platforms per term → prefer more platforms
2. Tiebreaker: prefer `is_hashtag: false` over `true`
3. Tiebreaker: use `display_name`

### 7. Filter and Rank

1. Drop all keywords with `composite_score < 0.10`
2. Sort remaining by `composite_score` descending
3. Ties: sort by `display_name` alphabetically
4. Assign `rank` starting from 1

### 8. Assemble Output

#### 8a. Get Period from Accumulated Data

```bash
python3 -c "
import json

with open('/tmp/step5_accumulated.json') as f:
    windows = json.load(f)

# Window boundaries already computed in step 2
print(f'CW_START=CURRENT_WEEK_START')
print(f'CW_END=CURRENT_WEEK_END')
print(f'PW_START=PREVIOUS_WEEK_START')
print(f'PW_END=PREVIOUS_WEEK_END')
print(f'CW_DAYS={windows[\"current_week\"][\"days_with_data\"]}')
print(f'PW_DAYS={windows[\"previous_week\"][\"days_with_data\"]}')
"
```

#### 8b. Get Generated At Timestamp

```bash
TZ='Asia/Hong_Kong' date +%Y-%m-%dT%H:%M:%S+08:00
```

#### 8c. Write Output

```bash
python3 -c "
import json

# Agent fills this from steps 5-7 results
keywords = [
    {
        'canonical_key': 'sukiyaki',
        'display_name': 'Sukiyaki',
        'raw_representative': 'Sukiyaki',
        'category': 'fnb',
        'potential': 'high',
        'social_composite_score': 0.7234,
        'trend_direction': 'active',
        'platform_hits': 2,
        'rank': 1,
        'platforms': {
            'instagram': {
                'platform_score': 0.68,
                'engagement_raw': 142.5,
                'post_count': 44,
                'previous_score': 0.52
            },
            'google': {
                'platform_score': 0.45,
                'volume': 62,
                'previous_score': 0.33
            }
        }
    }
    # ... more keywords filled by Agent
]

output = {
    'schema_version': '3.0',
    'generated_at': 'GENERATED_AT',
    'period': {
        'current_week': {
            'start': 'CW_START',
            'end': 'CW_END',
            'days_with_data': CW_DAYS
        },
        'previous_week': {
            'start': 'PW_START',
            'end': 'PW_END',
            'days_with_data': PW_DAYS
        }
    },
    'pipeline': {
        'mode': 'live',
        'timezone': 'Asia/Hong_Kong'
    },
    'keywords': keywords
}

with open('runs/YYYY-MM-DD/weekly_fnb_trending.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

# Ensure trailing newline
content = open('runs/YYYY-MM-DD/weekly_fnb_trending.json').read()
if content and not content.endswith('\n'):
    open('runs/YYYY-MM-DD/weekly_fnb_trending.json', 'w').write(content + '\n')

print(f'Wrote {len(keywords)} keywords to weekly_fnb_trending.json')
"
```

Replace placeholders with actual values from previous steps.

### 9. Verify

```bash
python3 -c "
import json
from collections import Counter

with open('runs/YYYY-MM-DD/weekly_fnb_trending.json') as f:
    data = json.load(f)

keywords = data['keywords']
period = data['period']
print(f'Total keywords: {len(keywords)}')
print(f'Schema version: {data[\"schema_version\"]}')
print(f'Current week: {period[\"current_week\"][\"start\"]} → {period[\"current_week\"][\"end\"]} ({period[\"current_week\"][\"days_with_data\"]} days)')
print(f'Previous week: {period[\"previous_week\"][\"start\"]} → {period[\"previous_week\"][\"end\"]} ({period[\"previous_week\"][\"days_with_data\"]} days)')
print()

if keywords:
    scores = [kw['social_composite_score'] for kw in keywords]
    print(f'Score range: {min(scores):.4f} – {max(scores):.4f}')
    directions = Counter(kw['trend_direction'] for kw in keywords)
    print(f'Directions: {dict(directions)}')
    plat_hits = Counter(kw['platform_hits'] for kw in keywords)
    print(f'Platform hits: {dict(plat_hits)}')
    print()
    print('Top 5:')
    for kw in keywords[:5]:
        print(f'  #{kw[\"rank\"]} {kw[\"display_name\"]:20s} score={kw[\"social_composite_score\"]:.4f} dir={kw[\"trend_direction\"]:15s} term={kw[\"raw_representative\"]}')
else:
    print('No keywords passed the composite score threshold.')
"
```

---

## Edge Cases

| Scenario                                    | Handling                                                             |
| ------------------------------------------- | -------------------------------------------------------------------- |
| < 14 days of data accumulated (cold start)  | Process whatever is available; `days_with_data` reflects reality     |
| Either window has < 2 days of data          | All keywords `trend_direction = "insufficient_data"`                 |
| Keyword in current week but not previous    | `previous_score = null`, trend = `new`                               |
| Keyword in previous week but not current    | Naturally absent from output (no current data to score)              |
| Some dates missing matched_groups.json      | Skipped; `days_with_data` decremented; normalize by actual day count |
| All 14 dates missing                        | Abort. Nothing to rank.                                              |
| Single platform only (all keywords IG-only) | Google scores all 0, max composite = 0.6                             |
| All keywords below threshold                | Output empty `keywords: []` with metadata                            |
| Config files missing                        | Abort. Required assets.                                              |

---

## Error Handling

| Scenario                                    | Action                      |
| ------------------------------------------- | --------------------------- |
| No `matched_groups.json` files found at all | Abort. Nothing to rank.     |
| Config files missing                        | Abort. Required assets.     |
| Output directory not writable               | Abort. Check permissions.   |
| Accumulation script fails                   | Abort. Check script output. |

---

## Token Budget

| Item                               | Estimate        |
| ---------------------------------- | --------------- |
| Config reads (3 files)             | ~500 tokens     |
| Accumulation scan (14 files × ~2K) | ~28K tokens     |
| Scoring computation                | ~3K tokens      |
| Trend direction computation        | ~2K tokens      |
| Assembly + write output            | ~2K tokens      |
| Verification                       | ~1K tokens      |
| **Total**                          | **~37K tokens** |

Token cost is dominated by reading 14 `matched_groups.json` files.
File sizes are small (~2K tokens each) since they contain only matched
canonical keys, not raw records.

---

## Dependencies

- **Input from Steps 3–4 (14 daily runs)**: `runs/{date}/matched_groups.json`
- **Required config**: `config/instagram_scoring.json`, `config/google_scoring.json`, `config/ranking.json`
- **Output to Step 6**: `runs/YYYY-MM-DD/weekly_fnb_trending.json`
