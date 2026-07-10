---
name: fnb-trending-by-social-listening
description: >
  HK + TW F&B social media trending keyword pipeline.
  Fetches Instagram/Threads/Google Trends via Apify, filters by engagement,
  then LLM extracts dish/venue/cuisine keywords.
  Triggered by any mention of food trends, trending keywords, pipeline
  execution, or trend analysis for Hong Kong/Taiwan F&B.
  Also handles read-only queries like "今日有咩trends" or "show trends for YYYY-MM-DD".
  Trigger keywords: "run trending pipeline", "hk food trends", "跑趨勢關鍵字",
  "今日有咩trends", "food trends", "trend analysis", "compare trends", "走勢", "變動".
---

# HK F&B Trending Keyword Pipeline

Daily trending keyword pipeline for Hong Kong + Taiwan F&B.
Fetches Google Trends + Instagram (HK hashtags, HK users, TW users) + Threads data via Apify,
filters to high-engagement posts, then Agent extracts specific
dish names, venue names, and cuisine types.

Taiwan coverage: Instagram user scraper (ig_tw_user_*) + Google Trends (google_tw).
TW posts are tagged with `"geo": "TW"` and merged into the same instagram_raw.json.
Google TW data goes to `google_tw_raw.json` → `google_tw_trends` in daily_trending_TW.json.
No Threads for Taiwan.

## Prerequisites

All commands must be run from the skill directory (`~/.agents/skills/fnb-trending-by-social-listening/`).

| Dependency | Version / Notes |
|------------|-----------------|
| `bash` 4+ | |
| `python3` 3.10+ | stdlib only — no external packages required |
| `curl` | |
| `jq` | JSON processing in shell scripts |
| `xargs` | concurrency control (`-P` flag required) |
| `APIFY_TOKEN` | Apify API token, set as environment variable |

`runs/` is a symlink → ArkDrive personal space for persistent output storage.

## Quick Reference

| User says | Action |
|-----------|--------|
| "run trending pipeline" / "行trending pipeline" | Full run — **HK only, defaults to yesterday** (Steps 1-4 + Summary) |
| "run TW pipeline" / "行台灣pipeline" / "行TW" | Full run — **Taiwan only, defaults to yesterday** (IG users + Google Trends TW) |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending_HK.json or daily_trending_TW.json` → present Top 10 by category with background |
| "trend analysis" / "compare trends" / "變動" / "走勢" | Run **Step T** (7-day snapshot comparison, on-demand) |

### ⚠️ Output format rule

All summary/analysis presentations in chat **must use markdown tables**,
not bullet lists. This applies to:
- Step 5 daily summary (each category as a table with appropriate columns)
- Step T trend comparison output
- "show trends for YYYY-MM-DD" readout
- Any multi-row data display (top N lists, comparisons, rankings)

Exception: single-value answers and short explanations can remain as prose.

### ⚠️ Region selector rule

When the user says "run trending pipeline" **without** specifying a region,
**default to HK only**. Do NOT run Taiwan unless the user explicitly says
"TW" / "台灣" / "Taiwan" / "台北" in the same request.

When the user specifies TW, run **Taiwan only** (skip HK Google/IG hashtags/Threads).

### ⚠️ Step T (trend analysis) is on-demand only

Step T (trend comparison / 變動分析) is **NOT part of the daily pipeline**.
Only run it when the user explicitly asks for:
- "trend analysis" / "compare trends" / "走勢" / "變動" / "compared to last week"
- Any phrase that implies comparing today vs historical data

Do NOT run Step T automatically after a regular pipeline run.

### ⚠️ Already-run rule

If today's pipeline has **already completed** (i.e. `daily_trending_{REGION}.json` exists
and was generated today), and the user asks about trends **without** explicitly
requesting a re-run (e.g. just "run trending pipeline" / "有什麼trends" /
"今日有咩趨勢"), do NOT re-execute the pipeline. Instead, read the existing
`daily_trending_{REGION}.json` and present the results directly:

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
Step 1: Fetch    → run_fetch.sh (xargs -P 30) → normalize_raw.py
Step 2: Filter   → filter_threshold.py (like>threshold AND share>threshold)
Step 3: Extract  → Agent reads filtered posts + Google Trends → extracts keywords
Step 4: Assemble → assemble_output.py → daily_trending_{REGION}.json
Step 5: Summary  → Present daily results in chat

--- on-demand only (not part of daily pipeline) ---

Step T: Trends  → trend_comparison.py (prepare) → Agent (fuzzy match) →
                  trend_comparison.py (merge) → daily_trending_{REGION}.json enriched
```

## Output Schema

`runs/YYYY-MM-DD/daily_trending_{REGION}.json` (e.g. `daily_trending_HK.json`, `daily_trending_TW.json`):

