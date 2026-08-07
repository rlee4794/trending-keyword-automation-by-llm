---
name: fnb-trending-keywords-apify-pipeline
description: >
  HK + TW F&B social media trending keyword pipeline.
  Fetches Instagram/Threads/Google Trends via Apify, filters by engagement,
  then LLM extracts dish/venue/cuisine keywords. On-demand: luxury dining (Step L).
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
| `python3` 3.10+ | stdlib + `openpyxl` (for Step 6 XLSX export) |
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
| "run trending pipeline" / "行trending pipeline" | Full run — **HK only** (Steps 1-6, see Date Convention) |
| "run trending pipeline --crossday-dedup" | Full run — HK only, **enable 6-day cross-day URL dedup** (remove posts that appeared in previous 6 days) |
| "run TW pipeline" / "行台灣pipeline" / "行TW" | Full run — **Taiwan only** (IG users + Google Trends TW, see Date Convention) |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending_HK.json or daily_trending_TW.json` → present Top 30 by category with background |
| "luxury analysis" / "貴價食材" / "高端餐飲" / "luxury dining" | Run **Step L** (luxury dining signal extraction, on-demand) |
| "export xlsx" / "export excel" / "匯出 xlsx" | Run **Step 6** standalone (re-export from existing daily_trending data) |

### ⚠️ Output format rule

All summary/analysis presentations in chat **must use markdown tables**,
not bullet lists. This applies to:
- Step 5 daily summary (each category as a table with appropriate columns)
- "show trends for YYYY-MM-DD" readout
- Any multi-row data display (top N lists, comparisons, rankings)

Exception: single-value answers and short explanations can remain as prose.

### ⚠️ Region selector rule

Default to **HK only**. Run Taiwan only when user explicitly says "TW" /
"台灣" / "Taiwan". See Quick Reference table above for per-phrase behavior.

### ⚠️ Step L is on-demand only

Step L (luxury dining extraction) is **NOT part of the daily pipeline**.

**Step L** — only when user explicitly asks for:
- "luxury analysis" / "貴價食材" / "高端餐飲" / "luxury dining" / "有咩貴嘢食"
- Any phrase about premium ingredients, fine dining, or high-end food trends

Do NOT run Step L automatically after a regular pipeline run.

### ⚠️ Already-run rule

If `daily_trending_{REGION}.json` for **TARGET_DATE** already exists and the user
asks about trends without explicitly requesting a re-run ("重跑" / "重新 fetch" /
"rerun"), do NOT re-execute. Read the existing file and present results directly
(see `docs/presentation.md` for format). Only re-run when the user explicitly
says "重跑" / "重新 fetch" / "rerun" / "再run多次".

## Pipeline Flow

```
Step 1: Fetch    → run_fetch.sh (xargs -P 30) → normalize_raw.py
Step 2: Filter   → filter_threshold.py (like OR share ≥ threshold, mode configurable)
Step 3: Extract  → Agent reads filtered posts + Google Trends → extracts keywords
Step 4: Assemble → assemble_output.py → daily_trending_{REGION}.json
Step 4.5: Background → Agent generates curated 50-70 char backgrounds for each keyword → writes back to daily_trending_{REGION}.json
Step 5: Summary  → Read daily_trending_{REGION}.json → present in chat (use curated backgrounds from Step 4.5)
Step 6: Export   → export_xlsx.py → formatted .xlsx workbook (reads keyword.background from Step 4.5)

⚠️ Step 6 is MANDATORY after Step 5. Agent must run it without asking.

--- on-demand only (not part of daily pipeline) ---

Step L: Luxury  → luxury_extract.py (format prompt) → Agent (semantic extraction) →
                  manual merge → daily_trending_{REGION}.json enriched with luxury_insights
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
      "concept": "沙嗲拼盤",
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

See `config/threshold.json` for current defaults and extraction scope.
Adjust `min_likes`/`min_shares` based on data volume — start conservative, widen if needed.

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

#### Abort-on-failure rule

After all actors finish, `run_fetch.sh` verifies every expected output file exists
and is non-empty. **If ANY platform (e.g. Threads, any single IG user/hashtag, Google)
fails to produce output → abort immediately. Do NOT proceed to Step 2.**

No retry. Individual actor failure = pipeline abort. Report which platform(s)
failed and stop.

