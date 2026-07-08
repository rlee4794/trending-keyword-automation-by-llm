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
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending.json` → present Top 10 by category with background |
| "trend analysis" / "compare trends" | Run Step T (7-day snapshot comparison, on-demand) |

### ⚠️ Already-run rule

If today's pipeline has **already completed** (i.e. `daily_trending.json` exists
and was generated today), and the user asks about trends **without** explicitly
requesting a re-run (e.g. just "run trending pipeline" / "有什麼trends" /
"今日有咩趨勢"), do NOT re-execute the pipeline. Instead, read the existing
`daily_trending.json` and present the results directly:

1. **Top 10 by category** — split into:
   - 🔥 Social 熱門菜式（按 likes 排序，最多 10 個）
   - 📍 Social 熱門餐廳（按 likes 排序，最多 10 個）
   - 🍽️ 熱門菜系（按 post_count 排序，最多 10 個）
   - 🔍 Google 熱搜（按 volume 排序，最多 10 個，只列 F&B 相關）
2. **Short background** — for each keyword in 🔥 Social 熱門菜式 and 📍 Social 熱門餐廳,
   include a one-line context from `caption_snippet` or source info.
   🍽️ 熱門菜系 and 🔍 Google 熱搜 do NOT need background.
   For example:
   - 梅菜扣肉飯 — 源自 7-11 聯乘貼文，兩日內累積 67K likes
   - 沙嗲牛 — 4 篇貼文提及，來自 #hkfoodie 及 @girlsfoodies
3. If the user explicitly says "重跑" / "重新 fetch" / "rerun" / "再run多次",
   then execute the full pipeline again.

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
    { "term": "壽司郎", "volume": 85, "related_terms": ["壽司郎", "迴轉壽司"] },
    { "term": "珍珠奶茶", "volume": 62, "related_terms": ["珍珠奶茶", "黑糖珍珠"] }
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

   **Extracting venues from lists and markers:**
   - Numbered/bullet lists of restaurants → extract each as a venue.
     Example: "1. 牛奶冰室 2. 蜜雪冰城 3. 百分百餐廳" → venues: [牛奶冰室, 蜜雪冰城, 百分百餐廳]
   - 📍 followed by a name → extract as venue.
     Example: "📍Picanhas' 中環伊利近街" → venues: [Picanhas']
   - Restaurant name + food description → extract the name.
     Example: "紅磡炒得喜 超大盆花甲蒸蛋！！" → venues: [紅磡炒得喜]

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

**Threads-specific notes:** Threads posts are shorter and more conversational
than Instagram. They rarely use hashtags. Pay extra attention to:
- Numbered/bullet lists of restaurants or dishes (e.g. "1. 牛奶冰室 2. 蜜雪冰城")
- Venue names after 📍 markers (e.g. "📍Picanhas'")
- Standalone restaurant names followed by food descriptions
  (e.g. "紅磡炒得喜 超大盆花甲蒸蛋！！")
- Dish names in short declarative sentences
  (e.g. "推薦一間中環附近嘅牛排午餐")

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

Show a detailed summary in chat. **Always split into four independent groups** —
social dishes, social venues, cuisines, and Google Trends keywords. Never mix them.

If a keyword appears on both channels, tag it `🔥🔍` to signal cross-channel heat.

**Format: Top 10 per category, with short background for each item.**

```
✅ Pipeline done. {len(posts)} posts passed threshold → {len(keywords)} keywords extracted

🔥 Social 熱門菜式（按互動熱度，Top 10）
  • 梅菜扣肉飯 (2 posts, 67.5K likes) — 源自 7-11 聯乘貼文，兩日內爆發
  • 沙嗲牛 (4 posts, 40.1K likes) — #hkfoodie 及 @girlsfoodies 多位 foodie 提及
  • 蝦多士 (4 posts, 9.8K likes) — 港式茶記經典小食，Threads 上熱議

📍 Social 熱門餐廳（按互動熱度，Top 10）
  • 7-11 (2 posts, 67.5K likes) — 便利商店聯乘新品引發熱潮
  • 夜嚐野 (2 posts, 27.8K likes) — 深水埗新開宵夜檔，串燒為主

🍽️ 熱門菜系（按提及 post 數，Top 10，無需背景）
  • 甜品 (20 posts)
  • 咖啡 (12 posts)

🔍 Google 熱搜關鍵詞（按搜尋量，Top 10，附 related_terms）
  • 大家樂冬瓜盅 (200 vol) 🔥🔍 — 相關詞：冬瓜盅、大家樂
  • 富臨漁港 (紅磡店) (2,000 vol) — 相關詞：富临渔港

Full data: runs/YYYY-MM-DD/daily_trending.json
```

#### Background extraction rules

For each keyword's background, infer from the associated posts' `caption_snippet`
and `source` fields. Keep it to one short line:
- **Dishes**: mention the source context (聯乘/新開/限時/傳統) and notable platform
- **Venues**: mention location/type (連鎖/新開/地區) and what they're known for
- **Cuisines**: NO background needed — just list post_count
- **Google**: show `related_terms` as a comma-separated list (exclude the term itself).
  If the term also appears in social keywords, tag `🔥🔍`

#### Google related_terms display rules

Each Google Trends entry now carries a `related_terms` array from the raw data.
When presenting Google results:
- Show `related_terms` inline after the volume, e.g. `— 相關詞：燒鵝, 大家樂`
- Exclude the primary term itself from the display (it's redundant)
- Deduplicate — if the same related term appears multiple times, show it once
- If no related_terms or all are duplicates of the primary term, omit the `— 相關詞：` part

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
