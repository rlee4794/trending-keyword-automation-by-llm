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
| "run trending pipeline" | Full run (Steps 1-4 + Summary) |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending.json` |
| "trend analysis" / "compare trends" | Run Step 5 (7-day snapshot comparison, on-demand) |

## Pipeline Flow

```
Step 1: Fetch    → apify_fetch.sh (15 actors) → normalize_raw.py
Step 2: Filter   → filter_threshold.py (like>threshold AND share>threshold)
Step 3: Extract  → Agent reads filtered posts + Google Trends → extracts keywords
Step 4: Assemble → assemble_output.py → daily_trending.json
Step 5: Summary  → Present daily results in chat

--- on-demand only (not part of daily pipeline) ---

Step T: Trends  → trend_comparison.py (prepare) → Agent (fuzzy match) →
                  trend_comparison.py (merge) → daily_trending.json enriched
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

### Step 5 — Present Summary

Show a quick summary in chat. **Always split into two independent groups** —
social keywords (ranked by likes/engagement) and Google Trends keywords
(ranked by search volume). Never mix them in a single ranked list.

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
| 7-days-ago data unavailable | Skip trend comparison, keywords get no `trend` field |
| Agent fuzzy match fails or returns invalid JSON | Retry once. If still failing, skip trend merge |

## Reading Trends

Trend comparison is an **on-demand** step (Step T), not part of the daily pipeline.
When user says "trend analysis" or "compare trends":

### Step T — Trend Comparison (7-day snapshot, on-demand)

Compare today's keywords against 7 days ago. Only two classifications:
- **new**: keyword did not appear in any of the last 7 days
- **surging**: keyword existed 7 days ago, but post_count increased ≥50%

#### Step Ta — Prepare snapshots

```bash
python3 scripts/trend_comparison.py --date YYYY-MM-DD --output /tmp/trend_snapshots.json
```

This reads today's `daily_trending.json`, the 7-days-ago file (if available),
and all intermediate days, then outputs:
- `today_keywords`: today's keyword list with stats
- `prev_keywords`: 7-days-ago keyword list (null if unavailable)
- `seen_in_period`: exact-match set of all terms from intermediate days
  (used to exclude false 'new' — a keyword seen on day-3 is NOT new)

#### Step Tb — Agent fuzzy matching

Read `/tmp/trend_snapshots.json`. The Agent does fuzzy matching between
today's keywords and the previous period keywords, then classifies each.

##### Trend Matching Prompt

---

You are matching today's F&B trending keywords against 7-days-ago keywords.

## Input

**Today's keywords** (date: {today_date}):
{today_keywords}

**7-days-ago keywords** (date: {prev_date}):
{prev_keywords}

**Seen in period** (terms that appeared on ANY of the last 7 days —
if a today keyword matches one of these but NOT the day-7 snapshot,
it is NOT 'new'):
{seen_in_period}

## Task

For each today keyword, determine if it is:

1. **"new"** — the keyword does NOT appear in `seen_in_period` AND does NOT
   have a fuzzy match in `prev_keywords`. This means it's genuinely new
   in the last 7 days.

2. **"surging"** — the keyword has a fuzzy match in `prev_keywords` AND
   today's `post_count` is ≥ 1.5× the previous post_count.
   The fuzzy match handles spelling variants: 沙爹牛 ≈ 沙嗲牛,
   寿司郎 ≈ 壽司郎, Sushiro ≈ 壽司郎.

3. **No trend** — omit from output. Keyword is stable, declining, or
   the match is too uncertain.

## Fuzzy matching rules

- Same meaning, different script: 寿司郎 ↔ 壽司郎 (SC/TC)
- Same dish, minor spelling: 沙爹牛 ↔ 沙嗲牛, 珍珠奶茶 ↔ 珍珠奶茶
- English ↔ Chinese: Sushiro ↔ 壽司郎, McDonald's ↔ 麥當勞
- Term is a substring of another: 沙嗲牛 ↔ 沙嗲牛肉麵 — these are
  DIFFERENT. Only match if the core concept is the same.
- If uncertain, omit — better to miss a match than produce a false one.

## Output

Return ONLY JSON. No markdown, no explanation.

```json
{
  "matches": [
    {
      "today_term": "沙嗲拼盤",
      "today_type": "dish",
      "classification": "surging",
      "matched_term": "沙爹拼盤",
      "prev_post_count": 1,
      "prev_total_likes": 2000
    },
    {
      "today_term": "至尊漢堡",
      "today_type": "dish",
      "classification": "new"
    }
  ]
}
```

Rules:
- `today_term`, `today_type`: exactly as they appear in today's keyword list
- `classification`: "new" or "surging" only
- For "surging": include `matched_term`, `prev_post_count`, `prev_total_likes`
- For "new": only `today_term`, `today_type`, `classification`
- Return ONLY the JSON

---

#### Step Tc — Merge results

After receiving the Agent's JSON, merge trend fields back into today's
daily_trending.json:

```bash
python3 scripts/trend_comparison.py --date YYYY-MM-DD --merge /path/to/agent_output.json
```

This adds a `trend` field to each matched keyword:

```json
{
  "term": "沙嗲拼盤",
  "type": "dish",
  "post_count": 3,
  "trend": {
    "direction": "surging",
    "matched_term": "沙爹拼盤",
    "prev_post_count": 1,
    "prev_total_likes": 2000
  }
}
```

Keywords without a trend signal get no `trend` field.

### Present Trend Summary

After merging, highlight trend signals in chat:
- 🆕 **New**: first appeared in the last 7 days
- 🔥 **Surging**: post_count up ≥50% vs 7 days ago
