---
name: hk-fnb-trending
description: >
  HK F&B social media trending keyword discovery pipeline.
  Fetches data via Apify, filters by engagement threshold, then Agent
  extracts dish/venue/cuisine keywords from top posts and Google Trends.
  Triggered by: "run trending pipeline", "hk food trends", "跑趨勢關鍵字".
---

# HK F&B Trending Keyword Pipeline

Daily trending keyword pipeline for Hong Kong F&B.
Fetches Google Trends + Instagram + Threads data via Apify,
filters to high-engagement posts, then Agent extracts specific
dish names, venue names, and cuisine types.

## Quick Reference

| User says | Action |
|-----------|--------|
| "run trending pipeline" | Full run |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending.json` |
| "compare trends this week" | Read 7 days, compare |

## Pipeline Flow

```
Step 1: Fetch    → apify_fetch.sh (15 actors) → normalize_raw.py
Step 2: Filter   → filter_threshold.py (like>threshold AND share>threshold)
Step 3: Extract  → Agent reads filtered posts + Google Trends → extracts keywords
Step 4: Output   → Write daily_trending.json + update runs/latest symlink
```

## Output Schema

`runs/YYYY-MM-DD/daily_trending.json`:

```json
{
  "schema_version": "1.0",
  "date": "2026-07-07",
  "generated_at": "2026-07-07T10:00:00+08:00",
  "threshold": {
    "instagram": { "min_likes": 1000, "min_shares": 500 },
    "threads": { "min_likes": 1000, "min_shares": 500 }
  },
  "posts": [
    {
      "platform": "instagram",
      "source": "#hkfoodie",
      "source_kind": "hashtag",
      "url": "https://www.instagram.com/reel/...",
      "likes": 3200,
      "comments": 85,
      "shares": 1200,
      "taken_at": "2026-07-06T18:20:00+08:00",
      "caption_snippet": "北角呢間隱世串燒店嘅沙嗲拼盤真係...",
      "hashtags": ["香港美食", "北角美食", "串燒", "沙嗲"],
      "extracted": {
        "dishes": ["沙嗲拼盤", "燒蠔"],
        "venues": ["北角串燒店"],
        "cuisines": []
      }
    }
  ],
  "google_trends": [
    { "term": "壽司郎", "volume": 85 },
    { "term": "珍珠奶茶", "volume": 62 }
  ],
  "keywords": [
    {
      "term": "沙嗲拼盤",
      "type": "dish",
      "post_count": 3,
      "total_likes": 8500,
      "total_comments": 210,
      "total_shares": 3200,
      "platforms": ["instagram"],
      "sources": ["#hkfoodie", "@girlsfoodies", "#hkfood"]
    },
    {
      "term": "壽司郎",
      "type": "venue",
      "post_count": 5,
      "total_likes": 12000,
      "total_comments": 340,
      "total_shares": 4800,
      "platforms": ["instagram", "google"],
      "sources": ["#hkfood", "@foodiehk", "google"]
    }
  ]
}
```

## Config

| File | Purpose |
|------|---------|
| `config/threshold.json` | Engagement thresholds per platform |
| `config/apify_actors_v1.json` | Apify actor IDs |
| `config/social_listening_v1.json` | Platform seeds |

Threshold defaults:

```json
{
  "instagram": { "min_likes": 1000, "min_shares": 500 },
  "threads": { "min_likes": 1000, "min_shares": 500 },
  "google": { "min_volume": 0 }
}
```

Adjust `min_likes`/`min_shares` based on data volume. If too few posts pass,
lower thresholds. Start conservative and widen if needed.

## Environment

| Variable | Purpose |
|----------|---------|
| `APIFY_TOKEN` | Apify API authentication |

## Procedure

### Step 1 — Fetch

Same as before: 15 parallel Apify actors, then normalize:

```bash
# Determine date (default: yesterday)
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)
RUN_DIR="runs/${TARGET_DATE}"
mkdir -p "${RUN_DIR}/raw/_apify"