Each file is self-contained per region — no cross-region merging.

```json
{
  "schema_version": "1.0",
  "date": "2026-07-07",
  "region": "hk",
  "generated_at": "2026-07-07T10:00:00+08:00",
  "threshold": {
    "instagram": { "min_likes": 1000, "min_shares": 500 },
    "threads": { "min_likes": 1000, "min_shares": 500 }
  },
  "posts": [
    {
      "platform": "instagram",
      "source": "@girlsfoodies",
      "source_kind": "user_post",
      "geo": "HK",
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
| `APIFY_TOKEN` | Apify API authentication (set before running pipeline) |

## Procedure

All commands below assume the working directory is the skill root
(`~/.agents/skills/fnb-trending-by-social-listening/`).

### Step 1 — Fetch

Dispatch Apify actors via `run_fetch.sh`, which reads configs and uses `xargs -P`
to respect Apify's 32-actor concurrent limit. Default max-concurrent is 30.

**Hong Kong:** 16 actors (1 Google + 4 IG hashtags + 10 IG users + 1 Threads)
**Taiwan:** 57 actors (1 Google + 56 IG users)

```bash
**⚠️ Always use yesterday's date (`date -d "yesterday"`) unless the user explicitly specifies a different date.**

# Determine date (default: yesterday)
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)

# Fetch data with concurrency control
bash scripts/run_fetch.sh --date "$TARGET_DATE" --region hk
# or for Taiwan:
bash scripts/run_fetch.sh --date "$TARGET_DATE" --region tw

# Normalize
python3 scripts/normalize_raw.py --date "$TARGET_DATE" --run-dir "runs/${TARGET_DATE}" --config config/social_listening_v1.json
```

### Step 2 — Filter

```bash
python3 scripts/filter_threshold.py --date "$TARGET_DATE"
```

Output: `runs/YYYY-MM-DD/filtered/{region}/threshold_filtered.json`

If 0 posts pass the threshold, warn and consider lowering thresholds in `config/threshold.json`.

### Step 3 — Extract Keywords (Agent)

Read `filtered/{region}/threshold_filtered.json`. The agent examines each post's
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
python3 scripts/assemble_output.py --date YYYY-MM-DD --region hk --extraction-file /path/to/extraction.json
```

The assembly script handles:
- Merging extraction results into posts
- Post-processing guards (stripping single-char / common-word false venues)
- Keyword aggregation with engagement stats
- Writing `daily_trending_{REGION}.json` + updating `runs/latest` symlink

### Step 5 — Present Summary

Show a detailed summary in chat. **Always split into four independent groups** —
social dishes, social venues, cuisines, and Google Trends keywords. Never mix them.

If a keyword appears on both channels, tag it `🔥🔍` to signal cross-channel heat.

**Format: Top 10 per category, with short background for each item.**
**Use markdown tables, not bullet lists.**

```
✅ Pipeline done. {len(posts)} posts passed threshold → {len(keywords)} keywords extracted

🔥 Social 熱門菜式（按互動熱度，Top 10）

| 關鍵詞 | Posts | Likes | 背景 |
|--------|-------|-------|------|
| 梅菜扣肉飯 | 2 | 67.5K | 源自 7-11 聯乘貼文，兩日內爆發 |
| 沙嗲牛 | 4 | 40.1K | #hkfoodie 及 @girlsfoodies 多位 foodie 提及 |
| 蝦多士 | 4 | 9.8K | 港式茶記經典小食，Threads 上熱議 |

📍 Social 熱門餐廳（按互動熱度，Top 10）

| 餐廳 | Posts | Likes | 背景 |
|------|-------|-------|------|
| 7-11 | 2 | 67.5K | 便利商店聯乘新品引發熱潮 |
| 夜嚐野 | 2 | 27.8K | 深水埗新開宵夜檔，串燒為主 |

🍽️ 熱門菜系（按提及 post 數，Top 10，無需背景）

| 菜系 | Posts |
|------|-------|
| 甜品 | 20 |
| 咖啡 | 12 |

🔍 Google 熱搜關鍵詞（按搜尋量，Top 10）

| 關鍵詞 | Volume | 趨勢 | 相關詞 |
|--------|--------|------|--------|
| 大家樂冬瓜盅 | 200 | 🔥🔍 | 冬瓜盅、大家樂 |
| 富臨漁港 | 2,000 | — | 富临渔港 |

Full data: runs/YYYY-MM-DD/daily_trending_HK.json
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
| Agent uses today's date by mistake | Re-run with yesterday. SKILL.md defaults to `date -d "yesterday"` |

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

This reads today's `daily_trending_{REGION}.json`, the 7-days-ago file (if available),
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
daily_trending_{REGION}.json:

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
