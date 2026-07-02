---
name: hk-fnb-step-01-fetch
description: >
  Step 1 of the HK F&B trending keyword pipeline.
  Fetches raw data from Apify (Google Trends + Instagram hashtags),
  then normalizes into the pipeline's standard raw format.
  Outputs google_raw.json and instagram_raw.json for downstream steps.
---

# Step 1 — Fetch & Normalize

**Pipeline position:** first step. No upstream dependencies.

## Purpose

Fetch today's social media data from two platforms via Apify actors, then
normalize the raw Apify output into the pipeline's standard record format.

Two sub-steps:
1. **Fetch** — trigger 5 parallel Apify actor runs (1 Google Trends + 4 Instagram hashtags), poll until complete, save raw Apify JSON
2. **Normalize** — transform Apify raw schemas into pipeline-normalized `google_raw.json` and `instagram_raw.json` with unified record structure

## Input

None (reads config files and env var).

## Output

| File | Content |
|---|---|
| `runs/YYYY-MM-DD/raw/google_raw.json` | Normalized Google Trends records |
| `runs/YYYY-MM-DD/raw/instagram_raw.json` | Normalized + merged Instagram records (4 hashtags → 1 file) |
| `runs/YYYY-MM-DD/raw/_apify/` | Raw Apify JSON preserved as single source of truth |

### Output schema

Both files share the same top-level structure:

```json
{
  "platform": "google_trends" | "instagram",
  "run_at": "2026-06-25T00:00:00+08:00",
  "window": {
    "start": "2026-06-24T00:00:00+08:00",
    "end": "2026-06-26T23:59:59+08:00"
  },
  "seed_context": {
    "broad_seed_group": ["香港美食", "hk food"]
  },
  "records": [
    {
      "raw_term": "珍珠奶茶",
      "source_kind": "trending_search" | "hashtag",
      "current_volume": 85,
      "raw_payload": { ... }
    }
  ]
}
```

**Google Trends record fields:**

| Field | Source (Apify raw) | Notes |
|---|---|---|
| `raw_term` | `term` | The trending search term |
| `source_kind` | fixed: `"trending_search"` | |
| `current_volume` | `trend_volume_raw` | Default 0 if missing |
| `raw_payload` | entire Apify item | Original data preserved |

**Instagram record fields:**

| Field | Source (Apify raw) | Notes |
|---|---|---|
| `raw_term` | search hashtag (e.g. `#hkfood`) | The hashtag used for this scrape |
| `source_kind` | fixed: `"hashtag"` | |
| `current_volume` | fixed: `1` | One post = one unit; aggregated by ranking |
| `raw_payload` | transformed Apify item | See fields below |

`raw_payload` for Instagram:

| Field | Source (Apify raw) | Notes |
|---|---|---|
| `caption_snippet` | `caption` | Truncated to 200 chars |
| `hashtags` | `hashtags` | Array of hashtag strings |
| `likes` | `like_count` | Default 0 |
| `comments` | `comment_count` | Default 0 |
| `engagement_hint` | computed | `"high"` / `"medium"` / `"low"` based on likes + comments×2 |
| `geo` | fixed: `"HK"` | |
| `taken_at_timestamp` | `taken_at_timestamp` | |
| `url` | `url` | |
| `reshare_count` | `reshare_count` | |

## Project Paths

All paths are relative to the skill directory (`skills/01-fetch/`) unless noted.

| Path | Purpose |
|---|---|
| `../../config/apify_actors_v1.json` | Apify actor IDs and dataset config |
| `../../config/social_listening_v1.json` | Platform seeds, weights, thresholds |
| `../../scripts/apify_fetch.sh` | Shell script: trigger actor, poll, download dataset |
| `../../scripts/normalize_raw.py` | Python script: transform Apify raw → pipeline format |
| `../../runs/YYYY-MM-DD/raw/` | Output directory for this step |

---

## Procedure

### 0. Pre-flight Checks

```bash
# Verify APIFY_TOKEN is set
if [ -z "$APIFY_TOKEN" ]; then
  echo "ERROR: APIFY_TOKEN environment variable is not set."
  echo "Set it with: export APIFY_TOKEN=your_token_here"
  exit 1
fi
```

If `APIFY_TOKEN` is missing, abort and tell the user to set it.

### 1. Determine Target Date

Default to **yesterday** (data for today is incomplete):

```bash
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d)
```

If the user specifies a date (e.g. "run trending for 2026-06-20"), use that instead.

Create the output directory:

```bash
RUN_DIR="runs/${TARGET_DATE}"
mkdir -p "${RUN_DIR}/raw/_apify"
```

### 2. Read Config

Load actor IDs and seeds from config files:

```bash
# Read from config/social_listening_v1.json
GOOGLE_SEEDS=$(python3 -c "import json; print(' '.join(json.load(open('config/social_listening_v1.json'))['broad_seeds']['google']))")
INSTAGRAM_SEEDS=$(python3 -c "import json; print(' '.join(json.load(open('config/social_listening_v1.json'))['broad_seeds']['instagram']))")

# Read actor config from config/apify_actors_v1.json
GOOGLE_ACTOR_ID=$(python3 -c "import json; print(json.load(open('config/apify_actors_v1.json'))['google']['actor_id'])")
GOOGLE_INPUT=$(python3 -c "import json; print(json.dumps(json.load(open('config/apify_actors_v1.json'))['google']['input']))")
INSTAGRAM_ACTOR_ID=$(python3 -c "import json; print(json.load(open('config/apify_actors_v1.json'))['instagram']['actor_id'])")
INSTAGRAM_INPUT=$(python3 -c "import json; print(json.dumps(json.load(open('config/apify_actors_v1.json'))['instagram']['input']))")
```

