---
name: hk-fnb-step-01-fetch
description: >
  Step 1 of the HK F&B trending keyword pipeline.
  Fetches raw data from Apify (Google Trends + Instagram hashtags + user posts),
  then normalizes into the pipeline's standard raw format.
  Outputs google_raw.json and instagram_raw.json for downstream steps.
---

# Step 1 — Fetch & Normalize

**Pipeline position:** first step. No upstream dependencies.

## Purpose

Fetch social media data from Apify, then normalize into pipeline format.

Two sub-steps:
1. **Fetch** — 15 parallel Apify actor runs (1 Google Trends + 4 IG hashtags + 10 IG users)
2. **Normalize** — `normalize_raw.py` transforms Apify raw → `google_raw.json` + `instagram_raw.json`

## Input

None (reads config files and env var `APIFY_TOKEN`).

## Output

| File | Content |
|------|---------|
| `runs/YYYY-MM-DD/raw/google_raw.json` | Normalized Google Trends records |
| `runs/YYYY-MM-DD/raw/instagram_raw.json` | Merged Instagram records (hashtags + users) |
| `runs/YYYY-MM-DD/raw/_apify/` | Raw Apify JSON (source of truth) |

### Output schema (both platforms)

```json
{
  "platform": "google_trends" | "instagram",
  "run_at": "2026-06-25T00:00:00+08:00",
  "window": { "start": "...", "end": "..." },
  "seed_context": { "broad_seed_group": ["香港美食", "hk food"] },
  "records": [
    {
      "raw_representative": "珍珠奶茶",
      "source_kind": "trending_search" | "hashtag" | "user_post",
      "current_volume": 85,
      "raw_payload": { ... }
    }
  ]
}
```

**Google Trends:** `raw_representative` = search term, `source_kind` = `"trending_search"`, `current_volume` = trend volume.

**Instagram:** `source_kind` = `"hashtag"` or `"user_post"`, `current_volume` = 1 per unique post. `raw_payload` includes: `caption_snippet` (500 chars), `likes`, `comments`, `reshare_count`, `hashtags`, `url`, `taken_at_timestamp`, `engagement_hint`, `geo` ("HK"), `source_username` (user_post only).

### Cross-Day Dedup

`normalize_raw.py` loads URLs from previous 6 days' `instagram_raw.json` and excludes any post whose URL has already been seen. Each post is counted only on its first appearance.

### Age Filter

`--max-age-days 30` (default): posts older than 30 days are discarded. Posts without timestamp are kept (fail-open). Set `--max-age-days 0` to disable.

## Procedure

### 1. Preflight

```bash
# Verify APIFY_TOKEN
test -n "$APIFY_TOKEN" || { echo "ERROR: APIFY_TOKEN not set"; exit 1; }

# Determine date (default: yesterday)
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)
RUN_DIR="runs/${TARGET_DATE}"
mkdir -p "${RUN_DIR}/raw/_apify"
```

### 2. Fetch (15 parallel actors)

Read seeds from `config/social_listening_v1.json`, actor IDs from `config/apify_actors_v1.json`. Run in parallel:

```bash
# Google Trends (1)
bash scripts/apify_fetch.sh "$GOOGLE_ACTOR_ID" "$GOOGLE_INPUT" "${RUN_DIR}/raw/_apify/google_apify_raw.json" 300 10 &

# IG hashtags (4) — iterate $INSTAGRAM_SEEDS
for seed in $INSTAGRAM_SEEDS; do
  hashtag="${seed#\#}"
  safe_name=$(echo "$hashtag" | python3 -c "import sys,hashlib; h=sys.stdin.read().strip(); print(hashlib.md5(h.encode()).hexdigest()[:8] + '_' + ''.join(c if c.isalnum() else '_' for c in h))")
  ig_input=$(echo "$INSTAGRAM_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); d['hashtag']='${hashtag}'; print(json.dumps(d))")
  bash scripts/apify_fetch.sh "$INSTAGRAM_ACTOR_ID" "$ig_input" "${RUN_DIR}/raw/_apify/ig_${safe_name}_apify_raw.json" 300 10 &
done

# IG users (10) — iterate $INSTAGRAM_USERS
for username in $INSTAGRAM_USERS; do
  safe_name=$(echo "$username" | python3 -c "import sys; s=sys.stdin.read().strip(); print(''.join(c if c.isalnum() else '_' for c in s))")
  ig_user_input=$(echo "$IG_USER_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); d['username']='${username}'; print(json.dumps(d))")
  bash scripts/apify_fetch.sh "$IG_USER_ACTOR_ID" "$ig_user_input" "${RUN_DIR}/raw/_apify/ig_user_${safe_name}_apify_raw.json" 300 10 &
done

wait
```

**Fail-open:** if some actors fail, continue with available data. Do not abort.

### 3. Normalize

```bash
python3 scripts/normalize_raw.py --date "$TARGET_DATE" --run-dir "$RUN_DIR" --config config/social_listening_v1.json
```

### 4. Verify

```bash
python3 -c "
import json, os
for platform in ['google', 'instagram']:
    path = f'${RUN_DIR}/raw/{platform}_raw.json'
    if not os.path.exists(path):
        print(f'{platform}: MISSING')
        continue
    with open(path) as f:
        data = json.load(f)
    print(f'{platform}: {len(data.get(\"records\", []))} records')
"
```

## Error Handling

| Scenario | Action |
|----------|--------|
| `APIFY_TOKEN` not set | Abort |
| Config files missing | Abort |
| All actors fail | Abort |
| Some actors fail | Continue, log warnings |
| `normalize_raw.py` fails | Abort |

## Dependencies

- **External:** Apify API (`APIFY_TOKEN`)
- **Scripts:** `scripts/apify_fetch.sh`, `scripts/normalize_raw.py`
- **Config:** `config/apify_actors_v1.json`, `config/social_listening_v1.json`
- **Output to Step 2A:** `runs/YYYY-MM-DD/raw/instagram_raw.json`
- **Output to Step 2B:** `runs/YYYY-MM-DD/raw/google_raw.json`
