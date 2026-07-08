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
| "run trending pipeline" | Full run (all 6 steps) |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending.json` |
| "trend analysis" | Read `runs/trend_analysis.md` |

## Pipeline Flow

```
Step 1: Fetch    → apify_fetch.sh (15 actors) → normalize_raw.py
Step 2: Filter   → filter_threshold.py (like>threshold AND share>threshold)
Step 3: Extract  → Agent reads filtered posts + Google Trends → extracts keywords
Step 4: Assemble → assemble_output.py → daily_trending.json
Step 5: Trends   → trend_comparison.py → Agent produces natural-language 14-day analysis
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
   dai pai dong, markets with food significance. Must be at least 2 characters.
   Include both chains (壽司郎, 麥當勞, 薩莉亞) and notable independents.
   A venue is a PROPER NOUN — if it's a common Chinese word that could appear
   in any sentence (不, 的, 好, 是, 有, 食, 飲, 去, 來, 我, 你, 他, 她, 很,
   個, 種, 啲, 嘅, 咁, 仲, 未, 冇, 無, 係, 喺, 俾, 畀, 令, 將, 但, 只,
   已, 更, 最, 都, 就, 也, 會, 要, 可, 又, 或, 與, 及), it is NOT a venue.

3. **Cuisines** (次要) — cuisine types or food categories: 日本菜, 泰國菜, 川菜,
   dim sum, ramen, omakase, 放題, 茶餐廳, 打邊爐, 燒烤.

**DO NOT extract:**
- Single characters as venues or dishes — minimum 2 characters required.
  A single Chinese character is almost never a restaurant name or dish.
  The rare exceptions (like the restaurant '不' at 北角錦屏街) appear
  ONLY in location/address contexts (📍不, 🗺️ address). If a single
  character appears mid-sentence as a common word, do NOT extract it.
- Common Chinese function words / adverbs / conjunctions as venues or dishes:
  不, 的, 了, 是, 在, 有, 和, 都, 就, 也, 會, 要, 可, 好, 食, 飲, 去, 來,
  我, 你, 他, 她, 很, 個, 種, 啲, 嘅, 咁, 仲, 未, 冇, 無, 係, 喺, 俾, 畀,
  令, 將, 但, 只, 已, 更, 最, 又, 或, 與, 及
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
- Google Trends terms: only include if they are **specific F&B proper nouns** — named dishes (至尊漢堡, 大家樂冬瓜盅), named venues (富臨漁港), or named brands (McGriddles, McDonald). Omit generic category words (套餐, 麵包, 榴槤), supermarket/retail names (百佳超級市場), and non-F&B terms entirely. Included terms get `post_indices: []`
- Return ONLY the JSON

---

### Step 4 — Assemble Output

After receiving the JSON, assemble the final output:

```bash
python3 scripts/assemble_output.py --date YYYY-MM-DD --extraction-file /path/to/extraction.json
```

The assembly script handles:
- Merging extraction results into posts
- Post-processing guards (stripping single-char / common-word false venues)
- Keyword aggregation with engagement stats
- Writing `daily_trending.json` + updating `runs/latest` symlink

### Step 5 — Trend Comparison (14-day analysis)

After assembling today's `daily_trending.json`, run the trend comparison
script to build a keyword timeline, then have the Agent produce a
natural-language analysis.

```bash
python3 scripts/trend_comparison.py --days 14 --output runs/trend_summary.json
```

This reads all available `daily_trending.json` files from the last 14 days,
builds per-keyword daily stats, and classifies each as new / surging / stable
/ declining.

#### Trend Analysis Prompt

---

You are analysing Hong Kong F&B keyword trends over the last 14 days.
Below is a keyword timeline extracted from daily pipeline runs.

## Task

Describe the trends in natural language. No scoring formula — just read
the data and tell the story.

For each trend category, list the most notable keywords:

1. **🔥 Surging** — keywords with increasing post count + engagement in the
   second half of the period. What's gaining momentum?
2. **🆕 New entries** — keywords that appeared for the first time recently.
   What's fresh?
3. **📉 Declining** — keywords with dropping engagement. What's fading?

Also note any patterns:
- Dishes clustering around a cuisine or theme (e.g. multiple ramen dishes surging)
- A venue appearing with many different dishes (menu expansion signal)
- Cross-channel heat (keyword appears on both social AND Google Trends)

## Keyword Timeline

{TIMELINE_DATA}

## Output

Write a concise natural-language summary. Group by trend direction.
Include specific numbers (post counts, likes) for the most notable items.
Keep it under 300 words. No JSON — just plain text.

---

After receiving the Agent's analysis, write it to `runs/trend_analysis.md`
and present a summary in chat.

### Step 6 — Present Summary

Show a quick summary in chat. Include both the daily extraction results
AND the trend analysis highlights.

If a keyword appears on both channels, tag it `🔥🔍` to signal cross-channel heat.

```
✅ Pipeline done. {len(posts)} posts passed threshold → {len(keywords)} keywords extracted

🔥 Social 熱門菜式（按互動熱度）
  • 沙嗲拼盤 (3 posts, 8.5K likes)
  • 冰鎮咕嚕肉 (2 posts, 5.2K likes)
  • 蝦拉麵 (1 post, 3.1K likes)

🔍 Google 熱搜關鍵詞（按搜尋量）
  • 至尊漢堡 (2,000 vol)
  • 燒鵝 (1,000 vol)
  • 大家樂冬瓜盃 (200 vol)

📍 Social 熱門餐廳
  • 壽司郎 (5 posts, 12K likes)
  • 麥當勞 (3 posts, 9.1K likes)

🔍 Google 熱搜餐廳
  • 富臨漁港 (2,000 vol)

🍽️ 熱門菜系: 日本菜, 泰國菜, 川菜

Full data: runs/YYYY-MM-DD/daily_trending.json
```

## Edge Cases

| Scenario | Handling |
|----------|----------|
| 0 posts pass threshold | Warn, suggest lowering `config/threshold.json` |
| LLM extraction fails | Retry once. If still failing, write posts without `extracted` field |
| Malformed JSON from LLM | Retry once with stricter prompt |
| `APIFY_TOKEN` not set | Abort |

## Reading Trends

Trend comparison runs automatically as part of the pipeline (Step 5).
The script `trend_comparison.py` builds a keyword timeline from the last
14 days of `daily_trending.json` files, classifies each keyword, and the
Agent produces a natural-language analysis saved to `runs/trend_analysis.md`.

When user asks to compare trends outside of a pipeline run, Agent reads
7-14 `daily_trending.json` files and uses its own judgment to identify:
surging keywords (increasing post count + engagement), declining keywords,
and new entries. No scoring formula needed — Agent describes patterns in
natural language.