```bash
# TARGET_DATE defaults to yesterday (see Date Convention)
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

The extraction prompt lives in `prompts/extract.md`. Read it, replace
`{CAPTIONS}` with formatted posts and `{GOOGLE_TERMS}` with Google Trends data,
then send to LLM for extraction. The prompt includes full instructions on
keyword types, concept extraction rules, geo_by_content tagging, DO NOT
rules, naming conventions, and the expected JSON output schema.

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

### Step 4.5 — Generate Curated Backgrounds (Agent)

After Step 4 produces `daily_trending_{REGION}.json`, the Agent **must** generate
curated backgrounds for each keyword before proceeding to Step 5 or Step 6.

**Why this step exists**: Step 5 markdown tables and Step 6 XLSX both need
50-70 character backgrounds that include restaurant names, context, and
characteristics. Raw caption excerpts are unreliable (restaurant names may
be in hashtags, mid-caption, or absent from the first 70 chars). Generating
curated backgrounds once and embedding them in `keywords[].background`
ensures consistency across all downstream outputs.

**Procedure**:

1. Read `daily_trending_{REGION}.json`
2. For each keyword with `post_count > 0`:
   - Find associated posts via `post_indices` or `sources`
   - Read each post's `caption_snippet`, `source`, and `extracted` fields
   - Synthesize a **50-70 character** (CJK count) curated background
   - Format: `[{source}] {餐廳名} {context}，{特色/反應}`
   - Store in `keywords[].background`
3. Re-save `daily_trending_{REGION}.json` with backgrounds embedded

**Background writing rules**:
- **50-70 CJK characters**, one line per keyword — no truncation mid-sentence
- **Must include restaurant/venue name**. If no specific name in captions,
  use district + type (e.g. "大角咀街坊麵包店", "銅鑼灣樓上Cafe")
- **Must include context**: why trending? (聯乘/新開/限時/排隊/口碑/跨平台/節日)
- **Must include key characteristic or reaction** (e.g. "爆餡排隊人龍",
  "Threads 熱議", "$62 套餐送角色卡")
- When `term != concept`, describe the dish using the concept as subject
- Use the most informative `source` as prefix (prefer @username over #hashtag)

Read `docs/presentation.md` § Step 4.5 for detailed prompt template.

### Step 5 — Present Summary

Show a detailed summary in chat, in two parts.

**Backgrounds**: Use the curated `keywords[].background` field from Step 4.5.
Do NOT generate new backgrounds on-the-fly during Step 5.

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

Read `docs/presentation.md` for full table templates, background extraction
rules, concept display conventions, and Google related_terms formatting.
Present each enabled category as a markdown table (Top 30, sorted by
engagement), with one-line background per item.

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Apify actor / platform fails (Step 1) | No retry. Abort entire pipeline immediately. See Step 1 abort-on-failure rule. |
| 0 posts pass threshold | Warn, suggest lowering `config/threshold.json` |
| LLM extraction fails | Retry once. If still failing, write posts without `extracted` field |
| Malformed JSON from LLM | Retry once with stricter prompt |
| Agent uses today's date by mistake | Re-run with correct TARGET_DATE (see Date Convention) |
| assemble_output.py fails (Step 4) | Check extraction file exists & is valid JSON. If missing, re-run Step 3. If malformed, fix manually. Abort if unrecoverable. |
| daily_trending.json missing or corrupt (Step 5) | Re-run Step 4 with validated extraction output. If still missing, report which step failed. |
| export_xlsx.py fails (Step 6) | Step 6 is mandatory — retry once. Check `openpyxl` installed (`pip install openpyxl`). Verify `daily_trending.json` exists. Check write permission on output path. If still failing, report error and output path. |
| luxury_extract.py fails (Step La) | Verify `daily_trending.json` exists (pipeline must complete first). Fix JSON if malformed before retrying. |
| Luxury LLM extraction fails (Step Lb) | Retry once. If still failing, skip luxury insights — pipeline output is still valid. |

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

The extraction framework (judgment criteria, output format) lives in
`prompts/luxury.md`. Read it before extracting — the prompt includes
the full luxury signal taxonomy, exclusion rules, and expected JSON schema.

### Step Lc — Merge

Manually merge the Agent's JSON into `daily_trending_{REGION}.json`:

```python
# daily["luxury_insights"] = agent_output
```

This adds a `luxury_insights` field to the daily trending file.

### Step 6 — Export XLSX

**⚠️ MANDATORY**: After Step 5 completes, immediately run Step 6 without asking.
This is a required pipeline step, not optional. Do NOT skip it.

Export the daily trending results to a formatted Excel workbook.

**Dependency**: `openpyxl` (Python package). Install with `pip install openpyxl` if missing.

```bash
# Export with default settings (HK, top 15 dishes, output to workspace)
python3 scripts/export_xlsx.py --date YYYY-MM-DD --region hk

# Custom output path and top N
python3 scripts/export_xlsx.py --date YYYY-MM-DD --region hk --output /path/to/output.xlsx --top 20
```

The workbook contains three sheets:

| Sheet | Content |
|-------|---------|
| **本日要點** | Auto-inferred daily highlights (signal + description) |
| **熱門菜式** | Top N dish keywords with term→concept, post count, likes, source background |
| **原始數據摘要** | Pipeline execution summary (date, thresholds, post counts, status) |

Output path defaults to `~/.openclaw/workspace/{REGION}_FB_Trending_{DATE}.xlsx`.

### Present Luxury Summary

Show in chat as markdown tables:

- **Top 10 luxury keywords** table: rank, term, type, key_signal, posts, likes
- **Signal distribution** table: category, count, representatives
- **Summary** prose: top trend + notable observations