# Read configs + run 15 actors in parallel (see scripts/apify_fetch.sh)
# ... (same as old Step 1) ...

wait

# Normalize
python3 scripts/normalize_raw.py --date "$TARGET_DATE" --run-dir "$RUN_DIR" --config config/social_listening_v1.json
```

### Step 2 — Filter

```bash
python3 scripts/filter_threshold.py --date "$TARGET_DATE"
```

Output: `runs/YYYY-MM-DD/filtered/threshold_filtered.json`

If 0 posts pass the threshold, warn and consider lowering thresholds in `config/threshold.json`.

### Step 3 — Extract Keywords (Agent)

Read `filtered/threshold_filtered.json`. The agent examines each post's
`caption_snippet` and `hashtags`, plus `google_trends` terms.

#### Extraction Prompt

---

You are extracting trending F&B keywords from Hong Kong social media posts
and Google Trends data. Your output drives a daily HK food trends report.

## Task

For each post below, extract:

1. **Dishes** (優先) — specific dish names. Keep the full name with modifiers:
   "蝦拉麵" NOT "拉麵", "冰鎮咕嚕肉" NOT "咕嚕肉", "沙嗲牛肉麵" NOT "沙嗲".
   Include: individual dishes, desserts, drinks, baked goods, specific food items.

2. **Venues** (優先) — restaurant names, cafe names, food venues, food streets,
   dai pai dong, markets with food significance. Include both chains (壽司郎, 麥當勞,
   薩莉亞) and notable independents.

3. **Cuisines** (次要) — cuisine types or food categories: 日本菜, 泰國菜, 川菜,
   dim sum, ramen, omakase, 放題, 茶餐廳, 打邊爐, 燒烤.

**DO NOT extract:**
- Vague/generic terms: 好味, 美食, 必食, 好食, 好西, 香港, foodie, foodporn, yum
- Standalone locations without food context: 北角, 旺角, 中環, mongkok, causeway bay
- Non-food activities: 唱K, 行山, 打卡, yoga
- Generic social media tags: hkfood, 香港美食, 相機食先, hkfoodie

**Naming rules:**
- Use the most common Hong Kong Chinese name: 壽司郎 not Sushiro, 麥當勞 not McDonald's
- For English-only concepts, keep English: craft beer, omakase, ramen
- Mixed terms OK: 和牛burger, DIY燒肉

## Posts

Format: `[N] platform | source | likes ❤️ | comments 💬 | shares 🔄`

{CAPTIONS}

## Google Trends

{GOOGLE_TERMS}

## Output

Return ONLY JSON. No markdown, no explanation.

```json
{
  "posts": [
    {
      "index": 0,
      "dishes": ["沙嗲拼盤", "燒蠔"],
      "venues": ["北角串燒店"],
      "cuisines": ["串燒"]
    },
    {
      "index": 1,
      "dishes": [],
      "venues": ["壽司郎"],
      "cuisines": ["日本菜"]
    }
  ],
  "keywords": [
    {
      "term": "沙嗲拼盤",
      "type": "dish",
      "post_indices": [0, 3, 7]
    },
    {
      "term": "壽司郎",
      "type": "venue",
      "post_indices": [1, 4, 5, 8, 12]
    },
    {
      "term": "日本菜",
      "type": "cuisine",
      "post_indices": [1, 6, 9]
    }
  ]
}
```

Rules:
- `dishes`, `venues`, `cuisines` arrays — empty `[]` if nothing found
- `keywords[].post_indices` — which posts mention this keyword (0-based)
- `keywords[].type` — "dish", "venue", or "cuisine"
- Google Trends terms that are F&B: include in `keywords` with type, `post_indices: []`
- Google Trends terms that are NOT F&B: omit entirely
- Return ONLY the JSON

---

### Step 4 — Assemble Output

After receiving the JSON, assemble the final output:

```bash
python3 -c "
import json
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))

