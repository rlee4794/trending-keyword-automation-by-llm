---
name: fnb-trending-keywords-apify-pipeline
description: >
  HK + TW F&B social media trending keyword pipeline.
  Fetches Instagram/Threads/Google Trends via Apify, filters by engagement,
  then LLM extracts dish/venue/cuisine keywords. On-demand: trend comparison (Step T),
  luxury dining (Step L), restaurant discovery with OpenRice (Step R).
  ONLY triggered when the user explicitly names this skill:
  "fnb-trending-keywords-apify-pipeline" or "apify-pipeline".
  Never triggered by general food/trend/dining keywords.
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

All commands must be run from the skill directory (`~/.agents/skills/fnb-trending-keywords-apify-pipeline/`).

| Dependency | Version / Notes |
|------------|-----------------|
| `bash` 4+ | |
| `python3` 3.10+ | stdlib only — no external packages required |
| `curl` | |
| `jq` | JSON processing in shell scripts |
| `xargs` | concurrency control (`-P` flag required) |
| `APIFY_TOKEN` | Apify API token, set as environment variable |

`runs/` is a symlink → ArkDrive personal space for persistent output storage.

### ⚠️ Date Convention

> All pipeline runs operate on **yesterday's data** by default.
> - "跑今天的 pipeline" / "run today's pipeline" → data folder is `runs/YYYY-MM-DD/` where `YYYY-MM-DD` = yesterday
> - This applies regardless of which step you start from (Step 1, Step 2, partial rerun, etc.)
> - Only override when user explicitly specifies a date like "跑 7 月 8 號嘅 pipeline"

## Quick Reference