### 3. Fetch from Apify (Parallel)

Run 5 actors in parallel using `scripts/apify_fetch.sh`:

```bash
SCRIPTS="scripts"

# Google Trends (1 actor)
bash "${SCRIPTS}/apify_fetch.sh" \
  "$GOOGLE_ACTOR_ID" \
  "$GOOGLE_INPUT" \
  "${RUN_DIR}/raw/_apify/google_apify_raw.json" \
  300 10 &

# Instagram (4 hashtags, parallel)
for seed in $INSTAGRAM_SEEDS; do
  hashtag="${seed#\#}"  # strip leading #
  safe_name=$(echo "$hashtag" | tr -c 'a-zA-Z0-9_' '_')
  # Merge hashtag into actor input template
  ig_input=$(echo "$INSTAGRAM_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); d['hashtag']='${hashtag}'; print(json.dumps(d))")
  bash "${SCRIPTS}/apify_fetch.sh" \
    "$INSTAGRAM_ACTOR_ID" \
    "$ig_input" \
    "${RUN_DIR}/raw/_apify/ig_${safe_name}_apify_raw.json" \
    300 10 &
done

# Wait for all 5 to complete
wait
```

**`apify_fetch.sh` contract:**

```
Usage: apify_fetch.sh <actor_id> <input_json> <output_path> [timeout_secs] [poll_interval_secs]

Behavior:
- POST to start actor run → get runId
- Poll GET every N seconds until SUCCEEDED/FAILED/ABORTED/TIMED-OUT
- On SUCCEEDED: fetch dataset items, write to output_path, exit 0
- On FAILED/ABORTED/TIMED-OUT: exit 1
- On timeout: exit 1
- On empty dataset: write [] to output_path, exit 0
- Retry once on transient failure (HTTP 5xx, network error)
```

### 4. Check Fetch Results

After `wait`, check which actors succeeded:

```bash
FAILED=""
for f in "${RUN_DIR}/raw/_apify/"*.json; do
  if [ ! -s "$f" ]; then
    FAILED="$FAILED $(basename $f)"
  fi
done

if [ -n "$FAILED" ]; then
  echo "WARNING: Some fetches produced empty/missing files:$FAILED"
  echo "Pipeline will continue with available data."
fi
```

**Fail-open policy:** If some actors fail, continue with what succeeded.
Missing platforms will be noted in output metadata. Do NOT abort the entire
run for partial failures.

### 5. Normalize Raw Data

Run the normalize script to transform Apify raw → pipeline format:

```bash
python3 "${SCRIPTS}/normalize_raw.py" \
  --date "$TARGET_DATE" \
  --run-dir "$RUN_DIR" \
  --config "config/social_listening_v1.json"
```

**`normalize_raw.py` contract:**

```
Reads:
  runs/{date}/raw/_apify/google_apify_raw.json
  runs/{date}/raw/_apify/ig_*.json
  config/social_listening_v1.json (for broad_seed_group metadata)

Writes:
  runs/{date}/raw/google_raw.json
  runs/{date}/raw/instagram_raw.json

Behavior:
- Compute window = target_date ±1 day (single-day snapshot window)
- Google: map term→raw_term, trend_volume_raw→current_volume
- Instagram: merge 4 hashtag files, map caption→caption_snippet (200 chars),
  compute engagement_hint, set current_volume=1 per post
- Preserve original Apify data in raw_payload
- Skip platforms whose _apify raw files are missing/empty
```

### 6. Verify Output

```bash
python3 -c "
import json, os, sys

run_dir = '${RUN_DIR}'
errors = []

for platform in ['google', 'instagram']:
    path = os.path.join(run_dir, 'raw', f'{platform}_raw.json')
    if not os.path.exists(path):
        errors.append(f'MISSING: {path}')
        continue
    with open(path) as f:
        data = json.load(f)
    records = data.get('records', [])
    print(f'{platform}: {len(records)} records')
    if not records:
        print(f'  WARNING: empty records array')

if errors:
    print('ERRORS:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
else:
    print('Step 1 complete.')
"
```

---

## Error Handling

| Scenario | Action |
|---|---|
| `APIFY_TOKEN` not set | Abort. Tell user to set the env var. |
| Config files missing | Abort. Config is required. |
| All 5 actors fail | Abort. Nothing to process. |
| Some actors fail | Continue with available data. Log warnings. |
| Single actor times out | Retry once. If still failing, skip that actor. |
| Apify returns empty dataset | Write `[]`, continue. Empty data is valid. |
| normalize_raw.py fails | Abort. Check script output for details. |
| Output directory not writable | Abort. Check permissions. |

---

## Token Budget

| Item | Estimate |
|---|---|
| Shell exec calls (fetch + normalize) | 0 LLM tokens |
| Config reading | ~1K tokens |
| Verification output | ~500 tokens |
| **Total** | **~1.5K tokens** |

This step is almost entirely shell/Python execution. Agent only reads config
and verifies results.

---

## Dependencies

- **External:** Apify API (requires `APIFY_TOKEN` env var)
- **Scripts:** `scripts/apify_fetch.sh`, `scripts/normalize_raw.py`
- **Config:** `config/apify_actors_v1.json`, `config/social_listening_v1.json`
- **Output to Step 2A:** `runs/YYYY-MM-DD/raw/instagram_raw.json`
- **Output to Step 2B:** `runs/YYYY-MM-DD/raw/google_raw.json`