# Load filtered data
with open('runs/YYYY-MM-DD/filtered/threshold_filtered.json') as f:
    filtered = json.load(f)

# Load extraction results (paste JSON response here)
extraction = '''PASTE_JSON_RESPONSE_HERE'''
ext = json.loads(extraction)

# Merge extraction into posts
posts = filtered['posts']
for pe in ext.get('posts', []):
    idx = pe['index']
    if idx < len(posts):
        posts[idx]['extracted'] = {
            'dishes': pe.get('dishes', []),
            'venues': pe.get('venues', []),
            'cuisines': pe.get('cuisines', []),
        }

# Build keyword aggregates
for kw in ext.get('keywords', []):
    indices = kw.get('post_indices', [])
    total_likes = sum(posts[i]['likes'] for i in indices if i < len(posts))
    total_comments = sum(posts[i]['comments'] for i in indices if i < len(posts))
    total_shares = sum(posts[i]['shares'] for i in indices if i < len(posts))
    platforms = list(set(posts[i]['platform'] for i in indices if i < len(posts)))
    if not indices:  # Google-only keyword
        platforms = ['google']
    sources = list(set(posts[i]['source'] for i in indices if i < len(posts)))
    kw['post_count'] = len(indices)
    kw['total_likes'] = total_likes
    kw['total_comments'] = total_comments
    kw['total_shares'] = total_shares
    kw['platforms'] = platforms
    kw['sources'] = sources
    # Clean up — remove post_indices from output
    del kw['post_indices']

# Google Trends: include F&B terms that weren't covered by posts
google_terms = filtered.get('google_trends', [])
# (Google terms already handled in keywords by agent)

output = {
    'schema_version': '1.0',
    'date': filtered['date'],
    'generated_at': datetime.now(HKT).strftime('%Y-%m-%dT%H:%M:%S+08:00'),
    'threshold': filtered['threshold'],
    'posts': posts,
    'google_trends': google_terms,
    'keywords': ext.get('keywords', []),
}

import os
run_dir = 'runs/YYYY-MM-DD'
os.makedirs(run_dir, exist_ok=True)
with open(f'{run_dir}/daily_trending.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
# Ensure trailing newline
content = open(f'{run_dir}/daily_trending.json').read()
if content and not content.endswith('\n'):
    open(f'{run_dir}/daily_trending.json', 'w').write(content + '\n')

# Update symlink
if os.path.islink('runs/latest') or os.path.exists('runs/latest'):
    os.remove('runs/latest')
os.symlink(f'YYYY-MM-DD', 'runs/latest')

print(f'✅ {len(output[\"keywords\"])} keywords from {len(posts)} posts + {len(google_terms)} Google terms')
print(f'Output: runs/YYYY-MM-DD/daily_trending.json')
"
```

### Step 5 — Present Summary

Show a quick summary in chat:

```
✅ Pipeline done.

{len(posts)} posts passed threshold → {len(keywords)} keywords extracted

🔥 Top dishes:
  • 沙嗲拼盤 (3 posts, 8.5K likes)
  • 冰鎮咕嚕肉 (2 posts, 5.2K likes)

📍 Top venues:
  • 壽司郎 (5 posts, 12K likes)
  • 麥當勞 (3 posts, 9.1K likes)

🍽️ Cuisines: 日本菜, 泰國菜, 川菜

Full data: runs/YYYY-MM-DD/daily_trending.json
```

## Edge Cases

| Scenario | Handling |
|----------|----------|
| 0 posts pass threshold | Warn, suggest lowering `config/threshold.json` |
| LLM extraction fails | Retry once. If still failing, write posts without `extracted` field |
| Malformed JSON from LLM | Retry once with stricter prompt |
| `APIFY_TOKEN` not set | Abort |

## Reading Trends (14-day comparison)

When user asks to compare trends, Agent reads 7-14 `daily_trending.json` files
and uses its own judgment to identify: surging keywords (increasing post count +
engagement), declining keywords, and new entries. No scoring formula needed —
Agent describes patterns in natural language.
