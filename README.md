# Trending Keyword Automation By LLM

HK F&B social media trending keyword discovery pipeline.
Fetches Google Trends + Instagram + Threads data via Apify,
filters to high-engagement posts, then Agent extracts specific
dish names, venue names, and cuisine types.

## Pipeline (v2.0)

```
Apify fetch → normalize → threshold filter → Agent extraction → JSON output
```

Three steps:

1. **Fetch** — 15 parallel Apify actors (1 Google + 4 IG hashtags + 10 IG users),
   then `normalize_raw.py` merges + deduplicates
2. **Filter** — `filter_threshold.py` keeps posts above engagement threshold
   (like≥1000 AND share≥500 by default, adjustable in `config/threshold.json`)
3. **Extract** — Agent reads filtered posts + Google Trends, extracts dish/venue/cuisine
   keywords with emphasis on specificity (蝦拉麵 not 拉麵) and common HK Chinese names
   (壽司郎 not Sushiro)

## Output

`runs/YYYY-MM-DD/daily_trending.json` (schema v1.0):

```json
{
  "schema_version": "1.0",
  "date": "2026-07-07",
  "threshold": { "instagram": { "min_likes": 1000, "min_shares": 500 } },
  "posts": [
    {
      "platform": "instagram",
      "likes": 3200,
      "caption": "北角呢間隱世串燒店嘅沙嗲拼盤...",
      "extracted": { "dishes": ["沙嗲拼盤"], "venues": ["北角串燒店"] }
    }
  ],
  "google_trends": [{ "term": "壽司郎", "volume": 85 }],
  "keywords": [
    { "term": "沙嗲拼盤", "type": "dish", "post_count": 3, "total_likes": 8500 }
  ]
}
```

## Key Assets

| Path | Purpose |
|------|---------|
| `skills/SKILL.md` | Agent procedure (fetch → filter → extract → output) |
| `scripts/apify_fetch.sh` | Apify actor runner |
| `scripts/normalize_raw.py` | Apify raw → pipeline format + cross-day dedup |
| `scripts/filter_threshold.py` | Engagement threshold filter |
| `config/threshold.json` | Threshold config per platform |
| `config/apify_actors_v1.json` | Apify actor IDs and input templates |
| `config/social_listening_v1.json` | Platform seeds (hashtags + users) |

## Environment

| Variable | Purpose |
|----------|---------|
| `APIFY_TOKEN` | Apify API authentication |

## Quick Reference

| User says | Action |
|-----------|--------|
| "run trending pipeline" | Full run (fetch → filter → extract → output) |
| "show trends for YYYY-MM-DD" | Read `runs/YYYY-MM-DD/daily_trending.json` → split Social / Google |
| "compare trends this week" | Read 7 days, Agent describes patterns |