| User says | Action |
|-----------|--------|
| "run trending pipeline" / "行trending pipeline" | Full run — **HK only, defaults to yesterday** (Steps 1-4 + Summary) |
| "run trending pipeline --crossday-dedup" | Full run — HK only, **enable 6-day cross-day URL dedup** (remove posts that appeared in previous 6 days) |
| "run TW pipeline" / "行台灣pipeline" / "行TW" | Full run — **Taiwan only, defaults to yesterday** (IG users + Google Trends TW) |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending_HK.json or daily_trending_TW.json` → present Top 10 by category with background |
| "trend analysis" / "compare trends" / "變動" / "走勢" | Run **Step T** (7-day snapshot comparison, on-demand) |
| "luxury analysis" / "貴價食材" / "高端餐飲" / "luxury dining" | Run **Step L** (luxury dining signal extraction, on-demand) |
| "搵餐廳" / "餐廳推薦" / "find restaurants" / "有咩餐廳" | Run **Step R** (restaurant discovery via OpenRice, on-demand) |

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

### ⚠️ Step T, Step L & Step R are on-demand only

Step T (trend comparison), Step L (luxury dining extraction), and Step R (restaurant discovery)
are **NOT part of the daily pipeline**.

**Step T** — only when user explicitly asks for:
- "trend analysis" / "compare trends" / "走勢" / "變動" / "compared to last week"
- Any phrase that implies comparing today vs historical data

**Step L** — only when user explicitly asks for:
- "luxury analysis" / "貴價食材" / "高端餐飲" / "luxury dining" / "有咩貴嘢食"
- Any phrase about premium ingredients, fine dining, or high-end food trends

**Step R** — only when user explicitly asks for:
- "搵餐廳" / "餐廳推薦" / "find restaurants" / "有咩餐廳"
- Any phrase about discovering restaurants based on trending keywords
- Requires `daily_trending_{REGION}.json` to exist (pipeline must have run first)

Do NOT run Step T, Step L, or Step R automatically after a regular pipeline run.

### ⚠️ Already-run rule

If today's pipeline run has **already completed** (i.e. `daily_trending_{REGION}.json` for
**yesterday's date** exists and was generated today), and the user asks about trends **without** explicitly
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
Step 2: Filter   → filter_threshold.py (like OR share ≥ threshold, mode configurable)
Step 3: Extract  → Agent reads filtered posts + Google Trends → extracts keywords
Step 4: Assemble → assemble_output.py → daily_trending_{REGION}.json
Step 5: Summary  → Present daily results in chat

--- on-demand only (not part of daily pipeline) ---

Step T: Trends  → trend_comparison.py (prepare) → Agent (fuzzy match) →
                  trend_comparison.py (merge) → daily_trending_{REGION}.json enriched

Step L: Luxury  → luxury_extract.py (format prompt) → Agent (semantic extraction) →
                  manual merge → daily_trending_{REGION}.json enriched with luxury_insights

Step R: Restaurants → restaurant_discovery.py (prepare) → Agent (concept distillation) →
                      Agent calls openrice-restaurant-list + openrice-restaurant-detail skills →
                      restaurant_discovery.py (merge) → daily_trending_{REGION}.json enriched
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
    "instagram": { "min_likes": 1000, "min_shares": 500, "mode": "or" },
    "threads": { "min_likes": 1000, "min_shares": 500, "mode": "or" }
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
| `config/threshold.json` | Engagement thresholds, data quality checks, extraction scope (`extraction_scope`), and Google Trends toggle (`google.enabled`) |
| `config/apify_actors_v1.json` | Apify actor IDs |
| `config/social_listening_v1.json` | Platform seeds |

Threshold defaults:

```json
{
  "instagram": { "min_likes": 1000, "min_shares": 500, "mode": "or" },
  "threads": { "min_likes": 1000, "min_shares": 500, "mode": "or" },
  "google": { "_comment": "Set enabled to false to skip Google Trends entirely (fetch, extract, display).", "enabled": false, "min_volume": 0 },
  "extraction_scope": {
    "_comment": "Controls which keyword types are extracted, assembled, and displayed. Set to false to skip entirely.",
    "dishes": true,
    "venues": false,
    "cuisines": false
  },
  "restaurant_discovery": {
    "_comment": "Step R config. max_keywords: how many top dish keywords to search restaurants for. max_restaurants_per_keyword: cap per concept.",
    "max_keywords": 10,
    "max_restaurants_per_keyword": 10
  }
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
(`~/.agents/skills/fnb-trending-keywords-apify-pipeline/`).

### Step 1 — Fetch

Dispatch Apify actors via `run_fetch.sh`, which reads configs and uses `xargs -P`
to respect Apify's 32-actor concurrent limit. Default max-concurrent is 30.

**Hong Kong:** 16 actors (1 Google + 4 IG hashtags + 10 IG users + 1 Threads)
**Taiwan:** 57 actors (1 Google + 56 IG users)

```bash
# Determine date (default: yesterday — see Date Convention above)
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

Read `filtered/{region}/threshold_filtered.json` and `config/threshold.json`.

**extraction_scope**: Before extracting, check `config/threshold.json` → `extraction_scope`.
Only extract types whose value is `true`. If `venues: false`, skip all venue extraction
instructions below and omit the `venues` field from output. Same for `dishes` and `cuisines`.

The agent examines each post's `caption_snippet` and `hashtags`, plus `google_trends` terms.

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

4. **geo_by_content** (必須) — where the food/venue is physically located.
   Output a **free-form location tag**, NOT a yes/no bucket.
   - `"HK"` — clearly Hong Kong (香港地名、港式用語、香港分店、$HKD 標價)
   - `"TW"` — clearly Taiwan (台灣地名如一中街/逢甲/西門町、台灣手機格式 09xx-xxx-xxx、
     台灣分店命名如XX店/XX分店、台幣 NT$ 標價、台灣特有品牌)
   - `"JP"` — Japan (大阪、東京、京都、札幌、沖繩…)
   - `"KR"` — Korea (首爾、釜山、明洞…)
   - `"TH"` — Thailand (曼谷、清邁、布吉…)
   - `"MO"` — Macau
   - `"CN"` — Mainland China (深圳、上海、北京…)
   - `"SG"` — Singapore
   - `"MY"` — Malaysia
   - `null` — truly cannot determine (e.g. pure food photo with no location clues)

   Use ISO 3166-1 alpha-2 country codes where possible.
   If a post mentions both regions (e.g. "香港人去台北食XXX"),
   classify by where the FOOD is served, not the author's location.

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
      "cuisines": ["串燒"],
      "geo_by_content": "HK"
    },
    {
      "index": 1,
      "dishes": ["豬排", "千層酥"],
      "venues": ["KYK", "grenier"],
      "cuisines": ["日本菜", "咖啡"],
      "geo_by_content": "JP"
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
- `geo_by_content` — free-form location tag (e.g. `"HK"`, `"TW"`, `"JP"`, `"KR"`, …) or `null`
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
- **extraction_scope enforcement**: strips disabled fields from posts + filters keywords by disabled types (defense-in-depth, in case LLM still extracted them)
- Post-processing guards (stripping single-char / common-word false venues)
- Keyword aggregation with engagement stats
- Writing `daily_trending_{REGION}.json` + updating `runs/latest` symlink

### Step 5 — Present Summary

Show a detailed summary in chat, in two parts.

**Step 5 follows `extraction_scope` from `config/threshold.json`** — only display
categories whose corresponding scope key is `true`. For example, if `venues: false`,
skip the 📍 Social 熱門餐廳 table entirely.

The four possible categories are (each shown only if enabled):
1. 🔥 Social 熱門菜式 (dishes)
2. 📍 Social 熱門餐廳 (venues)
3. 🍽️ 熱門菜系 (cuisines)
4. 🔍 Google 熱搜 (controlled by `google.enabled` in threshold config; shown only when enabled)

If a keyword appears on both channels, tag it `🔥🔍` to signal cross-channel heat.

#### 5a — 本日要點 (Daily Highlights)

Before the tables, read `daily_trending_{REGION}.json` and cross-reference all
categories to identify **3–5 key signals** for the day. Output as a compact
prose block:

```
### 📊 本日要點

- **{signal label}**：{one-line narrative}（關聯：{comma-separated keywords}）
- ...
```

Signal types to look for:
- **品牌集中爆發** — same brand across multiple posts/categories
- **品類對戰** — multiple venues competing on same dish/cuisine
- **新店/新品熱潮** — new opening or product driving a spike
- **跨平台共振** — same keyword trending on both IG + Google
- **異常互動** — single post with unusually high likes/shares relative to others
- **Google 熱搜亮點** — notable search spikes with context (e.g. new store, seasonal)

Each signal is one bullet, one line. Keep it tight — this is a high-level scan,
not a data dump.

#### 5b — 分類表格 (Category Tables)

**Format: Top 10 per enabled category, with short background for each item.**
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
| daily_trending not found for Step R | Warn: "請先執行 pipeline（行 trending pipeline）再搵餐廳" |
| OpenRice search returns 0 results for a concept | Skip that concept, note in output |
| openrice skills unavailable | Last resort: Agent chooses fallback method (BUA / web_fetch / etc.) — only after confirming both skills are unavailable |
| Step R: Agent JSON malformed | Retry once. If still failing, skip merge |

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

---

## Step L — Luxury Dining Extraction (on-demand)

Extract luxury / premium dining signals from today's trending keywords and posts.
LLM reads the full `daily_trending_{REGION}.json` (keywords + posts) and uses
**semantic judgment** to identify luxury ingredients, premium formats, and
high-end dining experiences. No lexicon — the LLM decides what qualifies.

### Trigger

Only when user explicitly asks for:
- "luxury analysis" / "貴價食材" / "高端餐飲" / "luxury dining" / "有咩貴嘢食"
- Any phrase about premium ingredients, fine dining, or high-end food trends

### Step La — Format Prompt

```bash
python3 scripts/luxury_extract.py --date YYYY-MM-DD --region hk --output /tmp/luxury_prompt.txt
```

This formats `daily_trending_{REGION}.json` keywords + posts into a structured text
prompt the Agent reads for extraction.

### Step Lb — Agent Extraction

Agent reads `/tmp/luxury_prompt.txt` and extracts:

1. **Top 10 luxury keywords** — ranked by engagement (likes), with:
   - `term`: the dish/ingredient/format name
   - `type`: dish / cuisine / venue / experience
   - `key_signal`: what makes it luxury (e.g. "A4和牛+雪糕壽喜燒")
   - `post_count`, `likes`
2. **Signal distribution** — aggregated by category (e.g. 🦞 龍蝦, 🥩 和牛, 🍷 魚子醬)
   with representative keywords per category
3. **Summary** — high-level trend narrative

### Judgment Framework

LLM should consider a keyword luxury if it involves:

| Signal | Examples |
|--------|---------|
| **貴價食材** | 魚子醬、鵝肝、和牛、龍蝦、鮑魚、海膽、松露、花膠、燕窩、西班牙黑豚、貓山王榴槤 |
| **精緻料理形式** | Omakase、割烹、懷石料理、Fine Dining、米芝蓮星級、預約制限定 |
| **溢價體驗** | 人均 $500+、名人飯堂、聯乘限定、過江龍名店、星級名廚客座 |

Exclude: 連鎖快餐、茶餐廳日常、放題/任食（除非主打貴價食材如榴槤放題）、街頭小食。

### Output Format

Agent outputs JSON:

```json
{
  "top_keywords": [
    {"rank": 1, "term": "龍蝦", "type": "dish",
     "key_signal": "鐵板燒$888+預約制龍蝦湯拉麵",
     "post_count": 9, "likes": 22300}
  ],
  "signal_distribution": {
    "🦞 龍蝦": {"count": 2, "representatives": ["龍蝦", "龍蝦汁海膽闊麵"]}
  },
  "summary": {
    "luxury_signal_count": 15,
    "top_trend": "..."
  }
}
```

### Step Lc — Merge

Manually merge the Agent's JSON into `daily_trending_{REGION}.json`:

```python
# daily["luxury_insights"] = agent_output
```

This adds a `luxury_insights` field to the daily trending file.

### Present Luxury Summary

Show in chat as markdown tables:

- **Top 10 luxury keywords** table: rank, term, type, key_signal, posts, likes
- **Signal distribution** table: category, count, representatives
- **Summary** prose: top trend + notable observations

---

## Step R — Restaurant Discovery (on-demand)

For each trending dish keyword, distill a pure food concept, search OpenRice
for restaurants, then fetch full details (name, description, BO services).

### Trigger

Only when user explicitly asks for:
- "搵餐廳" / "餐廳推薦" / "find restaurants" / "有咩餐廳"
- Any phrase about discovering restaurants based on trending keywords

Requires `daily_trending_{REGION}.json` to exist from a previous pipeline run.
If not found, warn: "請先執行 pipeline（行 trending pipeline）再搵餐廳"

### Config

```json
// config/threshold.json → restaurant_discovery
{
  "max_keywords": 10,
  "max_restaurants_per_keyword": 10
}
```

`max_keywords` controls how many top dish keywords (sorted by total_likes)
to process. `max_restaurants_per_keyword` caps results per concept.

### Step Ra — Prepare Prompt

```bash
python3 scripts/restaurant_discovery.py --date YYYY-MM-DD --region hk --prepare --output /tmp/restaurant_prompt.txt
```

Reads `daily_trending_{REGION}.json`, extracts all `type: "dish"` keywords
(sorted by total_likes, up to `max_keywords`), and formats a structured
prompt with each keyword's term, engagement stats, and background.

### Step Rb — Concept Distillation (Agent)

Agent reads `/tmp/restaurant_prompt.txt` and distills each keyword into
a pure food concept suitable for OpenRice search.

#### Concept Distillation Prompt

---

You are an F&B search concept distillation assistant.

## Task

For each trending dish keyword + background below, distill the **most
representative pure food concept** for searching restaurants on OpenRice.

## Rules

- **Strip noise**: remove brand names (7-11, McDonald's), campaign markers
  (聯乘, 限定, 期間), and region qualifiers (中環, 旺角)
- **Keep specificity**: "龍蝦湯拉麵" stays as-is, do NOT reduce to "拉麵".
  "沙嗲牛肉麵" stays as-is, do NOT reduce to "牛肉麵"
- **Prefer Traditional Chinese**: if the original is Chinese, keep it.
  If English (e.g. "craft beer"), keep English
- **One concept per keyword**: output exactly one concept string
- If the keyword is already a clean food concept (no noise to strip),
  output it unchanged

## Examples

| Keyword + Background | Distilled Concept |
|---------------------|-------------------|
| 梅菜扣肉飯 — 源自 7-11 聯乘貼文 | 梅菜扣肉 |
| 龍蝦湯拉麵 — 中環新店限定 | 龍蝦湯拉麵 |
| 沙嗲牛 — foodie 熱議 | 沙嗲牛肉 |
| omakase — 尖沙咀新場 | omakase |
| 珍珠奶茶 — 多間新開手搖店 | 珍珠奶茶 |

## Input Keywords

{KEYWORD_PROMPT}

## Output

Return ONLY JSON. No markdown, no explanation.

```json
[
  {"keyword": "梅菜扣肉飯", "concept": "梅菜扣肉"},
  {"keyword": "龍蝦湯拉麵", "concept": "龍蝦湯拉麵"}
]
```

---

### Step Rc — Search & Detail (Agent)

For each distilled concept, the Agent **MUST** use the dedicated skills in sequence.
**No other method is allowed unless both skills are confirmed unavailable.**

1. **`openrice-restaurant-list` skill** — search OpenRice for the concept,
   return restaurant name + URL list (up to `max_restaurants_per_keyword`)
2. **`openrice-restaurant-detail` skill** — for each restaurant URL, fetch:
   - Name
   - Description (meta description: area + specialty + signature dishes)
   - BO services: booking preorder, booking offer, takeaway, vouchers,
     bill discount

**Skill fallback (last resort only)**: if `openrice-restaurant-list` or
`openrice-restaurant-detail` skills are **both confirmed unavailable**,
the Agent may fall back to a method of its choice (e.g. BUA / browser-use
for OpenRice scraping, web_fetch, etc.). Do NOT skip the skills proactively —
always attempt them first.

Agent outputs structured JSON:

```json
[
  {
    "concept": "梅菜扣肉",
    "source_keyword": "梅菜扣肉飯",
    "source_background": "源自 7-11 聯乘貼文，兩日內爆發",
    "restaurants": [
      {
        "name": "XXX小廚",
        "url": "https://www.openrice.com/zh/hongkong/r-xxx",
        "description": "位於旺角，主打傳統客家菜，招牌梅菜扣肉肥瘦適中...",
        "bo_services": {
          "booking_preorder": [
            {"name": "[1位用] 晚市套餐 HK$188", "url": "..."}
          ],
          "booking_offer": [
            {"type": "offer", "tag": "特惠", "title": "晚市8折", "thumb": "...", "url": "..."},
            {"type": "reward", "reward": "賞$2 Rice Dollars"}
          ],
          "takeaway": [
            {"status": "active", "text": "外賣自取 9 折"}
          ],
          "vouchers": [
            {"discount": "82折", "title": "椒麻冷鍋魚", "priceNew": "HK$318", "priceOld": "HK$388", "thumb": "...", "url": "..."}
          ],
          "bill_discount": [
            {"text": "以指定電子錢包埋單，即賺0.5% Rice Dollars回贈"}
          ]
        }
      }
    ]
  }
]
```

Rules:
- Each concept gets its own array of restaurants
- `bo_services` fields: `booking_preorder`, `booking_offer`, `takeaway`,
  `vouchers`, `bill_discount`. Empty arrays `[]` if none found
- `booking_offer` includes both `type: "offer"` (折扣/贈品) and
  `type: "reward"` (Rice Dollars 獎賞)
- `takeaway` includes both `status: "active"` and `status: "inactive"`
- Skip concepts that return 0 OpenRice results

### Step Rd — Merge Results

```bash
python3 scripts/restaurant_discovery.py --date YYYY-MM-DD --region hk --merge /tmp/agent_output.json
```

Merges restaurant discoveries into `daily_trending_{REGION}.json`:

```json
{
  "restaurant_discoveries": [
    {
      "concept": "梅菜扣肉",
      "source_keyword": "梅菜扣肉飯",
      "source_background": "源自 7-11 聯乘貼文，兩日內爆發",
      "restaurants": [...]
    }
  ]
}
```

### Present Restaurant Discovery Summary

Show in chat as markdown tables, one section per concept:

```
🏪 關鍵詞餐廳推薦

### 梅菜扣肉（來自關鍵詞「梅菜扣肉飯」）
> 背景：源自 7-11 聯乘貼文，兩日內爆發

| # | 餐廳 | 簡介 | BO服務 |
|---|------|------|--------|
| 1 | **XXX小廚** (旺角) | 主打傳統客家菜，招牌梅菜扣肉肥瘦適中 | 訂座優惠、外賣自取 |
| 2 | **YYY飯店** (深水埗) | ... | 餐飲券、埋單優惠 |
| ... | ... | ... | ... |

### 龍蝦湯拉麵（來自關鍵詞「龍蝦湯拉麵」）
> 背景：中環新店限定，foodie 熱烈討論

| # | 餐廳 | 簡介 | BO服務 |
|---|------|------|--------|
| 1 | ... | ... | ... |

Full data: runs/YYYY-MM-DD/daily_trending_HK.json
```

**Display rules**:
- One `###` section per concept, with source keyword in parentheses
- Background quoted with `>` blockquote
- Table columns: `#`, `餐廳`, `簡介`, `BO服務`
- Restaurant name **bold**, area in parentheses extracted from description
- Description: one compact line summarizing the restaurant (area + specialty)
- BO服務: comma-separated list of available service types, omitting types
  with empty arrays. Map: `booking_preorder` → 訂座預購套餐,
  `booking_offer` → 訂座優惠, `takeaway` → 外賣自取,
  `vouchers` → 餐飲券, `bill_discount` → 埋單優惠
- Skip concepts with 0 restaurants found
- End with full data path
